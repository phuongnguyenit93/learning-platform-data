# Validator chuyên dụng mang tên `configurationPropertiesValidator` trong Spring Boot

## 1. Bài toán: kiểm tra cấu hình trước khi ứng dụng phục vụ yêu cầu

Spring Boot cho phép gom cấu hình ngoài vào các Java object bằng `@ConfigurationProperties`. Những giá trị đó có thể đến từ `application.yml`, `application.properties`, biến môi trường, Java system properties, đối số dòng lệnh hoặc các Config Data imports.

Ví dụ một dịch vụ giao tiếp với cổng thanh toán cần ba thông số:

~~~yaml
app:
  delivery:
    endpoint: https://gateway.example.test
    connect-timeout: 5s
    max-retries: 3
~~~

Ngay cả khi YAML hợp lệ về cú pháp và Spring Boot chuyển đổi được `5s` thành `Duration`, ứng dụng vẫn có thể nhận **cấu hình sai về nghiệp vụ**:

- `endpoint` không có scheme HTTPS hoặc không có host.
- `connect-timeout` bằng 0 hoặc âm.
- `max-retries` vượt giới hạn an toàn của dịch vụ.
- Hai thuộc tính riêng lẻ hợp lệ nhưng **không tương thích khi đi cùng nhau**.
- Một trường bắt buộc bị thiếu nhưng JavaBean vẫn được tạo.

Các lỗi này nên được phát hiện **khi khởi động**, thay vì đợi lúc có request thật. Spring Boot hỗ trợ Jakarta Bean Validation với `@Validated` và `@NotBlank`, `@Min`, `@NotNull`. Khi cần logic kiểm tra riêng, Spring Boot còn hỗ trợ một **Spring Validator chuyên dụng** được đăng ký bằng một tên bean đã quy định sẵn:

~~~text
configurationPropertiesValidator
~~~

Bài này trình bày cách viết, đăng ký và sử dụng validator đó, tại sao `@Bean` cần `static`, cách phối hợp với `@Validated`, cách báo lỗi vào đúng field, và những lỗi startup cần tránh.

> **Điểm cần nhớ:** tên `configurationPropertiesValidator` là một **hợp đồng tích hợp** của Spring Boot. Chỉ có một lớp triển khai `Validator` không đủ; bean phải được đăng ký đúng tên để infrastructure dành cho configuration properties tìm được nó.

## 2. Phân biệt validation với binding và chuyển đổi kiểu

Khi Spring Boot chuẩn bị một bean `@ConfigurationProperties`, ta có thể hình dung các trách nhiệm:

~~~text
application.yml, environment, JVM -D, command-line, ...
                         |
                         v
                    Environment
               (xác định nguồn ưu tiên)
                         |
                         v
                  Configuration Binder
              (ghép key → thuộc tính Java)
                         |
                         v
                  Type Conversion
            ("5s" → Duration, "3" → int)
                         |
                         v
                   Validation
             (ràng buộc trên object)
                         |
                         v
                 Bean được sử dụng
~~~

Ba loại lỗi cần phân biệt:

| Loại lỗi | Ví dụ | Cơ chế phát hiện |
| --- | --- | --- |
| Cấu hình sai định dạng | `connect-timeout: not-a-duration` | Converter/binder không chuyển được sang `Duration` |
| Ràng buộc đơn giản bị vi phạm | `endpoint: ""` | `@NotBlank` hoặc Spring `Validator` |
| Quy tắc nghiệp vụ bị vi phạm | `max-retries: 100` dù vẫn là `int` | Constraint hoặc Spring `Validator` kiểm tra khoảng |
| Quan hệ giữa các thuộc tính không hợp lệ | Chế độ gửi đồng bộ với retry quá cao | Validator kiểm tra nhiều field trong cùng object |

Spring `Validator` không thay thế parser của YAML, không lựa chọn nguồn cấu hình và không biến string bất kỳ thành Java type. Nó nhận một **đối tượng đã được binder tạo/thiết lập** rồi kiểm tra tính hợp lệ.

Nếu binding bị lỗi trước khi tạo được object, validator có thể chưa có cơ hội chạy. Vì vậy đừng viết validator để “sửa” lỗi converter; phải sửa giá trị hoặc định nghĩa converter phù hợp.

## 3. Bean tên `configurationPropertiesValidator` là gì?

Theo tài liệu Spring Boot, bạn có thể bổ sung một custom `org.springframework.validation.Validator` bằng cách đăng ký bean **có tên** `configurationPropertiesValidator`.

Chú ý ba phần khác nhau:

1. **Kiểu interface:** `org.springframework.validation.Validator` (Spring Framework).
2. **Tên bean Spring:** chính xác `configurationPropertiesValidator`.
3. **Thời điểm khởi tạo:** validator được infrastructure configuration properties yêu cầu **rất sớm**, nên factory method `@Bean` cần được khai báo `static` để Spring không phải khởi tạo sớm cả class `@Configuration`.

Khai báo tối thiểu:

~~~java
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;

@Configuration(proxyBeanMethods = false)
public class PropertiesValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

Ở đây `DeliveryPropertiesValidator` là class tự viết triển khai Spring `Validator`, được trình bày chi tiết ở phần sau.

Có thể dùng tên mặc định theo method:

~~~java
@Bean
public static Validator configurationPropertiesValidator() {
    return new DeliveryPropertiesValidator();
}
~~~

Vì tên method trùng tên bean yêu cầu, nó có thể được đăng ký đúng. Tuy nhiên, dùng `@Bean(name = "configurationPropertiesValidator")` là cách **tường minh** và vẫn đúng nếu sau này đổi tên method Java.

Không nên dùng một tên tùy ý như:

~~~java
@Bean(name = "deliveryValidator")
public static Validator validator() {
    return new DeliveryPropertiesValidator();
}
~~~

rồi kỳ vọng Spring Boot tự nhận bean này là **dedicated configuration properties validator** chỉ vì kiểu trả về là `Validator`. Để dùng cơ chế chuyên dụng, phải có tên bean chính xác.

## 4. Vì sao `@Bean` phải `static`?

Spring Boot cần validator trong giai đoạn khởi tạo hạ tầng bind configuration properties, trước khi toàn bộ application context và các bean thông thường đã sẵn sàng.

Xét cách đăng ký **không nên dùng**:

~~~java
@Configuration(proxyBeanMethods = false)
public class PropertiesValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

Đây là một instance factory method. Để gọi nó, container có thể phải tạo `PropertiesValidationConfiguration` trước thời điểm mà các bean và `BeanPostProcessor` khác đã ổn định. Điều đó tạo rủi ro khởi tạo sớm, warning và dependency/lifecycle bất ngờ.

Cách nên dùng:

~~~java
@Configuration(proxyBeanMethods = false)
public class PropertiesValidationConfiguration {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new DeliveryPropertiesValidator();
    }
}
~~~

Với `static`, phương thức factory có thể được gọi **mà không cần một instance của lớp `@Configuration`**. Đây là lý do quan trọng nhất, không phải tối ưu hiệu năng.

### 4.1. `static` không có nghĩa validator được chạy một lần

Một nhầm lẫn phổ biến: khi method `@Bean` là `static`, có phải `validate(...)` chỉ chạy một lần hay không?

Không. `static` chỉ mô tả **cách gọi factory method để tạo bean**. Validator được tạo như một Spring bean và phương thức `validate(target, errors)` có thể được gọi cho từng configuration-properties object phù hợp khi chúng được bind/validated.

### 4.2. Tránh dependencies khởi tạo muộn

Không nên cấu hình validator phải phụ thuộc vào repository, data source, HTTP client hoặc service nghiệp vụ chỉ được tạo sau khi toàn bộ context khởi động:

~~~java
// Không phải thiết kế phù hợp cho validator khởi tạo rất sớm.
@Bean(name = "configurationPropertiesValidator")
public static Validator configurationPropertiesValidator(
        CustomerRepository repository) {
    return new ValidatorThatQueriesDatabase(repository);
}
~~~

Về mặt DI, Spring có thể cố giải quyết tham số method, nhưng điều này kéo thêm bean vào quá trình startup sớm, tạo nguy cơ vòng phụ thuộc hoặc bean chưa được xử lý đầy đủ.

Validator dành cho cấu hình nên **thuần**, hoạt động trên các giá trị của target object; dùng Java API tiêu chuẩn, các utility không phụ thuộc context, hoặc dữ liệu đơn giản đã biết. Không gọi mạng, không truy cập database và không dựa vào trạng thái application đã khởi động.

Nếu quy tắc phụ thuộc dữ liệu bên ngoài (ví dụ kiểm tra một endpoint thực sự reachable), hãy tách thành kiểm tra readiness/health/dependency phù hợp thay vì nhét vào validator cấu hình chạy rất sớm.

## 5. Giao diện Spring `Validator` có hai phương thức

Spring Framework định nghĩa:

~~~java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

### 5.1. `supports(Class<?>)`

Spring dùng `supports` để biết validator có khả năng kiểm tra kiểu target cụ thể hay không.

Ví dụ:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return DeliveryProperties.class.isAssignableFrom(clazz);
}
~~~

Ý nghĩa: hỗ trợ `DeliveryProperties` và subtype thích hợp.

Không nên trả về `true` cho mọi class rồi cast tất cả target thành `DeliveryProperties`:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return true; // Dễ dẫn đến ClassCastException nếu nhiều properties bean.
}
~~~

Một application thường có rất nhiều `@ConfigurationProperties` bean, gồm cả các type do Spring Boot và thư viện cung cấp. Validator chuyên dụng có thể được đưa vào quá trình xử lý các bean khác; `supports` chính là cách hạn chế phạm vi để tránh cast sai.

### 5.2. `validate(Object, Errors)`

`validate` nhận đối tượng đã bind và một `Errors` collector để báo lỗi tại đúng field hoặc báo lỗi toàn object:

~~~java
@Override
public void validate(Object target, Errors errors) {
    DeliveryProperties props = (DeliveryProperties) target;

    if (props.getMaxRetries() < 0) {
        errors.rejectValue(
                "maxRetries",
                "delivery.maxRetries.invalid",
                "maxRetries must not be negative");
    }
}
~~~

Tham số của `rejectValue` gồm:

1. Tên **field JavaBean** (ở đây `maxRetries`), không nhất thiết là full property path `app.delivery.max-retries`.
2. Error code, ví dụ `delivery.maxRetries.invalid`.
3. Default message để logs/failure analysis có thể diễn giải.

Spring có cơ chế chuyển error codes sang thông báo thân thiện hơn thông qua `MessageSource` khi được cấu hình phù hợp. Nếu chưa cấu hình message bundle, default message vẫn giúp người vận hành biết lý do.

Đối với lỗi không gắn vào một trường cụ thể, có thể dùng:

~~~java
errors.reject("delivery.inconsistent",
        "Delivery configuration contains incompatible values");
~~~

Không throw `IllegalArgumentException` cho mọi rule nếu có thể dùng `Errors`; dùng error collector giúp infrastructure gắn lỗi vào binding/validation failure rõ ràng hơn.

## 6. Ví dụ hoàn chỉnh: model `DeliveryProperties`

Dự án demo dùng Java 17+ và Spring Boot 3.x. Chúng ta muốn kiểm tra:

- `endpoint` không được rỗng và phải có HTTPS URI với host.
- `connectTimeout` phải dương và không vượt ngưỡng nội bộ 60 giây.
- `maxRetries` nằm trong khoảng 0 đến 10.
- Nếu `enabled=true`, phải có endpoint dùng được.
- Nếu `enabled=false`, có thể cho phép endpoint thiếu; tùy contract. Trong ví dụ sau, ta đặt quy tắc rõ ràng: **khi bật thì endpoint bắt buộc, khi tắt thì endpoint có thể bỏ qua**.

File `src/main/resources/application.yml`:

~~~yaml
app:
  delivery:
    enabled: true
    endpoint: https://gateway.example.test
    connect-timeout: 5s
    max-retries: 3
~~~

Class properties kiểu JavaBean:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryProperties {

    private boolean enabled = false;
    private String endpoint;
    private Duration connectTimeout = Duration.ofSeconds(5);
    private int maxRetries = 2;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }

    public void setMaxRetries(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

Ghi chú:

- `@ConfigurationProperties(prefix = "app.delivery")` gom các key dưới một prefix.
- `@Validated` thể hiện rằng object cần tham gia validation; Spring Boot hỗ trợ xử lý validation cho configuration properties.
- JavaBean initializer cung cấp giá trị dự phòng nếu property không được khai báo.
- `Duration` bind được `5s`, `30s`... từ cấu hình theo conversion của Spring Boot.
- `endpoint` dùng `String` để validator có thể tự kiểm tra chính sách HTTPS. Có thể bind trực tiếp sang `URI`, nhưng vẫn cần kiểm tra scheme/host theo yêu cầu.
- Default trong JavaBean không tự tạo một property tương ứng trong `Environment` nếu không có nguồn cấu hình khai báo nó.

## 7. Triển khai `DeliveryPropertiesValidator`

Đây là class hoàn chỉnh không cần truy cập Spring container hay database:

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class DeliveryPropertiesValidator implements Validator {

    private static final Duration MAX_TIMEOUT = Duration.ofSeconds(60);

    @Override
    public boolean supports(Class<?> clazz) {
        return DeliveryProperties.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        DeliveryProperties props = (DeliveryProperties) target;

        validateTimeout(props, errors);
        validateRetries(props, errors);

        if (props.isEnabled()) {
            validateRequiredEndpoint(props.getEndpoint(), errors);
        }
        else if (props.getEndpoint() != null
                && !props.getEndpoint().isBlank()) {
            // Nếu có khai báo endpoint khi disabled, vẫn yêu cầu
            // giá trị hợp lệ để tránh cấu hình ẩn sai.
            validateRequiredEndpoint(props.getEndpoint(), errors);
        }
    }

    private void validateTimeout(
            DeliveryProperties props, Errors errors) {
        Duration timeout = props.getConnectTimeout();

        if (timeout == null || timeout.isZero()
                || timeout.isNegative()) {
            errors.rejectValue(
                    "connectTimeout",
                    "delivery.timeout.notPositive",
                    "connect-timeout must be positive");
            return;
        }

        if (timeout.compareTo(MAX_TIMEOUT) > 0) {
            errors.rejectValue(
                    "connectTimeout",
                    "delivery.timeout.tooLarge",
                    "connect-timeout must not exceed 60s");
        }
    }

    private void validateRetries(
            DeliveryProperties props, Errors errors) {
        int retries = props.getMaxRetries();

        if (retries < 0 || retries > 10) {
            errors.rejectValue(
                    "maxRetries",
                    "delivery.retries.outOfRange",
                    "max-retries must be between 0 and 10");
        }
    }

    private void validateRequiredEndpoint(
            String value, Errors errors) {
        if (value == null || value.isBlank()) {
            errors.rejectValue(
                    "endpoint",
                    "delivery.endpoint.required",
                    "endpoint must be configured when delivery is enabled");
            return;
        }

        try {
            URI uri = URI.create(value);

            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || uri.getHost() == null) {
                errors.rejectValue(
                        "endpoint",
                        "delivery.endpoint.invalid",
                        "endpoint must be an absolute HTTPS URI with a host");
            }
        }
        catch (IllegalArgumentException ex) {
            errors.rejectValue(
                    "endpoint",
                    "delivery.endpoint.malformed",
                    "endpoint is not a valid URI");
        }
    }
}
~~~

Phần code cố ý dùng `errors.rejectValue(...)` thay vì throw exception tùy ý. Nó cung cấp tên field, mã lỗi và thông báo; Spring Boot có thể tổng hợp các lỗi này thành binding/validation failure trong quá trình khởi động.

Cách validator xử lý `enabled=false` là **lựa chọn nghiệp vụ của ví dụ**. Dự án khác có thể yêu cầu `endpoint` luôn có mặt, hoặc chỉ kiểm tra `timeout` khi chức năng được bật. Không có một chính sách chung do Spring Boot tự áp dụng cho mọi ứng dụng.

Trong một ứng dụng có secret, **không đưa secret vào default message**, kể cả khi người dùng cấu hình sai. Chỉ nên nêu tên property và nguyên tắc bị vi phạm.

## 8. Đăng ký validator đúng tên và đúng thời điểm

Tạo một class cấu hình:

~~~java
package com.example.config;

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

**Tại sao không dùng `@Component` trên `DeliveryPropertiesValidator` rồi thôi?**

Vì component scan mặc định sẽ đặt tên bean dựa trên class, thường là `deliveryPropertiesValidator`, không phải `configurationPropertiesValidator`. Khi ấy Boot không có lý do tự động xem đó là dedicated validator chỉ dựa vào ý nghĩa tên class.

Cũng không cần tự tạo `LocalValidatorFactoryBean` chỉ để triển khai Spring `Validator` này. `LocalValidatorFactoryBean` là một cầu nối cho Jakarta Bean Validation và giải quyết bài toán khác (dù hai cơ chế có thể được kết hợp).

### 8.1. Có cần `@Primary` hoặc `@Qualifier` không?

Không cần dùng `@Primary` để Boot tìm ra dedicated validator này. **Tên bean mới là yếu tố nhận diện** theo hợp đồng Spring Boot.

Tương tự, `@Qualifier("configurationPropertiesValidator")` chỉ có ý nghĩa khi inject bean qua DI ở vị trí khác, không phải cách bắt buộc để đăng ký nó cho Binder.

### 8.2. Không đăng ký nhiều bean cùng tên

Một context không nên có nhiều định nghĩa bean `configurationPropertiesValidator` độc lập. Tùy cấu hình Spring Boot về bean overriding, sự trùng tên có thể khiến context fail startup hoặc bean bị thay thế không như dự kiến.

Nếu có nhiều bộ quy tắc, hãy tạo **một validator tổng** hỗ trợ nhiều properties type, hoặc dùng một cơ chế validator phù hợp theo từng class. Đừng tạo một bean `configurationPropertiesValidator` mới cho mỗi loại cấu hình rồi mong Spring gọi tất cả.

### 8.3. Class configuration phải được phát hiện

`DeliveryValidationConfiguration` cần nằm trong vùng quét component của `@SpringBootApplication` hoặc được import vào context. Nếu file ở package nằm ngoài vùng scan, có thể dùng `@Import(DeliveryValidationConfiguration.class)` trên cấu hình được Spring quản lý.

Annotation `static @Bean` đúng nhưng class chứa nó chưa được đăng ký thì bean vẫn không tồn tại.

## 9. Đăng ký `@ConfigurationProperties` để được bind và validate

Class properties cần được Spring Boot đăng ký đúng cơ chế.

### 9.1. Quét với `@ConfigurationPropertiesScan`

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Giả sử `DeliveryProperties` và `DeliveryValidationConfiguration` nằm dưới package `com.example`. Spring Boot sẽ tìm type properties trong vùng scan, tạo bean và bind giá trị từ `Environment`. Spring sẽ nhận `DeliveryValidationConfiguration` như một class `@Configuration` thông thường.

### 9.2. Đăng ký tường minh với `@EnableConfigurationProperties`

~~~java
package com.example.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryRegistrationConfiguration {
}
~~~

Lựa chọn này hữu ích khi muốn chỉ đăng ký một type cụ thể, chẳng hạn trong auto-configuration hoặc unit test.

### 9.3. Vì sao không nên tự kiểm tra trong service khi chạy lần đầu?

Một lựa chọn khác là gọi `properties.getEndpoint()` và kiểm tra mỗi khi thực hiện nghiệp vụ. Tuy nhiên, như vậy lỗi chỉ xuất hiện khi có request đầu tiên, có thể sau khi ứng dụng đã báo ready và nhận traffic.

Với validator configuration properties, lỗi được phát hiện trong quá trình bean configuration properties được bind/validate, **thường gây lỗi tạo application context và ngăn khởi động hoàn tất**. Cơ chế này phù hợp với các điều kiện cấu hình bắt buộc để dịch vụ hoạt động.

Cần lưu ý một bean chỉ được tạo muộn theo `@Lazy` hoặc một cơ chế khởi tạo đặc biệt có thể làm thời điểm nhận diện lỗi thay đổi. Với những cấu hình bắt buộc toàn hệ thống, nên bảo đảm bean được đăng ký và tạo trong startup path.

## 10. Phân biệt `@Validated`, Jakarta Bean Validation và Spring `Validator`

Các thuật ngữ dễ bị gộp chung:

| Khái niệm | Thành phần | Vai trò |
| --- | --- | --- |
| `@ConfigurationProperties` | Spring Boot | Bind key ngoài vào object Java |
| `@Validated` | Spring Framework | Khai báo nhu cầu validation và nhóm validation liên quan |
| `@NotBlank`, `@NotNull`, `@Min` | `jakarta.validation.constraints` | Ràng buộc Bean Validation dạng declarative |
| Bean Validation implementation | Ví dụ Hibernate Validator | Thực thi các Jakarta constraints |
| `org.springframework.validation.Validator` | Spring Framework | API lập trình thủ công qua `supports` và `validate` |
| Bean `configurationPropertiesValidator` | Spring Boot convention | Đăng ký custom Spring Validator cho config properties |

Nếu chỉ cần một tên bắt buộc, độ dài chuỗi hoặc giới hạn số, dùng Jakarta Bean Validation thường là giải pháp ít mã hơn:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        @NotBlank String endpoint,
        @Min(0) @Max(10) int maxRetries) {
}
~~~

Nhưng khi cần quy tắc đặc biệt như **endpoint phải là HTTPS khi enabled=true**, hoặc timeout khác nhau theo mode, một custom Spring `Validator` là lựa chọn tự nhiên.

**Hai cơ chế có thể bổ sung cho nhau.** Jakarta constraints kiểm tra những điều đơn giản; custom Spring Validator xử lý các quan hệ phức tạp. Tránh lập lại cùng một rule hai lần vì kết quả có thể sinh thông báo lỗi trùng lặp.

Ở Spring Boot 3.x, Jakarta validation API dùng namespace `jakarta.validation.*`, khác với `javax.validation.*` của các dự án Spring Boot 2.x. Spring `Validator` vẫn là `org.springframework.validation.Validator` và không yêu cầu bạn phải tự viết một `ConstraintValidator`.

### 10.1. Có bắt buộc dependency validation không?

Nếu sử dụng Jakarta Bean Validation annotations trong ứng dụng Spring Boot 3.x, cần một implementation phù hợp, thường qua:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Ngược lại, `org.springframework.validation.Validator` là một interface của Spring Framework. Bạn có thể viết custom rule bằng API Spring và `Errors` mà không cần biến mọi rule thành Jakarta constraint. Nếu dự án sử dụng cả hai, dependency validation vẫn cần để thực thi các annotation `@NotBlank`, `@Min`, `@Valid`...

Hãy xác nhận theo dependency graph thực tế của project: một starter khác có thể đã mang implementation validation, nhưng đừng giả định điều đó trong mọi ứng dụng.

## 11. Validator chuyên dụng có phải một validator cho tất cả bean?

Một bean tên `configurationPropertiesValidator` có tính chất **chung ở mức hạ tầng configuration properties**. Vì vậy, validator triển khai cần xác định rõ type nó hỗ trợ.

Ví dụ ứng dụng có:

~~~java
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryProperties { /* ... */ }

@ConfigurationProperties(prefix = "app.cache")
public class CacheProperties { /* ... */ }

@ConfigurationProperties(prefix = "app.mail")
public class MailProperties { /* ... */ }
~~~

Nếu custom validator dành riêng cho delivery, viết:

~~~java
@Override
public boolean supports(Class<?> clazz) {
    return DeliveryProperties.class.isAssignableFrom(clazz);
}
~~~

Khi infrastructure gặp `CacheProperties` hoặc `MailProperties`, validator này không nên ép cast chúng thành `DeliveryProperties`.

Nếu dự án cần kiểm tra nhiều type bằng cùng một bean, có thể tạo một **delegating validator**:

~~~java
public final class AppConfigurationValidator implements Validator {

    private final Validator delivery = new DeliveryPropertiesValidator();
    private final Validator cache = new CachePropertiesValidator();

    @Override
    public boolean supports(Class<?> clazz) {
        return delivery.supports(clazz) || cache.supports(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        if (delivery.supports(target.getClass())) {
            delivery.validate(target, errors);
        }
        if (cache.supports(target.getClass())) {
            cache.validate(target, errors);
        }
    }
}
~~~

Ví dụ giả định `CachePropertiesValidator` đã được triển khai cùng interface Spring `Validator` và có logic không phụ thuộc các bean khởi tạo muộn.

Đăng ký một bean:

~~~java
@Bean(name = "configurationPropertiesValidator")
public static Validator configurationPropertiesValidator() {
    return new AppConfigurationValidator();
}
~~~

Với số lượng loại cấu hình tăng, có thể dùng map danh sách validators thuần Java và logic dispatch phù hợp. Tránh cố inject một danh sách validator bean khác cần khởi tạo muộn vào dedicated validator ở giai đoạn startup rất sớm.

## 12. `Errors.rejectValue` và `Errors.reject` nên dùng lúc nào?

### 12.1. Gắn lỗi vào field

Dùng `rejectValue` khi một trường cụ thể có vấn đề:

~~~java
if (properties.getConnectTimeout() == null) {
    errors.rejectValue(
            "connectTimeout",
            "delivery.timeout.required",
            "connect-timeout is required");
}
~~~

Dùng tên property JavaBean `connectTimeout` là lựa chọn phù hợp với object đang được kiểm tra. Thông báo hiển thị có thể được infrastructure ghép với đường dẫn cấu hình bên ngoài `app.delivery.connect-timeout`.

### 12.2. Gắn lỗi vào cả object

Dùng `reject` khi nhiều field kết hợp tạo ra trạng thái không hợp lệ:

~~~java
if (properties.isEnabled()
        && properties.getMaxRetries() > 5
        && properties.getConnectTimeout().compareTo(
                Duration.ofSeconds(30)) > 0) {
    errors.reject(
            "delivery.retryTimeout.incompatible",
            "Retry count and timeout are too high when delivery is enabled");
}
~~~

Đoạn trên giả định `connectTimeout` đã khác null. Trong validator thực tế phải kiểm tra null trước khi so sánh để tránh `NullPointerException`.

Thông thường hãy ưu tiên một thông báo có thể hành động: nêu điều kiện thất bại và tên trường tương ứng, thay vì chỉ viết `"Invalid configuration"`.

### 12.3. Có nên ném exception trực tiếp không?

Một validator có thể ném exception khi gặp lỗi lập trình nội bộ, nhưng với **dữ liệu cấu hình không hợp lệ**, nên dùng `Errors` để biểu diễn validation failure. Điều đó cho phép Spring đóng gói lỗi vào luồng bind/validation và hiển thị tên thuộc tính rõ ràng hơn.

Nếu cần kiểm tra một cấu hình rất đơn giản mà không muốn tạo Spring Validator, một exception ngay trong constructor hoặc `@Bean` factory method cũng có thể cho fail-fast. Tuy nhiên, đó là một **thiết kế khác**, không phải cơ chế dedicated `configurationPropertiesValidator` đang học.

## 13. Validator chạy lúc nào trong vòng đời khởi động?

Xét một flow đơn giản:

~~~text
1. main → SpringApplication.run(args)
2. Spring Boot chuẩn bị Environment và config data
3. Spring khởi tạo các bean định nghĩa hạ tầng rất sớm
4. Spring Boot lấy dedicated configurationPropertiesValidator
5. Spring tạo/bind các @ConfigurationProperties objects
6. Spring thực hiện validation theo hạ tầng binding
7. Nếu có errors → binding/validation failure
8. Nếu hợp lệ → bean được dùng bởi application services
~~~

Những chi tiết thứ tự chính xác có thể khác theo phiên bản và cách bean được đăng ký, nhưng **hợp đồng quan trọng** là dedicated validator được lấy trong giai đoạn rất sớm. Vì thế `static @Bean` giúp tránh cần khởi tạo sớm cấu hình chứa method.

Không nên xem Spring `Validator` như một listener nhận sự kiện mỗi khi người vận hành sửa `application.yml`. Spring Boot thông thường **nạp và bind config data ở startup**; việc sửa file sau khi ứng dụng chạy không tự động kích hoạt lại validation hoặc cập nhật bean. Nếu dự án có cơ chế refresh ngoài Spring Boot chuẩn, cần xem contract riêng của cơ chế đó.

## 14. Cách kiểm thử bằng `ApplicationContextRunner`

`ApplicationContextRunner` tạo một application context nhỏ với bộ cấu hình tường minh, phù hợp để kiểm tra một validator ảnh hưởng ra sao đến startup.

Dependency test thường có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Một test dùng Spring Boot 3.x:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ConfigurationPropertiesAutoConfiguration.class))
            .withUserConfiguration(
                Registration.class,
                DeliveryValidationConfiguration.class);

    @Test
    void acceptsValidConfiguration() {
        runner.withPropertyValues(
                "app.delivery.enabled=true",
                "app.delivery.endpoint=https://gateway.example.test",
                "app.delivery.connect-timeout=5s",
                "app.delivery.max-retries=3")
            .run(context -> {
                assertThat(context).hasNotFailed();
                DeliveryProperties props =
                    context.getBean(DeliveryProperties.class);
                assertThat(props.getMaxRetries()).isEqualTo(3);
            });
    }

    @Test
    void rejectsInvalidEndpointAtStartup() {
        runner.withPropertyValues(
                "app.delivery.enabled=true",
                "app.delivery.endpoint=http://unsafe.example.test",
                "app.delivery.connect-timeout=5s",
                "app.delivery.max-retries=3")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure()).isNotNull();
            });
    }

    @Test
    void rejectsOutOfRangeRetries() {
        runner.withPropertyValues(
                "app.delivery.enabled=true",
                "app.delivery.endpoint=https://gateway.example.test",
                "app.delivery.max-retries=99")
            .run(context -> {
                assertThat(context).hasFailed();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class Registration {
    }
}
~~~

Trong ví dụ:

- `Registration` đảm bảo Spring tạo và bind `DeliveryProperties`.
- `DeliveryValidationConfiguration` đăng ký dedicated validator đúng tên, bằng `static @Bean`.
- Test hợp lệ kiểm tra context chạy và bean nhận đúng giá trị.
- Test không hợp lệ kiểm tra application context **không khởi động thành công**.
- Nếu muốn kiểm tra thông báo cụ thể, có thể kiểm tra cause chain của `getStartupFailure()`; đừng buộc test phụ thuộc nguyên văn thông báo lỗi vốn có thể thay đổi giữa các phiên bản Spring Boot.

Đây là dạng kiểm thử **khả năng từ chối cấu hình sai**, không phải kiểm thử kết nối thật đến gateway. URL ví dụ `example.test` chỉ được dùng để kiểm tra cú pháp.

## 15. Unit test trực tiếp `Validator` không cần Spring context

Một phần lớn logic validator có thể kiểm tra như một class Java bình thường. Dùng `BeanPropertyBindingResult` để nhận lỗi:

~~~java
package com.example.config;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesValidatorTest {

    private final DeliveryPropertiesValidator validator =
            new DeliveryPropertiesValidator();

    @Test
    void rejectsNonHttpsEndpoint() {
        DeliveryProperties props = new DeliveryProperties();
        props.setEnabled(true);
        props.setEndpoint("http://unsafe.example.test");
        props.setConnectTimeout(Duration.ofSeconds(5));
        props.setMaxRetries(3);

        Errors errors = new BeanPropertyBindingResult(props, "delivery");
        validator.validate(props, errors);

        assertThat(errors.hasFieldErrors("endpoint")).isTrue();
    }

    @Test
    void acceptsValidSettings() {
        DeliveryProperties props = new DeliveryProperties();
        props.setEnabled(true);
        props.setEndpoint("https://gateway.example.test");
        props.setConnectTimeout(Duration.ofSeconds(5));
        props.setMaxRetries(3);

        Errors errors = new BeanPropertyBindingResult(props, "delivery");
        validator.validate(props, errors);

        assertThat(errors.hasErrors()).isFalse();
    }
}
~~~

Unit test trực tiếp giúp xác minh `supports`, field error codes và các quy tắc nghiệp vụ mà không phải tạo application context. Nhưng nó **không chứng minh** Spring Boot đã đăng ký bean đúng tên và gọi validator khi bind.

Vì vậy nên kết hợp:

- **Unit test validator:** kiểm tra logic và `Errors`.
- **Context test:** xác minh wiring bean `configurationPropertiesValidator` và fail-fast trong luồng `@ConfigurationProperties`.

Nếu chỉ có unit test, lỗi thiếu `static` hoặc đặt sai tên bean có thể chưa được phát hiện.

## 16. Phân biệt dedicated validator với web/MVC validator

Trong Spring có nhiều “validator”, nhưng không phải tất cả cùng vai trò:

| Thành phần | Phạm vi sử dụng | Được chọn như thế nào? |
| --- | --- | --- |
| `configurationPropertiesValidator` | Config properties binding/validation | Spring Boot tìm bean theo **tên đặc biệt** |
| Validator trong Spring MVC/WebDataBinder | Request form/model binding | MVC/web infrastructure và đăng ký validator |
| `LocalValidatorFactoryBean` | Adapter Jakarta Bean Validation | Validator bean/factory cho Bean Validation |
| `ConstraintValidator<A,T>` | Kiểm tra annotation constraint tùy chỉnh | Jakarta Bean Validation engine |
| `@InitBinder` validator | Bind request model của controller | Áp dụng theo controller/WebDataBinder |

Do đó, việc khai báo:

~~~java
@Override
public void addValidators(Validator... validators) {
    // Cấu hình MVC không phải cách đăng ký dedicated validator.
}
~~~

hoặc cấu hình `@InitBinder` không thay thế một bean mang tên `configurationPropertiesValidator`.

Tương tự, bean có tên `validator` dùng trong cơ chế khác không mặc nhiên là configuration properties validator. **Tên bean chính xác và interface Spring Validator** là hai thành phần cần có.

## 17. Phối hợp custom Validator với Jakarta constraints

Một class có thể sử dụng `@Validated` cùng Jakarta constraints:

~~~java
package com.example.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public class DeliveryProperties {

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(5);

    @Min(0)
    @Max(10)
    private int maxRetries = 2;

    private boolean enabled;
    private String endpoint;

    // getters và setters như mô hình phần 6
}
~~~

Khi dùng phiên bản này, Jakarta validation có thể kiểm tra `connectTimeout` khác null và `maxRetries` trong khoảng 0..10. Custom validator tiếp tục kiểm tra URL HTTPS và giới hạn timeout không quá 60 giây.

Không cần viết hai lần cùng rule `maxRetries >= 0 && <= 10`. Nếu bạn giữ check này trong custom validator vì muốn học cơ chế, hãy hiểu nó có thể trùng với `@Min/@Max`; dự án thật nên chọn vị trí hợp lý cho mỗi ràng buộc.

### 17.1. Cross-field rule

Một ví dụ tự nhiên cho Spring Validator: khi `enabled=true`, `endpoint` phải có; khi `enabled=false`, cho phép bỏ trống.

Ràng buộc kiểu “trường A bắt buộc **chỉ khi** trường B có giá trị C” khó biểu đạt đẹp bằng các annotation trường độc lập. Custom validator có quyền đọc toàn bộ object và gọi `errors.rejectValue(...)` trên trường không hợp lệ.

### 17.2. Nested properties

Giả sử có:

~~~yaml
app:
  delivery:
    security:
      mode: bearer
      token: "${DELIVERY_TOKEN}"
~~~

Nếu object có một field nested `Security security`, custom validator có thể kiểm tra `security.getMode()` và `security.getToken()`. Cần kiểm tra `security != null` trước, và dùng đúng đường dẫn field nếu gọi `rejectValue` cho field nested, ví dụ `"security.token"`.

Với Jakarta Bean Validation, nested object thường cần `@Valid` để cascade validation. Với Spring `Validator` tự viết, bạn cũng có thể dùng `errors.pushNestedPath("security")`, sau đó gọi validator con rồi `popNestedPath()`, nhưng nên quản lý path trong `try/finally` để không làm lệch trạng thái error collector.

Không bao giờ đưa giá trị token vào thông báo lỗi.

## 18. Tính an toàn khi validate credentials và URL

Validator có thể được dùng để kiểm tra thông tin nhạy cảm, nhưng nên tránh những thao tác có side effect hoặc làm lộ dữ liệu.

**Nên làm:**

- Kiểm tra secret khác null/blank mà không log nó.
- Kiểm tra URL có scheme cho phép và host hợp lệ.
- Kiểm tra khoảng thời gian timeout và retry trong giới hạn.
- Kiểm tra tên queue/topic theo một pattern rõ ràng.
- Nêu tên field lỗi trong message.

**Không nên làm:**

- Gọi HTTP đến endpoint từ validator chỉ để kiểm tra reachability.
- Truy cập DB để xác minh mật khẩu trong giai đoạn early startup.
- Ghi log toàn bộ object cấu hình có `password` hoặc `apiKey`.
- Đưa user-supplied URL có chứa token trong query vào exception message.
- Tự sửa dữ liệu cấu hình hoặc property source trong `validate(...)`.

Mục đích của validator là **đọc và đánh giá trạng thái**, không phải tạo kết nối hạ tầng hay thay đổi giá trị đã bind. Những kiểm tra thực sự cần mạng nên thuộc cơ chế kiểm tra kết nối, readiness hoặc startup health với timeout và retry thích hợp.

## 19. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Validator không được gọi khi bind | Bean không mang tên chính xác `configurationPropertiesValidator` | Khai báo `@Bean(name = "configurationPropertiesValidator")` |
| Bean mang đúng tên nhưng không hoạt động | Lớp `@Configuration` không được Spring scan/import | Đặt trong vùng scan hoặc dùng `@Import` |
| Warning early bean creation | `@Bean` không phải `static`, hoặc có dependency khởi tạo quá sớm | Dùng `static` và giữ validator độc lập |
| `ClassCastException` trong `validate` | `supports` trả về `true` với type không được hỗ trợ | Thu hẹp `supports` theo class cụ thể |
| Startup không fail khi endpoint sai | Rule không gọi `errors.rejectValue`, bean chưa bind/validate, hoặc wiring sai | Unit test validator và context test riêng |
| Có nhiều bean cùng tên | Nhiều module định nghĩa `configurationPropertiesValidator` | Tập trung vào một bean/delegating validator |
| Không tìm được property trong object | Tên YAML sai hoặc thiếu cấu hình | Kiểm tra prefix và relaxed binding |
| Không parse được `connect-timeout` | Giá trị sai định dạng `Duration` | Sửa input trước khi logic validator chạy |
| Validation message không nói rõ trường | Dùng `errors.reject` cho lỗi vốn thuộc một field | Cân nhắc `rejectValue` với field Java thích hợp |
| Test validator pass nhưng ứng dụng vẫn không kiểm tra | Unit test không xác minh Spring Boot integration | Thêm `ApplicationContextRunner` test |
| Bean Validation annotations không có hiệu lực | Thiếu `@Validated` hoặc implementation phù hợp | Bổ sung cấu hình và `spring-boot-starter-validation` |
| Validator truy cập repository rất sớm và lỗi startup | Phụ thuộc vào bean nghiệp vụ chưa sẵn sàng | Bỏ IO/dependencies muộn khỏi custom validator |
| Kiểm tra secret làm lộ log | In toàn bộ object hoặc actual rejected value | Chỉ nêu field và policy vi phạm |

Một số startup failures được Spring Boot bọc nhiều lớp exception, ví dụ lỗi tạo bean hoặc lỗi bind `@ConfigurationProperties`. Khi chẩn đoán, hãy đọc nguyên nhân gốc (root cause) cùng field/error code và source precedence; không nên chỉ dựa vào dòng đầu tiên của stack trace.

## 20. Khi nào nên dùng dedicated `configurationPropertiesValidator`?

Cách này phù hợp khi:

1. Có các **quy tắc validation xuyên nhiều trường** khó biểu đạt bằng những annotation riêng lẻ.
2. Muốn logic kiểm tra nằm ngoài properties object để properties type chỉ giữ dữ liệu.
3. Cần kết hợp nhiều kiểu `@ConfigurationProperties` bằng một validator tổng có `supports` rõ ràng.
4. Muốn sử dụng Spring `Errors` và các field error codes có thể được kiểm thử độc lập.
5. Muốn fail-fast trong giai đoạn bind configuration properties thay vì đặt kiểm tra rải rác ở service.

Không nhất thiết cần dedicated validator khi chỉ có một vài điều kiện đơn giản:

~~~java
@NotBlank String endpoint;
@Min(1) int poolSize;
@NotNull Duration timeout;
~~~

Với các ràng buộc đó, `@Validated` và Jakarta Bean Validation thường ít mã hơn. Chọn custom validator khi nó giúp thiết kế **rõ rule hơn**, không chỉ vì tên cơ chế nghe mạnh hơn.

Một lựa chọn khác là validate trong constructor/compact constructor của immutable class hoặc record. Cách này bảo đảm invariant ngay khi object được tạo thủ công nhưng không có cùng mô hình `Errors`/field error codes; cũng không thay thế việc đăng ký dedicated validator nếu mục tiêu là tích hợp rule ở mức binder.

## 21. Bài tập tình huống

### 21.1. Đề bài

Cho YAML:

~~~yaml
app:
  delivery:
    enabled: true
    endpoint: http://gateway.example.test
    connect-timeout: -5s
    max-retries: 20
~~~

Đã đăng ký:

~~~java
@Bean(name = "configurationPropertiesValidator")
public static Validator configurationPropertiesValidator() {
    return new DeliveryPropertiesValidator();
}
~~~

Và `DeliveryProperties` được scan bằng `@ConfigurationPropertiesScan`.

**Câu hỏi 1:** Có mấy quy tắc trong validator ở phần 7 bị vi phạm?

**Đáp án:** Ít nhất ba:
- `endpoint` dùng HTTP thay vì HTTPS.
- `connect-timeout` là khoảng thời gian âm.
- `max-retries=20` vượt giới hạn 10.

Validator có thể gọi `errors.rejectValue(...)` cho cả ba trường, giúp lỗi startup rõ ràng hơn.

**Câu hỏi 2:** Nếu sửa `connect-timeout` thành `"not-a-duration"`, lỗi đến từ đâu?

**Đáp án:** Conversion/binding sang `Duration` có thể thất bại **trước** bước kiểm tra semantic timeout trong validator. Đây không phải trường hợp cần `errors.rejectValue` cho một `Duration` đã được bind hợp lệ.

**Câu hỏi 3:** Nếu đặt tên bean là `customPropertiesValidator` thì sao?

**Đáp án:** Không đáp ứng hợp đồng tên `configurationPropertiesValidator`. Validator này không tự được Boot nhận làm dedicated configuration-properties validator chỉ bởi kiểu `Validator`.

**Câu hỏi 4:** Nếu bỏ `static`, application chắc chắn không chạy được không?

**Đáp án:** Không nhất thiết. Nhưng cách đó tạo nguy cơ bean `@Configuration` bị khởi tạo quá sớm và sinh vấn đề lifecycle; tài liệu Spring Boot khuyến nghị mạnh mẽ khai báo method `static`.

**Câu hỏi 5:** Nếu validator luôn `supports(...)=true` và app có thêm `CacheProperties` thì sao?

**Đáp án:** Khi validator nhận target không phải `DeliveryProperties`, phép cast có thể ném `ClassCastException`. Nên giới hạn `supports` theo type hoặc dùng delegating validator có dispatch theo class.

### 21.2. Bài tập mở rộng: kiểm tra quan hệ giữa timeout và retry

Thêm quy tắc:

~~~text
Nếu enabled = true:
    maxRetries * connectTimeout <= 120s
~~~

Với Java:

~~~java
if (props.isEnabled()
        && props.getConnectTimeout() != null
        && !props.getConnectTimeout().isNegative()
        && props.getMaxRetries() >= 0) {
    long timeoutSeconds = props.getConnectTimeout().getSeconds();
    if (timeoutSeconds > 0
            && props.getMaxRetries() > 0
            && timeoutSeconds > 120L / props.getMaxRetries()) {
        errors.reject(
                "delivery.retryBudget.exceeded",
                "Total retry timeout budget must not exceed 120s");
    }
}
~~~

Ý tưởng kiểm tra `timeoutSeconds > 120L / maxRetries` giúp tránh phép nhân long trực tiếp khi đánh giá giới hạn, nhưng ví dụ làm tròn xuống giây, nên không phù hợp nếu yêu cầu chính xác đến mili giây hoặc nano giây. Khi cần chính xác, dùng phép so sánh `Duration` hoặc số nanosecond có xử lý overflow và giới hạn hợp lý.

Hãy viết thêm unit test cho các trường hợp `enabled=false`, `maxRetries=0`, `timeout=30s` với bốn lần retry và `timeout=60s` với ba lần retry.

## 22. Ghi nhớ

- **Tên bean bắt buộc:** `configurationPropertiesValidator`, đúng camelCase.
- **Kiểu:** `org.springframework.validation.Validator`, gồm `supports(Class<?>)` và `validate(Object, Errors)`.
- **Khai báo:** `@Bean(name = "configurationPropertiesValidator")` và phương thức factory `static` để tránh khởi tạo sớm lớp `@Configuration`.
- **Phạm vi:** `supports` nên chỉ nhận những `@ConfigurationProperties` type mà validator hiểu, tránh cast sai.
- **Báo lỗi:** dùng `errors.rejectValue(...)` cho field và `errors.reject(...)` cho rule cấp object; không log giá trị secret.
- **Phối hợp:** `@Validated` + Jakarta Bean Validation hữu ích cho ràng buộc khai báo; custom Spring Validator hữu ích cho logic cross-field.
- **Lỗi startup:** giá trị sai type có thể fail ở binding trước; lỗi semantic có thể fail khi validate nếu bean được đăng ký và tạo theo luồng configuration properties.
- **Kiểm thử:** unit test trực tiếp Validator và context test xác minh bean đúng tên, đúng thời điểm, đúng hành vi.
- **Không làm IO:** dedicated validator được tạo rất sớm; tránh dependency graph phức tạp, database, network và side effects.

### Tài liệu tham khảo

- Spring Boot Reference — Externalized Configuration, `@ConfigurationProperties` Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework Reference — Validation by Using Spring's Validator Interface: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Javadoc — Validator: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Validator.html
- Spring Framework Javadoc — Errors: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Errors.html
