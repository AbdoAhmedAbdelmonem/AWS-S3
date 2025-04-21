import os
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={
    r"/upload": {"origins": "*"},
    r"/aws-config": {"origins": "*"},
    r"/files": {"origins": "*"},
    r"/delete/*": {"origins": "*"}
})

load_dotenv()  # Load environment variables

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend-backend communication

# AWS Configuration
AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
S3_BUCKET = os.getenv('S3_BUCKET')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Initialize S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION
)

@app.route('/aws-config', methods=['GET'])
def get_aws_config():
    return jsonify({
        "AWS_ACCESS_KEY": AWS_ACCESS_KEY,
        "AWS_SECRET_KEY": AWS_SECRET_KEY,
        "S3_BUCKET": S3_BUCKET,
        "AWS_REGION": AWS_REGION
    })

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'csv', 'xlsx', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    try:
        # Secure filename and add timestamp
        filename = f"{datetime.now().timestamp()}_{secure_filename(file.filename)}"

        # Upload to S3
        s3.upload_fileobj(
            file,
            S3_BUCKET,
            filename,
            ExtraArgs={'ContentType': file.content_type}
        )

        # Generate pre-signed URL (valid for 1 hour)
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': filename},
            ExpiresIn=3600  # 1 hour
        )

        return jsonify({
            "success": True,
            "filename": filename,
            "download_url": download_url,
            "message": "File uploaded successfully"
        })

    except NoCredentialsError:
        return jsonify({"error": "AWS credentials not configured"}), 500
    except ClientError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/files', methods=['GET'])
def list_files():
    try:
        # List all objects in S3 bucket
        response = s3.list_objects_v2(Bucket=S3_BUCKET)

        if 'Contents' not in response:
            return jsonify({"files": []})

        files = []
        for item in response['Contents']:
            files.append({
                "filename": item['Key'],
                "size": item['Size'],
                "last_modified": item['LastModified'].isoformat(),
                "download_url": s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET, 'Key': item['Key']},
                    ExpiresIn=3600
                )
            })

        return jsonify({"files": files})

    except ClientError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=filename)
        return jsonify({"success": True, "message": f'File {filename} deleted successfully'}), 200
    except ClientError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)