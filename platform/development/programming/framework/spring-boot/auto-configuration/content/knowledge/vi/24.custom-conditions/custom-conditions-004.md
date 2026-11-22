# Tạo ConditionMessage và thông báo thiếu điều kiện cụ thể

## 1. Vì sao custom condition cần thông báo rõ ràng?

Auto-configuration thường chỉ đăng ký bean khi nhiều điều kiện cùng thỏa mãn: property được bật, thư viện tùy chọn có trên classpath, một bean prerequisite đã tồn tại hoặc ứng dụng đang chạy đúng loại context. Khi một điều kiện không đạt, bean có thể không xuất hiện dù ứng dụng vẫn khởi động bình thường.

Một thông báo chung như:

~~~text
Condition did not match
~~~

không giúp người phát triển biết cần sửa gì. Một thông báo tốt cần chỉ ra **điều kiện nào đang thiếu**, chẳng hạn:

~~~text
Acme Reports readiness did not find required prerequisites
'property acme.reports.enabled is not set',
'non-blank property acme.reports.endpoint',
'class com.example.sdk.ReportSdk on the runtime classpath'
~~~

Người đọc có thể hành động ngay: bật property, khai báo endpoint hoặc thêm dependency chứa SDK.

Spring Boot cung cấp ba thành phần phối hợp để làm việc này:

- **ConditionMessage**: tạo câu mô tả kết quả theo một format nhất quán.
- **ConditionOutcome**: mang kết quả match/no-match cùng thông báo.
- **SpringBootCondition**: lớp nền để viết condition tùy chỉnh theo cách Spring Boot ghi log và lưu kết quả vào Condition Evaluation Report.

Bài dùng **Java 17 và Spring Boot 3.3.13** làm baseline minh họa. Hãy căn chỉnh version với release line thật của ứng dụng khi áp dụng.

## 2. Phân biệt Condition, ConditionMessage, ConditionOutcome và ConditionEvaluationReport

Các API này có trách nhiệm khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| Condition | Contract của Spring để quyết định một cấu hình có được áp dụng không |
| SpringBootCondition | Lớp nền Spring Boot, hỗ trợ ghi log và lưu kết quả condition |
| ConditionMessage | Nội dung giải thích vì sao điều kiện khớp hoặc không khớp |
| ConditionOutcome | Kết quả boolean match hoặc noMatch, kèm ConditionMessage |
| ConditionEvaluationReport | Tập hợp kết quả của các condition theo class hoặc bean method |

Một ConditionMessage **không tự quyết định** bean có được tạo hay không. Boolean trong ConditionOutcome mới quyết định điều đó. Message giải thích kết quả cho log và báo cáo.

Luồng khái quát:

~~~text
Spring gặp @Conditional(MyCondition.class)
                  |
                  v
SpringBootCondition.getMatchOutcome(...)
                  |
          +-------+-------+
          |               |
          v               v
ConditionOutcome.match   ConditionOutcome.noMatch
          |               |
          +-------+-------+
                  |
                  v
ConditionEvaluationReport lưu outcome
                  |
                  v
Log / --debug / Actuator conditions
~~~

Nếu custom condition trả noMatch, bean method hoặc configuration được gắn condition sẽ không được áp dụng. Spring Boot vẫn có thể khởi động bình thường nếu không có dependency bắt buộc nào khác gây lỗi.

## 3. ConditionMessage API

Class nằm trong package:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionMessage
~~~

ConditionMessage cung cấp fluent builder để tạo câu giải thích. Một số factory/method thường dùng:

| API | Mục đích |
| --- | --- |
| ConditionMessage.forCondition(...) | Bắt đầu message cho một condition |
| ConditionMessage.of(...) | Tạo message trực tiếp từ chuỗi/format |
| builder.foundExactly(...) | Mô tả một kết quả cụ thể đã tìm thấy |
| builder.found(...) | Mô tả một hoặc nhiều item đã tìm thấy |
| builder.didNotFind(...) | Mô tả item hoặc prerequisite không tìm thấy |
| items(...) | Đưa danh sách item vào message |
| atAll() | Diễn tả không tìm thấy item nào |
| because(...) | Nêu lý do cụ thể |
| available(...) / notAvailable(...) | Diễn tả trạng thái khả dụng |

### 3.1. Bắt đầu bằng forCondition

Ví dụ:

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition("Acme Reports");
~~~

Có thể dùng tên condition dạng chuỗi để đặt nhãn dễ đọc. Cũng có overload nhận annotation class:

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition(ConditionalOnProperty.class);
~~~

Overload class phù hợp khi message giải thích một annotation condition cụ thể. Với custom condition không có annotation riêng, tên chuỗi như "Acme Reports readiness" thường rõ nghĩa hơn.

Có thể truyền thêm chi tiết:

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition(
                "Acme Reports readiness", "acme.reports");
~~~

### 3.2. Dùng didNotFind để nêu điều kiện thiếu

Nếu thiếu một prerequisite:

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .didNotFind("required bean")
        .items(ConditionMessage.Style.QUOTE, "reportTransport");
~~~

Nếu thiếu nhiều prerequisite:

~~~java
List<String> missing = List.of(
        "acme.reports.enabled must be true",
        "non-blank property acme.reports.endpoint");

ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports readiness")
        .didNotFind("required prerequisite", "required prerequisites")
        .items(ConditionMessage.Style.QUOTE, missing);
~~~

Style.QUOTE giúp phân biệt các item trong danh sách. didNotFind(singular, plural) cho phép builder chọn cách diễn đạt số ít/số nhiều.

Nếu không có item nào:

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .didNotFind("required class")
        .atAll();
~~~

### 3.3. Dùng found khi prerequisite đã có

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .found("required class", "required classes")
        .items(
                ConditionMessage.Style.QUOTE,
                "com.example.sdk.ReportSdk",
                "com.example.sdk.ReportTransport");
~~~

Hoặc với một kết quả đơn:

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .foundExactly("all required prerequisites");
~~~

### 3.4. Dùng because cho lý do

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .because("the endpoint property is blank");
~~~

Thông báo này hữu ích khi cần mô tả nguyên nhân hoặc trạng thái cụ thể, không chỉ liệt kê item thiếu.

### 3.5. ConditionMessage.of cho thông báo đơn giản

~~~java
ConditionMessage message = ConditionMessage.of(
        "property '%s' must be set",
        "acme.reports.endpoint");
~~~

Cách này phù hợp với một câu đơn giản. Khi có nhiều prerequisite, builder thường dễ mở rộng và nhất quán hơn.

## 4. ConditionOutcome quyết định match hay no-match

ConditionOutcome nằm trong package:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionOutcome
~~~

Tạo kết quả match:

~~~java
return ConditionOutcome.match(message);
~~~

Tạo kết quả không match:

~~~java
return ConditionOutcome.noMatch(message);
~~~

Có overload nhận chuỗi, nhưng khi đã tạo ConditionMessage, hãy truyền trực tiếp object đó:

~~~java
ConditionOutcome.noMatch(
        ConditionMessage.of("required endpoint is missing"));
~~~

Không nên chỉ trả ConditionOutcome.noMatch() với message rỗng nếu mục tiêu là giúp người dùng chẩn đoán. Một custom condition nên trả lý do đủ cụ thể để người đọc biết property, class hoặc prerequisite nào cần bổ sung.

## 5. Vì sao nên extends SpringBootCondition?

Spring Framework định nghĩa interface Condition với method:

~~~java
boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata);
~~~

Nếu triển khai trực tiếp interface này, method chỉ trả boolean. Không có chỗ chuẩn để trả ConditionOutcome chứa message.

Spring Boot cung cấp abstract class:

~~~java
org.springframework.boot.autoconfigure.condition.SpringBootCondition
~~~

Custom condition kế thừa class này và implement:

~~~java
@Override
public ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata) {
    // Kiểm tra prerequisite và trả match/noMatch kèm message.
}
~~~

Spring Boot quản lý phần tích hợp condition với log và Condition Evaluation Report. Vì vậy, khi cần diagnostic message cho custom condition, hãy ưu tiên SpringBootCondition.

Không tự ghi System.out.println, không log thủ công rồi trả boolean. Làm vậy khiến thông tin khó gắn với kết quả condition, có thể bị lặp và không xuất hiện đúng cấu trúc trong báo cáo.

## 6. Ví dụ custom condition: liệt kê tất cả prerequisite còn thiếu

Ta xây một auto-configuration tạo ReportClient khi thỏa ba điều kiện:

1. acme.reports.enabled=true.
2. acme.reports.endpoint có giá trị khác rỗng.
3. Class tùy chọn com.example.sdk.ReportSdk có trên runtime classpath.

Mục tiêu là nếu thiếu nhiều điều kiện cùng lúc, report phải liệt kê **tất cả nguyên nhân** thay vì chỉ báo điều kiện đầu tiên.

### 6.1. Cấu trúc project

~~~text
condition-message-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/reports/
    │       ├── ReportClient.java
    │       └── autoconfigure/
    │           ├── ReportsAutoConfiguration.java
    │           └── ReportsReadyCondition.java
    └── test/
        └── java/
            ├── com/example/reports/autoconfigure/
            │   └── ReportsReadyConditionTests.java
            └── com/example/sdk/
                └── ReportSdk.java
~~~

Class ReportSdk chỉ là test fixture mô phỏng SDK tùy chọn. Trong thư viện thật, class đó nằm trong dependency bên ngoài và có thể không xuất hiện trong runtime classpath.

### 6.2. pom.xml

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>condition-message-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

Spring Boot parent quản lý version của spring-boot-autoconfigure. Starter test cung cấp JUnit, AssertJ, ApplicationContextRunner và FilteredClassLoader.

### 6.3. ReportClient.java

**src/main/java/com/example/reports/ReportClient.java**

~~~java
package com.example.reports;

public record ReportClient(String endpoint) {
}
~~~

Bean chỉ giữ endpoint để minh họa kết quả auto-configuration; không gửi request mạng.

### 6.4. ReportsReadyCondition.java

**src/main/java/com/example/reports/autoconfigure/ReportsReadyCondition.java**

~~~java
package com.example.reports.autoconfigure;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.ConditionMessage.Style;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
import org.springframework.util.ClassUtils;
import org.springframework.util.StringUtils;

public final class ReportsReadyCondition extends SpringBootCondition {

    private static final String ENABLED_PROPERTY =
            "acme.reports.enabled";

    private static final String ENDPOINT_PROPERTY =
            "acme.reports.endpoint";

    private static final String SDK_CLASS =
            "com.example.sdk.ReportSdk";

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        List<String> missing = new ArrayList<>();

        String enabled = context.getEnvironment()
                .getProperty(ENABLED_PROPERTY);

        if (!"true".equalsIgnoreCase(enabled)) {
            if (enabled == null) {
                missing.add(
                        "property " + ENABLED_PROPERTY + " is not set");
            }
            else {
                missing.add(
                        "property " + ENABLED_PROPERTY + " must be true");
            }
        }

        String endpoint = context.getEnvironment()
                .getProperty(ENDPOINT_PROPERTY);

        if (!StringUtils.hasText(endpoint)) {
            missing.add(
                    "non-blank property " + ENDPOINT_PROPERTY);
        }

        if (!ClassUtils.isPresent(SDK_CLASS, context.getClassLoader())) {
            missing.add(
                    "class " + SDK_CLASS + " on the runtime classpath");
        }

        ConditionMessage.Builder message =
                ConditionMessage.forCondition("Acme Reports readiness");

        if (!missing.isEmpty()) {
            ConditionMessage details = message
                    .didNotFind(
                            "required prerequisite",
                            "required prerequisites")
                    .items(Style.QUOTE, missing);

            return ConditionOutcome.noMatch(details);
        }

        ConditionMessage details =
                message.foundExactly("all required prerequisites");

        return ConditionOutcome.match(details);
    }
}
~~~

Cách hoạt động:

- Đọc property qua Environment, không khởi động service hoặc tạo bean trong condition.
- Dùng StringUtils.hasText để coi null, chuỗi rỗng và chuỗi chỉ có khoảng trắng là thiếu endpoint.
- Dùng ClassUtils.isPresent với class name dạng String để kiểm tra dependency tùy chọn mà không tạo compile-time reference tới SDK.
- Gom mọi lý do vào danh sách missing.
- Nếu danh sách có phần tử, tạo message bằng didNotFind(...).items(...) và trả ConditionOutcome.noMatch.
- Nếu không thiếu điều kiện, trả ConditionOutcome.match với message xác nhận.

Vì condition không tham chiếu trực tiếp ReportSdk.class, thư viện vẫn có thể compile khi SDK tùy chọn không nằm trong dependency compile-time. Đây là cách phù hợp khi class được kiểm tra có thể vắng mặt ở runtime.

### 6.5. ReportsAutoConfiguration.java

**src/main/java/com/example/reports/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.reports.autoconfigure;

import com.example.reports.ReportClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.core.env.Environment;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @Conditional(ReportsReadyCondition.class)
    ReportClient reportClient(Environment environment) {
        return new ReportClient(
                environment.getRequiredProperty("acme.reports.endpoint"));
    }
}
~~~

Conditional gắn custom condition vào bean method. Nếu condition trả noMatch, method reportClient không đăng ký bean.

Environment được inject vào method chỉ sau khi condition đã match. getRequiredProperty giúp phát hiện cấu hình thiếu nếu có thay đổi ngoài dự kiến giữa lúc đánh giá condition và tạo bean.

## 7. Xem message trong Condition Evaluation Report

Spring Boot ghi condition outcome theo nguồn, thường là tên configuration class hoặc bean method. Trong ví dụ này, source của method có dạng:

~~~text
com.example.reports.autoconfigure.ReportsAutoConfiguration#reportClient
~~~

Nếu thiếu property và SDK, phần Negative matches sẽ có message liệt kê các prerequisite chưa thỏa. Câu chữ được format bởi ConditionMessage; không nên phụ thuộc vào toàn bộ chuỗi punctuation trong một phiên bản cụ thể.

Ví dụ minh họa ý nghĩa:

~~~text
Negative matches:
   ReportsAutoConfiguration#reportClient
      - ReportsReadyCondition:
        Acme Reports readiness did not find required prerequisites
        'property acme.reports.enabled is not set',
        'non-blank property acme.reports.endpoint'
~~~

Nếu SDK cũng không có, danh sách sẽ bổ sung:

~~~text
'class com.example.sdk.ReportSdk on the runtime classpath'
~~~

Đây là output minh họa rút gọn. Nội dung thực tế còn phụ thuộc cách report logger render và version Spring Boot.

### 7.1. Bật report khi chạy ứng dụng

Để xem toàn bộ quyết định auto-configuration:

~~~bash
java -jar target/condition-message-demo-1.0.0.jar --debug
~~~

Hoặc:

~~~properties
debug=true
~~~

ConditionMessage vẫn được tạo và condition vẫn được đánh giá khi không bật debug. Debug mode giúp hiển thị báo cáo condition trong log khởi động.

### 7.2. In report ở test bằng ConditionEvaluationReportLoggingListener

Spring Boot có listener để in report ngay trong test:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            // Assertions của test
        });
~~~

Cách này hữu ích khi điều tra vì sao condition không khớp. Không cần thêm log thủ công bên trong custom condition.

### 7.3. Đọc report qua Actuator

Nếu ứng dụng có Spring Boot Actuator và endpoint được expose phù hợp, có thể truy vấn:

~~~text
GET /actuator/conditions
~~~

Endpoint cung cấp báo cáo condition dưới dạng JSON. --debug không tự thêm Actuator dependency hoặc expose endpoint. Trong production, chỉ expose endpoint cần thiết và bảo vệ quyền truy cập.

## 8. Kiểm thử cả kết quả và nội dung thông báo

Test nên xác nhận hai việc:

1. Bean có hoặc không có đúng theo prerequisite.
2. Condition Evaluation Report chứa tên property/class cụ thể để người đọc biết phải sửa gì.

### 8.1. Test fixture cho SDK tùy chọn

**src/test/java/com/example/sdk/ReportSdk.java**

~~~java
package com.example.sdk;

public final class ReportSdk {
}
~~~

Class này có trong test runtime classpath nên test positive có thể thỏa điều kiện SDK. Một test khác sẽ dùng FilteredClassLoader để mô phỏng SDK bị thiếu.

### 8.2. ReportsReadyConditionTests.java

**src/test/java/com/example/reports/autoconfigure/ReportsReadyConditionTests.java**

~~~java
package com.example.reports.autoconfigure;

import java.util.ArrayList;
import java.util.List;

import com.example.reports.ReportClient;
import com.example.sdk.ReportSdk;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.util.FilteredClassLoader;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsReadyConditionTests {

    private static final String CONDITION_SOURCE =
            ReportsAutoConfiguration.class.getName() + "#reportClient";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void createsClientWhenEveryPrerequisiteIsPresent() {
        runner.withPropertyValues(
                "acme.reports.enabled=true",
                "acme.reports.endpoint=https://reports.example.test")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://reports.example.test");

                    assertThat(conditionMessages(context))
                            .anyMatch(message ->
                                    message.contains(
                                            "all required prerequisites"));
                });
    }

    @Test
    void listsEveryMissingPrerequisite() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(ReportClient.class);

            String messages = String.join("\n", conditionMessages(context));

            assertThat(messages)
                    .contains("acme.reports.enabled")
                    .contains("acme.reports.endpoint");
        });
    }

    @Test
    void explainsWhenEnabledPropertyIsFalse() {
        runner.withPropertyValues(
                "acme.reports.enabled=false",
                "acme.reports.endpoint=https://reports.example.test")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);

                    String messages =
                            String.join("\n", conditionMessages(context));

                    assertThat(messages)
                            .contains("acme.reports.enabled")
                            .contains("must be true");
                });
    }

    @Test
    void explainsWhenOptionalSdkIsMissing() {
        runner.withPropertyValues(
                "acme.reports.enabled=true",
                "acme.reports.endpoint=https://reports.example.test")
                .withClassLoader(new FilteredClassLoader(ReportSdk.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);

                    String messages =
                            String.join("\n", conditionMessages(context));

                    assertThat(messages)
                            .contains("com.example.sdk.ReportSdk");
                });
    }

    private List<String> conditionMessages(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(
                        context.getSourceApplicationContext().getBeanFactory());

        ConditionAndOutcomes outcomes =
                report.getConditionAndOutcomesBySource()
                        .get(CONDITION_SOURCE);

        assertThat(outcomes).isNotNull();

        List<String> messages = new ArrayList<>();

        for (ConditionAndOutcome item : outcomes) {
            messages.add(item.getOutcome().getMessage());
        }

        return messages;
    }
}
~~~

Các test lấy report từ bean factory của context và đọc outcome tại đúng bean method. Cách này kiểm tra nội dung message do condition trả về, thay vì chỉ xác nhận bean không tồn tại.

### 8.3. Chạy test

~~~bash
mvn clean test
~~~

Kỳ vọng **bốn test pass**:

| Test | Kết quả mong đợi |
| --- | --- |
| Đủ property và SDK | Có đúng một ReportClient |
| Thiếu property | Không có bean; message liệt kê enabled và endpoint |
| enabled=false | Không có bean; message nói enabled phải là true |
| Thiếu SDK | Không có bean; message nêu tên class SDK |

Nếu test không tìm thấy report source, kiểm tra source key có đúng tên đầy đủ của configuration class cộng #reportClient không. Nếu bean tồn tại trong trường hợp thiếu prerequisite, kiểm tra Conditional đã đặt đúng trên method và runner có nạp đúng auto-configuration không.

## 9. Kết hợp ConditionMessage với built-in conditions

Không nên viết custom condition cho mọi trường hợp. Spring Boot đã cung cấp condition phổ biến với thông báo hữu ích:

| Nhu cầu | Annotation nên ưu tiên |
| --- | --- |
| Một class phải có trên classpath | @ConditionalOnClass |
| Một property phải có/đúng giá trị | @ConditionalOnProperty |
| Một bean phải tồn tại | @ConditionalOnBean |
| Chưa có bean thì tạo default | @ConditionalOnMissingBean |
| Chỉ chạy trong servlet/reactive web context | @ConditionalOnWebApplication |
| Chỉ chạy khi resource tồn tại | @ConditionalOnResource |
| Chỉ chạy với một candidate có thể xác định | @ConditionalOnSingleCandidate |

Ví dụ dùng built-in condition:

~~~java
@Bean
@ConditionalOnClass(ReportSdk.class)
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@ConditionalOnMissingBean(ReportClient.class)
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

Các annotation này đã tạo message riêng cho class/property/bean. Nếu nhu cầu chỉ là kiểm tra từng điều kiện chuẩn, không cần custom SpringBootCondition.

Custom condition hữu ích khi:

- Một quy tắc kết hợp nhiều prerequisite và muốn báo cáo tất cả mục còn thiếu.
- Điều kiện cần phép kiểm tra chuyên biệt không có annotation tương ứng.
- Cần một lý do nghiệp vụ rõ ràng cho quyết định match/no-match.
- Cần kiểm tra trạng thái tổng hợp từ Environment và classpath.

Nếu chỉ cần kiểm tra nhiều condition độc lập, có thể gắn nhiều annotation built-in thay vì viết một condition lớn. Điều đó thường giúp report chỉ ra chính xác annotation nào không khớp.

## 10. Viết diagnostic message có chất lượng

Một thông báo tốt nên tuân theo các nguyên tắc sau.

### 10.1. Nêu tên đầy đủ của prerequisite

Tốt:

~~~text
property acme.reports.endpoint is not set
~~~

Kém:

~~~text
configuration missing
~~~

Với class, dùng fully qualified class name để người dùng biết dependency nào cần tìm.

### 10.2. Nêu trạng thái và hành động cần làm

Tốt:

~~~text
property acme.reports.enabled must be true
~~~

Kém:

~~~text
feature unavailable
~~~

Thông báo nên chỉ ra trạng thái mong đợi, không chỉ lặp lại tên feature.

### 10.3. Báo tất cả điều kiện thiếu khi điều đó hữu ích

Nếu một condition có ba prerequisite độc lập, gom chúng vào danh sách để người dùng sửa một lượt. Tuy nhiên, nếu điều kiện sau chỉ có ý nghĩa khi điều kiện trước đã đúng, có thể trả nguyên nhân đầu tiên để tránh message gây hiểu lầm.

### 10.4. Không tiết lộ secret

Không đưa password, token, API key hoặc giá trị cấu hình nhạy cảm vào ConditionMessage. Hãy ghi tên property và trạng thái:

~~~text
property acme.reports.api-key is not set
~~~

Không ghi nội dung API key đang có trong Environment. Condition report có thể xuất hiện trong log, endpoint quản trị hoặc hệ thống thu thập log.

### 10.5. Giữ message ổn định nhưng không kiểm thử cả câu dài

Message là công cụ chẩn đoán, không nên trở thành API máy đọc trừ khi thư viện chủ động cam kết điều đó. Test nên xác nhận các token quan trọng như property key, class name và reason, thay vì so sánh nguyên văn toàn bộ câu có thể thay đổi theo format của Spring Boot.

## 11. Những điều không nên làm trong custom condition

Condition có thể được đánh giá trong quá trình xử lý configuration và có thể chạy nhiều lần tùy cấu trúc context. Vì vậy:

- Không tạo kết nối database, HTTP client hoặc thread trong condition.
- Không khởi tạo bean chỉ để kiểm tra bean có tồn tại.
- Không thực hiện thao tác ghi file, gọi API hoặc thay đổi trạng thái.
- Không dựa vào thứ tự bean instance đã được tạo.
- Không log raw Environment hoặc toàn bộ cấu hình có thể chứa secret.
- Không nuốt exception rồi trả match như thể mọi thứ hợp lệ.
- Không viết condition phức tạp nếu built-in annotations đã mô tả đủ quy tắc.

Ưu tiên các thao tác nhẹ, có thể lặp lại và không có side effect: đọc property, kiểm tra class bằng classloader, kiểm tra resource hoặc metadata bean theo đúng phase.

### 11.1. Tránh hard reference tới optional class

Nếu class là dependency bắt buộc của module, có thể dùng:

~~~java
@ConditionalOnClass(ReportSdk.class)
~~~

Nhưng nếu dependency là optional và class có thể vắng mặt, tránh import class đó trực tiếp trong một condition/configuration class có thể được JVM nạp trước khi condition chạy. Dùng tên class dạng String cùng ClassUtils.isPresent hoặc đặt condition trên một nested configuration tách biệt có thể tránh lỗi nạp class sớm.

### 11.2. Không biến thiếu điều kiện thành startup exception

Một condition không khớp thường có nghĩa bean không được đăng ký. Đây là hành vi bình thường nếu feature optional. Đừng ném exception chỉ để tạo một dòng log dễ thấy, trừ khi cấu hình thực sự vi phạm contract bắt buộc và ứng dụng phải dừng.

Nếu feature bắt buộc theo thiết kế, có thể dùng validation/configuration-properties validation hoặc một failure analyzer phù hợp để báo lỗi startup rõ ràng.

## 12. ConditionMessage và các công cụ chẩn đoán khác

| Công cụ | Câu hỏi nó trả lời |
| --- | --- |
| ConditionMessage | Vì sao custom condition match hoặc không match? |
| ConditionOutcome | Condition trả kết quả true hay false? |
| ConditionEvaluationReport | Những condition nào đã được đánh giá trong context? |
| --debug | Làm sao xem report trong log khởi động? |
| Actuator /actuator/conditions | Làm sao truy vấn report qua HTTP khi endpoint được expose? |
| Stack trace | Vì sao bean đã được đăng ký nhưng thất bại khi khởi tạo? |
| ApplicationContextRunner | Làm sao kiểm thử từng nhánh condition độc lập? |

Một condition có thể match nhưng bean vẫn lỗi ở constructor hoặc factory method. Khi đó đọc stack trace; message condition không thay thế chẩn đoán lỗi tạo bean.

Ngược lại, condition no-match không phải startup failure. Report chỉ giải thích vì sao Spring bỏ qua cấu hình hoặc bean.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ thấy boolean, không có lý do | Triển khai trực tiếp Condition.matches | Kế thừa SpringBootCondition và trả ConditionOutcome |
| Message có nhưng bean vẫn được tạo | Trả ConditionOutcome.match dù message nói thiếu | Dùng noMatch khi prerequisite chưa thỏa |
| Condition không xuất hiện trong report | Condition chưa được gắn qua @Conditional hoặc configuration không được nạp | Kiểm tra annotation và auto-configuration discovery |
| Message chỉ nói "not ready" | Không liệt kê property/class/bean cụ thể | Dùng didNotFind(...).items(...) |
| Chỉ báo thiếu một điều kiện dù còn nhiều điều kiện khác | Trả ngay khi gặp prerequisite đầu tiên | Gom các nguyên nhân độc lập vào danh sách |
| Optional dependency gây NoClassDefFoundError | Hard reference tới class có thể vắng mặt | Dùng tên class + ClassUtils.isPresent hoặc nested configuration |
| Report không được in trong test | Không bật listener hoặc log level phù hợp | Dùng ConditionEvaluationReportLoggingListener |
| Test bean absence pass nhưng message sai | Chỉ assertion bean, không đọc report | Assert ConditionEvaluationReport và message quan trọng |
| Log chứa API key/token | Ghi raw property value vào message | Chỉ ghi tên property và trạng thái |
| Condition gọi dịch vụ ngoài | Có side effect trong quá trình đánh giá | Chuyển kiểm tra runtime sang bean/service sau khi context tạo |
| Message thay đổi theo format version làm test fail | So sánh toàn bộ câu chữ | Assert các token ổn định: key, class, reason |
| Custom condition trùng built-in annotation | Tự viết lại logic phổ biến | Ưu tiên @ConditionalOnClass, @ConditionalOnProperty, @ConditionalOnBean |

## 14. Checklist review custom condition

Trước khi phát hành thư viện:

1. Dùng built-in condition nếu nó đã diễn đạt đủ quy tắc.
2. Nếu cần message tùy chỉnh, kế thừa SpringBootCondition.
3. Trả ConditionOutcome.match hoặc noMatch đúng với logic.
4. Tạo message bằng ConditionMessage.forCondition.
5. Liệt kê prerequisite thiếu bằng didNotFind(...).items(...).
6. Nêu full property key hoặc fully qualified class name.
7. Không đưa secret hoặc raw config nhạy cảm vào message.
8. Condition chỉ đọc trạng thái; không tạo side effect.
9. Kiểm tra cả nhánh match và no-match.
10. Đọc message từ ConditionEvaluationReport trong test.
11. Dùng --debug hoặc listener để kiểm tra report khi chạy.
12. Phân biệt condition no-match với exception khi bean khởi tạo.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** ConditionMessage có tự quyết định bean được đăng ký không?  
**Đáp án:** Không. ConditionOutcome mang kết quả match/no-match; ConditionMessage chỉ giải thích kết quả.

**Câu 2.** Vì sao custom condition của Spring Boot thường nên kế thừa SpringBootCondition?  
**Đáp án:** Lớp này cung cấp cơ chế tích hợp outcome vào log và Condition Evaluation Report. Custom condition có thể trả ConditionOutcome kèm message.

**Câu 3.** API nào dùng để liệt kê prerequisite không tìm thấy?  
**Đáp án:** ConditionMessage.forCondition(...).didNotFind(...).items(...).

**Câu 4.** Nếu cần báo nhiều property/class đang thiếu, nên làm gì?  
**Đáp án:** Gom các nguyên nhân độc lập vào một collection rồi đưa vào items, sau đó trả ConditionOutcome.noMatch.

**Câu 5.** Khi condition match, nên trả outcome nào?  
**Đáp án:** ConditionOutcome.match(message) với message mô tả prerequisite đã thỏa.

**Câu 6.** Làm sao tránh NoClassDefFoundError khi dependency là optional?  
**Đáp án:** Không hard reference class tùy chọn trong code bị nạp sớm; kiểm tra bằng tên class và ClassUtils.isPresent hoặc dùng nested configuration phù hợp.

**Câu 7.** Có nên ghi API key vào ConditionMessage để tiện debug không?  
**Đáp án:** Không. Message có thể đi vào log/report; chỉ ghi tên property và trạng thái, không ghi giá trị secret.

**Câu 8.** Làm sao kiểm thử message do custom condition tạo ra?  
**Đáp án:** Dùng ApplicationContextRunner, lấy ConditionEvaluationReport từ bean factory, tìm source class/method và assert các token quan trọng trong outcome message.

**Ghi nhớ:** Một custom condition tốt trả lời hai câu hỏi: **có match không** và **nếu không, đang thiếu điều gì**. Kế thừa SpringBootCondition, tạo ConditionMessage bằng builder, trả ConditionOutcome chính xác và kiểm thử message trong ConditionEvaluationReport. Ưu tiên built-in conditions cho quy tắc phổ biến; chỉ viết custom condition khi cần logic tổng hợp hoặc diagnostic cụ thể hơn.

## 16. Tài liệu tham khảo chính thức

- [ConditionMessage — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html)
- [ConditionOutcome — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html)
- [SpringBootCondition — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html)
- [ConditionEvaluationReport — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Creating Your Own Auto-configuration — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Conditions Evaluation Report — Spring Boot Actuator 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
