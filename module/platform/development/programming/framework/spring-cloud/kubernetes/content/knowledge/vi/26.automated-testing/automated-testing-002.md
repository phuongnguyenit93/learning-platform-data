# Kiểm thử binding và validation của cấu hình

Một ConfigMap có YAML hợp lệ vẫn có thể chứa timeout sai đơn vị, tên thuộc tính gõ nhầm hoặc giá trị không đáp ứng yêu cầu của ứng dụng. Một Secret đã được tạo cũng chưa chứng minh ứng dụng nạp đúng khóa và sử dụng giá trị đó đúng cách. Kiểm thử binding và validation giúp phát hiện những lỗi thuộc hợp đồng cấu hình trước khi phải điều tra một Pod khởi động thất bại.

Trong chương **Kiểm thử tự động** của module **SPRING_CLOUD_KUBERNETES**, bài học này tập trung vào đoạn từ thuộc tính trong Spring `Environment` đến đối tượng cấu hình đã kiểm tra ràng buộc. Đoạn đó liên quan trực tiếp đến ConfigMap, Secret và tham số của các client; còn DiscoveryClient, Spring Cloud LoadBalancer, Configuration Watcher và RBAC cần thêm những phép thử tích hợp phù hợp.

Sau bài học, bạn có thể:

- Định nghĩa hợp đồng cấu hình bằng `@ConfigurationProperties` và Jakarta Bean Validation.
- Kiểm tra giá trị mặc định, chuyển kiểu, cấu hình lồng nhau và quy tắc liên trường.
- Phân biệt thất bại binding với thất bại validation.
- Viết test context nhỏ, không phụ thuộc Kubernetes API hoặc kubeconfig của máy chạy.
- Kiểm tra payload YAML và ánh xạ biến môi trường mà không nhầm chúng với kiểm thử tải cấu hình từ cluster.

## 1. Xác định đoạn cần kiểm thử

Luồng xử lý có thể nhìn theo các bước:

~~~mermaid
flowchart LR
    K["ConfigMap, Secret, file hoặc biến môi trường"] --> L["Cơ chế nạp và chọn nguồn"]
    L --> E["Spring Environment"]
    E --> B["Binding và chuyển kiểu"]
    B --> V["Validation"]
    V --> P["Bean cấu hình hợp lệ"]
    P --> U["Thành phần sử dụng cấu hình"]
~~~

Mỗi đoạn có thể sai theo cách khác nhau:

| Lớp | Ví dụ lỗi | Phép thử phù hợp |
| --- | --- | --- |
| Nạp nguồn | Sai namespace, thiếu quyền, sai tên ConfigMap | Test tích hợp cơ chế nạp hoặc cluster |
| Chọn nguồn | Biến môi trường ghi đè giá trị dự định lấy từ ConfigMap | Test thứ tự ưu tiên theo đường nạp thực tế |
| Binding | Chuỗi `abc` không chuyển được thành `Duration` | Test binder/context |
| Validation | Timeout chuyển kiểu được nhưng vượt ngân sách cho phép | Test ràng buộc và test context |
| Sử dụng | Bean cấu hình đúng nhưng HTTP client vẫn dùng timeout cũ | Test thành phần sử dụng cấu hình |
| Cập nhật | Watcher phát hiện thay đổi nhưng một replica chưa áp dụng | Test tích hợp refresh theo instance |

Không cần cluster thật để kiểm tra mọi dòng trong bảng. Chọn context nhỏ cho hợp đồng cấu hình giúp test chạy ổn định và chỉ rõ nguyên nhân khi thất bại.

Ngược lại, đưa một `MapPropertySource` có tên `configMapFixture` vào test chỉ mô phỏng thuộc tính đã nạp. Tên đó không làm test gọi Kubernetes API.

## 2. Thiết lập ví dụ và hợp đồng cấu hình

Bộ ví dụ sử dụng **Java 17 trở lên, Spring Boot 3.5.x, JUnit Jupiter và AssertJ**. Các import được viết cho nhánh Spring Boot này; khi dùng nhánh khác, đối chiếu API tương ứng. Spring Cloud Kubernetes của ứng dụng cần được chọn theo bộ phiên bản tương thích của dự án, không thêm một version tùy ý chỉ để chạy test binding.

Giả sử ứng dụng `catalog` có một client với hợp đồng:

| Thuộc tính | Kiểu | Quy tắc |
| --- | --- | --- |
| `catalog.client.service-id` | `String` | Bắt buộc, không trắng |
| `catalog.client.connect-timeout` | `Duration` | Mặc định `2s`, từ `100ms` đến `30s`, kể cả hai biên |
| `catalog.client.max-in-flight` | `int` | Mặc định `20`, từ `1` đến `100` |
| `catalog.client.retry.enabled` | `boolean` | Mặc định `false` |
| `catalog.client.retry.max-attempts` | `int` | Mặc định `1`, từ `1` đến `5` |
| Quan hệ retry | Quy tắc liên trường | Nếu bật retry, `max-attempts` phải từ `2` trở lên |

Trong ví dụ, `max-attempts` tính cả lần gọi đầu tiên. Các giới hạn trên là quyết định thiết kế của bài học, không phải giá trị mặc định của Spring Cloud Kubernetes.

Prefix `catalog.client` cũng do ứng dụng định nghĩa. Các thuộc tính này chưa tự cấu hình DiscoveryClient hoặc Spring Cloud LoadBalancer; mã tạo client phải sử dụng chúng một cách rõ ràng.

### 2.1. Dependency cần thiết

Trong dự án đã dùng dependency management của Spring Boot, các dependency Maven liên quan là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Starter validation cung cấp implementation cho Jakarta Bean Validation. Chỉ có các annotation trong mã nguồn chưa đủ để bảo đảm quá trình validation sẽ thực hiện khi chạy.

Các test dưới đây không cần Kubernetes client, Web server, DiscoveryClient hay Configuration Watcher. Những thành phần đó được giữ ngoài context của test.

### 2.2. Lớp cấu hình có kiểu và ràng buộc

~~~java
package com.example.catalog.config;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
    prefix = "catalog.client",
    ignoreUnknownFields = false
)
public record CatalogClientProperties(
    @NotBlank
    String serviceId,

    @NotNull
    @DefaultValue("2s")
    Duration connectTimeout,

    @Min(1)
    @Max(100)
    @DefaultValue("20")
    int maxInFlight,

    @Valid
    @NotNull
    @DefaultValue
    Retry retry
) {

    @AssertTrue(message = "connect-timeout must be between 100ms and 30s")
    public boolean isConnectTimeoutWithinBudget() {
        return connectTimeout == null
            || (connectTimeout.compareTo(Duration.ofMillis(100)) >= 0
                && connectTimeout.compareTo(Duration.ofSeconds(30)) <= 0);
    }

    @AssertTrue(message = "enabled retry requires at least 2 attempts")
    public boolean isRetryPolicyConsistent() {
        return retry == null
            || !retry.enabled()
            || retry.maxAttempts() >= 2;
    }

    public record Retry(
        @DefaultValue("false")
        boolean enabled,

        @Min(1)
        @Max(5)
        @DefaultValue("1")
        int maxAttempts
    ) {
    }
}
~~~

Các lựa chọn cần hiểu:

- `@ConfigurationProperties` khai báo prefix và mô hình nhận dữ liệu.
- `@Validated` yêu cầu Spring Boot kiểm tra bean cấu hình khi binding.
- `@NotBlank` bắt trường hợp thiếu, rỗng hoặc chỉ có khoảng trắng của `serviceId`.
- `@DefaultValue` khai báo giá trị mặc định cho constructor binding; annotation không có chuỗi trên `retry` yêu cầu tạo đối tượng lồng với các mặc định của nó.
- `@Valid` cho phép validation đi vào cấu hình lồng nhau.
- Hai getter `is...` có `@AssertTrue` biểu diễn quy tắc mà annotation số đơn lẻ không thể diễn đạt.

Các getter kiểm tra quan hệ trả `true` khi giá trị cần kiểm tra là `null`, để `@NotNull` chịu trách nhiệm báo lỗi thiếu dữ liệu. Cách này tránh một `NullPointerException` làm che mất lỗi cấu hình.

`ignoreUnknownFields = false` là lựa chọn có chủ đích để bắt khóa dư trong prefix của ứng dụng. Nó không kiểm tra mọi khóa của toàn bộ `Environment`; cũng cần cân nhắc nếu nhiều bean dùng chung một prefix hoặc cần giữ tương thích với khóa mở rộng.

Cơ chế constructor binding, mặc định và đăng ký bean được mô tả trong [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#features.external-config.typesafe-configuration-properties). Ý nghĩa các constraint và validation lồng nhau có trong [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).

### 2.3. Đăng ký bean trong ứng dụng

Trong ứng dụng thật, có thể đăng ký tường minh:

~~~java
package com.example.catalog.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
public class CatalogClientConfiguration {
}
~~~

Đặt configuration này trong vùng được ứng dụng nạp. Nếu dự án dùng `@ConfigurationPropertiesScan`, chọn cách đăng ký phù hợp và tránh đăng ký trùng không cần thiết.

Gọi trực tiếp `new CatalogClientProperties(...)` chỉ gọi constructor Java. Nó không tự thực hiện pipeline binding của Spring và cũng không tự gọi Bean Validation. Vì vậy, một test tạo record bằng `new` rồi đọc accessor chưa chứng minh cấu hình từ ConfigMap sẽ được kiểm tra khi khởi động.

## 3. Dựng test context nhỏ và cô lập nguồn ngoài

`ApplicationContextRunner` tạo một context cho từng lần `run`, cho phép cấp thuộc tính và kiểm tra cả khởi động thành công lẫn thất bại. Cách dùng được trình bày trong [Spring Boot — Testing your Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).

Lớp test sau dùng lại `CatalogClientConfiguration`. Nó chỉ nạp cấu hình cần kiểm tra và auto-configuration validation. Initializer loại nguồn system properties và biến môi trường **khỏi Environment của context test**, không sửa `System.getProperties()` hoặc môi trường thật của tiến trình.

~~~java
package com.example.catalog.config;

import java.time.Duration;
import java.util.List;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.UnboundConfigurationPropertiesException;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.validation.FieldError;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
            .withUserConfiguration(CatalogClientConfiguration.class)
            .withInitializer(context -> {
                var sources = context.getEnvironment().getPropertySources();
                sources.remove(
                    StandardEnvironment.SYSTEM_ENVIRONMENT_PROPERTY_SOURCE_NAME);
                sources.remove(
                    StandardEnvironment.SYSTEM_PROPERTIES_PROPERTY_SOURCE_NAME);
            });

    private ApplicationContextRunner validRunner() {
        return runner.withPropertyValues(
            "catalog.client.service-id=catalog");
    }

    @Test
    void bindsExplicitValues() {
        validRunner()
            .withPropertyValues(
                "catalog.client.connect-timeout=750ms",
                "catalog.client.max-in-flight=8",
                "catalog.client.retry.enabled=true",
                "catalog.client.retry.max-attempts=3")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(
                    CatalogClientProperties.class);

                var properties =
                    context.getBean(CatalogClientProperties.class);

                assertThat(properties.serviceId()).isEqualTo("catalog");
                assertThat(properties.connectTimeout())
                    .isEqualTo(Duration.ofMillis(750));
                assertThat(properties.maxInFlight()).isEqualTo(8);
                assertThat(properties.retry().enabled()).isTrue();
                assertThat(properties.retry().maxAttempts()).isEqualTo(3);
            });
    }

    @Test
    void appliesDefaultsWhenOptionalKeysAreMissing() {
        validRunner().run(context -> {
            assertThat(context).hasNotFailed();

            var properties =
                context.getBean(CatalogClientProperties.class);

            assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofSeconds(2));
            assertThat(properties.maxInFlight()).isEqualTo(20);
            assertThat(properties.retry()).isNotNull();
            assertThat(properties.retry().enabled()).isFalse();
            assertThat(properties.retry().maxAttempts()).isEqualTo(1);
        });
    }

    @Test
    void rejectsMissingRequiredServiceId() {
        runner.run(context -> {
            assertThat(context).hasFailed();
            assertValidationError(
                context.getStartupFailure(), "serviceId", "NotBlank");
        });
    }

    @ValueSource(strings = {"", "   "})
    @ParameterizedTest
    void rejectsBlankServiceId(String value) {
        runner
            .withPropertyValues("catalog.client.service-id=" + value)
            .run(context -> {
                assertThat(context).hasFailed();
                assertValidationError(
                    context.getStartupFailure(), "serviceId", "NotBlank");
            });
    }

    @Test
    void rejectsUnconvertibleTimeout() {
        validRunner()
            .withPropertyValues("catalog.client.connect-timeout=abc")
            .run(context -> {
                assertThat(context).hasFailed();

                findCause(
                    context.getStartupFailure(), BindException.class);
                findCause(
                    context.getStartupFailure(),
                    ConversionFailedException.class);
            });
    }

    @CsvSource({
        "catalog.client.max-in-flight=0, maxInFlight, Min",
        "catalog.client.max-in-flight=101, maxInFlight, Max",
        "catalog.client.connect-timeout=0ms, connectTimeoutWithinBudget, AssertTrue",
        "catalog.client.connect-timeout=31s, connectTimeoutWithinBudget, AssertTrue",
        "catalog.client.retry.max-attempts=0, maxAttempts, Min",
        "catalog.client.retry.max-attempts=6, maxAttempts, Max",
        "catalog.client.retry.enabled=true, retryPolicyConsistent, AssertTrue"
    })
    @ParameterizedTest
    void rejectsConstraintViolations(
            String override, String field, String code) {
        validRunner()
            .withPropertyValues(override)
            .run(context -> {
                assertThat(context).hasFailed();
                assertValidationError(
                    context.getStartupFailure(), field, code);
            });
    }

    @CsvSource({
        "100ms, 1",
        "30s, 100"
    })
    @ParameterizedTest
    void acceptsInclusiveBoundaries(String timeout, int maxInFlight) {
        validRunner()
            .withPropertyValues(
                "catalog.client.connect-timeout=" + timeout,
                "catalog.client.max-in-flight=" + maxInFlight)
            .run(context -> {
                assertThat(context).hasNotFailed();

                var properties =
                    context.getBean(CatalogClientProperties.class);

                assertThat(properties.connectTimeout())
                    .isEqualTo(Duration.parse(
                        timeout.equals("100ms") ? "PT0.1S" : "PT30S"));
                assertThat(properties.maxInFlight())
                    .isEqualTo(maxInFlight);
            });
    }

    @Test
    void rejectsUnknownKeyInsideThePrefix() {
        validRunner()
            .withPropertyValues("catalog.client.connect-timeot=750ms")
            .run(context -> {
                assertThat(context).hasFailed();

                var failure = findCause(
                    context.getStartupFailure(),
                    UnboundConfigurationPropertiesException.class);

                assertThat(failure.getUnboundProperties())
                    .extracting(property ->
                        property.getName().toString())
                    .contains("catalog.client.connect-timeot");
            });
    }

    private static void assertValidationError(
            Throwable failure, String leafField, String code) {
        var validation = findCause(
            failure, BindValidationException.class);

        List<FieldError> errors = validation.getValidationErrors()
            .getAllErrors()
            .stream()
            .filter(FieldError.class::isInstance)
            .map(FieldError.class::cast)
            .toList();

        assertThat(errors).anySatisfy(error -> {
            assertThat(error.getField()).matches(
                "(?:.*\\.)?" + Pattern.quote(leafField));
            assertThat(error.getCode()).isEqualTo(code);
        });
    }

    private static <T extends Throwable> T findCause(
            Throwable failure, Class<T> expectedType) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return expectedType.cast(current);
            }
        }

        throw new AssertionError(
            "Missing failure type: " + expectedType.getName(),
            failure);
    }
}
~~~

Trong test biên, hai giá trị mong đợi được viết độc lập dưới dạng ISO-8601 để đối chiếu kết quả chuyển từ `100ms` và `30s`. Đây là kiểm tra hợp đồng về đơn vị và biên cho phép.

## 4. Đọc đúng ý nghĩa của các assertion

### 4.1. Trường hợp thành công phải kiểm tra đối tượng kết quả

`hasNotFailed()` chỉ chứng minh context không thất bại. Nếu bean cấu hình không được đăng ký, một context trống vẫn có thể khởi động thành công.

Vì vậy, test đầu tiên còn kiểm tra:

- Có đúng một bean cấu hình.
- Chuỗi service ID được giữ đúng.
- `750ms` trở thành `Duration` đúng giá trị.
- Các số và boolean được binding.
- Đối tượng retry lồng nhau chứa dữ liệu mong đợi.

Test mặc định cố ý chỉ cấp thuộc tính bắt buộc. Nếu fixture luôn cấp đầy đủ mọi khóa, test sẽ không phát hiện việc mất hoặc thay đổi giá trị mặc định.

### 4.2. Test thất bại phải chỉ ra nguyên nhân cần bắt

Một test chỉ có `hasFailed()` có thể vượt qua vì thiếu class, thiếu bean hoặc lỗi khởi tạo ngoài ý muốn. Mỗi test âm ở trên bắt đầu từ một đầu vào hợp lệ, thay đổi một phần và tìm đúng loại lỗi.

| Đầu vào | Loại lỗi cần nhận diện |
| --- | --- |
| `connect-timeout=abc` | Binding/chuyển kiểu |
| `connect-timeout=31s` | Chuyển kiểu được, nhưng vi phạm validation |
| Thiếu `service-id` | Validation của trường bắt buộc |
| `retry.max-attempts=0` | Validation của đối tượng lồng |
| Bật retry nhưng giữ mặc định một lần gọi | Validation quan hệ liên trường |
| Khóa `connect-timeot` | Thuộc tính không được bind khi bật chế độ nghiêm ngặt |

`BindException` của Spring Boot nằm trong package `org.springframework.boot.context.properties.bind`; không nhầm với exception cùng tên ở package khác. Nó có thể xuất hiện trong chuỗi cause của lỗi tạo bean. [API BindException](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/bind/BindException.html) cung cấp tên thuộc tính và thông tin đích binding để hỗ trợ chẩn đoán.

Validation có kiểu lỗi riêng là [BindValidationException](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html). Ví dụ dùng error code thay vì so khớp toàn bộ thông báo tiếng Anh, vì thông báo có thể đổi theo locale hoặc phiên bản.

Helper chấp nhận tên trường lá hoặc đường dẫn kết thúc bằng tên đó. Trong fixture hiện tại, tên lá không bị trùng giữa nhiều nhánh; nếu mô hình lớn hơn có nhiều `maxAttempts`, bổ sung kiểm tra prefix và đường dẫn đầy đủ để tránh assertion trúng nhầm trường.

### 4.3. Không biến validation thành hoạt động gọi mạng

Quy tắc như “số lần thử phải hợp lệ” là kiểm tra cục bộ, xác định được từ dữ liệu cấu hình. “Service có endpoint đang Ready không?” hoặc “Secret có được hệ thống đích chấp nhận không?” là quan sát bên ngoài.

Không gọi Kubernetes API, database hoặc downstream service từ getter `@AssertTrue`. Nếu làm vậy, test binding sẽ phụ thuộc mạng và lỗi cấu hình sẽ khó phân biệt với lỗi hạ tầng.

## 5. Kiểm thử đúng payload YAML của ConfigMap

Giả sử manifest dùng cấu hình nhúng:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-config
  namespace: spring-cloud-lab
data:
  application.yaml: |-
    catalog:
      client:
        service-id: catalog
        connect-timeout: 750ms
        max-in-flight: 8
        retry:
          enabled: true
          max-attempts: 3
~~~

Có hai lớp YAML:

1. YAML của tài nguyên Kubernetes, có `apiVersion`, `kind`, `metadata`, `data`.
2. Chuỗi YAML ứng dụng nằm trong `data["application.yaml"]`.

Binder của Spring không tự lấy cấu hình ứng dụng từ `data.application.yaml` nếu bạn đưa nguyên manifest vào một YAML loader thông thường. Test binding cần nhận đúng payload hoặc đúng tập thuộc tính đã được cơ chế nạp tạo ra.

Để bổ sung phép thử payload vào lớp `CatalogClientPropertiesTest`, thêm các import:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.io.ByteArrayResource;
~~~

Sau đó thêm phương thức:

~~~java
@Test
void bindsRepresentativeConfigMapPayload() throws IOException {
    String yaml = """
        catalog:
          client:
            service-id: catalog
            connect-timeout: 750ms
            max-in-flight: 8
            retry:
              enabled: true
              max-attempts: 3
        """;

    var resource = new ByteArrayResource(
        yaml.getBytes(StandardCharsets.UTF_8));

    var sources = new YamlPropertySourceLoader()
        .load("configmap-payload", resource);

    assertThat(sources).hasSize(1);

    runner
        .withInitializer(context -> {
            var propertySources =
                context.getEnvironment().getPropertySources();

            sources.forEach(propertySources::addLast);
        })
        .run(context -> {
            assertThat(context).hasNotFailed();

            var properties =
                context.getBean(CatalogClientProperties.class);

            assertThat(properties.serviceId()).isEqualTo("catalog");
            assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofMillis(750));
            assertThat(properties.maxInFlight()).isEqualTo(8);
            assertThat(properties.retry().enabled()).isTrue();
            assertThat(properties.retry().maxAttempts()).isEqualTo(3);
        });
}
~~~

Dùng `runner` thay vì `validRunner()` ở đây để `service-id` phải đến từ payload. Nếu luôn cấp lại cùng khóa bằng thuộc tính test, YAML bị thiếu khóa vẫn có thể bị fixture che lỗi.

[YamlPropertySourceLoader](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/env/YamlPropertySourceLoader.html) tải YAML thành một hoặc nhiều property source. Ví dụ cố ý chỉ dùng một document. Việc tự thêm các source không thực hiện toàn bộ quy tắc Config Data về profile, import hoặc activation.

Phép thử này chứng minh payload đại diện được parse, binding và validation đúng trong context đã dựng. Nó chưa chứng minh:

- ConfigMap thực sự tồn tại trong namespace.
- Ứng dụng chọn đúng tên ConfigMap và key nội dung.
- ServiceAccount được cấp quyền cần thiết.
- Spring Cloud Kubernetes đã nạp nguồn đó lúc khởi động.
- File mount hoặc một thay đổi cấu hình đã được quan sát ở runtime.

Khi chuyển từ ví dụ sang dự án, nên lấy payload từ đầu ra render hoặc fixture đại diện được quản lý cùng nguồn triển khai. Nếu sao chép một bản cấu hình “đẹp” vào test nhưng manifest phát hành dùng bản khác, test vẫn xanh trong khi release có thể hỏng.

## 6. Kiểm thử tên biến môi trường và thứ tự ưu tiên

### 6.1. Mô phỏng đúng loại property source

Với prefix trong ví dụ, tên biến môi trường dạng canonical tương ứng là:

| Thuộc tính | Tên biến môi trường |
| --- | --- |
| `catalog.client.service-id` | `CATALOG_CLIENT_SERVICEID` |
| `catalog.client.connect-timeout` | `CATALOG_CLIENT_CONNECTTIMEOUT` |
| `catalog.client.max-in-flight` | `CATALOG_CLIENT_MAXINFLIGHT` |
| `catalog.client.retry.max-attempts` | `CATALOG_CLIENT_RETRY_MAXATTEMPTS` |

Quy tắc canonical là đổi dấu chấm thành gạch dưới, bỏ dấu gạch ngang và chuyển thành chữ hoa. Không suy đơn giản rằng mỗi dấu gạch ngang trong khóa đều trở thành một gạch dưới.

Để kiểm tra đường ánh xạ biến môi trường, dùng `SystemEnvironmentPropertySource` với tên được nhận diện phù hợp. Một `MapPropertySource` bất kỳ chứa khóa chữ hoa không tự đại diện đầy đủ cho môi trường hệ điều hành.

Thêm import vào lớp test:

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.SystemEnvironmentPropertySource;
~~~

Thêm phép thử:

~~~java
@Test
void environmentFixtureOverridesLowerPriorityFixture() {
    Map<String, Object> configMapValues = Map.of(
        "catalog.client.service-id", "from-configmap",
        "catalog.client.connect-timeout", "2s",
        "catalog.client.max-in-flight", "20"
    );

    Map<String, Object> environmentValues = Map.of(
        "CATALOG_CLIENT_SERVICEID", "from-env",
        "CATALOG_CLIENT_CONNECTTIMEOUT", "750ms",
        "CATALOG_CLIENT_MAXINFLIGHT", "8"
    );

    runner
        .withInitializer(context -> {
            var sources =
                context.getEnvironment().getPropertySources();

            sources.addLast(new MapPropertySource(
                "configMapFixture", configMapValues));

            sources.addFirst(new SystemEnvironmentPropertySource(
                "fixture-systemEnvironment", environmentValues));
        })
        .run(context -> {
            assertThat(context).hasNotFailed();

            var properties =
                context.getBean(CatalogClientProperties.class);

            assertThat(properties.serviceId()).isEqualTo("from-env");
            assertThat(properties.connectTimeout())
                .isEqualTo(Duration.ofMillis(750));
            assertThat(properties.maxInFlight()).isEqualTo(8);
        });
}
~~~

Tên nguồn kết thúc bằng `-systemEnvironment` phù hợp với cơ chế nhận diện của Spring Boot. Ví dụ vừa kiểm tra tên biến môi trường, vừa kiểm tra kết quả binding khi source đó được đặt trước source thấp hơn.

### 6.2. Hiểu giới hạn của thứ tự do test tự dựng

Trong phương thức trên, chính test gọi `addFirst` và `addLast`. Kết quả chứng minh binder tôn trọng thứ tự đã dựng; nó không tự chứng minh Spring Cloud Kubernetes chèn property source vào đúng vị trí trong ứng dụng thật.

Nếu cần kiểm tra đường Config Data, profile hoặc `spring.config.import`, dùng một test riêng nạp cấu hình theo cơ chế đó. [ConfigDataApplicationContextInitializer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/ConfigDataApplicationContextInitializer.html) là một công cụ hỗ trợ nạp Config Data trong context test.

Khi mở rộng test theo hướng này:

1. Chỉ định nguồn fixture và profile một cách tường minh.
2. Không vô tình nạp cấu hình production từ classpath hoặc thư mục làm việc.
3. Chọn rõ có thực sự nạp `kubernetes:` hay đang thay nguồn đó bằng dữ liệu test.
4. Nếu nạp qua Kubernetes API, chuẩn bị API thử nghiệm và danh tính tương ứng thay vì dựa vào kubeconfig cá nhân.
5. Kiểm tra giá trị kết quả của bean, không chỉ kiểm tra một giá trị có trong `Environment`.

Thứ tự nguồn của Spring Cloud Kubernetes phụ thuộc đường tích hợp và phiên bản. Không mặc định “Secret luôn thắng ConfigMap”, hoặc mọi nguồn remote đều thắng biến môi trường. Xem [Spring Cloud Kubernetes — Property source precedence](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html#_property_source_precedence) cho cơ chế đang dùng.

Một lỗi thường gặp là đặt giá trị hợp lệ bằng `withPropertyValues` cho mọi khóa rồi mong test phát hiện ConfigMap thật có khóa sai. Thuộc tính test có thể làm thay đổi giá trị hiệu lực. Chỉ cấp bằng test những đầu vào mà kịch bản thực sự muốn mô phỏng.

## 7. Thiết kế validation theo dữ liệu nghiệp vụ

### 7.1. Phân biệt thiếu, rỗng và sai định dạng

Ba tình huống sau cần kỳ vọng rõ:

~~~text
Không có catalog.client.service-id
catalog.client.service-id=
catalog.client.service-id=   
~~~

Với `@NotBlank` trong ví dụ, cả ba đều không được chấp nhận. Với một thuộc tính khác, kết quả còn phụ thuộc kiểu Java, converter, mặc định và constraint.

Một `int` có thể mang giá trị `0` nếu không có thiết kế mặc định phù hợp; một `Integer` có thể mang `null`. Vì vậy, chọn kiểu dữ liệu và constraint theo hợp đồng, không suy rằng “không có khóa” luôn tương đương “giá trị không hợp lệ”.

Với `Duration`, kiểm tra ít nhất:

- Đơn vị dự định sử dụng, chẳng hạn `750ms` hoặc `2s`.
- Giá trị ở hai biên.
- Giá trị bên ngoài biên.
- Chuỗi không chuyển kiểu được.
- Hành vi khi khóa vắng hoặc rỗng nếu người vận hành có thể tạo tình huống đó.

Nếu hệ thống chấp nhận số không kèm đơn vị, cần ghi và test rõ đơn vị mặc định hoặc dùng `@DurationUnit` theo thiết kế. Tránh để người vận hành và mã nguồn hiểu cùng một con số theo hai đơn vị khác nhau.

### 7.2. Kiểm tra quan hệ nhiều trường

Constraint đơn lẻ `@Min(1)` không thể diễn đạt đầy đủ “nếu bật retry thì cần ít nhất hai lần gọi”. Test có thể có các trường hợp:

| `enabled` | `max-attempts` | Kết quả theo hợp đồng |
| --- | --- | --- |
| `false` | `1` | Hợp lệ |
| `true` | `1` | Không hợp lệ |
| `true` | `2` | Hợp lệ |
| `true` | `6` | Không hợp lệ |

Trong mô hình lớn hơn, có thể viết constraint ở cấp class và `ConstraintValidator` riêng để đưa lỗi về vị trí phù hợp. Khi đó nên có test cục bộ cho quy tắc phức tạp và một số test context để xác nhận quy tắc thực sự tham gia pipeline cấu hình.

Không chỉ test hàm kiểm tra quy tắc rồi bỏ qua đường khởi tạo bean. Một hàm đúng nhưng chưa được framework gọi vẫn không bảo vệ ứng dụng lúc khởi động.

### 7.3. Dùng chế độ khóa nghiêm ngặt có chủ đích

Khóa gõ nhầm có thể để ứng dụng chạy với giá trị mặc định không mong muốn:

~~~properties
catalog.client.connect-timeot=750ms
~~~

Test khóa dư trong ví dụ bắt trường hợp này vì prefix được cấu hình nghiêm ngặt. Nếu dự án cho phép bỏ qua khóa chưa biết để giữ tương thích, thay đổi kỳ vọng test và ghi rõ lựa chọn đó; đừng để test và hợp đồng vận hành mâu thuẫn nhau.

Với list hoặc map cấu hình phức tạp, bổ sung phép thử cho định dạng index, khóa có dấu chấm và hành vi ghi đè giữa các nguồn. Chỉ cần thêm những trường hợp mà mô hình ứng dụng thực sự hỗ trợ, thay vì kiểm thử lại toàn bộ khả năng của framework.

## 8. Áp dụng với Secret mà không đưa bí mật vào kết quả test

Binding của dữ liệu lấy từ Secret vẫn cần kiểm tra kiểu, tên khóa và ràng buộc. Tuy nhiên, nơi lưu dữ liệu là Secret không làm giá trị tự được che trong mọi assertion, exception hoặc log.

Nguyên tắc cho fixture:

- Chỉ dùng giá trị giả dành cho test, không sao chép token hoặc mật khẩu thật.
- Kiểm tra lỗi bằng loại exception, mã constraint và đường dẫn thuộc tính khi có thể.
- Không in toàn bộ property source hoặc bean chứa credential để chẩn đoán.
- Xem cả cách assertion framework hiển thị giá trị thất bại.

Record tự sinh `toString()` theo các component. Mẫu record trong bài chỉ chứa dữ liệu không nhạy cảm. Nếu bổ sung credential vào record hoặc JavaBean, thiết kế cách che dữ liệu phù hợp; chỉ sửa `toString()` cũng chưa loại bỏ mọi khả năng lộ rejected value trong báo lỗi binding.

Khi Secret dùng `data`, Kubernetes manifest biểu diễn dữ liệu bằng base64. Đó là lớp biểu diễn của tài nguyên Kubernetes. Test binder sau khi nguồn đã nạp phải nhận giá trị ứng dụng cần dùng, không tùy tiện cấp chuỗi base64 rồi mong binder tự giải mã mọi trường `String`.

Các tình huống nên tách riêng:

| Tình huống | Cần kiểm chứng |
| --- | --- |
| Secret thiếu khóa bắt buộc | Hợp đồng cấu hình từ chối dữ liệu thiếu |
| Sai tên thuộc tính sau bước ánh xạ | Bean nhận đúng khóa hoặc báo thiếu rõ ràng |
| Người dùng/ServiceAccount không có quyền | Đường nạp API báo lỗi đúng chính sách |
| Credential đúng định dạng nhưng bị hệ thống đích từ chối | Test tích hợp với hệ thống đích hoặc bản thay thế phù hợp |

Validation cục bộ không nên thử xác thực với hệ thống đích. Điều đó sẽ làm lẫn lỗi dữ liệu cấu hình với lỗi mạng hoặc chính sách của bên ngoài.

## 9. Khởi động hợp lệ chưa bảo đảm refresh an toàn

Các test với `ApplicationContextRunner` ở trên tạo context mới cho mỗi kịch bản. Chúng kiểm tra binding và validation khi tạo bean. Chúng chưa mô phỏng một context đang phục vụ yêu cầu rồi nhận cấu hình mới.

Với Configuration Watcher, cần bổ sung test tích hợp cho đường cập nhật:

~~~text
Phiên bản cấu hình A hợp lệ
    -> ứng dụng đang dùng A
    -> nguồn thay đổi sang B
    -> watcher phát hiện và thông báo
    -> cơ chế refresh/rebind của ứng dụng xử lý
    -> quan sát cấu hình và hành vi thực tế của từng instance
~~~

Các câu hỏi phải trả lời cho cả B hợp lệ và B không hợp lệ:

1. Sự kiện thay đổi có đến đúng ứng dụng không?
2. Bean hoặc thành phần nào có thể được cập nhật theo cơ chế đang dùng?
3. Validation có được thực hiện trên đường cập nhật đó không?
4. Nếu cập nhật thất bại, ứng dụng tiếp tục dùng A, báo lỗi hay cần khởi động lại?
5. Có instance nào đã cập nhật trong khi instance khác còn giữ phiên bản cũ?
6. HTTP client, pool hoặc cache sử dụng cấu hình có thay đổi theo hay không?

Không mặc định record constructor-bound trong bài có thể được sửa tại chỗ khi refresh. Cơ chế cập nhật phải phù hợp với tính bất biến, scope và cách tạo thành phần sử dụng cấu hình.

Cũng không coi việc Bean Validation báo lỗi là bằng chứng hệ thống tự rollback cấu hình theo một giao dịch. Nếu cần cam kết giữ bản hợp lệ gần nhất, phải thiết kế cơ chế đó và kiểm thử trạng thái sau khi từ chối cập nhật.

Cơ chế thông báo và làm mới của watcher được mô tả trong [Spring Cloud Kubernetes — Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html). Chỉ đưa watcher vào bài thử khi ứng dụng có yêu cầu cập nhật động; ứng dụng nạp cấu hình lúc khởi động có thể dùng rollout với cấu hình được quản lý phiên bản.

## 10. Nối test cấu hình với DiscoveryClient, LoadBalancer và sức khỏe Pod

Một thuộc tính `service-id=catalog` vượt qua `@NotBlank` chỉ chứng minh nó có dữ liệu. Muốn chứng minh DiscoveryClient tìm được dịch vụ cần test đúng namespace, nguồn discovery và quyền truy cập.

Tương tự:

| Kết quả test binding | Việc cần kiểm tra tiếp nếu ứng dụng sử dụng |
| --- | --- |
| Service ID hợp lệ | DiscoveryClient tìm đúng tập instance |
| Timeout là `Duration` đúng | HTTP client thực sự nhận và dùng timeout đó |
| Số lần thử nằm trong khoảng | Cơ chế retry của đường gọi thực thi đúng chính sách |
| Chọn chế độ load balancing đúng kiểu | Client sử dụng đúng đường gọi và backend mong đợi |
| Bean khởi tạo thành công | Readiness và phép thử nghiệp vụ phản ánh đúng khả năng phục vụ |
| Cấu hình mới bind thành công | Từng thành phần sử dụng và từng replica đã áp dụng phiên bản nào |

Không dùng health `UP` làm thay thế assertion của bean cấu hình. Ngược lại, cũng không suy rằng binding thành công là đủ để Pod Ready hoặc mọi downstream truy cập được.

Các lớp kiểm thử có thể được tổ chức:

- **Test hợp đồng cấu hình:** context nhỏ như bài học, chạy cho mỗi thay đổi liên quan.
- **Test thành phần:** xác nhận mã tạo client truyền đúng giá trị từ bean cấu hình.
- **Test tích hợp nguồn:** kiểm tra Config Data, Spring Cloud Kubernetes, tên nguồn và RBAC.
- **Test triển khai:** kiểm tra startup, readiness, cập nhật và lỗi trên Pod trong môi trường phù hợp.

Mỗi lớp bổ sung một loại bằng chứng. Không cần biến test hợp đồng thành một bản triển khai Kubernetes hoàn chỉnh.

## 11. Chẩn đoán khi test không cho kết quả mong đợi

| Triệu chứng | Nguyên nhân cần kiểm tra |
| --- | --- |
| Giá trị sai vẫn không làm context thất bại | Bean chưa đăng ký, thiếu `@Validated`, thiếu provider hoặc constraint chưa áp dụng đúng |
| Test mặc định thất bại vì retry là `null` | Cách tạo đối tượng lồng và `@DefaultValue` |
| Test âm vượt qua vì một lỗi không liên quan | Assertion chỉ kiểm tra `hasFailed()`, chưa kiểm tra loại lỗi |
| YAML test xanh dù payload thiếu khóa | Fixture khác đang cấp lại cùng khóa |
| Biến chữ hoa không bind đúng | Loại/tên property source và quy tắc biến môi trường |
| Test xanh trên máy cá nhân nhưng lỗi ở CI | Nguồn ngoài, profile, dependency hoặc version chưa được chốt rõ |
| Test context nhỏ vô tình gọi API server | Đã nạp thêm Config Data/import hoặc configuration ngoài phạm vi |
| Exception chứa giá trị nhạy cảm | Fixture dùng bí mật thật hoặc log/assertion in quá nhiều dữ liệu |
| Test startup xanh nhưng refresh lỗi | Hai phép thử đi qua hai vòng đời khác nhau |
| Binding đúng nhưng client không đổi hành vi | Thành phần sử dụng vẫn giữ giá trị hoặc đối tượng đã tạo từ trước |

Khi thay đổi mô hình cấu hình, sửa fixture và assertion theo hợp đồng mới. Nếu đổi `@ConfigurationProperties` record thành JavaBean hoặc thay đường refresh, kiểm tra lại những giả định về mặc định và vòng đời bean.

## 12. Bài thực hành và tiêu chí hoàn thành

Thực hiện trong một dự án thử nghiệm phù hợp với bộ phiên bản đã chọn:

1. Thêm mô hình cấu hình và đăng ký bean theo ví dụ.
2. Tạo test context nhỏ; xác nhận test dữ liệu hợp lệ và mặc định kiểm tra đúng giá trị bean.
3. Bổ sung trường hợp thiếu, trắng, sai kiểu và ngoài khoảng.
4. Kiểm tra lỗi lồng nhau, quy tắc retry và khóa gõ nhầm.
5. Parse payload YAML đại diện rồi binding bằng chính lớp cấu hình của ứng dụng.
6. Mô phỏng biến môi trường bằng property source phù hợp và kiểm tra kết quả ghi đè.
7. Ghi rõ những phần chưa được phép thử chứng minh: tải nguồn Kubernetes, RBAC, gọi downstream và refresh.
8. Nếu ứng dụng dùng cập nhật động, thiết kế thêm phép thử riêng cho cấu hình mới không hợp lệ và trạng thái còn hiệu lực sau lỗi.

Một bộ test đạt mục tiêu khi lỗi cấu hình liên quan có thể bị phát hiện từ đầu vào xác định, test chỉ rõ nhóm nguyên nhân và các assertion chứng minh được đối tượng cấu hình nhận đúng dữ liệu. Bằng chứng về nguồn Kubernetes và hành vi runtime được bổ sung ở lớp tích hợp tương ứng.
