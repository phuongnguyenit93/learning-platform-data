# Amazon S3: Truyền dữ liệu dạng luồng và tải lên nhiều phần

## Mục tiêu học tập

Trong module `SPRING_CLOUD_PROVIDER_INTEGRATION`, Spring Boot được tích hợp với dịch vụ managed của AWS, Azure và Google Cloud để truy cập storage, messaging, dữ liệu và các tài nguyên cần xác thực. Với **Amazon S3**, một yêu cầu truyền tệp có thể chỉ vài kilobyte hoặc hàng gigabyte. Nếu ứng dụng đọc toàn bộ tệp vào `byte[]` trước khi xử lý, bộ nhớ có thể tăng nhanh khi nhiều người dùng tải tệp đồng thời. Hai kỹ thuật cần phân biệt là:

- **Streaming (truyền dạng luồng):** xử lý tuần tự từng phần dữ liệu từ `InputStream`, `OutputStream` hoặc API bất đồng bộ thay vì giữ toàn bộ object trong bộ nhớ.
- **Multipart upload (tải lên nhiều phần):** giao thức S3 cho phép chia **một object** thành nhiều part, upload riêng từng part và yêu cầu S3 hợp nhất thành object hoàn chỉnh.

Sau bài này, bạn sẽ biết cách upload/download bằng stream trong Spring Boot, tự điều phối multipart upload với AWS SDK for Java v2, dùng giải pháp truyền file cấp cao khi phù hợp, thiết kế retry/cleanup và kiểm thử sự cố mạng. Các ví dụ sử dụng `software.amazon.awssdk` (AWS SDK v2) và Spring Cloud AWS namespace `io.awspring.cloud`; chọn phiên bản thư viện tương thích với Spring Boot của dự án.

> **Trọng tâm:** Streaming mô tả cách ứng dụng **đọc và ghi dữ liệu**; multipart mô tả cách **S3 nhận một object lớn qua nhiều request**. Một upload có thể dùng streaming nhưng vẫn là một PUT duy nhất. Ngược lại, multipart có thể tải từng part từ các mảng byte nhỏ với bộ nhớ giới hạn.

## 1. Vấn đề bộ nhớ khi xử lý tệp lớn

Giả sử ứng dụng cho phép 50 người dùng đồng thời upload tệp 200 MiB. Nếu mỗi request gọi `file.getBytes()` và giữ nội dung trong RAM, lượng byte ứng dụng có thể đồng thời giữ lên đến khoảng **10.000 MiB**, chưa kể heap của framework, bộ đệm HTTP, xử lý file và GC. Đây là ví dụ về rủi ro dung lượng, không phải phép dự đoán chính xác việc phân bổ heap ở mọi môi trường.

~~~java
// Với file lớn, cách này có thể gây áp lực bộ nhớ đáng kể.
byte[] allBytes = file.getBytes();
s3.putObject(putRequest, RequestBody.fromBytes(allBytes));
~~~

Đối với streaming, mỗi request chỉ giữ một vùng đệm có kích thước cố định:

~~~text
Client ──stream──▶ Spring Boot ──stream──▶ Amazon S3
                   64 KiB buffer
                       │
                 không giữ toàn bộ file
~~~

Nếu sử dụng multipart, backend cũng có thể nạp một part, gửi lên S3, bỏ vùng đệm rồi lặp lại. Với part 8 MiB, lượng dữ liệu cư trú phụ thuộc **số part được giữ đồng thời**, thay vì bằng kích thước toàn bộ object. Dẫu vậy, 100 request đồng thời nhân với bộ đệm 8 MiB cũng có thể tiêu thụ khoảng 800 MiB chưa kể overhead; cần giới hạn số tác vụ đồng thời.

### 1.1. Những kiểu dữ liệu thường gặp trong Java

| API | Vai trò | Lưu ý |
| --- | --- | --- |
| `InputStream` | Đọc tuần tự từ nguồn, ví dụ file hoặc HTTP upload | Đóng stream sau khi đọc; không giả định có thể tua lại |
| `OutputStream` | Ghi tuần tự ra đích, ví dụ HTTP response hoặc file | Có thể gặp lỗi giữa chừng; không giữ trọn file |
| `RequestBody.fromBytes(byte[])` | Gửi một mảng byte qua AWS SDK sync | Dễ dùng với file nhỏ, phải giữ payload trong RAM |
| `RequestBody.fromInputStream(stream, length)` | SDK đồng bộ gửi từ stream có độ dài đã biết | **Cần chính xác số byte** và stream còn mở trong suốt lời gọi |
| `RequestBody.fromFile(path)` | Đọc nội dung từ file local | Hữu ích khi file đã có trên ổ đĩa |
| `S3Client.getObject(request)` | Trả `ResponseInputStream<GetObjectResponse>` | Đóng stream để giải phóng kết nối |
| `AsyncRequestBody` / `S3AsyncClient` | Truyền dữ liệu bất đồng bộ | Cần kiểm soát callback, backpressure, timeout và lifecycle |
| `S3TransferManager` | Truyền file qua API cấp cao của AWS SDK v2 | Phù hợp khi muốn SDK quản lý upload/download, multipart và concurrency |

**Cần phân biệt buffering trong các tầng:** dùng `MultipartFile.getInputStream()` ở Spring MVC không chứng minh request HTTP được stream xuyên suốt từ browser đến S3 mà không có trung gian. Servlet container có thể đã đệm multipart body trong RAM hoặc tệp tạm. Streaming ở phần S3 giúp tránh tạo thêm bản sao toàn bộ tệp trong application code, nhưng cần kiểm tra cấu hình nhận file ở web server.

### 1.2. Đơn vị và giới hạn thực hành

- **MiB** là mebibyte: 1 MiB = 1.048.576 byte. Kích thước truyền/giới hạn S3 phải tính bằng **byte**, không đếm ký tự của nội dung.
- Với multipart S3 thông thường, mỗi part phải **ít nhất 5 MiB**, trừ part cuối; một part có thể tối đa **5 GiB**; tối đa **10.000 part** cho một upload. Các hạn mức cấp object và tính năng cụ thể nên đối chiếu tài liệu AWS của môi trường đang dùng.
- `partSize` quyết định **số part**, số request, chi phí, vùng đệm và khả năng retry. Ví dụ part 8 MiB chỉ là giá trị học tập; tệp cực lớn cần part lớn hơn để không vượt giới hạn 10.000 part.
- S3 hỗ trợ truyền dữ liệu bền vững và PUT/GET/LIST nhất quán mạnh sau khi thao tác thành công; điều đó không thay thế việc xử lý timeout, request trùng và trạng thái chưa xác định của upload.

## 2. Chuẩn bị Spring Cloud AWS và quyền IAM

### 2.1. Dependency và cấu hình

Trong dự án Maven, dùng BOM Spring Cloud AWS **tương thích với phiên bản Spring Boot**, rồi khai báo S3 starter:

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
</dependencies>
~~~

`spring-cloud-aws.version` là property phải khai báo bằng phiên bản phát hành thực tế phù hợp; đây không phải một phiên bản cố định dành cho mọi Spring Boot.

~~~yaml
# application.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
  servlet:
    multipart:
      max-file-size: 200MB
      max-request-size: 200MB

app:
  storage:
    bucket: ${S3_BUCKET_NAME}
    prefix: documents/
~~~

`app.storage.*` là property riêng của ứng dụng. Các giới hạn `spring.servlet.multipart.*` là **ví dụ cho endpoint Spring MVC nhận multipart/form-data**, phải chọn theo nhu cầu và giới hạn hạ tầng; chúng không quyết định kích thước tối đa của API S3. Với một tệp lớn vượt hạn mức nhận request của web server, cân nhắc **direct upload** từ client đến S3 qua presigned URL hoặc giao thức multipart.

Khi triển khai trên AWS, ưu tiên IAM role gắn với workload. Ở local có thể sử dụng AWS profile hoặc credentials tạm thời qua default credentials provider chain. Không đưa access key/secret key vào source code, file cấu hình commit lên Git hoặc đoạn log.

### 2.2. Quyền cho PUT, GET và multipart

| Lời gọi | Quyền S3 thường cần | Phạm vi |
| --- | --- | --- |
| `PutObject`, `CreateMultipartUpload`, `UploadPart`, `CompleteMultipartUpload` | `s3:PutObject` | Object ARN |
| `GetObject` | `s3:GetObject` | Object ARN |
| `AbortMultipartUpload` | `s3:AbortMultipartUpload` | Object ARN |
| `ListParts` | `s3:ListMultipartUploadParts` | Object ARN |
| `ListMultipartUploads` | `s3:ListBucketMultipartUploads` | Bucket ARN |
| Liệt kê object thông thường | `s3:ListBucket` | Bucket ARN |

Chính sách tối thiểu cho một service cần upload, đọc và hủy multipart dưới prefix `documents/`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:AbortMultipartUpload"
      ],
      "Resource": "arn:aws:s3:::training-private-docs/documents/*"
    }
  ]
}
~~~

Đổi tên bucket mẫu thành bucket thật trước khi sử dụng. Nếu service còn gọi `ListParts` hoặc liệt kê các upload chưa hoàn tất, cấp các action tương ứng với đúng loại ARN. Nếu dùng SSE-KMS, cần xem xét quyền KMS như `kms:GenerateDataKey` và `kms:Decrypt` tùy thao tác, cùng key policy thực tế. Bucket policy, AWS Organizations SCP hoặc explicit deny có thể thu hẹp thêm quyền hiệu lực.

Bucket nên ở chế độ private với Block Public Access phù hợp. IAM role của Spring Boot có thể gửi dữ liệu đến S3, nhưng người dùng cuối vẫn phải được **xác thực và kiểm tra quyền nghiệp vụ** trước khi backend đọc, ghi hoặc cấp URL tới object của họ.

## 3. Streaming download bằng `S3Client`

Một lời gọi `GetObject` có thể trả stream từ S3. Đối với tệp lớn, tránh `getObjectAsBytes` hoặc `readAllBytes` nếu không cần toàn bộ file trong RAM.

### 3.1. Service đọc bằng stream

~~~java
import java.io.IOException;
import java.io.OutputStream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

@Service
public class S3DownloadService {
    private final S3Client s3Client;
    private final String bucket;

    public S3DownloadService(
            S3Client s3Client,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3Client = s3Client;
        this.bucket = bucket;
    }

    public void copyTo(String trustedKey, OutputStream destination)
            throws IOException {
        if (trustedKey == null
                || !trustedKey.startsWith("documents/")) {
            throw new IllegalArgumentException("Key không hợp lệ");
        }

        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build();

        try (ResponseInputStream<GetObjectResponse> source =
                     s3Client.getObject(request)) {
            source.transferTo(destination);
        }
    }
}
~~~

Ở đây:

1. `S3Client` được Spring Cloud AWS starter cấu hình và inject vào service, dùng lại giữa các request.
2. Mỗi `getObject` mở một stream đọc từ S3; **try-with-resources** bảo đảm đóng stream khi copy xong hoặc khi gặp lỗi.
3. `transferTo` chuyển byte từ stream nguồn sang đích mà không yêu cầu tạo một `byte[]` chứa toàn bộ nội dung.
4. `destination` do bên gọi sở hữu; service **không tự đóng** output stream HTTP hay stream do caller cung cấp.
5. `trustedKey` phải được lấy từ bản ghi đã **kiểm tra quyền user/tenant** trước đó. Kiểm tra prefix chỉ xác nhận hình dạng key, không cấp quyền truy cập dữ liệu.

Nếu cần chỉ tải một đoạn, S3 hỗ trợ byte range:

~~~java
var request = GetObjectRequest.builder()
        .bucket(bucket)
        .key("documents/large-video.bin")
        .range("bytes=0-1048575") // 1 MiB đầu, nếu object đủ lớn.
        .build();

try (var firstMegabyte = s3Client.getObject(request)) {
    firstMegabyte.transferTo(destination);
}
~~~

Range GET phù hợp phát media, hỗ trợ resume hoặc đọc header của định dạng file. Nó **không phải** một part của multipart upload; hai tính năng khác nhau về API và mục đích.

### 3.2. Stream HTTP response trong Spring MVC

Với `StreamingResponseBody` của Spring MVC, có thể chuyển dữ liệu từ S3 sang trình duyệt theo stream:

~~~java
// Đoạn minh họa luồng controller, trong đó documentService là
// service nghiệp vụ do ứng dụng tự định nghĩa.
@GetMapping("/documents/{id}/content")
public ResponseEntity<StreamingResponseBody> download(
        @PathVariable UUID id,
        Authentication authentication) {

    DocumentRecord record = documentService
            .requireReadableDocument(id, authentication);

    StreamingResponseBody body = output ->
            s3DownloadService.copyTo(record.objectKey(), output);

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .body(body);
}
~~~

Các kiểu `DocumentRecord`, `documentService` trong đoạn controller là **minh họa tích hợp với lớp nghiệp vụ của dự án**, chưa phải class hoàn chỉnh để copy và compile độc lập. Điểm cốt lõi là **kiểm tra quyền trước khi tạo phản hồi** và gọi `copyTo` khi MVC bắt đầu truyền stream.

`StreamingResponseBody` chạy trong cơ chế xử lý async của Spring MVC nhưng cách đọc `S3Client` đồng bộ vẫn có thể giữ một worker thread trong suốt thời gian chuyển dữ liệu. Cần cấu hình executor, timeout và số kết nối phù hợp; không mặc định đây là reactive hoặc non-blocking I/O.

Ngoài ra, nếu đã gửi response headers rồi stream gặp lỗi, API có thể không còn đổi sang JSON lỗi chuẩn. Hệ thống nên log request ID, xử lý client disconnect và đóng nguồn S3; với file lớn cần cân nhắc presigned GET URL để client tải trực tiếp từ S3.

### 3.3. `S3Template` và Spring `Resource` có stream được không?

Spring Cloud AWS còn cung cấp các abstraction đọc object:

~~~java
// S3Template được inject qua starter S3.
Resource object = s3Template.download(
        "training-private-docs", "documents/report.pdf");

try (InputStream input = object.getInputStream()) {
    input.transferTo(destination);
}
~~~

Hoặc dùng `ResourceLoader` nếu ứng dụng đã tích hợp S3 resource scheme:

~~~java
Resource resource = resourceLoader.getResource(
        "s3://training-private-docs/documents/report.pdf");

try (InputStream input = resource.getInputStream()) {
    input.transferTo(destination);
}
~~~

`S3Template`/`Resource` hữu ích khi phần còn lại của ứng dụng đã làm việc với `Resource`. Nhưng **không coi `Resource.getFile()` là file local**: object S3 là tài nguyên từ xa, và các lời gọi `exists()`, `contentLength()` hoặc `getInputStream()` có thể phát sinh request mạng. Với yêu cầu Range, conditional request, checksum hoặc xử lý response metadata chi tiết, dùng trực tiếp `S3Client` thường rõ ràng hơn.

## 4. Streaming upload một PUT khi biết độ dài

Multipart upload của S3 **không bắt buộc** cho mọi file. Với file nhỏ hoặc vừa, một PUT duy nhất qua `InputStream` có thể đơn giản và đủ dùng.

### 4.1. Upload từ `InputStream` có `contentLength` chính xác

~~~java
import java.io.InputStream;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class S3SinglePutService {
    private final S3Client s3Client;
    private final String bucket;

    public S3SinglePutService(
            S3Client s3Client,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3Client = s3Client;
        this.bucket = bucket;
    }

    public String uploadKnownLength(
            InputStream input,
            long contentLength,
            String contentType) {

        if (contentLength < 0) {
            throw new IllegalArgumentException(
                    "Phải biết chính xác kích thước byte");
        }

        String key = "documents/" + UUID.randomUUID();

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(contentType)
                .build();

        s3Client.putObject(
                request,
                RequestBody.fromInputStream(input, contentLength));

        return key;
    }
}
~~~

**Các điều kiện quan trọng:**

- `contentLength` là **số byte**, không phải số ký tự hoặc dung lượng ước tính. Nếu số byte được khai báo không khớp stream thực, request có thể thất bại, treo đợi byte hoặc tạo nội dung không đúng kỳ vọng.
- Caller phải giữ stream còn mở đến khi `putObject` trả về và chịu trách nhiệm đóng stream nguồn. `putObject` là lời gọi đồng bộ, sẽ giữ thread trong thời gian gửi dữ liệu.
- `contentType` cần được kiểm tra/chuẩn hóa từ định dạng file thực; không nên đặt tùy ý dựa trên header do client tự khai.
- Không dùng `RequestBody.fromContentProvider` không có length với giả định nó luôn giữ bộ nhớ thấp: SDK đồng bộ có thể cần buffer để xác định chiều dài. Với nguồn không biết kích thước, dùng tệp tạm được kiểm soát hoặc **multipart upload theo part**.
- Ghi lại key chỉ sau khi PUT thành công; nếu cần phối hợp với database, có thể cần cơ chế retry/idempotency và dọn object khi transaction khác thất bại.

### 4.2. Dùng `MultipartFile` trong controller

Spring MVC có thể cung cấp `MultipartFile.getInputStream()` và `MultipartFile.getSize()`:

~~~java
try (InputStream input = multipartFile.getInputStream()) {
    String objectKey = s3SinglePutService.uploadKnownLength(
            input,
            multipartFile.getSize(),
            validatedContentType);
    // Ghi objectKey vào database cùng owner/tenant.
}
~~~

Cấu hình `max-file-size`/`max-request-size` của Servlet container phải phù hợp. Một `MultipartFile` có thể đã được lưu tạm trước khi controller chạy; việc gọi `getInputStream` **không bảo đảm end-to-end streaming từ trình duyệt**.

Với file rất lớn hoặc nhiều client đồng thời, chuyển dữ liệu qua backend sẽ chiếm băng thông, số connection và thread. Khi không cần quét/chuyển đổi nội dung trên server, có thể chọn **direct-to-S3** qua presigned URL do backend cấp sau xác thực.

### 4.3. Một PUT so với multipart

| Tiêu chí | Một PUT | Multipart upload |
| --- | --- | --- |
| Số request upload | Một request PUT | Initiate + nhiều UploadPart + Complete |
| Truyền từng byte qua Java stream | Có thể | Có thể |
| Retry khi bị lỗi mạng giữa upload | Thường gửi lại request PUT | Có thể retry **part thất bại** |
| Upload song song | Không chia thành nhiều part ở mức S3 | Có thể gửi nhiều part đồng thời |
| Quản lý dọn dẹp khi thất bại | Đơn giản hơn | Phải Abort hoặc lifecycle dọn part chưa hoàn tất |
| Dùng cho file | Nhỏ/vừa, đường truyền ổn định | Lớn, cần retry/phục hồi hoặc song song |
| Ghi đè cùng key | Cập nhật phiên bản hiện hành | Complete sẽ tạo/cập nhật object hiện hành |

Không có một ngưỡng multipart duy nhất phù hợp mọi sản phẩm. Quyết định phụ thuộc kích thước file, môi trường mạng, yêu cầu tốc độ, giới hạn tài nguyên, chi phí request và SLA.

## 5. Multipart upload trên S3 hoạt động thế nào?

### 5.1. Vòng đời multipart

Một multipart upload có ít nhất ba giai đoạn:

1. **CreateMultipartUpload:** chọn bucket/key, metadata như Content-Type, nhận `uploadId` để định danh phiên upload đang diễn ra.
2. **UploadPart:** gửi dữ liệu từng part với **partNumber** (1–10.000) và `uploadId`; S3 trả `ETag` riêng cho từng part thành công.
3. **CompleteMultipartUpload:** gửi danh sách part theo **partNumber tăng dần**, kèm ETag tương ứng; S3 ghép các part thành một object hoàn chỉnh.

Nếu upload thất bại hoặc người dùng hủy, gọi **AbortMultipartUpload** để dọn các part đã truyền. Một `uploadId` chưa complete/abort không giống object hoàn chỉnh có thể GET bằng key.

~~~mermaid
stateDiagram-v2
    [*] --> ChuaBatDau
    ChuaBatDau --> DangUpload: CreateMultipartUpload
    DangUpload --> DangUpload: UploadPart #1, #2,...
    DangUpload --> HoanTat: CompleteMultipartUpload
    DangUpload --> Huy: AbortMultipartUpload
    HoanTat --> [*]: Object sẵn sàng
    Huy --> [*]: Part được dọn
~~~

~~~mermaid
sequenceDiagram
    participant A as Spring Boot
    participant S as Amazon S3

    A->>S: CreateMultipartUpload(bucket, key, metadata)
    S-->>A: uploadId
    A->>S: UploadPart(uploadId, partNumber=1, bytes)
    S-->>A: ETag #1
    A->>S: UploadPart(uploadId, partNumber=2, bytes)
    S-->>A: ETag #2
    A->>S: UploadPart(uploadId, partNumber=3, bytes)
    S-->>A: ETag #3
    alt tất cả part thành công
        A->>S: CompleteMultipartUpload(parts + ETags)
        S-->>A: Object được hoàn tất
    else lỗi không thể phục hồi
        A->>S: AbortMultipartUpload(uploadId)
        S-->>A: Hủy upload dang dở
    end
~~~

Các part có thể được truyền **không theo thứ tự** hoặc truyền lại cùng `partNumber`. S3 dùng phần đã upload thành công mới nhất cho partNumber đó trong cùng uploadId. Khi Complete, ứng dụng phải gửi đúng ETag của những part cuối cùng được chấp nhận và sắp xếp theo partNumber tăng dần.

### 5.2. Quy tắc kích thước và giới hạn

| Thuộc tính | Quy tắc cần nhớ |
| --- | --- |
| Part number | Số nguyên từ **1 đến 10.000** |
| Kích thước part | Thường **5 MiB đến 5 GiB**; **part cuối** có thể nhỏ hơn 5 MiB |
| Số part tối đa | **10.000** trong một multipart upload |
| Upload ID | Do S3 cấp, ràng buộc một phiên upload tới bucket/key |
| ETag của part | Giá trị trả về từ UploadPart; dùng lại chính xác khi Complete |
| ETag object sau Complete | **Không mặc nhiên là MD5** của toàn bộ nội dung |
| Metadata object | Các giá trị như Content-Type được khai báo khi **khởi tạo multipart** |
| Dữ liệu dang dở | Part đã upload nhưng chưa Complete/Abort vẫn có thể phát sinh chi phí lưu trữ |

Một object 100 MiB với part 8 MiB cần 13 part, trong đó part cuối 4 MiB được phép. Nếu dùng 8 MiB cho object lớn hơn khoảng 78 GiB, có thể chạm giới hạn 10.000 part; thiết kế thực tế phải **tính part size theo kích thước dự kiến** hoặc để SDK transfer layer chọn cách chia phù hợp.

## 6. Tự thực hiện multipart upload bằng `S3Client`

Phần này dùng **AWS SDK v2 đồng bộ** để hiểu vòng đời multipart và quản lý bộ nhớ. Code đọc tối đa 8 MiB mỗi vòng, gửi từng part tuần tự, rồi gọi Complete. Nó thích hợp để học hoặc cho một số luồng upload có thể kiểm soát; khi cần hiệu năng tốt hơn, cân nhắc `S3TransferManager` ở mục sau.

### 6.1. Service mẫu có Abort khi thất bại

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.AbortMultipartUploadRequest;
import software.amazon.awssdk.services.s3.model.CompleteMultipartUploadRequest;
import software.amazon.awssdk.services.s3.model.CompletedMultipartUpload;
import software.amazon.awssdk.services.s3.model.CompletedPart;
import software.amazon.awssdk.services.s3.model.CreateMultipartUploadRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.UploadPartRequest;
import software.amazon.awssdk.services.s3.model.UploadPartResponse;

@Service
public class BoundedMultipartUploader {
    private static final int PART_BYTES = 8 * 1024 * 1024;
    private static final int MAX_PARTS = 10_000;

    private final S3Client s3;
    private final String bucket;

    public BoundedMultipartUploader(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public String upload(InputStream source, String verifiedContentType)
            throws IOException {

        String key = "documents/" + UUID.randomUUID();

        // Đọc trước một chunk để xử lý file nhỏ hoặc file rỗng.
        byte[] firstChunk = source.readNBytes(PART_BYTES);

        if (firstChunk.length < PART_BYTES) {
            // Nhỏ hơn 8 MiB: một PUT là đủ, kể cả file 0 byte.
            s3.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .contentType(verifiedContentType)
                            .build(),
                    RequestBody.fromBytes(firstChunk));
            return key;
        }

        String uploadId = s3.createMultipartUpload(
                CreateMultipartUploadRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .contentType(verifiedContentType)
                        .build()
        ).uploadId();

        List<CompletedPart> completed = new ArrayList<>();
        int partNumber = 1;

        try {
            byte[] chunk = firstChunk;
            while (chunk.length > 0) {
                if (partNumber > MAX_PARTS) {
                    throw new IllegalArgumentException(
                            "Quá 10.000 part: tăng PART_BYTES");
                }

                UploadPartResponse result = s3.uploadPart(
                        UploadPartRequest.builder()
                                .bucket(bucket)
                                .key(key)
                                .uploadId(uploadId)
                                .partNumber(partNumber)
                                .build(),
                        RequestBody.fromBytes(chunk));

                completed.add(CompletedPart.builder()
                        .partNumber(partNumber)
                        .eTag(result.eTag())
                        .build());

                partNumber++;
                chunk = source.readNBytes(PART_BYTES);
            }

            s3.completeMultipartUpload(
                    CompleteMultipartUploadRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .uploadId(uploadId)
                            .multipartUpload(
                                    CompletedMultipartUpload.builder()
                                            .parts(completed)
                                            .build())
                            .build());
            return key;
        } catch (IOException | RuntimeException failure) {
            // Nếu đã tạo uploadId, phải cố hủy part chưa hoàn tất.
            try {
                s3.abortMultipartUpload(
                        AbortMultipartUploadRequest.builder()
                                .bucket(bucket)
                                .key(key)
                                .uploadId(uploadId)
                                .build());
            } catch (RuntimeException abortFailure) {
                failure.addSuppressed(abortFailure);
            }
            throw failure;
        }
    }
}
~~~

**Giải thích từng quyết định:**

- `readNBytes(PART_BYTES)` đọc cho đến đủ byte, EOF hoặc gặp lỗi; ví dụ yêu cầu Java 11+ (Spring Boot hiện đại thường dùng Java 17+). Chỉ có **một hoặc một vài mảng part** trong RAM, không có mảng byte chứa toàn bộ file.
- Nếu file nhỏ hơn 8 MiB, service dùng PUT đơn. Nếu file đúng 8 MiB, ví dụ sẽ dùng multipart một part; hợp lệ nhưng có thêm request nên production có thể chọn nhánh khác tùy bài toán.
- Mỗi `UploadPartResponse.eTag()` được giữ cùng partNumber. Danh sách `completed` được thêm tuần tự, nên có thứ tự tăng dần trước khi Complete.
- `PART_BYTES = 8 MiB` đáp ứng tối thiểu 5 MiB cho mọi part trừ part cuối. Trong ví dụ truyền tuần tự, mỗi chunk chưa phải phần cuối luôn đủ 8 MiB.
- Nếu gặp IOException lúc đọc nguồn, lỗi SDK lúc gửi part hoặc Complete, nhánh `catch` cố gọi Abort. Nếu Abort cũng lỗi, lỗi đó được đính kèm dưới dạng **suppressed exception** để giữ nguyên nguyên nhân đầu tiên.
- Service cố ý **không đóng `source`** vì nguồn do caller sở hữu. Mã gọi phải dùng try-with-resources hoặc đóng theo lifecycle phù hợp.
- Nếu Complete gặp timeout sau khi S3 đã xử lý thành công, trạng thái có thể **không rõ ràng với client**. Trong hệ thống thật cần truy vấn lại `HeadObject`/version ID, xử lý retry có kiểm soát và đối soát dữ liệu, thay vì tự động kết luận thất bại tuyệt đối.

Code trên chỉ minh họa xử lý phần upload. Khi triển khai production, cần xác thực file, giới hạn tốc độ/đồng thời, xử lý độ dài nguồn tối đa, chọn part size theo kích thước, log uploadId có kiểm soát, timeout, checksum và giám sát trạng thái upload. Không gọi trực tiếp `upload(InputStream, ...)` với dữ liệu không giới hạn kích thước mà thiếu quota.

### 6.2. Retry một part như thế nào?

Ví dụ khi part #3 bị lỗi tạm thời:

~~~text
uploadId = "u-123"
part 1 → thành công → ETag-A
part 2 → thành công → ETag-B
part 3 → mất kết nối
part 3 → gửi lại với partNumber=3 → thành công → ETag-C
part 4 → thành công → ETag-D

Complete: [(1, ETag-A), (2, ETag-B), (3, ETag-C), (4, ETag-D)]
~~~

Retry cùng `uploadId` và `partNumber` có thể **thay part trước** nếu part đã được S3 nhận; phải cập nhật ETag theo response của lần gửi thành công được sử dụng. AWS SDK đã có cơ chế retry theo cấu hình, nên không nhân số lần retry ở nhiều tầng một cách tùy tiện.

Nếu upload song song, hoàn tất part theo thứ tự nào cũng được, nhưng **Complete yêu cầu danh sách có thứ tự partNumber tăng dần**. Dữ liệu dùng cho một part phải có khả năng tái gửi ổn định khi retry; tệp local hoặc bộ đệm riêng cho part thuận tiện hơn một stream đầu vào một chiều không thể seek.

### 6.3. Quyền Abort và cơ chế dọn upload bị bỏ dở

Mã gọi Abort chỉ chạy nếu ứng dụng còn biết `uploadId` và còn thực thi nhánh xử lý lỗi. Nếu process bị kill, máy mất điện hoặc container bị xóa, mã `catch` không có cơ hội chạy. Vì vậy cần bổ sung **S3 Lifecycle rule có `AbortIncompleteMultipartUpload`** sau một số ngày phù hợp chính sách.

~~~text
Lifecycle rule (ý tưởng):
- Prefix: documents/
- Abort incomplete multipart uploads after: N days
- N được chọn theo thời lượng upload hợp lệ và yêu cầu khôi phục.
~~~

Không được nhầm rule này với xóa object đã hoàn tất. Các part chưa hoàn tất có thể phát sinh chi phí; rule dọn định kỳ giúp giảm phần tồn đọng. Nếu hệ thống hỗ trợ resume sau nhiều giờ/ngày, chọn thời gian lifecycle đủ dài và lưu trạng thái `uploadId`, partNumber/ETag vào nơi bền vững theo chính sách.

## 7. S3 Transfer Manager: lựa chọn cấp cao cho file lớn

Thay vì tự xây vòng Create → UploadPart → Complete → Abort, AWS SDK v2 cung cấp **`S3TransferManager`** để xử lý truyền file, multipart, theo dõi tiến độ và nhiều chi tiết retry. Nó phù hợp khi nguồn đã có dạng `Path` hoặc khi dự án cần throughput tốt, upload/download có kiểm soát.

Ví dụ ý tưởng sử dụng Transfer Manager cho một file local:

~~~java
import java.nio.file.Path;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.transfer.s3.S3TransferManager;
import software.amazon.awssdk.transfer.s3.model.UploadFileRequest;

// Cần dependency AWS SDK v2: s3-transfer-manager và
// các thư viện HTTP/CRT tương thích cho S3AsyncClient đã chọn.
try (S3AsyncClient asyncClient =
             S3AsyncClient.crtBuilder()
                     .region(Region.AP_SOUTHEAST_1)
                     .build();
     S3TransferManager manager =
             S3TransferManager.builder()
                     .s3Client(asyncClient)
                     .build()) {

    UploadFileRequest request = UploadFileRequest.builder()
            .source(Path.of("reports/large-report.csv"))
            .putObjectRequest(p -> p
                    .bucket("training-private-docs")
                    .key("documents/reports/large-report.csv")
                    .contentType("text/csv"))
            .build();

    manager.uploadFile(request).completionFuture().join();
}
~~~

Đoạn trên là **ví dụ minh họa lớp API**. Để build, cần thêm `software.amazon.awssdk:s3-transfer-manager` tương thích với BOM AWS SDK v2 và **AWS CRT dependency phù hợp** nếu dùng `S3AsyncClient.crtBuilder()`; xác nhận các artifact/phiên bản theo dự án. AWS SDK còn cung cấp cấu hình client async multipart khác tùy phiên bản.

Trong ứng dụng Spring Boot chạy liên tục, không tạo/đóng `S3TransferManager` và `S3AsyncClient` cho từng request như đoạn demo có `try-with-resources`. Nên cấu hình chúng như **bean dùng chung**, quản lý lifecycle qua Spring, rồi inject vào service. Thư viện transfer sẽ xử lý upload/download từ file hoặc nguồn được hỗ trợ; vẫn cần giới hạn concurrency, băng thông, quota và theo dõi kết quả hoàn tất.

**Không giả định `S3Template.upload` tự động triển khai multipart cho mọi `InputStream`.** Abstraction của Spring Cloud AWS làm giảm boilerplate nhưng cách upload cụ thể phụ thuộc API và phiên bản. Khi cần bảo đảm multipart, concurrency và retry ở mức part, sử dụng SDK transfer API được cấu hình rõ ràng là lựa chọn dễ kiểm chứng hơn.

## 8. Direct upload từ trình duyệt: presigned PUT và presigned multipart

Khi client tải file lớn, Spring Boot không nhất thiết phải nhận và truyền lại toàn bộ file. Backend có thể chỉ quản lý quyền và phiên upload; **browser/mobile gửi dữ liệu thẳng tới S3**.

### 8.1. Một presigned PUT

~~~mermaid
sequenceDiagram
    actor U as Client
    participant A as Spring Boot API
    participant D as Database
    participant S as S3 bucket private

    U->>A: Xin upload (tên, loại, kích thước)
    A->>A: Xác thực, kiểm quota, tạo key
    A->>D: Lưu trạng thái PENDING_UPLOAD
    A-->>U: Presigned PUT URL + key (thời hạn ngắn)
    U->>S: PUT tệp trực tiếp bằng URL
    S-->>U: Kết quả PUT
    U->>A: Báo hoàn tất
    A->>S: HEAD object, kiểm thuộc tính
    A->>D: Đổi trạng thái READY nếu hợp lệ
~~~

Một presigned PUT URL chỉ cho phép thực hiện request đã ký theo thời hạn/quy tắc chữ ký, **không biến bucket private thành public**. URL là dạng bearer capability: ai có URL còn hiệu lực có thể sử dụng trong phạm vi ký. Tránh lưu URL nguyên vẹn trong log và không cấp URL trước khi xác thực quyền user/tenant.

Với PUT URL, các header được ký phải khớp request client gửi. Nếu cần áp giới hạn upload nghiêm ngặt ở mức request, cân nhắc cơ chế hỗ trợ điều kiện kích thước phù hợp như **presigned POST policy** hoặc kiểm tra kích thước sau upload và chính sách quota. Không mặc nhiên cho rằng presigned PUT chỉ vì có URL hết hạn ngắn đã chặn được file lớn bất kỳ.

### 8.2. Presigned multipart cho tệp rất lớn

Mẫu triển khai thường gồm:

1. Spring Boot kiểm tra quyền, tạo key và gọi `CreateMultipartUpload` để nhận `uploadId`.
2. Backend cấp **presigned UploadPart URL** cho từng partNumber được phép, ràng buộc đúng bucket/key/uploadId.
3. Client chia tệp và PUT từng part trực tiếp lên S3; thu thập **ETag** của từng response UploadPart.
4. Client báo backend danh sách partNumber/ETag. Backend đối chiếu phiên upload, owner, quota và dữ liệu client gửi trước khi gọi `CompleteMultipartUpload`.
5. Nếu người dùng hủy, backend gọi `AbortMultipartUpload`; bổ sung lifecycle cleanup khi client không quay lại.

~~~mermaid
flowchart LR
    Browser["Browser: chia file thành part"] -->|"xin URL từng part"| API["Spring Boot: xác thực và ký"]
    API -->|"CreateMultipartUpload / presign"| S3["S3 bucket private"]
    API -->|"Presigned UploadPart URLs"| Browser
    Browser -->|"PUT part #1..N trực tiếp"| S3
    Browser -->|"ETag từng part + hoàn tất"| API
    API -->|"CompleteMultipartUpload"| S3
~~~

Cấu hình **S3 CORS** phù hợp là điều kiện khi browser gọi S3 cross-origin. Để client JavaScript đọc được ETag từ header response, CORS thường cần expose `ETag`. CORS **không cấp quyền S3**; request vẫn phải được ký và hợp lệ theo IAM/bucket policy.

Presigned multipart có thêm trách nhiệm: giới hạn thời hạn URL, theo dõi uploadId, chống lẫn part của user khác, ngăn Complete trái phép, hủy upload bỏ dở và xử lý retry khi một part lỗi. Không cho phép client tự truyền một uploadId/key bất kỳ để backend Complete mà thiếu đối chiếu ownership.

## 9. Tính toàn vẹn, metadata, timeout và chi phí

### 9.1. Kiểm tra toàn vẹn

Một object được lưu thành công không đồng nghĩa nó khớp chính xác với tài liệu nghiệp vụ mong đợi. Để xác minh:

- Dùng **checksum** được AWS SDK/S3 hỗ trợ khi upload, chẳng hạn SHA-256 hoặc CRC tùy tính năng và thuật toán. Quy tắc checksum multipart có thể khác một PUT thông thường và cần metadata/checksum nhất quán giữa các part và Complete.
- Xem lại `Content-Length`, `Content-Type`, version ID và checksum qua API/response phù hợp.
- Với ứng dụng yêu cầu chứng minh byte-for-byte, có thể tính hash độc lập ở nguồn và sau khi tải lại mẫu dữ liệu; chọn thuật toán và quy trình phù hợp với kích thước và yêu cầu bảo mật.

**Không mặc định ETag bằng MD5 của toàn bộ object**. ETag của object multipart thường được tính theo cơ chế khác, và hình thức mã hóa/cấu hình upload cũng ảnh hưởng ý nghĩa ETag. ETag của mỗi part trong `UploadPartResponse` vẫn phải được lưu chính xác để Complete.

### 9.2. Metadata được đặt lúc nào?

Với multipart, các thuộc tính như `Content-Type`, `Content-Disposition`, user-defined metadata và tùy chọn mã hóa thường được khai báo khi **CreateMultipartUpload**. `UploadPart` chuyển byte của part; nó không phải điểm thiết lập lại metadata chung của object.

Ví dụ:

~~~java
var created = s3.createMultipartUpload(
        CreateMultipartUploadRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("application/pdf")
                .metadata(java.util.Map.of("source", "portal"))
                .build());
~~~

Khi Complete thành công, object cuối có metadata tương ứng với những thuộc tính đã được khai báo. Tránh đưa secret, access token, dữ liệu cá nhân nhạy cảm hoặc thông tin không nên xuất hiện trong header S3 vào metadata.

### 9.3. Kiểm soát timeout và retry

Với file lớn, cần phân biệt:

- **Connection timeout:** thời gian thiết lập kết nối.
- **API call timeout:** thời gian tối đa cho cả lời gọi SDK.
- **Read/idle timeout:** kết nối đã mở nhưng byte không tiến triển.
- **Retry/backoff:** số lần thử lại, jitter và giới hạn tổng thời gian.
- **HTTP client connection pool / concurrency:** số luồng tải dữ liệu đồng thời.

Không đặt timeout quá ngắn cho mọi file lớn, cũng không cho phép upload treo vô hạn. Quy tắc timeout phải dựa trên dung lượng tối đa, tốc độ mạng kỳ vọng và khả năng resume/abort. Khi caller bị hủy request HTTP, tiến trình upload backend có thể tiếp tục nếu không truyền tín hiệu hủy; cần thiết kế lifecycle rõ ràng.

### 9.4. Các nguồn chi phí

Streaming hoặc multipart không loại bỏ phí S3. Các khoản có thể gồm:

- Số lượng request PUT/UploadPart/Complete/HEAD/GET.
- Dung lượng object đã hoàn tất và **dung lượng part multipart chưa hoàn tất**.
- Data transfer giữa các dịch vụ, giữa Region hoặc từ cloud ra ngoài.
- SSE-KMS request, lifecycle/replication/storage class tùy cấu hình.

Part càng nhỏ, số request và overhead càng cao; part càng lớn, bộ nhớ mỗi tác vụ, thời gian retry và tác động khi part lỗi càng đáng kể. Cần quan sát throughput, tổng số part và chi phí thay vì chỉ chọn partSize theo một giá trị cố định.

## 10. Kiểm thử streaming và multipart có kiểm soát

### 10.1. Các lớp kiểm thử

| Mức kiểm thử | Nội dung phù hợp | Hạn chế |
| --- | --- | --- |
| Unit test (mock) | Chunk boundary, partNumber, danh sách ETag, gọi Abort khi lỗi | Không xác minh S3 ghép part thật |
| Integration test với S3-compatible emulator | Upload nhiều part, Complete, GET byte, Abort, stream đóng đúng | Không bảo đảm giống mọi IAM/KMS hoặc edge case AWS |
| AWS sandbox | Permission, timeout, checksum, versioning, lifecycle, aborted upload và chi phí | Cần bucket/quota, quyền tối thiểu, dọn dữ liệu |

Kịch bản khuyến nghị:

1. Tạo bucket sandbox riêng, key ngẫu nhiên dưới `documents/lab-<id>/`, role có đúng quyền PUT/GET/Abort.
2. Upload tệp **nhỏ hơn part size** để xác minh nhánh PUT đơn và một tệp **lớn hơn 2 part size** để xác minh nhiều UploadPart.
3. GET object bằng stream và so sánh **byte** hoặc checksum đáng tin cậy với dữ liệu nguồn.
4. Mô phỏng lỗi ở part thứ hai bằng mock hoặc môi trường test có khả năng gây lỗi; kiểm tra Abort được gọi đúng uploadId.
5. Thử file rỗng, file có kích thước đúng bằng partSize, file dư 1 byte so với partSize và file có part cuối dưới 5 MiB.
6. Xác minh metadata, Content-Type, response status, quyền IAM và trạng thái key sau Complete.
7. Kiểm tra lifecycle cleanup cho upload tồn đọng trên AWS sandbox và dọn toàn bộ object/version test.

**Không** dùng bucket dữ liệu thật, file người dùng thật hay khóa production để thử fault injection và delete/abort.

### 10.2. Minh họa bài test kiểm tra nội dung

Đây là logic ví dụ để ghép với setup/teardown của test framework; nó không bao gồm môi trường AWS thật:

~~~java
byte[] expected = new byte[20 * 1024 * 1024 + 123];
new java.util.Random(42).nextBytes(expected);

String key;
try (var input = new java.io.ByteArrayInputStream(expected)) {
    key = uploader.upload(input, "application/octet-stream");
}

byte[] actual;
try (var source = s3.getObject(b -> b
        .bucket(bucket)
        .key(key))) {
    actual = source.readAllBytes(); // Chỉ làm trong test có kích thước giới hạn.
}

if (!java.util.Arrays.equals(expected, actual)) {
    throw new AssertionError("Multipart upload không toàn vẹn");
}
~~~

`readAllBytes()` được dùng **chỉ trong test với dữ liệu giới hạn** để so sánh dễ dàng. Production download tệp lớn nên copy stream hoặc so sánh checksum theo từng khối. Trong test thực tế cần dọn key trong `finally` và hủy các upload chưa hoàn tất; nếu bucket bật versioning, việc dọn phiên bản cần xử lý riêng.

### 10.3. Khả năng phục hồi và kiểm thử sự cố

Một số tình huống cần thiết kế trước:

- Client mất mạng giữa `UploadPart`: retry riêng part nếu còn uploadId và dữ liệu nguồn có thể đọc lại.
- Ứng dụng mất kết nối sau `CompleteMultipartUpload`: kiểm tra kết quả qua HEAD/version/đối soát, tránh tạo nhiều object trùng nghiệp vụ.
- Process bị kill trước Abort: lifecycle rule thu dọn part quá hạn.
- Trình duyệt upload xong nhưng chưa báo backend: backend cần trạng thái `PENDING_UPLOAD`, timeout và cơ chế xác minh để chuyển sang `READY`.
- Người dùng hủy khi nhiều part đang truyền: dừng các tác vụ đang gửi, sau đó Abort; một số request đang chạy có thể cần kết thúc trước khi cleanup hoàn toàn.

## 11. Liên hệ với Azure và Google Cloud

Cả ba cloud đều hỗ trợ truyền file lớn và nhận dữ liệu qua API, nhưng **giao thức phân mảnh và xác thực khác nhau**:

| Bài toán | AWS / Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Đọc dữ liệu dạng luồng | S3 GET stream / range | Blob download stream/range | Object read/range |
| Upload object thông thường | PutObject | Upload blob | Upload/create object |
| File lớn phục hồi từng phần | S3 Multipart Upload (UploadPart + Complete) | Block blob: stage blocks + commit block list | Resumable upload session |
| Danh tính ứng dụng | IAM role / AWS SDK credentials | Managed identity / Azure Identity | Service account / Application Default Credentials |
| URL tạm cho client | Presigned URL | Shared Access Signature (SAS) | Signed URL |
| Dọn tác vụ dang dở | AbortMultipartUpload + lifecycle cleanup | Quản lý block chưa commit theo chính sách provider | Quản lý session chưa hoàn tất theo giao thức provider |

Module **SPRING_CLOUD_PROVIDER_INTEGRATION** có thể dùng một interface ứng dụng như:

~~~java
public interface ObjectTransferPort {
    String upload(java.io.InputStream source,
                  long knownLength,
                  String contentType) throws java.io.IOException;

    void download(String trustedObjectKey,
                  java.io.OutputStream destination)
            throws java.io.IOException;
}
~~~

Adapter AWS dùng `S3Client`/`S3TransferManager`; adapter Azure hoặc GCP dùng SDK phù hợp. Tuy vậy, **không ép tất cả provider chia sẻ cùng thuật ngữ uploadId/partNumber/ETag**. Phần hợp đồng nghiệp vụ nên mô tả độ lớn, ownership, stream và kết quả; chi tiết chiến lược multipart/resume, checksum hoặc signed upload do adapter quản lý.

Khi đánh giá đa cloud, cần so sánh thêm chi phí truyền giữa region, quota, thiết lập secret/identity, trải nghiệm retry, kiểm thử trên emulator, quyền IAM/RBAC và quy trình cleanup của provider.

## 12. Bài tập thực hành và câu hỏi ôn tập

### Bài tập 1 — Đo bộ nhớ

Tạo endpoint Spring Boot nhận file 30 MiB ở sandbox. So sánh luồng dùng `MultipartFile.getBytes()` với luồng dùng `getInputStream()` và `RequestBody.fromInputStream(..., size)`. Quan sát heap, thời gian xử lý và giới hạn số request đồng thời. Giải thích vì sao `getInputStream()` không bảo đảm servlet container chưa từng buffer multipart form.

### Bài tập 2 — Multipart thủ công

Với uploader mẫu, upload lần lượt file rỗng, 2 MiB, 8 MiB, 8 MiB + 1 byte, 20 MiB và 50 MiB; ghi lại số part, độ dài part cuối, thời gian và kết quả HEAD. Kiểm tra dữ liệu tải xuống giống byte nguồn. Dự đoán số part trước khi chạy.

### Bài tập 3 — Fault injection và cleanup

Dùng mock client hoặc S3 emulator để làm part thứ hai trả lỗi. Xác minh code không gọi Complete, có gọi Abort và exception ban đầu được giữ lại. Mô phỏng thêm Abort cũng thất bại, kiểm tra suppressed exception. Trình bày vì sao lifecycle cleanup vẫn cần thiết.

### Bài tập 4 — Browser direct upload

Thiết kế API tạo phiên upload, ký UploadPart URL, xác minh ETag/owner trước Complete và hủy phiên. Chỉ rõ endpoint nào cần authentication, cách giới hạn thời gian URL, cách client đọc ETag qua CORS và cách chống Complete nhầm uploadId của người dùng khác.

### Bài tập 5 — Đánh giá đa cloud

Lập bảng kế hoạch upload file 2 GiB cho AWS, Azure và GCP: cơ chế truyền, resume, danh tính workload, kiểm soát quyền và cleanup. Đề xuất một interface nghiệp vụ dùng chung; chỉ ra tính năng nào phải giữ đặc thù provider.

### Câu hỏi tự kiểm tra

1. Streaming và multipart upload có khác nhau ở tầng nào?
2. Vì sao không nên đọc toàn bộ `MultipartFile` thành byte array khi nhiều người dùng upload đồng thời?
3. Điều gì có thể xảy ra nếu `RequestBody.fromInputStream` nhận `contentLength` sai?
4. `UploadId`, `partNumber` và `ETag` được dùng vào bước nào của multipart?
5. Vì sao phải sắp xếp `CompletedPart` theo partNumber khi Complete?
6. Khi nào part cuối được nhỏ hơn 5 MiB?
7. Khi upload dừng đột ngột và `catch` không được chạy, cách nào dọn part đang tồn đọng?
8. Tại sao ETag của object multipart không nên được coi là MD5 của nội dung?
9. Vì sao `StreamingResponseBody` không tự động biến `S3Client` đồng bộ thành non-blocking?
10. Khi nào nên dùng `S3TransferManager` hoặc presigned multipart thay vì tự viết vòng UploadPart?
11. Những loại lỗi nào cần retry riêng từng part và những lỗi nào phải dừng để kiểm tra IAM/quota?
12. Vì sao một interface multi-cloud nên trừu tượng hóa upload/download mà vẫn giữ chi tiết multipart trong adapter?

Kết thúc bài học, bạn có thể xây dựng luồng truyền file có bộ nhớ giới hạn trong Spring Boot, hiểu đầy đủ vòng đời **CreateMultipartUpload → UploadPart → Complete/Abort**, kiểm soát quyền truy cập, retry, checksum và tài nguyên dang dở, đồng thời chọn cách truyền dữ liệu phù hợp khi triển khai trên các cloud provider khác nhau.

