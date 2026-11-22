# Retry, destination và dead-letter queue

> **Chương:** Điện toán Lambda  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless; học cách thiết kế triển khai an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Trong hệ thống **event-driven**, một lời gọi **AWS Lambda** có thể thất bại vì lỗi ứng dụng, timeout, thiếu quyền, dịch vụ phụ thuộc không khả dụng hoặc không còn concurrency. Nếu xử lý sai, cùng một đơn hàng có thể bị thanh toán hai lần, email được gửi lặp, thông điệp bị mắc kẹt hoặc dữ liệu biến mất sau khi hết thời gian retry.

Ba nhóm cơ chế cần phân biệt:

- **Retry:** ai quyết định gọi lại, thử bao nhiêu lần, khi nào dừng và trong thời gian nào?
- **Destination:** nơi Lambda gửi **invocation record** khi một lần xử lý bất đồng bộ thành công (`OnSuccess`) hoặc hết khả năng xử lý (`OnFailure`).
- **Dead-letter queue (DLQ):** nơi giữ sự kiện/message không xử lý được để điều tra và redrive. DLQ của **Lambda async invocation** khác DLQ của **Amazon SQS source queue**.

Sau bài này, bạn sẽ có thể:

1. Phân loại **synchronous**, **asynchronous** và **event source mapping**; không áp sai retry policy giữa các nguồn.
2. Giải thích retry mặc định cho Lambda **asynchronous invocation**, `MaximumRetryAttempts` và `MaximumEventAgeInSeconds`.
3. So sánh **Lambda OnSuccess/OnFailure destinations**, **Lambda async DLQ**, **SQS redrive policy** và **stream event source mapping failure destination**.
4. Đọc cấu trúc invocation record, thiết kế quyền IAM/KMS và tránh mất dữ liệu nhạy cảm trong destination.
5. Xử lý **SQS batch failures**, partial batch response, visibility timeout và `maxReceiveCount`.
6. Giải thích hành vi Kinesis/DynamoDB Streams khi xuất hiện **poison-pill record**.
7. Thiết kế handler **idempotent**, retry có giới hạn, backoff, quan sát và quy trình **replay** an toàn.
8. Dùng AWS CLI và CloudWatch để kiểm tra cấu hình; chỉ thử thay đổi/đẩy lỗi trên tài nguyên sandbox đã được phê duyệt.

## 1. Bắt đầu từ câu hỏi: Ai gọi Lambda?

### 1.1. Ba cơ chế invocation khác nhau

| Mô hình | Ví dụ nguồn | Ai đợi kết quả? | Ai chịu trách nhiệm retry chính? |
|---|---|---|---|
| **Synchronous** | API Gateway, ALB, SDK `Invoke(RequestResponse)` | Caller đợi phản hồi | **Caller hoặc dịch vụ gọi** theo chính sách riêng; Lambda không tự retry lỗi hàm theo kiểu async |
| **Asynchronous** | Amazon S3 event notification, SNS, EventBridge target theo chế độ phù hợp, SDK `Invoke(Event)` | Caller nhận xác nhận đã xếp hàng | **Lambda async queue** và retry settings của function/alias/version |
| **Event source mapping (ESM)** | Amazon SQS, Kinesis, DynamoDB Streams, Kafka | Lambda service poll/batch nguồn rồi gọi function | **Cơ chế event source mapping**, source retention/visibility/redrive và cấu hình riêng |

**Sai lầm phổ biến:** nhìn thấy một Lambda nhận sự kiện từ SQS rồi vào mục **Asynchronous invocation** đặt `MaximumRetryAttempts=0`, kỳ vọng SQS message thất bại sẽ vào DLQ ngay. Thực tế SQS trigger chạy qua **event source mapping**; message được retry theo visibility timeout và source queue redrive policy. Tùy source ESM, các giới hạn retry cũng khác.

### 1.2. Sơ đồ chọn cơ chế

~~~mermaid
flowchart TD
    A[Event cần xử lý] --> B{Cơ chế gọi Lambda?}
    B -->|SDK/API synchronous| SY[RequestResponse]
    B -->|Event async| AS[Lambda-managed async event queue]
    B -->|Queue / stream poller| ESM[Event source mapping]
    SY --> C[Caller quyết định retry]
    AS --> D[Retry / max age của async invocation]
    ESM --> E{Nguồn dữ liệu?}
    E -->|SQS| S[SQS visibility timeout + redrive policy]
    E -->|Kinesis / DynamoDB| K[ESM retry/record age/bisect/destination]
    E -->|Kafka| F[ESM offset/commit và lỗi nguồn theo cấu hình]
    D --> OUT[OnSuccess / OnFailure destination hoặc Lambda DLQ]
    S --> SQDLQ[DLQ của SQS source queue]
    K --> KDEST[ESM OnFailure destination khi hỗ trợ]
~~~

Đây là **sơ đồ khái niệm**. Cùng một hệ thống có thể có **hai tầng retry**: ví dụ EventBridge thử giao sự kiện đến target, sau khi Lambda nhận async event thì Lambda lại có hàng đợi/retry riêng. Không lấy tổng số lần gọi lại bằng cách cộng máy móc các giá trị của hai dịch vụ.

### 1.3. Kết quả thành công ở tầng nào?

| Tình huống | Caller nhận gì? | Đã chắc nghiệp vụ thành công? |
|---|---|---|
| `Invoke(Event)` trả **202 Accepted** | Lambda nhận lời gọi async để xếp hàng xử lý | **Chưa**; handler có thể chưa chạy |
| `Invoke(RequestResponse)` trả HTTP 200 từ API Lambda nhưng payload có `FunctionError` | API invocation hoàn thành ở giao thức Lambda | **Không**; function có thể throw/timeout |
| Handler trả `{"statusCode": 500}` **mà không throw** trong async mode | Runtime coi handler đã trả về bình thường | **Không**; business failure có thể bị coi là invocation success |
| SQS batch handler return thành công dù một message hỏng nhưng không báo `batchItemFailures` | Mapping coi batch thành công và xóa messages | **Không**; mất dấu lỗi nghiệp vụ |
| Lambda `OnSuccess` destination nhận record | Handler hoàn thành theo semantics runtime | **Chưa chắc** giao dịch end-to-end đã được commit hoặc downstream đã xử lý |

**Bài học:** cần định nghĩa rõ “thành công” theo **business invariant**, không chỉ HTTP status hoặc Lambda metric `Errors=0`.

## 2. Lambda asynchronous invocation và retry mặc định

### 2.1. Luồng xử lý

Khi một nguồn gửi event theo mô hình **asynchronous**, Lambda đưa event vào **hàng đợi nội bộ do Lambda quản lý** rồi xử lý khi có capacity. Caller thường không chờ handler trả về.

~~~mermaid
sequenceDiagram
    participant P as Event producer
    participant L as Lambda async queue
    participant F as Lambda handler
    participant D as OnFailure destination / DLQ
    P->>L: Invoke asynchronous (Event)
    L-->>P: Accepted (ví dụ 202)
    L->>F: Lần invoke đầu
    F-->>L: Function error
    Note over L: Đợi khoảng 1 phút (mặc định)
    L->>F: Retry #1
    F-->>L: Function error
    Note over L: Đợi khoảng 2 phút (mặc định)
    L->>F: Retry #2
    F-->>L: Function error
    L->>D: Lưu sự kiện/record nếu có cấu hình
~~~

Với **function error** (handler throw, lỗi runtime hoặc timeout), mặc định Lambda thử lại **2 lần** sau lần chạy đầu; theo tài liệu AWS, khoảng chờ thường là **1 phút** rồi **2 phút**. Đây không phải thời gian xử lý cố định nếu hệ thống đang quá tải hoặc event hết hạn.

### 2.2. Function errors khác throttling/system errors

| Loại lỗi | Ví dụ | Hành vi retry async |
|---|---|---|
| **Function error** | Exception trong code, runtime error, timeout | Mặc định tối đa **2 lần retry** ngoài lần chạy đầu; điều chỉnh bằng `MaximumRetryAttempts` |
| **Throttling** | 429 vì thiếu concurrency hoặc quota | Event có thể được đưa lại async queue và retry theo **backoff**, chịu giới hạn tuổi sự kiện |
| **System error** | Lỗi dịch vụ 5xx trong luồng thực thi/invoke | Retry theo cơ chế dịch vụ và event age |
| **Event hết tuổi** | Backlog quá lâu hoặc retry kéo dài | Bị loại khỏi hàng đợi; kích hoạt luồng failed-event nếu đã cấu hình |
| **Event trùng** | Hàng đợi eventual consistency, delivery at least once | Handler phải **idempotent**, kể cả lần xử lý trước đã trả success |

Với throttling/system error, Lambda có thể retry từ khoảng 1 giây tăng dần lên tối đa khoảng **5 phút** theo cơ chế exponential backoff, **tới 6 giờ theo mặc định**. Cấu hình tuổi sự kiện giúp giới hạn khoảng lưu chờ; **MaximumRetryAttempts** chủ yếu giới hạn lỗi từ function, không thể hiểu là “toàn bộ lỗi mọi loại đều chỉ retry đúng 2 lần”.

### 2.3. Hai tùy chọn chính

| Thuộc tính | Phạm vi | Giới hạn theo AWS async invoke config | Ý nghĩa |
|---|---|---|---|
| `MaximumRetryAttempts` | Function errors của async invocation | **0–2** retry attempts | Số lần thử lại sau lần invoke đầu |
| `MaximumEventAgeInSeconds` | Tuổi event trong Lambda async queue | **60–21.600 giây** (tối đa 6 giờ) | Event quá tuổi có thể bị bỏ |
| `DestinationConfig.OnFailure` | Async invocation record | ARN destination được hỗ trợ | Giữ metadata/request/response khi thất bại/hết tuổi |
| `DestinationConfig.OnSuccess` | Async invocation record | ARN destination được hỗ trợ | Gửi record khi handler hoàn thành thành công |
| `DeadLetterConfig.TargetArn` | Async DLQ của function | SQS/SNS **standard** | Giữ nội dung event bị bỏ |

Một cấu hình `MaximumRetryAttempts=0` nghĩa là **không thử lại sau function error**, không có nghĩa Lambda sẽ không thử giao event do throttling/system errors trước khi event hết tuổi.

### 2.4. Ví dụ chọn tuổi và số lần retry

Giả sử hệ thống gửi email xác nhận đăng ký khóa học:

- Event có thông tin `registrationId`.
- Gửi email là thao tác có thể phát sinh side effect.
- Nếu nhà cung cấp email trả lỗi tạm thời, nên có retry/backoff trong phạm vi hợp lý.
- Nếu email không gửi được sau một giới hạn, phải giữ lại để điều tra và replay.

Một lựa chọn **minh họa**:

~~~text
MaximumRetryAttempts = 2
MaximumEventAgeInSeconds = 3600 (1 giờ)
OnFailure = SQS standard queue chứa invocation records
OnSuccess = để trống nếu không có yêu cầu xử lý tiếp theo
~~~

**Không có cấu hình tối ưu chung**. Với thông báo nhạy thời gian, event age cần ngắn hơn; với batch có thể chờ lâu, cần đánh giá backlog, chi phí và nghiệp vụ. Nếu phải bảo toàn công việc quá 6 giờ với queue có retention độc lập, cân nhắc **SQS** làm hàng đợi nguồn và thiết kế retry bằng redrive policy.

## 3. Destination và Lambda async DLQ giống/khác thế nào?

### 3.1. OnSuccess và OnFailure destinations

Đối với asynchronous invocation, Lambda có thể gửi **invocation record** đến destination sau khi xử lý:

- **`OnSuccess`:** handler hoàn thành thành công ở runtime.
- **`OnFailure`:** event hết tuổi hoặc hết các retry attempts và không hoàn thành.

Các đích được hỗ trợ theo tài liệu AWS:

| Destination | OnSuccess? | OnFailure? | Lưu ý |
|---|---|---|---|
| **SQS standard queue** | Có | Có | Giữ record làm message, phù hợp xử lý tuần tự qua consumer |
| **SNS standard topic** | Có | Có | Fan-out, có giới hạn message size |
| **AWS Lambda function** | Có | Có | Gọi function khác; cần tránh vòng lặp retry |
| **Amazon EventBridge bus** | Có | Có | Điều phối theo rules, có cơ chế retry/DLQ ở tầng EventBridge riêng |
| **Amazon S3 bucket** | Không | **Có** | Lưu invocation record JSON trong object; hỗ trợ payload lớn theo giới hạn API |

**SQS FIFO/SNS FIFO không được dùng như async invocation destinations kiểu này.** Những khả năng cho **event source mapping** hoặc các luồng tích hợp khác có thể khác — đừng suy từ một bảng sang mọi nguồn.

### 3.2. Ví dụ invocation record cho OnFailure

Một record mẫu **giản lược** gửi đến SQS OnFailure:

~~~json
{
  "version": "1.0",
  "timestamp": "2026-11-20T02:15:00.000Z",
  "requestContext": {
    "requestId": "request-id-placeholder",
    "functionArn": "arn:aws:lambda:ap-southeast-1:111122223333:function:aws-lab-worker",
    "condition": "RetriesExhausted",
    "approximateInvokeCount": 3
  },
  "requestPayload": {
    "eventId": "registration-123",
    "registrationId": "reg-123",
    "type": "SEND_CONFIRMATION_EMAIL"
  },
  "responseContext": {
    "statusCode": 200,
    "functionError": "Unhandled",
    "executedVersion": "$LATEST"
  },
  "responsePayload": {
    "errorType": "RuntimeError",
    "errorMessage": "Email provider unavailable"
  }
}
~~~

Dữ liệu trên là **JSON minh họa cấu trúc**, không đại diện kết quả chính xác của mọi runtime/version/condition. `requestPayload` chứa event gốc; `responseContext` và `responsePayload` giúp chẩn đoán vì sao handler không thành công.

Đối với OnSuccess, record cũng có ngữ cảnh request/response nhưng không có lỗi theo kiểu trên. Dù vậy, phản hồi ứng dụng có thể chứa dữ liệu nhạy cảm; **đừng bật destinations đến hệ thống không được phép nhận request/response payload**.

### 3.3. Lambda async DLQ

DLQ của function cho async invocations là cấu hình **`DeadLetterConfig.TargetArn`**. Hỗ trợ **SQS standard queue** hoặc **SNS standard topic**. Khác với destination, Lambda async DLQ chủ yếu gửi **event gốc**, kèm message attributes như:

~~~text
RequestID
ErrorCode
ErrorMessage
~~~

Hãy tưởng tượng input:

~~~json
{
  "eventId": "registration-123",
  "type": "SEND_CONFIRMATION_EMAIL"
}
~~~

Khi vào Lambda DLQ, body về cơ bản vẫn là **event input**, không phải invocation record đầy đủ có `requestContext` và `responsePayload` như OnFailure destination.

### 3.4. So sánh trực tiếp

| Tiêu chí | Async OnFailure destination | Lambda async DLQ |
|---|---|---|
| Điều kiện | Không xử lý được sau retry/event age | Không xử lý được sau retry/event age |
| Dữ liệu | **Invocation record**: request + response + context | **Event gốc**, thêm một số message attributes |
| Tài nguyên | SQS, SNS, Lambda, EventBridge, S3 (failure) | SQS standard hoặc SNS standard |
| OnSuccess | **Có** chế độ tương ứng | Không |
| Cấp cấu hình | Function, version hoặc alias theo hỗ trợ | Function-level theo hướng dẫn |
| Mục tiêu | Điều phối tiếp, lưu audit/diagnostic metadata | Bảo toàn input để kiểm tra/replay |
| Metric lỗi gửi | `DestinationDeliveryFailures` | `DeadLetterErrors` |

**Destination có nhiều ngữ cảnh lỗi hơn**, nhưng không tự động an toàn hơn: record lớn, giá/chi phí, quyền IAM, dữ liệu cá nhân và quy trình replay phải được thiết kế.

### 3.5. Lựa chọn theo mục tiêu

- **Cần điều tra vì sao handler lỗi:** ưu tiên **OnFailure destination** để có request/response context.
- **Chỉ cần lưu input và sau đó đưa lại vào pipeline:** có thể dùng **Lambda async DLQ**.
- **Cần fan-out thông báo lỗi cho nhiều hệ thống:** SNS/EventBridge với rules và consumers được bảo vệ.
- **Payload lớn, cần lưu lâu/chi phí storage:** xem xét **S3 OnFailure**, lifecycle và KMS.
- **Cần nghiệp vụ tuần tự/durable work queue:** dùng **SQS source queue** với redrive policy, không dựa vào Lambda async queue như kho dữ liệu công việc vĩnh viễn.

## 4. Cấu hình OnFailure/OnSuccess bằng AWS CLI và IaC

### 4.1. Phân biệt put và update

AWS Lambda cung cấp:

~~~text
put-function-event-invoke-config
    Tạo/thay thế toàn bộ async invoke config ở scope chỉ định.

update-function-event-invoke-config
    Điều chỉnh một phần config mà không chủ ý reset các option khác.
~~~

**Cảnh báo:** `put-function-event-invoke-config` có thể **ghi đè cấu hình hiện hữu**, gồm retry settings và destinations. Vì vậy phải **đọc cấu hình trước** và ưu tiên IaC/change review. Cấu hình có thể đặt ở function, published version hoặc alias; khi dùng qualifier, xác định request thực tế đang invoke phiên bản/alias nào.

### 4.2. Xem cấu hình hiện có (chỉ đọc)

~~~bash
REGION=ap-southeast-1
FUNCTION=aws-lab-worker

aws lambda get-function-event-invoke-config \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --query '{FunctionArn:FunctionArn,Retries:MaximumRetryAttempts,MaxAge:MaximumEventAgeInSeconds,Destinations:DestinationConfig}' \
  --output json
~~~

Nếu chưa có cấu hình riêng, `get-function-event-invoke-config` có thể báo `ResourceNotFoundException`. **Không hiểu lỗi này là function không tồn tại** nếu `get-function`/`list-functions` cho biết function vẫn có; cần kiểm tra scope và cấu hình mặc định.

### 4.3. Ví dụ file cấu hình IaC

CloudFormation minh họa:

~~~yaml
Resources:
  AsyncFailureConfig:
    Type: AWS::Lambda::EventInvokeConfig
    Properties:
      FunctionName: aws-lab-worker
      Qualifier: "$LATEST"
      MaximumRetryAttempts: 2
      MaximumEventAgeInSeconds: 3600
      DestinationConfig:
        OnFailure:
          Destination: arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-failures
~~~

Đây chỉ là một phần template, **không tạo đầy đủ function, queue, policies hoặc encryption key**. Với workload thực, quản lý ARN/roles/permissions bằng IaC và kiểm thử deployment plan. `Qualifier` phải khớp cách trigger/producer gọi function (version/alias hay unqualified).

### 4.4. Ví dụ CLI cập nhật có tác động (không chạy mặc định)

Chỉ khi đã kiểm tra config, destination ARN và quyền trong sandbox:

~~~bash
# CHỈ MINH HỌA; CÓ TÁC ĐỘNG LÊN FUNCTION
aws lambda update-function-event-invoke-config \
  --function-name aws-lab-worker \
  --maximum-retry-attempts 2 \
  --maximum-event-age-in-seconds 3600 \
  --destination-config '{"OnFailure":{"Destination":"arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-failures"}}' \
  --region ap-southeast-1
~~~

Nếu chưa có async event invoke config ở scope, cần dùng lệnh `put-function-event-invoke-config` theo API để tạo config, **nhưng phải xét toàn bộ properties muốn giữ**. Không chép lệnh production khi chưa biết IAM, cost, destination ownership và mức độ ảnh hưởng.

### 4.5. Cấu hình Lambda async DLQ (phương án thay thế)

Ví dụ `DeadLetterConfig` (khác `DestinationConfig`):

~~~json
{
  "DeadLetterConfig": {
    "TargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-dlq"
  }
}
~~~

Lệnh minh họa trên **function sandbox**:

~~~bash
# CÓ TÁC ĐỘNG; không chạy khi chưa review
aws lambda update-function-configuration \
  --function-name aws-lab-worker \
  --dead-letter-config "TargetArn=arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-dlq" \
  --region ap-southeast-1
~~~

Cần chú ý môi trường đã có DLQ hoặc destinations chưa. Ghi lại cấu hình trước khi thay, vì đổi một ARN không xử lý được các event đã gửi vào DLQ trước đó.

## 5. IAM, KMS và tính toàn vẹn của failure destinations

### 5.1. Execution role phải có quyền gửi kết quả

Để Lambda giao record/event tới destination, **function execution role** cần các quyền phù hợp. Ví dụ:

| Đích | IAM action tối thiểu theo tác vụ |
|---|---|
| SQS destination/DLQ | `sqs:SendMessage` |
| SNS destination/DLQ | `sns:Publish` |
| Lambda destination | `lambda:InvokeFunction` |
| EventBridge destination | `events:PutEvents` |
| S3 OnFailure destination | `s3:PutObject` và `s3:ListBucket` theo yêu cầu |
| S3 destination dùng customer-managed KMS key | Có thể cần `kms:GenerateDataKey` và key policy phù hợp |

Đối với cross-account, resource policy của queue/topic/bucket/bus và KMS key policy có thể cần cho phép principal theo bối cảnh. Không cấp wildcard `Resource:"*"` khi bạn có thể chỉ định đúng destination ARN.

### 5.2. Ví dụ least-privilege cho SQS OnFailure

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendOnlyFailureRecords",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-failures"
    }
  ]
}
~~~

Nếu SQS queue dùng **SSE-KMS customer-managed key**, thêm quyền KMS cần thiết và key policy cho principal; nếu cross-account, đánh giá resource-based policy ở queue. IAM Allow không tự vượt explicit Deny, permissions boundary hoặc SCP.

### 5.3. Rủi ro khi S3 destination bị xóa rồi tạo lại tên bucket

Với OnFailure S3 destination, AWS cảnh báo trường hợp bucket bị xóa **nhưng cấu hình destination vẫn trỏ tới tên bucket đó**. Nếu tên bucket bị người khác chiếm lại theo quy tắc namespace, record lỗi có thể được gửi tới bucket không còn do bạn sở hữu.

Biện pháp:

1. Trước khi xóa bucket, **gỡ hoặc cập nhật destination** ở function/alias/version liên quan.
2. Giới hạn `s3:PutObject` bằng policy, ví dụ ràng buộc account chủ sở hữu resource theo condition key thích hợp.
3. Dùng encryption, block public access, lifecycle, versioning và logging theo yêu cầu.
4. Kiểm tra quyền đọc invocation record vì có thể chứa requestPayload/responsePayload nhạy cảm.
5. Không tạo vòng lặp S3 event notification → Lambda failure → cùng S3 bucket nếu chưa thiết kế chống recursion.

### 5.4. Giới hạn payload và lỗi gửi

Bản record của OnFailure thường **lớn hơn event input** do có metadata và response. SNS có giới hạn kích thước message (ví dụ **256 KiB**); record quá lớn hoặc không đáp ứng định dạng đích có thể dẫn đến **DestinationDeliveryFailures**. Lambda DLQ cũng có thể báo **DeadLetterErrors** vì message attributes/size hoặc quyền.

Nếu thấy `AsyncEventsDropped` tăng nhưng DLQ/destination trống:

- Kiểm tra ARN, Region, loại destination và resource có tồn tại.
- Kiểm tra execution role, resource policy và KMS permissions.
- Kiểm tra payload size, quota hoặc limit của destination.
- Xem metrics `DestinationDeliveryFailures`/`DeadLetterErrors`.
- Đánh giá có sự kiện bị mất vĩnh viễn nếu không có nguồn replay bền vững khác.

**Giám sát đường gửi thất bại phải là yêu cầu bắt buộc**, không chỉ giám sát handler `Errors`.

## 6. SQS → Lambda: retry và DLQ thuộc source queue

### 6.1. Lambda poll SQS như thế nào?

Khi tích hợp SQS, Lambda dùng **event source mapping** để poll messages và gọi handler **đồng bộ theo batch**. SQS giữ messages trong hàng đợi, tạm **ẩn** chúng trong `VisibilityTimeout`. Nếu handler trả thành công, Lambda xóa messages của batch theo cơ chế dịch vụ. Nếu thất bại, messages trở lại trạng thái có thể nhận sau visibility timeout để thử lại.

~~~mermaid
sequenceDiagram
    participant Q as SQS source queue
    participant E as Lambda event source mapping
    participant F as Lambda handler
    participant D as SQS dead-letter queue
    E->>Q: ReceiveMessage batch
    Q-->>E: Messages tạm invisible
    E->>F: Invoke batch
    F-->>E: Error / failed items
    Note over Q: Visibility timeout kết thúc
    Q-->>E: Messages thất bại có thể nhận lại
    Note over Q: Receive count đạt ngưỡng redrive
    Q->>D: Redrive failed message theo policy
~~~

**Lambda async event invoke config** không kiểm soát flow này. Đối với SQS, bạn cấu hình:

- **Visibility timeout**;
- **Redrive policy** trên source queue, gồm DLQ ARN và `maxReceiveCount`;
- Batch size/batching window;
- `ReportBatchItemFailures` khi muốn partial batch responses;
- Concurrency và idempotency.

### 6.2. Ví dụ redrive policy của SQS source queue

JSON **minh họa** của thuộc tính `RedrivePolicy` trên queue nguồn:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:aws-lab-orders-dlq",
  "maxReceiveCount": "5"
}
~~~

Sau khi một message được nhận nhiều lần đến ngưỡng `maxReceiveCount` theo cơ chế SQS, service có thể chuyển message sang DLQ. Với SQS source, AWS khuyến nghị cân nhắc `maxReceiveCount` **ít nhất 5** để có đủ cơ hội thử lại trong trường hợp transient.

**Loại queue phải tương thích:** source FIFO dùng DLQ FIFO; source standard dùng DLQ standard theo quy tắc SQS. Đừng áp nhầm giới hạn **Lambda async DLQ chỉ hỗ trợ standard** cho **SQS source queue DLQ**.

### 6.3. Visibility timeout phải đủ dài

Theo hướng dẫn AWS cho SQS event source mapping:

- Function timeout **không được lớn hơn** SQS visibility timeout.
- AWS khuyến nghị đặt visibility timeout **ít nhất khoảng 6 lần** function timeout để có biên retry khi throttled.
- Nếu sử dụng batching window, cộng thêm batching window vào ước lượng theo tài liệu tương ứng.
- Visibility quá ngắn có thể khiến message lại được nhận trước khi lần xử lý trước hoàn thành, tăng duplicate processing.
- Visibility quá dài khiến retry sau lỗi chậm, tăng độ trễ DLQ.

Ví dụ:

~~~text
Lambda timeout = 20 giây
SQS visibility timeout mục tiêu ban đầu >= 120 giây
  (cộng batching window nếu có theo hướng dẫn)
maxReceiveCount = 5
~~~

Đây là **điểm khởi đầu**, không thay thế benchmark và tính toán SLO. Nếu workload có thời gian xử lý biến động lớn, xem xét idempotency, heartbeat/visibility extension và tách công việc dài.

### 6.4. Batch failure mặc định

SQS batch chứa 5 messages:

~~~text
m1: xử lý thành công
m2: xử lý thành công
m3: lỗi dữ liệu
m4: chưa xử lý
m5: chưa xử lý
~~~

Nếu handler ném exception trong batch mà **không bật partial batch response**, toàn batch có thể trở lại queue khi visibility timeout hết. Điều đó khiến **m1 và m2 bị xử lý lại** dù chúng đã có side effects. Đây là lý do SQS workflows cần **idempotency** và cân nhắc partial batch response.

### 6.5. Partial batch response

Khi event source mapping được cấu hình `FunctionResponseTypes=["ReportBatchItemFailures"]`, handler có thể trả danh sách **message IDs thất bại**:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "message-id-3"
    }
  ]
}
~~~

Khi xử lý hợp lệ, Lambda chỉ để những messages báo thất bại trở lại queue, còn successful messages được xóa. Nếu handler **throw uncaught exception** thay vì trả cấu trúc này, cả batch có thể bị coi là thất bại.

**Ví dụ Python handler có bắt lỗi từng message:**

~~~python
import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def process_order(order):
    # Thay bằng nghiệp vụ đã thiết kế idempotency.
    if not order.get("orderId"):
        raise ValueError("Missing orderId")
    # business processing here

def lambda_handler(event, context):
    failed = []

    for record in event.get("Records", []):
        message_id = record["messageId"]

        try:
            payload = json.loads(record["body"])
            process_order(payload)
        except Exception:
            # Không in body/credentials/PII.
            logger.exception("Failed to process message id=%s", message_id)
            failed.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failed}
~~~

Để cơ chế trả về có hiệu lực, cấu hình ESM phải bật `ReportBatchItemFailures`. **Không dùng đoạn code này trực tiếp với xử lý thanh toán thật**: hàm `process_order` cần đảm bảo idempotency, transaction và loại lỗi phải phân biệt rõ.

**SQS FIFO lưu ý:** để giữ thứ tự group, khi gặp lỗi nên **ngừng xử lý những records tiếp theo** và trả về cả message lỗi lẫn những message chưa xử lý theo hướng dẫn AWS. Không dùng cách “cứ tiếp tục xử lý m4/m5” của standard queue nếu việc đó phá thứ tự nghiệp vụ của FIFO.

### 6.6. Retry loops và poison-pill messages

Một record chứa schema sai vĩnh viễn sẽ thất bại lặp lại — gọi là **poison pill**. Nếu không có DLQ và limit hợp lý, hệ thống có thể:

- Tăng chi phí Lambda invoke và số SQS receives;
- Làm backlog/age tăng;
- Chặn hoặc làm chậm messages hợp lệ;
- Khiến batch lặp lại nhiều lần nếu không có partial response.

Hướng khắc phục:

1. Validate schema và phân loại lỗi transient/permanent.
2. Dùng partial batch response khi phù hợp.
3. Đặt maxReceiveCount hợp lý và DLQ retention.
4. Cảnh báo DLQ backlog.
5. Có runbook inspect/repair/replay bằng quyền hạn chế.

## 7. Kinesis/DynamoDB Streams: retry thuộc event source mapping

### 7.1. Cơ chế khác SQS

Kinesis và DynamoDB Streams lưu **sequence of records** trong shard/stream; Lambda event source mapping poll, batch và checkpoint. Nếu handler lỗi, retry có thể **chặn tiến độ xử lý shard** cho đến khi records xử lý thành công, quá tuổi, hết retry hoặc hết retention của nguồn.

~~~mermaid
flowchart TD
    ST[Stream shard] --> B[Event source mapping reads batch]
    B --> F[Lambda handler]
    F -->|Success| CP[Commit/checkpoint progress]
    F -->|Function error| R{Retry policy / record age}
    R -->|Còn điều kiện thử| F
    R -->|Hết giới hạn| D[Discard + OnFailure destination nếu có]
    D --> CP
~~~

Các thông số ESM thường gặp:

| Option | Ý nghĩa |
|---|---|
| `MaximumRetryAttempts` | Giới hạn retries cho failed stream records/batches theo cơ chế ESM |
| `MaximumRecordAgeInSeconds` | Giới hạn tuổi record ở luồng ESM |
| `BisectBatchOnFunctionError` | Chia batch lỗi để cô lập record gây hỏng |
| `FunctionResponseTypes=ReportBatchItemFailures` | Báo thất bại theo record được hỗ trợ |
| `DestinationConfig.OnFailure` | Lưu thông tin failed records/batch khi bị bỏ |
| `ParallelizationFactor` | Mức song song đọc các shard theo hỗ trợ và bảo toàn thứ tự keys phù hợp |

Đừng nhầm `MaximumRecordAgeInSeconds` của ESM với `MaximumEventAgeInSeconds` của **Lambda async event queue**: cùng mang ý tưởng hạn tuổi, nhưng áp dụng cho **đường xử lý khác nhau**.

### 7.2. Mặc định stream retries có thể rất dài

Một số stream mappings mặc định có `MaximumRetryAttempts=-1` và `MaximumRecordAgeInSeconds=-1` (ý nghĩa không giới hạn bởi option mapping), nhưng **record vẫn chịu data retention của stream**. Trong thực tế một poison-pill record có thể chặn shard đến khi dữ liệu hết hạn; phải có kế hoạch timeout, alarm IteratorAge và failure destination.

**Tùy nguồn**, failed stream record destination có thể là SQS, SNS, S3 hoặc đích được API hỗ trợ. Với destination **SQS/SNS**, thông điệp failed batch có thể chủ yếu chứa metadata; với **S3 destination** AWS hỗ trợ lưu cả payload record để replay dễ hơn. Kiểm tra tài liệu theo nguồn Kinesis/DynamoDB/Kafka cụ thể.

### 7.3. BisectBatchOnFunctionError

Giả sử batch gồm 8 records và có 1 poison pill. Khi bật `BisectBatchOnFunctionError`, Lambda có thể chia batch lỗi thành hai, rồi tiếp tục chia để cô lập record:

~~~text
[1 2 3 4 5 6 7 8] -> failure
[1 2 3 4]          -> success
[5 6 7 8]          -> failure
[5 6]              -> success
[7 8]              -> failure
[7]                -> failure
[8]                -> success
~~~

Ví dụ mang tính khái niệm; behavior thực tế phụ thuộc source, config và handler. Việc chia batch **không nên được hiểu là tự sửa poison pill**. Cần kết hợp tuổi record, retries, OnFailure destination, logs và replay plan.

## 8. Retry không thể thay thế idempotency

### 8.1. Tại sao “at least once” gây lặp side effects?

Một sự kiện `order-123` có thể:

1. Lambda gọi payment API, thanh toán thành công.
2. Trước khi handler trả về, Lambda timeout do network hoặc runtime.
3. Cơ chế nguồn/Lambda coi lần xử lý chưa thành công nên retry.
4. Handler lại gọi payment API, dẫn đến **hai lần charge** nếu không có idempotency.

~~~mermaid
sequenceDiagram
    participant SRC as Event source
    participant L as Lambda
    participant PAY as Payment API
    SRC->>L: order-123
    L->>PAY: Charge 100 USD
    PAY-->>L: Success
    Note over L: Timeout trước khi trả kết quả
    SRC->>L: Retry order-123
    L->>PAY: Charge 100 USD lần nữa?
    Note over L,PAY: Phải dùng idempotency key
~~~

**Cốt lõi:** không có cách chỉ đặt `MaximumRetryAttempts=0` là đảm bảo xử lý đúng một lần, vì duplicate delivery có thể xảy ra ngoài retry logic của handler.

### 8.2. Xây dựng idempotency key

Các lựa chọn:

| Event | Khóa idempotency khả thi | Lưu ý |
|---|---|---|
| Đơn hàng | `orderId` hoặc `paymentIntentId` | Phải ổn định qua mọi retries |
| Upload S3 | Bucket + object key + version ID/ETag theo nghiệp vụ | Không chỉ dùng key nếu file có thể ghi đè |
| SQS message | Business event ID trong body | MessageId có thể thay khi republish |
| EventBridge event | Event ID **hoặc** business operation ID | EventBridge event ID không thay thế định danh nghiệp vụ nếu producer tạo duplicate events |
| Báo cáo hằng ngày | Tenant + report date + report type | Xác định policy khi người dùng yêu cầu tạo lại |

**Không dùng Lambda `awsRequestId` làm idempotency key duy nhất**, vì mỗi lần invocation có thể có request ID mới. Dùng **business operation ID** do producer cấp.

### 8.3. Mẫu idempotent consumer

~~~text
Input event {eventId, operationId, payload}
  |
  v
Validate schema + authorization/business rules
  |
  v
Atomic claim cho operationId (DynamoDB conditional write hoặc DB transaction)
  |
  +-- COMPLETED trước đó --> return success, không lặp side effect
  |
  +-- IN_PROGRESS hợp lệ --> xử lý concurrency/lease theo thiết kế
  |
  +-- Claim thành công --> gọi downstream với same idempotency key
                           |
                           +-- Thành công --> mark COMPLETED atomically
                           +-- Lỗi tạm thời --> release/expire lease theo policy
                           +-- Lỗi vĩnh viễn --> failure record / DLQ
~~~

Các trạng thái `IN_PROGRESS`/`COMPLETED` và lease timeout giúp xử lý các trường hợp Lambda bị terminate giữa chừng. Tuy nhiên, **claim trước side effect** có thể gây mất công việc nếu không có recovery; **mark completed sau side effect** cũng có cửa sổ duplicate nếu downstream không hỗ trợ idempotency.

Giải pháp mạnh hơn thường kết hợp:

- **Idempotency key ở downstream** (ví dụ payment provider nhận cùng key);
- **Transactional outbox/inbox** khi cần gắn database commit với phát event;
- State machine/Step Functions cho workflow nhiều bước cần bù trừ;
- Conditional writes và transaction trong DynamoDB/RDS theo yêu cầu.

### 8.4. Retry với exponential backoff và jitter

Bên trong handler, với các call đến downstream API, có thể dùng retry có giới hạn cho lỗi transient:

~~~text
attempt 1: ngay
attempt 2: ~ 200 ms + jitter
attempt 3: ~ 400 ms + jitter
attempt 4: ~ 800 ms + jitter
dừng khi vượt timeout budget hoặc max attempts
~~~

**Không retry vô hạn bên trong Lambda**; vừa tiêu thụ execution duration, vừa có thể kéo dài timeout rồi khiến invocation bị retry thêm ở tầng Lambda/ESM. Tính tổng retry budget từ **caller → Lambda → downstream SDK → database/API** để tránh bão retry.

## 9. Observability: metrics và alerts không được bỏ qua

### 9.1. Metrics quan trọng

| Chỉ số / namespace | Ý nghĩa | Hành động nếu bất thường |
|---|---|---|
| `AWS/Lambda Invocations` | Lượng invocations được tính theo metric | So traffic và chi phí |
| `AWS/Lambda Errors` | Lỗi của function/runtime | Đọc logs, phân nhóm permanent/transient |
| `AWS/Lambda Throttles` | Thiếu concurrency/limit | Xem reserved/account concurrency và downstream scaling |
| `AWS/Lambda Duration` | Thời gian xử lý | So timeout, downstream slowness |
| `AWS/Lambda ConcurrentExecutions` | Số executions đồng thời | Capacity, throttling, cost |
| `AsyncEventsReceived` | Events vào async queue của Lambda | Theo dõi đột biến |
| `AsyncEventAge` | Tuổi event lúc được invoke | Cảnh báo backlog/latency, nguy cơ hết age |
| `AsyncEventsDropped` | Events bị loại sau failure/age/điều kiện khác | Rà soát risk và DLQ/destination |
| `DestinationDeliveryFailures` | Lambda không gửi được invocation record | IAM/KMS/size/destination type |
| `DeadLetterErrors` | Lambda gửi async DLQ thất bại | IAM/resource policy/size |
| `SQS ApproximateNumberOfMessagesVisible` | DLQ/source backlog gần đúng | Có poison-pill hay consumer stopped? |
| `SQS ApproximateAgeOfOldestMessage` | Thời gian chờ của message cũ nhất | Mục tiêu xử lý/replay có bị trễ? |
| `IteratorAge` của stream ESM | Độ trễ trong xử lý shard | Có poison pill hoặc throughput/capacity issue? |

Metric có **dimensions, statistic, granularity và khả năng xuất bản** tùy chế độ/source. Không lấy riêng `Errors=0` làm bằng chứng không mất sự kiện: event có thể hết tuổi, bị drop trước khi handler chạy, hoặc destination bị lỗi giao.

### 9.2. Ví dụ SLO và cảnh báo

Với nghiệp vụ gửi email sau đăng ký:

~~~text
SLO:
  99,9% registration events có kết quả xử lý cuối cùng
  trong vòng 10 phút.
  100% failed events có record trong nguồn lưu bền vững để điều tra.

Alerts tham khảo:
  AsyncEventAge p95 hoặc max vượt ngưỡng dự kiến
  AsyncEventsDropped > 0
  DestinationDeliveryFailures > 0
  SQS DLQ Visible messages > 0
  SQS DLQ oldest message age tăng liên tục
  Lambda Errors/Throttles tăng so baseline
~~~

**SLO dùng trong ví dụ**, không phải cam kết SLA của AWS. Với hệ thống thật, lựa chọn mức ngưỡng, thời gian xác nhận, owner trực sự cố và runbook liên quan.

### 9.3. Không chỉ bật alarm cho Lambda Errors

Một event có thể bị mất dù function chưa chạy nếu async backlog quá tuổi. Trường hợp khác: function đã lỗi nhưng record không tới SQS destination vì execution role thiếu `sqs:SendMessage`. Vì vậy cần quan sát cả:

1. **Source enqueue:** nhà sản xuất có thành công gửi event không?
2. **Lambda queue/ESM backlog:** event có đang chờ quá lâu?
3. **Handler:** lỗi, timeout, throttling, resource usage.
4. **Failure sink:** destination/DLQ có nhận và lưu đủ records không?
5. **Replay:** số records đang chờ điều tra và số records đã xử lý lại thành công.

## 10. Thực hành 1 — Kiểm tra Lambda async config (chỉ đọc)

> **Điều kiện:** AWS CLI v2 và danh tính IAM được cấp quyền xem Lambda/SQS/CloudWatch trong **sandbox**. Không tạo function, queue, trigger hay gửi event. Ví dụ Bash sử dụng Region `ap-southeast-1`. Tất cả tên/ARN trong bài là placeholder.

### Bước 1 — Xác nhận account, profile và Region

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

Nếu dùng AWS CloudShell với credentials đã được quản lý qua phiên Console, bỏ `AWS_PROFILE` và các `--profile` nếu không có profile trên máy. **Kiểm tra Account/Arn trước** để tránh thao tác nhầm môi trường.

### Bước 2 — Đọc function configuration

~~~bash
REGION=ap-southeast-1
FUNCTION=aws-lab-worker

aws lambda get-function-configuration \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --query '{Name:FunctionName,Runtime:Runtime,Timeout:Timeout,Memory:MemorySize,State:State,DeadLetterConfig:DeadLetterConfig}' \
  --output json
~~~

Chỉ trích các trường cần thiết; **không dùng output toàn bộ Environment.Variables**, vì có thể chứa thông tin nhạy cảm.

**Phân tích:** Nếu `DeadLetterConfig` rỗng, đừng kết luận function không có **OnFailure destination**; đó là cấu hình khác, đọc bằng `get-function-event-invoke-config`.

### Bước 3 — Đọc async invoke config

~~~bash
aws lambda get-function-event-invoke-config \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --query '{MaxRetry:MaximumRetryAttempts,MaxAgeSeconds:MaximumEventAgeInSeconds,Destinations:DestinationConfig}' \
  --output json
~~~

Nếu application dùng **alias `prod`**:

~~~bash
aws lambda get-function-event-invoke-config \
  --function-name "$FUNCTION" \
  --qualifier prod \
  --region "$REGION" \
  --output json
~~~

Đối chiếu đúng qualifier mà producer đang gọi. Một function có config ở alias có thể khác `$LATEST`. Không thay cấu hình function khác chỉ vì bạn thấy giá trị “không giống mặc định”.

### Bước 4 — Liệt kê event source mappings

~~~bash
aws lambda list-event-source-mappings \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --query 'EventSourceMappings[].{UUID:UUID,Source:EventSourceArn,State:State,BatchSize:BatchSize,PartialResponses:FunctionResponseTypes,Retries:MaximumRetryAttempts,RecordAge:MaximumRecordAgeInSeconds,Destination:DestinationConfig}' \
  --output json
~~~

Nếu có mapping SQS, Kinesis hoặc DynamoDB Streams, hãy **phân tích theo source type**. `MaximumRetryAttempts` của ESM không phải thuộc tính bạn vừa xem ở async invocation config; một số trường có thể trống vì nguồn đó không hỗ trợ.

### Bước 5 — Đọc SQS source queue redrive policy

Với queue URL sandbox thực:

~~~bash
QUEUE_URL=https://sqs.ap-southeast-1.amazonaws.com/111122223333/aws-lab-orders

aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names QueueArn VisibilityTimeout RedrivePolicy \
  --region "$REGION" \
  --output json
~~~

Kiểm tra `VisibilityTimeout` và JSON `RedrivePolicy`. **Không gọi `receive-message` trên queue production để “xem thử”**, vì thao tác nhận có thể làm message tạm invisible, ảnh hưởng consumer và expose payload. Với quyền chỉ đọc, chỉ lấy attributes/metrics.

### Bước 6 — Xem concurrency settings

~~~bash
aws lambda get-function-concurrency \
  --function-name "$FUNCTION" \
  --region "$REGION" \
  --output json
~~~

Nếu `ReservedConcurrentExecutions=0`, function có thể bị chặn invoke và ảnh hưởng event handling; kiểm tra backlog/drop và thiết kế failure sink. Nếu API báo không có reserved concurrency, **không kết luận function đang có 0 concurrency**; đó thường là chưa đặt giới hạn riêng.

## 11. Thực hành 2 — CloudWatch và kiểm tra destination (chỉ đọc)

### Bước 1 — Liệt kê metrics async

~~~bash
aws cloudwatch list-metrics \
  --namespace AWS/Lambda \
  --metric-name AsyncEventsDropped \
  --dimensions "Name=FunctionName,Value=$FUNCTION" \
  --region "$REGION" \
  --output table
~~~

Metric không có datapoint trong phạm vi hiển thị có thể không xuất hiện; không suy ra “chưa bao giờ có lỗi” từ kết quả rỗng. Với CloudWatch, dùng dimensions đúng function/qualifier nếu bạn đang phân tích riêng alias.

### Bước 2 — Lấy tổng events bị drop trong 30 phút

Ví dụ Bash trong AWS CloudShell (GNU date):

~~~bash
START_UTC=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name AsyncEventsDropped \
  --dimensions "Name=FunctionName,Value=$FUNCTION" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --period 300 \
  --statistics Sum \
  --region "$REGION" \
  --output json
~~~

**Diễn giải:** `Sum` trên mỗi khoảng 300 giây là tổng số events theo metric, không phải phần trăm lỗi. Nếu có drop, cần kiểm tra vì sao và đường recovery. Có thể lặp lại với `AsyncEventsReceived`, `DeadLetterErrors` và `DestinationDeliveryFailures`.

### Bước 3 — Xem DLQ backlog mà không đọc nội dung

~~~bash
DLQ_URL=https://sqs.ap-southeast-1.amazonaws.com/111122223333/aws-lab-failures

aws sqs get-queue-attributes \
  --queue-url "$DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesDelayed ApproximateNumberOfMessagesNotVisible \
  --region "$REGION" \
  --output json
~~~

Các giá trị SQS là **ước lượng gần đúng**, có độ trễ cập nhật. Nếu cần tuổi message cũ nhất, dùng CloudWatch `AWS/SQS ApproximateAgeOfOldestMessage` theo đúng QueueName. **Không dump DLQ messages** vì có thể chứa request/response, access tokens hoặc dữ liệu cá nhân.

### Bước 4 — Bảng ghi nhận

| Kiểm tra | Kết quả quan sát | Kết luận cần xác minh |
|---|---|---|
| Function InvocationType của producer | Đồng bộ / async / ESM | Chọn đúng lớp retry |
| Async `MaximumRetryAttempts` | ... | Function error có thể retry bao nhiêu lần? |
| Async `MaximumEventAgeInSeconds` | ... | Event có thể bị drop khi backlog đến đâu? |
| `DestinationConfig.OnFailure` | ... | Có giữ invocation record không? |
| `DeadLetterConfig.TargetArn` | ... | Có giữ event gốc cho async không? |
| SQS `RedrivePolicy` | ... | Source queue DLQ và maxReceiveCount |
| SQS `VisibilityTimeout` | ... | Retry delay và duplicate risk |
| `DestinationDeliveryFailures` / `DeadLetterErrors` | ... | Failure sink có được phép gửi không? |
| DLQ backlog | ... | Có records cần điều tra và replay không? |

## 12. Thực hành 3 — Phát sinh lỗi có kiểm soát trên sandbox (tùy chọn)

> **Có tác động thật.** Chỉ làm nếu bạn đã có function/queue sandbox riêng, được phép invoke/update, đã đặt budget và có người chịu trách nhiệm dọn. Phần này không bắt buộc để hoàn thành bài, và không nên dùng function gửi thanh toán/email thật.

### 12.1. Chuẩn bị lab

- Function `aws-lab-retry-demo` không có quyền làm thay đổi dữ liệu thật.
- Một **SQS standard queue** riêng, ví dụ `aws-lab-lambda-failures`, đã gắn thành OnFailure destination và có execution role `sqs:SendMessage`.
- Lambda timeout nhỏ và handler trả lỗi **có chủ đích** khi `simulateFailure=true`.
- `MaximumRetryAttempts` và max event age được cấu hình theo kế hoạch, tránh chạy lỗi quá lâu.
- CloudWatch logs/metrics và queue alarms.
- Không đưa PII, credential hay thông tin production vào event test.

Ví dụ handler Python đơn giản:

~~~python
import json

def lambda_handler(event, context):
    if event.get("simulateFailure") is True:
        raise RuntimeError("Expected training failure")

    return {
        "processed": True,
        "eventId": event.get("eventId")
    }
~~~

Code này chỉ mô tả cách tạo lỗi. **Không triển khai ngoài sandbox và không dùng `raise` có chủ đích trong business handler thật.**

### 12.2. Gửi một event async mẫu

File local `training-event.json` chỉ chứa dữ liệu giả:

~~~json
{
  "eventId": "training-001",
  "simulateFailure": true,
  "source": "lambda-retry-lab"
}
~~~

Lệnh minh họa cho AWS CLI v2:

~~~bash
# CHỈ CHẠY trên function sandbox đã được duyệt
aws lambda invoke \
  --function-name aws-lab-retry-demo \
  --invocation-type Event \
  --payload fileb://training-event.json \
  --region ap-southeast-1 \
  invoke-response.json
~~~

Một phản hồi `StatusCode=202` chỉ xác nhận async event đã được nhận để xử lý; **không phải handler đã thành công**. Trường `invoke-response.json` ở máy local không chứa toàn bộ invocation result async như sync mode.

### 12.3. Quan sát và kiểm tra

1. Xem function logs **không chứa dữ liệu nhạy cảm**.
2. Theo dõi số lần invoke/Errors và thời gian giữa các lần retry.
3. Kiểm tra `AsyncEventAge` và `AsyncEventsDropped` nếu có.
4. Xác nhận OnFailure destination nhận đúng **một record phù hợp** về mặt nghiệp vụ — nhưng đừng giả định exactly-once; handler/transport có thể trùng event.
5. Kiểm tra `requestContext.condition` và `approximateInvokeCount` qua giao diện an toàn, chỉ trong quyền được cấp.
6. Kiểm tra `DestinationDeliveryFailures=0` và DLQ backlog được xử lý theo runbook.

### 12.4. Khôi phục và dọn

- Ghi lại cấu hình trước khi thử, khôi phục retry/destination settings chỉ trên **function sandbox** và theo quy trình change review.
- Xử lý test record trong queue theo quy trình được duyệt; không xóa nhầm messages thật.
- Nếu queue hoặc function được tạo riêng cho lab, dọn chúng theo **thứ tự phụ thuộc** (gỡ destination/mapping trước, rồi dọn tài nguyên được sở hữu).
- Kiểm tra CloudWatch logs retention, SQS queue, Lambda function và chi phí trong Region.
- **Không xóa shared S3/SQS DLQ** đang phục vụ hệ thống khác.

## 13. Redrive và replay: cứu sự kiện nhưng không tạo side effect lặp

### 13.1. Redrive không phải nút “chạy lại tất cả”

Một DLQ chứa messages thất bại vì **nhiều lý do khác nhau**:

- Dữ liệu input thiếu trường;
- Downstream outage;
- IAM/KMS permission bị từ chối;
- Throttling quá lâu;
- Bug ứng dụng;
- Sự kiện lỗi thời, không còn ý nghĩa nghiệp vụ.

Nếu redrive toàn bộ mà không sửa nguyên nhân, messages có thể tiếp tục thất bại và quay lại DLQ hoặc gây side effects trùng.

### 13.2. Quy trình replay an toàn

~~~mermaid
flowchart TD
    A[DLQ / failure destination records] --> B[Phân loại lỗi]
    B --> C{Transient hay permanent?}
    C -->|Transient| D[Kiểm tra downstream hồi phục]
    C -->|Permanent| E[Sửa schema/đối soát dữ liệu]
    D --> F[Kiểm tra event age và business validity]
    E --> F
    F --> G[Idempotency key + dedup state]
    G --> H[Replay có kiểm soát / hạn tốc]
    H --> I[Quan sát success, errors và side effects]
    I --> J{Kết quả đạt?}
    J -->|Có| K[Audit / mark resolved]
    J -->|Không| B
~~~

Quy trình gợi ý:

1. Tách rõ **Lambda async DLQ body** (event gốc) và **OnFailure destination body** (invocation record). Nếu replay OnFailure, chỉ tái sử dụng phần `requestPayload` sau khi xác thực/validate.
2. So business operation ID với dữ liệu hiện tại; nếu đã hoàn tất, **không gửi lại side effect**.
3. Chuẩn hóa schema/phiên bản event và loại bỏ dữ liệu không còn hợp lệ.
4. Giới hạn tốc độ, dùng queue staging/quarantine nếu cần.
5. Theo dõi metrics, số event thành công, số mới vào DLQ và audit.
6. Có rollback/cancel plan cho replay khi phát sinh sự cố.

### 13.3. SQS DLQ redrive tự động và thao tác thủ công

SQS hỗ trợ các khả năng **dead-letter queue redrive** khi được cấp quyền và source/destination phù hợp. Tuy nhiên:

- Redrive có thể đưa message trở lại source queue hoặc queue được phép theo tính năng AWS; phải kiểm tra ARN, loại queue và permissions.
- Không tự động khôi phục những transaction downstream đã bị lỗi hay bị commit một phần.
- Messages phải còn trong retention window.
- Với FIFO, thứ tự và deduplication cần được đánh giá riêng.
- Không redrive cross-account/dữ liệu khách hàng khi thiếu phê duyệt.

**Không đưa lệnh `start-message-move-task` vào lab bắt buộc**, vì thao tác đó có thể gửi hàng loạt messages thật trở lại xử lý. Trong production chỉ thực thi khi có runbook/approval/giám sát và cách dừng khẩn cấp.

### 13.4. Khi nào cần Step Functions thay vì retry đơn giản?

Nếu workflow gồm nhiều bước phụ thuộc:

~~~text
Charge payment -> Reserve inventory -> Send email -> Update CRM
~~~

và mỗi bước có retry/compensation riêng, **AWS Step Functions** có thể phù hợp hơn Lambda async retry duy nhất. Step Functions hỗ trợ state machine, retries, catches và quản lý trạng thái từng bước theo cấu hình; tuy nhiên cũng cần idempotency và thiết kế bù trừ.

**Không dùng Lambda runtime sleep nhiều phút** chỉ để chờ một bước khác; điều này có thể tăng phí và chiếm concurrency không cần thiết.

## 14. Tính sẵn sàng và chi phí khi thiết kế retry

### 14.1. Concurrency ảnh hưởng backlog

Ví dụ hệ thống nhận 1.000 events/phút, mỗi event cần trung bình 2 giây xử lý. Năng lực xử lý lý thuyết cần khoảng:

~~~text
1000 events / 60 giây * 2 giây
≈ 33,3 concurrent executions
~~~

Nếu reserved concurrency chỉ là 10 và traffic giữ nguyên, backlog có thể tăng. Nếu tăng retries khi downstream đang lỗi, nhu cầu concurrency thực tế còn lớn hơn, làm chi phí tăng và có thể khiến nhiều events hết tuổi.

Số liệu trên **lý thuyết**; cold starts, runtime variability, reserved/account concurrency, traffic bursts, event source scaling và throttling sẽ thay đổi khả năng xử lý thật.

### 14.2. Chi phí trực tiếp/gián tiếp

| Thành phần | Có thể phát sinh phí | Cách kiểm soát |
|---|---|---|
| Lambda invokes | Mỗi attempt khi function chạy, request/duration/memory | Sửa lỗi gốc, giảm retry vô ích, tối ưu handler |
| Lambda async backlog | Hậu quả latency/age, có thể dẫn đến mất event | Concurrency hợp lý, alarms |
| SQS source/DLQ | Requests, payload/storage theo biểu giá | Retention, batch, redrive có kiểm soát |
| SNS/EventBridge | Publishing/delivery/rules theo dịch vụ | Tránh loops và fan-out không cần thiết |
| S3 OnFailure | Objects, PUT requests, storage, lifecycle, KMS | Retention, encryption và bucket governance |
| CloudWatch | Logs ingestion/retention, metrics, alarms | Redaction và lưu giữ có mục tiêu |
| Downstream | DB/API calls, third-party transactions | Idempotency và backoff, không retry vĩnh viễn |

**Đánh đổi:** một lần retry ít đi có thể giảm chi phí nhưng khiến nhiều sự kiện vào DLQ hơn. Retry quá nhiều có thể kéo dài khôi phục và tăng chi phí. Chọn theo **RTO/SLO, tính hợp lệ dữ liệu và khả năng xử lý lại**, không theo “càng nhiều retries càng an toàn”.

### 14.3. Failure isolation

- Đặt **reserved concurrency** phù hợp để Lambda không làm quá tải downstream; nhưng nếu đặt quá thấp, async event age tăng và có thể drop.
- Chia các nhóm công việc có SLO khác nhau thành **queue/function riêng**.
- Dùng **DLQ/quarantine** cho poison-pill events thay vì để một message chặn mọi processing.
- Cân nhắc **Circuit breaker** hoặc tạm giảm throughput khi downstream outage, với nguồn lưu bền vững và runbook khôi phục.
- Khi nguồn là SQS, dùng visibility/redrive/partial batch, không cấu hình Lambda async retries sai lớp.

## 15. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| `Invoke(Event)` trả 202 nhưng không có email | 202 chỉ xác nhận enqueue; handler hoặc downstream lỗi | Async metrics, logs, destination/DLQ |
| Hàm throw nhưng handler vẫn chạy 3 lần | Async function error mặc định 2 retries | `get-function-event-invoke-config`, logic idempotency |
| Đặt retry 0 nhưng vẫn thấy event được gọi lại | Throttling/system errors hoặc duplicate async delivery, hay nguồn ESM | Phân loại invocation type và nguyên nhân |
| `OnSuccess` được gọi dù app trả `statusCode:500` | Handler return bình thường, không throw | Định nghĩa business success, xử lý error đúng |
| `AsyncEventsDropped` tăng, queue OnFailure trống | Destination delivery thất bại hoặc config/qualifier sai | `DestinationDeliveryFailures`, ARN/IAM/KMS |
| `DeadLetterErrors` tăng | Lambda không gửi được async DLQ | SQS/SNS standard, policy, payload size |
| DLQ có raw event chứ không có responsePayload | Dùng Lambda async DLQ thay vì OnFailure destination | Kiểm tra `DeadLetterConfig` và `DestinationConfig` |
| SQS poison pill bị xử lý liên tục | Chưa có RedrivePolicy/`maxReceiveCount` phù hợp | SQS queue attrs/visibility/metrics |
| Một SQS message hỏng khiến cả batch chạy lại | Không bật partial batch hoặc handler throw | `ReportBatchItemFailures` và response schema |
| SQS successful message biến mất dù nghiệp vụ fail | Handler nuốt exception và trả success | Bắt lỗi đúng, trả partial failure hoặc throw |
| FIFO records sau record lỗi vẫn được xử lý | Partial response không giữ thứ tự | Dừng ở record lỗi và báo phần chưa xử lý |
| Stream `IteratorAge` tăng liên tục | Poison pill hoặc throughput/capacity yếu | Retry/age/bisect, shard backlog, destinations |
| OnFailure record lớn không gửi được SNS | 256 KiB SNS message cap hoặc destination limit | `DestinationDeliveryFailures`, chọn SQS/S3 phù hợp |
| Lambda timeout gây duplicate charge | Side effect thành công trước khi timeout | Downstream idempotency key, transactional design |
| Event replay xong nhưng kết quả trùng | Replay không đối soát trạng thái nghiệp vụ | Business operation ID và dedup state |
| Function thiếu concurrency, events quá tuổi | Throttles/backlog vượt max event age | `Throttles`, `AsyncEventAge`, reserved concurrency |
| Logs không chứa lỗi dù event bị mất | Event drop trước khi handler chạy | AsyncEventsDropped, metrics nguồn và sink |
| CloudWatch DLQ backlog không giảm | Chưa có owner/runbook/consumer hoặc consumer lỗi | Queue age, consumer errors, redrive plan |
| S3 destination bucket đã xóa | Destination ARN cũ có thể rủi ro gửi sang bucket ngoài ý muốn | Gỡ destination trước khi xóa, ràng buộc account |
| Không biết ai sở hữu lỗi | Thiếu correlation ID/owner và cảnh báo | Gắn eventId, traceId, owner; runbook và dashboard |

### 15.1. Quy trình điều tra theo thứ tự

~~~text
1. Xác nhận account, Region, function/alias/trigger.
2. Tìm invocation type: synchronous / async / event source mapping.
3. Xem error class: handler exception, timeout, throttle, system error.
4. Đối chiếu retry config thuộc đúng lớp.
5. Xem concurrency, backlog, age và source retention.
6. Kiểm tra OnFailure, Lambda DLQ hoặc source queue DLQ/ESM sink.
7. Kiểm tra quyền execution role, resource policy, KMS, size limit.
8. Xác định side effects đã commit hay chưa bằng business operation ID.
9. Sửa nguyên nhân và replay theo tốc độ được duyệt.
10. Theo dõi success, duplicate, latency, cost; ghi audit và kết thúc incident.
~~~

## 16. Tình huống thực tế: đăng ký khóa học và gửi email

### 16.1. Bối cảnh

Một nền tảng học trực tuyến trên AWS gồm:

- **API Gateway + Lambda** tiếp nhận đăng ký học;
- **DynamoDB** lưu trạng thái registration và business operation ID;
- **EventBridge** hoặc nguồn sự kiện phù hợp chuyển thông tin đăng ký;
- **Lambda email-worker** gọi nhà cung cấp email;
- **SQS DLQ/OnFailure destination** giữ lỗi sau khi retry;
- **CloudWatch** giám sát event lag, failures và số thư đã gửi.

Yêu cầu:

- Không gửi email trùng khi một event được deliver hai lần.
- Nếu email provider outage 15 phút, hệ thống có thể retry/replay.
- Sự kiện hỏng schema phải được cô lập.
- Không gửi địa chỉ email/PII tới destination không được phê duyệt.
- Có bảng điều khiển và runbook cho người trực.

### 16.2. Hai phương án kiến trúc

**Phương án A — Lambda asynchronous invocation trực tiếp:**

~~~mermaid
flowchart LR
    API[Registration API] --> EVT[EventBridge/S3/SNS async trigger]
    EVT --> L[Lambda async event queue]
    L --> W[Email worker]
    W --> P[Email provider]
    L -->|OnFailure| D[SQS standard destination]
    L -->|OnSuccess tùy chọn| S[EventBridge audit bus]
    D --> R[Quarantine / repair / replay]
~~~

Phù hợp khi sự kiện nhỏ và yêu cầu xử lý nằm trong giới hạn async queue. Có thể điều chỉnh retry attempts/max event age và gửi failure record.

**Phương án B — Durable SQS work queue:**

~~~mermaid
flowchart LR
    API[Registration API] --> Q[SQS source queue]
    Q --> E[Lambda event source mapping]
    E --> W[Email worker - partial batch response]
    W --> P[Email provider]
    Q -->|Redrive policy| D[SQS DLQ]
    D --> R[Controlled redrive]
~~~

Phù hợp khi muốn **quản lý queue retention, retry receive count, backlog và DLQ source** tách khỏi Lambda async invocation settings. Cả hai mô hình cần idempotency và giám sát.

### 16.3. Bảng chọn cơ chế

| Câu hỏi | Chọn Async Lambda | Chọn SQS source + ESM |
|---|---|---|
| Cần retry function error vài lần trong tối đa 6 giờ? | Phù hợp | Cũng làm được theo queue policy, nhưng cơ chế khác |
| Cần durable backlog retention độc lập Lambda? | Hạn chế hơn | **SQS** phù hợp hơn |
| Cần số lần nhận rõ ràng trước khi vào DLQ? | `MaximumRetryAttempts` chỉ function errors | `maxReceiveCount` trên source queue |
| Cần xử lý hàng loạt và partial failures? | Không phải dạng ESM batch | **SQS ESM** có `ReportBatchItemFailures` |
| Cần notification nhiều đích khi success? | `OnSuccess` destination | Consumer có thể phát sự kiện riêng sau commit |
| Cần record lỗi có request/response metadata? | `OnFailure` destination | Application log/record hoặc ESM features tùy nguồn |
| Có batch poison pills cần cô lập? | Xử lý event đơn hoặc thiết kế source | DLQ, partial batch, idempotency |

### 16.4. Giải pháp vận hành đề xuất

1. Mọi registration event có `registrationId` và `eventId` ổn định qua retries.
2. Email provider được gọi với idempotency key hoặc logic dedup tương đương.
3. Lỗi tạm thời được retry theo backoff có giới hạn; lỗi không sửa được được cách ly.
4. Failure sink bảo vệ bằng IAM/KMS, giữ dữ liệu tối thiểu và có retention.
5. Alarm nếu event lag, age, drop hoặc delivery failures vượt ngưỡng.
6. SQS DLQ/OnFailure record có owner và runbook để điều tra/replay.
7. Sau replay, đối soát email sent ledger và registration state.
8. Có kiểm thử duplicate, timeout ngay sau side effect, downstream outage và invalid payload.

## 17. Bài tập và câu hỏi tự kiểm tra

1. `InvocationType=Event` trả `StatusCode=202` có nghĩa handler đã gửi email chưa?
2. Vì sao Lambda sync invocation không tự retry function error như async?
3. `MaximumRetryAttempts=2` là tổng 2 lần chạy hay **2 lần thử lại** ngoài lần đầu?
4. Vì sao throttling và function error có cơ chế retry async khác nhau?
5. Điều gì xảy ra nếu event nằm trong Lambda async queue quá `MaximumEventAgeInSeconds`?
6. OnFailure destination khác Lambda async DLQ ở **message body** như thế nào?
7. OnSuccess destination có thể gửi record dù nghiệp vụ thực sự thất bại không?
8. Với một Lambda đọc SQS, tại sao `MaximumRetryAttempts` ở async invoke config không quyết định `maxReceiveCount`?
9. SQS visibility timeout ngắn hơn function timeout có rủi ro gì?
10. Khi xử lý batch 10 messages mà message thứ ba lỗi, vì sao có thể làm 2 messages đầu chạy lại?
11. `ReportBatchItemFailures` phải bật ở đâu, và handler cần trả cấu trúc gì?
12. Vì sao với SQS FIFO nên ngừng xử lý sau record đầu tiên thất bại?
13. Kinesis poison-pill record có thể làm tăng chỉ số nào?
14. `BisectBatchOnFunctionError` giúp xử lý lỗi gì? Có tự sửa record hỏng không?
15. Vì sao business operation ID tốt hơn Lambda request ID khi chống duplicate?
16. Event được gửi vào DLQ có nghĩa không còn cần IAM/KMS hay kiểm soát PII không?
17. Khi `DestinationDeliveryFailures` tăng, phải kiểm tra những lớp nào?
18. Nếu function tăng Errors nhưng source queue DLQ không có message, có những giải thích nào?
19. Vì sao redrive toàn bộ DLQ sau khi backend hồi phục vẫn nguy hiểm?
20. Những khoản phí nào có thể tăng khi một upstream outage kéo dài tạo nhiều retries?

### 17.1. Đáp án gợi ý ngắn

1. Không; chỉ là async request đã được chấp nhận.
2. Caller/service gọi quyết định việc retry.
3. Hai lần **retry**, thường tổng ba attempts nếu không bị giới hạn bởi tuổi/capacity.
4. Function error có số retry đã đặt; throttle/system error chịu backoff/event age.
5. Event có thể bị loại; cần OnFailure/DLQ phù hợp để lưu.
6. OnFailure là invocation record, Lambda DLQ chủ yếu là event input.
7. Có, nếu handler trả bình thường nhưng business logic thực sự fail.
8. SQS dùng ESM/visibility/redrive policy của queue.
9. Duplicate in-flight processing và inconsistent side effects.
10. Batch mặc định xử lý lại toàn bộ sau failure.
11. ESM `FunctionResponseTypes=ReportBatchItemFailures`, handler trả `batchItemFailures`.
12. Để giữ thứ tự trong message group.
13. `IteratorAge` tăng; xem ESM metrics và retention.
14. Chia batch lỗi để cô lập poison record; không tự sửa.
15. Request ID mới có thể xuất hiện mỗi invocation; business ID ổn định.
16. Không; failure records có thể chứa PII/response và phải bảo vệ.
17. Destination type, ARN, quyền, KMS, size, resource existence.
18. Sai source/lớp DLQ, chưa đạt redrive threshold, lỗi gửi DLQ, alias khác, retention/config khác.
19. Có thể tạo duplicate side effects hoặc replay invalid messages.
20. Lambda invokes/duration, SQS requests/storage, DLQ, CloudWatch, downstream calls và data transfer.

## 18. Checklist trước khi triển khai production

### Nguồn và retry

- [ ] Xác định từng trigger dùng **sync, async hay event source mapping**.
- [ ] Async function errors có retry count và max event age phù hợp SLO.
- [ ] SQS source có visibility timeout, redrive policy và maxReceiveCount phù hợp.
- [ ] Stream source có retention, max record age/retries, bisect và destination khi cần.
- [ ] Có kế hoạch xử lý duplicate và poison-pill records.
- [ ] Không giữ retry vô hạn bên trong handler hoặc SDK mà thiếu timeout budget.

### Failure handling

- [ ] Chọn rõ **OnFailure destination**, **Lambda async DLQ** hay **SQS source DLQ**, không đánh đồng.
- [ ] Hiểu body của failure record để xây parser/replay đúng.
- [ ] Destination/queue ARN, type và Region được xác minh.
- [ ] Function execution role và resource policy/KMS cấp đúng permissions.
- [ ] S3 destination có owner và guardrail khi xóa bucket.
- [ ] Bảo vệ event payload, response payload, PII và secret khỏi logs/failure sinks.
- [ ] Có metric/alarms cho `DeadLetterErrors`, `DestinationDeliveryFailures` và `AsyncEventsDropped`.
- [ ] Có owner/on-call, retention, runbook và quy trình redrive có phê duyệt.

### Nghiệp vụ, vận hành và chi phí

- [ ] Handler có idempotency key dựa trên business operation ID.
- [ ] Có chiến lược xử lý side effects đã commit trước timeout.
- [ ] Test duplicate event, transient failure, permanent failure, throttling và backlog.
- [ ] Theo dõi Errors/Throttles/Duration, AsyncEventAge hoặc IteratorAge, DLQ age.
- [ ] Có SLO xử lý cuối cùng và đối soát events processed vs events accepted.
- [ ] Có hướng rollback/replay an toàn và audit trails.
- [ ] Có budgets, tagging, cost allocation và dọn tài nguyên sandbox sau lab.

**Kết quả mong đợi:** người học không chỉ biết “bật retry” mà có thể xác định **lớp nào sở hữu retry**, thiết kế **đích giữ lỗi phù hợp**, giải thích lúc nào sự kiện bị loại, quản lý **at-least-once delivery** bằng idempotency và vận hành hệ thống event-driven có giám sát, khả năng phục hồi và chi phí được kiểm soát.

## Tài liệu AWS chính thức

- [Understanding retry behavior in AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html)
- [How Lambda handles errors and retries with asynchronous invocation](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html)
- [Configuring error handling settings for asynchronous invocations](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-configuring.html)
- [Capturing records of Lambda asynchronous invocations](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-retain-records.html)
- [Invoking Lambda functions asynchronously](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async.html)
- [AWS Lambda CloudWatch metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics-types.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Configuring an Amazon SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for SQS event sources](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Partial batch response for SQS event sources](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html#services-sqs-batchfailurereporting)
- [Using Lambda with Kinesis Data Streams](https://docs.aws.amazon.com/lambda/latest/dg/with-kinesis.html)
- [Retain discarded batch records for a Kinesis event source](https://docs.aws.amazon.com/lambda/latest/dg/kinesis-on-failure-destination.html)
- [Handling DynamoDB Streams errors](https://docs.aws.amazon.com/lambda/latest/dg/services-dynamodb-errors.html)
- [AWS Lambda API: EventInvokeConfig](https://docs.aws.amazon.com/lambda/latest/api/API_PutFunctionEventInvokeConfig.html)
- [AWS CloudFormation: AWS::Lambda::EventInvokeConfig](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-lambda-eventinvokeconfig.html)
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [AWS Step Functions retry and catch](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Lưu ý áp dụng:** Những tên function, queue, ARN, account ID, số liệu và JSON responses trong bài đều là ví dụ đào tạo. Tham số, nguồn event, loại destination, giới hạn, giá và tính năng AWS có thể thay đổi theo Region/thời điểm. Trước khi thay cấu hình production, đối chiếu API/tài liệu AWS hiện hành, thử nghiệm trên sandbox có dữ liệu giả, kiểm tra IAM/KMS và có phương án khôi phục được duyệt.
