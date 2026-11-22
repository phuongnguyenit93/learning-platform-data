# Xây dựng producer, consumer SQS và luồng xử lý DLQ

Amazon Simple Queue Service (Amazon SQS) là dịch vụ hàng đợi message được quản lý, giúp producer gửi công việc vào queue và consumer xử lý độc lập với tốc độ phát sinh. Producer không cần biết consumer đang chạy ở đâu hoặc có online tại thời điểm gửi hay không. SQS lưu message trong thời gian retention đã cấu hình và cung cấp cơ chế nhận, ẩn tạm thời, xác nhận xóa và retry.

Khi consumer liên tục không xử lý được một message, message đó có thể chiếm thời gian xử lý và gây nghẽn queue chính. Dead-letter queue (DLQ) tách các message lỗi ra để nhóm vận hành kiểm tra, tìm nguyên nhân và quyết định cách xử lý. Redrive cho phép chuyển message đã khắc phục từ DLQ trở lại queue để xử lý lại.

Bài thực hành này xây dựng một luồng order processing dùng SQS Standard, Python và boto3. Người học tạo DLQ trước, cấu hình redrive policy cho queue chính, gửi message bằng producer, nhận và xóa message bằng consumer, cố tình tạo một poison message để quan sát retry/DLQ, sau đó sửa lỗi và redrive message. Toàn bộ tài nguyên được tạo trong một AWS account và Region sandbox.

## 1. Mục tiêu học tập

Sau bài thực hành, người học có thể:

- Giải thích vai trò của producer, consumer, queue và message.
- Phân biệt SQS Standard và FIFO queue.
- Tạo queue và DLQ bằng AWS CLI.
- Cấu hình VisibilityTimeout, long polling, retention và redrive policy.
- Gửi message và message attributes bằng boto3.
- Nhận message theo batch và xử lý bằng consumer.
- Xóa message sau khi xử lý thành công.
- Giải thích visibility timeout, receipt handle và approximate receive count.
- Tạo poison message để quan sát retry và chuyển vào DLQ.
- Kiểm tra message trong DLQ và đọc CloudWatch metrics.
- Sửa consumer và redrive message về queue chính.
- Thiết kế idempotency để chịu được duplicate delivery.
- Cấp IAM permission theo least privilege.
- Dọn dẹp queue và nhận diện các rủi ro vận hành.

## 2. Kiến trúc và luồng xử lý

Trong bài lab, producer gửi event OrderCreated vào queue orders. Consumer nhận message, kiểm tra payload, thực hiện xử lý rồi gọi DeleteMessage. Nếu consumer gặp lỗi, nó không xóa message. Sau khi visibility timeout hết hạn, message có thể được nhận lại. Khi số lần nhận đạt ngưỡng maxReceiveCount, SQS chuyển message sang DLQ.

~~~text
+------------------+
| Order Producer   |
| Python / boto3   |
+--------+---------+
         |
         | SendMessage
         v
+------------------+       Redrive policy
| orders queue     |--------------------------+
| SQS Standard     |                          |
+--------+---------+                          |
         |                                    |
         | ReceiveMessage                     |
         v                                    |
+------------------+                          |
| Order Consumer   |                          |
| Python / boto3   |                          |
+--------+---------+                          |
         |                                    |
         +-- Success --> DeleteMessage        |
         |                                    |
         +-- Failure --> No delete            |
                          |                   |
                          | Visibility timeout|
                          | Retry              |
                          +-------------------+
                                              |
                            maxReceiveCount reached
                                              |
                                              v
                                   +------------------+
                                   | orders DLQ       |
                                   | Inspect / Fix    |
                                   +--------+---------+
                                            |
                                            | StartMessageMoveTask
                                            v
                                      orders queue
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| Producer | Tạo event và gửi message vào queue |
| Source queue | Lưu công việc chờ consumer xử lý |
| Consumer | Nhận, kiểm tra và xử lý message |
| Visibility timeout | Khoảng thời gian message đã nhận bị ẩn với consumer khác |
| Receipt handle | Token đại diện cho lần nhận cụ thể, dùng để xóa hoặc đổi visibility |
| Redrive policy | Xác định DLQ và số lần nhận tối đa |
| DLQ | Giữ message không xử lý thành công để điều tra |
| Redrive task | Di chuyển message từ DLQ đến queue đích |

SQS Standard cung cấp khả năng phân phối at-least-once. Một message có thể được giao nhiều hơn một lần, do đó consumer phải chịu được duplicate. Không được xem thao tác nhận message là bằng chứng xử lý đã hoàn tất; message chỉ được xóa sau khi side effect cần thiết đã thành công.

## 3. Chuẩn bị môi trường

### 3.1 Yêu cầu

Chuẩn bị:

- Một AWS account sandbox.
- Một IAM role/user được cấp quyền SQS cho bài lab.
- AWS CLI v2.
- Python 3.10 trở lên.
- boto3.
- PowerShell trên Windows hoặc shell tương đương.
- Một Region được phép sử dụng, ví dụ ap-southeast-1.

Không chạy bài lab trong production account. Queue là tài nguyên tính phí theo request và có thể phát sinh chi phí nếu để message hoặc tài nguyên tồn tại lâu.

### 3.2 Đăng nhập bằng IAM Identity Center

Nếu tổ chức dùng AWS IAM Identity Center, cấu hình SSO profile:

~~~powershell
aws configure sso --profile sandbox
aws sso login --profile sandbox
aws sts get-caller-identity --profile sandbox
~~~

Xác minh account ID và ARN trả về đúng account sandbox. Không dùng root access key hoặc nhúng access key vào mã nguồn.

Nếu tổ chức cấp quyền bằng cơ chế khác, dùng profile đã được cấu hình theo quy định nội bộ.

### 3.3 Tạo Python virtual environment

Trong thư mục làm việc của bài lab:

~~~powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install boto3
~~~

Thiết lập biến môi trường cho profile, Region và queue URL sau khi tạo queue:

~~~powershell
$env:AWS_PROFILE = "sandbox"
$env:AWS_REGION = "ap-southeast-1"
~~~

Kiểm tra boto3 nhận đúng danh tính:

~~~powershell
python -c "import boto3; print(boto3.Session().region_name)"
aws sts get-caller-identity --profile $env:AWS_PROFILE
~~~

Nếu PowerShell chặn activate script, dùng Python bằng đường dẫn .\.venv\Scripts\python.exe hoặc điều chỉnh execution policy theo quy định của máy. Không cần thay đổi policy máy dùng chung chỉ để chạy bài lab.

## 4. Chọn loại queue

SQS có hai loại queue chính:

| Tiêu chí | Standard | FIFO |
|---|---|---|
| Thứ tự | Best-effort ordering | Giữ thứ tự trong từng MessageGroupId |
| Throughput | Cao, tự động mở rộng | Phụ thuộc throughput mode và message group |
| Duplicate | Có thể xảy ra | Có deduplication trong phạm vi thời gian được hỗ trợ; consumer vẫn nên idempotent |
| Tên queue | Tên thông thường | Kết thúc bằng .fifo |
| DLQ | Standard DLQ | FIFO DLQ |
| Phù hợp | Event, task độc lập, xử lý song song | Workflow cần thứ tự theo nhóm |

Bài lab dùng Standard queue vì các order event được xử lý độc lập. Nếu nghiệp vụ cần giữ thứ tự theo khách hàng hoặc đơn hàng, FIFO có thể phù hợp hơn. Khi dùng FIFO, chọn MessageGroupId để xác định phạm vi thứ tự và cân nhắc tác động của DLQ đến chuỗi xử lý. Nếu chuyển một message ra DLQ, thứ tự nghiệp vụ ban đầu có thể bị gián đoạn.

## 5. Hiểu các thuộc tính quan trọng

### 5.1 Visibility timeout

Khi consumer nhận message, SQS không xóa message. Nó đặt message vào trạng thái invisible trong khoảng VisibilityTimeout. Trong thời gian này consumer khác không nhìn thấy message đó qua thao tác receive thông thường.

- Nếu xử lý thành công, consumer gọi DeleteMessage.
- Nếu consumer lỗi hoặc dừng trước khi xóa, message xuất hiện lại sau khi timeout hết.
- Nếu xử lý lâu hơn timeout, một consumer khác có thể nhận message khi consumer đầu vẫn đang làm việc.
- Có thể gọi ChangeMessageVisibility để gia hạn hoặc rút ngắn thời gian ẩn.

Chọn timeout dài hơn thời gian xử lý dự kiến và read timeout của SDK. Với tác vụ có thời gian xử lý biến động, consumer có thể gia hạn visibility bằng heartbeat. Visibility timeout tối đa là 12 giờ cho một lần nhận; công việc dài hơn cần được chia nhỏ hoặc điều phối bằng dịch vụ workflow phù hợp.

### 5.2 Long polling

Long polling cho phép SQS chờ message xuất hiện trước khi trả response. WaitTimeSeconds nhận giá trị từ 1 đến 20 giây; bài lab dùng 20 giây để giảm empty response và số request không cần thiết.

Khi dùng long polling, HTTP read timeout của SDK phải lớn hơn WaitTimeSeconds. Boto3 mặc định có read timeout đủ dài cho ví dụ này; nếu tùy chỉnh client config, hãy kiểm tra lại.

### 5.3 Retention period

Message retention period là thời gian SQS giữ message chưa bị xóa. Phạm vi cấu hình từ 1 phút đến 14 ngày. Bài lab đặt source queue 4 ngày và DLQ 14 ngày.

Với Standard queue, enqueue timestamp gốc được giữ khi message chuyển sang DLQ. Thời gian message đã nằm trong source queue được tính vào retention của DLQ. Metric ApproximateAgeOfOldestMessage trên DLQ phản ánh thời điểm message chuyển vào DLQ, còn thời hạn hết hạn vẫn dựa trên enqueue timestamp gốc. Vì vậy, đặt retention của DLQ dài hơn source queue để có đủ thời gian điều tra.

### 5.4 Redrive policy và maxReceiveCount

Redrive policy gắn source queue với DLQ. maxReceiveCount xác định số lần consumer có thể nhận message mà chưa xóa trước khi SQS chuyển message sang DLQ.

Bài lab đặt maxReceiveCount = 3 để quan sát nhanh. Đây là giá trị minh họa; production cần chọn ngưỡng dựa trên loại lỗi, thời gian retry, SLA và chi phí. Nếu dùng Lambda event source mapping, AWS khuyến nghị maxReceiveCount ít nhất là 5 để có đủ lần retry cho function.

## 6. Tạo DLQ trước

DLQ phải tồn tại trước khi gắn vào source queue. DLQ và source queue phải cùng AWS account, cùng Region và cùng loại queue.

Đặt biến môi trường PowerShell:

~~~powershell
$Region = "ap-southeast-1"
$Profile = "sandbox"
$Suffix = Get-Date -Format "yyyyMMddHHmmss"
$DlqName = "orders-dlq-lab-$Suffix"
$SourceName = "orders-lab-$Suffix"
~~~

Tạo Standard DLQ với retention 14 ngày và long polling 20 giây:

~~~powershell
$DlqUrl = aws sqs create-queue --queue-name $DlqName --attributes '{"MessageRetentionPeriod":"1209600","ReceiveMessageWaitTimeSeconds":"20"}' --query QueueUrl --output text --region $Region --profile $Profile
~~~

Lấy ARN của DLQ:

~~~powershell
$DlqArn = aws sqs get-queue-attributes --queue-url $DlqUrl --attribute-names QueueArn --query "Attributes.QueueArn" --output text --region $Region --profile $Profile
~~~

Kiểm tra URL và ARN:

~~~powershell
$DlqUrl
$DlqArn
~~~

Nếu queue name đã tồn tại hoặc create request trả lỗi, kiểm tra account, Region và queue đã có trước đó chưa. Không xóa queue đang được workload khác sử dụng chỉ để chạy lại bài lab.

## 7. Tạo source queue và cấu hình redrive policy

Tạo redrive policy bằng ARN vừa lấy:

~~~powershell
$RedrivePolicy = @{ deadLetterTargetArn = $DlqArn; maxReceiveCount = "3" } | ConvertTo-Json -Compress
$QueueAttributes = @{ VisibilityTimeout = "30"; ReceiveMessageWaitTimeSeconds = "20"; MessageRetentionPeriod = "345600"; RedrivePolicy = $RedrivePolicy } | ConvertTo-Json -Compress
$SourceUrl = aws sqs create-queue --queue-name $SourceName --attributes $QueueAttributes --query QueueUrl --output text --region $Region --profile $Profile
~~~

Giải thích:

| Attribute | Giá trị | Ý nghĩa |
|---|---:|---|
| VisibilityTimeout | 30 giây | Message được ẩn sau khi nhận |
| ReceiveMessageWaitTimeSeconds | 20 giây | Bật long polling |
| MessageRetentionPeriod | 345600 giây | Giữ message 4 ngày |
| RedrivePolicy.maxReceiveCount | 3 | Số lần nhận trước khi chuyển DLQ |
| RedrivePolicy.deadLetterTargetArn | DLQ ARN | Đích của message lỗi |

Lấy source queue ARN:

~~~powershell
$SourceArn = aws sqs get-queue-attributes --queue-url $SourceUrl --attribute-names QueueArn --query "Attributes.QueueArn" --output text --region $Region --profile $Profile
~~~

Đặt biến môi trường để Python script dùng queue URL:

~~~powershell
$env:SQS_QUEUE_URL = $SourceUrl
$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region
~~~

Xác minh các thuộc tính:

~~~powershell
aws sqs get-queue-attributes --queue-url $SourceUrl --attribute-names All --region $Region --profile $Profile
~~~

Kiểm tra RedrivePolicy trỏ đúng DLQ ARN và maxReceiveCount là 3. Kiểm tra DLQ có retention dài hơn source queue.

SQS có RedriveAllowPolicy để giới hạn queue nào được phép dùng một DLQ. Mặc định DLQ cho phép các source queue trong cùng account/Region sử dụng. Trong production, cân nhắc policy byQueue để chỉ cho phép các source queue được chỉ định; chế độ này hỗ trợ tối đa 10 source queue ARN. Không cấu hình denyAll cho DLQ đang được dùng.

## 8. Cấp quyền IAM theo vai trò

Không cần cấp quyền quản trị SQS cho producer và consumer. Tách quyền theo nhiệm vụ:

| Principal | Quyền cần thiết | Resource |
|---|---|---|
| Queue provisioner | sqs:CreateQueue, sqs:GetQueueAttributes, sqs:SetQueueAttributes, sqs:GetQueueUrl, sqs:TagQueue, sqs:DeleteQueue | Hai queue của lab |
| Producer | sqs:SendMessage | Source queue |
| Consumer | sqs:ReceiveMessage, sqs:DeleteMessage, sqs:ChangeMessageVisibility, sqs:GetQueueAttributes | Source queue |
| DLQ operator | sqs:ReceiveMessage, sqs:GetQueueAttributes | DLQ |
| Redrive operator | sqs:StartMessageMoveTask, sqs:ListMessageMoveTasks, sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes trên DLQ và sqs:SendMessage trên queue đích | DLQ và source queue |

Ví dụ policy rút gọn cho producer và consumer:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendOrderEvents",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:orders-lab-REPLACE"
    },
    {
      "Sid": "ConsumeOrderEvents",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:orders-lab-REPLACE"
    }
  ]
}
~~~

Thay account ID, Region và tên queue bằng ARN thực tế. Đây là policy tổng hợp để minh họa hai nhóm action; khi gán quyền thật, tách thành hai policy/role riêng để producer chỉ có SendMessage và consumer chỉ có quyền receive/delete/visibility cần thiết.

Đối với redrive, AWS yêu cầu quyền bắt đầu move task và nhận/xóa/đọc thuộc tính trên DLQ; queue đích cần quyền sqs:SendMessage. Nếu queue được mã hóa bằng AWS KMS, redrive có thể cần kms:Decrypt cho key nguồn và kms:GenerateDataKey/kms:Decrypt cho key đích tùy cấu hình.

## 9. Tạo producer bằng Python và boto3

Producer tạo event JSON và gửi vào source queue. Mỗi event có eventId duy nhất để consumer dùng làm idempotency key trong hệ thống thật.

Tạo file producer.py:

~~~python
import argparse
import json
import os
import uuid
from datetime import datetime, timezone

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument(
        "--poison",
        action="store_true",
        help="Send one event that the initial consumer will reject",
    )
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")

    session = boto3.Session(
        profile_name=os.getenv("AWS_PROFILE"),
        region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
    )
    sqs = session.client("sqs")
    queue_url = os.environ["SQS_QUEUE_URL"]

    for index in range(args.count):
        event = {
            "eventId": str(uuid.uuid4()),
            "eventType": "OrderCreated",
            "orderId": f"ORD-{uuid.uuid4().hex[:12].upper()}",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "simulateFailure": bool(args.poison and index == 0),
        }

        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(event, separators=(",", ":")),
            MessageAttributes={
                "eventType": {
                    "DataType": "String",
                    "StringValue": "OrderCreated",
                }
            },
        )

        print(
            f"Sent orderId={event['orderId']} "
            f"eventId={event['eventId']} "
            f"messageId={response['MessageId']}"
        )


if __name__ == "__main__":
    main()
~~~

Chạy producer để gửi 5 message bình thường:

~~~powershell
python producer.py --count 5
~~~

Gửi một poison message:

~~~powershell
python producer.py --count 1 --poison
~~~

Producer không xử lý message sau khi gửi. Response của SendMessage chứa MessageId do SQS cấp và MD5OfMessageBody/các checksum liên quan tùy response. MessageId là ID của message trong SQS; eventId là ID nghiệp vụ do ứng dụng tạo và nên được giữ ổn định nếu message cần được phát lại.

## 10. Tạo consumer bằng Python và boto3

Consumer dùng long polling để chờ message. Khi xử lý thành công, consumer gọi DeleteMessage với ReceiptHandle của lần nhận hiện tại. Nếu xử lý lỗi, ví dụ poison message, consumer không xóa message.

Tạo file consumer.py:

~~~python
import argparse
import json
import os

import boto3


def process_order(event, fix_poison=False):
    if event.get("simulateFailure") and not fix_poison:
        raise ValueError("Simulated poison message: unsupported order payload")

    # Lab handler: replace this print with the real business operation.
    # In production, persist eventId as an idempotency key before acknowledging.
    print(
        f"Processed orderId={event.get('orderId')} "
        f"eventId={event.get('eventId')}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fix-poison",
        action="store_true",
        help="Simulate a deployed handler fix for the lab poison event",
    )
    args = parser.parse_args()

    session = boto3.Session(
        profile_name=os.getenv("AWS_PROFILE"),
        region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
    )
    sqs = session.client("sqs")
    queue_url = os.environ["SQS_QUEUE_URL"]

    print("Consumer started. Press Ctrl+C to stop.")

    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            VisibilityTimeout=30,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
            MessageAttributeNames=["All"],
        )

        messages = response.get("Messages", [])
        if not messages:
            print("No visible messages; waiting...")
            continue

        for message in messages:
            receipt_handle = message["ReceiptHandle"]
            receive_count = message.get("Attributes", {}).get(
                "ApproximateReceiveCount", "unknown"
            )

            try:
                event = json.loads(message["Body"])
                print(
                    f"Received messageId={message['MessageId']} "
                    f"receiveCount={receive_count}"
                )

                process_order(event, fix_poison=args.fix_poison)

                # Acknowledge only after the business operation succeeds.
                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt_handle,
                )
                print(f"Deleted messageId={message['MessageId']}")

            except Exception as error:
                # Deliberately do not delete failed messages.
                # SQS makes them visible again after the visibility timeout.
                print(
                    f"Processing failed for messageId={message['MessageId']}: "
                    f"{error}. Message was not deleted."
                )


if __name__ == "__main__":
    main()
~~~

Chạy consumer:

~~~powershell
python consumer.py
~~~

Consumer tiếp tục long poll cho đến khi người học nhấn Ctrl+C. Khi queue không có message, nó chờ tối đa 20 giây cho mỗi lần receive. Trong ứng dụng thực tế, hãy cấu hình shutdown handling để ngừng nhận message mới, hoàn tất hoặc dừng an toàn tác vụ đang xử lý và giải phóng tài nguyên.

## 11. Kiểm tra luồng xử lý thành công

Với consumer đang chạy:

1. Mở terminal thứ hai.
2. Sao chép URL và ARN đã in ra ở terminal thứ nhất, sau đó đặt biến cho terminal thứ hai:

~~~powershell
$Region = "ap-southeast-1"
$Profile = "sandbox"
$SourceUrl = "<paste the source queue URL from terminal 1>"
$DlqUrl = "<paste the DLQ URL from terminal 1>"
$SourceArn = "<paste the source queue ARN from terminal 1>"
$DlqArn = "<paste the DLQ ARN from terminal 1>"
$env:AWS_PROFILE = $Profile
$env:AWS_REGION = $Region
$env:SQS_QUEUE_URL = $SourceUrl
~~~

3. Gửi 5 message bằng producer.
4. Quan sát consumer nhận và xử lý từng event.
5. Xác nhận consumer gọi DeleteMessage sau khi xử lý.

Kiểm tra số message visible và not visible:

~~~powershell
aws sqs get-queue-attributes --queue-url $SourceUrl --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --region $Region --profile $Profile
~~~

Các thuộc tính này là số liệu xấp xỉ và có thể cập nhật trễ. Không dùng một lần đọc để kết luận queue đã rỗng tuyệt đối. Hãy kết hợp log consumer, CloudWatch metrics và trạng thái xử lý nghiệp vụ.

Kết quả mong đợi:
- Producer in ra MessageId cho mỗi event.
- Consumer in ra orderId và eventId.
- Consumer in ra thông báo đã xóa message.
- Số message visible giảm về 0 sau khi xử lý hết.
- DLQ chưa có message từ các event bình thường.

## 12. Tạo poison message và quan sát retry

Poison message là message luôn gây lỗi khi consumer xử lý, ví dụ payload sai schema, giá trị không hợp lệ hoặc một điều kiện nghiệp vụ không thể hoàn thành.

Dừng consumer hiện tại bằng Ctrl+C nếu cần, sau đó gửi một poison message:

~~~powershell
python producer.py --count 1 --poison
~~~

Khởi động consumer không có --fix-poison:

~~~powershell
python consumer.py
~~~

Consumer sẽ nhận message có simulateFailure = true, ném lỗi mô phỏng và không gọi DeleteMessage. Sau 30 giây visibility timeout, message có thể được nhận lại. ApproximateReceiveCount tăng theo các lần nhận; khi đạt ngưỡng redrive policy, SQS chuyển message sang DLQ.

Để quan sát:
- Theo dõi log consumer và ApproximateReceiveCount.
- Đợi message chuyển khỏi source queue.
- Kiểm tra số message visible trên DLQ.
- Kiểm tra source queue không còn giữ poison message ở trạng thái visible.

Lấy số lượng message trên DLQ:

~~~powershell
aws sqs get-queue-attributes --queue-url $DlqUrl --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible --region $Region --profile $Profile
~~~

Với visibility timeout 30 giây và ngưỡng nhận là 3, quá trình có thể mất hơn một phút vì SQS cần thời gian giữa các lần nhận. SQS xử lý phân tán nên không nên phụ thuộc vào một mốc giây chính xác trong bài lab.

### 12.1 Vì sao không xóa message khi xử lý lỗi?

Nếu consumer xóa message trước khi hoàn tất business operation, ứng dụng có thể mất công việc. Nếu consumer không xóa sau khi xử lý thành công, message có thể được giao lại và side effect có thể lặp lại.

Quy tắc quan trọng:
- Chỉ xóa sau khi xử lý thành công.
- Khi lỗi tạm thời, để message retry hoặc điều chỉnh visibility theo backoff.
- Khi lỗi không thể tự phục hồi, dùng DLQ để cách ly.
- Ghi log đủ thông tin để xác định nguyên nhân.
- Thiết kế idempotency để duplicate không gây tác động sai.

## 13. Kiểm tra message trong DLQ

Có thể mở Amazon SQS console:
1. Chọn đúng Region.
2. Mở queue có tên orders-dlq-lab-...
3. Chọn Send and receive messages.
4. Poll for messages để xem message body và attributes.
5. Ghi lại eventId, orderId, receive count và lỗi ứng dụng tương ứng.

Lưu ý: Polling DLQ cũng là một lần nhận message. Message sẽ chuyển sang trạng thái invisible trong visibility timeout. Nếu chuẩn bị chạy redrive task, hãy chờ visibility timeout hết hoặc đưa visibility về 0 theo quy trình đã kiểm soát. Không xóa message khỏi DLQ trước khi đã lưu thông tin điều tra và quyết định cách phục hồi.

DLQ giúp cô lập message lỗi, nhưng không tự sửa payload hoặc xác định nguyên nhân. Hãy đối chiếu message với log producer/consumer, schema version, deployment version và các dependency mà consumer gọi.

## 14. Sửa lỗi và redrive message

Trong lab, poison message lỗi do consumer cố tình từ chối simulateFailure. Giả lập việc triển khai phiên bản handler đã sửa bằng cách chạy consumer với --fix-poison.

Dừng consumer cũ. Trước khi redrive:
- Xác nhận nguyên nhân lỗi đã được sửa.
- Xác nhận consumer mới có thể xử lý message.
- Kiểm tra queue chính có đủ capacity.
- Kiểm tra message đang không bị giữ invisible do thao tác inspect.
- Xác nhận operator có quyền redrive.

Khởi động message move task:

~~~powershell
aws sqs start-message-move-task --source-arn $DlqArn --destination-arn $SourceArn --max-number-of-messages-per-second 5 --region $Region --profile $Profile
~~~

SQS redrive là tác vụ bất đồng bộ. Kiểm tra trạng thái:

~~~powershell
aws sqs list-message-move-tasks --source-arn $DlqArn --max-results 10 --region $Region --profile $Profile
~~~

Theo dõi trạng thái task đến khi hoàn tất. Sau đó chạy consumer với handler đã sửa:

~~~powershell
python consumer.py --fix-poison
~~~

Message được redrive về source queue và consumer mới xử lý thành công. Kiểm tra queue visible count và DLQ count sau khi task hoàn tất.

### 14.1 Giới hạn của redrive

SQS redrive:
- Chuyển message từ DLQ về source queue hoặc queue đích cùng loại.
- Có thể giới hạn tốc độ di chuyển để tránh làm quá tải consumer.
- Không hỗ trợ lọc hoặc sửa message trong lúc redrive.
- Đặt lại retention period cho message được redrive.
- Cấp MessageId và enqueue time mới cho message sau khi redrive.

Nếu payload cần sửa trước khi phát lại, không dùng redrive trực tiếp. Operator có thể đọc message, tạo một message đã sửa vào queue đích với cùng business eventId nếu phù hợp, xác minh việc gửi thành công rồi mới xóa message cũ khỏi DLQ. Cần có audit trail để tránh phát lại hai lần.

## 15. Idempotency và duplicate delivery

SQS Standard có mô hình at-least-once delivery. Trong một số trường hợp message có thể được giao lại dù consumer đã nhận trước đó. Ví dụ:
- Consumer xử lý xong nhưng chết trước khi gọi DeleteMessage.
- DeleteMessage thất bại do lỗi mạng.
- Visibility timeout hết trong khi consumer vẫn đang xử lý.
- Message được redrive hoặc producer gửi lại cùng event.

Consumer production cần idempotent. Một cách phổ biến là dùng business event ID làm idempotency key và lưu trạng thái đã xử lý trong database có tính bền vững.

Ví dụ logic:

~~~text
Receive message
      |
      v
Read eventId
      |
      v
Check idempotency record
      |
      +-- Already processed --> Delete message
      |
      +-- Not processed
              |
              v
       Apply business operation
              |
              v
       Persist result + eventId
              |
              v
       Delete message
~~~

Nếu side effect và idempotency record nằm trong cùng database, dùng transaction để tránh trường hợp side effect thành công nhưng record idempotency chưa được ghi. Nếu side effect nằm ở hệ thống ngoài, cần thiết kế idempotency key hoặc reconciliation phù hợp.

Không chỉ dựa vào SQS MessageId để chống duplicate nghiệp vụ. Redrive có thể cấp MessageId mới, trong khi eventId do producer tạo có thể giữ nguyên.

## 16. Visibility timeout và xử lý công việc lâu

Nếu xử lý một message mất nhiều thời gian hơn visibility timeout, message có thể được giao cho consumer khác trước khi công việc đầu tiên kết thúc.

Các cách xử lý:
- Đặt visibility timeout lớn hơn thời gian xử lý dự kiến.
- Dùng ChangeMessageVisibility để gia hạn trong lúc xử lý.
- Dùng heartbeat để gia hạn theo chu kỳ.
- Chia tác vụ dài thành nhiều bước nhỏ.
- Chuyển workflow dài sang Step Functions hoặc cơ chế job phù hợp.

Ví dụ gia hạn visibility bằng boto3:

~~~python
sqs.change_message_visibility(
    QueueUrl=queue_url,
    ReceiptHandle=receipt_handle,
    VisibilityTimeout=120,
)
~~~

Giá trị trên đặt message invisible thêm 120 giây tính từ lúc gọi API. Tổng thời gian visibility cho một lần nhận không vượt giới hạn 12 giờ. Nếu không còn xử lý message, có thể đặt VisibilityTimeout = 0 để message hiển thị lại, nhưng chỉ làm vậy khi đã dừng xử lý và tránh tạo cạnh tranh giữa các consumer.

ReceiptHandle thay đổi theo từng lần receive. Luôn dùng receipt handle mới nhất của lần nhận hiện tại khi gọi DeleteMessage hoặc ChangeMessageVisibility.

## 17. Theo dõi queue và DLQ bằng CloudWatch

Amazon SQS tích hợp CloudWatch metrics. Các metric quan trọng:

| Metric | Ý nghĩa | Điều cần quan sát |
|---|---|---|
| ApproximateNumberOfMessagesVisible | Số message sẵn sàng nhận | Backlog tăng kéo dài |
| ApproximateNumberOfMessagesNotVisible | Số message đang in-flight | Consumer xử lý chậm hoặc không xóa |
| ApproximateNumberOfMessagesDelayed | Số message đang bị delay | Delivery delay hoặc message timer |
| ApproximateAgeOfOldestMessage | Tuổi message cũ nhất theo semantics của queue | SLA xử lý bị vượt |
| NumberOfMessagesSent | Số message gửi | Lưu lượng producer |
| NumberOfMessagesReceived | Số lần nhận message | Retry hoặc duplicate tăng |
| NumberOfMessagesDeleted | Số lần xóa message | Tỷ lệ hoàn tất xử lý |

Đặt alarm cho DLQ khi ApproximateNumberOfMessagesVisible lớn hơn 0. Với source queue, theo dõi backlog, age of oldest message và số lần nhận/xóa. Các metric số lượng message là approximate và có thể không cập nhật ngay sau mỗi thao tác.

### 17.1 Tín hiệu cảnh báo gợi ý

- DLQ visible count lớn hơn 0.
- ApproximateAgeOfOldestMessage vượt SLA.
- Source queue backlog tăng liên tục.
- Received tăng mạnh nhưng Deleted không tăng tương ứng.
- In-flight message tăng và giữ cao.
- Consumer error rate tăng sau deployment.
- Redrive task chạy quá lâu hoặc không hoàn tất.

Không chỉ dựa vào số lượng message. Hãy kết hợp log ứng dụng, request ID, eventId, queue metrics và deployment version để tìm nguyên nhân.

## 18. SQS encryption và bảo mật message

SQS hỗ trợ server-side encryption. Chọn SSE-SQS hoặc SSE-KMS tùy yêu cầu quản lý key và kiểm soát truy cập. Với SSE-KMS, producer, consumer và operator có thể cần quyền KMS tương ứng; KMS key policy cũng phải cho phép principal phù hợp.

Các nguyên tắc:
- Dùng IAM role cho producer và consumer.
- Chỉ producer có quyền SendMessage.
- Chỉ consumer cần thiết có quyền ReceiveMessage/DeleteMessage.
- Tách quyền redrive cho operator hoặc runbook role.
- Giới hạn queue ARN thay vì Resource: *.
- Không đưa password, access key, token hoặc dữ liệu nhạy cảm không cần thiết vào message body.
- Mã hóa dữ liệu ở tầng ứng dụng khi có yêu cầu riêng.
- Dùng TLS khi gọi AWS API.
- Theo dõi CloudTrail cho các thao tác quản trị queue và redrive.

Nếu dùng DLQ, hãy kiểm soát ai được đọc message lỗi. DLQ có thể chứa payload nhạy cảm hoặc thông tin debug không nên hiển thị cho mọi developer.

## 19. Tích hợp SQS với AWS Lambda

Bài lab dùng consumer Python tự poll queue để người học hiểu rõ ReceiveMessage, visibility timeout và DeleteMessage. Trong hệ thống serverless, có thể dùng Lambda event source mapping để Lambda poll SQS và gọi function theo batch.

Các điểm cần nhớ:
- Queue và Lambda function phải ở cùng Region; có thể ở account khác nếu cấu hình quyền phù hợp.
- Lambda execution role cần quyền đọc queue, thường dùng AWSLambdaSQSQueueExecutionRole.
- Visibility timeout của source queue nên ít nhất bằng 6 lần function timeout.
- Nếu có batching window, tính thêm thời gian batching vào visibility timeout.
- AWS khuyến nghị maxReceiveCount ít nhất là 5 cho Lambda consumer.
- Mặc định, nếu một message trong batch lỗi, cả batch có thể được retry.
- Dùng ReportBatchItemFailures để chỉ trả lại những message lỗi khi function xử lý batch.
- Lambda event source mapping cũng có at-least-once behavior; function cần idempotent.

Không dùng visibility timeout 30 giây của lab làm mặc định cho Lambda production. Hãy tính từ function timeout, batch size, batching window và thời gian xử lý thực tế.

## 20. Sự cố thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Producer AccessDenied | Thiếu sqs:SendMessage hoặc queue policy chặn | Kiểm tra IAM, queue resource policy và SCP |
| Consumer không nhận message | Sai queue URL/Region/profile hoặc message đang invisible | Kiểm tra GetQueueAttributes, account identity và in-flight count |
| Consumer nhận message lặp lại | At-least-once delivery hoặc không xóa message | Kiểm tra receipt handle, DeleteMessage và idempotency |
| Message quay lại source queue | Consumer không xóa hoặc visibility timeout hết | Kiểm tra log lỗi và receive count |
| Message không vào DLQ | Redrive policy sai, sai ARN hoặc DLQ type không khớp | Đọc RedrivePolicy, queue type và RedriveAllowPolicy |
| DLQ không có message dù consumer lỗi | Chưa đủ receive count hoặc consumer vẫn đang xử lý | Theo dõi ApproximateReceiveCount và visibility timeout |
| DeleteMessage lỗi | Dùng receipt handle cũ hoặc sai queue URL | Dùng receipt handle của lần receive hiện tại |
| Long polling timeout | HTTP read timeout ngắn hơn WaitTimeSeconds | Tăng SDK read timeout lớn hơn 20 giây |
| Redrive AccessDenied | Thiếu quyền trên DLQ hoặc destination queue | Kiểm tra quyền StartMessageMoveTask, Receive/Delete/GetAttributes và SendMessage |
| Redrive không chuyển message | Message đang invisible, task đang chạy hoặc queue type không khớp | Chờ visibility timeout, kiểm tra move task và queue type |
| DLQ message bị hết hạn | DLQ retention quá ngắn | Đặt retention DLQ dài hơn source queue |
| Lambda retry cả batch | Chưa bật partial batch response | Cấu hình ReportBatchItemFailures và sửa handler |

Khi gặp AccessDenied, xác định principal, action, queue ARN và Region trước. Không cấp quyền sqs:* trên mọi queue để xử lý tạm thời nếu chưa tìm được policy layer gây deny.

## 21. Dọn dẹp tài nguyên sau lab

Trước khi xóa:
1. Dừng producer và consumer.
2. Xác nhận không còn redrive task đang RUNNING.
3. Lưu log hoặc screenshot cần thiết.
4. Xác nhận không còn message cần điều tra.
5. Xác nhận queue đúng là queue được tạo cho lab.

Xóa source queue trước, sau đó xóa DLQ:

~~~powershell
aws sqs delete-queue --queue-url $SourceUrl --region $Region --profile $Profile
aws sqs delete-queue --queue-url $DlqUrl --region $Region --profile $Profile
~~~

Xóa queue là thao tác không thể khôi phục message đã lưu. Không chạy lệnh trên với URL queue production hoặc queue dùng chung.

Sau cleanup, thu hồi IAM permission tạm nếu đã tạo policy riêng và xóa file/biến môi trường có chứa thông tin không còn cần thiết. Nếu queue được tạo bằng IaC trong môi trường thực tế, xóa stack theo quy trình của stack owner thay vì xóa từng resource thủ công.

## 22. Kết quả mong đợi và tiêu chí hoàn thành

Bài lab hoàn tất khi:

- [ ] Đã đăng nhập đúng AWS sandbox account và Region.
- [ ] Đã tạo DLQ trước source queue.
- [ ] Source queue có redrive policy trỏ đúng DLQ.
- [ ] Long polling được bật với 20 giây.
- [ ] Visibility timeout được cấu hình phù hợp với consumer lab.
- [ ] Producer gửi được ít nhất 5 message bình thường.
- [ ] Consumer nhận và xóa message sau khi xử lý thành công.
- [ ] Poison message được nhận nhiều lần và chuyển vào DLQ.
- [ ] Người học xem được message và receive count trong DLQ.
- [ ] Consumer đã được sửa và message được redrive về source queue.
- [ ] Consumer mới xử lý thành công message sau redrive.
- [ ] Đã kiểm tra CloudWatch metrics của source queue và DLQ.
- [ ] Đã giải thích được vì sao consumer cần idempotent.
- [ ] Đã xóa hai queue sau khi kết thúc bài.

## 23. Bài tập mở rộng

### Bài 1: Thay đổi maxReceiveCount

Đổi maxReceiveCount từ 3 thành 5.

Yêu cầu: quan sát số lần nhận và thời gian chuyển message sang DLQ. Giải thích vì sao production không nên đặt ngưỡng quá thấp nếu lỗi có thể tự phục hồi.

### Bài 2: Thay đổi visibility timeout

Đặt visibility timeout thành 5 giây trong môi trường lab và giả lập xử lý mất 10 giây.

Yêu cầu: quan sát duplicate processing khi có hai consumer. Đề xuất timeout phù hợp và cách dùng ChangeMessageVisibility.

### Bài 3: Chạy hai consumer

Khởi động hai tiến trình consumer cùng đọc source queue.

Yêu cầu: quan sát phân phối message và giải thích vì sao hai consumer không nên xử lý cùng một message đồng thời trong điều kiện bình thường, nhưng vẫn phải idempotent vì at-least-once.

### Bài 4: Tạo lỗi payload

Thay producer để gửi JSON không có eventId hoặc sai kiểu dữ liệu.

Yêu cầu: thiết kế validation, log lỗi và quyết định trường hợp nào nên retry, trường hợp nào nên đưa DLQ.

### Bài 5: Kiểm tra redrive thủ công

Gửi một message lỗi vào DLQ, sửa payload bằng cách tạo message mới ở source queue và xóa message cũ sau khi xác nhận.

Yêu cầu: lưu lại eventId, MessageId cũ/mới và lý do thay đổi. Giải thích vì sao redrive task không thể sửa message body.

### Bài 6: Chuyển sang FIFO

Tạo hai queue FIFO với tên kết thúc bằng .fifo.

Yêu cầu: cấu hình FifoQueue, MessageGroupId, MessageDeduplicationId hoặc content-based deduplication. Tạo FIFO DLQ và giải thích tác động đến thứ tự khi message bị chuyển sang DLQ.

### Bài 7: Tích hợp Lambda

Tạo Lambda function đọc event từ source queue bằng event source mapping.

Yêu cầu: cấu hình execution role, visibility timeout tối thiểu theo function timeout, maxReceiveCount và partial batch response. Kiểm tra một message lỗi không khiến các message thành công trong batch bị retry không cần thiết.

## 24. Câu hỏi tự kiểm tra

1. Producer và consumer có trách nhiệm gì trong mô hình SQS?
2. Vì sao producer không cần biết consumer đang online?
3. Standard queue và FIFO queue khác nhau ở điểm nào?
4. Visibility timeout làm gì sau khi consumer nhận message?
5. Receipt handle được dùng trong thao tác nào?
6. Vì sao phải xóa message sau khi xử lý thành công?
7. Điều gì xảy ra nếu consumer lỗi và không xóa message?
8. Long polling có thời gian chờ tối đa bao nhiêu giây?
9. maxReceiveCount điều khiển điều gì?
10. Vì sao DLQ phải được tạo trước source queue?
11. DLQ và source queue cần cùng những thuộc tính loại nào?
12. Vì sao retention của Standard DLQ nên dài hơn source queue?
13. Poison message là gì?
14. Vì sao SQS Standard có thể giao message nhiều lần?
15. Idempotency key nên dựa trên trường nào của event?
16. ChangeMessageVisibility dùng khi nào?
17. Vì sao không nên xóa message trước khi side effect hoàn tất?
18. Redrive task có thể sửa hoặc lọc message không?
19. Vì sao message có MessageId mới sau redrive vẫn nên giữ eventId nghiệp vụ?
20. Những quyền IAM nào cần cho consumer?
21. Những quyền IAM nào cần cho redrive operator?
22. CloudWatch metric nào giúp theo dõi backlog?
23. Vì sao visibility timeout của Lambda/SQS cần ít nhất 6 lần function timeout?
24. Partial batch response giải quyết vấn đề gì?

Gợi ý trả lời:

1. Producer gửi event; consumer nhận và xử lý event.
2. Queue lưu message để consumer nhận sau.
3. Standard ưu tiên throughput và best-effort order; FIFO giữ thứ tự theo message group.
4. Ẩn message tạm thời với consumer khác.
5. DeleteMessage và ChangeMessageVisibility cho lần receive cụ thể.
6. Để xác nhận message đã được xử lý.
7. Message xuất hiện lại sau visibility timeout và có thể retry.
8. 20 giây.
9. Số lần nhận trước khi message chuyển vào DLQ.
10. SQS cần DLQ ARN tồn tại khi cấu hình redrive policy.
11. Cùng account, Region và queue type.
12. Với Standard queue, enqueue timestamp gốc vẫn được dùng để tính retention sau khi chuyển DLQ.
13. Message luôn gây lỗi hoặc không thể xử lý thành công.
14. SQS Standard có at-least-once delivery.
15. Business event ID do producer tạo, ví dụ eventId.
16. Khi cần gia hạn hoặc rút ngắn thời gian message bị ẩn.
17. Có thể làm mất message nếu xử lý chưa xong nhưng đã xóa.
18. Không; redrive chỉ di chuyển message.
19. Để nhận diện cùng một business event và chống xử lý lặp.
20. ReceiveMessage, DeleteMessage, ChangeMessageVisibility và GetQueueAttributes.
21. StartMessageMoveTask và quyền nhận/xóa/đọc thuộc tính trên DLQ, SendMessage trên destination.
22. ApproximateNumberOfMessagesVisible, ApproximateAgeOfOldestMessage và ApproximateNumberOfMessagesNotVisible.
23. Để Lambda có thời gian xử lý batch và retry khi bị throttling.
24. Chỉ trả lại message lỗi thay vì retry toàn bộ batch.

## 25. Tài liệu tham khảo chính thức

- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html)
- [Creating an Amazon SQS standard queue](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/creating-sqs-standard-queues.html)
- [Using dead-letter queues in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Configuring a dead-letter queue](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue.html)
- [Dead-letter queue redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html)
- [Setting up long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/best-practices-setting-up-long-polling.html)
- [Configuring visibility timeouts](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/working-with-visibility-timeouts.html)
- [Amazon SQS CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [Amazon SQS security best practices](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-security-best-practices.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Creating and configuring an Amazon SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Boto3 SQS client reference](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html)

Các giá trị timeout, retention, throughput và quota cần được kiểm tra theo queue type, Region và workload. Trước khi triển khai production, hãy đo thời gian xử lý thực tế, thử duplicate delivery, retry, DLQ redrive, encryption và cleanup trong môi trường staging.
