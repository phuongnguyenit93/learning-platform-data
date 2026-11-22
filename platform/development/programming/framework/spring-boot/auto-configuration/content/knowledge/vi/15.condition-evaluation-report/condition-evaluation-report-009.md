# ConditionEvaluationReportLoggingListener trong kiểm thử cấu hình

## 1. Mục tiêu và vấn đề cần giải quyết

Khi kiểm thử Spring Boot Auto Configuration, một bean có thể xuất hiện hoặc biến mất tùy theo nhiều điều kiện: class có trên classpath hay không, property có giá trị gì, bean người dùng đã được khai báo chưa, ứng dụng có chạy trong web context không, hoặc auto-configuration khác đã được áp dụng chưa.

Một test chỉ khẳng định:

```java
assertThat(context).doesNotHaveBean("paymentClient");
```

cho biết **kết quả cuối cùng** nhưng chưa trả lời được vì sao bean không xuất hiện. Có thể `@ConditionalOnClass` không khớp, `@ConditionalOnProperty` sai giá trị, `@ConditionalOnMissingBean` đã back off, hoặc chính cấu hình chưa được đưa vào context thử nghiệm.

Spring Boot lưu lại thông tin đánh giá điều kiện trong `ConditionEvaluationReport`. Lớp `ConditionEvaluationReportLoggingListener` giúp ghi report đó ra log khi chạy test cấu hình. Kết hợp với `ApplicationContextRunner`, bạn có thể vừa đọc được lý do matched/unmatched, vừa viết assertion để ngăn lỗi hồi quy.

Bài học tập trung vào Spring Boot **3.3.x** và JDK 17+:

- Hiểu quan hệ giữa `ApplicationContextRunner`, `ConditionEvaluationReport` và `ConditionEvaluationReportLoggingListener`.
- Đăng ký listener đúng cách qua `ApplicationContextInitializer`.
- Chọn log level `INFO` hoặc `DEBUG`, tránh trường hợp report bị ẩn.
- Không dùng log thay cho assertion; kiểm tra report bằng API khi cần.
- Viết test cho điều kiện khớp và không khớp bằng một ví dụ Java/Maven có thể chạy độc lập.

## 2. Ba thành phần và trách nhiệm của từng thành phần

### 2.1. `ApplicationContextRunner`: tạo context thử nghiệm cô lập

`ApplicationContextRunner` thuộc package:

```java
org.springframework.boot.test.context.runner.ApplicationContextRunner
```

Đây là runner dành cho **standard, non-web ApplicationContext**. Mỗi lần gọi `run(...)`, runner tạo một context được cấu hình theo kịch bản đã khai báo, refresh context, chuyển context cho callback để kiểm tra, rồi đóng context sau khi callback kết thúc.

Một runner cơ bản:

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(MyAutoConfiguration.class)
    )
    .withPropertyValues("demo.feature.enabled=true")
    .run(context -> {
        // Kiểm tra bean và trạng thái context.
    });
```

Những phần chính:

- `withConfiguration(AutoConfigurations.of(...))`: chỉ định các auto-configuration cần được đưa vào kịch bản test.
- `withUserConfiguration(...)`: thêm cấu hình do ứng dụng/người dùng cung cấp, ví dụ một `@Bean` tùy chỉnh để kiểm tra cơ chế back off.
- `withPropertyValues(...)`: thay đổi `Environment` cho test, không cần sửa file `application.properties` thật.
- `withClassLoader(...)`: mô phỏng một class hoặc package không có trên classpath, thường kết hợp `FilteredClassLoader`.
- `withInitializer(...)`: thêm `ApplicationContextInitializer`, nơi listener được gắn vào context.
- `run(...)`: thực thi kịch bản và cho phép assertion trên context.

Mỗi test nên mô tả một tổ hợp cụ thể của classpath, property và bean người dùng. Điều này giúp test có tính quyết định, không phụ thuộc vào cấu hình máy phát triển.

### 2.2. `ConditionEvaluationReport`: dữ liệu về kết quả đánh giá điều kiện

`ConditionEvaluationReport` thuộc package:

```java
org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport
```

Đây là đối tượng ghi lại thông tin condition evaluation. Những dữ liệu hữu ích gồm:

- `getConditionAndOutcomesBySource()`: trả về `Map` các kết quả condition được nhóm theo source, thường là tên lớp cấu hình hoặc tên method bean.
- `getExclusions()`: danh sách tên các auto-configuration bị loại trừ khỏi condition evaluation.
- `getUnconditionalClasses()`: các lớp được ghi nhận là không có condition.
- `getParent()`: report của bean factory cha nếu có.

Mỗi source có một `ConditionEvaluationReport.ConditionAndOutcomes`, là tập hợp có thể duyệt. Mỗi phần tử `ConditionAndOutcome` cung cấp:

- `getCondition()`: condition đã được đánh giá.
- `getOutcome()`: kết quả `ConditionOutcome`.
- `ConditionOutcome.isMatch()`: condition có khớp hay không.
- `ConditionOutcome.getMessage()`: lý do/diễn giải do condition cung cấp; nội dung có thể thay đổi theo condition và phiên bản.

Ví dụ về ý nghĩa của report:

```text
FeatureAutoConfiguration
  OnPropertyCondition
    MATCH
    @ConditionalOnProperty (demo.feature.enabled=true) matched

AnotherAutoConfiguration
  OnClassCondition
    NO MATCH
    @ConditionalOnClass did not find required class ...
```

Đây là **mẫu minh họa cách đọc**, không phải stdout cố định của mọi phiên bản hay mọi ứng dụng. Thông điệp thực tế được sinh bởi từng condition và phụ thuộc property, classpath, bean cùng cấu hình đang test.

### 2.3. `ConditionEvaluationReportLoggingListener`: ghi report ra log

Lớp này nằm trong package:

```java
org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener
```

Trong Spring Boot 3.3.13, nó triển khai:

```java
ApplicationContextInitializer<ConfigurableApplicationContext>
```

Vai trò của listener là **ghi `ConditionEvaluationReport` ra logging system**. Nó không tự chọn auto-configuration, không làm một condition trở thành true/false và không thay đổi bean definition. Nó chỉ hỗ trợ quan sát kết quả mà Spring Boot đã ghi nhận.

Có hai cách tạo listener:

```java
// Mặc định: ghi report ở DEBUG.
new ConditionEvaluationReportLoggingListener();

// Chọn INFO hoặc DEBUG một cách tường minh.
ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO);
ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.DEBUG);
```

Trong Boot 3.3:

- Constructor không tham số mặc định dùng `DEBUG`.
- `forLogLevel(LogLevel)` có từ Spring Boot 3.0.0.
- Triển khai 3.3.13 chấp nhận `INFO` hoặc `DEBUG` cho report; truyền mức khác không phải cách cấu hình hợp lệ.
- Javadoc nói rõ listener **không được thiết kế để dùng chung cho nhiều ApplicationContext**. Khi mỗi test tạo một context mới, hãy tạo một listener mới cho context đó.

Nếu muốn thấy report ngay trong log test thông thường, `INFO` thường thuận tiện hơn `DEBUG`:

```java
.withInitializer(
    ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
)
```

Tuy nhiên, log level mà listener yêu cầu vẫn chịu bộ lọc của logging backend. Nếu hệ thống log đang bỏ qua `INFO` thì dòng report vẫn có thể bị ẩn. Hãy kiểm tra cấu hình logging của test khi không thấy kết quả.

## 3. Gắn listener vào ApplicationContextRunner

Cách dùng chính thức trong Spring Boot 3.3 là thêm initializer vào runner:

```java
new ApplicationContextRunner()
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
    )
    .run(context -> {
        // Assertions.
    });
```

Trong test có auto-configuration cụ thể, kết hợp thêm `AutoConfigurations.of(...)`:

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(FeatureAutoConfiguration.class)
    )
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
    )
    .run(context -> {
        assertThat(context).hasSingleBean(FeatureService.class);
    });
```

Đây là **snippet minh họa**; các class `FeatureAutoConfiguration` và `FeatureService` cần được định nghĩa trong dự án thực tế.

### 3.1. Tạo listener mới cho từng context

Không tạo một listener ở field static rồi gắn lại cho hàng chục context khác nhau:

```java
// Không nên: cùng một initializer được dùng cho nhiều context.
private static final ConditionEvaluationReportLoggingListener LISTENER =
    ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO);
```

Javadoc của listener cảnh báo không chia sẻ instance giữa các context. Cách an toàn là tạo runner mới (và listener mới) theo từng test hoặc từng kịch bản:

```java
private ApplicationContextRunner newRunner() {
    return new ApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(FeatureAutoConfiguration.class)
        )
        .withInitializer(
            ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
        );
}
```

Mỗi lần gọi `newRunner()` tạo một runner cùng initializer riêng. Không gọi `newRunner()` một lần rồi tái sử dụng listener bên trong runner cho nhiều context nếu muốn tuân thủ khuyến nghị của Javadoc.

### 3.2. Listener không thay thế việc khai báo auto-configuration cần test

Chỉ thêm `withInitializer(listener)` không tự động đưa mọi auto-configuration trên classpath vào test. Bạn vẫn cần chỉ định lớp cấu hình qua `AutoConfigurations.of(...)` hoặc cơ chế phù hợp.

Ngược lại, `AutoConfigurations.of(...)` xác định auto-configuration cần chạy nhưng không tự in report. Hai thao tác có mục đích riêng:

| Thành phần | Trách nhiệm |
| --- | --- |
| `AutoConfigurations.of(...)` | Chọn auto-configuration tham gia test |
| `withPropertyValues(...)` | Thiết lập property của kịch bản |
| `withUserConfiguration(...)` | Thêm bean/cấu hình từ phía ứng dụng |
| `withInitializer(listener)` | Yêu cầu ghi report condition ra log |
| `assertThat(context)` | Kiểm chứng hành vi và bean thực tế |
| `ConditionEvaluationReport` API | Đọc condition outcome bằng code |

## 4. Đọc report trực tiếp để kiểm tra nguyên nhân

Listener chỉ ghi report ra log. Nếu test cần kiểm tra có cấu trúc, lấy report từ bean factory của context:

```java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(context.getBeanFactory());

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> outcomesBySource =
    report.getConditionAndOutcomesBySource();
```

Duyệt kết quả:

```java
outcomesBySource.forEach((source, outcomes) -> {
    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        ConditionOutcome outcome = item.getOutcome();

        System.out.printf(
            "%s | %s | %s%n",
            source,
            outcome.isMatch() ? "MATCH" : "NO MATCH",
            outcome.getMessage()
        );
    }
});
```

Trong ví dụ, mỗi dòng thể hiện:

1. Source: lớp cấu hình hoặc method bean có condition.
2. Kết quả: `MATCH` hoặc `NO MATCH`.
3. Message: giải thích do condition trả về.

Nếu cần xem những auto-configuration đã bị exclude:

```java
report.getExclusions().forEach(System.out::println);
```

Nếu cần xem các lớp unconditional:

```java
report.getUnconditionalClasses().forEach(System.out::println);
```

**Khác biệt giữa `get` và `find`:** `ConditionEvaluationReport.get(beanFactory)` lấy report hiện có hoặc tạo một report mới nếu chưa có; `ConditionEvaluationReport.find(beanFactory)` chỉ tìm report đã có và có thể trả `null`. Khi muốn kiểm tra xem context có report thực sự được ghi nhận không, `find` giúp tránh tự tạo một report rỗng trong quá trình kiểm tra.

**Lưu ý:** một source có thể có nhiều condition outcome, vì vậy hãy duyệt tất cả phần tử thay vì giả định một lớp chỉ có một condition. Report lưu dữ liệu theo source; tên source thường là tên class hoặc dạng `com.acme.MyAutoConfiguration#myBean` đối với method bean.

## 5. Report là công cụ chẩn đoán, assertion mới là hợp đồng của test

Đây là điểm quan trọng nhất khi sử dụng listener:

- Log report cho biết vì sao condition khớp hoặc không khớp.
- Assertion cho biết hành vi mà ứng dụng phải bảo đảm.
- Hai thứ hỗ trợ nhau nhưng không thay thế nhau.

Ví dụ, nếu yêu cầu nghiệp vụ là “khi `demo.feature.enabled=true` phải có `FeatureService`”, test cần assertion:

```java
assertThat(context).hasSingleBean(FeatureService.class);
```

Nếu yêu cầu là “khi property false thì không tạo bean”, test cần:

```java
assertThat(context).doesNotHaveBean(FeatureService.class);
```

Report có thể cho biết `OnPropertyCondition` không khớp vì giá trị property khác `true`. Nhưng nếu chỉ bật listener và nhìn log, test vẫn có thể xanh dù behavior bị thay đổi ngoài ý muốn; log không tự làm build thất bại.

Khi cần kiểm tra chính condition outcome, đọc `ConditionEvaluationReport` và assert `ConditionOutcome.isMatch()`. Điều này hữu ích để phát hiện trường hợp bean không xuất hiện vì lý do khác với dự đoán.

**Không assert toàn bộ chuỗi message mặc định nếu không cần thiết.** Message có thể thay đổi theo phiên bản Boot, condition implementation hoặc cách property/classpath được thiết lập. Nên ưu tiên assert bean behavior, outcome boolean, hoặc một phần thông điệp có ý nghĩa ổn định đối với test.

## 6. Ví dụ Java 17+ chạy độc lập với Maven và JUnit 5

Ví dụ tạo một auto-configuration có điều kiện property. Khi `demo.feature.enabled=true`, bean `FeatureService` xuất hiện; khi false, bean không xuất hiện. Cả hai test đều ghi report ở mức INFO và đọc trực tiếp outcome để assertion.

### 6.1. Cấu trúc dự án

```text
condition-report-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ConditionEvaluationReportingTests.java
```

Không cần `main()` vì đây là dự án test. Maven Surefire/JUnit sẽ chạy các phương thức `@Test`.

### 6.2. File `pom.xml`

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
    <artifactId>condition-report-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Spring context, auto-configuration và logging backend -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <!-- ApplicationContextRunner, JUnit 5 và AssertJ -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 6.3. File `src/test/java/demo/ConditionEvaluationReportingTests.java`

```java
package demo;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionEvaluationReportingTests {

    // Tạo runner mới cho mỗi test để mỗi context có listener riêng.
    private ApplicationContextRunner newRunner() {
        return new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(FeatureAutoConfiguration.class)
            )
            .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                    LogLevel.INFO
                )
            );
    }

    @Test
    void enabledPropertyMatchesAndCreatesBean() {
        newRunner()
            .withPropertyValues("demo.feature.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(FeatureService.class);

                ConditionOutcome outcome = featureConditionOutcome(context);
                assertThat(outcome.isMatch()).isTrue();

                System.out.println(
                    "enabled: bean=true, conditionMatch=" + outcome.isMatch()
                );
            });
    }

    @Test
    void disabledPropertyDoesNotMatchAndDoesNotCreateBean() {
        newRunner()
            .withPropertyValues("demo.feature.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(FeatureService.class);

                ConditionOutcome outcome = featureConditionOutcome(context);
                assertThat(outcome.isMatch()).isFalse();

                System.out.println(
                    "disabled: bean=false, conditionMatch=" + outcome.isMatch()
                );
            });
    }

    private ConditionOutcome featureConditionOutcome(
        AssertableApplicationContext context
    ) {
        ConditionEvaluationReport report =
            ConditionEvaluationReport.get(context.getBeanFactory());

        Map.Entry<String, ConditionEvaluationReport.ConditionAndOutcomes> source =
            report.getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry ->
                    entry.getKey().contains("FeatureAutoConfiguration")
                )
                .findFirst()
                .orElseThrow(() ->
                    new AssertionError("Feature condition was not recorded")
                );

        return source.getValue()
            .iterator()
            .next()
            .getOutcome();
    }

    @AutoConfiguration
    @ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true"
    )
    static class FeatureAutoConfiguration {

        @Bean
        FeatureService featureService() {
            return new FeatureService();
        }
    }

    static class FeatureService {
    }
}
```

### 6.4. Chạy test

Yêu cầu: JDK 17+, Maven 3.8+ và khả năng tải dependency từ Maven repository. Tại thư mục `condition-report-demo` chạy:

```bash
mvn test
```

Kết quả logic do các câu lệnh `System.out.println` trong hai test in ra:

```text
enabled: bean=true, conditionMatch=true
disabled: bean=false, conditionMatch=false
```

Maven Surefire có thể thu thập stdout của test vào báo cáo riêng thay vì hiển thị nguyên văn trên console; điều đó không thay đổi assertion. Khi hai test đều qua, Maven báo `BUILD SUCCESS`. Ngoài các dòng trên, logging listener ghi condition evaluation report ở mức `INFO`; định dạng, thứ tự và số lượng condition trong log phụ thuộc môi trường và phiên bản.

**Diễn giải:**

1. Test bật property: `FeatureAutoConfiguration` khớp condition, bean `featureService` được đăng ký; outcome là `true`.
2. Test tắt property: condition không khớp, bean không được đăng ký; outcome là `false`.
3. Mỗi test gọi `newRunner()`, do đó mỗi context có `ConditionEvaluationReportLoggingListener` mới.
4. Listener giúp nhìn lý do trong log; `assertThat(...)` và `outcome.isMatch()` mới là điều kiện để test thất bại khi hành vi sai.

## 7. Đọc report khi condition không khớp như dự kiến

Khi test báo thiếu bean, hãy đi theo thứ tự:

1. **Xác nhận auto-configuration đã được đưa vào runner.** Kiểm tra `AutoConfigurations.of(...)` hoặc cấu hình test đang sử dụng. Listener không tự thêm ứng viên.
2. **Kiểm tra property thực tế.** Dùng `context.getEnvironment().getProperty("demo.feature.enabled")` trong callback nếu condition phụ thuộc property. Chú ý giá trị, profile và property source.
3. **Kiểm tra classpath.** Nếu điều kiện dùng `@ConditionalOnClass`, xem dependency runtime/test và thử `FilteredClassLoader` để mô phỏng thiếu class.
4. **Kiểm tra bean người dùng.** `@ConditionalOnMissingBean` có thể back off khi đã có bean phù hợp. Xem `withUserConfiguration(...)` và các bean được đăng ký qua `withBean(...)`.
5. **Đọc condition message.** Xem source nào được ghi trong report, condition nào matched/unmatched và message cụ thể.
6. **Kiểm tra bean thực tế bằng assertion.** Report giải thích condition; assertion xác nhận kết quả context.

Ví dụ, nếu report ghi `OnClassCondition` không tìm thấy class yêu cầu, hãy kiểm dependency/classpath trước. Nếu report ghi `OnBeanCondition` không tìm thấy bean, kiểm tra thứ tự auto-configuration, tên/kiểu bean và cấu hình người dùng. Nếu report ghi `OnPropertyCondition` không khớp, kiểm property đầy đủ và `havingValue`.

### 7.1. Mô phỏng class bị thiếu bằng FilteredClassLoader

Spring Boot có `FilteredClassLoader` để kiểm tra auto-configuration khi một class hoặc package không có trên classpath:

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(MyLibraryAutoConfiguration.class)
    )
    .withClassLoader(
        new FilteredClassLoader(MyLibraryClient.class)
    )
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
    )
    .run(context -> {
        assertThat(context).doesNotHaveBean("myLibraryClient");
    });
```

Đây là snippet minh họa; `MyLibraryClient` và `MyLibraryAutoConfiguration` cần tồn tại. Test này kiểm tra đúng trường hợp thiếu class, hữu ích cho starter có dependency tùy chọn. Nếu cần kiểm thử class/package bị thiếu, hãy cân nhắc dùng tên chuỗi trong điều kiện class và cô lập các method bean tham chiếu trực tiếp tới class tùy chọn theo hướng dẫn Spring Boot.

### 7.2. Khi cần web context

`ApplicationContextRunner` tạo context non-web. Nếu auto-configuration chỉ hoạt động trong môi trường web:

- Dùng `WebApplicationContextRunner` cho Servlet/MVC.
- Dùng `ReactiveWebApplicationContextRunner` cho WebFlux/reactive.

Listener vẫn có thể được thêm qua `withInitializer(...)` vì nó triển khai `ApplicationContextInitializer<ConfigurableApplicationContext>`. Hãy test đúng loại context mà auto-configuration mong đợi; nếu dùng runner non-web cho điều kiện web, condition có thể không khớp đúng như ứng dụng thật.

## 8. Condition report trong test và trong ứng dụng thật

Trong ứng dụng Spring Boot đầy đủ, có thể bật debug mode khi khởi chạy để xem báo cáo điều kiện:

```bash
java -jar app.jar --debug
```

Hoặc thiết lập `debug=true` trong cấu hình phù hợp. Spring Boot sẽ bật thêm một số logger chọn lọc, trong đó có report về điều kiện auto-configuration. Không hiểu debug mode là bật toàn bộ logger ở mức DEBUG cho mọi thư viện.

Nếu ứng dụng có Spring Boot Actuator và endpoint được bật/expose phù hợp, endpoint `/actuator/conditions` cung cấp report dạng HTTP/JSON cho condition evaluation của context. Đây là cách quan sát khi ứng dụng đang chạy; `ConditionEvaluationReportLoggingListener` là cách ghi report vào log trong kiểm thử context.

| Cách quan sát | Môi trường phù hợp | Kết quả |
| --- | --- | --- |
| `ConditionEvaluationReportLoggingListener` | `ApplicationContextRunner` / test context | Ghi report vào log ở INFO hoặc DEBUG |
| `ConditionEvaluationReport` API | Test callback hoặc code chẩn đoán nội bộ | Đọc outcome có cấu trúc, source và exclusions |
| `--debug` | Ứng dụng Spring Boot khi khởi chạy | Bật báo cáo condition và một số logger debug được chọn |
| Actuator `/actuator/conditions` | Ứng dụng có Actuator và endpoint được expose | Report điều kiện qua HTTP/JSON |

Không bật endpoint điều kiện công khai tùy tiện trong production. Endpoint có thể tiết lộ tên class, cấu hình và chi tiết hạ tầng; chỉ expose theo chính sách quản trị và bảo mật của ứng dụng.

## 9. Giới hạn và lỗi thường gặp

### 9.1. Không thấy report trong log

Nguyên nhân thường gặp:

- Listener dùng mặc định `DEBUG` nhưng logging backend không hiển thị DEBUG.
- Dùng `forLogLevel(LogLevel.INFO)` nhưng logger đang bị lọc ở WARN/ERROR.
- Test không chạy auto-configuration có condition, hoặc report chưa có nội dung cần quan sát.
- Listener không được thêm vào runner đang thực thi; bạn đã cấu hình một runner khác.
- Logging backend trong test khác với logging backend khi chạy ứng dụng.

Cách xử lý: gắn listener trực tiếp vào runner của test, chọn `INFO`, và kiểm cấu hình logger. Không cần thay đổi condition chỉ vì log chưa xuất hiện.

### 9.2. Dùng log để thay assertion

Log chỉ cung cấp thông tin chẩn đoán. Test cần `assertThat(context).hasBean(...)`, `doesNotHaveBean(...)`, `hasSingleBean(...)` hoặc assertion về outcome. Nếu chỉ xem log thủ công, thay đổi hành vi có thể lọt qua CI.

### 9.3. Dùng một listener cho nhiều context

Javadoc cảnh báo không chia sẻ listener instance. Hãy tạo listener mới trong factory method của runner hoặc trực tiếp trong từng test. Đừng lưu một instance static để gắn vào nhiều context.

### 9.4. Truyền log level không được hỗ trợ

Trong Boot 3.3, `forLogLevel` được triển khai cho `INFO` hoặc `DEBUG`. Đừng truyền `WARN`, `ERROR` hoặc `TRACE` rồi mong listener chuyển report sang mức đó. Chọn `INFO`/`DEBUG` và cấu hình backend tương ứng.

### 9.5. Nhầm report với toàn bộ trace khởi động

Report ghi lại condition evaluation mà Spring Boot thu thập được. Nó không phải trace cho mọi dòng Java, không phải dependency tree, không phải lịch sử tạo instance bean và không thay thế exception stack trace. Với custom condition không ghi outcome theo cơ chế Spring Boot, report có thể không cung cấp thông điệp chi tiết như các condition tích hợp.

### 9.6. Đọc report sau khi runner đã đóng context

Callback của `run(...)` là nơi phù hợp để kiểm tra report. Hãy đọc report bên trong callback, khi context vẫn còn hoạt động. Không lưu `BeanFactory` hoặc đối tượng report để dùng như dữ liệu sống sau khi context đã đóng.

### 9.7. Chỉ test một property

Auto-configuration thường phụ thuộc nhiều trục. Với một starter thực tế, hãy tạo ma trận test:

- Class dependency có mặt/không có.
- Property bật/tắt/thiếu.
- Bean người dùng đã có/chưa có.
- Web/non-web context nếu có điều kiện web.
- Cấu hình tùy chỉnh hoặc default back off.

Mỗi test nên có assertion cho kết quả và dùng listener để chẩn đoán khi outcome không như mong đợi.

## 10. Quy trình thực hành đề xuất

1. Tạo một `ApplicationContextRunner` cơ sở chỉ chứa auto-configuration cần test.
2. Mỗi kịch bản tạo runner/context mới; gắn listener mới với `forLogLevel(LogLevel.INFO)` khi muốn report dễ thấy.
3. Thiết lập property, user configuration và classloader theo một tình huống cụ thể.
4. Trong callback, assertion bean và trạng thái context trước.
5. Khi cần giải thích condition, đọc `ConditionEvaluationReport` qua bean factory và in/kiểm `ConditionOutcome`.
6. Tạo test cho trường hợp condition khớp và không khớp; thêm test back off khi ứng dụng cung cấp bean tùy chỉnh.
7. Khi test fail, dùng report để tìm condition đầu tiên không đạt yêu cầu, sửa nguyên nhân và giữ assertion để ngăn hồi quy.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `ConditionEvaluationReportLoggingListener` triển khai interface nào và được thêm vào `ApplicationContextRunner` bằng API nào?  
**Đáp án:** Nó triển khai `ApplicationContextInitializer<ConfigurableApplicationContext>`; thêm bằng `withInitializer(...)`.

**Câu 2.** Constructor không tham số của listener dùng log level nào trong Spring Boot 3.3?  
**Đáp án:** `DEBUG`. Có thể dùng `forLogLevel(LogLevel.INFO)` để ghi report ở INFO.

**Câu 3.** Có thể dùng cùng một listener instance cho mười lần `ApplicationContextRunner.run(...)` không?  
**Đáp án:** Không nên. Javadoc nói listener không được thiết kế để dùng chung cho nhiều ApplicationContext; tạo listener mới cho mỗi context.

**Câu 4.** Listener có tự động đưa auto-configuration vào context không?  
**Đáp án:** Không. `AutoConfigurations.of(...)` hoặc cơ chế cấu hình runner quyết định lớp nào được test; listener chỉ ghi report.

**Câu 5.** `ConditionOutcome.isMatch()` là true thì có bảo đảm bean cuối cùng đã được khởi tạo thành công không?  
**Đáp án:** Không. Nó chỉ cho biết condition tương ứng matched. Vẫn cần assertion bean, và quá trình khởi tạo bean có thể thất bại vì dependency hoặc exception khác.

**Câu 6.** Muốn kiểm tra dữ liệu report có cấu trúc, dùng API nào?  
**Đáp án:** `ConditionEvaluationReport.get(context.getBeanFactory())` rồi đọc `getConditionAndOutcomesBySource()`, `getExclusions()` và `getUnconditionalClasses()`. Nếu chỉ muốn tìm report hiện có, dùng `find(beanFactory)`.

**Câu 7.** Vì sao không nên assert nguyên văn toàn bộ log report?  
**Đáp án:** Định dạng log và condition message có thể thay đổi theo phiên bản, logger và môi trường. Nên assert hành vi bean và outcome boolean; chỉ assert message khi đó thực sự là hợp đồng ổn định của test.

**Câu 8.** Test auto-configuration chỉ chạy trong Servlet context nên dùng runner nào?  
**Đáp án:** `WebApplicationContextRunner`. Với WebFlux dùng `ReactiveWebApplicationContextRunner`.

## 12. Ghi nhớ và tài liệu tham khảo

- `ConditionEvaluationReport` là **dữ liệu** ghi nhận condition evaluation.
- `ConditionEvaluationReportLoggingListener` là **initializer** ghi dữ liệu đó ra log; nó không thay đổi điều kiện.
- `ApplicationContextRunner` tạo context cô lập và cho phép thêm listener bằng `withInitializer(...)`.
- Spring Boot 3.3: constructor mặc định log DEBUG; `forLogLevel` dùng INFO hoặc DEBUG; không chia sẻ listener giữa nhiều context.
- Log report để **chẩn đoán**, assertion để **kiểm chứng hành vi**.
- Đọc report bằng `ConditionEvaluationReport.get(beanFactory)` khi cần outcome có cấu trúc; thao tác trong callback của runner.
- Test từng trường hợp property, classpath, user bean và loại context mà auto-configuration phụ thuộc.

Tài liệu chính thức:

1. Spring Boot 3.3.13 — [`ConditionEvaluationReportLoggingListener` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html).
2. Spring Boot 3.3.13 — [Creating Your Own Auto-configuration, mục Testing your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
3. Spring Boot 3.3.13 — [`ApplicationContextRunner` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
4. Spring Boot 3.3.13 — [`ConditionEvaluationReport` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html).
5. Spring Boot 3.3.13 — [`ConditionEvaluationReport.ConditionAndOutcome` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcome.html).
6. Spring Boot 3.3.13 — [`Conditions Evaluation Report` Actuator API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html).
