# Đo latency p50, p95, p99 và tránh kết luận từ giá trị trung bình

## Mục tiêu bài học

Một Kafka pipeline có thể xử lý hàng chục nghìn record mỗi giây nhưng vẫn làm một nhóm người dùng phải chờ rất lâu. Giá trị latency trung bình thường che khuất các request chậm ở đuôi phân phối. Vì vậy, khi đánh giá hiệu năng, cần theo dõi các percentile như p50, p95 và p99, xác định chính xác latency đang được đo ở ranh giới nào, rồi đối chiếu với throughput, error rate và tải hệ thống.

Bài học hướng dẫn cách đọc percentile, chọn cửa sổ và số lượng mẫu, thu thập histogram bằng Micrometer/Prometheus, phân tích latency của producer, broker và consumer, thiết kế benchmark có kiểm soát và tránh những kết luận sai khi tổng hợp số liệu từ nhiều instance.

Sau bài học, người học có thể:

- Giải thích p50, p95, p99 và mối quan hệ với phân phối latency.
- Hiểu vì sao average không mô tả được tail latency.
- Chọn histogram, bucket và cửa sổ đo phù hợp.
- Phân biệt latency ở producer, broker, consumer và end-to-end.
- Instrument thời gian xử lý Kafka bằng Micrometer.
- Truy vấn percentile từ Prometheus histogram.
- Tránh lấy trung bình percentile của nhiều instance.
- Thiết kế benchmark có warm-up, tải ổn định và đủ mẫu.
- Nhận diện coordinated omission và các nguồn sai lệch đo đạc.
- Tối ưu Kafka dựa trên số liệu thay vì chỉ thay cấu hình theo cảm tính.

## 1. Latency và percentile là gì?

Latency là thời gian từ một mốc bắt đầu đến một mốc kết thúc đã được định nghĩa. Ví dụ:

- Producer latency: từ lúc ứng dụng gọi send đến khi callback nhận kết quả.
- Broker request latency: thời gian broker xử lý một request.
- Consumer processing latency: từ lúc handler bắt đầu xử lý record đến khi nghiệp vụ hoàn tất.
- End-to-end latency: từ lúc event được tạo hoặc gửi đến lúc consumer hoàn tất xử lý.

Các con số này không thể thay thế cho nhau. Một pipeline có producer latency thấp vẫn có thể có end-to-end latency cao nếu record phải chờ trong topic hoặc consumer xử lý chậm.

Percentile mô tả vị trí của một giá trị trong phân phối mẫu đã sắp xếp:

| Chỉ số | Cách đọc |
|---|---|
| p50 | 50% mẫu có latency nhỏ hơn hoặc bằng giá trị này; gần với median |
| p95 | 95% mẫu có latency nhỏ hơn hoặc bằng giá trị này; 5% chậm hơn |
| p99 | 99% mẫu có latency nhỏ hơn hoặc bằng giá trị này; 1% chậm hơn |
| p99.9 | 99,9% mẫu có latency nhỏ hơn hoặc bằng giá trị này; 0,1% chậm hơn |
| max | Mẫu chậm nhất trong cửa sổ đo; rất nhạy với một outlier |

Ví dụ p99 = 250 ms nghĩa là trong cửa sổ đo và tập mẫu tương ứng, khoảng 99% lần xử lý hoàn tất trong tối đa 250 ms, còn khoảng 1% chậm hơn. Nó không có nghĩa mọi request đều hoàn tất trong 250 ms.

### 1.1. Một ví dụ cho thấy average che giấu tail

Giả sử có 1.000 lần xử lý với phân phối sau:

| Số mẫu | Latency |
|---:|---:|
| 501 | 10 ms |
| 449 | 100 ms |
| 40 | 500 ms |
| 10 | 2.000 ms |

Theo cách nearest-rank đơn giản:

- p50 nằm ở mẫu thứ 500: 10 ms.
- p95 nằm ở mẫu thứ 950: 100 ms.
- p99 nằm ở mẫu thứ 990: 500 ms.
- max là 2.000 ms.

Average của toàn bộ 1.000 mẫu là 89,91 ms. Nếu chỉ nhìn average, hệ thống có vẻ xử lý một request trong chưa đến 100 ms. Nhưng p99 cho thấy 1% request mất ít nhất khoảng nửa giây và 10 request mất tới 2 giây.

~~~mermaid
xychart-beta
    title "Latency theo percentile trong ví dụ"
    x-axis ["p50", "p95", "p99", "max"]
    y-axis "Milliseconds" 0 --> 2000
    bar [10, 100, 500, 2000]
~~~

Average vẫn hữu ích để tính tổng thời gian tiêu thụ tài nguyên hoặc theo dõi xu hướng tải. Vấn đề xảy ra khi dùng average làm đại diện duy nhất cho trải nghiệm người dùng hoặc SLA.

### 1.2. Median không phải average

Median là giá trị ở giữa phân phối sau khi sắp xếp. Với số mẫu chẵn, cách tính có thể lấy trung bình hai giá trị giữa. Median ít bị một số outlier rất lớn kéo lệch hơn arithmetic mean.

p50 thường được dùng như median, nhưng kết quả chính xác phụ thuộc thuật toán tính quantile và cách xử lý mẫu. Hai hệ thống metrics có thể báo p99 hơi khác nhau nếu dùng thuật toán nội suy hoặc histogram bucket khác nhau.

## 2. Cách tính percentile và số lượng mẫu

Với N mẫu đã sắp xếp tăng dần, nearest-rank percentile p có thể lấy mẫu tại vị trí:

\[
rank = \lceil p \times N \rceil
\]

Trong đó p được biểu diễn từ 0 đến 1. Ví dụ p99 tương ứng p = 0,99.

Đây là cách giải thích trực quan. Thư viện metrics có thể dùng thuật toán quantile khác, nội suy giữa các mẫu hoặc ước lượng từ histogram.

### 2.1. p99 cần đủ mẫu

Percentile cao cần nhiều mẫu để có ý nghĩa:

| Số mẫu trong cửa sổ | Phần đuôi 1% của p99 | Phần đuôi 0,1% của p99.9 |
|---:|---:|---:|
| 100 | 1 mẫu | 0,1 mẫu |
| 1.000 | 10 mẫu | 1 mẫu |
| 10.000 | 100 mẫu | 10 mẫu |
| 100.000 | 1.000 mẫu | 100 mẫu |

Nếu service chỉ xử lý vài chục record trong một phút, p99 theo cửa sổ một phút không ổn định. Một mẫu chậm có thể làm percentile nhảy mạnh. Khi traffic thấp, hãy xem cả sample count, thời gian dài hơn và raw trace/log có kiểm soát.

### 2.2. Cửa sổ đo

Percentile luôn gắn với một tập mẫu và một cửa sổ thời gian. p99 trong 30 giây có thể khác p99 trong 15 phút vì:

- Traffic thay đổi theo giờ.
- Có burst hoặc batch workload.
- Một node gặp GC pause hoặc network spike.
- Deployment tạo ra một giai đoạn warm-up.
- Một partition nóng chỉ xuất hiện trong một phần cửa sổ.

Dashboard nên cho phép so sánh cửa sổ ngắn để phát hiện sự cố và cửa sổ dài để thấy xu hướng. Không so p99 của 1 phút với p99 của 1 giờ như thể chúng là cùng một tập mẫu.

### 2.3. Không trộn các loại latency

Không gộp producer callback latency, fetch latency và business processing latency vào một histogram chỉ vì chúng đều có đơn vị milliseconds. Chúng có điểm bắt đầu/kết thúc khác nhau và chẩn đoán các thành phần khác nhau.

Đặt tên metric theo ranh giới đo, ví dụ:

- kafka.producer.send.duration
- kafka.consumer.fetch.duration
- kafka.consumer.process.duration
- kafka.consumer.commit.duration
- kafka.event.end.to.end.duration

Tên metric nên nhất quán, đơn vị rõ ràng và không chứa ID động.

## 3. Vì sao không thể kết luận từ average?

Average là tổng latency chia cho số mẫu. Một vài mẫu rất chậm có thể làm average tăng, nhưng cũng có thể bị hàng triệu mẫu nhanh che lấp. Average không cho biết tail dài đến đâu hoặc bao nhiêu request vượt một ngưỡng.

Ví dụ hai service có cùng average 100 ms:

| Phân phối | p50 | p95 | p99 | Max |
|---|---:|---:|---:|---:|
| Service A, latency ổn định | 95 ms | 130 ms | 160 ms | 220 ms |
| Service B, nhiều request nhanh và một tail dài | 20 ms | 150 ms | 1.200 ms | 5.000 ms |

Average bằng nhau nhưng trải nghiệm ở tail rất khác.

### 3.1. Average vẫn có vai trò

Average hữu ích khi:

- Tính tổng thời gian xử lý hoặc mức sử dụng tài nguyên.
- So sánh xu hướng tổng thể trong cùng workload.
- Phân tích throughput và capacity.
- Ước lượng thời gian xử lý trung bình khi số mẫu đủ lớn và phân phối ổn định.

Hãy đọc average cùng p50/p95/p99, max, sample count, throughput và error rate. Không loại bỏ average; chỉ tránh dùng nó như số liệu duy nhất.

### 3.2. Tail latency thường tăng khi hệ thống gần bão hòa

Khi CPU, disk, network, connection pool hoặc downstream gần hết capacity, queue bắt đầu tăng. Một request chậm có thể phải chờ các request trước đó, khiến tail latency tăng nhanh hơn average.

Trong Kafka pipeline, tail có thể đến từ:

- Producer chờ buffer memory hoặc broker acknowledgement.
- Broker request queue, disk flush hoặc replica acknowledgement.
- Consumer fetch chờ đủ dữ liệu hoặc broker phản hồi chậm.
- Consumer handler chờ database/HTTP dependency.
- JVM garbage collection, thread scheduling hoặc lock contention.
- Rebalance, partition movement hoặc retry.

Khi p99 tăng mà p50 gần như không đổi, hãy tìm một nhóm nhỏ request/partition/instance đang bị nghẽn thay vì chỉ nhìn toàn hệ thống.

## 4. Xác định ranh giới đo latency trong Kafka

Một event đi qua nhiều giai đoạn:

~~~mermaid
flowchart LR
    A["Event created"] --> B["Producer send()"]
    B --> C["Producer queue / batch"]
    C --> D["Broker receive and append"]
    D --> E["Replication / ACK"]
    E --> F["Consumer fetch"]
    F --> G["Application processing"]
    G --> H["Business side effect committed"]
    H --> I["Offset committed"]
~~~

| Ranh giới | Đo thời gian nào? | Metric phù hợp |
|---|---|---|
| Producer API | send() đến callback | Producer send/callback duration |
| Producer queue | Record chờ batch/buffer | record-queue-time, buffer wait |
| Broker request | Broker xử lý produce/fetch request | Request handler/local/queue latency |
| Replication ACK | Producer chờ acknowledgement theo acks | Producer callback duration và replica health |
| Consumer fetch | Fetch request đến response | fetch-latency |
| Business handler | Handler bắt đầu đến khi side effect xong | Application Timer |
| Offset commit | Commit request đến response | commit-latency |
| End-to-end | Event tạo/append đến business completion | Event timestamp hoặc trace |

Một số thời gian chồng lấn hoặc không cộng trực tiếp được. Producer batch có thể gom nhiều record; consumer fetch có thể trả một batch; application xử lý song song; offset commit có thể diễn ra sau khi nhiều record đã hoàn tất.

Không cộng p99 của từng giai đoạn để suy ra p99 end-to-end. Percentile của tổng hai biến ngẫu nhiên không bằng tổng percentile riêng lẻ. Hãy đo trực tiếp end-to-end nếu cần SLO end-to-end.

## 5. Producer latency

Producer send latency thường được quan sát từ lúc ứng dụng gọi send đến khi callback thành công hoặc thất bại. Thời gian này có thể bao gồm:

- Chờ record được đưa vào batch.
- Chờ buffer memory nếu producer bị backpressure.
- Serialization và compression.
- Network round-trip đến broker.
- Broker xử lý produce request.
- Chờ replication/acknowledgement theo cấu hình acks.
- Retry khi request lỗi hoặc broker leader thay đổi.

### 5.1. Producer metrics thường gặp

Kafka Java producer cung cấp metrics qua JMX. Tên metric có thể khác giữa client version:

| Metric | Ý nghĩa |
|---|---|
| request-latency-avg/max | Latency request phía producer |
| record-queue-time-avg/max | Thời gian record nằm trong producer accumulator/queue |
| record-send-rate | Số record gửi mỗi giây |
| record-send-total | Tổng record đã gửi |
| request-rate | Số request gửi mỗi giây |
| batch-size-avg | Kích thước batch trung bình |
| records-per-request-avg | Số record trung bình mỗi request |
| compression-rate-avg | Tỷ lệ nén quan sát được |
| bufferpool-wait-time-total | Tổng thời gian chờ buffer pool |
| bufferpool-wait-ratio | Tỷ lệ thời gian chờ buffer |
| record-retry-rate | Tốc độ retry record |
| record-error-rate | Tốc độ record lỗi |

Các metric avg/max của Kafka client không tự cung cấp p95/p99. Nếu cần percentile cho producer callback, hãy instrument thời gian callback ở ứng dụng bằng histogram.

### 5.2. Đo callback duration

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;

public class OrderPublisher {

    private final KafkaProducer<String, String> producer;
    private final MeterRegistry registry;

    public OrderPublisher(
            KafkaProducer<String, String> producer,
            MeterRegistry registry) {
        this.producer = producer;
        this.registry = registry;
    }

    public void publish(String key, String payload) {
        Timer.Sample sample = Timer.start(registry);
        ProducerRecord<String, String> record =
            new ProducerRecord<>("orders", key, payload);

        try {
            producer.send(record, (RecordMetadata metadata, Exception error) -> {
                Timer timer = Timer.builder("kafka.producer.callback.duration")
                    .publishPercentileHistogram()
                    .tag("topic", "orders")
                    .tag("result", error == null ? "success" : "error")
                    .register(registry);

                sample.stop(timer);
            });
        } catch (RuntimeException ex) {
            Timer timer = Timer.builder("kafka.producer.callback.duration")
                .publishPercentileHistogram()
                .tag("topic", "orders")
                .tag("result", "error")
                .register(registry);
            sample.stop(timer);
            throw ex;
        }
    }
}
~~~

Đây là ví dụ minh họa. Cần xử lý exception phù hợp với ứng dụng. Callback duration đo từ trước send đến khi callback được gọi; nó bao gồm queue/batch, request, acknowledgement và retry nhưng không đo riêng từng phần. Nhánh catch ghi nhận lỗi ném đồng bộ trước khi callback được đăng ký; callback ghi nhận kết quả trả về bất đồng bộ. Không gọi callback duration là broker processing latency.

Nếu callback thực thi trên producer I/O thread, callback cần ngắn; không thực hiện database write hoặc công việc blocking ở đó.

### 5.3. Những cấu hình ảnh hưởng producer latency

| Cấu hình | Tác động thường gặp |
|---|---|
| linger.ms | Chờ thêm record để tạo batch lớn hơn; có thể tăng latency thấp tải nhưng tăng throughput |
| batch.size | Kích thước batch mục tiêu cho mỗi partition |
| compression.type | Giảm bytes network/disk, đổi lại CPU và thời gian nén/giải nén |
| acks | Mức acknowledgement; ảnh hưởng durability và thời gian chờ |
| enable.idempotence | Bảo vệ retry khỏi duplicate trong phạm vi producer protocol |
| max.in.flight.requests.per.connection | Số request đồng thời; ảnh hưởng throughput và ordering trade-off |
| delivery.timeout.ms | Giới hạn tổng thời gian producer thử gửi một record |
| request.timeout.ms | Timeout cho request broker |
| buffer.memory | Bộ nhớ accumulator; thiếu buffer gây chờ/backpressure |

Không tối ưu latency bằng cách giảm linger hoặc tắt compression một cách máy móc. Đo p50/p95/p99 cùng throughput và bytes trước/sau thay đổi.

## 6. Broker latency và replication

Broker nhận produce/fetch request, đưa request vào queue, xử lý trên request handler, tương tác với log/disk và trả response. Broker latency có thể tăng do:

- Network processor hoặc request handler quá tải.
- Disk I/O hoặc page cache bị nghẽn.
- Replica follower chậm khiến acks=all phải chờ ISR.
- Partition leader mất cân bằng.
- Request batch nhỏ gây overhead cao.
- Broker CPU bị tiêu tốn cho TLS, compression hoặc garbage collection.

Broker metrics thường có average/max hoặc percentile theo request queue/handler tùy version và metric reporter. Không giả định mọi request metric đều có p95/p99.

### 6.1. Phân biệt queue time và processing time

Một request có thể mất nhiều thời gian trước khi broker bắt đầu xử lý. Nếu chỉ đo thời gian handler, bạn có thể bỏ sót thời gian request chờ trong queue.

Quan sát các nhóm:

- RequestQueueTimeMs: thời gian chờ trong request queue.
- LocalTimeMs: thời gian broker xử lý request tại node.
- RemoteTimeMs: thời gian chờ xử lý từ remote replica khi request cần.
- ResponseQueueTimeMs: thời gian chờ trước khi gửi response.
- TotalTimeMs: tổng thời gian theo định nghĩa metric của broker.

Tên và phạm vi metric phụ thuộc Kafka version. Dùng JMX MBean/request type tương ứng và đối chiếu với broker documentation.

### 6.2. acks và durability trade-off

Producer acks=0 không chờ broker acknowledgement; callback latency có thể thấp nhưng ứng dụng không biết chắc broker đã nhận record.

acks=1 chờ leader xác nhận local append theo semantics Kafka; nếu leader lỗi trước khi follower bắt kịp, record có thể mất.

acks=all chờ các replica trong ISR theo cấu hình min.insync.replicas; tăng khả năng chịu lỗi nhưng latency có thể tăng khi follower chậm.

Khi benchmark, phải giữ durability settings giống production. So sánh latency với acks khác nhau mà không ghi rõ durability sẽ dẫn đến kết luận sai.

## 7. Consumer latency

Consumer có ít nhất ba loại thời gian nên đo riêng:

1. Fetch latency: thời gian request fetch.
2. Processing latency: thời gian ứng dụng xử lý record.
3. Commit latency: thời gian lưu committed offset.

Kafka consumer metrics có các chỉ số như fetch-latency-avg/max, records-consumed-rate, bytes-consumed-rate và records-lag-max. Đây chủ yếu là metric client; chúng không tự mô tả thời gian business handler.

### 7.1. Đo processing duration

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.apache.kafka.clients.consumer.ConsumerRecord;

public class OrderHandler {

    private final MeterRegistry registry;
    private final OrderService orderService;

    public OrderHandler(
            MeterRegistry registry,
            OrderService orderService) {
        this.registry = registry;
        this.orderService = orderService;
    }

    public void handle(ConsumerRecord<String, String> record) {
        Timer.Sample sample = Timer.start(registry);
        String result = "success";

        try {
            orderService.process(record.value());
        } catch (RuntimeException ex) {
            result = "error";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("kafka.consumer.process.duration")
                    .publishPercentileHistogram()
                    .tag("topic", record.topic())
                    .tag("result", result)
                    .register(registry)
            );
        }
    }
}
~~~

Timer đo thời gian handler đồng bộ trong ví dụ. Nếu handler chỉ enqueue record vào executor rồi trả về, timer sẽ đo thời gian enqueue chứ không phải thời gian xử lý hoàn tất. Khi xử lý bất đồng bộ, đặt timer quanh công việc thực tế trong worker.

### 7.2. Consumer lag và latency

Lag là khoảng cách offset, không phải latency theo thời gian. Hai group có cùng lag có thể có event age rất khác do producer rate khác nhau.

Để ước lượng tuổi record, có thể dùng timestamp đã được xác định rõ:

- Event-created timestamp do producer gắn.
- Kafka record timestamp theo CreateTime hoặc LogAppendTime.
- Consumer processing timestamp.

Nếu lấy consumer wall clock trừ event timestamp, cần đồng bộ clock giữa producer và consumer. Clock skew có thể làm latency âm hoặc cao giả.

### 7.3. Consumer commit latency

Commit latency đo thời gian gửi và nhận kết quả commit offset. Nó không phải processing latency. Một record có thể xử lý xong nhanh nhưng offset commit chậm; hoặc commit nhanh trong khi business processing vẫn đang chờ.

Nếu ứng dụng commit theo batch, một commit request có thể đại diện nhiều record. Không chia commit latency cho số record để tạo ra “latency từng record”; đó là metric sai nghĩa.

## 8. Đo end-to-end latency

End-to-end latency nên đo từ một mốc event rõ ràng đến một mốc hoàn tất nghiệp vụ rõ ràng. Ví dụ:

~~~text
event_created_at -> order projection committed_at
~~~

Có thể truyền event ID và timestamp trong payload/header để liên kết các bước. Tuy nhiên:

- Timestamp ở producer và consumer có thể dùng clock khác nhau.
- Event có thể được retry hoặc replay, khiến một event ID có nhiều lần xử lý.
- Consumer có thể xử lý song song, nên thứ tự hoàn tất khác thứ tự append.
- Một event có thể đi qua nhiều service và nhiều topic.
- Không ghi payload nhạy cảm vào trace attribute.

Với distributed tracing, truyền trace context qua Kafka headers để liên kết producer span, consumer span và downstream spans. Nếu đo latency bằng timestamp, dùng đồng hồ đã đồng bộ và phân biệt event age với thời gian thực thi handler.

### 8.1. Event age và processing duration

Event age tại consumer:

~~~text
event_age = consumer_start_time - event_created_time
~~~

Processing duration:

~~~text
processing_duration = handler_end_time - handler_start_time
~~~

End-to-end:

~~~text
end_to_end = business_completion_time - event_created_time
~~~

Event age bao gồm thời gian chờ trong Kafka và trước khi handler bắt đầu. Processing duration chỉ đo phần ứng dụng thực thi. End-to-end bao gồm cả chờ và xử lý đến mốc hoàn tất đã chọn.

## 9. Thu percentile bằng Micrometer và Prometheus

Kafka Java client cung cấp nhiều metric avg/max qua JMX. Để có p50/p95/p99 cho business processing hoặc producer callback, ứng dụng cần phát histogram/timer.

### 9.1. Micrometer Timer

Timer ghi nhận count, total time và phân phối duration. Với Prometheus, bật percentile histogram để xuất bucket có thể được tổng hợp giữa nhiều instance.

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

Timer timer = Timer.builder("kafka.consumer.process.duration")
    .description("Kafka record processing duration")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(10),
        Duration.ofMillis(25),
        Duration.ofMillis(50),
        Duration.ofMillis(100),
        Duration.ofMillis(250),
        Duration.ofMillis(500),
        Duration.ofSeconds(1),
        Duration.ofSeconds(2)
    )
    .tag("topic", "orders")
    .register(meterRegistry);
~~~

SLO buckets giúp đo tỷ lệ record nằm dưới các ngưỡng nghiệp vụ. Chọn bucket tập trung quanh mục tiêu latency; bucket quá thưa làm percentile ước lượng kém chính xác ở vùng quan trọng. Prometheus histogram tính quantile bằng nội suy trong bucket chứa quantile. Nếu p99 nằm trong bucket rộng từ 100 ms đến 1 s, dashboard không thể cho biết tail là 110 ms hay 900 ms. Thêm bucket quanh vùng SLO/tail cần quan sát và cân nhắc chi phí số time series.

Có thể cấu hình histogram ở application properties:

~~~properties
management.metrics.distribution.percentiles-histogram.kafka.consumer.process.duration=true
management.metrics.distribution.slo.kafka.consumer.process.duration=10ms,25ms,50ms,100ms,250ms,500ms,1s,2s
~~~

Property binding và tên metric cần được kiểm tra theo Spring Boot/Micrometer version đang dùng. Nếu cấu hình qua Timer.builder, bảo đảm không tạo meter với tag set không nhất quán.

### 9.2. Prometheus histogram

Prometheus histogram xuất các bucket tích lũy, thường có hậu tố _bucket và label le (less than or equal). Nó cũng xuất _count và _sum.

Ví dụ truy vấn p99 theo topic:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, topic) (
    rate(kafka_consumer_process_duration_seconds_bucket[5m])
  )
)
~~~

p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, topic) (
    rate(kafka_consumer_process_duration_seconds_bucket[5m])
  )
)
~~~

p50:

~~~promql
histogram_quantile(
  0.50,
  sum by (le, topic) (
    rate(kafka_consumer_process_duration_seconds_bucket[5m])
  )
)
~~~

Tên metric ví dụ giả định Micrometer Prometheus registry chuyển metric name thành kafka_consumer_process_duration_seconds. Kiểm tra endpoint /actuator/prometheus để xác nhận tên thực tế.

### 9.3. Không lấy trung bình p99 của nhiều instance

Giả sử instance A có 10.000 mẫu với p99 = 100 ms, instance B có 100 mẫu với p99 = 2.000 ms. Trung bình số học hai p99 là 1.050 ms, nhưng con số này không phải p99 của toàn fleet.

Percentile không thể tổng hợp bằng phép cộng hoặc average percentile. Với Prometheus histogram, tổng hợp bucket trước rồi mới tính quantile:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(kafka_consumer_process_duration_seconds_bucket[5m])
  )
)
~~~

Nếu muốn phân biệt topic, giữ label topic trong phép sum. Chỉ giữ label cần thiết; tránh group theo instance nếu mục tiêu là percentile toàn fleet.

### 9.4. Histogram và summary khác nhau

| Loại | Đặc điểm | Có thể tổng hợp giữa instance? |
|---|---|---|
| Histogram | Ghi số mẫu trong các bucket; quantile được tính từ bucket | Có, nếu bucket boundaries giống nhau |
| Summary | Có thể tính quantile phía client trong một cửa sổ | Không thể cộng các quantile để có quantile fleet chính xác |
| Average/count/sum | Tổng và số mẫu | Có thể tổng hợp average có trọng số từ sum/count, nhưng không khôi phục percentile |

Với dashboard toàn cluster, histogram thường phù hợp hơn. Bucket boundaries phải thống nhất giữa các instance và version triển khai.

## 10. Prometheus SLO: percentile và tỷ lệ đáp ứng ngưỡng

Percentile hữu ích để đọc tail, nhưng SLO có thể được định nghĩa trực tiếp là tỷ lệ event hoàn tất dưới một ngưỡng.

Ví dụ: 99% record processing phải hoàn tất trong 100 ms. Với bucket 100 ms:

~~~promql
sum(
  rate(kafka_consumer_process_duration_seconds_bucket{le="0.1"}[5m])
)
/
sum(
  rate(kafka_consumer_process_duration_seconds_count[5m])
)
~~~

Kết quả là tỷ lệ mẫu có duration nhỏ hơn hoặc bằng 100 ms trong cửa sổ. Kiểm tra tên bucket và đơn vị của metric thực tế; Prometheus histogram bucket là tích lũy.

Percentile p99 = 100 ms gần với việc 99% mẫu nằm dưới 100 ms trong cùng phân phối/cửa sổ, nhưng SLO dựa trên tỷ lệ good events giúp biểu diễn ngưỡng và error budget rõ ràng hơn.

Không đặt SLO dựa trên một percentile ở cửa sổ quá ngắn khi số mẫu thấp. Cần xác định:

- Event nào thuộc denominator.
- Mốc bắt đầu/kết thúc của latency.
- Cách xử lý retry, duplicate và replay.
- Cửa sổ đo và lượng traffic tối thiểu.
- Ngưỡng cảnh báo và error budget.

## 11. Benchmark latency đúng cách

Benchmark chỉ có ý nghĩa khi tải, dữ liệu, cấu hình và môi trường được kiểm soát. Thay đổi nhiều tham số cùng lúc khiến không thể xác định nguyên nhân cải thiện hoặc suy giảm.

### 11.1. Chuẩn bị baseline

Ghi lại:

- Kafka broker/client version.
- Số broker và replication factor.
- Topic partition count và replication settings.
- Producer acks, idempotence, batch size, linger và compression.
- Consumer group size, fetch settings, max.poll.records và commit strategy.
- Message size distribution và key distribution.
- Producer rate, consumer rate và concurrency.
- CPU, heap/GC, disk I/O và network.
- Security/TLS/SASL và quota nếu production có sử dụng.

Benchmark với acks=0 hoặc replication factor 1 không thể so trực tiếp với production dùng acks=all và replication factor 3.

### 11.2. Warm-up và steady state

Một quy trình cơ bản:

1. Khởi động broker, producer và consumer.
2. Gửi tải warm-up để JVM JIT, connection và cache ổn định.
3. Chờ consumer group hoàn tất assignment và lag ban đầu giảm.
4. Phát tải ổn định trong cửa sổ đủ dài.
5. Ghi histogram, throughput, error rate, lag và resource utilization.
6. Lặp lại ít nhất vài lần với cùng điều kiện.
7. So sánh median của các lần chạy và phân phối của từng lần, không chỉ một con số.

Không lấy các giây đầu startup làm kết quả steady-state. Đồng thời không bỏ qua startup latency nếu SLA thực tế yêu cầu service sẵn sàng ngay sau deploy.

### 11.3. Open-loop và closed-loop load

Closed-loop load generator gửi request tiếp theo sau khi request trước hoàn tất. Khi hệ thống chậm, generator tự giảm tốc độ gửi; nó có thể che giấu tail latency vì không tiếp tục tạo request trong lúc hệ thống đang nghẽn.

Open-loop load generator phát request theo lịch hoặc arrival rate đã định trước, độc lập với thời gian hoàn tất request trước. Cách này giúp quan sát hệ thống dưới tải đến ổn định và giảm coordinated omission.

Coordinated omission xảy ra khi benchmark không ghi nhận những request lẽ ra được gửi trong lúc hệ thống bị pause/chậm. Kết quả latency có thể đẹp giả tạo vì chính load generator cũng chờ hệ thống.

### 11.4. Đo đủ mẫu cho p99

Nếu muốn p99 ổn định, cần đủ số mẫu trong mỗi cửa sổ. Với 1.000 mẫu, phần đuôi 1% chỉ có khoảng 10 mẫu. Với 100.000 mẫu, phần đuôi có khoảng 1.000 mẫu.

Không kéo dài cửa sổ quá mức đến nỗi trộn nhiều chế độ tải khác nhau. Chọn cửa sổ vừa đủ mẫu và giữ workload ổn định trong cửa sổ đó.

### 11.5. Báo cáo benchmark

Một báo cáo nên có:

| Nhóm | Chỉ số |
|---|---|
| Load | Arrival rate, payload size, key distribution |
| Throughput | Records/s, MB/s, processed records/s |
| Latency | p50, p95, p99, p99.9, max |
| Errors | Produce failures, processing errors, retries |
| Backlog | Lag max, lag sum, oldest event age |
| Commit | Commit rate, latency, failures |
| Rebalance | Count, rate, total time |
| Resources | CPU, heap, GC pause, disk, network |
| Durability | acks, min ISR, replication factor, idempotence |

Luôn ghi rõ latency đo từ mốc nào đến mốc nào và percentile được tính từ histogram nào.

## 12. Coordinated omission và sai lệch đo đạc

Ngoài coordinated omission, benchmark Kafka có thể sai lệch bởi:

- Producer gửi theo batch nhưng benchmark chỉ ghi thời điểm gọi send, không ghi callback.
- Consumer fetch batch rồi xử lý tuần tự nhưng chỉ đo thời gian poll.
- Clock giữa producer và consumer không đồng bộ.
- Chỉ đo các request thành công và bỏ qua timeout/error.
- Histogram reset khi process restart nhưng dashboard vẫn nối time series.
- Lấy percentile từ số mẫu quá ít.
- Tính trung bình p99 của nhiều instance.
- Gộp latency của các topic có payload và SLA khác nhau.
- Benchmark một partition rồi suy ra throughput của toàn cluster.
- Warm-up, GC hoặc disk cache khác với workload production.

### 12.1. Đo cả success và error

Latency của request thất bại cũng có ý nghĩa. Một request timeout sau 30 giây không được bỏ khỏi báo cáo chỉ vì không có callback success. Nên theo dõi:

- Success latency.
- Failure/timeout count.
- Retry count.
- Time to failure nếu có thể đo.

Không gán duration bằng 0 cho lỗi vì sẽ làm percentile đẹp giả tạo. Có thể tách histogram theo result=success/error và báo error rate riêng.

### 12.2. Clock monotonic và wall clock

Đo duration trong một process nên dùng monotonic clock như System.nanoTime() hoặc Timer của Micrometer, không dùng wall clock có thể bị điều chỉnh NTP.

Đo event age giữa hai host cần wall clock được đồng bộ và phải tính đến clock skew. Distributed trace giúp liên kết span nhưng không loại bỏ hoàn toàn vấn đề clock synchronization.

## 13. Diễn giải các mẫu hình latency

| Quan sát | Khả năng | Cần kiểm tra |
|---|---|---|
| p50, p95, p99 cùng tăng | Toàn hệ thống chậm hoặc tải tăng | CPU, disk, network, queue, throughput |
| p50 ổn định, p99 tăng | Tail do một số partition, node hoặc dependency | Per-partition/instance histogram, GC, retries |
| Producer callback p99 tăng, broker request latency ổn định | Chờ batch, buffer hoặc client queue | record-queue-time, bufferpool wait, linger |
| Producer và broker latency cùng tăng | Broker/network/replication | Request queue, disk, ISR, network |
| Fetch latency thấp, processing p99 cao | Business handler/downstream | DB, HTTP, thread pool, lock |
| Processing p50 thấp, p99 cao | Một nhóm record đặc biệt chậm | Payload size, key skew, retry, downstream |
| Commit p99 cao nhưng processing ổn định | Coordinator/commit path | Commit rate, coordinator queue, rebalance |
| p99 tăng cùng rebalance rate | Group không ổn định | Poll interval, heartbeat, deployment |
| Lag tăng nhưng processing p99 thấp | Producer ingress lớn hơn capacity hoặc partition skew | Producer rate, consumer count, partition assignment |
| p99 thấp nhưng error rate cao | Chỉ đo success hoặc lỗi bị bỏ khỏi histogram | Failure count, timeout, callback errors |

Đây là các giả thuyết chẩn đoán, không phải kết luận tự động. Xác minh bằng metrics ở đúng ranh giới và log/trace có tương quan.

## 14. Tối ưu dựa trên percentile

### 14.1. Nếu producer tail latency cao

- Kiểm tra record-queue-time và bufferpool wait.
- Kiểm tra batch-size và linger.ms.
- Đo compression CPU và network bytes.
- Kiểm tra broker request latency và ISR.
- Xem retry/error rate và leader changes.
- Chọn acks theo durability requirement, không chỉ latency.

### 14.2. Nếu broker tail latency cao

- Kiểm tra RequestQueueTimeMs, LocalTimeMs và ResponseQueueTimeMs.
- Kiểm tra disk I/O, page cache và filesystem.
- Kiểm tra network processor/request handler idle ratio.
- Kiểm tra partition leader distribution.
- Kiểm tra replica lag, ISR shrink/expand và min ISR.
- Đánh giá compression/TLS CPU cost.

### 14.3. Nếu consumer processing tail latency cao

- Đo handler duration riêng với fetch và commit.
- Phân tích payload size và key/partition skew.
- Kiểm tra downstream p95/p99.
- Giới hạn queue và concurrency để tránh tạo backlog trong memory.
- Tránh blocking call trong consumer thread nếu không cần.
- Đảm bảo retry không làm một số record bị xử lý lặp vô hạn.

### 14.4. Thay đổi một biến mỗi lần

Khi thử tuning:

1. Chụp baseline.
2. Chọn một giả thuyết và một cấu hình cần thay đổi.
3. Giữ nguyên workload và các điều kiện còn lại.
4. Chạy lại warm-up và steady-state.
5. So p50/p95/p99, throughput, error rate, lag và resource.
6. Giữ thay đổi chỉ khi cải thiện mục tiêu mà không vi phạm durability/SLO khác.

Không tối ưu p99 bằng cách làm throughput giảm mạnh nếu workload cần throughput. Performance luôn là bài toán cân bằng giữa latency, throughput, durability, cost và fairness.

## 15. Dashboard và alert cho percentile

Một dashboard hiệu quả nên tách theo ranh giới:

| Dashboard | Panels |
|---|---|
| Producer | Callback p50/p95/p99, record queue time, buffer wait, send rate, retries |
| Broker | Produce/fetch request queue/local/response time, disk/network, ISR |
| Consumer | Processing p50/p95/p99, fetch latency, lag, commit latency, rebalance |
| End-to-end | Event age p50/p95/p99, good-event ratio, error rate |
| Benchmark | Arrival rate, throughput, percentiles, resource utilization, test run ID |

Alert nên gắn với SLO hoặc baseline:

- p99 business processing vượt ngưỡng trong nhiều cửa sổ.
- Tỷ lệ event hoàn tất dưới SLA giảm dưới mục tiêu.
- p99 tăng mạnh so với baseline cùng khung giờ.
- Error/timeout rate tăng dù success latency ổn định.
- Lag và event age cùng tăng.
- Producer buffer wait hoặc retry tăng.
- Consumer processing p99 tăng cùng queue depth.

Không alert từ một mẫu p99 khi traffic thấp. Dùng sample count hoặc request rate làm điều kiện tối thiểu để tránh cảnh báo nhiễu.

## 16. Bài tập thực hành

### Bài tập 1: Chứng minh average che giấu tail

1. Tạo 1.000 duration mẫu theo phân phối: 500 mẫu 10 ms, 450 mẫu 100 ms, 40 mẫu 500 ms và 10 mẫu 2.000 ms.
2. Tính average, p50, p95, p99 và max.
3. Thay đổi 10 mẫu chậm nhất thành 5.000 ms.
4. So sánh mức thay đổi của average và p99.
5. Giải thích vì sao average không đủ làm SLA.

### Bài tập 2: Instrument consumer handler

1. Tạo Timer cho kafka.consumer.process.duration.
2. Bật publishPercentileHistogram.
3. Thêm tag topic và result với cardinality thấp.
4. Gửi record có payload nhỏ và lớn.
5. Quan sát p50/p95/p99 trên Prometheus/Grafana.

### Bài tập 3: So sánh fetch và processing latency

1. Thu thập fetch-latency-avg/max của Kafka client.
2. Thu thập processing Timer của handler.
3. Tạo downstream delay có kiểm soát.
4. Quan sát processing p99 thay đổi trong khi fetch latency ổn định.
5. Khôi phục downstream và xác minh percentile trở lại baseline.

### Bài tập 4: So sánh producer batching

1. Chạy baseline với linger.ms thấp.
2. Chạy lại với linger.ms cao hơn.
3. Giữ nguyên arrival rate, payload và durability.
4. So callback p50/p95/p99, batch-size, throughput và bytes/s.
5. Chọn cấu hình phù hợp với SLA.

### Bài tập 5: Histogram aggregation

1. Chạy ít nhất hai consumer instances.
2. Thu histogram trên từng instance.
3. Query p99 từng instance.
4. Query p99 toàn fleet bằng cách sum bucket theo le.
5. So sánh với average của hai p99 và giải thích vì sao phép tính đó sai.

### Bài tập 6: Benchmark open-loop

1. Chọn arrival rate cố định.
2. Warm-up trước khi đo.
3. Chạy steady-state đủ lâu để có số mẫu lớn.
4. Ghi p50/p95/p99, throughput, errors, lag và resource.
5. Lặp lại nhiều lần và so sánh kết quả.
6. Thử closed-loop để quan sát nguy cơ coordinated omission.

## 17. Câu hỏi tự kiểm tra

1. p50, p95 và p99 biểu diễn điều gì?
2. Vì sao hai hệ thống có cùng average nhưng tail latency khác nhau?
3. Cần bao nhiêu mẫu để p99 có ý nghĩa hơn?
4. Vì sao không cộng p99 producer, broker và consumer để ra p99 end-to-end?
5. Producer callback latency bao gồm những giai đoạn nào?
6. Kafka native request-latency-avg/max có cung cấp p95/p99 không?
7. Vì sao consumer fetch latency khác business processing latency?
8. Event age khác processing duration như thế nào?
9. Vì sao không lấy trung bình p99 của nhiều instance?
10. Histogram khác summary ở khả năng aggregation ra sao?
11. Prometheus histogram_quantile sử dụng bucket như thế nào?
12. Coordinated omission làm benchmark sai lệch ra sao?
13. Vì sao cần warm-up trước khi đo steady-state?
14. Khi nào p99 tăng nhưng p50 không đổi?
15. Vì sao benchmark phải giữ nguyên durability settings như production?
16. Khi nào nên dùng open-loop load generator?
17. Vì sao cần theo dõi cả latency, throughput, lag và error rate?

## Tài liệu tham khảo

- [Apache Kafka 4.4 – Monitoring](https://kafka.apache.org/44/operations/monitoring/)
- [Apache Kafka 4.4 – Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Apache Kafka 4.4 – Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 – Producer Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Prometheus – Histograms and summaries](https://prometheus.io/docs/practices/histograms/)
- [Prometheus – Querying histograms](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile)

Percentile chỉ có ý nghĩa khi biết rõ mẫu nào được đo, đo từ đâu đến đâu và trong cửa sổ nào. p50 mô tả phần giữa, p95/p99 phơi bày tail; histogram giúp tổng hợp phân phối giữa nhiều instance. Kết hợp các percentile với throughput, error rate, lag và tài nguyên hệ thống sẽ giúp tối ưu Kafka dựa trên bằng chứng thay vì kết luận từ một giá trị trung bình.
