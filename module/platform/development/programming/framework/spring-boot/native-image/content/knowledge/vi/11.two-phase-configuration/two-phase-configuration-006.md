# @ConfigurationProperties và việc binding trong ứng dụng native

## 1. Hai giai đoạn cần phân biệt

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring AOT chuẩn bị ứng dụng ở thời điểm build để GraalVM Native Image có thể phân tích và tạo executable. Khi dùng `@ConfigurationProperties`, cần hiểu rõ ranh giới giữa hai giai đoạn:

1. **Build time (Spring AOT):** Spring phân tích cấu trúc ứng dụng, bean definitions, các lớp cấu hình và những kiểu truy cập cần thiết. AOT có thể tạo mã khởi tạo và runtime hints để Native Image giữ được khả năng binding.
2. **Runtime (ứng dụng native khởi động):** Spring Boot đọc property sources thực tế, chuyển đổi giá trị sang kiểu Java, validate và tạo bean cấu hình. Các giá trị như URL, bucket, timeout hay feature setting vẫn có thể đến từ môi trường chạy.

Điểm quan trọng: **AOT chuẩn bị khả năng binding; nó không mặc định đóng băng mọi giá trị cấu hình vào executable.** Tuy nhiên, những giá trị được dùng để quyết định bean graph trong quá trình AOT, chẳng hạn điều kiện auto-configuration, có thể ảnh hưởng đến cấu trúc đã được chuẩn bị ở build time.

## 2. @ConfigurationProperties dùng để làm gì?

`@ConfigurationProperties` gom các thuộc tính có chung prefix vào một đối tượng Java có kiểu rõ ràng. Thay vì rải nhiều chuỗi cấu hình trong code bằng `@Value`, ứng dụng có thể khai báo một cấu trúc, dùng type conversion, default value và validation tập trung.

Ví dụ ứng dụng có nhóm cấu hình lưu trữ:

~~~yaml
app:
  storage:
    bucket: invoices
    connect-timeout: 5s
    endpoint: https://storage.example.internal
~~~

Ta muốn Spring bind các giá trị này vào một đối tượng có kiểu:

~~~java
StorageProperties properties;

String bucket = properties.getBucket();
Duration timeout = properties.getConnectTimeout();
URI endpoint = properties.getEndpoint();
~~~

Binder xử lý việc ánh xạ từ property names sang Java properties, chuyển đổi kiểu như `Duration` và `URI`, sau đó đưa đối tượng vào ApplicationContext để bean khác sử dụng.

## 3. Khai báo lớp cấu hình và đăng ký với Spring

### 3.1. JavaBean binding

Cách khai báo mutable JavaBean dễ hiểu và tương thích với nhiều phiên bản Spring Boot:

~~~java
package com.example.storage;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {

    @NotBlank
    private String bucket;

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(5);

    @NotNull
    private URI endpoint;

    public String getBucket() {
        return bucket;
    }

    public void setBucket(String bucket) {
        this.bucket = bucket;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

`@ConfigurationProperties(prefix = "app.storage")` chỉ rõ prefix. Spring Boot sẽ bind các property có tên bắt đầu bằng `app.storage` vào những thuộc tính tương ứng. `@Validated` kích hoạt validation; các annotation như `@NotBlank` và `@NotNull` đến từ Jakarta Bean Validation.

Để validation hoạt động, dự án cần có validation provider, thường được thêm qua dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Nếu dự án đang dùng Spring Boot 2.x, namespace validation có thể là `javax.validation` thay vì `jakarta.validation`. Hãy dùng namespace phù hợp với major version của ứng dụng.

### 3.2. Đăng ký configuration properties

Có hai cách phổ biến.

**Cách A — quét các lớp cấu hình:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class StorageApplication {
    public static void main(String[] args) {
        SpringApplication.run(StorageApplication.class, args);
    }
}
~~~

`@ConfigurationPropertiesScan` tìm các lớp có `@ConfigurationProperties` trong package được quét và package con. Đặt lớp cấu hình trong phạm vi scan hoặc chỉ rõ package phù hợp.

**Cách B — đăng ký tường minh:**

~~~java
@SpringBootApplication
@EnableConfigurationProperties(StorageProperties.class)
public class StorageApplication {
    public static void main(String[] args) {
        SpringApplication.run(StorageApplication.class, args);
    }
}
~~~

`@EnableConfigurationProperties` đăng ký trực tiếp kiểu cấu hình cần dùng. Cách này hữu ích khi muốn kiểm soát rõ những properties type được bật.

Chỉ đặt `@ConfigurationProperties` trên một class **không đảm bảo class đó đã là bean**. Nó cần được đăng ký qua scan hoặc `@EnableConfigurationProperties`. Đây cũng là điều AOT cần nhìn thấy để chuẩn bị metadata phù hợp.

## 4. Binding vẫn diễn ra khi ứng dụng native khởi động

Giả sử cấu hình trong `application.yml`:

~~~yaml
app:
  storage:
    bucket: invoices
    connect-timeout: 5s
    endpoint: https://storage.example.internal
~~~

Ứng dụng JVM và ứng dụng native đều có thể đọc các giá trị này lúc khởi động. Khi chạy executable native:

~~~bash
./storage-service
~~~

Spring Boot nạp Config Data, tạo Environment và bind các giá trị vào `StorageProperties`. Nếu giá trị được cung cấp qua biến môi trường hoặc system property ở runtime, Binder có thể nhận giá trị đó theo thứ tự ưu tiên của các property sources.

Ví dụ override bucket mà không rebuild native image:

~~~bash
APP_STORAGE_BUCKET=archive ./storage-service
~~~

Với property canonical là `app.storage.bucket`, dạng environment variable tương ứng là `APP_STORAGE_BUCKET`. Khi chạy trong container, có thể truyền biến môi trường qua cấu hình triển khai:

~~~bash
docker run --rm \
  -e APP_STORAGE_BUCKET=archive \
  -p 8080:8080 \
  storage-service:native
~~~

Như vậy, **giá trị cấu hình có thể thay đổi theo môi trường chạy** mà không cần biên dịch lại executable, miễn là chúng không làm thay đổi cấu trúc bean đã được quyết định trong quá trình AOT.

## 5. Relaxed binding và chuyển đổi kiểu

Spring Boot hỗ trợ relaxed binding để các cách viết property phổ biến có thể ánh xạ tới cùng một thuộc tính. Ví dụ thuộc tính Java `connectTimeout` có thể được khai báo trong YAML bằng kebab case:

~~~yaml
app:
  storage:
    connect-timeout: 5s
~~~

Hoặc cung cấp qua environment variable theo quy tắc chuyển đổi tên:

~~~bash
APP_STORAGE_CONNECTTIMEOUT=8s
~~~

Với environment variable, Spring Boot chuyển tên property canonical bằng cách:

1. Đổi dấu chấm (`.`) thành dấu gạch dưới (`_`).
2. Bỏ dấu gạch ngang (`-`).
3. Chuyển toàn bộ thành chữ hoa.

Do đó `app.storage.connect-timeout` thành `APP_STORAGE_CONNECTTIMEOUT`. Đừng tự chèn dấu gạch dưới vào giữa từng từ của tên có dấu gạch ngang nếu muốn tuân thủ quy tắc canonical conversion.

Binder còn hỗ trợ chuyển đổi các kiểu thông dụng:

| Kiểu Java | Ví dụ giá trị cấu hình | Kết quả |
| --- | --- | --- |
| `Duration` | `5s`, `250ms`, `PT2M` | Khoảng thời gian |
| `DataSize` | `16MB`, `512KB` | Kích thước dữ liệu |
| `URI` / `URL` | `https://storage.example.internal` | Địa chỉ tài nguyên |
| `InetAddress` | `127.0.0.1` | Địa chỉ mạng |
| Enum | `S3`, `LOCAL` | Giá trị enum tương ứng |
| List/Set | Danh sách YAML hoặc indexed properties | Tập hợp phần tử |
| Map | Các key con dưới prefix | Map key/value |

Ưu tiên tên property dạng kebab case trong file cấu hình. Với collection/map, cần chú ý cú pháp index và key khi truyền qua environment variable; nếu cấu trúc phức tạp, file YAML hoặc Config Data thường dễ đọc và ít nhầm hơn.

## 6. Binding lồng nhau, collection và default value

Một cấu hình thực tế thường có nhóm con:

~~~yaml
app:
  storage:
    bucket: invoices
    connect-timeout: 5s
    endpoint: https://storage.example.internal
    retry:
      max-attempts: 3
      backoff: 200ms
    allowed-regions:
      - ap-southeast-1
      - ap-southeast-2
~~~

Lớp cấu hình có thể mở rộng:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {

    private String bucket;
    private Duration connectTimeout = Duration.ofSeconds(5);
    private URI endpoint;
    private Retry retry = new Retry();
    private List<String> allowedRegions = new ArrayList<>();

    public static class Retry {
        private int maxAttempts = 3;
        private Duration backoff = Duration.ofMillis(200);

        public int getMaxAttempts() { return maxAttempts; }
        public void setMaxAttempts(int value) { this.maxAttempts = value; }
        public Duration getBackoff() { return backoff; }
        public void setBackoff(Duration value) { this.backoff = value; }
    }

    public String getBucket() { return bucket; }
    public void setBucket(String value) { this.bucket = value; }
    public Duration getConnectTimeout() { return connectTimeout; }
    public void setConnectTimeout(Duration value) { this.connectTimeout = value; }
    public URI getEndpoint() { return endpoint; }
    public void setEndpoint(URI value) { this.endpoint = value; }
    public Retry getRetry() { return retry; }
    public void setRetry(Retry value) { this.retry = value; }
    public List<String> getAllowedRegions() { return allowedRegions; }
    public void setAllowedRegions(List<String> value) { this.allowedRegions = value; }
}
~~~

Đoạn code trên minh họa JavaBean binding; trong dự án thực tế nên bổ sung validation, constructor và accessor theo quy ước codebase. Các object lồng nhau có thể được bind qua thuộc tính tương ứng. Với mutable nested object, khởi tạo mặc định giúp ứng dụng có giá trị dự phòng khi cấu hình con không được cung cấp.

Một lưu ý về collection: khi Binder nhận một giá trị list từ property source có độ ưu tiên cao hơn, list có thể được thay thế theo nguồn đó thay vì luôn cộng dồn phần tử từ mọi nguồn. Hãy kiểm thử hành vi override collection nếu môi trường staging/production truyền cấu hình khác nhau.

## 7. Constructor binding và cấu hình bất biến

Thay vì JavaBean với setter, có thể dùng constructor binding để tạo đối tượng cấu hình bất biến. Ví dụ với record trên Spring Boot 3:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
    String bucket,
    Duration connectTimeout,
    URI endpoint
) {
}
~~~

Record có canonical constructor duy nhất nên Spring Boot 3 có thể dùng constructor binding mà không cần setter. Nếu một class có nhiều constructor, cần chỉ rõ constructor binding theo quy tắc của phiên bản Spring Boot đang dùng. Các phiên bản Boot cũ hơn có khác biệt về vị trí/việc sử dụng `@ConstructorBinding`, vì vậy hãy kiểm tra API của major version trong dự án.

Constructor binding có lợi thế:

- Đối tượng được tạo đầy đủ qua constructor, dễ dùng với immutable design.
- Có thể khai báo default value và nested object qua constructor parameter/annotation phù hợp.
- Không phải để lộ setter cho các thuộc tính cấu hình.

Tuy nhiên, kiểu lồng nhau, tham số tùy chọn, default value và validation cần được khai báo rõ. Không nên trộn constructor binding với cách đăng ký bean thủ công bằng `@Component` hoặc `@Bean` tùy tiện; hãy dùng scan hoặc `@EnableConfigurationProperties` đúng cách.

## 8. Spring AOT và Native Image chuẩn bị binding như thế nào?

Trong JVM, Binder có thể dùng reflection và metadata của kiểu Java để đọc tên property, constructor, getter/setter, annotation và kiểu dữ liệu. GraalVM Native Image phân tích theo mô hình closed world; những thành viên chỉ được truy cập động có thể bị loại nếu không có thông tin cần thiết.

Với configuration properties được Spring Boot đăng ký đúng cách qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, Spring Boot AOT/native support có thể đóng góp runtime hints cho các kiểu cần thiết để binding hoạt động trong native executable.

Luồng khái niệm:

~~~mermaid
flowchart TB
    P["@ConfigurationProperties type"] --> R["Đăng ký qua scan hoặc EnableConfigurationProperties"]
    R --> A["Spring AOT nhận diện kiểu cấu hình"]
    A --> H["Runtime hints / metadata cho Native Image"]
    H --> N["GraalVM phân tích và giữ các truy cập cần thiết"]
    N --> E["Native executable"]
    E --> S["Runtime: đọc Environment / Config Data"]
    S --> B["Binder chuyển đổi và validate giá trị"]
    B --> O["ConfigurationProperties bean"]
~~~

Điều này **không có nghĩa Binder đã chạy và giá trị thật đã được ghi vào executable lúc build**. AOT chuẩn bị kiểu, cấu trúc và metadata cần thiết. Khi executable khởi động, Binder vẫn đọc các property sources có trong môi trường chạy và tạo đối tượng với giá trị tương ứng.

### 8.1. Vì sao cần đăng ký type đúng cách?

Nếu class có `@ConfigurationProperties` nhưng không được scan hoặc enable, nó có thể không trở thành bean, không được AOT nhận diện như một configuration properties bean và code khác không inject được.

Hãy dùng một trong hai cách:

~~~java
@ConfigurationPropertiesScan
@SpringBootApplication
class Application {
}
~~~

Hoặc:

~~~java
@EnableConfigurationProperties(StorageProperties.class)
@SpringBootApplication
class Application {
}
~~~

Không cần thêm `@Component` chỉ để biến class thành bean nếu đã dùng một trong hai cơ chế trên.

### 8.2. Khi nào cần RuntimeHintsRegistrar tự viết?

Trước hết kiểm tra xem lỗi có thực sự đến từ configuration properties binding không. Spring Boot đã cung cấp native support cho nhiều trường hợp phổ biến. Hãy chỉ bổ sung hints thủ công khi:

- Có kiểu hoặc thành viên truy cập bằng reflection ngoài phạm vi mà framework nhận diện.
- Custom binder/converter dùng reflection hoặc resource động.
- Thư viện thứ ba không cung cấp reachability metadata cần thiết.
- Lỗi native chỉ ra rõ constructor, method, field hoặc resource bị thiếu.

Ví dụ đăng ký một constructor dùng reflection cho một kiểu do ứng dụng tự tạo:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(StorageRuntimeHints.class)
class StorageNativeConfiguration {
}

class StorageRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            LegacyStorageDescriptor.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
    }
}
~~~

Đây chỉ là ví dụ cho một kiểu truy cập cụ thể. Nếu Binder cần gọi setter, đọc field hoặc dùng một constructor khác, hint phải phản ánh đúng thành viên đó. Không đăng ký rộng toàn bộ class hoặc package nếu không có lý do.

## 9. Hai loại cấu hình: giá trị runtime và cấu trúc build time

Đây là điểm dễ nhầm nhất khi đưa `@ConfigurationProperties` vào native image.

| Loại cấu hình | Ví dụ | Thời điểm quyết định |
| --- | --- | --- |
| Giá trị dùng trong bean đã tồn tại | bucket, endpoint, timeout, retry count | Thường bind lúc ứng dụng native khởi động |
| Secret/credential được cung cấp từ môi trường | API key, database password | Runtime qua environment/secret/config source |
| Cấu trúc bean phụ thuộc condition | `@ConditionalOnProperty` bật/tắt một bean | Có thể được đánh giá khi AOT xử lý |
| Auto-configuration phụ thuộc classpath | Có/không có thư viện hoặc class | Build time/AOT theo classpath |
| Runtime profile ảnh hưởng bean graph | Profile làm thay đổi bean definitions | Phải xem xét thời điểm AOT đánh giá profile/condition |

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class StorageConfiguration {
    @Bean
    StorageClient storageClient(StorageProperties properties) {
        return new StorageClient(
            properties.getEndpoint(),
            properties.getBucket()
        );
    }
}
~~~

Bean `StorageClient` vẫn được tạo lúc ứng dụng khởi động và nhận giá trị đã bind từ `StorageProperties`. Nếu endpoint thay đổi giữa staging và production, có thể cung cấp property khác khi chạy native.

Ngược lại:

~~~java
@Bean
@ConditionalOnProperty(prefix = "app.storage", name = "enabled", havingValue = "true")
StorageClient storageClient(StorageProperties properties) {
    return new StorageClient(properties.getEndpoint(), properties.getBucket());
}
~~~

Điều kiện quyết định **có bean hay không** có thể được xử lý trong giai đoạn AOT. Nếu build AOT trong cấu hình khiến bean không được đăng ký, đổi `app.storage.enabled=true` khi runtime không tự làm Spring tạo lại bean graph đã sinh.

Không đưa credential bí mật vào cấu hình dùng ở build time hoặc vào generated artifact. Secret nên được cung cấp qua secret manager, environment hoặc nguồn cấu hình runtime thích hợp; tránh ghi chúng vào log, generated file hay container layer.

## 10. Validation và lỗi binding

`@ConfigurationProperties` hỗ trợ validation khi class được đánh dấu `@Validated` và validation provider có trên classpath.

Ví dụ:

~~~java
@Validated
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {

    @NotBlank
    private String bucket;

    @Min(1)
    @Max(60)
    private int connectTimeoutSeconds = 5;

    // getters/setters
}
~~~

Nếu `bucket` bị bỏ trống hoặc timeout ngoài giới hạn, ứng dụng có thể thất bại ngay khi khởi động. Đây là hành vi có ích: cấu hình sai được phát hiện trước khi endpoint nhận traffic.

Với object lồng nhau, dùng `@Valid` để yêu cầu validation đi sâu vào object con:

~~~java
@Valid
private Credentials credentials;
~~~

Khi lỗi xuất hiện trên native:

- Kiểm tra property key có đúng prefix và tên canonical không.
- Xác nhận property source có thực sự được nạp.
- Kiểm tra lỗi chuyển đổi kiểu (ví dụ chuỗi không phải duration hợp lệ).
- Kiểm tra validation constraint và dependency validation provider.
- Phân biệt lỗi Binder với lỗi reflection/reachability do Native Image.

## 11. Kiểm thử binding trên JVM và native executable

Không nên chỉ dựa vào việc native image build thành công. Cần kiểm tra các giá trị thực sự được bind ở runtime.

### 11.1. Test context với property tường minh

Ví dụ Spring Boot integration test:

~~~java
@SpringBootTest(properties = {
    "app.storage.bucket=test-bucket",
    "app.storage.connect-timeout=2s",
    "app.storage.endpoint=https://localhost"
})
class StoragePropertiesTest {

    @Autowired
    private StorageProperties properties;

    @Test
    void bindsConfiguredValues() {
        assertThat(properties.getBucket()).isEqualTo("test-bucket");
        assertThat(properties.getConnectTimeout()).isEqualTo(Duration.ofSeconds(2));
        assertThat(properties.getEndpoint()).isEqualTo(URI.create("https://localhost"));
    }
}
~~~

Test cần import static AssertJ phù hợp và dependency test của dự án. Mục tiêu là xác nhận Binder tạo đúng kiểu/giá trị và validation được áp dụng.

### 11.2. Test override từ environment khi chạy native

Sau khi tạo executable, chạy với property khác:

~~~bash
APP_STORAGE_BUCKET=runtime-bucket ./target/storage-service
~~~

Tạo một endpoint hoặc log an toàn để xác nhận bucket đang dùng là giá trị runtime. Không in credential/secret để kiểm tra cấu hình.

### 11.3. Native test và smoke test

Nếu dự án cấu hình native test qua GraalVM Native Build Tools, hãy chạy test native phù hợp. Ngoài ra, một smoke test thực thi binary/container trong môi trường gần production giúp phát hiện lỗi mà test JVM không thể mô phỏng, chẳng hạn thiếu reflection metadata hoặc resource.

Một ma trận kiểm thử hữu ích:

| Trường hợp | JVM test | Native test/smoke |
| --- | --- | --- |
| YAML binding | Kiểm tra giá trị mặc định và giá trị khai báo | Xác nhận binary đọc được Config Data |
| Environment override | Cấp env var trong test/process | Chạy binary với env var khác build time |
| Type conversion | Duration, URI, enum, list/map | Xác nhận chuyển đổi giống JVM |
| Validation | Giá trị thiếu/sai phải báo lỗi | Xác nhận native khởi động thất bại rõ ràng |
| Nested properties | Bind object con và collection | Xác nhận các kiểu lồng nhau hoạt động |
| Conditional bean | Test cấu hình condition | Xác nhận bean graph đúng với biến thể đã AOT |

## 12. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không inject được properties bean | Chưa scan hoặc enable class | Thêm `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Giá trị luôn null/default | Prefix/key sai hoặc property source chưa được nạp | Kiểm tra tên canonical, profile và Config Data |
| JVM bind được nhưng native lỗi reflection | Kiểu/thành viên động chưa có metadata | Xác nhận properties type đã đăng ký; xem runtime hints và lỗi cụ thể |
| Environment variable không override | Chuyển đổi tên env var sai | Áp dụng quy tắc uppercase, dot thành underscore, bỏ dash |
| Lỗi convert Duration/URI/enum | Giá trị cấu hình không hợp lệ hoặc converter thiếu | Dùng format được hỗ trợ; kiểm tra custom converter |
| Validation không chạy | Thiếu `@Validated` hoặc validation provider | Thêm annotation và dependency phù hợp |
| Nested object không được validate | Thiếu `@Valid` ở thuộc tính cha | Đánh dấu cascade validation |
| Runtime bật feature nhưng bean không xuất hiện | Condition/bean graph đã được xử lý ở AOT với cấu hình khác | Build AOT với cấu hình phù hợp hoặc thiết kế lại feature thành runtime logic |
| Secret xuất hiện trong artifact | Đã đưa secret vào build-time property hoặc generated output | Loại secret khỏi build, cung cấp qua secret store lúc runtime |

Khi chẩn đoán native, hãy phân loại:

1. **Không có bean:** xem đăng ký configuration properties và điều kiện AOT.
2. **Có bean nhưng giá trị sai:** xem property source, tên key, conversion và validation.
3. **Chỉ native mới lỗi:** xem reachability metadata/runtime hints cho kiểu hoặc converter liên quan.
4. **Đổi cấu hình runtime nhưng bean graph không đổi:** xem condition đã được quyết định ở thời điểm AOT hay chưa.

## 13. Quy trình thực hành từ source đến native

Giả sử dịch vụ lưu trữ dùng `app.storage` và cần cùng một binary chạy ở staging/production với bucket, endpoint và timeout khác nhau.

**Bước 1 — khai báo và đăng ký properties**

- Tạo `StorageProperties` với kiểu Java phù hợp.
- Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
- Thêm validation nếu các giá trị bắt buộc.

**Bước 2 — cấu hình mặc định không chứa secret**

~~~yaml
app:
  storage:
    bucket: local-test
    connect-timeout: 5s
    endpoint: https://storage.example.internal
~~~

Không commit credential vào file cấu hình hoặc JAR.

**Bước 3 — chạy test JVM**

~~~bash
./mvnw test
# Hoặc:
./gradlew test
~~~

Xác nhận binding, conversion, nested values và validation.

**Bước 4 — chạy Spring AOT và tạo native image**

Với Maven, dùng profile/goal đã cấu hình trong POM; với Gradle, dùng task `nativeCompile` sau khi plugin Spring Boot và Native Build Tools được tích hợp. Kiểm tra log AOT và native compilation.

**Bước 5 — chạy executable với cấu hình runtime**

~~~bash
APP_STORAGE_BUCKET=staging-invoices ./target/storage-service
~~~

Với production, truyền bucket/endpoint/secret từ secret manager hoặc environment của nền tảng triển khai. Không rebuild chỉ để đổi giá trị thuộc tính runtime.

**Bước 6 — kiểm thử bean graph và các feature có điều kiện**

Nếu một property dùng trong `@ConditionalOnProperty` làm thay đổi việc đăng ký bean, hãy xác nhận cấu hình đó đã được áp dụng trong AOT. Khi cần các biến thể cấu trúc bean khác nhau, cân nhắc tạo artifact native riêng hoặc thay đổi thiết kế để điều kiện được xử lý ở runtime.

## 14. Ghi nhớ

- `@ConfigurationProperties` tạo một mô hình cấu hình có kiểu; Binder vẫn đọc giá trị từ Environment/Config Data khi ứng dụng native khởi động.
- Spring AOT nhận diện các properties type đã được đăng ký và chuẩn bị metadata cần thiết để Native Image giữ được khả năng binding.
- Environment variable, system property và file cấu hình runtime có thể cung cấp giá trị khác nhau cho cùng một native executable.
- Bean conditions và cấu trúc ApplicationContext có thể được quyết định ở build time; đừng nhầm chúng với giá trị thuộc tính được bind lúc runtime.
- Nếu JVM hoạt động nhưng native lỗi, kiểm tra registration, conversion, validation và reachability hints theo đúng triệu chứng trước khi bổ sung metadata thủ công.

Hiểu ranh giới **AOT chuẩn bị khả năng binding — Binder lấy giá trị ở runtime — Native Image giữ các kiểu/thành viên cần thiết** giúp cấu hình một Spring Boot native executable an toàn, linh hoạt giữa các môi trường và dễ chẩn đoán.
