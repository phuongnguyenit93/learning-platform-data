# Xây hợp đồng cấu hình: tên khóa, kiểu, đơn vị, mặc định và ràng buộc trong Spring Boot

## 1. Cấu hình là một API của hệ thống

Một ứng dụng Spring Boot có thể đọc thông số từ `application.yml`, `application.properties`, biến môi trường, JVM system properties, command-line arguments, Config Data import và các nguồn khác. Nhờ vậy, cùng một artifact có thể chạy ở development, staging và production.

Nhưng các khóa cấu hình không chỉ là biến nội bộ. Chúng là một **hợp đồng giữa người viết ứng dụng, người vận hành và hệ thống triển khai**. Khi một khóa được đưa vào Helm chart, Docker Compose, secret manager, CI/CD hoặc tài liệu của đối tác, đổi tên hay đổi nghĩa của nó có thể gây lỗi tương tự như thay đổi một public Java API.

Ví dụ:

~~~yaml
acme:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test
    connect-timeout: 5s
    max-retries: 3
    buffer-size: 2MB
~~~

Để gọi đây là hợp đồng, ứng dụng phải trả lời rõ:

- `connect-timeout: 5` có nghĩa 5 mili giây hay 5 giây?
- `buffer-size: 2` là 2 byte hay 2 megabyte?
- Không khai báo `max-retries` có mặc định không?
- `endpoint` có bắt buộc khi `enabled=false` không?
- Có cho phép HTTP hay chỉ HTTPS?
- `max-retries=-1` là bị cấm hay là ký hiệu cho retry vô hạn?
- Những khóa nào chứa secret và không được log?
- Khi có cả file và env var cùng key, nguồn nào thắng?
- Nếu đổi tên một khóa, deployment hiện có được hỗ trợ tới khi nào?

Một cấu hình thiếu mô tả có thể **bind thành công về kiểu** nhưng gây hành vi nguy hiểm: retry quá nhiều, timeout quá ngắn, cấp bộ đệm quá lớn hoặc kết nối nhầm môi trường.

> **Hợp đồng cấu hình** = tên khóa ổn định + kiểu dữ liệu + đơn vị + giá trị mặc định/tính bắt buộc + giới hạn hợp lệ + precedence + bảo mật + quy tắc nâng cấp.

Các ví dụ Java hướng tới Spring Boot 3.x, Java 17+ và `jakarta.validation`. Với phiên bản khác, cần đối chiếu API của BOM đang sử dụng.

## 2. Mẫu đặc tả một khóa

Một bảng contract tối thiểu:

| Trường | Điều cần ghi |
| --- | --- |
| Tên chuẩn | Key canonical theo kebab-case |
| Prefix | Module nào sở hữu key |
| Ý nghĩa | Dùng trong hành vi nào |
| Java type | `boolean`, `Duration`, `DataSize`, `URI`, `int`, enum, collection |
| Đơn vị | `ms`/`s`, `B`/`KB`/`MB`; nếu không hậu tố thì hiểu gì |
| Giá trị mặc định | Khi hoàn toàn thiếu key, đối tượng nhận gì |
| Required | Bắt buộc luôn hay chỉ trong một điều kiện |
| Miền hợp lệ | Min, max, regex, scheme, quan hệ với key khác |
| Nguồn cho phép | YAML, env, secret, CLI; cách override |
| Mức nhạy cảm | Public, internal, secret |
| Tương thích | Tên legacy, deprecated, replacement và version |
| Test | Missing, invalid, override, legacy và edge cases |

Ví dụ cho một module gửi dữ liệu:

| Khóa | Kiểu/đơn vị | Default | Quy tắc |
| --- | --- | --- | --- |
| `acme.delivery.enabled` | Boolean | `false` | Chỉ bật khi operator chọn |
| `acme.delivery.endpoint` | URI | Không có | Bắt buộc khi bật, HTTPS absolute URI có host |
| `acme.delivery.connect-timeout` | Duration | `5s` | Lớn hơn 0, tối đa `30s` |
| `acme.delivery.max-retries` | int | `3` | Từ 0 đến 10 |
| `acme.delivery.buffer-size` | DataSize | `2MB` | Từ `64KB` tới `64MB` |
| `acme.delivery.security.api-key-enabled` | Boolean | `false` | Bật cơ chế API key |
| `acme.delivery.security.api-key` | String/secret | Không có | Bắt buộc nếu enabled và API-key auth enabled |

Đây là **contract do ứng dụng tự thiết kế**, không phải tập khóa built-in của Spring Boot.

## 3. Quy ước tên khóa: kebab-case và namespace

Spring Boot khuyến nghị canonical form dùng chữ thường và dấu gạch ngang giữa các từ trong một segment:

~~~properties
acme.delivery.connect-timeout=5s
acme.delivery.max-retries=3
acme.delivery.buffer-size=2MB
~~~

Nên:

1. Dùng prefix riêng của ứng dụng hoặc module: `acme.delivery`.
2. Đặt tên theo ý nghĩa: `connect-timeout`, không chỉ `timeout` nếu có nhiều loại timeout.
3. Dùng một tên chuẩn công bố cho operator.
4. Tránh tên dựa vào class nội bộ hoặc môi trường cụ thể như `prod-timeout`.
5. Giữ các segment nhất quán, ví dụ `max-retries` thay vì xen kẽ `retryMax` và `max_retry`.
6. Không chiếm prefix `spring.*` cho khóa nghiệp vụ của ứng dụng.
7. Coi một key đã công bố là API cần quản lý vòng đời.

Một bảng namespace minh họa:

~~~text
acme.delivery.*   — gửi dữ liệu đến đối tác
acme.catalog.*    — đồng bộ sản phẩm
acme.cache.*      — caching nghiệp vụ
acme.audit.*      — ghi nhật ký kiểm toán
~~~

Tránh một key chung `app.timeout` mà ba team dùng với ba ý nghĩa.

### 3.1. Field Java khác tên key canonical

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
public record DeliveryProperties(Duration connectTimeout) {
}
~~~

~~~yaml
acme:
  delivery:
    connect-timeout: 5s
~~~

Java dùng camelCase cho field/component, YAML công bố kebab-case. Spring Boot relaxed binding kết nối hai hình thức; không cần ghi Java field bằng tên có dấu gạch ngang.

### 3.2. Mapping tới OS environment variables

Theo quy tắc môi trường cho `@ConfigurationProperties`:

- Dấu chấm `.` được thay bằng dấu gạch dưới.
- Dấu gạch ngang `-` bị **loại bỏ**.
- Chữ được chuyển sang uppercase.

Ví dụ:

~~~text
acme.delivery.enabled          → ACME_DELIVERY_ENABLED
acme.delivery.connect-timeout  → ACME_DELIVERY_CONNECTTIMEOUT
acme.delivery.max-retries      → ACME_DELIVERY_MAXRETRIES
acme.delivery.buffer-size      → ACME_DELIVERY_BUFFERSIZE
~~~

Không nên tùy tiện khẳng định `ACME_DELIVERY_CONNECT_TIMEOUT` cũng được bind chính xác như `ACME_DELIVERY_CONNECTTIMEOUT` trong mọi trường hợp. Viết rõ dạng đã được Spring Boot quy định trong tài liệu triển khai.

Khi dùng placeholders hoặc `@Value`, ưu tiên tên canonical:

~~~java
@Value("${acme.delivery.connect-timeout:5s}")
private Duration connectTimeout;
~~~

Nhưng với nhiều thuộc tính cùng nhóm, `@ConfigurationProperties` thường dễ kiểm tra hơn việc rải hàng chục `@Value` trong services.

## 4. Kiểu Java thể hiện ý nghĩa thay vì chỉ chứa String

Đừng chọn `String` cho mọi giá trị rồi tự parse tại mỗi consumer.

| Ý nghĩa | Type đề xuất | Ví dụ cấu hình |
| --- | --- | --- |
| Bật/tắt | `boolean`, `Boolean` | `true` |
| Số lần thử | `int`, `Integer` | `3` |
| Số lượng lớn | `long` | `1000000` |
| Timeout | `java.time.Duration` | `750ms`, `5s` |
| Dung lượng | `DataSize` | `512KB`, `2MB` |
| URI endpoint | `java.net.URI` | `https://api.example.test` |
| Lựa chọn đóng | `enum` | `SYNC`, `ASYNC` |
| Danh sách giữ thứ tự | `List<T>` | YAML sequence |
| Tra cứu theo tên | `Map<String,T>` | YAML map |
| Credential | Secret value/`String` | Cấp từ secret store |

### 4.1. Primitive vs wrapper và trường hợp thiếu property

~~~java
private int retries;
~~~

`int` có Java default là 0; nếu key thiếu, giá trị này có thể che đi việc chưa được cấu hình.

~~~java
@NotNull
private Integer retries;
~~~

Với `Integer` không có initializer, `null` cho phép kiểm tra “không khai báo”. Nếu 0 là default hợp lệ và có chủ đích, hãy công bố nó. Nếu key phải có, dùng nullable type và validation phù hợp.

### 4.2. Enum là một hợp đồng có version

~~~java
public enum DeliveryMode {
    DISABLED,
    ASYNC,
    SYNC
}
~~~

Chọn enum khi tập giá trị thực sự đóng. Đổi tên enum constant có thể làm input cũ không bind; nếu thay tên, cần compatibility layer hoặc migration. Một tập giá trị thay đổi liên tục có thể không phù hợp với enum.

## 5. Duration: công bố đơn vị, không phụ thuộc số trần

Một property `Duration` trong Spring Boot hiểu số nguyên không có hậu tố theo **mili giây** theo mặc định, trừ khi metadata `@DurationUnit` chỉ định đơn vị khác.

~~~properties
acme.delivery.connect-timeout=5
~~~

Nếu không có annotation đổi đơn vị, đây là **5ms**, không phải 5s.

Viết rõ:

~~~properties
acme.delivery.connect-timeout=5s
~~~

Các hậu tố được Spring Boot hỗ trợ gồm:

| Hậu tố | Nghĩa |
| --- | --- |
| `ns` | Nanoseconds |
| `us` | Microseconds |
| `ms` | Milliseconds |
| `s` | Seconds |
| `m` | Minutes |
| `h` | Hours |
| `d` | Days |

Có thể dùng ISO-8601 như `PT5S`. Với người vận hành, `5s` thường dễ đọc hơn.

Đổi default unit của giá trị **không có hậu tố**:

~~~java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.convert.DurationUnit;

@DurationUnit(ChronoUnit.SECONDS)
private Duration connectTimeout;
~~~

Khi đó `connect-timeout: 5` được hiểu là 5 giây. Nhưng nếu property **không tồn tại**, annotation không tự tạo giá trị 5 giây; nó chỉ mô tả **đơn vị**, không phải default.

Khuyến nghị contract: các ví dụ triển khai mới luôn viết hậu tố tường minh. Nếu nâng từ một field `long` đơn vị giây sang `Duration`, dùng `@DurationUnit(SECONDS)` khi cần giữ ý nghĩa giá trị số trần cũ.

## 6. DataSize: công bố hệ đơn vị và giới hạn

Spring Boot hỗ trợ `org.springframework.util.unit.DataSize` để biểu diễn dung lượng byte.

~~~properties
acme.delivery.buffer-size=2MB
~~~

| Đơn vị | Hậu tố | Số byte |
| --- | --- | ---: |
| Byte | `B` | 1 |
| Kilobyte | `KB` | 1.024 |
| Megabyte | `MB` | 1.048.576 |
| Gigabyte | `GB` | 1.073.741.824 |
| Terabyte | `TB` | 1.099.511.627.776 |

Các hậu tố trên trong `DataSize` dùng quy ước nhị phân (1024), không phải mặc nhiên `1MB=1.000.000B`.

~~~java
DataSize size = DataSize.ofMegabytes(2);
long bytes = size.toBytes();  // 2097152
~~~

Số trần không có suffix mặc định là **byte**:

~~~yaml
acme:
  delivery:
    buffer-size: 2
~~~

Nếu không có metadata khác, đây là 2 byte, không phải 2MB.

Có thể định nghĩa đơn vị mặc định:

~~~java
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataUnit;

@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize bufferSize;
~~~

Khi đó `buffer-size: 2` được diễn giải là 2MB, còn `buffer-size: 512KB` vẫn là 512KB vì có suffix tường minh.

**Không nhầm đơn vị với default:** `@DataSizeUnit(MEGABYTES)` không biến một field bị thiếu thành 1MB hoặc 2MB. Muốn default phải khai báo initializer hoặc `@DefaultValue`.

### 6.1. Giới hạn khác type conversion

`DataSize.ofBytes(0)` và giá trị âm có thể được biểu diễn, nhưng ứng dụng có thể yêu cầu buffer tối thiểu 64KB. Conversion thành công **không đồng nghĩa** cấu hình hợp lệ; phải thêm validation.

## 7. Bắt buộc, tùy chọn và default là ba chính sách khác nhau

Một khóa có thể được thiết kế là:

- **Required**: thiếu thì fail startup.
- **Optional + safe default**: thiếu thì dùng default có chủ đích.
- **Optional + absent means disabled**: thiếu mang ý nghĩa “không sử dụng”.
- **Conditionally required**: ví dụ endpoint bắt buộc nếu tính năng enabled.
- **Mutually constrained**: ví dụ retry và timeout kết hợp không được vượt một ngân sách thời gian.

Ví dụ:

| Key | Chính sách | Lý do |
| --- | --- | --- |
| `enabled` | Default false | Không tự bật tích hợp ngoài |
| `connect-timeout` | Default 5s | Có giới hạn chờ hữu hạn |
| `max-retries` | Default 3 | Tránh retry vô hạn |
| `buffer-size` | Default 2MB | Dễ dự đoán tài nguyên |
| `endpoint` | Required khi enabled | Không thể gửi nếu không có đích |
| `security.api-key` | Required khi auth enabled | Không có fallback secret |

### 7.1. Default ở JavaBean initializer

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
public class DeliveryProperties {
    private Duration connectTimeout = Duration.ofSeconds(5);
    private int maxRetries = 3;

    // getters/setters
}
~~~

Khi binder không nhận override, initializer cung cấp giá trị. Nếu có property hợp lệ từ môi trường, binder có thể ghi đè theo property nguồn thắng.

### 7.2. Default ở constructor/record binding

Trong Spring Boot 3.x:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import java.time.Duration;

@ConfigurationProperties(prefix = "acme.delivery")
public record DeliveryProperties(
    @DefaultValue("5s") Duration connectTimeout,
    @DefaultValue("3") int maxRetries) {
}
~~~

`@DefaultValue("5s")` được chuyển sang kiểu `Duration` khi value không được cung cấp. Nó khác `@DurationUnit(SECONDS)` vốn chỉ đổi cách diễn giải số trần **đã hiện diện**.

### 7.3. Default trong object không tự xuất hiện trong Environment

Giả sử record có default `5s` nhưng không có property `acme.delivery.connect-timeout` trong nguồn nào.

~~~java
DeliveryProperties props = ...; // được bind
Duration configured = props.connectTimeout(); // PT5S

String raw = environment.getProperty(
        "acme.delivery.connect-timeout"); // có thể null
~~~

Spring Boot không tự ghi default của configuration object ngược thành một PropertySource. Điều này quan trọng khi một `@ConditionalOnProperty` hoặc thành phần khác đọc trực tiếp `Environment`.

Nếu các component cần cùng một default, ưu tiên inject chung properties bean, hoặc cấp default qua nguồn cấu hình thích hợp với contract. Không có lý do để giả định getter của Environment sẽ tự trả `@DefaultValue`.

## 8. Mẫu đầy đủ bằng `@ConfigurationProperties` record

Thiết kế một model cho module delivery:

~~~java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.util.unit.DataSize;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.delivery")
public record DeliveryProperties(
        @DefaultValue("false") boolean enabled,
        URI endpoint,
        @NotNull @DefaultValue("5s") Duration connectTimeout,
        @Min(0) @Max(10) @DefaultValue("3") int maxRetries,
        @NotNull @DefaultValue("2MB") DataSize bufferSize,
        @Valid @DefaultValue Security security) {

    public record Security(
            @DefaultValue("false") boolean apiKeyEnabled,
            String apiKey) {
    }
}
~~~

Giải thích:

- `enabled` tắt mặc định.
- `endpoint` có thể null, vì contract chỉ yêu cầu nó khi enabled=true.
- `connectTimeout` mặc định 5s và không null.
- `maxRetries` giới hạn 0–10 bằng Bean Validation.
- `bufferSize` mặc định 2MB; giới hạn min/max cần custom rule.
- `Security` là nested record; `@Valid` cho phép cascade constraints trong nested object.
- `@DefaultValue` không có đối số trên nested component cho phép tạo instance từ defaults nếu không có section tương ứng.

Đăng ký trong ứng dụng:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DeliveryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DeliveryApplication.class, args);
    }
}
~~~

Hoặc đăng ký tường minh bằng `@EnableConfigurationProperties(DeliveryProperties.class)` trong một class cấu hình được scan.

### 8.1. Mẫu YAML

~~~yaml
acme:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test
    connect-timeout: 5s
    max-retries: 3
    buffer-size: 2MB
    security:
      api-key-enabled: true
      api-key: "${DELIVERY_API_KEY}"
~~~

`DELIVERY_API_KEY` cần được cấp bằng cơ chế môi trường/secret phù hợp. Không lưu API key thật vào file ví dụ.

## 9. Binding, conversion và semantic validation

Một contract cần phân biệt ba tầng:

| Tầng | Lỗi mẫu | Nơi được phát hiện |
| --- | --- | --- |
| Cú pháp Config Data | YAML indent không hợp lệ | Parser |
| Type conversion | `connect-timeout: abc` | Binder/Converter |
| Rule nghiệp vụ | `connect-timeout: 0s`, `max-retries: 99` | Validator |

Vì `Duration.ZERO` là một Duration hợp lệ, conversion không thể tự quyết định nó có được chấp nhận làm timeout mạng hay không.

### 9.1. Jakarta Bean Validation

Spring Boot 3.x sử dụng `jakarta.validation.*` khi có Bean Validation implementation phù hợp, thường qua:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Ví dụ:

~~~java
@Min(0) @Max(10) int maxRetries
@NotNull Duration connectTimeout
~~~

Nếu người vận hành đặt `max-retries=99`, ứng dụng có thể fail khi tạo configuration properties bean thay vì bắt đầu xử lý request với retry count vô lý.

Nhưng `@NotNull Duration` không yêu cầu Duration dương. `@NotNull URI` cũng không yêu cầu URI phải có scheme HTTPS và host. Cần logic bổ sung.

## 10. Cross-field rule và custom Spring Validator

Hợp đồng ví dụ:

~~~text
if enabled=false:
    endpoint có thể vắng mặt

if enabled=true:
    endpoint phải là absolute HTTPS URI có host

if enabled=true and security.api-key-enabled=true:
    security.api-key không được null/blank

always:
    timeout > 0 and <= 30s
    buffer-size >= 64KB and <= 64MB
    max-retries from 0 through 10
~~~

Một validator minh họa:

~~~java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import org.springframework.util.unit.DataSize;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class DeliveryPropertiesValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return DeliveryProperties.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        DeliveryProperties props = (DeliveryProperties) target;

        Duration time = props.connectTimeout();
        if (time == null || time.isZero()
                || time.isNegative()
                || time.compareTo(Duration.ofSeconds(30)) > 0) {
            errors.rejectValue("connectTimeout",
                "delivery.timeout.invalid",
                "connect-timeout must be positive and at most 30s");
        }

        DataSize size = props.bufferSize();
        if (size == null
                || size.compareTo(DataSize.ofKilobytes(64)) < 0
                || size.compareTo(DataSize.ofMegabytes(64)) > 0) {
            errors.rejectValue("bufferSize",
                "delivery.buffer.invalid",
                "buffer-size must be between 64KB and 64MB");
        }

        if (props.enabled()) {
            URI endpoint = props.endpoint();
            if (endpoint == null
                    || !endpoint.isAbsolute()
                    || !"https".equalsIgnoreCase(endpoint.getScheme())
                    || endpoint.getHost() == null) {
                errors.rejectValue("endpoint",
                    "delivery.endpoint.invalid",
                    "endpoint must be an absolute HTTPS URI with a host");
            }

            DeliveryProperties.Security security = props.security();
            if (security != null && security.apiKeyEnabled()
                    && (security.apiKey() == null
                        || security.apiKey().isBlank())) {
                errors.rejectValue("security.apiKey",
                    "delivery.security.keyMissing",
                    "security.api-key is required with API-key auth");
            }
        }
    }
}
~~~

Đăng ký dedicated validator với tên bean của Spring Boot:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;

@Configuration(proxyBeanMethods = false)
public class DeliveryValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

Phương thức factory nên là **static** vì Spring Boot có thể cần validator rất sớm trong lifecycle. `supports` phải kiểm tra type để không cast nhầm các `@ConfigurationProperties` bean khác.

Validator dùng `errors.rejectValue(...)` để báo field và lý do. Không in raw secret value. Ngoài Spring Validator, có thể dùng một Jakarta custom constraint ở cấp class nếu codebase chọn cách đó.

Nếu nested `Security` có quy tắc bổ sung, cần xử lý null theo contract, không giả định nested object luôn có mặt trong mọi binding arrangement.

## 11. Không dùng default để che dữ liệu cấu hình sai

Hai trường hợp khác nhau:

~~~text
Không có acme.delivery.max-retries:
  dùng default 3

Có acme.delivery.max-retries=not-a-number:
  lỗi conversion, không thể dùng default 3 như thể key vắng

Có acme.delivery.max-retries=999:
  bind int thành công nhưng vi phạm @Max(10)
~~~

`@DefaultValue` không phải cơ chế tự chữa mọi input hỏng. Khi operator cấp một giá trị sai, hành vi phù hợp cho key quan trọng là báo lỗi rõ ràng, thường fail startup.

Việc im lặng rơi về default có thể dẫn đến ứng dụng chạy **khác mong đợi** mà không có tín hiệu để chẩn đoán.

## 12. PropertySource precedence cũng là một phần hợp đồng

Giả sử có file:

~~~yaml
acme:
  delivery:
    connect-timeout: 5s
~~~

Biến môi trường:

~~~bash
ACME_DELIVERY_CONNECTTIMEOUT=8s
~~~

Tham số dòng lệnh:

~~~bash
java -jar app.jar --acme.delivery.connect-timeout=10s
~~~

Trong chế độ Spring Boot thông thường, CLI có ưu tiên cao hơn OS environment và OS environment cao hơn config data file. Không có một nguồn đặc biệt cao hơn thì giá trị hiệu lực là **10s**.

| Nguồn hiện diện | Giá trị kết quả |
| --- | --- |
| Không có key nào | Default object `5s` |
| File `5s` | `5s` |
| File `5s` và env `8s` | `8s` |
| File `5s`, env `8s`, CLI `10s` | `10s` |

Không gộp chúng bằng phép cộng và không coi default là nguồn có priority cao.

Chú ý thứ tự nguồn có thể được tùy chỉnh hoặc ảnh hưởng bởi test property sources và command-line processing. Hợp đồng nên nói rõ môi trường triển khai được phép override bằng nguồn nào.

### 12.1. Profile và Config Data

Profile-specific files như `application-prod.yml` có precedence trong nhóm Config Data nhưng vẫn có thể bị OS environment, JVM system properties hoặc CLI ghi đè.

Các key bootstrap như `spring.config.name`, `spring.config.location`, `spring.config.additional-location` phải có mặt **sớm** để điều khiển quá trình tìm file, không nên chỉ đặt chúng vào chính file mà chúng được dùng để tìm.

Một template deployment nên ghi rõ profile, vị trí config, tên biến môi trường và policy bắt buộc/tùy chọn đối với file.

## 13. List/Map: contract phải mô tả cách override

Giả sử:

~~~yaml
# application.yml
acme:
  delivery:
    targets:
      - apac
      - eu
    weights:
      apac: 2
      eu: 1
~~~

Profile `prod`:

~~~yaml
# application-prod.yml
acme:
  delivery:
    targets:
      - apac
    weights:
      apac: 3
      us: 1
~~~

Với Spring Boot collection binding thông thường:

- **List** từ nguồn ưu tiên cao hơn thay thế danh sách trước: `targets=[apac]`.
- **Map** có thể gộp các key, lấy key trùng từ nguồn ưu tiên cao hơn: `weights={apac:3,eu:1,us:1}`.

Một operator nghĩ rằng hai List tự nối lại có thể vô tình xóa target. Vì vậy, khi hợp đồng dùng List, hãy ghi rõ “override replaces entire list” và cung cấp ví dụ đầy đủ cho profile.

Với Map, cũng cần chú ý syntax của key chứa ký tự đặc biệt hoặc dấu chấm; khi cần giữ nguyên key, Spring Boot có bracket notation riêng. Đừng thiết kế key tùy ý mà không có test binding.

## 14. Secret có chính sách khác property thông thường

Không đặt một API key production làm default để app “dễ chạy”. Với secret, contract phải phân loại:

- Có bắt buộc không, và khi nào?
- Nguồn inject nào được chấp nhận?
- Có hỗ trợ secret file/config tree hay không?
- Rotation có cần restart/refresh không?
- Lỗi thiếu secret báo ra sao mà không lộ giá trị?
- Có được hiển thị property đó qua Actuator hoặc startup logs không?

Ví dụ YAML tham chiếu biến môi trường:

~~~yaml
acme:
  delivery:
    security:
      api-key-enabled: true
      api-key: "${DELIVERY_API_KEY}"
~~~

Biến `DELIVERY_API_KEY` phải được cấp bằng cơ chế secrets phù hợp. Có thể dùng Docker/Kubernetes Secret, secret store, hoặc config tree theo đặc điểm hạ tầng.

Tuyệt đối không log:

~~~java
log.info("allDeliveryConfig={}", deliveryProperties);
~~~

nếu object có thể chứa `apiKey`. Một record có `toString()` tự sinh nên càng cần cẩn trọng khi log object.

Thông báo lỗi tốt:

~~~text
acme.delivery.security.api-key is required when API-key auth is enabled
~~~

Thông báo xấu:

~~~text
Invalid API key value = actual-secret-string...
~~~

`@ConfigurationProperties` và `@Validated` không phải secret manager. Chúng giúp bind/validate; bảo vệ dữ liệu còn phụ thuộc nguồn, phân quyền, logs và cách ứng dụng sử dụng.

## 15. Metadata: để IDE và người vận hành khám phá keys

Một contract nên có cấu trúc giúp tooling hỗ trợ autocomplete, descriptions, defaults và deprecation.

Spring Boot hỗ trợ configuration metadata tại:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Với Maven, annotation processor có thể được thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Tùy Maven/Gradle compiler và cấu hình annotation processing, cần bảo đảm processor thực sự được chạy.

Một JSON metadata minh họa:

~~~json
{
  "properties": [
    {
      "name": "acme.delivery.connect-timeout",
      "type": "java.time.Duration",
      "description": "Connection establishment timeout.",
      "defaultValue": "5s"
    },
    {
      "name": "acme.delivery.max-retries",
      "type": "java.lang.Integer",
      "description": "Maximum number of retries.",
      "defaultValue": 3
    }
  ]
}
~~~

Metadata hỗ trợ công cụ và tài liệu; **nó không phải runtime PropertySource**. Sửa `defaultValue` trong JSON metadata không tự thay đổi default của bean.

### 15.1. Hints và mô tả bổ sung

Có thể đặt file:

~~~text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
~~~

Ví dụ:

~~~json
{
  "properties": [
    {
      "name": "acme.delivery.endpoint",
      "type": "java.net.URI",
      "description": "Absolute HTTPS URI when delivery is enabled."
    }
  ],
  "hints": [
    {
      "name": "acme.delivery.mode",
      "values": [
        {"value": "sync", "description": "Synchronous calls."},
        {"value": "async", "description": "Asynchronous delivery."}
      ]
    }
  ]
}
~~~

Hints giúp IDE đề xuất lựa chọn; chúng không thực thi validation. Nếu chỉ cho phép sync/async, cần enum hoặc constraint trong runtime code.

## 16. Đổi tên key là một thay đổi có version

Ví dụ ứng dụng cũ có:

~~~properties
acme.delivery.retry-count=3
~~~

Phiên bản mới muốn thay bằng:

~~~properties
acme.delivery.max-retries=3
~~~

Chỉ rename Java field là chưa đủ. Deployment cũ có thể vẫn cấp `retry-count` mà Binder không còn nhận theo ý định. Nếu new field có default `3`, lỗi thậm chí có thể bị che đi.

Quy trình migration hợp lý:

1. Công bố key mới và lý do.
2. Xác định có cần một giai đoạn hỗ trợ cả old và new key không.
3. Nếu cần compatibility, triển khai rõ ràng ở runtime, không chỉ docs.
4. Quy định **nếu cả old và new cùng xuất hiện thì cái nào thắng**.
5. Cảnh báo có kiểm soát khi còn dùng old key.
6. Cập nhật Helm/Compose/Kubernetes/systemd/CI/secrets.
7. Test cả hai cách cấu hình.
8. Đánh dấu deprecated trong metadata và đưa hướng dẫn vào release notes.
9. Chỉ xóa old support theo chính sách versioning.

### 16.1. Metadata deprecation không tạo alias runtime

Trong `additional-spring-configuration-metadata.json`:

~~~json
{
  "properties": [
    {
      "name": "acme.delivery.retry-count",
      "type": "java.lang.Integer",
      "deprecation": {
        "level": "warning",
        "reason": "Renamed for consistency with other retry settings.",
        "replacement": "acme.delivery.max-retries"
      }
    }
  ]
}
~~~

Thông tin này giúp IDE báo key cũ sắp bị thay thế. Nhưng `replacement` **không tự khiến Binder hiểu old key là alias cho new key**. Muốn hỗ trợ old key runtime phải có code/migration mechanism tương ứng.

Có thể quy định:

~~~text
Chỉ new key: dùng new.
Chỉ old key: chấp nhận old + cảnh báo.
Cả hai: dùng new + cảnh báo old.
Cả hai vắng: dùng default.
~~~

Kiểm thử contract phải xác nhận đúng chính sách, tránh phụ thuộc may rủi vào precedence của hai tên key khác nhau.

## 17. Đổi kiểu, đơn vị hay default cũng có thể breaking

| Thay đổi | Rủi ro |
| --- | --- |
| `long timeoutSeconds` → `Duration` mặc định ms | Giá trị `5` đổi từ 5s thành 5ms |
| `long bufferBytes` → `DataSize` có default unit MB | Giá trị `2` đổi nghĩa |
| `String mode` → enum | Legacy mode values có thể không parse |
| `List<T>` → `Map<String,T>` | Đổi YAML shape và merge semantics |
| Default retries `3` → `0` | Hành vi khi key thiếu đổi hoàn toàn |
| Chấp nhận timeout 60s → tối đa 30s | Deployment cũ có thể fail startup |
| Optional endpoint → required | Cần nâng cấp tất cả manifests |
| Optional secret → required | Cần provisioning bảo mật trước deploy |

Nếu field cũ `long timeoutSeconds` từng hiểu số trần là giây, khi nâng thành Duration có thể dùng:

~~~java
@DurationUnit(ChronoUnit.SECONDS)
private Duration timeout;
~~~

Tương tự với dung lượng:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize buffer;
~~~

Điều này giúp bảo toàn cách diễn giải số trần khi cần. Tài liệu mới vẫn nên yêu cầu suffix tường minh như `5s` và `2MB`, cùng migration plan cho key cũ.

Không nên coi việc thay default là “nội bộ” nếu ảnh hưởng production trong trường hợp operator không ghi đè key.

## 18. Tài liệu cho operator cần ví dụ hoàn chỉnh

Một README cấu hình tốt nên có bảng contract, các đoạn YAML, ví dụ OS environment, cách nạp secrets, lỗi thường gặp, migration và cách xác minh.

Development:

~~~yaml
acme:
  delivery:
    enabled: false
    connect-timeout: 5s
    max-retries: 1
    buffer-size: 512KB
~~~

Production:

~~~yaml
acme:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test
    connect-timeout: 3s
    max-retries: 3
    buffer-size: 8MB
    security:
      api-key-enabled: true
      api-key: "${DELIVERY_API_KEY}"
~~~

OS env tương ứng:

~~~bash
ACME_DELIVERY_ENABLED=true
ACME_DELIVERY_CONNECTTIMEOUT=3s
ACME_DELIVERY_MAXRETRIES=3
ACME_DELIVERY_BUFFERSIZE=8MB
~~~

Với API key, nên inject bằng secret mechanism riêng. Không log hay commit credential.

Khi mô tả defaults, hãy ghi **cái gì xảy ra nếu thiếu key**, không chỉ ghi giá trị mặc định trong một file ví dụ. Khi mô tả required, hãy ghi lỗi xảy ra **ở startup hay khi gọi request**, và phụ thuộc điều kiện nào.

## 19. Test contract bằng `ApplicationContextRunner`

Spring Boot `ApplicationContextRunner` phù hợp để test binding và startup validation ở phạm vi nhỏ.

~~~java
package com.example.delivery;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesContractTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ConfigurationPropertiesAutoConfiguration.class))
            .withUserConfiguration(
                Registration.class,
                DeliveryValidationConfiguration.class);

    @Test
    void usesSafeDefaultsWhenDisabled() {
        runner.withPropertyValues("acme.delivery.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();

                DeliveryProperties props =
                    context.getBean(DeliveryProperties.class);

                assertThat(props.enabled()).isFalse();
                assertThat(props.connectTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(5));
                assertThat(props.maxRetries()).isEqualTo(3);
                assertThat(props.bufferSize().toBytes())
                    .isEqualTo(2L * 1024 * 1024);
            });
    }

    @Test
    void bindsExplicitUnits() {
        runner.withPropertyValues(
            "acme.delivery.enabled=true",
            "acme.delivery.endpoint=https://gateway.example.test",
            "acme.delivery.connect-timeout=750ms",
            "acme.delivery.buffer-size=512KB")
            .run(context -> {
                assertThat(context).hasNotFailed();

                DeliveryProperties props =
                    context.getBean(DeliveryProperties.class);

                assertThat(props.connectTimeout())
                    .isEqualTo(java.time.Duration.ofMillis(750));
                assertThat(props.bufferSize().toBytes())
                    .isEqualTo(512L * 1024);
            });
    }

    @Test
    void rejectsRetriesAboveMaximum() {
        runner.withPropertyValues(
            "acme.delivery.enabled=true",
            "acme.delivery.endpoint=https://gateway.example.test",
            "acme.delivery.max-retries=99")
            .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsEnabledDeliveryWithoutEndpoint() {
        runner.withPropertyValues(
            "acme.delivery.enabled=true")
            .run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class Registration {
    }
}
~~~

Test này dựa trên model và validator ở các phần trước. Nếu dùng Jakarta constraints, bảo đảm có một Bean Validation implementation phù hợp (thường `spring-boot-starter-validation`) trong test runtime.

### 19.1. Những case không nên bỏ qua

| Input | Kỳ vọng |
| --- | --- |
| Missing các key optional | Dùng default an toàn |
| `enabled=false`, thiếu endpoint | Thành công nếu contract cho phép |
| `enabled=true`, thiếu endpoint | Fail startup |
| `endpoint=http://...` | Fail nếu yêu cầu HTTPS |
| `connect-timeout=0s` | Fail |
| `connect-timeout=31s` | Fail |
| `connect-timeout=750ms` | Parse chính xác |
| `buffer-size=1B` | Fail nếu tối thiểu 64KB |
| `max-retries=-1` | Fail |
| `max-retries=11` | Fail |
| `max-retries=abc` | Fail conversion |
| API-key auth bật, secret thiếu | Fail mà không lộ secret |
| Env var override YAML | Nhận giá trị theo precedence |
| Legacy + new key cùng khai báo | Tuân thủ migration policy |

Không nên chỉ có happy-path test, vì lỗi contract thường xuất hiện ở input thiếu, sai hoặc được triển khai theo phiên bản cũ.

## 20. Phân biệt test binding và test Config Data thật

`ApplicationContextRunner.withPropertyValues(...)` tạo property sources cho test và phù hợp kiểm chứng binding. Nhưng nó **không tự chứng minh** các file `application-prod.yml` hoặc các `spring.config.import` được SpringApplication nạp đầy đủ trong deployment thật.

Khi contract phụ thuộc:

- Active profiles.
- Config Data locations hoặc imports.
- Environment variable names.
- Docker/Kubernetes mounts.
- Precedence giữa file và CLI.
- Startup fail-fast khi thiếu secret.

Hãy thêm integration/smoke tests bằng con đường `SpringApplication` phù hợp và manifest thực tế. Với Spring TestContext, chú ý `@TestPropertySource` và `@DynamicPropertySource` có precedence riêng, nên một test dùng chúng có thể **khác** thứ tự nguồn production.

Một deployment smoke test có thể chạy với cấu hình môi trường không nhạy cảm rồi assert một marker như `acme.deployment.id`. Nó không nên dump toàn bộ Environment.

## 21. Hợp đồng phải cân bằng fail-fast và khả dụng

Lỗi cần phát hiện sớm:

- URI sai scheme hoặc host.
- Retry vượt giới hạn.
- Timeout bằng 0 trong API yêu cầu timeout dương.
- Secret bắt buộc bị thiếu.
- Hai field không tương thích.

Những lỗi không nên tùy tiện đưa vào configuration validator:

- Thử kết nối database/HTTP với thời gian chờ dài.
- Gọi API ngoài để kiểm tra token trong lúc binder đang chạy.
- Đọc repository hoặc sử dụng service bean chưa khởi tạo.
- Thay đổi cấu hình hoặc ghi file như một side effect của validation.

Tách rõ **cấu hình hợp lệ về dữ liệu** và **phụ thuộc ngoài thật sự sẵn sàng**. Với phần sau, dùng health/readiness checks hoặc integration verification có timeout và policy riêng.

## 22. Nếu viết reusable Spring Boot Starter

Một starter có thể được dùng bởi nhiều ứng dụng, nên config contract càng phải ổn định:

1. Dùng namespace riêng, không xung đột với khóa built-in.
2. Cung cấp `@ConfigurationProperties` type-safe.
3. Mô tả defaults, units, allowed values và behavior khi thiếu key.
4. Tạo metadata và documentation tự động khi phù hợp.
5. Đăng ký auto-configuration với điều kiện rõ.
6. Không tự bật kết nối production chỉ vì starter nằm trên classpath, trừ khi contract cho phép.
7. Không tạo secret default.
8. Thêm tests cho việc một project **không cấu hình starter**.
9. Có deprecation policy và release notes khi đổi key.
10. Đối chiếu hỗ trợ theo Spring Boot version.

Với `@ConditionalOnProperty`, nhớ rằng **default trong `@ConfigurationProperties` không tự xuất hiện trong Environment**. Điều kiện đọc Environment phải định nghĩa `matchIfMissing`/`havingValue` hoặc default source theo ý định; không dựa vào initializer của record để tác động magic lên condition.

## 23. Các lỗi thiết kế thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Có `@ConfigurationProperties` là đã có contract.” | Contract cần rõ tên, type, unit, default, constraints, precedence và nâng cấp. |
| “Relaxed binding cho phép đặt key tùy ý.” | Nó có quy tắc; vẫn nên công bố một canonical form. |
| “`Duration` nhận số `5` là 5s.” | Mặc định thường là 5ms nếu không có `@DurationUnit`. |
| “`DataSize` nhận số `2` là 2MB.” | Mặc định thường là 2B nếu không có `@DataSizeUnit`. |
| “`@DurationUnit` tạo default.” | Chỉ chỉ định đơn vị cho số trần đã có. |
| “`@DefaultValue` cập nhật Environment.” | Không, fallback của object không tự tạo PropertySource. |
| “URI parse thành công nghĩa là URL HTTPS an toàn.” | Cần semantic validation cho scheme/host và chính sách riêng. |
| “Value convert thành công là hợp lệ.” | Conversion khác validation. |
| “Đổi Java field là đổi tên an toàn.” | Legacy deployment có thể mất binding key. |
| “Metadata replacement tự tạo alias.” | Không; migration runtime cần thực thi riêng. |
| “List ở profile sẽ nối với List mặc định.” | List thường bị thay thế, không tự concat. |
| “Secret có thể có default production trong repo.” | Không nên có credential thật trong artifact/tài liệu. |
| “`@ConditionalOnProperty` nhìn thấy default record.” | Condition đọc Environment, không phải default Java object. |
| “Test withPropertyValues chứng minh YAML/import thực tế.” | Nó chỉ kiểm tra binding từ test properties; cần test Config Data riêng. |

## 24. Bài tập 1 — Thiết kế contract cho bộ xử lý sự kiện

Yêu cầu có:

~~~text
processor.enabled
processor.max-in-flight
processor.retry-delay
processor.max-payload
processor.dead-letter-topic
~~~

Hãy đề xuất types, defaults và constraints.

Một phương án:

| Key | Java type | Default | Constraint |
| --- | --- | --- | --- |
| `acme.processor.enabled` | boolean | `false` | Chỉ bật khi operator chọn |
| `acme.processor.max-in-flight` | int | `16` | 1–256 khi enabled |
| `acme.processor.retry-delay` | Duration | `1s` | >0, <=1m |
| `acme.processor.max-payload` | DataSize | `1MB` | 1KB–32MB |
| `acme.processor.dead-letter-topic` | String | Không có | Bắt buộc khi dead-letter mode bật |

**Giải thích:** tên phản ánh nghiệp vụ; type hỗ trợ đơn vị; default an toàn; các rule không chỉ kiểm tra type mà còn giới hạn tiêu thụ tài nguyên.

## 25. Bài tập 2 — Phát hiện contract thiếu thông tin

Code cũ:

~~~java
@ConfigurationProperties(prefix = "app")
public class BadProperties {
    private long timeout = 5;
    private long buffer = 2;
    private int retries = -1;
    // getters/setters
}
~~~

Các vấn đề:

- Prefix quá rộng, dễ xung đột.
- `timeout` không nói connect/read/total timeout.
- `5` không ghi đơn vị.
- `buffer=2` không cho biết byte/MB.
- `retries=-1` chưa có semantics.
- Không có validation min/max.
- Không có cách fail khi một key bắt buộc thiếu.
- Không có docs về env variable names, migration và precedence.

Một thiết kế tốt hơn: `acme.delivery.connect-timeout=5s` kiểu Duration, `acme.delivery.buffer-size=2MB` kiểu DataSize, `acme.delivery.max-retries=3` với giới hạn [0,10].

## 26. Bài tập 3 — Dự đoán binding

Record:

~~~java
@ConfigurationProperties(prefix = "acme.delivery")
public record SimpleProperties(
    @DefaultValue("5s") Duration connectTimeout,
    @DefaultValue("2MB") DataSize bufferSize,
    @DefaultValue("3") int maxRetries) {
}
~~~

**A. Cả ba key đều không được cấu hình.** Giá trị sau bind: 5s, 2MB, 3.

**B. YAML có `connect-timeout: 10`.** Nếu không có `@DurationUnit`, số trần được hiểu theo ms: kết quả 10ms.

**C. YAML có `buffer-size: 512KB`.** Kết quả 512KB = 524.288 byte.

**D. YAML có `max-retries: 3`, OS env có `ACME_DELIVERY_MAXRETRIES=6`.** Trong chế độ thông thường, env thắng và kết quả 6.

**E. YAML có `max-retries: 99` nhưng không có validator.** Binding int có thể thành công; cần constraint để chặn nghiệp vụ.

**F. Không có key `connect-timeout`, record dùng default 5s, hỏi Environment.** `Environment.getProperty(...)` có thể trả null; default trong record không tự trở thành property.

## 27. Bài tập 4 — Nâng cấp đơn vị không đổi nghĩa giá trị cũ

Mã cũ:

~~~java
private long timeoutSeconds = 5;
~~~

Đã công bố:

~~~properties
acme.delivery.timeout-seconds=5
~~~

Muốn chuyển sang `Duration` nhưng vẫn hỗ trợ input cũ.

Các bước:

1. Xác nhận ý nghĩa cũ: số trần là giây.
2. Định nghĩa key mới, cách chấp nhận old key và thời hạn hỗ trợ.
3. Với đích Duration nhận số trần, dùng `@DurationUnit(ChronoUnit.SECONDS)` nếu cần giữ ngữ nghĩa.
4. Tài liệu mới dùng `5s` thay cho số `5`.
5. Test `5`, `5s`, `500ms` và trường hợp missing.
6. Định nghĩa kết quả nếu old/new cùng xuất hiện.
7. Dùng metadata deprecation và migration guide.
8. Không âm thầm đổi `5` thành 5ms trong production.

Tương tự, nâng `bufferSizeMegabytes=2` sang `DataSize` có thể cần `@DataSizeUnit(MEGABYTES)` để không thay đổi ý nghĩa số trần cũ.

## 28. Bài tập 5 — Secret bắt buộc có điều kiện

Cho hợp đồng:

~~~text
acme.delivery.enabled=false
acme.delivery.security.api-key-enabled=false
acme.delivery.security.api-key=<absent>
~~~

Khi nào `api-key` phải có?

Theo hợp đồng mẫu: khi **delivery enabled=true** và **api-key-enabled=true**. Nếu cả hai false, thiếu secret là bình thường. Vì vậy `@NotBlank` không điều kiện có thể không phù hợp; dùng cross-field rule.

Lỗi nên chỉ nêu rằng secret bắt buộc đã thiếu, không in secret hoặc toàn bộ properties bean.

## 29. Checklist trước release

- [ ] Mỗi key có canonical name và owner/prefix rõ ràng.
- [ ] Type phản ánh đại lượng thật: Boolean, Duration, DataSize, URI, enum...
- [ ] Dạng số trần và đơn vị mặc định đã được công bố.
- [ ] Các mẫu YAML dùng hậu tố tường minh cho thời gian/dung lượng.
- [ ] Các key required/optional/conditionally required được phân biệt.
- [ ] Default an toàn và không che lỗi input đã khai báo sai.
- [ ] Cross-field rules, min/max và validation thực sự được triển khai.
- [ ] Lỗi startup cho operator biết key và quy tắc vi phạm.
- [ ] Tên env variables tuân theo relaxed binding của Spring Boot.
- [ ] Có tài liệu precedence giữa file/profile/OS env/CLI.
- [ ] Nếu có List/Map, mô tả semantics override.
- [ ] Không commit hoặc log secret; có nguồn inject được kiểm soát.
- [ ] Có configuration metadata cho IDE/docs khi cần.
- [ ] Deprecated keys có migration runtime, không chỉ metadata.
- [ ] Thay type/unit/default được đánh giá về breaking changes.
- [ ] Tests cho missing, invalid, boundary, precedence và legacy.
- [ ] Deployment manifest/Helm/Compose/CI đã theo tên mới.
- [ ] Nêu rõ thay file config có cần restart/reload hay không.

## 30. Kết luận

**Cấu hình ổn định là một phần của thiết kế phần mềm, không phải chi tiết sau cùng của deployment.** Một key cần được đặt tên, kiểu hóa và tài liệu hóa như một API:

~~~text
Canonical key + namespace
            |
            v
Type + unit conversion
            |
            v
Default / required / conditional required
            |
            v
Validation + cross-field invariants
            |
            v
PropertySource precedence + secrets policy
            |
            v
Metadata + examples + tests
            |
            v
Versioning + migration
~~~

Những điểm cần ghi nhớ:

1. `@ConfigurationProperties` cho model type-safe.
2. `Duration` và `DataSize` yêu cầu hợp đồng đơn vị rõ ràng.
3. `@DurationUnit` và `@DataSizeUnit` **không tự tạo default value**.
4. `@DefaultValue` hoặc initializer cung cấp default khi key thiếu, nhưng default không tự xuất hiện trong Environment.
5. `@Validated` + Jakarta/custom Validator chặn cấu hình sai nghiệp vụ.
6. Canonical kebab-case và env var mapping chuẩn giúp operator ít lỗi.
7. Thay key, type, default hoặc unit có thể là breaking change.
8. Configuration metadata hỗ trợ khám phá/deprecation, không tự triển khai alias runtime.
9. Secret phải có nguồn cấp và chính sách log/rotation riêng.
10. Test contract phải bao trùm cả trường hợp thiếu, sai, override và legacy.

### Tài liệu tham khảo

- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot — Converting Durations/Data Sizes: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion
- Spring Boot — Configuration Properties Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Spring Boot — Metadata Format: https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html
- Spring Boot — Annotation Processor: https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html
- Spring Boot — Additional Metadata: https://docs.spring.io/spring-boot/specification/configuration-metadata/manual-hints.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
