# Ánh xạ tài nguyên đám mây vào Spring Resource

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot tích hợp các dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud, SDK và driver tương ứng. Nhiều ứng dụng cần đọc tài nguyên từ classpath, file system, HTTP endpoint, Amazon S3, Google Cloud Storage hoặc Azure Blob Storage.

Spring Framework cung cấp abstraction **`Resource`** để mô tả một tài nguyên có thể đọc mà không buộc code gọi phải biết dữ liệu nằm ở đâu. **`ResourceLoader`** giải quyết chuỗi location thành một `Resource`. Nhờ đó, service có thể đọc qua `getInputStream()` thay vì tự xử lý từng loại storage.

Object storage không phải file system. Object trên S3 không nhất thiết có đường dẫn local, không thể mặc định đổi thành `java.io.File`, và thao tác đọc có thể cần gọi mạng, kiểm tra IAM permission, trả phí request hoặc mở một stream phải đóng đúng cách. Spring Resource là abstraction truy cập tài nguyên; nó không tự biến mọi cloud URI thành scheme được Spring hỗ trợ.

Bài dùng Amazon S3 làm ví dụ để xây dựng adapter `s3://bucket/key` thông qua extension point `ProtocolResolver`. Các nguyên tắc tương tự áp dụng cho Google Cloud Storage và Azure Blob Storage, nhưng URI scheme, SDK, danh tính, metadata và semantics cần được xác định riêng cho từng provider.

Sau bài học, bạn có thể:

1. Phân biệt `Resource`, `ResourceLoader` và `ResourcePatternResolver`.
2. Hiểu các method của `Resource` và giới hạn khi resource nằm trên cloud.
3. Ánh xạ URI cloud như `s3://bucket/key` thành implementation của Spring Resource.
4. Đăng ký `ProtocolResolver` và sử dụng `DefaultResourceLoader` trong Spring Boot.
5. Đọc object theo streaming, quản lý stream, metadata, lỗi và chi phí request.
6. Thiết kế quyền truy cập, tenant boundary, URI validation và credential provider an toàn.
7. Phân biệt abstraction đọc với upload/write, cache và wildcard listing.
8. Kiểm thử adapter bằng unit test, mock SDK, LocalStack và cloud staging.

> **Phạm vi:** `Resource` phù hợp để biểu diễn tài nguyên có thể đọc. Upload, multipart, copy, delete, versioning, encryption và conditional write nên dùng API/port storage có semantics rõ ràng. Không mặc định mọi cloud provider hoặc Spring Cloud starter đều đăng ký cùng một URI scheme.

## 2. Spring Resource abstraction

### 2.1. `Resource` là gì?

`org.springframework.core.io.Resource` là interface mô tả resource có thể đọc. Nó mở rộng `InputStreamSource` và cung cấp thông tin như resource có tồn tại, có đọc được, tên file, mô tả, URL/URI hoặc khả năng truy cập như file.

Các implementation thường gặp:

| Implementation | Nguồn tài nguyên | Ví dụ |
| --- | --- | --- |
| `ClassPathResource` | Classpath của ứng dụng | `classpath:templates/email.html` |
| `FileSystemResource` | File system | `file:/var/app/import/data.csv` |
| `UrlResource` | URL như HTTP/HTTPS | `https://example.org/config.json` |
| `ByteArrayResource` | Mảng byte trong bộ nhớ | Nội dung nhỏ tạo trong runtime |
| `InputStreamResource` | InputStream có sẵn | Stream do API khác cấp |
| `ServletContextResource` | Web application context | Tài nguyên trong servlet context |
| Cloud Resource tùy chỉnh | Object storage/provider API | `s3://rental-documents/invoices/2026/01.pdf` |

Điểm chung là code tiêu thụ có thể dùng `getInputStream()`. Nhưng các method khác có thể có khả năng khác nhau: `FileSystemResource` có thể trả về `File`, trong khi S3 resource không có file local.

### 2.2. Những method cần hiểu

| Method | Ý nghĩa | Lưu ý với cloud resource |
| --- | --- | --- |
| `exists()` | Kiểm tra resource tồn tại | Thường cần gọi metadata/HEAD API qua mạng |
| `isReadable()` | Resource có thể đọc theo implementation hay không | Có thể cần quyền đọc; không bảo đảm lần đọc sau luôn thành công |
| `isOpen()` | Resource đại diện cho stream đang mở hay không | Resource handle thường trả false; InputStreamResource có thể trả true |
| `isFile()` | Resource có được biểu diễn như file không | Object storage thường trả false |
| `getInputStream()` | Mở stream để đọc nội dung | Mỗi lần gọi nên mở stream mới nếu implementation hỗ trợ; caller phải đóng |
| `contentLength()` | Độ dài nội dung | Có thể gọi HEAD/metadata API; tránh gọi lặp lại |
| `lastModified()` | Thời điểm sửa đổi | Phụ thuộc metadata provider |
| `getFilename()` | Tên file/tên cuối của path | Với object key, thường là đoạn cuối sau dấu slash |
| `getURL()` / `getURI()` | URL/URI định danh resource | Cloud URI không nhất thiết là URL HTTP truy cập trực tiếp |
| `getFile()` | Trả về file local | Không dùng được với object storage nếu chưa tải về |
| `createRelative()` | Tạo resource tương đối | Quy tắc path object key khác file system |

Không gọi `getFile()` như cách đọc chung cho mọi Resource. Code portable nên dùng `getInputStream()` và đóng stream bằng try-with-resources.

### 2.3. Resource là handle, không phải nội dung đã tải về

Ví dụ đọc resource nhỏ:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.Resource;

public String readText(Resource resource) throws IOException {
    try (InputStream input = resource.getInputStream()) {
        return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }
}
~~~

Với object lớn, `readAllBytes()` giữ toàn bộ nội dung trong heap và có thể gây `OutOfMemoryError`. Hãy xử lý theo stream:

~~~java
try (InputStream input = resource.getInputStream()) {
    Files.copy(input, destination, StandardCopyOption.REPLACE_EXISTING);
}
~~~

Một `Resource` không đồng nghĩa với một stream đã mở. Gọi `getInputStream()` khi cần đọc, đóng stream sau khi xử lý và không chia sẻ cùng một InputStream cho nhiều thread.

### 2.4. Các method có thể gây network I/O

Với cloud resource, các lời gọi sau có thể gửi request tới provider:

- `exists()` có thể gọi HEAD hoặc metadata lookup.
- `contentLength()` có thể gọi HEAD.
- `lastModified()` có thể gọi HEAD.
- `getInputStream()` mở kết nối đọc object.
- `isReadable()` có thể kiểm tra metadata hoặc permission.

Không gọi `exists()` rồi `getInputStream()` nhiều lần trong vòng lặp nếu không cần. Hai thao tác có thể tạo hai request mạng và vẫn có race condition: object có thể bị xóa hoặc quyền thay đổi giữa lúc kiểm tra và lúc đọc. Trong nhiều use case, mở stream một lần rồi xử lý lỗi not-found/forbidden từ thao tác đọc hợp lý hơn.

Phân biệt rõ 404 và 403. Object không tồn tại có thể trả 404 nếu principal có quyền cần thiết; khi thiếu quyền list bucket, một số API có thể không tiết lộ object có tồn tại hay không và trả 403. Không biến mọi lỗi authorization thành "resource không tồn tại".

## 3. ResourceLoader và location prefix

### 3.1. ResourceLoader giải quyết location

`org.springframework.core.io.ResourceLoader` cung cấp method chính:

~~~java
Resource getResource(String location);
~~~

Các prefix thường gặp:

| Prefix | Ý nghĩa |
| --- | --- |
| `classpath:` | Tìm resource trong classpath |
| `file:` | Resource từ file system |
| `http:` / `https:` | Resource từ URL |
| Không có prefix | Quy tắc mặc định phụ thuộc ResourceLoader/ApplicationContext đang dùng |

Ví dụ:

~~~java
Resource classpathResource =
        resourceLoader.getResource("classpath:templates/report.html");

Resource localFile =
        resourceLoader.getResource("file:/var/app/import/report.csv");

Resource remoteUrl =
        resourceLoader.getResource("https://example.org/report.json");
~~~

`ResourceLoader` không tự hiểu các scheme `s3://`, `gs://` hoặc `azure-blob://`. Những scheme này chỉ hoạt động khi có starter/provider integration đăng ký chúng hoặc ứng dụng tự cài đặt resolver tương ứng.

Không giả định rằng `@Value("s3://...") Resource` tự hoạt động trong mọi Spring Boot application. Việc phân giải phụ thuộc ApplicationContext và resolver đã đăng ký. Với resolver tự viết, có thể tạo một `DefaultResourceLoader` riêng và inject rõ ràng vào component cần dùng.

### 3.2. ResourcePatternResolver khác ResourceLoader

`ResourcePatternResolver` mở rộng `ResourceLoader` và hỗ trợ tìm nhiều resource theo pattern, ví dụ:

~~~java
Resource[] resources =
        resolver.getResources("classpath*:/migrations/*.sql");
~~~

Pattern `classpath*:` hữu ích để tìm tài nguyên trên nhiều JAR/classpath location. Không suy ra rằng `s3://bucket/**/*.json` tự động liệt kê toàn bộ object trong bucket.

Cloud object listing cần provider API riêng, pagination, permission và chi phí. Nếu muốn hỗ trợ pattern trên cloud, phải định nghĩa semantics rõ ràng:

- Prefix và wildcard được chuyển thành API list nào?
- Có phân trang và giới hạn số object không?
- Thứ tự kết quả có ổn định không?
- Có lọc version/delete marker không?
- Request listing có thể tốn chi phí và mất thời gian ra sao?
- Caller xử lý object bị xóa trong lúc đang duyệt như thế nào?

Một `ProtocolResolver` trả về một `Resource` đơn lẻ không tự triển khai wildcard listing.
## 4. Extension point ProtocolResolver

### 4.1. Vì sao cần resolver?

Spring có interface:

~~~java
public interface ProtocolResolver {
    Resource resolve(String location, ResourceLoader resourceLoader);
}
~~~

Resolver nhận location và trả về Resource nếu nó nhận diện được scheme; nếu không xử lý location đó, trả về `null` để resolver khác tiếp tục. `DefaultResourceLoader` cho phép đăng ký resolver bằng `addProtocolResolver`.

Ví dụ luồng:

~~~mermaid
flowchart TD
    A["ResourceLoader.getResource(location)"] --> B["ProtocolResolver list"]
    B --> C{"Có resolver nhận scheme?"}
    C -->|Có| D["Cloud Resource"]
    C -->|Không| E["Default Spring resolution"]
    D --> F["Resource.getInputStream()"]
    F --> G["Cloud SDK / object storage"]
~~~

Resolver chỉ phân tích location và tạo resource handle. Nó không nên tải toàn bộ object khi `getResource()` được gọi. Nội dung chỉ được tải khi caller gọi `getInputStream()`.

### 4.2. Đăng ký resolver vào DefaultResourceLoader

Ví dụ cấu hình riêng cho ứng dụng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.DefaultResourceLoader;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class CloudResourceConfiguration {

    @Bean
    S3ProtocolResolver s3ProtocolResolver(S3Client s3Client) {
        return new S3ProtocolResolver(s3Client);
    }

    @Bean("cloudResourceLoader")
    DefaultResourceLoader cloudResourceLoader(
            S3ProtocolResolver s3ProtocolResolver) {
        DefaultResourceLoader loader = new DefaultResourceLoader();
        loader.addProtocolResolver(s3ProtocolResolver);
        return loader;
    }
}
~~~

Đây là ResourceLoader bean riêng có tên `cloudResourceLoader`. Inject bằng `@Qualifier("cloudResourceLoader")` ở component cần đọc cloud resource. Không nên khẳng định resolver này tự động thay đổi mọi lời gọi `ApplicationContext.getResource()` hoặc mọi `@Value` trong ứng dụng; muốn có behavior toàn context cần tích hợp vào ApplicationContext/resource loading strategy phù hợp với phiên bản Spring.

## 5. Thiết kế URI cho cloud object

### 5.1. Quy ước URI

Một convention dễ hiểu cho S3:

~~~text
s3://<bucket>/<object-key>
~~~

Ví dụ:

~~~text
s3://rental-documents/invoices/2026/INV-001.pdf
s3://rental-exports/tenant-a/2026/11/report.csv
~~~

Scheme `s3://` ở đây là quy ước của adapter trong ứng dụng. Nó không phải một giao thức chung được mọi Spring application hiểu tự động.

Các provider khác có thể dùng convention riêng:

| Provider | Ví dụ URI convention | Ghi chú |
| --- | --- | --- |
| AWS S3 | `s3://bucket/key` | Resolver dùng S3 SDK/AWSpring integration |
| Google Cloud Storage | `gs://bucket/object` | Một số Spring Cloud GCP integration có hỗ trợ Resource; kiểm tra version và module |
| Azure Blob Storage | `azure-blob://account/container/blob` | Có thể là scheme nội bộ do ứng dụng định nghĩa; không giả định Spring tự hỗ trợ |
| HTTP object gateway | `https://host/path` | Dùng UrlResource nếu endpoint thực sự cho phép HTTP GET |

Nếu ứng dụng cần đa cloud, không nhất thiết phải ép mọi provider vào cùng một URI string. Có thể định nghĩa locator type nội bộ gồm provider, container/bucket, object key và version; sau đó adapter tạo Resource tương ứng. URI chỉ là serialization/lookup convention, không nên trở thành domain identity duy nhất nếu provider có semantics khác nhau.

### 5.2. Parse URI có validation

Với S3, URI cần bucket và object key:

- Scheme phải là `s3`.
- Host phải là bucket hợp lệ.
- Path phải chứa object key.
- Không nhận user info, port, query hoặc fragment nếu adapter không định nghĩa các trường đó.
- Key có ký tự đặc biệt cần URI-encode đúng; không tự thay dấu cộng hoặc percent-encoding một cách tùy tiện.
- Không dùng URI do người dùng cuối cung cấp trực tiếp nếu chưa kiểm tra tenant, bucket allow-list và prefix được phép.

Không nhúng access key, secret, session token hoặc presigned URL vào URI cấu hình. IAM credentials được cung cấp qua SDK credential provider chain.

## 6. Ví dụ AWS: S3 Resource qua AWS SDK for Java 2.x

### 6.1. Dependency

Dùng AWS SDK BOM và module S3:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>`aws.sdk.version`</version>
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

Nếu phiên bản AWSpring trong dự án cung cấp abstraction S3 đáp ứng đầy đủ use case, cân nhắc dùng abstraction đó thay vì tự viết lại toàn bộ S3 operations. Ví dụ này dùng SDK v2 để minh họa ranh giới giữa Resource và provider API; không phải yêu cầu mọi dự án phải tự xây S3 adapter.

### 6.2. Tạo S3Client dùng chung

Khai báo Region theo cấu hình môi trường, không ghi credential vào file:

~~~yaml
app:
  aws:
    region: ap-southeast-1
~~~

Record cấu hình tối thiểu:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.aws")
public record AwsIntegrationProperties(String region) {
}
~~~

Đăng ký record bằng `@EnableConfigurationProperties(AwsIntegrationProperties.class)` hoặc configuration properties scanning của ứng dụng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
@EnableConfigurationProperties(AwsIntegrationProperties.class)
public class S3ClientConfiguration {

    @Bean(destroyMethod = "close")
    DefaultCredentialsProvider awsCredentialsProvider() {
        return DefaultCredentialsProvider.create();
    }

    @Bean(destroyMethod = "close")
    S3Client s3Client(
            DefaultCredentialsProvider credentialsProvider,
            AwsIntegrationProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(credentialsProvider)
                .build();
    }
}
~~~

`S3Client` thread-safe và nên được dùng chung như Spring singleton bean. AWS SDK dùng credential provider chain để lấy credentials theo môi trường: ECS task role, EKS Pod Identity/IRSA, EC2 instance profile hoặc profile dành cho local development. Không đặt access key dài hạn trong source hoặc file cấu hình commit Git.

Region phải phù hợp với bucket và client configuration. Với bucket ở nhiều Region, cần chiến lược client/Region rõ ràng; không giả định một client Region bất kỳ sẽ xử lý mọi bucket mà không cần cấu hình hoặc redirect behavior phù hợp.
### 6.3. Implement S3ObjectResource

Implementation dưới đây tập trung vào đọc object và metadata cơ bản:

~~~java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.util.Date;

import org.springframework.core.io.AbstractResource;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;
import software.amazon.awssdk.services.s3.model.S3Exception;

public final class S3ObjectResource extends AbstractResource {

    private final S3Client s3Client;
    private final String bucket;
    private final String key;

    public S3ObjectResource(S3Client s3Client, String bucket, String key) {
        this.s3Client = s3Client;
        this.bucket = bucket;
        this.key = key;
    }

    private HeadObjectResponse headObject() throws IOException {
        try {
            return s3Client.headObject(HeadObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build());
        } catch (S3Exception ex) {
            if (ex.statusCode() == 404) {
                throw new FileNotFoundException(getDescription());
            }
            throw new IOException("Cannot read S3 object metadata: "
                    + getDescription(), ex);
        } catch (SdkClientException ex) {
            throw new IOException("S3 metadata request failed: "
                    + getDescription(), ex);
        }
    }

    @Override
    public boolean exists() {
        try {
            headObject();
            return true;
        } catch (FileNotFoundException ex) {
            return false;
        } catch (IOException ex) {
            throw new java.io.UncheckedIOException(ex);
        }
    }

    @Override
    public boolean isReadable() {
        return exists();
    }

    @Override
    public boolean isFile() {
        return false;
    }

    @Override
    public boolean isOpen() {
        return false;
    }

    @Override
    public InputStream getInputStream() throws IOException {
        try {
            ResponseInputStream<?> stream = s3Client.getObject(
                    GetObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build());
            return stream;
        } catch (S3Exception ex) {
            if (ex.statusCode() == 404) {
                throw new FileNotFoundException(getDescription());
            }
            throw new IOException("Cannot open S3 object: "
                    + getDescription(), ex);
        } catch (SdkClientException ex) {
            throw new IOException("S3 object request failed: "
                    + getDescription(), ex);
        }
    }

    @Override
    public long contentLength() throws IOException {
        return headObject().contentLength();
    }

    @Override
    public long lastModified() throws IOException {
        Date modified = Date.from(headObject().lastModified());
        return modified.getTime();
    }

    @Override
    public String getFilename() {
        int slash = key.lastIndexOf('/');
        return slash >= 0 ? key.substring(slash + 1) : key;
    }

    @Override
    public java.io.File getFile() throws IOException {
        throw new FileNotFoundException(
                "S3 object is not a local file: " + getDescription());
    }

    @Override
    public String getDescription() {
        return "S3 object [s3://" + bucket + "/" + key + "]";
    }
}
~~~

Các điểm cần hiểu:

- `getInputStream()` gọi `GetObject` và trả về response stream. Caller phải đóng stream để giải phóng HTTP connection.
- `exists()` và `isReadable()` dùng `HeadObject` để kiểm tra metadata; đây là network call, không phải phép kiểm tra local miễn phí.
- `contentLength()` và `lastModified()` lấy metadata từ HEAD response.
- `isFile()` trả false vì object không phải file local.
- `getFile()` ném lỗi rõ ràng thay vì giả vờ object có path local.
- `getDescription()` dùng URI định danh, không chứa access key hoặc presigned query string.

Đây là implementation tối giản cho ví dụ. Trong production cần cân nhắc retry, timeout, mã lỗi provider, object version, SSE/KMS, request payer, checksum, endpoint tùy môi trường và telemetry. Không biến 403 thành 404; permission failure cần được giữ nguyên để chẩn đoán.

### 6.4. Một số giới hạn của implementation mẫu

Implementation trên có các lựa chọn có chủ đích:

1. `createRelative()` chưa được định nghĩa; không giả định path resolution của object key giống file system.
2. `getURL()` và `getURI()` không trả presigned URL; resource URI chỉ là locator.
3. `getFile()` không tải object về local; nếu cần file, caller phải copy stream vào temp path có lifecycle rõ.
4. `exists()` có thể ném `UncheckedIOException` khi lỗi mạng/permission khác not-found; caller phải phân biệt.
5. `contentLength()`/`lastModified()` gọi HEAD mỗi lần; nếu cần tối ưu, cache metadata theo policy và invalidation rõ.
6. Ví dụ giả định bucket/Region đã được cấu hình hợp lệ và client có quyền `s3:GetObject` trên key.

Không giữ `ResponseInputStream` mở trong field của Resource. Resource là mô tả object; stream là tài nguyên có vòng đời riêng của mỗi lần đọc.
## 7. Đăng ký S3 URI qua ProtocolResolver

### 7.1. S3ProtocolResolver

~~~java
import java.net.URI;

import org.springframework.core.io.Resource;
import org.springframework.core.io.ProtocolResolver;
import org.springframework.core.io.ResourceLoader;

import software.amazon.awssdk.services.s3.S3Client;

public final class S3ProtocolResolver implements ProtocolResolver {

    private final S3Client s3Client;

    public S3ProtocolResolver(S3Client s3Client) {
        this.s3Client = s3Client;
    }

    @Override
    public Resource resolve(String location, ResourceLoader resourceLoader) {
        if (!location.regionMatches(true, 0, "s3:", 0, 3)) {
            return null;
        }

        final URI uri;
        try {
            uri = URI.create(location);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid S3 resource URI", ex);
        }

        if (!"s3".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getPort() != -1
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException("Invalid S3 resource URI");
        }

        String path = uri.getPath();
        if (path == null || path.length() <= 1) {
            throw new IllegalArgumentException(
                    "S3 URI must include bucket and object key");
        }

        String key = path.substring(1);
        return new S3ObjectResource(s3Client, uri.getHost(), key);
    }
}
~~~

Resolver chỉ xử lý scheme `s3`; scheme khác trả `null`. Nếu location bắt đầu bằng `s3:` nhưng URI sai cú pháp, resolver ném lỗi rõ ràng thay vì để Spring coi chuỗi đó như classpath path. Ví dụ từ chối query/fragment/user info để URI có một nghĩa duy nhất.

Nếu ứng dụng muốn hỗ trợ object version, endpoint override hoặc encryption context, hãy thiết kế locator/options riêng và validate rõ, không tùy tiện nhét credential vào query string. Object key có ký tự đặc biệt phải được encode/decode nhất quán; kiểm thử các key chứa khoảng trắng, dấu %, dấu slash và Unicode.

### 7.2. Sử dụng ResourceLoader

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class CloudDocumentReader {

    private final ResourceLoader resourceLoader;

    public CloudDocumentReader(
            @Qualifier("cloudResourceLoader") ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource resolve(String location) {
        return resourceLoader.getResource(location);
    }
}
~~~

Cách dùng:

~~~java
Resource resource = cloudDocumentReader.resolve(
        "s3://rental-documents/invoices/2026/INV-001.pdf");

try (InputStream input = resource.getInputStream()) {
    // Stream sang parser hoặc destination.
}
~~~

Nếu component chỉ đọc S3, cân nhắc inject một port cụ thể như `DocumentStorage` thay vì cho phép truyền location tùy ý. ResourceLoader tổng quát phù hợp hơn khi use case thực sự cần đọc nhiều loại location.

## 8. Mapping Resource giữa AWS, Google Cloud và Azure

### 8.1. Khác biệt provider cần giữ lại

| Khía cạnh | AWS S3 | Google Cloud Storage | Azure Blob Storage |
| --- | --- | --- | --- |
| Locator thường gặp | Bucket + object key | Bucket + object name | Storage account + container + blob name |
| SDK Java | AWS SDK v2 S3 | Google Cloud Storage client | Azure Storage Blob SDK |
| Danh tính workload | IAM role / credential provider | Application Default Credentials / Workload Identity | Managed Identity / DefaultAzureCredential |
| Metadata | HeadObject, ETag, version ID, last modified | Blob metadata, generation, metageneration | Blob properties, ETag, version ID |
| Streaming read | GetObject response stream | ReadChannel/Blob read APIs | BlobInputStream |
| Conditional operation | ETag/version/condition headers | Generation preconditions | ETag conditions |
| URI scheme | Adapter có thể định nghĩa `s3://` | Một số Spring Cloud GCP module có Resource integration với `gs://` | Scheme phụ thuộc integration hoặc quy ước ứng dụng |

Một Resource abstraction chung có thể che đi thao tác mở stream và một số metadata. Nhưng provider vẫn khác nhau về version/generation, ETag, encryption, retention, ACL, consistency, retry, request cost và conditional operations. Khi nghiệp vụ cần các đặc tính đó, không được bỏ chúng khỏi contract chỉ để mọi provider trông giống nhau.

### 8.2. Google Cloud Storage

Spring Cloud GCP có các integration cho Cloud Storage theo phiên bản; một số release cung cấp Resource loader cho location `gs://`. Trước khi tự viết resolver, kiểm tra đúng starter/module và version đang dùng để tránh đăng ký trùng scheme hoặc bỏ qua tính năng đã có.

Nếu cần adapter riêng, triển khai `ProtocolResolver` dùng Google Cloud Storage client và một `Resource` riêng. Các thao tác metadata/read tương ứng có thể dùng API lấy Blob metadata và mở ReadChannel/stream. Authentication nên dùng Application Default Credentials hoặc Workload Identity; không đưa service account key vào URI hoặc source.

### 8.3. Azure Blob Storage

Azure Storage Blob SDK cung cấp `BlobServiceClient`, `BlobContainerClient` và `BlobClient` để đọc properties và mở stream. Azure Spring integrations có thể cung cấp template/operations tùy phiên bản, nhưng không giả định có một scheme ResourceLoader phổ quát cho mọi ứng dụng.

Nếu cần `azure-blob://account/container/blob`, định nghĩa URI convention, resolver và resource implementation riêng. Production nên ưu tiên Managed Identity hoặc DefaultAzureCredential với workload identity phù hợp; tránh lưu account key/SAS token dài hạn trong configuration. SAS URL có quyền và thời hạn, cần được coi là secret.

### 8.4. Khi nào dùng một ResourceLoader đa provider?

Có thể đăng ký nhiều ProtocolResolver trên cùng DefaultResourceLoader:

~~~java
loader.addProtocolResolver(s3ProtocolResolver);
loader.addProtocolResolver(gcsProtocolResolver);
loader.addProtocolResolver(azureBlobProtocolResolver);
~~~

Mỗi resolver nhận một scheme riêng và trả về Resource phù hợp. Tuy nhiên, đây chỉ là một lớp phân giải location. Nếu service cần upload, delete, copy, list, versioning hoặc generate signed URL, hãy dùng storage port riêng để thể hiện những thao tác đó.

Không ép provider có semantics khác nhau vào một interface quá yếu. Có thể chia interface theo use case:

- `DocumentReader`: mở stream và đọc metadata cần thiết.
- `DocumentWriter`: ghi object và trả về object identifier/version.
- `DocumentLister`: liệt kê theo prefix/page token.
- `DocumentLifecycle`: delete, archive, retention hoặc restore.
- `SignedDownloadUrlProvider`: tạo URL truy cập tạm thời theo policy.
## 9. Resource đọc và WritableResource ghi

### 9.1. Resource không mặc định hỗ trợ write

`Resource` tập trung vào việc truy cập/đọc. Spring có interface `WritableResource` mở rộng Resource, cung cấp `isWritable()` và `getOutputStream()`. Một số implementation local như `FileSystemResource` có thể hỗ trợ ghi; không có nghĩa mọi cloud Resource đều hỗ trợ upload.

Với object storage, write có thể liên quan đến:

- Object có bị overwrite không?
- Có điều kiện tạo mới nếu object chưa tồn tại không?
- Upload nhỏ hay multipart upload?
- Content type, metadata, tags, encryption và checksum được thiết lập ra sao?
- Có versioning hoặc retention/object lock không?
- Khi stream ghi đóng, upload đã commit hay còn bước finalize?
- Nếu upload lỗi giữa chừng, multipart parts có được abort không?
- Caller nhận được ETag/version/generation nào?

Nếu implement `WritableResource`, cần định nghĩa rõ semantics của output stream và thời điểm upload thực sự hoàn tất. Với nhiều ứng dụng, một port chuyên biệt như `DocumentStorage.store(key, input, metadata)` an toàn và dễ hiểu hơn.

### 9.2. Không dùng File để đại diện cloud object

Một số thư viện cũ chỉ nhận `File`. Nếu cần tương thích, tải object vào temporary file:

~~~java
Path temp = Files.createTempFile("cloud-resource-", ".bin");
try (InputStream input = resource.getInputStream()) {
    Files.copy(input, temp, StandardCopyOption.REPLACE_EXISTING);
}

try {
    legacyProcessor.process(temp.toFile());
} finally {
    Files.deleteIfExists(temp);
}
~~~

Ví dụ cần xử lý thêm giới hạn kích thước, disk quota, quyền file, cleanup khi process bị kill và tên file an toàn. Không dùng cách này cho object lớn nếu có thể sửa thư viện để nhận InputStream/ReadableByteChannel.

## 10. Security và tenant isolation

### 10.1. Resource URI không phải authorization

Biết URI `s3://bucket/key` không đồng nghĩa caller có quyền đọc object. Quyền được quyết định bởi IAM role, bucket policy, KMS key policy, network và các control của provider.

Ứng dụng cần kiểm soát:

- Bucket/container allow-list theo môi trường.
- Tenant prefix hoặc mapping tenant-to-container được xác minh phía server.
- Quyền đọc object tối thiểu; không cấp list/write/delete nếu use case chỉ cần get.
- Quyền KMS decrypt nếu object dùng SSE-KMS.
- Chặn URI do client tự cung cấp trỏ sang bucket/account khác ngoài phạm vi.
- Không cho người dùng tự chọn endpoint/host để tránh SSRF hoặc truy cập metadata service qua resolver HTTP tùy tiện.

### 10.2. Không đưa secret vào location

Không dùng các URI dạng:

~~~text
s3://ACCESS_KEY:SECRET_KEY@bucket/key
https://bucket.s3.amazonaws.com/key?X-Amz-Signature=...
~~~

URI chứa credential có thể lọt vào log, metric, exception, trace hoặc browser history. Dùng workload identity/credential provider cho SDK. Nếu cần signed URL, tạo qua một service chuyên trách, giới hạn method, object, thời hạn và người nhận; không coi signed URL là định danh ổn định của Resource.

### 10.3. Path normalization và object key

Object key có thể chứa dấu slash, khoảng trắng và ký tự Unicode. Không áp dụng quy tắc chuẩn hóa file system như xóa `..` một cách mù quáng vì object key là chuỗi tên do provider quản lý. Thay vào đó:

1. Parse URI theo RFC 3986.
2. Chỉ chấp nhận scheme/authority đã định nghĩa.
3. Decode path đúng một lần theo quy ước.
4. Kiểm tra bucket/container và tenant prefix bằng allow-list.
5. Không nối input người dùng vào endpoint/hostname.
6. Giữ nguyên object key đã validate khi gọi SDK.

Nếu tenant chỉ được đọc prefix `tenant-a/`, phải kiểm tra key bắt đầu bằng prefix đã xác thực ở server. Không dựa vào việc URI có chứa tenant ID trong chuỗi để cấp quyền.

## 11. Performance, cache và consistency

### 11.1. Streaming thay vì tải toàn bộ

Với object lớn:

- Dùng stream/byte channel và xử lý theo chunk.
- Đóng stream sớm khi caller hủy hoặc parser kết thúc.
- Thiết lập connection/read timeout và cancellation phù hợp với request deadline.
- Giới hạn số stream đồng thời để tránh cạn HTTP connection pool hoặc file descriptor.
- Dùng provider range read khi cần đọc một đoạn object; Resource interface không có API range chuẩn chung.

Đối với HTTP request, không giữ một cloud stream mở khi chờ thao tác người dùng. Nếu response client bị cancel, đóng stream và giải phóng connection.

### 11.2. Metadata và existence cache

`contentLength()`, `lastModified()` và `exists()` có thể gửi HEAD request. Nếu gọi nhiều lần trên cùng resource, chi phí/latency tăng. Có thể cache metadata trong resource handle hoặc service-level cache, nhưng cần cân nhắc:

- Object có thể bị overwrite hoặc delete.
- ETag không phải lúc nào cũng là checksum nội dung (ví dụ multipart hoặc encryption).
- Version ID/generation có thể định danh phiên bản bất biến tốt hơn key hiện tại.
- TTL cache tạo độ trễ khi nhận thay đổi.
- 403 không được cache thành not-found.
- Cache key phải bao gồm provider/account/bucket/key và version nếu có.

Resource mặc định không phải cache layer và không bảo đảm snapshot bất biến. Nếu cần đọc đúng một phiên bản, locator phải mang version ID/generation hoặc adapter phải nhận version rõ ràng.

### 11.3. Không giữ InputStream trong cache

Cache Resource handle có thể chấp nhận nếu resource immutable về locator/client; cache InputStream đang mở thường không an toàn. InputStream có cursor và lifecycle riêng, không tái sử dụng giữa request hoặc thread. Mỗi lần đọc hãy mở stream mới theo contract của implementation và đóng đúng cách.

## 12. Error mapping và observability

### 12.1. Phân biệt lỗi theo nguyên nhân

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Not found | S3 404/NoSuchKey, Blob not found | Trả not-found theo contract nghiệp vụ |
| Forbidden | IAM deny, bucket policy, KMS decrypt deny | Không retry mù; kiểm tra identity và resource policy |
| Network timeout | Connect/read timeout | Retry có giới hạn nếu thao tác idempotent và deadline còn |
| Throttling | Request rate vượt quota | Backoff + jitter, giới hạn concurrency |
| Invalid URI | Scheme, bucket hoặc key không hợp lệ | Từ chối input; không gọi provider |
| Serialization/processing | Parser không đọc được nội dung | Ghi nhận lỗi dữ liệu; tránh retry cùng bytes vô hạn |
| Resource changed | Object bị overwrite/delete giữa HEAD và GET | Dùng version/conditional read khi cần snapshot |

Không bắt mọi exception rồi trả `Optional.empty()` hoặc `null`; làm vậy khiến 403, timeout và bug cấu hình bị hiểu nhầm thành tài nguyên không tồn tại.

### 12.2. Log và metric

Log theo cấu trúc với:

- Provider, bucket/container đã được phép log, object key đã mask nếu nhạy cảm.
- Operation: resolve, head, get, list hoặc write.
- Correlation ID, tenant ID nội bộ và request ID provider nếu có.
- Latency, bytes read, status/error code và retry count.
- Cache hit/miss và số stream đang mở nếu có instrumentation.

Không log credential, SAS token, presigned query string hoặc nội dung tài liệu. Theo dõi latency p50/p95/p99, số request HEAD/GET, bytes, throttling, 4xx/5xx, stream leak và pool saturation. Có thể dùng Micrometer để đưa metric vào hệ thống quan sát của ứng dụng.
## 13. Kiểm thử Resource adapter

### 13.1. Unit test URI resolver

Kiểm tra:

1. `s3://bucket/key` tạo đúng S3ObjectResource.
2. Scheme khác trả null để resolver khác xử lý.
3. Thiếu bucket/key bị từ chối.
4. URI có user info, port, query hoặc fragment bị từ chối.
5. Key có dấu slash và ký tự percent-encoded được giữ theo quy ước.
6. URI không hợp lệ không làm SDK request được gửi.

### 13.2. Unit test S3ObjectResource với mock

Mock `S3Client` để xác minh:

- `getInputStream()` gọi `GetObject` đúng bucket/key.
- Caller đóng stream và response body được giải phóng.
- `exists()` trả false với 404 và không biến 403 thành false.
- `contentLength()`/`lastModified()` ánh xạ metadata đúng.
- `getFile()` luôn báo không phải local file.
- Lỗi SDK được ánh xạ thành IOException/runtime exception theo contract.

### 13.3. LocalStack và staging

LocalStack có thể giúp kiểm tra luồng S3 cơ bản trong local/CI: tạo bucket, put object, resolve `s3://` và đọc nội dung. Tuy nhiên, không giả định emulator mô phỏng đầy đủ IAM policy evaluation, KMS key policy, cross-account access, VPC endpoint, versioning, lifecycle, Object Lock hoặc mọi error code của AWS.

AWS staging nên xác minh workload role thật, bucket policy, KMS encryption, Region, endpoint và quyền object-level. Dùng một object test không chứa dữ liệu nhạy cảm, giới hạn chi phí và xóa tài nguyên test sau khi hoàn tất.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NoResourceFoundException` hoặc resource được coi là classpath | Chưa đăng ký ProtocolResolver vào loader đang dùng | Inject đúng `cloudResourceLoader` hoặc tích hợp resolver vào ApplicationContext |
| `getFile()` ném FileNotFoundException | Cloud object không phải local file | Dùng `getInputStream()` hoặc copy vào temp file có quản lý |
| `exists()` trả false nhưng object có thật | Principal không có quyền HEAD/GetObject hoặc provider không tiết lộ existence | Kiểm tra IAM/bucket policy; phân biệt 403 với 404 |
| `AccessDenied` | Thiếu IAM, bucket, KMS hoặc tenant prefix permission | Kiểm tra role, resource policy, KMS key policy và key |
| `Connection pool exhausted` khi đọc nhiều object | Stream không được đóng hoặc concurrency quá cao | try-with-resources, giới hạn concurrency và theo dõi pool |
| HEAD thành công nhưng GET thất bại | Object thay đổi, permission khác hoặc lỗi mạng ở thời điểm GET | Xử lý lỗi GET; dùng version/conditional read nếu cần |
| Resource pattern không tìm thấy object | ProtocolResolver chỉ resolve một location, không list wildcard | Implement ResourcePatternResolver/provider listing riêng |
| URI có khoảng trắng/Unicode bị sai key | Encode/decode không thống nhất | Chuẩn hóa URI theo RFC 3986 và test object key thực |
| Signed URL hết hạn | Dùng URL tạm thời như locator lâu dài | Lưu bucket/key/version; tạo signed URL khi cần truy cập |

## 15. Bài tập tự luyện

1. Viết một service đọc nội dung từ `classpath:`, `file:` và `s3:` bằng cùng method nhận `Resource`; giải thích vì sao không gọi `getFile()`.
2. Tạo `S3ObjectResource` với `getInputStream()`, `exists()`, `contentLength()`, `lastModified()` và xử lý not-found/forbidden.
3. Viết `S3ProtocolResolver` để parse `s3://bucket/key`; bổ sung test URI sai, query string và key có Unicode.
4. Đăng ký resolver trong `DefaultResourceLoader` riêng, inject bằng `@Qualifier` và chứng minh loader mặc định không tự hiểu scheme S3.
5. Đọc một object lớn theo streaming và đo heap usage so với `readAllBytes()`; xác minh stream được đóng khi lỗi/cancel.
6. Thiết kế `DocumentReader` và `DocumentWriter` riêng; giải thích vì sao `Resource` không thay thế upload/multipart API.
7. So sánh AWS S3, Google Cloud Storage và Azure Blob Storage về locator, identity, metadata, version và stream semantics.
8. Dùng LocalStack kiểm thử object read, sau đó kiểm thử staging bằng IAM role và SSE-KMS.
9. Thiết kế cache metadata có TTL và version-aware key; xác định cách xử lý overwrite/delete và permission error.
10. Thiết kế tenant isolation cho URI object: bucket allow-list, prefix authorization và cách chống caller truy cập object của tenant khác.

**Tiêu chí hoàn thành:** người học giải thích được Resource/ResourceLoader/ProtocolResolver, xây dựng được resolver cloud URI cho một provider, đọc object an toàn qua stream, xử lý metadata và lỗi đúng semantics, phân biệt read/write, và chứng minh tenant access được kiểm soát trong test.

## Tài liệu tham khảo

- [Spring Framework — Resources](https://docs.spring.io/spring-framework/reference/core/resources.html): Resource abstraction, ResourceLoader và resource path.
- [Spring Framework — Resource interface API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/Resource.html): contract của Resource.
- [Spring Framework — ResourceLoader API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/ResourceLoader.html): getResource và location prefix.
- [Spring Framework — ProtocolResolver API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/ProtocolResolver.html): extension point cho protocol tùy chỉnh.
- [Spring Framework — DefaultResourceLoader API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/io/DefaultResourceLoader.html): đăng ký protocol resolver.
- [Spring Cloud AWS — S3 reference](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): tích hợp S3 và các abstraction theo release.
- [AWS SDK for Java 2.x — Amazon S3 examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3.html): S3 client, GetObject và metadata operations.
- [Google Cloud Storage — Java client](https://cloud.google.com/storage/docs/reference/libraries#client-libraries-install-java): SDK Java và object read.
- [Azure Storage Blob — Java SDK](https://learn.microsoft.com/azure/storage/blobs/storage-blob-java-get-started): BlobClient, metadata và streaming.
