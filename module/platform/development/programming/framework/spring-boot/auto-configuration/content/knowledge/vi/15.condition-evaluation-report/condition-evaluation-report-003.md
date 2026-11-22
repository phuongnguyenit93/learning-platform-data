# Xác định điều kiện ở lớp ngoài và phương thức @Bean trong báo cáo

> **Mục tiêu:** Khi một bean không xuất hiện sau khi Spring Boot khởi động, xác định chính xác điều kiện nào đã chặn nó và điều kiện đó nằm ở **lớp cấu hình ngoài** hay **phương thức `@Bean`**. `ConditionEvaluationReport` của Spring Boot ghi lại kết quả điều kiện theo nguồn (class hoặc method), cho phép đối chiếu cấu hình tổng thể với từng bean riêng lẻ.

Bài học thuộc nhóm **Báo cáo điều kiện** trong Spring Boot Auto Configuration, dùng Spring Boot 3.3.x và Java 17+. Trọng tâm gồm cấu trúc report, cách đọc key `ClassName` và `ClassName#beanMethod`, quan hệ giữa điều kiện cấp lớp và cấp method, endpoint Actuator, log lúc khởi động và kiểm thử bằng `ApplicationContextRunner`.

## 1. Vì sao phải phân biệt hai cấp điều kiện?

Một auto-configuration có thể cung cấp nhiều bean:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.report",
        name = "enabled",
        havingValue = "true")
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService() {
        return new ReportService("default");
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "metrics-enabled",
            havingValue = "true")
    ReportMetrics reportMetrics() {
        return new ReportMetrics("default");
    }
}
~~~

Đoạn code thể hiện hai tầng:

- **Cấp lớp:** `demo.report.enabled` phải bằng `true` thì `ReportAutoConfiguration` mới được áp dụng.
- **Cấp phương thức:** `reportService()` chỉ đăng ký default nếu chưa có bean `ReportService` phù hợp; `reportMetrics()` chỉ đăng ký nếu `demo.report.metrics-enabled=true`.

Giả sử ứng dụng bật report nhưng tắt metrics:

- Điều kiện của lớp khớp.
- Điều kiện của `reportService()` có thể khớp nếu chưa có bean riêng.
- Điều kiện của `reportMetrics()` không khớp.
- Kết quả là service có mặt, metrics không có.

Nếu `demo.report.enabled=false`, điều kiện ở cấp lớp không khớp. Khi đó các phương thức `@Bean` bên trong không được xét để đăng ký bean theo cấu hình này. Đây là khác biệt cốt lõi: **điều kiện cấp lớp giới hạn toàn bộ cấu hình; điều kiện cấp method giới hạn một bean cụ thể**.

Đặt nhiều điều kiện trên cùng một class hoặc method có nghĩa là tất cả các điều kiện gắn ở vị trí đó phải thỏa. Điều kiện method còn phải nằm trong một class cấu hình đã qua điều kiện cấp lớp.

## 2. ConditionEvaluationReport là gì?

`ConditionEvaluationReport` là đối tượng của Spring Boot dùng để lưu kết quả đánh giá các condition phục vụ log và báo cáo. Nó nhóm kết quả theo **source** — nguồn khai báo condition:

- Tên class cấu hình, ví dụ `com.example.ReportAutoConfiguration`.
- Tên method bean theo dạng `com.example.ReportAutoConfiguration#reportService`.

Một source có thể có nhiều condition cùng lúc. Ví dụ, class có cả `@ConditionalOnClass` và `@ConditionalOnProperty` thì report ghi các kết quả của hai condition dưới source class đó. Method có `@ConditionalOnMissingBean` và `@ConditionalOnProperty` cũng có thể có nhiều kết quả dưới source method tương ứng.

Một report điển hình có các khái niệm:

| Thành phần | Ý nghĩa | Cách dùng khi điều tra |
| --- | --- | --- |
| `positiveMatches` | Các source mà toàn bộ condition được ghi nhận đều khớp | Xác nhận lớp hoặc method đã vượt qua các cổng điều kiện |
| `negativeMatches` | Các source có ít nhất một condition không khớp | Tìm điều kiện đã chặn cấu hình hoặc bean |
| `notMatched` | Những condition không khớp trong một source âm tính | Đọc nguyên nhân trực tiếp |
| `matched` | Những condition khác trong cùng source vẫn khớp | Biết điều kiện nào đã đạt trước khi có điều kiện thất bại |
| `unconditionalClasses` | Các lớp được đánh giá nhưng không có điều kiện | Phân biệt cấu hình không điều kiện với cấu hình có điều kiện |
| `exclusions` | Các auto-configuration đã bị loại trừ | Điều tra trường hợp cấu hình bị exclude thay vì condition không khớp |

`positiveMatches` và `negativeMatches` là phân loại theo **source**, không phải danh sách instance bean đã được tạo thành công. Condition khớp có nghĩa cấu hình/bean definition đủ điều kiện được đăng ký theo nhánh đó; việc khởi tạo object sau đó vẫn có thể thất bại vì dependency, constructor hoặc lỗi runtime.

## 3. Đọc tên source để xác định đúng vị trí

Hãy nhìn vào key trước khi đọc message:

~~~text
com.example.ReportAutoConfiguration
com.example.ReportAutoConfiguration#reportService
com.example.ReportAutoConfiguration#reportMetrics
~~~

- Key không có dấu `#` là source ở **cấp class**.
- Key có `#methodName` là source ở **cấp phương thức `@Bean`**.
- Phần sau dấu `#` là tên method Java, không nhất thiết là tên bean nếu method có khai báo tên bean tùy chỉnh bằng `@Bean("...")`.
- Class name có thể là tên đầy đủ package; nếu cấu hình là nested class, tên nhị phân có thể chứa dấu `$`.

Ví dụ `@Bean(name = "mainReportService")` trên method `reportService()` vẫn có source report theo tên method `#reportService`, không phải `#mainReportService`. Khi cần ánh xạ source sang bean name, xem method Java và khai báo `@Bean` tương ứng.

### Quy tắc đọc nhanh

1. Tìm source class `ReportAutoConfiguration`.
2. Nếu source class ở `negativeMatches`, đọc `notMatched` trước: điều kiện cấp lớp nào đang chặn toàn bộ cấu hình?
3. Nếu source class ở `positiveMatches`, chuyển sang các source `#methodName`.
4. Tìm method bean đang thiếu; đọc `notMatched` của method đó.
5. Nếu class và method đều positive nhưng bean không dùng được, chuyển sang điều tra bean definition, dependency injection và lỗi khởi tạo object.

Không kết luận “bean bị tắt bởi method” chỉ từ việc không thấy key method. Nếu class-level condition không khớp, các method bên trong có thể chưa được xét và do đó không có entry riêng.

## 4. Cấu trúc report trên Actuator

Nếu ứng dụng có `spring-boot-starter-actuator`, endpoint `conditions` có thể hiển thị report dưới dạng JSON. Trong môi trường chẩn đoán được bảo vệ, cấu hình exposure ví dụ:

~~~properties
management.endpoints.web.exposure.include=health,conditions
~~~

Sau đó gửi request:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

Endpoint này không tự động được mở công khai chỉ vì thêm Actuator. Cần cấu hình exposure phù hợp và bảo vệ bằng authentication/network policy; không phơi bày thông tin cấu hình nội bộ ra internet.

### Ví dụ JSON rút gọn

Giả sử `ReportAutoConfiguration` đã khớp, `reportService()` có thể tạo default, nhưng `reportMetrics()` bị chặn vì property chưa bật. Cấu trúc rút gọn có thể trông như sau:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.example.ReportAutoConfiguration": [
          {
            "condition": "OnPropertyCondition",
            "message": "@ConditionalOnProperty (demo.report.enabled) matched"
          }
        ],
        "com.example.ReportAutoConfiguration#reportService": [
          {
            "condition": "OnBeanCondition",
            "message": "@ConditionalOnMissingBean did not find any beans"
          }
        ]
      },
      "negativeMatches": {
        "com.example.ReportAutoConfiguration#reportMetrics": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "@ConditionalOnProperty (demo.report.metrics-enabled) did not match"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": []
    }
  }
}
~~~

Đây là JSON minh họa cách nhóm source và condition, không phải bản chép nguyên văn output của một ứng dụng cụ thể. Message thật phụ thuộc annotation, property, bean registry và phiên bản Boot.

Cách đọc ví dụ:

- Source class nằm trong `positiveMatches`: điều kiện ngoài đã khớp.
- `#reportService` cũng nằm trong `positiveMatches`: điều kiện thiếu bean cho service đã khớp.
- `#reportMetrics` nằm trong `negativeMatches`: metrics bị chặn ở method.
- `notMatched` cho biết condition property cụ thể không đạt; `matched` rỗng vì ví dụ này chỉ có một condition tại method đó.

Nếu có nhiều annotation condition trên cùng source, `negativeMatches` có thể có cả `matched` lẫn `notMatched`. Ví dụ một method có `@ConditionalOnClass` khớp nhưng `@ConditionalOnProperty` không khớp; report cho biết cả hai thay vì chỉ nói chung chung “method không được tạo”.

## 5. Khi điều kiện cấp lớp không khớp

Giả sử:

~~~properties
demo.report.enabled=false
demo.report.metrics-enabled=true
~~~

Kết quả:

1. `ReportAutoConfiguration` bị condition cấp lớp chặn.
2. `reportService()` và `reportMetrics()` không được đăng ký qua auto-configuration này.
3. Report ghi source class trong `negativeMatches` với condition property không khớp.
4. Không nên mong đợi report có hai source method riêng cho các method chưa được xét.

Điều kiện cấp lớp thường phù hợp với yêu cầu chung cho toàn nhóm: thư viện bắt buộc có trên classpath, ứng dụng phải là Servlet web application, hoặc một property tắt toàn bộ integration. Nó không phù hợp nếu chỉ muốn tắt riêng một bean mà vẫn cần các bean khác trong cùng class.

Một nuance: condition cấp lớp không có nghĩa Spring bỏ qua mọi thao tác đọc metadata của class. Theo tài liệu Boot, khác biệt quan trọng giữa điều kiện class-level và method-level là điều kiện class-level còn quyết định việc đăng ký chính class cấu hình như một bean; đồng thời các method trong class không được dùng để đóng góp bean khi class không qua điều kiện.

## 6. Khi class khớp nhưng method không khớp

Đây là trường hợp phổ biến khi một auto-configuration cung cấp nhiều bean độc lập.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.report",
        name = "enabled",
        havingValue = "true")
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService() {
        return new ReportService("default");
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "metrics-enabled",
            havingValue = "true")
    ReportMetrics reportMetrics() {
        return new ReportMetrics("default");
    }
}
~~~

Với:

~~~properties
demo.report.enabled=true
demo.report.metrics-enabled=false
~~~

Report có thể cho thấy class positive, method `reportService` positive, method `reportMetrics` negative. Đây là bằng chứng rằng cấu hình ngoài vẫn hoạt động; chỉ bean metrics bị điều kiện riêng của nó chặn.

Nếu `reportService` bị đưa vào `negativeMatches` vì `@ConditionalOnMissingBean` tìm thấy bean cùng kiểu, đó có thể là **back-off có chủ đích**: người dùng đã cung cấp implementation riêng. Khi đó kiểm tra bean thực tế để xác nhận custom bean được đăng ký, không cần ép default xuất hiện.

## 7. Dùng ConditionEvaluationReport trực tiếp trong Java

Ngoài Actuator, Spring Boot cung cấp API `ConditionEvaluationReport` để truy cập report từ bean factory. Đoạn sau là một **method minh họa** có thể đặt trong test hoặc code chẩn đoán nhận được `ConfigurableApplicationContext` đang mở:

~~~java
import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.context.ConfigurableApplicationContext;

static void printConditionSources(ConfigurableApplicationContext context) {
    ConditionEvaluationReport report =
            ConditionEvaluationReport.get(context.getBeanFactory());

    Map<String, ConditionAndOutcomes> bySource =
            report.getConditionAndOutcomesBySource();

    bySource.forEach((source, outcomes) -> {
        System.out.println(
                source + " (allMatched=" + outcomes.isFullMatch() + ")");
        for (ConditionAndOutcome outcome : outcomes) {
            System.out.println("  " + outcome);
        }
    });

    System.out.println("Excluded: " + report.getExclusions());
    System.out.println("Unconditional: " + report.getUnconditionalClasses());
}
~~~

Method này in từng source, trạng thái tất cả condition trong source có khớp không, từng cặp condition/outcome, danh sách exclusion và các class unconditional. Nó không phải chương trình Java độc lập: phải được gọi với context đang hoạt động và đã chạy qua giai đoạn đánh giá auto-configuration. Không gọi sau khi context đã đóng vì bean factory không còn khả dụng.

Một số method quan trọng:

| API | Trả về | Cách sử dụng |
| --- | --- | --- |
| `ConditionEvaluationReport.get(beanFactory)` | Report gắn với bean factory | Lấy report của context |
| `getConditionAndOutcomesBySource()` | Map source → các condition/outcome | Tìm class và method |
| `ConditionAndOutcomes.isFullMatch()` | Boolean | Kiểm tra tất cả condition tại source có khớp |
| `ConditionAndOutcome.getCondition()` | Condition | Xác định loại condition |
| `ConditionAndOutcome.getOutcome()` | ConditionOutcome | Đọc kết quả condition |
| `getExclusions()` | Danh sách class bị exclude | Điều tra cấu hình bị loại trừ |
| `getUnconditionalClasses()` | Tập class không có điều kiện | Phân biệt với conditional sources |

API này hữu ích cho kiểm thử và tooling nội bộ. Với vận hành thông thường, log startup hoặc Actuator thường đủ; tránh viết một endpoint debug riêng nếu endpoint chính thức đã đáp ứng nhu cầu.

## 8. Bật report trong log khi khởi động

Cách nhanh nhất để xem Condition Evaluation Report trong ứng dụng thực tế là chạy với:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot sẽ đưa thông tin điều kiện vào log startup, thường dưới tiêu đề `CONDITIONS EVALUATION REPORT`. Đọc các nhóm positive và negative match, rồi tìm class hoặc method liên quan.

Trong test, có thể dùng `ConditionEvaluationReportLoggingListener` để in report ở mức log mong muốn:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ConditionReportLoggingTest {

    @Test
    void printsConditionReport() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ReportAutoConfiguration.class))
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO))
                .withPropertyValues("demo.report.enabled=true")
                .run(context -> {
                    // Đặt assertion cho bean ở đây.
                });
    }
}
~~~

Ví dụ giả định `ReportAutoConfiguration` đã được khai báo trong test hoặc source set đang kiểm thử. Listener là `ApplicationContextInitializer` ghi report ra log. Theo API Boot, report mặc định được ghi ở DEBUG; `forLogLevel` cho phép chọn mức log. Không dùng cùng một instance listener để chia sẻ cho nhiều context khác nhau.

Nếu ứng dụng thất bại trong quá trình khởi động, report trong log có thể là manh mối hữu ích ngay cả khi HTTP server chưa chạy. Endpoint Actuator `/actuator/conditions` chỉ có thể được gọi khi ứng dụng/context đã khởi động đủ để phục vụ endpoint.

## 9. Kiểm thử: xác nhận class-level và method-level xuất hiện riêng

Ví dụ dưới đây là **một tệp test Java hoàn chỉnh** cho Java 17+, Spring Boot 3.3.x, JUnit Jupiter và AssertJ. Nó kiểm tra bốn trạng thái:

1. Class và cả hai method đều khớp.
2. Condition cấp class thất bại, các method không được xét.
3. Class khớp nhưng property condition của một method thất bại.
4. User cung cấp bean riêng, khiến condition `@ConditionalOnMissingBean` tại một method không khớp trong khi method còn lại vẫn hoạt động.

**Tệp:** `src/test/java/example/report/ConditionSourceReportTest.java`

~~~java
package example.report;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionSourceReportTest {

    record ReportService(String source) {}
    record ReportMetrics(String source) {}

    @AutoConfiguration
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "enabled",
            havingValue = "true")
    static class ReportAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportService.class)
        ReportService reportService() {
            return new ReportService("default");
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.report",
                name = "metrics-enabled",
                havingValue = "true")
        ReportMetrics reportMetrics() {
            return new ReportMetrics("default");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserReportConfiguration {

        @Bean
        ReportService customReportService() {
            return new ReportService("user");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(ReportAutoConfiguration.class));

    private static ConditionEvaluationReport report(
            AssertableApplicationContext context) {
        return ConditionEvaluationReport.get(
                context.getSourceApplicationContext().getBeanFactory());
    }

    private static ConditionAndOutcomes source(
            AssertableApplicationContext context, String suffix) {
        return report(context).getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().endsWith(suffix))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElseThrow(() ->
                        new AssertionError("Missing report source: " + suffix));
    }

    @Test
    void classAndBothBeanMethodsMatch() {
        runner.withPropertyValues(
                "demo.report.enabled=true",
                "demo.report.metrics-enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context).hasSingleBean(ReportMetrics.class);

                    assertThat(source(context, "ReportAutoConfiguration")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportService")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportMetrics")
                            .isFullMatch()).isTrue();
                });
    }

    @Test
    void classLevelFailurePreventsMethodConditionsFromBeingReached() {
        runner.withPropertyValues(
                "demo.report.enabled=false",
                "demo.report.metrics-enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("reportService");
                    assertThat(context).doesNotHaveBean("reportMetrics");

                    assertThat(source(context, "ReportAutoConfiguration")
                            .isFullMatch()).isFalse();

                    var keys = report(context)
                            .getConditionAndOutcomesBySource().keySet();
                    assertThat(keys)
                            .noneMatch(key -> key.endsWith("#reportService")
                                    || key.endsWith("#reportMetrics"));
                });
    }

    @Test
    void methodLevelFailureOnlyBlocksThatBean() {
        runner.withPropertyValues(
                "demo.report.enabled=true",
                "demo.report.metrics-enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context).doesNotHaveBean("reportMetrics");

                    assertThat(source(context, "ReportAutoConfiguration")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportService")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportMetrics")
                            .isFullMatch()).isFalse();
                });
    }

    @Test
    void userBeanMakesMethodLevelMissingBeanConditionFail() {
        runner.withPropertyValues(
                "demo.report.enabled=true",
                "demo.report.metrics-enabled=true")
                .withUserConfiguration(UserReportConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context).hasBean("customReportService");
                    assertThat(context).doesNotHaveBean("reportService");
                    assertThat(context).hasSingleBean(ReportMetrics.class);
                    assertThat(context.getBean(ReportService.class).source())
                            .isEqualTo("user");

                    assertThat(source(context, "ReportAutoConfiguration")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportService")
                            .isFullMatch()).isFalse();
                    assertThat(source(context, "#reportMetrics")
                            .isFullMatch()).isTrue();
                });
    }
}
~~~

**Cách chạy** trong dự án Maven hoặc Gradle có Spring Boot 3.3 và `spring-boot-starter-test`:

~~~bash
mvn -Dtest=ConditionSourceReportTest test
# Hoặc với Gradle wrapper trên Linux/macOS:
./gradlew test --tests example.report.ConditionSourceReportTest
~~~

**Kết quả mong đợi:** **4 test PASS**, không có stdout cố định vì test chỉ dùng assertion. Các assertion trên `ConditionEvaluationReport` chứng minh:

- Source class có entry độc lập với source method.
- Khi class-level condition thất bại, không có entry riêng cho hai method.
- Khi một method-level condition thất bại, method còn lại vẫn có thể khớp.
- Khi người dùng khai báo `ReportService`, source `#reportService` ghi nhận điều kiện thiếu bean không khớp, còn `#reportMetrics` vẫn khớp.

Các lớp auto-configuration lồng nhau trong ví dụ là để test nạp trực tiếp bằng `AutoConfigurations.of(...)`. Trong thư viện thật, nên dùng class top-level và đăng ký qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; không cần đưa class test vào file imports của starter.

## 10. Phân biệt report điều kiện với các dấu hiệu khác

| Dấu hiệu quan sát | Có thể kết luận | Cần kiểm tra tiếp |
| --- | --- | --- |
| Class source trong `negativeMatches` | Có condition cấp lớp không khớp | Message trong `notMatched` và giá trị Environment thực tế |
| Class positive, method source negative | Cấu hình ngoài đã qua; bean method bị chặn | Annotation trên method, type/name bean, property |
| Class positive, method positive, nhưng bean không dùng được | Condition đã khớp | Bean definition, dependency injection, exception khi tạo object |
| Không tìm thấy source class trong report | Chưa đủ bằng chứng để kết luận condition sai | AutoConfiguration imports, exclusion, classpath, package scanning và context đang xem |
| Class xuất hiện trong `exclusions` | Auto-configuration bị loại trừ khỏi quá trình áp dụng | `spring.autoconfigure.exclude` hoặc thuộc tính exclude của ứng dụng |
| Có bean nhưng không thấy method condition mong đợi | Có thể bean đến từ nguồn khác hoặc không đi qua method đó | `/actuator/beans`, bean name, bean definition resource |

Một lỗi hay gặp là thấy bean không tồn tại rồi kết luận condition method đã không khớp. Bean có thể không được đăng ký từ một cấu hình khác, auto-configuration có thể bị exclude, class có thể không được import, hoặc ứng dụng đang xem nhầm child/parent context. Hãy xác định đúng context và nguồn khai báo trước khi sửa annotation.

`ConditionEvaluationReport` tập trung vào hệ condition của Spring Boot. Những condition tùy chỉnh của Spring Framework (ví dụ `@Profile`) không nhất thiết xuất hiện với cùng loại message như `@ConditionalOnProperty` hoặc `@ConditionalOnBean`. Nếu cấu hình phụ thuộc profile, kiểm tra active/default profile bằng `Environment` song song với report.

Ngoài ra, report là kết quả đánh giá trong quá trình xây dựng context, không phải màn hình theo dõi liên tục. Thay đổi property sau khi ứng dụng đã khởi động không tự làm condition đánh giá lại và không tự đăng ký bean mới.

## 11. Quy trình điều tra theo đúng thứ tự

Khi một bean được mong đợi nhưng không xuất hiện, dùng quy trình sau:

1. **Xác định context:** ứng dụng có nhiều context cha/con không? Endpoint report hiển thị context id nào?
2. **Tìm source class:** class auto-configuration có nằm trong `positiveMatches`, `negativeMatches`, `unconditionalClasses` hoặc `exclusions`?
3. **Nếu class negative:** đọc condition không khớp đầu tiên và kiểm tra dữ liệu tương ứng — classpath, property, profile, application type hoặc bean definition.
4. **Nếu class positive:** tìm source `#beanMethod` đúng với method Java.
5. **Đọc toàn bộ condition ở method:** `notMatched` là nguyên nhân chặn; `matched` là điều kiện đã đạt. Nếu `@ConditionalOnMissingBean` không khớp, kiểm tra bean nào đang tồn tại và type nào được so sánh.
6. **Nếu method positive nhưng ứng dụng vẫn lỗi:** xem startup exception, dependency và quá trình tạo object; condition report không đảm bảo bean instance đã được khởi tạo thành công.
7. **Viết test tái hiện:** dùng `ApplicationContextRunner`, chỉ thay một biến mỗi lần (property, user bean hoặc classpath) để xác nhận đúng source thay đổi.

Cách làm này tránh sửa nhầm annotation cấp lớp trong khi vấn đề thực tế nằm ở một method, hoặc xóa cả auto-configuration khi chỉ cần sửa property của một bean.

## 12. Lưu ý khi thiết kế condition để report dễ đọc

- **Đặt điều kiện chung ở class:** ví dụ dependency bắt buộc cho toàn integration hoặc một cờ bật/tắt toàn nhóm.
- **Đặt điều kiện riêng ở method:** ví dụ `@ConditionalOnMissingBean` cho từng default hoặc property chỉ áp dụng cho một bean.
- **Dùng kiểu trả về cụ thể cho `@Bean`:** bean conditions dựa vào type information có trong method signature khi đánh giá.
- **Không phụ thuộc vào bean xuất hiện sau:** `@ConditionalOnBean` và `@ConditionalOnMissingBean` chỉ quan sát các bean definition đã xử lý tại thời điểm condition chạy; sắp thứ tự auto-configuration khi có quan hệ provider/consumer.
- **Tách optional dependency vào nested configuration:** đặc biệt khi `@ConditionalOnClass` kiểm tra một class có thể không có trên classpath; không để kiểu trả về method buộc JVM nạp class tùy chọn trước khi condition có cơ hội bảo vệ.
- **Đặt tên method rõ nghĩa:** source report dùng method name, nên tên `client` hoặc `configuration` quá chung làm khó đọc log. Ưu tiên `defaultReportService`, `reportMetrics` hoặc tên phản ánh đúng bean.
- **Giữ message condition cụ thể:** custom `Condition` nên trả về message nói rõ property/type/resource nào được tìm thấy hoặc thiếu. Nếu tự viết condition cho Boot, cân nhắc kế thừa `SpringBootCondition` để tích hợp cơ chế outcome/logging của Boot.

## 13. Câu hỏi tự kiểm tra

1. Report có key `com.example.ReportAutoConfiguration#reportMetrics` trong `negativeMatches` nhưng class source positive. Điều gì bị chặn? **Chỉ bean method `reportMetrics`**; cấu hình ngoài vẫn qua điều kiện.
2. Class source nằm trong `negativeMatches` và không có key `#reportService`. Có thể kết luận method condition sai không? **Không.** Method có thể chưa được đánh giá vì class-level condition đã chặn cấu hình.
3. `reportService` có key positive nhưng ứng dụng vẫn lỗi `UnsatisfiedDependencyException`. Điều đó có mâu thuẫn không? **Không.** Condition match cho phép đăng ký definition; dependency hoặc quá trình tạo object vẫn có thể thất bại.
4. Vì sao key có dấu `#` quan trọng? Nó phân biệt outcome của bean method với outcome của cấu hình class, giúp định vị phạm vi condition.
5. Muốn tìm auto-configuration bị exclude ở đâu? Xem `exclusions` trong report và cấu hình `spring.autoconfigure.exclude` hoặc thuộc tính exclude của `@SpringBootApplication`.
6. Vì sao test dùng `ApplicationContextRunner`? Nó tạo context nhỏ với property/user bean/classpath xác định, giúp so sánh report source qua từng trường hợp.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition ở class/method, thứ tự áp dụng, `ApplicationContextRunner` và kiểm thử auto-configuration.
- [Spring Boot 3.3 API — ConditionEvaluationReport](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): report, source grouping, exclusions, unconditional classes.
- [Spring Boot 3.3 API — ConditionEvaluationReportLoggingListener](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): cách ghi report vào log và chọn log level.
- [Spring Boot 3.3 Actuator — Conditions endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): cấu trúc `positiveMatches`, `negativeMatches`, `notMatched` và `matched`.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): exposure và bảo vệ endpoint quản trị.

**Ghi nhớ:** Hãy đọc report theo hai tầng: **class source trước, method source sau**. Class-level negative nghĩa là cấu hình ngoài không qua điều kiện; class-level positive nhưng method-level negative nghĩa là một bean cụ thể bị chặn. Đối chiếu source key với tên class/method, rồi xác minh bean thực tế và startup exception trước khi thay đổi cấu hình.
