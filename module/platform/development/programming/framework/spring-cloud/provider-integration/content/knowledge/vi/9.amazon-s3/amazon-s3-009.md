# Amazon S3: Sự kiện S3 và phối hợp xử lý tệp qua hàng đợi

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, ứng dụng Spring Boot tích hợp với dịch vụ managed của AWS, Azure và Google Cloud để xử lý storage, messaging, dữ liệu, danh tính và quyền. Khi người dùng upload tài liệu lên **Amazon S3**, ứng dụng thường cần tiếp tục quét virus, tạo thumbnail, trích xuất nội dung, chuyển đổi định dạng hoặc cập nhật trạng thái nghiệp vụ. Nếu API upload phải chờ tất cả công việc này hoàn tất, thời gian phản hồi sẽ dài và việc xử lý khó mở rộng.

S3 có thể phát **event notification** khi object được tạo, xóa hoặc có thay đổi thuộc nhóm sự kiện được hỗ trợ. Sự kiện có thể được gửi đến **Amazon SQS**, **Amazon SNS**, **AWS Lambda** hoặc **Amazon EventBridge**. Một consumer Spring Boot đọc message từ queue, lấy object tương ứng từ S3 và xử lý theo một quy trình có khả năng retry.

Bài này tập trung vào mô hình **S3 → SQS → Spring Boot worker**, đồng thời so sánh SNS/EventBridge, giải thích event delivery, duplicate/out-of-order, idempotency, dead-letter queue và cách kiểm thử.

Sau bài học, bạn có thể:

1. Cấu hình S3 event notification theo event type, prefix và suffix.
2. Cấp queue policy để S3 được phép gửi message vào SQS.
3. Dùng Spring Cloud AWS SQS listener để nhận và phân tích S3 event.
4. Tải object đúng phiên bản, xử lý file và cập nhật trạng thái nghiệp vụ.
5. Thiết kế consumer chịu được duplicate, sự kiện đến sai thứ tự, retry và lỗi xử lý.
6. Cấu hình visibility timeout, DLQ, quyền IAM và giám sát queue.
7. So sánh SQS, SNS và EventBridge khi xây dựng pipeline xử lý tệp.

> **Phạm vi:** Ví dụ sử dụng Spring Cloud AWS hiện đại (namespace `io.awspring.cloud`) và AWS SDK for Java v2 (namespace `software.amazon.awssdk`). Chọn phiên bản thư viện tương thích với Spring Boot của dự án. Bucket, queue, account ID và Region trong bài là dữ liệu minh họa.

## 1. Vì sao cần event-driven file processing?

Giả sử người dùng tải một file PDF lên S3. Sau khi nhận file, hệ thống cần:

- Kiểm tra file có đúng loại và kích thước không.
- Quét malware hoặc chuyển file sang vùng quarantine.
- Trích xuất text, OCR hoặc metadata.
- Tạo preview/thumbnail.
- Lưu kết quả và trạng thái xử lý vào database.
- Thông báo cho người dùng khi hoàn tất.

Nếu API upload gọi tuần tự tất cả các bước, request có thể kéo dài nhiều giây hoặc vài phút. Khi OCR hoặc scanner lỗi, người dùng có thể phải upload lại dù file đã được lưu thành công.

Mô hình event-driven tách **nhận file** khỏi **xử lý file**:

~~~mermaid
flowchart LR
    U["Browser / mobile"] -->|"Upload"| API["Spring Boot API"]
    API -->|"PUT object"| S3["S3 bucket: incoming/"]
    API -->|"PENDING"| DB["Database nghiệp vụ"]
    S3 -->|"ObjectCreated event"| Q["SQS standard queue"]
    Q --> W["Spring Boot worker"]
    W -->|"GET object"| S3
    W -->|"Scan / OCR / thumbnail"| P["Processing services"]
    W -->|"READY / FAILED"| DB
~~~

API upload có thể trả về sớm với trạng thái `PENDING`. Worker xử lý sau và cập nhật `READY` hoặc `FAILED`. SQS giữ message trong queue khi worker chưa nhận, giúp tách tốc độ upload khỏi tốc độ xử lý.

### 1.1. Event là thông báo, không phải nội dung file

S3 event notification thường chứa **thông tin tham chiếu** như:

- Bucket và object key.
- Loại sự kiện (ví dụ object được tạo hoặc xóa).
- Version ID nếu bucket bật versioning và event có trường này.
- Kích thước, ETag và sequencer ở những event có hỗ trợ.
- Thông tin request/response liên quan.

Message **không chứa toàn bộ byte của file**. Consumer dùng bucket/key/version ID để gọi S3 GET. Cách này tránh đưa file lớn vào SQS message và cho phép worker kiểm soát streaming.

### 1.2. Luồng xử lý điển hình

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant API as Spring Boot API
    participant DB as Database
    participant S3 as Amazon S3
    participant Q as Amazon SQS
    participant W as File worker

    User->>API: Upload tài liệu
    API->>DB: Tạo bản ghi PENDING
    API->>S3: PUT incoming/{tenant}/{uuid}
    S3-->>API: PUT thành công
    API-->>User: 202 Accepted + documentId
    S3->>Q: ObjectCreated notification
    Q-->>W: Message chứa bucket/key/version
    W->>DB: Claim công việc/idempotency
    W->>S3: GET object
    S3-->>W: Stream nội dung
    W->>W: Quét, OCR, tạo kết quả
    W->>DB: Cập nhật READY
    W-->>Q: Acknowledge message
~~~

Trong hệ thống thật, cần xử lý trường hợp database ghi `PENDING` thành công nhưng PUT S3 thất bại, hoặc PUT thành công nhưng cập nhật database gặp lỗi. S3 và database không chia sẻ một transaction ACID; thiết kế cần trạng thái, retry và đối soát.

## 2. Các loại S3 event và cấu hình filter

### 2.1. Event type thường dùng

S3 event notification có thể phát các nhóm sự kiện, trong đó thường gặp:

| Nhóm event | Ví dụ tên event | Use case |
| --- | --- | --- |
| Object created | `s3:ObjectCreated:Put` | Xử lý sau PUT đơn |
| Object created | `s3:ObjectCreated:Post` | Xử lý sau browser form POST |
| Object created | `s3:ObjectCreated:Copy` | Xử lý object được copy |
| Object created | `s3:ObjectCreated:CompleteMultipartUpload` | Xử lý sau khi multipart upload hoàn tất |
| Object removed | `s3:ObjectRemoved:Delete` | Đồng bộ trạng thái sau xóa |
| Object removed | `s3:ObjectRemoved:DeleteMarkerCreated` | Theo dõi delete marker ở bucket versioned |
| Restore | `s3:ObjectRestore:Completed` | Xử lý object archive sau khi restore hoàn tất |
| Tagging | `s3:ObjectTagging:Put` | Phản ứng với thay đổi tag nếu nghiệp vụ cần |

`s3:ObjectCreated:*` có thể đăng ký cả nhóm tạo object. Chỉ đăng ký những event thực sự cần; nếu worker chỉ xử lý file mới upload, không nhất thiết subscribe delete/tagging/restore.

Tên event trong payload như `ObjectCreated:Put` thường **không có tiền tố** `s3:`. Tiền tố `s3:` được dùng trong cấu hình notification.

### 2.2. Lọc theo prefix và suffix

Nếu bucket có nhiều vùng dữ liệu:

~~~text
incoming/          # File vừa upload, cần xử lý
processed/         # Kết quả đã xử lý
thumbnails/        # Ảnh preview
archive/           # Bản lưu
~~~

Chỉ muốn worker xử lý PDF mới dưới `incoming/`, có thể cấu hình filter:

- Prefix: `incoming/`
- Suffix: `.pdf`

Filter giúp S3 chỉ gửi notification phù hợp tới destination. Filter prefix/suffix là **so khớp chuỗi**, không phải regex hoặc glob. Không dùng ký tự `*` như wildcard trong giá trị filter. Các filter rule chồng lấn cho cùng event có thể bị từ chối khi cấu hình; thiết kế prefix/suffix không mơ hồ.

**Quan trọng:** nếu worker tạo thumbnail trong cùng prefix đang subscribe, thao tác PUT thumbnail có thể tạo event mới và kích hoạt worker lặp lại. Nên ghi output sang prefix khác, hoặc cấu hình filter chỉ bắt đầu từ vùng upload đầu vào.

### 2.3. Event test và event payload

Khi cấu hình notification, S3 có thể gửi một **test event** để xác nhận destination. Test event có trường `Event` với giá trị kiểu `s3:TestEvent` và không có cấu trúc `Records` giống object event. Consumer không nên giả định mọi message đều có `Records`.

Event notification cũng có thể chứa nhiều record trong mảng `Records`. Consumer phải duyệt từng record, thay vì giả định mỗi message luôn chỉ có một object.

## 3. Chọn SQS, SNS hay EventBridge?

S3 có thể gửi event đến nhiều loại destination. Lựa chọn phụ thuộc cách hệ thống cần phân phối công việc.

| Destination | Mô hình | Phù hợp khi | Lưu ý |
| --- | --- | --- | --- |
| **SQS standard** | Queue lưu message cho consumer xử lý | Một nhóm worker cần kéo việc theo năng lực | At-least-once, có thể duplicate và không đảm bảo thứ tự |
| **SNS** | Publish/subscribe fan-out | Một event cần gửi tới nhiều subscriber | Mỗi subscriber cần endpoint/queue riêng; retry và filter theo cấu hình |
| **EventBridge** | Event bus và rule định tuyến | Cần lọc theo event detail, nhiều target, tích hợp event-driven rộng hơn | Payload/schema và retry/DLQ theo cấu hình EventBridge |
| **Lambda** | Gọi function theo event | Xử lý nhỏ, ngắn, phù hợp mô hình serverless | Cần kiểm soát retry, concurrency và thời gian chạy |

### 3.1. S3 → SQS standard

Đây là mô hình phù hợp cho file-processing worker:

- S3 gửi notification tới queue.
- Nhiều worker có thể đọc cùng queue để mở rộng xử lý.
- Message vẫn nằm trong queue nếu chưa được consumer nhận.
- SQS visibility timeout tạm ẩn message trong lúc worker xử lý.
- Khi xử lý thành công, consumer acknowledge/delete message; nếu lỗi, message có thể xuất hiện lại sau visibility timeout.

S3 event notification trực tiếp hỗ trợ **SQS standard queue**. Không cấu hình S3 gửi trực tiếp vào **SQS FIFO queue**. Nếu nghiệp vụ cần FIFO, có thể đưa sự kiện qua **EventBridge** rồi route tới FIFO queue theo cấu hình target phù hợp; vẫn phải tự thiết kế idempotency và group/order theo object.

### 3.2. S3 → SNS → nhiều SQS queue

Nếu cùng một file cần nhiều quy trình độc lập:

~~~mermaid
flowchart LR
    S3["S3 ObjectCreated"] --> SNS["SNS topic"]
    SNS --> Q1["SQS: virus-scan"]
    SNS --> Q2["SQS: OCR"]
    SNS --> Q3["SQS: audit"]
    Q1 --> W1["Scanner worker"]
    Q2 --> W2["OCR worker"]
    Q3 --> W3["Audit worker"]
~~~

SNS fan-out cho phép mỗi consumer xử lý theo tốc độ và chính sách retry riêng. Mỗi queue subscriber có thể có DLQ riêng để lỗi OCR không làm tắc scanner hoặc audit. Khi SNS gửi tới SQS, body mặc định có thể là **SNS envelope** chứa payload S3 trong trường `Message`; nếu bật raw message delivery, body mới là payload S3 trực tiếp. Consumer phải biết chế độ subscription đang dùng và parse đúng một dạng, không thử decode mù cả hai.

### 3.3. S3 → EventBridge

Bật EventBridge cho bucket khi cần rule routing linh hoạt, nhiều loại target hoặc tích hợp nhiều dịch vụ. EventBridge event có **schema khác** S3 notification envelope truyền trực tiếp đến SQS/SNS. Ví dụ event detail thường đặt bucket/key dưới `detail.bucket.name` và `detail.object.key`, không dùng `Records[].s3.bucket.name`.

**Không dùng chung parser cho S3 notification và EventBridge payload nếu chưa có adapter chuẩn hóa.** Tách hai adapter, chuyển chúng về một domain event nội bộ như `ObjectCreatedEvent`.

## 4. Cấu hình S3 gửi event đến SQS

### 4.1. Tạo queue và DLQ

Tạo một SQS standard queue cho công việc và một dead-letter queue:

~~~text
file-processing-dlq
file-processing-queue
  └── redrive policy → file-processing-dlq
~~~

Queue chính nhận sự kiện mới. Nếu message được nhận nhiều lần nhưng vẫn thất bại, redrive policy chuyển message sang DLQ sau số lần nhận tối đa đã cấu hình. DLQ cho phép điều tra payload, lỗi và quyết định redrive sau khi sửa nguyên nhân.

### 4.2. Queue policy cho phép S3 gửi message

S3 cần được phép gọi `sqs:SendMessage` tới queue. Ví dụ resource policy cho queue:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3BucketNotifications",
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:file-processing-queue",
      "Condition": {
        "ArnLike": {
          "aws:SourceArn": "arn:aws:s3:::training-private-files"
        },
        "StringEquals": {
          "aws:SourceAccount": "111122223333"
        }
      }
    }
  ]
}
~~~

Thay Region, account ID, queue ARN và bucket ARN bằng giá trị của môi trường. Điều kiện `aws:SourceArn` và `aws:SourceAccount` giới hạn bucket nào được phép gửi message, giảm nguy cơ confused deputy.

Bucket và SQS queue phải ở **cùng AWS Region** cho cấu hình notification trực tiếp. Nếu queue dùng SSE-KMS với customer-managed key, cần xem thêm key policy để dịch vụ gửi message được mã hóa theo cấu hình queue.

### 4.3. Notification configuration

Ví dụ cấu hình gửi các event ObjectCreated dưới prefix `incoming/` và suffix `.pdf` tới queue:

~~~json
{
  "QueueConfigurations": [
    {
      "Id": "incoming-pdf-created",
      "QueueArn": "arn:aws:sqs:ap-southeast-1:111122223333:file-processing-queue",
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
              "Value": ".pdf"
            }
          ]
        }
      }
    }
  ]
}
~~~

Có thể lưu cấu hình thành file JSON rồi dùng AWS CLI trong sandbox:

~~~bash
aws s3api put-bucket-notification-configuration \
  --bucket training-private-files \
  --notification-configuration file://notification.json
~~~

Lệnh `put-bucket-notification-configuration` thay thế **toàn bộ notification configuration** của bucket theo payload gửi lên, không chỉ thêm một rule mới. Trước khi chạy ở bucket dùng chung, phải quản lý tất cả notification cần giữ trong cùng cấu hình và kiểm tra destination/queue policy.

### 4.4. Quy trình xác nhận destination

S3 kiểm tra destination khi lưu cấu hình. Nếu queue policy thiếu quyền hoặc ARN sai, thao tác cấu hình có thể thất bại. Trình tự nên là:

1. Tạo queue và DLQ.
2. Cấu hình redrive policy cho queue chính.
3. Cập nhật queue resource policy cho phép S3 gửi từ đúng bucket/account.
4. Cấu hình notification trên bucket.
5. Upload object test đúng prefix/suffix.
6. Xác nhận message xuất hiện ở queue và worker xử lý thành công.

Không bật event trên bucket production khi chưa có consumer idempotent, queue policy và cơ chế DLQ/monitoring.

## 5. Payload S3 event và cách đọc trong Spring Boot

### 5.1. Ví dụ cấu trúc notification trực tiếp

Payload minh họa rút gọn:

~~~json
{
  "Records": [
    {
      "eventVersion": "2.1",
      "eventSource": "aws:s3",
      "awsRegion": "ap-southeast-1",
      "eventTime": "2026-11-24T02:15:30.000Z",
      "eventName": "ObjectCreated:Put",
      "s3": {
        "bucket": {
          "name": "training-private-files"
        },
        "object": {
          "key": "incoming%2Ftenant-42%2Fdocument-123.pdf",
          "size": 8192,
          "eTag": "example-etag",
          "versionId": "example-version-id",
          "sequencer": "0067A123456789ABCD"
        }
      }
    }
  ]
}
~~~

Các trường có thể khác theo event type, cấu hình versioning và schema version. `versionId`, `size` hoặc `sequencer` không nhất thiết có mặt trong mọi record. `eventName` ví dụ `ObjectCreated:Put` không có tiền tố `s3:`.

**Object key trong S3 notification được URL-encode theo dạng form encoding.** Vì vậy key có khoảng trắng có thể biểu diễn bằng dấu `+`; cần decode UTF-8 đúng cách trước khi gọi S3. Không lấy chuỗi encoded trong JSON rồi đưa thẳng vào `GetObjectRequest`.

### 5.2. Dependency Spring Cloud AWS SQS

Bên cạnh S3 starter, thêm starter SQS để sử dụng listener:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
</dependencies>
~~~

Dùng BOM để đồng bộ các module Spring Cloud AWS. Phiên bản phải tương thích với Spring Boot; không trộn starter đời cũ với AWS SDK v2 trong ví dụ này.

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: training-private-files
  sqs:
    file-events-queue: file-processing-queue
~~~

`app.storage.bucket` và `app.sqs.file-events-queue` là property riêng của ứng dụng. Queue name phải trỏ đúng queue đã tạo ở cùng Region. Credentials của worker lấy từ AWS SDK provider chain, ưu tiên IAM role của workload.

### 5.3. Listener nhận message bằng `@SqsListener`

Spring Cloud AWS SQS hỗ trợ annotation `@SqsListener`. Có thể nhận raw JSON string để chủ động phân tích S3 notification envelope:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class S3EventQueueListener {
    private final ObjectMapper objectMapper;
    private final S3ObjectEventHandler handler;

    public S3EventQueueListener(
            ObjectMapper objectMapper,
            S3ObjectEventHandler handler) {
        this.objectMapper = objectMapper;
        this.handler = handler;
    }

    @SqsListener("${app.sqs.file-events-queue}")
    public void receive(String message) throws Exception {
        JsonNode root = objectMapper.readTree(message);

        // S3 có thể gửi test event khi xác minh destination.
        if ("s3:TestEvent".equals(root.path("Event").asText())) {
            return;
        }

        JsonNode records = root.path("Records");
        if (!records.isArray()) {
            throw new IllegalArgumentException(
                    "S3 notification không có Records array");
        }

        for (JsonNode record : records) {
            handler.handle(record);
        }
    }
}
~~~

Queue name trong ví dụ được lấy từ `app.sqs.file-events-queue`. Trong ứng dụng thật, cấu hình listener container factory phù hợp với concurrency, acknowledgement và error handling của phiên bản Spring Cloud AWS đang dùng. Với nhiều event source, nên tách listener cho từng queue hoặc chuẩn hóa payload qua adapter riêng.

**Acknowledgement:** với acknowledgement mode `ON_SUCCESS` (hoặc cấu hình tương đương của phiên bản Spring Cloud AWS đang dùng), message chỉ được acknowledge sau khi listener xử lý thành công. Nếu listener ném exception, message không được xem là hoàn tất và có thể được nhận lại sau visibility timeout. Hãy xác minh ack mode/error handler của phiên bản thư viện; không tự xóa message trước khi business transaction hoàn tất.

### 5.4. Chuẩn hóa từng record

Một SQS message có thể chứa nhiều record. Handler nên:

1. Kiểm tra `eventSource` là `aws:s3`.
2. Chỉ xử lý eventName nằm trong allowlist, ví dụ bắt đầu bằng `ObjectCreated:`.
3. Đọc bucket name và encoded object key.
4. Decode key bằng UTF-8.
5. Lấy `versionId`, `sequencer` và metadata tùy chọn.
6. Xác minh bucket/prefix thuộc cấu hình được phép; không dùng bucket/key bất kỳ do payload gửi tới để truy cập tài nguyên ngoài phạm vi.

Payload có trường `eventVersion` theo dạng major/minor. Consumer nên kiểm tra **major version** có được hỗ trợ hay không; với minor version mới hơn, bỏ qua field chưa biết và tiếp tục nếu các field bắt buộc vẫn có. Tránh deserialize cứng toàn bộ JSON theo một schema đóng khiến một field mới không liên quan làm hỏng consumer.

Ví dụ đoạn decode key:

~~~java
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

String encodedKey = record.path("s3")
        .path("object")
        .path("key")
        .asText();

String objectKey = URLDecoder.decode(
        encodedKey, StandardCharsets.UTF_8);
~~~

`URLDecoder` chuyển dấu `+` thành khoảng trắng, phù hợp dạng encoding của S3 notification key. Đừng decode lặp nhiều lần; một key có thể chứa ký tự `%` đã được encode và decode lần thứ hai sẽ làm thay đổi tên object.

## 6. Consumer tải object và xử lý file

### 6.1. Worker service dùng `S3Client`

Consumer chỉ được phép tải object trong bucket/prefix đã cấu hình. Ví dụ dưới đây minh họa tải theo version ID nếu event có cung cấp:

~~~java
import java.io.InputStream;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

@Service
public class S3ObjectEventHandler {
    private final S3Client s3;
    private final FileProcessingService processor;

    public S3ObjectEventHandler(
            S3Client s3,
            FileProcessingService processor) {
        this.s3 = s3;
        this.processor = processor;
    }

    public void handle(JsonNode record) throws Exception {
        if (!"aws:s3".equals(record.path("eventSource").asText())) {
            throw new IllegalArgumentException("Event source không phải S3");
        }

        String eventName = record.path("eventName").asText();
        if (!eventName.startsWith("ObjectCreated:")) {
            return; // Queue này chỉ xử lý object được tạo.
        }

        JsonNode s3Record = record.path("s3");
        JsonNode object = s3Record.path("object");
        String bucket = s3Record.path("bucket").path("name").asText();
        String encodedKey = object.path("key").asText();
        String key = java.net.URLDecoder.decode(
                encodedKey, java.nio.charset.StandardCharsets.UTF_8);
        String versionId = object.hasNonNull("versionId")
                ? object.path("versionId").asText() : null;

        processObject(bucket, key, versionId);
    }

    public void processObject(
            String bucket, String key, String versionId) throws Exception {

        if (!"training-private-files".equals(bucket)
                || !key.startsWith("incoming/")) {
            throw new IllegalArgumentException(
                    "Bucket/prefix không nằm trong phạm vi xử lý");
        }

        GetObjectRequest.Builder request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key);

        if (versionId != null && !versionId.isBlank()) {
            request.versionId(versionId);
        }

        try (InputStream input = s3.getObject(request.build())) {
            processor.process(input, key);
        }
    }
}
~~~

`FileProcessingService` là service nghiệp vụ do ứng dụng tự định nghĩa. Mẫu này dùng stream để tránh đọc toàn bộ file vào RAM; nếu scanner/OCR cần seek hoặc đọc lại, có thể stream vào vùng tạm an toàn với quota và cleanup rõ ràng.

Phần `handle` minh họa cách nối parser với `processObject`. Trong production, gọi bước **idempotency claim** trước `processObject` và chỉ đánh dấu event hoàn tất sau khi side effect cùng trạng thái database đã được ghi nhận. Nếu một SQS message chứa nhiều record và record sau thất bại, message có thể được giao lại; các record đã xử lý phải được nhận diện là duplicate để không lặp side effect.

Worker IAM role cần quyền `s3:GetObject` trên prefix. Nếu tải phiên bản cụ thể, cần `s3:GetObjectVersion`. Nếu object được mã hóa SSE-KMS, role còn cần quyền KMS phù hợp như `kms:Decrypt` và key policy phải cho phép.

### 6.2. Vì sao version ID quan trọng?

Giả sử cùng key được upload hai lần trước khi worker xử lý:

~~~text
10:00 PUT incoming/report.pdf → version v1
10:01 S3 gửi event cho v1
10:02 PUT incoming/report.pdf → version v2
10:03 Worker nhận event v1 và gọi GET key mặc định
~~~

Nếu worker GET key **không có versionId**, nó có thể đọc nội dung v2 thay vì byte đã tạo event v1. Nếu bucket bật versioning và event có version ID, worker nên GET đúng version đó.

Nếu bucket chưa bật versioning, giải pháp đơn giản là **key bất biến cho mỗi lần upload**, ví dụ `incoming/{tenant}/{uuid}.pdf`. Không tái sử dụng key cho các lần upload khác nhau trong pipeline cần xử lý đúng từng sự kiện.

### 6.3. Không xử lý mọi loại event như một file mới

Consumer nên phân nhánh theo `eventName`:

- `ObjectCreated:*`: có thể khởi tạo quy trình xử lý file mới.
- `ObjectRemoved:*`: cập nhật trạng thái hoặc đồng bộ index; không gọi GET như file vừa tạo.
- `ObjectRestore:Completed`: object archive đã được restore; xử lý theo use case tương ứng.
- Event tagging/ACL: chỉ xử lý nếu ứng dụng thực sự dùng thay đổi đó.

Bỏ qua event ngoài allowlist một cách có chủ đích; không biến event không hỗ trợ thành lỗi retry vô hạn. Với schema major version không hỗ trợ, nên đưa vào DLQ/đường điều tra thay vì âm thầm xử lý sai.

## 7. Duplicate và out-of-order: thiết kế consumer idempotent

### 7.1. S3 event không phải exactly-once

S3 event notifications được thiết kế theo mô hình **at-least-once delivery**. Sự kiện có thể được gửi nhiều lần và không đảm bảo thứ tự đến. SQS standard cũng có thể giao message trùng và không đảm bảo thứ tự tuyệt đối.

Vì vậy worker phải giả định:

- Một event có thể được xử lý lại sau khi đã hoàn tất.
- Event tạo object cũ có thể đến sau event tạo object mới.
- Một message có thể chứa nhiều record.
- Worker có thể chết sau khi xử lý side effect nhưng trước khi message được acknowledge.
- Retry có thể khiến một công việc được chạy lại.

**Không xây consumer dựa trên giả định mỗi object chỉ tạo đúng một message hoặc message đến theo thứ tự upload.**

### 7.2. Idempotency key

Một cách tạo event identity cho S3 object notification là kết hợp:

~~~text
bucket + decodedKey + versionId + sequencer + eventName
~~~

Trong đó:

- `bucket + key` xác định object.
- `versionId` phân biệt phiên bản nếu versioning bật.
- `sequencer` giúp phân biệt thứ tự event cho **cùng một object key** khi event cung cấp trường này.
- `eventName` phân biệt loại hành động.

Lưu composite key hoặc hash của nó vào bảng xử lý với **unique constraint**. Không chỉ dựa vào SQS message ID: cùng một S3 event được gửi lại có thể tạo message ID khác nhau ở queue.

Ví dụ bảng nghiệp vụ:

~~~sql
CREATE TABLE processed_s3_events (
    event_key       VARCHAR(128) PRIMARY KEY,
    bucket_name     VARCHAR(255) NOT NULL,
    object_key      TEXT NOT NULL,
    version_id      VARCHAR(1024),
    sequencer       VARCHAR(128),
    event_name      VARCHAR(128) NOT NULL,
    status          VARCHAR(32) NOT NULL,
    processed_at    TIMESTAMP NULL
);
~~~

`event_key` là hash/định danh đã chuẩn hóa của event. Khi nhận event:

1. Thử insert event record với trạng thái `PROCESSING`.
2. Nếu unique constraint báo đã tồn tại và trạng thái `COMPLETED`, bỏ qua duplicate.
3. Nếu đang `PROCESSING` bởi worker khác, dùng lease/lock hoặc chờ theo chính sách.
4. Nếu lần trước `FAILED` hoặc lease hết hạn, quyết định retry/reclaim.
5. Chỉ đánh dấu `COMPLETED` sau khi xử lý và cập nhật trạng thái nghiệp vụ thành công.

**Không đánh dấu COMPLETED trước khi làm side effect.** Nếu process chết sau khi ghi COMPLETED nhưng trước khi tạo thumbnail, message retry sẽ bị bỏ qua và công việc không hoàn tất. Ngược lại, nếu side effect hoàn tất nhưng DB chưa ghi COMPLETED, lần retry phải có khả năng tạo cùng kết quả mà không nhân đôi.

### 7.3. Sequencer chỉ so sánh trong cùng object key

S3 event có thể cung cấp `sequencer` để so sánh thứ tự sự kiện liên quan đến **cùng một object key**. Không dùng sequencer để sắp thứ tự giữa hai key khác nhau.

Khi so sánh hai giá trị hexadecimal có độ dài khác nhau, cần pad giá trị ngắn hơn ở bên trái bằng số `0`, rồi so sánh theo thứ tự từ điển. Không coi sequencer là timestamp hoặc version ID.

Trong nhiều pipeline, lựa chọn an toàn hơn là **key bất biến + xử lý từng upload độc lập**; khi đó không cần suy luận một event cũ có nên ghi đè trạng thái object mới hay không. Nếu nghiệp vụ xử lý current object theo key có thể bị cập nhật liên tục, phải lưu trạng thái mới nhất và chỉ áp dụng kết quả từ event không cũ hơn trạng thái đã chấp nhận.

### 7.4. Side effect phải có thể retry

Ví dụ worker tạo thumbnail:

~~~text
incoming/tenant-42/file-123.pdf
        ↓
processed/tenant-42/file-123.pdf
thumbnails/tenant-42/file-123/page-1.png
~~~

Dùng output key **xác định theo input version/event**, hoặc lưu trạng thái kết quả trong DB. Nếu worker chạy lại, nó có thể kiểm tra output đã tồn tại/đã hoàn thành để tránh tạo nhiều kết quả trùng. Nếu side effect là gọi API bên ngoài hoặc gửi email, dùng idempotency key của hệ thống đích hoặc transactional outbox phù hợp.

Không thể tạo transaction duy nhất bao trùm SQS acknowledgement, S3 PUT và database commit. Hãy thiết kế từng bước có trạng thái, retry và đối soát.

## 8. SQS visibility timeout, retry và dead-letter queue

### 8.1. Visibility timeout

Khi SQS giao message cho consumer, message tạm thời **ẩn khỏi consumer khác** trong thời gian visibility timeout. Nếu worker hoàn tất và acknowledge/delete, message được loại khỏi queue. Nếu worker chết hoặc không acknowledge trước khi timeout, message có thể xuất hiện lại.

Chọn visibility timeout dài hơn thời gian xử lý thông thường, có khoảng đệm cho network/retry. Với công việc kéo dài, consumer có thể gia hạn visibility timeout trong lúc xử lý bằng cơ chế phù hợp; không để message hiện lại khi worker cũ vẫn đang tạo side effect.

### 8.2. Redrive và DLQ

Ví dụ cấu hình ý tưởng:

~~~text
Main queue: file-processing-queue
  visibility timeout: phù hợp thời gian xử lý
  maxReceiveCount: 5
  redrive target: file-processing-dlq

DLQ: file-processing-dlq
  giữ message lỗi để điều tra
  không tự động xử lý lại vô hạn
~~~

`maxReceiveCount` là ngưỡng ví dụ, cần điều chỉnh theo retry/backoff và SLA. Khi message đến DLQ, điều tra:

- Payload có đúng schema và event type được hỗ trợ không?
- Bucket/key có tồn tại và role có quyền GET không?
- File có lỗi định dạng, quá lớn hoặc bị scanner từ chối không?
- KMS key có quyền decrypt không?
- Worker lỗi do bug hay phụ thuộc bên ngoài đang unavailable?

Sau khi sửa nguyên nhân, có thể redrive message về queue chính theo quy trình được kiểm soát. Không redrive hàng loạt khi chưa hiểu lỗi, vì có thể tạo backlog hoặc lặp side effect.

### 8.3. Long polling và concurrency

SQS long polling giảm số request rỗng và độ trễ chờ message. Cấu hình consumer concurrency phải phù hợp với:

- Số worker instance và số listener thread.
- CPU/RAM cho antivirus/OCR/conversion.
- Connection pool và throughput S3.
- Quota KMS nếu object dùng SSE-KMS.
- Khả năng chịu tải của database và dịch vụ phụ thuộc.

Tăng concurrency không luôn làm pipeline nhanh hơn; có thể làm scanner, KMS hoặc database quá tải. Theo dõi queue age và thời gian xử lý để điều chỉnh.

## 9. IAM và quyền cho từng thành phần

Một pipeline có ít nhất ba nhóm quyền độc lập:

| Thành phần | Quyền cần thiết thường gặp | Không nên cấp mặc định |
| --- | --- | --- |
| S3 bucket gửi event đến SQS | Queue resource policy cho service principal `s3.amazonaws.com` gửi `sqs:SendMessage` | Quyền đọc/xóa object |
| Spring Boot worker đọc queue | `sqs:GetQueueUrl`, `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`; có thể cần `sqs:ChangeMessageVisibility` | `sqs:*` trên mọi queue |
| Worker tải file từ S3 | `s3:GetObject` trên prefix đầu vào; `s3:GetObjectVersion` nếu GET theo version | `s3:PutObject`/`s3:DeleteObject` nếu worker không ghi/xóa |
| Worker ghi kết quả | `s3:PutObject` trên prefix output cần thiết | Quyền ghi toàn bucket |
| Worker đọc SSE-KMS object | `kms:Decrypt` và key policy/grant phù hợp | `kms:*` trên mọi key |

S3 service principal được cấp quyền gửi message thông qua **SQS queue policy**. Worker dùng IAM role của workload để nhận/xóa message và truy cập object. Hai danh tính này khác nhau.

Nếu queue bật SSE-KMS, worker cần quyền giải mã queue theo cấu hình; dịch vụ gửi message cũng cần được phép dùng KMS key theo yêu cầu của SQS encryption. Hãy xem policy của queue/key thay vì chỉ kiểm IAM role Spring Boot.

### 9.1. Tách quyền xử lý và quyền quản trị

API upload không cần `s3:PutBucketNotification` hoặc `sqs:SetQueueAttributes` trong runtime. Cấu hình notification, queue policy, redrive policy và lifecycle nên được quản lý bằng IaC hoặc role triển khai riêng. Worker chỉ nhận quyền cần để đọc queue, tải object và ghi output của nó.

## 10. Tránh event loop và xử lý trạng thái nghiệp vụ

### 10.1. Tách prefix input và output

Một lỗi phổ biến là cấu hình:

~~~text
Notification: ObjectCreated:* cho toàn bucket
Worker nhận event → tạo thumbnail vào cùng bucket
Thumbnail tạo ObjectCreated event mới
Worker xử lý thumbnail → tạo thumbnail khác
...
~~~

Để tránh vòng lặp:

- Chỉ subscribe prefix `incoming/`.
- Worker ghi output vào `processed/` hoặc `thumbnails/`.
- Nếu cần nhiều pipeline, dùng prefix/suffix riêng hoặc queue/topic riêng.
- Không dựa vào metadata tự gắn để chống loop nếu filter/policy chưa đảm bảo consumer xử lý đúng.

### 10.2. Quản lý trạng thái file

Một state machine đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_UPLOAD
    PENDING_UPLOAD --> UPLOADED: PUT thành công
    UPLOADED --> PROCESSING: Worker claim event
    PROCESSING --> READY: Scan/OCR thành công
    PROCESSING --> FAILED: Lỗi nghiệp vụ không retry được
    PROCESSING --> RETRY_WAIT: Lỗi tạm thời
    RETRY_WAIT --> PROCESSING: Message được nhận lại
    PENDING_UPLOAD --> EXPIRED: Không hoàn tất trong hạn
    FAILED --> PROCESSING: Redrive có kiểm soát
~~~

Trạng thái trong database là nguồn sự thật cho UI và nghiệp vụ. SQS chỉ giữ công việc cần xử lý; message đã bị xóa khỏi queue không có nghĩa file luôn `READY`. Ngược lại, object tồn tại trên S3 cũng không có nghĩa đã quét và được chấp nhận.

### 10.3. Xử lý file không hợp lệ

Không nên để consumer retry vô hạn với file có định dạng không hỗ trợ hoặc vi phạm chính sách:

1. Đưa object vào trạng thái `REJECTED` hoặc `QUARANTINED`.
2. Ghi lý do đã chuẩn hóa, không log nội dung nhạy cảm.
3. Nếu cần di chuyển/copy object, thực hiện theo quyền và chính sách riêng; không tự động xóa bản gốc nếu còn yêu cầu audit.
4. Acknowledge message sau khi trạng thái từ chối được lưu bền vững.
5. Thông báo kết quả cho API/UI qua database hoặc event nghiệp vụ riêng.

Lỗi tạm thời như timeout S3, database unavailable hoặc scanner đang gián đoạn có thể retry. Lỗi dữ liệu vĩnh viễn cần đi qua nhánh xử lý nghiệp vụ thay vì retry đến DLQ mà không có thông tin hữu ích.

## 11. Giám sát và vận hành pipeline

Một pipeline event-driven cần quan sát được từ lúc upload đến khi hoàn tất:

| Chỉ số | Ý nghĩa | Khi cần điều tra |
| --- | --- | --- |
| SQS ApproximateNumberOfMessagesVisible | Số message đang chờ | Backlog tăng liên tục |
| ApproximateNumberOfMessagesNotVisible | Message đang được consumer xử lý | Tăng cao kéo dài hoặc gần visibility timeout |
| ApproximateAgeOfOldestMessage | Tuổi message cũ nhất | Công việc chờ lâu, SLA bị ảnh hưởng |
| DLQ visible messages | Số message thất bại đến DLQ | Tăng đột ngột hoặc có cùng error |
| Processing duration | Thời gian worker xử lý một file | Tăng sau thay đổi scanner/OCR |
| Success/failure/retry count | Tỷ lệ kết quả và retry | Lỗi credentials, file hỏng hoặc dependency |
| S3/KMS error rate | Lỗi truy cập object/khóa | AccessDenied, throttling hoặc key policy |
| Pending file age | Tuổi bản ghi chưa READY | Event bị mất, queue backlog hoặc worker lỗi |

Log/trace nên có `documentId`, bucket/prefix đã chuẩn hóa, eventName, version ID/sequencer nếu có, SQS message ID, attempt và correlation ID. Không log presigned URL, access key, secret, session token hoặc byte nội dung.

S3 event notification là cơ chế giao sự kiện, nhưng hệ thống vẫn nên có **reconciliation job** định kỳ: tìm bản ghi `UPLOADED/PENDING` quá lâu, kiểm tra object và trạng thái xử lý, rồi phát lại công việc có idempotency. Cách này giúp phát hiện sự kiện bị cấu hình sai hoặc pipeline bị gián đoạn.

## 12. Kiểm thử S3 → SQS → Spring Boot

### 12.1. Các tầng kiểm thử

| Tầng | Nội dung kiểm tra | Giới hạn |
| --- | --- | --- |
| Unit test | Parse event, decode key, lọc eventName, idempotency và state transition | Không kiểm tra S3/SQS delivery thực |
| LocalStack hoặc emulator phù hợp | Bucket notification, queue, listener và luồng upload cơ bản nếu được hỗ trợ | Hành vi event schema, retry, IAM/KMS có thể khác AWS |
| AWS sandbox | Queue policy, S3 notification, delivery, IAM, visibility timeout, DLQ và KMS | Cần bucket/queue riêng, theo dõi chi phí và cleanup |

### 12.2. Kịch bản integration test

1. Tạo bucket sandbox, SQS standard queue và DLQ cùng Region.
2. Cấu hình queue policy cho phép đúng bucket gửi `sqs:SendMessage`.
3. Đăng ký S3 notification cho prefix `incoming/` và suffix `.pdf`.
4. Upload một PDF test; xác nhận message xuất hiện trong queue.
5. Chạy worker và kiểm tra database chuyển từ `UPLOADED` sang `PROCESSING` rồi `READY`.
6. Upload một file dưới prefix khác; xác minh không tạo công việc cho queue này.
7. Gửi lại cùng event hoặc mô phỏng duplicate; xác minh side effect không lặp.
8. Gửi event cho version cũ sau version mới; xác minh worker đọc đúng version ID hoặc dùng key bất biến.
9. Làm worker ném exception tạm thời; kiểm tra message xuất hiện lại sau visibility timeout.
10. Tạo lỗi lặp vượt maxReceiveCount; xác minh message vào DLQ.
11. Thử test event `s3:TestEvent` không có `Records`; listener không xử lý nhầm thành object event.
12. Kiểm tra worker không nhận event output do prefix filter ngăn vòng lặp.

### 12.3. Kiểm thử parser với payload giả lập

~~~java
String json = """
{
  "Records": [{
    "eventSource": "aws:s3",
    "eventName": "ObjectCreated:Put",
    "s3": {
      "bucket": {"name": "training-private-files"},
      "object": {
        "key": "incoming%2Ftenant-42%2Fmy+file.pdf",
        "versionId": "version-123",
        "sequencer": "0067A123"
      }
    }
  }]
}
""";

JsonNode root = objectMapper.readTree(json);
JsonNode record = root.path("Records").get(0);

String encoded = record.path("s3")
        .path("object").path("key").asText();

String decoded = java.net.URLDecoder.decode(
        encoded, java.nio.charset.StandardCharsets.UTF_8);

// decoded = "incoming/tenant-42/my file.pdf"
~~~

Test nên xác nhận dấu `+` được decode thành khoảng trắng và không decode lặp. Ngoài ra cần test key có ký tự Unicode, ký tự phần trăm đã encode và record thiếu optional field.

## 13. Liên hệ Azure và Google Cloud

Các provider khác cũng hỗ trợ event-driven file processing nhưng cách phát sự kiện và queue có thể khác:

| Khái niệm | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Object storage | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| Event source | S3 Event Notifications / EventBridge | Event Grid cho Blob Storage | Cloud Storage notifications / Eventarc tùy use case |
| Queue/messaging | Amazon SQS, SNS | Azure Service Bus, Storage Queue, Event Grid | Pub/Sub |
| Consumer Spring | Spring Cloud AWS SQS | Spring Cloud Azure messaging | Spring Cloud GCP Pub/Sub |
| Retry/dead-letter | SQS visibility/redrive/DLQ | Service Bus delivery count/DLQ hoặc queue policy tương ứng | Pub/Sub retry/dead-letter policy |
| Định danh | IAM role + queue/bucket policy | Managed Identity + Azure RBAC | Service account + Google IAM |

Không giả định event payload, ordering, retry, retention hoặc dead-letter semantics giống nhau. Một domain event nội bộ có thể chuẩn hóa:

~~~java
public record ObjectCreatedEvent(
        String provider,
        String bucketOrContainer,
        String objectKey,
        String versionOrGeneration,
        String eventType,
        String eventIdentity) {}
~~~

Adapter AWS chuyển S3 notification/EventBridge sang domain event; adapter Azure chuyển Event Grid; adapter GCP chuyển Cloud Storage/Pub/Sub event. Logic xử lý tài liệu dùng chung, còn provider-specific details (version ID/generation, identity, retry, queue ack và event schema) được giữ ở adapter.

## 14. Bài tập thực hành

### Bài A — S3 gửi event vào SQS

Tạo bucket sandbox, SQS standard queue và queue policy. Cấu hình event `s3:ObjectCreated:*` với prefix `incoming/`. Upload một file test và xác minh queue nhận được notification. Giải thích vì sao S3 cần `sqs:SendMessage` ở queue policy.

### Bài B — Spring Boot worker

Thêm `spring-cloud-aws-starter-sqs`, viết `@SqsListener` nhận JSON message, parse từng record và tải object bằng `S3Client`. Cập nhật trạng thái file trong database. Xác minh worker không đọc key ngoài bucket/prefix được phép.

### Bài C — Duplicate và retry

Gửi cùng một event hai lần. Dùng unique constraint/idempotency key để chứng minh chỉ tạo một kết quả nghiệp vụ. Sau đó làm worker lỗi một lần rồi thành công ở lần nhận lại; quan sát visibility timeout và acknowledgement.

### Bài D — Versioning và out-of-order

Bật versioning trong bucket test, upload hai nội dung vào cùng key và mô phỏng event đến sai thứ tự. Worker phải GET theo version ID hoặc dùng key bất biến. Trình bày giới hạn so sánh sequencer chỉ trong cùng object key.

### Bài E — DLQ và event loop

Cố tình tạo lỗi xử lý lặp để message vào DLQ. Điều tra payload và sửa lỗi trước khi redrive. Tạo output dưới prefix khác với input, xác minh worker không tự kích hoạt chính nó.

### Bài F — So sánh đa cloud

Thiết kế cùng pipeline xử lý tài liệu trên AWS (S3 + SQS), Azure (Blob + Event Grid/Service Bus) và GCP (Cloud Storage + Pub/Sub/Eventarc). Lập bảng mapping event, queue, identity, retry, DLQ và version reference.

### Câu hỏi tự kiểm tra

1. S3 event notification chứa byte file hay thông tin tham chiếu đến object?
2. Khi nào dùng `ObjectCreated:Put` và khi nào cần `ObjectCreated:CompleteMultipartUpload`?
3. Prefix/suffix filter giúp gì và vì sao output không nên nằm trong cùng prefix input?
4. Vì sao S3 cần queue policy cho phép `sqs:SendMessage`?
5. S3 event notification trực tiếp có gửi vào SQS FIFO queue không?
6. S3 event notification và EventBridge event có cùng JSON envelope không?
7. Vì sao S3 event và SQS standard có thể tạo duplicate hoặc out-of-order?
8. Tại sao không nên dùng riêng SQS message ID làm idempotency key cho S3 event?
9. Khi bucket bật versioning, vì sao worker nên GET theo version ID?
10. Sequencer dùng để so sánh sự kiện trong phạm vi nào?
11. Visibility timeout và DLQ giải quyết hai vấn đề gì?
12. Vì sao chỉ đánh dấu event COMPLETED sau khi side effect và database state được lưu đúng?
13. Khi nào nên dùng SNS fan-out thay vì một SQS queue?
14. Vì sao cần reconciliation job cho bản ghi UPLOADED bị treo?
15. Những phần nào của pipeline có thể dùng chung giữa AWS, Azure và GCP, phần nào phải theo provider?

**Kết quả mong đợi:** người học cấu hình được S3 event notification gửi đến SQS, xây Spring Boot worker nhận và xử lý file theo sự kiện, chịu được duplicate/out-of-order/retry, quản lý visibility timeout và DLQ, đồng thời hiểu cách ánh xạ event-driven file processing sang Azure và Google Cloud.

