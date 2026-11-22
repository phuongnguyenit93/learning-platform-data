# Đọc ConditionEvaluationReport khi điều kiện không khớp trong Spring Boot

## 1. Tại sao một bean không xuất hiện dù ứng dụng khởi động được?

Khi làm việc với Spring Boot, bạn có thể gặp trường hợp `@Autowired` báo thiếu bean, một starter không tạo client như dự kiến, cache không được bật hoặc một auto-configuration bị “bỏ qua”. Phản ứng thường gặp là thêm `@Import`, đổi package scan hoặc sửa cấu hình một cách thử-và-sai. Cách đó dễ che mất nguyên nhân thực sự: **một hay nhiều điều kiện (`@Conditional`) không khớp**.

Spring Boot có **`ConditionEvaluationReport`**, bản ghi các đánh giá điều kiện trong quá trình tạo `ApplicationContext`. Báo cáo giúp trả lời:

- Configuration hay `@Bean` method nào được xem xét?
- Điều kiện nào trả `match=true`, điều kiện nào trả `match=false`?
- Vì sao `@ConditionalOnProperty` không thỏa: thiếu property, sai key hay giá trị không đúng?
- Có thực sự thiếu class optional hay do `@ConditionalOnClass` đã lọc auto-configuration?
- `@ConditionalOnMissingBean` “không khớp” vì **người dùng đã cung cấp bean thay thế**, tức là một hành vi **đúng thiết kế**?
- Chỉ một bean method bị loại, hay cả auto-configuration class không được đưa vào context?
- Context **khởi động bình thường nhưng không có bean**, hay context **khởi động thất bại** vì một exception khác?

**Trọng tâm bài học:** biết đọc báo cáo để xác định *điều kiện nào không khớp và vì sao*, rồi viết kiểm thử `ApplicationContextRunner` bao phủ cả nhánh positive/negative. Bài cung cấp dự án Java 17+, Spring Boot 3.5.x, JUnit Jupiter và AssertJ với các auto-configuration có điều kiện thật, cách trích báo cáo bằng API và `ConditionEvaluationReportLoggingListener`. Không cần mở HTTP server hoặc kết nối database.

## 2. Mô hình hoạt động: từ annotation đến outcome

Giả sử một starter metrics tự tạo `MetricClient` khi:
- Class tùy chọn `com.example.conditionlab.optional.MetricTransport` có mặt.
- Property `sample.metrics.enabled=true`.
- Ứng dụng chưa tự định nghĩa một `MetricClient`.

Luồng khái niệm:

```text
                 AUTO-CONFIGURATION CANDIDATE
                            |
                 @ConditionalOnClass?
                        /        \
                     no          yes
                     |            |
                 no bean    @ConditionalOnProperty?
                                  /        \
                                no          yes
                                |            |
                            no bean   @Bean metricClient()
                                            |
                                   @ConditionalOnMissingBean?
                                        /         \
                      User bean exists            No user bean
                             |                         |
                       BACK OFF                   CREATE DEFAULT
                             |                         |
                      no default bean            default bean
```

Spring Boot có thể đánh giá conditions ở nhiều phase (parse configuration, register bean definitions, import filtering). **Không được coi sơ đồ này là thứ tự tất cả condition evaluations**: thứ tự và số outcomes ghi vào report phụ thuộc metadata, phase và Spring Boot version.

Với mỗi condition được báo cáo, một `ConditionOutcome` có hai phần chính:
- `isMatch()` — `true` hoặc `false`.
- `getMessage()` — giải thích lý do đánh giá, có thể thay đổi câu chữ qua các phiên bản.

Một source có thể có **nhiều condition outcomes**. Nếu ít nhất một điều kiện cần thiết không khớp, `ConditionAndOutcomes.isFullMatch()` là `false`. Nếu tất cả outcomes được ghi nhận cho source đều match thì `isFullMatch()` là `true`.

**Đừng đồng nhất các thuật ngữ:**
- `positive match` là condition đã thỏa.
- `negative match` là condition không thỏa.
- `bean created` là kết quả registration/initialization thực tế.
- `application context started` là trạng thái khởi động toàn context.

Một source có positive matches **không nhất thiết** tương ứng một bean business duy nhất. Một negative match **không nhất thiết** là lỗi. Và report không thay thế kiểm tra bean thực tế bằng `context.getBean(...)`.

## 3. Báo cáo có những nhóm thông tin nào?

Trong log điều kiện (khi bật debug) hoặc endpoint Actuator `conditions`, thường gặp:

| Nhóm | Ý nghĩa | Cách đọc đúng |
|---|---|---|
| **Positive matches** | Source có conditions được đánh giá phù hợp | Không tự suy ra bean đã được sử dụng thành công |
| **Negative matches** | Ít nhất một condition không phù hợp | Tìm `OnPropertyCondition`, `OnClassCondition`, `OnBeanCondition` và message |
| **Unconditional classes** | Auto-configuration candidates không có conditions tương ứng | Không có nghĩa đã tạo mọi bean |
| **Exclusions** | Auto-configurations bị loại theo exclude rules | Không phải “negative match” vì condition |
| **Source** | Tên cấu hình hoặc `ClassName#beanMethod` | Phân biệt điều kiện ở cấp class với cấp method |
| **Condition** | Loại kiểm tra, ví dụ `OnClassCondition` | Hiểu nó đang hỏi điều gì |
| **Message** | Mô tả điều kiện được/không được đáp ứng | Dùng để điều tra, tránh assert nguyên văn từng ký tự |
| **Parent report** | Điều kiện từ parent BeanFactory/context (nếu có) | Lưu ý khi ứng dụng có management context/parent-child |

**Lưu ý lớn:** Trong output Actuator, một negative source có thể bao gồm cả danh sách **`notMatched` và `matched`**. Điều đó không mâu thuẫn: một condition của source thất bại, trong khi những condition khác vẫn thỏa.

### 3.1. Ví dụ đọc một negative match của property

Đây là ví dụ **minh họa nội dung log**, không phải transcript chính xác của một lần chạy:

```text
NEGATIVE MATCHES
----------------
MetricsAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty
        (sample.metrics.enabled=true)
        did not find property 'enabled'
        (OnPropertyCondition)
   Matched:
      - @ConditionalOnClass found required class
        'com.example.conditionlab.optional.MetricTransport'
        (OnClassCondition)
```

Cách suy luận:
1. Source là `MetricsAutoConfiguration`.
2. Một điều kiện property không match — nên auto-configuration không được áp dụng.
3. Optional class condition đã match; **không cần sửa dependency**.
4. Điều cần sửa là property key/value (hoặc xác nhận rằng feature disabled **đúng theo chủ ý**).
5. Không copy một dòng log làm assertion snapshot: message có thể đổi theo patch version, log format, ordering hoặc metadata.

### 3.2. Ví dụ đọc một negative match *đúng thiết kế*

```text
NEGATIVE MATCHES
----------------
MetricsAutoConfiguration#metricClient:
   Did not match:
      - @ConditionalOnMissingBean found a bean of type
        'com.example.conditionlab.api.MetricClient'
        (OnBeanCondition)
```

Nếu ứng dụng đã có `customMetricClient`, báo cáo trên **không phải lỗi**: auto-configuration nên **back off** để nhường bean người dùng. Điều cần test là context có đúng **một `MetricClient` của user** và không có `metricClient` mặc định.

### 3.3. Source cấp class khác source cấp method

Một class:

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "sample.metrics",
    name = "enabled",
    havingValue = "true")
class MetricsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MetricClient.class)
    MetricClient metricClient() {
        return new DefaultMetricClient("metric");
    }
}
```

Đây là đoạn minh họa chưa đủ imports; project đầy đủ nằm phía dưới. Trong report có thể thấy:
- `com.example.conditionlab.autoconfigure.MetricsAutoConfiguration` — conditions trên **class**.
- `com.example.conditionlab.autoconfigure.MetricsAutoConfiguration#metricClient` — condition trên **bean method**.

Nếu class-level `@ConditionalOnProperty` fail, bean method **có thể không được đánh giá**, nên không nhất thiết có entry method. **Việc thiếu entry ở method không tự chứng minh method condition đã match**; trước tiên phải xác định class chứa nó có được xem xét hay không.

## 4. API đọc ConditionEvaluationReport qua Java

Trong Spring Boot 3.5.x, hai import chính:

```java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
```

Để lấy report trong `ApplicationContextRunner.run(...)`:

```java
runner.run(context -> {
    ConditionEvaluationReport report =
            ConditionEvaluationReport.get(
                    context.getBeanFactory());

    var bySource = report.getConditionAndOutcomesBySource();

    bySource.forEach((source, outcomes) -> {
        System.out.println(source + " -> fullMatch="
                + outcomes.isFullMatch());

        outcomes.forEach(pair -> {
            boolean matched = pair.getOutcome().isMatch();
            String message = pair.getOutcome().getMessage();
            String conditionName =
                    pair.getCondition().getClass().getSimpleName();
            System.out.println("  " + conditionName
                    + " matched=" + matched
                    + " reason=" + message);
        });
    });
});
```

Đây là **fragment** trong lớp đã khai báo `ApplicationContextRunner runner`; nó minh họa cách truy cập report trong callback. Trong ứng dụng thật, **lọc `source` theo auto-configuration đang điều tra**, thay vì in mọi condition của một Boot app lớn (có thể hàng nghìn lines, kèm thông tin cấu hình nội bộ).

### 4.1. Các methods và cấu trúc dữ liệu

| API | Kiểu/kết quả | Vai trò |
|---|---|---|
| `ConditionEvaluationReport.get(beanFactory)` | `ConditionEvaluationReport` | Lấy/tạo report gắn với `ConfigurableListableBeanFactory` |
| `ConditionEvaluationReport.find(beanFactory)` | report hoặc `null` | Tìm report hiện có mà không bắt buộc tạo mới |
| `report.getConditionAndOutcomesBySource()` | `Map<String, ConditionAndOutcomes>` | Tra nguồn class/method |
| `outcomes.isFullMatch()` | `boolean` | Tất cả outcomes của source match? |
| `outcomes.iterator()` | Iterator của `ConditionAndOutcome` | Duyệt từng điều kiện |
| `outcomes.stream()` | Stream của `ConditionAndOutcome` | Hỗ trợ predicate/filter; có từ Boot 3.5 |
| `pair.getCondition()` | Spring `Condition` | Loại condition được đánh giá |
| `pair.getOutcome()` | `ConditionOutcome` | Match flag và message |
| `outcome.isMatch()` | `boolean` | True/false tại condition cụ thể |
| `outcome.getMessage()` | `String` hoặc `null` | Thông điệp diễn giải |
| `report.getExclusions()` | `List<String>` | Auto-config exclusions được ghi |
| `report.getUnconditionalClasses()` | `Set<String>` | Auto-config classes được xem xét không có conditions |
| `report.getParent()` | Report parent hoặc `null` | Đọc hierarchy nếu có |

**Không giả định `Map.get(source)` luôn có kết quả.** Nếu `null`, source có thể chưa được import, bị exclude/early-filter, không có điều kiện ghi nhận, thuộc context khác hoặc tên source không giống dự kiến. Lúc đó cần tìm nguồn cấu hình và tên class/method đúng trước khi kết luận.

### 4.2. In ra *chỉ* các lý do không match

```java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource().forEach(
    (source, outcomes) -> {
        if (!source.contains("MetricsAutoConfiguration")) {
            return;
        }
        outcomes.forEach(pair -> {
            if (!pair.getOutcome().isMatch()) {
                System.out.println(
                    source + " | "
                    + pair.getCondition().getClass().getSimpleName()
                    + " | "
                    + pair.getOutcome().getMessage());
            }
        });
    });
```

Đây là fragment dùng trong runner callback; không cung cấp output exact vì wording tùy Boot patch/condition implementation. Cách tiếp cận này giúp người học tập trung **vào lý do thực** thay vì scroll toàn bộ report.

### 4.3. Tránh bug khi sử dụng report để assert

Không nên làm:

```java
assertThat(report.getConditionAndOutcomesBySource()
        .get("SomeAutoConfiguration"))
        .isNull();
// rồi kết luận 'đã được bật mặc định'
```

Đoạn trên là anti-pattern minh họa. Entry `null` không mang nghĩa enabled/disabled; nó chỉ nói **không có entry với key đó trong map hiện tại**. Test phải kiểm tra:
1. Auto-config class đã được đưa vào runner/context chưa?
2. Key có phải fully qualified name hay `ClassName#beanMethod`?
3. `report.getExclusions()` hoặc condition import filtering có liên quan không?
4. Bean mong đợi có/không có?
5. Context start thành công hay thất bại?

## 5. ConditionEvaluationReportLoggingListener: xem report mà không tự duyệt map

Spring Boot cung cấp `ConditionEvaluationReportLoggingListener`, là một `ApplicationContextInitializer` dành cho báo cáo điều kiện. Trong test:

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(MetricsAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(
            LogLevel.INFO))
    .withPropertyValues(
        "sample.metrics.enabled=false")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(MetricClient.class);
    });
```

Đây là fragment cần imports/lớp demo được cung cấp bên dưới. `LogLevel.INFO` làm report được log qua logging framework. **Nó không bảo đảm hiển thị nguyên văn trong JUnit console** nếu runner/build/test logger capture hoặc cấu hình log level khác. Không dùng snapshot output để buộc mọi message bất biến.

Các phương án:
- `forLogLevel(LogLevel.INFO)`: hữu ích cho test chẩn đoán.
- `forLogLevel(LogLevel.DEBUG)`: hữu ích khi muốn report chỉ xuất hiện ở DEBUG.
- Đọc API trực tiếp trong test để **assert logic**, còn listener dùng để **chẩn đoán người đọc**.

**Không nên re-use cùng một instance của listener cho nhiều ApplicationContexts** khi tài liệu Javadoc yêu cầu lifecycle riêng; `forLogLevel(...)` tạo instance cho runner cụ thể. Tránh bật in full report cho hàng trăm tests ở CI vì rất nhiễu.

## 6. Dự án runnable tối thiểu Spring Boot 3.5.x / Java 17

Các file trong ví dụ:

```text
build.gradle
src/main/java/com/example/conditionlab/app/
    ConditionLabApplication.java
src/main/java/com/example/conditionlab/api/
    MetricClient.java
    DefaultMetricClient.java
src/main/java/com/example/conditionlab/optional/
    MetricTransport.java
src/main/java/com/example/conditionlab/autoconfigure/
    MetricsAutoConfiguration.java
src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
src/test/java/com/example/conditionlab/autoconfigure/
    MetricsConditionReportTest.java
```

**Vì sao chia packages như vậy?** `ConditionLabApplication` đặt ở `com.example.conditionlab.app`, không nằm ở parent `com.example.conditionlab`. Thao tác component scan của ứng dụng demo vì vậy không tự quét `MetricsAutoConfiguration` trong package khác. Production discovery được thực hiện qua `AutoConfiguration.imports`; `ApplicationContextRunner` đăng ký auto-config tường minh.

### 6.1. Gradle build (Groovy DSL)

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` cung cấp core Boot/Spring logging và auto-configuration. `starter-test` đưa vào JUnit Jupiter, AssertJ và test runner classes. `spring-boot-autoconfigure-processor` tạo optional auto-config metadata để Boot có thể lọc một số configurations sớm; **nó không thay file discovery `AutoConfiguration.imports`**. Không cần `starter-web`, datasource hay Docker để kiểm thử bean conditions trong ví dụ.

Java source trong bài dùng package names cố định và không gọi Internet; để chạy `./gradlew` cần một **Gradle wrapper** có sẵn. Dự án ví dụ không mô tả stdout “build successful” nếu chưa có build thực.

### 6.2. Boot application class

Tệp `src/main/java/com/example/conditionlab/app/ConditionLabApplication.java`:

```java
package com.example.conditionlab.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConditionLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ConditionLabApplication.class, args);
    }
}
```

Main có thể dùng cho smoke test discovery, nhưng các test `ApplicationContextRunner` không khởi chạy main. Không có web starter nên nếu chạy `bootRun` chỉ khởi tạo non-web application context.

### 6.3. Interface, default implementation và optional marker

Tệp `src/main/java/com/example/conditionlab/api/MetricClient.java`:

```java
package com.example.conditionlab.api;

@FunctionalInterface
public interface MetricClient {
    String emit(String eventName);
}
```

Tệp `src/main/java/com/example/conditionlab/api/DefaultMetricClient.java`:

```java
package com.example.conditionlab.api;

import java.util.Objects;

public final class DefaultMetricClient
        implements MetricClient {

    private final String prefix;

    public DefaultMetricClient(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    @Override
    public String emit(String eventName) {
        return prefix + ":" + Objects.requireNonNull(eventName);
    }
}
```

Tệp `src/main/java/com/example/conditionlab/optional/MetricTransport.java`:

```java
package com.example.conditionlab.optional;

/**
 * Marker đại diện một dependency tùy chọn.
 */
public final class MetricTransport {
    private MetricTransport() {
    }
}
```

Một starter thật sẽ dùng class của Micrometer, SDK hoặc transport module bên ngoài. Ở đây marker được đặt trong project để code chạy độc lập; `FilteredClassLoader` sẽ mô phỏng trường hợp class **không có trên classpath** mà không phải thay `build.gradle` giữa các test.

### 6.4. Auto-configuration có cả class-level và bean-method conditions

Tệp `src/main/java/com/example/conditionlab/autoconfigure/MetricsAutoConfiguration.java`:

```java
package com.example.conditionlab.autoconfigure;

import com.example.conditionlab.api.DefaultMetricClient;
import com.example.conditionlab.api.MetricClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(
    name = "com.example.conditionlab.optional.MetricTransport")
@ConditionalOnProperty(
    prefix = "sample.metrics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false)
public class MetricsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MetricClient.class)
    public MetricClient metricClient(
            @Value("${sample.metrics.prefix:metric}") String prefix) {
        return new DefaultMetricClient(prefix);
    }
}
```

**Cơ chế:**
- Nếu thiếu `MetricTransport`, điều kiện classpath không thỏa, class auto-config không được đưa vào như mong đợi.
- Nếu `sample.metrics.enabled` vắng/false, `OnPropertyCondition` âm tính. **Đây có thể là chủ đích**: starter không tự bật.
- Khi class và property cùng thỏa, `@ConditionalOnMissingBean` xét bean type `MetricClient`.
- Nếu user tự cung cấp một `MetricClient`, default bean `metricClient` không được đăng ký.
- Nếu tất cả condition cần thiết thỏa, default implementation trả chuỗi dạng `metric:order-created`; property `sample.metrics.prefix` có thể thay đổi prefix.

**Những điểm hay nhầm:**
- `@ConditionalOnClass` và `@ConditionalOnProperty` đặt ở **class level**.
- `@ConditionalOnMissingBean` đặt ở **`@Bean` method level**.
- Một method `@Bean` bị loại bởi `@ConditionalOnMissingBean` **không** có nghĩa cả class auto-config không tồn tại.
- `@Value` resolution diễn ra lúc tạo bean; lỗi bind/inject property là chuyện khác với một condition không match.

### 6.5. Metadata imports để auto-configuration được phát hiện

Tệp chính xác:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.example.conditionlab.autoconfigure.MetricsAutoConfiguration
```

Khi build starter JAR, tài nguyên trên phải nằm dưới `META-INF/spring/`. Trong Boot 3.x, `AutoConfiguration.imports` là cơ chế discovery auto-configuration thông dụng.

**Giới hạn của unit test:** `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(MetricsAutoConfiguration.class))` nạp class **trực tiếp**. Do đó runner test có thể pass kể cả khi bạn xóa nhầm `AutoConfiguration.imports`. Hãy thêm kiểm tra artifact resource hoặc smoke test `@SpringBootTest` thực khi phát hành starter.

## 7. Test JUnit: đọc report programmatically và kiểm chứng outcomes

Tệp `src/test/java/com/example/conditionlab/autoconfigure/MetricsConditionReportTest.java`:

```java
package com.example.conditionlab.autoconfigure;

import com.example.conditionlab.api.DefaultMetricClient;
import com.example.conditionlab.api.MetricClient;
import com.example.conditionlab.optional.MetricTransport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class MetricsConditionReportTest {

    private static final String AUTO_SOURCE =
            MetricsAutoConfiguration.class.getName();

    private static final String BEAN_SOURCE =
            AUTO_SOURCE + "#metricClient";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                        AutoConfigurations.of(
                            MetricsAutoConfiguration.class));

    private static ConditionAndOutcomes reportFor(
            org.springframework.boot.test.context.assertj
                    .AssertableApplicationContext context,
            String source) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(
                        context.getBeanFactory());

        ConditionAndOutcomes matches =
                report.getConditionAndOutcomesBySource()
                        .get(source);

        assertThat(matches)
                .as("Expected a recorded condition source: " + source)
                .isNotNull();

        return matches;
    }

    @Test
    void missingPropertyProducesOnPropertyNegativeMatch() {
        runner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                .doesNotHaveBean(MetricClient.class);

            ConditionAndOutcomes conditions =
                    reportFor(context, AUTO_SOURCE);

            assertThat(conditions.isFullMatch()).isFalse();

            assertThat(conditions.stream().anyMatch(pair ->
                !pair.getOutcome().isMatch()
                && pair.getCondition().getClass()
                        .getSimpleName()
                        .equals("OnPropertyCondition")))
                .isTrue();
        });
    }

    @Test
    void falsePropertyAlsoHasNegativeOutcome() {
        runner.withPropertyValues(
                "sample.metrics.enabled=false")
            .run(context -> {
                assertThat(context)
                    .doesNotHaveBean(MetricClient.class);

                ConditionAndOutcomes conditions =
                        reportFor(context, AUTO_SOURCE);

                assertThat(conditions.isFullMatch()).isFalse();

                assertThat(conditions.stream().anyMatch(pair ->
                    !pair.getOutcome().isMatch()))
                    .isTrue();
            });
    }

    @Test
    void wrongPropertyKeyDoesNotEnableAutoConfiguration() {
        runner.withPropertyValues(
                "sample.metric.enabled=true")
            .run(context -> {
                assertThat(context)
                    .doesNotHaveBean(MetricClient.class);

                assertThat(reportFor(context, AUTO_SOURCE)
                    .isFullMatch()).isFalse();
            });
    }

    @Test
    void enabledPropertyHasPositiveMatchesAndDefaultBean() {
        runner.withPropertyValues(
                "sample.metrics.enabled=true")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(MetricClient.class);

                assertThat(context)
                    .hasBean("metricClient");

                MetricClient client =
                    context.getBean(MetricClient.class);

                assertThat(client)
                    .isInstanceOf(DefaultMetricClient.class);
                assertThat(client.emit("order-created"))
                    .isEqualTo("metric:order-created");

                assertThat(
                    reportFor(context, AUTO_SOURCE)
                        .isFullMatch()).isTrue();

                assertThat(
                    reportFor(context, BEAN_SOURCE)
                        .isFullMatch()).isTrue();
            });
    }

    @Test
    void userBeanBackOffIsNegativeOnBeanNotAnError() {
        runner.withUserConfiguration(
                CustomMetricConfiguration.class)
            .withPropertyValues(
                "sample.metrics.enabled=true")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(MetricClient.class);

                assertThat(context)
                    .hasBean("customMetricClient");

                assertThat(context)
                    .doesNotHaveBean("metricClient");

                assertThat(
                    context.getBean(MetricClient.class)
                        .emit("order-created"))
                    .isEqualTo("custom:order-created");

                // Class-level conditions vẫn match.
                assertThat(
                    reportFor(context, AUTO_SOURCE)
                        .isFullMatch()).isTrue();

                // Bean-method condition âm tính vì user bean có sẵn.
                ConditionAndOutcomes methodConditions =
                        reportFor(context, BEAN_SOURCE);

                assertThat(methodConditions.isFullMatch())
                    .isFalse();

                assertThat(methodConditions.stream().anyMatch(pair ->
                    !pair.getOutcome().isMatch()
                    && pair.getCondition().getClass()
                        .getSimpleName()
                        .equals("OnBeanCondition")))
                    .isTrue();
            });
    }

    @Test
    void absentOptionalClassPreventsDefaultBean() {
        runner.withPropertyValues(
                "sample.metrics.enabled=true")
            .withClassLoader(
                new FilteredClassLoader(
                    MetricTransport.class))
            .run(context -> {
                assertThat(context.getStartupFailure()).isNull();
                assertThat(context)
                    .doesNotHaveBean(MetricClient.class);

                // Một số phases/metadata filters có thể ghi outcomes
                // ở cấp import; test không buộc exact report key/message.
                ConditionEvaluationReport report =
                    ConditionEvaluationReport.get(
                        context.getBeanFactory());

                assertThat(report).isNotNull();
            });
    }

    @Test
    void prefixPropertyChangesCreatedBeanBehavior() {
        runner.withPropertyValues(
                "sample.metrics.enabled=true",
                "sample.metrics.prefix=custom-prefix")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(MetricClient.class);

                assertThat(context.getBean(MetricClient.class)
                    .emit("order-created"))
                    .isEqualTo("custom-prefix:order-created");
            });
    }

    @Test
    void reportMessagesExplainConditionsButAreNotSnapshots() {
        runner.withPropertyValues(
                "sample.metrics.enabled=false")
            .run(context -> {
                ConditionAndOutcomes conditions =
                    reportFor(context, AUTO_SOURCE);

                assertThat(conditions.stream().anyMatch(pair ->
                    !pair.getOutcome().isMatch()
                    && pair.getOutcome().getMessage() != null))
                    .isTrue();

                // Không assert nguyên văn câu message:
                // wording có thể đổi giữa các phiên bản Boot.
            });
    }

    @Test
    void separateRunnerScenariosDoNotLeakProperties() {
        runner.withPropertyValues(
                "sample.metrics.enabled=true")
            .run(context ->
                assertThat(context)
                    .hasSingleBean(MetricClient.class));

        runner.run(context ->
            assertThat(context)
                .doesNotHaveBean(MetricClient.class));
    }

    @Test
    void intentionalBeanFailureIsNotAConditionMismatch() {
        runner.withUserConfiguration(
                FailingConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                        IllegalStateException.class);
            });
    }

    @Test
    void diagnosticListenerCanLogConditionReport() {
        runner.withPropertyValues(
                "sample.metrics.enabled=false")
            .withInitializer(
                ConditionEvaluationReportLoggingListener
                    .forLogLevel(LogLevel.INFO))
            .run(context -> {
                assertThat(context.getStartupFailure()).isNull();
                assertThat(context)
                    .doesNotHaveBean(MetricClient.class);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomMetricConfiguration {

        @Bean
        MetricClient customMetricClient() {
            return event -> "custom:" + event;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FailingConfiguration {

        @Bean
        String failingBean() {
            throw new IllegalStateException(
                "Synthetic bean initialization failure");
        }
    }
}
```

**Lưu ý import của `AssertableApplicationContext`:** Trong helper `reportFor` trên, tên type được xuống dòng ở qualified name để tiết kiệm chiều ngang. Với code Java trong IDE, nên thay bằng import đầy đủ một dòng:

```java
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
```

và sửa chữ ký helper thành `reportFor(AssertableApplicationContext context, String source)`. Chú ý **Java không cho phép ngắt qualified identifier bằng một dấu chấm rời mà không đúng tokenization**; phiên bản import rõ ràng giúp copy/paste an toàn. Các classes khác trong mẫu có imports tường minh.

### 7.1. Những kiểm chứng chính được thực hiện

| Test | Vấn đề được mô phỏng | Bằng chứng đúng |
|---|---|---|
| `missingPropertyProducesOnPropertyNegativeMatch` | Cờ enabled thiếu | Bean vắng + class-level negative `OnPropertyCondition` |
| `falsePropertyAlsoHasNegativeOutcome` | enabled=false | Bean vắng + `isFullMatch=false` |
| `wrongPropertyKeyDoesNotEnableAutoConfiguration` | Key sai `sample.metric.enabled` | Property đúng vẫn thiếu |
| `enabledPropertyHasPositiveMatchesAndDefaultBean` | enabled=true | Default bean đúng type/name/behavior và class/method positive |
| `userBeanBackOffIsNegativeOnBeanNotAnError` | User đã định nghĩa MetricClient | Custom bean thắng; method `OnBeanCondition` negative |
| `absentOptionalClassPreventsDefaultBean` | Optional marker bị ẩn | Class condition không thỏa, context vẫn start |
| `prefixPropertyChangesCreatedBeanBehavior` | Custom prefix | Bean nhận property thật, output đổi |
| `reportMessagesExplainConditionsButAreNotSnapshots` | Cần đọc reason | Message có giá trị nhưng không assert nguyên văn |
| `separateRunnerScenariosDoNotLeakProperties` | Nhiều runner scenarios | Không rò `Environment` từ case trước |
| `intentionalBeanFailureIsNotAConditionMismatch` | Factory method ném lỗi | `getStartupFailure()`, không nhầm negative match |
| `diagnosticListenerCanLogConditionReport` | Cần log report | Listener được đăng ký ở INFO, không snapshot stdout |

**Tại sao không chỉ assert report?** Code còn assert bean có/không có và hành vi `emit(...)`, bởi một report positive không phải kiểm thử chức năng. **Tại sao không assert message đầy đủ?** Văn bản message phụ thuộc Spring Boot version, formatting, tên bean và metadata. Test nên assert boolean condition/type, còn message là tài liệu điều tra.

### 7.2. Điều quan trọng khi context khởi động thất bại

`ApplicationContextRunner` cho phép quan sát lỗi startup qua callback. Khi `@Bean failingBean()` ném `IllegalStateException`, `assertThat(context).hasFailed()` và `getStartupFailure()` chỉ rõ đó là **failure lúc tạo bean**, không phải điều kiện property không khớp.

Trong một context đã fail, một số thao tác trên `BeanFactory` hoặc beans đã đóng có thể không còn an toàn. **Đừng cố lấy report bằng `getBeanFactory()` sau một failed refresh rồi suy ra nó luôn khả dụng**. Ưu tiên đọc startup failure/root cause và bật `--debug`/diagnostic listeners khi cần.

## 8. Khi một source không xuất hiện trong report: suy luận đúng

Không phải mọi trường hợp “bean không có” đều có một negative entry rõ ràng dưới đúng tên bạn đang tìm.

### 8.1. Auto-configuration chưa bao giờ được import

Nguyên nhân:
- Thiếu entry trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Nhầm package/class name hoặc file không đóng gói vào JAR.
- Test runner chỉ nạp một auto-config khác.
- Auto-configuration bị exclude bởi `spring.autoconfigure.exclude` hoặc `@SpringBootApplication(exclude=...)`.

Khi đó, report có thể **không có entry** cho class đang tìm. Hãy kiểm tra source discovery/import trước khi sửa `@ConditionalOnProperty`. Trong runner, dùng `withConfiguration(AutoConfigurations.of(...))` rõ ràng. Trong app thật, kiểm tra resource trong JAR và exclusions.

### 8.2. Condition được kiểm tra trong early auto-configuration filtering

Spring Boot có `AutoConfigurationImportFilter` và metadata do `spring-boot-autoconfigure-processor` tạo ra. Một số `@ConditionalOnClass` có thể được xử lý trước khi configuration class được đăng ký đầy đủ.

Điều đó có thể ảnh hưởng chi tiết report được ghi, thứ tự logging hoặc danh sách bean methods. **Không ép test phụ thuộc một source key/message nếu class đã bị lọc ở phase sớm.** Hãy dùng `FilteredClassLoader` và assert context không có bean; khi report có entry thì đọc outcome để bổ sung chẩn đoán.

### 8.3. Entry cấp method không tồn tại vì class-level condition fail

Nếu `@ConditionalOnProperty` tại class level không match, Spring thường không cần xử lý nested `@Bean` methods của class đó. Vì vậy report có thể không chứa:
`MetricsAutoConfiguration#metricClient`

Điều đó **không có nghĩa `@ConditionalOnMissingBean` luôn match**. Nó có thể đơn giản là **chưa từng được đánh giá trong scenario này**. Test user override phải để class condition match trước rồi mới xem bean-method outcome.

### 8.4. Điều kiện không được Boot báo cáo theo cùng cơ chế

`ConditionEvaluationReport` đặc biệt hữu ích cho các `SpringBootCondition` của auto-configuration. Một `@Conditional` custom không kế thừa/không tích hợp cơ chế ghi report tương ứng có thể không được biểu diễn giống một Boot built-in condition. Hãy đọc logic của condition, diagnostic logs và kết quả bean registration thay vì coi report là truy vết tuyệt đối mọi quyết định trong JVM.

## 9. Khai thác DEBUG report khi chạy Spring Boot application

Nếu đang debug app thật (không phải runner), Spring Boot có thể in **Conditions Evaluation Report** khi bật debug mode.

Ví dụ Gradle wrapper:

```bash
./gradlew bootRun --args='--debug'
```

Với executable JAR đã build:

```bash
java -jar build/libs/your-application.jar --debug
```

Tên JAR ở lệnh thứ hai là **minh họa đường dẫn**: phải thay bằng artifact thật. Không phải stdout cố định. Có thể bật `debug=true` qua Spring `application.properties`/environment nhưng cần lưu ý không phải mọi logger đều phải chuyển sang DEBUG; Boot debug mode bật các core loggers và condition report.

**Quy trình đọc report ở runtime:**
1. Tìm source với tên auto-configuration gần tính năng bị thiếu.
2. Vào mục `Negative matches` trước, tìm điều kiện không match.
3. Đọc `OnClassCondition` để biết class nào thiếu.
4. Đọc `OnPropertyCondition` để biết property/key nào sai.
5. Đọc `OnBeanCondition` để biết bean type/name nào đã có hoặc còn thiếu.
6. Nếu class-level match, tìm source method dạng `#beanMethod`.
7. Nếu không thấy source, kiểm tra discovery/imports, exclusions và context hierarchy.
8. Đối chiếu bean có thực sự tồn tại hay không (`ApplicationContext`, Actuator `beans` khi được phép).
9. Chỉ sửa điều kiện khi **hành vi mong muốn** khác với hành vi thực; không “sửa” một negative match cố ý.
10. Giảm mức logging về cấu hình vận hành an toàn sau khi điều tra.

**Đọc log ngay cả khi start thành công:** Một ứng dụng start bình thường có thể có hàng trăm negative matches hợp lệ (ví dụ không có WebFlux class trong app Servlet, không có datasource, cache hoặc messaging). Báo cáo không phải danh sách lỗi cần sửa hết.

## 10. Actuator /actuator/conditions: xem report trên ứng dụng đang chạy

Khi ứng dụng có **`spring-boot-starter-actuator`**, Actuator cung cấp endpoint `conditions`, phản ánh các conditions đã được đánh giá và lý do match/không match.

Mảnh dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Ví dụ properties cho **môi trường phát triển nội bộ đã bảo vệ**:

```properties
management.endpoints.web.exposure.include=health,conditions
```

Mặc định, chỉ một số endpoint như `health` được expose qua HTTP. Muốn đọc `/actuator/conditions` cần actuator dependency, endpoint được phép truy cập (Spring Boot 3.5 endpoint access policy), đã được expose qua web, và authentication/authorization thích hợp nếu Security đang bật.

**An toàn:** Conditions có thể tiết lộ package names, library presence, bean names và configuration internals. Không expose endpoint này ra Internet công khai. Dùng private management port/network, RBAC và masking/logging policy phù hợp. **Chỉ đọc được endpoint nếu nó đang bật và được phép truy cập**; không bật thêm chỉ để tiện test trong production.

### 10.1. Cấu trúc JSON quan trọng

Response Actuator có thể có dạng **minh họa đã rút gọn**:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "MetricsAutoConfiguration": [
          {
            "condition": "OnClassCondition",
            "message": "required class was found"
          }
        ]
      },
      "negativeMatches": {
        "MetricsAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "required property was not found"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "required class was found"
            }
          ]
        }
      },
      "unconditionalClasses": [],
      "parentId": null
    }
  }
}
```

Đây **không** phải exact JSON do dự án demo sinh ra: keys/IDs, source names và message thực tùy context/version. Mục đích là cho thấy:
- `contexts` nhóm theo application context ID.
- `positiveMatches` có condition/name và message.
- `negativeMatches` có hai mảng: `notMatched` và `matched`.
- `unconditionalClasses` liệt kê auto-configurations không điều kiện.
- `parentId` (khi có) thể hiện quan hệ context hierarchy.

Trong một số report, cùng source không đồng thời xuất hiện ở positive và negative sections như JSON rút gọn ở trên; sơ đồ chỉ minh họa cấu trúc field, **không khẳng định kết quả test có hai trạng thái đồng thời cho một source**. Khi đọc endpoint thật, follow schema của Spring Boot 3.5 Actuator API.

### 10.2. Actuator conditions khác actuator beans và env

- `/actuator/conditions`: **vì sao** conditions match hoặc không match.
- `/actuator/beans`: **cái gì đang được đăng ký** trong bean factory.
- `/actuator/env`: property sources và values (chịu sanitization/access controls).
- `/actuator/configprops`: bound configuration properties của các beans.

Cả bốn endpoint đều có rủi ro tiết lộ thông tin nội bộ; không expose tất cả chỉ vì một ca debug. Khi nguồn dữ liệu sai, kết hợp `conditions` với **property key thực** và bean list có thể giúp xác định lỗi nhanh, nhưng cần hạn chế quyền và ghi nhận truy cập.

## 11. Ma trận lỗi và cách đọc thông điệp theo từng loại condition

### 11.1. @ConditionalOnProperty

Ví dụ:
`@ConditionalOnProperty(prefix="sample.metrics", name="enabled", havingValue="true", matchIfMissing=false)`.

| Input environment | Outcome | Điều cần xác minh |
|---|---|---|
| Không có `sample.metrics.enabled` | Negative | Thiếu property là expected disabled |
| `sample.metrics.enabled=false` | Negative | Đúng giá trị tắt |
| `sample.metrics.enabled=enabled` | Negative | Giá trị không phải `true` |
| `sample.metric.enabled=true` | Negative | Sai **prefix/key** |
| `sample.metrics.enabled=true` | Positive nếu các điều kiện khác thỏa | Bean default hoặc back-off nếu user bean |
| Có prefix nhưng thiếu enabled | Negative | Prefix một mình không bật feature |

**Cẩn trọng:** Khi `havingValue` không được khai báo, `@ConditionalOnProperty` có semantics khác (property tồn tại và không bằng `false` theo Spring Boot) chứ không phải mọi giá trị phải bằng Boolean `true`. Đọc chính annotation và outcome message trước khi quyết định.

### 11.2. @ConditionalOnClass / @ConditionalOnMissingClass

Nếu condition class-level âm tính:
- JAR tùy chọn có thể không nằm trong runtime classpath.
- Artifact có thể có version sai hoặc class đã đổi package.
- Test có `FilteredClassLoader` cố ý ẩn class.
- Meta-annotation/custom condition có thể dùng tên class không đúng.

**Không tự thêm dependency** nếu feature đang cố ý disabled và không sử dụng thư viện đó. Khi class thực tế cần hiện diện, kiểm tra Gradle/Maven dependency resolution và runtime classpath. Nếu optional class được tham chiếu trực tiếp trong `@Bean` return type, cần cô lập bằng nested `@Configuration` có `@ConditionalOnClass` để tránh `NoClassDefFoundError` trước condition evaluation.

### 11.3. @ConditionalOnBean / @ConditionalOnMissingBean

Giả sử:

```java
@Bean
@ConditionalOnMissingBean(MetricClient.class)
MetricClient metricClient() {
    return new DefaultMetricClient("metric");
}
```

Đây là fragment của `MetricsAutoConfiguration`. Nếu có custom `MetricClient`, condition **negative** là đúng. Khi condition ngược là `@ConditionalOnBean(DataSource.class)`, missing datasource bean có thể chặn một dependent auto-configuration.

**Thứ tự đánh giá bean conditions rất quan trọng.** Spring Boot thường bảo đảm auto-configurations được xử lý sau user configurations; nếu hai auto-configurations phụ thuộc nhau, dùng `@AutoConfiguration(after=...) / before=...` để điều chỉnh evaluation order. Một “missing bean” outcome có thể phản ánh **bean definition type không được biết tại thời điểm đánh giá**, không phải nhất thiết Spring không thể tạo bean đó bao giờ.

### 11.4. @ConditionalOnWebApplication

Một auto-config Servlet-only có thể negative trong `ApplicationContextRunner` không-web. Đó là **đúng** vì runner tạo context hẹp.

Để kiểm tra chính xác:
- Servlet: `WebApplicationContextRunner`.
- Reactive: `ReactiveWebApplicationContextRunner`.
- Không phụ thuộc web: `ApplicationContextRunner`.

Không chuyển sang `@SpringBootTest(RANDOM_PORT)` chỉ để kiểm tra một condition đơn giản nếu web context runner đã đủ.

### 11.5. @ConditionalOnResource và @ConditionalOnExpression

`@ConditionalOnResource` phụ thuộc resource có mặt: file path/classpath resource sai có thể làm negative. Khi test, dùng resource test rõ ràng và avoid phụ thuộc current working directory trừ khi contract cần.

`@ConditionalOnExpression` dùng SpEL có thể gây early bean initialization nếu expression tham chiếu bean, làm bean chưa được post-process đầy đủ. Đừng dùng một expression phức tạp thay cho `@ConditionalOnProperty` nếu chỉ cần test property flag.

### 11.6. Conditions phối hợp

Một source có thể có cả `OnClassCondition` positive và `OnPropertyCondition` negative. Khi đó **full match là false**, nhưng thông tin classpath positive giúp thu hẹp điều tra: đừng tiếp tục tìm kiếm dependency khi lỗi thực là property missing.

Đọc **đủ tất cả outcome entries hiện diện**, đừng chỉ nhìn dòng negative đầu tiên. Dù vậy một số conditions có thể không được đánh giá do phase/short-circuit; report mô tả những gì thực sự được ghi, không buộc mọi condition phải chạy bất chấp nhánh đã fail.

## 12. Khi auto-config bị exclude: đây không phải property mismatch

Có nhiều cách loại auto-configuration:

```java
@SpringBootApplication(
    exclude = MetricsAutoConfiguration.class)
class ExcludedApplication {
}
```

Đây là fragment minh họa, không thuộc runnable project phía trên. Khi một auto-config bị exclude:
- Nó có thể không xuất hiện trong positive/negative matches vì **không được đưa vào danh sách đánh giá**.
- Report `getExclusions()` có thể ghi tên auto-config bị loại bởi pipeline tương ứng.
- Kiểm tra `spring.autoconfigure.exclude`, annotation `exclude`, deployment profile và test `@ImportAutoConfiguration(exclude=...)` nếu được sử dụng.

Không sửa `@ConditionalOnClass` để cứu một class bị exclude có chủ ý. **Phân biệt:**
1. Không được discover/import.
2. Được import nhưng exclude.
3. Được xem xét và condition âm tính.
4. Được đăng ký nhưng bean init thất bại.
5. Được tạo nhưng không inject đúng vì nhiều candidates/qualifier.

Từng nhóm dẫn đến cách khắc phục khác nhau.

## 13. Startup failure không tự có nghĩa là negative condition

Một context có thể khởi động **thành công** dù thiếu một bean tùy chọn do condition negative. Ngược lại, nó có thể khởi động **thất bại** vì:
- Bean factory method ném exception.
- Property bắt buộc không bind/convert được.
- Circular dependency hoặc ambiguous injection.
- Optional library class được load quá sớm gây `NoClassDefFoundError`.
- Datasource/server/SDK cần thiết không thể initialize.
- Bean được tạo nhưng health/IO dependency lỗi.

`ConditionEvaluationReport` trả lời chuyện conditions đã được đánh giá, **không thay thế `ApplicationContext` startup failure stack trace**.

Trong runner:
```java
runner.withUserConfiguration(FailingConfiguration.class)
    .run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
            .hasRootCauseInstanceOf(
                IllegalStateException.class);
    });
```

Đây là fragment dùng test class trong mục 7. Nó cho thấy một failure là exception khi khởi tạo bean; không có nghĩa `OnPropertyCondition` tạo negative mismatch.

**Tránh một kết luận nguy hiểm:** “Report có positive match nên dependency chắc chắn sẵn sàng.” Một `DataSourceAutoConfiguration` có thể match conditions nhưng datasource bean init hoặc database connection về sau vẫn fail. Positive match là bằng chứng về **điều kiện**, không phải end-to-end health.

## 14. Không viết assertion phụ thuộc nguyên văn message

Một test yếu:

```java
assertThat(outcome.getMessage())
    .isEqualTo(
        "@ConditionalOnProperty (sample.metrics.enabled=true) did not find property");
```

Đây là đoạn minh họa trong test có `outcome`. Nó dễ fail vô lý khi Boot thay wording, whitespace, bean names hoặc cách render. Một test tốt tập trung:
- `outcomes.isFullMatch()` true/false.
- `getOutcome().isMatch()` cho condition cụ thể.
- `getCondition().getClass().getSimpleName()` hoặc logic xác định condition type.
- Bean có/không có và đúng implementation/value.
- `getMessage()` được đọc để debug, không bị coi là API contract có định dạng bất biến.

Nếu test là **tool chuyên parse report**, có thể kiểm thử format của chính parser nhưng phải chấp nhận quản lý compatibility theo Boot versions. Không áp nguyên tắc snapshot mọi report vào các auto-config tests phổ thông.

### 14.1. Một helper lọc kết quả khi debug

```java
private static void printRelevantReasons(
        ConditionEvaluationReport report,
        String sourceFragment) {

    report.getConditionAndOutcomesBySource()
        .forEach((source, outcomes) -> {
            if (!source.contains(sourceFragment)) {
                return;
            }
            outcomes.forEach(pair -> {
                String state =
                    pair.getOutcome().isMatch()
                        ? "MATCH"
                        : "NO MATCH";
                System.out.println(
                    state + " | " + source
                    + " | " + pair.getCondition()
                        .getClass().getSimpleName()
                    + " | " + pair.getOutcome().getMessage());
            });
        });
}
```

Đây là **method minh họa** trong một Java test helper, cần import `ConditionEvaluationReport`. Nó không in secrets trực tiếp trừ khi message của custom condition chứa dữ liệu nhạy cảm. Dù vậy, **không nên ghi API tokens/passwords trong messages của custom conditions**; report/log có thể được xuất ra CI hoặc Actuator.

## 15. Condition report trong CI: chỉ bật khi có ích

Một báo cáo condition đầy đủ trong full Spring Boot app có thể dài và nhiễu. Quy trình hiệu quả:
1. Viết runner test nhỏ cho một auto-configuration.
2. Assert branch behavior bằng beans + condition boolean.
3. Bật `ConditionEvaluationReportLoggingListener` ở **một test chẩn đoán** hoặc dùng helper lọc sources.
4. Trong CI, có thể capture report khi test fail bằng logger/test infrastructure phù hợp, nhưng không phát tán credential/internal path.
5. Khi cần debug full app, bật `--debug` cục bộ hoặc endpoint `conditions` trong môi trường đã bảo vệ.
6. Khi đã tìm ra nguyên nhân, sửa key, dependency, ordering hoặc expectation, **không “làm im” report bằng cách remove conditions**.
7. Giữ tests cho cả nhánh không match **đúng theo thiết kế** để ngăn regression khi thêm dependency/đổi cấu hình.

**Điểm QA:** Không cần để CI fail mỗi khi report có negative match. Một starter tốt thường có nhiều conditions âm tính cố ý vì các tích hợp optional không được bật.

## 16. Ví dụ case study: không thấy bean dùng cách debug nào?

Giả sử `MetricClient` không tồn tại:

**Trường hợp A — enabled property thiếu:**
- Context start thành công.
- Report `OnPropertyCondition` negative.
- `MetricTransport` đã hiện diện.
- Giải pháp: nếu feature cần bật, đặt đúng `sample.metrics.enabled=true`; nếu intentionally disabled, giữ test negative.

**Trường hợp B — enabled=true nhưng missing optional class:**
- Report `OnClassCondition` negative hoặc early import filter đã loại class.
- Không có bean.
- Giải pháp: kiểm tra dependency optional trên runtime classpath; nếu không sử dụng feature, đó là outcome expected.

**Trường hợp C — có custom bean:**
- Class conditions match.
- Method `#metricClient` `OnBeanCondition` negative.
- Context vẫn có **custom `MetricClient`**.
- Đây là **success của cơ chế back-off**, không phải bug.

**Trường hợp D — class imported đúng nhưng bean factory method ném exception:**
- Context fail startup.
- Report có thể chứa positive class/method conditions.
- Root cause ở Java exception của bean initialization.
- Giải pháp: sửa factory/binding/dependency; không chỉ đổi property.

**Trường hợp E — report không tìm thấy source:**
- Kiểm tra `AutoConfiguration.imports`, actual package name, `AutoConfigurations.of`, exclusions, config phase và context hierarchy.
- Không kết luận positive/negative từ `null`.

**Trường hợp F — context không phải Servlet/Reactive:**
- `OnWebApplicationCondition` negative.
- Nếu test muốn nhánh Servlet/Reactive, chọn runner type tương ứng; đừng bật HTTP server trọn bộ nếu không cần.

## 17. Bảng lỗi thường gặp và hướng sửa

| Dấu hiệu | Nguyên nhân có thể | Hành động |
|---|---|---|
| Bean không có, context start tốt | Condition âm tính đúng/sai theo thiết kế | Đọc source + reason, so với contract |
| `OnPropertyCondition`: did not find property | Thiếu property/key/prefix | Kiểm tra `withPropertyValues`, config profile |
| Property có nhưng value không match | `havingValue` khác hoặc spelling sai | Xem annotation, enum/boolean semantics |
| `OnClassCondition` negative | Optional class không ở runtime classpath | Kiểm tra JAR/dependency, `FilteredClassLoader` |
| `OnBeanCondition` negative cho MissingBean | User bean đã tồn tại | Assert custom bean thắng, không cố tạo default |
| `OnBeanCondition` negative cho OnBean | Dependency bean chưa được biết | Ordering/type/registration của dependency |
| Class positive nhưng bean method negative | Method-level condition fail | Tìm `Class#method` key, không chỉ class |
| Missing method key | Class-level condition fail/chưa process method | Kiểm tra class report trước |
| Missing source key | Excluded/unimported/early filtered/khác context | Imports, exclusions, key, hierarchy |
| `ConditionEvaluationReport.get(...)` rỗng | Context không chạy pipeline conditions tương ứng | Xác định runner withConfiguration và phase |
| `hasSingleBean` fail với nhiều candidates | Back-off/type/ordering sai | Đọc names/type, @Primary, bean conditions |
| `@ConditionalOnProperty` unexpected match | Không khai báo havingValue | Dùng explicit `havingValue="true"` nếu muốn |
| `NoClassDefFoundError` khi class optional vắng | Signature/load class sớm | Nested conditional configuration |
| Report cho class có match nhưng context fail | Bean init/binding/IO lỗi | `getStartupFailure()` và root cause |
| `@WebApplication` condition fail trong runner | Dùng plain context cho web-only config | Web/Reactive WebApplicationContextRunner |
| Report quá dài | Bật full debug cho mọi test | Lọc theo source và chỉ bật khi debug |
| Actuator 404/403 ở `conditions` | Endpoint chưa expose/không được access | Kiểm tra actuator dependency/exposure/security |
| Starter test pass nhưng app không auto-import | Thiếu file `AutoConfiguration.imports` | Verify JAR resources + smoke test |
| Test fail khi Boot upgrade vì log text | Assert nguyên message | Assert match flag/type/bean behavior |
| Report không có condition custom | Custom condition không được ghi như BootCondition | Review implementation và bean registration |
| `@ConditionalOnBean` phụ thuộc order | Đánh giá trước khi dependency defined | AutoConfig after/before + tests |
| Test native image không chạy runner | Runner không dành cho native test execution | JVM runner tests và native smoke tests |
| Negative matches bị coi là warnings | Nhầm report với error report | Phân biệt expected optional outcomes |
| Startup logs có debug report nhưng bean không dùng | Feature disabled/custom bean/candidate khác | Kiểm tra bean map, qualifiers, actual injection |

## 18. Bài thực hành: tự tìm nguyên nhân trong ba phút

Thực hành sau khi tạo project mẫu:

1. Chạy `missingPropertyProducesOnPropertyNegativeMatch`; xác định class source và `OnPropertyCondition` negative.
2. Đổi sang `sample.metrics.enabled=true` trong scenario: bean mặc định xuất hiện, class và method outcomes trở thành full match.
3. Thêm `CustomMetricConfiguration`: default bean back off, nhưng custom bean vẫn thực thi được; đọc **method source** thay vì chỉ class.
4. Dùng `new FilteredClassLoader(MetricTransport.class)`: class-level condition không còn thỏa; xác nhận không có default.
5. Bật `ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)` trong một scenario; đối chiếu thông điệp với các assertions structured.
6. Cố ý nhập sai key `sample.metric.enabled=true` (thiếu chữ s): đọc `OnPropertyCondition` và xác định lỗi cụ thể.
7. Thêm test tạo bean ném exception: chứng minh startup failure **khác negative match**.
8. Nếu muốn thấy full runtime conditions, dùng ứng dụng demo và bật `--debug`, không cần dùng một scanner toàn bộ classpath tự viết.

**Câu hỏi tự kiểm tra:**

- Vì sao `ConditionAndOutcomes.isFullMatch()==false` không có nghĩa auto-config bug?
- Khi source `MetricsAutoConfiguration#metricClient` negative, điều kiện ở class có nhất thiết negative không?
- Điều gì khiến một source không xuất hiện trong map report?
- Khi report positive nhưng context fail, bạn xem gì tiếp?
- Vì sao không nên snapshot nguyên văn `getMessage()` vào JUnit assertion?
- `/actuator/conditions` cần điều kiện gì để được expose an toàn?
- Tại sao runner test pass không tự chứng minh discovery metadata đã được đóng gói đúng?

## 19. Lệnh chạy dự án và đánh giá kết quả

Khi project có Gradle wrapper, chạy một test class:

```bash
./gradlew test --tests "com.example.conditionlab.autoconfigure.MetricsConditionReportTest"
```

Chạy từng method để điều tra nhanh:

```bash
./gradlew test --tests "com.example.conditionlab.autoconfigure.MetricsConditionReportTest.missingPropertyProducesOnPropertyNegativeMatch"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.conditionlab.autoconfigure.MetricsConditionReportTest"
```

Nếu dự án dùng Maven wrapper với `pom.xml`/BOM/dependencies tương đương:

```bash
./mvnw -Dtest=MetricsConditionReportTest test
```

Dự án cung cấp **11 phương thức JUnit `@Test` được thiết kế**. Đây là code và **expected behavior**, không phải kết quả thực thi: không có bằng chứng 11 tests đã chạy trong môi trường hiện tại. Cần xem `build/reports/tests/test/index.html` hoặc `target/surefire-reports/` của module, kiểm tra số test thực sự được discover và trạng thái pass/fail/skip.

Với việc chạy application `bootRun`, auto-configuration mặc định **không tạo MetricClient** nếu không có property enabled; điều đó là expected. Không mong chờ program in `metric:order-created` ra stdout, vì demo main không gọi `MetricClient.emit(...)` hoặc `System.out.println`. Nếu bật `--debug`, format report/verbosity phụ thuộc Spring Boot patch và logging config.

## 20. Checklist QA trước khi chốt một bài test conditions

- [ ] Xác định đúng auto-config source (class và bean method) đang điều tra.
- [ ] Có `ApplicationContextRunner` chỉ nạp auto-config cần thiết.
- [ ] Test negative property missing/false/wrong key và positive true.
- [ ] Test optional dependency absent bằng `FilteredClassLoader` nếu cần.
- [ ] Test user bean override/back-off qua `withUserConfiguration`.
- [ ] Lấy report từ `ConditionEvaluationReport.get(context.getBeanFactory())`.
- [ ] Phân biệt `isFullMatch` của source với `isMatch` của từng `ConditionOutcome`.
- [ ] Chỉ assert loại condition và match flag, không snapshot nguyên `getMessage()`.
- [ ] Kiểm tra bean thực tế (type/name/behavior), không chỉ report outcomes.
- [ ] Không coi mọi negative match là failure.
- [ ] Khi source không có trong map, kiểm tra imports/exclusions/phase/context key.
- [ ] Phân biệt condition mismatch với bean startup failure; dùng `getStartupFailure()` khi cần.
- [ ] Không giữ context/beans sau `ApplicationContextRunner.run` callback.
- [ ] Dùng đúng Web/Reactive runner cho `@ConditionalOnWebApplication`.
- [ ] Khi phát hành starter, kiểm tra `AutoConfiguration.imports` trong JAR, không chỉ runner.
- [ ] Actuator conditions endpoint chỉ dùng trong môi trường được kiểm soát.
- [ ] Không log credentials/PII trong custom condition messages.
- [ ] Không thử buộc mọi optional auto-config thành positive chỉ để làm đẹp report.
- [ ] Khi dùng Spring Boot 4.x, đối chiếu packages/API theo phiên bản thay vì copy imports 3.5.
- [ ] Chạy JUnit bằng Gradle/Maven và đọc report thật trước khi báo runtime PASS.

## 21. Nguồn chính thức và API để kiểm chứng

- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): các conditional annotations, `ApplicationContextRunner`, `FilteredClassLoader`, listener đọc report.
- [ConditionEvaluationReport (Boot 3.5 Javadoc)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): `get`, `find`, `getConditionAndOutcomesBySource`, `getExclusions`.
- [ConditionAndOutcomes (Boot 3.5 Javadoc)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcomes.html): `isFullMatch`, `iterator`, `stream`.
- [ConditionOutcome (Boot 3.5 Javadoc)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html): `isMatch`, `getMessage`.
- [ConditionEvaluationReportLoggingListener (Boot 3.5 Javadoc)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): in report ở INFO/DEBUG.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): exposure/access của `conditions` và lưu ý bảo mật.
- [Spring Boot 3.5 — Conditions Actuator REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/conditions.html): cấu trúc JSON `positiveMatches`/`negativeMatches`.
- [Spring Boot 3.5 — Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/using/auto-configuration.html): bật debug để xem conditions report.
- [Spring Framework — Core Container / Java Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): Spring bean definitions và context lifecycle.

**Kết luận:** Khi một auto-configuration không tạo bean, đừng đoán nguyên nhân từ việc bean vắng mặt. Dùng `ConditionEvaluationReport` để tìm **đúng source class/method**, đọc `ConditionAndOutcomes.isFullMatch()`, từng `ConditionOutcome.isMatch()` và `getMessage()`, rồi đối chiếu với **beans thực tế**. Một negative `OnPropertyCondition` có thể báo sai property, còn negative `OnBeanCondition` có thể là thành công của cơ chế user override. Nếu report không có source, kiểm tra import/exclusion/phase; nếu context fail, đọc startup exception. Dùng `ApplicationContextRunner` để bảo vệ cả nhánh match và không match bằng các tests nhỏ, nhanh và ổn định; chỉ dùng full application/Actuator khi cần điều tra phạm vi lớn hơn.