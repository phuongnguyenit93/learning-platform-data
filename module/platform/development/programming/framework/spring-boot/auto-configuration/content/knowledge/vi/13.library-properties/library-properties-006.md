# Đọc `Environment` để quyết định kích hoạt và dùng đối tượng thuộc tính để cấu hình bean

## 1. Vì sao phải tách hai trách nhiệm?

Khi viết thư viện hoặc Spring Boot auto-configuration, hai câu hỏi thường xuất hiện đồng thời:

1. **Có nên tạo bean hay không?** Ví dụ chỉ kích hoạt HTTP client khi `demo.remote.enabled=true` và `demo.remote.protocol=http`.
2. **Nếu tạo bean, cấu hình nó như thế nào?** Ví dụ endpoint dạng `URI`, thời gian chờ dạng `Duration`, số lần thử lại dạng `int`.

Hai câu hỏi thuộc **hai thời điểm khác nhau** trong vòng đời khởi động:

- Một `Condition` đọc dữ liệu từ `Environment` khi Spring đang xét đăng ký cấu hình/bean. Lúc này không nên giả định bean cấu hình đã được tạo và bind.
- Khi điều kiện phù hợp và cấu hình được đăng ký, Spring Boot có thể bind các khóa vào một đối tượng `@ConfigurationProperties`. Phương thức `@Bean` nhận đối tượng có kiểu rõ ràng, kiểm tra tính hợp lệ rồi dựng bean nghiệp vụ.

Dùng `Environment` để ra **quyết định kích hoạt**, dùng `@ConfigurationProperties` để chuyển **dữ liệu cấu hình** thành kiểu Java. Thiết kế này đặc biệt hữu ích cho thư viện dùng trong nhiều ứng dụng: chỉ ứng dụng thực sự bật feature mới có bean của thư viện.

> `Environment` và `@ConfigurationProperties` đều đọc từ hệ thống externalized configuration của Spring Boot; khác biệt chủ yếu là **mục đích**, **API** và **giai đoạn sử dụng**. Hai cơ chế có thể cùng được áp dụng trong một auto-configuration.

## 2. Luồng xử lý của một auto-configuration

Giả sử thư viện cung cấp `RemoteClient` và đọc các khóa:

```yaml
demo:
  remote:
    enabled: true
    protocol: http
    endpoint: https://api.example.test/v1
    timeout: 1500ms
    max-attempts: 4
```

Ta muốn quy tắc sau:

```text
Environment:
    demo.remote.enabled == true
    AND demo.remote.protocol == "http"
             |
             v
        Condition.matches() ?
             |
       +-----+-----+
       |           |
      NO          YES
       |           |
 Không đăng ký   Đăng ký cấu hình
 bean mặc định       |
                     v
        @EnableConfigurationProperties
        bind demo.remote → RemoteProperties
                     |
                     v
        @Bean RemoteClient(RemoteProperties)
        endpoint: URI
        timeout: Duration
        maxAttempts: int
```

Sự khác nhau quan trọng:

| Câu hỏi | Công cụ thích hợp | Kết quả |
|---|---|---|
| Có bật feature không? | `@ConditionalOnProperty` hoặc custom `Condition` với `Environment` | `true`/`false` tại thời điểm xét điều kiện |
| Thuộc tính nằm trong nguồn nào? | `Environment` và `PropertySource`/báo cáo cấu hình | Giá trị có hiệu lực theo thứ tự ưu tiên nguồn |
| Giá trị endpoint/timeout có kiểu gì? | `@ConfigurationProperties` và Spring Boot Binder | `URI`, `Duration`, `int` đã chuyển kiểu |
| Có thiếu cấu hình bắt buộc không? | Validation trên properties hoặc kiểm tra lúc tạo bean | Lỗi cấu hình cụ thể thay vì bean cấu hình sai |
| Người dùng đã có bean thay thế chưa? | `@ConditionalOnMissingBean` | Bean mặc định nhường chỗ cho bean tùy chỉnh |

`@ConditionalOnMissingBean` được dùng ở đây vì mục tiêu thư viện còn là **back off khi người dùng đã tự tạo bean**. Nó độc lập với quyết định bật feature bằng `Environment`.

## 3. Khi nào chỉ cần `@ConditionalOnProperty`?

Nếu yêu cầu duy nhất là có cờ `enabled=true`, dùng annotation có sẵn:

```java
@ConditionalOnProperty(
    prefix = "demo.remote",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

Cách đọc:

- `prefix` và `name` tạo khóa `demo.remote.enabled`.
- `havingValue="true"` yêu cầu giá trị khớp `true`; tránh xem các giá trị bất kỳ khác `false` là được bật.
- `matchIfMissing=false` đảm bảo thiếu khóa không tự kích hoạt; đây là lựa chọn hợp lý với tính năng cần **opt-in**.
- Annotation không tự kiểm tra endpoint, timeout, thư viện tùy chọn hay bean người dùng.

Đoạn trên là **annotation minh họa**, cần gắn trên một class cấu hình hoặc phương thức `@Bean`. Có thể thêm `@ConditionalOnClass` và `@ConditionalOnMissingBean` nếu bài toán yêu cầu.

Chỉ khi quy tắc kích hoạt phức tạp hơn, ví dụ **cả enabled và protocol**, mới cần cân nhắc custom `Condition`. Không cần viết Condition riêng cho một cờ boolean đơn giản.

## 4. Đọc `Environment` trong custom `Condition`

Một custom `Condition` phải triển khai `org.springframework.context.annotation.Condition` và nhận `ConditionContext`. Từ context này lấy `Environment`:

```java
package demo;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Environment;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class EnabledHttpCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Environment env = context.getEnvironment();

        boolean enabled = Boolean.TRUE.equals(
                env.getProperty("demo.remote.enabled", Boolean.class, false)
        );

        String protocol = env.getProperty(
                "demo.remote.protocol", "http"
        );

        return enabled && "http".equalsIgnoreCase(protocol.trim());
    }
}
```

Tệp `src/main/java/demo/EnabledHttpCondition.java` là **lớp Java độc lập** có thể biên dịch khi classpath có Spring Framework và Spring Boot starter phù hợp.

Ý nghĩa của từng phần:

1. `context.getEnvironment()` lấy dữ liệu thuộc tính của context đang xử lý. Dữ liệu có thể đến từ `application.yml`, `application.properties`, profile, biến môi trường, hệ thống hoặc tham số dòng lệnh.
2. `getProperty("demo.remote.enabled", Boolean.class, false)` yêu cầu chuyển giá trị thành `Boolean` và nhận mặc định `false` khi khóa vắng mặt. `Boolean.TRUE.equals(...)` chỉ bật khi đọc được true.
3. `getProperty("demo.remote.protocol", "http")` sử dụng mặc định là HTTP nếu không khai báo protocol; đây là **quyết định nghiệp vụ** trong ví dụ, không phải mặc định của mọi thư viện.
4. `"http".equalsIgnoreCase(protocol.trim())` yêu cầu protocol đúng ý định, chấp nhận khác biệt hoa/thường và khoảng trắng xung quanh.
5. Không gọi `context.getBeanFactory().getBean(RemoteProperties.class)` để lấy một bean properties rồi mới quyết định: bean có thể chưa được đăng ký hoặc chưa được bind khi condition chạy.

**Trường hợp dữ liệu lỗi:** chuyển đổi `Boolean` ở `Environment` có thể ném lỗi nếu giá trị không thể chuyển kiểu. Không nên tự động coi mọi cấu hình sai là “feature bị tắt” và che khuất lỗi vận hành. Nếu thư viện cần báo lỗi chuyên biệt, hãy xác định rõ hành vi đối với giá trị sai và viết test tương ứng.

### Điều kiện có được cập nhật khi thay đổi file cấu hình?

`Condition` được xét trong quá trình xây dựng application context, chủ yếu khi đăng ký cấu hình và bean. Đổi file hoặc biến môi trường **sau khi context đã tạo** không tự chạy lại toàn bộ điều kiện để thêm/xóa bean. Điều khiển bật/tắt động ở runtime là một thiết kế khác.

## 5. Dùng `@ConfigurationProperties` để nhận dữ liệu có kiểu

Các khóa vận hành `endpoint`, `timeout` và `max-attempts` nên được bind vào một đối tượng, không nên lặp hàng loạt `environment.getProperty(...)` ở mỗi phương thức tạo bean.

```java
package demo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.remote")
public class RemoteProperties {

    private URI endpoint;
    private Duration timeout = Duration.ofSeconds(2);
    private int maxAttempts = 3;

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
}
```

Đặt file tại `src/main/java/demo/RemoteProperties.java`. Đây là lớp Java đầy đủ với JavaBean setters; Spring Boot Binder sử dụng constructor mặc định và setters để bind.

Khi đọc YAML ở mục 2:

| Khóa cấu hình | Thuộc tính Java | Kết quả |
|---|---|---|
| `demo.remote.endpoint` | `URI endpoint` | `URI.create("https://api.example.test/v1")` |
| `demo.remote.timeout` | `Duration timeout` | `Duration.ofMillis(1500)` |
| `demo.remote.max-attempts` | `int maxAttempts` | `4` |
| Không có `timeout` | Giá trị khởi tạo | `Duration.ofSeconds(2)` |
| Không có `max-attempts` | Giá trị khởi tạo | `3` |

Tên `max-attempts` được bind vào `maxAttempts` nhờ **relaxed binding** của Spring Boot. `Duration` được chuyển kiểu theo hỗ trợ duration của Binder; viết đơn vị rõ ràng (`ms`, `s`,...) để tránh diễn giải sai.

Trong ví dụ này, `enabled` và `protocol` là **các khóa chỉ dùng để quyết định kích hoạt** nên không nhất thiết có field trong `RemoteProperties`. Binder mặc định bỏ qua những khóa cùng prefix nhưng không khớp thuộc tính Java; dữ liệu tạo client được khai báo bằng đúng các field cần thiết. Nếu ứng dụng cần xem trạng thái bật/tắt ở runtime, có thể chọn bổ sung các field tương ứng, nhưng **không dùng bean properties để quyết định condition trước khi nó được tạo**.

### Vì sao không dùng toàn bộ `@Value`?

`@Value` hợp lý cho vài giá trị lẻ, nhưng nhiều thiết lập cùng một prefix thuận tiện hơn với `@ConfigurationProperties` vì có nhóm field rõ ràng, hỗ trợ relaxed binding, chuyển kiểu, validation và metadata hỗ trợ IDE. Đừng kết hợp hai cách một cách ngẫu nhiên đến mức một khóa được đọc theo hai tên khác nhau.

## 6. Nối hai phần trong auto-configuration

Tạo file `src/main/java/demo/RemoteAutoConfiguration.java`:

```java
package demo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
@Conditional(EnabledHttpCondition.class)
@EnableConfigurationProperties(RemoteProperties.class)
public class RemoteAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RemoteClient.class)
    RemoteClient remoteClient(RemoteProperties properties) {

        URI endpoint = properties.getEndpoint();
        Duration timeout = properties.getTimeout();
        int maxAttempts = properties.getMaxAttempts();

        if (endpoint == null || !endpoint.isAbsolute()) {
            throw new IllegalArgumentException(
                    "demo.remote.endpoint must be an absolute URI"
            );
        }
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "demo.remote.timeout must be positive"
            );
        }
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "demo.remote.max-attempts must be >= 1"
            );
        }

        return new RemoteClient(endpoint, timeout, maxAttempts);
    }
}
```

Tệp này là **class auto-configuration đầy đủ**, dựa trên hai lớp `EnabledHttpCondition` và `RemoteProperties` đã trình bày, cùng class `RemoteClient` ở dưới.

```java
package demo;

import java.net.URI;
import java.time.Duration;

public final class RemoteClient {

    private final URI endpoint;
    private final Duration timeout;
    private final int maxAttempts;

    public RemoteClient(URI endpoint, Duration timeout, int maxAttempts) {
        this.endpoint = endpoint;
        this.timeout = timeout;
        this.maxAttempts = maxAttempts;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

Đặt file `src/main/java/demo/RemoteClient.java`. Đây là **client mô phỏng chỉ giữ cấu hình** nhằm kiểm tra hành vi auto-configuration, không gọi mạng và không giả định giao thức API thật. Trong ứng dụng thực tế, constructor có thể truyền các giá trị này tới HTTP client/SDK.

### Tại sao các annotation nằm ở vị trí này?

- `@Conditional(EnabledHttpCondition.class)` trên **class auto-configuration** nghĩa là khi không match, Spring Boot không xử lý các bean được khai báo trong cấu hình này.
- `@EnableConfigurationProperties(RemoteProperties.class)` đăng ký cơ chế bind và bean properties khi cấu hình được xử lý. `@ConfigurationProperties` **không tự tạo bean chỉ vì có annotation trên lớp**; phải có cơ chế đăng ký như `@EnableConfigurationProperties`, scanning hoặc `@Bean` được bind.
- `@Bean remoteClient(RemoteProperties properties)` nhận **properties đã được bind** qua dependency injection, không phải tự đọc lại từng chuỗi trong `Environment`.
- `@ConditionalOnMissingBean(RemoteClient.class)` cho phép ứng dụng đăng ký `RemoteClient` tùy chỉnh trước auto-configuration; mặc định sẽ nhường chỗ.
- Việc kiểm tra endpoint/timeout/attempts thuộc **validity của cấu hình**, không thuộc phép kiểm tra bật feature. Ví dụ dùng fail-fast trong phương thức bean cho dễ quan sát; trong thư viện thực có thể dùng `@Validated` và Jakarta Bean Validation để khai báo các ràng buộc rõ ràng.

Khi tạo một starter dùng Spring Boot 3.x, khai báo tên FQCN của auto-configuration trong:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung tương ứng:

```text
demo.RemoteAutoConfiguration
```

Vì đây là auto-configuration của thư viện, **không dựa vào component scan** để nạp nó. Trong test trực tiếp, `AutoConfigurations.of(RemoteAutoConfiguration.class)` đăng ký cấu hình nên không phụ thuộc file imports.

## 7. Ví dụ kiểm thử độc lập bằng `ApplicationContextRunner` (Spring Boot 3.3 / Java 17+)

Để giữ code có thể chạy, test bên dưới dùng **bốn tệp production đúng như mục 4–6** và một tệp test tại `src/test/java/demo/RemoteAutoConfigurationTest.java`. Dự án đã có các class `RemoteClient`, `RemoteProperties`, `EnabledHttpCondition`, `RemoteAutoConfiguration` trong package `demo`.

```java
package demo;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RemoteAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(RemoteAutoConfiguration.class)
                    );

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        RemoteClient customRemoteClient() {
            return new RemoteClient(
                    URI.create("https://user.example.test"),
                    Duration.ofSeconds(5),
                    8
            );
        }
    }

    @Test
    void enabledHttpBindsTypedConfiguration() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol=http",
                        "demo.remote.endpoint=https://api.example.test/v1",
                        "demo.remote.timeout=1500ms",
                        "demo.remote.max-attempts=4"
                )
                .run(context -> {
                    assertTrue(context.containsBean("remoteClient"));
                    RemoteClient client = context.getBean(RemoteClient.class);
                    assertEquals(
                            URI.create("https://api.example.test/v1"),
                            client.getEndpoint()
                    );
                    assertEquals(
                            Duration.ofMillis(1500), client.getTimeout()
                    );
                    assertEquals(4, client.getMaxAttempts());
                });
    }

    @Test
    void missingEnabledDoesNotActivate() {
        runner.withPropertyValues(
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("remoteClient"))
                );
    }

    @Test
    void falseEnabledDoesNotActivate() {
        runner.withPropertyValues(
                        "demo.remote.enabled=false",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("remoteClient"))
                );
    }

    @Test
    void otherProtocolDoesNotActivate() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol=grpc",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("remoteClient"))
                );
    }

    @Test
    void blankProtocolDoesNotActivate() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol= ",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("remoteClient"))
                );
    }

    @Test
    void omittedProtocolAndOptionalSettingsUseDefaults() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context -> {
                    RemoteClient client = context.getBean(RemoteClient.class);
                    assertEquals(
                            Duration.ofSeconds(2), client.getTimeout()
                    );
                    assertEquals(3, client.getMaxAttempts());
                });
    }

    @Test
    void userClientMakesDefaultBackOff() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol=http",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context -> {
                    assertTrue(context.containsBean("customRemoteClient"));
                    assertFalse(context.containsBean("remoteClient"));
                    assertEquals(
                            URI.create("https://user.example.test"),
                            context.getBean(RemoteClient.class).getEndpoint()
                    );
                });
    }

    @Test
    void enabledWithoutRequiredEndpointFailsFast() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol=http"
                )
                .run(context ->
                        assertNotNull(context.getStartupFailure())
                );
    }
}
```

### Ý nghĩa của tám test

| Test | Phép kiểm chứng |
|---|---|
| `enabledHttpBindsTypedConfiguration` | Condition match; đối tượng properties được bind sang `URI`, `Duration`, `int`; bean nhận đúng giá trị |
| `missingEnabledDoesNotActivate` | Không có cờ → không tạo bean |
| `falseEnabledDoesNotActivate` | Cờ tắt → không tạo bean |
| `otherProtocolDoesNotActivate` | Protocol khác HTTP → không tạo bean |
| `blankProtocolDoesNotActivate` | Protocol trắng → không bị hiểu nhầm là HTTP |
| `omittedProtocolAndOptionalSettingsUseDefaults` | Khi enabled=true, protocol mặc định HTTP; timeout và maxAttempts lấy mặc định JavaBean |
| `userClientMakesDefaultBackOff` | Bean người dùng được giữ, bean mặc định nhường chỗ |
| `enabledWithoutRequiredEndpointFailsFast` | Kích hoạt tính năng nhưng thiếu cấu hình bắt buộc → startup thất bại có ý nghĩa, không tự biến thành tắt feature |

**Lưu ý cuối:** test fail-fast chỉ kiểm tra `getStartupFailure()` khác `null`; trong dự án thực nên kiểm tra loại/nguyên nhân lỗi được kỳ vọng để phân biệt lỗi cấu hình với lỗi khác. Các test chỉ minh họa tính đúng đắn dự kiến; chưa phải kết quả từ một lần chạy trên dự án.

### Dependency và lệnh chạy

Với dự án Gradle Spring Boot 3.3.x đã dùng plugin/management tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy trên Linux/macOS:

```bash
./gradlew test --tests demo.RemoteAutoConfigurationTest
```

Chạy trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.RemoteAutoConfigurationTest
```

Với đúng bốn class và một test trong package `demo`, **kết quả kỳ vọng là 8 test pass**. Tên tệp và tên class public ở các mục 4–6 phải trùng nhau theo quy tắc Java; không gộp nhiều `public class` vào một tệp nguồn.

## 8. `Environment` và Binder có thể nhìn thuộc tính theo các cách khác nhau

### 8.1. Nguồn và độ ưu tiên

Spring Boot tổng hợp external configuration thành `Environment`. Nguồn có thể bao gồm `application.yml`, `application.properties`, profile, environment variables, system properties và command-line arguments. Giá trị cuối cùng chịu **thứ tự ưu tiên property source**. Do đó cờ `enabled` mà condition đọc phải là giá trị **thực tế của context đang chạy**, không nhất thiết là một dòng bạn nhìn thấy trong một file.

Ví dụ cấu hình gốc `enabled=false` có thể bị một nguồn ưu tiên cao hơn đặt thành `true`. Khi chẩn đoán feature bật ngoài dự kiến, kiểm tra property nguồn và precedence trước khi sửa code.

### 8.2. Relaxed binding và tên thuộc tính

Với `@ConfigurationProperties`, Spring Boot hỗ trợ relaxed binding, cho phép khóa dạng `max-attempts` đi vào field `maxAttempts`. Với việc đọc trực tiếp `Environment`, nên dùng **tên thuộc tính canonical dạng kebab-case** để ít phụ thuộc vào cách nguồn cấu hình biểu diễn tên.

Không nên dựa vào `Environment#getProperty("demo.remote.maxAttempts")` rồi cho rằng nó luôn tương đương với Binder đang xử lý `demo.remote.max-attempts` trong mọi loại `PropertySource`. Đối tượng properties là nơi phù hợp hơn cho nhiều giá trị có kiểu.

### 8.3. List và nested object

Nếu thư viện cần danh sách endpoint, proxy hoặc chiến lược retry phức tạp, `@ConfigurationProperties` có thể bind `List`/nested POJO theo quy tắc riêng. Một `Condition` dùng `Environment#getProperty("demo.remote.servers")` **không bảo đảm** nhìn thấy khóa cha khi dữ liệu khai báo dưới dạng `demo.remote.servers[0]`. Với điều kiện dựa vào **nội dung list** (ví dụ có phần tử hợp lệ), dùng `Binder` trong custom condition và kiểm tra dữ liệu bind được; đừng suy diễn từ một scalar property.

### 8.4. Không tạo bean trong condition

Đừng gọi trực tiếp `getBean(...)` hoặc tự `new RemoteProperties()` trong `matches()`:

- `getBean(...)` có thể thúc đẩy khởi tạo bean quá sớm, hoặc bean chưa tồn tại ở giai đoạn điều kiện.
- `new RemoteProperties()` chỉ cho object mặc định, **không bind** các giá trị external configuration.
- Inject `RemoteProperties` vào constructor của `Condition` không phải cách chuẩn: condition không thuộc vòng đời dependency injection thông thường như bean service.
- Một custom `Condition` cần dữ liệu kiểu phức tạp nên dùng `Binder.get(context.getEnvironment())`; chỉ nên dùng khi thực sự cần đánh giá dữ liệu có cấu trúc trong bước quyết định.

## 9. Validation, an toàn và sự nhất quán của cấu hình

**Quy tắc 1 — Dữ liệu bắt buộc thiếu phải có lỗi rõ ràng.** Nếu một feature được bật nhưng chưa khai báo endpoint, mặc định tắt âm thầm sẽ che lỗi vận hành. Có thể validate trong phương thức bean như ví dụ, hoặc dùng `@Validated` và Jakarta Bean Validation trên `@ConfigurationProperties` (cần implementation validation có sẵn, thường thông qua starter validation).

**Quy tắc 2 — Không coi enabled=true là “mọi cấu hình đã hợp lệ”.** Condition chỉ trả lời có bật không. Endpoint cần đúng scheme, timeout phải dương, retry phải nằm trong giới hạn phù hợp. Ranh giới giữa “bật” và “cấu hình hợp lệ” nên được giữ rõ.

**Quy tắc 3 — Không log toàn bộ properties nếu chứa credential.** `@ConfigurationProperties` có thể giữ API keys hoặc mật khẩu. Khi chẩn đoán, tránh in `toString()` của properties nếu nó có thông tin nhạy cảm; cấu hình Actuator `env`/`configprops` phải được bảo vệ và có chính sách che giấu dữ liệu.

**Quy tắc 4 — Back off đúng kiểu bean.** Trong library auto-configuration, người dùng có thể muốn thay implementation của `RemoteClient`. Đặt `@ConditionalOnMissingBean(RemoteClient.class)` trên phương thức bean, giữ chữ ký trả về `RemoteClient` rõ ràng. Nếu có nhiều loại client/interface, xác định chính xác abstraction mà user được phép override.

**Quy tắc 5 — Thứ tự auto-configuration ảnh hưởng điều kiện bean.** `@ConditionalOnMissingBean` kiểm tra định nghĩa đã được xử lý; khi thư viện phụ thuộc bean từ auto-configuration khác, dùng `@AutoConfiguration(after=...)` hoặc `afterName` nếu cần. Việc đọc `Environment` thường không phụ thuộc thứ tự đăng ký bean, nhưng **có thể** phụ thuộc khi nào property source tùy biến được thêm vào context.

**Quy tắc 6 — Phân biệt lỗi chuyển đổi với thiếu khóa.** Binder có thể báo lỗi với `timeout=abc` hoặc URI không hợp lệ. Đừng bắt mọi lỗi rồi chuyển thành mặc định, vì ứng dụng có thể chạy với giá trị nguy hiểm hoặc khác ý định.

## 10. Những lỗi thường gặp

1. **Dùng `@ConfigurationProperties` để quyết định đăng ký chính bean properties.** Thời điểm đánh giá condition và thời điểm binding khác nhau. Quyết định đơn giản bằng `@ConditionalOnProperty` hoặc custom `Condition` đọc `Environment`.
2. **Đọc trực tiếp `Environment` cho tất cả field rồi truyền chuỗi.** Mất kiểu dữ liệu và phân tán logic parse/validation; nên dùng object properties trong `@Bean`.
3. **Tưởng `@ConfigurationProperties` tự đăng ký bean.** Khi viết auto-configuration cho library, dùng `@EnableConfigurationProperties(RemoteProperties.class)` hoặc cơ chế phù hợp; annotation trên class chỉ mô tả binding.
4. **Đặt `matchIfMissing=true` cho tính năng opt-in.** Feature có thể bật ngay cả khi chưa khai báo cờ. Dùng mặc định false nếu yêu cầu explicit enablement.
5. **Không dùng `havingValue="true"` khi muốn chỉ cho phép true.** Với `@ConditionalOnProperty`, mặc định giá trị bất kỳ khác `false` có thể khiến condition match.
6. **Nhầm Spring profile với giá trị cờ.** Profile giúp chọn nguồn cấu hình; bản thân profile không chứng minh feature đã được bật bằng `enabled=true`.
7. **Tạo bean rồi kiểm tra enabled trong constructor.** Điều kiện đã quá muộn: bean có thể được đăng ký, kích hoạt dependency hoặc side effect trước khi code dừng. Hãy quyết định ở bước conditional registration.
8. **Quên cấu hình không hợp lệ khi enabled=true.** Cờ bật nên dẫn đến validation rõ ràng, không tự che lỗi thành bean mặc định sai.
9. **Giả định thay đổi thuộc tính sau startup sẽ tạo/gỡ bean.** Conditions chủ yếu được xét khi context được dựng; thay đổi động cần cơ chế riêng.
10. **Đặt condition trên cấu hình chưa xử lý đúng thứ tự.** Đối với bean conditions và auto-configuration khác, đảm bảo thứ tự đăng ký; không tự giả định một bean tương lai đã hiện diện.

## 11. Chẩn đoán khi bean không được tạo hoặc cấu hình sai

Đặt câu hỏi theo thứ tự:

1. **Điều kiện bật?** Giá trị có hiệu lực của `demo.remote.enabled` và `demo.remote.protocol` trong `Environment` là gì?
2. **Nguồn nào ghi đè?** File profile, biến môi trường, system property hoặc CLI có thay giá trị của ứng dụng không?
3. **Có qua condition không?** Dùng `--debug` khi khởi chạy Boot để xem **Condition Evaluation Report**. Nếu có Spring Boot Actuator và cho phép truy cập, endpoint `/actuator/conditions` có thể hiển thị lý do match/no-match.
4. **Properties đã được đăng ký chưa?** Kiểm tra `@EnableConfigurationProperties`, package scanning hoặc phương thức `@Bean`; `@ConfigurationProperties` đơn lẻ không đủ.
5. **Bind đúng kiểu chưa?** Xác nhận `endpoint` thành `URI`, `timeout` thành `Duration` và `max-attempts` thành `int`; xem lỗi binding nếu có.
6. **Bean do thư viện hay người dùng tạo?** `@ConditionalOnMissingBean` có thể khiến bean mặc định không xuất hiện vì user đã cung cấp `RemoteClient`; đó là hành vi hợp lệ.
7. **Đã thực sự chạy test các tình huống âm chưa?** Kiểm tra thiếu cờ, false, protocol khác, giá trị trống, thiếu endpoint và bean thay thế.

Trên ứng dụng có Actuator, `/actuator/env` và `/actuator/configprops` có thể hỗ trợ xác định giá trị cấu hình và đối tượng đã bind. Chúng cần cấu hình expose và bảo vệ truy cập phù hợp; tránh lộ secret khi chia sẻ báo cáo.

## 12. Ghi nhớ để thiết kế thư viện ổn định

- **`Environment`/`Condition`:** trả lời **“Có kích hoạt auto-configuration hay không?”** tại thời điểm đánh giá điều kiện.
- **`@ConfigurationProperties`:** trả lời **“Bean được cấu hình bằng giá trị có kiểu nào?”** sau khi config được đăng ký và binding diễn ra.
- Với một cờ, ưu tiên **`@ConditionalOnProperty`**. Với quy tắc phức tạp, dùng **`ConditionContext#getEnvironment()`**, hoặc Binder nếu phải xét cấu trúc.
- **`@EnableConfigurationProperties`** đăng ký properties class trong auto-configuration. Không yêu cầu ứng dụng phải component-scan package nội bộ thư viện.
- **`@ConditionalOnMissingBean`** hỗ trợ người dùng override bean mặc định mà vẫn giữ cơ chế cấu hình.
- **Validation và ma trận test** giúp phát hiện cả kích hoạt ngoài ý định lẫn cấu hình lỗi; không chỉ kiểm tra một trường hợp thành công.
- Thiết kế này phù hợp với Spring Boot 3.3.x và Java 17+, đồng thời tránh gắn quyết định khởi động vào thời điểm khởi tạo service.

### Tài liệu chính thức

- Spring Boot 3.3 Reference — Externalized Configuration, `Environment`, `@ConfigurationProperties` và relaxed binding: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 Javadoc — `ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 Javadoc — `ConfigurationProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Framework 6.1 Javadoc — `ConditionContext`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html
