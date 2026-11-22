# Tránh truy cập mạng, đọc bí mật vào log hoặc khởi tạo bean trong điều kiện

> **Mục tiêu:** Viết custom Spring Condition an toàn, nhanh và có thể dự đoán. Điều kiện chỉ quyết định một cấu hình hoặc bean definition có được đăng ký hay không. Nó không phải nơi kiểm tra dịch vụ bên ngoài đang sống, xác thực secret, ghi log dữ liệu nhạy cảm hoặc lấy một bean để hỏi trạng thái.

Bài học thuộc nhóm **Điều kiện tùy chỉnh**, sử dụng Spring Boot 3.3.x, Spring Framework 6.1.x và Java 17+. Nội dung tập trung vào contract của `Condition`, dữ liệu có thể đọc qua `ConditionContext`, ba ranh giới cần giữ (network, secrets, bean lifecycle), cách viết `SpringBootCondition` có thông điệp chẩn đoán an toàn và cách kiểm thử bằng `ApplicationContextRunner`.

## 1. Condition được gọi để làm gì?

Spring sử dụng `@Conditional` để quyết định một component có đủ điều kiện đăng ký hay không. Với auto-configuration, điều kiện có thể đặt trên:

- Class `@AutoConfiguration` hoặc `@Configuration` để quyết định có áp dụng cả cấu hình hay không.
- Method `@Bean` để quyết định có đăng ký bean definition của method đó hay không.
- Một annotation tổng hợp chứa `@Conditional` để tái sử dụng quy tắc.

Spring đánh giá condition trong giai đoạn xử lý cấu hình, ngay trước khi bean definition tương ứng được đăng ký. Ở thời điểm này, Spring đang xây dựng mô hình bean của context. Các singleton chưa nhất thiết đã được tạo, dependency injection và các bean post-processor cũng chưa hoàn tất.

Vì vậy, custom condition phải tuân theo những giới hạn tương tự `BeanFactoryPostProcessor`: chỉ làm việc với metadata và thông tin cấu hình có sẵn, tuyệt đối không tương tác với bean instance. Điều kiện nên là phép quyết định nhanh, không có side effect và không phụ thuộc trạng thái thay đổi ngoài context.

Hãy phân biệt ba việc:

| Việc cần quyết định | Nơi phù hợp |
| --- | --- |
| Có bật tính năng trong cấu hình hay không? | `@ConditionalOnProperty` hoặc custom condition đọc `Environment` |
| Thư viện/client class có trên classpath hay không? | `@ConditionalOnClass` hoặc kiểm tra `ClassLoader` |
| API/database/secret manager ở xa có đang truy cập được hay không? | Health check, readiness, retry hoặc logic kết nối sau khi ứng dụng khởi động |

Condition quyết định **có đăng ký cấu hình**. Nó không liên tục giám sát hệ thống và cũng không tự chạy lại mỗi khi mạng hoặc dịch vụ bên ngoài đổi trạng thái.

## 2. Ưu tiên condition có sẵn trước khi tự viết

Spring Boot đã cung cấp các condition phổ biến:

| Nhu cầu | Annotation phù hợp |
| --- | --- |
| Có class/thư viện trên classpath | `@ConditionalOnClass` |
| Thiếu class/thư viện trên classpath | `@ConditionalOnMissingClass` |
| Có bean theo type/name | `@ConditionalOnBean` |
| Chưa có bean để default có thể được đăng ký | `@ConditionalOnMissingBean` |
| Property có giá trị cụ thể | `@ConditionalOnProperty` |
| Resource cục bộ có tồn tại | `@ConditionalOnResource` |
| Ứng dụng là Servlet/Reactive web | `@ConditionalOnWebApplication` |
| Ứng dụng không phải web | `@ConditionalOnNotWebApplication` |

Ví dụ property đơn giản:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public class AuditAutoConfiguration {
    // Các @Bean mặc định.
}
~~~

Với boolean, ghi rõ `havingValue` và `matchIfMissing` để người đọc hiểu chính xác giá trị nào bật cấu hình và hành vi khi thiếu property. Nếu chỉ cần kiểm tra một property, không cần tạo một class `Condition` mới.

Chỉ viết custom condition khi quy tắc thực sự không thể biểu diễn rõ bằng các annotation có sẵn, chẳng hạn kết hợp nhiều tín hiệu cấu hình hoặc cần đọc một thuộc tính annotation chuyên biệt. Một condition tự viết làm tăng code cần kiểm thử, tài liệu và bảo trì.

## 3. ConditionContext cung cấp gì?

Method cốt lõi của Spring Condition là:

~~~java
boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata);
~~~

`ConditionContext` cung cấp một số nguồn thông tin ở giai đoạn đăng ký bean definition:

| API | Có thể dùng để |
| --- | --- |
| `context.getEnvironment()` | Đọc property, profile và thông tin môi trường |
| `context.getClassLoader()` | Kiểm tra class có thể được load hay không |
| `context.getResourceLoader()` | Tìm resource theo vị trí phù hợp |
| `context.getRegistry()` | Đọc/kiểm tra bean definition đã đăng ký |
| `context.getBeanFactory()` | Truy cập metadata của BeanFactory nếu có |
| `metadata` | Đọc annotation và thuộc tính của class/method đang được xét |

`getBeanFactory()` có thể trả về `null` nếu BeanFactory không khả dụng trong ngữ cảnh gọi. Dù có BeanFactory, điều đó không biến condition thành nơi lấy bean. Hãy dùng các nguồn này để đọc thông tin cấu hình và định nghĩa, không tạo hoặc truy cập object nghiệp vụ.

### Những thao tác phù hợp

- Đọc một cờ cấu hình không nhạy cảm từ `Environment`.
- Kiểm tra class tùy chọn bằng `ClassUtils.isPresent` hoặc class loader.
- Kiểm tra resource trong classpath hoặc filesystem cục bộ.
- Đọc thuộc tính annotation từ `AnnotatedTypeMetadata`.
- Khi thực sự cần kiểm tra bean definition, chỉ xem metadata đăng ký và chú ý thứ tự xử lý. Với nhu cầu thông thường, dùng `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`.

### Những thao tác không phù hợp

- Gọi `context.getBeanFactory().getBean(...)` để lấy bean instance.
- Gọi `getBean`, `getBeansOfType` hoặc `ObjectProvider.getObject()` để khởi tạo dependency.
- Tạo client/service bằng `new` rồi gọi method để hỏi trạng thái.
- Gọi HTTP, mở socket, ping database, truy vấn DNS hoặc gọi secret manager.
- Ghi file, thay system property, đăng ký bean thủ công hoặc tạo thread.
- Ghi toàn bộ `Environment`, annotation metadata hoặc connection URL ra log.

## 4. Vì sao không được truy cập mạng trong condition?

Giả sử một auto-configuration chỉ muốn đăng ký `AuditClient` khi audit server đang hoạt động. Cách viết dễ nghĩ tới nhưng không an toàn là gửi HTTP request hoặc mở socket ngay trong `matches(...)`.

Việc này gây ra nhiều vấn đề:

1. **Startup phụ thuộc mạng:** DNS chậm, firewall, proxy hoặc dịch vụ tạm thời mất kết nối có thể kéo dài hoặc làm hỏng quá trình tạo context.
2. **Timeout khó kiểm soát:** Mỗi lần refresh/test có thể phải chờ request. Một test unit nhỏ bất ngờ trở thành test tích hợp phụ thuộc môi trường.
3. **Kết quả không ổn định:** Cùng một cấu hình có thể match lúc này nhưng không match vài giây sau chỉ vì network fluctuation.
4. **Sai thời điểm:** Condition được đánh giá khi Spring xử lý cấu hình, không phải mỗi lần người dùng gọi service.
5. **Khó chẩn đoán:** Lỗi DNS/HTTP bị biến thành lỗi condition, khiến nguyên nhân startup khó tìm.
6. **Có thể tạo side effect:** Request kiểm tra có thể tạo audit event, ghi dữ liệu, tiêu thụ rate limit hoặc kích hoạt authentication flow.

Ví dụ không nên làm:

~~~java
public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata) {

    // Không gọi HTTP, socket, DNS hoặc database tại đây.
    return remoteAuditServerResponds();
}
~~~

Nếu chỉ cần biết tính năng được cấu hình bật hay không, đọc property. Nếu cần biết thư viện client có sẵn hay không, kiểm tra classpath. Nếu cần biết server có thật sự khỏe hay không, thực hiện health check sau khi context được tạo, ví dụ qua `HealthIndicator`, readiness check hoặc logic retry/circuit breaker của client.

**Không biến điều kiện startup thành health check.** Connectivity là trạng thái động; condition là quyết định đăng ký cấu hình tại một giai đoạn khởi tạo.

## 5. Không đọc secret vào thông điệp chẩn đoán hoặc log

Spring Boot có thể ghi nhận kết quả condition trong `ConditionEvaluationReport`. Với `SpringBootCondition`, thông điệp của `ConditionOutcome` được dùng để hỗ trợ giải thích vì sao condition match hoặc không match. Báo cáo có thể được in khi bật debug hoặc qua listener kiểm thử.

Do đó, thông điệp condition phải được xem như dữ liệu có khả năng xuất hiện trong log.

Không viết:

~~~java
String token = context.getEnvironment()
        .getProperty("acme.audit.token");

return ConditionOutcome.noMatch(
        "Invalid audit token: " + token);
~~~

Cũng không ghi username/password, bearer token, API key, private key, cookie, header xác thực, URL chứa user-info hoặc toàn bộ property source vào log. Không đưa secret vào exception message, condition outcome, assertion message hay telemetry.

### 5.1. Nếu chỉ cần biết secret đã được cấu hình

Dùng `Environment.containsProperty` để kiểm tra sự hiện diện của khóa mà không lấy giá trị secret:

~~~java
boolean credentialConfigured = context.getEnvironment()
        .containsProperty("acme.audit.token");

return credentialConfigured
        ? ConditionOutcome.match("Audit credential is configured")
        : ConditionOutcome.noMatch("Audit credential is not configured");
~~~

Thông điệp chỉ nói secret đã được cấu hình hay chưa; nó không tiết lộ nội dung. Lưu ý `containsProperty` chỉ kiểm tra property có tồn tại, không chứng minh giá trị không rỗng hoặc credential hợp lệ.

Nếu cần xác thực format hoặc yêu cầu bắt buộc của secret, dùng configuration binding và validation thích hợp, hoặc để client xử lý lỗi xác thực ở lifecycle phù hợp. Không in giá trị thô khi validation thất bại.

### 5.2. Viết thông điệp condition an toàn

Thông điệp tốt nên:

- Nêu tên property không nhạy cảm và kết quả boolean.
- Nêu class/resource cần có hoặc thiếu bằng tên kỹ thuật.
- Nêu lý do match/no-match ngắn gọn.
- Không chèn giá trị property tùy ý nếu không biết nó có nhạy cảm hay không.
- Không dump object, Environment, request, exception từ remote service hoặc secret source.

Ví dụ an toàn:

~~~text
acme.audit.enabled is true
Optional audit transport class is not present
Audit credential is configured
Audit auto-configuration is disabled
~~~

Các thông điệp trên giúp đọc condition report mà không tiết lộ credential.

## 6. Không khởi tạo hoặc lấy bean trong condition

Bean cần được tạo theo lifecycle của Spring. Nếu condition gọi BeanFactory để lấy một object, bean có thể bị khởi tạo quá sớm, trước khi các post-processor và bước cấu hình cần thiết hoàn tất.

Ví dụ không nên làm:

~~~java
@Override
public ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata) {

    AuditClient client = context.getBeanFactory()
            .getBean(AuditClient.class);

    return client.isReady()
            ? ConditionOutcome.match("Audit client is ready")
            : ConditionOutcome.noMatch("Audit client is not ready");
}
~~~

Các rủi ro:

- Bean có thể được tạo trước khi `@ConfigurationProperties` binding hoàn tất.
- Bean có thể chưa đi qua `BeanPostProcessor` hoặc proxy cần thiết.
- Dependency của bean có thể chưa được đăng ký hoặc chưa sẵn sàng.
- Việc tạo bean có thể mở connection, tạo thread hoặc gọi hệ thống bên ngoài.
- Condition vô tình làm thay đổi chính trạng thái mà nó đang cố đánh giá.

Không gọi `getBean`, `getBeansOfType` hoặc `ObjectProvider.getObject()` bên trong condition. Cũng không tự gọi constructor của client để thay thế BeanFactory; cách đó bỏ qua dependency injection và lifecycle của Spring.

### 6.1. Dùng bean conditions thay cho lấy bean instance

Nếu muốn default chỉ xuất hiện khi ứng dụng chưa cung cấp bean:

~~~java
@Bean
@ConditionalOnMissingBean(AuditClient.class)
AuditClient auditClient() {
    return new AuditClient();
}
~~~

Nếu bean phụ chỉ cần xuất hiện khi provider đã được đăng ký:

~~~java
@Bean
@ConditionalOnBean(AuditTransport.class)
AuditPublisher auditPublisher(AuditTransport transport) {
    return new AuditPublisher(transport);
}
~~~

Spring Boot đánh giá bean conditions dựa trên các bean definitions đã được xử lý tới thời điểm đó. Vì thế, hãy đặt chúng trên auto-configuration và khai báo thứ tự phù hợp khi phụ thuộc một provider khác. Tài liệu Boot khuyến nghị dùng `@ConditionalOnBean` và `@ConditionalOnMissingBean` trong auto-configuration vì chúng được xử lý sau các bean definition do người dùng khai báo.

### 6.2. Cẩn thận với @ConditionalOnExpression

`@ConditionalOnExpression` có thể dùng SpEL để quyết định điều kiện. Tuy nhiên, nếu expression tham chiếu bean bằng cú pháp `@someBean`, bean đó sẽ được khởi tạo rất sớm trong lúc refresh context. Nó có thể chưa được post-process, chưa bind cấu hình và có state chưa hoàn chỉnh.

Không viết:

~~~java
@ConditionalOnExpression("@auditClient.ready")
@Configuration
class AuditConfiguration {
}
~~~

Nếu chỉ kiểm tra property, dùng `@ConditionalOnProperty`. Nếu cần quy tắc tổng hợp, viết custom `Condition` đọc `Environment` và metadata, không gọi bean.

## 7. Mẫu custom condition an toàn với SpringBootCondition

Spring Framework cung cấp interface `Condition` với method `matches` trả về boolean. Spring Boot bổ sung lớp cơ sở `SpringBootCondition` để condition trả về `ConditionOutcome` có thông điệp giải thích.

Mẫu dưới đây kiểm tra một cờ property không nhạy cảm. Condition không đọc credential, không gọi mạng và không lấy bean.

**Tệp:** `src/main/java/com/acme/audit/autoconfigure/AuditFeatureEnabledCondition.java`

~~~java
package com.acme.audit.autoconfigure;

import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class AuditFeatureEnabledCondition extends SpringBootCondition {

    private static final String PROPERTY = "acme.audit.enabled";

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        boolean enabled = context.getEnvironment()
                .getProperty(PROPERTY, Boolean.class, Boolean.FALSE);

        if (enabled) {
            return ConditionOutcome.match(PROPERTY + " is true");
        }

        return ConditionOutcome.noMatch(PROPERTY + " is not true");
    }
}
~~~

Giải thích:

- `SpringBootCondition` triển khai contract `Condition` của Spring.
- `getMatchOutcome` nhận `ConditionContext` và metadata của class/method.
- `getEnvironment()` chỉ đọc property trong Environment hiện tại.
- Giá trị mặc định là `false` nên khi property thiếu, condition không match.
- `ConditionOutcome.match(...)` và `noMatch(...)` trả kết quả cùng thông điệp chẩn đoán.
- Thông điệp chỉ chứa tên property boolean và trạng thái; không có giá trị bí mật.

Đây là ví dụ để hiểu custom condition. Trong ứng dụng thực tế, vì quy tắc chỉ là một boolean property, `@ConditionalOnProperty` ngắn và phù hợp hơn. Hãy giữ custom condition cho trường hợp có logic thực sự đặc thù.

## 8. Dùng custom condition trên auto-configuration

Một client mẫu:

**Tệp:** `src/main/java/com/acme/audit/AuditClient.java`

~~~java
package com.acme.audit;

public final class AuditClient {

    public AuditClient() {
        // Khởi tạo object cục bộ; không mở kết nối mạng tại constructor.
    }

    public String name() {
        return "audit-client";
    }
}
~~~

Auto-configuration:

**Tệp:** `src/main/java/com/acme/audit/autoconfigure/AuditAutoConfiguration.java`

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Lazy;

@AutoConfiguration
@Conditional(AuditFeatureEnabledCondition.class)
public class AuditAutoConfiguration {

    @Bean
    @Lazy
    @ConditionalOnMissingBean(AuditClient.class)
    public AuditClient auditClient() {
        return new AuditClient();
    }
}
~~~

Có ba lớp quyết định riêng:

1. `@Conditional(AuditFeatureEnabledCondition.class)` quyết định toàn bộ auto-configuration có được áp dụng không.
2. `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp `AuditClient` riêng và khiến bean mặc định nhường chỗ.
3. `@Lazy` trì hoãn việc tạo instance cho đến khi có bean khác yêu cầu hoặc ứng dụng lấy bean. Annotation này minh họa rõ rằng condition có thể đăng ký bean definition mà không cần tạo object ngay.

Trong JAR phát hành, auto-configuration vẫn phải được đăng ký theo cơ chế imports của Spring Boot:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

Imports resource giúp Boot phát hiện class. Nó không làm thay đổi các nguyên tắc an toàn của custom condition.

## 9. Kiểm thử condition mà không cần mạng thật

`ApplicationContextRunner` cho phép kiểm tra condition trong context nhỏ, mỗi test đặt property riêng. Không cần mở HTTP connection hoặc dùng database thật để kiểm tra việc đăng ký bean.

**Tệp:** `src/test/java/com/acme/audit/autoconfigure/AuditAutoConfigurationTests.java`

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class));

    @Test
    void enabledPropertyRegistersLazyClientDefinition() {
        runner.withPropertyValues("acme.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("auditClient");

                    // Bean definition đã có, nhưng @Lazy chưa tạo singleton.
                    assertThat(context.getBeanFactory()
                            .containsSingleton("auditClient")).isFalse();

                    AuditClient client = context.getBean(AuditClient.class);
                    assertThat(client.name()).isEqualTo("audit-client");

                    // Bean chỉ được tạo sau khi test yêu cầu lấy nó.
                    assertThat(context.getBeanFactory()
                            .containsSingleton("auditClient")).isTrue();
                });
    }

    @Test
    void falsePropertyDoesNotRegisterClient() {
        runner.withPropertyValues("acme.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(AuditClient.class);
                });
    }

    @Test
    void missingPropertyDoesNotRegisterClient() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(AuditClient.class);
        });
    }
}
~~~

Test đầu chứng minh condition cho phép đăng ký bean definition khi property true, nhưng việc tạo instance vẫn theo lazy lifecycle. Hai test còn lại chứng minh property false hoặc thiếu thì cấu hình không đăng ký client.

Dependency test với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
~~~

Chạy:

~~~bash
./gradlew test --tests com.acme.audit.autoconfigure.AuditAutoConfigurationTests
~~~

Hoặc Maven:

~~~bash
mvn -Dtest=AuditAutoConfigurationTests test
~~~

**Kết quả mong đợi:** 3 test PASS. Đây là kiểm thử condition và bean registration trong context cục bộ; không có request mạng hoặc truy vấn database. Test không mô phỏng health check của audit server vì health check thuộc một lớp kiểm thử khác.

## 10. Kiểm tra condition report mà không làm lộ secret

Spring Boot lưu kết quả đánh giá condition trong `ConditionEvaluationReport`. Báo cáo nhóm các outcome theo class hoặc method và có thể dùng để giải thích vì sao một auto-configuration được áp dụng hoặc bị bỏ qua.

Có thể bật báo cáo khi chạy ứng dụng:

~~~bash
java -jar app.jar --debug
~~~

Hoặc dùng `ConditionEvaluationReportLoggingListener` trong kiểm thử để in report ở mức log phù hợp. Khi dùng các công cụ này:

- Chỉ trả thông điệp tĩnh, an toàn từ `ConditionOutcome`.
- Không ghép giá trị token/password/API key vào message.
- Không log toàn bộ Environment hoặc property sources.
- Không bật debug vô thời hạn ở production nếu report có thể làm lộ thông tin cấu hình nội bộ.
- Khi cần chẩn đoán, ghi tên property và trạng thái đã cấu hình hay chưa.

Ví dụ message tốt:

~~~java
return ConditionOutcome.noMatch(
        "Audit integration is disabled by configuration");
~~~

Ví dụ message không an toàn:

~~~java
return ConditionOutcome.noMatch(
        "Audit token rejected: " + token);
~~~

Nếu lỗi xác thực cần được điều tra, log một mã lỗi đã chuẩn hóa hoặc correlation ID không nhạy cảm. Không log credential để tiện debug.

## 11. Nếu cần kiểm tra bean definition, hãy tránh khởi tạo bean

Đôi khi custom condition cần biết một bean definition đã được đăng ký hay chưa. Có thể đọc metadata từ `BeanDefinitionRegistry` qua `context.getRegistry()`, nhưng phải chú ý thời điểm và thứ tự đăng ký.

Ví dụ kiểm tra sự hiện diện của một bean definition theo tên:

~~~java
boolean definitionExists =
        context.getRegistry().containsBeanDefinition("auditTransport");
~~~

Phép kiểm tra trên chỉ hỏi registry có definition tên đó hay không. Nó không lấy object instance. Tuy nhiên, nếu mục tiêu là điều kiện bean theo type hoặc cho phép user bean override, các annotation có sẵn thường rõ và an toàn hơn:

~~~java
@Bean
@ConditionalOnBean(AuditTransport.class)
AuditPublisher auditPublisher(AuditTransport transport) {
    return new AuditPublisher(transport);
}
~~~

Đừng tự duyệt tất cả singleton hoặc gọi factory method để suy ra bean có hoạt động hay không. Một bean definition có thể tồn tại nhưng bean chưa được tạo; đó là trạng thái bình thường của lazy bean. Khả năng kết nối hoặc tính sẵn sàng của bean phải được đánh giá ở lifecycle phù hợp.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gửi HTTP request trong `matches` | Startup chậm, phụ thuộc mạng và kết quả không ổn định | Chỉ đọc cấu hình/classpath; dùng health/readiness check sau startup |
| Ping database để quyết định đăng ký bean | Context không tạo được khi DB tạm mất kết nối | Đăng ký client theo cấu hình; kiểm tra kết nối trong lifecycle/health indicator |
| Log raw token hoặc password trong `ConditionOutcome` | Secret có thể xuất hiện trong debug report và log | Chỉ ghi tên property và trạng thái boolean/sự hiện diện |
| Gọi `getBean` từ BeanFactory | Khởi tạo bean quá sớm, bỏ qua một phần lifecycle dự kiến | Dùng metadata hoặc built-in bean conditions |
| Dùng `@ConditionalOnExpression` tham chiếu bean | Bean bị khởi tạo sớm trong lúc refresh | Dùng property condition hoặc custom Condition đọc Environment |
| Tạo client bằng `new` trong condition | Side effect và object không thuộc lifecycle Spring | Để method `@Bean` tạo bean theo lifecycle container |
| Kiểm tra remote endpoint một lần khi startup | Quyết định condition nhanh chóng lỗi thời khi network đổi trạng thái | Theo dõi health/readiness sau khi ứng dụng chạy |
| Condition giữ mutable state hoặc phụ thuộc thời gian | Kết quả khó tái lập và khó test | Viết condition stateless, deterministic và nhanh |
| Dùng custom condition cho một boolean property | Tăng code và công bảo trì không cần thiết | Ưu tiên `@ConditionalOnProperty` |
| Đặt bean condition sai thứ tự | Condition không nhìn thấy definition cần thiết tại thời điểm đánh giá | Dùng auto-configuration ordering và kiểm thử thứ tự |

### 12.1. Checklist review một custom condition

- [ ] Condition chỉ đọc Environment, metadata, classpath, local resource hoặc bean definition metadata.
- [ ] Không có HTTP, socket, DNS, database, secret manager hoặc I/O từ xa.
- [ ] Không gọi `getBean`, `getBeansOfType` hoặc `ObjectProvider.getObject()`.
- [ ] Không tạo client/service hoặc thread trong `matches` / `getMatchOutcome`.
- [ ] Không log hoặc trả về secret value trong `ConditionOutcome`.
- [ ] Message chẩn đoán ngắn, ổn định và không nhạy cảm.
- [ ] Logic stateless, deterministic và có thời gian thực thi nhỏ.
- [ ] Dùng built-in condition khi có thể.
- [ ] Có test cho match, no-match và property/classpath biên.
- [ ] Health/readiness được xử lý sau startup nếu cần quan sát dịch vụ bên ngoài.

## 13. Quy trình thiết kế condition an toàn

Khi có yêu cầu mới, hãy đi theo thứ tự:

1. Xác định quyết định cần đưa ra là về đăng ký bean, cấu hình property, classpath hay trạng thái vận hành.
2. Tìm annotation có sẵn phù hợp trước.
3. Nếu cần custom, liệt kê chính xác các tín hiệu cục bộ mà condition được phép đọc.
4. Không dùng network hoặc secret value làm dữ liệu chẩn đoán.
5. Không lấy bean instance; nếu cần bean presence, dùng built-in bean conditions.
6. Trả về match/no-match với thông điệp không nhạy cảm.
7. Kiểm thử cả trường hợp match, no-match, thiếu property và bean user override.
8. Nếu cần kiểm tra connectivity, thiết kế health/readiness test riêng sau khi context khởi động.

Một custom condition tốt có thể giải thích bằng một câu: "Dựa trên metadata và cấu hình hiện có, điều kiện này cho phép hoặc từ chối đăng ký bean." Nếu phải khởi tạo ứng dụng con, gọi remote service hoặc lấy credential để trả lời, logic đã đi quá xa trách nhiệm của condition.

## 14. Tự kiểm tra kiến thức

1. Khi nào Spring đánh giá một `Condition`?  
   **Đáp án:** Trong quá trình xử lý cấu hình, ngay trước khi bean definition tương ứng được đăng ký.

2. Vì sao không được gọi `getBean` trong custom condition?  
   **Đáp án:** Condition phải tuân theo giới hạn của BeanFactoryPostProcessor và không tương tác với bean instance; lấy bean có thể khởi tạo nó quá sớm.

3. Vì sao không ping API/database từ condition?  
   **Đáp án:** Nó làm startup phụ thuộc mạng, tạo timeout và kết quả không ổn định; condition cũng không được đánh giá liên tục khi connectivity đổi.

4. Thông điệp `ConditionOutcome` có thể chứa token không?  
   **Đáp án:** Không. Outcome có thể xuất hiện trong condition report và log; chỉ ghi lý do đã được làm sạch, không ghi secret.

5. Nếu chỉ cần biết secret property có được cấu hình không, có thể dùng API nào?  
   **Đáp án:** `Environment.containsProperty` để kiểm tra sự hiện diện mà không lấy raw value. Nó không thay thế validation về giá trị hợp lệ.

6. Khi chỉ kiểm tra một boolean property, có cần custom condition không?  
   **Đáp án:** Không. `@ConditionalOnProperty` thường ngắn và dễ bảo trì hơn.

7. `@ConditionalOnExpression` tham chiếu một bean có thể gây vấn đề gì?  
   **Đáp án:** Bean có thể bị khởi tạo rất sớm, trước post-processing và configuration-properties binding, khiến state chưa hoàn chỉnh.

8. Nếu cần kiểm tra server có khỏe sau startup, nên dùng gì?  
   **Đáp án:** Health indicator, readiness check hoặc logic giám sát/retry ở runtime, không dùng condition đăng ký bean.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition annotations, bean conditions, property conditions và cảnh báo SpEL tham chiếu bean.
- [Spring Boot 3.3 API — SpringBootCondition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html): lớp cơ sở cho condition của Boot và method `getMatchOutcome`.
- [Spring Boot 3.3 API — ConditionOutcome](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html): kết quả match/no-match cùng thông điệp chẩn đoán.
- [Spring Boot 3.3 API — ConditionEvaluationReport](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): nơi lưu condition evaluation details để reporting/logging.
- [Spring Framework 6.1 — Condition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html): contract của `Condition`, thời điểm đánh giá và yêu cầu không tương tác với bean instance.
- [Spring Framework 6.1 — ConditionContext Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html): Environment, ClassLoader, ResourceLoader, BeanDefinitionRegistry và BeanFactory có thể truy cập.

**Ghi nhớ:** Custom condition chỉ nên đưa ra quyết định từ thông tin cục bộ, có sẵn trong giai đoạn đăng ký bean definition. Không truy cập mạng, không đưa secret vào outcome/log và không khởi tạo hoặc lấy bean instance. Hãy dùng built-in conditions khi đủ, custom condition khi thật sự cần, còn health/connectivity thì kiểm tra sau startup.
