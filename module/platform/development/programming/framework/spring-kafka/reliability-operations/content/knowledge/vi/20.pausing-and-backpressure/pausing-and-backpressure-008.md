# Tạm dừng khi database quá tải trong Spring Kafka

Khi Kafka consumer đọc record nhanh hơn tốc độ ghi của database, hệ thống có thể bị quá tải ở connection pool, CPU, I/O hoặc locks. Nếu listener cứ tiếp tục đọc và thực hiện query, số request database đang chờ sẽ tăng; timeout gây retry; retry lại tiếp tục đẩy tải vào database. Kết quả có thể là một vòng lặp làm database càng ngày càng chậm.

Trong module **Spring Kafka Reliability Operations**, bài học **Tạm dừng khi database quá tải** tập trung vào cách dùng cơ chế **pause/resume** của Spring Kafka listener container để thực hiện **backpressure**. Thay vì tiếp tục đưa record mới vào listener khi database không còn đủ năng lực, ứng dụng yêu cầu container tạm dừng giao dữ liệu, cho database phục hồi rồi tiếp tục xử lý.

**Pause không xóa record, không tự commit offset, không rollback transaction database và không tự sửa các lỗi nghiệp vụ.** Nó là một van điều tiết đầu vào. Muốn triển khai an toàn, cần kết hợp tín hiệu health, hysteresis, timeout, acknowledgement đúng thời điểm, idempotency, error handler và monitoring.

## 1. Bản chất của backpressure từ Kafka tới database

Kafka lưu record bền vững theo topic và partition. Consumer có thể xử lý dữ liệu theo tốc độ riêng. Khi downstream chậm, consumer lag tăng; bản thân việc lag tăng không nhất thiết là mất dữ liệu, miễn Kafka vẫn giữ record trong thời hạn retention.

~~~text
Producers
    |
    v
Kafka topic orders.events
    |
    v
Spring Kafka consumers
    |
    +--> Consumer 1
    +--> Consumer 2
    +--> Consumer 3
    |
    v
Business listener
    |
    v
HikariCP connection pool
    |
    v
PostgreSQL
    |
    +--> CPU cao
    +--> lock waits tăng
    +--> queries chậm
    +--> threads chờ connection
~~~

Một hệ thống không có backpressure có thể tự tạo vòng xoáy:

1. Kafka có nhiều record sẵn sàng.
2. Listener tiếp tục thực hiện database queries.
3. Connection pool hết connection rảnh.
4. Thread chờ connection, rồi timeout.
5. DefaultErrorHandler hoặc cơ chế retry thử lại.
6. Nhiều lần retry cùng đánh vào database đang chậm.
7. Throughput giảm tiếp và consumer lag tăng.

Mục đích backpressure là **giảm số công việc mới bắt đầu** để hệ thống đích không sụp đổ. Không nên chỉ tăng concurrency hoặc max.poll.records để cố đuổi kịp Kafka khi bottleneck thực sự nằm ở database.

## 2. Pause container là gì?

Spring Kafka cung cấp các thao tác trên MessageListenerContainer:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

container.pause();

// Sau khi database hồi phục:
container.resume();
~~~

Một container được pause:

- Tạm ngừng giao thêm record mới cho listener.
- Thường tiếp tục gọi KafkaConsumer.poll() trong trạng thái pause để duy trì consumer group membership.
- Không chủ động bỏ qua record hay tiến offset chỉ vì pause.
- Có thể resume để xử lý dữ liệu còn tồn tại trong topic.
- Không tự hủy lời gọi listener hoặc JDBC đang chạy.

~~~text
RUNNING
   |
   | DB saturation detected
   v
PAUSE_REQUESTED
   |
   | Consumer áp dụng pause ở poll boundary
   v
PAUSED
   |
   | Consumer vẫn có thể poll để giữ group
   | Listener không nhận thêm record mới
   |
   | DB healthy đủ lâu
   v
RESUME_REQUESTED
   |
   v
RUNNING
~~~

**Pause khác stop.** Stop container đóng consumer theo lifecycle, có thể làm partition được phân phối lại. Pause thường giữ consumer trong group và giữ partition assignment, do đó phù hợp với sự cố quá tải tạm thời.

Cần hiểu giới hạn: lệnh pause() không đồng bộ hoàn toàn với thời điểm consumer thực sự bị pause. Consumer có thể đang xử lý record hoặc batch được poll trước khi nhận yêu cầu.

## 3. Pause request không phải pause đã hoàn tất

Spring Kafka có thể phân biệt trạng thái yêu cầu và trạng thái thực tế:

| API | Mục đích |
|---|---|
| pause() | Yêu cầu container pause |
| resume() | Yêu cầu container resume |
| isPauseRequested() | Xác định yêu cầu pause đang được giữ |
| isConsumerPaused() | Kiểm tra trạng thái consumer/container đã pause |
| pausePartition(TopicPartition) | Yêu cầu pause một partition khi API hỗ trợ |
| resumePartition(TopicPartition) | Yêu cầu tiếp tục partition đó |

Với ConcurrentMessageListenerContainer, các child consumers có thể áp dụng pause khi đến điểm thích hợp của vòng poll. Khi có nhiều child containers, cần phân biệt yêu cầu pause ở cấp container cha và trạng thái thực tế của từng consumer.

Spring Kafka có các lifecycle events liên quan đến pause/resume. Trong ứng dụng cần monitoring, có thể lắng nghe ConsumerPausedEvent, ConsumerResumedEvent và các partition-level events khi phiên bản hỗ trợ để phân biệt **pause requested** với **pause actually applied**.

## 4. Listener đã nhận record vẫn có thể tiếp tục chạy

Một điểm dễ gây nhầm là container có thể đã poll nhiều record trước khi ứng dụng gọi pause().

~~~text
poll() trả 100 records
      |
      +--> xử lý record 1
      +--> xử lý record 2
      |
      +--> monitoring phát hiện DB quá tải
      |       |
      |       +--> gọi container.pause()
      |
      +--> một số record đã poll có thể tiếp tục
      |
      v
consumer trở lại vòng poll và áp dụng pause
~~~

Thông thường pause có hiệu lực ở poll boundary. Một số phiên bản Spring Kafka hỗ trợ pauseImmediate thông qua ContainerProperties để pause sau record đang xử lý, thay vì chờ xử lý hết các record đã poll:

~~~java
factory.getContainerProperties().setPauseImmediate(true);
~~~

Điều này không cắt ngang một database transaction đang chạy, và không phải cách chia một batch listener callback thành nhiều phần. Cần đối chiếu hỗ trợ của phiên bản Spring Kafka và loại listener thực tế.

Nếu database đã treo và listener đang chờ connection vô hạn, container chưa trở lại vòng poll; lệnh pause từ scheduler không chữa được vấn đề ấy. **Timeout ở tầng database là yêu cầu bắt buộc**, không phải tùy chọn thay thế được bằng pause.

## 5. Nhận diện database quá tải bằng tín hiệu nào?

Không nên chỉ nhìn một metric đơn lẻ. Một database có nhiều connection active vẫn có thể khỏe nếu query nhanh; ngược lại, pool ít connection active không đảm bảo khỏe nếu database đã bị ngắt kết nối hoàn toàn.

| Tín hiệu | Dấu hiệu cần quan sát | Lưu ý |
|---|---|---|
| Hikari active connections | Mức sử dụng connection pool tăng | Nên so với max pool size |
| Hikari threads awaiting | Thread đang xếp hàng chờ connection | Thường là tín hiệu saturation rõ |
| Connection acquisition p95/p99 | Lấy connection chậm hơn bình thường | Cần tránh phản ứng vì một spike ngắn |
| Query latency p95/p99 | Query bị chậm | Phân biệt loại query |
| JDBC timeout/error rate | Database không đáp ứng request | Có thể do mạng hoặc backend |
| Lock wait/deadlocks | Transaction cạnh tranh khóa | Cần xử lý nguyên nhân query/transaction |
| Database CPU/IO | Tài nguyên dùng gần giới hạn | Metric toàn DB, không chỉ một pod |
| Circuit breaker state | Dependency bị đánh giá unavailable | Health có thể OPEN khi active=0 |
| Consumer lag growth | Consumer không theo kịp producers | Lag chưa đủ chứng minh DB overload |

Trong HikariCP, HikariPoolMXBean có các phương thức như getActiveConnections(), getTotalConnections(), getIdleConnections() và getThreadsAwaitingConnection(). HikariDataSource cung cấp cấu hình maximumPoolSize cùng interface lấy MXBean.

Khi chọn policy, nên kết hợp **tín hiệu local** như connection waiting với **tín hiệu database-wide** như query p99, saturation hoặc circuit breaker. Nếu nhiều service cùng dùng database, chỉ nhìn Hikari pool của một pod có thể bỏ sót áp lực do service khác tạo ra.

## 6. Thiết kế pause/resume có hysteresis

Nếu controller pause ngay ở 80% utilization và resume khi giảm còn 79%, hệ thống dễ bị flapping:

~~~text
80% -> PAUSE
79% -> RESUME
81% -> PAUSE
78% -> RESUME
...
~~~

Hãy dùng hai ngưỡng khác nhau:

~~~text
100% |
     |
 90% | ---- PAUSE THRESHOLD
     |
     | Giữ nguyên trạng thái trong vùng giữa
     |
 55% | ---- RESUME THRESHOLD
     |
  0% |
~~~

Chính sách minh họa:

- Pause khi connection pool đạt khoảng 90% giới hạn hoặc có waiting threads/error-rate cao, và trạng thái quá tải kéo dài một số lần lấy mẫu.
- Resume khi connection utilization dưới 55%, không còn waiting threads, database healthy và trạng thái hồi phục kéo dài một số lần lấy mẫu.
- Có minimum pause duration và cooldown để không thay đổi trạng thái liên tục.
- Circuit breaker OPEN phải giữ pause ngay cả khi số connection active thấp.
- Khi circuit breaker HALF_OPEN, không cho tất cả Kafka listeners đồng loạt tạo load mới; dùng probes có giới hạn.

**90% và 55% là ví dụ về policy của ứng dụng, không phải mặc định của Spring Kafka.** Ngưỡng cần đo theo database workload, connection acquisition latency và service SLO.

## 7. Cấu hình Spring Boot: database pool và consumer

Một cấu hình tham khảo:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/orders
    username: orders_app
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000

  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: order-service
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        "[max.poll.interval.ms]": 300000
    listener:
      ack-mode: record
      concurrency: 3
~~~

Ý nghĩa:

- maximum-pool-size giới hạn số connection của pool trên một application instance.
- connection-timeout giúp thread không chờ connection vô hạn.
- max-poll-records giảm lượng công việc trong một poll.
- max.poll.interval.ms giới hạn thời gian giữa các consumer poll.
- AckMode.RECORD commit sau record listener xử lý thành công.
- concurrency tạo các child consumers song song, nhưng cũng có thể làm tăng số lời gọi database.

Tổng số connection dự kiến cần tính trên **mọi replica và mọi service**, không chỉ một pool. Nếu 10 pods có maximum-pool-size=20, ứng dụng có thể dùng tới 200 connections, chưa tính services khác.

DB query timeout và transaction timeout có thể cần cấu hình thêm ở JDBC/framework/database, vì connection-timeout của Hikari chỉ giới hạn việc đợi **lấy connection**, không phải thời gian chạy mọi SQL query.

## 8. Điều khiển container qua KafkaListenerEndpointRegistry

Khai báo listener với id ổn định:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-service"
    )
    public void onOrder(OrderEvent event) {
        orderService.processIdempotently(event);
    }
}
~~~

Một service điều khiển:

~~~java
@Service
public class OrderListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderListenerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void requestPause() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null
                && container.isRunning()
                && !container.isPauseRequested()) {
            container.pause();
        }
    }

    public void requestResume() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container != null
                && container.isRunning()
                && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

Sử dụng API của Spring Kafka container thay vì gọi Consumer.pause() trực tiếp từ scheduler thread. KafkaConsumer không được dùng đồng thời tùy ý từ nhiều threads; container chịu trách nhiệm tương tác với consumer trên thread phù hợp.

Nếu container được tạo thủ công, không qua @KafkaListenerRegistry, ứng dụng phải giữ reference tới container tương ứng thay vì mong registry luôn tìm thấy nó.

## 9. Controller tự pause khi pool bão hòa

Có thể dùng @Scheduled để định kỳ đọc tín hiệu HikariCP và ra quyết định. Ví dụ sau trình bày cơ chế đơn giản, chưa bao gồm dwell time hoặc distributed coordination.

~~~java
@Component
public class DatabaseBackpressureController {

    private final HikariDataSource dataSource;
    private final KafkaListenerEndpointRegistry registry;
    private final DatabaseHealthSignals healthSignals;

    public DatabaseBackpressureController(
            HikariDataSource dataSource,
            KafkaListenerEndpointRegistry registry,
            DatabaseHealthSignals healthSignals) {

        this.dataSource = dataSource;
        this.registry = registry;
        this.healthSignals = healthSignals;
    }

    @Scheduled(fixedDelay = 2000)
    public void evaluate() {

        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null || !container.isRunning()) {
            return;
        }

        HikariPoolMXBean pool = dataSource.getHikariPoolMXBean();

        if (pool == null) {
            return;
        }

        int active = pool.getActiveConnections();
        int waiting = pool.getThreadsAwaitingConnection();
        int max = dataSource.getMaximumPoolSize();

        if (max <= 0) {
            return;
        }

        double ratio = (double) active / max;

        boolean overloaded =
                waiting > 0
                || ratio >= 0.90
                || healthSignals.circuitOpen();

        boolean recovered =
                waiting == 0
                && ratio <= 0.55
                && healthSignals.databaseHealthy();

        if (overloaded && !container.isPauseRequested()) {
            container.pause();
        }
        else if (recovered && container.isPauseRequested()) {
            container.resume();
        }
    }
}
~~~

DatabaseHealthSignals là abstraction của ứng dụng để cung cấp circuit breaker và database health. @Scheduled cần cấu hình scheduling, chẳng hạn @EnableScheduling. HikariDataSource chỉ inject được khi datasource thật dùng HikariCP; trường hợp nhiều data sources cần chọn đúng pool.

Đây là controller minh họa, chưa phải production controller hoàn chỉnh. Cần bổ sung:

- Số mẫu liên tiếp để xác nhận trạng thái.
- Minimum pause duration.
- Cooldown khi resume.
- Log lý do pause/resume.
- Manual maintenance override.
- Trạng thái trên từng container.
- Health signal từ các thống kê đã có thay vì mỗi lần chạy lại tạo SQL query nặng.

Không cần hỏi database bằng một health query tốn connection mỗi hai giây nếu chính database đang thiếu connection. Ưu tiên telemetry, circuit breaker và chỉ dùng probe nhẹ có deadline khi cần.

## 10. Không để nhiều cơ chế điều khiển pause xung đột

Một listener có thể bị pause vì nhiều lý do:

~~~text
DATABASE_OVERLOAD
MANUAL_MAINTENANCE
DOWNSTREAM_CIRCUIT_OPEN
REBALANCE_OR_RECOVERY_CONTROL
~~~

Nếu scheduler của DB thấy database khỏe và gọi resume(), nhưng operator đang chủ động pause để bảo trì, container có thể bị resume sai. Một thiết kế tốt nên có **pause coordinator** hoặc một quy tắc sở hữu trạng thái rõ ràng.

Ví dụ policy:

~~~text
pauseReasons = {DATABASE_OVERLOAD, MANUAL_MAINTENANCE}

DB hồi phục:
  remove DATABASE_OVERLOAD
  pauseReasons = {MANUAL_MAINTENANCE}
  => VẪN PAUSED

Operator kết thúc bảo trì:
  remove MANUAL_MAINTENANCE
  pauseReasons = {}
  => RESUME
~~~

Nếu DefaultErrorHandler hoặc ContainerPausingBackOffHandler cũng sử dụng pause state, cần kiểm tra tương tác với health-based pause ở phiên bản Spring Kafka. Không giả định một subsystem biết hết lý do của subsystem còn lại.

## 11. Event để quan sát actual pause/resume

Spring Kafka có thể phát các sự kiện ConsumerPausedEvent và ConsumerResumedEvent khi consumer được pause/resume.

~~~java
@Component
public class KafkaPauseLogging {

    @EventListener
    public void paused(ConsumerPausedEvent event) {
        log.info(
                "Kafka consumer paused, partitions={}",
                event.getPartitions()
        );
    }

    @EventListener
    public void resumed(ConsumerResumedEvent event) {
        log.info(
                "Kafka consumer resumed, partitions={}",
                event.getPartitions()
        );
    }
}
~~~

Ví dụ minh họa việc nghe event; chữ ký sự kiện/getters cần đối chiếu API Spring Kafka đang sử dụng. Có thể xuất metrics cho paused duration, số lần resume và flapping.

Phân biệt:

1. Controller quyết định pause.
2. Lệnh pause() được gửi.
3. Container áp dụng pause.
4. Các records đã giao cho listener hoàn tất.
5. Database bắt đầu phục hồi.

Đây là các thời điểm khác nhau. Không xem một event pause thành công là bằng chứng mọi database transaction đã dừng.

## 12. Pause toàn container hay pause từng partition?

Nếu toàn database đều quá tải, pause toàn container thường phù hợp:

~~~java
container.pause();
~~~

Nếu chỉ một partition/tenant tạo tải bất thường và workload cho phép, có thể yêu cầu pause partition trong các phiên bản hỗ trợ:

~~~java
TopicPartition partition =
        new TopicPartition("orders.events", 2);

container.pausePartition(partition);

// Khi có thể tiếp tục:
container.resumePartition(partition);
~~~

Khi pause partition riêng, cần quản lý topic/partition assignment:

- Chỉ consumer đang được gán partition mới điều khiển việc đọc partition đó.
- Partition có thể chuyển chủ khi rebalance.
- Pause state và fairness policy phải được khôi phục hoặc cập nhật khi assignment thay đổi.
- Không mặc định partition có lag cao là partition gây DB overload.
- Khi database bị quá tải toàn cục, chỉ pause một partition có thể không đủ giảm tải.

Với ConcurrentMessageListenerContainer, cần biết API pausePartition được áp dụng vào child consumer nào và trạng thái sau rebalance của phiên bản đang dùng.

## 13. Vì sao pause giúp consumer vẫn duy trì group?

Kafka consumer cần poll đúng hạn theo group protocol. Một listener đang sleep quá lâu có thể vượt max.poll.interval.ms và mất quyền sở hữu partition. Container pause của Spring Kafka giúp consumer tiếp tục poll trong trạng thái đã pause, qua đó duy trì membership bình thường.

~~~text
Container paused:
   |
   +--> consumer.poll() tiếp tục
   |
   +--> không giao record mới cho listener
   |
   +--> group membership được duy trì
   |
   +--> consumer lag có thể tăng
~~~

Ngược lại, code kiểu:

~~~java
@KafkaListener(topics = "orders.events")
public void onOrder(OrderEvent event)
        throws InterruptedException {

    Thread.sleep(600_000L);
    orderService.process(event);
}
~~~

giữ consumer thread trong listener, làm poll bị gián đoạn. Đây không phải phương án backpressure an toàn.

**Quan trọng:** pause không tự giải quyết việc listener đang bị block ở JDBC. Nếu query treo trước khi container quay lại poll, vẫn có nguy cơ vượt max.poll.interval.ms. Cần đặt connection/query/transaction timeouts và giới hạn batch processing time.

## 14. Ack offset phải theo sau database commit

Pause chỉ kiểm soát inflow. Một record đã vào listener vẫn phải được xử lý theo đúng acknowledgement policy:

~~~text
Record E
   |
   v
Begin DB transaction
   |
   +--> Business update
   |
   +--> DB commit thành công
   |       |
   |       v
   |   Listener return success
   |       |
   |       v
   |   Kafka offset commit theo AckMode
   |
   +--> DB exception / rollback
           |
           v
       Listener throw exception
           |
           v
       Error handler retry / recovery
~~~

Không acknowledge sớm chỉ để giảm lag. Ví dụ sai:

~~~java
public void onOrder(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    acknowledgment.acknowledge(); // Sai vị trí

    orderService.saveToDatabase(event);
}
~~~

Ví dụ đúng hơn với manual ack:

~~~java
@KafkaListener(
        topics = "orders.events",
        containerFactory = "manualAckFactory"
)
public void onOrder(
        OrderEvent event,
        Acknowledgment acknowledgment) {

    orderService.processIdempotently(event);

    acknowledgment.acknowledge();
}
~~~

manualAckFactory phải được cấu hình AckMode.MANUAL hoặc MANUAL_IMMEDIATE. processIdempotently chỉ return sau khi database transaction đã hoàn tất an toàn.

Nếu listener dispatch công việc sang thread pool rồi trả về ngay, AckMode.RECORD có thể commit offset trước khi database hoàn tất. Pause không sửa lỗi completion boundary ấy. Cần làm xử lý đồng bộ hoặc dùng cơ chế async ack có quản lý completion và ordering phù hợp.

## 15. Idempotency giúp an toàn khi pause, crash và rebalance

Một event có thể được xử lý database thành công nhưng Kafka offset chưa kịp commit trước khi container crash, bị stop hoặc bị rebalance. Consumer mới có thể đọc lại event ấy.

~~~text
Consumer A:
  DB COMMIT thành công
  Kafka offset CHƯA commit
  JVM crash
       |
       v
Consumer B:
  redelivery event E
       |
       v
  Nếu không idempotent: DB update có thể chạy lần nữa
~~~

Dùng eventId và unique constraint tại database:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(150) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Cài đặt service trong một database transaction:

~~~java
@Transactional
public void processIdempotently(OrderEvent event) {

    boolean firstTime = processedEvents.insertIfAbsent(
            "orders-service",
            event.eventId()
    );

    if (!firstTime) {
        return;
    }

    orders.apply(event);
}
~~~

insertIfAbsent phải dùng atomic insert/unique constraint; thao tác ghi dấu và orders.apply nằm trong cùng DB transaction. Nếu DB rollback, processed marker cũng phải rollback.

Điều này không loại bỏ redelivery, nhưng giúp **business effect** không bị nhân đôi khi record được giao lại sau sự cố.

## 16. Error handler và health-based pause khác vai trò

Hai cơ chế bổ sung cho nhau:

| Cơ chế | Trigger | Mục tiêu |
|---|---|---|
| Health-based pause | Database đang quá tải hoặc circuit breaker mở | Giảm công việc mới |
| DefaultErrorHandler | Listener ném exception với một record cụ thể | Retry hoặc recover record |
| BackOff | Record retryable cần chờ | Điều tiết số lần retry |
| DLT | Lỗi cố định hoặc hết retry | Lưu record chưa xử lý được |
| Circuit breaker | Downstream hiện không phục vụ ổn định | Ngăn thêm lời gọi tới dependency |

Ví dụ error handler:

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(1_000L, 2L)
            );

    handler.addNotRetryableExceptions(
            InvalidOrderEventException.class
    );

    return handler;
}
~~~

Nếu DB tạm lỗi, listener vẫn cần ném exception để error handler biết record chưa xử lý thành công. Không nuốt lỗi rồi return bình thường vì container có thể commit offset. Nếu payload sai cố định, pause DB không giúp gì; xử lý non-retryable và DLT/quarantine.

Với DB outage dài, retry quá dày có thể tạo thêm áp lực. Cần phối hợp retry có backoff và health-based pause. Nếu hết retries quá sớm trong khi DB chỉ đang tạm unavailable, một lượng lớn record hợp lệ có thể bị gửi DLT; hãy chọn policy theo thời gian phục hồi mong đợi và SLA.

## 17. ContainerPausingBackOffHandler khác health-based pause

Spring Kafka có ContainerPausingBackOffHandler dùng trong error handling để chờ một khoảng retry backoff dài mà vẫn tiếp tục poll.

~~~text
Record lỗi
    |
    v
DefaultErrorHandler / BackOff
    |
    v
ContainerPausingBackOffHandler
    |
    +--> pause theo khoảng backoff
    +--> poll tiếp tục
    |
    v
Retry record lỗi
~~~

Health-based pause được kích hoạt bởi tình trạng database chung, không cần có một record đã thất bại. Hai trường hợp có cùng primitive pause nhưng mục tiêu khác nhau.

Nếu dùng cả hai, cần đảm bảo một component không resume container khi component khác vẫn cần pause. Kiểm tra state và lifecycle theo Spring Kafka version cùng listener factory thực tế.

## 18. Concurrency, max.poll.records và lượng tải database

Khi database là bottleneck, tăng Kafka concurrency có thể làm số lời gọi DB đồng thời tăng, khiến tình hình tệ hơn.

~~~text
Concurrency 3:
  3 consumer threads
  khoảng 3 DB operations đang chạy đồng thời

Concurrency 12:
  12 consumer threads
  khoảng 12 DB operations tranh connection
~~~

Con số này chỉ minh họa listener đồng bộ mỗi record một DB operation. Các batch operations, async tasks và nhiều queries per record có thể tạo nhiều hoặc ít connections hơn.

Các biện pháp:

- Giới hạn concurrency theo database capacity.
- Giảm max.poll.records để mỗi poll ít record hơn.
- Thiết lập connection acquisition timeout.
- Tối ưu query/index và rút ngắn transaction.
- Dùng batch insert/update khi bulk API thực sự hiệu quả.
- Giới hạn request admission từ các nguồn khác cũng sử dụng DB.
- Tính tổng pool capacity trên mọi pods, không chỉ một pod.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      max-poll-records: 50
    listener:
      concurrency: 3
~~~

max.poll.records là số record tối đa của một poll, không phải tốc độ record/giây hoặc giới hạn số queries tới database. Throttle mượt hơn có thể cần thêm rate limiter hoặc bounded worker queue tại tầng xử lý.

## 19. Batch listener cần giới hạn thời gian xử lý

Batch listener nhận một tập record mỗi callback. Nếu một batch có hàng trăm record và database chậm, listener có thể bị giữ trong một database operation quá lâu.

~~~text
poll() -> 500 records
        |
        v
Batch listener
        |
        v
Database bulk write
        |
        +--> DB lock wait/timeout
        |
        v
Consumer chưa quay lại poll
~~~

Lúc này, scheduler gọi pause() không hủy query đang chạy. Cần giới hạn batch size, query timeout và thời gian transaction để tránh vượt max.poll.interval.ms.

Nếu batch xử lý một phần rồi thất bại, các record đã xử lý có thể được chạy lại. Hãy dùng bulk operation có transaction semantics rõ ràng và idempotency. Batch error handler phải biết record hoặc batch lỗi theo cách mà phiên bản Spring Kafka hỗ trợ.

Với yêu cầu latency thấp và độc lập từng record, record listener có thể dễ quản lý hơn batch listener.

## 20. Nhiều replicas và thundering herd khi resume

Một hệ thống 10 pods có thể có 10 listener containers. Nếu database phục hồi, tất cả pods có thể phát hiện healthy và resume cùng lúc.

~~~text
DB phục hồi
    |
    +--> Pod 1 resume
    +--> Pod 2 resume
    +--> Pod 3 resume
    +--> ...
    +--> Pod 10 resume
    |
    v
Backlog cùng đổ vào DB
    |
    v
DB lại quá tải
~~~

Cần tránh trạng thái dao động theo chu kỳ:

1. Resume chỉ sau khi health ổn định nhiều mẫu.
2. Dùng cooldown và minimum pause duration.
3. Giới hạn concurrency hoặc tốc độ DB operations lúc phục hồi.
4. Cân nhắc resume theo đợt, với jitter nếu có controller điều phối phù hợp.
5. Theo dõi query p99 và pool waiting threads ngay sau resume.
6. Nếu DB lại quá tải, pause có hysteresis nhưng không flapping liên tục.

Một controller chỉ dựa vào pool local của pod có thể không nhận biết DB đang chịu tải từ các pods khác. Cần kết hợp tín hiệu database-wide hoặc cơ chế admission control khi quy mô lớn.

## 21. Consumer lag tăng trong khi pause là điều dự kiến

Producer có thể tiếp tục publish dù consumer pause. Dữ liệu không bị drop do pause; nó tích lũy trong Kafka topic theo retention.

~~~text
Producer rate = 800 records/second
Pause 60 seconds

Backlog tăng xấp xỉ:
  800 * 60 = 48,000 records
~~~

Đây là phép tính minh họa, giả định rate ổn định và consumer không xử lý records mới khi pause. Consumer lag tăng có thể là lựa chọn đúng để giữ DB khỏi bị sập.

Nhưng cần đảm bảo:

- Kafka topic retention đủ cho thời gian pause cộng thời gian phục hồi.
- Broker storage/quota đủ chứa backlog.
- Khi DB khỏe, consumer throughput lớn hơn producer rate để giảm lag.
- Monitoring đo cả **oldest unprocessed event age**, không chỉ lag count.
- Có SLA tối đa cho thời gian lưu đọng event.
- Có kế hoạch nếu DB outage kéo dài vượt Kafka retention.

Nếu throughput tối đa khi DB khỏe chỉ bằng producer rate, backlog sinh ra trong thời gian pause sẽ không được rút hết. Khi đó cần tối ưu database hoặc giảm tốc độ upstream, không chỉ resume.

## 22. Khi database chết hẳn, pool utilization có thể đánh lừa

Nếu database down hoàn toàn, Hikari pool có thể không tạo được connection mới. active connections có thể giảm về 0, khiến một controller chỉ nhìn ratio kết luận sai rằng DB đã phục hồi.

~~~text
DB down
    |
    +--> active connections = 0
    +--> waiting threads có thể tăng
    +--> connection timeout/error tăng
    +--> circuit breaker OPEN
~~~

Vì thế, resume condition phải yêu cầu **databaseHealthy()** hoặc circuit breaker CLOSED ổn định, không chỉ ratio dưới ngưỡng thấp.

Khi circuit breaker HALF_OPEN, chỉ cho phép số lượng probe nhỏ và có deadline. Không mở toàn bộ backlog thành một lượng lớn probe đồng thời.

Tránh liên tục chạy một SQL health check nặng để xác nhận DB trong lúc DB đang quá tải. Dùng telemetry và probe được giới hạn.

## 23. Partition pause, rebalance và ownership

Nếu pause theo partition, assignment có thể thay đổi khi consumer group rebalance.

~~~text
Trước rebalance:
  Consumer A -> P0, P1
  Consumer B -> P2

Sau rebalance:
  Consumer A -> P0
  Consumer B -> P1, P2
~~~

Nếu P1 đang bị pause do policy riêng, application cần xác định cách áp dụng policy sau khi P1 chuyển sang consumer B. Không cho rằng state trong bộ nhớ của consumer A vẫn có hiệu lực với consumer B.

Ngược lại, nếu pause toàn container vì database chung quá tải, mỗi pod/container cần tự đánh giá health và giữ state phù hợp sau rebalance.

Không commit offset chỉ để bỏ qua record đang gây tải; một record lỗi cần error handler/recovery. Khi partition bị revoked/lost, công việc đang chạy có thể vẫn hoàn tất ở worker thread cũ, tạo side effect trùng với consumer mới. Dùng event ID, version check hoặc fencing để bảo vệ database.

## 24. Pause, stop và điều tiết bằng rate limiter

| Hành động | Phù hợp khi | Đánh đổi |
|---|---|---|
| pause() toàn container | DB quá tải tạm thời, mọi partition cùng dùng DB | Lag tăng, tốc độ xử lý rơi gần 0 |
| pausePartition() | Một partition/tenant tạo tải riêng | Cần quản lý assignment và fairness |
| Rate limiter trước DB call | Muốn điều tiết mượt hơn thay vì tạm ngừng hoàn toàn | Listener vẫn nhận record, phải đảm bảo không block poll quá lâu |
| Giảm concurrency | Điều chỉnh tải bền vững | Có thể thay đổi assignment và throughput |
| Giảm max.poll.records | Giảm burst từ một lần poll | Có thể giảm throughput và tăng overhead |
| stop() container | Bảo trì dài hoặc shutdown | Consumer rời group, có thể rebalance |

Pause không nên trở thành cách che giấu một query N+1, thiếu index hoặc transaction giữ lock quá lâu. Sửa bottleneck database vẫn là giải pháp nền tảng.

Nếu service phải tạm dừng nhiều ngày, cần đánh giá việc giữ containers sống trong trạng thái pause so với stop có kiểm soát; Kafka retention và resource usage của các pods sẽ quyết định lựa chọn.

## 25. Các sự cố thường gặp

### Đã pause nhưng listener vẫn xử lý thêm record

Container đã poll dữ liệu trước khi pause. Kiểm tra pauseImmediate nếu được phiên bản hỗ trợ, giảm max.poll.records và đảm bảo listener processing time hữu hạn.

### Pause nhưng Kafka lag tăng liên tục

Đây có thể là kết quả mong đợi. Kiểm tra retention, event age và throughput catch-up thay vì vội resume khi database chưa đủ năng lực.

### Container không resume sau khi DB khỏe

Kiểm tra isPauseRequested(), sự kiện ConsumerResumedEvent, controller health signal, manual pause reason, trạng thái container running và circuit breaker. Không để một pause reason cũ bị quên.

### Resume xong lại pause ngay

Ngưỡng thiếu hysteresis hoặc tải backlog tăng quá nhanh. Thêm dwell time, cooldown và gradual ramp-up.

### Pool active rất thấp nhưng listener vẫn timeout

DB có thể down hoặc connection acquisition đang lỗi. Dùng circuit breaker/error-rate/health state, không nhìn active count một mình.

### Pause không ngăn max.poll.interval.ms bị vượt

Listener đang block trong JDBC call và chưa quay lại poll. Đặt query/connection timeouts, giới hạn batch size và tránh Thread.sleep trong listener.

### Offset đã commit nhưng DB thiếu record

Listener có thể return/ack trước DB commit hoặc nuốt exception. Sửa completion boundary; pause không khôi phục record đã bị commit sai.

### DLT tăng trong thời gian DB outage

Policy retry có thể hết attempts quá sớm. Phân biệt lỗi database tạm thời với lỗi dữ liệu cố định; phối hợp pause và retry thay vì đưa hàng loạt valid records vào DLT.

### Nhiều pods cùng resume làm DB quá tải lại

Dùng phased recovery hoặc rate admission có giới hạn, không chỉ monitor pool của từng pod.

## 26. Monitoring và alerting

Theo dõi Kafka và database cùng lúc:

| Tín hiệu | Ý nghĩa |
|---|---|
| Pause requested count | Controller yêu cầu pause bao nhiêu lần |
| Actual paused duration | Thời gian consumer thực sự không giao record |
| Resume count/flapping count | Có dao động liên tục không |
| Consumer lag theo partition | Backlog ở đâu |
| Oldest event age | SLO dữ liệu |
| Records processed rate | Throughput phục hồi |
| Listener duration p95/p99 | Chi phí xử lý một record/batch |
| Hikari active/idle/total | Sử dụng connection pool |
| Hikari threads awaiting | Connection acquisition saturation |
| Hikari acquisition latency | Thời gian chờ lấy connection |
| DB query latency/error rate | Tốc độ và lỗi của downstream |
| DB CPU/IO/lock wait | Bản chất bottleneck |
| Circuit breaker state | OPEN, HALF_OPEN, CLOSED |
| Error handler retry/DLT count | Lỗi record và recovery |
| Rebalance count | Consumer group stability |
| Duplicate event rejection | Idempotency có bảo vệ redelivery |

Metric names thực tế khác nhau theo Kafka client, Spring Kafka, Micrometer, HikariCP và exporter. Một số như pause reason hoặc flapping phải được ứng dụng tự xuất.

Một mẫu log có cấu trúc:

~~~text
event=kafka_backpressure_pause
listener_id=ordersListener
reason=DATABASE_SATURATION
pool_active=19
pool_max=20
threads_waiting=4
db_circuit=CLOSED
container_state=PAUSE_REQUESTED
~~~

Không dùng event ID, Kafka key hoặc query chứa thông tin nhạy cảm làm metric label có cardinality lớn.

## 27. Thử nghiệm các tình huống vận hành

| Kịch bản | Kết quả mong đợi |
|---|---|
| Hikari pool đạt ngưỡng pause | Controller yêu cầu pause đúng container |
| Pool dưới ngưỡng resume, DB healthy | Resume có hysteresis |
| DB down nhưng active connections bằng 0 | Không resume sai |
| Pause giữa poll lớn | Record đã poll được xử lý theo semantics, record mới dừng |
| Producer tiếp tục gửi khi paused | Lag tăng, record vẫn ở Kafka |
| Pause kéo dài | Container poll duy trì group khi consumer thread không bị block |
| Listener bị chặn trong SQL query | Timeout hữu hạn, không treo vô thời hạn |
| DB commit xong, crash trước Kafka offset commit | Idempotency bảo vệ redelivery |
| Manual acknowledge bị gọi sớm | Test phát hiện nguy cơ mất dữ liệu |
| Nhiều replicas resume cùng lúc | Controller/rate limiter tránh overload mới |
| Rebalance trong lúc pause partition | Assignment và pause state hợp lệ |
| Lỗi schema cố định | Error handler/DLT chứ không pause mãi |
| Retry khi DB outage | Không tạo retry storm vô hạn |
| Graceful shutdown khi container đang pause | Lifecycle và redelivery an toàn |

Nên kiểm tra actual pause state, committed offsets, database state, listener calls và consumer lag. Một unit test chỉ gọi pause() trên mock container chưa chứng minh group membership và xử lý offset đúng.

## 28. Quy trình áp dụng trong production

1. Xác định database bottleneck qua query latency, pool waiting và CPU/IO/lock metrics.
2. Cấu hình connection/query/transaction timeouts, không để listener block vô hạn.
3. Giới hạn Kafka concurrency và max.poll.records theo DB capacity.
4. Bảo đảm listener chỉ return/ack sau DB commit.
5. Dùng event ID hoặc unique constraint để chống duplicate sau redelivery.
6. Dùng @KafkaListener id ổn định và KafkaListenerEndpointRegistry.
7. Xây health controller lấy tín hiệu pool, error rate và circuit breaker.
8. Áp pause()/resume() với hysteresis, dwell time và cooldown.
9. Theo dõi actual pause/resume events và consumer lag.
10. Khi nhiều pods, dùng recovery policy tránh thundering herd.
11. Giữ error handler/backoff/DLT policy riêng cho record đã lỗi.
12. Kiểm tra Kafka retention đủ cho khoảng pause và catch-up.
13. Thử DB outage, query timeout, crash, rebalance và restore.
14. Thiết lập runbook cho stuck pause, flapping và backlog quá lớn.

## 29. Checklist triển khai

- Có định nghĩa rõ database overload, không chỉ dựa vào một số đo.
- Pause/resume điều khiển qua Spring Kafka container, không từ worker thread gọi trực tiếp KafkaConsumer.pause().
- Hiểu isPauseRequested khác với trạng thái pause thực tế.
- Biết pause áp dụng tại poll boundary; record đang xử lý không tự bị cancel.
- pauseImmediate chỉ bật nếu loại listener và phiên bản hỗ trợ.
- Ngưỡng pause/resume có hysteresis và thời gian ổn định.
- Controller không resume khi còn manual pause hoặc circuit breaker OPEN.
- Connection acquisition/query timeout ngăn listener treo.
- Concurrency và max.poll.records phù hợp database capacity.
- Listener chỉ commit offset sau khi side effect bền vững.
- Idempotency giúp redelivery không nhân đôi DB effect.
- Retry có giới hạn; DLT cho lỗi cố định.
- Health-based pause không nuốt lỗi của record đang xử lý.
- Kafka retention đủ chứa dữ liệu trong thời gian pause.
- Có phương án rút backlog sau khi database phục hồi.
- Nhiều replicas không resume tạo tải đột ngột.
- Partition pause được xử lý đúng khi assignment thay đổi.
- Có monitoring pause duration, lag, DB latency, pool saturation và DLT.
- Đã test crash/rebalance sau DB commit trước Kafka offset commit.

**Kết luận:** Tạm dừng listener Spring Kafka khi database quá tải là biện pháp backpressure để bảo vệ downstream: container có thể giữ consumer group, tiếp tục poll nhưng không giao thêm record mới. Dữ liệu còn ở Kafka cho tới khi hệ thống có thể xử lý. Để thiết kế này an toàn, cần kết hợp health signals, hysteresis, timeout, giới hạn concurrency, acknowledgement sau DB commit, idempotency và kế hoạch xử lý backlog. Pause chỉ là van điều tiết đầu vào; nó **không thay thế transaction, retry/DLT hay việc khắc phục bottleneck database**.

