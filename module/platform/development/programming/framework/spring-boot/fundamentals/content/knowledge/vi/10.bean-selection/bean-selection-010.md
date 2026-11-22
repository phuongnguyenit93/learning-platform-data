# Kiểm thử trường hợp không có ứng viên hoặc có nhiều ứng viên

Khi Spring tạo một bean, IoC container phải tìm các dependency cần thiết để truyền vào constructor, field hoặc factory method. Có hai tình huống thường làm việc chọn bean thất bại:

- **Không có ứng viên (no candidate):** context không có bean nào đáp ứng kiểu, qualifier, profile hoặc các điều kiện của injection point.
- **Có nhiều ứng viên (ambiguous candidates):** nhiều bean cùng phù hợp nhưng Spring không có đủ thông tin để chọn một bean duy nhất.

Hai tình huống này thường xuất hiện khi ứng dụng khởi động, lúc Spring tạo bean và resolve dependency. Chúng có thể khiến ApplicationContext không refresh thành công, do đó ứng dụng Spring Boot không khởi động được.

Muốn kiểm soát tốt việc chọn bean, cần hiểu exception tương ứng, cách Spring lựa chọn candidate, các cơ chế như **@Primary** và **@Qualifier**, và cách viết test tái hiện từng tình huống. Bài học này dùng ví dụ thống nhất về các cổng thanh toán để minh họa.

## 1. Bắt đầu từ một dependency đơn

Giả sử ứng dụng có interface:

~~~java
package com.example.payment;

public interface PaymentProvider {
    String name();

    void charge(long orderId);
}
~~~

Một service cần đúng một PaymentProvider:

~~~java
package com.example.payment;

public class CheckoutService {
    private final PaymentProvider provider;

    public CheckoutService(PaymentProvider provider) {
        this.provider = provider;
    }

    public void checkout(long orderId) {
        provider.charge(orderId);
    }

    public PaymentProvider provider() {
        return provider;
    }
}
~~~

Constructor injection diễn đạt rằng **CheckoutService không thể hoạt động nếu chưa có một PaymentProvider**. Khi Spring tạo bean CheckoutService, container phải tìm một bean có kiểu tương thích để truyền vào constructor.

~~~text
ApplicationContext
       │
       ▼
Tạo CheckoutService
       │
       ▼
Resolve PaymentProvider
       │
       ├── Không có candidate
       │       └── Không thể tạo CheckoutService
       │
       ├── Một candidate
       │       └── Inject bean đó
       │
       └── Nhiều candidate
               ├── Có quy tắc chọn rõ ràng
               │       └── Inject candidate được chọn
               └── Không có quy tắc phân biệt
                       └── Dependency bị mơ hồ
~~~

Đây là bài toán **resolve dependency đơn**. Nó khác với việc inject List hoặc Map của nhiều bean, trong đó consumer chủ động yêu cầu một tập ứng viên.

## 2. Trường hợp không có ứng viên

Giả sử chỉ có CheckoutService được đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    CheckoutService checkoutService(PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Nhưng context không có bean nào implement PaymentProvider. Khi Spring gọi factory method checkoutService, nó không thể cung cấp tham số provider.

Kết quả thường là context khởi động thất bại với exception liên quan đến việc tạo bean và resolve dependency. Những loại exception có thể thấy gồm:

- **UnsatisfiedDependencyException:** Spring không đáp ứng được dependency của bean đang tạo.
- **NoSuchBeanDefinitionException:** không tìm thấy bean phù hợp cho kiểu hoặc tên được yêu cầu.
- **BeanCreationException:** exception bao ngoài trong quá trình tạo bean; nguyên nhân cụ thể thường nằm ở cause chain.

Một log rút gọn có thể có dạng:

~~~text
org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'checkoutService':
Unsatisfied dependency expressed through method 'checkoutService'
parameter 0
    ...
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentProvider' available
    ...
~~~

Tên method, vị trí tham số và cấu trúc log thực tế thay đổi theo cách khai báo bean và phiên bản Spring. Điều cần nhận ra là **CheckoutService là bean bị ảnh hưởng, còn PaymentProvider là dependency đang thiếu**.

### 2.1. Nguyên nhân thường gặp khiến không có candidate

Một implementation có thể tồn tại trong source nhưng không được đưa vào candidate set vì:

1. Class chưa được đăng ký thành bean.
2. Package chứa component nằm ngoài phạm vi component scan.
3. Configuration class chứa phương thức @Bean chưa được import hoặc scan.
4. Profile đang hoạt động không khớp với @Profile của bean.
5. Điều kiện auto-configuration hoặc @Conditional không thỏa.
6. Dependency chứa class implementation không có trên runtime classpath.
7. Bean bị loại khỏi autowiring bằng metadata như autowireCandidate=false.
8. Qualifier tại injection point lọc hết các bean hiện có.
9. Generic type của dependency không tương thích với bean đã đăng ký.

Ví dụ implementation:

~~~java
public class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }

    @Override
    public void charge(long orderId) {
        // Xử lý thanh toán thẻ.
    }
}
~~~

Class này **không tự trở thành bean** nếu không có cơ chế đăng ký. Có thể thêm @Component:

~~~java
@Component
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

hoặc đăng ký bằng @Bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {
    @Bean
    PaymentProvider cardPaymentProvider() {
        return new CardPaymentProvider();
    }
}
~~~

Hai cách đều có thể tạo bean, miễn cấu hình được Spring xử lý và các dependency liên quan có thể khởi tạo.

### 2.2. Không tìm thấy bean khác với bean tạo thất bại

| Hiện tượng | Ý nghĩa |
|---|---|
| **NoSuchBeanDefinitionException** | Không tìm thấy candidate phù hợp để đáp ứng dependency. |
| **BeanCreationException** với cause từ constructor/factory method | Bean definition có thể đã tồn tại, nhưng quá trình tạo instance thất bại. |
| **UnsatisfiedDependencyException** | Một bean không được tạo vì dependency không được đáp ứng; cần xem cause bên trong. |

Ví dụ, nếu CardPaymentProvider được đăng ký nhưng constructor của nó ném IllegalStateException do cấu hình thiếu, đó không đơn thuần là “không có bean”. Spring có thể tìm thấy định nghĩa nhưng không thể tạo instance.

Khi đọc log, không dừng ở dòng đầu như **Application run failed** hoặc **Error creating bean**. Hãy lần theo các đoạn **Caused by:** để xác định lỗi gốc ở tầng nào.

## 3. Trường hợp có nhiều ứng viên cùng kiểu

Bây giờ đăng ký hai implementation:

~~~java
@Component
public class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }

    @Override
    public void charge(long orderId) {
        System.out.println("Charge by card: " + orderId);
    }
}
~~~

~~~java
@Component
public class WalletPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "wallet";
    }

    @Override
    public void charge(long orderId) {
        System.out.println("Charge by wallet: " + orderId);
    }
}
~~~

Nếu CheckoutService vẫn yêu cầu:

~~~java
public CheckoutService(PaymentProvider provider) {
    this.provider = provider;
}
~~~

Spring tìm thấy hai candidate:

~~~text
PaymentProvider
├── cardPaymentProvider
└── walletPaymentProvider

CheckoutService cần đúng một PaymentProvider
                 │
                 ▼
       Có hai ứng viên cùng phù hợp
                 │
                 ▼
       Không biết nên chọn bean nào
~~~

Nếu không có qualifier, primary candidate hoặc quy tắc phân giải khác đủ rõ, Spring báo **NoUniqueBeanDefinitionException**. Trong lúc tạo bean, exception này có thể được bọc bởi UnsatisfiedDependencyException hoặc BeanCreationException.

Log rút gọn:

~~~text
org.springframework.beans.factory.UnsatisfiedDependencyException:
Error creating bean with name 'checkoutService'
    ...
Caused by: org.springframework.beans.factory.NoUniqueBeanDefinitionException:
No qualifying bean of type 'com.example.payment.PaymentProvider'
available: expected single matching bean but found 2:
cardPaymentProvider,walletPaymentProvider
    ...
~~~

Tên bean và số lượng candidate trong ví dụ chỉ minh họa. Điều quan trọng là **nhiều bean cùng phù hợp với một dependency đơn**, không phải vì Spring không thể tạo bất kỳ bean nào.

## 4. Dùng @Primary để chọn ứng viên mặc định

Nếu ứng dụng có một implementation nên được dùng làm lựa chọn mặc định, có thể đánh dấu bằng **@Primary**.

~~~java
@Component
@Primary
public class CardPaymentProvider implements PaymentProvider {
    @Override
    public String name() {
        return "card";
    }

    @Override
    public void charge(long orderId) {
        System.out.println("Charge by card: " + orderId);
    }
}
~~~

WalletPaymentProvider vẫn là bean hợp lệ:

~~~java
@Component
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

Khi một injection point yêu cầu đúng một PaymentProvider và các candidate còn lại tương đương, Spring có thể chọn bean được đánh dấu @Primary.

~~~text
PaymentProvider candidates
├── cardPaymentProvider   @Primary
└── walletPaymentProvider
             │
             ▼
Dependency đơn PaymentProvider
             │
             ▼
      Chọn cardPaymentProvider
~~~

### 4.1. @Primary không loại bean còn lại khỏi context

Sau khi đánh dấu CardPaymentProvider là primary, cả hai bean vẫn được đăng ký. Nếu consumer yêu cầu:

~~~java
public PaymentCatalog(List<PaymentProvider> providers) {
    this.providers = providers;
}
~~~

thì mục tiêu là lấy tất cả candidate phù hợp. @Primary **không làm List chỉ còn CardPaymentProvider**.

Tương tự, Map<String, PaymentProvider> vẫn có thể chứa cả hai bean. @Primary chủ yếu giúp phân giải **một dependency đơn** khi có nhiều candidate.

### 4.2. Không nên đánh dấu nhiều bean cùng @Primary cho cùng một kiểu

Nếu hai candidate đều được đánh dấu @Primary và không có quy tắc khác phân biệt, dependency đơn vẫn có thể mơ hồ. @Primary chỉ hữu ích khi có một lựa chọn ưu tiên rõ ràng trong tập candidate phù hợp.

### 4.3. @Primary không thay thế qualifier trong mọi tình huống

Nếu một service luôn phải dùng ví điện tử, dù CardPaymentProvider đang là primary, hãy khai báo rõ yêu cầu bằng qualifier. Điều đó diễn đạt chính xác hơn việc dựa vào mặc định chung của ứng dụng.

## 5. Dùng @Qualifier để chọn bean cụ thể

**@Qualifier** cho phép lọc các candidate theo metadata. Ví dụ:

~~~java
@Component
@Qualifier("card")
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

~~~java
@Component
@Qualifier("wallet")
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

Consumer chọn đúng nhóm hoặc implementation:

~~~java
@Service
public class CardCheckoutService {
    private final PaymentProvider provider;

    public CardCheckoutService(
            @Qualifier("card") PaymentProvider provider) {
        this.provider = provider;
    }
}
~~~

Khi resolve dependency, Spring lọc các candidate theo qualifier phù hợp. Nếu chỉ còn một candidate, injection có thể thành công dù context có nhiều bean cùng kiểu.

### 5.1. Qualifier có thể dùng với tên bean

~~~java
@Component("cardPaymentProvider")
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

~~~java
public CardCheckoutService(
        @Qualifier("cardPaymentProvider") PaymentProvider provider) {
    this.provider = provider;
}
~~~

Tên bean có thể được sử dụng như một qualifier trong quá trình autowiring khi phù hợp. Tuy nhiên, **@Qualifier** được thiết kế để biểu đạt tiêu chí lựa chọn; nó không chỉ là một cách viết khác của tên biến.

### 5.2. Tạo qualifier riêng theo ngữ nghĩa

Trong ứng dụng lớn, các chuỗi qualifier có thể khó quản lý. Có thể định nghĩa annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface OnlinePayment {
}
~~~

Đánh dấu implementation:

~~~java
@Component
@OnlinePayment
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

Inject:

~~~java
public OnlineCheckoutService(
        @OnlinePayment PaymentProvider provider) {
    this.provider = provider;
}
~~~

Qualifier riêng giúp thể hiện vai trò nghiệp vụ như **OnlinePayment**, **OfflinePayment**, **PrimaryRegion** hoặc **FallbackStorage** thay vì rải chuỗi tùy ý.

### 5.3. Qualifier có thể lọc collection

Qualifier không chỉ dùng cho dependency đơn. Với:

~~~java
public OnlinePaymentCatalog(
        @OnlinePayment List<PaymentProvider> providers) {
    this.providers = providers;
}
~~~

Spring có thể cung cấp tất cả candidate có qualifier phù hợp. Nếu nhiều bean cùng mang qualifier OnlinePayment, collection sẽ chứa các bean phù hợp đó.

## 6. Kết hợp @Primary và @Qualifier

Hai annotation giải quyết các vấn đề khác nhau:

- **@Primary:** lựa chọn mặc định khi một dependency đơn có nhiều candidate.
- **@Qualifier:** lọc candidate theo tiêu chí cụ thể tại injection point.

Ví dụ:

~~~java
@Component
@Primary
@Qualifier("card")
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

~~~java
@Component
@Qualifier("wallet")
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

Một injection point:

~~~java
public CheckoutService(
        @Qualifier("wallet") PaymentProvider provider) {
    this.provider = provider;
}
~~~

chỉ định rõ nhóm wallet. @Primary của CardPaymentProvider không làm cho bean đó vượt qua qualifier wallet.

Một quy trình khái niệm:

~~~text
Tất cả bean có kiểu tương thích
             │
             ▼
Lọc theo qualifier / candidate metadata
             │
             ▼
Nếu còn một candidate: chọn candidate đó
             │
             ▼
Nếu còn nhiều candidate:
             │
             ▼
Xét primary và các tiêu chí lựa chọn khác
             │
             ▼
Nếu vẫn không phân biệt được:
NoUniqueBeanDefinitionException
~~~

Đây là mô hình dễ hiểu, không phải mô tả đầy đủ mọi nhánh nội bộ của thuật toán autowiring. Spring còn xét kiểu generic, dependency name, priority và metadata khác tùy tình huống.

## 7. Phân biệt @Order với @Primary

Hai annotation thường bị dùng nhầm:

| Annotation | Mục tiêu chính |
|---|---|
| **@Primary** | Chọn bean mặc định cho một dependency đơn khi có nhiều candidate. |
| **@Qualifier** | Lọc candidate theo metadata tại injection point. |
| **@Order** | Sắp xếp các phần tử ở những điểm nhận collection có thứ tự, như List hoặc mảng. |

Ví dụ:

~~~java
@Component
@Order(1)
public class CardPaymentProvider implements PaymentProvider {
    // ...
}
~~~

~~~java
@Component
@Order(2)
public class WalletPaymentProvider implements PaymentProvider {
    // ...
}
~~~

@Order không có nghĩa CardPaymentProvider sẽ tự được chọn cho:

~~~java
public CheckoutService(PaymentProvider provider) {
    this.provider = provider;
}
~~~

Nếu cần một bean đơn, hãy dùng @Primary hoặc @Qualifier. Nếu cần List<PaymentProvider> theo thứ tự, @Order mới là cơ chế phù hợp.

## 8. Khi dependency có thể không tồn tại

Không phải lúc nào ứng dụng cũng cần một implementation. Ví dụ một module gửi email là tùy chọn; môi trường local có thể không cấu hình email provider.

Nếu khai báo dependency đơn bắt buộc:

~~~java
public NotificationService(NotificationGateway gateway) {
    this.gateway = gateway;
}
~~~

thì không có candidate có thể khiến context không khởi động được. Nếu việc vắng mặt là hợp lệ, hãy thể hiện tính optional rõ ràng.

### 8.1. Dùng Optional<T>

~~~java
import java.util.Optional;

@Service
public class NotificationService {
    private final Optional<NotificationGateway> gateway;

    public NotificationService(Optional<NotificationGateway> gateway) {
        this.gateway = gateway;
    }

    public void notifyUser(String message) {
        gateway.ifPresent(value -> value.send(message));
    }
}
~~~

Khi không có bean phù hợp, Spring có thể inject **Optional.empty()**. Khi có một candidate phù hợp, Optional chứa bean đó.

Nếu có nhiều candidate và không có quy tắc chọn rõ ràng, Optional không tự giải quyết sự mơ hồ. Optional diễn đạt **có thể không có một dependency đơn**, không phải “lấy bất kỳ bean nào trong số nhiều bean”.

### 8.2. Dùng ObjectProvider<T>

**ObjectProvider** hữu ích khi muốn trì hoãn lookup tới thời điểm sử dụng:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OptionalNotificationService {
    private final ObjectProvider<NotificationGateway> gatewayProvider;

    public OptionalNotificationService(
            ObjectProvider<NotificationGateway> gatewayProvider) {
        this.gatewayProvider = gatewayProvider;
    }

    public void notifyUser(String message) {
        NotificationGateway gateway =
                gatewayProvider.getIfAvailable();

        if (gateway != null) {
            gateway.send(message);
        }
    }
}
~~~

Một số phương thức quan trọng:

| API | Khi không có candidate | Khi có nhiều candidate không phân biệt được |
|---|---|---|
| **getObject()** | Ném lỗi không tìm thấy bean. | Ném lỗi không chọn được bean duy nhất. |
| **getIfAvailable()** | Trả về null. | Có thể ném NoUniqueBeanDefinitionException. |
| **getIfUnique()** | Trả về null. | Trả null nếu không có candidate duy nhất theo quy tắc resolution. |
| **stream()** | Stream rỗng. | Trả stream các candidate phù hợp. |
| **orderedStream()** | Stream rỗng. | Trả stream được sắp xếp theo quy tắc order của Spring. |

Nếu ứng dụng cần tất cả implementation, dùng stream hoặc collection. Nếu chỉ cần một bean tùy chọn, getIfAvailable hoặc getIfUnique giúp diễn đạt khác nhau giữa “có thể chọn” và “có một candidate duy nhất”.

### 8.3. Optional không thay thế collection

**Optional<PaymentProvider>** biểu diễn tối đa một candidate được chọn. Nếu cần tất cả payment provider, dùng **List<PaymentProvider>**, **Set<PaymentProvider>**, **Map<String, PaymentProvider>** hoặc **ObjectProvider<PaymentProvider>.orderedStream()**.

## 9. Trường hợp có nhiều bean nhưng muốn nhận tất cả

Nếu service thật sự cần tất cả implementation, đừng ép Spring chọn một bean đơn. Hãy khai báo collection:

~~~java
@Service
public class PaymentCatalog {
    private final List<PaymentProvider> providers;

    public PaymentCatalog(List<PaymentProvider> providers) {
        this.providers = providers;
    }
}
~~~

Với hai bean CardPaymentProvider và WalletPaymentProvider, List có thể chứa cả hai. Nếu không có candidate, collection injection và cách khai báo dependency có thể chịu các quy tắc required-dependency tương ứng; khi việc không có phần tử là một tình huống nghiệp vụ hợp lệ, **ObjectProvider.orderedStream()** thể hiện rõ hơn ý định trả về stream rỗng.

Map:

~~~java
public PaymentCatalog(Map<String, PaymentProvider> providersByBeanName) {
    this.providersByBeanName = providersByBeanName;
}
~~~

cung cấp key là **bean name**. Set phù hợp khi không cần biểu diễn thứ tự. Đừng dùng @Primary với kỳ vọng collection chỉ chứa bean primary; collection có mục đích tập hợp các candidate phù hợp.

## 10. Kiểm thử trường hợp không có ứng viên

Một cách viết test tập trung cho cấu hình Spring Boot là **ApplicationContextRunner**. Công cụ này cho phép dựng một ApplicationContext nhỏ với cấu hình được chọn, kiểm tra context thành công hay thất bại mà không cần khởi động toàn bộ web server.

Các ví dụ dưới đây dùng JUnit 5, AssertJ và Spring Boot Test. Cần có dependency test phù hợp, ví dụ:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Giả sử interface và service:

~~~java
public interface PaymentProvider {
    String name();
}
~~~

~~~java
public class CheckoutService {
    private final PaymentProvider provider;

    public CheckoutService(PaymentProvider provider) {
        this.provider = provider;
    }

    public String providerName() {
        return provider.name();
    }
}
~~~

### 10.1. Cấu hình thiếu bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MissingProviderConfiguration {
    @Bean
    CheckoutService checkoutService(PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Không khai báo bean PaymentProvider. Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class MissingProviderTest {
    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(MissingProviderConfiguration.class);

    @Test
    void contextFailsWhenRequiredProviderIsMissing() {
        runner.run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class);
        });
    }
}
~~~

Test này xác nhận context thất bại và nguyên nhân sâu nhất thuộc loại NoSuchBeanDefinitionException. Exception ngoài cùng có thể là UnsatisfiedDependencyException hoặc BeanCreationException tùy đường tạo bean.

Điều cần kiểm tra là **context thực sự không có PaymentProvider**. Nếu vô tình có một bean từ auto-configuration hoặc test configuration khác, test sẽ không tái hiện đúng tình huống.

### 10.2. Kiểm tra bằng context runner với một provider tùy chọn

Nếu dependency là tùy chọn, cấu hình có thể dùng ObjectProvider:

~~~java
import org.springframework.beans.factory.ObjectProvider;

public class OptionalCheckoutService {
    private final ObjectProvider<PaymentProvider> providers;

    public OptionalCheckoutService(
            ObjectProvider<PaymentProvider> providers) {
        this.providers = providers;
    }

    public boolean hasProvider() {
        return providers.getIfAvailable() != null;
    }
}
~~~

Cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
class OptionalProviderConfiguration {
    @Bean
    OptionalCheckoutService optionalCheckoutService(
            ObjectProvider<PaymentProvider> providers) {
        return new OptionalCheckoutService(providers);
    }
}
~~~

Test:

~~~java
@Test
void contextStartsWhenOptionalProviderIsMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(OptionalProviderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                OptionalCheckoutService service =
                        context.getBean(OptionalCheckoutService.class);
                assertThat(service.hasProvider()).isFalse();
            });
}
~~~

Ở đây context vẫn khởi động vì dependency được yêu cầu là ObjectProvider, bản thân provider có thể được inject dù không có PaymentProvider candidate. Khi gọi getIfAvailable, kết quả là null.

## 11. Kiểm thử trường hợp có nhiều ứng viên

Để tái hiện ambiguity, đăng ký hai bean khác tên nhưng cùng implement PaymentProvider:

~~~java
@Configuration(proxyBeanMethods = false)
class MultipleProviderConfiguration {

    @Bean
    PaymentProvider cardProvider() {
        return () -> "card";
    }

    @Bean
    PaymentProvider walletProvider() {
        return () -> "wallet";
    }

    @Bean
    CheckoutService checkoutService(PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Test:

~~~java
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;

class MultipleProviderTest {
    @Test
    void contextFailsWhenSingleDependencyHasMultipleCandidates() {
        new ApplicationContextRunner()
                .withUserConfiguration(MultipleProviderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }
}
~~~

Context không thể tạo CheckoutService vì tham số PaymentProvider có hai candidate: **cardProvider** và **walletProvider**. Test kiểm tra nguyên nhân sâu nhất thay vì phụ thuộc vào toàn bộ thông điệp exception có thể thay đổi theo phiên bản.

### 11.1. Kiểm tra cách sửa bằng @Primary

Đánh dấu một bean:

~~~java
@Configuration(proxyBeanMethods = false)
class PrimaryProviderConfiguration {

    @Bean
    @Primary
    PaymentProvider cardProvider() {
        return () -> "card";
    }

    @Bean
    PaymentProvider walletProvider() {
        return () -> "wallet";
    }

    @Bean
    CheckoutService checkoutService(PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Test:

~~~java
@Test
void primaryCandidateIsInjected() {
    new ApplicationContextRunner()
            .withUserConfiguration(PrimaryProviderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                CheckoutService service =
                        context.getBean(CheckoutService.class);
                assertThat(service.providerName()).isEqualTo("card");
            });
}
~~~

Test xác nhận khi có nhiều bean nhưng một candidate được đánh dấu primary, dependency đơn có thể resolve theo lựa chọn đó.

### 11.2. Kiểm tra cách sửa bằng @Qualifier

Nếu service cần wallet cụ thể, khai báo qualifier tại injection point:

~~~java
@Configuration(proxyBeanMethods = false)
class QualifiedProviderConfiguration {

    @Bean("cardProvider")
    PaymentProvider cardProvider() {
        return () -> "card";
    }

    @Bean("walletProvider")
    PaymentProvider walletProvider() {
        return () -> "wallet";
    }

    @Bean
    CheckoutService checkoutService(
            @Qualifier("walletProvider") PaymentProvider provider) {
        return new CheckoutService(provider);
    }
}
~~~

Test:

~~~java
@Test
void qualifierSelectsWalletProvider() {
    new ApplicationContextRunner()
            .withUserConfiguration(QualifiedProviderConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                CheckoutService service =
                        context.getBean(CheckoutService.class);
                assertThat(service.providerName()).isEqualTo("wallet");
            });
}
~~~

Qualifier làm rõ implementation mà CheckoutService yêu cầu, bất kể bean nào được chọn làm primary ở nơi khác.

### 11.3. Kiểm thử trường hợp qualifier không khớp

Nếu injection point yêu cầu:

~~~java
@Qualifier("bank") PaymentProvider provider
~~~

nhưng context chỉ có qualifier card và wallet, Spring không còn candidate đáp ứng. Trường hợp này gần với **no candidate after filtering**. Test nên xác nhận context thất bại và đọc cause để biết kiểu dependency nào không được đáp ứng.

Điểm cần nhớ: có nhiều bean cùng kiểu không có nghĩa mọi injection point đều mơ hồ; qualifier có thể lọc chúng thành không, một hoặc nhiều candidate.

## 12. Kiểm thử collection khi có nhiều bean

Nếu consumer yêu cầu List, Spring không cần chọn duy nhất một implementation:

~~~java
public class PaymentProviderCatalog {
    private final List<PaymentProvider> providers;

    public PaymentProviderCatalog(List<PaymentProvider> providers) {
        this.providers = providers;
    }

    public List<String> names() {
        return providers.stream()
                .map(PaymentProvider::name)
                .toList();
    }
}
~~~

Cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
class ProviderCollectionConfiguration {
    @Bean
    PaymentProvider cardProvider() {
        return () -> "card";
    }

    @Bean
    PaymentProvider walletProvider() {
        return () -> "wallet";
    }

    @Bean
    PaymentProviderCatalog catalog(List<PaymentProvider> providers) {
        return new PaymentProviderCatalog(providers);
    }
}
~~~

Test:

~~~java
@Test
void collectionReceivesAllMatchingProviders() {
    new ApplicationContextRunner()
            .withUserConfiguration(ProviderCollectionConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                PaymentProviderCatalog catalog =
                        context.getBean(PaymentProviderCatalog.class);
                assertThat(catalog.names())
                        .containsExactlyInAnyOrder("card", "wallet");
            });
}
~~~

Test dùng **containsExactlyInAnyOrder** vì không đặt ra hợp đồng thứ tự. Nếu thứ tự là yêu cầu, hãy cấu hình @Order và kiểm tra bằng **containsExactly**.

Để xử lý trường hợp không có phần tử một cách tường minh:

~~~java
public class OptionalProviderCatalog {
    private final ObjectProvider<PaymentProvider> provider;

    public OptionalProviderCatalog(
            ObjectProvider<PaymentProvider> provider) {
        this.provider = provider;
    }

    public List<PaymentProvider> all() {
        return provider.orderedStream().toList();
    }
}
~~~

orderedStream() có thể trả stream rỗng khi không có candidate. Điều này làm ý định “danh sách có thể không có phần tử” rõ ràng và tránh phụ thuộc vào cách một dependency collection bắt buộc được resolve trong từng injection point.

## 13. Dùng @SpringBootTest để kiểm tra ứng dụng đầy đủ

ApplicationContextRunner phù hợp với một lát cắt cấu hình. Khi muốn xác nhận cấu hình thực tế của ứng dụng, có thể dùng **@SpringBootTest**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest
class PaymentProviderContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void applicationHasExpectedPaymentProviders() {
        assertThat(context.getBeansOfType(PaymentProvider.class))
                .containsKeys("cardPaymentProvider", "walletPaymentProvider");
    }
}
~~~

Test này khởi tạo context theo cấu hình ứng dụng và kiểm tra các bean thật sự có mặt trong đó. Nó hữu ích khi candidate phụ thuộc component scanning, profile, auto-configuration hoặc nhiều configuration class.

Tuy nhiên, @SpringBootTest có thể khởi tạo nhiều thành phần, kết nối hệ thống ngoài hoặc chạy embedded web server tùy thuộc cấu hình test. Với bài toán chọn bean đơn giản, ApplicationContextRunner thường nhanh và cô lập hơn.

### 13.1. Kiểm tra lỗi khởi động của toàn ứng dụng

Nếu ứng dụng thật sự không khởi động do ambiguity, một test @SpringBootTest mặc định cũng có thể thất bại ngay khi dựng context. Khi đó:

- Đọc exception ngoài cùng để xác định bean đang tạo.
- Tìm NoUniqueBeanDefinitionException hoặc NoSuchBeanDefinitionException trong cause chain.
- Xác nhận tập bean candidate trong context test.
- Tránh bắt exception trong production chỉ để test chuyển sang xanh.

Không nên viết test chỉ xác nhận “context có lỗi” mà không kiểm tra nguyên nhân. Một context có thể thất bại do database, port, cấu hình hoặc lỗi unrelated; test nên xác nhận exception cụ thể hoặc hành vi chọn bean mong muốn.

## 14. Phân biệt ambiguity với trùng bean name

Hai lỗi sau thường bị nhầm:

### 14.1. Nhiều bean khác tên cùng kiểu

~~~text
cardProvider   : PaymentProvider
walletProvider : PaymentProvider
~~~

Dependency:

~~~java
CheckoutService(PaymentProvider provider)
~~~

Nếu không có cách chọn candidate, lỗi là **NoUniqueBeanDefinitionException**.

### 14.2. Hai định nghĩa trùng tên bean

Giả sử hai cấu hình đều đăng ký:

~~~java
@Bean
PaymentProvider paymentProvider() {
    return new CardPaymentProvider();
}
~~~

và:

~~~java
@Bean
PaymentProvider paymentProvider() {
    return new WalletPaymentProvider();
}
~~~

Nếu cả hai definition cùng được đăng ký vào một context với cùng tên và việc override bị tắt, Spring có thể báo **BeanDefinitionOverrideException** trong quá trình đăng ký bean definition.

Đây không phải ambiguity của dependency theo kiểu. Vấn đề là **hai định nghĩa cạnh tranh cùng một bean name**.

| Tình huống | Exception thường gặp | Nguyên nhân |
|---|---|---|
| Không có bean phù hợp | NoSuchBeanDefinitionException hoặc exception bọc dependency | Candidate set rỗng. |
| Nhiều bean cùng kiểu cho dependency đơn | NoUniqueBeanDefinitionException hoặc exception bọc dependency | Candidate set có nhiều phần tử, không chọn được một. |
| Nhiều bean definition trùng tên | BeanDefinitionOverrideException khi override bị cấm | Xung đột tên đăng ký. |
| Bean đã đăng ký nhưng tạo instance thất bại | BeanCreationException với cause cụ thể | Constructor, factory method hoặc dependency khi khởi tạo bị lỗi. |

Trong cấu hình Spring Boot thông thường, bean definition overriding mặc định bị tắt; không nên bật override chỉ để che lỗi trùng tên. Hãy đặt tên rõ ràng và quyết định implementation nào cần được đăng ký.

## 15. Candidate set còn phụ thuộc profile và điều kiện

Hai môi trường có thể có tập bean khác nhau dù cùng một source code.

~~~java
@Component
@Profile("development")
public class FakePaymentProvider implements PaymentProvider {
    public String name() {
        return "fake";
    }
}
~~~

~~~java
@Component
@Profile("production")
public class RealPaymentProvider implements PaymentProvider {
    public String name() {
        return "real";
    }
}
~~~

Nếu profile development active, FakePaymentProvider có thể là candidate. Nếu production active, RealPaymentProvider có thể được đăng ký thay thế.

Tương tự, auto-configuration có thể đăng ký bean theo **@ConditionalOnClass**, **@ConditionalOnProperty**, **@ConditionalOnBean** hoặc **@ConditionalOnMissingBean**.

Khi gặp no candidate, hãy kiểm tra:

1. Profile thực sự được kích hoạt.
2. Property được nạp từ file, biến môi trường hoặc nguồn khác.
3. Dependency có trên runtime classpath không.
4. Auto-configuration có bị exclude hoặc không match không.
5. Bean definition có được đăng ký trong context đang xét không.

Đừng thêm @Primary trước khi xác nhận candidate thực sự tồn tại. @Primary không thể giải quyết một tập candidate rỗng.

## 16. Chẩn đoán bằng ApplicationContext và Actuator

Trong code hoặc debugger, có thể xem các bean phù hợp:

~~~java
String[] names =
        context.getBeanNamesForType(PaymentProvider.class);

for (String name : names) {
    System.out.println(name);
}
~~~

Hoặc:

~~~java
Map<String, PaymentProvider> providers =
        context.getBeansOfType(PaymentProvider.class);
~~~

API thứ hai lấy instance và có thể kích hoạt khởi tạo các bean phù hợp. Nếu chỉ muốn biết tên candidate, dùng API tên theo kiểu phù hợp hơn.

Trong Spring Boot, **Actuator /actuator/beans** có thể giúp quan sát bean đang chạy nếu đã thêm Actuator và expose endpoint theo cấu hình. Endpoint **/actuator/conditions** giúp xem lý do auto-configuration được áp dụng hoặc bỏ qua.

Ví dụ cấu hình expose có giới hạn:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,beans,conditions
~~~

Endpoint quản trị có thể tiết lộ cấu trúc nội bộ. Trong môi trường thật, cần bảo vệ bằng authentication/authorization và giới hạn mạng truy cập; không expose công khai chỉ để thuận tiện debug.

### 16.1. Condition report giúp tìm lý do không có candidate

Chạy ứng dụng với tùy chọn:

~~~bash
java -jar app.jar --debug
~~~

Boot có thể in **Condition Evaluation Report** trong startup log. Nếu bean dự kiến đến từ auto-configuration, report có thể cho biết:

- Class cần thiết không có trên classpath.
- Property không tồn tại hoặc giá trị không khớp.
- Một bean phụ thuộc chưa có.
- Auto-configuration đã bị exclude.
- Một bean mặc định không được tạo vì ứng dụng đã cung cấp bean phù hợp.

Positive match ở cấp auto-configuration không chứng minh tất cả bean bên trong đã khởi tạo thành công; hãy kết hợp report với bean list và stack trace.

## 17. Chọn chiến lược kiểm thử phù hợp

| Mục tiêu kiểm thử | Cách làm phù hợp |
|---|---|
| Không có bean bắt buộc, context phải fail | ApplicationContextRunner và kiểm tra NoSuchBeanDefinitionException trong cause chain. |
| Có hai bean cho một dependency đơn, context phải fail | ApplicationContextRunner và kiểm tra NoUniqueBeanDefinitionException. |
| @Primary chọn implementation mặc định | Dựng hai candidate, đánh dấu một bean primary, kiểm tra dependency được inject. |
| @Qualifier chọn đúng implementation | Dựng nhiều candidate, thêm qualifier ở bean và injection point, kiểm tra behavior. |
| Collection nhận tất cả implementation | Inject List/Map và kiểm tra phần tử. |
| Dependency có thể vắng mặt | Optional hoặc ObjectProvider, kiểm tra empty/null/stream rỗng theo API. |
| Candidate thay đổi theo profile/property | Chạy context với profile/property khác nhau. |
| Cấu hình thật của toàn ứng dụng | @SpringBootTest khi cần xác nhận component scan, auto-configuration và wiring tổng thể. |

Một test tốt nên mô tả **hợp đồng lựa chọn bean** thay vì chỉ phụ thuộc vào message đầy đủ của exception. Message có thể thay đổi giữa các phiên bản Spring; kiểm tra loại exception và bean behavior thường ổn định hơn.

## 18. Những lỗi thiết kế khiến việc chọn bean khó kiểm soát

### 18.1. Dùng @Primary như một cách che ambiguity

Nếu hệ thống có nhiều implementation và mỗi service cần một implementation khác nhau, đánh dấu một bean primary toàn cục có thể khiến một số consumer nhận nhầm implementation.

Hãy dùng @Qualifier tại consumer nếu dependency có ý nghĩa cụ thể. @Primary chỉ nên biểu đạt lựa chọn mặc định hợp lý cho ứng dụng.

### 18.2. Dựa vào thứ tự khai báo bean để chọn một candidate

Không nên cho rằng bean được khai báo đầu tiên sẽ luôn được inject. Nếu cần một candidate duy nhất, hãy dùng @Primary hoặc @Qualifier. @Order dùng cho thứ tự collection, không phải cách thay thế để giải quyết ambiguity của dependency đơn.

### 18.3. Tên bean bị dùng như mã nghiệp vụ

Map<String, PaymentProvider> dùng bean name làm key. Nếu API bên ngoài gửi mã "wallet", không nên mặc định bean name cũng luôn là "wallet". Có thể xây registry theo PaymentProvider.name() và kiểm tra trùng key rõ ràng.

### 18.4. Tạo object bằng new để né lỗi injection

Nếu context báo không tìm thấy bean, viết:

~~~java
private final PaymentProvider provider =
        new CardPaymentProvider();
~~~

có thể khiến code chạy qua một tình huống đơn giản, nhưng nó bỏ qua cơ chế cấu hình, lifecycle, proxy và khả năng thay implementation của Spring. Hãy sửa nguồn đăng ký hoặc quy tắc lựa chọn bean nếu dependency thực sự thuộc container.

### 18.5. Nuốt exception khi context không thể resolve dependency

Không nên bắt rộng exception trong constructor/factory method rồi trả về một object không đầy đủ. Một dependency bắt buộc không được đáp ứng là lỗi cấu hình cần phát hiện sớm, không nên để nó biến thành NullPointerException ở một request sau.

### 18.6. Test phụ thuộc quá nhiều vào cấu hình ngoài

Nếu test selection chỉ cần hai bean giả, đừng khởi động cả database hoặc gọi dịch vụ thật. Dùng ApplicationContextRunner với configuration nhỏ để cô lập bài toán. Khi cần kiểm tra wiring toàn ứng dụng, mới dùng @SpringBootTest.

## 19. Bài tập đọc tình huống

### Tình huống A: Không có candidate

Log:

~~~text
No qualifying bean of type 'PaymentProvider' available
~~~

Context chỉ đăng ký CheckoutService.

**Cách hiểu:** dependency bắt buộc PaymentProvider không có candidate. Kiểm tra bean registration, component scan, profile, condition và runtime classpath. Không có cơ sở để chọn @Primary vì không có bean nào để ưu tiên.

### Tình huống B: Hai candidate

Log:

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
~~~

Context có cardProvider và walletProvider.

**Cách hiểu:** có nhiều bean cùng phù hợp cho dependency đơn. Quyết định nghiệp vụ là chọn một mặc định bằng @Primary, chọn cụ thể bằng @Qualifier, hoặc đổi consumer sang collection nếu thực sự cần tất cả.

### Tình huống C: Qualifier không khớp

Context có:

~~~text
cardProvider   @Qualifier("card")
walletProvider @Qualifier("wallet")
~~~

Consumer yêu cầu:

~~~java
@Qualifier("bank") PaymentProvider provider
~~~

**Cách hiểu:** trước khi áp dụng các quy tắc chọn candidate, qualifier đã loại hết bean. Đây là no candidate sau khi lọc, không phải ambiguity.

### Tình huống D: Trùng tên

Hai configuration cùng đăng ký bean name **paymentProvider**.

**Cách hiểu:** đây là xung đột bean definition name. Kiểm tra hai nguồn đăng ký và đổi tên hoặc bỏ một definition theo thiết kế. @Primary không giải quyết việc trùng tên.

## 20. Những hiểu nhầm thường gặp

**“Không có candidate thì Spring tự chọn bean gần giống nhất.”**  
Không. Spring cần candidate phù hợp theo type và metadata. Nếu không tìm được, dependency bắt buộc sẽ không resolve.

**“Có nhiều candidate thì bean đầu tiên được chọn.”**  
Không nên dựa vào thứ tự đăng ký. Hãy khai báo @Primary hoặc @Qualifier nếu cần một bean duy nhất.

**“@Primary xóa các bean còn lại.”**  
Không. Các bean vẫn nằm trong context và có thể được inject qua collection hoặc qualifier khác.

**“@Qualifier chỉ dùng cho bean name.”**  
Không. Qualifier là metadata để lọc candidate; có thể dùng chuỗi hoặc annotation qualifier riêng.

**“@Order chọn bean cho dependency đơn.”**  
Không. @Order chủ yếu sắp xếp collection/array có thứ tự.

**“Optional<T> xử lý được cả trường hợp không có và có nhiều bean.”**  
Optional xử lý việc có thể không có một dependency đơn; nó không tự giải quyết ambiguity khi nhiều candidate cùng phù hợp.

**“ObjectProvider.getIfAvailable luôn trả null nếu có nhiều bean.”**  
Không. Nếu có nhiều candidate nhưng không thể chọn duy nhất, phương thức này có thể ném NoUniqueBeanDefinitionException. Dùng getIfUnique khi muốn kết quả null trong trường hợp không có candidate duy nhất.

**“NoSuchBeanDefinitionException và BeanDefinitionOverrideException là một lỗi.”**  
Không. Một lỗi là không có candidate phù hợp; lỗi kia là xung đột đăng ký cùng bean name khi override không được phép.

**“Collection injection luôn tương đương một dependency đơn.”**  
Không. List/Set/Map thể hiện nhu cầu nhận nhiều candidate. Khi danh sách có thể rỗng, ObjectProvider làm tính optional rõ ràng.

**“Test context thất bại là đủ chứng minh có ambiguity.”**  
Không. Cần xác nhận cause cụ thể là NoUniqueBeanDefinitionException; context có thể thất bại do database, property hoặc một bean khác.

## Ghi nhớ cốt lõi

Khi Spring cần inject **một bean đơn**, candidate set rỗng thường dẫn đến **NoSuchBeanDefinitionException** (có thể được bọc trong exception tạo bean/dependency), còn candidate set có nhiều phần tử không phân biệt được dẫn đến **NoUniqueBeanDefinitionException**. **@Primary** chọn mặc định; **@Qualifier** lọc candidate theo yêu cầu cụ thể. **Optional** và **ObjectProvider** biểu đạt dependency có thể vắng mặt; collection phù hợp khi consumer cần nhiều implementation.

Để kiểm thử, hãy tạo context nhỏ với **ApplicationContextRunner**, cố ý bỏ bean hoặc đăng ký hai candidate, rồi xác nhận loại exception và hành vi mong muốn. Khi cần kiểm tra cấu hình ứng dụng thật, dùng **@SpringBootTest**. Phân biệt rõ thiếu bean, ambiguity, trùng bean name và lỗi khởi tạo sẽ giúp bạn sửa đúng nguồn cấu hình thay vì che lỗi bằng một lựa chọn tùy tiện.
