# Khi gRPC phù hợp hơn messaging và ngược lại

## 1. Chọn theo nhu cầu giao tiếp

Trong hệ sinh thái Spring gRPC, gRPC và messaging giải quyết hai kiểu tương tác khác nhau:

- **gRPC** phù hợp khi một thành phần cần gọi một thành phần khác và nhận kết quả trong cùng luồng xử lý. Contract Protocol Buffers định nghĩa service, method và message; caller có thể áp dụng deadline, cancellation và xử lý status ngay tại điểm gọi.
- **Messaging** phù hợp khi producer gửi một message để consumer xử lý độc lập, có thể muộn hơn. Broker giúp tách thời điểm gửi và nhận, lưu message trong thời gian cấu hình, phân phối tới nhiều consumer và hỗ trợ retry hoặc replay theo khả năng của nền tảng.

Không có lựa chọn luôn tốt hơn. Câu hỏi quyết định là: caller có cần câu trả lời ngay để tiếp tục hay chỉ cần công việc được ghi nhận và xử lý đáng tin cậy sau đó?

Ví dụ, trang checkout cần xác thực giá và tồn kho trước khi hiển thị kết quả có thể gọi gRPC tới các service tương ứng. Khi đơn hàng đã được chấp nhận, việc gửi sự kiện OrderCreated để email, analytics và fulfillment xử lý độc lập thường phù hợp với messaging.

## 2. So sánh bản chất hai mô hình

| Tiêu chí | gRPC | Messaging qua broker |
| --- | --- | --- |
| Kiểu tương tác | Request-response hoặc stream trực tiếp | Producer gửi message, consumer nhận và xử lý |
| Thời điểm phản hồi | Caller thường chờ kết quả của RPC | Producer thường chỉ chờ broker xác nhận nhận message |
| Coupling thời gian | Caller và server cần cùng sẵn sàng trong thời gian call | Producer và consumer có thể hoạt động ở thời điểm khác nhau |
| Contract | Service/method và message trong Protobuf | Event/command schema và quy tắc broker |
| Durability | Không tự tạo hàng đợi lưu request để xử lý sau khi server offline | Có thể lưu message theo retention và replication của broker |
| Fan-out | Caller phải gọi nhiều đích hoặc dùng một service trung gian | Một event có thể được nhiều consumer group nhận độc lập |
| Replay | Không có replay RPC mặc định | Có thể replay theo retention/offset hoặc cơ chế broker |
| Flow control | HTTP/2 và gRPC stream flow control | Producer/consumer rate, prefetch, partition và broker controls |
| Failure | Status, deadline, cancellation, retry của RPC | Redelivery, retry topic, dead-letter queue và consumer offset |
| Quan sát | Call rate, status, latency, deadline, in-flight | Publish/consume rate, lag, redelivery, DLQ, processing time |

Một RPC thành công có nghĩa server đã trả terminal result theo contract. Một publish thành công thường chỉ có nghĩa broker đã nhận message theo mức acknowledgement được cấu hình; nó không chứng minh consumer đã hoàn tất nghiệp vụ.

## 3. Khi nào gRPC là lựa chọn phù hợp?

Ưu tiên gRPC khi có một hoặc nhiều điều kiện sau:

1. **Cần kết quả ngay:** caller phải biết thao tác thành công, thất bại hoặc trả dữ liệu để tiếp tục luồng nghiệp vụ.
2. **Tương tác có contract rõ:** service cung cấp API có kiểu dữ liệu, versioning và code generation từ Protobuf.
3. **Latency thấp là yêu cầu:** các service nội bộ cần trao đổi trực tiếp, không cần chờ message được consumer lấy ra khỏi broker.
4. **Cần deadline và cancellation:** caller có ngân sách thời gian và muốn dừng call khi không còn cần kết quả.
5. **Cần stream trực tiếp:** server-streaming, client-streaming hoặc bidirectional streaming giữa hai endpoint đang kết nối.
6. **Cần status cụ thể:** caller phân biệt NOT_FOUND, INVALID_ARGUMENT, PERMISSION_DENIED, UNAVAILABLE hoặc DEADLINE_EXCEEDED.

Ví dụ: OrderService gọi InventoryService để kiểm tra số lượng còn khả dụng trước khi xác nhận đơn. Caller cần kết quả kiểm tra ngay để quyết định có chấp nhận đơn hay không.

~~~java
import java.util.concurrent.TimeUnit;

GetAvailabilityResponse availability =
        inventoryStub
                .withDeadlineAfter(300, TimeUnit.MILLISECONDS)
                .getAvailability(
                        GetAvailabilityRequest.newBuilder()
                                .setSku(sku)
                                .setQuantity(quantity)
                                .build());
~~~

Đoạn code giả định inventoryStub là generated blocking stub được tạo từ channel do ứng dụng/Spring gRPC quản lý. Deadline giới hạn thời gian chờ cho call; server và dependency vẫn cần xử lý cancellation, timeout riêng và không tiếp tục công việc vô ích khi call đã hết hạn.

## 4. Khi nào messaging phù hợp hơn?

Ưu tiên messaging khi:

1. **Không cần kết quả ngay:** producer chỉ cần ghi nhận yêu cầu hoặc phát sự kiện.
2. **Consumer có thể tạm offline:** broker lưu message để consumer xử lý khi hoạt động trở lại, trong giới hạn durability và retention.
3. **Một sự kiện có nhiều bên quan tâm:** nhiều consumer group xử lý cùng một event mà producer không cần biết từng consumer.
4. **Tải đến theo burst:** broker hấp thụ backlog trong giới hạn dung lượng, consumer xử lý theo capacity.
5. **Cần replay hoặc audit stream:** message được giữ đủ lâu và có thể đọc lại theo chính sách broker.
6. **Cần tách vòng đời:** producer và consumer triển khai, scale hoặc release độc lập.

Ví dụ: sau khi OrderService tạo đơn, nó phát OrderCreated. NotificationService gửi email, AnalyticsService cập nhật số liệu và FulfillmentService chuẩn bị giao hàng. OrderService không cần chờ cả ba consumer hoàn tất mới trả kết quả checkout.

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
                "order-created",
                event.orderId(),
                event);
    }
}
~~~

Ví dụ dùng Spring Kafka để minh họa publisher. Việc send bất đồng bộ cần xử lý kết quả gửi, lỗi broker, timeout và retry theo cấu hình thực tế. Không coi việc gọi send() là bằng chứng event đã được consumer xử lý.

## 5. Phân biệt RPC streaming với messaging

Streaming trong gRPC và messaging đều chuyển nhiều message, nhưng semantics khác nhau:

| Đặc điểm | gRPC streaming | Messaging |
| --- | --- | --- |
| Quan hệ | Một RPC stream giữa client và server | Producer/consumer giao tiếp qua broker |
| Vòng đời | Gắn với call, channel và deadline/cancellation | Gắn với message retention và subscription |
| Consumer offline | Stream không tự lưu message để consumer đọc lại sau | Broker có thể giữ message cho consumer đọc sau |
| Replay | Không có replay broker mặc định | Có thể replay theo offset/retention nếu broker hỗ trợ |
| Backpressure | Stream flow control và readiness | Consumer demand, prefetch, partition/queue và broker flow |
| Delivery | Message thuộc một call đang mở | Delivery/redelivery theo broker và acknowledgement |

Server-streaming phù hợp cho live updates khi client đang kết nối, ví dụ theo dõi trạng thái tác vụ trên một màn hình đang mở. Nếu người dùng có thể offline rồi quay lại và cần nhận mọi event bỏ lỡ, broker hoặc một event store có replay sẽ phù hợp hơn.

Bidirectional streaming không biến gRPC thành message broker. Nó vẫn là một RPC có peer, transport và vòng đời call cụ thể; server phải xử lý cancellation, reconnect và trạng thái client biến mất.

## 6. Ma trận quyết định theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Đọc hồ sơ người dùng để trả HTTP/gRPC response | gRPC | Cần dữ liệu ngay |
| Kiểm tra giá/tồn kho trước khi xác nhận đơn | gRPC | Cần kết quả để quyết định đồng bộ |
| Gửi email sau khi đơn được tạo | Messaging | Có thể xử lý sau, không giữ caller chờ |
| Phát OrderCreated cho nhiều domain | Messaging | Fan-out và consumer độc lập |
| Theo dõi tiến độ tác vụ đang chạy trên UI | gRPC server-streaming hoặc SSE | Cần cập nhật trực tiếp khi client online |
| Gửi telemetry số lượng lớn để xử lý theo lô | Messaging/stream platform | Buffer, throughput và consumer độc lập |
| Yêu cầu tạo báo cáo chạy vài phút | Messaging + query/status API | Ghi nhận job rồi xử lý bất đồng bộ |
| Gọi service kiểm tra quyền trước thao tác | gRPC hoặc local policy service | Cần quyết định trước side effect |
| Đồng bộ trạng thái giữa nhiều hệ thống | Messaging/event-driven, đôi khi kèm gRPC query | Cần eventual consistency và phát lại |
| Upload stream dữ liệu trực tiếp tới service | gRPC client-streaming nếu cần xử lý trong phiên | Stream có contract và phản hồi trực tiếp |

Đây là gợi ý theo semantics, không phải quy tắc cứng. Quyết định cuối cần xét latency, durability, volume, ordering, consumer count, operational maturity và failure model.

## 7. Mô hình kết hợp: gRPC cho command, messaging cho event

Một kiến trúc thường hiệu quả là dùng gRPC cho lệnh cần phản hồi ngay và messaging cho sự kiện phát sinh sau khi nghiệp vụ được chấp nhận:

~~~mermaid
sequenceDiagram
    participant C as Checkout client
    participant O as OrderService
    participant I as InventoryService
    participant DB as Order database
    participant R as Outbox relay
    participant B as Message broker
    participant N as Notification consumer
    participant F as Fulfillment consumer

    C->>O: CreateOrder RPC
    O->>I: CheckAvailability RPC
    I-->>O: Available
    O->>DB: Save order + outbox record
    DB-->>O: Commit
    O-->>C: Order accepted
    R->>DB: Read unpublished outbox rows
    R->>B: Publish OrderCreated
    B-->>R: Broker acknowledgement
    B->>N: Deliver event
    B->>F: Deliver event
    N-->>B: Acknowledge
    F-->>B: Acknowledge
~~~

Trong luồng này:

- gRPC kiểm tra tồn kho và trả kết quả cho caller.
- OrderService lưu order và outbox record trong cùng transaction.
- Outbox relay publish event sau commit.
- Consumer xử lý độc lập và có thể retry mà không giữ checkout request mở.

Mô hình này tránh dual-write: nếu ghi database thành công nhưng publish broker thất bại, outbox record vẫn còn để relay thử lại. Cần thiết kế unique event ID và consumer idempotency để xử lý trường hợp relay publish lại sau khi không nhận được acknowledgement.

## 8. Không dùng gRPC làm hàng đợi công việc

Một lỗi thiết kế là client gửi RPC, server nhận request rồi trả OK ngay, sau đó giữ task trong memory để xử lý khi rảnh. Nếu process restart hoặc server crash, task có thể mất. Caller lại tưởng công việc đã được lưu bền vững.

Nếu API cần nhận job để xử lý sau:

1. Ghi job vào storage/broker có durability phù hợp.
2. Chỉ trả accepted sau khi hệ thống xác nhận đã lưu theo contract.
3. Trả job ID để caller truy vấn trạng thái.
4. Worker xử lý job độc lập với RPC ban đầu.
5. Dùng gRPC query/status API hoặc event notification để báo tiến độ.

gRPC vẫn có thể là API để submit job và query status; messaging đảm nhiệm việc phân phối công việc bền vững.

## 9. Delivery semantics, retry và idempotency

Không nên giả định messaging luôn bảo đảm exactly-once end-to-end. Broker có thể cung cấp các mức delivery/transaction khác nhau, nhưng side effect ở database hoặc service ngoài broker vẫn cần thiết kế riêng.

| Mối quan tâm | gRPC | Messaging |
| --- | --- | --- |
| Retry | Client retry policy, status retryable, deadline và backoff | Broker redelivery, retry topic/queue, consumer retry |
| Duplicate | Client retry có thể gửi lại operation sau lỗi không rõ kết quả | At-least-once delivery có thể giao message nhiều lần |
| Idempotency | Idempotency key hoặc operation ID cho command có side effect | Event ID/inbox deduplication và idempotent handler |
| Ordering | Thứ tự trong một stream/call theo contract | Thứ tự thường theo partition/queue và broker guarantee |
| Dead letter | Không có DLQ RPC mặc định | Có thể chuyển message lỗi lâu dài sang DLQ |
| Timeout | Deadline của RPC | Publish/consume timeout và processing lease/visibility timeout |

Ví dụ client mất kết nối sau khi server đã commit CreateOrder nhưng trước khi nhận response. Client không biết thao tác đã thành công hay chưa. Retry mù có thể tạo đơn thứ hai. Dùng idempotency key gắn với logical command để server trả lại kết quả đã có.

Với consumer, lưu event ID đã xử lý trong inbox/deduplication store hoặc dùng unique constraint cùng transaction. Handler phải chịu được việc cùng event được giao lại.

## 10. Transaction boundary và Outbox/Inbox

Không thực hiện hai thao tác độc lập là commit database rồi publish broker mà không có cơ chế khôi phục. Có thể xảy ra:

- Database commit thành công nhưng publish thất bại.
- Publish thành công nhưng transaction database rollback.
- Broker đã nhận message nhưng publisher timeout trước khi nhận acknowledgement và publish lại.

Transactional outbox giải quyết khoảng hở giữa database transaction và publish:

1. Trong cùng transaction, ghi business data và outbox event.
2. Relay đọc outbox chưa publish.
3. Relay gửi event tới broker.
4. Sau acknowledgement, đánh dấu event đã publish.
5. Nếu relay crash trước khi đánh dấu, event có thể được publish lại; consumer phải idempotent.

Inbox hoặc deduplication store giúp consumer tránh áp dụng cùng event nhiều lần. Outbox không tạo exactly-once toàn hệ thống; nó giúp bảo đảm event không bị mất giữa commit và publish, còn duplicate vẫn cần xử lý.

## 11. Ordering và fan-out

Nếu consumer cần xử lý event theo thứ tự của một aggregate, dùng aggregate ID làm partition key hoặc routing key tùy broker. Không giả định thứ tự toàn cục giữa nhiều partition hay queue.

Fan-out nên dùng một subscription/consumer group riêng cho từng chức năng độc lập. Ví dụ NotificationService và FulfillmentService cần mỗi bên nhận OrderCreated. Nếu hai instance cùng nằm trong một consumer group theo semantics cạnh tranh của broker, một message thường chỉ được một instance trong group xử lý, không phải cả hai chức năng.

Với gRPC, fan-out thường do caller gọi nhiều service hoặc một orchestration service thực hiện. Cần tính đến latency cộng dồn, partial failure và retry của từng downstream. Nếu các consumer không cần kết quả ngay và cần xử lý độc lập, event broker thường đơn giản hơn.

## 12. Bảo mật và quản trị vận hành

gRPC và messaging có bề mặt bảo mật khác nhau:

| Khía cạnh | gRPC | Messaging |
| --- | --- | --- |
| Transport | TLS/mTLS trên channel | TLS tới broker và giữa broker nodes |
| Identity | Certificate, token, CallCredentials | Broker credential, workload identity, SASL/OAuth tùy nền tảng |
| Authorization | Quyền gọi method và truy cập resource | ACL/topic/queue/consumer group permission |
| Data exposure | Metadata, payload, logs và traces | Message payload, headers, broker logs và DLQ |
| Schema governance | Protobuf service/message compatibility | Event schema registry/versioning và consumer compatibility |
| Observability | RPC status, latency, deadline, in-flight | Publish/consume rate, lag, retry, redelivery, DLQ |

Không chuyển nguyên bearer token của người dùng vào event nếu consumer không cần credential đó. Event nên mang dữ liệu nghiệp vụ tối thiểu và actor/audit context đã được xác minh theo contract.

## 13. Chỉ số vận hành cần theo dõi

Với gRPC:

- Request rate theo method.
- Latency p50/p95/p99.
- Status distribution, đặc biệt UNAVAILABLE và DEADLINE_EXCEEDED.
- Retry attempts và retry recovery.
- In-flight calls, active streams và cancellation.
- Executor queue, rejection và dependency latency.

Với messaging:

- Publish rate và publish acknowledgement latency.
- Consumer throughput và processing duration.
- Consumer lag hoặc queue depth.
- Redelivery/retry count.
- Dead-letter queue depth.
- Age của message cũ nhất.
- Partition/consumer imbalance và broker availability.

Một hệ thống hybrid cần correlation ID/trace context xuyên qua ranh giới RPC và message. Khi publish event, inject trace context vào message headers theo propagator; consumer extract context để tạo processing span. Không dùng trace ID làm metric label.

## 14. Checklist chọn mô hình

Trước khi chọn gRPC hoặc messaging, trả lời:

1. Caller có cần kết quả nghiệp vụ ngay không?
2. Server/consumer có thể offline khi request được gửi không?
3. Message có cần được lưu bền vững và replay không?
4. Có bao nhiêu consumer độc lập cần nhận cùng một event?
5. Caller có cần deadline, cancellation và status đồng bộ không?
6. Tải có burst lớn và consumer cần xử lý chậm hơn producer không?
7. Ordering cần theo một aggregate hay toàn hệ thống?
8. Retry có thể tạo duplicate side effect không?
9. Hệ thống có outbox, idempotency và DLQ phù hợp không?
10. Đội vận hành đã có năng lực quản lý broker, lag và schema evolution chưa?

Nếu câu trả lời nghiêng về kết quả tức thì và contract call rõ, chọn gRPC. Nếu nghiêng về durability, decoupling, fan-out, replay và consumer độc lập, chọn messaging. Nếu một luồng có cả hai nhu cầu, dùng hybrid với ranh giới command/event rõ ràng.

## 15. Bài tập vận dụng

Thiết kế luồng tạo đơn hàng:

1. Dùng gRPC CreateOrder để caller nhận kết quả chấp nhận hoặc từ chối trong deadline.
2. Gọi InventoryService bằng gRPC để kiểm tra tồn kho đồng bộ.
3. Lưu order và OrderCreated outbox event trong cùng transaction.
4. Publish event tới broker sau commit.
5. Tạo NotificationService và FulfillmentService trong hai consumer group độc lập.
6. Thiết kế event ID, idempotent consumer và retry/DLQ.
7. Cung cấp gRPC GetOrderStatus để caller truy vấn tiến độ fulfillment khi cần.
8. Theo dõi RPC latency/status song song với broker lag/redelivery.
9. Mô phỏng broker offline sau khi order commit và chứng minh outbox relay publish lại khi broker phục hồi.
10. Mô phỏng duplicate event và xác minh consumer không tạo side effect trùng.

**Tiêu chí hoàn thành:** người học giải thích được khác biệt giữa RPC đồng bộ và messaging bất đồng bộ; chọn đúng mô hình theo latency, durability, fan-out và replay; phân biệt gRPC streaming với broker; thiết kế được hybrid gRPC-command/messaging-event có outbox, idempotency và quan sát vận hành.

### Tài liệu tham khảo

- [gRPC Concepts](https://grpc.io/docs/what-is-grpc/core-concepts/): service, RPC lifecycle và streaming.
- [gRPC Deadlines](https://grpc.io/docs/guides/deadlines/): giới hạn thời gian cho RPC.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
- [Spring for Apache Kafka](https://docs.spring.io/spring-kafka/reference/): producer, consumer, acknowledgement và error handling.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): topic, partition, consumer group, retention và delivery.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): đồng bộ database transaction với message publish.
- [Idempotent Consumer Pattern](https://microservices.io/post/microservices/patterns/2020/10/16/idempotent-consumer.html): xử lý duplicate message an toàn.
