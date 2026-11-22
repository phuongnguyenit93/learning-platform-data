# Rebalance count

## 1. Rebalance count đo điều gì?

Trong hệ thống Kafka consumer group, **rebalance** là quá trình coordinator và các consumer members phối hợp để thiết lập hoặc thay đổi việc phân công partitions. Khi một consumer mới tham gia, một consumer rời group, mất heartbeat, vi phạm poll deadline, hoặc khi subscription/assignment thay đổi, group có thể phải thực hiện rebalance.

**Rebalance count** là chỉ số đếm số lần quá trình rebalance được một thành phần quan sát trong một khoảng thời gian hoặc trong vòng đời của nó. Đây là chỉ số vận hành quan trọng vì rebalance thường tạo ra một khoảng gián đoạn hoặc thay đổi quyền xử lý partition, kéo theo biến động throughput, consumer lag và khả năng redelivery.

Tuy nhiên, cần phân biệt ngay từ đầu:

- **Client-level rebalance count**: số lần **một Kafka consumer client** đã trải qua các lần rebalance theo định nghĩa metric của Kafka client.
- **Group-level rebalance events**: những đợt thay đổi trạng thái của **toàn consumer group**. Một đợt của group có thể khiến nhiều consumer clients cùng tăng rebalance count.
- **Application callback count**: số lần Spring Kafka gọi `onPartitionsAssigned`, `onPartitionsRevokedBeforeCommit` hoặc `onPartitionsLost`. Những callback này không phải một phép đếm chuẩn duy nhất cho toàn group.

Nếu gộp ba khái niệm thành một, dashboard sẽ đưa ra các con số sai ý nghĩa. Ví dụ một group có năm members cùng rebalance một lần có thể khiến metric client tổng cộng tăng ở nhiều members, không phải group đã rebalance năm lần độc lập.

### 1.1. Ví dụ

~~~text
Consumer group: checkout-service
Topic: orders (6 partitions)

Trước rebalance:
  Consumer A -> P0, P1
  Consumer B -> P2, P3
  Consumer C -> P4, P5

Consumer D join group.

Group thực hiện một đợt phân phối lại:
  Consumer A -> P0, P1
  Consumer B -> P2
  Consumer C -> P3, P4
  Consumer D -> P5

Client A/B/C/D có thể quan sát các mốc rebalance riêng.
Một "lần group đổi assignment" không tương đương
với tổng số callback được chạy trên mọi client.
~~~

Rebalance count giúp nhận ra **churn**: group liên tục thay đổi assignment thay vì giữ các consumer ổn định. Bản thân con số chưa chứng minh có lỗi; cần đo theo thời gian, đối chiếu nguyên nhân và tác động.

## 2. Vì sao rebalance count quan trọng?

Một hệ thống có thể vẫn ghi log "consumer healthy", vẫn có pods ở trạng thái Running, nhưng liên tục rebalance và chỉ xử lý record trong các khoảng ngắn giữa những lần chuyển assignment.

Các hệ quả có thể thấy:

1. **Gián đoạn nhận record:** consumer đang join/reconcile group hoặc đang revoke/assign partitions.
2. **Consumer lag tăng:** producer tiếp tục ghi trong lúc consumer không xử lý với tốc độ bình thường.
3. **Thay đổi partition ownership:** state/cache theo partition có thể cần cleanup hoặc warm-up.
4. **Offset commit thất bại:** commit có thể bị từ chối khi group generation hoặc assignment thay đổi.
5. **Redelivery:** record xử lý xong nhưng offset chưa commit có thể được consumer mới đọc lại.
6. **Tải hạ tầng tăng:** thêm coordinator requests, metadata/assignment traffic và cold-start downstream.
7. **Dao động latency:** p95/p99 processing delay có thể tăng dù average throughput có vẻ vẫn ổn.

Không phải mỗi rebalance đều xấu. Scale-out, rolling deployment hoặc thay đổi số partition thường tạo rebalance hợp lệ. Điều cần phát hiện là **rebalance quá thường xuyên, kéo dài, thất bại hoặc xảy ra ngoài các hoạt động đã dự kiến**.

## 3. Các nguyên nhân khiến consumer group rebalance

| Nhóm nguyên nhân | Ví dụ | Hành động điều tra |
|---|---|---|
| Member join | Scale từ 2 lên 3 pods | Đối chiếu deployment/autoscaling |
| Member leave | Graceful shutdown, scale-in | Xem lifecycle và rollout |
| Session timeout | Heartbeat không đến coordinator đủ lâu | Kiểm tra network, JVM pause, broker |
| Max poll interval | Listener/batch xử lý quá lâu | Kiểm tra processing time và `max.poll.interval.ms` |
| Consumer crash | OOM, process kill, node failure | Kiểm tra pod restart, OOM events |
| Subscription thay đổi | Consumer subscribe tập topics khác | Xem configuration/deployment |
| Partition metadata thay đổi | Tăng số partitions hoặc thay đổi assignment | Đối chiếu topic operations |
| Coordinator disturbance | Broker failover, coordinator unavailable | Kiểm tra broker logs và request latency |
| Protocol/assignor thay đổi | Upgrade client, chuyển assignment strategy | Xem compatibility, protocol, assignor |
| Static member identity conflict | Trùng `group.instance.id` | Kiểm tra uniqueness theo member |

Bảng này mô tả các khả năng phổ biến, không có nghĩa cứ xảy ra một sự kiện là chắc chắn sẽ tăng mọi rebalance counter. Cách member reconcile assignment còn phụ thuộc Kafka client version, group protocol và assignor.

Đặc biệt, **listener xử lý chậm** không đồng nghĩa ngay với heartbeat timeout. Với classic consumer client hiện đại, heartbeat thường có background thread; listener có thể vẫn gửi heartbeat nhưng không gọi `poll()` kịp trước `max.poll.interval.ms`.

## 4. Từ rebalance event đến metric

### 4.1. Một lần group rebalance có thể liên quan nhiều clients

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant C as Group coordinator
    participant N as Consumer mới

    A->>C: Heartbeat / membership bình thường
    B->>C: Heartbeat / membership bình thường
    N->>C: Join group
    Note over C: Membership/assignment cần đổi
    C-->>A: Reconcile / rebalance
    C-->>B: Reconcile / rebalance
    C-->>N: Assignment
    Note over A: Client metrics có thể tăng
    Note over B: Client metrics có thể tăng
    Note over N: Có trạng thái tham gia mới
~~~

Nếu A và B đều tăng `rebalance-total` thêm 1, tổng client counter tăng 2. Điều đó không chứng minh coordinator thực hiện hai đợt group-level độc lập.

### 4.2. Vòng đời counter

Counter client thông thường tích lũy trong vòng đời process/client. Nó có thể reset khi JVM hoặc KafkaConsumer được tạo lại. Ví dụ:

~~~text
10:00 Consumer A rebalance-total = 12
10:10 Consumer A rebalance-total = 14
10:20 Process restart
10:21 Consumer A mới rebalance-total = 1
~~~

Nếu dashboard vẽ raw counter như một gauge và thấy 14 giảm xuống 1, đó chưa phải "số rebalance của group giảm". Nó là **counter reset do lifecycle**.

Trong Prometheus, thường phân tích bằng `rate()` hoặc `increase()` thay vì chỉ lấy giá trị counter hiện tại. Cần chú ý series labels, scraping và việc client ID thay đổi qua pod restart.

## 5. Kafka client metrics liên quan rebalance

Kafka consumer client cung cấp các metrics về group coordination. Trên nhiều phiên bản client, chúng xuất hiện dưới nhóm JMX/Metrics tương tự:

~~~text
kafka.consumer:
  type=consumer-coordinator-metrics
  client-id=<client-id>
~~~

Các tên metrics thường gặp:

| Kafka client metric | Ý nghĩa vận hành |
|---|---|
| `rebalance-total` | Tổng số rebalance thành công theo metric của consumer client |
| `rebalance-rate-per-hour` | Tốc độ rebalance theo giờ ở client |
| `rebalance-latency-avg` | Thời gian rebalance trung bình theo phép đo client |
| `rebalance-latency-max` | Thời gian rebalance lớn nhất theo phép đo client |
| `last-rebalance-seconds-ago` | Thời gian kể từ lần rebalance gần nhất, nếu client/version cung cấp |
| `assigned-partitions` | Số partition hiện được gán cho consumer |
| `failed-rebalance-total` | Tổng số lần rebalance thất bại, khi phiên bản hỗ trợ |
| `failed-rebalance-rate-per-hour` | Tốc độ rebalance thất bại, khi phiên bản hỗ trợ |

**Tên và tính sẵn có phụ thuộc Kafka client version, group protocol, JMX exporter và thư viện metrics.** Không coi danh sách trên là cam kết mọi ứng dụng đều có tất cả metric. Bước đầu tiên khi triển khai là xem metrics thực tế do client đang chạy xuất ra.

### 5.1. rebalance-total

Đây là counter tích lũy theo định nghĩa Kafka consumer client. Khi tăng, client đã tham gia một lần rebalance hoàn tất thành công theo protocol của nó. Counter thường có giá trị nhất khi theo dõi **mức tăng trong một cửa sổ thời gian**.

Không dùng raw `rebalance-total` của một pod mới so sánh với raw counter của pod đã chạy 30 ngày để kết luận pod mới tốt hơn.

### 5.2. rebalance-rate-per-hour

Metric tốc độ giúp phát hiện group đang churn. Ví dụ:

~~~text
Consumer A:
  rebalance-rate-per-hour ~ 0.0    -> ổn định trong giai đoạn quan sát
  rebalance-rate-per-hour ~ 12.0   -> có hoạt động membership lặp
~~~

Giá trị là rate phía client, không phải chắc chắn **12 group-wide rebalances độc lập**. Nên kết hợp counter, latency và số members.

### 5.3. rebalance latency

Rebalance count cao nhưng mỗi lần rất nhanh có tác động khác với count thấp nhưng một lần kéo dài vài chục giây.

Hai trục giám sát nên đi cùng nhau:

~~~text
Frequency: Có bao nhiêu lần rebalance?
Duration:  Mỗi lần kéo dài bao lâu?
~~~

Khi group có cooperative rebalance hoặc group protocol mới, assignment có thể thay đổi theo nhiều bước. Các metrics latency có ý nghĩa theo cơ chế đo của client, không tự thay thế đo gián đoạn nghiệp vụ thực tế.

### 5.4. last rebalance

Nếu có metric thời gian từ rebalance cuối, nó hữu ích để phân biệt:

- Một đợt rebalance duy nhất sau deployment.
- Một group cứ vài chục giây lại có rebalance.
- Một consumer vừa restart.
- Một client lâu ngày không thay đổi assignment.

Khi metric biến mất do process down, không được hiểu là "không có rebalance"; dữ liệu monitoring có thể bị thiếu.

## 6. Spring Kafka có tự tạo metric rebalance count không?

Spring Kafka quản lý listener containers và có thể tích hợp Micrometer/Observation. Tuy nhiên, cần phân biệt các lớp metrics:

1. **Kafka client metrics** như `rebalance-total`: do KafkaConsumer/Kafka client tạo.
2. **Spring Kafka listener/container metrics**: đo listener invocation, processing duration, container observations theo version/configuration.
3. **Application metrics tự tạo**: đếm callbacks hoặc state transitions từ `ConsumerAwareRebalanceListener`.
4. **Broker/group coordinator metrics**: phản ánh hoạt động server-side, không đồng nghĩa client-specific rebalance counter.

Bật Spring Kafka listener timer không có nghĩa mọi metric KafkaConsumer/JMX tự động xuất hiện ở endpoint Prometheus. Kafka client metrics có thể cần Micrometer Kafka binder hoặc cấu hình export JMX phù hợp. Tùy Spring Boot version, một số Kafka metrics có thể được auto-bound; cần xác nhận trong metrics endpoint.

Ví dụ cùng là "rebalance" nhưng ý nghĩa:

~~~text
Kafka consumer JMX:
  rebalance-total = 6
    -> Đếm theo định nghĩa Kafka client.

Application counter:
  partitions-assigned-callback-total = 8
    -> Đếm callback assigned, không phải cùng metric.

Broker logs:
  Group completed rebalance 3 times
    -> Quan sát theo group/coordinator, phạm vi khác.
~~~

**Không đặt tên metric callback là `kafka_consumer_rebalance_total` nếu nó chỉ đếm `onPartitionsAssigned`**, vì người đọc có thể tưởng đó là counter chính thức của Kafka client.

## 7. Ví dụ Spring Kafka cấu hình listener container

Cấu hình consumer group và listener:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092
    consumer:
      group-id: checkout-service
      enable-auto-commit: false
      max-poll-records: 200
      properties:
        max.poll.interval.ms: 300000
        session.timeout.ms: 30000
        heartbeat.interval.ms: 10000
    listener:
      concurrency: 3
      ack-mode: record
~~~

Đây là ví dụ cho group **classic** với các Kafka client versions hỗ trợ properties tương ứng. Nếu dùng `group.protocol=consumer`, một số session/heartbeat settings do broker quyết định; không sao chép cấu hình classic để kết luận chúng có hiệu lực.

Ý nghĩa đối với rebalance count:

- `concurrency` tăng số consumer members trên một instance, nên có thể làm số series client metrics và callbacks tăng.
- `max-poll-records` và `max.poll.interval.ms` ảnh hưởng nguy cơ client bị coi là không tiến bộ trong poll loop.
- `session.timeout.ms` liên quan mất heartbeat theo classic group protocol.
- `enable-auto-commit=false` giúp container quản lý offset theo processing, nhưng **không ngăn rebalance**.
- `ack-mode=record` giảm cửa sổ chưa commit cho từng record trong một số trường hợp, nhưng không bảo đảm không có redelivery khi rebalance/crash.

Không chọn timeout chỉ để làm rebalance count đẹp hơn. Cần cân bằng detection time, processing duration và SLO.

## 8. Theo dõi callback rebalance trong Spring Kafka

Nếu muốn giải thích rebalance count bằng các sự kiện cụ thể ở ứng dụng, Spring Kafka hỗ trợ `ConsumerAwareRebalanceListener`.

Các callback hữu ích:

- `onPartitionsRevokedBeforeCommit`: được gọi khi partitions chuẩn bị bị thu hồi theo quy trình mà container xử lý.
- `onPartitionsRevokedAfterCommit`: callback sau bước commit phù hợp, nếu được phiên bản/container hỗ trợ.
- `onPartitionsAssigned`: consumer nhận assignment.
- `onPartitionsLost`: consumer đã mất quyền sở hữu partition, không còn nên commit như thể vẫn sở hữu.

Callback ghi nhận **partition lifecycle**. Chúng không cung cấp một "group rebalance ID" toàn cục được bảo đảm duy nhất cho mỗi đợt. Trong cooperative rebalance hoặc thay đổi assignment nhiều bước, số callback có thể khác một cách đáng kể so với `rebalance-total`.

### 8.1. Ví dụ đăng ký rebalance listener

~~~java
@Configuration
public class CheckoutKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
            checkoutListenerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                MeterRegistry meterRegistry
            ) {
        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties().setConsumerRebalanceListener(
            new ConsumerAwareRebalanceListener() {

                @Override
                public void onPartitionsRevokedBeforeCommit(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions
                ) {
                    meterRegistry.counter(
                        "app.kafka.partition.callbacks",
                        "listener", "checkout",
                        "phase", "revoked"
                    ).increment();

                    log.info("Revoked partitions: {}", partitions);
                }

                @Override
                public void onPartitionsAssigned(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions
                ) {
                    meterRegistry.counter(
                        "app.kafka.partition.callbacks",
                        "listener", "checkout",
                        "phase", "assigned"
                    ).increment();

                    log.info("Assigned partitions: {}", partitions);
                }

                @Override
                public void onPartitionsLost(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions
                ) {
                    meterRegistry.counter(
                        "app.kafka.partition.callbacks",
                        "listener", "checkout",
                        "phase", "lost"
                    ).increment();

                    log.warn("Lost partitions: {}", partitions);
                }
            }
        );

        return factory;
    }
}
~~~

Các import cần thiết gồm:

~~~java
import java.util.Collection;

import io.micrometer.core.instrument.MeterRegistry;
import org.apache.kafka.clients.consumer.Consumer;
import org.apache.kafka.common.TopicPartition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ConsumerAwareRebalanceListener;
~~~

`OrderEvent` và `log` là kiểu/biến minh họa của ứng dụng. Callback signatures cần khớp Spring Kafka version. Đoạn này minh họa **callback counter**, không khẳng định đây là Kafka client `rebalance-total`.

### 8.2. Vì sao callback count không phải rebalance count?

Có thể có các trường hợp:

- Khi listener mới khởi động và được assign partition, `onPartitionsAssigned` được gọi dù consumer chưa từng có assignment trước đó.
- Trong eager rebalance, nhiều members cùng có revoke/assign.
- Trong cooperative rebalance, một phần partition có thể được giữ lại, một phần được chuyển dần.
- Khi consumer mất session/crash, JVM cũ không nhất thiết chạy callback trước lúc broker reassignment.
- Với concurrent container, nhiều child consumers có callback độc lập.
- Một callback có thể nhận nhiều partitions; đếm callback khác đếm partition transitions.

Bởi vậy, đặt tên metric theo đúng điều nó đếm: **assignment callbacks**, **revocation callbacks**, **lost callbacks**. Để có số rebalance phía Kafka client, dùng counter của KafkaConsumer/Kafka client metric.

## 9. Đếm partitions hay đếm callback?

Một callback có thể nhận một collection nhiều partitions:

~~~text
onPartitionsRevokedBeforeCommit:
  [orders-0, orders-1, orders-2]

Callback count tăng: 1
Partitions revoked: 3
~~~

Đây là hai metrics khác nhau. Có thể đo:

- `partition_callback_total{phase="revoked"}`: số callback.
- `partition_transition_partitions_total{phase="revoked"}`: tổng số partition nằm trong những callback.
- `assigned_partitions`: số partition hiện thuộc một consumer.
- `rebalance_total`: Kafka client metric, không thay bằng callback.

Nếu cần đo số partition bị ảnh hưởng, trong callback có thể tăng counter theo `partitions.size()` thay vì 1. Nhưng ngay cả con số đó cũng không chứng minh có từng ấy group-wide rebalances.

Cần chú ý rằng một assignment có thể chứa partition không mới đối với ứng dụng do protocol/initial state; "số partitions callback nhắc tới" chưa chắc là số partitions thực sự chuyển owner.

## 10. Lấy Kafka consumer metrics bằng JMX

Kafka client exposes metrics thường qua JMX nếu môi trường JVM/JMX được cấu hình phù hợp. Một object name thường gặp:

~~~text
kafka.consumer:type=consumer-coordinator-metrics,client-id=checkout-client-0
~~~

Thuộc tính có thể gồm:

~~~text
rebalance-total
rebalance-rate-per-hour
rebalance-latency-avg
rebalance-latency-max
last-rebalance-seconds-ago
assigned-partitions
~~~

Đây là minh họa tên thường gặp, không phải output từ một JVM thực tế. Với JConsole, JMX exporter hoặc instrumentation tương đương, cần **liệt kê attributes thật** và xác định đúng client ID trong môi trường chạy.

### 10.1. Client ID trong Spring Kafka

Một application JVM có `concurrency=3` có thể tạo ba KafkaConsumers với các client IDs khác nhau. Tùy cấu hình và version, ID có thể có suffix index.

Ví dụ:

~~~text
checkout-consumer-0
checkout-consumer-1
checkout-consumer-2
~~~

Nếu dashboard chỉ truy vấn một client ID, nó có thể bỏ qua phần lớn rebalance activity của listener container.

### 10.2. Nếu ứng dụng có nhiều listeners

Một process có thể chạy nhiều consumer groups hoặc nhiều listener container factories. Mỗi group và mỗi consumer client cần được gắn nhãn chính xác.

Ví dụ:

~~~text
service=checkout
  listener=orders
  group=checkout-service
  client=checkout-orders-0

service=checkout
  listener=payments
  group=payment-projection
  client=checkout-payments-0
~~~

Không cộng tất cả counters thành một số "rebalance của checkout-service" khi ứng dụng có nhiều groups với hành vi độc lập.

## 11. Từ JMX metric sang Prometheus

Nếu hệ thống dùng JMX Exporter, Micrometer Kafka binder hoặc cơ chế bridge tương đương, Kafka client rebalance metrics có thể được export sang Prometheus.

Một tên series minh họa từ JMX exporter:

~~~text
kafka_consumer_coordinator_metrics_rebalance_total
~~~

**Tên series này phụ thuộc cấu hình exporter; không phải tên chuẩn bắt buộc trong mọi Spring Boot deployment.** Micrometer có thể đặt meter name và tags theo quy ước khác. Trước khi viết PromQL production, hãy truy vấn `/actuator/prometheus` hoặc scrape endpoint thực tế và xem tên series/labels được xuất ra.

Một số labels hữu ích:

~~~text
application="checkout"
environment="prod"
group_id="checkout-service"
client_id="checkout-consumer-0"
instance="pod-a"
~~~

Không phải JMX metric nào tự chứa `group_id`. Nếu exporter chỉ có `client-id`, cần một mapping đáng tin cậy từ client đến consumer group hoặc cấu hình common tags phù hợp. Không tự tạo label group dựa trên cách parse tùy tiện một client ID không ổn định.

### 11.1. Counter reset và rate()

Counter Prometheus nên được phân tích qua:

~~~promql
increase(kafka_consumer_coordinator_metrics_rebalance_total[15m])
~~~

Biểu thức trả về số lần tăng **ước tính** trong cửa sổ 15 phút của một series. `increase()` xử lý counter reset theo semantics Prometheus khi có đủ samples, nhưng không thể tái tạo mọi sự kiện xảy ra trong khoảng không có scrape hoặc trong lúc một client chết rất nhanh.

Tốc độ theo giây:

~~~promql
rate(kafka_consumer_coordinator_metrics_rebalance_total[5m])
~~~

Nếu muốn đơn vị rebalance mỗi giờ cho một consumer series:

~~~promql
rate(kafka_consumer_coordinator_metrics_rebalance_total[15m]) * 3600
~~~

Đây vẫn là **client rate**, không phải group event rate đã được chuẩn hóa.

### 11.2. Tổng hợp qua các clients

Nếu nhãn `group_id` và `application` có sẵn và chính xác:

~~~promql
sum by (application, group_id) (
  increase(kafka_consumer_coordinator_metrics_rebalance_total[15m])
)
~~~

Biểu thức này ước tính **tổng số lần các Kafka clients trong group tham gia rebalance**, không nhất thiết bằng số đợt group-level rebalance duy nhất.

Có thể hiển thị metric với tên dashboard:

~~~text
Client rebalance participation, last 15m
~~~

Không nên ghi nhãn:

~~~text
Exact group rebalance events, last 15m
~~~

trừ khi nguồn dữ liệu được xây dựng thực sự đếm group-level events theo định nghĩa đã xác nhận.

### 11.3. Khi group có nhiều replicas

Giả sử:

~~~text
A rebalance-total: 12 -> 13
B rebalance-total:  7 ->  8
C rebalance-total:  4 ->  5

Tổng client increase: 3
Group có thể đã trải qua một đợt rebalance liên quan cả A, B, C.
~~~

Tổng 3 là có ý nghĩa nếu đang đo **client participation work**, nhưng sai nếu đặt nó làm "ba lần group rebalance".

## 12. Đếm group rebalance event thực sự thế nào?

Kafka client metric không có sẵn một phép biến đổi phổ quát, chính xác để suy ra duy nhất group rebalance ID từ tổng các client counters.

Nếu yêu cầu vận hành là "group đã hoàn tất bao nhiêu lần thay đổi assignment", có thể cân nhắc:

1. **Broker/coordinator logs hoặc metrics** có semantics group-level phù hợp ở phiên bản Kafka đang dùng.
2. Một hệ thống quan sát tập trung nhận các state transitions có định danh group và timestamp, kèm thuật toán correlation đã xác minh.
3. Kafka Admin API/group-state observation được polling có kiểm soát, nhưng lưu ý polling có thể bỏ lỡ các rebalances nhanh giữa hai lần đo.
4. Audit/rebalance event stream nội bộ được thiết kế để ghi nhận một sự kiện group-level có khóa duy nhất, nếu ứng dụng thực sự cần.

Không tự tuyên bố dùng `max()` trên các client `rebalance-total` sẽ cho số group rebalances: clients restart ở các thời điểm khác nhau, members join/leave và counter resets khiến phép toán không có nghĩa ổn định.

Với phần lớn hệ thống, metric client-level rebalance participation rate + rebalance duration + consumer lag là đủ để đánh giá group stability, nếu dashboard giải thích rõ semantics.

## 13. Thiết kế dashboard rebalance count

Một dashboard vận hành nên có ít nhất ba lớp:

### 13.1. Tổng quan group

- Group ID và service/environment.
- Số consumer members hiện tại.
- Số partitions được assign.
- Tốc độ rebalance client-level trong 5–15 phút.
- Consumer lag tổng và max lag theo partition.
- Số pod restarts/rollouts/HPA changes.

### 13.2. Chi tiết từng consumer client

- `rebalance-total` và `rebalance-rate-per-hour`.
- `rebalance-latency-avg` và `rebalance-latency-max` nếu có.
- Thời gian từ rebalance cuối.
- Assignment count, client ID, instance/pod.
- Heartbeat errors và coordinator request latency nếu có.

### 13.3. Tác động tới nghiệp vụ

- Listener throughput (records/sec).
- Processing latency p95/p99.
- Offset commit failures.
- Retry/redelivery counts.
- DLT volume.
- Database/HTTP downstream errors.
- SLO: time to process, end-to-end latency hoặc backlog drain time.

Bố cục khái quát:

~~~text
Consumer group checkout-service
+-------------------------------------------------------+
| Client rebalance participation, 15m: 12 (ước tính)     |
| Last rebalance: 40s ago (client-level)                 |
| Current members: 4                                     |
+-------------------------------------------------------+
| Lag by partition          | Throughput / sec           |
| P0:  50                   | 120                        |
| P1: 800                   |  70                        |
+-------------------------------------------------------+
| Rebalance latency         | Commit errors              |
| avg/max                   | count/rate                 |
+-------------------------------------------------------+
| Timeline: deployments, HPA, restarts, broker events     |
+-------------------------------------------------------+
~~~

Số liệu chỉ là ví dụ để hình dung cách trình bày. Tránh ghép client-level rebalance counts và group-level membership numbers thành cùng một giá trị không được định nghĩa.

## 14. Đặt cảnh báo cho rebalance count

### 14.1. Không cảnh báo từ raw lifetime counter

Sai về cách diễn giải:

~~~text
Alert khi rebalance-total > 100
~~~

Consumer chạy lâu sẽ tích lũy counter dù gần đây rất ổn định. Một client mới restart sẽ có counter thấp dù đang rebalance liên tục.

Nên alert theo **mức tăng/tốc độ trong một cửa sổ thời gian** và kết hợp tác động.

Ví dụ PromQL minh họa, giả sử metric name/labels thực sự tồn tại:

~~~promql
sum by (application, group_id) (
  increase(kafka_consumer_coordinator_metrics_rebalance_total[15m])
) > 10
~~~

Con số 10/15 phút là ví dụ, phải hiệu chỉnh theo số members, workload và baseline của group. Đặt `for` và severity phù hợp trong Prometheus alert rule để hạn chế alert storm.

### 14.2. Kết hợp lag hoặc throughput

Một group có nhiều rebalance nhưng vẫn đáp ứng SLO có mức độ khẩn cấp khác group mà rebalance dẫn đến mất throughput và backlog tăng.

Tư duy cảnh báo:

~~~text
Rebalance participation tăng
             |
             +-- Consumer lag tăng vượt SLO?
             |       |
             |       +-- Có -> ưu tiên xử lý cao
             |
             +-- Commit errors / retries tăng?
             |       |
             |       +-- Có -> kiểm tra correctness/redelivery
             |
             +-- Trùng thời điểm deploy/autoscaling?
                     |
                     +-- Có -> đánh giá expected churn
~~~

Một alert nên cho biết group, service, môi trường, cửa sổ thời gian, số members và links đến logs/lag dashboard.

### 14.3. Tránh ngưỡng cố định cho mọi group

Group có 2 members có mức tổng client participation khác group có 200 members. Với số members lớn, một group-level event có thể tạo nhiều client increments.

Có thể cân nhắc một chỉ số nội bộ đã được định nghĩa rõ như **client rebalance participation per active member**, nhưng denominator cần phản ánh members trung bình trong cửa sổ và được giải thích là phép chuẩn hóa, không phải "số đợt rebalance thật".

### 14.4. Missing metrics không bằng 0 rebalances

Nếu cả pod chết, rebalance-total series của nó biến mất. Một dashboard chỉ vẽ series đang còn sống có thể cho thấy mức tăng thấp giả tạo ngay lúc hệ thống thực sự bất ổn.

Cần kết hợp:

- `up` hoặc scrape health.
- Số expected/actual consumer members.
- Pod restarts.
- Group lag.
- Assignment gaps.
- Metric series freshness.

## 15. Rebalance count và rebalance duration

Hai nhóm hệ thống có thể có các chỉ số:

~~~text
Group A:
  Nhiều rebalance ngắn khi triển khai
  Lag tăng ít và giảm nhanh

Group B:
  Ít rebalance hơn
  Nhưng mỗi lần kéo dài rất lâu
  Lag tăng mạnh và recovery chậm
~~~

Chỉ nhìn count có thể coi A tệ hơn B, dù tác động thực tế ngược lại.

Một bộ chỉ số tốt gồm:

- **Frequency**: mức tăng rebalance count theo cửa sổ.
- **Duration**: latency trung bình/max hoặc percentiles khi có nguồn đo phù hợp.
- **Time spent unstable**: tỷ lệ thời gian group đang join/rebalance, nếu đo được.
- **Business impact**: throughput, end-to-end latency và consumer lag.
- **Correctness impact**: commit failures, redelivery và duplicate side effects.

Nếu client metric không cung cấp duration theo dạng histogram, không tự suy ra p99 từ `rebalance-latency-avg` hoặc `rebalance-latency-max`. Cần nguồn phân phối riêng để tính percentile.

## 16. Eager và cooperative rebalancing ảnh hưởng phép đếm

Kafka hỗ trợ các chiến lược assignment khác nhau, thường được mô tả bằng:

- **Eager rebalance**: members có thể revoke nhiều hoặc tất cả partitions trước khi nhận assignment mới.
- **Cooperative/incremental rebalance**: chỉ những partitions cần chuyển mới bị revoke theo các bước, giảm phần workload bị gián đoạn.

Khi chuyển từ eager sang cooperative:

- Một group-level change có thể có cấu trúc callbacks khác.
- Partition revocation count có thể giảm.
- Thời gian gián đoạn toàn group có thể giảm.
- Số callbacks hoặc iterations vẫn có thể thay đổi theo protocol.

Do đó, **không so sánh trực tiếp số `onPartitionsRevoked` callbacks trước/sau migration rồi gọi đó là cải thiện rebalance-total**. Cần dùng cùng metric source và so sánh cả lag/latency.

### 16.1. Assignor compatibility

Nếu các members cùng group không đồng thuận assignment strategy do version/configuration, group có thể gặp lỗi join hoặc churn. Kiểm tra `partition.assignment.strategy` hoặc cơ chế assignor của group protocol đang dùng.

Không đổi assignor đồng loạt mà chưa kiểm tra đường migration; một số nâng cấp cần triển khai qua nhiều giai đoạn để giữ compatibility.

### 16.2. Consumer group protocol mới

Khi dùng `group.protocol=consumer`, cơ chế membership và assignment có thể chuyển sang consumer group protocol mới với broker-driven coordination. Metrics và callback semantics có thể khác so với classic protocol, tùy Kafka client/broker version.

Khi migration, thiết lập baseline rebalance count/rate mới, kiểm tra metrics thực tế và không gộp hai giai đoạn khác semantics rồi suy ra hệ thống kém ổn định chỉ từ thay đổi con số.

## 17. Session timeout làm count tăng như thế nào?

Trong classic protocol, group coordinator theo dõi heartbeat của consumer. Nếu không nhận heartbeat hợp lệ đủ lâu, member có thể bị loại, group phải reassignment partitions.

Nguyên nhân thực tế:

- Broker coordinator không khả dụng.
- JVM stop-the-world GC pause kéo dài.
- CPU throttling khiến heartbeat thread không được chạy kịp.
- Network partition, DNS hoặc connection failures.
- Process crash/OOM.
- Node hoặc container bị kill đột ngột.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Consumer đang xử lý] --> B[Heartbeat không đến coordinator]
    B --> C{Vượt session timeout?}
    C -->|Không| D[Chờ heartbeat phục hồi]
    C -->|Có| E[Coordinator loại member]
    E --> F[Group reassignment partitions]
    F --> G[Client rebalance metrics/callbacks thay đổi]
    G --> H[Consumer lag/commit failure có thể tăng]
~~~

Nếu rebalance count tăng đồng thời với heartbeat errors, cần đối chiếu network/coordinator/GC trước. Tăng session timeout có thể giảm false failure do gián đoạn ngắn nhưng cũng làm phát hiện consumer chết thật chậm hơn.

Không mặc định session timeout là root cause chỉ vì một group có nhiều rebalances. Cần tìm bằng chứng member bị loại do liveness, không phải voluntary leave khi deploy.

## 18. Max poll interval và listener quá chậm

`max.poll.interval.ms` giới hạn thời gian giữa các lần consumer poll. Nếu listener processing kéo dài quá lâu, consumer có thể vi phạm poll deadline và group phải thay đổi membership.

Ví dụ:

~~~text
max.poll.interval.ms = 300000  (5 phút)

Một poll trả 500 records
Mỗi record xử lý ~ 800 ms

Tổng xử lý xấp xỉ:
  500 x 800 ms = 400000 ms (hơn 6 phút)

Consumer không quay lại poll kịp.
~~~

Với classic consumer client hiện đại, heartbeat thread có thể vẫn hoạt động trong một phần lớn thời gian listener bị block. Vì thế đây không nhất thiết là session timeout trực tiếp.

Biện pháp cần cân nhắc:

- Giảm `max.poll.records` để giảm worst-case work mỗi poll.
- Tối ưu database I/O hoặc xử lý batch theo transaction phù hợp.
- Đặt timeout cho HTTP/database calls.
- Giới hạn retry blocking trên consumer thread.
- Điều chỉnh concurrency phù hợp số partitions và downstream capacity.
- Chỉ tăng `max.poll.interval.ms` khi có số đo processing duration và recovery SLO cụ thể.

### 18.1. Static membership

Với static member (`group.instance.id`), khi quá max poll interval, consumer có thể ngừng heartbeat thay vì lập tức nhả assignment; sau đó coordinator đợi session timeout để reassignment. Log cuối cùng có thể nói session expired, trong khi gốc rễ là listener không poll kịp.

Vì thế khi biểu đồ rebalance count tăng, đối chiếu cả hai ngưỡng và event timeline.

## 19. Static membership giảm rebalance churn như thế nào?

Kafka static membership dùng `group.instance.id` để nhận diện consumer member logic ổn định qua một số lần restart. Điều này có thể giảm rebalance không cần thiết trong các đợt restart ngắn khi phối hợp với session timeout phù hợp.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: checkout-service
      properties:
        group.instance.id: checkout-worker-slot-0
~~~

**Không sao chép cùng một static instance ID cho nhiều consumers đang hoạt động.** Với Spring Kafka concurrency lớn hơn 1, cần hiểu cơ chế child consumer IDs và suffix theo phiên bản; mỗi static member phải có identity hợp lệ riêng.

Static membership không bảo đảm zero rebalances:

- Scale thêm members thực sự có thể cần assignment mới.
- Member chết lâu hơn session timeout vẫn có thể bị loại.
- Partition/subscription changes vẫn có thể cần rebalance.
- Group protocol/assignor migration vẫn ảnh hưởng assignment.

Nếu giảm rebalance count nhờ static membership nhưng kéo dài session timeout quá lớn, group có thể phục hồi rất chậm khi consumer chết thực sự. Cần đo **time to recover partition ownership** cùng rebalance frequency.

## 20. Offset commit failure và data correctness

Rebalance count không chỉ là performance metric; trong một số luồng processing, nó liên quan đến **at-least-once delivery**.

~~~text
Consumer A poll offset 100
      |
      v
Listener cập nhật database thành công
      |
      +-- Group rebalance xảy ra
      |
      v
A cố commit offset 101 nhưng mất quyền sở hữu
      |
      v
Offset commit có thể thất bại
      |
      v
Consumer B nhận partition, đọc lại offset 100
~~~

Nếu application không idempotent, record có thể tạo side effect lặp. Rebalance không tự xóa record hoặc làm Kafka exactly-once; nó làm thay đổi consumer member sở hữu partition.

### 20.1. Những metric nên đối chiếu

- Offset commit failures.
- Listener processing errors.
- Redelivery/retry attempts.
- DLT published count/failure count.
- Database unique conflict/inbox duplicate count.
- Consumer lag.
- Rebalance duration.
- Partition lost callbacks.

### 20.2. Idempotent consumer

Với database side effect, cần event ID ổn định, unique inbox key hoặc business operation ID, và database transaction bao gồm việc ghi inbox cùng domain update.

Kafka transaction có thể phối hợp Kafka output và source offset trong consume–process–produce, nhưng không tự bảo đảm database/HTTP side effects chỉ chạy một lần.

**Không đặt alert chỉ theo rebalance count mà bỏ qua correctness signals.** Một group có ít rebalances vẫn có thể mất dữ liệu nếu commit offset sớm; một group rebalance thường xuyên nhưng idempotent có thể giữ correctness, dù latency kém.

## 21. Rebalance count trong Kubernetes

Trong Kubernetes, nhiều vấn đề môi trường có thể làm rebalance count tăng:

### 21.1. Rolling deployment

Khi pod cũ rời group và pod mới tham gia, assignment thay đổi là hành vi có thể mong đợi. Dashboard nên có deployment markers để phân biệt churn chủ đích với churn bất thường.

Không ẩn toàn bộ cảnh báo trong suốt deployment; vẫn cần biết group có khôi phục ổn định sau rollout hay không.

### 21.2. HPA dao động

Nếu Horizontal Pod Autoscaler liên tục tăng/giảm replicas quanh một ngưỡng, consumer group có thể join/leave liên tục.

Các giải pháp có thể gồm HPA stabilization window, scale behavior phù hợp, baseline CPU/lag và tránh scale vượt partition parallelism mà không có ích.

### 21.3. CPU throttling/GC

Pod không đủ CPU hoặc JVM GC pause dài có thể gây heartbeat failures hoặc poll deadline violations. Rebalance count tăng cùng CPU throttling và JVM pause là tín hiệu cần kiểm tra resource limits.

### 21.4. Readiness và shutdown

Readiness không phải consumer group membership. Một pod có thể bị đánh dấu not-ready nhưng process Kafka consumer vẫn sống và join group, tùy application lifecycle.

Graceful shutdown cần cho listener container thời gian dừng theo policy để giảm unexpected partition loss. Nhưng stop/start thành công vẫn có thể gây assignment change; không có bảo đảm luôn "zero rebalance".

### 21.5. Trùng client ID hoặc thiếu labels

Nếu nhiều pods xuất metrics với cùng client ID và exporter không gắn instance/pod labels, series có thể bị merge hoặc ghi đè sai. Cần giữ **instance identity** ở monitoring, đặc biệt với counter reset và scale events.

## 22. Điều tra khi rebalance count tăng đột biến

Một runbook theo thứ tự:

1. Xác định chính xác metric đang xem: Kafka client rebalance-total hay custom callback counter.
2. Xác định group ID, service, môi trường, khoảng thời gian và số active members.
3. Đối chiếu số series hiện có với số consumers thực tế.
4. Kiểm tra counter reset/restart để loại trừ cách tính dashboard sai.
5. Kiểm tra deployment, rollout, HPA, manual scale và topic partition changes.
6. Tìm log join/leave group, member removed, coordinator discovery và assignment.
7. Kiểm tra heartbeat failures, session timeout và network errors.
8. Kiểm tra poll interval violations, listener duration p95/p99, batch size và blocking retries.
9. Kiểm tra JVM GC pauses, CPU throttling, OOM/restarts.
10. Kiểm tra broker coordinator health và metadata changes.
11. Đối chiếu rebalance latency, consumer lag, throughput và commit failures.
12. Kiểm tra idempotency/retries/DLT nếu có bằng chứng redelivery.
13. Xác định root cause rồi thay đổi từng nhóm cấu hình có kiểm soát.
14. Sau thay đổi, đo lại cùng metric, cùng grouping và cửa sổ quan sát.
15. Ghi nhận quyết định, tác động SLA và điều kiện rollback.

Một bản phân loại ngắn:

~~~text
Rebalance count tăng?
  |
  +-- Trùng deployment/scale?
  |      -> Member churn chủ đích hay HPA dao động?
  |
  +-- Heartbeat/session errors?
  |      -> Network, coordinator, GC, CPU
  |
  +-- Max poll interval exceeded?
  |      -> Listener/batch/IO/retry quá lâu
  |
  +-- Không rõ nguyên nhân?
         -> Group protocol, assignor, metadata changes,
            client metrics labels/reset, coordinator logs
~~~

Không thay cùng lúc session timeout, max poll interval, concurrency và assignment strategy: nếu chỉ số giảm, sẽ không biết thay đổi nào thực sự có tác dụng.

## 23. Rebalance count cao có luôn là lỗi không?

Không. Ví dụ:

- Trong một deployment có kiểm soát, group rebalance vài lần rồi ổn định.
- Khi nhóm consumer mở rộng lần đầu, các members join và nhận assignment.
- Khi topic mới hoặc partitions mới được thêm vào, assignment cần thay đổi.
- Khi một consumer chết thật, rebalance là **cơ chế phục hồi cần thiết**, không phải bug.

Rebalance count cao trở thành vấn đề khi nó:

- Lặp liên tục ngoài các thay đổi mong đợi.
- Làm phần đáng kể thời gian group nằm trong trạng thái chưa ổn định.
- Gây lag vượt SLO.
- Gây commit failures, redelivery và side effect trùng không được kiểm soát.
- Gây partition ownership thrashing, cache warm-up liên tục hoặc throughput giảm rõ rệt.

Do vậy, dashboard nên hiển thị **thời điểm deployment** cạnh rebalance graph. Không dùng một cảnh báo "rebalance total > 0" cho mọi group production.

## 24. Các chiến lược giảm rebalance không cần thiết

### 24.1. Sửa nguyên nhân liveness

Nếu có session timeout:

- Kiểm tra broker availability và coordinator health.
- Sửa mạng, DNS, service endpoint và connection stability.
- Giảm JVM pause và CPU throttling.
- Cân nhắc session timeout phù hợp với jitter thực tế và failover SLO.

Không tăng session timeout vô hạn; member chết thật sẽ mất lâu hơn để được phát hiện.

### 24.2. Giữ vòng poll đúng hạn

Nếu có max poll interval:

- Giảm công việc mỗi poll hoặc xử lý tối ưu.
- Đặt timeout downstream.
- Tránh blocking retry quá dài không có giới hạn.
- Giới hạn queue/inflight tasks và dùng backpressure phù hợp.
- Đo p99 listener processing, không chỉ average.

### 24.3. Giảm membership churn

- Tránh autoscaling dao động.
- Sử dụng rolling update/shutdown lifecycle nhất quán.
- Dùng static membership khi yêu cầu và ownership model phù hợp.
- Không chạy số consumers vượt quá partitions một cách vô nghĩa.
- Kiểm tra client/protocol/assignor compatibility khi nâng cấp.

### 24.4. Cooperative rebalance

Khi hệ thống và client hỗ trợ, cooperative assignment có thể giúp giảm phạm vi partition revocation và thời gian gián đoạn, đặc biệt với group lớn.

Tuy nhiên, cooperative không chữa lỗi process crash, GC freeze hoặc network partition. Nó là một **tối ưu cách chuyển assignment**, không thay thế giải pháp cho nguyên nhân rebalances.

### 24.5. Đo tác động thay vì tối ưu số đếm mù quáng

Một thay đổi có thể làm rebalance count thấp hơn nhưng recovery time sau crash tăng gấp đôi. Cần đánh giá cả:

- Failover time.
- Consumer lag và backlog drain time.
- Processing latency.
- Duplicate handling.
- Số lần group thực sự không ổn định.
- Tải broker/coordinator.

## 25. Kiểm thử rebalance count

Các bài thử nên dùng Kafka test cluster/group riêng, không chủ động gây churn trên production để đo metric.

### 25.1. Baseline ổn định

1. Chạy một consumer group với số members cố định.
2. Chờ assignment ổn định.
3. Thu thập Kafka client `rebalance-total` và `rebalance-rate-per-hour`.
4. Không thay đổi replicas, subscription hoặc partition count.
5. Kiểm tra metric tăng ít hoặc không tăng ngoài điều kiện gây rebalance thực tế.
6. Quan sát consumer lag và processing throughput.

### 25.2. Member join

1. Chạy group với một member.
2. Ghi lại counter trước khi có thêm member.
3. Khởi động member thứ hai.
4. Quan sát assignment thay đổi và client rebalance metrics.
5. Ghi nhận số client counters tăng.
6. Xác nhận không suy ra group rebalance count bằng tổng client deltas.

### 25.3. Graceful leave

1. Chạy hai members.
2. Dừng một member qua container lifecycle bình thường.
3. Quan sát group còn lại reassignment partitions.
4. Ghi nhận callbacks, lag và rebalance latency.
5. Phân biệt voluntary leave với session timeout.

### 25.4. Session timeout

1. Trong môi trường test, mô phỏng member không heartbeat đến coordinator.
2. Chờ group xử lý membership expiration.
3. Quan sát broker/client logs và rebalance metrics.
4. Xác nhận partition được reassigned.
5. Kiểm tra redelivery theo committed offset và idempotency.

### 25.5. Max poll interval

1. Cho test listener chạy lâu hơn `max.poll.interval.ms`.
2. Giữ network/coordinator bình thường để tách nguyên nhân.
3. Quan sát log poll interval và group membership.
4. Kiểm tra counter thay đổi khi rebalance.
5. Giảm workload hoặc chỉnh giới hạn có cơ sở rồi đo lại.

### 25.6. Consumer restart và Prometheus counter reset

1. Thu thập một vài samples của `rebalance-total`.
2. Restart consumer.
3. Xác nhận raw counter lifecycle mới có thể thấp hơn trước.
4. Kiểm tra PromQL `increase()`/`rate()` và labels instance/client.
5. Bảo đảm dashboard không diễn giải reset là "rebalance count âm" hoặc nhóm vừa ổn định hơn.
6. Kiểm tra mất scrape samples khi process down.

### 25.7. Cooperative và eager

1. Tạo nhóm test phù hợp từng assignor/protocol.
2. Cho một member join/leave.
3. Ghi nhận rebalance metrics, callbacks và partitions affected.
4. Đối chiếu duration và backlog, không chỉ callback count.
5. Nếu migrate protocol/assignor, thiết lập baseline lại sau khi xác nhận semantics.

Không chạy Content QA/code test khi nhiệm vụ của worker chỉ là soạn Markdown STEP 4; các kịch bản trên là kiến thức kiểm thử cho người học.

## 26. Những lỗi diễn giải thường gặp

**Gộp rebalance-total của mọi consumer rồi gọi là group event count:** một đợt của group có thể làm nhiều clients tăng counter.

**Đếm onPartitionsAssigned như rebalance-total chính thức:** callback count và client metric không tương đương.

**Coi raw counter lớn là sự cố:** counter tích lũy cả vòng đời; phải xem tốc độ và mức tăng gần đây.

**Bỏ qua counter reset sau restart:** dashboard có thể sai khi client ID/instance thay đổi.

**Chỉ nhìn một child consumer:** concurrent listener container có nhiều KafkaConsumers.

**Trộn các group IDs:** metrics một ứng dụng có thể gồm nhiều consumer groups.

**Không xác định exporter series name:** metric Prometheus có thể khác tên minh họa theo JMX exporter/Micrometer.

**Không xác định group protocol:** classic và consumer protocol có cách heartbeat/session, assignment và metrics khác nhau.

**Cho rằng cooperative không còn rebalance:** vẫn cần membership/assignment reconciliation khi group thay đổi.

**Coi rebalance count tăng sau deployment là bug:** có thể là lifecycle change hợp lệ.

**Tăng timeout chỉ để giảm count:** có thể làm failover chậm và giấu resource issue.

**Không xem max.poll.interval.ms:** listener dài có thể gây group churn dù heartbeat không mất ngay.

**Không xem pod restarts hoặc HPA:** churn có thể do môi trường, không phải Kafka broker.

**Coi rebalance count thấp là đã có exactly-once:** offset commit, retry và idempotency là các vấn đề riêng.

**Không gắn label instance/client:** series có thể merge sai hoặc mất counter khi scale.

**Dùng client metric để suy ra số bản ghi chưa xử lý:** rebalance count không phải backlog; cần consumer lag.

**Đếm mỗi partition trong revoke event như một lần group rebalance:** số partitions bị ảnh hưởng là metric khác.

## 27. Quy trình triển khai monitoring chuẩn

Một cách triển khai có thể theo các bước:

1. **Chọn đúng nguồn dữ liệu:** Kafka consumer client metrics cho rebalance count; Spring callback metrics cho partition lifecycle; coordinator logs khi cần group-level context.
2. **Xác nhận metrics thực tế:** liệt kê JMX/Actuator/Prometheus series của client version hiện hành.
3. **Giữ nhãn phân biệt:** application, environment, group ID, client ID và pod/instance.
4. **Dùng counter semantics:** tính `increase()` hoặc `rate()`, xử lý resets và missing scrapes.
5. **Đặt tên dashboard trung thực:** "client rebalance participation" nếu đang tổng hợp client counters.
6. **Thêm latency và impact:** rebalance latency, lag, throughput, commit failures, restarts.
7. **Gắn operational timeline:** deploys, HPA actions, topic changes, broker changes.
8. **Thiết lập baseline:** mức bình thường theo workload và số members.
9. **Đặt alert theo cửa sổ:** có điều kiện SLO/impact, không chỉ raw lifetime total.
10. **Viết runbook:** phân loại member churn, heartbeat/session timeout, poll interval và coordinator problems.
11. **Kiểm thử fault injection:** join/leave, restart, timeout và metric resets.
12. **Rà soát sau migration:** client version, group protocol, assignor và dashboard labels có thể thay đổi.

## 28. Kết luận

**Rebalance count** là một chỉ số quan trọng để theo dõi tính ổn định của Kafka consumer group trong Spring Kafka, nhưng giá trị chỉ hữu ích khi xác định rõ **ai đang đếm**: KafkaConsumer client, Spring rebalance callback hay broker/group coordinator.

Trong nhiều triển khai, `rebalance-total` và `rebalance-rate-per-hour` của Kafka client là điểm bắt đầu tốt. Khi quan sát qua Prometheus, hãy phân tích mức tăng/tốc độ theo cửa sổ thời gian, chú ý counter reset sau restart và không gọi tổng client increments là số group rebalances duy nhất. Đối chiếu với rebalance latency, consumer lag, offset commit errors, JVM/resource health và lịch triển khai để phân biệt churn hợp lệ với incident.

Mục tiêu vận hành không phải đưa rebalance count về 0 bằng mọi giá. Mục tiêu là **consumer group phục hồi đúng khi membership thay đổi, giữ throughput/latency trong SLO và không lặp side effect nghiệp vụ ngoài kiểm soát**.
