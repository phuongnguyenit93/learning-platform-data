# Xác nhận tác dụng phụ qua một cổng giao tiếp

Một ca kiểm thử đơn vị thường tập trung vào giá trị trả về hoặc trạng thái của đối tượng sau khi gọi một phương thức. Tuy nhiên, nhiều nghiệp vụ quan trọng còn tạo ra tác dụng phụ: ghi dữ liệu, trừ tồn kho, gửi yêu cầu thanh toán, phát thông điệp, gửi email hoặc ghi một tệp. Những kết quả này có thể xảy ra bên ngoài đối tượng đang được kiểm thử, nên chỉ kiểm tra giá trị trả về là chưa đủ.

Một cách tổ chức giúp kiểm thử các tác dụng phụ rõ ràng là đưa chúng qua **cổng giao tiếp (port)**. Trong kiến trúc hướng cổng và bộ chuyển đổi (Ports and Adapters, thường gọi là Hexagonal Architecture), ứng dụng định nghĩa các interface mô tả khả năng mà nghiệp vụ cần; adapter ở bên ngoài hiện thực các interface đó bằng database, HTTP client, message broker hoặc dịch vụ khác. Unit test thay adapter thật bằng mock hoặc fake để quan sát tác dụng phụ tại ranh giới của ứng dụng.

Trong ứng dụng Spring, Spring có thể inject adapter thật vào service khi chạy ứng dụng. Nhưng khi kiểm thử đơn vị, ta thường khởi tạo use case trực tiếp và truyền vào các port giả lập. Cách làm này giữ bài test nhanh, cô lập và tập trung vào quyết định nghiệp vụ. Các bài kiểm thử tích hợp riêng sẽ xác nhận adapter và cấu hình Spring hoạt động đúng với hạ tầng thực tế.

## 1. Tác dụng phụ là gì?

Tác dụng phụ là thay đổi hoặc tương tác có thể quan sát được bên ngoài giá trị trả về của một lời gọi. Ví dụ:

- Ghi một đơn hàng vào database.
- Gửi lệnh giữ tồn kho tới hệ thống kho.
- Gọi API của cổng thanh toán.
- Phát một event hoặc gửi message lên broker.
- Gửi email xác nhận hoặc thông báo đẩy.
- Ghi tệp, gọi dịch vụ lưu trữ hoặc cập nhật cache dùng chung.
- Ghi nhận một hành động kiểm toán (audit) cần được lưu lại.

Hãy phân biệt tác dụng phụ với kết quả tính toán thuần túy. Hàm tính tổng tiền có thể trả về một con số mà không thay đổi hệ thống bên ngoài. Hàm đặt hàng có thể trả về mã đơn hàng nhưng đồng thời phải lưu đơn, giữ tồn kho và yêu cầu thanh toán. Một test chỉ kiểm tra mã đơn hàng có thể bỏ sót việc hệ thống không gửi yêu cầu giữ tồn kho.

Không phải mọi lời gọi dependency đều là tác dụng phụ. Một truy vấn đọc dữ liệu cũng là tương tác qua ranh giới, nhưng mục tiêu kiểm thử có thể là kết quả trả về thay vì xác nhận số lần gọi. Hãy xác định điều gì là hợp đồng quan trọng của nghiệp vụ trước khi chọn assertion.

## 2. Cổng giao tiếp trong kiến trúc ứng dụng

Port là một interface mô tả khả năng mà ứng dụng cần hoặc cung cấp. Với kiểm thử tác dụng phụ, ta thường quan tâm đến **outbound port**: cổng mà use case gọi để tương tác với thế giới bên ngoài.

Ví dụ, use case đặt hàng có thể phụ thuộc vào các port sau:

```java
public interface OrderRepository {
    void save(Order order);
}

public interface PaymentPort {
    PaymentResult charge(PaymentRequest request);
}

public interface InventoryPort {
    ReservationResult reserve(ReservationRequest request);
}

public interface OrderNotificationPort {
    void sendConfirmation(OrderConfirmation confirmation);
}
```

Các interface này thuộc về lớp ứng dụng hoặc miền nghiệp vụ, nơi định nghĩa nhu cầu. Adapter hiện thực chúng:

| Port | Adapter có thể sử dụng |
| --- | --- |
| `OrderRepository` | Spring Data JPA repository và adapter chuyển đổi entity |
| `PaymentPort` | HTTP client gọi cổng thanh toán |
| `InventoryPort` | REST client hoặc message producer gọi hệ thống kho |
| `OrderNotificationPort` | SMTP client, dịch vụ email hoặc notification gateway |

Use case chỉ cần biết hợp đồng của port. Nó không cần biết adapter dùng `RestClient`, `WebClient`, JDBC, JPA, Kafka hay một SDK cụ thể. Vì vậy, trong unit test có thể thay thế adapter thật bằng mock hoặc fake mà không cần dựng database hay kết nối mạng.

### Inbound port và outbound port

Inbound port mô tả cách một actor bên ngoài yêu cầu ứng dụng thực hiện nghiệp vụ, ví dụ `PlaceOrderUseCase`. Controller Spring MVC hoặc message listener có thể đóng vai trò adapter gọi inbound port. Outbound port mô tả khả năng ứng dụng cần từ hệ thống ngoài, ví dụ lưu đơn hàng hoặc tính phí vận chuyển.

```text
HTTP request
    |
    v
Controller adapter
    |
    v
PlaceOrderUseCase (inbound port)
    |
    v
PlaceOrderService
    |          |             |
    v          v             v
OrderStore  PaymentPort  InventoryPort (outbound ports)
    |          |             |
    v          v             v
Database   Payment API   Warehouse API
```

Sơ đồ thể hiện hướng phụ thuộc: logic ứng dụng gọi các interface mà nó sở hữu; adapter bên ngoài hiện thực các interface đó. Điều này làm ranh giới kiểm thử dễ nhận biết và tránh để unit test phụ thuộc trực tiếp vào công nghệ hạ tầng.

## 3. Xác định hợp đồng tác dụng phụ trước khi viết test

Không nên bắt đầu bằng câu hỏi “cần verify mock nào?”. Hãy bắt đầu từ yêu cầu nghiệp vụ: trong điều kiện nào, hệ thống phải tạo ra thay đổi bên ngoài nào, với dữ liệu gì, bao nhiêu lần và vào thời điểm nào?

Ví dụ nghiệp vụ đặt hàng có thể có các kỳ vọng:

| Điều kiện | Tác dụng phụ cần xác nhận |
| --- | --- |
| Đơn hợp lệ và thanh toán thành công | Gửi yêu cầu thanh toán với số tiền đúng; lưu đơn ở trạng thái đã thanh toán; yêu cầu giữ tồn kho |
| Thanh toán bị từ chối | Không lưu đơn như đã thanh toán; không gửi email xác nhận; xử lý giữ tồn kho theo quy tắc đã chọn |
| Giỏ hàng rỗng | Không gọi cổng thanh toán, không lưu đơn |
| Hệ thống kho từ chối giữ hàng | Không tiếp tục thu tiền nếu quy trình yêu cầu giữ hàng trước; trả lỗi nghiệp vụ phù hợp |
| Yêu cầu được gửi lặp với cùng khóa idempotency | Không tạo hai giao dịch thanh toán hoặc hai đơn hàng |

Kỳ vọng phải dựa trên hợp đồng thật của nghiệp vụ. Thứ tự giữ hàng và thanh toán có thể khác nhau giữa các hệ thống. Nếu thanh toán được thực hiện trước rồi mới giữ hàng, thiết kế cần có quy trình hoàn tiền hoặc bù trừ khi giữ hàng thất bại. Test nên xác nhận chính sách đã chọn, không áp đặt thứ tự tùy ý.

Một tác dụng phụ cần được mô tả đủ cụ thể. Chẳng hạn “gửi email” có thể chưa đủ nếu hợp đồng yêu cầu email gửi đến địa chỉ của khách hàng, có mã đơn chính xác và chỉ gửi sau khi đơn được tạo thành công.

## 4. Ví dụ use case phụ thuộc vào các port

Giả sử ứng dụng có use case tạo đơn. Các port được truyền vào constructor để thể hiện rõ dependency:

```java
public interface OrderRepository {
    void save(Order order);
}

public interface PaymentPort {
    PaymentResult charge(PaymentRequest request);
}

public interface OrderNotificationPort {
    void sendConfirmation(OrderConfirmation confirmation);
}
```

Service ứng dụng sử dụng các port:

```java
public class PlaceOrderService {

    private final OrderRepository orders;
    private final PaymentPort payments;
    private final OrderNotificationPort notifications;

    public PlaceOrderService(
            OrderRepository orders,
            PaymentPort payments,
            OrderNotificationPort notifications) {
        this.orders = orders;
        this.payments = payments;
        this.notifications = notifications;
    }

    public OrderId place(PlaceOrderCommand command) {
        Order order = Order.create(command.customerId(), command.items());

        PaymentResult payment = payments.charge(
            new PaymentRequest(order.id(), order.total(), command.paymentToken())
        );

        if (!payment.approved()) {
            throw new PaymentDeclinedException(order.id());
        }

        order.markPaid(payment.reference());
        orders.save(order);
        notifications.sendConfirmation(
            new OrderConfirmation(order.id(), command.customerEmail())
        );

        return order.id();
    }
}
```

Đây là ví dụ minh họa; các kiểu `Order`, `PaymentRequest` và `PaymentResult` đại diện cho model của ứng dụng. Điểm quan trọng là service chỉ gọi các interface. Nó không trực tiếp tạo HTTP client, repository implementation hay email sender.

Trong Spring, adapter thật có thể được đăng ký thành bean:

```java
@Component
class HttpPaymentAdapter implements PaymentPort {
    // Dùng HTTP client để gọi cổng thanh toán
}

@Repository
class JpaOrderRepositoryAdapter implements OrderRepository {
    // Chuyển đổi và lưu entity bằng Spring Data JPA
}
```

Constructor injection cho phép Spring cung cấp adapter ở runtime và cho phép unit test truyền mock hoặc fake khi kiểm thử logic ứng dụng.

## 5. Kiểm tra lời gọi qua port bằng Mockito

Mockito cho phép xác nhận một port đã được gọi với tham số mong đợi. Dùng `verify()` để kiểm tra tương tác có ý nghĩa với hợp đồng.

```java
@ExtendWith(MockitoExtension.class)
class PlaceOrderServiceTest {

    @Mock
    OrderRepository orders;

    @Mock
    PaymentPort payments;

    @Mock
    OrderNotificationPort notifications;

    @InjectMocks
    PlaceOrderService service;

    @Test
    void savesOrderAndSendsConfirmationWhenPaymentIsApproved() {
        when(payments.charge(any(PaymentRequest.class)))
            .thenReturn(PaymentResult.approved("payment-123"));

        PlaceOrderCommand command = validCommand();

        OrderId orderId = service.place(command);

        verify(payments).charge(argThat(request ->
            request.amount().equals(command.expectedTotal())
                && request.paymentToken().equals(command.paymentToken())
        ));
        verify(orders).save(argThat(order ->
            order.id().equals(orderId) && order.isPaid()
        ));
        verify(notifications).sendConfirmation(argThat(message ->
            message.orderId().equals(orderId)
                && message.email().equals(command.customerEmail())
        ));
    }
}
```

Trong ví dụ, test xác nhận ba tác dụng phụ: yêu cầu thanh toán đúng số tiền và token, lưu đơn đã thanh toán, gửi xác nhận tới đúng địa chỉ. Assertion tập trung vào dữ liệu có ý nghĩa nghiệp vụ thay vì chỉ kiểm tra rằng các mock được gọi.

`@InjectMocks` tiện lợi khi Mockito có thể khởi tạo đối tượng với các mock tương ứng. Nếu constructor hoặc cách khởi tạo phức tạp, tạo service trực tiếp trong `@BeforeEach` thường dễ đọc hơn vì thể hiện rõ dependency nào được truyền vào.

## 6. Xác nhận tác dụng phụ không được xảy ra

Nhiều lỗi quan trọng liên quan đến một hành động đáng lẽ không được thực hiện. Mockito có `never()` để xác nhận một port không được gọi:

```java
@Test
void doesNotSaveOrderOrSendConfirmationWhenPaymentIsDeclined() {
    when(payments.charge(any(PaymentRequest.class)))
        .thenReturn(PaymentResult.declined("insufficient-funds"));

    assertThrows(
        PaymentDeclinedException.class,
        () -> service.place(validCommand())
    );

    verify(payments).charge(any(PaymentRequest.class));
    verify(orders, never()).save(any(Order.class));
    verify(notifications, never())
        .sendConfirmation(any(OrderConfirmation.class));
}
```

Test này xác nhận khi thanh toán bị từ chối, service có gọi cổng thanh toán nhưng không lưu đơn như thành công và không gửi email xác nhận. Đây là bằng chứng quan trọng vì chỉ kiểm tra exception không chứng minh rằng những side effect sau lỗi đã không xảy ra.

Một số trường hợp khác cần xác nhận không gọi port:

- Không gửi email khi dữ liệu đầu vào không hợp lệ.
- Không gọi cổng thanh toán khi giỏ hàng rỗng.
- Không phát event thành công khi lưu dữ liệu thất bại.
- Không gọi dịch vụ ngoài khi quyền truy cập bị từ chối.
- Không gửi message lần hai khi khóa idempotency đã được xử lý.

Chỉ dùng `never()` cho những tương tác bị cấm bởi hợp đồng. Không cần xác nhận mọi dependency khác đều không được gọi nếu điều đó không liên quan đến quy tắc đang kiểm tra.

## 7. Kiểm tra dữ liệu được gửi qua port

Tác dụng phụ thường quan trọng cả ở việc có gọi hay không lẫn nội dung được truyền đi. Nếu tham số là object phức tạp, `ArgumentCaptor` giúp lấy giá trị thực tế để kiểm tra nhiều trường.

```java
@Captor
ArgumentCaptor<OrderConfirmation> confirmationCaptor;

@Test
void sendsConfirmationContainingTheCreatedOrderId() {
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    OrderId orderId = service.place(validCommand());

    verify(notifications).sendConfirmation(confirmationCaptor.capture());

    OrderConfirmation sent = confirmationCaptor.getValue();
    assertEquals(orderId, sent.orderId());
    assertEquals("customer@example.test", sent.email());
}
```

`ArgumentCaptor` đặc biệt hữu ích khi cần kiểm tra payload gửi qua message broker, command gửi tới hệ thống ngoài hoặc event chứa snapshot dữ liệu tại thời điểm phát. Với điều kiện đơn giản, `argThat()` hoặc `eq()` có thể ngắn gọn hơn.

Không nên so sánh toàn bộ object nếu nhiều trường không liên quan tới hành vi. Hãy kiểm tra các trường nằm trong hợp đồng của port. Nếu một trường được thêm vào model nhưng không ảnh hưởng nghiệp vụ, test không nên thất bại chỉ vì trường đó thay đổi.

## 8. Xác nhận số lần gọi và tính idempotent

Số lần một side effect được thực hiện có thể là một phần của hợp đồng. Mockito hỗ trợ `times(n)`, `atLeastOnce()` và `never()`.

```java
verify(payments, times(1)).charge(any(PaymentRequest.class));
verify(orders, times(1)).save(any(Order.class));
verify(notifications, never()).sendConfirmation(any());
```

Ví dụ, nếu một command bị gửi lại với cùng idempotency key, hệ thống có thể phải trả lại kết quả cũ mà không tạo giao dịch thanh toán mới. Test có thể gọi use case hai lần và xác nhận chỉ có một lần gọi cổng thanh toán, tùy theo thiết kế nơi lưu idempotency key.

```java
@Test
void doesNotChargeTwiceWhenSameIdempotencyKeyIsSubmittedAgain() {
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    PlaceOrderCommand command = commandWithKey("request-abc");

    service.place(command);
    service.place(command);

    verify(payments, times(1)).charge(any(PaymentRequest.class));
}
```

Đoạn mã chỉ minh họa mục tiêu. Để bảo đảm idempotency thực sự qua nhiều instance hoặc sau restart, việc lưu khóa và kết quả thường cần được kiểm thử tích hợp với storage dùng chung. Một unit test với mock không chứng minh được tính duy nhất trong database phân tán.

Đừng mặc định mọi port chỉ được gọi đúng một lần. Retry có thể là hành vi hợp lệ đối với một số lỗi tạm thời. Khi kiểm tra số lần gọi, hãy căn cứ vào chính sách retry, idempotency và loại side effect. Một lần gửi email hoặc trừ tiền lặp có thể nguy hiểm; một lần đọc lại cấu hình có thể không quan trọng.

## 9. Kiểm tra thứ tự tương tác khi thứ tự là quy tắc nghiệp vụ

Một số side effect phải xảy ra theo thứ tự nhất định. Mockito `InOrder` giúp xác nhận thứ tự giữa các port:

```java
@Test
void reservesInventoryBeforeChargingPayment() {
    when(inventory.reserve(any()))
        .thenReturn(ReservationResult.reserved("reservation-7"));
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    service.place(validCommand());

    InOrder order = inOrder(inventory, payments, orders);
    order.verify(inventory).reserve(any(ReservationRequest.class));
    order.verify(payments).charge(any(PaymentRequest.class));
    order.verify(orders).save(any(Order.class));
}
```

Chỉ dùng cách kiểm tra này khi thứ tự là một phần của yêu cầu, ví dụ phải giữ tồn kho thành công trước khi thu tiền. Nếu thứ tự gọi không ảnh hưởng hợp đồng, xác nhận thứ tự sẽ làm test dễ vỡ khi refactor mà không tăng độ tin cậy.

Khi quy trình có nhiều bước và bù trừ, hãy kiểm tra cả nhánh thất bại. Ví dụ, nếu thanh toán bị từ chối sau khi giữ tồn kho, hệ thống phải hủy reservation:

```java
@Test
void releasesInventoryWhenPaymentIsDeclined() {
    when(inventory.reserve(any()))
        .thenReturn(ReservationResult.reserved("reservation-7"));
    when(payments.charge(any()))
        .thenReturn(PaymentResult.declined("insufficient-funds"));

    assertThrows(PaymentDeclinedException.class,
        () -> service.place(validCommand()));

    verify(inventory).reserve(any(ReservationRequest.class));
    verify(inventory).release("reservation-7");
    verify(orders, never()).save(any(Order.class));
}
```

Đây là ví dụ cho một nghiệp vụ có compensation. Nếu ứng dụng dùng saga hoặc workflow bất đồng bộ, quy tắc bù trừ có thể được thực hiện bởi một thành phần khác; khi đó hãy kiểm thử đúng cổng hoặc event phát ra để yêu cầu bù trừ được chuyển giao.

## 10. Dùng fake khi muốn kiểm tra trạng thái thay vì lời gọi

Mock phù hợp khi cần điều khiển phản hồi hoặc xác nhận tương tác. Fake phù hợp khi muốn một implementation đơn giản có trạng thái để kiểm tra kết quả mà không phụ thuộc hạ tầng thật.

Ví dụ fake repository trong bộ nhớ:

```java
class InMemoryOrderRepository implements OrderRepository {

    private final Map<OrderId, Order> stored = new HashMap<>();

    @Override
    public void save(Order order) {
        stored.put(order.id(), order.copy());
    }

    Optional<Order> findById(OrderId id) {
        return Optional.ofNullable(stored.get(id));
    }
}
```

Test có thể thực hiện use case rồi đọc lại dữ liệu từ fake:

```java
@Test
void storesPaidOrderAfterPaymentIsApproved() {
    InMemoryOrderRepository repository = new InMemoryOrderRepository();
    PaymentPort payment = request -> PaymentResult.approved("payment-123");
    OrderNotificationPort notifications = confirmation -> { };

    PlaceOrderService service = new PlaceOrderService(
        repository, payment, notifications
    );

    OrderId id = service.place(validCommand());

    Order stored = repository.findById(id).orElseThrow();
    assertTrue(stored.isPaid());
}
```

Fake cho phép kiểm tra trạng thái lưu trữ một cách tự nhiên. Tuy nhiên, fake chỉ mô phỏng một phần hợp đồng của adapter thật. Nó không chứng minh JPA mapping, transaction, constraint, serialization hoặc kết nối database đúng. Những hành vi đó cần integration test với adapter thật.

Một fake tốt nên đơn giản, dễ hiểu và đủ đúng với hợp đồng mà unit test sử dụng. Không nên biến fake thành một database tự xây dựng có đầy đủ query engine, locking và transaction. Khi fake trở nên phức tạp, cân nhắc dùng Testcontainers hoặc một adapter test riêng.

## 11. Khi nào nên dùng mock, fake hoặc spy?

| Cách thay thế | Dùng khi | Điểm cần chú ý |
| --- | --- | --- |
| Mock | Cần điều khiển kết quả trả về hoặc xác nhận side effect qua port | Tránh verify các lời gọi nội bộ không thuộc hợp đồng |
| Fake | Cần mô phỏng trạng thái đơn giản và kiểm tra kết quả qua hành vi | Phải giữ fake nhất quán với hợp đồng của adapter thật |
| Stub | Chỉ cần cung cấp phản hồi cố định cho dependency | Không dùng stub để khẳng định side effect đã xảy ra |
| Spy | Cần quan sát một đối tượng thật hoặc giữ phần lớn hành vi thật | Có thể làm test phụ thuộc implementation; dùng thận trọng |

Trong unit test của use case, mock outbound port thường là lựa chọn trực tiếp để xác nhận lệnh gửi ra ngoài. Với repository hoặc read port, fake có thể làm test dễ đọc hơn nếu cần kiểm tra state. Không có quy tắc rằng mọi dependency phải cùng dùng một kiểu double.

## 12. Tách kiểm tra quyết định nghiệp vụ khỏi kiểm tra adapter

Một lỗi thiết kế thường gặp là viết unit test để kiểm tra chi tiết HTTP request, SQL hoặc cấu hình broker trong khi mục tiêu thực sự là quy tắc nghiệp vụ. Hãy phân chia trách nhiệm:

- Unit test use case: xác nhận khi nào port được gọi, với dữ liệu nào, bao nhiêu lần và khi nào không được gọi.
- Adapter test: xác nhận adapter chuyển đổi dữ liệu và giao tiếp đúng với công nghệ ngoài.
- Integration test: xác nhận Spring wiring, transaction, serialization và kết nối giữa adapter với hạ tầng.

Ví dụ, `PaymentPort` có thể được hiện thực bằng `RestClient`. Unit test `PlaceOrderService` chỉ cần xác nhận nó gửi một `PaymentRequest` với order ID và amount đúng. Một test riêng cho `HttpPaymentAdapter` kiểm tra URL, HTTP method, header, JSON body, response mapping và xử lý lỗi. Không nên bắt unit test service biết tên endpoint hoặc cấu trúc JSON riêng của nhà cung cấp.

Tương tự, unit test có thể xác nhận `OrderRepository.save(order)` được gọi. `@DataJpaTest` hoặc integration test khác sẽ xác nhận entity được map và lưu đúng trên database. Hai lớp kiểm thử cung cấp bằng chứng khác nhau và bổ sung cho nhau.

## 13. Tác dụng phụ và transaction trong Spring

Trong ứng dụng Spring, `@Transactional` thường được áp dụng qua proxy. Unit test khởi tạo service bằng `new` không tự kích hoạt transaction do Spring quản lý. Vì thế, test đơn vị có thể xác nhận quyết định gọi port và xử lý lỗi, nhưng không thể chứng minh transaction thực sự commit hoặc rollback.

Ví dụ:

```java
@Service
class PlaceOrderService {

    @Transactional
    public OrderId place(PlaceOrderCommand command) {
        // Gọi các port và cập nhật trạng thái đơn hàng
    }
}
```

Một unit test gọi trực tiếp `new PlaceOrderService(...).place(command)` không đi qua Spring proxy. Đó vẫn là test hợp lệ cho logic của phương thức, nhưng không phải bằng chứng về transaction manager.

Để kiểm tra transaction, hãy có integration test chạy qua bean do Spring quản lý và xác nhận dữ liệu từ transaction độc lập. Với nghiệp vụ phát message sau commit, có thể dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` hoặc transactional outbox tùy kiến trúc. Unit test nên kiểm tra quyết định phát event hoặc ghi outbox; integration test kiểm tra event chỉ được gửi theo thời điểm commit mong muốn.

Không nên dùng `verify(eventPublisher).publish(...)` như bằng chứng rằng broker đã nhận message hoặc transaction đã commit. Nó chỉ chứng minh code gọi port publisher. Việc giao message thành công, retry, xác nhận ack và bảo đảm không mất message thuộc adapter và integration test.

## 14. Side effect qua Spring ApplicationEvent và message port

Spring có `ApplicationEventPublisher` để phát event trong cùng ứng dụng. Nếu nghiệp vụ cần phát thông tin ra hệ thống ngoài, một outbound port riêng thường làm ranh giới rõ hơn. Ví dụ `OrderEventPort` có thể được adapter hiện thực bằng Kafka hoặc RabbitMQ.

```java
public interface OrderEventPort {
    void publish(OrderPlaced event);
}
```

Unit test có thể xác nhận event được tạo đúng:

```java
@Test
void publishesOrderPlacedEventWhenOrderIsAccepted() {
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    service.place(validCommand());

    verify(orderEvents).publish(argThat(event ->
        event.orderId() != null
            && event.customerId().equals("customer-42")
    ));
}
```

Test trên xác nhận use case phát event có dữ liệu cần thiết. Nó chưa kiểm tra serialization, topic, routing key, partition, broker availability hay delivery guarantee. Những điều đó thuộc adapter và integration test.

Nếu event phải chỉ được phát sau commit, thiết kế port nên phản ánh rõ semantics. Một lựa chọn là ghi outbox record trong cùng transaction; một worker khác gửi record sang broker. Unit test kiểm tra outbox port nhận event; integration test xác nhận ghi outbox và cập nhật dữ liệu nghiệp vụ trong cùng transaction. Cách này tránh giả định rằng gọi một publisher đồng nghĩa message đã được broker lưu bền vững.

## 15. Tránh kiểm tra tương tác quá mức

Interaction test rất hữu ích với side effect, nhưng nếu xác nhận mọi lời gọi nội bộ, test sẽ trở nên mong manh. Một refactor có thể đổi thứ tự gọi helper hoặc gộp hai lời gọi mà không thay đổi hành vi bên ngoài. Khi đó test thất bại dù nghiệp vụ vẫn đúng.

Nên kiểm tra:

- Port nào phải được gọi hoặc không được gọi theo điều kiện nghiệp vụ.
- Dữ liệu quan trọng được truyền qua port.
- Số lần gọi khi số lần là một phần của hợp đồng, ví dụ idempotency hoặc tránh gửi email lặp.
- Thứ tự khi thứ tự có ý nghĩa nghiệp vụ hoặc là điều kiện an toàn.
- Side effect bù trừ khi một quy trình nhiều bước thất bại.

Thường không cần kiểm tra:

- Mọi lời gọi getter hoặc helper nội bộ.
- Một phương thức private đã được gọi bao nhiêu lần.
- Thứ tự giữa các port khi hợp đồng không yêu cầu.
- Toàn bộ trường của object nếu chỉ một số trường liên quan tới side effect.
- `verifyNoMoreInteractions()` trên tất cả mock chỉ để buộc test khớp tuyệt đối với implementation.

Một nguyên tắc hữu ích là kiểm tra ranh giới có ý nghĩa đối với ứng dụng hoặc hệ thống ngoài. Nếu một lời gọi chỉ là chi tiết tổ chức code bên trong service, hãy ưu tiên assertion trên kết quả nghiệp vụ.

## 16. Thiết kế port để test side effect dễ dàng

Port nên mô tả ý định nghiệp vụ thay vì phơi bày API của thư viện hạ tầng. So sánh:

```java
// Port gắn với công nghệ cụ thể
public interface KafkaTemplatePort {
    void send(String topic, String key, byte[] payload);
}

// Port mô tả ý định ứng dụng
public interface OrderEventPort {
    void publishOrderPlaced(OrderPlaced event);
}
```

Port thứ hai cho phép use case diễn đạt nhu cầu mà không phải biết topic, key hay cách serialize. Adapter Kafka chịu trách nhiệm ánh xạ `OrderPlaced` sang cấu trúc message.

Một port tốt thường có các đặc điểm:

- Có tên thể hiện khả năng hoặc mục đích nghiệp vụ.
- Chỉ chứa các thao tác mà ứng dụng thực sự cần.
- Dùng kiểu dữ liệu ổn định thuộc lớp ứng dụng hoặc domain.
- Có quy tắc lỗi rõ ràng: trả kết quả, ném exception hay biểu diễn trạng thái từ chối.
- Không làm rò rỉ kiểu của framework hoặc SDK nhà cung cấp nếu không cần thiết.
- Đủ nhỏ để một adapter hiện thực rõ ràng và một unit test xác nhận dễ dàng.

Không cần tạo interface cho mọi class. Port có giá trị khi nó đánh dấu một ranh giới thay đổi, một dependency bên ngoài hoặc một khả năng cần thay thế trong kiểm thử. Tạo interface chỉ để bọc một helper thuần túy không có side effect có thể làm kiến trúc phức tạp mà không thêm lợi ích.

## 17. Kiểm thử lỗi và retry ở cổng giao tiếp

Port thường là nơi lỗi hạ tầng đi vào ứng dụng. Unit test cần kiểm tra cách use case phản ứng với các kết quả mà port có thể trả về hoặc exception mà adapter có thể ném.

Ví dụ, với cổng thanh toán:

| Kết quả port | Hành vi ứng dụng cần xác định |
| --- | --- |
| Approved | Đánh dấu thanh toán thành công và tiếp tục luồng |
| Declined | Từ chối nghiệp vụ, không tạo xác nhận thành công |
| Timeout | Có thể không biết giao dịch đã xảy ra hay chưa; cần tra cứu hoặc idempotency |
| Service unavailable | Có thể retry theo chính sách và giới hạn |
| Invalid response | Ghi nhận lỗi tích hợp và xử lý an toàn |

Test có thể cấu hình mock trả về từng kết quả để kiểm tra các nhánh. Đặc biệt với timeout, không nên giả định rằng request chắc chắn chưa được xử lý. Nếu hệ thống thanh toán đã nhận yêu cầu nhưng response bị mất, retry không có idempotency key có thể thu tiền hai lần. Hợp đồng port và test nên phản ánh trạng thái không chắc chắn này.

Nếu retry nằm trong adapter HTTP, unit test use case không cần kiểm tra số lần HTTP request. Hãy kiểm tra retry policy trong adapter test riêng. Nếu retry là chính sách nghiệp vụ do use case điều khiển, test use case có thể xác nhận số lần gọi port và điều kiện dừng.

## 18. Đồng hồ, ID và các dependency tạo tác dụng phụ khó xác định

Không chỉ database hay HTTP mới là dependency. Việc đọc giờ hệ thống, sinh ID ngẫu nhiên hoặc đọc biến môi trường cũng có thể khiến kết quả khó lặp lại. Có thể đưa các khả năng này qua port hoặc abstraction nhỏ.

Ví dụ dùng `Clock` của Java:

```java
public class ExpirationService {

    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(Instant.now(clock));
    }
}
```

Test truyền clock cố định:

```java
@Test
void considersTokenExpiredWhenExpiryEqualsCurrentTime() {
    Instant now = Instant.parse("2026-01-10T10:00:00Z");
    Clock fixedClock = Clock.fixed(now, ZoneOffset.UTC);
    ExpirationService service = new ExpirationService(fixedClock);

    assertTrue(service.isExpired(now));
}
```

Ở đây `Clock` không phải outbound port tới dịch vụ ngoài, nhưng nó minh họa cùng nguyên tắc: đưa dependency có thể làm thay đổi kết quả vào constructor để test kiểm soát được. Với ID generator, có thể inject `OrderIdGenerator` để kiểm tra use case truyền đúng ID qua các port hoặc tạo dữ liệu xác định.

## 19. Kiểm thử adapter bằng Spring

Sau khi unit test xác nhận use case gọi port đúng, cần kiểm tra adapter thật ở mức phù hợp. Một số ví dụ:

| Adapter | Kiểm thử phù hợp | Điều cần xác nhận |
| --- | --- | --- |
| JPA repository adapter | `@DataJpaTest` hoặc integration test | Mapping, query, constraint, lưu và đọc dữ liệu |
| HTTP payment adapter | Mock server hoặc `@RestClientTest` | URL, method, header, body, response mapping và timeout |
| Message producer | Broker test với Testcontainers hoặc broker test double phù hợp | Topic, key, serialization, ack và lỗi gửi |
| Email adapter | Adapter test với SMTP sandbox hoặc fake server | Người nhận, nội dung, encoding và lỗi gửi |
| File storage adapter | Test với filesystem tạm hoặc storage emulator | Đường dẫn, nội dung, quyền và xử lý lỗi |

Sau đó, một integration test ở cấp ứng dụng có thể xác nhận Spring inject đúng adapter vào service. Unit test không cần khởi tạo `ApplicationContext` chỉ để truyền mock vào constructor. Ngược lại, integration test cần lấy bean từ Spring để kiểm tra cấu hình, proxy và wiring.

## 20. Một ví dụ hoàn chỉnh về bộ test cho use case

Với use case đặt hàng, có thể tổ chức các trường hợp theo tác dụng phụ:

| Trường hợp | Kết quả nghiệp vụ | Port được gọi |
| --- | --- | --- |
| Thanh toán thành công | Trả về mã đơn | Payment, repository, notification |
| Thanh toán bị từ chối | Ném lỗi từ chối | Payment; không lưu đơn, không gửi xác nhận |
| Dữ liệu đầu vào không hợp lệ | Ném lỗi validation nghiệp vụ | Không gọi port bên ngoài |
| Lưu đơn thất bại sau thanh toán | Trả lỗi hoặc kích hoạt quy trình bù trừ theo thiết kế | Payment và repository; có thể có refund/compensation port |
| Yêu cầu lặp cùng idempotency key | Trả lại kết quả đã có | Đọc idempotency store; không tạo side effect trùng |

Một số test mẫu:

```java
@Test
void doesNotCallExternalPortsWhenCommandIsInvalid() {
    PlaceOrderCommand invalid = commandWithNoItems();

    assertThrows(InvalidOrderException.class,
        () -> service.place(invalid));

    verifyNoInteractions(payments, notifications);
    verify(orders, never()).save(any());
}

@Test
void sendsConfirmationOnlyAfterPaymentIsApproved() {
    when(payments.charge(any()))
        .thenReturn(PaymentResult.approved("payment-123"));

    service.place(validCommand());

    verify(payments).charge(any(PaymentRequest.class));
    verify(notifications).sendConfirmation(any(OrderConfirmation.class));
}
```

`verifyNoInteractions()` thích hợp trong test đầu nếu hợp đồng nói rõ command không hợp lệ phải bị từ chối trước mọi tương tác với các port đó. Trong những test khác, hãy dùng `never()` cho các side effect cụ thể thay vì khóa chặt toàn bộ tương tác không liên quan.

## 21. Những sai lầm thường gặp

- **Kiểm tra giá trị trả về nhưng bỏ qua side effect:** use case có thể trả về mã đơn dù không lưu dữ liệu hoặc không gửi yêu cầu bắt buộc.
- **Mock adapter cụ thể thay vì mock port:** test bị gắn với thư viện HTTP, JPA hoặc broker, khiến logic ứng dụng khó kiểm tra độc lập.
- **Verify mọi lời gọi:** test thất bại khi refactor chi tiết nội bộ dù hợp đồng bên ngoài không đổi.
- **Không kiểm tra tham số:** port được gọi nhưng nhận sai số tiền, ID, người nhận hoặc payload.
- **Không kiểm tra trường hợp không được gọi:** lỗi nghiệp vụ có thể vẫn kích hoạt thanh toán, email hoặc message.
- **Nhầm lời gọi publisher với message đã được gửi:** verify port không chứng minh broker đã nhận và lưu message.
- **Nhầm unit test với kiểm thử transaction:** gọi service trực tiếp không kích hoạt Spring proxy và không chứng minh commit/rollback.
- **Dùng fake không phản ánh hợp đồng:** test xanh với fake nhưng adapter thật có hành vi khác.
- **Kiểm tra số lần gọi không đúng chính sách retry:** một retry hợp lệ bị coi là lỗi, hoặc một side effect không idempotent bị lặp mà test không phát hiện.
- **Đặt quá nhiều trách nhiệm vào một test:** một test vừa kiểm tra thanh toán, lưu đơn, email, transaction và serialization sẽ khó xác định nguyên nhân khi thất bại.

## 22. Quy trình thiết kế test tác dụng phụ qua port

Khi kiểm thử một use case có tương tác bên ngoài, có thể làm theo các bước sau:

1. **Xác định ranh giới:** liệt kê database, API, broker, email, cache hoặc hệ thống ngoài mà use case cần gọi.
2. **Định nghĩa port:** tạo interface mô tả ý định ứng dụng và dữ liệu cần trao đổi.
3. **Viết điều kiện nghiệp vụ:** xác định khi nào side effect phải xảy ra, bị cấm, được retry hoặc cần bù trừ.
4. **Chọn test double:** dùng mock để điều khiển phản hồi và xác nhận tương tác; dùng fake khi cần kiểm tra trạng thái đơn giản.
5. **Kiểm tra nội dung:** xác nhận các trường quan trọng của request, event hoặc command được gửi qua port.
6. **Kiểm tra nhánh thất bại:** xác nhận side effect không mong muốn không xảy ra và compensation được kích hoạt khi cần.
7. **Giữ test ở đúng tầng:** unit test kiểm tra quyết định của use case; adapter test và integration test kiểm tra giao tiếp thật, Spring wiring và transaction.

Một unit test có giá trị khi nó chứng minh được quyết định của ứng dụng tại ranh giới: trong điều kiện đã cho, ứng dụng gửi đúng lệnh, với dữ liệu đúng, đúng số lần và không tạo tác dụng phụ bị cấm. Port làm cho ranh giới đó rõ ràng, còn mock và fake cung cấp cách kiểm chứng nhanh mà không cần khởi động toàn bộ hạ tầng.
