# Amazon S3: Cấu hình S3 client, S3Template và Spring Resource

## Mục tiêu học tập

Trong hệ thống Spring Boot tích hợp dịch vụ managed của AWS, Azure và Google Cloud, **Amazon S3** là lựa chọn phổ biến để lưu tài liệu, ảnh, báo cáo và dữ liệu dạng object. Bài này tập trung vào **cách Spring Boot kết nối và thao tác với S3 qua Spring Cloud AWS**, từ lớp AWS SDK đến các abstraction của Spring. Sau bài học, bạn có thể:

1. Thêm dependency và cấu hình AWS Region, credentials, bucket cho ứng dụng Spring Boot.
2. Giải thích cách Spring Cloud AWS tạo/inject `S3Client` và khi nào cần tự cấu hình client.
3. Viết một service dùng AWS SDK for Java v2 để PUT, GET và HEAD object.
4. Dùng `S3Template` để upload/download với ít mã lặp hơn.
5. Đọc object qua Spring `Resource` với địa chỉ `s3://bucket/key`.
6. Chọn abstraction phù hợp với streaming, metadata, kiểm thử và triển khai an toàn.

> **Phạm vi phiên bản:** Ví dụ sử dụng namespace `io.awspring.cloud` của **Spring Cloud AWS hiện đại**, cùng AWS SDK for Java **v2** (`software.amazon.awssdk`). Chọn phiên bản Spring Cloud AWS tương thích với Spring Boot đang dùng theo bảng tương thích của bản phát hành; các API và starter đời cũ có thể khác.

## 1. Ba mức abstraction để làm việc với S3

Spring Cloud AWS không thay thế S3 API. Nó kết nối cơ chế auto-configuration của Spring Boot với AWS SDK và cung cấp các lớp tiện ích.

~~~mermaid
flowchart TD
    APP["Spring Boot service / controller"]
    APP --> SDK["AWS SDK v2: S3Client"]
    APP --> TEMPLATE["Spring Cloud AWS: S3Template"]
    APP --> RESOURCE["Spring: Resource / ResourceLoader"]
    TEMPLATE --> SDK
    RESOURCE --> S3["S3 Resource integration"]
    S3 --> SDK
    SDK --> HTTP["AWS Signature V4 + HTTP"]
    HTTP --> CLOUD["Amazon S3 bucket / object"]
~~~

| Cách dùng | Mức độ chi tiết | Hợp với trường hợp |
| --- | --- | --- |
| `S3Client` | Tường minh request/response của AWS SDK, kiểm soát API và metadata | PUT/GET/HEAD/LIST, conditional request, thao tác S3 chuyên biệt |
| `S3Template` | Lớp tiện ích theo tư duy Spring, giảm boilerplate | Upload/download object thông thường trong service |
| Spring `Resource` | Giao diện đọc tài nguyên thống nhất, qua `s3://` | Đọc file cấu hình, template, nội dung tĩnh hoặc stream như các `Resource` khác |

Một ứng dụng có thể dùng cả ba cách. Ví dụ: `S3Template` cho upload thông thường, `S3Client` khi cần metadata/điều kiện nâng cao, `ResourceLoader` khi một thành phần chỉ yêu cầu giao diện `Resource`.

Để dễ hình dung, giả sử ứng dụng có bucket **`training-app-private-files`** tại Region `ap-southeast-1`, với key `documents/demo-001.txt`. Đây là tên minh họa; phải thay bằng bucket thật của môi trường.

## 2. Bổ sung Spring Cloud AWS S3 starter

### 2.1. Maven

Ở dự án dùng Maven, khai báo **BOM** để đồng bộ phiên bản các thư viện Spring Cloud AWS và thêm starter S3:

~~~xml
<properties>
    <!-- Chọn phiên bản tương thích với Spring Boot đang sử dụng. -->
    <spring-cloud-aws.version>PHIEN_BAN_TUONG_THICH</spring-cloud-aws.version>
</properties>

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

`PHIEN_BAN_TUONG_THICH` là **placeholder có chủ đích**, phải đổi thành phiên bản phát hành phù hợp trước khi build. Không trộn các artifact Spring Cloud AWS cũ (`org.springframework.cloud`/`com.amazonaws` ở các thế hệ trước) với mẫu code AWS SDK v2 trong bài này.

Starter S3 đưa vào ứng dụng cấu hình tự động liên quan đến S3 và các thành phần hỗ trợ như `S3Template`; nếu không có yêu cầu đặc biệt, không cần tự viết một `@Bean S3Client` ngay từ đầu.

### 2.2. Cấu hình Region và bucket

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
    prefix: documents/
~~~

Trong đó:

- `spring.cloud.aws.region.static` định nghĩa AWS Region cho client được Spring Cloud AWS cấu hình; giá trị phải tương thích với Region của bucket.
- `S3_BUCKET_NAME` là biến môi trường do môi trường chạy cung cấp; không đưa tên bucket cố định của production vào ví dụ có thể sao chép nhiều nơi.
- `app.storage.*` là **cấu hình riêng do ứng dụng đặt tên**, không phải thuộc tính mặc định của S3 starter.
- Nếu có nhiều bucket, khai báo các tên bucket theo mục đích, chẳng hạn `app.storage.private-bucket` và `app.storage.archive-bucket`, hoặc quản lý qua lớp `@ConfigurationProperties`.

Bucket cần tồn tại sẵn và danh tính của ứng dụng phải có quyền thích hợp. Starter **không tự biến một bucket private thành public**, cũng không mặc nhiên tạo bucket mỗi lần service khởi động.

### 2.3. Credentials: dùng chuỗi tìm kiếm mặc định của AWS SDK

AWS SDK v2 có **Default Credentials Provider Chain**, lấy credentials từ các nguồn được hỗ trợ như thông tin runtime (IAM role trên workload), biến môi trường, system properties hoặc AWS shared profile. Cách cấu hình cụ thể tùy môi trường:

| Môi trường | Cách cung cấp danh tính phù hợp | Ghi chú |
| --- | --- | --- |
| Máy phát triển | AWS CLI/SDK profile đã cấu hình, SSO/credentials tạm thời | Chạy qua profile cá nhân của môi trường thử nghiệm |
| ECS | IAM **task role** | Không nhầm task role với execution role |
| EC2 | IAM instance profile | Giới hạn quyền cho đúng service |
| EKS | IAM Roles for Service Accounts hoặc EKS Pod Identity (tùy triển khai) | Map quyền vào Kubernetes service account/pod thích hợp |
| CI/CD | OIDC federation và role ngắn hạn | Tránh lưu khóa AWS dài hạn trong pipeline |

Ví dụ chọn profile khi chạy local:

~~~powershell
$env:AWS_PROFILE = "dev-sandbox"
$env:S3_BUCKET_NAME = "training-app-private-files"
~~~

Đây là biến môi trường của **phiên PowerShell**, không phải secret. Profile `dev-sandbox` phải được cấu hình hợp lệ từ trước. Đừng đưa `accessKey`/`secretKey` thực vào `application.yml`, Git repository hay ví dụ trong tài liệu. Với production, ưu tiên role hoặc workload identity và chính sách quyền tối thiểu.

### 2.4. Cấp quyền IAM phù hợp với thao tác

Ví dụ policy gắn cho role của backend chỉ được liệt kê và đọc/ghi dưới prefix `documents/`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListDocumentKeys",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::training-app-private-files",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["documents/", "documents/*"]
        }
      }
    },
    {
      "Sid": "ReadWriteDocumentObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::training-app-private-files/documents/*"
    }
  ]
}
~~~

**Phân biệt bucket ARN và object ARN:** `s3:ListBucket` gắn với `arn:aws:s3:::bucket`, trong khi `s3:GetObject`/`s3:PutObject` cần `arn:aws:s3:::bucket/key` hoặc mẫu key. `s3:prefix` ở câu lệnh LIST chỉ lọc danh sách được phép liệt kê, **không hạn chế** quyền GET/PUT; việc giới hạn object nằm ở ARN của câu lệnh tiếp theo.

`s3:ListBucket` không bắt buộc cho mọi GET/PUT; chỉ cấp nếu ứng dụng thực sự cần LIST hoặc xử lý trường hợp cần phân biệt object không tồn tại. Nếu bucket dùng **SSE-KMS**, có thể cần thêm quyền trên KMS key và kiểm tra cả KMS key policy. Quyền IAM của backend cũng **không thay thế** kiểm tra người dùng/tenant tại tầng nghiệp vụ.

## 3. Dùng `S3Client` do Spring Cloud AWS cung cấp

### 3.1. Inject client và thao tác PUT / GET / HEAD

Khi starter và cấu hình phù hợp đã có, có thể inject `software.amazon.awssdk.services.s3.S3Client` vào constructor của Spring service.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class S3DocumentClientService {
    private final S3Client s3;
    private final String bucket;

    public S3DocumentClientService(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public String uploadSmallText(String text) {
        // Tên key do server tạo, không nhận từ tham số tự do của client.
        String key = "documents/" + UUID.randomUUID() + ".txt";
        byte[] body = text.getBytes(StandardCharsets.UTF_8);

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("text/plain; charset=UTF-8")
                .metadata(Map.of("source", "spring-boot"))
                .build();

        s3.putObject(request, RequestBody.fromBytes(body));
        return key;
    }

    public HeadObjectResponse inspect(String key) {
        requireDocumentKey(key);
        return s3.headObject(HeadObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build());
    }

    public void streamDownload(String key, OutputStream target)
            throws IOException {
        requireDocumentKey(key);
        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();

        try (ResponseInputStream<GetObjectResponse> source =
                     s3.getObject(request)) {
            source.transferTo(target);
        }
    }

    private static void requireDocumentKey(String key) {
        if (key == null || !key.startsWith("documents/")) {
            throw new IllegalArgumentException("Key ngoài prefix documents/");
        }
    }
}
~~~

**Cách đọc code:**

- `S3Client` là **SDK client đồng bộ** được Spring inject. Cần giữ và tái sử dụng client; không tạo một client mới cho mỗi request.
- `putObject` upload toàn bộ nội dung. `RequestBody.fromBytes` phù hợp **file nhỏ**; với object lớn, nên dùng streaming có quản lý kích thước, multipart upload, S3 Transfer Manager hoặc presigned URL.
- `headObject` chỉ trả metadata (ví dụ `contentLength()`, `contentType()`, `metadata()`) mà không tải body.
- `getObject` trả `ResponseInputStream` nên đoạn ví dụ dùng try-with-resources để đóng kết nối dù có lỗi. `transferTo` copy sang output stream nhận vào mà không cố đọc toàn bộ object thành một mảng byte.
- Kiểm tra `startsWith("documents/")` minh họa việc giới hạn dạng key; **chưa phải kiểm tra chủ sở hữu**. Trước khi gọi service, tầng API phải xác minh người dùng được phép truy cập object đó.
- `metadata(Map.of("source", "spring-boot"))` tạo user metadata; khi hiển thị ở HTTP, S3 sử dụng dạng header `x-amz-meta-source`.

Ví dụ gọi từ controller có thể map `invoiceId` sang key trong database sau khi kiểm tra quyền, rồi truyền **key đã xác thực** cho service. Tránh API nhận trực tiếp `?key=documents/tenant-khac/...`.

### 3.2. Khi nào cần tự cấu hình `S3Client`?

Auto-configuration phù hợp với đa số ứng dụng. Tự cung cấp bean `S3Client` là lựa chọn khi cần cấu hình SDK riêng như timeout, HTTP client, endpoint S3-compatible hoặc cơ chế xác thực không theo mặc định.

Ví dụ bean tùy biến timeout, vẫn dùng provider chain mặc định:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class CustomS3ClientConfig {
    @Bean
    public S3Client s3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .overrideConfiguration(ClientOverrideConfiguration.builder()
                        .apiCallTimeout(Duration.ofSeconds(30))
                        .build())
                .build();
    }
}
~~~

Đây là **phương án thay cho auto-configured `S3Client`**, không nhất thiết phải thêm vào ứng dụng bình thường. Khi tự tạo bean như trên, bạn chịu trách nhiệm đồng bộ Region/credentials/endpoint với cấu hình còn lại. Nếu cần nhiều client cho nhiều mục đích, đặt bean name/`@Qualifier` rõ ràng để tránh inject nhầm. Kiểm tra cấu hình cụ thể theo phiên bản Spring Cloud AWS đang sử dụng khi cần tùy chỉnh nâng cao.

**Lưu ý về credential provider:** `DefaultCredentialsProvider` không có quyền tự sinh credentials. Nếu không tìm thấy danh tính hợp lệ, lời gọi S3 sẽ thất bại dù Spring đã khởi động thành công.

## 4. Dùng `S3Template`: API đơn giản theo phong cách Spring

`io.awspring.cloud.s3.S3Template` là abstraction hỗ trợ các thao tác S3 thường gặp. Starter S3 có thể auto-configure `S3Template` dựa trên AWS SDK và cấu hình hiện có.

### 4.1. Upload/download bằng `S3Template`

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import io.awspring.cloud.s3.S3Template;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class S3TemplateDocumentService {
    private final S3Template s3Template;
    private final String bucket;

    public S3TemplateDocumentService(
            S3Template s3Template,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3Template = s3Template;
        this.bucket = bucket;
    }

    public void upload(String key, InputStream source) {
        requireDocumentKey(key);
        s3Template.upload(bucket, key, source);
    }

    public void downloadTo(String key, OutputStream destination)
            throws IOException {
        requireDocumentKey(key);

        Resource resource = s3Template.download(bucket, key);
        try (InputStream source = resource.getInputStream()) {
            source.transferTo(destination);
        }
    }

    private static void requireDocumentKey(String key) {
        if (key == null || !key.startsWith("documents/")) {
            throw new IllegalArgumentException("Key không hợp lệ");
        }
    }
}
~~~

Ở đây:

1. `s3Template.upload(bucket, key, InputStream)` dùng stream dữ liệu đầu vào. Chủ sở hữu stream và thời điểm đóng stream phải được quy định rõ ở **mã gọi method**; với ví dụ này, caller chịu trách nhiệm đóng `source` sau khi upload xong.
2. `s3Template.download(bucket, key)` trả về abstraction tài nguyên có thể đọc. Mã dùng `getInputStream()` để chuyển dữ liệu sang `OutputStream`.
3. Cách dùng này ngắn hơn SDK vì không phải tạo `PutObjectRequest`/`GetObjectRequest` cho từng thao tác.
4. Khi cần điều kiện ghi (`If-None-Match`), kiểm soát checksum, tagging, metadata đặc biệt hoặc API mà `S3Template` không cung cấp trực tiếp, dùng `S3Client` (hoặc API thích hợp khác) sẽ rõ ràng hơn.

**Quan trọng:** `InputStream` không tự trở thành dữ liệu đã được validate. Controller/service vẫn phải giới hạn kích thước, định dạng thực, quyền nghiệp vụ và số luồng upload đồng thời. Không nên để một request HTTP tự do quyết định bucket hoặc key.

### 4.2. Cần metadata riêng thì sao?

Ví dụ `S3Client` đặt `Content-Type` và user metadata rất rõ ràng trong `PutObjectRequest`. `S3Template` có hỗ trợ API gắn metadata tùy phiên bản, nhưng các overload cụ thể có thể khác giữa các bản Spring Cloud AWS. Nếu bài toán yêu cầu kiểm soát metadata chính xác hoặc các tùy chọn S3 ít gặp, dùng `S3Client` như mục 3 là cách minh họa ít mơ hồ hơn.

Một quy tắc thiết kế thực dụng:

- Chọn `S3Template` cho *use case* đọc/ghi object thông thường.
- Chọn `S3Client` cho tính năng gắn với chi tiết request/response hoặc behavior cụ thể của S3.
- Có thể inject cả hai vào hai service riêng; tránh viết nhiều wrapper chỉ đổi tên method mà không đóng góp kiểm tra nghiệp vụ, quan sát lỗi hay chính sách.

## 5. Dùng Spring `Resource` để đọc đối tượng S3

Spring Framework cung cấp giao diện `org.springframework.core.io.Resource` để đọc tài nguyên từ classpath, filesystem, URL và các nguồn khác. Spring Cloud AWS tích hợp S3 vào cơ chế này, cho phép biểu diễn object bằng địa chỉ:

~~~text
s3://training-app-private-files/documents/demo-001.txt
      └──────── bucket ────────┘└─────── object key ────────┘
~~~

Địa chỉ `s3://...` là **resource location** theo giao thức S3, không phải URL HTTP public. Truy cập vẫn đi qua AWS SDK và quyền IAM của ứng dụng.

### 5.1. Đọc resource đã biết trước bằng `@Value`

Trong ứng dụng đã bật S3 resource integration, có thể inject một tài nguyên bằng địa chỉ cố định:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class WelcomeTextProvider {
    private final Resource welcomeText;

    public WelcomeTextProvider(
            @Value("s3://training-app-private-files/templates/welcome.txt")
            Resource welcomeText) {
        this.welcomeText = welcomeText;
    }

    public String loadText() throws IOException {
        try (var input = welcomeText.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
~~~

Ví dụ đọc một template **nhỏ**. Với file lớn, xử lý dòng/stream thay vì `readAllBytes()`. Việc inject `Resource` thường chỉ tạo **đối tượng đại diện cho vị trí tài nguyên**; nội dung thực tế được đọc khi gọi `getInputStream()`, nên lỗi credentials, quyền hoặc mạng vẫn có thể xuất hiện lúc đọc.

### 5.2. Địa chỉ động bằng `ResourceLoader`

Khi bucket/key được xác định trong runtime, dùng `ResourceLoader` thay vì chuỗi `@Value` cố định:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class S3ResourceReader {
    private final ResourceLoader resourceLoader;
    private final String bucket;

    public S3ResourceReader(
            ResourceLoader resourceLoader,
            @Value("${app.storage.bucket}") String bucket) {
        this.resourceLoader = resourceLoader;
        this.bucket = bucket;
    }

    public void copyTo(String trustedKey, OutputStream target)
            throws IOException {
        if (trustedKey == null
                || !trustedKey.startsWith("documents/")) {
            throw new IllegalArgumentException("Key ngoài vùng documents/");
        }

        Resource resource = resourceLoader.getResource(
                "s3://" + bucket + "/" + trustedKey);

        try (InputStream input = resource.getInputStream()) {
            input.transferTo(target);
        }
    }
}
~~~

Cách này hữu ích khi dịch vụ đã có API nhận `Resource` (ví dụ xử lý nội dung văn bản, đọc template, parse dữ liệu hoặc pipeline chuyển đổi file). Mã gọi không cần biết chi tiết `GetObjectRequest` để lấy stream.

**Điều kiện:** Phần phân giải giao thức `s3://` phải được starter/auto-configuration của Spring Cloud AWS hiện hành cung cấp và kích hoạt. Nếu resolver không được đăng ký, Spring có thể không nhận ra location này như tài nguyên S3. Khi đó kiểm tra dependency, version và auto-configuration; đừng xử lý bằng cách đổi ngẫu nhiên sang `https://` vì URL HTTP có cơ chế truy cập khác.

### 5.3. Giới hạn của `Resource`

Không coi `Resource` là một file local:

| Thao tác | Điểm cần lưu ý với S3 |
| --- | --- |
| `getInputStream()` | Có thể mở kết nối mạng, có độ trễ và lỗi S3; phải đóng stream |
| `exists()` hoặc `contentLength()` | Có thể cần gọi HEAD hoặc API mạng, không phải phép kiểm tra miễn phí |
| `getFile()` | Thường không áp dụng; S3 object không có `java.io.File` trên ổ đĩa ứng dụng |
| `getURL()` | Không bảo đảm tạo URL HTTPS công khai/có quyền truy cập |
| Đọc nhiều lần | Có thể tạo nhiều yêu cầu GET, kéo theo độ trễ và chi phí |
| Ghi | Chỉ dùng khả năng ghi nếu resource implementation/phiên bản đang dùng hỗ trợ; với upload rõ ràng, ưu tiên `S3Template` hoặc `S3Client` |

Nếu một framework yêu cầu `java.io.File`, phải cân nhắc tải object vào **tệp tạm** do ứng dụng quản lý, rồi dọn dẹp sau khi dùng. Cách đó phát sinh chi phí I/O/ổ đĩa và không còn là thao tác streaming thuần.

## 6. Chọn abstraction trong các tình huống thực tế

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| Backend upload ảnh nhỏ với metadata và `Content-Type` bắt buộc | `S3Client` | Cấu hình rõ thuộc tính `PutObjectRequest` |
| Service upload/download tài liệu theo key đã xác thực | `S3Template` | Mã ngắn gọn, tập trung vào use case |
| Công cụ đọc CSV/template qua giao diện chung `Resource` | `ResourceLoader` | Trừu tượng hóa nguồn đọc |
| Cần kiểm tra ETag/version, điều kiện PUT hoặc tagging | `S3Client` | Có đầy đủ mô hình request/response của AWS |
| File lớn qua trình duyệt | Presigned URL hoặc giải pháp multipart/transfer phù hợp | Giảm gánh nặng truyền dữ liệu và bộ nhớ cho backend |
| Service xử lý hàng loạt | Client tái sử dụng + giới hạn đồng thời + phân trang | Tránh tạo client cho mỗi object và tránh tải hết listing vào RAM |

Một luồng ứng dụng quản lý chứng từ có thể được tổ chức như sau:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant API as Spring Boot API
    participant DB as Database nghiệp vụ
    participant S3 as S3 bucket private

    User->>API: Yêu cầu tải chứng từ #42
    API->>DB: Kiểm tra người dùng và lấy key
    DB-->>API: Key thuộc quyền truy cập
    API->>S3: S3Client / S3Template / Resource GET
    S3-->>API: Stream nội dung object
    API-->>User: Stream chứng từ
~~~

Ở bước tìm key, backend phải kiểm tra quyền theo user/tenant. Việc S3 role có `s3:GetObject` không tự quyết định người dùng ứng dụng có được xem tài liệu nào.

## 7. Những lỗi hay gặp khi cấu hình

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không tạo được bean `S3Client` hoặc `S3Template` | Thiếu starter, version không tương thích, autoconfiguration bị tắt | Kiểm tra dependency và cấu hình Spring Boot |
| `Unable to load credentials` | SDK không tìm thấy profile/role/token hợp lệ | Kiểm tra danh tính runtime; tránh thêm khóa thật vào source |
| `AccessDenied` (403) | IAM/bucket policy/permission boundary/SCP/KMS hoặc điều kiện quyền | Đối chiếu action, ARN bucket/object, explicit deny và KMS |
| `NoSuchKey` (404) | Sai bucket/key hoặc object đã bị xóa | Log bucket/key đã được làm sạch dữ liệu nhạy cảm; kiểm tra key chính xác, phân biệt hoa thường |
| Sai Region, redirect hoặc `PermanentRedirect` | Client gửi request sang Region không khớp | Kiểm tra Region thực của bucket và cấu hình client |
| `getResource("s3://...")` không đọc được S3 | Thiếu S3 resource resolver hoặc nhầm version | Kiểm tra starter, auto-configuration và dạng location |
| `OutOfMemoryError` khi upload/download | Dùng `byte[]`/`readAllBytes` với object lớn | Stream, multipart/transfer, hạn chế kích thước và đồng thời |
| Download chậm/ngắt giữa chừng | Timeout, mạng, connection pool, mở nhiều stream | Tái sử dụng client, đóng response, cấu hình timeout/retry phù hợp |
| File được lưu nhưng browser xử lý sai | `Content-Type`/`Content-Disposition` không phù hợp | Đặt metadata theo định dạng thực đã kiểm tra |
| Nhận 403 khi HEAD key không tồn tại | Thiếu `s3:ListBucket` có thể khiến S3 trả 403 thay vì 404 | Không kết luận rằng object chắc chắn tồn tại chỉ dựa trên 403 |

### Phân biệt lỗi khởi động và lỗi khi gọi S3

Tạo được bean `S3Client` **không chứng minh** ứng dụng có quyền truy cập bucket. Nhiều lỗi chỉ xảy ra khi gọi `getObject`, `headObject` hoặc `putObject`. Vì vậy nên có kiểm tra tích hợp thực sự gọi S3 trong môi trường thử nghiệm, ngoài kiểm tra Spring context khởi động.

Khi log lỗi, ghi **operation**, bucket/key theo chính sách bảo mật, request ID và AWS error code nếu có. Tránh log access key, token, presigned URL đầy đủ hoặc nội dung file nhạy cảm.

## 8. Kiểm thử tích hợp không phụ thuộc dữ liệu production

Một chiến lược có ba lớp:

1. **Unit test:** mock `S3Client` hoặc abstraction của ứng dụng để kiểm tra key được tạo, quyền nghiệp vụ được gọi trước GET và lỗi được xử lý. Mock không xác nhận chính sách IAM thực tế.
2. **Integration test local:** dùng S3-compatible emulator như LocalStack qua Testcontainers khi phù hợp. Cấu hình endpoint/profile riêng cho test; tạo bucket thử nghiệm, PUT/GET/HEAD một object và dọn tài nguyên.
3. **Integration test trên AWS sandbox:** chạy với IAM role và bucket test thực, xác minh quyền tối thiểu, mã hóa, Region, metadata, 403/404 và tình huống mạng. Emulator không thể tái hiện hoàn toàn chính sách IAM/KMS hoặc mọi hành vi managed của AWS.

Ví dụ cấu hình **chỉ cho profile test/local** nếu ứng dụng dùng S3 emulator tại `localhost:4566`:

~~~yaml
# Ví dụ cấu hình dành cho profile local, không dùng tại production
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      s3:
        endpoint: http://localhost:4566

app:
  storage:
    bucket: local-training-files
~~~

Endpoint thực tế của Testcontainers có thể là host/port động; test phải đưa địa chỉ đó vào cấu hình runtime. Emulator cũng có thể yêu cầu **path-style addressing** hoặc các thiết lập tương thích khác tùy phiên bản. Chỉ nên ép endpoint trong profile kiểm thử, tránh để ứng dụng production trỏ nhầm sang máy local.

**Checklist cho bài lab:** tạo bucket test → xác thực qua credentials giả lập/role sandbox → upload file nhỏ bằng `S3Client` → đọc metadata bằng HEAD → download bằng `S3Template` → đọc cùng object qua `ResourceLoader` → đối chiếu bytes → chạy negative case thiếu quyền trong AWS sandbox → dọn object.

## 9. Liên hệ với Azure và Google Cloud

Module **SPRING_CLOUD_PROVIDER_INTEGRATION** nhằm giúp người học tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud. Khi chuyển thiết kế object storage sang provider khác, có thể giữ **hợp đồng nghiệp vụ** như `ObjectStorageService.put(key, bytes)` hoặc `get(key)`, nhưng lớp adapter thay đổi.

| Khái niệm ứng dụng | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Client thao tác đối tượng | `S3Client` (AWS SDK v2) | Azure Storage Blob SDK client | Google Cloud Storage Java client |
| Abstraction Spring | `S3Template` và S3 `Resource` theo Spring Cloud AWS | Tích hợp tương ứng của Spring Cloud Azure | Tích hợp tương ứng của Spring Cloud GCP |
| Danh tính workload | IAM role / SDK credential chain | Managed Identity / Azure Identity | Service account / Application Default Credentials |
| Đơn vị chứa object | Bucket | Storage account + container | Bucket |
| Chia sẻ đường dẫn có giới hạn | Presigned URL | SAS | Signed URL |

Không nên sao chép nguyên property namespace hay hành vi phân quyền giữa các provider. Ví dụ, `s3://` là resource location dành cho S3 integration; một adapter Azure hoặc GCP phải dùng API/resource scheme do thư viện tương ứng hỗ trợ. So sánh provider nên tập trung vào **xác thực, quyền, metadata, consistency, chi phí và cách kiểm thử**, không chỉ vào tên method upload/download.

## 10. Bài tập vận dụng

**Bài tập A — Quan sát auto-configuration.** Tạo một ứng dụng Spring Boot có S3 starter, cấu hình `spring.cloud.aws.region.static` và `app.storage.bucket`. Inject `S3Client` vào service. Dùng profile phát triển với credentials hợp lệ để PUT một object thử nghiệm; ghi lại key và content type. Giải thích vì sao không phải tự khai báo bean `S3Client` cho use case cơ bản.

**Bài tập B — So sánh ba cách đọc.** Upload `documents/lab.txt` có nội dung `Hello S3`. Lần lượt tải về bằng:

- `S3Client.getObject(...).getInputStream()/ResponseInputStream`.
- `S3Template.download(...).getInputStream()`.
- `ResourceLoader.getResource("s3://bucket/documents/lab.txt").getInputStream()`.

Kiểm tra ba kết quả byte giống nhau và đóng tất cả input stream. Quan sát số request mạng nếu có tracing ở môi trường test.

**Bài tập C — Xử lý lỗi và quyền.** Với bucket thử nghiệm, thử truy cập một key không tồn tại và một key mà IAM role thiếu quyền GET. So sánh mã lỗi; giải thích tại sao `403` không đủ để kết luận object tồn tại. Kiểm tra `s3:GetObject` ở object ARN và `s3:ListBucket` ở bucket ARN.

**Bài tập D — Thiết kế service dùng nhiều cloud.** Viết interface nghiệp vụ `ObjectStoragePort` với `upload`, `download` và `inspectMetadata`. Phác thảo adapter AWS triển khai bằng `S3Client` và một adapter khác cho Azure hoặc GCP. Chỉ ra thuộc tính nào là chung giữa các cloud và thuộc tính nào phụ thuộc provider.

### Câu hỏi tự kiểm tra

1. Khác biệt giữa một bean `S3Client` do Spring Cloud AWS tự tạo và bean tự cấu hình là gì?
2. Vì sao phải chọn BOM Spring Cloud AWS tương thích với phiên bản Spring Boot?
3. Khi nào nên dùng `S3Template` thay vì trực tiếp gọi `S3Client`?
4. Vì sao có thể inject `Resource` thành công nhưng `getInputStream()` vẫn phát sinh lỗi?
5. Vì sao `Resource.getFile()` không phù hợp với một object nằm trên S3?
6. Làm sao đọc một object lớn mà không đưa toàn bộ nội dung vào RAM?
7. Vì sao policy IAM của backend không thay thế kiểm tra quyền của người dùng ở tầng controller/service?
8. Bạn sẽ kiểm tra hành vi credentials, IAM, metadata và Region khác nhau ra sao giữa emulator với AWS sandbox?

Sau bài này, người học cần có thể thiết lập kết nối Spring Boot → S3 bằng Spring Cloud AWS, chọn đúng `S3Client`/`S3Template`/`Resource` cho từng nhu cầu, xử lý stream đúng cách và tổ chức kiểm thử cũng như danh tính truy cập theo môi trường triển khai.

