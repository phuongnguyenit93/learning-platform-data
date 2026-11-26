# Đảm bảo atomic write

## Vì sao cần atomic write khi phát application event?

Một nghiệp vụ thường phải thay đổi dữ liệu và thông báo cho phần còn lại của hệ thống. Ví dụ, khi đơn hàng được xác nhận, module Orders lưu trạng thái đơn hàng rồi phát OrderConfirmed để module Fulfillment chuẩn bị giao hàng và module Notification gửi thông báo.

Nếu hai thao tác này được thực hiện độc lập, hệ thống gặp bài toán **dual write**: ghi dữ liệu nghiệp vụ vào database và gửi sự kiện ra một nơi lưu trữ hoặc broker khác. Hai thao tác có thể thành công hoặc thất bại riêng rẽ.

| Tình huống | Hậu quả |
|---|---|
| Ghi đơn hàng thành công, gửi event thất bại | Dữ liệu đã đổi nhưng module nhận không biết |
| Gửi event thành công, transaction lưu đơn hàng rollback | Module nhận xử lý một nghiệp vụ chưa từng được commit |
| Ứng dụng dừng giữa hai thao tác | Kết quả phụ thuộc thao tác nào đã hoàn tất |
| Listener lỗi sau khi transaction nghiệp vụ commit | Nghiệp vụ đã được lưu nhưng công việc tiếp theo chưa hoàn tất |

Atomic write giải quyết phần ghi bằng cách đặt thay đổi nghiệp vụ và **bản ghi đại diện cho việc cần phát event** trong cùng một transaction. Database chỉ commit cả hai cùng nhau hoặc rollback cả hai cùng nhau.

Trong Spring Modulith, Event Publication Registry cung cấp cơ chế theo dõi publication dành cho transactional event listener. Khi event được phát trong transaction nghiệp vụ, registry ghi nhận publication cho từng listener tương ứng. Với persistent registry được cấu hình đúng, bản ghi publication tham gia cùng transaction với dữ liệu nghiệp vụ. Đây là nền tảng để ứng dụng khôi phục các publication chưa hoàn tất sau lỗi hoặc khởi động lại.

## Phân biệt atomic write với việc listener chạy sau commit

Hai khái niệm này liên quan nhưng đảm nhiệm hai việc khác nhau:

- **Atomic write** bảo đảm dữ liệu nghiệp vụ và bản ghi publication được commit hoặc rollback cùng nhau.
- **After commit** xác định thời điểm listener bắt đầu xử lý: chỉ sau khi transaction phát event đã commit thành công.
- **Persistent publication registry** lưu trạng thái publication đủ lâu để ứng dụng nhận biết và xử lý lại publication còn dang dở.
- **Retry và idempotency** giúp xử lý lỗi trong lúc listener thực thi mà không tạo tác động nghiệp vụ trùng lặp.

Chỉ dùng @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT) không tự tạo ra một hàng đợi bền vững. Annotation này điều khiển thời điểm gọi listener. Nếu tiến trình dừng sau commit nhưng trước khi listener hoàn tất, một listener không có cơ chế lưu publication bền vững có thể không được gọi lại. Registry bền vững bổ sung phần ghi nhận và phục hồi đó.

## Luồng ghi nguyên tử với Spring Modulith

Giả sử module Orders cập nhật đơn hàng và phát OrderConfirmed. Module Fulfillment đăng ký listener để tạo yêu cầu giao hàng.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as Orders module
    participant DB as Database
    participant Registry as Event Publication Registry
    participant Fulfillment as Fulfillment listener

    Client->>Orders: confirmOrder()
    Orders->>DB: BEGIN transaction
    Orders->>DB: UPDATE orders
    Orders->>Registry: publish OrderConfirmed
    Registry->>DB: INSERT publication record
    Orders->>DB: COMMIT
    Note over DB,Registry: Dữ liệu nghiệp vụ và publication cùng commit
    Orders-->>Fulfillment: Giao event sau commit
    Fulfillment->>Fulfillment: Xử lý event trong transaction listener
    Fulfillment-->>Registry: Báo xử lý thành công
    Registry->>DB: Đánh dấu publication hoàn tất
~~~

Điểm quan trọng nằm ở ranh giới transaction:

1. Transaction nghiệp vụ bắt đầu.
2. Module Orders lưu thay đổi của đơn hàng.
3. Module Orders phát application event.
4. Registry ghi publication tương ứng với transactional listener.
5. Transaction commit. Dữ liệu đơn hàng và publication record cùng trở nên bền vững.
6. Listener được gọi theo cấu hình của nó, thường là sau commit. Với @ApplicationModuleListener, Spring Modulith hỗ trợ cách xử lý bất đồng bộ và transaction riêng cho listener.
7. Khi listener xử lý thành công, registry cập nhật publication thành hoàn tất theo cơ chế lưu trữ đang dùng.

Nếu transaction ở bước 5 rollback, cả thay đổi đơn hàng và publication record đều rollback. Listener không được xử lý một event đại diện cho thay đổi chưa commit.

## Viết publisher trong transaction nghiệp vụ

Publisher nên phát event ngay trong transaction chứa thay đổi nghiệp vụ. Event mô tả một sự kiện đã xảy ra hoặc một sự thật nghiệp vụ vừa được ghi nhận; nó không nên buộc module phát event phải biết listener nào sẽ nhận.

Ví dụ:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

~~~java
@Service
@RequiredArgsConstructor
public class OrderConfirmationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher events;

    @Transactional
    public void confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();

        // Event được phát trong cùng transaction với thay đổi đơn hàng.
        events.publishEvent(
            new OrderConfirmed(UUID.randomUUID(), order.getId(), Instant.now())
        );
    }
}
~~~

Ở ví dụ này, @Transactional tạo ranh giới transaction cho thao tác xác nhận. Khi event được phát, Spring Modulith có thể ghi publication cho các transactional listener đã đăng ký. Điều kiện quan trọng là publisher và persistent registry phải tham gia cùng transaction manager và cùng tài nguyên transaction phù hợp.

Không nên chuyển việc phát event sang một luồng độc lập trước khi transaction nghiệp vụ commit. Nếu event được gửi đi trước commit, consumer có thể nhìn thấy một thay đổi chưa được xác nhận. Cũng không nên phát event sau khi transaction đã kết thúc bằng một lời gọi thủ công tách rời; cách đó tạo lại khoảng trống giữa ghi dữ liệu và ghi nhận event.

## Đăng ký listener và theo dõi publication

Một listener trong module nhận có thể dùng @ApplicationModuleListener:

~~~java
@Component
@RequiredArgsConstructor
public class OrderConfirmedListener {

    private final ShipmentService shipmentService;

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        shipmentService.prepareShipment(event.orderId());
    }
}
~~~

Annotation này là lựa chọn tiện dụng của Spring Modulith cho listener cần được xử lý sau transaction phát event, bất đồng bộ và trong transaction riêng. Transaction listener là một transaction khác với transaction của publisher. Vì vậy:

- Lỗi trong listener không thể rollback transaction đơn hàng đã commit.
- Publication chưa hoàn tất có thể được registry giữ lại để phục hồi.
- Listener phải chịu được việc cùng một event được giao lại.
- Nếu listener gọi một dịch vụ bên ngoài, kết quả của lời gọi đó vẫn có thể không đồng bộ với trạng thái lưu trong database của listener.

Registry cần một implementation lưu trữ bền vững phù hợp với kiến trúc ứng dụng, chẳng hạn implementation tích hợp với relational database hoặc MongoDB mà hệ thống đang dùng. Chỉ bật listener bất đồng bộ hoặc thêm annotation không đủ để khẳng định publication được lưu bền vững. Hãy xác nhận implementation registry thực tế đã được cấu hình và tham gia đúng transaction.

## Minh họa dữ liệu publication

Về mặt khái niệm, registry cần lưu được thông tin tương tự:

| Thông tin | Mục đích |
|---|---|
| Event hoặc payload đã serialize | Dữ liệu để listener có thể nhận lại |
| Event type | Xác định loại sự kiện |
| Listener identifier | Xác định consumer cần xử lý |
| Publication time | Biết publication được tạo lúc nào |
| Completion state/time | Biết listener đã hoàn tất hay còn dang dở |

Đây là mô hình khái niệm để giải thích vòng đời publication, không phải cam kết về tên bảng hoặc cấu trúc schema nội bộ của từng persistence implementation. Khi vận hành, dùng schema và migration do implementation Spring Modulith đang sử dụng cung cấp; không tự tạo một bảng có tên giả định rồi cho rằng registry sẽ tự nhận diện.

Event payload được lưu bền vững có thể tồn tại qua nhiều lần triển khai. Vì vậy, nên ưu tiên payload nhỏ, có cấu trúc ổn định và chứa định danh nghiệp vụ cần thiết. Tránh đưa thông tin bí mật, dữ liệu nhạy cảm hoặc toàn bộ object persistence vào event. Nếu thay đổi cấu trúc event, cần cân nhắc khả năng đọc các publication cũ còn tồn đọng.

## Khi nào atomic write thực sự được bảo đảm?

Atomic write chỉ đúng khi các điều kiện transaction được đáp ứng đồng thời.

| Điều kiện | Ý nghĩa |
|---|---|
| Có transaction nghiệp vụ đang hoạt động | Thay đổi dữ liệu và việc phát event diễn ra trong cùng ranh giới transaction |
| Registry là persistent | Publication record được lưu bền vững, không chỉ nằm trong bộ nhớ |
| Registry tham gia cùng transaction | Ghi dữ liệu nghiệp vụ và publication record commit/rollback cùng nhau |
| Transaction manager được cấu hình đúng | Các repository và registry dùng chung transaction resource hoặc một cơ chế phối hợp transaction có bảo đảm tương đương |
| Listener là transactional listener được registry theo dõi | Registry biết publication nào cần hoàn tất |

Nếu dữ liệu nghiệp vụ nằm trong database A còn registry ghi vào database B bằng một transaction độc lập, một @Transactional thông thường không thể tự bảo đảm atomicity giữa hai database. Cần chọn kiến trúc transaction phân tán phù hợp hoặc chuyển sang transactional outbox đặt cùng database với dữ liệu nghiệp vụ.

Tương tự, nếu publisher không chạy trong transaction, hoặc registry chỉ dùng implementation in-memory, không thể dựa vào cơ chế này để bảo đảm phục hồi sau khi tiến trình dừng.

## Khi cần gửi event ra message broker

Application event trong Spring Modulith chủ yếu biểu diễn giao tiếp trong ứng dụng. Nếu nghiệp vụ cần gửi thông điệp đến Kafka, RabbitMQ hoặc một hệ thống bên ngoài, hãy xác định rõ nơi lưu bản ghi outbox và nơi thực hiện việc gửi.

Mẫu transactional outbox thường có luồng:

1. Transaction nghiệp vụ cập nhật dữ liệu và thêm một outbox record vào cùng database transaction.
2. Một relay đọc các record chưa gửi.
3. Relay gửi message đến broker.
4. Sau khi broker xác nhận, relay đánh dấu record đã gửi.
5. Nếu relay dừng sau khi broker nhận message nhưng trước khi đánh dấu record, message có thể được gửi lại.

Ví dụ rút gọn về phần ghi outbox:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    order.confirm();

    outboxRepository.save(
        OutboxMessage.pending(
            UUID.randomUUID(),
            "OrderConfirmed",
            serialize(new OrderConfirmed(UUID.randomUUID(), order.getId(), Instant.now()))
        )
    );
}
~~~

Đoạn code trên chỉ minh họa ranh giới ghi. Relay, xác nhận từ broker, retry, khóa khi đọc theo lô và chính sách dọn dữ liệu cần được thiết kế theo broker và tải thực tế. Không nên đánh dấu message đã gửi trước khi có xác nhận phù hợp từ broker.

Có thể dùng Event Publication Registry cho vòng đời transactional listener trong ứng dụng. Khi cần tích hợp broker, hãy xác nhận rõ khả năng externalization và persistence của cấu hình Spring Modulith đang dùng, hoặc triển khai outbox relay riêng. Không nên mặc định rằng một application event đã được lưu trong registry đồng nghĩa message đã được broker nhận.

## Retry không đồng nghĩa exactly-once

Một publication chưa hoàn tất có thể được gửi lại sau lỗi hoặc khi ứng dụng phục hồi. Điều này ưu tiên độ tin cậy của giao sự kiện, nhưng đồng nghĩa listener có thể nhận cùng một event nhiều lần.

Ví dụ, listener gọi dịch vụ giao hàng thành công nhưng tiến trình dừng trước khi registry kịp ghi nhận listener đã hoàn tất. Khi phục hồi, publication có thể được xử lý lại và tạo yêu cầu giao hàng thứ hai nếu listener không có cơ chế chống trùng.

Một listener nên có chiến lược idempotency:

- Dùng event ID ổn định để nhận diện một lần phát event.
- Lưu dấu đã xử lý trong cùng transaction với thay đổi nghiệp vụ của consumer.
- Đặt unique constraint trên khóa idempotency nếu phù hợp.
- Với lời gọi ra hệ thống ngoài, truyền idempotency key nếu API đích hỗ trợ.
- Chỉ đánh dấu hoàn tất sau khi các thay đổi cần thiết của listener đã commit.

Ví dụ về ý tưởng lưu dấu xử lý:

~~~java
@Transactional
public void handle(OrderConfirmed event) {
    if (processedEventRepository.existsByEventId(event.eventId())) {
        return;
    }

    shipmentService.prepareShipment(event.orderId());
    processedEventRepository.save(
        ProcessedEvent.of(event.eventId())
    );
}
~~~

Ví dụ giả định event có eventId ổn định và việc kiểm tra, ghi dấu, cập nhật dữ liệu consumer cùng tham gia một transaction. Nếu shipmentService gọi hệ thống ngoài, transaction database không thể tự rollback tác động bên ngoài; cần idempotency ở hệ thống đích hoặc một quy trình bù trừ phù hợp.

## Kiểm thử atomic write

Kiểm thử cần xác nhận hành vi transaction, thay vì chỉ kiểm tra publisher đã gọi publishEvent.

Các tình huống nên có:

| Tình huống | Điều cần xác nhận |
|---|---|
| Publisher thành công | Dữ liệu nghiệp vụ và publication record đều được commit |
| Publisher ném exception trước commit | Dữ liệu nghiệp vụ và publication record đều không tồn tại sau rollback |
| Listener chạy sau commit | Listener không xử lý event của transaction rollback |
| Listener xử lý thành công | Publication được registry ghi nhận hoàn tất |
| Listener lỗi | Publication còn trạng thái có thể phục hồi theo cấu hình registry |
| Listener nhận lại cùng event | Idempotency ngăn tác động nghiệp vụ bị lặp |

Với kiểm thử rollback, tạo một luồng nghiệp vụ ghi entity, phát event rồi chủ động ném exception trong cùng transaction. Sau khi lời gọi kết thúc, kiểm tra dữ liệu nghiệp vụ đã rollback và registry không còn publication đã commit cho event đó. Cách kiểm tra publication cụ thể phụ thuộc persistence implementation của ứng dụng.

Với listener bất đồng bộ, kiểm tra điều kiện cuối cùng bằng cơ chế chờ có giới hạn hoặc công cụ đồng bộ dành cho test. Tránh dùng thời gian ngủ cố định vì test sẽ chậm và dễ chập chờn. Cũng cần phân biệt transaction của test với transaction của service: transaction test chưa commit có thể khiến listener after-commit không được kích hoạt như mong đợi.

## Quan sát và vận hành publication chưa hoàn tất

Persistent registry tạo khả năng phục hồi, nhưng đội vận hành vẫn cần biết publication nào đang chờ hoặc lỗi lâu bất thường. Nên theo dõi tối thiểu:

- Số publication chưa hoàn tất.
- Tuổi của publication cũ nhất.
- Tỷ lệ listener xử lý lỗi và số lần thử lại nếu implementation cung cấp.
- Thời gian xử lý từ lúc phát event đến lúc hoàn tất.
- Nhóm event type và listener thường xuyên phát sinh lỗi.

Khi số publication chưa hoàn tất tăng, hãy kiểm tra lỗi listener, trạng thái database, thay đổi schema hoặc event payload, và các dịch vụ mà listener phụ thuộc. Tránh xóa hàng loạt publication chưa hoàn tất để làm sạch dashboard; thao tác đó có thể loại bỏ công việc nghiệp vụ chưa được xử lý. Chính sách dọn publication đã hoàn tất cần cân bằng giữa dung lượng lưu trữ, khả năng điều tra và yêu cầu lưu vết.

Việc retry cần có giới hạn hoặc cơ chế backoff phù hợp để một listener lỗi liên tục không tiêu thụ toàn bộ tài nguyên. Với lỗi dữ liệu không thể tự phục hồi, cần có quy trình xử lý thủ công và lưu lại nguyên nhân. Khi triển khai phiên bản mới, cần giữ khả năng đọc event cũ còn tồn đọng hoặc có chiến lược chuyển đổi rõ ràng.

## Những lỗi thiết kế thường gặp

- **Cho rằng after-commit tự bảo đảm durable delivery:** after-commit chỉ quyết định thời điểm listener chạy; cần persistent registry hoặc outbox để theo dõi công việc qua lần dừng tiến trình.
- **Dùng registry không cùng transaction với dữ liệu nghiệp vụ:** hai bản ghi có thể lệch nhau khi một phía commit còn phía kia rollback.
- **Gửi broker message trực tiếp trước commit:** consumer có thể xử lý một thay đổi nghiệp vụ cuối cùng bị rollback.
- **Cho rằng retry là exactly-once:** retry có thể tạo lần giao trùng; listener phải idempotent.
- **Đánh dấu hoàn tất quá sớm:** nếu ghi nhận hoàn tất trước khi thay đổi của listener commit, lỗi có thể làm mất công việc.
- **Đổi event payload mà không tính đến publication tồn đọng:** dữ liệu cũ có thể không còn deserialize hoặc không còn phù hợp với listener mới.
- **Xóa publication chưa hoàn tất để giảm số liệu:** thao tác này có thể làm mất dấu công việc chưa xử lý.

## Quy trình thiết kế đề xuất

Khi thêm một event vào module Spring Modulith, hãy lần lượt xác định:

1. Thay đổi nghiệp vụ nào phải được commit cùng event?
2. Publisher có transaction bao quanh cả thao tác ghi và phát event không?
3. Listener nào cần được registry theo dõi?
4. Persistent Event Publication Registry nào đang được cấu hình và nó có tham gia cùng transaction không?
5. Listener có thể chạy lại an toàn không?
6. Nếu event phải ra broker, outbox hoặc cơ chế externalization nào bảo đảm việc chuyển tiếp?
7. Đội vận hành sẽ phát hiện, điều tra và xử lý publication bị treo như thế nào?

Khi các câu hỏi này có câu trả lời rõ ràng, ranh giới giữa dữ liệu nghiệp vụ, event publication và công việc của listener sẽ dễ kiểm soát hơn. Khi persistent registry tham gia cùng transaction, atomic write bảo đảm một thay đổi nghiệp vụ đã commit đi kèm dấu vết publication cần thiết; retry và idempotency hoàn thiện phần xử lý đáng tin cậy sau commit.
