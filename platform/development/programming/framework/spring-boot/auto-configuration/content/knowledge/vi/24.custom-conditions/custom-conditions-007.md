# AllNestedConditions cho nhóm yêu cầu đồng thời

> **Spring Boot Auto Configuration → Điều kiện tùy chỉnh.** Bài học giải thích cách dùng AllNestedConditions để gộp nhiều điều kiện thành một điều kiện tổng hợp chỉ match khi tất cả điều kiện thành viên đều match. Ví dụ thực hành dùng Spring Boot 3.3.13, Java 17 và một integration JDBC tùy chọn: tính năng lưu lịch sử chỉ được đăng ký khi JdbcTemplate có trên classpath và property bật tính năng có giá trị true. Bài cũng phân biệt PARSE_CONFIGURATION với REGISTER_BEAN, so sánh với AnyNestedConditions, NoneNestedConditions và kiểm thử từng tổ hợp bằng ApplicationContextRunner.

## 1. Bài toán: nhiều điều kiện phải cùng đúng

Một auto-configuration có thể chỉ phù hợp khi nhiều yêu cầu cùng được đáp ứng. Ví dụ một thư viện có module lưu lịch sử thông báo qua JDBC. Bean ghi lịch sử chỉ nên được tạo khi:

1. Spring JDBC có trên runtime classpath.
2. Người dùng bật tính năng bằng acme.notice.history.enabled=true.
3. Ứng dụng đã có bean JdbcTemplate để adapter sử dụng.
4. Ứng dụng chưa tự cung cấp bean NoticeHistoryWriter thay thế.

Các điều kiện này thuộc những tầng khác nhau:
- Classpath và property có thể được kiểm tra khi Spring đang parse cấu hình.
- Sự hiện diện của bean JdbcTemplate được kiểm tra ở giai đoạn đăng ký bean.
- Bean thay thế được xét bởi ConditionalOnMissingBean.

Ta có thể đặt nhiều annotation condition trên cùng một cấu hình, nhưng khi một nhóm điều kiện cần được đặt tên, tái sử dụng hoặc kiểm thử như một đơn vị, AllNestedConditions cung cấp một cách biểu diễn rõ ràng.

Điều quan trọng là không gộp mọi thứ vào một condition một cách máy móc. Chọn đúng những điều kiện có cùng giai đoạn đánh giá, rồi giữ điều kiện phụ thuộc bean ở đúng phạm vi bean method.

## 2. AllNestedConditions là gì?

org.springframework.boot.autoconfigure.condition.AllNestedConditions là lớp trừu tượng của Spring Boot, kế thừa AbstractNestedCondition. Nó tạo một condition tổng hợp từ các condition đặt trên những lớp static lồng bên trong.

Condition tổng hợp chỉ match khi **tất cả nested class conditions đều match**. Nếu một điều kiện thành viên không match, condition tổng hợp cũng không match.

Mẫu cơ bản:

~~~java
static class OnJndiAndProperty extends AllNestedConditions {

    OnJndiAndProperty() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnJndi
    static class OnJndi {
    }

    @ConditionalOnProperty("something")
    static class OnProperty {
    }
}
~~~

Trong ví dụ:
- OnJndi là một condition thành viên.
- OnProperty là condition thành viên còn lại.
- Cả hai phải match thì OnJndiAndProperty mới match.
- Constructor truyền ConfigurationPhase để Spring Boot biết thời điểm đánh giá nhóm condition.

Lớp thành viên không cần chứa logic Java. Annotation trên từng lớp là điều kiện thực sự được Spring Boot đánh giá. Lớp tổng hợp chỉ xác định cách kết hợp các kết quả đó.

### 2.1. Bảng chân trị của AllNestedConditions

Giả sử có hai điều kiện A và B:

| A | B | AllNestedConditions |
| --- | --- | --- |
| true | true | Match |
| true | false | No match |
| false | true | No match |
| false | false | No match |

Với ba điều kiện A, B, C, chỉ tổ hợp true, true, true mới match. Chỉ cần một điều kiện sai là kết quả tổng hợp không match.

Đây chính là phép logic AND:

~~~text
All(A, B, C) = A AND B AND C
~~~

Ví dụ thực tế:

~~~text
Spring JDBC có trên classpath?       true
acme.notice.history.enabled=true?    true
-------------------------------------------
AllNestedConditions                  MATCH
~~~

Nếu Spring JDBC không có trên classpath dù property đang true, kết quả vẫn là no-match.

### 2.2. Khi nào nên dùng?

Dùng AllNestedConditions khi:
- Có từ hai điều kiện trở lên phải đồng thời đúng.
- Muốn biểu diễn một quy tắc tổng hợp có tên dễ hiểu.
- Muốn tái sử dụng cùng nhóm điều kiện trên nhiều configuration.
- Muốn nhóm các điều kiện classpath/property thành một đơn vị riêng.
- Muốn báo cáo condition thể hiện một quy tắc tổng hợp thay vì lặp nhiều annotation ở nhiều nơi.

Nếu chỉ có hai annotation đơn giản trên một class và không cần tái sử dụng, đặt trực tiếp các annotation đó có thể dễ đọc hơn. AllNestedConditions không phải yêu cầu bắt buộc cho mọi phép AND.

## 3. Phân biệt AllNestedConditions, AnyNestedConditions và NoneNestedConditions

Spring Boot có ba lớp thường dùng để kết hợp nested conditions:

| Lớp | Quy tắc | Ý nghĩa |
| --- | --- | --- |
| AllNestedConditions | Tất cả phải match | AND |
| AnyNestedCondition | Chỉ cần một điều kiện match | OR |
| NoneNestedConditions | Không điều kiện nào được match | NOR |

Ví dụ cùng hai điều kiện A và B:

| A | B | All | Any | None |
| --- | --- | --- | --- | --- |
| true | true | Match | Match | No match |
| true | false | No match | Match | No match |
| false | true | No match | Match | No match |
| false | false | No match | No match | Match |

### 3.1. AnyNestedCondition: chỉ cần một nhánh đúng

Ví dụ một thư viện có thể dùng một trong hai cơ chế xác thực: API key hoặc OAuth. Nếu chỉ cần một cơ chế được bật, dùng AnyNestedCondition:

~~~java
static class OnApiKeyOrOAuth extends AnyNestedCondition {

    OnApiKeyOrOAuth() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.auth",
            name = "api-key-enabled",
            havingValue = "true"
    )
    static class ApiKeyEnabled {
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.auth",
            name = "oauth-enabled",
            havingValue = "true"
    )
    static class OAuthEnabled {
    }
}
~~~

Nếu API key hoặc OAuth bật, condition match. Nếu cả hai tắt hoặc không được khai báo, condition không match.

### 3.2. NoneNestedConditions: tất cả nhánh đều không đúng

Ví dụ một tính năng fallback chỉ được bật khi không có provider bên ngoài nào được chọn:

~~~java
static class OnNoExternalProvider extends NoneNestedConditions {

    OnNoExternalProvider() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.provider",
            name = "cloud",
            havingValue = "true"
    )
    static class CloudProviderSelected {
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.provider",
            name = "external",
            havingValue = "true"
    )
    static class ExternalProviderSelected {
    }
}
~~~

Condition này match khi cả cloud và external đều không match. Cần đặt default và tài liệu property rõ ràng để tránh fallback vô tình bật khi người dùng cấu hình sai.

### 3.3. Chọn đúng phép kết hợp

- Dùng AND khi mọi yêu cầu đều bắt buộc.
- Dùng OR khi bất kỳ một phương án nào cũng đủ.
- Dùng NOR khi chỉ được áp dụng trong trường hợp không có nhánh nào hoạt động.

Đừng chọn lớp theo tên gọi chung chung. Hãy viết bảng chân trị cho các trường hợp quan trọng trước khi triển khai condition.

## 4. ConfigurationPhase: chọn thời điểm đánh giá

Constructor của AllNestedConditions yêu cầu một giá trị ConfigurationPhase:

~~~java
super(ConfigurationPhase.PARSE_CONFIGURATION);
~~~

Hai phase chính là:

| Phase | Thời điểm | Dùng khi |
| --- | --- | --- |
| PARSE_CONFIGURATION | Khi Spring parse configuration classes | Điều kiện có thể đánh giá sớm, ví dụ classpath và property |
| REGISTER_BEAN | Khi Spring đăng ký bean definitions | Điều kiện phụ thuộc bean definitions, ví dụ ConditionalOnBean |

Tài liệu Spring Boot yêu cầu chọn phase phù hợp với các condition thành viên. Ví dụ classpath và property là điều kiện tĩnh có thể đánh giá sớm nên PARSE_CONFIGURATION phù hợp.

### 4.1. Ví dụ dùng PARSE_CONFIGURATION

Nhóm sau chỉ kiểm tra classpath và property:

~~~java
static class OnJdbcAndHistoryEnabled extends AllNestedConditions {

    OnJdbcAndHistoryEnabled() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnClass(name = "org.springframework.jdbc.core.JdbcTemplate")
    static class JdbcTemplatePresent {
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.history",
            name = "enabled",
            havingValue = "true"
    )
    static class HistoryFeatureEnabled {
    }
}
~~~

Cả hai condition có thể được đánh giá khi parse configuration. Nhóm này không kiểm tra bean JdbcTemplate đã được tạo hay chưa.

### 4.2. Vì sao không đưa mọi condition vào cùng một nhóm?

ConditionalOnBean phụ thuộc các bean definitions đã được đăng ký. Nếu trộn condition này vào nhóm đang dùng PARSE_CONFIGURATION, phase của condition tổng hợp có thể không còn phù hợp với thành viên.

Trong ví dụ thực hành, ta giữ ConditionalOnBean(JdbcTemplate.class) ở bean method. Nhóm AllNestedConditions chỉ kiểm tra classpath và property; bean method kiểm tra sự hiện diện của bean dependency ở giai đoạn phù hợp.

Cách phân tầng này làm rõ ba câu hỏi:

1. Môi trường có hỗ trợ JDBC không?
2. Người dùng có bật tính năng history không?
3. Ứng dụng có cung cấp JdbcTemplate để tạo adapter không?

Nếu một condition tùy chỉnh thực sự cần kiểm tra bean, hãy chọn phase phù hợp cho nhóm đó và kiểm tra tất cả nested conditions có thể được đánh giá ở phase đã chọn. Không chọn phase chỉ vì thấy ví dụ trên mạng dùng nó.

## 5. Áp dụng AllNestedConditions lên configuration

Lớp condition tổng hợp thường được gắn vào một configuration bằng Conditional:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(OnJdbcAndHistoryEnabled.class)
static class JdbcHistoryConfiguration {
    // Các bean chỉ tồn tại khi toàn bộ nhóm điều kiện match.
}
~~~

Khi nhóm condition không match:
- Spring bỏ qua configuration class.
- Các bean nằm trong class đó không được đăng ký.
- Bean ở configuration độc lập khác vẫn có thể hoạt động.

Đặt condition ở phạm vi phù hợp:
- Trên toàn auto-configuration nếu mọi bean trong đó cùng cần điều kiện.
- Trên nested configuration nếu chỉ một nhóm bean cần điều kiện.
- Trên bean method nếu điều kiện chỉ áp dụng cho một bean.

Với integration tùy chọn, nested configuration thường giúp cô lập dependency và tránh chặn các bean không liên quan.

### 5.1. Kết hợp với ConditionalOnBean và ConditionalOnMissingBean

Một cấu hình thực tế có thể dùng:
- AllNestedConditions cho classpath + feature property.
- ConditionalOnBean cho dependency bean.
- ConditionalOnMissingBean cho khả năng user override.

Các condition này có vai trò khác nhau. Không cần đưa tất cả vào lớp AllNestedConditions.

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(OnJdbcAndHistoryEnabled.class)
static class JdbcHistoryConfiguration {

    @Bean
    @ConditionalOnBean(JdbcTemplate.class)
    @ConditionalOnMissingBean(NoticeHistoryWriter.class)
    NoticeHistoryWriter noticeHistoryWriter(JdbcTemplate jdbcTemplate) {
        return new NoticeHistoryWriter(
                jdbcTemplate.getClass().getSimpleName()
        );
    }
}
~~~

Factory method chỉ được áp dụng khi configuration group match, có JdbcTemplate bean và chưa có NoticeHistoryWriter do ứng dụng cung cấp.

## 6. Ví dụ dự án hoàn chỉnh Java 17 + Spring Boot 3.3.13

Lab tạo một JDBC history adapter đơn giản. Bean NoticeHistoryWriter được tạo khi:
- Spring JDBC class có trên classpath.
- acme.notice.history.enabled=true.
- Context có bean JdbcTemplate.
- Chưa có bean NoticeHistoryWriter tùy chỉnh.

Để không cần database thật, bean mẫu chỉ ghi nhận class của JdbcTemplate; mục tiêu là kiểm thử condition và không thực hiện câu SQL.

### 6.1. Cấu trúc thư mục

~~~text
notice-all-nested-conditions/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/acme/notice/autoconfigure/
    │       ├── NoticeHistoryWriter.java
    │       └── NoticeHistoryAutoConfiguration.java
    └── test/
        └── java/com/acme/notice/autoconfigure/
            └── NoticeHistoryAutoConfigurationTest.java
~~~

### 6.2. pom.xml

Tệp pom.xml:

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

    <groupId>com.acme.notice</groupId>
    <artifactId>notice-all-nested-conditions</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

spring-jdbc được đánh dấu optional vì module này cung cấp tích hợp JDBC tùy chọn. Nó có trên compile/test classpath của module để biên dịch code, nhưng Maven không tự truyền dependency này đến mọi consumer. Ứng dụng muốn dùng integration phải tự thêm Spring JDBC hoặc starter tương ứng.

spring-boot-autoconfigure là dependency bắt buộc vì module dùng các annotation và cơ chế auto-configuration.

### 6.3. NoticeHistoryWriter.java

Tệp src/main/java/com/acme/notice/autoconfigure/NoticeHistoryWriter.java:

~~~java
package com.acme.notice.autoconfigure;

public record NoticeHistoryWriter(String jdbcTemplateType) {

    public String describe() {
        return "history-writer:" + jdbcTemplateType;
    }
}
~~~

Đây là bean đại diện cho adapter history trong lab. Nó không giữ JdbcTemplate và không mở kết nối database; field chỉ giúp test quan sát dependency được truyền vào factory method.

### 6.4. NoticeHistoryAutoConfiguration.java

Tệp src/main/java/com/acme/notice/autoconfigure/NoticeHistoryAutoConfiguration.java:

~~~java
package com.acme.notice.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.AllNestedConditions;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;
import org.springframework.jdbc.core.JdbcTemplate;

@AutoConfiguration
public class NoticeHistoryAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @Conditional(OnJdbcAndHistoryEnabled.class)
    static class JdbcHistoryConfiguration {

        @Bean
        @ConditionalOnBean(JdbcTemplate.class)
        @ConditionalOnMissingBean(NoticeHistoryWriter.class)
        NoticeHistoryWriter noticeHistoryWriter(
                JdbcTemplate jdbcTemplate) {

            return new NoticeHistoryWriter(
                    jdbcTemplate.getClass().getSimpleName()
            );
        }
    }

    static class OnJdbcAndHistoryEnabled extends AllNestedConditions {

        OnJdbcAndHistoryEnabled() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnClass(
                name = "org.springframework.jdbc.core.JdbcTemplate"
        )
        static class JdbcTemplatePresent {
        }

        @ConditionalOnProperty(
                prefix = "acme.notice.history",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false
        )
        static class HistoryFeatureEnabled {
        }
    }
}
~~~

Đọc cấu hình theo thứ tự:

1. AutoConfiguration công bố auto-configuration chính.
2. JdbcHistoryConfiguration là nhóm cấu hình chỉ được áp dụng khi OnJdbcAndHistoryEnabled match.
3. OnJdbcAndHistoryEnabled kế thừa AllNestedConditions.
4. JdbcTemplatePresent kiểm tra class JDBC bằng tên class, tránh class literal trong điều kiện tùy chọn.
5. HistoryFeatureEnabled kiểm tra property phải có giá trị true.
6. Constructor chọn PARSE_CONFIGURATION vì hai điều kiện thành viên có thể đánh giá sớm.
7. Bean method kiểm tra JdbcTemplate bean và nhường nếu NoticeHistoryWriter đã được ứng dụng cung cấp.

Nested class JdbcHistoryConfiguration chứa method signature tham chiếu JdbcTemplate. Nó chỉ được xử lý khi nhóm classpath/property match, nhờ vậy ứng dụng không có Spring JDBC có thể bỏ qua phần tích hợp này.

### 6.5. Đăng ký auto-configuration

Nếu đóng gói module thành JAR dùng bởi Spring Boot 3, tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.acme.notice.autoconfigure.NoticeHistoryAutoConfiguration
~~~

File này đăng ký auto-configuration với Spring Boot. Test dùng AutoConfigurations.of(...) sẽ nạp class trực tiếp, vì vậy test đó tập trung vào condition và bean behavior; nó không tự chứng minh imports metadata đã được đóng gói đúng trong JAR.

## 7. Kiểm thử các tổ hợp điều kiện bằng ApplicationContextRunner

ApplicationContextRunner tạo một context riêng cho mỗi lần run(...). Điều này phù hợp để kiểm tra từng tổ hợp classpath, property và bean mà không phải khởi động toàn ứng dụng.

Tệp src/test/java/com/acme/notice/autoconfigure/NoticeHistoryAutoConfigurationTest.java:

~~~java
package com.acme.notice.autoconfigure;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeHistoryAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeHistoryAutoConfiguration.class
                    ));

    @Test
    void createsWriterWhenEveryRequirementMatches() {
        runner.withPropertyValues("acme.notice.history.enabled=true")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NoticeHistoryWriter.class);

                    NoticeHistoryWriter writer =
                            context.getBean(NoticeHistoryWriter.class);

                    assertThat(writer.jdbcTemplateType())
                            .isEqualTo("JdbcTemplate");
                    assertThat(writer.describe())
                            .isEqualTo("history-writer:JdbcTemplate");
                });
    }

    @Test
    void propertyFalseMakesAllNestedConditionsNoMatch() {
        runner.withPropertyValues("acme.notice.history.enabled=false")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(NoticeHistoryWriter.class)
                );
    }

    @Test
    void missingJdbcClassMakesAllNestedConditionsNoMatch() {
        runner.withClassLoader(
                new FilteredClassLoader("org.springframework.jdbc")
        ).withPropertyValues("acme.notice.history.enabled=true")
         .run(context ->
                 assertThat(context)
                         .doesNotHaveBean(NoticeHistoryWriter.class)
         );
    }

    @Test
    void matchingGroupStillNeedsJdbcTemplateBean() {
        runner.withPropertyValues("acme.notice.history.enabled=true")
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(NoticeHistoryWriter.class)
                );
    }

    @Test
    void userWriterMakesDefaultFactoryMethodBackOff() {
        NoticeHistoryWriter custom =
                new NoticeHistoryWriter("application");

        runner.withPropertyValues("acme.notice.history.enabled=true")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .withBean(NoticeHistoryWriter.class, () -> custom)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NoticeHistoryWriter.class);

                    assertThat(context.getBean(NoticeHistoryWriter.class))
                            .isSameAs(custom);
                });
    }
}
~~~

### 7.1. Trường hợp tất cả điều kiện đều match

Test createsWriterWhenEveryRequirementMatches cung cấp:
- Spring JDBC có mặt trên classpath.
- acme.notice.history.enabled=true.
- Một bean JdbcTemplate.

Nhóm AllNestedConditions match, bean method cũng match, vì thế NoticeHistoryWriter được tạo.

Test kiểm tra cả số lượng bean lẫn nội dung jdbcTemplateType để chứng minh đúng factory method đã sử dụng dependency.

### 7.2. Property false

Test propertyFalseMakesAllNestedConditionsNoMatch vẫn cung cấp JdbcTemplate, nhưng property là false.

Một điều kiện thành viên không match làm toàn bộ nhóm không match. Vì nested configuration bị bỏ qua nên writer không xuất hiện.

### 7.3. Thiếu class JDBC

Test missingJdbcClassMakesAllNestedConditionsNoMatch dùng FilteredClassLoader để mô phỏng runtime classpath không có package org.springframework.jdbc.

Property vẫn true nhưng condition classpath không match. Nhóm tổng hợp no-match và nested configuration không được áp dụng.

Đây là cách kiểm tra hữu ích cho integration tùy chọn: core của thư viện có thể chạy trong consumer không cài Spring JDBC, còn adapter JDBC tự được bỏ qua.

### 7.4. Có class và property nhưng thiếu bean JdbcTemplate

Test matchingGroupStillNeedsJdbcTemplateBean có:
- Spring JDBC trên classpath.
- Property bật.
- Không có bean JdbcTemplate.

Hai nested conditions của AllNestedConditions đều match, nhưng bean method có ConditionalOnBean(JdbcTemplate.class) không match. Kết quả writer vẫn không xuất hiện.

Trường hợp này chứng minh AllNestedConditions chỉ giải quyết nhóm classpath/property đã khai báo. Nó không tự thay thế condition bean ở tầng đăng ký bean.

### 7.5. Ứng dụng cung cấp writer tùy chỉnh

Test userWriterMakesDefaultFactoryMethodBackOff cung cấp đủ điều kiện và thêm một bean NoticeHistoryWriter tùy chỉnh.

Nhóm tổng hợp match. ConditionalOnBean(JdbcTemplate.class) cũng match, nhưng ConditionalOnMissingBean(NoticeHistoryWriter.class) không match. Context giữ nguyên instance của ứng dụng.

Đây là hành vi back-off mong muốn của auto-configuration.

## 8. Chạy test và kết quả mong đợi

Từ thư mục dự án có pom.xml:

~~~bash
mvn clean test
~~~

Kỳ vọng năm test trong NoticeHistoryAutoConfigurationTest đều PASS:

| Test | Nhóm classpath + property | Bean JdbcTemplate | Kết quả |
| --- | --- | --- | --- |
| createsWriterWhenEveryRequirementMatches | Match | Có | Writer mặc định được tạo |
| propertyFalseMakesAllNestedConditionsNoMatch | No match | Có | Không có writer |
| missingJdbcClassMakesAllNestedConditionsNoMatch | No match | Không thể có | Không có writer |
| matchingGroupStillNeedsJdbcTemplateBean | Match | Không | Không có writer |
| userWriterMakesDefaultFactoryMethodBackOff | Match | Có | Giữ writer tùy chỉnh |

Maven Surefire in tổng số test, số test lỗi, số test thất bại và thời gian chạy. Thông tin thời gian có thể khác giữa máy; không dùng nó làm assertion.

Không cần database server vì lab chỉ kiểm tra việc tạo bean và sử dụng JdbcTemplate như dependency. Trong ứng dụng thực tế, adapter có thể gọi SQL; khi đó cần integration test riêng với database phù hợp.

## 9. Đọc ConditionEvaluationReport để hiểu nhóm condition

Khi một test thất bại, có thể đọc ConditionEvaluationReport trong callback của runner để xem source nào match hoặc no-match.

Ví dụ helper:

~~~java
private static void printConditionReport(
        org.springframework.context.ApplicationContext context) {

    var report = ConditionEvaluationReport.find(
            ((org.springframework.context.ConfigurableApplicationContext) context)
                    .getBeanFactory()
    );

    if (report == null) {
        System.out.println("Condition report not available");
        return;
    }

    report.getConditionAndOutcomesBySource()
            .forEach((source, outcomes) -> {
                System.out.println(
                        source + " => "
                                + (outcomes.isFullMatch()
                                    ? "MATCH"
                                    : "NO MATCH")
                );

                outcomes.forEach(item -> {
                    var outcome = item.getOutcome();

                    System.out.println(
                            "  " + item.getCondition().getClass().getSimpleName()
                                    + " => "
                                    + (outcome.isMatch()
                                        ? "MATCH"
                                        : "NO MATCH")
                                    + " : "
                                    + outcome.getMessage()
                    );
                });
            });
}
~~~

Trong callback của ApplicationContextRunner, context là AssertableApplicationContext. Có thể lấy source application context rồi truyền vào helper trên. Mã helper dùng ApplicationContext để minh họa cách lấy BeanFactory; khi dùng trong test, cần import ConditionEvaluationReport.

Report có thể cho biết custom condition tổng hợp không match và message tổng hợp từ nested conditions. Không nên so sánh toàn bộ message với chuỗi cố định vì wording có thể thay đổi giữa các bản Spring Boot.

Phân biệt:
- Report cho biết condition nào match/no-match.
- Assertion bean cho biết kết quả cuối trong context.
- Stack trace cho biết lỗi tạo bean nếu condition đã match nhưng factory method hoặc constructor thất bại.

Cần dùng cả ba loại bằng chứng khi điều tra lỗi.

## 10. Kết hợp với property condition và classpath condition trực tiếp

Nếu một cấu hình chỉ có hai điều kiện, có thể đặt trực tiếp:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "org.springframework.jdbc.core.JdbcTemplate")
@ConditionalOnProperty(
        prefix = "acme.notice.history",
        name = "enabled",
        havingValue = "true"
)
public class NoticeHistoryAutoConfiguration {
}
~~~

Nhiều condition annotation trên cùng configuration được kết hợp theo AND. Đây là lựa chọn đơn giản khi không cần tên condition tổng hợp hoặc tái sử dụng.

Dùng AllNestedConditions khi muốn đóng gói nhóm điều kiện:

~~~java
@Conditional(OnJdbcAndHistoryEnabled.class)
class JdbcHistoryConfiguration {
}
~~~

So sánh:

| Tiêu chí | Annotation trực tiếp | AllNestedConditions |
| --- | --- | --- |
| Điều kiện AND đơn giản | Rất phù hợp | Có thể dùng nhưng dài hơn |
| Tái sử dụng nhóm điều kiện | Cần lặp annotation hoặc meta-annotation | Có condition class có tên |
| Nhóm nhiều nhánh | Khó tổ chức khi phức tạp | Mỗi nhánh là nested class |
| Đọc tên quy tắc | Đọc từng annotation | Có thể đọc OnJdbcAndHistoryEnabled |
| Kiểm soát ConfigurationPhase | Theo condition annotations | Chỉ định trong constructor |

Không dùng AllNestedConditions chỉ để thay hai annotation nếu không tạo thêm giá trị về tổ chức hoặc tái sử dụng.

## 11. Các lưu ý về optional dependency và class loading

Khi một điều kiện kiểm tra class tùy chọn:
- Dùng ConditionalOnClass(name = "...") để biểu diễn tên class bằng chuỗi.
- Cô lập method signature cần type tùy chọn trong nested configuration được bảo vệ bởi condition.
- Không để outer/core configuration tham chiếu trực tiếp type tùy chọn trong field, method signature hoặc class literal nếu consumer có thể thiếu dependency.
- Dependency Maven của integration nên được khai báo đúng module và có thể đánh dấu optional nếu consumer cần tự chọn module đó.
- Test bằng FilteredClassLoader để mô phỏng runtime classpath thiếu class.

Ví dụ trong lab, JdbcTemplate chỉ xuất hiện trong nested configuration JdbcHistoryConfiguration. Outer auto-configuration và custom condition không dùng class literal JdbcTemplate trong metadata điều kiện; ConditionalOnClass kiểm tra bằng tên.

Nếu module integration luôn được phát hành cùng spring-jdbc bắt buộc, classpath condition có thể ít cần thiết hơn. Tuy nhiên, khi thiết kế starter tùy chọn hoặc thư viện có nhiều module, condition vẫn giúp kiểm soát rõ việc áp dụng cấu hình.

## 12. Những lỗi phổ biến khi dùng AllNestedConditions

1. **Nhầm AND với OR.** AllNestedConditions yêu cầu mọi nested conditions match; chỉ một điều kiện đúng là chưa đủ.
2. **Dùng sai lớp kết hợp.** Chọn AnyNestedCondition nếu chỉ cần một nhánh, NoneNestedConditions nếu không nhánh nào được match.
3. **Quên gọi constructor cha.** Lớp con phải truyền ConfigurationPhase cho AllNestedConditions.
4. **Chọn phase tùy tiện.** Phase phải phù hợp với các nested conditions; classpath/property thường dùng PARSE_CONFIGURATION.
5. **Trộn condition phụ thuộc bean vào nhóm parse phase.** ConditionalOnBean nên được xử lý ở phạm vi và phase đăng ký bean phù hợp.
6. **Nested member class không static.** Các lớp thành viên condition cần là static để Boot phát hiện và đánh giá.
7. **Đặt condition ở phạm vi quá rộng.** Một feature tùy chọn có thể vô tình chặn mọi bean khác trong auto-configuration.
8. **Đưa class tùy chọn vào signature của outer config.** Ứng dụng thiếu dependency có thể gặp lỗi class loading trước khi condition bảo vệ được cấu hình.
9. **Dùng class literal cho optional class sai chỗ.** Với dependency có thể vắng mặt, dùng tên class trong ConditionalOnClass và nested configuration phù hợp.
10. **Cho rằng group match nghĩa là bean chắc chắn tạo.** Bean method vẫn có thể bị ConditionalOnBean hoặc ConditionalOnMissingBean chặn.
11. **Không test từng tổ hợp.** Chỉ test tất cả điều kiện đúng sẽ không phát hiện nhánh property false hoặc thiếu class.
12. **Không test classpath thiếu.** Integration tùy chọn có thể làm ứng dụng core-only lỗi khi runtime không có thư viện bổ sung.
13. **Không test bean dependency thiếu.** Classpath và property đủ nhưng context vẫn có thể thiếu bean mà factory method cần.
14. **Không test user override.** Bean mặc định có thể cạnh tranh với bean do ứng dụng cung cấp.
15. **Dùng condition tổng hợp cho nhóm quá nhỏ.** Hai annotation trực tiếp có thể dễ đọc hơn.
16. **Coi message report là API ổn định.** Nên assert trạng thái và phần nội dung cần thiết, tránh so sánh toàn bộ message.
17. **Không phân biệt no-match có chủ đích với lỗi.** Condition không match thường là cách auto-configuration nhường quyền điều khiển cho ứng dụng.
18. **Dùng property đúng nhưng sai prefix.** Một nested condition không match nếu tên property không đúng contract.
19. **Đặt matchIfMissing không rõ ràng.** Nên quyết định và test hành vi khi property không tồn tại.
20. **Không cập nhật tài liệu property.** Người dùng cần biết từng điều kiện bắt buộc để feature có thể được bật.

## 13. Quy trình thiết kế và kiểm thử nhóm điều kiện

1. Viết yêu cầu bằng ngôn ngữ tự nhiên: feature cần những điều kiện nào cùng đúng?
2. Phân loại từng điều kiện: classpath, property, bean, resource, environment hay điều kiện tùy chỉnh.
3. Xác định phase phù hợp cho từng condition.
4. Chỉ nhóm các điều kiện có phase tương thích vào AllNestedConditions.
5. Tạo nested static class, mỗi class đại diện một điều kiện.
6. Gắn custom condition vào configuration hoặc nested configuration đúng phạm vi.
7. Giữ điều kiện bean ở bean method nếu nó thuộc giai đoạn đăng ký bean.
8. Giữ ConditionalOnMissingBean để hỗ trợ user override khi phù hợp.
9. Viết bảng chân trị cho các tổ hợp quan trọng.
10. Test cả trường hợp tất cả match, một điều kiện no-match và dependency bean thiếu.
11. Dùng FilteredClassLoader kiểm tra optional class vắng mặt.
12. Đọc ConditionEvaluationReport khi cần giải thích nguyên nhân.
13. Chạy mvn clean test và kiểm tra toàn bộ kết quả.
14. Nếu test trực tiếp auto-configuration class, bổ sung consumer/packaged test để xác minh imports metadata trong JAR.

## 14. Checklist nghiệm thu

- [ ] Quy tắc AND được mô tả rõ và phù hợp với AllNestedConditions.
- [ ] Mỗi điều kiện thành viên có nested static class riêng.
- [ ] Constructor gọi super(ConfigurationPhase...).
- [ ] ConfigurationPhase phù hợp với các condition thành viên.
- [ ] Condition tổng hợp được gắn vào đúng configuration.
- [ ] Property condition có prefix, name và havingValue chính xác.
- [ ] Classpath condition bảo vệ dependency tùy chọn.
- [ ] Type tùy chọn được cô lập khỏi outer/core configuration.
- [ ] Điều kiện bean được đặt ở phase/phạm vi phù hợp.
- [ ] ConditionalOnMissingBean hỗ trợ user override.
- [ ] Test khi mọi nested condition đều match.
- [ ] Test khi từng condition thành viên không match.
- [ ] Test khi class tùy chọn vắng mặt.
- [ ] Test khi bean dependency vắng mặt.
- [ ] Test khi ứng dụng cung cấp bean thay thế.
- [ ] Phân biệt All, Any và None bằng bảng chân trị.
- [ ] Report hoặc assertion giúp giải thích lý do no-match.
- [ ] Đã chạy mvn clean test.
- [ ] Metadata AutoConfiguration.imports được kiểm tra riêng nếu đóng gói thành JAR.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** AllNestedConditions match khi nào?  
**Đáp án:** Khi tất cả nested class conditions đều match. Chỉ một điều kiện no-match cũng làm condition tổng hợp no-match.

**Câu 2.** AnyNestedCondition khác AllNestedConditions thế nào?  
**Đáp án:** Any chỉ cần ít nhất một nested condition match; All yêu cầu tất cả match.

**Câu 3.** NoneNestedConditions match khi nào?  
**Đáp án:** Khi không nested condition nào match.

**Câu 4.** Vì sao ví dụ classpath và property dùng PARSE_CONFIGURATION?  
**Đáp án:** Hai điều kiện có thể được đánh giá sớm khi Spring parse configuration class.

**Câu 5.** Vì sao không đưa ConditionalOnBean(JdbcTemplate.class) vào cùng nhóm parse phase trong lab?  
**Đáp án:** Điều kiện bean phụ thuộc bean definitions và phù hợp với giai đoạn đăng ký bean; lab giữ nó ở factory method riêng.

**Câu 6.** Nếu property bật nhưng Spring JDBC class không có, kết quả là gì?  
**Đáp án:** Một nested condition no-match nên toàn bộ AllNestedConditions no-match và nested configuration bị bỏ qua.

**Câu 7.** Nếu nhóm AllNestedConditions match nhưng context không có bean JdbcTemplate thì sao?  
**Đáp án:** Nhóm classpath/property vẫn match, nhưng ConditionalOnBean trên bean method không match nên writer không được tạo.

**Câu 8.** Vì sao cần test bằng FilteredClassLoader?  
**Đáp án:** Để mô phỏng runtime classpath thiếu dependency tùy chọn và chứng minh integration được bỏ qua an toàn.

**Câu 9.** Có phải mọi nhóm AND đều cần AllNestedConditions không?  
**Đáp án:** Không. Các condition đơn giản có thể đặt trực tiếp trên cùng configuration; All hữu ích khi cần tên, tái sử dụng hoặc nhóm logic rõ ràng.

## 16. Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 Javadoc — AllNestedConditions](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AllNestedConditions.html).
- [Spring Boot 3.3.13 Javadoc — AnyNestedCondition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html).
- [Spring Boot 3.3.13 Javadoc — NoneNestedConditions](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/NoneNestedConditions.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html).
- [Spring Boot 3.3.13 Javadoc — FilteredClassLoader](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html).
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).