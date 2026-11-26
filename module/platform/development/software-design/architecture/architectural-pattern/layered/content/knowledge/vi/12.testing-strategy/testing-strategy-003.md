# Kiểm thử application service về điều phối, kết quả và tác động

Application service (dịch vụ ứng dụng) thực hiện một ca sử dụng bằng cách phối hợp các thành phần cần thiết: tải dữ liệu qua repository, gọi hành vi của Domain, sử dụng các cổng tích hợp và lưu kết quả. Kiểm thử application service cần xác minh rằng luồng công việc được điều phối đúng, kết quả phản ánh đúng ca sử dụng và các tác động chỉ xảy ra khi điều kiện phù hợp.

Trong kiến trúc phân tầng, Presentation chịu trách nhiệm chuyển request thành input của use case; Application điều phối; Domain bảo vệ quy tắc nghiệp vụ; Infrastructure triển khai repository, cổng tích hợp và lưu trữ. Vì vậy, unit test cho application service thường chạy trực tiếp service với các dependency giả, không cần khởi động toàn bộ Spring hay kết nối database.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, chiến lược này giúp kiểm tra đúng trách nhiệm của tầng ứng dụng: phối hợp các bước và bảo đảm kết quả của use case. Các quy tắc nội tại của Domain và hành vi kỹ thuật của adapter cần có những kiểm thử riêng ở ranh giới tương ứng.

## 1. Application service cần được kiểm thử điều gì?

Một application service thường không phải nơi chứa mọi quy tắc nghiệp vụ. Vai trò của nó là điều phối một luồng công việc. Khi kiểm thử, hãy tập trung vào những điều caller và các thành phần cộng tác có thể quan sát:

- **Đầu vào được sử dụng đúng:** command/query được chuyển đến đúng repository hoặc port với định danh và tham số cần thiết.
- **Các bước được phối hợp đúng:** use case tải dữ liệu cần thiết, gọi hành vi Domain và thực hiện các bước tiếp theo theo điều kiện.
- **Kết quả đúng:** trả đúng mã tài nguyên, trạng thái, dữ liệu đầu ra hoặc lỗi ứng dụng.
- **Tác động đúng:** lưu thay đổi, ghi outbox, gọi cổng thanh toán hoặc phát yêu cầu tích hợp khi nghiệp vụ cho phép.
- **Không có tác động khi không được phép:** dữ liệu không tồn tại hoặc quy tắc nghiệp vụ thất bại thì không được lưu hay phát sự kiện thành công.
- **Lỗi được truyền hoặc chuyển đổi đúng:** lỗi từ repository/port được xử lý theo hợp đồng của use case.

Không nên biến unit test thành bản sao của code production. Test cần kiểm tra hành vi có ý nghĩa đối với use case, không cần xác nhận từng dòng code hay từng lời gọi nội bộ không ảnh hưởng đến kết quả.

## 2. Phân biệt phạm vi unit test và các loại kiểm thử khác

Mỗi tầng có trách nhiệm khác nhau, nên kiểm thử cũng có phạm vi khác nhau:

| Phạm vi | Cần xác minh | Cách kiểm thử thường dùng |
|---|---|---|
| Application service | Điều phối, kết quả, lỗi và lời gọi các port | Unit test với fake/mock |
| Domain | Bất biến, chuyển trạng thái và quy tắc nghiệp vụ | Unit test trực tiếp domain object |
| Infrastructure adapter | SQL/JPQL, mapping, transaction, giao tiếp API | Integration test với database hoặc hệ thống giả lập phù hợp |
| Presentation | HTTP mapping, validation, status code và response DTO | Spring MVC test |
| Toàn luồng | Các tầng kết nối đúng trong một kịch bản quan trọng | Integration hoặc end-to-end test |

Một unit test tạo mới ConfirmOrderService rồi gọi phương thức trực tiếp không chạy qua Spring proxy. Vì vậy, annotation @Transactional trên service không tự tạo transaction trong test đó. Unit test có thể kiểm tra service yêu cầu các thao tác đúng; transaction thực tế cần được xác minh bằng integration test với cấu hình Spring và database.

## 3. Chuẩn bị test theo cấu trúc Arrange – Act – Assert

Một test rõ ràng thường có ba phần:

1. **Arrange:** tạo command, dữ liệu ban đầu và cấu hình kết quả của repository hoặc port.
2. **Act:** gọi đúng phương thức use case một lần.
3. **Assert:** kiểm tra kết quả, trạng thái liên quan và các tác động quan trọng.

Ví dụ, use case xác nhận đơn hàng cần tải đơn, yêu cầu Domain chuyển trạng thái, lưu đơn và ghi sự kiện vào outbox:

~~~mermaid
sequenceDiagram
    participant T as Application Test
    participant S as ConfirmOrderService
    participant R as OrderRepository
    participant D as Order Domain
    participant O as Event Outbox
    T->>S: confirm(command)
    S->>R: findById(orderId)
    R-->>S: Order
    S->>D: confirm()
    D-->>S: Order đã xác nhận
    S->>R: save(order)
    S->>O: append(OrderConfirmed)
    S-->>T: ConfirmOrderResult
    T->>T: Assert result và side effects
~~~

Sơ đồ mô tả hành vi mong đợi ở cấp use case. Test không cần kiểm tra mọi lời gọi method nội bộ của Order; trạng thái sau khi thực hiện và các tác động qua port mới là điều cần xác minh.

## 4. Ví dụ application service cần kiểm thử

Giả sử đơn hàng chỉ được xác nhận khi tồn tại và đang ở trạng thái phù hợp. Application service điều phối như sau:

~~~java
public record ConfirmOrderCommand(UUID orderId) {}

public record ConfirmOrderResult(
        UUID orderId,
        OrderStatus status
) {}

public interface OrderRepository {
    Optional<Order> findById(UUID orderId);
    void save(Order order);
}

public interface OrderEventOutbox {
    void append(OrderConfirmedEvent event);
}

public class ConfirmOrderService {
    private final OrderRepository orders;
    private final OrderEventOutbox outbox;

    public ConfirmOrderService(
            OrderRepository orders,
            OrderEventOutbox outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public ConfirmOrderResult handle(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() ->
                        new OrderNotFoundException(command.orderId()));

        order.confirm();

        orders.save(order);
        outbox.append(new OrderConfirmedEvent(order.getId()));

        return new ConfirmOrderResult(
                order.getId(),
                order.getStatus()
        );
    }
}
~~~

Trong ví dụ này:

- Repository cung cấp aggregate Order.
- Domain method confirm() quyết định trạng thái hiện tại có cho phép xác nhận hay không.
- Application service điều phối lưu aggregate và ghi event vào outbox.
- Kết quả use case trả lại ID và trạng thái đơn đã xác nhận.

Outbox được dùng để lưu ý định phát sự kiện trong cùng transaction database với thay đổi đơn hàng. Một worker riêng sẽ gửi event ra broker sau khi transaction commit. Nếu ứng dụng dùng một event publisher ngoài database trực tiếp, việc publish không tự động nằm trong transaction JPA; cần thiết kế xử lý lỗi và tính lũy đẳng phù hợp.

## 5. Kiểm thử luồng thành công: kết quả và tác động

Với JUnit 5 và Mockito, có thể thay repository và outbox bằng mock. Test xác minh kết quả trả về, đơn hàng được lưu với trạng thái đúng và event được ghi với đúng ID:

~~~java
@ExtendWith(MockitoExtension.class)
class ConfirmOrderServiceTest {

    @Mock
    OrderRepository orders;

    @Mock
    OrderEventOutbox outbox;

    ConfirmOrderService service;

    @BeforeEach
    void setUp() {
        service = new ConfirmOrderService(orders, outbox);
    }

    @Test
    void confirmsOrderAndRecordsEvent() {
        UUID orderId = UUID.randomUUID();
        Order order = Order.pending(orderId);

        when(orders.findById(orderId))
                .thenReturn(Optional.of(order));

        ConfirmOrderResult result = service.handle(
                new ConfirmOrderCommand(orderId)
        );

        assertEquals(orderId, result.orderId());
        assertEquals(OrderStatus.CONFIRMED, result.status());

        ArgumentCaptor<Order> savedOrder =
                ArgumentCaptor.forClass(Order.class);
        verify(orders).save(savedOrder.capture());
        assertEquals(
                OrderStatus.CONFIRMED,
                savedOrder.getValue().getStatus()
        );

        ArgumentCaptor<OrderConfirmedEvent> event =
                ArgumentCaptor.forClass(OrderConfirmedEvent.class);
        verify(outbox).append(event.capture());
        assertEquals(orderId, event.getValue().orderId());
    }
}
~~~

Order.pending, OrderStatus và event là các kiểu minh họa. Test cần khởi tạo trạng thái hợp lệ theo API Domain thực tế.

Test trên kiểm tra những tác động quan trọng: lưu aggregate và ghi sự kiện. Nó không cần xác minh findById phải được gọi trước save bằng InOrder nếu thứ tự đó đã được phản ánh qua kết quả và các quy tắc. Chỉ kiểm tra thứ tự lời gọi khi thứ tự là một phần thực sự của hợp đồng, chẳng hạn phải kiểm tra quyền trước khi thực hiện một side effect.

## 6. Kiểm thử các nhánh lỗi và bảo đảm không có tác động sai

Một test thành công chưa đủ. Cần kiểm tra các nhánh làm use case dừng trước khi thay đổi dữ liệu.

### Không tìm thấy đơn hàng

~~~java
@Test
void doesNotSaveOrPublishWhenOrderDoesNotExist() {
    UUID orderId = UUID.randomUUID();
    when(orders.findById(orderId)).thenReturn(Optional.empty());

    assertThrows(
            OrderNotFoundException.class,
            () -> service.handle(new ConfirmOrderCommand(orderId))
    );

    verify(orders, never()).save(any());
    verifyNoInteractions(outbox);
}
~~~

Test xác minh khi dữ liệu không tồn tại, service trả đúng lỗi và không tạo tác động. Không nên chỉ assert exception rồi bỏ qua việc kiểm tra save hoặc publish có bị gọi nhầm hay không.

### Domain từ chối chuyển trạng thái

Nếu đơn đã bị hủy, Domain có thể ném OrderStateConflictException khi gọi confirm(). Test cần xác minh lỗi được truyền lên và không có thay đổi được lưu hoặc event xác nhận được ghi:

~~~java
@Test
void doesNotPersistOrEmitConfirmationForCancelledOrder() {
    UUID orderId = UUID.randomUUID();
    Order order = Order.cancelled(orderId);

    when(orders.findById(orderId)).thenReturn(Optional.of(order));

    assertThrows(
            OrderStateConflictException.class,
            () -> service.handle(new ConfirmOrderCommand(orderId))
    );

    verify(orders, never()).save(any());
    verifyNoInteractions(outbox);
}
~~~

Điều kiện chuyển trạng thái là quy tắc của Domain. Unit test Domain nên kiểm tra riêng mọi trạng thái hợp lệ và không hợp lệ; application test ở đây chỉ cần xác minh service phối hợp đúng khi Domain từ chối.

### Lỗi khi lưu

Nếu orders.save ném lỗi, service không nên tiếp tục ghi event thành công. Có thể kiểm tra:

~~~java
@Test
void doesNotAppendEventWhenSavingFails() {
    UUID orderId = UUID.randomUUID();
    Order order = Order.pending(orderId);

    when(orders.findById(orderId)).thenReturn(Optional.of(order));
    doThrow(new DataAccessException("database unavailable") {})
            .when(orders).save(order);

    assertThrows(
            DataAccessException.class,
            () -> service.handle(new ConfirmOrderCommand(orderId))
    );

    verifyNoInteractions(outbox);
}
~~~

Test này kiểm tra luồng điều phối trong trường hợp lưu thất bại. Nó không chứng minh transaction rollback dữ liệu đã ghi trước đó; điều đó phải được kiểm tra ở integration test.

## 7. Kiểm tra tham số và dữ liệu truyền qua port

Ngoài việc xác minh một port có được gọi, cần kiểm tra nó nhận đúng dữ liệu khi dữ liệu đó ảnh hưởng tới nghiệp vụ. Ví dụ, khi Application gọi cổng gửi thông báo, người nhận và mã đơn phải chính xác; khi gọi repository, ID phải lấy từ command đã xác thực.

ArgumentCaptor giúp kiểm tra object được truyền qua ranh giới:

~~~java
ArgumentCaptor<OrderConfirmedEvent> eventCaptor =
        ArgumentCaptor.forClass(OrderConfirmedEvent.class);

verify(outbox).append(eventCaptor.capture());

OrderConfirmedEvent event = eventCaptor.getValue();
assertEquals(expectedOrderId, event.orderId());
~~~

Không nên capture và assert mọi field nếu chúng không thuộc hợp đồng của use case. Tập trung vào dữ liệu có ý nghĩa: resource ID, tenant, amount, currency, correlation ID hoặc thông tin ảnh hưởng đến tác động bên ngoài.

Với collection lớn, có thể xác minh tập hợp ID hoặc số phần tử thay vì phụ thuộc thứ tự nội bộ nếu thứ tự không được cam kết. Nếu thứ tự là một phần của hợp đồng, hãy kiểm tra rõ điều đó.

## 8. Chọn mock, stub hay fake phù hợp

Có nhiều cách thay dependency thật trong unit test:

| Cách thay thế | Mô tả | Khi phù hợp |
|---|---|---|
| Stub | Trả về dữ liệu đã định trước | Khi chỉ cần cung cấp đầu vào cho use case |
| Mock | Ghi nhận lời gọi và cho phép verify | Khi cần kiểm tra một tương tác quan trọng qua port |
| Fake | Implementation đơn giản nhưng chạy được, ví dụ repository lưu trong Map | Khi muốn kiểm thử nhiều hành vi với trạng thái có thể thay đổi |
| Spy | Bao quanh object thật và quan sát một phần lời gọi | Chỉ dùng khi có lý do cụ thể; thường dễ làm test phụ thuộc implementation |

Ví dụ fake repository:

~~~java
class InMemoryOrderRepository implements OrderRepository {
    private final Map<UUID, Order> data = new HashMap<>();

    @Override
    public Optional<Order> findById(UUID id) {
        return Optional.ofNullable(data.get(id));
    }

    @Override
    public void save(Order order) {
        data.put(order.getId(), order);
    }
}
~~~

Fake hữu ích khi kiểm thử một nhóm use case cần trạng thái dữ liệu đơn giản. Tuy nhiên, fake không chứng minh SQL, transaction hay mapping JPA đúng. Các đặc tính đó cần integration test cho adapter.

Không có yêu cầu phải mock mọi dependency. Nếu một object thuần Java, bất biến và rẻ để tạo, hãy dùng object thật. Mock quá nhiều khiến test khó đọc và phải cập nhật mỗi khi cấu trúc nội bộ thay đổi.

## 9. Kiểm tra side effect theo hợp đồng

Side effect là tác động vượt ra ngoài việc trả một giá trị cục bộ, chẳng hạn:

- Lưu hoặc cập nhật aggregate.
- Ghi outbox hoặc phát domain/application event.
- Gọi cổng thanh toán, vận chuyển hoặc gửi email.
- Cập nhật cache hoặc chỉ mục tìm kiếm.
- Tạo tác vụ nền hoặc gửi command sang một hệ thống khác.

Application test cần xác minh side effect nào được yêu cầu khi use case thành công và side effect nào không được phép khi use case thất bại. Tuy nhiên, cần xác định đúng ranh giới:

- Nếu use case ghi event vào outbox cùng transaction, application test có thể verify outbox.append.
- Nếu worker gửi event ra broker, đó là trách nhiệm của worker/adapter và cần test riêng.
- Nếu một cổng thanh toán thực hiện charge, unit test chỉ có thể xác minh port được gọi với key và số tiền đúng; test adapter hoặc contract test cần xác minh request thực gửi tới provider.
- Nếu email được gửi bất đồng bộ từ event, không nên bắt application unit test khởi chạy SMTP server chỉ để kiểm tra việc gửi mail.

Đặc biệt, không nên kiểm tra một side effect bên ngoài bằng cách verify mock rồi kết luận transaction database và provider được commit nguyên tử. Hai hệ thống không tự chia sẻ một transaction thông thường. Hãy test riêng outbox, consumer và cơ chế lũy đẳng hoặc bù trừ.

## 10. Kiểm thử transaction và rollback ở đúng cấp

Annotation @Transactional là hành vi do Spring proxy và transaction manager thực hiện. Unit test gọi trực tiếp service không chạy qua proxy; do đó nó không xác minh:

- Transaction có bắt đầu đúng lúc không.
- Các repository có dùng cùng transaction không.
- Exception nào làm rollback hoặc được cấu hình không rollback.
- Thay đổi database có được rollback khi outbox insert thất bại không.
- Lock hoặc optimistic version có hoạt động đúng không.

Để xác minh, dùng integration test khởi động phần Spring cần thiết và database kiểm thử tương thích. Ví dụ, thực hiện use case, khiến bước ghi outbox thất bại, sau đó truy vấn database trong transaction mới để xác minh đơn hàng không bị commit.

Có thể dùng Testcontainers để chạy database gần với môi trường production. H2 có thể phù hợp cho một số test nhanh, nhưng khác biệt SQL, locking, isolation và kiểu dữ liệu có thể khiến test không phát hiện lỗi chỉ xuất hiện trên database thực tế.

Cũng cần chú ý @Transactional trên test method có thể tự rollback khi test kết thúc và che khuất một số hành vi commit thực tế. Nếu cần xác minh dữ liệu sau commit, hãy thiết kế test với transaction boundary rõ ràng và đọc lại bằng transaction độc lập.

## 11. Tránh các test mong manh và kiểm tra implementation detail

Một số dấu hiệu test đang kiểm tra quá sâu:

- Verify mọi getter, setter hoặc method nội bộ của Domain.
- Kiểm tra chính xác số lần gọi một helper không thuộc hợp đồng.
- Mock cả object dữ liệu đơn giản thay vì tạo object thật.
- Assert thứ tự mọi lời gọi dù thứ tự không ảnh hưởng đến hành vi.
- Kiểm tra tên biến, cấu trúc private method hoặc cách chia lớp.
- Dùng verifyNoMoreInteractions trên mọi mock, khiến một logging hoặc metric mới làm test hỏng dù hành vi use case không đổi.

Hãy verify những tương tác có ý nghĩa nghiệp vụ hoặc bảo vệ side effect. Ví dụ, “không lưu đơn khi không tìm thấy” là một bảo đảm quan trọng. “Phương thức mapStatus được gọi đúng một lần” thường chỉ là chi tiết implementation.

Ngược lại, không nên né tránh kiểm tra tương tác khi đó chính là hành vi cần xác minh. Nếu use case phải gọi PaymentPort.authorize với cùng idempotency key, hoặc phải ghi outbox sau khi tạo đơn, kiểm tra port và tham số là hợp lý.

## 12. Tổ chức test suite theo hành vi của use case

Một bảng tình huống giúp tránh chỉ kiểm tra happy path:

| Tình huống | Kết quả cần kiểm tra | Tác động cần kiểm tra |
|---|---|---|
| Dữ liệu hợp lệ, use case thành công | Trả đúng ID/trạng thái | Lưu dữ liệu và ghi event đúng |
| Không tìm thấy tài nguyên | Trả lỗi not found | Không lưu, không phát event |
| Domain từ chối hành động | Trả lỗi nghiệp vụ | Không lưu thay đổi và không ghi event thành công |
| Port tích hợp từ chối | Trả kết quả/lỗi theo hợp đồng | Không thực hiện bước tiếp theo trái phép |
| Repository thất bại | Lỗi được truyền hoặc chuyển đổi đúng | Không gọi các tác động sau bước thất bại |
| Request trùng hoặc idempotency replay | Trả lại kết quả đã hoàn tất | Không tạo thêm tài nguyên hoặc side effect |
| Cập nhật đồng thời | Kết quả xung đột hoặc retry đúng chính sách | Không ghi đè sai trạng thái |

Không nhất thiết phải tạo một test cho mọi tổ hợp dữ liệu. Hãy chọn các nhánh quyết định quan trọng, các lỗi có khả năng xảy ra và các side effect có rủi ro cao. Dùng parameterized test khi nhiều dữ liệu đầu vào cần kiểm tra cùng một quy tắc.

## 13. Một cấu trúc thư mục test dễ theo dõi

Có thể tổ chức test theo use case và tầng:

~~~text
src
├── main
│   └── java/com/example/shop
│       ├── application
│       │   └── order/ConfirmOrderService.java
│       ├── domain
│       │   └── order/Order.java
│       └── infrastructure
│           └── persistence/JpaOrderRepositoryAdapter.java
└── test
    └── java/com/example/shop
        ├── application/order
        │   └── ConfirmOrderServiceTest.java
        ├── domain/order
        │   └── OrderTest.java
        └── infrastructure/persistence
            └── JpaOrderRepositoryAdapterTest.java
~~~

Tên test nên mô tả hành vi hoặc điều kiện, ví dụ doesNotSaveWhenOrderIsMissing hoặc recordsEventAfterSuccessfulConfirmation. Tên như test1, testService không giúp người đọc hiểu bảo đảm nào đang được kiểm tra.

Không cần ép mọi dự án theo đúng cấu trúc này. Điều quan trọng là người phát triển dễ tìm test của use case, Domain và adapter tương ứng.

## 14. Checklist kiểm thử Application service

Trước khi hoàn thành test cho một use case, hãy kiểm tra:

1. Test có gọi application service qua public API của nó không?
2. Có kiểm tra kết quả trả về hoặc lỗi theo hợp đồng không?
3. Các dependency được stub/fake/mock đúng ở ranh giới cần thiết không?
4. Có xác minh side effect quan trọng và dữ liệu truyền qua port không?
5. Có xác minh không phát sinh side effect khi use case thất bại không?
6. Domain rule có được test riêng ở Domain không?
7. Transaction, SQL và mapping có được test ở integration boundary không?
8. Test có tránh phụ thuộc vào private method và thứ tự gọi không cần thiết không?
9. Tên test có mô tả hành vi và tình huống rõ ràng không?

Kiểm thử application service tốt chứng minh rằng một ca sử dụng được điều phối đúng: dữ liệu được lấy từ đúng nguồn, quy tắc được giao cho Domain, kết quả được trả theo hợp đồng và tác động xảy ra đúng điều kiện. Khi mỗi tầng được kiểm tra ở ranh giới phù hợp, test suite vừa phát hiện lỗi thực tế vừa giúp kiến trúc phân tầng dễ thay đổi.

