# Deduplication store

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module giao tiếp bằng những sự kiện nghiệp vụ có hợp đồng rõ ràng. Khi listener xử lý event, cùng một event có thể được giao nhiều lần do retry, broker redelivery, ứng dụng khởi động lại hoặc acknowledgement bị mất. Nếu mỗi lần giao đều tạo tác dụng phụ mới, hệ thống có thể giữ hàng hai lần, ghi nhận thanh toán trùng hoặc gửi nhiều thông báo giống nhau.

**Deduplication store** là nơi lưu dấu định danh message mà một consumer đã tiếp nhận hoặc xử lý. Consumer dùng kho này để nhận biết lần giao hiện tại là lần đầu hay bản sao của một event đã gặp. Store chỉ phát huy tác dụng khi định danh event ổn định, phạm vi chống trùng được xác định đúng và việc ghi dấu được phối hợp nguyên tử với tác dụng nghiệp vụ cần bảo vệ.

Deduplication là một phần của thiết kế idempotency. Nó giúp phát hiện cùng một message được giao lại; idempotency bảo đảm việc xử lý lặp không tạo ra kết quả nghiệp vụ khác. Hai khái niệm liên quan nhưng không thay thế nhau: một consumer có thể cần idempotent ngay cả khi không có deduplication store, và một store có thể ghi nhận message nhưng vẫn không ngăn được tác dụng phụ bên ngoài nếu transaction được thiết kế sai.

## 1. Vì sao event được giao nhiều lần?

Trong hệ thống event-driven, producer và consumer không chia sẻ một transaction duy nhất. Producer có thể gửi message thành công nhưng mất phản hồi xác nhận. Consumer có thể xử lý xong rồi process dừng trước khi ACK. Broker không biết tác dụng nghiệp vụ đã xảy ra hay chưa, vì vậy có thể giao lại message.

Các tình huống thường gặp:

- Consumer xử lý thành công nhưng kết nối bị ngắt trước khi acknowledgement tới broker.
- Listener ném exception và cơ chế retry gửi lại message.
- Broker redeliver message chưa được ACK khi channel hoặc consumer đóng.
- Outbox dispatcher gửi message, broker đã nhận nhưng process dừng trước khi đánh dấu outbox hoàn tất.
- Event Publication Registry phục hồi một publication chưa hoàn tất.
- Người vận hành replay message từ dead-letter queue hoặc kho lưu trữ.
- Producer gửi lại cùng một sự kiện vì không nhận được kết quả publish rõ ràng.

Vì vậy, giao nhận thường được thiết kế theo hướng **at-least-once**: một message có thể được giao một hoặc nhiều lần cho tới khi hoàn tất theo chính sách. Consumer cần coi duplicate delivery là tình huống bình thường của hệ thống, không phải một trường hợp hiếm có thể bỏ qua.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    participant C as Consumer
    participant DB as Consumer database
    P->>B: Publish event E-42
    B->>C: Deliver E-42
    C->>DB: Commit tác dụng nghiệp vụ
    Note over C,B: ACK bị mất trước khi broker nhận
    B->>C: Redeliver E-42
    C->>DB: Tra deduplication store
    DB-->>C: E-42 đã hoàn tất
    C-->>B: ACK duplicate
~~~

Trong ví dụ, lần giao thứ hai không chạy lại tác dụng nghiệp vụ. Consumer tra store, nhận biết event đã hoàn tất và ACK bản sao để broker giải phóng message.

## 2. Deduplication và idempotency khác nhau thế nào?

Deduplication trả lời câu hỏi: “Message này đã được consumer xử lý hoặc ghi nhận chưa?”. Idempotency trả lời câu hỏi: “Nếu cùng một yêu cầu được thực hiện lại, kết quả nghiệp vụ có bị thay đổi thêm lần nữa không?”.

| Cơ chế | Trách nhiệm | Ví dụ |
|---|---|---|
| Deduplication store | Nhận diện cùng một message theo ID và phạm vi consumer | eventId đã có trong inbox |
| Idempotent handler | Bảo đảm tác dụng nghiệp vụ lặp không bị nhân đôi | Capture cùng payment reference không thu tiền lần hai |
| Unique constraint | Chặn dữ liệu trùng tại nơi lưu trữ | Một reservation cho một commandId |
| Idempotency key ở API ngoài | Giúp hệ thống đích nhận diện cùng yêu cầu | Gửi lại request hoàn tiền với cùng key |

Một deduplication store có thể bỏ qua lần giao thứ hai của cùng eventId. Nhưng nếu producer tạo eventId mới cho cùng một ý định nghiệp vụ, store không nhận ra đó là duplicate. Ngược lại, handler có thể dùng business key hoặc unique constraint để bảo vệ tác dụng phụ ngay cả khi hai event khác ID cùng yêu cầu một nghiệp vụ.

Hãy dùng cả hai lớp khi cần: message identity để loại duplicate delivery và business invariant để ngăn tác dụng phụ trùng theo quy tắc domain.

## 3. Xác định event identity và phạm vi chống trùng

Một event cần có ID ổn định, được tạo một lần khi event hình thành và giữ nguyên qua retry, redelivery hoặc replay của cùng message. Không sinh eventId mới ở mỗi lần gửi lại.

Store phải xác định phạm vi uniqueness. Chỉ dùng eventId làm khóa có thể không đủ nếu producer khác nhau có thể tạo cùng một ID. Một khóa thường dùng là:

- consumerName: tên handler hoặc subscription chịu trách nhiệm xử lý;
- eventSource: nguồn phát event, nếu ID chỉ duy nhất trong phạm vi producer;
- eventId: định danh message do producer cấp.

Có thể mở rộng khóa với tenant hoặc subscription khi các tenant có miền định danh riêng. Không đưa eventType vào khóa nếu cùng một eventId phải luôn đại diện cho một message duy nhất; eventType phù hợp hơn để kiểm tra metadata và chẩn đoán.

Ví dụ, cùng một event có thể được hai consumer xử lý độc lập. Consumer **inventory-projection** cần một bản ghi dedup riêng với consumer **notification-sender**. Nếu store chỉ khóa theo eventId trên toàn hệ thống, consumer đầu tiên có thể khiến consumer thứ hai bị bỏ qua nhầm.

Một schema minh họa:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(160) NOT NULL,
    event_source VARCHAR(240) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    event_type VARCHAR(240) NOT NULL,
    payload_hash VARCHAR(128),
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP,
    status VARCHAR(32) NOT NULL,
    PRIMARY KEY (consumer_name, event_source, event_id)
);
~~~

Khóa chính thể hiện một event chỉ được ghi nhận một lần trong phạm vi một consumer và một source. **payload_hash** có thể dùng để phát hiện trường hợp producer tái sử dụng cùng ID nhưng gửi nội dung khác. Không dùng hash làm định danh duy nhất thay cho eventId vì hai payload giống nhau vẫn có thể là hai sự kiện nghiệp vụ hợp lệ xảy ra ở hai thời điểm khác nhau.

## 4. Chọn khóa theo hợp đồng event

Nếu ứng dụng dùng CloudEvents, cặp **source** và **id** là định danh phù hợp để nhận diện một event. Nếu contract nội bộ bảo đảm eventId duy nhất trên toàn hệ thống, có thể dùng eventId đơn lẻ kết hợp consumerName. Điều quan trọng là producer và consumer phải thống nhất phạm vi uniqueness.

Nên ghi lại trong contract:

- Ai tạo eventId và ở thời điểm nào.
- ID có duy nhất toàn hệ thống, theo producer hay theo tenant.
- Retry có giữ nguyên ID hay không.
- Replay có giữ nguyên ID gốc hay tạo một event mới.
- Consumer nào có phạm vi dedup riêng.
- Bao lâu store giữ dấu đã xử lý.

Không dùng aggregateId làm event identity. Một aggregate có thể phát nhiều event trong vòng đời của nó. Nếu dùng orderId làm khóa dedup, event OrderPlaced có thể khiến OrderShipped hoặc OrderCancelled bị xem nhầm là duplicate. AggregateId là khóa liên kết nghiệp vụ; eventId là khóa nhận diện một lần xảy ra cụ thể.

Nếu event có sequence/version theo aggregate, có thể lưu thêm để phát hiện event cũ hoặc sai thứ tự. Sequence phục vụ ordering và kiểm tra tiến trình; nó không thay thế eventId vì một consumer có thể nhận nhiều loại event trong cùng một sequence policy.

## 5. Ghi inbox và tác dụng nghiệp vụ trong cùng transaction

Với handler chỉ thay đổi dữ liệu trong cùng một cơ sở dữ liệu, cách an toàn nhất là ghi dấu event và thay đổi nghiệp vụ trong một transaction. Hai thao tác phải cùng commit hoặc cùng rollback.

Luồng xử lý:

1. Consumer nhận event và xác thực envelope.
2. Trong transaction, thử insert khóa consumer/source/eventId vào inbox.
3. Nếu insert thành công, đây là lần xử lý đầu tiên; thực hiện thay đổi nghiệp vụ.
4. Đánh dấu inbox hoàn tất trong cùng transaction.
5. Commit transaction, sau đó listener mới ACK theo cơ chế container.
6. Nếu insert không thành công do khóa đã tồn tại, kiểm tra trạng thái và xử lý duplicate theo chính sách.

~~~mermaid
flowchart TD
    A["Nhận event"] --> B["Bắt đầu transaction"]
    B --> C["Insert inbox key"]
    C --> D{"Insert thành công?"}
    D -->|Không| E["Đã tồn tại: kiểm tra trạng thái"]
    E --> F["Bỏ qua tác dụng phụ"]
    F --> G["ACK duplicate"]
    D -->|Có| H["Thực hiện cập nhật nghiệp vụ"]
    H --> I["Đánh dấu inbox COMPLETED"]
    I --> J["Commit"]
    J --> K["ACK message"]
~~~

Nếu transaction rollback, cả inbox row và thay đổi nghiệp vụ đều rollback. Lần giao tiếp theo có thể thử lại từ đầu. Nếu transaction commit nhưng ACK bị mất, lần giao tiếp sau thấy inbox đã hoàn tất và bỏ qua tác dụng phụ.

Không đánh dấu event là COMPLETED trước khi cập nhật nghiệp vụ. Nếu store commit dấu đã xử lý nhưng tác dụng nghiệp vụ thất bại, lần giao lại sẽ bị bỏ qua và dữ liệu không bao giờ được cập nhật. Ngược lại, nếu tác dụng nghiệp vụ commit trước rồi mới ghi inbox bằng transaction khác, crash ở khoảng giữa có thể khiến tác dụng phụ bị lặp.

## 6. Thực hiện insert-if-absent an toàn khi có concurrency

Hai instance consumer có thể nhận cùng một event gần như đồng thời. Cả hai cùng đọc store và thấy chưa có bản ghi, rồi cùng xử lý. Mẫu SELECT trước rồi INSERT sau không đủ để chống race condition nếu không có khóa hoặc constraint phù hợp.

Dùng unique constraint làm hàng rào cuối cùng. Repository nên có thao tác insert-if-absent nguyên tử, dựa trên cú pháp của database đang dùng. Ví dụ PostgreSQL:

~~~sql
INSERT INTO consumer_inbox (
    consumer_name,
    event_source,
    event_id,
    event_type,
    received_at,
    status
)
VALUES (
    :consumer_name,
    :event_source,
    :event_id,
    :event_type,
    CURRENT_TIMESTAMP,
    'PROCESSING'
)
ON CONFLICT (consumer_name, event_source, event_id) DO NOTHING
RETURNING event_id;
~~~

Nếu câu lệnh trả về eventId, transaction hiện tại đã giành quyền xử lý. Nếu không có dòng trả về, khóa đã tồn tại. Consumer cần đọc trạng thái hiện có và quyết định duplicate đã hoàn tất, đang xử lý hay cần phục hồi.

Cú pháp **ON CONFLICT** là đặc thù PostgreSQL. Với hệ quản trị khác, dùng cơ chế insert-if-absent hoặc bắt lỗi unique constraint theo cách không làm transaction bị đánh dấu rollback ngoài ý muốn. Không chỉ dựa vào kiểm tra ở tầng Java vì nhiều instance vẫn có thể chạy đồng thời.

Với một event chỉ có xử lý database cục bộ, transaction insert inbox, cập nhật nghiệp vụ và đánh dấu hoàn tất có thể giữ rất ngắn. Tránh giữ khóa database trong khi gọi API hoặc chờ broker.

## 7. Ví dụ handler với Spring

Một listener Spring Modulith có thể chuyển event cho application service xử lý trong transaction:

~~~java
@Component
class InventoryEventListener {

    private final InventoryEventHandler handler;

    InventoryEventListener(InventoryEventHandler handler) {
        this.handler = handler;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        handler.handle(event);
    }
}
~~~

Service xử lý dedup và thay đổi tồn kho:

~~~java
@Service
class InventoryEventHandler {

    private final InboxRepository inbox;
    private final InventoryRepository inventory;

    InventoryEventHandler(
            InboxRepository inbox,
            InventoryRepository inventory) {
        this.inbox = inbox;
        this.inventory = inventory;
    }

    @Transactional
    public void handle(OrderConfirmed event) {
        boolean firstDelivery = inbox.tryInsert(
            "inventory-handler",
            event.source(),
            event.eventId(),
            "OrderConfirmed"
        );

        if (!firstDelivery) {
            return;
        }

        inventory.reserve(
            event.orderId(),
            event.items()
        );

        inbox.markCompleted(
            "inventory-handler",
            event.source(),
            event.eventId()
        );
    }
}
~~~

**tryInsert** cần được triển khai bằng insert-if-absent có unique constraint; không triển khai thành một cặp exists rồi save thiếu bảo vệ concurrency. Repository inbox và inventory phải tham gia cùng transaction manager để bảo đảm tính nguyên tử.

Ví dụ giả định event được xử lý bằng transaction cục bộ và reserve không thực hiện tác dụng phụ ngoài database. Nếu listener chạy bất đồng bộ, transaction cần bắt đầu trong application service được gọi qua Spring proxy; tránh self-invocation làm mất hiệu lực @Transactional. Cấu hình listener và transaction thực tế cần phù hợp với phiên bản Spring Modulith đang dùng.

## 8. Có cần trạng thái PROCESSING hay chỉ cần dấu COMPLETED?

Với xử lý ngắn và mọi tác dụng phụ nằm trong cùng database transaction, có thể chỉ lưu một bản ghi inbox khi transaction xử lý thành công. Bản ghi được insert, thay đổi nghiệp vụ và đánh dấu hoàn tất cùng commit. Khi transaction rollback, không còn dấu đã xử lý.

Với xử lý dài hoặc cần tách claim khỏi công việc, store có thể quản lý trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| PROCESSING | Một worker đã claim event và đang xử lý |
| COMPLETED | Tác dụng nghiệp vụ đã hoàn tất |
| RETRYABLE_FAILURE | Lần xử lý thất bại do nguyên nhân có thể phục hồi |
| REQUIRES_REVIEW | Cần điều tra hoặc xử lý thủ công |
| ABANDONED | Claim cũ đã hết lease và cần worker khác tiếp quản |

Trong mô hình có claim, cần thêm **owner_token**, **lease_until**, **attempt_count** và **last_error**. Worker chỉ được đánh dấu hoàn tất nếu vẫn sở hữu claim hợp lệ. Lease giúp phục hồi khi worker chết, nhưng cần kiểm soát gia hạn và fencing/version để worker cũ không ghi đè kết quả của worker mới sau khi lease hết hạn.

Không nên giữ trạng thái PROCESSING vĩnh viễn nếu process có thể dừng. Một bản ghi PROCESSING cần có lease hoặc cơ chế phục hồi rõ ràng. Nếu không có, duplicate delivery có thể bị bỏ qua mãi dù tác vụ ban đầu chưa bao giờ hoàn tất.

## 9. Tác dụng phụ bên ngoài database

Deduplication trong database không thể tự tạo transaction nguyên tử với một API bên ngoài, email server hoặc hệ thống thanh toán. Ví dụ consumer gọi cổng thanh toán, cổng đã thu tiền nhưng phản hồi timeout. Nếu consumer chưa đánh dấu inbox COMPLETED, message có thể được giao lại và yêu cầu thu tiền có thể lặp.

Không giải quyết bằng cách giữ transaction database mở trong khi gọi API. Thay vào đó, phối hợp các cơ chế:

1. Trong transaction, claim event và ghi command cần thực hiện vào outbox.
2. Commit inbox/state/outbox cùng nhau.
3. Dispatcher gửi command ra ngoài sau commit.
4. Dùng commandId hoặc idempotency key ổn định cho API đích.
5. Lưu kết quả phản hồi và trạng thái command.
6. Nếu kết quả không rõ, query trạng thái bằng cùng idempotency key trước khi thử hành động mới.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant DB as Database
    participant O as Outbox dispatcher
    participant X as External API
    C->>DB: Inbox + business state + outbox
    DB-->>C: Commit
    O->>DB: Claim command
    O->>X: Request với idempotency key
    X-->>O: Result hoặc timeout
    O->>DB: Lưu kết quả / trạng thái
~~~

Nếu API đích không hỗ trợ idempotency key, cần thiết kế trạng thái thao tác và reconciliation. Khi timeout, không thể suy ra API chưa thực hiện chỉ vì consumer chưa nhận phản hồi. Tra cứu theo business reference hoặc đối soát với hệ thống đích trước khi gửi lại.

## 10. Deduplication store và Event Publication Registry

Spring Modulith Event Publication Registry và consumer deduplication store có mục đích khác nhau.

Event Publication Registry theo dõi publication của application event tới transactional listeners. Nó giúp xác định publication đã hoàn tất hay còn incomplete và hỗ trợ phục hồi theo cấu hình persistence. Registry tập trung vào vòng đời giao event trong ứng dụng.

Deduplication store thuộc phía consumer. Nó ghi nhận một event đã được consumer xử lý để ngăn tác dụng phụ bị lặp khi event được giao lại. Store thường được khóa theo consumer và event identity, đồng thời được commit cùng dữ liệu nghiệp vụ mà handler thay đổi.

Hai cơ chế có thể cùng xuất hiện:

- Registry giúp ứng dụng biết listener publication còn cần được xử lý hay không.
- Inbox giúp listener nhận ra event đã xử lý trong một lần giao trước.
- Listener có thể nhận cùng event sau khi publication được resubmit; inbox giúp lần giao lại không chạy tác dụng phụ lần hai.
- Publication completed không tự chứng minh tác dụng phụ ngoài database đã được thực hiện đúng; handler vẫn cần idempotency.

Không dùng registry thay cho inbox nếu consumer cần bảo vệ tác dụng phụ ở mức nghiệp vụ. Cũng không coi inbox là cơ chế thay thế publication registry khi ứng dụng cần theo dõi publication chưa hoàn tất.

## 11. Retention và thời hạn lưu dấu dedup

Deduplication store phải giữ dấu đủ lâu để bao phủ mọi khả năng message được giao lại. Nếu xóa bản ghi quá sớm, một message cũ từ retry queue, dead-letter queue hoặc replay có thể được xử lý lại như lần đầu.

Thời hạn lưu nên xét:

- Message retention của broker hoặc event log.
- Thời gian retry tối đa và lịch backoff.
- Thời gian message có thể nằm trong dead-letter queue.
- Khoảng thời gian người vận hành được phép replay.
- Độ trễ tối đa của consumer và thời gian phục hồi sau outage.
- Yêu cầu audit hoặc quy định lưu trữ của nghiệp vụ.

Với event có tác dụng tài chính hoặc tạo tài nguyên quan trọng, chỉ đặt TTL ngắn có thể không đủ. Có thể cần giữ khóa idempotency lâu dài hoặc dùng business ledger/unique constraint để ngăn tác dụng phụ trùng ngay cả sau khi inbox row được dọn.

Dọn dữ liệu nên chạy theo batch có giới hạn, có metric và có thể tiếp tục sau lỗi. Không xóa bản ghi PROCESSING hoặc RETRYABLE_FAILURE chỉ vì quá cũ; cần kiểm tra lease và trạng thái thực tế trước. Bản ghi COMPLETED có thể được archive hoặc purge khi đã vượt retention và không còn khả năng replay hợp lệ.

## 12. Replay, backfill và xây dựng lại projection

Replay có chủ đích khác với redelivery ngoài ý muốn. Khi xây dựng lại read model, có thể cần xử lý lại toàn bộ event lịch sử. Nếu dùng cùng consumerName và cùng event identity, dedup store sẽ bỏ qua những event đã xử lý trước đó.

Một chiến lược là tạo một consumer identity/version mới, ví dụ **order-summary-v2**, với kho dedup riêng. Consumer mới xây projection từ đầu trong một namespace hoặc bảng riêng, sau đó chuyển traffic đọc khi đã kiểm tra dữ liệu. Cách này giữ nguyên dấu dedup của consumer đang phục vụ.

Nếu cần chạy lại một event để sửa dữ liệu, phải có quy trình replay được kiểm soát: xác định event, lý do, consumer đích, phạm vi tác dụng phụ và cách tránh gửi lại email/thu tiền/giữ hàng. Không xóa inbox row tùy tiện để ép xử lý lại. Với nghiệp vụ có tác dụng phụ không thể lặp, nên tạo một command sửa sai mới có business key và audit riêng thay vì replay nguyên event cũ.

Replay phải giữ được nguồn gốc. Log và audit nên phân biệt original delivery, broker redelivery, operator replay và projection rebuild. Có thể thêm replay batch ID hoặc processing generation vào metadata vận hành; không làm thay đổi eventId gốc nếu đó vẫn là cùng một event.

## 13. Xử lý cùng eventId nhưng payload khác

Nếu producer tái sử dụng eventId cho payload khác, consumer không nên âm thầm coi đó là duplicate hợp lệ. Đây là lỗi contract hoặc lỗi phát event có thể gây mất dữ liệu.

Có thể lưu payload hash cùng bản ghi inbox. Khi gặp khóa đã tồn tại:

- Hash giống nhau: nhiều khả năng là duplicate delivery của cùng payload.
- Hash khác nhau: ghi nhận identity collision hoặc producer contract violation; cách ly message và cảnh báo.

Hash nên được tính trên representation ổn định hoặc trên các field contract đã chuẩn hóa. Không so sánh chuỗi JSON nguyên văn nếu serializer có thể đổi thứ tự property hoặc khoảng trắng. Nếu cần canonical representation, quy định thuật toán chuẩn hóa và version rõ ràng.

Không ghi toàn bộ payload nhạy cảm vào store chỉ để so sánh. Có thể lưu hash, eventType, schemaVersion và metadata cần điều tra; giới hạn quyền truy cập và retention.

## 14. Ordering và deduplication

Deduplication không bảo đảm event được xử lý đúng thứ tự. Consumer có thể nhận event E2 trước E1; store sẽ nhận diện cả hai là message mới vì eventId khác nhau. Nếu nghiệp vụ phụ thuộc thứ tự, cần thêm sequence/version theo aggregate và quy tắc áp dụng.

Ví dụ Order có version 10 phát OrderAddressChanged và version 11 phát OrderShipped. Nếu consumer nhận version 11 trước, nó có thể cập nhật projection rồi sau đó áp dụng version 10 và làm trạng thái quay lùi. Consumer nên kiểm tra version, lưu event đến sớm hoặc chỉ áp dụng trạng thái mới hơn theo semantics của event.

Có thể dùng các trường:

- aggregateId: đối tượng nghiệp vụ liên quan;
- aggregateVersion: phiên bản sau khi event phát sinh;
- eventId: định danh duy nhất của event;
- occurredAt: thời điểm nghiệp vụ xảy ra;
- correlationId: liên kết quy trình.

Nếu event là delta cần áp dụng tuần tự, hãy lưu sequence đã xử lý và chỉ áp dụng event kế tiếp khi version phù hợp. Nếu event là snapshot trạng thái, có thể bỏ qua version cũ theo quy tắc rõ ràng. Không dùng timestamp đơn lẻ làm thứ tự tuyệt đối khi có clock skew hoặc nhiều producer.

## 15. Quan sát và vận hành deduplication store

Dedup store cần có telemetry để phát hiện duplicate bình thường, lỗi identity và backlog xử lý.

Metrics nên gồm:

- Tổng số event được nhận theo consumer và eventType.
- Số insert inbox thành công.
- Số duplicate bị bỏ qua.
- Số identity collision do cùng ID nhưng payload khác.
- Số bản ghi PROCESSING quá lease.
- Số retryable failure và manual review.
- Tuổi bản ghi chưa hoàn tất lâu nhất.
- Thời gian xử lý event và thời gian lưu inbox.
- Số bản ghi được archive/purge.

Không dùng eventId, orderId hoặc customerId làm metric tag vì cardinality cao. Dùng các định danh đó trong structured log và trace. Log nên ghi consumerName, eventSource, eventId, eventType, outcome, attempt và correlationId; tránh ghi payload hoặc secret.

Một dashboard có thể hiển thị tỷ lệ duplicate theo consumer, số claim hết lease, số identity collision và tuổi backlog. Tỷ lệ duplicate tăng đột biến có thể phản ánh broker redelivery, ACK bị mất, retry policy hoặc consumer restart thường xuyên. Duplicate tự nó không nhất thiết là lỗi; identity collision hoặc tác dụng phụ bị lặp mới cần điều tra ngay.

## 16. Kiểm thử deduplication store

Kiểm thử phải xác minh cả store và tác dụng nghiệp vụ. Chỉ kiểm tra repository trả về “đã tồn tại” chưa chứng minh rằng hai lần giao không tạo ra tác dụng phụ trùng.

Các kịch bản cần có:

1. **First delivery:** event mới được insert vào inbox và tác dụng nghiệp vụ được commit.
2. **Duplicate delivery:** cùng consumer/source/eventId không chạy lại tác dụng phụ.
3. **Different consumer:** cùng event được xử lý độc lập bởi hai consumer khác nhau.
4. **Concurrent duplicate:** hai instance cùng nhận một event nhưng chỉ một transaction thực hiện tác dụng nghiệp vụ.
5. **Rollback:** nếu cập nhật nghiệp vụ thất bại, inbox claim cũng rollback để lần retry có thể xử lý lại.
6. **Crash after commit before ACK:** broker redelivery không lặp tác dụng phụ.
7. **Retryable failure:** event có thể được thử lại theo chính sách mà không bị đánh dấu hoàn tất quá sớm.
8. **Expired lease:** worker chết khi PROCESSING và worker khác có thể tiếp quản an toàn.
9. **Payload mismatch:** cùng event identity nhưng payload khác được cách ly và cảnh báo.
10. **Retention:** bản ghi không bị xóa trước khi hết retry/replay horizon.
11. **Replay:** consumer rebuild có identity/version riêng và không kích hoạt tác dụng phụ ngoài ý muốn.
12. **External side effect:** API ngoài nhận cùng idempotency key qua các lần thử hoặc được reconciliation trước khi gửi lại.
13. **Ordering:** event cũ không làm trạng thái aggregate quay lùi.
14. **Multi-tenant:** cùng eventId ở hai source hoặc tenant độc lập không bị dedup nhầm nếu contract cho phép.

Với Spring Modulith, nên kiểm thử listener và transaction trong cấu hình thực tế, bao gồm publication được resubmit. Kiểm thử concurrency cần dùng database thật hoặc môi trường tích hợp phù hợp để xác minh unique constraint và transaction isolation. Mock một repository đơn lẻ không chứng minh được hành vi khi hai consumer chạy đồng thời.

## 17. Quy trình triển khai deduplication store

Khi thêm deduplication cho một consumer, hãy thực hiện theo thứ tự:

1. Xác định tác dụng phụ cần bảo vệ và module sở hữu dữ liệu.
2. Chốt event identity: source, eventId, consumer scope và tenant nếu cần.
3. Tạo inbox table với unique constraint trên khóa identity.
4. Thiết kế insert-if-absent nguyên tử, không dùng exists rồi save làm hàng rào duy nhất.
5. Với xử lý database cục bộ, ghi inbox và thay đổi nghiệp vụ trong cùng transaction.
6. Với xử lý dài hoặc API ngoài, dùng claim/lease, outbox và idempotency key ở hệ thống đích.
7. Xác định retry, poison message, manual review và recovery của PROCESSING.
8. Đặt retention theo retry horizon, broker retention và replay policy.
9. Tách consumer identity/version khi rebuild projection hoặc replay có chủ đích.
10. Bổ sung metrics, log, alert và quy trình reconciliation.
11. Kiểm thử duplicate, concurrency, rollback, crash, retention, replay và side effects.

Deduplication store giúp consumer nhận ra một event đã được xử lý trong phạm vi của nó. Khi event identity ổn định, khóa store phản ánh đúng consumer scope, inbox và tác dụng nghiệp vụ commit nguyên tử, duplicate delivery có thể được ACK an toàn mà không lặp tác dụng phụ. Với các thao tác vượt ra ngoài database, cần kết hợp outbox, idempotency key và reconciliation để bảo vệ toàn bộ quy trình. Đây là nền tảng để application events trong Spring Modulith tiếp tục đáng tin cậy khi retry, redelivery, restart và replay xảy ra.

