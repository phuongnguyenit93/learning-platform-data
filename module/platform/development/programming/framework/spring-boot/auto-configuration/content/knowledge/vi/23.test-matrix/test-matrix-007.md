# Kiểm chứng quan hệ thứ tự giữa nhiều lớp tự cấu hình

## 1. Vì sao thứ tự auto-configuration ảnh hưởng kết quả?

Một custom starter thường có nhiều lớp tự cấu hình. Ví dụ:

- Cấu hình nền tạo `FoundationService` mặc định.
- Cấu hình tính năng tạo `FeatureService` nếu đã có `FoundationService`.
- Cấu hình audit tạo `AuditService` nếu `FeatureService` đã được đăng ký.

Ba lớp này có quan hệ phụ thuộc về **thời điểm xử lý bean definitions**. Nếu consumer được xử lý trước provider, `@ConditionalOnBean` có thể chưa nhìn thấy bean definition mà provider sẽ đăng ký sau đó. Khi đó condition không match và bean consumer bị bỏ qua.

Spring Boot cung cấp metadata để sắp xếp các auto-configuration:

- `@AutoConfiguration(after = ...)` và `afterName`.
- `@AutoConfiguration(before = ...)` và `beforeName`.
- `@AutoConfigureAfter` và `@AutoConfigureBefore`.
- `@AutoConfigureOrder` cho thứ tự tổng quát giữa các cấu hình không cần tham chiếu trực tiếp lẫn nhau.

Điều cần kiểm chứng là **cấu hình provider được xử lý trước cấu hình consumer**, để condition nhìn thấy đúng bean definition. Không nên suy ra thứ tự chỉ từ tên class, thứ tự dòng trong file imports hoặc thứ tự các đối số truyền vào một test.

## 2. Ba loại thứ tự cần phân biệt

### 2.1. Thứ tự áp dụng auto-configuration

Đây là thứ tự Spring Boot xử lý các lớp auto-configuration và đăng ký bean definitions từ chúng.

Ví dụ:

```text
FoundationAutoConfiguration
        |
        v
FeatureAutoConfiguration
        |
        v
AuditAutoConfiguration
```

Trong sơ đồ, Foundation phải được xử lý trước Feature; Feature phải được xử lý trước Audit. Đây là quan hệ cần thiết khi condition của lớp sau kiểm tra bean do lớp trước cung cấp.

### 2.2. Thứ tự khởi tạo bean instance

Sau khi bean definitions đã được đăng ký, Spring mới tạo các object khi context refresh và khi chúng cần được sử dụng.

Thứ tự tạo object được quyết định bởi dependency graph của bean, constructor/factory-method injection, quan hệ `@DependsOn` và lifecycle của container.

Ví dụ:

```java
@Bean
FeatureService featureService(FoundationService foundationService) {
    return new FeatureService(foundationService.name());
}
```

Tham số `FoundationService` tạo dependency giữa hai bean. Spring phải resolve dependency đó khi tạo `FeatureService`. Quan hệ này khác với việc Spring Boot xử lý lớp `FoundationAutoConfiguration` trước `FeatureAutoConfiguration`.

**Điểm mấu chốt:** `@AutoConfiguration(after = ...)` chỉ sắp thứ tự xử lý auto-configuration/bean definitions. Nó không phải lệnh khởi tạo object trước sau.

### 2.3. Thứ tự trong collection và callback

`@Order`, `Ordered` hoặc `@Priority` có thể ảnh hưởng thứ tự một số danh sách bean, plugin, interceptor hoặc callback được inject/thu thập. Chúng không phải công cụ thay thế metadata sắp xếp auto-configuration.

Để sắp thứ tự auto-configuration, dùng `@AutoConfiguration` metadata hoặc `@AutoConfigureOrder`. Để tạo dependency giữa bean instance, dùng injection hoặc `@DependsOn` khi phù hợp.

## 3. Các cơ chế sắp xếp trong Spring Boot 3.3

### 3.1. `after` và `before` bằng class

Cấu hình consumer khai báo cần được áp dụng sau provider:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {
    // Các @Bean của feature.
}
```

Cấu hình provider có thể khai báo chiều ngược lại:

```java
@AutoConfiguration(before = FeatureAutoConfiguration.class)
public class FoundationAutoConfiguration {
    // Các @Bean nền.
}
```

Thông thường chỉ cần khai báo **một phía** của quan hệ. Tránh khai báo cả hai chiều hoặc tạo quan hệ vòng.

- `after`: các auto-configuration được nêu phải được áp dụng trước lớp hiện tại.
- `before`: lớp hiện tại phải được áp dụng trước các auto-configuration được nêu.

Các thuộc tính nhận class, giúp compiler phát hiện lỗi tên lớp khi dependency có mặt.

### 3.2. `afterName` và `beforeName` bằng tên lớp

Khi không muốn tạo liên kết compile-time tới một auto-configuration tùy chọn, dùng tên fully-qualified:

```java
@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration"
)
public class AcmeJsonFeatureAutoConfiguration {
}
```

Cách dùng chuỗi hữu ích khi lớp được tham chiếu có thể không có trong một số cấu hình dependency. Không cần import class đó chỉ để khai báo thứ tự.

Tên phải chính xác. Với nested class, tên dùng dấu `$` để phân cách class ngoài và class lồng nhau.

### 3.3. Annotation riêng `@AutoConfigureAfter` và `@AutoConfigureBefore`

Spring Boot cũng có hai annotation chuyên dụng:

```java
@AutoConfigureAfter(FoundationAutoConfiguration.class)
@Configuration(proxyBeanMethods = false)
public class FeatureAutoConfiguration {
}
```

```java
@AutoConfigureBefore(FeatureAutoConfiguration.class)
@Configuration(proxyBeanMethods = false)
public class FoundationAutoConfiguration {
}
```

Trong code mới dùng `@AutoConfiguration(after = ...)` và `@AutoConfiguration(before = ...)` thường gọn hơn, vì `@AutoConfiguration` đã là annotation chuyên cho auto-configuration và cung cấp các thuộc tính alias tương ứng. Hai annotation riêng vẫn hữu ích khi cấu hình dùng kiểu `@Configuration` truyền thống hoặc khi đọc code cũ.

### 3.4. `@AutoConfigureOrder` cho các cấu hình độc lập

Có lúc hai auto-configuration cần một thứ tự tương đối nhưng không nên tham chiếu trực tiếp class của nhau. Khi đó có thể dùng:

```java
@AutoConfigureOrder(-10)
@AutoConfiguration
public class EarlyDiagnosticsAutoConfiguration {
}

@AutoConfigureOrder(20)
@AutoConfiguration
public class LateDiagnosticsAutoConfiguration {
}
```

`@AutoConfigureOrder` là biến thể dành riêng cho auto-configuration của cơ chế `@Order`. Giá trị mặc định là `0`; giá trị order nhỏ hơn có mức ưu tiên sắp xếp cao hơn.

Không nên dùng `@AutoConfigureOrder` để thay thế một quan hệ dependency cụ thể. Nếu Feature bắt buộc phải nhìn thấy bean từ Foundation, khai báo `after = FoundationAutoConfiguration.class` diễn đạt ý định rõ hơn và bền vững hơn một cặp số order tùy ý.

### 3.5. So sánh nhanh

| Cơ chế | Dùng khi | Có diễn đạt quan hệ phụ thuộc cụ thể? |
| --- | --- | --- |
| `after` / `before` | Biết class auto-configuration liên quan | Có |
| `afterName` / `beforeName` | Biết tên class nhưng muốn tránh liên kết compile-time | Có |
| `@AutoConfigureAfter` / `@AutoConfigureBefore` | Cấu hình truyền thống dùng annotation riêng | Có |
| `@AutoConfigureOrder` | Các cấu hình độc lập cần thứ tự tổng quát | Không |
| `@DependsOn` | Một bean instance cần bean khác được khởi tạo trước | Không; chỉ áp dụng lifecycle bean |
| `@Order` | Sắp thứ tự một số collection/callback theo contract tương ứng | Không; không phải metadata auto-configuration |

## 4. Vì sao `@ConditionalOnBean` và `@ConditionalOnMissingBean` nhạy với thứ tự?

Các bean condition được đánh giá dựa trên bean definitions đã được xử lý tại thời điểm condition chạy.

Ví dụ provider:

```java
@AutoConfiguration
public class FoundationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationService.class)
    FoundationService foundationService() {
        return new FoundationService("default");
    }
}
```

Consumer:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    FeatureService featureService(FoundationService foundation) {
        return new FeatureService("uses:" + foundation.name());
    }
}
```

Nếu provider được xử lý trước:

1. `FoundationAutoConfiguration` được áp dụng.
2. `@ConditionalOnMissingBean` không tìm thấy user bean phù hợp nên default bean definition được đăng ký.
3. `FeatureAutoConfiguration` được áp dụng sau.
4. `@ConditionalOnBean` nhìn thấy `FoundationService` và đăng ký `FeatureService`.

Nếu consumer được xử lý trước provider, condition có thể đánh giá khi bean definition nền chưa xuất hiện. `FeatureService` không được đăng ký. Khi provider được xử lý sau, Spring không tự quay lại đánh giá condition đã chạy trước đó như một lần refresh mới.

Đó là lý do Spring Boot khuyến nghị dùng `@ConditionalOnBean` và `@ConditionalOnMissingBean` trong auto-configuration, vì các auto-configuration được xử lý sau user bean definitions. Khi có quan hệ giữa nhiều auto-configuration, cần khai báo thứ tự rõ ràng.

### Class-level condition và method-level condition

Điều kiện có thể đặt trên class hoặc trên từng `@Bean`:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
@ConditionalOnBean(FoundationService.class)
public class FeatureAutoConfiguration {
    // Mọi bean trong lớp phụ thuộc FoundationService.
}
```

Hoặc:

```java
@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    FeatureService featureService(FoundationService foundation) {
        return new FeatureService("uses:" + foundation.name());
    }

    @Bean
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

Ở cách thứ hai, chỉ `featureService` phụ thuộc condition; `featureMetrics` vẫn có thể được đăng ký. Chọn phạm vi nhỏ nhất phù hợp với dependency thực tế để tránh vô tình loại cả nhóm bean không phụ thuộc.

## 5. Cấu trúc ví dụ kiểm chứng ba lớp auto-configuration

Ví dụ dưới đây dùng Spring Boot 3.3.5 và Java 17+. Ta xây một chuỗi ba lớp:

- `FoundationAutoConfiguration` tạo bean nền.
- `FeatureAutoConfiguration` dùng bean nền và tạo feature.
- `AuditAutoConfiguration` dùng feature và tạo audit component.

Ta cố ý truyền các class vào `AutoConfigurations.of` theo thứ tự ngược trong test. Nếu metadata đúng, test vẫn thấy đầy đủ ba bean.

### 5.1. Cấu trúc project

```text
auto-configuration-order-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/api/
    │   │   ├── FoundationService.java
    │   │   ├── FeatureService.java
    │   │   └── AuditService.java
    │   ├── java/demo/autoconfigure/
    │   │   ├── FoundationAutoConfiguration.java
    │   │   ├── FeatureAutoConfiguration.java
    │   │   └── AuditAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/demo/autoconfigure/
        └── AutoConfigurationOrderingTests.java
```

### 5.2. `pom.xml`

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
    <artifactId>auto-configuration-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-autoconfigure` cung cấp annotation và condition. `spring-boot-starter-test` chỉ dùng ở test scope để có JUnit, AssertJ, `ApplicationContextRunner` và `AutoConfigurations`.

### 5.3. Ba kiểu API

**`src/main/java/demo/api/FoundationService.java`**

```java
package demo.api;

public record FoundationService(String name) {
}
```

**`src/main/java/demo/api/FeatureService.java`**

```java
package demo.api;

public record FeatureService(String description) {
}
```

**`src/main/java/demo/api/AuditService.java`**

```java
package demo.api;

public record AuditService(String description) {
}
```

Các record chỉ giữ dữ liệu để test có thể kiểm tra rõ bean nào đã được sử dụng.

### 5.4. Provider: `FoundationAutoConfiguration.java`

**`src/main/java/demo/autoconfigure/FoundationAutoConfiguration.java`**

```java
package demo.autoconfigure;

import demo.api.FoundationService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class FoundationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FoundationService.class)
    public FoundationService foundationService() {
        return new FoundationService("default");
    }
}
```

Provider tạo default nếu ứng dụng chưa cung cấp `FoundationService`. Nếu user đã khai báo bean cùng kiểu, auto-configuration nhường chỗ.

### 5.5. Consumer thứ nhất: `FeatureAutoConfiguration.java`

**`src/main/java/demo/autoconfigure/FeatureAutoConfiguration.java`**

```java
package demo.autoconfigure;

import demo.api.FeatureService;
import demo.api.FoundationService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FoundationAutoConfiguration.class)
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(FoundationService.class)
    public FeatureService featureService(
            FoundationService foundationService) {

        return new FeatureService(
                "uses:" + foundationService.name());
    }
}
```

`after` bảo đảm provider được xử lý trước khi condition của feature được đánh giá. Tham số `FoundationService` đồng thời tạo dependency giữa hai bean instance khi Spring khởi tạo `FeatureService`.

### 5.6. Consumer thứ hai: `AuditAutoConfiguration.java`

**`src/main/java/demo/autoconfigure/AuditAutoConfiguration.java`**

```java
package demo.autoconfigure;

import demo.api.AuditService;
import demo.api.FeatureService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = FeatureAutoConfiguration.class)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnBean(FeatureService.class)
    public AuditService auditService(FeatureService featureService) {
        return new AuditService(
                "audit:" + featureService.description());
    }
}
```

Audit cần Feature, vì vậy khai báo `after = FeatureAutoConfiguration.class`. Ta có chuỗi quan hệ:

```text
FoundationAutoConfiguration
          |
          | after
          v
FeatureAutoConfiguration
          |
          | after
          v
AuditAutoConfiguration
```

Nghĩa của mũi tên là cấu hình ở phía trên phải được xử lý trước cấu hình ở phía dưới.

### 5.7. Đăng ký auto-configuration candidate

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
demo.autoconfigure.AuditAutoConfiguration
demo.autoconfigure.FeatureAutoConfiguration
demo.autoconfigure.FoundationAutoConfiguration
```

File cố ý liệt kê theo thứ tự ngược để nhấn mạnh rằng thứ tự dòng trong imports không phải hợp đồng dependency. Spring Boot sắp xếp các candidate theo metadata `before`/`after` trước khi áp dụng.

Auto-configuration nên nằm trong package riêng và được đăng ký qua file imports; không dùng component scan của ứng dụng để dò tìm các lớp auto-configuration.

## 6. Kiểm chứng bằng `ApplicationContextRunner`

### 6.1. Test với thứ tự đầu vào đảo ngược

Tạo file **`src/test/java/demo/autoconfigure/AutoConfigurationOrderingTests.java`**:

```java
package demo.autoconfigure;

import demo.api.AuditService;
import demo.api.FeatureService;
import demo.api.FoundationService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderingTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AuditAutoConfiguration.class,
                            FeatureAutoConfiguration.class,
                            FoundationAutoConfiguration.class));

    @Test
    void metadataOrdersThreeConfigurationsEvenWhenInputIsReversed() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();

            assertThat(context).hasSingleBean(FoundationService.class);
            assertThat(context).hasSingleBean(FeatureService.class);
            assertThat(context).hasSingleBean(AuditService.class);

            assertThat(context.getBean(FoundationService.class).name())
                    .isEqualTo("default");

            assertThat(context.getBean(FeatureService.class).description())
                    .isEqualTo("uses:default");

            assertThat(context.getBean(AuditService.class).description())
                    .isEqualTo("audit:uses:default");
        });
    }

    @Test
    void downstreamConfigurationsAreSkippedWhenProviderIsAbsent() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        AuditAutoConfiguration.class,
                        FeatureAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FoundationService.class);
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                    assertThat(context).doesNotHaveBean(AuditService.class);
                });
    }

    @Test
    void userDefinedFoundationBeanIsVisibleToBothConsumers() {
        this.runner
                .withUserConfiguration(UserFoundationConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FoundationService.class);
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context).hasSingleBean(AuditService.class);

                    assertThat(context.getBean(FoundationService.class).name())
                            .isEqualTo("custom");

                    assertThat(context.getBean(FeatureService.class).description())
                            .isEqualTo("uses:custom");

                    assertThat(context.getBean(AuditService.class).description())
                            .isEqualTo("audit:uses:custom");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFoundationConfiguration {

        @Bean
        FoundationService customFoundationService() {
            return new FoundationService("custom");
        }
    }
}
```

### 6.2. Ý nghĩa từng test

**Test 1 — metadata sắp đúng thứ tự**

Các class được truyền theo thứ tự `Audit`, `Feature`, `Foundation`. Nhờ metadata, provider được xử lý trước hai consumer. Ba bean đều xuất hiện và giá trị của từng bean chứng minh dependency được nối đúng.

**Test 2 — thiếu provider**

Chỉ nạp hai consumer. Không có `FoundationService` nên `FeatureService` không được đăng ký; vì không có `FeatureService`, `AuditService` cũng không được đăng ký. Context vẫn khởi động thành công vì cả hai consumer được bảo vệ bằng `@ConditionalOnBean`.

**Test 3 — user bean thay provider mặc định**

Ứng dụng cung cấp `FoundationService("custom")`. `@ConditionalOnMissingBean` khiến provider default nhường chỗ. Cả Feature và Audit vẫn được tạo, sử dụng giá trị custom. Test này xác nhận auto-configuration chạy sau user configuration và back-off hoạt động đúng.

### 6.3. Chạy test

Từ thư mục `auto-configuration-order-demo`:

```bash
mvn -q test
```

Nếu test pass, các hợp đồng được xác minh gồm:

- Metadata thứ tự hoạt động dù thứ tự đầu vào bị đảo.
- Consumer không được đăng ký khi thiếu provider.
- Bean do user cung cấp được nhìn thấy và thay thế default.
- Chuỗi dependency ba lớp được duy trì từ Foundation đến Audit.

`ApplicationContextRunner` tạo context nhỏ, phù hợp để test auto-configuration mà không cần chạy web server hoặc một ứng dụng nghiệp vụ đầy đủ.

## 7. Kiểm tra thứ tự trong ứng dụng đóng gói thực tế

### 7.1. Kiểm tra file imports trong JAR

Sau khi build module starter, kiểm tra file được đóng gói:

```bash
jar tf target/auto-configuration-order-demo-0.0.1-SNAPSHOT.jar
```

Với một thư viện auto-configuration được đóng gói thành JAR riêng, kiểm tra:

```bash
jar tf acme-autoconfigure-1.0.0.jar
jar xf acme-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File imports phải có mặt và chứa đúng fully-qualified class name của các candidate. Nếu class không nằm trong imports, metadata before/after của nó không giúp Spring Boot tự phát hiện class đó.

### 7.2. Bật Condition Evaluation Report

Chạy ứng dụng Spring Boot với:

```bash
java -jar app.jar --debug
```

Trong `CONDITIONS EVALUATION REPORT`, tìm các source liên quan:

- `FoundationAutoConfiguration#foundationService`.
- `FeatureAutoConfiguration#featureService`.
- `AuditAutoConfiguration#auditService`.

Đọc condition message để biết bean nào được tìm thấy hoặc không tìm thấy. Nếu consumer không match, kiểm tra provider có được import, condition provider có match và quan hệ after có được khai báo đúng không.

Report giúp chẩn đoán condition; test bean registry vẫn là bằng chứng trực tiếp rằng kết quả cuối cùng đúng.

### 7.3. Phân biệt thứ tự definitions với thứ tự khởi tạo

Có thể thêm log trong constructor hoặc factory method để quan sát lúc object được tạo, nhưng đừng dùng log đó để suy ra thứ tự xử lý auto-configuration. Một bean definition có thể được đăng ký sớm nhưng instance chỉ được khởi tạo khi dependency hoặc singleton pre-instantiation yêu cầu.

Trong ví dụ, tham số của factory method tạo dependency rõ ràng. Nếu hai bean không có quan hệ injection nhưng cần một bean khởi tạo trước bean khác vì side effect/lifecycle, cân nhắc `@DependsOn`:

```java
@Bean
@DependsOn("foundationInitializer")
FeatureRegistry featureRegistry() {
    return new FeatureRegistry();
}
```

`@DependsOn` chỉ điều khiển quan hệ khởi tạo bean có tên được chỉ định. Nó không khiến `@ConditionalOnBean` nhìn thấy một bean definition chưa được đăng ký, không ép một auto-configuration được import và không sửa thứ tự condition đã đánh giá.

## 8. Những tình huống cần chọn đúng cơ chế

### 8.1. Consumer phụ thuộc provider của auto-configuration khác

Dùng `@AutoConfiguration(after = ProviderAutoConfiguration.class)`. Đây là trường hợp điển hình của `@ConditionalOnBean` và `@ConditionalOnMissingBean`.

### 8.2. Cấu hình phải chạy trước một auto-configuration hiện hữu

Dùng `before` hoặc `beforeName`. Ví dụ một auto-configuration tùy chỉnh cần đăng ký metadata hoặc một bean để cấu hình sau có thể nhìn thấy nó. Chỉ dùng khi có lý do cụ thể về condition/definition processing.

### 8.3. Hai auto-configuration độc lập cần một thứ tự tổng quát

Dùng `@AutoConfigureOrder`. Tránh tạo liên kết class chỉ để đạt thứ tự khi hai cấu hình không có dependency thực sự.

### 8.4. Cần giữ một bean instance sống trước bean khác

Dùng dependency injection. Nếu không có quan hệ injection nhưng có yêu cầu lifecycle, dùng `@DependsOn` một cách có chủ đích.

### 8.5. Cần chọn thứ tự phần tử trong list

Dùng `@Order` hoặc `Ordered` trên bean phù hợp. Ví dụ một `List<Handler>` có thể được sắp xếp theo order; đây không phải thứ tự áp dụng các lớp auto-configuration.

## 9. Những lỗi phổ biến

1. **Dựa vào thứ tự dòng trong `AutoConfiguration.imports`.** Không nên dùng thứ tự dòng làm hợp đồng dependency; khai báo `before`/`after` rõ ràng.
2. **Dựa vào thứ tự class truyền vào test.** `AutoConfigurations.of` áp dụng cơ chế sắp xếp auto-configuration; hãy test metadata bằng cách cố ý đảo thứ tự đầu vào.
3. **Nhầm thứ tự config với thứ tự object.** `after` ảnh hưởng việc xử lý bean definitions, còn dependency graph và `@DependsOn` chi phối việc tạo instance.
4. **Dùng `@DependsOn` để sửa condition không match.** Bean definition không tồn tại thì `@DependsOn` không thể tạo nó.
5. **Dùng `@AutoConfigureOrder` thay quan hệ phụ thuộc rõ ràng.** Một con số order không diễn đạt vì sao consumer cần provider; dùng after/before.
6. **Quên user bean được đăng ký trước auto-configuration.** `@ConditionalOnMissingBean` có thể nhường chỗ cho bean custom; đừng giả định provider default luôn tồn tại.
7. **Đặt bean condition quá sớm trong cấu hình người dùng thông thường.** Các condition dựa trên những bean definitions đã xử lý; đặt chúng trong auto-configuration và sắp xếp provider/consumer phù hợp.
8. **Đặt condition class-level quá rộng.** Một bean thiếu dependency có thể làm toàn bộ lớp config bị loại, kéo theo các bean không liên quan.
9. **Tạo vòng before/after.** Quan hệ thứ tự nên tạo thành đồ thị có hướng không chu trình; rà soát các cạnh nếu nhiều starter cùng ràng buộc lẫn nhau.
10. **Tham chiếu class tùy chọn trực tiếp trong metadata mà không cân nhắc dependency.** Dùng `afterName`/`beforeName` khi cần tránh liên kết compile-time tới lớp có thể vắng mặt.
11. **Không đăng ký class trong imports file.** Annotation thứ tự không tự khiến class trở thành auto-configuration candidate.
12. **Chỉ xem report mà không assert bean.** Condition message giải thích quyết định; test bean count, bean names và giá trị output xác minh hành vi.

## 10. Checklist review thứ tự auto-configuration

- [ ] Mỗi lớp auto-configuration được đăng ký trong `AutoConfiguration.imports`.
- [ ] Provider và consumer được xác định rõ theo bean condition.
- [ ] Quan hệ cần thiết được khai báo bằng `after`/`before` hoặc name variant.
- [ ] Không dựa vào thứ tự dòng imports hay tên class.
- [ ] `@AutoConfigureOrder` chỉ dùng cho thứ tự tổng quát giữa các cấu hình độc lập.
- [ ] User-defined bean được test để xác nhận default back-off.
- [ ] Thiếu provider được test để xác nhận consumer không đăng ký ngoài ý muốn.
- [ ] Test truyền candidate theo thứ tự đảo để kiểm tra metadata.
- [ ] Bean instance order được xử lý bằng dependency injection hoặc `@DependsOn` khi thật sự cần.
- [ ] Không có quan hệ before/after vòng.
- [ ] Đã kiểm tra Condition Evaluation Report khi có condition không match.
- [ ] Đã chạy test trên đúng Spring Boot version mà starter hỗ trợ.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): locating candidates, imports file, ordering metadata, bean conditions và test.
- [Spring Boot 3.3 — `@AutoConfiguration` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): các thuộc tính `before`, `beforeName`, `after` và `afterName`.
- [Spring Boot 3.3 — `@AutoConfigureBefore` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html): ý nghĩa thứ tự áp dụng và sự khác biệt với thứ tự khởi tạo bean.
- [Spring Boot 3.3 — `@AutoConfigureAfter` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html): khai báo cấu hình cần được áp dụng sau provider.
- [Spring Boot 3.3 — `@AutoConfigureOrder` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html): thứ tự tổng quát dành cho auto-configuration.
- [Spring Boot 3.3 — `ApplicationContextRunner` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): tạo context test cô lập để kiểm chứng bean condition.
