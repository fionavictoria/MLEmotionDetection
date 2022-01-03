import os
import inference
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
  return render_template('index.html')

@app.route('/my-link/')
def my_link():
  # start the inference phase
  result = inference.initiate()
  if(result):
      data = [{'result': result}]
      #return result containing the detected emotion
      return render_template('result.html', data=data)

if __name__ == '__main__':
  app.run(host=os.getenv('IP', '0.0.0.0'),
            port=int(os.getenv('PORT', 4444)),debug=True)
