# Xây dựng kho tài liệu với lưu trữ đối tượng và URL truy cập tạm thời

## 1. Bài toán và mục tiêu

Một ứng dụng quản lý tài liệu thường cần lưu hóa đơn, hợp đồng, ảnh, bản scan và báo cáo. Lưu toàn bộ bytes trong database làm database phình to, tăng chi phí backup và khiến luồng tải file phụ thuộc vào ứng dụng. Một thiết kế phổ biến là lưu metadata và trạng thái nghiệp vụ trong database, còn nội dung file nằm trong object storage.

Trong bài thực hành này, bạn xây một document repository bằng Spring Boot. Backend xác thực người dùng, kiểm tra quyền truy cập tài liệu, tạo object key và cấp URL có chữ ký để trình duyệt tải lên hoặc tải xuống trực tiếp:

- **Amazon S3:** presigned URL được tạo bằng `S3Presigner`.
- **Google Cloud Storage:** signed URL V4 được tạo bằng `Storage.signUrl`.
- **Azure Blob Storage:** user delegation SAS được tạo bằng Microsoft Entra identity và user delegation key.

URL chỉ cấp quyền cho một object, một HTTP method và một khoảng thời gian ngắn. Bucket/container vẫn private; client không cần nhận AWS access key, Google service account key, Azure account key hoặc credential của backend.

Bài học thuộc chương **Thực hành tổng hợp** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này kết hợp các kiến thức đó thành một luồng nghiệp vụ hoàn chỉnh: tạo tài liệu, upload, xác minh, cấp URL download và quản lý vòng đời.

Sau khi hoàn thành, bạn có thể:

- Thiết kế document repository tách metadata database khỏi object bytes.
- Tạo object key ngẫu nhiên, không dùng tên file người dùng làm key trực tiếp.
- Cấp presigned GET/PUT URL cho S3.
- Cấp signed GET/PUT URL V4 cho GCS.
- Cấp user delegation SAS chỉ đọc hoặc upload cho Azure Blob Storage.
- Cấu hình signer identity và quyền IAM/RBAC tối thiểu.
- Thiết kế upload session, finalize, download authorization và trạng thái tài liệu.
- Giới hạn thời gian URL, method, object và headers được ký.
- Cấu hình CORS, kiểm tra checksum/size và xử lý upload lỗi.
- Kiểm thử URL hết hạn, sai method, sai header và truy cập chéo tenant.

> **Phạm vi phiên bản:** Ví dụ dùng AWS SDK for Java 2.x, Google Cloud Storage Java client và Azure Storage Blob SDK for Java. Dùng BOM tương thích với Spring Boot của dự án. Version trong các ví dụ Maven là placeholder; không dùng chung một BOM cho cả ba provider. Các URL, bucket, container, project, account và object trong bài chỉ là dữ liệu minh họa.

## 2. Kiến trúc kho tài liệu

### 2.1. Tách metadata khỏi bytes

Database lưu thông tin cần cho tìm kiếm, authorization và trạng thái nghiệp vụ. Object storage lưu nội dung file.

~~~mermaid
flowchart LR
    USER["Browser / mobile client"] --> API["Spring Boot Document API"]
    API --> AUTH["Authentication + tenant authorization"]
    AUTH --> DB["Document metadata database"]
    API --> SIGN["Provider signer adapter"]
    SIGN --> S3["Amazon S3"]
    SIGN --> GCS["Google Cloud Storage"]
    SIGN --> AZ["Azure Blob Storage"]
    USER -->|"PUT / GET with temporary URL"| S3
    USER -->|"PUT / GET with temporary URL"| GCS
    USER -->|"PUT / GET with SAS URL"| AZ
    API --> VERIFY["Verify object metadata"]
    VERIFY --> DB
~~~

Backend không chuyển toàn bộ file qua API trong luồng upload/download thông thường. Backend chỉ cấp quyền truy cập tạm thời; trình duyệt gửi bytes trực tiếp tới storage. Điều này giảm tải CPU, memory, network bandwidth và connection time của Spring Boot.

### 2.2. Luồng upload

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Spring Boot
    participant DB as Database
    participant ST as Object Storage

    U->>API: POST /api/documents
    API->>API: Authenticate + authorize tenant
    API->>API: Validate filename, type, declared size
    API->>DB: Save PENDING_UPLOAD + opaque object key
    API->>ST: Sign PUT for exact object and short TTL
    ST-->>API: Temporary upload URL
    API-->>U: documentId + URL + required headers
    U->>ST: PUT bytes with signed URL
    ST-->>U: Upload success
    U->>API: POST /api/documents/{id}/complete
    API->>ST: HEAD object / read properties
    ST-->>API: Size, checksum, ETag/generation
    API->>DB: Mark AVAILABLE
    API-->>U: Document ready
~~~

### 2.3. Luồng download

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Spring Boot
    participant DB as Database
    participant ST as Object Storage

    U->>API: POST /api/documents/{id}/download-url
    API->>DB: Load document + tenant ownership
    API->>API: Check AVAILABLE and user permission
    API->>ST: Sign GET for exact object
    ST-->>API: Temporary download URL
    API-->>U: URL + expiry
    U->>ST: GET object with URL
    ST-->>U: Object bytes
~~~

Việc cấp URL là một hành động có authorization. Không cấp URL chỉ vì client biết document ID hoặc object key. Backend phải xác thực user, tenant, trạng thái document và quyền đọc trước khi ký.

## 3. Mô hình dữ liệu và object key

### 3.1. Document metadata

Một bảng document có thể gồm:

~~~sql
CREATE TABLE documents (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(100) NOT NULL,
    provider            VARCHAR(32) NOT NULL,
    bucket_name         VARCHAR(255) NOT NULL,
    object_key          VARCHAR(1024) NOT NULL,
    original_filename   VARCHAR(512) NOT NULL,
    content_type        VARCHAR(255) NOT NULL,
    expected_size       BIGINT NOT NULL,
    actual_size         BIGINT,
    checksum_sha256     VARCHAR(128),
    version_token       VARCHAR(256),
    state               VARCHAR(32) NOT NULL,
    upload_expires_at   TIMESTAMP WITH TIME ZONE,
    verified_at         TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    deleted_at          TIMESTAMP WITH TIME ZONE
);
~~~

`state` có thể gồm:

| State | Ý nghĩa |
| --- | --- |
| `PENDING_UPLOAD` | Đã tạo document record và cấp upload session |
| `VERIFYING` | Đang kiểm tra object sau upload |
| `AVAILABLE` | Object đã được xác minh và có thể tải |
| `REJECTED` | Object không đạt policy về size, type hoặc checksum |
| `UPLOAD_EXPIRED` | Upload session hết hạn mà không hoàn tất |
| `DELETE_PENDING` | Đang xử lý xóa object |
| `DELETED` | Tài liệu đã bị xóa theo nghiệp vụ |

Database không lưu signed URL hoặc SAS token. Lưu `upload_expires_at`, `verified_at` và version token nếu cần kiểm soát vòng đời; URL được tạo lại khi người dùng có quyền yêu cầu.

### 3.2. Object key do server sinh

Không dùng filename do người dùng gửi làm object key trực tiếp. Filename có thể chứa dấu `/`, ký tự điều khiển, Unicode bất thường, `..` hoặc trùng tên với tài liệu khác.

Ví dụ key do backend tạo:

~~~text
tenant/tenant-opaque-42/documents/4c9d8b21-2c71-4e10-8d34-1d7e2a2c4f11
~~~

Lưu `original_filename` riêng để hiển thị. Dùng UUID hoặc identifier ngẫu nhiên đủ mạnh cho object key; tenant segment lấy từ identity đã xác thực và được chuẩn hóa ở backend.

Object key không phải cơ chế authorization. Backend vẫn phải kiểm tra tenant ownership trong database trước khi cấp URL. Không cho client gửi bucket/container hoặc provider tùy ý.

### 3.3. Domain contract dùng chung

~~~java
import java.net.URI;
import java.time.Instant;
import java.util.Map;

public record UploadGrant(
        URI url,
        String method,
        Map<String, String> requiredHeaders,
        Instant expiresAt) {
}

public record DownloadGrant(
        URI url,
        String method,
        Instant expiresAt) {
}

public record StoredObjectMetadata(
        long sizeBytes,
        String contentType,
        String versionToken,
        String checksum) {
}

public interface DocumentObjectStorage {

    UploadGrant createUploadGrant(
            String bucket,
            String objectKey,
            String contentType,
            java.time.Duration ttl);

    DownloadGrant createDownloadGrant(
            String bucket,
            String objectKey,
            java.time.Duration ttl);

    StoredObjectMetadata head(
            String bucket,
            String objectKey);
}
~~~

Interface mô tả nghiệp vụ, không đưa AWS `PresignedPutObjectRequest`, GCS `URL` hay Azure `BlobClient` ra tầng service. Các adapter có thể trả thêm header bắt buộc vì mỗi provider có quy tắc ký request riêng.

## 4. URL có chữ ký là bearer capability

Presigned URL, signed URL và SAS token đều là thông tin xác thực mang quyền truy cập. Bất kỳ ai sở hữu URL hợp lệ đều có thể thực hiện thao tác đã được ký cho đến khi URL hoặc credential ký hết hiệu lực hay bị thu hồi.

Một URL cần giới hạn:

- **Resource:** đúng bucket/container và object key.
- **Operation:** GET, PUT hoặc quyền SAS cụ thể.
- **Time:** TTL ngắn, phù hợp thời gian upload/download.
- **Headers:** Content-Type hoặc checksum nếu được ký.
- **Identity:** principal ký URL chỉ có quyền cần thiết.
- **Distribution:** gửi qua HTTPS và chỉ cho user đã được backend authorization.

| Điều URL ký bảo vệ | Điều URL ký không tự bảo vệ |
| --- | --- |
| Chỉ định object cụ thể | Quyền nghiệp vụ của user trong ứng dụng |
| Chỉ định method/permission được ký | Giới hạn số lần URL được sử dụng |
| Giới hạn thời gian | Tự động xóa object khi URL hết hạn |
| Có thể ràng buộc một số request headers | Chống người dùng chia sẻ URL cho người khác |
| Dùng quyền của signer | Kiểm tra tenant ownership mỗi lần URL được dùng |

URL có thể bị copy, lưu trong browser history, proxy log, analytics, chat hoặc screenshot. Không ghi full URL vào application log, tracing span, exception message hoặc audit event. Không đặt signed URL trong query parameter của một URL khác. Trả response chứa URL với `Cache-Control: no-store` và chỉ truyền qua HTTPS.

URL hết hạn không đồng nghĩa object hết hạn. Object vẫn tồn tại trong bucket cho đến khi ứng dụng xóa hoặc lifecycle policy xử lý.

## 5. Thiết kế TTL và quyền signer

### 5.1. TTL theo nghiệp vụ

Một chính sách khởi đầu có thể là:

| Use case | TTL gợi ý | Lý do |
| --- | ---: | --- |
| Upload file nhỏ | 5–10 phút | Giảm thời gian URL bị lộ |
| Download tài liệu thông thường | 2–5 phút | Backend có thể cấp URL mới khi user cần |
| Download file lớn | 10–30 phút | Có thời gian cho download và retry |
| Multipart/resumable upload | Theo session/part | Mỗi phần có URL hoặc session token riêng |

Đây là giá trị khởi đầu, không phải giới hạn bắt buộc của provider. Hãy đo kích thước file, tốc độ mạng và nhu cầu retry để chọn TTL. Không dùng TTL tối đa của provider làm TTL mặc định cho ứng dụng.

### 5.2. Thời hạn URL phụ thuộc credential ký

| Provider | Giới hạn/đặc điểm |
| --- | --- |
| S3 | SDK/CLI hỗ trợ tối đa 7 ngày với SigV4; URL dùng temporary role credentials hết hạn khi credential đó hết hạn, dù TTL được đặt dài hơn |
| GCS | V4 signed URL tối đa 7 ngày; nếu ký qua IAM `signBlob`, nên dùng TTL ngắn vì chữ ký bằng Google-managed service account key có thể ngừng hợp lệ sớm hơn khi key rotation |
| Azure | User delegation key có thời hạn tối đa 7 ngày; SAS phải nằm trong thời hạn key và chịu policy của storage account |

S3 URL có thể hết hạn sớm hơn `signatureDuration` nếu session token của IAM role hết hạn hoặc credential bị thu hồi. GCS signed URL cần một signer hợp lệ và quyền `signBlob`; Azure user delegation SAS phụ thuộc user delegation key và RBAC của principal tạo key.

Trường `expiresAt` trong response của ứng dụng phải biểu diễn **thời điểm hết hạn hiệu lực thực tế**, không chỉ là `now + ttl` đã yêu cầu. Với S3, giới hạn nó bởi thời điểm hết hạn của temporary credentials; với GCS, tuân theo thời hạn của signer/key và giới hạn V4; với Azure, không vượt quá thời điểm hết hạn của user delegation key. Các phép tính trong ví dụ adapter dùng TTL minh họa; adapter production cần trả thời hạn hiệu lực đã được giới hạn theo credential thực tế.

### 5.3. Tách signer identity khỏi user

User cuối không cần cloud IAM. Backend kiểm tra user và dùng workload identity để ký URL. Người dùng nhận capability giới hạn, không nhận access token của signer.

Signer chỉ nên có:

- Quyền đọc object nếu cấp download URL.
- Quyền tạo object nếu cấp upload URL.
- Quyền ký URL tương ứng với cơ chế provider.
- Không có quyền quản trị bucket, IAM hoặc xóa dữ liệu nếu không cần.

Không dùng tài khoản Owner/Administrator để ký URL trong production.

## 6. Amazon S3 — presigned URL với AWS SDK for Java 2.x

### 6.1. Quyền IAM

Signer cần permission tương ứng với request sẽ ký:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadDocuments",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::training-document-vault/documents/*"
    },
    {
      "Sid": "UploadDocuments",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::training-document-vault/documents/*"
    }
  ]
}
~~~

Nếu workload chỉ cấp download URL, bỏ statement `s3:PutObject`. Nếu chỉ cấp upload URL, bỏ `s3:GetObject`. Không thêm `s3:ListBucket` nếu ứng dụng luôn biết object key và không cần liệt kê.

Nếu object dùng SSE-KMS, signer còn cần các quyền KMS phù hợp với thao tác, chẳng hạn `kms:GenerateDataKey` khi upload và `kms:Decrypt` khi download, cùng key policy cho phép. Quyền này nằm trên KMS key và không thay thế `s3:GetObject`/`s3:PutObject`.

Gắn policy vào IAM role của workload:

- EC2: instance profile.
- ECS: task role.
- EKS: IRSA hoặc EKS Pod Identity.
- Lambda: execution role.
- Local development: IAM Identity Center/SSO profile.

Bucket bật Block Public Access và không cấp public ACL. Presigned URL hoạt động trên private object nhờ chữ ký, không cần mở bucket public.

### 6.2. Dependency và presigner bean

Dùng Spring Cloud AWS BOM tương thích với Spring Boot và starter S3:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AWS_VERSION</version>
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

Starter cung cấp tích hợp S3 client. Khai báo `S3Presigner` riêng nếu ứng dụng cần tạo presigned URL:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration(proxyBeanMethods = false)
public class S3PresignerConfiguration {

    @Bean(destroyMethod = "close")
    S3Presigner s3Presigner(
            @Value("${app.storage.aws.region}") String region) {

        return S3Presigner.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~

`DefaultCredentialsProvider` tìm credential từ môi trường AWS: SSO/profile, web identity, ECS task role hoặc EC2 instance profile. Không đặt access key và secret key tĩnh trong `application.yml`.

### 6.3. Presign GET để tải tài liệu

~~~java
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

public class S3SignedUrlAdapter {

    private final S3Presigner presigner;

    public S3SignedUrlAdapter(S3Presigner presigner) {
        this.presigner = presigner;
    }

    public DownloadGrant createDownloadGrant(
            String bucket,
            String objectKey,
            Duration ttl) {

        GetObjectRequest objectRequest = GetObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .build();

        GetObjectPresignRequest presignRequest =
                GetObjectPresignRequest.builder()
                        .signatureDuration(ttl)
                        .getObjectRequest(objectRequest)
                        .build();

        var signed = presigner.presignGetObject(presignRequest);

        return new DownloadGrant(
                URI.create(signed.url().toExternalForm()),
                "GET",
                Instant.now().plus(ttl));
    }
}
~~~

Có thể thêm `responseContentDisposition("attachment; filename=...")` vào `GetObjectRequest` để yêu cầu browser tải file bằng tên hiển thị. Hãy sanitize filename trước khi đưa vào header; không nối chuỗi từ input tùy ý.

### 6.4. Presign PUT để upload

~~~java
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

public UploadGrant createUploadGrant(
        S3Presigner presigner,
        String bucket,
        String objectKey,
        String contentType,
        Duration ttl) {

    PutObjectRequest putRequest = PutObjectRequest.builder()
            .bucket(bucket)
            .key(objectKey)
            .contentType(contentType)
            .build();

    PutObjectPresignRequest presignRequest =
            PutObjectPresignRequest.builder()
                    .signatureDuration(ttl)
                    .putObjectRequest(putRequest)
                    .build();

    var signed = presigner.presignPutObject(presignRequest);

    return new UploadGrant(
            URI.create(signed.url().toExternalForm()),
            "PUT",
            Map.of("Content-Type", contentType),
            Instant.now().plus(ttl));
}
~~~

Vì Content-Type được đưa vào request đã ký, client phải gửi đúng header `Content-Type` như giá trị backend đã ký. Nếu header khác hoặc bị thiếu, S3 có thể trả `SignatureDoesNotMatch`.

Presigned PUT không tự giới hạn số lần sử dụng. Nếu URL còn hạn, người giữ URL có thể gửi lại PUT tới cùng key và ghi đè object. Dùng object key duy nhất cho mỗi upload session, TTL ngắn, lưu version token và xác minh sau upload. Nếu cần điều kiện create-only, đánh giá conditional write `If-None-Match: *` và ký đúng header theo khả năng API/SDK đang dùng.

### 6.5. Kiểm tra URL

Có thể kiểm tra danh tính signer:

~~~bash
aws sts get-caller-identity
~~~

Kiểm tra URL bằng HTTP client:

~~~bash
curl -I "PRESIGNED_GET_URL"
~~~

Đối với PUT:

~~~bash
curl -X PUT \
  -H "Content-Type: text/plain" \
  --upload-file ./sample.txt \
  "PRESIGNED_PUT_URL"
~~~

Không dán URL thật vào ticket, chat hoặc terminal history dùng chung. Trong ví dụ trên, thay placeholder bằng URL nhận từ API ở môi trường test.

## 7. Google Cloud Storage — V4 signed URL

### 7.1. Quyền của signer

Service account được dùng để ký URL phải có permission thực hiện operation trong URL:

- Download: `storage.objects.get`.
- Upload: `storage.objects.create`.
- Ghi đè object đã tồn tại có thể cần thêm quyền delete theo semantics của thao tác.
- Ký bằng IAM Credentials API: runtime identity cần `iam.serviceAccounts.signBlob` trên service account signer.

Permission `iam.serviceAccounts.signBlob` được bao gồm trong role `roles/iam.serviceAccountTokenCreator`. Gán role này trên đúng service account signer, không gán rộng ở project nếu không cần.

### 7.2. Dependency

Dùng Spring Framework on Google Cloud BOM và Storage starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_GCP_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
~~~

Starter cấu hình `Storage` bean và ADC. Không tải service account JSON key về production chỉ để ký URL.

### 7.3. Yêu cầu ServiceAccountSigner

`Storage.signUrl` cần một `ServiceAccountSigner`. Một số loại credentials trong ADC không implement interface này. Ví dụ, credentials từ Google Cloud CLI user account không tự động là signer.

Có hai cách thường gặp:

1. Dùng credentials của service account có hỗ trợ ký và được quản lý an toàn.
2. Dùng IAM Credentials API `signBlob` để ký từ xa thay mặt service account. Runtime identity được cấp `roles/iam.serviceAccountTokenCreator` trên service account signer.

Trên Cloud Run, GKE hoặc môi trường dùng workload identity, hãy kiểm tra loại credentials thực tế. Không giả định chỉ cần inject `Storage` là `signUrl` luôn ký được. Ví dụ dưới đây nhận signer đã được cấu hình qua credential/workload identity:

~~~java
import com.google.auth.ServiceAccountSigner;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.concurrent.TimeUnit;

public class GcsSignedUrlAdapter {

    private final Storage storage;
    private final ServiceAccountSigner signer;

    public GcsSignedUrlAdapter(
            Storage storage,
            ServiceAccountSigner signer) {
        this.storage = storage;
        this.signer = signer;
    }

    public URL createDownloadUrl(
            String bucket,
            String objectKey) {

        BlobInfo blobInfo = BlobInfo.newBuilder(bucket, objectKey).build();

        return storage.signUrl(
                blobInfo,
                5,
                TimeUnit.MINUTES,
                Storage.SignUrlOption.withV4Signature(),
                Storage.SignUrlOption.httpMethod(HttpMethod.GET),
                Storage.SignUrlOption.signWith(signer));
    }
}
~~~

Signed URL V4 dùng XML API endpoint của Cloud Storage. Không coi signed URL là một token OAuth thông thường hoặc thay endpoint bằng JSON API.

### 7.4. Ký URL PUT với Content-Type

~~~java
import com.google.auth.ServiceAccountSigner;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.HttpMethod;
import com.google.cloud.storage.Storage;
import java.net.URL;
import java.util.concurrent.TimeUnit;

public URL createUploadUrl(
        Storage storage,
        ServiceAccountSigner signer,
        String bucket,
        String objectKey,
        String contentType) {

    BlobInfo blobInfo = BlobInfo.newBuilder(bucket, objectKey)
            .setContentType(contentType)
            .build();

    return storage.signUrl(
            blobInfo,
            10,
            TimeUnit.MINUTES,
            Storage.SignUrlOption.withV4Signature(),
            Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
            Storage.SignUrlOption.withContentType(),
            Storage.SignUrlOption.signWith(signer));
}
~~~

Client gửi `PUT` với đúng Content-Type đã ký:

~~~bash
curl -X PUT \
  -H "Content-Type: application/pdf" \
  --upload-file ./contract.pdf \
  "GCS_SIGNED_PUT_URL"
~~~

Nếu request không gửi đúng header đã ký, Cloud Storage từ chối chữ ký. Signed URL V4 có giới hạn thời hạn tối đa 7 ngày; với workload signer dùng IAM `signBlob`, nên chọn thời gian ngắn cho URL truy cập tạm thời.

### 7.5. Kiểm tra cấu hình

Xác minh service account signer và quyền:

~~~bash
gcloud iam service-accounts describe \
  SIGNER_SERVICE_ACCOUNT \
  --project=PROJECT_ID
~~~

Kiểm tra quyền object ở bucket:

~~~bash
gcloud storage buckets get-iam-policy gs://training-document-vault
~~~

Kiểm tra signed GET:

~~~bash
curl -I "GCS_SIGNED_GET_URL"
~~~

Nếu `Storage.signUrl` ném `IllegalStateException`, kiểm tra credentials có implement `ServiceAccountSigner` hay chưa. Nếu ký bằng IAM Credentials API, kiểm tra Service Account Credentials API và quyền `iam.serviceAccounts.signBlob`.

## 8. Azure Blob Storage — user delegation SAS

### 8.1. Chọn user delegation SAS

Azure có service SAS và account SAS ký bằng storage account key. Với ứng dụng Spring Boot dùng Microsoft Entra identity, ưu tiên **user delegation SAS**:

- Backend xác thực bằng managed identity/workload identity hoặc service principal.
- Backend yêu cầu Blob Storage cấp user delegation key.
- Backend dùng key đó ký SAS với resource, permission và thời gian cụ thể.
- Client nhận SAS URL và truy cập blob mà không cần account key.

Microsoft khuyến nghị user delegation SAS khi có thể vì không phải chia sẻ storage account key. User delegation key có thời hạn tối đa 7 ngày; SAS phải nằm trong thời hạn key.

### 8.2. RBAC cho signer

Cần tách hai loại quyền:

| Phạm vi | Role/permission | Mục đích |
| --- | --- | --- |
| Storage account scope | `Storage Blob Delegator` | Cho phép gọi `getUserDelegationKey` |
| Container scope, download | `Storage Blob Data Reader` | Cho phép signer đọc blob |
| Container scope, upload | `Storage Blob Data Contributor` | Cho phép signer tạo/ghi blob |

`getUserDelegationKey` hoạt động ở cấp storage account. Vì vậy role `Storage Blob Delegator` cần được gán ở storage account, resource group hoặc subscription scope. Data role có thể giới hạn ở container cụ thể.

Quyền hiệu lực của user delegation SAS là giao giữa quyền data mà signer được Azure RBAC cấp và permission được ghi trong SAS. Nếu SAS có cờ read nhưng signer không có quyền đọc blob ở scope phù hợp, client vẫn không đọc được. Ngược lại, SAS không thể mở rộng quyền vượt quá permission của signer.

Không cấp `Storage Blob Data Owner` hoặc storage account key chỉ để ký một SAS đọc file.

### 8.3. Dependency và BlobServiceClient

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AZURE_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

Dùng `DefaultAzureCredential` để lấy token từ managed identity hoặc workload identity trong môi trường chạy:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AzureBlobConfiguration {

    @Bean
    BlobServiceClient blobServiceClient(
            @org.springframework.beans.factory.annotation.Value(
                    "${app.storage.azure.endpoint}") String endpoint) {

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();
    }
}
~~~

Trong môi trường local, `DefaultAzureCredential` có thể dùng Azure CLI hoặc developer credential. Trong production, ưu tiên managed identity/workload identity. Không đặt storage account key hoặc connection string có key trong source code.

### 8.4. Tạo user delegation key và SAS chỉ đọc

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.UserDelegationKey;
import com.azure.storage.blob.sas.BlobSasPermission;
import com.azure.storage.blob.sas.BlobServiceSasSignatureValues;
import com.azure.storage.common.sas.SasProtocol;
import java.net.URI;
import java.time.OffsetDateTime;

public class AzureSasAdapter {

    private final BlobServiceClient serviceClient;

    public AzureSasAdapter(BlobServiceClient serviceClient) {
        this.serviceClient = serviceClient;
    }

    public URI createReadUrl(
            String container,
            String blobName) {

        OffsetDateTime now = OffsetDateTime.now();
        OffsetDateTime start = now.minusMinutes(5);
        OffsetDateTime expiry = now.plusMinutes(5);

        UserDelegationKey delegationKey =
                serviceClient.getUserDelegationKey(start, expiry);

        var blob = serviceClient
                .getBlobContainerClient(container)
                .getBlobClient(blobName);

        BlobSasPermission permission =
                new BlobSasPermission().setReadPermission(true);

        BlobServiceSasSignatureValues values =
                new BlobServiceSasSignatureValues(expiry, permission)
                        .setStartTime(start)
                        .setProtocol(SasProtocol.HTTPS);

        String sasToken =
                blob.generateUserDelegationSas(values, delegationKey);

        return URI.create(blob.getBlobUrl() + "?" + sasToken);
    }
}
~~~

Ví dụ tạo user delegation key cho từng request để làm rõ quy trình. Trong production, có thể cache key trong thời hạn an toàn và tạo nhiều SAS từ key đó; không giữ key lâu hơn thời gian hiệu lực hoặc log key material.

SAS chỉ có quyền read. Không cấp write, delete hoặc list nếu client chỉ tải một blob.

### 8.5. Tạo SAS upload

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.UserDelegationKey;
import com.azure.storage.blob.sas.BlobSasPermission;
import com.azure.storage.blob.sas.BlobServiceSasSignatureValues;
import com.azure.storage.common.sas.SasProtocol;
import java.net.URI;
import java.time.OffsetDateTime;

public URI createUploadUrl(
        BlobServiceClient serviceClient,
        String container,
        String blobName) {

    OffsetDateTime now = OffsetDateTime.now();
    OffsetDateTime start = now.minusMinutes(5);
    OffsetDateTime expiry = now.plusMinutes(10);

    UserDelegationKey key =
            serviceClient.getUserDelegationKey(start, expiry);

    var blob = serviceClient
            .getBlobContainerClient(container)
            .getBlobClient(blobName);

    BlobSasPermission permission = new BlobSasPermission()
            .setCreatePermission(true)
            .setWritePermission(true);

    BlobServiceSasSignatureValues values =
            new BlobServiceSasSignatureValues(expiry, permission)
                    .setStartTime(start)
                    .setProtocol(SasProtocol.HTTPS);

    String sasToken = blob.generateUserDelegationSas(values, key);

    return URI.create(blob.getBlobUrl() + "?" + sasToken);
}
~~~

SAS upload có quyền create/write trên đúng blob. Client dùng `PUT` theo API Blob Storage và gửi headers phù hợp. Không cấp container-wide SAS nếu chỉ cần upload một object.

### 8.6. Thời hạn và thu hồi

User delegation key có thể dùng để ký nhiều SAS cho tới khi key hết hạn. Hãy đặt key validity đủ dài để ký các SAS ngắn hạn nhưng không quá 7 ngày. SAS expiry phải nằm trong key validity.

Khi phát hiện SAS bị lộ, có thể revoke user delegation keys ở storage account, thay đổi quyền RBAC hoặc xóa/đổi trạng thái resource. Việc revoke key có thể ảnh hưởng nhiều SAS được ký từ key đó; cần đánh giá blast radius.

## 9. Một API nghiệp vụ cho ba provider

### 9.1. Cấu hình provider

Chỉ một adapter được kích hoạt trong lab bằng Spring profile:

~~~yaml
app:
  storage:
    provider: aws
    bucket: training-document-vault
    upload-ttl: 10m
    download-ttl: 5m
    max-file-size: 10485760
    allowed-content-types:
      - application/pdf
      - image/png
      - image/jpeg
~~~

Tên bucket, endpoint và region được cấu hình theo môi trường. Không nhận các giá trị này từ request người dùng.

### 9.2. Service tạo upload session

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository repository;
    private final DocumentObjectStorage objectStorage;
    private final DocumentAuthorization authorization;

    public DocumentService(
            DocumentRepository repository,
            DocumentObjectStorage objectStorage,
            DocumentAuthorization authorization) {
        this.repository = repository;
        this.objectStorage = objectStorage;
        this.authorization = authorization;
    }

    public UploadSessionResponse createUpload(
            AuthenticatedUser user,
            CreateDocumentRequest request) {

        authorization.requireCanCreateDocument(user);

        validateUploadRequest(request);

        UUID documentId = UUID.randomUUID();
        String objectKey = "documents/" + user.tenantId()
                + "/" + documentId;

        DocumentRecord record = DocumentRecord.pending(
                documentId,
                user.tenantId(),
                objectKey,
                request.filename(),
                request.contentType(),
                request.sizeBytes());

        repository.save(record);

        UploadGrant grant = objectStorage.createUploadGrant(
                record.bucketName(),
                objectKey,
                request.contentType(),
                Duration.ofMinutes(10));

        Instant expiry = grant.expiresAt();
        repository.updateUploadExpiry(documentId, expiry);

        return new UploadSessionResponse(
                documentId,
                grant.url(),
                grant.method(),
                grant.requiredHeaders(),
                expiry);
    }

    private void validateUploadRequest(CreateDocumentRequest request) {
        if (request.sizeBytes() <= 0 || request.sizeBytes() > 10_485_760) {
            throw new IllegalArgumentException("Kích thước file không hợp lệ");
        }
        if (!request.contentType().matches(
                "application/pdf|image/png|image/jpeg")) {
            throw new IllegalArgumentException("Content-Type không được hỗ trợ");
        }
    }
}
~~~

Các kiểu `AuthenticatedUser`, `DocumentRepository`, `DocumentRecord`, `CreateDocumentRequest` và `UploadSessionResponse` là model nghiệp vụ minh họa. Không giữ transaction database mở trong khi chờ client upload file. Nếu ký URL thất bại sau khi record đã lưu, đánh dấu session lỗi hoặc để job reconciliation xử lý record `PENDING_UPLOAD`.

Không tin `filename`, `contentType` hoặc `sizeBytes` do client khai báo. Chúng chỉ dùng để khởi tạo session và kiểm tra sơ bộ; backend xác minh object thật sau upload.

### 9.3. Endpoint tạo session

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping
    public ResponseEntity<UploadSessionResponse> create(
            @RequestBody CreateDocumentRequest request,
            @AuthenticationPrincipal AuthenticatedUser user) {

        UploadSessionResponse response =
                documentService.createUpload(user, request);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(response);
    }
}
~~~

Trong ứng dụng thật, `AuthenticatedUser` lấy từ Spring Security principal hoặc service xác thực tương đương. Không bind principal từ JSON request.

### 9.4. Client upload trực tiếp

Response mẫu:

~~~json
{
  "documentId": "4c9d8b21-2c71-4e10-8d34-1d7e2a2c4f11",
  "method": "PUT",
  "url": "https://storage-provider.example/signed-request",
  "requiredHeaders": {
    "Content-Type": "application/pdf"
  },
  "expiresAt": "2026-11-24T11:20:00Z"
}
~~~

Client gửi đúng HTTP method và các headers backend trả về:

~~~javascript
const response = await fetch(uploadUrl, {
  method: "PUT",
  headers: requiredHeaders,
  body: file
});

if (!response.ok) {
  throw new Error("Upload failed");
}
~~~

Đây là ví dụ trình duyệt. Không log `uploadUrl`, không lưu URL trong local storage và không gửi URL cho analytics. Nếu upload thất bại do URL hết hạn, client gọi API tạo session mới theo policy của backend.

## 10. Xác minh object sau upload

### 10.1. Vì sao cần finalize?

Client báo upload thành công không đủ để đánh dấu tài liệu `AVAILABLE`. Backend cần đọc metadata object từ storage và kiểm tra:

- Object có tồn tại hay không.
- Size thực tế có khớp policy hay không.
- Content-Type có nằm trong allowlist hay không.
- Checksum có hợp lệ hay không.
- Object key có đúng session đã cấp hay không.
- Generation/ETag có được lưu để đối chiếu các lần cập nhật sau này hay không.

### 10.2. Endpoint complete

~~~java
@PostMapping("/{documentId}/complete")
public ResponseEntity<DocumentView> complete(
        @PathVariable UUID documentId,
        AuthenticatedUser user) {

    DocumentView result =
            documentService.verifyUploadAndComplete(documentId, user);

    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(result);
}
~~~

Service cần kiểm tra tenant ownership trước khi gọi storage. Nếu object chưa tồn tại, giữ trạng thái pending hoặc trả lỗi retryable. Nếu size/type/checksum sai, chuyển `REJECTED`, xóa hoặc quarantine object theo policy và ghi audit.

### 10.3. Đọc metadata bằng provider adapter

Ví dụ adapter S3 dùng `HeadObject`:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public StoredObjectMetadata headS3(
        S3Client client,
        String bucket,
        String key) {

    var response = client.headObject(
            HeadObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build());

    return new StoredObjectMetadata(
            response.contentLength(),
            response.contentType(),
            response.versionId() != null
                    ? response.versionId()
                    : response.eTag(),
            response.checksumSHA256());
}
~~~

GCS có thể dùng `Storage.get(BlobId.of(bucket, key))` và lấy `getSize()`, `getContentType()`, `getGeneration()` và checksum. Azure dùng `BlobClient.getProperties()` và đọc blob size, Content-Type, ETag và checksum fields phù hợp với version SDK.

Không dùng ETag như SHA-256. ETag có semantics riêng theo provider, encryption và multipart upload. Nếu cần kiểm tra integrity xuyên provider, tính SHA-256 ở client hoặc backend và xác minh bằng cơ chế checksum mà provider hỗ trợ.

### 10.4. Tránh race khi finalize

Presigned PUT có thể được dùng lại cho tới khi hết hạn. Nếu object bị ghi lại giữa lúc backend HEAD và lúc cập nhật database, record có thể lưu token không còn là phiên bản hiện tại.

Dùng object key riêng cho upload session và lưu version token trả về. Nếu provider hỗ trợ conditional create/write, ký đúng precondition hoặc dùng API server-side có generation/ETag condition. Nếu bucket bật versioning, lưu version ID/generation cụ thể và dùng version đó khi đọc. Với upload có thể bị replay, phát hiện generation/ETag thay đổi sau finalize và không tự động coi object mới là bản đã duyệt.

## 11. Cấp download URL có authorization

### 11.1. Kiểm tra quyền trước khi ký

Một API download không nên nhận bucket và key tùy ý. Luồng an toàn:

1. Xác thực người gọi.
2. Tải document record từ database.
3. Kiểm tra tenant ownership và quyền đọc document.
4. Xác nhận state là `AVAILABLE`.
5. Lấy bucket/object key từ record.
6. Ký URL GET với TTL ngắn.
7. Ghi audit metadata về lần cấp URL, không ghi token.
8. Trả URL với `Cache-Control: no-store`.

### 11.2. Service cấp download URL

~~~java
public DownloadSessionResponse createDownload(
        UUID documentId,
        AuthenticatedUser user) {

    DocumentRecord document = repository.findById(documentId)
            .orElseThrow(DocumentNotFoundException::new);

    authorization.requireCanRead(user, document);

    if (document.state() != DocumentState.AVAILABLE) {
        throw new IllegalStateException("Tài liệu chưa sẵn sàng");
    }

    DownloadGrant grant = objectStorage.createDownloadGrant(
            document.bucketName(),
            document.objectKey(),
            Duration.ofMinutes(5));

    audit.recordDownloadUrlIssued(
            document.id(),
            user.id(),
            grant.expiresAt());

    return new DownloadSessionResponse(
            document.id(),
            grant.url(),
            grant.method(),
            grant.expiresAt());
}
~~~

Mỗi lần người dùng cần tải lại, backend kiểm tra quyền và cấp URL mới. Không lưu URL để tái sử dụng lâu dài.

### 11.3. Không cấp URL cho document chưa xác minh

Nếu document ở trạng thái `PENDING_UPLOAD`, `VERIFYING` hoặc `REJECTED`, không cấp URL download. Nếu document đã bị xóa theo nghiệp vụ, URL mới không được tạo dù object storage chưa kịp dọn.

URL đã cấp trước đó có thể vẫn hoạt động tới khi hết hạn. Vì vậy TTL phải ngắn và quy trình xóa cần tính đến URL đang còn hiệu lực.

## 12. CORS cho trình duyệt upload/download trực tiếp

CORS cho phép browser gửi request cross-origin tới object storage. CORS không cấp quyền truy cập; request vẫn phải có chữ ký hợp lệ.

CORS cần giới hạn:

- Origin của frontend chính thức.
- HTTP methods cần thiết: GET, PUT, HEAD.
- Request headers: Content-Type và checksum headers được dùng.
- Response headers cần browser đọc: ETag hoặc generation header nếu cần.
- Max age của preflight cache.

Ví dụ cấu hình khái niệm:

~~~json
[
  {
    "origin": ["https://app.example.com"],
    "method": ["GET", "PUT", "HEAD"],
    "responseHeader": ["Content-Type", "ETag", "x-goog-generation"],
    "maxAgeSeconds": 1800
  }
]
~~~

Cấu trúc và tên field CORS khác nhau giữa S3, GCS và Azure. Chuyển cấu hình mẫu sang schema chính thức của provider trước khi áp dụng. Không dùng `origin: ["*"]` trong production nếu frontend chỉ có một số domain xác định.

Nếu browser báo CORS nhưng `curl` thành công, kiểm tra preflight OPTIONS, allowed origin, allowed headers và exposed response headers. Nếu `curl` cũng trả 403, kiểm tra chữ ký, credential expiry, method và IAM/RBAC.

## 13. Kiểm tra upload, loại file và kích thước

### 13.1. Không tin Content-Type từ client

Header Content-Type do client gửi không chứng minh nội dung thực sự là PDF hoặc PNG. Backend cần kiểm tra file signature/magic bytes hoặc chạy content scanner sau upload.

Quy trình phù hợp:

1. Client khai báo content type và size để tạo session.
2. Backend kiểm tra allowlist và giới hạn khai báo.
3. Backend ký URL với Content-Type nếu provider hỗ trợ.
4. Client upload.
5. Backend HEAD để đọc size và metadata.
6. Worker đọc một phần hoặc toàn bộ bytes để xác minh file signature, checksum và malware.
7. Chỉ chuyển state sang `AVAILABLE` khi tất cả bước cần thiết thành công.

### 13.2. Giới hạn kích thước

Không giả định presigned PUT/SAS tự áp dụng được mọi giới hạn size nghiệp vụ. Nếu cần hard limit:

- S3: xem xét presigned POST policy với điều kiện `content-length-range`, hoặc proxy upload qua backend/gateway.
- GCS: xem xét resumable upload/session và các precondition phù hợp; vẫn cần verify size sau upload.
- Azure: SAS giới hạn resource và permission, không tự cung cấp mọi content-length policy cho client.

Nếu chỉ kiểm tra size sau upload, object quá lớn đã được lưu và có thể phát sinh chi phí. Kết hợp quota theo tenant, rate limit, upload session expiry, cleanup và policy upload phù hợp.

### 13.3. Checksum và integrity

Khi provider hỗ trợ checksum header, ký checksum vào request để client không thể thay đổi header sau khi URL được cấp. Sau upload, đọc checksum hoặc tải bytes để xác minh theo yêu cầu.

Không dùng ETag như checksum chung cho cả ba provider. Multipart upload, server-side encryption và implementation khác nhau có thể làm ETag không tương đương hash nội dung.

## 14. URL hết hạn, thu hồi và xử lý lỗi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| S3 `Request has expired` | URL hết hạn hoặc temporary credentials signer đã hết hạn | Cấp URL mới sau khi authorization lại |
| S3 `SignatureDoesNotMatch` | Sai region, method hoặc signed header | So sánh request thực tế với method/header đã ký |
| GCS 403 | Signer thiếu object permission hoặc chữ ký không hợp lệ | Kiểm tra signer identity, IAM, clock và canonical request |
| GCS `IllegalStateException` khi sign | Credentials không implement `ServiceAccountSigner` | Cấu hình signer hoặc IAM `signBlob` |
| Azure 403 | SAS hết hạn, thiếu permission, sai resource hoặc delegation key hết hạn | Kiểm tra `sp`, `sr`, `st`, `se`, key validity và RBAC |
| Browser CORS error | CORS origin/method/header không khớp | Kiểm tra OPTIONS preflight và CORS config |
| Upload trả 200 nhưng document chưa READY | Chưa chạy complete hoặc verify thất bại | Kiểm tra object HEAD, checksum, size và state |
| URL đã hết hạn nhưng object còn | URL TTL không phải object lifecycle | Xóa object theo nghiệp vụ hoặc lifecycle rule |
| URL bị lộ | Người khác có thể dùng bearer URL trong thời hạn | Thu hồi theo khả năng provider, xóa/đổi object hoặc chờ expiry; điều tra audit |

Không retry cùng URL sau khi hết hạn. Backend phải xác thực lại user, kiểm tra trạng thái document và ký URL mới.

## 15. Bảo mật và vận hành kho tài liệu

### 15.1. Private bucket/container

- Tắt public access và public ACL.
- Bật encryption at rest theo policy của provider.
- Dùng IAM/RBAC tối thiểu cho runtime signer.
- Phân tách role upload, download, cleanup và provisioning nếu phù hợp.
- Bật audit log cho hoạt động object và role assignment.
- Dùng TLS/HTTPS cho mọi URL.
- Không đưa storage account key hoặc service account JSON vào source code.

### 15.2. Không log signed URL

Query string có thể chứa signature, credential scope, expiry và SAS permission. Log full URL tương đương log một credential bearer.

Trong log chỉ ghi:

- Document ID nội bộ.
- Tenant ID đã được chuẩn hóa.
- Provider và operation.
- Object key đã được bảo vệ theo policy.
- Expiry timestamp.
- Principal signer hoặc role session ID.
- Request ID và kết quả.

Không log URL, SAS token, access token hoặc nội dung file.

### 15.3. Audit issuance

Có thể tạo bảng `document_access_grants` để theo dõi:

- Document ID.
- User ID yêu cầu.
- Operation GET/PUT.
- Provider và signer identity.
- Issued time, expiry time.
- Upload session ID hoặc correlation ID.
- Trạng thái upload/finalize.

Không lưu token hoặc full URL trong bảng audit. Audit log giúp điều tra ai yêu cầu quyền truy cập và trong khoảng thời gian nào.

### 15.4. Cleanup orphan và lifecycle

Có hai loại dữ liệu cần cleanup:

1. Database record `PENDING_UPLOAD` hết hạn nhưng chưa có object.
2. Object đã upload nhưng không được finalize hoặc bị reject.

Dùng scheduled worker để tìm session quá hạn và kiểm tra object. Xóa object orphan theo policy; không chỉ xóa database record rồi bỏ object lại trong bucket.

Có thể dùng lifecycle rule để dọn prefix tạm như `staging/` sau một khoảng thời gian. Lifecycle là lớp bảo vệ chi phí, không thay thế state machine và authorization nghiệp vụ. Khi bucket bật versioning hoặc soft delete, tính thêm noncurrent version và soft-deleted storage vào chi phí.

## 16. Kiểm thử

### 16.1. Unit test cho domain service

Kiểm tra:

- User không thuộc tenant không tạo được upload session.
- Content-Type không nằm trong allowlist bị từ chối.
- Size khai báo vượt limit bị từ chối.
- Object key do server sinh và không chứa filename thô.
- Document chưa `AVAILABLE` không được cấp download URL.
- User không có quyền đọc document không nhận URL.
- Upload grant chỉ có method PUT và TTL đúng policy.
- Download grant chỉ có method GET và TTL ngắn hơn upload session nếu policy yêu cầu.
- Signed URL không được ghi vào database hoặc log.

### 16.2. Integration test với provider thật

Dùng bucket/container test và workload identity riêng:

1. Tạo object storage private.
2. Cấp signer role đúng phạm vi.
3. Tạo upload session từ Spring Boot.
4. Dùng URL upload file nhỏ với đúng method/header.
5. Gọi complete endpoint và xác minh object metadata.
6. Tạo download URL và tải file.
7. Thử URL sau khi hết hạn; kỳ vọng bị từ chối.
8. Thử sai HTTP method; kỳ vọng bị từ chối.
9. Thử đổi Content-Type đã ký; kỳ vọng bị từ chối.
10. Thử truy cập object key khác; kỳ vọng bị từ chối.
11. Thử user khác tenant yêu cầu download; backend phải từ chối trước khi ký.
12. Kiểm tra URL không xuất hiện trong log.
13. Kiểm tra CORS từ browser origin được phép và origin không được phép.
14. Dọn object, versions và test session sau khi kiểm thử.

### 16.3. Kiểm thử replay và race condition

Signed URL không phải token một lần. Kiểm thử:

- Gửi PUT hai lần trước expiry.
- Gọi complete hai lần.
- Gọi complete khi upload chưa xong.
- Ghi đè object sau khi document đã `AVAILABLE`.
- Gửi download URL sau khi document đã bị đánh dấu deleted.
- Upload object lớn hơn declared size.
- Upload nội dung không khớp Content-Type.
- Gửi cùng URL từ client khác.

Ứng dụng cần idempotent cho complete/finalize, lưu generation/version token, kiểm tra object hiện tại và không để một lần replay làm thay đổi tài liệu đã được duyệt mà không có quy trình version mới.

### 16.4. Test emulator và cloud thật

LocalStack, Azurite hoặc emulator phù hợp có thể giúp test một phần client API. Tuy nhiên, signing behavior, IAM/RBAC, URL expiry, CORS và cloud-specific policy cần integration test trên project/account test thật. Không kết luận quyền signer hoặc URL semantics chỉ từ mock.

## 17. So sánh ba provider

| Khía cạnh | Amazon S3 | Google Cloud Storage | Azure Blob Storage |
| --- | --- | --- | --- |
| Temporary URL | Presigned URL | Signed URL V4 | SAS URL |
| Java signing API | `S3Presigner` | `Storage.signUrl` | `generateUserDelegationSas` |
| Signing identity | AWS IAM role/user credentials | Service account signer | Microsoft Entra principal + user delegation key |
| Download permission | `s3:GetObject` | `storage.objects.get` | SAS `read` + RBAC data permission |
| Upload permission | `s3:PutObject` | `storage.objects.create` | SAS `create`/`write` + RBAC data permission |
| Max signing/key duration | SigV4 URL tối đa 7 ngày; temporary credentials có thể ngắn hơn | V4 tối đa 7 ngày; remote `signBlob` nên dùng TTL ngắn | User delegation key tối đa 7 ngày |
| Signed headers | Request headers có thể được ký | Content-Type và headers được chọn có thể được ký | SAS permission và signed fields theo SAS |
| Browser support | Cần CORS bucket | Cần CORS bucket | Cần CORS Blob service |
| Revocation | Credential/policy/object; URL thường không có nút revoke riêng | Signer key/permission hoặc object; URL có thể bị ảnh hưởng bởi key rotation | Revoke delegation keys/RBAC hoặc resource; ảnh hưởng có thể rộng |
| Version token | Version ID/ETag | Generation/metageneration | Version ID/ETag |

Không ánh xạ máy móc presigned URL, signed URL và SAS thành một loại token có semantics giống nhau. Adapter nên chuẩn hóa contract `createUploadGrant`/`createDownloadGrant`, còn provider implementation giữ riêng method, header, signer identity, version token và cơ chế revoke.

## 18. Bài tập thực hành tổng hợp

**Bối cảnh:** Xây document repository cho ứng dụng Spring Boot nhiều tenant. Người dùng upload hợp đồng PDF, backend xác minh file và cấp URL download có thời hạn. File phải nằm trong private bucket/container và không được truy cập chéo tenant.

### Nhiệm vụ A — Storage và metadata

1. Tạo bucket/container riêng cho môi trường lab.
2. Tắt public access.
3. Tạo bảng `documents` và state machine.
4. Sinh object key từ tenant đã xác thực và UUID.
5. Lưu filename gốc, content type, size, checksum và version token trong database.

### Nhiệm vụ B — Upload URL

1. Tạo signer identity riêng.
2. Cấp quyền upload tối thiểu cho đúng prefix/container.
3. Viết adapter tạo presigned PUT, GCS V4 PUT hoặc Azure SAS create/write.
4. Chọn TTL 5–10 phút.
5. Trả URL cùng required headers.
6. Upload file trực tiếp từ browser.

### Nhiệm vụ C — Verify và finalize

1. Tạo endpoint complete.
2. Đọc metadata object bằng HEAD/properties.
3. Kiểm tra size, Content-Type và checksum.
4. Kiểm tra tenant/object key và session state.
5. Lưu generation/version token.
6. Chỉ chuyển state sang `AVAILABLE` sau khi xác minh.

### Nhiệm vụ D — Download URL

1. Xác thực user và tenant.
2. Kiểm tra quyền đọc document.
3. Chỉ cấp URL cho document `AVAILABLE`.
4. Ký GET URL với TTL 2–5 phút.
5. Trả `Cache-Control: no-store`.
6. Xác minh URL tải được object mà không cần cloud credential của user.

### Nhiệm vụ E — Bảo mật và vận hành

- Kiểm tra URL hết hạn, sai method và sai Content-Type.
- Thử replay PUT và ghi nhận generation mới.
- Kiểm tra user tenant khác không nhận được URL.
- Cấu hình CORS chỉ cho frontend origin.
- Bật audit log nhưng không ghi URL/token.
- Dọn upload session hết hạn và object orphan.
- So sánh S3 presigned URL, GCS V4 signed URL và Azure user delegation SAS.

**Tiêu chí đạt:** Ứng dụng lưu metadata trong database và bytes trong object storage; signer dùng workload identity; bucket/container private; upload/download URL chỉ cấp sau authorization; TTL ngắn; object được verify trước khi `AVAILABLE`; và test chứng minh URL sai method, hết hạn hoặc truy cập chéo tenant bị từ chối.

## 19. Ghi nhớ

- Metadata và trạng thái tài liệu nên nằm trong database; bytes nằm trong object storage.
- Object key phải do backend sinh; filename gốc được lưu riêng.
- Presigned URL, GCS signed URL và Azure SAS là bearer capability; người giữ URL có thể sử dụng trong phạm vi đã ký.
- Backend phải authorize user và tenant trước khi cấp URL.
- S3 dùng `S3Presigner`; GCS dùng `Storage.signUrl` với V4 và `ServiceAccountSigner`; Azure ưu tiên user delegation SAS.
- TTL URL phụ thuộc cả expiry được cấu hình lẫn lifetime của signer credential hoặc delegation key.
- Signed PUT/SAS không tự đảm bảo URL chỉ dùng một lần; cần object key duy nhất, precondition/version guard và finalize idempotent.
- Client upload trực tiếp phải gửi đúng method và signed headers.
- Verify size, checksum, Content-Type và version token trước khi đánh dấu document `AVAILABLE`.
- CORS chỉ điều khiển browser cross-origin; CORS không thay IAM/RBAC.
- Không log hoặc lưu full URL/SAS token; trả response `Cache-Control: no-store`.
- URL hết hạn không xóa object; cần state machine, cleanup worker và lifecycle policy.

### Tài liệu tham khảo

- [AWS SDK for Java 2.x — Work with S3 presigned URLs](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3-presign.html)
- [Amazon S3 — Download and upload objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [AWS SDK for Java 2.x — S3Presigner API](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/s3/presigner/S3Presigner.html)
- [Spring Cloud AWS reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [Cloud Storage — Signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signed-urls)
- [Cloud Storage Java — Storage.signUrl](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Cloud Storage — Create signatures and signBlob](https://docs.cloud.google.com/storage/docs/authentication/creating-signatures)
- [Cloud Storage — CORS configuration](https://docs.cloud.google.com/storage/docs/cross-origin)
- [Azure Storage — Create a user delegation SAS with Java](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-user-delegation-sas-create-java)
- [Azure Storage — Built-in RBAC roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/storage)
- [Azure Storage — Get User Delegation Key permissions](https://learn.microsoft.com/en-us/rest/api/storageservices/get-user-delegation-key)
- [Azure Storage — SAS overview and security](https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview)
- [Spring Cloud Azure reference](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/)
