# Đọc báo cáo điều kiện ngay trong kiểm thử để giải thích kết quả

> **Spring Boot Auto Configuration → Kiểm thử độc lập.** Bài học hướng dẫn đọc `ConditionEvaluationReport` ngay trong callback của `ApplicationContextRunner`. Ta sẽ tra kết quả theo nguồn là lớp auto-configuration hoặc factory method, phân biệt condition match/no-match, đọc thông điệp giải thích của Spring Boot và viết assertion cho hai trường hợp: property không bật cấu hình và bean do ứng dụng cung cấp khiến bean mặc định back off. Ví dụ dùng Java 17+, Maven và Spring Boot 3.3.13.

## 1. Vì sao chỉ assert bean có hoặc không là chưa đủ?

Một test thường bắt đầu bằng:

~~~java
runner.run(context -> {
    assertThat(context).doesNotHaveBean(NoticeClient.class);
});
~~~

Assertion này xác nhận kết quả cuối cùng: context không có `NoticeClient`. Nhưng nó chưa giải thích **vì sao** bean không xuất hiện.

Có nhiều nguyên nhân dẫn đến cùng một kết quả:
- Property bật feature chưa được đặt hoặc có giá trị false.
- Một class tùy chọn không có trên classpath.
- Bean dependency mà integration cần chưa tồn tại.
- Ứng dụng đã cung cấp bean cùng type nên `@ConditionalOnMissingBean` không match.
- Auto-configuration bị loại trừ.
- Cấu hình có match nhưng factory method tạo bean gặp exception.

Khi test chỉ kiểm tra bean vắng mặt, các nguyên nhân này có thể bị nhầm lẫn. Ví dụ, một test dự kiến kiểm tra `acme.notice.enabled=false` có thể vẫn pass dù cấu hình bị bỏ qua vì thiếu dependency. Test không chứng minh được property condition đã được đánh giá đúng.

`ConditionEvaluationReport` giúp kiểm tra lý do của từng condition. Nó lưu:
- Source đã được đánh giá: lớp cấu hình hoặc factory method.
- Condition object đã chạy.
- Kết quả match hoặc no-match.
- Thông điệp giải thích do condition tạo ra.

Kết hợp assertion bean với report, test có thể trả lời cả hai câu hỏi: **đã xảy ra điều gì** và **điều kiện nào dẫn đến kết quả đó**.

## 2. ConditionEvaluationReport là gì?

`org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` là đối tượng Spring Boot dùng để ghi nhận kết quả đánh giá condition phục vụ báo cáo và logging.

Report được gắn với `BeanFactory` của application context. Trong một context do `ApplicationContextRunner` tạo, có thể lấy report sau khi context khởi động thành công:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.find(
                context.getSourceApplicationContext().getBeanFactory()
        );
~~~

Giải thích:
- `context` là `AssertableApplicationContext` được truyền vào callback của runner.
- `getSourceApplicationContext()` trả về application context thật đứng sau đối tượng assertion.
- `getBeanFactory()` lấy bean factory đã xử lý cấu hình.
- `ConditionEvaluationReport.find(...)` tìm report hiện có; nếu không tìm thấy thì trả về `null`.

Trong test nên dùng `find(...)` khi muốn xác nhận report thực sự đã được tạo. `ConditionEvaluationReport.get(beanFactory)` trả về report hiện có hoặc tạo một report mới; dùng `get(...)` có thể khiến test vô tình nhận một report rỗng và che giấu việc chưa có dữ liệu condition.

### 2.1. Các API quan trọng

| API | Ý nghĩa |
| --- | --- |
| `ConditionEvaluationReport.find(beanFactory)` | Tìm report hiện có; có thể trả về null |
| `ConditionEvaluationReport.get(beanFactory)` | Lấy report hiện có hoặc tạo report mới |
| `getConditionAndOutcomesBySource()` | Map các kết quả condition theo source |
| `getExclusions()` | Danh sách auto-configuration bị loại trừ |
| `getUnconditionalClasses()` | Các lớp được đánh giá nhưng không có condition |
| `ConditionAndOutcomes.isFullMatch()` | true khi mọi condition trong source đều match |
| `ConditionAndOutcome.getCondition()` | Condition object đã được đánh giá |
| `ConditionAndOutcome.getOutcome()` | Kết quả đánh giá của condition |
| `ConditionOutcome.isMatch()` | Condition có match hay không |
| `ConditionOutcome.getMessage()` | Thông điệp giải thích kết quả |

Các class và method trên thuộc API Spring Boot 3.3.13. Report ghi kết quả theo source, nên có thể xem riêng condition của class và condition trên từng method tạo bean.

### 2.2. Source là lớp hoặc factory method

Map từ `getConditionAndOutcomesBySource()` dùng tên source làm key. Hai dạng thường gặp:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
com.acme.notice.autoconfigure.NoticeAutoConfiguration#noticeClient
~~~

- Key thứ nhất đại diện condition ở cấp lớp.
- Key thứ hai đại diện condition ở factory method `noticeClient()`.

Điểm này rất hữu ích vì một lớp có thể match nhưng một bean method bên trong vẫn không match. Ví dụ, property bật toàn bộ cấu hình nhưng `@ConditionalOnMissingBean` trên method không match vì ứng dụng đã đăng ký bean thay thế.

Không nên chỉ lấy phần tử đầu tiên trong toàn report rồi kết luận cho một bean cụ thể. Hãy tra đúng source key mà test đang kiểm tra.

## 3. Phân biệt trạng thái condition và trạng thái bean

`ConditionAndOutcomes` chứa một hoặc nhiều `ConditionAndOutcome`.

- `isFullMatch()` trả về true khi tất cả outcome trong source đều match.
- `isMatch()` trên từng `ConditionOutcome` cho biết condition tương ứng match hay không.
- `getMessage()` cung cấp lời giải thích cho outcome.

Ví dụ:

~~~java
var outcomes = report.getConditionAndOutcomesBySource()
        .get(NoticeAutoConfiguration.class.getName());

assertThat(outcomes).isNotNull();
assertThat(outcomes.isFullMatch()).isFalse();

assertThat(outcomes).anySatisfy(item -> {
    assertThat(item.getOutcome().isMatch()).isFalse();
    assertThat(item.getOutcome().getMessage()).contains("enabled");
});
~~~

Không đồng nhất ba khái niệm:
1. **Class condition:** quyết định cấu hình có được áp dụng hay không.
2. **Bean method condition:** quyết định factory method cụ thể có được đăng ký hay không.
3. **Bean creation:** xảy ra sau khi bean definition đã được đăng ký; bean vẫn có thể lỗi khi khởi tạo.

Report giải thích bước đánh giá condition. Nó không chứng minh rằng mọi bean đã tạo thành công hoặc mọi thao tác nghiệp vụ sẽ hoạt động.

### 3.1. Một lớp không match có thể ngăn method condition được đánh giá

Giả sử lớp có `@ConditionalOnProperty` và factory method có `@ConditionalOnMissingBean`.

Nếu property không match:
- Spring bỏ qua cấu hình.
- Method `noticeClient()` không được đăng ký.
- Condition trên method có thể không có entry riêng trong report, vì method không đi đến bước đánh giá.

Nếu property match nhưng ứng dụng đã cung cấp `NoticeClient`:
- Condition của lớp match.
- Spring xét bean method.
- `@ConditionalOnMissingBean` không match.
- Bean mặc định không được tạo.

Hai tình huống đều làm `NoticeClient` vắng mặt, nhưng report cho thấy nguyên nhân khác nhau.

## 4. Dự án mẫu Java 17 và Spring Boot 3.3.13

Lab tạo một auto-configuration đơn giản. Bean `NoticeClient` chỉ được tạo khi `acme.notice.enabled=true`; factory method chỉ tạo bean mặc định nếu ứng dụng chưa cung cấp bean cùng kiểu.

### 4.1. Cấu trúc dự án

~~~text
notice-condition-report/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/notice/
    │   │   ├── NoticeClient.java
    │   │   └── autoconfigure/
    │   │       └── NoticeAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/notice/autoconfigure/
            └── NoticeAutoConfigurationConditionReportTest.java
~~~

### 4.2. pom.xml

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.acme</groupId>
    <artifactId>notice-condition-report</artifactId>
    <version>1.0.0</version>

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
~~~

`spring-boot-autoconfigure` cung cấp condition annotations và report API. `spring-boot-starter-test` cung cấp JUnit 5, AssertJ và `ApplicationContextRunner`.

### 4.3. NoticeClient.java

Tệp `src/main/java/com/acme/notice/NoticeClient.java`:

~~~java
package com.acme.notice;

public record NoticeClient(String origin) {

    public String send(String message) {
        return origin + ":" + message;
    }
}
~~~

Thuộc tính `origin` giúp test nhận biết bean đến từ auto-configuration hay từ ứng dụng.

### 4.4. NoticeAutoConfiguration.java

Tệp `src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java`:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeClient.class)
    NoticeClient noticeClient() {
        return new NoticeClient("auto");
    }
}
~~~

Có hai tầng condition:
- `@ConditionalOnProperty` nằm trên class. Khi property thiếu hoặc không phải true, cấu hình không được áp dụng.
- `@ConditionalOnMissingBean` nằm trên method. Khi context đã có `NoticeClient`, bean mặc định không được tạo.

### 4.5. Đăng ký auto-configuration

Tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
~~~

File này đăng ký cấu hình cho ứng dụng Spring Boot khi module được đóng gói thành JAR. Các test trong phần tiếp theo dùng `AutoConfigurations.of(NoticeAutoConfiguration.class)` để nạp class trực tiếp và tập trung đọc condition report; chúng chưa kiểm tra việc Boot phát hiện file imports trong JAR.

## 5. Tạo helper đọc report ngay trong test

Tệp test sẽ có hai helper:
- `conditionReport(...)` lấy report từ BeanFactory của context.
- `outcomesFor(...)` lấy kết quả theo đúng source key và bảo đảm source có trong report.

~~~java
private static ConditionEvaluationReport conditionReport(
        AssertableApplicationContext context) {

    var sourceContext = context.getSourceApplicationContext();

    ConditionEvaluationReport report =
            ConditionEvaluationReport.find(sourceContext.getBeanFactory());

    assertThat(report)
            .as("ConditionEvaluationReport should exist after refresh")
            .isNotNull();

    return report;
}

private static ConditionEvaluationReport.ConditionAndOutcomes outcomesFor(
        ConditionEvaluationReport report,
        String source) {

    var outcomes = report.getConditionAndOutcomesBySource().get(source);

    assertThat(outcomes)
            .as("Condition outcomes for " + source)
            .isNotNull();

    return outcomes;
}
~~~

Cần import:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
~~~

Lấy report bên trong callback `run(...)`, sau khi context đã refresh. Không lấy source context khi context chưa khởi động thành công; `getSourceApplicationContext()` không dùng được nếu context startup thất bại.

### 5.1. In thông tin của một source

Khi cần đọc report trong log test, có thể thêm helper:

~~~java
private static void printOutcomes(
        ConditionEvaluationReport report,
        String source) {

    var outcomes = outcomesFor(report, source);

    System.out.println("source: " + source);
    System.out.println("full match: " + outcomes.isFullMatch());

    for (var item : outcomes) {
        var outcome = item.getOutcome();

        System.out.println(
                "  " + item.getCondition().getClass().getSimpleName()
                        + " -> "
                        + (outcome.isMatch() ? "MATCH" : "NO MATCH")
                        + " : "
                        + outcome.getMessage()
        );
    }
}
~~~

Helper này không tự quyết định test pass/fail. Nó chỉ hiển thị dữ liệu để người đọc biết condition nào match và message nào giải thích kết quả. Assertion vẫn phải được viết riêng.

## 6. Ba test đọc report để giải thích ba kết quả

Tệp `src/test/java/com/acme/notice/autoconfigure/NoticeAutoConfigurationConditionReportTest.java`:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeAutoConfigurationConditionReportTest {

    private static final String CONFIG_SOURCE =
            NoticeAutoConfiguration.class.getName();

    private static final String BEAN_METHOD_SOURCE =
            NoticeAutoConfiguration.class.getName() + "#noticeClient";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeAutoConfiguration.class
                    ));

    private static ConditionEvaluationReport conditionReport(
            AssertableApplicationContext context) {

        var sourceContext = context.getSourceApplicationContext();

        ConditionEvaluationReport report =
                ConditionEvaluationReport.find(sourceContext.getBeanFactory());

        assertThat(report)
                .as("ConditionEvaluationReport should exist after refresh")
                .isNotNull();

        return report;
    }

    private static ConditionEvaluationReport.ConditionAndOutcomes outcomesFor(
            ConditionEvaluationReport report,
            String source) {

        var outcomes = report.getConditionAndOutcomesBySource().get(source);

        assertThat(outcomes)
                .as("Condition outcomes for " + source)
                .isNotNull();

        return outcomes;
    }

    private static void printOutcomes(
            ConditionEvaluationReport report,
            String source) {

        var outcomes = outcomesFor(report, source);

        System.out.println("source: " + source);
        System.out.println("full match: " + outcomes.isFullMatch());

        for (var item : outcomes) {
            var outcome = item.getOutcome();

            System.out.println(
                    "  " + item.getCondition().getClass().getSimpleName()
                            + " -> "
                            + (outcome.isMatch() ? "MATCH" : "NO MATCH")
                            + " : "
                            + outcome.getMessage()
            );
        }
    }

    @Test
    void missingPropertyReportExplainsWhyConfigurationWasSkipped() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(NoticeClient.class);

            ConditionEvaluationReport report = conditionReport(context);
            var outcomes = outcomesFor(report, CONFIG_SOURCE);

            assertThat(outcomes.isFullMatch()).isFalse();

            assertThat(outcomes).anySatisfy(item -> {
                assertThat(item.getOutcome().isMatch()).isFalse();
                assertThat(item.getOutcome().getMessage())
                        .contains("enabled");
            });

            printOutcomes(report, CONFIG_SOURCE);
        });
    }

    @Test
    void enabledPropertyShowsPositiveClassAndBeanMethodOutcomes() {
        runner.withPropertyValues("acme.notice.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context.getBean(NoticeClient.class).origin())
                            .isEqualTo("auto");

                    ConditionEvaluationReport report = conditionReport(context);

                    var classOutcomes =
                            outcomesFor(report, CONFIG_SOURCE);

                    var beanOutcomes =
                            outcomesFor(report, BEAN_METHOD_SOURCE);

                    assertThat(classOutcomes.isFullMatch()).isTrue();
                    assertThat(beanOutcomes.isFullMatch()).isTrue();

                    printOutcomes(report, CONFIG_SOURCE);
                    printOutcomes(report, BEAN_METHOD_SOURCE);
                });
    }

    @Test
    void userBeanExplainsWhyDefaultFactoryMethodWasSkipped() {
        NoticeClient customClient = new NoticeClient("application");

        runner.withPropertyValues("acme.notice.enabled=true")
                .withBean(NoticeClient.class, () -> customClient)
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context.getBean(NoticeClient.class))
                            .isSameAs(customClient);

                    ConditionEvaluationReport report = conditionReport(context);
                    var classOutcomes =
                            outcomesFor(report, CONFIG_SOURCE);
                    var beanOutcomes =
                            outcomesFor(report, BEAN_METHOD_SOURCE);

                    assertThat(classOutcomes.isFullMatch()).isTrue();
                    assertThat(beanOutcomes.isFullMatch()).isFalse();

                    assertThat(beanOutcomes).anySatisfy(item -> {
                        assertThat(item.getOutcome().isMatch()).isFalse();
                        assertThat(item.getOutcome().getMessage())
                                .contains("NoticeClient");
                    });

                    printOutcomes(report, CONFIG_SOURCE);
                    printOutcomes(report, BEAN_METHOD_SOURCE);
                });
    }
}
~~~

### 6.1. Trường hợp A: thiếu property

Test `missingPropertyReportExplainsWhyConfigurationWasSkipped()` không truyền `acme.notice.enabled`.

Kết quả:
- `NoticeClient` không có trong context.
- Source của class có entry trong report.
- `isFullMatch()` là false.
- Ít nhất một outcome no-match có message liên quan property `enabled`.

Đây là bằng chứng rằng bean vắng mặt vì condition trên class không match. Không cần đoán từ tên test hoặc chỉ đọc assertion bean.

### 6.2. Trường hợp B: property bật

Test `enabledPropertyShowsPositiveClassAndBeanMethodOutcomes()` truyền:

~~~java
.withPropertyValues("acme.notice.enabled=true")
~~~

Kết quả:
- Class-level property condition match.
- Method-level missing-bean condition match vì chưa có `NoticeClient`.
- Bean mặc định được tạo với `origin` bằng `auto`.

Hai source được kiểm tra riêng. Điều đó xác nhận cả cấu hình lẫn factory method đều đủ điều kiện.

### 6.3. Trường hợp C: ứng dụng cung cấp bean thay thế

Test `userBeanExplainsWhyDefaultFactoryMethodWasSkipped()` truyền property bật và đăng ký bean tùy chỉnh bằng `withBean(...)`.

Kết quả:
- Class-level property condition vẫn match.
- `@ConditionalOnMissingBean` trên factory method không match.
- Context giữ instance tùy chỉnh của ứng dụng.
- Report ở source `NoticeAutoConfiguration#noticeClient` giải thích vì sao bean mặc định bị bỏ qua.

Đây là ví dụ quan trọng: report có thể cho thấy **class match nhưng method no-match**. Nếu chỉ đọc trạng thái tổng thể của class, ta sẽ bỏ lỡ nguyên nhân khiến một bean cụ thể không được tạo.

## 7. Chạy test và đọc report

Từ thư mục dự án:

~~~bash
mvn clean test
~~~

Kỳ vọng ba test PASS:
- Property thiếu: cấu hình không match.
- Property true: class và bean method đều match.
- Property true cùng bean user: class match, factory method no-match.

`printOutcomes(...)` in source, trạng thái full match, tên condition và message của Boot. Ví dụ dạng kết quả rút gọn:

~~~text
source: com.acme.notice.autoconfigure.NoticeAutoConfiguration
full match: false
  OnPropertyCondition -> NO MATCH : <message giải thích property enabled không đáp ứng>
~~~

Với trường hợp user override:

~~~text
source: com.acme.notice.autoconfigure.NoticeAutoConfiguration
full match: true

source: com.acme.notice.autoconfigure.NoticeAutoConfiguration#noticeClient
full match: false
  OnBeanCondition -> NO MATCH : <message cho biết đã tìm thấy NoticeClient>
~~~

Phần trong dấu ngoặc nhọn là mô tả dạng message, không phải chuỗi stdout cố định. Message thật do Spring Boot tạo ra và có thể khác đôi chút giữa các phiên bản. Test nên kiểm tra trạng thái và một đoạn nội dung ổn định, tránh so sánh toàn bộ message.

## 8. Đọc toàn bộ report hoặc lọc đúng phần cần thiết

### 8.1. Duyệt tất cả source

Khi chưa biết condition nào gây ra kết quả, duyệt toàn bộ map:

~~~java
ConditionEvaluationReport report = conditionReport(context);

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    System.out.println(
            source + " => "
                    + (outcomes.isFullMatch() ? "MATCH" : "NO MATCH")
    );

    outcomes.forEach(item -> {
        var outcome = item.getOutcome();

        System.out.println(
                "  " + item.getCondition().getClass().getSimpleName()
                        + " => "
                        + (outcome.isMatch() ? "MATCH" : "NO MATCH")
                        + " : "
                        + outcome.getMessage()
        );
    });
});
~~~

Đây là cách tốt khi điều tra một auto-configuration có nhiều nested configuration và nhiều bean method. Khi đã biết bean cần kiểm tra, lọc theo source cụ thể để assertion không bị ảnh hưởng bởi condition của các thành phần không liên quan.

### 8.2. Lọc các source no-match

~~~java
report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    if (!outcomes.isFullMatch()) {
        System.out.println("NO MATCH: " + source);

        outcomes.forEach(item -> {
            if (!item.getOutcome().isMatch()) {
                System.out.println(item.getOutcome().getMessage());
            }
        });
    }
});
~~~

Lọc này giúp tập trung vào lý do cấu hình hoặc bean bị bỏ qua. Một source có thể chứa nhiều condition; `isFullMatch()` false nghĩa là ít nhất một outcome không match, vì vậy nên duyệt từng outcome để tìm nguyên nhân cụ thể.

### 8.3. Xem các auto-configuration bị loại trừ

~~~java
ConditionEvaluationReport report = conditionReport(context);

assertThat(report.getExclusions()).isNotNull();

report.getExclusions().forEach(exclusion ->
        System.out.println("excluded: " + exclusion)
);
~~~

`getExclusions()` cho biết các lớp bị loại khỏi condition evaluation do cấu hình loại trừ. Điều này khác với một condition được đánh giá rồi trả về no-match:
- Exclusion: lớp bị loại khỏi quá trình đánh giá.
- No-match: condition đã được đánh giá và không đáp ứng.

Không suy luận rằng mọi source vắng mặt trong map đều bị exclude. Có thể lớp không phải candidate, chưa được import hoặc không đi tới bước condition tương ứng.

## 9. Kết hợp report với assertion và failure message

Mục tiêu của report trong test là làm cho lỗi dễ chẩn đoán. Có thể thêm source key vào assertion:

~~~java
assertThat(outcomes.isFullMatch())
        .as("Condition report for %s", CONFIG_SOURCE)
        .isFalse();
~~~

Hoặc đưa message thực tế vào assertion:

~~~java
String reasons = StreamSupport.stream(
        outcomes.spliterator(),
        false
).map(item -> item.getOutcome().getMessage())
 .filter(Objects::nonNull)
 .collect(Collectors.joining("; "));

assertThat(reasons)
        .as("Condition no-match explanation")
        .contains("enabled");
~~~

Đoạn này cần import `java.util.Objects`, `java.util.stream.Collectors` và `java.util.stream.StreamSupport`. Chỉ dùng khi cần gộp nhiều outcome thành một chuỗi; với một source đơn giản, duyệt trực tiếp thường dễ đọc hơn.

Một test tốt thường có thứ tự:
1. Assert bean có/vắng đúng như contract.
2. Lấy report.
3. Assert source có entry.
4. Assert `isFullMatch()` theo kịch bản.
5. Assert ít nhất một outcome no-match hoặc match theo điều kiện cần kiểm tra.
6. Kiểm tra một phần message để xác nhận lý do.

Đừng chỉ assert message mà bỏ qua bean. Một condition no-match có thể đúng nhưng bean vẫn xuất hiện từ cấu hình khác. Cũng đừng chỉ assert bean vắng mặt mà không kiểm tra report khi mục tiêu test là xác minh lý do.

## 10. Khi nào dùng report trực tiếp, khi nào dùng --debug?

Hai cách phục vụ hai mục đích:

| Cách | Phạm vi | Dùng khi |
| --- | --- | --- |
| `ConditionEvaluationReport` trong `ApplicationContextRunner` | Một context kiểm thử | Assertion nguyên nhân cho một auto-configuration hoặc bean |
| `--debug` | Một lần chạy ứng dụng | Điều tra tổng thể cấu hình trong ứng dụng |
| Actuator `/actuator/conditions` | Context đã khởi động và endpoint được expose | Kiểm tra condition trong môi trường có kiểm soát |

Trong test, đọc object report trực tiếp tốt hơn parse log console. Log có thể đổi format, bị capture bởi test runner hoặc lẫn với log của các cấu hình khác.

Trong ứng dụng đang chạy, `--debug` có thể in Condition Evaluation Report tổng thể. Endpoint Actuator `conditions` cũng cung cấp dữ liệu cho các condition của configuration/auto-configuration khi Actuator được cấu hình và bảo vệ phù hợp.

Không cần bật `--debug` trong mọi test chỉ để đọc report. `ConditionEvaluationReport` có thể được lấy trực tiếp từ BeanFactory trong callback runner.

## 11. Những điều report không chứng minh

1. **Report không chứng minh bean đã khởi tạo thành công.** Condition match chỉ cho phép cấu hình/bean definition đi tiếp; constructor hoặc factory method vẫn có thể ném exception.
2. **Report không chứng minh kết nối bên ngoài hoạt động.** Ví dụ condition DataSource match không chứng minh database nhận kết nối.
3. **Report không thay thế assertion bean.** Cần xác nhận kết quả thực tế trong context.
4. **Report không nhất thiết có entry cho mọi condition Java.** Các condition Spring Boot có cơ chế ghi outcome vào report; custom `Condition` tùy chỉnh có thể không cung cấp message theo cùng cách.
5. **Report là dữ liệu của một BeanFactory cụ thể.** Khi context có parent, cần chú ý report của context con và parent.
6. **Report không phải API log ổn định theo từng ký tự.** Message có thể thay đổi giữa các phiên bản Boot; tránh assert toàn bộ câu.
7. **`find(...)` có thể trả về null.** Trong test, hãy assert report tồn tại trước khi đọc map.
8. **`get(...)` có thể tạo report mới.** Không dùng `get(...)` rồi kết luận rằng Spring đã ghi condition nếu report trước đó chưa tồn tại.
9. **Context startup failure cần xử lý riêng.** `getSourceApplicationContext()` không thể trả source context đã khởi động thất bại; hãy xem `context.getStartupFailure()` và exception chain.
10. **`AutoConfigurations.of(...)` không kiểm tra JAR metadata.** Nó nạp class cấu hình trực tiếp; cần consumer test riêng để kiểm tra `AutoConfiguration.imports`.

## 12. Các lỗi phổ biến khi đọc ConditionEvaluationReport

1. **Chỉ kiểm tra `isFullMatch()` ở class source.** Bean method có thể no-match dù class match.
2. **Đọc nhầm source key.** Một class và một method có hai key khác nhau.
3. **Dùng `get(...)` rồi không kiểm tra report rỗng.** Có thể test tự tạo report mới mà không có condition outcome.
4. **Gọi `getSourceApplicationContext()` sau startup failure.** Source context không khả dụng trong trường hợp đó.
5. **So sánh nguyên văn toàn bộ message.** Message có thể đổi wording giữa các bản vá.
6. **Chỉ assert report, không assert bean.** Một bean khác có thể cung cấp cùng type hoặc hành vi.
7. **Chỉ assert bean, không đọc report.** Test không giải thích được condition nào làm bean vắng mặt.
8. **Cho rằng no-match luôn là lỗi.** `@ConditionalOnMissingBean` no-match khi user bean tồn tại thường là back-off đúng.
9. **Cho rằng source không có trong map nghĩa là bị loại trừ.** Có nhiều lý do khiến source không được đánh giá.
10. **Đọc toàn bộ map trong mọi test.** Dễ tạo assertion phụ thuộc vào cấu hình không liên quan; lọc đúng source khi đã biết mục tiêu.
11. **Nhầm condition match với bean creation thành công.** Constructor/factory method có thể thất bại sau khi condition match.
12. **Dùng log thay cho report object trong unit test.** Parse log làm test mong manh và khó cô lập.

## 13. Quy trình viết test có giải thích condition

1. Xác định bean đang được kiểm tra và source tương ứng: class hay factory method.
2. Tạo `ApplicationContextRunner` với đúng auto-configuration.
3. Dùng `withPropertyValues(...)` để tạo kịch bản property cần kiểm tra.
4. Đăng ký bean nền hoặc bean thay thế bằng `withBean(...)` nếu kịch bản yêu cầu.
5. Trong callback `run(...)`, assert bean có/vắng.
6. Lấy report từ `context.getSourceApplicationContext().getBeanFactory()`.
7. Tra source key trong `getConditionAndOutcomesBySource()`.
8. Assert `isFullMatch()` và từng `ConditionOutcome.isMatch()`.
9. Kiểm tra message theo một phần nội dung ổn định để xác nhận nguyên nhân.
10. In report khi hữu ích để chẩn đoán trong CI.
11. Chạy test và kiểm tra Surefire report khi cần xem stdout đã capture.
12. Bổ sung consumer test nếu cần xác minh discovery từ JAR metadata.

## 14. Checklist nghiệm thu

- [ ] Test dùng `ApplicationContextRunner` cho auto-configuration cần kiểm tra.
- [ ] Property của từng kịch bản được thiết lập tường minh.
- [ ] Test xác nhận bean có/vắng.
- [ ] Report được lấy từ BeanFactory của đúng context.
- [ ] Test xác nhận report thực sự tồn tại khi cần đọc.
- [ ] Source key của class được phân biệt với source key của bean method.
- [ ] Test kiểm tra `ConditionAndOutcomes.isFullMatch()`.
- [ ] Test đọc từng `ConditionOutcome.isMatch()` và `getMessage()`.
- [ ] Test có tình huống property no-match.
- [ ] Test có tình huống property match.
- [ ] Test có tình huống user bean làm `@ConditionalOnMissingBean` no-match.
- [ ] Assertion message không phụ thuộc toàn bộ wording.
- [ ] Không nhầm condition match với bean creation hoặc kết nối thành công.
- [ ] Không nhầm no-match có chủ đích với lỗi.
- [ ] Có consumer test riêng nếu cần xác minh imports metadata trong JAR.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Lấy ConditionEvaluationReport từ ApplicationContextRunner bằng cách nào?  
**Đáp án:** Lấy source context trong callback, rồi gọi `ConditionEvaluationReport.find(sourceContext.getBeanFactory())`.

**Câu 2.** `getConditionAndOutcomesBySource()` trả về cấu trúc gì?  
**Đáp án:** Map từ tên source (lớp hoặc method) đến `ConditionAndOutcomes`.

**Câu 3.** `isFullMatch()` false có nghĩa gì?  
**Đáp án:** Ít nhất một condition thuộc source đó không match. Cần duyệt từng outcome để biết condition nào và message nào giải thích kết quả.

**Câu 4.** Class-level condition match nhưng bean method no-match có thể xảy ra không?  
**Đáp án:** Có. Ví dụ class property condition match, nhưng `@ConditionalOnMissingBean` trên factory method no-match vì ứng dụng đã cung cấp bean.

**Câu 5.** Vì sao test cần assert cả bean và report?  
**Đáp án:** Bean assertion xác nhận kết quả cuối; report giải thích condition dẫn đến kết quả đó. Cả hai giúp tránh kết luận sai từ một phía.

**Câu 6.** Có nên so sánh toàn bộ `ConditionOutcome.getMessage()` với chuỗi cố định không?  
**Đáp án:** Thường không. Nên kiểm tra trạng thái và một đoạn message ổn định vì wording có thể thay đổi theo phiên bản Boot.

**Câu 7.** `ConditionEvaluationReport.get(...)` và `find(...)` khác nhau thế nào?  
**Đáp án:** `find(...)` tìm report hiện có và có thể trả null; `get(...)` lấy report hiện có hoặc tạo report mới.

**Câu 8.** `AutoConfigurations.of(...)` có chứng minh file imports trong JAR đúng không?  
**Đáp án:** Không. Nó nạp class trực tiếp. Cần consumer hoặc packaged integration test để xác minh discovery metadata.

## 16. Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 Javadoc — ConditionEvaluationReport](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html).
- [Spring Boot 3.3.13 Javadoc — ConditionAndOutcome](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcome.html).
- [Spring Boot 3.3.13 Javadoc — ConditionAndOutcomes](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcomes.html).
- [Spring Boot 3.3.13 Javadoc — ConditionOutcome](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html).
- [Spring Boot 3.3.13 Javadoc — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).
- [Spring Boot 3.3 — Conditions Evaluation Report Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)