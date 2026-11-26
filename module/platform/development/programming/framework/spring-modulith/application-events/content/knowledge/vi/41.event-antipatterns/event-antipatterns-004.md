# Listener chứa quá nhiều trách nhiệm

Trong Spring Modulith, application event giúp module phát thông báo một sự kiện nghiệp vụ đã xảy ra và để module khác phản ứng thông qua listener. Listener là điểm tiếp nhận event, nhưng rất dễ trở thành nơi chứa toàn bộ logic: đọc và kiểm tra dữ liệu, áp dụng quy tắc nghiệp vụ, cập nhật nhiều aggregate, gọi REST API, gửi email, ghi audit, retry và xử lý lỗi.

Đây là anti-pattern **Listener chứa quá nhiều trách nhiệm**. Khi listener vừa làm nhiệm vụ tiếp nhận event vừa điều phối mọi chi tiết của use case, lớp này trở nên khó hiểu, khó kiểm thử và khó thay đổi. Cách tổ chức tốt hơn là để listener làm adapter mỏng: chuyển event thành lời gọi tới application service hoặc process manager có trách nhiệm rõ ràng. Quy tắc nghiệp vụ thuộc domain model/domain service; truy cập dữ liệu thuộc repository; tích hợp bên ngoài thuộc outbound port và adapter.

## 1. Vì sao listener dễ phình to?

Listener thường là nơi đầu tiên nhận thấy một luồng nghiệp vụ mới. Khi thêm yêu cầu, nhóm phát triển có thể tiếp tục nối logic vào method hiện tại vì mọi dữ liệu cần thiết đều có sẵn ở đó. Sau một thời gian, listener có thể vừa:

- Kiểm tra payload và tra cứu entity.
- Kiểm tra quyền hoặc điều kiện nghiệp vụ.
- Tính toán giá, phí, hạn mức hoặc trạng thái.
- Thay đổi nhiều aggregate hoặc bảng dữ liệu.
- Gọi dịch vụ thanh toán, vận chuyển hoặc HTTP API.
- Gửi email, notification và ghi audit.
- Quản lý retry, timeout, compensation và trạng thái quy trình.
- Ghi log, metric và xử lý mọi loại exception.

Một listener có nhiều dòng code chưa chắc đã sai. Vấn đề nằm ở việc nó sở hữu nhiều lý do thay đổi và nhiều chính sách độc lập. Khi quy tắc tính giá thay đổi, khi API đối tác đổi, hoặc khi chính sách retry đổi, cùng một listener đều phải sửa.

## 2. Ví dụ anti-pattern

Giả sử Orders phát `OrderPlaced`, và module Fulfillment nhận event để xác nhận địa chỉ, tính phí vận chuyển, tạo shipment, gửi email và ghi audit.

```java
@Component
class OrderPlacedListener {

    private final OrderRepository orders;
    private final AddressClient addressClient;
    private final ShippingClient shippingClient;
    private final EmailClient emailClient;
    private final AuditRepository audits;
    private final PricingService pricing;

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        var order = orders.findById(event.orderId()).orElseThrow();

        if (order.isCancelled()) {
            return;
        }

        var address = addressClient.verify(order.shippingAddress());
        var fee = pricing.calculateShipping(order, address);
        var shipment = shippingClient.create(order, fee);

        order.markShipmentCreated(shipment.id());
        orders.save(order);

        emailClient.sendShipmentCreated(order.customerEmail(), shipment);
        audits.save(AuditRecord.shipmentCreated(order.id(), shipment.id()));
    }
}
```

Đoạn code minh họa có nhiều vấn đề:

1. Listener tự điều phối toàn bộ use case và biết chi tiết của nhiều dependency.
2. Quy tắc chuyển trạng thái đơn hàng nằm lẫn với HTTP integration và gửi email.
3. Một lỗi email có thể làm listener thất bại dù shipment đã được tạo.
4. Retry toàn bộ method có thể tạo shipment lần thứ hai nếu lần trước đã thành công ở hệ thống ngoài.
5. Transaction của listener có thể kéo dài trong khi chờ nhiều network call.
6. Unit test phải mock quá nhiều collaborator để kiểm tra một hành vi đơn giản.
7. Thay đổi nhà cung cấp email hoặc vận chuyển buộc phải sửa lớp tiếp nhận event.

Listener đang trở thành một application service, domain service, integration adapter và workflow coordinator cùng lúc.

## 3. Nhận diện listener đang ôm quá nhiều trách nhiệm

Các dấu hiệu thường gặp:

| Dấu hiệu | Hệ quả |
|---|---|
| Constructor có nhiều client/repository không liên quan | Lớp phụ thuộc vào nhiều chính sách khác nhau |
| Method listener dài, có nhiều nhánh nghiệp vụ | Khó hiểu luồng chính và khó kiểm tra từng nhánh |
| Listener tự tạo transaction hoặc quản lý nhiều transaction | Ranh giới nhất quán dữ liệu khó xác định |
| Có nhiều `try/catch` cho từng dịch vụ ngoài | Retry và xử lý lỗi bị phân tán |
| Có logic tính toán domain trực tiếp | Quy tắc nghiệp vụ khó tái sử dụng và kiểm thử độc lập |
| Một listener xử lý nhiều event không cùng mục đích | Cohesion thấp, thay đổi một use case ảnh hưởng use case khác |
| Test cần dựng cả broker, email, HTTP server và database để kiểm tra quy tắc | Business logic bị dính vào infrastructure |
| Cùng một đoạn logic xuất hiện trong nhiều listener | Quy tắc bị phân tán và dễ lệch nhau |

Không dùng số dependency hoặc số dòng code làm tiêu chí duy nhất. Một listener có thể gọi hai service nhưng vẫn có cohesion tốt nếu chúng cùng thực hiện một phản ứng đơn giản. Ngược lại, listener ngắn nhưng gọi một facade khổng lồ có thể chỉ che giấu sự phức tạp.

## 4. Tách trách nhiệm theo vai trò

Một cấu trúc dễ duy trì thường phân chia như sau:

| Thành phần | Trách nhiệm |
|---|---|
| Event listener | Nhận event, trích xuất định danh và gọi use case phù hợp |
| Application service | Điều phối một use case trong module, xác định transaction boundary |
| Domain model/domain service | Bảo vệ invariant và thực hiện quy tắc nghiệp vụ |
| Repository | Đọc/ghi aggregate hoặc dữ liệu do module sở hữu |
| Outbound port | Khai báo nhu cầu gọi hệ thống bên ngoài bằng contract của module |
| Infrastructure adapter | Thực thi port bằng HTTP, broker, email hoặc SDK cụ thể |
| Process manager/Saga | Theo dõi quy trình nhiều bước, trạng thái chờ, timeout và compensation |
| Observability component | Ghi log, metric và trace theo convention chung |

Không cần tạo một class cho mỗi dòng code. Hãy tách khi một nhóm hành vi có lý do thay đổi riêng, có transaction/failure boundary riêng hoặc cần được kiểm thử độc lập.

## 5. Refactor thành listener mỏng

Listener sau refactor chỉ chuyển event thành lời gọi use case:

```java
@Component
class OrderPlacedListener {

    private final StartFulfillment startFulfillment;

    OrderPlacedListener(StartFulfillment startFulfillment) {
        this.startFulfillment = startFulfillment;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        startFulfillment.handle(event);
    }
}
```

Application service sở hữu luồng xử lý trong module Fulfillment:

```java
@Service
class StartFulfillment {

    private final OrderFulfillmentRepository fulfillments;
    private final ShippingAddressVerifier addressVerifier;
    private final ShippingQuoteProvider quoteProvider;
    private final ShipmentCreator shipmentCreator;

    StartFulfillment(
        OrderFulfillmentRepository fulfillments,
        ShippingAddressVerifier addressVerifier,
        ShippingQuoteProvider quoteProvider,
        ShipmentCreator shipmentCreator
    ) {
        this.fulfillments = fulfillments;
        this.addressVerifier = addressVerifier;
        this.quoteProvider = quoteProvider;
        this.shipmentCreator = shipmentCreator;
    }

    @Transactional
    public void handle(OrderPlaced event) {
        if (fulfillments.existsForOrder(event.orderId())) {
            return;
        }

        var address = addressVerifier.verify(event.shippingAddress());
        var quote = quoteProvider.quote(event.lines(), address);
        var fulfillment = Fulfillment.start(event, address, quote);

        fulfillments.save(fulfillment);
        shipmentCreator.request(fulfillment);
    }
}
```

Ví dụ cho thấy listener không biết cách kiểm tra địa chỉ hoặc tạo shipment. Tuy nhiên, `@Transactional` không nên bao trùm một network call kéo dài trong triển khai thực tế nếu việc đó giữ database connection/lock không cần thiết. Phần tiếp theo sẽ làm rõ cách đặt transaction và xử lý tích hợp ngoài.

Tên interface trong ví dụ là contract do module Fulfillment định nghĩa. Adapter HTTP hoặc SDK cụ thể triển khai các interface đó. Application service phụ thuộc vào port, không phụ thuộc trực tiếp vào vendor client.

## 6. Đặt quy tắc nghiệp vụ vào domain model

Application service điều phối use case, nhưng không nên biến nó thành nơi chứa toàn bộ quy tắc. Các invariant của Fulfillment nên được biểu diễn trong aggregate hoặc domain service.

Ví dụ:

```java
public class Fulfillment {

    private FulfillmentStatus status;
    private final UUID orderId;
    private ShipmentId shipmentId;

    public void markShipmentCreated(ShipmentId shipmentId) {
        if (status != FulfillmentStatus.READY_FOR_SHIPMENT) {
            throw new InvalidFulfillmentTransitionException(status);
        }

        this.shipmentId = shipmentId;
        this.status = FulfillmentStatus.SHIPMENT_CREATED;
    }
}
```

Domain model quyết định transition có hợp lệ hay không. Listener không nên tự kiểm tra rồi thay đổi nhiều field trực tiếp. Nếu event được giao lại, aggregate có thể từ chối transition lặp hoặc application service có thể nhận diện thao tác đã hoàn tất bằng idempotency key.

Không chuyển logic sang domain model chỉ để làm listener ngắn hơn. Quy tắc nào thuộc domain thì đặt ở domain; thao tác điều phối, gọi repository và phối hợp port thuộc application layer.

## 7. Không biến listener thành process manager

Một listener có thể cần khởi động quy trình nhiều bước. Nếu nó giữ trạng thái trong field, chờ callback, quản lý timeout, retry và compensation bằng các nhánh `if/else`, nó đang thực hiện vai trò process manager/Saga mà không có mô hình trạng thái rõ ràng.

Ví dụ quy trình fulfillment:

1. Xác minh địa chỉ.
2. Yêu cầu giữ tồn kho.
3. Chờ `InventoryReserved`.
4. Yêu cầu tạo shipment.
5. Chờ `ShipmentCreated`.
6. Thông báo kết quả.

Đây là quy trình có nhiều event, có thể kéo dài qua nhiều transaction. Nên lưu process state với trạng thái như `WAITING_FOR_INVENTORY`, `WAITING_FOR_SHIPMENT`, `COMPLETED` và `FAILED`. Mỗi listener nhận event chỉ gọi một transition/use case của process manager.

```java
@Component
class InventoryReservedListener {

    private final FulfillmentProcessManager processes;

    InventoryReservedListener(FulfillmentProcessManager processes) {
        this.processes = processes;
    }

    @ApplicationModuleListener
    void on(InventoryReserved event) {
        processes.onInventoryReserved(event);
    }
}
```

Process manager chịu trách nhiệm kiểm tra process ID, version, transition, timeout và command tiếp theo. Việc tách này giúp workflow có thể phục hồi sau restart và được kiểm thử bằng các event đầu vào/đầu ra rõ ràng.

## 8. Xử lý dịch vụ ngoài bằng outbound port

Listener chứa quá nhiều trách nhiệm thường gọi thẳng `RestClient`, `WebClient`, `JavaMailSender` hoặc SDK của nhà cung cấp. Điều đó khiến logic nghiệp vụ phụ thuộc vào chi tiết hạ tầng.

Định nghĩa port theo ngôn ngữ nghiệp vụ:

```java
public interface ShipmentCreator {
    ShipmentCreationResult request(CreateShipmentRequest request);
}
```

Adapter triển khai port bằng HTTP client:

```java
@Component
class HttpShipmentCreator implements ShipmentCreator {

    private final RestClient restClient;

    HttpShipmentCreator(RestClient.Builder builder) {
        this.restClient = builder.baseUrl("https://shipping.example")
            .build();
    }

    @Override
    public ShipmentCreationResult request(CreateShipmentRequest request) {
        return restClient.post()
            .uri("/shipments")
            .body(request)
            .retrieve()
            .body(ShipmentCreationResult.class);
    }
}
```

URL chỉ là ví dụ. Trong ứng dụng thực, base URL, authentication, timeout và retry policy lấy từ cấu hình an toàn. Adapter chuyển lỗi transport thành exception hoặc result theo contract đã định nghĩa; nó không tự quyết định trạng thái nghiệp vụ cuối cùng.

Port giúp unit test application service bằng fake, đồng thời cho phép thay adapter mà không đổi listener hoặc domain model.

## 9. Tránh giữ transaction trong lúc chờ network

Một transaction database nên ngắn và bảo vệ các thay đổi cần atomicity. Nếu listener mở transaction rồi gọi ba dịch vụ HTTP tuần tự, connection và lock có thể bị giữ trong thời gian chờ network.

Một cách tổ chức thường phù hợp:

1. Transaction ngắn tạo hoặc cập nhật process state thành `PENDING` và ghi command/outbox.
2. Dispatcher gửi command ra ngoài sau commit.
3. Khi nhận kết quả, listener gọi application service trong transaction riêng.
4. Service cập nhật state và ghi event tiếp theo/outbox cùng transaction.

Nếu nghiệp vụ yêu cầu gọi đồng bộ, vẫn cần giới hạn timeout và chỉ giữ transaction khi thực sự cần. Không đặt `@Transactional` ở listener một cách máy móc; xác định transaction boundary ở application service và persistence operation.

## 10. Không nuốt exception trong listener

Listener nhiều trách nhiệm thường có nhiều `try/catch`. Một anti-pattern phổ biến là log exception rồi kết thúc method bình thường:

```java
@ApplicationModuleListener
void on(OrderPlaced event) {
    try {
        startFulfillment.handle(event);
    } catch (Exception exception) {
        log.error("Fulfillment failed", exception);
    }
}
```

Khi method kết thúc bình thường, infrastructure có thể xem listener đã hoàn tất. Publication có thể được đánh dấu hoàn thành dù nghiệp vụ chưa được xử lý. Nếu lỗi cần retry, hãy để exception đi tới cơ chế quản lý publication hoặc chuyển sang trạng thái lỗi bền vững theo policy.

Có thể bắt exception để bổ sung ngữ cảnh rồi ném lại:

```java
@ApplicationModuleListener
void on(OrderPlaced event) {
    try {
        startFulfillment.handle(event);
    } catch (RetryableFulfillmentException exception) {
        log.warn(
            "Cannot start fulfillment: eventId={}, orderId={}",
            event.eventId(),
            event.orderId(),
            exception
        );
        throw exception;
    }
}
```

Không phải mọi exception đều nên retry. Lỗi nghiệp vụ như địa chỉ không được hỗ trợ nên được biểu diễn thành kết quả nghiệp vụ; lỗi tạm thời như network timeout có thể retry có giới hạn; lỗi payload/schema cần quarantine hoặc can thiệp. Phân loại này thuộc policy của use case/infrastructure, không nên bị rải khắp listener.

## 11. Idempotency là trách nhiệm của use case

Listener có thể được gọi lại do retry, restart hoặc publication recovery. Nếu listener gọi một application service không idempotent, side effect vẫn có thể bị lặp dù listener rất ngắn.

Application service nên nhận event ID hoặc command ID để bảo vệ tác động:

```java
@Transactional
public void handle(OrderPlaced event) {
    if (!inbox.insertIfAbsent("fulfillment-order-placed", event.eventId())) {
        return;
    }

    var fulfillment = Fulfillment.start(event);
    fulfillments.save(fulfillment);
}
```

`insertIfAbsent` phải dựa trên unique constraint và thao tác database nguyên tử. Inbox record và thay đổi nghiệp vụ cần commit cùng transaction. Nếu service gọi hệ thống ngoài, dùng idempotency key ổn định hoặc outbox/operation state; transaction database không thể rollback một request đã được hệ thống ngoài chấp nhận.

Listener không nên tự giữ một `Set<UUID>` trong memory để chống trùng vì trạng thái đó mất sau restart và không phối hợp giữa nhiều instance.

## 12. Tách notification và audit khỏi use case chính

Gửi email và ghi audit thường có failure policy khác với việc tạo fulfillment. Nếu email provider lỗi, có thể retry notification mà không cần tạo shipment lần nữa. Nếu audit là yêu cầu bắt buộc, độ bền vững và fail-open/fail-closed cần được xác định riêng.

Có thể phát event sau khi trạng thái nghiệp vụ đã commit:

```java
@Transactional
public void markShipmentCreated(UUID fulfillmentId, ShipmentId shipmentId) {
    var fulfillment = fulfillments.getRequired(fulfillmentId);
    fulfillment.markShipmentCreated(shipmentId);
    fulfillments.save(fulfillment);

    events.publishEvent(new ShipmentCreated(
        UUID.randomUUID(),
        fulfillment.orderId(),
        shipmentId.value(),
        clock.instant()
    ));
}
```

Notification module và Audit module có thể nghe `ShipmentCreated` theo contract riêng. Chúng tự quản lý retry, dedup và storage của mình. Nếu cần bảo đảm publication qua restart, cấu hình Event Publication Registry persistence hoặc outbox phù hợp; `publishEvent()` đơn thuần không phải broker và không tự bảo đảm delivery bền vững.

Không phát event phụ chỉ để chia method thành nhiều listener nếu các bước vẫn cần atomicity trong cùng một use case. Hãy xác định ranh giới nghiệp vụ và failure semantics trước khi tách.

## 13. Khi nào một listener có thể xử lý nhiều event?

Một class listener có thể có nhiều method nhận các event cùng một capability nếu chúng có chung mục đích và cùng lý do thay đổi. Ví dụ, `PaymentResultListener` nhận `PaymentAuthorized` và `PaymentDeclined`, rồi gọi hai use case tương ứng trong module Payments/Orders.

Nên tách class khi:

- Event thuộc các capability hoặc module khác nhau.
- Transaction/failure policy khác nhau.
- Một nhóm event cần executor, security hoặc observability riêng.
- Các method có nhiều dependency không liên quan.
- Thay đổi một event thường xuyên gây xung đột với nhóm event khác.

Không cần một listener class cho mỗi event theo quy tắc cứng. Hãy dùng cohesion và lý do thay đổi để quyết định. Một class có hai method ngắn, cùng một mục đích, có thể rõ ràng hơn hai class một method không có ranh giới trách nhiệm thực sự.

## 14. Transaction phase và `@ApplicationModuleListener`

Spring Modulith cung cấp `@ApplicationModuleListener` để biểu diễn listener ở ranh giới module. Annotation này được thiết kế cho xử lý bất đồng bộ và transaction riêng theo semantics của phiên bản Spring Modulith/Spring Framework tương ứng; trong các phiên bản phổ biến, nó kết hợp async execution, transactional event listener sau commit và propagation `REQUIRES_NEW`.

Điều này không có nghĩa mọi lỗi tự động được retry vô hạn. Cần cấu hình executor, transaction manager và Event Publication Registry persistence phù hợp với phiên bản đang dùng. Listener bất đồng bộ cũng không truyền exception về caller đã publish event như lời gọi đồng bộ.

Nếu dùng `@TransactionalEventListener`, chọn phase phù hợp như `AFTER_COMMIT` khi listener chỉ xử lý thay đổi đã commit. Nếu listener cần ghi dữ liệu, dùng transaction mới phù hợp. Tránh gắn nhiều annotation có semantics chồng lấn lên cùng method khi chưa hiểu cách chúng kết hợp.

## 15. Event Publication Registry không thay thế thiết kế trách nhiệm

Event Publication Registry theo dõi publication tới listener được Spring Modulith quản lý. Với persistence implementation phù hợp, registry lưu trạng thái publication và giúp phát hiện công việc chưa hoàn tất sau lỗi/restart.

Registry giúp phục hồi publication, nhưng không làm cho listener dễ bảo trì hơn. Nếu listener chứa nhiều side effect không idempotent, replay có thể tạo lỗi lặp. Nếu listener nuốt exception, registry có thể nhận thấy method hoàn tất bình thường dù use case thất bại.

Một listener mỏng kết hợp application service idempotent giúp recovery rõ ràng:

- Listener nhận event và chuyển tới use case.
- Use case bảo vệ invariant và transaction.
- Outbound side effect được tách qua port/outbox hoặc process manager.
- Exception cần retry được truyền tới infrastructure.
- Publication chỉ hoàn tất theo lifecycle thành công của listener.

Không cập nhật trực tiếp bảng registry để đánh dấu publication lỗi là hoàn tất. Dùng API recovery được hỗ trợ trong phiên bản Spring Modulith đang sử dụng.

## 16. Kiểm thử listener sau khi refactor

Tách trách nhiệm giúp kiểm thử từng tầng với phạm vi rõ ràng:

| Tầng test | Điều cần kiểm tra |
|---|---|
| Listener unit test | Event được chuyển tới đúng use case với đúng ID/dữ liệu |
| Application service test | Use case điều phối đúng thứ tự và xử lý kết quả |
| Domain test | Invariant và state transition đúng |
| Repository integration test | Persistence, unique constraint và transaction đúng |
| Adapter test | HTTP/email/broker mapping và error translation |
| Module integration test | Event được publish/nhận qua module boundary |
| Recovery test | Listener failure, publication retry và idempotency |

Listener unit test có thể rất nhỏ:

```java
@ExtendWith(MockitoExtension.class)
class OrderPlacedListenerTests {

    @Mock
    StartFulfillment startFulfillment;

    @InjectMocks
    OrderPlacedListener listener;

    @Test
    void delegatesEventToUseCase() {
        var event = TestEvents.orderPlaced();

        listener.on(event);

        verify(startFulfillment).handle(event);
    }
}
```

Test này xác minh listener chỉ đóng vai trò adapter. Nó không chứng minh transaction, publication registry hoặc broker behavior; những hành vi đó cần integration test riêng.

## 17. Kiểm thử transaction, duplicate và failure

Application service cần test các trường hợp:

- Event hợp lệ tạo đúng trạng thái fulfillment.
- Event duplicate không tạo shipment/reservation lần hai.
- Hai event khác ID nhưng cùng payload được xử lý theo business rule.
- Lỗi domain không để lại thay đổi một phần.
- Lỗi database rollback cả Inbox và business state.
- Lỗi hệ thống ngoài được phân loại và chuyển thành trạng thái/retry phù hợp.
- Event đến muộn không làm process quay về trạng thái cũ.
- Notification thất bại không khiến shipment được tạo lại.

Với async listener, dùng Spring Modulith `Scenario` hoặc Awaitility để chờ kết quả có timeout, không dùng `Thread.sleep()` cố định. Với concurrency/unique constraint, test trên database phù hợp thay vì chỉ mock repository.

## 18. Quan sát mà không nhồi logging vào listener

Observability cần nhất quán nhưng không nên khiến mọi listener tự xây logging framework riêng. Dùng convention hoặc component chung để ghi:

- Event ID, event type và correlation ID.
- Module/listener hoặc use case được gọi.
- Aggregate/process ID và version khi cần.
- Kết quả xử lý, duration và attempt nếu có.
- Exception type/root cause khi thất bại.

Metric hữu ích gồm processing duration, listener failure, publication incomplete, retry count, duplicate count và process backlog. Không dùng event ID/order ID làm metric label có cardinality cao; giữ định danh chi tiết trong log/trace.

Nếu cần bổ sung ngữ cảnh rồi ném lại exception, listener có thể ghi log một lần ở boundary phù hợp. Tránh mọi tầng đều log cùng stack trace gây nhiễu. Không log toàn bộ event payload nếu có dữ liệu nhạy cảm.

## 19. Quy trình refactor an toàn

Khi listener đã lớn, không nhất thiết phải viết lại toàn bộ luồng trong một lần. Có thể refactor từng bước:

1. Liệt kê trách nhiệm và side effect hiện tại của listener.
2. Xác định invariant, transaction boundary và failure policy của từng phần.
3. Viết characterization test cho hành vi hiện tại, gồm duplicate và lỗi quan trọng.
4. Trích xuất use case/application service với tên theo hành động nghiệp vụ.
5. Chuyển quy tắc invariant vào aggregate/domain service.
6. Đưa HTTP, email, broker và SDK ra outbound port/adapter.
7. Tách quy trình nhiều bước sang process manager/Saga nếu cần lưu trạng thái qua nhiều event.
8. Giữ listener chỉ làm nhiệm vụ nhận event và delegate.
9. Kiểm tra transaction, idempotency, retry và publication recovery sau mỗi bước.
10. Xóa logic cũ sau khi test xác nhận đường mới có cùng semantics.

Đừng tách class chỉ để giảm số dòng. Mỗi abstraction mới cần có tên thể hiện trách nhiệm và ranh giới kiểm thử hoặc thay đổi cụ thể.

## 20. Ví dụ cấu trúc package theo module

Một module Fulfillment có thể tổ chức:

```text
fulfillment/
├── api/
│   └── FulfillmentStatusView.java
├── events/
│   └── ShipmentCreated.java
├── application/
│   ├── StartFulfillment.java
│   ├── HandleInventoryResult.java
│   └── FulfillmentProcessManager.java
├── domain/
│   ├── Fulfillment.java
│   ├── FulfillmentStatus.java
│   └── FulfillmentPolicy.java
├── persistence/
│   └── JpaFulfillmentRepository.java
└── integration/
    ├── HttpShipmentCreator.java
    └── EmailNotificationAdapter.java
```

Đây là một cách tổ chức tham khảo, không phải cấu trúc bắt buộc của Spring Modulith. Điều quan trọng là package nội bộ được đóng gói, module khác chỉ sử dụng API/event contract được công bố và adapter hạ tầng không làm rò chi tiết ra domain.

## 21. Các cách sửa sai thường gặp

| Cách sửa | Vì sao chưa đủ |
|---|---|
| Chuyển toàn bộ code sang một `EventHandlerHelper` | Chỉ đổi tên lớp, trách nhiệm vẫn dồn vào một nơi |
| Tạo một service cho mỗi method | Tăng số lớp nhưng không tạo cohesion hoặc boundary có ý nghĩa |
| Bắt mọi exception rồi log | Có thể làm publication được đánh dấu hoàn tất nhầm |
| Dùng `@Async` để làm listener nhẹ | Chỉ thay execution thread, không tách trách nhiệm |
| Đưa mọi logic vào domain service | Có thể làm domain phụ thuộc infrastructure hoặc điều phối use case không phù hợp |
| Tách mỗi side effect thành event mới | Có thể tạo nhiều transaction và trạng thái trung gian không cần thiết |
| Giữ mọi thao tác trong một transaction | Kéo dài transaction và làm mờ failure boundary |
| Thêm retry mà không có idempotency | Side effect có thể lặp khi xử lý lại |

Refactor tốt cần làm rõ ai sở hữu quy tắc, ai điều phối use case, ai giao tiếp với hệ thống ngoài và cách phục hồi khi một bước thất bại.

## 22. Checklist thiết kế listener

- [ ] Listener có một mục đích rõ: tiếp nhận event và gọi use case phù hợp.
- [ ] Listener không chứa quy tắc domain hoặc cập nhật nhiều aggregate trực tiếp.
- [ ] Listener không phụ thuộc trực tiếp vào nhiều vendor client/SDK.
- [ ] Application service điều phối use case và xác định transaction boundary.
- [ ] Domain model bảo vệ invariant và state transition.
- [ ] Outbound integration được đặt sau port/adapter phù hợp.
- [ ] Workflow nhiều bước có process state/process manager khi cần.
- [ ] Transaction không bị giữ trong lúc chờ network không cần thiết.
- [ ] Consumer idempotent với duplicate delivery và retry.
- [ ] Exception cần retry không bị nuốt; lỗi nghiệp vụ có kết quả rõ.
- [ ] Notification/audit có failure policy độc lập với use case chính.
- [ ] Event Publication Registry/outbox được cấu hình theo yêu cầu durability.
- [ ] Có unit test cho listener/use case/domain và integration test cho transaction/recovery.
- [ ] Log, metric và trace có convention chung, không lặp hoặc lộ payload nhạy cảm.

Listener là cổng tiếp nhận application event, không phải nơi chứa mọi quy tắc và side effect của hệ thống. Trong Spring Modulith, giữ listener mỏng, chuyển điều phối sang application service, bảo vệ invariant trong domain model và tách tích hợp ngoài qua port/adapter giúp module dễ kiểm thử và thay đổi. Với quy trình nhiều bước, process manager cùng transaction boundary, idempotency và Event Publication Registry tạo nền tảng phục hồi rõ ràng mà không biến listener thành một khối xử lý khó kiểm soát.
