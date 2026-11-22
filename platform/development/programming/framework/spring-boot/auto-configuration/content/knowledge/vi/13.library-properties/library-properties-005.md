# Ràng buộc tính hợp lệ bằng @Validated và phản hồi lỗi cấu hình

> **Mục tiêu:** Khi xây dựng thư viện và Spring Boot Auto Configuration, các thuộc tính ngoài ứng dụng cần được **bind thành object có kiểu**, **kiểm tra ràng buộc** và **báo lỗi có thể hành động được** nếu giá trị sai. `@ConfigurationProperties` giải quyết việc gắn giá trị vào object; Spring `@Validated` kết hợp Jakarta Bean Validation xác nhận các giá trị có hợp lệ; Spring Boot có cơ chế báo lỗi binding/validation lúc tạo bean cấu hình.

Ví dụ sử dụng **Spring Boot 3.3.x và Java 17+**. Bài học tập trung vào thuộc tính được thư viện cung cấp cho ứng dụng tiêu thụ, không nhầm validation của cấu hình với validation request từ HTTP controller hoặc validation input nghiệp vụ trong service.

## 1. Tại sao thuộc tính thư viện cần được kiểm tra?

Một starter gửi thông báo có thể cần những khóa:

~~~yaml
demo:
  mailer:
    enabled: true
    from-address: "alerts@example.org"
    max-attempts: 3
    transport:
      host: "smtp.example.org"
      port: 2525
~~~

Thư viện không thể coi mọi giá trị đến từ `application.yml`, biến môi trường, Java system properties hoặc command line đều đúng. Chỉ một thay đổi triển khai cũng có thể gây:

- `demo.mailer.from-address` bị bỏ trống, khiến hệ thống không có địa chỉ người gửi.
- `demo.mailer.max-attempts=0` hoặc một số quá lớn, tạo chính sách thử lại vô nghĩa.
- `demo.mailer.transport.port=70000`, ngoài phạm vi cổng TCP thông thường.
- `demo.mailer.transport.host` không được khai báo.
- `demo.mailer.max-attempts=abc`, không thể chuyển từ chuỗi thành số nguyên.

Nếu để lỗi chỉ xuất hiện lần đầu khi gọi dịch vụ bên ngoài, việc tìm nguyên nhân chậm và thiếu bối cảnh. Với các cấu hình **bắt buộc để khởi tạo thành phần**, nên xác nhận khi container tạo configuration properties bean để ứng dụng thất bại sớm, có tên khóa và lý do cụ thể.

Các khái niệm không giống nhau:

| Lớp kiểm tra | Ví dụ | Cơ chế chính |
| --- | --- | --- |
| Tìm thuộc tính | Có khóa `demo.mailer.max-attempts` không? | Nguồn cấu hình/`Environment` |
| Chuyển đổi kiểu | `abc` có đổi thành `Integer` được không? | Spring Boot Binder + conversion |
| Kiểm tra ràng buộc | `0` có thỏa `@Min(1)` không? | Jakarta Bean Validation qua `@Validated` |
| Kiểm tra kết hợp | Port và giao thức có phù hợp chính sách riêng không? | Custom constraint/validator hoặc logic kiểm tra riêng |
| Điều kiện tạo bean | `demo.mailer.enabled` có bằng `true` không? | `@ConditionalOnProperty` của Spring Boot |

**Tính hợp lệ của một giá trị** và **điều kiện có tạo cấu hình hay không** là hai câu hỏi khác nhau. `@Validated` không có nhiệm vụ tự quyết định class auto-configuration có được bật; `@ConditionalOnProperty` không tự kiểm tra mọi field trong `@ConfigurationProperties`.

## 2. Bộ ba annotation và dependency cần có

### @ConfigurationProperties: định nghĩa hợp đồng cấu hình

~~~java
@ConfigurationProperties(prefix = "demo.mailer")
public record MailerProperties(
        String fromAddress,
        Integer maxAttempts,
        Transport transport) {
    public record Transport(String host, Integer port) {}
}
~~~

Đây là **phác thảo cấu trúc** (cần import ở phần ví dụ hoàn chỉnh). Spring Boot binder ánh xạ các tên canonical dạng kebab-case như `from-address` và `max-attempts` sang record components `fromAddress` và `maxAttempts`. `transport.host` và `transport.port` thuộc object lồng nhau.

Dùng `@ConfigurationProperties` thuận tiện hơn nhiều placeholder `@Value` rời rạc khi thư viện có một nhóm khóa có quan hệ. Record có constructor duy nhất được Spring Boot 3.x hỗ trợ **constructor binding** mà không cần đánh dấu `@ConstructorBinding` trên type. Class JavaBean với getter/setter cũng là lựa chọn hợp lệ.

### @Validated: yêu cầu kiểm tra sau khi bind

~~~java
@ConfigurationProperties(prefix = "demo.mailer")
@Validated
public record MailerProperties(
        @NotBlank @Email String fromAddress,
        @NotNull @Min(1) @Max(8) Integer maxAttempts,
        @NotNull @Valid Transport transport) {
    public record Transport(
            @NotBlank String host,
            @NotNull @Min(1) @Max(65535) Integer port) {}
}
~~~

Các annotation là:

- `org.springframework.validation.annotation.Validated`: yêu cầu quy trình configuration-properties áp dụng validation.
- `jakarta.validation.constraints.NotBlank`: chuỗi không được `null`, rỗng hoặc chỉ có ký tự trắng.
- `jakarta.validation.constraints.Email`: kiểm tra cú pháp địa chỉ email theo Bean Validation provider. `@Email` một mình không có nghĩa trường bắt buộc; ghép `@NotBlank`.
- `jakarta.validation.constraints.NotNull`: một giá trị/reference không được `null`; dùng cho field bắt buộc.
- `jakarta.validation.constraints.Min` và `Max`: giới hạn khoảng số nguyên; hai constraint này **không tự cấm `null`**, nên dùng cùng `@NotNull` nếu bắt buộc.
- `jakarta.validation.Valid`: kích hoạt **cascaded validation** cho object `Transport` lồng nhau. Khi muốn buộc object lồng nhau luôn tồn tại, ghép `@NotNull @Valid` trên field chứa object.

Với `@NotNull @Valid Transport transport`, thiếu toàn bộ nhánh `transport` được kiểm tra bằng `@NotNull`; còn khi `transport` tồn tại, `@Valid` cho phép kiểm tra `host` và `port` bên trong. Nếu chỉ gắn `@Valid` mà không `@NotNull`, một nested object `null` có thể được bỏ qua do cascaded validation không tự coi `null` là lỗi.

### Thêm Jakarta Validation implementation

Annotation alone không đủ: ứng dụng chạy cần **Bean Validation provider**. Trong Spring Boot, thêm `spring-boot-starter-validation` để dùng triển khai tương thích (thông dụng là Hibernate Validator). Ví dụ trong dự án Gradle Groovy đã có Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Nếu thư viện xuất bản thành starter độc lập, phải bảo đảm **runtime của ứng dụng tiêu thụ** có validation provider. Chỉ thêm annotation `jakarta.validation` mà không có implementation tương ứng có thể dẫn tới việc validation không thực sự được áp dụng như mong đợi. Trên **Spring Boot 3.x**, dùng package `jakarta.validation.*`, không dùng `javax.validation.*` từ thế hệ cũ.

## 3. Đăng ký properties bean trong auto-configuration

Tạo class properties **tách biệt với bean nghiệp vụ**, rồi đăng ký thông qua `@EnableConfigurationProperties`:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(MailerProperties.class)
class MailerAutoConfiguration {
    @Bean
    MailerClient mailerClient(MailerProperties properties) {
        return new MailerClient(
                properties.transport().host(),
                properties.transport().port(),
                properties.fromAddress(),
                properties.maxAttempts());
    }
}
~~~

Đây là mẫu cấu trúc; phần 6 cung cấp **đầy đủ tệp và import**. Khi Spring cần tạo `MailerProperties`, Boot bind các giá trị có hiệu lực từ `Environment`, thực hiện chuyển đổi kiểu, rồi kiểm tra ràng buộc nếu có `@Validated` và validator phù hợp. Khi cấu hình không hợp lệ và properties bean được tạo lúc khởi động, container thường dừng khởi tạo cùng báo cáo lỗi.

Điều quan trọng với **thư viện**:

1. `@ConfigurationProperties` xác định nhóm khóa và kiểu dữ liệu, **không đủ** để bảo đảm bean được đăng ký.
2. `@EnableConfigurationProperties(MailerProperties.class)` đăng ký chính xác type thư viện muốn bind; cách này phù hợp với auto-configuration, không cần người dùng bật scan vào package nội bộ thư viện.
3. Bean client nhận object đã được bind/validate thông qua injection, thay vì tự gọi `environment.getProperty(...)` nhiều nơi.
4. Nếu đưa `MailerProperties` vào nhiều đường đăng ký độc lập (scan, component và enable), có thể làm lifecycle và thông báo lỗi khó hiểu. Chọn một đường đăng ký có chủ đích trong starter.

Trong một starter công bố cho người dùng, các khóa nên viết ở dạng **lowercase kebab-case** với prefix nhất quán: `demo.mailer.from-address`, `demo.mailer.max-attempts`, `demo.mailer.transport.host`, `demo.mailer.transport.port`. Thông điệp lỗi và tài liệu sử dụng nên dùng tên khóa này.

## 4. Lỗi cấu hình được phản hồi như thế nào?

Với ứng dụng khởi động bằng Spring Boot, một vấn đề khi bind properties có thể dẫn đến exception trong chuỗi tạo bean và **Failure Analysis** mô tả nguyên nhân. Phân biệt hai nhóm chính:

**A. Không chuyển được kiểu (binding/conversion failure)**

~~~properties
demo.mailer.enabled=true
demo.mailer.from-address=alerts@example.org
demo.mailer.max-attempts=abc
demo.mailer.transport.host=smtp.example.org
demo.mailer.transport.port=2525
~~~

Trường `max-attempts` yêu cầu `Integer` nhưng nhận `abc`. Binder **không thể tạo giá trị đúng kiểu**; lỗi xảy ra ở bước chuyển đổi/binding, nên không nên mô tả đó là lỗi `@Min(1)`. Thông báo thường chỉ ra prefix/khóa, giá trị sai và nguyên nhân chuyển đổi.

**B. Chuyển kiểu thành công nhưng sai constraint (validation failure)**

~~~properties
demo.mailer.enabled=true
demo.mailer.from-address=alerts@example.org
demo.mailer.max-attempts=0
demo.mailer.transport.host=smtp.example.org
demo.mailer.transport.port=2525
~~~

`0` được chuyển thành `Integer` thành công nhưng vi phạm `@Min(1)`. Đây là lỗi validation khi bind properties. Spring Boot thường trình bày lỗi theo các thông tin: property path, giá trị, lý do, và origin (nếu nguồn hỗ trợ thông tin xuất xứ).

Một bản mô phỏng **có tính minh họa, không phải stdout cố định** của Failure Analysis:

~~~text
APPLICATION FAILED TO START

Description:
Failed to bind properties under 'demo.mailer' ...

Property: demo.mailer.max-attempts
Value: 0
Reason: must be greater than or equal to 1

Action:
Review the application's configuration.
~~~

Văn bản, ngôn ngữ message và chuỗi exception cụ thể có thể khác theo phiên bản Spring Boot, Jakarta Validation provider và nguồn thuộc tính. Điểm cần tìm là **tên khóa sai, giá trị đã nhận, lý do và nguồn giá trị**; đừng viết test so khớp nguyên văn toàn bộ banner lỗi.

### Điều kiện để có lỗi rõ ràng

- Có `@ConfigurationProperties` bean được đăng ký và **thực sự được tạo/bind**.
- Có `@Validated`/constraint tương ứng và Jakarta Validation implementation khi muốn kiểm tra ràng buộc.
- Không che lỗi bằng tùy chọn bỏ qua giá trị sai hoặc swallow exception.
- Thuộc tính cần kiểm tra **có nằm trong object** và constraint đang được kiểm tra hay không.

Giá trị đã có default hợp lệ thì không nhất thiết thiếu khóa sẽ báo lỗi. Ngược lại, trong ví dụ dùng `@NotNull`, thiếu `max-attempts` sẽ bị chặn thay vì ngầm hiểu là 0. Nếu dùng primitive `int` và không có giá trị cấu hình, giá trị 0 có thể trở thành nguyên nhân vi phạm `@Min(1)` nhưng message sẽ ít nói rõ “thiếu khóa” hơn thiết kế `Integer + @NotNull`.

## 5. Thuộc tính hiệu lực và origin: đừng sửa nhầm tệp

Spring Boot có nhiều `PropertySource` theo thứ tự ưu tiên. Chẳng hạn:

- `application.yml` trong JAR khai báo `demo.mailer.max-attempts=3`.
- Biến môi trường của container khai báo `DEMO_MAILER_MAXATTEMPTS=0`.
- Không có nguồn nào khác ưu tiên cao hơn ghi đè.

Khi bind, giá trị hiệu lực có thể là `0`, và `@Min(1)` sẽ thất bại dù file YAML bạn xem vẫn là `3`. Spring Boot áp dụng relaxed binding: từ canonical `demo.mailer.max-attempts` sang tên biến OS thông thường `DEMO_MAILER_MAXATTEMPTS` (dấu chấm → gạch dưới, xóa gạch ngang, viết hoa).

Quy trình điều tra:

1. Ghi ra **canonical property path** từ `@ConfigurationProperties(prefix=...)` và record field tương ứng.
2. Kiểm tra giá trị hiệu lực tại **đúng tiến trình**: tham số CLI, system properties, OS env, profile-specific config, config imports.
3. Đọc Failure Analysis để biết sai do chuyển kiểu hay constraint, theo property path nào.
4. Dùng thông tin **origin** nếu được trả về: nguồn file/dòng hoặc source name, không đoán origin nếu metadata không có.
5. Sửa giá trị ở **nguồn đang thắng**, khởi động lại context và chạy lại test.

Với Spring Boot Actuator và cấu hình truy cập an toàn, `/actuator/env/{name}` và `/actuator/configprops` giúp kiểm tra property source và giá trị đã bind. Tuy nhiên, nếu validation thất bại khiến app không khởi động, bạn sẽ **không thể dựa vào HTTP endpoint của chính app thất bại** để chẩn đoán; lúc đó log, command-line, manifest môi trường chạy hoặc một test context là nguồn thực tế hơn.

Các endpoint chẩn đoán có thể che dữ liệu nhạy cảm và không được mở HTTP mặc định; không công khai `env`/`configprops` chỉ để debug. Không in secret/token đầy đủ vào log hay thông báo lỗi tùy chỉnh.

## 6. Mẫu đầy đủ Java 17+ với startup validation

Ví dụ dưới đây tạo một **client mô phỏng cấu hình**; nó **không** thực hiện kết nối SMTP hay gửi email. Nhờ vậy có thể kiểm tra toàn bộ quá trình đăng ký, bind và validate một cách xác định, không cần dịch vụ bên ngoài.

### 6.1. File MailerProperties.java

**Đường dẫn:** `src/main/java/example/library/MailerProperties.java`

~~~java
package example.library;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "demo.mailer")
@Validated
public record MailerProperties(
        @NotBlank @Email String fromAddress,
        @NotNull @Min(1) @Max(8) Integer maxAttempts,
        @NotNull @Valid Transport transport) {

    public record Transport(
            @NotBlank String host,
            @NotNull @Min(1) @Max(65535) Integer port) {
    }
}
~~~

Đây là hợp đồng cấu hình: email phải có và đúng cú pháp, số lần thử từ 1–8, object transport phải có host không rỗng và port từ 1–65535. `@Valid` trên `transport` bảo đảm validation đi tiếp vào bean lồng nhau.

### 6.2. File MailerClient.java

**Đường dẫn:** `src/main/java/example/library/MailerClient.java`

~~~java
package example.library;

public record MailerClient(
        String host,
        int port,
        String fromAddress,
        int maxAttempts) {

    public String description() {
        return "host=" + host
                + ", port=" + port
                + ", from=" + fromAddress
                + ", attempts=" + maxAttempts;
    }
}
~~~

Record này chỉ lưu các giá trị đã bind và tạo chuỗi mô tả để test; **không kết nối mạng**. Việc truyền `Integer` validated vào tham số `int` sử dụng unboxing; nhờ `@NotNull`, dữ liệu cấu hình hợp lệ không làm unboxing `null`.

### 6.3. File MailerAutoConfiguration.java

**Đường dẫn:** `src/main/java/example/library/MailerAutoConfiguration.java`

~~~java
package example.library;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.mailer",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(MailerProperties.class)
public class MailerAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MailerClient.class)
    public MailerClient mailerClient(MailerProperties properties) {
        return new MailerClient(
                properties.transport().host(),
                properties.transport().port(),
                properties.fromAddress(),
                properties.maxAttempts());
    }
}
~~~

Luồng xử lý khi `demo.mailer.enabled=true`:

1. Boot xét property condition ở cấp auto-configuration.
2. Khi class được áp dụng, `@EnableConfigurationProperties` đăng ký bean `MailerProperties`.
3. Khi bean properties được tạo, binder chuyển dữ liệu và validation kiểm tra các ràng buộc.
4. Nếu mọi thứ hợp lệ và chưa có `MailerClient` do ứng dụng cung cấp, method `mailerClient` tạo client mặc định bằng các giá trị đã xác nhận.
5. Nếu dữ liệu sai, context không hoàn tất khởi động bình thường; test có thể bắt trạng thái thất bại.

`@ConditionalOnMissingBean` thuộc cơ chế back-off cho người dùng thay bean mặc định; nó không thay `@Validated`. Lưu ý nếu người dùng đã tự cung cấp `MailerClient` nhưng auto-configuration vẫn được áp dụng, `@EnableConfigurationProperties` có thể tiếp tục đăng ký/bind properties và kích hoạt validation — điều này có thể là chủ đích của thư viện hoặc cần thiết kế lại phạm vi đăng ký nếu muốn cấu hình hoàn toàn không liên quan được bỏ qua.

Để Boot tự phát hiện auto-configuration khi **đóng gói thư viện**, cần tệp:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
example.library.MailerAutoConfiguration
~~~

Không yêu cầu người dùng component-scan package thư viện. Trong unit test ngay dưới đây, `AutoConfigurations.of(...)` nạp trực tiếp class nên **không cần** file imports để chạy test.

### 6.4. File MailerValidationTest.java

**Đường dẫn:** `src/test/java/example/library/MailerValidationTest.java`

~~~java
package example.library;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class MailerValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(MailerAutoConfiguration.class));

    private ApplicationContextRunner enabled(
            String fromAddress,
            String attempts,
            String host,
            String port) {

        return runner.withPropertyValues(
                "demo.mailer.enabled=true",
                "demo.mailer.from-address=" + fromAddress,
                "demo.mailer.max-attempts=" + attempts,
                "demo.mailer.transport.host=" + host,
                "demo.mailer.transport.port=" + port);
    }

    @Test
    void validConfigurationBindsAndCreatesClient() {
        enabled("alerts@example.org", "3", "smtp.example.org", "2525")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(MailerProperties.class);
                    assertThat(context).hasSingleBean(MailerClient.class);
                    assertThat(context.getBean(MailerClient.class).description())
                            .isEqualTo("host=smtp.example.org, port=2525"
                                    + ", from=alerts@example.org, attempts=3");
                });
    }

    @Test
    void invalidEmailFailsValidation() {
        enabled("not-an-email", "3", "smtp.example.org", "2525")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void zeroAttemptsFailsValidation() {
        enabled("alerts@example.org", "0", "smtp.example.org", "2525")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void blankNestedHostFailsValidation() {
        enabled("alerts@example.org", "3", "", "2525")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void outOfRangePortFailsValidation() {
        enabled("alerts@example.org", "3", "smtp.example.org", "70000")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void missingTransportFailsValidation() {
        runner.withPropertyValues(
                "demo.mailer.enabled=true",
                "demo.mailer.from-address=alerts@example.org",
                "demo.mailer.max-attempts=3")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void invalidNumberFailsDuringTypeConversion() {
        enabled("alerts@example.org", "not-a-number",
                "smtp.example.org", "2525")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void disabledAutoConfigurationDoesNotBindTheseProperties() {
        runner.withPropertyValues(
                "demo.mailer.enabled=false",
                "demo.mailer.max-attempts=not-a-number")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(MailerProperties.class);
                    assertThat(context).doesNotHaveBean(MailerClient.class);
                });
    }
}
~~~

**Cách chạy** trong dự án Java 17+ với Spring Boot 3.3 và dependency `spring-boot-starter-test`, `spring-boot-starter-validation`:

~~~bash
mvn -Dtest=MailerValidationTest test
# Hoặc Gradle wrapper trên Linux/macOS:
./gradlew test --tests example.library.MailerValidationTest
~~~

**Kết quả mong đợi:** **8 bài test PASS**, nếu dự án đã cấu hình dependency và Java phù hợp. Các test không có stdout cố định, vì chúng chỉ assert kết quả từ Spring context. Các bài kiểm tra `BindValidationException` xác nhận đường lỗi validation khi constraint sai; bài `invalidNumberFailsDuringTypeConversion` chỉ xác nhận context thất bại, vì wrapper/cause của lỗi conversion có thể khác với validation.

Đối với một dự án thực, có thể thêm assertion trên thông tin bind failure cụ thể, nhưng tránh so khớp toàn bộ message lỗi phụ thuộc phiên bản. Những kiểm thử quan trọng nhất là: cấu hình hợp lệ được bind, nested constraint được xét, giá trị sai làm context không start, và tính năng tắt không tạo bean properties thông qua **đường đăng ký auto-configuration này**.

## 7. Phân biệt cấu hình tắt và cấu hình bị lỗi

Thiết kế thư viện cần trả lời: **Nếu người dùng đặt `demo.mailer.enabled=false`, các thuộc tính bắt buộc bên trong có còn cần hợp lệ không?**

Trong ví dụ phần 6, điều kiện:

~~~java
@ConditionalOnProperty(
        prefix = "demo.mailer",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(MailerProperties.class)
~~~

nằm ở **cùng lớp auto-configuration**. Khi `enabled=false` hoặc thiếu khóa và `matchIfMissing` mặc định là `false`, lớp không được áp dụng; `MailerProperties` không được đăng ký bởi lớp đó. Vì vậy một `max-attempts` sai có thể **không bị bind/validate trên nhánh bị tắt**. Đây là lựa chọn thiết kế hữu ích cho các integration tùy chọn, nhưng không được hiểu là “mọi cấu hình sai đều luôn gây lỗi startup”.

Ngược lại, nếu `MailerProperties` được đăng ký **độc lập** bởi `@ConfigurationPropertiesScan` hoặc một `@EnableConfigurationProperties` khác, validation có thể chạy dù client đã bị condition chặn. Phải xác định rõ **ai là chủ sở hữu việc đăng ký properties bean**.

Lựa chọn thiết kế:

| Hợp đồng thư viện | Cách cấu hình phù hợp | Hệ quả |
| --- | --- | --- |
| Tính năng tùy chọn; chỉ cần properties khi bật | Gắn condition lên nhóm cấu hình đăng ký properties | Tắt tính năng thì bỏ qua binding theo đường đó |
| Properties chung cho nhiều tính năng, luôn cần hợp lệ | Đăng ký properties ở cấu hình chung | Validation độc lập với một client riêng có bật hay không |
| Cần cho phép custom client thay default nhưng vẫn ràng buộc toàn bộ properties | Dùng `@ConditionalOnMissingBean` cho default client, giữ đăng ký properties | Validation vẫn diễn ra nếu properties bean được tạo |
| Cần custom client không dùng nhóm properties mặc định | Xem xét phân nhóm/nested configuration để đăng ký properties đúng phạm vi | Không ép user cung cấp cấu hình cho thành phần họ đã thay hoàn toàn |

Không dùng `@ConditionalOnProperty` như một giải pháp “giấu” lỗi cấu hình không mong muốn. Nếu ứng dụng **đã yêu cầu** bật tính năng, các trường bắt buộc phải được ràng buộc rõ ràng và lỗi startup phải cho người dùng biết cách sửa.

## 8. Giá trị mặc định, giá trị thiếu, lỗi đánh máy

### Thiết kế default có chủ đích

Các giá trị tùy chọn có thể có default trong model cấu hình, ví dụ thông qua `@DefaultValue` cho constructor binding, hoặc field initializer của JavaBean binding. Tuy nhiên:

- Default phải **nằm trong miền hợp lệ** của constraint.
- Nếu một giá trị bắt buộc người triển khai quyết định, không nên điền default che thiếu sót.
- Với record, phân biệt `Integer` nullable với primitive `int`: `@NotNull` chỉ phát hiện thiếu trực tiếp trên reference; primitive không `null`.
- Không tự kết luận “thiếu khóa là lỗi” khi model có default hợp lệ.

### Khóa sai chính tả chưa chắc bị phát hiện

`@Validated` kiểm tra **những thuộc tính đã được bind vào model**. Nó không tự chứng minh rằng mọi khóa cấu hình trong file đều được khai báo đúng. Theo `@ConfigurationProperties`, `ignoreUnknownFields` mặc định là `true`. Vì vậy, một khóa sai tên có thể bị bỏ qua, còn field tương ứng có default hợp lệ thì validation vẫn PASS.

Có thể cân nhắc `ignoreUnknownFields=false` cho trường hợp muốn chính sách chặt hơn, nhưng cần hiểu phạm vi: **mọi khóa cùng prefix có thể bị xem là unknown nếu model không khai báo nó**. Trong ví dụ đang dùng, `demo.mailer.enabled` là cờ do `@ConditionalOnProperty` xử lý nhưng **không nằm trong record `MailerProperties`**. Nếu bật strict unknown checking mà không bổ sung cờ đó vào model hoặc đổi cấu trúc prefix, cấu hình hợp lệ có thể bị báo unknown. Vì vậy đừng bật strict một cách máy móc.

Tương tự, `ignoreInvalidFields=true` không phải cách chữa lỗi cấu hình; nó có thể bỏ qua những giá trị không chuyển được kiểu, làm mất thông tin quan trọng. Mặc định là không bỏ qua invalid fields.

### Cẩn thận với @Email

`@Email` chủ yếu kiểm tra **hình thức** địa chỉ email, không xác thực sự tồn tại của mailbox hay quyền gửi. Phạm vi kiểm tra cú pháp cụ thể do Bean Validation provider quyết định. Ràng buộc nghiệp vụ như “chỉ cho domain công ty” hoặc “port phải phù hợp với TLS mode” cần một constraint chuyên biệt hoặc bước kiểm tra logic riêng.

### Validation group và kiểm tra kết hợp

Spring `@Validated` có thể chỉ định nhóm validation; Jakarta Validation hỗ trợ group sequences và custom class-level constraints. Chỉ dùng khi sản phẩm thật sự có quy tắc phức tạp. Với đa số starter, một model rõ ràng cùng `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@Valid` và vài custom constraints cụ thể dễ bảo trì hơn.

Nếu cần một `org.springframework.validation.Validator` riêng cho configuration properties, Spring Boot có cơ chế bean tên `configurationPropertiesValidator`. Khi khai báo `@Bean` tạo validator theo cách này, tài liệu Boot khuyến nghị method `static` vì validator được tạo rất sớm trong lifecycle, tránh kéo theo khởi tạo `@Configuration` class quá sớm. Đừng tự viết custom validator khi Jakarta constraints đã mô tả đầy đủ yêu cầu.

## 9. Phản hồi lỗi cấu hình hiệu quả cho người tích hợp thư viện

Một thông báo lỗi hữu ích cần giúp người triển khai biết **sửa gì**:

- **Đúng khóa:** ví dụ `demo.mailer.max-attempts` chứ không chỉ `attempts`.
- **Loại lỗi:** conversion, missing required value, constraint range, hoặc quy tắc liên trường.
- **Giới hạn hợp lệ:** “từ 1 đến 8” thay vì một thông báo mơ hồ “invalid”.
- **Nguồn nếu có:** tên file/dòng hoặc property source; không đoán khi origin chưa có.
- **Hành động:** đổi cấu hình tại source đang thắng và khởi động lại.
- **Bảo mật:** không hiển thị token/password hay giá trị chứa secret trong custom failure message.

Ví dụ diễn giải khi nhận lỗi ở `demo.mailer.transport.port`:

~~~text
Property: demo.mailer.transport.port
Value: 70000
Reason: must be less than or equal to 65535
Action: Set demo.mailer.transport.port to an integer from 1 to 65535.
~~~

Đây là **mẫu thông báo rõ nghĩa**, không phải nguyên văn do Spring Boot 3.3 luôn sinh ra. Với dữ liệu nhạy cảm, nên tránh đưa bản thân value vào thông báo do thư viện tùy chỉnh.

**Cơ chế chuẩn và vai trò bổ sung:** Khi Bean Validation thất bại, Spring Boot đã có failure analysis cho nhiều trường hợp bind. Việc thêm một `FailureAnalyzer` riêng chỉ đáng cân nhắc nếu thư viện cần giải thích một quy tắc đặc thù mà lỗi mặc định khó hiểu. Một custom analyzer cần nhận diện exception phù hợp và trả về description/action có ích; không nên bắt mọi exception rồi biến thành “invalid configuration” khiến lỗi lập trình hoặc thiếu dependency bị che khuất.

## 10. Lỗi phổ biến và cách tránh

1. **Chỉ viết `@NotNull` mà quên `@Validated` trên properties class**: các constraint có thể không được áp dụng tự động trong luồng binding như mong đợi. Xác nhận provider và registration.
2. **Quên `spring-boot-starter-validation` trong runtime**: annotation đã biên dịch nhưng không có Bean Validation implementation phù hợp. Kiểm tra dependency của ứng dụng dùng starter.
3. **Quên `@Valid` trên nested object**: constraint ở các field sâu không được đảm bảo chạy. Dùng `@NotNull @Valid` nếu nested object luôn bắt buộc.
4. **Dùng `int` rồi hiểu thiếu khóa giống `null`**: primitive có giá trị mặc định; dùng wrapper + `@NotNull` khi muốn phát hiện thiếu trực tiếp.
5. **Cố gọi conversion error là @Min error**: `abc` không đổi được thành `Integer`; đây là lỗi binding, khác `0` bind được nhưng vi phạm ràng buộc.
6. **Không xét nguồn override**: file YAML hợp lệ nhưng env var ưu tiên cao hơn đưa giá trị sai. Chẩn đoán property source thắng và origin.
7. **Coi mọi typo đều được @Validated phát hiện**: unknown keys có thể bị bỏ qua; cân nhắc chính sách metadata/strict binding và test tên khóa quan trọng.
8. **Tự động in secret vào log chẩn đoán**: che hoặc bỏ giá trị nhạy cảm, chỉ giữ đường dẫn khóa và lý do khi có thể.
9. **Đăng ký properties ở nhiều đường**: condition tắt không nhất thiết ngăn binding nếu bean được đăng ký độc lập ở nơi khác.
10. **Viết test chỉ kiểm tra context fail**: cần cả test hợp lệ, test từng constraint, nested field, kiểu sai và trường hợp feature disabled để xác minh chủ đích thiết kế.

## 11. Tự kiểm tra kiến thức

**Câu 1.** `demo.mailer.max-attempts=abc`, field là `Integer` có `@Min(1)`. Lỗi xảy ra ở đâu trước?  
**Đáp án:** Chuyển đổi kiểu/binding thất bại trước khi kiểm tra ràng buộc số.

**Câu 2.** `max-attempts=0` với `@NotNull @Min(1)` có hợp lệ không?  
**Đáp án:** Không; `0` bind được thành `Integer` nhưng vi phạm `@Min(1)`.

**Câu 3.** `Transport` có field `host` gắn `@NotBlank`, nhưng cha chỉ khai báo `Transport transport` và không có `@Valid`. Có bảo đảm host được kiểm tra như mong muốn không?  
**Đáp án:** Không; cần `@Valid` để áp dụng cascade. Nếu bắt buộc phải có cả object, ghép `@NotNull`.

**Câu 4.** Thư viện có enabled flag ở cấp auto-configuration; khi disabled, có nhất thiết báo lỗi port sai?  
**Đáp án:** Không; nếu properties chỉ được đăng ký trong auto-configuration bị bỏ qua thì không có binding/validation theo đường đó. Nhưng nếu bean properties đăng ký ở nơi khác, nó vẫn có thể bị kiểm tra.

**Câu 5.** Vì sao `@Email` nên đi cùng `@NotBlank` khi địa chỉ người gửi bắt buộc?  
**Đáp án:** Constraint email kiểm tra hình thức; `@NotBlank` cấm giá trị thiếu/rỗng/chỉ chứa khoảng trắng.

**Câu 6.** `@ConfigurationProperties` có `ignoreUnknownFields=true`, một khóa thừa trong file có luôn bị coi là lỗi không?  
**Đáp án:** Không. Validation trên model đã bind không phải là kiểm tra mọi khóa không được khai báo trong toàn bộ file.

**Câu 7.** Mục tiêu của Failure Analysis trong trường hợp này là gì?  
**Đáp án:** Cung cấp tên property, giá trị/lý do và origin nếu có, để người triển khai sửa đúng nguồn, thay vì chỉ nhận một stack trace khó hiểu.

## Tài liệu đối chiếu

- [Spring Boot 3.3 — Externalized Configuration: Type-safe Configuration Properties và Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): cách đăng ký `@ConfigurationProperties`, binder, `@Validated`, nested `@Valid`, property source và origin.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): điều kiện cấu hình, `@EnableConfigurationProperties` trong starter và kiểm thử `ApplicationContextRunner`.
- [Spring Boot 3.3 — ConfigurationProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): `prefix`, `ignoreUnknownFields` và `ignoreInvalidFields`.
- [Spring Boot 3.3 — BindValidationException API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html): lỗi ràng buộc khi bind properties.
- [Jakarta Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Valid` và validation provider.

**Ghi nhớ:** Thư viện nên coi configuration properties là **một hợp đồng có kiểu, có ràng buộc và có phản hồi lỗi**. `@ConfigurationProperties` bind giá trị hiệu lực, `@Validated` cùng Jakarta constraints bảo vệ miền hợp lệ, `@Valid` kiểm tra object lồng nhau; condition của auto-configuration quyết định **khi nào** những properties đó thực sự được đăng ký và kiểm tra.
