# Spy sau AOP proxy và verify nhầm đối tượng

Khi kiểm thử Spring bean bằng Mockito spy, một lỗi thường gặp là gọi đúng bean trong ApplicationContext nhưng lại `verify()` trên một object khác. Lỗi này dễ xuất hiện khi bean được Spring AOP bọc bằng proxy, khi test tự tạo thêm một spy riêng, hoặc khi có nhiều bean cùng kiểu.

Mockito chỉ xác minh được object mock/spy mà nó quản lý. Một Spring AOP proxy thông thường không tự động là Mockito spy. Ngược lại, một Mockito spy có thể nằm bên trong proxy AOP. Vì vậy, cần hiểu object nào được inject vào test, object nào đang nhận lời gọi và object nào thực sự là Mockito spy.

Bài này tập trung vào việc chẩn đoán identity của bean, phân biệt proxy với target, chọn đúng reference để `verify()`, và tránh làm thay đổi hành vi AOP trong lúc kiểm thử.

## 1. Vì sao verify có thể nhầm đối tượng?

Giả sử ứng dụng có service:

~~~java
@Service
class PaymentService {

    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void pay(String orderId) {
        gateway.charge(orderId);
    }
}
~~~

Test muốn xác nhận `PaymentGateway.charge()` được gọi:

~~~java
paymentService.pay("ORDER-42");
verify(paymentGateway).charge("ORDER-42");
~~~

Assertion chỉ đúng nếu biến `paymentGateway` đang được verify chính là Mockito spy đã nhận lời gọi. Nếu biến đó là một mock/spy khác do test tự tạo, hoặc là một Spring proxy không phải Mockito spy, Mockito không thể xác nhận interaction mong muốn.

Một số tình huống phổ biến:

- Test dùng `@Spy` tạo một object riêng, trong khi service trong ApplicationContext vẫn inject bean gốc.
- Test gọi bean lấy từ Spring nhưng verify một instance được tạo bằng `new`.
- Spring AOP bọc target bằng proxy, còn test lại verify proxy hoặc target không phải spy.
- Có nhiều bean cùng interface; test spy một bean nhưng service inject bean khác do qualifier hoặc `@Primary`.
- Test lấy target object để gọi trực tiếp, vô tình bỏ qua proxy và các advice.

Thông báo lỗi thường gặp:

~~~text
org.mockito.exceptions.misusing.NotAMockException:
Argument passed to verify() is not a mock!
~~~

Thông báo này có nghĩa object truyền vào `verify(...)` không phải Mockito mock/spy. Nó chưa nói rằng service không gọi method; trước hết cần xác định đúng reference.

## 2. Phân biệt bean, target, AOP proxy và Mockito spy

Trong Spring, một bean có thể được bao quanh bởi nhiều lớp object:

~~~text
Test field / reference được inject
              |
              v
      Spring AOP proxy
      (transaction, security,
       cache, retry, ...)
              |
              v
       Mockito spy target
              |
              v
        Bean instance thật
~~~

Đây là một cấu trúc thường gặp khi proxy AOP gọi vào target là Mockito spy. Cấu trúc thực tế có thể khác tùy thời điểm bean được post-process và cách spy được đăng ký:

- Mockito spy có thể là object bên ngoài proxy.
- Spring AOP proxy có thể nằm bên ngoài Mockito spy.
- Một bean có thể không được AOP proxy hóa.
- Có thể có nhiều proxy lồng nhau.

Các khái niệm:

| Thành phần | Ý nghĩa |
|---|---|
| Bean reference | Object mà Spring trả về khi lấy bean từ ApplicationContext hoặc inject vào field. |
| Target object | Instance thực hiện logic thật phía sau AOP proxy. |
| AOP proxy | Object trung gian áp dụng advice trước/sau khi gọi target. |
| Mockito spy | Object được Mockito theo dõi interaction và mặc định ủy quyền lời gọi thật. |
| Injected spy | Reference spy mà Spring Test đăng ký và inject vào test; có thể còn nằm trong một proxy khác. |

Không nên mặc định rằng `bean`, `proxy`, `target` và `spy` luôn là cùng một object. Chúng có thể cùng kiểu khai báo hoặc cùng delegate đến một instance, nhưng identity và vai trò khác nhau.

## 3. AOP proxy được tạo ra để làm gì?

Spring AOP dùng proxy để áp dụng các hành vi cắt ngang như:

- `@Transactional`: quản lý transaction.
- `@Cacheable`: đọc/ghi cache.
- `@PreAuthorize`: kiểm tra quyền truy cập.
- `@Retryable`: thử lại lời gọi khi gặp lỗi.
- Custom aspect: logging, metric, audit hoặc tracing.

Ví dụ:

~~~java
@Service
class OrderService {

    @Transactional
    public void placeOrder(String orderId) {
        // Ghi đơn hàng.
    }
}
~~~

Khi một bean khác gọi `orderService.placeOrder(...)` qua reference được Spring inject, lời gọi đi qua proxy. Proxy chạy transaction advice rồi mới gọi target.

Sơ đồ:

~~~text
Controller
    |
    | orderService.placeOrder(...)
    v
Spring AOP proxy
    |
    | bắt đầu transaction
    v
OrderService target
    |
    | thực hiện logic
    v
Spring AOP proxy
    |
    | commit / rollback transaction
    v
Controller nhận kết quả
~~~

Proxy là object Spring dùng để điều khiển lời gọi. Nó không mặc nhiên là Mockito spy. Nếu test muốn xác minh interaction, phải tìm reference Mockito spy đúng trong cấu trúc này.

## 4. JDK dynamic proxy và CGLIB proxy

Spring AOP có thể tạo proxy theo hai cách phổ biến:

| Loại proxy | Đặc điểm | Lưu ý khi test |
|---|---|---|
| JDK dynamic proxy | Proxy triển khai các interface của target. | Inject theo interface thường an toàn; ép proxy về implementation class có thể thất bại. |
| CGLIB proxy | Proxy là subclass được tạo cho class target. | Reference có thể trông giống kiểu implementation, nhưng vẫn không phải target instance ban đầu. |

Ví dụ service có interface:

~~~java
public interface OrderOperations {
    void placeOrder(String orderId);
}

@Service
class OrderService implements OrderOperations {

    @Override
    @Transactional
    public void placeOrder(String orderId) {
        // Ghi đơn hàng.
    }
}
~~~

Nếu Spring dùng JDK dynamic proxy, reference có thể triển khai `OrderOperations` nhưng không phải `OrderService`. Vì vậy, test nên inject theo interface khi hợp đồng bean là interface:

~~~java
@Autowired
OrderOperations orderOperations;
~~~

Không ép kiểu tùy tiện:

~~~java
OrderService service = (OrderService) applicationContext.getBean(OrderOperations.class);
~~~

Phép ép kiểu trên có thể thất bại khi bean là JDK proxy.

## 5. Dùng Spring-managed spy thay vì tạo một spy rời

Nếu cần theo dõi một bean thực sự nằm trong ApplicationContext, hãy dùng cơ chế spy bean của Spring Test.

Với Spring Framework 6.2 trở lên, có thể dùng `@MockitoSpyBean`:

~~~java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest
class OrderServiceTests {

    @MockitoSpyBean
    PaymentGateway paymentGateway;

    @Autowired
    OrderService orderService;

    @Test
    void callsPaymentGateway() {
        orderService.pay("ORDER-42");

        verify(paymentGateway).charge("ORDER-42");
    }
}
~~~

`@MockitoSpyBean` yêu cầu Spring Test wrap bean hiện có bằng Mockito spy và inject spy vào test field. Với bean có nhiều candidate cùng kiểu, dùng `@Qualifier` hoặc tên bean để chọn đúng candidate.

Ví dụ:

~~~java
@MockitoSpyBean
@Qualifier("primaryPaymentGateway")
PaymentGateway paymentGateway;
~~~

Trong Spring Boot cũ, dự án có thể đang dùng `@SpyBean`:

~~~java
import org.springframework.boot.test.mock.mockito.SpyBean;

@SpyBean
PaymentGateway paymentGateway;
~~~

`@SpyBean` đã deprecated từ Spring Boot 3.4 để chuyển sang `@MockitoSpyBean` của Spring Framework. Hãy dùng annotation có sẵn trong phiên bản dự án; không nâng dependency chỉ để thay annotation trong một test đơn lẻ.

Một spy bean thường gọi implementation thật nếu method chưa được stub. Vì vậy, test cần chuẩn bị database, network hoặc dependency mà method thật sử dụng, hoặc stub method cần thiết bằng cú pháp an toàn cho spy.

## 6. Vì sao @Spy và @MockitoSpyBean không tương đương?

`@Spy` của Mockito tạo spy cho một object trong phạm vi test:

~~~java
@ExtendWith(MockitoExtension.class)
class LocalSpyTests {

    @Spy
    PaymentGateway paymentGateway = new PaymentGatewayImpl();

    @InjectMocks
    PaymentService paymentService;
}
~~~

Đây là unit test thuần Mockito. Mockito tạo object và inject dependency vào instance mà nó quản lý. Test không tự động thay bean trong Spring ApplicationContext.

Ngược lại:

~~~java
@SpringBootTest
class SpringSpyTests {

    @MockitoSpyBean
    PaymentGateway paymentGateway;

    @Autowired
    PaymentService paymentService;
}
~~~

Ở đây, Spring tạo ApplicationContext và Spring Test thay bean bằng spy được quản lý trong context. Service được Spring tạo ra sẽ nhận dependency theo cấu hình bean của context.

Nếu kết hợp `@Spy` với `@SpringBootTest` mà không có cấu hình tích hợp rõ ràng, test có thể có hai object:

~~~text
Spring ApplicationContext
  PaymentService ---> PaymentGateway thật

Test field
  @Spy PaymentGateway ---> một instance riêng
~~~

Service gọi gateway thật, còn test verify spy riêng. Spy không ghi nhận lời gọi vì nó không nằm trong dependency graph của service.

Quy tắc thực tế:

- Unit test thuần Mockito: dùng `@Mock`, `@Spy`, `@InjectMocks`.
- Spring integration test: dùng `@MockitoSpyBean` hoặc annotation tương thích phiên bản để spy bean trong context.
- Không tạo thêm `Mockito.spy(...)` cho cùng dependency rồi giả định Spring bean sẽ tự động dùng object đó.

## 7. Chẩn đoán object nào thực sự là spy

Khi gặp `NotAMockException`, đừng đoán object nào là spy. Hãy kiểm tra từng reference.

Mockito cung cấp:

~~~java
Mockito.mockingDetails(object).isSpy()
Mockito.mockingDetails(object).isMock()
~~~

Spring cung cấp:

~~~java
import org.springframework.aop.support.AopUtils;
import org.springframework.test.util.AopTestUtils;
~~~

`AopUtils.isAopProxy(object)` cho biết reference có phải Spring AOP proxy hay không. `AopTestUtils.getUltimateTargetObject(object)` có thể tháo các proxy Spring AOP lồng nhau để lấy target cuối cùng.

Ví dụ chẩn đoán:

~~~java
Object bean = applicationContext.getBean(PaymentGateway.class);
Object target = AopTestUtils.getUltimateTargetObject(bean);

System.out.println("bean is AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("bean is Mockito spy: "
    + Mockito.mockingDetails(bean).isSpy());
System.out.println("target is Mockito spy: "
    + Mockito.mockingDetails(target).isSpy());
~~~

Kết quả giúp xác định lớp nào đang giữ Mockito spy. Không nên in toàn bộ object hoặc thông tin nhạy cảm trong log production; đoạn này chỉ dành cho chẩn đoán trong test.

Một bảng diễn giải:

| Bean reference là AOP proxy? | Bean reference là spy? | Ultimate target là spy? | Reference cần xem xét để verify |
|---|---|---|---|
| Không | Có | Có thể chính là bean | Bean reference. |
| Có | Có | Không nhất thiết | Bean reference nếu `mockingDetails(bean).isSpy()` là true. |
| Có | Không | Có | Ultimate target, nếu đó chính là Mockito spy. |
| Có | Không | Không | Chưa tìm thấy Mockito spy; kiểm tra cách spy được đăng ký và dependency đang inject. |
| Không | Không | Không | Object không phải Mockito spy; `verify()` trên nó sẽ ném `NotAMockException`. |

Điểm quan trọng: `getUltimateTargetObject()` chỉ giúp tìm target phía sau Spring AOP proxy. Không được gọi nó một cách máy móc rồi luôn verify target. Nếu Mockito spy nằm ở lớp ngoài proxy, target cuối cùng có thể là object thật, không phải spy.

## 8. Verify trên đúng reference

Giả sử test đã xác định bean reference được inject là Mockito spy:

~~~java
orderService.placeOrder("ORDER-42");

verify(paymentGateway, times(1)).charge("ORDER-42");
~~~

Nếu `paymentGateway` là AOP proxy và spy nằm ở target, lấy target rồi xác nhận nó là spy trước:

~~~java
PaymentGateway target =
    AopTestUtils.getUltimateTargetObject(paymentGateway);

assertThat(Mockito.mockingDetails(target).isSpy()).isTrue();
verify(target).charge("ORDER-42");
~~~

Ví dụ trên chỉ phù hợp khi ultimate target thực sự là Mockito spy. Nếu kiểm tra `isSpy()` trả về false, không tiếp tục verify object đó. Hãy quay lại cấu trúc bean override và xác định spy nằm ở lớp nào.

Có thể viết helper chẩn đoán trong test:

~~~java
static <T> T findSpyReference(T bean, Class<T> type) {
    if (Mockito.mockingDetails(bean).isSpy()) {
        return bean;
    }

    Object target = AopTestUtils.getUltimateTargetObject(bean);
    if (type.isInstance(target)
            && Mockito.mockingDetails(target).isSpy()) {
        return type.cast(target);
    }

    throw new AssertionError("No Mockito spy found in bean/proxy chain");
}
~~~

Sử dụng:

~~~java
PaymentGateway spy = findSpyReference(paymentGateway, PaymentGateway.class);
verify(spy).charge("ORDER-42");
~~~

Helper này chỉ xử lý hai trường hợp thường gặp: bean reference là spy hoặc ultimate target là spy. Với proxy tùy chỉnh hoặc nhiều tầng wrapper không phải Spring AOP, cần điều tra riêng; không nên coi helper là công cụ unwrap mọi loại proxy.

## 9. Không gọi target trực tiếp để thực hiện hành vi cần kiểm thử

`AopTestUtils.getUltimateTargetObject()` hữu ích để kiểm tra interaction trên spy nằm sau proxy. Tuy nhiên, không nên dùng target đã unwrap để thực hiện lời gọi chính trong test nếu muốn kiểm tra AOP:

~~~java
// Có thể bỏ qua transaction/security/cache advice.
PaymentService target =
    AopTestUtils.getUltimateTargetObject(orderService);
target.placeOrder("ORDER-42");
~~~

Lời gọi trên đi thẳng vào target, không qua proxy bên ngoài. Nếu mục tiêu test là hành vi của Spring bean trong ứng dụng, hãy gọi reference được inject từ context:

~~~java
orderService.placeOrder("ORDER-42");
~~~

Sau đó mới dùng spy reference phù hợp để verify interaction. Tách biệt hai nhiệm vụ:

- **Thực thi hành vi:** gọi bean qua Spring-managed reference để advice hoạt động.
- **Quan sát interaction:** verify đúng Mockito spy đang nằm trong bean/proxy chain.

## 10. Dùng doReturn khi stub spy

Spy mặc định gọi method thật. Vì vậy, cú pháp sau có thể thực thi method thật ngay trong lúc khai báo stub:

~~~java
when(paymentGateway.balance("ACCOUNT-1"))
    .thenReturn(new BigDecimal("100.00"));
~~~

Nếu method thật truy cập network, database hoặc có side effect, test có thể gặp lỗi ngay khi setup. Với spy, thường nên dùng `doReturn(...).when(...)`:

~~~java
doReturn(new BigDecimal("100.00"))
    .when(paymentGateway)
    .balance("ACCOUNT-1");
~~~

Các cú pháp `do...` hữu ích:

~~~java
doReturn(value).when(spy).method();
doThrow(exception).when(spy).method();
doNothing().when(spy).voidMethod();
doAnswer(invocation -> result).when(spy).method();
~~~

`doReturn` tránh gọi method thật trong quá trình thiết lập stub. Sau khi setup, lời gọi qua spy sẽ trả giá trị được stub theo cấu hình.

Chỉ stub những method cần kiểm soát. Nếu stub quá rộng, test có thể không còn kiểm tra hành vi thật mà mục tiêu ban đầu muốn xác nhận.

## 11. Verify số lần gọi, argument và thứ tự

Sau khi đã có đúng spy reference, Mockito hỗ trợ các kiểu xác minh quen thuộc:

~~~java
verify(paymentGateway).charge("ORDER-42");
verify(paymentGateway, times(1)).charge("ORDER-42");
verify(paymentGateway, never()).refund("ORDER-42");
verify(paymentGateway, atLeastOnce()).healthCheck();
~~~

Kiểm tra argument:

~~~java
ArgumentCaptor<PaymentRequest> captor =
    ArgumentCaptor.forClass(PaymentRequest.class);

verify(paymentGateway).charge(captor.capture());

assertThat(captor.getValue().orderId()).isEqualTo("ORDER-42");
~~~

Kiểm tra thứ tự giữa hai collaborator:

~~~java
InOrder inOrder = inOrder(tokenClient, orderClient);

inOrder.verify(tokenClient).getToken();
inOrder.verify(orderClient).submit(any(OrderRequest.class));
~~~

`InOrder` cũng cần các reference là Mockito mock/spy. Nếu một biến trong `inOrder(...)` chỉ là AOP proxy không phải spy, Mockito sẽ không thể theo dõi nó.

Không lạm dụng `verifyNoMoreInteractions()`. Assertion này có thể làm test phụ thuộc vào những lời gọi phụ trợ không phải hợp đồng quan trọng, khiến test dễ gãy khi implementation thay đổi.

## 12. Nhiều bean cùng kiểu: spy đúng bean mà service sử dụng

Một nguyên nhân khác của verify nhầm object là có nhiều bean cùng implement một interface:

~~~java
@Component("cardGateway")
class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component("bankGateway")
class BankPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Service chọn bean bằng qualifier:

~~~java
@Service
class PaymentService {

    private final PaymentGateway gateway;

    PaymentService(@Qualifier("bankGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Test cũng phải spy đúng bean:

~~~java
@MockitoSpyBean
@Qualifier("bankGateway")
PaymentGateway bankGateway;
~~~

Nếu test spy `cardGateway` nhưng service gọi `bankGateway`, verify trên spy card sẽ không thấy interaction. Điều này không liên quan đến Mockito lỗi; test đã chọn nhầm collaborator.

Khi có nhiều candidate, dùng qualifier hoặc bean name rõ ràng. Đừng dựa vào thứ tự scan hoặc giả định `@Primary` giống nhau ở mọi cấu hình test.

## 13. AOP và self-invocation

Spring AOP proxy chỉ áp dụng advice cho lời gọi đi qua proxy. Nếu một method trong target gọi một method khác trên cùng instance bằng `this`, lời gọi nội bộ không đi qua proxy.

Ví dụ:

~~~java
@Service
class ReportService {

    public void generate() {
        this.writeAuditRecord();
    }

    @Transactional
    public void writeAuditRecord() {
        // Ghi audit.
    }
}
~~~

Khi `generate()` được gọi qua proxy, proxy có thể áp dụng advice cho `generate()`. Nhưng lời gọi `this.writeAuditRecord()` diễn ra bên trong target và không quay lại proxy. Vì vậy transaction advice của `writeAuditRecord()` không được kích hoạt bởi self-invocation đó.

Đây là vấn đề về AOP interception, khác với vấn đề Mockito spy identity:

- Spy có thể ghi nhận một method được gọi trên object spy.
- AOP advice chỉ chạy khi lời gọi đi qua proxy.
- Verify thành công không chứng minh transaction/security/cache advice đã chạy.

Nếu cần test transaction của `writeAuditRecord()`, hãy gọi method qua bean proxy từ bên ngoài hoặc tách phần nghiệp vụ đó sang một bean khác được inject. Không dùng kết quả `verify(spy).writeAuditRecord()` làm bằng chứng rằng `@Transactional` đã được áp dụng.

## 14. Kiểm tra AOP có thực sự hoạt động không?

Nếu mục tiêu test là xác nhận advice được kích hoạt, hãy kiểm tra tác động mà advice tạo ra thay vì chỉ verify method invocation.

Ví dụ với transaction, có thể kiểm tra transaction active bên trong một collaborator:

~~~java
@Component
class TransactionProbe {

    boolean wasTransactionActive;

    void record() {
        wasTransactionActive =
            TransactionSynchronizationManager.isActualTransactionActive();
    }
}
~~~

Service:

~~~java
@Service
class TransferService {

    private final TransactionProbe probe;

    TransferService(TransactionProbe probe) {
        this.probe = probe;
    }

    @Transactional
    public void transfer() {
        probe.record();
    }
}
~~~

Test có thể gọi bean qua context và kiểm tra:

~~~java
transferService.transfer();
assertThat(transactionProbe.wasTransactionActive).isTrue();
~~~

Đây là ví dụ minh họa cách kiểm tra trạng thái transaction. Trong test thực tế, cần có transaction manager và cấu hình transaction phù hợp.

Tương tự:

- Với cache, kiểm tra cache entry hoặc số lần gọi collaborator thực tế.
- Với security, kiểm tra quyền truy cập qua proxy và kết quả 401/403.
- Với retry, kiểm tra số lần gọi dependency và kết quả sau retry.
- Với custom aspect, kiểm tra side effect hoặc metric mà aspect tạo ra.

Spy và AOP có thể cùng tham gia một test, nhưng cần xác định rõ test đang xác nhận interaction hay xác nhận advice.

## 15. Một ví dụ hoàn chỉnh với @MockitoSpyBean

Giả sử service gọi gateway thật:

~~~java
public interface PaymentGateway {
    void charge(String orderId);
}

@Component
class RemotePaymentGateway implements PaymentGateway {

    @Override
    public void charge(String orderId) {
        // Gọi hệ thống thanh toán.
    }
}

@Service
class CheckoutService {

    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void checkout(String orderId) {
        gateway.charge(orderId);
    }
}
~~~

Test Spring:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;

@SpringBootTest
class CheckoutServiceTests {

    @MockitoSpyBean
    PaymentGateway paymentGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void delegatesChargeToSpringManagedGatewaySpy() {
        checkoutService.checkout("ORDER-42");

        verify(paymentGateway, times(1)).charge("ORDER-42");
    }
}
~~~

Spring inject spy vào dependency graph của context. Test gọi `CheckoutService` do Spring quản lý, rồi verify reference spy được inject vào test.

Nếu `PaymentGateway` có nhiều bean, bổ sung `@Qualifier` trên field spy. Nếu gateway còn được bọc bởi AOP proxy, kiểm tra `AopUtils.isAopProxy(...)` và `Mockito.mockingDetails(...).isSpy()` trước khi quyết định có cần unwrap target để verify hay không.

## 16. Phân biệt lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `NotAMockException` | Verify trên object thường hoặc AOP proxy không phải spy. | Kiểm tra `mockingDetails(...).isSpy()`; tìm spy reference đúng. |
| Verify không thấy invocation | Service dùng instance khác với spy trong test. | Dùng Spring-managed spy và kiểm tra qualifier/bean name. |
| Verify trên target thất bại | Spy nằm bên ngoài proxy, target đã unwrap không phải spy. | Kiểm tra cả bean reference và ultimate target; verify object có `isSpy() == true`. |
| Ép kiểu proxy sang implementation bị lỗi | Spring dùng JDK dynamic proxy. | Inject và thao tác qua interface. |
| Stub spy nhưng method thật vẫn chạy lúc setup | Dùng `when(spy.method()).thenReturn(...)`. | Dùng `doReturn(...).when(spy).method(...)`. |
| Verify method thành công nhưng transaction không chạy | Lời gọi self-invocation không qua proxy. | Gọi qua proxy từ bean khác hoặc tách method sang collaborator. |
| Verify sai implementation | Có nhiều bean cùng interface. | Dùng `@Qualifier` hoặc tên bean chính xác. |
| Test chạy riêng pass nhưng chạy suite fail | Spy/resource hoặc context bị chia sẻ/reset không phù hợp. | Kiểm tra scope, context cache và reset lifecycle. |

## 17. Reset spy và trạng thái giữa các test

Spring Test spy bean thường được reset theo lifecycle test của cơ chế bean override. Với `@MockitoSpyBean`, mặc định reset mode là sau mỗi test method. Nếu dùng annotation cũ của Spring Boot, kiểm tra thuộc tính reset và hành vi theo phiên bản Boot đang chạy.

Không nên giữ reference tới target hoặc spy đã unwrap rồi dùng lại giữa nhiều test method nếu framework reset hoặc thay thế bean. Lấy reference từ context/test injection trong đúng scope của test.

Nếu test có nhiều giai đoạn và cần giữ invocation để kiểm tra sau, đừng reset spy trước khi verify. Nếu cần xóa invocation history giữa hai giai đoạn, dùng API reset Mockito một cách có chủ đích và lưu ý reset có thể xóa cả stubbing:

~~~java
clearInvocations(paymentGateway); // Xóa lịch sử invocation, giữ stubbing.
reset(paymentGateway);            // Xóa cả stubbing và invocation history.
~~~

Chỉ dùng reset khi test thật sự cần nhiều pha trên cùng spy. Thông thường, mỗi test method nên độc lập và để Spring Test quản lý reset.

## 18. Quy trình chẩn đoán khi verify thất bại

Khi gặp lỗi verify với bean có AOP:

1. **Xác định bean mà service thực sự inject.** Kiểm tra constructor, qualifier, `@Primary` và bean name.
2. **Lấy reference từ ApplicationContext hoặc test field.** Tránh tạo thêm object bằng `new` hoặc `Mockito.spy(...)` ngoài context.
3. **Kiểm tra proxy.** Dùng `AopUtils.isAopProxy(bean)` để biết reference có phải Spring AOP proxy.
4. **Kiểm tra Mockito spy.** Dùng `Mockito.mockingDetails(bean).isSpy()` trên reference đang verify.
5. **Nếu reference là AOP proxy nhưng không phải spy, kiểm tra ultimate target.** Chỉ verify target nếu `mockingDetails(target).isSpy()` trả về true.
6. **Thực hiện hành vi qua bean proxy.** Đừng gọi target trực tiếp nếu muốn advice hoạt động.
7. **Verify đúng spy reference.** Dùng `times`, `never`, argument matcher hoặc captor theo hợp đồng cần xác nhận.
8. **Nếu cần kiểm tra AOP advice, kiểm tra tác động của advice.** Interaction spy không chứng minh transaction, security hoặc cache đã chạy.

Các đoạn chẩn đoán nên được giữ trong test hoặc gỡ bỏ sau khi tìm ra nguyên nhân. Không thêm log nội bộ hoặc unwrap proxy trong code production chỉ để làm Mockito verify dễ hơn.

## 19. Nguyên tắc chọn công cụ

| Mục tiêu | Cách tiếp cận |
|---|---|
| Unit test một class không cần Spring | Mockito `@Mock`, `@Spy`, `@InjectMocks`. |
| Theo dõi collaborator trong ApplicationContext | `@MockitoSpyBean` hoặc `@SpyBean` trên phiên bản Boot cũ. |
| Xác minh bean được chọn khi có nhiều implementation | Spy đúng bean bằng qualifier hoặc bean name. |
| Chẩn đoán Spring proxy | `AopUtils.isAopProxy`, `AopTestUtils.getUltimateTargetObject`. |
| Xác định object có phải Mockito spy | `Mockito.mockingDetails(object).isSpy()`. |
| Kiểm tra method được gọi | `verify()` trên chính Mockito spy. |
| Kiểm tra transaction/cache/security advice | Kiểm tra tác động hoặc trạng thái do advice tạo ra. |

Khi làm việc với Spring AOP, đừng coi proxy, target và Mockito spy là cùng một object. Hãy xác định reference nào được service sử dụng, reference nào thực sự là spy, rồi mới gọi `verify()`. Thực hiện hành vi qua Spring-managed proxy để giữ nguyên AOP; chỉ unwrap target cho mục đích quan sát khi đã xác nhận target đó chính là Mockito spy. Cách tiếp cận này giúp tránh `NotAMockException`, verify nhầm instance và những test pass nhưng không hề kiểm tra bean đang chạy trong ứng dụng.
