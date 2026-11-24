# Amazon S3: Tạo URL ký sẵn và giới hạn quyền truy cập theo thời gian

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, người học tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud, đồng thời thực hành xác thực danh tính, phân quyền, quản lý secret và kiểm thử tích hợp. Khi ứng dụng lưu ảnh, hóa đơn hoặc tệp tải lên bằng **Amazon S3**, cách đơn giản là cho backend đọc/ghi dữ liệu rồi chuyển byte đến client. Tuy nhiên, backend có thể trở thành điểm nghẽn khi nhiều người dùng truyền tệp lớn.

**Presigned URL (URL ký sẵn)** cho phép client gửi yêu cầu HTTP trực tiếp đến một object S3 theo quyền đã được ký từ trước và trong một khoảng thời gian xác định. Ứng dụng Spring Boot vẫn kiểm tra **ai được phép truy cập object nào** trước khi tạo URL, còn S3 thực hiện phần truyền dữ liệu.

Sau bài này, bạn có thể:

1. Giải thích cách một presigned URL của S3 hoạt động, vì sao bucket có thể vẫn private và quyền của URL đến từ đâu.
2. Dùng **AWS SDK for Java v2** trong Spring Boot để tạo presigned **GET** và **PUT** URL.
3. Chọn thời hạn chữ ký hợp lý, hiểu giới hạn 7 ngày của S3 Signature V4 và tác động của **temporary credentials**.
4. Ràng buộc bucket, object key, HTTP method và các header đã ký; phân biệt giới hạn chữ ký với kiểm tra dữ liệu nghiệp vụ.
5. Bảo vệ luồng tải lên/tải xuống bằng IAM, bucket policy, CORS, kiểm tra quyền người dùng và giám sát.
6. Kiểm thử các tình huống URL hết hạn, credentials hết hạn, header không khớp, sai Region và lộ URL.

> Bài sử dụng **Spring Cloud AWS** cùng **AWS SDK for Java v2** (namespace `software.amazon.awssdk`). Cần chọn phiên bản Spring Cloud AWS tương thích với Spring Boot thực tế của dự án. Các đoạn code dùng tên bucket minh họa; không trỏ vào dữ liệu production khi thực hành.

## 1. Vì sao cần presigned URL?

Giả sử người dùng muốn tải một hóa đơn PDF dung lượng 80 MiB. Có hai cách tổ chức đường đi của dữ liệu:

| Cách truy cập | Đường đi dữ liệu | Trách nhiệm của Spring Boot |
| --- | --- | --- |
| Backend làm trung gian | Browser → Spring Boot → S3 (hoặc ngược lại) | Xác thực, kiểm tra quyền, mở stream và truyền từng byte |
| Presigned URL | Browser ↔ S3 trực tiếp | Xác thực, kiểm tra quyền, phát URL theo scope và thời hạn, theo dõi trạng thái |

Với presigned URL, backend không cần giữ một kết nối đọc/ghi dài với S3 cho mọi file lớn; nhưng backend vẫn chịu trách nhiệm về **authorization, quota, khóa đối tượng, audit và trạng thái nghiệp vụ**.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant API as Spring Boot API
    participant DB as Database nghiệp vụ
    participant S3 as S3 bucket private

    U->>API: GET /documents/42/download-url
    API->>DB: Kiểm tra owner/tenant và lấy object key
    DB-->>API: Có quyền + key tương ứng
    API-->>U: Presigned GET URL (10 phút)
    U->>S3: GET trực tiếp bằng URL
    S3-->>U: Nội dung object
~~~

Presigned URL **không tự đổi ACL hoặc bucket policy thành public**. Bucket có thể tiếp tục bật **S3 Block Public Access** và dùng Object Ownership `Bucket owner enforced`. Truy cập được xác thực bằng **chữ ký gắn với IAM principal** đã tạo URL, trong phạm vi quyền hiệu lực của principal đó.

### 1.1. URL ký sẵn chứa thông tin gì?

Một URL mang chữ ký Signature Version 4 có cấu trúc minh họa:

~~~text
https://training-private-docs.s3.ap-southeast-1.amazonaws.com/
    documents/invoice-42.pdf
    ?X-Amz-Algorithm=AWS4-HMAC-SHA256
    &X-Amz-Credential=...%2F20261124%2Fap-southeast-1%2Fs3%2Faws4_request
    &X-Amz-Date=20261124T090000Z
    &X-Amz-Expires=600
    &X-Amz-SignedHeaders=host
    &X-Amz-Signature=<chu-ky>
    [&X-Amz-Security-Token=...]
~~~

Các dòng được tách chỉ để dễ đọc; URL thực tế nằm trong **một chuỗi**. Các tham số quan trọng:

- `X-Amz-Algorithm`: thuật toán ký, thường `AWS4-HMAC-SHA256`.
- `X-Amz-Credential`: định danh thông tin ký và phạm vi ngày/Region/service. Đây **không phải** secret access key.
- `X-Amz-Date`: thời điểm ký; kết hợp với `X-Amz-Expires` để xác định khoảng hiệu lực tối đa theo chữ ký.
- `X-Amz-Expires`: thời lượng chữ ký, tính bằng **giây**.
- `X-Amz-SignedHeaders`: tập các HTTP header được đưa vào chữ ký; client phải tuân thủ các giá trị đã ký.
- `X-Amz-Signature`: chữ ký được tính từ request đã canonicalize và khóa ký.
- `X-Amz-Security-Token`: xuất hiện khi người ký sử dụng **temporary credentials**; token này là thành phần của request đã ký.

Ví dụ là **giả lập**; không thể dùng để truy cập object. Chữ ký ràng buộc request vào **HTTP method, host/bucket, key, query và các header đã ký**. Nếu thay GET thành PUT, đổi key hoặc sửa header bắt buộc, S3 thường từ chối do signature không hợp lệ.

**Không coi URL là thông tin công khai.** Ai có một presigned URL còn hiệu lực thường có thể thực hiện hành động đã ký trong thời hạn cho phép; URL hoạt động giống một *bearer capability*, không yêu cầu người nhận phải đăng nhập tài khoản AWS.

## 2. Thời hạn của presigned URL thực sự được quyết định như thế nào?

Một sai lầm thường gặp là nghĩ `signatureDuration(Duration.ofHours(1))` đảm bảo URL hoạt động chính xác một giờ bất kể điều gì xảy ra. Quyền thực tế phụ thuộc **nhiều giới hạn đồng thời**:

1. **Khoảng hiệu lực ghi trong chữ ký:** `X-Amz-Date` và `X-Amz-Expires`; với presigned URL S3 ký bằng AWS Signature V4, thời hạn được hỗ trợ tối đa **7 ngày**.
2. **Thời hạn credentials:** nếu người ký dùng IAM role/STS/temporary credentials, URL không thể tiếp tục hoạt động sau khi credentials đó hết hạn, ngay cả khi `X-Amz-Expires` còn dài.
3. **Chính sách IAM, bucket policy và ràng buộc bổ sung:** explicit deny, giới hạn `s3:signatureAge`, điều kiện network hoặc quyền KMS có thể từ chối request trước hạn.
4. **Trạng thái tài nguyên:** object có thể bị xóa, thay version, đổi key hoặc bị ngăn đọc bởi chính sách; URL không có chức năng bảo đảm object luôn tồn tại.

~~~text
Thời gian ký: 09:00
SignatureDuration: 60 phút     → chữ ký hết hạn tối đa 10:00
Credentials của role hết hạn: 09:30
Bucket policy signatureAge: 10 phút → yêu cầu sau 09:10 bị từ chối

=> URL chỉ còn khả năng sử dụng trong khoảng phù hợp với CẢ BA.
   Trạng thái IAM, KMS, object cũng vẫn phải hợp lệ.
~~~

Thời hạn **không phải bộ hẹn giờ để S3 tự động xóa object**. Hết hạn chỉ làm request dùng URL cũ bị từ chối; dữ liệu vẫn được lưu và quản lý theo versioning, lifecycle và chính sách giữ dữ liệu.

### 2.1. URL GET/PUT có được dùng lại không?

Có thể. Trong thời hạn còn hiệu lực, một presigned GET URL có thể bị mở nhiều lần. Một presigned PUT URL cũng có thể bị gửi lại, và PUT vào **cùng object key** có thể thay đổi dữ liệu hiện hành hoặc tạo version mới nếu bucket bật versioning.

Vì thế, presigned URL **không mặc định là token sử dụng một lần**. Nếu nghiệp vụ chỉ được upload một lần, cần thêm kiểm soát như tạo key ngẫu nhiên riêng cho phiên upload, trạng thái `PENDING_UPLOAD → READY`, kiểm tra trước khi cấp URL, conditional write được ký khi tương thích, và dừng/không phát lại link sau khi hoàn tất.

### 2.2. URL có thể bị thu hồi ngay lập tức không?

Không tồn tại thao tác đơn giản kiểu `revoke URL by ID` cho một S3 presigned URL bất kỳ. Các lựa chọn phụ thuộc bài toán:

- Dùng **TTL ngắn** ngay từ lúc tạo URL, ví dụ 5–15 phút.
- Đặt bucket policy chặn chữ ký quá cũ bằng `s3:signatureAge`.
- Thay đổi quyền hoặc thêm explicit deny, thay/loại bỏ object, hoặc vô hiệu hóa credentials khi thích hợp; tác động có thể ảnh hưởng nhiều request khác.
- Với nghiệp vụ cần thu hồi quyền chính xác theo phiên/người dùng ở thời gian thực, cho backend kiểm tra mỗi request và **stream qua API**, hoặc dùng một cơ chế phân phối có kiểm soát riêng.

Chỉ xóa bản ghi link khỏi database **không làm URL đã cấp lập tức ngừng hoạt động**; S3 xác minh chữ ký/chính sách, không tự truy vấn database ứng dụng.

## 3. Chuẩn bị Spring Boot, S3Presigner và IAM

### 3.1. Dependency

Import BOM Spring Cloud AWS với phiên bản phù hợp Spring Boot và thêm starter S3:

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

`spring-cloud-aws.version` là Maven property phải được khai báo theo phiên bản tương thích của dự án. `spring-cloud-aws-starter-s3` giúp Spring Boot tích hợp cấu hình S3 và AWS SDK; các ví dụ sử dụng **`S3Presigner`** của AWS SDK v2.

~~~yaml
# application.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: ${S3_BUCKET_NAME}
    presigned:
      get-minutes: 10
      put-minutes: 5
~~~

`app.storage.*` là property ứng dụng tự định nghĩa, **không phải** cấu hình chuẩn của S3 starter. Region cần phù hợp Region chứa bucket. Các thời hạn chỉ là ví dụ; production phải chọn theo kích thước file, trải nghiệm mạng, chính sách và rủi ro.

### 3.2. Danh tính ký URL

Trong AWS, nên dùng **IAM role gắn với workload** (ECS task role, instance profile hoặc danh tính EKS phù hợp). Máy phát triển có thể dùng AWS CLI profile/SSO và credentials tạm thời. AWS SDK dùng **Default Credentials Provider Chain** nếu ứng dụng không override.

`S3Presigner` dùng credentials của principal ký URL. Principal phải có quyền cho thao tác được ký như `s3:GetObject` hoặc `s3:PutObject` trên object đích. Việc Spring Boot tự tạo được URL không đồng nghĩa S3 sẽ chấp nhận URL nếu principal thiếu quyền khi request được thực thi.

**Không lưu access key/secret key vào source, YAML hay response.** Response chỉ nên chứa URL cần dùng, thông tin thời hạn và các header người nhận phải gửi.

### 3.3. Bean `S3Presigner` cho ứng dụng Spring

Tùy phiên bản và cấu hình Spring Cloud AWS, `S3Presigner` có thể được auto-configure. Nếu dự án chưa có bean này, có thể khai báo bean dưới đây. `@ConditionalOnMissingBean` giúp tránh tạo bean thứ hai khi đã có bean tương ứng:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration(proxyBeanMethods = false)
public class S3PresignerConfiguration {

    @Bean
    @ConditionalOnMissingBean(S3Presigner.class)
    public S3Presigner s3Presigner(
            @Value("${spring.cloud.aws.region.static}") String region) {
        return S3Presigner.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~

Nếu ứng dụng đã được starter tạo `S3Presigner`, chỉ cần inject bean đó; không cần viết cấu hình bổ sung.

Ở môi trường test dùng S3-compatible emulator, presigner còn phải thống nhất **endpoint, addressing style, Region và credentials** với client sử dụng. Nếu chỉ đổi endpoint của `S3Client` mà quên `S3Presigner`, URL có thể được ký cho host khác và thất bại.

### 3.4. IAM policy giới hạn object key

Ví dụ role của backend chỉ được đọc tài liệu đã phát hành và upload vào vùng `incoming/`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadPublishedDocuments",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::training-private-docs/documents/*"
    },
    {
      "Sid": "UploadIncomingFiles",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::training-private-docs/incoming/*"
    }
  ]
}
~~~

Policy này là **identity-based policy** minh họa, không tự bao gồm bucket policy, permission boundaries, SCP hay KMS key policy. `s3:GetObject` và `s3:PutObject` gắn với **object ARN**, còn quyền LIST (nếu cần) gắn với **bucket ARN**. Chỉ cấp đúng các quyền ứng dụng phải sử dụng; backend tạo GET URL không cần có quyền DELETE.

IAM role của backend có thể truy cập toàn bộ `documents/*`, nhưng người dùng A **không mặc nhiên** có quyền đọc tài liệu của người dùng B. Quyền nghiệp vụ phải được kiểm tra trước mỗi lần phát URL.

## 4. Tạo presigned GET URL với AWS SDK v2

### 4.1. Service phát URL cho key đã được kiểm tra quyền

Ví dụ sau giả định tầng API đã kiểm tra người dùng được phép xem tài liệu và truyền vào **trustedKey** lấy từ database:

~~~java
import java.time.Duration;
import java.time.Instant;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;
import software.amazon.awssdk.services.s3.presigner.model.PresignedGetObjectRequest;

@Service
public class S3DownloadUrlService {
    private final S3Presigner presigner;
    private final String bucket;

    public S3DownloadUrlService(
            S3Presigner presigner,
            @Value("${app.storage.bucket}") String bucket) {
        this.presigner = presigner;
        this.bucket = bucket;
    }

    public record DownloadGrant(String url, Instant expiresAt) {}

    public DownloadGrant presignDownload(String trustedKey) {
        if (trustedKey == null
                || !trustedKey.startsWith("documents/")) {
            throw new IllegalArgumentException("Object key không hợp lệ");
        }

        GetObjectRequest get = GetObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build();

        GetObjectPresignRequest request = GetObjectPresignRequest.builder()
                .signatureDuration(Duration.ofMinutes(10))
                .getObjectRequest(get)
                .build();

        PresignedGetObjectRequest signed =
                presigner.presignGetObject(request);

        return new DownloadGrant(
                signed.url().toExternalForm(),
                signed.expiration());
    }
}
~~~

`presignGetObject` **tạo chữ ký và URL**; bản thân bước tạo URL không tải file từ S3. Object có thể không tồn tại hoặc bị từ chối khi người nhận sử dụng URL. `signed.expiration()` mô tả thời điểm hết hạn theo chữ ký; **temporary credentials hoặc chính sách** có thể làm URL hết hiệu lực sớm hơn.

Nếu muốn trình duyệt tải về với tên file hiển thị riêng, S3 GET hỗ trợ các thuộc tính override như `responseContentDisposition` khi tạo `GetObjectRequest`. Chỉ sử dụng filename đã chuẩn hóa để tránh header injection và nội dung sai lệch.

### 4.2. Kết nối với quyền truy cập nghiệp vụ

Một endpoint an toàn nhận **document ID** thay vì nhận key S3 tùy ý:

~~~java
// Mẫu phối hợp lớp API, các kiểu DocumentRecord và
// DocumentAuthorizationService là lớp nghiệp vụ của dự án.
@GetMapping("/api/documents/{documentId}/download-url")
public S3DownloadUrlService.DownloadGrant issueDownloadLink(
        @PathVariable java.util.UUID documentId,
        org.springframework.security.core.Authentication user) {

    DocumentRecord record =
            documentAuthorizationService.requireCanRead(
                    user, documentId);

    return s3DownloadUrlService.presignDownload(record.objectKey());
}
~~~

**Trình tự cần giữ:** xác thực user → tra documentId → kiểm owner/tenant/quyền nghiệp vụ → lấy key từ dữ liệu đã lưu → ký URL. Nếu controller chỉ nhận `?key=documents/tenants/other-user/...`, user có thể thử key của người khác và biến role có quyền rộng của backend thành đường đọc chéo tenant.

Với tài liệu nhạy cảm, thời hạn nên ngắn, có rate limit phát link, logging theo **document ID, user ID, action và request ID**. Không log nguyên URL vì query chứa chữ ký và token phiên.

### 4.3. Dùng URL GET ở client

~~~bash
# Dùng URL nguyên vẹn, bao gồm tất cả tham số truy vấn.
curl --fail --location --output invoice.pdf "$PRESIGNED_GET_URL"
~~~

Ký URL theo path/key và query chính xác; đừng tự thay đổi host, Region, tên object hay các tham số `X-Amz-*`. Với browser, chỉ cần điều hướng đến URL hoặc gọi fetch theo phương thức GET phù hợp. Nếu gọi `fetch` cross-origin và cần JavaScript đọc response, cấu hình CORS S3 phải cho phép origin và method tương ứng.

Một presigned GET URL dùng được cho một request GET hợp lệ đến object; **không** phải là URL để LIST bucket hoặc truy cập tất cả key cùng prefix.

## 5. Tạo presigned PUT URL cho phép client upload trực tiếp

### 5.1. Mô hình upload an toàn

Backend tạo một **key mới do server kiểm soát** cho mỗi phiên upload. Client chỉ nhận URL và những HTTP header đã được thỏa thuận:

~~~mermaid
sequenceDiagram
    actor U as Client
    participant API as Spring Boot API
    participant DB as Database nghiệp vụ
    participant S3 as S3 private bucket

    U->>API: POST /uploads/init (loại file, kích thước)
    API->>API: Authentication, quota, kiểm loại file
    API->>DB: Tạo PENDING_UPLOAD + key ngẫu nhiên
    API-->>U: Presigned PUT URL (5 phút), key, Content-Type
    U->>S3: PUT trực tiếp object với headers đã ký
    S3-->>U: HTTP 200 + ETag
    U->>API: POST /uploads/{id}/complete
    API->>S3: HEAD key + kiểm metadata/kích thước
    API->>DB: READY nếu hợp lệ; xử lý sai lệch
~~~

**Không đánh dấu tệp READY chỉ vì đã cấp URL.** Client có thể bỏ cuộc, mạng lỗi hoặc tải lên tệp khác với nội dung khai báo. Backend nên kiểm tra lại object và ràng buộc nó với phiên upload đã được lưu.

### 5.2. Service ký URL PUT

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

@Service
public class S3UploadUrlService {
    private static final Set<String> ALLOWED_TYPES = Set.of(
            "application/pdf", "image/png", "image/jpeg");

    private final S3Presigner presigner;
    private final String bucket;

    public S3UploadUrlService(
            S3Presigner presigner,
            @Value("${app.storage.bucket}") String bucket) {
        this.presigner = presigner;
        this.bucket = bucket;
    }

    public record UploadGrant(
            String objectKey,
            String url,
            Instant expiresAt,
            String contentType) {}

    public UploadGrant presignUpload(
            String trustedTenantId, String validatedContentType) {

        // Tenant ID phải do hệ thống xác thực lấy từ dữ liệu tin cậy.
        if (trustedTenantId == null
                || !trustedTenantId.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Tenant ID không hợp lệ");
        }
        if (!ALLOWED_TYPES.contains(validatedContentType)) {
            throw new IllegalArgumentException(
                    "Định dạng upload chưa được hỗ trợ");
        }

        // Không dùng originalFilename của client làm object key.
        String key = "incoming/" + trustedTenantId + "/"
                + UUID.randomUUID();

        PutObjectRequest put = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(validatedContentType)
                .build();

        PutObjectPresignRequest request =
                PutObjectPresignRequest.builder()
                        .signatureDuration(Duration.ofMinutes(5))
                        .putObjectRequest(put)
                        .build();

        PresignedPutObjectRequest signed =
                presigner.presignPutObject(request);

        return new UploadGrant(
                key,
                signed.url().toExternalForm(),
                signed.expiration(),
                validatedContentType);
    }
}
~~~

Ví dụ kiểm tra `Content-Type` theo allowlist **chưa kiểm tra nội dung thực**: client vẫn có thể gửi dữ liệu khác với loại khai báo. Sau upload, backend cần giới hạn kích thước, kiểm định định dạng hoặc quét file theo yêu cầu; với hệ thống xử lý tệp bên ngoài, nên để tệp mới ở trạng thái **quarantine/pending** cho đến khi được chấp nhận.

`signed.httpRequest().headers()` có thể được dùng để xem các header nằm trong HTTP request đã presign. Các header được ký phải được client gửi tương ứng; đặc biệt, nếu `Content-Type` tham gia chữ ký, client phải dùng đúng giá trị. Không tự tùy tiện thay đổi `x-amz-*` hoặc những header thuộc chữ ký.

### 5.3. Gửi PUT bằng curl

~~~bash
# URL phải được đặt trong dấu nháy vì query chứa ký tự &.
curl --fail --request PUT \
  --header "Content-Type: image/png" \
  --upload-file "./photo.png" \
  "$PRESIGNED_PUT_URL"
~~~

Lệnh trên chỉ hợp lệ khi URL đã được ký cho **`Content-Type: image/png`** (hoặc request ký không ràng buộc khác). Nếu presigner ký thêm header khác, client phải gửi đúng những header đó. Với browser, API nên trả về các thông tin cần thiết để JavaScript thiết lập header được phép, đồng thời cấu hình CORS tương ứng.

**Presigned PUT không tự giới hạn file size một cách đáng tin cậy** chỉ vì API trước đó nhận tham số `fileSize`. Muốn kiểm soát kích thước nghiêm ngặt, có thể dùng **presigned POST policy với điều kiện `content-length-range`** khi phù hợp, thiết kế quy trình upload qua backend/proxy có giới hạn hoặc kiểm tra kích thước thực sau upload rồi xóa/quarantine object vượt quota. Các cơ chế này có phạm vi và đánh đổi khác nhau.

### 5.4. URL PUT có ngăn ghi đè không?

Không mặc định. Nếu một URL PUT còn hạn được gửi lại đến **cùng bucket/key**, request có thể ghi đè nội dung hiện hành hoặc tạo phiên bản mới trong bucket bật versioning. Sử dụng key ngẫu nhiên riêng cho mỗi phiên upload giúp tránh va chạm giữa các phiên, nhưng **không ngăn việc gửi lại cùng URL**.

Đối với chính sách `create-only`, S3 có thể hỗ trợ **conditional write** với header `If-None-Match: *` ở PUT khi API/SDK và chế độ bucket phù hợp. Nếu dùng điều kiện này, header phải được đưa vào request/chữ ký đúng cách; client phải gửi lại header tương ứng. Không nên coi bước `HEAD rồi PUT` là cơ chế chống race condition, vì request khác có thể ghi object giữa hai bước.

Nếu cần đảm bảo file chỉ được xử lý một lần trong nghiệp vụ, hãy tạo phiên upload duy nhất và dùng trạng thái/idempotency ở database, bất kể URL S3 được gọi bao nhiêu lần.

## 6. Giới hạn quyền theo thời gian bằng bucket policy

Khi ứng dụng phát link, `signatureDuration` là lớp đầu tiên. Với dữ liệu quan trọng, có thể đặt thêm **giới hạn phía S3** để các URL ký quá cũ bị từ chối dù ứng dụng phát thời hạn dài hơn dự kiến.

### 6.1. Giới hạn tuổi chữ ký bằng `s3:signatureAge`

Ví dụ bucket policy bên dưới từ chối presigned GET/PUT URL sử dụng phương thức ký qua query string khi tuổi chữ ký lớn hơn **600.000 mili giây (10 phút)**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyStalePresignedObjectRequests",
      "Effect": "Deny",
      "Principal": "*",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::training-private-docs/*",
      "Condition": {
        "StringEquals": {
          "s3:authType": "REST-QUERY-STRING"
        },
        "NumericGreaterThan": {
          "s3:signatureAge": "600000"
        }
      }
    }
  ]
}
~~~

Ý nghĩa:

- `s3:signatureAge` là **tuổi chữ ký tính bằng mili giây**; không nhầm với `X-Amz-Expires` tính bằng giây.
- `s3:authType = REST-QUERY-STRING` giúp nhắm vào kiểu authentication dùng query string, thường là presigned URL, thay vì mọi request có chữ ký trong HTTP header.
- `Effect: Deny` là **explicit deny**, nên có thể chặn request dù IAM identity policy cho phép.
- Policy **không cấp** quyền GET/PUT. IAM principal vẫn cần các quyền phù hợp.
- Resource trong ví dụ bao phủ object của bucket minh họa. Trong ứng dụng thật nên giới hạn action/prefix và thử nghiệm kỹ để tránh ảnh hưởng luồng hợp lệ.

Ví dụ, app phát URL GET 30 phút nhưng policy trên từ chối URL có chữ ký cũ hơn 10 phút; TTL thực tế bị rút ngắn. Nếu app phát URL chỉ 5 phút, bucket policy 10 phút **không kéo dài** hiệu lực URL thành 10 phút.

### 6.2. Các điều kiện quyền truy cập khác

Trong một số mô hình có thể cân nhắc:

- **Network restrictions** như `aws:SourceIp` hoặc `aws:SourceVpce` trong policy, nếu luồng mạng cho phép. Với người dùng di động, IP có thể đổi giữa lúc nhận link và lúc sử dụng.
- **KMS key policy** cho bucket dùng SSE-KMS; role ký có quyền S3 nhưng thiếu quyền KMS cần thiết vẫn có thể thất bại.
- **Explicit deny** đối với public access hoặc các yêu cầu không thỏa điều kiện mã hóa.
- **Credentials rotation/session timeout** như một giới hạn gián tiếp của temporary credentials.

Đặc biệt, nếu bucket policy bắt buộc `aws:SourceVpce` cho mọi thao tác, trình duyệt trên Internet công khai thường **không đi qua VPC endpoint của AWS**, nên presigned URL có thể bị chặn dù chữ ký đúng. Cần thiết kế đường đi dữ liệu tương thích với chính sách network, chẳng hạn dùng backend/proxy trong VPC hoặc hạ tầng phân phối đã được cấp quyền phù hợp.

### 6.3. Tại sao không dùng ACL public?

Mở bucket/object public để người dùng tải một file thường tạo quyền rộng và khó kiểm soát hơn nhu cầu. Presigned URL cho phép thực thi hành động đã ký trong một khoảng thời gian cụ thể mà vẫn giữ bucket private. Trong mô hình S3 mới, Object Ownership `Bucket owner enforced` thường vô hiệu hóa ACL; không nên xây thiết kế dựa vào thay ACL từng object khi không cần thiết.

## 7. CORS và các lỗi do header khi upload từ browser

Truy cập S3 trực tiếp từ trang web là **cross-origin** khi domain frontend khác host S3. Trình duyệt áp dụng **Cross-Origin Resource Sharing (CORS)**, đặc biệt với PUT hoặc request có header tùy chỉnh.

Ví dụ cấu hình CORS cho bucket thử nghiệm:

~~~json
[
  {
    "AllowedOrigins": [
      "https://app.example.test"
    ],
    "AllowedMethods": [
      "GET",
      "PUT",
      "HEAD"
    ],
    "AllowedHeaders": [
      "Content-Type",
      "x-amz-*"
    ],
    "ExposeHeaders": [
      "ETag"
    ],
    "MaxAgeSeconds": 300
  }
]
~~~

**CORS không phải IAM policy.** Một request được browser cho phép về CORS vẫn phải có chữ ký hợp lệ và thỏa IAM/bucket policy. Ngược lại, URL ký đúng có thể dùng được qua curl nhưng browser bị chặn vì thiếu `AllowedOrigins`, `AllowedMethods` hoặc header cần thiết.

- Chỉ thêm các origin đã kiểm soát, không đặt wildcard rộng nếu ứng dụng yêu cầu phân tách môi trường.
- Browser upload PUT thường kích hoạt **preflight OPTIONS**; S3 đánh giá CORS dựa trên cấu hình bucket.
- Nếu muốn JavaScript đọc `ETag` của response để gửi bước hoàn tất/multipart, hãy cấu hình `ExposeHeaders` phù hợp.
- Khi client gửi header khác với những header đã ký (ví dụ Content-Type bị thay hoặc thêm/bỏ một `x-amz-*` bắt buộc), S3 có thể trả `SignatureDoesNotMatch`.
- Trình duyệt tự quản lý một số header như `Host`; không yêu cầu frontend đặt thủ công các header bị browser cấm. Hãy kiểm tra các signed header mà presigner thực sự yêu cầu.

Trong nhiều hệ thống, GET chỉ cần điều hướng browser đến URL; CORS trở thành vấn đề khi JavaScript cần truy cập trực tiếp response qua `fetch` hoặc upload PUT qua browser.

## 8. Kiểm tra hoàn tất, quota và bảo vệ dữ liệu

Presigned URL giải quyết vấn đề **ủy quyền một HTTP request**; nó không thay thế toàn bộ luồng quản lý file.

### 8.1. Mô hình trạng thái upload

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Uploading: Phát presigned URL
    Uploading --> Verifying: Client báo hoàn tất
    Verifying --> Ready: Kiểm kích thước/định dạng/quyền thành công
    Verifying --> Rejected: Dữ liệu không hợp lệ
    Pending --> Expired: Quá thời gian mà chưa hoàn tất
    Uploading --> Expired: Không có xác nhận đúng hạn
    Rejected --> Cleaned: Dọn object
    Expired --> Cleaned: Dọn object chưa xác nhận
    Ready --> [*]
~~~

Một cách quản lý ứng dụng:

1. **Initiate:** xác thực user, kiểm quota sơ bộ, sinh key ngẫu nhiên riêng, tạo bản ghi `PENDING` với `uploadId` nghiệp vụ.
2. **Sign:** cấp URL PUT thời hạn ngắn, chỉ cho phép bucket/key đã chọn và header phù hợp.
3. **Client uploads:** client tải trực tiếp đến S3, sau đó gửi `uploadId` nghiệp vụ để báo hoàn tất.
4. **Verify:** backend đối chiếu user/tenant, gọi `HeadObject` để kiểm kích thước và metadata; nếu cần thì phân tích byte thực hoặc quét nội dung trước khi đánh dấu `READY`.
5. **Expire/cleanup:** dọn object và bản ghi ở trạng thái chờ quá lâu; xử lý trường hợp người dùng bỏ ngang mà không báo backend.

**Lưu ý:** `HeadObject.contentType()` chỉ phản ánh metadata đã ghi, không chứng minh bytes thực là PDF/PNG/JPEG. Quét nội dung và giới hạn kích thước phải thực hiện theo yêu cầu bảo mật/chi phí của ứng dụng. Hãy tránh đưa object mới upload vào vùng public/được người khác truy cập trước khi hoàn tất kiểm tra.

### 8.2. Upload file lớn: presigned multipart

Một presigned PUT URL phù hợp file nhỏ/vừa khi có thể truyền một request. Với tệp lớn, có thể dùng **S3 multipart upload**:

1. Backend xác thực và gọi `CreateMultipartUpload` để nhận `uploadId` của S3.
2. Backend cấp presigned `UploadPart` URL tương ứng với **partNumber + uploadId + key**.
3. Client gửi từng part trực tiếp đến S3, lưu `ETag` trả về cho mỗi part.
4. Client yêu cầu backend hoàn tất; backend kiểm quyền, đối chiếu part và gọi `CompleteMultipartUpload`.
5. Nếu người dùng hủy hoặc upload không hoàn tất, backend gọi `AbortMultipartUpload` và đặt S3 Lifecycle rule dọn upload chưa hoàn thành.

~~~mermaid
flowchart LR
    B["Browser: chia file thành part"] -->|"Xin URL cho part 1..N"| A["Spring Boot API"]
    A -->|"Presign từng UploadPart"| B
    B -->|"PUT trực tiếp"| S["S3 bucket private"]
    B -->|"partNumber + ETag"| A
    A -->|"Complete sau kiểm tra"| S
~~~

Các phần của multipart có quy tắc riêng (kích thước tối thiểu 5 MiB trừ part cuối, giới hạn part và thứ tự khi Complete). Điều kiện quyền và thời hạn mỗi presigned part URL vẫn cần được kiểm soát. **Không cho phép client truyền một uploadId/key thuộc người khác để backend gọi Complete** mà không kiểm tra chủ sở hữu phiên upload.

### 8.3. Dữ liệu nhạy cảm trong URL và log

Presigned URL chứa **chữ ký và đôi khi cả session token** trong query string. Để giảm nguy cơ lộ dữ liệu:

- Chỉ trao URL qua HTTPS và cho người dùng đã được ứng dụng xác thực.
- Không ghi URL đầy đủ vào access log, analytics, tracing, lỗi frontend, ticket hỗ trợ hoặc thông báo chat.
- Không đặt URL vào trang hoặc nguồn bên thứ ba có thể gửi thông tin qua `Referer`; cân nhắc `Referrer-Policy` và quy tắc lưu trữ cache phù hợp.
- Không cho phép frontend gửi presigned URL lên một service không được ủy quyền để kiểm tra hoặc “rút gọn”.
- Không đưa token/secret/dữ liệu cá nhân vào object key hoặc user metadata.
- Giới hạn tần suất phát link và theo dõi bất thường (nhiều lần xin link, nhiều IP, upload thất bại lặp lại).

URL hết hạn làm giảm thời gian bị lợi dụng nếu bị lộ, nhưng không thay thế kiểm soát quyền trước lúc phát URL.

## 9. Xử lý lỗi presigned URL và kiểm thử

### 9.1. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `SignatureDoesNotMatch` | Method, host, path, query hoặc signed header khác request được ký | Kiểm tra URL nguyên vẹn, Content-Type, endpoint, encoding |
| `AccessDenied` (403) | IAM/bucket policy/KMS, signatureAge, expired credentials | Xem quyền người ký, explicit deny, KMS và thời gian |
| `Request has expired` / lỗi liên quan thời hạn | `X-Amz-Expires` đã qua hoặc signatureAge policy chặn | Kiểm tra thời điểm ký, TTL và đồng hồ hệ thống |
| Lỗi clock skew hoặc chữ ký ở tương lai | Đồng hồ máy ký/khách lệch lớn, dùng ngày ký sai | Đồng bộ đồng hồ hệ thống, SDK signer/Region |
| Browser báo CORS nhưng curl chạy được | S3 CORS thiếu origin/method/header | Kiểm tra preflight OPTIONS và cấu hình CORS bucket |
| GET trả 404/403 | Key không tồn tại hoặc quyền bị chặn | Đối chiếu key trong database; HEAD theo role hợp lệ nếu cần |
| PUT thành công nhưng backend chưa thấy READY | Client chưa gọi complete hoặc backend chưa xác minh | Kiểm trạng thái PENDING, HEAD object, retry nghiệp vụ |
| URL hết hạn trước dự kiến | IAM role credentials hết hạn, bucket policy chặn sớm | Kiểm session credentials, `s3:signatureAge` |
| URL trỏ sai host hoặc Region | Presigner và bucket khác Region, custom endpoint lệch | Kiểm bean `S3Presigner`, Region, bucket endpoint |
| Upload vượt quota | URL PUT không tự thực thi hạn mức nghiệp vụ | POST policy phù hợp hoặc xác minh/hủy dữ liệu sau upload |

**403 không có một nguyên nhân duy nhất.** Nếu object không tồn tại, S3 có thể trả 404 khi caller có quyền `s3:ListBucket`, hoặc 403 nếu không có quyền này. Không dùng một lỗi HTTP đơn lẻ để suy đoán chắc chắn object tồn tại hay không.

### 9.2. Kiểm thử tích hợp trong AWS sandbox

Có thể chia kiểm thử thành ba lớp:

- **Unit test:** mock `S3Presigner` và authorization service để xác minh hệ thống chỉ ký key đã được phép, TTL được giới hạn, method GET/PUT đúng và không phát URL khi user bị từ chối.
- **Integration test với emulator:** kiểm luồng ký URL, PUT/GET, Content-Type, CORS và endpoint khi emulator hỗ trợ. Emulator không nhất thiết phản ánh chính xác IAM, KMS, signatureAge hoặc thời hạn STS.
- **AWS sandbox:** thử bucket private, IAM role thật, policy `s3:signatureAge`, temporary credentials, SSE-KMS nếu có, CORS browser và các trường hợp hết hạn.

Kịch bản gợi ý:

1. Cấp presigned GET URL có TTL ngắn cho một object kiểm thử mà caller được phép đọc; xác nhận HTTP GET thành công và byte khớp.
2. Gọi GET với URL đã **đổi key**, đổi method hoặc sửa query; xác nhận S3 từ chối chữ ký.
3. Cấp presigned PUT URL có Content-Type đã thỏa thuận; thử PUT khớp header rồi thử PUT với header không khớp chữ ký.
4. Trong sandbox có quyền kiểm soát, sử dụng TTL ngắn để kiểm chứng request sau hết hạn bị từ chối; không cần đợi nhiều giờ cho môi trường học.
5. Kiểm tra policy `s3:signatureAge` chặn URL cũ hơn ngưỡng ngay cả khi `signatureDuration` dài hơn.
6. Thử quyền user A với document của user B: **API không được phát URL** cho user A.
7. Kiểm tra tình huống PUT thành công nhưng client không báo complete; bản ghi ở trạng thái chờ và được cleanup.
8. Kiểm tra GET/PUT trên browser với origin cho phép và origin không được phép; so sánh với curl để tách lỗi CORS khỏi lỗi chữ ký.
9. Đảm bảo log không chứa query `X-Amz-Signature` và `X-Amz-Security-Token`.

Chỉ thực hiện kiểm thử xóa, credential expiry hoặc policy deny trên bucket/role test riêng. Với production, nên dựa vào kết quả kiểm thử có kiểm soát và quan sát lỗi runtime hơn là cố ý làm gián đoạn credential hoặc policy đang phục vụ người dùng.

### 9.3. Tiêu chí để nghiệm thu tính năng

Một tính năng presigned URL có thể được xem là đủ sẵn sàng để đánh giá tiếp khi:

- Mọi lần phát URL đều gắn với user/tenant và document/upload ID đã được kiểm tra quyền.
- TTL được cấu hình, giới hạn ở backend và không vượt thời gian credentials/policy cho phép.
- Method, key, Content-Type và các header được ký được kiểm tra nhất quán giữa API và client.
- Bucket còn private; IAM role chỉ được truy cập đúng prefix/operation cần thiết.
- Upload có quy trình xác minh sau khi hoàn tất và cleanup trạng thái chờ.
- CORS chỉ cho origin cần thiết; URL ký đầy đủ không bị ghi vào log.
- Có test cho expired URL, replay PUT, authorization failure, lệch header và môi trường trình duyệt thực.

## 10. So sánh với Azure và Google Cloud

Module **SPRING_CLOUD_PROVIDER_INTEGRATION** còn sử dụng các dịch vụ managed của Azure và Google Cloud. Ý tưởng cấp quyền truy cập tạm thời cho client tương đồng, nhưng cách tạo chữ ký, điều kiện quyền và thời hạn khác nhau:

| Ý tưởng | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Link truy cập tạm thời | Presigned URL | **Shared Access Signature (SAS)** | **Signed URL** |
| SDK Java điển hình | `S3Presigner` (AWS SDK v2) | Azure Storage Blob SDK, SAS API | GCS Storage Java client, URL signing |
| Identity của backend | IAM role / SDK credentials | Managed identity / Azure Identity và quyền ký SAS thích hợp | Service account / signing credentials |
| Scope phổ biến | Method, bucket/key, headers, TTL | Resource, permissions, thời hạn, policy có thể áp dụng | HTTP method, bucket/object, TTL, signed headers |
| Giới hạn/quyền | IAM + bucket policy + signatureAge + STS | SAS permissions + time + resource/account/network settings | Google Cloud IAM + chữ ký + thời hạn/điều kiện provider |
| Browser CORS | CORS của S3 bucket | CORS của Blob service | CORS của Cloud Storage bucket |

Không nên viết một hàm đa cloud giả định tất cả provider đều chấp nhận cùng dạng query hoặc có giới hạn ngày giống nhau. Một interface nghiệp vụ có thể trừu tượng hóa:

~~~java
public interface TemporaryObjectAccessPort {
    TemporaryLink createDownloadLink(
            String trustedObjectId, java.time.Duration ttl);

    TemporaryLink createUploadLink(
            String uploadSessionId, java.time.Duration ttl);
}

public record TemporaryLink(
        String url,
        java.time.Instant expiresAt,
        java.util.Map<String, String> requiredHeaders) {}
~~~

Adapter AWS dùng `S3Presigner`; adapter Azure tạo SAS phù hợp; adapter GCP sử dụng cơ chế signed URL của Cloud Storage. Phần **authorization và quản lý session/tenant** nên nằm ở tầng nghiệp vụ dùng chung, còn giới hạn chữ ký, header, IAM/RBAC và thời hạn tối đa được xử lý ở adapter theo từng provider.

## 11. Thực hành và câu hỏi ôn tập

### Bài tập 1 — Tải xuống có thời hạn

Tạo bucket sandbox private và object PDF mẫu. Xây dựng endpoint Spring Boot nhận `documentId`, xác thực user và sinh presigned GET URL 60 giây. Dùng curl tải file trước và sau khi hết hạn, quan sát HTTP status. Giải thích vì sao file vẫn tồn tại trên S3 khi URL đã hết hạn.

### Bài tập 2 — Upload trực tiếp từ browser

Tạo endpoint `POST /uploads/init` phát presigned PUT URL 5 phút cho key UUID nằm dưới `incoming/`. Viết trang thử nghiệm dùng JavaScript `fetch` PUT một PNG. Cấu hình S3 CORS cho origin local cố định và `ExposeHeaders: ETag`. Sau upload, backend kiểm tra HEAD và chuyển trạng thái upload sang READY.

### Bài tập 3 — Header và chữ ký

Tạo URL PUT gắn `Content-Type: image/png`. Thử gửi lần lượt đúng Content-Type, Content-Type khác và đổi HTTP method. Ghi lại kết quả từ S3, đối chiếu với tập header thật sự được presigner ký.

### Bài tập 4 — IAM và giới hạn signature age

Trong bucket sandbox, cấu hình role chỉ có GET vào `documents/*` và PUT vào `incoming/*`. Thử ký GET cho key ngoài phạm vi, rồi sử dụng URL. Áp dụng bucket policy signatureAge 60 giây trên prefix test, tạo URL có TTL 10 phút và xác minh nó bị từ chối sau ngưỡng policy.

### Bài tập 5 — Threat modeling

Phân tích các tình huống: URL bị lộ trong log; người dùng truyền key tenant khác; client upload lại cùng URL; object vượt quota; temporary credentials hết hạn sớm; browser CORS bị từ chối. Với mỗi tình huống, chỉ ra tầng kiểm soát tương ứng: ứng dụng, IAM/bucket policy, S3 API, CORS hay giám sát.

### Câu hỏi tự kiểm tra

1. Presigned URL có làm bucket hoặc object thành public không?
2. Tại sao người không có tài khoản AWS vẫn có thể sử dụng một presigned GET URL hợp lệ?
3. Những phần nào của HTTP request được ràng buộc bởi chữ ký?
4. Thời hạn `X-Amz-Expires` khác gì thời hạn của credentials STS?
5. `s3:signatureAge` sử dụng đơn vị gì và có thể rút ngắn TTL như thế nào?
6. Vì sao URL PUT không mặc nhiên chỉ sử dụng một lần?
7. Tại sao một controller chỉ nhận object key từ client rồi ký URL là nguy hiểm?
8. Vì sao backend cần kiểm tra object sau khi client báo upload thành công?
9. Khi nào presigned POST policy thuận tiện hơn presigned PUT để kiểm soát kích thước?
10. Vì sao curl có thể tải thành công nhưng browser báo lỗi CORS?
11. Những thông tin nào trong URL và response không được đưa vào log?
12. Nếu cần thu hồi quyền ngay lập tức theo user, vì sao một URL GET đã phát với TTL dài là bất lợi?
13. API cấp link tạm thời cho AWS, Azure và GCP nên giữ logic nào chung, logic nào thuộc adapter?

Kết thúc bài, người học phải có thể phát presigned **GET/PUT** URL từ Spring Boot, giới hạn thời gian và phạm vi quyền, kiểm tra chính xác luồng upload/download, bảo vệ dữ liệu private và đánh giá được rủi ro khi áp dụng cơ chế URL ký sẵn trên nhiều cloud provider.

