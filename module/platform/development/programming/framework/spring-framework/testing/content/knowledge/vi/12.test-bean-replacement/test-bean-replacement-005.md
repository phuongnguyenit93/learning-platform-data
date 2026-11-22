# Chọn bean theo kiểu, tên và qualifier

Trong Spring, nhiều bean có thể cùng triển khai một interface hoặc cùng có một kiểu. Ví dụ, ứng dụng thanh toán có thể đăng ký CardPaymentGateway, BankTransferGateway và WalletPaymentGateway, tất cả đều triển khai PaymentGateway. Khi một service yêu cầu PaymentGateway, Spring cần xác định bean phù hợp để inject.

Trong kiểm thử, cùng một vấn đề xuất hiện khi cần thay đúng bean bằng mock hoặc spy. Nếu test thay nhầm implementation, service có thể vẫn gọi bean thật; nếu có nhiều bean cùng kiểu mà không chỉ rõ mục tiêu, Spring có thể báo lỗi không xác định được candidate.

Để chọn bean chính xác, cần hiểu ba thông tin thường dùng:

- **Kiểu (type):** kiểu class hoặc interface mà dependency yêu cầu.
- **Tên (bean name):** định danh bean trong ApplicationContext.
- **Qualifier:** nhãn hoặc tiêu chí bổ sung để thu hẹp nhóm bean phù hợp.

Spring thường tìm candidate theo kiểu trước, sau đó áp dụng qualifier và các quy tắc ưu tiên. Tên bean có thể được dùng làm tiêu chí chọn trong một số tình huống. Các annotation như @Primary, @Fallback, @Qualifier, @Autowired và @Resource giúp mô tả ý định đó. Với test, @MockitoBean và @MockitoSpyBean dùng cùng thông tin kiểu, tên và qualifier để xác định bean cần thay thế hoặc theo dõi.

## 1. Vì sao một kiểu có thể có nhiều bean?

Một interface mô tả hợp đồng chung, nhưng ứng dụng có thể có nhiều implementation cho các môi trường hoặc phương thức khác nhau.

Ví dụ:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}
~~~

Hai implementation:

~~~java
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Gửi yêu cầu tới cổng thanh toán thẻ.
        return PaymentResult.approved();
    }
}
~~~

~~~java
@Component("bankGateway")
public class BankTransferGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Tạo yêu cầu chuyển khoản ngân hàng.
        return PaymentResult.pending();
    }
}
~~~

Một service chỉ khai báo dependency theo interface:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway gateway;

    public PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentResult pay(PaymentCommand command) {
        return gateway.charge(command);
    }
}
~~~

Khi Spring tạo PaymentService, có hai bean cùng thỏa mãn kiểu PaymentGateway. Nếu không có thêm thông tin để chọn, Spring không thể tự quyết định implementation nào là đúng và có thể ném NoUniqueBeanDefinitionException.

Đây không phải lỗi của interface. Nhiều implementation cùng kiểu là một cách thiết kế bình thường. Cấu hình cần thể hiện rõ service nào dùng implementation nào.

## 2. Bean type, bean name và alias

### Chọn theo kiểu

Kiểu là tiêu chí cơ bản khi Spring giải quyết dependency. Một điểm inject khai báo PaymentGateway có thể nhận bean được đăng ký bằng class triển khai PaymentGateway, hoặc một bean factory method có kiểu trả về tương thích.

Ví dụ:

~~~java
@Bean
PaymentGateway cardGateway() {
    return new CardPaymentGateway();
}
~~~

Bean trên có kiểu thực tế CardPaymentGateway và kiểu khai báo PaymentGateway. Spring có thể tìm bean này khi dependency yêu cầu PaymentGateway.

Nếu chỉ có một candidate phù hợp, injection theo kiểu thường là đủ:

~~~java
@Autowired
private PaymentGateway paymentGateway;
~~~

Khi có nhiều candidate cùng kiểu, cần thu hẹp bằng qualifier, tên hoặc quy tắc ưu tiên.

### Bean name

Mỗi bean được đăng ký trong BeanFactory có một tên chính. Với component scan, tên mặc định thường được tạo từ tên class theo quy tắc đặt tên bean của Spring. Có thể chỉ định tên rõ ràng:

~~~java
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {
}
~~~

Với @Bean, tên mặc định là tên method factory:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    PaymentGateway bankGateway() {
        return new BankTransferGateway();
    }
}
~~~

Ở ví dụ này, tên bean mặc định là bankGateway. Có thể khai báo tên hoặc alias:

~~~java
@Bean(name = {"bankGateway", "primaryBankGateway"})
PaymentGateway bankGateway() {
    return new BankTransferGateway();
}
~~~

Tên chính và alias đều có thể được dùng để tra cứu bean trong context. Tuy nhiên, khi thiết kế injection, nên dùng một tên có ý nghĩa và nhất quán thay vì tạo nhiều alias không cần thiết.

### Tra cứu theo tên trực tiếp

Khi cần lấy bean theo tên, có thể dùng ApplicationContext:

~~~java
PaymentGateway gateway =
        applicationContext.getBean("bankGateway", PaymentGateway.class);
~~~

Cách này yêu cầu biết tên bean tại thời điểm gọi. Nó phù hợp với một số cơ chế lựa chọn động, nhưng trong code ứng dụng thông thường, constructor injection theo kiểu và qualifier thường dễ kiểm tra hơn.

Không nên gọi getBean theo tên trong mọi service chỉ để né lỗi có nhiều candidate. Việc đó làm dependency trở nên ẩn trong thân method và khiến Spring khó kiểm tra cấu hình ngay lúc tạo bean.

## 3. @Qualifier: thu hẹp candidate theo nhãn

@Qualifier được dùng cùng injection theo kiểu để chỉ rõ nhóm bean phù hợp.

Có thể gắn qualifier lên bean:

~~~java
@Component
@Qualifier("card")
public class CardPaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
@Qualifier("bank")
public class BankTransferGateway implements PaymentGateway {
}
~~~

Và chọn khi inject:

~~~java
@Service
public class CardCheckoutService {

    private final PaymentGateway gateway;

    public CardCheckoutService(
            @Qualifier("card") PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
~~~

Spring trước hết tìm bean tương thích với kiểu PaymentGateway, sau đó qualifier card thu hẹp tập candidate. Nếu chỉ còn một candidate, bean đó được inject.

Giá trị của @Qualifier thường được hiểu như một nhãn ngữ nghĩa. Nó không bắt buộc phải trùng bean name, dù Spring có thể dùng tên bean làm fallback khi khớp qualifier trong những trường hợp phù hợp. Nên xem qualifier là cách mô tả vai trò của dependency, chẳng hạn card, bank, remote hoặc local.

### Qualifier không nhất thiết phải là tên bean

Có thể đặt qualifier khác tên bean:

~~~java
@Component("stripeGateway")
@Qualifier("externalCard")
public class StripePaymentGateway implements PaymentGateway {
}
~~~

Injection:

~~~java
public CheckoutService(
        @Qualifier("externalCard") PaymentGateway gateway
) {
    this.gateway = gateway;
}
~~~

Tên bean là stripeGateway, còn qualifier là externalCard. Điều này cho phép code thể hiện vai trò mà service cần, trong khi tên bean phản ánh implementation hoặc nhà cung cấp.

### Dùng qualifier tùy chỉnh có kiểu

Nếu một qualifier được sử dụng ở nhiều nơi, có thể tạo annotation riêng:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.METHOD,
        ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Qualifier
public @interface RemotePayment {
}
~~~

Đánh dấu bean:

~~~java
@Component
@RemotePayment
public class RemotePaymentGateway implements PaymentGateway {
}
~~~

Inject bean:

~~~java
public CheckoutService(
        @RemotePayment PaymentGateway gateway
) {
    this.gateway = gateway;
}
~~~

Annotation riêng giúp tránh rải chuỗi qualifier khắp code và làm ý nghĩa dependency rõ hơn. Có thể thêm thuộc tính vào custom qualifier nếu cần phân biệt nhiều giá trị, ví dụ region hoặc tenant. Khi đó, giá trị của thuộc tính cũng tham gia vào việc khớp candidate.

## 4. Spring giải quyết dependency như thế nào?

Khi Spring gặp một điểm inject đơn trị, nó cần tìm một candidate phù hợp với kiểu và metadata của dependency.

Có thể hiểu quy trình theo các bước khái quát:

1. Tìm các bean có kiểu tương thích với dependency.
2. Áp dụng qualifier để loại những candidate không thỏa điều kiện.
3. Nếu còn nhiều candidate, xem xét các quy tắc ưu tiên như @Primary, @Fallback hoặc @Priority.
4. Trong một số trường hợp, tên dependency hoặc tên parameter có thể giúp chọn bean có tên tương ứng.
5. Nếu vẫn còn nhiều candidate ngang nhau, Spring báo lỗi không xác định được bean duy nhất.

Đây là cách diễn giải để đọc cấu hình và chẩn đoán. Thuật toán thực tế có nhiều chi tiết phụ thuộc loại dependency, metadata và phiên bản Spring.

### @Primary chọn candidate mặc định

Đánh dấu một bean là @Primary để Spring ưu tiên bean đó khi có nhiều candidate cùng kiểu và điểm inject không chỉ rõ qualifier khác:

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
public class BankTransferGateway implements PaymentGateway {
}
~~~

Dependency sau nhận CardPaymentGateway:

~~~java
public PaymentService(PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

@Primary hữu ích khi ứng dụng có một implementation mặc định. Tuy nhiên, nó không loại bỏ các bean khác khỏi context. Một điểm inject có qualifier phù hợp với bean khác vẫn có thể chọn bean đó.

Nếu có nhiều candidate cùng được đánh dấu @Primary cho cùng kiểu và cùng qualifier, Spring vẫn có thể không xác định được một bean duy nhất.

### @Fallback trong Spring Framework 6.2 trở lên

Spring Framework 6.2 bổ sung @Fallback để đánh dấu candidate có mức ưu tiên thấp hơn. Nếu có một candidate thông thường và một candidate fallback cho cùng dependency, candidate thông thường được ưu tiên.

Ví dụ:

~~~java
@Component
@Fallback
public class DefaultPaymentGateway implements PaymentGateway {
}
~~~

~~~java
@Component
public class ProductionPaymentGateway implements PaymentGateway {
}
~~~

Khi inject PaymentGateway mà không có qualifier khác, ProductionPaymentGateway được chọn vì DefaultPaymentGateway là fallback.

@Fallback hữu ích khi muốn cung cấp implementation dự phòng mà không phải đánh dấu mọi implementation chính bằng @Primary. Nếu tất cả candidate đều là fallback hoặc vẫn còn nhiều candidate chính ngang nhau, dependency vẫn có thể mơ hồ.

### @Priority và thứ tự candidate

Trong một số trường hợp chọn một bean từ nhiều candidate, metadata priority có thể tham gia phân giải. Spring cũng hỗ trợ thứ tự bean trong các injection dạng collection. Cần phân biệt:

- @Priority có thể được dùng trong quá trình chọn một candidate đơn trị theo quy tắc của Spring.
- @Order hoặc Ordered thường điều khiển thứ tự các bean khi inject collection hoặc khi framework sắp xếp chúng.
- Thứ tự trong List không có nghĩa phần tử đầu tiên tự động trở thành bean mặc định cho mọi dependency đơn trị.

Nếu một dependency cần đúng implementation theo nghiệp vụ, qualifier hoặc tên rõ ràng thường diễn đạt ý định tốt hơn việc dựa vào thứ tự.

### Tên parameter và tên field làm tiêu chí fallback

Trong một số tình huống, khi nhiều candidate cùng kiểu và không có qualifier/primary đủ để phân giải, Spring có thể dùng tên dependency để tìm bean trùng tên.

Ví dụ:

~~~java
@Service
public class PaymentService {

    private final PaymentGateway bankGateway;

    public PaymentService(PaymentGateway bankGateway) {
        this.bankGateway = bankGateway;
    }
}
~~~

Nếu bean có tên bankGateway, tên parameter có thể giúp Spring chọn candidate đó theo cơ chế fallback tương ứng. Với constructor parameter, tên parameter cần được giữ trong bytecode; dự án Java thường bật tùy chọn biên dịch -parameters để Spring đọc được tên một cách đáng tin cậy. Field name có thể được Spring sử dụng trực tiếp tại điểm inject field.

Không nên dựa vào name fallback khi ý nghĩa dependency quan trọng. Dùng @Qualifier rõ ràng giúp code dễ đọc và ít phụ thuộc cấu hình compiler hơn.

## 5. Phân biệt @Autowired, @Qualifier và @Resource

Ba annotation thường xuất hiện cùng nhau nhưng thể hiện ý định khác nhau.

| Annotation | Cách chọn chính | Vai trò |
|---|---|---|
| @Autowired | Theo kiểu | Yêu cầu Spring inject dependency phù hợp |
| @Qualifier | Thu hẹp candidate | Chọn bean có nhãn/metadata phù hợp trong nhóm cùng kiểu |
| @Resource | Theo tên trước | Inject resource theo tên bean; có thể suy ra tên từ field hoặc setter nếu không chỉ định |

### @Autowired theo kiểu

~~~java
@Autowired
private PaymentGateway gateway;
~~~

Spring tìm bean tương thích với PaymentGateway. Nếu chỉ có một candidate thì injection rõ ràng. Nếu có nhiều candidate, cần thêm metadata để phân giải.

### @Autowired kết hợp @Qualifier

~~~java
@Autowired
@Qualifier("bank")
private PaymentGateway gateway;
~~~

Đây là injection theo kiểu có qualifier. Trong constructor injection, có thể đặt @Qualifier trên parameter:

~~~java
public PaymentService(
        @Qualifier("bank") PaymentGateway gateway
) {
    this.gateway = gateway;
}
~~~

Với constructor duy nhất, Spring thường không cần @Autowired trên constructor. @Qualifier vẫn cần để thu hẹp candidate.

### @Resource theo tên

@Resource thuộc Jakarta Annotations trong các phiên bản Spring hiện đại. Khi chỉ định name, nó tìm resource theo tên đó:

~~~java
@Resource(name = "bankGateway")
private PaymentGateway gateway;
~~~

Nếu không chỉ định name, tên field hoặc property có thể được dùng làm tên resource theo quy tắc của @Resource. Vì vậy, @Resource thường diễn đạt ý định chọn resource theo tên rõ hơn @Autowired.

Nếu yêu cầu là chọn một bean theo vai trò trong nhóm implementation cùng interface, @Autowired kết hợp @Qualifier thường thể hiện tốt mô hình type-first của Spring. Nếu yêu cầu là lấy một resource theo tên cụ thể, @Resource(name = "...") là lựa chọn phù hợp.

## 6. Inject nhiều bean cùng kiểu

Không phải dependency nào cũng cần chọn một bean duy nhất. Nếu service cần gọi tất cả implementation, Spring có thể inject collection.

### List hoặc array

~~~java
@Service
public class PaymentGatewayRegistry {

    private final List<PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public List<PaymentGateway> all() {
        return gateways;
    }
}
~~~

Spring đưa các bean phù hợp vào List. Nếu có @Order hoặc Ordered, thứ tự collection có thể được sắp xếp theo metadata tương ứng.

### Map theo bean name

~~~java
@Service
public class PaymentGatewayRegistry {

    private final Map<String, PaymentGateway> gateways;

    public PaymentGatewayRegistry(
            Map<String, PaymentGateway> gateways
    ) {
        this.gateways = gateways;
    }

    public PaymentGateway get(String name) {
        return gateways.get(name);
    }
}
~~~

Với Map injection, key là bean name và value là bean instance. Cách này phù hợp khi ứng dụng có registry lựa chọn implementation theo một mã đã được kiểm soát.

Nếu chỉ cần một implementation, đừng inject toàn bộ Map rồi tự lấy phần tử trong service chỉ để né NoUniqueBeanDefinitionException. Hãy thể hiện dependency cụ thể bằng qualifier.

### ObjectProvider khi cần tra cứu có điều kiện

ObjectProvider cho phép trì hoãn việc lấy bean hoặc xử lý trường hợp có/không có candidate:

~~~java
public class OptionalPaymentService {

    private final ObjectProvider<PaymentGateway> gateways;

    public OptionalPaymentService(
            ObjectProvider<PaymentGateway> gateways
    ) {
        this.gateways = gateways;
    }

    public PaymentGateway gatewayOrNull() {
        return gateways.getIfAvailable();
    }
}
~~~

ObjectProvider có các API như getIfAvailable, getIfUnique và stream. Nó hữu ích khi dependency thực sự là tùy chọn hoặc được tra cứu tại thời điểm chạy. Nếu ứng dụng luôn cần đúng một bean, injection trực tiếp thường giúp phát hiện lỗi cấu hình sớm hơn.

## 7. Chọn bean khi thay thế trong kiểm thử

Trong test Spring, việc có một field Mockito mock chưa đủ để thay bean mà service đang dùng trong ApplicationContext.

Ví dụ:

~~~java
@ExtendWith(MockitoExtension.class)
class PaymentServiceUnitTest {

    @Mock
    PaymentGateway gateway;

    private PaymentService service;

    @BeforeEach
    void setUp() {
        service = new PaymentService(gateway);
    }
}
~~~

Đây là unit test thuần: test tự tạo PaymentService và truyền mock vào constructor.

Nếu PaymentService được Spring tạo trong ApplicationContext, mock field do MockitoExtension quản lý không tự động thay bean PaymentGateway trong context. Khi cần thay bean trong context, Spring Framework cung cấp @MockitoBean; khi cần theo dõi một bean thật, có @MockitoSpyBean.

Các annotation bean override này được cung cấp trong Spring Framework 6.2 trở lên. Với dự án Spring Boot, @MockBean cũ đã được đánh dấu deprecated từ Spring Boot 3.4 để chuyển sang cơ chế @MockitoBean của Spring Framework.

### @MockitoBean chọn theo kiểu

Ví dụ test dùng Spring context:

~~~java
@SpringJUnitConfig(PaymentTestConfiguration.class)
class PaymentServiceSpringTest {

    @MockitoBean
    private PaymentGateway gateway;

    @Autowired
    private PaymentService paymentService;

    @Test
    void returnsApprovedResult() {
        when(gateway.charge(any()))
                .thenReturn(PaymentResult.approved());

        PaymentResult result =
                paymentService.pay(new PaymentCommand("ORDER-01"));

        assertTrue(result.approved());
        verify(gateway).charge(any());
    }
}
~~~

Ở đây:

- Kiểu field là PaymentGateway, nên Spring dùng kiểu đó để tìm bean cần override.
- @MockitoBean tạo Mockito mock và đăng ký nó trong ApplicationContext theo cơ chế bean override.
- Field trong test nhận cùng mock để test có thể stub và verify.
- PaymentService trong context nhận bean đã được thay thế khi nó được tạo hoặc lấy dependency từ context.

Nếu chỉ có một bean PaymentGateway, kiểu là đủ để xác định mục tiêu.

### Khi có nhiều bean cùng kiểu: dùng @Qualifier

Giả sử context có cardGateway và bankGateway. Test chỉ muốn thay bankGateway:

~~~java
@SpringJUnitConfig(PaymentTestConfiguration.class)
class BankPaymentServiceTest {

    @MockitoBean
    @Qualifier("bank")
    private PaymentGateway gateway;

    @Autowired
    private BankPaymentService bankPaymentService;

    @Test
    void usesMockedBankGateway() {
        when(gateway.charge(any()))
                .thenReturn(PaymentResult.pending());

        PaymentResult result =
                bankPaymentService.pay(new PaymentCommand("ORDER-02"));

        assertEquals(PaymentStatus.PENDING, result.status());
        verify(gateway).charge(any());
    }
}
~~~

Qualifier trên field giúp Spring thu hẹp candidate theo metadata của bean. Nếu bean bankGateway được đánh dấu @Qualifier("bank"), test nhắm đúng implementation đó.

Có thể dùng qualifier tùy chỉnh:

~~~java
@MockitoBean
@RemotePayment
private PaymentGateway gateway;
~~~

Điều kiện là bean cần thay cũng mang qualifier tương ứng.

### Dùng tên field làm fallback qualifier

Nếu nhiều bean cùng kiểu, tên field của @MockitoBean có thể được dùng như một qualifier fallback. Ví dụ, context có bean tên bankGateway:

~~~java
@MockitoBean
private PaymentGateway bankGateway;
~~~

Field name bankGateway giúp phân biệt bean cần override khi các qualifier khác không cung cấp thông tin rõ hơn.

Dù cơ chế fallback này tiện lợi, test nên dùng tên field có ý nghĩa và giữ nó ổn định. Khi lựa chọn bean là quyết định quan trọng hoặc tên field không trùng bean name, hãy khai báo @Qualifier tường minh.

### Chỉ định bean name trực tiếp

@MockitoBean hỗ trợ thuộc tính name để chỉ rõ bean cần thay:

~~~java
@MockitoBean(name = "bankGateway")
private PaymentGateway gateway;
~~~

Có thể dùng name cùng kiểu field. Cách này hữu ích khi test field có tên chung như gateway nhưng context chứa nhiều PaymentGateway.

Một cách khác là đặt @Qualifier trên field:

~~~java
@MockitoBean
@Qualifier("bankGateway")
private PaymentGateway gateway;
~~~

Chọn một cách thể hiện mục tiêu rõ ràng và nhất quán trong test suite. Nếu bean có qualifier ngữ nghĩa như bank, dùng qualifier đó thường giúp test ít phụ thuộc tên implementation hơn. Nếu cần thay đúng bean theo định danh kỹ thuật, name là lựa chọn trực tiếp.

## 8. @MockitoBean có tạo bean mới nếu không tìm thấy candidate không?

Mặc định, @MockitoBean có thể tạo mock bean nếu context chưa có bean phù hợp để thay thế. Hành vi đó hữu ích khi test slice cần cung cấp dependency mà cấu hình slice không tạo ra.

Tuy nhiên, nếu mục tiêu là chứng minh một bean hiện hữu đã được thay thế, việc annotation âm thầm tạo bean mới có thể che giấu lỗi cấu hình hoặc chọn sai context.

Có thể bật enforceOverride:

~~~java
@MockitoBean(
        name = "bankGateway",
        enforceOverride = true
)
private PaymentGateway gateway;
~~~

Với enforceOverride = true, test yêu cầu bean mục tiêu phải tồn tại để được thay thế. Nếu không tìm thấy bean phù hợp, Spring báo lỗi khi tạo context.

Nên dùng enforceOverride khi:

- Test cần xác nhận một bean cụ thể đã được cấu hình trong ứng dụng.
- Có nhiều implementation cùng kiểu và việc chọn nhầm là rủi ro.
- Muốn phát hiện sớm tên bean hoặc qualifier bị sai.
- Test đang kiểm tra cấu hình tích hợp của ứng dụng.

Nếu test slice cố ý không nạp implementation thật và cần thêm mock mới, hành vi tạo bean mới mặc định có thể là điều mong muốn.

## 9. Thay bean theo kiểu ở cấp test class

@MockitoBean có thể được khai báo ở cấp class với thuộc tính types để chỉ định kiểu cần thay thế:

~~~java
@SpringJUnitConfig(PaymentTestConfiguration.class)
@MockitoBean(types = NotificationClient.class)
class NotificationServiceTest {
    // Tests
}
~~~

Cách khai báo ở cấp class hữu ích khi muốn đăng ký mock cho một hoặc nhiều kiểu mà không cần field mock riêng. Có thể dùng dạng repeatable để khai báo nhiều override.

Khi một kiểu có nhiều bean candidate, cần thêm thông tin để xác định đúng bean. Với trường hợp cần qualifier hoặc tên riêng cho từng dependency, khai báo trên field cùng @Qualifier hoặc name thường dễ đọc và trực tiếp hơn.

Khi dùng type-level declaration cho nhiều kiểu, hãy kiểm tra thuộc tính name và quy tắc đăng ký của phiên bản Spring Framework trong dự án. Không nên giả định một tên duy nhất có thể mô tả nhiều bean cùng kiểu khác nhau.

## 10. @MockitoSpyBean và lựa chọn bean cần theo dõi

@MockitoSpyBean tạo spy bao quanh bean hiện có để test có thể gọi hành vi thật và quan sát tương tác. Việc xác định bean mục tiêu cũng dựa trên kiểu và qualifier tương tự bean override.

Ví dụ:

~~~java
@SpringJUnitConfig(PaymentTestConfiguration.class)
class BankGatewaySpyTest {

    @MockitoSpyBean
    @Qualifier("bank")
    private PaymentGateway bankGateway;

    @Autowired
    private PaymentService paymentService;

    @Test
    void observesBankGatewayCall() {
        paymentService.pay(new PaymentCommand("ORDER-03"));

        verify(bankGateway).charge(any());
    }
}
~~~

Spy giữ hành vi thật của bean được chọn, trừ khi test stub một method cụ thể. Vì vậy, cần cân nhắc side effect của method thật như gọi mạng, ghi database hoặc phát message.

@MockitoSpyBean yêu cầu bean hiện có để wrap. Nếu context không có bean phù hợp, việc tạo context sẽ thất bại. Khi muốn thay thế hoàn toàn dependency bằng mock, @MockitoBean thường phù hợp hơn.

Nếu có nhiều bean cùng kiểu, dùng @Qualifier hoặc tên field rõ ràng để tránh spy nhầm implementation.

## 11. Ví dụ đầy đủ: chọn đúng implementation trong service và test

Giả sử cấu hình ứng dụng đăng ký hai gateway:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    @Qualifier("card")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("bank")
    PaymentGateway bankGateway() {
        return new BankTransferGateway();
    }

    @Bean
    PaymentService cardPaymentService(
            @Qualifier("card") PaymentGateway gateway
    ) {
        return new PaymentService(gateway);
    }

    @Bean
    PaymentService bankPaymentService(
            @Qualifier("bank") PaymentGateway gateway
    ) {
        return new PaymentService(gateway);
    }
}
~~~

Test thay đúng gateway ngân hàng:

~~~java
@SpringJUnitConfig(PaymentConfiguration.class)
class BankPaymentServiceTest {

    @MockitoBean
    @Qualifier("bank")
    private PaymentGateway bankGateway;

    @Autowired
    private PaymentService bankPaymentService;

    @Test
    void delegatesToBankGateway() {
        when(bankGateway.charge(any()))
                .thenReturn(PaymentResult.pending());

        PaymentResult result =
                bankPaymentService.pay(new PaymentCommand("ORDER-10"));

        assertEquals(PaymentStatus.PENDING, result.status());
        verify(bankGateway).charge(any());
    }
}
~~~

Test thay đúng candidate vì cả bean definition và điểm injection đều mang qualifier bank. CardPaymentGateway vẫn là bean riêng của context và không bị thay bởi mock này.

Nếu test cần xác nhận card gateway vẫn là implementation thật, có thể lấy bean theo qualifier trong một test context phù hợp. Tuy nhiên, không nên kiểm tra quá nhiều chi tiết wiring trong một test chỉ nhằm xác nhận hành vi của BankPaymentService.

## 12. Các lỗi thường gặp khi chọn bean trong test

### NoUniqueBeanDefinitionException

Nguyên nhân là có nhiều bean cùng kiểu sau khi Spring áp dụng các tiêu chí hiện có, nhưng không có candidate duy nhất.

Cách xử lý:

- Thêm @Qualifier vào điểm injection.
- Đánh dấu @Primary cho implementation mặc định nếu đó là chính sách của ứng dụng.
- Dùng @Fallback cho implementation dự phòng trên Spring Framework 6.2 trở lên.
- Dùng tên dependency rõ ràng khi name fallback phù hợp.
- Kiểm tra component scan có vô tình đăng ký implementation hai lần không.

### NoSuchBeanDefinitionException khi dùng qualifier

Có thể bean tồn tại nhưng không mang qualifier mà test yêu cầu, hoặc test đang dùng context slice không nạp bean đó.

Kiểm tra annotation trên bean, tên qualifier, package scan và cấu hình test. Nếu mục tiêu là thay bean hiện có, dùng enforceOverride để phát hiện trường hợp không có candidate thay thế.

### Mock được tạo nhưng service vẫn gọi implementation thật

Một field @Mock của MockitoExtension không tự thay bean trong ApplicationContext. Dùng @MockitoBean hoặc cơ chế bean override phù hợp để đăng ký mock vào context.

Nếu đã dùng @MockitoBean, kiểm tra qualifier/name có chọn đúng bean được service inject không. Một service khác có thể đang dùng implementation khác cùng kiểu.

### @MockitoBean thay nhầm bean cùng kiểu

Khi có nhiều candidate, kiểu đơn thuần chưa đủ. Bổ sung @Qualifier trên field, dùng name rõ ràng hoặc đặt tên field trùng bean name theo cơ chế fallback.

Đừng dựa vào thứ tự khai báo @Bean hoặc thứ tự component scan để xác định bean được thay.

### @MockitoBean tạo bean mới ngoài dự kiến

Mặc định annotation có thể tạo mock nếu không tìm thấy bean phù hợp. Nếu test cần xác nhận bean thật đã được cấu hình, bật enforceOverride = true.

### @MockitoSpyBean không tìm thấy bean

Spy cần một bean hiện hữu để wrap. Kiểm tra test context có nạp đúng cấu hình và candidate theo type/qualifier/name có tồn tại không.

### Qualifier trên bean và injection không khớp

Qualifier là metadata. Giá trị ở bean và điểm inject phải tương thích. Nếu dùng custom qualifier, bảo đảm annotation được đánh dấu @Qualifier và có runtime retention.

### Nhầm @Primary với @Qualifier

@Primary chọn candidate mặc định trong nhóm phù hợp. @Qualifier thu hẹp nhóm theo nhãn. Nếu một service bắt buộc dùng bank gateway, ghi rõ @Qualifier("bank") thể hiện yêu cầu tốt hơn việc chỉ trông chờ bank gateway tình cờ là @Primary.

### Dùng tên field chung chung

Field tên gateway có thể không giúp phân biệt các bean cùng kiểu. Đặt tên bankGateway hoặc cardGateway, hoặc thêm @Qualifier/name tường minh để test dễ hiểu.

## 13. Cách chẩn đoán candidate Spring đang chọn

Khi kết quả injection không đúng, có thể điều tra theo thứ tự:

1. Xác định kiểu dependency tại điểm inject.
2. Liệt kê các bean trong context có kiểu tương thích.
3. Kiểm tra tên bean và alias.
4. Kiểm tra @Qualifier trên bean và điểm inject.
5. Kiểm tra @Primary, @Fallback và metadata priority.
6. Kiểm tra tên field/parameter nếu Spring đang dùng name fallback.
7. Với test override, xác nhận @MockitoBean/@MockitoSpyBean nhắm đúng candidate.
8. Nếu cần bean phải tồn tại, bật enforceOverride để tránh việc tạo mock mới che lỗi.
9. Kiểm tra test đang sử dụng đúng ApplicationContext hoặc test slice.

Có thể tra cứu bean name và kiểu trong một context bằng:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(PaymentGateway.class);

for (String name : names) {
    PaymentGateway gateway =
            applicationContext.getBean(name, PaymentGateway.class);

    System.out.println(name + " -> " + gateway.getClass().getName());
}
~~~

Đây là đoạn chẩn đoán hữu ích khi cần nhìn thấy các candidate thực tế. Không nên để logic tra cứu này trở thành cách lựa chọn bean thường xuyên trong service nếu dependency có thể được khai báo rõ qua constructor.

## 14. Chọn type, name hay qualifier trong trường hợp nào?

| Tình huống | Cách thể hiện phù hợp |
|---|---|
| Chỉ có một implementation của interface | Inject theo type |
| Có một implementation mặc định và các implementation phụ | @Primary hoặc @Fallback |
| Service cần implementation theo vai trò nghiệp vụ | @Qualifier hoặc custom qualifier |
| Cần đúng bean có định danh cụ thể | @Resource(name = ...) hoặc @Qualifier/name |
| Cần thay bean trong Spring test, chỉ có một candidate | @MockitoBean theo type |
| Cần thay một trong nhiều bean cùng kiểu | @MockitoBean kết hợp @Qualifier hoặc name |
| Cần bảo đảm bean mục tiêu tồn tại trước khi thay | @MockitoBean(enforceOverride = true) |
| Cần theo dõi hành vi bean thật | @MockitoSpyBean kết hợp qualifier/name khi cần |
| Cần sử dụng mọi implementation | List, array hoặc Map injection |

Một số nguyên tắc giúp cấu hình dễ hiểu:

- Dùng type để mô tả hợp đồng dependency.
- Dùng qualifier để mô tả vai trò hoặc nhóm candidate.
- Dùng bean name khi cần định danh chính xác một bean.
- Dùng @Primary cho mặc định của ứng dụng, không thay thế qualifier ở nơi có yêu cầu nghiệp vụ cụ thể.
- Dùng @Fallback cho implementation dự phòng nếu phiên bản Spring hỗ trợ.
- Trong test, chọn đúng bean bằng cùng metadata mà ứng dụng dùng để inject.
- Bật enforceOverride khi test cần chứng minh một bean hiện hữu đã được thay thế.
- Phân biệt mock field của Mockito với mock bean được đăng ký trong ApplicationContext.

Chọn bean theo kiểu, tên và qualifier là một phần của cơ chế dependency injection và cũng là nền tảng để thay bean đúng trong Spring test. Khi nhiều implementation cùng kiểu, qualifier thể hiện vai trò của dependency, tên xác định bean cụ thể và các quy tắc ưu tiên giúp Spring chọn candidate mặc định. Với @MockitoBean và @MockitoSpyBean, các thông tin đó quyết định chính xác bean nào bị thay hoặc được theo dõi. Khai báo rõ mục tiêu ở cả cấu hình ứng dụng và test giúp tránh lỗi mơ hồ, mock nhầm implementation và những bài kiểm thử vô tình vẫn gọi dependency thật.

