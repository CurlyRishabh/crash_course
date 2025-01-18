from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from celery import Celery
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv(SECRET_KEY)

# MongoDB setup
client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017/'))
db = client['expense_tracker']
expenses_collection = db['expenses']

# Celery setup
app.config['CELERY_BROKER_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
app.config['CELERY_RESULT_BACKEND'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

celery = Celery(
    app.name,
    broker=app.config['CELERY_BROKER_URL'],
    backend=app.config['CELERY_RESULT_BACKEND']
)
celery.conf.update(app.config)

@celery.task
def generate_expense_report(start_date, end_date):
    """
    Background task to generate expense report for a date range
    """
    pipeline = [
        {
            '$match': {
                'date': {
                    '$gte': start_date,
                    '$lte': end_date
                }
            }
        },
        {
            '$group': {
                '_id': '$category',
                'total': {'$sum': '$amount'},
                'count': {'$sum': 1}
            }
        }
    ]
    
    report = list(expenses_collection.aggregate(pipeline))
    return report

@app.route('/')
def index():
    expenses = list(expenses_collection.find().sort('date', -1))
    total = sum(expense['amount'] for expense in expenses)
    return render_template('index.html', expenses=expenses, total=total)

@app.route('/add', methods=['POST'])
def add_expense():
    if request.method == 'POST':
        expense = {
            'title': request.form['title'],
            'amount': float(request.form['amount']),
            'category': request.form['category'],
            'date': datetime.utcnow()
        }
        
        expenses_collection.insert_one(expense)
        flash('Expense added successfully!', 'success')
        return redirect(url_for('index'))

@app.route('/delete/<expense_id>')
def delete_expense(expense_id):
    expenses_collection.delete_one({'_id': ObjectId(expense_id)})
    flash('Expense deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/update/<expense_id>', methods=['POST'])
def update_expense(expense_id):
    expenses_collection.update_one(
        {'_id': ObjectId(expense_id)},
        {
            '$set': {
                'title': request.form['title'],
                'amount': float(request.form['amount']),
                'category': request.form['category']
            }
        }
    )
    flash('Expense updated successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/generate-report', methods=['POST'])
def request_report():
    start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
    
    # Trigger the Celery task
    task = generate_expense_report.delay(start_date, end_date)
    
    flash('Report generation started! Task ID: ' + task.id, 'success')
    return redirect(url_for('index'))

@app.route('/report-status/<task_id>')
def report_status(task_id):
    task = generate_expense_report.AsyncResult(task_id)
    if task.ready():
        # result = task.result  # Get the actual result of the task
        return ({'status': 'completed', 'result': task.get()})
    else:
        return jsonify({'status': 'pending'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
