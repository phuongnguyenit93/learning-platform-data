# Phân biệt không khớp có chủ đích với cấu hình bị lỗi ngoài dự kiến

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Báo cáo điều kiện (Condition Evaluation Report)  
**Mục tiêu:** Đọc báo cáo điều kiện để hiểu vì sao auto-configuration được áp dụng hoặc bị bỏ qua, nhận ra trường hợp `no match` là hành vi thiết kế bình thường, và tách nó khỏi lỗi cấu hình hoặc lỗi khởi tạo khiến ứng dụng không chạy được.

## 1. `No match` không có nghĩa ứng dụng bị lỗi

Spring Boot dùng các điều kiện như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnWebApplication` để quyết định một nhánh cấu hình có nên tham gia hay không.

Ví dụ:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.feature",
        name = "enabled",
        havingValue = "true"
)
FeatureService featureService() {
    return new FeatureService();
}
```

Nếu `acme.feature.enabled` không tồn tại hoặc có giá trị `false`, Spring bỏ qua bean `featureService`. Đây là một **kết quả điều kiện không khớp (no match)**. Context vẫn có thể khởi động bình thường. Nếu tính năng được thiết kế là opt-in, đây chính là kết quả mong muốn.

Một ví dụ khác:

```java
@Bean
@ConditionalOnMissingBean(FeatureService.class)
FeatureService defaultFeatureService() {
    return new FeatureService();
}
```

Khi ứng dụng đã cung cấp một bean `FeatureService`, điều kiện `@ConditionalOnMissingBean` không khớp và bean mặc định không được đăng ký. Đây là **back-off có chủ đích** để ứng dụng thay thế mặc định.

Do đó cần tách hai câu hỏi:

- **Condition có khớp không?** Spring Boot trả lời bằng `match` hoặc `no match`.
- **Kết quả đó có đúng với ý đồ cấu hình không?** Người phát triển đối chiếu với chính sách thiết kế và môi trường triển khai.

`no match` chỉ cho biết một điều kiện không thỏa. Nó không tự kết luận rằng cấu hình của người dùng sai, cũng không tự chứng minh rằng mọi thứ đều ổn.

## 2. `ConditionEvaluationReport` ghi lại điều gì?

`ConditionEvaluationReport` là báo cáo do Spring Boot thu thập trong quá trình đánh giá các điều kiện của auto-configuration. Mỗi kết quả được gắn với **nguồn** đã khai báo điều kiện, thường là tên lớp cấu hình hoặc tên phương thức `@Bean`.

Các khái niệm chính:

| Thành phần | Ý nghĩa |
| --- | --- |
| Source | Class hoặc phương thức `@Bean` mà điều kiện đang bảo vệ |
| Condition | Loại điều kiện được đánh giá, ví dụ `OnClassCondition`, `OnPropertyCondition`, `OnBeanCondition` |
| Outcome | Kết quả `match` hoặc `no match` |
| Message | Lý do mà condition cung cấp cho kết quả |
| Positive matches | Những source có các điều kiện liên quan khớp |
| Negative matches | Những source có ít nhất một điều kiện không khớp |
| Exclusions | Các lớp auto-configuration bị loại trừ khỏi việc đánh giá |
| Unconditional classes | Các lớp được ghi nhận không có điều kiện |

Trong API Spring Boot 3.3, có thể truy cập báo cáo qua:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(beanFactory);

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> outcomes =
        report.getConditionAndOutcomesBySource();
```

`ConditionAndOutcomes.isFullMatch()` trả về `true` khi tất cả outcome trong source đều khớp. Khi có một outcome không khớp, kết quả tổng hợp là `false`. Để biết **điều kiện nào** gây ra no-match, duyệt từng `ConditionAndOutcome` và đọc `getOutcome()`:

```java
for (Map.Entry<String, ConditionEvaluationReport.ConditionAndOutcomes> entry
        : outcomes.entrySet()) {

    String source = entry.getKey();
    var sourceOutcomes = entry.getValue();

    System.out.println(source + " => "
            + (sourceOutcomes.isFullMatch() ? "MATCH" : "NO MATCH"));

    for (ConditionEvaluationReport.ConditionAndOutcome item : sourceOutcomes) {
        var outcome = item.getOutcome();

        System.out.println("  "
                + item.getCondition().getClass().getSimpleName()
                + " | "
                + (outcome.isMatch() ? "matched" : "did not match")
                + " | "
                + outcome.getMessage());
    }
}
```

Đây là đoạn mã chẩn đoán đặt trong một nơi đã có `ConfigurableListableBeanFactory` hoặc context đang hoạt động; không phải chương trình Java độc lập. Các message cụ thể phụ thuộc condition và phiên bản. Hãy đọc nội dung thực tế của message, đừng viết logic ứng dụng dựa vào một chuỗi log cố định.

`ConditionEvaluationReport` được nhóm theo source, nên có thể biết **bean method nào** hoặc **configuration class nào** bị ảnh hưởng. Điều này hữu ích hơn việc chỉ nhìn một dòng log tổng quát như “auto-configuration did not match”.

## 3. Các kiểu `no match` thường là chủ đích

### 3.1. Tính năng được thiết kế mặc định tắt

```java
@ConditionalOnProperty(
        prefix = "acme.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

Nếu không khai báo khóa hoặc đặt `false`, bean không được đăng ký. Với một tính năng cần người vận hành bật rõ ràng, no-match là bình thường.

### 3.2. Thư viện tùy chọn không có trên classpath

```java
@ConditionalOnClass(name = "com.vendor.sdk.Client")
```

Nếu dependency của SDK không được thêm, integration tương ứng được bỏ qua. Đây là mục đích của điều kiện classpath trong một starter có nhiều tính năng tùy chọn.

Nếu người dùng **đã khai báo** dependency và mong muốn integration chạy, no-match có thể chỉ ra dependency chưa được đưa vào runtime classpath, version bị lệch hoặc classloader không nhìn thấy lớp đó. Cùng một kết quả condition có thể bình thường ở một ứng dụng và là lỗi cấu hình ở ứng dụng khác.

### 3.3. Bean mặc định nhường chỗ cho bean của ứng dụng

```java
@ConditionalOnMissingBean(FeatureService.class)
```

Nếu một bean `FeatureService` do ứng dụng cung cấp đã được nhận diện, bean mặc định của starter không xuất hiện. Report ghi nhận điều kiện không khớp vì tìm thấy bean phù hợp. Đây là kết quả mong đợi khi thư viện hỗ trợ override.

### 3.4. Ứng dụng không thuộc loại web mà cấu hình yêu cầu

`@ConditionalOnWebApplication(type = SERVLET)` có thể không khớp trong một application context không phải Servlet. Nếu module đang được dùng trong một ứng dụng non-web hoặc Reactive, việc bỏ qua cấu hình Servlet có thể là đúng.

### 3.5. Môi trường chưa đáp ứng điều kiện cloud hoặc resource

Một cấu hình chỉ chạy trên một cloud platform, khi có file resource hoặc khi thỏa một điều kiện runtime cụ thể có thể không khớp trên laptop hoặc trong test. Nếu tính năng đó chỉ được kỳ vọng trong production tương ứng, no-match ở local có thể là hành vi bình thường.

## 4. Khi `no match` lại là dấu hiệu cấu hình ngoài dự kiến

Report cho biết **điều kiện không thỏa và lý do kỹ thuật được condition cung cấp**. Nó không biết người vận hành có chủ đích cấu hình như vậy hay không. Hãy đối chiếu với cấu hình mong muốn.

### 4.1. Gõ sai tên property

Người vận hành định bật:

```yaml
acme:
  feature:
    enabled: true
```

Nhưng thực tế ghi:

```yaml
acme:
  feature:
    enabld: true
```

Với condition tìm `acme.feature.enabled`, khóa `enabled` vẫn bị coi là thiếu. Report có thể cho thấy condition không tìm thấy property `enabled`. Ứng dụng có thể vẫn khởi động và không tạo bean, nên lỗi này dễ bị nhầm với tính năng mặc định tắt.

Cách xử lý: đối chiếu **tên canonical** trong annotation, file YAML, biến môi trường và profile đang chạy. Đừng chỉ nhìn thấy một property “có vẻ tương tự” rồi kết luận condition phải khớp.

### 4.2. Giá trị không khớp `havingValue`

```java
@ConditionalOnProperty(
        prefix = "acme.feature",
        name = "mode",
        havingValue = "strict"
)
```

Nếu giá trị hiệu lực là `safe`, condition không khớp. Đây có thể là no-match có chủ đích hoặc người dùng chọn sai mode. Report giúp xác định giá trị không đáp ứng condition; chính sách sản phẩm mới quyết định giá trị đó có hợp lệ hay không.

Đặc biệt với `@ConditionalOnProperty`, nếu không khai báo `havingValue`, mặc định một property hiện diện và khác chuỗi `"false"` sẽ khớp. Nếu dùng Boolean feature flag, hãy khai báo rõ `havingValue = "true"` và `matchIfMissing` để tránh hiểu nhầm chuỗi như `off`, `0` hoặc giá trị rỗng.

### 4.3. Profile hoặc nguồn cấu hình đang hoạt động khác dự kiến

Property có thể nằm trong `application-prod.yml`, nhưng ứng dụng đang chạy profile `dev`; hoặc một biến môi trường/command-line argument ghi đè giá trị trong YAML. Điều condition nhìn thấy là giá trị hiệu lực trong `Environment`, không phải nội dung một file riêng lẻ.

Cách xử lý:

- Xác nhận active profiles.
- Kiểm tra tên property canonical và các nguồn cấu hình có độ ưu tiên cao.
- Kiểm tra giá trị hiệu lực bằng `/actuator/env` nếu endpoint được bật và bảo vệ phù hợp, hoặc quan sát `Environment` trong test.
- Đừng sửa annotation trước khi biết nguồn cấu hình nào đang thắng.

### 4.4. `@ConditionalOnMissingBean` tìm sai kiểu hoặc đánh giá sai thứ tự

Nếu fallback cần nhường chỗ cho mọi implementation của `FeatureService`, nhưng condition lại tìm một implementation cụ thể, một bean custom có thể không làm condition thất bại như mong muốn.

Ngoài ra, bean conditions dựa trên các bean definition đã được xử lý tại thời điểm condition chạy. Auto-configuration nên được tổ chức theo thứ tự phù hợp và method `@Bean` nên công khai kiểu trả về đủ cụ thể để Spring có thể dự đoán ứng viên. Nếu report nói không tìm thấy bean, hãy kiểm tra type, return type, parent/child context và thứ tự auto-configuration.

### 4.5. Auto-configuration không xuất hiện trong report

Không thấy một class trong `positiveMatches` hoặc `negativeMatches` **không tự động có nghĩa condition của nó no-match**. Có thể class đó chưa phải ứng viên được nạp, đã bị exclude, thiếu trong `AutoConfiguration.imports`, hoặc không có trên classpath.

Kiểm tra:

- File `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` trong artifact.
- Danh sách `exclusions` trong report và cấu hình `spring.autoconfigure.exclude`.
- Dependency starter/autoconfigure có trong runtime classpath hay không.
- Package/class có đúng artifact và version được ứng dụng sử dụng không.

`ConditionEvaluationReport` cung cấp danh sách exclusions và các source đã được đánh giá; nó không thay thế kiểm tra dependency tree và nội dung JAR.

## 5. Lỗi cấu hình thật khác với một condition không khớp

Một lỗi khiến context thất bại thường để lại **exception hoặc startup failure**, không chỉ là một outcome no-match.

| Tình huống | Dấu hiệu thường thấy | Hướng kiểm tra |
| --- | --- | --- |
| Property thiếu làm tính năng opt-in không được bật | Negative match, context vẫn chạy | Xác nhận đây có phải default mong muốn không |
| Sai tên hoặc sai giá trị property | Negative match, context có thể vẫn chạy | Đối chiếu canonical key, `havingValue`, profile, Environment |
| Optional class không có | Negative match từ class condition | Dependency/runtime classpath |
| YAML/Properties không parse được | Lỗi khi nạp Config Data, context có thể không dựng xong | Cú pháp YAML, file location, profile/import |
| Giá trị không chuyển đổi được hoặc validation thất bại | `BindException`, lỗi binding/validation trong startup failure | Kiểu property, format, ràng buộc |
| Bean method hoặc constructor ném exception | `BeanCreationException` hoặc root cause khác | Stacktrace, input, external dependency |
| Không tìm thấy dependency bắt buộc | `UnsatisfiedDependencyException` / `NoSuchBeanDefinitionException` | Bean definition, condition, wiring |
| Nhiều bean không thể phân giải một dependency đơn | `NoUniqueBeanDefinitionException` | `@Primary`, `@Qualifier`, bean candidates |
| Thiếu class hoặc method ở runtime | `NoClassDefFoundError`, `NoSuchMethodError` | Dependency tree và version compatibility |

Có ba điểm đặc biệt cần nhớ:

1. **Một condition khớp vẫn có thể dẫn tới startup failure.** Bean được phép đăng ký, nhưng constructor/factory method hoặc dependency của nó có thể thất bại.
2. **Một condition không khớp thường không làm context thất bại.** Nó có thể chỉ loại một bean tùy chọn; các bean khác vẫn hoạt động.
3. **Một lỗi nạp cấu hình có thể xảy ra trước khi có đủ report.** Khi context không dựng được, phải đọc exception gốc và Failure Analysis; không cố tìm một dòng `negativeMatches` để giải thích mọi lỗi.

`ConditionEvaluationReport` là công cụ giải thích quyết định điều kiện, không phải danh sách mọi exception và cũng không phải health report.

## 6. Cách xem báo cáo trong ứng dụng thật

### 6.1. Bật `--debug`

Chạy ứng dụng Spring Boot đã đóng gói:

```bash
java -jar app.jar --debug
```

Hoặc dùng cấu hình:

```properties
debug=true
```

`--debug` bật debug logging cho một số logger cốt lõi và in condition evaluation report. Tìm các phần positive/negative matches để biết nhánh nào được bật và nhánh nào bị bỏ qua.

Không nên bật debug lâu dài trong production chỉ để che lấp việc thiếu logging có chủ đích; hãy dùng đúng thời điểm chẩn đoán và kiểm soát log theo chính sách vận hành.

### 6.2. Xem qua Actuator `/actuator/conditions`

Nếu ứng dụng có dependency `spring-boot-starter-actuator`, endpoint `conditions` có thể cung cấp báo cáo dạng JSON. Ví dụ cấu hình exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
```

Sau khi chạy ứng dụng:

```bash
curl http://localhost:8080/actuator/conditions
```

Response của Spring Boot 3.3 có các vùng như:

- `contexts.*.positiveMatches`: các class/method có điều kiện khớp.
- `contexts.*.negativeMatches`: các class/method không khớp, kèm `notMatched`, `matched` và message.
- `contexts.*.exclusions`: các auto-configuration bị loại.
- `contexts.*.unconditionalClasses`: các lớp unconditional được ghi nhận.

Endpoint này có thể tiết lộ cấu trúc và lý do cấu hình nội bộ. Chỉ expose trong môi trường cần chẩn đoán và bảo vệ bằng xác thực/phân quyền phù hợp; không mở công khai chỉ vì tiện debug.

### 6.3. Dùng `ConditionEvaluationReportLoggingListener` trong test

Spring Boot cung cấp `ConditionEvaluationReportLoggingListener`, một `ApplicationContextInitializer` có thể ghi báo cáo khi chạy `ApplicationContextRunner`.

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(AutoConfigurations.of(FeatureAutoConfiguration.class))
        .run(context -> {
            // Assert kết quả bean và kiểm tra report tại đây.
        });
```

Mặc định listener ghi report ở DEBUG; `forLogLevel(LogLevel.INFO)` giúp test log ra ở INFO. Listener này không nên được chia sẻ cho nhiều application context instance; tạo initializer phù hợp cho lần chạy test.

`ApplicationContextRunner` là cách tốt để tạo từng context có classpath, property và user configuration xác định. Mỗi test nên mô tả một trường hợp: property thiếu, false, true, dependency thiếu hoặc bean custom đã tồn tại.

## 7. Bài thực hành: phân biệt no-match bình thường và lỗi khởi tạo

Bài thực hành dùng **Java 17**, **Spring Boot 3.3.5**, **JUnit 5**, Maven và `ApplicationContextRunner`. Nó tạo bốn loại kết quả: property thiếu, property false, property gõ sai, property đúng; thêm một trường hợp fallback nhường chỗ và một trường hợp condition khớp nhưng bean khởi tạo thất bại.

### 7.1. Cấu trúc dự án

```text
condition-diagnosis-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ConditionDiagnosisTest.java
```

### 7.2. `pom.xml`

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
    <artifactId>condition-diagnosis-demo</artifactId>
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

### 7.3. `ConditionDiagnosisTest.java`

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionDiagnosisTest {

    static class FeatureService {
    }

    static final class CustomFeatureService extends FeatureService {
    }

    @AutoConfiguration
    static class FeatureAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.feature",
                name = "enabled",
                havingValue = "true"
        )
        FeatureService featureService() {
            return new FeatureService();
        }
    }

    @AutoConfiguration
    static class FallbackAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(FeatureService.class)
        FeatureService fallbackFeatureService() {
            return new FeatureService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFeatureConfiguration {

        @Bean
        CustomFeatureService customFeatureService() {
            return new CustomFeatureService();
        }
    }

    @AutoConfiguration
    static class BrokenFeatureAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.feature",
                name = "enabled",
                havingValue = "true"
        )
        FeatureService brokenFeatureService() {
            throw new IllegalStateException(
                    "Required acme.feature.endpoint is missing");
        }
    }

    private final ApplicationContextRunner featureRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(FeatureAutoConfiguration.class));

    private static ConditionAndOutcomes outcomesFor(
            AssertableApplicationContext context, String methodName) {

        return ConditionEvaluationReport.get(context.getBeanFactory())
                .getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().endsWith("#" + methodName))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElseThrow(() ->
                        new AssertionError("No condition report for " + methodName));
    }

    private static List<String> messagesFor(ConditionAndOutcomes outcomes) {
        List<String> messages = new ArrayList<>();
        for (ConditionAndOutcome item : outcomes) {
            String message = item.getOutcome().getMessage();
            if (message != null) {
                messages.add(message);
            }
        }
        return messages;
    }

    @Test
    void missingOptInPropertyIsANormalNoMatch() {
        featureRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(FeatureService.class);

            ConditionAndOutcomes outcomes = outcomesFor(context, "featureService");
            assertThat(outcomes.isFullMatch()).isFalse();
            assertThat(messagesFor(outcomes))
                    .anyMatch(message -> message.contains("enabled"));
        });
    }

    @Test
    void explicitFalseIsANormalNoMatch() {
        featureRunner.withPropertyValues("acme.feature.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                    assertThat(outcomesFor(context, "featureService").isFullMatch())
                            .isFalse();
                });
    }

    @Test
    void typoInPropertyAlsoProducesNoMatchButIsUnexpectedToTheOperator() {
        featureRunner.withPropertyValues("acme.feature.enabld=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FeatureService.class);

                    ConditionAndOutcomes outcomes = outcomesFor(context, "featureService");
                    assertThat(outcomes.isFullMatch()).isFalse();
                    assertThat(messagesFor(outcomes))
                            .anyMatch(message -> message.contains("enabled"));
                });
    }

    @Test
    void explicitTrueMatchesAndRegistersTheBean() {
        featureRunner.withPropertyValues("acme.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(outcomesFor(context, "featureService").isFullMatch())
                            .isTrue();
                });
    }

    @Test
    void existingUserBeanMakesFallbackBackOff() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserFeatureConfiguration.class)
                .withConfiguration(
                        AutoConfigurations.of(FallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class))
                            .isInstanceOf(CustomFeatureService.class);

                    ConditionAndOutcomes outcomes =
                            outcomesFor(context, "fallbackFeatureService");
                    assertThat(outcomes.isFullMatch()).isFalse();
                });
    }

    @Test
    void matchedConditionCanStillBeFollowedByBeanCreationFailure() {
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO))
                .withConfiguration(AutoConfigurations.of(
                        BrokenFeatureAutoConfiguration.class))
                .withPropertyValues("acme.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class);
                });
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn test
```

**Kết quả mong đợi:** sáu test thành công; Maven Surefire thường hiển thị:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
```

Mã test không tự in stdout tùy biến. Log của `ConditionEvaluationReportLoggingListener` ở test cuối được ghi ở mức INFO và có thể xuất hiện trong log Maven.

Ý nghĩa của sáu phép thử:

1. Không khai báo property: condition no-match và context vẫn chạy. Đây là default OFF có chủ đích.
2. Khai báo `false`: condition no-match và context vẫn chạy.
3. Gõ nhầm `enabld`: kết quả condition cũng no-match, nhưng đây là lỗi ngoài dự kiến nếu người vận hành định bật tính năng.
4. Khai báo `true`: condition match và bean xuất hiện.
5. Ứng dụng có bean custom: condition fallback no-match và default nhường chỗ.
6. Property `true` làm condition match, nhưng factory method ném `IllegalStateException`; context thất bại. Đây là lỗi khởi tạo, không phải no-match.

Test thứ ba là điểm quan trọng: **ConditionEvaluationReport không thể tự biết người dùng có chủ ý gõ sai property hay không.** Cùng một outcome no-match có thể là đúng chính sách hoặc là lỗi vận hành. Test phải so sánh với trạng thái mong đợi của từng kịch bản.

## 8. Quy trình chẩn đoán theo thứ tự

Khi một bean hoặc auto-configuration không xuất hiện như mong đợi, xử lý theo trình tự:

### Bước 1: Xác định trạng thái ứng dụng

- Context khởi động thành công nhưng bean không có: bắt đầu từ condition report.
- Context khởi động thất bại: xem startup failure, exception chain và Failure Analysis trước.
- Context khởi động nhưng tính năng không hoạt động dù bean tồn tại: đây có thể là lỗi runtime/logic, không còn là câu hỏi condition.

### Bước 2: Tìm đúng source trong report

Tìm class auto-configuration hoặc method `@Bean` dự kiến tạo bean. Xem source có trong positive matches, negative matches, exclusions hay không xuất hiện.

- Positive: các condition ghi nhận cho source khớp.
- Negative: có ít nhất một condition không khớp.
- Excluded: lớp bị loại khỏi đánh giá theo cấu hình exclude.
- Không xuất hiện: xác minh auto-configuration có thực sự là candidate và được nạp hay không.

### Bước 3: Đọc từng condition và message

Không dừng ở chữ `NO MATCH`. Hãy ghi lại:

- Loại condition.
- Source class/method.
- Property, class, bean, resource hoặc application type mà condition kiểm tra.
- Message cho biết điều gì được tìm thấy hoặc không tìm thấy.

Nếu nhiều điều kiện cùng bảo vệ một source, chỉ một điều kiện không khớp đã có thể làm source không được áp dụng.

### Bước 4: Đối chiếu với ma trận hành vi mong đợi

Ví dụ cho một feature opt-in:

| Trạng thái mong đợi | Property/điều kiện | Kết quả đúng |
| --- | --- | --- |
| Người dùng không bật | `acme.feature.enabled` thiếu | No-match, không có bean |
| Người dùng tắt | `enabled=false` | No-match, không có bean |
| Người dùng bật | `enabled=true` | Match, bean có mặt |
| User cung cấp implementation | `@ConditionalOnMissingBean` tìm thấy bean | Fallback no-match, custom bean có mặt |
| Dependency tùy chọn không cài | `@ConditionalOnClass` không tìm thấy lớp | Integration no-match |

Chỉ khi kết quả thực tế khác ma trận mới cần sửa cấu hình/code.

### Bước 5: Nếu context thất bại, đọc exception gốc

Không kết luận “condition no-match” từ việc bean không tồn tại nếu ứng dụng thực ra đã fail trong quá trình refresh. Xem `Caused by` sâu nhất có ý nghĩa và FailureAnalyzer. Các lỗi YAML, bind, validation, dependency injection, bean factory method, class loading và external connection có cách xử lý khác nhau.

### Bước 6: Tái hiện trong `ApplicationContextRunner`

Tạo một test cho từng kết hợp property, classpath và bean của người dùng. Giữ test nhỏ để xác nhận điều kiện cụ thể; không cần dựng toàn bộ ứng dụng web nếu điều kiện chỉ phụ thuộc property hoặc bean.

## 9. Những hiểu lầm thường gặp

**Hiểu lầm 1: Mọi `negativeMatches` đều là lỗi.**  
Sai. Auto-configuration được thiết kế để không áp dụng khi thiếu điều kiện. Một ứng dụng có thể có nhiều negative matches hoàn toàn bình thường.

**Hiểu lầm 2: Context chạy được nghĩa là mọi cấu hình đều đúng.**  
Sai. Feature opt-in có thể bị tắt do gõ sai property mà không làm startup fail. Cần kiểm tra hành vi mong đợi, không chỉ trạng thái process.

**Hiểu lầm 3: Có property trong YAML thì condition chắc chắn match.**  
Sai. Có thể sai tên, sai prefix, sai profile, giá trị bị override, hoặc `havingValue` không khớp.

**Hiểu lầm 4: Condition report giải thích mọi startup failure.**  
Sai. Report ghi kết quả điều kiện. Lỗi binding, constructor, bean factory method, class loading hoặc kết nối ngoài phải được đọc qua exception/failure analysis.

**Hiểu lầm 5: Không thấy class trong negative matches tức nó bị condition từ chối.**  
Sai. Class có thể không được nạp, không có trong imports, bị exclude hoặc thiếu khỏi classpath. Kiểm tra candidate list, exclusions và artifact.

**Hiểu lầm 6: `@ConditionalOnMissingBean` không khớp nghĩa là starter hỏng.**  
Sai. Nếu ứng dụng đã cung cấp bean thay thế đúng kiểu, fallback không được tạo là hành vi back-off mong đợi.

**Hiểu lầm 7: Một no-match cần được sửa bằng cách ép condition thành match.**  
Sai. Nếu tính năng được thiết kế tùy chọn hoặc bean mặc định cần nhường chỗ, ép match có thể phá chính sách và tạo bean không mong muốn.

**Hiểu lầm 8: Chỉ cần xem một file `application.yml`.**  
Sai. `Environment` có nhiều property source và thứ tự ưu tiên; active profile, environment variables và command-line arguments có thể thay đổi giá trị hiệu lực.

## 10. Kết luận vận hành

Khi đọc báo cáo điều kiện, luôn phân loại theo hai trục độc lập:

- **Outcome:** condition match hay no-match?
- **Intent:** kết quả đó có đúng với yêu cầu triển khai hay không?

Nếu condition no-match đúng với ma trận cấu hình, đó là lựa chọn auto-configuration có chủ đích. Nếu no-match trái với ý định, kiểm tra key, giá trị, profile, classpath, bean type và thứ tự xử lý. Nếu condition đã match nhưng ứng dụng thất bại, chuyển sang chẩn đoán exception, binding và bean creation.

Một báo cáo tốt giúp trả lời “Spring đã quyết định điều gì và vì sao”. Nó không thay thế việc xác định “ứng dụng cần trạng thái nào”, cũng không thay thế startup exception hoặc kiểm thử hành vi.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing and Condition Reports](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `ConditionEvaluationReport`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Spring Boot 3.3 API — `ConditionEvaluationReportLoggingListener`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html)
- [Spring Boot 3.3 Actuator — Conditions Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
- [Spring Boot 3.3 API — `ConditionOutcome`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html)
