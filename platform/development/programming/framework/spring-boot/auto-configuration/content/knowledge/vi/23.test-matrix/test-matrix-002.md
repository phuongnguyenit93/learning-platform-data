# Kiểm thử ma trận thuộc tính không khai báo, hợp lệ, không hợp lệ và giá trị biên trong Spring Boot Auto-configuration

## 1. Mục tiêu của ma trận kiểm thử cấu hình

Một class `@ConfigurationProperties` là hợp đồng giữa thư viện Spring Boot và ứng dụng sử dụng thư viện. Hợp đồng này có thể quy định:
- Property nào là bắt buộc.
- Property nào có giá trị mặc định khi người dùng không khai báo.
- Kiểu dữ liệu và quy tắc chuyển đổi.
- Khoảng giá trị hợp lệ, định dạng hoặc ràng buộc nghiệp vụ.
- Cách xử lý key không thuộc hợp đồng cấu hình.

Chỉ kiểm thử một trường hợp “cấu hình hợp lệ” là chưa đủ. Một ma trận tốt phải bao phủ ít nhất bốn nhóm được nêu trong đề bài:

| Nhóm | Câu hỏi | Kết quả mong đợi |
| --- | --- | --- |
| Không khai báo | Người dùng bỏ qua property thì default có được áp dụng không? Property bắt buộc có bị từ chối không? | Default được dùng cho property tùy chọn; property bắt buộc thất bại rõ ràng |
| Hợp lệ | Giá trị đúng kiểu và thỏa constraint có bind được không? | Context khởi động, bean nhận đúng giá trị |
| Không hợp lệ | Giá trị sai kiểu, sai định dạng hoặc vi phạm constraint có bị phát hiện không? | Context thất bại với lỗi binding hoặc validation tương ứng |
| Giá trị biên | Giá trị đúng tại min/max có được chấp nhận, còn vượt ra ngoài có bị từ chối? | Biên bao gồm được chấp nhận; ngoài biên bị từ chối |

Bài này dùng `ApplicationContextRunner` để kiểm tra cả property binding lẫn auto-configuration. Mỗi test tạo một context độc lập, truyền property qua `withPropertyValues(...)` rồi assert bean và trạng thái khởi động. Không cần mở server hay kết nối database.

## 2. Phân biệt property không khai báo và key không được hỗ trợ

Hai tình huống thường bị gọi chung là “thiếu property”, nhưng có semantics khác nhau.

**Property không được khai báo trong Environment** là key hợp lệ của class properties nhưng người dùng không cung cấp giá trị. Kết quả phụ thuộc thiết kế:
- Field có initializer hoặc constructor default có thể giữ giá trị mặc định.
- Field không có default có thể nhận `null` hoặc giá trị primitive mặc định như `0`.
- Constraint như `@NotBlank`, `@NotNull` hoặc `@Min` có thể khiến context thất bại khi validation được bật.

**Key không được khai báo trong class properties** là key có trong `application.yml` nhưng class không có field/getter/constructor property tương ứng. Mặc định `@ConfigurationProperties` dùng `ignoreUnknownFields = true`, nên unknown key thường được bỏ qua. Nếu muốn cấu hình strict, đặt `ignoreUnknownFields = false` để việc bind key không được nhận diện trở thành lỗi.

Ví dụ:

~~~yaml
acme:
  retry:
    name: primary
    max-attempts: 4
    legacy-mode: true
~~~

Nếu class chỉ định nghĩa `name` và `maxAttempts`, `legacy-mode` là unknown property. Nó không giống trường hợp `max-attempts` bị bỏ trống.

**Quy tắc thiết kế:** quyết định rõ property nào là optional, property nào required, và có muốn từ chối unknown key hay không. Đừng dựa vào giá trị primitive mặc định `0` để ngầm biểu đạt một cấu hình hợp lệ.

## 3. Định nghĩa hợp đồng properties có default và validation

Ví dụ Java 17+ dùng JavaBean binding để dễ quan sát default và setter. Class này thuộc thư viện và được đăng ký bằng `@EnableConfigurationProperties` trong auto-configuration.

File `src/main/java/com/acme/retry/RetryProperties.java`:

~~~java
package com.acme.retry;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.retry")
@Validated
public class RetryProperties {

    /**
     * Tên cấu hình retry; ứng dụng phải cung cấp giá trị.
     */
    @NotBlank
    private String name;

    /**
     * Số lần thử tối đa, mặc định là 3 và chỉ chấp nhận từ 1 đến 10.
     */
    @Min(1)
    @Max(10)
    private int maxAttempts = 3;

    /**
     * Endpoint mặc định nếu ứng dụng không khai báo.
     */
    @NotBlank
    private String endpoint = "https://retry.example";

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

Ý nghĩa từng trường:

| Property | Java type | Required/default | Constraint |
| --- | --- | --- | --- |
| `acme.retry.name` | `String` | Bắt buộc; không có default | `@NotBlank` |
| `acme.retry.max-attempts` | `int` | Tùy chọn; default `3` | `@Min(1)` và `@Max(10)` |
| `acme.retry.endpoint` | `String` | Tùy chọn; default URL | `@NotBlank` |

Spring Boot relaxed binding ánh xạ key kebab-case `max-attempts` sang Java property `maxAttempts`. Dùng kebab-case trong file cấu hình để nhất quán với quy ước Spring Boot.

### Vì sao phải có @Validated và validation provider?

Các annotation `@Min`, `@Max` và `@NotBlank` thuộc Jakarta Bean Validation. Để chúng thực sự được áp dụng khi bind `@ConfigurationProperties`, cần:
1. Đánh dấu class properties bằng `@Validated`.
2. Có implementation Bean Validation trên classpath, thường qua dependency `spring-boot-starter-validation`.
3. Khai báo constraint phù hợp với kiểu dữ liệu.

Nếu thiếu validation provider, không thể kỳ vọng constraint tự chạy chỉ vì annotation đang có trong source. Binding chuyển đổi kiểu vẫn có thể hoạt động, nhưng các ràng buộc Bean Validation không được thực thi như mong muốn.

## 4. Đăng ký properties qua auto-configuration

File `src/main/java/com/acme/retry/autoconfigure/RetryAutoConfiguration.java`:

~~~java
package com.acme.retry.autoconfigure;

import com.acme.retry.RetryProperties;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;

@AutoConfiguration
@EnableConfigurationProperties(RetryProperties.class)
public class RetryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    RetryExecutor retryExecutor(RetryProperties properties) {
        return new RetryExecutor(
                properties.getName(),
                properties.getMaxAttempts(),
                properties.getEndpoint());
    }
}
~~~

Bean dùng giá trị đã bind:

~~~java
package com.acme.retry.autoconfigure;

public final class RetryExecutor {

    private final String name;
    private final int maxAttempts;
    private final String endpoint;

    public RetryExecutor(String name, int maxAttempts, String endpoint) {
        this.name = name;
        this.maxAttempts = maxAttempts;
        this.endpoint = endpoint;
    }

    public String getName() {
        return name;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public String getEndpoint() {
        return endpoint;
    }
}
~~~

Trong JAR thư viện, đăng ký `RetryAutoConfiguration` bằng file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

~~~text
com.acme.retry.autoconfigure.RetryAutoConfiguration
~~~

Trong `ApplicationContextRunner` bên dưới, class auto-configuration được đưa trực tiếp qua `AutoConfigurations.of(...)` nên test không cần kiểm tra discovery descriptor. Descriptor vẫn bắt buộc đối với auto-configuration được phát hiện tự động khi ứng dụng tiêu thụ JAR.

## 5. Cách phân loại lỗi: binding, conversion và validation

Không phải mọi cấu hình sai đều thất bại ở cùng một bước.

**Binding thành công:** Binder tìm thấy property, chuyển đổi được kiểu dữ liệu và gán giá trị vào properties object.

**Conversion/binding failure:** giá trị không chuyển được sang Java type. Ví dụ `max-attempts=abc` không thể chuyển thành `int`. Lỗi này xảy ra trước khi có thể đánh giá `@Min`/`@Max` cho giá trị đó.

**Validation failure:** giá trị đã bind được nhưng vi phạm constraint. Ví dụ `max-attempts=0` là số nguyên hợp lệ nhưng thấp hơn `@Min(1)`; `name=""` bind được thành chuỗi rỗng nhưng vi phạm `@NotBlank`.

**Missing required property:** nếu field không có default, sau binding nó có thể là `null`; `@NotBlank` hoặc `@NotNull` phát hiện thiếu dữ liệu. Với primitive, cần cẩn trọng vì giá trị mặc định của Java là 0; hãy dùng wrapper hoặc constraint thích hợp nếu cần phân biệt “không khai báo” với giá trị số 0.

Bảng chẩn đoán:

| Input | Giai đoạn | Kết quả |
| --- | --- | --- |
| Không có `acme.retry.name` | Validation | `@NotBlank` từ chối `null` |
| Không có `acme.retry.max-attempts` | Default/binding | Giữ `3` từ initializer |
| `max-attempts=abc` | Conversion/binding | Không chuyển được sang `int` |
| `max-attempts=0` | Validation | Vi phạm `@Min(1)` |
| `max-attempts=11` | Validation | Vi phạm `@Max(10)` |
| `max-attempts=1` hoặc `10` | Validation | Hợp lệ tại biên bao gồm |
| `legacy-mode=true` | Unknown field handling | Mặc định bị bỏ qua nếu không tắt `ignoreUnknownFields` |

Phân biệt các giai đoạn này giúp test kiểm tra đúng nguyên nhân. Một lỗi conversion không chứng minh validation hoạt động; một lỗi validation cũng không chứng minh property conversion cho mọi kiểu dữ liệu đều đúng.

## 6. Thiết lập test dependencies và runner

Project ví dụ dùng Java 17+, Spring Boot 3.3, JUnit 5, AssertJ và Jakarta Validation. Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Với Maven, các dependency tương đương:

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

Nếu dùng Spring Boot BOM hoặc starter parent, version được quản lý tập trung. Nếu không, import BOM hoặc khai báo version tương thích.

Runner cơ sở:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(RetryAutoConfiguration.class));
~~~

`AutoConfigurations.of(...)` đưa auto-configuration vào context theo đúng cơ chế test của Boot. Mỗi lần gọi `run(...)` tạo một context mới, vì vậy test có thể thay property values mà không rò rỉ trạng thái giữa các case.

## 7. Bài test hoàn chỉnh cho missing, valid, invalid và boundary

File `src/test/java/com/acme/retry/RetryPropertiesMatrixTests.java`. Để ví dụ tự chứa, các class properties và auto-configuration được khai báo static bên trong test; trong thư viện thực tế, dùng class production ở các mục trước.

~~~java
package com.acme.retry;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.annotation.Validated;

import static org.assertj.core.api.Assertions.assertThat;

class RetryPropertiesMatrixTests {

    @ConfigurationProperties(prefix = "acme.retry")
    @Validated
    static class RetryProperties {

        @NotBlank
        private String name;

        @Min(1)
        @Max(10)
        private int maxAttempts = 3;

        @NotBlank
        private String endpoint = "https://retry.example";

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public String getEndpoint() {
            return endpoint;
        }

        public void setEndpoint(String endpoint) {
            this.endpoint = endpoint;
        }
    }

    static final class RetryExecutor {
        private final RetryProperties properties;

        RetryExecutor(RetryProperties properties) {
            this.properties = properties;
        }

        int maxAttempts() {
            return properties.getMaxAttempts();
        }
    }

    @AutoConfiguration
    @EnableConfigurationProperties(RetryProperties.class)
    static class RetryAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean
        RetryExecutor retryExecutor(RetryProperties properties) {
            return new RetryExecutor(properties);
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(RetryAutoConfiguration.class));

    @Test
    void omittedOptionalPropertiesUseTheirDefaults() {
        runner.withPropertyValues("acme.retry.name=primary")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    RetryProperties properties =
                            context.getBean(RetryProperties.class);

                    assertThat(properties.getName()).isEqualTo("primary");
                    assertThat(properties.getMaxAttempts()).isEqualTo(3);
                    assertThat(properties.getEndpoint())
                            .isEqualTo("https://retry.example");
                    assertThat(context.getBean(RetryExecutor.class)
                            .maxAttempts()).isEqualTo(3);
                });
    }

    @Test
    void missingRequiredPropertyFailsValidation() {
        runner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasStackTraceContaining("name")
                    .hasStackTraceContaining("must not be blank");
        });
    }

    @Test
    void validPropertiesAndUnknownKeyBindAsExpected() {
        runner.withPropertyValues(
                "acme.retry.name=primary",
                "acme.retry.max-attempts=4",
                "acme.retry.endpoint=https://api.example.test",
                "acme.retry.legacy-mode=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    RetryProperties properties =
                            context.getBean(RetryProperties.class);

                    assertThat(properties.getMaxAttempts()).isEqualTo(4);
                    assertThat(properties.getEndpoint())
                            .isEqualTo("https://api.example.test");
                });
    }

    @Test
    void acceptsBothInclusiveBoundaryValues() {
        for (String value : new String[] {"1", "10"}) {
            runner.withPropertyValues(
                    "acme.retry.name=primary",
                    "acme.retry.max-attempts=" + value)
                    .run(context -> {
                        assertThat(context).hasNotFailed();
                        assertThat(context.getBean(RetryProperties.class)
                                .getMaxAttempts()).isEqualTo(Integer.parseInt(value));
                    });
        }
    }

    @Test
    void rejectsNumbersOutsideTheAllowedRange() {
        for (String value : new String[] {"0", "11"}) {
            runner.withPropertyValues(
                    "acme.retry.name=primary",
                    "acme.retry.max-attempts=" + value)
                    .run(context -> {
                        assertThat(context).hasFailed();
                        assertThat(context.getStartupFailure())
                                .hasStackTraceContaining("maxAttempts");
                    });
        }
    }

    @Test
    void rejectsBlankRequiredName() {
        runner.withPropertyValues("acme.retry.name=   ")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining("must not be blank");
                });
    }

    @Test
    void malformedIntegerFailsDuringBinding() {
        runner.withPropertyValues(
                "acme.retry.name=primary",
                "acme.retry.max-attempts=abc")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining("acme.retry.max-attempts");
                });
    }
}
~~~

Test class dùng cùng contract properties và auto-configuration với ví dụ production. Khi chuyển vào project thật, bỏ class nested trùng lặp và import class từ module autoconfigure.

Chạy bằng Gradle:

~~~bash
./gradlew test --tests "com.acme.retry.RetryPropertiesMatrixTests"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.acme.retry.RetryPropertiesMatrixTests"
~~~

Maven:

~~~bash
mvn -Dtest=RetryPropertiesMatrixTests test
~~~

**Kết quả kỳ vọng:** 7 test PASS. Hai vòng lặp trong test boundary/range lần lượt kiểm tra hai giá trị, nên tổng số tình huống được kiểm tra nhiều hơn số method test.

## 8. Đọc kết quả test theo từng nhóm

| Scenario | Input chính | Assertion quan trọng | Ý nghĩa |
| --- | --- | --- | --- |
| Optional missing | Chỉ khai báo `name` | `maxAttempts=3`, endpoint giữ default | Default trong properties được giữ khi key vắng mặt |
| Required missing | Không khai báo `name` | Context failed, có lỗi `must not be blank` | Contract bắt buộc được bảo vệ |
| Valid + unknown | `max-attempts=4` và key lạ | Context thành công, giá trị 4 được bind | Key không hỗ trợ bị bỏ qua theo mặc định |
| Min boundary | `max-attempts=1` | Context thành công | Biên dưới được bao gồm |
| Max boundary | `max-attempts=10` | Context thành công | Biên trên được bao gồm |
| Below min | `max-attempts=0` | Context failed | Validation từ chối giá trị nhỏ hơn 1 |
| Above max | `max-attempts=11` | Context failed | Validation từ chối giá trị lớn hơn 10 |
| Blank required | `name` là chuỗi trắng | Context failed | `@NotBlank` từ chối chuỗi rỗng/chỉ whitespace |
| Invalid conversion | `max-attempts=abc` | Context failed khi bind | Chuỗi không chuyển được sang `int` |

Lưu ý: các assertion trên kiểm tra outcome và dấu hiệu lỗi ổn định ở mức đủ dùng; không nên khóa test vào toàn bộ message hoặc thứ tự property trong exception vì chúng có thể thay đổi giữa các phiên bản validator/compiler.

## 9. Giá trị biên: inclusive, exclusive và kiểu dữ liệu

`@Min(1)` và `@Max(10)` là ràng buộc **bao gồm biên**:
- 1 hợp lệ.
- 10 hợp lệ.
- 0 và 11 không hợp lệ.

Nếu nghiệp vụ yêu cầu khoảng mở, chẳng hạn giá trị phải lớn hơn 1 và nhỏ hơn 10, dùng constraint tương ứng như `@DecimalMin(value = "1", inclusive = false)` và `@DecimalMax(value = "10", inclusive = false)` cho kiểu số phù hợp.

Với `int`, các biên nguyên thường dễ kiểm tra. Với `BigDecimal`, cần chú ý scale và phép so sánh số học; không so sánh bằng chuỗi biểu diễn. Với `Duration`, `DataSize` hoặc enum, hãy dùng converter/constraint tương ứng thay vì ép mọi thứ thành số nguyên.

### Đừng quên giá trị null

`@Min` và `@Max` theo Bean Validation thường xem `null` là hợp lệ; chúng chỉ kiểm tra khi có giá trị. Nếu property bắt buộc, kết hợp `@NotNull` với constraint số. Ví dụ:

~~~java
@NotNull
@Min(1)
@Max(10)
private Integer maxAttempts;
~~~

Sự khác biệt:
- `int` luôn có giá trị primitive, nhưng khi property vắng mặt có thể giữ initializer hoặc thành 0 nếu không có initializer.
- `Integer` có thể là `null` khi property vắng mặt.
- `@NotNull` làm rõ yêu cầu phải có giá trị.
- `@Min`/`@Max` xác định khoảng số hợp lệ.

Chọn kiểu dữ liệu dựa trên việc ứng dụng có cần phân biệt “không khai báo” với “được khai báo bằng 0” hay không.

## 10. Kiểm tra unknown fields theo chính sách của thư viện

Mặc định `ignoreUnknownFields=true` cho phép Binder bỏ qua key không được class properties mô tả. Điều này hữu ích khi có nhiều profile hoặc phiên bản cấu hình, nhưng cũng có thể che giấu lỗi gõ sai:

~~~yaml
acme:
  retry:
    max-attemtps: 5 # typo: thiếu chữ p trong attempts
~~~

Nếu `ignoreUnknownFields=true`, key sai có thể bị bỏ qua và default `maxAttempts=3` vẫn được dùng. Đây là lý do test “unknown key” nên được cân nhắc cùng với test typo.

Nếu muốn strict binding, khai báo:

~~~java
@ConfigurationProperties(
        prefix = "acme.retry",
        ignoreUnknownFields = false
)
public class RetryProperties {
    // Các property đã khai báo
}
~~~

Khi đó key không được bind có thể gây lỗi `UnboundConfigurationPropertiesException` trong quá trình binding. Strict mode hữu ích với cấu hình nhỏ, được quản lý chặt; với thư viện public cần tương thích giữa các phiên bản, hãy cân nhắc việc từ chối property tương lai mà ứng dụng đang dùng.

Không nhầm `ignoreUnknownFields` với `ignoreInvalidFields`:
- `ignoreUnknownFields` điều khiển key không có property tương ứng.
- `ignoreInvalidFields` điều khiển việc bỏ qua lỗi bind/conversion cho field đã biết; mặc định là `false` và thường nên giữ như vậy để cấu hình sai được phát hiện.

## 11. Property phụ thuộc condition và test theo tổ hợp

Ngoài binding/validation, một property có thể bật/tắt bean bằng `@ConditionalOnProperty`. Đây là một lớp quyết định khác:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "acme.retry.metrics",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
RetryMetrics retryMetrics() {
    return new RetryMetrics();
}
~~~

Ma trận cho condition:

| Property | Bean metrics |
| --- | --- |
| Không khai báo, `matchIfMissing=false` | Không tạo |
| `enabled=true` | Tạo |
| `enabled=false` | Không tạo |
| Giá trị không phải `true` | Không khớp với `havingValue="true"` |

`@ConditionalOnProperty` không thay thế Bean Validation. Nó quyết định bean có được đăng ký hay không; `@Min`, `@Max` và `@NotBlank` xác nhận dữ liệu đã bind có hợp lệ hay không.

Khi viết test, tách assertion cho hai lớp:
1. Properties bean có bind/validate đúng không?
2. Bean tùy chọn có xuất hiện theo condition không?

Điều này giúp biết lỗi nằm ở cấu hình dữ liệu hay ở quyết định auto-configuration.

## 12. Ma trận kiểm thử mở rộng nên có

Với một class properties thực tế, có thể lập bảng trước khi viết test:

| Nhóm | Ví dụ input | Kiểm tra |
| --- | --- | --- |
| Missing optional | Không có key, field có default | Default đúng |
| Missing required | Không có key, field có `@NotNull`/`@NotBlank` | Context thất bại |
| Explicit empty | Chuỗi `""` hoặc whitespace | Constraint đúng |
| Valid typical | Giá trị ở giữa khoảng | Bind và bean đúng |
| Min boundary | Đúng min | Thành công |
| Max boundary | Đúng max | Thành công |
| Below min | min trừ một đơn vị | Validation fail |
| Above max | max cộng một đơn vị | Validation fail |
| Wrong type | `abc` cho integer | Binding/conversion fail |
| Unknown key | Key không có trong class | Theo chính sách ignore/strict |
| Typo key | Gõ sai một ký tự | Không âm thầm dùng default ngoài ý muốn |
| Conditional bean | Property bật/tắt | Bean có/không đúng |
| Multiple properties | Nhiều key cùng thay đổi | Không bỏ sót tương tác giữa fields |
| Profile/override | Giá trị từ profile hoặc environment khác | Nguồn ưu tiên đúng |

Không phải dự án nào cũng cần mọi tổ hợp. Ưu tiên các case bảo vệ hợp đồng công khai và các lỗi từng xảy ra; tránh tạo tổ hợp Cartesian lớn không mang thêm giá trị.

## 13. Chẩn đoán lỗi từ ApplicationContextRunner

Khi context thất bại, xem `context.getStartupFailure()` thay vì chỉ assert `hasFailed()`. Có thể thêm Condition Evaluation Report listener khi cần điều tra condition:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(RetryAutoConfiguration.class))
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            if (context.getStartupFailure() != null) {
                context.getStartupFailure().printStackTrace();
            }
        });
~~~

Imports:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Đọc lỗi theo dấu hiệu:
- `Failed to bind properties under ...`: kiểm tra prefix, key và target type.
- `Failed to convert ...`: kiểm tra chuỗi đầu vào và converter.
- `must not be blank` hoặc `must be greater than or equal to ...`: Bean Validation đã chạy và từ chối giá trị.
- `NoSuchBeanDefinitionException`: kiểm tra properties class đã được đăng ký bằng `@EnableConfigurationProperties` hoặc scan chưa.
- Bean optional vắng mặt: xem `@ConditionalOnProperty` và `matchIfMissing`.
- Unknown property: xem `ignoreUnknownFields` và tên key thực tế.

Trong test, tránh assert nguyên văn toàn bộ stack trace. Chỉ assert failure state và phần message/field đủ phân biệt loại lỗi.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bỏ qua property nhưng context vẫn nhận `0` | Field primitive không có initializer | Đặt default rõ hoặc dùng wrapper + `@NotNull` |
| `@Min`/`@Max` không chạy | Thiếu `@Validated` hoặc validation provider | Thêm `@Validated` và `spring-boot-starter-validation` |
| Giá trị sai kiểu không bị phát hiện | Cấu hình đang bỏ qua invalid fields hoặc converter tùy chỉnh làm mất lỗi | Giữ `ignoreInvalidFields=false` và test conversion |
| Giá trị 1 bị từ chối dù dùng `@Min(1)` | Constraint/kiểu dữ liệu hoặc annotation import sai | Dùng Jakarta Validation đúng version; kiểm tra inclusive boundary |
| Unknown key bị bỏ qua | `ignoreUnknownFields=true` mặc định | Cân nhắc strict mode hoặc test typo |
| Property key sai nhưng default vẫn được dùng | Binder không tìm thấy key đúng; unknown key bị bỏ qua | Viết test cho key typo và kiểm tra metadata/relaxed binding |
| Properties bean không xuất hiện | Chưa đăng ký properties class | Dùng `@EnableConfigurationProperties` hoặc cơ chế scan phù hợp |
| Test pass dù validation chưa được bật | Test không đưa invalid input hoặc thiếu provider | Có test invalid rõ ràng và xác nhận context fail |
| Test bị ảnh hưởng bởi case trước | Dùng chung mutable fixture/context | Dùng `ApplicationContextRunner`; mỗi lần `run` tạo context riêng |
| Test khóa vào exception message quá cụ thể | Message phụ thuộc validator/version | Assert field, loại lỗi hoặc đoạn message ổn định cần thiết |

## 15. Nguyên tắc xây dựng ma trận bền vững

- Xác định property optional/required trước khi viết class.
- Khai báo default ở đúng nơi và test khi key vắng mặt.
- Dùng wrapper type khi cần phân biệt null với giá trị primitive mặc định.
- Bật Bean Validation rõ ràng bằng `@Validated` và provider tương ứng.
- Kiểm tra riêng conversion failure và validation failure.
- Với khoảng số, test cả min, max, dưới min và trên max.
- Test chuỗi rỗng/whitespace cho property bắt buộc.
- Quyết định chính sách unknown fields; thêm test cho typo nếu default có thể che giấu lỗi.
- Dùng `ApplicationContextRunner` để xác nhận bean properties và bean auto-configured được đăng ký theo đúng dữ liệu.
- Assert cả giá trị đã bind và trạng thái context; chỉ kiểm tra context khởi động là chưa đủ.
- Tránh khóa test vào stack trace hoàn chỉnh; giữ assertion đủ cụ thể để chẩn đoán.
- Cập nhật ma trận khi public configuration contract thay đổi.

## 16. Tự kiểm tra kiến thức

1. Property tùy chọn không được khai báo có thể nhận giá trị nào? **Giá trị default từ initializer/constructor nếu được thiết kế; nếu không có, theo quy tắc của Java type.**
2. Property bắt buộc kiểu String nên dùng constraint nào? **`@NotBlank` hoặc `@NotNull` tùy hợp đồng.**
3. `@Min(1)` có chấp nhận 1 không? **Có, biên là inclusive.**
4. `@Max(10)` có chấp nhận 10 không? **Có.**
5. `max-attempts=abc` là lỗi validation hay conversion? **Conversion/binding failure.**
6. `max-attempts=0` là lỗi nào? **Validation failure do `@Min(1)`.**
7. Annotation nào kích hoạt validation cho properties class? **`@Validated`, cùng validation provider trên classpath.**
8. Processor/annotation metadata có thay Bean Validation không? **Không; metadata phục vụ tooling, validation kiểm tra dữ liệu runtime khi bind.**
9. Unknown key bị bỏ qua theo mặc định không? **Có, vì `ignoreUnknownFields=true` mặc định.**
10. Làm sao bắt unknown key? **Đặt `ignoreUnknownFields=false` và kiểm tra lỗi binding.**
11. Vì sao dùng `ApplicationContextRunner`? **Để tạo context độc lập và kiểm tra binding/conditions theo từng bộ property.**
12. Test boundary nên gồm gì? **Min, max, một giá trị dưới min và một giá trị trên max.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Validating @ConfigurationProperties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): `@Validated`, Jakarta Bean Validation và validation provider.
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding, relaxed binding, default values và constructor/JavaBean binding.
- [Spring Boot 3.3 — @ConfigurationProperties JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): `ignoreUnknownFields` và `ignoreInvalidFields`.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `ApplicationContextRunner` và kiểm tra context theo property values.
- [Jakarta Bean Validation 3.0 — Built-in constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): semantics của `@NotBlank`, `@Min` và `@Max`.
