# Ghi event cùng transaction

Khi một đơn hàng được tạo, hệ thống thường phải cập nhật dữ liệu đơn hàng rồi thông báo cho các phần khác như kho, thanh toán hoặc thông báo khách hàng. Nếu hai thao tác này không có cùng một ranh giới nhất quán, hệ thống có thể rơi vào hai trạng thái sai:

- Đơn hàng đã commit nhưng tiến trình dừng trước khi gửi event, khiến phần nhận không bao giờ biết đơn hàng đã được tạo.
- Event được gửi trước khi transaction commit, phần nhận xử lý thành công nhưng transaction tạo đơn hàng lại rollback.

Ghi nhận event trong cùng transaction với dữ liệu nghiệp vụ giải quyết khoảng trống đó. Với Spring Modulith, Event Publication Registry có thể lưu trạng thái giao event cho các listener trong cùng transaction. Khi cần chuyển event sang một tiến trình hoặc message broker bên ngoài, transactional outbox là mẫu triển khai phù hợp để lưu thông điệp chờ gửi cùng transaction nghiệp vụ.

Bài này trình bày cách chọn và triển khai hai cơ chế đó, điều kiện để tính nguyên tử có hiệu lực, cách phục hồi khi listener hoặc broker gặp lỗi, và cách kiểm thử luồng giao event.

## 1. Vì sao chỉ publish sau commit vẫn chưa đủ?

Giả sử service tạo đơn hàng thực hiện hai bước:

1. Lưu đơn hàng vào database.
2. Publish event OrderPlaced để module kho giữ hàng.

Nếu publish ngay sau khi lưu nhưng trước commit, listener có thể chạy khi transaction vẫn còn khả năng rollback. Nếu đợi transaction commit rồi mới publish, ứng dụng vẫn có một khoảng trống giữa thời điểm database commit và thời điểm event được gửi.

Ví dụ, tiến trình có thể dừng đúng tại khoảng trống này:

~~~text
T1  INSERT order
T2  COMMIT database
T3  tiến trình bị dừng
T4  publish OrderPlaced   <-- không bao giờ xảy ra
~~~

Đơn hàng đã tồn tại nhưng module kho không nhận được thông báo. Đây là lỗi mất thông điệp do hai thao tác thuộc hai hệ thống lưu trữ hoặc hai thời điểm commit độc lập.

Spring cung cấp ApplicationEventPublisher để phát event trong phạm vi một ứng dụng. @TransactionalEventListener cho phép listener chạy theo một pha transaction, thường là AFTER_COMMIT. Cơ chế này ngăn listener xử lý event của một transaction đã rollback, nhưng riêng việc đợi AFTER_COMMIT không làm cho lần gọi listener trở thành một thao tác bền vững. Nếu ứng dụng dừng sau commit nhưng trước khi listener được gọi, event có thể bị mất.

Muốn xử lý cả trường hợp tiến trình dừng, cần ghi nhận rằng event còn phải được giao ngay trong transaction tạo dữ liệu nghiệp vụ. Khi transaction commit, cả dữ liệu nghiệp vụ và bản ghi publication cùng tồn tại. Khi transaction rollback, cả hai cùng bị rollback.

## 2. Hai cơ chế cần phân biệt

Spring Modulith và transactional outbox giải quyết các phạm vi liên quan nhưng không hoàn toàn giống nhau.

| Cơ chế | Phạm vi phù hợp | Dữ liệu được lưu | Thành phần giao tiếp |
|---|---|---|---|
| Event Publication Registry của Spring Modulith | Giao event tới listener trong các module của cùng ứng dụng | Publication cho từng listener, cùng trạng thái hoàn tất/chưa hoàn tất | Spring Modulith gọi listener và theo dõi publication |
| Transactional outbox | Giao integration event tới broker hoặc hệ thống khác | Thông điệp chờ gửi, trạng thái gửi, số lần thử và thông tin lỗi | Relay/worker đọc outbox rồi gửi tới broker |

Với giao tiếp giữa các module trong một Spring Modulith, hãy bắt đầu bằng application event và Event Publication Registry nếu cần theo dõi, phục hồi publication. Registry lưu trạng thái giao event tới các listener đã đăng ký; nó không tự biến mọi lời gọi HTTP hoặc broker tùy ý thành một giao dịch nguyên tử với database.

Với giao tiếp liên tiến trình, hãy dùng outbox để ghi integration event cùng transaction nghiệp vụ. Một relay độc lập sẽ chuyển các bản ghi đó sang Kafka, RabbitMQ hoặc broker tương ứng. Có thể dùng thêm cơ chế externalization phù hợp với phiên bản Spring Modulith đang sử dụng, nhưng vẫn cần xác định rõ nơi lưu bền vững, ranh giới transaction và chính sách xử lý trùng.

Không nên dùng một tên gọi chung là “event đã gửi” cho cả hai trạng thái. Publication nội bộ đã được listener xử lý thành công và thông điệp đã được broker xác nhận là hai mốc khác nhau.

## 3. Ghi nhận publication trong transaction với Spring Modulith

### 3.1. Publish event tại ranh giới nghiệp vụ

Event nên mô tả một sự kiện đã xảy ra, chẳng hạn OrderPlaced, thay vì mô tả một yêu cầu cần thực hiện như PlaceOrder. Dữ liệu event nên bất biến, có định danh nghiệp vụ cần thiết và không phụ thuộc vào việc listener truy cập trực tiếp entity đang được quản lý bởi persistence context.

Ví dụ dưới đây publish event ngay trong phương thức nghiệp vụ có transaction:

~~~java
public record OrderPlaced(
        UUID orderId,
        Instant occurredAt
) {}

@Service
@RequiredArgsConstructor
class PlaceOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    @Transactional
    public UUID place(PlaceOrderCommand command) {
        Order order = Order.place(
                command.customerId(),
                command.lines()
        );

        orders.save(order);

        events.publishEvent(new OrderPlaced(
                order.getId(),
                clock.instant()
        ));

        return order.getId();
    }
}
~~~

Điểm quan trọng là lời gọi publishEvent nằm trong cùng transaction với thao tác lưu Order. Event được phát ra từ service nghiệp vụ sau khi đã hình thành thay đổi cần công bố. Việc gọi publishEvent không có nghĩa listener đã xử lý xong; nó chỉ đưa event vào cơ chế xử lý event của Spring.

Phương thức phải thực sự chạy trong transaction do Spring quản lý. Nếu gọi một phương thức @Transactional thông qua self-invocation trong cùng bean, proxy transaction có thể không được áp dụng như mong đợi. Cần kiểm tra đường gọi thực tế từ bean khác hoặc cấu trúc service phù hợp.

### 3.2. Đăng ký listener sau commit

Spring Modulith cung cấp @ApplicationModuleListener cho listener của application module. Annotation này kết hợp xử lý event sau commit với thực thi bất đồng bộ và transaction riêng cho listener. Vì vậy listener không chạy trong transaction đang tạo đơn hàng.

~~~java
@Component
class ReserveInventoryOnOrderPlaced {

    private final InventoryService inventory;

    ReserveInventoryOnOrderPlaced(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        inventory.reserveFor(event.orderId());
    }
}
~~~

Có thể dùng @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT) khi cần tự khai báo rõ pha transaction hoặc khi không cần các đặc tính bổ sung của @ApplicationModuleListener. Với listener có side effect cần transaction riêng, hãy khai báo ranh giới transaction của listener một cách rõ ràng.

Nếu không có transaction đang hoạt động, transactional event listener mặc định không được gọi. Không nên dựa vào hành vi fallback cho luồng nghiệp vụ vốn yêu cầu event phải gắn với commit. Hãy bảo đảm event được publish từ một phương thức nghiệp vụ có transaction.

### 3.3. Event Publication Registry hoạt động như thế nào?

Khi Spring Modulith phát hiện event cần được giao cho transactional listener, Event Publication Registry tạo publication tương ứng cho từng listener. Với cấu hình persistence phù hợp, bản ghi publication được ghi trong cùng transaction với dữ liệu nghiệp vụ.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant S as PlaceOrderService
    participant DB as Database
    participant P as Event Publication Registry
    participant L as Module Listener

    S->>DB: Lưu Order
    S->>P: publish OrderPlaced
    P->>DB: Ghi publication cho listener
    Note over DB,P: Cùng transaction
    alt Transaction rollback
        DB-->>S: Rollback Order và publication
        Note over L: Listener không xử lý event đã rollback
    else Transaction commit
        DB-->>S: Commit Order và publication
        P-->>L: Giao event sau commit
        L->>DB: Thực hiện nghiệp vụ listener
        L-->>P: Đánh dấu publication hoàn tất
    end
~~~

Registry theo dõi publication riêng cho từng listener. Nếu một event có ba listener, trạng thái của một listener hoàn tất không có nghĩa hai listener còn lại cũng đã hoàn tất.

Để có khả năng phục hồi sau khi ứng dụng khởi động lại, cần cấu hình implementation lưu trữ bền vững của Spring Modulith, chẳng hạn JDBC, JPA hoặc MongoDB phù hợp với kiến trúc hiện tại. Với yêu cầu nguyên tử giữa dữ liệu nghiệp vụ và publication, kho lưu trữ publication phải tham gia đúng transaction và transaction manager tương ứng. Nếu chỉ dùng lưu trữ trong bộ nhớ hoặc ghi publication qua một transaction độc lập, không thể dựa vào bảo đảm nguyên tử này.

Cần triển khai schema lưu publication theo hướng dẫn của module persistence và phiên bản Spring Modulith đang dùng. Không tự giả định tên bảng, cấu trúc cột hoặc migration giữa các phiên bản; các chi tiết đó thuộc implementation lưu trữ được chọn.

### 3.4. Điều gì xảy ra khi transaction commit hoặc rollback?

| Tình huống | Dữ liệu nghiệp vụ | Publication | Listener |
|---|---|---|---|
| Transaction rollback | Không được commit | Bản ghi publication trong transaction cũng rollback | Không xử lý event của transaction đó |
| Transaction commit, listener xử lý thành công | Đã commit | Được đánh dấu hoàn tất | Đã xử lý |
| Transaction commit, listener ném exception | Đã commit | Vẫn chưa hoàn tất để có thể phục hồi | Có thể được thử lại |
| Ứng dụng dừng sau commit, trước khi listener hoàn tất | Đã commit | Publication chưa hoàn tất vẫn được lưu nếu dùng kho bền vững | Có thể được resubmit sau khi ứng dụng phục hồi |

Một listener thất bại sau commit không thể rollback đơn hàng đã được commit. Đây là hành vi đúng: transaction tạo đơn hàng và transaction xử lý event là hai transaction khác nhau. Hệ thống phải giữ lại publication chưa hoàn tất để phục hồi, đồng thời bảo đảm listener có thể chịu được việc được gọi lại.

## 4. Transactional outbox cho event gửi ra ngoài ứng dụng

Event Publication Registry phù hợp để theo dõi listener trong ứng dụng. Khi cần gửi thông điệp ra broker hoặc hệ thống khác, transactional outbox làm cho việc ghi dữ liệu nghiệp vụ và ghi thông điệp chờ gửi trở thành một transaction database duy nhất.

### 4.1. Cấu trúc bảng outbox

Ví dụ sau dùng cú pháp PostgreSQL. Cấu trúc thực tế có thể thay đổi theo database và chính sách vận hành:

~~~sql
CREATE TABLE outbox_event (
    id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT,
    event_type VARCHAR(200) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    last_error TEXT
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (status, next_attempt_at);
~~~

Ý nghĩa các trường chính:

- id là định danh duy nhất của event, dùng làm idempotency key khi gửi và nhận.
- aggregate_id xác định đối tượng nghiệp vụ phát sinh event.
- aggregate_version có thể dùng để giữ thứ tự event của cùng aggregate.
- event_type và schema_version cho phép consumer xác định loại payload và phiên bản hợp đồng.
- payload chứa snapshot dữ liệu cần công bố. Tránh lưu cả entity JPA hoặc dữ liệu không cần thiết.
- status biểu diễn trạng thái xử lý như PENDING, IN_FLIGHT hoặc SENT.
- attempts, next_attempt_at, locked_until hỗ trợ retry, lease và phối hợp nhiều relay.
- published_at và last_error phục vụ vận hành, điều tra lỗi.

Không nhất thiết phải dùng toàn bộ trường trên. Hãy chọn cấu trúc theo yêu cầu retry, thứ tự, lưu vết và khối lượng event của hệ thống.

### 4.2. Ghi business data và outbox trong cùng transaction

Service nghiệp vụ lưu aggregate và thêm outbox record trong cùng transaction:

~~~java
public record OrderPlacedV1(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}

@Service
@RequiredArgsConstructor
class PlaceOrderService {

    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final Clock clock;

    @Transactional
    public UUID place(PlaceOrderCommand command) {
        Order order = Order.place(
                command.customerId(),
                command.lines()
        );

        orders.save(order);

        OrderPlacedV1 event = new OrderPlacedV1(
                UUID.randomUUID(),
                order.getId(),
                clock.instant()
        );

        outbox.append(
                event.eventId(),
                order.getId(),
                "OrderPlaced",
                1,
                event
        );

        return order.getId();
    }
}
~~~

OutboxRepository có thể dùng JPA hoặc JdbcTemplate. Điều kiện bắt buộc là thao tác ghi outbox dùng cùng database connection/transaction manager với thao tác ghi Order. Nếu ghi outbox bằng một datasource khác hoặc đánh dấu REQUIRES_NEW, hai thao tác không còn được rollback/commit cùng nhau.

Kết quả:

- Nếu transaction rollback, cả Order và outbox record đều không tồn tại sau rollback.
- Nếu transaction commit, cả Order và outbox record cùng tồn tại.
- Nếu ứng dụng dừng ngay sau commit, relay vẫn có thể tìm thấy record PENDING khi chạy lại.

Event integration nên là một hợp đồng độc lập với cấu trúc entity nội bộ. Khi cần thay đổi payload, hãy tạo phiên bản schema mới hoặc áp dụng chiến lược tương thích ngược có kiểm soát.

### 4.3. Relay chuyển outbox sang broker

Relay đọc các record đến hạn, giữ quyền xử lý một khoảng thời gian, gửi tới broker và cập nhật trạng thái. Có thể triển khai bằng scheduled worker, message relay hoặc tiến trình riêng.

Một chu trình an toàn thường gồm các bước:

1. Trong một transaction ngắn, chọn một batch PENDING đến hạn và claim chúng bằng lock hoặc lease. Chuyển trạng thái sang IN_FLIGHT, ghi locked_until rồi commit.
2. Gửi payload tới broker bên ngoài transaction database. Chờ broker xác nhận thành công theo semantics của client.
3. Sau khi nhận xác nhận, dùng transaction ngắn để đánh dấu record SENT và ghi published_at.
4. Nếu gửi thất bại, dùng transaction ngắn để tăng attempts, lưu last_error, tính next_attempt_at theo backoff và trả record về trạng thái có thể retry.
5. Nếu worker dừng khi record đang IN_FLIGHT, lease hết hạn để worker khác có thể claim lại.

Không giữ transaction database mở trong suốt thời gian chờ network nếu không cần thiết. Transaction dài làm tăng thời gian giữ lock, gây áp lực connection pool và làm giảm khả năng xử lý đồng thời.

Với database hỗ trợ, relay có thể dùng SELECT ... FOR UPDATE SKIP LOCKED để nhiều worker claim batch mà ít tranh chấp. Nếu dùng lease, cần đặt thời hạn đủ dài cho một lần gửi bình thường và có cơ chế gia hạn khi xử lý kéo dài. Câu lệnh claim phải được thiết kế theo database cụ thể.

### 4.4. Vì sao outbox vẫn có thể gửi trùng?

Giả sử broker đã nhận event nhưng relay dừng trước khi cập nhật outbox thành SENT:

~~~text
T1  Relay gửi event E
T2  Broker xác nhận đã nhận E
T3  Relay bị dừng trước khi cập nhật SENT
T4  Lease hết hạn
T5  Relay khác gửi lại E
~~~

Broker có thể nhận E hai lần. Vì database và broker không cùng một transaction nguyên tử, outbox thường cung cấp semantics at-least-once: event sẽ được thử gửi cho tới khi thành công theo chính sách retry, nhưng consumer phải chấp nhận khả năng nhận trùng.

Không nên tuyên bố exactly-once chỉ vì có outbox. Hãy làm consumer idempotent bằng cách lưu event id đã xử lý trong cùng transaction với thay đổi nghiệp vụ:

~~~java
@Transactional
public void handle(OrderPlacedV1 event) {
    if (processedEvents.existsById(event.eventId())) {
        return;
    }

    inventory.reserveFor(event.orderId());
    processedEvents.save(new ProcessedEvent(event.eventId()));
}
~~~

Trong ví dụ này, cập nhật tồn kho và ghi nhận event id phải cùng transaction. Nếu transaction rollback, cả hai cùng rollback; lần giao lại có thể xử lý lại. Nếu transaction commit, lần giao trùng tiếp theo sẽ bị bỏ qua.

Với nhiều consumer, mỗi consumer cần vùng lưu idempotency riêng hoặc khóa duy nhất kết hợp consumer identity và event id. Nếu consumer gọi tiếp một hệ thống bên ngoài, cần thiết kế idempotency ở ranh giới đó nữa.

### 4.5. Giữ thứ tự event

Nếu nghiệp vụ yêu cầu event của cùng một aggregate phải được xử lý theo thứ tự, chỉ sắp xếp theo occurred_at có thể chưa đủ vì nhiều event có thể cùng timestamp hoặc relay chạy song song.

Có thể dùng aggregate_version hoặc sequence tăng đơn điệu cho từng aggregate. Relay cần tránh gửi phiên bản sau khi phiên bản trước của cùng aggregate còn chưa được gửi. Broker nên dùng aggregate_id làm partition key nếu broker có khái niệm partition và cần giữ thứ tự trong partition.

Chỉ nên áp dụng bảo đảm thứ tự ở phạm vi nghiệp vụ thực sự cần. Giữ thứ tự toàn cục thường làm giảm thông lượng và tạo điểm nghẽn không cần thiết.

## 5. Retry và phục hồi publication

Với Event Publication Registry, publication chưa hoàn tất là dấu hiệu listener chưa được xác nhận hoàn thành. Spring Modulith cung cấp API IncompleteEventPublications để truy vấn và resubmit các publication còn dang dở. Có thể đưa thao tác resubmit vào một quy trình vận hành có kiểm soát, lọc theo event hoặc listener nếu API của phiên bản đang dùng hỗ trợ predicate tương ứng.

Hãy kiểm tra overload API và cấu hình tự động resubmit theo đúng phiên bản Spring Modulith của dự án. Không nên chạy resubmit toàn bộ publication một cách mù quáng trong mỗi lần khởi động nếu chưa hiểu tác động tới listener, tải hệ thống và dữ liệu cũ.

Với outbox, retry nên có backoff tăng dần và giới hạn phù hợp. Một công thức đơn giản là:

~~~text
delay = min(initialDelay * 2^attempts, maxDelay) + jitter
~~~

Jitter giúp nhiều record lỗi không đồng loạt retry tại cùng một thời điểm. Sau số lần thử hoặc thời gian chờ đã định, có thể chuyển record sang trạng thái cần can thiệp, nhưng phải giữ đủ dữ liệu để điều tra và replay có kiểm soát.

Khi xử lý lỗi, phân biệt:

- Lỗi tạm thời: timeout, broker tạm ngừng, lỗi mạng. Có thể retry.
- Lỗi cấu hình: sai topic, credential hết hạn, quyền publish thiếu. Cần cảnh báo và sửa cấu hình.
- Lỗi hợp đồng: payload không hợp lệ hoặc consumer không hiểu schema. Cần xử lý phiên bản hoặc dữ liệu; retry liên tục thường không giải quyết được.
- Lỗi nghiệp vụ ở listener: dữ liệu hiện tại không thỏa điều kiện xử lý. Cần quyết định rõ có thể retry sau hay phải chuyển sang quy trình xử lý thủ công.

Một event được giao lại có thể chạy lại side effect. Vì vậy idempotency là điều kiện của cơ chế phục hồi, không phải phần tối ưu thêm.

## 6. Kiểm thử tính nguyên tử và khả năng phục hồi

Mock ApplicationEventPublisher chỉ xác minh service có gọi publishEvent; nó không chứng minh publication được lưu cùng transaction. Cần có integration test với database và persistence implementation mà ứng dụng thực sự sử dụng.

Các tình huống cần kiểm tra:

| Kịch bản | Điều cần xác minh |
|---|---|
| Tạo đơn hàng thành công | Order và publication/outbox record cùng được commit |
| Transaction tạo đơn hàng rollback | Không còn Order và không còn publication/outbox record của transaction đó |
| Listener chạy thành công | Publication tương ứng được đánh dấu hoàn tất |
| Listener ném exception | Publication vẫn ở trạng thái chưa hoàn tất và có thể resubmit |
| Ứng dụng dừng sau commit | Publication/outbox record còn trong kho bền vững sau khi khởi động lại |
| Relay gửi thành công rồi dừng trước khi đánh dấu SENT | Event có thể được gửi lại và consumer không tạo side effect trùng |
| Hai relay cùng chạy | Một record không bị hai worker claim đồng thời trong cùng lease |
| Payload đổi phiên bản | Consumer xử lý được phiên bản được công bố hoặc từ chối có kiểm soát |

Một lưu ý khi viết test: nếu test method tự mở transaction và rollback ở cuối test, listener AFTER_COMMIT có thể không được kích hoạt. Hãy chủ động commit transaction trong test hoặc dùng cách kiểm thử phù hợp để xác minh hành vi sau commit. Với listener bất đồng bộ, cần chờ điều kiện hoàn tất bằng cơ chế đồng bộ trong test thay vì dùng sleep cố định.

Nên có ít nhất một integration test chứng minh rollback của transaction nghiệp vụ cũng rollback bản ghi publication/outbox. Đây là kiểm thử trực tiếp cho yêu cầu “ghi event cùng transaction”.

## 7. Quan sát và vận hành

Một hệ thống có event bền vững vẫn cần quan sát được backlog và lỗi. Các chỉ số hữu ích gồm:

- Số publication chưa hoàn tất, phân nhóm theo listener.
- Tuổi của publication chưa hoàn tất lâu nhất.
- Số outbox record theo trạng thái PENDING, IN_FLIGHT, SENT và trạng thái cần can thiệp.
- Tuổi của outbox record PENDING lâu nhất.
- Số lần retry, tỷ lệ gửi thành công và thời gian từ occurred_at tới published_at.
- Số event bị consumer từ chối hoặc bị loại do trùng.
- Lỗi gần nhất theo event type, listener hoặc broker destination.

Log nên có event id, aggregate id, event type, schema version, correlation/trace id và tên listener hoặc destination. Không ghi toàn bộ payload nếu payload có dữ liệu nhạy cảm hoặc quá lớn; ưu tiên ghi định danh để truy vết.

Đặt cảnh báo theo tuổi backlog và tốc độ tăng lỗi, không chỉ theo tổng số record. Một backlog nhỏ nhưng không giảm trong thời gian dài có thể nghiêm trọng hơn một batch lớn đang được xử lý bình thường.

Quy trình vận hành cần chỉ rõ ai có quyền resubmit, điều kiện replay, cách xử lý poison event và cách tránh gửi lặp side effect. Không xóa publication hoặc outbox record lỗi chỉ để làm dashboard sạch; trước khi dọn dữ liệu phải xác định event đã được xử lý hay chưa và lưu lại dấu vết cần thiết.

## 8. Lỗi thiết kế thường gặp

**Publish event ngoài transaction nghiệp vụ.** Publication không còn được ràng buộc với commit của dữ liệu. Hãy publish từ service đang quản lý transaction.

**Dùng @EventListener cho công việc bắt buộc chạy sau commit.** Listener thông thường có thể chạy ngay khi event được publish. Dùng transactional listener hoặc @ApplicationModuleListener cho đúng pha.

**Cho rằng AFTER_COMMIT tự bảo đảm giao event bền vững.** AFTER_COMMIT kiểm soát thời điểm gọi listener, còn Event Publication Registry hoặc outbox mới cung cấp bản ghi để phục hồi sau sự cố.

**Ghi outbox bằng REQUIRES_NEW.** Outbox có thể commit dù transaction nghiệp vụ rollback. Ghi outbox trong cùng transaction và cùng transaction manager.

**Gửi broker trong transaction tạo đơn hàng.** Network call kéo dài transaction và vẫn không tạo ra atomic commit giữa database với broker. Hãy ghi outbox trước, rồi relay gửi sau commit.

**Đánh dấu SENT trước khi broker xác nhận.** Nếu gửi thất bại sau khi đánh dấu, event có thể mất. Chỉ đánh dấu sau xác nhận thành công; chấp nhận duplicate ở khoảng trống còn lại và xử lý bằng idempotency.

**Listener có side effect không idempotent.** Retry có thể trừ tồn kho hoặc gửi thông báo nhiều lần. Dùng event id và transaction deduplication để bảo vệ side effect.

**Dùng entity làm payload event.** Entity có thể chứa lazy association, trạng thái thay đổi theo thời gian và chi tiết persistence nội bộ. Tạo event DTO bất biến chỉ chứa dữ liệu cần thiết.

**Không quản lý phiên bản payload.** Consumer cũ có thể không đọc được event mới. Thêm schema version và chiến lược tương thích cho consumer.

## 9. Chọn cơ chế theo nhu cầu

| Nhu cầu | Cách triển khai |
|---|---|
| Module A thông báo module B trong cùng ứng dụng, không cần lưu vết phục hồi | Application event với listener phù hợp |
| Module A thông báo module B sau commit và cần theo dõi listener chưa hoàn tất | Spring Modulith Event Publication Registry với persistence bền vững |
| Gửi event tới broker hoặc ứng dụng khác, cần không mất event khi tiến trình dừng | Transactional outbox và relay |
| Vừa cần listener nội bộ đáng tin cậy vừa cần integration event | Dùng publication registry cho listener nội bộ và outbox cho thông điệp ra ngoài; xác định rõ event contract và ranh giới transaction |

Khi thiết kế, hãy trả lời bốn câu hỏi trước khi chọn giải pháp:

1. Event chỉ được dùng trong các module của cùng ứng dụng hay phải đi qua process boundary?
2. Nếu database commit nhưng ứng dụng dừng ngay sau đó, hệ thống cần phục hồi event bằng cách nào?
3. Ai chịu trách nhiệm retry và theo dõi publication chưa hoàn tất?
4. Listener/consumer có thể xử lý cùng một event nhiều lần mà không tạo side effect trùng không?

Một thiết kế tốt đặt bản ghi event ở cùng ranh giới commit với thay đổi nghiệp vụ, giao event sau commit, lưu trạng thái đủ để phục hồi và làm cho xử lý lặp trở nên an toàn. Với Spring Modulith, Event Publication Registry hỗ trợ phần giao event giữa các module; với tích hợp liên tiến trình, transactional outbox mở rộng nguyên tắc đó tới broker bằng một relay có retry và consumer idempotent.

