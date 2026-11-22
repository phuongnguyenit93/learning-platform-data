# DLT publish success và failure

Trong Spring Kafka, một record xử lý thất bại sau khi hết retry có thể được chuyển sang **Dead Letter Topic (DLT)** để điều tra hoặc xử lý lại. Tuy nhiên, việc một error handler quyết định “recover record” không đồng nghĩa record đã được **ghi thành công vào Kafka**. DLT có thể thiếu partition, producer không có quyền ghi, serializer gặp lỗi, broker tạm thời không phản hồi hoặc transaction phục hồi bị abort. Một hệ thống chỉ đo số lần gọi recoverer nhưng không đo kết quả gửi DLT có thể tạo ra cảm giác an toàn giả.

Bài học **DLT publish success và failure** trong chương **Monitoring và metrics** tập trung vào việc xác định chính xác thành công là gì, instrument `DeadLetterPublishingRecoverer` và Kafka producer, theo dõi kết quả publish/transaction/offset, thiết kế cảnh báo, chẩn đoán đường recovery bị lỗi và kiểm thử những failure windows có thể dẫn đến mất hoặc xử lý trùng record.

## 1. DLT ở vị trí nào trong luồng Spring Kafka?

Giả sử dịch vụ đọc `orders.created` và xử lý đơn hàng. Nếu lỗi tạm thời, framework có thể retry. Nếu lỗi tiếp tục sau giới hạn retry, hệ thống dùng recoverer đưa record đến DLT:

~~~text
orders.created
       |
       v
@KafkaListener
       |
       +---- Thành công -> commit offset theo chính sách
       |
       +---- Thất bại -> DefaultErrorHandler
                                  |
                                  v
                             Retry / backoff
                                  |
                     +------------+--------------+
                     |                           |
                 Thành công                  Hết retry
                     |                           |
                     v                           v
              Xử lý thành công       DeadLetterPublishingRecoverer
                                                 |
                                  +--------------+--------------+
                                  |                             |
                             DLT publish OK               DLT publish failed
                                  |                             |
                                  v                             v
                         orders.created.DLT             Recovery chưa hoàn tất
~~~

Trong mô hình transactional listener, `DefaultAfterRollbackProcessor` có thể điều phối recovery sau rollback; trong non-blocking retry, `@RetryableTopic` định tuyến record qua các retry topics và DLT. Điểm chung là **publish DLT là một thao tác Kafka riêng** và có thể gặp sự cố.

DLT là topic vật lý có partitions, replication, retention, ACL, producer serializer và monitoring. Nó không phải bộ nhớ tạm bên trong Spring Boot. Vì vậy, một luồng recovery đáng tin cậy phải kiểm tra kết quả publish thay vì chỉ xác nhận rằng logic retry đã hết lượt.

## 2. Phân biệt năm mốc thành công

Từ “success” dễ dẫn tới sai số liệu khi mỗi nhóm kỹ thuật hiểu khác nhau.

~~~text
[1] recoverer được gọi
        |
        v
[2] KafkaTemplate.send() được chấp nhận
        |
        v
[3] broker ACK gửi record
        |
        v
[4] Kafka transaction COMMIT (nếu có)
        |
        v
[5] DLT consumer nhận và xử lý record
~~~

| Mốc | Tên metric gợi ý | Điều có thể kết luận | Chưa thể kết luận |
|---|---|---|---|
| 1 | `recovery_attempt` | Bắt đầu thử đưa record lỗi sang DLT | Producer đã gửi hay broker đã nhận |
| 2 | `send_submitted` | Producer nhận yêu cầu gửi | Broker đã ack |
| 3 | `send_acked` | Send future hoàn tất thành công theo chính sách producer | Kafka transaction đã commit |
| 4 | `tx_committed` | Transaction chứa record DLT đã commit | DLT consumer đã xử lý nghiệp vụ |
| 5 | `dlt_processed` | Workflow DLT đã đọc/xử lý record | Sự cố nghiệp vụ đã được giải quyết cuối cùng nếu chỉ mới đọc |

Với **non-transactional producer** và `acks=all`, mốc 3 là tín hiệu broker đã xác nhận record theo cấu hình durability. Nhưng retention, vận hành và sự cố hạ tầng vẫn ảnh hưởng vòng đời record sau này.

Với **transactional producer**, một send future có thể hoàn tất thành công **trước transaction commit**. Consumer dùng `isolation.level=read_committed` chỉ nhìn thấy dữ liệu từ transaction đã commit. Vì vậy, metric `send_acked` không được đổi tên thành `tx_committed`.

Việc đọc record DLT cũng khác với **business recovery completed**: một record có thể nằm ở DLT hàng tuần dù publish thành công ngay từ đầu.

## 3. Failure không chỉ là một exception duy nhất

Các lỗi có thể xuất hiện trước, trong hoặc sau khi gửi:

| Giai đoạn | Ví dụ lỗi | Hệ quả |
|---|---|---|
| Destination resolution | Tên DLT sai, partition không tồn tại | Recoverer không có đích ghi hợp lệ |
| Serialization | Value là raw bytes nhưng serializer chỉ hỗ trợ DTO | Record không serialize được |
| Authorization | Thiếu quyền `WRITE` trên DLT | Broker từ chối publish |
| Broker/network | Leader unavailable, mất kết nối, timeout | Send thất bại hoặc outcome chưa rõ |
| Size validation | Payload và headers vượt giới hạn record | Producer/broker từ chối |
| Transaction | Producer fenced, commit timeout, coordinator lỗi | Transaction có thể abort hoặc outcome chưa rõ |
| Offset bookkeeping | DLT write OK nhưng source offset chưa commit | Record có thể redelivery và tạo bản sao DLT |

Một số lỗi có tính **permanent** như thiếu ACL, serializer không tương thích, invalid partition. Retry vô hạn không sửa chúng. Một số khác có thể **transient**, chẳng hạn broker đổi leader hoặc kết nối mạng gián đoạn.

Riêng timeout xảy ra đúng lúc broker xử lý request có thể tạo trạng thái **unknown outcome**. Không nên mặc định “app nhận exception” tương đương “broker chắc chắn chưa lưu record”.

## 4. DeadLetterPublishingRecoverer là điểm quan trọng nhất

`DeadLetterPublishingRecoverer` thường được sử dụng với `DefaultErrorHandler` hoặc cơ chế recovery phù hợp. Nó tạo producer record cho DLT, gắn metadata lỗi và gọi Kafka operations để publish.

Ví dụ định tuyến về một DLT theo topic nguồn:

~~~java
@Bean
DeadLetterPublishingRecoverer dltRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                    new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));
}
~~~

Imports:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
~~~

Ở đây record nguồn ở partition số `p` được đưa tới cùng partition `p` của topic `<source>.DLT`. DLT phải tồn tại và có partition tương ứng. Nếu không, publish có thể thất bại. Tùy thiết kế, có thể chọn destination resolver khác; cần giữ quy tắc ổn định để hạ tầng và monitoring cùng biết.

### 4.1. Cảnh giác với producer send bất đồng bộ

Một lệnh gửi Kafka có thể được nhận vào buffer của producer nhưng chưa có broker acknowledgment. Nếu logic recovery chỉ nhìn “không ném exception ngay”, nó có thể kết luận sớm rằng record đã được bảo toàn trong DLT.

Spring Kafka cung cấp những tùy chọn trên `DeadLetterPublishingRecoverer` giúp xử lý send failure:

- `setFailIfSendResultIsError(true)`: truyền lỗi gửi được phát hiện thành lỗi recovery.
- `setWaitForSendResultTimeout(Duration)`: giới hạn thời gian chờ kết quả send khi cơ chế recoverer kiểm tra kết quả.

Ví dụ:

~~~java
@Bean
DeadLetterPublishingRecoverer confirmedDltRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                    new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    recoverer.setFailIfSendResultIsError(true);
    recoverer.setWaitForSendResultTimeout(Duration.ofSeconds(10));

    return recoverer;
}
~~~

Imports bổ sung: `java.time.Duration`. Mười giây là giá trị minh họa, cần lựa chọn theo client timeouts, tải thực tế và mục tiêu phục hồi.

Hành vi mặc định/chi tiết API cần được kiểm tra với Spring Kafka version đang dùng. Dù send đã ack, nếu nó nằm trong transaction thì **không được suy ra final commit** chỉ từ kết quả của send.

### 4.2. Khi recoverer thất bại, không được âm thầm bỏ qua

Giả sử error handler đã hết retry cho record offset 75. Recoverer cố publish DLT nhưng gặp authorization failure. Nếu application nuốt lỗi và coi như recovery xong, source offset có thể bị commit theo một cấu hình không phù hợp, khiến record lỗi bị bỏ qua khỏi đường chính **mà DLT không có bản sao**.

Vì vậy, khi bảo đảm “không mất poison record” là yêu cầu, publish failure phải được truyền về cơ chế error handling/recovery để xử lý tiếp: retry ở thời điểm phù hợp, dừng container, cảnh báo và giữ nguyên khả năng đọc lại từ committed offset.

Không nên tùy tiện đổi `ackAfterHandle`, `commitRecovered` hoặc ack mode mà không hiểu mối quan hệ giữa recovery success và offset commit.

## 5. Instrument DLT bằng Micrometer

Một pattern hữu ích là đặt `ConsumerRecordRecoverer` wrapper quanh `DeadLetterPublishingRecoverer` để ghi lại nỗ lực và kết quả thực tế.

Ví dụ cho đường **non-transactional**:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

import java.time.Duration;

@Bean
DefaultErrorHandler monitoredErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate,
        MeterRegistry registry) {

    var publisher = new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, error) ->
                    new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    publisher.setFailIfSendResultIsError(true);
    publisher.setWaitForSendResultTimeout(Duration.ofSeconds(10));

    ConsumerRecordRecoverer observedRecoverer = (record, error) -> {
        registry.counter(
                "app.kafka.dlt.publish.attempts",
                "source_topic", record.topic()).increment();

        try {
            publisher.accept(record, error);

            registry.counter(
                    "app.kafka.dlt.publish.results",
                    "outcome", "send_acked",
                    "source_topic", record.topic()).increment();

        } catch (RuntimeException publishError) {
            registry.counter(
                    "app.kafka.dlt.publish.results",
                    "outcome", "failed_or_unknown",
                    "source_topic", record.topic()).increment();

            throw publishError;
        }
    };

    return new DefaultErrorHandler(
            observedRecoverer,
            new FixedBackOff(1_000L, 2L));
}
~~~

Ngữ nghĩa của metric này:

1. `attempts` tăng khi recoverer được gọi, **không** phải mỗi lần listener retry.
2. `send_acked` tăng sau khi recoverer trả về **với chế độ chờ send result** trong ví dụ.
3. `failed_or_unknown` tăng khi recoverer ném exception; có những tình huống timeout chưa rõ kết quả thực tế.
4. Exception **được ném lại**, không nuốt.
5. Vì ví dụ giả định DLT publish non-transactional, `send_acked` phản ánh acknowledgment, không phải commit Kafka transaction.

Các tên `app.kafka.*` là application-defined; framework không tự tạo đúng những counter này. Nếu producer transaction được dùng, cần đo transaction commit ở nơi thực sự biết kết quả commit, không ở wrapper này.

### 5.1. Không tăng success trước khi gửi

Sai:

~~~java
registry.counter("dlt.publish.success").increment();
publisher.accept(record, error);
~~~

Nếu publish lỗi, metric đã sai. Ngay cả khi gọi counter sau `publisher.accept(...)`, cần hiểu method có đợi send future hay chỉ enqueue gửi.

### 5.2. Đừng gộp failed với definitely lost

Một timeout send có thể xảy ra sau khi broker đã nhận record. Khi chỉ quan sát được exception, outcome có thể là `unknown`. Một hệ thống có thông tin đủ chi tiết có thể phân loại:

| Outcome | Ý nghĩa |
|---|---|
| `acked` | Producer đã được broker xác nhận gửi |
| `failed_definite` | Lỗi có thể kết luận publish không thành công, như serialization trước send |
| `unknown` | Kết quả broker/commit chưa xác nhận rõ |
| `tx_committed` | Transaction đã được xác nhận committed |

Không suy đoán trạng thái đã commit chỉ từ exception class chung hoặc thông điệp timeout. Một số tình huống cần đối soát bằng event ID và record thực tế ở DLT.

## 6. Theo dõi KafkaTemplate future

Nếu ứng dụng có một publisher DLT riêng, `KafkaTemplate.send()` cho phép nhận kết quả ở tầng producer send:

~~~java
@Component
public class StringDltPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;
    private final MeterRegistry metrics;

    public StringDltPublisher(
            KafkaTemplate<String, String> kafkaTemplate,
            MeterRegistry metrics) {
        this.kafkaTemplate = kafkaTemplate;
        this.metrics = metrics;
    }

    public void send(String eventId, String payload) {
        metrics.counter("app.kafka.dlt.send.requests").increment();

        kafkaTemplate.send("orders.created.DLT", eventId, payload)
                .whenComplete((result, exception) -> {
                    if (exception == null) {
                        metrics.counter(
                                "app.kafka.dlt.send.responses",
                                "result", "acked").increment();
                    } else {
                        metrics.counter(
                                "app.kafka.dlt.send.responses",
                                "result", "failed").increment();
                    }
                });
    }
}
~~~

Ví dụ giả định DLT dùng `StringSerializer` và publisher non-transactional. Callback `whenComplete` cho biết send future hoàn tất, nhưng **không tự giữ source offset lại khi publish lỗi**. Nếu dùng đoạn code này như một recoverer, cần tích hợp failure vào error handler hoặc sử dụng phương thức bảo đảm offset không được ack/commit trước khi publish hoàn tất.

Callback producer nên nhẹ: ghi metric, structured log rồi kết thúc. Không gọi database/HTTP blocking trong callback.

Spring Kafka cũng có `ProducerListener` để nhận callback producer success/error theo API tương ứng; có thể dùng nó cho số liệu tổng quan. Tuy nhiên, nếu KafkaTemplate gửi nhiều topic, phải lọc đúng DLT destination trước khi tính DLT success/failure.

## 7. DLT trong Kafka transaction

Với listener dùng Kafka transaction, recovery có thể có thêm một transaction mới sau khi transaction xử lý chính đã rollback.

~~~text
Transaction listener:
  xử lý record -> exception -> ROLLBACK
                         |
                         v
AfterRollbackProcessor / recoverer
                         |
                         v
Recovery transaction (nếu cấu hình hỗ trợ)
   +---- publish DLT record
   +---- send recovered source offset
                         |
                         v
                COMMIT hoặc ABORT
~~~

Trong các cấu hình Spring Kafka phù hợp, `DefaultAfterRollbackProcessor` có thể dùng `commitRecovered` và KafkaTemplate để gửi offset recovered vào **transaction recovery mới** cùng DLT output.

Sự khác nhau rất quan trọng:

- `KafkaTemplate.send()` thành công: producer đã nhận broker ack cho record.
- `Recovery transaction commit` thành công: DLT output và input offset trong transaction cùng được commit.
- `Commit thất bại hoặc abort`: không được coi recovery hoàn thành; có thể cần redelivery/reconciliation.

Nếu metric chỉ tăng khi `DeadLetterPublishingRecoverer.accept()` trả về, **không gọi metric đó là transactional publish committed** khi final commit nằm ở một bước phía sau. Muốn đo commit success, cần instrument transaction completion hoặc xác nhận bằng output `read_committed` và committed offsets trong các bài kiểm thử.

### 7.1. Producer fencing

`ProducerFencedException` có thể xuất hiện khi một transactional producer session mất quyền sử dụng `transactional.id` vì phiên mới đã chiếm thế hệ hợp lệ. Đây là lỗi nghiêm trọng ở cấp producer/transaction, không phải một HTTP timeout tạm thời có thể retry trên cùng session.

Khi có fencing, phải điều tra instance ownership và transactional ID prefix, không coi DLT send stage ack là transaction commit. Container/transaction manager cần khôi phục bằng session hợp lệ.

## 8. Hai failure windows liên quan source offset

### 8.1. DLT không ghi được nhưng source offset đã commit

~~~text
Source record offset 101 lỗi
       |
       v
DLT publish thất bại
       |
       v
Lỗi bị nuốt / recovery được coi là success
       |
       v
Source offset 102 được commit
       |
       v
Record 101 có nguy cơ biến mất khỏi đường xử lý
~~~

Đây là tình huống không thể chấp nhận nếu yêu cầu là “mọi record lỗi phải có dấu vết DLT hoặc hệ thống lưu trữ khác”.

Cần kiểm tra `DefaultErrorHandler`, recoverer, ack mode, `ackAfterHandle`, `commitRecovered` và ranh giới transaction tương ứng. Một exception DLT publish bị truyền ra thường cho phép cơ chế error handling giữ record ở trạng thái chưa recover, nhưng hành vi cụ thể phải kiểm thử ở đúng phiên bản/cấu hình.

### 8.2. DLT đã ghi nhưng source offset chưa commit

~~~text
Source record 101 -> DLT publish thành công
                            |
                            v
                       Process crash
                            |
                            v
                  Source offset chưa commit
                            |
                            v
                  Record 101 được giao lại
                            |
                            v
                  DLT có thể nhận bản sao nữa
~~~

Đây là tình huống **at-least-once recovery**: record được bảo toàn nhưng có thể duplicate. DLT consumer/replay tooling nên dùng event ID hoặc khóa tương quan ổn định để không tạo business side effect lặp.

Một transaction Kafka bao gồm DLT output và input offset có thể giảm khoảng trống này trong phạm vi Kafka. Với publisher non-transactional, cần chấp nhận khả năng redelivery và thiết kế chống trùng.

### 8.3. Khóa đối soát phù hợp

Khi điều tra duplicate hoặc missing record, dùng nhiều trường:

~~~text
business_event_id
source_topic
source_partition
source_offset
pipeline_owner
dlt_topic
~~~

`source_topic + partition + offset` định danh một bản ghi trong topic nguồn, còn `business_event_id` giúp theo dõi cùng event khi nó được publish sang topic khác và có offset mới. Nếu nhiều consumer groups khác nhau cùng xử lý một main topic, thêm `pipeline_owner` để phân biệt recovery hợp lệ của từng service.

## 9. Blocking retry và non-blocking retry khác nhau ở đâu?

| Mô hình | Đường đến DLT | Metric cần tách |
|---|---|---|
| `DefaultErrorHandler` blocking retry | Thử xử lý lại trước khi recoverer đưa record sang DLT | Listener attempts, recoverer attempts, DLT send outcome |
| Transactional + after-rollback | Rollback, retry rồi recovery vào DLT | Transaction rollback, send ack, recovery transaction commit |
| `@RetryableTopic` non-blocking retry | Main -> retry topics -> DLT | Publish failure ở retry topics, DLT publish outcome, DLT handler status |

Đừng nhầm hai loại failure:

1. **DLT publish failure**: không thể đưa record vào DLT theo bảo đảm đã chọn.
2. **DLT handler/consumer failure**: record đã ở DLT nhưng logic phân loại, sửa lỗi hoặc replay thất bại.

Đây là hai pipeline riêng với counters và runbooks khác nhau. Với non-blocking retry, còn phải quan sát việc publish tới **retry topic** trước DLT; nếu chặng đó thất bại, record chưa chắc đã đến bước DLT.

## 10. Metadata để liên kết DLT record và lỗi gốc

`DeadLetterPublishingRecoverer` có thể bổ sung các header Spring Kafka như:

| Header | Ý nghĩa |
|---|---|
| `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Topic nguồn được ghi nhận |
| `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition nguồn |
| `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset nguồn |
| `KafkaHeaders.DLT_EXCEPTION_FQCN` | Tên đầy đủ lớp exception |
| `KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN` | Lớp nguyên nhân nếu có |
| `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Thông điệp lỗi |
| `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace theo cấu hình/hành vi framework |

Không phải record nào cũng có tất cả headers. Header số có thể được mã hóa dưới dạng bytes nhị phân; không tự giải mã tất cả như UTF-8.

Kafka headers cho phép **nhiều giá trị cùng tên**. Khi record được chuyển qua nhiều retry hoặc recovery hops, có thể xuất hiện metadata tích lũy. Dùng `headers(name)` hoặc `lastHeader(name)` theo mục đích, không mặc định một map chỉ có một giá trị đã phản ánh đầy đủ lịch sử.

Tốt nhất, event có một `eventId` ổn định từ producer gốc. Khi metrics chỉ chứa nhãn ít cardinality, logs/traces có thể chứa event ID và source topic-partition-offset để đối soát chi tiết.

## 11. Thiết kế ứng dụng metrics

Một hệ thống có thể định nghĩa:

| Metric đề xuất | Loại | Định nghĩa |
|---|---|---|
| `app.kafka.dlt.publish.attempts` | Counter | Recoverer được gọi để thử publish |
| `app.kafka.dlt.publish.results{outcome="acked"}` | Counter | Send được broker xác nhận |
| `app.kafka.dlt.publish.results{outcome="failed"}` | Counter | Publish failure quan sát được |
| `app.kafka.dlt.publish.results{outcome="unknown"}` | Counter | Timeout/uncertain outcome |
| `app.kafka.dlt.publish.latency` | Timer | Thời gian từ attempt đến send outcome |
| `app.kafka.dlt.recovery.tx.commits` | Counter | Recovery transaction commit thành công nếu instrument |
| `app.kafka.dlt.recovery.tx.failures` | Counter | Recovery transaction commit/abort lỗi |
| `app.kafka.dlt.records.consumed` | Counter | DLT consumer nhận/xử lý record theo định nghĩa |
| `app.kafka.dlt.records.resolved` | Counter | Record DLT được xử lý cuối cùng/replay xong |
| `app.kafka.dlt.unresolved.age` | Gauge/Timer | Tuổi của backlog chưa giải quyết |

Các metrics này là **quy ước tự tạo**. Không nên tuyên bố framework tự cung cấp đúng các tên như trên.

Nhãn nên được giới hạn ở những nhóm có số lượng hữu hạn:

- `service` hoặc `pipeline`;
- `source_topic` và `dlt_topic`;
- `outcome`;
- `error_category` như `authorization`, `serialization`, `timeout`, `too_large`;
- `environment`.

Tránh dùng event ID, record key, offset, stack trace, full exception message hoặc transactional ID có suffix biến động làm Prometheus labels. Những giá trị đó có cardinality cao hoặc có thể chứa dữ liệu nhạy cảm; phù hợp hơn trong structured logs và traces.

### 11.1. Lựa chọn success rate

Một tỷ lệ ý tưởng:

~~~text
observed_failure_rate =
  DLT publish attempts được phân loại là failed
  /
  tổng DLT publish attempts có outcome đã xác định
~~~

Khi không có DLT attempts hoặc volume rất thấp, tỷ lệ phần trăm không đủ ý nghĩa. Một failure trên một attempt khác rất xa hàng nghìn failures mỗi phút.

Dùng cả absolute failure count, failure rate, duration, backlog và source consumer lag. Nếu không có DLT attempts trong nhiều giờ, có thể hệ thống không gặp lỗi nghiệp vụ — đó **không tự động là exporter lỗi**.

## 12. Kafka producer và broker metrics bổ sung

Kafka client/Spring Kafka/Micrometer có thể cung cấp producer metrics như:

- Record send/error/retry rates.
- Request latency, buffer pool wait, record size.
- Transaction commit/abort behavior tùy instrumentation.
- Consumer lag, poll duration và rebalance activity.
- Broker topic records-in/bytes-in.
- KafkaTemplate observation/tracing nếu đã bật.

Không nhầm **producer record error rate tổng thể** với DLT publish error rate: một KafkaTemplate có thể gửi cả main topic, retry topic và DLT. Cần instrument theo destination hoặc bổ sung context đủ rõ.

Broker metrics có thể chứng minh DLT topic nhận traffic, nhưng không cho biết exception gốc, source offset đã commit hay workflow replay đã giải quyết thành công.

## 13. Dashboard DLT reliability

Một dashboard hữu ích nên có nhiều góc nhìn:

~~~text
DLT Reliability Dashboard
  |
  +-- Publish
  |      attempts/sec, acked/sec, failed/sec, unknown/sec
  |      send latency p50 / p95 / p99
  |
  +-- Producer / infrastructure
  |      request errors, retries, broker availability
  |      Kafka transaction commit / abort / fencing
  |
  +-- Source consumer
  |      consumer lag by partition, error rate, retries
  |
  +-- DLT inventory
         DLT records in, oldest unresolved age
         DLT consumer lag, replay success/failure
~~~

Nếu DLT acknowledgments tăng mạnh và publish failures bằng 0, **đường DLT có thể đang hoạt động tốt nhưng ứng dụng nghiệp vụ đang lỗi hàng loạt**. Cần alert cho lượng record rơi DLT, không chỉ publish failure.

Nếu DLT attempts tăng, DLT failures tăng, topic records-in không tăng và source lag tăng, đường recovery có thể đã hỏng. Đây là tình huống ưu tiên cao vì consumer có thể không tiến hoặc record có nguy cơ bị bỏ qua nếu error handler cấu hình sai.

## 14. Alert theo đúng nguyên nhân

| Dấu hiệu | Phản ứng gợi ý |
|---|---|
| Một send failure ngắn rồi phục hồi | Ghi nhận warning, theo dõi retry |
| Send failures liên tục và source lag tăng | Alert khẩn cấp về DLT publish path |
| Authorization/serializer failure lặp lại | Incident có hành động cấu hình cụ thể |
| Recovery transaction commit failure | Điều tra transaction và offset commit |
| DLT records-in tăng đột biến, publish success vẫn cao | Điều tra lỗi listener hoặc dữ liệu đầu vào |
| DLT unresolved age vượt SLO | Alert triage/replay backlog |
| Unknown outcomes tăng | Reconciliation và chống trùng theo event ID |

Ví dụ PromQL khi exporter chuẩn hóa tên metrics đúng như ứng dụng cấu hình:

~~~promql
sum by (service, pipeline) (
  rate(app_kafka_dlt_publish_results_total{outcome="failed"}[5m])
)
~~~

Đây là ví dụ minh họa. Tên metric xuất ra và labels cần được kiểm chứng ở monitoring backend; không nên copy biểu thức mà không biết Micrometer đang export metric dưới tên nào.

Cảnh báo tốt kết hợp failure count, tỷ lệ failure, thời gian kéo dài và ảnh hưởng thực tế lên lag. Đừng tạo một incident cho từng DLT record lỗi nghiệp vụ, và cũng đừng bỏ qua đường DLT publish hoàn toàn ngừng hoạt động chỉ vì “DLT traffic đang thấp”.

## 15. Những nguyên nhân publish failure hay gặp

### 15.1. DLT topic không tồn tại

Khi cluster tắt auto-create và topic được tạo bằng Terraform/GitOps, dễ quên tạo DLT. Hãy kiểm tra đúng suffix, partition, replication và ACL. Nếu error handler cần DLT nhưng DLT không tồn tại, sự cố chỉ bộc lộ khi gặp poison record.

### 15.2. DLT thiếu partition

Destination resolver giữ partition gốc nhưng main có tám partitions, DLT chỉ có bốn. Một record nguồn ở partition 6 không thể được publish vào partition 6 của DLT. Phải quy hoạch partition count hoặc dùng resolver khác có chủ đích.

### 15.3. Serializer không hỗ trợ dữ liệu lỗi

Record deserialize thất bại có thể cần được recover dưới dạng raw `byte[]`. Nếu KafkaTemplate của DLT chỉ cấu hình serializer cho DTO Java, publish sẽ lỗi. Kiểm tra serializer cho cả normal records và deserialization failures; có thể cân nhắc `DelegatingByTypeSerializer` hoặc template phù hợp.

### 15.4. Record quá lớn

Exception stack traces và metadata headers có thể tăng kích thước record qua nhiều lần retry/recovery. Nếu payload + headers vượt giới hạn producer/broker/topic, publish sẽ bị từ chối. Cần kiểm soát header history, payload size và message limits, không chỉ nâng giới hạn một cách mù quáng.

### 15.5. Broker/authorization và Kafka transaction

Thiếu quyền WRITE, broker leader unavailable, timeout hoặc producer fencing đều có thể ngăn DLT publish. Nếu dùng Kafka transactions, phải theo dõi cả transaction coordinator và commit outcome — broker ack một send chưa bảo đảm transaction committed.

## 16. Runbook khi DLT publish thất bại

Khi phát hiện lỗi recovery, quy trình điều tra nên là:

1. Xác định service, pipeline, source topic, partition, offset, DLT topic và instance.
2. Lấy exception ở **DLT publish stage**, không chỉ exception của business listener.
3. Kiểm tra DLT topic tồn tại, đúng tên, đủ partitions và broker leader/replication khỏe.
4. Kiểm tra producer ACL, credentials, serializer và schema registry nếu dùng.
5. Đo kích thước value/key/headers; kiểm tra raw bytes của record deserialize lỗi.
6. Kiểm tra producer send future, timeout và retry metrics.
7. Nếu transactional, xác định transaction commit/abort hoặc producer fencing.
8. Xác nhận **source committed offset**: record còn khả năng redelivery không?
9. Với timeout, phân biệt `unknown outcome`: DLT có thể đã nhận record.
10. Sửa nguyên nhân trước khi retry/replay có kiểm soát.
11. Theo dõi DLT publish success, source lag và DLT consumer state sau khôi phục.
12. Đối soát duplicate/missing record dựa vào event ID và source metadata.

Không tự commit offset chỉ để làm giảm lag khi publish DLT còn lỗi. Điều đó có thể khiến poison record biến mất khỏi cả source stream lẫn DLT.

Khi nhiều partitions cùng bị kẹt bởi một ACL hoặc serializer lỗi, scale thêm consumer không sửa được nguyên nhân chung. Nên ưu tiên phục hồi recovery path và bảo vệ dữ liệu nguồn.

## 17. Structured logs cho một lần DLT publish

Một structured log minh họa:

~~~text
event_type=dlt_publish_result
service=orders-worker
pipeline=order-validation
source_topic=orders.created
source_partition=2
source_offset=481
dlt_topic=orders.created.DLT
event_id=evt-7aa2
outcome=failed_or_unknown
error_category=authorization
duration_ms=123
instance_id=orders-worker-4
~~~

Những trường này do ứng dụng tự bổ sung, không phải mọi trường đều là properties built-in của Spring Kafka event. Dùng event ID và source offset để truy nguyên, nhưng **không dùng chúng làm metric labels**.

Stack trace có thể chứa URI nội bộ, payload hoặc dữ liệu cá nhân. Cần có chính sách redaction/log sampling và quyền truy cập phù hợp. Nếu một lỗi bị retry rất nhiều lần, tránh log toàn bộ stack trace lặp đi lặp lại, thay vào đó log count, correlation ID và last failure summary.

## 18. Kiểm thử DLT publish success

Unit test gọi trực tiếp `recoverer.accept(...)` với producer mock chỉ chứng minh code của recoverer được gọi. Để kiểm chứng broker acknowledgment và DLT topic contents, nên dùng Embedded Kafka hoặc Kafka Testcontainers.

Kịch bản cơ bản:

1. Tạo main topic và DLT với cùng partition policy.
2. Cấu hình listener, error handler và recoverer.
3. Gửi một record khiến listener luôn ném exception.
4. Đợi hết retry và recoverer publish.
5. Đọc DLT bằng consumer test.
6. Xác nhận key/value, event ID, source headers và exception info.
7. Kiểm tra source group committed offset sau recovery.
8. Kiểm tra application counter attempts và send success theo ngữ nghĩa đã định.
9. Nếu dùng Kafka transaction, đọc DLT bằng `read_committed` để không nhầm output bị abort với committed output.

Ví dụ cấu hình consumer test:

~~~java
Map<String, Object> config = new HashMap<>();
config.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
config.put(ConsumerConfig.GROUP_ID_CONFIG, "dlt-observer-it");
config.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
config.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
config.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
config.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        ByteArrayDeserializer.class);
~~~

Đoạn này giả định DLT value được ghi dưới dạng bytes. Nếu thực tế dùng JSON/Avro serializer, phải chọn deserializer tương ứng. Test consumer cần có group ID riêng và topic được làm sạch/cách ly khỏi test khác.

## 19. Kiểm thử DLT publish failure

Một failure suite tốt cần có:

| Tình huống | Cách tạo lỗi | Assertion |
|---|---|---|
| Missing DLT | Tắt auto-create, không tạo topic | Recoverer báo failure, không coi recovery thành công |
| Invalid partition | Main nhiều partitions hơn DLT; giữ partition number | Publish không được ghi sai destination |
| ACL denied | Producer thiếu quyền WRITE | Failure metric tăng, offset nguồn tuân thủ chính sách |
| Serializer mismatch | Raw bytes với serializer chỉ hỗ trợ DTO | Lỗi được phát hiện, không mất record |
| Oversized record | Tạo payload/headers vượt giới hạn | Error rõ ràng và có alert |
| Broker outage | Ngắt mạng/dừng broker có kiểm soát | Retry/failure/unknown outcome theo đường thực tế |
| Transaction abort | Làm recovery transaction rollback | `read_committed` không thấy record bị abort |
| Producer fenced | Thay thế transactional producer identity | Session cũ không thể commit |
| Crash after ack | Kill trước commit source offset | Record có thể redelivery; DLT consumer chống trùng |
| Unknown outcome | Mất response tại điểm ack/commit | Reconciliation không tạo side effect trùng |

Đừng kết thúc test tại:

~~~java
assertThrows(Exception.class,
        () -> recoverer.accept(record, exception));
~~~

Cần xác nhận **dữ liệu thật trên DLT**, **input offset**, **error metric**, **khả năng khôi phục** và duplicate semantics. Một exception không đủ chứng minh record chưa có trên broker; một send ack cũng không đủ chứng minh source offset đã commit.

### 19.1. Test send vs transaction commit

Phân biệt các mốc:

~~~text
T0: send submitted
T1: send future completed
T2: Kafka transaction commit completed
~~~

Nếu ở T1 ack thành công nhưng T2 abort, một consumer `read_uncommitted` có thể quan sát record nhưng `read_committed` không coi đó là committed data. Vì vậy, integration test transaction phải quan sát đúng isolation level.

### 19.2. Không dùng sleep cố định làm assertion

Kafka publish, rebalance, leader election và retry bất đồng bộ. Dùng latch, consumer poll có timeout hữu hạn hoặc Awaitility chờ điều kiện; tránh giả định mọi send hoàn tất trong một số millisecond cố định trên CI.

Giữ test topic/consumer group/transactional ID riêng, cleanup producer/containers sau test và không dùng fault injection nguy hiểm trên shared production cluster.

## 20. DLT publish success chưa phải business resolution

Một record đã ghi thành công vào DLT vẫn có thể cần triage, sửa lỗi hoặc replay.

~~~text
orders.created.DLT
       |
       v
DLT triage / handler / recovery worker
       |
       +---- phân tích lỗi
       +---- sửa dữ liệu hoặc dịch vụ phụ thuộc
       +---- replay có kiểm soát
       +---- xác nhận nghiệp vụ xử lý thành công
~~~

Cần tách bạch:

- **Publication reliability**: record lỗi được đưa vào DLT đáng tin cậy chưa?
- **DLT backlog**: có bao nhiêu record chưa được xử lý?
- **Triage latency**: mất bao lâu để đánh giá?
- **Replay success**: record có được xử lý lại thành công?
- **Duplicate suppression**: replay và redelivery có tạo effect trùng?
- **Final resolution**: nghiệp vụ đã được sửa, đóng sự cố và ghi audit?

Một dịch vụ có `DLT publish success = 100%` nhưng hàng triệu record unresolved không thể được coi là khỏe mạnh theo góc nhìn nghiệp vụ.

## 21. Những sai lầm thường gặp

- **Đếm recoverer được gọi là publish success** dù future chưa có broker ack.
- **Đếm send ack là Kafka transaction committed** dù transaction có thể abort.
- **Coi mọi timeout là chắc chắn không ghi** dù có unknown outcome.
- **Nuốt publish exception** rồi để source offset commit.
- **Chỉ giám sát records-in của DLT** nên không thấy những attempts thất bại trước khi tới broker.
- **Gộp mọi producer error thành DLT publish failure** trong khi template gửi nhiều loại topic.
- **Không kiểm tra partition/ACL/serializer của DLT** trước rollout.
- **Không hỗ trợ raw bytes của lỗi deserialization** khi gửi DLT.
- **Không đối chiếu source offset** nên không biết đã mất record hay chỉ tạo duplicate.
- **Chỉ tăng error counter, không đo DLT unresolved backlog**.
- **Dùng offset và stack trace làm metric labels** gây cardinality và rò rỉ dữ liệu.
- **Retry vô hạn lỗi permanent** như ACL denied hoặc invalid partition.
- **Coi publish success đồng nghĩa DLT handler success**.
- **Không test broker outage, timeout, crash sau ack và transaction rollback**.
- **Scale consumer để chữa lỗi ACL của DLT** thay vì sửa nguyên nhân.
- **Không có runbook DLT publisher failure** nên sự cố recovery kéo dài mà không ai sở hữu.

## 22. Checklist triển khai production

Trước khi đánh dấu đường recovery là đủ tin cậy, hãy trả lời:

1. “DLT publish success” đang có nghĩa send submitted, broker ack hay transaction committed?
2. `DeadLetterPublishingRecoverer` có phát hiện send failure và truyền lỗi ngược về handler không?
3. Timeout/unknown outcome có được ghi riêng để đối soát không?
4. Source offset chỉ được commit sau recovery thành công theo đúng hợp đồng hay chưa?
5. DLT topic đã tồn tại, có partition count, replication và ACL phù hợp chưa?
6. Producer serializer có xử lý normal value và raw bytes khi deserialization lỗi không?
7. Transaction recovery có thể gặp producer fencing hoặc commit failure không?
8. Metric có tách attempts, acked, failed, unknown và transaction committed không?
9. Labels có giới hạn cardinality và không chứa payload nhạy cảm không?
10. Dashboard có liên kết DLT publish failures với source lag và DLT backlog không?
11. Alert có phân biệt lỗi publish path với tăng DLT vì lỗi nghiệp vụ không?
12. Có event ID hoặc source topic-partition-offset để reconciliation không?
13. DLT consumer/replay có idempotency không?
14. Đã kiểm thử missing topic, invalid partition, ACL, serializer, broker outage và crash chưa?
15. Có người hoặc hệ thống chịu trách nhiệm triage và giải quyết DLT tồn đọng không?

**DLT publish success và failure** là những tín hiệu nền tảng của độ tin cậy trong hệ thống Spring Kafka. Muốn giữ record lỗi an toàn, cần đo kết quả ở **đúng ranh giới producer acknowledgment hoặc transaction commit**, không nuốt recovery failure, bảo vệ source offset và đối soát được unknown outcome hoặc duplicate. Kết hợp metrics, structured logs, broker/client telemetry, dashboard, alert và integration tests sẽ giúp đội vận hành phát hiện ngay khi **đường xử lý lỗi cũng đang bị lỗi**, thay vì chỉ nhận ra sau khi dữ liệu đã thất lạc hoặc consumer bị kẹt.
