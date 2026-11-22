# NoUniqueBeanDefinitionException do nhiều bean cùng kiểu

## 1. Hiểu đúng lỗi

`NoUniqueBeanDefinitionException` xuất hiện khi Spring cần chọn **một bean duy nhất** theo kiểu yêu cầu nhưng tìm thấy nhiều bean cùng phù hợp và không thể xác định candidate nào nên được dùng.

Ví dụ có interface:

~~~java
public interface PaymentGateway {
    String provider();
}
~~~

Ứng dụng đăng ký hai implementation:

~~~java
@Bean
PaymentGateway stripeGateway() {
    return new StripeGateway();
}

@Bean
PaymentGateway walletGateway() {
    return new WalletGateway();
}
~~~

Một service yêu cầu duy nhất một `PaymentGateway`:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Spring thấy cả `stripeGateway` và `walletGateway` đều là candidate cho tham số `PaymentGateway`. Nếu không có qualifier hoặc quy tắc chọn candidate phù hợp, Spring không thể quyết định và quá trình tạo `CheckoutService` thất bại.

Thông báo thường có dạng:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'PaymentGateway' available:
expected single matching bean but found 2:
stripeGateway,walletGateway
~~~

Thông báo thực tế có thể được bọc trong `UnsatisfiedDependencyException` hoặc `BeanCreationException`. Hãy đọc phần `Caused by` sâu nhất để xác định nguyên nhân gốc.

`NoUniqueBeanDefinitionException` là một lớp con của `NoSuchBeanDefinitionException`, nhưng ý nghĩa khác nhau:

| Exception | Ý nghĩa |
| --- | --- |
| `NoSuchBeanDefinitionException` | Không tìm thấy bean phù hợp với kiểu/tên yêu cầu |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp trong khi điểm yêu cầu cần một bean duy nhất |
| `BeanDefinitionOverrideException` | Có nhiều bean definition trùng tên và việc override không được cho phép |
| `BeanCreationException` | Một bean không thể được tạo; nguyên nhân gốc có thể là lỗi khác, trong đó có ambiguity |

Không nên xử lý `NoUniqueBeanDefinitionException` bằng cách bật bean definition overriding. Hai bean có tên khác nhau nhưng cùng kiểu là vấn đề chọn candidate; override bean definition là vấn đề trùng tên.

## 2. Những nơi có thể phát sinh ambiguity

Lỗi không chỉ xảy ra trong constructor injection. Bất kỳ thao tác nào yêu cầu một bean duy nhất theo kiểu đều có thể gặp lỗi.

### 2.1. Constructor injection

~~~java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Constructor yêu cầu một `PaymentGateway`. Nếu có hai candidate ngang nhau, Spring không thể hoàn tất tạo service.

### 2.2. @Bean method parameter

~~~java
@Bean
CheckoutService checkoutService(PaymentGateway gateway) {
    return new CheckoutService(gateway);
}
~~~

Tham số của `@Bean` method cũng được Spring autowire. Vì vậy lỗi có thể nằm trong configuration class thay vì component class.

### 2.3. @Autowired field hoặc setter

~~~java
@Autowired
private PaymentGateway gateway;
~~~

Field injection và setter injection cũng dùng quy trình chọn candidate theo kiểu. Constructor injection thường dễ kiểm soát và kiểm thử hơn, nhưng bản thân cách inject không làm biến mất ambiguity.

### 2.4. BeanFactory.getBean theo kiểu

~~~java
PaymentGateway gateway =
        applicationContext.getBean(PaymentGateway.class);
~~~

Lệnh này yêu cầu một bean theo kiểu. Nếu nhiều bean cùng kiểu và không có candidate duy nhất, `getBean(Class)` cũng có thể ném `NoUniqueBeanDefinitionException`.

Nếu mục tiêu là lấy một bean theo tên, dùng `getBean("stripeGateway", PaymentGateway.class)` hoặc `@Resource(name = "stripeGateway")` tùy vị trí sử dụng.

### 2.5. Không phải mọi dependency cùng kiểu đều gây lỗi

Khi ứng dụng muốn nhận tất cả implementation, hãy khai báo một collection hoặc provider:

~~~java
List<PaymentGateway> gateways;
Map<String, PaymentGateway> gatewaysByName;
PaymentGateway[] gateways;
ObjectProvider<PaymentGateway> gateways;
~~~

Spring có thể đưa tất cả candidate phù hợp vào collection. `@Primary` không loại bean khỏi collection injection.

## 3. Cách 1: dùng @Primary khi có một implementation mặc định

`@Primary` đánh dấu bean được ưu tiên khi nhiều candidate cùng kiểu được inject vào một dependency đơn trị.

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway stripeGateway() {
        return new StripeGateway();
    }

    @Bean
    PaymentGateway walletGateway() {
        return new WalletGateway();
    }
}
~~~

Service không cần thay đổi:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Khi inject một `PaymentGateway`, Spring chọn `stripeGateway` vì đây là candidate duy nhất được đánh dấu `@Primary`.

Dùng `@Primary` khi:
- Ứng dụng có một implementation mặc định hợp lý.
- Các điểm inject thông thường nên dùng cùng implementation đó.
- Các implementation còn lại vẫn cần tồn tại để phục vụ những luồng được chọn rõ ràng.

Không đánh dấu nhiều bean cùng kiểu là `@Primary`. Nếu có nhiều primary candidate, Spring vẫn không có một lựa chọn duy nhất.

**Lưu ý:** `@Primary` chỉ ảnh hưởng injection đơn trị. Khi inject `List<PaymentGateway>`, `Map<String, PaymentGateway>`, array hoặc stream của `ObjectProvider`, Spring vẫn trả về tất cả candidate phù hợp.

## 4. Cách 2: dùng @Qualifier khi từng điểm inject cần implementation cụ thể

Nếu một ứng dụng có nhiều implementation và mỗi service cần một loại khác nhau, `@Qualifier` thể hiện lựa chọn tại đúng điểm inject.

Đánh dấu bean:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Qualifier("card")
    PaymentGateway stripeGateway() {
        return new StripeGateway();
    }

    @Bean
    @Qualifier("digital-wallet")
    PaymentGateway walletGateway() {
        return new WalletGateway();
    }
}
~~~

Chọn bean ở constructor:

~~~java
@Service
public class CardCheckoutService {

    private final PaymentGateway gateway;

    public CardCheckoutService(
            @Qualifier("card") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Một service khác có thể chọn wallet:

~~~java
@Service
public class WalletCheckoutService {

    private final PaymentGateway gateway;

    public WalletCheckoutService(
            @Qualifier("digital-wallet") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

`@Qualifier` lọc tập candidate đã khớp kiểu. Giá trị qualifier nên diễn đạt vai trò hoặc đặc điểm có ý nghĩa, chẳng hạn `card`, `digital-wallet`, `read-only`, `primary-region`.

Không cần qualifier phải duy nhất trong mọi trường hợp. Một qualifier có thể được dùng để lọc nhiều bean khi điểm inject nhận collection:

~~~java
@Autowired
@Qualifier("regional")
private List<PaymentGateway> regionalGateways;
~~~

### 4.1. @Qualifier không giống @Primary

| Annotation | Câu hỏi được trả lời |
| --- | --- |
| `@Primary` | Nếu cần một bean mặc định trong số nhiều candidate, bean nào được ưu tiên? |
| `@Qualifier` | Điểm inject này cần candidate có đặc điểm/nhãn nào? |

Ví dụ, `@Primary` có thể chọn gateway mặc định cho `CheckoutService`, trong khi `@Qualifier("digital-wallet")` chọn wallet cho một service chuyên biệt.

### 4.2. Dùng custom qualifier khi tên chuỗi không đủ rõ

Trong codebase lớn, có thể định nghĩa annotation qualifier riêng:

~~~java
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface CardPayment {
}
~~~

Đánh dấu bean:

~~~java
@Bean
@CardPayment
PaymentGateway stripeGateway() {
    return new StripeGateway();
}
~~~

Inject:

~~~java
public CardCheckoutService(@CardPayment PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom qualifier giảm lỗi chính tả và giúp compiler/IDE hỗ trợ tìm kiếm, refactor tốt hơn.

## 5. Cách 3: dùng @Fallback trong Spring Framework 6.2+

Spring Framework 6.2 giới thiệu `@Fallback`, là đối tác của `@Primary`. Annotation này đánh dấu một bean là candidate dự phòng.

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway stripeGateway() {
        return new StripeGateway();
    }

    @Bean
    @Fallback
    PaymentGateway sandboxGateway() {
        return new SandboxGateway();
    }
}
~~~

Khi một điểm inject yêu cầu duy nhất `PaymentGateway`, `stripeGateway` được chọn vì đây là candidate thông thường duy nhất còn lại sau khi các fallback candidate được xem xét.

Dùng `@Fallback` khi:
- Muốn cung cấp implementation dự phòng.
- Một bean thông thường nên được chọn khi tồn tại.
- Bean dự phòng chỉ nên được chọn khi không có candidate thông thường khác.

Nếu tất cả candidate đều là fallback hoặc còn nhiều candidate thông thường ngang nhau, Spring vẫn có thể không xác định được một bean duy nhất.

`@Fallback` chỉ tác động đến injection đơn trị. Collection injection vẫn chứa tất cả bean phù hợp, bao gồm cả fallback bean.

Spring Boot 3.5 sử dụng Spring Framework 6.2 nên có thể dùng annotation này. Nếu dự án dùng Spring Framework 6.1 hoặc cũ hơn, `@Fallback` chưa có; hãy dùng `@Primary`, `@Qualifier` hoặc thiết kế bean khác phù hợp.

## 6. Cách 4: dùng bean name hoặc @Resource khi cần định danh theo tên

Nếu yêu cầu nghiệp vụ thực sự là “lấy bean có tên `stripeGateway`”, có thể dùng `@Resource`:

~~~java
import jakarta.annotation.Resource;

@Service
public class CardCheckoutService {

    @Resource(name = "stripeGateway")
    private PaymentGateway gateway;
}
~~~

`@Resource` có ngữ nghĩa chọn theo tên bean. Đây là lựa chọn phù hợp khi tên là định danh chính.

Với constructor injection, thường nên dùng `@Qualifier` trên tham số:

~~~java
public CardCheckoutService(
        @Qualifier("card") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Spring Framework 6.1+ còn hỗ trợ dùng tên tham số làm gợi ý khi không có qualifier hoặc primary khác. Cơ chế này cần Java compiler lưu parameter names bằng tùy chọn `-parameters`. Spring Framework 6.2 có fast shortcut cho trường hợp tên tham số khớp tên bean.

Dù vậy, với dependency quan trọng, qualifier tường minh thường dễ đọc và ít phụ thuộc cấu hình compiler hơn.

Không nhầm `@Qualifier("stripeGateway")` với việc tham chiếu bean theo ID thuần túy: `@Autowired` vẫn bắt đầu bằng type matching, sau đó dùng qualifier để thu hẹp candidate. Nếu cần định danh bean theo tên là mục đích chính, `@Resource(name = "...")` thể hiện ý định đó trực tiếp hơn.

## 7. Cách 5: nhận nhiều implementation bằng List, Map hoặc array

Nếu ứng dụng cần hỗ trợ nhiều gateway, không nên ép Spring chọn một implementation tùy ý. Hãy nhận toàn bộ candidate và để logic nghiệp vụ chọn theo dữ liệu đầu vào.

### 7.1. Inject List

~~~java
@Component
public class PaymentGatewayRegistry {

    private final List<PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public List<PaymentGateway> all() {
        return this.gateways;
    }
}
~~~

Spring inject tất cả `PaymentGateway` phù hợp. Có thể dùng `@Order` trên bean để kiểm soát thứ tự trong collection:

~~~java
@Bean
@Order(1)
PaymentGateway stripeGateway() {
    return new StripeGateway();
}

@Bean
@Order(2)
PaymentGateway walletGateway() {
    return new WalletGateway();
}
~~~

`@Order` có thể ảnh hưởng thứ tự collection injection. Nó không phải cơ chế chọn bean duy nhất cho một constructor parameter, và không quyết định thứ tự khởi tạo singleton.

### 7.2. Inject Map với bean name làm key

~~~java
@Component
public class PaymentGatewayRegistry {

    private final Map<String, PaymentGateway> gateways;

    public PaymentGatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = Map.copyOf(gateways);
    }

    public PaymentGateway get(String beanName) {
        PaymentGateway gateway = this.gateways.get(beanName);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unknown payment gateway: " + beanName);
        }
        return gateway;
    }
}
~~~

Spring tạo map với key là bean name và value là instance tương ứng.

Đây là cách hữu ích khi một factory hoặc router cần chọn implementation theo cấu hình. Với lựa chọn theo nghiệp vụ như `CARD`, `WALLET`, `BANK_TRANSFER`, nên tạo một registry có API rõ ràng thay vì rải chuỗi bean name trong toàn bộ ứng dụng.

### 7.3. Inject array

~~~java
public PaymentGatewayRegistry(PaymentGateway[] gateways) {
    this.gateways = List.of(gateways);
}
~~~

Array phù hợp khi API hiện có yêu cầu kiểu mảng. `List` thường thuận tiện hơn cho code Java mới.

## 8. Cách 6: dùng ObjectProvider khi muốn tra cứu bean theo nhu cầu

`ObjectProvider<T>` cho phép yêu cầu bean tại thời điểm cần thiết và hỗ trợ nhiều cách xử lý candidate.

~~~java
@Component
public class PaymentGatewaySelector {

    private final ObjectProvider<PaymentGateway> gateways;

    public PaymentGatewaySelector(
            ObjectProvider<PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentGateway getUniqueGateway() {
        return this.gateways.getIfUnique();
    }

    public List<PaymentGateway> allGateways() {
        return this.gateways.orderedStream().toList();
    }
}
~~~

Một số phương thức:

| Phương thức | Hành vi |
| --- | --- |
| `getObject()` | Yêu cầu một bean; lỗi nếu không tìm thấy hoặc có nhiều candidate không phân giải được |
| `getIfAvailable()` | Trả về bean nếu có; vẫn lỗi nếu có nhiều candidate không thể chọn |
| `getIfUnique()` | Trả về bean nếu có một candidate duy nhất; trả `null` nếu không có hoặc không thể xác định candidate duy nhất |
| `stream()` | Stream tất cả candidate phù hợp |
| `orderedStream()` | Stream candidate phù hợp theo thứ tự Spring |

Nếu nhiều implementation là điều bình thường và việc chọn phụ thuộc request, tenant hoặc loại giao dịch, hãy dùng `Map`, `List` hoặc registry chuyên biệt. Đừng gọi `getObject()` rồi mong Spring tự đoán lựa chọn.

## 9. Auto-configuration: tránh tạo bean mặc định khi ứng dụng đã có bean riêng

Trong starter, một nguyên nhân phổ biến là auto-configuration tạo bean mặc định trong khi ứng dụng đã đăng ký implementation riêng.

Cấu hình dễ gây vấn đề:

~~~java
@AutoConfiguration
public class PaymentAutoConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Nếu ứng dụng cũng khai báo `PaymentGateway`, cả hai bean có thể tồn tại và một điểm inject đơn trị có thể bị ambiguity.

Giải pháp tiêu chuẩn là `@ConditionalOnMissingBean`:

~~~java
@AutoConfiguration
public class PaymentAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentGateway.class)
    PaymentGateway paymentGateway() {
        return new DefaultPaymentGateway();
    }
}
~~~

Ý nghĩa:
- Nếu context chưa có bean `PaymentGateway`, auto-configuration đăng ký implementation mặc định.
- Nếu ứng dụng đã cung cấp một bean phù hợp, method mặc định không đăng ký bean.
- Ứng dụng có thể thay thế hành vi mặc định mà không phải sửa starter.

### 9.1. @ConditionalOnMissingBean không tự giải quyết hai bean do người dùng khai báo

Giả sử ứng dụng tự đăng ký cả Stripe và Wallet. Auto-configuration sẽ back off vì đã có bean thuộc kiểu `PaymentGateway`. Nhưng hai bean người dùng vẫn tồn tại.

Nếu một service vẫn inject:

~~~java
CheckoutService(PaymentGateway gateway)
~~~

thì dependency vẫn mơ hồ nếu không có `@Primary`, `@Qualifier` hoặc quy tắc chọn khác.

`@ConditionalOnMissingBean` giải quyết xung đột giữa bean mặc định của auto-configuration và bean do ứng dụng cung cấp. Nó không thay thế việc thiết kế injection point cho trường hợp nhiều implementation có chủ đích.

### 9.2. Khai báo return type đủ cụ thể

Spring Boot khuyến nghị khai báo return type của `@Bean` method càng cụ thể càng tốt, đặc biệt khi dùng bean conditions.

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
DefaultPaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Return type cụ thể cung cấp thêm thông tin cho quá trình đánh giá condition và type matching. Nếu các injection point yêu cầu interface, bean vẫn có thể được inject qua `PaymentGateway`.

Tuy nhiên, hãy bảo đảm điều kiện diễn đạt đúng hợp đồng: nếu mục tiêu là không tạo default khi có bất kỳ `PaymentGateway` nào, khai báo `@ConditionalOnMissingBean(PaymentGateway.class)` tường minh.

### 9.3. Thứ tự auto-configuration có ý nghĩa

Các bean conditions được đánh giá dựa trên bean definitions đã được xử lý tại thời điểm condition chạy. Vì vậy:
- Nên dùng `@ConditionalOnMissingBean` và `@ConditionalOnBean` trong auto-configuration.
- Auto-configuration được thiết kế để chạy sau bean definitions do người dùng khai báo.
- Nếu candidate có thể được tạo bởi auto-configuration khác, hãy khai báo thứ tự bằng `@AutoConfiguration(after = ...)` hoặc cơ chế ordering tương ứng.
- Không đặt bean condition tùy tiện trong component scan configuration được xử lý quá sớm.

## 10. @ConditionalOnSingleCandidate: chỉ bật cấu hình khi có thể chọn một bean

Có những auto-configuration cần đúng một collaborator. Nếu có nhiều implementation và không có candidate duy nhất, cấu hình đó nên không được bật.

Dùng `@ConditionalOnSingleCandidate`:

~~~java
@AutoConfiguration
public class PaymentHealthAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(PaymentGateway.class)
    PaymentGatewayHealthIndicator paymentGatewayHealthIndicator(
            PaymentGateway gateway) {

        return new PaymentGatewayHealthIndicator(gateway);
    }
}
~~~

Condition này match khi:
- Có một bean phù hợp; hoặc
- Có nhiều bean phù hợp nhưng một primary candidate có thể được xác định.

Nếu có hai gateway ngang nhau, health indicator không được đăng ký. Điều đó giúp tránh lỗi inject trong chính auto-configuration này.

Điều kiện chỉ nhìn thấy bean definitions đã được xử lý tới thời điểm đánh giá. Vì vậy nên đặt condition trong auto-configuration và bảo đảm nó chạy sau cấu hình tạo candidate nếu candidate được cung cấp bởi auto-configuration khác.

Phân biệt hai annotation:

| Annotation | Mục đích |
| --- | --- |
| `@ConditionalOnMissingBean` | Chỉ tạo default bean khi chưa có bean phù hợp |
| `@ConditionalOnSingleCandidate` | Chỉ tạo bean phụ thuộc khi có thể xác định một candidate phù hợp |

## 11. Generic type cũng có thể giúp phân biệt candidate

Spring hỗ trợ dùng generic type như một qualifier ngầm.

Ví dụ:

~~~java
public interface Store<T> {
    T load();
}
~~~

Hai implementation:

~~~java
@Bean
Store<String> stringStore() {
    return new StringStore();
}

@Bean
Store<Integer> integerStore() {
    return new IntegerStore();
}
~~~

Injection:

~~~java
public ReportService(
        Store<String> nameStore,
        Store<Integer> countStore) {
    this.nameStore = nameStore;
    this.countStore = countStore;
}
~~~

Spring có thể dùng generic argument để phân biệt `Store<String>` với `Store<Integer>`.

Cách này hữu ích khi type parameter thể hiện vai trò thực sự của dependency. Cần giữ generic type rõ trong:
- Interface/class khai báo.
- Return type của `@Bean` method.
- Constructor parameter hoặc field injection point.

Nếu khai báo quá thô như `Store<?>` hoặc raw `Store`, thông tin generic có thể không đủ để phân biệt candidate.

Generic qualifier cũng áp dụng với collection, map và array. Ví dụ `List<Store<Integer>>` chỉ nhận các bean tương thích với generic type đó.

## 12. Kiểm thử lỗi và các cách khắc phục bằng ApplicationContextRunner

`ApplicationContextRunner` rất phù hợp để kiểm thử auto-configuration và candidate resolution trong một Spring context nhỏ.

Ví dụ dưới đây dùng Spring Boot 3.5.16, Java 17 và JUnit 5.

### 12.1. Maven dependencies

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

### 12.2. Test class hoàn chỉnh

Tạo `src/test/java/example/NoUniqueBeanDefinitionExceptionTests.java`:

~~~java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Fallback;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;

class NoUniqueBeanDefinitionExceptionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void failsWhenTwoBeansMatchSingleValuedInjection() {
        runner.withUserConfiguration(AmbiguousConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();

                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void primaryResolvesSingleValuedInjection() {
        runner.withUserConfiguration(PrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    CheckoutService checkout =
                            context.getBean(CheckoutService.class);

                    assertThat(checkout.provider()).isEqualTo("stripe");
                });
    }

    @Test
    void qualifierSelectsTheRequiredImplementation() {
        runner.withUserConfiguration(QualifierConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    CheckoutService checkout =
                            context.getBean(CheckoutService.class);

                    assertThat(checkout.provider()).isEqualTo("wallet");
                });
    }

    @Test
    void fallbackBeanIsNotSelectedWhenARegularCandidateExists() {
        runner.withUserConfiguration(FallbackConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    CheckoutService checkout =
                            context.getBean(CheckoutService.class);

                    assertThat(checkout.provider()).isEqualTo("stripe");
                });
    }

    @Test
    void collectionInjectionReceivesAllCandidates() {
        runner.withUserConfiguration(CollectionConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    GatewayRegistry registry =
                            context.getBean(GatewayRegistry.class);

                    assertThat(registry.providers())
                            .containsExactly("stripe", "wallet");
                });
    }

    @Test
    void autoConfigurationCreatesDefaultOnlyWhenMissing() {
        runner.withConfiguration(
                        AutoConfigurations.of(PaymentAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);

                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("default");
                });
    }

    @Test
    void userGatewayMakesAutoConfiguredDefaultBackOff() {
        runner.withConfiguration(
                        AutoConfigurations.of(PaymentAutoConfiguration.class))
                .withUserConfiguration(UserGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);

                    assertThat(context.getBean(PaymentGateway.class).provider())
                            .isEqualTo("custom");
                });
    }

    @Test
    void singleCandidateConditionDoesNotMatchWhenTwoBeansAreAmbiguous() {
        runner.withConfiguration(
                        AutoConfigurations.of(
                                PaymentHealthAutoConfiguration.class))
                .withUserConfiguration(TwoGatewayConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(PaymentGatewayHealthIndicator.class);
                });
    }

    @Test
    void singleCandidateConditionMatchesWhenPrimaryExists() {
        runner.withConfiguration(
                        AutoConfigurations.of(
                                PaymentHealthAutoConfiguration.class))
                .withUserConfiguration(PrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(PaymentGatewayHealthIndicator.class);
                });
    }

    interface PaymentGateway {
        String provider();
    }

    static class StripeGateway implements PaymentGateway {
        @Override
        public String provider() {
            return "stripe";
        }
    }

    static class WalletGateway implements PaymentGateway {
        @Override
        public String provider() {
            return "wallet";
        }
    }

    static class DefaultGateway implements PaymentGateway {
        @Override
        public String provider() {
            return "default";
        }
    }

    static class CheckoutService {

        private final PaymentGateway gateway;

        CheckoutService(PaymentGateway gateway) {
            this.gateway = gateway;
        }

        String provider() {
            return this.gateway.provider();
        }
    }

    record GatewayRegistry(List<String> providers) {
    }

    record PaymentGatewayHealthIndicator(PaymentGateway gateway) {
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousConfiguration {

        @Bean
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryConfiguration {

        @Bean
        @Primary
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class QualifierConfiguration {

        @Bean
        @Qualifier("card")
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        @Qualifier("wallet")
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        CheckoutService checkoutService(
                @Qualifier("wallet") PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FallbackConfiguration {

        @Bean
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        @Fallback
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CollectionConfiguration {

        @Bean
        @Order(1)
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        @Order(2)
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }

        @Bean
        GatewayRegistry gatewayRegistry(List<PaymentGateway> gateways) {
            return new GatewayRegistry(
                    gateways.stream()
                            .map(PaymentGateway::provider)
                            .toList());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGatewayConfiguration {

        @Bean
        PaymentGateway customGateway() {
            return () -> "custom";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoGatewayConfiguration {

        @Bean
        PaymentGateway stripeGateway() {
            return new StripeGateway();
        }

        @Bean
        PaymentGateway walletGateway() {
            return new WalletGateway();
        }
    }

    @AutoConfiguration
    static class PaymentAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(PaymentGateway.class)
        PaymentGateway defaultPaymentGateway() {
            return new DefaultGateway();
        }
    }

    @AutoConfiguration
    static class PaymentHealthAutoConfiguration {

        @Bean
        @ConditionalOnSingleCandidate(PaymentGateway.class)
        PaymentGatewayHealthIndicator paymentGatewayHealthIndicator(
                PaymentGateway gateway) {
            return new PaymentGatewayHealthIndicator(gateway);
        }
    }
}
~~~

### 12.3. Chạy test

~~~bash
mvn test -Dtest=NoUniqueBeanDefinitionExceptionTests
~~~

Kết quả mong đợi: **9 test PASS**.

Các test chứng minh:
- Hai bean cùng kiểu làm constructor injection thất bại.
- `@Primary` chọn một implementation mặc định.
- `@Qualifier` chọn implementation theo vai trò.
- `@Fallback` giữ implementation dự phòng.
- Collection injection nhận cả hai implementation và tôn trọng `@Order`.
- `@ConditionalOnMissingBean` tạo default khi chưa có bean.
- Bean do người dùng cung cấp khiến auto-configuration default back off.
- `@ConditionalOnSingleCandidate` không đăng ký consumer khi có hai candidate ngang nhau, và match khi có một primary candidate.

Test dùng context độc lập, không cần database hoặc dịch vụ ngoài.

## 13. Chẩn đoán trong ứng dụng thật

Khi gặp lỗi, đi theo thứ tự sau để tìm đúng injection point và candidate.

### 13.1. Đọc kiểu bean và danh sách candidate trong exception

`NoUniqueBeanDefinitionException` cung cấp:
- `getBeanType()`: kiểu đang được yêu cầu.
- `getNumberOfBeansFound()`: số candidate tìm thấy.
- `getBeanNamesFound()`: tên bean được tìm thấy, nếu có.

Ví dụ:

~~~java
try {
    PaymentGateway gateway =
            applicationContext.getBean(PaymentGateway.class);
}
catch (NoUniqueBeanDefinitionException exception) {
    System.err.println("Type: " + exception.getBeanType());
    System.err.println("Count: " + exception.getNumberOfBeansFound());
    System.err.println("Beans: " + exception.getBeanNamesFound());
}
~~~

Trong ứng dụng thật, log nên dùng logger thay cho `System.err`.

### 13.2. Liệt kê bean name theo type

Có thể kiểm tra candidate bằng `ListableBeanFactory`:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(PaymentGateway.class);

for (String name : names) {
    System.out.println(name);
}
~~~

Kết quả ví dụ:

~~~text
stripeGateway
walletGateway
~~~

`getBeanNamesForType` giúp nhìn danh sách bean definition theo type. Tránh gọi `getBeansOfType` chỉ để chẩn đoán nếu bean có khởi tạo đắt tiền hoặc side effect, vì thao tác lấy instance có thể khiến bean được tạo.

### 13.3. Tìm injection point đang yêu cầu một bean

Kiểm tra stack trace để tìm:
- Constructor nào có tham số `PaymentGateway`.
- `@Bean` method nào có tham số cùng kiểu.
- Field/setter nào được đánh dấu autowire.
- Code nào gọi `getBean(PaymentGateway.class)`.

Không sửa mọi bean cùng kiểu chỉ vì thấy chúng trong danh sách. Cần xác định injection point nào thật sự cần một implementation.

### 13.4. Kiểm tra auto-configuration có tạo default trùng không

Nếu candidate gồm một bean do ứng dụng tạo và một bean từ starter:
1. Tìm `@Bean` method tạo default.
2. Kiểm tra `@ConditionalOnMissingBean` có được đặt đúng type không.
3. Kiểm tra return type của factory method có đủ thông tin không.
4. Kiểm tra thứ tự auto-configuration.
5. Kiểm tra user bean có được đăng ký trước condition hay không.

Với Spring Boot Actuator, endpoint `beans` có thể giúp xem bean đã đăng ký và endpoint `conditions` giúp hiểu condition của auto-configuration. Chỉ expose các endpoint cần thiết và bảo vệ chúng theo chính sách vận hành của ứng dụng.

Chạy ứng dụng với `--debug` cũng có thể hiển thị condition evaluation report. Report hữu ích để xác định auto-configuration nào match hoặc back off; nó không thay thế việc kiểm tra injection point và candidate cụ thể.

## 14. Những cách sửa dễ gây lỗi về sau

### 14.1. Không đổi tên bean ngẫu nhiên

Đổi tên `walletGateway` thành `walletGatewayV2` không giải quyết được ambiguity khi cả hai vẫn implement `PaymentGateway`.

Tên bean chỉ giúp chọn theo name khi injection point thực sự dùng name/qualifier hoặc `@Resource`.

### 14.2. Không dùng @Primary ở mọi nơi

Nếu mỗi implementation đều được đánh dấu `@Primary`, Spring vẫn không có một candidate primary duy nhất.

Nếu mỗi consumer cần một gateway khác nhau, dùng `@Qualifier` trên từng dependency.

### 14.3. Không bật bean overriding để chữa lỗi cùng type

Bean overriding giải quyết xung đột bean name. `NoUniqueBeanDefinitionException` phát sinh vì nhiều candidate cùng type. Hai vấn đề khác nhau.

### 14.4. Không dùng @Order để chọn một bean đơn trị

`@Order` phù hợp để sắp xếp collection injection. Nó không phải cách thay thế `@Primary` hoặc `@Qualifier` cho constructor cần một bean.

### 14.5. Không loại một bean bằng @Profile chỉ để test qua

`@Profile` nên phản ánh môi trường triển khai thật, ví dụ implementation chỉ tồn tại trong `dev` hoặc `production`. Nếu profile chỉ được thêm để tránh ambiguity trong test nhưng production vẫn có nhiều candidate, lỗi vẫn còn.

### 14.6. Không inject Optional<T> để mong tự chọn một bean

`Optional<PaymentGateway>` thể hiện dependency có thể vắng mặt. Nếu có nhiều candidate và không thể chọn một candidate duy nhất, Spring vẫn có thể báo ambiguity.

Dùng `ObjectProvider<T>`, collection hoặc registry khi cần xử lý nhiều candidate.

## 15. Ma trận lựa chọn giải pháp

| Tình huống | Cách phù hợp |
| --- | --- |
| Có một implementation mặc định cho toàn ứng dụng | `@Primary` |
| Mỗi service cần implementation khác nhau | `@Qualifier` |
| Một bean là lựa chọn dự phòng | `@Fallback` (Spring 6.2+) |
| Cần chọn bean bằng tên duy nhất | `@Resource(name = "...")` |
| Cần chạy qua tất cả implementation | `List<T>`, `T[]` hoặc `Map<String, T>` |
| Cần lấy bean theo nhu cầu | `ObjectProvider<T>` |
| Starter chỉ tạo default nếu ứng dụng chưa cung cấp | `@ConditionalOnMissingBean` |
| Auto-configuration chỉ cần một candidate phân giải được | `@ConditionalOnSingleCandidate` |
| Có nhiều implementation cùng generic interface | Dùng generic type làm qualifier khi phù hợp |
| Muốn sắp xếp các implementation trong collection | `@Order` |

## 16. Checklist khi xử lý NoUniqueBeanDefinitionException

1. Đọc root cause và xác định type đang được yêu cầu.
2. Ghi lại tên tất cả candidate mà exception cung cấp.
3. Tìm constructor, field, setter hoặc `@Bean` method đang yêu cầu một bean đơn trị.
4. Xác định nhiều implementation là có chủ đích hay là bean default bị tạo trùng.
5. Nếu cần một default chung, chọn đúng một `@Primary`.
6. Nếu từng consumer cần implementation riêng, dùng `@Qualifier`.
7. Nếu một implementation chỉ là dự phòng, cân nhắc `@Fallback` trên Spring Framework 6.2+.
8. Nếu cần tất cả implementation, chuyển sang `List`, `Map`, array hoặc `ObjectProvider`.
9. Nếu lỗi liên quan starter, kiểm tra `@ConditionalOnMissingBean`, return type và ordering.
10. Nếu auto-configuration chỉ hoạt động khi có một candidate duy nhất, dùng `@ConditionalOnSingleCandidate`.
11. Viết test cho cả trường hợp một bean, nhiều bean, primary, fallback và user override.
12. Chạy lại test và xác nhận đúng implementation được inject trong từng tình huống.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào Spring ném `NoUniqueBeanDefinitionException`?

**Đáp án:** Khi một điểm cần một bean duy nhất theo type nhưng có nhiều candidate phù hợp và không thể xác định một candidate thắng.

**Câu 2.** `@Primary` có loại các bean còn lại khỏi `List<PaymentGateway>` không?

**Đáp án:** Không. Collection injection vẫn nhận tất cả candidate phù hợp. `@Primary` chỉ tác động đến dependency đơn trị.

**Câu 3.** Khi nào nên dùng `@Qualifier`?

**Đáp án:** Khi một consumer cần implementation cụ thể theo vai trò hoặc đặc điểm, chẳng hạn gateway `card` hoặc `digital-wallet`.

**Câu 4.** `@Fallback` có từ phiên bản nào?

**Đáp án:** Spring Framework 6.2. Spring Boot 3.5 dùng Spring Framework 6.2 nên hỗ trợ annotation này.

**Câu 5.** `@ConditionalOnMissingBean` có tự giải quyết hai bean cùng type do ứng dụng khai báo không?

**Đáp án:** Không. Nó ngăn auto-configuration tạo default khi đã có bean phù hợp. Nếu ứng dụng tự đăng ký hai bean, injection đơn trị vẫn cần qualifier hoặc quy tắc chọn candidate.

**Câu 6.** `@ConditionalOnSingleCandidate` dùng để làm gì?

**Đáp án:** Chỉ bật một bean/configuration khi có thể xác định một candidate duy nhất, ví dụ một bean phù hợp hoặc nhiều bean nhưng có primary candidate.

**Câu 7.** `@Order` có chọn implementation cho constructor đơn trị không?

**Đáp án:** Không. `@Order` chủ yếu điều khiển thứ tự khi inject collection; dùng `@Primary` hoặc `@Qualifier` cho dependency đơn trị.

**Câu 8.** Nếu muốn chọn bean theo tên rõ ràng, nên cân nhắc annotation nào?

**Đáp án:** `@Resource(name = "...")` thể hiện ngữ nghĩa chọn theo bean name. Với constructor injection, `@Qualifier` trên tham số thường phù hợp hơn.

## 18. Tài liệu tham khảo chính thức

- Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with `@Primary` or `@Fallback`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html
- Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with Qualifiers: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html
- Spring Framework 6.2 — Using Generics as Autowiring Qualifiers: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/generics-as-qualifiers.html
- Spring Framework 6.2 API — `NoUniqueBeanDefinitionException`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/NoUniqueBeanDefinitionException.html
- Spring Framework 6.2 API — `Fallback`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Fallback.html
- Spring Boot 3.5 — Creating Your Own Auto-configuration, bean conditions và auto-configuration ordering: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `ConditionalOnSingleCandidate`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html
- Spring Boot 3.5 API — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
