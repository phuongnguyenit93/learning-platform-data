# Đọc positive matches, negative matches, exclusions và unconditional classes trong Condition Evaluation Report

## 1. Mục đích của báo cáo điều kiện

Spring Boot có thể tìm thấy một auto-configuration trên classpath nhưng **không đăng ký bean** vì một hoặc nhiều điều kiện không đạt. Ngược lại, một auto-configuration có thể được áp dụng và tạo bean mặc định vì không có bean thay thế. Khi ứng dụng khởi động khác với dự kiến, chỉ nhìn dependency hoặc tên bean thường không đủ để biết nguyên nhân.

**Condition Evaluation Report** ghi lại kết quả đánh giá các điều kiện trên configuration và auto-configuration. Báo cáo giúp trả lời:

- Auto-configuration hoặc phương thức bean nào đã **match** tất cả điều kiện?
- Source nào **không match**, và condition nào làm nó thất bại?
- Những auto-configuration nào đã bị **exclude** khỏi quá trình đánh giá?
- Những auto-configuration nào được xét nhưng **không có điều kiện áp dụng** ở cấp lớp?

Bốn nhóm này liên quan nhưng không đồng nghĩa. Một lớp bị exclude không phải là negative match; một unconditional class cũng không có nghĩa tất cả bean method bên trong chắc chắn được tạo.

## 2. Bốn nhóm thông tin cần phân biệt

| Nhóm | Ý nghĩa | Nơi đọc |
|---|---|---|
| **Positive matches** | Source (configuration class hoặc bean method) có các điều kiện được đánh giá và tất cả đều match | Actuator `/actuator/conditions`; `getConditionAndOutcomesBySource()` |
| **Negative matches** | Source có ít nhất một condition không match; báo cáo chỉ ra condition thất bại và những condition đã match | Actuator `/actuator/conditions`; `getConditionAndOutcomesBySource()` |
| **Exclusions** | Tên các auto-configuration đã bị loại khỏi condition evaluation | `ConditionEvaluationReport.getExclusions()` |
| **Unconditional classes** | Tên các auto-configuration đã được xét nhưng bản thân class không có điều kiện áp dụng | `ConditionEvaluationReport.getUnconditionalClasses()`; Actuator `unconditionalClasses` |

Báo cáo chia kết quả theo **source**: có thể là tên đầy đủ của configuration class hoặc tên method dạng `com.example.ReportAutoConfiguration#reportFeature`. Đừng chỉ tìm theo tên bean: source trong báo cáo là class/method đã khai báo điều kiện.

Ví dụ tư duy:

```text
ReportedAutoConfiguration#reportFeature
  @ConditionalOnProperty(enabled=true)       MATCH
  @ConditionalOnBean(ReportGateway.class)    NO MATCH
  => NEGATIVE MATCH: bean method không được đăng ký

ExcludedAutoConfiguration
  được đưa vào danh sách loại trừ
  => EXCLUSION: condition của class không được đánh giá

UnconditionalAutoConfiguration
  không có condition ở cấp class
  => UNCONDITIONAL CLASS
```

Đây là sơ đồ minh họa, không phải log thực tế.

## 3. Positive matches: vì sao cấu hình được chấp nhận?

Một positive match có nghĩa các điều kiện áp dụng cho source đều đạt. Ví dụ:

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "enabled",
            havingValue = "true"
    )
    @ConditionalOnBean(ReportGateway.class)
    ReportFeature reportFeature() {
        return new ReportFeature();
    }
}
```

Đây là đoạn auto-configuration minh họa; `ReportGateway` và `ReportFeature` là các kiểu ứng dụng giả định.

Nếu context có `demo.report.enabled=true` và đã có bean `ReportGateway`, method `reportFeature` có thể match. Trong Actuator, source tương ứng xuất hiện dưới `positiveMatches`, cùng tên condition và thông điệp giải thích từng điều kiện đạt.

Một positive match **không chứng minh toàn bộ ứng dụng đã chạy thành công**. Nó cho biết điều kiện cho phép đăng ký source. Bean vẫn có thể thất bại khi khởi tạo do constructor, dependency, kết nối ngoài hoặc logic runtime.

## 4. Negative matches: tìm đúng điều kiện làm cấu hình bị loại

Giữ ví dụ trên nhưng ứng dụng không có `ReportGateway`. Property đã match, bean condition không match. Method `reportFeature` không được đăng ký.

Trong Actuator, `negativeMatches` hiển thị theo source. Mỗi source thường có hai danh sách:

- `notMatched`: những condition **không đạt**, đây là nơi nên đọc đầu tiên để tìm nguyên nhân.
- `matched`: những condition đã đạt; chúng giúp xác nhận phần cấu hình nào đã đúng.

Ví dụ JSON rút gọn về cấu trúc:

```json
{
  "contexts": {
    "application": {
      "negativeMatches": {
        "com.example.ReportAutoConfiguration#reportFeature": {
          "notMatched": [
            {
              "condition": "OnBeanCondition",
              "message": "Không tìm thấy bean ReportGateway"
            }
          ],
          "matched": [
            {
              "condition": "OnPropertyCondition",
              "message": "demo.report.enabled matched"
            }
          ]
        }
      }
    }
  }
}
```

Các chuỗi `message` ở ví dụ trên được viết để minh họa ý nghĩa; thông điệp thật do condition Spring Boot tạo ra và có thể khác theo phiên bản hoặc ngữ cảnh.

**Cách đọc có hệ thống:**

1. Tìm source trong `negativeMatches`.
2. Đọc từng phần tử của `notMatched` để xác định điều kiện không đạt.
3. Đọc `matched` để biết các điều kiện khác đã đạt hay chưa.
4. Từ tên condition, xác định nhóm kiểm tra: classpath, property, bean, web application, resource, Java version hoặc điều kiện tùy chỉnh.
5. Kiểm tra dữ liệu thực tế tại thời điểm context được tạo: dependency runtime, giá trị Environment, bean definitions và thứ tự auto-configuration.
6. Sau khi sửa, khởi động lại hoặc chạy test context mới để xem kết quả mới.

### Một source có nhiều condition

Các annotation condition trên cùng một class hoặc bean method thường phối hợp theo logic **AND**: mọi điều kiện phải match thì source mới được chấp nhận. Một điều kiện false đủ khiến source trở thành negative match.

Với điều kiện lồng như `AnyNestedCondition`, `AllNestedConditions` hoặc `NoneNestedConditions`, thông điệp có thể chứa nhiều lớp con và kết quả trung gian. Đọc toàn bộ message thay vì chỉ nhìn tên `OnPropertyCondition` hoặc `OnBeanCondition` bên ngoài.

### Negative match không luôn là lỗi

Ví dụ `@ConditionalOnMissingBean` không match vì ứng dụng đã tự cung cấp bean tương ứng là hành vi **back-off có chủ đích**. Một auto-configuration web không match trong ứng dụng CLI cũng có thể hoàn toàn bình thường. Hãy đối chiếu với thiết kế mong muốn trước khi sửa.

## 5. Exclusions: lớp bị loại không được đánh giá như negative match

Auto-configuration có thể bị loại trừ qua:

- `@SpringBootApplication(exclude = ...)` hoặc `excludeName = ...`.
- `@EnableAutoConfiguration(exclude = ...)` hoặc `excludeName = ...`.
- Property `spring.autoconfigure.exclude` trong Environment.

Ví dụ:

```java
@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Tên trong `excludeName` phải là **fully qualified class name của auto-configuration**. Với `exclude`, có thể dùng class literal nếu kiểu có mặt trên compile classpath. Với property, có thể khai báo một hoặc nhiều tên theo định dạng danh sách phù hợp.

Khác biệt quan trọng:

- **Negative match:** class hoặc method đã được xét điều kiện, ít nhất một condition không đạt.
- **Exclusion:** auto-configuration bị bỏ khỏi danh sách cần đánh giá. Vì vậy không có kết quả condition pass/fail cho chính candidate đó.
- **Unconditional:** class được xét nhưng không có condition áp dụng ở cấp class.

Trong API, `ConditionEvaluationReport.getExclusions()` trả về danh sách tên lớp đã bị exclude. Javadoc mô tả đây là các class bị loại khỏi condition evaluation.

Một chi tiết dễ nhầm: schema JSON công khai của Actuator `/actuator/conditions` mô tả `positiveMatches`, `negativeMatches` và `unconditionalClasses`, nhưng **không liệt kê trường `exclusions`**. Nếu cần đọc danh sách exclusions trực tiếp, dùng `ConditionEvaluationReport.getExclusions()` trong code hoặc đọc Condition Evaluation Report được ghi vào log. Đừng kết luận “không có exclusion” chỉ vì không thấy trường exclusions trong JSON Actuator.

## 6. Unconditional classes: không có điều kiện ở cấp auto-configuration class

`ConditionEvaluationReport.getUnconditionalClasses()` trả về tập tên các class đã được đánh giá nhưng không có condition áp dụng. Actuator hiển thị nhóm này trong `contexts.*.unconditionalClasses`.

Một unconditional class **không đồng nghĩa mọi bean method bên trong chắc chắn được đăng ký**. Ví dụ:

```java
@AutoConfiguration
public class CommonInfrastructureAutoConfiguration {

    @Bean
    Object baseInfrastructureMarker() {
        return new Object();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.extra",
            name = "enabled",
            havingValue = "true"
    )
    Object optionalInfrastructureMarker() {
        return new Object();
    }
}
```

Class không có condition ở cấp lớp, nhưng bean method thứ hai vẫn có condition riêng. Vì vậy class có thể xuất hiện trong unconditional classes trong khi một bean method của nó vẫn có thể positive hoặc negative match.

Khi đọc unconditional classes:

- Xem đây là thông tin về **class-level condition**, không phải kết luận cuối cùng cho mọi method.
- Nếu đang điều tra một bean cụ thể, tiếp tục tìm source dạng `ClassName#beanMethod` trong positive/negative matches.
- Đừng thêm condition chỉ để làm biến mất một class khỏi danh sách unconditional; nếu cấu hình được thiết kế để luôn áp dụng, trạng thái này là bình thường.

## 7. Đọc report trực tiếp trong Java bằng `ConditionEvaluationReport`

Spring Boot 3.3 cung cấp API trong package `org.springframework.boot.autoconfigure.condition`. Report gắn với `BeanFactory` của application context.

Ví dụ sau đọc các outcomes sau khi context đã refresh:

```java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.context.ConfigurableApplicationContext;

import java.util.Map;

public final class ConditionReportReader {

    private ConditionReportReader() {
    }

    public static void print(ConfigurableApplicationContext context) {
        ConditionEvaluationReport report =
                ConditionEvaluationReport.find(context.getBeanFactory());

        if (report == null) {
            System.out.println("No condition report is available.");
            return;
        }

        System.out.println("=== EXCLUSIONS ===");
        report.getExclusions().forEach(System.out::println);

        System.out.println("=== UNCONDITIONAL CLASSES ===");
        report.getUnconditionalClasses().forEach(System.out::println);

        System.out.println("=== CONDITION OUTCOMES BY SOURCE ===");
        for (Map.Entry<String, ConditionAndOutcomes> entry
                : report.getConditionAndOutcomesBySource().entrySet()) {

            System.out.println("Source: " + entry.getKey());

            for (ConditionAndOutcome item : entry.getValue()) {
                String conditionName =
                        item.getCondition().getClass().getSimpleName();
                boolean matched = item.getOutcome().isMatch();

                System.out.println(
                        "  " + conditionName + " -> "
                                + (matched ? "MATCH" : "NO MATCH")
                );
            }
        }
    }
}
```

Đặt file tại `src/main/java/demo/ConditionReportReader.java` sau khi thêm `package demo;` phù hợp. Đây là **lớp tiện ích đọc report**, không tự khởi động ứng dụng. Gọi `ConditionReportReader.print(context)` sau khi context được tạo nếu ứng dụng có quyền truy cập context.

### Vì sao dùng `find()` thay vì `get()`?

- `ConditionEvaluationReport.find(beanFactory)` cố tìm report đã tồn tại và có thể trả `null` nếu chưa có.
- `ConditionEvaluationReport.get(beanFactory)` lấy report hiện tại hoặc tạo một report mới nếu chưa có.

Khi chỉ muốn **đọc dữ liệu chẩn đoán**, `find()` giúp tránh tạo một report rỗng rồi nhầm nó với báo cáo đã ghi nhận các condition.

### Các API quan trọng

| API | Kết quả |
|---|---|
| `getConditionAndOutcomesBySource()` | Map source → các kết quả condition |
| `ConditionAndOutcomes.isFullMatch()` | `true` khi tất cả outcome của source đều match |
| `ConditionAndOutcome.getCondition()` | Condition đã được đánh giá |
| `ConditionAndOutcome.getOutcome().isMatch()` | Condition đó match hay không |
| `getExclusions()` | Danh sách class bị exclude |
| `getUnconditionalClasses()` | Tập class không có condition áp dụng |
| `getParent()` | Report của parent BeanFactory nếu có |

Khi ứng dụng dùng nhiều context (ví dụ management context riêng), report có thể khác nhau theo từng BeanFactory. Đừng gộp dữ liệu của parent và child rồi kết luận nhầm source thuộc context nào.

## 8. Bật report trong log khi khởi động

Cách nhanh nhất khi debug ứng dụng Spring Boot là chạy với tham số:

```bash
java -jar application.jar --debug
```

`--debug` bật debug logging cho một số logger cốt lõi và đưa Condition Evaluation Report ra console. Nó không bật debug cho mọi package của ứng dụng.

Nếu muốn ghi report ở log level cụ thể bằng initializer, Spring Boot 3.3 có `ConditionEvaluationReportLoggingListener`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

public class ApplicationLauncher {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addInitializers(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        );

        application.run(args);
    }
}
```

Đây là một launcher thay thế cho phương thức `main` hiện tại của ứng dụng. Listener mặc định ghi report ở DEBUG; `forLogLevel(LogLevel.INFO)` cho phép chọn log level khác. Javadoc lưu ý **không dùng chung một listener instance cho nhiều application context**; tạo initializer phù hợp cho từng context.

Log có thể dài vì một ứng dụng lớn có nhiều auto-configuration và condition lồng nhau. Hãy tìm theo FQCN hoặc tên method liên quan trước, sau đó đọc đầy đủ nhóm condition của source đó.

## 9. Dùng Actuator `/actuator/conditions`

Nếu ứng dụng đã dùng Spring Boot Actuator, có thể xem report qua HTTP:

```properties
management.endpoints.web.exposure.include=health,conditions
```

Thêm dependency `spring-boot-starter-actuator` nếu dự án chưa có, sau đó gọi:

```bash
curl http://localhost:8080/actuator/conditions
```

Đường dẫn mặc định là `/actuator/conditions`; nếu ứng dụng thay đổi `management.endpoints.web.base-path` thì URL sẽ thay đổi tương ứng.

Response JSON có cấu trúc chính:

| Trường | Nội dung |
|---|---|
| `contexts` | Các application context, định danh theo context id |
| `positiveMatches` | Class/method có condition match |
| `negativeMatches` | Class/method có ít nhất một condition không match |
| `negativeMatches.*.notMatched` | Condition không đạt và thông điệp lý do |
| `negativeMatches.*.matched` | Condition khác đã đạt trong source negative |
| `unconditionalClasses` | Các auto-configuration class không có condition áp dụng |
| `parentId` | ID parent context nếu có |

Ví dụ thực tế từ tài liệu Spring Boot 3.3 có các condition như `OnBeanCondition`, `OnClassCondition` và `OnWebApplicationCondition` cùng thông điệp giải thích. Một negative match có thể chỉ rõ “not a reactive web application” hoặc thiếu class cần thiết; những thông tin đó giúp chọn đúng property, dependency hay application type để kiểm tra.

**Actuator cần được bảo vệ.** Endpoint conditions có thể tiết lộ tên class, bean và chi tiết cấu hình nội bộ. Chỉ expose khi cần, giới hạn mạng và quyền truy cập bằng security policy phù hợp; không mở rộng toàn bộ endpoint bằng `management.endpoints.web.exposure.include=*` chỉ để debug.

## 10. Ví dụ kiểm thử report với `ApplicationContextRunner` (Spring Boot 3.3 / Java 17+)

`ApplicationContextRunner` tạo context nhỏ, có thể kiểm soát property và user bean theo từng test. Đây là cách tốt để xác nhận condition report thay đổi như mong muốn mà không phải khởi động toàn bộ ứng dụng.

Đặt file `src/test/java/demo/ConditionEvaluationReportTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConditionEvaluationReportTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ReportedAutoConfiguration.class,
                            UnconditionalReportAutoConfiguration.class
                    ));

    private ConditionEvaluationReport report(
            AssertableApplicationContext context) {
        return ConditionEvaluationReport.get(
                context.getSourceApplicationContext().getBeanFactory()
        );
    }

    @Test
    void positiveMatchAppearsWhenEveryConditionPasses() {
        runner.withUserConfiguration(GatewayConfiguration.class)
                .withPropertyValues("demo.report.enabled=true")
                .run(context -> {
                    assertTrue(context.containsBean("reportFeature"));

                    ConditionEvaluationReport report = report(context);
                    String source = ReportedAutoConfiguration.class.getName()
                            + "#reportFeature";

                    ConditionAndOutcomes outcomes =
                            report.getConditionAndOutcomesBySource().get(source);

                    assertNotNull(outcomes);
                    assertTrue(outcomes.isFullMatch());
                });
    }

    @Test
    void negativeMatchAppearsWhenRequiredBeanIsMissing() {
        runner.withPropertyValues("demo.report.enabled=true")
                .run(context -> {
                    assertFalse(context.containsBean("reportFeature"));

                    ConditionEvaluationReport report = report(context);
                    String source = ReportedAutoConfiguration.class.getName()
                            + "#reportFeature";

                    ConditionAndOutcomes outcomes =
                            report.getConditionAndOutcomesBySource().get(source);

                    assertNotNull(outcomes);
                    assertFalse(outcomes.isFullMatch());
                });
    }

    @Test
    void unconditionalAutoConfigurationIsListedSeparately() {
        runner.run(context -> {
            ConditionEvaluationReport report = report(context);

            assertTrue(report.getUnconditionalClasses().contains(
                    UnconditionalReportAutoConfiguration.class.getName()
            ));
            assertTrue(context.containsBean("unconditionalMarker"));
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class GatewayConfiguration {
        @Bean
        ReportGateway reportGateway() {
            return new ReportGateway() {
            };
        }
    }
}

@AutoConfiguration
class ReportedAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "enabled",
            havingValue = "true"
    )
    @ConditionalOnBean(ReportGateway.class)
    ReportFeature reportFeature() {
        return new ReportFeature();
    }
}

@AutoConfiguration
class UnconditionalReportAutoConfiguration {

    @Bean
    String unconditionalMarker() {
        return "available";
    }
}

interface ReportGateway {
}

final class ReportFeature {
}
```

Lớp `ReportedAutoConfiguration` có hai điều kiện: cờ property phải true và bean `ReportGateway` phải có mặt. Test thứ nhất tạo gateway nên source là positive match; test thứ hai chỉ đặt property nên source là negative match. Test thứ ba xác nhận auto-configuration không có condition ở cấp class được liệt kê trong unconditional classes.

### Kiểm tra exclusions trong một ứng dụng thật

Đối với exclusion, kiểm tra trực tiếp API report sau khi ứng dụng được cấu hình loại trừ:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.find(applicationContext.getBeanFactory());

if (report != null) {
    report.getExclusions().forEach(System.out::println);
}
```

Đoạn này là **mẫu kiểm tra sau startup**, giả định `applicationContext` là `ConfigurableApplicationContext` đã được tạo bằng `SpringApplication` và cấu hình loại trừ đã được áp dụng. Danh sách sẽ chứa tên auto-configuration đã exclude, ví dụ tên được khai báo trong `excludeName` hoặc `spring.autoconfigure.exclude`. Không tìm một exclusion trong `negativeMatches`.

### Dependency và lệnh chạy

Với dự án Gradle đã cấu hình Spring Boot 3.3.x và Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy:

```bash
./gradlew test --tests demo.ConditionEvaluationReportTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.ConditionEvaluationReportTest
```

**Kết quả kỳ vọng:** 3 test pass. Đây là kết quả dự kiến từ cấu trúc test, chưa phải log chạy thực tế; hãy chạy trên project với dependency/version cụ thể để xác nhận.

## 11. Các lỗi đọc report thường gặp

1. **Xem negative match như lỗi startup.** Một cấu hình không match có thể là hành vi mong muốn vì ứng dụng đang chạy non-web, thiếu starter tùy chọn hoặc đã cung cấp bean thay thế.
2. **Tìm class bị exclude trong negative matches.** Excluded class không được condition evaluation; đọc `getExclusions()`.
3. **Tưởng unconditional class luôn tạo mọi bean.** Danh sách chỉ nói class không có condition áp dụng; bean method vẫn có thể có condition riêng.
4. **Chỉ nhìn tên condition mà bỏ message.** `OnBeanCondition` có thể báo tìm thấy hoặc không tìm thấy bean nào; message mới cho biết kiểu bean, tên bean hoặc search strategy.
5. **Nhìn một matched condition rồi kết luận source match.** Với nhiều điều kiện, một condition pass không bù được condition khác fail.
6. **Đọc sai source.** Điều kiện có thể gắn ở class hoặc bean method. Một class positive không có nghĩa mọi method trong class đều positive.
7. **Quên context hierarchy.** Parent và child context có report riêng; dùng `getParent()` nếu cần điều tra context cha.
8. **Không thấy exclusion trong Actuator JSON rồi kết luận không có exclusion.** JSON schema conditions không liệt kê exclusions; đọc raw report API hoặc startup report.
9. **Sửa code nhưng không tạo context mới.** Report phản ánh lần condition evaluation trong lần khởi tạo context đó; đổi property sau startup không tự đánh giá lại toàn bộ auto-configuration.
10. **Expose Actuator conditions công khai để debug nhanh.** Endpoint có thể tiết lộ cấu trúc ứng dụng; bảo vệ quyền truy cập và chỉ expose khi thực sự cần.

## 12. Quy trình chẩn đoán nhanh

Khi một bean tự động không xuất hiện:

1. Tìm tên bean method hoặc auto-configuration trong `negativeMatches`.
2. Đọc `notMatched` để tìm điều kiện thất bại đầu tiên có ý nghĩa.
3. Nếu source không xuất hiện trong positive/negative, kiểm tra `exclusions` và `unconditionalClasses`; cũng xác nhận candidate có thực sự được import hay không.
4. Với `OnClassCondition`, kiểm tra runtime classpath và phiên bản dependency.
5. Với `OnPropertyCondition`, kiểm tra tên property, giá trị cuối cùng và profile/property source override.
6. Với `OnBeanCondition`, kiểm tra bean definition, kiểu trả về của `@Bean` và thứ tự đăng ký auto-configuration.
7. Với `OnWebApplicationCondition`, kiểm tra web application type thật của context.
8. Sau khi sửa, tạo context mới hoặc chạy `ApplicationContextRunner` với tình huống tương ứng; xác nhận cả bean thực tế và outcome mới.

Khi bean xuất hiện ngoài dự kiến:

- Tìm source tương ứng trong `positiveMatches`.
- Đọc từng message để biết condition nào đã match.
- Kiểm tra giá trị property cuối cùng, classpath, bean thay thế và application type.
- Nếu source unconditional, xác định nó có phải auto-configuration luôn áp dụng theo thiết kế hay không; xem condition ở bean method.
- Kiểm tra exclusion đã được đặt đúng trên application configuration hay property source chưa.

## 13. Ghi nhớ

- **Positive match:** tất cả condition của source đều match.
- **Negative match:** ít nhất một condition không match; đọc `notMatched` để biết lý do.
- **Exclusion:** candidate bị loại trước condition evaluation; đọc `ConditionEvaluationReport.getExclusions()`.
- **Unconditional class:** class được đánh giá nhưng không có condition áp dụng ở cấp class; bean method vẫn có thể có condition.
- **ConditionEvaluationReport:** API Java để đọc source/outcomes, exclusions, unconditional classes và parent report.
- **`--debug` / ConditionEvaluationReportLoggingListener:** cách đọc report qua log.
- **Actuator `/actuator/conditions`:** cách xem positive/negative matches và unconditional classes qua JSON; cần expose và bảo vệ endpoint phù hợp.

### Tài liệu chính thức

- Spring Boot 3.3 Javadoc — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 Javadoc — `ConditionEvaluationReport.ConditionAndOutcome`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcome.html
- Spring Boot 3.3 Javadoc — `ConditionEvaluationReportLoggingListener`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Spring Boot 3.3 Actuator API — Conditions Evaluation Report: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 Reference — Testing Auto-configuration with `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
