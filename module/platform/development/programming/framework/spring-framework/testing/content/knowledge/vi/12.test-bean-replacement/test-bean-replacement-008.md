# Phạm vi singleton, FactoryBean và khác biệt theo phiên bản

Khi thay một bean trong kiểm thử Spring, cần hiểu bean đó có scope nào và nó được tạo trực tiếp hay thông qua **FactoryBean**. Những chi tiết này quyết định test có thể thay bean hay không, object nào thực sự bị thay và liệu test có giữ được hành vi vòng đời của ứng dụng hay không.

Từ Spring Framework 6.2, Spring TestContext cung cấp cơ chế bean overriding chuyên biệt với **@TestBean**, **@MockitoBean** và **@MockitoSpyBean**. Cơ chế này có quy tắc riêng về scope và FactoryBean. Đặc biệt, quy tắc dành cho bean không phải singleton đã thay đổi giữa nhánh Framework 6.2 và 7.0. Nếu dùng tài liệu của phiên bản khác với phiên bản đang chạy, test có thể thất bại khi tạo context hoặc vô tình biến một dependency theo request thành object dùng chung.

Bài học này giải thích singleton scope trong Spring, cách bean override xử lý các scope khác, sự khác nhau giữa FactoryBean và object do nó tạo ra, cùng các thay đổi quan trọng theo phiên bản Spring Framework và Spring Boot.

## 1. Bean overriding trong kiểm thử là gì?

Bean overriding trong test là việc thay một bean trong ApplicationContext bằng một object khác dành cho test. Mục tiêu thường là cô lập một dependency bên ngoài, giả lập lỗi khó tái hiện hoặc quan sát tương tác mà không cần gọi hệ thống thật.

Ví dụ, OrderService phụ thuộc vào PaymentGateway:

~~~java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    public OrderService(
            PaymentGateway paymentGateway,
            OrderRepository orderRepository
    ) {
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
    }

    public OrderResult placeOrder(OrderCommand command) {
        var payment = paymentGateway.charge(command.amount());

        if (!payment.approved()) {
            return OrderResult.rejected();
        }

        var order = orderRepository.save(
                new Order(command.customerId(), command.amount())
        );

        return OrderResult.created(order.getId());
    }
}
~~~

Khi kiểm tra controller hoặc toàn bộ service layer, ta có thể muốn giữ OrderService thật nhưng thay PaymentGateway bằng Mockito mock:

~~~java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @MockitoBean
    private PaymentGateway paymentGateway;

    @Test
    void shouldCreateOrderWhenPaymentIsApproved() {
        when(paymentGateway.charge(any()))
                .thenReturn(PaymentResult.approved());

        var result = orderService.placeOrder(
                new OrderCommand("customer-1", new BigDecimal("250000"))
        );

        assertEquals(OrderStatus.CREATED, result.status());
        verify(paymentGateway).charge(new BigDecimal("250000"));
    }
}
~~~

**@MockitoBean** yêu cầu Spring TestContext tạo Mockito mock và đăng ký nó trong context theo quy tắc bean override. Các bean khác inject PaymentGateway sẽ nhận mock đó.

Spring Framework 6.2 bổ sung ba annotation chính:

| Annotation | Cách hoạt động | Mục đích |
|---|---|---|
| @TestBean | Thay bean bằng object do static factory method của test cung cấp | Dùng fake hoặc implementation riêng |
| @MockitoBean | Thay bean bằng Mockito mock | Kiểm soát phản hồi và xác minh lời gọi |
| @MockitoSpyBean | Bọc instance thật bằng Mockito spy | Giữ phần lớn hành vi thật và theo dõi tương tác |

Cả ba annotation dùng hạ tầng bean override của Spring TestContext. Vì vậy, các quy tắc về scope, FactoryBean và cách tìm bean áp dụng ở cấp hạ tầng, không chỉ riêng Mockito.

## 2. Singleton scope trong Spring có nghĩa gì?

Singleton là scope mặc định của bean Spring. Với một bean definition trong một Spring IoC container, Spring quản lý một instance dùng chung. Các thành phần inject cùng bean đó sẽ nhận cùng instance trong context tương ứng.

Ví dụ:

~~~java
@Component
public class PaymentAuditService {
    // Bean singleton theo mặc định.
}
~~~

Tương đương với khai báo scope tường minh:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
public class PaymentAuditService {
}
~~~

Singleton của Spring có phạm vi **mỗi container và mỗi bean definition**. Nó không phải singleton toàn JVM như mẫu thiết kế GoF. Hai ApplicationContext riêng biệt có thể có hai instance riêng của cùng một class.

Các scope thường gặp:

| Scope | Vòng đời instance |
|---|---|
| singleton | Một instance cho bean definition trong một container |
| prototype | Tạo instance mới mỗi lần container yêu cầu bean |
| request | Một instance cho mỗi HTTP request |
| session | Một instance cho mỗi HTTP session |
| application | Một instance theo ServletContext |
| websocket | Một instance theo WebSocket session |
| Custom scope | Theo quy tắc của Scope được đăng ký |

Các scope web chỉ hoạt động trong web-aware ApplicationContext. Prototype có thể dùng trong context thông thường.

Ví dụ một bean prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class RequestToken {

    private final String value = UUID.randomUUID().toString();

    public String value() {
        return value;
    }
}
~~~

Mỗi lần gọi getBean(RequestToken.class), Spring tạo một instance mới. Nếu inject trực tiếp prototype vào một singleton, dependency được giải quyết một lần khi singleton được tạo; muốn lấy instance mới trong từng lần xử lý, thường cần ObjectProvider, Provider hoặc method injection.

Điểm cần nhớ khi thay bean trong test: một mock thường là object duy nhất được tạo cho context test. Nếu bean gốc có vòng đời theo request hoặc prototype, việc thay nó bằng một mock singleton có thể làm thay đổi ý nghĩa của test.

## 3. Các chiến lược bean override

Hạ tầng bean override của Spring có ba chiến lược:

| Chiến lược | Hành vi | Annotation thường dùng |
|---|---|---|
| REPLACE | Thay bean hiện có; báo lỗi nếu không tìm thấy bean | @TestBean khi bật enforceOverride |
| REPLACE_OR_CREATE | Thay bean nếu có; tạo bean mới nếu chưa có | Mặc định của @TestBean và @MockitoBean |
| WRAP | Lấy instance hiện có và bọc nó | @MockitoSpyBean |

### 3.1. @MockitoBean: thay bằng mock

~~~java
@SpringBootTest
class PaymentServiceTest {

    @Autowired
    private PaymentService paymentService;

    @MockitoBean
    private PaymentGateway paymentGateway;
}
~~~

Mặc định, @MockitoBean dùng REPLACE_OR_CREATE. Nếu không có bean phù hợp, Spring có thể tạo mock mới và đăng ký vào context.

Điều này hữu ích khi test cần cung cấp một dependency mà cấu hình slice test không nạp. Tuy nhiên, nếu mục tiêu là xác minh ứng dụng thực sự có bean production, việc tự tạo mock khi bean gốc bị thiếu có thể che lỗi cấu hình.

Dùng enforceOverride = true để yêu cầu bean phải tồn tại:

~~~java
@MockitoBean(enforceOverride = true)
private PaymentGateway paymentGateway;
~~~

Khi đó, Spring dùng chiến lược REPLACE. Nếu không tìm thấy bean phù hợp, quá trình tạo context thất bại. Đây là lựa chọn phù hợp khi muốn bảo đảm test đang thay đúng một dependency đã được cấu hình trong ứng dụng.

### 3.2. @MockitoSpyBean: bọc bean thật

~~~java
@SpringBootTest
class PricingServiceTest {

    @MockitoSpyBean
    private PricingService pricingService;

    @Test
    void shouldCalculatePriceUsingRealImplementation() {
        var result = pricingService.calculate(sampleOrder());

        assertTrue(result.total().signum() > 0);
        verify(pricingService).calculate(any());
    }
}
~~~

@MockitoSpyBean dùng chiến lược WRAP. Spring lấy instance thật và tạo spy từ instance đó. Test có thể gọi logic thật, đồng thời stub hoặc verify một số phương thức.

Chiến lược này cần đúng một bean phù hợp. Nếu có nhiều bean cùng loại và không xác định được bean đích, test sẽ thất bại. Dùng @Qualifier hoặc tên bean để xác định rõ ứng viên.

Khi stub spy, nên cân nhắc doReturn(...).when(spy)... hoặc doThrow(...).when(spy)... nếu lời gọi thật có thể tạo side effect trong lúc thiết lập stub.

### 3.3. @TestBean: thay bằng fake do test cung cấp

@TestBean dùng một static factory method để tạo object thay thế:

~~~java
@SpringBootTest
class OrderServiceTest {

    @TestBean
    private PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Theo quy ước, Spring tìm factory method dựa trên tên field. Có thể khai báo tên method khác bằng thuộc tính methodName. Factory method phải là static, không nhận tham số và trả về kiểu tương thích với bean cần thay.

@TestBean cũng hỗ trợ enforceOverride. Khi cần kiểm tra bean production đã tồn tại, hãy bật thuộc tính này để test thất bại nếu không tìm được bean đích.

## 4. Phạm vi singleton trong Spring Framework 6.2

Trong tài liệu Spring Framework 6.2.x, bean overriding chỉ hỗ trợ bean có scope singleton. Nếu test cố thay một bean prototype hoặc bean có scope khác, Spring ném exception trong quá trình chuẩn bị ApplicationContext.

Ví dụ bean prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TokenGenerator {

    public String generate() {
        return UUID.randomUUID().toString();
    }
}
~~~

Test sau không hợp lệ theo quy tắc bean override của Framework 6.2.x:

~~~java
@SpringBootTest
class TokenGeneratorTest {

    @MockitoBean
    private TokenGenerator tokenGenerator;
}
~~~

Bean đích là prototype, vì vậy Spring Framework 6.2.x từ chối override. Thay @MockitoBean bằng @MockitoSpyBean hoặc @TestBean cũng không giải quyết được giới hạn chung này.

Lý do liên quan đến vòng đời object. Prototype được thiết kế để tạo nhiều instance theo từng lần yêu cầu. Một mock hoặc object thay thế được quản lý như instance override trong context không thể giữ nguyên hợp đồng tạo mới của prototype theo cơ chế 6.2.

Đối với request, session hoặc custom scope, giới hạn tương tự cũng áp dụng: nếu bean đích được nhận diện là non-singleton, hạ tầng override 6.2.x từ chối thao tác.

Điều này không có nghĩa Spring không hỗ trợ các scope đó trong ứng dụng. Nó chỉ mô tả giới hạn của cơ chế thay bean dành cho test ở phiên bản này.

## 5. Khác biệt từ Spring Framework 7.0 với bean không phải singleton

Tài liệu bean overriding của Spring Framework 7.0 mô tả hành vi mới đối với bean non-singleton: khi thay bean đó, Spring đăng ký instance override dưới dạng singleton và chuyển scope của bean definition tương ứng thành singleton.

Điều này khác với quy tắc 6.2.x:

| Phiên bản | Khi override bean prototype hoặc scoped |
|---|---|
| Spring Framework 6.2.x | Từ chối override non-singleton và ném exception |
| Spring Framework 7.0 | Thay bằng override instance singleton; bean definition được chuyển thành singleton |

Ví dụ với prototype:

~~~java
@SpringBootTest
class TokenGeneratorTest {

    @MockitoBean(enforceOverride = true)
    private TokenGenerator tokenGenerator;

    @Test
    void shouldReturnStubbedToken() {
        when(tokenGenerator.generate()).thenReturn("test-token");

        assertEquals("test-token", tokenGenerator.generate());
    }
}
~~~

Với Framework 7.0, bean prototype có thể được thay bằng mock singleton. Test có thể chạy, nhưng mock không còn được tạo mới theo từng lần lấy bean như prototype gốc.

Đây là thay đổi có ảnh hưởng đến ngữ nghĩa test. Nếu code production phụ thuộc vào việc mỗi lần lấy prototype nhận được một object độc lập, một mock singleton không mô phỏng được hành vi đó.

Tương tự, thay request-scoped bean bằng singleton mock có thể khiến nhiều request trong cùng context test quan sát cùng một object. Test có thể không phát hiện lỗi do state bị chia sẻ giữa các request.

Với @MockitoSpyBean, Framework 7.0 cũng chuyển bean definition non-singleton thành singleton khi tạo spy cho bean đó. Cần đọc riêng trường hợp scoped proxy: @MockitoSpyBean không hỗ trợ spy trực tiếp scoped proxy, ví dụ bean dùng @Scope(proxyMode = ScopedProxyMode.TARGET_CLASS). Trường hợp đó có thể thất bại ngay cả khi phiên bản hỗ trợ chuyển scope.

### Ví dụ về rủi ro thay đổi scope

Giả sử một bean giữ trạng thái theo request:

~~~java
@Component
@RequestScope
public class RequestContextData {

    private String correlationId;

    public void setCorrelationId(String correlationId) {
        this.correlationId = correlationId;
    }

    public String getCorrelationId() {
        return correlationId;
    }
}
~~~

Trong ứng dụng thật, mỗi HTTP request có instance riêng. Nếu test ở Framework 7.0 thay bean này bằng singleton mock, hai lần xử lý request có thể dùng chung mock đó.

Nếu test chỉ kiểm tra một request, kết quả có thể vẫn đúng. Nhưng test đó không chứng minh state được cô lập giữa các request.

Khi cần kiểm tra đúng vòng đời request, hãy chạy test với request scope thật và tạo hai request riêng biệt. Không dùng một singleton mock làm bằng chứng cho tính cô lập theo request.

## 6. Vì sao thay non-singleton thành singleton có thể làm test sai ý nghĩa?

Scope là một phần của hợp đồng bean. Khi test thay đổi scope, những thuộc tính sau có thể thay đổi:

- Một hay nhiều instance được sử dụng.
- Thời điểm tạo object.
- Thời điểm hủy object.
- State có được chia sẻ giữa request hoặc session không.
- Dependency có được tạo lại mỗi lần yêu cầu không.
- Các callback khởi tạo và hủy theo scope có được thực thi như trong ứng dụng thật không.

Ví dụ, một prototype object có bộ đếm nội bộ:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class OperationCounter {

    private int count;

    public int next() {
        return ++count;
    }
}
~~~

Với prototype thật, hai lần lấy bean tạo hai object:

~~~java
var first = context.getBean(OperationCounter.class);
var second = context.getBean(OperationCounter.class);

assertNotSame(first, second);
assertEquals(1, first.next());
assertEquals(1, second.next());
~~~

Nếu thay bean bằng singleton mock, assertion về identity và state không còn phản ánh scope ban đầu.

Vì vậy, khi dùng Framework 7.0 để thay non-singleton, hãy xem đó là một lựa chọn cô lập dependency cho một test cụ thể. Nếu mục tiêu của test là kiểm tra chính vòng đời prototype hoặc scoped bean, cần giữ scope thật và kiểm tra qua container.

## 7. FactoryBean là gì?

FactoryBean là một hợp đồng của Spring cho phép một object tạo ra object khác để container quản lý. Khi một bean definition dùng FactoryBean, tên bean thông thường trỏ đến object do factory tạo ra. Muốn lấy chính factory object, dùng tiền tố & trước tên bean.

Ví dụ:

~~~java
public class RemoteClientFactoryBean
        implements FactoryBean<RemoteClient> {

    @Override
    public RemoteClient getObject() {
        return new DefaultRemoteClient();
    }

    @Override
    public Class<?> getObjectType() {
        return RemoteClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}
~~~

Đăng ký factory:

~~~java
@Configuration(proxyBeanMethods = false)
class RemoteClientConfiguration {

    @Bean
    RemoteClientFactoryBean remoteClient() {
        return new RemoteClientFactoryBean();
    }
}
~~~

Có hai object cần phân biệt:

~~~text
ApplicationContext
      |
      +-- remoteClient (FactoryBean)
      |        |
      |        +-- getObject()
      |                |
      |                v
      |          RemoteClient product
      |
      +-- getBean("remoteClient")   -> RemoteClient product
      |
      +-- getBean("&remoteClient")  -> RemoteClientFactoryBean
~~~

Các cách truy cập:

~~~java
RemoteClient client =
        context.getBean("remoteClient", RemoteClient.class);

FactoryBean<?> factory =
        context.getBean("&remoteClient", FactoryBean.class);
~~~

Phương thức isSingleton() của FactoryBean mô tả scope của product do factory tạo ra. Nó không phải cách khai báo scope của chính factory object. Đây là một điểm dễ nhầm khi phân tích singleton behavior.

## 8. Khi thay bean được tạo bởi FactoryBean

Trong bean overriding, cần phân biệt chiến lược thay thế và chiến lược bọc.

### 8.1. @MockitoBean thay product và thay FactoryBean trong context

Giả sử RemoteClientFactoryBean tạo ra RemoteClient. Test muốn thay RemoteClient bằng mock:

~~~java
@SpringBootTest
class RemoteClientConsumerTest {

    @MockitoBean(enforceOverride = true)
    private RemoteClient remoteClient;
}
~~~

Spring xác định bean theo kiểu product RemoteClient. Khi thay bean được tạo bởi FactoryBean, hạ tầng override thay chính đăng ký FactoryBean bằng một bean singleton tương ứng với mock product type.

Kết quả mà các thành phần inject RemoteClient nhận được là Mockito mock. Factory không còn là object tạo product trong context test cho bean đã bị thay.

Cần hiểu rằng test đang thay product mà ứng dụng sử dụng, không kiểm tra logic bên trong RemoteClientFactoryBean.

### 8.2. @MockitoSpyBean spy product do FactoryBean tạo ra

Nếu dùng:

~~~java
@SpringBootTest
class RemoteClientSpyTest {

    @MockitoSpyBean
    private RemoteClient remoteClient;
}
~~~

Spring tạo spy từ object do FactoryBean tạo ra. Spy được đặt quanh product RemoteClient, không phải quanh RemoteClientFactoryBean.

Do đó:

- Các lời gọi đến RemoteClient có thể được quan sát bằng Mockito.
- Logic getObject() của factory không tự động trở thành đối tượng spy.
- Test không thể dùng field RemoteClient để xác minh lời gọi nội bộ trên factory.
- Factory có thể được khởi tạo sớm để lấy product cần bọc.

Nếu mục tiêu là kiểm tra factory tạo đúng product, hãy kiểm tra factory riêng hoặc dùng context test giữ factory thật và xác minh product được tạo ra. Nếu mục tiêu là cô lập consumer khỏi remote client, override product bằng mock sẽ phù hợp hơn.

### 8.3. @TestBean cũng thay FactoryBean theo product

@TestBean thay bean bằng object do static factory method của test trả về. Nếu bean đích là product do FactoryBean tạo, hạ tầng thay đăng ký FactoryBean bằng singleton bean tương ứng với object do test factory method cung cấp.

Ví dụ:

~~~java
@SpringBootTest
class RemoteClientConsumerTest {

    @TestBean
    private RemoteClient remoteClient;

    static RemoteClient remoteClient() {
        return new FakeRemoteClient();
    }
}
~~~

Test sử dụng FakeRemoteClient thay product. Nó không kiểm tra RemoteClientFactoryBean.getObject().

## 9. Scope của FactoryBean và scope của product

Một FactoryBean có thể tạo product singleton hoặc product không singleton. Cần đọc cả bean definition lẫn phương thức isSingleton() để hiểu vòng đời.

Ví dụ product singleton:

~~~java
@Override
public boolean isSingleton() {
    return true;
}
~~~

Spring cache product và trả lại cùng product cho các lần truy cập thông thường trong context.

Nếu factory trả về:

~~~java
@Override
public boolean isSingleton() {
    return false;
}
~~~

Spring không xem product là singleton. Việc lấy product có thể tạo instance mới theo hợp đồng của FactoryBean.

Điều này quan trọng khi bean override nhắm vào product:

- Với Framework 6.2.x, nếu product được xem là non-singleton, bean override bị từ chối theo giới hạn singleton.
- Với Framework 7.0, khi thay product qua bean override, factory registration được thay bằng singleton override instance.
- Với @MockitoSpyBean, spy được tạo trên product do factory tạo ra; nó không biến factory thành spy.

Vì vậy, không nên suy ra scope của product chỉ từ tên class FactoryBean. Hãy kiểm tra isSingleton() và cách bean được đăng ký.

## 10. Ví dụ hoàn chỉnh: thay RemoteClient được tạo bởi FactoryBean

Giả sử ứng dụng có interface:

~~~java
public interface RemoteClient {
    RemoteResult fetch(String id);
}
~~~

Factory tạo client:

~~~java
public class RemoteClientFactoryBean
        implements FactoryBean<RemoteClient> {

    @Override
    public RemoteClient getObject() {
        return new HttpRemoteClient();
    }

    @Override
    public Class<?> getObjectType() {
        return RemoteClient.class;
    }

    @Override
    public boolean isSingleton() {
        return true;
    }
}
~~~

Consumer:

~~~java
@Service
public class RemoteDataService {

    private final RemoteClient remoteClient;

    public RemoteDataService(RemoteClient remoteClient) {
        this.remoteClient = remoteClient;
    }

    public RemoteResult load(String id) {
        return remoteClient.fetch(id);
    }
}
~~~

Test thay product bằng mock:

~~~java
@SpringBootTest
class RemoteDataServiceTest {

    @Autowired
    private RemoteDataService remoteDataService;

    @MockitoBean(enforceOverride = true)
    private RemoteClient remoteClient;

    @Test
    void shouldReturnRemoteResult() {
        var expected = new RemoteResult("item-1", "ready");

        when(remoteClient.fetch("item-1"))
                .thenReturn(expected);

        var actual = remoteDataService.load("item-1");

        assertEquals(expected, actual);
        verify(remoteClient).fetch("item-1");
    }
}
~~~

Test giữ RemoteDataService thật và thay dependency product RemoteClient. Nó không cần khởi tạo HTTP connection thật.

Nếu muốn kiểm tra factory, hãy viết test riêng:

~~~java
class RemoteClientFactoryBeanTest {

    @Test
    void shouldCreateRemoteClientProduct() throws Exception {
        var factory = new RemoteClientFactoryBean();

        var client = factory.getObject();

        assertNotNull(client);
        assertEquals(RemoteClient.class, factory.getObjectType());
        assertTrue(factory.isSingleton());
    }
}
~~~

Ví dụ thứ hai tạo factory trực tiếp và kiểm tra hợp đồng của nó. Khi cần xác minh việc Spring đăng ký factory và phân giải product theo tên bean, có thể bổ sung context test dùng cấu hình factory thật.

## 11. Cách tìm bean đích: type, qualifier và tên bean

Hạ tầng bean override cần xác định rõ bean nào sẽ bị thay. Thông thường, Spring suy luận theo kiểu field hoặc parameter được đánh dấu. Nếu có nhiều bean cùng kiểu, cần bổ sung qualifier hoặc tên.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway cardPaymentGateway() {
        return new CardPaymentGateway();
    }

    @Bean
    PaymentGateway bankPaymentGateway() {
        return new BankPaymentGateway();
    }
}
~~~

Test chỉ rõ bean cần thay:

~~~java
@SpringBootTest
class CardPaymentServiceTest {

    @MockitoBean
    @Qualifier("cardPaymentGateway")
    private PaymentGateway paymentGateway;
}
~~~

Hoặc dùng tên bean trong annotation:

~~~java
@MockitoBean(name = "cardPaymentGateway")
private PaymentGateway paymentGateway;
~~~

Khi dùng field-level annotation, tên field cũng có thể được dùng làm qualifier dự phòng nếu không khai báo @Qualifier.

Với khai báo ở cấp class, kiểu cần thay được cung cấp qua thuộc tính types:

~~~java
@SpringBootTest
@MockitoBean(types = PaymentGateway.class, name = "cardPaymentGateway")
class CardPaymentServiceTest {
}
~~~

Một quy tắc thực tế: nếu test quan tâm một implementation cụ thể, hãy khai báo qualifier hoặc tên bean rõ ràng. Điều đó giúp tránh thay nhầm bean khi ứng dụng bổ sung implementation mới.

## 12. Phân biệt bean override với cho phép trùng bean definition

Có hai cơ chế thường bị nhầm:

**Bean overriding trong Spring TestContext**

- Dùng @TestBean, @MockitoBean, @MockitoSpyBean.
- Có chiến lược REPLACE, REPLACE_OR_CREATE, WRAP.
- Có quy tắc riêng về scope, FactoryBean và lựa chọn bean.
- Được xử lý bởi hạ tầng test của Spring.

**Bean definition overriding trong container**

- Xảy ra khi một bean definition mới dùng lại tên đã được đăng ký.
- Có liên quan đến DefaultListableBeanFactory và cờ allowBeanDefinitionOverriding.
- Là hành vi cấu hình container ở mức tổng quát.
- Không thay thế các quy tắc chuyên biệt của bean override trong test.

Ví dụ cấu hình Spring Boot:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

Property này không biến một bean prototype thành đối tượng hợp lệ để @MockitoBean thay trong Framework 6.2.x. Nó cũng không thay đổi quy tắc xử lý FactoryBean của TestContext.

Đừng bật cho phép trùng bean definition chỉ để né lỗi scope hoặc thay mock. Hãy xác định lỗi xuất phát từ cơ chế nào và chọn API phù hợp với cơ chế đó.

## 13. Khác biệt theo phiên bản Spring Framework và Spring Boot

Các API thay bean trong test đã thay đổi đáng kể qua các phiên bản. Bảng sau giúp chọn annotation và hiểu đúng hành vi.

| Nền tảng | API thường dùng | Quy tắc scope và ghi chú |
|---|---|---|
| Spring Framework 6.1 trở về trước | Chưa có bộ @TestBean, @MockitoBean, @MockitoSpyBean của Framework 6.2 | Dự án Spring Boot thường dùng @MockBean/@SpyBean của Boot; hoặc cấu hình test riêng |
| Spring Framework 6.2.x | @TestBean, @MockitoBean, @MockitoSpyBean | Bean override chỉ chấp nhận singleton; non-singleton gây exception |
| Spring Boot 3.4.x và 3.5.x | Có thể dùng annotation của Framework 6.2 | @MockBean và @SpyBean của Boot bị deprecated từ 3.4.0, dự kiến loại bỏ ở Boot 4.0 |
| Spring Framework 7.0.x | Tiếp tục dùng @TestBean, @MockitoBean, @MockitoSpyBean | Khi thay non-singleton, Spring chuyển bean definition thành singleton override |
| Spring Boot 4.0.x | Dùng annotation bean override của Spring Framework | Dùng @MockitoBean và @MockitoSpyBean; kiểm tra hướng dẫn migration của đúng bản Boot |

### 13.1. Trước Spring Framework 6.2

Các annotation @MockitoBean và @MockitoSpyBean thuộc Spring Framework TestContext được giới thiệu từ Framework 6.2.

Trong các dự án Spring Boot cũ, cách quen thuộc là:

~~~java
@SpringBootTest
class OrderServiceTest {

    @MockBean
    private PaymentGateway paymentGateway;
}
~~~

@MockBean thuộc package:

~~~text
org.springframework.boot.test.mock.mockito.MockBean
~~~

Không thể thay import này bằng org.springframework.test.context.bean.override.mockito.MockitoBean nếu phiên bản Spring Framework đang dùng chưa có annotation mới.

### 13.2. Spring Framework 6.2 và Spring Boot 3.4

Với Framework 6.2, có thể dùng:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
~~~

Ví dụ:

~~~java
@SpringBootTest
class OrderServiceTest {

    @MockitoBean
    private PaymentGateway paymentGateway;
}
~~~

Spring Boot 3.4.0 đánh dấu @MockBean và @SpyBean của Boot là deprecated để chuyển sang annotation của Spring Framework. Chúng được công bố là deprecated for removal trong Boot 4.0.0.

Vì vậy, với dự án Boot 3.4 hoặc 3.5, ưu tiên annotation của Framework nếu không có ràng buộc tương thích riêng. Khi nâng cấp, kiểm tra import để tránh vô tình vẫn dùng annotation cũ từ package Spring Boot.

### 13.3. Spring Framework 7.0 và Spring Boot 4.0

Framework 7.0 giữ các annotation bean override của Framework và cập nhật hành vi đối với bean non-singleton. Khi thay prototype hoặc scoped bean, override instance được quản lý như singleton và scope của bean definition được chuyển thành singleton.

Điều này có nghĩa một test trước đây thất bại ở Framework 6.2 có thể chạy ở Framework 7.0. Nhưng việc test chạy được không có nghĩa nó đang mô phỏng đúng scope production.

Khi nâng cấp, hãy kiểm tra các test có @MockitoBean, @MockitoSpyBean hoặc @TestBean trên bean prototype, request, session và custom scope. Những test đó có thể thay đổi ý nghĩa vì mock hoặc fake nay được chia sẻ như singleton.

## 14. @MockitoSpyBean với scoped proxy

Scoped proxy là một proxy được Spring tạo để cho phép bean singleton tham chiếu tới một bean có scope ngắn hơn, ví dụ request scope.

Ví dụ:

~~~java
@Component
@RequestScope
public class CurrentRequestData {
}
~~~

Hoặc khai báo proxy tường minh:

~~~java
@Component
@Scope(
        value = WebApplicationContext.SCOPE_REQUEST,
        proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class CurrentRequestData {
}
~~~

Trong Spring Framework 7.0, @MockitoSpyBean không hỗ trợ spy trực tiếp một scoped proxy. Nếu test cố spy bean được khai báo với scoped proxy, Spring có thể ném exception.

Lý do là spy cần lấy instance thật để bọc. Scoped proxy đại diện cho target có vòng đời phụ thuộc request/session, nên không thể xử lý như một instance bình thường mà spy có thể giữ lại xuyên suốt context.

Các lựa chọn phù hợp:

- Kiểm tra logic của lớp target bằng unit test thuần.
- Kiểm tra hành vi request scope bằng web integration test và request context thật.
- Thay một collaborator singleton nằm bên trong bean scoped nếu mục tiêu là cô lập collaborator đó.
- Thiết kế interface hoặc service boundary rõ ràng để test phần nghiệp vụ mà không cần spy scoped proxy.

Không nên đổi bean request-scoped thành singleton chỉ để làm @MockitoSpyBean hoạt động nếu yêu cầu kiểm thử liên quan đến việc cô lập state theo request.

## 15. Bean override và Spring AOP proxy

Một bean có thể được Spring bọc bằng AOP proxy để áp dụng @Transactional, @Cacheable, @Retryable hoặc method security.

Cách override ảnh hưởng đến proxy:

- @MockitoBean và @TestBean thay bean bằng instance override trực tiếp. Instance này không trải qua toàn bộ bean post-processing như bean production ban đầu, nên các AOP advice của bean gốc có thể không còn.
- @MockitoSpyBean dùng chiến lược WRAP. Nếu bean gốc cần AOP proxy, proxy vẫn có thể được tạo và bọc spy làm target.

Sơ đồ khái quát:

~~~text
@MockitoBean / @TestBean
        |
        v
Caller -> Override instance
          (mock hoặc fake)

@MockitoSpyBean
        |
        v
Caller -> Spring AOP proxy
              |
              v
          Mockito spy
              |
              v
          Instance thật
~~~

Khi test transaction, cache hoặc retry, cần xác minh test đang gọi object nào. Một mock thay thế không thể chứng minh @Transactional trên bean gốc vẫn hoạt động.

Với spy nằm sau AOP proxy, việc stubbing có thể bị ảnh hưởng bởi advice. Ví dụ, @Cacheable có thể cache giá trị rỗng trong lúc Mockito ghi nhận lời gọi dùng để stubbing. Nếu gặp tình huống này, có thể cần lấy target spy bằng AopTestUtils.getUltimateTargetObject(...) để stub trực tiếp, hoặc cấu hình cache test phù hợp.

Đây là một lý do nữa để xác định rõ mục tiêu: nếu cần test logic thật cùng AOP, spy có thể phù hợp; nếu chỉ cần thay dependency bên ngoài, mock ở ranh giới thường đơn giản hơn.

## 16. Chia sẻ singleton mock giữa các test

Một bean override trong context có thể được các bean khác và test class sử dụng chung thông qua ApplicationContext. Spring TestContext còn có thể cache context giữa các test class có cấu hình tương đương.

Vì thế, singleton mock có thể được chia sẻ trong phạm vi context. Việc test method kết thúc không có nghĩa ApplicationContext và bean override bị hủy.

Một số hệ quả:

- Stubbing và invocation history cần được reset theo cấu hình mock.
- Test không nên phụ thuộc vào thứ tự chạy.
- Không để nhiều test song song cùng sửa một mock dùng chung.
- Cẩn thận với @TestInstance(PER_CLASS) và field mutable.
- Giữ cấu hình bean override nhất quán giữa các class để tránh tạo nhiều context không cần thiết.

Tài liệu Spring TestContext khuyến cáo không chạy song song những test dùng @MockitoBean hoặc @MockitoSpyBean, vì tương tác đồng thời có thể tạo side effect khó dự đoán.

Nếu test cần state riêng cho từng invocation, hãy tạo fixture hoặc mock riêng trong phạm vi đó, hoặc dùng context test riêng có chủ đích.

## 17. Khi cần kiểm tra scope thật, hãy giữ scope thật

Nếu câu hỏi kiểm thử là "mỗi lần lấy prototype có nhận instance mới không?", đừng thay bean bằng singleton mock. Hãy kiểm tra bean definition và container trực tiếp:

~~~java
@SpringJUnitConfig(PrototypeConfiguration.class)
class PrototypeScopeTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void shouldCreateANewInstanceForEachLookup() {
        var first = context.getBean(OperationCounter.class);
        var second = context.getBean(OperationCounter.class);

        assertNotSame(first, second);
    }
}
~~~

Nếu cần kiểm tra request scope, tạo request context riêng cho mỗi tình huống. Trong Spring MVC integration test, có thể gửi các request riêng và xác minh state không rò rỉ giữa chúng.

Nếu cần kiểm tra session scope, tạo session khác nhau và xác minh mỗi session có state riêng.

Nếu cần kiểm tra FactoryBean, giữ factory thật và xác minh:

- getObject() trả về product đúng kiểu.
- getObjectType() khai báo đúng product type.
- isSingleton() phản ánh đúng vòng đời product.
- Các lần truy cập bean theo tên trả về product theo hợp đồng.
- Truy cập &beanName trả về factory object.

Các test này tạo bằng chứng trực tiếp về scope và factory lifecycle.

## 18. Các lựa chọn thay thế khi không thể override bean

Nếu Framework 6.2 từ chối một bean non-singleton hoặc test cần giữ nguyên scope, có thể chọn một cách khác tùy mục tiêu.

**Kiểm tra logic bằng unit test**

Tạo object trực tiếp và inject fake/mock vào constructor. Không cần ApplicationContext nếu câu hỏi chỉ liên quan đến logic của class.

**Giữ scope thật trong context test**

Nạp configuration thật của bean, thiết lập request/session context phù hợp và xác minh hành vi qua container.

**Mock một dependency singleton bên trong bean scoped**

Ví dụ, giữ RequestScopedService thật nhưng thay RemoteClient singleton mà nó sử dụng. Như vậy test vẫn giữ vòng đời request và cô lập kết nối mạng.

**Dùng interface ở ranh giới cần cô lập**

Nếu một bean có nhiều trách nhiệm, có thể tách phần giao tiếp bên ngoài thành một interface rõ ràng. Test thay collaborator ở ranh giới đó mà không phải thay bean giữ state theo scope.

**Dùng test configuration cho dependency mới**

@TestConfiguration và @Import phù hợp khi muốn bổ sung bean hỗ trợ test. Tuy nhiên, một bean được thêm vào context không tự động thay bean cũ. Cần kiểm tra qualifier, primary candidate và bean name để bảo đảm ứng dụng thực sự inject implementation mong muốn.

**Kiểm tra FactoryBean độc lập**

Nếu mục tiêu là logic tạo product, khởi tạo factory trực tiếp hoặc tạo context nhỏ với factory thật. Nếu mục tiêu là consumer, thay product type bằng mock.

## 19. Bảng chọn chiến lược theo tình huống

| Tình huống | Lựa chọn phù hợp | Điều cần nhớ |
|---|---|---|
| Thay singleton dependency bằng mock | @MockitoBean | Dùng enforceOverride = true nếu bean bắt buộc phải tồn tại |
| Theo dõi singleton bean thật | @MockitoSpyBean | Cần một candidate rõ ràng |
| Thay singleton bằng fake tự tạo | @TestBean | Factory method static, không tham số |
| Thay prototype trong Framework 6.2.x | Không dùng bean override | Framework từ chối non-singleton |
| Thay prototype trong Framework 7.0 | Có thể override | Instance thay thế trở thành singleton |
| Kiểm tra prototype tạo instance mới | Giữ bean thật và gọi container nhiều lần | Kiểm tra identity của instance |
| Thay product do FactoryBean tạo | Override product type | FactoryBean registration bị thay khi dùng chiến lược replace |
| Spy product do FactoryBean tạo | @MockitoSpyBean trên product type | Spy bọc product, không bọc factory |
| Kiểm tra logic bên trong FactoryBean | Test factory riêng | Dùng &beanName khi cần lấy factory từ context |
| Spy scoped proxy | Không dùng @MockitoSpyBean trực tiếp | Test qua scope thật hoặc thay collaborator bên trong |
| Kiểm tra AOP trên bean thật | Giữ bean và cân nhắc spy | Mock replacement có thể bỏ qua AOP advice |
| Test có nhiều implementation cùng interface | @Qualifier hoặc tên bean | Tránh thay nhầm candidate |

## 20. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Context thất bại khi dùng @MockitoBean | Bean đích là non-singleton trong Framework 6.2.x | Kiểm tra scope và phiên bản Framework |
| Test chạy được sau khi nâng Framework nhưng hành vi state khác | Framework 7.0 chuyển override non-singleton thành singleton | Kiểm tra lại giả định về scope và state |
| @MockitoSpyBean báo nhiều candidate | Không xác định được một bean duy nhất | Dùng @Qualifier hoặc tên bean |
| Mock được tạo dù bean production không tồn tại | @MockitoBean mặc định dùng REPLACE_OR_CREATE | Dùng enforceOverride = true |
| Spy gọi HTTP thật khi stubbing | Stubbing thực thi phương thức thật | Dùng doReturn/doThrow hoặc fake dependency |
| Không kiểm tra được logic FactoryBean | Test đang override product | Giữ factory thật và kiểm tra riêng |
| Mock product hoạt động nhưng factory không chạy | Override thay FactoryBean registration | Test factory trong context riêng |
| Spy scoped proxy thất bại | @MockitoSpyBean không hỗ trợ scoped proxy | Kiểm tra target qua request/session test |
| @Transactional không hoạt động như mong đợi | @MockitoBean thay bằng bare mock | Giữ bean thật hoặc kiểm tra proxy ở test khác |
| Test song song thất bại ngẫu nhiên | Nhiều test dùng chung mock trong context | Không chạy song song test dùng bean override hoặc cô lập context |
| Không tìm thấy annotation @MockitoBean | Phiên bản Spring Framework quá cũ | Kiểm tra dependency và dùng API phù hợp phiên bản |

Khi điều tra, hãy kiểm tra phiên bản Spring Framework thực tế trong dependency tree. Phiên bản Spring Boot chỉ là dấu hiệu ban đầu; dự án có thể override dependency quản lý hoặc dùng BOM khác. Hãy xác định artifact spring-test đang chạy trước khi kết luận hành vi.

## 21. Quy trình chọn bean override an toàn

Trước khi thay một bean, hãy xác định các thông tin sau:

1. Bean được inject là product thông thường hay object do FactoryBean tạo?
2. Scope của bean definition là singleton, prototype, request, session hay custom?
3. Nếu là FactoryBean, isSingleton() của product trả về gì?
4. Phiên bản Spring Framework là 6.2.x hay 7.0.x?
5. Test cần thay bean bằng mock, fake hay spy?
6. Test cần bảo vệ bean production đã tồn tại hay chấp nhận tạo bean mới?
7. Có nhiều candidate cùng kiểu cần qualifier hoặc bean name không?
8. Bean có AOP proxy hoặc scoped proxy không?
9. Việc thay bean có làm thay đổi vòng đời, state hoặc khả năng chạy song song không?
10. Test đang chứng minh hành vi của consumer, factory hay scope?

Sau khi trả lời:

- Dùng @MockitoBean cho dependency cần mock.
- Dùng enforceOverride = true khi thiếu bean phải là lỗi.
- Dùng @MockitoSpyBean khi cần theo dõi implementation thật và có đúng một candidate.
- Dùng @TestBean khi muốn thay bằng fake hoặc object do test tạo.
- Giữ bean thật khi test cần xác minh scope hoặc logic của FactoryBean.
- Kiểm tra lại test sau khi nâng Framework vì quy tắc non-singleton đã thay đổi.

## 22. Tài liệu tham khảo theo phiên bản

Các quy tắc về singleton và FactoryBean cần được đối chiếu với tài liệu đúng phiên bản:

- [Bean Overriding in Tests — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html)
- [@MockitoBean và @MockitoSpyBean — Spring Framework 6.2](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [BeanOverrideHandler — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/bean/override/BeanOverrideHandler.html)
- [Bean Overriding in Tests — Spring Framework 7.0](https://docs.spring.io/spring-framework/reference/7.0/testing/testcontext-framework/bean-overriding.html)
- [@MockitoBean và @MockitoSpyBean — Spring Framework 7.0](https://docs.spring.io/spring-framework/reference/7.0/testing/annotations/integration-spring/annotation-mockitobean.html)
- [@MockBean — Spring Boot 3.4 API và thông tin deprecated](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [Mocking and Spying Beans — Spring Boot Testing](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)

## 23. Kết luận

Khi thay bean trong kiểm thử Spring, scope và cách tạo bean quyết định hành vi của override.

- Spring Framework 6.2.x chỉ cho phép bean override đối với singleton; thay prototype hoặc scoped bean sẽ gây lỗi.
- Spring Framework 7.0 cho phép thay non-singleton nhưng chuyển bean definition thành singleton. Mock hoặc fake vì thế không còn mô phỏng vòng đời ban đầu.
- Với FactoryBean, chiến lược replace thay factory registration bằng singleton override tương ứng với product; chiến lược spy bọc product do factory tạo ra.
- FactoryBean.isSingleton() mô tả vòng đời product, còn &beanName dùng để lấy factory object.
- @MockitoBean, @MockitoSpyBean và @TestBean có chiến lược khác nhau; cần chọn đúng theo mục tiêu test.
- Spring Boot 3.4 deprecated @MockBean và @SpyBean để chuyển sang annotation của Spring Framework; dự án cần kiểm tra version và import khi nâng cấp.

Hãy giữ scope thật khi mục tiêu là kiểm tra vòng đời của bean. Khi chỉ cần cô lập một dependency, hãy thay đúng ranh giới và ghi nhớ rằng singleton mock có thể thay đổi cách state được chia sẻ trong context. Với FactoryBean, luôn xác định rõ test đang làm việc với factory hay product trước khi chọn kiểu bean override.

