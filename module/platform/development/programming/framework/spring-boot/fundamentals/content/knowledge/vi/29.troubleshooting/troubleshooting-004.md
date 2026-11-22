# NoUniqueBeanDefinitionException: nhiều ứng viên nhưng chưa có cách chọn

Spring thường inject dependency theo **kiểu dữ liệu**. Nếu một constructor yêu cầu `PaymentGateway`, container tìm các bean có thể gán cho kiểu đó rồi chọn một ứng viên phù hợp. Nhưng khi trong context có nhiều bean cùng đáp ứng yêu cầu mà không có quy tắc phân biệt, Spring không thể đoán ứng dụng muốn dùng bean nào.

Kết quả thường là `NoUniqueBeanDefinitionException`, đôi khi được bọc bên ngoài bởi `UnsatisfiedDependencyException` trong thông báo lỗi khởi động.

Ví dụ có hai implementation:

~~~java
public interface PaymentGateway {
    void charge(long amount);
}
~~~

~~~java
@Component
public class StripePaymentGateway implements PaymentGateway {
    @Override
    public void charge(long amount) {
        // Gọi Stripe.
    }
}
~~~

~~~java
@Component
public class BankPaymentGateway implements PaymentGateway {
    @Override
    public void charge(long amount) {
        // Gọi cổng thanh toán ngân hàng.
    }
}
~~~

Một service yêu cầu duy nhất một bean:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Nếu cả hai implementation đều được đăng ký và không có qualifier/primary hoặc quy tắc chọn khác phù hợp, Spring không biết nên inject `StripePaymentGateway` hay `BankPaymentGateway`.

**Đây là lỗi lựa chọn dependency khi có nhiều ứng viên**, không nhất thiết là lỗi tạo bean hoặc lỗi trùng tên bean. Cách sửa đúng phụ thuộc ý định thiết kế: chọn một bean mặc định, chỉ rõ qualifier, inject tất cả ứng viên, hoặc sửa cách đăng ký bean.

## 1. Hiểu exception và thông báo lỗi

`NoUniqueBeanDefinitionException` thuộc Spring Beans. Nó xảy ra khi một thao tác cần một bean duy nhất theo kiểu/tên hoặc điều kiện tra cứu nhưng có nhiều ứng viên phù hợp.

Một thông báo điển hình:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'com.example.PaymentGateway' available:
expected single matching bean but found 2:
stripePaymentGateway,bankPaymentGateway
~~~

Tên bean trong thông báo là manh mối quan trọng. Nó cho biết Spring đã tìm thấy những ứng viên nào.

Trong lúc khởi động, exception có thể xuất hiện bên trong chuỗi lỗi:

~~~text
ApplicationContext failed to start
  |
  v
UnsatisfiedDependencyException
  |
  v
NoUniqueBeanDefinitionException
  |
  v
PaymentGateway candidates:
  - stripePaymentGateway
  - bankPaymentGateway
~~~

`UnsatisfiedDependencyException` thường mô tả dependency của bean nào không thể được thỏa mãn. Root cause `NoUniqueBeanDefinitionException` cho biết lý do cụ thể là có nhiều bean phù hợp.

### Phân biệt với các lỗi gần giống

| Exception | Ý nghĩa | Ví dụ |
|---|---|---|
| `NoSuchBeanDefinitionException` | Không tìm thấy bean phù hợp | Không có bean nào implement `PaymentGateway` |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp nhưng cần một bean duy nhất | Có Stripe và Bank gateway, constructor chỉ nhận một gateway |
| `UnsatisfiedDependencyException` | Không thể giải quyết dependency khi tạo bean | Constructor của `CheckoutService` không được cung cấp dependency |
| `BeanDefinitionOverrideException` | Một bean definition trùng tên bị đăng ký trong khi override không được cho phép | Hai cấu hình cùng khai báo bean name `paymentGateway` |

Lưu ý: `NoUniqueBeanDefinitionException` là một dạng lỗi tra cứu bean không duy nhất và có quan hệ kế thừa với `NoSuchBeanDefinitionException`. Khi xem log, hãy tìm exception sâu nhất và danh sách candidate names thay vì chỉ đọc dòng đầu tiên.

## 2. Vì sao Spring tìm thấy nhiều bean?

Một bean có thể được đăng ký từ nhiều nguồn:

- `@Component`, `@Service`, `@Repository` hoặc `@Controller` được component scan phát hiện.
- Phương thức `@Bean` trong một class `@Configuration`.
- `@Import` một configuration class hoặc component.
- Auto-configuration từ Spring Boot starter.
- Cấu hình test như `@MockBean` (ở các dòng Spring Boot tương ứng) hoặc bean test tự khai báo.
- Một module tích hợp đăng ký implementation mặc định của interface.

Ví dụ hai cách đăng ký cùng xuất hiện:

~~~java
@Component
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway bankPaymentGateway() {
        return new BankPaymentGateway();
    }
}
~~~

Cả hai bean đều là ứng viên cho `PaymentGateway`. Điều này có thể hoàn toàn có chủ đích: ứng dụng hỗ trợ nhiều nhà cung cấp. Lỗi chỉ xảy ra khi một điểm injection yêu cầu đúng một bean mà không xác định được lựa chọn.

### 2.1. Hai bean khác tên không phải là duplicate bean name

Ví dụ:

- `stripePaymentGateway`
- `bankPaymentGateway`

Đây là hai bean definitions riêng biệt với hai tên khác nhau. Spring cho phép chúng cùng tồn tại.

Nếu hai configuration classes cùng khai báo bean name `paymentGateway`, đó lại là câu chuyện trùng tên/override bean definition. Không nên xử lý `NoUniqueBeanDefinitionException` bằng cách bật bean overriding; hai vấn đề có nguyên nhân khác nhau.

### 2.2. Component scan quá rộng

Một module có thể vô tình được scan hai lần hoặc cả hai implementation đều được phát hiện từ những package khác nhau. Cần xác định xem cả hai bean có thực sự cần thiết không.

Nếu chỉ muốn một implementation, hãy sửa phạm vi scan/import hoặc loại bỏ đăng ký thừa. Nếu cả hai đều có mục đích, hãy giữ chúng và chỉ rõ cách chọn ở nơi sử dụng.

## 3. Cách 1: @Primary chọn bean mặc định

Nếu ứng dụng có nhiều implementation nhưng một implementation được dùng **mặc định trong phần lớn trường hợp**, đánh dấu bean đó bằng `@Primary`.

~~~java
@Component
@Primary
public class StripePaymentGateway implements PaymentGateway {

    @Override
    public void charge(long amount) {
        // Gọi Stripe.
    }
}
~~~

Implementation còn lại không cần thay đổi:

~~~java
@Component
public class BankPaymentGateway implements PaymentGateway {

    @Override
    public void charge(long amount) {
        // Gọi ngân hàng.
    }
}
~~~

Constructor ban đầu giờ có thể được giải quyết:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Khi Spring cần một dependency đơn kiểu `PaymentGateway`, `StripePaymentGateway` được ưu tiên vì nó là primary candidate.

### 3.1. Đặt @Primary trên @Bean

Có thể đánh dấu bean factory method:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Primary
    PaymentGateway defaultPaymentGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    PaymentGateway bankPaymentGateway() {
        return new BankPaymentGateway();
    }
}
~~~

`@Primary` có thể đặt trên component class hoặc bean definition method. Khi dùng `@Bean`, annotation gắn với bean được đăng ký bởi phương thức đó.

### 3.2. @Primary không xóa các bean khác

Sau khi đánh dấu primary:

- Cả Stripe và Bank vẫn tồn tại trong context.
- Có thể inject bean Bank bằng qualifier.
- Có thể inject danh sách tất cả gateway.
- `@Primary` chỉ giúp chọn một candidate trong những điểm cần một dependency đơn mà không có chỉ dẫn cụ thể hơn.

Đừng hiểu `@Primary` là “bean duy nhất được đăng ký” hoặc “các bean còn lại bị vô hiệu hóa”.

### 3.3. Chỉ nên có một primary cho một tập ứng viên

Nếu hai bean cùng kiểu đều được đánh dấu `@Primary`, Spring vẫn không có một lựa chọn duy nhất:

~~~java
@Component
@Primary
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
@Primary
class BankPaymentGateway implements PaymentGateway {
}
~~~

Constructor cần `PaymentGateway` vẫn có thể thất bại vì có nhiều primary candidate ngang nhau. Hãy bỏ primary thừa hoặc dùng qualifier ở điểm injection để thể hiện ý định cụ thể.

### 3.4. @Primary không ảnh hưởng collection injection

Nếu constructor yêu cầu:

~~~java
public PaymentCoordinator(List<PaymentGateway> gateways) {
    this.gateways = gateways;
}
~~~

Spring đưa các bean phù hợp vào list, bao gồm cả primary và non-primary. `@Primary` không có nghĩa chỉ một bean được đưa vào collection.

Đây là điểm quan trọng khi một ứng dụng vừa có default gateway, vừa cần liệt kê tất cả gateway để chọn theo runtime.

## 4. Cách 2: @Qualifier chỉ rõ bean cần inject

Nếu một service phải dùng một implementation cụ thể, `@Qualifier` diễn đạt ý định rõ hơn việc thay đổi primary toàn ứng dụng.

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("bankPaymentGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Spring thu hẹp tập candidate theo qualifier. Trong ví dụ này, dependency nhận bean có qualifier phù hợp với `bankPaymentGateway`.

Tên bean mặc định của component thường là tên class viết thường chữ đầu, vì vậy `BankPaymentGateway` thường được đặt tên `bankPaymentGateway`. Nếu tên bean được tùy chỉnh, hãy dùng đúng tên đã đăng ký.

### 4.1. @Qualifier trên component class

Có thể gắn qualifier có ý nghĩa lên implementation:

~~~java
@Component
@Qualifier("bank")
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Qualifier("card")
public class StripePaymentGateway implements PaymentGateway {
    // ...
}
~~~

Injection:

~~~java
@Service
public class BankTransferService {

    private final PaymentGateway gateway;

    public BankTransferService(
            @Qualifier("bank") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

`bank` và `card` là các qualifier labels. Cách đặt tên theo vai trò hoặc capability thường dễ hiểu hơn phụ thuộc trực tiếp vào tên class implementation.

### 4.2. @Qualifier trên @Bean method

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Qualifier("card")
    PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    @Qualifier("bank")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
~~~

Service có thể yêu cầu `@Qualifier("card")` hoặc `@Qualifier("bank")`.

### 4.3. Qualifier không nhất thiết chỉ là bean name

Giá trị `@Qualifier` thường được dùng như một nhãn để lọc ứng viên. Tên bean có thể tham gia như một giá trị fallback phù hợp, nhưng không nên thiết kế hệ thống lớn bằng cách buộc mọi nơi phụ thuộc vào tên bean nội bộ.

Ví dụ, nhiều bean có thể cùng mang qualifier `"external"` nếu chúng cùng thuộc một nhóm. Khi đó qualifier biểu đạt một đặc tính, và có thể còn nhiều ứng viên trong nhóm; cần thêm tiêu chí khác nếu injection cần đúng một bean.

### 4.4. @Primary và @Qualifier kết hợp thế nào?

- `@Qualifier` giới hạn candidate theo nhãn/điều kiện phù hợp.
- `@Primary` chọn candidate mặc định trong tập ứng viên còn lại khi cần một bean đơn.
- Nếu qualifier không khớp bất kỳ bean nào, Spring không thể thỏa dependency.
- Nếu qualifier khớp nhiều bean và không có quy tắc chọn duy nhất, ambiguity vẫn có thể còn.

Khi service biết rõ cần Bank gateway, dùng `@Qualifier("bank")` là ý định trực tiếp. Đừng đánh dấu Bank làm primary chỉ để sửa một injection cụ thể nếu các service khác vẫn phải mặc định dùng Stripe.

## 5. Tạo custom qualifier annotation

Với hệ thống có nhiều loại gateway, chuỗi literal có thể bị lặp lại và khó refactor. Spring cho phép tạo annotation qualifier riêng.

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import org.springframework.beans.factory.annotation.Qualifier;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Qualifier
public @interface BankChannel {
}
~~~

Đăng ký implementation:

~~~java
@Component
@BankChannel
public class BankPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Injection:

~~~java
@Service
public class BankTransferService {

    private final PaymentGateway gateway;

    public BankTransferService(@BankChannel PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Custom qualifier giúp ý nghĩa của dependency trở nên rõ ràng trong code và hạn chế typo ở nhiều chuỗi. Với qualifier có thuộc tính, có thể mô tả thêm capability hoặc tenant category theo quy ước của ứng dụng.

Ví dụ annotation có thuộc tính:

~~~java
@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.TYPE,
        ElementType.METHOD
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface PaymentChannel {
    String value();
}
~~~

~~~java
@Component
@PaymentChannel("bank")
class BankPaymentGateway implements PaymentGateway {
}
~~~

~~~java
public CheckoutService(
        @PaymentChannel("bank") PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Custom qualifier không tạo một bean mới; nó chỉ cung cấp metadata để Spring lọc các bean đã đăng ký.

## 6. Cách 3: @Resource khi muốn inject theo tên

`@Autowired` thường giải quyết dependency theo kiểu, sau đó có thể dùng qualifier/primary để chọn. `@Resource` có semantics thiên về **tên bean**.

Ví dụ với Spring Boot 3:

~~~java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    @Resource(name = "bankPaymentGateway")
    private PaymentGateway gateway;
}
~~~

Với dòng Spring Boot 2 sử dụng Java EE namespace cũ, import thường là `javax.annotation.Resource` và cần dependency annotation tương ứng nếu JDK không cung cấp.

`@Resource(name = "...")` diễn đạt rõ rằng field/property cần bean theo tên đó. Đây là lựa chọn hữu ích khi tên bean là một phần chủ đích của wiring.

### 6.1. @Resource khác @Qualifier

| Cơ chế | Trọng tâm |
|---|---|
| `@Autowired` | Tìm dependency theo type |
| `@Autowired + @Qualifier` | Tìm theo type rồi lọc theo qualifier |
| `@Primary` | Đánh dấu candidate ưu tiên cho dependency đơn |
| `@Resource(name = "...")` | Yêu cầu bean theo tên đã chỉ định |

Không cần đổi toàn bộ constructor injection sang field injection chỉ để sử dụng `@Resource`. Với dependency bắt buộc, constructor injection thường giúp thể hiện rõ dependency và hỗ trợ test tốt hơn. Có thể dùng `@Resource` trên setter hoặc field khi phù hợp với kiến trúc hiện có.

## 7. Parameter name matching: tên tham số có thể giúp chọn bean

Trong một số trường hợp, Spring có thể dùng **tên tham số constructor/method** làm fallback để phân biệt candidate, nếu tên tham số khớp với tên bean.

Ví dụ:

~~~java
@Component("stripeGateway")
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component("bankGateway")
class BankPaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Service
class CheckoutService {

    private final PaymentGateway bankGateway;

    CheckoutService(PaymentGateway bankGateway) {
        this.bankGateway = bankGateway;
    }
}
~~~

Khi metadata tên tham số được giữ trong bytecode và các điều kiện resolution phù hợp, Spring có thể dùng tên `bankGateway` để chọn bean cùng tên.

### 7.1. Cần metadata tên tham số

Với các dòng Spring hiện đại, việc dùng parameter name matching phụ thuộc metadata tham số được giữ khi compile; với Java, thường cần compiler option `-parameters`.

Gradle Java:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Maven compiler plugin:

~~~xml
<configuration>
    <parameters>true</parameters>
</configuration>
~~~

Tùy phiên bản Spring và build setup, khả năng matching và thứ tự fallback có thể khác nhau. Đây là một tiện ích hỗ trợ resolution, **không nên thay thế qualifier tường minh cho dependency có ý nghĩa kiến trúc**.

### 7.2. Vì sao không nên dựa hoàn toàn vào tên tham số?

Đổi tên biến/parameter trong refactor có thể làm thay đổi cách chọn bean. Nếu dependency phải là Bank gateway vì yêu cầu nghiệp vụ, `@Qualifier("bank")` hoặc custom qualifier biểu đạt ý định rõ hơn.

Tên tham số phù hợp như một fallback trong những trường hợp đơn giản, không phải hợp đồng wiring duy nhất cho một ứng dụng có nhiều implementation.

## 8. Spring Framework 6.2+: @Fallback

Từ Spring Framework 6.2 (được dùng trong các dòng Spring Boot hiện đại tương ứng, ví dụ Boot 3.4+), có annotation `@Fallback` để đánh dấu bean dự phòng.

Ví dụ:

~~~java
import org.springframework.context.annotation.Fallback;
import org.springframework.stereotype.Component;

@Component
@Fallback
public class NoopNotificationSender implements NotificationSender {

    @Override
    public void send(String message) {
        // Không gửi thật; implementation dự phòng.
    }
}
~~~

Implementation thông thường:

~~~java
@Component
public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(String message) {
        // Gửi email.
    }
}
~~~

Nếu có một candidate không phải fallback và các candidate fallback khác, bean thông thường được ưu tiên cho dependency đơn. Fallback beans vẫn được đăng ký và có thể được inject theo qualifier hoặc lấy qua collection.

### 8.1. @Fallback khác @Primary

| Annotation | Ý nghĩa |
|---|---|
| `@Primary` | Đánh dấu bean được ưu tiên trong số các candidate |
| `@Fallback` | Đánh dấu bean dự phòng, nhường lựa chọn cho candidate thông thường |
| `@Qualifier` | Lọc candidate theo nhãn/metadata cụ thể |

Không nên gắn `@Primary` và `@Fallback` một cách mâu thuẫn lên cùng một bean. Nếu tất cả ứng viên đều fallback mà vẫn có nhiều bean cùng kiểu, vẫn cần quy tắc chọn rõ ràng.

`@Fallback` không có mặt ở các phiên bản Spring Framework cũ. Nếu dự án dùng Spring Boot 3.3 trở xuống hoặc dòng Framework chưa hỗ trợ, hãy dùng `@Primary`/`@Qualifier` phù hợp với version thay vì copy import không tồn tại.

## 9. @Order không giải quyết ambiguity cho một dependency đơn

Một hiểu nhầm phổ biến là đánh dấu:

~~~java
@Component
@Order(1)
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
@Order(2)
class BankPaymentGateway implements PaymentGateway {
}
~~~

rồi mong Spring tự chọn Stripe khi constructor yêu cầu:

~~~java
CheckoutService(PaymentGateway gateway) {
}
~~~

`@Order` chủ yếu điều khiển thứ tự các bean trong những điểm injection dạng collection/array/stream hoặc những cơ chế ordering phù hợp. Nó **không phải cách tiêu chuẩn để chọn một bean duy nhất** trong một dependency đơn.

Nếu cần default, dùng `@Primary`. Nếu cần một implementation cụ thể, dùng `@Qualifier`. Nếu cần tất cả implementation theo thứ tự, inject collection và dùng `@Order`.

Ví dụ:

~~~java
@Service
class PaymentCoordinator {

    private final List<PaymentGateway> gateways;

    PaymentCoordinator(List<PaymentGateway> gateways) {
        this.gateways = gateways;
    }
}
~~~

Các bean có `@Order` có thể được sắp xếp trong list theo thứ tự đó.

## 10. Cách 4: Inject tất cả ứng viên bằng List, Set hoặc array

Nếu ứng dụng thực sự cần nhiều implementation, đừng ép Spring chọn một bean đơn. Hãy yêu cầu collection:

~~~java
@Service
public class PaymentCoordinator {

    private final List<PaymentGateway> gateways;

    public PaymentCoordinator(List<PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public void chargeAll(long amount) {
        for (PaymentGateway gateway : gateways) {
            gateway.charge(amount);
        }
    }
}
~~~

Spring có thể inject tất cả bean phù hợp với `PaymentGateway` vào collection.

Các dạng thường dùng:

~~~java
PaymentCoordinator(List<PaymentGateway> gateways)
~~~

~~~java
PaymentCoordinator(Set<PaymentGateway> gateways)
~~~

~~~java
PaymentCoordinator(PaymentGateway[] gateways)
~~~

Collection injection không yêu cầu một bean duy nhất, nên tránh được kiểu ambiguity của dependency đơn.

### 10.1. Inject Map để dùng bean name làm key

~~~java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentGateway getGateway(String name) {
        PaymentGateway gateway = gateways.get(name);

        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unknown payment gateway: " + name);
        }

        return gateway;
    }
}
~~~

Với injection dạng map, key thường là bean name và value là bean instance. Ví dụ có thể dùng `stripePaymentGateway` hoặc `bankPaymentGateway` làm key.

Không nên để client HTTP truyền trực tiếp bean name tùy ý rồi gọi map lookup mà không có allowlist/authorization. Bean name là chi tiết nội bộ của ứng dụng, không phải API public hay cơ chế phân quyền.

### 10.2. Chọn theo business key thay vì bean name

Nếu runtime cần chọn gateway theo payment method, có thể thiết kế interface:

~~~java
public interface PaymentGateway {
    PaymentMethod supports();
    void charge(long amount);
}
~~~

Sau đó xây registry từ danh sách bean:

~~~java
@Component
public class PaymentGatewayRegistry {

    private final Map<PaymentMethod, PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> candidates) {
        this.gateways = candidates.stream()
                .collect(Collectors.toUnmodifiableMap(
                        PaymentGateway::supports,
                        Function.identity()
                ));
    }

    public PaymentGateway get(PaymentMethod method) {
        PaymentGateway gateway = gateways.get(method);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment method: " + method);
        }
        return gateway;
    }
}
~~~

Ví dụ này chủ động chuyển từ “Spring chọn một bean khi khởi động” sang “ứng dụng chọn implementation theo business key lúc chạy”. Nếu hai gateway khai báo cùng một `PaymentMethod`, `toUnmodifiableMap` sẽ thất bại khi tạo registry; đó là tín hiệu cần xử lý duplicate business mapping thay vì che giấu.

## 11. Cách 5: ObjectProvider khi lựa chọn hoặc truy cập cần trì hoãn

`ObjectProvider<T>` cho phép truy vấn bean theo nhu cầu thay vì inject trực tiếp một instance ngay trong constructor.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OptionalReportService {

    private final ObjectProvider<ReportExporter> exporters;

    public OptionalReportService(
            ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void exportIfAvailable() {
        ReportExporter exporter = exporters.getIfAvailable();

        if (exporter != null) {
            exporter.export();
        }
    }
}
~~~

Các API hữu ích:

| API | Hành vi khái quát |
|---|---|
| `getObject()` | Lấy bean; lỗi nếu không thể resolve duy nhất |
| `getIfAvailable()` | Trả null nếu không có bean; vẫn có thể ném lỗi nếu nhiều ứng viên không phân biệt được |
| `getIfUnique()` | Trả bean nếu có một candidate duy nhất có thể chọn; trả null nếu không có hoặc không unique |
| `stream()` | Duyệt các candidate |
| `orderedStream()` | Duyệt candidate theo thứ tự phù hợp với ordering |

`ObjectProvider` không tự giải quyết ambiguity bằng cách đoán. Nó cung cấp API để ứng dụng quyết định hành vi khi không có hoặc có nhiều candidate.

### 11.1. Optional không phải cách chọn giữa nhiều bean

Ví dụ:

~~~java
public CheckoutService(Optional<PaymentGateway> gateway) {
}
~~~

`Optional<PaymentGateway>` thể hiện dependency có thể không tồn tại. Nếu có hai bean phù hợp và không có cách chọn, `Optional` không làm chúng trở thành một bean duy nhất; ambiguity vẫn có thể xảy ra.

Dùng `Optional` cho tính optionality, `ObjectProvider` cho truy vấn linh hoạt và `@Qualifier`/`@Primary` cho việc chọn bean.

## 12. Dùng generic type để phân biệt các bean cùng raw interface

Spring có thể sử dụng generic type làm một phần metadata để thu hẹp candidate.

Ví dụ:

~~~java
public interface MessageHandler<T> {
    void handle(T message);
}
~~~

~~~java
@Component
class OrderMessageHandler implements MessageHandler<OrderMessage> {
    @Override
    public void handle(OrderMessage message) {
    }
}
~~~

~~~java
@Component
class InvoiceMessageHandler implements MessageHandler<InvoiceMessage> {
    @Override
    public void handle(InvoiceMessage message) {
    }
}
~~~

Dependency yêu cầu:

~~~java
@Service
class OrderProcessor {

    private final MessageHandler<OrderMessage> handler;

    OrderProcessor(MessageHandler<OrderMessage> handler) {
        this.handler = handler;
    }
}
~~~

Spring có thể dùng generic metadata để chọn `OrderMessageHandler` thay vì `InvoiceMessageHandler`, miễn là kiểu generic được giữ và có thể phân giải từ bean definitions/classes.

Đây là một dạng **generic qualifier**. Nó hữu ích khi interface được thiết kế theo kiểu dữ liệu xử lý, ví dụ `Repository<User>` và `Repository<Order>`.

Tuy nhiên, nếu generic bị xóa/không thể suy luận qua raw types, factory method hoặc cấu trúc inheritance phức tạp, việc lọc có thể không đạt như mong đợi. Khi đó hãy khai báo kiểu trả về cụ thể hơn hoặc dùng qualifier tường minh.

## 13. Khi nào nên sửa bean registration thay vì thêm qualifier?

Không phải mọi ambiguity đều nên giải quyết bằng cách thêm `@Primary` hoặc `@Qualifier`. Trước hết hãy xác định vì sao nhiều bean xuất hiện.

### Trường hợp A: Chỉ cần một implementation

Nếu ứng dụng chỉ dùng một gateway, nhưng cả component và configuration đều đăng ký cùng một implementation hoặc một implementation không cần thiết, hãy xóa đăng ký dư thừa.

Ví dụ sai thiết kế:

~~~java
@Component
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }
}
~~~

Cùng một logic Stripe được đăng ký hai lần dưới hai bean names. Nếu không có nhu cầu hai instance độc lập, chỉ giữ một cơ chế đăng ký.

### Trường hợp B: Hai implementation là hợp lệ

Nếu ứng dụng thật sự hỗ trợ nhiều nhà cung cấp, giữ cả hai. Dùng qualifier hoặc registry để chọn theo nhu cầu.

### Trường hợp C: Bean mặc định của starter bị trùng với bean người dùng

Một starter nên cung cấp implementation mặc định có điều kiện:

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

Nếu ứng dụng đã cung cấp một bean `PaymentGateway`, auto-configuration mặc định sẽ back off theo condition.

Nhưng nếu ứng dụng chủ động cung cấp **hai** bean `PaymentGateway`, condition “missing bean” đã không còn đúng; default bean sẽ không được tạo, song hai bean của ứng dụng vẫn tồn tại và một injection đơn vẫn có thể ambiguity.

`@ConditionalOnMissingBean` tránh tạo default không cần thiết; nó **không tự chọn giữa nhiều bean do ứng dụng khai báo**.

### Trường hợp D: Nhiều profile hoặc config import làm đăng ký trùng

Kiểm tra `@Profile`, `@ConditionalOnProperty`, `@Import` và component scanning. Một implementation chỉ nên được đăng ký trong những môi trường mà nó có ý nghĩa.

Không dùng profile để che giấu lỗi nếu ứng dụng production vẫn thực sự cần hai implementation. Profile chỉ là điều kiện kích hoạt cấu hình, không phải quy tắc chọn bean tại từng injection point.

## 14. Bean name, qualifier và primary: chọn theo ý định

Ví dụ một ứng dụng có hai gateway:

~~~java
@Component("cardGateway")
@Qualifier("external")
class StripePaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component("bankGateway")
@Qualifier("domestic")
class BankPaymentGateway implements PaymentGateway {
}
~~~

Service cần cổng trong nước:

~~~java
@Service
class DomesticCheckoutService {

    private final PaymentGateway gateway;

    DomesticCheckoutService(
            @Qualifier("domestic") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Service cần gateway external:

~~~java
@Service
class InternationalCheckoutService {

    private final PaymentGateway gateway;

    InternationalCheckoutService(
            @Qualifier("external") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Một service khác có thể inject tất cả:

~~~java
@Service
class PaymentDiagnostics {

    PaymentDiagnostics(List<PaymentGateway> gateways) {
        // Quan sát hoặc điều phối tất cả implementation.
    }
}
~~~

Cách tổ chức này biểu đạt rõ:

- Bean name là định danh đăng ký trong container.
- Qualifier là nhãn lựa chọn theo vai trò.
- Primary là mặc định khi cần một bean đơn.
- Collection là cách lấy nhiều ứng viên.

Đừng chọn một trong các cơ chế này chỉ vì nó làm startup chạy được. Hãy chọn theo hợp đồng của service.

## 15. Constructor injection giúp phát hiện ambiguity sớm

Constructor injection thường được khuyến nghị cho dependency bắt buộc:

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Nếu Spring không giải quyết được dependency, context thường thất bại ngay lúc tạo bean, thay vì service được tạo với một field chưa được inject.

Với một constructor duy nhất, Spring thường không cần `@Autowired` trên constructor:

~~~java
@Service
class CheckoutService {

    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Nếu có nhiều constructor, cần xem quy tắc lựa chọn constructor và annotation tương ứng. Nhưng dù dùng field, setter hay constructor injection, **nhiều candidate cho một dependency đơn vẫn cần được phân biệt**.

### 15.1. Đừng dùng @Autowired(required = false) để che ambiguity

~~~java
@Autowired(required = false)
private PaymentGateway gateway;
~~~

`required=false` cho phép dependency không có mặt trong một số trường hợp. Nó không phải quy tắc chọn một trong hai bean cùng kiểu. Nếu có nhiều ứng viên không phân biệt được, ambiguity vẫn cần được xử lý.

## 16. Chẩn đoán từ exception: đọc tên candidate trước

Khi ứng dụng báo:

~~~text
expected single matching bean but found 3:
stripePaymentGateway,bankPaymentGateway,mockPaymentGateway
~~~

Hãy lần theo các tên này:

1. Tìm class hoặc method khai báo bean.
2. Xác định bean được tạo từ `@Component`, `@Bean`, import hay auto-configuration.
3. Kiểm tra mỗi bean có thực sự cần tồn tại trong profile hiện tại không.
4. Xác định injection point cần một bean hay tất cả.
5. Chọn qualifier/primary/registry hoặc sửa đăng ký dư thừa.

Tên bean có thể là tên method `@Bean`, tên component hoặc tên tùy chỉnh. Không giả định tất cả đều được tạo theo tên class.

### 16.1. Dùng ApplicationContext để liệt kê bean theo type

Trong một test hoặc đoạn diagnostics có quyền truy cập context:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(PaymentGateway.class);

for (String name : names) {
    System.out.println(name);
}
~~~

Để xem bean instance theo type:

~~~java
Map<String, PaymentGateway> candidates =
        applicationContext.getBeansOfType(PaymentGateway.class);
~~~

Các API này hữu ích để xác nhận container đang có những ứng viên nào. Tránh ghi toàn bộ object hoặc field nhạy cảm của bean ra log.

### 16.2. Actuator beans endpoint

Nếu Actuator được cài đặt và endpoint `beans` được expose theo chính sách phù hợp, nó có thể giúp quan sát bean names và context ownership.

Không expose endpoint diagnostics rộng ra Internet chỉ để debug ambiguity. Ưu tiên test/log nội bộ hoặc môi trường development được bảo vệ.

### 16.3. Condition Evaluation Report

Với auto-configuration, chạy ứng dụng với `--debug` có thể hiển thị Condition Evaluation Report để hiểu cấu hình nào match hoặc back off.

Báo cáo giúp trả lời vì sao một auto-configuration đã tạo hoặc không tạo bean. Nó không tự giải quyết ambiguity giữa các bean người dùng đã đăng ký.

## 17. Kiểm thử lựa chọn bean với ApplicationContextRunner

Một integration test nhỏ giúp xác nhận `@Primary` và `@Qualifier` thực sự được wiring như mong đợi.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

class PaymentGatewayWiringTest {

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {

        @Bean
        @Primary
        PaymentGateway stripeGateway() {
            return new StripePaymentGateway();
        }

        @Bean
        @Qualifier("bank")
        PaymentGateway bankGateway() {
            return new BankPaymentGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway gateway) {
            return new CheckoutService(gateway);
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void primaryGatewayIsInjectedByDefault() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();

            CheckoutService service =
                    context.getBean(CheckoutService.class);

            assertThat(service.gateway())
                    .isInstanceOf(StripePaymentGateway.class);
        });
    }
}
~~~

Ví dụ giả định `CheckoutService` có accessor `gateway()` phục vụ test, và hai implementation có thể được khởi tạo trong test. Có thể thay bằng assertion trên một hành vi quan sát được nếu không muốn mở accessor chỉ để kiểm thử.

### 17.1. Kiểm thử qualifier cụ thể

~~~java
@Bean
BankTransferService bankTransferService(
        @Qualifier("bank") PaymentGateway gateway) {
    return new BankTransferService(gateway);
}
~~~

Sau đó xác nhận bean được inject là `BankPaymentGateway`.

### 17.2. Kiểm thử trường hợp vẫn ambiguity

Có thể bỏ `@Primary` và khai báo service yêu cầu một `PaymentGateway`. Test context nên thất bại và root cause là `NoUniqueBeanDefinitionException`.

~~~java
runner.run(context -> {
    assertThat(context).hasFailed();
    assertThat(context.getStartupFailure())
            .hasRootCauseInstanceOf(
                    NoUniqueBeanDefinitionException.class);
});
~~~

Đây là cách kiểm thử cấu hình wiring. Không nên chỉ unit test constructor Java vì constructor có thể tạo object bình thường mà không đi qua Spring container.

## 18. Kiểm thử collection injection

Nếu service cần tất cả implementations:

~~~java
@Service
public class GatewayRegistry {

    private final List<PaymentGateway> gateways;

    public GatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public int size() {
        return gateways.size();
    }
}
~~~

Test:

~~~java
@Test
void injectsAllPaymentGateways() {
    runner.run(context -> {
        assertThat(context).hasNotFailed();

        GatewayRegistry registry =
                context.getBean(GatewayRegistry.class);

        assertThat(registry.size()).isEqualTo(2);
    });
}
~~~

Test này xác nhận ứng dụng đang yêu cầu nhiều candidate thay vì một candidate duy nhất.

Nếu thứ tự có ý nghĩa, đánh dấu các implementation bằng `@Order` hoặc dùng cơ chế ordering phù hợp và kiểm thử thứ tự. Không dựa vào thứ tự ngẫu nhiên từ component scan.

## 19. Một số tình huống đặc biệt

### 19.1. Hai bean cùng tên nhưng khác type

Bean name là duy nhất trong một bean registry theo quy tắc đăng ký. Nếu hai cấu hình cùng khai báo một tên, có thể xảy ra lỗi override hoặc hành vi phụ thuộc thiết lập cho phép override. Đây không phải cùng một vấn đề với hai bean khác tên nhưng cùng type.

### 19.2. Parent-child ApplicationContext

Trong context hierarchy, bean ở child có thể nhìn thấy bean từ parent theo quy tắc lookup. Nếu cùng một type xuất hiện ở nhiều context, việc phân giải dependency có thể liên quan đến local candidate và ancestor candidate. Hãy kiểm tra chính context đang tạo bean và API lookup cụ thể, không chỉ đếm bean trên toàn JVM.

Nếu nhiều child cùng khai báo một implementation, chúng không tự nhìn thấy bean của sibling. Parent cũng không nhìn xuống child. Do đó, việc đếm candidate phải xét đúng context hierarchy.

### 19.3. Bean được tạo có điều kiện

Một bean có thể chỉ xuất hiện khi property hoặc classpath thỏa condition:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "provider",
        havingValue = "bank"
)
PaymentGateway bankGateway() {
    return new BankPaymentGateway();
}
~~~

Nếu nhiều condition cùng match, nhiều implementation có thể xuất hiện. Kiểm tra active profiles và property sources khi candidate list khác nhau giữa local/test/production.

### 19.4. Test thêm mock bean

Test có thể đăng ký mock thay cho bean thật nhưng vẫn giữ implementation thật trong context, khiến hai candidate cùng tồn tại. Khi dùng cơ chế mock bean của phiên bản Spring Boot tương ứng, hãy xác nhận mock đang **replace** bean đúng tên/type hay đang tạo thêm một bean mới.

Test slice và test context có cấu hình import khác nhau nên danh sách candidate có thể khác ứng dụng production.

## 20. Quy trình xử lý NoUniqueBeanDefinitionException

Khi gặp lỗi, thực hiện theo thứ tự:

~~~text
NoUniqueBeanDefinitionException
          |
          v
Đọc type và candidate names trong message
          |
          v
Tìm nơi đăng ký từng bean
          |
          v
Các implementation có cùng tồn tại là chủ đích?
          |
      +---+---+
      |       |
     Không    Có
      |       |
      v       v
Bỏ đăng ký  Injection cần một bean
thừa?        hay tất cả bean?
              |
          +---+---+
          |       |
         Một     Nhiều
          |       |
          v       v
     @Primary /   List / Set / Map /
     @Qualifier  ObjectProvider / Registry
          |
          v
Viết integration test xác nhận wiring
          |
          v
Chạy lại ứng dụng trong đúng profile/context
~~~

### Checklist chẩn đoán

- Đọc root cause, không chỉ exception bọc ngoài.
- Ghi lại toàn bộ candidate names.
- Tìm từng bean definition và nguồn đăng ký.
- Kiểm tra component scan, `@Import`, `@Bean` và auto-configuration.
- Xác nhận injection point thực sự cần một bean hay nhiều bean.
- Nếu một bean mặc định, chọn `@Primary` hoặc `@Fallback` phù hợp version.
- Nếu một implementation cụ thể, dùng `@Qualifier` hoặc `@Resource(name=...)`.
- Nếu cần runtime selection, inject collection và tạo registry theo business key.
- Kiểm tra profile/conditions và context hierarchy.
- Viết test context xác nhận đúng implementation được inject.

## 21. Những cách sửa nên tránh

**Bật bean definition overriding để xử lý ambiguity.** Override xử lý tên bean trùng, trong khi NoUnique thường do nhiều bean khác tên cùng thỏa một kiểu. Bật override không tạo ra quy tắc chọn đúng dependency.

**Đổi tên class cho đến khi Spring chỉ tìm thấy một bean.** Tên class không phải công cụ lựa chọn dependency theo kiểu. Nếu cả hai implementation vẫn được scan, chúng vẫn là candidate.

**Đánh dấu tất cả implementation bằng @Primary.** Khi có nhiều primary, vấn đề không được giải quyết. Chỉ đánh dấu một default có chủ đích hoặc dùng qualifier.

**Dùng @Order để chọn một bean đơn.** Ordering chủ yếu dành cho collection/ordered processing; nó không thay cho @Primary hoặc @Qualifier.

**Dùng Optional để che lỗi.** Optional thể hiện dependency có thể vắng mặt, không chọn một bean giữa nhiều candidate.

**Bắt exception rồi lấy đại một bean đầu tiên.** Thứ tự candidate không phải hợp đồng business. Lấy phần tử đầu có thể thay đổi khi thêm dependency hoặc refactor package.

**Dùng @Lazy để che ambiguity.** Lazy trì hoãn việc khởi tạo/resolve, không tạo ra một quy tắc lựa chọn ổn định. Lỗi có thể chỉ xuất hiện khi bean được sử dụng.

**Dùng ApplicationContext.getBean(type) rải rác trong business code.** Điều đó chuyển lỗi wiring từ startup sang runtime và làm dependency ẩn. Nếu cần registry động, xây một bean registry chuyên trách với business key rõ ràng.

## 22. Chọn cơ chế theo ý định

| Ý định thiết kế | Cơ chế phù hợp |
|---|---|
| Một implementation mặc định cho dependency đơn | `@Primary` |
| Một bean dự phòng khi không có implementation thông thường | `@Fallback` (Spring Framework 6.2+) |
| Một service cần implementation cụ thể | `@Qualifier` hoặc custom qualifier |
| Chọn bean theo tên chính xác | `@Resource(name = "...")` hoặc lookup theo tên trong hạ tầng phù hợp |
| Lấy tất cả implementation | `List<T>`, `Set<T>` hoặc `T[]` |
| Lấy tất cả và tra cứu theo tên bean | `Map<String, T>` |
| Chọn implementation theo business key lúc runtime | Inject collection và xây registry |
| Dependency có thể không tồn tại hoặc cần truy vấn trì hoãn | `ObjectProvider<T>` / `Optional<T>` theo semantics |
| Phân biệt implementation theo kiểu generic | Generic injection khi metadata có thể phân giải |
| Starter cung cấp bean mặc định | `@ConditionalOnMissingBean` |
| Bean xuất hiện ngoài ý muốn | Sửa component scan, import, profile hoặc điều kiện đăng ký |

## 23. Nguyên tắc ghi nhớ

1. `NoUniqueBeanDefinitionException` có nghĩa Spring tìm thấy nhiều bean phù hợp trong khi điểm sử dụng cần một bean duy nhất.
2. Đọc candidate names trong exception để tìm nguồn đăng ký.
3. `@Primary` chọn một default candidate; nó không loại bỏ các bean còn lại.
4. `@Qualifier` hoặc custom qualifier thể hiện implementation mà một dependency cụ thể cần.
5. `@Resource(name = "...")` phù hợp khi muốn wiring theo bean name.
6. Parameter name matching có thể là fallback ở những phiên bản/compile setup phù hợp; đừng dùng nó thay qualifier cho hợp đồng quan trọng.
7. `@Fallback` có từ Spring Framework 6.2; kiểm tra version trước khi sử dụng.
8. `@Order` sắp xếp collection, không phải cách tiêu chuẩn chọn một dependency đơn.
9. Nếu cần tất cả implementation, inject collection; nếu cần chọn theo nghiệp vụ lúc runtime, xây registry có business key.
10. `Optional` không giải quyết ambiguity; `ObjectProvider` cung cấp API truy vấn nhưng vẫn cần xử lý trường hợp không unique.
11. `@ConditionalOnMissingBean` giúp auto-configuration lùi lại khi ứng dụng có bean, nhưng không phân biệt nhiều bean do ứng dụng tự đăng ký.
12. Constructor injection và integration test giúp phát hiện lỗi wiring ngay khi khởi động.
13. Phân biệt lỗi nhiều candidate với lỗi trùng bean name; không bật overriding để che giấu lỗi chọn dependency.
14. Chọn cơ chế dựa trên ý định: default, cụ thể, tất cả candidate hay lựa chọn theo runtime.

**Kết luận:** `NoUniqueBeanDefinitionException` không phải dấu hiệu Spring không biết tạo bean; nó cho biết container đã tìm thấy nhiều ứng viên nhưng không có đủ thông tin để chọn một cách chắc chắn. Hãy quyết định rõ service cần bean mặc định, một implementation cụ thể hay toàn bộ implementations. Dùng `@Primary` cho default, `@Qualifier` cho lựa chọn theo vai trò, collection/registry cho nhiều chiến lược, và sửa đăng ký bean nếu có implementation thừa. Khi ý định dependency được thể hiện rõ trong code và được xác nhận bằng context test, lỗi ambiguity sẽ dễ chẩn đoán và ít tái xuất hiện hơn.
