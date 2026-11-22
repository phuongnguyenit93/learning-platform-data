# @ConfigurationProperties và kiểm tra dữ liệu cấu hình đầu vào

> **Chương:** Cấu hình kết nối  
> **Module:** `SPRING_BOOT_INTEGRATION` — tổ chức tích hợp hệ thống trong Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter của Spring Integration. Trọng tâm là cấu hình, hợp đồng dữ liệu, giao dịch, xử lý lỗi, chống trùng, kiểm thử và quan sát những luồng tích hợp thực tế.
>
> **Phạm vi ví dụ:** Java 17+, phong cách Spring Boot 3 với `jakarta.validation.*` và immutable `record`. Nếu dùng nhánh Spring Boot khác, kiểm tra package, artifact, API và hướng dẫn migration tương ứng. Những hostname, ID và property sau đây chỉ để minh họa; không phải credential thật.

## 1. Bài toán: dịch vụ chạy được nhưng kết nối sai hệ thống

Một dịch vụ Spring Boot nhận webhook vận chuyển, ghi inbox/outbox vào PostgreSQL, gọi API đối tác để tra trạng thái giao hàng và xuất event lên broker. Hệ thống có nhiều môi trường: local, test, staging, production.

Ban đầu đội phát triển khai báo:

```yaml
integration:
  partner:
    base-url: https://shipping.example.test
    timeout: 5000
    retry:
      max-retries: 12
```

Nhìn qua cấu hình có vẻ đầy đủ, nhưng có nhiều câu hỏi chưa được trả lời:

- `timeout: 5000` nghĩa là **5.000 giây, mili giây hay đơn vị khác**?
- `base-url` có phải là một URI hợp lệ, bắt buộc HTTPS, hay có thể vô tình chứa user-info/token?
- `max-retries: 12` có vượt ngân sách retry khiến API đối tác quá tải không?
- Nếu `retry` không được khai báo, ứng dụng có bỏ qua kiểm tra những trường con không?
- Nếu thiếu biến môi trường, application có **thất bại khi khởi động** hay mã chỉ lỗi khi request đầu tiên chạy?
- Cấu hình đã bind đúng vào bean được inject hay chỉ nằm trong YAML mà không ai sử dụng?
- Khi nhiều instance cùng chạy, tổng timeout/retry/concurrency có vượt hạn mức của hệ thống đối tác không?

Đối với mô-đun `SPRING_BOOT_INTEGRATION`, cấu hình kết nối không đơn thuần là vài chuỗi trong `application.yml`. Nó là **hợp đồng vận hành** giữa ứng dụng, HTTP client, database, cache, broker và hệ thống bên ngoài. Một giá trị hợp lệ về cú pháp chưa chắc hợp lệ về nghiệp vụ hoặc an toàn khi triển khai.

`@ConfigurationProperties` giúp gom các property liên quan thành một bean **có kiểu**, có thể validate và kiểm thử riêng. Bean Validation giúp **fail fast** khi cấu hình không đạt ràng buộc trước khi ứng dụng bắt đầu xử lý công việc, thay vì chờ tới lúc mất dữ liệu hoặc gọi nhầm hệ thống.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Phân biệt `@ConfigurationProperties` với `@Value` và việc đọc trực tiếp `Environment`.
2. Bind các cấu hình lồng nhau, `Duration`, số nguyên, URI và collection theo quy tắc relaxed binding.
3. Đăng ký bean cấu hình bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
4. Dùng `@Validated`, `@NotBlank`, `@NotNull`, `@Valid`, `@Min`, `@Max` và validation liên trường.
5. Hiểu ranh giới giữa validation của property bean, kiểm tra kết nối thật và kiểm tra hợp đồng tích hợp.
6. Áp dụng cấu hình thực tế lên `RestClient` thay vì chỉ khai báo trong YAML.
7. Kiểm thử cấu hình hợp lệ/sai, bảo vệ secrets, chẩn đoán startup failure và nâng cấp an toàn.

## 2. Vị trí của @ConfigurationProperties trong Spring Boot

Spring Framework cung cấp `Environment`, property sources, IoC container và dependency injection. Spring Boot bổ sung cơ chế **externalized configuration** và **type-safe configuration properties binding** để nối dữ liệu từ file cấu hình, biến môi trường, command-line và các nguồn được hỗ trợ vào bean.

```mermaid
flowchart LR
    E["application.yml<br/>env / profile / command line"] --> P["Spring Environment<br/>property sources + precedence"]
    P --> B["Spring Boot Binder<br/>relaxed names + type conversion"]
    B --> V["Bean Validation<br/>@Validated + constraints"]
    V --> C["PartnerConnectionProperties<br/>immutable typed bean"]
    C --> A["RestClient adapter<br/>timeout + base URL"]
    C --> O["Observability / startup diagnostics"]
    A --> X["Partner HTTP API"]
```

Khi dùng đúng cơ chế:

- `@ConfigurationProperties` đặt **prefix** và định nghĩa cấu trúc của một nhóm cấu hình.
- Binder ánh xạ tên property sang constructor/field và chuyển đổi kiểu khi hỗ trợ.
- `@Validated` yêu cầu kích hoạt kiểm tra constraint trên bean đã bind.
- `@Valid` kích hoạt kiểm tra tiếp các object lồng nhau.
- Container quản lý bean cấu hình để service/adapter inject bằng constructor.

**Điểm quan trọng:** `@ConfigurationProperties` không tự mở kết nối HTTP, không tự tạo client và **không tự áp dụng timeout** lên mọi thư viện. Phần adapter phải lấy các giá trị đã được bind và cấu hình đúng API của client tương ứng.

## 3. @ConfigurationProperties so với @Value và Environment

| Cách đọc | Phù hợp với | Giới hạn cần nhớ |
|---|---|---|
| `@Value("${integration.partner.base-url}")` | Một hoặc vài property rời rạc | Validation nhóm và cấu hình lồng nhau không có cấu trúc rõ |
| `Environment.getProperty(...)` | Tra cứu động, điều kiện đặc biệt, công cụ nền tảng | Nhiều key dạng chuỗi, dễ thiếu type/validation tập trung |
| **`@ConfigurationProperties`** | Một cụm cấu hình có contract và nhiều field | Cần đăng ký bean, quản lý binding, validation và version |
| `@Bean @ConfigurationProperties` | Bind lên bean mutable từ thư viện bên thứ ba | Khác với constructor binding cho immutable record |

Ví dụ sử dụng `@Value` đơn lẻ:

```java
@Value("${integration.partner.base-url}")
private String partnerBaseUrl;
```

Cách này có thể phù hợp với một giá trị đơn giản. Nhưng khi phải kiểm tra rằng `base-url` là HTTPS, `timeout.read` dương, `retry.max-retries` nằm trong giới hạn và một nhóm thông số cùng hợp lệ, việc rải `@Value` khắp service gây khó bảo trì.

**Khuyến nghị:** dùng `@ConfigurationProperties` để định nghĩa hợp đồng kết nối, giữ `@Value` cho những trường hợp nhỏ thật sự không cần một configuration group.

## 4. Thiết kế hợp đồng cấu hình cho một HTTP partner

Giả sử dịch vụ dùng các field:

| Property | Java type | Bắt buộc? | Quy tắc |
|---|---|---:|---|
| `integration.partner.base-url` | `String` | Có | URI tuyệt đối, `https`, có host; không chứa user-info |
| `integration.partner.client-id` | `String` | Có | Không trắng; là ID kỹ thuật, không chứa secret |
| `integration.partner.timeout.connect` | `Duration` | Có | Dương và không vượt ngưỡng đã xác định |
| `integration.partner.timeout.read` | `Duration` | Có | Dương và không vượt ngưỡng đã xác định |
| `integration.partner.retry.max-retries` | `Integer` | Có | Từ `0` đến `5` |
| `integration.partner.retry.backoff` | `Duration` | Có | Không âm; nếu có retry thì phải dương |

Tạo file cấu hình:

```yaml
integration:
  partner:
    base-url: ${PARTNER_BASE_URL}
    client-id: ${PARTNER_CLIENT_ID}
    timeout:
      connect: 2s
      read: 5s
    retry:
      max-retries: 2
      backoff: 500ms
```

Những giá trị môi trường `PARTNER_BASE_URL` và `PARTNER_CLIENT_ID` phải được cấp trong cấu hình triển khai. Không để một URL production mặc định trong source chỉ để ứng dụng khởi động được.

Có thể đặt `PARTNER_BASE_URL=https://shipping.example.test` cho kiểm thử, nhưng URL đó chỉ là placeholder, không được phép dùng như endpoint thật mà chưa được cấu hình. Giá trị `2s`, `5s` và `500ms` có **đơn vị tường minh**, giúp tránh nhầm mili giây với giây.

## 5. Khai báo immutable record với @ConfigurationProperties

Đây là ví dụ đầy đủ cho Spring Boot 3 và Bean Validation API:

```java
package com.example.integration.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integration.partner")
public record PartnerConnectionProperties(
    @NotBlank String baseUrl,
    @NotBlank String clientId,
    @Valid @NotNull Timeouts timeout,
    @Valid @NotNull Retry retry
) {

    @AssertTrue(message = "base-url must be an absolute HTTPS URI without credentials")
    public boolean isSecureBaseUrl() {
        if (baseUrl == null || baseUrl.isBlank()) {
            return true; // @NotBlank xử lý lỗi thiếu/blank.
        }
        try {
            URI uri = URI.create(baseUrl);
            return "https".equalsIgnoreCase(uri.getScheme())
                && uri.getHost() != null
                && uri.getUserInfo() == null
                && uri.getFragment() == null;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    public record Timeouts(
        @NotNull Duration connect,
        @NotNull Duration read
    ) {
        @AssertTrue(message = "connect/read timeouts must be positive and at most 30 seconds")
        public boolean isTimeoutRangeValid() {
            return valid(connect) && valid(read);
        }

        private static boolean valid(Duration d) {
            return d != null
                && d.compareTo(Duration.ZERO) > 0
                && d.compareTo(Duration.ofSeconds(30)) <= 0;
        }
    }

    public record Retry(
        @NotNull @Min(0) @Max(5) Integer maxRetries,
        @NotNull Duration backoff
    ) {
        @AssertTrue(message = "backoff must be nonnegative and positive when retry is enabled")
        public boolean isRetryPolicyValid() {
            if (backoff == null || maxRetries == null) {
                return true; // @NotNull xử lý thiếu dữ liệu.
            }
            return backoff.compareTo(Duration.ZERO) >= 0
                && backoff.compareTo(Duration.ofSeconds(10)) <= 0
                && (maxRetries == 0 || backoff.compareTo(Duration.ZERO) > 0);
        }
    }
}
```

**Giải thích thiết kế:**

- `record` tạo immutable value object cho cấu hình đã bind; code khác không thể đổi trực tiếp field sau khi khởi tạo.
- `@ConfigurationProperties(prefix = "integration.partner")` định nghĩa nhóm key được bind.
- `@Validated` kích hoạt validation của Spring khi bean được tạo/bind qua infrastructure tương ứng.
- `@NotBlank` áp dụng cho `String` cần nội dung, không chỉ khác `null`.
- `@NotNull` giúp phát hiện thiếu nested object hoặc giá trị cần thiết.
- `@Valid` đảm bảo các constraint **bên trong** `Timeouts` và `Retry` được kiểm tra.
- `@Min`/`@Max` được dùng với `Integer`; chúng **không phải** cách validate `Duration`.
- `@AssertTrue` trên phương thức theo convention getter kiểm tra quy tắc nhiều field hoặc kiểu đặc biệt.

Ví dụ giới hạn 30 giây/5 lần retry là **quy tắc minh họa của ứng dụng**, không phải giới hạn mặc định của Spring Boot. Hãy chọn theo SLA, hạn mức partner, số instance và retry budget thực tế.

### 5.1. Vì sao sử dụng Integer thay vì int cho property bắt buộc?

Nếu `maxRetries` là `int` và bị thiếu, quá trình constructor binding có thể nhận giá trị nguyên thủy mặc định trong một số đường bind, khiến `0` bị hiểu là “có chủ ý không retry”. Với `Integer` và `@NotNull`, ta thể hiện rõ rằng property **phải được cung cấp**.

Điều tương tự áp dụng cho Boolean ba trạng thái: khi “chưa cấu hình” khác với `false`, dùng `Boolean` + validation hoặc chọn default có chủ đích.

### 5.2. @Valid không thay @NotNull

Một nested object không tồn tại có thể không được Bean Validation đi sâu vào vì không có object để validate. Vì vậy:

```java
@Valid @NotNull Timeouts timeout
```

thường cần **cả hai**: `@NotNull` bắt thiếu cả nhóm, `@Valid` kiểm tra các field con khi nhóm tồn tại. Chỉ đặt `@Valid` trên object nullable không tự có nghĩa nhóm bắt buộc phải xuất hiện.

## 6. Đăng ký bean cấu hình để Spring thực hiện binding

Một class chỉ có `@ConfigurationProperties` chưa chắc tự trở thành bean nếu bạn không đăng ký theo cơ chế phù hợp.

### 6.1. Cách 1: @ConfigurationPropertiesScan

```java
package com.example.integration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class IntegrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IntegrationApplication.class, args);
    }
}
```

Nếu `PartnerConnectionProperties` nằm trong `com.example.integration.config`, package con của class khởi động, scanner có thể phát hiện nó. Nếu class nằm trong thư viện/JAR ngoài package mặc định, dùng `@ConfigurationPropertiesScan(basePackageClasses = PartnerConnectionProperties.class)` hoặc cấu hình package tường minh tương ứng.

**Chú ý:** `@ConfigurationPropertiesScan` không tự quét `@Component` bất kỳ; nó tìm những type đánh dấu config properties. Không cần gắn `@Component` vào immutable record chỉ để đăng ký.

### 6.2. Cách 2: @EnableConfigurationProperties

Thích hợp khi muốn chỉ rõ những type cần đăng ký:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerConnectionProperties.class)
class PartnerPropertiesConfiguration {
}
```

Trong một ứng dụng chỉ cần chọn **một cơ chế đăng ký rõ ràng**; không cần vừa scan vừa enable đúng cùng một type ở nhiều nơi. Nếu tự định nghĩa bean khác cùng type và dùng constructor binding, phải kiểm tra đường đăng ký nào thực sự được sử dụng.

### 6.3. Không nhầm với @ComponentScan

`@ComponentScan` tìm các stereotype bean của Spring như `@Service` hoặc `@Component`. Nó không phải cách thay thế trực tiếp cho configuration properties scanning với immutable record. Hãy đặt application class ở package gốc hợp lý và đăng ký properties bean bằng API của Spring Boot.

## 7. Dependency để Bean Validation thực sự hoạt động

Spring Boot cho phép binding typed properties không cần mọi thư viện validation, nhưng các constraint `jakarta.validation.constraints.*` cần **Bean Validation provider** và Spring validation infrastructure phù hợp để được thực thi.

Gradle Groovy DSL:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    testImplementation("org.springframework.boot:spring-boot-starter-test")

    // Metadata cho IDE / cấu hình; không phải runtime validator.
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
```

Ví dụ này giả định build đã quản lý phiên bản Spring Boot theo plugin/BOM phù hợp. Với codebase Spring Boot 3, `jakarta.validation` là namespace được dùng; không copy `javax.validation` từ bài viết Spring Boot 2 mà không kiểm tra migration.

**Hai công cụ có trách nhiệm khác nhau:**

- `spring-boot-starter-validation`: cung cấp môi trường để chạy các constraint như `@NotBlank`, `@NotNull`, `@Valid` theo kiểu Bean Validation được hỗ trợ.
- `spring-boot-configuration-processor`: sinh metadata giúp IDE gợi ý property và mô tả type; **không** thực hiện validation runtime.

Nếu startup vẫn chấp nhận property sai, hãy kiểm tra bean có được quản lý qua `@ConfigurationProperties` hay chỉ được tạo thủ công bằng `new`, có `@Validated`, provider và nested `@Valid` hay chưa.

## 8. Relaxed binding: tên YAML, environment và Java khớp thế nào?

Binder của Spring Boot hỗ trợ các quy tắc tên linh hoạt:

| YAML/property key | Java record component |
|---|---|
| `base-url` | `baseUrl` |
| `client-id` | `clientId` |
| `max-retries` | `maxRetries` |
| `timeout.connect` | `Timeouts.connect` |
| `timeout.read` | `Timeouts.read` |

Khi cấu hình bằng system environment variables, dùng quy tắc chuyển đổi property name phù hợp phiên bản Boot (thường thay `.` bằng `_`, bỏ `-`, rồi viết hoa), hoặc sử dụng placeholder rõ ràng như `PARTNER_BASE_URL` trong YAML để tránh mơ hồ. Không suy đoán mọi tên có dấu gạch dưới sẽ mapping về cùng một cấu trúc ở mọi tình huống, đặc biệt với list/map keys.

### 8.1. Bind type khác nhau

```yaml
integration:
  partner:
    timeout:
      connect: 750ms
      read: 8s
    retry:
      max-retries: 3
      backoff: 1s
```

Binder chuyển giá trị sang `Duration`, `Integer` theo converter được hỗ trợ. Đừng viết `timeout.read: 5000` mà không biết đơn vị mặc định; nên luôn thêm `ms`, `s` hoặc `m` rõ ràng để tránh lỗi vận hành.

Các kiểu thường gặp có thể bind bao gồm `Duration`, `DataSize`, URI, enum, list, map và các kiểu cơ bản. Khả năng convert kiểu tùy module và converter có mặt.

### 8.2. Khi cần Date/URI/enum/custom value object

Ví dụ:

```java
public enum PartnerMode {
    SANDBOX, LIVE
}
```

```yaml
integration:
  partner:
    mode: LIVE
```

Một property có thể map sang enum nếu record có component tương ứng. Nhưng enum không giải quyết **quy tắc môi trường**: chế độ `LIVE` có được bật trên staging không, host có đúng không, secret/token có thuộc môi trường không? Các quy tắc này cần validation hoặc chính sách triển khai riêng.

Nếu kiểu tự định nghĩa không có converter mặc định, Spring Boot hỗ trợ khai báo converter dành cho configuration binding theo API như `@ConfigurationPropertiesBinding`. Converter phải **thuần túy, có test** và báo lỗi rõ; không thực hiện network call hoặc đọc secret bên ngoài một cách khó dự đoán khi bind.

## 9. Validation đầu vào: bắt lỗi thiếu, sai kiểu và sai ngữ nghĩa

Có ít nhất **ba lớp kiểm tra**:

| Lớp | Ví dụ lỗi | Cơ chế |
|---|---|---|
| **Binding/conversion** | `timeout.read: abc` không chuyển được sang `Duration` | Binder/type conversion, exception khi khởi tạo bean |
| **Bean Validation** | `client-id` rỗng, `max-retries` vượt `5` | `@Validated` và Jakarta Bean Validation constraints |
| **Semantic validation** | URL HTTP thay vì HTTPS; retry bật nhưng backoff bằng `0` | `@AssertTrue`, custom constraint hoặc validator do ứng dụng thiết kế |

### 9.1. Sai kiểu không đồng nghĩa vi phạm constraint

Giá trị `max-retries: ten` có thể gây **binding failure** trước khi `@Min`/`@Max` chạy. Giá trị `max-retries: 9` là số nguyên chuyển đổi được nhưng vi phạm giới hạn.

Khi chẩn đoán startup, cần tìm **root cause** và tên property cụ thể: `BindException`, `ConfigurationPropertiesBindException`, `BindValidationException` hay lỗi conversion/validation tương ứng. Tên exception có thể khác theo phiên bản và lớp bọc; không chỉ nhìn dòng đầu “Application failed to start”.

### 9.2. Không dùng constraint sai kiểu

```java
// Không hợp lý: @Min/@Max nhắm tới numeric type, không phải Duration.
@Min(1)
Duration readTimeout;
```

Dùng `@NotNull` cho hiện diện và custom validation cho giới hạn `Duration`, hoặc sử dụng constraint chuyên biệt được **Bean Validation provider** hiện tại hỗ trợ sau khi đã kiểm tra package/phiên bản. Trong ví dụ chính, `@AssertTrue` tường minh hóa quy tắc dương và trần 30 giây.

### 9.3. Validation nhiều field cần thông báo dễ hiểu

Kiểm tra `retry.max-retries` và `retry.backoff` cùng nhau: nếu bật retry mà backoff bằng `0`, có thể tạo retry storm. `@AssertTrue` trong nested record minh họa quy tắc này.

Nếu hệ thống có hàng chục field và nhiều quy tắc phức tạp, cân nhắc custom constraint như `@ValidPartnerRetryPolicy` kèm `ConstraintValidator<..., PartnerConnectionProperties.Retry>` để tập trung logic và tạo message lỗi rõ hơn. Không nên nhét logic kết nối network vào validator; validation cấu hình chủ yếu nên **thuần túy và xác định được**.

## 10. Giá trị mặc định: tiện lợi nhưng có thể che lỗi thiếu cấu hình

Các lựa chọn default thường gặp:

1. Đặt default trong `application.yml`.
2. Dùng `@DefaultValue` ở constructor parameter/record component theo API Spring Boot hỗ trợ.
3. Tạo giá trị mặc định tại configuration class/bean khi hợp đồng cho phép.

Ví dụ cho một property **không bắt buộc**, theo API Boot 3:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

public record OptionalTimeout(
    @DefaultValue("2s") Duration connect
) {}
```

Không dùng default để “cho phép ứng dụng chạy bằng mọi giá” đối với URL, tenant, database name hoặc broker destination quan trọng. Ví dụ đặt URL production làm fallback cho staging là rủi ro lớn hơn một startup failure có thông báo rõ.

### 10.1. Phân biệt default và bắt buộc

| Property | Thường nên bắt buộc? | Có thể dùng default? |
|---|---|---|
| Partner base URL | **Có** | Tránh default production |
| Tenant/namespace đích | **Có** nếu ảnh hưởng dữ liệu | Chỉ dùng default có kiểm soát |
| Client ID | Có | Không nên gán từ máy local ngẫu nhiên |
| Connect/read timeout | Có hoặc default đã phê duyệt | Có, nếu SLA thống nhất |
| Max retries | Theo chính sách vận hành | Có, nhưng cần budget |
| Logging verbosity | Không | Có |
| Tracing sampling | Không | Có, nhưng kiểm soát hiệu năng/chi phí |

### 10.2. Tham số ngoài dự kiến

`@ConfigurationProperties` có tùy chọn xử lý **unknown fields** và **invalid fields** theo API Boot, ví dụ `ignoreUnknownFields = false` để tăng tính chặt chẽ trong các trường hợp được binder nhận diện. Tuy nhiên, **không nên xem đây là công cụ phát hiện tuyệt đối mọi typo** ở mọi property source, đặc biệt với cấu trúc map/dynamic keys. Cần kết hợp metadata, review cấu hình, kiểm thử context và kiểm soát deploy.

Không bật tùy chọn “bỏ qua invalid fields” để né lỗi bind khi cấu hình dùng cho kết nối quan trọng; việc che lỗi chuyển đổi có thể khiến hệ thống chạy với tham số không đúng dự kiến.

## 11. Áp dụng cấu hình đã validate lên RestClient thực sự

Đến đây mới có một object config hợp lệ. Muốn `timeout.connect` và `timeout.read` hoạt động, phải **áp dụng vào HTTP client**. Một ví dụ với Spring MVC/`RestClient` và request factory đơn giản:

```java
package com.example.integration.http;

import com.example.integration.config.PartnerConnectionProperties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PartnerRestClientConfiguration {

    @Bean("partnerRestClient")
    RestClient partnerRestClient(
            RestClient.Builder builder,
            PartnerConnectionProperties properties) {

        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(Math.toIntExact(
            properties.timeout().connect().toMillis()));
        requestFactory.setReadTimeout(Math.toIntExact(
            properties.timeout().read().toMillis()));

        return builder
            .baseUrl(properties.baseUrl())
            .requestFactory(requestFactory)
            .defaultHeader("X-Client-Id", properties.clientId())
            .build();
    }
}
```

Điều cần hiểu:

- `RestClient.Builder` do Boot có thể cung cấp/tùy chỉnh theo dependency và phiên bản.
- `SimpleClientHttpRequestFactory` dùng để minh họa rõ cách gắn timeout; **nó không phải lựa chọn mặc định tối ưu cho hệ thống tải cao cần pool connection và nhiều tính năng HTTP nâng cao**.
- Khi production yêu cầu pooling/TLS/proxy hoặc connection lifecycle phức tạp, chọn request factory/client stack phù hợp và cấu hình timeout theo API cụ thể, có test.
- `Math.toIntExact(...)` phát hiện overflow khi chuyển duration sang mili giây kiểu `int`; ở ví dụ validation đã giới hạn `Duration` nên trường hợp này ít xảy ra.
- Header `X-Client-Id` là metadata không bí mật. Nếu dùng Bearer token/API key, cần giải pháp auth riêng và tránh để token xuất hiện trong log.

Một adapter có thể inject client theo qualifier:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerStatusGateway {
    private final RestClient client;

    public PartnerStatusGateway(
            @Qualifier("partnerRestClient") RestClient client) {
        this.client = client;
    }

    public String fetchStatus(String shipmentId) {
        return client.get()
            .uri("/shipments/{id}/status", shipmentId)
            .retrieve()
            .body(String.class);
    }
}
```

Method `fetchStatus` chỉ minh họa gọi HTTP; production cần định nghĩa DTO hợp đồng, mapping lỗi HTTP, timeout/retry có chọn lọc, bảo mật, correlation ID và kiểm thử với mock HTTP server.

### 11.1. Một property có mặt không chứng minh hành vi đã hiệu lực

`integration.partner.timeout.read: 5s` **chưa tự tạo timeout** nếu code chỉ thực hiện:

```java
return builder.baseUrl(properties.baseUrl()).build();
```

Cần kiểm thử thời gian xử lý khi upstream cố tình trì hoãn phản hồi. Tương tự, `retry.max-retries` chỉ là một con số: phải gắn vào retry policy của adapter hoặc job relay, nếu không nó không làm hệ thống tự retry.

## 12. @ConfigurationProperties cho database, cache và broker

Cách tiếp cận tương tự có thể dùng cho các nhóm cấu hình phụ trợ, nhưng cần phân biệt **property chuẩn của Spring Boot** và **property do ứng dụng tự định nghĩa**.

| Nhu cầu | Property Boot/library phổ biến | Property ứng dụng tự định nghĩa |
|---|---|---|
| Database JDBC | `spring.datasource.*` | `integration.inbox.retention-days`, `integration.outbox.batch-size` |
| JPA/Hibernate | `spring.jpa.*` | `integration.reconciliation.max-age` |
| Redis/Cache | `spring.data.redis.*` / `spring.cache.*` theo phiên bản | `integration.cache.default-ttl` |
| Kafka | `spring.kafka.*` | `integration.events.topic`, `integration.events.max-inflight` |
| RabbitMQ | `spring.rabbitmq.*` | `integration.messaging.retry-policy.*` |
| HTTP client partner | Cấu hình builder/client theo API thực tế | `integration.partner.*` |
| Spring Integration | Channel/poller/adapter có config riêng | `integration.flow.poll-delay`, `integration.flow.queue-capacity` |

Ví dụ nếu định nghĩa:

```yaml
integration:
  events:
    topic: orders.events.v1
    max-inflight: 200
```

thì cần một bean `@ConfigurationProperties(prefix = "integration.events")` và code producer thực sự đọc các field đó. Chỉ đưa key vào YAML **không tự tạo Kafka topic** hay cập nhật producer configuration.

### 12.1. Không thay thế bean Boot không cần thiết

Nếu mục tiêu là cấu hình pool PostgreSQL, sử dụng `spring.datasource.hikari.*` khi dùng Hikari thông qua Boot thay vì vội tạo `@Bean DataSource` mới. Nếu tự khai báo DataSource, một số nhánh auto-configuration có thể **back off** và các property mặc định không còn được áp dụng như trước.

Tương tự, nếu chỉ cần HTTP client theo đối tác, thường nên inject builder phù hợp rồi tạo bean client riêng, thay vì tự định nghĩa lại `RestClient.Builder` toàn ứng dụng.

### 12.2. Custom @Bean @ConfigurationProperties khác immutable record

Một third-party mutable bean có thể được bind trực tiếp:

```java
@Bean
@ConfigurationProperties(prefix = "integration.legacy-client")
LegacyClientSettings legacyClientSettings() {
    return new LegacyClientSettings();
}
```

`LegacyClientSettings` là class minh họa có setter/getter do thư viện hoặc ứng dụng cung cấp. Đường này là **binding lên một bean đã được factory method tạo**, không phải constructor binding của immutable record trong ví dụ chính. Các quy tắc validation vẫn cần được xác lập; không mặc nhiên suy luận `@Validated` đặt ở mọi nơi sẽ có cùng hành vi khi dùng các đường tạo bean khác nhau.

## 13. Cấu hình môi trường, profile và thứ tự ưu tiên

Spring Boot tập hợp property từ nhiều nguồn theo **thứ tự ưu tiên** đã quy định cho phiên bản hiện tại. Một giá trị trong `application.yml` có thể bị ghi đè bởi biến môi trường, command-line argument hoặc nguồn cấu hình được import.

Ví dụ:

```yaml
# application.yml
integration:
  partner:
    timeout:
      connect: 2s
      read: 5s
```

```yaml
# application-staging.yml (minh họa một profile)
integration:
  partner:
    timeout:
      read: 10s
```

Khi profile `staging` được kích hoạt theo đúng cơ chế, `timeout.read` có thể là `10s` còn `timeout.connect` vẫn lấy từ cấu hình chung. Tuy nhiên, một nguồn có ưu tiên cao hơn có thể tiếp tục override cả hai. **Không xác định cấu hình hiệu lực chỉ bằng cách đọc một file YAML.**

### 13.1. Configuration binding có thể thay đổi qua deployment

- Thiết lập profile tại môi trường triển khai theo quy trình tổ chức, không hard-code `spring.profiles.active` bừa bãi trong code.
- Không lưu token/mật khẩu trong `application-prod.yml` được commit lên Git.
- Nếu dùng `spring.config.import` để nhập cấu hình ngoài, cần hiểu hành vi khi nguồn không sẵn sàng và quy trình cấp quyền.
- Khi config thay đổi, không mặc nhiên mọi bean immutable tự refresh tại runtime. Cần thiết kế cơ chế refresh/restart có kiểm soát nếu có yêu cầu thay đổi động.
- Với config map/secret có nhiều phiên bản, quy định rollout và kiểm thử “hai version cùng chạy” khi đổi endpoint hay schema.

### 13.2. Endpoint đúng môi trường quan trọng hơn việc khởi động thành công

Một `base-url` HTTPS và DNS resolve thành công **vẫn có thể trỏ sai tenant hoặc môi trường**. Cần quy tắc môi trường: production chỉ gọi endpoint production được phê duyệt, staging chỉ dùng sandbox hoặc test tenant. Đây là **semantic/policy validation** có thể thực hiện bằng configuration policy, allowlist host, deploy admission checks hoặc test cấu hình theo môi trường.

## 14. Secrets, logging và Actuator configprops

Cấu hình kết nối thường chứa credential, token, password hoặc secret endpoint. Chúng cần được bảo vệ ngay từ bước binding:

1. Lấy secrets từ secret manager/env được tổ chức quản lý; không hard-code và không đưa vào ví dụ log.
2. Nếu bean properties có secret field, tránh gọi `toString()` trên record vì nó có thể in toàn bộ field.
3. Không đưa credential vào URI `https://user:pass@host`.
4. Che giá trị nhạy cảm trong exception, health diagnostics và support bundle.
5. Đảm bảo actuator endpoints, tracing và logging không vô tình lộ config.
6. Dùng quyền tối thiểu cho database, broker, Redis và API đối tác.

Actuator có endpoint như `/actuator/configprops` (nếu dependency, exposure và quyền phù hợp) để quan sát **configuration properties beans**. Nhưng endpoint đó có thể tiết lộ cấu trúc bean, key và có chính sách hiển thị/masking giá trị tùy phiên bản. **Không bật công khai** hoặc tắt masking chỉ vì muốn debug.

### 14.1. Tránh ghi toàn bộ bind failure chứa secret

Validation message nên chỉ ra tên property và **quy tắc** sai (ví dụ “must not be blank”), không in token hoặc credential đang được bind. Với custom `@AssertTrue`, trả về thông báo tĩnh rõ ràng như ví dụ `base-url must be HTTPS`, không ghép nội dung secret vào message.

## 15. Fail-fast validation khác health check và readiness

Có ba thời điểm kiểm tra khác nhau:

```mermaid
flowchart LR
    A["Startup: bind + validate config"] --> B["Khởi tạo HTTP/DB/broker clients"]
    B --> C["Readiness: có thể phục vụ?"]
    C --> D["Runtime: request/job/message"]
    D --> E["Resilience: timeout/retry/circuit breaker"]
    E --> F["Metrics + alert + reconciliation"]
```

| Cơ chế | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Configuration validation** | “Các thông số có hiện diện, đúng type và hợp lý không?” | `timeout.read > 0`, `base-url` là HTTPS |
| **Startup connectivity** | “Có kết nối ban đầu được không?” | Ping DB hoặc broker trong phase khởi tạo nếu được thiết kế |
| **Readiness/health** | “Instance hiện đủ khả năng phục vụ traffic không?” | Connection pool, dependency thiết yếu |
| **Runtime resilience** | “Dependency thất bại giữa lúc xử lý thì sao?” | Timeout, retry budget, circuit breaker, outbox |
| **End-to-end reconciliation** | “Công việc đã thật sự hoàn tất ở downstream chưa?” | Outbox pending, consumer processing status |

Không nên thực hiện network call trong `ConstraintValidator` hoặc `@AssertTrue` để “validate URL đúng” — phụ thuộc ngoài có thể chập chờn, làm startup thiếu ổn định và logic validation khó test. Kiểm tra URI syntax/allowlist ở configuration layer, còn kiểm tra health/readiness/liveness theo chính sách hệ thống.

Đặc biệt, đối tác HTTP tạm ngừng không nhất thiết phải làm **liveness** fail khiến pod restart liên tục. Nếu ứng dụng vẫn có thể nhận và lưu request vào inbox/outbox, readiness và business degradation nên được xác định theo SLA.

## 16. Validation cấu hình trong luồng webhook → DB → outbox → broker

Một sơ đồ tích hợp điển hình:

```mermaid
sequenceDiagram
    participant Boot as Spring Boot startup
    participant Binder as Binder + Bean Validation
    participant API as Webhook Controller
    participant Service as Application service
    participant DB as PostgreSQL
    participant Relay as Outbox relay
    participant Broker as Kafka / RabbitMQ

    Boot->>Binder: Bind integration.partner.*
    Binder-->>Boot: Validated PartnerConnectionProperties
    Boot->>API: Application ready
    API->>Service: receive webhook(eventId)
    Service->>DB: TX: inbox + state + outbox
    DB-->>Service: Commit
    Service-->>API: accepted / duplicate
    Relay->>DB: claim committed outbox
    Relay->>Broker: publish event
    Broker-->>Relay: publish acknowledgement
    Relay->>DB: mark published or retry
```

Configuration validation không thay những trách nhiệm sau:

- **Inbound HTTP contract:** kiểm tra chữ ký, payload schema, tenant và event ID.
- **Database transaction:** ràng buộc UNIQUE trên `partner,eventId` và ghi inbox/outbox trong cùng transaction.
- **HTTP client:** áp dụng timeout/authorization thực tế và xử lý kết quả không chắc chắn.
- **Broker:** chọn đúng topic/queue, serializer, ACK và retry.
- **Consumer:** idempotent processing; duplicate message có thể đến từ relay retry/redelivery.
- **Observability:** correlation ID, event ID, số outbox pending và lỗi theo ranh giới.

### 16.1. Không nhầm valid config với đúng nghiệp vụ

`retry.max-retries = 5` có thể nằm trong giới hạn Bean Validation, nhưng có thể quá cao đối với API đối tác giới hạn 10 request/phút. Cần chọn retry budget dựa trên **SLA và hạn mức thực tế**, kết hợp backoff/jitter, concurrency và tổng tải toàn cụm.

Tương tự, tên topic Kafka hợp lệ theo cú pháp không chứng minh topic tồn tại, quyền publish đã được cấp hoặc schema producer/consumer tương thích.

## 17. Kiểm thử cấu hình với ApplicationContextRunner

Khi viết properties bean, nên có **test context nhỏ** để kiểm tra ba nhóm: hợp lệ, thiếu field và giá trị sai.

Ví dụ Spring Boot 3 test support, dùng `ApplicationContextRunner` và validation auto-configuration:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PartnerPropertiesBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PartnerConnectionProperties.class)
    static class TestConfig {
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(ValidationAutoConfiguration.class))
            .withUserConfiguration(TestConfig.class);

    @Test
    void bindsAndValidatesCorrectValues() {
        runner.withPropertyValues(
            "integration.partner.base-url=https://partner.example.test",
            "integration.partner.client-id=order-service",
            "integration.partner.timeout.connect=2s",
            "integration.partner.timeout.read=5s",
            "integration.partner.retry.max-retries=2",
            "integration.partner.retry.backoff=500ms"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNull();

            PartnerConnectionProperties props =
                context.getBean(PartnerConnectionProperties.class);

            assertThat(props.timeout().read())
                .isEqualTo(java.time.Duration.ofSeconds(5));
            assertThat(props.retry().maxRetries()).isEqualTo(2);
        });
    }

    @Test
    void failsOnInvalidRetryAndTimeout() {
        runner.withPropertyValues(
            "integration.partner.base-url=https://partner.example.test",
            "integration.partner.client-id=order-service",
            "integration.partner.timeout.connect=0s",
            "integration.partner.timeout.read=5s",
            "integration.partner.retry.max-retries=9",
            "integration.partner.retry.backoff=0ms"
        ).run(context ->
            assertThat(context.getStartupFailure()).isNotNull()
        );
    }
}
```

Test này minh họa cách tách validation khỏi database, broker và HTTP thật. Nó giả định dependency Bean Validation đã có, các class/config ở cùng package test hoặc import hợp lệ, và API test support đúng phiên bản.

**Đừng chỉ assert “startup failed”** trong test thật. Nên kiểm tra thêm root cause có liên quan tới đúng field/constraint cần kiểm, tránh một lỗi classpath hay bean thiếu khiến test sai vẫn báo pass.

### 17.1. Một số test case bổ sung

| Test case | Kết quả mong đợi |
|---|---|
| Thiếu `base-url` | Fail do `@NotBlank` |
| `base-url` là HTTP thay HTTPS | Fail do semantic validation |
| `base-url` sai cú pháp URI | Fail với message tĩnh không lộ secret |
| Thiếu toàn bộ `timeout` | Fail do `@NotNull` nested |
| `timeout.connect=0s` | Fail do positive duration rule |
| `timeout.read=31s` | Fail do giới hạn minh họa 30 giây |
| `max-retries=-1` hoặc `6` | Fail do `@Min`/`@Max` |
| `max-retries=2`, `backoff=0ms` | Fail do cross-field policy |
| `max-retries=0`, `backoff=0ms` | Pass nếu hợp đồng cho phép |
| `timeout.read=not-a-duration` | Fail từ binder/conversion |
| Env ghi đè YAML | Kết quả bind lấy đúng nguồn ưu tiên |
| Config đúng nhưng HTTP chậm | Client thật timeout theo request factory đã cấu hình |
| Hai bean cùng type | Injection rõ `@Qualifier`, không phụ thuộc chọn ngẫu nhiên |
| Custom DataSource/HTTP builder | Cấu hình dùng đúng bean, không mất auto-customizers ngoài ý muốn |

## 18. Kiểm thử integration: config hợp lệ phải tạo đúng client

Validation unit chỉ chứng minh các field đạt constraint, **không chứng minh adapter đã sử dụng chúng**. Cần integration test ở các ranh giới quan trọng.

Ví dụ với mock HTTP server do test sở hữu:

1. Cấu hình `base-url` trỏ tới mock server ở port test.
2. Tạo `RestClient` qua `PartnerRestClientConfiguration`, không tạo builder khác trong test.
3. Gửi một request và kiểm tra path, header, body và authentication chính xác.
4. Cho mock server trì hoãn phản hồi vượt `timeout.read`, xác minh client timeout.
5. Cho server trả HTTP 429/503/400, kiểm tra phân loại retryable/non-retryable theo chính sách.
6. Kiểm tra rằng retry không dùng ID mới cho cùng command và không gửi quá ngân sách.
7. Xác minh không có secret/token xuất hiện ở log, exception hoặc metrics.

Với database/broker, kiểm thử tương tự việc bind endpoint và quyền: tạo datasource/consumer thật bằng test infrastructure, kiểm tra schema, unique constraint, producer ACK và xử lý trùng. **Không lấy việc `ApplicationContext` khởi động thành công làm bằng chứng tích hợp đã đúng toàn tuyến.**

## 19. Troubleshooting: lỗi cấu hình thường xuất hiện ở đâu?

### 19.1. Startup không có PartnerConnectionProperties bean

Lỗi kiểu:

```text
No qualifying bean of type
'com.example.integration.config.PartnerConnectionProperties'
```

Kiểm tra `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`, package scanner có bao phủ type không, và có vô tình tạo record bằng `new` bên ngoài container không. `@ConfigurationProperties` **không phải** `@Component`.

### 19.2. Bean tồn tại nhưng field toàn null

Cần xem:

- Prefix có đúng là `integration.partner` không?
- YAML đang chứa key đúng cấu trúc chưa?
- Profile/property source nào đang có ưu tiên cao?
- Có tự khai báo bean mutable mà không bind như kỳ vọng không?
- Có dùng constructor binding đúng phiên bản không?
- Bean có được tạo trong **đúng ApplicationContext** đang chạy không?

Khi có `@NotNull` và `@NotBlank` đúng như ví dụ, tình trạng thiếu field bắt buộc phải làm startup fail thay vì âm thầm chạy; nếu không, validation có thể chưa được kích hoạt.

### 19.3. Validation không chạy hoặc chạy thiếu nested object

Kiểm tra:

1. Dependency validation provider có trên runtime classpath không?
2. Type properties có `@Validated` hoặc đường bật validation phù hợp không?
3. Type được bind qua Spring Boot binder, hay chỉ khởi tạo bằng `new`?
4. Nested field có `@Valid` để kiểm tra constraint bên trong không?
5. Nested object bắt buộc có `@NotNull` không?
6. Có exception được bắt hoặc cấu hình bỏ qua invalid fields che mất lỗi không?

### 19.4. Timeout đã khai báo nhưng request vẫn treo

Một biểu hiện điển hình là code đọc `timeout.read` từ properties để log nhưng không gắn vào HTTP client. Kiểm tra **bean RestClient được inject thực tế**, request factory, các interceptor/client khác và test độ trễ. Nhiều client có phân biệt connect timeout, response/read timeout, connection acquisition timeout và tổng deadline; không dùng một property làm thay thế cho tất cả.

### 19.5. Cấu hình env “đúng” nhưng ứng dụng dùng giá trị khác

Đối chiếu thứ tự ưu tiên của Spring Boot cho phiên bản hiện tại, profile đang bật, import sources và placeholder. Không in secret ra màn hình; khi chẩn đoán, chỉ log **nguồn/property key không nhạy cảm, type và trạng thái hợp lệ**, hoặc dùng công cụ nội bộ có masking.

### 19.6. Bean tự khai báo làm Boot back off

Khi tạo `DataSource`, `RestClient.Builder` hoặc infrastructure bean khác, điều kiện auto-configuration như `@ConditionalOnMissingBean` có thể khiến Boot **không tạo default bean**. Đọc Condition Evaluation Report (ví dụ startup với `--debug` trong môi trường kiểm soát) và bean wiring thật trước khi thêm annotation hoặc bật bean definition overriding.

## 20. Checklist triển khai cấu hình kết nối đáng tin cậy

1. **Phân nhóm property** theo adapter/đối tác (`integration.partner.*`, `integration.events.*`), không rải magic string.
2. **Chọn type đúng**: `Duration`, `Integer`, URI, enum, list/map; tránh truyền đơn vị thời gian mơ hồ.
3. **Đánh dấu bắt buộc** bằng `@NotBlank`/`@NotNull` và dùng boxed types khi thiếu khác giá trị mặc định.
4. **Validate nested** bằng `@Valid` cùng `@NotNull` khi nhóm bắt buộc.
5. **Validate ngữ nghĩa**: HTTPS, URL allowlist, timeout dương, retry budget và cross-field invariants.
6. **Đăng ký đúng bean** qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
7. **Có validator provider** và test startup fail khi giá trị sai; không dựa vào annotation chỉ hiện trên source.
8. **Ưu tiên cấu hình chuẩn của Boot** cho datasource/broker/cache khi có thể; tránh manual bean làm mất auto-config.
9. **Áp dụng cấu hình vào client thực tế**: pool, timeout, TLS, auth, retry; không chỉ bind rồi bỏ đó.
10. **Không đưa bí mật vào source/log/Actuator public**; kiểm tra masking, quyền và vòng đời secret.
11. **Quản lý môi trường**: profile, placeholder, import, precedence, tenant và đích kết nối được phê duyệt.
12. **Phân biệt validation và health**; không biến external outage thành lỗi cấu hình không liên quan.
13. **Bảo đảm nghiệp vụ**: inbox/outbox, idempotency, transaction, consumer ACK và reconciliation vẫn cần thiết.
14. **Kiểm thử đa tầng**: binding unit, Spring context, mock HTTP, DB/broker integration và crash/retry.
15. **Quan sát hành vi**: config validation failure, timeout, retry count, pool saturation, outbox backlog và correlation ID.

### Tự kiểm tra kiến thức

**Câu 1:** `@ConfigurationProperties` khác gì `@Value` khi cấu hình một HTTP partner?  
**Trả lời:** Nó gom nhiều property thành một bean có kiểu, hỗ trợ nested binding và validation tập trung. `@Value` phù hợp với một vài giá trị đơn giản.

**Câu 2:** Chỉ dùng `@NotNull` trên nested `Timeouts` có đủ để kiểm tra `connect > 0` không?  
**Trả lời:** Không. Cần `@Valid` để kích hoạt constraint bên trong và thêm rule dương đối với `Duration`.

**Câu 3:** Đã có `timeout.read: 5s` trong YAML, RestClient có tự timeout sau 5 giây không?  
**Trả lời:** Không mặc nhiên. Adapter phải áp dụng giá trị vào request factory/client tương ứng và kiểm thử hành vi.

**Câu 4:** `@Min(1) Duration timeout` có phải cách đúng để validate thời lượng không?  
**Trả lời:** Không nên. `@Min` áp dụng cho kiểu số; dùng constraint phù hợp với `Duration` hoặc custom validation có kiểm thử.

**Câu 5:** Vì sao bean chứa token không nên dùng `record.toString()` trong log?  
**Trả lời:** Record thường đưa field vào chuỗi biểu diễn, có thể làm lộ secret.

**Câu 6:** Property bean đã validate thành công có bảo đảm broker đang hoạt động và đúng quyền không?  
**Trả lời:** Không. Cần connectivity/readiness check và integration test theo môi trường, cùng chính sách retry/alert.

**Câu 7:** Nếu một biến môi trường ghi đè YAML, giá trị nào được bind?  
**Trả lời:** Giá trị từ property source có ưu tiên cao theo quy tắc của phiên bản Spring Boot đang dùng; cần kiểm tra cấu hình hiệu lực.

---

Trong chương **Cấu hình kết nối** của `SPRING_BOOT_INTEGRATION`, hãy nhớ: **`@ConfigurationProperties` biến cấu hình ngoài ứng dụng thành một hợp đồng Java có kiểu; `@Validated` và Bean Validation buộc hợp đồng đó đúng ngay từ lúc khởi tạo**. Nhưng một config bean hợp lệ **không thay thế** việc cấu hình client thực, bảo vệ bí mật, xác định ranh giới transaction, thiết kế idempotency/retry và quan sát kết quả HTTP–database–cache–broker xuyên hệ thống.
