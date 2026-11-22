# Viết điều kiện tổ hợp và kiểm tra thông điệp cho từng nhánh

## 1. Vì sao cần condition tổ hợp?

Một auto-configuration thực tế thường phụ thuộc đồng thời vào nhiều điều kiện. Ví dụ, một search gateway chỉ nên được đăng ký khi:

- Feature search được bật.
- Ứng dụng đã chọn một region được hỗ trợ.
- Có ít nhất một transport được bật: HTTP **hoặc** JMS.
- Chế độ legacy không được bật.

Nếu viết mỗi condition trên một bean method hoặc lặp lại nhiều annotation ở nhiều nơi, cấu hình dễ bị phân tán. Khi một nhánh không khớp, người phát triển cũng khó biết điều kiện nào đã làm auto-configuration bị bỏ qua.

Spring Boot cung cấp ba lớp condition tổ hợp:

- **AllNestedConditions** — AND: tất cả condition con phải khớp.
- **AnyNestedCondition** — OR: ít nhất một condition con phải khớp.
- **NoneNestedConditions** — NOR/NOT: không condition con nào được khớp.

Ngoài kết quả boolean, Spring Boot còn có **ConditionOutcome** và **ConditionMessage** để giải thích vì sao một condition khớp hoặc không khớp. Bài này kết hợp cả hai phần: viết điều kiện tổ hợp, sau đó đọc và kiểm thử thông điệp của từng nhánh.

Phạm vi ví dụ: **Spring Boot 3.3.13, Spring Framework 6.1 và Java 17+**. Sau bài học, bạn có thể:

1. Biểu diễn AND, OR và NOT bằng nested conditions.
2. Chọn đúng ConfigurationPhase cho các condition con.
3. Đóng gói condition tổ hợp thành annotation dùng lại.
4. Tạo thông điệp match/no-match riêng cho từng nhánh bằng SpringBootCondition.
5. Đọc ConditionEvaluationReport để tìm condition con đã khớp hoặc thất bại.
6. Viết test cho từng nhánh, bao gồm cả message, thay vì chỉ kiểm tra bean có hay không.

## 2. Mô hình logic trước khi viết code

Giả sử feature search cần bốn quy tắc:

- enabled phải là true.
- region phải là ap-southeast-1.
- transport phải là http hoặc jms.
- legacy.enabled không được là true.

Biểu thức logic:

~~~text
SEARCH_READY =
    ENABLED
    AND REGION_SUPPORTED
    AND (HTTP_TRANSPORT OR JMS_TRANSPORT)
    AND NOT LEGACY_ENABLED
~~~

Bảng chân trị rút gọn:

| Enabled | Region hợp lệ | HTTP | JMS | Legacy | Search gateway |
| --- | --- | --- | --- | --- | --- |
| true | true | true | false | false | Match |
| true | true | false | true | false | Match |
| true | true | false | false | false | No match |
| true | false | true | false | false | No match |
| false | true | true | true | false | No match |
| true | true | true | false | true | No match |

Bảng này cho thấy condition tổ hợp có nhiều nhánh độc lập. Khi kết quả cuối là no-match, một thông điệp chung như “conditions did not match” chưa đủ hữu ích. Ta cần biết feature flag sai, region không được hỗ trợ, cả hai transport đều tắt hay legacy mode đang bật.

## 3. Ba loại nested conditions trong Spring Boot

Các class nằm trong package:

~~~java
org.springframework.boot.autoconfigure.condition
~~~

Cả ba đều kế thừa AbstractNestedCondition, đồng thời là Condition và ConfigurationCondition.

### 3.1. AllNestedConditions — tất cả nhánh phải khớp

Dùng khi quy tắc có dạng A AND B AND C:

~~~java
public static class OnSearchEnabledAndRegion
        extends AllNestedConditions {

    public OnSearchEnabledAndRegion() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "enabled",
        havingValue = "true"
    )
    static class SearchEnabled {
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "region",
        havingValue = "ap-southeast-1"
    )
    static class SupportedRegion {
    }
}
~~~

AllNestedConditions chỉ match khi tất cả nested class conditions đều match. Nếu một nhánh no-match, condition tổng thể no-match.

### 3.2. AnyNestedCondition — chỉ cần một nhánh khớp

Dùng khi quy tắc có dạng A OR B:

~~~java
public static class OnHttpOrJmsTransport
        extends AnyNestedCondition {

    public OnHttpOrJmsTransport() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "transport",
        havingValue = "http"
    )
    static class HttpTransport {
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "transport",
        havingValue = "jms"
    )
    static class JmsTransport {
    }
}
~~~

Khi acme.search.transport=http, nhánh HTTP match và condition tổng thể match. Khi property là jms, nhánh JMS match. Nếu không nhánh nào match, condition tổng thể no-match.

Một nhánh OR match không có nghĩa các nhánh còn lại cũng match. Report vẫn có thể cho biết nhánh nào match và nhánh nào không.

### 3.3. NoneNestedConditions — không nhánh nào được khớp

Dùng khi quy tắc yêu cầu không có condition cấm nào xuất hiện:

~~~java
public static class OnLegacyModeDisabled
        extends NoneNestedConditions {

    public OnLegacyModeDisabled() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "legacy.enabled",
        havingValue = "true"
    )
    static class LegacyModeEnabled {
    }
}
~~~

Condition này match khi nested condition LegacyModeEnabled không match. Vì nested condition chỉ match khi property là true, các giá trị false hoặc property bị thiếu đều khiến OnLegacyModeDisabled match.

Đây là điểm dễ nhầm: NoneNestedConditions không có nghĩa “tất cả condition con đều phải no-match để tạo từng bean con”. Nó tạo **một condition tổng hợp** chỉ match khi không condition con nào match.

## 4. Chọn ConfigurationPhase đúng

Mỗi nested condition phải khai báo phase trong constructor:

~~~java
super(ConfigurationPhase.PARSE_CONFIGURATION);
~~~

Hoặc:

~~~java
super(ConfigurationPhase.REGISTER_BEAN);
~~~

| Phase | Khi nào đánh giá | Loại dữ liệu phù hợp |
| --- | --- | --- |
| PARSE_CONFIGURATION | Khi Spring đang phân tích cấu hình/import | Environment properties, classpath, resource và metadata có thể kiểm tra sớm |
| REGISTER_BEAN | Khi Spring đang đăng ký bean definitions | Điều kiện phụ thuộc bean definitions hoặc bean conditions |

Ví dụ trong bài chỉ kiểm tra property từ Environment, nên PARSE_CONFIGURATION phù hợp.

Nếu một condition con sử dụng ConditionalOnBean, ConditionalOnMissingBean hoặc logic phụ thuộc bean definitions, cần cân nhắc REGISTER_BEAN. Phase của condition tổ hợp phải phù hợp với các condition con mà nó chứa. Khi một tổ hợp có nhánh cần bean definitions, hãy chọn phase muộn tương ứng để không đánh giá quá sớm.

**Không chọn phase theo thói quen.** Nếu chọn PARSE_CONFIGURATION cho điều kiện cần bean definitions, condition có thể được đánh giá trước khi những bean đó được đăng ký. Ngược lại, chọn REGISTER_BEAN cho điều kiện chỉ cần property không làm sai kết quả, nhưng có thể trì hoãn việc đánh giá không cần thiết.

## 5. Xây dựng một condition tổng hợp có thể tái sử dụng

Ta đóng gói các nhánh trong class SearchConditions. Các nested condition đều là static class; mỗi class thành viên mang annotation condition riêng.

File src/main/java/demo/search/autoconfigure/SearchConditions.java:

~~~java
package demo.search.autoconfigure;

import org.springframework.boot.autoconfigure.condition.AllNestedConditions;
import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.NoneNestedConditions;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

public final class SearchConditions {

    private SearchConditions() {
    }

    public static final class OnTransportAvailable
            extends AnyNestedCondition {

        public OnTransportAvailable() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "transport",
            havingValue = "http"
        )
        static class HttpTransport {
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "transport",
            havingValue = "jms"
        )
        static class JmsTransport {
        }
    }

    public static final class OnLegacyModeDisabled
            extends NoneNestedConditions {

        public OnLegacyModeDisabled() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "legacy.enabled",
            havingValue = "true"
        )
        static class LegacyModeEnabled {
        }
    }

    public static final class OnSearchReady
            extends AllNestedConditions {

        public OnSearchReady() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "enabled",
            havingValue = "true"
        )
        static class FeatureEnabled {
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "region",
            havingValue = "ap-southeast-1"
        )
        static class SupportedRegion {
        }

        @Conditional(OnTransportAvailable.class)
        static class TransportAvailable {
        }

        @Conditional(OnLegacyModeDisabled.class)
        static class LegacyModeDisabled {
        }
    }
}
~~~

Cấu trúc logic:

- OnSearchReady dùng AND để kết hợp bốn nhánh cấp cao.
- TransportAvailable lồng condition OR: HTTP hoặc JMS.
- LegacyModeDisabled lồng condition NOT: không được bật legacy mode.

Như vậy ta có thể đọc logic từ class structure thay vì phải suy luận từ một biểu thức dài.

### 5.1. Đóng gói condition thành annotation

File src/main/java/demo/search/autoconfigure/ConditionalOnSearchReady.java:

~~~java
package demo.search.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(SearchConditions.OnSearchReady.class)
public @interface ConditionalOnSearchReady {
}
~~~

Người dùng thư viện có thể áp dụng annotation này lên configuration class hoặc bean method mà không cần biết các nhánh nội bộ.

### 5.2. Dùng annotation trong auto-configuration

File src/main/java/demo/search/autoconfigure/SearchGateway.java:

~~~java
package demo.search.autoconfigure;

public record SearchGateway(String description) {
}
~~~

File src/main/java/demo/search/autoconfigure/SearchAutoConfiguration.java:

~~~java
package demo.search.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnSearchReady
    SearchGateway searchGateway() {
        return new SearchGateway("search gateway ready");
    }
}
~~~

Đăng ký auto-configuration trong JAR qua file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
demo.search.autoconfigure.SearchAutoConfiguration
~~~

Trong test, có thể nạp trực tiếp bằng AutoConfigurations.of(SearchAutoConfiguration.class). Ứng dụng tiêu thụ thư viện sẽ phát hiện class thông qua imports file.

## 6. Thông điệp condition: kết quả boolean cần có lý do

Condition của Spring Framework chỉ yêu cầu phương thức matches() trả về boolean. Nếu tự viết condition trực tiếp bằng interface này, bạn không có API chuẩn để gắn message chi tiết vào outcome.

Spring Boot cung cấp SpringBootCondition:

~~~java
public abstract class SpringBootCondition implements Condition {

    public abstract ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    );
}
~~~

SpringBootCondition thực hiện matches() và logging outcome cho bạn. Phương thức matches() của base class là final; class con cần triển khai getMatchOutcome().

ConditionOutcome chứa hai thông tin:

- isMatch() — condition có khớp không.
- getMessage() — thông điệp giải thích outcome.

Tạo outcome:

~~~java
ConditionOutcome.match("required property is available");
ConditionOutcome.noMatch("required property is missing");
~~~

Hoặc dùng ConditionMessage để tạo message có cấu trúc:

~~~java
ConditionMessage message =
    ConditionMessage.forCondition("Search transport")
        .because("acme.search.mode selects HTTP transport");

return ConditionOutcome.match(message);
~~~

Với nhánh không khớp:

~~~java
ConditionMessage message =
    ConditionMessage.forCondition("Search transport")
        .because("acme.search.mode is missing; expected http or jms");

return ConditionOutcome.noMatch(message);
~~~

### 6.1. Phân biệt message của condition tổng hợp và message của từng nhánh

Có hai cấp thông điệp:

1. **Thông điệp của nested condition:** condition con do ConditionalOnProperty hoặc condition riêng trả về. Nó giải thích property/class/resource nào đã match hoặc no-match.
2. **Thông điệp của condition tổng hợp:** AllNestedConditions, AnyNestedCondition hoặc NoneNestedConditions tổng hợp kết quả các nhánh con.

Spring Boot giữ lại các outcome của nested conditions trong ConditionEvaluationReport. Nhờ vậy, khi condition tổng thể no-match, ta vẫn có thể xem nhánh nào đã thất bại.

Nếu cần một lý do nghiệp vụ riêng cho mỗi nhánh, hãy tạo custom condition kế thừa SpringBootCondition và trả ConditionOutcome tương ứng. Không nên chỉ trả message chung như “search condition failed” cho mọi trường hợp.

## 7. Custom SpringBootCondition với message riêng cho từng nhánh

Ví dụ này chọn transport dựa trên property acme.search.mode. Có bốn nhánh:

- http — match và chọn HTTP.
- jms — match và chọn JMS.
- Property thiếu hoặc rỗng — no-match với lý do cụ thể.
- Giá trị không được hỗ trợ — no-match và ghi lại giá trị đã nhận.

### 7.1. Annotation

File src/main/java/demo/search/autoconfigure/ConditionalOnSearchMode.java:

~~~java
package demo.search.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(SearchModeCondition.class)
public @interface ConditionalOnSearchMode {
}
~~~

### 7.2. Condition implementation

File src/main/java/demo/search/autoconfigure/SearchModeCondition.java:

~~~java
package demo.search.autoconfigure;

import java.util.Locale;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class SearchModeCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String configuredMode =
            context.getEnvironment().getProperty("acme.search.mode");

        if (configuredMode == null || configuredMode.isBlank()) {
            return noMatch(
                "acme.search.mode is missing; expected http or jms"
            );
        }

        String mode = configuredMode.trim().toLowerCase(Locale.ROOT);

        return switch (mode) {
            case "http" -> match(
                "acme.search.mode selects HTTP transport"
            );
            case "jms" -> match(
                "acme.search.mode selects JMS transport"
            );
            default -> noMatch(
                "unsupported acme.search.mode '" + configuredMode
                    + "'; expected http or jms"
            );
        };
    }

    private ConditionOutcome match(String reason) {
        ConditionMessage message =
            ConditionMessage.forCondition("Search mode")
                .because(reason);

        return ConditionOutcome.match(message);
    }

    private ConditionOutcome noMatch(String reason) {
        ConditionMessage message =
            ConditionMessage.forCondition("Search mode")
                .because(reason);

        return ConditionOutcome.noMatch(message);
    }
}
~~~

### 7.3. Dùng custom condition trên bean method

File src/main/java/demo/search/autoconfigure/SearchModeClient.java:

~~~java
package demo.search.autoconfigure;

public record SearchModeClient(String transport) {
}
~~~

File src/main/java/demo/search/autoconfigure/SearchModeAutoConfiguration.java:

~~~java
package demo.search.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@AutoConfiguration
public class SearchModeAutoConfiguration {

    @Bean
    @ConditionalOnSearchMode
    SearchModeClient searchModeClient(Environment environment) {
        return new SearchModeClient(
            environment.getRequiredProperty("acme.search.mode")
        );
    }
}
~~~

Ví dụ này minh họa thông điệp cho mỗi nhánh. Trong một thư viện thực tế, nếu mode được bind vào configuration properties thì bean method có thể nhận properties bean thay vì đọc Environment trực tiếp.

### 7.4. Message mong đợi theo từng nhánh

| Property | Match? | Message fragment |
| --- | --- | --- |
| acme.search.mode=http | Có | acme.search.mode selects HTTP transport |
| acme.search.mode=jms | Có | acme.search.mode selects JMS transport |
| Property thiếu | Không | acme.search.mode is missing; expected http or jms |
| acme.search.mode=kafka | Không | unsupported acme.search.mode 'kafka'; expected http or jms |

Thông điệp không quyết định kết quả; boolean trong ConditionOutcome mới quyết định. Message chỉ giải thích lý do để người phát triển đọc condition report và chẩn đoán cấu hình.

## 8. Đọc ConditionEvaluationReport để kiểm tra từng nhánh

Spring Boot ghi nhận condition outcomes trong ConditionEvaluationReport. Report nhóm kết quả theo source, thường là configuration class hoặc bean method.

Các API hữu ích:

~~~java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(beanFactory);

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> outcomes =
    report.getConditionAndOutcomesBySource();
~~~

Mỗi ConditionAndOutcomes là một collection có thể lặp qua các ConditionAndOutcome. Mỗi phần tử cung cấp:

- getCondition() — condition đã được đánh giá.
- getOutcome() — kết quả của condition.
- getOutcome().isMatch() — trạng thái match/no-match.
- getOutcome().getMessage() — thông điệp chẩn đoán.

Ví dụ đọc report trong test:

~~~java
private static List<String> conditionMessages(
        AssertableApplicationContext context) {

    ConditionEvaluationReport report =
        ConditionEvaluationReport.get(
            context.getSourceApplicationContext().getBeanFactory()
        );

    return report.getConditionAndOutcomesBySource()
        .values()
        .stream()
        .flatMap(outcomes ->
            StreamSupport.stream(outcomes.spliterator(), false)
        )
        .map(item -> item.getOutcome().getMessage())
        .toList();
}
~~~

ConditionAndOutcomes trong Spring Boot 3.3 implements Iterable, nên có thể dùng StreamSupport như trên. Không dùng stream() nếu cần tương thích với Boot 3.3: phương thức đó chỉ xuất hiện từ Spring Boot 3.5.

### 8.1. Report có thể chứa nhiều source

Ví dụ một condition tổng hợp trên bean method có thể tạo các source tương ứng:

~~~text
demo.search.autoconfigure.SearchAutoConfiguration#searchGateway
demo.search.autoconfigure.SearchConditions$OnSearchReady
demo.search.autoconfigure.SearchConditions$OnSearchReady$FeatureEnabled
demo.search.autoconfigure.SearchConditions$OnSearchReady$SupportedRegion
demo.search.autoconfigure.SearchConditions$OnTransportAvailable
demo.search.autoconfigure.SearchConditions$OnTransportAvailable$HttpTransport
demo.search.autoconfigure.SearchConditions$OnTransportAvailable$JmsTransport
demo.search.autoconfigure.SearchConditions$OnLegacyModeDisabled
~~~

Tên source cụ thể phụ thuộc cấu trúc class và cách Spring ghi nhận metadata. Khi viết test, nên lọc message theo nội dung ổn định như property name hoặc lý do nghiệp vụ, thay vì phụ thuộc toàn bộ tên source nội bộ.

### 8.2. Xem report khi chạy ứng dụng

Có thể bật condition evaluation report bằng:

~~~bash
java -jar target/search-demo-1.0.0.jar --debug
~~~

Spring Boot sẽ in các nhóm positive matches và negative matches trong startup log.

Nếu ứng dụng có Actuator và endpoint được expose, endpoint /actuator/conditions cũng có thể cung cấp condition report. Report này dành cho chẩn đoán; không nên expose rộng rãi nếu message có thể tiết lộ cấu hình nội bộ.

## 9. Ví dụ Maven và kiểm thử các nhánh

Ví dụ dùng Spring Boot 3.3.13, Java 17+ và ApplicationContextRunner. Test xác nhận:

1. AND/OR/NOT cùng khớp và gateway được đăng ký.
2. OR chọn được nhánh HTTP.
3. OR chọn được nhánh JMS.
4. Region sai làm AND no-match.
5. Legacy bật làm NOT no-match.
6. Custom condition trả đúng message cho HTTP, JMS, property thiếu và mode không hỗ trợ.

### 9.1. Cấu trúc project

~~~text
search-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/search/autoconfigure/
    │   │   ├── SearchConditions.java
    │   │   ├── ConditionalOnSearchReady.java
    │   │   ├── SearchGateway.java
    │   │   ├── SearchAutoConfiguration.java
    │   │   ├── ConditionalOnSearchMode.java
    │   │   ├── SearchModeCondition.java
    │   │   ├── SearchModeClient.java
    │   │   └── SearchModeAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/demo/search/autoconfigure/
            └── SearchConditionTests.java
~~~

### 9.2. File pom.xml

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

    <groupId>demo</groupId>
    <artifactId>search-condition-demo</artifactId>
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
~~~

### 9.3. Đăng ký auto-configuration

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
demo.search.autoconfigure.SearchAutoConfiguration
demo.search.autoconfigure.SearchModeAutoConfiguration
~~~

Trong project thư viện thật, hai class này sẽ nằm trong JAR và được consumer phát hiện qua imports file. Trong test, ta có thể nạp trực tiếp qua AutoConfigurations.of(...).

### 9.4. File test hoàn chỉnh

File src/test/java/demo/search/autoconfigure/SearchConditionTests.java:

~~~java
package demo.search.autoconfigure;

import java.util.List;
import java.util.stream.StreamSupport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class SearchConditionTests {

    private final ApplicationContextRunner compositeRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(SearchAutoConfiguration.class)
            );

    private final ApplicationContextRunner modeRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(SearchModeAutoConfiguration.class)
            );

    private static List<String> conditionMessages(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
            ConditionEvaluationReport.get(
                context.getSourceApplicationContext().getBeanFactory()
            );

        return report.getConditionAndOutcomesBySource()
            .values()
            .stream()
            .flatMap(outcomes ->
                StreamSupport.stream(outcomes.spliterator(), false)
            )
            .map(item -> item.getOutcome().getMessage())
            .toList();
    }

    @Test
    void matchesWhenAndOrAndNotBranchesAreSatisfied() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=ap-southeast-1",
                "acme.search.transport=http",
                "acme.search.legacy.enabled=false"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(SearchGateway.class);

                List<String> messages = conditionMessages(context);

                assertThat(messages)
                    .anyMatch(message ->
                        message.contains("acme.search.enabled"));

                assertThat(messages)
                    .anyMatch(message ->
                        message.contains("acme.search.region"));

                assertThat(messages)
                    .anyMatch(message ->
                        message.contains("acme.search.transport"));

                assertThat(messages)
                    .anyMatch(message ->
                        message.contains("acme.search.legacy.enabled"));
            });
    }

    @Test
    void anyNestedConditionCanSelectJmsBranch() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=ap-southeast-1",
                "acme.search.transport=jms",
                "acme.search.legacy.enabled=false"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(SearchGateway.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains("jms"));
            });
    }

    @Test
    void allNestedConditionDoesNotMatchWhenRegionIsUnsupported() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=eu-west-1",
                "acme.search.transport=http",
                "acme.search.legacy.enabled=false"
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(SearchGateway.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains("acme.search.region"));
            });
    }

    @Test
    void noneNestedConditionRejectsLegacyMode() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=ap-southeast-1",
                "acme.search.transport=http",
                "acme.search.legacy.enabled=true"
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(SearchGateway.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains("acme.search.legacy.enabled"));
            });
    }

    @Test
    void anyNestedConditionDoesNotMatchWhenNoTransportIsSelected() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=ap-southeast-1",
                "acme.search.legacy.enabled=false"
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(SearchGateway.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains("acme.search.transport"));
            });
    }

    @Test
    void customConditionReportsHttpBranchMessage() {
        this.modeRunner
            .withPropertyValues("acme.search.mode=http")
            .run(context -> {
                assertThat(context).hasSingleBean(SearchModeClient.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains(
                            "acme.search.mode selects HTTP transport"
                        ));
            });
    }

    @Test
    void customConditionReportsJmsBranchMessage() {
        this.modeRunner
            .withPropertyValues("acme.search.mode=jms")
            .run(context -> {
                assertThat(context).hasSingleBean(SearchModeClient.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains(
                            "acme.search.mode selects JMS transport"
                        ));
            });
    }

    @Test
    void customConditionReportsMissingPropertyMessage() {
        this.modeRunner.run(context -> {
            assertThat(context).doesNotHaveBean(SearchModeClient.class);

            assertThat(conditionMessages(context))
                .anyMatch(message ->
                    message.contains(
                        "acme.search.mode is missing; expected http or jms"
                    ));
        });
    }

    @Test
    void customConditionReportsUnsupportedValueMessage() {
        this.modeRunner
            .withPropertyValues("acme.search.mode=kafka")
            .run(context -> {
                assertThat(context).doesNotHaveBean(SearchModeClient.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains(
                            "unsupported acme.search.mode 'kafka'"
                        ));
            });
    }
}
~~~

### 9.5. Chạy test

Yêu cầu: JDK 17+ và Maven 3.8+. Từ thư mục project:

~~~bash
mvn clean test
~~~

Có chín test độc lập. Kết quả mong đợi:

| Test | Nhánh được kiểm tra | Assertion chính |
| --- | --- | --- |
| matchesWhenAndOrAndNotBranchesAreSatisfied | AND + HTTP OR JMS + NOT legacy | Gateway được tạo và report có message của từng property |
| anyNestedConditionCanSelectJmsBranch | OR / JMS | Gateway được tạo qua nhánh JMS |
| allNestedConditionDoesNotMatchWhenRegionIsUnsupported | AND / region | Gateway không được tạo; report nêu region |
| noneNestedConditionRejectsLegacyMode | NOT / legacy | Gateway không được tạo; report nêu legacy |
| anyNestedConditionDoesNotMatchWhenNoTransportIsSelected | OR / không nhánh | Gateway không được tạo; report nêu transport |
| customConditionReportsHttpBranchMessage | Custom / HTTP | Có client và message HTTP |
| customConditionReportsJmsBranchMessage | Custom / JMS | Có client và message JMS |
| customConditionReportsMissingPropertyMessage | Custom / missing | Không có client; message báo property thiếu |
| customConditionReportsUnsupportedValueMessage | Custom / unsupported | Không có client; message nêu giá trị không hỗ trợ |

Maven Surefire sẽ báo chín test thành công và BUILD SUCCESS nếu các assertion đều đúng. Đây là kết quả mong đợi từ code test, không phải stdout đã được chạy trong môi trường hiện tại.

## 10. Cách đọc message của từng nhánh trong thực tế

Giả sử cấu hình:

~~~properties
acme.search.enabled=true
acme.search.region=eu-west-1
acme.search.transport=http
acme.search.legacy.enabled=false
~~~

Ta có thể diễn giải report:

| Nhánh | Kết quả | Lý do |
| --- | --- | --- |
| Feature enabled | Match | Property enabled là true |
| Supported region | No match | Region hiện tại là eu-west-1, yêu cầu ap-southeast-1 |
| HTTP transport | Match | Transport là http |
| JMS transport | No match | Transport không phải jms |
| Legacy mode enabled | No match | Legacy flag là false |
| Search ready (AND) | No match | Có ít nhất một điều kiện bắt buộc không đạt |

Condition tổng hợp no-match không có nghĩa tất cả nhánh đều thất bại. Trong ví dụ, feature và HTTP transport đã match; chỉ region làm AND thất bại.

Nếu đổi transport thành jms, nhánh JMS sẽ match thay cho HTTP. OR condition vẫn match vì ít nhất một nhánh đúng.

Nếu đổi legacy.enabled thành true, nested condition LegacyModeEnabled match, vì thế NoneNestedConditions no-match và search gateway bị loại.

## 11. Quy tắc viết message tốt

Một message hữu ích nên trả lời ba câu hỏi:

1. **Condition nào đang được đánh giá?** Ví dụ Search mode, supported region hoặc transport availability.
2. **Nhánh nào được kiểm tra?** HTTP, JMS, legacy, property hoặc class.
3. **Vì sao match/no-match?** Giá trị thực tế, giá trị mong đợi hoặc điều kiện còn thiếu.

### 11.1. Viết lý do thay vì lặp lại tên annotation

Message yếu:

~~~text
Condition did not match
~~~

Message tốt hơn:

~~~text
acme.search.region is 'eu-west-1'; expected 'ap-southeast-1'
~~~

Message yếu:

~~~text
Search mode failed
~~~

Message tốt hơn:

~~~text
unsupported acme.search.mode 'kafka'; expected http or jms
~~~

### 11.2. Message nên ổn định và không chứa dữ liệu nhạy cảm

Condition message thường xuất hiện trong startup logs, debug report hoặc Actuator conditions endpoint. Không đưa password, token, secret, private key hay toàn bộ URL chứa credentials vào message.

Nên ghi:

- Property key.
- Giá trị không nhạy cảm hoặc trạng thái missing.
- Giá trị được hỗ trợ.
- Tên class/resource khi hữu ích.
- Một hành động khắc phục ngắn.

Nếu property chứa secret, hãy ghi “credential property is configured/missing” thay vì ghi giá trị thực tế.

### 11.3. Test message bằng fragment ổn định

Không nên assert toàn bộ message mặc định do Spring Boot tạo ra cho ConditionalOnProperty. Format có thể chứa annotation name, prefix, expected value và wording nội bộ.

Thay vào đó:

- Với built-in condition, assert fragment ổn định như property key hoặc tên class.
- Với custom condition, assert câu lý do do bạn tự kiểm soát.
- Kiểm tra cả isMatch() hoặc bean presence; message không thay thế kết quả logic.
- Không assert source class name nội bộ nếu không phải API mà thư viện cam kết.

## 12. Lỗi phổ biến khi viết condition tổ hợp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng AllNestedConditions cho nhánh HTTP hoặc JMS | AND yêu cầu cả hai nhánh cùng match | Dùng AnyNestedCondition |
| Dùng AnyNestedCondition cho feature cần đủ mọi điều kiện | Chỉ một nhánh đúng đã làm condition match | Dùng AllNestedConditions |
| Dùng NoneNestedConditions nhưng mong một nhánh đúng sẽ cho match | None match khi không nested condition nào match | Viết lại biểu thức logic và test cả hai phía |
| Quên constructor gọi super(ConfigurationPhase...) | Nested condition cần phase để đánh giá | Chọn PARSE_CONFIGURATION hoặc REGISTER_BEAN |
| Dùng PARSE_CONFIGURATION cho condition cần bean definition | Có thể đánh giá quá sớm | Chọn REGISTER_BEAN |
| Các nested member class không static | Không phù hợp cơ chế nested condition | Khai báo static class |
| Nhét toàn bộ logic vào một expression dài | Khó đọc và message khó phân nhánh | Tách nested condition theo domain |
| Condition custom chỉ trả boolean | Mất thông điệp chẩn đoán có cấu trúc | Kế thừa SpringBootCondition |
| Override matches() trong SpringBootCondition | Method của base class là final | Override getMatchOutcome() |
| Dùng message chung cho mọi no-match | Không biết nhánh nào thất bại | Tạo ConditionOutcome riêng theo nhánh |
| Assert toàn bộ message mặc định của Boot | Dễ gãy khi wording thay đổi | Assert message fragment có ý nghĩa |
| Chỉ test một tổ hợp thành công | Không kiểm OR branch thứ hai hoặc các nhánh phủ định | Test match và no-match cho từng nhánh |
| Gọi getBean() hoặc I/O trong condition | Condition chạy trong configuration phase và không nên tạo side effect | Chỉ đọc metadata/Environment; để bean/service làm việc runtime |
| Dùng condition để thay thế validation dữ liệu | Match không bảo đảm dữ liệu hợp lệ | Bind/validate properties riêng |

## 13. Quy trình thiết kế và review condition tổ hợp

1. Viết biểu thức logic trước khi viết Java: A AND (B OR C) AND NOT D.
2. Đặt tên cho từng nhánh theo ngôn ngữ nghiệp vụ.
3. Chọn AllNestedConditions, AnyNestedCondition và NoneNestedConditions theo đúng toán tử.
4. Đặt các nested member classes là static và gắn condition annotation cho từng class.
5. Chọn ConfigurationPhase theo loại input mà nhánh cần đọc.
6. Đóng gói condition thành annotation nếu nhiều auto-configuration cần dùng lại.
7. Nếu cần message domain-specific, tạo SpringBootCondition và trả ConditionOutcome cho từng nhánh.
8. Kiểm tra ConditionEvaluationReport để xem từng condition và outcome.
9. Viết test cho từng nhánh match/no-match, cả giá trị missing và unsupported.
10. Assert cả bean presence/absence và message fragment.
11. Chạy ứng dụng với --debug để kiểm report trong startup logs.
12. Giữ message ngắn, ổn định và không chứa secret.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào dùng AllNestedConditions?  
**Đáp án:** Khi tất cả nested conditions phải match, tương đương AND.

**Câu 2.** Khi nào dùng AnyNestedCondition?  
**Đáp án:** Khi chỉ cần ít nhất một nested condition match, tương đương OR.

**Câu 3.** NoneNestedConditions match khi nào?  
**Đáp án:** Khi không nested condition nào match.

**Câu 4.** Vì sao nested condition cần ConfigurationPhase?  
**Đáp án:** Để Spring biết condition được đánh giá ở phase phân tích cấu hình hay đăng ký bean definitions; phase phải phù hợp dữ liệu mà các nhánh cần.

**Câu 5.** Các nested condition class nên được khai báo như thế nào?  
**Đáp án:** Là static nested classes và mỗi class được gắn condition tương ứng.

**Câu 6.** ConditionOutcome chứa những gì?  
**Đáp án:** Trạng thái match/no-match và thông điệp giải thích.

**Câu 7.** Vì sao kế thừa SpringBootCondition thay vì chỉ implement Condition?  
**Đáp án:** SpringBootCondition cung cấp logging/reporting phù hợp với Spring Boot và cho phép trả ConditionOutcome có message.

**Câu 8.** Phương thức nào cần override trong custom SpringBootCondition?  
**Đáp án:** getMatchOutcome(context, metadata). Phương thức matches() của base class là final.

**Câu 9.** ConditionEvaluationReport nhóm kết quả theo gì?  
**Đáp án:** Theo source của condition evaluation, thường là configuration class hoặc bean method; mỗi entry chứa condition và outcome.

**Câu 10.** Khi test message của ConditionalOnProperty, nên assert toàn bộ chuỗi hay fragment?  
**Đáp án:** Nên assert fragment ổn định như property key và lý do. Với custom condition, có thể assert chính xác câu lý do do mình kiểm soát.

**Câu 11.** Nếu HTTP match và JMS no-match, AnyNestedCondition có match không?  
**Đáp án:** Có. Chỉ cần một nhánh match.

**Câu 12.** Nếu một trong bốn nhánh của AllNestedConditions no-match thì kết quả là gì?  
**Đáp án:** Condition tổng thể no-match, dù các nhánh còn lại có thể match.

## 15. Ghi nhớ và tài liệu tham khảo

- AllNestedConditions là AND; AnyNestedCondition là OR; NoneNestedConditions là NOT của tập condition con.
- Nested conditions sử dụng các static member classes có annotation condition riêng.
- ConfigurationPhase.PARSE_CONFIGURATION phù hợp với property/classpath/resource có thể đánh giá sớm; REGISTER_BEAN dành cho điều kiện phụ thuộc bean definitions.
- SpringBootCondition cho phép trả ConditionOutcome có message và logging; override getMatchOutcome(), không override matches().
- ConditionMessage.forCondition(...).because(...) giúp tạo message nhất quán; ConditionOutcome.match/noMatch giữ cả trạng thái và message.
- ConditionEvaluationReport nhóm outcome theo source; có thể lặp qua ConditionAndOutcomes để đọc message từng nhánh.
- Test phải kiểm tra cả boolean/bean presence lẫn message. Với built-in condition, assert fragment ổn định; với custom condition, assert lý do cụ thể.
- Condition message là công cụ chẩn đoán, không thay thế validation, bean creation hoặc xử lý lỗi runtime.

Tài liệu chính thức Spring Boot 3.3.13:

1. [AllNestedConditions Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AllNestedConditions.html) — điều kiện AND và ConfigurationPhase.
2. [AnyNestedCondition Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html) — điều kiện OR.
3. [NoneNestedConditions Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/NoneNestedConditions.html) — điều kiện phủ định.
4. [SpringBootCondition Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html) — getMatchOutcome() và logging.
5. [ConditionMessage Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html) — fluent message builder.
6. [ConditionOutcome Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html) — match/no-match outcome và message.
7. [ConditionEvaluationReport Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html) — report theo source và cách truy cập outcomes.
8. [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — custom auto-configuration và kiểm thử bằng ApplicationContextRunner.
