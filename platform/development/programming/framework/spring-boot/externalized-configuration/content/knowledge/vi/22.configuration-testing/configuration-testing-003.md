# Kiểm thử bean cấu hình bằng ApplicationContextRunner.withPropertyValues

## 1. Vì sao nên kiểm thử cấu hình như một thành phần độc lập?

Trong Spring Boot, ứng dụng có thể chạy đúng trên máy lập trình viên nhưng không khởi động ở staging hoặc production vì thiếu một property, sai kiểu dữ liệu, sai tên biến môi trường hoặc vi phạm ràng buộc giữa các trường.

Ví dụ:

~~~yaml
demo:
  delivery:
    endpoint: "https://delivery.example.invalid"
    timeout: 5s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Tập cấu hình này có vẻ đơn giản, nhưng một số lỗi rất dễ xuất hiện:

- Gõ **demo.delivery.time-out** thay vì tên được model sử dụng.
- Ghi **timeout: five-seconds**, không chuyển được thành **Duration**.
- Để **endpoint** trống dù client yêu cầu URL.
- Cấp **retry.max-attempts: 0**, trái với quy tắc ít nhất một lần thử.
- Quên đăng ký **@ConfigurationProperties** nên bean không được tạo.
- Giả định rằng một default nằm trong Java record cũng được thêm ngược vào **Environment**.
- Chỉ kiểm tra file **application.yml** mà không kiểm tra những giá trị được override khi khởi chạy.

Có thể dùng **@SpringBootTest** để kiểm tra, nhưng nếu mục tiêu chỉ là **một configuration bean** và những giá trị từ Environment, việc khởi động cả ứng dụng có thể tạo nhiều bean và hạ tầng không liên quan, khiến test chậm hoặc khó xác định nguyên nhân lỗi.

**ApplicationContextRunner** của Spring Boot Test giúp tạo một **ApplicationContext nhỏ, có kiểm soát**, với các property mà test chỉ định trực tiếp:

~~~java
new ApplicationContextRunner()
    .withPropertyValues("demo.delivery.timeout=5s")
    .run(context -> {
        // Assert bean và giá trị đã được bind
    });
~~~

Đây là cách thực hành rất phù hợp cho **kiểm thử cấu hình**, đặc biệt khi viết **@ConfigurationProperties**, auto-configuration hoặc thư viện cần hoạt động với nhiều bộ property.

Bài này sử dụng **Spring Boot 3.3.x**, **Java 21**, JUnit 5, AssertJ và ví dụ độc lập không cần kết nối API thật. Domain **example.invalid** chỉ dành cho minh họa.

## 2. Kết quả học tập

Sau bài này, bạn có thể:

1. Hiểu **ApplicationContextRunner** tạo context thử nghiệm như thế nào.
2. Dùng **withPropertyValues("key=value", ...)** để cấp và ghi đè test properties.
3. Đăng ký configuration bean qua **@EnableConfigurationProperties** trong một test configuration.
4. Kiểm tra **binding thành công** vào **record** hoặc JavaBean.
5. Kiểm tra **Duration**, URI, boolean, enum và kiểu số sau conversion.
6. Kiểm tra nested properties và collection như **List**, **Map**.
7. Kiểm tra **default values** và trường hợp property không được cung cấp.
8. Kiểm tra **Bean Validation** với **@Validated**, **@NotBlank**, **@NotNull**, **@Min**, **@Valid**.
9. Phân biệt lỗi **không tạo bean**, lỗi **conversion/binding** và lỗi **validation**.
10. Test bean điều kiện với **@ConditionalOnProperty**.
11. Dùng các trường hợp test riêng không làm nhiễm dữ liệu giữa các lần chạy.
12. Biết giới hạn của ApplicationContextRunner so với **@SpringBootTest** và quy trình khởi động SpringApplication đầy đủ.

## 3. ApplicationContextRunner là gì?

**org.springframework.boot.test.context.runner.ApplicationContextRunner** là một test utility tạo **standard non-web ApplicationContext**, cho phép chỉ định những configuration classes, beans và Environment property values cần thiết.

Ví dụ tối thiểu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingConfigTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withPropertyValues("app.greeting=Xin chào");

    @Test
    void suppliesPropertyToEnvironment() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getEnvironment()
                    .getProperty("app.greeting"))
                    .isEqualTo("Xin chào");
        });
    }
}
~~~

Điểm cần chú ý:

- **withPropertyValues(...)** thêm property vào Environment của context được tạo khi chạy test.
- **run(context -> { ... })** khởi tạo context và cung cấp một **AssertableApplicationContext** để assertion.
- Context được **đóng sau callback**, tránh tích lũy các singleton hoặc tài nguyên của lần chạy trước.
- Đây là **non-web context**; test không tự khởi động embedded Tomcat, Jetty hay một REST server.
- **Không có toàn bộ auto-configuration của ứng dụng được bật mặc định**. Bạn phải đăng ký những configuration/auto-configuration mà bài test cần.

Một ApplicationContextRunner có thể dùng làm **template** cho nhiều test, mỗi lần bổ sung bộ property khác nhau mà không cần build lại ApplicationContext của cả hệ thống.

### 3.1. Khác với ApplicationRunner

Tên dễ gây nhầm:

| Type | Mục đích |
| --- | --- |
| **ApplicationContextRunner** | Công cụ trong **spring-boot-test**, tạo context nhỏ để chạy assertion |
| **ApplicationRunner** | Interface cho callback chạy sau khi Spring Boot application context được chuẩn bị |
| **CommandLineRunner** | Interface callback có arguments sau startup |
| **SpringApplication** | Điều phối toàn bộ vòng đời khởi động Spring Boot |
| **@SpringBootTest** | Hỗ trợ integration test với application context theo cơ chế Spring Boot Test |

Không dùng **ApplicationRunner** thay cho **ApplicationContextRunner** trong JUnit test.

## 4. Dependency và cấu trúc dự án

Ví dụ Gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Version trong ví dụ là một phiên bản của dòng Spring Boot 3.3**, không phải yêu cầu phải dùng đúng những patch version đó; trong dự án thực, nên sử dụng version được hệ thống build quản lý/phê duyệt.

Ví dụ Maven:

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

Maven snippet giả định project đã khai báo parent/BOM Spring Boot thích hợp, hoặc các dependency versions được quản lý ở nơi khác.

Các thành phần quan trọng:

- **spring-boot-starter-test** cung cấp Spring Boot Test, JUnit 5, AssertJ và các tiện ích test thông dụng.
- **spring-boot-starter-validation** cung cấp một Bean Validation implementation cho các annotation **jakarta.validation**.
- **ApplicationContextRunner** thuộc package **org.springframework.boot.test.context.runner**, không phải class của Spring Framework core.
- Test ở dạng JUnit thông thường không cần annotation **@SpringBootTest**.

Cây thư mục:

~~~text
src/
├── main/
│   └── java/
│       └── com/example/delivery/
│           ├── DeliveryProperties.java
│           └── DeliveryClient.java
└── test/
    └── java/
        └── com/example/delivery/
            ├── DeliveryPropertiesTest.java
            ├── DeliveryDefaultsTest.java
            └── DeliveryFeatureConditionTest.java
~~~

Các file test sau đây là ví dụ độc lập hoặc bổ sung cho cùng một cấu trúc; không cần copy tất cả nếu bài thực hành chỉ tập trung vào một aspect.

## 5. Tạo @ConfigurationProperties cần kiểm thử

Một record cấu hình cho delivery client:

~~~java
package com.example.delivery;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.delivery")
public record DeliveryProperties(
        @NotBlank String endpoint,
        @NotNull Duration timeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff) {
    }
}
~~~

**Endpoint** ở đây chọn **String** để có thể kiểm tra thiếu/rỗng bằng **@NotBlank**. Nếu muốn type chặt hơn, có thể dùng **URI** và ràng buộc thêm scheme/host phù hợp. Đừng cho rằng một URI syntactically parseable tự động chứng minh endpoint an toàn hoặc có thể kết nối.

Tên canonical của các property:

~~~text
demo.delivery.endpoint
demo.delivery.timeout
demo.delivery.retry.max-attempts
demo.delivery.retry.backoff
~~~

YAML minh họa:

~~~yaml
demo:
  delivery:
    endpoint: "https://delivery.example.invalid"
    timeout: 5s
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Trong test dùng **withPropertyValues**, ta sẽ cung cấp trực tiếp những property này dưới dạng các chuỗi **"key=value"**, không cần tạo file YAML tạm.

### 5.1. Tại sao có @Validated và @Valid?

- **@Validated** yêu cầu validation trên type configuration properties khi hạ tầng binding tương ứng hoạt động.
- **@NotBlank** trên endpoint yêu cầu có nội dung không chỉ gồm whitespace.
- **@NotNull** trên timeout và retry yêu cầu các giá trị tồn tại.
- **@Min(1)** trên maxAttempts yêu cầu số lần thử ít nhất là một.
- **@Valid** trên retry yêu cầu validation đi sâu vào nested record.

Spring Boot Binder chịu trách nhiệm chuyển property thành type Java. Jakarta Bean Validation kiểm tra những ràng buộc sau binding. Hai cơ chế không giống nhau.

### 5.2. Cách đăng ký type trong production

Ứng dụng thật có thể dùng:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DeliveryApplication {
}
~~~

Hoặc:

~~~java
@SpringBootApplication
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryApplication {
}
~~~

Hai cách này là các phương án thay thế.

Trong **ApplicationContextRunner**, để giữ scope test nhỏ nhất, ta thường dùng một **nested @Configuration** chỉ đăng ký type cụ thể qua **@EnableConfigurationProperties**.

## 6. Viết test đầu tiên với @EnableConfigurationProperties

Đây là ví dụ trung tâm của bài học, có thể dùng làm mẫu cho những bài test tiếp theo.

~~~java
package com.example.delivery;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class TestConfiguration {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(TestConfiguration.class)
                .withConfiguration(AutoConfigurations.of(
                        ValidationAutoConfiguration.class));

    @Test
    void bindsDeliveryProperties() {
        runner.withPropertyValues(
                "demo.delivery.endpoint=https://delivery.example.invalid",
                "demo.delivery.timeout=5s",
                "demo.delivery.retry.max-attempts=3",
                "demo.delivery.retry.backoff=250ms"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DeliveryProperties.class);

            DeliveryProperties properties =
                    context.getBean(DeliveryProperties.class);

            assertThat(properties.endpoint())
                    .isEqualTo("https://delivery.example.invalid");
            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(5));
            assertThat(properties.retry().maxAttempts())
                    .isEqualTo(3);
            assertThat(properties.retry().backoff())
                    .isEqualTo(Duration.ofMillis(250));
        });
    }
}
~~~

Giải thích chi tiết:

1. **TestConfiguration** là một Spring **@Configuration** có nhiệm vụ kích hoạt type cần test.
2. **@EnableConfigurationProperties(DeliveryProperties.class)** đăng ký configuration properties bean và infrastructure cần thiết.
3. **withUserConfiguration(TestConfiguration.class)** yêu cầu runner nạp class này.
4. **withConfiguration(AutoConfigurations.of(ValidationAutoConfiguration.class))** chủ động bổ sung validation auto-configuration để test tự mô tả những infrastructure đang sử dụng. Trong môi trường có Bean Validation implementation phù hợp, đây là một cách làm minh bạch khi cần kiểm thử validation.
5. **withPropertyValues(...)** cung cấp bốn key với giá trị thử nghiệm.
6. **run(...)** tạo context, khởi tạo bean và thực hiện assertion.
7. **hasSingleBean(...)** kiểm tra bean được đăng ký đúng và không bị trùng theo type.
8. **Duration.ofSeconds(5)** và **Duration.ofMillis(250)** xác nhận Spring Boot đã chuyển kiểu đúng, không chỉ giữ string.

**Không cần @SpringBootTest** trên class này. Đó là ưu thế của ApplicationContextRunner: test có scope nhỏ và chỉ khởi tạo thành phần được khai báo.

### 6.1. Vì sao không chỉ viết @ConfigurationProperties rồi getBean?

**@ConfigurationProperties** một mình không đảm bảo type trở thành bean của một ApplicationContextRunner tối thiểu. Bạn phải đăng ký type bằng **@EnableConfigurationProperties**, **@ConfigurationPropertiesScan** trong cấu hình được runner nạp, hoặc cơ chế tương đương.

Ví dụ sau không đủ:

~~~java
new ApplicationContextRunner()
    .withPropertyValues("demo.delivery.timeout=5s")
    .run(context -> context.getBean(DeliveryProperties.class));
~~~

Nếu không có TestConfiguration hoặc cách đăng ký phù hợp, context có thể không chứa DeliveryProperties. **Có property trong Environment không đồng nghĩa đã có configuration bean.**

## 7. withPropertyValues hoạt động như thế nào?

API chính:

~~~java
ApplicationContextRunner withPropertyValues(String... pairs)
~~~

Trong ví dụ:

~~~java
runner.withPropertyValues(
        "demo.delivery.timeout=5s",
        "demo.delivery.retry.max-attempts=3"
);
~~~

**String... pairs** có nghĩa một hoặc nhiều cặp property được đưa vào method. Cú pháp hỗ trợ dấu **=** và trong API còn hỗ trợ dấu **:** làm separator; với ví dụ chương trình, nên nhất quán dùng **=**.

Phân biệt:

~~~text
demo.delivery.timeout=5s
|-------------------| |-|
       key           value
~~~

Method thêm những giá trị này vào **Environment** của context runner. Nó không sửa file **application.yml**, không ghi biến môi trường của hệ điều hành và không thay đổi Java system properties thật của máy.

### 7.1. withPropertyValues trả về runner đã cấu hình

Giả sử:

~~~java
ApplicationContextRunner base =
        new ApplicationContextRunner();

ApplicationContextRunner fiveSeconds =
        base.withPropertyValues(
                "demo.delivery.timeout=5s");

ApplicationContextRunner tenSeconds =
        base.withPropertyValues(
                "demo.delivery.timeout=10s");
~~~

Mỗi runner là một bản cấu hình khác nhau để tạo context riêng. **withPropertyValues không khởi động context ngay lập tức**; context chỉ được tạo khi gọi **run(...)**.

Điều này rất thuận tiện cho nhiều test scenarios.

### 7.2. withPropertyValues có thể ghi đè key đã cấu hình trong runner

~~~java
ApplicationContextRunner base =
        new ApplicationContextRunner()
            .withPropertyValues(
                    "demo.delivery.timeout=5s");

base.withPropertyValues(
        "demo.delivery.timeout=10s"
).run(context -> {
    assertThat(context.getEnvironment()
            .getProperty("demo.delivery.timeout"))
            .isEqualTo("10s");
});
~~~

Cặp property được đưa vào ở lần cấu hình runner sau có thể override cùng key đã được khai báo trước đó trong runner.

**Đừng nhầm điều này với toàn bộ thứ tự ưu tiên runtime giữa CLI, env, profile và Config Data.** Đây là test setup cho Environment được tạo bởi runner.

### 7.3. Mỗi run tạo context riêng

~~~java
runner.withPropertyValues("app.mode=alpha")
        .run(context -> {
            assertThat(context.getEnvironment()
                    .getProperty("app.mode"))
                    .isEqualTo("alpha");
        });

runner.withPropertyValues("app.mode=beta")
        .run(context -> {
            assertThat(context.getEnvironment()
                    .getProperty("app.mode"))
                    .isEqualTo("beta");
        });
~~~

Hai callback làm việc với hai context riêng. Giá trị **alpha** ở lần trước không trở thành state của singleton bean trong lần sau.

Đây là lý do ApplicationContextRunner phù hợp với kiểm thử nhiều tổ hợp cấu hình liên tiếp.

## 8. Kiểm tra chuyển kiểu: String thành Duration, số và boolean

Trong test, các cặp như:

~~~text
demo.delivery.timeout=5s
demo.delivery.retry.max-attempts=3
~~~

là **chuỗi**, nhưng target type có:

~~~java
Duration timeout
int maxAttempts
~~~

Binder chuyển:

~~~text
"5s"  -> Duration.ofSeconds(5)
"3"   -> int 3
~~~

Nếu chỉ kiểm tra:

~~~java
context.getEnvironment()
        .getProperty("demo.delivery.timeout")
~~~

ta mới biết key có giá trị **5s**, chưa chứng minh việc bind vào **Duration** hoạt động.

**Assertion nên đọc bean**, ví dụ:

~~~java
DeliveryProperties p =
        context.getBean(DeliveryProperties.class);

assertThat(p.timeout())
        .isEqualTo(Duration.ofSeconds(5));
~~~

### 8.1. Các kiểu khác

Spring Boot Binder còn hỗ trợ các kiểu như:

- **Duration**: **500ms**, **5s**, **PT5S**.
- **DataSize**: **10MB**, **512KB**.
- **URI**: URL dưới dạng URI.
- **Boolean**: **true** hoặc **false** theo converter.
- **Integer/Long**: số phù hợp.
- **Enum**: một trong các giá trị enum theo conversion.
- **List/Map** và nested configuration object.

Không nên chỉ test tên property; nên kiểm tra **kiểu dữ liệu cuối cùng** nếu chính conversion là điều quan trọng với nghiệp vụ.

## 9. Test Duration theo nhiều định dạng

Một test parameterized hoặc nhiều test case giúp xác nhận cùng một Duration từ các cách biểu diễn khác nhau.

Ví dụ kiểm tra với base runner của mục 6:

~~~java
@Test
void understandsIsoDuration() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=PT5S",
            "demo.delivery.retry.max-attempts=2",
            "demo.delivery.retry.backoff=PT0.25S"
    ).run(context -> {
        assertThat(context).hasNotFailed();

        DeliveryProperties p =
                context.getBean(DeliveryProperties.class);

        assertThat(p.timeout())
                .isEqualTo(Duration.ofSeconds(5));
        assertThat(p.retry().backoff())
                .isEqualTo(Duration.ofMillis(250));
    });
}
~~~

Ví dụ khác:

~~~java
@Test
void understandsMilliseconds() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=5000ms",
            "demo.delivery.retry.max-attempts=2",
            "demo.delivery.retry.backoff=100ms"
    ).run(context -> {
        assertThat(context).hasNotFailed();

        DeliveryProperties p =
                context.getBean(DeliveryProperties.class);

        assertThat(p.timeout())
                .isEqualTo(Duration.ofMillis(5000));
    });
}
~~~

Khi test số không hậu tố:

~~~text
demo.delivery.timeout=5000
~~~

nó thường được hiểu là **5000 mili-giây** với cấu hình Duration mặc định của Spring Boot. Nếu field có **@DurationUnit(ChronoUnit.SECONDS)**, ý nghĩa bare number thay đổi.

**Đừng test cấu hình Duration bằng cách so sánh string "5000" với string "5s"**. Bind thành Duration rồi so sánh giá trị Java.

## 10. Test nested properties

DeliveryProperties có nested record:

~~~java
public record Retry(
        @Min(1) int maxAttempts,
        @NotNull Duration backoff) {
}
~~~

Tên canonical:

~~~text
demo.delivery.retry.max-attempts
demo.delivery.retry.backoff
~~~

Test:

~~~java
@Test
void bindsNestedRetrySettings() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=3s",
            "demo.delivery.retry.max-attempts=5",
            "demo.delivery.retry.backoff=750ms"
    ).run(context -> {
        assertThat(context).hasNotFailed();

        DeliveryProperties p =
                context.getBean(DeliveryProperties.class);

        assertThat(p.retry()).isNotNull();
        assertThat(p.retry().maxAttempts()).isEqualTo(5);
        assertThat(p.retry().backoff())
                .isEqualTo(Duration.ofMillis(750));
    });
}
~~~

**@Valid @NotNull Retry retry** yêu cầu nested object tồn tại và cho phép Bean Validation kiểm tra constraint bên trong.

Nếu trong test chỉ truyền **demo.delivery.retry.max-attempts** mà bỏ **retry.backoff**, nested record có thể được tạo nhưng field backoff thiếu; validation với **@NotNull** nên làm context fail khi cơ chế validation được cấu hình.

Đây là trường hợp tốt để kiểm thử vì nó chứng minh **nested validation**, không chỉ binding của parent.

## 11. Kiểm tra property bị thiếu

Một lỗi thường gặp ở production là config được cung cấp không đầy đủ. Test cần diễn đạt rõ đâu là trường bắt buộc.

Ví dụ thiếu endpoint:

~~~java
@Test
void rejectsMissingEndpoint() {
    runner.withPropertyValues(
            "demo.delivery.timeout=5s",
            "demo.delivery.retry.max-attempts=3",
            "demo.delivery.retry.backoff=250ms"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure()).isNotNull();
    });
}
~~~

**Điểm cần hiểu:** Binder có thể tạo record với endpoint null; Bean Validation thấy **@NotBlank** không được thỏa mãn và hạ tầng khởi tạo context báo lỗi.

Không nên assert cố định toàn bộ exception message, vì các chi tiết message, exception wrapping và format có thể khác giữa patch versions.

Nếu muốn kiểm tra class lỗi hoặc property path chính xác, có thể tìm root cause trong test một cách có chủ đích. Tuy nhiên, một test đơn giản nên tránh phụ thuộc mọi dòng stack trace.

### 11.1. Thiếu nested field

~~~java
@Test
void rejectsMissingRetryBackoff() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=5s",
            "demo.delivery.retry.max-attempts=3"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

Vì **retry.backoff** có **@NotNull**, và parent khai báo **@Valid**, nested validation có thể phát hiện giá trị thiếu.

### 11.2. Thiếu toàn bộ nested object

~~~java
@Test
void rejectsMissingRetryObject() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=5s"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

**@NotNull Retry retry** biểu diễn hợp đồng không được thiếu toàn bộ nhánh retry.

Nên có test cho cả “nhánh không tồn tại” và “nhánh có một vài field thiếu” nếu cấu hình thật có mức độ quan trọng cao.

## 12. Kiểm tra lỗi chuyển kiểu

Validation không đồng nghĩa với type conversion.

Một giá trị sai:

~~~text
demo.delivery.timeout=not-a-duration
~~~

không chuyển được sang Duration. Lỗi thường phát sinh ở bước bind/conversion, trước khi validation có thể kiểm tra đầy đủ object.

Test:

~~~java
@Test
void rejectsInvalidDuration() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=not-a-duration",
            "demo.delivery.retry.max-attempts=3",
            "demo.delivery.retry.backoff=250ms"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
                .isNotNull();
    });
}
~~~

Một trường hợp tương tự là:

~~~text
demo.delivery.retry.max-attempts=three
~~~

Nếu target là int, Binder có thể lỗi chuyển đổi.

**Phân biệt ba tình huống**:

| Tình huống | Lớp lỗi |
| --- | --- |
| Không có endpoint | Validation, @NotBlank |
| max-attempts bằng 0 | Validation, @Min(1) |
| timeout bằng "abc" | Conversion/binding |
| retry.backoff không có | Nested validation, @NotNull |
| Tên property sai khiến trường thiếu | Có thể biểu hiện thành validation lỗi thiếu |

Một test failure không nên đơn giản coi “context fail = validation đã hoạt động”. Hãy có test riêng cho conversion và validation để biết nguyên nhân đúng.

## 13. Kiểm tra ràng buộc về giá trị

Ví dụ:

~~~text
demo.delivery.retry.max-attempts=0
~~~

Giá trị **0** bind được vào kiểu int nhưng không thỏa **@Min(1)**.

~~~java
@Test
void rejectsZeroRetryAttempts() {
    runner.withPropertyValues(
            "demo.delivery.endpoint=https://delivery.example.invalid",
            "demo.delivery.timeout=5s",
            "demo.delivery.retry.max-attempts=0",
            "demo.delivery.retry.backoff=250ms"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure()).isNotNull();
    });
}
~~~

Đây là bài test nhằm xác nhận ràng buộc nghiệp vụ cho một field đã được chuyển kiểu thành công.

Nếu không có validation implementation trên classpath, hoặc **@Validated** không được áp dụng như dự kiến, trường hợp này có thể không fail. Chính test giúp phát hiện việc thiếu hạ tầng validation.

### 13.1. Kiểm tra quan hệ giữa nhiều field

Ví dụ business rule:

~~~text
connect-timeout < request-timeout
~~~

Hai Duration có thể đều hợp lệ riêng lẻ nhưng sai quan hệ khi **connect-timeout=8s**, **request-timeout=3s**. Để kiểm tra, cần custom class-level Bean Validation constraint hoặc phương thức **@AssertTrue** phù hợp trên model.

ApplicationContextRunner có thể cấp cả hai property và assert context fail. Nhưng bản thân runner không tự hiểu quan hệ nghiệp vụ; phải có validator trong class được bind.

## 14. Kiểm thử default value

Spring Boot constructor binding hỗ trợ **@DefaultValue**. Ví dụ một type riêng:

~~~java
package com.example.delivery;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.worker")
public record WorkerProperties(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("10s") Duration timeout,
        @DefaultValue("3") int maxAttempts) {
}
~~~

Cấu hình test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerDefaultsTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class Config {
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(Config.class);

    @Test
    void usesDeclaredDefaultsWhenOnePropertyProvided() {
        runner.withPropertyValues(
                "demo.worker.enabled=false"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            WorkerProperties p =
                    context.getBean(WorkerProperties.class);

            assertThat(p.enabled()).isFalse();
            assertThat(p.timeout())
                    .isEqualTo(java.time.Duration.ofSeconds(10));
            assertThat(p.maxAttempts()).isEqualTo(3);
        });
    }
}
~~~

Test cấp ít nhất một property cho prefix **demo.worker**, đồng thời bỏ **timeout** và **maxAttempts** để chứng minh **@DefaultValue** hoạt động.

### 14.1. Default trong Java không luôn là property trong Environment

Trong test trên, **WorkerProperties.timeout()** có thể là **Duration.ofSeconds(10)** dù test không cấp **demo.worker.timeout**.

Nhưng:

~~~java
context.getEnvironment()
        .getProperty("demo.worker.timeout")
~~~

không bắt buộc trả **10s**, bởi default khai báo trong configuration object không tự ghi ngược vào Environment.

Điều này rất quan trọng khi test:

- **Bean đã bind** phải được assertion qua getter/record accessor.
- **Environment** chỉ phản ánh property sources, không phản ánh mọi default của các Java object.

### 14.2. JavaBean default khác constructor @DefaultValue

Nếu một JavaBean mutable khởi tạo:

~~~java
private Duration timeout = Duration.ofSeconds(10);
~~~

thì binder theo setter binding có thể giữ default đó khi không có property tương ứng. Với record constructor binding, **@DefaultValue** là một cách thể hiện default rõ ràng.

Đừng dùng cả hai mô hình trong cùng class mà không hiểu khi nào object được tạo.

## 15. Kiểm thử relaxed binding

Spring Boot hỗ trợ **relaxed binding** cho **@ConfigurationProperties**. Tên Java camelCase:

~~~java
Duration connectTimeout;
~~~

thường tương ứng với key canonical:

~~~text
demo.client.connect-timeout
~~~

Một configuration record riêng:

~~~java
package com.example.delivery;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(Duration connectTimeout) {
}
~~~

Test:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
static class ClientConfig {
}

@Test
void bindsCanonicalKebabCase() {
    new ApplicationContextRunner()
        .withUserConfiguration(ClientConfig.class)
        .withPropertyValues("demo.client.connect-timeout=5s")
        .run(context -> {
            assertThat(context.getBean(ClientProperties.class)
                    .connectTimeout())
                    .isEqualTo(Duration.ofSeconds(5));
        });
}
~~~

Có thể kiểm tra thêm các dạng được Binder hỗ trợ trong property sources phù hợp, ví dụ camelCase hay underscore. Nhưng **nên viết key canonical lowercase kebab-case trong test và tài liệu**, để tránh hình thành convention thiếu nhất quán.

### 15.1. Test biến môi trường có thật không?

**withPropertyValues("DEMO_CLIENT_CONNECTTIMEOUT=5s")** không nhất thiết mô phỏng y hệt OS environment variable tên **DEMO_CLIENT_CONNECTTIMEOUT**. Nó đang cấp một property string cho test PropertySource.

Muốn kiểm thử **quy tắc ánh xạ từ một SystemEnvironmentPropertySource**, cần tạo nguồn property phù hợp và gắn vào Environment, hoặc dùng một integration test chạy với environment tương ứng.

Đừng dùng runner với cặp key uppercase rồi kết luận Docker/Kubernetes env mapping chắc chắn đúng trong mọi trường hợp.

## 16. Kiểm thử List và Map qua withPropertyValues

Khi cấu hình là List hoặc Map, các key có cấu trúc có thể được biểu diễn bằng indexed notation.

Ví dụ type:

~~~java
package com.example.delivery;

import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.routing")
public record RoutingProperties(
        List<Endpoint> endpoints,
        Map<String, Integer> limits) {

    public record Endpoint(String name, URI url) {
    }
}
~~~

Cấu hình tương đương:

~~~yaml
demo:
  routing:
    endpoints:
      - name: primary
        url: "https://primary.example.invalid"
      - name: backup
        url: "https://backup.example.invalid"
    limits:
      asia: 100
      europe: 150
~~~

Test:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RoutingProperties.class)
static class RoutingConfig {
}

@Test
void bindsListAndMap() {
    new ApplicationContextRunner()
        .withUserConfiguration(RoutingConfig.class)
        .withPropertyValues(
            "demo.routing.endpoints[0].name=primary",
            "demo.routing.endpoints[0].url=https://primary.example.invalid",
            "demo.routing.endpoints[1].name=backup",
            "demo.routing.endpoints[1].url=https://backup.example.invalid",
            "demo.routing.limits.asia=100",
            "demo.routing.limits.europe=150"
        )
        .run(context -> {
            assertThat(context).hasNotFailed();

            RoutingProperties p =
                    context.getBean(RoutingProperties.class);

            assertThat(p.endpoints()).hasSize(2);
            assertThat(p.endpoints().get(0).name())
                    .isEqualTo("primary");
            assertThat(p.endpoints().get(1).url())
                    .isEqualTo(java.net.URI.create(
                            "https://backup.example.invalid"));
            assertThat(p.limits().get("asia"))
                    .isEqualTo(100);
            assertThat(p.limits().get("europe"))
                    .isEqualTo(150);
        });
}
~~~

Điểm cần hiểu:

- **endpoints[0]** và **endpoints[1]** cho Binder biết thứ tự phần tử.
- **limits.asia** và **limits.europe** trở thành các entry của Map.
- Không cần một file YAML thật; với mục đích test mapping, tập key đã làm phẳng thường đủ.

### 16.1. Giới hạn với List merging

Trong runtime Spring Boot, nếu cùng một List được khai báo ở các nguồn có độ ưu tiên khác nhau, nguồn ưu tiên cao hơn có thể **thay toàn bộ List** thay vì merge từng phần tử.

Một runner với một nguồn **withPropertyValues** là test tuyệt vời cho cấu trúc List, nhưng không chứng minh đầy đủ mọi trường hợp merging giữa **application.yml**, profile files và OS env. Muốn test precedence nhiều nguồn, cần xây test với những PropertySource thích hợp hoặc integration test.

## 17. Kiểm thử bean điều kiện theo property

Ngoài bản thân configuration bean, nhiều ứng dụng có các feature được bật/tắt bằng property:

~~~text
demo.feature.enabled=true
~~~

Trong auto-configuration, **@ConditionalOnProperty** là một cơ chế thường dùng.

Ví dụ:

~~~java
package com.example.delivery;

public final class FeatureWorker {
}
~~~

Configuration:

~~~java
package com.example.delivery;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true")
    public FeatureWorker featureWorker() {
        return new FeatureWorker();
    }
}
~~~

Test:

~~~java
package com.example.delivery;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withUserConfiguration(FeatureConfiguration.class);

    @Test
    void createsBeanWhenEnabled() {
        runner.withPropertyValues(
                "demo.feature.enabled=true"
        ).run(context -> {
            assertThat(context).hasSingleBean(FeatureWorker.class);
        });
    }

    @Test
    void skipsBeanWhenDisabled() {
        runner.withPropertyValues(
                "demo.feature.enabled=false"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(FeatureWorker.class);
        });
    }

    @Test
    void skipsBeanWhenPropertyMissing() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(FeatureWorker.class);
        });
    }
}
~~~

**Điểm cần hiểu:** runner hữu ích cho cả **binding** lẫn **conditional bean registration**. Nó kiểm tra trực tiếp ApplicationContext có chứa bean hay không, không chỉ Environment có chứa giá trị nào.

### 17.1. Default của @ConditionalOnProperty

Khi **matchIfMissing** không được bật, một property vắng mặt thường khiến điều kiện không match trong ví dụ trên. Nếu use case yêu cầu enabled mặc định, có thể khai báo **matchIfMissing=true** và viết test tương ứng.

Đừng lẫn giá trị mặc định bên trong **@ConfigurationProperties** Java object với điều kiện **@ConditionalOnProperty** đọc từ Environment. Một default chỉ tồn tại trong object không tự trở thành key trong Environment.

## 18. Không phải lúc nào test cũng cần @SpringBootTest

So sánh các công cụ:

| Công cụ | Phạm vi | Khi nào dùng |
| --- | --- | --- |
| **ApplicationContextRunner** | Context nhỏ do test chỉ định, không web | Kiểm tra config bean, auto-configuration, conditional bean, conversion |
| **WebApplicationContextRunner** | Mô phỏng Servlet web application context | Auto-configuration chỉ kích hoạt trong Servlet context |
| **ReactiveWebApplicationContextRunner** | Mô phỏng reactive web context | Auto-configuration chỉ dành cho WebFlux/reactive |
| **@SpringBootTest** | Khởi tạo application context theo Spring Boot Test | Integration test liên quan nhiều bean, profile/Config Data và wiring thực tế |
| **Unit test Java thuần** | Không khởi tạo Spring context | Kiểm tra logic thuần của validator hoặc object |

**ApplicationContextRunner** không có ý định thay thế toàn bộ end-to-end testing. Nó đặc biệt hữu ích khi một test có thể mô tả chính xác những bean/properties cần thiết.

### 18.1. Khi nào nên dùng @SpringBootTest?

Dùng **@SpringBootTest** nếu bạn thực sự cần:

- Kiểm tra auto-configuration và component scan của ứng dụng thật.
- Tải Config Data/profile-specific files qua vòng đời SpringApplication đầy đủ.
- Xác minh dependency wiring giữa nhiều subsystem.
- Kết hợp Testcontainers, database hoặc network mock có cấu hình phức tạp.
- Kiểm tra một ứng dụng web thật với server phù hợp.

Một test runner nhỏ không chứng minh toàn bộ YAML trong repository đã được nạp đúng theo production launch process.

### 18.2. Test native image

Theo tài liệu Spring Boot về testing auto-configuration, **ApplicationContextRunner không hoạt động khi chạy các test trong native image**. Điều này không đồng nghĩa application configuration properties không thể dùng trong native application; chỉ là giới hạn của test utility theo tài liệu.

Khi dùng Spring AOT/native workflow, cần chọn chiến lược test phù hợp, không giả định runner kiểm tra được mọi behavior của native image.

## 19. Tránh hiểu nhầm nguồn Config Data khi dùng runner

Một ví dụ có thể gây nhầm:

~~~java
new ApplicationContextRunner()
    .withPropertyValues("spring.profiles.active=prod")
    .run(context -> {
        // Không tự suy ra application-prod.yml chắc chắn đã được nạp
    });
~~~

Chỉ thêm property **spring.profiles.active=prod** vào Environment của một context test tối thiểu **không đồng nghĩa đã khởi chạy toàn bộ Config Data bootstrap** của SpringApplication.

Nếu test thực sự cần xác minh **application-prod.yml**, **spring.config.import** hoặc location precedence, nên sử dụng:

1. **@SpringBootTest** với profile phù hợp; hoặc
2. Test harness chủ động kích hoạt Config Data infrastructure tương ứng.

Không nên lấy một ApplicationContextRunner trống rồi assert rằng đã mô phỏng đầy đủ cách Spring Boot tìm file **application.yml** và profile files.

Đây là ranh giới quan trọng giữa **test property binding** và **test bootstrap configuration**.

### 19.1. withPropertyValues cũng không tạo OS environment thật

Khi gọi:

~~~java
.withPropertyValues("demo.delivery.timeout=5s")
~~~

ta tạo property cho test context. Nó không set biến **DEMO_DELIVERY_TIMEOUT** cho hệ điều hành và không đổi lệnh launch của process.

Muốn kiểm tra biến môi trường thực hoặc file secret mount thật, cần integration test/launch environment phù hợp.

## 20. Test các nguồn ghi đè theo cách có kiểm soát

Giả sử muốn chứng minh test có thể override một default:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(Config.class)
            .withPropertyValues("demo.worker.timeout=10s");
~~~

Một test:

~~~java
@Test
void overridesTimeoutForScenario() {
    runner.withPropertyValues(
            "demo.worker.timeout=3s"
    ).run(context -> {
        WorkerProperties p =
                context.getBean(WorkerProperties.class);

        assertThat(p.timeout())
                .isEqualTo(Duration.ofSeconds(3));
    });
}
~~~

Điều này hữu ích khi nhiều tests dùng chung những giá trị mặc định, nhưng mỗi scenario cần một override.

**Không sử dụng System.setProperty(...) trong nhiều test song song** nếu chỉ muốn cấp property cho một runner; nó tạo shared state ở cấp JVM. **withPropertyValues(...)** thường an toàn và rõ scope hơn.

### 20.1. withSystemProperties dùng khi nào?

ApplicationContextRunner có **withSystemProperties(...)** để thiết lập Java system properties cho thời gian chạy context rồi phục hồi trạng thái sau đó.

Dùng khi behavior cần kiểm tra thực sự phụ thuộc System properties và không thể được mô phỏng đầy đủ bằng test property source.

Tuy nhiên, do System properties là global state của JVM, thận trọng với các test chạy song song. Đối với binding thông thường, **withPropertyValues** là lựa chọn mặc định dễ kiểm soát.

## 21. Kiểm tra failure cụ thể mà không làm test giòn

Lỗi cấu hình có thể được wrap trong nhiều exception:

~~~text
Context startup failure
  -> bean creation / binding failure
     -> conversion failure hoặc validation failure
~~~

Nếu test chỉ cần bảo đảm ứng dụng fail-fast với cấu hình sai:

~~~java
runner.withPropertyValues(
        "demo.delivery.endpoint=https://delivery.example.invalid",
        "demo.delivery.timeout=bad",
        "demo.delivery.retry.max-attempts=3",
        "demo.delivery.retry.backoff=250ms"
).run(context -> {
    assertThat(context).hasFailed();
    assertThat(context.getStartupFailure()).isNotNull();
});
~~~

Nếu test cần chứng minh cụ thể lỗi thuộc trường timeout, có thể kiểm tra stack trace/cause với mức chi tiết hợp lý. Tránh assert toàn bộ message chứa tên các class nội bộ, đường file hoặc dấu câu được Spring Boot thay đổi qua patch version.

### 21.1. Khi failure không phải do cấu hình

Một context có thể fail vì nhiều nguyên nhân:

- Bean chưa được đăng ký.
- Thiếu dependency của bean nghiệp vụ.
- Điều kiện auto-configuration không thỏa mãn.
- Validation implementation chưa có.
- ConstraintValidator bị lỗi.
- Giá trị cấu hình sai kiểu.
- Vòng phụ thuộc hoặc bean definition conflict.

Vì vậy, nếu một test có nhiệm vụ chứng minh **@Min(1)** hoạt động, đừng vô tình để test fail vì một datasource thiếu URL. Tạo context càng nhỏ càng tốt và xác định root cause khi cần.

Một test được thiết kế tốt nên fail khi code cấu hình sai, không phải khi một dịch vụ bên ngoài đang tạm thời không truy cập được.

## 22. Test bean JavaBean có setter

Không phải project nào cũng sử dụng record. Với cấu hình mutable JavaBean:

~~~java
package com.example.delivery;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.cache")
public class CacheProperties {

    private boolean enabled = true;
    private Duration ttl = Duration.ofMinutes(5);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTtl() {
        return ttl;
    }

    public void setTtl(Duration ttl) {
        this.ttl = ttl;
    }
}
~~~

Test configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CacheProperties.class)
static class CacheConfig {
}
~~~

Test:

~~~java
@Test
void bindsJavaBeanAndRetainsDefault() {
    new ApplicationContextRunner()
        .withUserConfiguration(CacheConfig.class)
        .withPropertyValues("demo.cache.enabled=false")
        .run(context -> {
            assertThat(context).hasNotFailed();

            CacheProperties p = context.getBean(CacheProperties.class);

            assertThat(p.isEnabled()).isFalse();
            assertThat(p.getTtl())
                    .isEqualTo(Duration.ofMinutes(5));
        });
}
~~~

Ở đây, ttl giữ default được khởi tạo trong JavaBean. Đây là một cách khác với **@DefaultValue** trên constructor parameter của record.

Test cũng chứng minh **setter-based binding** hoạt động, không chỉ constructor binding.

## 23. Test property không rõ tên và các binding flags

Trong một số trường hợp, cấu hình chứa key gõ sai nhưng Binder không bắt buộc báo lỗi nếu **@ConfigurationProperties** vẫn cho phép unknown fields.

Ví dụ người dùng cấp:

~~~text
demo.delivery.time-out=5s
~~~

trong khi target cần **timeout**.

Nếu có **@NotNull Duration timeout**, lỗi có thể xuất hiện vì timeout vẫn null. Nhưng với field tùy chọn có default, một key sai có thể bị bỏ qua mà không có lỗi rõ ràng.

Spring Boot cung cấp các tùy chọn trên **@ConfigurationProperties**, trong đó **ignoreUnknownFields** mặc định true và **ignoreInvalidFields** mặc định false trong dòng Spring Boot liên quan.

Khi thiết kế configuration API:

- Giữ property names canonical và dễ đọc.
- Test những key quan trọng có được bind đúng.
- Dùng validation cho field bắt buộc.
- Cân nhắc strict binding/unknown fields nếu module yêu cầu; khi thay đổi policy, test cả trường hợp key lạ.
- Không nghĩ mọi typo đều chắc chắn gây failure trong mọi cấu hình.

### 23.1. Kiểm tra tiền tố sai

Giả sử record:

~~~java
@ConfigurationProperties(prefix = "demo.delivery")
~~~

nhưng test chỉ cấp:

~~~text
demo.deliveries.endpoint=...
demo.deliveries.timeout=...
~~~

Thì đây là hai prefix khác nhau. Nếu không có dữ liệu nào dưới **demo.delivery**, bean được đăng ký vẫn có thể được tạo theo default/null semantics của type, rồi validation quyết định pass/fail.

**Đừng suy ra Binder tự hiểu delivery và deliveries là alias**. Relaxed binding xử lý biến thể cách viết trong phạm vi quy tắc, không tự sửa những từ có nghĩa khác nhau.

## 24. Test những giá trị đặc biệt: zero, âm và ranh giới

Một Duration có thể parse được nhưng không phù hợp nghiệp vụ:

~~~text
demo.delivery.timeout=0s
demo.delivery.timeout=-5s
~~~

**@NotNull** chỉ kiểm tra sự hiện diện, không cấm zero hoặc số âm.

Nếu hợp đồng yêu cầu timeout dương, cần constraint phù hợp, ví dụ custom Bean Validation cho Duration hoặc class-level method/validator.

Khi đã có constraint đó, ApplicationContextRunner có thể kiểm tra:

~~~text
timeout=1ms  -> pass nếu min=1ms
timeout=0s   -> fail
timeout=-1s  -> fail
timeout=24h  -> có thể fail nếu có max limit
~~~

Không gắn **@Min(1)** hoặc **@Positive** lên Duration rồi mặc định provider nào cũng hỗ trợ. Các annotation số chuẩn không nhất thiết có validator cho Duration.

Tương tự với retry count, nên test:

~~~text
max-attempts=1 -> pass
max-attempts=0 -> fail
max-attempts=3 -> pass
max-attempts=-1 -> fail
~~~

Các biên này mang nhiều giá trị kiểm thử hơn việc chỉ test một cấu hình “đẹp”.

## 25. Dùng @AssertTrue để kiểm tra quan hệ cross-field

Ví dụ một configuration type khác:

~~~java
package com.example.delivery;

import java.time.Duration;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.timeout")
public record TimeoutRangeProperties(
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout) {

    @AssertTrue(message =
        "request-timeout must exceed connect-timeout")
    public boolean isTimeoutOrderValid() {
        if (connectTimeout == null || requestTimeout == null) {
            return true;
        }
        return requestTimeout.compareTo(connectTimeout) > 0;
    }
}
~~~

Test:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(TimeoutRangeProperties.class)
static class TimeoutConfig {
}

@Test
void rejectsInvalidTimeoutOrder() {
    new ApplicationContextRunner()
        .withUserConfiguration(TimeoutConfig.class)
        .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
        .withPropertyValues(
                "demo.timeout.connect-timeout=8s",
                "demo.timeout.request-timeout=3s")
        .run(context -> {
            assertThat(context).hasFailed();
        });
}
~~~

Đây là một quy tắc nghiệp vụ **minh họa**. Không phải mọi HTTP client đều yêu cầu request timeout lớn hơn connect timeout, vì semantic của các loại timeout tùy thư viện. Chỉ tạo constraint khi hợp đồng của hệ thống thực sự yêu cầu.

Nếu cần gắn lỗi vào một field cụ thể thay vì property boolean suy ra, có thể viết custom **class-level Jakarta Bean Validation constraint**.

## 26. Tổ chức nhiều test dùng một base runner

Một pattern thường dùng:

~~~java
class PaymentConfigTests {

    private final ApplicationContextRunner baseRunner =
            new ApplicationContextRunner()
                .withUserConfiguration(PaymentTestConfig.class);

    @Test
    void scenarioA() {
        baseRunner.withPropertyValues(
                "demo.payment.enabled=true"
        ).run(context -> {
            // asserts riêng scenario A
        });
    }

    @Test
    void scenarioB() {
        baseRunner.withPropertyValues(
                "demo.payment.enabled=false"
        ).run(context -> {
            // asserts riêng scenario B
        });
    }
}
~~~

Ý nghĩa:

- **baseRunner** biểu diễn các bean/configuration classes chung.
- Mỗi test bổ sung property scenario riêng.
- Mỗi **run(...)** tạo context khác và đóng sau khi callback kết thúc.
- Không phải sửa toàn cục System properties hay Spring profile của JVM.

**Điểm cần tránh:** trong một test, đừng cấp nhiều biến thể tên cho cùng property với những giá trị mâu thuẫn rồi dựa vào precedence khó nhìn. Nên giữ test dữ liệu rõ ràng, mỗi key có một giá trị cuối mong đợi.

### 26.1. Test failure phải thuộc chính scenario

Ví dụ test thiếu endpoint cần cấp **timeout** và nested retry đủ, để failure được gây ra do endpoint thiếu. Nếu thiếu cả timeout và retry, test vẫn fail nhưng không chứng minh riêng @NotBlank endpoint.

Một test rõ mục đích sẽ dễ duy trì và tìm nguyên nhân khi refactor.

## 27. Khả năng xem điều kiện auto-configuration

Với một module nhiều **@ConditionalOn...**, một test có thể pass hoặc fail do điều kiện không match. Spring Boot cung cấp **ConditionEvaluationReport** và các tiện ích logging trong các test auto-configuration để quan sát điều kiện.

Có thể dùng:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Rồi:

~~~java
new ApplicationContextRunner()
    .withInitializer(
        ConditionEvaluationReportLoggingListener
            .forLogLevel(LogLevel.INFO))
    .withUserConfiguration(FeatureConfiguration.class)
    .withPropertyValues("demo.feature.enabled=true")
    .run(context -> {
        assertThat(context).hasSingleBean(FeatureWorker.class);
    });
~~~

Mục đích là có thêm tín hiệu khi một bean không được tạo. Không cần bật logging report cho tất cả test; chỉ dùng khi chẩn đoán hoặc kiểm tra auto-configuration phức tạp.

### 27.1. ConditionEvaluationReport không thay assertion

Việc report có dòng “matched” hoặc “did not match” chưa đủ để chứng minh wiring đúng. Test vẫn nên assert **bean có tồn tại không**, **giá trị đã bind** và **trạng thái context**.

## 28. Khi nào cần test end-to-end ngoài runner?

Một configuration bean có thể bind tốt với test property values nhưng vẫn lỗi ở production vì:

- File **application-prod.yml** không được đóng gói hoặc không nằm ở path mong đợi.
- Namespace ConfigMap/Secret không khớp với tên env.
- Secret file không được mount vào container.
- **SPRING_CONFIG_IMPORT** hoặc **spring.config.additional-location** được cấp quá muộn.
- Profile khác với profile deployment đang dùng.
- Source precedence khiến một env override giá trị theo profile.
- Một component chỉ khởi tạo khi web context tồn tại.
- Một auto-configuration phụ thuộc dependency hoặc classpath thật.
- Chế độ AOT/native có hành vi riêng.

Đây là những trường hợp nên bổ sung:

1. Integration test dùng **@SpringBootTest** và profile phù hợp.
2. Smoke test khi deploy trên môi trường thật.
3. Contract test cấu hình được platform cấp.
4. Security tests để không lộ secret qua Actuator/log.
5. Readiness probe và kiểm tra dependency connectivity.

**ApplicationContextRunner.withPropertyValues** rất tốt để kiểm tra **binding logic**, nhưng không thay kiểm tra đường đi từ Secret/ConfigMap/CLI đến process Java.

## 29. Những lỗi hay gặp

### 29.1. Quên withUserConfiguration hoặc @EnableConfigurationProperties

Runner có property nhưng không có bean đích. Dùng **withUserConfiguration(TestConfiguration.class)** và **@EnableConfigurationProperties**.

### 29.2. Dùng @SpringBootTest chỉ để kiểm tra một Duration

Test có thể khởi tạo quá nhiều bean, chậm và phụ thuộc bên ngoài. Với một configuration type đơn giản, runner thường gọn hơn.

### 29.3. Gọi withPropertyValues mà không gọi run

**withPropertyValues** chỉ cấu hình runner. Phải gọi **run(context -> ...)** để tạo context và thực hiện assertion.

### 29.4. Giả định withPropertyValues thay đổi file application.yml

Method thêm key cho test Environment; nó không sửa file Config Data trên đĩa.

### 29.5. Giả định @Validated luôn hoạt động dù thiếu validation provider

Cần implementation Jakarta Bean Validation và infrastructure tương ứng. Sử dụng starter-validation và kiểm thử failure rõ ràng.

### 29.6. Gán nguyên nhân sai cho hasFailed()

Context có thể fail do thiếu bean khác hoặc conversion, không phải do constraint đang kiểm tra. Giữ context nhỏ và cấp đủ các trường khác.

### 29.7. Test Environment thay vì bean đã bind

Đọc **getProperty("demo.delivery.timeout")** chỉ cho biết giá trị chuỗi trong Environment; chưa chứng minh Binder chuyển thành Duration.

### 29.8. Dùng key không canonical

Nên thống nhất **demo.delivery.retry.max-attempts** thay vì tùy tiện mix camelCase/underscore.

### 29.9. Giả định với runner có active profile là Config Data được nạp

Runner tối thiểu không đồng nghĩa startup SpringApplication đầy đủ. Muốn kiểm tra file/profile, dùng test phù hợp.

### 29.10. Test list merge bằng một PropertySource duy nhất

List merging/replacement giữa nhiều nguồn có precedence không thể được kết luận đầy đủ từ một nguồn withPropertyValues.

### 29.11. Chia sẻ state mutable giữa các test

Tránh dùng mutable static maps hoặc System.setProperty không phục hồi. Tận dụng runner bất biến và context độc lập.

### 29.12. Không đóng context khi tự tạo bằng tay

Ưu điểm của **run(...)** là context được đóng sau callback. Nếu viết harness thủ công khác, phải quản lý vòng đời tài nguyên.

### 29.13. So sánh nguyên văn toàn bộ exception message

Các wrapper và message có thể thay đổi giữa patch versions. Assert lỗi ở mức đủ ổn định cho mục đích test.

### 29.14. Quên kiểm tra nested validation

Parent có @Validated chưa chắc constraints trong nested object được cascade nếu thiếu **@Valid**.

### 29.15. Coi default của Java record là property trong Environment

Default trong object không tự viết ngược thành property source. Assert bằng accessor của bean.

### 29.16. Lộ secret qua test log

Không in record chứa password/apiKey hoặc toàn bộ Environment. Dùng token giả và log tên key, không log giá trị nhạy cảm.

## 30. Bài thực hành

### Bài A — binding thành công

1. Tạo **DeliveryProperties** như mục 5.
2. Tạo **TestConfiguration** với @EnableConfigurationProperties.
3. Tạo **ApplicationContextRunner**.
4. Cấp endpoint, timeout, retry bằng **withPropertyValues**.
5. Assert hasSingleBean và các accessor trả giá trị đúng.

**Mục tiêu:** chứng minh binding xảy ra và các type được convert.

### Bài B — thiếu property

1. Chạy test không cấp **demo.delivery.endpoint**.
2. Giữ tất cả field khác hợp lệ.
3. Assert context fail với validation.
4. Bổ sung endpoint, chạy lại và assert pass.

**Mục tiêu:** kiểm tra contract bắt buộc.

### Bài C — lỗi conversion

1. Đổi timeout thành **nonsense**.
2. Chạy runner.
3. Assert hasFailed.
4. Đổi thành **500ms**, chạy lại và so sánh Duration.

**Mục tiêu:** phân biệt lỗi cú pháp với lỗi ràng buộc nghiệp vụ.

### Bài D — nested validation

1. Đặt retry.max-attempts=0.
2. Chạy context với tất cả field khác hợp lệ.
3. Assert fail.
4. Đặt max-attempts=1 rồi kiểm tra pass.

**Mục tiêu:** xác nhận @Valid cascade vào nested type.

### Bài E — default value

1. Tạo WorkerProperties với **@DefaultValue("10s")**.
2. Chỉ cấp **demo.worker.enabled=false**.
3. Assert timeout bằng Duration.ofSeconds(10).
4. So sánh với Environment.getProperty("demo.worker.timeout").

**Mục tiêu:** hiểu default của object khác nguồn Env.

### Bài F — List và Map

1. Tạo RoutingProperties.
2. Cấp endpoints[0], endpoints[1] và limits.asia/europe.
3. Assert size, thứ tự và map entries.
4. Thử bỏ một field của phần tử nếu có validation và quan sát failure.

**Mục tiêu:** test object binding cho dữ liệu có cấu trúc.

### Bài G — conditional bean

1. Tạo FeatureConfiguration với @ConditionalOnProperty.
2. Chạy với enabled=true.
3. Chạy với enabled=false.
4. Chạy không có key.
5. Assert bean tồn tại đúng khi cần.

**Mục tiêu:** kiểm thử registration dựa trên cấu hình, không chỉ giá trị field.

### Bài H — giới hạn của runner

1. Tạo **application-prod.yml** với một key riêng.
2. Chạy runner chỉ với **spring.profiles.active=prod**.
3. Quan sát rằng test không thể mặc định dựa vào quá trình Config Data của SpringApplication.
4. Viết integration test phù hợp để nạp profile thực.
5. So sánh phạm vi hai loại test.

**Mục tiêu:** chọn đúng công cụ cho đúng tầng hệ thống.

## 31. Checklist cho một test configuration bean

Một test tốt nên trả lời:

- Đã đăng ký type đích bằng **@EnableConfigurationProperties** hoặc cơ chế tương đương chưa?
- Có cần ValidationAutoConfiguration hoặc Bean Validation implementation không?
- Các key truyền cho **withPropertyValues** có canonical, chính tả đúng không?
- Các giá trị test có hợp lý và độc lập với máy developer không?
- Assertion có kiểm tra bean tồn tại và được bind thành type Java đúng không?
- Có test missing required property không?
- Có test conversion failure không?
- Có test @NotBlank, @Min hoặc constraint quan trọng không?
- Có test nested @Valid không?
- Có test default value và override không?
- Có kiểm tra List/Map nếu model có collection không?
- Có phân biệt Condition evaluation với configuration binding không?
- Có tránh assert toàn bộ error message giòn theo patch version không?
- Có tránh file, network, database hoặc secret thật không cần thiết không?
- Có xác định rõ phần nào runner không mô phỏng như profile Config Data không?
- Có integration test riêng cho những điểm runtime/production quan trọng không?

## 32. Tổng kết

- **ApplicationContextRunner** tạo một **non-web Spring ApplicationContext** nhỏ, dễ điều khiển trong test.
- **withPropertyValues("key=value", ...)** bổ sung Environment property pairs cho một scenario.
- **run(context -> ...)** khởi tạo context, cho phép assertion và tự đóng context sau callback.
- **@EnableConfigurationProperties** giúp đăng ký configuration bean cần test mà không nạp cả ứng dụng.
- Assertion nên kiểm tra chính **configuration bean**, không chỉ string property trong Environment.
- **Duration**, các giá trị số, boolean và nested object được Spring Boot Binder chuyển kiểu theo target model.
- **@Validated**, **@Valid** và Jakarta Bean Validation giúp fail-fast khi cấu hình thiếu hoặc sai ràng buộc.
- **hasNotFailed()**, **hasSingleBean()**, **hasFailed()** và **getStartupFailure()** là những kiểm tra hữu ích.
- Dùng một base runner cho nhiều scenario và override property riêng của từng test.
- **List/Map** có thể kiểm tra bằng các key indexed/structured được cấp trực tiếp.
- **@ConditionalOnProperty** có thể được kiểm tra bằng sự tồn tại hoặc vắng mặt của bean.
- **withPropertyValues** không tự nạp Config Data theo profile, không set OS env thật và không thay thế toàn bộ integration test.
- Khi cần chứng minh application.yml, profile, secret mount, CLI hoặc container deployment hoạt động, bổ sung test ở tầng integration/runtime phù hợp.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 API — **ApplicationContextRunner**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 API — **AbstractApplicationContextRunner** và **withPropertyValues**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html
- Spring Boot 3.3 — **Testing Auto-configuration**: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — **Externalized Configuration**, Type-safe Configuration Properties, Binding, Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — **Testing**: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
