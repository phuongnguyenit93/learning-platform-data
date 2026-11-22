# Kiểm thử cấu hình không hợp lệ và xác nhận lỗi khởi động

Spring Boot hỗ trợ externalized configuration qua `application.yml`, `application.properties`, các tài liệu theo profile, Config Data imports, biến môi trường, Java system properties và tham số dòng lệnh. Binder sẽ chuyển các giá trị này sang kiểu Java, thường thông qua `@ConfigurationProperties`. Một cấu hình có thể được đọc thành công nhưng **không hợp lệ để vận hành**: timeout không chuyển được sang `Duration`, token bắt buộc bị bỏ trống, số lần retry bằng 0 hoặc một phần tử trong danh sách endpoint thiếu URL.

Đối với nhiều service, lỗi như vậy nên được phát hiện **khi ứng dụng khởi động** thay vì đến request đầu tiên hoặc lúc hệ thống đã tiếp nhận công việc. Vì thế, kiểm thử cấu hình phải bao gồm cả hai chiều:

- **Positive test:** cấu hình đúng thì ApplicationContext khởi động được và bean nhận giá trị mong đợi.
- **Negative test:** cấu hình không hợp lệ thì ApplicationContext không khởi động được, và lỗi xuất phát từ binding/validation/bootstrap đúng như thiết kế.

Một negative test đúng vẫn **PASS trong JUnit** khi xác minh ứng dụng khởi động thất bại như kỳ vọng. Không nên coi việc chạy test suite rồi để toàn bộ suite đỏ là “đã kiểm tra lỗi khởi động”.

Bài học dùng Spring Boot 3.x, Java 17+, JUnit 5, AssertJ và Jakarta Bean Validation. API hoặc message lỗi có thể khác giữa các phiên bản; khi áp dụng cần thống nhất với Spring Boot đang dùng trong dự án.

## 1. Phân biệt các lớp lỗi cấu hình

Một bài kiểm thử âm tính cần biết lỗi sẽ phát sinh ở đâu.

| Lớp | Input không hợp lệ | Điểm phát hiện |
| --- | --- | --- |
| YAML/parser | Thiếu dấu đóng, sai cấu trúc YAML | Nạp Config Data |
| Config Data location | File được import bắt buộc nhưng không tồn tại | Bootstrap |
| Conversion | `timeout=tomorrow` vào `Duration` | Binder/conversion |
| Missing value | `api-key` không có | Validation hoặc logic bắt buộc |
| Bean Validation | `retries=0` với `@Min(1)` | Validate typed properties |
| Nested validation | Endpoint trong List thiếu URL | `@Valid` cascade |
| Strict unknown key | `max-retreis` do gõ sai | Cấu hình Binder strict nếu phù hợp |
| Cross-field rule | `enabled=true` nhưng thiếu endpoint | Custom/class-level validation |
| Bean composition | Properties type không được đăng ký | Khởi tạo ApplicationContext |
| Profile override | List từ dev làm mất trường của item | Binding/validation sau khi chọn source |

Các lỗi này đều có thể khiến Spring Boot “Failed to start”, nhưng **không có cùng nguyên nhân**. Nếu chỉ assert một exception bất kỳ, có thể vô tình chứng minh một lỗi classpath thay vì constraint được dự định.

## 2. Tiêu chí của một negative configuration test tốt

Một test cần trả lời:

1. Input sai cụ thể là gì?
2. Những property khác có được giữ hợp lệ để cô lập lỗi không?
3. Context có thất bại không?
4. Thất bại có thuộc nhóm lỗi mong đợi không?
5. Khi thay input thành hợp lệ, cùng test configuration có khởi động thành công không?
6. Có tránh log giá trị secret hoặc gọi external production services không?

Ví dụ test `max-retries=0` muốn chứng minh `@Min(1)` hoạt động. Nếu context thực ra fail vì thiếu datasource hoặc thiếu properties bean, assertion `hasFailed()` vẫn có thể pass nhưng **không kiểm tra được điều đã định**.

Do đó, nên có **baseline hợp lệ** và các case chỉ thay một tham số không hợp lệ.

## 3. Chuẩn bị dependencies

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Với Spring Boot 3.x, constraint API dùng `jakarta.validation`. Trên các dòng Boot cũ, namespace có thể khác. Trong một dự án sử dụng Spring Boot parent hoặc BOM, phiên bản dependency thường được quản lý đồng bộ; không thêm tùy ý nhiều Bean Validation providers.

Cần hiểu rằng `@NotBlank`, `@Min`, `@NotNull` và `@Valid` chỉ là annotation. Để validation thực sự chạy khi properties bean được bind, phải có infrastructure/provider và cơ chế kích hoạt phù hợp.

## 4. Một @ConfigurationProperties làm đối tượng kiểm thử

Cấu hình đúng:

~~~yaml
payment:
  client:
    endpoint: "https://api.example.invalid"
    timeout: 3s
    max-retries: 3
    api-key: "fake-test-key"
~~~

Java:

~~~java
package example.payment;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.client")
public record PaymentClientProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(1) @Max(5) int maxRetries,
        @NotBlank String apiKey
) {}
~~~

Hợp đồng cấu hình:

- `endpoint` phải có giá trị URI; `@NotNull` chưa bảo đảm URI là địa chỉ HTTP(S) có host hợp lệ.
- `timeout` phải có giá trị `Duration`; `@NotNull` chưa cấm `Duration.ZERO` hoặc thời lượng âm.
- `maxRetries` nằm trong 1..5.
- `apiKey` không null, rỗng hoặc toàn whitespace.

Cần đăng ký bean:

~~~java
package example.payment;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentClientProperties.class)
public class PaymentClientConfiguration {
}
~~~

Đừng bỏ bước registration rồi thử validation: một properties type không được tạo thành bean có thể khiến test vô tình kiểm tra lỗi hoàn toàn khác.

## 5. Công cụ phù hợp: ApplicationContextRunner

`ApplicationContextRunner` của Spring Boot Test tạo ApplicationContext nhỏ từ một tập configuration classes và property values do test cấp. Nó đặc biệt hữu ích vì **có thể quan sát startup failure mà không để JUnit thất bại trong setup trước khi test method chạy**.

Một runner:

~~~java
package example.payment;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class PaymentClientPropertiesTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
            .withUserConfiguration(PaymentClientConfiguration.class);
}
~~~

`withConfiguration(AutoConfigurations.of(...))` đưa auto-configuration hỗ trợ validation vào context nhỏ khi các điều kiện và dependencies phù hợp. `withUserConfiguration(...)` nạp registration của properties bean. `withPropertyValues(...)` cung cấp các giá trị test, còn `run(context -> ...)` cho phép xác minh khởi động thành công hoặc thất bại.

Một runner nhỏ **không mặc nhiên chạy đầy đủ mọi Spring Boot auto-configuration hoặc toàn bộ cơ chế đọc các file Config Data theo profile**. Nó phù hợp để kiểm tra binding/validation của một module. Những tình huống bootstrap phức tạp cần integration test riêng.

## 6. Baseline: cấu hình hợp lệ phải pass

~~~java
package example.payment;

import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentClientPropertiesTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
            .withUserConfiguration(PaymentClientConfiguration.class);

    @Test
    void validConfigurationStarts() {
        runner.withPropertyValues(
            "payment.client.endpoint=https://api.example.invalid",
            "payment.client.timeout=3s",
            "payment.client.max-retries=3",
            "payment.client.api-key=fake-test-key"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                .hasSingleBean(PaymentClientProperties.class);

            PaymentClientProperties props =
                context.getBean(PaymentClientProperties.class);

            assertThat(props.endpoint()).isEqualTo(
                URI.create("https://api.example.invalid"));
            assertThat(props.timeout()).isEqualTo(
                Duration.ofSeconds(3));
            assertThat(props.maxRetries()).isEqualTo(3);
        });
    }
}
~~~

Baseline khẳng định:

1. Configuration class được nạp.
2. `PaymentClientProperties` có mặt đúng một bean.
3. Binder chuyển URI, Duration và số nguyên đúng.
4. Validation không từ chối dữ liệu hợp lệ.
5. Test infrastructure hoạt động.

Nếu baseline đã fail, không nên tiếp tục diễn giải rằng các negative tests thành công. Trước hết phải sửa setup/registration của test.

## 7. Test vi phạm @Min nhưng dữ liệu vẫn đúng kiểu

~~~java
@Test
void zeroRetriesStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=3s",
        "payment.client.max-retries=0",
        "payment.client.api-key=fake-test-key"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
            .isNotNull();
    });
}
~~~

Số `0` vẫn chuyển được sang `int`. Lỗi là ràng buộc `@Min(1)`, không phải conversion. Cách kiểm tra này giúp phát hiện một service có thể tự chấp nhận retry policy không hợp lệ nếu annotation validation bị vô hiệu hoặc không chạy.

Một test tương tự cho `@Max(5)`:

~~~java
@Test
void tooManyRetriesStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=3s",
        "payment.client.max-retries=99",
        "payment.client.api-key=fake-test-key"
    ).run(context ->
        assertThat(context).hasFailed()
    );
}
~~~

Đừng dùng `max-retries=abc` để thử giới hạn của `@Min`, vì giá trị có thể không qua được bước conversion để đi tới Bean Validation.

## 8. Test lỗi binding/conversion

~~~java
@Test
void malformedDurationStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=not-a-duration",
        "payment.client.max-retries=3",
        "payment.client.api-key=fake-test-key"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
            .isNotNull();
    });
}
~~~

Ở đây `not-a-duration` không thể được chuyển sang `Duration` theo định dạng thường được hỗ trợ. Lỗi xảy ra trong Binder/conversion.

So sánh:

| Property | Java type | Nhóm lỗi |
| --- | --- | --- |
| `timeout=not-a-duration` | `Duration` | Conversion |
| `max-retries=many` | `int` | Conversion |
| `max-retries=0` | `int` + `@Min(1)` | Validation |
| `api-key=` | `String` + `@NotBlank` | Validation |
| Thiếu `endpoint` | `URI` + `@NotNull` | Validation hoặc binding theo contract |

`@DefaultValue` không phải cơ chế bỏ qua mọi dữ liệu có mặt nhưng sai định dạng. Default có ý nghĩa cho trường hợp thiếu key theo contract; conversion error vẫn cần được xử lý rõ.

## 9. Test thiếu property bắt buộc

Giữ endpoint, timeout và retries hợp lệ; chỉ **bỏ `api-key`**:

~~~java
@Test
void missingApiKeyStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=3s",
        "payment.client.max-retries=3"
    ).run(context ->
        assertThat(context).hasFailed()
    );
}
~~~

Giả định không có nguồn property khác cấp `payment.client.api-key`, Binder nhận null hoặc absence và `@NotBlank` từ chối. Nếu CI đã có biến môi trường hay system property cùng key, kết quả có thể khác — vì thế test nhỏ với tên namespace riêng là quan trọng.

Test blank khác missing:

~~~java
@Test
void blankApiKeyStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=3s",
        "payment.client.max-retries=3",
        "payment.client.api-key=   "
    ).run(context ->
        assertThat(context).hasFailed()
    );
}
~~~

Dữ liệu test chỉ dùng token giả; không ghi secret thật vào source, logs, assertion messages hoặc snapshots. Nếu muốn xác nhận lỗi đúng field, ưu tiên kiểm tra violation metadata hoặc cause type chứ không in raw value.

## 10. Null, blank, zero và giá trị thiếu là khác nhau

| Khai báo Java | Input | Có thể dẫn đến |
| --- | --- | --- |
| `@NotNull String name` | `""` | Qua @NotNull nhưng có thể không đạt nghiệp vụ |
| `@NotBlank String name` | `"   "` | Vi phạm @NotBlank |
| `@Min(1) int retries` | `0` | Vi phạm @Min |
| `@Min(1) Integer retries` | Vắng key | Null có thể qua @Min |
| `@NotNull @Min(1) Integer retries` | Vắng key | Vi phạm @NotNull |
| `@NotNull Duration timeout` | `0s` | Khác null, cần rule dương nếu muốn cấm |
| `@NotNull URI endpoint` | URI relative | Có thể qua @NotNull, cần rule scheme/host |

Một số numeric constraints như `@Min` thường xem null là hợp lệ; nếu key bắt buộc, kết hợp với `@NotNull`.

Với primitive, thiếu key có thể dùng mặc định Java như 0 hoặc false trong một số cấu trúc binding; không nên dựa vào điều này để biểu diễn sự vắng mặt nếu cần phân biệt “không khai báo” với “khai báo 0”. Wrapper như `Integer` giúp phân biệt rõ hơn.

## 11. Đọc nguyên nhân lỗi mà không gắn chặt vào chuỗi log

Khi ApplicationContext khởi động lỗi, framework thường wrap nguyên nhân qua nhiều tầng, chẳng hạn:

~~~text
BeanCreationException
    |
    +-- ConfigurationPropertiesBindException
            |
            +-- BindException
                    |
                    +-- conversion/validation cause
~~~

Sơ đồ là minh họa; kiểu và thứ tự wrapper có thể khác theo version và đường tạo bean.

Một helper duyệt cause chain:

~~~java
static boolean containsCause(
        Throwable error,
        Class<? extends Throwable> expected) {
    for (Throwable current = error;
         current != null;
         current = current.getCause()) {
        if (expected.isInstance(current)) {
            return true;
        }
    }
    return false;
}
~~~

Dùng với một exception type thuộc Spring Boot:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBindException;

@Test
void bindingErrorIsReportedAsConfigurationPropertiesFailure() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=not-a-duration",
        "payment.client.max-retries=3",
        "payment.client.api-key=fake-test-key"
    ).run(context -> {
        Throwable error = context.getStartupFailure();
        assertThat(error).isNotNull();
        assertThat(containsCause(
            error,
            ConfigurationPropertiesBindException.class
        )).isTrue();
    });
}
~~~

Assertion vào exception type giúp phân biệt lỗi binding với lỗi hoàn toàn khác. Muốn phân biệt conversion với validation chặt hơn, có thể xem `BindValidationException` hoặc các violation details theo API của phiên bản đang dùng.

Tránh assert nguyên văn toàn bộ failure analysis. Stack trace, tên bean và wording có thể thay đổi khi nâng cấp Boot/Framework, thậm chí thông báo lỗi có thể vô tình chứa giá trị nhạy cảm.

## 12. Kiểm tra đúng một lỗi trong mỗi test

Không nên tạo test như sau rồi chỉ assert context fail:

~~~properties
payment.client.endpoint=
payment.client.timeout=broken
payment.client.max-retries=0
payment.client.api-key=
~~~

Có ít nhất bốn vấn đề. Binder có thể dừng ngay ở conversion của Duration, khiến `@Min` và `@NotBlank` không được thử. Hoặc một lỗi khác xuất hiện trước khi validation chạy.

Tổ chức tốt hơn:

~~~text
Case A: dữ liệu hợp lệ -> PASS.
Case B: chỉ timeout sai format -> FAIL binding.
Case C: chỉ maxRetries=0 -> FAIL validation.
Case D: chỉ apiKey blank -> FAIL validation.
Case E: chỉ endpoint thiếu -> FAIL validation.
~~~

Đây là cách dễ chẩn đoán và bảo trì: sau một lần sửa ràng buộc, người đọc biết case nào bảo vệ hợp đồng nào.

Có thể thêm một integration test nhiều lỗi để kiểm tra failure analysis tổng thể, nhưng không dùng nó làm bằng chứng duy nhất cho tất cả constraints.

## 13. @DefaultValue làm thay đổi test expectation

Ví dụ record có default:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "batch")
public record BatchProperties(
        @DefaultValue("3s") Duration timeout,
        @DefaultValue("2") int retries
) {}
~~~

Khi source **không có** timeout hoặc retries, Binder có thể dùng default được khai báo; test missing property lúc này nên PASS và assert `3s`/`2`.

Ngược lại:

~~~properties
batch.timeout=not-a-duration
~~~

là giá trị có mặt nhưng sai format, không tự động được thay bằng `3s`. Một default hợp lý không phải cơ chế nuốt lỗi cấu hình.

Khi thay đổi hợp đồng Java, hãy cập nhật test matrix:

- Property required: thiếu phải fail.
- Property có default an toàn: thiếu phải pass, dùng đúng default.
- Property sai format: phải fail.
- Property bị nguồn ưu tiên cao ghi đè: phải lấy giá trị hiệu lực được chọn.

## 14. Nested objects cần @Valid để cascade validation

Một root có nested endpoint:

~~~java
@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @NotNull @Valid Server server
) {
    public record Server(
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

Nếu chỉ đặt `@NotNull Server server` mà thiếu `@Valid`, validator không nhất thiết đi vào host và port. Nếu chỉ đặt `@Valid Server server` mà thiếu `@NotNull`, null object thường không bị cascading validation từ chối.

Một bộ test nên có:

1. server vắng mặt: fail vì `@NotNull`.
2. server có host blank: fail vì `@NotBlank`.
3. server có port 0: fail vì `@Min(1)`.
4. server đầy đủ: pass.

Đừng dùng một object nested không có constraint rồi nghĩ `@Valid` đã bảo đảm “mọi field hợp lệ”; cascading chỉ áp dụng những ràng buộc được khai báo.

## 15. Kiểm thử List elements

YAML:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      timeout: 3s
    - name: ""
      url: "https://backup.example.invalid"
      timeout: 5s
~~~

Java:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotEmpty
        List<@NotNull @Valid Endpoint> endpoints
) {
    public record Endpoint(
            @NotBlank String name,
            @NotNull URI url,
            @NotNull Duration timeout
    ) {}
}
~~~

Ý nghĩa:

- `@NotEmpty`: List có ít nhất một item.
- `@NotNull` ở type argument: item không null.
- `@Valid`: đi vào field của mỗi Endpoint.
- `@NotBlank`/`@NotNull` ở Endpoint: bảo vệ các property bắt buộc.

Runner với registration tương ứng:

~~~java
private final ApplicationContextRunner routingRunner =
    new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
            ValidationAutoConfiguration.class))
        .withUserConfiguration(RoutingConfiguration.class);
~~~

Test lỗi ở item thứ hai:

~~~java
@Test
void blankEndpointNameStopsStartup() {
    routingRunner.withPropertyValues(
        "routing.endpoints[0].name=primary",
        "routing.endpoints[0].url=https://primary.example.invalid",
        "routing.endpoints[0].timeout=3s",
        "routing.endpoints[1].name=",
        "routing.endpoints[1].url=https://backup.example.invalid",
        "routing.endpoints[1].timeout=5s"
    ).run(context ->
        assertThat(context).hasFailed()
    );
}
~~~

`RoutingConfiguration` là một `@Configuration` có `@EnableConfigurationProperties(RoutingProperties.class)`. Test này chỉ có ý nghĩa khi runner có baseline hai endpoints hợp lệ cũng PASS.

## 16. Test Map values không hợp lệ

Ví dụ Map theo tên:

~~~yaml
clients:
  definitions:
    inventory:
      endpoint: "https://inventory.example.invalid"
      pool-size: 5
    pricing:
      endpoint: "https://pricing.example.invalid"
      pool-size: 0
~~~

Java:

~~~java
@Validated
@ConfigurationProperties(prefix = "clients")
public record ClientsProperties(
        @NotEmpty
        Map<String, @NotNull @Valid Client> definitions
) {
    public record Client(
            @NotNull URI endpoint,
            @Min(1) int poolSize
    ) {}
}
~~~

Khi `pricing.pool-size=0`, binding số nguyên có thể thành công, nhưng nested validation phải từ chối.

Một negative test có thể cấp:

~~~java
clientRunner.withPropertyValues(
    "clients.definitions.pricing.endpoint=https://pricing.example.invalid",
    "clients.definitions.pricing.pool-size=0"
).run(context -> assertThat(context).hasFailed());
~~~

`clientRunner` trong ví dụ là runner chuyên cho `ClientsProperties` có đăng ký bean và validation infrastructure tương ứng. Đừng dùng lại runner của `PaymentClientProperties` rồi suy luận Map sẽ được validate.

Nếu bỏ `@Valid` trên Map value, test có thể không còn bắt được các constraints trong Client. Đây là bằng chứng quan trọng rằng validation phải được đặt **đúng tầng**, không chỉ trên Map root.

## 17. Container-element constraints

Với danh sách String, `@NotEmpty List<String>` chỉ kiểm tra List không rỗng, không kiểm tra mỗi phần tử.

~~~java
@Validated
@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        @NotEmpty
        List<@NotBlank String> recipients
) {}
~~~

Input:

~~~properties
notifications.recipients[0]=ops@example.invalid
notifications.recipients[1]=
~~~

Phần tử thứ hai có thể bị `@NotBlank` từ chối.

Với Map, các constraint trực tiếp lên key/value cũng khác:

~~~java
Map<
    @NotBlank String,
    @NotNull @Min(1) Integer
> retryLimits
~~~

Nếu muốn test key có ký tự đặc biệt, cần hiểu Map binding/bracket notation và cách key được chuẩn hóa trước validation. Đừng kết luận validator hỏng chỉ vì input key đã được Binder biến đổi.

## 18. Profile thay List có thể tạo lỗi thiếu field

Spring Boot có quy tắc quan trọng: **List không được deep merge theo chỉ số giữa nhiều nguồn có mức ưu tiên khác nhau**. Khi profile ưu tiên cao định nghĩa lại List, List từ nguồn thấp có thể bị thay hoàn toàn.

File chung:

~~~yaml
# application.yml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      timeout: 3s
    - name: "backup"
      url: "https://backup.example.invalid"
      timeout: 5s
~~~

File dev:

~~~yaml
# application-dev.yml
routing:
  endpoints:
    - name: "local"
      url: "http://localhost:9090"
~~~

Nếu dev List thắng, endpoint local có thể không có timeout. Nó **không tự lấy 3s** từ phần tử cùng index ở file chung.

Một integration test có profile dev và `RoutingProperties` chứa `@NotNull Duration timeout` cần xác minh context từ chối cấu hình này. Tương tự, phần tử backup có thể không còn trong List hiệu lực.

**Lưu ý:** `ApplicationContextRunner.withPropertyValues(...)` cung cấp một tập test properties, không mặc nhiên tái tạo **hai Config Data PropertySources với thứ tự ưu tiên và profile khác nhau**. Test List replacement thật cần mô hình hóa hai nguồn hoặc dùng bootstrap/integration fixture nạp file theo profile.

## 19. Map merge cũng cần được kiểm tra sau binding

Map thường có khả năng kết hợp key/field từ các property sources theo độ ưu tiên. Nếu file chung có:

~~~yaml
# application.yml
clients:
  definitions:
    pricing:
      endpoint: "https://pricing.example.invalid"
      timeout: 3s
      pool-size: 5
~~~

và file dev chỉ ghi:

~~~yaml
# application-dev.yml
clients:
  definitions:
    pricing:
      endpoint: "http://localhost:9090"
~~~

Map entry pricing có thể lấy endpoint từ dev, timeout/pool-size từ base.

Validation chạy trên **object đã bind sau khi các nguồn được kết hợp**, không riêng từng file YAML. Test chỉ xem file dev thiếu timeout rồi assert fail có thể sai expectation nếu Map được thiết kế để kế thừa timeout từ cấu hình chung.

Với configuration security-sensitive, cần xác định rõ field nào được phép kế thừa qua profile và field nào phải được cấp theo môi trường.

## 20. Vì sao @SpringBootTest không thuận tiện cho expected startup failure?

Một negative test kiểu:

~~~java
@SpringBootTest(properties = {
    "payment.client.max-retries=0"
})
class InvalidConfigurationSpringBootTest {

    @Test
    void shouldFail() {
        // Test method có thể không bao giờ chạy.
    }
}
~~~

Spring Test thường cố tạo ApplicationContext trước khi test method thực thi. Nếu startup cố ý fail, JUnit có thể báo lỗi setup thay vì cho test method khẳng định điều mong muốn.

Với **positive integration test**, `@SpringBootTest` rất hữu ích. Với **expected failure của một configuration module**, `ApplicationContextRunner` thường đơn giản hơn.

Nếu muốn kiểm tra **giai đoạn bootstrap thực** (file import, YAML parser, profile), có thể tạo một SpringApplication tối giản trong test và assert exception, hoặc một test fixture chuyên biệt theo framework/version. Mục tiêu vẫn là JUnit PASS khi startup fail đúng lý do.

## 21. Các lỗi Config Data xảy ra trước binding

Một số lỗi không thể tái hiện chỉ bằng `withPropertyValues(...)`.

Ví dụ thiếu location bắt buộc:

~~~yaml
spring:
  config:
    import: "file:./config/required-settings.properties"
~~~

Nếu file không tồn tại, Spring Boot có thể fail trong Config Data loading trước khi tạo bean.

Tương phản với:

~~~yaml
spring:
  config:
    import: "optional:file:./config/local-settings.properties"
~~~

Khi location không tồn tại, `optional:` cho phép bỏ qua theo quy tắc hỗ trợ. Nhưng nó **không** làm giá trị sai kiểu, file có mặt nhưng sai cú pháp hoặc secret bắt buộc bị thiếu trở thành hợp lệ.

Các test nên tách:

1. Location bắt buộc vắng mặt → bootstrap fail.
2. Location optional vắng mặt → bootstrap có thể tiếp tục.
3. File có mặt nhưng YAML/properties sai định dạng → parse/load failure.
4. File hợp lệ nhưng giá trị sai kiểu → binding failure.
5. File hợp lệ nhưng vi phạm constraints → validation failure.

Đây là năm tình huống khác nhau dù có thể đều thấy một thông báo “Application failed to start”.

## 22. Một bài test bootstrap với SpringApplication độc lập

Ý tưởng khi muốn bắt một lỗi cấu hình từ giai đoạn sớm:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MissingImportBootstrapTest {

    @SpringBootConfiguration
    static class MinimalApp {}

    @Test
    void missingRequiredImportFails() {
        SpringApplication app =
            new SpringApplication(MinimalApp.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setDefaultProperties(Map.of(
            "spring.config.import",
            "file:./a-missing-required-test-file.properties"
        ));

        assertThatThrownBy(app::run)
            .isInstanceOf(Exception.class);
    }
}
~~~

Đây là **mẫu khái niệm cho một test bootstrap**, không phải fixture cô lập hoàn hảo cho mọi dự án. Khi đưa vào test thật:

- Dùng đường dẫn tạm riêng và xác nhận file không tồn tại.
- Bảo đảm `spring.config.import` không bị nguồn khác ghi đè.
- Dùng application fixture chỉ nạp những cấu hình cần thiết.
- Cô lập Config Data/application resources ngoài ý muốn.
- Xác minh loại nguyên nhân Config Data cụ thể, không dừng ở Exception chung.
- Nếu startup bất ngờ thành công, phải đóng context; không để resource leak.
- Không kết nối dịch vụ production.

Có thể dùng một helper chạy `SpringApplication` trong `try-with-resources` và assert trạng thái theo API test phù hợp.

## 23. Cú pháp YAML sai cần test đọc file thật

Ví dụ một YAML không hợp lệ:

~~~yaml
service:
  endpoints: [one, two
~~~

Khi source được đọc qua Config Data, parser có thể fail. Nhưng nếu test chỉ dùng:

~~~java
runner.withPropertyValues(
    "service.endpoints[0]=one",
    "service.endpoints[1]=two"
)
~~~

thì bạn **không kiểm tra parser YAML**. Runner nhận các key/value trực tiếp.

Nếu mục đích là kiểm tra pipeline xử lý file, cần sử dụng YAML fixture hoặc một bootstrap test nạp resource đó.

Hãy tránh cố biến một negative test chung thành test đồng thời YAML, Binder, validation và SpringApplication. Phân tầng sẽ làm kết quả nhanh và dễ xác định nguyên nhân hơn.

## 24. Unknown property không mặc định luôn là lỗi

Ví dụ typo:

~~~yaml
payment:
  client:
    max-retreis: 3
~~~

thay vì:

~~~yaml
payment:
  client:
    max-retries: 3
~~~

Nếu typed properties không có field `maxRetreis`, Binder có thể bỏ qua unknown field theo cấu hình mặc định của `@ConfigurationProperties`. Kết quả còn phụ thuộc field đích có default/validation hay không.

Có thể yêu cầu strict handling:

~~~java
@ConfigurationProperties(
    prefix = "payment.client",
    ignoreUnknownFields = false
)
public record PaymentClientProperties(
        int maxRetries
) {}
~~~

Nhưng strict unknown-field handling cần được kiểm thử trên **cấu trúc và nguồn thực tế**, vì module khác có thể chia sẻ prefix hoặc các key không ràng buộc thuộc phần mở rộng của ứng dụng.

Không nên xem `ignoreUnknownFields=false` là lời bảo đảm mọi typo trong mọi file đều được phát hiện. Thiết kế schema và test đúng prefix vẫn cần thiết.

## 25. Required và optional theo feature flag

Một tính năng có thể bị tắt mà không cần endpoint:

~~~yaml
billing:
  enabled: false
~~~

Nhưng khi bật:

~~~yaml
billing:
  enabled: true
  endpoint: "https://billing.example.invalid"
~~~

Muốn kiểm tra điều kiện, một record có thể dùng `@AssertTrue`:

~~~java
import jakarta.validation.constraints.AssertTrue;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "billing")
public record BillingProperties(
        boolean enabled,
        URI endpoint
) {
    @AssertTrue(message = "endpoint is required when enabled")
    public boolean isEndpointPresentWhenEnabled() {
        return !enabled || endpoint != null;
    }
}
~~~

Negative test phải chứng minh:

- `enabled=true` và endpoint thiếu → context fail.
- `enabled=false` và endpoint thiếu → context pass.
- `enabled=true` và endpoint có mặt → pass.

Lưu ý: `URI.create("relative-path")` có thể là URI hợp lệ theo Java nhưng không phải HTTP endpoint tuyệt đối. Muốn giới hạn scheme/host phải bổ sung validation phù hợp.

## 26. Tạo client có điều kiện không đồng nghĩa bỏ validation

Ví dụ:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "billing",
    name = "enabled",
    havingValue = "true"
)
BillingClient billingClient(BillingProperties properties) {
    return new BillingClient(properties.endpoint());
}
~~~

Nếu `BillingProperties` luôn được đăng ký, nó có thể vẫn bị bind/validate ngay cả khi BillingClient bean bị loại bởi điều kiện. Hai việc:

- Registration/validation của BillingProperties.
- Điều kiện tạo BillingClient.

là hai trách nhiệm khác nhau. Nếu feature tắt thì thiếu secret/endpoint hợp lệ, hãy thiết kế constraints có điều kiện hoặc boundary registration phù hợp rồi test cả trạng thái bật và tắt.

Một test chỉ assert `BillingClient` bean không tồn tại không chứng minh được rằng cấu hình bắt buộc đã được kiểm tra đúng khi feature hoạt động.

## 27. Kiểm tra Duration dương là rule riêng

`@NotNull Duration timeout` chưa đủ nếu ứng dụng cấm thời lượng bằng 0 hay âm.

Ví dụ:

~~~java
import jakarta.validation.constraints.AssertTrue;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotNull Duration timeout
) {
    @AssertTrue(message = "timeout must be positive")
    public boolean isTimeoutPositive() {
        return timeout != null
            && timeout.compareTo(Duration.ZERO) > 0;
    }
}
~~~

Test matrix:

~~~text
timeout=3s             -> Pass
timeout=0s             -> Fail validation
timeout=-1s            -> Fail validation
timeout=not-a-duration -> Fail conversion
timeout absent         -> Fail @NotNull
~~~

Không đặt `@Min(1)` tùy tiện lên `Duration` nếu validator không hỗ trợ kiểu ấy. Với business constraints, class-level validation hoặc custom constraint có thể rõ nghĩa hơn.

## 28. Cô lập externalized property sources trong CI

Những nguồn có thể làm test khác nhau giữa local và CI:

- OS environment variables.
- Java system properties.
- Các file `application-*.yml`.
- `@TestPropertySource` và `@SpringBootTest(properties=...)`.
- `@DynamicPropertySource` từ Testcontainers.
- Secret manager hoặc config directory được mount.
- Profile do hệ thống test kích hoạt.
- Command-line parameters hoặc custom PropertySource.

Một negative test “thiếu token phải fail” có thể bất ngờ pass nếu CI đã cung cấp key đó bằng environment variable.

Giảm rủi ro:

1. Dùng namespace key riêng cho module/test.
2. Dựng context tối giản và kiểm soát input.
3. Tránh đọc production resources/secrets.
4. Với integration test, khai báo profile và location rõ ràng.
5. Nếu nguồn cần phải thiếu, tạo fixture không thể vô tình bị cấp bởi máy chạy.
6. Không in raw Environment hoặc toàn bộ bean chứa secret.
7. Khi cần xem precedence, chỉ kiểm tra nguồn/giá trị giả được chọn một cách có kiểm soát.

## 29. Kiểm thử không được gây side effects

Một full application context có thể khởi tạo các bean **trước khi** một properties bean bị validation từ chối:

- Tạo kết nối tới database.
- Kết nối message broker.
- Gửi HTTP request.
- Đăng ký scheduled job.
- Gọi secret manager.
- Xuất telemetry tới endpoint bên ngoài.
- Ghi file hoặc tạo thread.

Với negative configuration tests, hãy dùng `ApplicationContextRunner` và nạp đúng configuration liên quan. Nếu cần full bootstrap:

- Tắt hoặc mock external integrations.
- Dùng database test hoặc Testcontainers, không dùng production.
- Sử dụng fake secrets.
- Đóng context nếu tình huống test bất ngờ startup thành công.
- Giải phóng file tạm và resources.
- Giữ test ổn định khi chạy song song.

Một test khởi động lỗi không được phép gây thay đổi dữ liệu thật chỉ vì framework đã tạo một bean sớm.

## 30. Các test có thể pass giả

**Pass giả 1 — Context fail vì thiếu bean.** Không có `@EnableConfigurationProperties`, nên lỗi injection chứ không phải validation.

**Pass giả 2 — Context fail vì DB unavailable.** Test không chứng minh `@Min` hoạt động.

**Pass giả 3 — Input sai bị nguồn ưu tiên cao ghi đè.** Test có thể pass một cách bất ngờ vì Binder nhận giá trị khác.

**Pass giả 4 — Chỉ test kiểu sai mà không test phạm vi.** `retries=abc` fail conversion, không chứng minh `@Min(1)`.

**Pass giả 5 — Không có validation provider.** Constraint tồn tại trong source nhưng không được thực thi trong test context.

**Pass giả 6 — Có @Validated nhưng nested thiếu @Valid.** Map/List vẫn có entry nhưng field bên trong không được kiểm tra.

**Pass giả 7 — Cố tình fail @SpringBootTest ở setup.** JUnit đỏ thay vì assertion âm tính pass.

**Pass giả 8 — Test file YAML bằng withPropertyValues.** Chưa hề kiểm tra YAML parser và Config Data.

**Pass giả 9 — Assert toàn bộ exception text.** Test dễ vỡ khi nâng cấp framework dù hành vi vẫn đúng.

**Pass giả 10 — Dùng secret thật để tái hiện lỗi.** Tăng rủi ro lộ dữ liệu trong logs/artifacts.

Đây là những lý do nên có baseline thành công, phân loại lỗi và giữ một phạm vi test nhỏ.

## 31. Bảng test matrix đầy đủ

| Kịch bản | endpoint | timeout | retries | api-key | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| Hợp lệ | URI đúng | 3s | 3 | fake | Startup pass |
| Endpoint thiếu | Không có | 3s | 3 | fake | Fail validation |
| Timeout thiếu | URI đúng | Không có | 3 | fake | Fail validation |
| Timeout sai format | URI đúng | bad | 3 | fake | Fail binding |
| Retry 0 | URI đúng | 3s | 0 | fake | Fail validation |
| Retry 6 | URI đúng | 3s | 6 | fake | Fail validation |
| Retry chữ | URI đúng | 3s | many | fake | Fail binding |
| Token thiếu | URI đúng | 3s | 3 | Không có | Fail validation |
| Token blank | URI đúng | 3s | 3 | spaces | Fail validation |
| Key chưa biết | URI đúng | 3s | 3 | fake | Tùy strict policy |

Với mỗi hàng, giữ các điều kiện ngoài mục tiêu ở giá trị hợp lệ. Nếu thêm `@DefaultValue` hoặc đổi rule business, matrix phải được cập nhật theo **hợp đồng mới**, không sửa assertion chỉ để làm test xanh.

## 32. Bài tập 1: batch configuration

Đề bài: service có cấu hình:

~~~yaml
batch:
  enabled: true
  max-threads: 4
  polling-interval: 5s
  queue-name: "orders"
~~~

Yêu cầu:

- maxThreads từ 1 đến 16.
- pollingInterval có mặt và dương.
- Nếu enabled=true, queueName không blank.
- Nếu enabled=false, queueName có thể vắng mặt.

Record:

~~~java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "batch")
public record BatchProperties(
        boolean enabled,
        @Min(1) @Max(16) int maxThreads,
        @NotNull Duration pollingInterval,
        String queueName
) {
    @AssertTrue(message = "queue-name is required when enabled")
    public boolean isQueueNameValid() {
        return !enabled ||
            (queueName != null && !queueName.isBlank());
    }

    @AssertTrue(message = "polling-interval must be positive")
    public boolean isPollingIntervalPositive() {
        return pollingInterval != null &&
            pollingInterval.compareTo(Duration.ZERO) > 0;
    }
}
~~~

Viết runner có validation infrastructure, đăng ký BatchProperties, sau đó kiểm tra:

1. Hợp lệ: pass.
2. `max-threads=0`: fail.
3. `max-threads=17`: fail.
4. `max-threads=abc`: conversion fail.
5. `polling-interval=0s`: validation fail.
6. `polling-interval=not-a-duration`: conversion fail.
7. Enabled true, queueName blank: validation fail.
8. Enabled false, queueName missing: pass nếu các field khác hợp lệ.

Câu hỏi: nếu đổi `@NotNull Duration pollingInterval` thành default `@DefaultValue("5s")`, test thiếu pollingInterval nên mong đợi kết quả nào? Đáp: pass với default hợp lệ, nếu không còn ràng buộc yêu cầu cấp tường minh.

## 33. Bài tập 2: Map clients và cascaded validation

YAML:

~~~yaml
integrations:
  clients:
    inventory:
      endpoint: "https://inventory.example.invalid"
      max-connections: 5
    pricing:
      endpoint: "https://pricing.example.invalid"
      max-connections: 0
~~~

Properties:

~~~java
@Validated
@ConfigurationProperties(prefix = "integrations")
public record IntegrationProperties(
        @NotEmpty
        Map<String, @NotNull @Valid Client> clients
) {
    public record Client(
            @NotNull URI endpoint,
            @Min(1) int maxConnections
    ) {}
}
~~~

Các test:

- Inventory hợp lệ: pass.
- Pricing maxConnections 0: fail validation.
- Map rỗng: fail.
- Endpoint bị thiếu trong một entry: fail validation.
- maxConnections là chữ: fail conversion.
- Bỏ `@Valid` khỏi Map value và chạy lại để thấy vì sao nested validation cần cascade.

Không chỉ test rằng Map tồn tại. Mục tiêu là xác nhận **giá trị bên trong các entries** được kiểm tra.

## 34. Bài tập 3: file cấu hình bắt buộc và secret

Ứng dụng dùng:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/orders/"
~~~

Và một typed property:

~~~java
@Validated
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        @NotBlank String apiToken
) {}
~~~

Test fixture cần phân biệt:

1. Directory không tồn tại và import bắt buộc: bootstrap fail.
2. Directory tồn tại nhưng thiếu file token: validation fail.
3. File token rỗng: validation fail.
4. File chứa token giả: startup pass.
5. Import `optional:configtree:` và directory vắng: bootstrap có thể tiếp tục nhưng token vẫn required nếu module bật.
6. Secret bị cung cấp bằng nguồn ưu tiên khác: kiểm tra giá trị hiệu lực theo cấu hình thực, không dựa vào việc file đã tồn tại.

Không dùng production token. Test cần chuẩn bị directory/file trước khi Config Data được xử lý và xóa fixture sau khi kết thúc.

## 35. Quy trình triển khai kiểm thử trong dự án

Một quy trình có thể áp dụng lặp lại:

**Bước 1:** Liệt kê các nhóm cấu hình quan trọng và phân biệt required/default/optional.

**Bước 2:** Định nghĩa typed configuration qua `@ConfigurationProperties`. Dùng `@Validated`, constraint thích hợp và `@Valid` cho nested objects.

**Bước 3:** Đăng ký properties type bằng `@EnableConfigurationProperties` hoặc scanning, không đánh đồng nó với `@Component` của service.

**Bước 4:** Tạo một `ApplicationContextRunner` tối giản cho nhóm cấu hình.

**Bước 5:** Viết baseline thành công và xác nhận giá trị đã bind.

**Bước 6:** Viết negative cases: thiếu, blank, sai kiểu, ngoài giới hạn, nested thiếu field.

**Bước 7:** Với các trường hợp có ý nghĩa, assert loại nguyên nhân trong cause chain để tránh false-positive.

**Bước 8:** Viết integration tests riêng cho profile-specific Config Data, import location và YAML parser.

**Bước 9:** Cô lập environment/test data, bảo đảm không có secret thật hoặc side effects.

**Bước 10:** Chạy test ở CI bằng JDK và Spring Boot versions của dự án, không tùy tiện tắt validation để làm build xanh.

**Bước 11:** Khi thay đổi schema/defaults/constraints, cập nhật test matrix như một phần của thay đổi hợp đồng cấu hình.

**Bước 12:** Trên staging, thử ứng dụng với cấu hình triển khai thực và health/readiness policy; không dùng negative unit test làm thay thế smoke test.

## 36. Checklist tổng hợp

- [ ] Có một baseline hợp lệ khởi động thành công.
- [ ] Properties type được đăng ký đúng và có `@Validated` khi cần.
- [ ] Có Bean Validation provider tương thích.
- [ ] Required fields có constraints tương ứng.
- [ ] Wrapper/null/default semantics được xem xét.
- [ ] Có test conversion error riêng với validation error.
- [ ] Có test `@Min`/`@Max` bằng số hợp lệ về kiểu nhưng sai phạm vi.
- [ ] Nested List/Map có `@Valid` và constraint đúng tầng.
- [ ] Một negative case chỉ tạo lỗi chính có chủ đích.
- [ ] Có kiểm tra cause type khi cần bảo đảm fail đúng lý do.
- [ ] Không assert toàn bộ stack trace dễ thay đổi.
- [ ] Có test Config Data/profile nếu cấu hình dùng nhiều nguồn.
- [ ] Không dùng `withPropertyValues` để tự nhận đã test YAML parser.
- [ ] Không dùng full `@SpringBootTest` sai cấu hình làm expected-failure test một cách mơ hồ.
- [ ] Không dùng production secrets hoặc external services.
- [ ] Startup failure được xác minh mà JUnit test vẫn PASS.
- [ ] Test chạy ổn định trong local/CI và không rò rỉ tài nguyên.

## 37. Ghi nhớ

**Kiểm thử cấu hình không hợp lệ là kiểm thử hợp đồng khởi động của Spring Boot.** Một test âm tính đáng tin cậy phải chứng minh ứng dụng **từ chối input sai vì lý do đúng**. `ApplicationContextRunner` rất phù hợp cho binding và Bean Validation; `@SpringBootTest` thích hợp hơn cho positive integration; còn YAML parse, profile-specific Config Data và import location có thể cần kiểm thử bootstrap thật.

Phải phân biệt **binding/conversion failure**, **validation failure**, **missing property**, **bean registration failure** và **Config Data bootstrap failure**. Viết baseline hợp lệ, từng case invalid có chủ đích, assertion đủ đặc hiệu và giữ test cô lập sẽ giúp phát hiện lỗi trước triển khai, tránh trạng thái ứng dụng chạy nửa chừng với cấu hình nguy hiểm.

**Công thức ngắn:** cấu hình hợp lệ phải khởi động được; cấu hình sai phải khởi động thất bại có kiểm soát; test phải chứng minh đúng nguyên nhân mà không lộ bí mật.
