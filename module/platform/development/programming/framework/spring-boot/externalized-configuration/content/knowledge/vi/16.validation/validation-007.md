# Ràng buộc quan hệ giữa nhiều trường cấu hình

## 1. Bài toán: từng trường hợp lệ nhưng toàn bộ cấu hình lại sai

Trong Spring Boot Externalized Configuration, một ứng dụng có thể nhận thông số từ **application.yml**, **application.properties**, biến môi trường, command-line, file bên ngoài hoặc các PropertySource khác. **@ConfigurationProperties** ánh xạ các giá trị đó thành một object Java có kiểu. **Bean Validation** giúp phát hiện dữ liệu thiếu hoặc không hợp lệ.

Các annotation như **@NotNull**, **@Min**, **@Max**, **@NotBlank** giải quyết rất tốt **ràng buộc trên từng trường**. Nhưng không phải mọi quy tắc nghiệp vụ đều kiểm tra được một field riêng lẻ.

Ví dụ:

~~~yaml
demo:
  http-client:
    connect-timeout: 8s
    request-timeout: 3s
~~~

Hai chuỗi **8s** và **3s** đều có thể chuyển thành **Duration** hợp lệ. Thế nhưng nếu quy ước của client là **request-timeout phải lớn hơn connect-timeout**, cặp giá trị này mâu thuẫn.

Ví dụ khác:

~~~yaml
demo:
  retry:
    enabled: true
    initial-delay: 5s
    max-delay: 1s
    max-attempts: 3
~~~

**initial-delay** và **max-delay** đều hợp lệ nếu xét riêng. Nhưng **initial-delay > max-delay** vi phạm quy tắc retry. Hoặc một chức năng được bật bằng **enabled: true** nhưng thiếu URL bắt buộc trong chế độ bật.

Đó là **cross-field validation**, hay **kiểm tra ràng buộc quan hệ giữa nhiều trường cấu hình**.

Bài học này hướng dẫn:

1. Phân biệt lỗi chuyển kiểu, validation từng field và validation quan hệ nhiều field.
2. Dùng **@Validated** và **jakarta.validation** để validate **@ConfigurationProperties**.
3. Biểu diễn quy tắc đơn giản bằng **@AssertTrue** trên một JavaBean getter.
4. Viết custom constraint ở cấp class bằng **@Constraint** và **ConstraintValidator**.
5. Gắn thông báo lỗi vào đúng property bằng **ConstraintValidatorContext**.
6. Validate nested object với **@Valid**, xử lý **null** và các điều kiện bật/tắt.
7. Kiểm thử cả cấu hình hợp lệ và không hợp lệ bằng **ApplicationContextRunner**.
8. Phân biệt ràng buộc trong một object với ràng buộc giữa nhiều configuration beans.
9. Thiết kế fail-fast, tránh lỗi runtime do cấu hình chỉ sai khi đặt cạnh nhau.

Bối cảnh: **Spring Boot 3.3.x**, **Java 21**, **Jakarta Bean Validation** và ví dụ đơn giản không phụ thuộc kết nối mạng thật.

## 2. Ba tầng cần phân biệt

Trước khi viết validation, cần tách ba vấn đề:

| Tầng | Ví dụ | Phát hiện bằng |
| --- | --- | --- |
| **Chuyển kiểu / binding** | **connect-timeout: abc** không chuyển được sang Duration | Spring Boot Binder và ConversionService |
| **Ràng buộc một field** | **max-attempts: 0** vi phạm tối thiểu 1 | **@Min(1)**, **@NotNull**, **@NotBlank**, v.v. |
| **Ràng buộc nhiều field** | **request-timeout <= connect-timeout** dù từng Duration hợp lệ | **@AssertTrue**, custom class-level constraint hoặc validator riêng |

Một ví dụ rõ hơn:

~~~text
connect-timeout = 5s       -> đúng kiểu Duration
request-timeout = 2s       -> đúng kiểu Duration
                              nhưng sai quan hệ timeout

max-attempts = 0           -> đúng kiểu int
                              nhưng sai ràng buộc @Min(1)

connect-timeout = invalid  -> sai ngay ở bước chuyển kiểu
~~~

**Đừng cố dùng @Min hoặc @Max cho hai field Duration rồi tưởng rằng đã kiểm tra được thứ tự giữa chúng.** Validation từng trường và validation quan hệ giải quyết những yêu cầu khác nhau.

Mục đích của cross-field validation là từ chối cấu hình **tổng thể không nhất quán**, trước khi logic nghiệp vụ bắt đầu sử dụng.

## 3. Khai báo dependency cần thiết

Trong Spring Boot 3.3, các constraint Bean Validation dùng package **jakarta.validation**. Cần có một implementation tương thích trên classpath, và cách thông dụng là thêm **spring-boot-starter-validation**.

### 3.1. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

### 3.2. Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Nếu dự án dùng **spring-boot-starter-web**, đừng mặc định rằng starter-validation đã được kéo vào trong mọi phiên bản hoặc cấu hình build. Hãy khai báo dependency validation khi dự án cần nó.

Một số annotation dùng trong bài:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.validation.annotation.Validated;
~~~

**jakarta.validation** là namespace phù hợp với Spring Boot 3.3. Ví dụ cũ dùng **javax.validation** từ Spring Boot 2.x không nên được sao chép nguyên xi sang dự án Boot 3.x.

## 4. Bước đầu: tạo configuration model có cấu trúc

Giả sử một HTTP client có các yêu cầu:

- **base-url** bắt buộc.
- **connect-timeout** bắt buộc.
- **request-timeout** bắt buộc.
- Retry có số lần thử và khoảng trì hoãn.
- **request-timeout > connect-timeout**.
- Nếu retry được bật thì **initial-delay <= max-delay** và **max-attempts >= 1**.

Định nghĩa một Java record:

~~~java
package com.example.crossfield;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.http-client")
public record HttpClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            boolean enabled,
            Integer maxAttempts,
            Duration initialDelay,
            Duration maxDelay) {
    }
}
~~~

Đây là **model xuất phát** để giải thích các cách validation; các mục sau bổ sung ràng buộc vào model đó.

### 4.1. YAML có dữ liệu hợp lệ

~~~yaml
demo:
  http-client:
    base-url: "https://api.example.invalid"
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      enabled: true
      max-attempts: 3
      initial-delay: 250ms
      max-delay: 3s
~~~

Tất cả giá trị đều dùng URL giả và Duration. Không cần thực hiện kết nối thật để kiểm tra binding.

### 4.2. Khởi tạo configuration properties

Một cách đăng ký type là **@ConfigurationPropertiesScan**:

~~~java
package com.example.crossfield;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CrossFieldApplication {

    public static void main(String[] args) {
        SpringApplication.run(CrossFieldApplication.class, args);
    }
}
~~~

Một cách thay thế là **@EnableConfigurationProperties(HttpClientProperties.class)** trên một configuration class. Với record constructor binding, nên dùng scanning hoặc enable theo cơ chế Spring Boot hỗ trợ, thay vì chỉ gắn **@Component** vào record.

### 4.3. Vai trò của @Validated

**@Validated** trên class **@ConfigurationProperties** yêu cầu Spring Boot thực hiện validation với các constraint hỗ trợ.

**@NotNull** kiểm tra một giá trị cần có; **@Valid** yêu cầu Bean Validation xét tiếp nested object. Nếu chỉ có binding mà không có validation, Binder có thể tạo object dù các điều kiện nghiệp vụ chưa thỏa mãn.

Nhưng ngay cả khi cả hai Duration đều **@NotNull**, Spring Boot vẫn không tự suy ra quy tắc **requestTimeout > connectTimeout**. Ta phải khai báo quy tắc quan hệ.

## 5. Cách 1: @AssertTrue cho một quan hệ đơn giản

**@AssertTrue** từ Jakarta Bean Validation yêu cầu một giá trị boolean/Boolean là true. Khi đặt nó trên một JavaBean getter được nhận diện là property, có thể dùng một phương thức suy ra điều kiện từ nhiều field.

Ví dụ một JavaBean riêng, mutable:

~~~java
package com.example.crossfield;

import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.timeout")
public class TimeoutProperties {

    @NotNull
    private Duration connectTimeout;

    @NotNull
    private Duration requestTimeout;

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }

    @AssertTrue(
        message = "request-timeout phải lớn hơn connect-timeout")
    public boolean isTimeoutOrderValid() {
        if (connectTimeout == null || requestTimeout == null) {
            return true;
        }
        return requestTimeout.compareTo(connectTimeout) > 0;
    }
}
~~~

Cấu hình hợp lệ:

~~~properties
demo.timeout.connect-timeout=2s
demo.timeout.request-timeout=10s
~~~

Cấu hình không hợp lệ:

~~~properties
demo.timeout.connect-timeout=8s
demo.timeout.request-timeout=3s
~~~

**isTimeoutOrderValid()** là một getter boolean có tên JavaBean, nên có thể được Bean Validation nhận diện như thuộc tính suy ra. Nó không cần có setter vì ta không muốn Binder cấp giá trị **timeout-order-valid** từ file cấu hình.

### 5.1. Vì sao trả true nếu có null?

Điều kiện quan hệ chỉ có nghĩa khi cả hai Duration đã tồn tại. **@NotNull** trên từng field chịu trách nhiệm báo thiếu dữ liệu.

Nếu method trả false khi một trường null, người triển khai có thể thấy đồng thời:

- Lỗi **connect-timeout không được để trống**.
- Lỗi **thứ tự timeout không hợp lệ**.

Thông báo thứ hai có thể gây nhiễu vì thực tế chưa thể so sánh hai giá trị. Vì vậy, một cách thiết kế tốt là **bỏ qua kiểm tra quan hệ khi thiếu input**, để constraint đơn trường giải thích lỗi thiếu trước.

### 5.2. Ưu điểm và giới hạn của @AssertTrue

Ưu điểm:

- Không cần tự viết annotation và ConstraintValidator.
- Gọn cho quan hệ hai field đơn giản.
- Dễ test và đọc ở class nhỏ.

Giới hạn:

- Method boolean suy ra có thể xuất hiện trong công cụ introspection hoặc được xem là một bean property.
- Lỗi thường gắn vào property suy ra như **timeoutOrderValid**, không trực tiếp vào **requestTimeout**.
- Nếu có nhiều nhánh điều kiện và nhiều thông báo lỗi, một method boolean khó diễn đạt chi tiết.
- Với ràng buộc tái sử dụng ở nhiều type, custom class-level constraint dễ bảo trì hơn.

Dùng cách này khi chỉ cần một hoặc vài điều kiện đơn giản, thông báo lỗi có thể mang tính tổng hợp.

## 6. Cách 2: custom constraint ở cấp class

Khi cần so sánh nhiều trường, muốn tái sử dụng quy tắc hoặc định vị lỗi rõ, có thể tạo một **Jakarta Bean Validation constraint** đặt trên class/record.

Ví dụ chính: **request-timeout phải lớn hơn connect-timeout**.

Quy trình gồm:

1. Tạo annotation **@ValidTimeoutWindow**.
2. Tạo **ConstraintValidator<ValidTimeoutWindow, HttpClientProperties>**.
3. Gắn annotation lên **HttpClientProperties**.
4. Đảm bảo class có **@Validated** và validation implementation.
5. Chạy test với các tổ hợp hợp lệ/không hợp lệ.

### 6.1. Annotation @ValidTimeoutWindow

~~~java
package com.example.crossfield;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = TimeoutWindowValidator.class)
public @interface ValidTimeoutWindow {

    String message() default
            "request-timeout phải lớn hơn connect-timeout";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Các thành phần chính:

- **@Target(TYPE)**: constraint đặt trên cả object, không phải một field riêng.
- **@Retention(RUNTIME)**: annotation còn tồn tại khi validator chạy.
- **@Constraint(validatedBy = ...)**: trỏ tới class kiểm tra.
- **message**: thông báo mặc định khi điều kiện sai.
- **groups** và **payload**: các phần tiêu chuẩn của custom Bean Validation constraint.

Annotation được khai báo trong code ứng dụng, không phải là một annotation built-in của Spring Boot. Tên **ValidTimeoutWindow** chỉ là tên minh họa.

### 6.2. Validator so sánh hai Duration

~~~java
package com.example.crossfield;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class TimeoutWindowValidator
        implements ConstraintValidator<
            ValidTimeoutWindow, HttpClientProperties> {

    @Override
    public boolean isValid(
            HttpClientProperties value,
            ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        if (value.connectTimeout() == null
                || value.requestTimeout() == null) {
            return true;
        }

        boolean valid = value.requestTimeout()
                .compareTo(value.connectTimeout()) > 0;

        if (valid) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context.buildConstraintViolationWithTemplate(
                "request-timeout phải lớn hơn connect-timeout")
                .addPropertyNode("requestTimeout")
                .addConstraintViolation();

        return false;
    }
}
~~~

Validator chỉ làm một việc: kiểm tra quan hệ giữa **hai field** đã được bind thành Duration.

Biểu thức:

~~~java
requestTimeout.compareTo(connectTimeout) > 0
~~~

có nghĩa:

~~~text
requestTimeout > connectTimeout
~~~

Nếu quy tắc thực tế cho phép bằng nhau, thay **> 0** bằng **>= 0**. Quyết định đó phải dựa trên hợp đồng của HTTP client hoặc nghiệp vụ, không mặc định một công thức phù hợp mọi hệ thống.

### 6.3. Gắn constraint vào HttpClientProperties

~~~java
package com.example.crossfield;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ValidTimeoutWindow
@ConfigurationProperties(prefix = "demo.http-client")
public record HttpClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            boolean enabled,
            Integer maxAttempts,
            Duration initialDelay,
            Duration maxDelay) {
    }
}
~~~

**Đây là phiên bản hoàn thiện cho bài minh họa**, thay thế cho record chưa gắn constraint ở mục 4. Không đăng ký đồng thời hai bản cùng tên/class trong cùng project.

Spring Boot bind các trường từ Config Data trước, sau đó validation dùng object với giá trị đã được chuyển kiểu.

## 7. Gắn lỗi vào property cụ thể bằng ConstraintValidatorContext

Một constraint đặt trên class thường tạo vi phạm gắn vào **object tổng thể**. Trong một số hệ thống, thông báo chỉ cho biết object không hợp lệ, mà không chỉ rõ field cần sửa.

Đoạn này trong validator:

~~~java
context.disableDefaultConstraintViolation();

context.buildConstraintViolationWithTemplate(
        "request-timeout phải lớn hơn connect-timeout")
        .addPropertyNode("requestTimeout")
        .addConstraintViolation();
~~~

yêu cầu Bean Validation tạo violation với đường property trỏ tới trường Java **requestTimeout**, thay vì chỉ gắn vào object tổng.

Một lợi ích là khi phát hiện lỗi, người vận hành dễ liên hệ với property canonical:

~~~text
demo.http-client.request-timeout
~~~

Tên trong **addPropertyNode(...)** thường sử dụng tên property Java được Bean Validation hiểu, ví dụ **requestTimeout**, không phải tùy tiện đưa cả chuỗi **demo.http-client.request-timeout** vào như một property node.

**Thông điệp chính:** khi cần báo cho người vận hành một key cụ thể nên sửa, có thể dùng **ConstraintValidatorContext** để mô tả đường vi phạm một cách rõ ràng.

Nếu bạn muốn lỗi áp dụng đồng thời cho hai field, có thể xây nhiều violation theo các node khác nhau. Tuy nhiên, nên tránh tạo quá nhiều thông báo giống hệt gây nhiễu.

## 8. Cross-field validation với nested object

Một nhóm cấu hình có thể chứa **retry** như object con.

Yêu cầu:

- **retry.enabled = false**: không cần áp dụng các quy tắc retry đang bật.
- **retry.enabled = true**: **max-attempts >= 1**, **initial-delay** và **max-delay** phải có.
- Khi bật retry, **initial-delay <= max-delay**.
- Theo nhu cầu nghiệp vụ, cả hai delay phải lớn hơn 0.

Đây là một quy tắc có điều kiện, không chỉ là hai số cần so sánh.

### 8.1. Dùng @AssertTrue trên record con

Có thể thêm method boolean có quy tắc rõ ràng vào nested record:

~~~java
package com.example.crossfield;

import java.time.Duration;
import jakarta.validation.constraints.AssertTrue;

public record RetrySettings(
        boolean enabled,
        Integer maxAttempts,
        Duration initialDelay,
        Duration maxDelay) {

    @AssertTrue(message =
        "Khi bật retry, max-attempts và khoảng delay phải hợp lệ")
    public boolean isRetryPolicyConsistent() {

        if (!enabled) {
            return true;
        }

        if (maxAttempts == null || maxAttempts < 1
                || initialDelay == null || maxDelay == null) {
            return false;
        }

        if (initialDelay.isNegative()
                || initialDelay.isZero()
                || maxDelay.isNegative()
                || maxDelay.isZero()) {
            return false;
        }

        return initialDelay.compareTo(maxDelay) <= 0;
    }
}
~~~

Với kiểu này, khi retry bị tắt, method trả **true** bất kể các trường retry không được cấp. Khi bật, method kiểm tra đầy đủ.

Nếu nested object được dùng trong một parent record:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

public record WrapperProperties(
        @Valid @NotNull RetrySettings retry) {
}
~~~

thì **@Valid** cho phép Bean Validation kiểm tra constraint nằm ở RetrySettings.

**Điểm lưu ý:** ví dụ **RetrySettings** độc lập ở đây minh họa một lựa chọn thiết kế. Trong project bài tập, có thể đổi nested record **HttpClientProperties.Retry** thành một record tương đương có method này, thay vì khai báo hai kiểu retry cạnh nhau.

### 8.2. Tránh dùng @NotNull vô điều kiện cho field chỉ cần khi bật

Nếu đặt:

~~~java
@NotNull Duration initialDelay
~~~

trực tiếp lên một cấu hình có **enabled = false**, Bean Validation có thể báo lỗi vì thiếu initial-delay dù cơ chế retry đang tắt.

Nếu hợp đồng nói những field chỉ **bắt buộc khi enabled = true**, nên đặt logic yêu cầu trong constraint quan hệ hoặc dùng validation groups được thiết kế cẩn thận.

Một cách khác là luôn yêu cầu đầy đủ retry settings dù tính năng có bật hay không. Cách nào đúng tùy hợp đồng cấu hình. Điều quan trọng là **đừng để annotation từng field mâu thuẫn với điều kiện nghiệp vụ**.

## 9. @Valid giúp kiểm tra nested object, không phải phép so sánh tự động

Trong Java record:

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.http-client")
public record HttpClientProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry) {
}
~~~

**@Valid** nói với Bean Validation rằng cần đi sâu kiểm tra constraint trong **retry**, nếu object đó tồn tại.

**@NotNull** nói rằng retry object phải tồn tại.

Nhưng **@Valid không tự so sánh retry.initialDelay với retry.maxDelay**. Bạn vẫn phải khai báo constraint ở lớp con hoặc viết một custom validator có khả năng đọc những trường đó.

Tương tự, nếu một nested object có constraint mà parent không khai báo **@Valid**, việc validate parent có thể không đi sâu vào các constraint của nested type như bạn kỳ vọng.

Tài liệu Spring Boot cũng nhấn mạnh **@Valid** khi cần luôn kích hoạt validation của nested properties, kể cả khi không có property bên ngoài ở nhánh đó. Với record constructor binding, nếu thiếu toàn bộ nhánh thì nested object có thể không được tạo; kết hợp **@NotNull**, default binding hoặc thiết kế constructor phù hợp theo hợp đồng thực tế.

## 10. Nguyên tắc về null, giá trị thiếu và thứ tự kiểm tra

Cross-field validation nên xét ba khả năng:

1. **Dữ liệu không bind được**: ví dụ **connect-timeout: wrong**.
2. **Dữ liệu bind được nhưng bị thiếu**: ví dụ không có **request-timeout**.
3. **Dữ liệu có đủ nhưng quan hệ sai**: ví dụ **connect-timeout=9s**, **request-timeout=3s**.

Một validator chỉ so sánh hai Duration thường nên viết:

~~~java
if (value.connectTimeout() == null
        || value.requestTimeout() == null) {
    return true;
}
~~~

Đây không phải bỏ qua lỗi thiếu. Các annotation **@NotNull** kiểm tra lỗi đó một cách trực tiếp.

Khi dữ liệu không bind được, Binder có thể dừng hoặc báo lỗi trước khi tạo một object hoàn chỉnh. Không nên dựa vào một validator quan hệ để xử lý chuỗi lỗi chuyển kiểu.

### 10.1. Tránh NullPointerException trong validator

Không viết:

~~~java
return value.requestTimeout()
        .compareTo(value.connectTimeout()) > 0;
~~~

nếu các field có thể null và bạn chưa bảo đảm chúng tồn tại.

Một validator gây **NullPointerException** sẽ tạo thông báo khó hiểu hơn rất nhiều so với constraint violation đúng nghĩa.

### 10.2. Không nhầm parse thành công với giá trị hợp lệ

Spring Boot có thể bind:

~~~text
connect-timeout = -2s
request-timeout = 0s
~~~

thành các Duration có giá trị âm hoặc zero. Nếu ứng dụng yêu cầu cả hai phải dương, hãy thêm validation riêng.

Các annotation chuẩn **@Min** và **@Positive** chủ yếu dành cho kiểu số phù hợp; không nên gắn trực tiếp lên **Duration** rồi mặc định sẽ có validator tương thích. Có thể dùng custom constraint, method boolean hoặc một logic bảo vệ phù hợp.

## 11. Một trường hợp có điều kiện: bật chức năng thì URL bắt buộc

Ví dụ hệ thống có tính năng webhook:

~~~yaml
demo:
  webhook:
    enabled: true
    url: ""
~~~

Nếu tính năng tắt, URL có thể bỏ trống. Nếu tính năng bật, URL phải được cấu hình.

Một record:

~~~java
package com.example.crossfield;

import java.net.URI;
import jakarta.validation.constraints.AssertTrue;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.webhook")
public record WebhookProperties(
        boolean enabled,
        URI url) {

    @AssertTrue(message =
        "url là bắt buộc khi webhook.enabled=true")
    public boolean isWebhookConfigurationValid() {
        return !enabled || url != null;
    }
}
~~~

Với ví dụ này, field **url** dùng **URI**; giá trị rỗng có thể chuyển thành một URI rỗng tùy converter/nguồn, vì vậy khi yêu cầu URL thật sự có scheme và host, cần validate nội dung sâu hơn thay vì chỉ dựa vào null.

Một cách minh bạch hơn nếu cần kiểm tra chuỗi:

~~~java
@Validated
@ConfigurationProperties(prefix = "demo.webhook")
public record WebhookTextProperties(
        boolean enabled,
        String url) {

    @AssertTrue(message = "Phải có url khi bật webhook")
    public boolean isConfigured() {
        return !enabled || (url != null && !url.isBlank());
    }
}
~~~

Hai record chỉ là những **phương án minh họa**. Khi thiết kế production, cân nhắc dùng kiểu URI cùng custom validator kiểm tra scheme, host và những ràng buộc bảo mật cần thiết.

### 11.1. Không dùng một regex dài thay cho mô hình rõ ràng

Một regex trên URL không thể giải quyết tất cả quy tắc:

- URL chỉ bắt buộc khi enabled?
- Có cho phép HTTP trong môi trường local không?
- Có bắt buộc HTTPS ở production không?
- Có cho phép domain nội bộ không?
- Có thể khai báo cả token và username/password cùng lúc không?

Đây là các quy tắc quan hệ; hãy biểu diễn chúng bằng model và validator có thể đọc được.

## 12. Quan hệ loại trừ lẫn nhau: chỉ chọn một chế độ cấu hình

Một số hệ thống hỗ trợ hai cách xác thực:

- Dùng **api-key**.
- Dùng cặp **username/password**.

Không muốn cho phép cấu hình đồng thời cả hai, hoặc không có cách nào.

Ví dụ record:

~~~java
package com.example.crossfield;

import jakarta.validation.constraints.AssertTrue;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.auth")
public record AuthProperties(
        String apiKey,
        String username,
        String password) {

    @AssertTrue(message =
        "Chọn đúng một cơ chế: api-key hoặc username/password")
    public boolean isExactlyOneAuthModeConfigured() {

        boolean hasApiKey =
                apiKey != null && !apiKey.isBlank();

        boolean hasUsername =
                username != null && !username.isBlank();

        boolean hasPassword =
                password != null && !password.isBlank();

        boolean hasUserPassword = hasUsername && hasPassword;
        boolean incompletePair = hasUsername != hasPassword;

        if (incompletePair) {
            return false;
        }

        return hasApiKey ^ hasUserPassword;
    }
}
~~~

Biểu thức **^** là XOR đối với boolean: chỉ đúng khi một trong hai chế độ được chọn.

Các tổ hợp:

| api-key | username/password | Kết quả |
| --- | --- | --- |
| Có | Không | Hợp lệ |
| Không | Đầy đủ | Hợp lệ |
| Có | Đầy đủ | Không hợp lệ |
| Không | Không | Không hợp lệ |
| Không | Thiếu một trường | Không hợp lệ |

**Đừng in giá trị api-key/password vào log hoặc thông báo validation.** Nếu phải chẩn đoán, chỉ báo tên key nào thiếu hoặc xung đột.

Ví dụ trên dùng String để minh họa quan hệ lựa chọn. Trong ứng dụng thực, việc lưu/đọc credential phải tuân thủ cơ chế secret và quyền truy cập thích hợp.

## 13. Ràng buộc nhiều trường trong các nhóm cấu hình khác nhau

Ví dụ:

~~~text
demo.http-client.request-timeout = 10s
demo.worker.job-timeout          = 5s
~~~

Một quy tắc có thể yêu cầu **job-timeout > request-timeout**.

Nếu mỗi nhóm được bind thành một class riêng:

~~~java
@ConfigurationProperties(prefix = "demo.http-client")
public record HttpClientProperties(Duration requestTimeout) {
}

@ConfigurationProperties(prefix = "demo.worker")
public record WorkerProperties(Duration jobTimeout) {
}
~~~

thì custom constraint của **HttpClientProperties** không nên tự inject **WorkerProperties**, datasource hoặc service chỉ để so sánh. Tài liệu Spring Boot khuyến nghị configuration properties class chủ yếu làm việc với **Environment**; các bean cấu hình thường được tạo rất sớm.

Một lựa chọn đơn giản là tạo một component chuyên kiểm tra **sau khi cả hai configuration beans đã được tạo**:

~~~java
package com.example.crossfield;

import org.springframework.stereotype.Component;

@Component
public class StartupConfigurationGuard {

    public StartupConfigurationGuard(
            HttpClientProperties client,
            WorkerProperties worker) {

        if (client.requestTimeout() == null
                || worker.jobTimeout() == null) {
            throw new IllegalStateException(
                    "Cần cả request-timeout và job-timeout");
        }

        if (worker.jobTimeout()
                .compareTo(client.requestTimeout()) <= 0) {
            throw new IllegalStateException(
                    "demo.worker.job-timeout phải lớn hơn "
                    + "demo.http-client.request-timeout");
        }
    }
}
~~~

Trong bản code này, **StartupConfigurationGuard** là Spring bean được tạo khi ApplicationContext khởi tạo. Nếu điều kiện sai, việc khởi tạo bean thất bại và có thể khiến ứng dụng không khởi động.

**Đây là lựa chọn cho quy tắc liên quan nhiều bean**, không phải ví dụ thay thế cho constraint cấp class trên một object. Nếu cần bảo đảm thực thi trước những initialization phụ thuộc cấu hình đó, hãy thiết kế dependency/initialization order phù hợp thay vì chỉ tin vào thứ tự ngẫu nhiên giữa các singleton beans.

### 13.1. Vì sao không inject service vào ConstraintValidator?

Một số Bean Validation provider hỗ trợ tạo validator có tích hợp Spring. Tuy nhiên, việc validate cấu hình trong giai đoạn boot thường xảy ra sớm; thêm phụ thuộc vào database, network client hoặc service khác có thể tạo vòng đời phức tạp, circular dependencies hoặc side effects.

**Ưu tiên validator thuần**, chỉ so sánh giá trị đã bind. Nếu ràng buộc thực sự cần nhiều subsystem, thực hiện ở một lớp orchestration hoặc guard chuyên trách sau khi các dependency có thể sử dụng.

## 14. Spring Validator thay cho Jakarta class-level constraint

Ngoài Jakarta Bean Validation, Spring Boot còn cho phép tích hợp một **org.springframework.validation.Validator** tùy biến cho configuration properties.

Một ví dụ cơ bản về Spring Validator:

~~~java
package com.example.crossfield;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class HttpClientSpringValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return HttpClientProperties.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        HttpClientProperties value =
                (HttpClientProperties) target;

        if (value.connectTimeout() == null
                || value.requestTimeout() == null) {
            return;
        }

        if (value.requestTimeout()
                .compareTo(value.connectTimeout()) <= 0) {
            errors.rejectValue(
                    "requestTimeout",
                    "timeout.order",
                    "request-timeout phải lớn hơn connect-timeout");
        }
    }
}
~~~

Với Spring Boot, một custom bean **được đặt tên configurationPropertiesValidator** có thể được dùng để validate các configuration properties. Vì validator được tạo **rất sớm** trong lifecycle, tài liệu Spring Boot khuyến nghị khai báo factory **@Bean** dưới dạng **static**:

~~~java
package com.example.crossfield;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.Validator;

@Configuration(proxyBeanMethods = false)
public class ConfigValidationSetup {

    @Bean
    public static Validator configurationPropertiesValidator() {
        return new HttpClientSpringValidator();
    }
}
~~~

**Cần thận trọng với phạm vi**: bean này là một phần của hạ tầng kiểm tra các configuration properties trong context; **supports(...)** phải chỉ cho phép loại đối tượng phù hợp, tránh cast sai hoặc áp quy tắc nhầm cho các nhóm khác.

Khi quy tắc chỉ áp dụng một type, một **Jakarta class-level constraint** đặt trên chính type đó thường rõ và dễ tái sử dụng hơn. Dùng Spring Validator khi project cần cơ chế đó hoặc muốn tích hợp với hệ thống validation riêng của Spring.

**Không cần đăng ký đồng thời tất cả các cách** trong cùng demo; mỗi cách là một phương án giải quyết.

## 15. Quan hệ thời gian: điều kiện nào mới là đúng?

Không phải hệ thống nào cũng dùng cùng cách hiểu timeout:

- **connect-timeout**: giới hạn cho việc thiết lập kết nối.
- **read-timeout**: giới hạn cho thao tác đọc hoặc khoảng chờ dữ liệu, tùy client.
- **request-timeout**: giới hạn toàn request hoặc timeout ở một tầng cao hơn.
- **retry.initial-delay**, **retry.max-delay**: khoảng chờ giữa các lần thử.

Ví dụ **request-timeout > connect-timeout** có ý nghĩa với **một số thiết kế client**, nhưng không phải mọi thư viện HTTP đều mô tả timeout theo cùng semantic.

Trước khi viết validator, phải xác định:

1. Hai field được dùng trong cùng một pipeline hay các giai đoạn không phụ thuộc?
2. Quan hệ cần **>**, **>=** hay chỉ cần không âm?
3. Giá trị **0** có mang nghĩa đặc biệt như vô hạn/disabled?
4. Có cần tính tổng retry budget không?
5. Khi feature tắt, điều kiện còn áp dụng không?
6. Giá trị lớn nhất phải giới hạn bao nhiêu?

Ví dụ giới hạn ngân sách retry:

~~~text
total-budget >= request-timeout + estimated-retry-delays
~~~

Đây là quy tắc nâng cao, cần tính toán bằng **Duration**, kiểm tra overflow nếu dữ liệu cực lớn và hiểu rõ retry strategy (exponential backoff, jitter, max attempts).

Đừng tạo một constraint chỉ vì quan hệ trông hợp lý về mặt số học nếu nó không đúng với semantics của thư viện tiêu thụ cấu hình.

## 16. Dùng @DefaultValue mà không che giấu lỗi quan hệ

Spring Boot constructor binding có thể dùng **@DefaultValue**:

~~~java
package com.example.crossfield;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.timeouts")
public record DefaultTimeoutProperties(
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("10s") Duration requestTimeout) {
}
~~~

Các default giúp model có giá trị khi nguồn cấu hình không cung cấp. Tuy nhiên, nếu người vận hành chỉ ghi đè:

~~~text
demo.timeouts.connect-timeout=15s
~~~

thì cặp giá trị cuối có thể là:

~~~text
connectTimeout = 15s
requestTimeout = 10s
~~~

Từng trường hợp lệ nhưng **quan hệ không hợp lệ**. Vì vậy ngay cả khi có default, constraint cấp class vẫn rất hữu ích.

### 16.1. Default không thay validation

Một default tốt giúp ứng dụng dễ chạy local; một constraint tốt bảo đảm tổ hợp cuối cùng hợp lệ sau mọi override từ môi trường.

Không tạo default giả cho các trường mà ứng dụng bắt buộc phải được operator cung cấp, như URL production hoặc credential.

## 17. Kiểm tra các tổ hợp khi dùng profile và nhiều nguồn cấu hình

Spring Boot có thể nạp cấu hình theo profile:

**application.yml**:

~~~yaml
demo:
  http-client:
    connect-timeout: 2s
    request-timeout: 10s
~~~

**application-prod.yml**:

~~~yaml
demo:
  http-client:
    connect-timeout: 8s
~~~

Lệnh chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Kết quả ví dụ khi không có nguồn khác ghi đè: **connect-timeout=8s**, **request-timeout=10s**, quan hệ vẫn đúng.

Nhưng nếu operator cấp:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --demo.http-client.request-timeout=5s
~~~

thì cấu hình cuối trở thành **8s** và **5s**, vi phạm quy tắc.

**Validation phải chạy trên các giá trị hiệu lực cuối cùng sau binding**, không nên chỉ kiểm tra một file YAML theo từng môi trường riêng lẻ. Điều này là một lý do quan trọng để gắn cross-field validation vào **@ConfigurationProperties**.

### 17.1. Biến môi trường tương ứng

~~~text
demo.http-client.connect-timeout
    -> DEMO_HTTPCLIENT_CONNECTTIMEOUT

demo.http-client.request-timeout
    -> DEMO_HTTPCLIENT_REQUESTTIMEOUT
~~~

Theo quy tắc binding từ môi trường:

- Dấu **.** biến thành **_**.
- Dấu **-** bị bỏ.
- Chữ được viết hoa.

Tên env **DEMO_HTTP_CLIENT_CONNECT_TIMEOUT** không phải phép chuyển canonical của **demo.http-client.connect-timeout**. Đừng tự thêm dấu dưới theo cách tách từng từ của kebab-case.

## 18. Mở rộng với nhiều field tùy chọn

Một object có thể có:

~~~text
cache.enabled
cache.ttl
cache.max-size
cache.eviction-policy
~~~

Ví dụ yêu cầu:

- Khi cache **disabled**, các giá trị TTL/size có thể không cần thiết.
- Khi cache **enabled**, TTL phải dương và max-size > 0.
- Nếu eviction-policy là **time-based**, TTL bắt buộc.
- Nếu eviction-policy là **size-based**, max-size bắt buộc.

Trong tình huống này, không nên ép từng field dùng @NotNull vô điều kiện nếu nó chỉ bắt buộc ở một chế độ.

Một strategy dễ hiểu:

1. Bind một object chứa flag/chế độ và các field tùy chọn.
2. Validate các giá trị độc lập (ví dụ định dạng enum hợp lệ).
3. Dùng class-level constraint hoặc **@AssertTrue** để kiểm tra sự tương thích giữa chế độ và field.
4. Trả thông báo lỗi có nhắc key và điều kiện bị vi phạm.

Khi logic phức tạp hơn, có thể chia thành nhiều validator hoặc class chuyên nghiệp vụ cấu hình. Đừng gộp mọi quy tắc vào một phương thức dài không thể kiểm thử riêng.

## 19. Kiểm thử bằng ApplicationContextRunner

**ApplicationContextRunner** là tiện ích test của Spring Boot cho phép tạo một ApplicationContext nhỏ với property values cụ thể. Nó phù hợp để kiểm tra configuration properties, validation và failure khi startup mà không phải khởi chạy toàn bộ ứng dụng web.

Giả sử có những class đã trình bày:

- **HttpClientProperties** gắn **@Validated**, **@ValidTimeoutWindow** và nested Retry.
- **ValidTimeoutWindow**.
- **TimeoutWindowValidator**.
- Dependency **spring-boot-starter-validation** và **spring-boot-starter-test**.

### 19.1. Test hợp lệ và không hợp lệ

~~~java
package com.example.crossfield;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class HttpClientPropertiesValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(HttpClientProperties.class)
    static class TestConfiguration {
    }

    @Test
    void acceptsValidTimeoutOrder() {
        runner.withPropertyValues(
                "demo.http-client.base-url=https://api.example.invalid",
                "demo.http-client.connect-timeout=2s",
                "demo.http-client.request-timeout=10s",
                "demo.http-client.retry.enabled=true",
                "demo.http-client.retry.max-attempts=3",
                "demo.http-client.retry.initial-delay=250ms",
                "demo.http-client.retry.max-delay=3s"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            HttpClientProperties properties =
                    context.getBean(HttpClientProperties.class);

            assertThat(properties.connectTimeout())
                    .isEqualTo(Duration.ofSeconds(2));
            assertThat(properties.requestTimeout())
                    .isEqualTo(Duration.ofSeconds(10));
        });
    }

    @Test
    void rejectsRequestTimeoutShorterThanConnectTimeout() {
        runner.withPropertyValues(
                "demo.http-client.base-url=https://api.example.invalid",
                "demo.http-client.connect-timeout=8s",
                "demo.http-client.request-timeout=3s",
                "demo.http-client.retry.enabled=false",
                "demo.http-client.retry.max-attempts=1",
                "demo.http-client.retry.initial-delay=100ms",
                "demo.http-client.retry.max-delay=1s"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
    }
}
~~~

Ở test thứ hai, cả hai Duration hợp lệ về cú pháp, nhưng constraint **@ValidTimeoutWindow** từ chối quan hệ sai.

**Không cần kết nối API thật**: URL với domain **.invalid** chỉ được bind thành URI, không phải thực hiện HTTP call.

### 19.2. Test nhiều tổ hợp theo bảng

Có thể lập ma trận test:

| connect-timeout | request-timeout | Kỳ vọng |
| --- | --- | --- |
| **1s** | **10s** | Pass |
| **3s** | **3s** | Fail nếu yêu cầu lớn hơn nghiêm ngặt |
| **8s** | **2s** | Fail |
| Thiếu | **10s** | Fail qua @NotNull |
| **bad-value** | **10s** | Fail ở bước bind/conversion |

Đối với retry:

| enabled | initial-delay | max-delay | max-attempts | Kỳ vọng |
| --- | --- | --- | --- | --- |
| false | không có | không có | không có | Có thể pass nếu thiết kế cho phép |
| true | 100ms | 2s | 3 | Pass |
| true | 5s | 1s | 3 | Fail |
| true | 100ms | 2s | 0 | Fail |
| true | không có | 2s | 3 | Fail |

**Bảng là hợp đồng kiểm thử cho validation mà bạn thiết kế**, không phải quy định bắt buộc của mọi Spring Boot HTTP client.

## 20. Kiểm thử validator trực tiếp bằng Jakarta Validator

Không nhất thiết mọi test phải khởi tạo Spring Boot context. Nếu validator là Java thuần, có thể kiểm thử quy tắc độc lập qua Jakarta Bean Validation.

Ví dụ dùng **jakarta.validation.Validation**:

~~~java
package com.example.crossfield;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class TimeoutWindowConstraintTest {

    @Test
    void detectsInvalidTimeoutWindow() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            HttpClientProperties properties =
                    new HttpClientProperties(
                        URI.create("https://api.example.invalid"),
                        Duration.ofSeconds(8),
                        Duration.ofSeconds(3),
                        new HttpClientProperties.Retry(
                            false, null, null, null));

            var violations = validator.validate(properties);

            assertThat(violations).isNotEmpty();
            assertThat(violations.stream()
                    .anyMatch(v -> v.getMessage()
                        .contains("request-timeout")))
                    .isTrue();
        }
    }
}
~~~

Test này kiểm tra Bean Validation trên object được tạo thủ công, không kiểm tra cách YAML hoặc env được bind. Vì thế nên có **cả hai loại test** nếu cấu hình quan trọng: một lớp kiểm tra validator, một lớp xác minh Spring Boot binding và validation tích hợp.

Nếu custom validator dùng service từ Spring, test thuần với **Validation.buildDefaultValidatorFactory()** có thể thiếu cơ chế dependency injection đó. Đây cũng là lý do nên để validator kiểm tra config ở dạng thuần.

## 21. Phân biệt lỗi bind và lỗi validation khi khởi động

Một cấu hình sai có thể dừng khởi động ở các bước khác nhau.

### 21.1. Sai kiểu

~~~yaml
demo:
  http-client:
    connect-timeout: not-a-duration
~~~

Binder không thể tạo Duration từ chuỗi không hợp lệ. Kết quả là lỗi conversion/binding.

### 21.2. Thiếu trường bắt buộc

~~~yaml
demo:
  http-client:
    request-timeout: 10s
~~~

Nếu record có **@NotNull Duration connectTimeout** và validation được bật, lỗi có thể chỉ ra trường bắt buộc chưa có.

### 21.3. Quan hệ sai

~~~yaml
demo:
  http-client:
    connect-timeout: 8s
    request-timeout: 3s
~~~

Hai giá trị đều được convert thành Duration; custom constraint phát hiện vi phạm quan hệ.

Thay vì chỉ nhìn thông điệp cuối cùng “Failed to bind properties”, hãy xem chuỗi nguyên nhân, đường property và thông báo constraint.

Không cần dựa vào tên exception chính xác trong mọi version/test; một integration test ổn định có thể assert context **hasFailed()**, và một validator unit test kiểm tra thông báo constraint cụ thể.

## 22. Khi nào dùng @AssertTrue, custom constraint hay startup guard?

| Tình huống | Cách thường hợp lý |
| --- | --- |
| Một quan hệ boolean đơn giản trong một object nhỏ | **@AssertTrue** trên getter thích hợp |
| Cần gắn lỗi vào field cụ thể | **Class-level constraint + ConstraintValidatorContext** |
| Muốn dùng cùng quy tắc cho nhiều type | Custom annotation có tính tái sử dụng |
| Quy tắc điều kiện trong nested config | Constraint trên nested object, cascade bằng **@Valid** |
| Quan hệ giữa hai configuration beans độc lập | Startup guard hoặc validation orchestration chuyên trách |
| Cấu hình của thư viện không thể gắn annotation | Tích hợp Spring Validator hoặc lớp kiểm tra bên ngoài |
| Muốn test thuần, không cần Spring context | Jakarta Validator trên object Java |
| Muốn kiểm tra full binding và fail-fast | **ApplicationContextRunner** |

Không có lý do để áp dụng đồng thời mọi cơ chế cho một quan hệ duy nhất. Hãy chọn phương án đơn giản nhất thể hiện rõ hợp đồng và tạo thông báo dễ xử lý.

## 23. Những lỗi thường gặp

### Lỗi 1: chỉ validate từng field, bỏ qua quan hệ

**@NotNull** trên hai timeout không bảo đảm request-timeout lớn hơn connect-timeout. Cần custom rule.

### Lỗi 2: ép @Min/@Max lên Duration

Các constraint số không mặc định hỗ trợ Duration; phải kiểm tra support của Bean Validation provider hoặc dùng constraint phù hợp.

### Lỗi 3: quên @Validated

Nếu class **@ConfigurationProperties** không được đưa vào cơ chế validation phù hợp, những constraint có thể không được chạy như kỳ vọng.

### Lỗi 4: thiếu validation implementation

Chỉ import các annotation từ jakarta.validation nhưng classpath không có implementation phù hợp sẽ không tạo ra quá trình Bean Validation như mong đợi. Thêm starter-validation trong dự án Spring Boot thông thường.

### Lỗi 5: quên @Valid trên nested object

Parent được validate không đồng nghĩa các constraint của nested object luôn được kiểm tra. Dùng **@Valid** để cascade.

### Lỗi 6: validator gây NullPointerException

Validator nên bỏ qua quan hệ khi thiếu đầu vào và để **@NotNull** báo lỗi thiếu, hoặc xử lý null có chủ đích.

### Lỗi 7: ràng buộc field tùy chọn như bắt buộc vô điều kiện

Nếu retry tắt thì không cần delay, nhưng đặt **@NotNull** lên delay sẽ khiến cấu hình hợp lệ theo nghiệp vụ bị từ chối. Đồng bộ annotation với quy tắc bật/tắt.

### Lỗi 8: message không nêu quan hệ

Thông báo **"invalid configuration"** quá chung. Nên nói **"request-timeout phải lớn hơn connect-timeout"**, tránh in giá trị nhạy cảm.

### Lỗi 9: thêm dependency mạng vào validator

Validator cấu hình chạy sớm. Không nên mở kết nối DB/HTTP trong hàm validation. Chỉ kiểm tra giá trị đã bind.

### Lỗi 10: test chỉ một tổ hợp hợp lệ

Cần test cả biên bằng nhau, trường thiếu, điều kiện tắt, điều kiện bật, kiểu sai và override từ env/CLI.

### Lỗi 11: so sánh chuỗi thay vì Duration

**"10s"** và **"2s"** không thể so sánh đúng bằng thứ tự từ điển. Hãy bind thành Duration rồi dùng **compareTo(...)**.

### Lỗi 12: kiểm tra riêng từng file YAML, bỏ qua override

Cấu hình cuối có thể là tổ hợp giá trị từ file chung, profile-specific, biến môi trường và command-line. Validation cần áp dụng lên object đã bind từ nguồn hiệu lực.

### Lỗi 13: dựa vào thứ tự khởi tạo bean không được khai báo

Với quy tắc giữa hai configuration beans, startup guard cần có dependency rõ để tránh logic dùng cấu hình sai trước khi guard chạy. Không mặc định mọi singleton được tạo theo một thứ tự tình cờ.

### Lỗi 14: dùng bean validation như giải pháp mọi vấn đề nghiệp vụ

Những quy tắc phụ thuộc trạng thái DB, API bên ngoài hoặc dữ liệu runtime có thể không phù hợp để kiểm tra ngay trong configuration properties. Tách validation cấu hình thuần khỏi kiểm tra readiness/integration theo vòng đời thích hợp.

## 24. Bài thực hành

### Bài A — so sánh hai timeout

1. Tạo **demo.http-client.connect-timeout=2s** và **request-timeout=10s**.
2. Viết **@AssertTrue** hoặc custom constraint cho quan hệ requestTimeout > connectTimeout.
3. Đổi request-timeout thành **1s**.
4. Quan sát context startup thất bại.
5. Khôi phục về **10s**.

Kết quả: các field có thể đúng kiểu nhưng sai quan hệ.

### Bài B — thay @AssertTrue bằng class-level constraint

1. Tạo **@ValidTimeoutWindow**.
2. Viết **ConstraintValidator** dùng **Duration.compareTo**.
3. Dùng **addPropertyNode("requestTimeout")**.
4. Chạy lại cấu hình không hợp lệ.

Kết quả: validation có thể chỉ ra đúng field liên quan.

### Bài C — retry có điều kiện

1. Tạo **retry.enabled**, **max-attempts**, **initial-delay**, **max-delay**.
2. Khi enabled=false, cho phép thiếu các trường retry nếu hợp đồng mong muốn.
3. Khi enabled=true, yêu cầu delay dương, maxAttempts >= 1 và initialDelay <= maxDelay.
4. Test các nhánh khác nhau.

Kết quả: conditional validation phù hợp hơn việc đặt mọi @NotNull vô điều kiện.

### Bài D — override môi trường

1. Khai báo timeout hợp lệ trong **application.yml**.
2. Cấp **DEMO_HTTPCLIENT_CONNECTTIMEOUT=8s**.
3. Cấp request-timeout thấp hơn qua command-line hoặc profile.
4. Quan sát validation từ chối tổ hợp cuối.

Kết quả: fail-fast trước khi client thật sử dụng các timeout không nhất quán.

### Bài E — kiểm thử không cần server

1. Dùng **ApplicationContextRunner** với @EnableConfigurationProperties.
2. Tạo test success và failure.
3. Assert **hasNotFailed()** cho cấu hình hợp lệ.
4. Assert **hasFailed()** cho quan hệ sai.
5. Dùng Validator thuần để kiểm tra thông điệp vi phạm.

Kết quả: phát hiện sai cấu hình sớm mà không cần API, DB hay message broker.

### Bài F — quan hệ giữa hai prefix

1. Tạo nhóm **demo.http-client** và **demo.worker**.
2. Định nghĩa yêu cầu worker jobTimeout > client requestTimeout.
3. Tạo startup guard nhận hai configuration beans.
4. Test các tổ hợp phù hợp/không phù hợp.
5. Chọn dependency order rõ ràng nếu một service cần được guard trước khi sử dụng.

Kết quả: có thể validate chéo nhiều nhóm, nhưng không nên biến một configuration properties class thành service điều phối.

## 25. Checklist thiết kế cross-field validation

Trước khi công bố một constraint, hãy xác định:

1. Quan hệ nghiệp vụ cụ thể là gì?
2. Các field cùng một object hay thuộc nhiều configuration beans?
3. Quan hệ **>**, **>=**, **<**, **<=** hoặc loại trừ lẫn nhau?
4. Khi thiếu field, ai chịu trách nhiệm báo lỗi: **@NotNull** hay custom constraint?
5. Khi feature disabled, điều kiện còn có hiệu lực không?
6. Với Duration, zero và số âm có ý nghĩa đặc biệt không?
7. Các giá trị đã được bind đúng kiểu trước khi so sánh chưa?
8. Có cần gắn lỗi vào một property cụ thể?
9. Thông báo đã giải thích được key hoặc quan hệ cần sửa chưa?
10. Validator có thuần, không phụ thuộc I/O hay hạ tầng runtime không?
11. Nested object có **@Valid** khi cần cascade không?
12. Type đã được đăng ký bằng scanning hoặc enable chưa?
13. Dependency Bean Validation đã có chưa?
14. Test đã có trường hợp biên, thiếu dữ liệu, và override môi trường chưa?
15. Có nguy cơ lộ secret trong message hoặc log không?
16. Cơ chế fail-fast có diễn ra trước khi tính năng phụ thuộc cấu hình hoạt động không?

## 26. Tổng kết

- **Validation từng field** không đủ để phát hiện một tổ hợp cấu hình mâu thuẫn.
- **@ConfigurationProperties** cùng **@Validated** cho phép kiểm tra cấu hình đã được bind thành object Java.
- **@AssertTrue** phù hợp với một điều kiện boolean đơn giản có thể suy ra từ nhiều field.
- **Custom class-level constraint** với **@Constraint** và **ConstraintValidator** phù hợp khi quy tắc phức tạp hoặc cần tái sử dụng.
- **ConstraintValidatorContext.addPropertyNode(...)** có thể gắn vi phạm vào trường cụ thể thay vì chỉ object tổng.
- **@Valid** giúp cascade validation vào nested object; nó không tự suy ra các quan hệ cần kiểm tra.
- Validator nên xử lý null có chủ đích, tránh thông báo lỗi trùng và tránh side effects.
- Quan hệ có điều kiện cần xét các flag như **enabled** thay vì dùng @NotNull vô điều kiện cho mọi trường.
- Ràng buộc liên quan nhiều configuration beans có thể được thực hiện ở một startup guard hoặc lớp orchestration.
- **ApplicationContextRunner** và Jakarta Validator giúp kiểm thử cả full binding lẫn constraint riêng lẻ.
- Validation phải áp dụng cho **cấu hình hiệu lực sau khi các nguồn đã được kết hợp**, không chỉ một file YAML tách rời.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Externalized Configuration, mục *@ConfigurationProperties Validation* và *Type-safe Configuration Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Jakarta Bean Validation 3.0 — Specification: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API — @AssertTrue: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/asserttrue
- Jakarta Validation API — ConstraintValidator và ConstraintValidatorContext: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator
- Spring Boot 3.3 API — ApplicationContextRunner: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
