# Tạo lỗi thiếu bean, trùng bean, cấu hình sai rồi viết test tái hiện

Một ứng dụng Spring Boot có thể không khởi động vì một dependency không có bean tương ứng, vì nhiều bean cùng thỏa một điểm injection hoặc vì cấu hình không bind/không kích hoạt như dự kiến. Những lỗi này thường xuất hiện dưới dạng stack trace dài bắt đầu bằng `Failed to load ApplicationContext`, `UnsatisfiedDependencyException` hoặc `BeanCreationException`.

Cách học và xử lý hiệu quả là **chủ động tạo một lỗi có kiểm soát, viết test tái hiện lỗi đó, quan sát exception gốc, sửa cấu hình hoặc dependency wiring, rồi giữ test để bảo vệ hành vi mong muốn**.

Bài học thuộc chương **Thực hành tổng hợp** của **Spring Boot Fundamentals**. Chúng ta sẽ thực hành ba nhóm lỗi:

1. **Thiếu bean:** Spring không tìm được dependency để inject.
2. **Trùng bean:** có nhiều candidate cùng type và Spring không biết chọn bean nào.
3. **Cấu hình sai:** property thiếu, sai kiểu, không hợp lệ hoặc conditional configuration không kích hoạt bean cần thiết.

Ta dùng một ví dụ checkout/payment nhỏ xuyên suốt. Các test tập trung vào ApplicationContext và dependency injection, vì mục tiêu là tái hiện lỗi cấu hình một cách cô lập.

## 1. Chuẩn bị project kiểm thử

Ví dụ sử dụng Java 17 trở lên và Spring Boot 3.x. Các API kiểm thử chính là JUnit Jupiter, AssertJ và `ApplicationContextRunner`.

Với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Nếu bài thực hành dùng Jakarta Bean Validation như `@NotBlank` và `@Min`, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

`spring-boot-starter-test` cung cấp JUnit 5, AssertJ, Mockito và Spring Boot test support. Dùng Spring Boot dependency management để các thư viện tương thích với phiên bản Boot của project.

### 1.1. Cấu trúc source gợi ý

```text
src/
├── main/
│   ├── java/com/example/shop/
│   │   ├── ShopApplication.java
│   │   ├── checkout/
│   │   │   ├── CheckoutService.java
│   │   │   └── PaymentGateway.java
│   │   └── config/
│   │       └── CheckoutConfiguration.java
│   └── resources/
│       └── application.yml
└── test/
    └── java/com/example/shop/
        ├── MissingBeanTests.java
        ├── DuplicateBeanTests.java
        └── InvalidConfigurationTests.java
```

Trong các ví dụ dùng `ApplicationContextRunner`, ta khai báo configuration class tĩnh trong test để chủ động tạo context nhỏ. Cách này giúp tái hiện failure mà không cần khởi động cả ứng dụng hoặc phụ thuộc component scan ngoài ý muốn.

## 2. Mô hình ứng dụng mẫu

Tạo contract cho cổng thanh toán:

```java
package com.example.shop.checkout;

public interface PaymentGateway {
    String name();
    PaymentResult charge(long amountInCents);
}
```

Kết quả thanh toán:

```java
package com.example.shop.checkout;

public record PaymentResult(
        String transactionId,
        boolean approved
) {
}
```

Service cần một bean implement `PaymentGateway`:

```java
package com.example.shop.checkout;

public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public String selectedGateway() {
        return paymentGateway.name();
    }

    public PaymentResult checkout(long amountInCents) {
        if (amountInCents <= 0) {
            throw new IllegalArgumentException(
                    "amount must be positive"
            );
        }
        return paymentGateway.charge(amountInCents);
    }
}
```

Configuration tạo service:

```java
package com.example.shop.config;

import com.example.shop.checkout.CheckoutService;
import com.example.shop.checkout.PaymentGateway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutConfiguration {

    @Bean
    CheckoutService checkoutService(PaymentGateway paymentGateway) {
        return new CheckoutService(paymentGateway);
    }
}
```

Spring cần resolve tham số `PaymentGateway` của bean factory method. Nó tìm các bean candidate theo type:

```text
Tạo bean CheckoutService
          │
          ▼
Cần tham số PaymentGateway
          │
          ▼
Tìm bean có type tương thích
          │
      ┌───┴────────┐
      │            │
      ▼            ▼
   0 candidate   1 candidate
      │            │
      ▼            ▼
    Lỗi          Inject
                   │
                   ▼
             CheckoutService
```

Nếu có từ hai candidate trở lên, Spring cần thêm thông tin để chọn. Ba tình huống này là nền tảng cho các bài lab tiếp theo.

## 3. Lỗi 1: thiếu bean dependency

### 3.1. Tạo lỗi có chủ đích

Giữ `CheckoutConfiguration` như trên nhưng không đăng ký bất kỳ bean `PaymentGateway` nào.

Context có cấu hình tạo `CheckoutService`, nhưng constructor/factory method cần một dependency chưa tồn tại.

Thông báo thường có dạng:

```text
Parameter 0 of method checkoutService required a bean of type
'com.example.shop.checkout.PaymentGateway' that could not be found.
```

Hoặc:

```text
No qualifying bean of type 'PaymentGateway' available
```

Exception bên ngoài thường là `UnsatisfiedDependencyException`; nguyên nhân sâu hơn có thể là `NoSuchBeanDefinitionException`.

### 3.2. Viết test tái hiện bằng ApplicationContextRunner

`ApplicationContextRunner` cho phép dựng context thử nghiệm từ configuration class được chỉ định và quan sát trạng thái sau startup.

```java
package com.example.shop;

import com.example.shop.config.CheckoutConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;

import static org.assertj.core.api.Assertions.assertThat;

class MissingBeanTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(CheckoutConfiguration.class);

    @Test
    void contextFailsWhenPaymentGatewayBeanIsMissing() {
        contextRunner.run(context -> {
            assertThat(context).hasFailed();

            assertThat(context.getStartupFailure())
                    .isNotNull()
                    .hasRootCauseInstanceOf(
                            NoSuchBeanDefinitionException.class
                    );
        });
    }
}
```

Test này **mong đợi context thất bại**. JUnit vẫn báo pass nếu context thất bại đúng như dự đoán và nguyên nhân gốc thuộc loại mong đợi.

Đây là kỹ thuật hữu ích: thay vì để lỗi startup làm cả test suite không thể chạy, runner giữ failure trong `context.getStartupFailure()` để bạn assert.

### 3.3. Đọc exception theo cause chain

Đừng chỉ đọc dòng đầu tiên `Failed to load ApplicationContext`. Hãy tìm:

- Bean nào đang được tạo?
- Dependency nào không resolve?
- Type nào được yêu cầu?
- Có bean candidate nào bị loại do profile hoặc condition không?
- Root cause là missing definition hay lỗi tạo bean khác?

Một stack trace có thể đi qua nhiều tầng:

```text
BeanCreationException
  └── UnsatisfiedDependencyException
        └── NoSuchBeanDefinitionException
```

Tên wrapper exception cho biết giai đoạn thất bại; root cause thường chỉ ra vấn đề cần sửa.

### 3.4. Sửa bằng cách cung cấp implementation

Tạo implementation:

```java
package com.example.shop.checkout;

public class SandboxPaymentGateway implements PaymentGateway {

    @Override
    public String name() {
        return "sandbox";
    }

    @Override
    public PaymentResult charge(long amountInCents) {
        return new PaymentResult("sandbox-transaction", true);
    }
}
```

Đăng ký implementation:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentGatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new SandboxPaymentGateway();
    }
}
```

Thêm configuration này vào runner:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(
                        CheckoutConfiguration.class,
                        PaymentGatewayConfiguration.class
                );
```

Test thành công:

```java
@Test
void contextStartsWhenPaymentGatewayIsProvided() {
    contextRunner.run(context -> {
        assertThat(context).hasNotFailed();
        assertThat(context).hasSingleBean(PaymentGateway.class);
        assertThat(context).hasSingleBean(CheckoutService.class);

        assertThat(context.getBean(CheckoutService.class)
                .selectedGateway())
                .isEqualTo("sandbox");
    });
}
```

Test kiểm tra context không lỗi, có đúng một bean gateway và service nhận đúng implementation.

### 3.5. Những nguyên nhân missing bean thường gặp

| Nguyên nhân | Dấu hiệu | Cách kiểm tra |
|---|---|---|
| Class thiếu `@Component` | Implementation không thành bean | Kiểm tra stereotype hoặc `@Bean` |
| Package ngoài component scan | Class có annotation nhưng không được phát hiện | Kiểm tra package của `@SpringBootApplication` |
| Chưa import configuration | Bean khai báo trong config không được load | Kiểm tra `@Import` và component scan |
| Profile không active | Bean có `@Profile` bị loại | Kiểm tra active profiles |
| Conditional property không match | Bean có `@ConditionalOnProperty` không xuất hiện | Kiểm tra tên và giá trị property |
| Dependency ngoài classpath | Auto-configuration không kích hoạt | Kiểm tra runtime dependencies |
| Test slice loại bean | Context test chỉ load một phần ứng dụng | Import test configuration phù hợp |
| Bean definition bị exclude | Component scan/filter loại class | Kiểm tra scan filters và exclusions |

### 3.6. Missing bean do component scan

Giả sử main application nằm tại:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

Component scan mặc định thường bắt đầu từ package của class này và các package con. Nếu runner hoặc adapter nằm ở `com.other.payment`, nó có thể nằm ngoài scan boundary.

Có ba cách thường dùng:

1. Di chuyển class vào package con của application root.
2. Import configuration/bean rõ ràng.
3. Cấu hình component scan với base packages phù hợp.

Đừng mở scan quá rộng nếu điều đó có thể đăng ký nhầm class từ module khác.

## 4. Lỗi 2: nhiều bean cùng type

Tạo hai implementation cho cùng contract:

```java
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public String name() {
        return "card";
    }

    @Override
    public PaymentResult charge(long amountInCents) {
        return new PaymentResult("card-transaction", true);
    }
}
```

```java
public class BankTransferGateway implements PaymentGateway {

    @Override
    public String name() {
        return "bank-transfer";
    }

    @Override
    public PaymentResult charge(long amountInCents) {
        return new PaymentResult("bank-transaction", true);
    }
}
```

Đăng ký cả hai:

```java
@Configuration(proxyBeanMethods = false)
class TwoPaymentGatewaysConfiguration {

    @Bean
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    PaymentGateway bankTransferGateway() {
        return new BankTransferGateway();
    }
}
```

Khi tạo `CheckoutService`, Spring thấy hai bean candidate cùng type `PaymentGateway`.

### 4.1. Thông báo lỗi

Thông báo thường có dạng:

```text
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2:
cardPaymentGateway,bankTransferGateway
```

Exception gốc thường là `NoUniqueBeanDefinitionException`; nó có thể được bọc trong `UnsatisfiedDependencyException` hoặc `BeanCreationException`.

### 4.2. Viết test tái hiện

```java
package com.example.shop;

import com.example.shop.config.CheckoutConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;

import static org.assertj.core.api.Assertions.assertThat;

class DuplicateBeanTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            CheckoutConfiguration.class,
                            TwoPaymentGatewaysConfiguration.class
                    );

    @Test
    void contextFailsWhenTwoGatewaysAreCandidates() {
        contextRunner.run(context -> {
            assertThat(context).hasFailed();

            assertThat(context.getStartupFailure())
                    .isNotNull()
                    .hasRootCauseInstanceOf(
                            NoUniqueBeanDefinitionException.class
                    );
        });
    }
}
```

Test xác nhận lỗi ambiguity. Nếu vô tình xóa một bean hoặc thay injection point, test không còn thất bại theo cách mong đợi và báo regression.

## 5. Sửa lỗi trùng bean bằng @Primary

Nếu một implementation thực sự là lựa chọn mặc định, đánh dấu bean đó bằng `@Primary`.

```java
@Configuration(proxyBeanMethods = false)
class PrimaryPaymentGatewayConfiguration {

    @Bean
    @Primary
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    PaymentGateway bankTransferGateway() {
        return new BankTransferGateway();
    }
}
```

Khi inject theo type `PaymentGateway`, Spring ưu tiên candidate primary.

Test:

```java
@Test
void primaryGatewayIsSelected() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    CheckoutConfiguration.class,
                    PrimaryPaymentGatewayConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasBean("cardPaymentGateway");
                assertThat(context).hasBean("bankTransferGateway");

                assertThat(context.getBean(CheckoutService.class)
                        .selectedGateway())
                        .isEqualTo("card");
            });
}
```

Hai bean vẫn tồn tại. `@Primary` chỉ giúp Spring chọn candidate mặc định cho injection theo type.

### 5.1. Khi nào không nên dùng @Primary?

Nếu hai implementation đại diện cho hai capability khác nhau và từng consumer cần lựa chọn cụ thể, việc đánh dấu một bean primary có thể che giấu lựa chọn sai.

Ví dụ service chuyển khoản phải luôn dùng bank gateway, còn service thanh toán thẻ phải luôn dùng card gateway. Dùng `@Qualifier` sẽ diễn đạt ý định rõ hơn.

## 6. Sửa lỗi trùng bean bằng @Qualifier

Đánh dấu bean bằng qualifier:

```java
@Configuration(proxyBeanMethods = false)
class QualifiedPaymentGatewayConfiguration {

    @Bean
    @Qualifier("card")
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("bankTransfer")
    PaymentGateway bankTransferGateway() {
        return new BankTransferGateway();
    }
}
```

Chọn bean tại injection point:

```java
public class CardCheckoutService {

    private final PaymentGateway paymentGateway;

    public CardCheckoutService(
            @Qualifier("card") PaymentGateway paymentGateway
    ) {
        this.paymentGateway = paymentGateway;
    }

    public String selectedGateway() {
        return paymentGateway.name();
    }
}
```

Đăng ký service:

```java
@Bean
CardCheckoutService cardCheckoutService(
        @Qualifier("card") PaymentGateway paymentGateway
) {
    return new CardCheckoutService(paymentGateway);
}
```

Test:

```java
@Test
void qualifierSelectsCardGateway() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    QualifiedPaymentGatewayConfiguration.class,
                    CardCheckoutConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context.getBean(CardCheckoutService.class)
                        .selectedGateway())
                        .isEqualTo("card");
            });
}
```

`@Qualifier` là lựa chọn tốt khi consumer cần một implementation cụ thể. Nó làm ý định được ghi ngay tại dependency injection point.

### 6.1. Tên bean và qualifier

Tên method `@Bean` mặc định cũng trở thành bean name. Spring có thể dùng bean name như một fallback qualifier trong một số trường hợp, nhưng nên khai báo qualifier tường minh khi lựa chọn có ý nghĩa kiến trúc.

### 6.2. Không dùng @Primary để che cấu hình sai

Nếu một bean được đánh dấu primary chỉ để ứng dụng khởi động được, hãy xác nhận đó thực sự là implementation đúng cho consumer. Context xanh không tự chứng minh hệ thống đang gọi đúng payment provider.

## 7. Lỗi 3: cấu hình properties sai

Spring Boot thường bind cấu hình bên ngoài vào object bằng `@ConfigurationProperties`. Nếu property sai kiểu hoặc vi phạm validation, quá trình tạo bean có thể thất bại.

Tạo cấu hình checkout:

```java
package com.example.shop.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "checkout")
@Validated
public record CheckoutProperties(
        @Min(1) int maxAttempts,
        @NotBlank String baseUrl
) {
}
```

Đăng ký properties:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CheckoutProperties.class)
class CheckoutPropertiesConfiguration {
}
```

### 7.1. Cấu hình hợp lệ

```yaml
checkout:
  max-attempts: 3
  base-url: https://checkout.example.test
```

Với cấu hình này, `max-attempts` bind vào integer và phải từ 1 trở lên; `base-url` phải là chuỗi không rỗng. Bean properties chỉ được tạo thành công nếu binding và validation thành công.

### 7.2. Tạo lỗi validation

Cấu hình sai:

```yaml
checkout:
  max-attempts: 0
  base-url: ""
```

Giá trị `0` vi phạm `@Min(1)` và chuỗi rỗng vi phạm `@NotBlank`.

### 7.3. Test tái hiện cấu hình sai

```java
package com.example.shop;

import com.example.shop.config.CheckoutPropertiesConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;

import static org.assertj.core.api.Assertions.assertThat;

class InvalidConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            CheckoutPropertiesConfiguration.class
                    );

    @Test
    void contextFailsWhenPropertiesViolateValidation() {
        contextRunner
                .withPropertyValues(
                        "checkout.max-attempts=0",
                        "checkout.base-url="
                )
                .run(context -> {
                    assertThat(context).hasFailed();

                    assertThat(context.getStartupFailure())
                            .isNotNull()
                            .hasRootCauseInstanceOf(
                                    BindValidationException.class
                            );
                });
    }
}
```

Test chủ động truyền giá trị không hợp lệ rồi khẳng định context thất bại do binding validation.

Nếu project chưa có `spring-boot-starter-validation`, các constraint Jakarta Validation có thể không được thực thi như mong đợi. Hãy thêm validation provider tương thích với Spring Boot trước khi chạy test.

### 7.4. Test cấu hình hợp lệ

```java
@Test
void contextStartsWithValidCheckoutProperties() {
    contextRunner
            .withPropertyValues(
                    "checkout.max-attempts=3",
                    "checkout.base-url=https://checkout.example.test"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();

                CheckoutProperties properties =
                        context.getBean(CheckoutProperties.class);

                assertThat(properties.maxAttempts()).isEqualTo(3);
                assertThat(properties.baseUrl())
                        .isEqualTo("https://checkout.example.test");
            });
}
```

Test này bảo vệ cả hai điều: cấu hình có thể bind và giá trị nhận được đúng như dự kiến.

## 8. Cấu hình sai kiểu dữ liệu

Một dạng lỗi khác là giá trị không thể chuyển sang Java type.

```yaml
checkout:
  max-attempts: many
  base-url: https://checkout.example.test
```

`max-attempts` cần integer nhưng giá trị `many` không chuyển đổi được.

Test:

```java
@Test
void contextFailsWhenIntegerPropertyCannotBeConverted() {
    contextRunner
            .withPropertyValues(
                    "checkout.max-attempts=many",
                    "checkout.base-url=https://checkout.example.test"
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull()
                        .hasStackTraceContaining("checkout.max-attempts");
            });
}
```

Tùy phiên bản Boot và conversion service, loại exception trong cause chain có thể khác; assertion theo property path thường hữu ích hơn việc phụ thuộc vào một exception nội bộ quá sâu.

### 8.1. Property bị thiếu và default value

Không phải property nào bị thiếu cũng làm startup fail. Với primitive hoặc field có default, ứng dụng có thể nhận giá trị mặc định như `0` hoặc `false`.

Nếu property là bắt buộc, hãy biểu diễn yêu cầu đó bằng validation hoặc một kiểu dữ liệu/cấu hình có thể phát hiện trạng thái thiếu. Đừng giả định mọi missing property tự động gây exception.

## 9. Lỗi conditional configuration không kích hoạt bean

Một bean có thể chỉ được tạo khi property thỏa điều kiện.

```java
@Configuration(proxyBeanMethods = false)
class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "notifications",
            name = "enabled",
            havingValue = "true"
    )
    NotificationSender notificationSender() {
        return new SmtpNotificationSender();
    }

    @Bean
    NotificationService notificationService(
            NotificationSender notificationSender
    ) {
        return new NotificationService(notificationSender);
    }
}
```

Nếu cấu hình ghi sai prefix:

```yaml
notification:
  enabled: true
```

trong khi condition chờ `notifications.enabled`, bean `NotificationSender` không được tạo. `NotificationService` không thể inject dependency và context fail.

### 9.1. Test tái hiện

```java
@Test
void contextFailsWhenConditionalPropertyUsesWrongPrefix() {
    new ApplicationContextRunner()
            .withUserConfiguration(NotificationConfiguration.class)
            .withPropertyValues("notification.enabled=true")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull()
                        .hasRootCauseInstanceOf(
                                NoSuchBeanDefinitionException.class
                        );
            });
}
```

### 9.2. Sửa property

```yaml
notifications:
  enabled: true
```

Test cấu hình đúng:

```java
@Test
void notificationBeanIsCreatedWhenPropertyMatches() {
    new ApplicationContextRunner()
            .withUserConfiguration(NotificationConfiguration.class)
            .withPropertyValues("notifications.enabled=true")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(NotificationSender.class);
                assertThat(context).hasSingleBean(NotificationService.class);
            });
}
```

### 9.3. matchIfMissing

`@ConditionalOnProperty` có thuộc tính `matchIfMissing`. Mặc định, nếu property không tồn tại thì condition thường không match khi yêu cầu một giá trị cụ thể.

Nếu muốn mặc định bật/tắt, hãy đặt semantics rõ trong configuration và test cả hai trường hợp: property có giá trị và property không tồn tại. Đừng dựa vào giá trị mặc định ngầm nếu tác động tới side effects như gửi email hoặc publish message.

## 10. Dùng ApplicationContextRunner để viết test cấu hình

`ApplicationContextRunner` đặc biệt hữu ích khi test auto-configuration hoặc bean conditions.

Một runner có thể cấu hình:

- User configuration classes.
- Property values.
- Active profiles.
- Classpath filters.
- Context customizers phù hợp.

Ví dụ với profile:

```java
new ApplicationContextRunner()
        .withUserConfiguration(ProfiledGatewayConfiguration.class)
        .withInitializer(context ->
                context.getEnvironment()
                        .setActiveProfiles("sandbox"))
        .run(context -> {
            // Assertions
        });
```

Trong project thực tế, có thể dùng các customizer phù hợp phiên bản để kiểm soát environment. Hãy ưu tiên property/profile setup tường minh trong test.

### 10.1. AssertableApplicationContext

Trong callback của `run`, context có các tiện ích để kiểm tra:

```java
assertThat(context).hasNotFailed();
assertThat(context).hasBean("paymentGateway");
assertThat(context).hasSingleBean(PaymentGateway.class);
assertThat(context).doesNotHaveBean("legacyGateway");
```

Khi startup fail:

```java
assertThat(context).hasFailed();
assertThat(context.getStartupFailure()).isNotNull();
```

Bạn có thể kiểm tra exception chain bằng AssertJ:

```java
assertThat(context.getStartupFailure())
        .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class);
```

Dùng assertion theo nguyên nhân mà test đang bảo vệ. Nếu test chỉ quan tâm context không được khởi động, có thể assert `hasFailed()` và một thông điệp ổn định thay vì khóa chặt vào mọi wrapper exception.

### 10.2. Tại sao không dùng @SpringBootTest cho mọi negative case?

`@SpringBootTest` hữu ích khi muốn kiểm tra application context gần với cấu hình ứng dụng thật. Nhưng khi context không khởi động, failure có thể xảy ra trong test bootstrap trước khi JUnit vào test method.

`ApplicationContextRunner` giúp thử nhiều configuration nhỏ trong một test class và quan sát cả trường hợp thành công lẫn thất bại. Nó đặc biệt phù hợp cho conditional beans và auto-configuration.

Điều đó không có nghĩa thay thế mọi integration test. Một test runner nhỏ không chứng minh toàn bộ production application wiring.

## 11. Dùng @SpringBootTest cho smoke test ứng dụng hoàn chỉnh

Sau khi sửa lỗi cấu hình, vẫn nên có smoke test cho application context thật:

```java
@SpringBootTest
class ShopApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

Test này xác nhận ứng dụng có thể tạo context theo test configuration hiện tại.

Nếu muốn kiểm tra một bean cụ thể:

```java
@SpringBootTest
class CheckoutWiringTests {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void checkoutServiceIsAvailable() {
        assertThat(checkoutService).isNotNull();
    }
}
```

Tuy nhiên, test này không tự xác nhận payment gateway đang trỏ tới provider đúng hoặc HTTP request thực sự hoạt động. Cần adapter test riêng cho những contract đó.

### 11.1. Test profile

```java
@SpringBootTest
@ActiveProfiles("test")
class ShopApplicationTests {
    @Test
    void contextLoads() {
    }
}
```

Điều quan trọng là `application-test.yml` có thể khác production. Context xanh trong profile test không chứng minh profile production cũng bind đúng. Nếu production configuration có các nhánh condition quan trọng, hãy test chúng bằng property/profile scenarios riêng.

## 12. Tái hiện lỗi component scan

Đây là một dạng missing bean thường gặp trong ứng dụng thật.

Main application:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

Implementation nằm ở package không liên quan:

```java
package com.acme.gateway;

@Component
public class AcmePaymentGateway implements PaymentGateway {
    // ...
}
```

Nếu component scan chỉ bắt đầu từ `com.example.shop`, class `com.acme.gateway.AcmePaymentGateway` không được phát hiện.

### 12.1. Sửa component registration

```java
@Configuration(proxyBeanMethods = false)
@Import(AcmePaymentGateway.class)
class PaymentAdapterImportConfiguration {
}
```

Có thể dùng component scan, `@Import` hoặc `@Bean` tùy cách module được tổ chức. Nếu class có constructor dependency, test phải cung cấp dependencies đó.

### 12.2. Chọn component scan hay @Import?

- Dùng component scan khi package layout là một phần của component discovery bình thường.
- Dùng `@Import` khi muốn đăng ký một configuration/adapter có chủ đích.
- Dùng `@Bean` khi muốn kiểm soát construction hoặc cấu hình implementation.
- Dùng auto-configuration khi xây một module/library có điều kiện đăng ký bean.

Không nên thêm scan base package quá rộng chỉ để làm test xanh mà không hiểu class nào sẽ được phát hiện.

## 13. Tái hiện lỗi profile không active

Bean:

```java
@Component
@Profile("sandbox")
public class SandboxPaymentGateway implements PaymentGateway {
    // ...
}
```

Nếu profile `sandbox` không active, bean sẽ không tồn tại.

Test hai trường hợp:

```java
@Test
void sandboxGatewayIsMissingWithoutSandboxProfile() {
    new ApplicationContextRunner()
            .withUserConfiguration(SandboxGatewayConfiguration.class)
            .run(context -> {
                assertThat(context).doesNotHaveBean(PaymentGateway.class);
            });
}
```

Khi active profile:

```java
@Test
void sandboxGatewayExistsWhenProfileIsActive() {
    new ApplicationContextRunner()
            .withInitializer(context ->
                    context.getEnvironment()
                            .setActiveProfiles("sandbox"))
            .withUserConfiguration(SandboxGatewayConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(PaymentGateway.class);
            });
}
```

Ở đây `SandboxGatewayConfiguration` có thể đăng ký class bằng `@Import` hoặc `@Bean` để test không phụ thuộc component scan toàn ứng dụng.

### 13.1. Profile expression

Spring hỗ trợ biểu thức profile như `@Profile("production & cloud")` hoặc `@Profile("sandbox | local")`.

Một ký tự sai hoặc profile không active có thể khiến bean biến mất. Test các tổ hợp profile quan trọng thay vì chỉ test một profile mặc định.

## 14. Tái hiện lỗi do @ConditionalOnMissingBean

`@ConditionalOnMissingBean` thường được dùng trong auto-configuration để tạo default bean khi ứng dụng chưa cung cấp implementation riêng.

```java
@Configuration(proxyBeanMethods = false)
class DefaultPaymentConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway defaultPaymentGateway() {
        return new SandboxPaymentGateway();
    }
}
```

Test default bean xuất hiện:

```java
@Test
void createsDefaultGatewayWhenNoCustomGatewayExists() {
    new ApplicationContextRunner()
            .withUserConfiguration(DefaultPaymentConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(PaymentGateway.class);
                assertThat(context).hasBean("defaultPaymentGateway");
            });
}
```

Test custom bean thay thế default:

```java
@Test
void backsOffWhenCustomGatewayExists() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    DefaultPaymentConfiguration.class,
                    CustomPaymentConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(PaymentGateway.class);
                assertThat(context).hasBean("customPaymentGateway");
                assertThat(context).doesNotHaveBean("defaultPaymentGateway");
            });
}
```

Đây là behavior quan trọng của auto-configuration: default bean nên nhường chỗ cho user-defined bean theo condition đã công bố.

Điều kiện được đánh giá trong quá trình đăng ký bean definitions. Khi viết auto-configuration, cần theo các quy tắc ordering/condition của Spring Boot để user configuration có thể override đúng như thiết kế. Không nên giả định mọi thứ tự khai báo class đều quyết định thứ tự condition theo ý muốn.

## 15. Phân biệt các exception thường gặp

| Exception | Ý nghĩa | Hướng điều tra |
|---|---|---|
| `NoSuchBeanDefinitionException` | Không có bean phù hợp với type/name cần tìm | Registration, scan, profile, condition, import |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp và không có lựa chọn duy nhất | Qualifier, primary, injection point |
| `UnsatisfiedDependencyException` | Spring không resolve được dependency của bean | Đọc cause chain để tìm missing/ambiguous dependency |
| `BeanCreationException` | Tạo bean thất bại | Xem bean name và nested cause |
| `ConfigurationPropertiesBindException` | Bind configuration properties thất bại | Property name, type conversion, validation |
| `BindValidationException` | Giá trị đã bind nhưng không qua validation | Constraint và property value |

Exception ngoài cùng thường mô tả bean nào thất bại; exception sâu hơn giải thích vì sao.

## 16. Viết test cho nhiều loại lỗi mà không làm suite thất bại

Một test tái hiện lỗi nên **mong đợi lỗi** và assert đúng điều kiện. Nó không phải test bị đỏ vô tình.

```java
@Test
void missingDependencyIsReported() {
    new ApplicationContextRunner()
            .withUserConfiguration(CheckoutConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                                NoSuchBeanDefinitionException.class
                        );
            });
}
```

Nếu context thất bại vì một nguyên nhân khác, test phải fail. Đây là điều ta muốn: test không chỉ kiểm tra “có lỗi”, mà kiểm tra **đúng lỗi**.

### 16.1. Đừng assert toàn bộ stack trace

Stack trace có thể thay đổi theo phiên bản Spring/Boot, JDK và bean processing. Tránh snapshot toàn bộ stack trace nếu không thật sự cần.

Ưu tiên kiểm tra:

- Context có fail hay không.
- Root cause type.
- Bean/type/property liên quan.
- Một thông báo ổn định đủ xác định lỗi.

### 16.2. Negative test và positive test đi cùng nhau

Với mỗi lỗi:

1. Viết test tái hiện cấu hình sai.
2. Viết test cấu hình đúng.
3. Xác nhận context khởi động.
4. Assert bean hoặc property đã chọn.
5. Giữ cả hai test để bảo vệ failure mode và fix.

Negative test chứng minh lỗi được phát hiện; positive test chứng minh cách sửa tạo ra trạng thái đúng.

## 17. Dùng ConditionEvaluationReport khi auto-configuration không chạy

Khi một bean được tạo bởi Spring Boot auto-configuration nhưng không xuất hiện, nguyên nhân có thể là một condition không match.

Spring Boot có `ConditionEvaluationReport` để ghi lại các điều kiện auto-configuration đã match hoặc không match.

Có thể bật debug condition report khi chạy ứng dụng:

```properties
debug=true
```

Startup output có thể cho biết:

- Auto-configuration nào match.
- Auto-configuration nào bị loại.
- Property/class/bean condition nào không thỏa.
- Vì sao một configuration không được áp dụng.

### 17.1. Đừng đoán condition từ tên class

Một auto-configuration có thể cần class dependency trên classpath, property có giá trị cụ thể, chưa tồn tại bean do user cung cấp hoặc một loại web application context phù hợp.

Hãy đọc condition report để biết điều kiện nào không thỏa. Sau đó viết test tái hiện đúng điều kiện đó bằng `ApplicationContextRunner`.

### 17.2. ApplicationContextRunner và auto-configuration

Khi viết test cho auto-configuration, có thể dùng `AutoConfigurations.of(...)` cùng `ApplicationContextRunner` theo Spring Boot version.

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                PaymentAutoConfiguration.class
                        )
                );
```

API và package cụ thể cần khớp phiên bản Boot của project. Test nên xác nhận cả trường hợp condition match và không match.

## 18. Một ví dụ tổng hợp: ba lỗi liên tiếp

Giả sử checkout module có các yêu cầu:

- Phải có một `PaymentGateway`.
- Nếu có nhiều gateway, checkout cần chọn rõ một gateway.
- `checkout.max-attempts` phải là số nguyên dương.
- `checkout.base-url` phải không rỗng.

Có thể tổ chức test theo bảng:

| Test | Cấu hình đầu vào | Kết quả mong đợi |
|---|---|---|
| Missing gateway | Không đăng ký PaymentGateway | Context fail với missing bean |
| Duplicate gateway | Đăng ký card và bank, không qualifier/primary | Context fail vì ambiguity |
| Primary gateway | Hai bean, một bean primary | Context pass và chọn primary |
| Qualified gateway | Hai bean, injection có qualifier | Context pass và chọn đúng bean |
| Invalid attempts | max-attempts = 0 | Context fail validation |
| Wrong type | max-attempts = many | Context fail conversion |
| Missing conditional bean | Sai property prefix | Context fail missing dependency |
| Correct configuration | Properties hợp lệ và một gateway rõ ràng | Context pass |

Đây là một bộ regression tests nhỏ nhưng bảo vệ nhiều failure modes quan trọng.

## 19. Khi nào dùng @MockBean/@MockitoBean trong context test?

Nếu muốn test service wiring mà không gọi external integration, có thể thay port bằng mock bean.

Ở Spring Boot 3.4+/Spring Framework 6.2+, dùng `@MockitoBean`:

```java
@SpringBootTest
class CheckoutWiringTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void serviceCanBeCreatedWithMockGateway() {
        given(paymentGateway.name()).willReturn("test");

        assertThat(checkoutService.selectedGateway())
                .isEqualTo("test");
    }
}
```

Với các phiên bản Boot cũ hơn, project có thể dùng `@MockBean` của Spring Boot Test. API này đã được deprecate ở dòng Boot mới để chuyển sang bean override support của Spring Framework; hãy dùng annotation tương thích version.

### 19.1. Mock bean có thể che lỗi registration

Nếu test luôn mock `PaymentGateway`, nó có thể pass ngay cả khi production adapter thật chưa được scan hoặc cấu hình condition sai.

Vì vậy, cần có test riêng kiểm tra production wiring/adapter registration khi đó là rủi ro cần bảo vệ. Mock context test chỉ chứng minh service hoạt động với mock được inject.

## 20. Cách đọc và chẩn đoán stack trace trong thực tế

Khi chạy ứng dụng và thấy lỗi startup, hãy đi theo thứ tự:

1. Tìm bean đầu tiên được báo không tạo được.
2. Đọc dependency chain của bean đó.
3. Tìm exception cuối cùng trong chuỗi `Caused by`.
4. Nếu missing bean, tìm nơi bean đáng lẽ được đăng ký.
5. Nếu ambiguous, liệt kê candidate beans và quyết định qualifier/primary.
6. Nếu binding error, đọc property path, giá trị thực tế và Java target type.
7. Nếu condition không match, bật condition report.
8. Viết một context runner nhỏ tái hiện cấu hình gây lỗi.
9. Sửa cấu hình/registration.
10. Thêm positive assertion để xác nhận bean hoặc property đúng.

Ví dụ log:

```text
APPLICATION FAILED TO START

Parameter 0 of method checkoutService required a bean
of type 'PaymentGateway' that could not be found.

Action:
Consider defining a bean of type 'PaymentGateway'
in your configuration.
```

Câu action gợi ý là hướng điều tra, không phải luôn là toàn bộ giải pháp. Trước khi thêm bean, xác nhận có phải implementation bị thiếu do profile, condition, package scan hoặc test slice hay không.

## 21. Những lỗi khi viết test tái hiện

### 21.1. Test mong context fail nhưng lại không assert nguyên nhân

Không nên:

```java
contextRunner.run(context -> {
    assertThat(context).hasFailed();
});
```

Nếu test được thiết kế để bảo vệ missing bean, nó nên xác nhận root cause là `NoSuchBeanDefinitionException` hoặc kiểm tra type/bean cụ thể. Nếu context fail vì lỗi khác, test đơn giản trên vẫn xanh giả.

### 21.2. Dùng @SpringBootTest cho mọi tổ hợp property

Một ứng dụng lớn có thể mất nhiều thời gian bootstrap. Dùng `ApplicationContextRunner` cho những configuration nhỏ và lặp nhiều tổ hợp; dành `@SpringBootTest` cho integration tests cần toàn bộ application context.

### 21.3. Tạo mock bean nhưng không kiểm tra bean thật

Mock bean có thể thay thế implementation thật. Nếu mục tiêu là xác nhận production adapter được đăng ký, không dùng mock làm bằng chứng duy nhất.

### 21.4. Chỉ sửa để context xanh

Một context có thể khởi động nhưng chọn nhầm payment gateway. Sau khi thêm `@Primary`, hãy assert `selectedGateway()` đúng với yêu cầu.

### 21.5. Dùng profile test che cấu hình production

Test profile có thể cung cấp fake bean trong khi production profile thiếu adapter. Test profile xanh không chứng minh production profile có wiring đúng. Viết test cho các profile/conditions quan trọng.

### 21.6. Assert exception message quá chi tiết

Thông điệp có thể thay đổi theo version. Assert root cause type và property/bean liên quan thay vì toàn bộ stack trace.

## 22. Quy trình thực hành từ lỗi tới regression test

Với mỗi lỗi cấu hình, làm theo vòng lặp:

```text
Tạo lỗi có chủ đích
        │
        ▼
Viết test tái hiện
        │
        ▼
Xác nhận test fail đúng nguyên nhân
        │
        ▼
Sửa bean/configuration
        │
        ▼
Viết hoặc cập nhật positive test
        │
        ▼
Xác nhận context và dependency đúng
        │
        ▼
Giữ test làm regression protection
```

### 22.1. Ghi rõ giả định trong test

Tên test nên mô tả trạng thái cấu hình và behavior mong đợi:

- `contextFailsWhenPaymentGatewayBeanIsMissing`.
- `contextFailsWhenMultipleGatewaysAreAmbiguous`.
- `primaryGatewayIsSelectedForUnqualifiedInjection`.
- `qualifierSelectsBankTransferGateway`.
- `contextFailsWhenMaxAttemptsIsZero`.
- `conditionalGatewayIsCreatedWhenPropertyIsEnabled`.

Khi test fail trong CI, người đọc biết ngay contract nào bị phá vỡ.

### 22.2. Tách test configuration khỏi production configuration

Test fixture nên được đặt trong test source set. Đừng vô tình đưa fake gateway vào `src/main` chỉ để làm test pass, trừ khi đó thực sự là adapter được thiết kế cho runtime.

Nếu production cần một default implementation, hãy cấu hình rõ ràng và dùng condition phù hợp; test cần kiểm tra cả default và custom override.

## 23. Bài thực hành

### Bài 1 — Missing bean cơ bản

Tạo `CheckoutService` cần `PaymentGateway` nhưng không đăng ký implementation. Viết `ApplicationContextRunner` test xác nhận context fail và root cause là `NoSuchBeanDefinitionException`.

### Bài 2 — Sửa missing bean

Đăng ký `SandboxPaymentGateway` bằng `@Bean`. Viết positive test xác nhận context pass và service nhận đúng implementation.

### Bài 3 — Component scan sai package

Đặt implementation ngoài package root của `@SpringBootApplication`. Tạo test tái hiện bean không được scan. Sửa bằng package layout hoặc `@Import` và kiểm tra bean xuất hiện.

### Bài 4 — Profile không active

Gắn `@Profile("sandbox")` cho gateway. Viết test khi profile chưa active và khi profile active. Xác nhận sự khác nhau trong bean registry.

### Bài 5 — Conditional property sai prefix

Dùng `@ConditionalOnProperty` cho notification sender. Cố tình viết property sai prefix, tái hiện missing dependency, rồi sửa property và viết test positive.

### Bài 6 — Duplicate bean

Đăng ký card và bank gateway cùng type. Viết test xác nhận context fail vì `NoUniqueBeanDefinitionException`.

### Bài 7 — @Primary

Đánh dấu card gateway là primary. Viết test xác nhận cả hai bean tồn tại và checkout service chọn card gateway.

### Bài 8 — @Qualifier

Bỏ primary, dùng qualifier để service chuyển khoản chọn bank gateway. Viết test xác nhận implementation được inject chính xác.

### Bài 9 — ConfigurationProperties validation

Tạo properties có `@Min` và `@NotBlank`. Test giá trị hợp lệ, giá trị 0 và chuỗi rỗng. Xác nhận lỗi validation được phát hiện khi context khởi động.

### Bài 10 — Sai kiểu property

Truyền chuỗi không phải số vào property integer. Viết test xác nhận binding thất bại và thông báo chỉ ra property path.

### Bài 11 — Property bị thiếu

Bỏ một property bắt buộc. Thiết kế validation hoặc constructor contract để startup fail với thông báo rõ. So sánh với property có default value.

### Bài 12 — ConditionalOnMissingBean

Viết default gateway auto-configuration. Test default bean được tạo khi không có user bean và tự back off khi custom gateway xuất hiện.

### Bài 13 — Test profile che lỗi production

Tạo fake gateway chỉ có trong profile test, còn production gateway có condition sai. Viết test riêng cho từng profile và quan sát context nào fail.

### Bài 14 — Context runner nhiều properties

Tạo một test class với runner chung và nhiều scenario property. Xác nhận mỗi scenario có context độc lập và assertions phù hợp.

### Bài 15 — Context failure cause chain

Tạo hai lỗi khác nhau trong cùng dependency graph. Quan sát wrapper exceptions và root causes. Viết assertions chỉ phụ thuộc vào phần ổn định của failure.

### Bài 16 — Condition evaluation

Tạo một auto-configuration có class/property/missing-bean conditions. Dùng condition report để tìm điều kiện không match, rồi viết context runner test cho từng trường hợp.

### Bài 17 — Mock bean và production adapter

Dùng `@MockitoBean` hoặc `@MockBean` theo version để test service. Sau đó viết một test khác xác nhận adapter production được đăng ký khi profile tương ứng active.

### Bài 18 — Tổng hợp

Tạo checkout application có hai gateway, properties validation và conditional notification sender. Cố tình đưa vào một missing bean, một ambiguous injection và một invalid property. Viết ba negative tests, sửa từng lỗi và bổ sung positive tests bảo vệ cấu hình cuối cùng.

## 24. Tài liệu tham khảo chính thức

- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): các công cụ kiểm thử Spring Boot và test context.
- [Spring Boot Reference — Developing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): phát triển và kiểm thử auto-configuration.
- [Spring Boot API — ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): dựng context nhỏ và kiểm tra kết quả startup.
- [Spring Boot API — AssertableApplicationContext](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/assertj/AssertableApplicationContext.html): truy cập startup failure và context assertions.
- [Spring Framework Reference — Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): dependency injection, candidate resolution, qualifier và primary.
- [Spring Framework Reference — @Primary](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html): chọn bean ưu tiên khi có nhiều candidates.
- [Spring Framework Reference — Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html): lọc bean candidates theo qualifier.
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, binding và cấu hình theo môi trường.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties` và type-safe binding.
- [Jakarta Bean Validation](https://beanvalidation.org/): constraint annotations như `@Min` và `@NotBlank`.

**Điều cần nhớ:** missing bean là không có candidate phù hợp; duplicate bean là có nhiều candidate nhưng injection point chưa chỉ rõ lựa chọn; cấu hình sai có thể làm binding/validation thất bại hoặc khiến conditional bean không được đăng ký. Hãy tạo lỗi có kiểm soát bằng context configuration nhỏ, dùng `ApplicationContextRunner` để assert cả startup failure lẫn root cause, rồi thêm positive test xác nhận bean/property được chọn đúng sau khi sửa. Khi đó stack trace dài trở thành một regression test cụ thể, dễ hiểu và có thể chạy lại mỗi lần cấu hình thay đổi.
