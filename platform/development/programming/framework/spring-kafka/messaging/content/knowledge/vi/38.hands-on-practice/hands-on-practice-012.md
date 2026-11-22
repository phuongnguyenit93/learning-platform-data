# Tổng kết kiến trúc và điểm đánh đổi

Một ứng dụng Spring Kafka đáng tin cậy không chỉ cần gửi và nhận được record. Nó cần một kiến trúc nhất quán từ lúc sự kiện được tạo, serialize, publish, lưu trong Kafka, phân phối tới consumer, xử lý nghiệp vụ, xác nhận offset cho tới khi lỗi được retry hoặc đưa vào dead-letter topic. Mỗi lựa chọn đều có đánh đổi về độ bền dữ liệu, thứ tự, độ trễ, throughput, khả năng phục hồi, chi phí vận hành và mức độ phức tạp.

Bài tổng kết này kết nối các phần đã học trong module **SPRING_KAFKA_MESSAGING** thành một kiến trúc event-driven có thể triển khai và vận hành. Mục tiêu không phải chọn cấu hình mạnh nhất cho mọi hệ thống, mà là chọn đúng cơ chế cho yêu cầu nghiệp vụ, xác định rõ phạm vi bảo đảm và biết phải đo điều gì để kiểm chứng.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Vẽ và giải thích kiến trúc producer, Kafka cluster, consumer group và downstream service.
- Chọn ranh giới giữa synchronous API, event publication và asynchronous processing.
- Thiết kế topic, partition key, consumer group và ordering requirement.
- Chọn serializer, type header, schema version và chiến lược schema evolution.
- Phân biệt at-most-once, at-least-once và exactly-once trong phạm vi Kafka.
- Kết hợp retry, dead-letter, idempotency và replay an toàn.
- Chọn Kafka transaction, database outbox/inbox hoặc saga theo ranh giới dữ liệu.
- Cân bằng throughput, latency, concurrency, partition count và resource capacity.
- Thiết kế bảo mật bằng TLS, SASL và ACL.
- Xây dựng observability, integration test, runbook và quy trình rollout.
- Ghi lại các quyết định kiến trúc cùng lý do và trade-off.

## 1. Bức tranh kiến trúc tổng thể

Một luồng event-driven thường gồm các thành phần:

~~~mermaid
flowchart LR
    A[API / Domain Service] --> B[Database Transaction]
    B --> C[Outbox]
    C --> D[Outbox Relay / CDC]
    D --> E[Kafka Topic]
    E --> F[Consumer Group A]
    E --> G[Consumer Group B]
    F --> H[Business Service A]
    G --> I[Business Service B]
    F --> J[Retry / DLT]
    G --> K[Retry / DLT]
~~~

Một cách triển khai khác là publish trực tiếp bằng `KafkaTemplate` sau khi nghiệp vụ tạo event. Cách này đơn giản hơn, nhưng nếu service vừa commit database vừa gửi Kafka thì cần xử lý failure window giữa hai hệ thống. Khi cần bảo đảm thay đổi database và ý định phát event được ghi cùng nhau, outbox thường là lựa chọn phù hợp.

Kafka giữ vai trò event log phân tán. Producer và consumer không cần biết trực tiếp implementation của nhau; chúng phối hợp thông qua topic, key, headers và event contract.

## 2. Chọn ranh giới giữa command và event

Command yêu cầu một service thực hiện hành động; event mô tả điều đã xảy ra.

| Khái niệm | Ví dụ | Đặc điểm |
|---|---|---|
| Command | `CreateOrder` | Có người nhận chịu trách nhiệm thực hiện và có thể từ chối. |
| Event | `OrderCreated` | Mô tả sự kiện đã xảy ra; có thể có nhiều consumer độc lập. |
| Query | `GetOrderStatus` | Yêu cầu đọc trạng thái hiện tại. |

Không phải mọi lời gọi API đều nên chuyển thành Kafka event. Nếu caller cần câu trả lời đồng bộ để tiếp tục, HTTP/gRPC có thể phù hợp hơn. Kafka phù hợp khi cần tách thời điểm xử lý, fan-out cho nhiều consumer, hấp thụ burst hoặc lưu event để xử lý lại.

Một API có thể trả về `202 Accepted` sau khi ghi command/outbox, nhưng cần định nghĩa rõ trạng thái “đã nhận” khác với “nghiệp vụ đã hoàn tất”.

## 3. Event contract là giao diện giữa các service

Event nên mô tả dữ liệu nghiệp vụ ổn định, không phơi bày cấu trúc database hoặc class nội bộ của producer.

Ví dụ:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        int eventVersion,
        Instant occurredAt,
        String customerId,
        BigDecimal total,
        String currency
) {}
~~~

Các trường nên có mục đích rõ ràng:

- `eventId`: định danh duy nhất để idempotency và tracing.
- `orderId`: aggregate/business identifier.
- `eventVersion`: phiên bản contract theo quy ước của hệ thống.
- `occurredAt`: thời điểm nghiệp vụ xảy ra.
- Các trường nghiệp vụ cần thiết cho consumer, tránh gửi dữ liệu dư thừa.

Không đưa password, token hoặc dữ liệu cá nhân không cần thiết vào event. Event có thể được lưu trong Kafka retention, DLT, log và hệ thống archive lâu hơn vòng đời request ban đầu.

## 4. Topic, partition key và ordering

Kafka bảo đảm thứ tự trong một partition. Kafka không tạo thứ tự toàn cục giữa nhiều partition.

Nếu các event của cùng order cần được xử lý theo thứ tự, dùng `orderId` làm key:

~~~java
kafkaTemplate.send(
        "orders.events",
        event.orderId(),
        event
);
~~~

Điểm đánh đổi:

| Quyết định | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| Ít partition | Ít overhead, dễ quản lý ordering | Ít khả năng song song. |
| Nhiều partition | Tăng khả năng consumer song song | Tăng metadata, replica, file segment và chi phí vận hành. |
| Key theo aggregate | Giữ thứ tự trong một aggregate | Key nóng có thể tạo partition skew. |
| Không key | Có thể phân phối đều hơn tùy partitioner | Không giữ thứ tự theo aggregate. |

Tăng partition count có thể làm key được ánh xạ sang partition khác đối với record mới. Nếu ordering dài hạn quan trọng, cần có kế hoạch migration hoặc sequence/version trong event trước khi mở rộng partition.

## 5. Consumer group và khả năng song song

Mỗi consumer group có offset riêng. Nhiều group có thể đọc cùng topic độc lập; trong một group, partition được phân phối cho các consumer member.

Ví dụ topic có 6 partition:

- Một group có 3 consumer có thể phân phối 2 partition cho mỗi consumer.
- Một group có 8 consumer chỉ có tối đa 6 consumer nhận partition từ topic đó tại một thời điểm.
- Hai group khác nhau có thể cùng đọc toàn bộ 6 partition và tiến offset độc lập.

Concurrency nên được chọn dựa trên partition count, thời gian xử lý, CPU, connection pool và năng lực downstream. Tăng concurrency vượt partition count không tự tăng throughput.

## 6. Producer: độ bền, retry và batching

Producer configuration cần phản ánh mức độ quan trọng của event.

Ví dụ cấu hình nền tảng thường dùng:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
~~~

Ý nghĩa và trade-off:

- `acks=all`: chờ acknowledgement theo ISR và `min.insync.replicas`; tăng durability nhưng có thể từ chối ghi khi ISR không đủ.
- Idempotent producer: ngăn duplicate do retry ở tầng producer protocol; không chống mọi lần ứng dụng chủ động gửi lại cùng event.
- Retry và delivery timeout: cần giới hạn thời gian gửi; retry vô hạn có thể giữ buffer và làm tăng latency.
- Batching/linger: tăng hiệu quả network nhưng có thể thêm thời gian chờ trước khi gửi.
- Compression: giảm byte truyền/lưu nhưng tiêu tốn CPU.

Không tối ưu producer chỉ dựa trên throughput. Hãy đo send latency, error rate, buffer wait và kết quả consumer.

## 7. Consumer: offset và delivery semantics

Với consumer thông thường, at-least-once là lựa chọn phổ biến: xử lý record thành công rồi mới commit offset.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

| Semantics | Cách xác nhận | Đánh đổi |
|---|---|---|
| At-most-once | Commit trước xử lý | Có thể mất record khi process dừng sau commit. |
| At-least-once | Xử lý rồi commit | Có thể redeliver và cần idempotency. |
| Exactly-once Kafka | Output và input offset cùng Kafka transaction | Phức tạp hơn; chỉ bao phủ thao tác trong Kafka transaction. |

Không nên diễn giải exactly-once là listener chỉ chạy một lần. Listener có thể chạy lại sau rollback; điều được bảo vệ là kết quả Kafka đã commit trong pipeline consume-transform-produce được cấu hình đúng.

## 8. Idempotency là hàng rào cho side effect

At-least-once có thể giao lại record. Consumer nên dùng `eventId` ổn định để chống lặp side effect.

Một mô hình inbox:

~~~text
Database transaction:
  1. Insert eventId into inbox (unique constraint)
  2. If already exists: skip business mutation
  3. Apply business mutation
  4. Commit
~~~

Unique constraint phải nằm trong cùng database transaction với thay đổi nghiệp vụ. Chỉ gọi `existsById` rồi insert mà không có ràng buộc duy nhất vẫn có race condition khi hai consumer xử lý đồng thời.

Idempotency không có nghĩa bỏ qua mọi record có cùng payload. Event ID phải đại diện cho một sự kiện logic duy nhất; nếu producer tạo ID mới mỗi lần retry nghiệp vụ, consumer không thể nhận diện duplicate.

## 9. Kafka transaction và phạm vi exactly-once

Kafka transaction phù hợp khi một lần xử lý cần ghi nhiều output topic/partition và commit input offset nguyên tử.

~~~mermaid
flowchart TD
    A[Consume input] --> B[Transform]
    B --> C[Begin Kafka transaction]
    C --> D[Produce output records]
    D --> E[Add input offsets]
    E --> F{Commit}
    F -->|Success| G[Output visible and offset advances]
    F -->|Abort| H[Output aborted and input can replay]
~~~

Consumer downstream cần `isolation.level=read_committed` để chỉ nhìn thấy output của transaction đã commit.

Kafka transaction không tự rollback database, HTTP call, email hoặc object storage. Nếu listener cập nhật database rồi transaction Kafka abort, database có thể vẫn đã commit. Với ranh giới database/Kafka, cân nhắc outbox/inbox hoặc saga/compensation.

## 10. Outbox: phối hợp database và Kafka

Outbox giải quyết failure window giữa database commit và publish event:

1. Trong một database transaction, cập nhật bảng nghiệp vụ.
2. Cùng transaction đó, insert outbox row.
3. Commit database.
4. Relay hoặc CDC đọc outbox và publish sang Kafka.
5. Đánh dấu/đối soát trạng thái relay theo thiết kế.

Nếu relay publish thành công nhưng chưa ghi nhận đã gửi, event có thể được publish lại. Vì vậy consumer vẫn cần idempotency.

Outbox tăng độ tin cậy nhưng thêm bảng, relay/CDC, monitoring, retention và quy trình xử lý outbox backlog. Nó không tự tạo exactly-once end-to-end.

## 11. Retry: phục hồi lỗi tạm thời

Phân loại lỗi trước khi chọn retry:

| Loại lỗi | Hướng xử lý |
|---|---|
| Network/database timeout tạm thời | Retry có giới hạn và backoff. |
| Rate limit/downstream unavailable | Retry có giới hạn, tôn trọng retry-after nếu có. |
| Payload/schema sai cố định | Không retry vô hạn; đưa vào recovery/DLT. |
| Business rule không hợp lệ | Xử lý theo nghiệp vụ hoặc reject có audit. |
| Authentication/authorization sai | Sửa credential/ACL; retry vô hạn không giúp ích. |

Blocking retry giữ partition bị ảnh hưởng trong lúc chờ, có thể duy trì thứ tự nhưng giảm throughput. Non-blocking retry topic giải phóng luồng chính nhanh hơn, nhưng event retry có thể quay lại sau các event mới hơn và làm thay đổi ordering. Chọn theo yêu cầu nghiệp vụ.

## 12. Dead-letter topic và replay

DLT lưu record không thể xử lý sau retry/recovery. Một DLT workflow cần:

- Giữ raw key/value và headers cần thiết.
- Lưu original topic, partition, offset và exception metadata.
- Có owner, trạng thái case và retention.
- Phân loại nguyên nhân trước khi replay.
- Gắn replay ID và audit trail.
- Replay thử một record hoặc batch nhỏ.
- Kiểm tra idempotency, trạng thái aggregate và ordering.
- Giới hạn tốc độ replay để tránh tạo tải đột biến.

Replay record cũ không đưa nó về offset cũ. Khi publish lại, record có offset mới; nếu ordering quan trọng, consumer phải kiểm tra sequence/version hoặc dùng quy trình recovery riêng.

## 13. Serialization và schema evolution

JSON serializer/deserializer thuận tiện, nhưng type header chứa FQCN có thể coupling producer với package Java của consumer. Dùng token ổn định qua type mapping khi nhiều event type cần polymorphic deserialization.

Ví dụ wire token:

~~~text
__TypeId__ = order-created
~~~

Producer và consumer ánh xạ token đó tới class nội bộ riêng. Token type không thay thế event version hoặc schema compatibility. Với hệ thống nhiều ngôn ngữ hoặc cần governance chặt, cân nhắc Avro, Protobuf hoặc JSON Schema cùng Schema Registry.

Quy tắc rollout: consumer phải hỗ trợ token/schema mới trước khi producer phát dữ liệu mới. Kiểm thử cả record cũ còn trong retention và payload mới trong giai đoạn rolling deployment.

## 14. Bảo mật: identity, transport và quyền

Một kết nối Kafka production thường cần kết hợp:

- TLS để mã hóa kết nối và xác minh broker certificate.
- SASL để xác thực client, ví dụ SCRAM hoặc OAUTHBEARER theo nền tảng.
- ACL để giới hạn principal được đọc/ghi topic, dùng consumer group hoặc transactional ID.
- Secret management để cấp, rotation và thu hồi credential.

Authentication thành công không đồng nghĩa có quyền đọc/ghi. Dùng principal riêng theo vai trò khi phù hợp và cấp quyền tối thiểu. Không commit secret, JAAS password, token hoặc private key vào repository/log.

## 15. Hiệu năng và capacity planning

Ba nhóm chỉ số cần nhìn cùng nhau:

| Chỉ số | Ý nghĩa |
|---|---|
| Throughput | Số record hoặc byte xử lý mỗi giây. |
| Latency | Thời gian từ mốc bắt đầu tới mốc kết thúc đã định nghĩa. |
| Consumer lag | Khoảng cách offset giữa log end và committed offset theo partition. |

Đo p50/p95/p99, không chỉ average. Theo dõi retry/DLT, producer buffer wait, listener processing time, database pool wait, broker disk/network và rebalance.

Benchmark cần warm-up, steady state, payload thực tế, key distribution thực tế và offered load rõ ràng. Open-loop load test giúp thấy backlog khi hệ thống chậm; closed-loop có thể tự giảm tốc và che giấu quá tải.

## 16. Observability: đo để biết luồng đang khỏe

Một dashboard tối thiểu nên có:

- Producer acknowledged/failed rate và send latency.
- Consumer processing rate và p95/p99.
- Lag theo topic/partition/group.
- Listener error, retry và DLT incoming/backlog.
- Rebalance và partition assignment.
- Broker offline partitions, under-replicated partitions, ISR shrink.
- Transaction commit/abort và fencing.
- CPU, heap, GC, disk, network và downstream latency.

Log nên liên kết bằng event ID, correlation ID, topic, partition, offset, group ID và service version. Không dùng event ID hoặc customer ID làm metric label có cardinality cao.

## 17. Kiểm thử theo nhiều tầng

| Tầng test | Mục tiêu | Công cụ/gợi ý |
|---|---|---|
| Unit | Business mapping, validation, idempotency logic | JUnit, Mockito, AssertJ. |
| Serializer/contract | JSON bytes, type headers, version compatibility | ObjectMapper, contract fixtures. |
| Spring Kafka integration | Listener, producer, ack, retry, DLT | EmbeddedKafka. |
| Broker integration | Broker version, transactions, security, metadata | Testcontainers hoặc Kafka test cluster. |
| Failure test | Crash window, rebalance, timeout, broker interruption | Fault injection có kiểm soát. |
| Load test | Throughput, latency, lag và capacity | Open-loop/closed-loop generator. |

Kafka xử lý bất đồng bộ; test cần Awaitility, BlockingQueue, CountDownLatch hoặc consumer polling có deadline. Tránh Thread.sleep cố định, polling vô hạn và dùng chung group/topic khiến test đọc dữ liệu cũ.

## 18. Vận hành và thay đổi có kiểm soát

Mỗi topic cần có owner và baseline:

- Partition count, replication factor.
- Retention và cleanup policy.
- Min ISR và producer acknowledgement expectations.
- ACL và service principal.
- Schema/type token và version policy.
- Consumer group và expected lag.
- DLT destination, owner và replay procedure.

Khi tăng partition, đánh giá key remapping và ordering. Khi reset offset, xác định rõ record sẽ bị bỏ qua hay đọc lại. Khi replay DLT, sửa nguyên nhân trước và xác minh idempotency. Khi rotation secret, theo dõi tất cả instance đã dùng credential mới trước khi thu hồi credential cũ.

## 19. Ma trận lựa chọn kiến trúc

| Yêu cầu | Lựa chọn thường phù hợp | Đánh đổi cần chấp nhận |
|---|---|---|
| Publish event đơn giản, không có DB side effect cùng transaction | KafkaTemplate + idempotent producer | Ứng dụng vẫn phải xử lý send failure và duplicate nghiệp vụ. |
| DB update phải đi cùng ý định phát event | Transactional outbox | Thêm relay/CDC và quản lý backlog. |
| Consumer chỉ cập nhật DB, cần chống redelivery | At-least-once + inbox/idempotency | Có thể nhận lại record nhưng side effect được dedupe. |
| Kafka consume-transform-produce cần output/offset atomic | Kafka transaction + read_committed | Thêm transaction coordination và giới hạn timeout. |
| Cần giữ thứ tự theo aggregate | Key theo aggregate ID, xử lý tuần tự trong partition | Hot key giới hạn song song. |
| Cần phục hồi lỗi tạm thời | Retry có giới hạn và backoff | Tăng latency hoặc backlog. |
| Cần cô lập poison pill | DLT + quarantine/replay workflow | Cần owner, retention và thao tác recovery. |
| Nhiều event type trong JSON topic | Stable type mapping hoặc envelope discriminator | Cần quản lý token/schema contract. |
| Nhiều ngôn ngữ và schema governance | Schema Registry với Avro/Protobuf/JSON Schema | Thêm registry và compatibility workflow. |
| Bảo vệ cluster production | SASL_SSL + ACL + secret management | Cần vận hành certificate, credential và policy. |

Đây là điểm xuất phát, không phải quy tắc tuyệt đối. Quyết định cuối cùng phải dựa trên SLA, data loss tolerance, duplicate tolerance, ordering, volume và năng lực đội vận hành.

## 20. Reference flow: Order Service

Một kiến trúc tham khảo cho đơn hàng:

1. API nhận lệnh tạo đơn.
2. Database transaction lưu Order và OutboxEvent.
3. Outbox relay publish `OrderCreated` lên `orders.events`, key là orderId.
4. Fulfillment consumer group đọc event và dùng inbox/eventId để chống xử lý trùng.
5. Consumer phát `OrderAccepted` hoặc `OrderRejected` tùy kết quả.
6. Notification consumer group độc lập đọc event phù hợp để gửi thông báo.
7. Lỗi tạm thời retry có giới hạn; lỗi không thể phục hồi chuyển DLT.
8. Operator điều tra DLT, sửa nguyên nhân và replay có kiểm soát.
9. Dashboard theo dõi producer, lag, listener latency, retry, DLT và broker health.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as Order DB + Outbox
    participant R as Outbox Relay
    participant K as Kafka
    participant F as Fulfillment Consumer
    participant N as Notification Consumer
    API->>DB: Save order + outbox in one DB transaction
    DB-->>API: Commit
    R->>DB: Read unpublished outbox rows
    R->>K: Publish OrderCreated (key=orderId)
    K-->>R: Broker acknowledgement
    K->>F: Deliver to fulfillment group
    F->>F: Inbox/idempotency + business update
    K->>N: Deliver to notification group
    N->>N: Send notification idempotently
~~~

Các consumer group có thể xử lý độc lập. Nếu notification chậm, fulfillment vẫn có thể tiếp tục; nếu fulfillment lỗi, retry/DLT của group đó được quản lý riêng.

## 21. Các câu hỏi cần trả lời trước khi production

Trước khi đưa một pipeline vào production, nhóm nên trả lời:

1. Event nào là contract công khai giữa service?
2. Event ID được tạo ở đâu và có ổn định qua retry không?
3. Key nào giữ ordering theo aggregate?
4. Partition count và replication factor dựa trên tải nào?
5. Producer acknowledgement và min ISR có đáp ứng durability mong muốn không?
6. Consumer commit offset sau điều kiện nào?
7. Duplicate side effect được ngăn bằng cơ chế nào?
8. DB update và Kafka publish có cần outbox không?
9. Retry lỗi nào, tối đa bao nhiêu lần và backoff bao lâu?
10. DLT ai sở hữu, giữ bao lâu và replay theo quy trình nào?
11. Schema/type token được version và rollout ra sao?
12. Principal nào được đọc/ghi topic và group?
13. Dashboard nào chứng minh luồng đang khỏe?
14. Ai trực và runbook nào được dùng khi incident?
15. Test nào chứng minh crash, retry, rebalance và recovery an toàn?

Nếu chưa có câu trả lời cho data ownership, duplicate, ordering và recovery, pipeline chưa sẵn sàng chỉ vì producer/consumer demo chạy thành công.

## 22. Bài tập tổng hợp cuối module

Thiết kế và triển khai một hệ thống Order Messaging với các yêu cầu:

**Luồng dữ liệu**

- API tạo order và lưu database.
- Event `OrderCreated` được publish qua outbox.
- Topic có key theo orderId và nhiều partition.
- Fulfillment và Notification là hai consumer group độc lập.
- Fulfillment cập nhật trạng thái đơn bằng inbox/idempotency.
- Notification gửi thông báo có cơ chế chống gửi trùng phù hợp.

**Độ tin cậy**

- Producer dùng acknowledgement/idempotence phù hợp.
- Consumer dùng at-least-once và commit sau xử lý.
- Kafka transaction được dùng nếu có pipeline Kafka-to-Kafka cần atomic output/offset.
- Retry có giới hạn; poison pill vào DLT.
- Replay DLT có event ID, replay ID, audit và giới hạn tốc độ.
- Ordering theo orderId được kiểm tra bằng sequence/version.

**Contract và security**

- JSON type token ổn định hoặc schema registry.
- Có quy tắc event version và rolling compatibility.
- Kết nối SASL_SSL, principal riêng và ACL tối thiểu.
- Secret lấy từ secret manager và có rotation plan.

**Quan sát và kiểm thử**

- Dashboard producer/consumer throughput, p95/p99, lag, retry, DLT và broker health.
- Integration test với EmbeddedKafka hoặc Testcontainers.
- Test duplicate, crash window, transaction abort, rebalance, deserialize failure và replay.
- Load test với key distribution và payload đại diện.
- Runbook cho producer outage, lag, DLT backlog và partition degradation.

**Tiêu chí hoàn thành**

- Không mất ý định phát event khi database transaction đã commit.
- Duplicate delivery không tạo side effect nghiệp vụ lặp.
- Consumer group có thể phục hồi sau restart/rebalance.
- Record lỗi có thể điều tra và replay có kiểm soát.
- Ordering requirement được chứng minh trong phạm vi đã cam kết.
- Security principal chỉ có quyền cần thiết.
- Throughput/latency đạt SLA đã định nghĩa và có headroom.
- Đội vận hành có dashboard, owner và runbook.

## 23. Thứ tự hoàn thiện kiến trúc

| Chặng | Quyết định | Bằng chứng cần có |
|---|---|---|
| 1. Domain contract | Event, ID, version, ownership | Contract và ví dụ payload. |
| 2. Topic design | Topic, key, partition, retention | Ordering requirement và capacity estimate. |
| 3. Producer | Serializer, acks, idempotence, retry | Send metrics và failure tests. |
| 4. Consumer | Group, concurrency, AckMode | Offset behavior và lag dashboard. |
| 5. Reliability | Idempotency, retry, DLT | Duplicate/recovery tests. |
| 6. Consistency | Kafka transaction hoặc outbox/inbox | Failure-window test. |
| 7. Security | TLS, SASL, ACL, secrets | Positive/negative authorization tests. |
| 8. Performance | Throughput, p95/p99, capacity | Repeatable benchmark. |
| 9. Operations | Alert, runbook, ownership | Incident drill và recovery evidence. |
| 10. Release | Compatibility, rollout, rollback | Consumer-first rollout plan và version matrix. |

Bài học hoàn thành khi bạn có thể giải thích vì sao kiến trúc chọn từng cơ chế, điều gì được bảo đảm, điều gì có thể xảy ra khi lỗi và đội vận hành sẽ phục hồi ra sao. Một kiến trúc tốt không loại bỏ mọi failure; nó làm cho failure có thể phát hiện, giới hạn, điều tra và phục hồi mà vẫn bảo vệ dữ liệu nghiệp vụ.

Spring Kafka cung cấp các building block như KafkaTemplate, listener container, error handler, transaction manager và serializer/deserializer. Độ tin cậy cuối cùng đến từ cách ghép chúng với event contract, partition strategy, idempotency, outbox/inbox, security, observability và quy trình vận hành phù hợp với yêu cầu thực tế.

