# SNS topic, subscription và giao thức phân phối

> **Chương:** Hàng đợi và thông báo  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá AWS qua Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless; rèn cách chọn dịch vụ, triển khai an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Một hệ thống bán hàng cần gửi sự kiện `order.created` cho kho, vận chuyển, thông báo khách hàng, kiểm toán và phân tích. Nếu API đặt hàng phải gọi đồng bộ từng hệ thống, một dependency chậm có thể làm tăng độ trễ hoặc gây lỗi dây chuyền. **Amazon Simple Notification Service (Amazon SNS)** cung cấp mô hình **publish/subscribe (pub/sub)**: ứng dụng phát thông điệp vào một **topic**, các **subscriptions** xác định đích nhận và giao thức vận chuyển.

Ba khái niệm trung tâm:

- **Topic:** điểm phát message dùng chung, có ARN, loại Standard/FIFO, resource policy, encryption và giới hạn kích thước.
- **Subscription:** liên kết giữa topic và endpoint cụ thể, có protocol, filter policy, trạng thái xác nhận, raw delivery, retry và DLQ phù hợp.
- **Delivery protocol:** cách SNS đẩy message đến SQS, Lambda, HTTP(S), email, SMS, mobile push hoặc Amazon Data Firehose.

Sau bài học, bạn có thể:

1. Mô tả luồng producer → SNS topic → subscription → consumer và lý do cần fan-out.
2. Phân biệt SNS **Standard** và **FIFO**, mức bảo đảm thứ tự/deduplication và loại đích được hỗ trợ.
3. Chọn giao thức đích theo yêu cầu backlog, độ trễ, thông báo người dùng và phân tích.
4. Cấu hình hoặc phân tích subscription confirmation, filter policy và raw delivery.
5. Phân biệt lỗi **giao message tại SNS** với lỗi **xử lý ở consumer** và chọn đúng DLQ.
6. Thiết kế IAM, topic policy, SQS queue policy, KMS, HTTPS signature verification.
7. Kiểm tra cấu hình bằng AWS CLI; hiểu ví dụ IaC và quy trình lab sandbox.
8. Giải thích monitoring, event schema, idempotency, replay, chi phí và giới hạn mới.

## 1. Từ tích hợp đồng bộ đến publish/subscribe

### 1.1. Bài toán fan-out

Một Order API tạo đơn hàng, sau đó nhiều nghiệp vụ cần phản ứng độc lập:

~~~mermaid
flowchart LR
    API[Order API] -->|Publish: order.created| SNS[(SNS Standard Topic)]
    SNS -->|subscription inventory| Q1[SQS queue inventory]
    SNS -->|subscription shipping| Q2[SQS queue shipping]
    SNS -->|subscription notify| L[Lambda notifications]
    SNS -->|subscription analytics| FH[Amazon Data Firehose]
    Q1 --> INV[Inventory worker]
    Q2 --> SHIP[Shipping worker]
    L --> EMAIL[Email/SMS service]
    FH --> LAKE[(S3 data lake)]
~~~

**Publisher** chỉ cần biết topic và contract của event. **Subscriber** có thể đăng ký nhánh mới mà không bắt publisher sửa mọi chỗ gọi API. Mỗi đích có delivery status, filter và retry riêng.

Dù `Publish` trả `MessageId`, bạn **chưa biết mọi consumer đã xử lý thành công**. Phân biệt:

~~~text
Producer gọi sns:Publish thành công
   -> SNS chấp nhận message
      -> SNS giao tới từng endpoint
         -> Endpoint nhận/ghi message
            -> Consumer thực hiện nghiệp vụ
               -> Ghi dữ liệu và ack/commit
~~~

Một lỗi ở bước cuối không mặc nhiên khiến bước publish ban đầu thất bại.

### 1.2. SNS và SQS không thay thế nhau

| Khía cạnh | SNS | SQS |
|---|---|---|
| Kiểu kết nối | Pub/sub: một message có thể tới nhiều endpoints | Queue: consumer chủ động nhận messages |
| Fan-out | Có, qua nhiều subscriptions | Thường kết hợp nhiều SQS queues với SNS/EventBridge |
| Lưu backlog worker | Không phải mục tiêu chính của Standard topic | Có queue retention, visibility timeout |
| Retry chính | SNS retry **delivery tới subscription endpoint** | Consumer retry qua visibility timeout/redrive |
| Phân phối | SQS, Lambda, HTTPS, email, SMS, push, Firehose... | Worker/SDK/Lambda ESM poll queue |
| Lưu thất bại | SNS subscription DLQ nếu không giao được | SQS source-queue DLQ nếu xử lý nhiều lần không thành công |
| Thứ tự | Standard best effort; FIFO theo điều kiện | Standard best effort; FIFO theo MessageGroupId |

Một mô hình thường dùng là **SNS topic → mỗi nhóm một SQS queue**. Nếu inventory ngừng hoạt động 30 phút, queue của inventory vẫn chứa công việc trong retention window, trong khi shipping tiếp tục hoạt động.

**Khi không nên thêm SNS:** nếu chỉ có đúng một consumer và không cần fan-out/nhánh thông báo, SQS trực tiếp có thể đơn giản và rẻ hơn.

### 1.3. SNS so với EventBridge

**SNS** thuận tiện cho phân phối pub/sub tới nhiều protocol, filter theo attributes/body và fan-out có độ trễ thấp. **Amazon EventBridge** phù hợp event bus/routing theo event pattern, SaaS integrations, schema-based architecture và quy trình tích hợp khác. Hai dịch vụ có retry, quota, pricing và security controls không đồng nhất. Không chọn chỉ vì tên “event”; hãy bắt đầu từ **delivery contract** của subscriber.

## 2. Standard topic và FIFO topic

### 2.1. Standard

**SNS Standard** phù hợp đa số ứng dụng muốn fan-out qua nhiều protocol:

- Tính sẵn sàng và thông lượng lớn;
- Phân phối **at least once** trong các trường hợp được dịch vụ hỗ trợ, nên có thể có bản trùng;
- Thứ tự giao theo **best effort**, không dùng nó làm thứ tự giao dịch bắt buộc;
- Hỗ trợ SQS, Lambda, HTTP(S), email, SMS, mobile push, Firehose theo giới hạn từng protocol.

Ví dụ thông báo: thay đổi hồ sơ, sự kiện đơn hàng, cảnh báo vận hành và analytics. Nếu out-of-order event nguy hiểm, consumer cần version/sequence và không ghi đè bằng dữ liệu cũ.

### 2.2. FIFO

**SNS FIFO topic** có thứ tự/deduplication theo **message group**:

- Cần `MessageGroupId` cho các sự kiện thuộc cùng luồng thứ tự.
- Sử dụng `MessageDeduplicationId` hoặc content-based deduplication theo cấu hình.
- Đường **SNS FIFO → SQS FIFO** phù hợp khi cần strict ordering trong từng group.
- SNS FIFO cũng có thể giao tới **SQS Standard**, nhưng queue Standard không giữ strict order/no duplicates tại tầng nhận.
- SNS FIFO **không trực tiếp subscribe Lambda, email, HTTP(S), SMS hoặc mobile push**.
- Nếu cần Lambda xử lý FIFO: **SNS FIFO → SQS FIFO → Lambda event source mapping**.
- Filtering, expiration, retry và các nguồn duplicate bên ngoài vẫn cần được phân tích; **không suy ra exactly-once business side effect**.

~~~mermaid
flowchart LR
    P[Publisher] -->|MessageGroupId=order-123| T[(SNS FIFO)]
    T --> Q1[SQS FIFO accounting]
    T --> Q2[SQS FIFO shipping]
    T --> Q3[SQS Standard analytics]
    Q1 --> F[Lambda via SQS ESM]
    Q2 --> W[Worker]
~~~

Trong cùng group `order-123`, việc publish các trạng thái created → paid → shipped theo đúng thứ tự là trách nhiệm publisher. SNS không sửa các event phát sai thứ tự từ nguồn.

### 2.3. Bảng chọn

| Yêu cầu | Chọn |
|---|---|
| Fan-out tới nhiều giao thức gồm HTTPS/email | Standard |
| Thứ tự theo từng đơn hàng tới hàng đợi | FIFO topic + FIFO queue |
| Một worker queue đơn giản, không fan-out | SQS trực tiếp |
| Cần cả FIFO và webhook/email | Tách luồng: FIFO → SQS cho nghiệp vụ có thứ tự; Standard topic cho notification |
| Thông điệp được xử lý ngay không cần durable backlog ở endpoint | Standard → Lambda nếu phù hợp |
| Báo cáo/lưu trữ stream | Standard → Data Firehose |

### 2.4. Ví dụ publish FIFO

~~~bash
# CHỈ MINH HỌA, không chạy trên topic production
aws sns publish \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events.fifo \
  --message '{"eventId":"evt-001","orderId":"order-123","eventType":"order.created"}' \
  --message-group-id "order-123" \
  --message-deduplication-id "evt-001" \
  --region ap-southeast-1
~~~

Dùng **business event ID ổn định** khi retry cùng event, không sinh ID mới mỗi lần retry. Khoảng deduplication của SNS/SQS là hữu hạn; do đó, consumer vẫn cần idempotency khi được replay ngoài cửa sổ ấy.

## 3. Topic, Subscription ARN và endpoint

### 3.1. Các định danh

~~~text
TopicArn:
arn:aws:sns:ap-southeast-1:111122223333:orders-events

SubscriptionArn:
arn:aws:sns:ap-southeast-1:111122223333:orders-events:550e8400-e29b-41d4-a716-446655440000

Endpoint (SQS queue):
arn:aws:sqs:ap-southeast-1:111122223333:inventory-events
~~~

**Topic ARN** dùng với `sns:Publish` và topic policy; **Subscription ARN** dùng với `Get/SetSubscriptionAttributes`, `Unsubscribe`; **Endpoint ARN/URL** định vị queue, Lambda, Firehose, HTTP URL, email hoặc số điện thoại theo protocol.

### 3.2. Subscription attributes

| Thuộc tính | Tác dụng | Giới hạn |
|---|---|---|
| `Protocol` | Kiểu giao nhận | Mỗi topic type hỗ trợ các protocol khác nhau |
| `Endpoint` | Địa chỉ đích | Phải hợp lệ và có quyền nhận |
| `PendingConfirmation` | Chờ xác nhận | Chưa confirm thì không nhận notification thông thường |
| `FilterPolicy` | Chọn subset messages | Không phải cơ chế bảo mật |
| `FilterPolicyScope` | `MessageAttributes` hoặc `MessageBody` | Mặc định `MessageAttributes` |
| `RawMessageDelivery` | Gửi payload trực tiếp cho SQS/HTTP(S)/Firehose theo hỗ trợ | Parser và message attributes khác |
| `DeliveryPolicy` | HTTP(S) retries/backoff | Không điều khiển retries của SQS consumer |
| `RedrivePolicy` | SNS delivery failure DLQ | Queue cùng account/Region theo tài liệu |
| `SubscriptionRoleArn` | Role giao tới Firehose | Cần đúng IAM permissions |

### 3.3. Subscription confirmation

Email và HTTP(S) thường cần **chủ endpoint xác nhận**:

~~~mermaid
sequenceDiagram
    participant O as Topic owner
    participant SNS as Amazon SNS
    participant E as Email / HTTPS endpoint
    O->>SNS: Subscribe
    SNS->>E: SubscriptionConfirmation
    E->>E: Verify sender/signature + TopicArn
    E->>SNS: ConfirmSubscription / link được tin cậy
    SNS-->>O: Confirmed
    O->>SNS: Publish
    SNS->>E: Notification
~~~

Đối với **email**, người nhận có quyền với mailbox cần click xác nhận. Đối với **HTTP(S)**, SNS gửi thông điệp `SubscriptionConfirmation` có `Token` và `SubscribeURL`. **Không tự động truy cập URL bất kỳ do bên ngoài cung cấp**; kiểm tra chữ ký/TopicArn/cert và domain AWS SNS hợp lệ trước khi xác nhận để tránh SSRF và subscription hijack.

Nếu trạng thái vẫn `PendingConfirmation`, cần xử lý confirmation trước khi tìm lỗi message filtering hoặc consumer.

### 3.4. Một topic có nhiều subscribers

~~~text
SNS Standard topic: orders-events
├── subscription protocol=sqs, endpoint=inventory-events
├── subscription protocol=sqs, endpoint=billing-events
├── subscription protocol=lambda, endpoint=notification-worker
├── subscription protocol=https, endpoint=partner.example.com
└── subscription protocol=firehose, endpoint=orders-data-stream
~~~

Mỗi subscription có thể có **filter policy**, DLQ và các quyền khác nhau. **Đừng cho principal không được phép đọc event subscribe vào topic nhạy cảm** chỉ dựa vào một filter mà họ có thể thay đổi.

## 4. Giao thức phân phối

### 4.1. Tổng quan

| Protocol | Endpoint | Dùng khi nào? | Trách nhiệm riêng |
|---|---|---|---|
| `sqs` | SQS queue ARN | Work queue, backlog, tách consumer | Queue resource policy, visibility, redrive |
| `lambda` | Lambda function ARN | Xử lý serverless, side effects nhỏ | Lambda permission, async errors/destinations |
| `http` / `https` | URL | Webhook, tích hợp đối tác | Confirmation, signature, retry/backoff |
| `email` | Email address | Thông báo đơn giản/on-call | Confirm mailbox, không bảo đảm đã đọc |
| `email-json` | Email address | Nhận SNS JSON qua email | Không phải durable queue |
| `sms` | Phone number | Cảnh báo/người dùng nhận SMS | Consent, quốc gia, sender registration, phí |
| `application` | Platform endpoint ARN | Mobile push APNs/FCM | Device token, credentials, endpoint state |
| `firehose` | Firehose stream ARN | Lưu sự kiện vào S3/analytics | Subscription role và streaming configuration |

**Chú ý:** danh sách trên mô tả khả năng của **Standard topic** trong cấu hình hỗ trợ. FIFO có giới hạn trực tiếp tới SQS. Với `MaximumMessageSize>256 KiB`, SNS chỉ hỗ trợ **SQS, Lambda và Firehose subscriptions** và có quota ≤100 subscriptions/topic; giới hạn FIFO-to-SQS vẫn áp dụng.

### 4.2. SQS — lựa chọn phổ biến nhất cho xử lý bền vững

~~~mermaid
flowchart LR
    T[(SNS Topic)] -->|delivered| Q[SQS Source Queue]
    Q --> W[Worker/Lambda ESM]
    Q -->|redrive nếu xử lý thất bại| D[SQS Consumer DLQ]
    T -->|SNS không giao được| SD[SNS Subscription DLQ]
~~~

**Phải có SQS queue policy** cho phép SNS principal gửi `sqs:SendMessage` từ đúng topic ARN. Với queue SSE-KMS, cũng phải có KMS permissions phù hợp. Nếu queue nhận thành công nhưng worker throw, retry thuộc **SQS consumer** (visibility timeout/redrive), không thuộc SNS.

**Khi nào dùng:** inventory, shipping, billing, email worker, jobs có retry, xử lý theo batch hoặc cần tự điều chỉnh tốc độ consumer.

### 4.3. Lambda — SNS Standard trực tiếp

SNS có thể gửi tới Lambda function và Lambda được invoke **asynchronously**. Phân biệt hai tình huống:

- SNS **không invoke được** Lambda (function không tồn tại, resource policy deny): lỗi delivery của SNS → retry SNS → **SNS subscription DLQ**.
- SNS đã invoke thành công nhưng handler exception/timeout: Lambda quản lý **async retry**, `OnFailure` destination hoặc **Lambda DLQ** theo cấu hình riêng.

Lambda function cần resource-based policy cho `sns.amazonaws.com` và condition giới hạn topic `SourceArn`. SNS FIFO không trực tiếp subscribe Lambda; phải đi qua SQS.

### 4.4. HTTPS — webhook có xác thực

SNS gửi HTTP POST tới HTTPS endpoint với `Type=SubscriptionConfirmation`, `Notification` hoặc `UnsubscribeConfirmation`.

Những kiểm soát tối thiểu:

1. Xác minh **SNS message signature** bằng SDK hoặc quy trình AWS công bố (ưu tiên SignatureVersion 2/SHA-256 khi phù hợp).
2. Kiểm tra `TopicArn` nằm trong danh sách tin cậy và certificate URL thực sự thuộc SNS trên HTTPS.
3. Chống SSRF khi tải `SigningCertURL` và xác nhận subscription.
4. Xác thực quyền nghiệp vụ bổ sung nếu cần; HTTPS **không thay thế** signature.
5. Ghi event một cách **durable** trước khi trả 2xx; không nhận xong rồi crash trước khi lưu.
6. Xử lý duplicates bằng business eventId.
7. Dùng queue/worker để không làm việc nặng trong request webhook.

SNS xem HTTP(S) **5xx và 429** là lỗi có thể retry theo delivery policy; phần lớn 4xx khác được xem là lỗi permanent. Đừng dựa vào HTTP endpoint tự mở rộng vô hạn khi SNS đang retry.

### 4.5. Email và email-json

Cả `email` và `email-json` cần xác nhận mailbox; chỉ phù hợp khi nội dung được phép gửi qua hệ thống email:

- `email`: nội dung thân thiện cho người đọc, ví dụ alarm đơn giản.
- `email-json`: thư có notification JSON để người/hệ thống xử lý sau.

**Không coi SNS email là transactional email service đầy đủ.** Nếu cần template, bounce/complaint handling, unsubscribe compliance, chiến dịch hoặc deliverability metrics, cân nhắc **Amazon SES** hoặc dịch vụ chuyên biệt.

### 4.6. SMS

Với `sms`, SNS giao nội dung ngắn đến số điện thoại. Phải xem **SMS sandbox**, consent, opt-in/opt-out, origination identity, sender ID, registration và quy định theo quốc gia. Giá phụ thuộc quốc gia và số đoạn SMS; payload UTF-8 Unicode có thể làm tăng số đoạn tính phí.

Không đẩy PII/token dài hoặc bí mật vào SMS theo kiểu fan-out tùy ý. SMS được “delivered” không đồng nghĩa người nhận đã đọc.

### 4.7. Mobile push — application

`application` subscription dùng **platform endpoint ARN** đại diện thiết bị/app, SNS chuyển push qua APNs/FCM theo platform credentials.

Các việc phải quản trị: token hết hạn/thay đổi, endpoint disabled, credentials rotation, push format theo nền tảng, phản hồi lỗi, số thiết bị/đăng ký và data minimization. Push có thể xuất hiện trên màn hình khóa, không chứa thông tin nhạy cảm.

### 4.8. Amazon Data Firehose

`firehose` subscription chuyển events tới **Amazon Data Firehose** để lưu vào S3/data lake hoặc downstream đích theo stream configuration. Cần `SubscriptionRoleArn` với IAM policy phù hợp, monitoring failures/buffering, schema/cost và encryption.

Ví dụ:

~~~text
SNS orders-events → Firehose → S3 analytics bucket → Athena
~~~

Không gửi toàn bộ thông tin khách hàng nếu analytics chỉ cần aggregated/pseudonymized fields.

## 5. Message body, attributes và raw delivery

### 5.1. Event schema

Một event có thể mang:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-2026-001",
  "eventType": "order.created",
  "occurredAt": "2026-11-20T09:00:00Z",
  "orderId": "order-123",
  "tenantId": "shop-7",
  "amount": 250000,
  "currency": "VND"
}
~~~

Dùng `eventId` và `schemaVersion` cho dedup/compatibility; không gửi full payment card, access token hoặc secret. Các IDs/amount vẫn có thể nhạy cảm trong hệ thống, nên phân loại và kiểm soát người nhận.

### 5.2. Message attributes

SNS hỗ trợ attributes, ví dụ:

~~~json
{
  "eventType": {
    "DataType": "String",
    "StringValue": "order.created"
  },
  "channel": {
    "DataType": "String",
    "StringValue": "fulfillment"
  },
  "priority": {
    "DataType": "Number",
    "StringValue": "2"
  }
}
~~~

Một số data types gồm String, String.Array, Number, Binary. Với Number, giá trị truyền qua `StringValue` của API. Attribute names case-sensitive: `eventType` khác `EventType`. Đây là metadata phục vụ filtering, không phải chứng cứ xác thực của producer.

### 5.3. SNS JSON envelope mặc định

Khi subscription SQS có `RawMessageDelivery=false`, SQS body thông thường chứa SNS JSON wrapper:

~~~json
{
  "Type": "Notification",
  "MessageId": "sns-message-id-placeholder",
  "TopicArn": "arn:aws:sns:ap-southeast-1:111122223333:orders-events",
  "Subject": "order.created",
  "Message": "{\"eventId\":\"evt-2026-001\",\"orderId\":\"order-123\"}",
  "Timestamp": "2026-11-20T09:00:00.000Z",
  "SignatureVersion": "2",
  "Signature": "EXAMPLE",
  "SigningCertURL": "https://sns.ap-southeast-1.amazonaws.com/EXAMPLE.pem"
}
~~~

JSON này **chỉ minh họa**, không có chữ ký hợp lệ. Consumer SQS cần parse **SQS body → SNS envelope → JSON trong field Message**.

### 5.4. RawMessageDelivery

| Endpoint | Raw=false | Raw=true |
|---|---|---|
| SQS | SNS envelope chứa message | **SQS body là original message** |
| HTTP(S) | SNS JSON notification | Payload gốc và header raw delivery |
| Firehose | SNS form theo cấu hình | Payload gốc theo hỗ trợ |
| Lambda | Cơ chế SNS Lambda event envelope | Không sử dụng raw option như SQS |
| Email/SMS | Delivery theo protocol | Không áp raw option như SQS |

Với **SQS subscription RawMessageDelivery=true**, SNS hỗ trợ tối đa **10 message attributes**. Nếu message có hơn 10 attributes, SNS có thể **discard delivery cho subscription đó như client-side error**. Hãy chọn schema vừa đủ, theo dõi failed deliveries, hoặc tắt raw nếu cần nhiều attributes.

Khi bật/tắt raw, **consumer parser phải đổi**. Messages đang có trong queue có thể có format cũ, vì vậy rollout nên hỗ trợ hai formats trong cửa sổ chuyển đổi.

### 5.5. Protocol-specific payload

SNS `Publish` với `MessageStructure=json` cho phép nội dung khác theo protocol:

~~~json
{
  "default": "Order 123 created",
  "email": "Đơn hàng 123 đã được tạo.",
  "sms": "Don 123 da duoc tao.",
  "sqs": "{\"eventId\":\"evt-2026-001\",\"orderId\":\"order-123\"}"
}
~~~

Mỗi protocol value phải là **JSON string** theo API SNS. Kiểm tra parser và quota, tránh gửi dữ liệu bí mật vào nhánh email/SMS.

## 6. Subscription filter policies

### 6.1. Mặc định fan-out toàn bộ

Nếu không có filter policy, một subscription nhận mọi message theo các điều kiện delivery. Nếu có filter, SNS chỉ giao message **khớp**.

~~~mermaid
flowchart TD
    P[Publish event] --> T[(SNS Topic)]
    T --> A{Filter eventType=order.created?}
    T --> B{Filter eventType=payment.received?}
    T --> C[Không filter]
    A -->|true| Q1[SQS inventory]
    B -->|true| Q2[SQS billing]
    C --> Q3[SQS analytics]
~~~

### 6.2. MessageAttributes mặc định

Filter policy:

~~~json
{
  "eventType": ["order.created", "order.updated"],
  "channel": ["fulfillment"]
}
~~~

Logic:

~~~text
(eventType = order.created OR order.updated)
AND (channel = fulfillment)
~~~

Các filter có operators như numeric ranges, prefix, anything-but và existence. Nếu message thiếu `channel`, filter trên không khớp. Cần kiểm tra data types và JSON syntax; đừng gửi tên attribute sai chữ hoa/thường.

### 6.3. MessageBody

Nếu producer chỉ có body JSON, dùng:

~~~text
FilterPolicyScope = MessageBody
~~~

và policy ví dụ:

~~~json
{
  "eventType": ["order.created"],
  "metadata": {
    "region": ["ap-southeast-1"]
  }
}
~~~

Payload phải là JSON object hợp lệ với field/type phù hợp. Nested filter trong body khác với filter attributes. **Đừng nhầm filterPolicy với kiểm soát truy cập:** một endpoint không đáng tin không được subscribe vào topic chứa payload bí mật chỉ vì filter hiện tại không khớp.

### 6.4. Eventual consistency

Theo AWS, thay đổi filter policy có thể mất **tới 15 phút** để áp dụng đầy đủ. Vì vậy, khi rollout event types mới, cân nhắc publish cả hai phiên bản trong cửa sổ tương thích và theo dõi filtering metrics, thay vì thay policy rồi lập tức dựa vào đó để kiểm soát giao dịch.

### 6.5. Ma trận kiểm thử filter

| Attributes của message | Inventory filter | Billing filter | Analytics no filter |
|---|---|---|---|
| `eventType=order.created`, `channel=fulfillment` | Nhận | Không | Nhận |
| `eventType=payment.received`, `channel=finance` | Không | Nhận | Nhận |
| Thiếu `eventType` | Không | Không | Nhận |
| Key `EventType` thay `eventType` | Không | Không | Nhận |

## 7. Retry tại SNS khác retry ở consumer

### 7.1. Delivery retry

| Protocol | Một số lỗi | Cơ chế cần theo dõi |
|---|---|---|
| HTTP(S) | 429, 5xx, timeout | SNS DeliveryPolicy/backoff |
| SQS | Queue denied, deleted, service error | SNS managed retry, queue policy/KMS |
| Lambda | Permission denied, function missing | SNS retry giao đến Lambda |
| Email/SMS/mobile | Delivery endpoint lỗi | SNS managed retry theo protocol |
| Firehose | IAM/stream unavailable | SNS delivery/retry, feedback logs |

Với HTTP(S), SNS hỗ trợ `DeliveryPolicy` có no-delay/pre-backoff/backoff/post-backoff và `maxReceivesPerSecond` trung bình. Không coi cấu hình này là rate limit cứng: bursts vẫn có thể xảy ra. Thiết kế webhook nên kiểm tra chữ ký, **ghi bền vững** vào queue/storage, trả 2xx nhanh; consumer làm việc lâu ở phía sau.

### 7.2. Hai cấp retry

~~~text
SNS Standard topic
  -> SQS queue: SNS delivery thành công
     -> worker xử lý lỗi, không delete message
        -> SQS visibility timeout
        -> SQS source-queue DLQ nếu đạt maxReceiveCount

SNS Standard topic
  -> SQS queue: SNS delivery thất bại do queue policy
     -> SNS retry rồi SNS subscription DLQ nếu có
~~~

Tương tự với Lambda, SNS delivery success chỉ nghĩa Lambda **đã nhận lời gọi async**. Nếu handler lỗi sau đó, xem **Lambda async retries/OnFailure destination/Lambda DLQ**, không cấu hình SNS HTTP delivery policy để sửa.

## 8. SNS subscription DLQ và SQS consumer DLQ

### 8.1. DLQ gắn ở mức subscription

SNS subscription có `RedrivePolicy`:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:orders-delivery-dlq"
}
~~~

SNS dùng queue đó khi **không thể giao notification tới endpoint** theo retry semantics. DLQ cần thuộc **cùng account và Region với SNS subscription**, với Standard subscriptions dùng Standard DLQ; FIFO topic subscriptions dùng FIFO DLQ theo hướng dẫn.

SQS DLQ phải cho phép SNS `sqs:SendMessage` từ đúng topic ARN. Với encrypted queue, cần KMS key policy thích hợp.

### 8.2. Ba tình huống dễ nhầm

| Hiện tượng | Nơi tìm event thất bại |
|---|---|
| SNS không gửi được đến SQS vì queue policy sai | **SNS subscription DLQ** |
| SQS đã nhận, worker throw nhiều lần | **SQS source-queue DLQ** |
| SNS không invoke được Lambda | **SNS subscription DLQ** |
| Lambda accepted event nhưng handler timeout | **Lambda OnFailure destination hoặc Lambda DLQ** |
| Webhook HTTP(S) lỗi sau hết retries | **SNS subscription DLQ** |
| Email được giao nhưng người dùng chưa mở | Không tự có DLQ vì “chưa đọc” |

Các lớp DLQ có **khác owner và khác runbook**. Mỗi queue phải có retention, alarm, encryption, người phụ trách điều tra và quy trình replay có idempotency.

### 8.3. SQS DLQ retention và metrics

SNS subscription DLQ chỉ là SQS queue đặc biệt về **mục đích sử dụng**. Dùng SQS retention phù hợp, thường cân nhắc tối đa 14 ngày khi cần thời gian điều tra. Không mặc định một DLQ có retention vô hạn.

Theo AWS, `ApproximateNumberOfMessagesVisible` là metric phù hợp để nhận biết DLQ backlog. Không chỉ dựa trên `NumberOfMessagesSent` của SQS để đếm mọi message được redrive tự động.

## 9. IAM và bảo mật end-to-end

### 9.1. Ba lớp quyền với SNS → SQS

1. **Producer identity policy:** được gọi `sns:Publish` tới topic.
2. **SNS topic access policy:** cho phép đúng principal/accounts publish/subscribe/modify.
3. **SQS queue resource policy:** SNS service principal được phép `sqs:SendMessage` từ đúng `aws:SourceArn`.

Với SSE-KMS, **KMS key policy** và permissions cũng phải cho phép dịch vụ theo cơ chế encryption.

### 9.2. IAM policy publisher

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "arn:aws:sns:ap-southeast-1:111122223333:orders-events"
    }
  ]
}
~~~

Nên cấp IAM role cho Lambda/EC2/ECS workloads thay vì nhúng AWS access keys vào source code.

### 9.3. SQS queue policy

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOneSnsTopic",
      "Effect": "Allow",
      "Principal": {"Service": "sns.amazonaws.com"},
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:inventory-events",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:orders-events"
        }
      }
    }
  ]
}
~~~

`aws:SourceArn` giúp hạn chế confused-deputy risks. Không mở queue `Principal:"*"` hoặc cho mọi topic gửi chỉ để tránh AccessDenied.

### 9.4. Lambda permission

Lambda subscription cần resource permission cho SNS:

~~~bash
# CHỈ MINH HỌA - chỉ dùng function sandbox khi được duyệt
aws lambda add-permission \
  --function-name aws-lab-notification-worker \
  --statement-id AllowOrdersTopic \
  --action lambda:InvokeFunction \
  --principal sns.amazonaws.com \
  --source-arn arn:aws:sns:ap-southeast-1:111122223333:orders-events \
  --region ap-southeast-1
~~~

### 9.5. Cross-account, encryption và PrivateLink

Cross-account SQS subscriptions cần **topic policy và queue policy** từ hai phía; nếu encrypted, cần **KMS key policy** phù hợp. Với SNS publisher trong VPC private, có thể dùng **SNS interface VPC endpoint/PrivateLink** theo Region/tính năng, nhưng endpoint này chỉ giải quyết đường **producer → SNS API**. Nó không tự chuyển webhook HTTP(S) sang private network, cũng không thay thế IAM.

Phân tách topic theo **trust boundary**. Subscription filter **không thay được quyền truy cập**; không để một principal ngoài tổ chức subscribe vào topic chứa PII chỉ vì filter hiện tại chưa gửi dữ liệu đó.

## 10. SNS message size và quota năm 2026

### 10.1. Cập nhật AWS tháng 9/2026

AWS công bố ngày **18/09/2026**: SNS có thể chấp nhận messages đến **1 MiB** khi cấu hình `MaximumMessageSize` trên topic.

| Thuộc tính | Giá trị |
|---|---|
| Mặc định | **256 KiB (262.144 bytes)** |
| Tối đa cấu hình | **1 MiB (1.048.576 bytes)** |
| Tên thuộc tính | `MaximumMessageSize` |
| Khi >256 KiB | Chỉ **SQS, Lambda, Data Firehose** subscriptions; không quá **100 subscriptions/topic** |
| Khi ≤256 KiB | Các protocol khác như HTTPS/email/SMS/mobile có thể được hỗ trợ theo topic type |
| Tính kích thước | Body và message attributes được kiểm tra so với configured maximum |

**Giới hạn của FIFO không đổi:** FIFO topic chỉ giao trực tiếp tới SQS, dù `MaximumMessageSize` có thể tăng.

### 10.2. Có nên gửi payload lớn?

Payload lớn có thể tăng phí publish/delivery, thời gian xử lý, log size, rủi ro PII và DLQ storage. Thông thường nên phát **event metadata + reference tới S3**:

~~~json
{
  "eventType": "report.ready",
  "eventId": "evt-report-123",
  "reportId": "report-123",
  "s3Bucket": "private-report-bucket",
  "s3Key": "reports/report-123.json",
  "versionId": "s3-version-example"
}
~~~

Consumer dùng IAM để đọc object private, đúng version, có encryption và retention. Không gửi thông tin thanh toán hoặc token trong SNS chỉ vì message size đã lớn hơn.

### 10.3. Chi phí

Chi phí có thể gồm SNS requests (kích thước message ảnh hưởng đơn vị tính), deliveries theo protocol, SQS requests/DLQ, Lambda invokes/duration, Firehose ingestion, SMS/viễn thông theo quốc gia, KMS requests, CloudWatch và network. Một message gửi tới 10 subscriptions có thể tạo **10 deliveries** và downstream costs; cần lọc các nhánh không cần thiết và theo dõi ngân sách.


## 11. Thực hành 1 — Kiểm tra SNS bằng AWS CLI (chỉ đọc)

> Phần này không tạo hoặc thay đổi tài nguyên. Cần AWS CLI v2, account/Region sandbox và quyền như `sns:ListTopics`, `sns:GetTopicAttributes`, `sns:ListSubscriptionsByTopic`, `sns:GetSubscriptionAttributes`. Không đọc message của SQS queue dùng chung.

### 11.1. Xác minh danh tính

Bash/AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1
REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

Nếu CloudShell đã có IAM credentials và không có profile này, bỏ biến `AWS_PROFILE` và các tham số `--profile`. Kiểm tra `Account` và `Arn` để tránh thao tác sai môi trường.

### 11.2. Liệt kê topics

~~~bash
aws sns list-topics \
  --region "$REGION" \
  --query 'Topics[].TopicArn' \
  --output table
~~~

Kết quả có thể rỗng vì Region/account hoặc quyền. Dùng pagination của AWS CLI khi cần; không tạo production topic chỉ để làm bài.

### 11.3. Đọc topic attributes

~~~bash
TOPIC_ARN="arn:aws:sns:ap-southeast-1:111122223333:orders-events"

aws sns get-topic-attributes \
  --topic-arn "$TOPIC_ARN" \
  --region "$REGION" \
  --query 'Attributes.{FifoTopic:FifoTopic,ContentBasedDeduplication:ContentBasedDeduplication,MaximumMessageSize:MaximumMessageSize,SubscriptionsConfirmed:SubscriptionsConfirmed,SubscriptionsPending:SubscriptionsPending,KmsMasterKeyId:KmsMasterKeyId}' \
  --output json
~~~

Các ARN đều **giả định**. Xác định loại topic, max message size, lượng subscriptions confirmed/pending và encryption. Tránh in toàn bộ topic resource policy ra log công khai nếu chứa role/account metadata nội bộ.

### 11.4. Liệt kê subscriptions

~~~bash
aws sns list-subscriptions-by-topic \
  --topic-arn "$TOPIC_ARN" \
  --region "$REGION" \
  --query 'Subscriptions[].{Protocol:Protocol,SubscriptionArn:SubscriptionArn}' \
  --output table
~~~

Chủ ý bỏ field `Endpoint` khỏi output vì có thể chứa email, số điện thoại, webhook URL hoặc resource ARN nội bộ. Nếu có `PendingConfirmation`, subscriber phải xác nhận qua kênh an toàn.

Đọc attributes của một subscription đã confirmed:

~~~bash
SUB_ARN="arn:aws:sns:ap-southeast-1:111122223333:orders-events:550e8400-e29b-41d4-a716-446655440000"

aws sns get-subscription-attributes \
  --subscription-arn "$SUB_ARN" \
  --region "$REGION" \
  --query 'Attributes.{Protocol:Protocol,Raw:RawMessageDelivery,FilterScope:FilterPolicyScope,Filter:FilterPolicy,Redrive:RedrivePolicy,DeliveryPolicy:DeliveryPolicy}' \
  --output json
~~~

**Phân tích:** subscription có filter policy không? `FilterPolicyScope` là `MessageAttributes` hay `MessageBody`? `RawMessageDelivery` có phù hợp parser không? Có DLQ ở `RedrivePolicy` chưa?

### 11.5. Xem SQS queue metadata

~~~bash
QUEUE_URL="https://sqs.ap-southeast-1.amazonaws.com/111122223333/inventory-events"

aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names QueueArn RedrivePolicy KmsMasterKeyId \
  --region "$REGION" \
  --output json
~~~

Nếu cần kiểm tra queue resource policy, dùng `get-queue-attributes --attribute-names Policy` theo quyền được cấp và **không đăng policy chứa nội dung nội bộ công khai**. Xem SQS DLQ của consumer có khác SNS subscription DLQ không.

**Không gọi `ReceiveMessage` trên queue production**: việc nhận làm message temporarily invisible và có thể ảnh hưởng worker thật.

## 12. Thực hành 2 — SNS Standard → SQS Standard (sandbox tùy chọn)

> Phần này **có tác động và có thể tính phí**. Chỉ làm trong account sandbox, tài nguyên do bạn sở hữu, có quyền và approval. Không subscribe email/phone/HTTPS endpoint của người khác. Có thể hoàn thành bài bằng cách phân tích IaC mà không chạy.

### 12.1. Mô hình

~~~text
SNS Standard topic: aws-lab-orders-events
    |
    | Subscription protocol=sqs
    v
SQS Standard queue: aws-lab-inventory-events
    |
    v
Consumer test
~~~

Các bước:

1. Tạo topic và queue sandbox riêng.
2. Đặt queue policy cho phép `sns.amazonaws.com` với `aws:SourceArn` là topic ARN.
3. Subscribe queue ARN vào topic.
4. Đặt filter `eventType=order.created`.
5. Publish message test có attributes.
6. Xem SQS message body/wrapper trong queue lab.
7. Dọn topic, queue, subscription bằng IaC sau khi không còn dữ liệu cần giữ.

### 12.2. CloudFormation template tham khảo

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: SNS Standard to SQS Standard lab, sandbox only

Resources:
  EventsTopic:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: aws-lab-orders-events

  InventoryQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: aws-lab-inventory-events

  InventoryQueuePolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues:
        - !Ref InventoryQueue
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: AllowOnlyEventsTopic
            Effect: Allow
            Principal:
              Service: sns.amazonaws.com
            Action: sqs:SendMessage
            Resource: !GetAtt InventoryQueue.Arn
            Condition:
              ArnEquals:
                aws:SourceArn: !Ref EventsTopic

  InventorySubscription:
    Type: AWS::SNS::Subscription
    DependsOn: InventoryQueuePolicy
    Properties:
      TopicArn: !Ref EventsTopic
      Protocol: sqs
      Endpoint: !GetAtt InventoryQueue.Arn
      RawMessageDelivery: false
      FilterPolicy:
        eventType:
          - order.created

Outputs:
  TopicArn:
    Value: !Ref EventsTopic
  QueueUrl:
    Value: !Ref InventoryQueue
~~~

Đây là cấu hình **đào tạo tối giản**. Production cần cân nhắc SNS/SQS SSE-KMS, subscription DLQ, metrics/alarms, resource tags, queue retention, quyền triển khai và quotas. Dùng tên stack/resource riêng nếu môi trường có nhiều người học. Không áp lên tài nguyên có sẵn hay dùng chung.

### 12.3. Đọc stack và publish test message

Giả sử stack đã được tạo qua quy trình được duyệt:

~~~bash
STACK="aws-lab-sns-sqs"

aws cloudformation describe-stacks \
  --stack-name "$STACK" \
  --region "$REGION" \
  --query 'Stacks[].{Status:StackStatus,Outputs:Outputs}' \
  --output json
~~~

Lấy topic ARN và queue URL từ Outputs, thay cho placeholder dưới đây:

~~~bash
TOPIC_ARN="arn:aws:sns:ap-southeast-1:111122223333:aws-lab-orders-events"

aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"schemaVersion":1,"eventId":"training-001","eventType":"order.created","orderId":"test-123"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"order.created"}}' \
  --region "$REGION"
~~~

Nếu vừa cấu hình filter, cần xem xét **eventual consistency tới 15 phút** trước khi đánh giá thành công/thất bại.

### 12.4. Quan sát message trên queue lab

~~~bash
QUEUE_URL="https://sqs.ap-southeast-1.amazonaws.com/111122223333/aws-lab-inventory-events"

aws sqs receive-message \
  --queue-url "$QUEUE_URL" \
  --max-number-of-messages 1 \
  --wait-time-seconds 5 \
  --message-attribute-names All \
  --region "$REGION" \
  --output json
~~~

**Lệnh này thay đổi visibility** và chỉ được dùng với queue riêng của lab. Với `RawMessageDelivery=false`, SQS body chứa SNS JSON envelope; `Message` trong đó là chuỗi JSON order gốc.

Nếu chuyển raw=true, consumer nhận body trực tiếp và phải đổi parser:

~~~bash
SUB_ARN="arn:aws:sns:ap-southeast-1:111122223333:aws-lab-orders-events:subscription-id-placeholder"

aws sns set-subscription-attributes \
  --subscription-arn "$SUB_ARN" \
  --attribute-name RawMessageDelivery \
  --attribute-value true \
  --region "$REGION"
~~~

Không đổi raw mode trên subscription production nếu chưa có kế hoạch tương thích message cũ/mới.

### 12.5. Dọn sandbox

Chỉ xóa stack do bạn sở hữu khi đã kiểm tra không có message/tài nguyên dùng chung:

~~~bash
# CÓ TÁC ĐỘNG: chỉ chạy khi được phép
aws cloudformation delete-stack \
  --stack-name "$STACK" \
  --region "$REGION"
~~~

Sau đó kiểm tra stack status và SNS/SQS resource còn tồn tại, cùng phí KMS/CloudWatch/NAT nếu lab tạo thêm. Không xóa queue có dữ liệu nghiệp vụ.

## 13. HTTPS subscription: xác thực và phản hồi an toàn

### 13.1. Ba message types

Một HTTPS endpoint có thể nhận:

- `SubscriptionConfirmation`: cần xác nhận endpoint thuộc quyền kiểm soát.
- `Notification`: nội dung message thực sự.
- `UnsubscribeConfirmation`: thông báo hủy subscription.

JSON ví dụ **không có chữ ký hợp lệ**:

~~~json
{
  "Type": "SubscriptionConfirmation",
  "MessageId": "placeholder-message-id",
  "TopicArn": "arn:aws:sns:ap-southeast-1:111122223333:orders-events",
  "Token": "placeholder",
  "SubscribeURL": "https://sns.ap-southeast-1.amazonaws.com/?Action=ConfirmSubscription&...",
  "Timestamp": "2026-11-20T09:00:00.000Z",
  "SignatureVersion": "2",
  "Signature": "EXAMPLE",
  "SigningCertURL": "https://sns.ap-southeast-1.amazonaws.com/EXAMPLE.pem"
}
~~~

### 13.2. Runbook HTTP webhook

~~~text
POST received
  |
  | 1. Giới hạn body size, validate JSON.
  | 2. Verify SNS signature và TopicArn tin cậy.
  | 3. Verify certificate URL/chain, chống SSRF.
  |
  +-- SubscriptionConfirmation -> chỉ confirm topic đã duyệt
  |
  +-- Notification -> validate eventId + schema
  |                   ghi event bền vững vào queue/DB
  |                   trả 2xx sau commit
  |
  +-- UnsubscribeConfirmation -> audit/sửa quy trình nhận
~~~

Không chỉ tin `User-Agent` hoặc một IP nguồn. AWS khuyến nghị verify cryptographic signature; với `SignatureVersion=2` sử dụng SHA-256 theo quy tắc SNS. Không tự theo một URL certificate do payload giả mạo cung cấp mà chưa kiểm tra hostname/trust.

**Webhook trả 200 trước khi commit có thể mất message:** SNS xem delivery thành công nhưng process có thể crash trước khi ghi vào hệ thống nội bộ. Khi không thể giữ event, trả status có thể retry theo chính sách, tránh nuốt lỗi.

## 14. Giám sát SNS và downstream

### 14.1. Metrics quan trọng

| Metric/tín hiệu | Nguồn | Câu hỏi |
|---|---|---|
| `NumberOfMessagesPublished` | SNS | Bao nhiêu messages vào topic? |
| `NumberOfNotificationsDelivered` | SNS | SNS giao thành công tới endpoints? |
| `NumberOfNotificationsFailed` | SNS | Có delivery thất bại? |
| `NumberOfNotificationsFilteredOut` | SNS | Có bị filter nhiều bất thường? |
| `NumberOfNotificationsRedrivenToDlq` | SNS | Có event phải chuyển SNS DLQ? |
| `ApproximateNumberOfMessagesVisible` | SQS | Backlog/DLQ đang tăng? |
| `ApproximateAgeOfOldestMessage` | SQS | Độ trễ xử lý cao? |
| `Errors`, `Throttles`, `AsyncEventsDropped` | Lambda | Handler/async queue lỗi? |
| 4xx/5xx, request duration | HTTPS endpoint | Webhook chậm hoặc từ chối? |
| Firehose delivery metrics | Firehose | Analytics có lưu thành công? |

Metrics availability, dimensions và costs có thể thay đổi theo configuration. **SNS `Delivered` không chứng minh business consumer commit**.

### 14.2. Delivery status logging

SNS có thể tích hợp **CloudWatch Logs** để ghi delivery status cho các protocols được hỗ trợ khi có feedback roles/configuration. Chỉ log dữ liệu tối thiểu, che PII và có retention phù hợp. Thiết lập alerts cho failed deliveries và DLQ age; dashboard không thay thế on-call owner.

### 14.3. Runbook sự cố

~~~text
1. Xác nhận account, Region, TopicArn, MessageId.
2. Topic Standard/FIFO? Protocol có được hỗ trợ?
3. Subscription Confirmed hay PendingConfirmation?
4. FilterPolicyScope và attributes/body khớp không?
5. SNS Published / FilteredOut / Delivered / Failed?
6. Queue/Lambda/Firehose: policy, ARN, Region, KMS?
7. HTTPS: chữ ký, certificate, TopicArn, HTTP status, latency?
8. Nếu SNS delivered, kiểm tra consumer SQS/Lambda processing và DLQ.
9. Đối soát business eventId, side effect đã commit chưa?
10. Sửa đúng lớp lỗi, replay có kiểm soát và ghi audit.
~~~

## 15. Idempotency, event contract và outbox

### 15.1. At-least-once khác exactly-once

Một SQS worker có thể xử lý đơn hàng thành công nhưng crash trước khi `DeleteMessage`. Message xuất hiện trở lại sau visibility timeout và được xử lý lần hai. Giải pháp là idempotency:

~~~text
operationId = order-123:reserve-inventory

if operationId already COMPLETED:
    acknowledge without side effect
else:
    atomic claim in DynamoDB/DB
    execute inventory operation
    mark completed transactionally
    acknowledge message
~~~

Không dùng `Lambda awsRequestId` làm business key nếu mỗi attempt tạo ID mới. `SNS MessageId` cũng có thể khác khi producer publish lại cùng business event. Cần `eventId`/operationId ổn định từ producer.

### 15.2. Transactional outbox

Nguy cơ:

~~~text
Order database commit thành công
Process crash trước khi Publish SNS
=> không consumer nào được thông báo
~~~

Mẫu outbox:

~~~mermaid
flowchart LR
    API[Order API] --> TX[Database transaction]
    TX --> ORD[(Order table)]
    TX --> OUT[(Outbox table)]
    OUT --> PUB[Publisher / CDC]
    PUB --> SNS[(SNS topic)]
    SNS --> SQS[SQS queues]
~~~

Order và outbox record được commit cùng transaction theo khả năng DB. Publisher có thể publish trùng nếu crash trước khi mark dispatched, nên consumer vẫn phải idempotent.

### 15.3. Replay an toàn

Đừng redrive mọi message DLQ trở lại topic mà không phân tích. Có thể gây fan-out toàn bộ lần hai và double charge. Trước replay:

1. Xác định subscription/consumer nào lỗi và nguyên nhân đã được sửa chưa.
2. Đối chiếu business state bằng stable event ID.
3. Kiểm tra schema version và thời hạn hợp lệ.
4. Chọn đích replay đúng, không phát toàn topic khi không cần.
5. Giới hạn tốc độ và theo dõi duplicate/side effects.
6. Ghi audit và dọn DLQ sau xác nhận.

## 16. Chi phí, giới hạn và phân loại dữ liệu

| Thành phần | Chi phí cần tính |
|---|---|
| SNS | Publish và deliveries, kích thước message/chunks |
| SQS | Queue requests, retention, DLQ, consumers |
| Lambda | Invocation, duration, memory, retries |
| HTTP(S)/mobile | Hạ tầng nhận, traffic, retry và vendor fees |
| SMS | Quốc gia, sender registration, message segments, opt-in |
| Firehose/S3 | Streaming ingest, storage, transform và queries |
| KMS | Key/requests theo configuration |
| CloudWatch | Metrics, logs, alarms, retention |
| Networking | VPC endpoints, data transfer theo kiến trúc |

Một message gửi tới 8 subscribers không chỉ tính như một thông báo đơn độc. Chỉ dùng filter để giảm delivery không cần, **không loại message phải xử lý** để tiết kiệm.

**Không đưa secrets, access tokens, payment card details hoặc PII không cần thiết** vào topic rộng; emails, webhooks, analytics và CloudWatch logs có các trust boundaries riêng. Nếu dữ liệu quá lớn, dùng S3 private object + reference event với IAM/KMS phù hợp.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Publish trả MessageId nhưng SQS rỗng | Filter mismatch, policy, sai ARN hoặc subscription chưa tồn tại | `ListSubscriptionsByTopic`, filter, SNS metrics |
| Subscription PendingConfirmation | Chưa được chủ endpoint xác nhận | Email/HTTPS confirmation workflow |
| AccessDenied khi publish | Producer IAM, topic policy, SCP hoặc KMS | Principal, Resource, Conditions |
| SQS không nhận | Queue policy thiếu `sns.amazonaws.com`/`SourceArn` | Resource policy, KMS |
| Lambda không được invoke | Lambda resource policy thiếu permission | `lambda:InvokeFunction` SourceArn |
| SNS delivered nhưng Lambda báo Errors | Handler lỗi sau khi nhận | Lambda logs, async retry/destinations |
| HTTPS 403 | Signature/TopicArn/app policy sai | Signature verification, HTTP logs |
| HTTPS 429/5xx | Quá tải/outage | DeliveryPolicy, queue ingress, scaling |
| Email không tới | Pending, spam, quyền mailbox | Subscription status, email route |
| SMS không đến | Sender registration/sandbox/consent | SMS settings, Region, phí |
| Raw mode khiến parser lỗi | Consumer kỳ vọng SNS envelope | Hỗ trợ body trực tiếp và old format |
| Raw SQS mất message | Message >10 attributes | Giảm attrs/tắt raw, alert failures |
| FIFO topic không subscribe Lambda | FIFO trực tiếp chỉ SQS | SQS FIFO/Standard trung gian |
| FIFO → SQS Standard mất thứ tự | Queue standard best effort | Dùng FIFO queue nếu strict order |
| Filter mới chưa có tác dụng | Eventual consistency đến 15 phút | Đợi và test có correlation |
| DLQ SNS rỗng dù worker lỗi | Delivery thành công, processing lỗi | SQS consumer DLQ |
| Message vượt kích thước | MaximumMessageSize chưa nâng/không tương thích | Body+attributes, protocol, 1 MiB limit |
| Duplicated side effects | Retry/replay/at-least-once | Business idempotency |
| Chi phí tăng | Fan-out, retries, SMS, logging | Cost Explorer/Budgets |
| DLQ tồn lâu | Không có owner/runbook | Alarms, retry/replay workflow |

## 18. Bài tập ứng dụng

### 18.1. Bối cảnh

Một nền tảng học trực tuyến có:

- `enrollment.created`: cần gửi email và cấp quyền học.
- `payment.received`: cần kế toán xử lý đúng thứ tự theo `enrollmentId`.
- Analytics lưu mọi event nhưng **không nhận token/PII**.
- Nếu email worker ngừng 30 phút, không được mất jobs.
- Người học có thể bấm đăng ký hai lần, nhưng không được charge hai lần.

### 18.2. Thiết kế tham khảo

~~~mermaid
flowchart TD
    API[Enrollment API] --> DB[(DB + Outbox)]
    DB --> PUB[Outbox publisher]
    PUB --> STD[(SNS Standard)]
    PUB --> FIFO[(SNS FIFO finance)]
    STD -->|filter enrollment.created| SQ1[SQS notification]
    STD -->|sanitized events| FH[Firehose -> S3]
    FIFO -->|group=enrollmentId| SQF[SQS FIFO finance]
    SQ1 --> W1[Notification worker]
    SQF --> W2[Finance worker]
    SQ1 -. processing fail .-> DLQ1[SQS consumer DLQ]
    STD -. delivery fail .-> DLQ2[SNS subscription DLQ]
~~~

Vì cần email template và durable backlog, nên để SNS giao SQS queue rồi notification worker dùng dịch vụ gửi email phù hợp. Finance FIFO dùng MessageGroupId theo enrollmentId; idempotency vẫn kiểm tra business operation ID.

### 18.3. Câu hỏi tự kiểm tra

1. Topic, subscription và endpoint khác nhau ra sao?
2. `Publish` trả MessageId có nghĩa mọi consumer đã thành công chưa?
3. Vì sao SNS Standard không bảo đảm strict ordering?
4. SNS FIFO có direct subscription tới Lambda/HTTPS/email không?
5. Nếu Lambda cần xử lý FIFO, kiến trúc nào phù hợp?
6. Mặc định `FilterPolicyScope` là gì?
7. Filter theo MessageBody đòi message body định dạng nào?
8. Nếu thiếu `eventType`, filter cần field này có nhận message không?
9. Vì sao filter không thay thế tenant authorization?
10. RawMessageDelivery thay SQS body ra sao?
11. Vì sao raw SQS >10 attributes nguy hiểm?
12. HTTPS webhook xác minh SNS bằng gì?
13. Khi webhook trả HTTP 200 trước khi commit, điều gì có thể xảy ra?
14. Subscription PendingConfirmation có nhận notification thường chưa?
15. SNS subscription DLQ và SQS source queue DLQ khác nhau thế nào?
16. Khi SNS delivered Lambda nhưng handler throw, retry thuộc dịch vụ nào?
17. IAM publisher có tự cho phép SNS ghi vào SQS không?
18. FIFO → SQS Standard có giữ strict order không?
19. 2026 SNS mặc định và tối đa kích thước message là bao nhiêu?
20. Tại sao cần business idempotency key và outbox?

**Đáp án gợi ý:** 1. Topic phát, subscription liên kết, endpoint nhận. 2. Chưa. 3. Best-effort ordering/at-least-once. 4. Không, FIFO trực tiếp chỉ tới SQS. 5. SNS FIFO → SQS → Lambda ESM. 6. MessageAttributes. 7. JSON object hợp lệ. 8. Không. 9. Filtering không cấp/giới hạn quyền đáng tin. 10. Body là message gốc. 11. Có thể bị discard như lỗi delivery. 12. Signature, TopicArn, signing certificate URL/chain. 13. Mất event khi process crash. 14. Chưa. 15. Lỗi giao endpoint so với lỗi consumer. 16. Lambda async. 17. Không; cần queue resource policy/KMS. 18. Không. 19. 256 KiB mặc định, có thể nâng đến 1 MiB với giới hạn protocol/subscription. 20. Tránh duplicates và mất event sau DB commit.

## 19. Checklist trước khi triển khai production

### Topic/subscription

- [ ] Chọn Standard hay FIFO theo ordering/deduplication và protocol.
- [ ] FIFO groups/dedup IDs và SQS queues phù hợp.
- [ ] Subscriptions có owner, confirmed status, endpoint và purpose rõ ràng.
- [ ] Filter policies có test theo attributes/body và propagation.
- [ ] Raw delivery tương thích parser và giới hạn 10 attributes trên SQS.
- [ ] Đã kiểm tra MaximumMessageSize, protocol và quota khi >256 KiB.
- [ ] Có schemaVersion/eventId/operationId ổn định.

### Security/reliability

- [ ] Producer IAM chỉ có `sns:Publish` tới topic cần thiết.
- [ ] SNS topic access policy giới hạn publish/subscribe/update permissions.
- [ ] SQS queue policy dùng `sns.amazonaws.com` với `aws:SourceArn`.
- [ ] Lambda resource policy có quyền gọi từ đúng topic.
- [ ] KMS permissions, encryption và endpoint policies được xác minh.
- [ ] HTTPS endpoints xác thực signature/certificate/TopicArn, chống SSRF.
- [ ] Có SNS subscription DLQ để giữ delivery failures cần thiết.
- [ ] Consumer SQS/Lambda có retry/DLQ riêng cho processing failures.
- [ ] Consumers idempotent; replay có kiểm tra side effects.
- [ ] PII/secrets không bị fan-out ra ngoài trust boundary.

### Monitoring/cost

- [ ] CloudWatch metrics/alarms cho published, failed, filtered, redriven.
- [ ] SQS backlog/DLQ, Lambda Errors và HTTP endpoint status được theo dõi.
- [ ] Có on-call owner, retention, runbook và audit.
- [ ] Có kiểm thử queue denied, webhook lỗi, filter mismatch, duplicates.
- [ ] Đã tính phí SNS/SQS/Lambda/SMS/Firehose/KMS/CloudWatch.
- [ ] Có tags, Budgets, lifecycle và dọn tài nguyên sandbox.
- [ ] Thay đổi infrastructure qua IaC/change approval, có rollback.

**Kết quả mong đợi:** người học tự thiết kế được SNS topic và subscriptions có đúng delivery protocol, hiểu fan-out, filtering, confirmation, retry và DLQ tại từng lớp, triển khai quyền truy cập và encryption an toàn, đồng thời có cách quan sát, phục hồi và kiểm soát chi phí.

## Tài liệu AWS chính thức

- [What is Amazon SNS?](https://docs.aws.amazon.com/sns/latest/dg/welcome.html)
- [SNS features and capabilities](https://docs.aws.amazon.com/sns/latest/dg/welcome-features.html)
- [Creating SNS topics](https://docs.aws.amazon.com/sns/latest/dg/sns-create-topic.html)
- [Creating topic subscriptions](https://docs.aws.amazon.com/sns/latest/dg/sns-create-subscribe-endpoint-to-topic.html)
- [SNS message delivery](https://docs.aws.amazon.com/sns/latest/dg/message-delivery.html)
- [SNS FIFO message delivery](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-delivery.html)
- [FIFO ordering](https://docs.aws.amazon.com/sns/latest/dg/fifo-topic-message-ordering.html)
- [SNS message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html)
- [Message filtering scope](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering-scope.html)
- [Raw message delivery](https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html)
- [SNS message attributes](https://docs.aws.amazon.com/sns/latest/dg/sns-message-attributes.html)
- [SNS delivery retry](https://docs.aws.amazon.com/sns/latest/dg/sns-message-delivery-retries.html)
- [SNS dead-letter queues](https://docs.aws.amazon.com/sns/latest/dg/sns-dead-letter-queues.html)
- [Configuring SNS subscription DLQ](https://docs.aws.amazon.com/sns/latest/dg/sns-configure-dead-letter-queue.html)
- [Verifying SNS message signature](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html)
- [Subscribe an SQS queue to SNS](https://docs.aws.amazon.com/sns/latest/dg/subscribe-sqs-queue-to-sns-topic.html)
- [Using Lambda with SNS](https://docs.aws.amazon.com/lambda/latest/dg/with-sns.html)
- [Publishing SNS messages up to 1 MiB](https://docs.aws.amazon.com/sns/latest/dg/large-message-payloads.html)
- [AWS SNS 1 MiB announcement (18/09/2026)](https://aws.amazon.com/about-aws/whats-new/2026/09/amazon-sns-1mib-support/)
- [SNS pricing](https://aws.amazon.com/sns/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Lưu ý áp dụng:** Mọi ARN, account ID, URL, SNS topic, SQS queue, code và IaC trong bài là **ví dụ đào tạo**. AWS có thể cập nhật message size, quotas, protocol support, IAM/KMS yêu cầu và giá theo Region. Trước khi triển khai production, kiểm tra tài liệu AWS hiện hành, thử nghiệm trong sandbox, phân loại dữ liệu được fan-out và tuân thủ quy trình phê duyệt thay đổi.
