# Upload và download tệp qua Object Storage trong ứng dụng

Trong chương **Triển khai Java và Spring Boot** của module **CLOUD_PROVIDERS_ORACLE**, bài này xây dựng chức năng nhận và trả tệp bằng OCI Object Storage. Ứng dụng dùng bucket riêng tư, tự xác định object key và gọi OCI bằng danh tính có quyền giới hạn.

Tình huống thực hành là một API cho người dùng lưu tài liệu cá nhân: người A upload tệp rồi tải lại bằng mã tệp; người B không được dùng mã đó để đọc nội dung của A. Tệp được đặt ngoài ổ đĩa của instance để ứng dụng có thể thay instance hoặc chạy nhiều replica mà vẫn truy cập cùng dữ liệu.

Sau bài học, người học có thể:

- Phân biệt danh tính người dùng ứng dụng với danh tính OCI dùng để gọi Object Storage.
- Cấu hình OCI Java SDK cho máy phát triển và OCI Compute.
- Upload tệp có giới hạn dung lượng, tải xuống theo stream và đóng tài nguyên đúng chỗ.
- Lựa chọn giữa truyền tệp qua backend, Pre-Authenticated Request và multipart upload của OCI.
- Xử lý lỗi, theo dõi vận hành và đặt giới hạn chi phí cho chức năng lưu tệp.

## 1. Những thành phần cần phân biệt

| Thành phần | Ý nghĩa trong bài |
| --- | --- |
| Tenancy | Phạm vi quản trị OCI chứa các tài nguyên và chính sách liên quan |
| Compartment | Nơi đặt bucket và phạm vi áp dụng policy |
| Namespace | Định danh Object Storage của tenancy; không thay bằng tenancy OCID hoặc tên compartment |
| Region | Vùng chứa bucket mà SDK cần kết nối |
| Bucket | Vùng chứa object, ví dụ `app-private-files` |
| Object key | Tên đầy đủ của một object trong bucket, ví dụ `users/<owner-hash>/<file-id>` |
| OCI principal | Danh tính được IAM cho phép gọi API OCI |
| Application principal | Người dùng đã được Spring Security xác thực; dùng để quyết định được đọc tệp nào |

Dấu `/` trong object key giúp tổ chức tên theo prefix. Nó không tạo một thư mục có quyền truy cập độc lập như trên hệ thống tệp. Backend vẫn phải kiểm tra quyền ở từng thao tác.

Một locator đầy đủ về mặt ứng dụng cần biết region, namespace, bucket và object key. UUID mà API trả về chỉ là mã nghiệp vụ; backend dùng UUID cùng danh tính người dùng để tạo object key. Không yêu cầu client gửi namespace, bucket hay object key.

Trong hệ thống có lưu trữ metadata, nên phân tách dữ liệu như sau:

| Dữ liệu | Nơi lưu phù hợp |
| --- | --- |
| Nội dung tệp | Object Storage |
| Chủ sở hữu, trạng thái kiểm tra tệp, tên tải xuống, loại nội dung đã xác minh | Cơ sở dữ liệu ứng dụng |
| Namespace, bucket, region | Cấu hình triển khai |
| API signing key khi phát triển | Kho cấu hình được bảo vệ ngoài repository |
| Quyền gọi OCI trên Compute | Instance principal kết hợp dynamic group và IAM policy |

Không dùng đường dẫn tệp trong container làm nơi lưu lâu dài khi chạy nhiều replica. Dung lượng tạm phục vụ xử lý multipart HTTP vẫn cần được cấp và giám sát riêng.

## 2. Luồng truyền tệp qua Spring Boot

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Spring Boot API
    participant S as OCI Object Storage
    U->>A: POST /api/files + Bearer token + multipart/form-data
    A->>A: Xác thực, kiểm tra dung lượng, tạo fileId và object key
    A->>S: PutObject bằng OCI principal
    S-->>A: ETag và request ID
    A-->>U: 201 Created + fileId
    U->>A: GET /api/files/{fileId} + Bearer token
    A->>A: Tạo key từ chủ thể đã xác thực và fileId
    A->>S: GetObject
    S-->>A: Metadata và InputStream
    A-->>U: Truyền từng phần nội dung
    A->>A: Đóng InputStream của OCI
~~~

Hai lớp quyền cùng tồn tại:

1. **Spring Security** xác định người đang gọi API và tài nguyên mà người đó được phép sử dụng.
2. **OCI IAM** cho phép tiến trình backend thao tác với bucket.

OCI chỉ nhìn thấy danh tính backend trong luồng này. Việc backend có quyền `OBJECT_READ` không có nghĩa mọi người dùng ứng dụng đều được đọc mọi object.

Truyền tệp qua backend phù hợp khi cần kiểm tra quyền ở mỗi lần tải, kiểm soát nội dung trả về hoặc không muốn phát URL truy cập trực tiếp. Đổi lại, backend chịu thêm lưu lượng mạng, kết nối và thời gian giữ request.

## 3. Chuẩn bị OCI

### 3.1. Bucket và cấu hình

Dùng một bucket **private**, tier Standard cho bài thực hành. Ghi nhận namespace, region và bucket name từ môi trường OCI thực tế. Ví dụ trong bài dùng tên `app-private-files` và region `ap-singapore-1`; cần thay bằng tài nguyên của mình.

Bucket được tạo trước bởi người quản trị hoặc quy trình cấp hạ tầng. Backend của bài không cần quyền tạo bucket, liệt kê bucket hay tự khám phá namespace.

Giữ HTTPS cho kết nối đến OCI và cho API khi triển khai. Không đặt tệp riêng tư vào bucket public để làm cho đường dẫn tải xuống hoạt động.

### 3.2. Instance principal và quyền tối thiểu

Với ứng dụng chạy trên OCI Compute, có thể tạo dynamic group `java-file-app` chỉ khớp instance được giao chạy ứng dụng:

~~~text
ALL {instance.id = '<APP_INSTANCE_OCID>'}
~~~

Thay placeholder bằng OCID thực. Tên dynamic group và cách định danh theo identity domain phải phù hợp tenancy đang dùng.

Ví dụ policy tại phạm vi có hiệu lực với compartment `app-data`:

~~~text
Allow dynamic-group java-file-app to manage objects in compartment app-data where all {target.bucket.name = 'app-private-files', any {request.permission = 'OBJECT_CREATE', request.permission = 'OBJECT_READ'}}
~~~

Policy này chỉ cấp hai permission đã lọc. Code tạo object mới, dùng `ifNoneMatch("*")` và không cung cấp API ghi đè hoặc xóa.

| Thao tác | Permission cần xét |
| --- | --- |
| `PutObject` tạo tên mới | `OBJECT_CREATE` |
| `GetObject` | `OBJECT_READ` |
| Ghi đè object có sẵn | `OBJECT_OVERWRITE` |
| Xóa object | `OBJECT_DELETE` |

Khi thêm chức năng mới, bổ sung quyền tương ứng sau khi xác định nhu cầu. Không thay policy bằng quyền quản trị toàn tenancy. Tham chiếu: [OCI Object Storage policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

Trên máy phát triển, dùng API signing key và profile OCI của một user được cấp quyền tương đương qua group. Không đưa private key, passphrase hoặc nội dung `~/.oci/config` vào mã nguồn, image hay ví dụ log.

Instance principal áp dụng cho môi trường Compute tương ứng. Khi chuyển sang Functions hoặc OKE, chọn cơ chế danh tính phù hợp với nền tảng và cấu hình IAM riêng. Không giả định provider của Compute hoạt động ở mọi môi trường.

### 3.3. Đường mạng từ ứng dụng

Ứng dụng phải phân giải DNS và kết nối được đến endpoint Object Storage đúng region qua HTTPS.

Nếu Compute nằm trong private subnet, một cách triển khai là Service Gateway cùng route tới service CIDR thích hợp của Oracle Services Network. Kiểm tra thêm egress rule của NSG/security list và tường lửa hệ điều hành. Service Gateway không thay thế quyền IAM và không tự cung cấp kết nối đến mọi địa chỉ Internet, chẳng hạn identity provider bên ngoài. Tham chiếu: [Access to Oracle Services: Service Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/servicegateway.htm).

Với local development, máy phát triển cần đường mạng đến OCI và identity provider dùng trong ví dụ. Lỗi timeout mạng cần được tách khỏi lỗi bị IAM từ chối.

## 4. Cấu hình dự án Spring Boot

Mẫu dùng **Java 21, Spring Boot 3.5.x, Spring MVC và OCI Java SDK 3.102.0**. Đây là phiên bản SDK được ghim cho ví dụ; khi nâng cấp, đồng bộ các artifact OCI bằng BOM và kiểm tra tương thích dependency của dự án.

Các đoạn mã thuộc package `example.files`, đặt trong các tệp Java có tên tương ứng. Phần Maven sau được thêm vào `pom.xml` của dự án Spring Boot đã quản lý phiên bản Spring:

~~~xml
<properties>
    <java.version>21</java.version>
    <oci-java-sdk.version>3.102.0</oci-java-sdk.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.oracle.oci.sdk</groupId>
            <artifactId>oci-java-sdk-bom</artifactId>
            <version>${oci-java-sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>com.oracle.oci.sdk</groupId>
        <artifactId>oci-java-sdk-objectstorage</artifactId>
    </dependency>
    <dependency>
        <groupId>com.oracle.oci.sdk</groupId>
        <artifactId>oci-java-sdk-common-httpclient-jersey3</artifactId>
    </dependency>
</dependencies>
~~~

OCI SDK 3 yêu cầu chọn HTTP client implementation. Ví dụ chọn Jersey 3, phù hợp hệ sinh thái Jakarta của Spring Boot 3. Tránh thêm đồng thời nhiều implementation nếu không có chủ đích. Tham chiếu: [Getting Started with the Java SDK](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm).

Cấu hình ứng dụng:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 11MB
      file-size-threshold: 0B
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OIDC_ISSUER_URI}
          audiences:
            - ${OIDC_AUDIENCE}

app:
  oci:
    storage:
      region: ${OCI_REGION}
      namespace: ${OCI_NAMESPACE}
      bucket: ${OCI_BUCKET}
      auth-mode: ${OCI_AUTH_MODE:config-file}
      config-file: ${OCI_CONFIG_FILE:~/.oci/config}
      config-profile: ${OCI_CONFIG_PROFILE:DEFAULT}
~~~

`max-request-size` lớn hơn `max-file-size` để chừa chỗ cho phần đóng gói multipart. `file-size-threshold: 0B` cấu hình ngưỡng chuyển nội dung multipart sang đĩa tạm; đây không phải lời hứa rằng toàn bộ đường truyền HTTP không có bộ đệm. Giám sát dung lượng đĩa tạm, số upload đồng thời và giới hạn của reverse proxy. Tham chiếu: [Spring Boot MultipartProperties](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html).

Trên Compute, đặt `OCI_AUTH_MODE=instance-principal`. Trên máy phát triển, đặt `OCI_AUTH_MODE=config-file` và chuẩn bị profile OCI bên ngoài repository.

### 4.1. Khởi động ứng dụng và tạo client dùng chung

~~~java
package example.files;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FileApplication {
    public static void main(String[] args) {
        SpringApplication.run(FileApplication.class, args);
    }
}
~~~

~~~java
package example.files;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.oci.storage")
public record StorageProperties(
        String region,
        String namespace,
        String bucket,
        String authMode,
        String configFile,
        String configProfile) {
}
~~~

~~~java
package example.files;

import com.oracle.bmc.ClientConfiguration;
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.AbstractAuthenticationDetailsProvider;
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.auth.InstancePrincipalsAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorageClient;
import java.io.IOException;
import java.util.stream.Stream;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(StorageProperties.class)
public class OciStorageConfiguration {

    @Bean(destroyMethod = "close")
    ObjectStorageClient objectStorageClient(StorageProperties properties)
            throws IOException {
        if (Stream.of(properties.region(), properties.namespace(),
                properties.bucket(), properties.authMode())
                .anyMatch(value -> value == null || value.isBlank())) {
            throw new IllegalArgumentException("Thiếu cấu hình OCI Object Storage");
        }

        AbstractAuthenticationDetailsProvider provider =
                switch (properties.authMode()) {
                    case "instance-principal" ->
                            InstancePrincipalsAuthenticationDetailsProvider
                                    .builder().build();
                    case "config-file" ->
                            new ConfigFileAuthenticationDetailsProvider(
                                    properties.configFile(),
                                    properties.configProfile());
                    default -> throw new IllegalArgumentException(
                            "auth-mode phải là config-file hoặc instance-principal");
                };

        ClientConfiguration configuration = ClientConfiguration.builder()
                .connectionTimeoutMillis(3_000)
                .readTimeoutMillis(60_000)
                .build();

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .configuration(configuration)
                .build(provider);
    }
}
~~~

Tạo một client dùng chung cho cấu hình region của ứng dụng và đóng khi Spring shutdown. Không tạo client mới cho từng request hoặc đổi region của client dùng chung trong lúc xử lý request. Các timeout trên là ví dụ cấu hình kết nối/đọc của SDK; cần đặt thêm ngân sách thời gian cho toàn request ở tầng ứng dụng và proxy. Tham chiếu: [OCI Java SDK overview](https://docs.oracle.com/en-us/iaas/tools/java/latest/index.html).

### 4.2. Bảo vệ API bằng Bearer token

~~~java
package example.files;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .csrf(csrf -> csrf.disable())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Mẫu là API dùng access token trong header `Authorization: Bearer ...`, không dùng cookie làm cơ chế xác thực, vì vậy cấu hình CSRF như trên chỉ áp dụng cho mô hình đó. `issuer-uri` và `audiences` phải là issuer và audience thực của API. Spring kiểm tra token trước khi controller nhận danh tính; không nhận `ownerId` do client tự khai báo để quyết định quyền tệp. Tham chiếu: [Spring Boot security configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html) và [JWT resource server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).

Trong mẫu, `Principal.getName()` dùng định danh subject mặc định của JWT thuộc một issuer đã cấu hình. Nếu thay cơ chế ánh xạ principal hoặc chấp nhận nhiều issuer, phải điều chỉnh cách xác định chủ sở hữu cho ổn định và tránh trùng subject giữa các issuer.

## 5. Upload: khóa do server tạo, dung lượng được giới hạn

Ví dụ tối thiểu không lưu tên tệp gốc và không hiển thị nội dung trực tiếp trong trình duyệt. Mọi tệp được lưu với `application/octet-stream` và tải xuống dưới dạng attachment tên `<file-id>.bin`. Cách này giữ ví dụ tập trung vào luồng dữ liệu và quyền sở hữu; khi cần giữ tên gốc, bổ sung metadata có kiểm soát như phần sau.

Object key có cấu trúc:

~~~text
users/<SHA-256 của subject>/<UUID do server tạo>
~~~

Hash giúp không đưa nguyên văn subject vào object key; đây không phải cơ chế mã hóa hay bảo đảm ẩn danh. Quyền sở hữu đến từ việc server luôn tạo prefix dựa trên principal đã xác thực. UUID khó đoán cũng không thay thế kiểm tra quyền.

~~~java
package example.files;

import com.oracle.bmc.objectstorage.ObjectStorageClient;
import com.oracle.bmc.objectstorage.requests.GetObjectRequest;
import com.oracle.bmc.objectstorage.requests.PutObjectRequest;
import com.oracle.bmc.objectstorage.responses.GetObjectResponse;
import com.oracle.bmc.objectstorage.responses.PutObjectResponse;
import com.oracle.bmc.retrier.RetryConfiguration;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
public class FileStorageService {

    private static final long MAX_FILE_BYTES = 10L * 1024 * 1024;

    private final ObjectStorageClient client;
    private final StorageProperties properties;

    public FileStorageService(ObjectStorageClient client,
                              StorageProperties properties) {
        this.client = client;
        this.properties = properties;
    }

    public UploadReceipt upload(String subject, MultipartFile file)
            throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Tệp không được rỗng");
        }
        if (file.getSize() > MAX_FILE_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "Tệp vượt quá 10 MiB");
        }

        UUID id = UUID.randomUUID();
        String key = objectKey(subject, id);

        try (InputStream input = file.getInputStream()) {
            PutObjectRequest request = PutObjectRequest.builder()
                    .namespaceName(properties.namespace())
                    .bucketName(properties.bucket())
                    .objectName(key)
                    .contentLength(file.getSize())
                    .contentType("application/octet-stream")
                    .ifNoneMatch("*")
                    .opcClientRequestId(UUID.randomUUID().toString())
                    .retryConfiguration(RetryConfiguration.NO_RETRY_CONFIGURATION)
                    .putObjectBody(input)
                    .build();

            PutObjectResponse result = client.putObject(request);
            return new UploadReceipt(id, file.getSize(), result.getETag());
        }
    }

    // Caller phải đóng InputStream trong response sau khi sử dụng.
    public GetObjectResponse open(String subject, UUID id) {
        return client.getObject(GetObjectRequest.builder()
                .namespaceName(properties.namespace())
                .bucketName(properties.bucket())
                .objectName(objectKey(subject, id))
                .opcClientRequestId(UUID.randomUUID().toString())
                .build());
    }

    private String objectKey(String subject, UUID id) {
        if (subject == null || subject.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "Thiếu danh tính người dùng");
        }

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(subject.getBytes(StandardCharsets.UTF_8));
            String ownerHash = HexFormat.of().formatHex(digest);
            return "users/" + ownerHash + "/" + id;
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                    "Runtime không hỗ trợ SHA-256", exception);
        }
    }

    public record UploadReceipt(UUID id, long size, String eTag) {
    }
}
~~~

Những quyết định cần giữ khi áp dụng vào hệ thống thực:

- **Không dùng `file.getBytes()` hoặc `readAllBytes()`** để giữ toàn tệp trong heap. Stream được đóng sau khi SDK hoàn thành thao tác.
- **Truyền đúng `contentLength`** lấy từ tệp multipart mà framework đã tiếp nhận. Không lấy một header tùy ý của client làm số byte đáng tin cậy.
- **Không dùng tên gốc làm key.** Hai người upload `report.pdf` không được ghi đè lẫn nhau; tên chứa đường dẫn hoặc ký tự điều khiển cũng không đi vào key.
- **Không cho ghi đè vô tình.** `ifNoneMatch("*")` làm yêu cầu thất bại nếu key đã tồn tại. Nếu cần cập nhật một object, thiết kế riêng quyền ghi đè và điều kiện ETag.
- **Không tự retry một stream đã đọc dở.** Mẫu đặt cấu hình không retry ở request `PutObject` để làm rõ trách nhiệm này. Khi muốn retry, cần nguồn dữ liệu đọc lại được và cơ chế xác định kết quả trước đó.

API `PutObject` thông thường có thể ghi đè tên đã tồn tại; điều kiện tạo mới trong ví dụ là chủ đích của ứng dụng. Tham chiếu: [PutObjectRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/requests/PutObjectRequest.Builder.html).

`MultipartFile` trong Spring là một phần của HTTP `multipart/form-data`. Nó chưa có nghĩa ứng dụng đang dùng **multipart upload của OCI**. Ở ví dụ này backend gọi một `PutObject` cho mỗi tệp.

## 6. Download: kiểm tra chủ sở hữu trước, truyền stream sau

Controller chỉ nhận UUID. Service tạo lại key bằng subject của người đang gọi. Nếu người B gửi UUID của A, service sẽ tìm trong prefix của B, không dùng prefix của A.

~~~java
package example.files;

import com.oracle.bmc.objectstorage.responses.GetObjectResponse;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.security.Principal;
import java.util.UUID;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/files")
public class FileController {

    private final FileStorageService storage;

    public FileController(FileStorageService storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<FileStorageService.UploadReceipt> upload(
            @RequestPart("file") MultipartFile file,
            Principal principal) throws IOException {
        FileStorageService.UploadReceipt receipt =
                storage.upload(principal.getName(), file);

        return ResponseEntity
                .created(URI.create("/api/files/" + receipt.id()))
                .body(receipt);
    }

    @GetMapping("/{id}")
    public void download(@PathVariable("id") UUID id,
                         Principal principal,
                         HttpServletResponse response) throws IOException {
        // Gọi OCI trước khi ghi header/body thành công cho client.
        GetObjectResponse object = storage.open(principal.getName(), id);

        try (InputStream input = object.getInputStream()) {
            response.setContentType(MediaType.APPLICATION_OCTET_STREAM_VALUE);
            response.setHeader(HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                            .filename(id + ".bin")
                            .build().toString());
            response.setHeader(HttpHeaders.CACHE_CONTROL, "private, no-store");
            response.setHeader("X-Content-Type-Options", "nosniff");

            if (object.getContentLength() != null) {
                response.setContentLengthLong(object.getContentLength());
            }

            input.transferTo(response.getOutputStream());
        }
    }
}
~~~

`GetObjectResponse` cung cấp `InputStream` cùng thông tin như dung lượng và ETag. Ứng dụng phải đóng stream để giải phóng kết nối SDK; container quản lý output stream HTTP của response. Tham chiếu: [GetObjectResponse](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/responses/GetObjectResponse.html).

Không mở stream trong một khối `try` rồi trả chính stream đó ra ngoài sau khi nó đã bị đóng. Với `StreamingResponseBody`, nơi đóng stream phải nằm trong quá trình thực thi callback và cần quản lý cả trường hợp tác vụ không được thực thi hoặc bị hủy. Ví dụ dùng MVC đồng bộ để vòng đời tài nguyên dễ quan sát.

Cách truyền trên không nạp toàn tệp vào heap, nhưng vẫn giữ một servlet thread trong suốt lần tải. Khả năng phục vụ nhiều download đồng thời phụ thuộc pool kết nối SDK, thread, băng thông, giới hạn proxy và tốc độ nhận của client.

### 6.1. Khi cần giữ tên và loại nội dung

Với chức năng hoàn chỉnh, lưu metadata theo `fileId` trong cơ sở dữ liệu:

~~~text
file_id, owner_id, object_key, original_name, verified_content_type,
size_bytes, sha256, etag, status, created_at
~~~

Trước download, truy vấn `file_id` cùng `owner_id` hoặc quyền chia sẻ được cấp, kiểm tra `status=AVAILABLE` rồi mới gọi OCI.

Tên gốc chỉ phục vụ hiển thị và `Content-Disposition`. Cần giới hạn chiều dài, loại ký tự điều khiển, xử lý dấu phân cách đường dẫn và dùng API xây header an toàn. Không ghép thẳng tên do client gửi vào một header HTTP.

`MultipartFile.getContentType()` và phần mở rộng chỉ là dữ liệu do bên gửi khai báo. Nếu ứng dụng chỉ nhận PDF hoặc hình ảnh, kiểm tra allowlist, chữ ký nội dung và các điều kiện nghiệp vụ trước khi công bố tệp. Nếu cần quét mã độc, dùng trạng thái cách ly; chỉ cho tải sau khi tệp được xác nhận.

### 6.2. Cache, Range và nội dung tải dở

Mẫu dùng `private, no-store` để không lưu cache tài liệu riêng tư. Nếu cần cache hoặc tải tiếp, thiết kế thêm theo hợp đồng HTTP:

| Nhu cầu | Việc cần làm |
| --- | --- |
| Cache có điều kiện | Ánh xạ ETag đúng định dạng HTTP, xử lý điều kiện và trả `304` khi thích hợp |
| Tải một khoảng byte | Kiểm tra `Range`, truyền khoảng hợp lệ cho OCI, trả `206` cùng `Content-Range` và độ dài đoạn |
| Khoảng không hợp lệ | Trả `416` theo kích thước object |
| Tải tiếp khi object có thể thay đổi | Gắn phiên bản hoặc ETag để tránh ghép các đoạn của hai nội dung khác nhau |

OCI có hỗ trợ tham số range và điều kiện ETag trong API đọc. Controller ở trên trả toàn bộ tệp và chưa triển khai hợp đồng tải tiếp; không thêm `Accept-Ranges: bytes` khi chưa có phần xử lý tương ứng. Tham chiếu: [GetObjectRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/requests/GetObjectRequest.Builder.html).

## 7. Ánh xạ lỗi và giữ kết nối ổn định

Một exception từ OCI là lỗi ở ranh giới backend–storage. Đừng trả toàn bộ message, stack trace, đường dẫn key hoặc cấu hình credential ra client.

~~~java
package example.files;

import com.oracle.bmc.model.BmcException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class FileApiErrors {

    private static final Logger log =
            LoggerFactory.getLogger(FileApiErrors.class);

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ProblemDetail> fileTooLarge() {
        return problem(HttpStatus.PAYLOAD_TOO_LARGE,
                "Yêu cầu upload vượt giới hạn dung lượng");
    }

    @ExceptionHandler(BmcException.class)
    ResponseEntity<ProblemDetail> storageFailure(BmcException exception) {
        log.warn("OCI Object Storage failure: status={}, code={}, requestId={}",
                exception.getStatusCode(),
                exception.getServiceCode(),
                exception.getOpcRequestId());

        HttpStatus status = switch (exception.getStatusCode()) {
            case 404 -> HttpStatus.NOT_FOUND;
            case 409, 412 -> HttpStatus.CONFLICT;
            case 429, 500, 502, 503, 504 -> HttpStatus.SERVICE_UNAVAILABLE;
            default -> HttpStatus.BAD_GATEWAY;
        };

        String detail = status == HttpStatus.NOT_FOUND
                ? "Không tìm thấy tệp khả dụng"
                : "Không hoàn tất được thao tác lưu trữ";

        return problem(status, detail);
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String detail) {
        return ResponseEntity.status(status)
                .body(ProblemDetail.forStatusAndDetail(status, detail));
    }
}
~~~

Đây là ánh xạ tối thiểu. Mã `404` từ OCI có thể liên quan tài nguyên không tồn tại hoặc việc không có quyền nhìn thấy tài nguyên; API trả thông báo chung, còn vận hành dùng request ID để điều tra. Lỗi OCI `401/403` thường đòi hỏi kiểm tra danh tính và policy của backend, không yêu cầu người dùng ứng dụng đăng nhập lại một cách máy móc.

Nếu lỗi phát sinh khi đã ghi một phần body download, không thể chuyển response đang truyền thành một JSON lỗi sạch. Cần kết thúc luồng lỗi phù hợp ở container, đóng stream và ghi nhận download chưa hoàn tất. Không bắt mọi `IOException` rồi tiếp tục ghi JSON nối vào nội dung tệp.

Tránh retry download từ byte đầu sau khi đã gửi một phần dữ liệu cho client. Nếu muốn phục hồi ở mức ứng dụng, phải có giao thức range và kiểm tra phiên bản nội dung.

Các lỗi xác thực ở Spring Security xảy ra trước controller; `@RestControllerAdvice` trên không thay thế cấu hình xử lý lỗi của security filter chain.

## 8. Thực hành gọi API

Chuẩn bị bucket private, quyền OCI, một identity provider và access token có issuer/audience đúng như cấu hình. Ví dụ PowerShell dưới đây giả định ứng dụng đã khởi động ở `http://localhost:8080` và biến `APP_TOKEN` chứa token hợp lệ. Khi triển khai thực tế, dùng địa chỉ API HTTPS.

Thiết lập các giá trị cho local development bằng thông tin thật của môi trường:

~~~powershell
$env:OCI_REGION = "ap-singapore-1"
$env:OCI_NAMESPACE = "<namespace-cua-tenancy>"
$env:OCI_BUCKET = "app-private-files"
$env:OCI_AUTH_MODE = "config-file"
$env:OCI_CONFIG_PROFILE = "DEFAULT"
$env:OIDC_ISSUER_URI = "<issuer-uri-thuc>"
$env:OIDC_AUDIENCE = "<audience-cua-api>"
~~~

Các biến môi trường phải có trước khi khởi động tiến trình Java; thay đổi biến trong một terminal khác không cập nhật cấu hình của tiến trình đang chạy.

Upload tệp có sẵn trong thư mục hiện tại:

~~~powershell
curl.exe --fail-with-body --show-error `
  -H "Authorization: Bearer $env:APP_TOKEN" `
  -F "file=@.\sample.txt" `
  http://localhost:8080/api/files
~~~

Response thành công có status `201 Created`, header `Location` và body dạng:

~~~json
{
  "id": "6cb4e5b1-d59d-4c48-8d35-630f3a67bf51",
  "size": 128,
  "eTag": "<etag-do-oci-tra-ve>"
}
~~~

Giá trị `size` ở trên chỉ minh họa. Dùng `id` thật của lần upload để tải:

~~~powershell
$fileId = "<id-tu-response-upload>"

curl.exe --fail-with-body --show-error `
  -H "Authorization: Bearer $env:APP_TOKEN" `
  -D .\download-headers.txt `
  -o .\downloaded.bin `
  "http://localhost:8080/api/files/$fileId"

if ($LASTEXITCODE -ne 0) {
    throw "Download thất bại; kiểm tra HTTP status trước khi dùng tệp kết quả"
}
~~~

Chỉ sau khi HTTP download thành công mới so sánh nội dung:

~~~powershell
$sourceHash = (Get-FileHash -LiteralPath .\sample.txt -Algorithm SHA256).Hash
$downloadHash = (Get-FileHash -LiteralPath .\downloaded.bin -Algorithm SHA256).Hash

if ($sourceHash -ne $downloadHash) {
    throw "Nội dung tải xuống không khớp tệp nguồn"
}
~~~

ETag là định danh phiên bản/nội dung theo hợp đồng dịch vụ, không nên mặc định coi là SHA-256 của tệp hoặc checksum MD5 trong mọi phương thức upload. Nếu nghiệp vụ cần checksum, lưu thuật toán và digest rõ ràng; phép so sánh SHA-256 ở trên kiểm tra trực tiếp hai tệp.

Các tình huống thực hành cần quan sát:

| Tình huống | Kết quả cần thấy |
| --- | --- |
| Token hợp lệ, tệp nhỏ hơn giới hạn | Upload `201`; download trả đúng byte |
| Không có token | Bị security filter từ chối trước controller |
| UUID không đúng định dạng | Request không được xử lý như một object key tùy ý |
| Tệp rỗng | `400` theo service |
| Tệp vượt giới hạn | `413` tại ứng dụng hoặc tầng proxy được cấu hình tương ứng |
| Người B dùng ID của người A | Không nhận được nội dung của A; mẫu trả thông báo không tìm thấy |
| Hai lần upload cùng tên gốc | Hai ID khác nhau, không ghi đè nhau |
| Backend thiếu quyền OCI | Nhận lỗi storage; log nội bộ chứa request ID để điều tra |
| Ngắt kết nối trong khi tải | Stream được đóng và lần tải không được tính là hoàn tất |
| Tải từ replica thứ hai | Vẫn đọc được nếu cấu hình bucket và danh tính người dùng nhất quán |

Đây là hướng dẫn thực hành cho người học, không phải tuyên bố ví dụ đã được chạy trên tenancy của họ.

## 9. Kết quả upload không rõ ràng và tính nhất quán với cơ sở dữ liệu

`PutObject` có thể đã được OCI chấp nhận nhưng response không đến backend vì lỗi mạng. Không thể kết luận “object chưa tồn tại” chỉ từ một timeout.

Mẫu tạo UUID mới cho mỗi lần upload và chưa có cơ chế idempotency bền vững. Nếu client không nhận được response rồi gửi lại, hệ thống có thể tạo hai object. Nếu response đầu tiên bị mất, client cũng có thể không biết ID của object đầu tiên để truy cập lại.

Khi đưa vào sản phẩm, thiết kế một phiên upload trong cơ sở dữ liệu:

~~~text
PENDING -> STORED -> AVAILABLE
    |          |
    +------> FAILED hoặc QUARANTINED
~~~

Một quy trình phù hợp:

1. Xác thực người dùng, kiểm tra quota và nhận idempotency key của request.
2. Tạo bản ghi `PENDING` với `fileId`, owner, object key ổn định và giới hạn dự kiến.
3. Upload tới key đã ghi nhận; không tự sinh key mới cho mỗi lần retry của cùng phiên.
4. Khi thành công, lưu size, ETag, checksum cần thiết và chuyển sang `STORED`.
5. Kiểm tra nội dung hoặc quét theo chính sách; chuyển sang `AVAILABLE` khi đủ điều kiện.
6. Có tác vụ đối soát các bản ghi treo và object không còn được tham chiếu.

Nếu timeout ở bước upload, đối chiếu cùng object key bằng metadata hoặc đọc nội dung khi cần. Kiểm tra sự tồn tại đơn thuần chưa đủ để chứng minh object là đúng tệp dự kiến. Cần so sánh các thông tin đã gắn với phiên upload như size và checksum.

Không đặt lời gọi mạng dài vào một transaction cơ sở dữ liệu rồi cho rằng transaction rollback sẽ xóa được object. Object Storage và cơ sở dữ liệu ứng dụng không tự tham gia một transaction ACID chung. Xử lý bù, đối soát và vòng đời dữ liệu phải là một phần của thiết kế.

Một job dọn object cần danh tính và policy phù hợp với quyền xóa. Không cấp `OBJECT_DELETE` cho backend chỉ vì một quy trình dọn rác khác cần quyền đó. Với versioning hoặc retention, định nghĩa rõ điều kiện nào cho phép xóa và thời điểm tính là đã hết lưu giữ.

## 10. Khi nên dùng đường truyền trực tiếp hoặc multipart OCI

### 10.1. Pre-Authenticated Request

PAR tạo URL cho phép truy cập tài nguyên đã chỉ định mà người dùng không phải có credential OCI. Ai giữ URL đều có thể sử dụng trong phạm vi và thời gian còn hiệu lực. Có thể thu hồi bằng cách xóa PAR. Tham chiếu: [Object Storage Pre-Authenticated Requests](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests.htm).

Luồng áp dụng cho ứng dụng:

~~~text
Client -> Backend: xin quyền upload/download
Backend: xác thực, kiểm tra owner/quota, chọn key và hạn truy cập
Backend -> Client: URL PAR cho đúng object và thao tác
Client -> Object Storage: truyền tệp trực tiếp
Backend: xác minh kết quả trước khi công bố tệp
~~~

Thiết kế URL ngắn hạn cho đúng object; giữ URL khỏi log và công cụ phân tích. PAR không mặc định chỉ dùng một lần và không tự áp dụng hạn mức 10 MiB của Spring. Với browser, cấu hình CORS theo origin/method/header cần dùng; CORS không thay thế quyền truy cập.

Mẫu backend ở trên chưa cấp `PAR_MANAGE`. Nếu bổ sung PAR, phải thiết kế quyền tạo PAR và quyền dữ liệu tương ứng riêng; không suy rằng `OBJECT_CREATE` đủ cho mọi loại PAR.

Chọn backend proxy khi cần kiểm tra quyền ở mỗi request. Chọn truyền trực tiếp khi cần giảm gánh truyền dữ liệu qua backend và chấp nhận cơ chế cấp URL có thời hạn. Với upload trực tiếp, không đánh dấu `AVAILABLE` chỉ vì client thông báo đã upload xong.

### 10.2. Multipart upload của OCI cho tệp lớn

Multipart upload OCI chia một object thành nhiều part, upload từng part rồi commit. Có thể retry part thất bại thay vì gửi lại toàn bộ tệp. Những part chưa commit cần được abort hoặc dọn theo lifecycle để tránh tiếp tục chiếm dung lượng. Tham chiếu: [Object Storage Multipart Uploads](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingmultipartuploads.htm).

OCI Java SDK có `UploadManager` để lựa chọn giữa một `PutObject` và multipart theo cấu hình. Nguồn dữ liệu phải cho phép đọc lại hoặc chia part theo cách đã chọn; không giả định mọi `InputStream` đều đọc song song hay tiếp tục sau khi tiến trình khởi động lại được. Tham chiếu: [UploadManager source and contract](https://github.com/oracle/oci-java-sdk/blob/master/bmc-objectstorage/bmc-objectstorage-extensions/src/main/java/com/oracle/bmc/objectstorage/transfer/UploadManager.java).

Trước khi mở rộng mẫu 10 MiB, xác định:

- Kích thước tối đa và thời gian sống của một phiên upload.
- Nguồn tệp đọc lại được, dung lượng tạm và cách mã hóa dữ liệu tạm nếu cần.
- Kích thước part, số part song song và tổng upload đồng thời.
- Cách lưu upload ID, danh sách part và trạng thái commit nếu cần phục hồi qua lần chạy khác.
- Điều kiện abort, lifecycle dọn part và quota của người dùng.

Policy cho mẫu `PutObject` tạo mới không đủ để mặc định dùng nguyên cho multipart. Kiểm tra các quyền `OBJECT_CREATE`, `OBJECT_OVERWRITE` và quyền abort/dọn part cần thiết trước khi đổi cơ chế.

Giới hạn HTTP multipart ở Spring, giới hạn ở ingress/load balancer và giới hạn API OCI là ba lớp khác nhau. Tăng một giá trị không tự thay đổi hai lớp còn lại.

## 11. Retry, giám sát, chi phí và tính sẵn sàng

### 11.1. Retry có giới hạn và có nguồn dữ liệu phù hợp

Với GET, có thể retry giai đoạn chưa phát body xuống client nếu loại lỗi phù hợp và còn ngân sách thời gian. Khi đã phát dữ liệu, chỉ retry được theo cơ chế phục hồi được thiết kế cho download.

Với upload, cần làm rõ nguồn stream có hỗ trợ đọc lại không, key có ổn định không và request trước có thể đã thành công không. SDK có cơ chế retry và các yêu cầu riêng với stream; mẫu chủ động đặt `NO_RETRY_CONFIGURATION` ở request upload, không bọc thêm một vòng retry tùy tiện. Tham chiếu: [OCI Java SDK concepts](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm) và [RetryConfiguration](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/retrier/RetryConfiguration.html).

Nếu bổ sung retry cho nguồn tệp đọc lại được, dùng giới hạn số lần, thời gian tổng, backoff có jitter và phân loại lỗi. Không retry vô hạn với sai credential, thiếu quyền, dữ liệu không hợp lệ hoặc điều kiện ghi đã thất bại.

### 11.2. Quan sát được lỗi ở đúng tầng

Bổ sung metric cho số upload/download thành công, thất bại, byte đã truyền, độ trễ, request đang hoạt động và số lần bị từ chối vì quota. Với download, chỉ ghi nhận hoàn tất sau khi truyền hết nội dung; việc `GetObject` trả header thành công chưa có nghĩa client đã nhận hết tệp.

Khi ghi log, liên kết request của ứng dụng với `opcClientRequestId` và request ID OCI. Không dùng object key hoặc user ID làm nhãn metric không giới hạn vì số lượng giá trị có thể tăng rất lớn. Không ghi access token, URL PAR đầy đủ, private key hay nội dung tệp.

Theo dõi riêng:

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| Timeout kết nối OCI | DNS, route, Service Gateway/NAT theo thiết kế, egress và endpoint |
| OCI từ chối quyền | Principal thực tế, dynamic group, policy và bucket đích |
| Heap hoặc GC tăng mạnh | Đọc toàn tệp vào bộ nhớ, buffering, số upload đồng thời |
| Đĩa tạm đầy | Multipart HTTP, tệp chưa dọn, quota đĩa tạm |
| Download treo hoặc hết kết nối pool | Stream không đóng, client chậm, giới hạn đồng thời |
| API trả lỗi nhưng dung lượng vẫn tăng | Upload đã thành công trước timeout, retry tạo bản sao, object mồ côi |
| Tải bằng browser lỗi nhưng công cụ HTTP chạy được | CORS và các header browser cần dùng trong luồng trực tiếp |

Cấu hình logging và audit theo khả năng dịch vụ đã bật; không giả định mọi lần đọc/ghi nội dung đều tự có nhật ký chi tiết đủ cho yêu cầu của ứng dụng.

### 11.3. Giới hạn chi phí gắn với hành vi ứng dụng

Mẫu giới hạn kích thước mỗi tệp nhưng chưa giới hạn tổng dung lượng của một người dùng. Khi triển khai, cần quota theo user/tenant, số request trong một khoảng thời gian và số truyền tệp đồng thời.

Các yếu tố cần đưa vào dự toán là dung lượng object, phiên bản cũ nếu bật versioning, các part chưa commit, số request, lưu lượng truyền theo tuyến triển khai và chi phí xử lý tại backend. Không áp dụng một mức giá cố định cho mọi region hoặc storage tier; dùng bảng giá áp dụng cho tài nguyên thật khi tính toán.

Đặt lifecycle phù hợp vòng đời nghiệp vụ để dọn dữ liệu hết hạn và upload bỏ dở. Không chuyển tệp còn cần tải ngay sang Archive mà chưa thiết kế thời gian restore và trạng thái API trong thời gian chờ.

Giảm chi phí bằng cách hạn chế dữ liệu không cần lưu và kiểm soát retry, thay vì chỉ chọn một storage tier rẻ hơn nhưng không đáp ứng cách truy cập.

### 11.4. Khả năng chạy nhiều instance

Lưu byte trong Object Storage giúp các replica đọc cùng nguồn dữ liệu mà không phải đồng bộ thư mục local. Tuy vậy, dịch vụ tệp vẫn phụ thuộc vào:

- Identity provider để xác thực request.
- Đường mạng và quyền OCI của từng instance.
- Cơ sở dữ liệu metadata nếu ứng dụng đã bổ sung lớp này.
- Pool kết nối, thread và hạn mức truyền tệp của backend.

Nếu cần phục hồi khi cả region gặp sự cố, thiết kế riêng bản sao dữ liệu, metadata, chuyển hướng lưu lượng, RPO/RTO và kiểm thử khôi phục. Việc dùng Object Storage không tự tạo một phương án khôi phục ứng dụng giữa các region.

## 12. Những quyết định phải giữ rõ khi triển khai

| Câu hỏi thiết kế | Lựa chọn trong mẫu | Khi mở rộng |
| --- | --- | --- |
| Bucket có công khai không? | Private | Chỉ công khai dữ liệu được chủ động phân loại là public |
| Ai chọn object key? | Server | Client chỉ nhận ID hoặc phiên upload đã được cấp |
| Chủ sở hữu được xác định từ đâu? | Subject trong principal đã xác thực | Cơ sở dữ liệu cùng mô hình quyền chia sẻ khi cần |
| Có giữ tên và MIME do client gửi không? | Không; trả attachment dạng nhị phân | Lưu metadata đã kiểm tra, xây header an toàn |
| Giới hạn mỗi tệp? | 10 MiB | Quota tổng, giới hạn đồng thời và ngân sách thời gian |
| Retry upload có sẵn chưa? | Tắt ở request upload mẫu | Nguồn đọc lại được, key ổn định, idempotency và đối soát |
| Có quản lý metadata bền vững chưa? | Chưa | Phiên upload và trạng thái khả dụng trong cơ sở dữ liệu |
| Tệp lớn truyền cách nào? | Chưa thuộc giới hạn mẫu | Multipart OCI hoặc đường truyền trực tiếp có kiểm soát |
| Khi truyền xong ai đóng stream? | Backend đóng stream OCI | Giữ trách nhiệm rõ cả khi hủy hoặc lỗi giữa chừng |

Kết quả của bài thực hành là một API nhận và trả đúng byte qua OCI Object Storage, với danh tính người dùng và quyền OCI được xử lý ở hai lớp rõ ràng. Các phần idempotency, metadata, kiểm tra nội dung, quota và phục hồi cần được hoàn thiện theo yêu cầu của hệ thống trước khi đưa chức năng lưu tệp vào vận hành.
