# S3 Event Notifications và xử lý sự kiện object

> **Chương:** Lưu trữ đối tượng S3  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua hạ tầng Region/Availability Zone (AZ), IAM, VPC, tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn luyện khả năng chọn dịch vụ, thiết kế ứng dụng an toàn, giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **Amazon S3 Event Notifications** là gì, sự khác nhau giữa **sự kiện thay đổi object** và thao tác đọc/ghi dữ liệu qua S3 API.
2. Liệt kê các nhóm sự kiện thường dùng như **ObjectCreated**, **ObjectRemoved**, khôi phục từ lưu trữ lưu trữ lạnh, lifecycle và replication.
3. So sánh các đích **Amazon SQS, Amazon SNS, AWS Lambda** và **Amazon EventBridge**, xác định khi nào nên dùng hàng đợi hoặc bộ định tuyến sự kiện.
4. Cấu hình tư duy theo **bucket, event type, prefix/suffix filter, destination, IAM/resource-based policy** và Region.
5. Đọc cấu trúc bản tin S3, giải mã object key đúng cách; xử lý trường hợp **at-least-once**, bản tin trùng và **không bảo đảm thứ tự**.
6. Xây dựng kiến trúc xử lý object an toàn và có thể phục hồi, tránh **vòng lặp kích hoạt Lambda**, giới hạn quyền và quản lý lỗi bằng retry/DLQ.
7. Kiểm tra cấu hình bằng AWS CLI chỉ đọc, quan sát bằng CloudWatch/CloudTrail và đánh giá chi phí, khả năng mở rộng.

## 1. Vì sao ứng dụng cần phản ứng khi object thay đổi?

Hãy tưởng tượng một website cho người dùng tải ảnh lên Amazon S3. Sau khi upload thành công, hệ thống cần tạo thumbnail, kiểm tra định dạng, cập nhật metadata hoặc gửi thông báo. Nếu ứng dụng phải liên tục hỏi S3 “đã có file mới chưa?” thì:

- Ứng dụng tạo nhiều API LIST/HEAD không cần thiết.
- Việc xử lý dễ chậm, phụ thuộc vào lịch polling.
- Khi số object và lượng upload tăng, việc quản lý trạng thái và số lần kiểm tra trở nên phức tạp.

**S3 Event Notifications** cho phép cấu hình để S3 phát **thông báo về các sự kiện object được hỗ trợ** tới một đích xử lý. Ví dụ, sau thao tác **PutObject** hợp lệ, S3 gửi thông tin về object được tạo mới. Worker dùng thông tin này để xử lý dữ liệu.

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Upload ảnh"| S3[("S3 bucket: incoming/")]
    S3 -->|"ObjectCreated event"| Q["SQS queue"]
    Q -->|"Poll"| L["Lambda image worker"]
    L -->|"Ghi thumbnail"| OUT[("S3 output bucket")]
    L -->|"Cập nhật kết quả"| DB[("DynamoDB / database")]
~~~

Sơ đồ là **kiến trúc tham khảo**. S3 gửi *metadata sự kiện* tới hàng đợi; **nội dung object không được đính kèm đầy đủ trong event**. Worker cần dùng API S3 để đọc object thực tế.

### 1.1. Event-driven khác polling ở đâu?

| Khía cạnh | Polling | S3 Event Notifications |
| --- | --- | --- |
| Cách phát hiện thay đổi | Worker chủ động liệt kê/kiểm tra object. | S3 phát bản tin khi có sự kiện được cấu hình. |
| Độ trễ | Phụ thuộc chu kỳ polling. | Thường được chuyển nhanh, nhưng là cơ chế bất đồng bộ, không có cam kết thứ tự và không nên coi là tức thời tuyệt đối. |
| Tải lên hệ thống | Có thể nhiều request ngay cả khi không có dữ liệu mới. | Tăng theo sự kiện object; downstream vẫn cần giới hạn khả năng xử lý. |
| Xử lý lỗi | Worker tự lưu checkpoint và lên lịch kiểm tra lại. | Destination/consumer cần retry, chống trùng và phương án phục hồi. |
| Tình huống | Quét định kỳ, reconciliation, kiểm kê. | Xử lý ảnh, ETL, cập nhật chỉ mục, log pipeline. |

**Điểm quan trọng:** Event-driven không có nghĩa sẽ **không bao giờ cần kiểm kê lại**. Với dữ liệu quan trọng, nên có khả năng đối soát object (ví dụ S3 Inventory/batch processing khi thích hợp), kiểm tra DLQ và tái xử lý khi pipeline gặp sự cố.

## 2. S3 phát thông báo về những sự kiện gì?

Thông báo được cấu hình theo nhóm **event type**. Các tên bên dưới là những loại thường gặp, không phải toàn bộ danh sách API/service hỗ trợ.

| Nhóm | Event type minh họa | Khi nào dùng |
| --- | --- | --- |
| **Tạo object** | **s3:ObjectCreated:Put**, **:Post**, **:Copy**, **:CompleteMultipartUpload**, **s3:ObjectCreated:*** | Phát hiện object được tạo/ghi đè hoặc hoàn tất multipart upload. |
| **Xóa object** | **s3:ObjectRemoved:Delete**, **:DeleteMarkerCreated**, **s3:ObjectRemoved:*** | Xóa metadata liên quan, cập nhật chỉ mục, audit. |
| **Khôi phục object lưu trữ lạnh** | **s3:ObjectRestore:Post**, **:Completed**, **:Delete** khi hỗ trợ | Theo dõi yêu cầu/hoàn thành/biến động bản sao phục hồi theo storage class. |
| **Lifecycle** | **s3:LifecycleTransition**, **s3:LifecycleExpiration:*** | Theo dõi object chuyển class hoặc hết hạn bởi lifecycle rule. |
| **Replication** | **s3:Replication:*** và các event con được hỗ trợ | Theo dõi lỗi/trạng thái các hoạt động replication nhất định. |
| **Thay đổi metadata liên quan** | Các loại event tagging, ACL, Intelligent-Tiering hoặc nhóm mới theo tính năng hỗ trợ | Đồng bộ chỉ mục/quản trị dữ liệu theo sự kiện phù hợp. |

Ví dụ chọn **s3:ObjectCreated:*** nghĩa là nhận các kiểu tạo object được nhóm này bao phủ. Nếu chỉ chọn **s3:ObjectCreated:Put**, một upload theo **multipart upload** có thể tạo ra **ObjectCreated:CompleteMultipartUpload**, nên pipeline có thể bỏ sót đối tượng cần xử lý.

### 2.1. Sự kiện ghi đè và phiên bản object

S3 object được xác định bằng **bucket + key**; khi bucket bật versioning, một thao tác có thể tạo **versionId** mới. Sự kiện **ObjectCreated** không có nghĩa key chưa từng tồn tại.

Ví dụ:

1. Người dùng upload **incoming/report.csv**.
2. Người dùng upload lại cùng key **incoming/report.csv** sau vài giây.
3. Hệ thống có thể nhận **hai bản tin ObjectCreated** về cùng một key.
4. Worker đọc **GET bucket/key** mà không chỉ định version có thể thấy bản **mới nhất**, không phải chính xác nội dung gắn với bản tin đầu tiên.

Khi cần xử lý *mỗi phiên bản chính xác*, hãy bật versioning theo thiết kế và sử dụng **versionId** do event cung cấp khi có, kết hợp quyền IAM/KMS tương ứng. Không giả định mọi event đều có versionId hữu ích nếu bucket không bật versioning.

### 2.2. Sự kiện xóa và delete marker

Với bucket có versioning, thao tác DELETE không luôn đồng nghĩa dữ liệu đã bị xóa vĩnh viễn: thao tác có thể tạo **delete marker**. Event **ObjectRemoved:DeleteMarkerCreated** cần được hiểu khác với việc xóa hẳn một object version.

Ví dụ, hệ thống tìm kiếm muốn ẩn tài liệu khi current version bị đánh dấu xóa; hệ thống audit có thể vẫn cần giữ thông tin các version trước đó. Thiết kế nên phân biệt **xóa khỏi kết quả nghiệp vụ**, **xóa version** và **hết hạn do lifecycle**.

### 2.3. Có phải mọi thao tác với bucket đều phát sự kiện?

Không. Notification tập trung vào **những event type mà S3 hỗ trợ**. Đổi bucket policy, sửa IAM, đọc object qua GetObject hoặc thay đổi cấu hình bucket không mặc nhiên trở thành **ObjectCreated/Removed**.

Muốn audit việc thay đổi cấu hình hay các API data-plane, cân nhắc **AWS CloudTrail** (trong đó data events cần cấu hình phù hợp). Không dùng S3 Event Notifications làm nguồn audit đầy đủ cho tất cả thao tác AWS.

## 3. Các đích nhận sự kiện

S3 Event Notifications trực tiếp có thể gửi tới những loại destination được hỗ trợ. **EventBridge** là một nhánh nhận và định tuyến bổ sung.

| Đích | Cách sử dụng | Ưu điểm | Điều cần lưu ý |
| --- | --- | --- | --- |
| **AWS Lambda** | S3 kích hoạt function trực tiếp. | Ít thành phần, thuận tiện xử lý đơn giản, thời gian chạy ngắn. | Retry, giới hạn concurrency, mất kiểm soát tải khi có đột biến; tránh loop. |
| **Amazon SQS queue** | S3 gửi message vào queue, consumer poll để xử lý. | Đệm tải, tách producer/consumer, retry, DLQ, kiểm soát tốc độ. | Có phí queue, quản lý visibility timeout, duplicate và retention. |
| **Amazon SNS topic** | S3 publish notification lên topic để phân phối cho subscriber. | Fan-out đến nhiều subscriber theo kiến trúc phù hợp. | Subscriber/policy và cơ chế retry khác nhau; topic không phải queue lưu backlog để tùy ý poll. |
| **Amazon EventBridge** | S3 phát event tới **default event bus** trong account/Region; EventBridge rule chọn target. | Lọc theo nhiều trường, phân phối nhiều target, tích hợp workflow và cross-account routing. | Cần quản lý rule/bus/target/permissions và chi phí theo luồng. |

### 3.1. S3 → Lambda trực tiếp

Dùng khi workflow rõ ràng, tải tương đối dễ quản lý và không cần một queue riêng.

Ví dụ:

~~~mermaid
flowchart LR
    S3[("S3 incoming bucket")] -->|"ObjectCreated"| L["Lambda metadata validator"]
    L --> D[("DynamoDB metadata")]
~~~

Các lưu ý:

- Lambda cần **resource-based permission** cho **s3.amazonaws.com** được invoke function, nên giới hạn **SourceArn** của bucket và **SourceAccount**.
- Lambda nhận bản tin bất đồng bộ; lỗi và retries cần được theo dõi theo cơ chế async invocation.
- Số upload tăng có thể tạo nhiều concurrent invocations; cần kiểm soát tài nguyên, timeout, quota và idempotency.
- Nếu function ghi lại object vào đúng phạm vi kích hoạt, có thể tạo **vòng lặp vô hạn**.

### 3.2. S3 → SQS → worker/Lambda

Dùng khi khối lượng upload lên xuống bất thường, cần backlog, retry và DLQ.

~~~mermaid
flowchart LR
    S3[("S3 uploads")] -->|"S3 event"| Q["SQS Standard queue"]
    Q -->|"Lambda event source mapping"| L["Lambda worker"]
    L --> OUT[("Output bucket")]
    Q -.->|"Redrive khi vượt số lần nhận"| DLQ["Dead-letter queue"]
~~~

**SQS là hàng đợi lưu message để consumer xử lý**, không chuyển nội dung object vào queue. Worker nhận **bucket/key/versionId** và tự gọi S3 API lấy nội dung.

S3 Event Notifications trực tiếp truyền thống hỗ trợ **SQS Standard** làm queue destination; nếu workflow cần **SQS FIFO**, cách thiết kế được AWS hướng dẫn là định tuyến **S3 → EventBridge → SQS FIFO** khi các điều kiện tích hợp tương ứng được đáp ứng. Hãy xác minh giới hạn destination và tính năng hiện hành trước khi áp dụng.

**Queue giúp giảm áp lực**, nhưng không tự ngăn trùng: S3 có thể tạo bản tin trùng, SQS Standard cũng có thể trả cùng message nhiều hơn một lần. Consumer phải idempotent.

### 3.3. S3 → SNS → nhiều subscriber

Phù hợp khi một object mới cần kích hoạt nhiều hướng xử lý độc lập, chẳng hạn kiểm duyệt nội dung, tạo thumbnail và cập nhật analytics.

~~~mermaid
flowchart TB
    S3[("S3 incoming/")] --> SNS["SNS topic"]
    SNS --> Q1["SQS queue — thumbnail"]
    SNS --> Q2["SQS queue — antivirus"]
    SNS --> Q3["SQS queue — indexing"]
    Q1 --> L1["Worker 1"]
    Q2 --> L2["Worker 2"]
    Q3 --> L3["Worker 3"]
~~~

Mỗi subscriber có thể triển khai cơ chế retry/giới hạn concurrency riêng. Nếu một worker ngừng hoạt động, các worker khác có thể tiếp tục. Cần kiểm tra **SNS topic policy**, subscription, SQS queue policy và cách phân phối message.

Đối với SNS FIFO topic và những ràng buộc nguồn S3 notification trực tiếp, hãy kiểm tra loại topic được hỗ trợ; khi cần workflow FIFO, thường dùng EventBridge/SQS FIFO hoặc thiết kế khác được AWS hỗ trợ.

### 3.4. S3 → EventBridge → nhiều target

Khi bật EventBridge delivery cho bucket, S3 đưa **các sự kiện S3 được hỗ trợ** vào **default event bus**; các EventBridge rule mới quyết định event nào được chuyển tiếp đến target.

~~~mermaid
flowchart TB
    S3[("S3 bucket")] --> EB["EventBridge default bus"]
    EB -->|"Event pattern: Object Created, prefix/field"| R1["Rule ảnh"]
    EB -->|"Event pattern: Object Deleted"| R2["Rule audit"]
    R1 --> L["Lambda / Step Functions"]
    R2 --> Q["SQS / target khác"]
~~~

EventBridge phù hợp khi cần:

- Lọc dựa trên nhiều trường của event hơn prefix/suffix thuần túy.
- Chuyển tới nhiều loại target như Lambda, Step Functions, SQS hoặc event bus khác trong khả năng hỗ trợ.
- Xây dựng integration giữa account và routing có chính sách riêng.
- Tách việc phát sự kiện khỏi logic lựa chọn từng consumer.

EventBridge event **không dùng cùng JSON envelope** với S3 notification trực tiếp. Consumer phải phân tích đúng schema trước khi đọc key và các thuộc tính.

## 4. Quy trình từ upload tới xử lý hoàn tất

Giả sử người dùng tải ảnh lên key **incoming/avatar-001.jpg**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Amazon S3
    participant Q as SQS Standard
    participant L as Lambda
    participant O as S3 output
    C->>S: PutObject incoming/avatar-001.jpg
    S-->>C: Upload thành công
    S-->>Q: ObjectCreated notification (bất đồng bộ)
    Q-->>L: Batch message (qua event source mapping)
    L->>S: GetObject theo bucket/key/version nếu có
    S-->>L: Nội dung ảnh
    L->>O: PutObject thumbnail/output
    L-->>Q: Xử lý thành công, message được xóa qua mapping
~~~

### Các điểm kiểm soát chính

1. **Client ghi object:** cần quyền **s3:PutObject** phù hợp và điều kiện mã hóa nếu áp dụng.
2. **S3 phát event:** notification configuration của bucket phải phù hợp event type, filter và destination.
3. **Destination nhận event:** queue/topic/function phải cho phép dịch vụ S3 gửi message hoặc invoke qua resource-based policy.
4. **Consumer đọc dữ liệu:** worker cần **s3:GetObject**, có thể cần **kms:Decrypt** nếu object SSE-KMS.
5. **Consumer ghi kết quả:** quyền **s3:PutObject** tới output bucket/prefix thích hợp, có thể cần KMS permission.
6. **Consumer đánh dấu hoàn tất:** bảo đảm thao tác có thể chạy lại an toàn nếu message được gửi/lấy lại.
7. **Quan sát và phục hồi:** theo dõi backlog, failed invocation, DLQ và khả năng xử lý lại.

**Upload thành công không đồng nghĩa workflow xử lý đã hoàn tất.** S3 notifications hoạt động bất đồng bộ. Với nghiệp vụ quan trọng, lưu trạng thái processing (received, processing, completed, failed) trong database hoặc hệ thống theo dõi thích hợp.

## 5. Đọc cấu trúc một S3 Event Notification

Một notification trực tiếp gửi tới SQS/SNS/Lambda thường có trường **Records**, mỗi record mô tả một sự kiện. Ví dụ đã rút gọn:

~~~json
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "ap-southeast-1",
      "eventTime": "2026-11-20T02:10:00.000Z",
      "eventName": "ObjectCreated:Put",
      "userIdentity": {
        "principalId": "EXAMPLE"
      },
      "requestParameters": {
        "sourceIPAddress": "203.0.113.10"
      },
      "responseElements": {
        "x-amz-request-id": "EXAMPLE-REQUEST"
      },
      "s3": {
        "s3SchemaVersion": "1.0",
        "configurationId": "incoming-images",
        "bucket": {
          "name": "example-incoming-images",
          "arn": "arn:aws:s3:::example-incoming-images"
        },
        "object": {
          "key": "incoming/avatar+one.jpg",
          "size": 120481,
          "eTag": "example-etag",
          "versionId": "example-version-id",
          "sequencer": "0065F0000000000000"
        }
      }
    }
  ]
}
~~~

*Dữ liệu và ID trong ví dụ đều là giả định; không nên coi ví dụ chứa đầy đủ trường của mọi event.*

| Trường | Ý nghĩa | Lưu ý khi code |
| --- | --- | --- |
| **Records** | Danh sách record; một payload có thể chứa nhiều record. | Duyệt từng record, không mặc định chỉ có record đầu tiên. |
| **eventVersion** | Phiên bản schema của S3 event. | Kiểm tra major version và xử lý thêm field không biết để tương thích minor version. |
| **eventSource** | Nguồn sự kiện, thường **aws:s3**. | Dùng để phân loại nếu handler còn nhận event khác. |
| **eventName** | Ví dụ **ObjectCreated:Put**. | **Không** có tiền tố **s3:** trong trường eventName, khác tên event type lúc cấu hình. |
| **awsRegion** | Region liên quan tới event. | Dùng cho routing/SDK client khi cần. |
| **eventTime** | Thời điểm event được ghi nhận theo schema. | Không dùng làm số thứ tự tuyệt đối cho nhiều event. |
| **bucket.name / bucket.arn** | Bucket liên quan. | Kiểm tra bucket có thuộc danh sách cho phép. |
| **object.key** | Key của object. | **Phải giải mã URL form encoding** khi dùng trong S3 API. |
| **object.size / eTag** | Metadata theo event khi có. | ETag không luôn là MD5 nội dung; không dùng làm checksum duy nhất. |
| **object.versionId** | Phiên bản nếu liên quan và được cung cấp. | Xử lý trường hợp thiếu/null. |
| **object.sequencer** | Chuỗi dùng hỗ trợ so sánh thứ tự với một số event cùng key. | Không so sánh thứ tự giữa các key khác nhau. |

### 5.1. Object key được URL encode

Trong S3 notification truyền thống, **object.key** thường được **URL form encoded**. Dấu cách có thể được biểu diễn bằng dấu **+**. Ví dụ key thực là **incoming/avatar one.jpg**, payload mang **incoming/avatar+one.jpg**.

Với Python:

~~~python
from urllib.parse import unquote_plus

encoded_key = "incoming/avatar+one.jpg"
key = unquote_plus(encoded_key)
print(key)  # incoming/avatar one.jpg
~~~

Dùng **unquote_plus** cho schema notification trực tiếp là lựa chọn phù hợp vì xử lý cả dấu **+** thay cho space và ký tự percent-encoding. Không thực hiện giải mã nhiều lần; với event schema khác, đọc đúng định dạng trước khi áp dụng cùng cách.

### 5.2. s3:TestEvent có dạng đặc biệt

Khi cấu hình notification tới destination, S3 có thể phát một **test message** nhằm xác minh quyền gửi. Test message **không nhất thiết có trường Records như các event object thông thường**.

Handler nên kiểm tra cấu trúc payload thay vì truy cập cứng **event["Records"][0]** và báo lỗi khi gặp test event.

### 5.3. SQS message có thêm lớp envelope

Nếu Lambda được trigger bởi **SQS**, event Lambda bên ngoài có dạng:

~~~json
{
  "Records": [
    {
      "messageId": "example-sqs-message-id",
      "eventSource": "aws:sqs",
      "body": "{\"Records\":[{\"eventSource\":\"aws:s3\",\"eventName\":\"ObjectCreated:Put\",\"s3\":{\"bucket\":{\"name\":\"example-incoming-images\"},\"object\":{\"key\":\"incoming%2Favatar.jpg\"}}}]}"
    }
  ]
}
~~~

Nội dung **body** là chuỗi JSON chứa S3 notification. Khi dùng tuyến **S3 → SNS → SQS**, body có thể còn chứa envelope SNS và thông điệp S3 nằm trong trường **Message**. Luôn phân biệt **SQS Records** và **S3 Records**.

### 5.4. EventBridge event có schema khác

EventBridge event cho S3 object có dạng rút gọn:

~~~json
{
  "version": "0",
  "id": "example-event-id",
  "source": "aws.s3",
  "detail-type": "Object Created",
  "account": "111122223333",
  "time": "2026-11-20T02:10:00Z",
  "region": "ap-southeast-1",
  "resources": [
    "arn:aws:s3:::example-incoming-images"
  ],
  "detail": {
    "version": "0",
    "bucket": {
      "name": "example-incoming-images"
    },
    "object": {
      "key": "incoming/avatar.jpg",
      "size": 120481,
      "etag": "example-etag",
      "sequencer": "0065F0000000000000"
    },
    "request-id": "EXAMPLE-REQUEST",
    "reason": "PutObject"
  }
}
~~~

Trong EventBridge event, **detail-type** và **detail.object** được dùng thay cho **Records[].eventName** và **Records[].s3.object**. Không được tái sử dụng parser của S3 notification trực tiếp mà không phân nhánh theo schema.

## 6. Lọc sự kiện bằng prefix và suffix

Không phải object nào cũng cần xử lý. S3 notification configuration hỗ trợ lọc object key bằng **prefix** (tiền tố) và **suffix** (hậu tố) với các loại thông báo trực tiếp được hỗ trợ.

Ví dụ:

- Chỉ nhận object nằm dưới **incoming/**.
- Chỉ nhận file có key kết thúc **.jpg**.
- Event type **s3:ObjectCreated:***.

~~~mermaid
flowchart LR
    B[("Bucket")] --> A{"ObjectCreated?"}
    A -->|"Không"| X["Bỏ qua"]
    A -->|"Có"| P{"Key bắt đầu incoming/?"}
    P -->|"Không"| X
    P -->|"Có"| S{"Key kết thúc .jpg?"}
    S -->|"Không"| X
    S -->|"Có"| Q["Gửi notification đến queue"]
~~~

### 6.1. Ví dụ cấu hình JSON theo định dạng API

Dưới đây là cấu trúc minh họa cho tham số **NotificationConfiguration** của S3 API:

~~~json
{
  "QueueConfigurations": [
    {
      "Id": "incoming-jpg-events",
      "QueueArn": "arn:aws:sqs:ap-southeast-1:111122223333:image-processing-queue",
      "Events": [
        "s3:ObjectCreated:*"
      ],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "incoming/"
            },
            {
              "Name": "suffix",
              "Value": ".jpg"
            }
          ]
        }
      }
    }
  ]
}
~~~

Đây là **ví dụ khai báo để học cấu trúc**, không phải thao tác thay đổi trên tài nguyên thật. Cấu hình này chỉ hoạt động sau khi queue tồn tại, ở Region hỗ trợ và policy của queue cho phép S3 gửi message.

**Cảnh báo khi triển khai:** API **PutBucketNotificationConfiguration** có thể **thay thế toàn bộ notification configuration** của bucket bằng tài liệu được gửi. Khi dùng IaC/CLI, cần quản lý **tất cả** các destination hiện hành, tránh vô tình xóa notification do một nhóm khác cấu hình.

### 6.2. Quy tắc về filter chồng lấn

Trong cùng một bucket, các cấu hình notification trực tiếp **không được có bộ lọc prefix/suffix chồng lấn gây mơ hồ đối với cùng event type**, theo quy tắc AWS.

Ví dụ muốn tạo hai notification cùng bắt **ObjectCreated**:

- Rule A: prefix **incoming/**, suffix **.jpg**.
- Rule B: prefix **incoming/photos/**, suffix **.jpg**.

Hai filter có vùng key chung như **incoming/photos/a.jpg** và có thể bị từ chối khi lưu cấu hình. Có thể tổ chức lại prefix độc lập hoặc dùng EventBridge để có bộ lọc và nhiều consumer linh hoạt hơn.

**Prefix/suffix là cách khớp chuỗi, không phải regex hoặc glob pattern.** Không dùng dấu **\*** trong filter như một wildcard; để chọn nhiều phần mở rộng, xây dựng các rule không xung đột hoặc dùng cơ chế router được hỗ trợ.

### 6.3. Với EventBridge, đặt filter tại rule

Khi S3 gửi event tới EventBridge, dùng **event pattern** để lọc theo nguồn, detail-type, bucket và object key.

Ví dụ rule chỉ nhận Object Created của bucket **example-incoming-images**, có key bắt đầu **incoming/**:

~~~json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": {
      "name": ["example-incoming-images"]
    },
    "object": {
      "key": [
        {
          "prefix": "incoming/"
        }
      ]
    }
  }
}
~~~

Đây là **event pattern** cho EventBridge, khác JSON của **NotificationConfiguration** trong S3 API. Rule có thể lọc theo nhiều trường/condition mà EventBridge hỗ trợ, nhưng cần kiểm tra field thực tế của event và behavior theo schema.

## 7. Giao hàng at-least-once, trùng lặp và thứ tự

**Điều kiện quan trọng nhất khi thiết kế S3 event pipeline:** các thông báo có thể được gửi **ít nhất một lần (at-least-once)**; đôi khi nhận nhiều bản tin cho cùng thao tác, và **không có cam kết thứ tự** giữa các thông báo.

Ví dụ người dùng ghi đè key **incoming/report.csv** ba lần:

- Event A được tạo trước, Event B và C được tạo sau.
- Worker có thể nhận **B rồi A rồi C**.
- Một bản tin của B có thể xuất hiện **hai lần**.
- Worker đọc key không chỉ định version có thể nhận nội dung của C ngay cả khi đang xử lý event A.

### 7.1. Idempotency là gì?

Một thao tác **idempotent** có nghĩa chạy lại nhiều lần với cùng một logical event không gây tác động nghiệp vụ ngoài dự kiến.

Ví dụ:

- Tạo thumbnail tại một object key xác định từ cùng source version → có thể an toàn nếu nội dung được tính deterministic và ghi đè có kiểm soát.
- Tăng **viewCount += 1** mỗi lần nhận event → **không idempotent** nếu event bị giao trùng.
- Gửi email hóa đơn cho khách mỗi khi event đến → có thể gửi hai email nếu không có kiểm soát trạng thái.
- Ghi nhận một thanh toán hoặc tăng số dư → cần cơ chế idempotency/transaction của ứng dụng, không được dựa vào giả định mỗi event chỉ đến một lần.

### 7.2. Chọn khóa idempotency

Tùy yêu cầu nghiệp vụ:

| Mục tiêu | Khóa gợi ý | Lưu ý |
| --- | --- | --- |
| Xử lý một phiên bản object đúng một lần về mặt nghiệp vụ | **bucket + key + versionId + loại xử lý** | Phù hợp khi versioning có mặt và event mang versionId dùng được. |
| Phân biệt nhiều thay đổi liên tiếp trên cùng key | **bucket + key + sequencer + event type** | Sequencer có trong những event PUT/DELETE thích hợp; kiểm tra schema. |
| Đảm bảo một báo cáo nghiệp vụ không tạo trùng | **business ID + workflow step** | Có thể tốt hơn khóa hạ tầng nếu cùng dữ liệu được upload nhiều lần. |
| Đảm bảo kết quả thumbnail tương ứng source | **bucket + key + versionId + variant** | Tạo output key deterministic và kết hợp cơ chế chống ghi đè sai. |

Không dùng **messageId của SQS** làm khóa chống trùng duy nhất nếu S3 có thể gửi nhiều thông báo khác nhau cho cùng sự kiện object; mỗi message SQS có thể có ID khác.

### 7.3. Sequencer giúp so sánh sự kiện cùng key

Đối với các sự kiện PUT/DELETE có **sequencer**, S3 cung cấp chuỗi hex có thể dùng so sánh trình tự các thay đổi **trên cùng object key**. Khi so sánh hai sequencer:

1. Chỉ so sánh khi cùng bucket/object key và trong ngữ cảnh event tương ứng.
2. Nếu chuỗi khác độ dài, **pad số 0 bên trái** đến cùng độ dài.
3. So sánh theo giá trị hex; sequencer lớn hơn thường tương ứng sự kiện thay đổi muộn hơn cho **cùng key**.

Không dùng sequencer để quyết định sự kiện của **hai key khác nhau** xảy ra trước hay sau. Không phải mọi loại event đều cung cấp sequencer.

### 7.4. Bài toán race condition

Nếu worker X nhận event A trước, worker Y nhận event B sau nhưng X xử lý lâu hơn, X có thể ghi đè kết quả của Y bằng dữ liệu cũ.

Cách giảm rủi ro:

- Với versioning, đọc đúng **versionId**.
- Lưu **latest processed sequencer/version** theo bucket + key.
- Dùng cập nhật có điều kiện trong DynamoDB hoặc database để **chỉ chấp nhận trạng thái mới hơn**.
- Gắn key output theo version của input hoặc tách version-specific output khỏi **latest**.
- Giới hạn concurrency per key hoặc áp dụng một bộ điều phối khi nghiệp vụ đòi hỏi xử lý tuần tự.

**Cẩn thận với “đánh dấu đã xử lý” quá sớm:** Nếu đặt một idempotency marker rồi worker lỗi trước khi hoàn tất, lần retry có thể bỏ qua công việc chưa làm. Thiết kế trạng thái nên có **PENDING/PROCESSING/COMPLETED**, lease/timeout hoặc giao dịch/outbox theo nhu cầu.

## 8. Ví dụ Lambda xử lý sự kiện trực tiếp

Ví dụ Python sau minh họa cách:

- Phân biệt S3 event thông thường với test event.
- Giải mã key.
- Chỉ xử lý các event ObjectCreated dưới **incoming/**.
- Ghi metadata vào **một output bucket khác** để tránh loop.
- Tạo output key deterministic theo key/version hoặc sequencer để dễ xử lý lại.

Đây là đoạn **minh họa luồng**, chưa có state store chống race cho xử lý đồng thời; production cần bổ sung idempotency có tính nguyên tử và kiểm thử lỗi.

~~~python
import json
import os
from urllib.parse import quote, unquote_plus

import boto3

s3 = boto3.client("s3")
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]


def lambda_handler(event, context):
    # TestEvent hoặc event khác có thể không chứa Records.
    records = event.get("Records", [])
    processed = 0

    for record in records:
        if record.get("eventSource") != "aws:s3":
            continue

        name = record.get("eventName", "")
        if not name.startswith("ObjectCreated:"):
            continue

        data = record["s3"]
        bucket = data["bucket"]["name"]
        obj = data["object"]
        key = unquote_plus(obj["key"])

        if not key.startswith("incoming/"):
            continue

        # Không giả định versionId tồn tại hoặc luôn khác "null".
        version_id = obj.get("versionId")
        if version_id == "null":
            version_id = None

        read_args = {"Bucket": bucket, "Key": key}
        if version_id:
            read_args["VersionId"] = version_id

        # HEAD để xác nhận quyền và metadata của object.
        # Nếu bucket không versioned và key bị ghi đè liên tiếp,
        # HEAD có thể phản ánh object mới hơn event đang xử lý.
        source = s3.head_object(**read_args)

        revision = version_id or obj.get("sequencer") or "unversioned"
        safe_key = quote(key, safe="")
        out_key = f"manifests/{safe_key}/{quote(revision, safe='')}.json"

        manifest = {
            "sourceBucket": bucket,
            "sourceKey": key,
            "sourceVersion": version_id,
            "sourceETag": source.get("ETag"),
            "eventName": name,
        }

        s3.put_object(
            Bucket=OUTPUT_BUCKET,
            Key=out_key,
            Body=json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        processed += 1

    return {"processed": processed}
~~~

### 8.1. Những gì còn cần cho production

- **Bảo đảm dữ liệu đúng version:** nếu không dùng versioning, event cũ có thể đọc object đã bị ghi đè; nên xác định chính sách xử lý latest-only hoặc version-specific.
- **Idempotency atomically:** dùng conditional write và trạng thái hoàn thành; tránh side effects lặp như gửi email hoặc charge.
- **Permission least privilege:** chỉ đọc bucket/prefix input và ghi bucket/prefix output; tránh **s3:\*** khi không cần.
- **IAM/KMS:** execution role có quyền CloudWatch Logs, S3 và KMS cần thiết; S3 có quyền invoke Lambda nếu trigger trực tiếp.
- **Validation:** không tin nội dung file chỉ vì bucket của tổ chức; kiểm tra kích thước, định dạng, thư viện parser và tệp độc hại.
- **Concurrency/timeout:** đặt timeout, memory, reserved concurrency và retry phù hợp với kích thước object.
- **Vòng lặp:** output bucket khác input bucket hoặc filter input prefix thật chặt.
- **Audit:** log bucket/key/version và correlation ID phù hợp, hạn chế log dữ liệu nhạy cảm.

### 8.2. Vì sao dùng output bucket riêng?

Nếu function xử lý object tại **incoming/photo.jpg** rồi ghi **processed/photo.jpg** **vào cùng bucket** trong khi trigger cấu hình **s3:ObjectCreated:*** không có filter, thao tác ghi output tạo sự kiện mới và lại kích hoạt function.

~~~mermaid
flowchart LR
    S3["S3 bucket"] -->|"ObjectCreated"| L["Lambda"]
    L -->|"PutObject vào chính bucket"| S3
~~~

Vòng lặp này có thể tiêu tốn tài nguyên và chi phí đáng kể. Tách **input bucket** và **output bucket** là cách rõ ràng nhất; nếu cùng bucket, dùng prefix filter không chồng lấn và bảo vệ code khỏi xử lý output.

## 9. Retry, SQS visibility timeout và DLQ

### 9.1. Tại sao queue giúp hệ thống bền vững hơn?

Giả sử 10.000 ảnh được upload trong thời gian ngắn, nhưng một Lambda worker chỉ xử lý được 50 ảnh/giây.

Nếu kết nối trực tiếp, Lambda có thể chạm giới hạn concurrency/throttle và logic retry phải xử lý lượng tải đột biến. Nếu dùng SQS:

1. S3 gửi notification vào queue.
2. Queue lưu backlog trong thời gian retention.
3. Worker lấy message theo batch/tốc độ phù hợp.
4. Message xử lý thành công được xóa.
5. Message lỗi xuất hiện lại sau **visibility timeout** và có thể được gửi tới **DLQ** khi vượt maxReceiveCount đã cấu hình.

### 9.2. Visibility timeout không phải thời gian xử lý tối đa

**Visibility timeout** là thời gian một message đã được nhận tạm thời **ẩn khỏi consumer khác**. Nếu worker chưa xử lý xong và thời gian này hết hạn, message có thể được nhận lại, dẫn tới xử lý đồng thời/trùng.

Với Lambda event source mapping cho SQS, cấu hình visibility timeout phù hợp **thời gian chạy function, batch window và retry** theo hướng dẫn AWS. Không coi việc đặt timeout dài là đã có idempotency.

### 9.3. Dead-letter queue

**DLQ** chứa các message liên tục lỗi sau số lần xử lý được quy định. Nó giúp:

- Không để một message hỏng làm nghẽn toàn bộ pipeline.
- Điều tra nguyên nhân như file bị xóa, quyền KMS thiếu, định dạng ảnh lỗi.
- Cho phép sửa vấn đề rồi **redrive/reprocess** theo quy trình kiểm soát.

Cần có cảnh báo khi DLQ có message và chính sách retention đủ thời gian điều tra. **Có DLQ nhưng không theo dõi** vẫn có thể khiến dữ liệu quan trọng bị bỏ quên.

### 9.4. Partial batch response

Khi Lambda lấy batch SQS gồm nhiều message, nếu một message lỗi mà handler ném exception cho toàn batch, các message khác có thể được xử lý lại.

AWS Lambda hỗ trợ **partial batch response** cho SQS qua cấu hình **ReportBatchItemFailures**. Handler trả danh sách message ID thất bại, giúp xử lý lại đúng phần lỗi theo cơ chế hỗ trợ.

Ví dụ hình dạng response:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "failed-sqs-message-id"
    }
  ]
}
~~~

Đây là response của **Lambda SQS event source mapping**, không phải response của Lambda được S3 invoke trực tiếp. Với SNS/SQS lồng nhau hoặc nhiều S3 record trong một SQS message, phải quyết định rõ đơn vị retry và thiết kế idempotency.

### 9.5. Giới hạn của retry

Nếu source object đã bị xóa hoặc object phiên bản cũ không còn, replay message có thể thất bại vĩnh viễn. Cần:

- Chọn retention/versioning phù hợp.
- Phân biệt lỗi tạm thời (throttle, network) và lỗi vĩnh viễn (unsupported file, 404 không thể phục hồi).
- Chuyển lỗi vĩnh viễn sang trạng thái nghiệp vụ đã ghi nhận, không retry vô hạn.
- Có quy trình replay từ DLQ hoặc kho sự kiện khi phù hợp.

## 10. Bảo mật, phân quyền và giới hạn theo Region

### 10.1. Các lớp quyền cần phân biệt

| Luồng | Ai cần quyền? | Quyền điển hình |
| --- | --- | --- |
| Quản trị bucket notifications | Người/role triển khai | **s3:GetBucketNotification**, **s3:PutBucketNotification** trong phạm vi bucket. |
| S3 gửi message tới SQS | **s3.amazonaws.com** theo queue resource policy | **sqs:SendMessage** trên queue đích. |
| S3 publish SNS | **s3.amazonaws.com** theo topic policy | **sns:Publish** trên topic đích. |
| S3 invoke Lambda trực tiếp | **s3.amazonaws.com** theo Lambda resource-based policy | **lambda:InvokeFunction** trên function, hạn chế nguồn bucket. |
| Worker đọc object | Execution role của worker | **s3:GetObject** theo bucket/object ARN, **kms:Decrypt** khi áp dụng. |
| Worker ghi output | Execution role của worker | **s3:PutObject**, **kms:GenerateDataKey** hoặc quyền khóa cần thiết. |
| Lambda poll SQS | Execution role của Lambda | **sqs:ReceiveMessage**, **sqs:DeleteMessage**, **sqs:GetQueueAttributes** và quyền liên quan. |
| EventBridge gửi tới target | EventBridge service/rule role và target resource policy tùy loại target | Quyền invoke/send/StartExecution theo target và cách cấu hình. |

Cấp quyền **S3 gửi tới queue/topic/function** khác với quyền **worker đọc object**. Một cấu hình có queue nhận event thành công nhưng Lambda không đọc được S3 object vẫn thất bại ở bước xử lý.

### 10.2. Ví dụ SQS queue policy cho S3

Policy minh họa cho queue chỉ cho phép S3 gửi message từ bucket được chỉ định trong account nguồn:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyExampleBucketEvents",
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:image-processing-queue",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:s3:::example-incoming-images"
        },
        "StringEquals": {
          "aws:SourceAccount": "111122223333"
        }
      }
    }
  ]
}
~~~

**SourceArn** và **SourceAccount** giúp giới hạn nguồn, giảm nguy cơ tài nguyên trong tài khoản khác lợi dụng quyền service principal. Policy thực tế phải dùng đúng bucket ARN, account, queue ARN và điều kiện mà tài liệu dịch vụ yêu cầu.

**Để queue nhận được message không cần mở S3 bucket thành public**. Public bucket là quyết định phân quyền dữ liệu riêng, thường không phù hợp với dữ liệu người dùng nhạy cảm.

### 10.3. Mã hóa SSE-KMS

Nếu SQS queue hoặc SNS topic được mã hóa bằng **customer managed KMS key**, policy của key có thể cần cho phép service S3 sử dụng quyền liên quan như **kms:GenerateDataKey** và **kms:Decrypt** theo hướng dẫn cho loại destination. Những AWS managed key của destination không phải lúc nào cũng cho phép cập nhật key policy theo nhu cầu tích hợp.

Nếu object nguồn được mã hóa bằng **SSE-KMS**, Lambda/worker đọc object cũng cần quyền sử dụng key thích hợp. Các quyền này **khác nhau**:

- KMS key mã hóa **queue/topic message** trong đường gửi notification.
- KMS key mã hóa **object S3** mà worker thực sự đọc/ghi.

Không cấp quyền KMS rộng toàn account nếu có thể giới hạn cụ thể key, role và điều kiện.

### 10.4. Region và cross-account

Với các **destination notification trực tiếp**, AWS có yêu cầu về **Region tương thích** giữa S3 bucket và destination như Lambda/SNS/SQS. Khi muốn chuyển event tới một Region hoặc account khác, hãy thiết kế tuyến được hỗ trợ qua EventBridge/SNS/SQS và những resource policies cần thiết.

**Cross-account không được giải quyết chỉ bằng việc biết ARN.** Cần quyền gửi ở destination và quyền quản trị/configuration của các account liên quan.

Ví dụ EventBridge có thể định tuyến event đến event bus ở account khác theo rule/role và bus policy được cấp quyền phù hợp. Khi làm cross-Region, xác minh khả năng routing, định tuyến target và chi phí truyền nhận sự kiện tại các Region liên quan.

### 10.5. Quyền tối thiểu và bảo vệ dữ liệu

Với pipeline xử lý ảnh:

- Người upload chỉ cần quyền ghi đúng prefix, có thể dùng presigned URL theo policy.
- Worker chỉ đọc prefix input được giao.
- Worker chỉ ghi prefix/bucket output.
- Metadata DB dùng quyền tối thiểu theo bảng/record phù hợp.
- CloudWatch Logs lưu dữ liệu cần điều tra, tránh log nội dung file hoặc thông tin cá nhân không cần.
- Bucket policy, S3 Block Public Access, mã hóa at rest/in transit, versioning và lifecycle cần được review riêng.

S3 Event Notifications **không phải cơ chế authorization**; event có thể phát từ một thao tác đã thành công nhưng worker vẫn phải xác minh object và nghiệp vụ trước khi xử lý.

## 11. Kiểm tra cấu hình qua AWS CLI (chỉ đọc)

Các lệnh sau không tạo, sửa, xóa hay invoke workflow. Cần AWS CLI cấu hình đúng account/Region và có quyền đọc tương ứng. Thay các tên/ID giả định bằng tài nguyên của môi trường được phép truy cập.

### 11.1. Xác định danh tính

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Một bucket S3 có Region riêng; các destination liên quan cần được kiểm tra đúng Region theo kiến trúc.

### 11.2. Xem notification configuration của bucket

~~~bash
aws s3api get-bucket-notification-configuration \
  --bucket example-incoming-images
~~~

Quan sát các trường:

- **LambdaFunctionConfigurations**: function ARN, Events và Filter.
- **QueueConfigurations**: queue ARN, Events và Filter.
- **TopicConfigurations**: topic ARN, Events và Filter.
- **EventBridgeConfiguration**: cấu hình bật gửi event tới EventBridge, khi có.

Nếu kết quả trả về **{}** hoặc không có cấu hình đích cụ thể, bucket có thể chưa cấu hình notification theo dạng đó. Nếu lệnh lỗi **AccessDenied**, hãy kiểm tra quyền đọc, không vội kết luận không có notification.

### 11.3. Xem versioning của bucket

~~~bash
aws s3api get-bucket-versioning \
  --bucket example-incoming-images
~~~

Kiểm tra **Status** (Enabled/Suspended hoặc không có trường Status) và xác định thiết kế idempotency phù hợp. Versioning suspended có behavior riêng với null version; không mặc định mọi object có versionId hữu ích.

### 11.4. Kiểm tra queue và DLQ

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/image-processing-queue \
  --attribute-names QueueArn Policy VisibilityTimeout RedrivePolicy ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
  --region ap-southeast-1
~~~

**ApproximateNumberOfMessages** là xấp xỉ backlog; **ApproximateNumberOfMessagesNotVisible** là số message đang bị ẩn theo trạng thái queue, không phải chính xác số lượng công việc đã hoàn tất. Kiểm tra **VisibilityTimeout**, **RedrivePolicy**, DLQ ARN và queue policy.

### 11.5. Xem Lambda policy và cấu hình

~~~bash
aws lambda get-function-configuration \
  --function-name image-worker \
  --region ap-southeast-1

aws lambda get-policy \
  --function-name image-worker \
  --region ap-southeast-1

aws lambda list-event-source-mappings \
  --function-name image-worker \
  --region ap-southeast-1
~~~

Với **S3 → Lambda trực tiếp**, quan tâm **get-policy** cho phép S3 invoke. Với **S3 → SQS → Lambda**, quan tâm **event source mapping**, execution role có quyền poll SQS và cấu hình partial batch response khi cần. Function có thể có policy resource-based mà không có event source mapping S3, vì hai cơ chế khác nhau.

### 11.6. Xem EventBridge rules và targets

~~~bash
aws events list-rules \
  --event-bus-name default \
  --region ap-southeast-1

aws events describe-rule \
  --name process-s3-objects \
  --event-bus-name default \
  --region ap-southeast-1

aws events list-targets-by-rule \
  --rule process-s3-objects \
  --event-bus-name default \
  --region ap-southeast-1
~~~

Không phải mọi rule trên default bus đều liên quan S3. Hãy kiểm tra **EventPattern** có source **aws.s3**, detail-type và bucket phù hợp. **get-bucket-notification-configuration** cũng cần cho thấy EventBridge delivery đã được bật trong mô hình sử dụng.

### 11.7. Đọc S3 object metadata

~~~bash
aws s3api head-object \
  --bucket example-incoming-images \
  --key incoming/example.jpg

aws s3api list-object-versions \
  --bucket example-incoming-images \
  --prefix incoming/example.jpg \
  --max-items 20
~~~

Lệnh **head-object** trên key không có VersionId có thể nhìn thấy **current version** mới hơn notification đang xử lý. Nếu worker cần tái hiện chính xác trạng thái quá khứ, dùng event versionId cùng dữ liệu versioning còn giữ và quyền tương ứng.

## 12. Giám sát và xử lý sự cố

### 12.1. Các tín hiệu đáng quan tâm

| Thành phần | Tín hiệu | Cách sử dụng |
| --- | --- | --- |
| S3 | Upload/PUT success, notification configuration, CloudTrail data events khi bật. | Xác minh object đã thực sự được ghi, bucket đúng. |
| SQS | Queue depth, AgeOfOldestMessage, NumberOfMessagesSent/Received/Deleted, DLQ depth. | Phát hiện backlog, consumer lỗi, mất cân bằng tốc độ. |
| Lambda | Invocations, Errors, Duration, Throttles, ConcurrentExecutions, async failures. | Tìm lỗi handler, timeout, concurrency. |
| SNS | Published/Delivered/Failed notifications tùy protocol. | Xác định subscriber không nhận được. |
| EventBridge | Matched/Invocations/FailedInvocations và target DLQ khi cấu hình. | Tìm lỗi rule, permissions, target. |
| Worker/app | Bucket/key/version, processing status, lỗi loại dữ liệu, kết quả output. | Điều tra tác động nghiệp vụ và replay. |

CloudWatch metrics, CloudTrail và logs chỉ hữu ích khi đã có cấu hình thu thập/quyền phù hợp. **CloudTrail data events cho S3 object thường cần được bật có chủ đích**; không nên mặc định mọi ObjectCreated đều đã được lưu trong audit trail đầy đủ.

### 12.2. Không thấy event sau khi upload

Kiểm tra theo thứ tự:

1. Upload có thật sự thành công và ghi vào **bucket/key** dự kiến không?
2. **get-bucket-notification-configuration** có loại event cần thiết chưa? Multipart upload có được bắt bằng **ObjectCreated:CompleteMultipartUpload** hoặc ObjectCreated:* không?
3. Prefix/suffix có khớp chính xác key (phân biệt chữ hoa/thường) không?
4. Destination ARN, Region và resource policy có đúng không?
5. Với SQS/SNS SSE-KMS, key policy có cho phép service sử dụng không?
6. Nếu dùng EventBridge, đã bật EventBridge delivery và rule pattern/target chính xác chưa?
7. Kiểm tra test message, queue metrics, Lambda metrics, EventBridge metrics và thời gian xử lý bất đồng bộ.

**Đừng sửa bằng cách mở S3 bucket public**. Việc gửi notification từ S3 đến destination là cơ chế resource policy riêng.

### 12.3. Event có trong SQS nhưng Lambda không xử lý

Kiểm tra:

- Event source mapping **Enabled** và trỏ đúng queue.
- Execution role có quyền poll/xóa message.
- Function không bị lỗi do timeout, bộ nhớ, concurrency hoặc biến môi trường.
- Visibility timeout phù hợp thời gian xử lý/batch.
- Parser đã đọc **SQS body** thành JSON S3 event chưa.
- Nếu queue dùng encryption, có quyền KMS cần thiết không.
- DLQ có message và cảnh báo đã kích hoạt chưa.

Queue depth tăng liên tục gợi ý tốc độ xử lý thấp hơn tốc độ nhận hoặc worker lỗi. Tăng concurrency có thể giúp throughput nhưng cũng có thể gây quá tải S3 API, database hoặc dịch vụ downstream.

### 12.4. Lambda bị gọi lặp vô hạn

Triệu chứng: số invocations tăng nhanh sau khi triển khai thumbnail job, output object liên tục tạo object mới.

Nguyên nhân thường là notification nhận cả object do function **tự ghi vào bucket nguồn**. Cách xử lý:

1. Tạm dừng/kiểm soát vòng lặp bằng biện pháp vận hành thích hợp theo quyền được giao.
2. Chuyển output sang **bucket riêng** hoặc prefix không thuộc filter.
3. Tăng lớp guard trong code, chỉ chấp nhận prefix/input format dự kiến.
4. Kiểm tra notification configuration và số object phát sinh ngoài ý muốn.
5. Rà soát log, phí Lambda/S3/queue và tránh tái diễn bằng test.

### 12.5. Cùng event được xử lý hai lần

Đây có thể là **hành vi đúng theo at-least-once delivery**, không nhất thiết là lỗi S3. Xem idempotency state, sequencer/versionId, retry, visibility timeout và số lần nhận queue. Nếu có side effect không lặp an toàn, sửa logic xử lý theo transaction/conditional state, không chỉ hy vọng hệ thống ngừng gửi trùng.

### 12.6. Event A xử lý sau event B

Khi cùng key được ghi đè nhanh, bản tin không bảo đảm thứ tự. Giải pháp là so sánh sequencer đối với những event đủ điều kiện, version-specific processing và ghi trạng thái có điều kiện.

Không lấy **eventTime** để giả định một thứ tự đáng tin cậy cho mọi event từ nhiều key hoặc kết hợp nhiều dịch vụ.

## 13. Chi phí, giới hạn và phương án mở rộng

Event processing phát sinh chi phí từ nhiều thành phần, dù bản thân mỗi notification chỉ là thông điệp nhỏ.

| Thành phần | Chi phí cần ước tính | Cách kiểm soát |
| --- | --- | --- |
| S3 | PUT/GET/HEAD/LIST, storage, data transfer, versioning/lifecycle. | Filter event, tránh HEAD/GET không cần, dùng storage class đúng. |
| SQS | Số API requests, payload, DLQ/backlog và chi phí liên quan. | Batch và long polling phù hợp, quản lý retention. |
| SNS | Notification publish/delivery theo protocol, payload/traffic. | Tránh fan-out không cần thiết và subscription trùng. |
| Lambda | Invocations, thời gian/GB-second, concurrency, logs và retry. | Tối ưu memory/time, batch, giới hạn luồng. |
| EventBridge | Events/target delivery, rule/pipes/archive/replay tùy cấu hình và bảng giá. | Pattern hiệu quả, tránh rule/target dư thừa. |
| KMS | Số lượt sử dụng khóa/API khi mã hóa tích hợp. | Đánh giá lượng request và quyền cần thiết. |
| Monitoring | CloudWatch Logs, metrics, CloudTrail data events và lưu retention. | Chọn log/retention đủ điều tra, tránh log payload nhạy cảm. |

Ví dụ 1 triệu ảnh/ngày có thể tạo 1 triệu hoặc nhiều hơn số lần nhận event (do retry/duplicate); worker có thể gọi thêm HEAD/GET và PUT kết quả. Không chỉ lấy **số object mới** làm tổng số request của pipeline.

### 13.1. Một phép tính năng lực xử lý

Giả sử trung bình có **120 object/phút**, mỗi worker xử lý **1 object trong 2 giây**.

- Một worker có thể xử lý khoảng **30 object/phút** trong điều kiện lý tưởng.
- Để theo kịp 120 object/phút cần khoảng **4 worker hoạt động đồng thời**, chưa tính overhead, variance và retry.
- Để chịu spike 10 lần, cần khả năng đệm queue và kế hoạch scale/concurrency phù hợp.

Đây chỉ là **ước tính năng lực lý thuyết**. Giới hạn thực còn ở mạng, object size, SDK, Lambda concurrency, database, KMS và downstream. Cần đo traffic thật và đặt alarm theo backlog age.

### 13.2. Những giới hạn cần kiểm tra

- Loại bucket S3, event type và destination được tính năng hỗ trợ; các bucket đặc thù như **directory bucket/S3 Express One Zone** có khả năng hỗ trợ khác với general-purpose bucket.
- Region và cross-account permissions.
- Quota notification rules/filter và quota của Lambda/SQS/SNS/EventBridge.
- Số lượng/loại target, khả năng FIFO khi cần xử lý thứ tự.
- Timeout, message retention và giới hạn payload của từng dịch vụ.
- Quy tắc event filter chồng lấn và khả năng thay đổi cả bucket notification configuration.

Khi mở rộng production, kiểm tra tài liệu **Service Quotas** và tài liệu tương ứng theo Region, thay vì ghi nhớ một con số cố định.

## 14. Tình huống thực tế

### Tình huống A — Tạo thumbnail cho ảnh người dùng

**Yêu cầu:** Ứng dụng nhận ảnh JPG/PNG. Sau upload, tạo thumbnail và cập nhật URL.

**Thiết kế tham khảo:**

1. Người dùng upload vào **uploads-original/** bằng API/role/presigned URL đúng quyền.
2. S3 gửi ObjectCreated tới **SQS Standard** với filter cho prefix input và loại file phù hợp.
3. Lambda đọc event, decode key, kiểm tra file type/size và lấy đúng version nếu cần.
4. Lambda tạo ảnh tại **bucket outputs** khác; output key theo source version/variant.
5. Worker cập nhật trạng thái trong database bằng thao tác có điều kiện, để retry không tạo metadata trùng.
6. Theo dõi queue backlog, DLQ, lỗi Lambda và chất lượng ảnh.

**Bài học:** Dùng queue để chịu burst; tách input/output để tránh recursion; sử dụng idempotency vì event trùng không hiếm tới mức có thể bỏ qua về thiết kế.

### Tình huống B — Ingest CSV vào data lake

**Yêu cầu:** Mỗi file CSV mới dưới **landing/** cần kiểm tra schema và kích hoạt ETL.

**Thiết kế:** S3 EventBridge delivery → rule lọc Object Created của bucket/prefix → Step Functions hoặc queue/worker; workflow validate schema, ghi trạng thái xử lý, gửi lỗi sang DLQ/queue nếu cần. Với batch lớn hoặc xử lý nặng, dùng ECS/Glue/Batch phù hợp.

**Bài học:** Một S3 event **không phải** chứng minh dữ liệu business hợp lệ. Validation, schema version, retry, idempotency và audit vẫn thuộc ứng dụng.

### Tình huống C — Cập nhật chỉ mục tìm kiếm

**Yêu cầu:** Index tài liệu khi upload mới, xóa khỏi kết quả khi object bị xóa.

**Thiết kế:** Lắng nghe **ObjectCreated** và **ObjectRemoved**, lưu trạng thái theo bucket/key/version hoặc latest sequencer; cập nhật index bằng thao tác có điều kiện để event cũ không ghi đè event mới.

**Bài học:** Vì không bảo đảm thứ tự, xử lý đơn giản “event nào đến sau thì thắng” có thể khiến kết quả index sai.

### Tình huống D — Nhiều team cùng dùng một bucket

**Yêu cầu:** Team Thumbnail, Compliance và Analytics đều cần event.

**Thiết kế:** S3 → SNS với subscriber queue riêng hoặc S3 → EventBridge với các rule riêng, quản lý ownership, IAM, lưu log và DLQ tương ứng. Không để từng nhóm ghi **PutBucketNotificationConfiguration** độc lập và vô tình xóa cấu hình của nhóm khác.

**Bài học:** Thiết kế fan-out và quản lý cấu hình tập trung giúp các consumer phát triển độc lập.

### Tình huống E — File nhập bị ghi đè liên tục

**Yêu cầu:** Báo cáo **report.csv** bị upload lại nhiều lần; chỉ kết quả từ version cuối được hiển thị.

**Thiết kế:** Bật S3 versioning khi phù hợp, xử lý theo versionId, dùng sequencer cho PUT/DELETE cùng key khi có, rồi cập nhật con trỏ “latest” bằng điều kiện so sánh phiên bản/seq. Worker xử lý event cũ vẫn có thể lưu bản kết quả theo version nhưng không được làm lùi trạng thái latest.

**Bài học:** Không đồng nhất thời điểm worker hoàn thành với thời điểm object mới nhất được tạo.

## 15. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “S3 gửi event chính xác một lần.” | S3 Event Notifications theo **at-least-once**, có thể trùng; worker phải idempotent. |
| “S3 đảm bảo thứ tự khi các object được upload.” | Không đảm bảo thứ tự notification; sequencer chỉ hỗ trợ một số event trên **cùng key**. |
| “ObjectCreated event chứa toàn bộ file.” | Event chứa metadata; worker cần gọi S3 API để lấy nội dung. |
| “Bản tin eventName chứa s3:ObjectCreated:Put.” | Trong record notification, eventName thường là **ObjectCreated:Put** (không có tiền tố s3:). |
| “Key trong event dùng trực tiếp không cần decode.” | S3 notification trực tiếp có key URL form encoded; ví dụ space thành +. |
| “Chọn ObjectCreated:Put là bắt được mọi cách upload.” | Multipart hoàn tất có event **CompleteMultipartUpload**; chọn nhóm event phù hợp. |
| “Lambda ghi output vào cùng bucket luôn an toàn.” | Có thể tạo vòng lặp nếu output khớp điều kiện trigger. |
| “SQS giúp đảm bảo không bị trùng.” | SQS Standard vẫn có duplicate/redelivery; queue chủ yếu giúp đệm và retry. |
| “Không cần DLQ vì Lambda tự retry.” | Retry có giới hạn và có thể thất bại mãi; cần DLQ/giám sát/phục hồi phù hợp. |
| “Bucket public mới gửi event tới SQS được.” | S3 gửi bằng service principal thông qua queue/topic/function policy; bucket public không liên quan. |
| “IAM role của Lambda đủ để S3 invoke trực tiếp.” | Lambda cần **resource-based permission** cho S3; execution role phục vụ code chạy trong Lambda. |
| “EventBridge dùng cấu trúc Records[] giống S3 notification.” | EventBridge event dùng source/detail-type/detail schema khác. |
| “S3 event đã được ghi trong CloudTrail mặc định.” | CloudTrail data events S3 cần được cấu hình phù hợp; notification không thay audit. |
| “Đã có versioning là pipeline không cần idempotency.” | Versioning giúp định danh phiên bản, không ngăn xử lý trùng hoặc side effects lặp. |
| “S3 lưu xong nghĩa là xử lý ảnh đã xong.” | Notification và xử lý downstream bất đồng bộ, có thể lag/fail. |
| “Bất kỳ consumer nào cũng có thể sửa notification config mà không ảnh hưởng nhóm khác.” | Thao tác ghi notification config có thể thay toàn bộ cấu hình bucket. |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Upload object thành công thì Lambda chắc đã xử lý xong ngay không?  
**Đáp án:** Không. S3 notification và pipeline downstream là bất đồng bộ; phải có trạng thái/quan sát riêng cho công việc xử lý.

**Câu 2.** Vì sao cần xử lý event trùng?  
**Đáp án:** S3 Event Notifications theo at-least-once; event có thể phát/giao lại và SQS Standard cũng có thể redeliver.

**Câu 3.** Một object upload bằng multipart thường cần bắt event nào?  
**Đáp án:** **s3:ObjectCreated:CompleteMultipartUpload** hoặc nhóm **s3:ObjectCreated:*** theo mục tiêu.

**Câu 4.** Từ record S3 trực tiếp, làm thế nào lấy đúng key **incoming/photo one.jpg**?  
**Đáp án:** Đọc **record.s3.object.key** và giải mã URL form encoding, ví dụ Python **unquote_plus**.

**Câu 5.** Có thể dùng sequencer để so sánh Object A với Object B khác key không?  
**Đáp án:** Không. Sequencer dùng để so sánh trình tự những PUT/DELETE events thích hợp của **cùng key**.

**Câu 6.** Worker tạo thumbnail nên ghi vào đâu để tránh loop?  
**Đáp án:** Ưu tiên output bucket riêng; hoặc prefix output nằm ngoài filter trigger và có guard trong code.

**Câu 7.** Khi S3 gửi notification đến queue mã hóa bằng SSE-KMS, quyền nào cần xem thêm?  
**Đáp án:** Queue resource policy cho **sqs:SendMessage** từ S3 và KMS key policy cho phép service S3 sử dụng khóa theo hướng dẫn.

**Câu 8.** Khi queue dồn message, SQS có tự xử lý object không?  
**Đáp án:** Không. Queue chỉ giữ/chuyển message; Lambda hoặc consumer khác cần poll và xử lý bằng API S3.

**Câu 9.** Với EventBridge, rule có thể lọc key theo prefix ở đâu?  
**Đáp án:** Trong event pattern trên **detail.object.key**, kèm source/detail-type/bucket khi cần.

**Câu 10.** Vì sao không dùng SQS message ID làm khóa chống trùng sự kiện S3 duy nhất?  
**Đáp án:** Cùng logical S3 event có thể tạo/giao nhiều message SQS với ID khác nhau; cần khóa dựa trên object/version/sequencer hoặc business ID.

**Câu 11.** Nếu key bị overwrite sau khi event cũ phát ra và bucket không bật versioning, worker GET key sẽ nhận gì?  
**Đáp án:** Thường là trạng thái object hiện hành, có thể mới hơn event cũ; không đảm bảo tái hiện nội dung trước khi overwrite.

**Câu 12.** Điểm khác chính giữa S3 → Lambda và S3 → SQS → Lambda?  
**Đáp án:** Tuyến có SQS bổ sung hàng đợi bền vững/backlog, visibility timeout, DLQ và khả năng kiểm soát tốc độ; đổi lại cần quản lý consumer/queue/chi phí.

**Câu 13.** Muốn nhiều nhóm xử lý cùng event mà quản lý routing tập trung nên cân nhắc gì?  
**Đáp án:** SNS fan-out hoặc EventBridge rules/targets, thường với consumer queue riêng và quyền/giám sát rõ ràng.

**Câu 14.** Vì sao S3 notification không thay CloudTrail?  
**Đáp án:** Notification chỉ bao phủ những event object được hỗ trợ và cấu hình; audit API/config/data events có cơ chế, phạm vi và mục đích riêng.

**Câu 15.** Những bước quan trọng nhất khi không nhận event là gì?  
**Đáp án:** Xác minh upload, event type, prefix/suffix, Region/destination ARN, resource policy/KMS, EventBridge rule nếu dùng, rồi xem queue/Lambda/metrics/logs.

## 17. Ghi nhớ

**S3 Event Notifications** là cầu nối giữa object storage và kiến trúc xử lý sự kiện/serverless. S3 phát **metadata về thay đổi object** tới Lambda, SQS, SNS hoặc EventBridge để hệ thống có thể tự động xử lý ảnh, tài liệu, ETL, chỉ mục và nhiều workflow khác.

Thiết kế tốt cần chú ý năm điểm:

1. **Đúng sự kiện:** chọn event type, bucket, prefix/suffix hoặc EventBridge pattern chính xác.
2. **Đúng đích:** chọn Lambda trực tiếp cho tác vụ đơn giản, SQS để đệm/khôi phục, SNS để fan-out, EventBridge để định tuyến linh hoạt.
3. **Đúng quyền:** bucket notification configuration, resource policies của destination, IAM execution role, KMS key policy và Region.
4. **Chịu lỗi:** at-least-once, duplicates, event out-of-order, versioning/sequencer, retry/DLQ và idempotency có thể kiểm chứng.
5. **Vận hành:** tránh vòng lặp khi ghi output, theo dõi backlog/Errors/DLQ, kiểm thử replay và tính chi phí theo toàn bộ pipeline.

Khi triển khai hệ thống AWS thực tế, hãy xem **object được lưu thành công**, **event được gửi**, **worker xử lý thành công** và **nghiệp vụ cập nhật chính xác** là những trạng thái khác nhau cần được theo dõi riêng. Cách tiếp cận này giúp ứng dụng an toàn, có khả năng phục hồi, mở rộng và kiểm soát chi phí.

### Tài liệu AWS tham khảo

- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html) — khái niệm, loại event và destination.
- [Event notification types and destinations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-event-types-and-destinations.html) — danh sách event type, đích và điều kiện.
- [Event message structure](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html) — cấu trúc Records, key encoding và sequencer.
- [Configuring event notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-event-notifications.html) — cách thiết lập và kiểm tra.
- [Filtering event notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-filtering.html) — prefix/suffix và quy tắc chồng lấn.
- [Granting permissions to publish messages](https://docs.aws.amazon.com/AmazonS3/latest/userguide/grant-destinations-permissions-to-s3.html) — policy cho SQS/SNS/Lambda và KMS.
- [Using EventBridge with Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventBridge.html) — chuyển event từ S3 tới EventBridge.
- [Process Amazon S3 event notifications with Lambda](https://docs.aws.amazon.com/lambda/latest/dg/with-s3.html) — Lambda trigger và lưu ý vòng lặp.
- [Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html) — batch, visibility timeout, partial failures và retry.

