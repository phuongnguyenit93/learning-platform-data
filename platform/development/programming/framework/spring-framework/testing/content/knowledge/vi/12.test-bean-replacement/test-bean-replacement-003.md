# `@MockitoBean` và thay thế thành phần cộng tác trong context

Khi kiểm thử một ứng dụng Spring, đôi khi cần giữ nguyên `ApplicationContext`, controller, service hoặc cấu hình thật nhưng thay một thành phần cộng tác bằng mock. Ví dụ, một bài kiểm thử MVC cần chạy request qua Spring MVC và security filter, nhưng không cần gọi database hay cổng thanh toán thật. Ta muốn controller thật được khởi tạo trong context, còn `OrderService` được thay bằng một Mockito mock để kiểm soát kết quả.

Spring Framework 6.2 giới thiệu `@MockitoBean` để đăng ký mock trực tiếp trong `ApplicationContext` của test. Annotation này thay thế bean phù hợp bằng Mockito mock; nếu không tìm thấy bean tương ứng, mặc định Spring có thể tạo mock bean mới. Nhờ đó, các bean phụ thuộc vào type được mock sẽ nhận mock trong quá trình dependency injection.

`@MockitoBean` đặc biệt hữu ích với các test dùng `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` hoặc `@ContextConfiguration`, khi mục tiêu là kiểm tra một phần ứng dụng trong context thật và cô lập một số dependency bên ngoài.

## 1. `@MockitoBean` là gì?

`@MockitoBean` thuộc package:

```java
org.springframework.test.context.bean.override.mockito.MockitoBean
```

Đây là annotation của Spring TestContext Framework, có từ **Spring Framework 6.2.0**. Nó tích hợp Mockito với cơ chế bean override của Spring để thêm mock vào test `ApplicationContext` hoặc thay thế bean hiện có.

Ví dụ cơ bản:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsOrderDetails() throws Exception {
        when(orderService.findById("order-42"))
            .thenReturn(new OrderResponse("order-42", "PAID"));

        mockMvc.perform(get("/orders/order-42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("order-42"))
            .andExpect(jsonPath("$.status").value("PAID"));

        verify(orderService).findById("order-42");
    }
}
```

Trong ví dụ, `OrderController` là bean thật được Spring MVC tạo. `OrderService` được thay bằng mock. Request đi qua `MockMvc`, còn kết quả của service được test kiểm soát bằng `when()` và `thenReturn()`.

Khi controller inject `OrderService` qua constructor, nó nhận đúng mock được đăng ký trong context. Field `orderService` trong test class cũng được Spring gán cùng mock đó, nên test có thể stub và verify trực tiếp.

## 2. Phân biệt `@MockitoBean` với `@Mock`

Hai annotation đều tạo Mockito mock, nhưng phạm vi quản lý khác nhau:

| Tiêu chí | `@Mock` | `@MockitoBean` |
| --- | --- | --- |
| Nguồn | Mockito | Spring Test |
| Vị trí sử dụng phổ biến | Unit test thuần | Test có `ApplicationContext` |
| Đăng ký vào Spring context | Không | Có |
| Thay thế bean hiện có | Không | Có |
| Bean khác được inject mock tự động | Không | Có, theo type/qualifier phù hợp |
| Tạo context Spring | Không cần | Cần tích hợp Spring Test |
| Mục tiêu phù hợp | Kiểm tra một class bằng cách truyền mock vào constructor | Kiểm tra một phần ứng dụng trong context Spring |

Ví dụ unit test thuần dùng `@Mock`:

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderService = new OrderService(repository);
    }

    @Test
    void returnsOrderWhenItExists() {
        when(repository.findById("order-42"))
            .thenReturn(Optional.of(sampleOrder()));

        Order result = orderService.findById("order-42");

        assertEquals("order-42", result.getId());
    }
}
```

Unit test này không cần Spring context. Ta tự tạo service thật và truyền mock repository vào constructor.

Khi cần kiểm tra controller, filter, converter, bean wiring hoặc cấu hình Spring, `@MockitoBean` cho phép thay một collaborator ngay trong context. Không cần dùng `@MockitoBean` cho mọi unit test; chỉ dùng nó khi context Spring là một phần của điều cần kiểm tra.

## 3. Spring Framework 6.2 và khả năng tương thích phiên bản

`@MockitoBean` được giới thiệu trong Spring Framework 6.2.0. Nếu dự án dùng Spring Framework 6.1 hoặc thấp hơn, annotation này chưa có trong `spring-test`.

| Phiên bản | Cách tiếp cận |
| --- | --- |
| Spring Framework trước 6.2 | Dùng cơ chế phù hợp của phiên bản, thường là `@MockBean` của Spring Boot Test hoặc mock thủ công trong unit test |
| Spring Framework 6.2 trở lên | Dùng `@MockitoBean` của Spring Test |
| Spring Boot 3.4 trở lên | Có thể dùng `@MockitoBean`; `@MockBean` của Spring Boot đã được deprecated để chuyển sang annotation của Spring Framework |

Trong Spring Boot, version của Spring Framework thường được quản lý bởi dependency management. Hãy xác định version `spring-test` thực tế trong test runtime trước khi sử dụng annotation.

Với Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-test
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
```

Nếu dự án chưa dùng Spring Framework 6.2, không thể chỉ thêm import `@MockitoBean` mà không nâng dependency tương thích. Trong hệ sinh thái Spring Boot, hãy nâng theo phiên bản Boot hỗ trợ thay vì tự ép một version Spring Framework khác với dependency management của dự án.

## 4. Cách Spring thay thế bean trong context

Khi phát hiện `@MockitoBean`, Spring Test đăng ký một bean override trong quá trình xây dựng test `ApplicationContext`. Mock được tạo bởi Mockito và đưa vào context theo type, tên bean hoặc qualifier phù hợp.

Mặc định, chiến lược là **replace or create**:

- Nếu tìm thấy bean phù hợp, bean đó được thay bằng Mockito mock.
- Nếu không tìm thấy bean phù hợp, Spring tạo mock bean mới và đăng ký vào context.

Điều này hữu ích trong test slice. Ví dụ, `@WebMvcTest(OrderController.class)` chỉ nạp một phần web layer; `OrderService` có thể chưa được đưa vào slice. `@MockitoBean OrderService` tạo mock để controller vẫn có thể được inject.

Nếu muốn bắt buộc phải thay thế bean đã tồn tại, đặt `enforceOverride = true`:

```java
@MockitoBean(enforceOverride = true)
OrderService orderService;
```

Với cấu hình này, nếu context không có bean phù hợp để thay thế, Spring sẽ báo lỗi khi tạo context. Cách này hữu ích khi test cần bảo đảm bean production thực sự tồn tại và đang được thay thế; nó tránh tình huống test âm thầm tạo một mock mới do cấu hình context bị thiếu.

## 5. Khai báo mock ở field của test class

Cách thường gặp nhất là đặt `@MockitoBean` trên field của test class:

```java
@SpringBootTest
class CheckoutIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @MockitoBean
    PaymentGateway paymentGateway;

    @Test
    void completesCheckoutWhenPaymentIsApproved() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved("payment-123"));

        CheckoutResult result = checkoutService.checkout(validCommand());

        assertTrue(result.isCompleted());
        verify(paymentGateway).charge(any(PaymentRequest.class));
    }
}
```

`CheckoutService` và các bean còn lại trong context được tạo theo cấu hình ứng dụng. Khi Spring inject `PaymentGateway` vào `CheckoutService`, mock đã đăng ký bởi `@MockitoBean` được sử dụng.

Field có annotation cũng nhận mock để test cấu hình hành vi và verify. Vì thế, test không cần gọi `applicationContext.getBean(PaymentGateway.class)` để lấy mock.

### Tên field và qualifier

Nếu context có nhiều bean cùng type, Spring cần biết bean nào cần thay thế. Có thể dùng `@Qualifier` trên field:

```java
@MockitoBean
@Qualifier("primaryPaymentGateway")
PaymentGateway paymentGateway;
```

Hoặc chỉ định tên bean:

```java
@MockitoBean(name = "primaryPaymentGateway")
PaymentGateway paymentGateway;
```

Nếu không chỉ định qualifier hoặc tên, Spring trước tiên tìm bean theo type. Tên field có thể được dùng làm qualifier fallback khi cần phân biệt nhiều bean cùng type. Vì vậy, tên field trong test cũng có thể ảnh hưởng bean nào được chọn.

Hãy dùng qualifier hoặc tên bean rõ ràng khi có nhiều implementation như `sandboxPaymentGateway`, `primaryPaymentGateway` và `fallbackPaymentGateway`. Không dựa vào thứ tự khai báo bean để chọn implementation.

## 6. Thay một bean cụ thể khi có nhiều implementation

Giả sử ứng dụng có hai adapter cùng implement `PaymentGateway`:

```java
@Component("cardPaymentGateway")
class CardPaymentGateway implements PaymentGateway {
    // Gọi cổng thanh toán thẻ
}

@Component("walletPaymentGateway")
class WalletPaymentGateway implements PaymentGateway {
    // Gọi cổng ví điện tử
}
```

Service inject implementation theo qualifier:

```java
@Service
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(
            @Qualifier("cardPaymentGateway") PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Test chỉ thay adapter thẻ:

```java
@SpringBootTest
class CheckoutServiceTest {

    @MockitoBean(name = "cardPaymentGateway")
    PaymentGateway cardGateway;

    @Autowired
    CheckoutService checkoutService;

    @Test
    void usesTheCardGatewayForCardCheckout() {
        when(cardGateway.charge(any()))
            .thenReturn(PaymentResult.approved("card-123"));

        checkoutService.checkout(cardCommand());

        verify(cardGateway).charge(any());
    }
}
```

Bean ví điện tử vẫn là bean thật trong context. Test thay đúng bean có tên `cardPaymentGateway`. Nếu service cần một implementation cụ thể, qualifier trong production và tên mock trong test nên khớp nhau.

## 7. Khai báo mock ở cấp class bằng `types`

`@MockitoBean` có thể được đặt ở cấp type trên test class. Khi dùng ở cấp class, khai báo các type cần mock qua thuộc tính `types`:

```java
@SpringBootTest
@MockitoBean(types = {
    PaymentGateway.class,
    NotificationGateway.class
})
class OrderWorkflowTest {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrderWithoutCallingExternalSystems() {
        // Các mock được đăng ký trong ApplicationContext
    }
}
```

Cách khai báo ở cấp class hữu ích khi một nhóm test hoặc một cấu hình test dùng chung cùng tập mock. Nếu test cần stub hoặc verify trực tiếp, có thể inject mock qua `@Autowired` hoặc dùng field-level declaration để có field tham chiếu rõ ràng.

Field-level declaration thường dễ đọc hơn khi mỗi mock có hành vi riêng trong test. Type-level declaration phù hợp khi muốn gom các bean override chung cho cả class hoặc tái sử dụng cấu hình qua annotation composed.

## 8. `@MockitoBean` với `@WebMvcTest`

`@WebMvcTest` chỉ nạp phần MVC cần thiết, chẳng hạn controller, MVC configuration, converter, filter được chọn và các thành phần web liên quan. Service hoặc repository thường không được nạp như trong full context.

Khi controller phụ thuộc service, cung cấp mock bằng `@MockitoBean`:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsNotFoundWhenOrderDoesNotExist() throws Exception {
        when(orderService.findById("missing"))
            .thenThrow(new OrderNotFoundException("missing"));

        mockMvc.perform(get("/orders/missing"))
            .andExpect(status().isNotFound());
    }
}
```

Test này kiểm tra request mapping, exception handler và response của controller thông qua MVC pipeline. `OrderService` được thay bằng mock nên test không cần database hay dịch vụ ngoài.

Nếu controller có nhiều collaborator, khai báo mock cho từng dependency mà controller cần. Nếu một dependency được tạo bởi test configuration riêng, hãy bảo đảm test context nạp đúng configuration đó.

Không nên dùng `@MockitoBean` để thay controller đang được kiểm tra. Nếu controller bị thay bằng mock, request có thể không chạy qua implementation controller thật và test mất mục tiêu.

## 9. `@MockitoBean` với `@SpringBootTest`

`@SpringBootTest` tạo context rộng hơn và thường dùng để kiểm tra nhiều bean phối hợp. Có thể thay một hệ thống ngoài bằng mock trong khi giữ các thành phần ứng dụng khác:

```java
@SpringBootTest
class PlaceOrderIntegrationTest {

    @Autowired
    PlaceOrderService placeOrderService;

    @Autowired
    OrderRepository orderRepository;

    @MockitoBean
    PaymentPort paymentPort;

    @Test
    @Transactional
    void persistsOrderWhenPaymentSucceeds() {
        when(paymentPort.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved("payment-42"));

        OrderId orderId = placeOrderService.place(validCommand());

        assertTrue(orderRepository.findById(orderId).isPresent());
        verify(paymentPort).charge(any(PaymentRequest.class));
    }
}
```

Trong ví dụ, repository và service là bean thật, còn payment port là mock. Test có thể kiểm tra service phối hợp với persistence thật và xử lý phản hồi thanh toán được điều khiển.

Nếu mục tiêu là kiểm tra HTTP adapter của cổng thanh toán, không nên thay adapter đó bằng mock trong cùng bài test. Hãy tạo adapter test riêng bằng mock server để xác nhận request/response mapping.

## 10. `@MockitoBean` với test slice khác

Các test slice cũng có thể dùng bean override khi cần thay collaborator ngoài phạm vi slice.

Ví dụ `@DataJpaTest` tập trung vào JPA:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @MockitoBean
    AuditPublisher auditPublisher;

    @Test
    void savesOrderWithoutPublishingToExternalBroker() {
        // Test repository thật; publisher được thay bằng mock nếu bean thuộc slice
    }
}
```

Tuy nhiên, `@DataJpaTest` không tự nạp mọi bean của ứng dụng. Nếu `AuditPublisher` không có trong slice, `@MockitoBean` mặc định có thể tạo mock mới. Nếu muốn xác nhận slice thật sự đã có bean để thay, dùng `enforceOverride = true`.

Hãy giữ slice tập trung vào mục tiêu của nó. Nếu phải import quá nhiều service và adapter để test chạy, có thể đang cần một `@SpringBootTest` hoặc một test cấu hình chuyên biệt thay vì mở rộng slice quá mức.

## 11. Điều khiển mock bằng Mockito

Sau khi `@MockitoBean` đăng ký mock, có thể sử dụng các API Mockito thông thường:

```java
when(paymentGateway.charge(any()))
    .thenReturn(PaymentResult.approved("payment-123"));

verify(paymentGateway).charge(any());
verify(notificationGateway, never()).send(any());
```

Các kỹ thuật phổ biến:

| API | Mục đích |
| --- | --- |
| `when(...).thenReturn(...)` | Cấu hình giá trị trả về |
| `when(...).thenThrow(...)` | Mô phỏng exception |
| `doAnswer(...)` | Tạo phản hồi theo tham số hoặc logic tùy chỉnh |
| `verify(...)` | Xác nhận collaborator được gọi |
| `never()` | Xác nhận không có lời gọi |
| `times(n)` | Xác nhận số lần gọi |
| `ArgumentCaptor` | Thu thập tham số thực tế để kiểm tra |

Ví dụ kiểm tra payload:

```java
@Test
void sendsConfirmationForTheCreatedOrder() {
    when(paymentGateway.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    OrderId orderId = orderService.place(validCommand());

    ArgumentCaptor<OrderConfirmation> captor =
        ArgumentCaptor.forClass(OrderConfirmation.class);

    verify(notificationGateway).send(captor.capture());

    assertEquals(orderId, captor.getValue().orderId());
    assertEquals("customer@example.test", captor.getValue().email());
}
```

Chỉ xác nhận những tương tác có ý nghĩa với hợp đồng. Nếu test verify mọi lời gọi nội bộ, một refactor không đổi hành vi cũng có thể làm test thất bại.

## 12. Reset mock giữa các test method

Một mock trong context có thể được dùng bởi nhiều test method. Nếu stub hoặc invocation history còn lại, test sau có thể bị ảnh hưởng.

`@MockitoBean` hỗ trợ thuộc tính `reset`. Mặc định, mock được reset sau mỗi test method bằng chính sách `MockReset.AFTER`:

```java
@MockitoBean(reset = MockReset.AFTER)
PaymentGateway paymentGateway;
```

Các lựa chọn chính:

| Giá trị | Ý nghĩa |
| --- | --- |
| `MockReset.AFTER` | Reset sau mỗi test method; đây là mặc định |
| `MockReset.BEFORE` | Reset trước mỗi test method |
| `MockReset.NONE` | Không tự reset mock |

Ví dụ dùng `NONE`:

```java
@MockitoBean(reset = MockReset.NONE)
PaymentGateway paymentGateway;
```

Chỉ chọn `NONE` khi có lý do rõ ràng và test tự quản lý stub cùng invocation history. Nếu không, trạng thái mock có thể rò rỉ giữa các test method.

Reset mock xóa stubbing và lịch sử tương tác theo cơ chế Mockito. Nó không hoàn tác side effect mà implementation thật đã thực hiện trước đó. Với `@MockitoBean`, bean được thay bằng mock nên method thật của bean đó không được chạy; nhưng các bean khác trong context vẫn có thể thực hiện side effect của chúng.

## 13. `@MockitoBean` và context cache

Spring Test cache `ApplicationContext` để các test có cấu hình tương đương có thể tái sử dụng context. Bean override là một phần của cấu hình test context. Vì vậy, các test class có tập `@MockitoBean` khác nhau có thể cần context cache entry khác nhau.

Một số yếu tố có thể làm cấu hình bean override khác nhau:

- Type của mock.
- Bean name được chỉ định.
- Qualifier metadata.
- Các thuộc tính cấu hình override.
- Số lượng và cách khai báo mock trong test class.

Tên field cũng có thể trở thành qualifier fallback. Vì vậy, hai test class mock cùng type nhưng dùng tên field khác nhau có thể được xem là cấu hình override khác nhau. Nếu muốn tái sử dụng context tốt hơn, hãy thống nhất tên field và metadata cho cùng một mock dùng chung.

Không nên thêm nhiều `@MockitoBean` vào một base class dùng chung nếu mỗi test con thực sự cần một tập dependency khác nhau. Điều đó có thể làm context phình lớn hoặc tạo nhiều cache key khác nhau. Hãy chỉ mock những collaborator cần thiết cho test.

## 14. Dùng chung cấu hình mock qua test superclass hoặc meta-annotation

Khi nhiều test class cần cùng một bean override, có thể tổ chức cấu hình chung. Ví dụ, một base test class:

```java
abstract class ExternalGatewayTestSupport {

    @MockitoBean
    protected PaymentGateway paymentGateway;

    @MockitoBean
    protected NotificationGateway notificationGateway;
}
```

Các test class kế thừa có thể dùng các mock này:

```java
@SpringBootTest
class OrderWorkflowTest extends ExternalGatewayTestSupport {

    @Autowired
    OrderService orderService;
}
```

Spring Test hỗ trợ kế thừa cấu hình test và các bean override theo quy tắc của TestContext. Hãy giữ base class nhỏ, có một nhóm mock thực sự dùng chung và tránh tạo một lớp cha chứa mọi mock của toàn bộ hệ thống.

Với cấu hình dùng chung ở cấp type, có thể tạo composed annotation bằng các annotation Spring Test phù hợp. Cách này hữu ích khi nhiều class cần cùng một tập bean override. Hãy bảo đảm cấu hình không vô tình thay thế collaborator mà một test cần kiểm tra thật.

## 15. Bean override trong context hierarchy

Một số ứng dụng dùng `@ContextHierarchy` để tạo parent context và child context. Nếu test cần thay bean ở một cấp cụ thể, `@MockitoBean` có thuộc tính `contextName` để giới hạn bean override vào context configuration có tên tương ứng.

Ví dụ khái quát:

```java
@ContextHierarchy({
    @ContextConfiguration(name = "parent", classes = RootConfig.class),
    @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class OrderWebIntegrationTest {

    @MockitoBean(contextName = "web")
    OrderViewService orderViewService;
}
```

Khi dùng hierarchy, hãy xác định bean được định nghĩa ở parent hay child. Nếu không giới hạn đúng context, bean override có thể được áp dụng ở nhiều cấp theo mặc định và tạo kết quả ngoài dự kiến. `contextName` phải khớp tên được khai báo trong `@ContextConfiguration`.

Nếu ứng dụng không cần parent-child context, không cần đưa `contextName` vào cấu hình thông thường.

## 16. Phân biệt `@MockitoBean` và `@MockitoSpyBean`

Hai annotation đều thuộc bean override infrastructure của Spring Test 6.2 nhưng có mục tiêu khác nhau:

| Annotation | Hành vi |
| --- | --- |
| `@MockitoBean` | Thay bean bằng mock; lời gọi được điều khiển bởi Mockito và không chạy implementation gốc theo mặc định |
| `@MockitoSpyBean` | Wrap bean hiện có bằng spy; method chưa stub tiếp tục chạy implementation thật |

Ví dụ spy:

```java
@SpringBootTest
class PricingServiceTest {

    @MockitoSpyBean
    PricingService pricingService;

    @Test
    void usesRealPricingLogic() {
        BigDecimal total = pricingService.calculateTotal(sampleCart());

        assertTrue(total.signum() > 0);
        verify(pricingService).calculateTotal(any());
    }
}
```

Với spy, cần cẩn thận khi stubbing. Cú pháp `when(spy.method()).thenReturn(...)` có thể gọi method thật ngay trong bước thiết lập. Dùng `doReturn(...).when(spy).method(...)` nếu muốn tránh side effect trong lúc stubbing.

Khi mục tiêu là thay hoàn toàn collaborator bên ngoài như payment gateway, email sender hoặc remote client, `@MockitoBean` thường rõ ràng hơn. Dùng spy khi cần giữ hành vi thật và chỉ quan sát hoặc thay thế có chọn lọc một phần bean.

## 17. Bean override không thay thế mục tiêu cần kiểm tra

Khi dùng `@MockitoBean`, hãy giữ bean đang kiểm tra là bean thật. Ví dụ:

- Test controller: giữ controller thật, mock service.
- Test service: giữ service thật, mock repository hoặc outbound port.
- Test orchestration: giữ use case thật, mock các hệ thống ngoài.
- Test adapter HTTP: giữ adapter thật và dùng mock server ở phía đối tác.

Nếu thay chính `OrderService` bằng mock trong bài test được đặt tên là `OrderServiceIntegrationTest`, test có thể chỉ xác nhận mock được gọi mà không chạy logic service. Tên test và assertion khi đó không chứng minh nghiệp vụ của service.

Tương tự, nếu thay repository bằng mock trong `@DataJpaTest`, test không còn kiểm tra query hoặc mapping JPA của repository đó. Hãy quyết định ranh giới cần kiểm tra trước khi chọn bean để thay.

## 18. Thay bean có điều kiện và `enforceOverride`

Mặc định `@MockitoBean` dùng chiến lược replace-or-create. Cách này phù hợp khi test slice không chứa bean production nhưng vẫn cần một collaborator mock để khởi tạo controller hoặc component.

Khi test cần bảo đảm bean thật đã được cấu hình, bật `enforceOverride`:

```java
@SpringBootTest
class PaymentConfigurationTest {

    @MockitoBean(enforceOverride = true)
    PaymentGateway paymentGateway;
}
```

Nếu không có bean `PaymentGateway` trong context, Spring báo lỗi thay vì âm thầm tạo mock mới. Điều này giúp phát hiện lỗi component scan, import configuration, profile hoặc test setup.

Ví dụ so sánh:

| Cấu hình | Bean có sẵn | Kết quả |
| --- | --- | --- |
| Mặc định | Có | Thay bean bằng mock |
| Mặc định | Không | Tạo mock bean mới |
| `enforceOverride = true` | Có | Thay bean bằng mock |
| `enforceOverride = true` | Không | Context khởi tạo thất bại vì không có bean để thay |

Chọn chế độ dựa trên ý định của test. Với slice test, tạo mock mới thường hợp lý; với test xác nhận wiring của full application, strict override có thể giúp tránh cấu hình thiếu bị che giấu.

## 19. Những giới hạn và điểm cần lưu ý

Bean override là một cơ chế thay thế bean trong test context, vì vậy có một số điều cần lưu ý:

- **Không kiểm tra implementation của bean bị thay:** mock không chứng minh logic, transaction hoặc side effect của bean gốc.
- **Chỉ override được bean phù hợp:** nếu type, qualifier hoặc tên không khớp, Spring có thể tạo mock mới hoặc báo lỗi tùy `enforceOverride`.
- **Nhiều bean cùng type cần phân biệt:** dùng `@Qualifier`, tên bean hoặc field name có chủ đích.
- **Scope bean cần được xem xét:** bean override infrastructure được thiết kế cho bean singleton; các bean có scope đặc biệt hoặc factory cần kiểm tra giới hạn theo phiên bản Spring.
- **Context cache có thể bị phân mảnh:** tập mock và qualifier khác nhau có thể tạo cache key khác nhau.
- **Mock vẫn có thể trả giá trị mặc định khó hiểu:** stub các phương thức quan trọng để test không vô tình phụ thuộc vào `null`, `false` hoặc collection rỗng mặc định.
- **Reset không cleanup hệ thống ngoài:** reset mock không xóa dữ liệu database, message hoặc file do bean khác tạo.
- **Không dùng thay cho kiểm thử adapter:** giao tiếp HTTP, SQL, broker và serialization cần test riêng khi đó là mục tiêu.

## 20. Những lỗi thường gặp

- **Dùng `@MockitoBean` trong unit test không có Spring context:** annotation không thay thế `@Mock` của Mockito trong test thuần.
- **Quên Spring Framework 6.2:** dependency `spring-test` cũ không có annotation này.
- **Mock nhầm bean đang kiểm tra:** test không chạy implementation thật nên không chứng minh hành vi mục tiêu.
- **Không chỉ rõ qualifier:** Spring chọn nhầm bean hoặc không thể xác định bean cần thay khi có nhiều implementation.
- **Không dùng `enforceOverride` khi cần strict replacement:** test tạo mock mới dù bean production dự kiến bị thiếu.
- **Mock quá nhiều collaborator:** test context phức tạp và phần lớn ứng dụng không còn được kiểm tra thật.
- **Không reset hoặc dùng `NONE` tùy tiện:** stub và invocation history rò rỉ giữa test method.
- **Dựa vào context restart để xóa mock state:** reset mock có cơ chế riêng; `@DirtiesContext` thường quá tốn kém cho mục đích đó.
- **Dùng mock thay adapter trong bài test adapter:** test chỉ kiểm tra mock chứ không kiểm tra giao tiếp thật.
- **Nhầm `@MockitoBean` với `@MockitoSpyBean`:** mock thay implementation, spy tiếp tục gọi method thật nếu chưa stub.

## 21. Quy trình chọn và sử dụng `@MockitoBean`

Khi cần thay một collaborator trong test context, hãy thực hiện theo trình tự:

1. **Xác định bean cần kiểm tra:** giữ bean này thật trong context.
2. **Xác định collaborator cần thay:** chọn dependency có side effect hoặc nằm ngoài phạm vi test.
3. **Kiểm tra phiên bản:** xác nhận Spring Framework 6.2 trở lên và `spring-test` có API tương ứng.
4. **Chọn cách định danh:** dùng type khi chỉ có một bean; dùng qualifier hoặc bean name khi có nhiều implementation.
5. **Chọn chiến lược override:** dùng mặc định nếu slice có thể thiếu bean; bật `enforceOverride` nếu bắt buộc thay bean có sẵn.
6. **Stub hành vi cần thiết:** cấu hình kết quả thành công và lỗi có ý nghĩa.
7. **Gọi hành vi qua bean thật:** chạy request, gọi service hoặc thực hiện luồng ứng dụng mà test cần xác nhận.
8. **Verify hợp đồng:** kiểm tra dữ liệu và số lần tương tác có ý nghĩa, tránh verify chi tiết nội bộ không cần thiết.
9. **Quản lý reset:** giữ mặc định `AFTER` trừ khi có lý do cụ thể để thay đổi.
10. **Bổ sung test adapter/integration khi cần:** mock bean không chứng minh cấu hình và giao tiếp của hệ thống ngoài.

`@MockitoBean` giúp thay thành phần cộng tác ngay trong `ApplicationContext`, để một phần ứng dụng Spring thật có thể được kiểm tra với dependency được điều khiển. Nó phù hợp khi cần giữ controller, service hoặc cấu hình thật nhưng cô lập một adapter hay dịch vụ ngoài. Hãy chọn đúng bean để thay, định danh rõ khi có nhiều implementation và giữ ranh giới giữa test logic ứng dụng với test giao tiếp hạ tầng.

## 22. Tài liệu tham khảo

- [Spring Framework Reference — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Framework Javadoc — `@MockitoBean`](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html)
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes)
