# Kiểm thử binding, validation và giá trị mặc định của configuration properties

## 1. Vấn đề: configuration là một hợp đồng của auto-configuration

Trong Spring Boot, một thư viện có thể đọc cấu hình từ `application.properties`, YAML, environment variables và các property sources khác rồi chuyển thành đối tượng Java qua `@ConfigurationProperties`. Bean được tạo bởi `@AutoConfiguration` thường sử dụng đối tượng ấy để đặt URL, timeout, retry, kích thước pool, tính năng bật/tắt và các lựa chọn vận hành.

Nếu kiểm tra không đầy đủ, lỗi có thể chỉ xuất hiện sau khi deploy: một typo khiến giá trị rơi về mặc định; `500ms` bind nhầm thành 500 giây; một nested setting không được validate; feature được đánh dấu enabled=true trong JavaBean nhưng conditional bean không được tạo; hoặc auto-configuration ghi đè bean mà ứng dụng đã tự định nghĩa.

**Ba câu hỏi riêng phải được kiểm thử:**

1. **Binding:** key được ánh xạ sang đúng Java property và chuyển thành đúng kiểu chưa?
2. **Validation:** missing, blank, sai kiểu và out-of-range có làm context fail theo hợp đồng không?
3. **Defaults/conditions:** khi thiếu key, các giá trị mặc định có đúng không, có bị override được không, và bean auto-config có tạo/back off đúng không?

Một test như `assertThat(new ClientProperties().getTimeout()).isEqualTo(Duration.ofSeconds(3))` chỉ chứng minh field initializer Java; nó **không** chứng minh Spring Boot Binder, Jakarta Bean Validation và auto-configuration hoạt động.

### Mục tiêu học

Sau bài này, bạn có thể dùng `ApplicationContextRunner` để kiểm tra binding, validation và defaults trong một auto-configuration Spring Boot; phân biệt `BindException` với `BindValidationException`; test JavaBean/record defaults, relaxed binding, nested properties, `@ConditionalOnProperty` và `@ConditionalOnMissingBean`; hiểu hạn chế của ContextRunner so với `@SpringBootTest`; có một ví dụ Java 17+ Spring Boot 3.5.x gồm **18 JUnit Jupiter test methods**.

**Phiên bản mẫu:** Java 17+, Spring Boot **3.5.16**, Spring Framework 6.x, Jakarta Bean Validation, JUnit Jupiter và AssertJ. Spring Boot 4.x thay đổi một số test starters/packages nên phải đối chiếu theo phiên bản, không sao chép imports 3.5 vô điều kiện.

## 2. Luồng cấu hình từ nguồn đến bean

```text
 application.properties / application.yaml / OS environment
          / Java system properties / CLI arguments
                            |
                            v
                Spring Environment
                  PropertySources
                            |
                            v
                 Spring Boot Binder
                 relaxed key matching
                 + type conversion
                            |
                            v
               @ConfigurationProperties
              JavaBean / record / constructor
                            |
                            v
              @Validated + @Valid cascade
                            |
                   +--------+--------+
                   |                 |
                 invalid           valid
                   |                 |
             startup failure        v
                              @AutoConfiguration
                              @Conditional...
                                    |
                                    v
                             application bean
```

**Chú ý ranh giới:**

- Binder chuyển text thành kiểu như `Duration`, `URI`, `int`, `boolean` và collections.
- Validation kiểm tra ngữ nghĩa do developer khai báo (ví dụ retry count nằm trong 1–8).
- Conditional annotations thường đọc `Environment` hoặc bean definitions, không đọc field initializers trực tiếp.
- Việc context start thành công **không** chứng minh real HTTP client/network hoặc database được vận hành đúng; nó mới chứng minh cấu hình/wiring trong phạm vi context.
- Full SpringApplication còn có ConfigData/profile loading mà `ApplicationContextRunner` không tự tái hiện đầy đủ.

### 2.1. Ma trận tối thiểu

| Loại | Input | Kỳ vọng |
|---|---|---|
| Default | Chỉ cung cấp key bắt buộc | Bean valid, defaults đúng |
| Override | `timeout=750ms` | `Duration.ofMillis(750)` |
| Relaxed binding | `maxAttempts=4` | Java field `maxAttempts=4` |
| Nested | `pool.size=12` | Nested object nhận 12 |
| Validation | `max-attempts=0` | Startup fail |
| Conversion | `max-attempts=banana` | Startup fail vì không convert được |
| Required | Bỏ `service-name` | Startup fail với @NotBlank |
| Blank | `service-name=   ` | Startup fail với @NotBlank |
| Disabled | `enabled=false` | Properties vẫn bind, conditional client vắng |
| User override | User định nghĩa bean client | Auto-configuration back off |
| Unknown key | Typo, strict mode | Startup fail thay vì lặng lẽ dùng default |

## 3. @ConfigurationProperties, @Value và relaxed binding

`@ConfigurationProperties(prefix="demo.client")` đăng ký một nhóm setting type-safe. Nó phù hợp với starter/library có nhiều key liên quan. `@Value` hữu ích với giá trị đơn lẻ nhưng không cung cấp cùng khả năng nested type-safe binding, generated metadata và relaxed binding như một properties type.

Ví dụ:

```properties
demo.client.service-name=orders
demo.client.timeout=750ms
demo.client.max-attempts=4
demo.client.pool.size=12
demo.client.tags=blue,green
```

Spring Boot binder thường ánh xạ `max-attempts` sang JavaBean `maxAttempts`. Trong nguồn dạng properties, nên công bố key dưới dạng **lowercase kebab-case**. Dạng camelCase `demo.client.maxAttempts` có thể bind nhờ relaxed binding; nhưng cách đặt environment variable có quy tắc riêng: thường thay dấu chấm bằng underscore, bỏ dấu gạch ngang và uppercase. `demo.client.max-attempts` trở thành `DEMO_CLIENT_MAXATTEMPTS`, **không mặc định** mọi dạng có underscore trong từ đều tương đương.

Một runner với `withPropertyValues("demo.client.maxAttempts=4")` thử map-based property source; nó **không phải** test thực tế cho OS environment variable. Khi cần xác nhận env names/precedence, dùng môi trường/subprocess hoặc một property source loại `SystemEnvironmentPropertySource` trong test riêng.

### 3.1. Sai kiểu khác sai giới hạn

- `max-attempts=banana`: Binder không chuyển String thành int, thường dẫn đến `BindException` trong cause chain.
- `max-attempts=0`: chuyển int thành công nhưng @Min(1) reject; `BindValidationException` là tín hiệu validation failure.
- `timeout=not-a-duration`: lỗi conversion.
- `timeout=PT0S`: chuyển thành Duration.ZERO hợp lệ về kiểu; `@NotNull` **không** cấm 0. Nếu nghiệp vụ cần timeout dương, phải bổ sung constraint/custom validator phù hợp.

Đừng gộp các cases vào cùng một test với nhiều inputs sai, vì lúc context fail bạn sẽ không biết chính xác cái nào đã bị reject.

## 4. Giá trị mặc định: JavaBean, @DefaultValue và Environment

### 4.1. JavaBean initializer

```java
private Duration timeout = Duration.ofSeconds(3);
private int maxAttempts = 2;
private boolean enabled = true;
```

Nếu một key không được cung cấp, JavaBean field initializer được giữ; nếu key có giá trị hợp lệ, Binder sẽ override qua setter. Hãy kiểm tra **cả absent và explicit override**; test `new Props()` chỉ đo initializer, không đo binding.

### 4.2. Record/constructor binding

Với record ở Spring Boot 3.x, `@DefaultValue` dùng trên record components/constructor parameters. Đây là snippet độc lập minh họa immutable binding (không phải file của demo chính):

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties("demo.worker")
public record WorkerOptions(
        @DefaultValue("5s") Duration timeout,
        @DefaultValue("3") int retries,
        @DefaultValue Pool pool
) {
    public record Pool(@DefaultValue("4") int size) {}
}
```

Để dùng constructor-bound type, đăng ký bằng `@EnableConfigurationProperties` hoặc configuration properties scanning. **Không** gắn `@Component` lên record rồi kỳ vọng Boot thực hiện configuration constructor binding như registration-by-binder. Record một canonical constructor thường không cần `@ConstructorBinding` riêng ở Boot 3.x. Với nested constructor binding, `@DefaultValue` không đối số có thể yêu cầu tạo nested value khi nested properties vắng.

### 4.3. Default trong file khác default trong bean

```properties
demo.client.timeout=3s
demo.client.enabled=true
```

Một default trong `application.properties` tồn tại trong Environment. Trái lại, Spring Boot documentation xác nhận **default được định nghĩa trong `@ConfigurationProperties` không tự được phản ánh ngược vào Environment**.

Do đó trong một JavaBean:

```java
private boolean enabled = true;
```

khi user chưa đặt `demo.client.enabled`:

- `properties.isEnabled()` là true;
- `environment.containsProperty("demo.client.enabled")` có thể là false;
- `@ConditionalOnProperty(havingValue="true")` **không tự đọc default này**.

Chính vì thế nếu mặc định phải tạo client, dùng `matchIfMissing=true` hoặc thiết kế default configuration source và condition một cách nhất quán.

### 4.4. Absent khác explicit empty/false/zero

| Cấu hình | Ý nghĩa |
|---|---|
| Không có key | Giữ JavaBean initializer / record @DefaultValue |
| `enabled=false` | Override true thành false |
| `max-attempts=0` | Bind 0 rồi vi phạm @Min(1) |
| `service-name=` | String blank, @NotBlank reject |
| `timeout=` | Có key empty; conversion/null semantics cần kiểm tra |
| `tags=` | Có thể tạo empty collection theo converter, không nên suy từ absent |
| `pool.size=0` | Nested constraint reject nếu @Valid cascade |
| Unknown key | Mặc định có thể bị ignore hoặc bị reject ở strict mode |

## 5. Jakarta Bean Validation với @Validated và @Valid

Spring Boot 3.5 yêu cầu một Jakarta Bean Validation provider trên classpath khi dùng constraint annotations trên `@ConfigurationProperties`. Thông thường thêm `spring-boot-starter-validation`, có Hibernate Validator. Import ở Boot 3.x bắt đầu bằng `jakarta.validation`, không dùng `javax.validation` như nhiều tutorial Boot 2.

- `@NotBlank`: String không null và không chỉ whitespace.
- `@NotNull`: reference không null; không tự kiểm tra URI scheme hoặc Duration dương.
- `@NotEmpty`: collection/string phải có phần tử/ký tự.
- `@Min(1)`, `@Max(8)`: numeric boundaries.
- `@Size`, `@Pattern`: constraints khác.
- `@Valid`: yêu cầu **cascade validation vào nested object**.
- `@Validated`: bật validation cho configuration properties type theo Spring Boot.

Ví dụ:

```java
@ConfigurationProperties(prefix = "demo.client")
@Validated
public class ExampleProperties {
    @NotBlank
    private String serviceName;
    @Min(1)
    private int retries = 2;
    @Valid
    private final Pool pool = new Pool();
    // JavaBean getters/setters and Pool class follow...
}
```

Snippet này chưa là Java file runnable riêng; full implementation ở phần 9.

### 5.1. Vì sao @Valid quan trọng?

Nếu outer properties bean có `@Validated` và một nested object có `@Min(1)`, validator **không nhất thiết** kiểm tra nested field trừ khi outer field có `@Valid`. Test happy-path `pool.size=4` không phát hiện thiếu cascade. Một test negative `pool.size=0` mới có khả năng phát hiện regression khi `@Valid` bị xóa.

Nested POJO đã được initialize, có getter và JavaBean setters cho fields con thường bind được; `@NestedConfigurationProperty` chủ yếu hỗ trợ metadata khi cần mô tả nested type bên ngoài, không phải nút bật validation.

### 5.2. Failing context là behavior mong đợi

Config sai nên fail-fast **trước khi app nhận traffic**. Test bằng ContextRunner có thể assert context failed, kiểm tra cause chain và bảo đảm nhánh lỗi đúng. Không thêm `ignoreInvalidFields=true` chỉ để giữ startup thành công nếu timeout/retry/security settings quan trọng: nó có thể che config sai và khiến app dùng default ngoài ý muốn.

## 6. Unknown keys: lenient hay strict?

`@ConfigurationProperties` có `ignoreUnknownFields=true` theo mặc định. Một key typo `demo.client.max-attemps=5` (thiếu chữ e) có thể bị bỏ qua, khiến maxAttempts giữ default 2 và người vận hành khó phát hiện.

Trong demo chọn **strict**:

```java
@ConfigurationProperties(
        prefix = "demo.client",
        ignoreUnknownFields = false
)
```

Test `demo.client.max-attemps=4` phải khiến context fail. Đây là quyết định có chủ đích; với starter có nhiều phiên bản hoặc dùng property sources phức tạp, strictness có thể gây incompatibility. Cần quyết định dựa trên migration/versioning policy, không mặc định một lựa chọn là đúng cho mọi sản phẩm.

Không nhầm `ignoreUnknownFields` (key không được map) với `ignoreInvalidFields` (giá trị không convert được). Chúng là hai flags khác nhau.

## 7. Khi nào dùng ApplicationContextRunner?

Spring Boot khuyến nghị `ApplicationContextRunner` khi kiểm thử auto-configuration. Runner tạo một ApplicationContext nhỏ cho từng case, nhận property values và user config, cho phép assert bean conditions và thu được startup failure.

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    DemoClientAutoConfiguration.class));

@Test
void defaultCase() {
    runner.withPropertyValues(
            "demo.client.service-name=orders")
          .run(context -> {
              assertThat(context).hasNotFailed();
              assertThat(context)
                      .hasSingleBean(DemoClientProperties.class);
          });
}
```

Đây là đoạn rút gọn trong lớp test đầy đủ phía sau.

**Ưu điểm:** nhanh, không phải mở HTTP server, dễ thử từng thay đổi property, có thể mô phỏng user-defined beans với `withUserConfiguration`, mô phỏng classpath thiếu bằng `FilteredClassLoader` khi cần.

**Giới hạn:** `ApplicationContextRunner` không tự khởi tạo toàn bộ SpringApplication ConfigData pipeline hay đọc YAML profiles như full Boot startup. Với auto-configuration phụ thuộc Servlet/Reactive context, dùng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner`. Boot docs nêu hạn chế của ApplicationContextRunner khi chạy native image tests.

## 8. Thiết kế demo và phiên bản

Bài này tạo một starter-like auto-configuration cho `DemoHttpClient` (record chứa values, **không gọi HTTP thật**).

| Key | Type | Default | Constraint |
|---|---|---|---|
| `demo.client.service-name` | String | Không có | @NotBlank |
| `demo.client.endpoint` | URI | https://api.example.invalid | @NotNull |
| `demo.client.timeout` | Duration | 3s | @NotNull |
| `demo.client.max-attempts` | int | 2 | @Min(1), @Max(8) |
| `demo.client.enabled` | boolean | true | type conversion |
| `demo.client.tags` | List String | ["default"] | @NotEmpty |
| `demo.client.pool.size` | nested int | 4 | @Min(1), @Max(32) |

Auto-configuration policy:

- Properties bean đăng ký và validate qua `@EnableConfigurationProperties`.
- Client bean được tạo khi `enabled` vắng hoặc true.
- Khi `enabled=false`, client bean không tạo, properties bean vẫn bind/validate.
- Khi user tự định nghĩa client bean, default auto-config phải back off.
- Unknown key dưới prefix bị reject vì `ignoreUnknownFields=false`.

### 8.1. Build file dùng Gradle Groovy DSL

File `build.gradle` cho Spring Boot 3.5.16 / Java 17:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    annotationProcessor(
            'org.springframework.boot:spring-boot-configuration-processor')

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Gradle Wrapper files được Gradle hoặc IDE sinh riêng. Nếu dùng Maven, tương đương cần Spring Boot 3.5 parent/BOM, `spring-boot-starter`, `spring-boot-starter-validation` và `spring-boot-starter-test` test scope; dùng Surefire/JUnit Platform phù hợp. Không trộn những dependencies do nhiều major Boot quản lý.

### 8.2. Cấu trúc project

```text
src/
├── main/
│   ├── java/com/example/autoconfig/
│   │   ├── DemoClientProperties.java
│   │   ├── DemoHttpClient.java
│   │   └── DemoClientAutoConfiguration.java
│   ├── java/com/example/demoapp/
│   │   └── DemoApplication.java
│   └── resources/
│       ├── application.properties
│       └── META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── test/java/com/example/autoconfig/
    └── DemoClientAutoConfigurationTest.java
```

Tách `com.example.autoconfig` khỏi component scanning root `com.example.demoapp` vì auto-configuration nên được Boot nạp qua `AutoConfiguration.imports`, không bị scan như regular @Configuration class.

## 9. Mã production đầy đủ

### 9.1. Properties bean có defaults và validation

**File `src/main/java/com/example/autoconfig/DemoClientProperties.java`:**

```java
package com.example.autoconfig;

import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(
        prefix = "demo.client",
        ignoreUnknownFields = false
)
@Validated
public class DemoClientProperties {

    @NotBlank
    private String serviceName;

    @NotNull
    private URI endpoint =
            URI.create("https://api.example.invalid");

    @NotNull
    private Duration timeout = Duration.ofSeconds(3);

    @Min(1)
    @Max(8)
    private int maxAttempts = 2;

    private boolean enabled = true;

    @NotEmpty
    private List<String> tags =
            new ArrayList<>(List.of("default"));

    @Valid
    private final Pool pool = new Pool();

    public String getServiceName() {
        return serviceName;
    }

    public void setServiceName(String serviceName) {
        this.serviceName = serviceName;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public Pool getPool() {
        return pool;
    }

    public static class Pool {

        @Min(1)
        @Max(32)
        private int size = 4;

        public int getSize() {
            return size;
        }

        public void setSize(int size) {
            this.size = size;
        }
    }
}
```

**Lưu ý kỹ thuật:**

- `serviceName` là required, không có initializer. `@NotBlank` bắt missing và blank.
- `endpoint` mặc định là URI thuộc domain `.invalid`, không được dùng để kết nối external service. `@NotNull` không xác nhận URI có HTTPS scheme/hostname hợp lệ; cần custom constraint nếu đó là requirement.
- `timeout` mặc định 3 giây, nhưng @NotNull không cấm Duration.ZERO.
- `maxAttempts` được giới hạn bởi @Min/@Max.
- `tags` dùng mutable ArrayList và setter để binder có thể replace list values; không tự trộn default ["default"] với override ["blue","green"].
- `pool` đã được khởi tạo, có getter, field @Valid cho nested validation và getter/setter size.
- `ignoreUnknownFields=false` là lựa chọn strict của ví dụ; annotation default là true.
- Không nên dùng static fields để lưu configuration được bind.

### 9.2. Client bean mẫu

**File `src/main/java/com/example/autoconfig/DemoHttpClient.java`:**

```java
package com.example.autoconfig;

import java.net.URI;
import java.time.Duration;

public record DemoHttpClient(
        String serviceName,
        URI endpoint,
        Duration timeout,
        int maxAttempts,
        int poolSize
) {}
```

Đây là immutable record dùng để quan sát values được truyền từ properties sang auto-configured bean, **không thực hiện request mạng**. Test này không thể chứng minh actual HTTP timeout, retry behavior hay connection pool hoạt động; muốn làm vậy cần tests cho client implementation thật.

### 9.3. Auto-configuration và conditions

**File `src/main/java/com/example/autoconfig/DemoClientAutoConfiguration.java`:**

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(DemoClientProperties.class)
public class DemoClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DemoHttpClient.class)
    @ConditionalOnProperty(
            prefix = "demo.client",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    DemoHttpClient demoHttpClient(DemoClientProperties props) {
        return new DemoHttpClient(
                props.getServiceName(),
                props.getEndpoint(),
                props.getTimeout(),
                props.getMaxAttempts(),
                props.getPool().getSize());
    }
}
```

**Phân biệt rõ:**

- `@EnableConfigurationProperties` đăng ký/bind/validate properties type khi auto-config class được load.
- `@ConditionalOnProperty` quyết định có tạo client bean hay không; nó đọc Environment. `matchIfMissing=true` được chọn vì mặc định enabled=true.
- `@ConditionalOnMissingBean` giúp auto-config không ghi đè bean do ứng dụng định nghĩa.
- Enabled=false **không** ngăn đăng ký properties bean theo thiết kế này, nên required field vẫn được validate kể cả khi client bean bị suppress.
- Có thể thêm classpath conditions nếu auto-configuration thực phụ thuộc thư viện tùy chọn; cần test riêng cho `@ConditionalOnClass`.

### 9.4. AutoConfiguration.imports và SpringBootApplication

**File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

```text
com.example.autoconfig.DemoClientAutoConfiguration
```

**File `src/main/java/com/example/demoapp/DemoApplication.java`:**

```java
package com.example.demoapp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**File `src/main/resources/application.properties`:**

```properties
demo.client.service-name=orders
```

Spring Boot production boot path đọc AutoConfiguration.imports và nạp class theo cơ chế auto-config candidates. Test ContextRunner ở phần 10 **chỉ định chính class đó** qua `AutoConfigurations.of` và không mặc nhiên đọc application.properties như SpringApplication.

## 10. Bộ JUnit kiểm tra binding, validation, defaults và conditions

**File `src/test/java/com/example/autoconfig/DemoClientAutoConfigurationTest.java`:**

```java
package com.example.autoconfig;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.bind.BindException;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DemoClientAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            DemoClientAutoConfiguration.class));

    private ApplicationContextRunner valid() {
        return runner.withPropertyValues(
                "demo.client.service-name=orders");
    }

    private static boolean containsCause(
            Throwable root, Class<? extends Throwable> kind) {
        for (Throwable e = root; e != null; e = e.getCause()) {
            if (kind.isInstance(e)) {
                return true;
            }
        }
        return false;
    }

    private static void validationFails(
            AssertableApplicationContext context) {
        assertThat(context).hasFailed();
        assertThat(containsCause(
                context.getStartupFailure(),
                BindValidationException.class)).isTrue();
    }

    private static void bindingFails(
            AssertableApplicationContext context) {
        assertThat(context).hasFailed();
        assertThat(containsCause(
                context.getStartupFailure(),
                BindException.class)).isTrue();
    }

    @Test
    void defaultsAreBoundWhenOptionalKeysAreMissing() {
        valid().run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(DemoClientProperties.class);
            assertThat(context)
                    .hasSingleBean(DemoHttpClient.class);

            DemoClientProperties p =
                    context.getBean(DemoClientProperties.class);
            assertThat(p.getServiceName()).isEqualTo("orders");
            assertThat(p.getEndpoint()).isEqualTo(
                    URI.create("https://api.example.invalid"));
            assertThat(p.getTimeout()).isEqualTo(
                    Duration.ofSeconds(3));
            assertThat(p.getMaxAttempts()).isEqualTo(2);
            assertThat(p.isEnabled()).isTrue();
            assertThat(p.getTags()).containsExactly("default");
            assertThat(p.getPool().getSize()).isEqualTo(4);

            DemoHttpClient client =
                    context.getBean(DemoHttpClient.class);
            assertThat(client.timeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(client.maxAttempts()).isEqualTo(2);
            assertThat(client.poolSize()).isEqualTo(4);
        });
    }

    @Test
    void javaDefaultsAreNotAutomaticallyEnvironmentProperties() {
        valid().run(context -> {
            assertThat(context).hasNotFailed();
            DemoClientProperties p =
                    context.getBean(DemoClientProperties.class);

            assertThat(p.isEnabled()).isTrue();
            assertThat(p.getMaxAttempts()).isEqualTo(2);
            assertThat(context.getEnvironment()
                    .containsProperty("demo.client.enabled"))
                    .isFalse();
            assertThat(context.getEnvironment()
                    .containsProperty("demo.client.max-attempts"))
                    .isFalse();
            assertThat(context)
                    .hasSingleBean(DemoHttpClient.class);
        });
    }

    @Test
    void explicitOverridesConvertAndReachClient() {
        valid().withPropertyValues(
                "demo.client.endpoint=https://stage.example.invalid:8443",
                "demo.client.timeout=750ms",
                "demo.client.max-attempts=5",
                "demo.client.tags=blue,green",
                "demo.client.pool.size=12"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DemoClientProperties p =
                    context.getBean(DemoClientProperties.class);

            assertThat(p.getEndpoint()).isEqualTo(
                    URI.create("https://stage.example.invalid:8443"));
            assertThat(p.getTimeout()).isEqualTo(
                    Duration.ofMillis(750));
            assertThat(p.getMaxAttempts()).isEqualTo(5);
            assertThat(p.getTags())
                    .containsExactly("blue", "green");
            assertThat(p.getPool().getSize()).isEqualTo(12);

            DemoHttpClient client =
                    context.getBean(DemoHttpClient.class);
            assertThat(client.endpoint()).isEqualTo(p.getEndpoint());
            assertThat(client.timeout()).isEqualTo(p.getTimeout());
            assertThat(client.maxAttempts()).isEqualTo(5);
            assertThat(client.poolSize()).isEqualTo(12);
        });
    }

    @Test
    void relaxedCamelCaseKeysBind() {
        runner.withPropertyValues(
                "demo.client.serviceName=billing",
                "demo.client.maxAttempts=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DemoClientProperties p =
                    context.getBean(DemoClientProperties.class);
            assertThat(p.getServiceName()).isEqualTo("billing");
            assertThat(p.getMaxAttempts()).isEqualTo(4);
        });
    }

    @Test
    void minAndMaxBoundsAreInclusive() {
        for (int count : new int[] {1, 8}) {
            valid().withPropertyValues(
                    "demo.client.max-attempts=" + count,
                    "demo.client.pool.size=32"
            ).run(context -> {
                assertThat(context).hasNotFailed();
                DemoClientProperties p =
                        context.getBean(DemoClientProperties.class);
                assertThat(p.getMaxAttempts()).isEqualTo(count);
                assertThat(p.getPool().getSize()).isEqualTo(32);
            });
        }
    }

    @Test
    void missingRequiredServiceNameFails() {
        runner.run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void blankServiceNameFails() {
        runner.withPropertyValues(
                "demo.client.service-name=   "
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void maxAttemptsZeroFails() {
        valid().withPropertyValues(
                "demo.client.max-attempts=0"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void maxAttemptsNineFails() {
        valid().withPropertyValues(
                "demo.client.max-attempts=9"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void malformedIntegerFailsConversion() {
        valid().withPropertyValues(
                "demo.client.max-attempts=not-a-number"
        ).run(DemoClientAutoConfigurationTest
                ::bindingFails);
    }

    @Test
    void malformedDurationFailsConversion() {
        valid().withPropertyValues(
                "demo.client.timeout=not-a-duration"
        ).run(DemoClientAutoConfigurationTest
                ::bindingFails);
    }

    @Test
    void nestedPoolZeroFailsValidation() {
        valid().withPropertyValues(
                "demo.client.pool.size=0"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void nestedPoolThirtyThreeFailsValidation() {
        valid().withPropertyValues(
                "demo.client.pool.size=33"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void explicitFalseDisablesClientButNotProps() {
        valid().withPropertyValues(
                "demo.client.enabled=false"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(DemoClientProperties.class);
            assertThat(context)
                    .doesNotHaveBean(DemoHttpClient.class);
            assertThat(context.getBean(
                    DemoClientProperties.class).isEnabled())
                    .isFalse();
        });
    }

    @Test
    void malformedBooleanFailsConversion() {
        valid().withPropertyValues(
                "demo.client.enabled=not-a-boolean"
        ).run(DemoClientAutoConfigurationTest
                ::bindingFails);
    }

    @Test
    void unknownKeyFailsInStrictMode() {
        valid().withPropertyValues(
                "demo.client.max-attemps=4"
        ).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
    }

    @Test
    void requiredPropertiesValidateEvenWhenFeatureDisabled() {
        runner.withPropertyValues(
                "demo.client.enabled=false"
        ).run(DemoClientAutoConfigurationTest
                ::validationFails);
    }

    @Test
    void customClientMakesAutoConfigurationBackOff() {
        valid().withUserConfiguration(
                CustomClientConfiguration.class
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DemoHttpClient.class);
            assertThat(context.getBean(
                    DemoHttpClient.class).serviceName())
                    .isEqualTo("custom");
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        DemoHttpClient customClient() {
            return new DemoHttpClient(
                    "custom",
                    URI.create("https://custom.example.invalid"),
                    Duration.ofSeconds(7),
                    1,
                    5);
        }
    }
}
```

**Đúng 18 phương thức `@Test`**, không kể các helper và nested configuration. Bộ tests không dùng `@SpringBootTest`, không mở socket, không kết nối external API, và mỗi runner invocation có context độc lập.

### 10.1. Phân nhóm tests

| Nhóm | Số test | Nội dung |
|---|---:|---|
| Default values và Environment | 2 | JavaBean defaults, matchIfMissing, keys không tự xuất hiện trong Environment |
| Valid overrides và relaxed names | 3 | URI/Duration/List/nested, camelCase, min/max inclusive |
| Required fields và numeric constraint violations | 4 | Missing/blank serviceName, count 0/9 |
| Conversion errors | 3 | Integer, Duration, boolean không convert được |
| Nested Bean Validation | 2 | Pool size 0/33 |
| Conditional client | 1 | Enabled=false, properties vẫn tồn tại |
| Strict unknown key | 1 | Typo bị reject |
| Validation khi disabled | 1 | Required config vẫn fail vì props đăng ký unconditional |
| User override | 1 | @ConditionalOnMissingBean back-off |
| **Tổng** | **18** | Các trạng thái context khác nhau |

### 10.2. Vì sao helper duyệt cause chain?

Spring có thể bọc lỗi dưới `BeanCreationException` hoặc `ConfigurationPropertiesBindException`, trong khi `BindValidationException` nằm sâu hơn. Test chỉ so nguyên văn lỗi `must be greater than or equal to 1` dễ thất bại khi Hibernate Validator thay locale hoặc message, dù validation vẫn hoạt động. Helper `containsCause` tìm type thật ở chuỗi `Throwable.getCause()` và ổn định hơn.

Với các test phức tạp, hãy kiểm tra thêm property path/constraint violations có cấu trúc. Ở demo mỗi test cố tình chỉ thay **một input**, nhờ đó startup failure có nguyên nhân rõ hơn. Trong một environment khác, nếu cause chain khác vì version/custom validators, phải xem root cause thực tế, không đơn giản bỏ assertion.

### 10.3. Các điều kiện của demo có nghĩa gì?

`@ConditionalOnProperty` đọc Environment chứ không đọc JavaBean default. `matchIfMissing=true` nhất quán với default enabled=true. `@EnableConfigurationProperties` đặt tại class auto-config, nên ngay khi client bean bị condition false, properties vẫn bind/validate.

Nếu thiết kế thật muốn **feature disabled không bắt service-name**, có thể đặt các điều kiện ở scope phù hợp với registration của properties bean, hoặc thay validation groups/conditional registration. Khi đổi thiết kế, **phải thay tests** để phản ánh đúng contract; không tự suy một policy là phổ quát.

## 11. Cách chạy và đọc báo cáo

Linux/macOS:

```bash
./gradlew test --tests "com.example.autoconfig.DemoClientAutoConfigurationTest"

# Chạy application demo (không gọi API ngoài):
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.autoconfig.DemoClientAutoConfigurationTest"
.\gradlew.bat bootRun
```

Nếu dùng Maven, cần một Maven project có Spring Boot parent/BOM, Java 17 và các dependencies tương ứng, sau đó gọi `./mvnw -Dtest=DemoClientAutoConfigurationTest test` (Windows `mvnw.cmd`). Chỉ dùng build tool thực sự có trong project.

**Kỳ vọng theo code:** 18 JUnit methods pass nếu dependencies/version và môi trường đầy đủ. Trong phiên viết bài, mã được rà soát tĩnh theo tài liệu Spring Boot 3.5 nhưng **chưa biên dịch hoặc thực thi JUnit**. Một log `BUILD SUCCESSFUL` từ cache cũng không đủ kết luận; xem test report bao nhiêu executed/passed/failed/skipped.

## 12. Những gì ApplicationContextRunner chưa chứng minh

Các bài test trên **đã nhắm tới** binding/defaults/validation và conditional bean creation. Chúng **không kiểm tra**:

- SpringApplication ConfigData parser đọc YAML/profile documents đúng.
- `spring.config.import` từ Config Server/secret manager.
- Actual OS env var naming hoặc shell quoting.
- Properties precedence giữa profile-specific jar file, external file, CLI arguments.
- Đường request HTTP/TLS, retry/circuit breaker, network timeout thật.
- Native-image AOT startup (ContextRunner có hạn chế trong native mode theo Boot docs).
- Một starter jar sau khi publish có AutoConfiguration.imports metadata đúng trong artifact cuối.
- Độ an toàn của secrets/credentials hoặc Actuator configprops exposure.

### 12.1. Khi cần full application test

Thêm `@SpringBootTest(properties = ...)` để nạp SpringApplication/full context. Dùng `@ActiveProfiles("test")` và resource `application-test.yml` khi muốn kiểm tra profile loading thật. Với dynamic endpoint của Testcontainers, có thể dùng `@DynamicPropertySource`. Test nhiều property sources phải so precedence dựa trên Boot documentation, không suy từ ContextRunner.withPropertyValues.

Một ví dụ **snippet bổ sung**, không được tính trong 18 methods của project mẫu:

```java
@SpringBootTest(
    classes = DemoApplication.class,
    properties = {
        "demo.client.service-name=orders",
        "demo.client.timeout=500ms"
    }
)
class FullBootConfigTest {

    @Autowired DemoClientProperties props;

    @Test
    void timeoutIsLoadedBySpringApplication() {
        assertThat(props.getTimeout())
                .isEqualTo(Duration.ofMillis(500));
    }
}
```

Snippet yêu cầu imports và package đúng; nó hữu ích khi cần xác minh actual Boot app startup chứ không thay các case nhỏ của ApplicationContextRunner.

### 12.2. Lists và property sources

Spring Boot có cơ chế override collection values: list từ higher-priority property source thường **thay** list ở nguồn thấp hơn, không tự cộng thêm. Maps có behavior merge theo keys tùy trường hợp. Nếu cấu hình của bạn quan trọng về lists/maps, test actual final bound object với nhiều sources thay vì giả định concat.

### 12.3. Duration và DataSize

`Duration` nhận các suffix như `ms`, `s`, `m` theo binding conventions; `DataSize` có dạng `KB`, `MB`, `GB`. Với input chỉ có số, mặc định unit và `@DurationUnit`/`@DataSizeUnit` có thể quan trọng. Hãy khai báo đơn vị rõ trong docs và tests: `750ms` không đồng nghĩa `750s`, `4MB` không đồng nghĩa 4 bytes.

### 12.4. Configuration metadata

`spring-boot-configuration-processor` tạo metadata để IDE có thể gợi ý property names/types/defaults khi hỗ trợ. Nó **không thay thế** runtime Bean Validation hoặc tests. Một starter nên có tài liệu cho keys, defaults, constraints, deprecated aliases và compatibility policy.

## 13. Anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách cải thiện |
|---|---|---|
| Test `new Properties()` rồi gọi là binding test | Không chạy binder | ContextRunner + withPropertyValues |
| Có @NotBlank nhưng quên @Validated | Constraint có thể không được áp dụng | @Validated + starter-validation |
| Nested @Min nhưng quên @Valid | Không cascade | Negative nested test |
| Dùng `ignoreInvalidFields=true` để app start | Che input sai kiểu | Fail-fast, sửa cấu hình |
| Dùng lenient unknown field cho critical keys mà không test typos | Key sai bị bỏ qua | Strict mode hoặc config lint |
| Có JavaBean default true nhưng condition không matchIfMissing | Auto bean không tồn tại | Align default/condition |
| Test only enabled=true, không test disabled | Không thấy conditional failure | Có cả missing/false cases |
| Không test custom user bean | Auto-config có thể gây duplicate | Test @ConditionalOnMissingBean |
| Assert toàn bộ translated error message | Locale/version flakiness | Cause type/property path |
| Có nhiều input sai trong cùng test | Không biết violation nào kích hoạt | Baseline valid, thay một key |
| Nghĩ ContextRunner nạp application.yml | Bỏ qua ConfigData loading | SpringBootTest profile test |
| Nghĩ @NotNull URI kiểm tra HTTPS | Relative URI vẫn không null | Custom validator và test scheme |
| Nghĩ @NotNull Duration cấm 0 | Duration.ZERO vẫn là object | Domain-specific validation |
| Nghĩ property default tự ở Environment | Conditions đọc key vắng | matchIfMissing/config default |
| Dùng System.setProperty toàn cục ở parallel tests | Rò state | Scoped runner/TestPropertySource |
| Log raw passwords/API keys trong failure reports | Lộ secrets | Mask/redact config |

## 14. Quy trình debug configuration startup fail

1. Ghi chính xác prefix/key canonical và expected Java type.
2. Xác nhận class properties được đăng ký bằng `@EnableConfigurationProperties` hoặc scanning.
3. Kiểm tra current property source precedence, profiles và ConfigData khi dùng full app.
4. Kiểm tra JavaBean setter/nested getter hoặc record constructor binding.
5. Phân biệt conversion error từ Binder với Bean Validation constraints.
6. Kiểm tra `@Validated`, `@Valid`, Jakarta Validator provider.
7. Đọc lỗi ở root cause, field name và rejected value **đã redact nếu là secret**.
8. Kiểm tra condition report nếu bean không được tạo.
9. Thử ContextRunner nhỏ với một valid baseline và một input thay đổi.
10. Thêm full SpringApplication test nếu lỗi liên quan file/env profile.
11. Giữ regression negative test để cùng lỗi không quay lại.
12. Không chữa bằng cách bỏ validation, đổi default trái hợp đồng hoặc ignoreInvalidFields.

## 15. Bài tập và lời giải

### A. Thiếu key bắt buộc

Class có `@NotBlank String serviceName`, không có key, context fail. Đó là lỗi convert hay validate?

**Validation:** thuộc tính không được cung cấp nên field null, vi phạm @NotBlank. Test nên xác minh cause chain có BindValidationException.

### B. Sai định dạng số

`demo.client.max-attempts=banana`. @Min không được đánh giá thành công vì binder không tạo được int. **Conversion failure**, kiểm tra BindException.

### C. Nested size=0 không fail

Nếu `Pool.size` có @Min(1) nhưng context vẫn pass, hãy kiểm tra `@Valid` ở outer nested field và Bean Validation provider. Test negative pool.size=0 là bằng chứng cần có.

### D. Enabled default true nhưng bean vắng

JavaBean `enabled=true` không khiến Environment có key. Condition dùng matchIfMissing=false sẽ không match khi key vắng. **Sửa conditional policy** hoặc explicit default source, và test case key missing.

### E. Enabled=false nhưng thiếu serviceName

Trong demo, properties bean luôn được enable trên auto-config class; vì vậy validation vẫn chạy và startup fail. Nếu business requirement khác, thay điều kiện đăng ký properties type có chủ đích rồi viết tests mới.

### F. User-defined bean

Auto-config tạo thêm bean client dù app đã có custom client. Bổ sung `@ConditionalOnMissingBean(DemoHttpClient.class)` và test ContextRunner.withUserConfiguration để chứng minh back-off.

### G. JavaBean default và override list

Default tags=["default"]; user đặt tags=blue,green. Test demo assert ["blue","green"], không ["default","blue","green"]. Collections có override semantics, không tự merge append.

### H. Required URI có HTTPS không?

`@NotNull URI endpoint` không bảo đảm `https`/host hợp lệ. Nếu policy yêu cầu HTTPS, thêm custom Bean Validation constraint hoặc validation method rồi test http/relative/wrong host.

### I. Record @DefaultValue và @Component

Một record @ConfigurationProperties dùng @DefaultValue nhưng được tạo như @Component. Nó có chắc được constructor-bound bởi Boot không? **Không nên giả định.** Dùng EnableConfigurationProperties/configuration properties scan.

### J. @SpringBootTest hay ApplicationContextRunner?

Nếu mục tiêu là một starter's conditional bean matrix, dùng ContextRunner. Nếu mục tiêu là YAML profile file loading, full SpringApplication test thích hợp.

### K. Tiếng Anh và localized constraint messages

Test compare exact message `must be greater than or equal to 1` có thể fail do locale. Tốt hơn kiểm tra cause types và violation metadata ổn định.

### L. Secret property

Một configuration property là API key, validation startup fail và logs in raw value. **Không lưu secrets trong test/report.** Log failure metadata có redaction và quản lý Actuator config endpoints.

## 16. Checklist QA cho configuration properties và auto-configuration

- [ ] Properties prefix và names canonical nhất quán.
- [ ] Class được register đúng; auto-config class không bị component scan vô ý.
- [ ] JavaBean fields có setters/getters hoặc record constructor binding hợp lệ.
- [ ] Defaults được test khi key vắng.
- [ ] Explicit overrides được test, không chỉ Java initializer.
- [ ] Duration/URI/int/boolean/List/nested conversions đúng.
- [ ] Required fields có @NotBlank/@NotNull hợp lý.
- [ ] Bean Validation provider có trên classpath.
- [ ] @Validated có trên properties bean, @Valid cascade nested khi cần.
- [ ] Min/max được test cả valid boundaries và invalid neighbors.
- [ ] Invalid numbers/durations/booleans fail binding.
- [ ] Unknown key strict/lenient behavior được ghi rõ/test.
- [ ] Không dùng ignoreInvalidFields=true để che input errors.
- [ ] Default JavaBean không bị nhầm thành Environment key.
- [ ] @ConditionalOnProperty matchIfMissing phù hợp default contract.
- [ ] @ConditionalOnMissingBean back-off đúng khi user override.
- [ ] Disabled branch và validation scope được test rõ.
- [ ] Test contexts độc lập, không rò global properties.
- [ ] Startup failures kiểm tra đúng cause, không match full localized message.
- [ ] List/map source precedence được test nếu là requirement.
- [ ] Profiles/YAML/ConfigData được test qua SpringApplication khi cần.
- [ ] AutoConfiguration.imports có đúng class FQN.
- [ ] Metadata processor được dùng nếu cần IDE completion.
- [ ] Security/secret fields được mask trong logs/Actuator.
- [ ] Test runner thực thi đúng JUnit methods; báo skipped rõ.
- [ ] Đừng dùng ContextRunner pass để chứng minh external HTTP client/network behavior.
- [ ] Với Boot 4.x, cập nhật modules/imports và xác minh behavior mới.

## 17. Kết luận

**Configuration properties là một interface được vận hành bởi Spring Boot Binder, Bean Validation và auto-configuration conditions.** Test tốt không chỉ đọc getters. Nó phải kiểm tra:

- **Binding:** key names, relaxed matching, data types, nested objects và explicit overrides.
- **Validation:** missing, blank, sai giới hạn, sai kiểu và unknown keys theo chính sách.
- **Defaults/conditions:** Java defaults, @DefaultValue, Environment visibility, enabled/disabled branches và user bean overrides.

`ApplicationContextRunner` kết hợp `AutoConfigurations.of` là công cụ phù hợp để test nhiều tổ hợp nhanh và cô lập. Khi cần kiểm chứng YAML/profile/env source hay real external dependencies, bổ sung SpringApplication/full integration tests riêng.

Ví dụ Java 17+/Spring Boot 3.5.16 đi kèm **18 JUnit Jupiter methods** được thiết kế để kiểm tra ba nhóm rủi ro trên. Các tests sử dụng một DemoHttpClient record không mở network; vì thế kết quả mong đợi chỉ là **configuration/auto-configuration correctness**, không phải performance hay real HTTP connectivity.

## 18. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): type-safe properties, relaxed binding, validation, @DefaultValue, defaults và Environment.
- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): ApplicationContextRunner, AutoConfigurations, bean conditions và AutoConfiguration.imports.
- [Spring Boot 3.5 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): context lifecycle và runner customization.
- [Spring Boot 3.5 — BindValidationException API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html): exception khi Bean Validation thất bại trong binding.
- [Spring Boot 3.5 — ConfigurationProperties API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): prefix, ignoreUnknownFields, ignoreInvalidFields.
- [Spring Boot 3.5 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): havingValue, matchIfMissing.
- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html): plugin 3.5.16 và dependency management.
- [Jakarta Bean Validation 3.0](https://jakarta.ee/specifications/bean-validation/3.0/): @NotBlank, @Min/@Max và @Valid cascade.
