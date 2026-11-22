# Kiểm tra message flow bằng Java Logging

## 1. Vì sao cần kiểm tra message flow?

Trong ứng dụng dùng message broker, việc một service gửi thông điệp không đồng nghĩa thông điệp đã được broker lưu, chuyển đến consumer hoặc xử lý thành công. Một hành trình có thể đi qua **producer → broker → consumer → database → acknowledgment**, đồng thời phát sinh retry, redelivery, dead-letter queue (DLQ), fan-out và các message tiếp theo.

**Kiểm tra message flow** là việc dùng logging có cấu trúc, định danh tương quan, broker metadata, traces, metrics và đối soát nghiệp vụ để trả lời: một logical message đang ở đâu, đã đi qua những stage nào, lần thử thứ mấy, bước nào đã được xác nhận và bước nào mới chỉ được yêu cầu?

Những câu hỏi thực tế:

- Producer đã **yêu cầu publish** hay đã nhận **broker confirmation**?
- Message đã vào topic/queue nào, qua partition/offset hoặc routing key nào?
- Consumer nào nhận, có xử lý nghiệp vụ thành công hay chỉ deserialize thành công?
- Consumer đã ACK/commit theo đúng cơ chế broker chưa?
- Một lỗi tạm thời đã dẫn đến retry, redelivery hay DLQ?
- Có duplicate, lost confirmation, out-of-order processing hoặc missing stage không?
- traceId, messageId, correlationId và attemptNo có được bảo toàn qua thread và service không?
- Nếu dashboard không thấy ERROR, điều đó do message thành công hay vì thiếu dữ liệu quan sát?

**Logging không tự chứng minh exactly-once hoặc durability.** Một dòng log cho biết application đã ghi nhận một trạng thái; xác nhận cuối cần đối chiếu với broker, outbox/inbox, business database và chính sách commit.

## 2. Mô hình hành trình một thông điệp

~~~text
HTTP request / domain event / scheduled job
                    |
                    v
                Producer
               create event
                    |
                    v
             PUBLISH_REQUESTED
                    |
             broker send attempt
                    |
              +-----+------+
              |            |
              v            v
      PUBLISH_CONFIRMED  FAILED / UNKNOWN
              |
              v
       Topic / exchange / queue
              |
              v
         DELIVERY_RECEIVED
              |
              v
        PROCESSING_STARTED
              |
          +---+----+
          |        |
          v        v
       SUCCESS    FAILURE
          |        |
          v        +--> RETRY_SCHEDULED
     ACK/COMMIT               |
          |                   v
          v                REDELIVERY
     COMPLETED                |
                              +--> MAX_ATTEMPTS --> DLQ
~~~

Sơ đồ mô tả **các trạng thái logic**, không phải một giao thức duy nhất. Kafka có producer callback và consumer offset commit; RabbitMQ có publisher confirms và consumer ack/nack/reject. Các hệ thống queue quản lý visibility timeout, message lock hoặc sessions còn có cách settlement khác.

Vì vậy **cần định nghĩa chính xác mỗi stage trước khi ghi log**. Tên PUBLISHED ở một hệ thống có thể nghĩa là đã gọi send(), nhưng ở hệ thống khác nghĩa là đã nhận xác nhận broker. Khi kiểm tra flow, hai nghĩa này không được đánh đồng.

## 3. Phân biệt message ID, event ID và trace ID

| Field | Vai trò | Lưu ý |
| --- | --- | --- |
| **messageId** | Nhận diện logical message trong hành trình xử lý | Nên ổn định qua retry/redelivery của cùng message |
| **eventId** | Nhận diện sự kiện nghiệp vụ để chống duplicate | Có thể khác messageId nếu một event tạo nhiều messages |
| **correlationId / workflowId** | Liên kết nhiều message cùng workflow/request | Một request có thể tạo fan-out nhiều nhánh |
| **causationId / parentMessageId** | Chỉ message/event đã gây ra message con | Hỗ trợ dựng đồ thị quan hệ nhân quả |
| **traceId** | Liên kết các span của distributed trace | Không phải bằng chứng broker ACK |
| **spanId** | Nhận diện một đoạn hoạt động trong trace | Thay đổi khi sinh span khác |
| **attemptNo** | Đánh dấu lần xử lý/retry | Phải định nghĩa tăng từ đâu và ở boundary nào |
| **deliveryId** | Nhận diện một lần giao từ broker nếu có | Không phải lúc nào broker cũng cấp ID toàn cục |
| **consumerGroup / subscription** | Phân biệt nhóm xử lý một message | Cùng message có thể hợp lệ ở nhiều subscriber |
| **topic-partition-offset** | Tọa độ Kafka record | Offset chỉ có nghĩa trong partition tương ứng |
| **queue + routingKey + deliveryTag** | Ngữ cảnh RabbitMQ | Delivery tag thuộc phạm vi channel |

**Không dùng traceId thay cho messageId.** Một trace có thể chứa nhiều messages, còn một message có thể được xử lý nhiều lần với nhiều spans. Tương tự, không dùng offset Kafka làm ID toàn cục vì offset có thể trùng giữa các partitions.

Các ID được lấy từ client/header bên ngoài phải được validate, giới hạn độ dài và tránh log injection; nếu cần bảo đảm correlation ID tin cậy, hãy tạo một ID tại trust boundary.

## 4. Xây dựng từ điển lifecycle events

Một hệ thống dễ quan sát cần **eventName ổn định**, không chỉ viết câu tự do “message is being handled”.

| Event | Thời điểm hợp lệ | Không được hiểu nhầm |
| --- | --- | --- |
| MESSAGE_CREATED | Envelope logic đã tạo | Chưa chắc đã publish |
| PUBLISH_REQUESTED | Producer gọi API gửi | Chưa có broker confirmation |
| PUBLISH_CONFIRMED | Callback/future/confirm báo thành công theo cấu hình | Consumer chưa chắc đã xử lý |
| PUBLISH_FAILED | API gửi/confirm báo lỗi | Nếu mất ACK, broker vẫn có thể đã nhận |
| DELIVERY_RECEIVED | Consumer nhận record/delivery | Chưa hoàn thành handler |
| PROCESSING_STARTED | Handler bắt đầu xử lý | Side effect chưa commit |
| PROCESSING_SUCCEEDED | Hành động đã hoàn tất theo hợp đồng nghiệp vụ | ACK/offset commit có thể chưa xong |
| PROCESSING_FAILED | Một attempt thất bại | Message có thể được thử lại |
| RETRY_SCHEDULED | Đã lên lịch retry theo policy | Không có nghĩa broker đã giao lại |
| REDELIVERED | Một delivery mới thực sự xảy ra | Không phải message nghiệp vụ mới |
| ACKNOWLEDGED | Broker settlement/commit được thực hiện theo API phù hợp | Không tự chứng minh exactly-once |
| DEAD_LETTERED | Message đã được chuyển DLQ theo policy và xác nhận cần thiết | Chưa được xử lý nguyên nhân |
| DEDUPLICATE_SKIPPED | Event đã xử lý trước đó nên bỏ qua side effect | Đây là nhánh xử lý đúng của redelivery |
| REPLAYED | Có lần replay được kiểm soát từ DLQ/archive | Cần policy idempotency và audit riêng |

Các tên này là **quy ước gợi ý**. Ở production phải có tài liệu định nghĩa rõ điều kiện phát event, producer/consumer nào chịu trách nhiệm và có xác nhận từ hệ thống nào.

### Ví dụ phân biệt hai thời điểm

~~~text
2026-11-10T02:41:00Z INFO event=PUBLISH_REQUESTED messageId=msg-101
2026-11-10T02:41:01Z INFO event=PUBLISH_CONFIRMED messageId=msg-101
2026-11-10T02:41:03Z INFO event=DELIVERY_RECEIVED messageId=msg-101
2026-11-10T02:41:04Z INFO event=PROCESSING_SUCCEEDED messageId=msg-101
2026-11-10T02:41:05Z INFO event=ACKNOWLEDGED messageId=msg-101
~~~

Đây là **log minh họa**, không phải thời gian/hành vi mặc định của một broker. Nhờ có các stage riêng, người điều tra không kết luận nhầm rằng app “đã gửi” nghĩa là đã hoàn tất giao dịch.

## 5. Schema của một structured log event

Ví dụ JSON cho một consumer xử lý thành công:

~~~json
{
  "timestamp": "2026-11-10T02:41:04Z",
  "level": "INFO",
  "service": "order-consumer",
  "environment": "production",
  "instanceId": "worker-3",
  "event": "PROCESSING_SUCCEEDED",
  "messageId": "msg-101",
  "eventId": "evt-101",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "correlationId": "req-42",
  "consumerGroup": "orders",
  "topic": "order-commands",
  "partition": 2,
  "offset": 108,
  "attemptNo": 2,
  "durationMs": 37,
  "outcome": "SUCCESS"
}
~~~

Đây là **schema minh họa**, không phải JSON tự sinh từ Java SE. Các field cần được định nghĩa nhất quán về tên, kiểu dữ liệu và nghĩa:

1. **timestamp** nên có timezone/UTC rõ ràng; ghi cả occurredAt và recordedAt nếu cần phân biệt.
2. **service/environment/version/instance** để biết event phát từ bản triển khai nào.
3. **messageId/eventId/correlationId** theo envelope/headers; không lấy raw payload làm ID.
4. **event** có tập giá trị hữu hạn, tốt cho dashboard/alert hơn message text.
5. **attemptNo**, retryReasonCode, retryable, errorCode khi có lỗi.
6. **broker coordinates** (topic/partition/offset hoặc queue/routing key) chỉ khi API thật sự cung cấp.
7. **duration/outcome** được tính quanh bước có ý nghĩa nghiệp vụ, không dùng thời gian một câu logger thay thế processing latency.
8. **exception.type** và dữ liệu chẩn đoán tối thiểu khi thất bại; không mặc định dump toàn bộ payload.

Trong JSON encoder, serialization phải escape đúng dấu ngoặc kép, Unicode và xuống dòng. Structured logging giải quyết **framing và truy vấn**, nhưng **không tự redact** token hoặc dữ liệu riêng tư.

## 6. Producer: quan sát publish request và broker confirmation

Ở producer, ghi stage khi **gọi send/publish** và khi **nhận kết quả callback/future**. Một send bất đồng bộ thường trả điều khiển cho caller trước khi broker xác nhận.

~~~text
producer.send()
   |
   +--> PUBLISH_REQUESTED
   |
   +--> async callback:
          |
          +-- success --> PUBLISH_CONFIRMED + broker metadata
          |
          +-- error --> PUBLISH_FAILED / UNKNOWN + errorCode
~~~

**Timeout là một tình huống mơ hồ**: producer có thể mất ACK sau khi broker nhận record. Đừng khẳng định “message chắc chắn chưa được gửi” chỉ từ timeout. Retry có thể tạo duplicate; nên dùng eventId ổn định và idempotency phù hợp với business contract.

Với producer Kafka, metadata thành công có thể chứa topic, partition và offset. Với RabbitMQ, dùng publisher confirm cùng route/return handling phù hợp, vì một publish được broker xác nhận chưa tự chứng minh routing đến một queue có consumer.

Đối với **transactional outbox**, một quy trình kiểm tra đầy đủ còn cần:

- business commit đã tạo outbox record hay chưa;
- outbox publisher đã poll và gửi request chưa;
- callback broker confirm có đến không;
- outbox marked sent có trùng eventId không;
- tuổi bản ghi outbox chưa xử lý có tăng bất thường không.

**PUBLISH_CONFIRMED không phải PROCESSING_SUCCEEDED**: broker nhận dữ liệu là một bước độc lập với consumer xử lý.

## 7. Consumer: xử lý thành công khác ACK/commit

Consumer thường có ba ranh giới quan trọng:

~~~text
DELIVERY_RECEIVED
       |
       v
PROCESSING_STARTED
       |
  business transaction
       |
       v
PROCESSING_SUCCEEDED
       |
       v
ACKNOWLEDGED / OFFSET_COMMITTED
~~~

Nếu consumer ACK trước khi side effect được cam kết, một crash có thể làm broker coi message hoàn tất dù DB chưa cập nhật. Nếu DB commit thành công nhưng ACK chưa được thực hiện, broker có thể giao lại và tạo **duplicate delivery**.

Điều này dẫn đến ba yêu cầu:

- Xác định **điểm xử lý thành công** theo business transaction, không theo một câu log sớm.
- Thiết kế **inbox/dedup record, idempotency key hoặc atomic transaction** nếu side effects không được phép lặp.
- Log ACK/offset commit đúng lúc API settle thành công; không tự suy ra từ việc handler return.

Đối với consumer dùng auto-commit, cần hiểu rằng commit có thể không gắn chính xác với lúc side effect kết thúc. Khi đang debug, phải đọc chính sách commit cụ thể thay vì giả định “offset đã tăng nên mọi transaction đã thành công”.

**Consumer ACK không chứng minh side effect ngoài broker là exactly-once.** Đó là lý do message flow phải được đối chiếu với DB/inbox/outbox khi có yêu cầu bảo đảm.

## 8. Retry, redelivery, backoff và DLQ

Một logical message có thể có nhiều lần giao:

~~~text
msg-102 attempt=1 PROCESSING_FAILED errorCode=TEMPORARY_DB_ERROR
msg-102 attempt=1 RETRY_SCHEDULED delayMs=500
msg-102 attempt=2 PROCESSING_STARTED
msg-102 attempt=2 PROCESSING_SUCCEEDED
msg-102 attempt=2 ACKNOWLEDGED
~~~

Một số thực hành cần chuẩn hóa:

| Trường | Công dụng |
| --- | --- |
| messageId/eventId | Bền vững qua các attempt của cùng sự kiện logic |
| attemptNo | Phân biệt số lần xử lý |
| errorCode | Nhóm nguyên nhân lỗi, có tập giá trị ổn định |
| retryable | Cho biết lỗi có được lên lịch thử lại không |
| backoffMs / nextAttemptAt | Theo dõi lịch thử lại, tránh retry storm |
| deliveryTag / offset | Ngữ cảnh broker theo từng delivery |
| DLQ destination | Vị trí lưu message cuối kỳ thất bại |
| replayOf / parentMessageId | Phân biệt message replay và nguồn |

**PROCESSING_FAILED không phải terminal failure.** Có thể lần thứ hai thành công. Với các lỗi không hồi phục, cần policy đưa DLQ hoặc trạng thái terminal phù hợp, không retry vô hạn.

**DLQ không phải dấu kết thúc điều tra.** Message có thể cần được kiểm tra, sửa dữ liệu và replay có kiểm soát; phải audit hành động replay và tránh nhân đôi side effect.

Nếu retry delay hoặc requeue khiến broker giao nhanh liên tục, log rate có thể tăng mạnh và che mất nguyên nhân thực. Hãy giám sát retry rate, DLQ age và backlog bên cạnh số lượng dòng ERROR.

## 9. Delivery semantics, duplicate và idempotency

| Semantics | Có thể xảy ra | Yêu cầu khi đọc flow |
| --- | --- | --- |
| **At-most-once** | Event có thể mất, ít hoặc không retry theo cơ chế | Kiểm tra completeness từ nguồn |
| **At-least-once** | Một event có thể đến consumer nhiều lần | Idempotency và attempt/delivery tracking |
| **Exactly-once trong phạm vi cụ thể** | Có thể được broker hỗ trợ với điều kiện riêng | Không suy rộng sang database/API ngoài transaction |
| **Transactional outbox + inbox** | Giúp kết nối business commit với publish/consume | Vẫn cần retry, dedup, reconciliation |

Tình huống điển hình:

~~~text
attempt=1: DATABASE_COMMITTED
attempt=1: ACK_FAILED
attempt=2: DELIVERY_RECEIVED
attempt=2: DEDUPLICATE_SKIPPED
attempt=2: ACKNOWLEDGED
~~~

Hai lần delivery nhưng chỉ **một side effect** là kết quả đúng nếu consumer có dedup hợp lệ. Dashboard cần phân biệt số **attempt failures** và số **logical messages failed** để không đếm trùng một incident.

**Không gọi mọi retry là message mới.** Nếu workflow cố ý phát một message mới thay thế, hãy cho eventId mới và causationId trỏ về event gốc; nếu đó là redelivery cùng event, giữ ID ổn định theo contract.

## 10. Java 17 chạy độc lập: kiểm tra flow và retry

Ví dụ chỉ dùng **Java SE 17**, không có broker thực. Queue trong bộ nhớ mô phỏng hành trình ba messages, gồm thành công ngay, retry một lần rồi thành công, và hết ba attempt đưa vào DLQ. Tất cả event được in theo thứ tự xác định để dễ đối chiếu.

Tạo file **MessageFlowDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;

public class MessageFlowDemo {
    record Message(String messageId, String traceId, String payload) {}
    record Delivery(Message message, int attempt) {}

    private static void emit(List<String> lines, Message message,
                             String stage, int attempt) {
        String line = "FLOW id=" + message.messageId()
                + " trace=" + message.traceId()
                + " stage=" + stage
                + " attempt=" + attempt;
        lines.add(line);
        System.out.println(line);
    }

    public static void main(String[] args) {
        List<Message> messages = List.of(
                new Message("msg-101", "trace-101", "ok"),
                new Message("msg-102", "trace-102", "retry-once"),
                new Message("msg-103", "trace-103", "always-fail"));

        Queue<Delivery> queue = new ArrayDeque<>();
        List<String> lines = new ArrayList<>();

        for (Message message : messages) {
            emit(lines, message, "PUBLISHED", 0);
            queue.add(new Delivery(message, 1));
        }

        int acknowledged = 0;
        int deadLettered = 0;
        int retries = 0;

        while (!queue.isEmpty()) {
            Delivery delivery = queue.remove();
            Message message = delivery.message();
            int attempt = delivery.attempt();
            emit(lines, message, "DELIVERED", attempt);

            boolean failed = "always-fail".equals(message.payload())
                    || ("retry-once".equals(message.payload())
                        && attempt == 1);

            if (failed && attempt < 3) {
                emit(lines, message, "RETRY_SCHEDULED", attempt);
                queue.add(new Delivery(message, attempt + 1));
                retries++;
            } else if (failed) {
                emit(lines, message, "DEAD_LETTERED", attempt);
                deadLettered++;
            } else {
                emit(lines, message, "PROCESSED", attempt);
                emit(lines, message, "ACKNOWLEDGED", attempt);
                acknowledged++;
            }
        }

        System.out.println("SUMMARY published=" + messages.size()
                + " ack=" + acknowledged
                + " dlq=" + deadLettered
                + " retries=" + retries
                + " records=" + lines.size());

        if (acknowledged + deadLettered != messages.size()) {
            throw new IllegalStateException("Terminal states mismatch");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MessageFlowDemo.java
java MessageFlowDemo
~~~

**Stdout chính xác** trong lần chạy thành công:

~~~text
FLOW id=msg-101 trace=trace-101 stage=PUBLISHED attempt=0
FLOW id=msg-102 trace=trace-102 stage=PUBLISHED attempt=0
FLOW id=msg-103 trace=trace-103 stage=PUBLISHED attempt=0
FLOW id=msg-101 trace=trace-101 stage=DELIVERED attempt=1
FLOW id=msg-101 trace=trace-101 stage=PROCESSED attempt=1
FLOW id=msg-101 trace=trace-101 stage=ACKNOWLEDGED attempt=1
FLOW id=msg-102 trace=trace-102 stage=DELIVERED attempt=1
FLOW id=msg-102 trace=trace-102 stage=RETRY_SCHEDULED attempt=1
FLOW id=msg-103 trace=trace-103 stage=DELIVERED attempt=1
FLOW id=msg-103 trace=trace-103 stage=RETRY_SCHEDULED attempt=1
FLOW id=msg-102 trace=trace-102 stage=DELIVERED attempt=2
FLOW id=msg-102 trace=trace-102 stage=PROCESSED attempt=2
FLOW id=msg-102 trace=trace-102 stage=ACKNOWLEDGED attempt=2
FLOW id=msg-103 trace=trace-103 stage=DELIVERED attempt=2
FLOW id=msg-103 trace=trace-103 stage=RETRY_SCHEDULED attempt=2
FLOW id=msg-103 trace=trace-103 stage=DELIVERED attempt=3
FLOW id=msg-103 trace=trace-103 stage=DEAD_LETTERED attempt=3
SUMMARY published=3 ack=2 dlq=1 retries=3 records=17
~~~

Giải thích:

1. **msg-101:** attempt 1 thành công, có ACK terminal.
2. **msg-102:** attempt 1 thất bại, attempt 2 thành công và ACK terminal.
3. **msg-103:** attempt 1 và 2 thất bại, attempt 3 vào DLQ terminal.
4. Có **3 logical messages**, nhưng có **6 delivery attempts** và **17 stage records**.
5. **retries=3**: một lần của msg-102, hai lần của msg-103.
6. **traceId** được truyền qua message record giả lập, không có SDK tracing hoặc span tự sinh.
7. **ACKNOWLEDGED/PUBLISHED** chỉ là mô phỏng trong memory, không kết nối broker, không bảo đảm durability.

Kết quả được xác định vì chương trình dùng một ArrayDeque tuần tự và không có concurrent workers. Không lấy kết quả này để suy ra thứ tự stage của một hệ thống nhiều partition hoặc consumer.

## 11. Gắn message context vào SLF4J MDC

Trong ứng dụng sử dụng SLF4J/Logback, **Mapped Diagnostic Context (MDC)** giúp gắn ID vào nhiều dòng log. Ví dụ pattern text:

~~~text
%d{ISO8601} %-5level message=%X{messageId} trace=%X{traceId} %logger - %msg%n
~~~

Đây chỉ là **pattern minh họa**; cần cấu hình encoder/appender phù hợp trong runtime. Pattern **%X{traceId} không tự tạo tracing**: MDC phải có giá trị do code hoặc instrumentation đưa vào.

Đoạn tích hợp (cần SLF4J dependency và một Runnable handler do app cung cấp):

~~~java
import org.slf4j.MDC;

void consume(String messageId, String traceId, Runnable handler) {
    String oldMessage = MDC.get("messageId");
    String oldTrace = MDC.get("traceId");
    try {
        MDC.put("messageId", messageId);
        MDC.put("traceId", traceId);
        handler.run();
    } finally {
        if (oldMessage == null) MDC.remove("messageId");
        else MDC.put("messageId", oldMessage);

        if (oldTrace == null) MDC.remove("traceId");
        else MDC.put("traceId", oldTrace);
    }
}
~~~

Trong thread pool, nếu quên dọn/restore MDC, log message B có thể nhận nhầm ID của message A. Khi CompletableFuture hoặc executor chuyển task sang thread khác, ThreadLocal/MDC thường không tự lan truyền; cần capture/activate/restore hoặc cơ chế propagation của framework.

**Không đưa raw payload, Authorization header hoặc email vào MDC**. Một encoder xuất toàn MDC sẽ phát các giá trị này trên nhiều dòng log. Message ID từ header bên ngoài phải validate trước khi dùng.

## 12. Tracing xuyên broker và ranh giới bất đồng bộ

Một trace có thể nối các giai đoạn producer, broker boundary, consumer và downstream database/API bằng instrumentation. W3C Trace Context dùng header **traceparent** và có thể có **tracestate**; một số hệ thống dùng OpenTelemetry propagator để inject/extract.

~~~text
Producer span -- inject headers --> Broker delivery
                                         |
                                         v
                               Consumer extracts context
                                         |
                                         v
                                Processing span + logs
~~~

Cần hiểu:

- TraceId chỉ có ý nghĩa nếu có tracing context thực, không phải một chuỗi ngẫu nhiên gắn tên traceId.
- Async consumers, batch và fan-out có thể có **span links** thay vì một chuỗi parent-child duy nhất; cách biểu diễn phụ thuộc instrumentation/semantic conventions.
- Trace sampling có thể làm thiếu spans trong UI dù message đã đi qua đủ stages.
- Trace context không thay thế messageId và broker coordinates.
- Không tự đưa baggage chứa PII/secret vào headers hoặc log; chỉ giữ trường được phép.
- Nếu header thiếu/không hợp lệ, ghi nhận **context_missing** hoặc tạo context mới theo chính sách thay vì giả vờ có liên kết chính xác.

Với consumer handler chia việc qua thread pool, phải propagate trace context và MDC đúng scope; cần tránh trộn trace của nhiều message xử lý song song.

## 13. Kafka: topic, partition, offset và commit

Với Kafka Java client, tọa độ record phục vụ debug là **cluster/topic/partition/offset**, đi kèm eventId/messageId. Offset chỉ có nghĩa trong **một partition**, không phải global sequence.

Theo dõi:

1. Producer gửi request, gắn messageId vào key/header/value theo contract.
2. Callback/future thành công nhận RecordMetadata, log topic, partition, offset.
3. Callback lỗi ghi exceptionType/errorCode; timeout có thể là kết quả ambiguous.
4. Consumer poll nhận topic/partition/offset, ghi delivery và consumerGroup.
5. Handler commit side effect, ghi PROCESSING_SUCCEEDED nếu contract đã thỏa.
6. Commit offset theo policy, log kết quả callback hoặc hành động commit phù hợp.
7. Rebalance, seek, retry topic và DLQ routing phải có event riêng nếu chúng ảnh hưởng flow.

Ví dụ Java tích hợp cần Kafka client cùng các biến producer, record, logger và messageId đã được định nghĩa trong ứng dụng:

~~~java
producer.send(record, (metadata, error) -> {
    if (error == null) {
        logger.info("event=PUBLISH_CONFIRMED messageId={} "
                + "topic={} partition={} offset={}",
                messageId, metadata.topic(),
                metadata.partition(), metadata.offset());
    } else {
        logger.error("event=PUBLISH_FAILED messageId={}",
                messageId, error);
    }
});
~~~

**Đây không phải chương trình độc lập.** Callback success nghĩa là broker xác nhận theo cấu hình producer/cluster, không có nghĩa consumer đã hoàn tất.

Lưu ý:

- **Consumer lag** đo backlog theo group/partition, không đo chính xác processing latency của từng message.
- Kafka phân biệt thứ tự record trong một partition; **không có thứ tự toàn cục mặc định** giữa các partitions.
- Rebalance và commit behavior có thể tạo redelivery; phải xử lý idempotency.
- Một chỗ “nhảy” offset khi quan sát chưa đủ chứng minh mất record: isolation level, transaction/control records, filtering hoặc compaction có thể ảnh hưởng.
- Auto-commit không bảo đảm đã commit business DB transaction.

## 14. RabbitMQ: publisher confirm, routing và ACK/NACK

Với RabbitMQ, cần phân biệt ba nhóm xác nhận:

- **Publisher confirm:** broker báo trạng thái publish theo cơ chế confirm, không phải consumer completion.
- **Routing/returns:** exchange có route đến queue hay không phụ thuộc binding, mandatory flag/return handling và cấu hình.
- **Consumer acknowledgments:** basicAck, basicNack hoặc basicReject thể hiện settlement một delivery theo channel.

Khi log consumer, nên có queue, consumer tag nếu phù hợp, messageId, attempt/delivery context, routingKey, errorCode và terminal outcome. **Delivery tag thuộc phạm vi channel**, không thay messageId.

Một lỗi phổ biến là nack + requeue liên tục, không delay hoặc giới hạn retry, gây **retry storm**. Chính sách có thể dùng retry queues, dead-letter exchange, TTL, delayed delivery (khi có cơ chế phù hợp) và DLQ. **Không giả định gọi nack tự tạo backoff**.

~~~text
DELIVERY_RECEIVED queue=order.commands messageId=msg-102
PROCESSING_FAILED attempt=1 errorCode=DB_UNAVAILABLE
RETRY_SCHEDULED attempt=2 backoffMs=500
DELIVERY_RECEIVED queue=order.retry messageId=msg-102
PROCESSING_SUCCEEDED attempt=2
ACKNOWLEDGED
~~~

Các dòng là **minh họa**. Với runtime thực, phải kiểm tra queue, DLX, routing và confirm result tương ứng. Gửi DLQ cũng là một hành động có thể thất bại hoặc chưa hoàn tất.

## 15. Flow nhiều service, fan-out và saga

Một message có thể tạo nhiều message con:

~~~text
order.created (workflowId=w-55)
    |
    +--> inventory.reserve ---> inventory.reserved
    |
    +--> payment.authorize ---> payment.authorized
    |
    +--> notification.send ---> notification.sent
                                      |
                                      v
                               order.completed
~~~

Để dựng hành trình:

- Một **workflowId/correlationId** cho toàn workflow.
- Một **messageId riêng** cho từng message.
- Một **causationId/parentMessageId** thể hiện message nào kích hoạt message mới.
- Một **stepName/attempt/outcome** cho từng nhánh.
- Một **terminal workflow outcome** khi tất cả nhánh bắt buộc hoàn thành hoặc được compensating action.
- Theo dõi timeout và branch outstanding; không gọi workflow completed chỉ vì một nhánh đã ACK.

Nếu dùng saga, ghi rõ event **compensation requested/succeeded/failed**. Một bước từng thành công rồi được bù trừ là hai sự kiện lịch sử hợp lệ, không sửa bản log cũ để khiến bước thành công biến mất.

Trong fan-out nhiều subscription, cùng messageId có thể có nhiều consumer xử lý hợp lệ. Kiểm tra terminal uniqueness phải theo **messageId + subscription/consumerGroup + workflowStep**, không chỉ theo messageId toàn hệ thống.

## 16. Những invariant để xác nhận flow

Định nghĩa bất biến theo **business contract**, không chỉ số dòng:

| Bất biến | Giá trị | Giới hạn |
| --- | --- | --- |
| Một logical event có origin | Tìm producer/outbox nguồn | Logs có thể bị sampling/drop |
| Publish có kết quả | Confirm, lỗi hoặc UNKNOWN sau deadline | Timeout có thể là trạng thái chưa biết |
| Delivery có attempt | Biết từng lần xử lý | Broker không luôn cấp retry count chuẩn |
| Side effect không lặp trái phép | Dedup theo eventId | Có thể có nhiều subscriber hợp lệ |
| Settlement phù hợp với commit | ACK sau điểm thành công theo policy | Broker/business transaction khác nhau |
| Terminal outcome trong SLA | Completed, canceled hoặc DLQ | In-flight có thể chưa đến deadline |
| Causal links hợp lệ | Fan-out/fan-in có parent/workflow IDs | Đồng hồ không chứng minh quan hệ nhân quả |
| Có thể đối soát missing events | So với outbox/inbox/broker/DB | Chỉ đọc logs không đủ |

**Số ACK không nhất thiết bằng số messages publish** khi có multiple subscriptions hoặc filters. Một flow có thể có trạng thái hợp lệ “pending”; khi tính missing terminal, phải có time window/SLA và hệ thống nguồn.

**Exactly-once end-to-end** không thể chứng minh chỉ từ log; cần atomicity, idempotency và đối soát side effects thật.

## 17. Metrics và traces bổ sung logs như thế nào?

| Công cụ | Dùng khi | Hạn chế |
| --- | --- | --- |
| **Structured logs** | Truy hành trình một messageId và từng errorCode | Có thể bị sampling, drop, hết retention |
| **Distributed traces** | Xem latency/call graph qua nhiều service | Không luôn đầy đủ với async/sampling |
| **Metrics** | Phát hiện tăng lag, retry rate, DLQ size | Không theo từng ID cụ thể |
| **Broker tools** | Kiểm tra offsets, queue depth, consumer connectivity | Không chứng minh side effect DB |
| **Outbox/inbox/business DB** | Đối soát commit, dedup, terminal outcome | Thiếu chi tiết timeline nếu không có logs |

Các metrics hữu ích gồm:

- Producer publish requests/confirms/failures và confirmation latency.
- Consumer delivery/success/failure **theo attempt** và **theo logical message**.
- Processing duration p50/p95/p99; oldest message age và consumer lag.
- Retry scheduled, redelivery, DLQ ingress, DLQ age, replay outcomes.
- Outbox age/backlog; inbox dedup hits; outstanding workflow steps.
- Async logger queue fullness, collector parse errors, log drop count và trace context missing rate.

**Không đưa messageId/traceId/requestId vào metrics labels** vì cardinality tăng cực nhanh. Dùng service, topic/queue, group, outcome và errorCode có miền giá trị hữu hạn; ID động dành cho log/trace.

## 18. Backpressure và độ bền của pipeline logging

Khi tải cao, logging pipeline cũng có thể trở thành bottleneck:

~~~text
Message handler -> logger -> async queue -> formatter -> stdout/file
                                              |
                                              v
                                       collector/backend
~~~

**Backpressure** nghĩa là cơ chế điều tiết producer khi queue hoặc sink không theo kịp. Với async appender, queue đầy có thể khiến thread xử lý bị chặn, log event bị drop, hoặc áp chính sách khác tùy provider/cấu hình. Vì vậy:

- Không giả định bật async logging là miễn phí hoặc mọi ERROR đều được giữ.
- Biết queue capacity, blocking/discard policy và thời điểm flush ở shutdown.
- Theo dõi log drop rate và ingestion delay; nếu chúng tăng, **khoảng trống log không chứng minh khoảng trống message flow**.
- Tránh dump payload/stack trace cho mọi retry attempt nếu không cần thiết; volume lớn có thể che sự kiện quan trọng.
- Ghi audit bắt buộc phải dùng kênh lưu bền vững theo contract, không dựa duy nhất vào diagnostic logger best effort.

**Broker backpressure** là vấn đề khác: queue depth/consumer lag tăng khi consumer xử lý chậm. Một service có thể vừa backlog messages vừa drop logs; lúc đó càng cần outbox/inbox và broker metadata để điều tra.

## 19. Runbook: tìm điểm đứt trong message flow

Bắt đầu từ correlationId hoặc messageId, lần lượt kiểm tra:

1. **Business source / outbox:** có event gốc và commit chưa?
2. **Producer:** PUBLISH_REQUESTED có xuất hiện? Callback có CONFIRMED, FAILED hay UNKNOWN?
3. **Broker:** record/queue entry có tồn tại? Topic/partition/offset, routing/ACL có đúng?
4. **Consumer:** group/subscription nào nhận; có lag hoặc thread pool bị nghẽn?
5. **Processing:** handler bắt đầu và kết thúc chưa; exceptionType/errorCode nào?
6. **Business DB:** side effect commit chưa; inbox dedup có record không?
7. **ACK/offset:** settlement diễn ra sau thành công hay bị timeout/rebalance?
8. **Retry/DLQ:** attempt có tăng; backoff và route hoạt động đúng không?
9. **Downstream:** handler có phát message mới, causationId nối đúng không?
10. **Telemetry:** collector có drop, parser mismatch, sampling hoặc retention hết hạn không?

Bảng phân tích nhanh:

| Quan sát | Giả thuyết | Cách xác minh |
| --- | --- | --- |
| Requested nhưng không Confirmed | Callback lỗi, timeout, crash, log drop | Producer callback, outbox, broker query |
| Confirmed nhưng không Received | Consumer offline, lag, routing/group sai | Broker depth, subscription, ACL |
| Received nhưng không Processing | Deserialize lỗi, handler queue nghẽn | Error handler, executor, thread dump |
| Success nhưng không ACK | Crash giữa commit và ACK, commit failure | Business DB, broker offset, inbox |
| Nhiều failed attempts | Retry/redelivery hoặc log duplicate | attemptNo, eventId, dedup |
| ACK nhưng dữ liệu nghiệp vụ chưa có | Ack sớm, side effect rollback, contract sai | Transaction logs và DB state |
| Retry scheduled nhưng không delivered | Retry queue/scheduler lỗi, TTL/routing | Retry infrastructure, DLQ |
| DLQ event nhưng DLQ trống | Chuyển thất bại, đã replay, expired | DLX config, retention, ops history |
| TraceId đứt giữa services | Headers hoặc context propagation lỗi | Instrumentation, propagator, MDC |
| Không thấy log nhưng broker vẫn tiến | Sampling/retention/collector issue | Metrics, raw sink, broker metadata |

**Không thấy log không chứng minh stage không xảy ra.** Điều quan trọng là chỉ ra nguồn bằng chứng nào có độ tin cậy và trạng thái nào còn UNKNOWN.

## 20. Bảo mật và kiểm soát chi phí log

Không đưa raw payload, header chứa secret hoặc request/response body vào log chung chỉ để tiện debug. Message có thể mang thông tin cá nhân, token, dữ liệu thanh toán hoặc business secrets.

Nên lưu:

- ID được validate (messageId/eventId/traceId/correlationId).
- Event name, service, destination, consumerGroup, attemptNo.
- Status/outcome/errorCode/exceptionType và timing.
- Broker coordinates khi được trả về.
- Payload schema/version và kích thước nếu cần, **không** payload gốc.

Cần tránh:

- Authorization, Cookie, access/refresh token và API keys.
- Dump toàn bộ JSON message khi ERROR.
- Exception message/stack trace chưa kiểm soát có nhúng URL/query/secret.
- MDC chứa raw user object hoặc email.
- Log forging do header/payload có CR/LF phá text log; dùng structured encoder, validation và escaping theo sink.

**Redaction ở collector là lớp bổ sung, không thay việc tối thiểu hóa tại nguồn.** Nếu token đã vào stdout/file, nó có thể tồn tại ở nhiều bản sao trước khi collector che.

Về hiệu năng, log mọi stage ở mức INFO cho throughput cực lớn có thể tăng chi phí. Hãy phân biệt **lifecycle events thiết yếu**, logs dùng debug, metrics aggregate và traces được sampling. Không tự tắt các audit events bắt buộc.

## 21. Kiểm thử end-to-end trong staging

| Tình huống | Kỳ vọng |
| --- | --- |
| Message bình thường | Đủ publish confirm, delivery, processing, settlement |
| Producer timeout/mất ACK | Trạng thái UNKNOWN được xử lý; retry không nhân side effect |
| Broker unavailable | Producer fail/retry hợp lý, outbox backlog được đo |
| Crash trước business commit | Message được phục hồi/redeliver theo contract |
| Crash sau DB commit nhưng trước ACK | Redelivery được dedup, không nhân side effect |
| Handler lỗi tạm thời | Retry/backoff đúng, attemptNo tăng |
| Poison message / sai schema | ErrorCode rõ, không dump secret, DLQ đúng |
| Consumer group rebalance | Ownership và offset không gây mất nghiệp vụ |
| Nhiều partitions | Không giả định global ordering |
| Fan-out nhiều consumers | Terminal đúng theo từng subscription |
| DLQ replay | Có audit, causation link, idempotency |
| Thread pool reuse | MDC không trộn context giữa messages |
| Collector outage | Backpressure/drop được đo, business flow được đối soát |
| Chứa CR/LF hoặc secret | Encoder/redaction không gây leak/forged event |
| Trace context thiếu | Có dấu hiệu context_missing, không ghép sai trace |

Ví dụ Java 17 ở mục 10 là unit-level simulation: 3 messages, 6 deliveries, 3 retries, 2 ACK và 1 DLQ. Nó **không thay thế** integration tests với broker, database và collector thật.

Các thử nghiệm crash, network partition hay poison message phải chạy trên hệ thống **được cấp quyền kiểm thử**; không làm gián đoạn production không có kế hoạch.

## 22. Checklist vận hành

| Kiểm tra | Tiêu chí |
| --- | --- |
| Event contract | Producer/consumer/retry/terminal có stage semantics rõ |
| Identity | Phân biệt messageId, eventId, traceId, correlationId và attemptNo |
| Structured output | Schema nhất quán, timestamp rõ, errorCode hữu hạn |
| Producer | Callback/confirm log đúng mốc broker xác nhận |
| Consumer | Processing result và ACK/offset commit không bị trộn |
| Retry | Backoff, attempt limit, redelivery và DLQ quan sát được |
| Delivery | Duplicate xử lý bằng idempotency/inbox |
| Outbox | Business commit và publish được đối soát, có lag alert |
| Ordering | Contract theo partition/stream và causal links |
| Trace/MDC | Context được truyền qua headers/thread, dọn đúng scope |
| Metrics | Lag, oldest age, DLQ count, retry rate, log drop |
| Privacy | Không lộ credential/payload; chống log forging |
| Backpressure | Hiểu queue overflow ở broker và logging pipeline |
| Verification | Có các invariants và staging failure tests |
| Incident runbook | Tìm từ ID → producer → broker → consumer → terminal |

**Kết luận:** kiểm tra message flow hiệu quả đòi hỏi **định danh ổn định, event theo lifecycle rõ ràng, phân biệt broker confirmation với business processing và settlement, nhìn thấy retry/DLQ, và kiểm chứng với business state**. Java logging là nơi tạo timeline; broker metadata, distributed tracing, metrics và outbox/inbox là các nguồn bổ sung giúp xác nhận đường đi thực tế, tránh kết luận từ một dòng “message received” đơn lẻ.