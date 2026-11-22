# Kiểm tra loại bean, số lượng bean và thuộc tính cấu hình

## Mục tiêu

Trong nhóm **Kiểm thử auto-configuration** của **Spring Boot - testing**, một test không nên chỉ xác nhận ApplicationContext khởi động. Nó cần trả lời chính xác: **bean thuộc loại nào, có bao nhiêu bean theo một interface, auto-configuration có tạo default bean đúng điều kiện, người dùng có override được không, và thuộc tính cấu hình đã được bind, validate và truyền vào bean thực tế chưa?** Một context vẫn có thể khởi động dù vô tình tạo hai email clients, một DataSource sai endpoint, hoặc một service mang giới hạn mặc định thay vì giá trị do operator nhập.

Bài học dùng **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, JUnit Jupiter, AssertJ và Bean Validation**. Ví dụ hoàn chỉnh xây **AlertAutoConfiguration** cho AlertSender. Khi feature bật và ứng dụng chưa tự cung cấp sender, Spring Boot tạo ConsoleAlertSender; khi feature tắt, không có sender mặc định; khi user đã cung cấp một hoặc hai senders, default bean phải **back off**. Config **acme.alert** gồm enabled, prefix và max-message-length với default/override và validation. Phần kiểm tra nhanh dùng **ApplicationContextRunner**, phần kiểm tra Boot discovery dùng **@SpringBootTest**.

**Phạm vi bằng chứng:** ApplicationContextRunner xác nhận behavior của một auto-configuration được import trực tiếp. Nó **không tự chứng minh** Spring Boot đã phát hiện auto-configuration từ resource **AutoConfiguration.imports**. Vì vậy phải có test discovery riêng. Các expected outcomes là kết quả suy ra từ source; **không tuyên bố đã chạy Gradle thực tế**.

## 1. Ba hợp đồng khác nhau

### Loại bean: contract, implementation và proxy

- **Contract type**: interface hoặc superclass mà consumer yêu cầu inject, ví dụ **AlertSender**.
- **Concrete type**: implementation mặc định, ví dụ **ConsoleAlertSender**, có thể cần assert khi đó là contract của starter.
- **Bean name**: tên như **consoleAlertSender**, hữu ích khi cần phân biệt default bean và user bean; không nên assert tên khi tên chỉ là chi tiết nội bộ có thể refactor.
- **Runtime class**: nếu bean được AOP proxy, runtime getClass() có thể là JDK proxy/CGLIB, không giống class implementation. Nên assert **assignable contract** và behavior, không assert exact getClass() vô cớ.
- **Definition type**: kiểu mà Spring biết từ @Bean return type, BeanDefinition hoặc factory metadata; có thể chưa biết subtype implementation trước khi instantiate.

Khi feature được bật, kiểm tra **có một AlertSender**, **bean thực sự là ConsoleAlertSender** trong context không có proxy, và **phương thức send dùng đúng properties**. Cả ba cùng tạo ra bằng chứng mạnh hơn assertNotNull.

### Số lượng bean: 0, 1 hay 2?

| Trường hợp | Số AlertSender mong đợi | Ý nghĩa |
| --- | --- | --- |
| enabled=false, không có user sender | 0 | Feature default không được đăng ký |
| enabled=true, không có user sender | 1 | Một ConsoleAlertSender |
| Không khai báo enabled, không có user sender | 1 | matchIfMissing=true cho default |
| User cung cấp customSender | 1 | @ConditionalOnMissingBean khiến default back off |
| User cung cấp hai senders | 2 | Có hai user beans, không có default |
| enabled=false nhưng user tự định nghĩa sender | 1 | Điều kiện của default bean không xóa user bean |

**getBean(AlertSender.class)** không đủ để chứng minh chỉ có một bean: nếu có **@Primary**, Spring có thể chọn được một bean dù tồn tại hai candidates. Dùng **getBeanNamesForType(AlertSender.class).length** hoặc **getBeansOfType(AlertSender.class).size()** khi contract yêu cầu count. Nếu hai beans không @Primary/@Qualifier, getBean(type) có thể ném **NoUniqueBeanDefinitionException**.

### Thuộc tính cấu hình

Kiểm tra đồng thời:
1. **Default** khi không cung cấp property.
2. **Override** từ Environment qua withPropertyValues.
3. Giá trị của **@ConfigurationProperties** bean.
4. Giá trị đã được truyền vào **implementation thực**, không chỉ xuất hiện trong Environment.
5. **@ConditionalOnProperty** match/không match.
6. Validation sai cấu hình có khiến startup **fail có chủ đích** không.
7. Property bị gõ sai key có bị test phát hiện nhờ assertion trên giá trị bind thực không.

Một property xuất hiện trong application.yml chưa chứng minh client đã dùng nó. Nếu AlertProperties.prefix là OPS nhưng ConsoleAlertSender vẫn dùng NOTICE, test config phải thất bại.

## 2. Các annotation và cơ chế tự cấu hình

**@AutoConfiguration** là loại configuration được Spring Boot xem xét như ứng viên tự cấu hình, đăng ký trong tệp **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** theo Spring Boot 3.x.

**@ConditionalOnClass** yêu cầu một library/class hiện diện trên classpath; **@ConditionalOnProperty** xét Environment; **@ConditionalOnMissingBean** dùng để tạo default bean khi user chưa có bean thích hợp; **@ConditionalOnBean** yêu cầu dependency bean hiện diện; **@ConditionalOnWebApplication** phụ thuộc web application type; **@EnableConfigurationProperties** đăng ký object nhận type-safe binding; **@ConfigurationProperties** khai báo prefix; **@Validated** kích hoạt Bean Validation cho bound properties khi có validation provider.

Condition được xét trong quá trình xử lý configuration/bean definitions, khác với if/else chạy trong business service. Khi **@ConditionalOnProperty(enabled=false)** đặt trên một @Bean method, method đó không tạo bean; các beans khác trong auto-config class vẫn có thể tồn tại. Khi đặt condition trên cả @AutoConfiguration class, toàn bộ class có thể bị bỏ qua. Vì vậy không đánh đồng **0 AlertSender** với **0 AlertProperties**.

### Vì sao @ConditionalOnMissingBean quan trọng?

Một starter nên nhường chỗ cho application có custom implementation. Nếu auto-config luôn tạo default cùng interface, application có thể có duplicate beans và lỗi injection, hoặc chọn nhầm bean vì @Primary. Trong luồng chuẩn, user-defined configurations được xử lý trước auto-configurations để **@ConditionalOnMissingBean** có thể thấy lựa chọn của user. Đặt điều kiện này trong các @Configuration bị component scan không kiểm soát thứ tự có thể gây khác biệt.

**Tình huống test đúng:** application có một bean AlertSender tên customSender, auto-config phải không tạo consoleAlertSender; count vẫn là một. Nếu application có hai user senders, auto-config cũng không thêm default; count hai là hành vi do user cấu hình, không phải lỗi của auto-config.

## 3. ApplicationContextRunner dùng để tách từng tổ hợp điều kiện

Spring Boot cung cấp **org.springframework.boot.test.context.runner.ApplicationContextRunner**. Nó tạo context riêng cho mỗi callback, chạy các conditions theo tổ hợp property/user configurations bạn chỉ định, rồi đóng context sau callback. Không cần full @SpringBootTest, web server, database hay network.

~~~java
private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(AlertAutoConfiguration.class));

@Test
void disabledFeatureHasNoSender() {
    runner.withPropertyValues("acme.alert.enabled=false")
        .run(context -> {
            assertNull(context.getStartupFailure());
            assertEquals(0, context
                .getBeanNamesForType(AlertSender.class).length);
        });
}
~~~

**withConfiguration(AutoConfigurations.of(...))** nạp một hoặc vài auto-configuration classes; **withUserConfiguration(...)** đưa user beans vào đúng luồng; **withPropertyValues(...)** cung cấp test Environment; **run(...)** cho AssertableApplicationContext để assert type/count/values.

**Không nên test nhiều cases bằng cách thay property của một context đã refresh** rồi mong conditions được đánh giá lại. Mỗi combination phải dùng **context mới**. Đừng dùng System.setProperty toàn JVM khi runner property là đủ; static/global changes dễ ảnh hưởng tests chạy parallel.

Tài liệu Spring Boot lưu ý **ApplicationContextRunner không dùng được khi chính test chạy trong native image**. Khi cần native/AOT compatibility, bổ sung native-specific test strategy.

## 4. Dự án runnable với Spring Boot 3.4.5

### Cây file

~~~text
settings.gradle
build.gradle
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
src/main/java/com/example/alertlib/AlertSender.java
src/main/java/com/example/alertlib/ConsoleAlertSender.java
src/main/java/com/example/alertlib/AlertProperties.java
src/main/java/com/example/alertlib/AlertAutoConfiguration.java
src/main/java/com/example/alertdemo/AlertDemoApplication.java
src/test/java/com/example/alertlib/AlertAutoConfigurationTest.java
src/test/java/com/example/alertdemo/AutoConfigurationDiscoveryTest.java
~~~

Application nằm trong package **com.example.alertdemo**, auto-config nằm ở sibling package **com.example.alertlib**. Điều này giúp chứng minh auto-config phải được tìm qua resource imports thay vì vô tình bị component scan từ @SpringBootApplication.

### settings.gradle

~~~groovy
rootProject.name = 'autoconfiguration-bean-contracts'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter-validation** cung cấp Bean Validation provider để @NotBlank/@Min/@Max thực thi. **spring-boot-configuration-processor** hỗ trợ tạo metadata cho IDE; nó **không phải Binder** và không bắt buộc cho runtime binding. **spring-boot-starter-test** có JUnit Jupiter, AssertJ, ApplicationContextRunner và các test utilities. Dependency management theo Spring Boot BOM tránh tự trộn versions không tương thích.

### Contract interface: AlertSender.java

~~~java
package com.example.alertlib;

public interface AlertSender {
    String send(String recipient, String message);
}
~~~

**AlertSender** là interface mà client sẽ inject. Ví dụ cố tình không gửi network request: send trả về chuỗi deterministic để test behavior không cần external email/SMS service. Production implementation phải có hợp đồng delivery/errors riêng.

### Default implementation: ConsoleAlertSender.java

~~~java
package com.example.alertlib;

import java.util.Objects;

public final class ConsoleAlertSender implements AlertSender {
    private final String prefix;
    private final int maxMessageLength;

    public ConsoleAlertSender(
            String prefix, int maxMessageLength) {
        this.prefix = Objects.requireNonNull(prefix);
        this.maxMessageLength = maxMessageLength;
    }

    public String getPrefix() {
        return prefix;
    }

    public int getMaxMessageLength() {
        return maxMessageLength;
    }

    @Override
    public String send(String recipient, String message) {
        Objects.requireNonNull(recipient, "recipient");
        Objects.requireNonNull(message, "message");

        if (message.length() > maxMessageLength) {
            throw new IllegalArgumentException(
                "message too long");
        }
        return prefix + ":" + recipient + ":" + message;
    }
}
~~~

Trong test default, message hello cho output **NOTICE:anna:hello**. Với prefix OPS và maxMessageLength=5, **OPS:bob:hello** hợp lệ, nhưng abcdef dài 6 phải ném IllegalArgumentException. Như vậy property value được assert qua cả properties bean và **hành vi implementation**.

### Cấu hình có default + validation: AlertProperties.java

~~~java
package com.example.alertlib;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.alert")
public class AlertProperties {
    private boolean enabled = true;

    @NotBlank
    private String prefix = "NOTICE";

    @Min(1)
    @Max(500)
    private int maxMessageLength = 80;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    public int getMaxMessageLength() {
        return maxMessageLength;
    }

    public void setMaxMessageLength(int maxMessageLength) {
        this.maxMessageLength = maxMessageLength;
    }
}
~~~

**Default:** enabled=true, prefix=NOTICE, maxMessageLength=80.

**Override:** acme.alert.enabled=false hoặc acme.alert.prefix=OPS, acme.alert.max-message-length=5.

**Invalid:** acme.alert.max-message-length=0 không đạt @Min(1); prefix chỉ có whitespace không đạt @NotBlank; enabled=not-a-boolean không convert được thành boolean. Spring Boot Binder và Bean Validation phải làm context startup fail.

**Relaxed binding:** @ConfigurationProperties hiểu các naming variants hợp lệ như kebab-case và camelCase, nhưng không sửa typo ngẫu nhiên. Trong tài liệu và configuration files nên dùng canonical kebab-case, tránh key **max-message-lenght** bị bỏ qua rồi default 80 vẫn được sử dụng.

### Auto-config: AlertAutoConfiguration.java

~~~java
package com.example.alertlib;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(AlertProperties.class)
public class AlertAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AlertSender.class)
    @ConditionalOnProperty(
        prefix = "acme.alert",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
    ConsoleAlertSender consoleAlertSender(
            AlertProperties properties) {
        return new ConsoleAlertSender(
            properties.getPrefix(),
            properties.getMaxMessageLength());
    }
}
~~~

**Điều kiện default:** feature bật nếu property enabled=true hoặc thiếu key (matchIfMissing=true), **nhưng chỉ tạo sender khi không có AlertSender khác**. Method @Bean trả **ConsoleAlertSender concrete type**, cung cấp type metadata rõ. Khách hàng vẫn nên inject **AlertSender** thay vì implementation type.

**Điểm tinh tế:** @EnableConfigurationProperties nằm trên auto-config class, còn @ConditionalOnProperty nằm ở @Bean method. Vì thế **enabled=false** vẫn có **AlertProperties bean**, nhưng **không có default AlertSender bean**. Test phải đếm đúng type, không đếm toàn bộ ApplicationContext.

### Registration resource: AutoConfiguration.imports

Tạo file **src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** đúng đường dẫn:

~~~text
com.example.alertlib.AlertAutoConfiguration
~~~

Spring Boot 3.x tìm auto-configuration candidates từ file imports. Mỗi dòng là fully-qualified class name. Không dùng spring.factories để đăng ký EnableAutoConfiguration theo kiểu Spring Boot 2.x. Không đánh dấu ConsoleAlertSender bằng @Component ngoài @Bean, nếu không có thể dẫn đến duplicate/default back-off ngoài ý định.

### Boot app: AlertDemoApplication.java

~~~java
package com.example.alertdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AlertDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AlertDemoApplication.class, args);
    }
}
~~~

Vì app nằm ở com.example.alertdemo và auto-config ở com.example.alertlib, **component scanning không trực tiếp tìm thấy AlertAutoConfiguration**. Integration test ở phần 6 chứng minh resource imports được Spring Boot sử dụng.

## 5. Bộ test auto-configuration hoàn chỉnh

**src/test/java/com/example/alertlib/AlertAutoConfigurationTest.java**

~~~java
package com.example.alertlib;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AlertAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(AlertAutoConfiguration.class));

    @Test
    void defaultHasExactlyOneSenderOfCorrectType() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());

            assertEquals(1, context
                .getBeanNamesForType(AlertSender.class).length);
            assertEquals(1, context
                .getBeansOfType(AlertSender.class).size());
            assertEquals(1, context
                .getBeanNamesForType(
                    ConsoleAlertSender.class).length);
            assertTrue(context.containsBean("consoleAlertSender"));

            ConsoleAlertSender sender = assertInstanceOf(
                ConsoleAlertSender.class,
                context.getBean(AlertSender.class));

            assertEquals("NOTICE", sender.getPrefix());
            assertEquals(80, sender.getMaxMessageLength());
            assertEquals("NOTICE:anna:hello",
                sender.send("anna", "hello"));
        });
    }

    @Test
    void defaultConfigurationPropertiesAreBoundOnce() {
        runner.run(context -> {
            assertNull(context.getStartupFailure());
            assertEquals(1, context
                .getBeanNamesForType(AlertProperties.class).length);

            AlertProperties properties =
                context.getBean(AlertProperties.class);
            assertTrue(properties.isEnabled());
            assertEquals("NOTICE", properties.getPrefix());
            assertEquals(80, properties.getMaxMessageLength());
        });
    }

    @Test
    void disabledFeatureHasZeroSenderButRetainsProperties() {
        runner.withPropertyValues("acme.alert.enabled=false")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertEquals(0, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertFalse(
                    context.containsBean("consoleAlertSender"));

                AlertProperties properties =
                    context.getBean(AlertProperties.class);
                assertFalse(properties.isEnabled());
                assertEquals("NOTICE", properties.getPrefix());
            });
    }

    @Test
    void explicitEnabledTrueCreatesDefaultSender() {
        runner.withPropertyValues("acme.alert.enabled=true")
            .run(context -> {
                assertNull(context.getStartupFailure());
                assertEquals(1, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertInstanceOf(
                    ConsoleAlertSender.class,
                    context.getBean(AlertSender.class));
            });
    }

    @Test
    void overriddenPropertiesAffectRealImplementation() {
        runner.withPropertyValues(
            "acme.alert.prefix=OPS",
            "acme.alert.max-message-length=5")
            .run(context -> {
                assertNull(context.getStartupFailure());

                AlertProperties properties =
                    context.getBean(AlertProperties.class);
                assertEquals("OPS", properties.getPrefix());
                assertEquals(5, properties.getMaxMessageLength());

                ConsoleAlertSender sender =
                    context.getBean(ConsoleAlertSender.class);
                assertEquals("OPS", sender.getPrefix());
                assertEquals(5, sender.getMaxMessageLength());
                assertEquals("OPS:bob:hello",
                    sender.send("bob", "hello"));

                assertThrows(IllegalArgumentException.class,
                    () -> sender.send("bob", "abcdef"));
            });
    }

    @Test
    void userSenderMakesDefaultAutoConfigurationBackOff() {
        runner.withUserConfiguration(UserSenderConfig.class)
            .run(context -> {
                assertNull(context.getStartupFailure());

                assertEquals(1, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertTrue(context.containsBean("customSender"));
                assertFalse(
                    context.containsBean("consoleAlertSender"));

                assertEquals("CUSTOM:anna:hello",
                    context.getBean(AlertSender.class)
                        .send("anna", "hello"));
                assertNotNull(
                    context.getBean(AlertProperties.class));
            });
    }

    @Test
    void disablingDefaultDoesNotRemoveUserBean() {
        runner.withUserConfiguration(UserSenderConfig.class)
            .withPropertyValues("acme.alert.enabled=false")
            .run(context -> {
                assertNull(context.getStartupFailure());

                assertEquals(1, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertTrue(context.containsBean("customSender"));
                assertFalse(
                    context.containsBean("consoleAlertSender"));
            });
    }

    @Test
    void twoUserSendersStayTwoWithoutExtraDefault() {
        runner.withUserConfiguration(TwoSendersConfig.class)
            .run(context -> {
                assertNull(context.getStartupFailure());

                assertEquals(2, context
                    .getBeanNamesForType(AlertSender.class).length);
                assertEquals(2, context
                    .getBeansOfType(AlertSender.class).size());
                assertFalse(
                    context.containsBean("consoleAlertSender"));

                assertThrows(
                    NoUniqueBeanDefinitionException.class,
                    () -> context.getBean(AlertSender.class));
            });
    }

    @Test
    void numericConfigBelowMinimumFailsStartup() {
        runner.withPropertyValues(
            "acme.alert.max-message-length=0")
            .run(context -> {
                assertNotNull(context.getStartupFailure());
            });
    }

    @Test
    void blankPrefixFailsBeanValidation() {
        runner.withPropertyValues("acme.alert.prefix= ")
            .run(context -> {
                assertNotNull(context.getStartupFailure());
            });
    }

    @Test
    void invalidBooleanFailsConfigBinding() {
        runner.withPropertyValues(
            "acme.alert.enabled=not-a-boolean")
            .run(context -> {
                assertNotNull(context.getStartupFailure());
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserSenderConfig {
        @Bean
        AlertSender customSender() {
            return (recipient, message) ->
                "CUSTOM:" + recipient + ":" + message;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoSendersConfig {
        @Bean
        AlertSender alphaSender() {
            return (recipient, message) -> "ALPHA";
        }

        @Bean
        AlertSender betaSender() {
            return (recipient, message) -> "BETA";
        }
    }
}
~~~

### Những gì tests xác minh

**defaultHasExactlyOneSenderOfCorrectType:** count=1 theo interface, count=1 theo concrete type, bean name default tồn tại, behavior dùng NOTICE. Không chỉ assert context started.

**defaultConfigurationPropertiesAreBoundOnce:** chứng minh properties bean tồn tại đúng một lần, default enabled=true, prefix=NOTICE, maxMessageLength=80.

**disabledFeatureHasZeroSenderButRetainsProperties:** enabled=false loại sender mặc định nhưng vẫn có properties bean. Đây là điểm rất dễ assert sai khi @ConditionalOnProperty ở method-level.

**explicitEnabledTrueCreatesDefaultSender:** property true có cùng behavior như default enabled do matchIfMissing=true.

**overriddenPropertiesAffectRealImplementation:** kiểm giá trị đã bind trong AlertProperties **và** được truyền vào ConsoleAlertSender; gửi chuỗi quá dài gây exception. Nếu key bị typo thì test phải fail.

**userSenderMakesDefaultAutoConfigurationBackOff:** @ConditionalOnMissingBean hoạt động; customSender được giữ, consoleAlertSender vắng mặt, count vẫn 1.

**disablingDefaultDoesNotRemoveUserBean:** điều kiện enabled chỉ chi phối auto bean, không xóa user bean.

**twoUserSendersStayTwoWithoutExtraDefault:** khi user có hai senders, auto-config vẫn back off. Lookup unqualified theo interface ném NoUniqueBeanDefinitionException, tránh giả định getBean chọn ngẫu nhiên.

**Ba invalid-config tests:** max-message-length=0, prefix trắng, boolean không hợp lệ làm context startup failure, thay vì âm thầm dùng giá trị sai. Có positive tests bên cạnh để tránh false positive rằng “mọi cấu hình đều fail”.

**Tính cô lập:** mỗi test method dùng runner withConfiguration chung nhưng tạo **context mới trong run callback**. Không sửa System properties, không dùng @TestMethodOrder, không có state từ method trước.

### Nâng chất lượng startup-failure assertions

Chỉ assertNotNull(context.getStartupFailure()) có thể PASS do một lỗi unrelated khác. Trong code production, khi test invalid property, nên kiểm **cause chain** tới Bean Validation/BindException hoặc tên property bị lỗi theo Spring Boot version đã khóa; không assert nguyên văn full stack trace/log message vốn dễ thay đổi.

Với những tests khác, assertNull(context.getStartupFailure()) trước type/count kiểm context không lỗi vì lý do ngoài dự kiến.

## 6. Spring Boot discovery test độc lập

ApplicationContextRunner đã chỉ định **AlertAutoConfiguration.class** trực tiếp. Nếu xóa nhầm resource **AutoConfiguration.imports**, 11 runner tests có thể vẫn PASS. Để chứng minh Boot tự phát hiện class khi chạy app, thêm test:

**src/test/java/com/example/alertdemo/AutoConfigurationDiscoveryTest.java**

~~~java
package com.example.alertdemo;

import com.example.alertlib.AlertSender;
import com.example.alertlib.ConsoleAlertSender;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest(
    classes = AlertDemoApplication.class,
    properties = {
        "acme.alert.enabled=true",
        "acme.alert.prefix=DISCOVERED"
    })
class AutoConfigurationDiscoveryTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void importsFileRegistersAlertAutoConfiguration() {
        assertEquals(1, context
            .getBeanNamesForType(AlertSender.class).length);

        ConsoleAlertSender sender =
            assertInstanceOf(
                ConsoleAlertSender.class,
                context.getBean(AlertSender.class));

        assertEquals("DISCOVERED", sender.getPrefix());
        assertEquals("DISCOVERED:client:ok",
            sender.send("client", "ok"));
    }
}
~~~

Nếu class tự cấu hình không nằm trong imports file và không bị quét bởi app package, **không có AlertSender**; test sẽ fail. **Không sửa test này bằng @Import(AlertAutoConfiguration.class)**, vì như vậy lại bỏ qua discovery mechanism.

**@SpringBootTest không mặc nhiên cần HTTP server:** project chỉ có starter thường, không có starter-web. Nó vẫn tạo full application context và auto-configurations; chạy chậm hơn ApplicationContextRunner nhưng cung cấp bằng chứng tích hợp cần thiết.

## 7. Loại bean: getBean(), getBeansOfType() và bean definitions

| Câu hỏi | Công cụ | Điều cần lưu ý |
| --- | --- | --- |
| Có đúng một bean theo interface? | getBeanNamesForType(T).length | Đếm tên candidates theo type |
| Có bao nhiêu instances theo type? | getBeansOfType(T).size() | Có thể instantiate/làm ảnh hưởng lazy FactoryBeans |
| Consumer inject được type? | getBean(T.class) | @Primary có thể che trường hợp có nhiều beans |
| Tên default bean tồn tại? | containsBean("consoleAlertSender") | Naming là contract khi cần |
| Implementation cụ thể đúng? | assertInstanceOf(ConsoleAlertSender.class, bean) | Proxy có thể làm runtime class khác |
| Có properties bean? | getBean(AlertProperties.class) | Không cần assert generated bean name |
| Tổng definitions? | getBeanDefinitionCount() | Không phải số AlertSender |
| Có 2 user beans? | getBeansOfType(AlertSender.class) | Không được auto-config thêm default |
| Context startup lỗi? | getStartupFailure() | Không đếm beans giữa startup failure |

### getBeanNamesForType vs getBeansOfType

**getBeanNamesForType** thường dùng metadata để trả các names phù hợp type, tránh phải lấy instance trong nhiều trường hợp. **getBeansOfType** trả map **name → bean instance** và có thể kích hoạt việc tạo singleton/factory. Với lazy, FactoryBean hay proxy, type query semantics phụ thuộc metadata và thời điểm initialization; nên test contract **bean sau khi context đã start**, không cố suy từ class file.

**@Bean return type quan trọng:** nếu method khai báo trả interface AlertSender nhưng runtime tạo ConsoleAlertSender, metadata không phải lúc nào cũng cho biết concrete implementation trước khi instantiate. Trong ví dụ, @Bean trả **ConsoleAlertSender** nên Spring có concrete return type rõ ràng.

### @Primary và @Qualifier không làm count giảm

Một @Primary lựa chọn default injection candidate, nhưng **vẫn có hai bean definitions**. Một @Qualifier giúp inject bean có tên/qualifier phù hợp, nhưng cũng không xóa bean khác. Nếu contract yêu cầu đúng một bean, phải assert **count**, không chỉ assert getBean(type) hoạt động.

### Singleton, prototype và parent context

Một singleton bean definition thường có một instance trong context. Prototype bean definition có thể tạo nhiều instances khi gọi getBean nhiều lần, nhưng getBeanNamesForType count vẫn là **số definitions**, không phải số instances từng sinh ra. Với parent/child contexts, danh sách local beans có thể khác danh sách có ancestor beans; khi test hierarchy cần dùng APIs có SearchStrategy/BeanFactoryUtils phù hợp. Đừng assert một số lượng toàn cục mà không biết phạm vi.

## 8. @ConditionalOnProperty và ConfigProperties: đúng phạm vi

Trong project:

~~~java
@ConditionalOnProperty(
    prefix = "acme.alert",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
~~~

| Value | Default sender | AlertProperties |
| --- | --- | --- |
| Không khai báo | Có, nếu thiếu AlertSender khác | enabled=true |
| true | Có, nếu thiếu AlertSender khác | enabled=true |
| false | Không | enabled=false |
| not-a-boolean | Condition không cho phép default; Binder fail | Startup failure |
| Có customSender, enabled=true | Không (back-off) | Có |
| Có customSender, enabled=false | Không | Có |

**Condition không phải validator.** Nó chỉ quyết định registration khi property match. Binder và Bean Validation kiểm type, constraints của @ConfigurationProperties. Trong thiết kế này properties bean được đăng ký từ @EnableConfigurationProperties **ở class level** nên vẫn bind khi sender disabled; nếu đặt @ConditionalOnProperty ở cả class-level, properties bean có thể cũng bị loại.

Khi thêm nested properties, dùng **@Valid** để cascade validation theo Bean Validation. Với enum/Duration/DataSize, test conversion và invalid values. Với relaxed binding, canonical kebab-case trong config docs vẫn được khuyến nghị.

### Cấu hình nguồn nào thắng?

ApplicationContextRunner.withPropertyValues bổ sung giá trị test Environment. Full Spring Boot application còn có default config, profile-specific config, environment variables, command-line properties, @TestPropertySource và test annotation properties với precedence quy định. Một runner test không nhất thiết chứng minh production profile nhận đúng nguồn; khi precedence/profiles là requirement, bổ sung **@SpringBootTest(properties=...)** hoặc ConfigDataApplicationContextInitializer, rồi assert bean bound values trong hoàn cảnh thật.

## 9. Classpath, web context và auto-config ordering

Các điều kiện còn lại có thể ảnh hưởng type/count. Ví dụ **@ConditionalOnClass(name="com.vendor.FastClient")** khi optional dependency không có phải **không tạo client bean**, chứ không gây ClassNotFoundException.

**FilteredClassLoader** của Spring Boot test có thể giả lập class vắng mặt:

~~~java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(OptionalClientAutoConfiguration.class))
    .withClassLoader(
        new FilteredClassLoader("com.vendor.FastClient"))
    .run(context -> {
        // Assert optional client bean vắng mặt.
    });
~~~

Đây là **trích đoạn**, không thuộc runnable tree; cần class OptionalClientAutoConfiguration thực, annotation @ConditionalOnClass và các imports. Với optional class, tránh tham chiếu class trực tiếp ở method signature nếu nó có thể bị load trước khi condition áp dụng; dùng cấu trúc configuration tách biệt hoặc name-based condition phù hợp.

**@ConditionalOnWebApplication**: nếu test web auto-config trong plain ApplicationContextRunner, điều kiện sẽ không match vì context không phải web. Chọn **WebApplicationContextRunner** cho servlet, **ReactiveWebApplicationContextRunner** cho reactive. Khi có @ConditionalOnBean và nhiều auto-configurations, **thứ tự processing definitions** có thể ảnh hưởng condition; dùng @AutoConfiguration(before/after) theo dependency thực và test cả có/không có prerequisite beans.

## 10. ConditionEvaluationReport hỗ trợ debug

Khi sender không được tạo, có thể do feature disabled, user bean đã tồn tại, class optional vắng mặt, imports file thiếu hoặc property bind sai. Không nên mò bằng cách xóa conditions. Spring Boot có **ConditionEvaluationReport** để thấy positive/negative matches.

Trong runner có thể bật log:

~~~java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(AlertAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(
            LogLevel.INFO))
    .withPropertyValues("acme.alert.enabled=false")
    .run(context -> {
        assertEquals(0, context
            .getBeanNamesForType(AlertSender.class).length);
    });
~~~

Đây là **trích đoạn minh họa**, thêm imports:
- org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener
- org.springframework.boot.logging.LogLevel
- org.springframework.boot.test.context.runner.ApplicationContextRunner
- org.springframework.boot.autoconfigure.AutoConfigurations
- JUnit Assertions và code demo.

**ConditionEvaluationReport không thay thế assertions.** Nó giải thích vì sao conditions match/không match; bean creation còn có thể fail do dependency resolution/binding/validation. Khi bật debug/Actuator conditions/configprops trong môi trường thật, cần bảo vệ endpoint và không đưa secrets lên CI logs công khai.

## 11. Lỗi test thường gặp

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| Chỉ assert context != null | Không biết bean đúng type/count không | Assert cụ thể type/count/config |
| Chỉ getBean(T.class) | @Primary có thể che duplicate beans | getBeanNamesForType(T).length |
| Assert tổng 17 bean definitions | Phụ thuộc framework version | Đếm bean theo contract |
| Chỉ test enabled=true | Bỏ sót disabled/default branch | Default/true/false tests |
| Không test user override | Duplicate beans bất ngờ | withUserConfiguration và back-off |
| Mock AlertProperties trong test binding | Che lỗi property binder | Dùng AlertProperties bean thật |
| Kiểm property chỉ trong Environment | Không chứng minh implementation dùng value | Assert sender behavior |
| Thiếu validation provider | @Min/@NotBlank không hoạt động | starter-validation |
| Test runner pass rồi kết luận imports file đúng | Class đã được import trực tiếp | @SpringBootTest discovery |
| Đặt auto-config trong package app scan | Không chứng minh auto-config registration | Package sibling và imports |
| Dùng @Component trên implementation + @Bean | Có thể tạo duplicate/back-off bất ngờ | Chỉ đăng ký theo một source |
| Dùng allow-bean-definition-overriding để che duplicate | Runtime chọn bean không rõ | @ConditionalOnMissingBean đúng |
| Test servlet condition trong plain runner | Context type không match | WebApplicationContextRunner |
| Assert concrete getClass() khi bean proxied | Dễ fail do AOP | Contract type/behavior assertions |
| Sai property name rồi default vẫn xanh | Relaxed binding không sửa typo | Explicit override + assert values |
| Startup-failure test chỉ cần non-null | Có thể pass do lỗi không liên quan | Kiểm root cause khi QA chặt |
| Dùng @DirtiesContext để chữa duplicate | Chậm mà không sửa conditions | Runner contexts độc lập |
| Thay System properties giữa parallel tests | State global bị rò | withPropertyValues |
| Test tất cả bằng @SpringBootTest | Nặng và khó chẩn đoán | Runner cho conditions, full context cho discovery |

## 12. Chạy Gradle và kết quả kỳ vọng

Với Gradle Wrapper tương thích JDK 17:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.alertlib.AlertAutoConfigurationTest
./gradlew test --tests com.example.alertdemo.AutoConfigurationDiscoveryTest
./gradlew test --tests com.example.alertlib.AlertAutoConfigurationTest.defaultHasExactlyOneSenderOfCorrectType
./gradlew test --tests com.example.alertlib.AlertAutoConfigurationTest.userSenderMakesDefaultAutoConfigurationBackOff
~~~

Trên Windows dùng **gradlew.bat**. Nếu chưa tạo Gradle Wrapper files, dùng Gradle đã cài hoặc chạy Gradle wrapper task; không giả vờ ./gradlew có sẵn khi chưa tạo. Không có một stdout BUILD SUCCESSFUL được quan sát trong quá trình viết bài.

| Test | Kỳ vọng |
| --- | --- |
| defaultHasExactlyOneSenderOfCorrectType | 1 AlertSender, 1 ConsoleAlertSender, output NOTICE |
| defaultConfigurationPropertiesAreBoundOnce | 1 AlertProperties, true/NOTICE/80 |
| disabledFeatureHasZeroSenderButRetainsProperties | 0 AlertSender, AlertProperties enabled=false |
| explicitEnabledTrueCreatesDefaultSender | 1 default sender |
| overriddenPropertiesAffectRealImplementation | OPS/5 và reject message dài 6 |
| userSenderMakesDefaultAutoConfigurationBackOff | 1 customSender, default vắng mặt |
| disablingDefaultDoesNotRemoveUserBean | 1 user sender |
| twoUserSendersStayTwoWithoutExtraDefault | 2 user beans, unqualified lookup ambiguous |
| numericConfigBelowMinimumFailsStartup | Startup failure do @Min |
| blankPrefixFailsBeanValidation | Startup failure do @NotBlank |
| invalidBooleanFailsConfigBinding | Startup failure do type conversion |
| importsFileRegistersAlertAutoConfiguration | @SpringBootTest tìm imports, 1 sender prefix DISCOVERED |

**Debug nếu tests không đạt:**
- Default 0 bean: xem @ConditionalOnProperty, @EnableConfigurationProperties, AutoConfigurations.of.
- User override 2 beans: xem @ConditionalOnMissingBean và user configuration timing.
- Property override không có tác dụng: xem key, setters, nested binding và factory method truyền values.
- Invalid properties không fail: kiểm @Validated và validation implementation.
- Runner PASS nhưng discovery FAIL: xem META-INF/spring/...imports path, package name và component scanning.
- Full context có nhiều beans bất ngờ: xem @Primary, @Qualifier, @Component scan, @ConditionalOnBean và active profiles.

## 13. Quy trình QA có thể áp dụng cho starter thật

**Bước 1 — Liệt kê các contract types**: DataSource, HttpClient, MeterRegistry, AlertSender hoặc bất kỳ bean mà module cung cấp. Định nghĩa 0/1/N mong muốn.

**Bước 2 — Định nghĩa điều kiện**: classpath, property, missing user bean, web environment, cloud platform. Xây ma trận tối thiểu để không bỏ nhánh.

**Bước 3 — Định nghĩa cấu hình**: prefix, default, type conversion, validation, required/optional fields, nested object; tránh property key mơ hồ.

**Bước 4 — Viết runner tests**: default, enabled/disabled, override, user bean, missing prerequisites và failure startup. Đếm bằng contract type, kiểm behavior.

**Bước 5 — Thêm integration discovery test**: bắt lỗi AutoConfiguration.imports bị thiếu/sai FQN hoặc một class vô tình bị component scan.

**Bước 6 — Kiểm đi qua injection point**: nếu ứng dụng inject có @Qualifier, @Primary, List<T>, Map<String,T> hoặc parent-child contexts thì assertion count/type đơn giản có thể chưa đủ.

**Bước 7 — Tránh brittle assertions**: không assert global beanDefinitionCount hoặc full stack trace. Không bỏ qua root cause của invalid config.

**Bước 8 — Kiểm classpath/environment thực tế**: với optional vendor library, test FilteredClassLoader; với servlet/reactive conditions chọn runner đúng. Với datasource/message broker thật, bổ sung Testcontainers/integration test chứ không gọi runner test là end-to-end.

**Bước 9 — Review regression**: khi đổi @Bean method return type, conditions, prefix, Bean Validation hoặc imports resource, update tests dựa trên contract, không chỉ sửa expected count cho xanh.

### Checklist

- Có kiểm 0/1/2 beans theo interface?
- Có kiểm implementation type phù hợp mà không phụ thuộc exact proxy class vô lý?
- Có kiểm bean names chỉ khi là contract?
- Có kiểm property defaults, overrides và dùng thật trong behavior?
- Có kiểm invalid config và startup failure đúng nguyên nhân?
- Có @ConditionalOnMissingBean user override tests?
- Có hiểu @Primary/@Qualifier không làm count giảm?
- Có tách @ConfigurationProperties bean khỏi default feature bean khi disabled?
- Có sử dụng ApplicationContextRunner cho conditions và @SpringBootTest cho discovery?
- Có file AutoConfiguration.imports đúng đường dẫn, FQN?
- Có tránh component-scan auto-config class?
- Có kiểm optional classpath/web context khi feature phụ thuộc chúng?
- Có hiểu singleton/prototype/FactoryBean/hierarchy khác nhau?
- Có dùng ConditionEvaluationReport để debug thay vì xóa conditions?
- Có tránh property sources global/static mutable state giữa tests?
- Có phân biệt startup check với functional behavior và production integration?
- Có ghi rõ code được thiết kế runnable nhưng không bịa runtime output?

## 14. Câu hỏi tự kiểm tra

**1.** Context có AlertSender qua getBean(type), vậy exactly-one đã được chứng minh? **Chưa**, @Primary có thể chọn một trong nhiều beans.

**2.** API nào đếm bean theo interface? **getBeanNamesForType(T).length** hoặc getBeansOfType(T).size().

**3.** enabled=false trong demo có AlertProperties không? **Có**, vì @EnableConfigurationProperties class-level, condition chỉ đặt trên sender @Bean.

**4.** Không khai báo enabled thì sao? **Default sender được tạo nếu thiếu user sender**, do matchIfMissing=true.

**5.** User customSender có nhưng auto-config vẫn tạo consoleAlertSender là gì? **Back-off không đúng**, gây duplicate.

**6.** Hai AlertSender không có primary, getBean(AlertSender.class) ra sao? **NoUniqueBeanDefinitionException**.

**7.** @Primary giảm bean count không? **Không**; chỉ ảnh hưởng candidate selection.

**8.** Set prefix OPS nhưng test chỉ đọc Environment đủ chưa? **Chưa**, phải đọc AlertProperties và kiểm ConsoleAlertSender thực dùng OPS.

**9.** @ConfigurationProperties có relaxed binding không? **Có**, nhưng không tự sửa key typo.

**10.** @Validated + @Min có cần validation provider? **Có**; starter-validation là lựa chọn thông dụng.

**11.** max-message-length=0 kỳ vọng gì? **Startup failure**.

**12.** Runner AutoConfigurations.of có chứng minh imports discovery? **Không**, nó chỉ định class trực tiếp.

**13.** Test nào chứng minh imports? **@SpringBootTest** của app không component-scan auto-config, rồi đếm bean được nạp.

**14.** @ConditionalOnWebApplication có test tốt trong plain ApplicationContextRunner không? **Không**, nên chọn WebApplicationContextRunner.

**15.** Muốn giả class optional vắng mặt dùng gì? **FilteredClassLoader**.

**16.** ConditionEvaluationReport có thay assertions không? **Không**, nó dùng để chẩn đoán.

**17.** Prototype bean definition count=1 có nghĩa chỉ một instance suốt JVM không? **Không**.

**18.** Khi @Bean return type là interface, Spring luôn biết implementation concrete trước instantiate? **Không phải lúc nào**.

**19.** Tại sao không assert tổng beanDefinitionCount? **Infrastructure definitions thay đổi theo phiên bản và dependencies**.

**20.** Kết luận quan trọng nhất? **Auto-config phải tạo đúng số và đúng loại beans, nhường chỗ cho user-defined beans, đồng thời bind/validate/áp dụng properties đúng như contract.**

**Kết luận:** Kiểm thử Spring Boot auto-configuration không chỉ là xác nhận context khởi động; phải **đếm bean theo contract, kiểm kiểu, names khi cần, conditional back-off, binding defaults/overrides, validation và behavior**. **ApplicationContextRunner** làm các tổ hợp này nhanh, cô lập và dễ debug. **@SpringBootTest** thêm bằng chứng discovery thực qua resource **AutoConfiguration.imports**. Với classpath/web conditions hoặc nhiều beans, điều chỉnh context runner và assertion theo đúng contract thay vì bắt buộc tất cả phải là single bean.

## Tài liệu chính thức

- Spring Boot 3.4 — Creating Your Own Auto-configuration và Testing Your Auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html
- Spring Boot 3.4 — Externalized Configuration và ConfigurationProperties Validation: https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — ConditionalOnMissingBean Javadoc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.4 — ConditionalOnProperty Javadoc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Framework 6.2 — BeanFactory/ApplicationContext: https://docs.spring.io/spring-framework/reference/6.2/core/beans/introduction.html
