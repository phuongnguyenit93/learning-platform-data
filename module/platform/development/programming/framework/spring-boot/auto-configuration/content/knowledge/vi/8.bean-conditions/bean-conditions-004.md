# Quy tắc kết hợp nhiều yêu cầu trong điều kiện có bean và thiếu bean

## 1. Mục tiêu và bối cảnh

Trong Spring Boot Auto Configuration, `@ConditionalOnBean` và `@ConditionalOnMissingBean` quyết định một cấu hình hoặc một phương thức `@Bean` có được đăng ký hay không dựa trên **các bean definition mà ApplicationContext/BeanFactory đã biết tại thời điểm đánh giá**. Bài này tập trung vào trường hợp **một annotation chứa nhiều yêu cầu**: nhiều kiểu bean, nhiều tên bean, nhiều annotation hoặc kết hợp các nhóm đó.

Sau bài học, bạn cần trả lời được ba câu hỏi: (1) Các yêu cầu được ghép theo logic nào? (2) Chúng có phải cùng khớp trên **một bean duy nhất** không? (3) Vì sao điều kiện “thiếu ít nhất một bean” khác với `@ConditionalOnMissingBean` khai báo nhiều kiểu?

## 2. Quy tắc cốt lõi: tất cả có / tất cả không

Đặt `hasA` = BeanFactory đã nhận diện một bean phù hợp kiểu `A`; `hasB` tương tự cho `B`.

- `@ConditionalOnBean({A.class, B.class})` khớp khi `hasA && hasB`. **Mỗi yêu cầu đều phải được đáp ứng**.
- `@ConditionalOnMissingBean({A.class, B.class})` khớp khi `!hasA && !hasB`. **Không yêu cầu nào được đáp ứng**: cả A và B đều vắng mặt.
- Các yêu cầu không nhất thiết được đáp ứng bởi **cùng một bean**. Hai bean riêng biệt, một kiểu A và một kiểu B, đủ cho điều kiện thứ nhất.
- Hai annotation trên **không phải hai nhánh bổ sung nhau** khi khai báo nhiều kiểu. Có trạng thái khiến cả hai đều không khớp.

| Bean A có mặt? | Bean B có mặt? | `@ConditionalOnBean({A,B})` | `@ConditionalOnMissingBean({A,B})` |
| --- | --- | --- | --- |
| Không | Không | Không khớp | **Khớp** |
| Có | Không | Không khớp | Không khớp |
| Không | Có | Không khớp | Không khớp |
| Có | Có | **Khớp** | Không khớp |

Diễn giải tình huống chỉ có A: điều kiện `OnBean` từ chối vì thiếu B; điều kiện `OnMissingBean` cũng từ chối vì A đã tồn tại. **“Thiếu cả A lẫn B” hoàn toàn khác “thiếu A hoặc B”.** Theo De Morgan, phủ định của `hasA && hasB` là `!hasA || !hasB`, không phải `!hasA && !hasB`.

## 3. Cách ghép nhiều yêu cầu trên từng thuộc tính

### 3.1. Nhiều kiểu: `value` hoặc `type`

```java
@ConditionalOnBean({DataSource.class, TransactionManager.class})
// Cần có ít nhất một bean kiểu DataSource
// VÀ ít nhất một bean kiểu TransactionManager.

@ConditionalOnMissingBean({DataSource.class, TransactionManager.class})
// Chỉ khớp khi không có bean thuộc CẢ HAI kiểu trên.
```

`value` nhận `Class<?>[]`; `type` nhận tên lớp đầy đủ (`String[]`), hữu ích khi cần kiểm tra kiểu bằng tên để hạn chế tham chiếu trực tiếp đến lớp tùy chọn. “Có bean kiểu T” bao gồm bean có kiểu được nhận diện là T hoặc kiểu con/kiểu triển khai phù hợp; không yêu cầu tên bean phải là `t`. Không suy luận rằng nhiều phần tử trong `value` là toán tử OR.

### 3.2. Nhiều tên: `name`

```java
@ConditionalOnBean(name = {"primaryStore", "auditStore"})
// Hai tên bean đều phải tồn tại.

@ConditionalOnMissingBean(name = {"primaryStore", "auditStore"})
// Cả hai tên bean đều phải vắng mặt.
```

Ở đây so khớp theo tên đăng ký trong BeanFactory; bean có tên khác nhưng cùng kiểu không tự đáp ứng yêu cầu tên cụ thể. Chọn `name` khi hợp đồng phụ thuộc vào định danh bean, chọn `value`/`type` khi phụ thuộc vào kiểu.

### 3.3. Nhiều annotation: `annotation`

```java
@ConditionalOnBean(annotation = {Primary.class, Lazy.class})
// Cần có bean mang @Primary và có bean mang @Lazy;
// có thể là hai bean khác nhau.

@ConditionalOnMissingBean(annotation = {Primary.class, Lazy.class})
// Không được có bean khớp @Primary, cũng không có bean khớp @Lazy.
```

Đây là điều kiện về annotation liên quan đến bean được đăng ký; nó **không** đòi một bean đồng thời mang cả hai annotation. Ví dụ chỉ minh họa cách ghép yêu cầu, không khuyến nghị dùng `@Lazy` làm tiêu chí tính năng trong ứng dụng thực tế.

### 3.4. Phối hợp `value`, `type`, `name`, `annotation`

```java
@ConditionalOnBean(
    value = {PaymentGateway.class, AuditWriter.class},
    name = {"paymentGateway", "auditWriter"}
)
```

Các yêu cầu của từng nhóm đều phải được thỏa mãn: có kiểu `PaymentGateway`, có kiểu `AuditWriter` và có đủ hai tên được liệt kê. **Không có bảo đảm** bean tên `paymentGateway` chính là bean thỏa yêu cầu kiểu `PaymentGateway`. Mỗi tiêu chí có thể được đáp ứng bởi một bean khác. Với `@ConditionalOnMissingBean` và một tập các nhóm tương tự, điều kiện chỉ khớp khi **không có bất cứ yêu cầu kiểu/tên/annotation nào** được thỏa mãn.

Nếu cần khẳng định **một bean tên X có kiểu Y**, kiểm tra đồng thời tên và kiểu của chính bean đó bằng `Condition` tùy chỉnh hoặc cơ chế kiểm tra rõ ràng tại BeanFactory (`containsBean("X")` và `isTypeMatch("X", Y.class)`); đừng suy diễn quan hệ “cùng một bean” từ các thuộc tính độc lập của `@ConditionalOnBean`.

## 4. Ví dụ thực hành: kết quả của bốn trạng thái

Một tính năng tích hợp chỉ nên đăng ký khi **đã có cả** `PaymentGateway` lẫn `AuditWriter`. Một thành phần hỗ trợ cấu hình rỗng chỉ nên xuất hiện khi **không có thành phần đầu vào nào**. Nếu người dùng cung cấp đúng một đầu vào, hai bean điều kiện đều không được tạo. Đây là hành vi có chủ đích trong ví dụ, giúp bộc lộ khoảng trống giữa hai nhánh.

Đặt tệp sau trong dự án **Spring Boot 3.3.x, Java 17+**, có `spring-boot-starter-test`, JUnit Jupiter và AssertJ: `src/test/java/example/conditions/MultipleBeanConditionTests.java`.

```java
package example.conditions;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class MultipleBeanConditionTests {

    interface PaymentGateway {}
    interface AuditWriter {}

    static final class DefaultPaymentGateway implements PaymentGateway {}
    static final class DefaultAuditWriter implements AuditWriter {}
    static final class IntegratedService {}
    static final class NoInputsNotice {}

    @Configuration(proxyBeanMethods = false)
    static class OnlyPayment {
        @Bean
        PaymentGateway paymentGateway() {
            return new DefaultPaymentGateway();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OnlyAudit {
        @Bean
        AuditWriter auditWriter() {
            return new DefaultAuditWriter();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BothInputs {
        @Bean
        PaymentGateway paymentGateway() {
            return new DefaultPaymentGateway();
        }

        @Bean
        AuditWriter auditWriter() {
            return new DefaultAuditWriter();
        }
    }

    @AutoConfiguration
    static class FeatureAutoConfiguration {
        @Bean
        @ConditionalOnBean({PaymentGateway.class, AuditWriter.class})
        IntegratedService integratedService(
                PaymentGateway paymentGateway,
                AuditWriter auditWriter) {
            return new IntegratedService();
        }

        @Bean
        @ConditionalOnMissingBean({PaymentGateway.class, AuditWriter.class})
        NoInputsNotice noInputsNotice() {
            return new NoInputsNotice();
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(FeatureAutoConfiguration.class));

    @Test
    void noInputBeansCreatesOnlyNotice() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(NoInputsNotice.class);
            assertThat(context).doesNotHaveBean(IntegratedService.class);
        });
    }

    @Test
    void paymentOnlyCreatesNeitherConditionalBean() {
        runner.withUserConfiguration(OnlyPayment.class).run(context -> {
            assertThat(context).doesNotHaveBean(NoInputsNotice.class);
            assertThat(context).doesNotHaveBean(IntegratedService.class);
        });
    }

    @Test
    void auditOnlyCreatesNeitherConditionalBean() {
        runner.withUserConfiguration(OnlyAudit.class).run(context -> {
            assertThat(context).doesNotHaveBean(NoInputsNotice.class);
            assertThat(context).doesNotHaveBean(IntegratedService.class);
        });
    }

    @Test
    void bothInputsCreateOnlyIntegratedService() {
        runner.withUserConfiguration(BothInputs.class).run(context -> {
            assertThat(context).hasSingleBean(IntegratedService.class);
            assertThat(context).doesNotHaveBean(NoInputsNotice.class);
        });
    }
}
```

**Cách chạy:** Trong dự án Spring Boot dùng Gradle, đã bật JUnit Platform và khai báo dependency test phù hợp, thực hiện:

```bash
./gradlew test --tests example.conditions.MultipleBeanConditionTests
```

Trong dự án Maven đã cấu hình Surefire/JUnit 5, có thể chạy `./mvnw -Dtest=MultipleBeanConditionTests test`. **Kết quả kỳ vọng:** cả bốn test PASS; không suy diễn chuỗi stdout cụ thể vì cách Gradle/Maven in báo cáo phụ thuộc bản build. `ApplicationContextRunner` dựng từng ApplicationContext độc lập; `withUserConfiguration` đăng ký những bean do người dùng cung cấp và `AutoConfigurations.of(...)` đưa auto-configuration vào quá trình đánh giá.

Lưu ý: ```java``` trong đoạn mã trên là một tệp test hoàn chỉnh; không đặt bốn `@Configuration` vào component scan của ứng dụng thật, vì chúng là các cấu hình **tình huống test riêng biệt**.

## 5. Khi muốn “ít nhất một điều kiện đúng” hoặc “ít nhất một bean thiếu”

Phân biệt rõ ý định trước khi chọn annotation:

| Yêu cầu nghiệp vụ | Biểu thức logic với `hasA`, `hasB` | Cách thể hiện |
| --- | --- | --- |
| Đòi đủ A và B | `hasA && hasB` | `@ConditionalOnBean({A.class, B.class})` |
| Đòi A và B đều vắng | `!hasA && !hasB` | `@ConditionalOnMissingBean({A.class, B.class})` |
| Có A **hoặc** B | `hasA || hasB` | `AnyNestedCondition` hoặc `Condition` riêng |
| Thiếu A **hoặc** B | `!hasA || !hasB` | `AnyNestedCondition` hoặc `Condition` riêng |
| Chính xác một trong A/B có | `hasA != hasB` | `Condition` riêng, kèm test bốn trạng thái |

Ví dụ minh họa một `AnyNestedCondition` cho yêu cầu **ít nhất một trong A/B còn thiếu** (đoạn này dùng các kiểu `PaymentGateway` và `AuditWriter` đã định nghĩa trong dự án, không phải một tệp Java độc lập):

```java
import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.ConfigurationCondition;

final class EitherInputMissing extends AnyNestedCondition {
    EitherInputMissing() {
        super(ConfigurationCondition.ConfigurationPhase.REGISTER_BEAN);
    }

    @ConditionalOnMissingBean(PaymentGateway.class)
    static class PaymentMissing {}

    @ConditionalOnMissingBean(AuditWriter.class)
    static class AuditMissing {}
}
```

Sử dụng `@Conditional(EitherInputMissing.class)` tại lớp cấu hình/phương thức bean cần điều kiện đó, với import `org.springframework.context.annotation.Conditional`. Hai điều kiện lồng là hai nhánh OR; khi **ít nhất một** nhánh “missing” khớp, tổng thể khớp. Nếu chỉ cần một bean mặc định của **một kiểu duy nhất** để người dùng ghi đè, thường chỉ dùng `@ConditionalOnMissingBean(MyService.class)`, không gom thêm các kiểu không liên quan.

## 6. Quy tắc thời điểm và phạm vi tra cứu

1. **Thời điểm:** điều kiện dựa trên bean definition đã được xử lý **đến lúc đánh giá**, không phải phép kiểm tra các singleton đã khởi tạo sau khi ứng dụng chạy xong. Một bean sẽ được khai báo về sau không nhất thiết được tính. Hãy đặt các điều kiện này trong **auto-configuration**, nơi các bean người dùng đã được xử lý trước, và điều chỉnh thứ tự giữa các auto-configuration nếu có phụ thuộc.
2. **Thứ tự giữa auto-config:** nếu cấu hình B cần bean do cấu hình A khai báo, dùng `@AutoConfiguration(after = AAutoConfiguration.class)` (hoặc tương đương) để B được đánh giá sau A. `@DependsOn` chỉ quy định thứ tự **khởi tạo bean**, không giải quyết thứ tự đánh giá điều kiện đăng ký bean.
3. **Vị trí annotation:** đặt trên một `@Bean` sẽ quyết định chính phương thức bean đó; đặt trên lớp `@Configuration`/`@AutoConfiguration` sẽ quyết định việc đăng ký lớp cấu hình cùng các bean của nó. Chọn phạm vi hẹp nếu chỉ một bean cần điều kiện.
4. **Không điền thuộc tính:** trên phương thức `@Bean`, nếu không khai báo `value`, `type` hoặc `name`, Spring Boot 3.3 lấy **kiểu trả về của phương thức** làm kiểu mặc định cần kiểm tra. Ví dụ `@Bean @ConditionalOnMissingBean MyService myService()` tạo mặc định khi chưa có bean `MyService`. Để Spring nhận diện kiểu chính xác, khai báo kiểu trả về đủ cụ thể.
5. **Bean cha:** thuộc tính `search` mặc định là `SearchStrategy.ALL` (gồm khả năng xét context cha). `SearchStrategy.CURRENT` chỉ xét context hiện tại; `ANCESTORS` xét context cha theo quy tắc API. Trong các hệ thống có parent/child contexts, chiến lược tra cứu có thể làm thay đổi kết quả bảng điều kiện.
6. **Bean trong generic container:** `parameterizedContainer` cho phép tính một số wrapper có tham số generic khi kiểm tra kiểu. Ví dụ khi cấu hình `value = User.class, parameterizedContainer = Registration.class` thì bean `Registration<User>` có thể được nhận diện theo hợp đồng của thuộc tính này. Đây **không** phải cơ chế tự động quét tất cả generic wrapper.
7. **Loại trừ khi kiểm tra thiếu:** `@ConditionalOnMissingBean` có `ignored` và `ignoredType` để bỏ qua một số kiểu bean trong quá trình tìm bean khớp. `@ConditionalOnBean` không có hai thuộc tính này; đừng nhầm chúng với việc loại trừ hoặc xóa bean thật.

## 7. Lỗi thường gặp và cách chẩn đoán

- **Hiểu nhầm danh sách là OR.** `@ConditionalOnBean({A,B})` nghĩa là cần **A VÀ B**. `@ConditionalOnMissingBean({A,B})` nghĩa là thiếu **A VÀ B**.
- **Cho rằng hai annotation phủ kín mọi trường hợp.** Với “chỉ có A” hoặc “chỉ có B”, cả hai đều từ chối. Lập bảng chân trị trước khi thiết kế fallback.
- **Cho rằng mọi tiêu chí phải trỏ tới cùng một bean.** Kiểu, tên và annotation có thể được đáp ứng bởi các bean khác nhau. Cần một ràng buộc trên cùng bean thì tự kiểm tra tên + kiểu hoặc dùng một định danh bean/kiểu rõ ràng.
- **Đặt điều kiện quá sớm.** Một bean được đăng ký sau lúc kiểm tra làm kết quả khác dự kiến. Xem thứ tự auto-configuration và thông tin bean definitions đã có; đừng dựa vào thứ tự gọi constructor.
- **Sai kiểu hiển thị ở `@Bean`.** Nếu bean thực tế là `SpecialGateway` nhưng phương thức khai báo kiểu trả về quá chung, điều kiện theo `SpecialGateway` có thể không thấy thông tin kiểu cần thiết tại thời điểm xét. Khai báo kiểu trả về hữu ích và ổn định.
- **Nhầm `name` với `@Qualifier`.** `name` kiểm tra tên bean trong container; `@Qualifier` là metadata phục vụ chọn ứng viên injection, không đồng nghĩa một tên bean bất kỳ.
- **Không xét context cha hoặc wrapper generic.** Kiểm tra `search`/`parameterizedContainer` khi môi trường nhiều context hay bean wrapper làm kết quả bất ngờ.

Để kiểm tra kết quả thực tế: chạy ứng dụng với `--debug` để xem condition evaluation report, hoặc dùng `ConditionEvaluationReportLoggingListener` với `ApplicationContextRunner` trong test. Tập trung vào lý do cụ thể điều kiện nào khớp/không khớp và bean definition nào đã được phát hiện. Với một tính năng quan trọng, nên có test cho **không có A/B, chỉ A, chỉ B, có cả A/B**; thêm các biến thể `name`/`annotation` nếu bài toán dùng chúng.

## 8. Tự kiểm tra

1. Có bean A và B do hai phương thức `@Bean` khác nhau đăng ký. `@ConditionalOnBean({A.class, B.class})` có khớp không? **Có**, miễn cả hai đã được xử lý đúng lúc; chúng không cần cùng một bean.
2. Chỉ có A, chưa có B. `@ConditionalOnMissingBean({A.class, B.class})` có khớp không? **Không**, vì yêu cầu “thiếu A” không đúng.
3. Có bean tên `primaryStore` nhưng không có bean kiểu `AuditWriter`. Điều kiện `@ConditionalOnBean(value=AuditWriter.class, name="primaryStore")` có khớp không? **Không**; phải đủ cả yêu cầu kiểu lẫn tên.
4. Cần kích hoạt khi **một trong A/B thiếu**. Dùng `@ConditionalOnMissingBean({A.class,B.class})` có đúng không? **Không**; cần tổ hợp OR qua `AnyNestedCondition` hay `Condition` tương đương.

## Tài liệu đối chiếu (Spring Boot 3.3.x)

- [`@ConditionalOnBean` — API Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)
- [`@ConditionalOnMissingBean` — API Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Creating Your Own Auto-configuration — bean conditions và cách test](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
