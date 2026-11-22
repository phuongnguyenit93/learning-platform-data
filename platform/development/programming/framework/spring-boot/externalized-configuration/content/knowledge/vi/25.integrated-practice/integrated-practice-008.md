# Viết kiểm thử cho quy tắc ghi đè, liên kết và kiểm tra hợp lệ trong Spring Boot

## 1. Mục tiêu bài thực hành

Spring Boot Externalized Configuration cho phép ứng dụng nhận cấu hình từ nhiều nguồn: `application.yml`, `application.properties`, profile-specific files, OS environment variables, Java system properties, command-line arguments và property sources thêm bằng lập trình.

Khi cùng một khóa xuất hiện ở nhiều nguồn, Spring Boot phải giải quyết **thứ tự ưu tiên**. Sau đó, Binder chuyển dữ liệu thành các kiểu Java và cơ chế validation kiểm tra ràng buộc nghiệp vụ. Cả ba bước đều có thể sai hoặc bị hiểu sai.

Một test cấu hình tốt cần trả lời được:

1. Khi file đặt `retries=1` và CLI đặt `retries=4`, kết quả hiệu lực là gì?
2. Giá trị `timeout=750ms` được bind thành `Duration` như thế nào?
3. Khi chỉ định `regions` ở profile cao hơn, hai danh sách có nối nhau không?
4. Khi cấu hình `Map<String,Integer>` nằm trong nhiều sources, key trùng và không trùng được xử lý ra sao?
5. Khi `retries=many`, hệ thống fail tại binding hay validation?
6. Khi `retries=99`, Binder chuyển kiểu thành công nhưng validator có phát hiện sai giới hạn không?
7. Khi `enabled=true` nhưng thiếu `base-url`, application context có fail-fast không?
8. Khi dùng `@DynamicPropertySource`, giá trị động có ghi đè `@TestPropertySource` không?
9. Một test dùng `ApplicationContextRunner` đã đủ để chứng minh Config Data file được nạp thực tế chưa?

Đề bài tập trung vào một **bộ kiểm thử có thể chạy lại**, thay vì chỉ giải thích khái niệm.

> Hãy phân biệt ba bước: **property resolution → type-safe binding → validation**. Kiểm tra đúng bước sẽ giúp xác định nguyên nhân khi test thất bại.

Ví dụ dưới đây hướng tới Spring Boot 3.x, Java 17+, JUnit Jupiter và AssertJ.

## 2. Chọn cấp kiểm thử theo mục tiêu

| Mục tiêu | Công cụ | Điều xác minh |
| --- | --- | --- |
| Nguồn cấu hình nào thắng? | `StandardEnvironment`, `MapPropertySource` | Thứ tự ưu tiên khi property trùng tên |
| Binder chuyển `String` thành `Duration`, `int`, `URI`? | `ApplicationContextRunner` | Binding từ test properties vào bean |
| Bean có validate và fail startup? | `ApplicationContextRunner` | Khởi tạo context và lỗi binding/validation |
| `application-it.yml` ghi đè file base? | `@SpringBootTest` + `@ActiveProfiles` | Config Data được nạp theo profile |
| CLI có thắng default app không? | `SpringApplication` chạy không có web server | Startup source precedence |
| Port từ Testcontainers có hiệu lực? | `@DynamicPropertySource` | Dynamic property sources và bean wiring |
| File mount từ Docker/Kubernetes có được tìm? | Deployment smoke test | Runtime location, working directory và permissions |

Đừng bắt mọi trường hợp dùng full `@SpringBootTest`: thời gian khởi động dài và lỗi bean khác có thể che mất câu hỏi cấu hình chính. Đồng thời, đừng dùng `withPropertyValues(...)` rồi kết luận một file YAML ngoài JAR đã được Config Data loader tìm thấy.

## 3. Hợp đồng cấu hình dùng trong bài

Giả sử một ứng dụng kết nối tới dịch vụ `lab.gateway`:

~~~yaml
lab:
  gateway:
    enabled: true
    base-url: https://gateway.example.test
    timeout: 750ms
    retries: 3
    regions:
      - apac
      - eu
    limits:
      catalog: 2
      inventory: 1
~~~

Bảng quy tắc:

| Khóa | Kiểu | Default | Ràng buộc |
| --- | --- | --- | --- |
| `lab.gateway.enabled` | Boolean | `false` | Chỉ bật theo lựa chọn triển khai |
| `lab.gateway.base-url` | `URI` | Không có | Khi bật, phải là URI HTTPS tuyệt đối có host |
| `lab.gateway.timeout` | `Duration` | `2s` | Dương và không vượt 10 giây |
| `lab.gateway.retries` | `int` | `2` | Từ 0 đến 5 |
| `lab.gateway.regions` | `List<String>` | Không bắt buộc | Giữ thứ tự, bị thay cả List khi nguồn cao hơn khai báo |
| `lab.gateway.limits` | `Map<String,Integer>` | Không bắt buộc | Key không trùng có thể kết hợp, key trùng lấy nguồn cao |

Contract này phân biệt **missing property**, **invalid type** và **invalid business rule**. Đây là ba trường hợp cần những assertion khác nhau.

## 4. Dependencies và cấu trúc source

Một project Maven dùng Spring Boot dependency management:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
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

`spring-boot-starter-validation` mang Bean Validation implementation cần để xử lý Jakarta validation annotations. `spring-boot-starter-test` chứa JUnit Jupiter, AssertJ, Spring Test và utility test của Boot.

Cấu trúc gợi ý:

~~~text
src/
├── main/java/com/example/gateway/
│   └── GatewayProperties.java
└── test/
    ├── java/com/example/gateway/
    │   ├── GatewayPropertiesTest.java
    │   ├── PropertyPriorityTest.java
    │   ├── CommandLinePriorityTest.java
    │   ├── ProfileConfigDataTest.java
    │   └── DynamicValueTest.java
    └── resources/
        ├── application.yml
        └── application-it.yml
~~~

Các test cần Testcontainers nên ở nhóm integration riêng hoặc chỉ chạy tại runner có Docker-compatible runtime.

## 5. Tạo model type-safe với validation

~~~java
package com.example.gateway;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "lab.gateway")
public record GatewayProperties(
        @DefaultValue("false") boolean enabled,
        URI baseUrl,
        @NotNull @DefaultValue("2s") Duration timeout,
        @Min(0) @Max(5) @DefaultValue("2") int retries,
        List<String> regions,
        Map<String, Integer> limits) {

    @AssertTrue(message = "base-url must be an absolute HTTPS URI when enabled")
    public boolean isBaseUrlValidWhenEnabled() {
        if (!enabled) {
            return true;
        }

        return baseUrl != null
                && baseUrl.isAbsolute()
                && "https".equalsIgnoreCase(baseUrl.getScheme())
                && baseUrl.getHost() != null;
    }

    @AssertTrue(message = "timeout must be positive and at most 10s")
    public boolean isTimeoutWithinRange() {
        return timeout != null
                && !timeout.isZero()
                && !timeout.isNegative()
                && timeout.compareTo(Duration.ofSeconds(10)) <= 0;
    }
}
~~~

Giải thích:

- `@ConfigurationProperties` bind các key dưới prefix `lab.gateway`.
- `@DefaultValue` cung cấp fallback khi một key thiếu.
- `@Min/@Max` chặn retry ngoài khoảng cho phép.
- `@AssertTrue` trên JavaBeans-style boolean getters kiểm tra những quan hệ nghiệp vụ.
- `@Validated` kết hợp Jakarta Bean Validation để phát hiện cấu hình sai trong lifecycle binding bean.
- `List<String>` và `Map<String,Integer>` giữ type của phần tử và giá trị map.

`baseUrl` có thể thiếu khi `enabled=false`. Đặt `@NotNull` vô điều kiện ở đó sẽ trái contract. URI có scheme `http` vẫn là URI parse được, vì vậy business rule cần kiểm tra HTTPS riêng.

## 6. Test nền bằng `ApplicationContextRunner`

Tạo một cấu hình test không cần full application:

~~~java
package com.example.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestConfiguration {
    }

    @Test
    void bindsDefaults() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                    context.getBean(GatewayProperties.class);

            assertThat(p.enabled()).isFalse();
            assertThat(p.timeout())
                    .isEqualTo(java.time.Duration.ofSeconds(2));
            assertThat(p.retries()).isEqualTo(2);
        });
    }
}
~~~

`ApplicationContextRunner` tạo context nhỏ để test bean registration, binding và validation. Nó có thể cho phép kiểm tra context startup failure mà không cần server HTTP hoặc database.

### 6.1. Default trong bean không phải property source

Một test riêng:

~~~java
@Test
void defaultInRecordDoesNotCreateEnvironmentProperty() {
    runner.run(context -> {
        GatewayProperties p =
                context.getBean(GatewayProperties.class);

        assertThat(p.timeout())
                .isEqualTo(java.time.Duration.ofSeconds(2));

        assertThat(context.getEnvironment()
                .getProperty("lab.gateway.timeout")).isNull();
    });
}
~~~

`@DefaultValue("2s")` nằm trong đường binding sang record, không tự tạo key `lab.gateway.timeout=2s` trong `Environment`. Điều này quan trọng nếu thành phần khác đọc Environment trực tiếp hoặc dùng `@ConditionalOnProperty`.

Đừng sử dụng duy nhất `Environment.getProperty` làm bằng chứng một `@ConfigurationProperties` object đã được bind đúng.

## 7. Test rule ghi đè với `MapPropertySource`

`StandardEnvironment` giúp tạo các nguồn có priority rõ ràng mà không cần can thiệp OS environment thật.

~~~java
package com.example.gateway;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class PropertyPriorityTest {

    @Test
    void lastAddFirstHasHighestPriority() {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
                new MapPropertySource("packaged",
                    Map.of("lab.gateway.retries", "1")));

        env.getPropertySources().addFirst(
                new MapPropertySource("deployment",
                    Map.of("lab.gateway.retries", "3")));

        env.getPropertySources().addFirst(
                new MapPropertySource("commandLine",
                    Map.of("lab.gateway.retries", "4")));

        assertThat(env.getProperty(
                "lab.gateway.retries", Integer.class)).isEqualTo(4);
    }

    @Test
    void lowerPrioritySourceStillSuppliesMissingKey() {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
                new MapPropertySource("defaults", Map.of(
                    "lab.gateway.retries", "1",
                    "lab.gateway.timeout", "2s")));

        env.getPropertySources().addFirst(
                new MapPropertySource("override", Map.of(
                    "lab.gateway.retries", "5")));

        assertThat(env.getProperty(
                "lab.gateway.retries", Integer.class)).isEqualTo(5);

        assertThat(env.getProperty(
                "lab.gateway.timeout")).isEqualTo("2s");
    }
}
~~~

`addFirst` đặt nguồn ở đầu danh sách priority. Với một key trùng, nguồn xuất hiện trước thắng; với key không trùng, Spring tiếp tục tìm ở các nguồn thấp hơn.

### 7.1. Kiểm tra `addLast` dùng làm fallback

~~~java
@Test
void fallbackSourceDoesNotOverrideDeployment() {
    StandardEnvironment env = new StandardEnvironment();

    env.getPropertySources().addFirst(
        new MapPropertySource("deployment",
            Map.of("lab.gateway.retries", "4")));

    env.getPropertySources().addLast(
        new MapPropertySource("fallback",
            Map.of("lab.gateway.retries", "1")));

    assertThat(env.getProperty(
        "lab.gateway.retries", Integer.class)).isEqualTo(4);
}
~~~

Đây là test **quy tắc của Environment với các nguồn được mô phỏng**. Nó chưa kiểm tra `SpringApplication` thực sự xử lý OS env, CLI và Config Data theo thứ tự nào. Cấp tiếp theo sẽ giải quyết điều đó.

## 8. Test command-line arguments với `SpringApplication` thật

Không cần gọi `System.setProperty(...)` để kiểm tra precedence. Có thể chạy một `SpringApplication` tối giản:

~~~java
package com.example.gateway;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import static org.assertj.core.api.Assertions.assertThat;

class CommandLinePriorityTest {

    @SpringBootConfiguration
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestApplication {
    }

    @Test
    void commandLineOverridesDefaultProperties() {
        SpringApplication app =
                new SpringApplication(TestApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setDefaultProperties(Map.of(
            "lab.gateway.retries", "1",
            "lab.gateway.timeout", "3s"));

        try (ConfigurableApplicationContext ctx =
                app.run("--lab.gateway.retries=4")) {

            GatewayProperties p =
                    ctx.getBean(GatewayProperties.class);

            assertThat(p.retries()).isEqualTo(4);
            assertThat(p.timeout())
                    .isEqualTo(java.time.Duration.ofSeconds(3));
        }
    }
}
~~~

Đây là bài test gần với startup thật: Spring Boot tạo Environment và sử dụng command-line property source. Với cấu hình mặc định, CLI có ưu tiên cao hơn `SpringApplication.setDefaultProperties(...)`.

Nếu project tắt nguồn CLI bằng `setAddCommandLineProperties(false)`, test phải theo contract khác. Đừng bỏ qua cấu hình `SpringApplication` riêng của dự án.

### 8.1. Vì sao hạn chế `System.setProperty`?

`System.setProperty` thay đổi trạng thái toàn JVM, gây test leak khi thiếu cleanup hoặc suite chạy song song. Đặc biệt không an toàn nếu hai test classes dùng cùng key nhưng mong đợi hai giá trị khác nhau.

Khi chỉ cần một nguồn trong test context, dùng `withPropertyValues` hoặc test source cụ thể. Khi cần chứng minh CLI thực, truyền args vào `SpringApplication.run`.

## 9. Test binding giá trị đơn

Tiếp tục class `GatewayPropertiesTest` và `runner` ở phần 6.

### 9.1. Duration

~~~java
@Test
void convertsDurationToTypedProperty() {
    runner.withPropertyValues(
            "lab.gateway.timeout=750ms")
        .run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                    context.getBean(GatewayProperties.class);

            assertThat(p.timeout())
                    .isEqualTo(java.time.Duration.ofMillis(750));
        });
}
~~~

Spring Boot có syntax thời gian như `500ms`, `2s`, `1m`. Một `Duration` không có suffix thường hiểu số theo **mili giây** trừ khi `@DurationUnit` quy định khác. Do đó test nên dùng suffix tường minh để tránh lỗi đơn vị.

### 9.2. URI

~~~java
@Test
void bindsHttpsUri() {
    runner.withPropertyValues(
            "lab.gateway.enabled=true",
            "lab.gateway.base-url=https://gateway.example.test")
        .run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                    context.getBean(GatewayProperties.class);

            assertThat(p.baseUrl().getScheme())
                    .isEqualTo("https");
            assertThat(p.baseUrl().getHost())
                    .isEqualTo("gateway.example.test");
        });
}
~~~

URI parse thành công không chứng minh service reachable. Ở đây test type conversion và rule HTTPS, không phải connectivity của endpoint ngoài.

### 9.3. Integer và default

~~~java
@Test
void overridesDefaultRetryValue() {
    runner.withPropertyValues(
            "lab.gateway.retries=5")
        .run(context -> {
            assertThat(context).hasNotFailed();

            assertThat(context.getBean(GatewayProperties.class)
                    .retries()).isEqualTo(5);
        });
}
~~~

`5` nằm ở ranh giới trên hợp lệ. Test ranh giới có ý nghĩa hơn chỉ dùng một giá trị ở giữa miền hợp lệ.

## 10. Test List và Map có kiểu generic

~~~java
@Test
void bindsIndexedListAndKeyedMap() {
    runner.withPropertyValues(
            "lab.gateway.regions[0]=apac",
            "lab.gateway.regions[1]=eu",
            "lab.gateway.limits.catalog=2",
            "lab.gateway.limits.inventory=4")
        .run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                context.getBean(GatewayProperties.class);

            assertThat(p.regions())
                    .containsExactly("apac", "eu");

            assertThat(p.limits())
                    .containsEntry("catalog", 2)
                    .containsEntry("inventory", 4);
        });
}
~~~

`List<String>` giữ thứ tự `apac` rồi `eu`. `Map<String,Integer>` có value kiểu `Integer` chứ không chỉ là các String trong cấu hình.

Không nên dùng `List.class` hoặc `Map.class` raw rồi cast kết quả, vì việc đó làm mất generic type information của target.

### 10.1. Khi giá trị Map không convert được

~~~java
@Test
void rejectsNonNumericMapValue() {
    runner.withPropertyValues(
            "lab.gateway.limits.catalog=many")
        .run(context -> assertThat(context).hasFailed());
}
~~~

Đây là lỗi **type conversion** của `Map<String,Integer>`. Nó độc lập với validation giới hạn `retries`.

## 11. Test sai kiểu, sai giá trị và thiếu key riêng biệt

Ba trường hợp:

~~~properties
# Missing retries
~~~

~~~properties
lab.gateway.retries=many
~~~

~~~properties
lab.gateway.retries=99
~~~

Kỳ vọng:

- Missing: dùng `@DefaultValue("2")`.
- `many`: fail tại binder/conversion.
- `99`: chuyển thành int được nhưng fail `@Max(5)`.

Đưa vào test:

~~~java
@Test
void missingRetriesUsesDefault() {
    runner.run(ctx -> {
        assertThat(ctx.getBean(GatewayProperties.class)
                .retries()).isEqualTo(2);
    });
}

@Test
void nonNumericRetriesFailBinding() {
    runner.withPropertyValues("lab.gateway.retries=many")
        .run(ctx -> assertThat(ctx).hasFailed());
}

@Test
void retriesAboveMaximumFailValidation() {
    runner.withPropertyValues("lab.gateway.retries=99")
        .run(ctx -> assertThat(ctx).hasFailed());
}
~~~

Nếu bài test thứ ba không fail, có thể validation provider không có trên test runtime classpath, `@Validated` bị bỏ sót, hoặc bean không đi qua đường binding mà bạn nghĩ.

## 12. Test validation với JUnit parameterized tests

JUnit Jupiter cho phép kiểm tra nhiều boundary values gọn hơn:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@ValueSource(strings = {"-1", "6", "100"})
void rejectsRetriesOutsideAllowedRange(String retries) {
    runner.withPropertyValues(
            "lab.gateway.retries=" + retries)
        .run(ctx -> assertThat(ctx).hasFailed());
}

@ParameterizedTest
@ValueSource(strings = {"0", "1", "5"})
void acceptsRetriesInsideAllowedRange(String retries) {
    runner.withPropertyValues(
            "lab.gateway.retries=" + retries)
        .run(ctx -> assertThat(ctx).hasNotFailed());
}
~~~

Tương tự với timeout:

~~~java
@ParameterizedTest
@ValueSource(strings = {"0s", "-1s", "11s"})
void rejectsInvalidTimeout(String timeout) {
    runner.withPropertyValues(
            "lab.gateway.timeout=" + timeout)
        .run(ctx -> assertThat(ctx).hasFailed());
}

@ParameterizedTest
@ValueSource(strings = {"1ms", "2s", "10s"})
void acceptsValidTimeout(String timeout) {
    runner.withPropertyValues(
            "lab.gateway.timeout=" + timeout)
        .run(ctx -> assertThat(ctx).hasNotFailed());
}
~~~

Các giá trị biên `0`, `5`, `10s` cần được test riêng vì lỗi dấu so sánh `<` / `<=` dễ không được phát hiện bởi ví dụ ở giữa miền giá trị.

## 13. Test validation liên trường

Hợp đồng:

~~~text
enabled=false:
  base-url có thể thiếu

enabled=true:
  base-url phải là absolute HTTPS URI với host
~~~

Tests:

~~~java
@Test
void disabledGatewayDoesNotRequireUrl() {
    runner.withPropertyValues("lab.gateway.enabled=false")
        .run(ctx -> assertThat(ctx).hasNotFailed());
}

@Test
void enabledGatewayRequiresUrl() {
    runner.withPropertyValues("lab.gateway.enabled=true")
        .run(ctx -> assertThat(ctx).hasFailed());
}

@Test
void enabledGatewayRejectsHttp() {
    runner.withPropertyValues(
            "lab.gateway.enabled=true",
            "lab.gateway.base-url=http://gateway.example.test")
        .run(ctx -> assertThat(ctx).hasFailed());
}

@Test
void enabledGatewayAcceptsHttps() {
    runner.withPropertyValues(
            "lab.gateway.enabled=true",
            "lab.gateway.base-url=https://gateway.example.test")
        .run(ctx -> assertThat(ctx).hasNotFailed());
}
~~~

`@NotNull` trên `baseUrl` sẽ không biểu diễn đúng rule có điều kiện. Trong model mẫu, `@AssertTrue` phụ trách kiểm tra. Với logic phức tạp hơn có thể dùng class-level Jakarta constraint hoặc Spring `Validator`.

Không nên làm một test “fail” bằng cách bỏ validation dependency rồi để một bean khác vô tình lỗi startup. Cô lập config model giúp assertion phản ánh đúng nguyên nhân.

## 14. Test rule ghi đè từ Config Data profile

`ApplicationContextRunner.withPropertyValues(...)` không mặc nhiên nạp toàn bộ `application-{profile}.yml` như một `SpringApplication` thông thường. Muốn kiểm tra behavior của Config Data thật, tạo file trong `src/test/resources` và dùng `@SpringBootTest`.

`src/test/resources/application.yml`:

~~~yaml
lab:
  gateway:
    enabled: false
    timeout: 2s
    retries: 1
    regions:
      - apac
      - eu
    limits:
      catalog: 2
      inventory: 1
~~~

`src/test/resources/application-it.yml`:

~~~yaml
lab:
  gateway:
    retries: 3
    regions:
      - us
    limits:
      catalog: 5
      billing: 3
~~~

Test:

~~~java
package com.example.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ProfileConfigDataTest.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("it")
class ProfileConfigDataTest {

    @SpringBootConfiguration
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestApp {
    }

    @Autowired
    GatewayProperties properties;

    @Test
    void profileOverridesScalarsAndCollections() {
        assertThat(properties.retries()).isEqualTo(3);
        assertThat(properties.timeout())
                .isEqualTo(java.time.Duration.ofSeconds(2));

        assertThat(properties.regions())
                .containsExactly("us");

        assertThat(properties.limits())
                .containsEntry("catalog", 5)
                .containsEntry("inventory", 1)
                .containsEntry("billing", 3);
    }
}
~~~

Đây là bài test quan trọng vì:

- `retries` trong file profile ghi đè value ở file base.
- `timeout` không xuất hiện trong profile, nên vẫn có thể lấy từ base.
- `regions` là **List** nên bị thay toàn bộ, kết quả `[us]`.
- `limits` là **Map** nên kết hợp các key; catalog trùng bị ghi đè thành 5, inventory được giữ, billing được thêm.

Cùng một thuật toán “merge tất cả” **không áp dụng** cho cả List và Map.

### 14.1. Tách test để dễ tìm nguyên nhân

~~~java
@Test
void profileListReplacesAllPreviousElements() {
    assertThat(properties.regions()).containsExactly("us");
}

@Test
void mapRetainsNonOverriddenKeys() {
    assertThat(properties.limits())
            .containsEntry("inventory", 1)
            .containsEntry("catalog", 5)
            .containsEntry("billing", 3);
}
~~~

Nếu test fail vì một giá trị `regions` không như mong đợi, nó không tự suy ra có lỗi ở `@Validated`. Kiểm tra cấp độ đúng: đầu tiên xác định các Config Data sources rồi mới xem binding.

## 15. Kiểm thử `@TestPropertySource` và dynamic properties

Giá trị tĩnh đã biết từ lúc viết test:

~~~java
@TestPropertySource(properties = {
    "lab.gateway.retries=1",
    "lab.gateway.timeout=3s"
})
~~~

Nhưng Testcontainers hoặc HTTP mock server có thể chọn random mapped port chỉ khi runtime bắt đầu. `@DynamicPropertySource` giải quyết trường hợp này và có precedence cao hơn `@TestPropertySource`.

Test:

~~~java
package com.example.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = DynamicValueTest.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = "lab.gateway.retries=1")
class DynamicValueTest {

    @SpringBootConfiguration
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestApp {
    }

    @DynamicPropertySource
    static void dynamic(DynamicPropertyRegistry registry) {
        registry.add("lab.gateway.retries", () -> 4);
    }

    @Autowired
    GatewayProperties properties;

    @Test
    void dynamicPropertyWins() {
        assertThat(properties.retries()).isEqualTo(4);
    }
}
~~~

Một phương thức `@DynamicPropertySource` phải là `static`, nhận một `DynamicPropertyRegistry` và dùng `registry.add(key, Supplier)`. Supplier có thể là lambda hoặc method reference. Đừng truyền trực tiếp value thay vì Supplier.

### 15.1. Hạn chế của dynamic supplier

Dynamic source có thể được resolve nhiều lần, không chỉ khi đăng ký. Nhưng một singleton đã inject `@Value` hoặc bind `@ConfigurationProperties` **không tự rebind** chỉ vì Supplier đổi value sau startup.

Khi các test classes dùng container khác nhau, Spring TestContext caching có thể giữ bean trỏ tới container cũ đã dừng. Cần quyết định fixture lifecycle và có thể dùng `@DirtiesContext` nếu context không được tái sử dụng an toàn.

## 16. Testcontainers: kiểm tra cả client wiring

Một test chỉ assert JDBC URL string có mặt **không chứng minh** datasource thực sự hoạt động.

Ví dụ hướng dẫn:

~~~java
@Testcontainers
@SpringBootTest
class PostgreSqlIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("integration_db")
            .withUsername("integration_user")
            .withPassword("integration_password");

    @DynamicPropertySource
    static void dataSourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    DataSource dataSource;

    @Test
    void connectsToTheContainer() {
        Integer result = new JdbcTemplate(dataSource)
                .queryForObject("select 1", Integer.class);

        assertThat(result).isEqualTo(1);
    }
}
~~~

Ví dụ cần Testcontainers PostgreSQL/JUnit Jupiter dependencies, Spring JDBC/JDBC starter và PostgreSQL driver; môi trường CI phải có container runtime hoạt động. `@Container` quản lý một container theo vòng đời extension, `@DynamicPropertySource` lấy URL, username và password **thực tế**.

Khi dùng Spring Boot 3.1+ và `spring-boot-testcontainers`, `@ServiceConnection` có thể thay thế một số property registration thủ công bằng `ConnectionDetails`. Chọn một cách tích hợp phù hợp với phiên bản Boot thay vì chồng nhiều cơ chế mâu thuẫn.

## 17. Test cách viết tên key theo relaxed binding

Java component `baseUrl` thường được bind từ key canonical:

~~~properties
lab.gateway.base-url=https://gateway.example.test
~~~

Một số biến thể tên như camelCase cũng được Binder nhận:

~~~java
@Test
void camelCaseNameCanBindToCanonicalProperty() {
    runner.withPropertyValues(
            "lab.gateway.enabled=true",
            "lab.gateway.baseUrl=https://gateway.example.test")
        .run(ctx -> {
            assertThat(ctx).hasNotFailed();

            GatewayProperties p =
                    ctx.getBean(GatewayProperties.class);

            assertThat(p.baseUrl().getHost())
                    .isEqualTo("gateway.example.test");
        });
}
~~~

Nhưng khi viết tài liệu vận hành vẫn nên dùng **một tên canonical kebab-case**.

Đối với OS env:

~~~text
lab.gateway.base-url  → LAB_GATEWAY_BASEURL
lab.gateway.timeout   → LAB_GATEWAY_TIMEOUT
lab.gateway.retries   → LAB_GATEWAY_RETRIES
~~~

Đừng dùng `MapPropertySource` thông thường để mô phỏng mọi ngữ nghĩa của `SystemEnvironmentPropertySource` rồi khẳng định quy tắc chuyển đổi OS env đã được chứng minh. Muốn kiểm thử biến môi trường thật, chạy một process hoặc container với env vars được cấp rõ ràng, hoặc dùng đúng source type ở tầng Environment.

## 18. Kiểm thử custom `Validator` khi rule phức tạp

Với một rule nhiều field, có thể dùng Spring Validator:

~~~java
package com.example.gateway;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class GatewayPropertiesValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return GatewayProperties.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object value, Errors errors) {
        GatewayProperties p = (GatewayProperties) value;

        if (p.enabled() && p.baseUrl() == null) {
            errors.rejectValue("baseUrl",
                "gateway.baseUrl.required",
                "base-url is required when enabled");
        }
    }
}
~~~

Đăng ký theo tên đặc biệt nếu muốn Spring Boot dùng khi bind configuration properties:

~~~java
@Configuration(proxyBeanMethods = false)
public class GatewayValidationConfig {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new GatewayPropertiesValidator();
    }
}
~~~

`@Bean` nên là `static` vì validator có thể được khởi tạo rất sớm.

Test validator thuần:

~~~java
@Test
void customValidatorRejectsMissingEndpoint() {
    GatewayProperties p = new GatewayProperties(
        true, null, Duration.ofSeconds(2), 2,
        List.of(), Map.of());

    BeanPropertyBindingResult errors =
        new BeanPropertyBindingResult(p, "gateway");

    new GatewayPropertiesValidator().validate(p, errors);

    assertThat(errors.hasFieldErrors("baseUrl")).isTrue();
}
~~~

Test này kiểm tra logic validator nhưng chưa chứng minh bean đặc biệt đã được Boot đăng ký. Để test wiring, đưa `GatewayValidationConfig.class` vào `ApplicationContextRunner.withUserConfiguration(...)` và assert startup fails với config tương ứng.

Không nên duy trì trùng lặp cùng rule bằng `@AssertTrue` và custom Validator trong codebase thật nếu không có chủ đích. Chọn cách nhất quán để lỗi không bị lặp.

## 19. Kiểm tra nguồn lỗi khi context thất bại

Một assertion tổng quát:

~~~java
assertThat(context).hasFailed();
~~~

hữu ích, nhưng một context có thể fail vì nhiều nguyên nhân khác nhau. Để tránh false confidence, xem startup failure:

~~~java
@Test
void invalidRetriesPreventStartup() {
    runner.withPropertyValues("lab.gateway.retries=99")
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
}
~~~

Khi cần xác nhận lỗi cụ thể, test class/cause hoặc error code do ứng dụng kiểm soát. Không nên assert toàn bộ stack trace hoặc dấu câu của message Spring Boot, vì chi tiết framework exceptions thay đổi giữa các phiên bản.

### 19.1. Conversion failure và validation failure

~~~properties
lab.gateway.retries=wrong
~~~

là conversion failure.

~~~properties
lab.gateway.retries=99
~~~

là validation failure nếu `@Max(5)` có hiệu lực.

Nếu cả hai test cùng fail, vẫn cần hiểu chúng fail ở hai tầng khác nhau. Một test semantic validation không nên fail vì Spring không tìm thấy bean unrelated.

## 20. Hợp đồng về unknown fields

Spring Boot `@ConfigurationProperties` hỗ trợ:

~~~java
@ConfigurationProperties(
    prefix = "lab.gateway",
    ignoreUnknownFields = false)
~~~

Khi cấu hình sai chính tả:

~~~properties
lab.gateway.timout=5s
~~~

thì `timout` không phải `timeout`. Nếu binder bỏ qua key này, record vẫn có thể nhận default 2s, khiến operator tưởng override `5s` đã có hiệu lực.

Với contract nghiêm ngặt, có thể cân nhắc `ignoreUnknownFields=false` và thêm test một key viết sai. Tuy nhiên, tính phát hiện unknown keys còn phụ thuộc property sources và cấu trúc; không nên cho rằng mọi biến thể sai chính tả ở mọi nguồn đều được báo giống nhau.

Nếu nhiều module chia chung prefix, strict binding cũng có thể làm lộ vấn đề thiết kế namespace. Tốt nhất mỗi nhóm cấu hình có prefix sở hữu rõ ràng.

## 21. Config Data location và working directory trong integration tests

Một ví dụ:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:/etc/gateway/
~~~

`spring.config.additional-location` thêm location ngoài các defaults; `spring.config.location` thay tập locations mặc định. Thông số này cần có từ rất sớm để điều khiển Config Data loading.

Một test với `withPropertyValues("spring.config.additional-location=...")` trong `ApplicationContextRunner` không chứng minh rằng Config Data processor đã load file đó như lúc `SpringApplication` khởi động.

Nếu yêu cầu là kiểm tra location:

1. Tạo file test trong thư mục tạm hoặc fixture cố định.
2. Khởi động `SpringApplication` với argument location tuyệt đối.
3. Assert giá trị được nạp và bean đã bind.
4. Đóng context và dọn fixture đúng vòng đời.
5. Chạy thêm smoke test với filesystem thực của Docker/systemd/Kubernetes nếu cần.

Đường dẫn `file:./config/` phụ thuộc **working directory**, không tự động là thư mục chứa JAR. Nếu production startup ở nơi khác IDE, test cần phản ánh sự khác biệt này.

## 22. Một ma trận kiểm thử gợi ý

| ID | Loại | Input | Kỳ vọng |
| --- | --- | --- | --- |
| P01 | Priority | source A=1, source B=4 (B cao) | 4 |
| P02 | Priority | fallback=1, deployment=3 | 3 |
| P03 | Priority | `setDefaultProperties=1`, CLI=4 | 4 |
| P04 | Profile | base retries=1, it retries=3 | 3 |
| P05 | Dynamic | TestPropertySource=1, dynamic=4 | 4 |
| B01 | Binding | Không khai báo timeout | 2s từ default record |
| B02 | Binding | `timeout=750ms` | `Duration.ofMillis(750)` |
| B03 | Binding | `retries=5` | int 5 |
| B04 | Binding | URI HTTPS | Scheme và host đúng |
| B05 | Binding | regions[0], regions[1] | List có thứ tự |
| B06 | Binding | limits.catalog=2 | Map value Integer 2 |
| B07 | Binding | Profile thay regions | List chỉ chứa từ profile |
| B08 | Binding | Profile thay limits.catalog | Map key trùng bị override |
| B09 | Conversion | `retries=many` | Context fail |
| B10 | Conversion | `limits.catalog=many` | Context fail |
| V01 | Validation | enabled=false, thiếu URL | Context chạy |
| V02 | Validation | enabled=true, thiếu URL | Context fail |
| V03 | Validation | enabled=true, HTTP URL | Context fail |
| V04 | Validation | enabled=true, HTTPS URL | Context chạy |
| V05 | Validation | retries=-1 hoặc 6 | Context fail |
| V06 | Validation | retries=0 hoặc 5 | Context chạy |
| V07 | Validation | timeout=0s, -1s, 11s | Context fail |
| V08 | Validation | timeout=1ms, 10s | Context chạy |
| I01 | Integration | Container random port | Query/HTTP call đúng endpoint |
| I02 | Deployment | External config directory | Đúng value và startup behavior |

Một bộ test tốt có cả **positive** và **negative** cases. Đừng chỉ thử một file cấu hình hợp lệ rồi coi như bảo đảm mọi quy tắc ghi đè và validation đã được thực thi.

## 23. Bài tập thực hành: precedence

Cho các nguồn:

~~~text
Source A:
  lab.gateway.retries=1
  lab.gateway.timeout=2s

Source B (cao hơn A):
  lab.gateway.retries=3

Source C (cao hơn B):
  lab.gateway.base-url=https://gateway.example.test
~~~

Hỏi kết quả cho từng key.

**Đáp án:**

- `retries=3` từ B.
- `timeout=2s` từ A vì không có nguồn nào cao hơn ghi đè.
- `base-url` từ C.
- Mỗi property được resolve theo key, không phải chọn nguyên một source rồi bỏ tất cả key ở source khác.

Hãy viết `StandardEnvironment` test dùng `addFirst` theo thứ tự A, B, C và assert cả ba keys.

## 24. Bài tập: List replacement và Map merge

Cấu hình base:

~~~yaml
lab:
  gateway:
    regions: [apac, eu]
    limits:
      catalog: 2
      inventory: 1
~~~

Config profile:

~~~yaml
lab:
  gateway:
    regions: [us]
    limits:
      catalog: 5
      billing: 3
~~~

**Kỳ vọng:** `regions=[us]`; `limits.catalog=5`, `limits.inventory=1`, `limits.billing=3`.

Không dùng kỳ vọng `regions=[apac,eu,us]` vì Spring Boot list override thông thường không tự concat. Viết test `@SpringBootTest` với hai file YAML để chứng minh rule trong Config Data lifecycle thật.

## 25. Bài tập: phân biệt lỗi conversion và validation

Giả sử:

~~~properties
lab.gateway.retries=abc
~~~

và:

~~~properties
lab.gateway.retries=8
~~~

**Đáp án:**

- `abc` không chuyển được sang int, nên fail trong type conversion.
- `8` chuyển kiểu được, nhưng vi phạm `@Max(5)` nên fail validation.

Một bộ kiểm thử nên có case cho cả hai. Nếu missing key thì theo contract dùng default 2, không fail.

## 26. Bài tập: required có điều kiện

Cho:

~~~text
enabled=false, base-url missing
enabled=true, base-url missing
enabled=true, base-url=http://gateway.example.test
enabled=true, base-url=https://gateway.example.test
~~~

**Kết quả lần lượt:** hợp lệ, fail, fail, hợp lệ.

Rule `@AssertTrue` ở record model cho phép diễn đạt hành vi này. Với logic phức tạp hơn, Spring Validator hoặc Jakarta class-level constraint phù hợp.

Không gắn `@NotNull` lên baseUrl một cách vô điều kiện nếu bạn muốn feature có thể disabled mà không cần URL.

## 27. Bài tập: dynamic value ghi đè test property

~~~java
@TestPropertySource(properties = "lab.gateway.retries=1")
class ExampleTest {

    @DynamicPropertySource
    static void values(DynamicPropertyRegistry registry) {
        registry.add("lab.gateway.retries", () -> 4);
    }
}
~~~

Khi test class chạy trong Spring TestContext, dynamic property có precedence cao hơn TestPropertySource: giá trị được resolve là **4**.

Nếu muốn bean đã bind nhận 4, cần đảm bảo bean được tạo trong context có dynamic source đó. Chỉ có annotation trên JUnit test thuần không khởi tạo Spring context sẽ không tạo cơ chế binding tự động.

## 28. Test hygiene và CI

Các nguyên tắc:

1. Không sửa global JVM properties trong test nếu có lựa chọn context-scoped.
2. Tránh phụ thuộc port cố định cho tài nguyên ngoài.
3. Dùng dữ liệu test không nhạy cảm; không log passwords/tokens.
4. Đảm bảo Testcontainers resource tồn tại trong suốt vòng đời cached context.
5. Tách tests cần Docker khỏi unit tests nhanh khi CI không luôn có runtime.
6. Dùng `@DirtiesContext` chỉ khi thật sự cần reload context, vì nó tốn chi phí.
7. Không assert nguyên văn stack trace của framework.
8. Tạo values khác nhau giữa các sources để test không pass do tình cờ trùng default.
9. Với integration test, xác nhận bean/client thật, không chỉ property String.
10. Đưa profile, Config Data import và startup args vào test có chủ đích.
11. Cô lập các file `src/test/resources/application*.yml` dùng chung trong suite.
12. Dọn temp files, connections và container resources sau test.
13. Test cả giá trị min, max và input ở ngoài boundary.
14. Khi nâng Spring Boot version, xem xét những assumptions về source ordering và conversion.
15. Khi đổi tên, kiểu hoặc default của một key, cập nhật tests như một hợp đồng API.

Lệnh Maven:

~~~bash
mvn test
~~~

Chỉ chạy test contract:

~~~bash
mvn -Dtest=GatewayPropertiesTest test
~~~

Với Gradle:

~~~bash
./gradlew test
~~~

Nếu dự án dùng Maven Failsafe cho integration tests, `mvn verify` có thể chạy những test cấu hình tương ứng theo plugin configuration. Không mặc định mọi project có Failsafe hoạt động nếu chưa cấu hình.

## 29. Khi test fail: trình tự chẩn đoán

1. **Context có bean cần kiểm tra không?** Xem `@EnableConfigurationProperties` hoặc scan.
2. **Value từ nguồn nào?** Kiểm tra active profile, CLI, env và test properties.
3. **Tên key canonical đúng không?** Phân biệt `base-url`, `baseUrl` và OS env naming.
4. **Giá trị convert được không?** `abc` không phải retry int; `wrong` không phải Duration.
5. **Business validation có chạy không?** Có `@Validated` và provider không?
6. **Rule có điều kiện nào?** Enabled=true có bắt buộc URL?
7. **Có profile-specific file không?** Test đã dùng `@ActiveProfiles` chưa?
8. **List/Map merge semantics đúng?** List thay thế, Map có thể gộp keys.
9. **Dynamic source có thay test property không?** `@DynamicPropertySource` có precedence cao.
10. **Context cache có giữ bean cũ?** Kiểm tra fixture lifecycle và `@DirtiesContext`.
11. **Test đang giả lập hay nạp Config Data thật?** Runner và SpringApplication có phạm vi khác nhau.
12. **Startup thất bại vì đúng rule không?** Không để một lỗi dependency không liên quan khiến test pass giả.

Không nên sửa hàng loạt annotation hoặc nguồn cấu hình trước khi biết **tầng nào** đang cho kết quả sai.

## 30. Tổng kết

Một kế hoạch kiểm thử cấu hình tốt đi từ dữ liệu nguồn tới hành vi bean:

~~~text
application.yml / profile / env / CLI / dynamic test source
                     |
                     v
          [PropertySource precedence]
                     |
                     v
          [Binder + type conversion]
                     |
                     v
          [@ConfigurationProperties]
                     |
                     v
          [Jakarta / custom validation]
                     |
                     v
             [Spring beans]
                     |
                     v
         [Integration with real resources]
~~~

Các ý cần nhớ:

- `StandardEnvironment` phù hợp để test priority giữa các nguồn giả rõ ràng.
- `ApplicationContextRunner` phù hợp cho binding/defaults/validation mà không chạy full app.
- `SpringApplication` và `@SpringBootTest` xác minh tốt hơn Config Data và startup semantics.
- `Duration` nên có suffix rõ như `750ms` hoặc `2s`.
- List thường **thay toàn bộ** khi nguồn cao hơn khai báo; Map có thể kết hợp các key.
- `@Validated` và provider thực sự cần tồn tại để kiểm tra Jakarta constraints.
- Error do conversion khác error do semantic validation.
- `@DynamicPropertySource` có precedence cao hơn `@TestPropertySource` nhưng không tự rebind singleton khi Supplier thay đổi sau startup.
- Test positive, negative, boundary, missing, precedence và failure causes riêng biệt.
- Khi có external dependencies, một truy vấn/HTTP request thực tế mới xác minh đầy đủ client wiring.

### Tài liệu tham khảo

- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot — Configuration Properties Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Spring Boot — Testing: https://docs.spring.io/spring-boot/reference/testing/index.html
- Spring Boot — Testing Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing
- Spring Framework — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework — Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Framework — TestContext Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Testcontainers Java — JUnit Jupiter: https://java.testcontainers.org/test_framework_integration/junit_5/
