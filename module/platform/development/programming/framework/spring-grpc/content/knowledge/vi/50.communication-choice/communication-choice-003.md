# Chọn messaging cho giao tiếp bất đồng bộ

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện workload phù hợp với asynchronous messaging giữa các service.
- Phân biệt message broker, event stream và asynchronous RPC.
- Chọn giữa command và event theo ý nghĩa nghiệp vụ.
- Đánh giá delivery guarantee, ordering, retry, dead-letter queue và idempotency.
- Kết hợp messaging với gRPC trong kiến trúc Spring.
- Thiết kế publisher/consumer, transactional outbox và inbox để xử lý lỗi an toàn.
- Theo dõi độ trễ xử lý, consumer lag, retry và khả năng phục hồi.

## 1. Khi nào giao tiếp bất đồng bộ phù hợp?

Trong giao tiếp đồng bộ, caller gửi request và chờ service được gọi trả kết quả. Cả hai phía cùng tham gia vào thời gian xử lý của request. Nếu service đích chậm hoặc không khả dụng, caller có thể phải chờ, timeout hoặc trả lỗi cho người dùng.

Với **asynchronous messaging**, producer gửi message tới broker hoặc nền tảng truyền sự kiện rồi tiếp tục công việc của mình. Consumer nhận và xử lý message vào thời điểm phù hợp. Producer không cần giữ một RPC mở cho tới khi consumer hoàn tất.

Messaging phù hợp khi:

- Công việc có thể hoàn tất sau response ban đầu, ví dụ gửi email, tạo báo cáo hoặc xử lý thanh toán nền.
- Producer và consumer cần hoạt động độc lập, có thể deploy và scale riêng.
- Hệ thống cần hấp thụ burst traffic bằng queue hoặc log bền vững.
- Một sự kiện cần được nhiều consumer xử lý độc lập.
- Consumer có thể tạm ngừng và xử lý lại message sau khi phục hồi.
- Quy trình nghiệp vụ gồm nhiều bước và không cần một response đồng bộ duy nhất.

Messaging không tự động làm nghiệp vụ hoàn tất nhanh hơn. Nó chuyển thời điểm xử lý sang sau và giúp tách phụ thuộc thời gian giữa các service. Người dùng có thể nhận trạng thái ACCEPTED/PENDING trước, rồi truy vấn kết quả hoặc nhận notification khi xử lý xong.

## 2. Phân biệt messaging với asynchronous gRPC

Một gRPC client có thể dùng async stub, callback hoặc future để không block thread gọi. Tuy nhiên, đó vẫn là một RPC: client gọi một endpoint cụ thể, call có deadline, và kết quả cuối cùng gắn với service được gọi.

Messaging tạo ra ranh giới khác:

- Producer gửi message tới broker, không cần consumer cụ thể đang online.
- Broker giữ message theo durability/retention policy.
- Consumer độc lập nhận message và xác nhận xử lý.
- Producer và consumer có thể scale, restart hoặc deploy vào thời điểm khác nhau.
- Một message có thể được phân phối cho một consumer group hoặc nhiều subscription tùy broker.

| Tiêu chí | gRPC RPC | Asynchronous messaging |
| --- | --- | --- |
| Quan hệ | Caller gọi service cụ thể | Producer gửi tới destination/topic |
| Thời điểm xử lý | Thường trong thời gian call | Consumer xử lý sau khi nhận |
| Kết quả | Response hoặc gRPC status | Ack/receipt khi publish; kết quả nghiệp vụ có thể đến sau |
| Phụ thuộc availability | Caller cần endpoint có thể nhận call | Broker cần nhận message; consumer có thể tạm offline nếu message được lưu |
| Buffering | Không phải durable queue mặc định | Broker có thể lưu và phân phối lại |
| Fan-out | Caller phải gọi nhiều service hoặc dùng orchestration | Một event có thể có nhiều subscription/consumer group |
| Deadline | Có deadline cho RPC | Cần expiry/TTL và business deadline ở cấp message |
| Phù hợp | Query/command cần kết quả ngay | Workflows nền, event, buffering và loose coupling |

Async gRPC giúp caller không block thread nhưng không thay thế broker khi cần lưu message bền vững, replay, fan-out hoặc consumer độc lập.

## 3. Chọn command hay event

Hai loại message thường gặp có ý nghĩa khác nhau:

- **Command** diễn đạt yêu cầu thực hiện một hành động: ReserveStock, SendInvoice hoặc GenerateReport. Nó thường hướng tới một nhóm xử lý có trách nhiệm thực hiện command.
- **Event** diễn đạt một sự kiện đã xảy ra: OrderCreated, StockReserved hoặc PaymentSettled. Nó mô tả sự thật trong domain và có thể được nhiều consumer quan tâm.

Tên event thường dùng thì quá khứ vì sự kiện đã xảy ra. Consumer không nên sửa ý nghĩa lịch sử của event; nếu trạng thái mới xuất hiện, producer phát event mới.

Ví dụ khi OrderService tạo đơn:

1. OrderService lưu đơn thành công.
2. Hệ thống phát OrderCreated.
3. BillingService tạo yêu cầu thanh toán.
4. NotificationService gửi thông báo.
5. AnalyticsService cập nhật dữ liệu phân tích.

OrderService không cần gọi tuần tự cả ba service để hoàn tất request tạo đơn. Tuy nhiên, nếu nghiệp vụ yêu cầu biết ngay việc thanh toán có được chấp nhận hay không, cần thiết kế response đồng bộ hoặc quy trình trạng thái rõ ràng thay vì giả vờ rằng publish event đồng nghĩa thanh toán đã thành công.

## 4. Message broker và event streaming

Broker/queue và event log có thể cùng hỗ trợ giao tiếp bất đồng bộ nhưng có đặc tính vận hành khác nhau:

| Đặc tính | Queue/message broker | Event log/stream platform |
| --- | --- | --- |
| Cách tiêu thụ | Message thường được phân phối cho một consumer trong nhóm cạnh tranh | Consumer đọc log theo offset/vị trí riêng |
| Lưu trữ | Thường xóa/loại message sau ack theo policy | Thường giữ message theo retention, không phụ thuộc consumer đã đọc |
| Replay | Phụ thuộc dead-letter/requeue và broker | Có thể đọc lại từ offset cũ trong retention |
| Routing | Có thể routing qua exchange, binding và queue | Thường partition theo key/topic |
| Trường hợp phù hợp | Work distribution, command queue, routing | Event history, throughput lớn, nhiều consumer độc lập |

RabbitMQ thường được dùng cho queue và routing linh hoạt. Kafka thường được dùng cho partitioned event log, consumer group và replay. Cả hai đều có nhiều khả năng hơn bảng so sánh rút gọn này; chọn dựa trên durability, ordering, retention, routing, throughput và năng lực vận hành của đội ngũ.

Không chọn broker chỉ theo số message/giây quảng cáo. Kiểm tra latency publish/consume, kích thước message, số partition/queue, replication, retention, failover và chi phí vận hành.

## 5. Kiến trúc producer, broker và consumer

~~~mermaid
flowchart LR
  A["Order API / OrderService"] -->|"Publish OrderCreated"| B["Message Broker"]
  B --> C["Billing Consumer"]
  B --> D["Notification Consumer"]
  B --> E["Analytics Consumer"]
  C --> F["Billing Database"]
  D --> G["Notification Provider"]
  E --> H["Analytics Store"]
~~~

Producer chịu trách nhiệm tạo message có schema và identity ổn định. Broker chịu trách nhiệm tiếp nhận, lưu trữ và phân phối theo cấu hình. Consumer chịu trách nhiệm xác minh, xử lý nghiệp vụ và xác nhận message đã được xử lý theo semantics của broker.

Producer nhận được broker acknowledgement chỉ chứng minh broker đã nhận message theo mức durability được cấu hình. Nó không chứng minh consumer đã hoàn thành nghiệp vụ. Nếu cần biết kết quả xử lý, thiết kế trạng thái operation, callback event hoặc query API riêng.

## 6. Chọn messaging cùng gRPC trong Spring

Trong kiến trúc **SPRING_GRPC**, có thể dùng gRPC cho tương tác đồng bộ nội bộ và broker cho workflow bất đồng bộ:

- REST controller nhận request từ browser.
- Spring application service gọi gRPC để lấy dữ liệu cần ngay.
- Sau khi lưu thay đổi nghiệp vụ, service phát event qua broker.
- Consumer Spring xử lý email, báo cáo, indexing hoặc bước workflow tiếp theo.

Ví dụ: OrderService gọi InventoryService qua gRPC để kiểm tra hoặc giữ tồn kho trong luồng có phản hồi tức thì. Khi đơn đã được ghi nhận, OrderService phát OrderCreated để BillingService và NotificationService xử lý độc lập.

Không dùng broker để thay một query cần response ngay nếu caller không có cơ chế nhận kết quả sau. Cũng không dùng gRPC RPC tuần tự để phát một event cho nhiều consumer khi broker fan-out là semantics phù hợp hơn.

## 7. Thiết kế message contract bằng Protobuf

Nếu hệ thống đã dùng Protocol Buffers cho gRPC, có thể dùng Protobuf message làm payload của broker. Điều này tái sử dụng schema/code generation nhưng không có nghĩa broker đang chạy giao thức gRPC; broker chỉ vận chuyển byte payload.

~~~proto
syntax = "proto3";

package acme.orders.events.v1;

option java_package = "com.acme.orders.events";
option java_multiple_files = true;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  string customer_id = 3;
  int64 occurred_at_epoch_millis = 4;
  string correlation_id = 5;
}
~~~

Các trường event_id và correlation_id có mục đích khác nhau:

- event_id định danh duy nhất một sự kiện, hỗ trợ deduplication.
- correlation_id liên kết các bước trong cùng một luồng nghiệp vụ hoặc trace.
- order_id là aggregate/resource identifier.
- occurred_at biểu diễn thời điểm nghiệp vụ; không dùng timestamp nhận ở consumer thay thế thời điểm event xảy ra.

Đặt package/version cho schema và tuân thủ quy tắc tương thích Protobuf. Không tái sử dụng field number đã xóa. Consumer cũ phải bỏ qua field mới chưa biết và producer không nên thay đổi ý nghĩa field hiện có.

## 8. Publish message với Spring Kafka

Ví dụ sau dùng Spring Kafka với payload là Protobuf serialized bytes. Producer dùng order ID làm record key để các event cùng order có thể được định tuyến vào cùng partition theo partitioner mặc định:

~~~java
@Component
final class OrderEventPublisher {
    private final KafkaTemplate<String, byte[]> kafkaTemplate;

    OrderEventPublisher(KafkaTemplate<String, byte[]> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    CompletableFuture<SendResult<String, byte[]>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "order-created.v1",
            event.getOrderId(),
            event.toByteArray());
    }
}
~~~

Đoạn mã minh họa API Spring Kafka 3.x. Cấu hình serializer, broker, acknowledgement, replication và timeout cần được thiết lập theo môi trường. Gửi thành công ở client API chưa đồng nghĩa message đã được lưu bền vững nếu cấu hình broker/producer không bảo đảm mức durability cần thiết.

Nếu publish là bước quan trọng của transaction nghiệp vụ, không chỉ gọi KafkaTemplate sau khi commit rồi bỏ qua lỗi. Process có thể crash giữa lúc database commit và lúc publish. Phần transactional outbox bên dưới giải quyết cửa sổ lỗi này.

## 9. Nhận message với Spring Kafka

Consumer có thể dùng @KafkaListener để xử lý payload:

~~~java
@Component
final class BillingOrderConsumer {
    private final BillingApplicationService billing;

    BillingOrderConsumer(BillingApplicationService billing) {
        this.billing = billing;
    }

    @KafkaListener(
        topics = "order-created.v1",
        groupId = "billing-service")
    void onOrderCreated(ConsumerRecord<String, byte[]> record)
            throws InvalidProtocolBufferException {
        OrderCreated event = OrderCreated.parseFrom(record.value());
        billing.createInvoice(event);
    }
}
~~~

Listener container quản lý việc poll và acknowledgement theo cấu hình. Nếu handler ném exception, error handler/container quyết định retry, seek, recover hoặc dead-letter theo policy đã thiết lập. Không tự nuốt exception rồi coi message đã xử lý thành công.

Consumer cần xác thực schema/payload và kiểm tra event ID trước khi thực hiện side effect. Với message không parse được, ghi nhận lỗi có kiểm soát và đưa vào dead-letter flow thay vì retry vô hạn một payload hỏng.

## 10. Delivery guarantee: at-most-once và at-least-once

Messaging không mặc nhiên bảo đảm mỗi message chỉ được xử lý đúng một lần:

- **At-most-once:** message có thể bị mất nhưng không được giao lại theo policy. Phù hợp một số telemetry có thể bỏ qua.
- **At-least-once:** message được giao lại khi broker/client không chắc consumer đã xử lý và ack. Có thể tạo duplicate delivery.
- **Effectively-once business effect:** consumer xử lý at-least-once nhưng dùng idempotency/deduplication để side effect logic chỉ xảy ra một lần.

Một tình huống phổ biến: consumer ghi invoice vào database thành công nhưng chết trước khi commit offset/ack. Khi khởi động lại, broker giao message lần nữa. Nếu consumer không có idempotency, invoice có thể được tạo trùng.

Broker có tính năng transaction hoặc exactly-once processing trong phạm vi nhất định, nhưng phạm vi đó không tự động bao gồm mọi database, email provider hay HTTP API bên ngoài. Cần thiết kế end-to-end theo ranh giới transaction thực tế.

## 11. Idempotent consumer và inbox

Consumer nên dùng event_id làm khóa deduplication. Một bảng inbox có unique constraint trên event_id giúp nhận diện event đã xử lý:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong một transaction database:

1. Thử insert event_id vào processed_event.
2. Nếu unique key đã tồn tại, event đã được xử lý; bỏ qua side effect lặp.
3. Nếu insert thành công, thực hiện thay đổi nghiệp vụ.
4. Commit inbox record và business changes cùng transaction.
5. Chỉ ack/commit offset sau khi transaction hoàn tất theo acknowledgement mode đã chọn.

Nếu side effect nằm ngoài database transaction, ví dụ gọi payment provider, cần idempotency key hoặc workflow compensation tương ứng. Inbox không thể tự làm một HTTP call bên ngoài trở thành atomic với database.

## 12. Transactional outbox tránh mất event

Giả sử OrderService lưu order vào database rồi publish OrderCreated:

- Nếu commit database trước và process crash trước publish, order tồn tại nhưng event bị mất.
- Nếu publish trước rồi database rollback, consumer nhận event cho order không tồn tại.

Transactional outbox ghi business data và event record vào cùng một database transaction:

~~~text
BEGIN TRANSACTION
  INSERT order (...)
  INSERT outbox_event (event_id, aggregate_id, event_type, payload, ...)
COMMIT

Outbox relay:
  đọc event chưa publish
  publish tới broker
  khi broker xác nhận -> đánh dấu event đã publish
~~~

Outbox relay có thể publish lặp nếu broker đã nhận message nhưng relay crash trước khi đánh dấu published. Vì vậy consumer vẫn phải idempotent. Outbox giải quyết tính nhất quán giữa database và ý định publish, không tự bảo đảm exactly-once end-to-end.

Có thể triển khai relay bằng polling hoặc CDC tùy hệ thống. Cần theo dõi backlog, số lần retry và tuổi của event chưa publish.

## 13. Ordering và partition key

Thứ tự message thường chỉ được bảo đảm trong một phạm vi cụ thể, không phải toàn hệ thống. Với Kafka, message cùng key thường được đưa vào cùng partition và thứ tự được giữ trong partition. Với queue broker, thứ tự có thể bị ảnh hưởng bởi nhiều consumer, redelivery và retry.

Nếu nghiệp vụ yêu cầu OrderCreated trước OrderPaid cho cùng order, chọn key theo order_id và giữ consumer processing phù hợp. Nếu dùng nhiều worker xử lý song song cùng partition hoặc tự đưa message vào executor không kiểm soát, thứ tự nghiệp vụ có thể bị phá ở tầng ứng dụng.

Không chọn key có cardinality thấp hoặc một key duy nhất cho mọi message nếu điều đó tạo hot partition. Thiết kế partition key cân bằng giữa ordering cần thiết và phân phối tải.

## 14. Retry, backoff và dead-letter queue

Consumer có thể gặp lỗi tạm thời như database unavailable hoặc dependency timeout. Policy nên phân biệt:

- Lỗi tạm thời: retry có giới hạn, backoff tăng dần và jitter.
- Lỗi dữ liệu/contract không hợp lệ: không retry vô hạn; chuyển dead-letter hoặc quarantine.
- Lỗi nghiệp vụ cần can thiệp: lưu trạng thái thất bại và phát tín hiệu vận hành.
- Quá số lần thử: chuyển dead-letter queue/topic, giữ metadata lỗi và nguồn gốc message.

Retry ngay lập tức có thể tạo retry storm và làm dependency đang lỗi quá tải hơn. Với queue, retry/requeue có thể chặn message sau nếu broker giữ thứ tự; cân nhắc retry queue có delay hoặc dead-letter routing.

Dead-letter queue không phải thùng rác. Cần quy trình quan sát, sửa lỗi, replay có kiểm soát và tránh phát lại message độc hại hoặc đã lỗi thời.

## 15. TTL, expiry và business deadline

Message có thể được giữ lâu trong broker khi consumer chậm. Không phải mọi command đều còn hữu ích sau vài giờ. Ví dụ yêu cầu gửi mã OTP hoặc cập nhật trạng thái tạm thời có thể hết hạn.

Đặt expiry/TTL khi semantics cho phép và mang business deadline trong message nếu consumer cần kiểm tra tính hợp lệ. Broker TTL có thể loại message khỏi queue theo policy, nhưng consumer vẫn nên xác minh deadline nghiệp vụ trước side effect.

Không sao chép gRPC deadline trực tiếp thành message TTL mà không xem xét khác biệt: gRPC deadline giới hạn một call; message có thể chờ trong broker và được xử lý nhiều phút sau. Với async workflow, deadline thuộc operation logic và cần được truyền qua message.

## 16. Consumer concurrency và backpressure

Consumer nhanh hơn producer thì lag thấp; producer nhanh hơn consumer thì backlog tăng. Broker hấp thụ burst nhưng không tạo năng lực xử lý vô hạn.

Các biện pháp kiểm soát:

- Chọn số partition/queue và consumer instance theo throughput.
- Giới hạn concurrency và số message poll/prefetch.
- Dùng bounded executor/queue nếu handler dispatch công việc nền.
- Theo dõi consumer lag và tuổi message lâu nhất.
- Pause/resume consumption khi downstream quá tải.
- Giới hạn kích thước message và tổng byte đang xử lý.
- Scale consumer theo lag nhưng không vượt giới hạn database/API phụ thuộc.

Tăng consumer count không luôn tăng throughput. Nếu mọi consumer cùng ghi một database đã bão hòa, scale có thể làm lỗi và retry tăng nhanh hơn.

## 17. Schema evolution và compatibility

Producer và consumer có thể deploy lệch thời điểm. Vì vậy, message schema phải tương thích qua nhiều phiên bản:

- Ưu tiên thêm field optional có default semantics rõ.
- Không tái sử dụng field number Protobuf đã xóa; dùng reserved.
- Consumer cũ phải bỏ qua field mới chưa biết.
- Không đổi ý nghĩa field hoặc enum value đã phát hành.
- Version topic/subject khi thay đổi không tương thích.
- Kiểm tra producer mới với consumer cũ và ngược lại trong contract test.

Nếu dùng Protobuf, payload byte cần được parse bằng schema phù hợp. Có thể dùng package version/topic version hoặc schema registry để quản lý contract. Đừng giả định cùng topic đồng nghĩa mọi producer/consumer đã dùng cùng generated code.

## 18. Observability và trace context

Một RPC đồng bộ có thể đo thời gian từ lúc client gửi tới lúc nhận response. Với messaging, cần đo nhiều mốc:

- Thời điểm producer tạo event.
- Thời điểm broker nhận/ack.
- Thời điểm consumer bắt đầu xử lý.
- Thời điểm consumer commit/ack.
- Tổng event age và processing duration.
- Consumer lag, retry count, DLQ count và outbox backlog.

Đưa event_id, correlation_id và trace context vào message header hoặc envelope theo convention. Consumer tiếp tục trace từ producer để quan sát workflow qua nhiều service. Không dùng event_id hoặc customer_id làm metric label có cardinality cao; dùng trace/log cho định danh chi tiết.

Theo dõi cả tỷ lệ publish failure và consumer failure. Producer publish thành công nhưng consumer lag tăng vẫn là dấu hiệu workflow không hoàn tất kịp.

## 19. Bảo mật message broker

Giao tiếp bất đồng bộ cần bảo mật cả transport lẫn quyền truy cập:

- TLS bảo vệ kết nối producer/consumer tới broker.
- Authentication và authorization giới hạn ai được publish/consume topic hoặc queue.
- Tách credential theo service và áp dụng least privilege.
- Không đưa secret hoặc dữ liệu nhạy cảm không cần thiết vào event.
- Mã hóa payload ở tầng ứng dụng khi yêu cầu threat model đòi hỏi.
- Có retention, backup và deletion policy phù hợp với dữ liệu cá nhân.
- Quản lý schema/topic ACL và audit hoạt động quản trị.

Message có thể tồn tại trong broker, replication log, DLQ và backup lâu hơn một RPC. Thiết kế payload tối thiểu và retention policy phải xét cả vòng đời dữ liệu.

## 20. Kiểm thử messaging trong Spring

Một bộ test nên chia theo mục đích:

1. Unit test cho handler: xác minh business logic với event hợp lệ và không hợp lệ.
2. Serialization/contract test: producer và consumer dùng schema tương thích.
3. Integration test với broker thật hoặc Testcontainers: publish, consume, ack và retry.
4. Idempotency test: giao cùng event hai lần nhưng chỉ tạo một business effect.
5. Failure-window test: consumer crash sau DB commit trước ack; message được giao lại an toàn.
6. Outbox test: transaction commit tạo outbox row; relay publish và xử lý publish lặp.
7. DLQ test: message poison được chuyển đúng nơi sau retry policy.
8. Ordering test: cùng aggregate key được xử lý theo thứ tự contract yêu cầu.

Không chỉ dùng mock KafkaTemplate/RabbitTemplate để kết luận broker delivery guarantee hoạt động. Mock hữu ích cho unit test nhưng không kiểm tra broker, serialization wire, offset/ack, routing hoặc redelivery.

## 21. Lỗi thường gặp khi chọn messaging

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng messaging cho query cần response ngay | Caller không có kết quả để tiếp tục | Dùng gRPC/REST hoặc thiết kế async operation có status API. |
| Coi broker ack là consumer hoàn tất | Báo thành công quá sớm | Phân biệt publish acknowledgement và business completion. |
| Giả định exactly-once end-to-end | Side effect vẫn có thể bị lặp | Dùng idempotency, inbox/outbox và transaction boundary rõ. |
| Retry vô hạn hoặc không backoff | Retry storm và backlog tăng | Giới hạn attempts, backoff, DLQ. |
| Không có event ID | Khó deduplicate và trace | Định danh event duy nhất. |
| Không xác định partition key | Mất ordering cần thiết hoặc hot partition | Chọn key theo aggregate và throughput. |
| Consumer xử lý quá nhiều message đồng thời | Quá tải DB và phá thứ tự | Giới hạn concurrency/queue. |
| Thay schema không tương thích | Consumer cũ không parse/hiểu event | Version và contract test. |
| Nuốt exception rồi ack | Mất message dù business chưa hoàn tất | Để error handler áp retry/recover policy. |
| Không theo dõi lag và DLQ | Workflow chậm hoặc thất bại không được phát hiện | Đo event age, lag, retry và DLQ. |

## 22. Ma trận quyết định

| Câu hỏi | Nếu câu trả lời là “có” | Hướng cân nhắc |
| --- | --- | --- |
| Caller cần kết quả ngay trong cùng request? | Có | gRPC hoặc REST thường phù hợp. |
| Công việc có thể xử lý sau response ban đầu? | Có | Messaging là ứng viên tốt. |
| Cần buffer khi consumer tạm offline? | Có | Chọn broker có durability phù hợp. |
| Một event cần nhiều consumer độc lập? | Có | Topic/fan-out hoặc nhiều subscription. |
| Cần replay lịch sử event? | Có | Event log/stream retention có lợi thế. |
| Cần routing queue linh hoạt cho command/work item? | Có | Message broker queue/routing có thể phù hợp. |
| Side effect phải tránh lặp? | Có | Thiết kế idempotency/inbox/outbox trước khi bật retry. |
| Cần ordering theo aggregate? | Có | Chọn partition/routing key và concurrency phù hợp. |

Messaging chỉ phù hợp khi đội ngũ chấp nhận eventual consistency, vận hành broker, quản lý schema và theo dõi backlog. Nếu không cần buffering hoặc tách thời điểm, RPC đồng bộ có thể đơn giản hơn.

## 23. Bài tập thực hành

Thiết kế luồng tạo đơn hàng trong hệ Spring:

1. Browser gọi REST API để tạo order.
2. OrderService gọi InventoryService qua gRPC nếu cần phản hồi kiểm tra tồn kho ngay.
3. OrderService lưu order và OrderCreated event trong cùng transaction bằng outbox.
4. Outbox relay publish Protobuf payload tới topic.
5. BillingService và NotificationService consume event bằng Spring listener.
6. Consumer dùng event_id để idempotent và không tạo side effect trùng.
7. Cấu hình retry có giới hạn, backoff và DLQ.
8. Chọn key theo order_id để giữ thứ tự event của cùng order.
9. Theo dõi publish acknowledgement, consumer lag, event age, processing duration và DLQ.
10. Kiểm thử consumer redelivery sau khi database commit nhưng trước acknowledgement.

**Tiêu chí hoàn thành:** xác định rõ phần nào cần gRPC đồng bộ, phần nào dùng messaging, có delivery/retry/idempotency policy, schema tương thích và cách quan sát workflow khi consumer chậm hoặc lỗi.

## 24. Ghi nhớ

- Messaging tách thời điểm producer và consumer, hỗ trợ buffering, fan-out và xử lý nền.
- Async gRPC vẫn là RPC; nó không tự cung cấp durable queue hoặc replay.
- Command là yêu cầu hành động; event là sự kiện đã xảy ra.
- Broker acknowledgement không chứng minh consumer đã hoàn thành nghiệp vụ.
- At-least-once có thể giao trùng; idempotent consumer và inbox giúp bảo vệ side effect.
- Transactional outbox tránh mất event giữa database commit và publish; consumer vẫn phải chịu duplicate.
- Ordering thường chỉ có trong queue/partition/key scope, không phải toàn hệ thống.
- Retry cần giới hạn, backoff và DLQ; poison message không nên retry vô hạn.
- Schema phải tương thích khi producer và consumer deploy lệch phiên bản.
- Theo dõi event age, consumer lag, retry, DLQ và outbox backlog để biết workflow có hoàn tất kịp hay không.
- Dùng gRPC cho tương tác đồng bộ cần response; dùng messaging cho công việc có thể xử lý sau và cần tách thời điểm.

Chọn messaging cho giao tiếp bất đồng bộ khi hệ thống cần tách producer khỏi consumer, hấp thụ tải và xử lý công việc nền bền vững; kết hợp gRPC cho các bước cần kết quả đồng bộ để mỗi interaction dùng đúng semantics.
