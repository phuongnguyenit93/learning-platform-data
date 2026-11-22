# Property không được đọc, binding lỗi hoặc profile sai

Một ứng dụng Spring Boot có thể khởi động thành công nhưng vẫn chạy sai cấu hình: server nghe nhầm port, client dùng timeout mặc định, một bean không được tạo hoặc service production lại dùng implementation dành cho môi trường phát triển. Những lỗi này thường thuộc ba nhóm:

1. **Property không được đọc:** key không có trong `Environment`, file cấu hình không được nạp, tên key sai hoặc một nguồn khác ghi đè giá trị mong muốn.
2. **Binding lỗi:** property có trong `Environment` nhưng không được chuyển vào object Java như mong đợi, do sai prefix, kiểu dữ liệu, cấu trúc nested/list/map, đăng ký bean hoặc validation.
3. **Profile sai:** profile không được kích hoạt, file `application-{profile}` không được nạp, điều kiện `@Profile` không match hoặc nhiều profile cùng active làm chọn nhầm bean.

Ba nhóm này liên quan nhưng không đồng nhất. **Property tồn tại không bảo đảm đã bind vào object; object đã bind không bảo đảm condition tạo bean đúng; profile được khai báo trong file không bảo đảm profile đó thực sự active.**

Bài học này hướng dẫn cách truy tìm nguyên nhân từ nguồn cấu hình đến hành vi runtime, đọc lỗi binding/profile và kiểm chứng kết quả bằng test.

## 1. Luồng cấu hình từ nguồn đến bean

Hãy hình dung luồng xử lý:

```text
application.yml / environment / command line / system properties
                         │
                         ▼
                 Spring Environment
                 PropertySources
                         │
              ┌──────────┴───────────┐
              │                      │
              ▼                      ▼
       @Value placeholder     @ConfigurationProperties
              │                      │
              ▼                      ▼
       Field/constructor       Binder chuyển kiểu
              │                      │
              └──────────┬───────────┘
                         ▼
               Configuration / Bean
                         │
                         ▼
              Conditions và dependency
                         │
                         ▼
                Hành vi ứng dụng
```

Nếu kết quả sai, xác định tầng lỗi:

- Không có key trong `Environment`: điều tra config data, tên key, profile, import và property source.
- Có key nhưng field không đúng: điều tra binding, conversion, prefix và object registration.
- Field đúng nhưng bean không có: điều tra `@Profile`, `@Conditional...`, component scanning và dependency.
- Bean đúng nhưng hành vi sai: điều tra consumer, default logic, cache, runtime state hoặc code nghiệp vụ.

Không nên thay nhiều property cùng lúc trước khi biết lỗi nằm ở tầng nào.

## 2. Phân biệt ba khái niệm

| Khái niệm | Câu hỏi | Công cụ kiểm tra |
|---|---|---|
| Property resolution | Spring đọc key và resolve value nào? | `Environment`, Actuator `env` |
| Property binding | Value được chuyển vào Java object nào và thành kiểu gì? | `@ConfigurationProperties`, `configprops`, binding tests |
| Profile/condition evaluation | Cấu hình hoặc bean nào được đăng ký? | Active profiles, `@Profile`, condition report, `beans` |

Ví dụ:

```yaml
app:
  client:
    timeout: 5s
```

`Environment` có thể resolve `app.client.timeout` thành chuỗi `5s`. Binder có thể chuyển giá trị đó thành `Duration` năm giây. Nhưng nếu class `ClientProperties` chưa được đăng ký, không có object nào tự xuất hiện chỉ vì key tồn tại.

Tương tự, `@Profile("prod")` chỉ áp dụng khi profile `prod` active. Việc file `application-prod.yml` nằm trong project không tự kích hoạt profile đó.

## 3. Property không được đọc: kiểm tra tên key

Một nguyên nhân phổ biến là **tên property không trùng với tên mà code đọc**.

YAML:

```yaml
app:
  client:
    read-timeout: 5s
```

Code:

```java
@Value("${app.client.timeout}")
private Duration timeout;
```

Hai key khác nhau:

- YAML khai báo `app.client.read-timeout`.
- Code yêu cầu `app.client.timeout`.

Spring không tự suy đoán rằng `read-timeout` và `timeout` là cùng một property.

Hãy đối chiếu key theo từng đoạn, kể cả dấu chấm, dấu gạch ngang, số nhiều và prefix. Một lỗi nhỏ cũng đủ khiến property không được tìm thấy.

**Cách xử lý:** tìm nơi khai báo property và nơi sử dụng; đối chiếu canonical key chính xác trước khi kiểm tra các tầng phức tạp hơn.

## 4. Kiểm tra property bằng Environment

`Environment` là API trực tiếp để xem property mà Spring resolve tại runtime.

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationInspector {

    private final Environment environment;

    public ConfigurationInspector(Environment environment) {
        this.environment = environment;
    }

    public void inspect() {
        String timeout =
                environment.getProperty("app.client.timeout");

        boolean present =
                environment.containsProperty("app.client.timeout");

        System.out.println("timeout present: " + present);
        System.out.println("timeout value: " + timeout);
    }
}
```

Các API hữu ích:

| API | Ý nghĩa |
|---|---|
| `getProperty("key")` | Lấy value đã resolve dưới dạng String |
| `getProperty("key", Type.class)` | Lấy và chuyển sang kiểu yêu cầu nếu conversion phù hợp |
| `containsProperty("key")` | Kiểm tra key có được tìm thấy không |
| `getActiveProfiles()` | Danh sách profile active tường minh |
| `getDefaultProfiles()` | Danh sách default profiles |

Ví dụ chuyển kiểu:

```java
Duration timeout = environment.getProperty(
        "app.client.timeout",
        Duration.class
);
```

Dùng cách này trong test hoặc diagnostic code. Không tạo endpoint công khai để in toàn bộ `Environment` vì có thể làm lộ secrets.

## 5. Property có thể đến từ nhiều nguồn

Spring Boot không chỉ đọc `application.yml`. Cấu hình runtime có thể đến từ:

- `application.properties` hoặc `application.yml`.
- File profile-specific như `application-prod.yml`.
- Environment variables của hệ điều hành/container.
- Java system properties (`-Dname=value`).
- Command-line arguments (`--name=value`).
- Config data import hoặc external config location.
- Test properties, dynamic properties và custom property sources.

Ví dụ file:

```yaml
# application.yml
app:
  client:
    timeout: 10s
```

Environment variable:

```text
APP_CLIENT_TIMEOUT=5s
```

Command line:

```bash
java -jar app.jar --app.client.timeout=2s
```

Trong cấu hình Spring Boot thông dụng, command-line property có thể override giá trị từ environment variable và config file. Vì vậy, YAML ghi `10s` không có nghĩa runtime chắc chắn dùng `10s`.

## 6. Property precedence: nguồn nào thắng?

Spring Boot tổng hợp nhiều nguồn theo thứ tự ưu tiên. Các nguồn thường gặp:

| Nguồn | Ví dụ | Vai trò |
|---|---|---|
| Default properties | `SpringApplication.setDefaultProperties(...)` | Giá trị fallback |
| Config data | `application.yml`, profile-specific files, imports | Cấu hình đóng gói/ngoài |
| OS environment | `APP_CLIENT_TIMEOUT` | Cấu hình deployment |
| JVM system property | `-Dapp.client.timeout=3s` | Cấu hình process |
| Command-line property | `--app.client.timeout=2s` | Override khi khởi chạy |
| Test-specific property | `@SpringBootTest(properties=...)` | Override trong test context |

Đây là các nguồn minh họa, không phải danh sách đầy đủ hay thứ tự tuyệt đối cho mọi trường hợp. Spring Boot có quy tắc precedence chi tiết; test properties, dynamic properties, servlet sources và custom sources cũng có thể tham gia.

Khi gặp override bất ngờ:

1. Xác định key canonical.
2. Kiểm tra giá trị hiệu lực trong `Environment`.
3. Xác định property source đang cung cấp giá trị.
4. Tìm nơi deployment/IDE/build tool đặt cùng key.
5. Chỉ sửa nguồn có trách nhiệm cung cấp giá trị đó.

Đừng sửa YAML nếu command line hoặc environment variable vẫn override nó.

## 7. Dùng Actuator env để tìm nguồn property

Nếu ứng dụng có Spring Boot Actuator và endpoint được expose/bảo vệ phù hợp, endpoint `env` giúp quan sát Spring Environment và property sources.

```bash
curl http://localhost:8080/actuator/env/app.client.timeout
```

Đường dẫn thực tế có thể khác nếu management port hoặc base path đã được đổi.

Endpoint có thể cung cấp:

- Property key.
- Các property sources có liên quan.
- Giá trị đã sanitize.
- Origin metadata như file/dòng nếu nguồn hỗ trợ.

Giá trị nhạy cảm có thể được mask. `******` là biểu diễn sanitize, không phải giá trị thật của property.

Nếu endpoint chưa được bật/expose, dùng `Environment` trong test hoặc diagnostic code. Không bật toàn bộ Actuator endpoints công khai chỉ để điều tra một property.

## 8. Property file không được nạp

Spring Boot thường tìm cấu hình ở các vị trí mặc định, gồm config data trên classpath và một số vị trí ngoài filesystem như thư mục làm việc hoặc thư mục `config`.

Các tên file phổ biến:

```text
application.properties
application.yml
application.yaml
application-dev.properties
application-dev.yml
application-prod.yml
```

Nếu file nằm ngoài vị trí được tìm kiếm hoặc không được import, nội dung trong file có thể không tham gia Environment.

Ví dụ file thực tế nằm ở:

```text
./deployment/config/application.yml
```

nhưng ứng dụng không được cấu hình để tìm thư mục đó. Việc file tồn tại trên máy không chứng minh Spring Boot đã đọc nó.

Kiểm tra:

1. File có nằm trong classpath hoặc config location được khai báo không?
2. File có được đóng gói vào artifact không?
3. Working directory có đúng không?
4. Tên file và extension có đúng không?
5. Profile-specific file có profile tương ứng active không?
6. File có lỗi cú pháp hoặc encoding không?
7. Config import có bị thiếu hoặc đánh dấu optional không?

## 9. spring.config.location và spring.config.additional-location

Hai property này dễ bị nhầm:

- `spring.config.location`: chỉ định các vị trí cấu hình và có thể **thay thế** các vị trí tìm kiếm mặc định.
- `spring.config.additional-location`: thêm vị trí tìm kiếm bên cạnh các vị trí mặc định.

Ví dụ:

```bash
java -jar app.jar --spring.config.additional-location=file:./deployment/config/
```

Ứng dụng tiếp tục dùng các vị trí mặc định và bổ sung thư mục `deployment/config`.

Trong khi:

```bash
java -jar app.jar --spring.config.location=file:./deployment/config/
```

có thể thay thế các vị trí mặc định bằng vị trí được chỉ định, khiến file `application.yml` trong classpath không còn được nạp theo cách bạn mong đợi.

Đây là nguyên nhân thường gặp khi ứng dụng “đọc được một số property nhưng mất các property mặc định”.

`spring.config.name`, `spring.config.location` và `spring.config.additional-location` cần được biết từ giai đoạn rất sớm khi Boot chuẩn bị config data. Hãy truyền chúng qua environment, system property hoặc command line; đừng đặt chúng trong chính file cấu hình mà bạn đang trông đợi chúng giúp Spring tìm thấy.

## 10. Dùng spring.config.import

Spring Boot hỗ trợ import thêm config data từ nguồn khác.

```yaml
spring:
  config:
    import: "optional:file:./config/extra.properties"
```

`optional:` cho phép ứng dụng tiếp tục khi nguồn import không tồn tại, theo contract của Config Data. Nếu bỏ `optional:` và location bắt buộc không tồn tại, startup có thể thất bại khi nạp config.

Ví dụ import YAML:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"
```

Khi property không xuất hiện, hãy kiểm tra import path, prefix `file:`, file existence/permissions, optional marker và nguồn khác override property sau đó.

Không nhầm `spring.config.import` với Java `@Import`: một bên nạp **config data**, một bên đăng ký cấu hình/bean vào Spring context.

## 11. Lỗi cú pháp YAML và cấu trúc indentation

YAML phụ thuộc indentation. Ví dụ đúng:

```yaml
app:
  client:
    timeout: 5s
    max-attempts: 3
```

Ví dụ sai cấu trúc:

```yaml
app:
client:
  timeout: 5s
    max-attempts: 3
```

YAML parser có thể báo lỗi ngay khi startup, hoặc một cấu trúc hợp lệ nhưng không tạo ra key bạn mong đợi.

Một số điểm cần chú ý:

- Dùng spaces nhất quán, không trộn tabs.
- Indentation thể hiện hierarchy.
- `:` và `#` có ý nghĩa cú pháp trong một số vị trí.
- Giá trị có ký tự đặc biệt nên được quote khi cần.
- Duplicate keys nên tránh vì có thể gây behavior khó hiểu tùy parser.
- List phải dùng `-` đúng cấp.
- Không đặt key cùng cấp nhầm thành nested property.

Ví dụ list:

```yaml
app:
  allowed-origins:
    - https://dev.example.invalid
    - https://test.example.invalid
```

Nếu cấu trúc bị sai, hãy xem startup error đầy đủ và xác định file/line được nhắc tới, thay vì chỉ đổi tên property.

## 12. application.properties và application.yml

Hai định dạng có thể diễn đạt cùng một cấu hình.

Properties:

```properties
app.client.timeout=5s
app.client.max-attempts=3
```

YAML:

```yaml
app:
  client:
    timeout: 5s
    max-attempts: 3
```

Không nên khai báo cùng key ở cả hai định dạng mà không có lý do. Nếu có, giá trị hiệu lực còn phụ thuộc property source ordering và vị trí config data.

Trong YAML, hierarchy dễ đọc hơn nhưng indentation sai có thể làm thay đổi key. Trong properties, hierarchy được biểu diễn bằng dấu chấm nên dễ đối chiếu với key trong code.

Khi di chuyển giữa hai định dạng, hãy kiểm tra property canonical sau khi parse, không chỉ so sánh hình thức văn bản.

## 13. Relaxed binding và tên environment variable

Spring Boot hỗ trợ relaxed binding cho `@ConfigurationProperties`, cho phép nhiều cách viết tương đương theo quy tắc binding.

Ví dụ canonical property:

```properties
app.client.max-retries=4
```

Tên environment variable theo quy tắc chuyển đổi thông dụng:

1. Thay dấu chấm `.` bằng dấu gạch dưới `_`.
2. Bỏ dấu gạch ngang `-`.
3. Chuyển thành chữ hoa.

Kết quả:

```text
APP_CLIENT_MAXRETRIES=4
```

Đây là điểm dễ nhầm: không nhất thiết là `APP_CLIENT_MAX_RETRIES`.

Ví dụ khác:

| Canonical property | Environment variable |
|---|---|
| `server.port` | `SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `app.client.base-url` | `APP_CLIENT_BASEURL` |
| `app.client.max-retries` | `APP_CLIENT_MAXRETRIES` |
| `integration.payment.api-key` | `INTEGRATION_PAYMENT_APIKEY` |

Với `@Value`, không nên dựa vào toàn bộ khả năng relaxed binding như `@ConfigurationProperties`; placeholder cần trỏ đến property name phù hợp. Khi cần binding nhiều trường, ưu tiên `@ConfigurationProperties`.

## 14. Phân biệt @Value và @ConfigurationProperties

`@Value` phù hợp khi cần inject một vài property đơn lẻ:

```java
@Component
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${app.greeting.prefix:Hello}") String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + " " + name;
    }
}
```

`@ConfigurationProperties` phù hợp với một nhóm cấu hình có prefix và cấu trúc:

```java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration timeout,
        int maxRetries
) {
}
```

| Tiêu chí | `@Value` | `@ConfigurationProperties` |
|---|---|---|
| Một giá trị đơn | Rất phù hợp | Có thể dùng nhưng thường dư |
| Nhóm cấu hình | Nhiều annotation rời rạc | Một object có cấu trúc |
| Relaxed binding | Hạn chế hơn | Được hỗ trợ |
| Nested object/list/map | Không thuận tiện | Hỗ trợ binding |
| Type conversion | Có conversion | Binder hỗ trợ nhiều kiểu |
| Validation theo object | Không tập trung | Có thể dùng `@Validated` |
| Metadata cho IDE | Hạn chế | Có thể sinh configuration metadata |

Ví dụ placeholder với default:

```java
@Value("${app.client.timeout:3s}")
private Duration timeout;
```

Nếu property thiếu, default `3s` được dùng. Không có default và không resolve được placeholder có thể làm bean creation thất bại với lỗi unresolved placeholder.

## 15. @ConfigurationProperties cần được đăng ký

Một class chỉ có `@ConfigurationProperties` không tự động trở thành bean trong mọi trường hợp.

Có thể đăng ký qua scanning:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Hoặc bật rõ class:

```java
@Configuration
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {
}
```

Nếu thiếu đăng ký, có thể gặp lỗi:

```text
No qualifying bean of type 'ClientProperties' available
```

Đây không nhất thiết là lỗi property file. Có thể key đã tồn tại trong Environment nhưng bean đích chưa được đăng ký.

Nếu class properties nằm ngoài package scan, hãy kiểm tra package của main application và phạm vi `@ConfigurationPropertiesScan`.

## 16. Binding vào record hoặc constructor-bound properties

Ví dụ dùng Java record:

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration timeout,
        int maxRetries
) {
}
```

Đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

YAML:

```yaml
app:
  client:
    base-url: https://catalog.example.invalid
    timeout: 5s
    max-retries: 3
```

Spring Boot binder ánh xạ `base-url` vào `baseUrl`, `timeout` thành `Duration` và `max-retries` vào `maxRetries`.

Với constructor binding, constructor parameter cần được bind theo quy tắc tương ứng. Giá trị bắt buộc bị thiếu hoặc sai type có thể gây lỗi tạo properties bean, tùy kiểu, default và cấu hình validation.

Trong các dòng Spring Boot hiện đại, record với canonical constructor thường hỗ trợ constructor binding mà không cần thêm annotation riêng. Với class nhiều constructor hoặc version khác, cần theo đúng contract của version Boot đang dùng.

## 17. Binding vào JavaBean mutable

Một lựa chọn khác là class có no-args constructor và setters:

```java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    private URI baseUrl;
    private Duration timeout;
    private int maxRetries;

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
```

Kiểu binding này cần class được đăng ký và các accessor/setter phù hợp.

Nếu field không có setter hoặc constructor binding không được cấu hình như mong muốn, binder có thể không cập nhật được giá trị theo cách bạn nghĩ.

Khi debug, kiểm tra bean registration, prefix, field names, setter/constructor, conversion và giá trị default.

## 18. Type conversion: String không phải lúc nào cũng là kiểu cuối

Spring Boot Binder có thể chuyển property text thành các kiểu Java phổ biến.

Ví dụ:

```yaml
app:
  client:
    endpoint: https://catalog.example.invalid
    timeout: 5s
    max-response-size: 10MB
    enabled: true
```

Properties:

```java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI endpoint,
        Duration timeout,
        DataSize maxResponseSize,
        boolean enabled
) {
}
```

Các kiểu thường gặp:

| Java type | Ví dụ cấu hình |
|---|---|
| `int`, `long` | `3`, `5000` |
| `boolean` | `true`, `false` |
| `Duration` | `5s`, `500ms`, `2m` |
| `DataSize` | `10MB`, `512KB` |
| `URI`/`URL` | `https://service.example.invalid` |
| `List<String>` | YAML sequence hoặc indexed properties |
| `Map<String, String>` | YAML mapping |
| `enum` | Tên enum phù hợp với quy tắc conversion |

Dùng đơn vị rõ ràng cho `Duration` và `DataSize`, tránh để người đọc phải suy đoán. Default unit có thể phụ thuộc annotation/configuration; explicit unit giúp tránh hiểu nhầm.

## 19. Duration và DataSize sai đơn vị

Ví dụ:

```yaml
app:
  client:
    timeout: 500ms
    max-response-size: 10MB
```

Nên tránh những giá trị mơ hồ:

```yaml
app:
  client:
    timeout: 500
    max-response-size: 10
```

Giá trị không có unit có thể được diễn giải theo default unit của Spring Boot hoặc annotation `@DurationUnit`/`@DataSizeUnit` trên field/constructor parameter. Đừng mặc định `500` là 500 giây hoặc `10` là 10 megabytes.

Ví dụ chỉ rõ unit mặc định cho Duration:

```java
@ConfigurationProperties(prefix = "app.client")
public class ClientProperties {

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration timeout = Duration.ofSeconds(3);

    // Getter/setter.
}
```

Nếu cần chính xác, hãy dùng suffix trong config và kiểm tra giá trị typed trong test.

## 20. Lỗi chuyển đổi kiểu dữ liệu

Ví dụ property:

```properties
app.client.max-retries=three
```

nhưng Java field là:

```java
private int maxRetries;
```

Binder không thể chuyển chuỗi `three` thành số nguyên. Startup có thể thất bại với lỗi binding/conversion, thường được bọc trong exception cao hơn như `ConfigurationPropertiesBindException` hoặc `BeanCreationException`.

Nguyên nhân tương tự:

- `timeout=soon` nhưng field là `Duration`.
- URL không hợp lệ với kiểu `URI`.
- Enum value không phù hợp.
- Boolean có chuỗi không được converter chấp nhận.
- List/map có cấu trúc không đúng.
- Property có placeholder tham chiếu đến key không tồn tại.

Hãy đọc **root cause** trong exception chain, không dừng ở dòng đầu `Failed to bind properties`.

## 21. Validation: value bind được nhưng vẫn không hợp lệ

Giá trị có thể chuyển kiểu thành công nhưng sai yêu cầu nghiệp vụ.

```yaml
app:
  client:
    timeout: 0s
    max-retries: -2
```

Cả hai value có thể được parse thành `Duration` và `int`, nhưng hệ thống có thể yêu cầu timeout dương và retry không âm.

Có thể thêm validation:

```java
@ConfigurationProperties(prefix = "app.client")
@Validated
public record ClientProperties(
        @NotNull URI baseUrl,
        @NotNull @Positive Duration timeout,
        @Min(0) int maxRetries
) {
}
```

Ví dụ cần các import Jakarta Bean Validation và validation provider/dependency tương ứng với Spring Boot version. Constraint `@Positive` trên `Duration` phụ thuộc support của provider; nếu provider không hỗ trợ kiểu đó, hãy dùng custom validator hoặc kiểm tra trong validation method phù hợp.

Với nested properties, dùng `@Valid` khi muốn cascade validation.

Binding và validation là hai bước khác nhau:

- Binding kiểm tra dữ liệu có thể được chuyển vào object hay không.
- Validation kiểm tra object có thỏa constraints hay không.

## 22. Property bị viết sai nhưng không báo lỗi

Một trường hợp khó tìm: key trong file bị typo, nhưng ứng dụng vẫn chạy và dùng default.

```yaml
app:
  client:
    max-retyrs: 5
```

Trong khi Java properties cần `maxRetries`.

Tùy cấu hình binder, các unknown fields có thể bị bỏ qua theo mặc định. Do đó, không phải mọi key sai đều làm startup thất bại.

Có thể yêu cầu strict handling cho unknown fields:

```java
@ConfigurationProperties(
    prefix = "app.client",
    ignoreUnknownFields = false
)
public class ClientProperties {
    // Fields và accessors.
}
```

Điều này giúp phát hiện property không được bind trong phạm vi object tương ứng. Tuy nhiên, trước khi bật, hãy bảo đảm config files không cố ý chứa key mở rộng mà class hiện tại không quản lý.

## 23. Nested properties

YAML:

```yaml
app:
  client:
    connection:
      connect-timeout: 2s
      read-timeout: 5s
```

Java:

```java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Connection connection
) {
    public record Connection(
            Duration connectTimeout,
            Duration readTimeout
    ) {
    }
}
```

Binder ánh xạ `connection.connect-timeout` vào `connection.connectTimeout`.

Nếu nested object bị null hoặc thiếu field, kiểm tra YAML indentation, prefix root, tên nested property, constructor binding, default, `@Valid` và registration.

Không nhầm việc nested object chưa được tạo với việc file YAML hoàn toàn không được đọc.

## 24. List binding và override

YAML:

```yaml
app:
  allowed-origins:
    - https://dev.example.invalid
    - https://test.example.invalid
```

Properties dạng indexed:

```properties
app.allowed-origins[0]=https://dev.example.invalid
app.allowed-origins[1]=https://test.example.invalid
```

Java:

```java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<String> allowedOrigins
) {
}
```

Khi cùng một list được cung cấp từ nhiều property sources, **list từ nguồn có độ ưu tiên cao hơn thường thay thế toàn bộ list**, thay vì tự nối từng phần tử từ nguồn thấp hơn.

Ví dụ file mặc định có hai origins, còn profile production chỉ khai báo một origin; list hiệu lực có thể chỉ chứa origin từ nguồn production.

Nếu muốn thêm phần tử, hãy cấu hình đầy đủ danh sách hiệu lực hoặc thiết kế cơ chế merge riêng. Đừng mặc định list được merge giống map.

## 25. Map binding và key đặc biệt

YAML:

```yaml
app:
  client:
    headers:
      X-Region: ap-southeast-1
      X-Mode: safe
```

Java:

```java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Map<String, String> headers
) {
}
```

Nếu map key chứa ký tự đặc biệt như dấu `/`, dấu chấm hoặc ký tự cần giữ nguyên, có thể cần bracket notation khi khai báo property key.

Ví dụ trong properties:

```properties
app.client.labels.[/v1/orders]=orders-api
```

Với YAML, có thể quote key bracket:

```yaml
app:
  client:
    labels:
      "[/v1/orders]": orders-api
```

Nếu key bị mất hoặc biến đổi, kiểm tra cách parser/binder chuẩn hóa key và dùng bracket notation để bảo toàn ký tự.

## 26. Placeholder ${...} tham chiếu property khác

Một property có thể tham chiếu property khác:

```properties
app.client.host=localhost
app.client.base-url=https://${app.client.host}:8443
```

Hoặc YAML:

```yaml
app:
  client:
    host: localhost
    base-url: "https://${app.client.host}:8443"
```

Nếu key được tham chiếu không tồn tại, placeholder có thể không resolve và làm bean/configuration thất bại, trừ khi có default phù hợp:

```properties
app.client.timeout=${APP_TIMEOUT:5s}
```

Ở ví dụ cuối, `5s` là fallback nếu property `APP_TIMEOUT` không được tìm thấy. Hãy phân biệt placeholder default với giá trị default trong Java constructor/field.

Khi property có trong file nhưng bean lỗi, hãy kiểm tra placeholder chain. Key gốc có thể tồn tại nhưng một key được tham chiếu từ nó lại thiếu.

## 27. Profile là gì trong Spring?

Profile là tên logic cho một tập cấu hình hoặc bean conditions. Các tên phổ biến:

```text
dev
test
staging
prod
local
cloud
```

Profile có thể ảnh hưởng đến:

- File `application-{profile}.yml`.
- Bean có `@Profile`.
- Config document có `spring.config.activate.on-profile`.
- Một số auto-configuration/condition của ứng dụng.

Tên profile không tự có ý nghĩa đặc biệt ngoài convention và configuration bạn định nghĩa. Spring không mặc định coi `dev`, `test` và `prod` loại trừ lẫn nhau; nhiều profile có thể active cùng lúc.

## 28. Kích hoạt profile đúng cách

Có thể kích hoạt bằng command line:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Environment variable:

```text
SPRING_PROFILES_ACTIVE=prod
```

Hoặc trong cấu hình cơ sở `application.yml`:

```yaml
spring:
  profiles:
    active: prod
```

Trong IDE, `--spring.profiles.active=dev` là application argument; `SPRING_PROFILES_ACTIVE=dev` là environment variable.

Đừng nhầm:

- `--spring.profiles.active=prod`: application argument cho Spring Boot.
- `-Dspring.profiles.active=prod`: JVM system property nếu được truyền vào JVM ứng dụng.
- `-Pprod`: Maven build profile, không tự động là Spring profile.
- Gradle project property `-P...`: build configuration, không tự động là runtime profile.

## 29. application-prod.yml không tự active prod

Giả sử project có:

```text
application.yml
application-dev.yml
application-prod.yml
```

Spring Boot chỉ nạp profile-specific configuration khi profile tương ứng được kích hoạt.

Nếu chạy:

```bash
java -jar app.jar
```

thì không thể mặc định file `application-prod.yml` được nạp chỉ vì nó tồn tại.

Cần:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Hoặc cấu hình active profile qua nguồn hợp lệ khác.

Nếu app đang dùng `dev` nhưng bạn mong `prod`, hãy kiểm tra startup log và `Environment.getActiveProfiles()` trước khi sửa nội dung `application-prod.yml`.

## 30. Không đặt spring.profiles.active trong profile-specific file

Một lỗi thường gặp là viết:

```yaml
# application-prod.yml
spring:
  profiles:
    active: prod
```

`spring.profiles.active` không được dùng để kích hoạt profile từ tài liệu cấu hình đã được profile-specific hoặc từ tài liệu được điều kiện hóa bằng `spring.config.activate.on-profile`.

Hãy khai báo active profile ở nguồn cấu hình khởi động hợp lệ, ví dụ command line, environment variable, JVM system property hoặc tài liệu cấu hình cơ sở không profile-specific.

File `application-prod.yml` nên chứa cấu hình dành cho profile prod, không tự quyết định bật chính profile đó.

## 31. Profile default và active profiles

Nếu không có active profile tường minh, Spring sử dụng **default profiles**. Tên default mặc định thường là `default`.

Có thể thay default profile:

```properties
spring.profiles.default=local
```

Khi không có active profile tường minh, `local` có thể là default profile hiệu lực.

Phân biệt:

```java
@Profile("default")
```

với:

```java
@Profile("!prod")
```

`default` kiểm tra tên profile default; `!prod` là biểu thức phủ định, đúng khi `prod` không active.

Khi active profile là `dev`, `!prod` vẫn match, còn `default` thông thường không match vì default profiles chỉ được dùng khi không có active profile tường minh.

Nếu một bean chỉ dành cho local/test, không nên dùng `!prod` mà không xem xét những profile mới có thể xuất hiện trong tương lai.

## 32. Nhiều profile có thể active cùng lúc

Ví dụ:

```bash
java -jar app.jar --spring.profiles.active=prod,cloud,metrics
```

Tập profile gồm ba tên. Các condition được đánh giá trên tập này.

```java
@Profile("prod & cloud")
```

match vì cả `prod` và `cloud` đều active.

Trong khi:

```java
@Profile("dev | test")
```

không match nếu `dev` và `test` đều vắng mặt.

Một mảng profile:

```java
@Profile({"dev", "test"})
```

là OR giữa các expression, không phải AND.

Nếu cần cả hai:

```java
@Profile("dev & cloud")
```

Nếu trộn AND và OR, nhóm bằng dấu ngoặc:

```java
@Profile("(dev | staging) & cloud")
```

## 33. Profile group

Profile group cho phép kích hoạt một nhóm profile bằng một tên đại diện.

```yaml
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - observability
```

Khi chạy:

```bash
java -jar app.jar --spring.profiles.active=production
```

Spring Boot kích hoạt group profile cùng các profile thành viên theo cấu hình.

Điều này hữu ích khi production cần một tập tính năng nhất quán. Hãy kiểm tra `Environment.getActiveProfiles()` để xác nhận danh sách thực tế, đặc biệt khi có nhiều profile hoặc group kết hợp.

Không khai báo profile group trong tài liệu profile-specific hoặc tài liệu được kích hoạt bằng `spring.config.activate.on-profile`; các thuộc tính điều khiển profile cần nằm ở tài liệu cấu hình hợp lệ theo quy tắc Boot.

## 34. Profile-specific config document

Ngoài file `application-prod.yml`, Spring Boot hỗ trợ nhiều tài liệu YAML trong cùng file, phân tách bằng `---`.

```yaml
app:
  banner: default

---
spring:
  config:
    activate:
      on-profile: prod

app:
  banner: production
```

Tài liệu thứ hai chỉ được kích hoạt khi profile `prod` active.

Có thể dùng expression:

```yaml
---
spring:
  config:
    activate:
      on-profile: "(staging | prod) & cloud"

app:
  client:
    remote-mode: true
```

Đừng nhầm `spring.config.activate.on-profile` với `spring.profiles.active`:

- `spring.profiles.active` chọn tập profile.
- `spring.config.activate.on-profile` điều kiện hóa việc nạp một config document.

## 35. Profile sai do spelling hoặc source override

Ví dụ deployment đặt:

```text
SPRING_PROFILE=prod
```

nhưng Spring Boot property là `spring.profiles.active`.

Tên environment variable chuẩn theo quy tắc chuyển đổi là:

```text
SPRING_PROFILES_ACTIVE=prod
```

Một biến gần giống tên không có nghĩa Spring sẽ tự hiểu.

Ngoài spelling, profile có thể bị override bởi command-line arguments, JVM system properties, environment variables khác, test configuration hoặc custom property source.

Kiểm tra profile hiệu lực bằng:

```java
Environment environment = ...;

System.out.println(
    Arrays.toString(environment.getActiveProfiles())
);
```

Trong code thật, inject `Environment` thay vì tự lấy một biến toàn cục.

## 36. Profile condition và bean không được tạo

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Profile("prod")
    PaymentGateway remoteGateway() {
        return new RemotePaymentGateway();
    }

    @Bean
    @Profile("!prod")
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
```

Nếu không có `prod`, bean local được đăng ký. Nếu có `prod`, bean remote được đăng ký.

Nhưng nếu remote còn có:

```java
@Bean
@Profile("prod")
@ConditionalOnProperty(
    prefix = "payment.remote",
    name = "enabled",
    havingValue = "true"
)
PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}
```

thì cả hai điều kiện phải thỏa.

Trong prod nhưng `payment.remote.enabled=false`, local đã bị loại và remote cũng bị loại. Kết quả là không có `PaymentGateway`.

Khi gặp `NoSuchBeanDefinitionException`, hãy kiểm tra toàn bộ condition chain thay vì chỉ nhìn profile.

## 37. Đọc condition evaluation report

Khi ứng dụng startup thành công và Actuator được bật/expose an toàn, endpoint `conditions` có thể giúp quan sát conditional configuration:

```bash
curl http://localhost:8080/actuator/conditions
```

Khi startup thất bại trước khi management endpoint sẵn sàng, dùng debug flag:

```bash
java -jar app.jar --debug
```

Hoặc với Gradle:

```bash
./gradlew bootRun --args="--debug"
```

Hoặc Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--debug"
```

`--debug` giúp Spring Boot in condition evaluation report cho auto-configuration. Nó không tự bật TRACE cho mọi logger và cũng không thay thế việc đọc exception gốc.

Một negative match không nhất thiết là lỗi: Boot có nhiều auto-configurations dành cho stack mà ứng dụng không dùng.

## 38. Property có trong env nhưng configprops không có

`env` và `configprops` trả lời hai câu hỏi khác nhau.

- `env`: key có trong Environment và value/source nào hiệu lực?
- `configprops`: object `@ConfigurationProperties` nào đã được bind?

Ví dụ key có trong YAML:

```yaml
app:
  client:
    timeout: 5s
```

Nhưng không có properties bean vì class chưa được đăng ký. Khi đó `env` có thể thấy key, còn `configprops` không có object tương ứng.

Kiểm tra:

1. Class có `@ConfigurationProperties(prefix="app.client")` không?
2. Đã có `@ConfigurationPropertiesScan` chưa?
3. Hoặc đã dùng `@EnableConfigurationProperties(ClientProperties.class)` chưa?
4. Class có nằm trong phạm vi scan không?
5. Profile/condition có loại bean không?

Không kết luận rằng YAML không được đọc chỉ vì `configprops` thiếu một class.

## 39. configprops có object nhưng value sai

Nếu properties bean đã có mặt nhưng field sai, hãy so sánh:

1. `env`: effective value của key.
2. `configprops`: typed value đã bind.
3. Class Java: field name, prefix, constructor/setter, defaults.
4. Validation: constraint có được áp dụng không?

Ví dụ `env` cho thấy `app.client.timeout=5s` nhưng object vẫn có `Duration.ZERO`. Có thể object đang được tạo theo cách khác, bean không dùng prefix bạn nghĩ, field không tham gia binding, constructor/default được dùng ngoài dự kiến, hoặc bạn đang quan sát nhầm instance/context.

Hãy xác định đúng bean được inject vào consumer; không chỉ đọc một object có cùng tên class.

## 40. Lỗi placeholder unresolved

Ví dụ:

```properties
app.client.base-url=${APP_CLIENT_BASE_URL}
```

Nếu `APP_CLIENT_BASE_URL` không tồn tại và không có default, placeholder có thể không resolve, làm bean/configuration thất bại.

Thêm default nếu đó là chính sách hợp lệ:

```properties
app.client.base-url=${APP_CLIENT_BASE_URL:https://localhost:8443}
```

Nhưng đừng đặt default giả cho endpoint production nếu việc thiếu URL phải làm ứng dụng fail-fast. Default chỉ nên dùng khi giá trị fallback thực sự an toàn và có ý nghĩa.

Khi thấy `Could not resolve placeholder`, tìm key trong dấu `${...}` của exception; đó thường là property đang thiếu, không nhất thiết là property bên ngoài mà bạn nhìn thấy trong file.

## 41. Các exception thường gặp và ý nghĩa

| Exception/message | Ý nghĩa có thể | Điều tra tiếp |
|---|---|---|
| `Could not resolve placeholder ...` | Placeholder không tìm thấy key và không có fallback | Property source, spelling, import |
| `ConfigurationPropertiesBindException` | Không bind được properties bean | Prefix, field, constructor, type |
| `BindException` | Binder gặp lỗi trong quá trình bind | Root cause, property path |
| `ConversionFailedException` | Không chuyển được kiểu | Format, converter, target type |
| `BeanCreationException` | Bean creation thất bại; có thể bọc lỗi binding | Xem nested cause |
| `NoSuchBeanDefinitionException` | Không tìm được bean dependency | Component scan, profile, conditions |
| `NoUniqueBeanDefinitionException` | Có nhiều candidates cùng type | `@Primary`, `@Qualifier`, conditions |
| `Failed to bind properties under ...` | Một prefix/field không bind được | Xem property name và exception chain |
| YAML parse error | Cấu trúc file không hợp lệ | File/line/indentation |
| Profile-specific file không có hiệu lực | Profile không active hoặc file không được tìm thấy | Active profiles, config locations |

Đừng chỉ copy exception ngoài cùng. Dùng stack trace để tìm `Caused by` sâu nhất có ý nghĩa; thường đó là nguyên nhân cụ thể như parse, conversion hoặc missing dependency.

## 42. Phân biệt startup failure và runtime wrong value

Hai tình huống cần cách tiếp cận khác nhau.

**Startup failure:**

- YAML parse error.
- Placeholder bắt buộc không resolve.
- Type conversion thất bại.
- Validation fail.
- Required bean không tồn tại.
- Hai bean cùng type gây ambiguous injection.

Dùng startup logs, stack trace, `--debug` và test context.

**Ứng dụng chạy nhưng value sai:**

- Một property source override.
- Profile khác dự kiến.
- Java default che mất property không được bind.
- List từ profile-specific source thay thế toàn bộ list.
- Bean được tạo nhưng consumer dùng một bean khác.
- Cấu hình được đọc ở thời điểm startup rồi lưu vào state.

Dùng `Environment`, `configprops`, `beans`, instance identity và integration tests.

## 43. Quy trình chẩn đoán: property không được đọc

Tình huống: service luôn dùng timeout mặc định dù file YAML có giá trị khác.

1. **Xác định key code đang đọc.** Ví dụ `app.client.timeout`.
2. **Tìm key trong file cấu hình.** Kiểm tra spelling, hierarchy và indentation.
3. **Xác nhận file có được nạp.** Kiểm tra tên, location, import, profile.
4. **Đọc effective value từ Environment.** Nếu null, key chưa resolve; nếu khác mong đợi, có override.
5. **Tìm property source đang thắng.** Environment variable, command line, system property, test override.
6. **Kiểm tra object binding.** Nếu code dùng `@ConfigurationProperties`, xem bean và typed field.
7. **Kiểm tra consumer.** Đảm bảo service dùng đúng properties bean/field.
8. **Viết test tái hiện.** Đặt profile và property rõ ràng, assert giá trị cuối.

Không thay cả file config và code cùng lúc nếu chưa xác định tầng lỗi.

## 44. Quy trình chẩn đoán: binding lỗi

Tình huống: startup báo `Failed to bind properties under 'app.client'`.

1. Tìm prefix chính xác trong exception.
2. Xác định property path gây lỗi.
3. Kiểm tra value thô từ Environment nếu có.
4. Kiểm tra Java target type.
5. Kiểm tra định dạng `Duration`, `DataSize`, enum, URI, number, boolean.
6. Kiểm tra nested structure/list/map và YAML indentation.
7. Kiểm tra `@ConfigurationProperties` registration.
8. Kiểm tra constructor/setter/record parameters.
9. Kiểm tra Bean Validation và nested `@Valid`.
10. Nếu value bind được nhưng sai nghiệp vụ, bổ sung validation và test.

Nếu exception có `origin`, dùng file/line đó để tìm nguồn cấu hình cụ thể.

## 45. Quy trình chẩn đoán: profile sai

Tình huống: ứng dụng đang dùng bean dev dù deploy production.

1. Đọc active profiles từ startup log hoặc `Environment`.
2. Kiểm tra deployment có truyền `SPRING_PROFILES_ACTIVE` hay `--spring.profiles.active` đúng không.
3. Kiểm tra command-line/JVM/environment sources có override lẫn nhau không.
4. Kiểm tra file `application-prod.yml` có đúng tên và location không.
5. Kiểm tra `spring.profiles.active` có bị đặt nhầm trong profile-specific document không.
6. Kiểm tra nhiều profile cùng active.
7. Đọc `@Profile` expression trên class và `@Bean` method.
8. Kiểm tra property conditions kết hợp với profile.
9. Dùng `beans`/context test để xác nhận implementation thực tế.
10. Viết test cho đúng tập profile của deployment.

Đừng chỉ nhìn biến môi trường trong pipeline; xác nhận giá trị **đã đi vào Spring Environment của instance**.

## 46. Test property resolution và binding

Một test hẹp dùng `ApplicationContextRunner`:

```java
class ClientPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(ClientPropertiesConfiguration.class);

    @Test
    void bindsTimeoutAndRetryCount() {
        runner
            .withPropertyValues(
                "app.client.timeout=5s",
                "app.client.max-retries=3"
            )
            .run(context -> {
                assertThat(context)
                        .hasSingleBean(ClientProperties.class);

                ClientProperties properties =
                        context.getBean(ClientProperties.class);

                assertThat(properties.timeout())
                        .isEqualTo(Duration.ofSeconds(5));

                assertThat(properties.maxRetries())
                        .isEqualTo(3);
            });
    }
}
```

Test này giả định `ClientPropertiesConfiguration` đăng ký `ClientProperties` bằng `@EnableConfigurationProperties`.

Nó kiểm tra binder và typed values mà không cần khởi động toàn bộ web application. Thêm test cho property missing, malformed value và override để bảo vệ các trường hợp dễ lỗi.

## 47. Test profile và implementation selection

Ví dụ:

```java
@SpringBootTest(
    classes = NotificationConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "integration.notifications.enabled=true"
)
@ActiveProfiles("prod")
class ProductionNotificationSelectionTest {

    @Autowired
    ApplicationContext context;

    @Test
    void selectsRemoteImplementation() {
        NotificationChannel channel =
                context.getBean(NotificationChannel.class);

        assertThat(channel)
                .isInstanceOf(RemoteNotificationChannel.class);

        assertThat(context.getBeansOfType(NotificationChannel.class))
                .hasSize(1);
    }
}
```

Test phải kiểm tra cả type và số lượng bean nếu contract yêu cầu đúng một implementation.

Các test khác nên bao gồm dev profile/property missing, prod true, prod false, prod missing, nhiều profile cùng active, profile-specific YAML override và bean missing khiến consumer fail-fast nếu đó là chính sách.

Không mock implementation đang cần kiểm tra selection, vì mock có thể che condition thực tế.

## 48. Actuator endpoints hỗ trợ điều tra

Nếu Actuator được cài đặt và expose an toàn, các endpoint sau hữu ích:

| Endpoint | Câu hỏi |
|---|---|
| `/actuator/env` | Property key/source/value hiệu lực là gì? |
| `/actuator/configprops` | `@ConfigurationProperties` bean đã bind thế nào? |
| `/actuator/conditions` | Conditional configuration match hay không? |
| `/actuator/beans` | Bean nào thực sự có trong context? |

Một workflow:

```text
env
 │
 ├── Key có tồn tại không?
 ├── Source nào thắng?
 └── Profile nào active?
       │
       ▼
configprops
 │
 └── Typed bean đã bind đúng chưa?
       │
       ▼
conditions
 │
 └── Điều kiện tạo bean có match không?
       │
       ▼
beans
   └── Implementation nào thực sự được đăng ký?
```

Nếu ứng dụng chưa khởi động được, các HTTP endpoints này có thể chưa sẵn sàng. Khi đó hãy dùng logs, `--debug` và tests.

Các endpoint có thể tiết lộ tên property, class, package, cấu trúc bean và thông tin nội bộ. Giữ values nhạy cảm được mask, giới hạn network và authorization; không expose rộng chỉ để debug.

## 49. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Environment.getProperty(...)` trả null | Key sai hoặc config file chưa nạp | Kiểm tra key, location, import |
| File YAML có giá trị nhưng runtime khác | Property source ưu tiên cao hơn override | Xác định source hiệu lực |
| `@Value` dùng default | Placeholder key không tồn tại hoặc sai | Kiểm tra spelling và source |
| `@ConfigurationProperties` bean không tồn tại | Chưa scan/enable properties class | Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Binder báo lỗi Duration | Value không có format hợp lệ | Dùng `5s`, `500ms` và kiểm tra type |
| Property typo nhưng app vẫn chạy | Unknown fields bị bỏ qua | Cân nhắc `ignoreUnknownFields=false` |
| Nested field null | YAML hierarchy hoặc constructor sai | Kiểm tra indentation/prefix/binding model |
| List mất phần tử mặc định | List ở nguồn ưu tiên cao thay thế list thấp | Khai báo đầy đủ list hiệu lực |
| Map key bị biến đổi | Ký tự đặc biệt không được escape | Dùng bracket notation |
| `application-prod.yml` không có tác dụng | Profile prod chưa active hoặc file không được tìm thấy | Xác nhận active profiles và config location |
| Profile prod không active | Env var/argument sai tên hoặc bị override | Kiểm tra `SPRING_PROFILES_ACTIVE` và Environment |
| `@Profile` không match | Expression sai hoặc thiếu profile | Kiểm tra toàn bộ active set |
| Bean thiếu dù profile đúng | Property condition khác không match | Kiểm tra conditions và property |
| Hai bean cùng type | Profile expressions chồng lấp | Dùng điều kiện loại trừ nhau hoặc `@Qualifier` |
| Startup fail vì placeholder | Placeholder bắt buộc không resolve | Cung cấp key hoặc default hợp lệ |
| Test pass nhưng deployment fail | Test context khác config/runtime thực tế | Thêm integration test và so sánh property sources |
| Actuator trả 404 | Endpoint chưa enabled/exposed hoặc path khác | Kiểm tra exposure/base path |
| Actuator trả 401/403 | Security yêu cầu authentication/role | Dùng quyền quản trị phù hợp, không tắt bảo mật |

## 50. Checklist điều tra theo thứ tự

Khi gặp lỗi property/profile, có thể đi qua các câu hỏi sau:

```text
[ ] Key code đang đọc là gì?
[ ] Key có tồn tại trong Environment không?
[ ] File/source nào cung cấp giá trị hiệu lực?
[ ] Có command line, system property hoặc env var override không?
[ ] Config file có được nạp từ đúng location/import không?
[ ] YAML hierarchy và spelling có đúng không?
[ ] Profile nào đang active/default?
[ ] File profile-specific có đúng tên không?
[ ] @ConfigurationProperties bean đã được đăng ký chưa?
[ ] Prefix, constructor, setter và field names có khớp không?
[ ] Value có chuyển sang Java type được không?
[ ] Validation có pass không?
[ ] @Profile và @Conditional... có match không?
[ ] Consumer có nhận đúng implementation không?
[ ] Test có mô phỏng đúng runtime configuration không?
```

Không nhất thiết chạy mọi bước cho một lỗi đơn giản. Dùng checklist như bản đồ để tránh bỏ sót tầng cấu hình liên quan.

## 51. Bài tập thực hành

### Bài tập A — Property không được đọc

Tạo property `app.client.timeout=5s`, nhưng code đọc `app.client.read-timeout`. Dùng `Environment.containsProperty()` và `getProperty()` để xác định key nào tồn tại. Sửa một phía và kiểm tra lại.

### Bài tập B — Property bị override

Đặt timeout `10s` trong `application.yml`, sau đó chạy:

```bash
java -jar app.jar --app.client.timeout=2s
```

Xác nhận giá trị hiệu lực và giải thích vì sao sửa YAML không thay đổi kết quả khi command line vẫn override.

### Bài tập C — Environment variable naming

Tạo property `app.client.max-retries`. Đặt environment variable theo quy tắc relaxed binding và kiểm tra binder nhận đúng. Thử một tên có thêm dấu gạch dưới giữa `MAX` và `RETRIES` rồi quan sát khác biệt.

### Bài tập D — Binding Duration

Bind `app.client.timeout=500ms` vào `Duration`. Thử `5s`, `500ms`, `soon` và giá trị thiếu. Ghi lại trường hợp bind thành công và lỗi.

### Bài tập E — Properties bean chưa được đăng ký

Tạo class `@ConfigurationProperties(prefix="app.client")` nhưng chưa scan/enable. Đặt property trong YAML và quan sát vì sao key có thể tồn tại trong Environment nhưng không có bean. Sau đó đăng ký class đúng cách.

### Bài tập F — Unknown property

Cố tình viết `max-retyrs` thay cho `max-retries`. Quan sát behavior mặc định, sau đó thử strict binding với `ignoreUnknownFields=false`. Ghi lại trade-off.

### Bài tập G — Profile không active

Tạo `application-dev.yml` và `application-prod.yml` có một property khác nhau. Chạy app không truyền profile, sau đó với `--spring.profiles.active=prod`. So sánh effective value.

### Bài tập H — Nhiều profile cùng active

Tạo bean `@Profile("dev | test")` và bean `@Profile("prod & cloud")`. Chạy với `dev,prod,cloud`. Xác định các condition match; giải thích vì sao tên profile không tự loại trừ nhau.

### Bài tập I — Profile đặt sai vị trí

Đặt `spring.profiles.active=prod` trong `application-prod.yml`. Quan sát lỗi/behavior theo version Boot. Chuyển active profile sang environment hoặc command line và giải thích khác biệt.

### Bài tập J — Placeholder chain

Đặt `app.client.url=${CLIENT_URL}` nhưng không cung cấp `CLIENT_URL`. Quan sát startup error. Thử default hợp lệ và thảo luận khi nào fail-fast tốt hơn fallback.

### Bài tập K — List override

Khai báo hai origins trong `application.yml`, một origin trong `application-prod.yml`. Kích hoạt prod và quan sát list hiệu lực. Giải thích vì sao không nên kỳ vọng list tự nối.

### Bài tập L — End-to-end diagnosis

Tạo tình huống production dùng local implementation do profile sai hoặc property flag thiếu. Điều tra từ Environment, configprops, conditions đến beans. Viết báo cáo gồm symptom, effective profile, property source, binding result, bean selection, root cause và fix.

## 52. Ghi nhớ

1. **Property resolution, binding và condition evaluation là ba bước khác nhau.**
2. `Environment` cho biết property hiệu lực; `@ConfigurationProperties` binder chuyển property thành typed object.
3. File YAML có chứa key không chứng minh file đã được nạp hoặc giá trị không bị override.
4. Property sources có precedence; command line, system properties và environment variables có thể làm giá trị runtime khác file cấu hình.
5. `spring.config.location` có thể thay thế vị trí mặc định; `spring.config.additional-location` bổ sung vị trí.
6. `spring.config.import` nạp thêm config data; `optional:` quyết định hành vi khi nguồn không tồn tại.
7. YAML indentation, spelling, nested structure, list/map và quoting đều có thể làm key được parse khác dự kiến.
8. Environment variable cho canonical property `app.client.max-retries` thường là `APP_CLIENT_MAXRETRIES`.
9. `@Value` phù hợp cho vài property đơn; `@ConfigurationProperties` phù hợp với nhóm cấu hình có cấu trúc và relaxed binding.
10. `@ConfigurationProperties` class phải được đăng ký qua scanning, enable hoặc cơ chế bean phù hợp.
11. Binding failure khác validation failure: chuyển kiểu thành công không bảo đảm giá trị hợp lệ nghiệp vụ.
12. Unknown fields có thể bị bỏ qua theo mặc định; strict handling giúp phát hiện typo khi phù hợp.
13. `application-prod.yml` không tự kích hoạt profile `prod`.
14. `spring.profiles.active` phải được khai báo ở nguồn cấu hình hợp lệ, không đặt trong profile-specific document.
15. Nhiều profile có thể active đồng thời; `@Profile` expression cần được đánh giá trên toàn bộ tập profile.
16. `@Profile({"dev","test"})` là OR; `@Profile("dev & test")` là AND.
17. `spring.config.activate.on-profile` điều kiện hóa config document; nó không thay thế `spring.profiles.active`.
18. Khi bean thiếu, kiểm tra profile và property conditions cùng component scanning, không chỉ nhìn một annotation.
19. Khi startup thất bại, đọc nested cause và dùng `--debug`; Actuator HTTP endpoint có thể chưa sẵn sàng.
20. Dùng `env`, `configprops`, `conditions` và `beans` để ghép bằng chứng, nhưng bảo vệ endpoint và values nhạy cảm.
21. Test cần xác nhận effective property, typed binding và implementation được chọn, không chỉ xác nhận file có chứa key.
22. Với lỗi cấu hình, tìm nguồn hiệu lực và tầng gây lỗi trước khi thay đổi; tránh sửa nhiều nơi cùng lúc.

**Tư duy cốt lõi:** khi property không được đọc, hãy tìm nó trong **Environment**; khi binding lỗi, kiểm tra **prefix, Java type và properties bean**; khi profile sai, xác nhận **tập profile active và các condition**. Lần theo luồng từ nguồn cấu hình đến bean được inject sẽ giúp tìm đúng nguyên nhân thay vì thử sửa YAML hoặc annotation một cách ngẫu nhiên.
