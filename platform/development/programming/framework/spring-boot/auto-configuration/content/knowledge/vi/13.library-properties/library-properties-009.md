# Phân biệt thuộc tính công khai ổn định với chi tiết triển khai nội bộ

**Chủ đề:** Spring Boot Auto Configuration  
**Ngữ cảnh:** Thuộc tính thư viện  
**Mục tiêu:** Thiết kế một starter Spring Boot cho phép ứng dụng cấu hình những hành vi được hỗ trợ, trong khi thư viện vẫn có thể thay đổi cấu trúc và thuật toán nội bộ mà không phá vỡ cấu hình của người dùng.

## 1. Một thuộc tính trở thành hợp đồng công khai khi nào?

Giả sử thư viện `acme-dispatch-starter` cho phép ứng dụng khai báo:

```yaml
acme:
  dispatch:
    enabled: true
    connect-timeout: 2s
    max-attempts: 3
```

Khi thư viện công bố các khóa này trong tài liệu và các ví dụ triển khai, người dùng có quyền kỳ vọng:

- `acme.dispatch.enabled` xác định có kích hoạt client mặc định của starter hay không.
- `acme.dispatch.connect-timeout` điều khiển thời gian chờ thiết lập kết nối, có đơn vị rõ ràng.
- `acme.dispatch.max-attempts` điều khiển số lần thử, với quy ước **bao gồm lần thử ban đầu**.

Chúng là **giao diện cấu hình công khai** nếu thư viện cam kết hỗ trợ tên, kiểu, ngữ nghĩa, mặc định và cách xử lý giá trị sai của chúng trong các phiên bản tương thích.

Ngược lại, thư viện có thể đang dùng `InternalBackoffCalculator`, một `Executor`, `ThreadFactory`, pool kết nối hoặc thuật toán chọn transport cụ thể. Khi chúng không được công bố thành extension point, đó là **chi tiết triển khai** có thể thay đổi qua refactor. Người dùng không nên phải sửa YAML chỉ vì tác giả thư viện đổi một lớp helper.

**Ranh giới chính:** Public property diễn tả *hành vi người dùng được phép yêu cầu*; chi tiết nội bộ diễn tả *cách thư viện hiện thực hành vi ấy*. Một property không tự trở thành ổn định chỉ vì có thể gọi `Environment.getProperty(...)` hoặc được Binder chấp nhận.

## 2. Bảng phân biệt thực tế

| Thành phần | Ví dụ | Bản chất | Cam kết phù hợp |
| --- | --- | --- | --- |
| Cờ bật tính năng | `acme.dispatch.enabled` | Public property | Kiểu boolean, mặc định, điều kiện đăng ký bean |
| Timeout | `acme.dispatch.connect-timeout=2s` | Public property | Đơn vị, mức áp dụng, hành vi hết hạn |
| Chính sách retry cấp người dùng | `acme.dispatch.max-attempts=3` | Public property | Có bao gồm lần thử đầu, giới hạn hợp lệ |
| Lớp helper | `demo.internal.RetryPlanner` | Chi tiết nội bộ | Có thể thay khi contract vẫn đúng |
| Tên thread hoặc tên implementation | `dispatch-pool-0`, `JdkTransport` | Thường nội bộ | Không cam kết ổn định nếu không công bố |
| Bean `DispatchClient` có thể được người dùng cung cấp | `@Bean DispatchClient` | Extension point ở tầng Spring | Hợp đồng Java/bean riêng, không phải property |
| Chuỗi đọc ngầm | `acme.dispatch.internal-buffer-count` | Nguy cơ API ngầm | Cần loại bỏ hoặc công bố có chủ đích |
| Metadata gợi ý IDE | `spring-configuration-metadata.json` | Mô tả property | Không tự bảo đảm runtime bind hay tương thích |

Không được đánh đồng “có thể truy cập bằng kỹ thuật” với “được thư viện hỗ trợ chính thức”. Tuy nhiên, khi một khóa ẩn đã tồn tại trong bản phát hành và người dùng dựa vào nó, việc xóa có thể vẫn làm hỏng deployment. Vì thế cần tránh tạo API ngầm ngay từ đầu.

## 3. Cách quyết định property nào cần công khai

Trước khi thêm một khóa, cần trả lời:

1. **Nhu cầu thật của ứng dụng là gì?** Ví dụ timeout, bật/tắt tính năng, concurrency hay số retry. Nếu chỉ để xử lý một tình tiết implementation tạm thời, nên giữ nội bộ.
2. **Ngữ nghĩa có độc lập với implementation hiện tại không?** `connect-timeout` vẫn có nghĩa nếu thay HTTP client; `apache-pool-validation-thread-name` lại khóa người dùng vào một thư viện cụ thể.
3. **Kiểu và giới hạn là gì?** Với `Duration`, xác định đơn vị; với `max-attempts`, xác định ít nhất 1 và có nên giới hạn tối đa hay không.
4. **Mặc định khi không khai báo ra sao?** Mặc định cũng là hành vi public. Thay default có thể gây thay đổi lớn cho các ứng dụng không ghi khóa đó.
5. **Property tác động lên phạm vi nào?** Một client mặc định, toàn bộ starter, hay mọi bean có cùng interface?
6. **Có thể kiểm thử kết quả bên ngoài không?** Nếu chỉ có thể assert tên helper private, property có thể đang mô tả chi tiết triển khai hơn là hợp đồng.
7. **Khi người dùng cần tùy biến thuật toán toàn phần, có SPI hoặc bean extension không?** Không nên liên tục thêm cờ cấp thấp để thay thế cho một extension point rõ ràng.

Một API công khai tốt thường **ít key nhưng có ý nghĩa lâu dài**, thay vì hàng chục khóa gắn với từng helper.

## 4. Mô hình hóa public contract với `@ConfigurationProperties`

Spring Boot khuyến khích dùng `@ConfigurationProperties` cho nhóm cấu hình có kiểu. Một ví dụ Java 17:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.dispatch")
public record DispatchProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts
) {
}
```

Điều cần hiểu:

- `@ConfigurationProperties` khai báo nhóm property có tên chuẩn và kiểu rõ ràng.
- `@DefaultValue` chỉ được Binder dùng khi property không có; nó **không ghi giá trị đó vào toàn bộ `Environment`**.
- `Duration` xử lý đơn vị như `ms`, `s`, `m`, tránh nhập nhằng số nguyên “là giây hay millisecond?”.
- Record phù hợp với nhóm lựa chọn cấu hình bất biến lúc khởi động.
- Cơ chế relaxed binding cho phép Spring Boot liên hệ canonical kebab-case trong file với camelCase Java. Tài liệu nên chọn cách viết chuẩn nhất quán.

Không nên rải những dòng như `environment.getProperty("acme.dispatch.max-attempts")` ở nhiều chỗ rồi mỗi nơi tự parse một kiểu. Điều đó dễ lệch tên, thiếu validation, thiếu metadata và khó kiểm tra default. `@ConfigurationProperties` là điểm tập trung dữ liệu; **annotation tự thân không phải chính sách cam kết backward compatibility**.

### 4.1. Ranh giới namespace

Thư viện nên dùng một tiền tố riêng, chẳng hạn `acme.dispatch`, không tự ý chiếm namespace được Spring Boot dùng như `spring.*`, `server.*`, `management.*`. Các property của chính Spring Boot vẫn có thể được đọc khi tích hợp, nhưng nếu tạo key mới cho thư viện thì nên có namespace riêng.

Tên được tài liệu hóa nên dùng lower-case kebab-case:

```properties
acme.dispatch.enabled=true
acme.dispatch.connect-timeout=750ms
acme.dispatch.max-attempts=5
```

Đổi `max-attempts` sang `max-retries` không phải thao tác thay tên biến Java đơn thuần nếu người dùng đã lưu key cũ vào Kubernetes ConfigMap, Helm values hoặc hệ thống cấu hình CI/CD.

### 4.2. Validation là phần của contract

Một cấu hình số lần thử là 0 thường không có ý nghĩa. Có thể dùng Jakarta Bean Validation:

```java
@Validated
@ConfigurationProperties(prefix = "acme.dispatch")
public record DispatchProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("2s") Duration connectTimeout,
        @Min(1) @DefaultValue("3") int maxAttempts
) {
}
```

Đoạn trên cần các import tương ứng (`@Validated` của Spring, `@Min` của Jakarta Validation) và một implementation validation trên classpath, ví dụ `spring-boot-starter-validation`.

Kiểu có validation cho phép lỗi được phát hiện sớm khi ứng dụng khởi tạo, thay vì đợi tác vụ runtime gặp số retry không hợp lệ. Song những ràng buộc cần **được ghi trong tài liệu và test**, không chỉ nằm ngầm trong code.

## 5. Public default phải khớp với điều kiện auto-configuration

Một lỗi tinh vi là cho rằng `@DefaultValue("true")` trong `DispatchProperties` tự làm điều kiện đăng ký bean nhận biết `acme.dispatch.enabled=true`.

Thực tế hai cơ chế độc lập:

- **Binder** lấy default từ record nếu không thấy khóa.
- **`@ConditionalOnProperty`** kiểm tra giá trị hiệu lực trong `Environment`, không được cam kết tự đọc giá trị default trong record.

Ví dụ:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.dispatch",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
DispatchClient dispatchClient(DispatchProperties properties) {
    return new DispatchClient(
            properties.connectTimeout(),
            properties.maxAttempts());
}
```

Thiếu `acme.dispatch.enabled` làm condition **không khớp** vì `matchIfMissing=false`. Với record mặc định `enabled=false`, hai quyết định nhất quán. Nhưng nếu ai đó chỉ sửa `@DefaultValue("true")`, record có thể nhận `true` còn factory vẫn không tạo bean khi missing. Thay default public phải kiểm tra cả annotation điều kiện lẫn test.

Nếu feature thực sự mặc định bật, cần làm rõ `matchIfMissing=true` và default bind tương ứng. Không sử dụng default nội bộ như một lý do để phá hợp đồng đang được triển khai.

## 6. Ví dụ đầy đủ: Java 17, Spring Boot 3.3.5 và `ApplicationContextRunner`

Đây là một dự án Maven nhỏ minh họa ba public properties, validation và một extension point. Người học có thể biên dịch, chạy test mà không cần hệ thống gửi tác vụ thực hoặc kết nối mạng.

### 6.1. Cấu trúc tệp

```text
dispatch-starter-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DispatchProperties.java
    │   │   ├── DispatchClient.java
    │   │   └── DispatchAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/
        └── DispatchAutoConfigurationTest.java
```

### 6.2. Tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>dispatch-starter-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Dependency `spring-boot-configuration-processor` phục vụ quá trình build metadata gợi ý IDE, không phải thành phần điều khiển runtime binding. Trên các toolchain mới, annotation processing có thể cần được khai báo riêng trong Maven Compiler Plugin theo hướng dẫn chính thức.

### 6.3. `src/main/java/demo/DispatchProperties.java`

```java
package demo;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.dispatch")
public record DispatchProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("2s") Duration connectTimeout,
        @Min(1) @DefaultValue("3") int maxAttempts
) {
}
```

Hợp đồng công khai: `enabled=false`, timeout 2 giây, tối đa 3 lần thử tính cả lần đầu. `max-attempts` tối thiểu 1; mã test sẽ chứng minh một giá trị 0 không được chấp nhận.

Nếu cần mô tả property trong metadata từ record, có thể bổ sung Javadoc ở mức record với các tag `@param` cho ba component. Annotation processor hỗ trợ ghi nhận mô tả phù hợp từ mã nguồn; khi không suy luận được, có thể bổ sung metadata bằng file riêng. Không cần tạo một class properties chỉ để bộc lộ các field debug nội bộ.

### 6.4. `src/main/java/demo/DispatchClient.java`

```java
package demo;

import java.time.Duration;

public record DispatchClient(Duration connectTimeout, int maxAttempts) {
}
```

Trong ví dụ, client chỉ giữ cấu hình đã bind để dễ test. Một thư viện production có thể dùng HTTP client, queue hoặc retry helper khác; người dùng vẫn chỉ cần biết ngữ nghĩa public của timeout và attempts.

### 6.5. `src/main/java/demo/DispatchAutoConfiguration.java`

```java
package demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(DispatchProperties.class)
public class DispatchAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.dispatch",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    @ConditionalOnMissingBean(DispatchClient.class)
    DispatchClient dispatchClient(DispatchProperties properties) {
        return new DispatchClient(
                properties.connectTimeout(),
                properties.maxAttempts());
    }
}
```

Điều kiện property thể hiện **quyết định bật/tắt fallback client** của thư viện. Điều kiện missing bean là **extension point ở tầng Spring bean**, cho phép ứng dụng tự cung cấp `DispatchClient` và ngăn starter tạo thêm một bean cùng loại.

`@EnableConfigurationProperties` làm `DispatchProperties` được đăng ký và bind ngay khi application context dựng. Khi `enabled=false`, bean properties vẫn tồn tại nhưng fallback client không xuất hiện; đây là thiết kế có chủ đích.

### 6.6. Đăng ký auto-configuration

Tệp:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung đúng một dòng:

```text
demo.DispatchAutoConfiguration
```

Spring Boot 3.x dùng file imports này để khám phá auto-configuration của starter qua classpath. Việc thay tên class hoặc di chuyển package ảnh hưởng tới cấu trúc phân phối của starter, nhưng **không có nghĩa người dùng phải đổi tên property** đã công bố.

### 6.7. `src/test/java/demo/DispatchAutoConfigurationTest.java`

```java
package demo;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DispatchAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DispatchAutoConfiguration.class));

    @Test
    void missingPropertiesUsePublicDefaultsAndDisableClient() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DispatchProperties.class);
            DispatchProperties p = context.getBean(DispatchProperties.class);
            assertThat(p.enabled()).isFalse();
            assertThat(p.connectTimeout()).isEqualTo(Duration.ofSeconds(2));
            assertThat(p.maxAttempts()).isEqualTo(3);
            assertThat(context).doesNotHaveBean(DispatchClient.class);
        });
    }

    @Test
    void explicitEnableUsesDefaultParameters() {
        runner.withPropertyValues("acme.dispatch.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DispatchClient.class);
                    DispatchClient client = context.getBean(DispatchClient.class);
                    assertThat(client.connectTimeout())
                            .isEqualTo(Duration.ofSeconds(2));
                    assertThat(client.maxAttempts()).isEqualTo(3);
                });
    }

    @Test
    void documentedKeysChangeObservableBehavior() {
        runner.withPropertyValues(
                        "acme.dispatch.enabled=true",
                        "acme.dispatch.connect-timeout=750ms",
                        "acme.dispatch.max-attempts=5")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    DispatchClient client = context.getBean(DispatchClient.class);
                    assertThat(client.connectTimeout())
                            .isEqualTo(Duration.ofMillis(750));
                    assertThat(client.maxAttempts()).isEqualTo(5);
                });
    }

    @Test
    void explicitFalseTurnsDefaultOff() {
        runner.withPropertyValues("acme.dispatch.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(DispatchClient.class);
                });
    }

    @Test
    void invalidAttemptCountFailsValidation() {
        runner.withPropertyValues(
                        "acme.dispatch.enabled=true",
                        "acme.dispatch.max-attempts=0")
                .run(context ->
                        assertThat(context.getStartupFailure()).isNotNull());
    }

    @Test
    void undocumentedInternalLookingKeyHasNoSupportedEffect() {
        runner.withPropertyValues(
                        "acme.dispatch.enabled=true",
                        "acme.dispatch.internal-worker-count=100")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(DispatchProperties.class)
                            .maxAttempts()).isEqualTo(3);
                    assertThat(context.getBean(DispatchClient.class)
                            .maxAttempts()).isEqualTo(3);
                });
    }

    @Test
    void userProvidedClientMakesDefaultBackOff() {
        runner.withUserConfiguration(CustomClientConfiguration.class)
                .withPropertyValues("acme.dispatch.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DispatchClient.class);
                    assertThat(context.getBean(DispatchClient.class)
                            .maxAttempts()).isEqualTo(9);
                    assertThat(context).hasBean("customClient");
                    assertThat(context).doesNotHaveBean("dispatchClient");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {
        @Bean
        DispatchClient customClient() {
            return new DispatchClient(Duration.ofSeconds(9), 9);
        }
    }
}
```

Chạy trong thư mục `dispatch-starter-demo`:

```bash
mvn test
```

Kết quả mong đợi khi JDK 17+, Maven và các dependency đã có:

```text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
```

Đây là phần tổng kết thường thấy của Maven Surefire; mã không tự in stdout. Nếu môi trường không có Maven/JDK hoặc không tải được dependency, đó là lỗi môi trường thực thi chứ không nên tự tuyên bố test đã chạy thành công.

Các test kiểm tra chính **hành vi đã hứa**: mặc định, bật/tắt, giá trị typed, validation và bean extension. Chúng tránh phụ thuộc tên helper hoặc cách thực hiện retry bên trong.

**Lưu ý về khóa lạ:** `@ConfigurationProperties` mặc định có thể bỏ qua unknown fields. Test `internal-worker-count` minh họa khóa trông như cấu hình nội bộ nhưng không được record đọc và không thay đổi hành vi. Một khóa lạ được chấp nhận mà không báo lỗi **không chứng minh đó là cấu hình được hỗ trợ**. Nếu ứng dụng cần từ chối typo một cách nghiêm ngặt, phải thiết kế chính sách phát hiện/validation phù hợp.

## 7. Metadata: công cụ khám phá, không phải cơ chế runtime

Spring Boot có thể sinh:

```text
META-INF/spring-configuration-metadata.json
```

File này giúp IDE gợi ý tên, kiểu, default, mô tả và deprecation. Nếu dùng `spring-boot-configuration-processor` đúng cách, phần lớn metadata được tạo từ lớp `@ConfigurationProperties`.

Một entry **minh họa**:

```json
{
  "properties": [
    {
      "name": "acme.dispatch.connect-timeout",
      "type": "java.time.Duration",
      "description": "Thời gian chờ kết nối của client mặc định.",
      "defaultValue": "2s"
    }
  ]
}
```

Đây là JSON rút gọn để giải thích cấu trúc metadata, không phải kết quả byte-for-byte của Maven build. Metadata thật có thể chứa `groups`, `sourceType`, `hints` và nhiều properties.

Có thể bổ sung metadata cho các tình huống processor không suy luận được bằng:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Annotation processor hợp nhất metadata bổ sung với metadata tự sinh. Không cần tạo file bổ sung khi thông tin hiện tại đã được mô tả chính xác.

Ba tầng không nên lẫn lộn:

| Tầng | Làm gì? | Không làm gì? |
| --- | --- | --- |
| `@ConfigurationProperties`/Binder | Đọc, đổi kiểu, bind/validate giá trị tại runtime | Không tự cam kết backward compatibility giữa các release |
| Configuration metadata | Đưa thông tin cho IDE, tooling, documentation generator | Không tự khiến key hoạt động nếu code không đọc nó |
| Tài liệu, tests và version policy | Công bố và bảo vệ hợp đồng mà người dùng dựa vào | Không tự thay thế implementation runtime |

Một key xuất hiện trong metadata không chứng minh bean điều kiện đã được tạo; cần kiểm thử `ApplicationContextRunner` và hành vi. Một key bị đọc ngầm từ `Environment` nhưng không trong metadata vẫn có thể tác động runtime; đó là lý do tránh API ngầm.

## 8. Public property và chi tiết nội bộ trong quá trình refactor

Giả sử bản v1 dùng `LegacyHttpTransport`, bản v2 dùng `JdkHttpClientTransport`. Nếu user-facing behavior của `connect-timeout=2s` vẫn tương đương, giữ nguyên public key.

**Thay đổi nội bộ có thể không phá hợp đồng:**

- Đổi tên helper/package private.
- Thay thuật toán chọn thread pool, miễn hành vi public không đổi.
- Thay thư viện HTTP mà vẫn áp đúng timeout/retry như đã công bố.
- Tối ưu cache và cơ chế lập lịch bên trong.
- Đổi cách wire những bean không được public như extension point.

**Những thay đổi có thể phá hợp đồng dù code Java vẫn compile:**

- Đổi `max-attempts` từ tổng số lần thử thành số lần retry **ngoài lần đầu**.
- Đổi default `enabled` từ `false` sang `true`.
- Đổi timeout mặc định từ `2s` sang `30s`.
- Xóa `acme.dispatch.connect-timeout` hoặc thay đơn vị ngầm.
- Thay quy tắc ưu tiên property khi người dùng đặt nhiều nguồn cấu hình.
- Bỏ việc back-off của bean mặc định dù thư viện đã công bố bean override là cách tùy biến được hỗ trợ.

Đừng đánh đồng đổi field Java trong thư viện với đổi hợp đồng của người vận hành. Một property là giao diện giữa ứng dụng và thư viện ngay cả khi người dùng không biên dịch lại mã nguồn nào.

### 8.1. Có nên thêm một “property nội bộ” để debug?

Ví dụ mã nội bộ:

```java
int workers = environment.getProperty(
        "acme.dispatch.executor.pool-implementation-size",
        Integer.class,
        4);
```

Đây chỉ là đoạn minh họa nằm trong một method có sẵn và cần biến `environment` kiểu Spring `Environment`.

Nếu người dùng phát hiện key và bắt đầu sử dụng, việc thay executor có thể gây hỏng behavior của họ dù key không được tài liệu hóa. Tốt hơn:

- Nếu **concurrency** là nhu cầu chính đáng, tạo property trung lập, ví dụ `acme.dispatch.concurrency`, có mặc định/ràng buộc và test rõ.
- Nếu chỉ phục vụ debug một bug, dùng log level, metric hoặc test hook chuyên biệt; tránh đưa một property kỹ thuật không ổn định vào cấu hình production.
- Nếu cần thay toàn bộ chiến lược, thiết kế SPI/bean override rõ hơn là dùng tên class implementation nằm trong property.

Không nên đặt tên như `acme.dispatch.netty.worker-loops` khi thư viện muốn giữ quyền chuyển sang implementation khác và ứng dụng không thực sự cần kiểm soát Netty.

## 9. Thay đổi, deprecate và di trú property công khai

Một thuộc tính đã công bố không nên bị đổi tên/xóa âm thầm. Kế hoạch di trú mẫu khi đổi từ `acme.dispatch.retry-count` sang `acme.dispatch.max-attempts`:

1. Định nghĩa ý nghĩa và default của tên mới. Đảm bảo việc rename không vô tình đổi ngữ nghĩa.
2. Trong thời gian chuyển tiếp, **code runtime phải thực sự đọc/bind cả key cũ và key mới** nếu thư viện cam kết tương thích.
3. Xác định quy tắc rõ ràng khi người dùng khai báo cả hai, ví dụ key mới được ưu tiên; thêm test.
4. Ghi deprecation metadata với lý do, thời điểm, replacement và thông báo migration.
5. Chỉ xóa đường bind key cũ theo chính sách versioning đã công bố; cập nhật release notes và migration guide.

Ví dụ cấu trúc metadata deprecation:

```json
{
  "properties": [
    {
      "name": "acme.dispatch.retry-count",
      "type": "java.lang.Integer",
      "deprecation": {
        "level": "warning",
        "reason": "Đã đổi tên thành max-attempts để mô tả tổng số lần thử.",
        "replacement": "acme.dispatch.max-attempts",
        "since": "2.1.0"
      }
    }
  ]
}
```

**Không dán JSON này vào demo và cho rằng tên cũ đã tự được hỗ trợ.** Metadata chỉ gửi gợi ý đến tooling; chính code phải thực hiện alias/binding. Mức `warning` thường dành cho property còn được quản lý trong quá trình di trú. Mức `error` mô tả property không còn được quản lý; chuyển level metadata không tự động vô hiệu hóa một đoạn code vẫn tiếp tục đọc property.

`@DeprecatedConfigurationProperty` có thể được dùng trên getter phù hợp của một class `@ConfigurationProperties` theo kiểu JavaBean để tạo metadata. Đừng nhầm annotation đánh dấu deprecation này với một cơ chế tự tạo alias, và không mặc định áp nó vào record component.

**Điểm cần review trong breaking change:** đổi tên, đổi kiểu, đổi đơn vị, đổi mặc định, đổi ngữ nghĩa, bỏ giá trị từng hợp lệ, thay validation và thay cách ưu tiên nguồn cấu hình. Tất cả có thể phá deployment cũ dù Java code không đổi.

## 10. Public không có nghĩa là công khai giá trị bí mật

Tên của một cấu hình có thể public, nhưng giá trị của nó vẫn là secret:

```properties
acme.dispatch.api-token=${DISPATCH_TOKEN}
```

Nếu thư viện chính thức hỗ trợ một key cho credential, cần mô tả cách cấp bí mật an toàn, tránh log giá trị hoặc đưa ra thông báo lỗi lộ token. Chỉ tài liệu hóa **tên, kiểu và hành vi** của key; không bao giờ yêu cầu người dùng commit credential thật vào repository.

Các endpoint như `/actuator/env` và `/actuator/configprops` có thể phục vụ chẩn đoán nhưng phải giới hạn truy cập và cấu hình che thông tin nhạy cảm. “Public property” là khái niệm ổn định API, hoàn toàn không phải quyền tiết lộ dữ liệu.

## 11. Gỡ lỗi cấu hình không có tác dụng

Nếu người dùng đặt `acme.dispatch.connect-timeout=750ms` nhưng client vẫn dùng mặc định:

1. Đảm bảo **đúng prefix/key**; tránh nhầm `connection-timeout` với `connect-timeout`.
2. Xem giá trị **hiệu lực** trong Spring `Environment`, bao gồm YAML, profile, môi trường runtime và command-line. Đừng chỉ kiểm tra một file.
3. Xem `DispatchProperties` đã được đăng ký bằng `@EnableConfigurationProperties` hoặc scanning chưa.
4. Xem property có bind đúng `Duration` và có lỗi conversion/validation không.
5. Xem `@ConditionalOnProperty` đã khớp chưa; `matchIfMissing` và default record không phải cùng cơ chế.
6. Xem `@ConditionalOnMissingBean` có back off vì ứng dụng tự cung cấp `DispatchClient` không. Khi đó client sử dụng không nhất thiết là bean fallback của thư viện.
7. Dùng Condition Evaluation Report bằng `--debug` hoặc `/actuator/conditions` khi endpoint được bật và bảo vệ phù hợp. Endpoint `configprops` giúp kiểm tra binding, nhưng đừng tiết lộ secret.

Để chẩn đoán library API, ưu tiên test theo **giá trị đầu ra/bean behavior**. Chỉ assert tên class helper private sẽ khiến refactor hợp lệ bị lỗi test, trong khi không chứng minh điều người dùng cần.

## 12. Checklist phát hành một public property

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Tên canonical và namespace | Rõ ràng, ổn định, không chiếm namespace người khác |
| Kiểu và đơn vị | `boolean`, `Duration`, số nguyên có mô tả |
| Mặc định và missing branch | Binder và condition nhất quán |
| Validation | Giá trị vô nghĩa báo lỗi rõ |
| Tài liệu | Có ví dụ YAML/properties và giới hạn |
| Configuration metadata | IDE gợi ý đúng tên/kiểu/mô tả |
| Runtime tests | Missing, true/false, override, invalid, user bean |
| Compatibility tests | Không mất alias/đổi meaning ngoài kế hoạch |
| Nội bộ | Không vô tình expose class/helper/secret |
| Release notes | Nêu thêm/sửa/deprecate property rõ ràng |

Trong Maven có thể đóng gói:

```bash
mvn package
```

Sau build, kiểm tra artifact có `META-INF/spring-configuration-metadata.json` và `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` khi annotation processor được bật và auto-configuration được đóng gói đúng. Metadata có thể chưa đủ nếu processor không chạy hoặc thiếu thông tin nguồn; khi đó sửa build/config, không thay thế kiểm thử hành vi bằng niềm tin rằng IDE autocomplete đã chứng minh runtime.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Nếu thư viện thay Netty client bằng JDK HttpClient nhưng vẫn áp đúng `connect-timeout`, có bắt buộc đổi property không?  
**Đáp án:** Không. Timeout là ngữ nghĩa public độc lập với lớp triển khai.

**Câu 2.** Một lớp helper tên `RetryPlanner` bị xóa khi refactor. Có phải breaking change không?  
**Đáp án:** Không nếu đây thực sự là chi tiết nội bộ, không phải phần hợp đồng/extension point được công bố và hành vi public được bảo toàn.

**Câu 3.** Đổi default của `enabled` từ `false` sang `true` trong record có tự bật fallback khi `@ConditionalOnProperty(matchIfMissing=false)` không?  
**Đáp án:** Không. Binder default không tự thêm property vào `Environment`; phải phối hợp condition đúng chính sách.

**Câu 4.** Metadata có `"replacement"` cho một property cũ. Spring Boot có tự động nhận alias không?  
**Đáp án:** Không. Metadata không triển khai đường bind/runtime migration.

**Câu 5.** Bất kỳ chuỗi nào được Binder bỏ qua mà không báo lỗi có là property được hỗ trợ không?  
**Đáp án:** Không. Unknown key có thể bị bỏ qua; chỉ key có hợp đồng rõ và code áp dụng đúng mới là lựa chọn được hỗ trợ.

**Câu 6.** Vì sao đổi từ “ba lần thử tổng cộng” sang “ba lần retry sau lần đầu” có thể phá compatibility?  
**Đáp án:** Hành vi runtime và tải dịch vụ thay đổi dù tên và kiểu property không đổi.

**Câu 7.** Người dùng muốn thay toàn bộ implementation, có nên expose tên class helper private làm property?  
**Đáp án:** Thường nên thiết kế extension point/bean override chính thức; public hóa implementation class khiến refactor trở thành breaking change.

## 14. Các nguyên tắc phải nhớ

- **Public configuration contract** gồm tên, ý nghĩa, kiểu, đơn vị, default, validation, phạm vi và chính sách versioning.
- **Internal implementation** gồm class helper, thuật toán, tên thread, tên bean không công bố và cách wiring có thể đổi khi giữ nguyên hợp đồng.
- `@ConfigurationProperties` và metadata giúp tạo API cấu hình có kiểu, dễ khám phá; chúng không tự quyết định tương thích của phiên bản.
- Default trong Binder khác với quyết định của `@ConditionalOnProperty` khi missing. Luôn test cả hai.
- `@ConditionalOnMissingBean` có thể tạo extension point riêng ở tầng Spring bean; nó không đồng nghĩa với property cấu hình.
- Metadata deprecation không tự sửa key cũ. Muốn hỗ trợ chuyển tiếp phải triển khai và kiểm thử alias ở runtime.
- Ít key ổn định, tài liệu rõ ràng và test hành vi đáng tin hơn một danh sách dài các thông số gắn với implementation tạm thời.

### Tài liệu chính thức

- [Spring Boot 3.3 — Externalized Configuration và Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html)
- [Spring Boot — Generating Metadata with Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot — Configuration Metadata Format và Deprecation](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
