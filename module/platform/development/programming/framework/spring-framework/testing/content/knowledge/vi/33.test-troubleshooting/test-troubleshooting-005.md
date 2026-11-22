# Mock không được tiêm vào đối tượng thật sự được gọi

Một test có thể tạo mock đúng cách, stub đúng giá trị nhưng khi chạy ứng dụng vẫn gọi dependency thật. Kết quả thường là test đi vào database, gọi HTTP, truy cập filesystem hoặc trả về dữ liệu khác với stub. Nguyên nhân phổ biến là mock đang nằm trong test object, trong khi đối tượng được gọi lại là một instance khác do Spring quản lý.

Muốn chẩn đoán lỗi này, cần xác định chính xác **đối tượng nào đang thực thi hành vi** và **ai đã tạo đối tượng đó**. Mockito `@Mock` tạo mock trong phạm vi Mockito; nó không tự thay bean trong Spring `ApplicationContext`. Khi test gọi bean Spring, hãy dùng cơ chế override bean của Spring như `@MockitoBean` hoặc cấu hình mock bean tương ứng với phiên bản dự án.

## 1. Hiểu đúng hai đồ thị đối tượng

Trong một test có Spring và Mockito, có thể tồn tại hai đồ thị đối tượng độc lập:

```text
Đồ thị Mockito trong test                     Đồ thị Spring trong ApplicationContext

@Mock PaymentGateway                          PaymentGateway thật
       |                                               |
       v                                               v
Test field                                    OrderService bean
                                                       |
                                                       v
                                              PaymentGateway thật
```

Khai báo `@Mock PaymentGateway` chỉ tạo một mock và gán nó vào field của test khi Mockito extension xử lý test. Spring không tự biết field đó tồn tại và cũng không thay dependency trong bean đã được tạo.

Nếu test gọi `orderService` được inject từ Spring, `orderService` vẫn có thể giữ `PaymentGateway` thật. Stub trên mock field không tác động đến object graph của Spring.

Có hai cách kiểm thử hợp lệ, tùy mục tiêu:

- Unit test thuần Mockito: Mockito tạo cả mock lẫn đối tượng cần kiểm tra, rồi inject mock vào đối tượng đó.
- Spring test: Spring tạo đối tượng cần kiểm tra và test yêu cầu Spring thay bean dependency bằng mock trong `ApplicationContext`.

Lỗi thường xuất hiện khi trộn hai cách mà không nhận ra chúng đang tạo ra hai instance khác nhau.

## 2. Dấu hiệu mock không được dùng

Một số biểu hiện thường gặp:

- `when(mock.method()).thenReturn(...)` đã khai báo nhưng kết quả trả về vẫn giống hệ thống thật.
- `verify(mock).method()` báo `Wanted but not invoked` dù luồng nghiệp vụ có vẻ đã gọi dependency.
- Test bất ngờ cần database, broker hoặc dịch vụ HTTP bên ngoài.
- Stub trả về `null` hoặc giá trị mặc định vì lời gọi thực tế đi tới một mock khác.
- Test chạy qua một implementation khác với implementation mà người viết nghĩ đã thay thế.
- Một test class hoạt động, nhưng test khác lại sử dụng bean khác do qualifier, profile hoặc cấu hình context.

Những dấu hiệu này không nhất thiết có nghĩa Mockito bị lỗi. Thường cần kiểm tra wiring, phạm vi context và instance thực tế trước khi sửa stub.

## 3. `@Mock` không thay thế bean trong Spring

Ví dụ service nhận dependency qua constructor:

```java
interface PaymentGateway {
    PaymentResult charge(String orderId, long amount);
}

class OrderService {

    private final PaymentGateway paymentGateway;

    OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    PaymentResult pay(String orderId, long amount) {
        return paymentGateway.charge(orderId, amount);
    }
}
```

Ứng dụng đăng ký implementation thật:

```java
@Component
class HttpPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, long amount) {
        // Gọi payment provider qua HTTP.
        return callPaymentProvider(orderId, amount);
    }
}
```

Một test dễ gây nhầm lẫn:

```java
@SpringBootTest
class OrderServiceTest {

    @Mock
    PaymentGateway paymentGateway;

    @Autowired
    OrderService orderService;

    @Test
    void usesStubbedPaymentResult() {
        when(paymentGateway.charge("ORD-1", 5000))
                .thenReturn(new PaymentResult("APPROVED"));

        PaymentResult result = orderService.pay("ORD-1", 5000);

        assertThat(result.status()).isEqualTo("APPROVED");
        verify(paymentGateway).charge("ORD-1", 5000);
    }
}
```

`@Mock` ở đây tạo một Mockito mock cho field `paymentGateway`. Nhưng `orderService` được lấy từ Spring context; Spring đã inject bean `HttpPaymentGateway` vào service. Hai dependency không phải cùng một object. Stub của test không điều khiển lời gọi mà service thực hiện.

Đừng cố khắc phục bằng cách stub lại nhiều lần hoặc thay matcher. Trước hết hãy đưa mock vào đúng object graph.

## 4. Dùng `@MockitoBean` để thay bean trong ApplicationContext

Trong Spring Framework 6.2 trở lên, `@MockitoBean` cho phép khai báo một Mockito mock làm bean override trong test `ApplicationContext`. Annotation nằm trong package `org.springframework.test.context.bean.override.mockito`.

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class OrderServiceTest {

    @Autowired
    OrderService orderService;

    @MockitoBean
    PaymentGateway paymentGateway;

    @Test
    void usesThePaymentGatewayMockFromSpringContext() {
        when(paymentGateway.charge("ORD-1", 5000))
                .thenReturn(new PaymentResult("APPROVED"));

        PaymentResult result = orderService.pay("ORD-1", 5000);

        assertThat(result.status()).isEqualTo("APPROVED");
        verify(paymentGateway).charge("ORD-1", 5000);
    }
}
```

Spring áp dụng mock vào bean phù hợp trong context. Khi tạo `OrderService`, dependency mà Spring inject là mock được khai báo bởi `@MockitoBean`, nên stub và verify trên field `paymentGateway` quan sát đúng lời gọi.

Mặc định, `@MockitoBean` có thể thay bean hiện có hoặc tạo mock bean nếu chưa có bean phù hợp. Nếu test cần xác nhận bean thật sự phải tồn tại trong context trước khi thay thế, có thể dùng `enforceOverride = true`:

```java
@MockitoBean(enforceOverride = true)
PaymentGateway paymentGateway;
```

Khi đó test sẽ thất bại nếu không tìm thấy bean để override. Tùy chọn này hữu ích để phát hiện cấu hình slice hoặc component scan thiếu bean mà test kỳ vọng.

## 5. Chọn đúng annotation theo phiên bản Spring

Các dự án Spring có thể dùng annotation khác nhau tùy phiên bản:

| Annotation | Package | Vai trò |
|---|---|---|
| `@Mock` | `org.mockito.Mock` | Tạo mock trong test; không thay bean Spring |
| `@InjectMocks` | `org.mockito.InjectMocks` | Mockito tạo đối tượng test và inject các mock/spies phù hợp |
| `@MockitoBean` | `org.springframework.test.context.bean.override.mockito.MockitoBean` | Override bean bằng Mockito mock trong Spring context |
| `@MockitoSpyBean` | `org.springframework.test.context.bean.override.mockito.MockitoSpyBean` | Wrap bean hiện có bằng spy trong Spring context |
| `@MockBean` | `org.springframework.boot.test.mock.mockito.MockBean` | Cơ chế Spring Boot cũ để thêm/thay bean bằng mock |

`@MockitoBean` và `@MockitoSpyBean` có từ Spring Framework 6.2. Spring Boot 3.4 chuyển sang khuyến nghị các annotation mới này; `@MockBean` và `@SpyBean` cũ được đánh dấu deprecated trong dòng Boot 3.4. Với dự án Boot cũ hơn chưa có Spring Framework 6.2, dùng `@MockBean` theo phiên bản đang quản lý.

Ví dụ tương thích với các dự án Spring Boot cũ:

```java
import org.springframework.boot.test.mock.mockito.MockBean;

@SpringBootTest
class OrderServiceLegacyTest {

    @Autowired
    OrderService orderService;

    @MockBean
    PaymentGateway paymentGateway;
}
```

Không import nhầm `org.mockito.Mock` khi mục tiêu là thay bean Spring. Tên annotation gần nhau nhưng phạm vi tác động khác nhau.

## 6. Dùng `@Mock` và `@InjectMocks` cho unit test thuần

Nếu không cần Spring context, hãy để Mockito tạo đối tượng đang được kiểm tra. Đây là cách đúng để dùng `@Mock`:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceUnitTest {

    @Mock
    PaymentGateway paymentGateway;

    @InjectMocks
    OrderService orderService;

    @Test
    void returnsTheResultFromGateway() {
        when(paymentGateway.charge("ORD-1", 5000))
                .thenReturn(new PaymentResult("APPROVED"));

        PaymentResult result = orderService.pay("ORD-1", 5000);

        assertThat(result.status()).isEqualTo("APPROVED");
        verify(paymentGateway).charge("ORD-1", 5000);
    }
}
```

`MockitoExtension` khởi tạo các annotation Mockito. `@InjectMocks` yêu cầu Mockito tạo instance `OrderService` và inject mock phù hợp. Test gọi chính instance này, nên dependency mock được dùng.

Không cần `@SpringBootTest` cho test trên. Cũng không nên đồng thời inject một `OrderService` khác bằng `@Autowired` rồi gọi bean Spring trong khi stub mock được tạo cho `@InjectMocks`. Nếu gọi nhầm instance, test lại gặp đúng vấn đề ban đầu.

Mockito thường ưu tiên constructor injection, sau đó mới thử setter/property và field injection theo cơ chế của `@InjectMocks`. Tuy nhiên, `@InjectMocks` không phải dependency injection container đầy đủ: nó không chạy Spring lifecycle, không áp dụng bean post-processor, `@Value`, `@Transactional`, `@Async`, qualifier semantics hoặc cấu hình AOP của Spring. Nếu test cần những hành vi đó, dùng Spring context.

## 7. Kiểm tra đúng bean trong Spring MVC slice

Một trường hợp phổ biến là test controller bằng `@WebMvcTest`. Slice này tạo MVC infrastructure và controller được chọn; service thường được thay bằng mock.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void delegatesToTheMockedService() throws Exception {
        when(orderService.findStatus("ORD-1"))
                .thenReturn("PAID");

        mockMvc.perform(get("/orders/ORD-1/status"))
                .andExpect(status().isOk());

        verify(orderService).findStatus("ORD-1");
    }
}
```

Trong test slice, `@MockitoBean` cung cấp dependency mà controller cần. Không cần nạp database hoặc toàn bộ service layer nếu test chỉ quan tâm đến MVC contract.

Nếu controller cần một bean khác ngoài slice, có thể mock bean đó, import cấu hình cần thiết hoặc chọn một test context rộng hơn. `@WebMvcTest` không tự nạp mọi service/repository của ứng dụng.

## 8. Qualifier và nhiều bean cùng kiểu

Nếu có nhiều bean cùng implement một interface, chỉ khai báo mock theo type có thể không xác định được bean mà đối tượng đang dùng. Ví dụ:

```java
@Component("cardPaymentGateway")
class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component("walletPaymentGateway")
class WalletPaymentGateway implements PaymentGateway {
    // ...
}
```

Service chọn implementation bằng qualifier:

```java
class OrderService {

    private final PaymentGateway paymentGateway;

    OrderService(@Qualifier("cardPaymentGateway") PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Test cũng phải override đúng candidate:

```java
@MockitoBean
@Qualifier("cardPaymentGateway")
PaymentGateway cardPaymentGateway;
```

Hoặc chỉ định tên bean trực tiếp:

```java
@MockitoBean(name = "cardPaymentGateway")
PaymentGateway paymentGateway;
```

`@Primary` chỉ ảnh hưởng đến lựa chọn candidate khi Spring giải quyết injection theo type mà không có qualifier cụ thể. Nếu constructor yêu cầu một qualifier cụ thể, hãy mock đúng bean được qualifier đó chọn.

Tên field của `@MockitoBean` cũng có thể được dùng như qualifier fallback khi không có qualifier rõ ràng. Vì vậy, khi có nhiều bean cùng kiểu, tên field nên phản ánh bean mà test muốn override. Cách rõ ràng nhất vẫn là khai báo `@Qualifier` hoặc `name` khi cấu hình ứng dụng có nhiều implementation.

## 9. Phân biệt mock bean và spy bean

`@MockitoBean` thay bean bằng mock. Lời gọi không được stub sẽ theo hành vi mặc định của Mockito, thường trả giá trị mặc định như `null`, `0` hoặc `false`.

`@MockitoSpyBean` wrap bean hiện có bằng spy, nên lời gọi không stub vẫn có thể chạy logic thật. Dùng spy khi muốn giữ phần lớn hành vi của bean nhưng quan sát hoặc thay đổi một số lời gọi cụ thể.

```java
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

@SpringBootTest
class PricingServiceTest {

    @Autowired
    PricingService pricingService;

    @MockitoSpyBean
    ExchangeRateProvider exchangeRateProvider;
}
```

Với spy, cẩn thận khi stub method có side effect. Cách `when(spy.method()).thenReturn(...)` có thể gọi method thật trong lúc thiết lập stub. Mockito cung cấp `doReturn(...).when(spy).method(...)` để tránh gọi method thật trong một số trường hợp.

Không dùng spy chỉ vì mock không được inject. Trước tiên phải xác định test muốn thay toàn bộ dependency hay muốn giữ implementation thật. Nếu mục tiêu là không gọi hệ thống ngoài, mock bean thường đúng hơn spy.

## 10. Đối tượng được tạo bằng `new` không nhận dependency override của Spring

Một lỗi khác là test tạo controller/service bằng `new`, trong khi lại kỳ vọng `@MockitoBean` tác động tới object đó:

```java
@SpringBootTest
class OrderControllerTest {

    @MockitoBean
    OrderService orderService;

    @Test
    void test() {
        OrderController controller = new OrderController(
                new RealOrderService());

        // controller này đang giữ RealOrderService.
    }
}
```

`@MockitoBean` chỉ thay bean trong Spring context. Đối tượng được tạo thủ công không được Spring quản lý, nên constructor vẫn nhận `RealOrderService` mà test truyền vào.

Hãy chọn một trong hai cách:

**Cách Spring-managed:** inject controller từ context và để Spring truyền mock bean vào constructor.

```java
@Autowired
OrderController controller;

@MockitoBean
OrderService orderService;
```

**Cách unit test:** tạo controller thủ công nhưng truyền mock trực tiếp.

```java
@ExtendWith(MockitoExtension.class)
class OrderControllerUnitTest {

    @Mock
    OrderService orderService;

    @InjectMocks
    OrderController controller;
}
```

Không tạo một instance bằng `new` rồi kiểm tra nó như thể đó là bean Spring.

## 11. Kiểm tra bean có thực sự tồn tại trong test context

Nếu `@MockitoBean` không được dùng như mong đợi, hãy kiểm tra context có chứa bean mục tiêu hay không. Một slice có thể không load service; một profile có thể loại bean; một `@ConditionalOnProperty` có thể không thỏa điều kiện.

Ví dụ khi biết chính xác tên bean:

```java
@Autowired
ApplicationContext applicationContext;

@MockitoBean(name = "paymentGateway")
PaymentGateway paymentGateway;

@Test
void contextUsesTheExpectedMock() {
    assertThat(applicationContext.getBean("paymentGateway"))
            .isSameAs(paymentGateway);
}
```

Đây là assertion chẩn đoán hữu ích khi cần xác nhận override đã được áp dụng. Không nhất thiết phải lặp lại trong mọi test nếu cấu hình đã rõ ràng.

Nếu dùng `enforceOverride = true`, Spring sẽ báo lỗi khi bean không tồn tại để thay thế. Điều này giúp phân biệt hai trường hợp:

- Context có bean đúng nhưng test chưa override đúng candidate.
- Context chưa load bean mà test nghĩ rằng đang kiểm tra.

Với slice test, nếu bean cần mock không nằm trong slice, có thể để `@MockitoBean` tạo mock mới để thỏa dependency của controller. Nếu muốn test wiring production đầy đủ, dùng context rộng hơn và `enforceOverride = true` để xác nhận bean thực sự có trong cấu hình đó.

## 12. Những nguyên nhân wiring khác cần kiểm tra

Ngoài việc dùng nhầm annotation, mock có thể không được dùng do các nguyên nhân sau:

| Nguyên nhân | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Có nhiều bean cùng interface | Service nhận implementation khác với mock | Dùng `@Qualifier` hoặc `@MockitoBean(name = ...)` |
| Test gọi object được tạo thủ công | Spring bean override không có tác dụng | Inject bean từ context hoặc truyền mock vào constructor |
| Test slice không load bean mục tiêu | Bean không tồn tại hoặc dependency chưa được cấu hình | Import cấu hình, dùng đúng slice hoặc context rộng hơn |
| Profile/condition khác test mong đợi | Bean production không được đăng ký | Kiểm tra `@ActiveProfiles`, property và `@Conditional...` |
| Factory tạo một object khác | Test field và bean runtime không cùng instance | Kiểm tra `@Bean` method và nơi object được tạo |
| Dependency được giữ trong một singleton khác | Mock bean mới không thay reference đã được tạo ở nơi khác | Kiểm tra lifecycle và object graph của singleton đó |
| Có proxy/AOP | Object inject có thể là proxy | Xác định bean target và kiểm tra mock field được override đúng |
| Stub sai argument hoặc matcher | Mock được gọi nhưng không khớp stub | Dùng `ArgumentCaptor`, matcher nhất quán và kiểm tra lời gọi thực tế |
| Test chạy async hoặc trên thread khác | Verify xảy ra trước khi lời gọi hoàn tất | Chờ điều kiện hoàn tất bằng latch/Awaitility hoặc publisher verification |

Proxy do `@Transactional`, `@Async`, security hoặc AOP không tự động có nghĩa mock bị bỏ qua. Tuy nhiên, proxy có thể làm việc quan sát instance khó hơn. Hãy kiểm tra bean dependency thực sự được truyền vào target và verify trên mock field đã đăng ký trong context.

## 13. Phân biệt lỗi injection với lỗi stub

Không phải mọi `Wanted but not invoked` đều là lỗi Spring wiring. Có thể mock đúng nhưng lời gọi không xảy ra vì nhánh điều kiện khác, hoặc argument thực tế không khớp stub.

### Kiểm tra lời gọi bằng ArgumentCaptor

```java
ArgumentCaptor<String> orderIdCaptor = ArgumentCaptor.forClass(String.class);

verify(paymentGateway).charge(orderIdCaptor.capture(), anyLong());
assertThat(orderIdCaptor.getValue()).isEqualTo("ORD-1");
```

Nếu verify thành công nhưng stub không được áp dụng, kiểm tra matcher. Mockito yêu cầu khi một argument dùng matcher thì các argument còn lại cũng cần dùng matcher:

```java
when(paymentGateway.charge(eq("ORD-1"), anyLong()))
        .thenReturn(new PaymentResult("APPROVED"));
```

Nếu verify không tìm thấy lời gọi, quay lại kiểm tra instance và object graph trước khi thay đổi matcher.

### Kiểm tra mock có nhận tương tác nào không

```java
verifyNoInteractions(paymentGateway);
```

Assertion này chỉ phù hợp khi hợp đồng của test yêu cầu dependency không được gọi. Nếu test mong có lời gọi, hãy verify đúng method và argument. Không dùng `verifyNoInteractions` như một cách chẩn đoán mặc định sau khi test đã gọi service.

## 14. Test với nhiều dependency

Nếu service có nhiều dependency, chỉ mock những ranh giới cần kiểm soát. Ví dụ:

```java
@SpringBootTest
class OrderWorkflowTest {

    @Autowired
    OrderWorkflow orderWorkflow;

    @MockitoBean
    PaymentGateway paymentGateway;

    @MockitoBean
    FraudCheckClient fraudCheckClient;

    @Test
    void approvesOrderWhenChecksPass() {
        when(fraudCheckClient.isAllowed("ORD-1")).thenReturn(true);
        when(paymentGateway.charge("ORD-1", 5000))
                .thenReturn(new PaymentResult("APPROVED"));

        OrderResult result = orderWorkflow.process("ORD-1", 5000);

        assertThat(result.status()).isEqualTo("PAID");
        verify(fraudCheckClient).isAllowed("ORD-1");
        verify(paymentGateway).charge("ORD-1", 5000);
    }
}
```

Hai mock được đăng ký vào Spring context, nên bean `OrderWorkflow` nhận đúng các dependency đó. Repository hoặc database có thể vẫn là thật nếu test chủ ý kiểm tra persistence. Phạm vi test cần nhất quán: mock gateway bên ngoài nhưng dùng database thật là một integration test hợp lệ.

## 15. Reset mock và chia sẻ ApplicationContext

Spring TestContext có thể cache context để tăng tốc giữa các test class. Bean mock được đăng ký trong context có thể được dùng lại cùng context theo cơ chế test framework. Spring bean override mặc định reset mock sau mỗi test method để tránh invocation/stubbing cũ rò sang test tiếp theo.

Nếu thay đổi chính sách reset, hãy hiểu rõ tác động khi test chạy song song. Không dùng một mock singleton để lưu trạng thái riêng của từng test. Mỗi test nên tự khai báo stub và chỉ verify tương tác do chính test đó tạo ra.

Nếu một test thay đổi cấu hình context hoặc dùng override khác, Spring có thể tạo context riêng. Điều này ảnh hưởng thời gian chạy nhưng không phải bằng chứng rằng mock không được inject. Hãy kiểm tra cấu hình test và bean identity trước khi thêm `@DirtiesContext`.

## 16. Quy trình chẩn đoán có hệ thống

Khi stub không được dùng hoặc verify báo mock không có lời gọi, hãy đi theo trình tự:

1. Xác định method thực sự đang được gọi và object nhận lời gọi đó.
2. Xác định object được tạo bởi Spring hay bằng `new`/factory riêng.
3. Kiểm tra test đang gọi bean `@Autowired` hay instance `@InjectMocks`.
4. Nếu test thuần Mockito, dùng `@Mock` và `@InjectMocks` trên cùng object graph.
5. Nếu test dùng Spring, thay dependency bằng `@MockitoBean` hoặc `@MockBean` phù hợp phiên bản.
6. Kiểm tra bean candidate theo type, name, qualifier, profile và conditional configuration.
7. Nếu dùng slice, xác nhận bean mục tiêu có trong context hoặc được mock để thỏa dependency.
8. Stub đúng argument và matcher; dùng `ArgumentCaptor` để quan sát lời gọi thực tế.
9. Nếu luồng async, chờ lời gọi hoàn tất trước khi verify.
10. Chỉ sau khi xác nhận đúng instance mới xem xét thay đổi cách stub hoặc matcher.

## 17. Những lỗi thường gặp

| Cách làm | Vì sao sai | Cách làm phù hợp hơn |
|---|---|---|
| Dùng `@Mock` rồi gọi service `@Autowired` | Mock chỉ tồn tại ở test field, không thay bean trong context | Dùng `@MockitoBean` hoặc `@MockBean` |
| Dùng `@InjectMocks` nhưng gọi bean Spring | Mockito và Spring tạo hai instance khác nhau | Chọn unit test thuần hoặc Spring test rõ ràng |
| Tạo controller bằng `new` rồi kỳ vọng bean override tác động | Object thủ công không đi qua Spring injection | Inject controller từ context hoặc truyền mock trực tiếp |
| Mock theo type khi có nhiều implementation | Spring có thể chọn bean khác | Khai báo qualifier hoặc bean name |
| Dùng `@MockitoBean` trong slice nhưng mong mọi service production được load | Slice chỉ tạo một phần context | Import cấu hình hoặc chọn context rộng hơn |
| Dùng spy để ngăn gọi hệ thống ngoài | Spy vẫn gọi method thật nếu không stub | Dùng mock bean cho dependency cần thay hoàn toàn |
| Chỉnh matcher trước khi xác nhận mock được gọi | Có thể che giấu lỗi wiring | Verify instance và argument trước |
| Thêm `@DirtiesContext` ngay khi verify thất bại | Không sửa nguyên nhân injection | Chẩn đoán object graph và bean override trước |

## 18. Tài liệu tham khảo

- [Spring Framework Reference — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): cơ chế override bean trong Spring TestContext.
- [Spring Framework Javadoc — `@MockitoBean`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html): thay bean bằng Mockito mock.
- [Spring Framework Javadoc — `@MockitoSpyBean`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoSpyBean.html): wrap bean hiện có bằng Mockito spy.
- [Spring Boot Reference — Mocking and Spying Beans](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): hỗ trợ mock/spy bean trong Spring Boot test và chuyển tiếp sang annotation của Spring Framework.
- [Mockito — `@InjectMocks`](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/InjectMocks.html): cơ chế Mockito tạo instance và inject mock trong unit test.
- [Mockito — JUnit Jupiter Extension](https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org/mockito/junit/jupiter/MockitoExtension.html): khởi tạo và quản lý annotation Mockito cho JUnit Jupiter.

Mock chỉ có tác dụng với object graph mà nó thực sự được gắn vào. Trong unit test, hãy để Mockito tạo đối tượng cần kiểm tra và inject mock vào nó. Trong Spring test, hãy yêu cầu Spring override đúng bean bằng `@MockitoBean` hoặc annotation tương ứng với phiên bản dự án. Khi stub không được dùng, kiểm tra instance, bean type/name/qualifier và phạm vi context trước khi sửa matcher.
