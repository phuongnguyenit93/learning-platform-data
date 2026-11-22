# @ConfigurationProperties, binding và validation trong test

## 1. Mục tiêu: kiểm tra cấu hình như một phần của hợp đồng ứng dụng

Trong Spring Boot, một ứng dụng có thể chạy đúng logic Java nhưng khởi động sai vì thiếu cấu hình, sai kiểu dữ liệu, gõ nhầm tên property hoặc nhập giá trị vượt giới hạn. Các ví dụ quen thuộc là timeout không hợp lệ, số lần thử lại bằng 0, URL dịch vụ bị thiếu và khóa truy cập rỗng.

`@ConfigurationProperties` giúp nhóm các khóa cấu hình theo **prefix**, ánh xạ (binding) chúng thành một đối tượng Java có kiểu rõ ràng. `@Validated` phối hợp với các constraint Jakarta Bean Validation để từ chối cấu hình không đáp ứng quy tắc.

Trong test, cần trả lời ba câu hỏi riêng:

1. **Registration:** Lớp cấu hình đã được Spring đăng ký làm configuration-properties bean chưa?
2. **Binding và conversion:** Các key, dữ liệu lồng nhau, default value và định dạng như `5s` đã chuyển thành đúng kiểu Java chưa?
3. **Validation:** Nếu bắt buộc có giá trị hoặc có giới hạn nghiệp vụ, ứng dụng có **fail fast** khi cấu hình thiếu/sai hay không?

Bài này dùng Java 17, Spring Boot **3.x** (minh họa theo API 3.5), JUnit Jupiter, AssertJ và Jakarta Validation. Có hai mức test: một context nhỏ với `ApplicationContextRunner` và một test tích hợp dùng `@SpringBootTest`. Không cần khởi chạy HTTP server hay kết nối dịch vụ bên ngoài để chứng minh việc bind cấu hình.

**Phân biệt:** `@ConfigurationProperties` là cơ chế binding của Spring Boot, khác với việc truyền trực tiếp một POJO vào constructor Java. Nếu chỉ viết `new DeliveryProperties(...)`, ta chưa hề kiểm thử Spring đọc key từ `Environment` hay validate trong quá trình binding.

## 2. Cơ chế từ file cấu hình đến đối tượng Java

Một luồng thường gặp:

~~~text
application.yml / application.properties
       + biến môi trường / test properties / nguồn khác
                     |
                     v
             Spring Environment
             (PropertySources, thứ tự ưu tiên)
                     |
                     v
           ConfigurationProperties Binder
         key -> tên trường -> chuyển kiểu
                     |
                     v
     @ConfigurationProperties DeliveryProperties
                     |
                     v
       @Validated + Jakarta Bean Validation
                     |
              hợp lệ / lỗi
                |      |
                v      v
         bean sẵn dùng  context khởi động thất bại
~~~

Ví dụ khóa:

~~~properties
app.delivery.base-url=https://sandbox.example/api
app.delivery.max-attempts=3
app.delivery.timeout=5s
app.delivery.auth.api-key=test-key
~~~

Khi bind thành công, đối tượng có thể chứa:

- `baseUrl = "https://sandbox.example/api"` (String).
- `maxAttempts = 3` (int).
- `timeout = Duration.ofSeconds(5)`.
- `auth.apiKey = "test-key"`.

`test-key` ở đây là **giá trị giả dành cho kiểm thử**, tuyệt đối không dùng khóa thật trong repository hay log.

### Relaxed binding

Spring Boot hỗ trợ **relaxed binding**: khóa canonical `app.delivery.base-url` có thể bind vào thuộc tính Java `baseUrl`. Nên viết tên key trong file `.properties`/`.yml` theo **kebab-case, chữ thường**. Một số cách viết như `baseUrl` cũng có thể được binder chấp nhận tùy nguồn dữ liệu, nhưng đừng dùng sự linh hoạt đó để hợp thức hóa key cấu hình thiếu nhất quán.

Lưu ý quy tắc đặt tên của **biến môi trường hệ điều hành** khác với file properties; ví dụ muốn biểu diễn các dấu chấm/dấu gạch nối, thường dùng cách chuyển sang chữ hoa, thay dấu chấm bằng dấu gạch dưới và bỏ dấu gạch nối theo hướng dẫn chính thức. Với nested/list properties, cần tuân thủ đúng quy tắc index. Test qua `withPropertyValues` kiểm tra binding từ test property source, **chưa chứng minh** tên env var cụ thể của hệ điều hành được xử lý đúng.

### Type conversion và validation là hai bước khác nhau

- `app.delivery.timeout=5s` → chuyển được thành `Duration`.
- `app.delivery.timeout=not-a-duration` → **lỗi chuyển kiểu/bind**, trước khi có thể kiểm tra constraint trên Duration.
- `app.delivery.max-attempts=0` → chuyển kiểu số nguyên **thành công**, nhưng bị `@Min(1)` từ chối.
- `app.delivery.base-url=   ` → chuyển được thành String, nhưng bị `@NotBlank` từ chối.

Trong báo lỗi startup, các exception có thể được bọc nhiều tầng, chẳng hạn bean creation → configuration properties bind → bind validation/conversion. Test không nên so sánh nguyên văn toàn bộ stack trace hoặc thông điệp exception vốn có thể thay đổi giữa các bản Spring Boot.

## 3. Lựa chọn kiểu dữ liệu và cách đăng ký @ConfigurationProperties

Spring Boot hỗ trợ hai kiểu thiết kế phổ biến:

| Cách thiết kế | Đặc điểm | Lưu ý khi kiểm thử |
| --- | --- | --- |
| JavaBean mutable | Field, getter/setter, constructor rỗng; binder đi qua property setter | Kiểm tra field thực sự được set, setter/getter và default value |
| Immutable constructor binding / Java `record` | Giá trị được truyền qua constructor; phù hợp cấu hình bất biến | Kiểm tra registration đúng, type conversion, constructor parameter và giá trị lồng nhau |

Với **record Java 17 chỉ có constructor canonical**, Spring Boot 3.x có thể dùng constructor binding mà không cần thêm `@ConstructorBinding`. Nếu class có nhiều constructor, cần chọn constructor thích hợp theo API phiên bản đang dùng.

**Quan trọng:** các loại cấu hình sử dụng constructor binding cần được đăng ký qua `@EnableConfigurationProperties(...)` hoặc `@ConfigurationPropertiesScan`. Không đánh dấu record đó bằng `@Component` rồi mong cơ chế constructor binding xử lý nó như một bean thông thường; đây không phải cách tạo bean phù hợp với constructor binding. Trong một test giới hạn phạm vi, `@EnableConfigurationProperties` giúp xác định chính xác loại cần kiểm tra.

Ví dụ trong ứng dụng có thể dùng:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Đây là **đoạn minh họa**, cần imports tương ứng và các class khác trong một dự án Spring Boot thực tế. `@ConfigurationPropertiesScan` sẽ quét theo package của class được gắn annotation (hoặc package chỉ định), trong khi `@EnableConfigurationProperties(DeliveryProperties.class)` đăng ký riêng loại đó. **Không cần dùng cả hai cho cùng một class** trong ví dụ test phía dưới.

## 4. Một mô hình cấu hình thực tế với Jakarta Validation

Xét cấu hình cho một bộ gửi thông báo nội bộ. Hợp đồng:

| Trường | Kiểu Java | Rule |
| --- | --- | --- |
| `app.delivery.base-url` | String | Bắt buộc không được blank |
| `app.delivery.max-attempts` | int | Từ 1 đến 5 |
| `app.delivery.timeout` | Duration | Bắt buộc có giá trị |
| `app.delivery.auth.api-key` | String trong record lồng nhau | Bắt buộc không blank |
| `app.delivery.auth` | Record lồng nhau | Bắt buộc tồn tại |

**Tệp `src/main/java/com/example/testing/DeliveryProperties.java`:**

~~~java
package com.example.testing;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.delivery")
public record DeliveryProperties(
        @NotBlank String baseUrl,
        @Min(1) @Max(5) int maxAttempts,
        @NotNull Duration timeout,
        @NotNull @Valid Auth auth
) {
    public record Auth(@NotBlank String apiKey) {
    }
}
~~~

Những annotation có chức năng riêng:

- `@ConfigurationProperties("app.delivery")`: kết nối prefix trong `Environment` tới object.
- `@Validated`: yêu cầu Spring Boot kiểm tra bean cấu hình trong quá trình bind khi có validator/provider phù hợp.
- `@NotBlank`: kiểm tra String không null/rỗng/chỉ gồm whitespace.
- `@Min(1)`, `@Max(5)`: giới hạn số lần thử lại.
- `@NotNull`: kiểm tra thời gian chờ và đối tượng `Auth` phải có mặt.
- `@Valid`: **cascade validation** xuống record `Auth`, để `apiKey` không bị bỏ qua khi nested object được tạo.

Nếu chỉ có `@NotNull Auth` mà không có `@Valid`, bean có thể chứa một `Auth` với `apiKey` blank mà constraint lồng nhau không được đánh giá. Nếu chỉ có `@Valid` nhưng thiếu `@NotNull`, giá trị `Auth = null` không tự trở thành vi phạm. Khi có ràng buộc bắt buộc, nên thể hiện **cả hai**.

Giới hạn ví dụ: `@NotBlank baseUrl` chỉ kiểm tra chuỗi không trống, **không kiểm tra URL có scheme/host hợp lệ**. Muốn kiểm tra HTTPS hoặc domain, cần thêm quy tắc phù hợp (ví dụ custom constraint). `@NotNull Duration` cũng không có nghĩa duration bắt buộc dương; hãy bổ sung ràng buộc nếu yêu cầu nghiệp vụ là timeout lớn hơn 0.

## 5. Chuẩn bị dependencies cho test

Ví dụ được trình bày trong dự án Spring Boot **3.x** sử dụng Gradle Groovy DSL, Java 17+. Tệp `build.gradle` cần có Spring Boot Gradle plugin, repository, dependency management/toolchain phù hợp; **khối dưới đây chỉ là phần phụ thuộc và task liên quan**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-validation` mang Jakarta Bean Validation API và một provider hỗ trợ, phổ biến là Hibernate Validator. `spring-boot-starter-test` mang JUnit Jupiter, AssertJ và `spring-boot-test` (chứa `ApplicationContextRunner`).

Không nhầm `spring-boot-starter-test` với việc tự có tất cả provider validation cần thiết: **hãy thêm starter validation** khi dùng `@Validated` và constraint Jakarta. Chỉ import annotation `jakarta.validation.constraints.NotBlank` mà không có runtime provider phù hợp là chưa đủ để xác nhận fail-fast.

Nếu dự án đang ở Spring Boot 2.x, tên package Bean Validation, yêu cầu Java và cơ chế constructor binding có khác biệt đáng kể. Các mã ví dụ ở đây được cố ý chọn cho **Spring Boot 3.x + Java 17**, không giả định sao chép nguyên xi giữa các major version.

## 6. Ví dụ hoàn chỉnh: test binding và validation bằng ApplicationContextRunner

`ApplicationContextRunner` là tiện ích Spring Boot Test tạo một `ApplicationContext` nhỏ, áp dụng những cấu hình/giá trị chỉ định, trao context cho callback assertion rồi tự đóng sau khi hoàn tất. Nó đặc biệt phù hợp khi muốn biết **cấu hình có bind được không, thiếu property thì context fail hay không** mà không mở cả ứng dụng.

Ta đăng ký chính xác `DeliveryProperties` với `@EnableConfigurationProperties` rồi cung cấp dữ liệu bằng `withPropertyValues`. Mỗi lời gọi `run(...)` có context riêng và không sửa `System.setProperty(...)` toàn cục.

**Tệp `src/test/java/com/example/testing/DeliveryPropertiesBindingTest.java`:**

~~~java
package com.example.testing;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesBindingTest {
    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(OnlyPropertiesConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class OnlyPropertiesConfiguration {
    }

    @Test
    void bindsAllProperties_whenConfigurationIsValid() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=5s",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasNotFailed().hasSingleBean(DeliveryProperties.class);

            DeliveryProperties props = context.getBean(DeliveryProperties.class);
            assertThat(props.baseUrl()).isEqualTo("https://sandbox.example/api");
            assertThat(props.maxAttempts()).isEqualTo(3);
            assertThat(props.timeout()).isEqualTo(Duration.ofSeconds(5));
            assertThat(props.auth().apiKey()).isEqualTo("test-key");
        });
    }

    @Test
    void bindsRelaxedNameAndDuration_whenKeyUsesCamelCase() {
        runner.withPropertyValues(
                "app.delivery.baseUrl=https://sandbox.example/api",
                "app.delivery.max-attempts=2",
                "app.delivery.timeout=1500ms",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DeliveryProperties props = context.getBean(DeliveryProperties.class);

            assertThat(props.baseUrl()).isEqualTo("https://sandbox.example/api");
            assertThat(props.timeout()).isEqualTo(Duration.ofMillis(1500));
        });
    }

    @Test
    void rejectsMissingBaseUrl_whenRequiredPropertyIsAbsent() {
        runner.withPropertyValues(
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=5s",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindValidationException.class
            )).isTrue();
        });
    }

    @Test
    void rejectsZeroAttempts_whenMinimumIsOne() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=0",
                "app.delivery.timeout=5s",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindValidationException.class
            )).isTrue();
        });
    }

    @Test
    void rejectsBlankNestedApiKey_whenCascadeValidationRuns() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=5s",
                "app.delivery.auth.api-key=   "
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindValidationException.class
            )).isTrue();
        });
    }

    @Test
    void rejectsMissingAuth_whenNestedObjectIsRequired() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=5s"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindValidationException.class
            )).isTrue();
        });
    }

    @Test
    void rejectsUnconvertibleTimeout_whenBindingFails() {
        runner.withPropertyValues(
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=3",
                "app.delivery.timeout=not-a-duration",
                "app.delivery.auth.api-key=test-key"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(hasCause(
                    context.getStartupFailure(),
                    BindException.class
            )).isTrue();
        });
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expectedType
    ) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

### Phân tích test dương

Ca `bindsAllProperties_whenConfigurationIsValid` chứng minh cả **registration + binding + conversion + điều kiện hợp lệ**:

1. `withUserConfiguration` đăng ký `OnlyPropertiesConfiguration`.
2. `@EnableConfigurationProperties` đăng ký `DeliveryProperties` để binder tạo immutable record.
3. `withPropertyValues` cung cấp dữ liệu cho riêng lượt chạy.
4. `assertThat(context).hasNotFailed()` chứng minh khởi động context nhỏ thành công.
5. `hasSingleBean` xác nhận chỉ có một bean kiểu mong đợi.
6. Các assertion trên `baseUrl`, `maxAttempts`, `Duration` và `Auth` xác nhận từng trường thực tế, không chỉ việc tồn tại bean.

Nếu chỉ assert `context != null` hoặc `context.containsBean(...)`, một bean chứa giá trị mặc định sai vẫn có thể khiến test xanh. Luôn so sánh giá trị đã bind ở các trường có ý nghĩa nghiệp vụ.

Ca `bindsRelaxedNameAndDuration_whenKeyUsesCamelCase` minh họa hai điểm có thể làm sai khi đổi cấu hình: `baseUrl` cần liên kết với component `baseUrl` của record; `1500ms` phải thành `Duration.ofMillis(1500)`, **không bị nhầm là 1.500 giây**.

### Phân tích test âm: validation khác conversion

Ba ca thiếu `baseUrl`, `maxAttempts = 0` và `auth.apiKey` blank đều cung cấp dữ liệu **có thể bind nhưng vi phạm Jakarta constraints**. Chúng kiểm tra context startup thất bại và một `BindValidationException` có mặt trong chuỗi nguyên nhân.

Ca `timeout=not-a-duration` là lỗi **chuyển kiểu**, không phải lỗi `@NotNull`. Nó kiểm tra context thất bại và chứa `org.springframework.boot.context.properties.bind.BindException`.

`hasCause` đi qua các exception lồng nhau thay vì so sánh tên hoặc thông điệp của exception ngoài cùng. Cách này có ý nghĩa vì lỗi binding thường được Spring bọc bởi `BeanCreationException` hoặc `ConfigurationPropertiesBindException`. Nếu nâng phiên bản Spring Boot, cần kiểm tra lại taxonomy exception và các assertion tương ứng.

### Điều gì thực sự được chứng minh?

Các bài test dùng `ApplicationContextRunner` chứng minh **đối tượng cấu hình nhận đúng giá trị** và **Spring không chấp nhận cấu hình thiếu/sai**. Chúng **không** chứng minh HTTP endpoint hoạt động, service bên ngoài chạy, file `application-prod.yml` đã tồn tại hay profile được bật trong toàn bộ ứng dụng. Muốn bao phủ những yêu cầu đó, thêm một test tích hợp chuyên biệt ở tầng thích hợp.

## 7. Ca kiểm thử bổ sung cho boundary, null và nested properties

Một ma trận kiểm tra giúp tránh chỉ test “happy path”:

| Nhóm | Input | Kỳ vọng |
| --- | --- | --- |
| Số lần thử tối thiểu | `max-attempts=1` | Bind thành công |
| Số lần thử tối đa | `max-attempts=5` | Bind thành công |
| Dưới min | `max-attempts=0` | Validation fail |
| Trên max | `max-attempts=6` | Validation fail |
| Không thể convert số | `max-attempts=abc` | Binding/conversion fail |
| Duration hợp lệ | `timeout=2s`, `timeout=1500ms` | Đúng `Duration` |
| Duration không hợp lệ | `timeout=hello` | Binding/conversion fail |
| Timeout thiếu | Không có `timeout` | `@NotNull` fail |
| Base URL null/blank | Không có key hoặc giá trị toàn dấu cách | `@NotBlank` fail |
| Thiếu `auth` | Không có key con | `@NotNull Auth` fail |
| Nested key blank | `auth.api-key=   ` | `@Valid` + `@NotBlank` fail |
| Cấu hình đúng | Đủ bốn key và giá trị hợp lệ | Bean tạo và bind đủ trường |

Vì bài tập sử dụng `int maxAttempts`, nếu key thiếu thì Java có thể nhận giá trị mặc định `0` trong constructor binding. `@Min(1)` từ chối `0`, nhưng **đó không phải lúc nào cũng là chứng cứ đã phát hiện thiếu key**: việc cố tình cấu hình `0` và việc không có key có thể có triệu chứng giống nhau. Nếu cần phân biệt “bắt buộc khai báo” với “có giá trị mặc định”, hãy thiết kế kiểu phù hợp (chẳng hạn `Integer` kèm `@NotNull`) hoặc xem property source trực tiếp trong test.

Đối với `@NotBlank baseUrl`, một chuỗi như `"not a URL"` vẫn không blank và được chấp nhận theo hợp đồng hiện tại. Không viết test đòi reject “URL sai định dạng” nếu trong mã chưa có constraint tương ứng.

### Tạo parameterized test không làm mất ngữ cảnh

Có thể gom các giá trị biên cho `maxAttempts` bằng `@ParameterizedTest`, nhưng cần đủ **ba property khác hợp lệ** ở mỗi invocation. Ví dụ khối test đặt trong `DeliveryPropertiesBindingTest` ở trên:

~~~java
@ParameterizedTest
@ValueSource(ints = { 1, 5 })
void acceptsBoundaryAttempts(int attempts) {
    runner.withPropertyValues(
            "app.delivery.base-url=https://sandbox.example/api",
            "app.delivery.max-attempts=" + attempts,
            "app.delivery.timeout=5s",
            "app.delivery.auth.api-key=test-key"
    ).run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context.getBean(DeliveryProperties.class).maxAttempts())
                .isEqualTo(attempts);
    });
}
~~~

Đây là **đoạn phương thức bổ sung**, cần import `org.junit.jupiter.params.ParameterizedTest` và `org.junit.jupiter.params.provider.ValueSource`. `ApplicationContextRunner` tạo context mới cho mỗi lần chạy nên dữ liệu của ca `1` và `5` không chồng lấn. Không dùng chung một biến `static` mutable để lưu số lần thử giữa các invocation.

## 8. Kiểm tra @ConfigurationProperties trong một Spring Boot test thực sự

Khi mục tiêu không chỉ là binder mà còn là tích hợp với hạ tầng Spring Boot test, có thể dùng `@SpringBootTest`. Ví dụ sau chủ động cấu hình một ứng dụng thử nghiệm nhỏ để tránh phụ thuộc vào lớp ứng dụng chính trong một dự án cụ thể.

**Tệp `src/test/java/com/example/testing/DeliveryPropertiesSpringBootTest.java`:**

~~~java
package com.example.testing;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        classes = DeliveryPropertiesSpringBootTest.TestApplication.class,
        properties = {
                "app.delivery.base-url=https://sandbox.example/api",
                "app.delivery.max-attempts=2",
                "app.delivery.timeout=2s",
                "app.delivery.auth.api-key=test-key"
        }
)
class DeliveryPropertiesSpringBootTest {

    @Autowired
    DeliveryProperties properties;

    @Test
    void configurationProperties_whenBootContextStarts_areBound() {
        assertNotNull(properties);
        assertEquals("https://sandbox.example/api", properties.baseUrl());
        assertEquals(2, properties.maxAttempts());
        assertEquals(Duration.ofSeconds(2), properties.timeout());
        assertEquals("test-key", properties.auth().apiKey());
    }

    @SpringBootConfiguration
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class TestApplication {
    }
}
~~~

`@SpringBootTest(properties=...)` đưa các test properties vào Spring Environment cho test class. `@SpringBootConfiguration` cung cấp lớp cấu hình Boot để loader khởi tạo context; `@EnableConfigurationProperties` bảo đảm record cấu hình được đăng ký. Ở ví dụ này, không bật `@EnableAutoConfiguration` hoặc dịch vụ mạng: mục đích chỉ là chứng minh **Boot test context và binding/validation**.

**Khác biệt chi phí:** `@SpringBootTest` tham gia cơ chế Spring TestContext và context cache; khi quét/ngữ cảnh ứng dụng thật càng lớn thì test thường càng nặng. `ApplicationContextRunner` gọn hơn và thường tốt cho một ma trận nhiều ca thất bại khởi động. Đừng khởi động cả ứng dụng cho từng tổ hợp giá trị chỉ để kiểm tra một constraint nếu context nhỏ đã đủ chứng minh.

## 9. @ActiveProfiles, @TestPropertySource và @DynamicPropertySource

Trong dự án thực tế, dữ liệu test không chỉ đến từ `withPropertyValues`.

| Cơ chế | Dùng cho | Điểm dễ nhầm |
| --- | --- | --- |
| `@ActiveProfiles("test")` | Kích hoạt profile test trong Spring TestContext | Tự nó không tạo file; Spring Boot sẽ xét `application-test.yml`/`application-test.properties` nếu có |
| `@TestPropertySource(properties = "...")` | Chèn property test trực tiếp vào TestContext | Không đồng nghĩa với tự động đọc YAML qua `locations` |
| `@SpringBootTest(properties = "...")` | Cung cấp property cho một Boot test class | Context với tập properties khác có thể tạo cache key khác |
| `@DynamicPropertySource` | Cấp property động, thường từ Testcontainers hoặc cổng runtime | Method thường `static`; giá trị có thể động và ưu tiên cao |
| `ApplicationContextRunner.withPropertyValues` | Tạo từng context nhỏ với cấu hình khác nhau | Không tự quét `application.yml` của ứng dụng chính |

Ví dụ profile:

~~~yaml
# src/test/resources/application-test.yml
app:
  delivery:
    base-url: https://sandbox.example/api
    max-attempts: 2
    timeout: 2s
    auth:
      api-key: test-key
~~~

Đây là **file dành cho môi trường test**, chỉ chứa credential giả. Trong test có `@SpringBootTest` với cơ chế config data của Spring Boot, dùng `@ActiveProfiles("test")` để kích hoạt profile phù hợp. Tuy nhiên nếu muốn test đúng file YAML thật, **không đồng thời override tất cả các key bằng `@SpringBootTest(properties=...)`**, bởi test sẽ chứng minh các override chứ không phải nội dung của file.

Đối với integration test có Testcontainers, `@DynamicPropertySource` có thể cung cấp JDBC URL/port do container cấp. Đừng hard-code cổng hoặc chạy `System.setProperty` ở nhiều test làm rò trạng thái cho cả JVM. Luôn chú ý thứ tự ưu tiên property sources khi có nhiều nguồn cùng định nghĩa một key.

### Property precedence: test điều gì?

Nếu `application-test.yml` ghi `max-attempts: 2` nhưng annotation test đưa `app.delivery.max-attempts=4`, giá trị bind được là giá trị từ **nguồn có ưu tiên cao hơn** trong cấu hình test đó (thông thường override trong test). Một test chỉ chạy với override sẽ **không** phát hiện file YAML cấu hình sai ở key bị ghi đè.

Nên chia rõ hai loại test:

1. **Binding theo dữ liệu chủ động:** dùng `ApplicationContextRunner` hoặc properties trên annotation để kiểm tra mapping/rule.
2. **Kiểm tra file cấu hình/profile thực tế:** nạp đúng profile, hạn chế override các key cần xác nhận và assert giá trị cuối cùng.

## 10. Giá trị mặc định, null và @DefaultValue

Một record có thể khai báo default value cho constructor-binding parameter bằng `org.springframework.boot.context.properties.bind.DefaultValue` (API Spring Boot 3.x). Ví dụ minh họa:

~~~java
@ConfigurationProperties("example.retry")
public record RetryProperties(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("2s") Duration timeout
) {
}
~~~

Đoạn này là **tệp class minh họa**, cần import `java.time.Duration`, `ConfigurationProperties` và `DefaultValue`; muốn binder tạo bean cần đăng ký loại như phần 3. Khi những key tương ứng vắng mặt, binder có thể dùng giá trị default đã khai báo.

**Phân biệt:** default ở constructor/record tạo ra giá trị trong object; điều này **không nhất thiết tạo thêm property thật trong `Environment`**. Vì thế test phải assert trên `RetryProperties` đã bind, không chỉ đọc `environment.getProperty("example.retry.max-attempts")` rồi kỳ vọng mặc định xuất hiện ở đó.

Một số quy tắc cần lựa chọn rõ:

- Dùng `@NotNull Integer attempts` nếu muốn biết thuộc tính có thật sự bị thiếu hay không.
- Dùng primitive `int` với default rõ ràng nếu muốn hệ thống có giá trị mặc định hợp lệ.
- Dùng `@NotNull @Valid Nested nested` khi nested config bắt buộc có mặt và phải kiểm tra constraint bên trong.
- Với nested constructor binding, `@DefaultValue` không có tham số đôi khi được dùng để tạo object lồng nhau ngay cả khi không có key con, rồi validation đi sâu vào nó. Đây là lựa chọn thiết kế cần thử bằng test cụ thể.

Với cấu hình bảo mật, **không log giá trị secret đầy đủ**, kể cả khi context khởi động không thành công. Hãy kiểm tra lỗi với key/constraint thay vì copy giá trị nhạy cảm vào báo cáo.

## 11. Những lỗi phổ biến và cách khắc phục

1. **Chỉ gọi constructor Java và tuyên bố đã test binding.** Test không dùng Spring Binder/Environment. **Sửa:** dùng `ApplicationContextRunner` hoặc Boot test context thực sự.
2. **Không đăng ký configuration-properties bean.** `@ConfigurationProperties` chỉ là annotation, không tự bảo đảm class được scan. **Sửa:** khai báo `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.
3. **Đánh dấu record constructor-bound bằng `@Component`.** Spring DI tạo bean theo đường khác, dễ lỗi hoặc không dùng cơ chế binder mong đợi. **Sửa:** đăng ký bằng đúng API cho configuration properties.
4. **Thiếu `spring-boot-starter-validation`.** Constraint có thể không được áp dụng vì thiếu provider hoặc cấu hình thích hợp. **Sửa:** bảo đảm Jakarta validation provider hiện diện trên classpath.
5. **Quên `@Validated` trên configuration-properties class.** Chỉ gắn `@NotBlank`/`@Min` có thể không kích hoạt validation trong quá trình binding. **Sửa:** thêm `@Validated` và test một trường hợp vi phạm.
6. **Quên `@Valid` cho object lồng nhau.** Inner constraint không được kiểm tra đầy đủ. **Sửa:** kết hợp cascade `@Valid` và `@NotNull` nếu nested object bắt buộc.
7. **Nhầm conversion failure với Bean Validation failure.** `timeout=not-a-duration` không thể đổi sang Duration; `max-attempts=0` có thể đổi sang int nhưng vi phạm `@Min`. **Sửa:** phân biệt nhóm lỗi và test đúng loại.
8. **So sánh nguyên văn thông điệp exception.** Wrapper, wording và thứ tự chi tiết lỗi có thể đổi theo phiên bản. **Sửa:** assert context fail và loại exception/cause hoặc cấu trúc violation khi ổn định.
9. **Dùng cấu hình thật trong test.** URL/secret có thể trỏ đến production hoặc bị lộ trong log. **Sửa:** mọi endpoint/secret test phải là giá trị giả, không tạo kết nối thực.
10. **Dùng `@TestPropertySource(locations="classpath:application-test.yml")` nhưng không có factory hỗ trợ YAML.** Cơ chế TestPropertySource mặc định không giống Config Data loader của Boot. **Sửa:** dùng `@ActiveProfiles("test")` với `application-test.yml` theo cơ chế Boot hoặc thêm factory có chủ đích.
11. **Override toàn bộ property khi test file profile.** Test chỉ chứng minh override, bỏ lọt YAML sai. **Sửa:** tách test dữ liệu chủ động và test file thật.
12. **Đưa mọi ca lỗi vào một `@SpringBootTest` nặng.** Startup fail làm test khó quản lý và tốn tài nguyên. **Sửa:** với ma trận binding/validation, ưu tiên `ApplicationContextRunner`.
13. **Giả định `@NotBlank` kiểm tra URL hợp lệ hoặc `@NotNull Duration` kiểm tra timeout dương.** Đây là hai hợp đồng khác nhau. **Sửa:** khai báo constraint/custom validator đúng yêu cầu và viết test âm tương ứng.
14. **Tạo phụ thuộc thời gian/hệ điều hành không kiểm soát.** Biến môi trường/secret/profile trên máy dev ảnh hưởng kết quả. **Sửa:** cô lập sources, cố định data và không thay đổi global system properties giữa các test.

## 12. Quy trình thực hành và checklist QA

Khi thêm một nhóm `@ConfigurationProperties` mới:

1. **Viết danh sách key và kiểu:** prefix, tên canonical, nested structure, loại `Duration`/`DataSize`/enum và định dạng hợp lệ.
2. **Ghi rõ rule:** bắt buộc, giá trị mặc định, giới hạn, yêu cầu bảo mật, kết quả khi sai.
3. **Chọn cách binding:** JavaBean mutable hoặc constructor/record immutable; đăng ký bằng scan hay `@EnableConfigurationProperties`.
4. **Tạo một test dương:** bind đủ giá trị và assert tất cả trường quan trọng.
5. **Tạo các test âm:** key thiếu, blank, giá trị ngoài min/max, conversion error và nested validation.
6. **Chọn công cụ:** `ApplicationContextRunner` cho ma trận nhỏ; `@SpringBootTest` khi cần chứng minh wiring/Boot TestContext thực.
7. **Kiểm tra môi trường test:** profiles, precedence, property source, không dùng secret thật.
8. **Chạy test độc lập và cả suite:** xác nhận không có state chia sẻ hoặc context bị ảnh hưởng bởi cấu hình của test khác.

Checklist trước khi kết thúc:

- [ ] `@ConfigurationProperties` dùng đúng prefix và bean đã được đăng ký.
- [ ] Tên key canonical/kebab-case tương ứng với trường Java.
- [ ] Test khẳng định kiểu được convert đúng (String, int, Duration, nested record).
- [ ] Test biên hợp lệ và không hợp lệ cho các constraint.
- [ ] `@Validated` và Jakarta provider hoạt động thật; `@Valid` cascade tới nested.
- [ ] Test lỗi binding riêng với lỗi validation khi có ý nghĩa.
- [ ] Các ca startup failure dùng context runner, không làm sập test suite.
- [ ] Không chỉ `assertNotNull` bean; đã assert đầy đủ giá trị bind quan trọng.
- [ ] Test profile/file cấu hình thực không bị override nhầm.
- [ ] Không có credential thật hoặc thay đổi global property gây rò state.
- [ ] Ví dụ và tên file/class phù hợp với Java 17, JUnit Jupiter, Spring Boot 3.x.

### Chạy bộ test

Từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.DeliveryPropertiesBindingTest"
./gradlew test --tests "com.example.testing.DeliveryPropertiesSpringBootTest"
~~~

Trên Windows, dùng `gradlew.bat` thay `./gradlew`. Hai lớp test không in `System.out.println` nên **không có stdout cố định** của mã ứng dụng. Build/test runner sẽ hiển thị trạng thái và báo cáo test theo cấu hình của dự án. Chúng cần dependency Spring Boot, AssertJ và JUnit trên classpath, vì vậy không thể chạy riêng `javac DeliveryPropertiesBindingTest.java` không cung cấp những thư viện đó.

**Ghi nhớ:** `@ConfigurationProperties` quyết định **cách đọc và chuyển cấu hình**; `@Validated` + Jakarta constraints quyết định **cấu hình nào được phép tồn tại**. Trong test, hãy chứng minh đủ ba tầng **đăng ký bean → bind/convert → validate**, rồi phân biệt rõ test dữ liệu chủ động với test profile/cấu hình được nạp thực tế.

### Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Boot — Creating Your Own Auto-configuration / ApplicationContextRunner](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.5 — BindValidationException API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/)