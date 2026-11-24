# Giới hạn kiểm chứng thứ tự, giao nhận lại và xử lý đúng một lần

## 1. Vì sao message contract đúng vẫn có thể tạo ra kết quả sai?

Trong hệ thống bất đồng bộ, **producer** phát thông điệp qua broker/topic/queue và **consumer** nhận để xử lý nghiệp vụ. Spring Cloud Contract mô tả các giao tiếp này bằng **Groovy/YAML DSL**, sinh kiểm thử phía producer và stub để consumer kiểm thử bằng Stub Runner. Tuy nhiên, **schema đúng không có nghĩa delivery hoặc business effect đúng**.

Ví dụ Payment Service phát:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "PaymentCaptured",
  "paymentId": "PAY-77",
  "orderId": "ORD-123",
  "aggregateVersion": 2,
  "amount": 120000,
  "currency": "VND"
}
~~~

Contract có thể kiểm tra destination, các headers và JSON trên. Nhưng một test như vậy **chưa chứng minh**:

- Sự kiện `OrderCreated`, `OrderPaid` và `OrderShipped` được xử lý theo đúng thứ tự.
- Broker không giao lại `evt-1001` sau khi consumer crash.
- Consumer không trừ tồn kho hoặc thu tiền hai lần khi nhận duplicate.
- Kafka transaction bao trùm cả database, email hoặc HTTP service bên ngoài.
- Retry, dead-letter và recovery luôn làm đúng dưới lỗi mạng hoặc xử lý song song.

Bài học thuộc chương **Hợp đồng thông điệp** của module `SPRING_CLOUD_CONTRACT`. Ta sẽ nghiên cứu **giới hạn kiểm chứng thứ tự, giao nhận lại và xử lý đúng một lần**, phân biệt ranh giới của contract testing với integration testing, rồi thiết kế các kiểm chứng bổ sung trong CI.

### Mục tiêu

Sau bài này, bạn sẽ:

1. Đọc một message contract và chỉ ra được những gì nó thực sự xác minh.
2. Phân biệt thứ tự phát sinh nghiệp vụ, publish, broker delivery và completion của consumer.
3. Nhận diện redelivery khi mất ack/offset commit hoặc retry.
4. Phân biệt at-most-once, at-least-once và exactly-once **effect**.
5. Thiết kế consumer idempotent với event ID, unique constraint và transaction.
6. Giải thích outbox/inbox, Kafka transactions, DLT và giới hạn của chúng.
7. Viết test matrix cho schema, ordering, duplicate, crash và release pipeline.

> **Nguyên tắc:** Contract kiểm tra một tương tác có thể quan sát được. **Một chuỗi các tương tác qua thời gian, retry và crash** là bài toán khác, cần các test tương ứng.

## 2. Spring Cloud Contract Messaging xác minh điều gì?

Ví dụ message contract Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('payment_captured')
    description('Producer phát sự kiện sau khi thu tiền')
    label 'paymentCaptured'

    input {
        triggeredBy('publishCapturedPayment()')
    }

    outputMessage {
        sentTo('payments.captured')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'PaymentCaptured')
        }
        body(
            eventId: 'evt-1001',
            eventType: 'PaymentCaptured',
            paymentId: 'PAY-77',
            orderId: 'ORD-123',
            aggregateVersion: 2,
            amount: 120000,
            currency: 'VND'
        )
    }
}
~~~

Cùng ý định bằng YAML DSL:

~~~yaml
name: payment_captured
description: Producer phát sự kiện sau khi thu tiền
label: paymentCaptured
input:
  triggeredBy: publishCapturedPayment()
outputMessage:
  sentTo: payments.captured
  headers:
    contentType: application/json
    eventType: PaymentCaptured
  body:
    eventId: evt-1001
    eventType: PaymentCaptured
    paymentId: PAY-77
    orderId: ORD-123
    aggregateVersion: 2
    amount: 120000
    currency: VND
~~~

**Giải thích DSL:**

- `label` dùng nhận diện/kích hoạt message stub ở phía consumer khi được hỗ trợ.
- `input.triggeredBy` chỉ rõ phương thức producer test gọi để kích hoạt message; base class/test context phải cung cấp cách gọi tương ứng.
- `outputMessage.sentTo` là destination được kiểm chứng theo messaging integration.
- `outputMessage.headers` bảo vệ các headers được công bố.
- `outputMessage.body` bảo vệ dữ liệu và kiểu quan trọng của payload.
- `eventId`, `aggregateVersion` là **field nghiệp vụ**, không phải cờ bật cơ chế exactly-once trong Spring Cloud Contract.

Với message verifier đúng, generated producer test kích hoạt phương thức, quan sát message tại destination và so sánh headers/body. Có thể cần `@AutoConfigureMessageVerifier` và cấu hình Spring Cloud Stream/Spring Integration/JMS hoặc adapter riêng phù hợp với phiên bản ứng dụng.

Một generated test thành công **không tự tạo crash**, **không buộc broker redeliver**, **không kiểm tra offset commit** và **không chứng minh database side effect không trùng**.

### 2.1. Đừng suy bảo đảm từ một field trong schema

Có `eventId` chỉ cho phép consumer **nhận diện một logical event**; cần code/DB constraint để dedup. Có `aggregateVersion: 2` cho phép consumer biết version; cần routing, sequencing và xử lý thiếu/lệch version. Có `occurredAt` cho phép truy vết thời gian; nó không phải một đồng hồ toàn cục bảo đảm order.

### 2.2. Bảng phạm vi kiểm chứng

| Contract producer test đã đạt | Được kết luận | Chưa được kết luận |
| --- | --- | --- |
| Message đúng destination | Có một output phù hợp được quan sát trong test context | Mọi lần publish đều thành công qua broker thật |
| Payload đúng JSON | Consumer có ví dụ schema phù hợp | Mọi runtime events đều hợp lệ |
| Header `eventType` đúng | Event mẫu mang metadata đã thỏa thuận | Retry policy của broker đúng |
| `eventId` đúng định dạng | Producer cung cấp identity | Duplicate delivery không xảy ra |
| `aggregateVersion` là số | Dữ liệu phù hợp schema | Consumer thực thi version tăng dần |
| Test thấy message mong đợi | Producer thỏa một tương tác | Không có message thứ hai được phát |
| CI build xanh | Các assertions đã chạy và đạt | Business effect exactly once dưới sự cố |

## 3. Ba nhóm trách nhiệm riêng

| Nhóm | Câu hỏi điển hình | Kiểm thử chính |
| --- | --- | --- |
| **Giao diện thông điệp** | Event type, body, header, destination có khớp? | Spring Cloud Contract và Stub Runner |
| **Giao nhận** | Thứ tự, ack, retry, redelivery, dead-letter ra sao? | Broker integration tests, failure injection |
| **Nghiệp vụ** | Consumer có trừ kho hai lần, tính sai tổng, xử lý version cũ? | Unit/domain/transaction tests |

Các test có thể dùng cùng dữ liệu mẫu để giảm khác biệt, nhưng **lời kết luận phải theo đúng tầng**. Ví dụ, consumer xử lý hai bản sao event mà không sinh effect lặp chưa có nghĩa broker đã được kiểm chứng về redelivery. Ngược lại, broker redelivery đúng nhưng handler áp dụng tiền hai lần vẫn là lỗi nghiệp vụ.

## 4. Thứ tự có nhiều nghĩa

“Message đúng thứ tự” có thể nói tới:

1. Thứ tự **business event** xuất hiện trong domain.
2. Thứ tự producer gửi publish requests.
3. Thứ tự broker ghi hoặc enqueue.
4. Thứ tự consumer nhận message.
5. Thứ tự consumer **commit side effects**.

Những thứ tự này không nhất thiết trùng nhau:

~~~text
Producer:   E1(OrderCreated) → E2(OrderPaid) → E3(OrderShipped)
Broker:     E1 → E2 → E3
Consumers:  E1 bắt đầu; E2 bắt đầu; E2 xong; E1 xong; E3 xong
Effects:    E2 → E1 → E3
~~~

Một hợp đồng riêng cho `E2` không thể chứng minh hiệu ứng E1 phải hoàn tất trước E2.

### 4.1. Kafka chỉ bảo đảm thứ tự theo partition

Kafka lưu records theo **topic-partition** với offset tăng dần. Consumer có thể đọc theo thứ tự offset **trong một partition**; không có thứ tự tổng quát giữa các partition.

~~~text
orders.events
  partition-0: ORD-123/v1 → ORD-123/v2 → ORD-123/v3
  partition-1: ORD-456/v1 → ORD-456/v2
~~~

Cách thường dùng để giữ per-order order là chọn Kafka record key = `orderId` và kiểm soát partitioning. Tuy nhiên:

- `orderId` trong JSON body **không tự trở thành Kafka key**.
- Producer concurrent, retry và async publishing cần được thiết kế để giữ thứ tự ghi mong muốn.
- Thay số partition/partitioner có thể ảnh hưởng nơi records mới của key được định tuyến.
- Retry topics, xử lý nhiều tasks đồng thời hoặc handler bất đồng bộ có thể làm **thứ tự hoàn tất nghiệp vụ** khác thứ tự offset.
- Order khác nhau trên hai partition không có total order chung.

### 4.2. RabbitMQ: FIFO không đồng nghĩa hoàn tất đúng thứ tự

Queue có thể phân phối theo thứ tự enqueue trong điều kiện xác định, nhưng nhiều consumers, prefetch, requeue, nack và connection loss ảnh hưởng việc delivery lại và xử lý.

~~~text
Queue: E1 → E2 → E3
Consumer A nhận E1, xử lý chậm
Consumer B nhận E2, commit trước E1
Consumer A mất kết nối, E1 bị giao lại
~~~

Do đó câu “queue là FIFO nên consumer sẽ xử lý tất cả effects theo thứ tự” **không đúng một cách vô điều kiện**.

### 4.3. Sequence/version phải có chính sách đi kèm

~~~json
{
  "eventId": "evt-102",
  "aggregateId": "ORD-123",
  "aggregateVersion": 2,
  "eventType": "OrderPaid"
}
~~~

Field `aggregateVersion` có thể được contract kiểm tra, nhưng consumer phải có logic riêng:

| Trạng thái trước | Event nhận | Chính sách ví dụ |
| --- | --- | --- |
| Đã áp dụng v1 | v2 | Xử lý và ghi lastAppliedVersion=2 |
| Đã áp dụng v2 | v2 | Bỏ qua duplicate |
| Đã áp dụng v2 | v1 | Xử lý event cũ theo chính sách |
| Đã áp dụng v1 | v3 | Phát hiện gap v2; buffer/retry/resync |

Không mặc định mọi ứng dụng phải xử lý toàn bộ version theo thứ tự: có hệ thống dùng snapshot latest-state, hệ khác cần đầy đủ chuyển đổi. Hãy nêu rõ cam kết nghiệp vụ rồi mới viết test.

## 5. Redelivery: crash sau commit trước ACK

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Database
    B->>C: Giao evt-102
    C->>D: Ghi business effect
    D-->>C: COMMIT thành công
    Note over C: Crash trước ACK / offset commit
    B->>C: Giao lại evt-102
    C->>D: Nguy cơ effect lặp
~~~

Các tình huống thường tạo redelivery hoặc duplicate:

- Consumer crash hoặc mất connection khi chưa ack.
- Offset Kafka chưa commit hoặc transaction rollback.
- Error handler thực hiện retry sau exception.
- Producer publish lại vì xác nhận publish trước đó bị mất.
- Outbox relay publish xong nhưng crash trước khi lưu trạng thái đã publish.

**Publisher confirm**, **consumer ack** và **database commit** là ba tín hiệu khác nhau. RabbitMQ publisher confirm không chứng minh consumer đã xử lý; ack consumer không tự làm external transaction an toàn.

RabbitMQ có cờ `redelivered` làm gợi ý rằng message từng được giao, nhưng một duplicate do producer publish lại có thể tới như delivery mới. Vì vậy **không dùng cờ redelivered thay cho event identity và dedup**.

## 6. At-most-once, at-least-once và exactly-once effects

| Mô hình | Ý nghĩa | Rủi ro hoặc yêu cầu |
| --- | --- | --- |
| **At-most-once** | Không chủ động redeliver sau khi hệ thống coi là đã nhận | Có thể mất message |
| **At-least-once** | Retry/redelivery khi chưa chắc đã xử lý | Có thể giao cùng event nhiều lần |
| **Exactly-once effect** | Một logical event chỉ gây một side effect trong phạm vi đã nêu | Cần idempotency, transaction, dedup |
| **Kafka EOS read-process-write** | Kafka output và consumed offsets có thể được commit atomically | Không tự bao trùm database/email/gateway ngoài Kafka |

“Đã nhận một lần”, “listener được gọi một lần”, “event có một offset”, “tiền chỉ bị trừ một lần” là **những lời bảo đảm khác nhau**. Cần nói rõ đối tượng, ranh giới transaction, retry/crash scenarios và bằng chứng kiểm thử.

Một hệ thống at-least-once có thể đạt **đúng một business effect** nếu consumer idempotent đúng. Nó không vì thế trở thành hệ thống có exactly-once delivery.

## 7. Idempotent consumer và ghi dấu atomic

Giả sử Fulfillment Service chỉ được mở khóa giao hàng một lần cho `evt-1001`:

~~~text
evt-1001 lần 1 → mở khóa
evt-1001 lần 2 → không mở khóa thêm
evt-1001 lần 3 → không mở khóa thêm
~~~

Dùng event identity ổn định qua các lần redelivery của cùng **logical event**. Một cấu trúc PostgreSQL minh họa:

~~~sql
CREATE TABLE processed_messages (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ý tưởng xử lý trong **cùng database transaction**:

~~~sql
BEGIN;
INSERT INTO processed_messages (consumer_name, event_id)
VALUES ('fulfillment-service', 'evt-1001');

UPDATE orders
SET fulfillment_unlocked = TRUE
WHERE order_id = 'ORD-123';
COMMIT;
~~~

Khi insert duplicate key, application phải **không chạy UPDATE thêm lần nữa**. Đây là mô tả cơ chế, không phải SQL handler hoàn chỉnh. DB uniqueness và transaction giúp chống hai instances cùng nhận duplicate rồi xử lý đồng thời.

### 7.1. Sai lầm check-then-act

~~~java
if (!processedMessages.existsById(event.eventId())) {
    fulfillment.apply(event);
    processedMessages.save(event.eventId());
}
~~~

Hai threads có thể cùng thấy `exists = false` trước khi lưu, rồi cùng áp dụng effect. Chỉ kiểm tra tồn tại trên ứng dụng là **không atomic**.

Pseudocode có chủ đích:

~~~java
// PSEUDOCODE: tryInsert là API tự triển khai
@Transactional
public void handle(PaymentCaptured event) {
    boolean firstTime =
        processedMessages.tryInsert("fulfillment-service", event.eventId());
    if (!firstTime) {
        return;
    }
    fulfillmentRepository.unlock(event.orderId());
}
~~~

`tryInsert` không phải API mặc định của Spring Cloud Contract hay Spring Data. Implementation phải dùng unique constraint và transaction đúng.

### 7.2. Phạm vi transaction cần nói rõ

Nếu effect chỉ là cập nhật cùng database, có thể tổ chức atomic với ghi dấu processed. Nếu effect là **gửi email, gọi payment gateway hoặc HTTP service**, database transaction không rollback side effect bên ngoài. Cần idempotency key ở dịch vụ nhận, transactional outbox hoặc cơ chế bù/đối soát.

**Khóa dedup có thể là** `eventId`, `(eventType, aggregateId, aggregateVersion)` hay `paymentId + loại effect` tùy nghiệp vụ. Dùng đơn thuần `orderId` có thể chặn nhầm các event hợp lệ khác trong vòng đời đơn hàng.


## 8. Transactional outbox không tự loại bỏ duplicate

Một producer thường cần cập nhật database và phát event. Hai trình tự ngây thơ đều có cửa sổ lỗi:

~~~text
COMMIT payment = CAPTURED
→ Crash trước publish
→ Consumer không biết payment đã đổi

Publish PaymentCaptured
→ Database rollback
→ Consumer nhận event cho trạng thái chưa commit
~~~

**Transactional outbox** ghi business change và một outbox record trong **cùng database transaction**; sau commit, relay đọc record để publish lên broker.

~~~mermaid
flowchart LR
    A["Business action"] --> B["DB transaction"]
    B --> C["Update payment"]
    B --> D["Insert outbox"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Outbox relay"]
    F --> G["Broker"]
    G --> H["Idempotent consumer"]
~~~

Outbox **không mặc nhiên bảo đảm không publish trùng**: relay có thể publish thành công rồi crash trước khi lưu rằng event đã được gửi. Nó có thể publish lại sau restart. Vì vậy bên consumer vẫn cần xử lý duplicate.

### 8.1. Inbox/processed-message ledger

Một thiết kế bổ sung là lưu `(consumerName,eventId)` vào bảng processed messages hoặc inbox trong **cùng transaction** với business effect. Nếu event đã xử lý, không áp dụng lại effect.

Cần xác định thời hạn lưu processed IDs. Nếu broker hoặc vận hành cho phép replay những event từ nhiều tháng trước, xóa bảng dedup sau vài ngày có thể làm xử lý lặp.

### 8.2. Các mã định danh có vai trò khác nhau

| Trường | Ý nghĩa |
| --- | --- |
| `eventId` | Identity ổn định của logical event, phục vụ dedup |
| `aggregateId` | Entity/domain aggregate bị tác động |
| `aggregateVersion` | Version hoặc sequence trong phạm vi aggregate |
| `correlationId` | Ghép log/tracing qua nhiều tương tác |
| `causationId` | Event/command tạo ra event hiện tại, nếu schema công bố |

Đây là **quy ước schema**, không phải các trường mà Spring Cloud Contract tự thêm. Contract kiểm tra được sự tồn tại/định dạng; ứng dụng phải thực thi quy tắc vận hành.

## 9. Exactly-once của Kafka có giới hạn ranh giới

Spring Kafka hỗ trợ transaction cho luồng **read → process → write Kafka**. Khi cấu hình listener container, transaction manager, Kafka output và consumed offsets đúng, output records và offsets có thể commit atomically trong phạm vi Kafka transaction.

Tài liệu Spring Kafka cũng giải thích rằng **read/process có thể xảy ra hơn một lần**, còn kết quả Kafka read-process-write được bảo vệ bằng transaction. Cần phân biệt chuyện listener được gọi lại với chuyện Kafka output xuất hiện như thế nào ở consumer có isolation phù hợp.

| Luồng | Kafka EOS tự bảo vệ đủ? | Tại sao |
| --- | --- | --- |
| Kafka input → Kafka output + consumed offsets | Có thể khi cấu hình chính xác | Cùng Kafka transaction |
| Kafka input → cập nhật PostgreSQL | Không mặc nhiên | Database có transaction riêng |
| Kafka input → gửi email | Không | SMTP không rollback theo Kafka |
| Kafka input → gọi payment gateway | Không | Gateway có side effect riêng |
| Kafka input → gọi HTTP service | Không mặc nhiên | Timeout/retry cần idempotency bên đích |

Với side effect bên ngoài Kafka, cần idempotency key, outbox/inbox hoặc reconciliation. **Một generated message contract test không chứng minh distributed transaction**.

Các API EOS mode, broker version và transaction behavior thay đổi theo Spring Kafka/client version; phải đối chiếu dependency đang dùng khi cấu hình thật.

## 10. Retry, backoff, DLQ/DLT và poison message

Consumer có thể gặp lỗi **tạm thời** như DB gián đoạn, lỗi **vĩnh viễn** như schema không thể parse, hoặc lỗi chưa phân loại được. Chính sách xử lý cần nêu:

- Lỗi nào được retry, lỗi nào bị từ chối ngay?
- Số lần tối đa và backoff bao nhiêu?
- Có giữ `eventId` khi retry hoặc replay?
- Event không thể xử lý được chuyển tới DLT/DLQ nào?
- Ai theo dõi, sửa và replay những events này?
- Retry topic có làm event mới vượt qua event cũ cùng aggregate không?
- Có metrics và tracing theo event ID, attempt, consumer instance không?

Spring Kafka có `DefaultErrorHandler`, `BackOff` và `DeadLetterPublishingRecoverer`; RabbitMQ có ack/nack, requeue và dead-lettering. Các cơ chế này thuộc **runtime/integration tests**, không thể được suy ra từ một `outputMessage`.

### 10.1. Non-blocking retry có thể đảo thứ tự nghiệp vụ

~~~text
Main topic: E1(v1) rồi E2(v2)
E1 lỗi → chuyển retry topic
E2 trên main topic được xử lý thành công
Sau delay, E1 được retry
Business completion: E2 trước E1
~~~

Nếu phải xử lý chính xác từng version, cần chiến lược gap detection, buffering hoặc giữ xử lý theo key thay vì dựa vào thứ tự publish ban đầu.

### 10.2. Dead-letter không có nghĩa business effect thành công

Chuyển message vào DLT có nghĩa pipeline **chưa hoàn tất nghiệp vụ theo đường thông thường**. Nên có alert, runbook replay, monitoring số lượng retry và dedup khi phát lại.

Nếu consumer cần đọc error event ở DLT, có thể viết message contract cho **schema error event**; nhưng số lần retry và thời điểm chuyển DLT cần được kiểm chứng qua broker test thật.

## 11. Kiểm thử ordering bằng chuỗi message, không phải một event

Ví dụ order có events:

~~~json
{"eventId":"evt-1","aggregateId":"ORD-123","aggregateVersion":1,"eventType":"OrderCreated"}
~~~

~~~json
{"eventId":"evt-2","aggregateId":"ORD-123","aggregateVersion":2,"eventType":"OrderPaid"}
~~~

~~~json
{"eventId":"evt-3","aggregateId":"ORD-123","aggregateVersion":3,"eventType":"OrderShipped"}
~~~

Một **broker integration test** nên:

1. Tạo broker/test container và consumer trong môi trường cô lập.
2. Publish events với cùng key `ORD-123` theo thứ tự.
3. Chờ trạng thái cuối `SHIPPED` và lastAppliedVersion = `3` với timeout hữu hạn.
4. Nếu nghiệp vụ cần đủ ba bước, kiểm tra audit/domain records thay vì chỉ nhìn status cuối.
5. Cố ý gửi thứ tự `v1 → v3 → v2` để kiểm tra chính sách gap/out-of-order.
6. Thử consumer concurrency, redelivery và retry policy gần với production.

Pseudocode:

~~~java
// PSEUDOCODE: publish và awaitCondition là test helpers tự định nghĩa
publish(orderCreated("ORD-123", 1));
publish(orderPaid("ORD-123", 2));
publish(orderShipped("ORD-123", 3));

awaitCondition(Duration.ofSeconds(10), () ->
    orderProjection.find("ORD-123").status().equals("SHIPPED")
);

assertThat(orderProjection.find("ORD-123").lastAppliedVersion())
    .isEqualTo(3);
~~~

Các hàm `publish`, `awaitCondition` và `orderProjection.find` trong ví dụ **không phải API của Spring Cloud Contract**.

### 11.1. Không chờ bằng thời lượng đoán mò

~~~java
publish(orderShipped("ORD-123", 3));
Thread.sleep(2000);
assertThat(orderProjection.find("ORD-123").status())
    .isEqualTo("SHIPPED");
~~~

Test trên dễ flaky khi CI có backlog. Nên chờ **điều kiện quan sát được** với timeout và log trạng thái khi timeout, chẳng hạn dùng Awaitility hoặc helper tương đương.

### 11.2. Khi test fail cần thu thập

- Topic/partition/offset hoặc queue/delivery tag.
- `eventId`, `aggregateId`, `aggregateVersion`, message key.
- Thời điểm publish, broker accept, consumer receive và DB commit.
- Consumer concurrency, prefetch, error handler và transaction mode.
- Có duplicate hay thiếu version không?

Bằng chứng này phân biệt producer publish sai order, broker redelivery và consumer xử lý song song.

## 12. Test redelivery và duplicate ở hai cấp

### 12.1. Unit/domain test: cùng event hai lần

~~~java
// PSEUDOCODE: các method dưới đây là helper của ứng dụng
PaymentCaptured event =
    samplePaymentCaptured("evt-1001", "ORD-123");

handler.handle(event);
handler.handle(event);

assertThat(fulfillmentRepository.countUnlockActions("ORD-123"))
    .isEqualTo(1);
~~~

Test này giúp bảo vệ idempotent business effect trong môi trường thử nghiệm. Nó **không chứng minh** broker sẽ redeliver đúng sau mất ack.

### 12.2. Concurrent duplicate test

Hai consumers cùng nhận eventId. Test cần xác minh:

- Unique constraint ngăn hai transactions cùng ghi dấu và apply effect.
- Transaction thua cuộc xử lý duplicate an toàn.
- Không có side effect ngoài DB trước khi có quyết định xử lý.
- Không bị retry/deadlock vô hạn.

Một test gọi handler tuần tự hai lần **không đủ** khi production có nhiều consumer instances.

### 12.3. Broker test với failure injection

~~~text
Given:
  Consumer nhận evt-1001
  Business transaction commit thành công

When:
  Consumer bị dừng trước ack/offset commit
  Broker phát hiện client lỗi
  Consumer khởi động lại

Then:
  Event được giao lại theo chính sách
  Không có business effect thứ hai
  Duplicate được ack/commit an toàn
~~~

Cần tiêm lỗi **đúng sau commit và trước ack**. Nếu chỉ publish trùng hai lần, bạn kiểm tra duplicate handling chứ chưa kiểm tra cơ chế broker redelivery khi crash.

### 12.4. Ack/offset commit nên theo mốc xử lý đã công bố

- Ack quá sớm có thể mất khả năng xử lý lại sau crash.
- Ack quá muộn hoặc thất bại có thể tạo redelivery.
- Consumer phải an toàn khi event được xử lý lại.
- Kafka transactional read-process-write có cơ chế offset/output transaction riêng.
- RabbitMQ manual ack nên theo chính sách xác định mốc xử lý thành công.

Không có một thứ tự ack giống nhau cho mọi messaging integration.

## 13. Stub Runner kiểm tra consumer ở mức nào?

Spring Cloud Contract có thể tạo messaging stub với label `paymentCaptured`. Với integration phù hợp, consumer test kích hoạt event mẫu và xem application có xử lý message đúng schema không.

**Consumer stub tests có thể kiểm tra:**

- Listener giải mã JSON, headers và metadata.
- Consumer không phụ thuộc field chưa được hợp đồng công bố.
- Business handler xử lý một event mẫu.
- Nếu chủ động kích hoạt hai lần cùng event ID và kiểm tra side effect, consumer idempotency trong test context.

**Không tự chứng minh:**

- Kafka/RabbitMQ giữ order như cấu hình production.
- Ack/nack, rebalance hoặc retry hoạt động đúng dưới lỗi mạng.
- Outbox relay không mất event ở crash scenario.
- External payment/email side effect không xảy ra trùng.
- Hệ thống có exactly-once end-to-end.

**Kết luận:** Generated producer messaging tests, consumer tests với Stub Runner, broker integration tests và failure injection là **các lớp bổ sung**, không thay thế nhau.


## 14. Thiết kế end-to-end: theo dõi từng ranh giới giao tiếp

Xét Payment Service và Fulfillment Service. Kiến trúc minh họa:

~~~mermaid
flowchart TD
    P["Payment Service"] --> O["Payment DB + Outbox"]
    O --> R["Outbox relay"]
    R --> K["Kafka / RabbitMQ"]
    K --> C["Fulfillment Consumer"]
    C --> I["Inbox / unique eventId"]
    I --> D["Cập nhật fulfillment trong DB transaction"]
    D --> A["Ack / offset commit theo policy"]
    C --> X["DLT nếu không thể xử lý"]
~~~

Sơ đồ là một **mô hình thiết kế tham khảo**, không phải hệ thống mà Spring Cloud Contract tự triển khai.

### 14.1. Các bất biến (invariants) cần bảo vệ

| Bất biến | Chủ sở hữu | Kiểm thử |
| --- | --- | --- |
| `PaymentCaptured` có body/header và kiểu đúng | Producer | Spring Cloud Contract messaging producer test |
| Message được phát vào destination đã công bố | Producer adapter | Generated contract test với message verifier |
| Payment status và outbox event được commit cùng nhau | Producer persistence | Outbox transaction integration test |
| Relay retry khi publish thất bại | Relay/broker integration | Relay integration/failure test |
| Event cùng aggregate dùng message key phù hợp | Producer broker adapter | Kafka/RabbitMQ integration test |
| Consumer hiểu event schema | Consumer | Stub Runner consumer contract test |
| Duplicate event không mở khóa giao hàng hai lần | Consumer domain/DB | Idempotency transaction + concurrency test |
| Event version cũ không làm lùi trạng thái | Consumer domain | Out-of-order sequence test |
| Crash trước ack không làm lặp business effect | Consumer + broker | Failure injection + restart test |
| Poison event đi DLT đúng policy | Consumer infrastructure | Retry/DLT integration test |
| CI chặn producer không đáp ứng contract | Release pipeline | Producer verification và publish gate |

### 14.2. Viết yêu cầu exactly-once đủ cụ thể

Phát biểu mơ hồ:

> Mọi message trong hệ thống luôn được xử lý đúng một lần.

Một yêu cầu có thể kiểm thử hơn:

> Với cùng `eventId` của `PaymentCaptured`, thao tác mở khóa fulfillment cho `orderId` chỉ được commit tối đa một lần trong PostgreSQL; processed-event record và thay đổi fulfillment nằm trong một transaction. Nếu message được giao lại, consumer không thực thi side effect lần nữa.

Yêu cầu thứ hai nói rõ **logical event identity**, **business effect**, **database boundary**, và **điều kiện redelivery**. Nó vẫn chưa bao phủ việc gửi email hoặc gọi cổng thanh toán nếu những side effects đó không nằm trong thiết kế.

## 15. Ma trận kiểm thử có trách nhiệm

Một bộ test thực tế nên chia theo tầng:

| Tầng | Tình huống | Assertions |
| --- | --- | --- |
| Contract producer | Phát `PaymentCaptured` mẫu | Destination, eventType, schema, headers |
| Contract consumer | Stub trigger event mẫu | Deserialize, nhánh xử lý dữ liệu |
| Domain unit | Cùng eventId được xử lý hai lần | Effect chỉ được áp dụng một lần |
| DB integration | Hai handlers concurrent nhận duplicate | Unique constraint và transaction an toàn |
| Kafka ordering | Events v1-v3 cùng key | Partition/offset và consumer projection phù hợp |
| Rabbit delivery | Mất ack/connection | Redelivery theo chính sách |
| Crash injection | Crash sau DB commit trước ack | Không có effect thứ hai |
| Outbox integration | Relay crash sau publish | Có thể publish lại, downstream vẫn idempotent |
| Retry policy | Lỗi transient/permanent | Attempts, backoff, DLT đúng |
| Replay | Replay event cũ | Không tạo side effect trùng |
| Release gate | Producer contract fail | Không publish stub/artifact đã lỗi |

### 15.1. Độ tin cậy của test bất đồng bộ

Test với broker cần quan sát điều kiện thật, không chỉ ngủ một khoảng tùy ý:

- Dùng timeout hữu hạn và thông báo lỗi rõ ràng.
- Dùng `eventId`/`correlationId` riêng cho mỗi kịch bản.
- Cô lập topic, queue, consumer group, schema hoặc DB theo khả năng.
- Không để dữ liệu từ test trước gây pass giả.
- Nếu cần order, thử đúng concurrency/prefetch production.
- Không đếm số lần listener được gọi để kết luận về số lần business effect.
- Kiểm tra cả trạng thái database và vị trí message khi fault test thất bại.

Pseudocode kiểm tra trạng thái sau xử lý:

~~~java
// PSEUDOCODE: không phải API Spring Cloud Contract
publish(paymentCaptured("evt-1001", "ORD-123"));
publish(paymentCaptured("evt-1001", "ORD-123"));

awaitCondition(Duration.ofSeconds(10), () ->
    fulfillmentRepository.find("ORD-123").isUnlocked()
);

assertThat(fulfillmentRepository.countUnlockActions("ORD-123"))
    .isEqualTo(1);
~~~

Với điều kiện **concurrent duplicate**, cần cho hai consumer xử lý đồng thời và có rào cản/ràng buộc DB thích hợp, không chỉ publish hai lần tuần tự rồi suy ra mọi race đã được xử lý.

## 16. CI bảo vệ contract và reliability như thế nào?

Một producer có Spring Cloud Contract plugin đã cấu hình có thể dùng:

~~~bash
./mvnw -B clean verify
~~~

hoặc Gradle:

~~~bash
./gradlew clean build
~~~

Lệnh chỉ có ý nghĩa nếu generated tests thực sự được **sinh, biên dịch và thực thi** với message verifier/binder tương ứng. Một `BUILD SUCCESS` khi không có generated messaging test nào chạy **không phải bằng chứng contract đã được kiểm chứng**.

### 16.1. Gợi ý pipeline theo tầng

~~~text
Pull request:
  - Compile, unit/domain tests
  - Generated producer contract tests
  - Consumer tests với stub tương thích
  - Database idempotency/transaction tests

Integration pipeline:
  - Kafka/RabbitMQ order, retry, DLT
  - Concurrent duplicates, redelivery, crash injection
  - Outbox relay recovery

Trước release:
  - Verify stub artifact/version
  - Kiểm tra backward compatibility cho consumer
  - Kiểm tra metrics, alerts, replay runbook
  - Chỉ phát hành producer/stub đã vượt qua các gates cần thiết
~~~

Không phải mọi test nặng cần chạy mỗi commit nếu tài nguyên hạn chế. Tuy nhiên, **kết luận về độ tin cậy phải căn cứ vào những tests thực sự chạy ở một cadence được quản lý**. Đừng dùng kết quả contract test để tuyên bố một failure-injection scenario đã được kiểm tra khi nó chưa bao giờ được thực thi.

### 16.2. Checklist code review cho thay đổi message

1. Có đổi destination, header, field hoặc kiểu dữ liệu mà consumer đọc không?
2. `eventId` có ổn định qua các lần retry cùng logical event không?
3. Có đưa thêm consumer group hoặc thay concurrency không?
4. Có thay message key/partitioner, số partition hoặc routing không?
5. Retry/DLT có làm per-key ordering bị thay đổi không?
6. Business effect có được bảo vệ bằng idempotency/transaction không?
7. Có side effect ngoài DB cần idempotency key không?
8. Nếu outbox relay crash trước/sau publish, dữ liệu có thể mất/trùng thế nào?
9. Đã thêm tests chứng minh tính chất mới theo đúng ranh giới chưa?

## 17. Những nhầm lẫn thường gặp

| Nhận định | Vì sao chưa đủ | Cách sửa nhận thức hoặc test |
| --- | --- | --- |
| “Contract có `eventId` nên không thể duplicate” | Field không có tác dụng dedup tự động | Thiết kế unique constraint/handler idempotent |
| “Kafka đảm bảo thứ tự mọi message trong topic” | Ordering theo partition, không total order giữa partitions | Chọn key và kiểm tra per-aggregate order |
| “Queue là FIFO nên effects commit FIFO” | Concurrency, prefetch, requeue có thể đổi thứ tự hoàn tất | Broker/consumer integration tests |
| “Publisher confirm chứng minh consumer đã xử lý” | Confirm và consumer ack độc lập | Quan sát các tín hiệu riêng |
| “Đã ack là business effect chắc chắn commit” | Ack có thể không gắn với external transaction | Thiết kế ack boundary + idempotency |
| “Kafka EOS bao phủ PostgreSQL và email” | Kafka transaction không tự bao trùm external systems | DB idempotency/outbox hoặc coordination |
| “Gửi event hai lần là test broker redelivery” | Đây chủ yếu là duplicate handling test | Thử crash/mất ack với broker thật |
| “Đã chuyển DLT tức là xử lý thành công” | DLT báo chưa xử lý theo đường bình thường | Monitoring, alert, replay |
| “Timestamp quyết định version” | Clock skew, retry và delay làm order không ổn định | Dùng version/sequence do domain cấp |
| “Check exists rồi update là đủ” | Hai instances cùng thấy false | Unique constraint và transaction |
| “Outbox loại bỏ duplicate” | Relay có thể publish lại | Consumer idempotent |
| “Stub Runner xanh là broker ổn định” | Stub không mô phỏng toàn bộ delivery faults | Broker integration/fault tests |

### 17.1. Quy trình điều tra một effect bị áp dụng hai lần

Khi thấy đơn hàng bị trừ tồn kho hai lần:

1. Hai lần xử lý có **cùng eventId** không?
2. Producer phát hai events logic hay relay/broker gửi lại?
3. Có crash, rebalance, timeout hoặc nack/requeue không?
4. Handler ghi processed-event trước hay sau effect? Có cùng transaction không?
5. Hai consumer instances có chạy cùng lúc và vượt qua `exists` check không?
6. Có external API nào tạo effect lặp do thiếu idempotency key?
7. Logs có eventId, aggregateId, attempt, partition/offset và transaction outcome không?

Đừng sửa contract thành matcher dễ dãi chỉ để cho qua duplicate ở runtime. Contract schema và business idempotency là **hai bài toán khác nhau**.

## 18. Bài thực hành: PaymentCaptured và Fulfillment Service

Giả sử Payment Service phát sự kiện khi giao dịch `PAY-900` của đơn `ORD-900` đã được capture:

~~~json
{
  "eventId": "evt-pay-900",
  "eventType": "PaymentCaptured",
  "paymentId": "PAY-900",
  "orderId": "ORD-900",
  "aggregateVersion": 2,
  "amount": 450000,
  "currency": "VND"
}
~~~

Consumer Fulfillment Service phải mở khóa giao hàng **một lần** và không bị đưa lùi trạng thái bởi event cũ.

### 18.1. Nhiệm vụ A — Viết contract producer

Viết một Groovy messaging contract gồm:

- `label: paymentCaptured`.
- `input.triggeredBy` là trigger do test context cung cấp.
- `outputMessage.sentTo` là `payments.captured`.
- Header `eventType: PaymentCaptured`.
- Body có `eventId`, `paymentId`, `orderId`, `aggregateVersion`, `amount` và `currency` đúng kiểu.

Gợi ý:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('payment_captured_for_fulfillment')
    label 'paymentCaptured'

    input {
        triggeredBy('publishCapturedPayment()')
    }

    outputMessage {
        sentTo('payments.captured')
        headers {
            header('eventType', 'PaymentCaptured')
        }
        body(
            eventId: 'evt-pay-900',
            eventType: 'PaymentCaptured',
            paymentId: 'PAY-900',
            orderId: 'ORD-900',
            aggregateVersion: 2,
            amount: 450000,
            currency: 'VND'
        )
    }
}
~~~

**Giải thích:** Contract bảo vệ một event cụ thể về destination/payload/headers. Nó chưa kiểm tra redelivery, outbox, ordering hoặc external effects.

### 18.2. Nhiệm vụ B — Idempotency

Gửi event `evt-pay-900` tới consumer **hai lần**. Kiểm tra:

- Fulfillment chỉ có một business change.
- Bảng processed messages ghi nhận event đúng một lần.
- Duplicate không gây exception làm retry vô tận.
- Chạy thêm hai instances xử lý cùng event đồng thời để kiểm tra uniqueness.

Câu hỏi: Nếu broker giao hai lần nhưng effect chỉ một lần, đây có phải exactly-once **delivery** không?

**Gợi ý:** Không. Có thể là at-least-once delivery kết hợp exactly-once **effect trong phạm vi đã test**.

### 18.3. Nhiệm vụ C — Ordering

Gửi events với versions `1`, `2`, `3` của cùng `ORD-900` rồi cố tình gửi `1`, `3`, `2`. Định nghĩa rõ ứng dụng sẽ:

- Buffer v3 và chờ v2?
- Retry v3?
- Chỉ áp dụng snapshot mới nhất và bỏ qua v2?
- Báo lỗi và chuyển DLT khi gap không thể giải quyết?

Không có đáp án duy nhất cho mọi domain. Quan trọng là **quy tắc được viết rõ và có test chứng minh**, không phụ thuộc tình cờ vào scheduler.

### 18.4. Nhiệm vụ D — Crash sau commit trước ack

Dùng broker test container hoặc môi trường tích hợp cô lập. Cho consumer commit business effect, rồi dừng trước ack/offset commit. Khởi động lại và xác minh:

1. Broker giao lại message theo cấu hình.
2. Processed event ID ngăn effect lặp.
3. Consumer ack/commit an toàn cho duplicate.
4. Logs/metrics giúp truy vết đầy đủ sự kiện.

Đừng thay bài test này bằng hai lần gọi handler và tuyên bố đã test crash thật.

### 18.5. Nhiệm vụ E — Viết kết luận có ranh giới

Hãy tự viết ba câu:

- “Contract test của chúng tôi bảo vệ ___”.
- “Broker integration test của chúng tôi bảo vệ ___”.
- “Idempotency + transaction test bảo vệ ___”.

Nếu một điều chưa được test, hãy viết “chưa được kiểm chứng” thay vì khẳng định đã bảo đảm.

## 19. Checklist trước khi khẳng định hệ thống messaging an toàn

- [ ] Contract ghi đúng destination, headers, body và schema version mà consumer cần.
- [ ] Generated producer messaging tests thực sự được sinh và chạy.
- [ ] Message verifier, trigger và test context được cấu hình đúng.
- [ ] Không suy ordering/redelivery/exactly-once từ một message contract.
- [ ] Ordering được định nghĩa theo aggregate key, partition/queue hoặc phạm vi cụ thể.
- [ ] Message key, partitioning, consumer concurrency phù hợp yêu cầu.
- [ ] `eventId` ổn định qua mọi redelivery của cùng logical event.
- [ ] Consumer có unique constraint và transaction cho processed-event + business effect.
- [ ] Concurrent duplicate được kiểm thử, không chỉ duplicate tuần tự.
- [ ] Side effects ngoài database có idempotency/compensation.
- [ ] Producer outbox/relay được kiểm thử với crash trước và sau publish.
- [ ] Broker redelivery, ack/offset commit, retry/backoff và DLT đã được kiểm chứng.
- [ ] Test ordering có out-of-order và missing-version scenarios.
- [ ] Test có timeout hữu hạn và tài nguyên cô lập; tránh `Thread.sleep`.
- [ ] Consumer Stub Runner tests kiểm tra xử lý schema, không giả định broker guarantees.
- [ ] CI chặn publish artifact khi producer verification thất bại.
- [ ] Metrics, alerts và replay runbook sẵn sàng cho vận hành.

## 20. Tài liệu tham khảo

- [Spring Cloud Contract — Messaging](https://docs.spring.io/spring-cloud-contract/reference/project-features-messaging.html): `triggeredBy`, `outputMessage`, `sentTo`, label và message verifier.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): ranh giới read-process-write Kafka transaction và consumed offsets.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): partition ordering, partition keys, consumer groups và reliability.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): publisher confirm, ack/nack, requeue và redelivery.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): hướng dẫn hệ thống chịu được redelivery.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): error handlers, backoff và dead-lettering.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox): nhất quán giữa DB commit và publish cùng nguy cơ duplicate relay.

**Ghi nhớ:** Spring Cloud Contract giúp kiểm chứng **message được mô tả đúng**, không tự bảo đảm **mọi message đến đúng thứ tự, chỉ được giao một lần hoặc tạo đúng một business effect**. Cần nêu rõ phạm vi theo aggregate, event ID và transaction boundary; kết hợp idempotent consumer, outbox/inbox, broker integration tests và fault injection. CI đáng tin cậy phải kiểm chứng cả **giao diện dữ liệu** lẫn **hành vi khi retry, duplicate và crash**.
