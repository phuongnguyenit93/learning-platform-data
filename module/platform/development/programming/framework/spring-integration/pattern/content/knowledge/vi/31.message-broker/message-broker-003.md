# Durable message và queue semantics

**Chương:** Message broker  
**Chủ đề:** Durable message và queue semantics  
**Phạm vi:** Enterprise Integration Patterns với Spring Integration, tập trung vào lưu trữ thông điệp, nhận và xử lý từ hàng đợi, giao dịch, retry, lỗi và correlation khi triển khai hệ thống ít phụ thuộc, dễ mở rộng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **message bền vững (durable/persistent message)**, **hàng đợi bền vững (durable queue)** và **xử lý bền vững**; hiểu vì sao mỗi yếu tố giải quyết một loại sự cố khác nhau.
- Giải thích các ngữ nghĩa của queue: producer/consumer, cạnh tranh giữa các consumer, thứ tự xử lý, thời điểm lấy message, ACK/commit, redelivery và delivery guarantee.
- Thiết kế luồng Spring Integration có `QueueChannel` và persistent `MessageStore`, hoặc dùng broker như RabbitMQ/Kafka khi cần tách tiến trình; kiểm soát giao dịch, retry, idempotency và luồng lỗi.
- Xây dựng kịch bản kiểm thử restart, crash, duplicate, poison message và giám sát queue trong môi trường vận hành.

## 1. Vấn đề: nhận được message chưa có nghĩa là xử lý thành công

Giả sử hệ thống đặt hàng phát sinh sự kiện `OrderPlaced`. Dịch vụ gửi message vào hàng đợi để worker tạo hóa đơn. Khi worker bận hoặc tạm dừng, message cần được giữ lại. Khi ứng dụng hay máy chủ khởi động lại, các message **đã được chấp nhận nhưng chưa xử lý** vẫn phải có thể được xử lý tiếp.

Một hàng đợi trong bộ nhớ giải quyết việc **tách nhịp độ** giữa phía gửi và phía nhận, nhưng không tự bảo vệ dữ liệu trước việc tiến trình bị dừng. Một hàng đợi có lưu trữ bền vững giúp dữ liệu tồn tại sau restart, nhưng vẫn chưa đủ để ngăn **xử lý trùng** hoặc đảm bảo một tác vụ nghiệp vụ đã hoàn tất.

Tách ba câu hỏi:

1. **Message có còn tồn tại?** Phụ thuộc vào nơi lưu trữ và thời điểm hệ thống xác nhận đã ghi.
2. **Message đã được xử lý hay chưa?** Phụ thuộc vào ACK, offset, transaction hoặc quy tắc xóa khỏi queue.
3. **Tác động nghiệp vụ xảy ra bao nhiêu lần?** Phụ thuộc vào idempotency và ranh giới giao dịch của consumer.

## 2. Thuật ngữ nền tảng

| Khái niệm | Ý nghĩa | Điểm dễ nhầm |
|---|---|---|
| **Durable queue** | Định nghĩa/cấu hình hàng đợi còn sau lần khởi động lại broker, tùy công nghệ. | Queue tồn tại không đồng nghĩa mọi message trong đó đã được ghi bền vững. |
| **Persistent/durable message** | Message được ghi vào tầng lưu trữ có khả năng phục hồi theo cơ chế của broker hoặc message store. | Việc gửi thành công ở phía API không nhất thiết đồng nghĩa đã có xác nhận ghi ổn định từ broker. |
| **In-flight message** | Message đã giao cho consumer hoặc đang được xử lý, chưa được xác nhận hoàn tất. | Có thể được giao lại khi timeout, rollback, mất kết nối hoặc crash. |
| **ACK/commit** | Tín hiệu kết thúc trách nhiệm của queue/broker đối với một lần giao hoặc vị trí tiêu thụ. | ACK quá sớm có thể làm mất việc; ACK muộn có thể dẫn đến duplicate. |
| **Redelivery** | Message được giao lại sau khi lần xử lý trước không hoàn tất theo quy tắc của hệ thống. | Cần phân biệt giao lại với tạo message mới. |
| **Dead-letter queue (DLQ)** | Nơi cách ly message không thể xử lý sau chính sách retry hoặc do lỗi không phục hồi. | Chuyển tới DLQ cần cơ chế quan sát và xử lý tiếp. |
| **Idempotency** | Xử lý cùng một sự kiện nhiều lần vẫn tạo kết quả nghiệp vụ như một lần. | Đây là thuộc tính của nghiệp vụ, không phải mặc định của queue. |

**Lưu ý:** RabbitMQ, JMS, Kafka và `QueueChannel` của Spring Integration có cách lưu trữ và xác nhận hoàn tất khác nhau. Không nên suy ra tính năng của một công nghệ từ tên gọi chung “message broker”.

## 3. Luồng queue và thời điểm xác nhận

~~~mermaid
flowchart LR
    P["Producer"] --> S["Gửi message"]
    S --> Q[("Durable queue / persistent store")]
    Q --> C["Consumer / Poller"]
    C --> H{"Xử lý nghiệp vụ"}
    H -->|Thành công| A["ACK / commit"]
    H -->|Lỗi có thể phục hồi| R["Rollback / retry có backoff"]
    H -->|Lỗi không phục hồi| D["DLQ / quarantine"]
    R --> Q
~~~

Đường đi thành công thường có ý nghĩa: producer gửi → hệ thống lưu trữ tiếp nhận → consumer nhận → nghiệp vụ xử lý → xác nhận. **Chính sách thực tế phụ thuộc loại queue và cách cấu hình transaction/acknowledgement**; sơ đồ mô tả ý định thiết kế, không khẳng định tất cả broker đều hoạt động giống nhau.

Ba mốc cần phân biệt:

- **Producer accepted:** lời gọi gửi đã được phía gửi hoặc tầng nhận chấp nhận; cần xác định rõ có xác nhận lưu trữ hay chưa.
- **Consumer received:** một consumer được giao message hoặc lấy message từ store; chưa chắc nghiệp vụ đã hoàn thành.
- **Business committed:** thay đổi nghiệp vụ đã được commit. Lúc này cần phối hợp ACK/transaction để tránh mất message hoặc xử lý lại không kiểm soát.

Nếu tiến trình dừng **trước khi ghi message thành công**, producer phải có cơ chế retry hoặc outbox. Nếu dừng **sau khi nghiệp vụ commit nhưng trước ACK**, hệ thống có thể giao lại message; consumer phải nhận biết và bỏ qua tác động trùng.

## 4. Queue semantics: truyền cho một nhóm worker

### 4.1 Point-to-point và cạnh tranh consumer

Ở kiểu point-to-point, mỗi message được phân phối để một consumer trong nhóm xử lý ở một lần giao. Nếu nhiều worker cùng đọc một queue, các worker **cạnh tranh** lấy công việc; đây là cách mở rộng throughput. “Một consumer nhận tại một thời điểm” không bảo đảm kết quả nghiệp vụ *chỉ xảy ra đúng một lần*, vì một message có thể bị redeliver.

Trái lại, publish/subscribe thường phát thông điệp tới nhiều subscriber. Muốn mỗi nhóm nghiệp vụ nhận độc lập, cần thiết kế queue/subscription riêng theo công nghệ. Không thể coi nhiều consumer cùng đọc **một** work queue như nhiều subscriber đều sẽ nhận đủ các message.

### 4.2 FIFO, concurrency và thứ tự hoàn thành

FIFO (first in, first out) thường là thứ tự lấy phần tử trong một queue đơn giản. Tuy nhiên:

- Hai worker nhận lần lượt message A, B vẫn có thể **hoàn thành B trước A**.
- Retry, redelivery, độ ưu tiên hoặc nhiều queue/partition có thể thay đổi thứ tự quan sát.
- Kafka chỉ duy trì thứ tự bản ghi **trong một partition**; không có tổng thứ tự toàn topic khi có nhiều partition.
- Khi nghiệp vụ yêu cầu thứ tự theo đơn hàng, hãy gắn `orderId` làm khóa định tuyến/correlation và chọn chiến lược serialization theo khóa, hoặc giữ một consumer cho phạm vi cần thứ tự.

Không nên dựa vào FIFO của queue để bảo đảm thứ tự cập nhật dữ liệu trong hệ thống phân tán.

### 4.3 Backpressure và giới hạn tài nguyên

Producer có thể gửi nhanh hơn consumer. Queue sẽ dài ra, tăng độ trễ, tăng dung lượng lưu trữ và có thể làm quá tải database hoặc broker. Cần đặt giới hạn phù hợp: số worker, số message xử lý song song, prefetch/batch, tốc độ poller, quota queue và cảnh báo tuổi message lâu nhất. Cách xử lý khi queue đầy phải được xác định rõ: chờ, từ chối có kiểm soát, hoặc định tuyến sang phương án dự phòng phù hợp.

## 5. Spring Integration: `QueueChannel` và message store

Spring Integration cung cấp `MessageChannel` để tách component gửi/nhận. Với `QueueChannel`, consumer lấy message bằng mô hình `PollableChannel`; một poller có thể kéo message rồi đưa tới `Service Activator` hoặc handler.

| Lựa chọn | Dữ liệu tồn tại ở đâu? | Khi nào dùng? |
|---|---|---|
| `QueueChannel` mặc định | Bộ nhớ của tiến trình | Buffer tạm thời, ứng dụng đơn giản, chấp nhận mất message khi tiến trình dừng. |
| `QueueChannel` kết hợp `JdbcChannelMessageStore` | Cơ sở dữ liệu qua JDBC | Cần queue bền vững trong ứng dụng Spring Integration, có quyền quản trị schema và transaction của DB. |
| Adapter Spring Integration nối RabbitMQ/JMS | Broker ngoài tiến trình | Cần giao tiếp giữa các dịch vụ, consumer độc lập và cơ chế queue/ACK của broker. |
| Adapter nối Kafka | Distributed log và consumer offsets | Cần stream, replay, consumer group, retention và thứ tự theo partition. |

`QueueChannel` dùng bộ nhớ **không mặc nhiên durable**. Để bảo toàn message qua restart, phải cấu hình một persistent message store tương thích và bảo đảm cơ sở dữ liệu được quản lý bền vững. Một message store có lưu trữ vẫn không thay thế yêu cầu transaction khi consumer lấy message và chạy nghiệp vụ.

### 5.1 Ví dụ: hàng đợi lưu JDBC

Ví dụ Java DSL dưới đây minh họa một `QueueChannel` có JDBC store và poller xử lý trong transaction. Các import được lược bỏ để tập trung vào luồng chính; cấu hình này cần các thư viện Spring Integration JDBC/Java DSL, JDBC transaction manager và schema bảng Spring Integration phù hợp với loại database, phiên bản đang dùng.

~~~java
@Configuration
@EnableIntegration
public class DurableOrderFlowConfig {

    @Bean
    JdbcChannelMessageStore orderMessageStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        store.setRegion("orders");
        return store;
    }

    @Bean
    MessageChannel durableOrders(JdbcChannelMessageStore orderMessageStore) {
        return new QueueChannel(orderMessageStore, "order-events");
    }

    @Bean
    IntegrationFlow orderProcessingFlow(
            OrderService orderService,
            PlatformTransactionManager transactionManager) {

        return IntegrationFlow
                .from("durableOrders",
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(1000)
                                        .maxMessagesPerPoll(5)
                                        .transactional(transactionManager)))
                .handle(OrderEvent.class, (event, headers) -> {
                    orderService.applyOnce(event.eventId(), event);
                    return null;
                })
                .get();
    }
}

public record OrderEvent(String eventId, String orderId)
        implements java.io.Serializable {
}
~~~

Ý nghĩa của các thành phần:

- `JdbcChannelMessageStore` lưu message trong database; `region` và group ID tách phạm vi của queue, giúp tránh trộn dữ liệu giữa các nhóm.
- `QueueChannel` dùng message store được truyền vào thay vì queue bộ nhớ mặc định.
- `Pollers.fixedDelay(...)` chọn chu kỳ lấy message; `maxMessagesPerPoll` giới hạn lượng xử lý cho một lần poll. Cần điều chỉnh theo tải thực tế.
- `transactional(transactionManager)` đặt transaction cho lần poll và xử lý qua advice của poller. Transaction manager phải phù hợp với **cùng tài nguyên JDBC** mà message store sử dụng; kiểm thử rollback và redelivery thực tế là bắt buộc.
- `orderService.applyOnce(...)` là hợp đồng xử lý idempotent: cùng `eventId` không được tạo hai tác động nghiệp vụ. Việc triển khai phụ thuộc database và phải bảo đảm kiểm tra trùng cùng transaction với cập nhật nghiệp vụ.

Producer có thể đưa message vào channel như sau:

~~~java
public void publishOrder(MessageChannel durableOrders, OrderEvent event) {
    Message<OrderEvent> message = MessageBuilder
            .withPayload(event)
            .setHeader("eventId", event.eventId())
            .setHeader("correlationId", event.orderId())
            .build();

    boolean accepted = durableOrders.send(message);
    if (!accepted) {
        throw new IllegalStateException("Queue did not accept the message");
    }
}
~~~

Lời gọi `send` trả về thành công chỉ phản ánh hợp đồng gửi của channel tại thời điểm đó. Khi hệ thống cần bảo đảm giao dịch **ghi đơn hàng và phát message** không rời nhau, hãy dùng transactional outbox hoặc cơ chế giao dịch phù hợp; không giả định gọi `send` sau khi commit database là atomic với lần ghi trước đó.

**Điểm triển khai cần kiểm tra:** khởi tạo bảng JDBC Message Store theo script/schema tương ứng với cơ sở dữ liệu; cấu hình transaction manager; serializer/message converter cho payload và header; giữ tương thích dữ liệu khi thay đổi class `OrderEvent`; xác định quyền truy cập và lifecycle của message store. Việc ghi object Java trực tiếp vào JDBC store trong ví dụ nhằm minh họa; ở hệ thống thực tế nên dùng định dạng sự kiện có phiên bản rõ ràng.

### 5.2 Vì sao cần transaction bao quanh xử lý?

Một pollable queue có thể xóa message khỏi hàng đợi khi consumer nhận. Nếu việc nhận và nghiệp vụ không nằm trong transaction/chiến lược xác nhận phù hợp, crash ngay sau khi nhận có thể làm message biến mất mà tác vụ chưa hoàn thành. Với persistent store hỗ trợ transaction, rollback có thể khiến thao tác lấy chưa được commit, tạo cơ hội xử lý lại.

Giả sử xử lý hóa đơn gồm hai bước: cập nhật trạng thái vào DB rồi gửi email. Transaction DB chỉ có thể rollback thay đổi trong DB; email đã gửi ra ngoài **không thể rollback bằng transaction DB**. Vì vậy idempotency hoặc outbox cho side effect bên ngoài vẫn cần thiết, kể cả khi phần xử lý message có transaction.

## 6. Delivery guarantees: chọn giả định đúng

| Cam kết | Hành vi điển hình | Rủi ro và yêu cầu |
|---|---|---|
| **At-most-once** | Message có thể mất, nhưng không cố giao lại sau lỗi. | Phù hợp với tín hiệu không quan trọng; không đủ cho giao dịch cần xử lý chắc chắn. |
| **At-least-once** | Hệ thống cố giao lại cho đến khi được xác nhận hoặc tới giới hạn chính sách. | Có thể xử lý trùng; cần idempotent consumer. |
| **Exactly-once effect** | Tác động nghiệp vụ cuối cùng tương đương xử lý một lần. | Phải định nghĩa rõ phạm vi; thường đạt bằng transaction, khóa duy nhất, deduplication và phối hợp xác nhận. |

Không nên khẳng định “exactly once” xuyên nhiều hệ thống chỉ từ một tùy chọn của broker. Ví dụ một broker có thể chống ghi trùng trong phạm vi log, nhưng việc gọi API thanh toán, gửi email hay ghi database khác vẫn có thể lặp khi consumer chạy lại.

### 6.1 Ba điểm crash đáng kiểm tra

| Thời điểm crash | Điều có thể xảy ra | Cách ứng phó |
|---|---|---|
| Trước khi hệ thống xác nhận đã lưu message | Producer không biết message đã được lưu hay chưa. | Retry với khóa sự kiện ổn định; publisher confirm/outbox khi cần. |
| Sau khi consumer lấy message, trước khi commit nghiệp vụ | Công việc có thể cần được giao lại, tùy ACK/transaction. | Thiết lập ACK/rollback đúng ranh giới; kiểm tra redelivery. |
| Sau khi nghiệp vụ commit, trước ACK | Lần xử lý tiếp theo có thể lặp thao tác đã thành công. | Khóa idempotency và kiểm tra duplicate trên dữ liệu nghiệp vụ. |

### 6.2 Xử lý idempotent bằng khóa nghiệp vụ

Dùng `eventId` do producer sinh ổn định, độc lập với ID message nội bộ. Một cách phổ biến là ghi bảng `processed_event` với unique constraint và cập nhật nghiệp vụ **trong cùng transaction**:

~~~sql
-- Minh họa PostgreSQL; bảng processed_event có UNIQUE(event_id).
BEGIN;

INSERT INTO processed_event(event_id)
VALUES (:eventId)
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ thực hiện cập nhật nghiệp vụ nếu INSERT ở trên
-- thực sự tạo một dòng mới.
UPDATE orders
SET invoice_status = 'CREATED'
WHERE order_id = :orderId;

COMMIT;
~~~

Đoạn SQL thể hiện nguyên tắc; ứng dụng phải đọc số dòng được insert và **bỏ qua câu UPDATE khi insert không thành công vì event đã tồn tại**. Nếu việc đánh dấu processed và cập nhật nghiệp vụ ở hai transaction khác nhau, consumer có thể tạo ra trạng thái dở dang. Đối với API ngoài database, cần dùng idempotency key của phía nhận hoặc lưu lệnh chờ trong outbox để điều phối lại.

## 7. Retry, error channel và poison message

Lỗi transient như database timeout có thể thử lại; lỗi dữ liệu không hợp lệ hoặc vi phạm schema thường cần tách riêng. Một chính sách xử lý thực dụng:

1. **Phân loại lỗi:** có thể phục hồi (timeout, mạng chập chờn) hoặc lỗi không phục hồi (payload sai schema, thiếu trường bắt buộc).
2. **Retry hữu hạn:** đặt số lần thử, exponential backoff và jitter; tránh lặp tức thì gây nghẽn.
3. **Giữ thông tin liên kết:** `eventId`, `correlationId`, số lần thử, nguyên nhân lỗi, thời điểm đầu tiên.
4. **Đưa tới DLQ/quarantine:** khi vượt ngưỡng hoặc gặp lỗi không thể xử lý; việc chuyển giao phải có cơ chế tránh làm mất message.
5. **Sửa nguyên nhân rồi replay:** chỉ chạy lại sau khi dữ liệu hoặc handler đã được xử lý, bảo đảm idempotency.

Trong Spring Integration, `errorChannel` giúp định tuyến `ErrorMessage` tới luồng xử lý lỗi, nhưng **không tự động mang nghĩa retry bền vững hay ACK thành công**. Cần xem lỗi nảy sinh từ handler có được propagate tới poller/adapter hay đã bị handler lỗi hấp thụ; lựa chọn này quyết định transaction rollback và phản ứng của broker. Không nên cấu hình một error handler chỉ ghi log rồi nuốt exception khi kỳ vọng broker sẽ redeliver.

Khi dùng broker ngoài:

- **RabbitMQ:** thường cần cả queue được khai báo durable, message persistent, và xác nhận phát/nhận phù hợp. ACK/requeue và DLX/DLQ là các cơ chế riêng; cấu hình phải được kiểm tra với broker thực.
- **JMS:** persistent delivery và transaction/session acknowledgment phụ thuộc provider và cấu hình listener.
- **Kafka:** message được giữ trong log theo chính sách retention; consumer commit offset để lưu vị trí đọc. Đây không phải dequeue/xóa message kiểu work queue truyền thống. Retry, dead-letter topic và ordering theo partition phải thiết kế riêng.

## 8. Correlation, tracing và quan sát

Message tối thiểu nên mang một **ID sự kiện bất biến** để deduplicate, một **business key** (ví dụ `orderId`) để correlation và một **trace context** để kết nối nhật ký xuyên các bước Router, Transformer, Service Activator và broker adapter. Không sử dụng message ID tự sinh như bảo đảm duy nhất cho cùng sự kiện nghiệp vụ qua mọi lần retry hoặc publish lại.

Các chỉ số vận hành quan trọng gồm:

- Số message đang chờ, message đang xử lý và **tuổi message lâu nhất**.
- Tốc độ enqueue/dequeue, thời gian từ publish tới xử lý, số consumer hoạt động và độ trễ mỗi lần poll.
- Số lần retry, lỗi theo nguyên nhân, DLQ depth, tỉ lệ duplicate được chặn, thời gian khôi phục sau restart.
- Dung lượng store, độ trễ database/broker, thất bại ghi message và trạng thái kết nối.

Đặt cảnh báo theo mục tiêu nghiệp vụ. Ví dụ queue có 10.000 message nhưng giải phóng nhanh có thể ít nghiêm trọng hơn queue có 100 message đã chờ quá SLA xử lý.

## 9. Chọn persistent QueueChannel hay broker ngoài?

**Dùng persistent `QueueChannel`** khi ứng dụng cần tách producer/consumer nội bộ, khối lượng vừa phải, có thể quản lý một JDBC store và không cần topology broker phức tạp. Cần kiểm thử kỹ throughput, contention, kích thước bảng và transaction khi mở rộng nhiều instance.

**Dùng RabbitMQ/JMS** khi các dịch vụ độc lập cần giao tiếp qua queue và muốn tận dụng routing, consumer management, ACK, DLQ và cơ chế vận hành broker. **Dùng Kafka** khi bài toán là dòng sự kiện có retention/replay, nhiều consumer group và yêu cầu thứ tự theo khóa/partition. Một application vẫn có thể dùng Spring Integration làm lớp kết nối, Router, Transformer, Gateway và Error Channel xung quanh các adapter đó.

Không chọn chỉ dựa trên tên “durable”. Hãy viết rõ failure model: *sự cố nào cần chịu được, dữ liệu nào không được mất, trùng lặp được xử lý thế nào, cần replay đến đâu, và nghiệp vụ hoàn thành được xác nhận tại đâu*.

## 10. Bài thực hành và kiểm thử hành vi

Giả sử `order-42` phát sự kiện `evt-123`; worker cập nhật `invoice_status`. Hãy chạy luồng từ ví dụ JDBC và kiểm tra các tình huống:

| Tình huống | Thao tác | Kết quả kỳ vọng |
|---|---|---|
| Producer gửi rồi worker tạm ngừng | Enqueue `evt-123`, không khởi động poller ngay. | Message vẫn ở persistent store, được xử lý sau khi poller chạy. |
| Restart trước khi xử lý | Tắt và bật lại ứng dụng sau khi việc enqueue đã commit. | Message có thể được lấy và xử lý sau restart. |
| Lỗi giữa xử lý | Cho handler throw exception trước khi commit. | Kiểm chứng transaction rollback và redelivery đúng theo cấu hình thật; không đánh dấu thành công giả. |
| Crash sau business commit, trước ACK | Giả lập giao lại cùng `evt-123`. | `applyOnce` ngăn tạo hóa đơn/side effect trùng. |
| Poison message | Gửi payload không hợp lệ lặp lại. | Retry hữu hạn, chuyển quarantine/DLQ và có log/correlation để điều tra. |
| Nhiều worker | Tăng consumer rồi phát sự kiện A và B cùng `orderId`. | Không tự giả định thứ tự hoàn thành; áp dụng xử lý theo khóa nếu yêu cầu. |
| Store/broker mất kết nối | Ngắt database hoặc broker ở lúc publish và lúc consume. | Gửi/nhận báo lỗi rõ, không âm thầm xác nhận khi chưa lưu hoặc chưa xử lý. |

Một cách đo kết quả thực hành là đếm **tác động nghiệp vụ** sau khi chạy lại cùng một `eventId`, thay vì chỉ đếm số lần handler được gọi. Handler có thể chạy hai lần trong mô hình at-least-once; trạng thái cuối cùng vẫn phải đúng và không phát sinh hai hóa đơn.

## 11. Checklist trước khi đưa vào vận hành

- [ ] Xác định rõ message được ghi bền vững ở đâu và điều kiện nào chứng tỏ producer đã được xác nhận.
- [ ] Kiểm tra durability của queue, message, database/broker và cơ chế recovery theo công nghệ cụ thể.
- [ ] Kiểm tra transaction/ACK bao quanh nhận message và xử lý; mô phỏng crash ở các mốc quan trọng.
- [ ] Dùng `eventId` ổn định, deduplication và idempotency trên mọi side effect quan trọng.
- [ ] Có chính sách retry/backoff, DLQ/quarantine, replay an toàn và người chịu trách nhiệm xử lý.
- [ ] Tài liệu hóa yêu cầu ordering, correlation, concurrency và capacity.
- [ ] Quan sát queue lag, message age, duplicate, lỗi và sức khỏe tầng lưu trữ.
- [ ] Thử restart, failover, xử lý trùng và thay đổi version payload trước khi triển khai.

**Kết luận:** durable message bảo vệ **dữ liệu đang chờ xử lý**; queue semantics quy định **ai lấy message và điều gì xảy ra khi có lỗi**; transaction, ACK và idempotency bảo vệ **kết quả nghiệp vụ**. Kết hợp đúng ba lớp này mới tạo ra luồng thông điệp Spring Integration đáng tin cậy khi hệ thống có retry, restart và nhiều consumer.
