# Tạo nhiều implementation rồi chọn bằng @Qualifier hoặc @Primary

Trong ứng dụng Spring Boot, một interface có thể có nhiều implementation hợp lệ. Ví dụ, hệ thống thanh toán hỗ trợ Stripe, chuyển khoản ngân hàng và một gateway giả lập. Cả ba cùng thực hiện contract `PaymentGateway`, nhưng từng use case có thể cần một implementation khác nhau.

Khi Spring inject dependency theo type, container phải xác định bean phù hợp. Nếu chỉ có một candidate, việc lựa chọn đơn giản. Nếu có nhiều bean cùng type, Spring có thể báo `NoUniqueBeanDefinitionException`. Hai công cụ thường dùng để giải quyết tình huống này là:

- `@Primary`: đánh dấu một bean là lựa chọn ưu tiên khi injection point cần một candidate duy nhất.
- `@Qualifier`: thu hẹp tập bean candidate theo nhãn cụ thể tại injection point.

Bài học trình bày cách đăng ký nhiều implementation, lựa chọn bằng `@Primary` và `@Qualifier`, inject collection, chọn strategy theo dữ liệu runtime, tạo custom qualifier annotation, kiểm thử context và xử lý lỗi thường gặp.

## 1. Vì sao một interface có nhiều implementation?

Interface mô tả contract chung, còn implementation quyết định cách thực hiện contract.

~~~java
package com.example.payment;

import java.math.BigDecimal;

public interface PaymentGateway {
    PaymentResult charge(String orderId, BigDecimal amount);
}
~~~

Kết quả:

~~~java
package com.example.payment;

public record PaymentResult(
        String transactionId,
        String provider
) {
}
~~~

Các implementation có thể là:

- `StripePaymentGateway`: gọi dịch vụ thanh toán Stripe.
- `BankTransferPaymentGateway`: tạo yêu cầu chuyển khoản.
- `SandboxPaymentGateway`: giả lập thanh toán trong môi trường phát triển.

Cả ba đáp ứng `PaymentGateway`, nhưng không thể thay thế nhau trong mọi tình huống.

### 1.1. Lợi ích của interface

Application service phụ thuộc contract:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentResult checkout(String orderId, BigDecimal amount) {
        return gateway.charge(orderId, amount);
    }
}
~~~

Service không cần biết request được gửi tới provider nào. Việc thay implementation, tạo fake hoặc mock trở nên dễ dàng.

### 1.2. Nhiều implementation không phải lúc nào cũng là lỗi

Nhiều bean cùng type là hợp lệ. Vấn đề chỉ xuất hiện khi một injection point cần một bean duy nhất mà container không có đủ thông tin lựa chọn.

Nếu consumer cần tất cả gateway, inject `List<PaymentGateway>` hoặc `Map<String, PaymentGateway>`. Nếu chỉ cần một gateway, phải xác định quy tắc chọn.

## 2. Đăng ký nhiều implementation

Có thể dùng component scanning:

~~~java
@Component
public class StripePaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, BigDecimal amount) {
        // Gọi Stripe API trong implementation thực tế.
        return new PaymentResult("stripe-123", "stripe");
    }
}
~~~

~~~java
@Component
public class BankTransferPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, BigDecimal amount) {
        // Tạo yêu cầu chuyển khoản trong implementation thực tế.
        return new PaymentResult("bank-456", "bank-transfer");
    }
}
~~~

Khi component scan bao phủ package, Spring đăng ký cả hai bean.

### 2.1. Tên bean mặc định

Tên bean mặc định thường được suy ra từ tên class theo dạng lower camel case:

| Class | Bean name mặc định |
| --- | --- |
| `StripePaymentGateway` | `stripePaymentGateway` |
| `BankTransferPaymentGateway` | `bankTransferPaymentGateway` |

Có thể đặt tên rõ ràng:

~~~java
@Component("stripeGateway")
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

`@Component` và `@Service` đều là stereotype annotations được component scan nhận diện. Dùng annotation phù hợp với vai trò class và quy ước dự án.

## 3. Vì sao xảy ra NoUniqueBeanDefinitionException?

Nếu Spring tìm thấy hai bean cùng implement `PaymentGateway`, constructor sau có hai candidate:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Thông báo có thể tương tự:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentGateway'
available: expected single matching bean but found 2:
stripePaymentGateway, bankTransferPaymentGateway
~~~

Exception này có thể được bọc trong `UnsatisfiedDependencyException` hoặc `BeanCreationException` khi Spring tạo service.

### 3.1. Vì sao Spring không tự chọn bean đầu tiên?

Thứ tự component scan hoặc thứ tự class trên classpath không phải business rule đáng tin cậy. Nếu container âm thầm chọn bean đầu tiên, kết quả có thể thay đổi khi thêm dependency hoặc thay đổi cấu trúc package.

Spring yêu cầu lựa chọn rõ ràng để tránh hành vi ngẫu nhiên.

### 3.2. Chọn đúng công cụ

- Có một implementation mặc định cho consumer thông thường: dùng `@Primary`.
- Consumer cần implementation cụ thể: dùng `@Qualifier`.
- Consumer cần tất cả implementation: inject collection.
- Lựa chọn phụ thuộc dữ liệu runtime: dùng registry/factory.

## 4. Dùng @Primary để đặt implementation mặc định

Đánh dấu một component:

~~~java
@Component
@Primary
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Khi có nhiều bean `PaymentGateway` và injection point cần một bean duy nhất, Spring ưu tiên bean có `@Primary`.

Service giữ constructor đơn giản:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

### 4.1. @Primary diễn đạt default của ứng dụng

Dùng `@Primary` khi một implementation thực sự là lựa chọn mặc định trong context. Ví dụ, phần lớn checkout dùng Stripe, còn bank transfer được sử dụng ở một số flow đặc biệt.

### 4.2. Đặt @Primary trên @Bean method

Nếu bean được tạo bằng Java configuration:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway stripeGateway(StripeClient client) {
        return new StripePaymentGateway(client);
    }

    @Bean
    PaymentGateway bankTransferGateway(BankTransferClient client) {
        return new BankTransferPaymentGateway(client);
    }
}
~~~

Tên method thường là bean name mặc định nếu không chỉ định tên khác.

### 4.3. @Primary không xóa các bean khác

Cả Stripe và bank transfer vẫn được đăng ký. `@Primary` chỉ ảnh hưởng quá trình chọn một candidate cho injection point phù hợp. Bạn vẫn có thể inject cả hai bằng collection hoặc chọn cụ thể bằng qualifier.

### 4.4. Không đánh dấu nhiều primary cùng type

Nếu nhiều bean cùng type đều là primary candidate, Spring vẫn không có lựa chọn duy nhất. Khi mỗi consumer cần implementation riêng, hãy dùng qualifier thay vì tạo nhiều default.

## 5. Dùng @Qualifier để chọn implementation cụ thể

Đánh dấu bean:

~~~java
@Component
@Qualifier("stripe")
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Qualifier("bankTransfer")
public class BankTransferPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Inject đúng bean:

~~~java
@Service
public class InternationalCheckoutService {

    private final PaymentGateway gateway;

    public InternationalCheckoutService(
            @Qualifier("stripe") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

~~~java
@Service
public class DomesticCheckoutService {

    private final PaymentGateway gateway;

    public DomesticCheckoutService(
            @Qualifier("bankTransfer") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Mỗi consumer thể hiện rõ dependency mà nó cần.

### 5.1. Qualifier phải được dùng tại injection point

Chỉ gắn qualifier trên bean mà không chỉ định qualifier tương ứng ở consumer chưa chắc giải quyết được ambiguity. Constructor parameter là nơi thể hiện lựa chọn:

~~~java
public DomesticCheckoutService(
        @Qualifier("bankTransfer") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

### 5.2. Qualifier value không bắt buộc là bean name

Qualifier là metadata dùng để lọc candidate. Ví dụ bean name có thể là `stripePaymentGateway` nhưng qualifier là `stripe`. Điều này giúp đổi tên class mà không phải thay mọi consumer.

Tên bean đôi khi cũng được dùng làm qualifier fallback, nhưng nếu nhãn là một phần của contract lựa chọn, nên khai báo qualifier rõ ràng.

### 5.3. Một bean có thể có nhiều qualifier

Một bean có thể được phân loại theo nhiều chiều. Khi injection point khai báo nhiều qualifier, candidate cần đáp ứng các metadata tương ứng. Chỉ tạo nhãn thực sự giúp lựa chọn rõ hơn.

## 6. So sánh @Primary và @Qualifier

| Tiêu chí | `@Primary` | `@Qualifier` |
| --- | --- | --- |
| Mục đích | Chỉ định candidate mặc định | Chỉ định candidate theo nhãn |
| Đặt ở đâu | Bean definition/component | Bean và/hoặc injection point |
| Ảnh hưởng | Ưu tiên khi cần một candidate | Thu hẹp tập candidate |
| Phù hợp | Có một default chung | Consumer cần implementation cụ thể |
| Khi thêm implementation | Default vẫn được ưu tiên nếu chỉ có một primary | Consumer đã gắn qualifier tiếp tục chọn theo nhãn |
| Có loại bỏ bean khác không? | Không | Không |
| Dùng với collection | Không loại bean khác khỏi collection | Có thể lọc collection theo qualifier |

### 6.1. Có thể kết hợp hai annotation không?

Có. `@Qualifier` thu hẹp candidate theo metadata; `@Primary` có thể giúp chọn một bean ưu tiên trong tập candidate còn lại khi vẫn có nhiều lựa chọn.

Nếu qualifier đã xác định duy nhất một bean, `@Primary` thường không cần thiết tại injection point đó.

### 6.2. Quy tắc lựa chọn

- “Default của ứng dụng là gateway nào?” → `@Primary`.
- “Consumer này cần gateway nào?” → `@Qualifier`.

Đừng tạo primary chỉ để làm context hết lỗi. Hãy quyết định theo business configuration.

## 7. Dùng @Qualifier với @Bean methods

Có thể gắn qualifier vào factory method:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentGatewayConfiguration {

    @Bean
    @Qualifier("stripe")
    PaymentGateway stripeGateway(StripeClient client) {
        return new StripePaymentGateway(client);
    }

    @Bean
    @Qualifier("bankTransfer")
    PaymentGateway bankTransferGateway(BankTransferClient client) {
        return new BankTransferPaymentGateway(client);
    }
}
~~~

Consumer:

~~~java
@Service
public class BankCheckoutService {

    private final PaymentGateway gateway;

    public BankCheckoutService(
            @Qualifier("bankTransfer") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Có thể đặt tên bean và qualifier khác nhau:

~~~java
@Bean("stripeGateway")
@Qualifier("cardPayment")
PaymentGateway stripeGateway(StripeClient client) {
    return new StripePaymentGateway(client);
}
~~~

Bean name là `stripeGateway`, qualifier là `cardPayment`. Consumer có thể yêu cầu qualifier `cardPayment`.

### 7.1. Tránh trùng bean names

Hai `@Bean` methods cùng khai báo một bean name có thể gây conflict hoặc phụ thuộc cấu hình bean overriding. Đặt tên riêng cho các implementation và dùng qualifier để lựa chọn.

Bean overriding không phải cơ chế thay thế hợp lý cho việc có nhiều candidate cùng type.

## 8. Nhiều bean nhưng mỗi consumer cần một capability khác nhau

Một ứng dụng có thể có InternationalCheckoutService cần Stripe, DomesticCheckoutService cần bank transfer, RefundService cần gateway hỗ trợ refund và ReconciliationService cần tất cả gateway.

Nếu không phải mọi gateway đều hỗ trợ refund, hãy cân nhắc contract riêng:

~~~java
public interface RefundGateway {
    RefundResult refund(String transactionId, BigDecimal amount);
}
~~~

Đừng lạm dụng qualifier để che một interface quá rộng. Nếu một implementation phải ném `UnsupportedOperationException` cho nhiều method, contract có thể cần tách theo capability.

Qualifier giải quyết lựa chọn bean, không làm hai implementation có behavior tương đương.

## 9. Inject tất cả implementation bằng List

Nếu consumer cần tất cả gateway, inject collection:

~~~java
@Service
public class PaymentGatewayRegistry {

    private final List<PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public List<PaymentGateway> all() {
        return gateways;
    }
}
~~~

Spring có thể resolve tất cả bean phù hợp type `PaymentGateway` và inject thành list.

### 9.1. @Primary không loại bean khỏi List

Nếu Stripe được đánh dấu `@Primary`, collection vẫn có thể chứa Stripe và bank transfer. `@Primary` áp dụng khi chọn một candidate duy nhất, không phải filter để loại các bean còn lại khỏi collection.

### 9.2. Sắp xếp collection bằng @Order

Nếu thứ tự có ý nghĩa, có thể dùng `@Order` hoặc `Ordered`:

~~~java
@Component
@Order(10)
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Order(20)
public class BankTransferPaymentGateway implements PaymentGateway {
    // ...
}
~~~

`@Order` ảnh hưởng thứ tự trong một số collection injection/ordered streams; nó không thay thế `@Primary` để chọn một bean cho scalar injection.

## 10. Inject Map để tạo registry theo tên

Spring có thể inject map với bean name làm key:

~~~java
@Service
public class PaymentGatewayRegistry {

    private final Map<String, PaymentGateway> gateways;

    public PaymentGatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = Map.copyOf(gateways);
    }

    public PaymentGateway byBeanName(String name) {
        PaymentGateway gateway = gateways.get(name);

        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unknown payment gateway: " + name
            );
        }

        return gateway;
    }
}
~~~

Map có thể chứa keys `stripePaymentGateway` và `bankTransferPaymentGateway` nếu đó là bean names thực tế.

### 10.1. Không nhận bean name tùy ý từ request

Bean names là chi tiết wiring nội bộ, không phải public API của hệ thống. Không nên để client HTTP gửi tên Spring bean rồi gọi thẳng `Map.get(name)`.

Hãy ánh xạ enum/domain key ổn định như `CARD` hoặc `BANK_TRANSFER` sang implementation tương ứng, đồng thời validate quyền sử dụng provider.

## 11. Chọn implementation theo runtime input bằng Strategy Registry

Qualifier được resolve khi Spring tạo bean. Nếu lựa chọn phụ thuộc dữ liệu runtime như payment method, hãy dùng registry/factory.

Enum:

~~~java
public enum PaymentMethod {
    CARD,
    BANK_TRANSFER
}
~~~

Strategy:

~~~java
public interface PaymentProcessor {

    PaymentMethod method();

    PaymentResult process(
            String orderId,
            BigDecimal amount
    );
}
~~~

Registry:

~~~java
@Component
public class PaymentProcessorRegistry {

    private final Map<PaymentMethod, PaymentProcessor> processors;

    public PaymentProcessorRegistry(List<PaymentProcessor> processorList) {
        EnumMap<PaymentMethod, PaymentProcessor> map =
                new EnumMap<>(PaymentMethod.class);

        for (PaymentProcessor processor : processorList) {
            PaymentProcessor previous =
                    map.put(processor.method(), processor);

            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate processor for " + processor.method()
                );
            }
        }

        this.processors = Map.copyOf(map);
    }

    public PaymentProcessor get(PaymentMethod method) {
        PaymentProcessor processor = processors.get(method);

        if (processor == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment method: " + method
            );
        }

        return processor;
    }
}
~~~

Use case:

~~~java
@Service
public class PaymentApplicationService {

    private final PaymentProcessorRegistry registry;

    public PaymentApplicationService(PaymentProcessorRegistry registry) {
        this.registry = registry;
    }

    public PaymentResult pay(
            PaymentMethod method,
            String orderId,
            BigDecimal amount) {
        return registry.get(method).process(orderId, amount);
    }
}
~~~

### 11.1. Vì sao registry phù hợp hơn qualifier?

Registry chọn strategy khi method được gọi, dựa trên dữ liệu runtime. Nếu hai strategy cùng khai báo `CARD`, registry có thể phát hiện duplicate rõ ràng thay vì phụ thuộc thứ tự list.

### 11.2. Registry không phải service locator toàn cục

Registry vẫn là dependency tường minh được inject qua constructor. Nó quản lý tập strategy thuộc một contract cụ thể, không cung cấp quyền truy cập tùy ý tới mọi bean trong ApplicationContext.

## 12. Custom qualifier annotation

Khi qualifier string lặp lại nhiều nơi, có thể tạo annotation riêng với `@Qualifier` meta-annotation.

~~~java
package com.example.payment;

import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import org.springframework.beans.factory.annotation.Qualifier;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.PARAMETER;
import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target({FIELD, PARAMETER, METHOD, TYPE})
@Retention(RUNTIME)
@Documented
@Qualifier
public @interface CardPayment {
}
~~~

Đánh dấu bean:

~~~java
@Component
@CardPayment
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Inject:

~~~java
@Service
public class CardCheckoutService {

    private final PaymentGateway gateway;

    public CardCheckoutService(@CardPayment PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

### 12.1. Qualifier annotation có attribute

~~~java
@Target({FIELD, PARAMETER, METHOD, TYPE})
@Retention(RUNTIME)
@Qualifier
public @interface RegionalGateway {
    String value();
}
~~~

Đánh dấu bean và inject theo vùng:

~~~java
@Component
@RegionalGateway("asia")
public class AsiaPaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
public AsiaCheckoutService(
        @RegionalGateway("asia") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom annotation hữu ích khi nhãn là vocabulary domain được dùng nhiều nơi. Với một lựa chọn đơn lẻ, `@Qualifier("stripe")` thường dễ hiểu hơn.

## 13. Generic type cũng có thể tham gia chọn bean

Spring có thể dùng generic type information trong quá trình autowiring:

~~~java
public interface MessageEncoder<T> {
    byte[] encode(T message);
}
~~~

~~~java
@Component
public class JsonOrderEncoder implements MessageEncoder<OrderMessage> {
    // ...
}
~~~

~~~java
@Component
public class JsonInvoiceEncoder implements MessageEncoder<InvoiceMessage> {
    // ...
}
~~~

Consumer có thể inject `MessageEncoder<OrderMessage>` để thể hiện type cụ thể.

Nếu có nhiều bean cùng implement `MessageEncoder<OrderMessage>`, Spring vẫn có thể cần qualifier hoặc primary. Dùng generic khi khác biệt nằm ở type contract; dùng qualifier/strategy khi khác biệt nằm ở provider, region hoặc behavior.

## 14. @Primary không phải thứ tự ưu tiên trong List

Một bean được đánh dấu `@Primary` không làm cho `List<PaymentGateway>` chỉ chứa bean đó. Collection injection có mục đích lấy nhiều candidate.

Nếu cần một default, inject một `PaymentGateway`. Nếu cần tất cả, inject collection. Nếu cần một tập con, có thể dùng qualifier trên collection:

~~~java
public PaymentAuditService(
        @Qualifier("auditable") List<PaymentGateway> gateways) {
    this.gateways = gateways;
}
~~~

Những bean được đánh dấu qualifier `auditable` có thể được chọn cho collection này.

`@Order` sắp xếp collection; `@Primary` ưu tiên một candidate cho injection đơn.

## 15. Optional dependency và ObjectProvider

Có trường hợp bean là optional, ví dụ adapter metrics chỉ được cài trong một số ứng dụng.

~~~java
@Component
public class PaymentMetricsBridge {

    private final ObjectProvider<PaymentMetrics> metricsProvider;

    public PaymentMetricsBridge(
            ObjectProvider<PaymentMetrics> metricsProvider) {
        this.metricsProvider = metricsProvider;
    }

    public void recordSuccess(String provider) {
        PaymentMetrics metrics = metricsProvider.getIfAvailable();

        if (metrics != null) {
            metrics.recordSuccess(provider);
        }
    }
}
~~~

`ObjectProvider` cho phép resolve dependency khi cần và xử lý trường hợp không có bean.

Nếu có nhiều optional beans, có thể dùng `orderedStream()` hoặc `stream()`. Nếu dependency là bắt buộc và phải có đúng một bean, constructor injection trực tiếp sẽ cho lỗi startup sớm và dễ hiểu hơn.

## 16. Chọn bean theo profile hoặc property condition

Có thể chỉ đăng ký implementation theo profile:

~~~java
@Component
@Profile("dev")
public class SandboxPaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Profile("prod")
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Profile phù hợp khi implementation phụ thuộc môi trường triển khai.

Spring Boot cũng có thể đăng ký bean theo property:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentGatewayConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "payment.gateway",
            name = "provider",
            havingValue = "stripe"
    )
    PaymentGateway stripeGateway(StripeClient client) {
        return new StripePaymentGateway(client);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "payment.gateway",
            name = "provider",
            havingValue = "bank"
    )
    PaymentGateway bankGateway(BankTransferClient client) {
        return new BankTransferPaymentGateway(client);
    }
}
~~~

Cấu hình:

~~~yaml
payment:
  gateway:
    provider: stripe
~~~

### 16.1. Condition và qualifier giải quyết hai vấn đề khác nhau

- Condition quyết định bean nào được đăng ký vào context.
- Qualifier quyết định bean nào được inject tại một injection point trong tập candidate đã đăng ký.
- Primary chọn default trong tập candidate phù hợp.

Nếu ứng dụng chỉ muốn đăng ký một provider theo cấu hình, condition có thể phù hợp hơn việc tạo tất cả implementation rồi chọn. Nếu nhiều implementation phải cùng tồn tại, không dùng một property condition toàn cục để loại bỏ chúng.

## 17. @Qualifier không chọn bean động theo request

Một constructor có `@Qualifier("stripe")` được resolve khi Spring tạo bean. Qualifier không thay đổi theo từng HTTP request.

Nếu request có field `paymentMethod`, Spring không thay constructor argument bằng qualifier tương ứng ở mỗi lần gọi method.

Dùng factory hoặc registry được inject tường minh. Application service lấy strategy theo domain key, rồi kiểm tra provider có được phép cho tenant, quốc gia, currency hoặc loại giao dịch đó không.

Không gọi `ApplicationContext.getBean()` trong controller để lấy bean theo tên request truyền vào. Cách đó giấu dependency và biến bean name thành API bên ngoài.

## 18. Lỗi thường gặp khi dùng @Primary và @Qualifier

### 18.1. NoUniqueBeanDefinitionException vẫn xuất hiện

**Nguyên nhân:** có nhiều candidate nhưng không có primary duy nhất hoặc qualifier không khớp.

**Cách xử lý:** kiểm tra bean names, qualifier metadata, profile và component scan. Đọc exception message để biết candidate names.

### 18.2. NoSuchBeanDefinitionException sau khi thêm @Qualifier

**Nguyên nhân:** qualifier không khớp bean; hoặc bean không được đăng ký vì component scan/profile/condition.

**Cách xử lý:** xác nhận bean có mặt trong context trước, sau đó kiểm tra nhãn qualifier.

### 18.3. Gắn @Primary nhưng vẫn có lỗi

**Nguyên nhân:** có nhiều primary candidates, bean không được scan, hoặc qualifier lọc ra tập không chứa primary bean.

**Cách xử lý:** kiểm tra candidate set tại đúng injection point. `@Primary` không thể làm bean không tồn tại xuất hiện.

### 18.4. Đặt @Qualifier sai vị trí

**Nguyên nhân:** chỉ gắn qualifier lên field không được Spring inject hoặc gắn metadata vào bean không được đăng ký.

**Cách xử lý:** đặt qualifier trên bean definition và injection point cần chọn. Với constructor injection, annotation nằm trên parameter tương ứng.

### 18.5. Dùng tên bean không ổn định

**Nguyên nhân:** consumer phụ thuộc tên mặc định suy ra từ class name; refactor đổi tên class làm lựa chọn không còn khớp.

**Cách xử lý:** dùng qualifier label hoặc bean name tường minh khi lựa chọn là một phần của contract.

### 18.6. Hai @Primary

**Nguyên nhân:** nhiều bean cùng type đều được đánh dấu primary.

**Cách xử lý:** chỉ đánh dấu một default trong candidate set hoặc yêu cầu consumer dùng qualifier.

### 18.7. Mong @Primary lọc List

**Nguyên nhân:** hiểu `@Primary` như bộ lọc collection.

**Cách xử lý:** collection injection lấy nhiều candidate; dùng qualifier/filter/registry khi muốn tập con.

### 18.8. Dùng @Order thay cho @Primary

**Nguyên nhân:** nhầm thứ tự với lựa chọn candidate duy nhất.

**Cách xử lý:** `@Order` sắp xếp collection; `@Primary` ưu tiên scalar dependency.

### 18.9. Dùng @Qualifier để giải quyết lựa chọn runtime

**Nguyên nhân:** qualifier được resolve lúc tạo bean, không phải khi request chạy.

**Cách xử lý:** dùng strategy registry hoặc factory nhận domain key.

### 18.10. Bean bị loại bởi profile/condition

**Nguyên nhân:** qualifier đúng nhưng bean không tồn tại trong context do profile không active hoặc property condition không khớp.

**Cách xử lý:** kiểm tra active profiles, property sources và condition evaluation.

## 19. Kiểm thử lựa chọn bean bằng Spring context

Unit test tạo object bằng `new` có thể kiểm tra business logic, nhưng không xác nhận Spring chọn bean theo `@Primary` hoặc `@Qualifier`.

Để kiểm tra container behavior, dùng Spring Test context hoặc `ApplicationContextRunner`.

### 19.1. Ví dụ cấu hình test nhỏ

~~~java
@Configuration(proxyBeanMethods = false)
static class TestConfiguration {

    @Bean
    @Primary
    PaymentGateway stripeGateway() {
        return (orderId, amount) ->
                new PaymentResult("stripe-test", "stripe");
    }

    @Bean
    @Qualifier("bank")
    PaymentGateway bankGateway() {
        return (orderId, amount) ->
                new PaymentResult("bank-test", "bank");
    }

    @Bean
    DefaultCheckout defaultCheckout(PaymentGateway gateway) {
        return new DefaultCheckout(gateway);
    }

    @Bean
    BankCheckout bankCheckout(
            @Qualifier("bank") PaymentGateway gateway) {
        return new BankCheckout(gateway);
    }
}
~~~

Test:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
class PaymentGatewaySelectionTest {

    @Autowired
    DefaultCheckout defaultCheckout;

    @Autowired
    BankCheckout bankCheckout;

    @Test
    void usesPrimaryForUnqualifiedInjection() {
        assertEquals("stripe", defaultCheckout.charge().provider());
    }

    @Test
    void usesQualifierForSpecificInjection() {
        assertEquals("bank", bankCheckout.charge().provider());
    }
}
~~~

`DefaultCheckout` và `BankCheckout` là class test đơn giản nhận `PaymentGateway` qua constructor. Context test chứng minh lựa chọn bean được Spring thực hiện.

### 19.2. Kiểm tra bean names và count

Có thể xác nhận cả hai implementation vẫn tồn tại:

~~~java
assertThat(context.getBeansOfType(PaymentGateway.class))
        .hasSize(2);
~~~

Sau đó kiểm tra bean lấy theo type trả primary candidate nếu có đúng một primary phù hợp.

### 19.3. Kiểm tra lỗi ambiguity có chủ đích

Một test khác có thể tạo context chỉ với hai bean không có primary và một consumer inject scalar `PaymentGateway`. Xác nhận context startup thất bại với lỗi ambiguity.

Negative test này hữu ích khi muốn bảo vệ behavior configuration, nhưng nên kiểm tra exception theo cách ổn định với Spring version đang dùng thay vì phụ thuộc toàn bộ message nội bộ.

## 20. Kiểm thử auto-configuration bằng ApplicationContextRunner

Nếu thư viện cung cấp auto-configuration, `ApplicationContextRunner` có thể kiểm tra bean selection trong context nhỏ.

~~~java
class PaymentAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PaymentAutoConfiguration.class);

    @Test
    void backsOffWhenUserProvidesPrimaryGateway() {
        runner.withUserConfiguration(UserPaymentConfiguration.class)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(PaymentGateway.class);
                });
    }
}
~~~

`UserPaymentConfiguration` là configuration test đăng ký implementation riêng. Test nên xác minh:

- Default bean có được tạo khi không có user bean không?
- User bean có làm default auto-configuration back off không?
- Nếu có nhiều user beans, injection point có qualifier/primary đúng không?
- Property/profile conditions có đăng ký đúng tập bean không?

### 20.1. @ConditionalOnMissingBean và nhiều implementation

Auto-configuration thường dùng `@ConditionalOnMissingBean(PaymentGateway.class)` để tạo một default khi chưa có bean nào cùng type.

Nếu ứng dụng muốn có nhiều gateway, auto-configuration cần thiết kế contract phù hợp: có thể tạo default khi chưa có user-defined gateway, còn user configuration tự đăng ký nhiều implementation; hoặc mỗi provider có condition riêng và qualifier riêng.

Không nên vô tình tạo default bean thứ ba rồi khiến scalar injection trở nên ambiguous.

## 21. Test có thể che cấu hình production

Nếu test configuration luôn đánh dấu một mock là `@Primary`, mọi test có thể pass dù production context có hai implementation thật và không có primary.

### 21.1. Unit test không xác minh bean selection

~~~java
CheckoutService service = new CheckoutService(mockGateway);
~~~

Test này xác minh service với dependency được truyền, không xác minh `@Primary` hay `@Qualifier`.

### 21.2. Context test xác minh container rules

Khi behavior phụ thuộc bean metadata, dùng context test có bean definitions tương ứng.

### 21.3. Integration test xác minh composition thật

Nếu ứng dụng có nhiều configuration modules, profile và auto-configuration, cần ít nhất một test ở phạm vi đại diện cho composition production để phát hiện xung đột.

## 22. Quy ước đặt tên và qualifier

Khi số implementation tăng, quy ước đặt tên giúp tránh nhầm lẫn:

| Provider | Bean name | Qualifier |
| --- | --- | --- |
| Stripe | `stripePaymentGateway` | `stripe` |
| Bank transfer | `bankTransferPaymentGateway` | `bankTransfer` |
| Sandbox | `sandboxPaymentGateway` | `sandbox` |

Nguyên tắc:

- Dùng tên theo vai trò/provider, không theo thứ tự đăng ký.
- Không tái sử dụng cùng qualifier cho hai bean nếu consumer kỳ vọng một bean duy nhất.
- Giữ qualifier ổn định khi đổi tên class.
- Đặt custom qualifier annotation khi nhãn trở thành vocabulary dùng chung.
- Tài liệu hóa implementation nào được dùng làm default.
- Nếu có nhiều context/profile, ghi rõ bean nào tồn tại trong từng context.

## 23. Khi nào dùng @Primary, @Qualifier, List, Map hay Registry?

| Nhu cầu thực tế | Cơ chế nên cân nhắc |
| --- | --- |
| Một default cho consumer thông thường | `@Primary` |
| Một consumer cần bean cụ thể | `@Qualifier` |
| Consumer cần tất cả implementation | `List<T>` hoặc `Collection<T>` |
| Consumer cần tra cứu theo bean key nội bộ | `Map<String, T>` |
| Chọn strategy theo enum/domain key runtime | Registry/factory |
| Chỉ đăng ký implementation theo môi trường | `@Profile` |
| Chỉ đăng ký theo property/classpath | Conditional bean |
| Nhiều capability khác nhau | Tách interface hoặc strategy có contract rõ |

Không có một annotation duy nhất giải quyết mọi bài toán. Hãy chọn cơ chế phản ánh đúng thời điểm và nguồn quyết định: startup configuration hay runtime business input.

## 24. Các nguyên tắc thiết kế quan trọng

1. **Constructor injection là mặc định tốt.** Dependency nhìn thấy rõ và dễ kiểm thử.
2. **Không dựa vào thứ tự component scan.** Thứ tự không phải business rule.
3. **Dùng `@Primary` cho default thực sự.** Đừng dùng chỉ để dập lỗi startup.
4. **Dùng `@Qualifier` cho lựa chọn có chủ đích.** Consumer thể hiện rõ implementation cần dùng.
5. **Tách contract theo capability.** Đừng ép interface quá rộng lên mọi implementation.
6. **Dùng registry cho runtime selection.** Qualifier được resolve khi Spring tạo bean.
7. **Định nghĩa naming convention ổn định.** Bean name/qualifier là một phần cấu hình nội bộ cần quản lý.
8. **Test container behavior bằng context.** Direct unit test không xác minh bean resolution.
9. **Quản lý profile và conditions rõ ràng.** Bean không tồn tại thì qualifier cũng không thể chọn.
10. **Không expose bean names thành API công khai.** Dùng enum/domain key cho request hoặc configuration bên ngoài.

## 25. Bài thực hành

### Bài A: Tạo hai implementation

Tạo `PaymentGateway`, `StripePaymentGateway` và `BankTransferPaymentGateway`. Đăng ký cả hai bằng component scanning. Inject `PaymentGateway` vào một service và quan sát lỗi ambiguity.

### Bài B: Dùng @Primary

Đánh dấu Stripe là `@Primary`. Khởi động context và xác nhận consumer không có qualifier nhận Stripe.

### Bài C: Dùng @Qualifier

Đánh dấu bank gateway bằng `@Qualifier("bankTransfer")`. Tạo service yêu cầu qualifier này và xác nhận nó nhận đúng implementation.

### Bài D: Đặt bean bằng @Bean

Tạo hai bean qua `@Configuration`. Dùng `@Primary` trên factory method và `@Qualifier` trên bean khác. Kiểm tra bean names mặc định từ method.

### Bài E: Kết hợp primary và qualifier

Tạo một default primary và một consumer có qualifier cụ thể. Xác nhận hai consumer nhận hai implementation khác nhau.

### Bài F: Inject List

Inject `List<PaymentGateway>`. Xác nhận collection có cả hai bean dù một bean là primary.

### Bài G: Inject Map

Inject `Map<String, PaymentGateway>`. Ghi nhận bean names và xây một registry nội bộ.

### Bài H: Strategy Registry

Tạo enum `PaymentMethod`, interface `PaymentProcessor` và registry theo method. Kiểm tra trường hợp thiếu strategy và duplicate strategy.

### Bài I: Custom qualifier annotation

Tạo `@CardPayment` hoặc `@PaymentRegion`. Dùng annotation trên bean và constructor parameter.

### Bài J: Conditional provider

Chỉ đăng ký Stripe khi `payment.gateway.provider=stripe`, bank khi giá trị là `bank`. Test cả hai property values bằng context runner.

### Bài K: Context test và unit test

Viết một unit test truyền fake gateway trực tiếp và một context test xác minh `@Primary`/`@Qualifier`. Giải thích mỗi test bảo vệ điều gì.

### Bài L: Chọn theo quyền sử dụng

Tạo registry nhận `PaymentMethod`, rồi thêm kiểm tra provider được phép theo tenant/currency. Không dùng bean name trực tiếp từ request.

## 26. Câu hỏi tự kiểm tra

**1. Vì sao Spring báo `NoUniqueBeanDefinitionException`?**

Vì injection point cần một bean duy nhất nhưng có nhiều candidate cùng phù hợp và không có quy tắc lựa chọn duy nhất.

**2. `@Primary` có làm bean khác biến mất không?**

Không. Nó chỉ đánh dấu candidate ưu tiên cho một số dạng injection đơn.

**3. `@Qualifier` dùng để làm gì?**

Thu hẹp candidate theo qualifier metadata để consumer nhận implementation phù hợp.

**4. Có thể đặt `@Primary` trên `@Bean` method không?**

Có. Annotation có thể đặt trên bean definition được tạo bởi factory method.

**5. Qualifier có bắt buộc phải trùng bean name không?**

Không. Qualifier là metadata riêng; bean name có thể được dùng trong một số tình huống fallback nhưng không phải cách duy nhất.

**6. Nếu hai bean cùng được đánh dấu `@Primary` thì sao?**

Spring vẫn có thể không xác định được một primary candidate duy nhất.

**7. `@Primary` có lọc `List<PaymentGateway>` không?**

Không. Collection injection vẫn có thể chứa tất cả candidate phù hợp.

**8. `@Order` khác `@Primary` thế nào?**

`@Order` liên quan thứ tự trong collection/ordered resolution; `@Primary` ưu tiên một candidate cho injection đơn.

**9. Qualifier có chọn implementation theo từng request không?**

Không. Qualifier được resolve khi Spring tạo bean. Runtime selection cần registry/factory hoặc strategy phù hợp.

**10. Khi nào nên dùng custom qualifier annotation?**

Khi nhãn qualifier là vocabulary có ý nghĩa, được dùng nhiều nơi và cần giảm chuỗi string lặp lại.

**11. Có nên dùng `ApplicationContext.getBean()` trong controller để chọn gateway không?**

Không nên. Dùng registry/factory được inject tường minh và domain key đã validate.

**12. Khi nào nên inject List thay vì một bean?**

Khi consumer thực sự cần xử lý tất cả implementation, ví dụ registry, aggregator hoặc chạy qua nhiều plugin.

**13. Nếu qualifier đúng nhưng bean không tồn tại thì sao?**

Spring vẫn không resolve được dependency. Kiểm tra component scan, profile, conditions và runtime classpath.

**14. Unit test tự tạo service có xác minh `@Primary` không?**

Không. Nó chỉ xác minh service với dependency được truyền trực tiếp; cần context test để kiểm tra bean resolution.

**15. Nên chọn cơ chế nào khi provider được chọn theo request?**

Dùng strategy registry/factory với enum hoặc domain key, có validation và kiểm soát quyền.

## 27. Kết luận

Khi một interface có nhiều implementation, Spring cần quy tắc lựa chọn rõ ràng tại mỗi injection point. `@Primary` phù hợp khi ứng dụng có một implementation mặc định; `@Qualifier` phù hợp khi consumer cần một implementation cụ thể. Hai cơ chế không xóa bean còn lại, và có thể kết hợp khi candidate set cần được thu hẹp rồi chọn ưu tiên.

Nếu consumer cần tất cả implementation, hãy inject collection. Nếu lựa chọn phụ thuộc dữ liệu runtime như payment method, hãy dùng registry hoặc factory với domain key thay vì cố dùng qualifier động. Nếu implementation chỉ tồn tại trong một môi trường, profile hoặc conditional bean registration có thể quyết định tập bean được tạo.

Hãy giữ constructor dependencies tường minh, không dựa vào thứ tự scan, đặt tên/qualifier ổn định và kiểm thử bean resolution bằng Spring context. Khi lựa chọn phản ánh đúng ý nghĩa của dependency, ứng dụng có thể thêm provider mới mà không làm những consumer hiện tại trở nên mơ hồ.

