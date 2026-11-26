# Lạm dụng broker

## Broker không phải lựa chọn mặc định cho mọi giao tiếp

Message broker như Kafka hoặc RabbitMQ giải quyết những vấn đề quan trọng: giao tiếp bất đồng bộ giữa các tiến trình, đệm tải, phân phối message, tách vòng đời producer và consumer, lưu giữ message theo policy, retry và fan-out. Nhưng broker cũng đưa thêm một hệ thống phân tán vào kiến trúc: network, authentication, topology, schema, vận hành cluster, quan sát, xử lý duplicate, ordering, replay và khôi phục sự cố.

Lạm dụng broker xảy ra khi ứng dụng đưa message qua hạ tầng phân tán dù bài toán không cần các đặc tính đó, hoặc dùng broker để thay thế một cơ chế phù hợp hơn như lời gọi module API, application event nội bộ, transaction database hay một workflow rõ ràng.

Trong Spring Modulith, các module thường cùng chạy trong một ứng dụng. Nếu Orders cần gọi một capability của Inventory trong cùng tiến trình, việc gửi message qua Kafka chỉ để hai module trao đổi có thể biến một lời gọi nội bộ thành một quy trình phân tán. Một application event nội bộ hoặc module API có thể giải quyết vấn đề với ít điểm lỗi và dễ kiểm thử hơn.

Nguyên tắc thiết kế là chọn cơ chế giao tiếp theo ranh giới và yêu cầu thực tế. Dùng broker khi cần giao tiếp qua tiến trình hoặc tổ chức, xử lý bất đồng bộ bền vững, đệm tải hoặc phân phối độc lập. Không đưa broker vào chỉ vì hệ thống đang theo kiến trúc event-driven.

~~~mermaid
flowchart TD
    A[Need to communicate] --> B{Same application process?}
    B -->|Yes| C{Need a response now?}
    C -->|Yes| D[Call the module public API]
    C -->|No| E[Publish an internal application event]
    B -->|No| F{Need durable asynchronous delivery or buffering?}
    F -->|No| G[Consider HTTP or another direct integration]
    F -->|Yes| H[Use a broker with explicit contract and operations]
~~~

## Nhận diện các dấu hiệu lạm dụng broker

Một số dấu hiệu thường gặp:

- Mọi lời gọi giữa hai module đều phải đi qua broker, kể cả khi chúng nằm trong cùng ApplicationContext.
- Một consumer gửi message và chờ response chỉ để mô phỏng lời gọi hàm đồng bộ.
- Mỗi method hoặc mỗi thay đổi nhỏ tạo một topic/queue riêng mà không có yêu cầu routing hay lifecycle riêng.
- Broker được dùng làm database chính, nơi ứng dụng truy vấn trạng thái hiện tại của entity.
- Producer phát toàn bộ entity hoặc object graph để consumer tự chọn dữ liệu.
- Thiết kế giả định message chỉ được giao đúng một lần và không có idempotency.
- Ứng dụng phụ thuộc vào thứ tự toàn cục giữa các partition, queue hoặc consumer.
- Retry vô hạn khiến poison message liên tục quay lại queue.
- Một thay đổi database và một lần publish broker được thực hiện độc lập mà không có cơ chế bảo vệ dual-write.
- Đội phát triển phải vận hành nhiều broker hoặc nhiều cluster chỉ để đáp ứng các luồng nội bộ đơn giản.
- Không ai sở hữu schema, retention, ACL, DLQ, replay và quy trình xử lý sự cố.

Một dấu hiệu riêng lẻ chưa đủ kết luận kiến trúc sai. Ví dụ, cùng một ứng dụng có thể cần broker để gửi event sang hệ thống thanh toán độc lập. Cần xem mục tiêu, ranh giới, tải và yêu cầu phục hồi của từng luồng.

## Dùng broker cho giao tiếp nội bộ cùng tiến trình

Đây là trường hợp phổ biến trong modular monolith. Orders, Inventory, Billing và Shipping là các module khác nhau nhưng cùng chạy trong một ứng dụng Spring Modulith. Chúng có thể giao tiếp qua public API hoặc application event mà không cần đưa message qua network.

Ví dụ, Orders xác nhận đơn hàng và công bố OrderConfirmed:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}

@Service
@RequiredArgsConstructor
class OrderConfirmationService {

    private final ApplicationEventPublisher events;

    @Transactional
    public void confirm(UUID orderId) {
        // Kiểm tra và cập nhật trạng thái đơn hàng.
        events.publishEvent(new OrderConfirmed(
            UUID.randomUUID(),
            orderId,
            Instant.now()
        ));
    }
}
~~~

Một listener nội bộ có thể xử lý event theo ranh giới module:

~~~java
@Component
class OrderSummaryListener {

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        // Cập nhật read model thuộc module sở hữu listener.
    }
}
~~~

Ví dụ minh họa cách tổ chức event nội bộ. Hãy dùng Clock được inject thay vì Instant.now() trực tiếp nếu cần kiểm thử thời gian xác định. Cấu hình listener và transaction cần tuân theo phiên bản Spring Modulith của dự án.

Application event nội bộ phù hợp khi các module cùng tiến trình và cần giảm phụ thuộc trực tiếp. Module phát event không cần biết listener cụ thể nào sẽ xử lý. Spring Modulith có thể kiểm tra ranh giới module và theo dõi publication cho các listener được quản lý.

Nếu một module cần kết quả ngay để tiếp tục quyết định nghiệp vụ, public API thường rõ ràng hơn event bất đồng bộ. Không biến một truy vấn hoặc command đồng bộ thành message rồi chờ phản hồi nếu không có yêu cầu phân tán thực sự.

## Phân biệt module API, application event và broker

Ba cơ chế có vai trò khác nhau:

| Cơ chế | Dùng khi | Đặc tính |
|---|---|---|
| Module public API | Module gọi capability hoặc cần kết quả ngay | Lời gọi trong cùng tiến trình, dễ theo dõi luồng điều khiển |
| Application event nội bộ | Một module công bố sự kiện để listener trong ứng dụng phản ứng độc lập | Giảm phụ thuộc trực tiếp, không nhất thiết đi qua network |
| Message broker | Producer và consumer ở các tiến trình/hệ thống khác nhau hoặc cần buffering/durable asynchronous delivery | Có network, topology, delivery semantics và chi phí vận hành riêng |

Không dùng event để che giấu một dependency đồng bộ. Nếu Orders không thể xác nhận đơn hàng khi Inventory chưa giữ được hàng, một lời gọi module API hoặc một workflow có trạng thái có thể diễn đạt dependency tốt hơn việc phát event rồi giả định Inventory đã xử lý xong.

Ngược lại, nếu Notification chỉ cần phản ứng sau khi đơn hàng đã xác nhận, event nội bộ là phù hợp. Nếu Notification chạy ở một service độc lập hoặc cần broker giữ message khi service tạm ngừng, externalization qua broker có thể đáng giá.

## Anti-pattern: biến broker thành RPC

Một luồng RPC qua broker thường có dạng:

1. Service A gửi command message lên queue.
2. Service B nhận command và xử lý.
3. Service B gửi response vào reply queue.
4. Service A chờ correlation ID tương ứng.
5. Timeout dẫn đến retry hoặc gửi lại command.

Cách này tạo nhiều vấn đề nếu mục tiêu chỉ là gọi một API:

- Caller vẫn bị chặn chờ kết quả nhưng phải quản lý timeout, correlation và reply queue.
- Khó xác định request đã được xử lý hay response bị mất.
- Retry có thể thực hiện command nhiều lần.
- Trace và exception propagation phức tạp hơn lời gọi trực tiếp.
- Broker trở thành dependency bắt buộc cho thao tác cần phản hồi ngay.

Dùng request/reply qua broker khi có lý do rõ ràng như kết nối qua network không đồng bộ, client không thể giữ kết nối trực tiếp hoặc cần giao thức message đã chuẩn hóa. Nếu không, dùng HTTP/gRPC giữa tiến trình hoặc module API trong cùng ứng dụng.

Nếu business workflow thực sự bất đồng bộ, hãy mô hình hóa trạng thái như ACCEPTED, PROCESSING, COMPLETED và FAILED. Trả về operation ID cho caller thay vì giả vờ có lời gọi đồng bộ.

## Anti-pattern: phát event cho mọi thao tác nhỏ

Không phải mọi thay đổi nội bộ đều cần trở thành event công khai. Các event quá chi tiết có thể làm lộ cấu trúc triển khai và khiến consumer phụ thuộc vào bước nội bộ.

Ví dụ, một service phát UserNameTrimmed, AddressFieldNormalized và TemporaryFlagRemoved như các event độc lập chỉ vì đó là các bước trong một method. Consumer không cần biết những bước kỹ thuật đó; chúng không đại diện cho sự kiện nghiệp vụ ổn định.

Nên công bố event có ý nghĩa nghiệp vụ như CustomerRegistered hoặc OrderConfirmed khi trạng thái nghiệp vụ đã thay đổi và consumer có lý do phản ứng.

Event contract nên mô tả điều đã xảy ra, không mô tả từng dòng code hoặc từng bước triển khai. Nếu consumer cần một capability, cung cấp API. Nếu cần biết kết quả nghiệp vụ, phát domain/application event ở thời điểm phù hợp.

## Anti-pattern: topic và queue cho từng module hoặc từng event nhỏ

Tạo một topic hoặc queue riêng cho mọi event type có thể làm topology phình to. Mỗi destination cần ACL, retention, monitoring, alert, capacity, naming, cleanup và owner. Nhiều destination nhỏ cũng khiến việc quản lý schema, consumer group và replay khó hơn.

Không có một quy tắc duy nhất rằng mỗi event type phải có một topic hoặc mọi event phải chung một topic. Thiết kế destination dựa trên:

- Nhu cầu retention và replay.
- Số lượng consumer và cách subscription.
- Security boundary và quyền truy cập.
- Throughput, partitioning và ordering.
- Lifecycle và ownership.
- Chính sách retry, DLQ và data classification.

Kafka thường dùng topic cho một luồng record có retention và partitioning; consumer group tạo các subscription độc lập. RabbitMQ thường định tuyến qua exchange tới queue theo binding; queue biểu diễn nơi message chờ một nhóm consumer. Hai mô hình không nên bị ép vào cùng một sơ đồ topology.

Nhóm nhiều event vào cùng destination có thể hợp lý nếu chúng có cùng security, retention, throughput và ownership. Tách destination khi cần cách ly tải, quyền truy cập hoặc lifecycle. Tránh cả hai cực đoan: một destination cho mọi thứ và một destination cho từng chi tiết nhỏ.

## Anti-pattern: dùng broker làm database hoặc source of truth

Broker phục vụ giao nhận message theo semantics của nó. Nó không tự thay thế database nghiệp vụ hoặc API truy vấn trạng thái hiện tại.

Kafka có thể giữ log trong thời gian dài và hỗ trợ replay trong retention, nhưng compaction, retention policy, partitioning và consumer offset có mục đích riêng. RabbitMQ queue chủ yếu giữ message đang chờ xử lý và thường loại message sau acknowledgement. Không nên thiết kế ứng dụng dựa trên giả định mọi message sẽ luôn có thể truy vấn như một bản ghi nghiệp vụ.

Không dùng queue để trả lời câu hỏi “đơn hàng hiện đang ở trạng thái nào?” hoặc “số dư hiện tại là bao nhiêu?”. Hãy truy vấn module sở hữu dữ liệu hoặc read model phù hợp.

Nếu cần lịch sử event lâu dài, audit hoặc event sourcing, thiết kế event store với schema, transaction, retention, query và governance phù hợp. Không coi broker retention là cam kết lưu trữ lịch sử vô hạn.

## Anti-pattern: gửi toàn bộ entity hoặc object graph

Đưa toàn bộ JPA entity, aggregate hoặc dữ liệu liên quan vào message làm tăng coupling và payload size. Consumer có thể bắt đầu phụ thuộc vào field nội bộ không nằm trong contract ổn định. Payload lớn còn tăng serialization, network, broker storage, retry cost và nguy cơ lộ dữ liệu.

Event nên chứa snapshot hoặc dữ liệu tối thiểu cần cho ý nghĩa sự kiện và consumer đã được xác định. Có thể gửi aggregate ID và các thuộc tính cần thiết, nhưng nếu consumer phải gọi producer để lấy dữ liệu thì cần cân nhắc consistency và availability.

Không gửi một object graph chứa lazy proxy, quan hệ vòng hoặc dữ liệu nhạy cảm không cần thiết. Dùng event DTO riêng, versioned schema và field definitions rõ ràng.

Nếu payload lớn thực sự cần thiết, xem xét lưu blob ở object storage và truyền reference có quyền truy cập, checksum, content type và retention rõ ràng. Cần bảo đảm consumer có thể lấy blob trong thời gian xử lý và quyền truy cập được giới hạn.

## Anti-pattern: giả định exactly-once và bỏ qua idempotency

Broker có thể cung cấp các semantics giao nhận khác nhau, nhưng end-to-end exactly-once giữa broker, database và API bên ngoài là một yêu cầu khó. Consumer có thể commit database thành công rồi mất acknowledgement; broker sẽ giao lại message. Producer có thể gửi thành công nhưng không nhận confirm; retry có thể tạo duplicate.

Vì vậy, consumer cần idempotency:

- Event ID ổn định qua retry và replay.
- Unique constraint theo consumer và event ID.
- Ghi nhận processed event cùng transaction với side effect database.
- Business key chống tạo trùng thực thể.
- Idempotency key cho API bên ngoài.
- Outbox cho event tiếp theo cần publish.

Không dựa vào cờ redelivered, offset hoặc broker message ID làm định danh nghiệp vụ nếu contract cần một event ID xuyên suốt nhiều lần publish và transport.

Một message được giao một lần ở một tầng broker không có nghĩa toàn bộ nghiệp vụ chỉ xảy ra một lần. Hãy thiết kế consumer an toàn với duplicate.

## Anti-pattern: dựa vào thứ tự toàn cục

Nhiều hệ thống cần giữ thứ tự event theo aggregate, nhưng broker thường chỉ bảo đảm ordering trong phạm vi hẹp.

Kafka bảo đảm thứ tự record trong một partition; không có thứ tự toàn cục giữa các partition. RabbitMQ queue có thể giao message cho nhiều consumer và hoàn tất không theo thứ tự enqueue khi xử lý song song hoặc redelivery.

Nếu mọi consumer đều cần thấy một thứ tự toàn cục, thiết kế có thể bị nghẽn bởi một partition hoặc một consumer duy nhất.

Thay vào đó:
- Xác định ordering cần ở mức aggregate, tenant hay toàn hệ thống.
- Dùng aggregate ID làm Kafka key khi cần giữ event của cùng aggregate trên một partition.
- Dùng aggregate version/sequence để phát hiện event cũ hoặc gap.
- Tuần tự hóa theo key khi nghiệp vụ yêu cầu.
- Không dựa vào timestamp đơn thuần để suy ra thứ tự nhân quả.

Nếu event độc lập, cho phép xử lý song song và không tạo ordering giả tạo.

## Anti-pattern: retry vô hạn và không có quarantine

Retry không sửa được payload sai, schema không hỗ trợ, authorization thất bại hoặc business invariant đã thay đổi. Retry vô hạn có thể chiếm worker, tạo log/alert liên tục, làm queue tăng và trì hoãn message hợp lệ.

Phân loại lỗi:

| Loại lỗi | Xử lý phù hợp |
|---|---|
| Lỗi network/database tạm thời | Retry có backoff, jitter và giới hạn |
| Downstream rate limit | Tuân theo retry-after và throttle |
| Schema không tương thích | Quarantine, cập nhật consumer hoặc upcast |
| Payload không hợp lệ | Reject/DLQ và điều tra producer |
| Authorization thất bại | Reject và audit |
| Business rule không còn đúng | Đối soát hoặc correction workflow |

DLQ cần owner, alert, retention và quy trình redrive. Redrive phải giữ event ID, có idempotency và kiểm tra trạng thái nghiệp vụ. Không tự động replay toàn bộ DLQ sau khi deploy một bản sửa nếu trong đó có nhiều nhóm lỗi khác nhau.

## Anti-pattern: dual-write database và broker không có bảo vệ

Một luồng thường gặp:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orderRepository.markConfirmed(orderId);
    rabbitTemplate.convertAndSend(
        "orders.exchange",
        "order.confirmed",
        new OrderConfirmed(orderId)
    );
}
~~~

Database và broker không tự tham gia cùng một local transaction. Nếu database commit nhưng publish thất bại, consumer không nhận event. Nếu broker nhận message nhưng database rollback hoặc acknowledgement không rõ ràng, consumer có thể xử lý event không tương ứng với trạng thái đã commit.

Không giải quyết bằng cách chỉ đặt hai lời gọi trong cùng method có @Transactional. Transaction manager của database không tự bảo đảm atomicity với broker trừ khi có cấu hình distributed transaction thực sự và trade-off phù hợp.

Với yêu cầu không mất event, cân nhắc transactional outbox: ghi thay đổi nghiệp vụ và outbox record trong cùng database transaction; relay publish record sau commit và đánh dấu trạng thái theo kết quả gửi. Consumer vẫn cần idempotency vì relay có thể gửi lại.

Trong Spring Modulith, Event Publication Registry hỗ trợ theo dõi publication cho listener được quản lý. Cơ chế persistence và externalization cần được cấu hình theo yêu cầu; không giả định registry tự động thay thế mọi outbox hoặc bảo đảm end-to-end exactly-once.

## Anti-pattern: dùng broker để né thiết kế module

Nếu module A không được phép truy cập repository của module B, thêm broker giữa hai module không tự động sửa được dependency sai. Nó chỉ chuyển dependency thành schema, topic, routing, credential và consumer lifecycle.

Trong modular monolith, hãy công bố public API hoặc application event tại ranh giới module. Dùng công cụ kiểm tra cấu trúc của Spring Modulith để phát hiện dependency không hợp lệ.

Nếu hai module cần chia sẻ dữ liệu, xác định module sở hữu dữ liệu và hợp đồng truy cập. Không để cả hai cùng ghi một database table rồi dùng event để thông báo sau đó. Nếu một module cần snapshot, phát event với dữ liệu được công bố rõ hoặc gọi API đọc có kiểm soát.

Broker không thay thế thiết kế bounded context, ownership hoặc transaction boundary.

## Anti-pattern: chọn công nghệ theo trào lưu

Kafka và RabbitMQ có mô hình vận hành khác nhau. Chọn công nghệ dựa trên yêu cầu:

| Nhu cầu | Cân nhắc |
|---|---|
| Log record có retention, replay theo offset, nhiều consumer group | Kafka hoặc nền tảng log tương đương |
| Work queue, routing exchange/binding, acknowledgement và DLQ | RabbitMQ hoặc broker queue tương đương |
| Giao tiếp nội bộ trong cùng ApplicationContext | Spring application event |
| Gọi capability đồng bộ giữa module | Module public API |
| Gọi service độc lập cần phản hồi ngay | HTTP/gRPC |
| Lưu trạng thái nghiệp vụ và truy vấn hiện tại | Database/read model |
| Chuyển thay đổi database sang hệ thống khác | CDC hoặc outbox tùy yêu cầu |

Không chọn Kafka chỉ vì cần gửi một task nhỏ tới một worker nếu queue semantics đơn giản hơn. Không chọn RabbitMQ làm event log dài hạn nếu yêu cầu replay/retention/partition semantics phù hợp hơn với nền tảng log.

Cũng tránh vận hành nhiều broker cùng lúc nếu lợi ích không đủ bù chi phí về chuyên môn, bảo mật, monitoring, backup, upgrade và incident response.

## Khi nào broker thực sự đáng dùng?

Broker thường đáng giá khi một hoặc nhiều điều kiện sau là yêu cầu thật:

- Producer và consumer chạy ở tiến trình hoặc tổ chức khác nhau.
- Consumer có thể ngừng hoạt động tạm thời nhưng message cần được giữ lại.
- Producer cần tiếp tục mà không chờ consumer hoàn tất.
- Một event cần được phân phối tới nhiều consumer độc lập.
- Cần đệm tải để tách tốc độ producer và consumer.
- Cần retention/replay theo policy để phục hồi hoặc rebuild.
- Hệ thống cần scale consumer độc lập.
- Cần giao thức tích hợp được quản trị, có schema, ACL và observability.

Ngay cả khi broker cần thiết, chỉ externalize những event có mục đích tích hợp rõ. Không nhất thiết mọi application event nội bộ đều phải đi qua broker.

## Ma trận quyết định chọn cơ chế giao tiếp

Có thể dùng các câu hỏi sau để quyết định:

| Câu hỏi | Nếu có | Hướng phù hợp |
|---|---|---|
| Caller cần kết quả ngay để tiếp tục? | Có | Public API hoặc HTTP/gRPC |
| Hai thành phần cùng ApplicationContext? | Có | Public API hoặc application event nội bộ |
| Consumer có thể offline nhưng cần nhận lại message? | Có | Broker với durability và retry policy |
| Nhiều hệ thống độc lập cần nhận cùng event? | Có | Broker với subscription/queue riêng |
| Cần lưu lịch sử nghiệp vụ để query và replay dài hạn? | Có | Event store/archive được thiết kế riêng |
| Chỉ cần chuyển DB change sang downstream? | Có | Outbox hoặc CDC theo semantics |
| Chỉ là tác vụ nền đơn giản trong một ứng dụng? | Có | Executor/job queue nội bộ nếu đủ yêu cầu |

Không dùng bảng như luật tuyệt đối. Cần xem security, latency, throughput, availability, ordering, consistency và năng lực vận hành của tổ chức.

## Thiết kế broker boundary khi đã có lý do sử dụng

Khi quyết định dùng broker, cần định nghĩa rõ contract và ownership:

- Producer sở hữu event type và schema.
- Consumer sở hữu cách xử lý và idempotency.
- Destination có owner, retention và security policy.
- Event ID ổn định qua retry và replay.
- Schema có version và compatibility policy.
- Retry có giới hạn, backoff và quarantine.
- Ordering được xác định theo partition/key hoặc queue semantics.
- Consumer có capacity, backpressure và graceful shutdown.
- Có dashboard backlog, lag, publish failure và processing failure.
- Có runbook replay, DLQ redrive và incident response.

Không để broker topology trở thành API ẩn mà không có tài liệu. Topic, exchange, queue, routing key, consumer group, header và schema đều là một phần của integration contract.

## Tích hợp broker có chọn lọc với Spring Modulith

Spring Modulith giúp tổ chức module và application event bên trong ứng dụng. Có thể dùng event nội bộ để tách producer khỏi listener, sau đó externalize một số event được chọn tới hệ thống ngoài.

Một luồng hợp lý:

~~~mermaid
flowchart TD
    A[Orders module] --> B[Publish internal application event]
    B --> C[Internal module listeners]
    B --> D[Selected externalization adapter]
    D --> E[Transactional publication/outbox mechanism]
    E --> F[Broker]
    F --> G[External consumer]
~~~

Các điểm cần lưu ý:

- Public API dùng khi cần kết quả đồng bộ.
- Application event nội bộ dùng khi module khác phản ứng với thay đổi đã xảy ra.
- Externalization chỉ áp dụng cho event có consumer ngoài ứng dụng.
- Event Publication Registry theo dõi publication theo listener; nó không phải event store tổng quát.
- Outbox/relay và broker delivery cần idempotency, retry và observability.
- Không để consumer bên ngoài phụ thuộc vào class nội bộ của module producer; công bố wire contract ổn định.

Nếu ứng dụng chưa cần tách tiến trình, có thể giữ event nội bộ. Khi một consumer cần scale hoặc deploy độc lập, externalize đúng event đó và kiểm tra lại transaction, schema, security và operational readiness.

## Lộ trình loại bỏ broker không cần thiết

Nếu hệ thống đã có broker giữa các module cùng tiến trình, không nên xóa ngay khi chưa hiểu consumer và side effect.

Một lộ trình có kiểm soát:

1. Liệt kê producer, consumer, destination, routing và side effect của luồng.
2. Xác định consumer nào nằm cùng ứng dụng và consumer nào ở ngoài.
3. Phân loại luồng cần phản hồi đồng bộ, event nội bộ hay delivery bền vững qua broker.
4. Công bố module API hoặc application event nội bộ tương ứng.
5. Chuyển một consumer tại một thời điểm, giữ hành vi tương đương.
6. Đối chiếu kết quả giữa đường cũ và đường mới trong môi trường kiểm thử/canary.
7. Dừng publish broker sau khi xác nhận không còn consumer phụ thuộc.
8. Chờ hết backlog, retention/replay window và hoàn tất migration consumer.
9. Thu hồi ACL, xóa destination không còn dùng và cập nhật runbook.
10. Theo dõi latency, lỗi và side effect sau khi loại bỏ broker.

Nếu phải chạy song song hai đường trong thời gian chuyển tiếp, tránh để cả hai cùng tạo side effect. Có thể dùng shadow processing không ghi dữ liệu hoặc idempotency/business key chung để kiểm soát duplicate.

Không xóa topic/queue trước khi xác minh không còn consumer, message tồn đọng hoặc yêu cầu audit.

## Kiểm thử để phát hiện lạm dụng và rủi ro broker

Kiểm thử không chỉ xác nhận message gửi được. Cần chứng minh cơ chế được chọn đáp ứng yêu cầu và không tạo coupling ngoài ý muốn.

| Kiểm tra | Câu hỏi cần trả lời |
|---|---|
| Module test | Module có thể hoạt động qua public API mà không cần broker không? |
| Application event test | Listener nội bộ nhận đúng event và xử lý sau commit không? |
| Architecture test | Dependency giữa module có tuân thủ ranh giới không? |
| Contract test | Producer và consumer có thống nhất schema/version không? |
| Broker integration test | Routing, acknowledgement, retry và DLQ hoạt động đúng không? |
| Failure test | Broker outage có làm hỏng luồng không cần broker không? |
| Duplicate test | Consumer có idempotent khi redelivery/replay không? |
| Load test | Broker và consumer có xử lý được throughput/backpressure không? |
| Security test | Producer/consumer chỉ truy cập destination được cấp không? |
| Recovery test | Có thể replay và đối soát mà không tạo side effect trùng không? |

Nếu một unit test nội bộ cần khởi động Kafka chỉ để gọi một service, đó là dấu hiệu cần xem lại test boundary và dependency injection. Ngược lại, nếu test mục tiêu là externalization thì broker thật hoặc container tương đương là cần thiết.

## Các chỉ số vận hành cần theo dõi

Khi broker được dùng đúng chỗ, vẫn phải quản lý chi phí và độ tin cậy:

- Publish latency và publish failure rate.
- Consumer lag hoặc queue depth.
- Message age và oldest pending age.
- Retry count, redelivery và DLQ volume.
- Duplicate skipped và idempotency conflict.
- Serialization/schema error.
- Broker availability, disk, memory, network và replication health.
- Consumer throughput, processing latency và downstream error.
- Số destination, consumer group và policy chưa có owner.

Không dùng event ID hoặc aggregate ID làm metric label vì cardinality lớn. Dùng chúng trong structured logs và traces để điều tra một event cụ thể.

Nếu broker chỉ phục vụ giao tiếp nội bộ đơn giản nhưng chi phí vận hành, độ trễ và số lỗi tăng đáng kể, hãy đánh giá lại lợi ích kiến trúc so với module API hoặc application event nội bộ.

## Checklist trước khi đưa broker vào một luồng mới

1. Producer và consumer có thực sự nằm ở các tiến trình hoặc miền vận hành độc lập không?
2. Có yêu cầu bất đồng bộ, buffering, durability, fan-out hoặc replay rõ ràng không?
3. Vì sao module API hoặc application event nội bộ chưa đủ?
4. Ai sở hữu event contract, schema và destination?
5. Consumer có idempotent và chịu được duplicate không?
6. Ordering cần ở phạm vi nào?
7. Retry, DLQ, retention và replay có policy không?
8. Dual-write được bảo vệ bằng outbox hoặc cơ chế tương đương chưa?
9. Security, ACL, secret và dữ liệu nhạy cảm đã được thiết kế chưa?
10. Monitoring, alert, runbook và năng lực vận hành đã sẵn sàng chưa?
11. Chi phí broker có tương xứng với lợi ích của luồng không?
12. Có cách kiểm thử và diễn tập broker outage/recovery không?

Lạm dụng broker làm một lời gọi đơn giản trở thành một quy trình phân tán với nhiều điểm lỗi, nhiều trạng thái và chi phí vận hành. Trong Spring Modulith, hãy bắt đầu từ module public API và application event nội bộ; chỉ externalize qua broker khi cần ranh giới tiến trình, delivery bền vững, buffering, fan-out hoặc replay. Khi mỗi luồng có mục tiêu, contract, ownership và policy vận hành rõ ràng, broker trở thành hạ tầng hỗ trợ đúng nhu cầu thay vì một lớp phức tạp không cần thiết.

## Tài liệu tham khảo

- Spring Modulith Reference — Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Spring Modulith Reference — Application Module Structure: https://docs.spring.io/spring-modulith/reference/fundamentals.html
- Apache Kafka Documentation — Design and Concepts: https://kafka.apache.org/documentation/
- RabbitMQ Documentation — AMQP Concepts: https://www.rabbitmq.com/tutorials/amqp-concepts
- Enterprise Integration Patterns — Messaging Patterns: https://www.enterpriseintegrationpatterns.com/
