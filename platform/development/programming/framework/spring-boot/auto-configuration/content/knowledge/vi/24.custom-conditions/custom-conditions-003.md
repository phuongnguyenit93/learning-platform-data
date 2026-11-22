# SpringBootCondition và getMatchOutcome cho kết quả có thể giải thích

## 1. Vì sao custom condition cần giải thích được quyết định?

Spring Boot dùng condition để quyết định có đăng ký một cấu hình hoặc bean hay không. Những annotation có sẵn như **@ConditionalOnClass**, **@ConditionalOnProperty** và **@ConditionalOnMissingBean** đã giải quyết phần lớn nhu cầu thông thường.

Khi viết điều kiện riêng, interface **Condition** của Spring cho phép triển khai **matches(...)** và trả về boolean. Kết quả đó đủ để Spring quyết định cấu hình có được áp dụng hay không, nhưng boolean không tự giải thích vì sao condition khớp hoặc không khớp.

Ví dụ, một integration gateway chỉ hoạt động khi:

- Property **app.gateway.enabled** có giá trị **true**.
- **app.gateway.provider** bằng provider mà cấu hình yêu cầu.
- Thư viện **GatewayClient** có mặt trên classpath.

Nếu bean không được tạo, người vận hành cần biết điều kiện nào thất bại. Chỉ thấy bean vắng mặt không giúp phân biệt property đang tắt, provider sai hay dependency chưa được đóng gói.

**SpringBootCondition** là lớp nền của Spring Boot dành cho condition có kết quả kèm thông điệp chẩn đoán. Thay vì tự viết matches trả về boolean, ta override **getMatchOutcome(...)** để trả về **ConditionOutcome**, gồm trạng thái match/no-match và message mô tả lý do.

## 2. Spring Condition và SpringBootCondition

| Thành phần | Trách nhiệm |
| --- | --- |
| **org.springframework.context.annotation.Condition** | Contract chung của Spring: matches(context, metadata) trả về boolean |
| **SpringBootCondition** | Lớp nền của Boot, bổ sung logging và ghi nhận kết quả condition |
| **getMatchOutcome(...)** | Callback custom mà subclass phải triển khai |
| **ConditionOutcome** | Kết quả match/no-match cùng thông điệp |
| **ConditionMessage** | Builder tạo thông điệp nhất quán, dễ đọc |
| **ConditionEvaluationReport** | Lưu kết quả condition theo class hoặc method được đánh giá |

SpringBootCondition triển khai Condition. Phương thức **matches(...)** của nó là **final**: Boot điều khiển quy trình đánh giá, gọi getMatchOutcome(...), ghi log và ghi kết quả vào báo cáo. Vì vậy, subclass chỉ override getMatchOutcome; không override matches và không tự gọi logOutcome.

Chữ ký quan trọng:

~~~java
public abstract class SpringBootCondition implements Condition {

    public final boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        // Spring Boot điều khiển việc đánh giá và ghi nhận kết quả.
    }

    public abstract ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata);
}
~~~

Đây là chữ ký khái quát để minh họa quan hệ giữa hai method. Khi triển khai, kế thừa class thực tế từ package org.springframework.boot.autoconfigure.condition.

### 2.1. Khi nào nên dùng SpringBootCondition?

Dùng khi điều kiện có logic kết hợp hoặc quy tắc domain riêng mà annotation có sẵn không diễn tả rõ, và người vận hành cần biết nguyên nhân match/no-match.

Ví dụ phù hợp:

- Chọn implementation theo property và classpath capability.
- Kiểm tra resource cùng với một cấu hình đặc biệt.
- Đánh giá tổ hợp nhiều điều kiện có thứ tự và cần thông điệp riêng cho từng nhánh.
- Kiểm tra một provider tùy chỉnh, sau đó giải thích provider nào được chấp nhận.

Với điều kiện đơn giản, ưu tiên annotation có sẵn:

| Nhu cầu | API nên dùng trước |
| --- | --- |
| Class có trên classpath | **@ConditionalOnClass** |
| Property có giá trị cụ thể | **@ConditionalOnProperty** |
| Chưa có bean thay thế | **@ConditionalOnMissingBean** |
| Có bean phù hợp | **@ConditionalOnBean** |
| Có một ứng viên duy nhất | **@ConditionalOnSingleCandidate** |
| Resource tồn tại | **@ConditionalOnResource** |
| Logic riêng cần thông điệp | **SpringBootCondition** |

Custom condition làm tăng trách nhiệm bảo trì. Chỉ tạo nó khi logic thực sự cần thiết; đừng viết lại một annotation có sẵn chỉ để đổi câu chữ log.

## 3. Hiểu các tham số của getMatchOutcome

Method nhận hai tham số:

~~~java
public abstract ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata);
~~~

### 3.1. ConditionContext

ConditionContext cung cấp môi trường đánh giá condition:

| API | Có thể dùng để |
| --- | --- |
| getEnvironment() | Đọc property, profile và Environment |
| getClassLoader() | Kiểm tra class có thể được nạp hay không |
| getResourceLoader() | Tìm resource theo cơ chế Spring |
| getRegistry() | Truy cập bean definition registry nếu có |
| getBeanFactory() | Đọc thông tin BeanFactory khi đã có ở phase hiện tại |

Trong condition, ưu tiên kiểm tra metadata, property, classpath và bean definitions. Không gọi database, HTTP service hoặc tạo bean nghiệp vụ để quyết định condition. Condition được đánh giá trong quá trình xử lý cấu hình; side effect hoặc I/O ở đây làm startup khó dự đoán và khó kiểm thử.

Một condition nên nhanh, xác định và không phụ thuộc trạng thái thay đổi ngẫu nhiên.

### 3.2. AnnotatedTypeMetadata

AnnotatedTypeMetadata mô tả class hoặc method đang mang annotation condition. Nó cho phép đọc attributes mà không cần tạo bean.

Các API thường dùng:

- isAnnotated(annotationName): kiểm tra metadata có annotation hay không.
- getAnnotationAttributes(annotationName): lấy map các thuộc tính của annotation.
- getAllAnnotationAttributes(annotationName): lấy các giá trị annotation trong metadata.

Ví dụ, một annotation riêng có thuộc tính provider. Condition có thể đọc giá trị này từ metadata thay vì hard-code một provider duy nhất.

Không giả định metadata luôn là class. Nếu condition được gắn trên @Bean method, metadata có thể mô tả method đó. Hãy viết code phù hợp với nơi annotation được phép xuất hiện.

## 4. ConditionOutcome và ConditionMessage

### 4.1. ConditionOutcome

ConditionOutcome biểu diễn kết quả của một condition và thông điệp đi kèm.

Các factory method quan trọng:

~~~java
ConditionOutcome.match();
ConditionOutcome.match("reason");
ConditionOutcome.match(conditionMessage);

ConditionOutcome.noMatch("reason");
ConditionOutcome.noMatch(conditionMessage);
~~~

Đọc kết quả qua:

- isMatch(): condition có khớp không.
- getMessage(): thông điệp dạng String hoặc null.
- getConditionMessage(): thông điệp dạng ConditionMessage hoặc null.

Khi viết condition mới, nên trả về thông điệp có ý nghĩa cho cả nhánh match và no-match. Một lý do cụ thể giúp người đọc hiểu cấu hình nào đã đáp ứng hoặc chưa đáp ứng yêu cầu.

### 4.2. ConditionMessage

ConditionMessage cung cấp fluent builder để thông điệp có cấu trúc nhất quán.

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition("GatewayModeCondition");

ConditionMessage matched = message.foundExactly("primary gateway");
ConditionMessage rejected = message.because("provider is not configured");
~~~

Các cách dựng thông điệp thường dùng:

| Builder method | Ý nghĩa |
| --- | --- |
| foundExactly(value) | Tìm thấy chính xác giá trị mong đợi |
| found("bean") | Tìm thấy một hoặc nhiều mục |
| didNotFind("required class") | Không tìm thấy mục bắt buộc |
| available("resource") | Tài nguyên có sẵn |
| notAvailable("resource") | Tài nguyên không có |
| because(reason) | Nêu nguyên nhân |
| items(Style.QUOTE, values) | Liệt kê các giá trị với dấu nháy |
| append(text) | Bổ sung chi tiết vào message đã tạo |

Có thể khởi tạo builder với tên condition và chi tiết:

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition(
                "GatewayModeCondition",
                "provider=primary"
        );
~~~

Dùng tên condition ổn định, mô tả ngắn gọn và tránh đưa thông tin nhạy cảm như password, token hoặc connection string vào message.

### 4.3. Chọn match hoặc noMatch đúng ngữ nghĩa

- Trả ConditionOutcome.match(message) khi toàn bộ điều kiện cần thiết đều đúng.
- Trả ConditionOutcome.noMatch(message) khi cấu hình hợp lệ nhưng điều kiện không được đáp ứng.
- Chỉ ném exception khi startup thực sự phải thất bại theo hợp đồng cấu hình; không dùng exception thay cho một nhánh no-match bình thường.

Không trả về null. Mỗi đường đi trong getMatchOutcome phải tạo một outcome rõ ràng.

**Lưu ý Spring Boot 3.5:** ConditionOutcome.inverse(...) đã deprecated từ 3.5.0 và được đánh dấu for removal ở 4.0.0. Khi cần đảo kết quả, hãy tự tạo outcome mới với thông điệp phù hợp thay vì dùng API này.

## 5. Ví dụ đầy đủ: condition chọn gateway theo provider

Ta tạo một custom condition cho integration gateway. Cấu hình chỉ khớp khi đồng thời:

1. app.gateway.enabled có giá trị true.
2. app.gateway.provider bằng primary, theo thuộc tính của annotation.
3. Class example.gateway.GatewayClient có trên classpath.

Ví dụ dùng Java 17 và Spring Boot 3.5.0.

### 5.1. Cấu trúc project

~~~text
gateway-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── example/
    │   │   │   ├── gateway/
    │   │   │   │   └── GatewayClient.java
    │   │   │   └── autoconfigure/
    │   │   │       ├── ConditionalOnGatewayMode.java
    │   │   │       ├── GatewayModeCondition.java
    │   │   │       ├── GatewayFeature.java
    │   │   │       └── GatewayAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── example/
                └── autoconfigure/
                    └── GatewayModeConditionTests.java
~~~

### 5.2. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>gateway-condition-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

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

### 5.3. Tệp GatewayClient.java

Đây là class đại diện cho thư viện gateway bên ngoài. Trong starter thật, class này thường đến từ dependency riêng.

~~~java
package example.gateway;

public final class GatewayClient {

    public String ping() {
        return "gateway-ready";
    }
}
~~~

### 5.4. Tệp ConditionalOnGatewayMode.java

Annotation này cho phép cấu hình khai báo provider cần chọn. Nó được meta-annotate bằng @Conditional để Spring gọi condition tương ứng.

~~~java
package example.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(GatewayModeCondition.class)
public @interface ConditionalOnGatewayMode {

    String provider();
}
~~~

### 5.5. Tệp GatewayModeCondition.java

~~~java
package example.autoconfigure;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
import org.springframework.util.ClassUtils;

public final class GatewayModeCondition extends SpringBootCondition {

    private static final String ENABLED_PROPERTY = "app.gateway.enabled";
    private static final String PROVIDER_PROPERTY = "app.gateway.provider";
    private static final String REQUIRED_CLIENT = "example.gateway.GatewayClient";

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Map<String, Object> attributes =
                metadata.getAnnotationAttributes(
                        ConditionalOnGatewayMode.class.getName()
                );

        if (attributes == null) {
            return ConditionOutcome.noMatch(
                    ConditionMessage.forCondition("GatewayModeCondition")
                            .because("ConditionalOnGatewayMode metadata is missing")
            );
        }

        String expectedProvider = (String) attributes.get("provider");

        ConditionMessage.Builder message =
                ConditionMessage.forCondition(
                        "GatewayModeCondition",
                        "provider=" + expectedProvider
                );

        String enabled = context.getEnvironment()
                .getProperty(ENABLED_PROPERTY);

        if (!"true".equalsIgnoreCase(enabled)) {
            return ConditionOutcome.noMatch(
                    message.because(ENABLED_PROPERTY + " is not true")
            );
        }

        String actualProvider = context.getEnvironment()
                .getProperty(PROVIDER_PROPERTY);

        if (!expectedProvider.equals(actualProvider)) {
            String reason = (actualProvider == null || actualProvider.isBlank())
                    ? PROVIDER_PROPERTY + " is not set"
                    : PROVIDER_PROPERTY + " is " + actualProvider;

            return ConditionOutcome.noMatch(message.because(reason));
        }

        if (!ClassUtils.isPresent(REQUIRED_CLIENT, context.getClassLoader())) {
            return ConditionOutcome.noMatch(
                    message.didNotFind("required class")
                            .items(ConditionMessage.Style.QUOTE, REQUIRED_CLIENT)
            );
        }

        return ConditionOutcome.match(
                message.foundExactly(REQUIRED_CLIENT)
                        .append(" with " + ENABLED_PROPERTY + "=true"
                                + " and " + PROVIDER_PROPERTY + "=" + expectedProvider)
        );
    }
}
~~~

Đọc code theo thứ tự:

1. Lấy giá trị provider từ annotation metadata.
2. Kiểm tra property bật/tắt.
3. Kiểm tra provider thực tế có trùng provider mà annotation yêu cầu.
4. Kiểm tra class của thư viện bên ngoài.
5. Trả về match/no-match cùng thông điệp mô tả nhánh đã quyết định.

Condition không tạo GatewayClient, không mở kết nối và không gọi bean. Nó chỉ kiểm tra Environment và classpath. Việc tạo object xảy ra sau đó trong bean factory method.

### 5.6. Tệp GatewayFeature.java

~~~java
package example.autoconfigure;

public record GatewayFeature(String provider, String status) {
}
~~~

### 5.7. Tệp GatewayAutoConfiguration.java

Condition được gắn lên nested configuration. Đây là cách cô lập method signature tham chiếu tới dependency tùy chọn: khi condition không khớp, Spring bỏ qua cấu hình con trước khi xử lý các bean method của nó.

~~~java
package example.autoconfigure;

import example.gateway.GatewayClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class GatewayAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnGatewayMode(provider = "primary")
    static class PrimaryGatewayConfiguration {

        @Bean
        GatewayClient gatewayClient() {
            return new GatewayClient();
        }

        @Bean
        GatewayFeature gatewayFeature(GatewayClient client) {
            return new GatewayFeature("primary", client.ping());
        }
    }
}
~~~

Đăng ký auto-configuration trong tệp META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
example.autoconfigure.GatewayAutoConfiguration
~~~

Trong test bên dưới, runner nạp trực tiếp class bằng AutoConfigurations.of(...) nên không phụ thuộc vào việc quét resource imports. Tệp imports vẫn cần thiết khi starter được tiêu thụ bởi một ứng dụng thực tế.

### 5.8. Tệp GatewayModeConditionTests.java

~~~java
package example.autoconfigure;

import example.gateway.GatewayClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayModeConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GatewayAutoConfiguration.class)
                    );

    @Test
    void matchesWhenEnabledProviderAndClientAreAvailable() {
        runner.withPropertyValues(
                        "app.gateway.enabled=true",
                        "app.gateway.provider=primary"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(GatewayFeature.class);

                    GatewayFeature feature =
                            context.getBean(GatewayFeature.class);

                    assertThat(feature.provider()).isEqualTo("primary");
                    assertThat(feature.status()).isEqualTo("gateway-ready");

                    ConditionOutcome outcome = gatewayOutcome(context);
                    assertThat(outcome.isMatch()).isTrue();
                    assertThat(outcome.getMessage())
                            .contains("example.gateway.GatewayClient")
                            .contains("app.gateway.enabled=true");
                });
    }

    @Test
    void doesNotMatchWhenFeatureIsDisabled() {
        runner.withPropertyValues(
                        "app.gateway.enabled=false",
                        "app.gateway.provider=primary"
                )
                .run(context -> {
                    assertThat(context).doesNotHaveBean("gatewayFeature");

                    ConditionOutcome outcome = gatewayOutcome(context);
                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("app.gateway.enabled is not true");
                });
    }

    @Test
    void doesNotMatchWhenProviderIsDifferent() {
        runner.withPropertyValues(
                        "app.gateway.enabled=true",
                        "app.gateway.provider=backup"
                )
                .run(context -> {
                    assertThat(context).doesNotHaveBean("gatewayFeature");

                    ConditionOutcome outcome = gatewayOutcome(context);
                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("app.gateway.provider is backup");
                });
    }

    @Test
    void doesNotMatchWhenRequiredClientIsMissing() {
        runner.withClassLoader(new FilteredClassLoader(GatewayClient.class))
                .withPropertyValues(
                        "app.gateway.enabled=true",
                        "app.gateway.provider=primary"
                )
                .run(context -> {
                    assertThat(context).doesNotHaveBean("gatewayFeature");

                    ConditionOutcome outcome = gatewayOutcome(context);
                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("required class")
                            .contains("example.gateway.GatewayClient");
                });
    }

    private ConditionOutcome gatewayOutcome(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        for (ConditionEvaluationReport.ConditionAndOutcomes outcomes
                : report.getConditionAndOutcomesBySource().values()) {

            for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
                if (item.getCondition() instanceof GatewayModeCondition) {
                    return item.getOutcome();
                }
            }
        }

        throw new AssertionError("GatewayModeCondition was not recorded");
    }
}
~~~

### 5.9. Chạy test

Dùng JDK 17+ và Maven tại thư mục chứa pom.xml:

~~~bash
java -version
mvn -version
mvn test
~~~

**Kết quả mong đợi:** bốn test JUnit pass và Maven kết thúc BUILD SUCCESS nếu dependency tải thành công. Test không gọi System.out.println, nên không có stdout nghiệp vụ cố định. Báo cáo test nằm trong target/surefire-reports.

Đây là kết quả kỳ vọng từ ví dụ; cần chạy Maven trên project để xác nhận theo môi trường thực tế. Ví dụ dùng FilteredClassLoader để giả lập dependency bị thiếu dù class mẫu vẫn tồn tại trong test project.

## 6. Spring Boot ghi nhận và giải thích condition như thế nào?

### 6.1. Logging trong quá trình đánh giá

SpringBootCondition.matches điều phối đánh giá và ghi log dựa trên ConditionOutcome. Thông điệp được tạo trong getMatchOutcome sẽ giúp log giải thích vì sao condition khớp hoặc không khớp.

Nếu message chỉ nói "matched" mà không cho biết lý do, người vận hành vẫn phải tự suy luận. Nên ghi rõ property, class hoặc provider nào đã đáp ứng điều kiện.

Ví dụ về nội dung chẩn đoán có ý nghĩa:

| Kết quả | Thông điệp |
| --- | --- |
| Match | Tìm thấy GatewayClient với enabled=true và provider=primary |
| No match | app.gateway.enabled is not true |
| No match | app.gateway.provider is backup |
| No match | Không tìm thấy required class GatewayClient |

Thông điệp thực tế được render theo ConditionMessage và phiên bản Boot; bảng trên mô tả nội dung, không phải output log nguyên văn.

### 6.2. ConditionEvaluationReport

ConditionEvaluationReport lưu kết quả đánh giá condition, nhóm theo nguồn là configuration class hoặc bean method. Mỗi bản ghi có condition và outcome tương ứng.

API thường dùng:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(beanFactory);

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> results =
        report.getConditionAndOutcomesBySource();
~~~

Mỗi ConditionAndOutcome cung cấp:

- getCondition(): condition đã được đánh giá.
- getOutcome(): kết quả match/no-match cùng message.

Báo cáo này hữu ích khi một auto-configuration có nhiều nested configuration hoặc nhiều bean method cùng condition. Có thể xác định chính xác nhánh nào bị bỏ qua và vì sao.

### 6.3. Xem report khi chạy ứng dụng

Có hai cách phổ biến:

- Chạy ứng dụng với --debug để Spring Boot in condition evaluation report trong log khởi động.
- Nếu ứng dụng có Spring Boot Actuator, dùng endpoint /actuator/conditions khi endpoint đã được cấu hình và expose phù hợp.

Endpoint conditions trình bày các positive/negative matches, condition và message. Nó phục vụ chẩn đoán cấu hình; không nên dùng response của endpoint này làm API nghiệp vụ cho code ứng dụng.

## 7. Quy tắc viết getMatchOutcome dễ bảo trì

### 7.1. Mỗi nhánh no-match phải có lý do riêng

Tránh viết một nhánh chung như:

~~~java
if (!enabled || !providerMatches || !clientPresent) {
    return ConditionOutcome.noMatch("Condition not satisfied");
}
~~~

Thông điệp đó không cho biết người vận hành phải sửa property, provider hay dependency.

Thay vào đó, kiểm tra tuần tự và trả message cụ thể cho nhánh thất bại đầu tiên. Nếu cần hiển thị nhiều điều kiện cùng lúc, hãy tổng hợp các ConditionMessage hoặc dùng một cấu trúc nested condition phù hợp.

### 7.2. Đừng dùng condition để thay thế validation

Condition trả lời câu hỏi "cấu hình này có nên được áp dụng không?". Validation trả lời "cấu hình người dùng nhập có hợp lệ không?".

Ví dụ:

- app.gateway.enabled=false: condition không khớp là bình thường.
- app.gateway.provider=unknown: có thể là no-match hoặc lỗi validation, tùy hợp đồng sản phẩm.
- app.gateway.timeout=-1: đây thường là lỗi cấu hình cần validation, không nên âm thầm biến thành một condition no-match.

Chọn hành vi rõ ràng và tài liệu hóa. Nếu bật feature mà thiếu dependency phải làm startup thất bại, thiết kế fail-fast có chủ đích thay vì để lỗi NoClassDefFoundError xảy ra ở bean khác sau đó.

### 7.3. Tránh side effect và truy cập bean sớm

Trong getMatchOutcome, không nên:

- Gọi context.getBeanFactory().getBean(...) để khởi tạo bean.
- Tạo connection tới database hoặc broker.
- Gửi HTTP request để kiểm tra service bên ngoài.
- Sửa Environment hoặc đăng ký bean definition.
- Ghi file hoặc thay đổi trạng thái ứng dụng.
- Dựa vào thứ tự khởi tạo bean chưa được bảo đảm.

Condition có thể được đánh giá trước khi các bean thông thường tồn tại. Chỉ đọc những metadata và trạng thái cấu hình cần thiết cho quyết định.

### 7.4. Không lặp lại built-in conditions

Nếu chỉ cần kiểm tra class có mặt, dùng @ConditionalOnClass. Nếu chỉ kiểm tra property, dùng @ConditionalOnProperty. Các annotation này đã có message và report tích hợp của Boot.

Custom condition nên tập trung vào phần logic đặc thù, chẳng hạn kết hợp provider annotation, property và classpath capability như ví dụ.

### 7.5. Chọn đúng phase khi phụ thuộc bean definitions

Condition có thể được đánh giá ở các giai đoạn khác nhau của xử lý configuration. Nếu logic phụ thuộc việc bean definitions đã được đăng ký đầy đủ hay chưa, hãy nghiên cứu ConfigurationCondition và ConfigurationPhase trước khi triển khai. Không giả định rằng mọi condition đều chạy sau khi tất cả bean đã tồn tại.

Với kiểm tra bean thông thường, ưu tiên @ConditionalOnBean hoặc @ConditionalOnMissingBean và đặt chúng trong auto-configuration theo thứ tự phù hợp của Spring Boot.

## 8. Lỗi thường gặp

1. **Chỉ trả về boolean bằng Condition.** Vẫn hoạt động, nhưng thiếu outcome message và cơ chế chẩn đoán tích hợp của Spring Boot.
2. **Override matches trong SpringBootCondition.** Method này là final; override getMatchOutcome thay thế.
3. **Trả null từ getMatchOutcome.** Luôn trả ConditionOutcome.match(...) hoặc ConditionOutcome.noMatch(...).
4. **Message quá chung chung.** "Condition failed" không chỉ ra property, class hoặc provider nào cần sửa.
5. **Chỉ tạo message cho nhánh match.** No-match là nhánh người vận hành cần chẩn đoán nhiều nhất; hãy giải thích lý do.
6. **Đọc annotation bằng tên sai.** Dùng đúng tên đầy đủ của custom annotation khi gọi getAnnotationAttributes.
7. **Giả định metadata luôn mô tả class.** Condition gắn trên @Bean method có thể nhận metadata của method.
8. **Tham chiếu optional class trực tiếp trong cấu hình gốc.** Cô lập method signature trong nested configuration có class condition phù hợp.
9. **Dùng class literal để kiểm tra dependency tùy chọn trong chính condition.** Nếu class không có, class literal có thể gây lỗi nạp; dùng tên class cùng classloader hoặc @ConditionalOnClass.
10. **Tạo bean hoặc gọi mạng trong condition.** Điều này gây side effect ở giai đoạn xử lý cấu hình và làm startup khó dự đoán.
11. **Dùng no-match để che giấu cấu hình sai bắt buộc.** Nếu sản phẩm yêu cầu startup thất bại, hãy có validation/fail-fast rõ ràng.
12. **Lặp lại annotation built-in.** Dùng custom condition chỉ khi logic không được biểu diễn rõ bằng API sẵn có.
13. **Dùng ConditionEvaluationReport như API nghiệp vụ.** Report dành cho chẩn đoán; không để logic runtime phụ thuộc nội dung log hoặc endpoint Actuator.
14. **Không test cả hai kết quả.** Cần test match và từng nguyên nhân no-match quan trọng.
15. **Không kiểm tra message trong test.** Bean vắng mặt chưa chứng minh condition giải thích đúng nguyên nhân.
16. **Dùng ConditionOutcome.inverse trong Boot 3.5.** API đã deprecated for removal; tạo outcome mới với message đúng ngữ nghĩa.
17. **Quên classpath test.** Test thường luôn có optional dependency; dùng FilteredClassLoader để xác minh nhánh dependency vắng mặt.
18. **Đưa dữ liệu nhạy cảm vào message.** Không ghi password, token hoặc connection string vào condition report.

## 9. Checklist review custom condition

- [ ] Đã xác định annotation built-in có đáp ứng yêu cầu chưa?
- [ ] Condition có thật sự cần kế thừa SpringBootCondition không?
- [ ] Chỉ override getMatchOutcome, không override matches.
- [ ] Mọi đường đi đều trả ConditionOutcome.
- [ ] Có message rõ cho match và từng nguyên nhân no-match quan trọng.
- [ ] Đọc ConditionContext và AnnotatedTypeMetadata đúng mục đích.
- [ ] Không tạo bean, gọi network, mở database hoặc tạo side effect.
- [ ] Optional class được kiểm tra an toàn và được cô lập trong nested configuration nếu cần.
- [ ] Bean condition dùng @ConditionalOnBean/@ConditionalOnMissingBean khi phù hợp.
- [ ] Có test match, no-match, property thiếu/sai, provider khác và classpath thiếu.
- [ ] Test kiểm tra cả ConditionOutcome.isMatch() và message.
- [ ] Condition report có thể được dùng để chẩn đoán khi startup.
- [ ] Không dùng API đã deprecated như ConditionOutcome.inverse.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** SpringBootCondition khác Condition cơ bản ở điểm nào?  
**Đáp án:** Nó bổ sung logging và ghi nhận kết quả có thông điệp; subclass trả ConditionOutcome thay vì chỉ trả boolean.

**Câu 2.** Method nào cần override khi kế thừa SpringBootCondition?  
**Đáp án:** getMatchOutcome(ConditionContext, AnnotatedTypeMetadata).

**Câu 3.** Có thể override matches(...) không?  
**Đáp án:** Không. matches là final; Spring Boot dùng nó để điều phối việc đánh giá và ghi nhận outcome.

**Câu 4.** ConditionOutcome chứa những gì?  
**Đáp án:** Trạng thái match/no-match và message giải thích kết quả.

**Câu 5.** ConditionMessage.forCondition(...) có tác dụng gì?  
**Đáp án:** Tạo builder để dựng message có cấu trúc nhất quán, với các phần như found, didNotFind và because.

**Câu 6.** AnnotatedTypeMetadata được dùng để làm gì?  
**Đáp án:** Đọc attributes của annotation gắn trên class hoặc method mà không cần tạo bean.

**Câu 7.** Condition có nên gọi database để xác nhận server đang hoạt động không?  
**Đáp án:** Không nên. Condition cần nhanh và xác định; health check hoặc integration test phù hợp hơn cho kết nối thật.

**Câu 8.** Xem condition evaluation report bằng cách nào?  
**Đáp án:** Dùng --debug, đọc ConditionEvaluationReport, hoặc Actuator /actuator/conditions khi endpoint được bật và expose phù hợp.

**Câu 9.** Khi dependency tùy chọn có thể vắng mặt, nên kiểm tra class bằng cách nào?  
**Đáp án:** Dùng ClassUtils.isPresent(className, context.getClassLoader()) hoặc built-in @ConditionalOnClass; tránh class literal trong code phải nạp khi dependency vắng mặt.

**Câu 10.** Vì sao message no-match cần cụ thể?  
**Đáp án:** Nó cho biết chính xác property, provider hoặc class nào không đáp ứng điều kiện, giúp người vận hành sửa cấu hình nhanh hơn.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 API — SpringBootCondition: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html
- Spring Boot 3.5 API — ConditionOutcome: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html
- Spring Boot 3.5 API — ConditionMessage: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html
- Spring Boot 3.5 API — ConditionMessage.Builder: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.Builder.html
- Spring Boot 3.5 API — ConditionEvaluationReport: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Actuator API — Conditions Evaluation Report endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/conditions.html

**Ghi nhớ:** SpringBootCondition giúp custom condition trả lời hai câu hỏi cùng lúc: cấu hình có khớp không và vì sao. Override getMatchOutcome, tạo ConditionOutcome bằng ConditionMessage, để Spring Boot ghi nhận kết quả trong ConditionEvaluationReport, rồi kiểm thử cả match lẫn từng nguyên nhân no-match.
