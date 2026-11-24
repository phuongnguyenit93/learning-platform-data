# Theo dõi Kafka consumer lag, RabbitMQ queue depth và DLQ

Một ứng dụng Spring Cloud Stream có thể vẫn khởi động bình thường trong khi message bị tồn đọng ở broker. HTTP health endpoint trả về UP không chứng minh consumer đang xử lý kịp tốc độ phát sinh dữ liệu. Muốn vận hành pipeline sự kiện, cần quan sát cả ứng dụng lẫn trạng thái queue/partition của broker.

Ba tín hiệu quan trọng của bài học này là Kafka consumer lag, RabbitMQ queue depth và dead-letter queue (DLQ). Kafka lag cho biết consumer group còn cách cuối log bao nhiêu record. RabbitMQ queue depth cho biết có bao nhiêu message đang chờ hoặc đã giao nhưng chưa được xác nhận. DLQ cho biết message đã rời luồng xử lý bình thường do lỗi, hết TTL hoặc chính sách dead-letter. Các số liệu này cần được đọc cùng tốc độ publish/consume, tuổi message, số consumer, lỗi xử lý và tài nguyên broker.

Spring Cloud Stream cung cấp binding và binder cho Kafka, RabbitMQ và Pulsar; Micrometer/Actuator giúp xuất metrics của ứng dụng, còn Prometheus và Grafana có thể thu thập và hiển thị metrics broker. Bài học tập trung vào cách định nghĩa, thu thập, diễn giải, cảnh báo và xử lý các tín hiệu này trong production.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích Kafka consumer lag theo consumer group, topic và partition.
- Phân biệt committed offset, log end offset và số record chưa tiêu thụ.
- Dùng Kafka CLI và metrics để tìm partition gây lag.
- Phân biệt RabbitMQ messages_ready, messages_unacked và tổng queue depth.
- Theo dõi consumer count, consumer capacity và tốc độ message.
- Giám sát DLQ, tuổi message và tỷ lệ dead-letter.
- Xuất metrics Spring Cloud Stream qua Micrometer, Actuator và Prometheus.
- Thiết kế dashboard và alert dựa trên backlog, tốc độ xử lý và SLA.
- Tránh cardinality cao và các cảnh báo gây nhiễu.
- Thực hiện runbook khi Kafka lag hoặc RabbitMQ queue/DLQ tăng.

## 1. Observability của một pipeline sự kiện

~~~text
Producer -> Broker -> Consumer -> Xử lý nghiệp vụ -> Output broker
                |          |
                |          +-- retry / error / DLQ
                +-- lag / queue depth / broker health
~~~

Mỗi lớp trả lời một câu hỏi khác nhau:

| Lớp | Câu hỏi | Tín hiệu |
|---|---|---|
| Broker | Message đang nằm ở đâu? | Kafka lag, RabbitMQ queue depth, DLQ depth |
| Consumer | Có consumer hoạt động và xử lý kịp không? | Consumer count, poll, ack, processing rate |
| Ứng dụng | Handler có lỗi hoặc chậm không? | Error rate, processing duration, retry count |
| Hạ tầng | Broker và ứng dụng có thiếu tài nguyên không? | CPU, memory, disk, network, file descriptors |
| Nghiệp vụ | Sự kiện có đến đích trong thời hạn không? | End-to-end age, success rate, event loss |

Không nên dựa vào một số đo duy nhất. Queue depth cao có thể bình thường trong giờ cao điểm nếu consumer đang rút backlog nhanh. Ngược lại, queue depth nhỏ nhưng message cũ nhiều giờ có thể là dấu hiệu một partition hoặc routing key bị kẹt.

### 1.1. Metrics, logs và traces

- **Metrics** là số liệu tổng hợp theo thời gian, thích hợp để phát hiện xu hướng và cảnh báo.
- **Logs** ghi lại sự kiện cụ thể như exception, rebalance, publish failure hoặc dead-letter.
- **Traces** liên kết các bước xử lý của một event qua nhiều service và broker.

Dùng metrics để phát hiện bất thường, sau đó dùng trace và log có correlation ID/event ID để tìm nguyên nhân. Không đưa event ID, order ID, email hoặc payload vào metric label vì mỗi giá trị có thể tạo một time series mới.

## 2. Kafka consumer lag là gì?

Kafka lưu record trong từng partition. Consumer group đọc các partition đó và commit offset để ghi nhận vị trí đã xử lý. Consumer lag là khoảng cách giữa vị trí cuối log và offset đã commit của consumer group.

Với một partition:

~~~text
Log end offset (LEO)             = 1,250
Committed offset                 = 1,190
Consumer lag                     = 1,250 - 1,190 = 60 records
~~~

Committed offset thường biểu thị vị trí kế tiếp mà consumer sẽ đọc, vì vậy công thức trên là số offset chưa được commit tới cuối log theo cách tính phổ biến. Công cụ exporter có thể có quy ước riêng; hãy kiểm tra tài liệu metric trước khi so sánh các hệ thống.

Đây là khoảng cách offset, không phải lúc nào cũng bằng chính xác số record ứng dụng sẽ nhận. Topic compacted có thể có offset đã bị loại bỏ; transactional consumer dùng isolation level read_committed có thể chỉ đọc tới Last Stable Offset (LSO), thấp hơn Log End Offset khi còn transaction chưa hoàn tất. Khi điều tra chênh lệch, xác minh exporter đang so committed offset với LEO hay LSO và hiểu semantics của topic.

### 2.1. Lag phải được xem theo group và partition

Kafka lag không phải một số duy nhất cho toàn cluster. Cần biết consumer group nào bị lag, topic nào có backlog, partition nào lớn nhất và consumer nào đang được gán partition đó.

| Topic | Partition | Committed offset | Log end offset | Lag |
|---|---:|---:|---:|---:|
| orders | 0 | 10.000 | 10.020 | 20 |
| orders | 1 | 8.100 | 8.900 | 800 |
| orders | 2 | 9.500 | 9.510 | 10 |
| orders | 3 | 7.000 | 7.005 | 5 |
| **Tổng** | | | | **835** |

Tổng lag là 835 record, nhưng partition 1 chiếm phần lớn backlog. Nếu chỉ nhìn tổng, có thể bỏ lỡ hiện tượng phân bố key lệch, một consumer chậm hoặc lỗi chỉ xảy ra với một nhóm message.

### 2.2. Lag là số record, không phải thời gian chờ

Lag bằng 10.000 record không tự cho biết người dùng phải chờ bao lâu. Nếu consumer xử lý 20.000 record/giây, backlog có thể được xóa nhanh. Nếu consumer chỉ xử lý 10 record/giây, cùng backlog có thể mất nhiều phút.

\[
\text{Drain time} \approx
\frac{\text{Backlog}}{\text{Consume rate} - \text{Ingress rate}}
\]

Công thức chỉ có ý nghĩa khi tốc độ consume lớn hơn tốc độ ingress. Nếu ingress rate lớn hơn hoặc bằng consume rate, backlog không thể giảm về 0 khi tải tiếp tục duy trì.

Vì vậy, theo dõi đồng thời lag, ingress rate, consume rate và tuổi của record. Với SLA theo thời gian, event age thường có ý nghĩa vận hành trực tiếp hơn số offset.

### 2.3. Các nguyên nhân thường gặp

- Producer tăng tốc độ phát message.
- Consumer xử lý nghiệp vụ chậm hoặc gọi dịch vụ phụ thuộc bị timeout.
- Consumer gặp exception và retry kéo dài.
- Một partition có key nóng hoặc message lớn.
- Consumer liên tục rebalance do restart hoặc mất heartbeat.
- Số partition hoặc số consumer không đủ cho mức song song cần thiết.
- Consumer bị chặn bởi database connection pool, thread pool hoặc giới hạn downstream.
- Deserialization lỗi khiến một record không thể đi qua handler bình thường.

## 3. Đo Kafka lag và kiểm tra consumer group

### 3.1. Dùng Kafka command-line tools

Lệnh sau hiển thị offset và lag theo partition:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group order-bridge
~~~

Kết quả thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| GROUP | Consumer group |
| TOPIC | Topic đang được tiêu thụ |
| PARTITION | Partition |
| CURRENT-OFFSET | Offset đã commit |
| LOG-END-OFFSET | Offset cuối log |
| LAG | Khoảng cách offset |
| CONSUMER-ID | Consumer đang nhận partition |
| HOST | Host của consumer |
| CLIENT-ID | Client ID |

Để xem trạng thái group và thành viên, dùng các tùy chọn `--state` và `--members` nếu phiên bản Kafka CLI hỗ trợ:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group order-bridge \
  --state

kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.net:9092 \
  --describe \
  --group order-bridge \
  --members
~~~

Tên script có thể là `kafka-consumer-groups.sh` trên Linux hoặc `kafka-consumer-groups.bat` trên Windows. Hãy dùng script thuộc đúng phiên bản Kafka client được cài.

### 3.2. Đọc lag theo partition

Khi một partition có lag vượt trội:

1. Xác định consumer đang sở hữu partition đó.
2. Kiểm tra processing time và error rate của consumer.
3. Kiểm tra key distribution và message size.
4. Kiểm tra rebalance hoặc thay đổi assignment.
5. Xem downstream dependency có bị chậm không.

Nếu tất cả partition cùng tăng lag, có thể producer đang vượt năng lực toàn bộ consumer group hoặc downstream đang gặp sự cố chung. Nếu chỉ một partition tăng, hãy kiểm tra key skew, record lỗi và consumer cụ thể.

### 3.3. Offset lag và event age

Offset lag không phản ánh trực tiếp tuổi message. Một partition có thể có 500 record mới phát trong một giây, trong khi một partition khác có 50 record bị kẹt từ một giờ trước.

Để đo event age:

- Đưa timestamp nghiệp vụ hoặc timestamp phát sinh vào event envelope.
- Ghi nhận thời điểm consumer bắt đầu xử lý.
- Tạo histogram cho độ trễ từ occurredAt tới processing time.
- Nếu cần tuổi record chưa tiêu thụ, dùng exporter/consumer kiểm tra có kiểm soát hoặc metric riêng; không giả định broker offset tự cung cấp tuổi từng record.

## 4. Kafka metrics trong Spring Cloud Stream

Kafka binder có metric Micrometer dành cho consumer lag:

`spring.cloud.stream.binder.kafka.offset`

Metric này phản ánh số message chưa được tiêu thụ theo topic và consumer group; tags mang thông tin group, topic và lag. Binder tạo `KafkaBinderMetrics` khi Micrometer có trên classpath và ứng dụng không cung cấp bean thay thế.

Các thuộc tính điều khiển việc tính offset lag gồm:

| Property | Tác dụng |
|---|---|
| `spring.cloud.stream.kafka.binder.metrics.defaultOffsetLagMetricsEnabled` | Khi true, lag được tính khi metric được truy cập; khi false dùng giá trị tính định kỳ |
| `spring.cloud.stream.kafka.binder.metrics.offsetLagMetricsInterval` | Khoảng thời gian tính lag định kỳ; tài liệu binder hiện hành mô tả mặc định 60 giây |

Ví dụ cấu hình dạng properties:

~~~properties
spring.cloud.stream.kafka.binder.metrics.defaultOffsetLagMetricsEnabled=true
spring.cloud.stream.kafka.binder.metrics.offsetLagMetricsInterval=60
~~~

Việc tính lag có thể cần truy vấn Kafka metadata và consumer group offsets. Nếu có nhiều topic/partition hoặc nhiều group, hãy đánh giá chi phí thu thập và chọn interval phù hợp.

### 4.1. Kafka client metrics

Ngoài lag, theo dõi các metric của consumer client:

- `records-consumed-rate` và `records-consumed-total`: tốc độ và tổng record được consume.
- `records-lag-max`: lag lớn nhất theo partition ở một số client metric group.
- `fetch-latency-avg` và `fetch-rate`: độ trễ và tốc độ fetch.
- `commit-latency-avg` và `commit-rate`: độ trễ và tần suất commit.
- `time-between-poll-avg` và `last-poll-seconds-ago`: nhịp poll.
- `assigned-partitions`: số partition được gán cho consumer.
- Rebalance và heartbeat metrics: dấu hiệu group membership không ổn định.

Tên metric JMX/Micrometer có thể khác giữa Kafka client và exporter. Không copy tên từ một phiên bản cũ mà chưa kiểm tra registry thực tế.

### 4.2. Micrometer và Actuator

Thêm Spring Boot Actuator và registry Prometheus tương ứng với phiên bản Spring Boot của dự án. Ví dụ dependency Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Cấu hình endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true
~~~

Sau khi ứng dụng khởi động:

- `/actuator/health` cung cấp trạng thái health.
- `/actuator/metrics` liệt kê các metric Micrometer.
- `/actuator/metrics/spring.cloud.stream.binder.kafka.offset` cho phép xem metric binder nếu tên metric được expose đúng trong registry.
- `/actuator/prometheus` xuất metrics theo định dạng Prometheus khi registry được cấu hình.

Không expose mọi Actuator endpoint ra Internet. Giới hạn endpoint bằng network policy, authentication và management port riêng khi cần.

### 4.3. Binder observation và tracing

Kafka binder có thuộc tính `spring.cloud.stream.kafka.binder.enableObservation` để bật Micrometer Observation cho các binding của binder. Observation/tracing giúp liên kết hoạt động producer/consumer; nó không thay thế metric lag của consumer group.

Hãy kiểm tra support của phiên bản binder và tracing bridge đang dùng. Không giả định mọi header hoặc trace context đều tự truyền qua mọi broker và mọi phiên bản.

## 5. RabbitMQ queue depth là gì?

RabbitMQ hiển thị số message trong queue theo hai trạng thái chính:

- **Ready**: message đang chờ được giao cho consumer.
- **Unacknowledged (unacked)**: message đã giao cho consumer nhưng consumer chưa ack.

Tổng queue depth:

\[
\text{messages} =
\text{messages\_ready} +
\text{messages\_unacknowledged}
\]

Ví dụ:

| Trạng thái | Số message |
|---|---:|
| messages_ready | 1.200 |
| messages_unacknowledged | 300 |
| Tổng messages | 1.500 |

Ready cao thường chỉ ra tốc độ publish lớn hơn tốc độ giao/consume. Unacked cao có thể cho biết consumer đã nhận nhiều message nhưng đang xử lý chậm, prefetch lớn, ack bị trì hoãn hoặc consumer bị treo.

### 5.1. Không chỉ nhìn tổng queue depth

| Tình huống | Diễn giải cần kiểm tra |
|---|---|
| Ready tăng, unacked thấp | Thiếu consumer, consumer không nhận được message hoặc throughput thấp |
| Ready thấp, unacked tăng | Consumer đang giữ message nhưng xử lý/ack chậm |
| Ready và unacked cùng tăng | Tải đầu vào vượt năng lực xử lý hoặc downstream bị nghẽn |
| Ready giảm đều, unacked ổn định | Consumer đang rút backlog |
| Queue depth thấp nhưng message age cao | Có thể message bị kẹt ở một queue/consumer hoặc lưu lượng rất thấp |
| Consumer count bằng 0, ready lớn hơn 0 | Queue không có worker xử lý |

RabbitMQ queue depth là trạng thái tại thời điểm scrape. Muốn biết backlog có đang tăng hay không, hãy xem chuỗi thời gian và tốc độ publish/deliver/ack.

## 6. RabbitMQ metrics và Prometheus

RabbitMQ cung cấp plugin Prometheus tích hợp:

~~~bash
rabbitmq-plugins enable rabbitmq_prometheus
~~~

Plugin thường expose metrics tại cổng 15692, đường dẫn `/metrics`. Kiểm tra cấu hình listener và network của cluster trước khi đưa vào Prometheus.

Ví dụ Prometheus scrape config:

~~~yaml
scrape_configs:
  - job_name: rabbitmq
    static_configs:
      - targets:
          - rabbitmq-1:15692
          - rabbitmq-2:15692
          - rabbitmq-3:15692
~~~

### 6.1. Các metric queue quan trọng

RabbitMQ 4.4 cung cấp các metric chi tiết theo queue:

| Metric | Ý nghĩa |
|---|---|
| `rabbitmq_detailed_queue_messages_ready` | Message sẵn sàng giao |
| `rabbitmq_detailed_queue_messages_unacked` | Message đã giao nhưng chưa ack |
| `rabbitmq_detailed_queue_messages` | Tổng ready và unacked |
| `rabbitmq_detailed_queue_consumers` | Số consumer của queue |
| `rabbitmq_detailed_queue_consumer_capacity` | Consumer capacity |
| `rabbitmq_detailed_queue_consumer_utilisation` | Tên metric tương đương consumer capacity |
| `rabbitmq_detailed_queue_messages_delivered_ack_total` | Tổng message giao ở chế độ manual ack |
| `rabbitmq_detailed_queue_messages_acked_total` | Tổng message được consumer ack |
| `rabbitmq_detailed_queue_messages_redelivered_total` | Tổng message được giao lại |

Metric names và metric family phụ thuộc RabbitMQ version cùng cấu hình Prometheus plugin. Các metric chi tiết theo từng queue có chi phí thu thập cao hơn nhóm coarse metrics; chỉ bật các nhóm cần thiết.

### 6.2. Consumer capacity

Consumer capacity thể hiện tỷ lệ thời gian queue có thể giao message ngay khi consumer sẵn sàng. Giá trị thấp có thể do:

- Không có consumer.
- Consumer bị giới hạn tốc độ hoặc prefetch.
- Consumer xử lý message lâu.
- Queue thường xuyên rỗng do producer phát chậm.

Consumer capacity thấp không tự động có nghĩa consumer lỗi. Hãy xem cùng queue depth và publish/delivery rate. Queue rỗng thường có capacity thấp vì không có message để giao.

### 6.3. RabbitMQ Management UI và HTTP API

Management UI và HTTP API hữu ích để điều tra nhanh. Endpoint:

~~~text
GET /api/queues/{vhost}/{queue}
~~~

có thể trả về các trường như `messages`, `messages_ready`, `messages_unacknowledged`, số consumer và thống kê message. Management API phù hợp với thao tác chẩn đoán, còn Prometheus phù hợp với lưu trữ chuỗi thời gian và cảnh báo dài hạn.

CLI để xem queue:

~~~bash
rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers
~~~

Thay `/` bằng virtual host đúng môi trường. Tùy phiên bản, có thể thêm trường `messages` hoặc các trường queue khác được hỗ trợ.

## 7. Theo dõi DLQ và dead-letter rate

Dead-letter queue chứa message bị chuyển khỏi queue xử lý bình thường do:

- Consumer reject/nack với requeue=false.
- Message hết TTL.
- Queue vượt giới hạn hoặc overflow policy.
- Quorum queue vượt delivery limit.

DLQ có thể được tạo theo consumer group hoặc theo topology của ứng dụng. Đặt tên queue rõ ràng để dễ lọc và xác định owner, ví dụ `orders.fulfillment.dlq` hoặc `orders.retry.30s`. Retry queue và quarantine queue có mục đích khác nhau; không gộp tất cả vào một DLQ không có quy trình xử lý.

### 7.1. Các chỉ số DLQ cần theo dõi

- DLQ ready depth và unacked depth.
- Số message được dead-letter trong mỗi phút.
- Số message được redeliver/replay.
- Tuổi message cũ nhất trong DLQ.
- Số lần retry hoặc x-death count nếu có.
- Tỷ lệ DLQ trên tổng message đã xử lý.
- Consumer count nếu DLQ có consumer điều tra tự động.

RabbitMQ Prometheus plugin có thể xuất queue depth và delivery counters. Tuổi message cũ nhất thường cần metric ứng dụng hoặc quy trình kiểm tra message timestamp; không giả định metric queue depth tiêu chuẩn tự cung cấp tuổi của từng message.

### 7.2. DLQ khác retry queue

Retry queue thường có TTL/DLX để tự động đưa message quay lại queue chính sau thời gian chờ. DLQ hoặc quarantine giữ message để điều tra và replay có kiểm soát. Nếu DLQ tự động dead-letter trở lại queue chính, nó đang hoạt động như một tầng retry.

| Queue | Kỳ vọng | Hành động khi tăng |
|---|---|---|
| Main queue | Có thể có backlog ngắn hạn | Kiểm tra throughput và consumer |
| Retry queue | Có message chờ theo lịch | Kiểm tra lỗi tạm thời và TTL |
| DLQ/quarantine | Thường thấp hoặc bằng 0 | Điều tra lỗi và lập kế hoạch replay |

### 7.3. Tỷ lệ dead-letter

Một DLQ có 10 message có thể là bất thường nếu hệ thống chỉ xử lý 100 message/ngày, nhưng có thể nhỏ nếu xử lý hàng triệu message/ngày. Hãy xem count tuyệt đối cùng tỷ lệ:

\[
\text{DLQ rate} =
\frac{\text{dead-lettered messages}}
{\text{messages processed}} \times 100\%
\]

Nếu counter dead-letter không có sẵn ở queue/broker version đang dùng, tạo application counter khi nhận error hoặc khi đưa message vào quarantine. Tránh đếm cùng một message ở nhiều tầng retry như nhiều lỗi nghiệp vụ độc lập.

## 8. Tạo metric nghiệp vụ trong Spring Cloud Stream

Metrics broker cho biết queue và offset; metrics ứng dụng cho biết vì sao consumer không theo kịp.

| Metric ứng dụng | Loại | Mục đích |
|---|---|---|
| `stream.messages.processed` | Counter | Số message xử lý thành công |
| `stream.messages.failed` | Counter | Số message xử lý thất bại |
| `stream.messages.retried` | Counter | Số lần retry |
| `stream.messages.dead_lettered` | Counter | Số message đưa vào DLQ |
| `stream.processing.duration` | Timer/Histogram | Thời gian xử lý một message |
| `stream.event.age` | Timer/Histogram | Tuổi event khi consumer bắt đầu xử lý |
| `stream.outbox.pending` | Gauge | Số event chờ relay nếu có outbox |

Ví dụ dùng Micrometer:

~~~java
@Component
class OrderMetrics {

    private final Counter processed;
    private final Counter failed;
    private final Timer processingDuration;

    OrderMetrics(MeterRegistry registry) {
        this.processed = Counter.builder("stream.messages.processed")
                .description("Successfully processed stream messages")
                .tag("binding", "processOrder-in-0")
                .register(registry);

        this.failed = Counter.builder("stream.messages.failed")
                .description("Failed stream message processing")
                .tag("binding", "processOrder-in-0")
                .register(registry);

        this.processingDuration = Timer.builder("stream.processing.duration")
                .description("Time spent processing a stream message")
                .tag("binding", "processOrder-in-0")
                .publishPercentileHistogram()
                .register(registry);
    }

    void recordSuccess(Duration duration) {
        processed.increment();
        processingDuration.record(duration);
    }

    void recordFailure() {
        failed.increment();
    }
}
~~~

Ví dụ tập trung vào cách tạo meter; tích hợp vào handler cần ghi nhận đúng một lần cho mỗi kết quả cuối cùng, không tăng success counter mỗi lần retry thành công nội bộ. Tên binding và tag nên là giá trị ổn định.

### 8.1. Cardinality của metric

Không gắn eventId, orderId, customerId, exception message đầy đủ, URL có path động, timestamp hoặc payload làm metric tag. Các giá trị này tạo số lượng time series không giới hạn, làm tăng RAM và chi phí Prometheus.

Hãy dùng tag có tập giá trị nhỏ như application, environment, binding, destination, consumer group đã được kiểm soát và outcome. Nếu cần tìm một event cụ thể, dùng log hoặc trace với eventId/correlationId thay vì metric label.

## 9. Dashboard cho Kafka và RabbitMQ

### 9.1. Kafka consumer dashboard

Hiển thị:

- Tổng lag theo consumer group.
- Lag theo topic/partition.
- Lag lớn nhất của một partition.
- Ingress rate và consume rate.
- Event age hoặc ước lượng drain time.
- Consumer group members và assigned partitions.
- Rebalance, commit latency và poll interval.
- Application processing duration và error rate.

Đặt group và topic làm filter; mặc định hiển thị các group quan trọng của ứng dụng. Không chỉ vẽ tổng lag vì một partition nóng có thể bị che khuất.

### 9.2. RabbitMQ dashboard

Hiển thị:

- Ready, unacked và tổng messages theo queue.
- Consumer count và consumer capacity.
- Publish, deliver, ack và redelivery rate.
- Queue depth của main, retry và DLQ.
- DLQ oldest message age nếu đã có metric.
- Node memory, disk, file descriptors và connection.

RabbitMQ khuyến nghị Prometheus và Grafana cho thu thập dài hạn. Management UI hữu ích cho điều tra nhanh nhưng không thay thế hệ thống lưu chuỗi thời gian.

### 9.3. Pipeline overview

~~~text
Producer rate
    |
    v
Kafka topic -> Consumer group -> Processing success/error
    |                |
    v                v
Consumer lag     Retry / DLQ

Rabbit exchange -> Main queue -> Consumer
                       |            |
                       v            v
                  Queue depth    Ack rate
                       |
                       v
                 Retry / DLQ
~~~

Mục tiêu là trả lời nhanh: dữ liệu đang dừng ở broker nào, consumer nào không theo kịp, lỗi có tăng không và message nào cần điều tra.

## 10. PromQL và cảnh báo mẫu

Tên metric Kafka lag phụ thuộc exporter. Spring Cloud Stream Kafka binder có metric `spring.cloud.stream.binder.kafka.offset`; một Kafka exporter có thể đặt tên theo quy ước riêng. Hãy kiểm tra endpoint Prometheus trước khi dùng rule bên dưới.

### 10.1. Kafka lag

Ví dụ nếu exporter cung cấp metric `kafka_consumergroup_lag`:

~~~promql
sum by (consumergroup, topic) (
  kafka_consumergroup_lag
)
~~~

Lag lớn nhất theo partition:

~~~promql
max by (consumergroup, topic, partition) (
  kafka_consumergroup_lag
)
~~~

Cảnh báo khi lag duy trì trên ngưỡng:

~~~yaml
groups:
  - name: kafka-consumer
    rules:
      - alert: KafkaConsumerLagHigh
        expr: sum by (consumergroup, topic) (kafka_consumergroup_lag) > 10000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Kafka consumer lag is high
          description: Check ingress rate, processing rate and partition assignment.
~~~

Metric name và label `consumergroup`, `topic`, `partition` trong ví dụ phụ thuộc exporter. Thay chúng bằng tên thực tế trong Prometheus. Ngưỡng 10.000 chỉ là ví dụ; hãy đặt theo throughput và SLA.

### 10.2. RabbitMQ queue depth

Ready backlog theo queue:

~~~promql
rabbitmq_detailed_queue_messages_ready
~~~

Tổng ready và unacked:

~~~promql
rabbitmq_detailed_queue_messages
~~~

Unacked theo queue:

~~~promql
rabbitmq_detailed_queue_messages_unacked
~~~

Ví dụ alert khi queue ready tồn đọng:

~~~yaml
groups:
  - name: rabbitmq-queues
    rules:
      - alert: RabbitQueueBacklogHigh
        expr: rabbitmq_detailed_queue_messages_ready > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: RabbitMQ queue backlog is growing
          description: Inspect consumer count, capacity, delivery rate and downstream latency.
~~~

### 10.3. Consumer không hoạt động

Nếu queue có message ready nhưng không có consumer:

~~~promql
rabbitmq_detailed_queue_consumers == 0
and
rabbitmq_detailed_queue_messages_ready > 0
~~~

### 10.4. DLQ có message

Nếu tên queue DLQ theo quy ước kết thúc bằng `.dlq`:

~~~promql
rabbitmq_detailed_queue_messages_ready{queue=~".*\\.dlq"} > 0
~~~

Hãy kiểm tra label queue của exporter có chứa tên queue đầy đủ hay không. Một số topology đặt tên DLQ khác; dùng label thực tế.

### 10.5. Tạo alert theo nhiều tín hiệu

Không cảnh báo chỉ dựa trên một giá trị backlog. Một alert hữu ích có thể yêu cầu backlog vượt ngưỡng trong một khoảng thời gian, consume rate thấp hơn ingress rate hoặc event age vượt SLA.

Với DLQ, có thể cảnh báo khi có message mới trong 5 phút hoặc khi oldest age vượt thời hạn xử lý. Đối với một hệ thống có DLQ hoạt động bình thường, ngưỡng phải dựa trên chính sách nghiệp vụ thay vì mặc định mọi message đều là sự cố nghiêm trọng.

## 11. Thiết kế ngưỡng và SLO

Không có một ngưỡng lag hoặc queue depth phù hợp cho mọi hệ thống. Xác định throughput bình thường và peak, độ trễ xử lý mục tiêu, backlog tối đa có thể rút trong thời gian phục hồi, số consumer/partition có thể mở rộng và giới hạn downstream.

Ví dụ một pipeline xử lý 2.000 message/giây có thể chịu backlog 20.000 message trong 10 giây. Nhưng nếu SLA yêu cầu mỗi đơn hàng được xử lý trong 2 giây, event age vượt 2 giây cần cảnh báo ngay cả khi tổng lag thấp.

### 11.1. Alert theo symptom và cause

| Symptom | Tín hiệu nguyên nhân cần kiểm tra |
|---|---|
| Kafka lag tăng | Producer rate, consume rate, rebalance, processing duration |
| Một partition lag cao | Key skew, consumer assignment, record lỗi |
| Rabbit ready tăng | Consumer count, capacity, prefetch, downstream |
| Rabbit unacked tăng | Processing duration, ack mode, consumer stuck |
| DLQ tăng | Exception type, schema, retry exhaustion, TTL |
| End-to-end age tăng | Broker backlog, network, downstream latency |

### 11.2. Alert không gây nhiễu

- Dùng `for` để bỏ qua dao động ngắn.
- Chia severity theo mức ảnh hưởng SLA.
- Group alert theo application, group, topic hoặc queue.
- Thêm link dashboard và runbook vào annotation.
- Tránh gửi một alert cho từng partition nếu một alert tổng hợp đã đủ.
- Dùng inhibit rule khi broker down khiến hàng loạt queue alert cùng xuất hiện.

## 12. Cardinality và chi phí thu thập

Kafka có thể có nhiều topic, partition và consumer group. RabbitMQ có thể có hàng nghìn queue. Nếu mọi metric đều gắn label đầy đủ và scrape quá thường xuyên, monitoring system cũng có thể trở thành nguồn tiêu thụ tài nguyên lớn.

Thực hành tốt:

- Chỉ giữ label cần cho điều tra và alert.
- Dùng coarse queue metrics cho overview.
- Bật detailed queue metrics cho queue quan trọng hoặc khi cần chẩn đoán.
- Scrape theo tần suất phù hợp với SLA; không cần scrape mọi metric mỗi giây.
- Giới hạn retention và recording rules.
- Dùng relabel/filter để loại bỏ queue tạm thời hoặc không thuộc phạm vi.
- Không dùng metric label cho ID động.

RabbitMQ Prometheus plugin phân chia metric theo nhóm; nhóm detailed queue metrics có chi phí cao hơn coarse metrics. Hãy chọn metric family có chủ đích và quan sát overhead khi mở rộng số queue.

## 13. Runbook: Kafka consumer lag tăng

Khi nhận alert Kafka lag:

1. Xác định consumer group, topic và partition có lag.
2. So sánh ingress rate với consume rate.
3. Kiểm tra group members, assigned partitions và rebalance.
4. Xem processing duration, exception và retry rate.
5. Kiểm tra consumer poll, commit latency và downstream dependency.
6. Kiểm tra partition có key nóng hoặc record lớn.
7. Nếu thiếu năng lực, tăng consumer instance/concurrency trong giới hạn partition và downstream.
8. Nếu một partition bị kẹt bởi record lỗi, xử lý error/DLQ theo policy; không reset offset tùy tiện.
9. Theo dõi lag giảm và event age trở lại SLA.
10. Ghi lại nguyên nhân và thay đổi capacity cần thiết.

Tăng số consumer không luôn tăng throughput. Trong cùng một consumer group, số consumer hoạt động song song bị giới hạn bởi số partition; consumer dư có thể không được gán partition. Nếu downstream là bottleneck, tăng consumer có thể làm sự cố nặng hơn.

## 14. Runbook: RabbitMQ queue depth hoặc DLQ tăng

Khi queue depth tăng:

1. Xác định queue, vhost và loại queue.
2. So sánh messages_ready, messages_unacked và tổng messages.
3. Kiểm tra số consumer và consumer capacity.
4. So sánh publish, deliver, ack và redelivery rate.
5. Kiểm tra prefetch, thời gian xử lý và downstream dependency.
6. Kiểm tra node memory, disk, file descriptors và connection.
7. Nếu consumer count bằng 0, kiểm tra binding lifecycle, deployment và kết nối.
8. Nếu unacked cao, kiểm tra consumer bị treo, ack timeout hoặc xử lý quá chậm.
9. Nếu DLQ tăng, phân loại exception, schema và số lần retry.
10. Chỉ replay DLQ sau khi nguyên nhân đã được khắc phục và có kế hoạch dedup.

Không purge queue hoặc DLQ chỉ để làm dashboard về 0. Trước khi purge, phải xác định message có thể bị mất hay không, có cần lưu bản sao để audit và có được phép bỏ dữ liệu không.

## 15. Kiểm thử observability

### 15.1. Kafka

- Dừng consumer để tạo lag.
- Tăng producer rate vượt consume rate.
- Tạo một partition nóng.
- Restart consumer để tạo rebalance.
- Gửi record lỗi schema hoặc lỗi xử lý.
- Xác minh lag theo group/partition, event age và alert.

### 15.2. RabbitMQ

- Dừng consumer khi producer vẫn publish.
- Tăng prefetch để quan sát unacked.
- Làm consumer xử lý chậm.
- Reject một message để đưa vào DLQ.
- Tạo message hết TTL nếu topology dùng retry queue.
- Xác minh ready/unacked/depth, consumer capacity và DLQ metrics.

### 15.3. Alert và runbook

- Xác minh alert chỉ firing sau thời gian `for`.
- Kiểm tra label và annotation có đúng queue/group.
- Xác minh dashboard mở được từ alert.
- Thử quy trình khôi phục và xác nhận alert resolved.
- Kiểm tra monitoring không tạo quá nhiều time series khi có nhiều event ID.

## 16. Những lỗi thường gặp

1. **Chỉ nhìn tổng Kafka lag**: một partition nóng có thể bị che khuất. Hãy drill down theo partition.
2. **Coi lag là thời gian chờ**: lag đo số offset, không phải giây. Hãy đo event age và throughput.
3. **Bỏ qua ingress rate**: lag tăng có thể do producer tăng tải. Hãy so sánh ingress và consume rate.
4. **Tăng consumer mà không kiểm tra partition**: consumer dư không được gán partition. Hãy xem số partition và assignment.
5. **Chỉ nhìn Rabbit tổng messages**: không biết message đang chờ hay đã giao. Hãy tách ready và unacked.
6. **Coi unacked cao luôn là consumer lỗi**: prefetch lớn hoặc xử lý lâu cũng làm unacked tăng. Hãy xem capacity, ack rate và processing time.
7. **Không theo dõi DLQ**: message lỗi có thể tồn tại lâu mà không ai xử lý. Hãy đặt alert, owner và retention.
8. **Coi DLQ depth bằng 0 là đủ**: message có thể đang ở retry queue hoặc lỗi chưa tới DLQ. Hãy theo dõi retry và error rate.
9. **Chỉ dùng Management UI**: UI không thay thế lưu trữ chuỗi thời gian. Hãy dùng Prometheus/Grafana cho production.
10. **Scrape mọi metric chi tiết quá thường xuyên**: tăng overhead và cardinality. Hãy chọn metric family và interval phù hợp.
11. **Đưa eventId vào metric tag**: tạo time series không giới hạn. Hãy dùng log/trace để tra cứu event cụ thể.
12. **Coi health UP là pipeline khỏe**: broker có thể kết nối nhưng consumer vẫn lag. Hãy kết hợp health, lag, depth và event age.
13. **Đặt alert chỉ theo một threshold cố định**: không phản ánh throughput hoặc SLA. Hãy dùng trend, rate và thời gian tồn đọng.
14. **Purge DLQ để xóa cảnh báo**: có thể làm mất dữ liệu cần điều tra. Hãy xử lý và replay có kiểm soát.

## 17. Quy trình triển khai monitoring

Khi triển khai Spring Cloud Stream trong production:

1. Xác định các consumer group, topic, queue, retry queue và DLQ quan trọng.
2. Bật metric Kafka binder và cấu hình thu thập lag phù hợp.
3. Bật RabbitMQ Prometheus plugin và chọn metric family cần thiết.
4. Thêm Actuator, Micrometer registry và application metrics.
5. Cấu hình Prometheus scrape endpoints với authentication/network policy phù hợp.
6. Tạo dashboard tổng quan và dashboard drill-down theo group/partition/queue.
7. Định nghĩa alert theo SLA, backlog trend, consumer count và DLQ.
8. Bổ sung event age, processing duration, error/retry counters.
9. Giới hạn metric cardinality và chi phí scrape.
10. Viết runbook cho Kafka lag, Rabbit queue depth và DLQ growth.
11. Kiểm thử bằng cách tạo backlog, consumer outage và dead-letter.
12. Đánh giá dashboard và alert định kỳ theo tải thực tế.

## Kết luận

Kafka consumer lag cho biết consumer group còn bao nhiêu offset chưa theo kịp cuối log; cần xem theo group, topic và partition, đồng thời so sánh ingress rate, consume rate và event age. RabbitMQ queue depth phải được tách thành messages_ready và messages_unacked; tổng depth không đủ để xác định consumer đang chậm hay queue chưa có worker. DLQ là tín hiệu lỗi cần theo dõi riêng cùng retry rate và tuổi message.

Spring Cloud Stream Kafka binder có metric lag Micrometer; RabbitMQ cung cấp queue metrics qua Prometheus plugin; Spring Boot Actuator/Micrometer có thể xuất thêm processing duration, error, retry và event age. Dashboard tốt kết hợp broker metrics, application metrics và hạ tầng. Alert cần gắn với SLA và xu hướng backlog, còn runbook phải hướng dẫn kiểm tra partition/consumer, ready/unacked, DLQ và nguyên nhân downstream. Khi có các tín hiệu này, đội vận hành có thể phát hiện backlog sớm, xác định nơi message bị kẹt và phục hồi có kiểm soát.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Binder Metrics](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/metrics.html)
- [Spring Cloud Stream — Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html)
- [Apache Kafka — Monitoring](https://kafka.apache.org/documentation/#monitoring)
- [RabbitMQ — Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [RabbitMQ — Prometheus and Grafana](https://www.rabbitmq.com/docs/prometheus)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
