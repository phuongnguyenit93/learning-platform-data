# SDK của dịch vụ đám mây hoặc kho đối tượng và quản lý vòng đời client trong Spring Boot

Trong ứng dụng Spring Boot, lưu hóa đơn PDF, ảnh sản phẩm, bản xuất báo cáo hoặc file đính kèm thường cần một **object store** như Amazon S3, Google Cloud Storage (GCS), Azure Blob Storage hoặc hệ thống tương thích một API tương ứng. SDK Java giúp gửi request tới dịch vụ, ký/xác thực yêu cầu, quản lý HTTP connection, retry và chuyển đổi dữ liệu. Tuy nhiên, **việc tạo client SDK đúng cách và kiểm soát vòng đời của nó** quan trọng không kém thao tác `putObject` hay `download`: tạo client mỗi request làm tiêu tốn pool kết nối; quên đóng stream có thể khiến pool bị cạn; quản lý credentials và shutdown sai khiến ứng dụng không thể dừng sạch hoặc bất ngờ mất quyền truy cập.

Bài thuộc chương **Thư viện bổ sung** của module **SPRING_BOOT_INTEGRATION**, nơi nghiên cứu tổ chức các luồng tích hợp Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration. Chúng ta xem object storage như một **phụ thuộc ngoài tiến trình** có hợp đồng, lỗi, giới hạn, chi phí và trạng thái riêng. Trọng tâm là thiết kế cấu hình, vòng đời SDK client, hợp đồng object/key, retry, idempotency, giao dịch database–storage, kiểm thử và khả năng quan sát khi đưa ứng dụng vào vận hành.

Các ví dụ chính sử dụng **Spring Boot 3.x và AWS SDK for Java 2.x (S3Client)**. Phần đối chiếu trình bày GCS Java client và Azure Blob Java SDK. API, phiên bản artifact, chiến lược retry và hành vi tài nguyên có thể thay đổi theo SDK và transport; phải đối chiếu tài liệu của **phiên bản đang dùng** trước khi triển khai.

## 1. Từ filesystem tới object storage: những thay đổi phải hiểu

Filesystem cung cấp đường dẫn và các thao tác quen thuộc: tạo file, đổi tên, đọc một đoạn, ghi đè, xóa. Object storage cung cấp các đối tượng được xác định bởi **bucket/container + object key/blob name**, cùng nội dung byte và metadata; thao tác thường qua API dịch vụ từ xa. Chìa khóa là hiểu đây không phải ổ đĩa POSIX được mount vào máy:

| Thành phần | S3 | GCS | Azure Blob |
| --- | --- | --- | --- |
| Không gian lưu | Bucket | Bucket | Container trong storage account |
| Danh tính nội dung | Object key | Object name | Blob name |
| Java client chính | `S3Client`, `S3AsyncClient` | `Storage`, hoặc client API thế hệ khác tùy nhu cầu | `BlobServiceClient`, `BlobContainerClient`, `BlobClient` và biến thể async |
| Xác thực mặc định nên ưu tiên | AWS default credentials provider chain / workload role | Application Default Credentials (ADC) / workload identity | `DefaultAzureCredential` / managed identity |
| SDK quản lý kết nối | S3 service client với HTTP transport/pool | Transport được chọn trong library | HTTP pipeline/client do Azure SDK sử dụng |
| Kiểm soát ghi đồng thời | Conditional request, ETag, version ID | Generation/metageneration preconditions | ETag, request conditions, leases/versioning theo API |

Các object key như `invoices/2026/11/INV-1042.pdf` có dấu `/` nhưng thường chỉ là **tên logic**, không có bảo đảm đây là cấu trúc thư mục vật lý. Quy trình liệt kê theo prefix và delimiter có thể tạo cảm giác giống folder. Đừng lưu object bằng đường dẫn cục bộ rồi giả định `rename`, `append`, `fsync` hoặc khóa file có cùng ý nghĩa trên mọi nhà cung cấp.

### Ví dụ một luồng tích hợp thực tế

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as invoice-service (Spring Boot)
    participant DB as SQL database
    participant S as Object store
    participant B as Message broker

    U->>A: Yêu cầu tạo hóa đơn
    A->>DB: Ghi job trạng thái PENDING + outbox
    DB-->>A: Commit
    A->>S: Upload PDF đến key bất biến
    S-->>A: Object metadata / version / checksum
    A->>DB: Cập nhật job READY + object key
    A->>B: Publish InvoiceReady (qua outbox)
    A-->>U: URL tải hoặc mã tham chiếu
~~~

Đây là **luồng nghiệp vụ nhiều tài nguyên**: SQL, object storage và broker **không tự động nằm trong cùng một transaction**. Phải định nghĩa chuyện gì xảy ra khi upload thành công nhưng ghi SQL thất bại, hay khi SQL đã commit còn upload chưa thực hiện.

## 2. Phân biệt ba vòng đời khác nhau

Cụm từ “lifecycle” có ít nhất ba nghĩa trong tích hợp cloud SDK:

1. **Vòng đời SDK client**: thời điểm tạo, tái sử dụng, cấp tài nguyên HTTP, refresh credentials và đóng client khi ứng dụng dừng.
2. **Vòng đời yêu cầu truyền dữ liệu**: mở request/stream, giới hạn timeout, xử lý retry, giải phóng response body/connection sau khi đọc hoặc hủy.
3. **Vòng đời object trong kho**: tạo, cập nhật phiên bản, chuyển storage class, lưu giữ, hết hạn, xóa và khôi phục theo chính sách bucket/container.

Bài này đặt trọng tâm vào (1), nhưng một client được đóng đúng không giải quyết rò rỉ stream ở (2) hay object tồn tại vô hạn ở (3).

~~~mermaid
flowchart TD
    APP["Spring Boot ApplicationContext"] --> CLIENT["Singleton SDK Client"]
    CLIENT --> POOL["HTTP pool / threads / credential provider"]
    CLIENT --> REQ1["Upload request"]
    CLIENT --> REQ2["Download request"]
    REQ2 --> STREAM["ResponseInputStream"]
    STREAM -->|"Đóng trong finally/try-with-resources"| RELEASE["Trả/giải phóng HTTP connection"]
    APP -->|"Shutdown -> close()"| STOP["Client release resources"]
    REQ1 --> OBJECT["Object trong bucket/container"]
    OBJECT --> POLICY["Lifecycle rule, retention, versioning"]
~~~

**Không được nhầm lẫn:** gọi `close()` lên client lúc shutdown không xóa object, và xóa object không giải phóng một `ResponseInputStream` đang mở trong tiến trình.

## 3. Chọn SDK, dependency và cách quản lý version

Ứng dụng không nhất thiết cần một “cloud starter” để dùng SDK. Có thể khai báo SDK Java chính thức và tích hợp qua Spring `@Bean`. Những starter như Spring Cloud AWS, Spring Cloud GCP hoặc Spring Cloud Azure có thể thêm auto-configuration, cấu hình properties và các adapter khác; khi chọn starter, phải xác minh version compatibility với Spring Boot và tránh khai báo hai client cùng vai trò ngoài chủ đích.

### AWS SDK for Java 2.x

Với Maven, dùng AWS SDK BOM để thống nhất phiên bản giữa `s3`, `sts` và các module AWS khác:

~~~xml
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
</dependencies>
~~~

`aws.sdk.version` là property phải được dự án xác định. Tùy transport đã chọn, có thể cần khai báo module HTTP client tương ứng, ví dụ Apache HTTP client cho đồng bộ hoặc Netty NIO cho bất đồng bộ. Không nên trộn SDK v1 `com.amazonaws.*` với SDK v2 `software.amazon.awssdk.*` trong cùng adapter mà không có lý do và kế hoạch nâng cấp rõ ràng.

### Google Cloud Storage và Azure Blob

Các dependency điển hình:

~~~xml
<!-- GCS: đồng bộ các phiên bản bằng google-cloud-libraries-bom
     do dự án quản lý, sau đó thêm module chính. -->
<dependency>
  <groupId>com.google.cloud</groupId>
  <artifactId>google-cloud-storage</artifactId>
</dependency>

<!-- Azure: quản lý phiên bản bằng azure-sdk-bom được kiểm thử
     cùng Azure Identity. -->
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-storage-blob</artifactId>
</dependency>
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-identity</artifactId>
</dependency>
~~~

Ví dụ trên chỉ minh họa **tọa độ module**, giả định dự án đã cấu hình dependency management phù hợp. Nếu không import BOM hoặc không chỉ định version riêng, Maven sẽ không tự suy ra version từ Spring Boot cho mọi thư viện cloud. Nên khóa và kiểm tra dependency tree, đặc biệt khi SDK chia sẻ Netty, Reactor, gRPC, Jackson hoặc OpenTelemetry với ứng dụng.

### Chọn sync hay async?

| Tiêu chí | Client đồng bộ | Client bất đồng bộ |
| --- | --- | --- |
| API thường gặp | `S3Client` | `S3AsyncClient` |
| Mô hình thực thi | Thread caller chờ I/O | Trả future/reactive publisher, callback/executor |
| Trong Spring MVC | Dễ tích hợp cho thao tác nhỏ và vừa | Có thể giảm block thread khi cần thông lượng lớn |
| Trong WebFlux | Gọi trực tiếp trên event loop gây block | Phù hợp hơn nếu transport và toàn pipeline non-blocking |
| Quản lý tài nguyên | HTTP pool, response stream | HTTP pool, event-loop/executor, body publisher/cancellation |
| Độ phức tạp | Dễ theo dõi call stack | Phải kiểm soát backpressure, buffer, timeout và cancellation |

Không chuyển `S3Client` blocking thành non-blocking chỉ bằng cách bọc nó trong `Mono.fromCallable()`. Khi dùng WebFlux mà vẫn cần SDK blocking, phải chuyển sang scheduler phù hợp, giới hạn concurrency và theo dõi số thread đang giữ. Với luồng upload lớn, cân nhắc client/transfer manager có hỗ trợ multipart hoặc async thực sự.

## 4. Thiết kế bean singleton cho S3Client

AWS SDK for Java 2.x khuyến nghị **tái sử dụng service client**, vì client thread-safe và giữ pool kết nối có chi phí khởi tạo. Mỗi HTTP request hay mỗi message broker **không nên** tạo một `S3Client.builder().build()` mới. Với Spring, bean singleton do ApplicationContext sở hữu là lựa chọn tự nhiên.

### 4.1. Cấu hình bằng @ConfigurationProperties

File `application.yml`:

~~~yaml
app:
  object-storage:
    bucket: invoice-documents
    region: ap-southeast-1
    max-download-bytes: 10485760  # 10 MiB nếu cần tải vào bộ nhớ

# Credentials do môi trường/runtime cung cấp; không ghi access key vào YAML.
~~~

Lớp cấu hình:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.object-storage")
public record ObjectStorageProperties(
        String bucket,
        String region,
        long maxDownloadBytes
) {
}
~~~

Nếu dùng record trong một source file độc lập, đặt đúng tên file Java và package của project. Đối với production, nên thêm Bean Validation cho bucket/region, giới hạn dung lượng và lỗi cấu hình ngay khi startup, tránh nhận message đầu tiên rồi mới phát hiện bucket name rỗng. Có thể chọn region qua AWS default region chain, nhưng nếu policy triển khai yêu cầu một region cụ thể thì khai báo rõ để ngăn request đi nhầm vùng.

### 4.2. Tạo và đóng client theo Spring lifecycle

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ObjectStorageProperties.class)
public class ObjectStorageClientConfiguration {

    @Bean(destroyMethod = "close")
    S3Client s3Client(ObjectStorageProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .overrideConfiguration(config -> config
                        .apiCallTimeout(Duration.ofSeconds(15))
                        .apiCallAttemptTimeout(Duration.ofSeconds(5)))
                .build();
    }
}
~~~

Điểm cần hiểu:

- `S3Client` là SDK client có thể chia sẻ giữa nhiều thread, không giữ per-request mutable state trong bean.
- Spring tạo **một singleton bean** cho cấu hình này và gọi `close()` khi ApplicationContext hủy bean. `destroyMethod = "close"` diễn đạt rõ quyền sở hữu tài nguyên.
- Ví dụ **không truyền static credentials**. AWS SDK dùng default credentials provider chain khi không chỉ định `credentialsProvider` và có cơ chế lấy credentials theo môi trường như profile dùng cho development, workload role/identity trên hạ tầng.
- `apiCallAttemptTimeout` giới hạn **một lần thử**; `apiCallTimeout` giới hạn **toàn bộ API call gồm nhiều attempt**. Chọn các số phù hợp SLA; 5/15 giây chỉ là ví dụ minh họa, chưa phải policy production.
- Không tạo bean `S3Client` thứ hai có cùng nhiệm vụ khi đã để starter tự cấu hình và inject client; nếu thật sự cần nhiều region/account, dùng bean name/`@Qualifier` để chọn đúng client.

Nếu dùng một `SdkHttpClient` riêng và chia sẻ nó cho nhiều AWS client, phải xác định **chủ sở hữu đóng HTTP client**. SDK không nhất thiết đóng một HTTP client đã được cung cấp từ bên ngoài qua `httpClient(...)`. `httpClientBuilder(...)` và `httpClient(...)` có ngữ nghĩa sở hữu tài nguyên khác nhau: cách quản lý nên theo hợp đồng SDK và được kiểm thử khi shutdown.

### 4.3. Đừng “làm nóng” client bằng thao tác đặc quyền

Không nên gọi `listBuckets()` hoặc `headBucket()` để kiểm tra sức khỏe mặc định trong mọi ứng dụng: principal của service có thể chỉ có quyền `s3:GetObject`/`s3:PutObject` cho một prefix, không được phép liệt kê bucket. Một probe như vậy có thể báo “unhealthy” dù thao tác thực tế hoàn toàn được cho phép.

Khi cần readiness theo external dependency, chọn thao tác kiểm tra tối thiểu **đúng với quyền và SLA**; phân biệt **startup validation** với **health probe chạy mỗi vài giây**, tránh tăng chi phí API và làm sập ứng dụng theo lỗi ngắn hạn của cloud.

## 5. Credentials, region, endpoint và phân quyền

SDK client thường cần bốn nhóm cấu hình: **identity**, **địa chỉ service/region**, **transport/TLS** và **chính sách request**.

### 5.1. Ưu tiên danh tính workload

Các cách cấp quyền nên ưu tiên:

- **AWS**: role của workload (ví dụ instance/container task hoặc workload identity tương ứng), default credentials chain; dùng profile cá nhân chỉ ở môi trường dev.
- **GCP**: Application Default Credentials với service account/workload identity được cấp quyền trên bucket/object cần thiết.
- **Azure**: `DefaultAzureCredential` và managed identity hoặc workload identity trên runtime được hỗ trợ, gán RBAC cho storage account/container phù hợp.
- **S3-compatible tự host**: endpoint/region/signing và credential theo cơ chế được nhà cung cấp triển khai; không mặc định dịch vụ tương thích mọi tính năng AWS S3.

Không commit access key, secret key, connection string chứa mật khẩu hoặc SAS token vào code, test fixture hay log. Không dùng quyền owner/admin trên toàn account để giải quyết tạm lỗi 403. Tách rõ quyền read/write/list/delete và prefix theo nghiệp vụ.

**Credentials rotation**: khả năng SDK tự làm mới credentials phụ thuộc provider đang dùng. Workload credential provider thường tự refresh; nếu bạn tự tạo `StaticCredentialsProvider` với key cứng, SDK không tự biết khi nào secret được thay thế. Đổi credentials có thể yêu cầu tạo provider/client mới theo cơ chế hỗ trợ hoặc restart có kiểm soát. Cần test rotation thực tế.

### 5.2. Endpoint override cho môi trường giả lập

Một số test dùng MinIO/LocalStack hoặc hệ thống S3-compatible. Khi đó có thể cần cấu hình:

~~~java
S3Client testClient = S3Client.builder()
        .region(Region.US_EAST_1)
        .endpointOverride(URI.create("http://localhost:9000"))
        .forcePathStyle(true)
        .credentialsProvider(
                StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test-key", "test-secret")))
        .build();
~~~

Các class `Region`, `URI`, `StaticCredentialsProvider` và `AwsBasicCredentials` đến từ JDK/AWS SDK. Đoạn này **chỉ là cấu hình test**, không khuyến khích HTTP plaintext và static key trong production. `forcePathStyle(true)` hữu dụng cho một số endpoint giả lập nhưng không nên suy ra phải bật cho mọi dịch vụ S3.

Khi endpoint bị override, signing region, host header, TLS certificate và đường route phải khớp. Đừng “giải” lỗi TLS bằng cách tắt kiểm tra chứng chỉ hoặc tin mọi hostname.

## 6. Adapter nghiệp vụ giúp tách SDK khỏi phần còn lại

Controller, RabbitMQ/Kafka listener hoặc Spring Integration flow không nên tự xây từng request SDK và tự xử lý lỗi cloud ở nhiều nơi. Tạo một **port/adapter** với hợp đồng ứng dụng rõ ràng:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.util.Map;

public interface DocumentStore {
    StoredDocument putSmall(
            String objectKey, byte[] content, String contentType);
    void downloadTo(String objectKey, OutputStream target)
            throws IOException;
    void delete(String objectKey);
}

public record StoredDocument(
        String bucket,
        String objectKey,
        String versionId,
        String eTag
) {
}
~~~

`objectKey` là định danh do ứng dụng kiểm soát, không nên nhận raw path từ user rồi ghép tùy ý. `versionId` và `eTag` giúp theo dõi kết quả nhưng **không thay cho checksum nghiệp vụ**. Không giả định ETag luôn là MD5 của payload, đặc biệt với multipart upload hoặc cấu hình mã hóa/triển khai khác.

S3 adapter cho các object nhỏ:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
public class S3DocumentStore implements DocumentStore {

    private static final int MAX_SMALL_UPLOAD = 8 * 1024 * 1024;

    private final S3Client s3;
    private final ObjectStorageProperties settings;

    public S3DocumentStore(
            S3Client s3, ObjectStorageProperties settings) {
        this.s3 = s3;
        this.settings = settings;
    }

    @Override
    public StoredDocument putSmall(
            String key, byte[] content, String contentType) {

        if (content.length > MAX_SMALL_UPLOAD) {
            throw new IllegalArgumentException(
                    "Dùng upload streaming/multipart cho file lớn");
        }

        var request = PutObjectRequest.builder()
                .bucket(settings.bucket())
                .key(key)
                .contentType(contentType)
                .build();

        var response = s3.putObject(
                request, RequestBody.fromBytes(content));

        return new StoredDocument(
                settings.bucket(), key,
                response.versionId(), response.eTag());
    }

    @Override
    public void downloadTo(String key, OutputStream target)
            throws IOException {

        var request = GetObjectRequest.builder()
                .bucket(settings.bucket())
                .key(key)
                .build();

        try (var input = s3.getObject(request)) {
            input.transferTo(target);
        }
    }

    @Override
    public void delete(String key) {
        s3.deleteObject(DeleteObjectRequest.builder()
                .bucket(settings.bucket())
                .key(key)
                .build());
    }
}
~~~

Ví dụ cố ý đơn giản để làm rõ **quyền sở hữu client và stream**:

- Adapter **không đóng `s3`** sau từng phương thức; Spring đóng singleton bean khi ứng dụng shutdown.
- `getObject()` trả stream gắn với response HTTP; `try-with-resources` đóng stream ở mọi nhánh xử lý, kể cả khi `transferTo` ném lỗi.
- `OutputStream target` do caller truyền vào. Adapter không tự đóng stream của caller; nơi tạo nó chịu trách nhiệm đóng hoặc flush theo hợp đồng.
- `putSmall` dùng `byte[]`, vì vậy chỉ phù hợp với file nhỏ đã có trong bộ nhớ. Giới hạn 8 MiB là lựa chọn của ví dụ, không phải giới hạn S3.
- `deleteObject` với bucket bật versioning có thể tạo **delete marker** thay vì xóa mọi version vĩnh viễn. Object lock/retention hoặc policy có thể cấm xóa. Không giả định “gọi delete thành công” đã xóa mọi byte và mọi phiên bản.
- Method đang chưa ánh xạ cloud exceptions sang domain exceptions và chưa giới hạn dữ liệu download. Các phần sau bổ sung policy cho sản phẩm thật.

### Chú ý khi đọc stream vào bộ nhớ

Nếu API thực sự cần `byte[]`, phải có **giới hạn kích thước**. Đọc trực tiếp toàn bộ object từ bucket vào heap chỉ dựa vào dữ liệu khách hàng cung cấp có thể gây `OutOfMemoryError`. Với response HTTP tải file, streaming và backpressure phù hợp hơn; khi file lớn hãy đi qua object store bằng URL được ký ngắn hạn nếu mô hình bảo mật cho phép.

Một cách đọc an toàn có thể kiểm tra `HeadObject` trước, nhưng độ dài đối tượng có thể thay đổi giữa HEAD và GET nếu key bị ghi đè. Do đó việc giới hạn byte thực sự được đọc vẫn cần diễn ra trong **vòng lặp streaming**, hoặc chỉ đọc một version/generation xác định.

## 7. Vòng đời HTTP response và multipart upload

Các lỗi tài nguyên thường xảy ra ở **request cụ thể** hơn là lúc tạo client.

### 7.1. Stream phải được tiêu thụ hoặc đóng

Với AWS `S3Client#getObject`, `ResponseInputStream<GetObjectResponse>` chiếm tài nguyên HTTP cho đến khi được đọc hết hoặc đóng. Nếu code chỉ đọc vài byte để nhận diện file rồi bỏ stream, connection có thể không trở lại pool hoặc phải bị hủy; khi tải tăng, caller khác bị chờ connection rảnh.

~~~java
try (var stream = s3.getObject(
        GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build())) {

    // Xử lý theo luồng, đóng stream tự động.
    stream.transferTo(destination);
}
~~~

Nếu downstream hủy tải HTTP giữa chừng, `try-with-resources` vẫn phải chạy và giải phóng stream. Với async client, quản lý cancellation của future/publisher, memory buffers, subscriber và event-loop cũng quan trọng như việc đóng `InputStream` đồng bộ.

### 7.2. Upload file lớn cần một chiến lược khác

Với sync API, `RequestBody.fromInputStream(input, contentLength)` cần **content length chính xác**. Nếu khai quá nhỏ có thể upload thiếu byte; khai quá lớn có thể block/chờ vô hạn hoặc thất bại. Khi đã có file trên đĩa tạm do server quản lý, API `RequestBody.fromFile(path)` để SDK có thể đọc nội dung file là lựa chọn đơn giản:

~~~java
var request = PutObjectRequest.builder()
        .bucket(bucket)
        .key(objectKey)
        .contentType("application/pdf")
        .build();

s3.putObject(request, RequestBody.fromFile(pdfPath));
~~~

`pdfPath` là một `java.nio.file.Path` trỏ tới file đã được kiểm tra về nguồn gốc, kích thước và quyền truy cập. File tạm cũng có lifecycle: tạo ở thư mục hạn chế quyền, xử lý thành công/thất bại, rồi xóa trong `finally` phù hợp.

Đối với object lớn, concurrency cao hoặc cần tiếp tục upload sau lỗi, cân nhắc **multipart upload và S3 Transfer Manager**. Multipart có thêm trạng thái upload ID, part number, ETag/checksum từng phần và bước complete. Nếu abandon multipart mà không abort/cleanup, dữ liệu part dang dở có thể vẫn chiếm chi phí lưu trữ. Bucket nên có chính sách dọn **incomplete multipart uploads** cùng với logic abort trên đường lỗi.

### 7.3. Không ghép tài nguyên vào global cache không giới hạn

Một service không nên cache hàng nghìn client theo tenant hoặc từng bucket nếu tất cả dùng cùng identity/region/transport. Cần phân biệt **client** và **request target**: thông thường một S3 client có thể thao tác với nhiều bucket cùng region/chính sách. Nếu multi-tenant cần identity/region khác nhau, dùng cache có giới hạn và cơ chế eviction/close an toàn; chú ý không đóng client đang được request dùng.

## 8. Timeout, retry và giới hạn tải

SDK thường có retry mặc định cho một số lỗi được coi là transient. Bật thêm `@Retryable`, `RetryTemplate`, Reactor `retryWhen` hoặc retry từ broker có thể **nhân số attempt** không chủ đích. Một request thất bại qua nhiều tầng có thể tạo hàng chục HTTP call thực tế.

### Các loại timeout không đồng nhất

| Tham số | Phạm vi | Nếu bỏ qua |
| --- | --- | --- |
| TCP connect timeout | Thời gian mở kết nối tới endpoint | Thread/call chờ connect quá lâu |
| TLS handshake timeout | Thời gian thương lượng TLS | Không phân biệt mạng chậm và certificate/handshake |
| Socket/read timeout | Khoảng chờ đọc/ghi ở HTTP transport | Một attempt treo lâu |
| API call attempt timeout | Một lần thử của SDK | Không kiểm soát chi phí mỗi retry |
| API call timeout | Toàn thao tác API, gồm retries/backoff | API upstream hết SLA khi SDK vẫn đang thử |
| Business deadline | Toàn luồng nghiệp vụ qua DB, object store và broker | Các dependency độc lập cộng dồn vượt giới hạn API |

Ví dụ phân bổ ngân sách: API tạo file cần kết thúc trong 10 giây; SDK có attempt timeout 3 giây, tổng API call timeout 7 giây, để lại thời gian cho validation/SQL/response. Các giá trị này chỉ minh họa; file lớn hoặc network cross-region cần ngân sách khác.

Một cấu hình client cấp thấp có thể khai báo HTTP timeout qua transport builder:

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.apache.ApacheHttpClient;

var client = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClientBuilder(
                ApacheHttpClient.builder()
                        .connectionTimeout(Duration.ofSeconds(2))
                        .socketTimeout(Duration.ofSeconds(4)))
        .overrideConfiguration(o -> o
                .apiCallAttemptTimeout(Duration.ofSeconds(6))
                .apiCallTimeout(Duration.ofSeconds(15)))
        .build();
~~~

Cần thêm artifact `software.amazon.awssdk:apache-client` nếu project chưa có. Đoạn ví dụ minh họa quan hệ timeout, không phải mặc định tối ưu: chọn các mốc phải dựa theo lưu lượng, response size, số lần retry và SLA. Với streaming download lớn, socket/read timeout cần phân biệt “đợi một đoạn dữ liệu” với thời gian tải toàn file.

### Phân loại lỗi và retry

| Kết quả/exception | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `404` / `NoSuchKeyException` | Key không tồn tại hoặc đã bị xóa | Xử lý not-found; không retry mù |
| `403 AccessDenied` | Không đủ quyền hoặc bị policy từ chối | Kiểm tra identity, bucket policy, KMS, network policy; không coi là key vắng mặt |
| `400` do sai request | Region/metadata/key/header/contract sai | Sửa caller/config; không retry vô hạn |
| `409 Conflict` hoặc `412 Precondition Failed` | Xung đột ghi có điều kiện / state thay đổi | Kiểm tra optimistic concurrency; không tự ghi đè |
| `429`/`503 SlowDown` hoặc một số `5xx` | Throttling, quá tải hoặc lỗi tạm thời | Retry giới hạn + exponential backoff/jitter |
| `SdkClientException` / network reset | Transport, DNS, TLS hoặc client-side | Phân loại nguyên nhân; retry chỉ khi thao tác an toàn |
| Timeout sau upload | Chưa biết server đã nhận/ghi object hay chưa | Kiểm tra key/version/checksum và cơ chế idempotency |
| Credentials expired/invalid | Identity chain/rotation lỗi | Điều tra refresh và quyền; không retry với token sai mãi |

Mã HTTP cụ thể, exception hierarchy và tính retryable phụ thuộc cloud SDK. Một số lệnh đọc S3 có thể trả `403` thay cho `404` khi principal không có quyền liệt kê/nhìn thấy đối tượng. **Không suy ra trạng thái tồn tại của object chỉ từ status 403.**

### Bulkhead và concurrency

HTTP pool, thread pool, server servlet thread, Reactor scheduler và số upload đồng thời đều là tài nguyên có hạn. Khi cloud service chậm, queue request nội bộ có thể dồn lên và làm hỏng cả API không liên quan. Áp dụng giới hạn:

- Số upload/download đồng thời và tổng byte in-flight.
- Dung lượng file/người dùng/tenant.
- Connection pool size và acquisition timeout.
- Số attempt retry và tổng ngân sách chờ.
- Số multipart upload được chạy cùng lúc.
- Giới hạn bộ nhớ/đĩa tạm và hàng đợi công việc.

Nếu muốn xử lý file nặng, đưa việc tạo PDF hoặc upload qua queue/job worker có backpressure, trạng thái và giám sát là lựa chọn thường dễ kiểm soát hơn để một HTTP request đồng bộ chờ vô hạn.

## 9. Ghi đè, đối soát và idempotency của object

Một `PUT` đến cùng object key thường có thể ghi đè nội dung hiện tại (phụ thuộc quyền và precondition), vì vậy **object key chính là một phần hợp đồng nghiệp vụ**.

Ví dụ lựa chọn key:

| Mẫu key | Đặc điểm | Cần lưu ý |
| --- | --- | --- |
| `orders/{orderId}/invoice.pdf` | Dễ tìm theo đơn hàng | Retry/ghi lại có thể overwrite; cần version/conditional write |
| `orders/{orderId}/invoices/{version}.pdf` | Có version nghiệp vụ | Quản lý dọn version cũ/retention |
| `documents/{documentId}/{sha256}.bin` | Gắn với nội dung bất biến | Metadata DB phải lưu documentId, hash, content type |
| `uploads/{uuid}` | Chống xung đột key ngẫu nhiên | Retry phải dùng **cùng UUID** để tránh tạo bản sao |

Đối với create-only, dùng **conditional write** mà provider hỗ trợ. S3 có khả năng đặt `If-None-Match: *` cho `PutObject` để tránh thay một key đã tồn tại, tùy khả năng SDK/API phiên bản. GCS có generation precondition như `doesNotExist()`; Azure có ETag/request conditions tương ứng. Cần xử lý phản hồi conflict/precondition như một kết quả nghiệp vụ có thể kiểm tra, không retry mù.

**ETag không nhất thiết bằng MD5 của object.** Khi cần đối soát nội dung, dùng checksum có thuật toán cụ thể được thỏa thuận và xác thực end-to-end, ví dụ SHA-256 trong metadata do hệ thống quản lý. Một timeout có thể xảy ra **sau khi** PUT hoàn tất trên server; retry với key ngẫu nhiên mới làm mất idempotency.

### State machine cho tài liệu

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> UPLOADING
    UPLOADING --> READY: upload confirmed + DB metadata saved
    UPLOADING --> RETRYABLE_FAILURE: timeout/5xx
    RETRYABLE_FAILURE --> UPLOADING: retry with same ID
    UPLOADING --> FAILED: unrecoverable + manual action
    READY --> DELETING: retention/legal policy allows
    DELETING --> DELETED: storage delete verified
~~~

Trạng thái `READY` nên chỉ có khi cả object và metadata nghiệp vụ đã nhất quán theo quy ước. Nếu upload đã hoàn tất nhưng cập nhật DB thất bại, cần reconciliation job tìm **orphan object**; nếu DB đánh dấu READY nhưng object bị xóa ngoài luồng, cần theo dõi inconsistency.

## 10. SQL transaction không bao trùm object store

Một vấn đề kinh điển:

~~~java
@Transactional
public void registerDocument(DocumentRequest request) {
    documentRepository.save(...);
    s3.putObject(...); // Lời gọi mạng ngoài database transaction.
}
~~~

`@Transactional` ở đây quản lý transaction SQL theo `PlatformTransactionManager`, **không biến PutObject thành một phần của cùng transaction ACID**. Nếu SQL rollback sau khi upload, object vẫn có thể tồn tại. Nếu SQL commit rồi upload lỗi, row có thể đã tồn tại nhưng file thiếu. Không nên giả định XA/2PC luôn khả thi với object store.

Một luồng quản lý rõ ràng hơn:

1. SQL ghi `documentId`, key bất biến, checksum kỳ vọng và trạng thái `PENDING` trong transaction; nếu xử lý async, ghi cả outbox event.
2. Worker nhận job, upload object; mọi lần retry giữ cùng document ID/key và có điều kiện ghi phù hợp.
3. Sau khi xác nhận upload, cập nhật SQL `READY` cùng version/ETag/checksum và phát sự kiện qua outbox.
4. Nếu lỗi transient, giữ trạng thái retryable và backoff; nếu lỗi dữ liệu/quyền vĩnh viễn, chuyển `FAILED` để xử lý.
5. Có reconciliation job dò `PENDING` quá lâu, object orphan và mismatch metadata; chỉ xóa theo chính sách retention.

Luồng này giống thiết kế tích hợp với broker khác: **at-least-once processing + idempotency + trạng thái bền vững**, không dựa vào exactly-once delivery. Đối với hóa đơn, hợp đồng dữ liệu còn phải xác định ai được đọc object và trong bao lâu.

## 11. Presigned URL và upload trực tiếp từ trình duyệt

Khi file lớn, phương án *browser → Spring Boot → object store* khiến ứng dụng trở thành proxy chuyển byte và tốn băng thông/connection. Có thể chuyển sang **presigned URL** hoặc signed upload policy:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Spring Boot API
    participant S as Object Store
    participant D as Metadata DB

    B->>A: Xin quyền upload file (size/type/business ID)
    A->>D: Lưu pending upload, random object key
    A-->>B: Presigned PUT URL có thời hạn
    B->>S: PUT trực tiếp qua TLS
    S-->>B: HTTP success + headers
    B->>A: Thông báo hoàn tất với documentId
    A->>S: HEAD/checksum/metadata để xác nhận
    A->>D: Đánh dấu READY sau khi xác minh
~~~

Với S3 SDK v2, dùng `S3Presigner` để ký request có thời hạn:

~~~java
import java.time.Duration;
import java.net.URL;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

public URL presignUpload(
        S3Presigner presigner, String bucket, String key) {

    var put = PutObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .contentType("application/pdf")
            .build();

    var signed = PutObjectPresignRequest.builder()
            .signatureDuration(Duration.ofMinutes(5))
            .putObjectRequest(put)
            .build();

    return presigner.presignPutObject(signed).url();
}
~~~

Tạo `S3Presigner` như một bean dùng chung với cấu hình region/credentials phù hợp và đóng theo vòng đời ứng dụng khi implementation yêu cầu `close()`:

~~~java
@Bean(destroyMethod = "close")
S3Presigner s3Presigner(ObjectStorageProperties properties) {
    return S3Presigner.builder()
            .region(Region.of(properties.region()))
            .build();
}
~~~

URL đã ký là một **bearer capability**: ai có URL thường có thể thực hiện thao tác được cho phép cho đến khi URL hết hạn và các giới hạn khác còn hiệu lực. Không ghi URL đầy đủ vào log, không dùng thời hạn quá dài, giới hạn key và policy theo user/tenant. Nếu request được ký kèm `Content-Type` hoặc header đặc biệt, browser phải gửi **cùng giá trị header đã ký**, nếu không có thể lỗi chữ ký.

Đừng coi việc browser gọi API “upload hoàn tất” là bằng chứng object hợp lệ. Backend cần kiểm tra kích thước, content type, object existence, checksum/metadata, tenant ownership và chống race với lần upload khác. Presigned upload không tự kiểm virus hay nội dung nguy hiểm; thêm scan/quarantine và chuyển READY sau khi đạt điều kiện an toàn.

## 12. So sánh vòng đời Java client giữa ba hệ sinh thái

Một quy tắc “mọi SDK client đều implements Closeable” là **không chính xác**. Phải xem loại client cụ thể có `close()` hay không, ai sở hữu HTTP transport và credential provider.

### 12.1. AWS S3: S3Client và S3Presigner

- `S3Client` và `S3AsyncClient` có lifecycle/`close()` của AWS SDK. Với Spring singleton, đóng khi ApplicationContext shutdown.
- `S3Presigner` nên dùng lại nếu phát URL thường xuyên; đóng khi bean bị hủy.
- `ResponseInputStream` từ mỗi `getObject` phải đóng **theo từng request**.
- HTTP client được SDK tạo và HTTP client được **truyền vào** có thể có khác biệt về ownership; hãy thiết kế bean resources rõ ràng.

### 12.2. Google Cloud Storage: ADC và Storage

Ví dụ tạo `Storage` từ default credentials/configuration:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GcsConfiguration {

    @Bean(destroyMethod = "close")
    Storage gcsStorage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Ví dụ dựa trên `com.google.cloud.storage.Storage` của Java library; bản hiện đại có API `close()` để giải phóng tài nguyên transport. Thực tế cách đóng có thể phụ thuộc transport và phiên bản, nên cần đối chiếu javadoc. Các client Google Cloud khác, nhất là lớp gRPC `*Client`, thường dùng `close()`/`shutdown()` và đôi khi cần chờ termination; đừng suy diễn lifecycle giữa các client chỉ vì đều mang tên Google Cloud.

Google ADC lấy credentials theo môi trường. Trong production, ưu tiên service account/workload identity với quyền tối thiểu trên bucket; tránh phát tán JSON service account key.

Khi ghi GCS, có thể sử dụng generation precondition để tránh overwrite:

~~~java
BlobInfo info = BlobInfo.newBuilder(
        BlobId.of(bucketName, objectName))
        .setContentType("application/pdf")
        .build();

storage.create(
        info,
        payloadBytes,
        Storage.BlobTargetOption.doesNotExist());
~~~

Mã này chỉ minh họa thao tác upload bytes; các type `BlobInfo`, `BlobId` và `Storage` thuộc `com.google.cloud.storage`. Nếu object đã tồn tại, SDK báo lỗi precondition/điều kiện; ứng dụng phải quyết định đọc lại metadata hay từ chối. Không dùng cách upload bytes không giới hạn kích thước file.

### 12.3. Azure Blob: service, container và blob clients

Azure SDK thường sử dụng cấu trúc client phân cấp:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

BlobServiceClient serviceClient = new BlobServiceClientBuilder()
        .endpoint("https://account-name.blob.core.windows.net/")
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();

var container = serviceClient.getBlobContainerClient("documents");
var blob = container.getBlobClient("invoices/INV-1042.pdf");
~~~

`BlobServiceClient` là entrypoint cho storage account; `BlobContainerClient` và `BlobClient` định danh phạm vi tài nguyên hẹp hơn. Các client này được thiết kế để tái sử dụng. **Không gọi `close()` theo thói quen lên `BlobServiceClient` nếu API không có method đó.** Vòng đời underlying HTTP transport, Reactor/Netty resource và credential provider phải theo đúng hợp đồng của Azure SDK và cách bạn cung cấp custom `HttpClient`. Nếu tự tạo shared HTTP client/event-loop, chính chủ sở hữu đó chịu trách nhiệm shutdown khi ứng dụng dừng.

Có thể đăng ký bean Spring:

~~~java
@Bean
BlobServiceClient azureBlobServiceClient(
        @Value("${app.azure.blob.endpoint}") String endpoint) {
    return new BlobServiceClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
}
~~~

SDK và framework có thể quản lý các resource mặc định. Với custom HTTP client hoặc credential cần cleanup, khai báo bean cho chúng và lifecycle theo hướng dẫn của loại tài nguyên đó. **Không dùng `@Bean(destroyMethod = "close")` tùy tiện cho một loại không có `close()`.**

### So sánh thiết kế sử dụng

| Chủ đề | AWS S3 SDK v2 | Google Cloud Storage Java | Azure Blob SDK |
| --- | --- | --- | --- |
| Client thường chia sẻ dài hạn | `S3Client` / `S3AsyncClient` | `Storage` | `BlobServiceClient` và các client con |
| Tạo bằng | `S3Client.builder()` | `StorageOptions...getService()` | `BlobServiceClientBuilder` |
| Quyền mặc định | Credential provider chain | ADC | `DefaultAzureCredential` |
| Đóng client | `close()` khi không còn dùng | Theo `Storage.close()`/transport version | Đánh giá owner của HTTP pipeline/transport; không mặc định client có `close()` |
| Chỉ định region/endpoint | Region và endpoint override | Project/options/endpoint | Storage account endpoint |
| Ghi có điều kiện | `If-None-Match`/ETag/version | Generation preconditions | ETag/request conditions |
| Thao tác lớn | Multipart/Transfer Manager | Resumable upload/streaming theo API | Block blob staged blocks/parallel upload |

## 13. Object lifecycle: retention, versioning và xóa an toàn

Dù client đã đóng đúng, object vẫn tồn tại theo policy của storage. Cần tách **vòng đời dữ liệu** khỏi vòng đời JVM.

| Policy | Mục đích | Cần đánh giá |
| --- | --- | --- |
| Versioning | Giữ các version để phục hồi overwrite/xóa | Chi phí version cũ, quyền delete version |
| Lifecycle expiration | Tự xóa object theo tuổi/tags/prefix | Không xóa nhầm tài liệu còn ràng buộc pháp lý |
| Storage class transition | Chuyển dữ liệu ít đọc sang lớp rẻ hơn | Restore delay, chi phí truy xuất và tối thiểu lưu |
| Incomplete multipart cleanup | Dọn part chưa complete | Không phá upload đang diễn ra hợp lệ |
| Object Lock/retention/legal hold | Chặn xóa/sửa trong thời hạn | Khả năng thay đổi policy, quyền admin |
| Delete marker/soft delete | Phục hồi sau thao tác delete | Xóa logic khác xóa vĩnh viễn mọi version |
| Replication/cross-region | Đáp ứng DR và locality | Trễ sao chép, chi phí, quyền truy cập |

Một key `users/{userId}/avatar.jpg` có thể bị overwrite nhiều lần. Nếu bucket bật versioning, các phiên bản trước vẫn chiếm dung lượng; xóa key không nhất thiết xóa dữ liệu cũ. Với dữ liệu nhạy cảm và yêu cầu xóa theo chính sách, cần biết rõ versioning, replication, retention, object lock và quy trình purge.

Không đặt lifecycle rule xóa object chỉ dựa vào ngày tạo nếu database còn tham chiếu object và chưa có phương án đồng bộ; nên xác định trạng thái dữ liệu nghiệp vụ và chính sách retention trước.

## 14. Phân loại lỗi, observability và bảo mật

### Lỗi theo tầng

| Tầng | Dấu hiệu | Cần kiểm tra |
| --- | --- | --- |
| Startup/bean | Không tạo được client, region rỗng, dependency conflict | Properties, dependency management, provider |
| Credentials | Access denied, expired token, ADC thất bại | Identity, role, KMS key, credential rotation |
| Network/HTTP | DNS, TLS, connect timeout, pool wait | Endpoint, proxy, NAT, connection pool, certificate |
| Object API | 404, 409, 412, 429, 503 | Key, conditions, quota, service policy |
| Stream | Pool exhaustion, abandoned response body | `ResponseInputStream.close()`, cancellation, concurrency |
| Data contract | MIME không khớp, checksum lệch, object quá lớn | Validation, scan, metadata và bounded read |
| Business consistency | DB READY nhưng object thiếu, orphan object | State machine, outbox, reconciliation |
| Lifecycle | Chi phí tăng, data hết hạn sai, multipart chưa xóa | Lifecycle rules, retention, versioning, cleanup |

### Metrics và log

Quan sát cả **SDK request** lẫn **business outcome**:

- Request count, HTTP status và loại operation (`PutObject`, `GetObject`, `HeadObject`, `DeleteObject`).
- Latency p50/p95/p99, api call attempts, retry delay, timeout theo loại, connection acquisition wait.
- Số upload/download đồng thời, bytes truyền, throughput, multipart active và incomplete uploads.
- Credential refresh/auth failures, throttling/5xx, lỗi region/signature.
- Tỷ lệ đối soát `PENDING`, `READY`, `FAILED`, orphan object và checksum mismatch.
- Chi phí storage/API request/egress theo workload, bucket và prefix được cấp phép.

Không log secret key, bearer token, SAS token, presigned URL đầy đủ, dữ liệu file hoặc metadata chứa thông tin cá nhân. Object key đôi khi mang định danh khách hàng, vì vậy log dạng đã làm sạch hoặc sử dụng document ID nội bộ khi cần. Tracing nên ghi thông tin operation và correlation ID; tuyệt đối không đưa credential vào span attributes.

### Một số yêu cầu bảo mật trọng yếu

Bảo mật tầng transport bằng HTTPS/TLS, xác minh endpoint, hạn chế quyền bucket/prefix, bật mã hóa phía server theo policy và bảo vệ khóa KMS. Kiểm tra loại file theo nội dung/threat model thay vì chỉ tin `Content-Type` từ browser. Không tạo object key từ path như `../../secret`, không cho người dùng chọn bucket hoặc endpoint tùy ý (nguy cơ SSRF/exfiltration), không tự động trả quyền truy cập object chỉ vì biết tên key.

Với presigned URL, giới hạn tuổi, quyền thao tác, key, size/content type theo khả năng API/policy và xác minh kết quả sau upload. Nếu CDN/cache tham gia, cần thiết kế invalidation và quyền truy cập nhất quán.

## 15. Kiểm thử vòng đời client và luồng tích hợp

### 15.1. Unit test cho adapter

Mock `S3Client` hoặc dùng fake adapter để kiểm thử:

- Key/metadata được tạo đúng định dạng.
- Upload file nhỏ từ bytes; file lớn bị từ chối hoặc đưa qua đường streaming.
- Response S3 được ánh xạ thành `StoredDocument`, giữ version ID/ETag.
- `404`, `403`, timeout, `412` được phân loại đúng, không retry lỗi vĩnh viễn.
- Không đóng singleton `S3Client` sau mỗi request.
- `downloadTo` đóng stream ngay cả khi `OutputStream` ném `IOException`.

Để xác minh lifecycle bean, có thể tạo `ApplicationContext` nhỏ và dùng một test double `AutoCloseable` hoặc mock client, đóng context, rồi kiểm tra `close()` được gọi đúng lúc. Không nên chỉ test một phương thức `@Bean` trả object mà bỏ qua hành vi shutdown thực tế.

### 15.2. Integration test với object store thật hoặc emulator

| Trường hợp | Cách thử | Kỳ vọng |
| --- | --- | --- |
| Upload/download cơ bản | PUT file có SHA-256, GET về | Byte và metadata khớp, stream luôn đóng |
| Quyền đọc/ghi khác nhau | Dùng identity ít quyền | 403/AccessDenied được phân loại, không tăng quyền mù |
| Object không tồn tại | GET key ngẫu nhiên | Not found hoặc 403 theo quyền; không suy luận sai |
| Ghi cùng key đồng thời | Dùng conditional put/generation precondition | Chỉ một create thắng; caller còn lại nhận conflict rõ |
| Timeout sau server commit | Cắt response ở thời điểm khó | Retry với cùng document ID/key, không tạo bản sao |
| Hỏng stream giữa download | Cắt connection khi GET đang đọc | Stream được giải phóng, metrics ghi lỗi |
| Pool cạn | Mở nhiều request đồng thời và cố tình giữ stream | Cảnh báo/giới hạn concurrency; không treo cả service |
| Credentials rotation | Đổi identity/token trong môi trường thử | Client refresh đúng hoặc restart theo policy |
| Upload lớn | Multipart/parallel + cancel | Cleanup incomplete uploads, không để orphan tăng mãi |
| Versioning và delete | Tạo nhiều version rồi delete | Hiểu delete marker, retention và restore |
| SQL/object consistency | Inject lỗi giữa upload và DB commit | Reconciliation đưa trạng thái về nhất quán |
| Presigned upload | Ký URL, tải với đúng/sai header | Chỉ đúng request trong thời hạn/điều kiện được phép |
| Lifecycle shutdown | Đóng Spring context đang có request | Không leak client/pool/executor; xử lý in-flight theo SLA |

**Emulator không phải cloud service thật.** MinIO/LocalStack có thể khác AWS về IAM, ACL, checksum, versioning, multipart, object lock hoặc presign; Azurite/GCS fake cũng có giới hạn tương tự. Test nhanh trên emulator, sau đó có một bộ contract/integration test hạn chế chạy trên dịch vụ thực để xác nhận những tính năng production sử dụng.

Test chi phí và độ trễ phải đo ở region/network thực tế; chạy một test local nhanh không chứng minh API sẽ giữ SLA khi đối tượng vài GB hoặc có cross-region egress.

## 16. Những lỗi thiết kế thường gặp

**“Tạo S3Client trong phương thức service rồi dùng try-with-resources thì an toàn hơn?”**

Không cho ứng dụng phục vụ request thường xuyên. Việc tạo và phá HTTP pool liên tục gây overhead và mất khả năng tái sử dụng connection. Dùng singleton bean lâu dài, chỉ đóng khi shutdown hoặc không còn cần dùng. `try-with-resources` rất phù hợp cho *response stream* của từng request.

**“Đã đóng S3Client khi Spring shutdown, vậy không còn connection leak?”**

Chưa chắc. Nếu quên đóng response stream trong lúc server chạy, pool có thể bị cạn trước khi tới shutdown. Cần giải phóng tài nguyên theo *cả vòng đời request và vòng đời client*.

**“Đặt `@Transactional` quanh upload thì upload sẽ rollback theo SQL?”**

Không. Object store là hệ thống ngoài database transaction. Dùng trạng thái bền vững, outbox, retry có giới hạn và reconciliation.

**“SDK tự retry nên upload chắc chắn không bị nhân đôi?”**

Không. Retry xử lý một số lỗi transport/service, nhưng lỗi sau commit có thể để lại kết quả không rõ ràng. Object key, conditional write, checksum và idempotency nghiệp vụ mới quyết định trạng thái cuối.

**“Cứ gặp 404 thì key chắc chắn chưa tồn tại; gặp 403 thì sửa bằng admin credentials?”**

Không. Các quyền và provider có thể che thông tin tồn tại. Sửa IAM theo quyền tối thiểu và kiểm tra mục đích thao tác, tránh leo thang quyền để che lỗi contract.

**“Azure BlobServiceClient, Google Storage và AWS S3Client đều close như nhau?”**

Không. Đọc API và hợp đồng ownership của **loại client/transport cụ thể**. AWS S3Client hỗ trợ close, Google Cloud Storage có close ở các version hiện đại, còn Azure Blob client thường quản lý pipeline theo cách khác và không mặc nhiên cung cấp close trên mọi lớp.

**“Xóa object bằng SDK là dữ liệu đã biến mất vĩnh viễn?”**

Không khi có versioning, delete marker, soft delete, retention, object lock hoặc replication. Phải thiết kế lifecycle dữ liệu theo chính sách thực tế.

**“Presigned URL đưa cho browser rồi có thể đánh dấu file READY ngay?”**

Không. Cần xác nhận upload đã xảy ra, đúng object/key, đúng checksum/size, có quyền owner tương ứng, và đã qua validation/scan nếu nghiệp vụ yêu cầu.

### Checklist đưa vào production

1. Chọn SDK/BOM được hỗ trợ, đồng bộ version dependency và xác định sync/async cho loại traffic.
2. Tạo service client ở scope singleton hoặc scope tenant có giới hạn; ghi rõ owner của client, HTTP transport, credentials và shutdown.
3. Dùng default identity chain/workload identity, quyền tối thiểu; tránh static key trong ứng dụng và thử rotation.
4. Cấu hình bucket/container, region/endpoint, TLS, KMS và validation cho object key/metadata.
5. Đặt timeout từng attempt và toàn API call, kiểm soát retry, pool, concurrency và kích thước file.
6. Đóng response stream sau mọi GET; quản lý temp file, multipart upload, cancellation và pool.
7. Định nghĩa key bất biến, conditional write/version, checksum và idempotency cho mọi thao tác có thể bị thử lại.
8. Xử lý nhất quán SQL–object storage–broker bằng state machine, outbox, retry và reconciliation.
9. Thiết kế presigned URL ngắn hạn, kiểm tra hoàn tất tải lên, quyền truy cập và bảo mật payload.
10. Cấu hình object lifecycle, retention, versioning và dọn multipart/orphan theo chính sách dữ liệu.
11. Đo errors/latency/retries/bytes/pool và business state; test emulator **và** contract với cloud thật khi phù hợp.

### Nguồn kỹ thuật để đối chiếu phiên bản

- [AWS SDK for Java 2.x – Client best practices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html): tái sử dụng thread-safe service clients và đóng response stream.
- [AWS SDK for Java 2.x – Singleton service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/singleton-service-clients.html): một client dùng chung trong application.
- [AWS SDK for Java 2.x – Timeouts](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html): apiCallTimeout và apiCallAttemptTimeout.
- [AWS SDK for Java 2.x – Uploading streams](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices-s3-uploads.html): content length và streaming.
- [AWS SDK for Java 2.x – Presigned URLs](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3-presign.html): quyền tải lên/tải xuống tạm thời.
- [Google Cloud Java – Storage API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.html): lifecycle và thao tác object theo precondition.
- [Microsoft Learn – Azure Blob Storage Java quickstart](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-java-how-to-use-blob-storage): client, identity và cấu trúc storage account/container/blob.

**Ghi nhớ:** Một **SDK client** là thành phần tích hợp sống cùng ứng dụng và quản lý kết nối/identity; một **request/response stream** có vòng đời ngắn, phải được tiêu thụ hoặc đóng; còn **object** tồn tại theo chính sách lưu trữ độc lập với JVM. Thiết kế đúng cả ba vòng đời, cùng với idempotency, timeout, giao dịch và kiểm thử, mới giúp luồng tích hợp Spring Boot với dịch vụ đám mây vận hành ổn định.

