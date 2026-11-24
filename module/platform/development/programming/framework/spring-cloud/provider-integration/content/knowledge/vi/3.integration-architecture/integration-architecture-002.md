# Auto-configuration, điều kiện tạo bean và cơ chế tùy chỉnh client

Khi thêm một Spring Cloud starter vào ứng dụng Spring Boot, nhiều khi ta chỉ cần khai báo dependency và vài thuộc tính cấu hình rồi có thể inject một cloud client để gọi S3, Azure Blob Storage hoặc Google Cloud Storage. Cảm giác “client tự xuất hiện” đến từ **auto-configuration**: Spring Boot và thư viện tích hợp kiểm tra classpath, cấu hình, các bean hiện có, sau đó đăng ký những bean đủ điều kiện. Hiểu cơ chế này giúp biết lúc nào client được tạo, vì sao một cấu hình không có hiệu lực và làm thế nào để thay đổi client mà không phá vỡ các tích hợp khác.

Bài thuộc chương **Kiến trúc tích hợp** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng, bao gồm danh tính và quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Trong bài này, trọng tâm là **quá trình tạo và tùy chỉnh client bên trong Spring application context**, trước khi client thực hiện yêu cầu mạng tới cloud.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích Spring Boot phát hiện auto-configuration và đánh giá điều kiện để đăng ký bean.
- Phân biệt **bean definition**, **bean instance**, **configuration properties**, **client builder** và **cloud credentials**.
- Đọc được các điều kiện thường gặp như **@ConditionalOnClass**, **@ConditionalOnMissingBean**, **@ConditionalOnProperty** và **@ConditionalOnBean**.
- Lựa chọn cấp độ tùy chỉnh phù hợp: sửa property, dùng hook/builder customizer được thư viện hỗ trợ, hoặc định nghĩa bean client.
- Chẩn đoán lỗi thiếu bean, nhiều bean, cấu hình không khớp và client dùng sai region/project/identity.
- Xây dựng kiểm thử cho điều kiện tạo bean và kiểm chứng kết nối tới managed service trên AWS, Azure hoặc Google Cloud.

## 2. Auto-configuration thực hiện công việc gì?

**Spring Framework** cung cấp IoC container: quản lý các bean và tiêm dependency. **Spring Boot** cung cấp cơ chế auto-configuration trên nền container đó. Các starter của **Spring Cloud AWS**, **Spring Cloud Azure** và **Spring Cloud GCP** có thể đưa thêm thư viện SDK, lớp cấu hình tự động và tích hợp chuyên biệt vào ứng dụng.

Auto-configuration làm việc chủ yếu ở **thời điểm khởi động ứng dụng**:

1. Boot khởi tạo **ApplicationContext**, đọc cấu hình hiệu lực và quét các bean ứng dụng.
2. Boot phát hiện các lớp auto-configuration do dependency cung cấp. Trong thế hệ Spring Boot 3.x, thư viện thường khai báo chúng bằng tệp **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
3. Các cấu hình tự động được xét theo điều kiện: một class có trên classpath hay không, thuộc tính có bật không, đã có bean cùng loại chưa, và những điều kiện riêng của starter.
4. Nếu điều kiện phù hợp, Spring đăng ký bean definition, tạo đối tượng khi cần, inject dependency, rồi đưa chúng vào vòng đời ứng dụng.
5. Controller, service, adapter, template hoặc listener có thể nhận client qua constructor injection.

Sự có mặt của một **starter** không bảo đảm mọi client đều được tạo: chỉ những nhánh cấu hình thỏa điều kiện mới hoạt động. Mặt khác, việc bean được tạo cũng **không chứng minh client đã kết nối, token đã hợp lệ hoặc danh tính có đủ quyền**. Nhiều SDK trì hoãn gọi mạng đến khi phương thức đầu tiên được thực thi.

~~~mermaid
flowchart TD
    D[Dependency / starter trên classpath] --> I[Boot tìm auto-configuration]
    P[application.yml và nguồn property khác] --> E[Đánh giá conditions]
    U[Bean tự khai báo trong ứng dụng] --> E
    I --> E
    E -->|Đạt| B[Đăng ký bean definition]
    E -->|Không đạt| S[Back off / bỏ qua nhánh cấu hình]
    B --> C[Tạo bean cloud client hoặc template]
    C --> A[Inject vào adapter / service]
    A --> R[Runtime: gọi SDK / API của cloud]
~~~

**Back off** là hành vi một cấu hình tự động nhường quyền cho bean mà ứng dụng đã tự định nghĩa, thường nhờ điều kiện **@ConditionalOnMissingBean**. Đây là quy ước phổ biến của starter, nhưng không phải bảo đảm tuyệt đối cho mọi loại bean hoặc mọi thư viện: phải xem điều kiện thật và phiên bản đang dùng.

## 3. Những điều kiện quyết định bean được tạo

| Điều kiện / annotation | Câu hỏi Spring đánh giá | Hệ quả minh họa |
| --- | --- | --- |
| **@ConditionalOnClass** | Class được chỉ định có trên classpath không? | Cấu hình S3 chỉ có ý nghĩa khi dependency SDK S3 hiện diện |
| **@ConditionalOnMissingClass** | Class được chỉ định vắng mặt không? | Chọn nhánh dành cho môi trường không có một API cụ thể |
| **@ConditionalOnBean** | Có bean phù hợp đã được đăng ký không? | Tạo template khi đã có client cần thiết |
| **@ConditionalOnMissingBean** | Chưa có bean phù hợp không? | Không tạo client mặc định nếu ứng dụng đã định nghĩa client đó |
| **@ConditionalOnSingleCandidate** | Có đúng một ứng viên phù hợp (hoặc một primary trong nhiều ứng viên) không? | Chỉ tạo thành phần phụ thuộc khi có thể xác định client để inject |
| **@ConditionalOnProperty** | Property tồn tại và có giá trị phù hợp không? | Bật adapter khi **app.storage.enabled=true** |
| **@ConditionalOnResource** | Tài nguyên được chỉ định có tồn tại không? | Bật một cấu hình chỉ khi có resource tương ứng |
| **@ConditionalOnWebApplication** | Đây có phải một web application đúng loại không? | Bật cấu hình web trong môi trường thích hợp |

Điều kiện có thể đặt ở **lớp cấu hình** hoặc **phương thức @Bean**, có thể kết hợp theo quan hệ AND. Khi một điều kiện ở cấp lớp không đạt, các bean bên trong lớp thường không được xét tiếp.

Ví dụ minh họa nguyên lý, **không phải mã nguồn thực tế của một Spring Cloud starter**:

~~~java
// Pseudocode minh họa một auto-configuration.
@AutoConfiguration
@ConditionalOnClass(S3Client.class)
@ConditionalOnProperty(
    prefix = "example.s3",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
class ExampleS3AutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(S3Client.class)
    S3Client s3Client() {
        return S3Client.create();
    }
}
~~~

Với điều kiện minh họa này, nếu thiếu class **S3Client** thì cả nhánh bị bỏ qua; nếu property đặt là **false** thì cấu hình bị tắt; nếu ứng dụng đã có bean **S3Client** thì phương thức mặc định không được dùng. **example.s3.enabled** chỉ là tên property giả định để giải thích cách hoạt động, không phải property của Spring Cloud AWS.

Hai chi tiết dễ nhầm:

- **@ConditionalOnProperty** kiểm tra property theo quy tắc của annotation; giá trị chuỗi **false** có ý nghĩa khác với thiếu property, đặc biệt khi dùng **havingValue** hoặc **matchIfMissing**. Nó không kiểm tra bucket có tồn tại hay identity có quyền hay không.
- **@ConditionalOnMissingBean** phụ thuộc các bean definition được container biết **tại thời điểm đánh giá**. Annotation này được thiết kế chủ yếu cho auto-configuration có thứ tự rõ ràng; không nên dùng tùy tiện trong mã cấu hình ứng dụng rồi xem nó như cơ chế chọn client ở runtime.

**@Profile** cũng có thể giới hạn bean theo environment (ví dụ local, staging), nhưng đây là cách chọn cấu hình theo profile. **@Primary** và **@Qualifier** giải quyết việc **chọn bean để inject khi có nhiều ứng viên**, không tự tắt hay bật auto-configuration.

## 4. Phân biệt property binding, bean và SDK client

Xét một ứng dụng cần ghi dữ liệu lên object storage:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Configuration property** | Region, bucket, endpoint, timeout, enabled | Dữ liệu để lựa chọn và cấu hình đối tượng |
| **@ConfigurationProperties** | StorageSettings chứa enabled/bucket | Bind và kiểm tra cấu hình thành đối tượng kiểu rõ ràng |
| **Bean definition** | Phương thức **@Bean S3Client s3Client(...)** | Công thức để Spring tạo và quản lý đối tượng |
| **Bean instance** | Một đối tượng **S3Client** đã được tạo | Đối tượng được inject và dùng trong runtime |
| **SDK client builder** | **S3Client.builder()** | Cấu hình cụ thể cho đối tượng SDK trước khi tạo |
| **Credential provider** | AWS default chain, Azure credential, Google ADC | Lấy/làm mới danh tính để ký hoặc gắn token vào lời gọi |
| **Cloud service** | S3, Blob Storage, Cloud Storage | Kiểm tra quyền, thực hiện thao tác và trả kết quả |

~~~mermaid
flowchart LR
    Y[Config properties] --> A[Spring auto-configuration / @Bean]
    K[Classpath + conditions] --> A
    A --> B[SDK client bean]
    C[Credential provider] --> B
    B --> D[DocumentStorage adapter]
    E[Application service] --> D
    D --> F[Managed cloud service]
~~~

**Client bean** được Spring quản lý trong một application context. **Client builder** chỉ là công cụ khởi tạo. **Credential** có thể được lấy theo chuỗi provider hoặc token acquisition riêng; không nhất thiết xuất hiện ở dạng chuỗi cố định trong YAML. Và một client có thể được cấu hình hoàn toàn hợp lệ ở thời điểm startup nhưng thất bại khi gọi mạng vì DNS, endpoint, IAM/RBAC hoặc quota.

## 5. Ví dụ cơ bản: Spring Cloud AWS tự cấu hình S3Client

Với ứng dụng Spring Boot 3 và **Spring Cloud AWS 3.x**, starter S3 thường cung cấp phần tích hợp cần thiết để Spring tạo **S3Client** và các bean liên quan khi điều kiện được đáp ứng. Phiên bản artifact và các property thực tế phải đồng bộ với **BOM Spring Cloud AWS** tương thích với Spring Boot của dự án.

Khai báo dependency Maven minh họa (version do BOM quản lý):

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-s3</artifactId>
</dependency>
~~~

Ví dụ **application.yml**:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    enabled: true
    bucket: ${APP_STORAGE_BUCKET}
~~~

Ở cấu hình này, **spring.cloud.aws.region.static** là property phục vụ client AWS qua Spring Cloud AWS; **app.storage.enabled** và **app.storage.bucket** là property **do ứng dụng tự định nghĩa** cho adapter, không tự động được starter hiểu. Biến môi trường **APP_STORAGE_BUCKET** chứa tên bucket, không phải secret. SDK có thể dùng credential chain thích hợp theo môi trường; production nên ưu tiên role hoặc workload identity và quyền tối thiểu.

Ứng dụng có thể nhận client được quản lý qua constructor:

~~~java
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.core.sync.RequestBody;

@Component
public class S3DocumentWriter {
    private final S3Client s3;

    public S3DocumentWriter(S3Client s3) {
        this.s3 = s3;
    }

    public void write(String bucket, String key, byte[] data) {
        s3.putObject(
            PutObjectRequest.builder().bucket(bucket).key(key).build(),
            RequestBody.fromBytes(data)
        );
    }
}
~~~

Trình tự lúc khởi động: starter đưa auto-configuration lên classpath → điều kiện phù hợp → đăng ký client bean → Spring inject vào **S3DocumentWriter**. Trình tự lúc ghi: mã nghiệp vụ gọi **write** → adapter gọi **S3Client.putObject** → SDK sử dụng credential/HTTP để tới S3. Auto-configuration không phải một lớp proxy nằm trên mỗi lần gọi SDK.

Nếu chỉ cần chọn region theo cấu hình được hỗ trợ, **ưu tiên property chính thức của starter**. Đừng định nghĩa thêm bean client bằng tay khi mục tiêu thực sự chỉ là thay một thuộc tính có sẵn.

## 6. Ba cấp độ tùy chỉnh client

Không có một API tùy chỉnh chung áp dụng cho mọi cloud provider. Thứ tự cân nhắc hợp lý:

### 6.1. Cấp 1 — Dùng property của starter

Phù hợp cho các lựa chọn mà thư viện đã hỗ trợ: region, project ID, account/endpoint, credential mode, bật/tắt tính năng, và đôi khi timeout/retry. Ví dụ với Spring Cloud AWS:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Ưu điểm: ít mã, thuận tiện cho nhiều môi trường, vẫn giữ cách tạo bean, lifecycle và tích hợp template/listener của thư viện. Giới hạn: không phải mọi tham số SDK đều có property Spring tương ứng.

### 6.2. Cấp 2 — Dùng customizer hoặc builder hook được thư viện công bố

Một số starter công bố **customizer**, **builder hook** hoặc tùy chọn cụ thể cho SDK. Nếu có, đó là nơi phù hợp để bổ sung cấu hình client mà vẫn sử dụng auto-configuration cho các phần khác. Phải kiểm tra chính xác **tên interface, thứ tự áp dụng và loại client được tác động** theo phiên bản thư viện; không nên tự suy ra rằng AWS, Azure và Google Cloud đều có cùng một interface customizer.

Ví dụ các nhu cầu thường phải kiểm tra hook được hỗ trợ: proxy, endpoint riêng, interceptor, tracing, retry, connect/read timeout hoặc HTTP transport. Việc thêm một interceptor vào builder của client A không có nghĩa listener/template B tự dùng cùng client.

### 6.3. Cấp 3 — Tự khai báo bean SDK client

Khi cần quyền kiểm soát trực tiếp cấu hình SDK, có thể đăng ký bean bằng **@Configuration** và **@Bean**. Ví dụ dưới đây minh họa việc sở hữu riêng cấu hình **S3Client**:

~~~java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class AwsS3ClientConfiguration {

    @Bean
    S3Client s3Client(
            @Value("${app.aws.s3.region}") String region) {
        return S3Client.builder()
            .region(Region.of(region))
            .credentialsProvider(DefaultCredentialsProvider.create())
            .overrideConfiguration(config -> config
                .apiCallAttemptTimeout(Duration.ofSeconds(5))
                .apiCallTimeout(Duration.ofSeconds(20)))
            .build();
    }
}
~~~

~~~yaml
app:
  aws:
    s3:
      region: ap-southeast-1
~~~

Với auto-configuration dùng **@ConditionalOnMissingBean(S3Client.class)**, bean tự khai báo này làm nhánh tạo **S3Client mặc định** back off; những template/component khác có thể vẫn sử dụng bean mới. **Không được giả định điều đó cho mọi phiên bản starter**: phải xác minh condition report và bean graph. Ví dụ dùng **DefaultCredentialsProvider**, không đưa access key/secret key vào source code hoặc config. Timeout được chọn chỉ để minh họa, phải hiệu chỉnh theo SLA và retry thực tế.

Bean là singleton theo mặc định nên client có thể tái sử dụng thay vì tạo mới cho từng request. Spring quản lý lifecycle của bean, thường suy luận phương thức **close** trên SDK client khi context đóng; cần kiểm tra tài nguyên transport khi cấu hình custom HTTP client bên ngoài. Nếu bỏ hẳn starter và chỉ dùng SDK, ứng dụng sẽ phải tự cấu hình thêm các phần tích hợp trước đây do starter cung cấp.

### 6.4. Quy tắc lựa chọn

| Nhu cầu | Cách phù hợp đầu tiên | Lưu ý |
| --- | --- | --- |
| Chọn region hoặc project/account theo môi trường | Property của starter | Tránh đặt hai nguồn region trái nhau |
| Bổ sung interceptor hoặc HTTP timeout không có property | Hook/customizer chính thức, nếu có | Xem customizer áp dụng cho sync/async client nào |
| Dùng client cho endpoint/identity đặc biệt | Tự khai báo bean phù hợp | Xem tác động đến auto-config, template và listener |
| Có hai cloud account hoặc hai region trong cùng context | Định nghĩa nhiều bean có tên/qualifier rõ ràng | Tránh dựa vào inject theo type khi mơ hồ |
| Bật hoặc tắt một adapter nghiệp vụ | Condition trên adapter/port của ứng dụng | Không đồng nghĩa vô hiệu toàn bộ starter |
| Cần chạy local không có cloud thật | Mock port hoặc emulator/test configuration | Test context và IAM thật phải được kiểm chứng riêng |

## 7. Tùy chỉnh điều kiện tạo adapter của chính ứng dụng

Giả sử chỉ muốn tạo adapter lưu tài liệu khi **app.storage.enabled=true**, độc lập với việc starter có tạo SDK client hay không. Có thể khai báo port và một lớp cấu hình điều kiện:

~~~java
// DocumentStorage.java
public interface DocumentStorage {
    void put(String key, byte[] bytes);
}
~~~

~~~java
// S3DocumentStorage.java
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

public final class S3DocumentStorage implements DocumentStorage {
    private final S3Client client;
    private final String bucket;

    public S3DocumentStorage(S3Client client, String bucket) {
        this.client = client;
        this.bucket = bucket;
    }

    @Override
    public void put(String key, byte[] bytes) {
        client.putObject(
            PutObjectRequest.builder().bucket(bucket).key(key).build(),
            RequestBody.fromBytes(bytes)
        );
    }
}
~~~

~~~java
// StorageSettings.java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.storage")
public record StorageSettings(boolean enabled, String bucket) {}
~~~

~~~java
// DocumentStorageConfiguration.java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(StorageSettings.class)
public class DocumentStorageConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.storage",
        name = "enabled",
        havingValue = "true"
    )
    DocumentStorage documentStorage(
            S3Client s3Client, StorageSettings settings) {
        return new S3DocumentStorage(s3Client, settings.bucket());
    }
}
~~~

Với cấu hình trên:

| **app.storage.enabled** | Bean **DocumentStorage** | Điều gì xảy ra? |
| --- | --- | --- |
| **true** | Được đăng ký, nếu có dependency **S3Client** | Adapter sẵn sàng để được inject |
| **false** | Bị bỏ qua | Service bắt buộc inject **DocumentStorage** có thể không khởi động nếu thiếu phương án khác |
| Không khai báo | Bị bỏ qua theo mặc định | Vì **matchIfMissing** mặc định là **false** |

Điều kiện này chỉ điều khiển **DocumentStorage**, không tự động tắt bean **S3Client** của Spring Cloud AWS. Nếu ứng dụng cần hỗ trợ nhiều provider, có thể thêm property **app.storage.provider** để chọn adapter tương ứng; khi đó đảm bảo đúng một adapter thỏa điều kiện, hoặc dùng **@Qualifier** cụ thể khi nhiều adapter hợp lệ.

**@ConfigurationProperties** gom dữ liệu theo một namespace và hỗ trợ binding kiểu rõ ràng. Với cấu hình production, có thể kết hợp validation (**@Validated**, các ràng buộc Jakarta Validation khi dependency phù hợp hiện diện) để phát hiện bucket rỗng hoặc giá trị sai ngay khi startup thay vì chỉ gặp lỗi ở runtime.

## 8. Có nhiều client bean: @Primary, @Qualifier và ranh giới auto-config

Hai S3 account, hai region hay hai API endpoint có thể cần hai bean cùng loại **S3Client**. Khi đó:

~~~java
// Ý tưởng trong một @Configuration do ứng dụng sở hữu.
@Bean("invoiceS3Client")
S3Client invoiceS3Client() {
    return S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();
}

@Bean("archiveS3Client")
S3Client archiveS3Client() {
    return S3Client.builder()
        .region(Region.AP_NORTHEAST_1)
        .build();
}
~~~

~~~java
// Ví dụ lựa chọn client theo tên bean.
public InvoiceWriter(
        @Qualifier("invoiceS3Client") S3Client s3Client) {
    this.s3Client = s3Client;
}
~~~

Các đoạn trên là **trích đoạn minh họa**, phải đặt trong class thích hợp và thêm import theo dự án. Mỗi client dùng credential chain và quyền truy cập tương ứng; khác region **không** tự tạo ra danh tính khác. Nếu dùng hai account, phải cấu hình identity cho từng client một cách có chủ đích.

**@Primary** chỉ tạo ứng viên mặc định khi inject theo type. **@Qualifier** diễn đạt rõ client nào phục vụ nghiệp vụ nào, thường phù hợp hơn khi hai client có trách nhiệm khác nhau. Có nhiều **S3Client** cũng có thể khiến điều kiện **@ConditionalOnSingleCandidate** không đạt hoặc template không biết chọn bean nào. Với ứng dụng sở hữu nhiều client, cần kiểm tra luôn những bean phụ thuộc của Spring Cloud và có thể phải cấu hình lại template/listener theo tên bean cụ thể.

Không nên bật **spring.main.allow-bean-definition-overriding=true** chỉ để “chữa” lỗi trùng bean: ghi đè definition bằng tên có thể che mất xung đột cấu hình, còn lỗi **NoUniqueBeanDefinitionException** là xung đột chọn theo type. Xử lý đúng bằng điều kiện, tên bean, qualifier hoặc sở hữu rõ ràng cấu hình.

## 9. Đối chiếu cách Spring Cloud tích hợp AWS, Azure và Google Cloud

Cả ba hệ sinh thái đều có ý tưởng cấu hình tự động và client được inject, nhưng **starter, class SDK, credential và property không đồng nhất**.

| Tiêu chí | Spring Cloud AWS | Spring Cloud Azure | Spring Cloud GCP |
| --- | --- | --- | --- |
| Storage managed điển hình | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| Starter tương ứng (ví dụ phổ biến) | **spring-cloud-aws-starter-s3** | **spring-cloud-azure-starter-storage-blob** | **spring-cloud-gcp-starter-storage** (tọa độ phụ thuộc thế hệ thư viện) |
| Client Java thường gặp | **S3Client**, đôi khi **S3AsyncClient** | **BlobServiceClient** hoặc async variant | **Storage** của Google Cloud Java client |
| Nguồn danh tính thường dùng | AWS default credentials chain, IAM role | DefaultAzureCredential, Managed Identity | Application Default Credentials, workload identity |
| Phạm vi tài nguyên | Region + bucket | Storage account/endpoint + container | Project + bucket và location của bucket |
| Điểm tùy chỉnh quan trọng | Region, credential provider, endpoint, retry/timeout | Endpoint, credential, retry/transport | Project, credentials, transport/retry |

Đường đi của các adapter có thể mô tả bằng cùng sơ đồ:

~~~text
Business service
  -> StoragePort do ứng dụng định nghĩa
  -> Provider adapter
  -> Client hoặc template do Spring quản lý
  -> SDK của AWS / Azure / Google Cloud
  -> Managed service tương ứng
~~~

Trong nhiều trường hợp, Spring Cloud tạo **template** cao hơn SDK client và adapter gọi template đó. Trong trường hợp khác, adapter gọi trực tiếp SDK client được Spring inject. Cả hai vẫn dùng cơ chế bean và dependency injection; khác nhau ở abstraction dành cho lập trình viên.

**Cần phân biệt các nguồn cấu hình:**

- **AWS:** region, credential chain và endpoint phải nhất quán với S3 hoặc dịch vụ được gọi. Có thể dùng IAM role của workload, nhưng role hợp lệ vẫn phải được cấp quyền trên bucket.
- **Azure:** endpoint gắn với storage account; Managed Identity/DefaultAzureCredential giải quyết authentication, còn Azure RBAC và các chính sách storage quyết định authorization.
- **Google Cloud:** project ID lựa chọn dự án làm việc; ADC xác định credential; quyền trên bucket/project phải được cấp riêng. Bucket location không tương đương trực tiếp với một endpoint region của S3.

Không thể giả định đổi tên một property AWS thành tên tương đương ở Azure hoặc GCP là đủ để chuyển cloud. Các bean, builder, cơ chế retry, lifecycle và đặc tính dịch vụ cần được kiểm tra theo từng thư viện. Trước khi áp dụng ví dụ vào dự án, hãy dùng một **BOM** tương thích cho từng family và đọc tài liệu đúng phiên bản.

## 10. Một cloud client có thể cấu hình đúng nhưng vẫn lỗi runtime

Auto-configuration chỉ quyết định object được đăng ký và khởi tạo, không thay thế các bước bảo mật/kết nối:

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant A as Auto-config
    participant C as Cloud SDK client
    participant I as Identity provider
    participant S as Managed service
    B->>A: Đánh giá điều kiện và properties
    A-->>B: Đăng ký client bean
    B->>C: Tạo / inject client
    Note over B,C: Context có thể khởi động thành công
    C->>I: Lấy credential / token khi cần
    I-->>C: Danh tính hoặc lỗi xác thực
    C->>S: Yêu cầu tới endpoint
    S-->>C: Thành công / 403 / 429 / 5xx
~~~

Ví dụ: container Spring có **S3Client** và service inject thành công, nhưng khi gọi **putObject** ứng dụng nhận **AccessDenied**. Điều này thường hướng tới IAM/policy/bucket hoặc danh tính đang dùng, không trực tiếp chứng minh điều kiện auto-configuration sai. Ngược lại, nếu Spring báo **NoSuchBeanDefinitionException** cho **S3Client** khi startup thì phải kiểm tra starter, điều kiện, dependency, bean scanning và config trước khi kiểm tra IAM.

## 11. Chẩn đoán khi auto-configuration không như mong đợi

### 11.1. Quy trình điều tra

1. **Đọc lỗi ban đầu**: thiếu bean, nhiều bean, bean khởi tạo thất bại hay lỗi mạng ở runtime?
2. **Kiểm tra dependency/BOM**: starter và SDK có mặt, version tương thích không? Có xung đột classpath không?
3. **Xem property hiệu lực**: profile, biến môi trường, property source, thứ tự ưu tiên và tên namespace có đúng không?
4. **Xem Condition Evaluation Report**: nhánh auto-config nào đã match, nhánh nào back off và vì lý do gì?
5. **Xem bean graph**: có bao nhiêu bean cùng type, tên/qualifier là gì, bean nào inject vào template/listener/adapter?
6. **Gọi kiểm thử cloud có kiểm soát**: nếu context đúng, kiểm tra identity, quyền, endpoint, network và chính sách dịch vụ.

Trong môi trường phát triển, có thể bật báo cáo điều kiện bằng tham số **--debug** khi chạy Spring Boot. Nếu đã cấu hình Actuator và cấp quyền phù hợp, endpoint **/actuator/conditions** có thể giúp kiểm tra kết quả điều kiện; không phơi bày endpoint chẩn đoán nội bộ cho người dùng công cộng.

### 11.2. Triệu chứng và nguyên nhân có thể

| Triệu chứng | Kiểm tra đầu tiên | Sửa theo nguyên nhân |
| --- | --- | --- |
| **NoSuchBeanDefinitionException** | Starter có trên classpath? condition/property có match? | Thêm đúng dependency, sửa điều kiện hoặc khai báo bean cần thiết |
| **UnsatisfiedDependencyException** ở adapter | Bean dependency nào thiếu hoặc khởi tạo lỗi? | Lần theo root cause, bean definition và cấu hình bind |
| **NoUniqueBeanDefinitionException** | Có nhiều client cùng type không? | Dùng qualifier/tên bean, hoặc giảm số bean về đúng thiết kế |
| **BeanDefinitionOverrideException** | Hai bean cùng tên đang được đăng ký? | Đổi tên hoặc điều kiện, bỏ định nghĩa trùng |
| Property mới thêm nhưng client vẫn dùng mặc định | Property có thuộc starter và đúng namespace không? Có custom bean override không? | Kiểm tra property binding và bean đang thực sự được sử dụng |
| Client inject thành công nhưng **403/PermissionDenied** | Identity, IAM/RBAC/policy, resource scope | Cấp quyền tối thiểu đúng tài nguyên, kiểm tra deny và workload identity |
| Client gọi nhầm project/region/account | Hai nguồn cấu hình, biến môi trường, builder hard-code | Chọn một nguồn giá trị có chủ đích và xác minh bean runtime |
| Timeout hoặc retry quá nhiều | HTTP client, endpoint, proxy, quota, chính sách retry ở nhiều tầng | Kiểm tra mạng và tổng thời gian gọi, tránh retry chồng lên nhau |

**Cẩn trọng với thông tin nhạy cảm:** khi chẩn đoán có thể log tên bean, class, endpoint đã được cho phép hiển thị, region/project và nguyên nhân lỗi đã làm sạch. Không log access key, SAS token, connection string, secret, OAuth token hoặc body dữ liệu nhạy cảm. Việc bật debug toàn bộ SDK trên production có thể lộ thông tin và tạo quá nhiều log.

## 12. Kiểm thử điều kiện tạo bean và client

Có hai nhóm kiểm thử khác mục đích:

**Kiểm thử context** xác minh cấu hình Spring: khi property bật/tắt thì bean xuất hiện đúng, và khi có user-defined client thì adapter chọn đúng bean. Không cần kết nối cloud.

**Kiểm thử tích hợp cloud** xác minh SDK gọi API thực: bucket/container tồn tại, identity có quyền, endpoint và mạng đúng. Có thể dùng LocalStack (một phần dịch vụ AWS), Azurite (Azure Blob) hoặc một môi trường test phù hợp cho Google Cloud; emulator không mô phỏng đầy đủ IAM/Managed Identity/workload identity và mọi chính sách dịch vụ.

Với lớp **DocumentStorageConfiguration** ở phần 7, có thể dùng **ApplicationContextRunner** của Spring Boot Test để kiểm thử nhánh bật/tắt mà không khởi động cả server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import software.amazon.awssdk.services.s3.S3Client;

class DocumentStorageConfigurationTest {
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(DocumentStorageConfiguration.class)
            .withBean(S3Client.class, () -> mock(S3Client.class));

    @Test
    void createsStorageWhenEnabled() {
        runner.withPropertyValues(
                "app.storage.enabled=true",
                "app.storage.bucket=demo-bucket")
            .run(context ->
                assertThat(context).hasSingleBean(DocumentStorage.class));
    }

    @Test
    void skipsStorageWhenDisabled() {
        runner.withPropertyValues("app.storage.enabled=false")
            .run(context ->
                assertThat(context).doesNotHaveBean(DocumentStorage.class));
    }
}
~~~

Kiểm thử này **không gọi S3**; client là mock dùng để chứng minh Spring wiring và condition. Để kiểm tra nhánh back off của chính một starter, cần import đúng auto-configuration cần xét, và so sánh context **có** và **không có** bean do người dùng cung cấp. Khi chọn test container hoặc môi trường cloud thật, cần kiểm tra thêm timeout/retry, quyền, dữ liệu test tách biệt và cleanup sau test.

Một bộ test đáng tin nên bao gồm:

- Property đúng/sai/không có; cả trường hợp property bị override bởi profile hoặc environment.
- Có một client mặc định, có client tùy chỉnh, có nhiều client và qualifier rõ ràng.
- Thiếu credentials hoặc thiếu quyền trên cloud thật (kiểm tra phân loại lỗi ở adapter), không đánh đồng với thiếu bean.
- Network timeout, retry và việc client được tái sử dụng; không tạo client mới cho mỗi lần gọi.
- Tính tương thích giữa starter và SDK/BOM khi nâng cấp phiên bản.

## 13. Bài tập thực hành

**Bài tập 1 — Giải thích điều kiện.** Với một nhánh auto-config gồm **@ConditionalOnClass(S3Client.class)**, **@ConditionalOnProperty(havingValue="true")** và **@ConditionalOnMissingBean(S3Client.class)**, hãy lập bảng bốn tình huống: thiếu SDK, property false, có custom S3Client, và mọi điều kiện đạt. Chỉ rõ nhánh nào tạo bean mặc định.

**Bài tập 2 — Tùy chỉnh an toàn.** Bắt đầu với region được cấu hình qua property của Spring Cloud AWS. Thiết kế hai phương án để thêm timeout: dùng hook chính thức nếu thư viện hỗ trợ hoặc tự đăng ký bean **S3Client**. Cho biết cách xác minh client thật sự được inject và cách tránh retry trùng ở SDK/service.

**Bài tập 3 — Chọn provider.** Đề xuất property **app.storage.provider=aws|azure|gcp** và điều kiện tạo ba adapter cùng triển khai **DocumentStorage**. Hãy chỉ ra tình huống hai adapter cùng có mặt, một adapter không có, và cách báo lỗi cấu hình rõ ràng khi khởi động.

**Bài tập 4 — Debug.** Một ứng dụng chạy local nhận **S3Client** bình thường, nhưng trên Kubernetes báo **NoUniqueBeanDefinitionException** sau khi thêm một cấu hình client cho archive. Hãy dùng condition report và danh sách bean để xác định xung đột; đề xuất sử dụng **@Qualifier** và kiểm tra template liên quan.

**Bài tập 5 — So sánh cloud.** Vẽ một sơ đồ gồm service → storage port → adapter → SDK client → managed service cho Azure Blob và Google Cloud Storage. Ghi rõ tại đâu Spring bind property, ở đâu credential/token được lấy và ở đâu cloud service quyết định quyền truy cập.

## 14. Ghi nhớ

- **Auto-configuration là cơ chế đăng ký và tạo bean lúc startup** dựa trên classpath, properties và trạng thái context; nó không phải lời gọi mạng tới cloud.
- **@ConditionalOnMissingBean** thường giúp starter nhường quyền cho bean ứng dụng tự khai báo, nhưng phải xác minh điều kiện và phạm vi cụ thể của thư viện.
- **Property → customizer được hỗ trợ → custom client bean** là ba cấp độ tùy chỉnh tăng dần về quyền kiểm soát và trách nhiệm bảo trì.
- **@Primary/@Qualifier** xử lý lựa chọn bean khi có nhiều ứng viên; điều kiện tạo bean và lựa chọn bean là hai việc khác nhau.
- Context khởi động thành công không bảo đảm workload có **credential hợp lệ, IAM/RBAC đúng, kết nối mạng hoặc quyền sử dụng tài nguyên**.
- Cùng một tư duy áp dụng cho Spring Cloud AWS, Azure và GCP, nhưng phải xác minh **BOM, starter, SDK class, properties và lifecycle** của đúng provider/phiên bản.
