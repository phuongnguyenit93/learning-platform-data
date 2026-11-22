# Dùng withUserConfiguration để mô phỏng cấu hình ứng dụng khi kiểm thử Spring Boot Auto-configuration

## 1. Vì sao cần mô phỏng cấu hình do ứng dụng cung cấp?

Một thư viện Spring Boot thường có auto-configuration cung cấp bean mặc định. Ứng dụng tiêu thụ có thể khai báo bean riêng để thay thế default, bổ sung dependency hoặc thay đổi cách tích hợp.

Ví dụ thư viện cung cấp `GreetingService` mặc định. Ứng dụng muốn dùng lời chào theo quy tắc riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class UserGreetingConfiguration {

    @Bean
    CustomGreetingService customGreetingService() {
        return new CustomGreetingService();
    }
}
~~~

Khi kiểm thử auto-configuration, ta cần tái tạo hai tình huống độc lập:

- Ứng dụng **không khai báo** bean tùy chỉnh: thư viện phải tạo default.
- Ứng dụng **có khai báo** bean tùy chỉnh: auto-configuration phải nhận ra bean đó và back off đúng cách.

`ApplicationContextRunner` của Spring Boot tạo một `ApplicationContext` nhỏ cho từng test. Phương thức `withUserConfiguration(...)` cho phép đưa trực tiếp một hoặc nhiều class cấu hình đại diện cho cấu hình do ứng dụng sở hữu vào context kiểm thử.

**Ý nghĩa:** test có thể kiểm tra sự tương tác giữa user configuration và auto-configuration mà không cần khởi động toàn bộ ứng dụng, quét toàn bộ package hoặc dựng server/database thật.

## 2. ApplicationContextRunner gồm những phần nào?

Một runner thường có hai nhóm cấu hình:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(GreetingAutoConfiguration.class));
~~~

- `ApplicationContextRunner` là bộ dựng context độc lập, phù hợp cho các test tập trung vào bean registration và conditions.
- `withConfiguration(AutoConfigurations.of(...))` đưa các auto-configuration cần kiểm tra vào runner theo cơ chế dành riêng cho auto-configuration.
- `withUserConfiguration(...)` thêm cấu hình do người dùng cung cấp, thường là class `@Configuration` có các method `@Bean`.
- `run(context -> { ... })` mở context, chạy assertion trong callback và đóng context sau callback.

Tư duy quan trọng là phân vai:

| API | Dùng để mô phỏng | Ví dụ |
| --- | --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Thư viện/Spring Boot auto-configuration đang được kiểm thử | `GreetingAutoConfiguration.class` |
| `withUserConfiguration(...)` | Cấu hình do ứng dụng khai báo | `UserGreetingConfiguration.class` |
| `withPropertyValues(...)` | Giá trị cấu hình của ứng dụng trong `Environment` | `acme.greeting.prefix=Hi` |
| `withBean(...)` | Một bean test được đăng ký trực tiếp bằng supplier/type | Mock hoặc fixture đơn lẻ |
| `withClassLoader(...)` | Classpath của ứng dụng trong tình huống kiểm thử | `FilteredClassLoader` để giả lập thiếu dependency |
| `withInitializer(...)` | ApplicationContext initializer/listener | In `ConditionEvaluationReport` |

Không truyền auto-configuration vào `withUserConfiguration` chỉ vì muốn nó xuất hiện trong context. Hãy dùng `AutoConfigurations.of(...)` cho auto-configuration để Boot áp dụng đúng semantics và thứ tự của nhóm cấu hình này.

## 3. withUserConfiguration làm gì?

`withUserConfiguration(Class<?>... userConfigurations)` nhận một hoặc nhiều class cấu hình và đưa chúng vào context do runner tạo.

Ví dụ:

~~~java
contextRunner
        .withUserConfiguration(
                UserGreetingConfiguration.class,
                UserMetricsConfiguration.class)
        .run(context -> {
            // Kiểm tra các bean do ứng dụng khai báo
        });
~~~

Các class thường được viết bằng `@Configuration(proxyBeanMethods = false)` và cung cấp bean bằng `@Bean`. Mỗi class có thể đại diện cho một phần cấu hình độc lập của ứng dụng: client tùy chỉnh, metrics, cache, security adapter hoặc mock dependency.

Phương thức này:
- Đăng ký các configuration source được truyền vào runner.
- Cho phép các method `@Bean` trong user configuration tham gia vào quá trình tạo context.
- Giúp kiểm tra auto-configuration nhìn thấy bean do người dùng cung cấp và có back off đúng không.
- Cho phép kết hợp nhiều class cấu hình trong cùng một scenario.

Nó **không tự quét package** chứa các class đó. Bạn chỉ định rõ class nào được đưa vào. Nếu chính user configuration có `@ComponentScan`, scan đó vẫn có thể chạy; vì vậy test tập trung vào auto-configuration nên giữ fixture tường minh và tránh scan ngoài ý muốn.

### Cấu hình lồng trong test nên là static

Một cách tổ chức phổ biến là đặt các class fixture bên trong test class:

~~~java
@Configuration(proxyBeanMethods = false)
static class UserGreetingConfiguration {

    @Bean
    CustomGreetingService customGreetingService() {
        return new CustomGreetingService();
    }
}
~~~

Dùng nested class `static` để Spring có thể khởi tạo configuration mà không cần instance của test class bên ngoài. Các class này chỉ là fixture kiểm thử; không cần đưa chúng vào package scan của ứng dụng.

## 4. Cấu trúc auto-configuration mẫu

Ta xây một ví dụ Java 17+ với ba thành phần:

1. `GreetingService` là API mà client dùng.
2. `GreetingAutoConfiguration` tạo default nếu chưa có implementation.
3. User configuration có thể cung cấp implementation riêng và một bean hỗ trợ khác.

Interface:

~~~java
public interface GreetingService {
    String message();
}
~~~

Implementation mặc định:

~~~java
public final class DefaultGreetingService implements GreetingService {

    @Override
    public String message() {
        return "hello from library";
    }
}
~~~

Auto-configuration:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    DefaultGreetingService greetingService() {
        return new DefaultGreetingService();
    }

    @Bean
    @ConditionalOnBean(AuditSink.class)
    GreetingAuditRecorder greetingAuditRecorder(AuditSink auditSink) {
        return new GreetingAuditRecorder(auditSink);
    }
}
~~~

Điểm cần chú ý:

- Condition `@ConditionalOnMissingBean(GreetingService.class)` kiểm tra contract interface. Nếu user configuration cung cấp một bean triển khai `GreetingService`, default không được đăng ký.
- Return type của method là `DefaultGreetingService`, kiểu cụ thể giúp Spring có type metadata rõ ràng.
- `@ConditionalOnBean(AuditSink.class)` minh họa một bean auto-configured khác chỉ xuất hiện khi ứng dụng cung cấp prerequisite `AuditSink`.
- Các bean condition kiểu này nên nằm trong auto-configuration. Spring Boot bảo đảm auto-configuration được áp dụng sau các bean definitions do người dùng khai báo; condition dựa trên những bean definitions đã được xử lý đến thời điểm đánh giá.

Trong thư viện thật, auto-configuration còn cần được công bố qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Runner bên dưới nhận class trực tiếp qua `AutoConfigurations.of(...)` nên test fixture không cần descriptor để đưa class đó vào runner.

## 5. User configuration đại diện cho ứng dụng

Ứng dụng cung cấp implementation riêng:

~~~java
@Configuration(proxyBeanMethods = false)
static class UserGreetingConfiguration {

    @Bean
    CustomGreetingService customGreetingService() {
        return new CustomGreetingService();
    }
}
~~~

Class bean:

~~~java
static final class CustomGreetingService implements GreetingService {

    @Override
    public String message() {
        return "hello from application";
    }
}
~~~

Một cấu hình ứng dụng khác có thể cung cấp dependency hỗ trợ:

~~~java
@Configuration(proxyBeanMethods = false)
static class UserAuditConfiguration {

    @Bean
    MemoryAuditSink auditSink() {
        return new MemoryAuditSink();
    }
}
~~~

Trong test, gọi:

~~~java
contextRunner
        .withUserConfiguration(
                UserGreetingConfiguration.class,
                UserAuditConfiguration.class)
        .run(context -> {
            // Context chứa cả custom greeting và audit sink
        });
~~~

Đây là điểm mạnh của `withUserConfiguration`: ta dựng được một context mô phỏng nhiều phần cấu hình thực tế của ứng dụng. Không cần copy tất cả class production; chỉ đưa những configuration source liên quan đến scenario đang kiểm tra.

## 6. Bài test hoàn chỉnh với JUnit 5 và AssertJ

File sau gom interface, implementation, auto-configuration và user configurations vào một test class để ví dụ có thể đọc và chạy độc lập. Project cần Java 17+, Spring Boot 3.3 và dependency `spring-boot-starter-test`.

Tạo `src/test/java/com/example/demo/GreetingAutoConfigurationTests.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    interface GreetingService {
        String message();
    }

    static final class DefaultGreetingService implements GreetingService {
        @Override
        public String message() {
            return "hello from library";
        }
    }

    static final class CustomGreetingService implements GreetingService {
        @Override
        public String message() {
            return "hello from application";
        }
    }

    interface AuditSink {
        String destination();
    }

    static final class MemoryAuditSink implements AuditSink {
        @Override
        public String destination() {
            return "memory";
        }
    }

    static final class GreetingAuditRecorder {
        private final AuditSink auditSink;

        GreetingAuditRecorder(AuditSink auditSink) {
            this.auditSink = auditSink;
        }

        String destination() {
            return auditSink.destination();
        }
    }

    static final class GreetingMetrics {
    }

    @AutoConfiguration
    static class GreetingAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(GreetingService.class)
        DefaultGreetingService greetingService() {
            return new DefaultGreetingService();
        }

        @Bean
        @ConditionalOnBean(AuditSink.class)
        GreetingAuditRecorder greetingAuditRecorder(AuditSink auditSink) {
            return new GreetingAuditRecorder(auditSink);
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.greeting.metrics",
                name = "enabled",
                havingValue = "true"
        )
        GreetingMetrics greetingMetrics() {
            return new GreetingMetrics();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreetingConfiguration {

        @Bean
        CustomGreetingService customGreetingService() {
            return new CustomGreetingService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {

        @Bean
        MemoryAuditSink auditSink() {
            return new MemoryAuditSink();
        }
    }

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class));

    @Test
    void defaultServiceIsCreatedWhenNoUserConfigurationIsAdded() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasSingleBean(DefaultGreetingService.class);
            assertThat(context).doesNotHaveBean(CustomGreetingService.class);
            assertThat(context.getBean(GreetingService.class).message())
                    .isEqualTo("hello from library");
            assertThat(context).doesNotHaveBean(GreetingAuditRecorder.class);
        });
    }

    @Test
    void userConfigurationReplacesTheDefaultService() {
        contextRunner
                .withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasSingleBean(CustomGreetingService.class);
                    assertThat(context).doesNotHaveBean(DefaultGreetingService.class);
                    assertThat(context.getBean(GreetingService.class).message())
                            .isEqualTo("hello from application");
                    assertThat(context.getBean("customGreetingService"))
                            .isSameAs(context.getBean(GreetingService.class));
                });
    }

    @Test
    void multipleUserConfigurationsCanBeCombined() {
        contextRunner
                .withUserConfiguration(
                        UserGreetingConfiguration.class,
                        UserAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(CustomGreetingService.class);
                    assertThat(context).hasSingleBean(AuditSink.class);
                    assertThat(context).hasSingleBean(GreetingAuditRecorder.class);
                    assertThat(context.getBean(GreetingAuditRecorder.class)
                            .destination()).isEqualTo("memory");
                    assertThat(context).doesNotHaveBean(DefaultGreetingService.class);
                });
    }

    @Test
    void userConfigurationCanBeCombinedWithEnvironmentProperties() {
        contextRunner
                .withUserConfiguration(UserGreetingConfiguration.class)
                .withPropertyValues("acme.greeting.metrics.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(CustomGreetingService.class);
                    assertThat(context).hasSingleBean(GreetingMetrics.class);
                    assertThat(context).doesNotHaveBean(DefaultGreetingService.class);
                });
    }

    @Test
    void missingUserDependencyKeepsConditionalBeanDisabled() {
        contextRunner
                .withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditSink.class);
                    assertThat(context).doesNotHaveBean(GreetingAuditRecorder.class);
                });
    }
}
~~~

Chạy trong project Gradle có dependency test:

~~~bash
./gradlew test --tests "com.example.demo.GreetingAutoConfigurationTests"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.GreetingAutoConfigurationTests"
~~~

Maven:

~~~bash
mvn -Dtest=GreetingAutoConfigurationTests test
~~~

**Kết quả kỳ vọng:** 5 test PASS. Các assertion kiểm tra bean và hành vi:
- Không có user configuration: default service được tạo.
- Có custom user configuration: default back off và custom bean được tiêm.
- Có hai user configurations: cả hai được đưa vào context; audit recorder được tạo vì prerequisite có mặt.
- User configuration có thể kết hợp với property values để bật một bean khác.
- Không có audit sink: bean phụ thuộc audit không xuất hiện.

Các test là ví dụ runnable theo cấu hình dependency đã nêu; cần chạy trong project để xác nhận môi trường build cụ thể.

## 7. withUserConfiguration và các API thường đi cùng

Một test auto-configuration thường mô phỏng nhiều chiều của ứng dụng. Chọn API theo đúng loại dữ liệu cần đưa vào context:

| API | Khi nào dùng | Ví dụ |
| --- | --- | --- |
| `withUserConfiguration(A.class)` | Ứng dụng có một class `@Configuration` chứa nhiều `@Bean` | Custom service, cache config |
| `withUserConfiguration(A.class, B.class)` | Ứng dụng có nhiều nhóm cấu hình độc lập | Client config + metrics config |
| `withPropertyValues(...)` | Cấu hình đến từ `Environment` | Bật/tắt feature bằng property |
| `withBean(...)` | Cần đăng ký trực tiếp một fixture hoặc mock mà không tạo class cấu hình | Mock external gateway |
| `withConfiguration(AutoConfigurations.of(...))` | Nạp auto-configuration đang kiểm thử | LibraryAutoConfiguration |
| `withClassLoader(new FilteredClassLoader(...))` | Giả lập dependency không có trên classpath | Kiểm tra `@ConditionalOnClass` |
| `withInitializer(...)` | Thêm context initializer hoặc listener | Ghi Condition Evaluation Report |

Không cần tạo một `@Configuration` class chỉ để đăng ký một bean mock duy nhất; `withBean` có thể gọn hơn. Ngược lại, khi muốn mô phỏng đúng một phần cấu hình production có nhiều bean, `withUserConfiguration` làm ý đồ rõ hơn.

## 8. Thứ tự user configuration và auto-configuration

Một trong các mục tiêu chính của test này là xác nhận người dùng có thể thay bean mặc định. Với auto-configuration chuẩn, Spring Boot xử lý bean definitions do người dùng khai báo trước auto-configuration. Vì vậy `@ConditionalOnMissingBean` có thể nhìn thấy custom bean và bỏ qua default.

~~~mermaid
flowchart TD
    A["ApplicationContextRunner"] --> B["Nạp UserGreetingConfiguration"]
    B --> C["Đăng ký CustomGreetingService"]
    C --> D["Áp dụng GreetingAutoConfiguration"]
    D --> E{"Đã có GreetingService?"}
    E -->|"Có"| F["Default bean back off"]
    E -->|"Không"| G["Tạo DefaultGreetingService"]
    F --> H["AssertJ kiểm tra custom bean"]
    G --> I["AssertJ kiểm tra default bean"]
~~~

Đây là thứ tự logic để hiểu bean conditions. Không nên dựa vào việc gọi method builder trước/sau như một thủ thuật sắp xếp; hãy phân biệt user configuration và auto-configuration qua đúng API.

### Vì sao condition phải nằm trong auto-configuration?

`@ConditionalOnMissingBean` dựa trên các bean definitions đã được xử lý tại thời điểm condition đánh giá. Nếu đặt condition tương tự trong một cấu hình thông thường được component scan sớm, nó có thể chạy trước bean mà nó cần phát hiện.

Spring Boot khuyến nghị dùng bean conditions trên auto-configuration class/method vì auto-configuration được áp dụng sau các bean definitions của người dùng. Bài test `withUserConfiguration` là cách xác minh hợp đồng này trong một context cô lập.

## 9. Nhiều user configurations, trùng bean và ambiguity

`withUserConfiguration` cho phép truyền nhiều class. Điều đó không có nghĩa Spring tự giải quyết mọi xung đột:

- Nếu hai class cùng khai báo bean trùng tên, context có thể thất bại do bean definition conflict; đừng dựa vào bean overriding.
- Nếu hai class cùng tạo hai bean cùng type và consumer inject một dependency đơn trị, có thể phát sinh `NoUniqueBeanDefinitionException` nếu không có candidate rõ ràng.
- `@Primary` có thể chọn candidate ưu tiên cho injection đơn trị khi có nhiều bean phù hợp; `@Qualifier` có thể chọn bean theo qualifier.
- `@ConditionalOnMissingBean` ngăn default được tạo khi đã có bean phù hợp, nhưng không loại bỏ các custom bean trùng type với nhau.
- Mỗi test nên khai báo đúng nhóm user configurations của scenario; tránh gom tất cả test fixture vào mọi test khiến kết quả khó giải thích.

Ví dụ user configurations độc lập:

~~~java
contextRunner
        .withUserConfiguration(
                UserGreetingConfiguration.class,
                UserAuditConfiguration.class,
                UserMetricsConfiguration.class)
        .run(context -> {
            // Assert các bean thuộc scenario này
        });
~~~

Nếu một cấu hình chỉ cần trong test riêng, đừng đưa nó vào runner base dùng chung. Hãy thêm qua `withUserConfiguration` trong đúng test cần scenario đó.

## 10. Kiểm tra điều kiện và chẩn đoán context

Khi test không có bean mong đợi, cần phân biệt:
- User configuration chưa được đưa vào runner.
- Auto-configuration chưa được đưa vào `AutoConfigurations.of(...)`.
- Bean có mặt nhưng condition khiến default back off.
- Property condition không khớp.
- Dependency bean mà method cần chưa được đăng ký.
- Nhiều candidate làm injection không xác định.

Có thể thêm `ConditionEvaluationReportLoggingListener`:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(GreetingAutoConfiguration.class))
        .withUserConfiguration(UserGreetingConfiguration.class)
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            // Assertions
        });
~~~

Import:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Report cho biết condition nào match/no-match và lý do. Kết hợp với AssertJ:
- `hasSingleBean(Type.class)` xác nhận đúng một bean phù hợp.
- `doesNotHaveBean(Type.class)` xác nhận default không xuất hiện.
- `getBean(Type.class)` lấy bean để kiểm tra hành vi.
- `getBean("beanName")` kiểm tra bean cụ thể theo tên.

Đừng chỉ kiểm tra context khởi động thành công. Auto-configuration có thể back off ngoài ý muốn mà context vẫn khởi động bình thường.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `withUserConfiguration` là cách nạp auto-configuration | Dùng `AutoConfigurations.of(...)` cho auto-configuration; `withUserConfiguration` dành cho cấu hình ứng dụng |
| Truyền một class vào runner đồng nghĩa package của class được scan | Runner nạp source class được chỉ định; nó không tự quét package |
| Không có user configuration nghĩa là auto-configuration không chạy | Runner vẫn chạy auto-configuration đã được đưa vào `withConfiguration` |
| Custom bean cùng type sẽ được tạo song song với default | `@ConditionalOnMissingBean` khiến default back off khi condition thấy custom bean |
| Nhiều user configurations luôn được gộp mà không xung đột | Bean name/type vẫn tuân theo quy tắc registry và dependency injection |
| Thứ tự viết các class trong varargs là cách điều khiển auto-configuration order | Dùng metadata ordering của auto-configuration; không dùng thứ tự truyền user config làm hợp đồng |
| `withPropertyValues` thay thế `withUserConfiguration` | Một API bổ sung Environment, API kia thêm configuration source |
| Test runner tương đương chạy toàn bộ `SpringApplication` | Runner tạo context cô lập, không tự chạy main class và toàn bộ quy trình khởi động ứng dụng |
| Context refresh thành công chứng minh mọi bean mong muốn tồn tại | Phải assert cả bean có và bean không có |
| Dùng một runner chung nghĩa mọi test dùng chung context instance | Mỗi lần `run` tạo context cho callback; runner là cấu hình nền để tạo các context test độc lập |

## 12. Khi nào dùng runner khác hoặc @SpringBootTest?

`ApplicationContextRunner` phù hợp cho auto-configuration thông thường, non-web context và các scenario nhanh. Nếu condition phụ thuộc loại web context:
- Dùng `WebApplicationContextRunner` cho servlet.
- Dùng `ReactiveWebApplicationContextRunner` cho reactive.

Dùng `@SpringBootTest` khi mục tiêu là kiểm thử ứng dụng gần với cấu hình production, cần tích hợp `SpringApplication`, component scanning thật, nhiều auto-configuration cùng hoạt động hoặc cần các thành phần khởi động ứng dụng. `ApplicationContextRunner` thường thích hợp hơn khi muốn cô lập đúng một auto-configuration và từng tổ hợp user configuration/property/classpath.

Một giới hạn cần biết: tài liệu Spring Boot ghi nhận `ApplicationContextRunner` không hoạt động khi chạy test trong native image. Nếu dự án kiểm thử native image, chọn cách kiểm thử tương thích với quy trình native của dự án.

## 13. Checklist viết test với withUserConfiguration

1. Tạo một runner base và đưa auto-configuration vào bằng `withConfiguration(AutoConfigurations.of(...))`.
2. Xác định cấu hình nào là của ứng dụng, cấu hình nào là của thư viện.
3. Đặt user fixture trong class `@Configuration(proxyBeanMethods = false)`, thường là nested static class.
4. Thêm đúng user configuration bằng `withUserConfiguration(...)` trong từng test.
5. Nếu scenario có property, thêm `withPropertyValues(...)`.
6. Nếu scenario cần mock đơn lẻ, cân nhắc `withBean(...)`.
7. Assert cả default bean, custom bean và bean phụ thuộc condition.
8. Kiểm tra nhiều user configs có trùng tên/type hoặc gây ambiguity không.
9. Khi condition khó hiểu, bật `ConditionEvaluationReportLoggingListener`.
10. Chạy test và xác minh phiên bản Spring Boot/JUnit/AssertJ thực tế của project.

## 14. Tự kiểm tra kiến thức

1. `withUserConfiguration` nhận đối tượng hay class? **Nhận class configuration/source (một hoặc nhiều class).**
2. Dùng API nào để nạp auto-configuration? **`withConfiguration(AutoConfigurations.of(...))`.**
3. Vì sao dùng `@Configuration(proxyBeanMethods = false)` trong user fixture? **Để khai báo một configuration source tường minh, không cần proxy bean methods khi không có nhu cầu gọi chéo method.**
4. Một user configuration có thể khai báo nhiều bean không? **Có**, bằng nhiều method `@Bean`.
5. Có thể truyền hai user configurations vào cùng một lần gọi không? **Có**, vì method nhận varargs class.
6. Làm sao kiểm tra default back off? **Assert custom bean tồn tại, default bean không tồn tại và bean theo interface là custom implementation.**
7. Có thể thêm property cùng user configuration không? **Có**, kết hợp `withPropertyValues`.
8. Nếu hai user config cùng tạo một bean type, điều gì có thể xảy ra? **Ambiguous injection hoặc bean definition conflict tùy tên và consumer.**
9. Khi nào dùng `WebApplicationContextRunner`? **Khi auto-configuration cần servlet web context.**
10. `ApplicationContextRunner` có chạy được trong native image test không? **Không theo giới hạn được ghi trong tài liệu Spring Boot.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): cách dựng runner, `AutoConfigurations.of`, `withUserConfiguration`, property values, condition report, classloader và web runner.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html): các module test và dependency `spring-boot-starter-test`.
- [Spring Boot 3.3 — `ApplicationContextRunner` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): API tạo và tùy chỉnh context test.
- [Spring Boot 3.3 — `AutoConfigurations` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html): đăng ký danh sách auto-configuration trong runner.
- [Spring Boot 3.3 — `@ConditionalOnMissingBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): cơ chế back-off theo bean đã có.
