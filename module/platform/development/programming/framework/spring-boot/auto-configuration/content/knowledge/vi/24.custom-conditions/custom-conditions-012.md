# Kiểm thử cả nhánh khớp, không khớp và thông điệp chẩn đoán của điều kiện tùy chỉnh

## 1. Mục tiêu: kiểm tra cả quyết định lẫn lý do

Một điều kiện tùy chỉnh của Spring Boot quyết định một cấu hình hoặc bean có được đăng ký hay không. Test chỉ xác nhận bean xuất hiện khi điều kiện đúng vẫn chưa đủ. Điều kiện còn phải xử lý đúng những trường hợp không đạt và giải thích được vì sao nó không đạt.

Ví dụ, thư viện Northstar có tính năng audit được bật bằng property:

~~~properties
northstar.audit.enabled=true
~~~

Quy tắc mong muốn:

- Property là `true`: điều kiện khớp, bean audit được tạo.
- Property là `false`: điều kiện không khớp, bean không được tạo.
- Property không được khai báo: điều kiện không khớp và thông báo nói rõ property đang thiếu.
- Property có giá trị không hợp lệ như `yes`: điều kiện không khớp và thông báo nêu giá trị không được hỗ trợ.

Ta cần kiểm tra hai đầu ra độc lập:

1. **Kết quả điều kiện:** match hay no-match, thể hiện qua việc bean có được đăng ký hay không và `ConditionOutcome.isMatch()`.
2. **Thông điệp chẩn đoán:** lý do cụ thể được ghi vào condition evaluation report, thể hiện qua `ConditionOutcome.getMessage()`.

Kiểm thử cả hai giúp tránh tình huống điều kiện trả về đúng boolean nhưng báo cáo khó hiểu, hoặc thông báo nói một đằng trong khi bean lại được đăng ký theo nhánh khác.

## 2. `Condition` và `SpringBootCondition`

Spring Framework định nghĩa interface `org.springframework.context.annotation.Condition`. Một implementation thông thường viết phương thức:

~~~java
boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata)
~~~

Phương thức chỉ trả về `true` hoặc `false`. Nó không có kiểu kết quả chuẩn để đính kèm lý do match/no-match.

Spring Boot cung cấp lớp cơ sở `org.springframework.boot.autoconfigure.condition.SpringBootCondition`. Thay vì tự viết `matches`, lớp con triển khai:

~~~java
ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
)
~~~

`ConditionOutcome` chứa trạng thái match hoặc no-match cùng thông điệp giải thích kết quả. Lớp cơ sở `SpringBootCondition` thực hiện phần điều phối: gọi `getMatchOutcome`, ghi log kết quả và lưu kết quả vào `ConditionEvaluationReport`. Vì vậy, condition tùy chỉnh nên trả về `ConditionOutcome.match(...)` hoặc `ConditionOutcome.noMatch(...)` thay vì tự log hoặc ghi report bằng tay.

| Thành phần | Trách nhiệm |
|---|---|
| `ConditionContext` | Cung cấp Environment, BeanFactory, ClassLoader và ResourceLoader trong lúc đánh giá |
| `AnnotatedTypeMetadata` | Cung cấp metadata của class hoặc method đang được kiểm tra |
| `SpringBootCondition` | Điều phối đánh giá, log và ghi nhận kết quả |
| `ConditionOutcome` | Chứa kết quả match/no-match và thông điệp |
| `ConditionMessage` | Tạo thông điệp nhất quán cho kết quả điều kiện |
| `ConditionEvaluationReport` | Lưu các kết quả theo class hoặc bean method nguồn |

Chỉ viết custom condition khi các condition có sẵn như `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean` hoặc `@ConditionalOnResource` không diễn tả được quy tắc cần thiết. Condition tùy chỉnh làm tăng phần code phải kiểm thử và duy trì.

## 3. Tạo annotation cho điều kiện riêng

Ví dụ tạo annotation `@ConditionalOnAuditEnabled`:

~~~java
package com.example.audit.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnAuditEnabledCondition.class)
public @interface ConditionalOnAuditEnabled {
}
~~~

Annotation có thể đặt trên class cấu hình hoặc method `@Bean`. Trong bài này, ta đặt nó trên auto-configuration để test dễ quan sát một kết quả cho cả cấu hình.

Condition triển khai `SpringBootCondition`:

~~~java
package com.example.audit.autoconfigure;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class OnAuditEnabledCondition extends SpringBootCondition {

    private static final String PROPERTY = "northstar.audit.enabled";

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String configuredValue =
                context.getEnvironment().getProperty(PROPERTY);

        if (configuredValue == null) {
            return ConditionOutcome.noMatch(
                    ConditionMessage.of(
                            "property '" + PROPERTY + "' is missing; expected 'true'"
                    )
            );
        }

        String value = configuredValue.trim();

        if ("true".equalsIgnoreCase(value)) {
            return ConditionOutcome.match(
                    ConditionMessage.of(
                            "property '" + PROPERTY + "' is true"
                    )
            );
        }

        if ("false".equalsIgnoreCase(value)) {
            return ConditionOutcome.noMatch(
                    ConditionMessage.of(
                            "property '" + PROPERTY + "' is false"
                    )
            );
        }

        return ConditionOutcome.noMatch(
                ConditionMessage.of(
                        "property '" + PROPERTY + "' has unsupported value '"
                                + configuredValue + "'; expected 'true' or 'false'"
                )
        );
    }
}
~~~

Các nhánh được tách rõ ràng:

- `null` nghĩa là property không tồn tại.
- `true` không phân biệt chữ hoa/thường nghĩa là bật tính năng.
- `false` nghĩa là tắt tính năng.
- Giá trị còn lại là cấu hình không hợp lệ.

Không dùng riêng `Boolean.parseBoolean(value)` nếu cần chẩn đoán giá trị sai. Phương thức đó trả `false` cho mọi chuỗi khác `true`, vì vậy `false`, chuỗi rỗng và `yes` sẽ bị gộp vào cùng một nhánh. Việc phân biệt các trạng thái giúp thông điệp hữu ích hơn khi cấu hình ứng dụng.

`ConditionMessage.of(...)` tạo một thông điệp có thể truyền cho `ConditionOutcome.match(...)` hoặc `ConditionOutcome.noMatch(...)`. Với thông điệp phức tạp hơn, Spring Boot còn cung cấp builder `ConditionMessage.forCondition(...)`.

## 4. Dùng condition trong auto-configuration

Tạo bean chỉ khi điều kiện match:

~~~java
package com.example.audit.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnAuditEnabled
public class AuditFeatureAutoConfiguration {

    @Bean
    AuditFeature auditFeature() {
        return new AuditFeature();
    }
}
~~~

Kiểu bean mẫu:

~~~java
package com.example.audit.autoconfigure;

public final class AuditFeature {
}
~~~

Khi `northstar.audit.enabled=true`, Spring đăng ký `AuditFeature`. Khi property bị thiếu, là `false` hoặc chứa giá trị không hỗ trợ, cấu hình không match và bean không được đăng ký.

Trong thư viện thực tế, thêm class `AuditFeatureAutoConfiguration` vào file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File này cần thiết để ứng dụng khám phá auto-configuration qua starter đã đóng gói. Ví dụ kiểm thử bằng `ApplicationContextRunner` có thể đăng ký class trực tiếp, nên bản thân test runner không chứng minh file imports đã được đóng gói đúng. Nếu cần kiểm tra discovery của artifact, bổ sung consumer smoke test riêng.


## 5. Kiểm thử bốn trường hợp bằng `ApplicationContextRunner`

`ApplicationContextRunner` tạo một application context mới cho mỗi lần chạy test. Nó cho phép cung cấp tập auto-configuration, property, user configuration và classloader cụ thể. Đây là công cụ phù hợp để kiểm thử condition mà không phải khởi động toàn bộ ứng dụng.

Test dưới đây xác nhận:

1. Property là `true`: condition match và bean xuất hiện.
2. Property là `false`: condition không match và bean vắng mặt.
3. Property bị thiếu: condition không match với lý do thiếu cấu hình.
4. Property sai định dạng: condition không match và báo giá trị không được hỗ trợ.

Tệp `src/test/java/com/example/audit/autoconfigure/AuditFeatureConditionTests.java`:

~~~java
package com.example.audit.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditFeatureConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AuditFeatureAutoConfiguration.class
                            )
                    );

    @Test
    void matchesWhenPropertyIsTrue() {
        runner.withPropertyValues("northstar.audit.enabled=true")
                .run(context -> {
                    assertThat(context.getBeansOfType(AuditFeature.class))
                            .hasSize(1);

                    ConditionOutcome outcome = conditionOutcome(context);

                    assertThat(outcome.isMatch()).isTrue();
                    assertThat(outcome.getMessage())
                            .contains("northstar.audit.enabled")
                            .contains("is true");
                });
    }

    @Test
    void doesNotMatchWhenPropertyIsFalse() {
        runner.withPropertyValues("northstar.audit.enabled=false")
                .run(context -> {
                    assertThat(context.getBeansOfType(AuditFeature.class))
                            .isEmpty();

                    ConditionOutcome outcome = conditionOutcome(context);

                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("northstar.audit.enabled")
                            .contains("is false");
                });
    }

    @Test
    void doesNotMatchWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context.getBeansOfType(AuditFeature.class))
                    .isEmpty();

            ConditionOutcome outcome = conditionOutcome(context);

            assertThat(outcome.isMatch()).isFalse();
            assertThat(outcome.getMessage())
                    .contains("northstar.audit.enabled")
                    .contains("is missing");
        });
    }

    @Test
    void reportsUnsupportedPropertyValue() {
        runner.withPropertyValues("northstar.audit.enabled=yes")
                .run(context -> {
                    assertThat(context.getBeansOfType(AuditFeature.class))
                            .isEmpty();

                    ConditionOutcome outcome = conditionOutcome(context);

                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("unsupported value 'yes'")
                            .contains("expected 'true' or 'false'");
                });
    }

    private ConditionOutcome conditionOutcome(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        var source = report.getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().equals(
                        AuditFeatureAutoConfiguration.class.getName()
                ))
                .findFirst()
                .orElseThrow(() ->
                        new AssertionError(
                                "Condition report entry for AuditFeatureAutoConfiguration was not found"
                        )
                );

        return source.getValue().iterator().next().getOutcome();
    }
}
~~~

### 5.1. Vì sao test đọc `ConditionEvaluationReport`?

Chỉ kiểm tra bean có tồn tại hay không chưa chứng minh condition đã đi qua đúng nhánh. Ví dụ, bean có thể vắng mặt vì một condition khác không match hoặc vì cấu hình chưa được nhập.

`ConditionEvaluationReport` lưu các kết quả theo nguồn là tên class hoặc bean method. Test lấy entry của `AuditFeatureAutoConfiguration` rồi đọc `ConditionOutcome`:

- `isMatch()` xác nhận kết quả logic.
- `getMessage()` xác nhận lý do được condition trả về.

Helper `conditionOutcome` giữ phần truy xuất report ở một chỗ, để từng test tập trung vào tình huống đang kiểm tra.

Nếu condition được đặt trên một phương thức `@Bean` thay vì class cấu hình, nguồn trong report có thể là tên class nối với `#tênBeanMethod`. Khi đó, hãy lọc theo key tương ứng với bean method, thay vì mặc định dùng tên class.

### 5.2. Ma trận test mong đợi

| Property | Bean `AuditFeature` | `isMatch()` | Nội dung thông điệp |
|---|---|---|---|
| `true` | Có | `true` | Property là true |
| `false` | Không | `false` | Property là false |
| Không khai báo | Không | `false` | Property bị thiếu |
| `yes` | Không | `false` | Giá trị không hỗ trợ; yêu cầu true hoặc false |

Một test tốt xác nhận đồng thời cả ba lớp: input, kết quả bean và chẩn đoán. Nhờ đó, khi refactor logic condition, test sẽ phát hiện cả thay đổi hành vi lẫn thông điệp bị mất hoặc sai.


## 6. In báo cáo condition trong test

Khi cần xem toàn bộ kết quả thay vì chỉ một condition, dùng `ConditionEvaluationReportLoggingListener`. Listener là `ApplicationContextInitializer` ghi condition evaluation report vào log.

Ví dụ một lần chạy riêng:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(AuditFeatureAutoConfiguration.class)
        )
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
        )
        .withPropertyValues("northstar.audit.enabled=false")
        .run(context -> {
            assertThat(context.getBeansOfType(AuditFeature.class)).isEmpty();
        });
~~~

`forLogLevel(LogLevel.INFO)` yêu cầu report được ghi ở mức INFO. Listener mặc định ghi report ở DEBUG. Tạo listener mới cho mỗi context; Javadoc lưu ý listener không được thiết kế để dùng chung giữa nhiều application context instance.

Dùng hai cách theo mục đích:

- `ConditionEvaluationReport` trong test: đọc một entry cụ thể và assert kết quả cùng thông điệp.
- `ConditionEvaluationReportLoggingListener`: in toàn bộ report để quan sát các condition liên quan trong lần chạy test.

Không cần assert toàn bộ log văn bản nếu mục tiêu là kiểm tra logic condition. Log tổng thể có thể thay đổi về định dạng giữa các phiên bản; test nên assert `ConditionOutcome` và những đoạn thông điệp có ý nghĩa.

## 7. Chẩn đoán trong ứng dụng đang chạy

Khi một bean tự động cấu hình không xuất hiện trong ứng dụng, có thể bật condition report lúc khởi động bằng:

~~~bash
java -jar app.jar --debug
~~~

Hoặc:

~~~bash
java -Ddebug=true -jar app.jar
~~~

Report giúp tìm:

- Auto-configuration nào đã match.
- Auto-configuration nào không match.
- Condition nào không đạt.
- Lý do được condition ghi nhận.
- Cấu hình nào đã bị exclude.

Nếu ứng dụng có Spring Boot Actuator, endpoint `/actuator/conditions` cung cấp condition evaluation report dưới dạng dữ liệu có cấu trúc. Endpoint phải được bật và expose theo cấu hình Actuator của ứng dụng; bảo vệ endpoint bằng cơ chế bảo mật phù hợp, không công khai report nội bộ ra Internet.

Khi đọc report, tìm đúng class hoặc bean method sở hữu bean cần kiểm tra. Một bean có thể vắng mặt vì nhiều nguyên nhân: class không có trên classpath, property không đúng, bean thay thế đã tồn tại, hoặc một condition phụ thuộc chưa đạt. Đọc thông điệp của từng condition giúp phân biệt các trường hợp này.

## 8. Viết thông điệp chẩn đoán có ích

Thông điệp condition nên trả lời ba câu hỏi:

1. **Đã kiểm tra điều gì?** Ví dụ property `northstar.audit.enabled`.
2. **Đã quan sát thấy gì?** Property thiếu, là `false`, hay chứa `yes`.
3. **Điều kiện cần gì để match?** Giá trị phải là `true`.

Ví dụ:

| Trường hợp | Thông điệp phù hợp |
|---|---|
| Match | Property `northstar.audit.enabled` is true |
| No-match | Property `northstar.audit.enabled` is false |
| Missing | Property `northstar.audit.enabled` is missing; expected `true` |
| Invalid | Property has unsupported value `yes`; expected `true` or `false` |

Một vài nguyên tắc:

- Viết rõ lý do, tránh câu chung chung như `condition failed` hoặc `feature disabled`.
- Dùng cùng tên property hoặc class trong mọi nhánh để người đọc tìm được cấu hình nguồn.
- Phân biệt thiếu cấu hình, cấu hình tắt và cấu hình sai.
- Không đưa password, token, secret, connection string chứa thông tin xác thực hoặc dữ liệu nhạy cảm vào message.
- Không phụ thuộc vào toàn bộ câu thông báo trong test nếu một vài từ khóa đã đủ xác nhận nguyên nhân.
- Không dùng exception để biểu diễn một trường hợp no-match bình thường. Điều kiện không đạt thường là một kết quả hợp lệ, không phải lỗi khởi động.

`ConditionMessage` giúp chuẩn hóa cách tạo thông điệp. `ConditionOutcome.match` và `ConditionOutcome.noMatch` thể hiện rõ kết quả. Hãy tạo message ở đúng nhánh; đừng trả về một message thành công cho mọi kết quả rồi chỉ thay boolean.

## 9. Các nguyên tắc khi triển khai custom condition

Condition được đánh giá trong quá trình Spring xử lý cấu hình. Vì vậy, implementation nên nhanh, xác định và không gây side effect.

Nên:

- Đọc `Environment`, metadata, classpath hoặc resource cần thiết.
- Trả về cùng kết quả với cùng input.
- Ghi rõ lý do cho cả nhánh match và no-match.
- Dùng condition tích hợp sẵn nếu nó đã biểu diễn đúng quy tắc.
- Kiểm thử classpath, property và bean conditions theo từng trường hợp.

Tránh:

- Khởi tạo bean hoặc gọi `context.getBean(...)` để quyết định condition.
- Mở kết nối database, gọi HTTP hoặc truy vấn dịch vụ từ xa khi đánh giá condition.
- Ghi file, thay đổi property, sửa global state hoặc thực hiện thao tác không thể lặp lại an toàn.
- Tự log rồi trả về boolean mà không cung cấp `ConditionOutcome`.
- Bắt mọi exception rồi biến thành no-match mà không giữ lại nguyên nhân cần chẩn đoán.
- Đưa giá trị cấu hình bí mật vào thông điệp.

Nếu một điều kiện cần biết bean khác có tồn tại hay không, ưu tiên các annotation có sẵn như `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean`. Nếu cần kết hợp điều kiện, xem `AllNestedConditions`, `AnyNestedCondition` và `NoneNestedConditions` trước khi tự viết logic boolean phức tạp.


## 10. Dependency và lệnh chạy test

Các ví dụ dùng Java 17+, Spring Boot 3.3.x, JUnit 5 và AssertJ. Với Gradle:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Chạy riêng test class bằng Gradle:

~~~bash
./gradlew test --tests com.example.audit.autoconfigure.AuditFeatureConditionTests
~~~

Hoặc Maven:

~~~bash
mvn -Dtest=AuditFeatureConditionTests test
~~~

Bài test có bốn trường hợp. Kết quả mong đợi là bốn test pass: một nhánh match, ba nhánh no-match. Đây là kết quả kỳ vọng từ ví dụ; chưa phải log của một lần chạy thực tế.

## 11. Các lỗi thường gặp

1. **Chỉ kiểm tra bean có tồn tại hay không.** Bean vắng mặt có thể do một condition khác. Hãy kiểm tra cả `ConditionOutcome` trong report.
2. **Chỉ kiểm thử nhánh match.** Bổ sung test cho property false, missing và invalid để tránh các nhánh no-match bị sai hoặc không có thông điệp.
3. **Dùng `Boolean.parseBoolean` rồi gộp mọi giá trị sai thành false.** Nếu cần chẩn đoán cấu hình lỗi, phân biệt false, missing và giá trị không hợp lệ.
4. **Triển khai trực tiếp Spring `Condition` nhưng mong có message tự động.** `Condition.matches` chỉ trả boolean. Kế thừa `SpringBootCondition` và trả về `ConditionOutcome` để dùng cơ chế report của Boot.
5. **Override `matches` trong lớp kế thừa `SpringBootCondition`.** Đây là phương thức final; triển khai `getMatchOutcome`.
6. **Tự log thông điệp trong condition.** Có thể tạo log trùng lặp và không đưa lý do vào condition report. Trả message qua `ConditionOutcome`.
7. **Condition có side effect.** Không gọi HTTP, truy vấn database hoặc khởi tạo bean trong lúc đánh giá condition.
8. **Không phân biệt condition đặt trên class và bean method.** Source key trong report có thể là tên class hoặc tên class kèm `#beanMethod`. Hãy lấy đúng source.
9. **Assert toàn bộ chuỗi log.** Log tổng thể có thể thay đổi format. Assert `isMatch()` và các đoạn message ổn định.
10. **Đưa dữ liệu nhạy cảm vào message.** Report có thể xuất hiện trong log hoặc endpoint Actuator. Chỉ ghi tên cấu hình và lý do an toàn.
11. **Dùng exception cho một no-match bình thường.** Một điều kiện không đạt là kết quả hợp lệ; chỉ ném exception khi ứng dụng thực sự không thể tiếp tục.
12. **Bỏ qua condition tích hợp sẵn.** Nếu `@ConditionalOnProperty` hoặc condition có sẵn đã đủ diễn tả yêu cầu, dùng nó để giảm code tùy chỉnh phải duy trì.

## 12. Quy trình kiểm thử một custom condition

1. Viết quy tắc bằng câu rõ ràng: input nào làm điều kiện match, input nào làm no-match.
2. Liệt kê tất cả trạng thái đầu vào: đúng, sai, thiếu và không hợp lệ; thêm các trường hợp classpath hoặc bean nếu condition kiểm tra chúng.
3. Triển khai condition bằng `SpringBootCondition` và trả về `ConditionOutcome` cho mọi nhánh.
4. Tạo message nêu rõ dữ liệu đã kiểm tra và lý do kết quả.
5. Dùng `ApplicationContextRunner` để nạp auto-configuration và thay đổi từng input theo test case.
6. Assert bean được tạo hoặc không được tạo.
7. Đọc `ConditionEvaluationReport` để assert `isMatch()` và message của đúng source.
8. Thêm test log report bằng `ConditionEvaluationReportLoggingListener` khi cần quan sát toàn bộ condition.
9. Nếu điều kiện phụ thuộc classpath, dùng `FilteredClassLoader` để kiểm tra thư viện vắng mặt.
10. Chạy test trong project với phiên bản Spring Boot thực tế và kiểm tra report khi một nhánh không cho kết quả mong muốn.

## 13. Ghi nhớ

- Custom condition nên kế thừa `SpringBootCondition` khi cần kết quả cùng thông điệp chẩn đoán.
- Triển khai `getMatchOutcome`; không override `matches`.
- Dùng `ConditionOutcome.match` và `ConditionOutcome.noMatch` để biểu diễn hai nhánh.
- `ConditionMessage` tạo thông điệp nhất quán và `ConditionEvaluationReport` lưu kết quả theo class hoặc bean method.
- `ApplicationContextRunner` giúp kiểm thử từng tổ hợp property, bean và classpath trong context nhỏ.
- Kiểm tra cả bean behavior, `isMatch()` và message; không chỉ nhìn vào việc context có khởi động được hay không.
- Phân biệt property false, property thiếu và giá trị sai định dạng nếu chúng có ý nghĩa chẩn đoán khác nhau.
- Dùng `ConditionEvaluationReportLoggingListener` trong test, `--debug` khi khởi động ứng dụng hoặc Actuator conditions endpoint để điều tra.
- Condition nên nhanh, xác định, không side effect và không ghi thông tin bí mật.

### Tài liệu Spring Boot 3.3 chính thức

- Javadoc `SpringBootCondition`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html
- Javadoc `ConditionOutcome`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html
- Javadoc `ConditionMessage`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html
- Javadoc `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Javadoc `ConditionEvaluationReportLoggingListener`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Creating Your Own Auto-configuration — testing auto-configuration và condition report: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Testing Spring Boot Applications — test support và ApplicationContextRunner: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Testing — các module test support của Spring Boot: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
