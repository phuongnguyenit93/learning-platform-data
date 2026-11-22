# Mã hóa hàng đợi và phân quyền producer, consumer

Một hệ thống thương mại điện tử có thể nhận đơn hàng từ REST API, gửi thông báo cho kho và xử lý thanh toán bất đồng bộ. Dịch vụ tạo sự kiện (**producer**) gửi message vào **Amazon Simple Queue Service (Amazon SQS)**; các tiến trình xử lý (**consumer**) nhận message, thực thi nghiệp vụ rồi xóa message đã xử lý thành công. Nếu cấu hình sai, producer có thể gửi dữ liệu nhạy cảm vào hàng đợi không được bảo vệ, người không có quyền có thể đọc/xóa message, hoặc hệ thống gặp **KMS.AccessDeniedException** mặc dù IAM đã cho phép **sqs:SendMessage**.

Bài học thuộc chương **Hàng đợi và thông báo** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung đặt SQS và SNS trong kiến trúc AWS gồm Region/AZ, IAM, VPC, compute, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Mục tiêu là thiết kế **mã hóa, phân quyền producer/consumer**, giám sát, phục hồi và kiểm soát chi phí theo **least privilege**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò **producer, queue, consumer**, message lifecycle, visibility timeout và dead-letter queue (DLQ).
2. Phân biệt **SSE-SQS**, **SSE-KMS với AWS managed key**, **SSE-KMS với customer managed KMS key**, TLS và mã hóa phía ứng dụng.
3. Xác định phạm vi **message body được mã hóa** và những metadata không nằm trong phạm vi SSE.
4. Thiết kế **IAM identity policies**, **SQS resource-based queue policy**, **KMS key policy** và VPC endpoint policy.
5. Giải thích tại sao producer SSE-KMS cần cả **kms:GenerateDataKey và kms:Decrypt**, còn consumer cần **kms:Decrypt**.
6. Cấu hình quyền cho **SNS → encrypted SQS**, **Lambda polling SQS**, cross-account access, DLQ và key rotation.
7. Thực hành AWS CLI, Java SDK v2, chẩn đoán AccessDenied và xây checklist production.

## 2. Producer, queue và consumer hoạt động thế nào?

~~~mermaid
flowchart LR
    P["API / Lambda / ECS<br/>Producer"] -->|"SendMessage"| Q["Amazon SQS<br/>orders-events"]
    Q -->|"ReceiveMessage"| C["Lambda / ECS / EC2<br/>Consumer"]
    C -->|"Xử lý thành công:<br/>DeleteMessage"| Q
    C -. "Lỗi / visibility hết hạn:<br/>có thể nhận lại" .-> Q
    Q -->|"maxReceiveCount"| DLQ["Dead-letter queue"]
    C --> DB["DynamoDB / RDS / S3"]
~~~

**Producer** gửi message bằng **SendMessage/SendMessageBatch**. **Consumer** dùng **ReceiveMessage**, xử lý rồi **DeleteMessage** bằng receipt handle khi hoàn tất. Trong thời gian xử lý, **visibility timeout** tạm ẩn message khỏi consumer khác. Nếu xử lý lỗi hoặc không xóa kịp, message có thể được nhận lại. **Redrive policy** có thể chuyển message thất bại nhiều lần sang DLQ.

| Thành phần | Trách nhiệm | Vùng cần bảo vệ |
|---|---|---|
| **Queue** | Giữ message trước khi xử lý | Encryption, access policy, retention, DLQ |
| **Producer role** | Chỉ tạo message đúng queue | SendMessage và KMS quyền tạo data key |
| **Consumer role** | Nhận, xử lý, xóa message | Receive/Delete/ChangeVisibility, decrypt |
| **Visibility timeout** | Thời gian cho consumer xử lý | Tránh xử lý lặp sớm khi công việc dài |
| **Dead-letter queue** | Cô lập message gặp lỗi | Encryption, quyền kiểm tra và redrive |
| **SNS topic** | Fan-out một thông báo sang nhiều subscribers | Topic publishing policy và SQS queue policy |

**SQS không bảo đảm exactly-once end-to-end cho business side effects.** Standard queue giao ít nhất một lần và có thể không giữ đúng thứ tự. FIFO hỗ trợ thứ tự trong message group cùng cơ chế deduplication theo điều kiện, nhưng vẫn cần **idempotency, retry và transaction safety** ở consumer.

### 2.1. Role runtime nên dùng

| Runtime | IAM principal nên cấp quyền SQS | Tránh |
|---|---|---|
| AWS Lambda | **Lambda execution role** | Access keys hard-code trong environment variables |
| ECS/Fargate | **ECS task role** | Nhầm với task execution role dành cho image/log |
| EC2 | **EC2 instance profile role** | Access key lưu trong AMI |
| EKS | **EKS Pod Identity/IRSA** khi phù hợp | Pod dùng quyền node IAM role quá rộng |
| CI/CD hoặc operator | Role quản trị riêng, quyền thay đổi có kiểm soát | Dùng producer role để PurgeQueue/DeleteQueue |

SQS là dịch vụ theo **AWS Region**, không phải queue đặt trong subnet VPC; ứng dụng ở private subnet cần kết nối SQS regional endpoint qua **VPC interface endpoint** hoặc một tuyến mạng được phép khác.

## 3. Ba lựa chọn mã hóa at rest trong SQS

SQS hỗ trợ **server-side encryption (SSE)**. AWS đã triển khai **mã hóa SSE-SQS mặc định cho hàng đợi mới từ năm 2022** khi không chỉ định tùy chọn khác. Nhưng phải **kiểm tra thuộc tính của queue thật** vì queue cũ hoặc queue đã được cấu hình lại có thể dùng chế độ khác hoặc đã tắt SSE.

| Lựa chọn | Khóa bảo vệ | Điểm mạnh | Điều cần quản lý |
|---|---|---|---|
| **SSE-SQS** | Khóa do SQS sở hữu, AES-256 | Mã hóa tự quản lý, ít phức tạp | IAM/SQS policy; không cần KMS quyền riêng cho runtime |
| **SSE-KMS với AWS managed key** | AWS KMS key **alias/aws/sqs** | Sử dụng KMS mà không tự thiết kế key policy | Không sửa key policy, hạn chế một số integration/cross-account |
| **SSE-KMS với customer managed key** | KMS key do khách hàng quản lý | Tùy chỉnh quyền, lifecycle, audit, dịch vụ/cross-account | IAM + key policy, key rotation, quota và phí KMS |

**SSE-SQS khác SSE-KMS dùng alias/aws/sqs.** Hai chế độ không dùng đồng thời trên một queue. Các thuộc tính cần hiểu:

- **SqsManagedSseEnabled:** cho biết mã hóa bằng khóa SQS-owned.
- **KmsMasterKeyId:** key ID/ARN hoặc alias của AWS KMS dùng cho SSE-KMS.
- **KmsDataKeyReusePeriodSeconds:** thời gian SQS tái dùng data key, từ **60 đến 86.400 giây**, mặc định **300 giây**.

### 3.1. SSE-SQS không cần KMS IAM permissions riêng

Với SSE-SQS, producer được IAM/SQS policy cho phép gửi, consumer được cho phép nhận thì SQS tự mã hóa/giải mã message body theo cơ chế dịch vụ. Không cần thêm **kms:GenerateDataKey/kms:Decrypt** vào runtime roles chỉ để sử dụng SSE-SQS. Lựa chọn này phù hợp khi cần encryption at rest nhưng không cần kiểm soát customer-managed KMS key.

### 3.2. SSE-KMS dùng envelope encryption

~~~mermaid
flowchart TD
    P["Producer SendMessage"] --> SQS["Amazon SQS"]
    SQS -->|"GenerateDataKey khi cần"| KMS["AWS KMS<br/>Customer managed / alias aws/sqs"]
    KMS -->|"Data key và ciphertext key"| SQS
    SQS --> STORE["Lưu message body đã mã hóa"]
    STORE -->|"ReceiveMessage"| SQS
    SQS -->|"Decrypt data key khi cần"| KMS
    SQS -->|"Trả plaintext body qua API cho caller hợp lệ"| C["Consumer"]
~~~

Trong **envelope encryption**, KMS key bảo vệ **data encryption key (DEK)**; SQS dùng DEK để mã hóa/giải mã message body. Producer/consumer dùng **SQS API**, không cần tự gọi KMS trên từng message, nhưng KMS permissions vẫn được đánh giá cho caller khi SQS cần thao tác key thay mặt họ.

### 3.3. SSE mã hóa trường nào?

AWS xác định **SSE mã hóa message body**, không mã hóa:

- **Queue metadata:** queue name và các queue attributes.
- **Message metadata:** message ID, timestamp và **message attributes**.
- **Per-queue metrics**.

Ví dụ một body nghiệp vụ:

~~~json
{
  "orderId": "ord-example-104",
  "customerReference": "cust-example-79",
  "eventType": "ORDER_CREATED"
}
~~~

Nếu PII nằm trong **message attributes** hoặc queue name, **không được mặc định nó đã được SSE bảo vệ**. Hạn chế các dữ liệu nhạy cảm trong tags, headers, log và metadata. Nếu yêu cầu bảo mật nội dung đầu-cuối ngay cả với tầng SQS được ủy quyền, cân nhắc **client-side/application-level encryption** kèm quản lý khóa tại ứng dụng.

### 3.4. TLS và message đã tồn tại

**Mã hóa at rest không thay thế HTTPS/TLS in transit.** Đối với queue SSE, các yêu cầu cần dùng HTTPS và Signature Version 4. Có thể thêm **queue policy chặn insecure transport** như một lớp bảo vệ.

Thay đổi encryption của queue **không mã hóa lại toàn bộ backlog**. Message có sẵn trước khi bật SSE không tự động được mã hóa; message đã mã hóa tiếp tục cần key cũ ngay cả khi thay đổi thiết lập. Vì vậy khi đổi KMS key không được vội tắt/xóa key cũ trước khi tất cả message mã hóa bằng key đó đã được xử lý/loại bỏ.

## 4. Nhiều lớp authorization đồng thời

~~~mermaid
flowchart TD
    R["Producer / Consumer IAM role"] --> IAM["IAM identity policy<br/>Cho phép hành động SQS"]
    IAM --> Q["SQS queue policy<br/>Principals, network, SourceArn"]
    Q --> ENC{"SSE mode"}
    ENC -->|"SSE-SQS"| OK["SQS xử lý request<br/>nếu không bị Deny khác"]
    ENC -->|"SSE-KMS"| KEY["KMS key policy và IAM<br/>GenerateDataKey / Decrypt"]
    KEY --> OK
    GUARD["SCP, boundary, session policy,<br/>VPC endpoint policy, explicit Deny"] -. "Có thể giới hạn" .-> OK
~~~

| Lớp | Chức năng | Ví dụ |
|---|---|---|
| **IAM identity policy** | Cấp quyền SQS API cho role/user | Producer: **sqs:SendMessage** |
| **SQS queue policy** | Resource policy cho principal/service/cross-account/guardrail | SNS topic được gửi vào queue, chặn request không TLS |
| **KMS key policy** | Cấp hoặc cho phép IAM cấp quyền sử dụng KMS key | Chỉ đúng roles/service source được Decrypt/GenerateDataKey |
| **IAM KMS permission** | Cho principal sử dụng KMS key phù hợp khi policy cho phép | Consumer: **kms:Decrypt** theo key ARN |
| **SCP, permission boundary, session policy** | Giới hạn quyền được dùng | Chặn KMS actions ngoài điều kiện cho phép |
| **VPC endpoint policy** | Giới hạn truy cập khi request đi qua endpoint | Chỉ một queue/role được dùng từ interface endpoint |

**Một IAM Allow không thắng Explicit Deny.** Ví dụ producer có **sqs:SendMessage** nhưng thiếu quyền KMS thì request SSE-KMS có thể thất bại. Một queue policy từ chối request ngoài VPCE cũng có thể chặn role vốn đã được IAM cho phép.

### 4.1. Cùng account, cross-account và AWS service

- **IAM principal cùng account:** Allow từ identity policy **hoặc** queue resource policy có thể cấp phép theo cách IAM đánh giá, miễn không có Deny/giới hạn khác. Thực hành dễ audit: dùng IAM role policy cho ứng dụng, queue policy cho guardrails/integration.
- **Principal khác account:** cần Allow từ **identity policy account gọi** và **queue policy account sở hữu**, cộng quyền KMS liên account nếu queue dùng SSE-KMS.
- **AWS service** như SNS, S3 hoặc EventBridge gửi sự kiện: cần **queue policy cho service principal** với điều kiện **aws:SourceArn**/**aws:SourceAccount** phù hợp. Với queue SSE-KMS, cần thêm **customer-managed KMS key policy** cho service.

Tránh **Principal = "*" trong một Allow không điều kiện** để chữa lỗi tạm thời. Một statement **Deny** dùng principal "*" để bắt buộc TLS là trường hợp khác và phải được kiểm thử với những tích hợp AWS services có liên quan.

## 5. Permission matrix producer/consumer/operator

| Action | Producer | Consumer | Operator |
|---|---|---|---|
| **sqs:SendMessage** | Cần | Không mặc định | Khi redrive/publish có chủ đích |
| **sqs:ReceiveMessage** | Không | Cần | Chỉ khi kiểm tra message được phép |
| **sqs:DeleteMessage** | Không | Cần sau xử lý thành công | Khi redrive được ủy quyền |
| **sqs:ChangeMessageVisibility** | Không | Có thể cần cho job dài | Thường không |
| **sqs:GetQueueAttributes** | Tùy SDK | Thường cần | Cần khi kiểm kê |
| **sqs:GetQueueUrl** | Khi tra queue theo tên | Khi tra queue theo tên | Khi kiểm kê |
| **sqs:SetQueueAttributes** | Không | Không | Chỉ vai trò IaC/quản trị |
| **sqs:PurgeQueue/DeleteQueue** | Không | Không | Quyền nhạy cảm cần kiểm soát |
| **kms:GenerateDataKey** khi SSE-KMS | Cần | Không nếu chỉ đọc | Cần khi redrive đến queue SSE-KMS |
| **kms:Decrypt** khi SSE-KMS | Cần | Cần | Cần khi đọc/redrive message mã hóa |

**Vì sao producer cũng cần kms:Decrypt?** Khi **data key reuse period** hết hạn, lần **SendMessage/SendMessageBatch** tiếp theo có thể khiến SQS gọi cả **GenerateDataKey** và **Decrypt** để kiểm tra data key mới. Producer chỉ có GenerateDataKey có thể chạy được một thời gian rồi mới lỗi.

Consumer SSE-KMS cần **kms:Decrypt trên mọi KMS key dùng để mã hóa những message còn trong queue**. Nếu key đã đổi nhưng backlog cũ còn tồn, quyền với key mới không đủ để đọc toàn bộ queue.

### 5.1. Phân quyền bảo vệ dữ liệu và chi phí

Producer không cần **ReceiveMessage**. Consumer không cần **SendMessage** nếu chỉ xử lý/xóa. Các quyền **PurgeQueue**, **DeleteQueue** và **SetQueueAttributes** có thể xóa dữ liệu hoặc vô hiệu bảo vệ của cả hệ thống; tách chúng khỏi runtime roles và đưa vào quy trình change management.

## 6. Ví dụ IAM policy cho producer dùng SSE-KMS

Giả sử:

| Tài nguyên | Giá trị ví dụ |
|---|---|
| Region | **ap-southeast-1** |
| AWS account | **111122223333** |
| Queue | **orders-events** |
| Queue ARN | **arn:aws:sqs:ap-southeast-1:111122223333:orders-events** |
| KMS key ARN | **arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID** |
| Producer runtime | **ECS task role / EC2 instance role / Lambda execution role** |

Policy sau gắn vào **producer IAM role**. Đổi các ARN placeholder thành ARN thật trước khi sử dụng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendToOnlyOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:SendMessage"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events"
    },
    {
      "Sid": "UseOnlyOrdersQueueKmsKeyForProducer",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt"
      ],
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID"
    }
  ]
}
~~~

**Không cấp sqs:ReceiveMessage, sqs:DeleteMessage hoặc sqs:PurgeQueue** cho producer chỉ gửi message. Nếu ứng dụng tra queue URL bằng tên, cân nhắc thêm **sqs:GetQueueUrl** trên queue theo nhu cầu. Các permissions KMS chỉ có hiệu lực khi **key policy** cho phép role đó sử dụng KMS key hoặc cho phép account sử dụng IAM policies để cấp quyền.

### 6.1. Giới hạn KMS thêm bằng điều kiện

Với customer-managed KMS key, tổ chức có thể cân nhắc hạn chế quyền qua **kms:ViaService** và encryption context theo hỗ trợ của AWS KMS/SQS, chẳng hạn chỉ dùng key thông qua **sqs.ap-southeast-1.amazonaws.com**. Không tự thêm điều kiện vào production key policy mà chưa kiểm chứng **request context thực tế**, đặc biệt với cross-account, SNS/S3/EventBridge service principals và quy trình redrive.

**Không gắn điều kiện aws:SourceArn của SNS vào IAM policy của một producer application role rồi cho rằng nó sẽ hoạt động như SNS.** Service-to-service và direct SDK calls có principal/context khác nhau.

## 7. Ví dụ IAM policy cho consumer

Một worker Java trên ECS dùng **ECS task role** có thể có policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ProcessOnlyOrdersQueue",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events"
    },
    {
      "Sid": "DecryptOrdersMessages",
      "Effect": "Allow",
      "Action": "kms:Decrypt",
      "Resource": "arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID"
    }
  ]
}
~~~

**ChangeMessageVisibility** chỉ cần nếu consumer có thao tác kéo dài/điều chỉnh visibility. **GetQueueAttributes** thường được polling client/library dùng để kiểm tra cấu hình. Nếu worker đọc DLQ hoặc messages mã hóa bằng **nhiều key qua thời gian**, cần quyền tương ứng trên **DLQ ARN** và những **KMS key ARN** liên quan; không tự mở Decrypt trên mọi key.

### 7.1. Consumer phải xóa message đúng lúc

Một consumer đúng nên:

1. Nhận message và lưu **messageId**, **receipt handle**.
2. Kiểm tra schema, thực thi idempotent handler.
3. Nếu thành công, **DeleteMessage** bằng **receipt handle của lần nhận hiện tại**.
4. Nếu thất bại, không xóa; để retry hoặc DLQ theo thiết kế.
5. Với tác vụ dài, điều chỉnh **visibility timeout** hoặc dùng **ChangeMessageVisibility** có giới hạn.

**Xóa trước khi commit giao dịch có thể làm mất công việc.** Ngược lại, commit thành công rồi process chết trước khi DeleteMessage có thể khiến message được nhận lại. Idempotency và transactional design giúp xử lý khoảng hở đó.

### 7.2. Quyền đọc SQS không bằng quyền đọc database

Consumer có **kms:Decrypt** cho queue không có nghĩa được xem mọi KMS data, gọi DynamoDB hoặc đọc S3. Các tài nguyên downstream cần quyền IAM, resource policy, VPC network và authentication riêng. Người dùng chỉ có **sqs:ReceiveMessage** trên một queue SSE-KMS cũng không mặc nhiên nhận được plaintext nếu KMS key policy không cho quyền tương ứng.

## 8. Queue policy: principal, TLS và giới hạn nguồn

**SQS queue policy** là **resource-based policy** gắn trực tiếp với queue, dùng để cho phép AWS services/cross-account gửi message hoặc thêm guardrails. Khác với **IAM identity policy**, resource policy có **Principal** và các condition như **aws:SourceArn**, **aws:SourceAccount**, **aws:SecureTransport** và **aws:sourceVpce** trong những trường hợp được hỗ trợ.

### 8.1. Từ chối HTTP không mã hóa

Một statement minh họa để thêm vào **queue policy**:

~~~json
{
  "Sid": "DenyInsecureTransport",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "sqs:*",
  "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events",
  "Condition": {
    "Bool": {
      "aws:SecureTransport": "false",
      "aws:PrincipalIsAWSService": "false"
    }
  }
}
~~~

Đây là **một statement**, không phải toàn bộ policy JSON. Điều kiện **aws:PrincipalIsAWSService** giúp tránh Deny nhầm direct AWS service principals trong một số ngữ cảnh service-to-service thiếu network context. Vẫn phải kiểm tra các dịch vụ thực tế đang gọi queue, đặc biệt nếu service sử dụng một IAM role thay cho service principal.

**Không biến Deny thành một Allow có Principal "*".** SQS SSE cũng yêu cầu HTTPS/SigV4; explicit Deny là thêm một guardrail để tránh cấu hình sai và làm chuẩn kiểm toán rõ ràng.

### 8.2. VPC endpoint và queue policy

Nếu consumer chạy ở VPC private, một **SQS interface endpoint** có thể giúp kết nối SQS mà không dùng Internet/NAT cho traffic đó. Có hai lớp:

- **VPC endpoint policy:** chỉ định principal/action/queue được phép đi qua endpoint.
- **SQS queue policy:** có thể dùng **aws:sourceVpce** để giới hạn luồng từ một endpoint cụ thể.

Ví dụ kiến trúc:

~~~mermaid
flowchart LR
    WORKER["ECS / EC2 private subnet"] -->|"HTTPS 443"| VPCE["SQS Interface VPC Endpoint"]
    VPCE --> SQS["SQS orders-events"]
    SQS -->|"SSE-KMS khi cần"| KMS["AWS KMS"]
    ROLE["ECS task role / EC2 profile"] -. "IAM permissions" .-> WORKER
    QUEUE["Queue policy: VPCE/TLS guardrails"] -. "Resource authorization" .-> SQS
~~~

**Không chặn tất cả request không đi qua VPCE một cách máy móc** nếu SNS, S3, EventBridge hoặc một dịch vụ AWS khác cần gửi message **trực tiếp bằng service principal**. Các service-to-service calls có network context khác nhau và có thể bị Deny. Thiết kế ngoại lệ chính xác, dựa trên principal/service/source được phép; kiểm thử fan-out sau mỗi thay đổi.

KMS không nằm trong SQS VPC endpoint. Nếu ứng dụng thực sự gọi KMS API trực tiếp từ private subnet, có thể cần **KMS interface endpoint** hoặc tuyến mạng khác; khi SQS dùng SSE-KMS thay mặt caller, cần phân biệt luồng nội bộ service-to-service với network của SDK caller.

### 8.3. Tránh confused deputy bằng SourceArn và SourceAccount

Khi một AWS service gửi vào SQS thay mặt tài nguyên khác, queue policy nên ràng buộc **nguồn cụ thể**:

- **aws:SourceArn:** ARN của SNS topic, EventBridge rule hoặc tài nguyên sự kiện được phép.
- **aws:SourceAccount:** AWS account sở hữu nguồn khi service/context hỗ trợ.
- **Principal.Service:** service producer đúng, ví dụ **sns.amazonaws.com**.

Đây là cách giảm nguy cơ **confused deputy**: một principal khác không thể nhờ service đã được tin cậy gửi vào queue bằng nguồn không được phê duyệt. Kiểm tra condition keys nào thực sự được dịch vụ tích hợp cung cấp; thiếu key trong request context có thể làm statement không match.

## 9. SNS → encrypted SQS: phải mở cả SQS lẫn KMS

Với **Amazon SNS fan-out**, publisher ứng dụng gọi **sns:Publish** vào SNS topic, **không** trực tiếp gọi SendMessage tới SQS queues được subscribe. Sau đó **SNS** làm producer khi chuyển thông báo đến từng SQS queue.

~~~mermaid
flowchart LR
    PUB["Ứng dụng publisher"] -->|"sns:Publish"| SNS["SNS orders-topic"]
    SNS -->|"sqs:SendMessage"| Q1["SQS orders-billing<br/>SSE-KMS"]
    SNS -->|"sqs:SendMessage"| Q2["SQS orders-warehouse<br/>SSE-KMS"]
    Q1 --> L["Lambda consumer<br/>kms:Decrypt"]
    Q2 --> ECS["ECS consumer<br/>kms:Decrypt"]
    KMS["Customer-managed<br/>KMS key policy"] -. "Cho SNS dùng<br/>GenerateDataKey/Decrypt" .-> Q1
    KMS -. "Key phù hợp Q2" .-> Q2
~~~

### 9.1. Queue policy cho phép một SNS topic cụ thể

Ví dụ statement **gắn vào queue orders-billing**:

~~~json
{
  "Sid": "AllowOnlyOrdersTopic",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-billing",
  "Condition": {
    "ArnEquals": {
      "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:orders-topic"
    },
    "StringEquals": {
      "aws:SourceAccount": "111122223333"
    }
  }
}
~~~

**Đây là queue policy fragment, không phải SNS topic policy.** App publisher cần **sns:Publish** trên topic; muốn tạo subscription phải có quyền/subscription policy tương ứng. SQS queue phải chấp nhận service principal **SNS**, không chỉ vai trò publisher của ứng dụng.

### 9.2. KMS key policy cho phép SNS publish tới SSE-KMS queue

Với queue SSE-KMS sử dụng customer-managed KMS key, cần thêm quyền cho **sns.amazonaws.com** trong **key policy** của đúng KMS key. Ví dụ statement minh họa:

~~~json
{
  "Sid": "AllowSNSServiceUseKeyForSqs",
  "Effect": "Allow",
  "Principal": {
    "Service": "sns.amazonaws.com"
  },
  "Action": [
    "kms:GenerateDataKey",
    "kms:Decrypt"
  ],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "aws:SourceAccount": "111122223333"
    }
  }
}
~~~

**Resource "*" ở đây nằm trong statement của KMS key policy**, nghĩa là tài nguyên key đang mang policy đó; không tương đương cho phép SNS thao tác mọi KMS keys của account. Đây **chỉ là một statement**, cần key policy hoàn chỉnh có quyền quản trị phù hợp, các consumer permissions và chính sách khôi phục. Có thể ràng buộc chặt hơn theo **SourceArn** khi dịch vụ/tình huống hỗ trợ và đã kiểm chứng request context.

**AWS-managed KMS key alias/aws/sqs không cho bạn thay key policy.** Vì thế khi dùng SNS/S3/EventBridge hoặc cross-account gửi tới encrypted SQS và cần service principal KMS permissions tùy chỉnh, lựa chọn thường là **customer-managed KMS key**. Đừng lẫn việc SNS topic có SSE với việc SQS subscriber có SSE; mỗi phía có key policy, quyền và chi phí riêng.

### 9.3. EventBridge, S3 notifications và những nguồn khác

Các nguồn như **EventBridge rules**, **S3 event notifications**, **SNS subscriptions** có thể gửi message vào SQS theo cách được hỗ trợ. Mỗi luồng cần:

1. Quyền của service/producer ở **SQS queue policy**.
2. Nếu SSE-KMS, quyền **kms:GenerateDataKey/kms:Decrypt** ở **customer-managed KMS key policy** theo loại source.
3. Các rule, subscription, filters và target ARNs đúng Region/account, cùng giới hạn hỗ trợ FIFO/standard của từng nguồn.

Không chỉ kiểm tra IAM role của ứng dụng ban đầu rồi kết luận quyền SNS đã đủ. **SNS, S3 và EventBridge là những service principals khác nhau**, mỗi service có sự kiện và condition keys cần đối chiếu.

## 10. Cross-account producer và consumer

Giả sử **Account A** có producer và **Account B** sở hữu SQS queue:

| Bước | Nơi cấu hình | Yêu cầu |
|---|---|---|
| **1. Identity policy** | Account A | Role producer được **sqs:SendMessage** trên queue ARN của B |
| **2. Queue policy** | Account B | Allow đúng role/account A thực hiện SendMessage trên queue B |
| **3. KMS key policy** (nếu SSE-KMS) | Account B hoặc account sở hữu key | Cho principal Account A quyền KMS cần thiết qua customer-managed key |
| **4. IAM KMS permission** | Account A | Cho producer dùng đúng KMS key ARN được chia sẻ |
| **5. SCP/endpoint/network** | Hai account | Không có Deny chặn path hoặc service integration |

Ví dụ **queue policy statement** cho role cụ thể từ Account A:

~~~json
{
  "Sid": "AllowOneExternalProducer",
  "Effect": "Allow",
  "Principal": {
    "AWS": "arn:aws:iam::444455556666:role/external-orders-producer"
  },
  "Action": "sqs:SendMessage",
  "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events"
}
~~~

Một consumer ở account khác cần **Receive/Delete/GetQueueAttributes** theo mô hình tương tự, cộng quyền Decrypt nếu SSE-KMS. Với SSE-KMS cross-account, **không thể sửa AWS-managed KMS key policy** để cấp quyền mới; dùng **customer-managed key** được cấu hình cross-account.

**Lưu ý:** role trust policy và sts:AssumeRole chỉ cần thêm nếu thiết kế cho Account A **assume một role ở Account B**. Nếu producer Account A gọi trực tiếp SQS bằng IAM role của A và được queue policy cho phép, đó là **resource-based cross-account authorization**, không tự đòi ứng dụng phải assume role B.

### 10.1. Không dùng queue URL để xác định quyền

Biết queue URL hoặc ARN **không tạo ra quyền truy cập**. Mỗi request vẫn được ký bằng credentials của một IAM principal và được IAM/queue/KMS/endpoint policies kiểm tra. Queue URL là địa chỉ API, không phải secret.

## 11. Lambda làm consumer của encrypted SQS

Với **AWS Lambda event source mapping** cho SQS, Lambda service poll queue, nhận batch rồi invoke function. **Lambda execution role** cần ít nhất:

- **sqs:ReceiveMessage**
- **sqs:DeleteMessage**
- **sqs:GetQueueAttributes**
- **kms:Decrypt** nếu queue được mã hóa bằng KMS key cần quyền đó

Trong nhiều trường hợp, managed policy **AWSLambdaSQSQueueExecutionRole** cung cấp nhóm quyền SQS cơ bản, nhưng phải xem policy hiện hành và **chỉ cấp bổ sung KMS key permissions khi cần**. Với queue cross-account hoặc customer-managed KMS key, đối chiếu queue policy/key policy và giới hạn cùng Region của event source mapping.

~~~mermaid
flowchart TD
    SQS["Encrypted SQS queue"] --> POLL["Lambda event source mapping<br/>Poll + batch"]
    POLL -->|"Invoke batch"| FN["Lambda function<br/>Execution role"]
    FN -->|"Thành công"| DELETE["Lambda/SQS xóa message<br/>đã xử lý"]
    FN -->|"Lỗi / partial failure"| RETRY["Retry sau visibility<br/>hoặc DLQ"]
    KMS["KMS key"] -. "Execution role: Decrypt" .-> POLL
~~~

### 11.1. Visibility timeout và batch failure

Một task có thể nhận message nhiều lần khi handler lỗi, timeout hoặc consumer bị gián đoạn. Khi gắn Lambda với SQS:

- Đặt **visibility timeout** đủ cho thời gian function thực thi, retry/throttling; AWS có hướng dẫn sử dụng ít nhất **6 lần function timeout** trong cấu hình thông thường cần điều chỉnh theo batch window.
- Tùy use case, bật **partial batch response** với **ReportBatchItemFailures** để chỉ retry các message lỗi thay vì toàn bộ batch.
- Đảm bảo consumer **idempotent** và xử lý đúng thứ tự FIFO khi có lỗi theo message group.
- Giới hạn concurrency nếu RDS/API downstream không chịu được tăng tải.

**Lambda function role không cần sqs:SendMessage để đọc queue.** Còn **producer Lambda** gửi vào queue thì cần SendMessage và GenerateDataKey/Decrypt nếu SSE-KMS. Vai trò được phân theo **hành động thực hiện**, không theo tên dịch vụ Lambda.

## 12. Dead-letter queue (DLQ), mã hóa và redrive

**DLQ** giúp giữ message vượt quá **maxReceiveCount** trong redrive policy của source queue. Nó phục vụ chẩn đoán/retry, không phải kho backup vô thời hạn. DLQ phải có retention đủ dài để đội vận hành phát hiện và phân tích lỗi trước khi message hết hạn.

### 12.1. Điểm dễ hiểu sai về mã hóa khi chuyển sang DLQ

Theo tài liệu SQS, **việc SQS chuyển message sang DLQ không làm thay đổi encryption của chính message đó**:

| Source queue | DLQ | Trạng thái message được tự động chuyển |
|---|---|---|
| SSE-KMS encrypted | SSE-SQS/không SSE | Message mã hóa bằng KMS key nguồn vẫn yêu cầu **key nguồn** khi giải mã |
| Không mã hóa | DLQ SSE-KMS | Message được chuyển không tự trở thành message mã hóa bằng DLQ KMS key |
| Source thay key qua thời gian | DLQ nhận message từ nhiều giai đoạn | Consumer/redrive có thể cần **nhiều KMS keys** cũ và mới |

**Đừng dùng DLQ để “mã hóa lại” một backlog vốn không mã hóa.** Đồng thời đừng tắt customer-managed KMS key nguồn ngay sau khi message đã chuyển sang DLQ; khi đọc/redrive có thể vẫn phải dùng key đó.

### 12.2. Quyền đọc DLQ và quyền redrive không giống nhau

Một nhân viên vận hành đọc DLQ để điều tra cần **ReceiveMessage** và, nếu xem body SSE-KMS, **kms:Decrypt** đúng key. Nhưng thao tác **StartMessageMoveTask** để chuyển hàng loạt message từ DLQ trở lại queue nguồn hoặc queue khác cần một nhóm quyền riêng:

| Tài nguyên | Quyền liên quan đến redrive |
|---|---|
| **DLQ nguồn của move task** | **sqs:StartMessageMoveTask**, **sqs:ReceiveMessage**, **sqs:DeleteMessage**, **sqs:GetQueueAttributes** |
| **Queue đích** | **sqs:SendMessage** |
| **KMS keys của DLQ/message cũ** | **kms:Decrypt** nếu có encryption |
| **KMS key của queue đích** | **kms:GenerateDataKey** và **kms:Decrypt** khi dùng SSE-KMS |
| **Theo dõi/hủy move task** | **sqs:ListMessageMoveTasks** và **sqs:CancelMessageMoveTask** theo hành động được ủy quyền |

**SQS redrive allow policy** của DLQ quyết định những source queues nào được phép dùng DLQ đó theo thiết lập tương ứng, **không phải** cùng một thứ với **queue access policy** hoặc IAM policy của operator.

Redrive một backlog có thể khiến consumer xử lý lại nhiều giao dịch. Trước khi thực hiện phải xác minh **root cause đã được sửa**, idempotency, ordering (đặc biệt FIFO), tốc độ redrive, downstream capacity và quyền dữ liệu. Không cho phép redrive hàng loạt bằng runtime role thông thường.

### 12.3. Ví dụ redrive policy (minh họa)

Một source queue có thể lưu thuộc tính redrive policy:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:orders-events-dlq",
  "maxReceiveCount": "5"
}
~~~

Đây là **giá trị của RedrivePolicy**, không phải một IAM policy. Queue nguồn và DLQ phải có **loại queue tương thích** (standard với standard, FIFO với FIFO); phải kiểm tra quyền dịch vụ, retention và dữ liệu thực trước khi thay đổi. **maxReceiveCount = 5** chỉ là ví dụ, không phải ngưỡng đúng cho mọi workload.

## 13. KMS key rotation, data key reuse và tổng chi phí

### 13.1. Data key reuse period

SQS SSE-KMS có cơ chế **tái dùng data key** trong khoảng thời gian cấu hình để giảm số yêu cầu KMS. Tham số:

~~~text
KmsDataKeyReusePeriodSeconds = 60 ... 86400
Default = 300
~~~

Một khoảng tái dùng ngắn có thể làm tăng số lần SQS sử dụng KMS và chi phí API KMS; một khoảng dài giảm overhead nhưng phải phù hợp chính sách bảo mật/khả năng kiểm toán của tổ chức. SQS còn xét **requester** khác nhau dựa trên AWS credentials và một số scoping policies, nên không thể lấy số message chia giản đơn cho reuse period rồi khẳng định chính xác số KMS API calls.

**Không nghĩ rằng đặt reuse period thành 300 giây nghĩa là message chỉ được mã hóa 5 phút.** Message body tiếp tục được lưu mã hóa đến khi SQS xóa nó; reuse period chỉ liên quan cách sử dụng **data key** và tần suất thao tác KMS.

### 13.2. Thay key khác với tự động quay vòng key material

Hai khái niệm:

- **KMS automatic/on-demand key rotation:** KMS thay đổi key material của **cùng logical key** theo cơ chế hỗ trợ; ciphertext cũ vẫn được decrypt bằng key đó theo lifecycle.
- **Chuyển queue sang KMS key ARN khác:** messages cũ giữ encryption/key ban đầu. Phải duy trì **KMS key cũ còn hoạt động và permissions** đến khi những message cũ, DLQ và bản ghi còn liên quan đã được xử lý hết.

Nếu tắt/xóa key quá sớm, consumer có thể nhận **KMS.DisabledException**, **KMS.NotFoundException** hoặc **AccessDenied** khi giải mã những message tồn đọng, kể cả queue hiện đã hiển thị key mới.

### 13.3. Chi phí cần dự toán

| Hạng mục | Cách tính/cân nhắc |
|---|---|
| **SQS API requests** | Send, Receive, Delete, batch, long polling và số yêu cầu thực |
| **SSE-SQS** | Không có phí KMS riêng cho chế độ SQS-owned |
| **SSE-KMS** | KMS key storage/monthly fee với customer-managed keys, KMS API requests theo giá hiện hành |
| **Data key reuse period** | Có thể thay số lượng KMS calls và tỷ lệ lỗi khi KMS throttling |
| **DLQ/retries** | Message được nhận/gửi lại nhiều lần, log và công xử lý |
| **SNS/EventBridge** | Publish/delivery/ingestion và retry tương ứng |
| **Compute** | Lambda invocations/duration hoặc ECS/EC2 capacity |
| **Network/logging** | Interface endpoints, data transfer, CloudWatch, CloudTrail data events nếu được bật |

Không nên chọn SSE-KMS chỉ vì một bảng giá tham khảo có số nhỏ hơn. Quyết định dựa trên **compliance, key policy, cross-account integration, auditability, KMS quota** và cả chi phí vận hành. Dùng bảng giá hiện hành cho đúng Region và workload để ước lượng.

## 14. AWS CLI kiểm kê encryption và quyền queue

**Những lệnh dưới đây chỉ đọc**, có thể chạy trong lab/tài khoản được ủy quyền. Đổi Region, queue name và AWS profile cho môi trường thực.

### 14.1. Xác định đúng IAM principal và queue ARN

~~~bash
# Ai đang ký AWS requests?
aws sts get-caller-identity --output json

# Lấy QueueUrl từ tên queue.
aws sqs get-queue-url \
  --region ap-southeast-1 \
  --queue-name orders-events \
  --output json

# Kiểm tra ARN, trạng thái SSE, key, queue policy và DLQ.
aws sqs get-queue-attributes \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --attribute-names QueueArn SqsManagedSseEnabled KmsMasterKeyId KmsDataKeyReusePeriodSeconds Policy RedrivePolicy RedriveAllowPolicy \
  --output json
~~~

Kết quả có thể thiếu những thuộc tính không được cấu hình trên loại queue đó. Với **SSE-SQS**, kiểm tra **SqsManagedSseEnabled = true**; với **SSE-KMS**, kiểm tra **KmsMasterKeyId**. Không suy luận “không có field KmsMasterKeyId” nghĩa là queue hoàn toàn không mã hóa.

### 14.2. Kiểm tra KMS key và thời hạn xóa

~~~bash
aws kms describe-key \
  --region ap-southeast-1 \
  --key-id arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID \
  --query 'KeyMetadata.{Arn:Arn,State:KeyState,Enabled:Enabled,KeyManager:KeyManager,DeletionDate:DeletionDate}' \
  --output json
~~~

Nếu key ở account khác, quyền đọc metadata hoặc KMS cross-account policy có thể khiến lệnh không được phép. **DescribeKey thành công không chứng minh GenerateDataKey/Decrypt được phép**; phải xét key policy, IAM, permission boundaries, SCP và KMS log/errors.

### 14.3. Cấu hình mã hóa trong môi trường thử nghiệm

Các lệnh này **thay đổi tài nguyên SQS**; chỉ thực hiện khi đã có quyền và kế hoạch kiểm soát backlog/key lifecycle:

~~~bash
# Ví dụ: chọn customer-managed KMS key cho queue lab.
aws sqs set-queue-attributes \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --attributes KmsMasterKeyId=arn:aws:kms:ap-southeast-1:111122223333:key/REPLACE_KEY_ID,KmsDataKeyReusePeriodSeconds=300
~~~

Lệnh mẫu giả định queue đang dùng một trạng thái tương thích để chuyển sang SSE-KMS. Vì SQS chỉ cho một SSE option tại một thời điểm, nếu queue hiện dùng **SSE-SQS**, phải kiểm tra cơ chế chuyển đổi **SqsManagedSseEnabled** và SSE-KMS theo AWS CLI/API hiện hành, tránh đưa hai lựa chọn trái nhau trong một thay đổi. Sau khi ghi, luôn đọc lại các thuộc tính.

**Không tự vô hiệu hóa encryption** hoặc đổi sang key chưa cấp đủ quyền cho producer/consumer. Thử trước với message riêng trong staging, xác nhận queue access, KMS permissions, DLQ và fan-out integrations.

### 14.4. Thử Send/Receive trong lab

Các lệnh tiếp theo **có tác động lên queue** và chỉ nên chạy với payload giả, queue lab không xử lý nghiệp vụ thật:

~~~bash
# Producer lab, không chứa PII hoặc secrets.
aws sqs send-message \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --message-body '{"eventType":"LAB_TEST","id":"test-001"}'

# Consumer lab nhận tối đa 1 message; lưu ý message sẽ vào trạng thái in-flight.
aws sqs receive-message \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --max-number-of-messages 1 \
  --wait-time-seconds 10
~~~

Không thử **ReceiveMessage** trên queue production chỉ để “xem thử” vì sẽ làm thay đổi visibility và có thể can thiệp consumer thật. Để chứng minh phân quyền, nên thử với **hai IAM roles tách biệt trong lab**: producer Send được nhưng Receive bị từ chối; consumer Receive/Delete được nhưng Send bị từ chối; vai trò không được phép phải nhận AccessDenied.

## 15. AWS SDK for Java v2: producer và consumer đúng trách nhiệm

AWS SDK for Java v2 sử dụng **default credentials provider chain** để lấy temporary credentials từ Lambda execution role, ECS task role, EC2 instance role hoặc cơ chế đã cấu hình. **Không hard-code AWS access keys trong Java code, Docker image hoặc Git**.

### 15.1. Producer gửi một message

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public final class OrdersProducer {
    private static final String QUEUE_URL =
        "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events";

    public static void main(String[] args) {
        try (SqsClient sqs = SqsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            sqs.sendMessage(SendMessageRequest.builder()
                .queueUrl(QUEUE_URL)
                .messageBody("{\"eventType\":\"LAB_TEST\",\"id\":\"test-001\"}")
                .build());
        }
    }
}
~~~

Với SSE-KMS, code **không tự mã hóa body trước khi SendMessage**. SQS dùng queue encryption settings; role của process phải có **sqs:SendMessage** và các quyền KMS của producer tương ứng. Payload minh họa không chứa dữ liệu thật; trong production cần JSON serialization, schema version, correlation ID, retry với backoff và idempotency design.

### 15.2. Consumer: DeleteMessage chỉ sau khi xử lý thành công

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;

public final class OrdersConsumer {
    private static final String QUEUE_URL =
        "https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events";

    public static void main(String[] args) {
        try (SqsClient sqs = SqsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            var result = sqs.receiveMessage(ReceiveMessageRequest.builder()
                .queueUrl(QUEUE_URL)
                .maxNumberOfMessages(5)
                .waitTimeSeconds(10)
                .build());

            for (Message message : result.messages()) {
                // Lab-only: xử lý idempotent; ở production phải kiểm tra schema.
                boolean processed = process(message.body());
                if (processed) {
                    sqs.deleteMessage(DeleteMessageRequest.builder()
                        .queueUrl(QUEUE_URL)
                        .receiptHandle(message.receiptHandle())
                        .build());
                }
                // Nếu false: không xóa; message có thể retry/DLQ.
            }
        }
    }

    static boolean process(String body) {
        // Chỉ demo, không thực thi side effects.
        return body.contains("LAB_TEST");
    }
}
~~~

Ví dụ ngắn này **không phải consumer production hoàn chỉnh**: phải có loop, lifecycle/shutdown handling, retry, exception handling, idempotency store, DLQ alerts, visibility extension và concurrency control phù hợp. Nếu việc xử lý có side effect mà consumer chết trước DeleteMessage, message có thể được nhận lại — vì thế **at-least-once** là hợp đồng cần thiết kế từ đầu.

## 16. Quy trình triển khai một encrypted queue an toàn

### Bước 1 — Phân loại dữ liệu và đường đi

Xác định producer là app IAM role, **SNS**, **S3**, **EventBridge** hay một account khác. Consumer là Lambda event source mapping, ECS task hay EC2 service? Vẽ nguồn/đích rõ ràng, ví dụ:

~~~mermaid
flowchart LR
    USER["REST API"] --> APP["Lambda producer<br/>IAM role A"]
    APP -->|"SendMessage"| Q["orders-events<br/>SSE-KMS CMK"]
    Q -->|"ReceiveMessage"| WORKER["ECS consumer<br/>IAM task role B"]
    WORKER -->|"Idempotent write"| DB["DynamoDB"]
    Q --> DLQ["orders-events-dlq"]
    KMS["Customer-managed KMS key"] -. "Producer: GenerateDataKey/Decrypt<br/>Consumer: Decrypt" .-> Q
    IAM["IAM + queue + key policies"] -. "Least privilege" .-> Q
~~~

Đầu ra nên là ma trận **principal × queue × action × encryption key × network path**, có owner và yêu cầu lưu trú dữ liệu/retention. Đưa **thông tin nghiệp vụ tối thiểu** vào message body; không nhúng passwords/access tokens.

### Bước 2 — Chọn encryption mode

- **SSE-SQS** nếu chỉ cần mã hóa mặc định mà không cần key policy KMS tùy chỉnh.
- **SSE-KMS customer managed key** nếu cần quyền KMS chi tiết, key rotation/quản trị hoặc integration/cross-account mà AWS-managed key không đáp ứng.
- Kiểm tra sự hỗ trợ theo **Region, source service và queue type**; xác định phí KMS/quotas và kế hoạch khôi phục key.

**Chọn customer-managed KMS key trước khi cấu hình SNS/S3/EventBridge** nếu hệ thống đó cần quyền key policy riêng; việc đổi chế độ giữa chừng tác động quyền producer, consumer và backlog.

### Bước 3 — Tách IAM roles

Tạo **producer role** chỉ gửi message; **consumer role** chỉ nhận/xóa và decrypt; **infrastructure deployment role** quản lý queue/key policies. Mỗi role có trust policy đúng runtime. Với SSE-KMS, bảo đảm key policy hỗ trợ IAM delegation hoặc cấp phép trực tiếp cho principals/service sources cụ thể.

### Bước 4 — Cấu hình queue policy và network

Đặt queue policy cho **service principal/SourceArn** hoặc IAM principal cross-account đúng. Bổ sung TLS guardrail; khi dùng VPCE, bảo đảm client VPC dùng endpoint và service integrations không bị chặn. Với private subnets, kiểm tra DNS, endpoint security group, TCP 443, NACL và route thích hợp.

### Bước 5 — Bảo vệ DLQ và lifecycle key

Tạo DLQ cùng loại phù hợp, redrive policy, redrive allow policy, encryption, retention, quyền điều tra và redrive operator. Theo dõi các message mã hóa bằng key cũ; đừng xóa key cũ nếu còn messages hoặc quy trình recovery dùng nó.

### Bước 6 — Kiểm thử positive/negative permissions

Tối thiểu kiểm thử:

| Thử nghiệm | Kỳ vọng |
|---|---|
| Producer role SendMessage đúng queue | **Allow** |
| Producer role ReceiveMessage | **Deny** |
| Consumer role Receive/Delete đúng queue | **Allow** |
| Consumer role SendMessage | **Deny** nếu không được giao |
| SNS từ đúng topic gửi vào encrypted queue | **Allow** với queue và KMS policies đúng |
| SNS từ topic/account không được phép | **Deny** |
| Role không có KMS decrypt đọc SSE-KMS queue | **Deny** |
| Worker private subnet gọi qua endpoint được phép | **Allow** |
| Quyền PurgeQueue của runtime | **Deny** |
| DLQ redrive chỉ bởi operator có quyền | **Allow**, các role runtime khác bị từ chối |

Trong production, thay vì cố gửi/nhận message thật để kiểm tra Deny, hãy dùng **IAM Policy Simulator/Access Analyzer** khi khả dụng, kiểm tra policies và thực hiện thử nghiệm động trong staging. Với KMS, simulator không thay thế hoàn toàn việc kiểm tra **key policy và service integration thực tế**.

## 17. Giám sát, kiểm toán và dữ liệu nhạy cảm

### 17.1. CloudWatch metrics của SQS

SQS phát hành metric trong namespace **AWS/SQS**. Những chỉ số vận hành quan trọng:

| Metric | Ý nghĩa | Hướng xử lý khi bất thường |
|---|---|---|
| **ApproximateNumberOfMessagesVisible** | Backlog đang sẵn sàng nhận | Producer tăng đột biến, consumer chậm hoặc lỗi |
| **ApproximateNumberOfMessagesNotVisible** | Message đang in-flight | Worker nghẽn, visibility timeouts hoặc batch lớn |
| **ApproximateAgeOfOldestMessage** | Tuổi message cũ nhất theo semantics SQS | Nguy cơ chậm SLO, consumer không theo kịp |
| **NumberOfMessagesSent** | Số lần gửi thành công được đếm theo API | Phát hiện producer giảm/bất thường |
| **NumberOfMessagesReceived** | Số message được trả cho consumers | Có thể cao hơn sent vì retry |
| **NumberOfMessagesDeleted** | Số lần delete thành công được đếm | Không đồng nghĩa số unique business events xử lý |
| **NumberOfEmptyReceives** | Số lần polling không có message | Kiểm tra hiệu quả long polling và chi phí |
| **DLQ ApproximateNumberOfMessagesVisible** | Message thất bại đang đợi chẩn đoán | Cảnh báo poison messages/processor failure |

Vì kiến trúc SQS phân tán, **nhiều chỉ số chỉ xấp xỉ**. **NumberOfMessagesReceived** có thể đếm cùng message nhiều lần; **NumberOfMessagesDeleted** có thể phản ánh nhiều delete calls, không chứng minh số giao dịch hoàn thành. Với DLQ, những message tự động chuyển từ source không nhất thiết được tính vào **NumberOfMessagesSent** như gửi tay. Do đó nên cảnh báo dựa vào **backlog, age, errors và SLO**, không chỉ số lần send/delete.

### 17.2. CloudTrail và KMS audit

**CloudTrail** hỗ trợ điều tra các thao tác AWS APIs được ghi nhận, trong đó có cấu hình queue, key usage và các tương tác phù hợp theo loại event. Khi cần giám sát **message-level access**, xác định rõ loại log/data event được hỗ trợ và cấu hình thu thập theo yêu cầu, không giả định mọi Send/Receive luôn xuất hiện trong mặc định CloudTrail event history.

Với **SSE-KMS**, CloudTrail KMS events có thể giúp thấy hoạt động như **GenerateDataKey/Decrypt** hoặc lỗi khi dùng key, nhưng việc KMS dùng data key reuse nghĩa là **không có một KMS event cho mọi message**. Khi điều tra cần kết hợp:

1. **SQS API error response** và thời gian/thao tác.
2. **Caller identity/role** cùng account/Region.
3. **SQS queue policy và queue encryption attributes**.
4. **KMS key ARN, key state, IAM/key policy, KMS events**.
5. **VPC endpoint policy, SCP, boundaries** nếu có.

### 17.3. Logging ứng dụng nhưng không lộ nội dung nhạy cảm

Producer/consumer nên log:

- Correlation ID, event type, schema version, queue ARN hoặc tên an toàn.
- Thời điểm send, receive, process, delete, retry, DLQ.
- Lý do lỗi dạng **KMS AccessDenied, authorization denied, timeout, schema invalid**.
- Latency xử lý, số retries và tỉ lệ thành công.

Không log **toàn bộ message body** nếu chứa thông tin khách hàng, dữ liệu thanh toán hoặc secrets; không log AWS access key, authorization headers, decrypted payload không cần thiết hoặc receipt handles công khai. Dùng redaction, retention và IAM read logs theo nguyên tắc tối thiểu.

## 18. Runbook chẩn đoán lỗi mã hóa và quyền truy cập

~~~mermaid
flowchart TD
    A["SendMessage / ReceiveMessage lỗi"] --> B["Ghi lại caller role, account,<br/>Region, action và queue ARN"]
    B --> C{"Lỗi đến từ SQS hay KMS?"}
    C -->|"SQS AccessDenied"| Q["IAM identity policy + queue policy<br/>SCP, endpoint, SecureTransport"]
    C -->|"KMS.AccessDenied"| K["Queue SSE-KMS key ARN<br/>key policy, IAM permissions, key state"]
    C -->|"Timeout / network"| N["DNS, TLS, route, VPC endpoint,<br/>security group / NAT"]
    Q --> R["Kiểm tra đúng principal,<br/>SourceArn, VPCE và explicit Deny"]
    K --> R
    N --> R
    R --> T["Sửa quyền tối thiểu trong staging<br/>xác minh positive/negative tests"]
~~~

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra theo thứ tự |
|---|---|---|
| **SQS AccessDenied khi SendMessage** | Thiếu SendMessage, queue policy Deny, queue ARN sai | STS caller identity, IAM/queue policies, SCP |
| **SQS AccessDenied khi ReceiveMessage** | Consumer thiếu ReceiveMessage, VPCE condition hoặc queue policy Deny | Caller, queue ARN, queue/endpoint policy |
| **KMS.AccessDeniedException khi SendMessage** | Thiếu GenerateDataKey hoặc Decrypt; key policy không cho | Queue KmsMasterKeyId, producer IAM, KMS key policy |
| **Gửi vài phút rồi mới KMS AccessDenied** | Data key reuse đã hết, caller thiếu kms:Decrypt | Key reuse period, logs và cả hai KMS actions |
| **ReceiveMessage lỗi KMS Decrypt** | Consumer thiếu kms:Decrypt hoặc dùng key cũ | Consumer IAM, key policy, lịch sử đổi key |
| **KMS.DisabledException / NotFoundException** | Key bị disabled, scheduled deletion hoặc sai ARN | DescribeKey state, key lifecycle, backlog |
| **SNS subscription nhận zero messages** | Queue policy không cho SNS, KMS key policy thiếu SNS, filter sai | Subscription status, SourceArn, SNS delivery metrics, key policy |
| **S3/EventBridge event không vào queue** | Chưa cho đúng service principal, condition sai, integration không hỗ trợ | Source ARN, queue policy, KMS key policy, events/errors |
| **Cross-account caller được IAM Allow nhưng vẫn lỗi** | Thiếu queue resource Allow hoặc KMS cross-account policy | Cả hai accounts, queue policy, key policy, SCP |
| **SSE-KMS alias/aws/sqs không dùng được với nguồn khác account** | Không thể sửa AWS-managed key policy | Chuyển sang customer-managed key có kiểm soát |
| **ECS private subnet timeout SQS** | Thiếu endpoint/NAT/DNS/SG/route | VPC endpoint, TCP 443, private DNS và routes |
| **Queue đọc được qua VPCE nhưng SNS không gửi được** | Deny ngoài VPCE chặn service-to-service | Kiểm tra aws:sourceVpce condition và ngoại lệ service principal |
| **DLQ có message nhưng không đọc được** | Key nguồn đã tắt, thiếu decrypt key cũ | DLQ message history, source keys, IAM |
| **Redrive AccessDenied** | Thiếu StartMessageMoveTask, Receive/Delete, Send, KMS permissions | DLQ/destination permissions và keys |
| **Tăng receive count/age** | Consumer lỗi, processing lâu, visibility thấp | App logs, DLQ, visibility timeout, database |
| **Message bị xử lý hai lần** | At-least-once, timeout giữa commit và delete | Idempotency key, business transaction, receipts |
| **Chi phí KMS tăng đột ngột** | Nhiều requesters, reuse period ngắn, high throughput | Key reuse, KMS usage, SQS requests, pricing |

### 18.1. Quy trình từng bước khi xảy ra AccessDenied

1. Lấy **role ARN thật** bằng **aws sts get-caller-identity** trong đúng runtime/tài khoản.
2. Phân biệt **SQS.AccessDenied** với **KMS.AccessDeniedException**; đọc toàn bộ error metadata và request ID.
3. Đọc **SqsManagedSseEnabled/KmsMasterKeyId** để biết đang dùng SSE-SQS hay SSE-KMS.
4. Kiểm tra đúng **IAM action** trên **queue ARN** và nếu SSE-KMS, **KMS actions** trên **key ARN**.
5. Đọc **queue policy**, **KMS key policy**, SCP/boundary và VPC endpoint policy; tìm explicit Deny hoặc condition không match.
6. Với SNS/S3/EventBridge, kiểm tra **service principal** và **SourceArn/SourceAccount**, không chỉ role ứng dụng gửi sự kiện ban đầu.
7. Thử sửa **một lớp quyền cụ thể** trong staging và kiểm tra lại thành công/lệnh bị Deny. Không mở wildcard permissions để “cứu” production.
8. Sau khi sửa, đối chiếu **CloudWatch metrics, backlog, DLQ và dữ liệu thật** để bảo đảm messages không bị bỏ sót hoặc xử lý lặp ngoài thiết kế.

## 19. Tình huống thực hành

### Tình huống A — Producer có SendMessage nhưng vẫn lỗi sau 5 phút

Một worker ECS gửi thành công vào queue dùng SSE-KMS với **KmsDataKeyReusePeriodSeconds = 300**. Sau một thời gian, request lỗi **KMS.AccessDeniedException**. Producer IAM có **kms:GenerateDataKey** nhưng không có **kms:Decrypt**.

**Câu hỏi:** vì sao quyền SQS đúng vẫn chưa đủ?

**Gợi ý:** khi reuse period hết, SQS có thể cần cả **GenerateDataKey** và **Decrypt**. Thêm quyền chính xác cho producer trên key ARN, xác minh key policy/IAM/SCP. Không cấp kms:* toàn account.

### Tình huống B — SNS không gửi vào queue SSE-KMS

Ứng dụng đã có **sns:Publish** tới topic. Queue subscribe có policy cho **sns.amazonaws.com** và đúng SourceArn nhưng không nhận message. Queue dùng **alias/aws/sqs**.

**Câu hỏi:** cần kiểm tra phần nào?

**Gợi ý:** kiểm tra SNS delivery errors/filter, queue policy, sau đó **KMS key policy cho SNS service producer**. Khi cần quyền tùy chỉnh mà AWS-managed key không cho sửa, cân nhắc **customer-managed KMS key** và add đúng KMS service principal permissions.

### Tình huống C — Consumer Lambda khác account

Queue thuộc Account B, function Lambda thuộc Account A. Lambda execution role có **sqs:ReceiveMessage**, **DeleteMessage**, **GetQueueAttributes** trên queue ARN, nhưng poll không thành công; queue SSE-KMS dùng key của B.

**Câu hỏi:** cần những lớp quyền nào?

**Gợi ý:** IAM policy Account A, queue resource policy Account B, KMS key policy/role decrypt permission hỗ trợ cross-account, network/Region/quotas. Nếu dùng AWS-managed KMS key alias/aws/sqs mà không thể sửa policy, chuyển sang customer-managed key theo hướng dẫn. Không chỉ thêm ReceiveMessage lặp lại.

### Tình huống D — DLQ không giải mã được sau khi thay key

Source queue đã chuyển từ KMS key **K1** sang **K2**. Đội vận hành tắt **K1** ngay vì nghĩ những message đã nằm DLQ giờ được mã hóa bằng key DLQ. Khi mở DLQ, họ gặp lỗi decrypt.

**Câu hỏi:** sai ở đâu?

**Gợi ý:** chuyển message tự động sang DLQ **không đổi encryption của message**. Message mã hóa bằng K1 vẫn cần K1; phải giữ key và quyền decrypt cho backlog/DLQ, sau đó mới tính kế hoạch loại bỏ key cũ.

### Tình huống E — Bắt buộc VPC endpoint làm hỏng SNS fan-out

Một queue policy Deny tất cả requests không có **aws:sourceVpce** nhất định. Worker ECS nhận được message qua endpoint, nhưng SNS topic không gửi được.

**Câu hỏi:** vì sao?

**Gợi ý:** AWS service-to-service requests có context khác worker trong VPC. Rà soát explicit Deny, dành ngoại lệ được chứng minh theo service principal/SourceArn thay vì mở toàn bộ queue; kiểm tra queue/KMS policies sau thay đổi.

### Tình huống F — Consumer xóa message trước khi ghi DB

Một Java consumer gọi **DeleteMessage** ngay sau ReceiveMessage rồi mới ghi database. Nếu database timeout, đơn hàng biến mất khỏi queue mà chưa được xử lý.

**Câu hỏi:** sửa theo thứ tự nào?

**Gợi ý:** xử lý idempotent và commit thành công trước khi DeleteMessage; khi lỗi không xóa để SQS retry và DLQ. Thiết kế giao dịch/deduplication để xử lý khả năng message bị gửi lại sau commit.

### Tình huống G — Queue SSE-SQS nhưng auditor yêu cầu KMS logs theo key riêng

Hệ thống hiện dùng SSE-SQS, đạt encryption at rest. Auditor yêu cầu quản lý customer-owned key policy, lifecycle và audit events ở mức KMS.

**Câu hỏi:** có thể chỉ gắn một IAM KMS policy vào producer rồi xem yêu cầu được đáp ứng?

**Gợi ý:** không. SSE-SQS không phải SSE-KMS. Cần đánh giá chuyển sang **SSE-KMS customer-managed key**, thiết kế quyền, KMS cost/quota, backlog, service integrations và cơ chế rotation trước khi thay đổi.

## 20. Checklist triển khai production

- [ ] Đã xác định producer/consumer/service sources và queue/Region/account chính xác.
- [ ] Đã chọn **SSE-SQS** hoặc **SSE-KMS** theo yêu cầu dữ liệu, audit, cross-account và ngân sách.
- [ ] Đã xác minh **message body** được SSE mã hóa; không để PII/secrets trong **message attributes, queue names, logs**.
- [ ] Đã bật HTTPS/TLS và SigV4; queue policy có guardrail phù hợp với service integrations.
- [ ] Producer IAM chỉ có **SendMessage** (và GetQueueUrl nếu cần), không có Receive/Delete/Purge.
- [ ] Consumer IAM chỉ có **Receive/Delete/GetQueueAttributes/ChangeVisibility** theo nhu cầu thật.
- [ ] Nếu SSE-KMS, producer có **kms:GenerateDataKey + kms:Decrypt**, consumer có **kms:Decrypt** trên đúng key ARN.
- [ ] KMS key policy cho phép đúng roles/service principals; không phụ thuộc vào IAM Allow nếu key policy không cho.
- [ ] Queue policy giới hạn service principal, **SourceArn/SourceAccount** và cross-account principals đúng.
- [ ] Nếu dùng SNS/S3/EventBridge, đã kiểm tra **cả queue policy và KMS key policy**.
- [ ] Nếu dùng cross-account, đã xác minh identity IAM, SQS resource policy và customer-managed key permissions.
- [ ] Nếu dùng VPCE, đã kiểm tra endpoint policy, DNS, SG, TCP 443 và tránh Deny nhầm service-to-service.
- [ ] Đã đặt visibility timeout, retry/idempotency, FIFO group semantics và DLQ phù hợp.
- [ ] DLQ encryption, retention, redrive allow policy và quyền read/redrive chỉ cấp cho operator được duyệt.
- [ ] Khi đổi KMS key, đã có kế hoạch cho message cũ và không disable key trước khi xử lý backlog/DLQ.
- [ ] Đã test positive/negative permissions, AWS SDK flows và service integration trong staging.
- [ ] Đã giám sát backlog, oldest age, processing errors, DLQ và KMS AccessDenied/usage.
- [ ] Đã giới hạn quyền quản trị **SetQueueAttributes/PurgeQueue/DeleteQueue** và lưu audit logs theo retention.
- [ ] Đã dự toán SQS API, KMS requests/key cost, retries, compute, DLQ, networking và CloudWatch.
- [ ] Đã có runbook khi lỗi IAM, KMS, network, key rotation và redrive.

## 21. Ghi nhớ

**SQS SSE-SQS** mã hóa message body bằng khóa do SQS sở hữu, ít phức tạp và không cần runtime KMS permissions riêng. **SSE-KMS** dùng AWS KMS key, trong đó **producer cần kms:GenerateDataKey và kms:Decrypt**, còn **consumer cần kms:Decrypt**; KMS key policy phải cho phép các quyền tương ứng. **IAM identity policy** xác định hành động của application role, **SQS queue policy** kiểm soát truy cập vào queue từ service/cross-account/source, và **KMS key policy** kiểm soát sử dụng khóa. Ba lớp không thể dùng thay thế nhau.

Khi nối **SNS → SQS**, phải kiểm tra cả quyền **SNS service principal ở queue policy** lẫn **KMS key policy của encrypted queue**; khi cần tùy chỉnh policy cho AWS services/cross-account, dùng **customer-managed KMS key**. **DLQ không tự mã hóa lại message**, vì thế cần giữ key cũ đến khi backlog đã được xử lý. Cuối cùng, bảo mật chỉ đầy đủ khi kết hợp **TLS, IAM least privilege, dữ liệu tối thiểu, idempotent consumers, giám sát và kế hoạch phục hồi**.

### Tài liệu AWS chính thức để đối chiếu

- [What is Amazon SQS?](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html) — tổng quan queue, producer, consumer.
- [Encryption at rest in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-server-side-encryption.html) — SSE-SQS, SSE-KMS, phạm vi message body và DLQ.
- [Configure SSE-SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-sqs-sse-queue.html) — SQS-owned encryption keys.
- [Configure SSE-KMS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-sse-existing-queue.html) — key ARN và queue encryption.
- [Amazon SQS key management](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-key-management.html) — producer/consumer KMS permissions, reuse period, key rotation.
- [Least privilege policies for encrypted queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-least-privilege-policy.html) — IAM, SQS, KMS, DLQ và confused deputy.
- [Troubleshoot AccessDenied in Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/troubleshooting-access-denied.html) — IAM, queue, KMS, VPCE, SCP.
- [Amazon SQS security best practices](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-security-best-practices.html) — TLS, least privilege, network endpoints.
- [Subscribe Amazon SQS to Amazon SNS topic](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-subscribe-queue-sns-topic.html) — fan-out, SourceArn và cross-account.
- [Configure SQS Lambda trigger](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-lambda-function-trigger.html) — execution role và polling encrypted queue.
- [SQS dead-letter queue redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html) — DLQ permissions, redrive và KMS.
- [Available CloudWatch SQS metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html) — backlog, age, receive/delete metrics.
- [Amazon SQS API SetQueueAttributes](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SetQueueAttributes.html) — SSE queue attributes.
- [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/), [AWS KMS pricing](https://aws.amazon.com/kms/pricing/) và [AWS Pricing Calculator](https://calculator.aws/) — dự toán theo giá hiện hành.



