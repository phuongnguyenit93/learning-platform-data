# Chọn @Value, Environment hoặc @ConfigurationProperties

> **Chương:** Cấu hình kiểu dữ liệu  
> **Module:** SPRING_CLOUD_CORE

Spring Boot cung cấp nhiều cách để đọc cấu hình từ `application.yml`, profile, biến môi trường, tham số dòng lệnh và các nguồn do Spring Cloud bổ sung. Ba cách thường gặp là **`@Value`**, **`Environment`** và **`@ConfigurationProperties`**. Chúng đều có thể đọc giá trị từ môi trường cấu hình, nhưng phục vụ những nhu cầu khác nhau.

Chọn sai cơ chế thường làm cấu hình bị rải rác, khó kiểm tra kiểu dữ liệu, thiếu validation hoặc khó kiểm thử. Bài này giúp chọn đúng công cụ theo hình dạng dữ liệu và vòng đời sử dụng, đồng thời minh họa cách bind cấu hình cho một client giao tiếp dịch vụ trong module **SPRING_CLOUD_CORE**.

## 1. Ba cách tiếp cận và vai trò chính

| Cơ chế | Phù hợp nhất khi | Đặc điểm |
| --- | --- | --- |
| `@Value` | Một vài giá trị đơn giản cần inject trực tiếp vào bean | Ngắn gọn, hỗ trợ placeholder và SpEL, phù hợp với một thuộc tính nhỏ |
| `Environment` | Cần tra cứu property theo tên trong code, kiểm tra sự hiện diện hoặc chọn giá trị theo logic | API linh hoạt, có thể yêu cầu kiểu đích, truy cập nhiều nguồn property |
| `@ConfigurationProperties` | Có một nhóm thuộc tính liên quan, có cấu trúc và cần validation | Typed binding, gom cấu hình thành một object, hỗ trợ nested object, list, map và metadata |

Cả ba cơ chế đều đọc từ **Spring Environment** hoặc quy trình binding dựa trên nguồn cấu hình của Spring Boot. Chúng không phải ba kho cấu hình riêng biệt và không tự tạo ra ba bộ giá trị khác nhau. Giá trị hiệu lực vẫn chịu ảnh hưởng của property source, profile và thứ tự ưu tiên.

Có thể bắt đầu bằng câu hỏi: cấu hình là một giá trị đơn lẻ, một nhóm dữ liệu có cấu trúc, hay một key chỉ được xác định khi code đang chạy? Câu trả lời thường dẫn tới lựa chọn phù hợp.

## 2. Dùng @Value cho một vài thuộc tính đơn giản

`@Value` inject một biểu thức vào field, constructor parameter hoặc method parameter của bean Spring. Cách dùng phổ biến nhất là placeholder:

~~~yaml
spring:
  application:
    name: order-service

catalog:
  client:
    base-url: "https://catalog.internal"
    read-timeout: 3s
~~~

Ví dụ inject một giá trị:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ApplicationIdentity {

    private final String applicationName;

    public ApplicationIdentity(
            @Value("${spring.application.name:unknown-service}")
            String applicationName) {
        this.applicationName = applicationName;
    }

    public String applicationName() {
        return applicationName;
    }
}
~~~

Placeholder `${spring.application.name:unknown-service}` đọc property `spring.application.name`. Nếu không có giá trị phân giải được, phần sau dấu `:` là giá trị mặc định.

### 2.1. Placeholder, giá trị mặc định và kiểu dữ liệu

Spring có thể chuyển đổi giá trị placeholder sang kiểu đích được hỗ trợ:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class RetrySettings {

    private final int maxAttempts;
    private final Duration retryDelay;

    public RetrySettings(
            @Value("${catalog.client.max-attempts:3}") int maxAttempts,
            @Value("${catalog.client.retry-delay:500ms}") Duration retryDelay) {
        this.maxAttempts = maxAttempts;
        this.retryDelay = retryDelay;
    }
}
~~~

Các giá trị có thể được chuyển đổi theo conversion service của Spring. Ví dụ chuỗi `500ms` có thể được chuyển thành `Duration`. Tuy nhiên, khi số lượng thuộc tính tăng, việc khai báo từng tham số `@Value` làm constructor dài và khiến cấu hình khó quản lý.

### 2.2. SpEL và placeholder là hai cú pháp khác nhau

`@Value` còn hỗ trợ Spring Expression Language (SpEL), ví dụ:

~~~java
@Value("#{systemProperties['user.timezone']}")
private String timezone;
~~~

Placeholder `${...}` đọc một property từ Environment. SpEL `#{...}` đánh giá biểu thức theo ngữ cảnh Spring. Không dùng SpEL cho dữ liệu đầu vào tùy ý hoặc chuỗi do người dùng cung cấp; biểu thức nên được viết cố định trong mã nguồn và chỉ phục vụ nhu cầu cấu hình đã xác định.

### 2.3. Khi nào @Value không còn phù hợp?

Nếu một bean cần hàng chục giá trị thuộc cùng namespace, ví dụ URL, timeout, pool size, retry và danh sách header, việc inject từng key làm cấu hình phân tán khắp code. `@Value` cũng không tự cung cấp một object cấu hình có schema và bộ validation tập trung.

`@Value` phù hợp với một số thuộc tính nhỏ như tên ứng dụng, một cờ đơn giản hoặc một giới hạn riêng của bean. Khi cấu hình trở thành một nhóm có ý nghĩa, nên chuyển sang `@ConfigurationProperties`.

## 3. Dùng Environment khi cần tra cứu linh hoạt

`Environment` là abstraction của Spring để truy cập property và profile của ứng dụng. Có thể inject nó vào một bean:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ServiceEndpointResolver {

    private final Environment environment;

    public ServiceEndpointResolver(Environment environment) {
        this.environment = environment;
    }

    public String endpointFor(String serviceName) {
        String key = "services." + serviceName + ".base-url";
        return environment.getProperty(key);
    }
}
~~~

Ở ví dụ này, tên service được xác định khi code chạy nên không thể dễ dàng khai báo một placeholder cố định cho từng key. `Environment` cho phép ghép tên property rồi tra cứu theo nhu cầu.

### 3.1. Các phương thức thường dùng

| API | Tác dụng |
| --- | --- |
| `getProperty(key)` | Đọc property dưới dạng String |
| `getProperty(key, TargetType.class)` | Đọc và chuyển đổi sang kiểu đích |
| `getProperty(key, defaultValue)` | Dùng giá trị mặc định khi không có giá trị phân giải được |
| `getRequiredProperty(key)` | Đọc property bắt buộc; ném lỗi nếu không có giá trị |
| `containsProperty(key)` | Kiểm tra property có giá trị có thể phân giải trong Environment |
| `getActiveProfiles()` | Lấy các profile đang active |
| `acceptsProfiles(...)` | Kiểm tra điều kiện profile theo API phiên bản đang dùng |

Ví dụ đọc kiểu dữ liệu trực tiếp:

~~~java
Duration timeout = environment.getProperty(
        "catalog.client.read-timeout",
        Duration.class,
        Duration.ofSeconds(3));

Integer poolSize = environment.getProperty(
        "catalog.client.pool-size",
        Integer.class);
~~~

Cách này hữu ích khi tên key được quyết định động hoặc khi một thành phần cần đọc một số giá trị rời rạc. Nếu cần một nhóm thuộc tính, hãy cân nhắc binding thành object thay vì tự viết nhiều lệnh `getProperty`.

### 3.2. Phân biệt thiếu, null và chuỗi rỗng

`Environment.getProperty` trả về null nếu không có giá trị phù hợp để phân giải. Chuỗi rỗng là một giá trị String có mặt và khác null. Do đó:

~~~java
String label = environment.getProperty("notification.label");

if (label == null) {
    // Không có giá trị có thể phân giải.
} else if (label.isEmpty()) {
    // Có giá trị, nhưng là chuỗi rỗng.
} else if (label.isBlank()) {
    // Chỉ có whitespace.
} else {
    // Có nội dung.
}
~~~

`containsProperty` không giúp phân biệt mọi trạng thái nguồn như absent và YAML null. Nó trả lời việc Environment có property có thể phân giải hay không theo cách tra cứu của Spring. Nếu cần điều tra nguồn nào cung cấp giá trị, hãy kiểm tra từng PropertySource/origin; đừng suy luận chỉ từ một lần gọi `getProperty`.

### 3.3. Environment không tự bind và validate một nhóm cấu hình

`Environment` cho phép truy cập property linh hoạt, nhưng code phải tự xử lý việc đọc từng key, giá trị mặc định, chuyển đổi và validation. Ví dụ, nếu có năm thuộc tính client, năm lần tra cứu không tự tạo thành một schema cấu hình thống nhất.

Có thể dùng `Environment` để chọn namespace theo tenant hoặc service ID, nhưng phải kiểm soát tên key và xác thực kết quả. Không ghép tên property từ dữ liệu không tin cậy rồi dùng nó để truy cập các key nhạy cảm.

## 4. Dùng @ConfigurationProperties cho cấu hình có cấu trúc

`@ConfigurationProperties` bind một nhóm property có cùng prefix thành object Java. Đây thường là lựa chọn phù hợp cho cấu hình client, connection pool, discovery, timeout, retry hoặc các nhóm thuộc tính có quan hệ với nhau.

Ví dụ YAML:

~~~yaml
catalog:
  client:
    enabled: true
    base-url: "https://catalog.internal"
    connect-timeout: 1s
    read-timeout: 3s
    max-attempts: 3
    supported-regions:
      - north
      - south
~~~

Record cấu hình:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        boolean enabled,
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout,
        int maxAttempts,
        List<String> supportedRegions
) {}
~~~

Spring Boot binder ánh xạ các key bên dưới prefix `catalog.client` vào tham số tương ứng. Các tên dạng kebab-case như `base-url` và `connect-timeout` có thể bind vào tên Java camelCase như `baseUrl` và `connectTimeout` nhờ relaxed binding.

Record giúp mô tả cấu hình bất biến sau khi được tạo. Ví dụ này dùng constructor binding được Spring Boot hỗ trợ cho record trong các phiên bản hiện đại; với ứng dụng dùng phiên bản cũ hơn, cần theo hướng dẫn constructor binding của đúng phiên bản Boot.

### 4.1. Đăng ký bean cấu hình

Có thể dùng `@ConfigurationPropertiesScan` trên lớp ứng dụng:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
}
~~~

Hoặc đăng ký tường minh:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogClientConfiguration {
}
~~~

Chọn một cách đăng ký rõ ràng và bảo đảm class cấu hình nằm trong phạm vi scan phù hợp. Nếu không đăng ký, chỉ thêm annotation `@ConfigurationProperties` trên class chưa chắc đã khiến bean được tạo trong mọi cấu hình ứng dụng.

### 4.2. Nested properties, list và map

Cấu hình có thể có cấu trúc sâu:

~~~yaml
catalog:
  client:
    base-url: "https://catalog.internal"
    headers:
      x-client-name: "order-service"
      x-region: "ap-southeast"
    retry:
      max-attempts: 3
      backoff: 250ms
    endpoints:
      - name: products
        path: /api/products
      - name: categories
        path: /api/categories
~~~

Nếu cấu hình cần object lồng nhau thay vì một record phẳng, có thể dùng một kiểu cấu hình khác như dưới đây. Đây là một mô hình thay thế cho record `CatalogClientProperties` ở trên; không đăng ký cả hai kiểu cùng prefix nếu chúng cùng đại diện cho một nhóm cấu hình.

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.client")
public record NestedCatalogClientProperties(
        URI baseUrl,
        Map<String, String> headers,
        Retry retry,
        List<Endpoint> endpoints
) {
    public record Retry(int maxAttempts, Duration backoff) {}
    public record Endpoint(String name, String path) {}
}
~~~

Với cấu hình thực tế, nên xác định rõ field bắt buộc, giá trị mặc định và giới hạn hợp lệ. Nếu dữ liệu từ remote config có thể thiếu hoặc sai kiểu, validation giúp phát hiện sớm thay vì để lỗi xuất hiện trong request.

### 4.3. Conversion cho kiểu dữ liệu phổ biến

Spring Boot hỗ trợ chuyển đổi nhiều kiểu thường gặp:

| Kiểu Java | Ví dụ giá trị cấu hình | Ý nghĩa |
| --- | --- | --- |
| `Duration` | `500ms`, `5s`, `2m` | Thời lượng |
| `DataSize` | `512KB`, `16MB` | Dung lượng |
| `URI` / `URL` | `https://catalog.internal` | Địa chỉ |
| `List<T>` | Các phần tử YAML dạng list | Danh sách |
| `Map<K,V>` | Nhóm key/value lồng nhau | Bản đồ thuộc tính |
| Enum | `ROUND_ROBIN` | Hằng số theo kiểu |

Đối với thời lượng hoặc dung lượng, nên dùng kiểu chuyên biệt thay vì tự đọc số nguyên rồi tự quy ước đơn vị. Nếu cần quy định đơn vị mặc định hoặc giới hạn, cấu hình annotation và validation tương ứng theo phiên bản Spring Boot.

## 5. Validation cho cấu hình có kiểu

Cấu hình sai có thể khiến ứng dụng gọi sai endpoint, tạo connection pool quá lớn hoặc retry không giới hạn. Validation giúp từ chối cấu hình không hợp lệ ngay trong quá trình khởi tạo.

Ví dụ:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.AssertTrue;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.client")
public record ValidatedCatalogClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(1) @Max(5) int maxAttempts
) {
    @AssertTrue(message = "connectTimeout must be positive")
    public boolean isConnectTimeoutPositive() {
        return connectTimeout != null
                && !connectTimeout.isZero()
                && !connectTimeout.isNegative();
    }

    @AssertTrue(message = "readTimeout must be positive")
    public boolean isReadTimeoutPositive() {
        return readTimeout != null
                && !readTimeout.isZero()
                && !readTimeout.isNegative();
    }
}
~~~

Cần có dependency validation tương thích để các constraint được thực thi. Trong ví dụ này, `@AssertTrue` kiểm tra `Duration` dương vì constraint `@Positive` chuẩn dành cho kiểu số, không áp dụng trực tiếp cho `Duration`. Với Spring Boot 3, các annotation validation thường thuộc namespace `jakarta.validation`; các dự án Boot 2 có thể dùng namespace `javax.validation` tùy phiên bản. Không trộn hai namespace trong cùng cấu hình.

Một số constraint thường gặp:

| Constraint | Điều kiện |
| --- | --- |
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | Chuỗi không null, không rỗng và không chỉ có whitespace |
| `@NotEmpty` | Chuỗi/collection không null và không rỗng |
| `@Positive` | Số lớn hơn 0 |
| `@Min` / `@Max` | Giới hạn số tối thiểu/tối đa |
| `@Pattern` | Chuỗi phải khớp biểu thức chính quy |

Nếu một nested object có constraint riêng, có thể dùng `@Valid` để yêu cầu validation đi sâu vào object con. Hãy phân biệt validation của cấu hình với validation của request nghiệp vụ: chúng chạy ở những thời điểm và phục vụ những mục tiêu khác nhau.

## 6. So sánh qua cùng một ví dụ

Giả sử `order-service` cần timeout để gọi `catalog-service`.

### 6.1. Dùng @Value

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class CatalogTimeoutWithValue {

    private final Duration readTimeout;

    public CatalogTimeoutWithValue(
            @Value("${catalog.client.read-timeout:3s}")
            Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

Phù hợp khi bean chỉ cần một giá trị và không có nhóm cấu hình đi kèm.

### 6.2. Dùng Environment

~~~java
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CatalogTimeoutWithEnvironment {

    private final Environment environment;

    public CatalogTimeoutWithEnvironment(Environment environment) {
        this.environment = environment;
    }

    public Duration readTimeoutFor(String clientName) {
        String key = "clients." + clientName + ".read-timeout";
        return environment.getProperty(
                key, Duration.class, Duration.ofSeconds(3));
    }
}
~~~

Phù hợp khi key được chọn trong lúc chạy, ví dụ client name đến từ một registry nội bộ. Cần giới hạn tập client/key hợp lệ và kiểm thử logic chọn tên.

### 6.3. Dùng @ConfigurationProperties

~~~java
@ConfigurationProperties(prefix = "catalog.client")
public record CatalogTimeoutProperties(
        Duration readTimeout,
        Duration connectTimeout,
        int maxAttempts
) {}
~~~

Phù hợp khi các thuộc tính cùng mô tả một client và được nhiều bean sử dụng. Bean có thể được inject qua constructor, kiểm thử độc lập và validation tập trung.

### 6.4. Bảng chọn nhanh

| Nhu cầu | Nên bắt đầu bằng | Lý do |
| --- | --- | --- |
| Một cờ hoặc một tên đơn giản trong bean | `@Value` | Ngắn, rõ, ít cấu trúc |
| Đọc key được xác định động | `Environment` | Tên property chỉ biết khi code chạy |
| Lấy một nhóm thuộc tính có cùng prefix | `@ConfigurationProperties` | Typed binding và gom cấu hình |
| Cần validation nhiều trường | `@ConfigurationProperties` | Có thể gắn constraint ở cấp object |
| Cần nested object, list, map | `@ConfigurationProperties` | Hỗ trợ binding cấu trúc |
| Kiểm tra profile hoặc property source | `Environment` | API cung cấp thông tin môi trường |
| Dùng biểu thức SpEL cố định | `@Value` | Hỗ trợ expression |
| Muốn cấu hình có metadata cho IDE | `@ConfigurationProperties` | Có thể sinh configuration metadata |

Không có quy tắc bắt buộc mọi ứng dụng chỉ được dùng một cơ chế. Một ứng dụng có thể dùng `@ConfigurationProperties` cho nhóm client, `@Value` cho một cờ đơn lẻ và `Environment` cho một trường hợp tra cứu động. Điều quan trọng là mỗi cách dùng có mục đích rõ ràng và không tạo ra nhiều nguồn sự thật cho cùng một thuộc tính.

## 7. Nguồn cấu hình và thứ tự ưu tiên vẫn áp dụng cho cả ba

Dù dùng `@Value`, `Environment` hay `@ConfigurationProperties`, giá trị được đọc vẫn phụ thuộc vào nguồn cấu hình đang hoạt động. Ví dụ:

- `application.yml` cung cấp timeout mặc định.
- `application-production.yml` ghi đè timeout cho production.
- Biến môi trường ghi đè giá trị theo cấu hình triển khai.
- Tham số dòng lệnh có thể có ưu tiên cao hơn trong lần chạy cụ thể.
- Spring Cloud Config hoặc custom property source có thể bổ sung cấu hình từ xa.

Ví dụ:

~~~yaml
catalog:
  client:
    read-timeout: 3s
~~~

Ở production:

~~~yaml
catalog:
  client:
    read-timeout: 1500ms
~~~

Nếu biến môi trường `CATALOG_CLIENT_READTIMEOUT` cũng được cung cấp, giá trị cuối cùng phụ thuộc thứ tự ưu tiên property source. Các cách đọc cấu hình không tự chọn nguồn khác nhau; chúng nhìn vào Environment hoặc binder đã tổng hợp các nguồn đó.

Đừng đặt cùng một property ở quá nhiều nơi nếu không có lý do. Khi có xung đột, cần biết giá trị cuối cùng và nguồn cung cấp nó. Actuator `env`/`configprops` có thể hỗ trợ chẩn đoán nếu được expose và bảo vệ an toàn.

## 8. Cấu hình kiểu dữ liệu trong ứng dụng Spring Cloud

Các thuộc tính của Spring Cloud thường là nhóm cấu hình có quan hệ:

~~~yaml
spring:
  application:
    name: order-service

catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 1s
    read-timeout: 3s
    max-attempts: 2

discovery:
  client:
    prefer-same-zone: true
    zone: ap-southeast
~~~

Có thể dùng `@ConfigurationProperties` để bind nhóm do ứng dụng sở hữu như `catalog.client`. Các thuộc tính chuẩn của Spring Boot/Spring Cloud vẫn phải tuân thủ đúng prefix và kiểu mà thư viện định nghĩa. Không tự đặt tên key rồi giả định một starter sẽ tự đọc chúng.

### 8.1. Không nhầm typed configuration với refresh

`@ConfigurationProperties` giải quyết **cách bind dữ liệu có cấu trúc**. Nó không tự làm cấu hình thay đổi ngay khi file hoặc Config Server được cập nhật.

Trong Spring Cloud Context, `@RefreshScope` và cơ chế refresh có thể giúp một số bean được tạo lại sau khi Environment được làm mới. Nhưng phải xem bean nào được refresh, property source nào đã được cập nhật và client/kết nối nào cần tái tạo. Dùng typed configuration không tự bật refresh.

### 8.2. Cẩn thận với giá trị bí mật

Cấu hình có kiểu có thể chứa URI, username hoặc các tham số kết nối, nhưng không nên lưu secret vào file cấu hình được commit. Hãy lấy credential từ secret manager, biến môi trường hoặc file secret được mount. Không expose secret qua log, Actuator hoặc exception message.

## 9. Kiểm thử từng cơ chế

Kiểm thử nên xác nhận cả giá trị được đọc lẫn hành vi khi thiếu hoặc sai cấu hình.

### 9.1. Kiểm thử @ConfigurationProperties

`ApplicationContextRunner` cho phép dựng một Spring context nhỏ với property riêng:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsTypedValues() {
        runner.withPropertyValues(
                "catalog.client.read-timeout=1500ms",
                "catalog.client.max-attempts=2")
            .run(context -> {
                CatalogClientProperties properties =
                        context.getBean(CatalogClientProperties.class);

                assertThat(properties.readTimeout())
                        .isEqualTo(Duration.ofMillis(1500));
                assertThat(properties.maxAttempts()).isEqualTo(2);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogClientProperties.class)
    static class TestConfig {
    }
}
~~~

Test này không cần khởi động toàn bộ ứng dụng hoặc kết nối Config Server. Nó tập trung xác nhận binder chuyển giá trị thành đúng kiểu. Nếu class cấu hình có validation, có thể thêm test với giá trị không hợp lệ và xác nhận context báo lỗi.

### 9.2. Kiểm thử @Value

Dùng `@SpringBootTest(properties = ...)` hoặc một context nhỏ để cung cấp property test. Kiểm tra cả trường hợp có giá trị, thiếu key có fallback và chuỗi rỗng nếu nghiệp vụ cho phép. Không chỉ kiểm tra happy path.

### 9.3. Kiểm thử Environment

Có thể dùng `MockEnvironment` trong unit test cho thành phần chỉ cần đọc property:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class EndpointResolverTest {

    @Test
    void readsEndpointByDynamicKey() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty(
                        "services.catalog.base-url",
                        "https://catalog.test");

        String endpoint = environment.getProperty(
                "services.catalog.base-url");

        assertThat(endpoint).isEqualTo("https://catalog.test");
    }
}
~~~

Nếu code cần chọn key động, hãy kiểm thử cả tên key không hợp lệ, thiếu property và giá trị rỗng. Test này không chứng minh profile, Config Data hoặc remote Config Server đã được cấu hình đúng; những luồng đó cần integration test riêng.

## 10. Các lỗi thường gặp và cách tránh

1. **Dùng quá nhiều `@Value`:** constructor và class trở nên dài, khó quản lý; gom nhóm thuộc tính bằng `@ConfigurationProperties`.
2. **Dùng `Environment` cho mọi cấu hình:** code phải tự đọc và validate nhiều key; chỉ dùng khi thực sự cần truy cập động hoặc thao tác với Environment.
3. **Quên đăng ký `@ConfigurationProperties`:** kiểm tra `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
4. **Sai prefix hoặc tên key:** kiểm tra prefix, kebab-case và cấu trúc YAML; dùng test binding.
5. **Dùng primitive khi cần phân biệt thiếu với false/zero:** dùng wrapper hoặc quy tắc mặc định rõ ràng.
6. **Không validate URL/timeout/retry:** thêm constraint và kiểm thử cấu hình sai ngay khi khởi động.
7. **Cho rằng mọi chuỗi rỗng đều là thiếu:** kiểm tra null, empty và blank theo semantics nghiệp vụ.
8. **Dùng SpEL không cần thiết:** ưu tiên placeholder đơn giản; chỉ dùng expression cố định khi thực sự cần.
9. **Cho rằng typed binding tự refresh:** xác định riêng cơ chế refresh và vòng đời bean.
10. **Nhầm property tự định nghĩa với property của starter:** chỉ key được code hoặc thư viện đọc mới có tác dụng.

## 11. Quy trình chọn và triển khai

Khi thêm cấu hình cho một thành phần trong Spring Cloud, có thể thực hiện theo thứ tự:

1. Xác định dữ liệu là một thuộc tính đơn, một nhóm có cấu trúc hay một key được xác định động.
2. Dùng `@Value` cho một vài giá trị đơn giản; dùng `Environment` khi cần tra cứu động; dùng `@ConfigurationProperties` cho nhóm cấu hình.
3. Định nghĩa kiểu dữ liệu rõ ràng như `Duration`, `URI`, `DataSize`, enum, list hoặc nested record.
4. Đăng ký bean cấu hình và thêm validation cho giá trị bắt buộc.
5. Xác định nguồn cấu hình, profile và thứ tự ưu tiên cho local/test/production.
6. Không commit secret; dùng nguồn secret phù hợp.
7. Viết test binding, fallback, giá trị rỗng và cấu hình không hợp lệ.
8. Nếu cần refresh runtime, thiết kế riêng cơ chế refresh và kiểm tra bean/client được tạo lại.
9. Kiểm tra phiên bản Spring Boot/Spring Cloud và dependency tương thích.

**Điểm ghi nhớ:** `@Value` phù hợp với vài giá trị đơn giản; `Environment` phù hợp với truy vấn property linh hoạt khi key được quyết định lúc chạy; `@ConfigurationProperties` phù hợp với một nhóm cấu hình có kiểu, cấu trúc và validation. Cả ba cùng dựa trên nguồn cấu hình của Spring, vì vậy vẫn tuân theo profile, property source precedence và vòng đời nạp cấu hình. Chọn cơ chế theo hình dạng dữ liệu và nhu cầu kiểm soát sẽ giúp cấu hình Spring Cloud rõ ràng, dễ kiểm thử và dễ vận hành.
