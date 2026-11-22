# Chọn constructor bằng `@ConstructorBinding` khi có nhiều constructor — Spring Boot 3.3

## 1. Vấn đề cần giải quyết

Khi sử dụng cấu hình bên ngoài trong Spring Boot, ta thường gom các khóa liên quan vào một lớp `@ConfigurationProperties` rồi để Spring Boot liên kết giá trị từ `application.properties`, YAML, biến môi trường hoặc đối số dòng lệnh thành đối tượng Java.

Với một lớp chỉ có **một constructor có tham số**, Spring Boot 3.3 thường có thể tự suy ra rằng phải dùng constructor đó để binding. Nhưng khi cùng một lớp có **nhiều constructor**, ví dụ một constructor đầy đủ và một constructor tiện lợi cho việc tạo đối tượng trong unit test, Spring Boot cần biết **constructor nào đại diện cho cấu trúc dữ liệu cấu hình**.

Trong trường hợp đó, dùng annotation:

```java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
```

và đặt `@ConstructorBinding` **trên constructor được chọn**.

Bài này giải thích cơ chế lựa chọn, phân biệt constructor binding với JavaBean binding và Dependency Injection (DI) thông thường, xây dựng ví dụ chạy được, áp dụng cho `record`, `@DefaultValue`, đối tượng lồng nhau và validation, đồng thời trình bày các lỗi phổ biến của Spring Boot 3.3.

**Phạm vi:** Spring Boot 3.3.x, Java 17 trở lên. Cú pháp API và import trong bài dành cho Spring Boot 3.x; không sao chép máy móc ví dụ sử dụng vị trí annotation của phiên bản cũ.

## 2. Hiểu đúng constructor binding

Giả sử cấu hình:

```yaml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 4
```

Một lớp cấu hình bất biến:

```java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    private final URI baseUrl;
    private final Duration connectTimeout;
    private final int maxRetries;

    public ClientProperties(
            URI baseUrl,
            Duration connectTimeout,
            int maxRetries
    ) {
        this.baseUrl = baseUrl;
        this.connectTimeout = connectTimeout;
        this.maxRetries = maxRetries;
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
```

Các import Java và Spring Boot cần có:

```java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
```

Khi bean được đăng ký theo cơ chế `@ConfigurationProperties`, Spring Boot Binder sử dụng tên tham số constructor để tìm các khóa tương ứng:

```text
app.client.base-url        -> baseUrl: URI
app.client.connect-timeout -> connectTimeout: Duration
app.client.max-retries     -> maxRetries: int
```

Nó chuyển giá trị chuỗi sang kiểu Java tương ứng rồi gọi constructor với các đối số đã được binding.

```text
Nguồn cấu hình bên ngoài
          |
          v
 Spring Boot Binder
  - tìm prefix app.client
  - nhận diện tham số constructor
  - relaxed binding tên khóa
  - chuyển kiểu URI / Duration / int
          |
          v
new ClientProperties(baseUrl, connectTimeout, maxRetries)
          |
          v
Bean cấu hình bất biến được các bean khác sử dụng
```

Điểm quan trọng: các tham số này đến từ **thuộc tính cấu hình**, không phải từ những bean khác trong Spring context. Constructor binding là **gắn dữ liệu cấu hình vào đối tượng**, không phải cơ chế tự động tiêm dependency nghiệp vụ.

## 3. Một constructor có tham số: không cần annotation

Spring Boot 3.3 có quy tắc suy luận: khi một kiểu cấu hình chỉ có **một constructor có tham số** đủ điều kiện, constructor binding được chọn ngầm định.

Ví dụ:

```java
package example.binding;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cache")
public final class CacheProperties {

    private final boolean enabled;
    private final int maxEntries;

    public CacheProperties(boolean enabled, int maxEntries) {
        this.enabled = enabled;
        this.maxEntries = maxEntries;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public int getMaxEntries() {
        return maxEntries;
    }
}
```

Tệp `application.properties`:

```properties
app.cache.enabled=true
app.cache.max-entries=500
```

Không cần thêm `@ConstructorBinding` vào constructor trên.

**Tại sao?** Không có lựa chọn nào khác để gây nhập nhằng; Binder có một constructor thích hợp để tạo đối tượng. Viết annotation trong trường hợp này không sai về mục đích, nhưng không phải bắt buộc.

Tuy nhiên, cần đáp ứng những điều kiện của constructor binding: kiểu cấu hình được đăng ký đúng cách, tên tham số có sẵn khi biên dịch, và không đánh dấu constructor theo cách khiến Spring bỏ cơ chế constructor binding.

### Không đồng nghĩa với mọi constructor đều được binding tự động

Nếu bạn có:

```java
public CacheProperties() { ... }

public CacheProperties(boolean enabled, int maxEntries) { ... }
```

thì lớp đã có **nhiều constructor**. Không nên giả định Spring Boot tự chọn đúng constructor có hai tham số. Khi muốn dùng constructor có tham số, hãy chỉ rõ bằng `@ConstructorBinding`.

## 4. Nhiều constructor: đánh dấu constructor cần binding

Ví dụ lớp `ClientProperties` có hai cách tạo đối tượng:

- Constructor đầy đủ dùng khi ứng dụng nạp cấu hình.
- Constructor tiện lợi với một URL, dùng trong code hoặc test.

```java
package example.binding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public final class ClientProperties {

    private final URI baseUrl;
    private final Duration connectTimeout;
    private final int maxRetries;

    @ConstructorBinding
    public ClientProperties(
            URI baseUrl,
            @DefaultValue("3s") Duration connectTimeout,
            @DefaultValue("3") int maxRetries
    ) {
        this.baseUrl = baseUrl;
        this.connectTimeout = connectTimeout;
        this.maxRetries = maxRetries;
    }

    public ClientProperties(URI baseUrl) {
        this(baseUrl, Duration.ofSeconds(3), 3);
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
```

Tệp `application.yaml`:

```yaml
app:
  client:
    base-url: https://api.example.test
    max-retries: 5
```

Trong tình huống này:

1. Binder nhận biết kiểu `ClientProperties`.
2. Nó thấy **constructor đầy đủ** có `@ConstructorBinding`.
3. Nó tìm giá trị của `baseUrl`, `connectTimeout` và `maxRetries` dưới `app.client`.
4. `connect-timeout` không được cung cấp, nên `@DefaultValue("3s")` cung cấp giá trị cho tham số `Duration`.
5. `max-retries=5` từ YAML được chuyển thành `int`.
6. Constructor ba tham số được gọi để tạo bean cấu hình.

Kết quả giá trị:

```text
baseUrl        = https://api.example.test
connectTimeout = PT3S
maxRetries     = 5
```

Constructor một tham số **không phải constructor Binder chọn**, dù constructor đó vẫn có thể được gọi khi bạn chủ động viết `new ClientProperties(uri)` trong mã Java.

### Tại sao annotation đặt trên constructor, không trên class?

Trong Spring Boot 3.3, API `org.springframework.boot.context.properties.bind.ConstructorBinding` có target gồm `CONSTRUCTOR` và `ANNOTATION_TYPE`. Nó phục vụ việc **chỉ định constructor**. Do đó:

```java
@ConfigurationProperties(prefix = "app.client")
public final class ClientProperties {
    @ConstructorBinding
    public ClientProperties(URI baseUrl, Duration timeout) {
        // ...
    }
}
```

là cách đặt đúng trong phiên bản này.

Không dùng ví dụ cũ với:

```java
@ConstructorBinding
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    // ...
}
```

vì annotation với package/target của Spring Boot 3.3 không có mục đích đặt trên kiểu theo cách đó.

## 5. Chọn một constructor trong nhiều constructor để tránh điều gì?

Nếu một lớp có nhiều constructor với cùng mục đích chung nhưng tham số khác nhau, chẳng hạn:

```java
public ClientProperties(URI baseUrl) { ... }

public ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxRetries
) { ... }
```

Spring Boot không thể dựa vào **số lượng tham số** để đoán chắc bạn muốn dùng constructor nào. Constructor ít tham số có thể dùng cho test, nhưng cũng có thể là constructor chứa toàn bộ cấu hình cần thiết. Constructor nhiều tham số có thể phục vụ logic khác và không nhất thiết là cấu trúc cấu hình.

`@ConstructorBinding` là một **quyết định thiết kế rõ ràng**:

```text
Có nhiều constructor
        |
        v
Constructor nào mô tả dữ liệu của @ConfigurationProperties?
        |
        v
Đặt @ConstructorBinding lên constructor ấy
        |
        v
Binder lấy tham số của constructor đã chọn
```

Ưu điểm:

- Không phụ thuộc vào việc IDE, Lombok hoặc refactor sinh thêm constructor.
- Người đọc biết constructor nào phản ánh schema cấu hình.
- Không cần setter để đưa dữ liệu vào các field `final`.
- Giữ được constructor tiện lợi cho unit test hoặc code khởi tạo thủ công.
- Có thể đặt `@DefaultValue` trên đúng tham số mà Binder sử dụng.

Khi thêm constructor mới, **không tự ý thêm một `@ConstructorBinding` thứ hai**. Mục tiêu là chỉ rõ một constructor dùng cho cấu hình, không phải khai báo một tập constructor để Binder thử lần lượt.

## 6. Phân biệt `@ConstructorBinding` với `@Autowired`

Đây là nhầm lẫn quan trọng nhất.

### 6.1. `@ConstructorBinding` nhận giá trị cấu hình

```java
@ConfigurationProperties(prefix = "app.report")
public final class ReportProperties {
    private final String title;
    private final int batchSize;

    @ConstructorBinding
    public ReportProperties(String title, int batchSize) {
        this.title = title;
        this.batchSize = batchSize;
    }

    public String getTitle() { return title; }
    public int getBatchSize() { return batchSize; }
}
```

Hai tham số `title`, `batchSize` tương ứng với khóa cấu hình `app.report.title`, `app.report.batch-size`.

### 6.2. `@Autowired` là DI cho bean

```java
@Service
public class ReportService {

    private final ReportProperties settings;
    private final ReportRepository repository;

    public ReportService(
            ReportProperties settings,
            ReportRepository repository
    ) {
        this.settings = settings;
        this.repository = repository;
    }
}
```

Spring container tạo `ReportService` bằng cách tiêm **bean** `ReportProperties` và **bean** `ReportRepository`, không lấy một thuộc tính tên `reportRepository` từ YAML.

Khi chỉ có một constructor, Spring Framework thường tự sử dụng constructor đó để DI mà không cần thêm `@Autowired`. Nếu lớp bean thông thường có nhiều constructor, quy tắc chọn constructor cho DI có thể cần `@Autowired`; đây là bài toán khác với lựa chọn constructor cấu hình.

### 6.3. Không dùng hai annotation để “tăng khả năng nhận dữ liệu”

Sai về ý tưởng:

```java
@Autowired
@ConstructorBinding
public ReportProperties(String title, int batchSize) {
    // ...
}
```

Đừng gắn cả hai lên một constructor với hy vọng Spring vừa tìm bean `String`, `int` vừa đọc file cấu hình. Hai annotation thể hiện **hai cơ chế tạo đối tượng khác nhau**.

Tài liệu Spring Boot 3.3 cũng nêu rằng nếu muốn *không dùng constructor binding* với một constructor có tham số, có thể đánh dấu constructor ấy bằng `@Autowired` hoặc dùng một constructor `private`, tùy thiết kế JavaBean binding. Nhưng đó không phải là phương án thông thường để tạo cấu hình bất biến.

### Bảng so sánh nhanh

| Tiêu chí | Constructor binding | Constructor injection |
| --- | --- | --- |
| Thành phần chọn dữ liệu | Spring Boot Binder | Spring container |
| Đối số đến từ | Các khóa trong `Environment` | Các bean phù hợp trong context |
| Khai báo chính | `@ConfigurationProperties` + constructor thích hợp | `@Component`, `@Service`, `@Configuration`, ... |
| Khi nhiều constructor | `@ConstructorBinding` trên constructor được chọn | Có thể dùng `@Autowired` theo quy tắc DI |
| Mục tiêu | Tạo object cấu hình có kiểu | Kết nối các thành phần ứng dụng |
| Nên có field `final` | Rất phù hợp | Cũng rất phù hợp |
| Có dùng `@DefaultValue` cho giá trị cấu hình | Có | Không theo cùng cơ chế Binder |

## 7. Không gắn `@Component` cho kiểu dùng constructor binding

Spring Boot 3.3 chỉ ra giới hạn cụ thể: **constructor binding không dùng với bean được tạo bằng những cơ chế tạo bean thông thường** như `@Component`, phương thức `@Bean` hay `@Import`.

Ví dụ dễ gây nhầm:

```java
@Component
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {
    @ConstructorBinding
    public ClientProperties(String baseUrl) {
        // ...
    }
}
```

Với `@Component`, Spring cố tạo object theo quy tắc bean thông thường, không theo quy trình constructor binding chuyên biệt dành cho bean configuration properties. Kết quả có thể thất bại hoặc không hoạt động theo mong muốn.

**Cách đăng ký đúng khi dùng constructor binding:**

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Hoặc đăng ký trực tiếp:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientConfiguration {
}
```

Các import tương ứng:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
```

Hai cơ chế trên giúp Spring Boot **nhận diện và đăng ký bean cấu hình**. Sau đó bean ấy có thể được tiêm vào các service bình thường.

### Đăng ký kiểu nào?

- `@ConfigurationPropertiesScan`: phù hợp khi ứng dụng có nhiều kiểu cấu hình tự định nghĩa trong các package được quét.
- `@EnableConfigurationProperties(TheProperties.class)`: phù hợp khi muốn khai báo tường minh một hoặc vài kiểu, ví dụ trong module hoặc auto-configuration.
- `@Bean @ConfigurationProperties`: thường hữu ích để liên kết các thuộc tính JavaBean vào một bean của thư viện bên thứ ba, **không phải cách tương đương để constructor-bind một class cấu hình bất biến**.

Nếu project chỉ có một kiểu cấu hình, cả scan lẫn enable trực tiếp đều có thể phù hợp. Tránh đăng ký trùng không cần thiết khi một cấu hình đã được xử lý qua cơ chế khác.

## 8. Ví dụ hoàn chỉnh: hai constructor, một constructor được chọn

Ví dụ sau dùng **Spring Boot 3.3.x**, Java 17 và dependency `spring-boot-starter`. Tên package là `example.constructorbinding`.

### 8.1. Tệp cấu hình

`src/main/resources/application.yaml`:

```yaml
spring:
  application:
    name: constructor-binding-demo

app:
  delivery:
    endpoint: https://delivery.example.test
    max-retries: 6
    connect-timeout: 2s
```

### 8.2. Lớp có hai constructor

`src/main/java/example/constructorbinding/DeliveryProperties.java`:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.delivery")
public final class DeliveryProperties {

    private final URI endpoint;
    private final int maxRetries;
    private final Duration connectTimeout;

    @ConstructorBinding
    public DeliveryProperties(
            URI endpoint,
            @DefaultValue("3") int maxRetries,
            @DefaultValue("5s") Duration connectTimeout
    ) {
        this.endpoint = endpoint;
        this.maxRetries = maxRetries;
        this.connectTimeout = connectTimeout;
    }

    // Tiện lợi cho code/test tạo đối tượng trực tiếp.
    public DeliveryProperties(URI endpoint) {
        this(endpoint, 3, Duration.ofSeconds(5));
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }
}
```

Đây là một lớp cấu hình bất biến:

- Ba field đều `final`.
- Constructor ba tham số là **điểm vào của Binder**.
- Constructor một tham số gọi lại constructor đầy đủ bằng `this(...)` nhưng **không được Binder chọn**.
- Không cần setter.
- `@DefaultValue` có thể áp dụng nếu một khóa không xuất hiện trong những nguồn cấu hình được xét.

### 8.3. Đăng ký và in giá trị

`src/main/java/example/constructorbinding/DemoApplication.java`:

```java
package example.constructorbinding;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showDeliveryProperties(DeliveryProperties config) {
        return args -> {
            System.out.println("endpoint=" + config.getEndpoint());
            System.out.println("maxRetries=" + config.getMaxRetries());
            System.out.println("connectTimeout=" + config.getConnectTimeout());
        };
    }
}
```

`@ConfigurationPropertiesScan` quét các kiểu `@ConfigurationProperties` trong phạm vi package phù hợp. Phương thức `showDeliveryProperties` nhận **bean cấu hình đã được tạo sẵn**, không tự gọi constructor.

### 8.4. Khởi động

Từ dự án dùng Maven wrapper:

```bash
./mvnw spring-boot:run
```

Hoặc chạy JAR đã đóng gói (thay tên minh họa bằng tên JAR thực tế):

```bash
java -jar app.jar
```

Các dòng kết quả chính:

```text
endpoint=https://delivery.example.test
maxRetries=6
connectTimeout=PT2S
```

Spring Boot dùng `app.delivery.endpoint`, `app.delivery.max-retries`, `app.delivery.connect-timeout`. Với các giá trị này, tham số mặc định `@DefaultValue` không cần dùng.

### 8.5. Quan sát default khi thiếu thuộc tính

Giữ lại trong YAML:

```yaml
app:
  delivery:
    endpoint: https://delivery.example.test
```

Sau khi chạy lại, dự kiến:

```text
endpoint=https://delivery.example.test
maxRetries=3
connectTimeout=PT5S
```

`maxRetries=3` đến từ `@DefaultValue("3")`; `connectTimeout=PT5S` đến từ `@DefaultValue("5s")`.

Điểm quan trọng là **giá trị mặc định nằm trên tham số của constructor được Binder chọn**. Nếu chỉ gắn default ở một constructor tiện lợi khác mà Binder không sử dụng, bạn không có bảo đảm rằng default đó tham gia binding.

### 8.6. Quan sát nguồn cấu hình ưu tiên hơn

Trong terminal:

```bash
java -jar app.jar --app.delivery.max-retries=9
```

Với thứ tự ưu tiên thông thường, tham số dòng lệnh có thể ghi đè `max-retries` trong YAML. Binder vẫn dùng **cùng constructor**, nhưng giá trị đưa vào `maxRetries` đổi thành `9`.

**Chọn constructor** và **chọn giá trị cấu hình có hiệu lực** là hai vấn đề độc lập:

```text
Nguồn nào cho ra max-retries?  --> PropertySource precedence
Constructor nào nhận giá trị? --> @ConstructorBinding
```

## 9. Record trong Java 17: thông thường không cần annotation

Record rất phù hợp cho một cấu hình bất biến:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.client")
public record ClientOptions(
        URI endpoint,
        @DefaultValue("3") int retryCount,
        @DefaultValue("5s") Duration timeout
) {
}
```

Với record đơn giản này, constructor canonical được tạo dựa trên các component. Nếu đó là constructor phù hợp duy nhất, Spring Boot 3.3 **không yêu cầu** `@ConstructorBinding`.

Cấu hình:

```properties
app.client.endpoint=https://api.example.test
app.client.retry-count=4
app.client.timeout=2s
```

Kết quả tương ứng:

```text
endpoint   = https://api.example.test
retryCount = 4
timeout    = PT2S
```

Record giúp tránh việc viết thủ công field `final`, constructor và getter. Nhưng **record không phải cơ chế khác**: nó vẫn có thể được constructor-bind bởi Binder, và vẫn cần đăng ký kiểu cấu hình qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

## 10. Record có nhiều constructor: chọn constructor canonical rõ ràng

Record vẫn có thể có constructor bổ sung. Ví dụ cần một constructor một tham số để tạo object thử nghiệm:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "app.remote")
public record RemoteOptions(
        URI endpoint,
        int maxRetries,
        Duration timeout
) {
    @ConstructorBinding
    public RemoteOptions(URI endpoint, int maxRetries, Duration timeout) {
        this.endpoint = endpoint;
        this.maxRetries = maxRetries;
        this.timeout = timeout;
    }

    public RemoteOptions(URI endpoint) {
        this(endpoint, 3, Duration.ofSeconds(5));
    }
}
```

Trong ví dụ:

- Constructor ba tham số là constructor canonical của record, chứa toàn bộ component.
- Constructor một tham số là constructor bổ sung.
- `@ConstructorBinding` gắn với constructor ba tham số để chỉ rõ đây là constructor cho cấu hình.
- Constructor bổ sung gọi `this(...)` theo quy tắc Java record.

Cấu hình:

```properties
app.remote.endpoint=https://remote.example.test
app.remote.max-retries=7
app.remote.timeout=4s
```

Binder dùng giá trị từ ba khóa thay vì tự chọn convenience constructor một tham số.

Một record chỉ có constructor canonical mặc định thì đơn giản hơn; **đừng thêm constructor phụ chỉ vì muốn truyền giá trị mặc định**. Nếu default là thuộc tính cấu hình, `@DefaultValue` thường biểu đạt rõ ý định hơn.

## 11. `@DefaultValue` nằm ở đâu khi có nhiều constructor?

Trong Spring Boot 3.3, `@DefaultValue` được hỗ trợ trên **tham số constructor** và **record component**. Khi chọn constructor bằng annotation, các mặc định phục vụ binding nên nằm trên tham số constructor ấy.

Ví dụ:

```java
@ConfigurationProperties(prefix = "app.job")
public final class JobProperties {

    private final int concurrency;
    private final Duration pause;

    @ConstructorBinding
    public JobProperties(
            @DefaultValue("4") int concurrency,
            @DefaultValue("250ms") Duration pause
    ) {
        this.concurrency = concurrency;
        this.pause = pause;
    }

    public JobProperties() {
        this(4, Duration.ofMillis(250));
    }

    public int getConcurrency() { return concurrency; }
    public Duration getPause() { return pause; }
}
```

Cấu hình:

```yaml
app:
  job:
    concurrency: 8
```

Giá trị sau binding dự kiến:

```text
concurrency = 8
pause       = PT0.25S
```

Mặc dù có constructor không tham số, Binder được hướng dẫn chọn constructor hai tham số. Constructor không tham số chỉ là phương thức khởi tạo Java khác.

### 11.1. Default không phải validation

`@DefaultValue("4")` không ngăn một nguồn cấu hình đưa `-10` vào `concurrency`. Nếu giá trị tồn tại nhưng vi phạm quy tắc nghiệp vụ, cần dùng validation.

Đồng thời, constructor binding không tự bảo đảm một giá trị tham chiếu như `URI endpoint` luôn được cung cấp. Nếu dữ liệu thiếu, tham số tham chiếu có thể là `null` khi không có default hoặc validation. Hãy khai báo ràng buộc bắt buộc thay vì coi mọi tham số constructor là tự động required.

### 11.2. Không nhầm constructor tiện lợi với giá trị mặc định của Binder

Hai dòng:

```java
public JobProperties() {
    this(4, Duration.ofMillis(250));
}
```

là default **khi một đoạn Java gọi `new JobProperties()`**.

Còn:

```java
@DefaultValue("4") int concurrency
```

là default **khi Spring Boot Binder liên kết tham số constructor** và nguồn cấu hình không cung cấp giá trị tương ứng.

Cách viết có thể cho cùng số ở một ví dụ, nhưng **nguồn sinh ra giá trị và thời điểm áp dụng khác nhau**.

## 12. Đối tượng lồng nhau cũng được constructor-bind

Với cấu hình có nhóm:

```yaml
app:
  service:
    endpoint: https://service.example.test
    retry:
      max-attempts: 4
      backoff: 250ms
```

Ta có thể dùng một lớp chứa record lồng:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.service")
public final class ServiceProperties {

    private final URI endpoint;
    private final Retry retry;

    @ConstructorBinding
    public ServiceProperties(URI endpoint, Retry retry) {
        this.endpoint = endpoint;
        this.retry = retry;
    }

    public ServiceProperties(URI endpoint) {
        this(endpoint, new Retry(3, Duration.ofMillis(500)));
    }

    public URI getEndpoint() { return endpoint; }
    public Retry getRetry() { return retry; }

    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("500ms") Duration backoff
    ) {
    }
}
```

Binder sẽ liên kết:

```text
app.service.endpoint           -> ServiceProperties.endpoint
app.service.retry.max-attempts -> Retry.maxAttempts
app.service.retry.backoff      -> Retry.backoff
```

`Retry` cũng được constructor-bind dựa trên cấu trúc record lồng. **Không bắt buộc** viết `@ConstructorBinding` trên mỗi record con khi chúng chỉ có constructor hợp lệ duy nhất.

### 12.1. Nếu cả nhóm nested bị thiếu?

Nếu không có khóa nào dưới `app.service.retry`, đối tượng nested `retry` có thể không được tạo, dù record `Retry` có `@DefaultValue` trên các trường. Nếu muốn vẫn tạo một nested object để các default con được áp dụng, Spring Boot hỗ trợ `@DefaultValue` **rỗng** trên tham số nested:

```java
@ConstructorBinding
public ServiceProperties(
        URI endpoint,
        @DefaultValue Retry retry
) {
    this.endpoint = endpoint;
    this.retry = retry;
}
```

Trong tình huống này, Binder được hướng dẫn liên kết nested object ngay cả khi không có khóa con, cho phép mặc định trong `Retry` tham gia.

Hãy phân biệt:

```text
Không có app.service.retry.* + không có @DefaultValue ở nested
    -> nested object có thể là null

Không có app.service.retry.* + có @DefaultValue rỗng ở nested
    -> Binder có thể tạo nested object từ các default của con
```

Không sử dụng `@DefaultValue` rỗng như một cách ẩn lỗi bắt buộc. Nếu cấu hình `retry` phải được cung cấp thật, hãy dùng validation hoặc cách kiểm tra phù hợp.

## 13. Metadata tên tham số: cần `-parameters`

Binder phải biết tham số constructor tương ứng với khóa cấu hình nào. Với Java class thông thường:

```java
public ClientProperties(URI baseUrl, int maxRetries) {
    // ...
}
```

Tên tham số `baseUrl`, `maxRetries` cần được giữ lại trong metadata khi biên dịch. Spring Boot 3.3 yêu cầu class có constructor binding được biên dịch với tùy chọn:

```text
-parameters
```

Tùy chọn này khiến Java compiler giữ tên tham số để reflection/Binder sử dụng.

Theo tài liệu Spring Boot, cơ chế build từ **Spring Boot Gradle plugin** hoặc **Maven với `spring-boot-starter-parent`** thường cấu hình việc này tự động.

Nếu project dùng cấu hình build tự tùy chỉnh, hãy bảo đảm plugin biên dịch Java bật flag tương ứng.

Ví dụ Maven Compiler Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Ví dụ Gradle Groovy DSL khi muốn chỉ định trực tiếp:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Nếu không có metadata tên tham số, Spring Boot có thể không xác định đúng tên khóa cần liên kết và báo lỗi binding. Lỗi này **không phải do thiếu `@ConstructorBinding`**: annotation chọn constructor, còn `-parameters` giúp xác định tên tham số trên constructor đó.

### 13.1. Khác biệt với tên field

Nếu một constructor nhận:

```java
public ClientProperties(int retries) {
    this.maxRetries = retries;
}
```

thì tên tham số là `retries`, không phải `maxRetries`. Binder chủ yếu dựa vào tên tham số constructor được chọn; không nên giả định nó sẽ suy luận tùy ý từ trường được gán ở bên trong.

Ưu tiên đặt tên tham số thống nhất với dữ liệu cần binding:

```java
public ClientProperties(int maxRetries) {
    this.maxRetries = maxRetries;
}
```

Khi tên bắt buộc khác vì từ khóa Java hoặc lý do đặc biệt, Spring Boot còn có annotation `@Name` cho tham số constructor, chẳng hạn trường hợp muốn liên kết khóa tên `import` vốn là từ khóa của Java.

## 14. `@Name`: khi khóa cấu hình không thể đặt làm tên tham số Java

Giả sử cấu hình dùng khóa:

```properties
app.resources.import=https://source.example.test
```

Tên `import` là từ khóa Java, nên không thể viết:

```java
public ResourceProperties(String import) { ... }
```

Spring Boot cung cấp `@Name` trong package `org.springframework.boot.context.properties.bind`:

```java
package example.constructorbinding;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.Name;

@ConfigurationProperties(prefix = "app.resources")
public final class ResourceProperties {

    private final String importLocation;

    @ConstructorBinding
    public ResourceProperties(@Name("import") String importLocation) {
        this.importLocation = importLocation;
    }

    public ResourceProperties() {
        this.importLocation = "";
    }

    public String getImportLocation() {
        return importLocation;
    }
}
```

`@Name("import")` chỉ định tên cấu hình được dùng cho tham số constructor. Vì lớp có hai constructor nên `@ConstructorBinding` chọn constructor nhận `importLocation`.

Đây là một tình huống chuyên biệt; trong phần lớn dự án nên đặt tên khóa và tên tham số rõ ràng, không cần `@Name`.

## 15. Validation khi dùng constructor binding

Bất biến không có nghĩa là **giá trị hợp lệ**. Nếu dữ liệu chứa `max-retries=-10` hoặc thiếu endpoint, object bất biến vẫn có thể mang trạng thái không mong muốn nếu không áp dụng ràng buộc.

Với dependency `spring-boot-starter-validation`, có thể kết hợp:

```java
package example.constructorbinding;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public final class DeliveryProperties {

    @NotNull
    private final URI endpoint;

    @Min(0)
    private final int maxRetries;

    @NotNull
    private final Duration connectTimeout;

    @ConstructorBinding
    public DeliveryProperties(
            URI endpoint,
            @DefaultValue("3") int maxRetries,
            @DefaultValue("5s") Duration connectTimeout
    ) {
        this.endpoint = endpoint;
        this.maxRetries = maxRetries;
        this.connectTimeout = connectTimeout;
    }

    public DeliveryProperties(URI endpoint) {
        this(endpoint, 3, Duration.ofSeconds(5));
    }

    public URI getEndpoint() { return endpoint; }
    public int getMaxRetries() { return maxRetries; }
    public Duration getConnectTimeout() { return connectTimeout; }
}
```

Các annotation `@NotNull` và `@Min` mô tả ràng buộc dữ liệu, `@Validated` yêu cầu Spring Boot áp dụng validation cho configuration properties.

Khi dữ liệu không hợp lệ, lỗi có thể xảy ra ngay ở giai đoạn binding/validation thay vì đến lúc bean nghiệp vụ gọi API với endpoint rỗng hoặc số lần thử lại âm.

### Validation với nested object

Nếu cấu hình lồng nhau có ràng buộc, cần xem xét `@Valid` trên điểm tham chiếu nested và annotation trên các trường con để quá trình validation đi vào bên trong. Không nên mặc định mọi object con luôn được kiểm tra đầy đủ chỉ vì lớp cha có `@Validated`.

### Default và validation là hai việc khác nhau

- `@DefaultValue("3")` xử lý **thiếu giá trị**.
- `@Min(0)` xử lý **giá trị số ngoài miền chấp nhận**.
- `@NotNull` xử lý **vắng giá trị tham chiếu**.

Dùng đủ cơ chế theo yêu cầu thực tế, tránh lấy constructor tiện lợi để che cấu hình thiếu bắt buộc.

## 16. JavaBean binding khác constructor binding

Spring Boot hỗ trợ liên kết thông qua JavaBean getters/setters:

```java
@ConfigurationProperties(prefix = "app.cache")
public class MutableCacheProperties {
    private boolean enabled;
    private int maxEntries;

    public MutableCacheProperties() {
    }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }

    public int getMaxEntries() { return maxEntries; }
    public void setMaxEntries(int maxEntries) {
        this.maxEntries = maxEntries;
    }
}
```

Mô hình này:

1. Tạo object (thường bằng constructor không tham số).
2. Binder tìm các setter/property descriptor.
3. Binder đặt giá trị vào thuộc tính có thể thay đổi.

Mô hình constructor binding:

1. Binder đọc dữ liệu và chuyển kiểu.
2. Binder gọi constructor được chọn.
3. Object được tạo với giá trị hoàn chỉnh qua constructor.
4. Các field có thể là `final`, không cần setter.

| Khía cạnh | JavaBean binding | Constructor binding |
| --- | --- | --- |
| Cách cấp giá trị | Setter hoặc các cấu trúc mutable thích hợp | Tham số constructor |
| Trạng thái sau tạo | Thường có thể sửa | Dễ thiết kế bất biến |
| Constructor không tham số | Thường dùng | Không bắt buộc |
| Nhiều constructor | Có thể cấu hình cách tạo bean | Nên chọn bằng `@ConstructorBinding` |
| `@DefaultValue` trên tham số | Không phải công cụ chính | Rất phù hợp |
| Trường `final` | Không tiện cho setter thông thường | Rất phù hợp |
| Đăng ký qua scan hoặc enable | Có thể | Cần cho constructor binding |

Không có một kiểu duy nhất luôn tốt hơn. Một đối tượng cấu hình mới, có kiểu rõ ràng và cần bất biến thường phù hợp với constructor binding. Một thư viện cũ có JavaBean setters có thể phù hợp với JavaBean binding.

Điều quan trọng khi **một lớp có nhiều constructor** là không mơ hồ về chế độ binding thực sự đang dùng.

## 17. Lombok và constructor được sinh tự động

Lombok có thể sinh constructor dựa trên field:

```java
@RequiredArgsConstructor
public class ClientProperties {
    private final URI endpoint;
    private final int retries;
}
```

Khi cùng lớp có thêm `@NoArgsConstructor`, `@AllArgsConstructor`, constructor thủ công hoặc các annotation khác, số lượng constructor thực tế có thể khác những gì người viết nghĩ khi chỉ đọc field.

Hậu quả có thể gồm:

- Lớp có nhiều constructor nhưng không chỉ định constructor cần dùng cho Binder.
- Lombok tạo constructor cùng chữ ký với constructor thủ công, gây lỗi biên dịch.
- Metadata tên tham số không được giữ nếu cấu hình build không phù hợp.
- Các annotation mặc định/validation không nằm ở vị trí mà Binder đọc.

Với lớp `@ConfigurationProperties` có nhiều constructor, cách rõ ràng nhất thường là **viết tường minh constructor được chọn**:

```java
@ConstructorBinding
public ClientProperties(URI endpoint, int retries) {
    this.endpoint = endpoint;
    this.retries = retries;
}
```

Có thể vẫn dùng Lombok để tạo getter nếu dự án muốn, nhưng đừng để lớp config phụ thuộc vào các constructor được sinh mà không kiểm soát ý nghĩa của chúng.

Record thường cho cấu hình bất biến gọn hơn Lombok trong Java 17, đặc biệt khi không cần constructor bổ sung.

## 18. Các trường hợp biên cần suy nghĩ kỹ

### 18.1. Hai constructor cùng số tham số

Ví dụ:

```java
public TimeoutProperties(Duration timeout, int attempts) { ... }
public TimeoutProperties(int attempts, Duration timeout) { ... }
```

Hai constructor cùng số tham số nhưng thứ tự khác nhau. Binder không nên phải đoán dựa vào số lượng hay thứ tự field; hãy đánh dấu chính xác constructor mô tả schema cấu hình.

### 18.2. Constructor một tham số để chuyển từ cấu trúc cũ

Một lớp có thể giữ constructor cũ:

```java
public ConnectorProperties(String url) {
    this(URI.create(url), Duration.ofSeconds(5));
}
```

và constructor mới:

```java
@ConstructorBinding
public ConnectorProperties(URI endpoint, Duration timeout) {
    // ...
}
```

Việc giữ constructor cũ phục vụ API Java không khiến Binder tự ưu tiên constructor ấy. Ngược lại, giá trị mặc định mà constructor cũ áp dụng không thay thế `@DefaultValue` của constructor mới.

### 18.3. Thêm constructor phụ cho unit test

Nếu test muốn dễ tạo object:

```java
new ConnectorProperties(URI.create("https://test.example"));
```

đó là lý do có thể giữ convenience constructor. Nhưng không cần tạo constructor phụ chỉ để test nếu record hoặc builder test đã đủ rõ. Mỗi constructor phụ làm tăng nhu cầu giữ sự chọn lựa explicit.

### 18.4. `@ConstructorBinding` trên kiểu phụ bên trong

Với cấu trúc nested có nhiều constructor, kiểu nested cũng cần có một cách xác định constructor đúng. Một constructor độc nhất cho record nested thường không cần annotation; nếu một class nested có nhiều constructor và dùng constructor binding, cần chỉ rõ tại nơi tương ứng, thay vì chỉ đặt annotation trên lớp cha rồi kỳ vọng mọi class con tự chọn đúng.

### 18.5. `Optional` trong configuration properties

Tài liệu Spring Boot không khuyến khích dùng `Optional` làm thuộc tính của `@ConfigurationProperties`, bởi `Optional` chủ yếu được thiết kế để làm kiểu trả về. Hãy dùng kiểu phù hợp, default hoặc validation theo yêu cầu, thay vì thêm `Optional` cho mọi tham số constructor.

### 18.6. Một lớp cấu hình không nên dùng để tiêm bean nghiệp vụ

Lỗi kiến trúc:

```java
@ConfigurationProperties(prefix = "app.worker")
public WorkerProperties(TaskRepository repository, int batchSize) {
    // ...
}
```

Trong constructor binding, Binder tìm thuộc tính cấu hình cho `repository` và `batchSize`; nó không tự động lấy bean `TaskRepository` cho một tham số rồi lấy `batchSize` từ cấu hình theo cách DI hỗn hợp.

Nếu cần repository, để `WorkerService` nhận `TaskRepository` và `WorkerProperties` như **hai bean riêng**:

```java
@Service
public class WorkerService {
    public WorkerService(
            TaskRepository repository,
            WorkerProperties settings
    ) {
        // ...
    }
}
```

`WorkerProperties` chỉ mô tả dữ liệu cấu hình; `WorkerService` phối hợp các dependency.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Giải pháp |
| --- | --- | --- |
| IDE báo `@ConstructorBinding` không đặt được lên class | Dùng vị trí đặt annotation của phiên bản cũ | Trong Spring Boot 3.3 đặt annotation trên **constructor** |
| IDE không tìm thấy `ConstructorBinding` | Import sai package | Dùng `org.springframework.boot.context.properties.bind.ConstructorBinding` |
| Lớp có nhiều constructor, Binder không chọn như mong muốn | Thiếu chỉ định constructor | Đặt `@ConstructorBinding` trên constructor cấu hình |
| Thêm `@Component` rồi không constructor-bind | Bean được tạo bằng cơ chế DI thông thường | Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Lỗi không biết tên tham số constructor | Thiếu metadata `-parameters` | Bật cờ compiler / dùng cấu hình build Boot phù hợp |
| Thiếu khóa cấu hình nhưng vẫn nhận `null` | Constructor binding không tự coi mọi tham số reference là required | Thêm `@NotNull` và validation hoặc default phù hợp |
| Thiếu nested object | Cả nhóm nested không có dữ liệu | Dùng `@DefaultValue` rỗng ở tham số nested nếu cần |
| Field có default nhưng khi binding không đúng | Default viết ở constructor khác hoặc field initializer | Đặt `@DefaultValue` ở tham số constructor được chọn |
| `@Autowired` bị nhầm với `@ConstructorBinding` | Nhầm DI và Binder | Tách kiểu cấu hình và service |
| Thêm nhiều constructor do Lombok rồi lỗi | Số constructor thực tế khác dự kiến | Viết tường minh constructor binding và kiểm soát annotation sinh code |
| Giá trị YAML khác giá trị trong object | Có nguồn ưu tiên hơn hoặc profile khác | Kiểm tra PropertySource và active profiles |
| Cấu hình có giá trị sai nhưng object vẫn tạo | Chưa có ràng buộc validation | Thêm `@Validated` và constraint |
| Record có constructor phụ và việc chọn không rõ | Không chỉ định constructor canonical | Đánh dấu canonical constructor phù hợp bằng `@ConstructorBinding` |
| Không có bean `ClientProperties` | Chưa đăng ký configuration properties | Thêm scan hoặc enable đúng package |

### Không tự động kết luận lỗi là do annotation

Nếu ứng dụng báo không bind được `Duration` vì giá trị `abc`, việc thêm `@ConstructorBinding` sẽ không biến chuỗi đó thành thời lượng hợp lệ. Tương tự, cấu hình có key sai chính tả hoặc profile chưa bật là vấn đề **dữ liệu nguồn**, không phải lỗi lựa chọn constructor.

Khi xử lý sự cố, hãy chia nguyên nhân thành bốn nhóm:

```text
1. Loại bean / cách đăng ký: scan, enable, @Component?
2. Constructor được chọn: một hay nhiều? Có @ConstructorBinding?
3. Dữ liệu nguồn: đúng key, đúng profile, đúng precedence?
4. Kiểu dữ liệu / validation: chuyển đổi thành công, ràng buộc hợp lệ?
```

## 20. Cách quan sát bean cấu hình sau khi binding

Nếu muốn thấy kết quả với dữ liệu mẫu, tạo một `ApplicationRunner`:

```java
@Bean
ApplicationRunner inspect(DeliveryProperties properties) {
    return args -> {
        System.out.println("endpoint=" + properties.getEndpoint());
        System.out.println("maxRetries=" + properties.getMaxRetries());
        System.out.println("connectTimeout="
                + properties.getConnectTimeout());
    };
}
```

Phương thức này phải được đặt **bên trong một lớp `@Configuration` hoặc `@SpringBootApplication` thích hợp**, không phải là một tệp Java độc lập chỉ có phương thức.

Khi ứng dụng đã tạo bean, bạn có thể so sánh giá trị thực với YAML hoặc biến môi trường. Nếu cần kiểm tra quá trình nạp config data:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Chỉ bật log chi tiết tạm thời ở môi trường phù hợp. Không in khóa bí mật, mật khẩu hoặc token thật; cơ chế này phục vụ quan sát dữ liệu cấu hình không nhạy cảm.

Dùng `Environment#getProperty` có thể giúp phân biệt giá trị nguồn và dữ liệu bean. Ví dụ:

```java
@Bean
ApplicationRunner inspectEnvironment(Environment env) {
    return args -> System.out.println(
            "app.delivery.max-retries="
                    + env.getProperty("app.delivery.max-retries")
    );
}
```

Nếu `Environment` trả giá trị đúng nhưng bean không được tạo, hãy kiểm tra đăng ký, constructor, chuyển đổi kiểu và validation. Nếu `Environment` trả giá trị khác dự kiến, hãy kiểm tra profile, biến môi trường, đối số và nguồn ưu tiên.

## 21. Các bài tập củng cố

### Bài 1 — constructor duy nhất

```java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int size;

    public CacheProperties(int size) {
        this.size = size;
    }

    public int getSize() { return size; }
}
```

**Hỏi:** Có cần `@ConstructorBinding` trong Spring Boot 3.3 không?

**Đáp án:** Thông thường không. Constructor có tham số duy nhất cho phép Spring Boot suy luận constructor binding, nếu lớp được đăng ký đúng cách và metadata tên tham số có sẵn.

### Bài 2 — thêm constructor tiện lợi

```java
@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties {
    private final int size;

    public CacheProperties(int size) {
        this.size = size;
    }

    public CacheProperties() {
        this(100);
    }

    public int getSize() { return size; }
}
```

**Hỏi:** Nếu muốn Binder dùng constructor nhận `size`, nên làm gì?

**Đáp án:** Đánh dấu constructor `CacheProperties(int size)` bằng `@ConstructorBinding` trong package của Spring Boot 3.3. Constructor rỗng chỉ là lựa chọn tiện lợi trong Java.

### Bài 3 — import annotation

Cho hai lựa chọn:

```java
import org.springframework.boot.context.properties.ConstructorBinding;
```

```java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
```

**Hỏi:** Lựa chọn nào phù hợp với Spring Boot 3.3?

**Đáp án:** Dùng package `.bind.ConstructorBinding` (lựa chọn thứ hai) và đặt annotation trên constructor, không trên lớp.

### Bài 4 — constructor binding và DI

```java
@ConfigurationProperties(prefix = "app.service")
public class ServiceProperties {
    @ConstructorBinding
    public ServiceProperties(ServiceRepository repository, int poolSize) {
        // ...
    }
}
```

**Hỏi:** Vì sao cách viết này đáng nghi ngờ?

**Đáp án:** Binder không tự lấy bean `ServiceRepository` từ Spring context như constructor injection của một `@Service`. `@ConfigurationProperties` nên tập trung vào giá trị cấu hình. Tách repository ra khỏi kiểu cấu hình và tiêm nó vào bean nghiệp vụ.

### Bài 5 — record có constructor phụ

```java
@ConfigurationProperties(prefix = "app.remote")
public record RemoteProperties(String host, int port) {
    public RemoteProperties(String host) {
        this(host, 8080);
    }
}
```

**Hỏi:** Nên làm gì khi muốn rõ constructor được sử dụng cho binding?

**Đáp án:** Đánh dấu constructor canonical nhận `host`, `port` bằng `@ConstructorBinding`, không đánh dấu constructor tiện lợi một tham số.

### Bài 6 — mặc định và validation

Một cấu hình có `max-retries=-5`, nhưng constructor được chọn đặt `@DefaultValue("3")` trên tham số. Binder sẽ tự thay `-5` thành `3` không?

**Đáp án:** Không. `@DefaultValue` phục vụ trường hợp **thiếu giá trị**, không tự sửa giá trị tồn tại nhưng sai quy tắc. Nếu `maxRetries >= 0`, cần validation như `@Min(0)`.

### Bài 7 — thiếu nested group

Lớp cha có tham số `Retry retry`, còn cấu hình không có `app.service.retry.*`. Muốn Binder khởi tạo record nested để các mặc định bên trong có hiệu lực, có thể dùng gì?

**Đáp án:** `@DefaultValue` rỗng trên tham số `Retry retry` của constructor đã chọn, kết hợp các mặc định của record con.

### Bài 8 — thiếu tên tham số

Bạn đã đánh dấu constructor đúng và đăng ký `@ConfigurationPropertiesScan`, nhưng Binder báo không tìm thấy tên tham số. Annotation nào còn thiếu?

**Đáp án:** Có thể **không thiếu annotation nào**. Cần kiểm tra tùy chọn compiler `-parameters` và thông tin metadata tên tham số được giữ trong bytecode.

## 22. Quy ước đề xuất cho dự án Spring Boot 3.3

1. **Ưu tiên một constructor rõ ràng.** Với kiểu cấu hình mới, dùng một constructor bất biến hoặc record đơn giản nếu có thể.
2. **Chỉ dùng `@ConstructorBinding` khi cần lựa chọn tường minh**, thường khi có nhiều constructor.
3. **Đặt annotation trên constructor, import từ `.bind`.** Không sao chép import và vị trí annotation của Spring Boot 2.x.
4. **Đăng ký kiểu cấu hình bằng scan hoặc enable.** Tránh đưa constructor-bound config thành `@Component`.
5. **Giữ tham số constructor tương ứng với schema cấu hình.** Tên tham số có ý nghĩa quan trọng.
6. **Đảm bảo compiler giữ tên tham số (`-parameters`).**
7. **Dùng `@DefaultValue` trên constructor được Binder chọn** khi cần giá trị mặc định.
8. **Dùng validation cho tính hợp lệ**, không mặc định rằng constructor hoặc default đã kiểm tra ràng buộc.
9. **Giữ cấu hình tách khỏi dependency nghiệp vụ.** Không cố dùng constructor binding để tiêm repository/service.
10. **Không tạo constructor phụ không cần thiết**, nhất là khi record hoặc một constructor đầy đủ đã đáp ứng yêu cầu.
11. **Kiểm tra các nguồn cấu hình có hiệu lực** trước khi kết luận lỗi thuộc về constructor.
12. **Xem constructor public phụ như một phần API Java cần bảo trì**, tránh để nó gây nhập nhằng khi refactor.

## 23. Tổng kết

Có thể ghi nhớ quy tắc ra quyết định như sau:

```text
Kiểu dữ liệu có @ConfigurationProperties?
               |
               v
Được đăng ký qua scan / enable?
               |
               v
Có một constructor có tham số đủ điều kiện?
          /                  \
         Có                 Không; nhiều constructor
          |                          |
          v                          v
Binding ngầm định           Chọn đúng constructor
thường là đủ                bằng @ConstructorBinding
          \                          /
           \                        /
            v                      v
               Spring Boot Binder
                        |
                        v
            Đọc và chuyển giá trị từ
                 các nguồn cấu hình
                        |
                        v
             Tạo bean cấu hình có kiểu
                        |
                        v
                Các bean khác dùng DI
```

**Một constructor có tham số:** thường không cần `@ConstructorBinding`.

**Nhiều constructor:** dùng `@ConstructorBinding` trên constructor mà Binder cần gọi.

**Record có constructor phụ:** có thể chọn rõ constructor canonical bằng `@ConstructorBinding`.

**Giá trị thiếu:** cân nhắc `@DefaultValue`; **giá trị sai:** dùng validation; **thiếu tên tham số:** kiểm tra `-parameters`; **bean không được tạo:** kiểm tra `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

Với Spring Boot 3.3, `@ConstructorBinding` là một công cụ **chỉ định constructor được sử dụng để liên kết dữ liệu cấu hình**, không phải một annotation thay thế `@Autowired`. Phân biệt đúng hai cơ chế giúp viết cấu hình bất biến, rõ ràng và ít lỗi khi mở rộng lớp cấu hình.

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration, phần *Constructor Binding*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — *Enabling @ConfigurationProperties-annotated Types*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — `ConstructorBinding`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/ConstructorBinding.html
- Spring Boot 3.3 Reference — `@ConfigurationProperties` Validation and Default Values: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
