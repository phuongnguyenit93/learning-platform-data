# Kiểm tra thuộc tính danh sách bằng điều kiện chuyên biệt

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Điều kiện tùy chỉnh  
**Mục tiêu:** Tạo điều kiện chỉ kích hoạt auto-configuration khi một thuộc tính dạng danh sách được khai báo. Bài giải thích vì sao `@ConditionalOnProperty` không đáng tin với danh sách được biểu diễn bằng key có chỉ số, cách dùng `Binder` và `OnPropertyListCondition`, cùng cách kiểm thử các dạng cấu hình khác nhau.

## 1. Vấn đề: list trong YAML không phải một property scalar đơn

Giả sử một starter chỉ đăng ký `TargetRegistry` khi ứng dụng cấu hình danh sách target:

```yaml
acme:
  targets:
    - eu-west
    - ap-southeast
```

Spring Boot chuyển YAML thành các property phẳng trong `Environment`. Danh sách trên được biểu diễn tương đương:

```properties
acme.targets[0]=eu-west
acme.targets[1]=ap-southeast
```

Đây là các property có phần tử chỉ số `[0]`, `[1]`. Một cách cấu hình khác là dùng chuỗi phân tách bằng dấu phẩy:

```properties
acme.targets=eu-west,ap-southeast
```

Cả hai dạng đều có thể được Spring Boot `Binder` bind thành `List<String>`. Tuy nhiên, chúng không tạo cùng một key trong `Environment`: dạng indexed có các key `acme.targets[0]`, `acme.targets[1]`, trong khi dạng comma-separated có key trực tiếp `acme.targets`.

Khác biệt này ảnh hưởng đến điều kiện cấu hình. Điều kiện kiểm tra sự hiện diện của một key scalar không tự động hiểu rằng các key con được đánh chỉ số tạo thành một danh sách.

## 2. Vì sao `@ConditionalOnProperty` không đáng tin với collection?

Một cách viết tưởng như hợp lý:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "acme", name = "targets")
class TargetAutoConfiguration {
    // Đăng ký các bean phụ thuộc vào danh sách target.
}
```

`@ConditionalOnProperty` kiểm tra property có tên `acme.targets` trong `Environment`. Mặc định, property phải tồn tại và giá trị không bằng chuỗi `"false"`; `havingValue` và `matchIfMissing` có thể thay đổi quy tắc này.

Với cấu hình comma-separated:

```properties
acme.targets=eu-west,ap-southeast
```

key `acme.targets` có mặt nên điều kiện có thể match.

Với cấu hình YAML list:

```yaml
acme:
  targets:
    - eu-west
    - ap-southeast
```

các key thực tế là `acme.targets[0]` và `acme.targets[1]`. Key gốc `acme.targets` có thể không tồn tại, vì vậy `@ConditionalOnProperty(prefix = "acme", name = "targets")` không match dù danh sách đã được cấu hình.

Spring Boot API documentation cảnh báo rõ rằng `@ConditionalOnProperty` không thể được dùng một cách đáng tin cậy để match collection properties. Đây không phải lỗi của YAML; đây là khác biệt giữa kiểm tra một key cụ thể và bind một cấu trúc collection.

**Quy tắc thực hành:** nếu điều kiện phụ thuộc vào một list, hãy dùng `Binder` để bind list đó hoặc dùng lớp cơ sở chuyên biệt `OnPropertyListCondition`.

## 3. `Binder` gom các key indexed thành một danh sách

`Binder` thuộc package:

```java
org.springframework.boot.context.properties.bind
```

Có thể lấy binder từ `Environment`:

```java
Binder binder = Binder.get(context.getEnvironment());
```

Sau đó bind property thành một kiểu collection cụ thể:

```java
BindResult<List<String>> result = binder.bind(
        "acme.targets",
        Bindable.listOf(String.class)
);
```

Các thành phần chính:

| API | Vai trò |
| --- | --- |
| `Binder.get(environment)` | Tạo binder sử dụng các property source của Environment |
| `bind(name, target)` | Thử bind property bắt đầu từ tên được chỉ định |
| `Bindable.listOf(String.class)` | Mô tả kiểu đích là `List<String>` |
| `BindResult.isBound()` | Cho biết có bind được giá trị hay không |
| `BindResult.orElse(...)` | Lấy giá trị đã bind hoặc dùng giá trị thay thế |

Ví dụ lấy list an toàn khi property vắng mặt:

```java
List<String> targets = Binder.get(environment)
        .bind("acme.targets", Bindable.listOf(String.class))
        .orElseGet(List::of);
```

Với YAML list hoặc các key indexed, Binder nhận diện cấu trúc và gom phần tử theo chỉ số. Với comma-separated property, Binder cũng có thể chuyển giá trị thành `List<String>`.

Không nên tự duyệt `Environment.getProperty("acme.targets")` rồi tách chuỗi bằng dấu phẩy. Cách đó bỏ sót indexed keys, relaxed binding, conversion và các quy tắc property source mà Binder đã xử lý.

## 4. Dùng `OnPropertyListCondition` có sẵn trong Spring Boot

Spring Boot cung cấp lớp cơ sở `OnPropertyListCondition` trong package:

```java
org.springframework.boot.autoconfigure.condition
```

Lớp này kế thừa `SpringBootCondition` và dùng `Binder` để kiểm tra một property có thể bind thành list hay không. Constructor nhận tên property đầy đủ và một `Supplier<ConditionMessage.Builder>` để tạo message mới cho mỗi lần đánh giá.

Đây là lựa chọn phù hợp khi một auto-configuration cần kiểm tra một list có tên cố định.

### 4.1. Tạo annotation riêng

File `ConditionalOnConfiguredTargets.java`:

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnConfiguredTargetsCondition.class)
public @interface ConditionalOnConfiguredTargets {
}
```

Annotation có thể đặt trên configuration class hoặc `@Bean` method. `@Conditional` liên kết annotation với condition class.

### 4.2. Viết condition bằng `OnPropertyListCondition`

File `OnConfiguredTargetsCondition.java`:

```java
package demo;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.OnPropertyListCondition;

public final class OnConfiguredTargetsCondition extends OnPropertyListCondition {

    public OnConfiguredTargetsCondition() {
        super(
                "acme.targets",
                () -> ConditionMessage.forCondition("Configured targets")
        );
    }
}
```

Condition kiểm tra list property `acme.targets`. `OnPropertyListCondition` tự thực hiện bind và tạo condition outcome/message để Spring Boot dùng khi chẩn đoán.

Việc dùng `Supplier` rất quan trọng: mỗi lần đánh giá condition cần một `ConditionMessage.Builder` mới. Không chia sẻ một builder có trạng thái giữa các lần đánh giá.

### 4.3. Áp dụng vào auto-configuration

File `TargetRegistry.java`:

```java
package demo;

import java.util.List;

public record TargetRegistry(List<String> targets) {
}
```

File `TargetAutoConfiguration.java`:

```java
package demo;

import java.util.List;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
@ConditionalOnConfiguredTargets
public class TargetAutoConfiguration {

    @Bean
    TargetRegistry targetRegistry(Environment environment) {
        List<String> targets = Binder.get(environment)
                .bind("acme.targets", Bindable.listOf(String.class))
                .orElseGet(List::of);

        return new TargetRegistry(List.copyOf(targets));
    }
}
```

Condition ở cấp class quyết định toàn bộ `TargetAutoConfiguration` có được áp dụng hay không. Khi list có thể bind, bean `TargetRegistry` được đăng ký và nhận danh sách từ cùng một `Environment`.

Trong một thư viện thực tế, bean có thể dùng `@ConfigurationProperties` thay vì bind lại trực tiếp trong method. Ví dụ trên bind trực tiếp để làm rõ cùng một property name được condition kiểm tra và bean tiêu thụ như thế nào.

Nếu chỉ một bean phụ thuộc vào list, có thể đặt `@ConditionalOnConfiguredTargets` trên riêng method `@Bean`. Khi đặt ở cấp class, các bean method khác trong configuration cũng bị bỏ qua nếu condition không match.

## 5. Kiểm thử indexed list và comma-separated list

Nên kiểm tra ít nhất ba trường hợp:

1. Không có list: configuration không được áp dụng.
2. Có các key indexed: custom list condition match.
3. Có một property comma-separated: custom list condition cũng match.

Đồng thời, kiểm thử một `@ConditionalOnProperty` thông thường để thấy sự khác biệt với indexed list.

### 5.1. `pom.xml`

Ví dụ dùng Java 17 và Spring Boot 3.3.13:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>list-property-condition</artifactId>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 5.2. `TargetAutoConfigurationTests.java`

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class TargetAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            TargetAutoConfiguration.class,
                            DirectPropertyConditionConfiguration.class
                    );

    @Test
    void indexedListActivatesCustomConditionButNotScalarPropertyCondition() {
        this.runner
                .withPropertyValues(
                        "acme.targets[0]=eu-west",
                        "acme.targets[1]=ap-southeast"
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(TargetRegistry.class);

                    assertThat(context.getBean(TargetRegistry.class).targets())
                            .containsExactly("eu-west", "ap-southeast");

                    assertThat(context)
                            .doesNotHaveBean("directPropertyMarker");
                });
    }

    @Test
    void missingListDoesNotRegisterTargetRegistry() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(TargetRegistry.class);
            assertThat(context).doesNotHaveBean("directPropertyMarker");
        });
    }

    @Test
    void commaSeparatedPropertyCanBeBoundAsList() {
        this.runner
                .withPropertyValues("acme.targets=eu-west,ap-southeast")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(TargetRegistry.class);

                    assertThat(context.getBean(TargetRegistry.class).targets())
                            .containsExactly("eu-west", "ap-southeast");

                    assertThat(context).hasBean("directPropertyMarker");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class DirectPropertyConditionConfiguration {

        @Bean
        @ConditionalOnProperty(prefix = "acme", name = "targets")
        String directPropertyMarker() {
            return "root-property-present";
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi từ Maven Surefire:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Không có stdout tùy biến từ các test. Kết quả được kiểm tra bằng AssertJ trong từng callback của `ApplicationContextRunner`.

### 5.3. Đọc kết quả test

| Trường hợp | Property source | `OnPropertyListCondition` | `@ConditionalOnProperty` |
| --- | --- | --- | --- |
| Không có list | Không có `acme.targets` | No match | No match |
| YAML/indexed list | `acme.targets[0]`, `acme.targets[1]` | Match | Không match nếu key gốc không tồn tại |
| Comma-separated | `acme.targets=eu-west,ap-southeast` | Match | Match |

Test đầu là bằng chứng chính: `TargetRegistry` được tạo từ indexed list, còn bean `directPropertyMarker` bị bỏ qua vì condition scalar không tìm thấy key gốc.

Test cuối cho thấy `@ConditionalOnProperty` vẫn phù hợp với property scalar chứa chuỗi comma-separated. Vấn đề không phải annotation này luôn sai với mọi biểu diễn list; vấn đề là nó không aggregate các indexed keys thành một collection.

## 6. Khi nào chỉ cần list tồn tại, khi nào cần list không rỗng?

`OnPropertyListCondition` kiểm tra liệu property có thể được bind thành một list hay không. Mục tiêu của nó là nhận diện list property trong `Environment`, kể cả khi danh sách được biểu diễn bằng các key indexed.

Đây không đồng nghĩa với mọi quy tắc nghiệp vụ về nội dung list. Có thể có những yêu cầu khác nhau:

- Property list đã được khai báo.
- List bind được và có ít nhất một phần tử.
- List có ít nhất một phần tử không rỗng hoặc không chỉ chứa khoảng trắng.
- List có ít nhất một phần tử thỏa định dạng hoặc chính sách cụ thể.

Nếu chỉ cần biết list property được khai báo, kế thừa `OnPropertyListCondition` là phù hợp.

Nếu cần kiểm tra list có phần tử không rỗng, viết một `Condition` dùng Binder và kiểm tra nội dung sau khi bind:

```java
package demo;

import java.util.List;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

final class OnNonEmptyTargetsCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata
    ) {
        List<String> targets = Binder.get(context.getEnvironment())
                .bind("acme.targets", Bindable.listOf(String.class))
                .orElseGet(List::of);

        return targets.stream()
                .anyMatch(value -> value != null && !value.isBlank());
    }
}
```

Liên kết condition này bằng annotation riêng:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnNonEmptyTargetsCondition.class)
public @interface ConditionalOnNonEmptyTargets {
}
```

Có thể đặt `@ConditionalOnNonEmptyTargets` trên configuration class hoặc bean method cần bảo vệ. Ví dụ trên định nghĩa chính sách cụ thể: ít nhất một phần tử phải chứa ký tự khác khoảng trắng. Nếu nghiệp vụ yêu cầu phần tử phải khớp hostname, URI hoặc mã vùng, hãy kiểm tra đúng quy tắc đó sau khi bind.

Khi cần message chi tiết trong Condition Evaluation Report, có thể kế thừa `SpringBootCondition` và trả về `ConditionOutcome` với lý do match/no-match. `OnPropertyListCondition` đã cung cấp sẵn cách ghi nhận outcome cho trường hợp kiểm tra sự hiện diện của list.

## 7. List gồm object thay vì String

Binder không chỉ bind `List<String>`. Nếu mỗi phần tử là một object có nhiều thuộc tính, dùng kiểu phần tử cụ thể trong `Bindable`.

Ví dụ YAML:

```yaml
acme:
  endpoints:
    - name: europe
      url: https://eu.example.test
      enabled: true
    - name: asia
      url: https://asia.example.test
      enabled: false
```

Các key tương đương:

```properties
acme.endpoints[0].name=europe
acme.endpoints[0].url=https://eu.example.test
acme.endpoints[0].enabled=true
acme.endpoints[1].name=asia
acme.endpoints[1].url=https://asia.example.test
acme.endpoints[1].enabled=false
```

Khai báo kiểu:

```java
public record Endpoint(
        String name,
        URI url,
        boolean enabled
) {
}
```

Có thể bind:

```java
List<Endpoint> endpoints = Binder.get(environment)
        .bind("acme.endpoints", Bindable.listOf(Endpoint.class))
        .orElseGet(List::of);
```

`OnPropertyListCondition` cơ sở được thiết kế để kiểm tra list property theo `List<String>`. Nếu list chứa object phức tạp hoặc cần xét một trường cụ thể như `enabled=true`, hãy dùng custom `Condition` với Binder và `Bindable.listOf(Endpoint.class)`.

Ví dụ, điều kiện “có ít nhất một endpoint đang bật” nên kiểm tra `endpoints.stream().anyMatch(Endpoint::enabled)`, thay vì chỉ kiểm tra list có được khai báo.

## 8. Property source, relaxed binding và profile

`Binder.get(context.getEnvironment())` dùng các property source mà Spring Boot đã nạp vào `Environment`. Vì vậy, condition có thể làm việc với các nguồn cấu hình như:

- `application.yml` và `application.properties`.
- File profile-specific như `application-prod.yml`.
- Environment variables.
- System properties.
- Command-line arguments.
- Property source bổ sung được ứng dụng đăng ký.

Ví dụ list từ environment variables có thể dùng dạng:

```text
ACME_TARGETS_0=eu-west
ACME_TARGETS_1=ap-southeast
```

Spring Boot dùng quy tắc chuyển đổi tên environment variable cho phần tử list, trong đó chỉ số được bao quanh bởi dấu gạch dưới. Binder thực hiện relaxed binding và conversion dựa trên `Environment`.

Nếu profile `prod` chứa list nhưng profile hiện tại không active, condition sẽ không thấy giá trị đó. Khi debug, hãy xác nhận active profile và property source thực sự có hiệu lực; đừng chỉ nhìn một file YAML không được nạp.

Khi nhiều property source cùng khai báo list, Binder áp dụng quy tắc precedence và collection binding của Spring Boot. Không tự ghép list bằng cách đọc từng nguồn riêng lẻ. Nếu cần thay toàn bộ list trong profile override, hãy kiểm tra kết quả bind thực tế để xác nhận danh sách cuối cùng đúng như mong đợi.

## 9. Condition được đánh giá khi nào và nên làm gì bên trong?

Spring đánh giá condition trong quá trình phân tích/đăng ký configuration class và bean definition. Tại thời điểm đó, các bean mà auto-configuration định nghĩa có thể chưa được tạo.

Vì vậy, custom condition nên:

- Đọc `Environment` và bind property bằng `Binder`.
- Chỉ thực hiện phép kiểm tra nhanh, xác định và không có side effect.
- Trả kết quả ổn định với cùng một cấu hình.
- Tránh truy cập bean của ứng dụng mà chưa chắc đã tồn tại.
- Tránh mở kết nối database, gọi HTTP hoặc đọc dịch vụ từ xa.
- Không tạo bean hoặc sửa `Environment` trong `matches`.

Không inject `@ConfigurationProperties` bean vào condition để đọc list. Bean đó có thể chưa được đăng ký hoặc khởi tạo khi condition chạy. Bind trực tiếp từ `ConditionContext.getEnvironment()` là cách phù hợp.

Nếu cần kiểm tra một bean đã tồn tại, dùng các condition bean tương ứng như `@ConditionalOnBean`/`@ConditionalOnMissingBean` hoặc custom condition đọc `BeanFactory` theo đúng lifecycle. Đừng trộn kiểm tra bean với kiểm tra property list nếu hai quyết định có thể được mô tả độc lập.

## 10. Xử lý lỗi bind và dữ liệu không hợp lệ

Một condition list cần phân biệt:

1. **Không có property:** Binder không bind được list; condition có thể no-match.
2. **List hợp lệ:** Binder trả về danh sách; condition quyết định match theo chính sách.
3. **Giá trị không chuyển đổi được:** Binder có thể ném `BindException` hoặc lỗi chuyển đổi liên quan. Đây là dấu hiệu cấu hình không hợp lệ, không nên âm thầm coi như danh sách vắng mặt.
4. **List có phần tử rỗng:** Binder có thể bind được phần tử nhưng nghiệp vụ có thể không chấp nhận. Condition kiểm tra nội dung hoặc validation phải quyết định rõ.

Không bắt mọi `Exception` rồi trả `false`. Cách đó biến lỗi cấu hình thật thành một no-match khó phát hiện; ứng dụng có thể khởi động mà tính năng không được bật và không giải thích được lý do.

Với list cấu hình phức tạp, cân nhắc dùng `@ConfigurationProperties` kết hợp Bean Validation (`@Validated`, `@NotEmpty`, `@NotBlank`, v.v.) để xác thực nội dung sau khi bind. Condition quyết định configuration có được áp dụng; validation xác nhận dữ liệu đã bind có hợp lệ theo contract hay không. Hai cơ chế có mục đích khác nhau.

## 11. Chẩn đoán khi condition không match như mong đợi

Khi auto-configuration không được áp dụng:

1. Bật `--debug` hoặc `debug=true` để xem Condition Evaluation Report.
2. Tìm configuration class hoặc bean method được bảo vệ bởi custom condition.
3. Xác nhận property name đầy đủ, ví dụ `acme.targets`.
4. Kiểm tra cấu hình thực tế là indexed list (`acme.targets[0]`) hay scalar/comma-separated (`acme.targets`).
5. Dùng `Binder.get(environment).bind(..., Bindable.listOf(String.class))` trong test hoặc điểm debug để xem list cuối cùng.
6. Xác nhận profile và property source đang active.
7. Kiểm tra conversion/validation nếu property tồn tại nhưng bind thất bại.
8. Nếu condition match nhưng bean không có, kiểm tra condition khác trên configuration/method, bean registration và auto-configuration ordering.

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@ConditionalOnProperty` no-match với YAML list | Chỉ có các key `[0]`, `[1]`, không có key gốc | Dùng `OnPropertyListCondition` hoặc Binder |
| Custom condition no-match khi không có list | Không có property để bind | Kiểm tra profile và nguồn cấu hình |
| Comma-separated match nhưng indexed no-match | Condition đang đọc trực tiếp key gốc | Bind bằng `Binder` |
| Condition match nhưng list rỗng | Chỉ kiểm tra list có được bind | Kiểm tra kích thước/phần tử nếu nghiệp vụ yêu cầu |
| Condition ném lỗi bind | Kiểu dữ liệu hoặc cấu trúc property không hợp lệ | Đọc root cause và sửa cấu hình |
| Test pass nhưng ứng dụng không match | Test và runtime dùng property source/profile khác nhau | Tái hiện bằng đúng active profile và environment |

## 12. Những hiểu lầm thường gặp

**Hiểu lầm 1: `@ConditionalOnProperty` tự nhận biết mọi dạng collection.**  
Không đúng. Nó kiểm tra property name cụ thể. Indexed keys không bảo đảm key gốc tồn tại.

**Hiểu lầm 2: YAML list là một chuỗi duy nhất trong Environment.**  
Không đúng. YAML list thường được flatten thành các key indexed như `acme.targets[0]`.

**Hiểu lầm 3: Chỉ cần gọi `Environment.getProperty("acme.targets")`.**  
Không đúng. Cách đọc key scalar không aggregate các phần tử indexed. Dùng Binder cho cấu trúc list.

**Hiểu lầm 4: `OnPropertyListCondition` xác nhận mọi phần tử hợp lệ.**  
Không đúng. Nó kiểm tra list property có thể bind được; quy tắc nghiệp vụ về giá trị từng phần tử cần được kiểm tra riêng.

**Hiểu lầm 5: List được khai báo thì chắc chắn không rỗng.**  
Không đúng. “Có property” và “có ít nhất một phần tử hữu ích” là hai điều kiện khác nhau.

**Hiểu lầm 6: Có thể lấy `@ConfigurationProperties` bean ngay trong condition.**  
Không nên. Condition chạy trước khi các bean của configuration được tạo; hãy bind trực tiếp từ Environment.

**Hiểu lầm 7: Bind lỗi cũng nên trả no-match.**  
Không nên. Lỗi conversion hoặc cấu trúc dữ liệu thường là lỗi cấu hình cần được hiển thị rõ.

**Hiểu lầm 8: Thứ tự khai báo key trong YAML quyết định thứ tự condition.**  
Không đúng. Binder đọc property source và các chỉ số list; thứ tự khai báo văn bản không phải cơ chế bật/tắt condition.

## 13. Checklist review

- [ ] Xác định rõ condition cần kiểm tra list được khai báo hay list có phần tử hợp lệ.
- [ ] Không dùng `@ConditionalOnProperty` để kiểm tra indexed collection keys.
- [ ] Dùng `OnPropertyListCondition` cho list property cố định khi chỉ cần kiểm tra khả năng bind.
- [ ] Dùng `Binder` + `Bindable.listOf(...)` cho custom type hoặc quy tắc nội dung riêng.
- [ ] Đặt condition ở cấp configuration class hoặc đúng bean method cần bảo vệ.
- [ ] Không phụ thuộc vào bean `@ConfigurationProperties` trong lúc condition đang chạy.
- [ ] Có test cho list thiếu, indexed list và comma-separated list.
- [ ] Có test chứng minh `@ConditionalOnProperty` không match indexed keys.
- [ ] Xử lý conversion/binding failure như lỗi cấu hình, không che bằng catch-all.
- [ ] Xác nhận profile và property source giống môi trường triển khai.
- [ ] Đọc Condition Evaluation Report khi kết quả khác mong đợi.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `@ConditionalOnProperty(prefix = "acme", name = "targets")` có thể không match khi YAML chứa một list `acme.targets`?  
**Đáp án:** YAML list được flatten thành `acme.targets[0]`, `acme.targets[1]`; key gốc `acme.targets` có thể không tồn tại để condition kiểm tra.

**Câu 2.** API nào giúp bind indexed list thành `List<String>`?  
**Đáp án:** `Binder.get(environment).bind("acme.targets", Bindable.listOf(String.class))`.

**Câu 3.** `OnPropertyListCondition` của Spring Boot làm nhiệm vụ gì?  
**Đáp án:** Dùng Binder để kiểm tra một property có thể bind thành list và cung cấp condition outcome/log message.

**Câu 4.** `OnPropertyListCondition` có đồng nghĩa list chắc chắn chứa phần tử không rỗng không?  
**Đáp án:** Không. Nếu cần phần tử không rỗng, bind list rồi kiểm tra nội dung theo quy tắc nghiệp vụ.

**Câu 5.** Khi nào `@ConditionalOnProperty` có thể hoạt động với list?  
**Đáp án:** Khi property được biểu diễn bằng key gốc, ví dụ `acme.targets=eu-west,ap-southeast`; điều này không giải quyết trường hợp chỉ có indexed keys.

**Câu 6.** Vì sao condition không nên truy cập bean `@ConfigurationProperties`?  
**Đáp án:** Condition được đánh giá trong giai đoạn cấu hình, trước khi bean đó chắc chắn được tạo. Bind trực tiếp từ `Environment`.

**Câu 7.** Nếu Binder ném lỗi chuyển đổi, có nên coi đó là no-match không?  
**Đáp án:** Không. Đó thường là cấu hình không hợp lệ; cần giữ root cause để người vận hành sửa dữ liệu.

## 15. Nguyên tắc cần nhớ

- `@ConditionalOnProperty` kiểm tra key cụ thể; nó không aggregate indexed collection properties.
- YAML list thường trở thành `property[0]`, `property[1]` trong Environment.
- `Binder` và `Bindable.listOf(...)` là cách phù hợp để đọc list theo đúng quy tắc Spring Boot.
- `OnPropertyListCondition` là lớp cơ sở có sẵn để xây dựng condition kiểm tra list property.
- Phân biệt list được khai báo với list có phần tử hợp lệ.
- Dùng custom `Condition` khi cần kiểm tra nội dung, kiểu phần tử hoặc quy tắc nghiệp vụ riêng.
- Condition nên nhanh, xác định, không side effect và không phụ thuộc bean chưa được tạo.
- Kiểm thử indexed list, comma-separated list và trường hợp thiếu property bằng `ApplicationContextRunner`.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 API — `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3.13 API — `OnPropertyListCondition`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/OnPropertyListCondition.html)
- [Spring Boot 3.3.13 API — `Binder`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html)
- [Spring Boot 3.3 — Externalized Configuration and YAML Lists](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
