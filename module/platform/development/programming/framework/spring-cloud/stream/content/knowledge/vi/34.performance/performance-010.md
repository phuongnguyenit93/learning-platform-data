# So sánh cấu hình bằng số đo thay vì chỉ tăng số luồng

Trong Spring Cloud Stream, việc tăng `consumer.concurrency` từ 1 lên 4 hoặc 16 có thể làm ứng dụng xử lý nhanh hơn, **nhưng cũng có thể không tăng throughput**, làm tăng độ trễ p99, áp lực lên database, bộ nhớ và số lần retry. Concurrency chỉ là một tham số trong hệ thống gồm producer, broker, partition, consumer, logic nghiệp vụ và các dịch vụ phụ thuộc.

Bài học này trình bày cách thiết kế phép đo, so sánh các cấu hình và chọn phương án có hiệu quả thực tế. Trọng tâm là ứng dụng xử lý sự kiện bằng mô hình hàm `Supplier`/`Function`/`Consumer` của Spring Cloud Stream, chạy qua Kafka, RabbitMQ hoặc Pulsar binder, kể cả topology có trạng thái của Kafka Streams. Mục tiêu không phải tìm giá trị luồng lớn nhất mà là đạt **mức tải cần thiết với độ trễ, độ tin cậy, tài nguyên và chi phí chấp nhận được**.

Ví dụ xuyên suốt: dịch vụ `order-projection` nhận `OrderCreated`, kiểm tra dữ liệu, ghi projection vào PostgreSQL và có thể phát `OrderProjected`. Khi lưu lượng tăng, consumer lag tích lũy. Cần đo trước khi quyết định tăng consumer, thêm partition, thay batch size hay tối ưu database.

## 1. Hiệu năng là một hệ thống, không phải một biến

Đường đi thông thường:

~~~text
Producer
  |
  | serialization, batching, compression, acks
  v
Broker (Kafka topic / Rabbit queue / Pulsar topic)
  |
  | partition, dispatch, fetch/prefetch, subscription
  v
Spring Cloud Stream input binding
  |
  | conversion, headers, retry policy
  v
Consumer / Function
  |
  | CPU, allocation, DB calls, HTTP calls, lock
  v
Output binding / ack / offset commit
  |
  v
Downstream service and storage
~~~

Throughput cuối cùng bị giới hạn bởi nút thắt hiện tại. Nếu PostgreSQL chỉ nhận được khoảng 1.200 thao tác ghi/giây, tăng số consumer có thể khiến nhiều request tranh chấp connection pool hơn mà không cải thiện số event xử lý thành công.

Tối ưu cần phân biệt:

| Tầng | Tham số thường thử | Giới hạn có thể gặp |
|---|---|---|
| Producer | `linger.ms`, `batch.size`, compression, acks | CPU nén, băng thông, thời gian chờ batch |
| Broker | Partition, replication, quota, storage | I/O, network, leader hoặc queue hotspot |
| Consumer | Concurrency, số replica, fetch/prefetch | Partition assignment, queue dispatch, RAM |
| Function | Chuyển đổi payload, batch logic, allocation | CPU, GC, đồng bộ hóa |
| Downstream | Batch writes, connection pool, indexes | Transaction lock, pool, rate limit |
| Error path | Retry/backoff/DLQ | Retry storm, poison message, duplicate |
| Stateful processing | Streams thread, cache, state store | RocksDB I/O, restore, changelog, key skew |

Không thể kết luận cấu hình tốt chỉ từ tốc độ gọi function. Nếu output không được lưu bền vững hoặc message lỗi bị bỏ qua, con số ấy không đại diện cho nghiệp vụ hoàn thành.

## 2. Xác định mục tiêu và ràng buộc trước khi đo

Trước khi tune, viết rõ **SLO** (mục tiêu vận hành) và ràng buộc chức năng:

- Lưu lượng mục tiêu: ví dụ 1.500 event/giây ổn định và 3.000 event/giây trong 10 phút.
- Độ trễ: p95 dưới 250 ms, p99 dưới 800 ms, đo ở ranh giới đã thống nhất.
- Backlog: không tăng liên tục ở lưu lượng ổn định; sau burst phải hồi phục trong thời hạn yêu cầu.
- Tính đúng: không mất event; xử lý trùng theo chính sách idempotency; thứ tự theo `orderId` nếu nghiệp vụ yêu cầu.
- Lỗi: tỷ lệ lỗi nghiệp vụ, retry và DLQ dưới ngưỡng định nghĩa.
- Tài nguyên: giới hạn CPU, RAM, database connections, chi phí/triệu event.
- An toàn: không đổi delivery guarantee hay bỏ qua acknowledgment chỉ để đạt chỉ số cao.

Nếu chưa có mục tiêu, cấu hình nhanh nhất trong một bài test có thể không phải cấu hình phù hợp khi triển khai. Ví dụ phương án đạt 4.000 event/giây nhưng p99 trên 5 giây không đáp ứng hệ thống cần phản hồi gần thời gian thực.

## 3. Phân biệt throughput, latency, lag và backlog

Bốn khái niệm đo những điều khác nhau:

| Chỉ số | Ý nghĩa | Đơn vị thường dùng |
|---|---|---|
| Input rate | Message producer tạo/gửi vào broker | event/s |
| Processing rate | Event được ứng dụng xử lý thành công | event/s |
| Output rate | Event được ghi ra sink hoặc phát output thành công | event/s |
| Latency | Thời gian từ mốc A đến mốc B | ms, p50/p95/p99 |
| Kafka consumer lag | Chênh lệch giữa offset cuối và offset tiêu thụ/commit tùy metric | records |
| RabbitMQ ready/unacked | Message đang chờ giao / đã giao chưa ack | messages |
| Pulsar backlog | Message còn backlog theo subscription | messages |
| Error/DLQ rate | Thất bại và chuyển sang luồng lỗi | event/s, % |

Một ứng dụng có latency xử lý function chỉ 20 ms vẫn có end-to-end latency vài phút nếu message nằm trong broker lâu. Ngược lại, Kafka lag bằng 0 lúc không có traffic không chứng minh ứng dụng chịu được burst.

Cần đo ít nhất ba loại thời gian khác nhau:

1. **Queue waiting time:** từ khi message sẵn sàng ở broker đến khi consumer bắt đầu xử lý.
2. **Business processing time:** từ khi function bắt đầu đến khi xử lý nghiệp vụ kết thúc.
3. **End-to-end latency:** từ mốc event được tạo/phát đến khi side effect hoặc output được xác nhận theo tiêu chí test.

Chọn mốc cụ thể: timestamp ở producer, thời điểm broker nhận, thời điểm consumer nhận, và thời điểm database transaction commit. Nếu máy chủ có clock skew, độ trễ tính bằng hiệu timestamp từ nhiều máy có thể sai; đồng bộ thời gian hoặc dùng trace có clock discipline và xác minh sai lệch.

## 4. Các công thức giúp đọc số liệu đúng

Với khoảng đo \(\Delta t\):

\[
\text{Throughput thành công} =
\frac{\text{số event hoàn thành hợp lệ}}{\Delta t}
\]

Với hệ thống ổn định và đơn vị nhất quán, Little's Law cho biết:

\[
L \approx \lambda W
\]

Trong đó \(L\) là số công việc trung bình đang tồn tại trong hệ thống, \(\lambda\) là tốc độ công việc hoàn thành ổn định và \(W\) là thời gian trung bình một công việc ở trong hệ thống. Không áp dụng máy móc khi hàng đợi đang tăng vô hạn hoặc tải thay đổi liên tục.

Nếu producer tạo \(\lambda\) event/giây và consumer hoàn thành \(\mu\) event/giây:

- \(\mu < \lambda\): backlog có xu hướng tăng khoảng \(\lambda-\mu\) event/giây.
- \(\mu = \lambda\): năng lực sát tải, ít dự phòng cho burst và retry.
- \(\mu > \lambda\): có khả năng thu hẹp backlog, nếu downstream không thay đổi.

Với backlog đầu kỳ \(B\) và tốc độ ổn định \(\mu>\lambda\), thời gian xả backlog xấp xỉ:

\[
T_{\text{drain}} \approx \frac{B}{\mu-\lambda}
\]

Ví dụ thuần minh họa: backlog 120.000 event, input tiếp tục 800 event/s và consumer hoàn thành 1.000 event/s; tốc độ xả ròng 200 event/s, cần khoảng 600 giây (10 phút) nếu các giả định giữ nguyên. Không dùng công thức này khi retry, throttling hoặc key skew làm throughput biến động lớn.

## 5. p95 và p99 quan trọng hơn một giá trị trung bình

Giả sử hai cấu hình có độ trễ xử lý trung bình gần bằng nhau:

| Cấu hình | Avg | p95 | p99 |
|---|---:|---:|---:|
| A | 45 ms | 100 ms | 160 ms |
| B | 44 ms | 115 ms | 850 ms |

B có average thấp hơn nhưng tail latency tệ hơn nhiều. Một số ít event có thể đang chờ khóa database, GC pause hoặc retry. Với dịch vụ cần p99 dưới 300 ms, A phù hợp hơn.

Chỉ số percentiles cần thống nhất khoảng thời gian tổng hợp và ranh giới đo. Không lấy trung bình các p99 của từng phút để suy ra p99 của cả bài test. Hãy tổng hợp histogram hoặc dữ liệu phân phối tương ứng, với cấu hình histogram nhất quán giữa các lần chạy.

Đừng chỉ đo p95 của function nếu SLO áp dụng cho hành trình từ publish đến lưu bền vững. Một system chạy nhanh trong function nhưng đọng hàng ở broker vẫn có end-to-end p95 rất cao.

## 6. Thiết lập baseline có thể lặp lại

Một baseline là kết quả của cấu hình hiện tại trong điều kiện đã kiểm soát:

~~~text
Build:            cùng commit và JVM
Binder:           cùng phiên bản
Broker:           cùng cluster/partition/replication
Consumer group:   xác định rõ và có offset bắt đầu tương đương
Payload:          cùng kích thước, phân phối key và tỷ lệ lỗi
Downstream:       cùng database dataset, index, pool và giới hạn
Environment:      cùng CPU/memory quota, số pod, network
Traffic profile:  cùng ramp-up, steady state và burst
Measurement:      cùng metrics và cửa sổ đo
~~~

Nếu lần A chạy trong một cluster rảnh và lần B chạy khi database có job backup, sự chênh lệch có thể không đến từ concurrency.

Với Kafka, chuẩn bị consumer group/offset cho mỗi lượt một cách có kiểm soát. Với RabbitMQ, chuẩn bị cùng số lượng message và trạng thái queue. Với Pulsar, giữ cùng subscription type, backlog và điểm bắt đầu. Không để một lượt tiêu thụ luôn backlog cũ còn lượt khác nhận live traffic rồi so sánh trực tiếp.

## 7. Thiết kế workload giống thực tế

Chọn ít nhất ba profile:

| Profile | Mô tả | Điều cần nhìn |
|---|---|---|
| Stable | Tốc độ gửi không đổi dưới tải dự kiến | Năng lực duy trì và headroom |
| Burst | Tốc độ tăng 2–3 lần trong vài phút | Lag tăng, p99, thời gian hồi phục |
| Recovery | Producer giảm về mức nền sau burst | Tốc độ xả backlog, retry/DLQ |

Workload nên bao gồm phân phối payload thực tế, ví dụ 60% nhỏ, 30% trung bình, 10% lớn. Nếu có 5% event cần truy cập database chậm hoặc 1% phát sinh retry thì test cũng phải có, với tỷ lệ và nguyên nhân được ghi nhận.

Kiểm tra phân phối key. Nếu mọi message cùng `customerId`, tăng consumer sẽ không cải thiện parallelism theo key cho những hệ thống phải bảo toàn thứ tự. Một benchmark dùng key ngẫu nhiên đều có thể đẹp nhưng khác workload production bị hot key.

Giữ seed của dữ liệu giả lập, kích thước message, key cardinality và tỷ lệ lỗi cố định cho từng so sánh.

## 8. Đo ở nhiều tầng để định vị nút thắt

Bộ số đo tối thiểu:

| Tầng | Metrics cần thu |
|---|---|
| Producer | send rate, ack latency, error/retry rate, bytes/s, batch size |
| Broker | ingress/egress, request latency, storage/network, throttle, partition distribution |
| Consumer | records/s, lag/backlog, poll/fetch behavior, rebalance, redelivery |
| Function | successful events/s, failure ratio, duration p50/p95/p99 |
| Database/API | query latency, pool active/waiting, lock waits, timeout/rate limit |
| JVM | process CPU, heap, GC pause, allocation, thread count |
| Container/node | CPU throttling, memory limit, network, disk I/O |
| Business | số event thực sự đã commit/output, duplicate, DLQ |

Ví dụ Kafka binder có Micrometer metric `spring.cloud.stream.binder.kafka.offset` phản ánh lag theo topic và group ở góc độ binder. Kafka client cũng có metric như `records-consumed-rate` và `records-lag-max`. Phải đọc mô tả metric: có metric dựa vào committed offset, có metric thể hiện tiến độ fetch/poll, nên hai biểu đồ không nhất thiết trùng nhau.

Với RabbitMQ, phân biệt `messages_ready` (chưa giao) và `messages_unacknowledged` (đã giao nhưng chưa ack). Với Pulsar, quan sát backlog theo subscription, unacked, redelivery và tốc độ dispatch/ack. Đừng dùng một loại metric Kafka để suy ra ý nghĩa tương đương tuyệt đối trên RabbitMQ/Pulsar.

## 9. Bật Actuator và Micrometer

Với Spring Boot, có thể dùng Actuator và Prometheus registry để thu JVM, system và custom application metrics.

Maven (để Spring Boot quản lý phiên bản):

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
  <groupId>io.micrometer</groupId>
  <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Cấu hình ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Khi registry có trên classpath và endpoint được expose đúng cách, truy cập `/actuator/metrics` để xem meter name và `/actuator/prometheus` để hệ thống quan sát scrape. Cần bảo vệ management endpoint trong production; không mở toàn bộ metrics ra Internet.

Có thể thử:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/jvm.memory.used
curl http://localhost:8080/actuator/prometheus
~~~

Tên meter trong Actuator giữ dạng Micrometer như `jvm.memory.used`, còn dạng Prometheus thường đã được chuẩn hóa thành tên riêng. Dùng đúng hệ thống và đúng tên khi truy vấn.

## 10. Gắn custom metrics vào Consumer

Đo đúng phần logic nghiệp vụ để biết CPU/DB là nguyên nhân hay chỉ là hiệu ứng của concurrency.

Ví dụ một Consumer nhận event đơn hàng và gọi service; đo thời gian xử lý function với `Timer`, đếm kết quả thành công/thất bại:

~~~java
import java.util.function.Consumer;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
class OrderMetricsConfiguration {

    record OrderCreated(String orderId, long total) {}

    interface ProjectionWriter {
        void save(OrderCreated order);
    }

    @Bean
    Consumer<Message<OrderCreated>> projectOrder(
            ProjectionWriter writer,
            MeterRegistry registry) {

        return message -> {
            Timer.Sample sample = Timer.start(registry);

            try {
                writer.save(message.getPayload());
                registry.counter(
                    "orders.processed",
                    "outcome", "success"
                ).increment();
            } catch (RuntimeException error) {
                registry.counter(
                    "orders.processed",
                    "outcome", "failure"
                ).increment();
                throw error;
            } finally {
                sample.stop(
                    registry.timer("orders.processing.duration")
                );
            }
        };
    }
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: projectOrder
    stream:
      bindings:
        projectOrder-in-0:
          destination: orders.created
          group: order-projection
~~~

`orders.processing.duration` chỉ bao phủ lời gọi `writer.save` và overhead đo/đếm nằm trong lambda. Nó **không** tự bao gồm thời gian message xếp hàng ở broker, giao nhận network, retry sau exception hoặc commit offset/ack sau khi function trả về. Vì vậy cần kết hợp metrics broker và đo end-to-end riêng.

Không thêm `orderId` hoặc `customerId` làm label/tag: số lượng giá trị quá lớn gây bùng nổ metric cardinality. Dùng tag có số giá trị hữu hạn như `outcome`, `function`, `binding` hoặc `eventType`.

## 11. Phương pháp A/B có thể tái hiện

Không thay năm tham số rồi kết luận concurrency là nguyên nhân tăng tốc. Nên thiết kế thí nghiệm:

1. Đặt giả thuyết cụ thể: “tăng concurrency 1 lên 2 giúp giảm lag vì CPU còn rảnh và Kafka có ít nhất 2 partition”.
2. Đo A (baseline), sau đó B (một thay đổi), rồi chạy lại A để kiểm tra môi trường có trôi hay không.
3. Giữ tải, dữ liệu, resource limit, broker và downstream tương đương.
4. Dành thời gian warm-up cho JIT, connection pool, cache và consumer assignment; không tính warm-up vào steady-state.
5. Chạy đủ dài để thấy GC, retry, backlog và độ trễ tail, không chỉ burst 10 giây.
6. Lặp lại các phép đo độc lập; báo median, độ dao động hoặc khoảng tin cậy thay vì chỉ một lượt.
7. Ghi commit, cấu hình, thời điểm, dashboard/snapshot và kết quả vào experiment log.
8. Chọn cấu hình theo mục tiêu và guardrail đã đặt.

Nếu thay Kafka partition count, đó là thí nghiệm hạ tầng riêng; thay đổi này có thể ảnh hưởng key distribution và ordering. Cần ghi rõ để không so sánh như một chỉnh sửa chỉ ở tầng thread.

## 12. Bảng kết quả mẫu: nhiều luồng hơn chưa chắc tốt hơn

**Số liệu dưới đây hoàn toàn giả lập để minh họa cách đọc kết quả; không phải benchmark thật.**

Điều kiện mô phỏng: Kafka topic 6 partition, 1 instance 4 vCPU, PostgreSQL cố định, load ổn định 1.500 event/s trong 20 phút sau warm-up, không có backlog ban đầu. Phân phối payload, key và rate lỗi giữ nguyên. Vì A/B xử lý chậm hơn tốc độ đến, latency E2E phải bao gồm thời gian xếp hàng tăng dần và có thể lên đến hàng chục hoặc hàng trăm giây.

| Phương án | Consumer concurrency | Hoàn thành (event/s) | p95 E2E | p99 E2E | CPU | Lag cuối kỳ |
|---|---:|---:|---:|---:|---:|---:|
| A | 1 | 980 | 395.000 ms | 412.000 ms | 38% | Tăng mạnh |
| B | 2 | 1.420 | 62.000 ms | 66.500 ms | 63% | Tăng |
| C | 4 | 1.500 | 210 ms | 510 ms | 83% | Ổn định |
| D | 8 | 1.500 | 370 ms | 1.060 ms | 94% | Ổn định |

C bắt kịp tốc độ đến và giảm tail latency so với B. D không tăng số event hoàn thành vì đã bị giới hạn bởi input rate, nhưng CPU và p99 tệ hơn. Với 6 partition, cấu hình 8 consumer threads trong một group có thể để một số threads không có partition để xử lý; thêm overhead không tạo thêm công việc hữu ích. Các p95/p99 giả lập ở A/B phù hợp với backlog tích lũy: nếu chỉ báo p99 vài trăm mili giây khi hàng đợi tăng suốt 20 phút, rất có thể dashboard đang đo thời gian xử lý trong function thay vì E2E.

Nếu cần p99 dưới 800 ms và giữ CPU headroom, C có thể là ứng viên, nhưng vẫn cần kiểm tra ổn định, retry, cost và độ dao động giữa các lượt. Không chọn từ một bảng duy nhất.

## 13. Kafka consumer: partition đặt giới hạn thực tế

Với regular Kafka binder, mỗi partition của một topic được gán cho tối đa một consumer trong cùng group tại cùng thời điểm. Vì vậy mức song song tiêu thụ hữu ích với một topic thường bị giới hạn bởi số partition của topic đó.

Giả sử có 6 partition:

~~~text
concurrency=1
  consumer-1: P0 P1 P2 P3 P4 P5

concurrency=3
  consumer-1: P0 P1
  consumer-2: P2 P3
  consumer-3: P4 P5

concurrency=8 (cùng một group, một topic)
  consumer-1..6: mỗi consumer có thể nhận 1 partition
  consumer-7..8: không có partition để xử lý
~~~

Đây là hình minh họa đơn giản: phân công thực tế còn phụ thuộc số instance, các topic được subscribe và thuật toán assignor. Cần xét **tổng số consumer trong cùng group trên mọi replica**, không chỉ concurrency của một pod.

Nếu partition count đã đủ nhưng lag chỉ tăng ở 1–2 partition, vấn đề có thể là hot key hoặc phân phối key lệch. Tăng tổng số consumer không giải quyết hotspot nếu các record cần cùng key tiếp tục đến một partition.

## 14. Ví dụ thí nghiệm concurrency cho Kafka binder

Một Function chuyển event thành projection:

~~~java
@Bean
Function<OrderCreated, OrderProjected> projectOrder(
        OrderProjectionService service) {

    return event -> service.project(event);
}
~~~

Baseline:

~~~yaml
spring:
  cloud:
    function:
      definition: projectOrder

    stream:
      bindings:
        projectOrder-in-0:
          destination: orders.created
          group: order-projection
          consumer:
            concurrency: 1
        projectOrder-out-0:
          destination: orders.projected
~~~

Thí nghiệm B chỉ thay một tham số:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        projectOrder-in-0:
          consumer:
            concurrency: 2
~~~

Thí nghiệm C dùng `concurrency: 4`. Giữ cùng group và destination giữa các lượt, nhưng chuẩn bị vị trí offset/bộ dữ liệu tương đương cho từng lượt. Nếu số replica thay đổi, ghi thêm `replicas × concurrency` để biết tổng số consumer.

Đo ít nhất: records/s thành công, p95/p99 end-to-end, records-lag-max theo partition, consumer rebalance, CPU, GC, database pool waiting và DLT. Nếu throughput tăng nhưng lỗi lock/timeout tăng mạnh, thử nghiệm chưa thành công.

## 15. Kafka fetch, batch và producer cần đo riêng

Khi giới hạn nằm ở I/O hoặc overhead từng record, có thể thử các tham số Kafka native qua cấu hình binder:

| Tham số Kafka client | Tác dụng | Đánh đổi có thể xảy ra |
|---|---|---|
| `max.poll.records` | Giới hạn records trả về mỗi poll | Batch lớn có thể kéo dài xử lý và ảnh hưởng poll deadline |
| `fetch.min.bytes` | Số byte tối thiểu broker cố đợi cho fetch | Tăng throughput batch nhưng tăng thời gian chờ khi traffic thấp |
| `fetch.max.wait.ms` | Thời gian broker chờ đủ dữ liệu | Giảm fetch quá nhỏ, tăng latency khi ít message |
| `max.partition.fetch.bytes` | Giới hạn dữ liệu trên mỗi partition/fetch | Ảnh hưởng memory và tốc độ fetch |
| `linger.ms` | Producer đợi một khoảng để gom batch | Hiệu quả batch tốt hơn nhưng có thể tăng publish latency |
| `batch.size` | Giới hạn kích thước batch producer | Batch lớn cần thêm memory |
| `compression.type` | Nén record batch | Ít network hơn nhưng tốn CPU |

Các thay đổi này phải theo khả năng Kafka binder/client và phiên bản đang dùng. Ví dụ producer extended config:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          projectOrder-out-0:
            producer:
              configuration:
                "linger.ms": 5
                "batch.size": 32768
                "compression.type": lz4
~~~

Đây là cấu hình để đo thử, không phải preset “nhanh nhất”. Đo kích thước batch thực tế, send latency, byte/s và CPU nén trước khi áp dụng. Với consumer batch mode, payload shape và ack/retry semantics có thể đổi, nên test cả tính đúng của function.

## 16. RabbitMQ: prefetch và số consumer

RabbitMQ dùng queue và cơ chế dispatch khác Kafka. Một queue có thể có nhiều consumer nhận message theo hành vi broker, nhưng **prefetch** giới hạn số message đã giao mà chưa được ack cho consumer, giúp tránh flooding khi xử lý chậm.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder

    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: projection
          consumer:
            concurrency: 2

      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              prefetch: 20
~~~

Cần kiểm tra Rabbit binder version và listener container đang dùng. `prefetch` là extended Rabbit consumer property, còn `concurrency` là generic consumer binding property. Prefetch cao hơn giúp giữ sẵn nhiều message nhưng cũng tăng số unacked và memory; nếu consumer chậm, có thể khiến message tích lũy ở những consumer cụ thể.

Thử các tổ hợp có kiểm soát, ví dụ `(concurrency, prefetch) = (1,10), (2,10), (2,50)` thay vì bật `concurrency=20, prefetch=1000` ngay. Theo dõi queue ready, unacked, rate ack và thời gian xử lý.

Nếu workload phụ thuộc thứ tự, nhiều consumer trên một queue có thể làm thứ tự hoàn thành khác thứ tự publish. Đảm bảo semantics nghiệp vụ trước khi tăng concurrency.

## 17. RabbitMQ: thông số nào cho biết prefetch quá lớn?

Dấu hiệu prefetch quá cao:

- `messages_unacknowledged` tăng mạnh trong khi ack rate không tăng.
- Heap của consumer và số object giữ message tăng.
- Message tập trung ở một vài consumer chậm, những consumer khác rảnh.
- Thời gian chờ trước khi xử lý kéo dài, p99 tăng.
- Khi consumer chết, số message cần redeliver nhiều.

Dấu hiệu prefetch quá thấp:

- Consumer phải chờ nhận message tiếp theo sau mỗi ack, throughput thấp so với CPU rảnh.
- Network round trip/dispatch chiếm tỷ lệ lớn so với xử lý nghiệp vụ.
- Tăng prefetch vừa phải làm throughput tăng mà memory/unacked vẫn trong ngưỡng.

RabbitMQ có phân biệt message ready và unacked; tổng queue depth không đủ mô tả tình trạng. Trong chế độ manual acknowledgment, prefetch đặc biệt hữu ích để giới hạn delivery chưa ack.

Nếu bật consumer-side batching của Rabbit binder, có thể thử `batch-mode`, `enable-batching`, `batch-size` và `receive-timeout` theo tài liệu binder. Nhưng lúc đó API nhận `List<...>` và xử lý batch/error cần được thiết kế riêng; không chuyển sang batch mode chỉ bằng thay một biến YAML mà không kiểm tra kiểu function.

## 18. Pulsar: subscription type, receiver queue và partition

Với Pulsar binder, `group` của Spring Cloud Stream tương ứng danh tính subscription; `subscription.type` điều khiển cách các consumer trong subscription nhận message.

| Type | Hệ quả khi scale |
|---|---|
| Exclusive | Một consumer gắn vào subscription; thêm replica không tăng consumer active |
| Failover | Có standby; với partitioned topic có thể có active theo từng partition |
| Shared | Nhiều consumer active; không bảo đảm thứ tự |
| Key_Shared | Phân phối theo key, giữ thứ tự theo key theo semantics broker |

Pulsar có receiver queue và batching ở client. Tăng buffer/receiver queue có thể giảm chờ nhận nhưng tăng in-flight memory. Hiệu quả phụ thuộc message size, số partition, subscription type, xử lý key và consumer memory limit.

Thay vì giả định một property native luôn có cùng tên trên mọi phiên bản, hãy lấy cấu hình Pulsar consumer được **Spring Boot/Spring for Apache Pulsar** và binder version hỗ trợ. Pulsar binder cho phép override ở cấp extended binding, theo cấu trúc:

~~~text
spring.cloud.stream.pulsar.bindings.<input-binding>.consumer.*
~~~

Ví dụ chỉ định Shared subscription:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://acme/orders/orders-created
          group: order-projection

      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription:
                type: Shared
                mode: Durable
~~~

Kiểm tra tính đúng của ordering và idempotency khi đổi subscription type; đây là thay đổi semantics, không thuần túy là tuning tốc độ. Với Key_Shared, producer phải dùng key ổn định và batching tương thích (tắt batching hoặc key-based batching theo hướng dẫn Pulsar).

## 19. Kafka Streams: số thread và state store

Kafka Streams không nên được benchmark như một Consumer không trạng thái. Nó xử lý task gắn với partition, có thể materialize state store, changelog và phục hồi trạng thái khi rebalance.

Một cách cấu hình concurrency cho Kafka Streams binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              "num.stream.threads": 2
~~~

Với functional Kafka Streams binder, generic `spring.cloud.stream.bindings.<first-input>.consumer.concurrency` cũng có thể được ánh xạ thành `num.stream.threads`. Nếu function có nhiều input binding, theo tài liệu cần cấu hình concurrency trên input đầu tiên khi dùng cách generic. Đừng cấu hình hai nguồn cho cùng mục đích với giá trị xung đột.

Trước khi tăng thread, đo:

- Số stream task/partition có thể xử lý song song.
- `process-rate` và latency theo task/processor nếu có.
- CPU, GC và RocksDB/state-store I/O.
- Changelog traffic, state restoration time và rebalances.
- Mức lệch key và kích thước state store.
- Tác động của caching, commit interval và suppression tới độ trễ đầu ra.

Một topic chỉ có 2 partition thường không tạo thêm công việc stream task hữu ích khi tăng thread từ 2 lên 8 cho cùng topology. Thêm thread cũng không sửa hot key; có thể làm tăng overhead và memory.

## 20. Đừng đánh đổi đúng/sai để có con số đẹp

Một số thay đổi có thể tạo “tăng throughput” giả:

- Không chờ producer acknowledgement rồi đếm message là đã thành công.
- Tự động ack trước khi database transaction hoàn tất.
- Bỏ retry hoặc cho message lỗi đi thẳng tới DLQ nhưng chỉ đếm successful path.
- Bật parallel processing làm sai thứ tự theo `orderId`.
- Tăng batch nhưng không đảm bảo transaction/idempotency khi batch xử lý một phần.
- Tắt changelog hoặc đổi exactly-once guarantee mà không ghi vào so sánh.
- Đổi schema/serialization làm message nhỏ hơn nhưng làm mất dữ liệu.

Báo cáo hiệu năng phải đi cùng kiểm tra data correctness: số event đầu vào, thành công, lỗi, retry, DLQ, duplicate, và output đã được lưu. Tốt hơn là 1.500 event/s đúng và phục hồi được thay vì 3.000 event/s nhưng âm thầm mất 1% event.

## 21. Retry, DLQ và failure injection

Để benchmark gần thực tế, tạo lỗi có kiểm soát:

- Database trả timeout trong 1% request.
- Broker trả lỗi tạm thời hoặc mất kết nối ngắn.
- Một số event sai schema vào DLQ.
- Consumer restart giữa lúc đang xử lý.
- Downstream chậm trong khoảng 2 phút.

Đo retry rate, thời gian backoff, redelivery, DLQ và ảnh hưởng lên p95/p99 của event không lỗi. Nếu concurrency tăng nhưng exception rate cũng tăng do database pool cạn, throughput thành công có thể giảm.

Tách ba dòng số:

\[
N_{\text{input}} = N_{\text{success}} + N_{\text{dead-letter}} + N_{\text{pending}}
\]

Đây là phương trình kiểm kê đơn giản cho một cửa sổ đã được kiểm soát, với mỗi event được tính một lần theo trạng thái cuối kỳ. Retry attempt và duplicate delivery không phải event mới. Trong thực tế cần thêm trạng thái filtered/expired nếu hệ thống có chủ đích loại bỏ event.

## 22. CPU, memory, GC và connection pool

Khi tăng concurrency, số yêu cầu đồng thời tới database/API thường tăng. Hãy đối chiếu:

| Tín hiệu | Giả thuyết | Thí nghiệm tiếp theo |
|---|---|---|
| CPU cao, lag tăng | Xử lý CPU-bound hoặc serialization | Profile CPU, tối ưu code, compression |
| CPU thấp, DB pool pending cao | Chờ kết nối database | Điều chỉnh pool/query, không vội thêm consumer |
| CPU throttling tăng | Container thiếu CPU quota | Thử quota phù hợp trước khi tăng threads |
| Heap/GC pause tăng | Prefetch/buffer/batch quá lớn | Giảm in-flight, kiểm tra allocation |
| Throttle từ broker | Quota hoặc broker saturation | Đo broker request/storage/network |
| Một partition lag tăng | Hot key / skew | Đo per-partition, cân nhắc key strategy |
| DLT tăng sau scale | Downstream quá tải | Cô lập nguyên nhân lỗi và điều tiết |

`concurrency` trong Spring Cloud Stream không tự tăng `maximumPoolSize` của HikariCP, cũng không thêm CPU thật vào pod. Nếu 8 consumer chia sẻ pool 4 connection và mỗi event cần 3 query, waiting time có thể tăng dù có thêm threads.

Không tăng đồng thời consumer threads, DB pool và pod count trong một vòng test nếu cần biết thay đổi nào mang lại hiệu quả.

## 23. Tối ưu partition và key có điều kiện

Khi đã đo chứng minh partition là giới hạn, có thể xem xét tăng partition count hoặc thay chiến lược chọn key. Tuy nhiên:

- Tăng Kafka partition có thể đổi hash-to-partition của key và ảnh hưởng ordering của các message cùng key qua thời điểm thay đổi.
- Kafka Streams cần cân nhắc repartition, changelog, restore và trạng thái địa phương.
- Pulsar partitioned topic có thể scale throughput nhưng cần kiểm tra subscription, routing key và ordering.
- RabbitMQ không có Kafka partition semantics; mô hình queue/super stream/plugin cần được đánh giá riêng.
- Với dữ liệu có một key rất nóng, chỉ thêm partition chưa chắc phân tán được key đó.

Một bài kiểm tra hữu ích là vẽ throughput và lag theo partition/key bucket, không chỉ tổng topic. Mục tiêu là xác định **mức song song thực tế có công việc hữu ích**, rồi mới chọn số consumer.

## 24. Bảng benchmark minh họa theo nhiều trục

**Tất cả số liệu trong bảng tiếp theo là giả định, không phải đo thực tế.** Ở bảng này, p99 chỉ tính **từ khi function bắt đầu xử lý**, không gồm thời gian chờ trong broker. Giả định có sẵn backlog cần xử lý để so sánh năng lực tối đa; báo cáo triển khai phải đo thêm p99 E2E và backlog theo thời gian.

| Run | Concurrency | Batch/prefetch | Thành công/s | p99 xử lý | CPU | Retry/s | Ghi chú |
|---|---:|---|---:|---:|---:|---:|---|
| A1 | 1 | mặc định | 950 | 1.200 ms | 36% | 2 | Baseline |
| B1 | 2 | mặc định | 1.350 | 690 ms | 58% | 3 | Tăng song song |
| C1 | 4 | mặc định | 1.520 | 520 ms | 79% | 5 | Ứng viên |
| D1 | 8 | mặc định | 1.500 | 1.050 ms | 94% | 18 | Contention |
| C2 | 4 | batch điều chỉnh | 1.620 | 610 ms | 78% | 6 | Throughput cao hơn, tail tệ hơn |
| A2 | 1 | mặc định | 940 | 1.240 ms | 37% | 2 | Baseline lại |

A2 gần A1 cho thấy môi trường tương đối ổn định trong lần minh họa. Nếu A2 khác rất xa A1, cần điều tra thay đổi môi trường trước khi quy kết B/C/D tốt hơn.

Nếu mục tiêu cục bộ là p99 **xử lý trong function** dưới 700 ms và năng lực xả backlog trên 1.400 event/s, C1 và C2 qua được bước lọc này, nhưng C1 có p99 tốt hơn còn C2 có throughput cao hơn. Trước khi quyết định, cần đo p99 E2E, headroom, chi phí và mức biến động giữa các run.

## 25. Chấm điểm cấu hình theo ràng buộc thay vì một số lớn nhất

Ví dụ quy tắc lựa chọn:

1. Loại cấu hình vi phạm correctness (mất event, sai ordering, duplicate chưa xử lý).
2. Loại cấu hình vi phạm SLO latency/error/lag recovery.
3. So sánh throughput **đã được xác nhận** của các phương án còn lại.
4. So sánh CPU/memory/broker I/O và chi phí tài nguyên.
5. Ưu tiên phương án có headroom khi burst và downstream chậm.
6. Nếu hiệu quả chênh lệch trong phạm vi nhiễu đo, chọn cấu hình đơn giản, dễ vận hành hơn.

Có thể dùng chỉ số chi phí:

\[
\text{Cost / 1M events} =
\frac{\text{chi phí trong kỳ đo}}
{\text{event hoàn thành thành công trong kỳ đo}}
\times 1{,}000{,}000
\]

Chi phí cần tính nhất quán: số pod × CPU/RAM, broker, storage và downstream. Đừng tính mỗi CPU application rồi coi broker và database miễn phí.

## 26. Mẫu experiment log để tái hiện

Mỗi lượt chạy nên lưu một bản ghi như sau:

~~~yaml
experimentId: perf-order-projection-2026-11-24-c1
buildCommit: "<git-sha>"
javaVersion: "<version>"
springCloudStreamVersion: "<version>"
binder: kafka
function: projectOrder
inputDestination: orders.created
consumerGroup: order-projection
partitions: 6
replicas: 1
consumerConcurrency: 4

traffic:
  profile: steady-plus-burst
  steadyRatePerSecond: 1500
  burstRatePerSecond: 3000
  payloadDataset: orders-fixture-v2
  keyDistribution: zipf-like
  errorInjectionPercent: 1

environment:
  cpuLimit: "4"
  memoryLimit: "2Gi"
  databasePoolSize: 10

measurement:
  warmupMinutes: 5
  steadyMinutes: 20
  repeatedRuns: 3
  dashboardSnapshot: "<link-to-results>"

metrics:
  successPerSecond: "<measured>"
  p95EndToEndMs: "<measured>"
  p99EndToEndMs: "<measured>"
  lagAtEnd: "<measured>"
  cpuPercent: "<measured>"
  retryPerSecond: "<measured>"
  dlqTotal: "<measured>"

decision:
  result: pending-review
  notes: "So sánh với A/B/A và kiểm tra guardrails"
~~~

Không điền số giả như số đo thực tế. Thay placeholder bằng kết quả hệ thống đo đạc và giữ nguyên định nghĩa metric. Gắn link dashboard/snapshot và timestamp để người khác đối chiếu được.

## 27. Quy trình thực hành hoàn chỉnh

Hãy triển khai một bài đo có 4 cấu hình cho dịch vụ `order-projection`:

1. Chuẩn bị broker và topic có 6 partition, database có dữ liệu nền và producer tạo workload tái lập.
2. Bật Actuator/Micrometer; thêm timer/counter ở function và số đo broker theo group.
3. Chạy baseline `concurrency=1` với warm-up và steady load 20 phút.
4. Lặp lại với `concurrency=2`, giữ nguyên mọi điều kiện khác.
5. Lặp lại với `concurrency=4` và `concurrency=8`.
6. Chạy lại baseline ở cuối hoặc xen kẽ để phát hiện drift.
7. Thu event/s thành công, p95/p99 end-to-end, lag per-partition, CPU/GC, DB pool và retry/DLT.
8. Dùng cùng workload burst để đo thời gian hồi phục backlog.
9. Dùng bảng kết quả xác định sweet spot, giải thích nguyên nhân thay vì chỉ xếp theo throughput.
10. Nếu vẫn chưa đạt SLO, tạo thí nghiệm kế tiếp cho một biến khác (DB batch, key distribution, prefetch hoặc partition count).
11. Kiểm tra tính đúng bằng đối soát input, output, duplicate và DLQ.
12. Ghi đề xuất, cấu hình được chọn và rollback plan.

Với RabbitMQ, thay biến thí nghiệm bằng `consumer.concurrency` và `prefetch` sau khi có baseline. Với Pulsar, kiểm tra subscription type, receiver queue và partition theo phiên bản. Với Kafka Streams, thử `num.stream.threads` và theo dõi state-store/restore/task-level metrics.

## 28. Sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách làm đúng |
|---|---|---|
| Tăng concurrency theo cảm tính | Overhead tăng, p99 xấu | A/B/A với cùng traffic |
| Chỉ xem CPU của application | Không thấy DB/broker bottleneck | Thu metrics nhiều tầng |
| Chỉ dùng throughput producer | Không biết output hoàn thành | Đếm nghiệp vụ đã commit |
| Không tính retry/DLQ | Throughput thành công bị thổi phồng | Đối soát input/success/error |
| Đo trung bình thay vì p99 | Che giấu tail latency | Đo histogram/percentile |
| Thay nhiều biến cùng lúc | Không biết nguyên nhân | Một biến mỗi thí nghiệm |
| Bỏ warm-up | JIT/cache làm số lệch | Loại warm-up khỏi kết quả |
| Consumer > partition mà không kiểm tra | Có thread nhàn rỗi | Đo assignment/lag per partition |
| Prefetch rất lớn | Memory/unacked phình ra | Đo prefetch theo mức vừa phải |
| Test chỉ có message nhỏ/key đều | Không phản ánh production | Dùng payload/key distribution thực tế |
| Không kiểm tra baseline lần cuối | Environmental drift bị nhầm là tối ưu | A/B/A hoặc nhiều lần lặp |
| Đổi delivery guarantee khi benchmark | Kết quả không còn tương đương | Giữ semantics, kiểm tra correctness |
| Chỉ tối ưu steady load | Không biết recovery sau burst | Đo burst + drain time |
| So sánh chi phí khác phạm vi | Quyết định sai về cost | Chuẩn hóa cost/1M success |

## 29. Câu hỏi tự kiểm tra

1. Vì sao tăng concurrency từ 6 lên 12 không nhất thiết tăng throughput khi Kafka topic có 6 partition?
2. Vì sao Kafka lag giảm có thể chưa đủ chứng minh database đã ghi thành công?
3. Thế nào là một benchmark có baseline tái hiện được?
4. Sự khác nhau giữa p99 của function và p99 end-to-end là gì?
5. Khi RabbitMQ unacked tăng nhưng ack/s đứng yên, nên kiểm tra gì trước khi tăng prefetch?
6. Khi Kafka Streams có 2 task hữu ích, tăng `num.stream.threads` lên 8 thường dẫn đến điều gì?
7. Vì sao thay subscription Shared thành Key_Shared ở Pulsar là thay đổi semantics cần kiểm thử?
8. Làm thế nào phân biệt giới hạn của broker, CPU và database pool?
9. Nếu backlog 90.000 event, input 700/s và output 1.000/s, thời gian xả xấp xỉ là bao lâu trong điều kiện ổn định?
10. Khi hai cấu hình gần bằng throughput nhưng khác p99 và retry rate, chọn bằng tiêu chí nào?

## 30. Kết luận thực hành

Bắt đầu từ **định nghĩa thành công**, đo baseline, tìm nút thắt và thử từng giả thuyết. Giữ nguyên workload cùng ràng buộc đúng/sai, kiểm tra throughput thành công cùng latency, lag, error rate và tài nguyên. Concurrency, partition, prefetch, batching hoặc số replica chỉ có ý nghĩa khi số đo cho thấy chúng cải thiện SLO mà không gây tác dụng phụ không chấp nhận được.

Trong Spring Cloud Stream, cùng một tên thuộc tính có thể tương tác khác nhau với Kafka, RabbitMQ, Pulsar và Kafka Streams. Vì vậy tài liệu binder đúng phiên bản, kết quả quan sát ở broker thật và phép đo có thể tái hiện là căn cứ để quyết định.

## 31. Tài liệu tham khảo chính thức

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/binding-properties.html) — `consumer.concurrency` và thuộc tính binding.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/config-options.html) — các cấu hình Kafka binder, client và metrics.
- [Spring Cloud Stream — Kafka Binder Metrics](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/metrics.html) — `spring.cloud.stream.binder.kafka.offset` và ý nghĩa lag.
- [Spring Cloud Stream — Kafka Streams Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html) — `num.stream.threads` và concurrency.
- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html) — prefetch, batching và consumer options.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/5.0/pulsar/pulsar_binder.html) — subscription, partition và extended binding properties.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Actuator, Micrometer và Prometheus.
- [Apache Kafka — Monitoring](https://kafka.apache.org/34/operations/monitoring/) — consumer records-lag, records-consumed-rate, fetch và broker metrics.
- [RabbitMQ — Queues and Prefetch](https://www.rabbitmq.com/docs/queues) — unacked deliveries, prefetch và consumer overload.
- [Spring Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html) — record/listener observation.

