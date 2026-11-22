# Chẩn đoán duplicate từ log

Khi một hệ thống Spring Kafka xử lý cùng một đơn hàng, thanh toán hoặc thông báo nhiều lần, log thường là nơi đầu tiên đội vận hành tìm bằng chứng. Tuy nhiên, nhìn thấy hai dòng log giống nhau **không đủ để kết luận Kafka đã gửi trùng record**. Một record có thể được giao lại sau khi consumer chưa commit offset; một business event có thể được producer phát hai lần với hai Kafka offsets khác nhau; một listener có thể retry cùng record nhiều lần; hoặc log collector có thể gửi lại cùng một log entry.

Muốn chẩn đoán đúng, phải xác định **đang trùng ở tầng nào**:

- **Duplicate log entry:** cùng một log event xuất hiện nhiều lần trong hệ thống log.
- **Duplicate Kafka delivery:** cùng một Kafka record được consumer xử lý lại, thường có cùng topic-partition-offset.
- **Duplicate publication:** producer ghi hai Kafka records cho cùng một business event, thường có offsets khác nhau.
- **Duplicate business command/event:** client hoặc upstream tạo hai event riêng biệt cho cùng một yêu cầu nghiệp vụ.
- **Duplicate side effect:** cùng một nghiệp vụ được áp dụng nhiều lần, ví dụ trừ tồn kho hoặc charge payment hai lần.
- **Duplicate recovery/replay:** record được retry, gửi DLT rồi replay hoặc được phục hồi qua nhiều đường.

Các tầng này có thể xảy ra cùng lúc nhưng không đồng nghĩa. Ví dụ, consumer nhận lại cùng record hai lần (duplicate delivery), nhưng inbox/idempotency bảo vệ side effect nên business operation chỉ xảy ra một lần. Ngược lại, producer gửi cùng event hai lần ở hai offsets khác nhau có thể khiến consumer xử lý hai lần dù consumer group không hề redeliver cùng một offset.

Bài học thuộc chương **Logging và chẩn đoán** trong module **Spring Kafka Reliability Operations**. Trọng tâm là xây dựng bằng chứng từ structured logs, dùng event ID và topic-partition-offset đúng mục đích, lần theo retry/rebalance/commit, phân biệt producer duplicate với consumer replay và log ingestion duplicate, sau đó đối chiếu với metrics, traces và dữ liệu nghiệp vụ.

## 1. Bốn câu hỏi trước khi kết luận có duplicate

Khi có báo cáo “Kafka xử lý trùng”, hãy hỏi theo thứ tự:

1. **Hai log lines có cùng một log event không?** Kiểm tra log event ID, timestamp gốc, logger, thread, trace/span và collector metadata.
2. **Hai lần xử lý có cùng Kafka record identity không?** So sánh cluster, topic, partition, offset và source/original metadata.
3. **Hai record có cùng business event identity không?** So sánh eventId, commandId hoặc idempotency key.
4. **Business side effect có thực sự xảy ra hai lần không?** Kiểm tra database transaction, payment provider, downstream API và audit records.

Một kết luận tốt chỉ ra được identity và boundary. Ví dụ:

~~~text
Kết luận: consumer redelivery cùng Kafka record.
Kafka cluster: prod-a
Consumer group: inventory-service
Topic-partition-offset: orders.events-2-18420
Observed processing: pod-3 lúc 10:01:02, pod-5 lúc 10:01:08
Lý do khả dĩ: lần xử lý đầu đã hoàn tất DB nhưng offset chưa commit trước rebalance.
Business effect: inbox unique constraint chỉ cho phép reserve stock một lần.
~~~

Đây là kết luận có thể kiểm chứng. Câu “thấy hai dòng OrderCreated nên Kafka gửi trùng” chưa đủ bằng chứng.

## 2. Các tầng identity không được đánh đồng

Một Kafka pipeline có nhiều loại ID:

| Identity | Ví dụ | Dùng để trả lời |
|---|---|---|
| Log event ID | UUID do logging appender tạo | Hai dòng log có phải cùng một log entry bị ingest lặp? |
| Trace ID | 4bf92f... | Các spans có thuộc cùng một request/distributed trace? |
| Span ID | 00f067... | Một operation cụ thể trong trace là gì? |
| Business event ID | evt-7b91 | Hai Kafka records có đại diện cùng business event không? |
| Command/idempotency key | create-order-req-42 | Client có gửi lại cùng yêu cầu không? |
| Kafka record identity | cluster + topic + partition + offset | Đây có phải cùng một record trong log Kafka không? |
| Consumer group | inventory-worker | Tiến độ offset được theo dõi cho group nào? |
| Delivery attempt | 2 | Đây là lần giao/xử lý thứ mấy trong phạm vi attempt tracker? |
| Original record identity | original topic/partition/offset | Retry/DLT record bắt nguồn từ record nào? |

**Topic-partition-offset** là định danh của một record trong một Kafka log cụ thể. Nó không phải business event ID xuyên các topics. Khi record được publish sang retry topic hoặc DLT, nó nhận topic/partition/offset mới.

**Business event ID** có thể được giữ nguyên qua các retry stages, nhưng chỉ đáng tin nếu producer tạo ổn định và các service tuân thủ contract.

**Trace ID** có thể không tồn tại hoặc thay đổi giữa các lần replay dài hạn. Không dùng trace ID làm khóa dedup business trừ khi hệ thống định nghĩa rõ lifecycle của nó.

## 3. Một business event có thể xuất hiện ở nhiều Kafka offsets

Ví dụ producer publish OrderCreated hai lần:

~~~text
orders.events partition 2:
  offset 100 -> eventId=E-42, orderId=O-123
  offset 101 -> eventId=E-42, orderId=O-123
~~~

Đây là **hai Kafka records khác nhau** vì offsets khác nhau, nhưng cùng business event ID. Nguyên nhân có thể:

- HTTP client retry CreateOrder và service không idempotent.
- Outbox publisher gửi lại sau timeout/ack ambiguity.
- Producer code publish ở hai nhánh.
- Event handler nhận lại command và tạo event mới nhưng tái sử dụng business ID.
- Upstream replay một message mà không có dedup.

Consumer group có thể đọc offset 100 rồi offset 101 theo thứ tự bình thường. Không có consumer redelivery nào bắt buộc xảy ra.

Nếu chỉ so sánh offset, đội vận hành sẽ bỏ sót duplicate business event. Nếu chỉ so sánh eventId, đội vận hành có thể nhầm hai record khác nhau thành cùng một Kafka delivery. Cần giữ cả hai identity.

## 4. Cùng topic-partition-offset được xử lý hai lần

Ví dụ:

~~~text
orders.events-2 offset 18420

10:01:02 pod-3 listener started
10:01:03 pod-3 database transaction committed
10:01:04 pod-3 process crashed

10:01:08 pod-5 assigned partition 2
10:01:09 pod-5 listener started offset 18420
~~~

Đây là **redelivery/reprocessing cùng Kafka record**. Lần đầu có thể đã thực hiện side effect nhưng consumer group chưa ghi nhận offset tiếp theo.

Kafka consumer thường đảm bảo tiến độ dựa trên committed offsets, không biết database transaction bên ngoài đã commit hay chưa. Nếu app commit database rồi crash trước khi commit Kafka offset, record có thể được xử lý lại.

Đó là lý do consumer cần idempotency hoặc inbox pattern nếu side effect phải xảy ra một lần theo business semantics.

## 5. Duplicate log entry do log pipeline

Không phải mọi duplicate log đều xuất phát từ Kafka. Log có thể bị lặp bởi:

- Agent thu thập log retry gửi lại batch sau timeout.
- Hai collectors cùng tail một file hoặc cùng nhận stdout.
- Log forwarder có at-least-once delivery và chưa dedup.
- Ứng dụng tự gắn hai appenders cùng ghi một destination.
- Root logger và package logger có additivity gây ghi hai lần.
- Pod restart làm collector đọc lại đoạn file chưa checkpoint.
- Log aggregator reindex một document.
- Một log line multiline bị tách/ghép không đúng.

Ví dụ cùng một log event:

~~~json
{
  "logEventId": "log-8f31",
  "timestamp": "2026-11-15T10:01:02.123Z",
  "message": "kafka_listener_started",
  "eventId": "evt-42",
  "topic": "orders.events",
  "partition": 2,
  "offset": 18420
}
~~~

Nếu hệ thống log lưu hai documents với cùng logEventId và timestamp gốc, nhưng collector receipt time khác nhau, có khả năng đây là **duplicate ingestion**.

Nếu hai log entries có logEventId khác nhau, timestamps khác nhau và cùng Kafka identity, có khả năng listener đã thực sự chạy hai lần.

Nếu ứng dụng không phát log event ID riêng, hãy dùng tổ hợp timestamp gốc, pod, thread, logger, message, trace/span và Kafka identity để điều tra; tổ hợp đó chỉ là heuristic, không phải khóa duy nhất tuyệt đối.

## 6. Thiết kế structured log để điều tra duplicate

Log dạng câu tự do:

~~~text
Received order event
Processing order
Order processed
~~~

khó trả lời event nào, record nào, consumer nào và attempt nào.

Một structured log nên có các trường:

~~~json
{
  "timestamp": "2026-11-15T10:01:02.123Z",
  "level": "INFO",
  "event": "kafka_listener_started",
  "service": "inventory-service",
  "instance": "inventory-pod-3",
  "listener_id": "orders-listener",
  "consumer_group": "inventory-worker",
  "cluster": "prod-a",
  "topic": "orders.events",
  "partition": 2,
  "offset": 18420,
  "key": "O-123",
  "event_id": "evt-42",
  "delivery_attempt": 1,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7"
}
~~~

Đây là schema gợi ý, không phải cấu trúc mặc định mà Spring Kafka tự phát ra cho mọi log. Ứng dụng cần chủ động thêm metadata tại boundary listener hoặc thông qua interceptor/observation phù hợp.

### 6.1. Những trường nên có

- **timestamp:** thời điểm log event được tạo, ưu tiên UTC.
- **event:** tên sự kiện ổn định, ví dụ kafka_listener_started.
- **service/instance:** service và pod/instance identity.
- **listener_id/group:** listener và consumer group.
- **cluster/topic/partition/offset:** Kafka record identity.
- **event_id/command_id:** business identity.
- **delivery_attempt:** attempt metadata nếu có và có phạm vi rõ.
- **trace_id/span_id:** liên kết distributed trace.
- **outcome:** started/succeeded/failed/recovered.
- **exception_group:** taxonomy lỗi có giới hạn.
- **duration_ms:** thời gian xử lý.

Không nhất thiết mọi log line đều chứa toàn bộ trường. Nhưng các event quan trọng như delivery started, processing succeeded, failed, recovery và DLT publication nên chia sẻ correlation fields nhất quán.

## 7. Log các boundary khác nhau, không chỉ một dòng “received”

Một flow tối thiểu nên có các event logs:

~~~text
kafka_listener_started
kafka_listener_succeeded
kafka_listener_failed
kafka_retry_scheduled
kafka_retry_started
kafka_recovery_started
kafka_recovery_succeeded
kafka_recovery_failed
kafka_dlt_published
~~~

Ví dụ:

~~~json
{
  "event": "kafka_listener_succeeded",
  "event_id": "evt-42",
  "topic": "orders.events",
  "partition": 2,
  "offset": 18420,
  "listener_id": "orders-listener",
  "consumer_group": "inventory-worker",
  "delivery_attempt": 2,
  "duration_ms": 18
}
~~~

Không log tất cả events ở INFO trong workload lớn nếu điều đó làm log volume tăng quá mức. Có thể dùng metrics cho mọi attempt, logs có chọn lọc cho failures/recovery và sampling cho successful processing, trong khi vẫn giữ correlation fields đủ để điều tra.

## 8. Ví dụ listener log với ConsumerRecord

Một listener có thể lấy topic, partition, offset và key trực tiếp từ ConsumerRecord:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.events",
    groupId = "inventory-worker"
)
public void consume(
        ConsumerRecord<String, OrderEvent> record) {

    log.info(
        "kafka_listener_started topic={} partition={} offset={} key={} eventId={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.key(),
        record.value().eventId()
    );

    inventoryService.apply(record.value());

    log.info(
        "kafka_listener_succeeded topic={} partition={} offset={} eventId={}",
        record.topic(),
        record.partition(),
        record.offset(),
        record.value().eventId()
    );
}
~~~

Ví dụ này giả định payload có eventId và các trường không nhạy cảm. Nếu key/payload chứa dữ liệu nhận dạng hoặc thông tin bảo mật, cần mask hoặc không log chúng. Không nên in toàn bộ payload chỉ để điều tra duplicate.

### 8.1. Vì sao cần log started và succeeded riêng?

Nếu chỉ log received ở đầu listener, hai dòng received giống nhau có thể là:

- Một record được giao hai lần.
- Một lần giao và một lần log collector duplicate.
- Hai Kafka records có cùng eventId.

Nếu có started và succeeded, ta còn biết lần đầu đã đi tới đâu. Ví dụ started ở pod A nhưng không có succeeded, sau đó started ở pod B có thể là redelivery sau crash hoặc timeout. Nếu succeeded ở cả hai pod cùng Kafka identity, side effect có nguy cơ đã chạy hai lần.

## 9. Delivery attempt header không phải global identity

Spring Kafka có thể cung cấp metadata **delivery attempt** trong những phiên bản/cấu hình phù hợp, ví dụ qua KafkaHeaders.DELIVERY_ATTEMPT và ContainerProperties.

Ví dụ minh họa:

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        @Header(
            name = KafkaHeaders.DELIVERY_ATTEMPT,
            required = false
        ) Integer deliveryAttempt) {

    log.info(
        "delivery topic={} partition={} offset={} attempt={}",
        record.topic(),
        record.partition(),
        record.offset(),
        deliveryAttempt
    );

    inventoryService.apply(record.value());
}
~~~

API để bật header, kiểu dữ liệu và behavior cần xác nhận theo Spring Kafka version. Nếu header vắng mặt, đừng tự coi đó là attempt 1 mà không ghi nhận trạng thái unknown.

**Delivery attempt** thường có phạm vi error handler/container path. Nó không tự đếm lifetime retries của một business event xuyên:

- nhiều retry topics;
- nhiều consumer groups;
- restart hoặc rebalance;
- DLT replay;
- producer republish;
- các service độc lập.

Để điều tra end-to-end, cần business event ID và original record metadata.

## 10. Correlate retry và DLT records về record nguồn

Khi một record chuyển sang retry topic hoặc DLT, nó nhận một Kafka offset mới. Ví dụ:

~~~text
Source:
  orders.events-2 offset 18420

Retry:
  orders-retry-5000-1 offset 900

DLT:
  orders.events.DLT-0 offset 55
~~~

Ba Kafka identities khác nhau có thể cùng liên quan một source event.

Spring Kafka retry-topic và DeadLetterPublishingRecoverer có thể bổ sung headers chứa original topic, partition, offset, exception và thông tin retry tùy cơ chế/phiên bản. Hãy giữ các headers cần thiết và xác nhận tên header/format thực tế trước khi viết parser.

Trong logs, nên chuẩn hóa thành:

~~~json
{
  "event_id": "evt-42",
  "current_topic": "orders-retry-5000",
  "current_partition": 1,
  "current_offset": 900,
  "original_topic": "orders.events",
  "original_partition": 2,
  "original_offset": 18420,
  "stage": "retry"
}
~~~

Không thay thế current record identity bằng original identity. Cả hai đều quan trọng:

- Current identity giúp tìm record đang được consumer xử lý.
- Original identity giúp dựng đường đi của event.

## 11. Dùng event ID ổn định xuyên pipeline

Một event ID nên được tạo khi business event được hình thành và giữ nguyên qua:

- Producer retry.
- Kafka retry topics.
- Consumer redelivery.
- DLT publication.
- DLT replay.
- Downstream service processing.

Ví dụ envelope:

~~~json
{
  "eventId": "evt-42",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateId": "O-123",
  "occurredAt": "2026-11-15T10:00:00Z",
  "payload": {
    "orderId": "O-123"
  }
}
~~~

Nếu producer tạo UUID mới mỗi lần retry gửi lại cùng event, eventId không còn hỗ trợ dedup. Event ID phải được tạo một lần tại command/event creation boundary và được persist nếu cần outbox.

Không tái sử dụng eventId cho hai business events khác nhau chỉ vì cùng aggregateId. Một order có thể phát OrderCreated, OrderPaid và OrderCancelled; mỗi event cần identity riêng.

## 12. Phân biệt duplicate producer với consumer redelivery bằng offset

Đây là phép phân loại đầu tiên:

| Hai log entries | Khả năng |
|---|---|
| Cùng cluster, topic, partition, offset; khác timestamp/instance | Cùng Kafka record được xử lý lại |
| Cùng cluster, topic, partition; offset khác; eventId giống | Hai Kafka records cho cùng business event |
| Topic/partition/offset khác và eventId khác nhưng payload giống | Có thể hai business events riêng, hoặc producer tạo ID sai |
| Cùng logEventId và log timestamp gốc | Có thể log collector ingest lặp |
| Cùng eventId nhưng source metadata khác | Republish/replay hoặc identity reuse; cần truy nguồn |
| Cùng offset nhưng cluster khác | Hai record khác nhau ở hai Kafka clusters |

**Cluster identity** quan trọng. Topic-partition-offset chỉ có ý nghĩa trong một Kafka cluster/log. Hai môi trường có cùng tên topic và offset không phải cùng record.

## 13. Consumer group và instance identity

Khi consumer group có nhiều instances:

~~~text
inventory-worker
  +-- pod-1 owns P0, P3
  +-- pod-2 owns P1, P4
  +-- pod-3 owns P2, P5
~~~

Sau rebalance, partition P2 có thể chuyển từ pod-3 sang pod-1. Nếu record chưa được commit, pod-1 có thể xử lý lại offset cũ.

Logs nên ghi:

- service name;
- pod/instance ID;
- consumer group;
- listener ID;
- client ID nếu cần;
- assignment/rebalance context;
- topic-partition-offset.

Nếu chỉ log eventId, sẽ khó biết duplicate xảy ra do producer republish hay consumer group redeliver. Nếu chỉ log pod ID, không thể biết hai pods có xử lý cùng record hay hai records khác nhau.

## 14. Rebalance là một nguyên nhân thường gặp của redelivery

Một timeline:

~~~text
Pod A nhận offset 500
       |
       v
Listener xử lý business DB thành công
       |
       v
Consumer chưa commit next offset 501
       |
       v
Pod A bị restart hoặc mất group membership
       |
       v
Rebalance giao partition cho Pod B
       |
       v
Pod B bắt đầu từ committed offset trước đó
       |
       v
Offset 500 được giao lại
~~~

Đây là behavior có thể xảy ra với at-least-once processing. Kafka không biết DB của Pod A đã commit.

Để xác minh:

1. So sánh cùng cluster/topic/partition/offset.
2. So sánh instance ID và timestamps.
3. Tìm rebalance, partition revoked/lost và member changes.
4. Xem committed offset trước/sau incident.
5. Kiểm tra processing success ở pod đầu.
6. Kiểm tra idempotency/dedup ở business DB.

Không kết luận producer gửi trùng chỉ vì hai pods cùng log eventId.

## 15. Offset commit failure tạo replay như thế nào?

Giả sử AckMode.BATCH:

~~~text
Poll trả về offset 100, 101, 102
Listener xử lý cả batch thành công
Database commit thành công
Container commit next offsets
        |
        +-- Commit success -> group tiến lên
        |
        +-- Commit failure -> records có thể replay
~~~

Nếu commit failure hoặc process crash xảy ra sau business side effect, records có thể được xử lý lại.

Trong logs cần phân biệt:

- listener_started
- business_processing_succeeded
- offset_commit_requested
- offset_commit_succeeded hoặc commit failure nếu được instrument

Một dòng listener_succeeded không chứng minh offset đã commit. Một dòng commit intent không chứng minh broker đã xác nhận.

## 16. Producer retries và idempotence

Kafka producer có thể retry send khi gặp lỗi tạm thời. **enable.idempotence=true** giúp producer tránh tạo duplicate Kafka log entries do một số retry nội bộ của producer trong phạm vi producer session/protocol semantics.

Tuy nhiên:

- Idempotence không dedup hai lần gọi send() riêng biệt từ application code cho cùng event.
- Idempotence không ngăn HTTP client gửi lại cùng command và service tạo event mới.
- Idempotence không thay thế event ID business.
- Idempotence không bảo vệ side effects ở database hoặc HTTP downstream.
- Một producer restart hoặc producer identity/session khác có semantics riêng; không dùng idempotence như global dedup registry.

Khi nghi producer duplicate, log cần eventId và metadata của lần send:

~~~text
event_id=evt-42
send_invocation_id=send-1
topic=orders.events
key=O-123
result=success
~~~

Nếu cùng eventId có hai send invocations khác nhau và hai Kafka offsets khác nhau, producer/application đã publish hai records. Kiểm tra call paths, retries ở HTTP boundary, event listener duplication và outbox publisher.

## 17. Producer log duplicate không luôn là broker duplicate

Ví dụ:

~~~text
10:00:00 application calls KafkaTemplate.send(E-42)
10:00:01 send callback times out
10:00:02 application logs "retry publish E-42"
10:00:03 application calls send(E-42) again
~~~

Lần đầu có thể broker đã append record nhưng acknowledgement bị mất. Lần gửi thứ hai có thể tạo record thứ hai nếu đây là hai application-level sends riêng.

Log send failed có thể chỉ phản ánh kết quả phía client không nhận được ACK; không chứng minh broker chắc chắn chưa lưu.

Để chẩn đoán:

- Ghi send invocation ID riêng.
- Giữ business eventId ổn định.
- Ghi producer callback outcome và metadata RecordMetadata khi thành công.
- Đối chiếu Kafka topic records theo eventId.
- Xem producer idempotence và transactional ID.
- Xác minh application retry có gọi send mới hay Kafka producer tự retry request.

Không tự động replay publish chỉ vì callback timeout nếu không có event identity/dedup policy phù hợp.

## 18. Producer idempotence và application-level duplicate

Hai tình huống:

**Producer protocol retry:**

~~~text
Application send invocation #1
       |
       v
Producer gửi request
       |
       v
Network retry trong producer protocol
       |
       v
Broker deduplicates theo producer sequence
~~~

**Application gọi send hai lần:**

~~~text
Application send invocation #1 -> E-42
Application send invocation #2 -> E-42
       |
       v
Hai logical sends riêng
       |
       v
Có thể có hai Kafka records
~~~

Idempotent producer giải quyết trường hợp thứ nhất theo protocol. Trường hợp thứ hai cần idempotency ở application/outbox hoặc downstream.

## 19. Kafka transactions không tự khử mọi duplicate business event

Kafka producer transactions có thể atomically commit nhiều Kafka writes và consumed offsets trong consume-transform-produce pipeline.

Chúng giúp xử lý:

- Output Kafka records trong một transaction.
- Offset input gửi vào cùng transaction.
- Abort output khi transaction thất bại.
- read_committed consumers chỉ nhìn thấy transactional records đã commit.

Nhưng Kafka transaction không tự:

- Bao gồm database transaction ngoài Kafka.
- Dedup hai commands giống nhau từ client.
- Ngăn hai service độc lập tạo cùng business event.
- Bảo vệ HTTP side effects.
- Biến hai lần application send() riêng biệt thành một business event.

Khi log cho thấy cùng eventId xuất hiện hai offsets, hãy xem transaction logs/producer identity, nhưng vẫn cần truy ngược event creation boundary.

## 20. Consumer retry có thể tạo duplicate log mà không tạo duplicate Kafka record

Với DefaultErrorHandler, cùng một source record có thể được giao lại trong một chuỗi blocking retries:

~~~text
orders.events-2 offset 18420

Attempt 1 -> failure
Attempt 2 -> failure
Attempt 3 -> success
~~~

Logs có thể chứa ba dòng listener_started với cùng topic/partition/offset, nhưng Kafka log chỉ có **một record** ở offset đó.

Nếu attempt metadata được bật, delivery attempt có thể giúp thấy thứ tự attempts trong phạm vi error handler. Nếu không có metadata, timestamps và cùng Kafka identity vẫn là bằng chứng về repeated processing, nhưng không nhất thiết cho biết chính xác attempt number.

Đừng gọi đây là producer duplicate. Đây là **redelivery/retry của consumer**.

## 21. Non-blocking retry tạo Kafka records mới

Với @RetryableTopic:

~~~text
orders.events P2 offset 18420
       |
       +-- listener failure
       |
       v
orders-retry-5000 P1 offset 900
       |
       +-- retry listener failure
       |
       v
orders-retry-30000 P0 offset 410
       |
       +-- success
~~~

Mỗi retry topic publication tạo một record ở một Kafka log khác, với identity mới. Các logs của cùng eventId ở nhiều topics là **cùng business event qua nhiều processing stages**, không phải nhất thiết producer duplicate ngoài dự kiến.

Khi tìm kiếm logs:

- Giữ eventId.
- Ghi current topic/partition/offset.
- Ghi original topic/partition/offset.
- Ghi retry stage và delivery attempt nếu có.
- Ghi outcome của mỗi stage.

Không group chỉ theo eventId rồi kết luận tất cả entries là duplicates. Một event đi qua các stages là hành vi retry bình thường.

## 22. DLT replay có thể làm record xuất hiện lần nữa

Một record được gửi DLT và sau đó operator replay về topic nguồn hoặc retry topic. Khi đó:

- Business event ID có thể giữ nguyên.
- Current Kafka topic/partition/offset mới.
- Original record metadata có thể được giữ trong headers.
- Processing attempt bắt đầu lại theo scope mới.

Logs cần phân biệt:

~~~text
stage=source
stage=retry
stage=dlt
stage=manual_replay
~~~

Nếu operator replay cùng DLT record nhiều lần, các lần xử lý có thể là intentional. Hãy log replay request ID, actor, reason và eventId để phân biệt manual replay với automatic retry.

Một DLT record được replay không nên tạo eventId mới nếu business semantics vẫn là cùng event. Tuy nhiên, nếu operator tạo một compensating/new command, đó có thể là business event mới và cần identity mới.

## 23. Outbox publisher và duplicate publication

Transactional Outbox giúp business state và event intent được ghi trong cùng database transaction. Nhưng polling publisher thường có một cửa sổ:

~~~text
Outbox row E-42
       |
       v
Kafka send thành công
       |
       v
Process crash trước khi mark row SENT
       |
       v
Publisher chạy lại
       |
       v
Send E-42 lần nữa
~~~

Đây là at-least-once publication; cùng eventId có thể xuất hiện ở hai Kafka offsets. Không nên xóa outbox row hoặc đánh dấu SENT trước khi có bằng chứng publish, vì cách đó có thể biến duplicate thành event loss.

Khi log cho thấy duplicate eventId ở offsets khác nhau:

1. Tìm outbox row ID/eventId.
2. Tìm publisher claim/lease logs.
3. Tìm send acknowledgement và timeout ambiguity.
4. Tìm crash giữa Kafka ACK và DB markSent.
5. Kiểm tra idempotent consumer.

Outbox không tự tạo distributed exactly-once transaction giữa database và Kafka.

## 24. Client retry và duplicate command

Một nguồn duplicate thường bị bỏ qua nằm trước Kafka:

~~~text
Client POST /orders
       |
       v
Service tạo order O-123
       |
       v
DB commit
       |
       v
HTTP response bị mất
       |
       v
Client retry POST /orders
       |
       v
Service tạo order O-124
~~~

Hai orders có thể tạo hai OrderCreated events hợp lệ theo góc nhìn service, dù client chỉ muốn một order.

Nếu API có yêu cầu idempotent, dùng **Idempotency-Key** hoặc command ID:

- Client gửi cùng key khi retry.
- Service persist key với kết quả command trong DB.
- Unique constraint ngăn tạo command/order thứ hai.
- Retry trả về kết quả đã lưu.
- Outbox event chỉ được tạo một lần cho command đã dedup.

Trong logs, ghi commandId/idempotencyKey đã mask hoặc hashed phù hợp, không log secret. Nếu không có command ID, việc thấy cùng payload không đủ để kết luận hai requests là một.

## 25. Consumer idempotency: duplicate delivery không thành duplicate effect

Một cách phổ biến là **inbox/processed_events** với unique constraint, cập nhật cùng transaction với business side effect.

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) NOT NULL,
    consumer_name VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, consumer_name)
);
~~~

Spring service minh họa:

~~~java
@Service
public class InventoryProcessor {

    private final JdbcTemplate jdbc;
    private final InventoryRepository inventoryRepository;

    public InventoryProcessor(
            JdbcTemplate jdbc,
            InventoryRepository inventoryRepository) {
        this.jdbc = jdbc;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void process(OrderCreated event) {
        int inserted = jdbc.update(
            """
            INSERT INTO processed_events(event_id, consumer_name)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            event.eventId(),
            "inventory-service"
        );

        if (inserted == 0) {
            return; // Event đã được xử lý thành công trước đó.
        }

        inventoryRepository.reserve(
            event.orderId(),
            event.items()
        );
    }
}
~~~

**Điều kiện bắt buộc:** insert processed_events và cập nhật inventory phải nằm trong cùng DB transaction. Nếu reserve thất bại, cả dấu processed và side effect phải rollback. Nếu ghi dấu processed trước, commit riêng rồi mới reserve, một failure có thể làm record bị bỏ qua vĩnh viễn khi replay.

Listener:

~~~java
@KafkaListener(topics = "orders.events", groupId = "inventory-worker")
public void onOrderCreated(OrderCreated event) {
    inventoryProcessor.process(event);
}
~~~

Nếu DB commit thành công nhưng Kafka offset commit thất bại, record có thể redeliver. Unique constraint giúp consumer nhận diện eventId đã xử lý và không lặp side effect.

## 26. Event ID phải có scope đúng

Một processed_events table dùng eventId đơn lẻ có thể không đủ nếu:

- Nhiều tenants tự tạo event IDs trùng nhau.
- Nhiều consumer applications cần xử lý cùng event.
- Một service xử lý event theo nhiều workflow độc lập.
- Một replay có chủ đích cần chạy lại một projection mới.

Khóa dedup có thể là:

~~~text
(tenant_id, event_id, consumer_name)
~~~

Hoặc:

~~~text
(event_source, event_id, processing_contract)
~~~

Chọn theo uniqueness contract. Đừng dùng topic-partition-offset làm dedup key business nếu cùng event được republish sang topic khác; cũng đừng dùng eventId đơn lẻ nếu producer không đảm bảo uniqueness.

## 27. Logs cho idempotency decisions

Khi consumer thấy event đã được xử lý, nên log một event riêng có outcome **duplicate_suppressed**:

~~~json
{
  "event": "kafka_duplicate_suppressed",
  "service": "inventory-service",
  "consumer_group": "inventory-worker",
  "event_id": "evt-42",
  "topic": "orders.events",
  "partition": 2,
  "offset": 18421,
  "reason": "processed_event_exists"
}
~~~

Đây là ví dụ: offset 18421 có thể là một Kafka record mới nhưng cùng eventId đã được xử lý. Log giúp phân biệt **duplicate business event bị dedup** với **same offset redelivery**.

Đừng log mọi duplicate suppression ở ERROR. Trong at-least-once systems, duplicate delivery có thể là behavior dự kiến. Dùng DEBUG/INFO có sampling và metric counter; chỉ alert khi tỷ lệ vượt baseline hoặc liên quan side effect nguy hiểm.

## 28. Log collector duplicate: cách xác minh

Để phân biệt log collector replay với ứng dụng thực sự phát lại:

1. Kiểm tra logEventId nếu appender/collector tạo được ID ổn định.
2. So sánh event timestamp gốc với ingestion/receipt timestamp.
3. So sánh host/pod, process ID, thread và logger.
4. Kiểm tra hai documents có cùng raw message bytes và source offset của log file không.
5. Xem collector checkpoints, retry batches và duplicate ingestion metrics.
6. Kiểm tra root logger/additivity và appender wiring.

Ví dụ:

~~~text
Document A:
  event timestamp = 10:00:01.100
  collector time  = 10:00:02
  logEventId      = L-77

Document B:
  event timestamp = 10:00:01.100
  collector time  = 10:00:15
  logEventId      = L-77
~~~

Nếu raw source event là cùng một log entry và collector gửi lại sau retry, khả năng duplicate ingestion cao.

Ngược lại:

~~~text
Document A:
  event timestamp = 10:00:01.100
  pod             = pod-1
  thread          = kafka-consumer-1

Document B:
  event timestamp = 10:00:07.200
  pod             = pod-2
  thread          = kafka-consumer-2
~~~

Cùng Kafka identity nhưng hai app log events khác thời điểm/instance có khả năng là redelivery thật.

## 29. Logger additivity và appender bị gắn hai lần

Trong Logback, logger con có thể truyền log events lên root logger theo **additivity**. Nếu cùng một appender được cấu hình ở logger con và root, một log event có thể được ghi hai lần.

Ví dụ cấu hình minh họa dễ gây lặp:

~~~xml
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>

<logger name="com.example.inventory" level="INFO">
    <appender-ref ref="CONSOLE"/>
</logger>
~~~

Nếu logger con vẫn additivity=true mặc định và cùng appender được tham chiếu ở cả hai nơi, một event có thể đi qua hai đường tới console.

Giải pháp:

- Chỉ gắn appender ở một cấp khi có thể.
- Nếu logger con cần appender riêng, cân nhắc additivity="false" và xác nhận không làm mất logs khác.
- Kiểm tra appender references và logback-spring.xml.
- So sánh log event ID và source stream.

Đừng sửa Kafka consumer hoặc producer chỉ để xử lý một duplicate log do logging configuration.

## 30. MDC và thread reuse

MDC thường dựa trên thread-local context. Consumer thread được tái sử dụng qua nhiều records. Nếu không xóa MDC, record sau có thể kế thừa eventId/topic/offset của record trước.

Ví dụ sai:

~~~java
MDC.put("event_id", event.eventId());
inventoryService.process(event);
// Không remove MDC
~~~

Log tiếp theo trên cùng thread có thể chứa metadata cũ, làm điều tra duplicate sai.

Cách an toàn:

~~~java
try {
    MDC.put("event_id", event.eventId());
    MDC.put("kafka.topic", record.topic());
    MDC.put("kafka.partition", Integer.toString(record.partition()));
    MDC.put("kafka.offset", Long.toString(record.offset()));

    inventoryService.process(event);
}
finally {
    MDC.remove("event_id");
    MDC.remove("kafka.topic");
    MDC.remove("kafka.partition");
    MDC.remove("kafka.offset");
}
~~~

Hoặc dùng cơ chế copy/restore context phù hợp. Với asynchronous executor, MDC không tự động truyền sang thread khác nếu không có instrumentation/context propagation.

Một log line có eventId không khớp với message thực tế có thể là lỗi MDC propagation, không phải duplicate Kafka.

## 31. Timestamp và clock skew

Khi so sánh logs trên nhiều pods, timestamp có thể lệch do:

- NTP synchronization.
- VM/container clock drift.
- Log pipeline parse timezone sai.
- Timestamp event gốc khác timestamp collector receipt.
- Producer occurredAt khác consumer processing time.

Để điều tra:

- Ghi timestamp UTC.
- Ghi event occurredAt và log timestamp riêng nếu cần.
- Dùng monotonic clock cho duration trong cùng JVM.
- Dùng trace/span timestamps và collector ingest time để đối chiếu.
- Không kết luận thứ tự causality chỉ từ timestamps nếu clock skew đáng kể.

Offset trong cùng partition có thứ tự log ổn định; timestamps không thay thế offset để xác định record order.

## 32. Dùng trace để lần theo duplicate

Distributed tracing có thể nối:

~~~text
HTTP request
   |
   v
Order service writes DB + outbox
   |
   v
Kafka publish
   |
   v
Inventory consumer
   |
   v
Inventory DB transaction
~~~

Nếu một event được redeliver, mỗi lần xử lý có thể tạo span mới. Có thể giữ business event ID làm span attribute và dùng links/parent context phù hợp cho asynchronous messaging.

Không nhất thiết reuse cùng span ID cho nhiều lần xử lý. Một span mô tả một operation; redelivery là một operation mới, nhưng có thể liên kết với cùng event ID/original context.

Trace ID cũng không phải durable dedup key:

- Trace có thể hết retention trước khi DLT replay.
- Retry consumer có thể tạo trace mới.
- Sampling có thể bỏ mất một số traces.
- Producer và consumer có thể không propagate context đúng.

Dùng traces để hiểu causal path; dùng eventId và idempotency store để nhận diện business event.

## 33. Metrics bổ sung cho duplicate investigation

Một số metrics hữu ích:

| Metric | Ý nghĩa |
|---|---|
| listener_attempts_total | Số lần listener bắt đầu xử lý |
| listener_failures_total | Số attempts thất bại |
| retry_attempts_total | Số retry attempts thực sự bắt đầu theo định nghĩa |
| recovery_attempts_total | Số lần recovery bắt đầu |
| dlt_publish_success_total | Số DLT publishes được xác nhận |
| idempotency_duplicate_hits_total | Số lần dedup chặn side effect lặp |
| same_record_redelivery_total | Số lần cùng topic-partition-offset được xử lý lại nếu instrumentation xác định được |
| duplicate_event_id_observed_total | Số lần eventId xuất hiện lại theo scope đã định nghĩa |
| offset_commit_failures_total | Số commit failures |
| rebalance_total | Số lần rebalance |
| producer_send_retry_total | Producer send retries theo metric/client semantics |
| consumer_lag | Lag theo group/partition |

Các tên trên là metric custom/khái niệm; không phải tất cả đều có sẵn trong Spring Kafka. Không đưa eventId hoặc offset làm labels vào Prometheus. Dùng logs/traces để lưu identity chi tiết.

### 33.1. Duplicate rate phải có denominator

Ví dụ:

~~~text
duplicate_event_rate =
  duplicate_event_id_observed
  / distinct_or_total_input_events
~~~

Phải nói rõ denominator là:

- Total Kafka deliveries?
- Distinct event IDs?
- Producer send invocations?
- Business commands?

Nếu numerator là duplicate deliveries còn denominator là producer sends, tỷ lệ không có ý nghĩa trực tiếp.

## 34. PromQL ví dụ

Giả sử ứng dụng export các custom counters:

~~~promql
sum by (service, consumer_group) (
  rate(app_kafka_idempotency_duplicate_hits_total[5m])
)
~~~

Tốc độ listener failures:

~~~promql
sum by (listener_id, exception_group) (
  rate(app_kafka_listener_failures_total[5m])
)
~~~

Tỷ lệ duplicate suppression trên listener attempts:

~~~promql
sum(rate(app_kafka_idempotency_duplicate_hits_total[10m]))
/
clamp_min(
  sum(rate(app_kafka_listener_attempts_total[10m])),
  0.000001
)
~~~

Query này chỉ hợp lệ nếu duplicate hits và listener attempts cùng scope, stage, labels và unit. Nếu idempotency hits đếm theo distinct business event còn listener attempts đếm theo record delivery, ratio chỉ là một chỉ báo tương đối.

## 35. Không dùng event ID làm metric label

Một event ID mới cho mỗi message có cardinality gần như không giới hạn. Nếu metric có label event_id:

~~~text
app_kafka_duplicate_total{event_id="evt-1"}
app_kafka_duplicate_total{event_id="evt-2"}
app_kafka_duplicate_total{event_id="evt-3"}
...
~~~

Time series tăng theo lượng events và làm hệ thống metrics tốn bộ nhớ/storage rất lớn.

Metric labels nên có tập giá trị giới hạn:

- service;
- listener_id;
- consumer_group;
- topic (nếu danh sách topic hữu hạn);
- stage=main/retry/dlt;
- duplicate_type=redelivery/republished/log_ingestion;
- exception_group.

Event ID, command ID, trace ID và topic-partition-offset nên nằm trong structured logs hoặc traces.

## 36. Chẩn đoán theo mẫu logs

### Mẫu A: cùng Kafka identity, hai pods

~~~text
10:00:01 pod-A listener_started topic=orders.events p=2 o=18420 eventId=E-42
10:00:02 pod-A business_succeeded topic=orders.events p=2 o=18420 eventId=E-42
10:00:05 pod-B listener_started topic=orders.events p=2 o=18420 eventId=E-42
~~~

Khả năng cao là redelivery cùng record. Kiểm tra commit, crash, rebalance và idempotency. Pod B có thể đang lặp side effect nếu không có inbox.

### Mẫu B: eventId giống, offsets khác

~~~text
10:00:01 pod-A listener_started topic=orders.events p=2 o=18420 eventId=E-42
10:00:05 pod-A listener_started topic=orders.events p=2 o=18421 eventId=E-42
~~~

Hai Kafka records khác nhau cho cùng business event. Tìm producer/outbox/client retry hoặc upstream replay.

### Mẫu C: cùng logEventId, collector time khác

~~~text
source_time=10:00:01.100 logEventId=L-77 collector_time=10:00:02
source_time=10:00:01.100 logEventId=L-77 collector_time=10:00:15
~~~

Khả năng cao log ingestion duplicate. Kiểm tra collector retry/checkpoint và appender configuration.

### Mẫu D: eventId giống qua main và retry topics

~~~text
topic=orders.events offset=18420 eventId=E-42 stage=main
topic=orders-retry-5000 offset=900 eventId=E-42 stage=retry
~~~

Đây có thể là non-blocking retry đúng thiết kế. Cần original metadata và stage, không gọi ngay là producer duplicate.

### Mẫu E: cùng eventId, DLT rồi replay

~~~text
topic=orders.events.DLT offset=55 eventId=E-42 stage=dlt
topic=orders.events offset=19000 eventId=E-42 stage=manual_replay
~~~

Đây là replay có thể có chủ đích. Kiểm tra replay request, actor, reason và idempotency behavior.

## 37. Quy trình điều tra duplicate từ log

Một quy trình thực tế:

**Bước 1 — Lấy hai log entries đầy đủ**

Không chỉ copy message text. Lấy timestamp gốc, pod, logger, thread, event ID, trace ID, topic, partition, offset và stage.

**Bước 2 — Xác định duplicate type**

- Cùng log event ID?
- Cùng Kafka identity?
- Cùng business event ID?
- Hay chỉ payload giống nhau?

**Bước 3 — Dựng timeline**

Sắp xếp theo source timestamp, offset, instance và rebalance. Xác định processing started/succeeded/failed, commit request/outcome, restart và retry.

**Bước 4 — Xác minh Kafka group state**

Kiểm tra consumer group, committed offsets, lag và assignment tại thời điểm sự cố nếu telemetry có lưu.

**Bước 5 — Tìm producer path**

Nếu offsets khác nhưng eventId giống, tìm command ID, outbox row, producer send invocations, retries và ack ambiguity.

**Bước 6 — Xác minh business side effect**

Kiểm tra unique constraints, processed_events/inbox, payment provider idempotency keys, database audit hoặc downstream request IDs.

**Bước 7 — Phân loại và khắc phục**

Chọn nguyên nhân: redelivery, producer republish, retry/replay, duplicate command, log collector duplication hoặc instrumentation lỗi.

**Bước 8 — Xác nhận sau fix**

Theo dõi duplicate rate, lag, commit failures, idempotency hits và business outcomes. Không chỉ xác nhận log lines giảm.

## 38. Runbook: cùng offset được xử lý trên hai pods

### Bước 1: Xác nhận identity

Đảm bảo hai log entries cùng Kafka cluster, topic, partition và offset. Kiểm tra consumer group và listener ID.

### Bước 2: Xem timeline

Tìm processing started/succeeded của pod đầu. Tìm crash, SIGTERM, OOMKilled, timeout hoặc rebalance gần đó.

### Bước 3: Xem commit

Đối chiếu commit intent/outcome và consumer group committed offset. Nhớ committed offset là next offset.

### Bước 4: Kiểm tra business transaction

Pod đầu đã commit DB chưa? Pod sau có dedup qua eventId/inbox không? Side effect có thực sự lặp không?

### Bước 5: Khắc phục

Nếu là behavior at-least-once dự kiến, đảm bảo idempotency. Nếu do max.poll.interval.ms/rebalance không phù hợp, giảm thời gian blocking, đặt timeout và điều chỉnh batch/poll settings.

### Bước 6: Xác minh

Kiểm tra record có được xử lý cuối cùng, committed offset tiến, duplicate side effect bằng 0 và rebalance ổn định.

## 39. Runbook: eventId giống nhưng offsets khác

1. Xác nhận current topic/partition/offset của từng record.
2. So sánh eventId, eventType, aggregateId và payload fingerprint.
3. Tìm commandId/idempotency key tại API boundary.
4. Tìm outbox row ID và publisher logs.
5. Kiểm tra producer send invocation IDs và acknowledgement timeouts.
6. Xem application có hai call paths publish cùng event không.
7. Kiểm tra manual replay hoặc retry topic routing.
8. Đối chiếu database business event/audit.
9. Thêm unique constraint/dedup tại command/outbox boundary nếu root cause là duplicate creation.
10. Giữ consumer idempotency để bảo vệ trước những duplicate đã tồn tại.

Không xóa record Kafka hoặc reset offsets để làm biến mất bằng chứng trước khi lưu log/audit cần thiết.

## 40. Runbook: duplicate log lines nhưng Kafka offsets không đổi

Khả năng:

- Collector gửi lại cùng log event.
- Logback appender được gắn hai lần.
- Root logger additivity ghi hai đường.
- Application code gọi logger hai lần.
- Log aggregator reindex document.

Kiểm tra:

1. logEventId hoặc source file offset.
2. Raw event timestamp và collector ingest time.
3. Appender refs/root logger config.
4. Collector retry/checkpoint metrics.
5. Pod/process/thread identity.
6. Có một hay hai listener started events thật.

Nếu Kafka group offsets và listener invocation metrics không thay đổi nhưng log documents nhân đôi, ưu tiên điều tra logging pipeline trước.

## 41. Runbook: side effect bị thực hiện hai lần

Đây là tình huống cần xử lý theo mức độ nghiệp vụ cao nhất.

1. Xác định business event ID và side effect ID.
2. Kiểm tra có hai Kafka records hay cùng record redeliver.
3. Xác định lần xử lý đầu đã commit database hay gọi external API thành công chưa.
4. Kiểm tra inbox/unique constraint/idempotency key.
5. Kiểm tra external provider có hỗ trợ idempotency và request lookup không.
6. Dừng hoặc giới hạn nguồn tạo thêm duplicate nếu cần và an toàn.
7. Reconcile dữ liệu nghiệp vụ: hoàn tiền, hoàn tồn kho hoặc sửa trạng thái theo quy trình domain.
8. Khắc phục ranh giới transaction và retry.
9. Thử lại trong môi trường test với crash giữa side effect và offset commit.

Không chỉ sửa log hoặc tăng retry limit. Nếu business side effect không idempotent, duplicate có thể tiếp tục gây thiệt hại dù logs đã được dedup.

## 42. Kiểm thử duplicate delivery

Một integration test nên:

1. Publish một event với eventId ổn định.
2. Cho consumer ghi business state và inbox trong cùng transaction.
3. Làm consumer không commit offset sau lần xử lý đầu, hoặc mô phỏng crash/rebalance trong môi trường test.
4. Để consumer nhận lại cùng topic-partition-offset.
5. Xác nhận listener log hai attempts.
6. Xác nhận inbox chỉ ghi một event ID và business side effect xảy ra một lần.
7. Xác nhận consumer group cuối cùng tiến offset.

Điều quan trọng là kiểm tra **cùng Kafka identity** được giao lại và side effect vẫn idempotent.

## 43. Kiểm thử duplicate publication

1. Tạo một business event với eventId ổn định.
2. Gửi producer send lần đầu và làm kết quả ACK bị timeout/không rõ trong môi trường test.
3. Kích hoạt application-level retry hoặc outbox reclaim.
4. Xác nhận có thể tồn tại hai Kafka offsets cho cùng eventId.
5. Xác nhận consumer inbox/dedup chỉ thực hiện side effect một lần.
6. Ghi nhận send invocation ID và producer outcomes.

Test cần phân biệt producer protocol retries với hai application sends riêng. Không giả định mọi timeout đều tạo duplicate hoặc không tạo duplicate.

## 44. Kiểm thử log collector duplicate

Trong môi trường logging test:

- Gửi một log event có event ID ổn định.
- Mô phỏng collector retry batch hoặc gửi cùng source event hai lần.
- Xác nhận log backend nhận hai documents nhưng source log event identity giống nhau.
- Kiểm tra application listener attempts và Kafka offsets không đổi.
- Xác nhận dashboard có thể phân loại ingestion duplicate khỏi processing duplicate.

Không thay đổi consumer logic để xử lý duplicate log ingestion nếu nguyên nhân nằm ở collector/appender.

## 45. Kiểm thử retry và DLT correlation

Một kịch bản:

~~~text
Source event E-42
   |
   v
Blocking retry attempt 1
   |
   v
Non-blocking retry topic
   |
   v
Retry listener fails
   |
   v
DLT publication
   |
   v
Manual replay
~~~

Xác nhận:

- Event ID giữ nguyên.
- Current Kafka identity thay đổi theo topic/stage.
- Original topic/partition/offset được lưu đúng.
- Retry stage và delivery attempt được log rõ.
- Replay request ID/actor được ghi.
- Idempotency xử lý theo business policy.

## 46. Những sai lầm chẩn đoán thường gặp

| Sai lầm | Vì sao sai | Cách điều chỉnh |
|---|---|---|
| Hai dòng log giống nhau = Kafka gửi duplicate | Có thể log collector ingest lặp | Kiểm tra log event identity và Kafka offsets |
| Cùng eventId = cùng Kafka record | Hai records có thể ở offsets khác nhau | So sánh cluster/topic/partition/offset |
| Offset giống nhau = cùng record trên mọi cluster | Offset chỉ có nghĩa trong một cluster/log | Ghi cluster identity |
| Listener chạy hai lần = producer gửi hai records | Consumer có thể redeliver cùng offset | Xem rebalance/commit/retry |
| Hai offsets khác nhau = business duplicate chắc chắn | Payload giống có thể là hai events hợp lệ | Dùng event/command identity và domain |
| Trace ID là dedup key | Trace sampling/retention/replay thay đổi | Dùng eventId bền vững |
| DeliveryAttempt là lifetime attempt count | Scope có thể reset qua retry stages/restart | Dùng stage-aware correlation |
| Producer idempotence chặn mọi duplicate | Không dedup hai application sends riêng | Idempotency/outbox ở app boundary |
| Kafka transaction bảo vệ database side effect | Kafka transaction không bao gồm DB/HTTP | Inbox/outbox/saga |
| Log succeeded chứng minh offset commit | Listener success và commit là hai boundary | Log/metric commit outcome riêng |
| Offset commit chứng minh business success | Record có thể được recover vào DLT | DLT và business metrics riêng |
| Chỉ dedup logs là đủ | Side effect có thể đã lặp | Kiểm tra business DB/external provider |
| MDC không cần cleanup | Thread reuse làm metadata rò sang record sau | Cleanup/propagate context rõ ràng |
| Event ID làm metric label | Cardinality tăng theo event volume | ID trong logs/traces |
| Reset offset để loại duplicate | Có thể bỏ qua dữ liệu và phá bằng chứng | Reconcile trước, chỉ thao tác theo quy trình |

## 47. Checklist production

Khi xây dựng khả năng chẩn đoán duplicate:

1. Structured logs có cluster, consumer group, listener, topic, partition và offset không?
2. Logs có business event ID/command ID ổn định không?
3. Retry/DLT logs có current và original topic-partition-offset không?
4. Có ghi instance/pod ID và trace/span context không?
5. Có tách listener started/succeeded/failed, retry, recovery và DLT publication events không?
6. Delivery attempt metadata có được bật và hiểu đúng scope không?
7. Có phân biệt cùng Kafka identity với cùng business event identity không?
8. Producer send logs có invocation ID và acknowledgement outcome không?
9. Consumer group committed offsets/rebalance có thể đối chiếu với logs không?
10. Có idempotency/inbox unique constraint cho side effects cần bảo vệ không?
11. Outbox publisher có event ID ổn định và retry observability không?
12. DLT replay có actor/reason/request ID và dedup policy không?
13. Logging appender/root logger/collector có được kiểm tra duplicate ingestion không?
14. MDC có cleanup trên consumer thread và propagation trên async executor không?
15. Clock/timestamps có UTC và duration có dùng monotonic clock không?
16. Metrics có đếm duplicate suppression, retry, recovery, rebalance và commit failures không?
17. Prometheus labels có tránh event IDs và dữ liệu high-cardinality không?
18. Dashboard có tách producer duplicate, consumer redelivery và log ingestion duplicate không?
19. Có test crash sau DB commit trước Kafka offset commit không?
20. Có runbook đối soát side effect khi duplicate đã xảy ra không?

## 48. Kết luận

**Chẩn đoán duplicate từ log phải bắt đầu bằng identity và boundary.** Cùng topic-partition-offset trên cùng cluster cho thấy cùng một Kafka record được xử lý lại; eventId giống nhưng offsets khác cho thấy nhiều Kafka records cùng đại diện một business event; logEventId giống nhưng ingestion times khác có thể chỉ là log collector gửi lại một entry. Những tình huống này có nguyên nhân và cách khắc phục khác nhau.

Trong Spring Kafka, hãy ghi structured logs tại các boundary listener, retry, recovery, DLT và commit; giữ business event ID ổn định; lưu current/original Kafka metadata; đối chiếu với consumer group offsets, rebalance, producer acknowledgements và transaction outcomes. Dùng inbox/idempotency để bảo vệ side effects trước redelivery, và outbox/idempotent command handling để hạn chế duplicate publication từ upstream. Logs cho biết **điều gì đã được quan sát**, metrics cho thấy **tần suất và xu hướng**, traces nối **đường đi**, còn database/audit xác nhận **business effect có thực sự xảy ra hay không**.

Một hệ thống đáng tin cậy không cần giả định duplicate sẽ không bao giờ xuất hiện. Nó cần nhận diện được duplicate ở đúng tầng, giữ dữ liệu có thể truy vết và bảo đảm việc xử lý lại không tạo ra side effect ngoài ý muốn.
