# Commit latency

Trong một Spring Kafka consumer, việc listener đã xử lý xong record và việc **Kafka xác nhận offset commit** là hai cột mốc khác nhau. Consumer có thể hoàn tất thao tác database trong vài mili giây nhưng mất hàng trăm mili giây để commit offset vì độ trễ mạng, group coordinator đang bận hoặc quá nhiều commit request. Khi đó throughput, consumer lag và nguy cơ redelivery đều bị ảnh hưởng.

**Commit latency** trong ngữ cảnh giám sát Kafka thường chỉ **thời gian một yêu cầu commit consumer offset cần để hoàn tất**. Đây là metric quan trọng của chương **Monitoring và metrics**, nhưng phải diễn giải đúng: không phải thời gian xử lý record, không phải thời gian publish record, và cũng không tự đo toàn bộ thời gian một Kafka transaction.

Bài học này hướng dẫn cách hiểu commit latency, phân biệt offset commit với transaction commit, theo dõi metric của Kafka client, cấu hình commit trong Spring Kafka, thiết kế dashboard/alert và điều tra sự cố mà không làm giảm bảo đảm giao nhận.

## 1. Tại sao cần đo commit latency?

Hãy xét dịch vụ order-worker đang đọc topic `orders.created`:

    Topic orders.created
             |
             v
       KafkaConsumer.poll()
             |
             v
        @KafkaListener
             |
             v
      Xử lý nghiệp vụ: 12 ms
             |
             v
      Offset commit: 180 ms
             |
             v
        Poll lần tiếp theo

Nếu container thực hiện commit đồng bộ sau mỗi record, độ trễ commit cao có thể khiến tốc độ xử lý giảm mạnh. Trong ví dụ đơn giản, một consumer tuần tự có tổng thời gian gần 192 ms/record, tương đương khoảng 5,2 record/giây; trong khi business code riêng lẻ có thể xử lý hơn 80 record/giây.

Ngược lại, nếu ứng dụng commit mỗi batch 100 record, chi phí commit không còn nằm trên đường xử lý của từng record. Tuy nhiên, khoảng cách giữa các lần commit lớn hơn có thể khiến nhiều record phải được xử lý lại nếu consumer crash.

Commit latency ảnh hưởng tới:

- **Throughput:** commit đồng bộ giữ consumer thread chờ kết quả.
- **Độ trễ hoàn tất công việc:** business side effect đã xong nhưng offset chưa được ghi nhận bền vững.
- **Consumer lag và freshness:** việc commit chậm có thể làm tốc độ đọc/commit thấp hơn tốc độ producer.
- **Redelivery:** các record đã xử lý nhưng chưa commit có thể được giao lại sau restart/rebalance.
- **Rebalance và shutdown:** commit kéo dài làm chậm việc bàn giao partition hoặc dừng consumer.
- **SLO vận hành:** consumer có thể đang running nhưng không tiến triển đủ nhanh.

Không nên tối ưu commit latency bằng cách commit offset trước khi side effect thành công. Giảm latency theo cách đó có thể đánh đổi bằng mất dữ liệu nghiệp vụ.

## 2. “Commit” là commit nào?

Trong Spring Kafka có nhiều thao tác mang tên commit:

| Loại commit | Hệ thống | Ý nghĩa |
|---|---|---|
| Consumer offset commit | Kafka group coordinator | Ghi vị trí đọc tiếp theo của consumer group |
| Producer transaction commit | Kafka transaction coordinator | Hoàn tất một Kafka transaction chứa output records, có thể kèm offsets |
| Database transaction commit | PostgreSQL/MySQL/... | Làm bền vững các thay đổi database |
| Listener acknowledgment | Spring Kafka container | Thông báo record đã được ứng dụng xử lý, có thể dẫn tới commit theo AckMode |
| HTTP business acknowledgment | Service khác | Một loại xác nhận nghiệp vụ, không phải Kafka offset commit |

**Commit latency** được xuất bản bởi Kafka consumer client thường liên quan đến yêu cầu commit offset của consumer group. Nếu listener dùng Kafka transaction, cần theo dõi thêm thời gian commit Kafka transaction vì đường commit offsets có thể đi qua `sendOffsetsToTransaction` và `commitTransaction`, không giống lời gọi `commitSync` thông thường.

Tương tự, một metric JDBC transaction commit chậm không được gộp với Kafka commit latency. Hai nguyên nhân và cách khắc phục rất khác nhau.

## 3. Consumer offset được commit theo quy tắc nào?

Mỗi record có địa chỉ:

    topic + partition + offset

Ví dụ:

    orders.created partition 2

      offset 100 -> Order A
      offset 101 -> Order B
      offset 102 -> Order C
      offset 103 -> Order D

Consumer xử lý thành công record ở offset 100. Giá trị được commit cho group thường là **101**, tức offset tiếp theo mà consumer cần đọc khi tiếp tục.

    Last processed offset: 100
    Committed offset:      101

Nếu consumer xử lý 100, 101, 102 nhưng chỉ commit 101, khi restart nó có thể đọc lại từ offset 101. Những side effect của 101 và 102 có thể chạy lần nữa.

Cần phân biệt:

- **Consumer position:** vị trí mà consumer sẽ poll tiếp trong phiên hiện tại.
- **Committed offset:** vị trí được group coordinator lưu cho lần restart/reassignment.
- **Processed offset:** offset ứng dụng đã xử lý xong theo định nghĩa nghiệp vụ.
- **Acknowledged offset:** offset đã được listener/container xác nhận, chưa chắc commit request đã hoàn tất.

Việc KafkaConsumer.poll() trả về record tới offset 150 không chứng minh group đã commit tới 151.

## 4. Timeline: từ xử lý record đến commit thành công

Một pipeline đơn giản:

    T0  consumer.poll() trả record
    T1  listener bắt đầu xử lý
    T2  business side effect hoàn tất
    T3  container quyết định commit offset
    T4  Kafka client gửi OffsetCommit request
    T5  Group coordinator xử lý yêu cầu
    T6  Kafka client nhận response
    T7  container tiếp tục vòng xử lý/poll

Có thể phân tách:

    Business processing latency = T2 - T1

    Waiting-to-commit latency    = T3 - T2
      (phụ thuộc AckMode, batching, scheduling)

    Offset commit request latency ~= T6 - T4

    Time until durable progress  = T6 - T2
      (nếu commit thành công)

Cách đo T4/T6 trong Kafka client là chi tiết implementation, nhưng phân tách khái niệm trên rất quan trọng. Một metric `commit-latency-avg` thấp không chứng minh offset được commit ngay sau business side effect nếu ứng dụng cố ý đợi nhiều record rồi mới commit.

Muốn đo **processing-to-commit** end-to-end phải thu thập thêm timestamp/metric ở tầng ứng dụng hoặc container, không dùng duy nhất metric Kafka client.

## 5. Kafka group coordinator tham gia ra sao?

Consumer offset là trạng thái của **consumer group**, được Kafka lưu qua cơ chế coordinator và internal topic `__consumer_offsets`.

Luồng giản lược:

    Spring Kafka listener container
               |
               v
       KafkaConsumer.commitSync()
               |
               v
         Kafka client
               |
               v
       Group coordinator broker
               |
               v
        Offset commit response

Group coordinator cần xử lý yêu cầu commit theo metadata nhóm, partition và generation hợp lệ. Nếu consumer vừa mất quyền sở hữu partition hoặc group đang rebalance, commit có thể bị từ chối, thử lại theo cơ chế được hỗ trợ, hoặc ném exception.

Độ trễ có thể đến từ:

1. Network RTT giữa client và broker.
2. Quá tải group coordinator.
3. Broker CPU, I/O hoặc replication pressure.
4. Rất nhiều commit requests từ nhiều consumer groups.
5. Request queue, throttling hoặc connection chập chờn.
6. Group rebalance và membership thay đổi.
7. Client thread/scheduler bị chậm hoặc JVM GC pause.

Đo commit latency từ client cần đi kèm broker metrics, bởi chỉ riêng một biểu đồ latency không xác định được root cause.

## 6. commitSync và commitAsync

Kafka Java consumer có hai kiểu commit cơ bản:

**commitSync:** đợi commit hoàn tất hoặc gặp lỗi/timeout theo contract API. Thích hợp khi ứng dụng cần biết kết quả commit trước khi tiếp tục hoặc trước khi rời partition.

**commitAsync:** gửi yêu cầu commit bất đồng bộ, có callback khi hoàn tất. Consumer không bị chặn theo cùng cách như synchronous commit, nhưng ứng dụng phải hiểu failure handling và thứ tự tiến độ.

So sánh:

| Khía cạnh | commitSync | commitAsync |
|---|---|---|
| Đường gọi | Có thể block chờ kết quả | Trả về nhanh, callback sau |
| Tác động latency lên consumer thread | Có thể lớn khi broker chậm | Ít blocking trực tiếp hơn |
| Xử lý lỗi | Exception từ lời gọi | Callback/logic theo dõi lỗi |
| Nhận biết kết quả | Rõ ràng sau khi method hoàn tất thành công | Cần theo dõi callback |
| Tương tác rebalance | Có thể cần commit trước revoke | Cần cẩn thận với callback trễ |
| Redelivery khi chưa commit | Vẫn có thể | Vẫn có thể |

**Async không có nghĩa commit miễn phí.** Yêu cầu vẫn phải đi tới broker. Metric latency của commit request có thể vẫn cao, chỉ là consumer thread ít bị block hơn tại thời điểm gọi.

Kafka client có các bảo đảm cụ thể về thứ tự request/callback, nhưng không nên thiết kế tự động retry một async commit cũ mà không xét offset mới đã được commit. Một retry muộn của tiến độ cũ có thể gây trạng thái offset lùi nếu logic tùy chỉnh sai.

## 7. Spring Kafka quyết định sync hay async thế nào?

Trong các phiên bản Spring Kafka hỗ trợ, `ContainerProperties` có tùy chọn `setSyncCommits(boolean)` điều khiển container dùng commit đồng bộ hay bất đồng bộ khi commit offsets theo cách container quản lý.

Ví dụ Java Configuration:

~~~java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        ContainerProperties props = factory.getContainerProperties();

        props.setAckMode(ContainerProperties.AckMode.BATCH);
        props.setSyncCommits(true);
        props.setSyncCommitTimeout(Duration.ofSeconds(8));

        return factory;
    }
}
~~~

Các import chính:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
~~~

`OrderEvent` là DTO ứng dụng. Ví dụ thể hiện cách cấu hình container, chưa có đầy đủ producer/consumer factories, serializers hoặc topic creation.

**Lưu ý về phiên bản:** API `setSyncCommitTimeout` và cơ chế commit retry/error handling có thể khác theo Spring Kafka version. Hãy kiểm tra Javadoc tương ứng với dependency của dự án.

Để dùng async commits trong đường commit của container, có thể cấu hình `setSyncCommits(false)`. Quyết định này cần dựa trên yêu cầu an toàn, cách xử lý async commit failures và kết quả integration test; không đổi sang async chỉ để làm đẹp p95 latency trong dashboard.

## 8. AckMode quyết định tần suất commit

Spring Kafka listener container có nhiều AckMode. Tùy mode, offset có thể được commit sau từng record, sau một batch từ poll hoặc theo điều kiện đếm/thời gian.

| AckMode | Hành vi khái quát | Ý nghĩa với commit latency |
|---|---|---|
| RECORD | Commit sau khi mỗi record listener xử lý thành công, theo cơ chế container | Nhiều commit requests hơn trong workload có record nhỏ |
| BATCH | Commit sau khi tất cả records từ một poll được xử lý | Ít commits hơn; nhiều record cùng một commit boundary |
| TIME | Commit khi đạt khoảng thời gian cấu hình theo cơ chế container | Có thể giảm commit frequency |
| COUNT | Commit khi đạt số record cấu hình | Phụ thuộc lượng record |
| COUNT_TIME | Khi đạt điều kiện count hoặc time | Cân bằng frequency và cửa sổ chưa commit |
| MANUAL | Listener acknowledge; commit theo cơ chế batch/container | Ack không luôn đồng nghĩa commit ngay |
| MANUAL_IMMEDIATE | Có thể commit ngay khi acknowledge trên consumer thread | Dễ tạo commit thường xuyên nếu ack từng record |

Ví dụ RECORD:

    poll() -> [A, B, C]

    process A -> commit offset after A
    process B -> commit offset after B
    process C -> commit offset after C

Ví dụ BATCH:

    poll() -> [A, B, C]

    process A
    process B
    process C
    commit offset after C

Chi tiết thời điểm commit thực tế còn phụ thuộc record/batch listener, transaction, error handler, seek/recovery và phiên bản Spring Kafka. Bảng trên để hiểu lựa chọn thiết kế, không phải mô tả một giao thức cố định cho mọi cấu hình.

## 9. RECORD và BATCH: trade-off giữa throughput và replay

Giả sử mỗi consumer xử lý 1.000 record/giây. Một commit request đồng bộ trung bình mất 15 ms.

Nếu cấu hình commit từng record thật sự chặn mỗi lần:

    Commit rate lý thuyết cần: 1.000 commits/s
    Thời gian chờ commit: 1.000 * 15 ms = 15 giây
      trong 1 giây hoạt động

Một consumer thread tuần tự không thể đạt 1.000 record/s với cấu hình đó nếu mỗi commit phải hoàn tất trước record tiếp theo. Đây là bottleneck tự tạo.

Nếu commit mỗi 100 record:

    Commit frequency ~= 1.000 / 100 = 10 commits/s

Chi phí chờ commit trên mỗi record được amortize xuống đáng kể. Nhưng trong trường hợp consumer crash trước commit cuối, những record đã xử lý trong batch nhưng chưa commit có thể phải thực hiện lại.

| Thiết kế | Lợi ích | Đánh đổi |
|---|---|---|
| Commit từng record | Cửa sổ replay nhỏ hơn | Overhead commit lớn |
| Commit theo batch | Throughput thường tốt hơn | Cửa sổ replay lớn hơn |
| Commit async | Giảm blocking trên thread | Phải xử lý lỗi và callback đúng |
| Transactional offsets + output | Atomic Kafka read-process-write | Chi phí transaction và timeout riêng |

Không áp dụng BATCH chỉ vì latency cao nếu mỗi record thực hiện side effect không idempotent. Trước hết, phải bảo đảm xử lý lại record không làm thay đổi nghiệp vụ sai.

## 10. MANUAL acknowledgment không phải commit request trực tiếp

Một listener có thể chủ động acknowledge:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-worker",
    containerFactory = "manualAckFactory"
)
public void onOrder(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(record.value());
    acknowledgment.acknowledge();
}
~~~

Ví dụ này yêu cầu `manualAckFactory` dùng một AckMode hỗ trợ manual acknowledgment, chẳng hạn MANUAL hoặc MANUAL_IMMEDIATE.

Cần phân biệt:

- **Thời gian xử lý:** từ lúc listener nhận record tới khi `processIdempotently` hoàn tất.
- **Thời gian gọi acknowledge:** thao tác xác nhận với Spring Kafka container.
- **Thời gian Kafka offset commit:** request/response giữa consumer client và coordinator.

Với AckMode.MANUAL, acknowledge thường đánh dấu tiến độ để container commit ở một ranh giới thích hợp, không bảo đảm commit đến broker ngay lúc method trở về.

Với MANUAL_IMMEDIATE, nếu acknowledge được gọi trên consumer thread, cơ chế có thể commit ngay theo cấu hình. Nếu gọi từ thread khác, hành vi có thể khác; không dùng async ack mà không nắm hợp đồng của container.

**Đừng đặt timestamp ngay sau acknowledge() rồi gọi chênh lệch đó là Kafka commit latency.** Nó có thể mới đo local method overhead hoặc thời gian chờ scheduling.

## 11. Commit latency trong transactional consumer

Với một listener container có Kafka transaction, luồng read-process-write thường là:

    Consume input record
             |
             v
      Begin Kafka TX
             |
             v
     Process + KafkaTemplate.send()
             |
             v
    Send input offsets into TX
             |
             v
       commitTransaction()
             |
             +-- Output Kafka committed
             +-- Input group offsets committed

Trong mô hình này, việc hoàn tất offset của consumer gắn với **transaction commit**, chứ không chỉ một `commitSync` độc lập.

Vì vậy:

1. Client consumer `commit-latency-avg` không nhất thiết đo toàn bộ độ trễ producer transaction commit.
2. Cần theo dõi producer transaction duration/commit/abort metrics tương ứng.
3. Input offsets và output Kafka được commit nguyên tử khi transaction hoạt động đúng.
4. Nếu transaction abort, offset không được commit bởi transaction đó và input có thể redelivery.
5. Nếu business side effect ghi database trước Kafka commit, nó vẫn có thể lặp lại khi Kafka rollback.

Không trộn lẫn Kafka transaction commit latency với database commit latency trong cùng một biểu đồ nếu không ghi rõ nguồn đo.

## 12. Kafka client metrics liên quan commit

Kafka Java consumer xuất bản metrics qua Kafka client Metrics API và thường qua JMX. Những metric thường gặp trong nhóm consumer coordinator metrics là:

| Metric | Diễn giải |
|---|---|
| `commit-latency-avg` | Độ trễ trung bình ghi nhận cho offset commit requests |
| `commit-latency-max` | Độ trễ lớn nhất được ghi nhận trong cửa sổ đo của client |
| `commit-rate` | Tốc độ commit requests trong đơn vị thời gian theo metric client |
| `commit-total` | Tổng số commit requests được ghi nhận theo client metric |
| `assigned-partitions` | Số partition consumer đang được assign, trong nhóm metric phù hợp |
| `rebalance-total` | Số lần rebalance được ghi nhận, tùy Kafka client version |
| `last-rebalance-seconds-ago` | Khoảng thời gian kể từ rebalance gần nhất khi metric hỗ trợ |

Tên chính xác, group, đơn vị đo và những metrics sẵn có **phụ thuộc phiên bản Kafka client**. Khi dựng dashboard, kiểm tra danh sách thực tế do client xuất bản thay vì giả định tất cả luôn có.

Commit latency thường được báo cáo theo **milliseconds** cho Kafka consumer coordinator metrics. Khi chuyển qua JMX exporter, Prometheus hoặc Micrometer, cần kiểm tra hệ thống có chuyển đổi unit hay đổi tên metric không.

`commit-total` là số yêu cầu theo định nghĩa metric client, **không phải số record được xử lý**, cũng không mặc nhiên là số lần commit thành công nếu không xem contract của phiên bản.

## 13. JMX và nguồn dữ liệu metric

Kafka client thường cung cấp coordinator metrics dưới một JMX MBean dạng:

~~~text
kafka.consumer:type=consumer-coordinator-metrics,client-id=<consumer-client-id>
~~~

Các thuộc tính có thể bao gồm `commit-latency-avg`, `commit-latency-max`, `commit-rate` và các chỉ số liên quan.

Trong môi trường Spring Kafka với concurrency > 1, mỗi child consumer có thể có client.id riêng. Một dashboard chỉ theo dõi một MBean/client ID có thể bỏ sót các consumer khác.

Ví dụ:

    Group: billing-workers
    Pod A:
      clientId billing-0
      clientId billing-1
    Pod B:
      clientId billing-2
      clientId billing-3

Nếu billing-2 có commit latency tăng mạnh còn các client khác bình thường, trung bình toàn group có thể che giấu sự cố ở một consumer.

Khi scrape JMX cần chú ý:

- JMX exporter có rule map attribute name thành Prometheus metric.
- Dấu gạch ngang có thể được chuyển thành dấu gạch dưới.
- client-id có thể chứa suffix động theo container và deployment.
- Một số metrics chỉ xuất hiện sau khi consumer bắt đầu hoạt động.
- Metric mất đi khi consumer bị đóng; không hiểu “không còn series” là latency bằng 0.

## 14. Micrometer trong Spring Kafka

Spring Kafka có khả năng tích hợp Micrometer để theo dõi listener/container, và Kafka Java client cũng có metrics riêng cho consumer/coordinator.

**Hai nhóm này không hoàn toàn giống nhau:**

- **Listener timer/observation:** thời gian Spring Kafka gọi listener hoặc xử lý record/batch theo phạm vi instrumentation.
- **Kafka consumer client metrics:** bao gồm các chỉ số poll, fetch, commit, rebalance tùy version.
- **Producer transaction metrics:** đo hoạt động producer/transaction, cần được theo dõi riêng khi dùng EOS.
- **Business metrics:** thời gian database/HTTP call, commit DB và kết quả xử lý nghiệp vụ.

Khi hệ thống dùng Micrometer, có thể dùng Kafka client metrics binder/listener của thư viện đang chạy hoặc JMX exporter để đưa commit metrics vào registry giám sát.

Đừng suy luận `spring.kafka.listener.observation-enabled=true` mặc nhiên tạo ra một timer tên “Kafka commit latency” cho mọi offset commit. Observation của listener và consumer coordinator commit request là hai phạm vi khác nhau.

Cần kiểm tra metric thực tế qua actuator metrics endpoint, JMX, Prometheus scrape hoặc hệ thống APM được cấu hình trong dự án.

## 15. Cấu hình listener telemetry

Ví dụ Spring Boot YAML bật observation nếu phiên bản có hỗ trợ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: billing-workers
      enable-auto-commit: false
      properties:
        max.poll.records: 100
    listener:
      ack-mode: batch
      observation-enabled: true

management:
  metrics:
    tags:
      application: billing-service
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Đây là cấu hình định hướng cho ứng dụng có Micrometer/Actuator và registry tương ứng. Sự tồn tại của endpoint `prometheus` cần dependency Prometheus registry; không phải cấu hình YAML đơn lẻ tự tạo exporter.

Khi dùng observation, hãy kiểm tra sự tương thích với các Micrometer listener timer truyền thống trong Spring Kafka version đang chạy; một số mode instrumentation có thể thay thế nhau hoặc thay đổi tên metric.

Muốn có `commit-latency-avg`, vẫn cần **Kafka consumer client metrics** được expose. Không giả định listener observation đã bao trùm coordinator.

## 16. Đo commit latency thủ công khi dùng raw KafkaConsumer

Với ứng dụng trực tiếp quản lý KafkaConsumer, có thể tự đo thời gian lời gọi commitSync bằng `System.nanoTime()` và Micrometer Timer:

~~~java
public final class TimedOffsetCommitter {

    private final Timer commitTimer;

    public TimedOffsetCommitter(MeterRegistry registry) {
        this.commitTimer = Timer.builder(
                "app.kafka.offset.commit.duration")
            .description("Synchronous offset commit call duration")
            .register(registry);
    }

    public void commit(
            Consumer<String, String> consumer,
            Map<TopicPartition, OffsetAndMetadata> offsets) {

        long started = System.nanoTime();

        try {
            consumer.commitSync(offsets);
        }
        finally {
            commitTimer.record(
                System.nanoTime() - started,
                TimeUnit.NANOSECONDS
            );
        }
    }
}
~~~

Các import liên quan:

~~~java
import java.util.Map;
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.common.TopicPartition;
~~~

Đoạn này dành cho **consumer do ứng dụng tự quản lý**, chạy commit trên thread sở hữu KafkaConsumer. Không được gọi `commitSync` từ một @KafkaListener chỉ để thêm metric khi Spring Kafka container đã quản lý offset, vì có thể làm sai AckMode, transaction hoặc commit order.

Một `Timer` ghi trong `finally` đo thời gian method kể cả khi commit thất bại; để phân biệt success/error, dùng thêm counter hoặc timer tag có cardinality thấp và trạng thái rõ ràng.

Timer này đo **wall-clock method duration**, có thể bao gồm retry/wait bên client. Do đó giá trị không nhất thiết trùng hoàn toàn với client `commit-latency-avg`. Điều đó không có nghĩa metric nào sai; chúng đo hai phạm vi khác nhau.

## 17. Vì sao không nên đo bằng thời gian acknowledge()?

Ví dụ sai về mặt khái niệm:

~~~java
long start = System.nanoTime();

ack.acknowledge();

long duration = System.nanoTime() - start;
recordMetric(duration, "commit_latency");
~~~

Đoạn code này có thể chỉ ghi nhận thời gian để container tiếp nhận acknowledgment, chưa chắc request `OffsetCommit` đã được gửi và hoàn tất.

Tùy AckMode, acknowledgment có thể được lưu để commit ở cuối poll, sau một batch hoặc tại một ranh giới khác. Nếu ack được gọi từ worker thread, thời điểm commit có thể còn muộn hơn.

Nếu mục tiêu là đo Kafka offset commit latency, ưu tiên metric từ **Kafka client coordinator**. Nếu muốn đo thời gian từ “business success” tới “offset durable”, cần thiết kế instrumentation bám vào callback/kết quả commit thực tế theo contract container, không đo nhầm đoạn code đang thuận tiện.

## 18. Độ trễ commit có thể tăng vì commit quá thường xuyên

Giả sử một group có 60 consumer, mỗi consumer làm synchronous commit sau mỗi record và mỗi consumer xử lý 100 record/giây:

    60 consumers * 100 commits/s
      = 6.000 commits/s

Đó là một lượng lớn offset commit requests, chưa tính các consumer groups khác sử dụng cùng Kafka cluster.

Khi coordinator quá tải hoặc network/request queue bận, commit latency có thể tăng. Một vòng phản hồi xấu xuất hiện:

    Commit requests nhiều
          |
          v
    Coordinator latency tăng
          |
          v
    Consumer threads block lâu hơn
          |
          v
    Processing throughput giảm
          |
          v
    Consumer lag tăng

Biện pháp có thể là commit theo batch phù hợp, giảm tần suất commit không cần thiết hoặc phân bố workloads, nhưng phải cân nhắc replay và độ bền nghiệp vụ. Không khắc phục bằng cách tăng thread count vô hạn; việc đó có thể tạo thêm commit traffic.

## 19. Tính cost trên mỗi record

Một mô hình throughput đơn giản cho consumer xử lý đồng bộ:

    CostPerRecord = BusinessTime + CommitCostPerRecord

Nếu commit sau từng record:

    CommitCostPerRecord ~= AverageCommitLatency

Nếu commit mỗi N record:

    CommitCostPerRecord ~= AverageCommitLatency / N

Ví dụ:

    BusinessTime = 8 ms/record
    CommitLatency = 40 ms/commit

    Commit từng record:
      Cost ~= 8 + 40 = 48 ms/record
      Throughput lý thuyết ~= 20,8 record/s/thread

    Commit mỗi 50 record:
      Cost ~= 8 + 40/50 = 8,8 ms/record
      Throughput lý thuyết ~= 113,6 record/s/thread

Đây là mô hình minh họa, giả định xử lý tuần tự, không overlap I/O và commit blocking. Thực tế cần xét fetch, network, batch overhead, partition skew, synchronous producer send và scheduler.

Con số giúp thấy vì sao giảm commit frequency có thể tăng throughput, nhưng **không tự chứng minh cấu hình đó an toàn cho nghiệp vụ**.

## 20. Đánh đổi giữa commit frequency và duplicate window

Giả sử consumer xử lý được 500 record/giây và commit mỗi 200 record.

    Khoảng cách giữa commits ~= 200/500 = 0,4 giây

Nếu JVM crash trước commit kế tiếp, một số record đã thực hiện side effect có thể được giao lại. Về mặt số lượng, cửa sổ chưa commit thường tối đa xấp xỉ kích thước batch còn xử lý, nhưng phạm vi replay thực tế còn phụ thuộc committed offset, cách container xử lý lỗi và partition assignments.

Nếu commit mỗi 2.000 record:

    Khoảng commit ~= 2.000/500 = 4 giây

Giảm số commit requests nhưng có thể làm nhiều work hơn phải chạy lại.

Để lựa chọn hợp lý:

1. Side effect có idempotency không?
2. Lần xử lý lại có gây duplicate payment/email không?
3. Recovery từ backlog có đủ nhanh không?
4. SLA cho committed progress là bao lâu?
5. Consumer restart/rebalance thường xảy ra mức nào?
6. DLT/recovery có bảo toàn record lỗi không?

Không có một batch size tối ưu chung cho mọi consumer group.

## 21. Ảnh hưởng của async commit và callback lỗi

Khi dùng async commit trực tiếp bằng Kafka client:

~~~java
consumer.commitAsync(
    offsets,
    (committedOffsets, exception) -> {
        if (exception != null) {
            log.warn(
                "Asynchronous Kafka offset commit failed; offsets={}",
                committedOffsets,
                exception
            );
        }
    }
);
~~~

Đoạn code này dành cho **raw consumer** hoặc ví dụ Kafka client API; không nên gọi trong listener nếu offset đã do Spring Kafka quản lý.

Rủi ro thường gặp là **retry commit cũ không đúng thời điểm**:

    Async commit #1: offset 100
    Async commit #2: offset 150
    Commit #2 thành công
    Callback lỗi của #1 xuất hiện
    Ứng dụng retry #1 một cách mù quáng

Nếu retry offset 100 sau khi offset 150 đã được ghi nhận, ứng dụng có thể làm tiến độ group lùi theo một đường commit không phù hợp.

Do đó, nếu tự quản lý async commits, cần xác định policy chỉ commit tiến độ hợp lệ mới nhất và phối hợp với revoke/shutdown. Đừng trộn `commitAsync`, `commitSync` và callback retry tùy tiện.

Spring Kafka có cơ chế quản lý callback và commit behavior khi `syncCommits=false`; muốn biết lỗi/metric ở mức nào, cần kiểm tra chính sách container và listener factory đang chạy.

## 22. Commit failure khác commit latency cao

Một yêu cầu commit mất 300 ms nhưng thành công là **high latency**. Một yêu cầu timeout sau nhiều giây và không có xác nhận là **commit failure hoặc uncertain outcome**.

| Tình trạng | Biểu hiện | Ý nghĩa |
|---|---|---|
| Latency tăng, success vẫn cao | p95/p99 commit tăng | Coordinator/network chậm hoặc quá tải |
| Timeout | Client không nhận kết quả trong timeout | Có thể chưa rõ broker đã commit chưa |
| CommitFailedException | Group membership/assignment không còn phù hợp | Cần xem rebalance/poll interval |
| Authorization error | Thiếu quyền thực hiện thao tác phù hợp | Cấu hình ACL/credential |
| Rebalance đang diễn ra | Commit gặp generation change | Xem group stability, poll latency |
| Transaction abort/fencing | Offset trong Kafka TX không commit | Xem producer transaction metrics, lifecycle |

Không dùng một `commit-latency-max` rất lớn để kết luận đã có data loss. Kafka có thể redeliver từ committed offset trước đó nếu commit chưa thành công; đây thường là at-least-once behavior, không phải mặc nhiên mất message.

Ngược lại, lỗi nguy hiểm là ứng dụng **tự đánh dấu nghiệp vụ thành công rồi commit offset quá sớm**; latency thấp cũng không cứu được thiết kế sai đó.

## 23. Commit latency khi rebalance

Trong rebalance, partition ownership thay đổi. Một consumer có thể được gọi `onPartitionsRevoked` trước khi nhường partition để hoàn tất công việc và commit offsets phù hợp.

Nếu commitSync quá chậm:

    Rebalance bắt đầu
          |
          v
    Revocation callback
          |
          v
    Flush + commitSync
          |
          v
    Chờ coordinator / network
          |
          v
    Consumer mới nhận assignment muộn

Commit latency cao có thể làm kéo dài rebalance và giảm thời gian sẵn sàng xử lý.

Quan trọng:

- Trong `onPartitionsRevoked`, commit có thể phù hợp nếu consumer vẫn có quyền và state hợp lệ.
- Trong `onPartitionsLost`, consumer **đã mất ownership**; không nên cố commit offset như owner cũ.
- Khi rebalance và commit xung đột, lỗi commit có thể xuất hiện, cần xem nguyên nhân.
- Với `CooperativeStickyAssignor` hoặc chiến lược cooperative tương ứng, phạm vi revoke có thể nhỏ hơn eager rebalance.
- Một ứng dụng dùng async work cần fencing/stop task cũ khi partition chuyển owner.

Không nên tự gọi commitSync bên trong rebalance listener nếu Spring Kafka container đã có cơ chế commit và không cần logic tùy chỉnh; dễ tạo double commit, sai offset hoặc deadlock.

## 24. max.poll.interval.ms và commit latency

`max.poll.interval.ms` giới hạn khoảng thời gian giữa các lần poll theo yêu cầu consumer group. Trong một số đường xử lý, **thời gian xử lý listener cộng thời gian chờ synchronous commit** ảnh hưởng đến khoảng cách giữa các poll.

Ví dụ:

    max.poll.interval.ms = 300.000 ms

    Một poll trả 500 records
    Xử lý mỗi record 350 ms: 175.000 ms
    Tổng synchronous commit wait: 100.000 ms
    Tổng xấp xỉ: 275.000 ms

Khi cộng retry, GC và scheduler overhead, consumer có thể tiến sát ngưỡng và gặp rebalance.

Đánh giá theo công thức gần đúng:

    TimeBetweenPolls
      ~= processingTimeForReturnedRecords
         + commitWaitingTime
         + handler/retry/otherOverhead

Không nhất thiết mọi ACK/commit nằm nguyên trong đường này với mọi AckMode, nhưng đối với sync commit tuần tự, thời gian chờ là một phần overhead rõ ràng.

Khi tăng timeout, cần tính đến tốc độ phát hiện consumer bị treo. Đừng chỉ tăng max.poll.interval.ms để che việc coordinator đang commit chậm.

## 25. Group coordinator overload

Nếu nhiều consumer groups cùng commit liên tục, broker làm coordinator có thể trở thành điểm nóng. Các dấu hiệu:

- Commit latency tăng đồng thời trên nhiều consumers.
- Commit request rate cao.
- CPU/request queue broker cao.
- Rebalance/heartbeat metrics biến động.
- Kafka client request timeout tăng.
- Một số group gặp commit failures.

Hướng điều tra:

1. Xác định broker đang phục vụ coordinator cho các group bị ảnh hưởng.
2. So sánh latency theo client, group và thời điểm.
3. Kiểm tra broker CPU, network, request handler và I/O.
4. Kiểm tra request throttling và quota.
5. Xem commit rate có tăng sau rollout AckMode.RECORD hay không.
6. Xem có nhiều consumer instances mới sinh ra do autoscale không.
7. Nếu cần, giảm commit frequency phù hợp thay vì tiếp tục tăng tải coordinator.

Đừng suy ra root cause chỉ vì một broker có CPU cao. Các chỉ số group coordinator, network latency và client-specific metrics cần được ghép lại.

## 26. Network latency và multi-region

Một consumer ở region khác xa Kafka cluster có thể có RTT cao hơn đáng kể so với consumer cùng region.

Ví dụ:

    Consumer region A -> broker region A: RTT 3 ms
    Consumer region B -> broker region A: RTT 70 ms

Nếu commitSync phụ thuộc một request/response, khoảng cách mạng có thể chiếm tỷ lệ lớn trong commit latency. Commit từng record trên đường truyền RTT 70 ms dễ làm throughput của mỗi consumer thread bị giới hạn, dù business logic chạy rất nhanh.

Một số hướng cải thiện:

- Ưu tiên đặt consumer gần cluster hoặc đường mạng có RTT thấp, ổn định.
- Tránh thiết kế synchronous cross-region commit cho từng record nhỏ nếu không cần thiết.
- Đo network packet loss, retransmit và TLS overhead.
- Xem khả năng dùng batching hoặc pipeline phù hợp với replay/idempotency.
- Không coi việc tăng `request.timeout.ms` là giảm latency; nó chủ yếu thay đổi thời gian chờ trước khi báo lỗi.

Nếu kiến trúc bắt buộc multi-region, cần dự trù latency vào throughput/SLO ngay từ thiết kế.

## 27. JVM, GC và client-thread scheduling

Commit latency quan sát ở ứng dụng có thể chịu ảnh hưởng từ JVM:

- Stop-the-world GC kéo dài.
- CPU throttling trong Kubernetes.
- Thread starvation trong container/host.
- Synchronous callback hoặc logging chậm trên consumer thread.
- Áp lực allocation khi deserialization/serialization.
- Thread pool nghẽn cho telemetry hoặc error handling.

Một method commitSync mất lâu trên đồng hồ ứng dụng có thể bao gồm cả thời gian thread bị scheduler trì hoãn. Vì vậy, khi phân tích wall-clock duration, cần so sánh với Kafka client metrics và JVM/process metrics.

Nếu commit latency tăng cùng lúc với GC pause trên một pod nhưng không tăng trên những pod khác, có thể vấn đề nằm ở client JVM thay vì coordinator broker.

Theo dõi CPU usage, CPU throttling, GC pause p99, heap allocation và sự kiện pod restart cùng commit metrics.

## 28. Phân biệt commit latency với fetch và poll latency

Kafka consumer có nhiều giai đoạn:

    poll/fetch
        |
        v
    deserialize
        |
        v
    process
        |
        v
    acknowledge
        |
        v
    commit
        |
        v
    next poll

Các metric có ý nghĩa khác nhau:

| Metric | Câu hỏi |
|---|---|
| Fetch latency | Broker/client lấy dữ liệu mất bao lâu? |
| Poll duration | Một vòng poll mất bao lâu? |
| Listener processing duration | Business listener mất bao lâu? |
| Commit latency | Yêu cầu ghi nhận offset mất bao lâu? |
| Consumer lag | Còn bao nhiêu offset chưa được tiêu thụ/commit theo cách đo? |
| End-to-end event age | Một event mất bao lâu từ publish đến xử lý? |

Một group có lag cao có thể do fetch chậm, listener chậm, commit chậm, downstream quá tải hoặc partition skew. Không kết luận commit là bottleneck nếu chưa phân biệt các giai đoạn.

Commit latency thấp nhưng listener p99 cao vẫn có thể khiến lag tăng. Commit latency cao nhưng commit frequency rất thấp có thể ảnh hưởng throughput ít hơn bạn tưởng.

## 29. Thiết kế dashboard commit latency

Một dashboard phục vụ vận hành có thể gồm bốn vùng.

**A. Commit health**

- `commit-latency-avg` theo consumer group/client.
- `commit-latency-max` theo client.
- `commit-rate` và `commit-total` rate.
- Commit failures/timeouts từ log hoặc counter ứng dụng.

**B. Consumer progress**

- Committed offset progression.
- Consumer lag theo partition/group.
- Oldest unprocessed record age.
- Records consumed/processed per second.

**C. Group lifecycle**

- Rebalance count/duration.
- Assigned partitions/active members.
- Listener container running state.
- ConsumerStoppedEvent và NonResponsiveConsumerEvent.

**D. Dependency và broker**

- Listener processing p95/p99.
- HTTP/database latency và saturation.
- Broker request queue, CPU, network, group coordinator workload.
- JVM GC và CPU throttling.

Biểu đồ nên có khả năng drill down từ toàn group tới instance/clientId/partition phù hợp. Khi metrics từ nhiều clients được aggregate, tránh dùng trung bình đơn giản che giấu một client bị commit latency rất cao.

## 30. Avg/max không giống p95/p99

Kafka client thường xuất bản `commit-latency-avg` và `commit-latency-max`, nhưng **không phải phiên bản nào cũng cung cấp histogram commit duration** để tính p95/p99 trực tiếp.

- **Average:** dễ thấy xu hướng chung nhưng che tail spikes.
- **Maximum:** nhận biết đỉnh cao nhưng nhạy với một sự kiện bất thường và cửa sổ đo.
- **p95/p99:** cần histogram hoặc tập mẫu có đủ thông tin, không thể suy ra từ avg và max.
- **Request failure rate:** metric khác; latency của request thành công thấp không loại trừ nhiều commit timeout.

Đừng ghi nhãn một đường biểu diễn là `commit_p99` nếu nguồn thực tế chỉ có `commit-latency-max`. Với yêu cầu tail latency nghiêm ngặt, có thể bổ sung instrumentation thích hợp tại nơi phát commit/nhận callback, theo API thực tế của client/container.

Khi dùng Micrometer Timer, cần bật histogram/SLO buckets trước khi kỳ vọng Prometheus có thể tính quantile từ histogram. Timer đơn thuần không bảo đảm mọi percentile được xuất bản.

## 31. Đặt ngưỡng cảnh báo

Một chính sách cảnh báo không nên chỉ so sánh commit latency với hằng số.

Ví dụ:

    Warning:
      commit latency average > 100 ms trong 5 phút
      AND commit rate đủ lớn để số liệu có ý nghĩa

    Critical:
      commit failures tăng
      AND consumer lag/oldest age tăng

    Incident:
      commit progress ngừng hoàn toàn
      AND producer vẫn phát dữ liệu
      AND consumer group có active consumers

Các con số là minh họa, không phải chuẩn Kafka cố định. Trong cluster cùng region, 100 ms có thể bất thường; trong kiến trúc cross-region, baseline có thể cao hơn.

Nên kết hợp:

1. Baseline bình thường theo giờ/ngày.
2. Commit rate để tránh alert khi chỉ có một mẫu.
3. Mức tăng tương đối so với baseline.
4. Error/timeout/rebalance signals.
5. Consumer lag và business freshness SLO.
6. Phạm vi ảnh hưởng: một consumer hay nhiều groups.

Một alert chỉ vì `commit-latency-max` có một spike nhỏ có thể gây alert fatigue.

## 32. Khi commit latency thấp nhưng lag vẫn tăng

Kịch bản:

    CommitLatency: 8 ms (ổn định)
    ListenerProcessing: 500 ms/record
    InputRate: 400 records/s
    ConsumerCapacity: 100 records/s
    Lag tăng

Vấn đề là business throughput, không phải offset commit. Tối ưu commit từ 8 xuống 3 ms sẽ có tác dụng nhỏ nếu record đang chờ database nửa giây.

Các nguồn thường gặp:

- External API/database chậm.
- Rate limiter đang bảo vệ quota.
- Hot partition và phân phối key lệch.
- Consumer concurrency thấp so với số partition.
- Retry blocking vì dữ liệu hoặc dependency lỗi.
- Batch processing không tối ưu.

Xem processing duration và dependency metrics trước khi thay đổi AckMode.

## 33. Khi commit latency cao nhưng lag vẫn thấp

Kịch bản:

    InputRate: 10 records/s
    ConsumerCapacity: 100 records/s
    CommitLatency: 120 ms
    Lag: gần 0

Có thể workload thưa và còn nhiều headroom nên commit latency cao không gây ảnh hưởng rõ rệt tới freshness.

Dù vậy vẫn cần quan sát:

- Commit failures hoặc group instability.
- Shutdown/rebalance duration.
- Kafka transaction timeout nếu dùng giao dịch.
- Khả năng sự cố sẽ nghiêm trọng hơn khi traffic tăng đột ngột.
- Các consumer group khác bị coordinator quá tải.

Ưu tiên xử lý dựa trên ảnh hưởng SLO và trend; không chỉ tối ưu một con số để tạo dashboard đẹp.

## 34. Khi commit latency tăng sau deployment

Một kịch bản điều tra hữu ích:

    T0: Deployment A dùng AckMode.BATCH
    T1: Deployment B chuyển thành AckMode.RECORD
    T2: Commit-rate tăng gấp nhiều lần
    T3: Commit latency tăng, lag tăng
    T4: Rollback hoặc điều chỉnh frequency có kiểm soát

Các câu hỏi:

1. Có đổi AckMode, syncCommits, commit timeout hoặc commit retries không?
2. Có đổi max.poll.records hoặc listener concurrency không?
3. Có tăng số pod nhưng giữ nguyên partition count không?
4. Có bật transaction cho listener mới không?
5. Có thay đổi producer/consumer client version không?
6. Có thay đổi network region hoặc broker routing không?
7. Commit latency tăng trên nhóm mới hay toàn cluster?

Đánh dấu deployment trên dashboard giúp phân biệt hệ quả của thay đổi cấu hình với broker outage độc lập.

## 35. Không giảm commit latency bằng cách commit sớm

Một anti-pattern:

~~~java
@KafkaListener(topics = "payments")
public void consume(
        PaymentRequested event,
        Acknowledgment ack) {

    ack.acknowledge(); // Quá sớm!

    paymentGateway.charge(
        event.paymentId(),
        event.amount()
    );
}
~~~

Nếu ứng dụng ack/commit offset trước khi gọi paymentGateway và bị crash sau ack, consumer group có thể bỏ qua event khi restart dù thanh toán chưa được thực hiện.

Ví dụ đúng về mặt thứ tự nghiệp vụ:

~~~java
@KafkaListener(topics = "payments")
public void consume(
        PaymentRequested event,
        Acknowledgment ack) {

    paymentGateway.chargeIdempotently(
        event.paymentId(),
        event.amount(),
        event.eventId()
    );

    ack.acknowledge();
}
~~~

Cần listener container có manual AckMode phù hợp. Dù ack sau side effect, vẫn có cửa sổ side effect thành công nhưng offset chưa commit, dẫn tới redelivery. Vì vậy phải dùng idempotency key.

**Commit offset sớm không phải giải pháp performance hợp lệ nếu nó phá vỡ delivery guarantee.**

## 36. Commit latency trong batch listener

Với batch listener, ứng dụng nhận danh sách records trong một lần gọi:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "orders-batch",
    containerFactory = "batchListenerFactory"
)
public void consumeBatch(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        orderService.processIdempotently(record.value());
    }
}
~~~

Ví dụ giả định factory dùng `setBatchListener(true)` và transaction/ack policy được cấu hình thích hợp.

Commit theo batch giảm số lần commit nhưng có những đánh đổi:

- Một record lỗi có thể ảnh hưởng nhiều record trong batch.
- Thời gian xử lý cả batch có thể gần max.poll.interval.ms.
- Nếu batch bị retry, side effect của các record trước lỗi có thể chạy lại.
- Recovery từng record trong batch phụ thuộc error handler và exception class.
- Commit latency của một batch có thể tương tự một commit đơn lẻ, nhưng số records được bảo vệ bởi commit đó lớn hơn.

Để báo cáo chính xác, nên theo dõi `records-per-commit` (số đo ứng dụng nếu cần), không chỉ commit-rate.

## 37. Commit latency và DLT/recovery

Khi một record bị lỗi và được chuyển sang dead-letter topic, container có thể cần cập nhật offset sau khi recovery thành công.

Nếu DLT publish thành công nhưng offset commit thất bại, record nguồn có thể được giao lại; recoverer có thể gửi lại DLT nếu thiếu idempotency hoặc xử lý recovery phù hợp.

Nếu container commit offset nguồn dù DLT publish thất bại, record lỗi có thể bị mất khỏi đường recovery. Vì vậy:

- Theo dõi DLT send latency và failures riêng.
- Không gộp DLT publish success với consumer offset commit success.
- Nếu dùng Kafka transactions cho recovery, giám sát transaction commit outcome.
- Ghi eventId/headers gốc để nhận diện duplicate khi re-drive.
- Không coi commit latency tăng là lý do bỏ qua xác nhận DLT publish bền vững.

Commit latency cao trong đường recovery có thể làm chậm việc giải phóng một poison record, làm partition lag tiếp tục tăng.

## 38. Tác động của producer transaction commit latency

Một ứng dụng Kafka-to-Kafka transactional có thể có output latency tăng vì producer transaction commit chậm, ngay cả khi metric consumer offset commit thông thường rất thấp.

Ví dụ:

    Input -> listener -> KafkaTemplate.send(output)
        -> sendOffsetsToTransaction(input offsets)
        -> commitTransaction()
        -> downstream read_committed thấy output

Nếu transaction còn mở, downstream read_committed có thể phải chờ last stable offset. Đo riêng:

- Producer transaction begin/commit/abort count.
- Transaction duration.
- Transaction commit/abort errors.
- Producer send latency.
- End-to-end output visibility delay.

Không kết luận “offset commit latency bình thường nên EOS flow không có vấn đề” khi bottleneck thực tế là producer transaction coordinator hoặc transaction timeout.

## 39. Kết hợp commit latency với durability của database

Với consumer ghi database:

    poll
      |
      v
    Database transaction begin
      |
      v
    INSERT/UPDATE
      |
      v
    Database COMMIT
      |
      v
    Kafka OFFSET COMMIT

Đây thường là thứ tự phù hợp với at-least-once database processing: side effect database hoàn tất trước khi Kafka commit tiến độ. Nhưng nếu Kafka commit thất bại, record có thể redelivery và thao tác database có thể lặp.

Các metric cần xem riêng:

| Metric | Nội dung |
|---|---|
| Database commit latency | Độ trễ database xác nhận transaction |
| Kafka commit latency | Độ trễ group coordinator xác nhận offset |
| Listener end-to-end latency | Cả xử lý lẫn các bước commit liên quan |
| Duplicate detection count | Số lần idempotency từ chối xử lý lại |
| Consumer lag | Khối lượng record chưa tiến triển |

Nếu DBA tối ưu database commit từ 100 ms xuống 10 ms mà Kafka coordinator vẫn commit 200 ms, throughput có thể vẫn bị giới hạn. Ngược lại, commit Kafka nhanh nhưng DB transaction lâu cũng không giúp listener tăng throughput đáng kể.

## 40. Thử nghiệm commit latency bằng integration test

Commit latency phụ thuộc broker, mạng, group coordinator và client, vì vậy unit test đơn thuần không đủ để chứng minh behavior thực tế.

Có thể dùng Embedded Kafka hoặc Testcontainers với broker Kafka tương thích. Kịch bản:

1. Tạo topic có nhiều partition và consumer group test.
2. Cấu hình listener container với AckMode.RECORD và syncCommits=true.
3. Gửi tập record có eventId ổn định.
4. Ghi nhận client coordinator commit metrics và consumer throughput.
5. Chạy lại với AckMode.BATCH trong một môi trường test riêng.
6. So sánh commit-rate, latency và thời gian xử lý tổng.
7. Dừng consumer giữa batch, quan sát redelivery từ committed offset.
8. Bật idempotency và xác nhận side effect không bị nhân đôi.
9. Gây rebalance rồi xem commit error/latency.
10. Mô phỏng broker/coordinator chậm trong khả năng hạ tầng test cho phép.
11. Đối chiếu với listener processing timer và lag.
12. Xác nhận không có path nào commit offset trước side effect bền vững.

Không viết assertion commit latency phải đúng 20,000 ms hoặc p99 tuyệt đối trong CI: scheduler, broker test và máy chạy có dao động. Test nên kiểm tra tính đúng đắn transaction/offset và đặc điểm tương đối của commit frequency; hiệu năng tail latency nên được đo trong benchmark có kiểm soát.

## 41. Test xử lý lỗi commit

Ngoài happy path, cần mô phỏng:

**Commit timeout:** làm network/broker chậm để commitSync timeout hoặc phản hồi không chắc chắn. Xác nhận ứng dụng không đánh dấu record nguồn là “bảo đảm đã commit” chỉ dựa vào side effect.

**Rebalance:** một consumer mất assignment trong lúc xử lý; xác nhận container không cố commit offset như owner cũ ở onPartitionsLost.

**Async callback lỗi:** nếu tự dùng KafkaConsumer.commitAsync, kiểm tra callback ghi lỗi và không retry offset cũ đè lên offset mới.

**Shutdown:** dừng container khi còn record in-flight, xác nhận graceful lifecycle và committed progress phù hợp.

**Transactional read-process-write:** cố ý abort Kafka transaction sau khi gửi output và xác nhận downstream read_committed không nhận output bị abort.

**Database side effect:** cho DB commit thành công nhưng Kafka offset commit thất bại rồi redeliver, xác nhận Inbox/idempotency ngăn double update.

Các test này bảo vệ delivery guarantee, không chỉ xác nhận số liệu giám sát.

## 42. Runbook khi commit latency tăng

Một quy trình điều tra theo thứ tự:

1. **Xác nhận metric:** đơn vị ms/s, metric group, client ID, scrape timestamp và metric source.
2. **Xác định phạm vi:** một pod, một consumer group hay toàn cluster?
3. **Đối chiếu commit-rate:** lượng commit requests có tăng sau deployment/scale không?
4. **Kiểm tra commit failures:** timeout, CommitFailedException, authorization, transaction errors.
5. **Đọc lag/freshness:** sự cố đã ảnh hưởng thời gian xử lý nghiệp vụ chưa?
6. **Đo business processing:** listener và dependency có chậm cùng lúc không?
7. **Kiểm tra consumer group:** rebalance, assignment, max.poll.interval.ms.
8. **Kiểm tra broker coordinator:** CPU, request queue, I/O, replication, throttling.
9. **Kiểm tra network:** RTT, cross-region, packet loss, TLS errors.
10. **Kiểm tra JVM/pod:** GC, CPU throttling, memory pressure.
11. **Kiểm tra cấu hình:** AckMode, syncCommits, commit timeout, max.poll.records, concurrency.
12. **Chọn thay đổi nhỏ có kiểm soát:** tối ưu frequency hoặc xử lý root cause.
13. **Kiểm tra delivery guarantee:** duplicate window, idempotency, DLT và transactions.
14. **Theo dõi sau sửa:** commit latency, commit rate, lag, failures và business SLO.

Không thay đổi `auto.offset.reset` hoặc tự seek bỏ qua record chỉ để giảm lag. Những thao tác đó có thể che mất dữ liệu chưa được xử lý.

## 43. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| Gọi listener duration là commit latency | Listener timer đo phạm vi khác | Dùng consumer coordinator metrics |
| Gọi thời gian ack() là Kafka commit latency | Ack chưa chắc đã gửi commit | Phân biệt AckMode và kết quả commit |
| Chỉ theo dõi average | Không thấy tail spikes | Kết hợp max/failure và histogram nếu có |
| Tính p99 từ avg và max | Không có đủ phân bố dữ liệu | Thu histogram đúng nguồn |
| Đặt syncCommits=false để “xóa” latency | Latency request vẫn tồn tại, lỗi xử lý khác | Đánh giá trade-off và callback |
| Commit từng record không cân nhắc coordinator | Tạo quá nhiều requests | Chọn batching phù hợp |
| Commit batch rất lớn mà không có idempotency | Replay window lớn | Dùng eventId/Inbox hoặc giảm batch |
| Gọi Kafka client commit metrics là transaction commit time | Hai cơ chế khác nhau | Theo dõi producer transaction riêng |
| Chỉ tăng max.poll.interval.ms | Không sửa coordinator chậm | Phân tích commit, processing và broker |
| Restart consumer ngay khi có spike | Gây rebalance và redelivery | Điều tra phạm vi, cooldown |
| Ack/commit trước side effect | Có nguy cơ bỏ qua nghiệp vụ chưa xong | Chỉ commit sau xử lý bền vững |
| Trộn series nhiều client bằng trung bình không trọng số | Che consumer bị lỗi | Drill down theo client/group |
| Không kiểm tra metric unit sau exporter | Alert sai ngưỡng ms/s | Chuẩn hóa đơn vị |
| Coi commit-total là số message xử lý | Một commit có thể bao phủ nhiều record | Theo dõi records consumed/processed riêng |

## 44. Checklist triển khai monitoring

Trước khi dùng commit latency làm chỉ số vận hành, cần có câu trả lời:

- Đang đo offset commit thường hay transaction commit?
- Kafka consumer client metrics có xuất `commit-latency-avg` và `commit-latency-max` không?
- Đơn vị metric đã được xác nhận sau khi qua exporter?
- Có label hợp lý theo application, consumer group, client ID không?
- Có biết AckMode và syncCommits của listener container?
- Commit frequency có liên quan đến max.poll.records và concurrency?
- Có metric commit failures/timeout riêng?
- Có đo listener processing latency và dependency latency?
- Có monitor consumer lag, oldest record age và committed offset progression?
- Có theo dõi rebalances và ConsumerStoppedEvent?
- Có đo producer transaction duration nếu đang dùng Kafka EOS?
- Có chính sách idempotency khi commit thất bại dẫn đến redelivery?
- Có test restart giữa batch, DLT recovery và rebalance?
- Có baseline trước deployment để so sánh?
- Có runbook phân biệt bottleneck tại broker, network hay ứng dụng?

Để cảnh báo có ích, nên kết hợp ít nhất ba chiều: **commit health**, **consumer progress** và **business processing**.

## 45. Kết luận

**Commit latency cho biết Kafka consumer mất bao lâu để hoàn tất yêu cầu ghi nhận offset với group coordinator theo cơ chế metric được dùng.** Đây là chỉ số quan trọng vì một consumer xử lý nghiệp vụ nhanh nhưng commit đồng bộ chậm vẫn có thể bị giới hạn throughput, tăng lag hoặc kéo dài rebalance.

Muốn tối ưu commit latency đúng cách cần phân biệt commitSync và commitAsync, hiểu AckMode, đo commit request metrics tách khỏi listener processing, và không đánh đồng offset commit với Kafka producer transaction hay database commit. Batching và giảm commit frequency có thể cải thiện hiệu năng nhưng mở rộng cửa sổ redelivery; vì vậy phải phối hợp idempotency, DLT/recovery và các phép thử sự cố.

Trong production, không chỉ hỏi “commit mất bao nhiêu mili giây”, mà còn phải hỏi **“offset có tiến an toàn sau khi nghiệp vụ hoàn tất không, consumer có đáp ứng freshness SLO không và khi xảy ra lỗi hệ thống có thể xử lý lại record mà không gây side effect sai không?”** Đó mới là giá trị của việc giám sát commit latency trong Spring Kafka Reliability Operations.
