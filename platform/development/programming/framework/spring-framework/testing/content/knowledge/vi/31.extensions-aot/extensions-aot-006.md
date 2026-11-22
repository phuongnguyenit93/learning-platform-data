# Annotation override bean riêng với hạ tầng BeanOverride

## 1. Vì sao cần override bean trong test?

Một Spring ApplicationContext thường có các bean thật được tạo từ component scan, Java configuration, auto-configuration hoặc thư viện bên ngoài. Khi kiểm thử một service, đôi lúc cần thay một dependency bằng mock hoặc fake để kiểm soát đầu vào và kết quả.

Ví dụ, OrderService dùng PaymentGateway để gọi hệ thống thanh toán. Test logic của OrderService không nhất thiết phải gửi request ra cổng thanh toán thật. Ta muốn thay bean PaymentGateway trong test context bằng một mock, rồi điều khiển mock trả về kết quả mong muốn.

Có thể tự tạo một bean test trong @TestConfiguration, nhưng cách đó có thể dẫn tới nhiều cấu hình lặp lại, phải xử lý tên bean hoặc @Primary, và đôi khi không thay đúng bean mà ứng dụng thực sự inject.

Spring Framework cung cấp **BeanOverride infrastructure** để khai báo việc thay thế hoặc bọc bean ngay trên test class bằng annotation. Hạ tầng này tìm bean mục tiêu, áp dụng chiến lược override, rồi inject bean thay thế vào test field khi cần.

Các annotation tiêu biểu:

- **@TestBean**: thay bean bằng một instance do factory method của test tạo ra.
- **@MockitoBean**: thay bean bằng Mockito mock.
- **@MockitoSpyBean**: bọc bean hiện có bằng Mockito spy để theo dõi hoặc stub một phần hành vi.

Các annotation này giúp khai báo rõ dependency nào được thay trong test context. Chúng không thay đổi bean của ứng dụng đang chạy ngoài test.

## 2. BeanOverride infrastructure là gì?

BeanOverride infrastructure được giới thiệu trong Spring Framework **6.2**. Đây là cơ chế chung của Spring Test để tìm và áp dụng các bean override trong TestContext Framework.

Thay vì mỗi annotation tự cài một quy trình riêng, Spring cung cấp một hạ tầng dùng chung với các khái niệm chính:

| Thành phần | Trách nhiệm |
|---|---|
| **@BeanOverride** | Meta-annotation đánh dấu một annotation là annotation khai báo bean override |
| **BeanOverrideProcessor** | Đọc annotation trên test class/field và tạo handler tương ứng |
| **BeanOverrideHandler** | Mô tả bean cần thay, tên/kiểu bean, chiến lược và cách tạo instance thay thế |
| **BeanOverrideStrategy** | Quy định thay bean hiện có, thay hoặc tạo mới, hay bọc bean hiện có |
| **TestContext Framework** | Phát hiện override và áp dụng chúng khi xây dựng ApplicationContext của test |

Quy trình khái quát:

~~~text
Test class có annotation override
          |
          v
Spring TestContext đọc metadata
          |
          v
BeanOverrideProcessor
          |
          v
BeanOverrideHandler
          |
          v
Chọn bean theo tên / kiểu / qualifier
          |
          v
Áp dụng BeanOverrideStrategy
          |
          v
Tạo ApplicationContext dùng trong test
          |
          v
Inject bean override vào test field
~~~

Bean override là một phần của quá trình chuẩn bị test context. Khi test được chạy, controller hoặc service trong context sẽ nhận dependency đã được thay theo khai báo đó.

Đây là cơ chế dành cho Spring Test. Không cần bật chế độ cho phép ghi đè bean toàn cục trong cấu hình ứng dụng chỉ để thay một dependency của test.

## 3. Ba chiến lược override

Hạ tầng BeanOverride định nghĩa ba chiến lược cơ bản:

| Chiến lược | Hành vi | Trường hợp sử dụng |
|---|---|---|
| **REPLACE** | Yêu cầu bean mục tiêu đã tồn tại rồi thay bean đó | Test muốn bảo đảm cấu hình ứng dụng thật sự có bean cần thay |
| **REPLACE_OR_CREATE** | Thay bean nếu tìm thấy; nếu không có thì đăng ký bean mới | Test slice hoặc test context có thể không nạp bean gốc |
| **WRAP** | Lấy bean hiện có rồi bọc nó bằng một instance khác | Theo dõi hoặc thay đổi có chọn lọc hành vi của bean thật |

Các annotation chuẩn sử dụng chiến lược phù hợp với mục đích:

- **@TestBean** và **@MockitoBean** mặc định dùng hành vi thay thế hoặc tạo mới. Có thể yêu cầu bean phải tồn tại bằng thuộc tính **enforceOverride = true**.
- **@MockitoSpyBean** dùng chiến lược bọc bean hiện có. Nó cần một bean thật để spy, không tự tạo một bean thay thế khi không tìm thấy target.

### REPLACE

Dùng khi test phải thay đúng một bean đã được cấu hình trong ứng dụng. Nếu bean không tồn tại, việc chuẩn bị context thất bại thay vì âm thầm tạo thêm mock.

### REPLACE_OR_CREATE

Dùng khi test có thể chạy với context rút gọn, ví dụ MVC slice chỉ nạp controller mà không nạp service thật. Trong trường hợp này, mock có thể được đăng ký nếu context chưa có bean tương ứng.

Cần cân nhắc kỹ: nếu test toàn ứng dụng mà bean đáng lẽ phải được cấu hình nhưng bị thiếu, mặc định tạo mới có thể che giấu lỗi cấu hình. Dùng **enforceOverride = true** khi sự hiện diện của bean gốc là điều test muốn xác nhận.

### WRAP

Dùng khi cần giữ logic thật nhưng muốn quan sát hoặc stub một số lời gọi. Spy bọc bean đang tồn tại; các phương thức không stub vẫn chạy implementation thật. Vì vậy, test cần chuẩn bị trạng thái và dependency của bean thật một cách phù hợp.

## 4. @TestBean: thay bean bằng factory method của test

**@TestBean** cho phép một test class cung cấp instance thay thế thông qua một static factory method. Đây là lựa chọn tốt khi muốn dùng fake hoặc stub tự viết mà không cần Mockito.

Ví dụ, ứng dụng có interface:

~~~java
public interface PaymentGateway {
    PaymentResult charge(String orderId, BigDecimal amount);
}
~~~

Service phụ thuộc vào interface đó:

~~~java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public PaymentResult pay(String orderId, BigDecimal amount) {
        return paymentGateway.charge(orderId, amount);
    }
}
~~~

Trong test, khai báo bean thay thế:

~~~java
import org.springframework.test.context.bean.override.convention.TestBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(AppConfig.class)
class OrderServiceTest {

    @TestBean
    PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return (orderId, amount) ->
                new PaymentResult("TEST-" + orderId, true);
    }

    @Autowired
    OrderService orderService;

    @Test
    void shouldUseTheTestPaymentGateway() {
        PaymentResult result = orderService.pay(
                "O-42",
                new BigDecimal("120.00")
        );

        assertThat(result.approved()).isTrue();
        assertThat(result.transactionId()).isEqualTo("TEST-O-42");
    }
}
~~~

Factory method mặc định được tìm theo tên field. Trong ví dụ, field tên **paymentGateway**, nên factory method có tên **paymentGateway()**. Method phải là **static**, không nhận tham số và trả về kiểu tương thích với kiểu field.

Nếu muốn dùng tên factory method khác, có thể chỉ định bằng thuộc tính **methodName**:

~~~java
@TestBean(methodName = "createFakeGateway")
PaymentGateway paymentGateway;

static PaymentGateway createFakeGateway() {
    return (orderId, amount) ->
            new PaymentResult("FAKE-" + orderId, true);
}
~~~

Có thể đặt **enforceOverride = true** nếu test yêu cầu bean gốc phải tồn tại. Nếu không, cơ chế mặc định có thể thay bean phù hợp hoặc tạo bean mới khi context chưa có bean đó.

**@TestBean** phù hợp với fake có hành vi xác định, chẳng hạn gateway trả kết quả theo input, repository giả lập nhỏ hoặc clock cố định. Khi cần verify số lần gọi và đối số, Mockito thường thuận tiện hơn.

## 5. @MockitoBean: thay bean bằng Mockito mock

**@MockitoBean** tạo Mockito mock và đăng ký nó làm bean trong test ApplicationContext. Annotation thường được đặt trên field của test class:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringJUnitConfig(AppConfig.class)
class OrderServiceMockitoTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    OrderService orderService;

    @Test
    void shouldReturnApprovedPayment() {
        given(paymentGateway.charge(
                "O-42",
                new BigDecimal("120.00")
        )).willReturn(new PaymentResult("TX-42", true));

        PaymentResult result = orderService.pay(
                "O-42",
                new BigDecimal("120.00")
        );

        assertThat(result.approved()).isTrue();
        then(paymentGateway).should().charge(
                "O-42",
                new BigDecimal("120.00")
        );
    }
}
~~~

Mockito mock được inject vào field **paymentGateway** và cũng được dùng làm bean dependency mà **OrderService** nhận được. Test điều khiển kết quả bằng stubbing, sau đó kiểm tra tương tác bằng **then(...).should()** hoặc **verify(...)**.

### Tìm bean cần thay

Spring thường tìm bean theo kiểu của field. Nếu có nhiều bean cùng kiểu, có thể xác định bean bằng:

- **@Qualifier** trên field.
- Tên field, được dùng như một gợi ý qualifier khi cần phân biệt.
- Thuộc tính **name** của **@MockitoBean** để chỉ định tên bean rõ ràng.

Ví dụ:

~~~java
@MockitoBean(name = "remotePaymentGateway")
PaymentGateway paymentGateway;
~~~

Hoặc dùng qualifier:

~~~java
@MockitoBean
@Qualifier("remotePaymentGateway")
PaymentGateway paymentGateway;
~~~

Khi có nhiều candidate cùng kiểu mà không có qualifier hoặc tên rõ ràng, Spring có thể không xác định được bean mục tiêu và làm context khởi tạo thất bại.

### Bắt buộc bean gốc phải tồn tại

Mặc định, **@MockitoBean** có thể thay bean nếu tìm thấy hoặc đăng ký mock mới nếu không tìm thấy. Nếu test cần bảo đảm cấu hình ứng dụng đã khai báo bean thật, dùng:

~~~java
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
~~~

Khi không có bean phù hợp để thay, context sẽ không được tạo thành công. Cách này hữu ích cho integration test cần kiểm tra cấu hình wiring.

### Đặt override ở cấp class

**@MockitoBean** cũng có thể khai báo ở cấp type để định nghĩa mock cho test class mà không cần field nhận mock. Thuộc tính **types** cho phép chỉ rõ các kiểu bean cần mock:

~~~java
@MockitoBean(types = {
        PaymentGateway.class,
        InventoryGateway.class
})
@SpringJUnitConfig(AppConfig.class)
class OrderWorkflowTest {
}
~~~

Khi cần stubbing hoặc verify mock, khai báo trên field thường dễ sử dụng hơn vì test có sẵn reference tới mock. Khai báo ở cấp class phù hợp khi chỉ cần thay bean trong context hoặc khi dùng annotation tổng hợp cho nhiều test.

## 6. @MockitoSpyBean: bọc bean thật bằng Mockito spy

**@MockitoSpyBean** dùng khi test muốn giữ implementation thật nhưng vẫn có thể quan sát hoặc stub một số phương thức.

Ví dụ, TaxCalculator là bean thật:

~~~java
@Component
public class TaxCalculator {

    public BigDecimal calculate(BigDecimal subtotal) {
        return subtotal.multiply(new BigDecimal("0.10"));
    }
}
~~~

Test bọc bean bằng spy:

~~~java
@SpringJUnitConfig(AppConfig.class)
class InvoiceServiceTest {

    @MockitoSpyBean
    TaxCalculator taxCalculator;

    @Autowired
    InvoiceService invoiceService;

    @Test
    void shouldUseTheRealTaxCalculator() {
        BigDecimal tax = taxCalculator.calculate(
                new BigDecimal("100.00")
        );

        assertThat(tax).isEqualByComparingTo("10.00");
        then(taxCalculator).should().calculate(
                new BigDecimal("100.00")
        );
    }
}
~~~

Spy giữ hành vi thật cho các method không stub. Nếu cần stub một method, cần tránh vô tình gọi implementation thật trong lúc cấu hình Mockito. Với spy, cách **doReturn(...).when(spy).method(...)** thường an toàn hơn **when(spy.method()).thenReturn(...)**, vì dạng thứ hai gọi method thật trước khi cài stubbing.

Ví dụ:

~~~java
doReturn(new BigDecimal("0.00"))
        .when(taxCalculator)
        .calculate(any(BigDecimal.class));
~~~

**@MockitoSpyBean** cần bean gốc tồn tại và bọc bean đó. Nó không phải lựa chọn để tạo một mock mới cho dependency chưa có trong context. Bean được spy phải phù hợp với giới hạn của hạ tầng override; đặc biệt, spy được hỗ trợ cho singleton bean.

### Khi nào nên dùng spy?

Spy có ích khi:

- Muốn kiểm tra một bean thật được gọi với đối số nào.
- Muốn thay một nhánh cụ thể trong một dependency nhưng giữ phần còn lại.
- Muốn test một luồng tích hợp mà không thay toàn bộ implementation.

Spy có thể làm test phụ thuộc implementation nội bộ và khiến hành vi thật chạy ngoài dự kiến. Nếu chỉ cần xác nhận contract của service, mock interface dependency hoặc dùng fake thường đơn giản và ổn định hơn.

## 7. So sánh @TestBean, @MockitoBean và @MockitoSpyBean

| Annotation | Bean được đưa vào context | Cần bean gốc? | Dùng khi |
|---|---|---|---|
| **@TestBean** | Instance do static factory method của test tạo | Không bắt buộc theo mặc định; có thể yêu cầu bằng enforceOverride | Fake/stub có hành vi do test kiểm soát |
| **@MockitoBean** | Mockito mock | Không bắt buộc theo mặc định; có thể yêu cầu bằng enforceOverride | Stub và verify dependency |
| **@MockitoSpyBean** | Mockito spy bọc bean thật | Có | Theo dõi hoặc stub có chọn lọc bean thật |

Không nên dùng ba annotation như các cách viết khác nhau cho cùng một mục đích:

- Chọn **@TestBean** khi cần một implementation test nhỏ, xác định và không cần framework mocking.
- Chọn **@MockitoBean** khi cần điều khiển kết quả và xác nhận tương tác của dependency.
- Chọn **@MockitoSpyBean** khi có lý do giữ implementation thật và chỉ can thiệp một phần.

Nếu test cần thay một service lớn bằng một mock chỉ để kiểm tra logic controller, **@MockitoBean** là lựa chọn phổ biến. Nếu test cần một fake repository trong bộ nhớ có quy tắc rõ ràng, **@TestBean** có thể giúp test dễ hiểu hơn.

## 8. Bean được chọn như thế nào?

Hạ tầng override cần xác định đúng bean trước khi thay. Việc chọn bean thường dựa trên kiểu field và các qualifier liên quan.

Một số quy tắc thực tế:

1. Nếu chỉ có một bean tương thích với kiểu field, Spring có thể chọn bean đó.
2. Nếu có nhiều bean cùng kiểu, thêm **@Qualifier** hoặc chỉ định tên bean.
3. Tên field có thể được dùng như qualifier fallback khi phân giải candidate.
4. Nếu không tìm được bean, **@MockitoBean** và **@TestBean** có thể tạo bean mới theo chiến lược mặc định; **enforceOverride = true** yêu cầu phải có bean gốc.
5. **@MockitoSpyBean** phải tìm được bean để bọc.

Ví dụ ứng dụng có hai implementation:

~~~java
@Configuration
class PaymentConfig {

    @Bean
    @Qualifier("card")
    PaymentGateway cardGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    @Qualifier("bank")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
~~~

Test muốn thay gateway ngân hàng:

~~~java
@MockitoBean
@Qualifier("bank")
PaymentGateway bankGateway;
~~~

Nếu chỉ khai báo một field kiểu **PaymentGateway** mà context có hai bean và không có thông tin phân biệt, Spring không nên tự chọn ngẫu nhiên. Hãy khai báo qualifier để ý định test rõ ràng.

Các bean override được thiết kế cho bean singleton. Nếu target là prototype hoặc một scope khác, không giả định cơ chế thay thế sẽ giữ nguyên semantics của scope. Đặc biệt, **@MockitoSpyBean** cần một singleton bean để bọc.

### Bean do FactoryBean tạo ra

Nếu bean mục tiêu được tạo thông qua **FactoryBean**, override nhắm tới object mà FactoryBean cung cấp. Với mock, Spring thay product bean bằng mock; với spy, Spring bọc object product được tạo ra. Test thường quan tâm dependency mà ứng dụng inject, không phải implementation của chính FactoryBean.

## 9. BeanOverride có thể mở rộng bằng annotation riêng

Một lợi ích quan trọng của BeanOverride infrastructure là cho phép dự án tạo annotation override riêng, thay vì chỉ dùng ba annotation có sẵn.

Ví dụ, một dự án có thể muốn annotation **@StubPaymentGateway** để thay gateway bằng một fake dùng chung trong nhiều test. Annotation riêng giúp nhóm thống nhất cách tạo fake và tránh lặp factory method.

Một annotation tùy chỉnh được đánh dấu bằng meta-annotation **@BeanOverride** của Spring Test. Meta-annotation này liên kết annotation tùy chỉnh với một implementation của **BeanOverrideProcessor**. Ví dụ:

~~~java
import org.springframework.test.context.bean.override.BeanOverride;

@Target(ElementType.FIELD)
@Retention(RetentionPolicy.RUNTIME)
@BeanOverride(StubPaymentGatewayProcessor.class)
public @interface StubPaymentGateway {
}
~~~

**StubPaymentGatewayProcessor** là processor do dự án triển khai. Processor đọc metadata annotation và tạo một hoặc nhiều **BeanOverrideHandler** mô tả việc override cần thực hiện.

Ở mức khái niệm, processor cần xác định:

- Kiểu bean nào sẽ được thay.
- Bean name hoặc qualifier nào dùng để phân biệt target.
- Chiến lược nào được áp dụng: **REPLACE**, **REPLACE_OR_CREATE** hoặc **WRAP**.
- Cách tạo instance thay thế hoặc cách bọc bean hiện có.
- Field test nào cần nhận instance override, nếu annotation hỗ trợ field injection.

**BeanOverrideHandler** đóng gói thông tin cần thiết để Spring Test áp dụng override trong quá trình xây dựng context. Processor không nên tự sửa singleton bean sau khi test đã bắt đầu; nó phải mô tả override để hạ tầng áp dụng đúng lifecycle.

### Khi nào cần annotation riêng?

Tạo annotation riêng khi dự án có một quy ước override lặp lại và có ý nghĩa rõ ràng, ví dụ:

- Thay một adapter bên ngoài bằng fake chuẩn của test suite.
- Thay clock hoặc ID generator bằng implementation xác định.
- Tạo mock có cấu hình mặc định dùng chung.
- Bọc một bean để thu thập event hoặc metrics trong test.

Nếu chỉ có một test cần fake đơn giản, **@TestBean** thường đã đủ. Không cần xây processor mới chỉ để tránh viết vài dòng factory method.

## 10. Phạm vi áp dụng và vòng đời override

Bean override được áp dụng trong ApplicationContext do Spring Test quản lý. Khi TestContext Framework chuẩn bị context, các override được phát hiện và đăng ký trước khi test sử dụng bean.

Điều này có một số hệ quả:

- Bean thay thế được sử dụng bởi các bean khác trong context, không chỉ bởi field test.
- Override thuộc cấu hình test context; nó không thay đổi cấu hình bean của ứng dụng production.
- Test class có thể dùng chung cached context nếu cấu hình tương thích.
- Mocks và spies có vòng đời gắn với context; stubbing và invocation cần được quản lý giữa các test method.
- Việc thay đổi bean trong context không tự dọn dữ liệu database, cache hoặc hệ thống ngoài context.

Với **@MockitoBean** và **@MockitoSpyBean**, Spring Test mặc định reset Mockito mock/spy sau mỗi test method. Có thể cấu hình chế độ reset bằng thuộc tính **reset** khi cần. Dù vậy, không nên dựa vào thứ tự test để giữ stub hoặc invocation history từ method trước.

Khi test chạy song song, một cached context có thể được chia sẻ. Mock được reset theo lifecycle không có nghĩa mọi thao tác đồng thời trên cùng mock đều trở nên độc lập. Tránh để nhiều test method cùng sửa stubbing hoặc xác nhận invocation trên một mock dùng chung trong cùng thời điểm.

## 11. BeanOverride trong context hierarchy

Một số test dùng **@ContextHierarchy** để tạo nhiều cấp ApplicationContext, ví dụ root context chứa service và child context chứa web layer.

Khi có nhiều context, cần xác định override thuộc cấp nào. Một override áp dụng sai context có thể tạo mock ở root trong khi bean thực tế được lấy từ child, hoặc ngược lại.

Các annotation override hiện đại có hỗ trợ metadata để chỉ định context hierarchy level trong những phiên bản tương ứng, chẳng hạn thuộc tính **contextName**. Tên này cần khớp với tên cấu hình context đã khai báo trong hierarchy.

Ví dụ minh họa:

~~~java
@ContextHierarchy({
        @ContextConfiguration(name = "root", classes = RootConfig.class),
        @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class WebLayerTest {

    @MockitoBean(contextName = "root")
    PaymentGateway paymentGateway;
}
~~~

Dùng **contextName** khi test thực sự có hierarchy và cần giới hạn override ở một cấp cụ thể. Nếu chỉ có một ApplicationContext, không cần thêm thuộc tính này.

## 12. Quan hệ với Spring Boot @MockBean và @SpyBean

Trước khi Spring Framework có BeanOverride infrastructure, Spring Boot cung cấp **@MockBean** và **@SpyBean** để thay hoặc spy bean trong test context.

Từ Spring Framework 6.2, Spring cung cấp **@MockitoBean** và **@MockitoSpyBean** trong chính Spring Test. Spring Boot 3.4 chuyển hướng sang các annotation mới và đánh dấu **@MockBean**/**@SpyBean** cũ là deprecated để chuyển đổi.

| API cũ | API mới |
|---|---|
| Spring Boot **@MockBean** | Spring Framework **@MockitoBean** |
| Spring Boot **@SpyBean** | Spring Framework **@MockitoSpyBean** |

Khi nâng cấp dự án:

- Kiểm tra phiên bản Spring Framework mà Spring Boot BOM đang quản lý.
- Đổi import sang package của Spring Framework khi phiên bản hỗ trợ.
- Kiểm tra lại thuộc tính annotation vì API cũ và mới không nhất thiết giống nhau hoàn toàn.
- Không trộn annotation cũ và mới trên cùng một bean override nếu không có lý do rõ ràng.
- Chạy test slice và test context có nhiều candidate để xác nhận bean được chọn đúng.

Ví dụ import của annotation mới:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.context.bean.override.convention.TestBean;
~~~

Nếu dự án còn dùng Spring Framework 6.1 hoặc Spring Boot cũ hơn, các annotation mới có thể chưa tồn tại. Không thể giải quyết bằng cách chỉ đổi import; cần nâng cấp dependency phù hợp hoặc tiếp tục dùng API được phiên bản hiện tại hỗ trợ.

## 13. Kết hợp BeanOverride với test slice

Test slice chỉ nạp một phần ApplicationContext. Điều này làm BeanOverride đặc biệt hữu ích vì dependency của controller có thể không nằm trong slice.

Ví dụ Spring Boot MVC slice:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void shouldReturnOrder() throws Exception {
        given(orderService.findById(42L))
                .willReturn(new OrderResponse(42L, "PAID"));

        mockMvc.perform(get("/api/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

**@WebMvcTest** nạp MVC slice và controller được chọn. **@MockitoBean** cung cấp service mock để controller có thể được tạo trong context. Mock được sử dụng cả khi test stub hành vi và khi controller gọi dependency trong request.

Với một integration test nạp toàn bộ ứng dụng, có thể dùng **enforceOverride = true** để bảo đảm bean gốc thực sự có trong cấu hình trước khi thay:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @MockitoBean(enforceOverride = true)
    PaymentGateway paymentGateway;
}
~~~

Không dùng mock để thay những thành phần mà chính test cần xác nhận. Ví dụ, nếu mục tiêu là kiểm tra repository và transaction thật, không thay repository bằng mock; chỉ thay dependency bên ngoài phạm vi cần kiểm thử.

## 14. BeanOverride và AOT

AOT (Ahead-of-Time) trong Spring chuẩn bị một phần thông tin ứng dụng ở thời điểm build để giảm công việc phải làm khi khởi động hoặc hỗ trợ native image. TestContext Framework cũng có cơ chế AOT dành cho test context trong các phiên bản Spring hỗ trợ.

BeanOverride là một phần của quá trình tùy biến test ApplicationContext. Annotation override được đọc trong lúc Spring Test chuẩn bị context; processor và handler mô tả bean cần thay trước khi test chạy.

Cần phân biệt ba việc:

1. **AOT của ứng dụng production:** chuẩn bị metadata và mã khởi tạo cho application context production. Bean override chỉ dành cho test không tự động trở thành bean của production.
2. **AOT của test context:** chuẩn bị context dùng trong test. Nếu test dùng annotation override, cơ chế tạo context phải nhận được metadata và processor tương ứng.
3. **Chạy test trong native image:** ngoài việc tạo context, còn phải bảo đảm các thư viện mocking, reflection, proxy và runtime hints phù hợp với môi trường native.

Với annotation override tùy chỉnh, processor phải có mặt trong test runtime và tương thích với quy trình AOT mà dự án sử dụng. Nếu processor dựa vào reflection, classpath scanning hoặc tạo proxy động, cần kiểm tra các yêu cầu runtime hints và giới hạn của native image theo phiên bản Spring/GraalVM cụ thể.

Không nên kết luận rằng một test dùng **@MockitoBean** chạy trên JVM thì tự động chạy được trong native image. Ngược lại, cũng không nên giả định mọi bean override đều không tương thích AOT. Hãy kiểm tra hỗ trợ của phiên bản Spring đang dùng, cách test context được AOT xử lý và khả năng của thư viện mock trong runtime mục tiêu.

## 15. Những lỗi thường gặp khi dùng BeanOverride

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Context không khởi tạo vì có nhiều bean cùng kiểu | Không xác định rõ bean cần override | Dùng **@Qualifier**, tên field hoặc **name** |
| Test chạy dù bean gốc bị thiếu | **@MockitoBean** mặc định có thể tạo bean mới | Dùng **enforceOverride** khi cần yêu cầu bean phải tồn tại |
| **@MockitoSpyBean** không tìm thấy bean | Spy cần bean hiện có để bọc | Kiểm tra component scan/configuration và context slice |
| Spy gọi implementation thật ngoài dự kiến | Stubbing dùng **when(spy.method())** đã gọi method thật | Dùng **doReturn(...).when(spy).method(...)** khi phù hợp |
| Test method sau nhận mock history không mong muốn | Mock/spy dùng chung cached context hoặc reset mode khác dự kiến | Kiểm tra **reset**, không phụ thuộc thứ tự test |
| Override đặt sai context trong hierarchy | Annotation được áp dụng ở cấp context không chứa target | Chỉ định context level phù hợp |
| Không thể override bean scope tùy ý | BeanOverride nhắm tới bean singleton | Thiết kế dependency test phù hợp hoặc dùng cơ chế khác |
| Test slice tạo mock ngoài dự kiến | Context không nạp bean gốc nhưng chiến lược cho phép tạo mới | Dùng **enforceOverride** nếu cần xác minh wiring |
| Annotation custom không được phát hiện | Thiếu **@BeanOverride** hoặc processor không được cấu hình đúng | Kiểm tra meta-annotation và processor |
| JVM test chạy nhưng native test thất bại | Reflection/proxy/mock library cần runtime support | Kiểm tra AOT/native hints và hỗ trợ phiên bản |

Một lỗi khác là dùng BeanOverride để che lỗi cấu hình. Nếu test luôn tạo mock mới khi bean thật bị thiếu, test có thể vẫn xanh dù component scan hoặc auto-configuration đã hỏng. Với test xác nhận wiring, hãy yêu cầu bean gốc phải tồn tại.

## 16. Chọn cơ chế phù hợp

| Nhu cầu | Lựa chọn |
|---|---|
| Tạo fake bằng code của test | **@TestBean** |
| Mock dependency và stub/verify tương tác | **@MockitoBean** |
| Giữ bean thật nhưng theo dõi hoặc stub có chọn lọc | **@MockitoSpyBean** |
| Thêm một bean test độc lập, không thay bean hiện có | **@TestConfiguration** và **@Import** |
| Cần bảo đảm bean gốc có trong context | **enforceOverride = true** |
| Có nhiều bean cùng kiểu | **@Qualifier** hoặc tên bean rõ ràng |
| Cần quy ước override dùng chung cho dự án | Custom annotation với **@BeanOverride** và **BeanOverrideProcessor** |
| Dùng nhiều context trong hierarchy | Chỉ định context level phù hợp |
| Test native/AOT | Xác nhận hỗ trợ của Spring version, processor và mocking library |

**@TestConfiguration** vẫn có vị trí riêng. Nếu muốn bổ sung một bean test độc lập mà không thay bean nào, cấu hình test là lựa chọn phù hợp. BeanOverride phù hợp khi ý định chính là thay hoặc bọc một bean đã được chọn.

## 17. Nguyên tắc thiết kế test dễ bảo trì

- Chỉ override dependency nằm ngoài phạm vi mà test muốn xác nhận.
- Dùng interface ở ranh giới tích hợp để mock/fake dễ dàng.
- Dùng **enforceOverride = true** khi sự tồn tại của bean thật là một phần điều kiện test.
- Đặt qualifier hoặc tên bean rõ ràng khi có nhiều implementation.
- Dùng fake cho hành vi có quy tắc và mock cho tương tác cần xác nhận.
- Dùng spy có chọn lọc vì spy vẫn chạy code thật.
- Không dựa vào stubbing hoặc invocation history của test method trước.
- Không dùng override để che lỗi component scan, profile hoặc auto-configuration.
- Với custom processor, giữ logic chọn bean và tạo handler nhỏ, xác định, dễ kiểm tra.
- Khi dùng AOT/native image, xác nhận riêng test context và thư viện mocking ở runtime mục tiêu.

BeanOverride infrastructure chuẩn hóa cách Spring Test thay bean trong ApplicationContext. **@TestBean** tạo instance theo factory method, **@MockitoBean** thay dependency bằng mock, còn **@MockitoSpyBean** bọc bean thật. Khi chọn đúng chiến lược, bean mục tiêu và phạm vi context, test có thể cô lập dependency mà vẫn giữ cấu hình Spring có ý nghĩa đối với hành vi đang được kiểm tra.

