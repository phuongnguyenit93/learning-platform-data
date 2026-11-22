# Lưu trữ tệp ứng dụng bằng S3

Một ứng dụng Spring Boot cho phép người dùng tải ảnh đại diện, hóa đơn PDF, tài liệu hợp đồng hoặc video lên hệ thống. Nếu lưu toàn bộ bytes vào ổ đĩa của container, dữ liệu có thể biến mất khi pod/task được thay thế, khó chia sẻ giữa nhiều instances và làm application server phải gánh cả nhiệm vụ lưu trữ. **Amazon S3** giải quyết bài toán này bằng object storage có khả năng mở rộng, độ bền cao và tích hợp trực tiếp với IAM, KMS, CloudWatch, EventBridge và các dịch vụ AWS khác.

Trong kiến trúc Java, ứng dụng thường lưu **object key và metadata nghiệp vụ trong database**, còn bytes nằm trong bucket S3. Backend có thể upload/download qua **AWS SDK for Java 2.x**, hoặc cấp **presigned URL** để browser/mobile truyền file trực tiếp tới S3. Với file lớn, **multipart upload** và **S3 Transfer Manager** tăng throughput, hỗ trợ retry từng phần và tránh đưa toàn bộ dữ liệu qua API server.

Bài thuộc chương **Ứng dụng Java và Spring Boot**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung gắn với Region/AZ, IAM, VPC, compute, database, serverless, giám sát, khả năng phục hồi và kiểm soát chi phí. Ví dụ sử dụng Java 17+, Spring Boot, AWS SDK for Java 2.x và một bucket private trong Region được cấu hình bên ngoài.

> **Nguyên tắc thiết kế:** S3 lưu **object bytes**; database lưu **quyền sở hữu và trạng thái nghiệp vụ**; Spring Boot xác thực người dùng, quyết định object key và điều phối upload/download. Không dùng tên file do client gửi làm đường dẫn lưu trữ, không mở bucket public để phục vụ file riêng tư và không giữ file lớn trong RAM chỉ để chuyển tiếp.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích bucket, object, key, metadata, tags, version và storage class của S3.
2. Thiết kế object key an toàn cho multi-tenant Spring Boot application.
3. Tích hợp AWS SDK for Java 2.x với Maven BOM và Spring dependency injection.
4. Upload/download object bằng `S3Client` và xử lý stream có kiểm soát.
5. Giới hạn kích thước, xác thực MIME/file signature và kiểm tra quyền truy cập.
6. Phân biệt upload qua backend với direct upload bằng presigned URL.
7. Sinh presigned GET/PUT URL và quản lý thời hạn, signed headers, quyền của signer.
8. Chọn single PUT, multipart upload hoặc S3 Transfer Manager theo kích thước/workload.
9. Bảo vệ tính toàn vẹn bằng checksum; hiểu vì sao ETag không phải luôn là MD5.
10. Thiết kế DB metadata, idempotency, trạng thái upload và reconciliation giữa S3/DB.
11. Cấu hình IAM least privilege, Block Public Access, Object Ownership, SSE-S3/SSE-KMS, TLS và CORS.
12. Dùng Versioning, Lifecycle, replication, backup và storage classes.
13. Tích hợp S3 events, SQS/EventBridge/Lambda và xử lý duplicate/out-of-order.
14. Quan sát, troubleshooting và tối ưu chi phí S3 trong production.

## 2. Kiến trúc lưu trữ tệp trong Spring Boot

~~~mermaid
flowchart TD
    USER["Browser / Mobile"] --> API["Spring Boot API"]
    API --> AUTH["Authentication + authorization"]
    AUTH --> DB[("RDS / DynamoDB<br/>File metadata + ownership")]
    API --> SDK["AWS SDK for Java 2.x"]
    SDK --> S3[("Private S3 bucket<br/>Objects / versions")]
    API --> PRESIGN["S3Presigner"]
    PRESIGN -->|"Short-lived URL"| USER
    USER -->|"Direct PUT / GET"| S3
    S3 --> EVT["S3 Event / EventBridge"]
    EVT --> Q["SQS / Lambda / scanner"]
    Q --> DB
~~~

Có hai luồng chính:

- **Backend proxy:** browser gửi multipart request tới Spring Boot; backend validate rồi upload S3. Dễ kiểm soát request, phù hợp file vừa/nhỏ, nhưng API server chịu bandwidth, connection và disk/RAM pressure.
- **Direct-to-S3:** backend xác thực, tạo metadata record và cấp presigned URL; browser upload/download trực tiếp với S3. Backend không phải truyền toàn bộ bytes, phù hợp file lớn hoặc nhiều clients.

Trong cả hai mô hình, database giữ record như `fileId`, `tenantId`, `objectKey`, `originalFilename`, `contentType`, `size`, `checksum`, `status`, `createdAt`, `uploadedAt`. **Không lưu bytes của file trong DB chỉ vì application đang dùng relational database**, trừ khi có yêu cầu đặc biệt đã được đánh giá.

### 2.1. Trách nhiệm của từng thành phần

| Thành phần | Trách nhiệm |
|---|---|
| Spring Controller | Nhận HTTP request, validate request boundary, trả response |
| Authentication/authorization | Xác định user, tenant, quyền upload/download |
| File service | Tạo key, validate metadata, điều phối trạng thái |
| S3 SDK client | Gọi Put/Get/Head/Delete/List/Copy |
| S3Presigner | Tạo URL tạm thời với HTTP method và key cụ thể |
| S3 bucket | Lưu bytes, version, encryption, lifecycle |
| Database | Lưu owner, tenant, file status, object key và business metadata |
| SQS/EventBridge/Lambda | Scan malware, tạo thumbnail, indexing, xử lý hậu upload |
| CloudWatch/CloudTrail | Quan sát request, errors, access và thay đổi cấu hình |

Không khởi tạo bucket mỗi lần user upload. Bucket và security settings nên được provision bằng IaC (CloudFormation/CDK/Terraform) hoặc quy trình nền tảng có kiểm soát; application chỉ thao tác trên bucket được cấu hình.

## 3. S3 object model: bucket, key và metadata

S3 là **object storage**. Một object gồm data, key, metadata, tags, version ID và các thuộc tính như storage class/encryption. Tên bucket phải duy nhất trong namespace phù hợp; key xác định object bên trong bucket.

~~~text
Bucket: company-private-files-prod
Key:    tenants/tenant-42/invoices/2026/11/01JAZ...pdf
Object: bytes + system metadata + user metadata + tags + version
~~~

### 3.1. Key không phải filesystem path

S3 không có thư mục thật theo semantics của filesystem. Các dấu `/` trong key chỉ giúp tổ chức prefix và hiển thị như folder trong console. Key là một chuỗi phân biệt chữ hoa/thường và có quy tắc ký tự/encoding riêng.

Không tạo key bằng cách nối trực tiếp:

~~~java
String key = "uploads/" + multipartFile.getOriginalFilename();
~~~

`getOriginalFilename()` do client gửi, có thể chứa path segments, ký tự đặc biệt, tên trùng hoặc tên gây nhầm lẫn. Hãy sinh key phía server:

~~~java
String key = "tenants/" + tenantId
        + "/files/" + UUID.randomUUID();
~~~

Nếu cần giữ tên file gốc, lưu riêng trong database hoặc metadata đã sanitize. Tên hiển thị không phải object identity.

### 3.2. Prefix và multi-tenancy

Một key convention có thể là:

~~~text
tenants/{tenantId}/uploads/{yyyy}/{MM}/{fileId}
~~~

- `tenantId` lấy từ security principal đã xác thực, không tin field do browser gửi.
- `fileId` là UUID/ULID do server sinh.
- Không để user tự chọn prefix tùy ý nếu có nguy cơ ghi/đọc sang tenant khác.
- IAM có thể giới hạn theo prefix bằng policy conditions khi thiết kế phù hợp, nhưng authorization theo từng file vẫn nên được kiểm tra trong ứng dụng.
- Với lượng object rất lớn, tránh tạo một prefix nóng theo một key pattern cố định nếu workload cần phân tán; đo request distribution trước khi thiết kế sharding.

### 3.3. Metadata, tags và database record

| Nơi lưu | Dùng cho | Đặc điểm |
|---|---|---|
| System metadata | Content-Type, Content-Length, Last-Modified, ETag, storage class | S3 quản lý |
| User metadata | `x-amz-meta-*`, upload ID, nguồn tạo | Gắn khi upload; muốn đổi metadata thường phải copy object |
| Object tags | Phân loại retention/cost/access workflow | Có thể cập nhật độc lập qua tagging API |
| Application DB | Owner, tenant, original name, status, scan result, business link | Query nghiệp vụ, authorization và audit |

Không nhét toàn bộ hồ sơ nghiệp vụ vào user metadata. Metadata không thay database index, có giới hạn kích thước và không phù hợp cho các truy vấn theo nhiều thuộc tính.

### 3.4. Một object key có thể được overwrite

`PutObject` lên cùng key sẽ thay object hiện tại (khi versioning tắt) hoặc tạo version mới (khi versioning bật). Do đó, key do server tạo duy nhất theo file ID thường an toàn hơn key dựa trên `avatar.jpg` hay `invoice.pdf`.

Nếu nghiệp vụ muốn “thay file”, cân nhắc tạo file version mới hoặc dùng S3 Versioning và ghi `versionId` vào DB. Đừng vô tình để presigned PUT ghi đè object đã tồn tại mà không có policy.

## 4. Chọn mô hình upload: backend proxy hay direct-to-S3?

| Tiêu chí | Backend proxy | Presigned direct upload |
|---|---|---|
| Bytes đi qua | Browser → Spring → S3 | Browser → S3 |
| Tải mạng backend | Cao hơn | Thấp hơn |
| Kiểm soát upload | Dễ validate/scan trước khi gửi | Validate trước và hậu kiểm sau upload |
| File lớn | Cần streaming/disk temp hoặc transfer manager | Rất phù hợp; multipart có thể do client/transfer flow |
| IAM credentials cho browser | Không cần | Không cần; URL mang chữ ký tạm thời |
| Khả năng triển khai | Ít thành phần hơn | Cần upload session/finalize workflow |
| CORS | Thường không cần S3 CORS nếu browser chỉ gọi API | Cần CORS phù hợp cho browser cross-origin |
| Use case | File nhỏ/vừa, policy xử lý ở server | File lớn, nhiều client, giảm backend bandwidth |

Không có một ngưỡng file duy nhất cho mọi ứng dụng. Chọn dựa trên file size distribution, throughput, server bandwidth, latency, validation requirements, network và chi phí.

## 5. Cấu hình Spring Boot multipart upload

Spring MVC dùng multipart resolver để nhận `MultipartFile`. Cần giới hạn kích thước ở **application layer**, reverse proxy/load balancer và gateway nếu có.

### 5.1. Application properties

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=20MB
spring.servlet.multipart.max-request-size=21MB
spring.servlet.multipart.file-size-threshold=1MB
~~~

Các giá trị trên là ví dụ cho endpoint upload nhỏ/vừa. `max-file-size` giới hạn một file, `max-request-size` giới hạn tổng multipart request. `file-size-threshold` quyết định ngưỡng trước khi multipart content được ghi ra disk temp theo cấu hình servlet container. Hãy đặt giới hạn nhất quán với ingress/API Gateway, disk capacity và business policy.

### 5.2. MultipartFile không có nghĩa file luôn nằm trong RAM

Tùy servlet container/configuration, multipart resolver có thể giữ phần nhỏ trong memory và ghi phần lớn ra temporary disk. Vì thế:

- Tránh `multipartFile.getBytes()` cho file lớn vì tạo byte array toàn bộ trong heap.
- Ưu tiên `getInputStream()` và đóng stream đúng cách.
- Xác minh size trước khi upload và đảm bảo stream length đúng khi dùng API cần content length.
- Dọn temp files nếu tự tạo file trung gian.
- Giới hạn số upload đồng thời và request duration; một upload lâu có thể giữ HTTP connection/threads.

### 5.3. Validate file trước khi lưu

`Content-Type`, extension và original filename do client gửi **không đáng tin**. Cần phối hợp:

1. Cho phép một danh sách file types theo use case (PDF, JPEG, PNG…).
2. Kiểm tra extension đã normalize và MIME type sniff từ bytes/magic signature.
3. Giới hạn kích thước, số trang/độ phân giải/thời lượng nếu nghiệp vụ yêu cầu.
4. Quét malware bằng service phù hợp trước khi file được công khai/cho tải.
5. Chống archive bombs, polyglot files, HTML/script upload và path traversal.
6. Lưu file vào trạng thái quarantine/pending cho tới khi scan xong.
7. Không render HTML/SVG do user upload inline trên cùng origin ứng dụng nếu chưa sanitize.

Validation ở browser chỉ giúp UX; backend phải thực hiện kiểm tra bắt buộc.

## 6. Upload file nhỏ/vừa bằng AWS SDK for Java 2.x

Dùng `S3Client` và `RequestBody` để upload từ Path, File hoặc InputStream. Ví dụ sau dùng `MultipartFile` cho file đã được Spring giới hạn kích thước.

### 6.1. Maven dependencies

AWS SDK v2 nên dùng BOM như bài trước. Khai báo service module `s3` không cần version riêng khi BOM đã import:

~~~xml
<project>
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
</project>
~~~

`aws.sdk.version` phải được định nghĩa ở parent POM hoặc project properties bằng một version đã được phê duyệt. Không copy một version cũ không kiểm tra vào production.

### 6.2. S3Client singleton bean

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class S3Configuration {
    @Bean(destroyMethod = "close")
    S3Client s3Client(@Value("${app.aws.region}") String region) {
        return S3Client.builder()
                .region(Region.of(region))
                .build();
    }
}
~~~

Client dùng default credentials provider chain. Trên Lambda/ECS/EC2/EKS nên dùng workload IAM role phù hợp; không đặt access key/secret key trong `application.properties`.

### 6.3. Service upload

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class S3FileStorageService {
    private final S3Client s3;
    private final String bucket;

    public S3FileStorageService(
            S3Client s3,
            @Value("${app.s3.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public String upload(String tenantId, MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File must not be empty");
        }

        String fileId = UUID.randomUUID().toString();
        String key = "tenants/" + tenantId + "/uploads/" + fileId;

        String contentType = file.getContentType() == null
                ? "application/octet-stream"
                : file.getContentType();

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(contentType)
                .contentLength(file.getSize())
                .metadata(Map.of("file-id", fileId))
                .build();

        try (InputStream input = file.getInputStream()) {
            s3.putObject(request,
                    RequestBody.fromInputStream(input, file.getSize()));
        }

        return key;
    }
}
~~~

Đây là code minh họa cho **file size đã được giới hạn**. Trước production cần validate `tenantId` lấy từ principal và chuẩn hóa thành ID an toàn cho key (ví dụ UUID hoặc chuỗi chỉ gồm ký tự được cho phép), MIME/file signature, quyền upload, quota và metadata; không tin `getContentType()` là bằng chứng file thật sự thuộc loại đó. Lưu thêm file record trong DB theo workflow nhất quán ở phần sau.

### 6.4. Controller

~~~java
import java.io.IOException;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/files")
public class FileUploadController {
    private final S3FileStorageService storage;

    public FileUploadController(S3FileStorageService storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadResponse upload(@RequestPart("file") MultipartFile file) {
        try {
            // tenantId thực tế phải lấy từ security principal đã xác thực.
            String key = storage.upload("tenant-42", file);
            return new UploadResponse(key);
        } catch (IOException | IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid upload", ex);
        }
    }

    public record UploadResponse(String objectKey) {
    }
}
~~~

`tenant-42` chỉ là placeholder. Ứng dụng multi-tenant phải lấy tenant/user từ authentication context, kiểm tra quyền trước khi tạo key và không nhận `tenantId` tùy ý từ request body.

## 7. Download object và stream về HTTP response

Với file vừa/nhỏ, có thể lấy object bằng `GetObject`. Với file lớn, tránh `ResponseBytes.asByteArray()` hoặc đọc toàn bộ vào `byte[]`. Dùng `ResponseInputStream` và stream tới HTTP response.

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

@RestController
public class FileDownloadController {
    private final S3Client s3;
    private final FileRepository files;
    private final String bucket;

    public FileDownloadController(
            S3Client s3, FileRepository files,
            @Value("${app.s3.bucket}") String bucket) {
        this.s3 = s3;
        this.files = files;
        this.bucket = bucket;
    }

    @GetMapping("/api/files/{fileId}/content")
    public ResponseEntity<StreamingResponseBody> download(
            @PathVariable String fileId,
            Authentication authentication) {

        // Repository method must verify tenant/owner permissions.
        FileRecord file = files.findAuthorized(fileId, authentication);

        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(file.objectKey())
                .build();

        StreamingResponseBody body = output -> {
            try (ResponseInputStream<GetObjectResponse> input =
                         s3.getObject(request)) {
                input.transferTo(output);
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(file.contentType()))
                .contentLength(file.size())
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(file.safeDownloadName(),
                                        StandardCharsets.UTF_8)
                                .build().toString())
                .body(body);
    }
}
~~~

Đây là skeleton controller: `FileRepository`, `FileRecord` và authorization là application-specific. Không nhận `objectKey` từ client; client gửi `fileId` để backend tra record đã kiểm tra quyền. Với response lớn, cấu hình async executor/timeout của Spring MVC và reverse proxy phù hợp.

### 7.1. Download bằng presigned GET

Nếu không cần proxy nội dung qua Spring, backend có thể cấp presigned GET URL sau khi xác thực quyền sở hữu. Browser tải trực tiếp từ S3; ứng dụng giảm bandwidth và threads. URL là bearer token tạm thời, không được ghi vào logs, analytics hoặc gửi cho người không có quyền.

### 7.2. Range requests và resume

S3 hỗ trợ đọc một byte range của object. Với media player hoặc file download lớn, có thể truyền Range header tới S3 hoặc dùng presigned GET có request header tương ứng. Nếu backend proxy, cần chuyển tiếp đúng HTTP status `206`, `Content-Range` và `Accept-Ranges`; không tự tuyên bố hỗ trợ resume nếu controller luôn tải toàn bộ object.

### 7.3. Content-Disposition và nội dung không tin cậy

- Dùng filename đã sanitize cho `Content-Disposition`.
- File user upload nên tải dưới dạng attachment nếu không có lý do hiển thị inline.
- Không ghép raw filename vào HTTP header.
- Có thể phục vụ file từ một domain riêng để giảm rủi ro same-origin khi hỗ trợ nội dung do người dùng tạo.
- Quyết định MIME dựa trên validation, không chỉ dựa vào extension hoặc client header.

## 8. Database metadata và tính nhất quán giữa S3/DB

S3 và RDS/DynamoDB không tham gia cùng một ACID transaction. Vì vậy không thể giả định upload object và ghi metadata trong DB commit hoặc rollback cùng lúc.

Một bảng metadata có thể gồm:

~~~sql
CREATE TABLE stored_files (
    file_id          VARCHAR(36) PRIMARY KEY,
    tenant_id        VARCHAR(100) NOT NULL,
    object_key       VARCHAR(1024) NOT NULL UNIQUE,
    original_name    VARCHAR(255) NOT NULL,
    content_type     VARCHAR(150) NOT NULL,
    content_length   BIGINT NOT NULL,
    checksum_sha256  VARCHAR(128),
    status           VARCHAR(30) NOT NULL,
    s3_version_id    VARCHAR(1024),
    created_at       TIMESTAMP NOT NULL,
    uploaded_at      TIMESTAMP,
    scanned_at       TIMESTAMP
);

CREATE INDEX ix_stored_files_tenant_created
    ON stored_files (tenant_id, created_at);
~~~

Đây là schema minh họa; giới hạn độ dài, timestamp timezone, encryption, retention và indexes phải dựa trên business/query patterns.

### 8.1. Workflow upload backend proxy

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Spring Boot
    participant DB as File metadata DB
    participant S3 as Private S3
    participant SCAN as Malware scanner
    U->>API: POST multipart
    API->>API: Authenticate + validate + quota
    API->>DB: Create PENDING_UPLOAD record
    API->>S3: PutObject / multipart
    S3-->>API: ETag / VersionId / success
    API->>DB: Set UPLOADED_PENDING_SCAN
    API-->>U: fileId + status
    S3-->>SCAN: Object-created event
    SCAN->>S3: Read / scan object
    SCAN->>DB: Set AVAILABLE or REJECTED
~~~

### 8.2. Vì sao cần trạng thái?

Các trường hợp lỗi:

- DB ghi PENDING thành công nhưng upload S3 thất bại.
- S3 upload thành công nhưng DB update timeout.
- Upload thành công nhưng event scan bị trễ hoặc consumer retry.
- User retry request và tạo object thứ hai.
- Client bị ngắt kết nối sau khi S3 nhận đủ bytes nhưng trước khi backend trả response.

Dùng state machine như:

~~~text
PENDING_UPLOAD
UPLOADED_PENDING_SCAN
SCANNING
AVAILABLE
REJECTED
FAILED
DELETE_PENDING
DELETED
RECONCILIATION_REQUIRED
~~~

Đặt `AVAILABLE` chỉ sau khi object tồn tại, metadata được kiểm tra và các bước bảo mật bắt buộc đã hoàn tất. Không trả presigned GET cho file ở trạng thái `PENDING_UPLOAD`, `SCANNING` hoặc `REJECTED`.

### 8.3. Idempotency và reconciliation

- API upload nhận idempotency key/request ID; cùng một business request phải ánh xạ tới cùng `fileId`/object key.
- Tạo key duy nhất từ server, không sinh key mới mỗi lần retry mù quáng.
- Nếu S3 thành công nhưng DB chưa cập nhật, job reconcile dùng `HeadObject` theo key đã lưu để xác định object có tồn tại hay không.
- Nếu DB record pending quá hạn mà object không tồn tại, đánh dấu FAILED hoặc cho phép retry theo policy.
- Nếu object mồ côi không có DB record, quy trình cleanup phải xác định ownership/retention trước khi xóa.
- Dùng outbox/inbox khi phát event nghiệp vụ; S3 notification không phải transaction chung với DB.

**Không xóa object ngay khi một API call timeout.** Timeout chỉ cho biết client không nhận được response; nó không chứng minh S3 chưa hoàn tất PutObject.

## 9. Direct upload bằng presigned PUT URL

Presigned URL cho phép browser upload/download object private trong thời gian giới hạn mà browser không cần AWS credentials. Backend ký URL bằng IAM principal có quyền thực hiện operation. Người cầm URL có thể thực hiện request đã ký cho đến khi URL hết hạn hoặc credentials signer mất hiệu lực.

### 9.1. Workflow cấp upload URL

1. Client gọi API tạo upload session với filename, expected size, content type và business reference.
2. Backend xác thực user, quota, loại file và giới hạn kích thước.
3. Backend sinh `fileId` và object key duy nhất; lưu record `PENDING_UPLOAD`.
4. Backend tạo presigned PUT URL với thời hạn ngắn và các headers cần ký.
5. Browser PUT bytes trực tiếp tới S3.
6. Browser gọi finalize API; backend dùng `HeadObject` kiểm tra key, size, metadata/checksum mong đợi.
7. Backend chuyển record sang `UPLOADED_PENDING_SCAN`; event/worker scan rồi chuyển `AVAILABLE`.

### 9.2. Tạo presigned PUT URL bằng SDK v2

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest;

@Component
public class S3UploadUrlService {
    private final S3Presigner presigner;
    private final String bucket;

    public S3UploadUrlService(
            S3Presigner presigner,
            @Value("${app.s3.bucket}") String bucket) {
        this.presigner = presigner;
        this.bucket = bucket;
    }

    public String createPutUrl(String objectKey, String contentType) {
        PutObjectRequest putObject = PutObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .contentType(contentType)
                .build();

        PutObjectPresignRequest presignRequest =
                PutObjectPresignRequest.builder()
                        .signatureDuration(Duration.ofMinutes(10))
                        .putObjectRequest(putObject)
                        .build();

        PresignedPutObjectRequest signed =
                presigner.presignPutObject(presignRequest);

        return signed.url().toExternalForm();
    }
}
~~~

Tạo `S3Presigner` thành bean dùng chung, cấu hình cùng Region và credentials chain với ứng dụng; đóng khi shutdown. Trong production, `objectKey` phải được backend sinh và xác thực quyền trước khi gọi method. Nếu request ký gồm Content-Type hoặc checksum header, client PUT phải gửi đúng các headers đã ký.

### 9.3. S3Presigner bean

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration
public class S3PresignerConfiguration {
    @Bean(destroyMethod = "close")
    S3Presigner s3Presigner(
            @Value("${app.aws.region}") String region) {
        return S3Presigner.builder()
                .region(Region.of(region))
                .build();
    }
}
~~~

### 9.4. Browser upload

~~~javascript
const response = await fetch(presignedUrl, {
  method: "PUT",
  headers: {
    "Content-Type": file.type
  },
  body: file
});

if (!response.ok) {
  throw new Error("S3 upload failed: " + response.status);
}
~~~

Nếu Content-Type đã được ký, header thực tế phải khớp giá trị lúc tạo URL. Browser cần S3 CORS cho origin/method/headers tương ứng. CORS chỉ là browser cross-origin policy; **CORS không thay IAM authorization** và không biến bucket thành public.

### 9.5. Giới hạn và bảo vệ presigned URL

- Presigned URL là **bearer token**: ai có URL có thể dùng quyền đã ký trong thời hạn hợp lệ.
- URL có thể được dùng nhiều lần trước khi hết hạn; PUT cùng key có thể overwrite object.
- Thời gian hiệu lực tối đa phụ thuộc loại credentials/signing; với SDK/CLI SigV4 có thể đặt đến 7 ngày, nhưng temporary role credentials thường hết hạn sớm hơn. Nên dùng thời hạn ngắn (ví dụ 5–15 phút) theo workflow.
- Không log URL đầy đủ, không đưa vào analytics/referrer, không lưu trong ticket hoặc chat.
- Giới hạn object key, method, signed headers và IAM permissions của signer.
- Với yêu cầu giới hạn file size ở policy, xem presigned POST policy với `content-length-range`; presigned PUT đơn giản không tự cung cấp mọi điều kiện của POST policy.
- Sau upload, verify size/checksum/content metadata và scan trước khi đánh dấu AVAILABLE.

### 9.6. Presigned GET URL

Dùng `GetObjectPresignRequest` với `GetObjectRequest` và thời hạn phù hợp. Trước khi cấp URL, backend phải tra `fileId`, kiểm tra tenant/owner/business permissions và trạng thái file. Không cho client tự gửi object key rồi backend ký URL mà không authorize.

## 10. Bảo mật bucket và object

Bucket lưu file riêng tư nên mặc định **private**. Quyền truy cập cần được quản lý bằng IAM policies, bucket policy, VPC endpoint policy và AWS Organizations guardrails. Tránh dựa vào ACL cho các use cases mới.

### 10.1. Block Public Access và Object Ownership

Với bucket general purpose mới, S3 mặc định bật **Block Public Access** và **Bucket owner enforced Object Ownership**:

- Bucket owner sở hữu objects trong bucket.
- ACL bị disable; quyền truy cập được quản lý qua policies.
- PUT requests không nên gửi ACL như `public-read`.
- Nếu request gửi ACL không tương thích với Bucket owner enforced, S3 có thể trả `AccessControlListNotSupported`.
- Giữ bốn Block Public Access settings ở mức account/bucket theo security baseline; chỉ thay đổi khi có use case public đã được review.

### 10.2. IAM least privilege cho application role

Một role upload/download trong prefix ứng dụng có thể cần các actions sau (policy cần điều chỉnh theo feature thực tế):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UploadAndReadTenantFiles",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts"
      ],
      "Resource": "arn:aws:s3:::company-private-files-prod/tenants/*"
    },
    {
      "Sid": "ListOnlyTenantPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::company-private-files-prod",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["tenants/*"]
        }
      }
    }
  ]
}
~~~

Policy minh họa cho role có nhiều tenant; ứng dụng vẫn phải kiểm tra quyền tenant/file ở DB. Không cấp `s3:*` hoặc bucket-wide access nếu không cần. Nếu không có chức năng list, bỏ `s3:ListBucket`; nếu dùng Transfer Manager/multipart, kiểm tra permissions cho các multipart operations trong IAM reference.

### 10.3. Bucket policy bắt buộc HTTPS

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::company-private-files-prod",
        "arn:aws:s3:::company-private-files-prod/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
~~~

Deny insecure transport giúp từ chối request HTTP không mã hóa. Trong hệ thống thật, bucket policy có thể thêm điều kiện VPC endpoint, principal, encryption headers hoặc organization ID; cần review để không chặn các service integrations hợp lệ.

### 10.4. Encryption at rest

S3 tự động mã hóa object mới bằng **SSE-S3** theo default hiện hành. Có thể chọn:

| Chế độ | Khi phù hợp | Lưu ý |
|---|---|---|
| SSE-S3 | Hầu hết file thông thường | S3 quản lý keys |
| SSE-KMS | Cần key policy, audit và kiểm soát KMS | Cần quyền KMS và quản lý key lifecycle/cost |
| DSSE-KMS | Yêu cầu dual-layer encryption theo policy | Tăng chi phí/latency |
| SSE-C | Customer cung cấp key trong request | Vận hành key phức tạp; không chọn nếu không có requirement rõ |
| Client-side encryption | Cần dữ liệu mã hóa trước khi tới S3 | Ứng dụng tự quản lý encryption/decryption/key lifecycle |

Với SSE-KMS, application role có thể cần `kms:GenerateDataKey` khi upload và `kms:Decrypt` khi download (tùy API/encryption path); key policy cũng phải cho phép principal. Không đặt KMS key ID từ client request. Không lưu plaintext encryption keys trong object metadata hoặc logs.

### 10.5. Bucket CORS cho direct browser upload

Ví dụ CORS giới hạn một frontend origin cụ thể:

~~~xml
<CORSConfiguration>
    <CORSRule>
        <AllowedOrigin>https://app.example.com</AllowedOrigin>
        <AllowedMethod>PUT</AllowedMethod>
        <AllowedMethod>GET</AllowedMethod>
        <AllowedMethod>HEAD</AllowedMethod>
        <AllowedHeader>content-type</AllowedHeader>
        <AllowedHeader>x-amz-checksum-*</AllowedHeader>
        <ExposeHeader>ETag</ExposeHeader>
        <ExposeHeader>x-amz-checksum-sha256</ExposeHeader>
        <MaxAgeSeconds>300</MaxAgeSeconds>
    </CORSRule>
</CORSConfiguration>
~~~

Cấu hình CORS phải khớp method và headers mà presigned request ký. Chỉ cho phép origin cần thiết; không dùng wildcard origin như một giải pháp authorization. Client không thể dùng CORS để có quyền truy cập object nếu URL/IAM không cho phép.

## 11. Versioning, Object Lock và phục hồi

### 11.1. S3 Versioning

Khi bật Versioning:

- PUT object cùng key tạo version mới; version cũ được giữ lại.
- DELETE không chỉ định version ID thường tạo **delete marker**, làm object trông như đã xóa trong GET thông thường.
- Muốn xóa vĩnh viễn một version phải chỉ định version ID và có quyền phù hợp.
- Mỗi version được tính storage riêng; versioning tăng khả năng phục hồi nhưng có thể tăng chi phí.

Lưu `versionId` trong DB nếu workflow cần tham chiếu chính xác một bản file. Khi upload object mới, cập nhật metadata record sang version mới sau khi kiểm tra thành công.

### 11.2. S3 Object Lock

Object Lock cung cấp WORM retention theo version, có Governance/Compliance modes và Legal Hold. Chỉ bật khi có yêu cầu lưu trữ bất biến/audit/legal. Object Lock yêu cầu bucket versioning và có thể ngăn permanent delete cho version đang được bảo vệ. Đây không phải lựa chọn mặc định cho file upload thông thường.

### 11.3. Versioning không thay backup

Versioning giúp khôi phục overwrite/delete nhầm, nhưng không tự bảo vệ trước mọi tình huống như account compromise, lifecycle misconfiguration hoặc region-wide disaster. Đánh giá S3 Replication, AWS Backup for S3, cross-account copy, retention và restore tests theo RPO/RTO. Replication không phải backup độc lập nếu thao tác xóa/corruption được replicate theo cấu hình.

## 12. Lifecycle và storage classes để kiểm soát chi phí

S3 có nhiều storage classes cho access patterns khác nhau:

| Storage class | Access pattern | Đánh đổi |
|---|---|---|
| S3 Standard | Truy cập thường xuyên | Millisecond access, giá lưu trữ chuẩn |
| S3 Intelligent-Tiering | Pattern không dự đoán/biến động | Tự chuyển tier; có monitoring/automation fees |
| S3 Standard-IA | Ít truy cập nhưng cần truy xuất nhanh | Retrieval fee, minimum storage duration và minimum billable size |
| S3 One Zone-IA | Dữ liệu tái tạo được, chấp nhận một AZ | Lưu trong một AZ; không phù hợp bản duy nhất quan trọng |
| S3 Glacier Instant Retrieval | Archive nhưng cần millisecond retrieval | Retrieval fee/minimum duration |
| S3 Glacier Flexible Retrieval | Archive, chấp nhận restore time | Restore request và thời gian chờ |
| S3 Glacier Deep Archive | Lưu dài hạn, ít truy xuất | Restore lâu hơn, chi phí retrieval |

Không chọn Glacier cho ảnh profile được mở mỗi ngày. Storage class ảnh hưởng retrieval latency, fees, minimum duration, availability design và restore workflow.

### 12.1. Lifecycle rules

Một bucket có thể có lifecycle rules theo prefix/tag để:

- Transition object cũ sang storage class phù hợp.
- Expire file tạm sau retention period.
- Chuyển noncurrent versions sang tier rẻ hơn hoặc xóa sau thời gian cho phép.
- Abort incomplete multipart uploads.
- Dọn expired delete markers khi phù hợp.

### 12.2. Cẩn thận khi bật Versioning + Expiration

Trong versioned bucket, expiration của current version thường tạo delete marker; object data trở thành noncurrent version và vẫn chiếm storage. Muốn xóa version cũ, cần lifecycle action riêng `NoncurrentVersionExpiration`. Vì vậy chỉ đặt “expire current objects after 30 days” không đồng nghĩa tất cả bytes đã bị xóa vĩnh viễn.

### 12.3. Retention theo business record

Không để Lifecycle xóa object trước khi business record hết thời hạn cần giữ. Nếu có legal hold, audit hoặc invoice retention, policy cần được thống nhất giữa DB record, S3 object tags, versioning và lifecycle. Trước khi deploy rule expiration, test trên prefix sandbox và kiểm tra noncurrent versions/delete markers.


## 13. Multipart upload và S3 Transfer Manager cho file lớn

Với object lớn, S3 hỗ trợ **multipart upload**: chia object thành nhiều parts, upload song song hoặc retry từng part, rồi gọi CompleteMultipartUpload để ghép object. Nếu một part lỗi, chỉ cần upload lại part đó thay vì gửi lại toàn bộ file.

Theo giới hạn multipart hiện hành:

| Thông số | Giới hạn |
|---|---:|
| Maximum object size | 48.8 TiB |
| Số parts tối đa | 10.000 |
| Part number | 1–10.000 |
| Kích thước mỗi part | 5 MiB–5 GiB |
| Part cuối | Có thể nhỏ hơn 5 MiB |
| Parts trả về mỗi ListParts | 1.000 |
| Multipart uploads trả về mỗi ListMultipartUploads | 1.000 |

AWS khuyến nghị **cân nhắc multipart khi object khoảng 100 MB trở lên**. Đây là hướng dẫn hiệu năng, không phải điều kiện bắt buộc. Kích thước part và số upload đồng thời phải được tính để không vượt 10.000 parts hoặc làm ứng dụng cạn RAM/network.

### 13.1. Vòng đời multipart upload

~~~mermaid
flowchart TD
    A["CreateMultipartUpload"] --> B["UploadPart 1..N"]
    B --> C{"All parts uploaded?"}
    C -->|"Yes"| D["CompleteMultipartUpload"]
    D --> E["One S3 object visible"]
    C -->|"No / failure"| F["Retry failed parts"]
    F --> B
    F -->|"Cancel / unrecoverable"| G["AbortMultipartUpload"]
    G --> H["Delete uploaded parts"]
~~~

Các bước:

1. `CreateMultipartUpload` khởi tạo upload và trả `uploadId`.
2. `UploadPart` gửi từng phần với part number.
3. Client lưu `ETag`/checksum của từng part để complete.
4. `CompleteMultipartUpload` ghép parts và tạo object.
5. Nếu không tiếp tục, gọi `AbortMultipartUpload` để giải phóng các parts đã lưu.

S3 chỉ tạo object hoàn chỉnh sau khi Complete thành công. Các parts chưa complete vẫn được lưu và **có thể bị tính phí storage**. Luôn hoàn tất hoặc abort.

### 13.2. S3 Transfer Manager

**S3 Transfer Manager** là high-level utility trong AWS SDK for Java 2.x cho upload/download file và directory. Nó sử dụng multipart upload và byte-range fetches khi cấu hình client phù hợp, có transfer progress listener và hỗ trợ pause/resume theo API.

Thêm module:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3-transfer-manager</artifactId>
</dependency>
~~~

BOM SDK v2 quản lý version của module này. Có thể dùng Java-based `S3AsyncClient` với multipart enabled hoặc AWS CRT-based S3 client. Nếu dùng CRT, cần thêm dependency `software.amazon.awssdk.crt:aws-crt` với version CRT phù hợp; BOM SDK v2 không quản lý version artifact CRT này.

### 13.3. Upload file bằng Transfer Manager

~~~java
import java.nio.file.Path;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.transfer.s3.S3TransferManager;
import software.amazon.awssdk.transfer.s3.model.CompletedFileUpload;
import software.amazon.awssdk.transfer.s3.model.FileUpload;
import software.amazon.awssdk.transfer.s3.model.UploadFileRequest;

public final class LargeFileUploader {
    public static String upload(
            String bucket, String key, Path source, Region region) {

        try (S3AsyncClient s3 = S3AsyncClient.builder()
                     .region(region)
                     .multipartEnabled(true)
                     .build();
             S3TransferManager manager = S3TransferManager.builder()
                     .s3Client(s3)
                     .build()) {

            UploadFileRequest request = UploadFileRequest.builder()
                    .putObjectRequest(b -> b
                            .bucket(bucket)
                            .key(key))
                    .source(source)
                    .build();

            FileUpload upload = manager.uploadFile(request);
            CompletedFileUpload result =
                    upload.completionFuture().join();

            return result.response().eTag();
        }
    }
}
~~~

Ví dụ nhận file từ filesystem path; với Spring multipart upload có thể dùng temporary file đã được kiểm soát để đưa vào Transfer Manager, nhưng cần giới hạn disk quota và xóa file tạm sau khi transfer hoàn tất. Với file lớn, direct browser-to-S3 thường giảm việc ghi file vào disk của Spring API server.

### 13.4. Chọn part size và concurrency

- Part size lớn giảm số request/parts nhưng tăng buffer/memory mỗi upload.
- Concurrency cao tăng throughput nếu network/CPU/S3 capacity cho phép, nhưng tăng số buffers và connection pressure.
- Ước tính bộ nhớ transfer tối đa từ `partSize × concurrentParts × concurrentUploads`, cộng overhead.
- Không tăng concurrency chỉ để đạt throughput trong benchmark đơn lẻ; quan sát P95/P99, throttles, heap, direct memory, file descriptors và network.
- Đặt timeout và retry hợp lý; không giữ upload vô hạn khi client đã disconnect.

### 13.5. Abort incomplete uploads bằng Lifecycle

Cấu hình S3 Lifecycle rule với `AbortIncompleteMultipartUpload` để dọn multipart uploads không complete sau một số ngày (ví dụ 7 ngày). Rule giúp tránh lưu parts bỏ quên và phát sinh chi phí. Vẫn nên abort chủ động trong exception/cancellation path; lifecycle là lớp cleanup bổ sung.

### 13.6. Download lớn và byte-range fetch

Transfer Manager có thể download file hoặc directory, chia range để tải song song. Đảm bảo disk đủ chỗ, giới hạn concurrent transfers và xác minh checksum/version trước khi đưa file vào quy trình nghiệp vụ. Không tải toàn bộ object vào `byte[]` chỉ để ghi ra filesystem.

## 14. Data integrity: checksum và ETag

S3 hỗ trợ checksum để xác minh dữ liệu trong upload/download. AWS SDK có thể tự tính checksum theo cấu hình/version; application cũng có thể chỉ định thuật toán và giá trị checksum đã tính trước.

### 14.1. Checksum algorithms

S3 hỗ trợ các thuật toán như CRC-64/NVME, CRC32, CRC32C, SHA-1, SHA-256, MD5 và một số XXHash/SHA-512 algorithms theo API hiện hành. Với ứng dụng lưu file quan trọng:

- Chọn checksum algorithm phù hợp yêu cầu compliance/performance.
- Gửi checksum cùng upload hoặc để SDK tự tính theo default hiện hành.
- Lưu checksum đã xác thực vào metadata DB để đối chiếu nghiệp vụ.
- Khi download, có thể yêu cầu checksum để kiểm tra integrity theo API/SDK support.
- Với multipart checksum dạng composite/part-level, part numbers phải liên tiếp bắt đầu từ 1.

### 14.2. ETag không phải luôn là MD5

ETag thường hữu ích làm entity tag/identifier, nhưng **không thể mặc định là MD5 của toàn bộ object**. Với multipart upload, ETag được hình thành từ checksum của các parts và có suffix số parts; với một số encryption modes và upload patterns, ETag cũng không phải MD5 đơn giản.

Không dùng `ETag` làm checksum nghiệp vụ duy nhất nếu chưa hiểu upload/encryption mode. Dùng explicit checksum algorithm và lưu giá trị rõ ràng.

### 14.3. Verify sau upload

Với presigned upload, backend có thể dùng `HeadObject` để kiểm tra Content-Length, metadata, VersionId và checksum fields mà request trả về. HEAD chỉ xác nhận object metadata tồn tại; nó **không thay malware scan** và không chứng minh nội dung thực sự là MIME type client khai báo. Cần validate bytes trong scan pipeline khi yêu cầu an toàn.

## 15. S3 Event Notifications và xử lý hậu upload

Sau khi object được tạo, ứng dụng có thể phát event để tạo thumbnail, OCR, quét malware, trích xuất metadata, lập chỉ mục hoặc gửi thông báo. S3 hỗ trợ gửi notifications tới SQS, SNS, Lambda và Amazon EventBridge theo cấu hình bucket.

~~~mermaid
flowchart LR
    APP["Spring Boot / Browser"] --> S3["S3 PutObject"]
    S3 --> EVT["S3 ObjectCreated event"]
    EVT --> EB["EventBridge / SQS"]
    EB --> SCAN["Malware scan"]
    EB --> THUMB["Thumbnail / OCR"]
    EB --> META["Metadata extraction"]
    SCAN --> DB["Update file status"]
    THUMB --> DB
    META --> DB
~~~

### 15.1. Event delivery không phải exactly-once

Amazon S3 Event Notifications được thiết kế theo kiểu **at-least-once**. Notification thường đến nhanh nhưng có thể trễ, trùng lặp hoặc đến không theo thứ tự phát sinh. Consumer phải idempotent.

Một consumer nên:

1. Parse bucket, object key, event type, version ID và event metadata.
2. URL-decode object key theo format notification.
3. Dùng event ID hoặc business file ID làm deduplication key.
4. Kiểm tra `sequencer` khi cần so thứ tự events **cùng một object key**; không so sequencer giữa các keys khác nhau.
5. Ghi trạng thái processed/inbox cùng business update.
6. Retry lỗi transient, đưa poison messages vào DLQ và hỗ trợ replay có kiểm soát.

### 15.2. Tránh event loop

Nếu Lambda được trigger bởi `ObjectCreated` rồi ghi thumbnail vào cùng bucket/prefix cũng match notification, Lambda có thể tự kích hoạt lặp vô hạn. Dùng bucket riêng hoặc prefix filter rõ ràng như:

~~~text
uploads/       → trigger scanner
derived/       → không trigger scanner
thumbnails/    → chỉ trigger workflow khác nếu cần
~~~

EventBridge giúp định tuyến và lọc events; SQS giúp buffering/backpressure và DLQ. Chọn theo retry, fan-out, ordering và operational requirements.

### 15.3. S3 event không thay transaction với database

Nếu Spring Boot ghi DB status `UPLOADED` rồi mới PutObject, event có thể đến trước khi DB update hoàn tất. Nếu upload thành công nhưng API crash, event vẫn có thể đến dù browser không nhận response. Consumer nên tra file record theo key/fileId và xử lý các trạng thái chuyển tiếp, không giả định thứ tự API response và notification.

## 16. Observability và audit

| Nguồn | Dữ liệu cần theo dõi | Mục tiêu |
|---|---|---|
| Application metrics | Upload success/failure, file size, duration, queue time | SLO trải nghiệm |
| AWS SDK | Request ID, retry count, service error, latency | Chẩn đoán API calls |
| S3 CloudWatch | Storage bytes, request metrics, 4xx/5xx, latency khi bật metrics phù hợp | Sức khỏe bucket |
| S3 Storage Lens | Storage usage, object count, activity, cost optimization | Xu hướng toàn tổ chức |
| CloudTrail data events | Object-level API access theo cấu hình | Audit ai đọc/ghi/xóa object |
| S3 server access logs | Request-level records theo cấu hình | Phân tích truy cập |
| SQS/Lambda | Queue age, DLQ depth, Lambda errors/throttles | Hậu xử lý upload |
| Database | Pending uploads, orphan records, scan backlog | Consistency nghiệp vụ |

### 16.1. CloudTrail data events

CloudTrail management events và **S3 data events** có phạm vi/chi phí khác nhau. Muốn audit các thao tác như GetObject/PutObject, cấu hình data event selectors cho bucket/prefix liên quan và kiểm soát retention của CloudTrail destination. Không giả định mọi object-level access đã được ghi nếu chưa bật data events.

### 16.2. Không log dữ liệu nhạy cảm

Không log presigned URLs, authorization headers, AWS credentials, raw file bytes, metadata nhạy cảm hoặc object content. Log correlation ID, fileId, tenant ID đã được phép, bucket/prefix (nếu policy cho phép), operation, AWS request ID, status, duration và error code.

### 16.3. Alert hữu ích

- Upload failures hoặc 5xx tăng bất thường.
- `PENDING_UPLOAD` tồn tại quá SLA.
- `UPLOADED_PENDING_SCAN` backlog tăng.
- SQS oldest message age/DLQ vượt ngưỡng.
- S3 storage growth hoặc noncurrent version count bất thường.
- Incomplete multipart uploads tăng.
- Unexpected public access/config changes hoặc access-denied spikes.

## 17. Tối ưu chi phí và hiệu năng

Chi phí S3 không chỉ là giá lưu trữ mỗi GB. Cần nhìn theo **storage + requests + retrieval + data transfer + replication + KMS + incomplete multipart + versioning**.

### 17.1. Các cost drivers

| Thành phần | Tác động chi phí |
|---|---|
| Storage class và số GB-month | Bytes của mọi current/noncurrent versions |
| PUT/GET/LIST/HEAD requests | Số request theo API/operation |
| Multipart | Create/UploadPart/Complete requests và parts còn dang dở |
| Retrieval | Phí lấy dữ liệu từ IA/Glacier tiers theo class |
| Data transfer | Egress, inter-Region transfer, CDN/origin traffic |
| Replication | Storage và transfer ở destination, replication requests |
| SSE-KMS | KMS request volume và key costs |
| Versioning | Mỗi version lưu toàn bộ object bytes |
| Object Lock | Retention giữ data lâu hơn |
| Inventory/Storage Lens/logging | Report, monitoring và destination storage |

### 17.2. Giảm chi phí có kiểm soát

- Dùng presigned direct upload để giảm backend bandwidth/compute; vẫn cần tính S3 request và data transfer.
- Chọn storage class dựa trên access frequency và retrieval SLA.
- Dùng Lifecycle cho temporary files, noncurrent versions và incomplete multipart uploads.
- Đặt file size limits, quota và upload rate limits theo tenant.
- Không LIST toàn bucket cho mỗi trang giao diện; dùng DB index hoặc prefix Query patterns.
- Dùng CloudFront khi cần phân phối nội dung nhiều nơi; đánh giá cache policy và signed cookies/URLs.
- Dùng checksum và multipart phù hợp để tránh upload lại toàn bộ file sau lỗi mạng.
- Xóa orphan objects bằng reconciliation có ownership/retention guardrails, không xóa theo age mù quáng.

### 17.3. Tối ưu latency

- Đặt bucket và application ở Region phù hợp; tránh cross-Region transfer không cần thiết.
- Tái sử dụng S3 clients/HTTP connections.
- Dùng multipart/Transfer Manager cho file lớn và concurrency có giới hạn.
- Với download public/cacheable, đánh giá CloudFront; với private content, dùng origin access control và signed access theo thiết kế.
- Đo P50/P95/P99, retry, connection pool saturation và bytes transferred.
- Không chuyển file qua database hoặc base64 trong JSON nếu có thể dùng stream/object transfer trực tiếp.

## 18. Troubleshooting S3 trong Java/Spring Boot

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `NoSuchBucket` | Sai bucket name/Region/account | Bucket ARN, Region, environment config |
| `NoSuchKey` | Key khác chính tả/case/prefix hoặc version mismatch | DB object key, URL decode, VersionId |
| `AccessDenied` | IAM/bucket/KMS/VPC endpoint policy deny | Caller identity, role, bucket/key policy, KMS key policy |
| `SignatureDoesNotMatch` | Region, signed headers, URL bị encode/modify hoặc clock drift | Region, method, Content-Type, checksum header, NTP/proxy |
| Presigned URL trả 403 | URL hết hạn, credentials signer hết hạn, policy deny hoặc headers không khớp | Expiration, role session, exact HTTP method/headers |
| Browser CORS error | CORS rule thiếu origin/method/header/expose header | Bucket CORS và preflight response |
| Upload timeout | Request quá lớn, proxy timeout, network, pool/concurrency | Upload path, SDK timeout, multipart, client disconnect |
| Spring `MaxUploadSizeExceededException` | Multipart limits thấp hơn file/request | `max-file-size`, `max-request-size`, ingress limits |
| Heap OOM khi upload | `getBytes()`/buffer toàn file hoặc concurrency quá cao | Stream, temp disk, concurrency, heap profile |
| S3 object có nhưng DB pending | API timeout sau S3 success hoặc DB failure | Reconciliation bằng HeadObject/VersionId |
| DB record có nhưng object thiếu | S3 upload failed hoặc object bị xóa | State transition, S3 events, delete audit |
| Multipart parts còn tính phí | Upload chưa complete/abort | ListMultipartUploads, Abort, Lifecycle rule |
| ETag khác MD5 mong đợi | Multipart/encryption/checksum behavior | Dùng explicit checksum thay ETag |
| File scan không chạy | Event destination permission/config hoặc DLQ | S3 notification, EventBridge/SQS policy, queue age |
| Object public ngoài ý muốn | Public access settings/policy/ACL | Block Public Access, Object Ownership, bucket policy |
| Download file bị sai tên/MIME | Metadata/DB record không đúng hoặc header unsafe | Safe filename, Content-Type validation |
| Versioning làm storage tăng | Noncurrent versions và delete markers tích lũy | Lifecycle noncurrent expiration, Storage Lens |
| File archived không mở ngay | Glacier class cần restore | Storage class, restore status và SLA |

### 18.1. Chẩn đoán theo tầng

1. Xác minh caller identity, account, Region, bucket và object key.
2. Đọc service error code/request ID; phân biệt service error với client/network exception.
3. Kiểm tra IAM role, bucket policy, KMS key policy, Block Public Access và endpoint policy.
4. Kiểm tra signed method/headers/URL expiry nếu dùng presigned URL.
5. Kiểm tra multipart upload ID, completed parts và incomplete-upload Lifecycle.
6. Kiểm tra DB status/version, event queue/DLQ và audit trail.
7. Đối chiếu checksum/VersionId và thực hiện reconciliation trước khi retry/delete.

Đừng cấp `s3:*` hoặc mở bucket public để xử lý nhanh một lỗi AccessDenied. Xác định đúng action/resource/condition đang deny và sửa policy tối thiểu cần thiết.

## 19. AWS CLI chỉ đọc để kiểm tra bucket/object

Các lệnh sau dùng profile `dev` và Region ví dụ. Đây là thao tác đọc metadata/configuration; một số lệnh vẫn tạo request charges. Chỉ truy cập bucket được phép.

### 19.1. Xác minh identity và bucket

~~~bash
aws sts get-caller-identity --profile dev

aws s3api head-bucket \
  --bucket company-private-files-prod \
  --profile dev \
  --region ap-southeast-1

aws s3api get-bucket-location \
  --bucket company-private-files-prod \
  --profile dev
~~~

### 19.2. Đọc security configuration

~~~bash
aws s3api get-public-access-block \
  --bucket company-private-files-prod \
  --profile dev

aws s3api get-bucket-ownership-controls \
  --bucket company-private-files-prod \
  --profile dev

aws s3api get-bucket-encryption \
  --bucket company-private-files-prod \
  --profile dev

aws s3api get-bucket-versioning \
  --bucket company-private-files-prod \
  --profile dev

aws s3api get-bucket-lifecycle-configuration \
  --bucket company-private-files-prod \
  --profile dev
~~~

Nếu configuration chưa được thiết lập, một số API có thể trả lỗi như `NoSuchPublicAccessBlockConfiguration`/`ServerSideEncryptionConfigurationNotFoundError`/`NoSuchLifecycleConfiguration`; phân biệt trạng thái “chưa cấu hình” với lỗi permission/network.

### 19.3. Head object và list prefix có giới hạn

~~~bash
aws s3api head-object \
  --bucket company-private-files-prod \
  --key tenants/tenant-42/uploads/example-file-id \
  --profile dev \
  --region ap-southeast-1

aws s3api list-objects-v2 \
  --bucket company-private-files-prod \
  --prefix tenants/tenant-42/uploads/ \
  --max-keys 20 \
  --profile dev \
  --region ap-southeast-1
~~~

`HeadObject` đọc metadata, không tải bytes. `ListObjectsV2` có thể trả object keys và metadata; giới hạn prefix/MaxKeys, không list toàn bucket chỉ để debug. Không in presigned URL hoặc PII trong shell history.

### 19.4. Đọc incomplete multipart uploads

~~~bash
aws s3api list-multipart-uploads \
  --bucket company-private-files-prod \
  --prefix tenants/tenant-42/ \
  --max-uploads 20 \
  --profile dev \
  --region ap-southeast-1
~~~

Lệnh này đọc danh sách multipart uploads còn dang dở. **Không** gọi `abort-multipart-upload` trong quy trình chỉ đọc; abort là thao tác thay đổi state và giải phóng parts.

## 20. Bài thực hành: thiết kế file storage cho ứng dụng Spring Boot

### 20.1. Lab A — Upload hóa đơn qua backend

Yêu cầu:

- Endpoint `POST /api/files` nhận một file PDF.
- Chỉ user đã xác thực, thuộc tenant hợp lệ mới được upload.
- Giới hạn kích thước 20 MB và validate PDF signature.
- Backend sinh `fileId`/object key; không dùng original filename làm key.
- Ghi record `PENDING_UPLOAD`, upload S3, rồi cập nhật `UPLOADED_PENDING_SCAN`.
- Worker scan file và chỉ chuyển `AVAILABLE` khi kiểm tra thành công.
- Endpoint download nhận `fileId`, xác thực quyền và stream object về client.

Hãy vẽ sequence diagram và giải thích cách xử lý nếu S3 upload thành công nhưng DB update thất bại.

### 20.2. Lab B — Direct upload ảnh/video

1. Tạo API tạo upload session, kiểm tra quota/size/type.
2. Lưu DB record pending với object key do backend sinh.
3. Tạo presigned PUT URL hết hạn sau 10 phút.
4. Browser PUT file trực tiếp vào S3 với headers khớp chữ ký.
5. Browser gọi finalize API.
6. Backend dùng HeadObject kiểm tra size/metadata/checksum và đưa vào scan queue.
7. Worker cập nhật trạng thái AVAILABLE hoặc REJECTED.

Giải thích vì sao presigned URL không phải user identity, vì sao URL cần bảo mật như bearer token và tại sao CORS không thay authorization.

### 20.3. Lab C — Multipart upload

Dùng sandbox file lớn:

- Upload file 200 MB bằng S3 Transfer Manager.
- Thử part size/concurrency khác nhau và đo throughput/P95.
- Ngắt một part trong môi trường test và quan sát retry.
- Hủy upload và xác minh AbortMultipartUpload giải phóng parts.
- Cấu hình Lifecycle abort incomplete uploads sau 7 ngày.
- Đọc ETag và checksum; giải thích vì sao ETag không luôn là MD5.

Không chạy test lớn trên bucket production hoặc file nhạy cảm.

### 20.4. Lab D — Bảo mật bucket

Dùng AWS Console/CLI chỉ đọc để kiểm tra:

- Block Public Access ở account và bucket.
- Object Ownership là Bucket owner enforced.
- Encryption default là SSE-S3 hoặc SSE-KMS theo policy.
- Bucket policy deny insecure transport.
- Application role chỉ có actions/resources cần thiết.
- CORS chỉ cho origin frontend được phép.
- Versioning/Lifecycle theo retention policy.
- CloudTrail data events đã được bật nếu yêu cầu audit object-level.

### 20.5. Lab E — Reconciliation và duplicate events

Mô phỏng:

1. Upload object thành công nhưng API timeout trước DB update.
2. S3 notification bị gửi lại hai lần.
3. Worker nhận event cũ sau event mới.
4. Scan worker crash sau khi ghi DB nhưng trước khi ACK SQS.

Thiết kế idempotency key, inbox, trạng thái file, sequencer/version checks và job reconciliation để không scan/đánh dấu/xóa sai object.

## 21. Checklist review trước khi merge

### API và data model

- [ ] Tenant/user lấy từ authentication context?
- [ ] Object key do server sinh và không chứa path do client kiểm soát?
- [ ] DB record lưu owner, object key, version/checksum, size, content type và state?
- [ ] Idempotency key bảo vệ request retry?
- [ ] Có reconciliation khi S3/DB outcome không rõ?
- [ ] Không cấp download URL cho file pending/rejected/quarantined?

### Upload/download

- [ ] Có giới hạn multipart request ở Spring và ingress?
- [ ] Tránh `getBytes()`/buffer toàn file trong heap?
- [ ] Stream được đóng và temp files được dọn?
- [ ] File type kiểm tra bằng bytes/signature, không chỉ extension?
- [ ] File lớn dùng multipart/Transfer Manager hoặc direct-to-S3?
- [ ] Presigned URL ngắn hạn, không log và headers khớp chữ ký?
- [ ] Download kiểm tra quyền qua fileId và stream/Range đúng nếu hỗ trợ?

### S3 security và operations

- [ ] Bucket private, Block Public Access bật?
- [ ] Object Ownership Bucket owner enforced, không ACL public?
- [ ] IAM least privilege theo bucket/prefix?
- [ ] HTTPS enforced và encryption at rest phù hợp?
- [ ] SSE-KMS key policy/KMS permissions đúng khi sử dụng?
- [ ] CORS giới hạn origin/method/header?
- [ ] Versioning/Lifecycle/Object Lock đúng retention?
- [ ] Incomplete multipart cleanup đã cấu hình?
- [ ] S3 events xử lý duplicate/out-of-order?
- [ ] CloudWatch/CloudTrail/DLQ/Storage Lens có giám sát cần thiết?
- [ ] Cost model gồm storage, requests, retrieval, transfer, versions, KMS và replication?

## 22. Câu hỏi tự đánh giá

1. Vì sao file upload thường nên lưu bytes trong S3 và metadata trong database?
2. Bucket, object, key và prefix khác nhau thế nào?
3. Vì sao object key không nên dùng trực tiếp original filename?
4. S3 có filesystem folder thật hay chỉ có key prefix?
5. Backend proxy và direct presigned upload khác nhau về bandwidth/validation ra sao?
6. `MultipartFile.getBytes()` gây rủi ro gì với file lớn?
7. Vì sao cần giới hạn `max-file-size` và `max-request-size`?
8. Vì sao Content-Type do browser gửi không đủ để xác nhận file type?
9. `RequestBody.fromInputStream` cần biết điều gì về content length?
10. Vì sao S3Client nên được tái sử dụng trong Spring singleton bean?
11. Presigned URL là bearer token nghĩa là gì?
12. URL presigned PUT có thể được dùng nhiều lần trước khi hết hạn không?
13. Nếu presigned PUT ghi cùng key lần hai, điều gì có thể xảy ra?
14. Vì sao temporary role credentials có thể làm URL hết hạn sớm hơn expiration đã đặt?
15. CORS có thay IAM authorization không?
16. Khi nào nên dùng multipart upload?
17. Part size tối thiểu (ngoại trừ part cuối) và số parts tối đa là bao nhiêu?
18. S3 Transfer Manager hỗ trợ những loại transfer nào?
19. Vì sao incomplete multipart parts vẫn có thể bị tính phí?
20. ETag có luôn là MD5 của toàn object không?
21. S3 checksum dùng để bảo vệ điều gì?
22. Vì sao S3 và RDS không có một transaction ACID chung?
23. Tại sao file cần trạng thái PENDING/SCANNING/AVAILABLE?
24. S3 Event Notifications có đảm bảo exactly-once và ordering không?
25. Làm sao xử lý event trùng và out-of-order?
26. Block Public Access và Bucket owner enforced giải quyết rủi ro nào?
27. Khi nào nên dùng SSE-KMS thay SSE-S3?
28. Versioning xử lý DELETE như thế nào?
29. Lifecycle expiration trên versioned bucket có xóa vĩnh viễn noncurrent version không?
30. Khi nào dùng S3 Standard, Intelligent-Tiering hoặc Glacier?
31. Những thành phần nào tạo chi phí ngoài storage GB-month?
32. CloudTrail data events khác management events ở điểm nào?
33. Vì sao không nên log presigned URL?
34. Khi S3 upload thành công nhưng DB update timeout, cần làm gì?
35. Vì sao retry upload cần idempotency key và reconciliation?

### Định hướng đáp án

- **Architecture:** S3 lưu bytes; DB lưu owner/key/status; Spring Boot điều phối authorization và metadata.
- **Upload:** MultipartFile size limits, streaming, MIME sniff, presigned URLs hoặc Transfer Manager tùy file size.
- **Security:** Private bucket, Block Public Access, Bucket owner enforced, IAM least privilege, TLS, SSE-S3/SSE-KMS, CORS hẹp.
- **Consistency:** S3 và DB không atomic; dùng states, idempotency, outbox/inbox và reconciliation.
- **Reliability:** Multipart retry/abort, checksum, event consumers idempotent, versioning/backup/lifecycle.
- **Cost:** Storage class, requests, retrieval, data transfer, KMS, replication, incomplete parts và object versions.

## 23. Tài liệu AWS và Spring chính thức

1. [Amazon S3 examples using AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_s3_code_examples.html) — PutObject/GetObject, presigned URLs, multipart, Transfer Manager.
2. [Work with Amazon S3 using SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3.html) — Upload streams, cross-Region, checksums, client performance and events.
3. [S3 pre-signed URLs with SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3-presign.html) — Generate GET/PUT URLs and use them.
4. [S3 Transfer Manager for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/transfer-manager.html) — Multipart transfer, progress, directory transfer and CRT.
5. [AWS CRT-based S3 client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/crt-based-s3-client.html) — Performance, multipart and stream behavior.
6. [S3 multipart upload overview](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html) — Upload lifecycle, parts and pricing.
7. [S3 multipart upload limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html) — Object/part limits.
8. [Abort incomplete multipart uploads with Lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html) — Cleanup and cost.
9. [Checking object integrity for uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html) — Checksum algorithms and ETag behavior.
10. [S3 presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html) — Permissions, expiry, credentials and URL reuse.
11. [Uploading objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html) — PUT upload semantics.
12. [S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html) — Public access, ACLs, encryption and audit.
13. [S3 Object Ownership](https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html) — Bucket owner enforced and disabled ACLs.
14. [S3 access management](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-management.html) — IAM, bucket policies and object access.
15. [S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html) — Versions, overwrite and delete markers.
16. [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) — WORM retention and legal holds.
17. [S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html) — Access patterns and minimum durations.
18. [S3 Lifecycle configuration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html) — Transition, expiration and noncurrent versions.
19. [S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html) — Destinations and at-least-once delivery.
20. [S3 event message structure](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html) — Key encoding and sequencer ordering.
21. [S3 CloudWatch metrics](https://docs.aws.amazon.com/AmazonS3/latest/userguide/cloudwatch-monitoring.html) — Request and storage metrics.
22. [S3 CloudTrail data events](https://docs.aws.amazon.com/AmazonS3/latest/userguide/cloudtrail-logging.html) — Object-level API audit.
23. [Spring Boot multipart properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — Servlet/WebFlux multipart limits.
24. [AWS SDK for Java 2.x credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — IAM role/profile credentials.
25. [AWS SDK for Java 2.x Maven setup](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/setup-project-maven.html) — BOM and service module dependencies.

> **Ghi nhớ cuối bài:** S3 là object storage; object key do server tạo và DB quản lý ownership/status. Với file nhỏ, Spring Boot có thể stream qua SDK; với file lớn, cân nhắc presigned direct upload và multipart/Transfer Manager. Bucket private, IAM least privilege, Block Public Access, encryption, checksum, lifecycle và idempotent event processing là những thành phần cần thiết để hệ thống lưu trữ tệp an toàn, phục hồi được và kiểm soát chi phí.
