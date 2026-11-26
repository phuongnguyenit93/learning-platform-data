# Event identifier

## Event identifier là gì?

Event identifier (event ID) là định danh duy nhất của một lần phát sinh sự kiện nghiệp vụ. Nó giúp producer, broker, consumer và hệ thống vận hành nhận diện cùng một sự kiện xuyên suốt quá trình ghi nhận, truyền đi, retry, replay và xử lý.

Ví dụ, khi đơn hàng được xác nhận, module Orders phát OrderConfirmed với event ID là một UUID. Nếu message được gửi lại vì producer không nhận được xác nhận từ broker, lần gửi lại vẫn mang cùng event ID. Consumer có thể nhận ra đây là cùng một sự kiện và tránh áp dụng tác động nghiệp vụ lần thứ hai.

Event ID nhận diện **sự kiện đã xảy ra**, không nhận diện riêng một lần truyền message. Một sự kiện có thể được gửi nhiều lần, xuất hiện ở nhiều consumer hoặc được replay sau nhiều ngày nhưng vẫn giữ cùng event ID.

~~~mermaid
flowchart LR
    A[Business transaction] --> B[Create event with stable event ID]
    B --> C[Persist event / publication]
    C --> D[Publish attempt 1]
    C --> E[Publish retry]
    D --> F[Consumer]
    E --> F
    F --> G{Event ID already processed?}
    G -->|Yes| H[Skip duplicate effect]
    G -->|No| I[Apply effect and record ID atomically]
~~~

Nếu mỗi lần retry lại tạo một ID mới, consumer không thể nhận ra các lần gửi đó cùng đại diện cho một sự kiện. Vì vậy, event ID phải được tạo một lần tại thời điểm tạo sự kiện và được giữ nguyên trong mọi lần gửi lại.

## Phân biệt event ID với các định danh khác

Một message có thể mang nhiều loại ID. Mỗi loại trả lời một câu hỏi khác nhau:

| Định danh | Câu hỏi | Ví dụ |
|---|---|---|
| Event ID | Đây là sự kiện cụ thể nào? | Một lần OrderConfirmed |
| Message/record ID | Đây là bản ghi hoặc lần gửi nào trong hạ tầng? | Kafka topic-partition-offset hoặc ID do broker cấp |
| Aggregate ID | Sự kiện thuộc thực thể nghiệp vụ nào? | orderId |
| Aggregate version | Đây là trạng thái thứ mấy của aggregate? | orderVersion = 12 |
| Correlation ID | Sự kiện thuộc luồng yêu cầu hoặc quy trình nào? | Một checkout workflow |
| Causation ID | Hành động hoặc message nào gây ra sự kiện này? | ID của command hoặc event trước |
| Command/request ID | Đây là yêu cầu thay đổi nghiệp vụ nào? | Một lần client gửi ConfirmOrder |
| Publication ID | Registry đang theo dõi lần giao event tới listener nào? | Bản ghi publication nội bộ |

Không dùng các ID này thay thế cho nhau:

- Hai event khác nhau của cùng một đơn hàng có cùng aggregate ID nhưng phải có event ID riêng.
- Một event có thể được gửi nhiều lần và có nhiều broker offset khác nhau nhưng vẫn giữ một event ID.
- Correlation ID có thể được chia sẻ bởi nhiều event trong cùng workflow.
- Aggregate version biểu diễn thứ tự nghiệp vụ; event ID không tự cho biết event nào mới hơn.
- Event Publication Registry của Spring Modulith theo dõi publication cho listener. ID nội bộ của bản ghi registry không mặc nhiên là event ID nghiệp vụ.

Một event có thể được chuyển qua nhiều broker hoặc adapter. Event ID nên nằm trong hợp đồng dữ liệu hoặc metadata được truyền nhất quán để consumer ở các công nghệ khác nhau vẫn nhận diện được cùng sự kiện.

## Tạo event ID ở đâu?

Tạo event ID tại nơi hình thành sự kiện nghiệp vụ, sau khi ứng dụng xác định được sự kiện nào thực sự xảy ra. ID cần được tạo đúng một lần và lưu cùng event hoặc bản ghi outbox/publication trước khi bắt đầu gửi.

Ví dụ với Java record:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    long aggregateVersion,
    Instant occurredAt
) {
    public static OrderConfirmed create(
            UUID orderId,
            long aggregateVersion,
            Instant occurredAt) {
        return new OrderConfirmed(
            UUID.randomUUID(),
            orderId,
            aggregateVersion,
            occurredAt
        );
    }
}
~~~

Publisher phát event trong transaction nghiệp vụ:

~~~java
@Service
@RequiredArgsConstructor
public class OrderConfirmationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm();

        events.publishEvent(OrderConfirmed.create(
            order.getId(),
            order.getVersion(),
            clock.instant()
        ));
    }
}
~~~

Trong ví dụ, UUID được tạo một lần khi tạo OrderConfirmed. Nếu event được lưu bền vững hoặc publication được gửi lại, payload phải giữ nguyên event ID đó.

Không tạo event ID trong listener hoặc ở mỗi lần gọi KafkaTemplate.send. Những vị trí đó có thể được thực thi lại và vô tình tạo ID khác cho cùng một sự kiện.

Nếu một transaction tạo ra nhiều sự kiện nghiệp vụ khác nhau, mỗi sự kiện cần event ID riêng, kể cả khi chúng cùng aggregate và cùng correlation ID.

## Chọn định dạng ID

Định dạng ID nên đáp ứng phạm vi duy nhất, khả năng truyền qua nhiều hệ thống và chi phí lưu trữ.

| Cách tạo | Đặc điểm | Khi cân nhắc |
|---|---|---|
| UUID v4 | Ngẫu nhiên, dễ tạo độc lập, không cần bộ cấp phát tập trung | Lựa chọn phổ biến cho event ID |
| UUID v7 | Có thành phần thời gian, hỗ trợ sắp xếp gần theo thời điểm tạo | Khi cần locality hoặc quan sát theo thứ tự gần đúng và thư viện hỗ trợ |
| ULID | Định dạng sortable theo thời gian, có thể biểu diễn dạng chuỗi | Khi hệ thống đã chuẩn hóa ULID |
| Sequence tập trung | Tăng đơn điệu theo bộ cấp phát | Khi cần thứ tự toàn cục và chấp nhận phụ thuộc bộ cấp phát |

Với UUID v4, xác suất va chạm rất thấp trong phạm vi sử dụng thông thường, nhưng vẫn nên đặt unique constraint ở nơi lưu event ID để phát hiện lỗi dữ liệu hoặc bug tạo ID.

ID có thành phần thời gian như UUID v7 hoặc ULID có thể sắp xếp gần đúng theo thời điểm tạo, nhưng không thay thế aggregate version hay sequence nghiệp vụ. Clock lệch và sự kiện đồng thời vẫn có thể khiến thứ tự ID không phản ánh quan hệ nhân quả.

Tránh dùng số thứ tự tăng toàn cục chỉ để lấy event ID nếu nó tạo thêm điểm nghẽn hoặc yêu cầu một dịch vụ cấp số tập trung không cần thiết.

## Phạm vi duy nhất và quy tắc bất biến

Trước khi chọn định dạng, cần xác định event ID duy nhất trong phạm vi nào:

- Toàn bộ hệ thống.
- Một tenant.
- Một producer hoặc bounded context.
- Một loại event.
- Một aggregate.

Nếu ID chỉ duy nhất trong phạm vi producer hoặc tenant, khóa deduplication phải bao gồm namespace tương ứng. Ví dụ, có thể dùng cặp producerId + eventId hoặc tenantId + eventId.

Với hệ thống có nhiều producer, UUID ngẫu nhiên thường giúp tạo ID độc lập mà không cần phối hợp. Nếu dùng ID cục bộ như 000123, cần ghép namespace ổn định để tránh hai producer cùng tạo một ID.

Event ID phải bất biến sau khi event được tạo. Không đổi ID khi:

- Gửi lại do timeout.
- Retry sau lỗi broker.
- Chuyển qua retry topic.
- Replay từ dead-letter topic.
- Deserialize rồi serialize lại.
- Chuyển payload qua adapter hoặc integration.

Nếu nội dung nghiệp vụ cần sửa, hãy tạo một sự kiện mới với event ID mới và tham chiếu tới sự kiện cũ qua causationId, supersedesEventId hoặc metadata phù hợp. Không thay payload của một event đã công bố nhưng giữ nguyên ID, vì consumer có thể đã xử lý phiên bản nội dung trước đó.

## Lưu event ID cùng dữ liệu bền vững

Khi hệ thống dùng transactional outbox, event ID nên được lưu trong cùng bản ghi với payload. Unique constraint giúp bảo vệ tính duy nhất trong phạm vi được chọn.

Ví dụ schema khái niệm:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Publisher tạo event và ghi outbox trong cùng transaction với thay đổi nghiệp vụ. Relay có thể gửi lại bản ghi chưa publish sau timeout hoặc restart mà không tạo event ID mới.

Nếu dùng Event Publication Registry của Spring Modulith, registry theo dõi publication của application event tới các listener được quản lý. Hãy giữ event ID nghiệp vụ trong chính payload hoặc metadata hợp đồng và xác nhận adapter có truyền nó sang message broker theo cách nào. Không giả định mọi adapter tự động đặt field eventId thành Kafka header có tên cụ thể.

## Truyền event ID qua broker

Event ID cần tồn tại ở phía consumer sau serialization. Có hai cách thường gặp:

- Đặt event ID trong payload/envelope.
- Đặt event ID trong message header hoặc metadata của broker.

Một envelope minh họa:

~~~json
{
  "eventId": "9f8d8c24-5d75-4a93-8c3b-9d0f7b6b1f12",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "aggregateId": "b6d2dca1-2d88-4e7b-8d12-7d6e4e7c8f30",
  "aggregateVersion": 12,
  "occurredAt": "2026-11-25T10:15:30Z",
  "correlationId": "checkout-7a4c",
  "payload": {
    "orderNumber": "ORD-2026-0042"
  }
}
~~~

Envelope là ví dụ về hợp đồng do ứng dụng thiết kế, không phải cấu trúc mặc định của Spring Modulith hay Kafka. Nếu dùng cả payload và header, quy định một nguồn chuẩn và kiểm tra chúng khớp nhau.

Header hữu ích khi broker hoặc middleware cần định tuyến, trace hay quan sát mà không deserialize payload. Payload hữu ích vì event ID vẫn tồn tại khi message được export, lưu file hoặc chuyển sang một transport khác.

Không đặt event ID vào Kafka key chỉ vì cần deduplication. Kafka key thường phục vụ partitioning và ordering theo key; event ID duy nhất cho mỗi event sẽ phân tán các event của cùng aggregate sang các partition khác nhau. Nếu cần giữ event cùng aggregate trên một partition, dùng aggregate ID làm Kafka key và giữ event ID riêng trong payload/header.

## Event ID và idempotency ở consumer

At-least-once delivery cho phép broker hoặc adapter giao lại message khi không chắc lần xử lý trước đã hoàn tất. Vì vậy consumer cần nhận diện một event đã xử lý.

Một bảng processed_event có thể lưu định danh event theo từng consumer:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khóa gồm consumer_name và event_id vì nhiều consumer độc lập có thể cần xử lý cùng một event. Fulfillment và Notification đều được phép xử lý OrderConfirmed một lần theo trạng thái riêng của mỗi consumer.

Nếu một consumer có nhiều projection handler với vòng đời độc lập, hãy chọn tên consumer hoặc handler scope đủ cụ thể để mỗi luồng xử lý có khóa deduplication riêng.

### Ghi nhận ID và thay đổi nghiệp vụ trong cùng transaction

Để tránh race condition, không chỉ kiểm tra existsByEventId() rồi mới xử lý. Hai instance có thể cùng kiểm tra thấy chưa tồn tại và cùng thực hiện tác động. Cần dùng unique constraint hoặc thao tác insert nguyên tử để giành quyền xử lý, rồi ghi nhận ID và thay đổi read/write model trong cùng transaction.

Ví dụ dưới đây dùng cú pháp PostgreSQL:

~~~java
@Transactional
public void on(OrderConfirmed event) {
    int inserted = jdbcTemplate.update("""
        INSERT INTO processed_event (
            consumer_name,
            event_id,
            processed_at
        )
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT DO NOTHING
        """,
        "fulfillment-order-confirmed",
        event.eventId()
    );

    if (inserted == 0) {
        return; // Event này đã được consumer xử lý.
    }

    shipmentRepository.prepareShipment(
        event.orderId(),
        event.aggregateVersion()
    );
}
~~~

Nếu insert thành công, consumer tiếp tục cập nhật nghiệp vụ. Nếu cập nhật thất bại và transaction rollback, bản ghi processed_event cũng rollback, cho phép lần giao lại thử xử lý. Nếu event đã được xử lý và transaction trước đã commit, unique constraint ngăn lần giao trùng áp dụng tác động lần nữa.

Đoạn SQL là ví dụ cho PostgreSQL. Với database khác, dùng insert-if-absent, upsert hoặc cơ chế claim tương đương có unique constraint. Không bắt duplicate key exception rồi tiếp tục trong cùng transaction nếu database/ORM đã đánh dấu transaction rollback-only.

Không ghi processed_event trong một transaction độc lập trước khi cập nhật nghiệp vụ. Nếu tiến trình dừng sau khi đánh dấu nhưng trước khi thay đổi read model, lần giao lại sẽ bị bỏ qua và dữ liệu không bao giờ được cập nhật.

## Khi consumer gọi hệ thống bên ngoài

Transaction database của consumer không thể bao trùm nguyên tử một HTTP API hoặc một hệ thống ngoài không tham gia cùng transaction.

Ví dụ listener thực hiện:

1. Ghi event ID đã xử lý vào database.
2. Gọi API tạo shipment.
3. Đánh dấu hoàn tất.

Nếu API tạo shipment thành công nhưng tiến trình dừng trước khi ghi trạng thái hoàn tất, lần retry có thể gọi API lần nữa. Ngược lại, nếu ghi processed_event trước rồi API thất bại, consumer có thể bỏ qua event và không bao giờ thử lại.

Các cách xử lý:

- Truyền event ID hoặc idempotency key ổn định tới API đích nếu API hỗ trợ.
- Ghi một command/outbox cho tác vụ ngoài trong cùng transaction với processed_event.
- Dùng workflow state machine để lưu trạng thái PENDING, IN_PROGRESS, SUCCEEDED và FAILED.
- Đặt unique business key ở hệ thống đích, ví dụ một shipment chỉ được tạo một lần cho order ID.
- Dùng retry có giới hạn và quy trình đối soát để xử lý trạng thái không chắc chắn.

Event ID giúp các lần thử nhận diện cùng một sự kiện, nhưng hệ thống đích vẫn cần cơ chế chống trùng nếu tác động nằm ngoài transaction của consumer.

## Event ID không thay thế aggregate version

Event ID trả lời “đây là sự kiện nào”; aggregate version trả lời “sự kiện thuộc phiên bản nghiệp vụ nào”.

Ví dụ:

| Event ID | Aggregate ID | Version | Ý nghĩa |
|---|---|---:|---|
| E-101 | ORDER-42 | 10 | OrderPlaced |
| E-102 | ORDER-42 | 11 | OrderConfirmed |
| E-103 | ORDER-42 | 12 | OrderCancelled |

Các event có ID riêng nhưng cùng aggregate. Nếu E-103 được xử lý trước E-102, consumer không thể dùng event ID để biết trạng thái nào mới hơn. Cần version hoặc sequence để phát hiện event cũ, event đến sai thứ tự hoặc bị thiếu.

Một projection snapshot có thể chỉ áp dụng event khi version lớn hơn version hiện tại. Một projection incremental có thể cần yêu cầu version kế tiếp để tránh bỏ qua delta. Quy tắc cụ thể phụ thuộc semantics của event.

Không sắp xếp event theo UUID ngẫu nhiên rồi coi đó là thứ tự nghiệp vụ.

## Phân biệt retry, replay và event mới

Các thao tác này có quy tắc event ID khác nhau:

| Tình huống | Event ID |
|---|---|
| Producer gửi lại vì không nhận được broker acknowledgement | Giữ nguyên |
| Consumer nhận lại cùng record sau lỗi | Giữ nguyên |
| Replay record từ DLT sau khi sửa consumer | Giữ nguyên |
| Rebuild projection bằng event history | Giữ nguyên ID của từng event gốc |
| Phát sự kiện nghiệp vụ mới do hành động mới | Tạo ID mới |
| Phát correction event thay cho một sự kiện sai trước đó | Tạo ID mới và tham chiếu event được sửa |
| Gửi lại cùng một command request do client timeout | Dùng command/request idempotency key ổn định; event ID được tạo theo kết quả nghiệp vụ đã ghi |

Một lần replay không phải là một sự kiện nghiệp vụ mới. Có thể thêm replayAttemptId, replayedAt hoặc operator metadata để quan sát lần phát lại mà không thay event ID gốc.

Nếu client gửi lại command sau timeout, command ID giúp server nhận ra cùng một yêu cầu. Một command có thể tạo không hoặc nhiều event; do đó command ID và event ID có vòng đời khác nhau.

## Phát hiện ID bị trùng nhưng payload khác nhau

Cùng event ID nhưng payload khác nhau là dấu hiệu nghiêm trọng: producer có thể tái sử dụng ID sai, dữ liệu bị thay đổi sau khi phát hoặc adapter làm sai nội dung.

Có thể lưu thêm hash của payload đã chuẩn hóa:

- Khi event ID đã tồn tại và hash giống nhau, đó có thể là lần giao trùng hợp lệ.
- Khi event ID đã tồn tại nhưng hash khác, ghi nhận integrity error và đưa vào luồng điều tra.
- Không âm thầm ghi đè payload cũ bằng payload mới có cùng ID.

Hash chỉ hữu ích nếu serialization và canonicalization ổn định. Hai JSON có thứ tự field khác nhau có thể biểu diễn cùng dữ liệu nhưng tạo hash khác nếu hash trực tiếp byte thô. Hãy chuẩn hóa schema/payload trước khi hash hoặc so sánh các field có ý nghĩa.

Không dùng hash payload làm event ID một cách mặc định. Hai sự kiện nghiệp vụ độc lập có thể có payload giống hệt nhau nhưng vẫn là hai lần xảy ra khác nhau.

## Retention của processed event

Bản ghi processed_event phải được giữ đủ lâu để bao phủ khoảng thời gian message có thể được giao lại hoặc replay.

Khi quyết định retention, xem xét:

- Retention của Kafka topic và retry/DLT topic.
- Thời gian consumer có thể ngừng hoạt động.
- Khoảng thời gian vận hành cho phép replay.
- Chính sách backfill hoặc rebuild projection.
- Yêu cầu audit và lưu trữ dữ liệu.
- Khả năng xóa hoặc archive processed event mà vẫn giữ invariant chống trùng.

Nếu xóa processed_event sau 7 ngày nhưng DLT cho phép replay sau 30 ngày, event cũ có thể được áp dụng lại. Với nghiệp vụ tài chính hoặc tác động không thể đảo ngược, có thể cần giữ khóa deduplication lâu hơn hoặc dựa thêm vào unique business constraint.

Bảng deduplication có thể tăng lớn. Có thể phân vùng theo thời gian, archive hoặc lưu compact key theo chính sách. Không xóa dữ liệu chỉ dựa trên tuổi mà chưa tính đến mọi đường replay.

## Event ID trong Spring Modulith

Trong Spring Modulith, application event được phát qua ApplicationEventPublisher và có thể được các listener nội bộ hoặc externalization adapter xử lý. Nếu ứng dụng cần idempotency xuyên qua nhiều listener hoặc broker, event contract nên mang event ID ổn định.

Event Publication Registry theo dõi publication theo listener và trạng thái hoàn tất. Registry có thể lưu một publication record riêng cho từng listener; publication record đó phục vụ quản lý vòng đời giao event. Event ID trong payload vẫn là định danh nghiệp vụ dùng chung cho các consumer và hệ thống ngoài.

Với @ApplicationModuleListener, listener có thể được gọi lại theo cơ chế phục hồi/resubmission tùy cấu hình. Giữ event ID trong event để listener nhận diện cùng một lần phát khi xử lý lại.

Khi externalize event ra Kafka, RabbitMQ hoặc hệ thống khác, xác nhận adapter serialize event ID vào payload hoặc truyền qua header theo hợp đồng đã thống nhất. Nếu consumer chuyển đổi envelope, cần giữ event ID qua mọi bước mapping.

## Bảo mật và quyền riêng tư

Event ID thường không phải bí mật và không nên được dùng làm cơ chế xác thực hoặc phân quyền. Biết event ID không được phép giúp người dùng truy cập payload hay trạng thái nghiệp vụ.

Tuy vậy, event ID có thể xuất hiện trong log, trace, dashboard, URL hoặc công cụ hỗ trợ. Cần tránh nhúng dữ liệu cá nhân, số tài khoản, email hoặc thông tin nhạy cảm vào ID. Dùng UUID ngẫu nhiên hoặc định danh opaque thay vì ID có ý nghĩa chứa dữ liệu.

Giới hạn quyền đọc event payload và bảng deduplication theo vai trò. Không ghi toàn bộ payload nhạy cảm chỉ để phục vụ điều tra trùng lặp; event ID, event type, consumer và kết quả xử lý thường đã đủ để truy vết.

## Kiểm thử event identifier và idempotency

Các test nên xác nhận ID được tạo, truyền và sử dụng đúng qua toàn bộ vòng đời:

| Tình huống | Điều cần xác nhận |
|---|---|
| Tạo event mới | Có event ID không rỗng và duy nhất theo phạm vi |
| Cùng command tạo hai event khác nhau | Mỗi event có ID riêng |
| Retry publish | Event ID không đổi |
| Retry consumer | Processed-event constraint ngăn tác động trùng |
| Hai consumer độc lập | Mỗi consumer có thể xử lý cùng event một lần |
| Hai instance nhận đồng thời | Chỉ một transaction giành được khóa deduplication |
| Consumer rollback | Processed record rollback cùng thay đổi nghiệp vụ |
| Replay từ DLT | Giữ event ID gốc và thêm metadata replay riêng |
| Cùng ID, payload khác | Phát hiện integrity error |
| Event đến sai thứ tự | Aggregate version xử lý ordering độc lập với event ID |
| Retention hết hạn | Chính sách replay không làm phát sinh tác động trùng |
| Command gửi lại sau timeout | Command idempotency ngăn tạo nghiệp vụ/event trùng ngoài ý muốn |

Integration test nên dùng database thực tế hoặc container tương đương để kiểm tra unique constraint và transaction. Mock repository không chứng minh hai consumer đồng thời không thể cùng xử lý một event.

Với test concurrency, chạy hai transaction cạnh tranh trên cùng event ID và xác nhận chỉ một transaction áp dụng tác động. Đồng thời kiểm tra trường hợp transaction thắng bị rollback để lần thử sau có thể xử lý thành công.

## Quan sát event ID trong production

Event ID là khóa nối log và trace giữa publisher, broker và consumer. Nên ghi nhận:

- Event ID.
- Event type và schema version.
- Producer/module phát event.
- Aggregate ID và aggregate version.
- Correlation ID và causation ID nếu có.
- Consumer hoặc handler name.
- Kết quả: processed, duplicate skipped, retrying hoặc failed.
- Broker topic/partition/offset khi có.
- Thời điểm phát, nhận và xử lý.

Dùng event ID trong log và trace, nhưng tránh làm metric label vì số lượng ID gần như không giới hạn và gây cardinality cao. Metric nên nhóm theo event type, producer, consumer, kết quả và lỗi.

Các chỉ số hữu ích gồm:

- Tỷ lệ event bị nhận trùng.
- Số duplicate bị bỏ qua.
- Số xung đột event ID với payload khác.
- Số lỗi unique constraint ngoài dự kiến.
- Tuổi publication chưa hoàn tất.
- Tỷ lệ event được xử lý thành công sau retry.
- Số record processed_event và dung lượng lưu trữ.

Khi điều tra một nghiệp vụ, tìm event ID từ log publisher rồi lần theo cùng ID qua registry, broker metadata và consumer logs. Nếu mỗi adapter tự thay event ID hoặc không truyền ID, trace sẽ bị đứt; cần chuẩn hóa hợp đồng metadata.

## Quy trình thiết kế event ID

Khi tạo event contract mới, hãy xác định:

1. Event ID duy nhất trong phạm vi nào: toàn hệ thống, tenant hay producer?
2. Định dạng nào phù hợp: UUID v4, UUID v7, ULID hay sequence?
3. ID được tạo tại thời điểm nào và lưu bền vững cùng event ở đâu?
4. Retry, replay và chuyển qua adapter có giữ nguyên ID không?
5. Consumer deduplication dùng khóa nào và unique constraint nào?
6. Ghi nhận event ID và thay đổi nghiệp vụ có cùng transaction không?
7. Nếu gọi hệ thống ngoài, idempotency key được truyền tới đâu?
8. Retention của processed event có bao phủ mọi khoảng replay không?
9. Log, trace và dashboard có thể nối các chặng bằng event ID không?

Event identifier là nền tảng để nhận diện một sự kiện qua nhiều lần truyền và xử lý. Khi ID được tạo một lần, lưu bền vững, giữ nguyên qua retry/replay và kết hợp với deduplication nguyên tử ở consumer, hệ thống có thể xử lý giao nhận at-least-once mà tránh lặp tác động nghiệp vụ.

## Tài liệu tham khảo

- Spring Modulith Reference — Application Events and Event Publication Registry: https://docs.spring.io/spring-modulith/reference/events.html
- Apache Kafka Documentation — Message Delivery Semantics: https://kafka.apache.org/documentation/#semantics
- RFC 9562 — Universally Unique IDentifiers (UUIDs): https://www.rfc-editor.org/rfc/rfc9562
- PostgreSQL Documentation — INSERT and ON CONFLICT: https://www.postgresql.org/docs/current/sql-insert.html
