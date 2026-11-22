# EOS và retry topic

**Exactly-Once Semantics (EOS)** và **retry topic** giải quyết hai vấn đề khác nhau trong hệ thống Spring Kafka. EOS của Kafka hướng tới việc **commit các record đầu ra và offset đầu vào một cách nguyên tử** trong pipeline Kafka-to-Kafka. Retry topic, đặc biệt là **non-blocking retry** của Spring Kafka, đưa một record thất bại sang topic trung gian để xử lý lại sau một khoảng delay, giúp consumer gốc không bị chặn bởi record đó.

Ghép hai khái niệm mà không xác định ranh giới transaction có thể dẫn đến kết luận sai: **“đã bật transaction” không đồng nghĩa “mọi lần chuyển sang retry topic đều exactly-once”**. Một record có thể được ghi vào retry topic rồi bị forward lần nữa khi tiến trình chết trước khi xác nhận offset. Record được retry có thể hoàn tất sau record đến sau nó, làm đảo thứ tự nghiệp vụ. Khi có database, HTTP API hoặc email, Kafka transaction cũng không tự rollback các side effect bên ngoài.

Bài học giải thích mức bảo đảm của từng cơ chế, giới hạn khi kết hợp, thiết kế thay thế và cách quan sát các failure window trong Spring Kafka.

## 1. Xác định chính xác “exactly once” có nghĩa gì

Một event có thể đi qua nhiều bước:

~~~text
Producer -> input topic -> consumer/listener -> output topic -> downstream consumer
                               |
                               +-> database, HTTP API, email...
~~~

Các mức bảo đảm thường gặp:

| Mức bảo đảm | Ý nghĩa | Ví dụ rủi ro |
|---|---|---|
| At-most-once | Có thể mất bản ghi nhưng tránh xử lý lại | Offset được commit trước khi side effect hoàn tất |
| At-least-once | Không chủ đích bỏ mất record, nhưng có thể giao lại | Side effect đã chạy, process chết trước commit offset |
| Kafka EOS cho consume–process–produce | Output Kafka và offset input được commit nguyên tử trong Kafka transaction | Không bao phủ database/HTTP nằm ngoài Kafka transaction |
| Exactly-once business effect | Một tác động nghiệp vụ được áp dụng một lần theo event ID/invariant | Cần idempotency, inbox/outbox hoặc transaction phù hợp |

**EOS không có nghĩa Java listener chỉ chạy một lần.** Nếu Kafka transaction rollback hoặc process chết trước commit, cùng input có thể được listener chạy lại. Điều được bảo vệ là output transactional cùng tiến độ đầu vào của những giao dịch thành công, khi downstream đọc với `isolation.level=read_committed`.

Kafka EOS cũng không tự loại bỏ các *business events trùng nhau* đã được producer publish thành các record khác nhau. Nếu upstream gửi hai record có cùng `eventId`, container transaction có thể xử lý và commit cả hai nếu nghiệp vụ không có deduplication.

## 2. EOS chuẩn của Spring Kafka: output và offset cùng transaction

Trong một listener container được cấu hình Kafka transaction manager, đường xử lý điển hình:

~~~mermaid
sequenceDiagram
    participant K as Input topic
    participant C as Listener container
    participant L as Business listener
    participant P as Transactional Kafka producer
    participant O as Output topic
    K-->>C: Poll record offset N
    C->>P: Begin Kafka transaction
    C->>L: Invoke listener
    L->>P: Send output record
    P-->>O: Write as uncommitted
    L-->>C: Return success
    C->>P: Add input offset to transaction
    C->>P: Commit Kafka transaction
    Note over O: Visible to read_committed consumers
~~~

Nếu listener ném exception hoặc transaction abort, output chưa committed bị ẩn khỏi consumer `read_committed` và offset input không được commit qua transaction thất bại.

| Tình huống | Output transactional | Offset input |
|---|---|---|
| Commit thành công | Có hiệu lực | Được commit trong cùng transaction |
| Abort vì listener lỗi | Không visible với `read_committed` | Không commit bằng transaction đó |
| Process chết trước commit | Có thể bị broker abort/được xử lý theo trạng thái broker | Input có thể được giao lại |
| DB đã commit nhưng Kafka abort | DB vẫn thay đổi | Input có thể được giao lại |

Trường hợp cuối chứng minh ranh giới EOS chỉ nằm trên những tài nguyên thực sự thuộc Kafka transaction.

## 3. Non-blocking retry topic hoạt động ra sao?

Spring Kafka hỗ trợ chuyển record lỗi sang các retry topic thay vì giữ consumer gốc chờ backoff dài. Retry listener đọc record ở topic trung gian và trì hoãn xử lý đến khi đủ thời gian.

~~~text
orders
  |
  +-- listener lỗi
       |
       v
orders-retry-1000    (chờ khoảng 1 giây)
       |
       +-- vẫn lỗi
            |
            v
orders-retry-2000    (chờ khoảng 2 giây)
            |
            +-- vẫn lỗi
                 |
                 v
orders-dlt          (hết retry budget)
~~~

Tên topic chỉ mang tính minh họa; framework có chiến lược hậu tố và reuse topic theo cấu hình. Broker Kafka không tự hiểu rằng topic có hậu tố `1000` thì bắt buộc giữ record chính xác 1.000 ms. Hạ tầng retry listener dùng metadata và cơ chế pause/resume để thực thi delay.

Việc chuyển record sang retry topic tạo **một lần publish mới** với topic, partition, offset riêng. Consumer retry sử dụng consumer group/offset và vòng đời khác với consumer gốc. Nếu không có một transaction được thiết kế để gộp thao tác forward với offset nguồn, sẽ tồn tại khoảng hở có thể tạo duplicate.

## 4. Vì sao EOS và retry topic dễ bị nhầm là tương thích mặc định?

Giả sử record A tại `orders-1@42` thất bại. Một retry mechanism thực hiện:

~~~text
(1) Đọc orders-1@42
(2) Publish A sang orders-retry-1000
(3) Xác nhận/commit offset của orders-1
(4) Sau delay, retry consumer xử lý A
~~~

Nếu hai bước (2) và (3) **không** được commit nguyên tử:

- Publish retry thành công nhưng process chết trước offset commit: A có thể được đọc lại tại topic gốc và được publish thêm một lần sang retry topic.
- Offset commit thành công dù publish retry thật ra thất bại: có nguy cơ làm mất đường xử lý record, nếu error handling sai.
- Retry consumer xử lý xong một side effect nhưng chết trước offset commit của retry topic: A được giao lại và side effect có thể bị lặp.
- Chuyển tiếp tới DLT thành công nhưng chưa commit offset retry: có thể có thêm bản sao DLT sau restart.

Nói cách khác, **retry topic có thể bảo vệ khả năng tiếp tục xử lý bằng at-least-once delivery nhưng không tự đảm bảo exactly-once business effects**.

Kafka transactional producer có thể giúp xây một bước *consume-from-topic-X → produce-to-topic-Y + commit offset của X* nguyên tử, nếu cả hai thực sự nằm cùng Kafka transaction. Nhưng đó là một thiết kế có chủ đích cho từng chặng, không phải bảo đảm tự động phát sinh chỉ nhờ thêm annotation retry topic.

## 5. Giới hạn quan trọng: @RetryableTopic với container transaction

Trong các phiên bản Spring Kafka hỗ trợ retry topic phổ biến, cơ chế **non-blocking retry qua `@RetryableTopic` không được kết hợp trực tiếp với container transactions** theo luồng cấu hình mặc định. Ngoài ra, non-blocking retry topic có những giới hạn riêng với batch listener.

Vì vậy, không nên triển khai:

~~~java
// MINH HỌA MÔ HÌNH CẦN TRÁNH / KHÔNG MẶC ĐỊNH HỖ TRỢ
@RetryableTopic(attempts = "4")
@KafkaListener(
    topics = "orders",
    containerFactory = "transactionalListenerFactory")
public void onMessage(OrderEvent event) {
    // Không được giả định annotation retry và Kafka container
    // transaction ghép thành một EOS pipeline.
}
~~~

Ví dụ này chỉ thể hiện **cấu hình có vấn đề cần tránh**, không phải mẫu code khuyến nghị. Nếu cần chạy Spring Kafka transactional listener, hãy dùng cơ chế rollback và retry tương thích với container transaction hoặc xây topology riêng có ranh giới transaction được xác minh.

Khi nâng phiên bản Spring Kafka, phải xem tài liệu/API của phiên bản dự án để biết mức hỗ trợ chính xác. Không dựa vào một đoạn code thử đơn giản chạy được để suy luận rằng việc chuyển retry topic và offset đang atomic.

## 6. Cấu hình Kafka transaction cho listener

Với trường hợp đọc Kafka rồi ghi Kafka, một cấu hình Spring Boot minh họa:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example:9092,kafka-2.example:9092
    producer:
      transaction-id-prefix: order-transform-instance-01-
      acks: all
    consumer:
      group-id: order-transformer
      enable-auto-commit: false
      isolation-level: read_committed
    listener:
      ack-mode: record
~~~

Những điểm cần chú ý:

- `transaction-id-prefix` phải được quản lý để transactional IDs không trùng giữa những producer/instance cùng hoạt động.
- `enable-auto-commit: false` thể hiện rõ rằng offset do container điều phối thay vì Kafka client tự commit.
- `read_committed` đặc biệt quan trọng với **downstream consumer** đọc output transactional, vì consumer `read_uncommitted` có thể thấy record sau đó bị abort.
- `acks: all` phù hợp với mục tiêu durability của transactional publishing.
- Nếu dùng custom listener factory, cần gắn transaction manager đúng cách; không suy ra toàn bộ factory đều transactional chỉ vì một property tồn tại.

Một transaction manager được tạo từ transactional `ProducerFactory`:

~~~java
@Bean
KafkaTransactionManager<String, OutputEvent> kafkaTransactionManager(
        ProducerFactory<String, OutputEvent> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Gắn vào container factory trong phiên bản hỗ trợ API tương ứng:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, InputEvent>
transactionalListenerFactory(
        ConsumerFactory<String, InputEvent> consumerFactory,
        KafkaTransactionManager<String, OutputEvent> txManager) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, InputEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
           .setKafkaAwareTransactionManager(txManager);
    factory.getContainerProperties()
           .setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
~~~

Đoạn code minh họa cho Spring Kafka dùng `setKafkaAwareTransactionManager`; các phiên bản cũ hơn có thể dùng API khác. Cần đảm bảo `KafkaTemplate` gửi output dùng **cùng transactional producer factory** mà transaction manager đang điều phối.

## 7. Phương án ưu tiên cho EOS: blocking retry và after-rollback

Khi cần Kafka EOS và xử lý lỗi transient, một hướng đơn giản hơn là để container transaction rollback rồi sử dụng **`DefaultAfterRollbackProcessor`** cho seek/retry/recovery thay vì chuyển sang non-blocking retry topic.

~~~mermaid
flowchart TD
    A["Consume từ topic gốc"] --> B["Begin Kafka transaction"]
    B --> C["Listener xử lý, gửi Kafka output"]
    C --> D{"Listener thành công?"}
    D -->|Có| E["Offset + output commit trong tx"]
    D -->|Không| F["Abort transaction"]
    F --> G["AfterRollbackProcessor"]
    G --> H{"Còn retry?"}
    H -->|Có| I["Backoff + seek/đọc lại"]
    I --> A
    H -->|Không| J["Recovery/DLT theo chính sách"]
~~~

Ví dụ cấu hình ý tưởng:

~~~java
@Bean
DefaultAfterRollbackProcessor<String, InputEvent>
afterRollbackProcessor(DeadLetterPublishingRecoverer recoverer) {
    return new DefaultAfterRollbackProcessor<>(
        (record, exception) -> recoverer.accept(record, exception),
        new FixedBackOff(1_000L, 3L)
    );
}
~~~

Gắn processor lên factory:

~~~java
factory.setAfterRollbackProcessor(afterRollbackProcessor);
~~~

`FixedBackOff(1_000L, 3L)` nghĩa là khoảng nghỉ 1 giây và tối đa ba retry theo semantics của `FixedBackOff`. Cần phân loại lỗi dữ liệu permanent để không retry vô ích; các exception fatal có thể cần recover ngay.

**Rất quan trọng:** Chỉ có after-rollback processor và recoverer **không tự chứng minh** việc publish DLT và commit recovered offset cùng một Kafka transaction. Muốn recovery được commit trong một transaction mới, cần cấu hình `commitRecovered` và Kafka operations/template tương ứng theo API và phiên bản Spring Kafka đang dùng.

## 8. Mô hình lựa chọn theo yêu cầu nghiệp vụ

| Yêu cầu quan trọng nhất | Hướng thiết kế |
|---|---|
| Kafka input offset và Kafka output phải cùng commit | Container Kafka transaction + retry/rollback flow tương thích |
| Lỗi thoáng qua, cần giữ thứ tự partition | Blocking retry/backoff sau rollback |
| Lỗi kéo dài, cần giữ throughput topic gốc | Retry topic/workflow riêng, chấp nhận at-least-once và quản lý duplicate |
| Thứ tự từng aggregate/key bắt buộc | Giữ xử lý theo partition hoặc workflow có state/sequence |
| Cần kết hợp retry topic với atomic forward | Thiết kế từng chặng transactional consume→produce→offset, không dựa vào annotation mặc định |
| Xử lý database và Kafka output | Transactional outbox + inbox/idempotency theo invariant |
| Lỗi payload vĩnh viễn | DLT/quarantine, không retry liên tục |
| Retry sau nhiều giờ/ngày | Workflow scheduler bền vững hoặc queue có delay theo thiết kế riêng |

Không có lựa chọn nào tối ưu cho mọi pipeline. Transactional blocking retry có thể giữ một partition lâu; retry topic giúp throughput cao nhưng đánh đổi ordering và làm tăng số chặng phải xử lý duplicate.

## 9. Thứ tự xử lý khi record đi qua retry topic

Kafka duy trì thứ tự **trong một partition của một topic**. Khi record A chuyển sang retry topic, record B trong topic gốc có thể được xử lý trước A.

~~~mermaid
sequenceDiagram
    participant K as orders-1
    participant L as Original listener
    participant R as orders-retry-1000
    participant S as Business state
    K-->>L: A = OrderCreated, offset 10
    L-->>R: Forward A do lỗi
    K-->>L: B = OrderCancelled, offset 11
    L->>S: Apply B
    Note over R: Chờ delay
    R-->>S: Apply A muộn hơn B
~~~

Nếu xử lý B trước A làm state machine sai, non-blocking retry topic có thể không phù hợp. **Kafka transaction không tự bảo toàn ordering xuyên các topic khác nhau.**

Biện pháp:

- Dùng event version/sequence và optimistic locking cho từng aggregate.
- Bỏ qua event cũ đã bị vượt version nếu nghiệp vụ cho phép.
- Lưu event đến sớm vào bảng pending, chỉ áp dụng khi dependency/sequence hợp lệ.
- Chọn blocking retry khi ordering quan trọng hơn throughput.
- Dùng idempotency theo event ID, không dựa đơn thuần vào offset hiện hành.

## 10. Kafka EOS không bao phủ database và HTTP side effects

Giả sử một listener transactional vừa ghi DB vừa publish Kafka:

~~~java
@KafkaListener(
    topics = "payments.received",
    containerFactory = "transactionalListenerFactory")
public void onPayment(PaymentReceived event) {
    paymentService.updateDatabase(event); // DB transaction riêng
    kafkaTemplate.send(
        "payments.applied",
        event.paymentId(),
        new PaymentApplied(event.paymentId())
    );
}
~~~

Một failure window có thể là:

~~~text
1. Kafka container transaction bắt đầu.
2. DB ghi và commit thành công.
3. Kafka output/offset commit thất bại.
4. Input được giao lại sau rollback/restart.
5. Listener cập nhật DB lần nữa nếu không idempotent.
~~~

Kafka transaction không rollback được database transaction đã commit. Retry topic lại có thêm những lần giao từ các topic trung gian nên yêu cầu idempotency càng rõ.

Giải pháp điển hình:

- **Inbox:** ghi event ID đã xử lý và business state cùng một DB transaction.
- **Outbox:** ghi business state và event cần publish trong cùng DB transaction; publisher gửi Kafka sau đó.
- **Idempotency key:** dùng một business ID ổn định cho HTTP/payment API nếu provider hỗ trợ.
- **Saga/workflow:** quản lý tiến độ và compensation khi có nhiều bước hệ thống bên ngoài.

Chỉ thêm `@Transactional` của Spring vào method mà không xác định transaction manager và resource không làm hai hệ thống trở thành một transaction atomic phân tán.

## 11. Ví dụ idempotent consumer cho retry topic

Một event cần giữ ID ổn định qua topic gốc, retry và DLT:

~~~json
{
  "eventId": "evt-91fe",
  "orderId": "order-101",
  "eventType": "OrderApproved",
  "schemaVersion": 2
}
~~~

Ứng dụng có thể dùng unique constraint trên `event_id`:

~~~java
@Service
public class OrderProjectionService {

    @Transactional // transaction của database
    public void apply(OrderApproved event) {
        boolean firstProcessing =
            processedEventRepository.insertIfAbsent(event.eventId());

        if (!firstProcessing) {
            return;
        }

        orderRepository.markApproved(event.orderId());
    }
}
~~~

`insertIfAbsent` là thao tác khái niệm: triển khai bằng insert với unique key và transaction DB thật. Dấu đã xử lý và update nghiệp vụ phải được commit **cùng một DB transaction**.

Tuy nhiên, có một bẫy tinh vi: nếu DB đã commit, Kafka output ở lần đầu bị rollback, rồi lần replay chỉ return sớm vì inbox báo “đã xử lý”, output Kafka cần thiết có thể không bao giờ được gửi. Với pipeline kết hợp DB+Kafka, phải dùng outbox hoặc cơ chế tái tạo output nhất quán từ state đã commit, không chỉ thêm inbox là xong.

Đối với Kafka-only transform, container transaction giải quyết atomicity output/offset tốt hơn việc commit offset thủ công. Idempotency theo business event ID vẫn cần nếu producer hoặc các retry stages có thể tạo nhiều record chứa cùng event ID.

## 12. Định danh giao dịch và read_committed khi có nhiều stage

Một Kafka transaction dùng `transactional.id` để xác định producer. Khi scale nhiều consumer instances hoặc listener concurrency, transactional IDs phải được quản lý để tránh producer fencing.

~~~text
pod-A: transaction-id-prefix = orders-tx-A-
pod-B: transaction-id-prefix = orders-tx-B-
pod-C: transaction-id-prefix = orders-tx-C-
~~~

Nếu hai producer đồng thời dùng cùng transactional ID, broker có thể fence một producer. Những lỗi như `ProducerFencedException` không phải lỗi dữ liệu của một record nên cần xử lý ở tầng lifecycle/transaction, không đẩy record đó qua mọi retry topic một cách vô nghĩa.

Đối với topic retry do ứng dụng tự xây bằng Kafka transactions, **mỗi chặng** cần xác định:

1. Producer transactional nào đang publish sang chặng kế tiếp?
2. Offset của consumer thuộc chặng hiện tại có được gửi vào cùng transaction không?
3. Consumer đọc chặng kế tiếp có `read_committed` không?
4. Có bước publish/commit nào nằm ngoài transaction?
5. Cách phục hồi khi process chết giữa transaction là gì?

Một chặng được bảo vệ bằng Kafka EOS không tự làm toàn bộ business workflow exactly-once nếu chặng khác dùng at-least-once publishing hoặc side effect ngoài Kafka.

## 13. Thêm transaction thủ công vào retry pipeline có đủ không?

Về nguyên lý, có thể xây một hệ thống retry topic custom mà mỗi lần forward được thực hiện trong một transaction:

~~~text
Retry stage X:
  begin Kafka transaction
  read record from X
  publish same business event to Y
  send consumed offset of X to transaction
  commit

Retry stage Y:
  read_committed consumer nhận record
~~~

Nếu mọi chặng thực hiện đúng, atomicity của từng lần forward có thể được bảo vệ. Nhưng việc triển khai phải xử lý thêm:

- Transaction lifecycle và producer fencing.
- Quy tắc delay, timestamp, pause/resume partition.
- DLT publish và recovered offset.
- Lỗi serialization ở forward producer.
- Rebalance và partition assignment.
- Idempotency của business handler.
- Ordering xuyên topics.
- Khả năng quan sát trạng thái event qua các chặng.

Đó là **một kiến trúc riêng**, không phải lời khuyên thay `@RetryableTopic` bằng vài lời gọi KafkaTemplate rồi mặc định được EOS. Cần xác minh failure window thực tế và phù hợp với phiên bản Spring Kafka được triển khai.

## 14. DLT không đồng nghĩa nghiệp vụ đã thành công

Khi record hết retry, việc chuyển sang Dead Letter Topic (DLT) có thể là trạng thái xử lý **terminal của consumer** nhưng không có nghĩa hoạt động nghiệp vụ thành công.

Một quy trình recovery điển hình:

~~~text
Input record failed repeatedly
       |
       v
Classify permanent/transient
       |
       +-- Recover to DLT
       |
       +-- Store original topic/partition/offset
       +-- Store exception and event ID
       +-- Alert owner
       |
       v
Manual/controlled replay after fixing cause
~~~

Nếu DLT publishing thành công nhưng offset của source stage chưa commit, record có thể được đưa sang DLT lần nữa. Nếu offset commit nhưng DLT publish thất bại, hệ thống có nguy cơ mất đường phục hồi. Phải lựa chọn cơ chế atomic recover khi bắt buộc, hoặc chấp nhận duplicate DLT và deduplicate theo event ID/source provenance.

DLT nên giữ metadata như original topic, partition, offset, consumer group, exception class và event ID. Không tự thay event ID khi replay. Nếu copy toàn bộ stack trace/headers qua nhiều stage, cần chú ý record size và dữ liệu nhạy cảm.

## 15. Số lần xử lý thực tế có thể tăng vượt cấu hình

Một non-blocking retry annotation:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1_000, multiplier = 2.0)
)
@KafkaListener(topics = "orders", groupId = "order-processor")
public void process(OrderEvent event) {
    orderService.apply(event);
}
~~~

Ví dụ này áp dụng cho một listener **không dùng container Kafka transactions** trong môi trường hỗ trợ `@RetryableTopic`. `attempts = "4"` có nghĩa một lần xử lý gốc và tối đa ba lần retry do topology này điều phối; không phải bốn lần retry bổ sung.

Nhưng **các lần gọi nghiệp vụ thực tế** có thể lớn hơn nếu:

- HTTP client có retry nội bộ.
- Service layer có `@Retryable` hoặc thư viện retry riêng.
- Record bị giao lại sau consumer crash/rebalance.
- Forward sang retry topic bị thực hiện hai lần ở failure window.
- DLT được replay sau khi sửa sự cố.
- Upstream phát trùng business event.

Không dùng số attempts của annotation như một chứng minh rằng side effect chỉ được thực hiện tối đa bốn lần trong mọi tình huống. Chỉ số này mô tả chính sách retry của topology, không phải giới hạn toán học end-to-end khi có crash/duplicate/replay.

## 16. Xử lý lỗi transient khác lỗi permanent

| Lỗi | Chính sách thường phù hợp | Tác động EOS/retry |
|---|---|---|
| HTTP 503/timeout tạm thời | Retry có backoff hữu hạn | Cần idempotency của API |
| Database connection tạm thời | Retry + giám sát outage | DB transaction riêng vẫn cần idempotency |
| JSON/schema không parse được | Non-retryable, DLT/quarantine | Retry cùng bytes không làm payload hợp lệ |
| Business rule violation terminal | Không retry vô ích | Lưu kết quả từ chối hoặc DLT theo chính sách |
| Kafka producer fencing | Điều tra transactional IDs, lifecycle | Không coi là lỗi nghiệp vụ per-record |
| Kafka transaction timeout | Tối ưu thời gian xử lý/timeout | Rollback, có thể giao lại |
| DLT publisher lỗi | Recovery chưa hoàn tất | Không được bỏ record âm thầm |

Với listener container transaction, dùng retry phù hợp với rollback flow. Với retry topics non-transactional, error classification quyết định forward sang retry stage hay DLT. Cả hai trường hợp đều cần có điểm kết thúc rõ ràng.

## 17. Khả năng tương thích với batch listener và long-running retry

Non-blocking retry topic của Spring Kafka thường nhắm tới **record listeners**; không nên mặc định nó hoạt động với batch listener như với record listener trong mọi phiên bản. Với batch + transaction, lỗi có thể làm rollback cả batch, kể cả khi một số record đã tạo side effect ngoài Kafka.

Nếu record phải chờ nhiều phút hoặc hàng giờ để retry, keeping an open Kafka transaction trong thời gian chờ là thiết kế không phù hợp:

- `transaction.timeout.ms` giới hạn thời gian transaction được phép mở.
- `max.poll.interval.ms` và consumer group lifecycle cần được duy trì.
- Transaction mở lâu ảnh hưởng khả năng đọc `read_committed` theo Last Stable Offset.
- Kafka transaction không phải hệ thống lập lịch tác vụ dài hạn.

Dùng workflow bền vững hoặc retry topic với ranh giới rõ ràng và idempotency thường hợp lý hơn khi delay dài. Nhưng điều đó là **quyết định đánh đổi về consistency**, không phải “một cách bật EOS dễ hơn”.

## 18. Failure matrix: câu hỏi nào quyết định mức bảo đảm?

| Failure point | Rủi ro nếu không có atomic forward/offset | Cơ chế cần xem xét |
|---|---|---|
| Crash trước publish retry | Record gốc có thể được giao lại | At-least-once, retry hợp lệ |
| Crash sau publish retry, trước commit offset nguồn | Hai bản cùng event trên retry topic | Atomic forward+offset hoặc dedup |
| Publish retry fail nhưng offset đã commit | Bỏ mất luồng retry | Không commit tiến độ khi recover chưa thành công |
| Retry listener tạo side effect rồi crash | Side effect có thể bị lặp | Idempotency/inbox |
| DLT publish OK nhưng source offset chưa commit | Duplicate DLT | Dedup theo event ID/source |
| DB commit thành công nhưng Kafka abort | DB update có thể bị chạy lại | Inbox/outbox |
| Listener nuốt exception rồi trả về success | Container có thể commit dù nghiệp vụ chưa hoàn tất | Propagate failure đúng semantics |
| Consumer output đọc `read_uncommitted` | Có thể thấy record abort | Cấu hình `read_committed` |
| Retry record xử lý sau event mới | Đảo thứ tự nghiệp vụ | Version/sequence/state machine |

Bảng này không thay thế thiết kế transaction cụ thể; nó giúp tìm đúng failure window phải được bảo vệ.

## 19. Observability: không chỉ nhìn consumer lag topic gốc

Khi retry topic hoạt động, lag topic gốc có thể thấp nhưng backlog thực tế còn nằm ở retry topics hoặc DLT. Mỗi business event có thể đi qua nhiều topic với nhiều offset khác nhau.

Nên quan sát:

- Lượng record forward từ topic gốc sang từng retry topic.
- Lag và tuổi record lớn nhất của mỗi retry stage.
- Số lần xử lý theo event ID trong log/tracing (không dùng event ID làm metric label).
- Số lỗi commit/abort Kafka transaction và transaction duration.
- Producer fencing, transaction timeout, consumer group rebalance.
- Số duplicate được inbox/idempotency phát hiện.
- DLT volume, DLT publish failure và tỷ lệ replay thành công.
- Thời gian từ event đầu tiên tới business completion, bao gồm retry delays.
- Thứ tự event theo aggregate/version khi nghiệp vụ phụ thuộc ordering.

Metric label nên dùng topic, stage, event type, exception class và outcome với cardinality thấp. Event ID, original offset và trace ID phù hợp trong log/tracing, không phù hợp làm metric label cho hàng triệu event.

## 20. Runbook khi có duplicate sau khi bật retry topics

1. **Khoanh vùng duplicate:** Hai Kafka records có cùng event ID hay một Kafka record bị listener chạy nhiều lần?
2. **Xác định nơi duplicate:** Topic retry, DLT, output topic, database hay HTTP side effect?
3. **Đọc metadata:** Original topic/partition/offset, event ID, attempt, consumer group và retry stage.
4. **Kiểm tra transactional boundary:** Forward producer và source offset có được commit cùng Kafka transaction hay không?
5. **Kiểm tra application crash/rebalance:** Có sự cố giữa publish và offset commit không?
6. **Kiểm tra idempotency:** Inbox unique constraint/idempotency key có hoạt động không?
7. **Kiểm tra downstream isolation:** Consumer output có `read_committed` không?
8. **Kiểm tra retry nhiều tầng:** HTTP client, service retry và `@RetryableTopic` có nhân số lần gọi không?
9. **Kiểm tra ordering:** Event cũ được retry sau event mới có gây sai state không?
10. **Sửa và replay có kiểm soát:** Giữ event ID, không gửi lại toàn bộ DLT trước khi rõ nguyên nhân.

Nếu duplicate nằm trong DB/HTTP, chỉ bật Kafka producer transactions không tự khắc phục. Nếu duplicate là hai bản committed của cùng business event được tạo bởi những transactions khác nhau, `read_committed` cũng không tự deduplicate chúng.

## 21. Runbook khi transactional listener không tiến offset

Với listener dùng Kafka container transaction, hãy xem:

- Listener có ném exception liên tục không? Đọc cause và phân loại transient/permanent.
- `DefaultAfterRollbackProcessor` có retry budget hữu hạn không?
- Có đang giữ transaction quá lâu do dependency timeout không?
- Có producer fencing vì prefix trùng giữa pod không?
- KafkaTemplate có đang dùng transactional producer factory của container không?
- Broker transaction coordinator và ACL có hoạt động không?
- Downstream bị giới hạn bởi một transaction mở và `read_committed`/LSO không?
- Recovery/DLT có thất bại rồi buộc record được xử lý lại không?

Không chỉ reset offset để xử lý lag. Reset sai có thể bỏ record nghiệp vụ và che nguyên nhân transaction/rollback thực sự.

## 22. Các tình huống minh họa để hiểu đúng semantics

### Trường hợp A — Kafka-only transform, một transaction

Input A được đọc từ `orders`, listener publish output A' vào `shipments` và commit offset trong cùng Kafka transaction. Nếu transaction abort thì consumer `read_committed` không thấy A'. Sau restart, A có thể được gọi lại và giao dịch mới commit A' cùng offset.

**Kết quả mong muốn:** output Kafka và input offset cùng kết cục; listener có thể thực thi lại nhưng không có output abort hiển thị với downstream đúng isolation.

### Trường hợp B — Non-blocking retry mặc định, process crash lúc forward

Input A được publish sang `orders-retry-1000`. Trước khi offset của topic gốc được commit, process chết. Khi phục hồi, consumer gốc đọc lại A và publish thêm một lần sang retry topic.

**Kết quả có thể xảy ra:** hai retry records chứa cùng event ID. Cần deduplication/idempotency hoặc thiết kế atomic forward/offset có chủ đích.

### Trường hợp C — Retry thành công nhưng DB đã được ghi ở lần đầu

Consumer lần đầu ghi DB rồi lỗi trước khi xác nhận record. Retry listener nhận A và ghi DB lần nữa. Dù cả Kafka transaction và offset được xử lý tốt ở một số chặng, DB không tự rollback theo Kafka.

**Kết quả cần thiết:** inbox unique constraint và cùng DB transaction để chặn side effect trùng; nếu còn Kafka output, xem xét outbox để không mất output khi retry bỏ qua lần ghi DB thứ hai.

### Trường hợp D — Retry làm đảo thứ tự

A: OrderCreated bị chuyển retry; B: OrderCancelled được xử lý ngay ở topic gốc. Sau delay, A chạy lại và cố tạo order đã bị hủy.

**Kết quả cần thiết:** version/sequence kiểm tra thứ tự hoặc thiết kế không cho B vượt A khi invariant đòi hỏi.

## 23. Checklist thiết kế EOS và retry topic

- [ ] Đã định nghĩa EOS cần bảo vệ Kafka-only pipeline hay cả business side effects?
- [ ] Kafka output và offset đầu vào nằm cùng transaction nếu claim Kafka EOS?
- [ ] Consumer downstream quan trọng dùng `read_committed`?
- [ ] Transactional ID prefix duy nhất giữa instance đang hoạt động?
- [ ] Chế độ listener transactional có dùng after-rollback/recovery phù hợp, không lạm dụng `@RetryableTopic`?
- [ ] Nếu dùng retry topic, đã mô tả các failure window publish/commit và duplicate?
- [ ] Có event ID bền vững, idempotency key và deduplication phù hợp?
- [ ] Đã đánh giá ordering xuyên original topic và retry topics?
- [ ] Đã tính tổng attempts từ mọi tầng retry và thời gian xử lý?
- [ ] DLT publishing thất bại không được coi là xử lý thành công?
- [ ] Có runbook và metrics bao phủ mọi retry stage, không chỉ topic gốc?
- [ ] Nếu có DB/HTTP, đã chọn inbox/outbox/workflow cho từng invariant?

**Kết luận:** Spring Kafka EOS và non-blocking retry topic là hai công cụ bổ sung về mặt mục tiêu nhưng không mặc định kết hợp thành một bảo đảm exactly-once end-to-end. Khi cần atomic Kafka output + source offset, dùng container transaction và rollback/retry tương thích. Khi cần delay dài và giữ throughput, retry topic có thể là lựa chọn tốt nếu chấp nhận rủi ro duplicate, ordering thay đổi và thiết kế idempotency/recovery đầy đủ. Với database hoặc hệ thống ngoài Kafka, bảo đảm nghiệp vụ phải được xây ở chính hệ thống đó, không thể chỉ dựa vào Kafka transaction.
