# Đo tải, theo dõi lag và kiểm chứng phục hồi sau lỗi

Một ứng dụng Spring Cloud Stream có thể khởi động thành công và vẫn không đáp ứng được tải thực tế. Producer có thể phát sự kiện nhanh hơn consumer xử lý; một partition có thể bị dồn tải; retry có thể che khuất lỗi kéo dài; hoặc consumer khởi động lại nhưng không xử lý hết backlog trong thời gian vận hành cho phép. Vì vậy, cần đo toàn bộ đường đi của sự kiện, theo dõi độ trễ của hàng đợi và chủ động tạo lỗi để xác nhận khả năng phục hồi.

Bài thực hành này xây dựng quy trình kiểm chứng cho pipeline Supplier/Function/Consumer chạy trên Kafka, RabbitMQ hoặc Pulsar. Ta sẽ xác định tải mục tiêu, tạo dữ liệu có thể đối soát, quan sát thông lượng và lag, dừng hoặc làm chậm consumer, khởi động lại dịch vụ, rồi xác nhận dữ liệu đã được xử lý đầy đủ và backlog đã trở về mức bình thường.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Phân biệt thông lượng, độ trễ xử lý, backlog, consumer lag và tuổi của sự kiện cũ nhất.
- Thiết kế bài đo baseline, tải ổn định, tải tăng đột biến và soak test.
- Đo số sự kiện vào, số sự kiện xử lý thành công, lỗi, retry và thời gian xử lý bằng Micrometer.
- Đọc lag theo từng partition của Kafka; đọc queue depth và unacked của RabbitMQ; đọc subscription backlog của Pulsar.
- Tính thời gian cần để tiêu backlog khi producer vẫn tiếp tục gửi sự kiện.
- Kiểm chứng consumer restart, broker reconnect, redelivery, retry và dead-letter queue.
- Phân biệt mất dữ liệu với xử lý trùng, đồng thời kiểm tra tính idempotent của consumer.
- Đưa ra kết luận dựa trên số liệu và tiêu chí chấp nhận đã xác định trước.

## 2. Mô hình pipeline và các điểm cần đo

Xét luồng xử lý đơn hàng:

```text
Supplier / Producer
        |
        v
   Broker topic / queue
        |
        v
Consumer group / subscription
        |
        v
Function xử lý nghiệp vụ
        |
        v
Database hoặc dịch vụ đích
```

Mỗi điểm có một loại số liệu riêng:

| Điểm đo | Câu hỏi cần trả lời | Số liệu nên thu thập |
|---|---|---|
| Producer | Ứng dụng phát được bao nhiêu sự kiện? | Số sự kiện gửi, tốc độ gửi, lỗi gửi |
| Broker | Sự kiện đang chờ bao nhiêu? | Queue depth, log end offset, subscription backlog |
| Consumer | Consumer đang theo kịp producer không? | Lag, số consumer đang hoạt động, tốc độ đọc |
| Function | Mỗi sự kiện mất bao lâu để xử lý? | Processing latency, số lần lỗi, retry |
| Hệ thống đích | Kết quả có được ghi nhận đúng không? | Số bản ghi duy nhất, lỗi giao dịch, độ trễ ghi |
| Toàn pipeline | Sự kiện từ lúc phát đến lúc hoàn tất mất bao lâu? | End-to-end latency, tuổi sự kiện cũ nhất |

Không nên chỉ nhìn CPU hoặc số lượng message đã gửi. CPU thấp có thể đi cùng backlog tăng nếu consumer đang chờ một dịch vụ bên ngoài; producer báo gửi thành công cũng chưa chứng minh nghiệp vụ đã hoàn tất.

## 3. Phân biệt throughput, latency và lag

**Throughput** là số sự kiện được xử lý trong một đơn vị thời gian, thường dùng event/second. Cần tách ít nhất ba tốc độ:

- Ingress rate: tốc độ producer đưa sự kiện vào broker.
- Consume rate: tốc độ consumer lấy sự kiện khỏi broker.
- Completion rate: tốc độ xử lý nghiệp vụ hoàn tất thành công.

Ba tốc độ này có thể khác nhau. Consumer có thể đọc nhanh nhưng xử lý chậm, khiến số message đang nằm trong bộ nhớ hoặc trạng thái unacked tăng.

**Processing latency** là thời gian function xử lý một sự kiện, từ lúc bắt đầu đến lúc kết thúc phần nghiệp vụ. **End-to-end latency** là thời gian từ lúc sự kiện được tạo đến khi nghiệp vụ hoàn tất. End-to-end latency bao gồm thời gian chờ trong broker, thời gian chờ consumer, xử lý và các lần retry.

**Backlog** là lượng công việc đang chờ xử lý. **Consumer lag** thường biểu thị khoảng cách giữa vị trí mới nhất của log và vị trí consumer đã xác nhận. Lag tăng liên tục có nghĩa consumer đang tụt lại so với producer. Lag là số lượng record hoặc message theo cách đo của broker; nó không tự động cho biết người dùng phải chờ bao nhiêu giây.

Cần theo dõi thêm **oldest message age** — tuổi của sự kiện cũ nhất chưa hoàn tất. Hai consumer group có cùng lag 10.000 record nhưng tốc độ phát khác nhau có thể có thời gian chờ rất khác nhau.

| Chỉ số | Ý nghĩa | Dùng để phát hiện |
|---|---|---|
| Ingress rate | Sự kiện đi vào broker mỗi giây | Tải đầu vào tăng |
| Completion rate | Sự kiện hoàn tất mỗi giây | Năng lực xử lý thực tế |
| Lag / backlog | Số sự kiện đang chờ | Consumer không theo kịp |
| Oldest message age | Thời gian sự kiện cũ nhất đã chờ | Vi phạm SLA độ trễ |
| Processing p50/p95/p99 | Phân vị thời gian xử lý | Chậm ở một phần request |
| Retry rate | Số lần thử lại | Lỗi tạm thời hoặc dependency không ổn định |
| DLQ rate | Số sự kiện chuyển sang dead-letter | Sự kiện không thể xử lý theo chính sách hiện tại |
| Rebalance / redelivery | Consumer group phân công lại hoặc broker giao lại | Consumer mất kết nối, restart hoặc ack không thành công |

Một giá trị trung bình tốt có thể che khuất một nhóm sự kiện xử lý rất chậm. Khi đánh giá latency, hãy xem p95 và p99 cùng với p50, số lượng mẫu và thời gian quan sát.

## 4. Tính năng lực xử lý và thời gian tiêu backlog

Gọi:

- `λ`: tốc độ sự kiện mới đi vào, đơn vị event/second.
- `μ`: tốc độ hoàn tất của consumer group, cùng đơn vị.
- `B`: số sự kiện đang chờ.
- `t`: thời gian quan sát.

Nếu `μ > λ`, consumer có phần năng lực dư để tiêu backlog. Nếu `μ = λ`, backlog gần như không giảm. Nếu `μ < λ`, backlog tiếp tục tăng.

Khi tải tương đối ổn định và năng lực xử lý không đổi, thời gian tiêu backlog gần đúng là:


`T_drain = B / (μ - λ)`, với `μ > λ`.


Ví dụ, consumer đang hoàn tất 1.200 event/s, producer tiếp tục gửi 900 event/s và backlog có 108.000 sự kiện:


`T_drain = 108.000 / (1.200 - 900) = 360 giây`.


Nếu producer dừng hoàn toàn thì thời gian gần đúng là `108.000 / 1.200 = 90` giây. Vì thế, không được lấy backlog chia cho tốc độ consumer rồi kết luận đó là thời gian phục hồi khi producer vẫn hoạt động.

Khi `μ < λ`, tốc độ tăng backlog xấp xỉ `λ - μ`. Ví dụ producer gửi 1.000 event/s nhưng consumer chỉ hoàn tất 750 event/s, backlog tăng khoảng 250 event/s. Sau 10 phút, backlog có thể tăng khoảng 150.000 sự kiện nếu không có giới hạn hoặc biến động khác.

Các công thức trên là ước lượng vận hành. Tải thực tế còn chịu ảnh hưởng của phân phối key, số partition, batch, retry, độ trễ database, garbage collection và tốc độ broker. Hãy dùng số đo trong cửa sổ đủ dài để lập kế hoạch capacity.

## 5. Chuẩn bị môi trường đo

Trước khi chạy tải, ghi lại cấu hình và điều kiện thử nghiệm:

- Phiên bản Java, Spring Boot, Spring Cloud Stream và binder đang dùng.
- Broker, số partition hoặc queue, replication và chính sách lưu trữ.
- Consumer group hoặc subscription, số instance, concurrency và số consumer thực sự hoạt động.
- Cấu hình retry, backoff, ack/commit, DLQ và timeout của dependency.
- CPU, RAM, giới hạn container, số kết nối và cấu hình database.
- Dữ liệu thử nghiệm, kích thước payload và phân bố key.
- Thời điểm bắt đầu, thời gian warm-up, thời gian tải ổn định và thời gian recovery.

Dùng topic, queue hoặc namespace thử nghiệm riêng để tránh trộn dữ liệu với môi trường dùng chung. Đặt mã nhận diện cho mỗi lần chạy, chẳng hạn `runId=load-2026-11-24-a`, và mã duy nhất cho từng sự kiện. Đồng bộ đồng hồ giữa máy phát tải, consumer và hệ thống quan sát nếu cần đo end-to-end latency bằng timestamp.

Không đưa thông tin nhạy cảm vào payload thử nghiệm. Dùng kích thước và cấu trúc dữ liệu gần với sự kiện thật; payload quá nhỏ có thể làm kết quả thông lượng lạc quan hơn thực tế.

## 6. Cấu hình consumer có group và DLQ

Ví dụ dưới đây dùng Kafka binder và function tên `processOrder`. Tên binding đầu vào của function là `processOrder-in-0`.

```yaml
spring:
  application:
    name: order-stream
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 3
            concurrency: 3
    kafka:
      binder:
        brokers: localhost:9092
      bindings:
        processOrder-in-0:
          consumer:
            enable-dlq: true
```

Trong cấu hình này:

- `group` tạo danh tính consumer group ổn định để broker lưu tiến độ tiêu thụ.
- `max-attempts` đặt số lần thử xử lý theo cấu hình consumer của Spring Cloud Stream.
- `concurrency` yêu cầu Kafka binder chạy nhiều consumer thread cho binding.
- `enable-dlq` bật dead-letter handling của Kafka binder cho sự kiện không xử lý được theo chính sách retry.

Số consumer hoạt động song song trong một group bị giới hạn bởi số partition có thể được gán. Nếu topic có 3 partition thì tăng concurrency lên 8 không tự tạo ra 8 luồng đọc partition độc lập; một số consumer có thể không được gán partition. Tăng số partition có ảnh hưởng đến thứ tự theo key, phân bố dữ liệu và kế hoạch vận hành, vì vậy cần đánh giá trước khi thay đổi.

Tên thuộc tính và hành vi chi tiết có thể thay đổi theo phiên bản Spring Cloud Stream và binder. Đối chiếu với tài liệu đúng phiên bản trong dependency BOM của dự án. Với RabbitMQ và Pulsar, cấu hình queue, subscription, retry và dead-letter có cơ chế riêng của binder và broker.

## 7. Gắn metrics vào function bằng Micrometer

Spring Boot Actuator và Micrometer giúp quan sát thời gian xử lý, số lỗi và end-to-end latency. Ví dụ sau dùng timer và counter có tên ổn định. Không gắn `eventId`, email, order ID hoặc giá trị thay đổi theo từng message làm metric tag, vì số lượng time series có thể tăng không giới hạn.

Lớp metric:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

@Component
public class OrderMetrics {
    private final Timer processingTimer;
    private final Timer endToEndTimer;
    private final Counter processingFailures;

    public OrderMetrics(MeterRegistry registry) {
        this.processingTimer = Timer.builder("app.orders.processing")
                .description("Time spent processing one order event")
                .register(registry);

        this.endToEndTimer = Timer.builder("app.orders.end.to.end")
                .description("Time from event creation to successful processing")
                .register(registry);

        this.processingFailures = Counter.builder("app.orders.processing.failures")
                .description("Number of failed processing attempts")
                .register(registry);
    }

    public void recordProcessing(long elapsedNanos) {
        processingTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
    }

    public void recordEndToEnd(Instant createdAt) {
        Duration delay = Duration.between(createdAt, Instant.now());
        if (!delay.isNegative()) {
            endToEndTimer.record(delay);
        }
    }

    public void recordFailure() {
        processingFailures.increment();
    }
}
```

Function tiêu thụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

import java.time.Instant;
import java.util.function.Consumer;

@Configuration
public class OrderFunctions {
    @Bean
    Consumer<Message<OrderCreated>> processOrder(
            OrderService orderService,
            OrderMetrics metrics) {

        return message -> {
            long started = System.nanoTime();
            OrderCreated event = message.getPayload();

            try {
                orderService.handle(event);
                metrics.recordEndToEnd(event.createdAt());
            } catch (RuntimeException exception) {
                metrics.recordFailure();
                throw exception;
            } finally {
                metrics.recordProcessing(System.nanoTime() - started);
            }
        };
    }
}

record OrderCreated(String eventId, Instant createdAt, int quantity) {}
```

Ví dụ giả định `OrderService.handle` là phần nghiệp vụ đã có trong ứng dụng. Function ném lại exception để cơ chế error handling và retry của Spring Cloud Stream tiếp tục hoạt động. Nếu nuốt exception rồi trả về bình thường, binder có thể xem message là đã xử lý thành công và tiến độ tiêu thụ có thể được xác nhận dù nghiệp vụ thất bại.

Timer xử lý được ghi ở cả nhánh thành công và thất bại. End-to-end timer chỉ ghi khi xử lý hoàn tất thành công. Counter lỗi đếm số lần xử lý thất bại; một sự kiện được retry ba lần có thể làm counter tăng nhiều lần. Khi cần đếm số sự kiện duy nhất thất bại, hãy đối soát theo event ID ở kho dữ liệu hoặc tạo metric nghiệp vụ phù hợp, tránh dùng event ID làm tag.

Timestamp `createdAt` cần được tạo tại producer và đồng hồ các máy cần đồng bộ. Nếu đồng hồ lệch, end-to-end latency có thể âm hoặc sai lệch. `System.nanoTime()` phù hợp để đo khoảng thời gian trong cùng tiến trình; không dùng nó làm timestamp trao đổi giữa các máy.

## 8. Bật Actuator và xuất metrics

Thêm các dependency Actuator và registry Prometheus tương ứng với Spring Boot đang dùng. Ví dụ cấu hình:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
  metrics:
    distribution:
      percentiles-histogram:
        app.orders.processing: true
        app.orders.end.to.end: true
```

Các endpoint thường dùng:

- `/actuator/health`: trạng thái health indicator.
- `/actuator/metrics`: khám phá meter và xem số liệu của một meter.
- `/actuator/prometheus`: định dạng để Prometheus scrape, khi đã thêm registry tương ứng.

Ví dụ kiểm tra metric:

```bash
curl http://localhost:8080/actuator/metrics/app.orders.processing
curl http://localhost:8080/actuator/prometheus
```

Trong môi trường thật, chỉ expose endpoint cần thiết và đặt xác thực, phân quyền, network policy phù hợp. Endpoint metrics có thể tiết lộ cấu trúc vận hành của dịch vụ. Không mở actuator không bảo vệ ra Internet.

Micrometer timer thường cung cấp count, total time và max; histogram hoặc percentile cần cấu hình phù hợp với registry. Percentile phía client và histogram phía server có đặc tính khác nhau. Khi so sánh p95/p99 giữa các instance, ưu tiên histogram có bucket tương thích để hệ thống quan sát tổng hợp được dữ liệu.

## 9. Theo dõi lag trên Kafka

Kafka lưu log theo partition. Mỗi consumer group có tiến độ tiêu thụ riêng. Lag thường được tính từ log end offset trừ committed offset của group cho từng partition. Đây là khoảng cách offset; nó không phải số giây chờ.

Dùng công cụ đi kèm Kafka:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-processor
```

Trên Windows có thể dùng script `kafka-consumer-groups.bat` trong thư mục `bin\windows` của bản phân phối Kafka.

Kết quả thường có các cột như `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG`. Đọc theo từng partition:

- Lag của một partition tăng trong khi các partition khác gần 0 có thể chỉ ra key skew, một consumer bị chậm hoặc vấn đề phân công.
- Lag tăng đồng đều ở tất cả partition thường cho thấy tổng năng lực consumer thấp hơn ingress rate.
- Lag giảm sau khi tăng consumer capacity cho thấy phần năng lực bổ sung có hiệu quả.
- Lag đột ngột thay đổi cùng lúc với rebalance có thể là tác động của consumer restart, membership hoặc thay đổi assignment.

Kiểm tra cả consumer group state và members khi cần tìm nguyên nhân rebalance. Một lệnh describe chụp tại một thời điểm không đủ để kết luận hệ thống đang ổn định; hãy ghi lại số liệu theo chu kỳ và quan sát xu hướng.

Offset là vị trí trong log, không nhất thiết đồng nhất với số message nghiệp vụ nếu có transaction, record bị lọc hoặc cách ghi nhận offset đặc thù. Khi đối soát dữ liệu, dùng event ID và kết quả nghiệp vụ cùng với lag.

## 10. Theo dõi backlog trên RabbitMQ

RabbitMQ không dùng Kafka consumer offset để biểu diễn lag. Với queue, hãy theo dõi ít nhất:

- `messages_ready`: message đang chờ được consumer nhận.
- `messages_unacknowledged`: message đã giao cho consumer nhưng chưa được xác nhận.
- `consumers`: số consumer đang đăng ký.
- Tốc độ publish, deliver, ack và redeliver.
- Tuổi của message cũ nhất nếu công cụ monitoring hoặc cách instrument của hệ thống cung cấp.

Có thể xem nhanh bằng CLI:

```bash
rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
```

Nếu `messages_ready` tăng, consumer có thể không lấy kịp message. Nếu `messages_unacknowledged` tăng liên tục, consumer có thể đang xử lý chậm, giữ message quá lâu hoặc không ack. Nếu redelivery tăng, kiểm tra consumer crash, channel đóng, timeout và chính sách reject/requeue.

Với dead-letter exchange hoặc dead-letter queue, theo dõi số message đi vào DLQ và nguyên nhân dead-letter. Một queue chính có độ sâu thấp chưa chắc hệ thống khỏe nếu message đang bị chuyển sang DLQ nhanh.

## 11. Theo dõi backlog trên Apache Pulsar

Với Pulsar, theo dõi trạng thái theo topic và subscription. Các số liệu hữu ích gồm:

- Message backlog của subscription.
- Message rate in và out.
- Số message chưa được acknowledge và số lần redelivery.
- Consumer đang kết nối, trạng thái subscription và phân bố tải.
- DLQ hoặc dead-letter topic nếu ứng dụng bật dead-letter policy.

Có thể kiểm tra thống kê topic bằng lệnh:

```bash
pulsar-admin topics stats persistent://tenant/namespace/orders
```

Trong kết quả, xem phần subscription tương ứng với consumer của ứng dụng và các trường backlog, rate, unacked hoặc redelivery được broker cung cấp ở phiên bản đang chạy. Tên trường và cấu trúc JSON có thể khác giữa phiên bản Pulsar.

Pulsar backlog không nên được diễn giải bằng công thức offset của Kafka. Dùng số liệu subscription và tuổi message để xác định consumer có theo kịp không. Đồng thời kiểm tra backlog quota, retention và chính sách subscription để tránh nhầm việc message hết hạn hoặc bị giới hạn lưu trữ với việc consumer đã xử lý thành công.

## 12. Thiết kế bài đo tải có thể lặp lại

Một bài load test có ích cần tái lập được và phản ánh cách ứng dụng hoạt động. Chuẩn bị payload gần với dữ liệu thật, giữ kích thước message ổn định trong từng kịch bản và phân bố key giống thực tế. Nếu mọi message đều dùng cùng một key Kafka, phép đo có thể dồn vào một partition và không phản ánh tải phân bố đều.

Thực hiện các pha sau:

1. **Baseline:** chạy ở tải thấp để xác nhận hệ thống, dashboard và đối soát dữ liệu hoạt động.
2. **Warm-up:** tăng tải từ từ để JVM JIT, connection pool và cache đạt trạng thái ổn định.
3. **Ramp-up:** tăng ingress rate theo từng nấc, giữ mỗi nấc đủ lâu để thấy xu hướng lag.
4. **Steady-state:** giữ tải mục tiêu trong một khoảng thời gian định trước.
5. **Burst:** tăng tải đột ngột để xem hệ thống hấp thụ đỉnh và backlog tăng ra sao.
6. **Soak:** giữ tải dài hơn để phát hiện rò rỉ bộ nhớ, tăng connection, GC kéo dài hoặc suy giảm dần.
7. **Recovery:** hạ hoặc dừng tải, đo thời gian tiêu backlog và trở lại trạng thái bình thường.

Mỗi pha cần có thời điểm bắt đầu và kết thúc, ingress rate thực tế, completion rate, p95/p99, lag, oldest message age, error rate và tài nguyên sử dụng. Đừng chỉ ghi mức tải dự định; ghi mức tải mà producer thực sự phát được.

### 12.1. Tạo tải qua StreamBridge

Có thể dùng một ứng dụng producer nhỏ hoặc profile chuyên cho load test. Ví dụ sau phát sự kiện JSON qua output binding tên `orders-out-0`:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
```

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.cloud.stream.function.StreamBridge;

import java.time.Instant;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

@Configuration
@Profile("load")
public class LoadPublisher {
    @Bean
    ApplicationRunner publishLoad(StreamBridge streamBridge) {
        return args -> {
            int totalEvents = 100_000;
            long targetPerSecond = 1_000;
            long intervalNanos =
                    TimeUnit.SECONDS.toNanos(1) / targetPerSecond;
            long nextSend = System.nanoTime();

            for (int i = 0; i < totalEvents; i++) {
                OrderCreated event = new OrderCreated(
                        "load-" + i,
                        Instant.now(),
                        1);

                boolean accepted = streamBridge.send("orders-out-0", event);
                if (!accepted) {
                    throw new IllegalStateException(
                            "StreamBridge did not accept event " + event.eventId());
                }

                nextSend += intervalNanos;
                long waitNanos = nextSend - System.nanoTime();
                if (waitNanos > 0) {
                    LockSupport.parkNanos(waitNanos);
                }
            }
        };
    }
}
```

Chạy publisher bằng profile `load` trong môi trường thử nghiệm. Điều chỉnh số sự kiện, tốc độ mục tiêu và payload theo kịch bản. Nếu cần kiểm tra tải đồng thời, dùng nhiều producer instance hoặc một load generator có khả năng kiểm soát concurrency.

Giá trị `true` từ `StreamBridge.send` cho biết message được chấp nhận qua channel của ứng dụng; nó không thay thế xác nhận rằng consumer đã hoàn tất nghiệp vụ hoặc dữ liệu đã được ghi bền vững theo yêu cầu. Để kết luận, phải đối chiếu số sự kiện duy nhất đã phát với kết quả nghiệp vụ sau khi consumer xử lý xong.

Không bật profile load trong môi trường production. Khi phát tải đồng thời, dùng event ID duy nhất xuyên suốt tất cả producer để tránh đếm nhầm hoặc ghi đè dữ liệu.

### 12.2. Đo riêng năng lực broker

Với Kafka, công cụ `kafka-producer-perf-test.sh` có thể đo năng lực ghi của broker bằng payload có kích thước cố định. Ví dụ:

```bash
kafka-producer-perf-test.sh \
  --topic broker-load-test \
  --num-records 1000000 \
  --record-size 512 \
  --throughput 5000 \
  --producer-props bootstrap.servers=localhost:9092 acks=all
```

Đây là phép đo broker/producer với record thử nghiệm. Nó không chạy JSON conversion, function, database hay retry của ứng dụng Spring Cloud Stream. Hãy dùng phép đo này để tách giới hạn broker khỏi giới hạn xử lý nghiệp vụ, không dùng nó làm bằng chứng duy nhất về throughput end-to-end.

## 13. Định nghĩa tiêu chí chấp nhận trước khi chạy

Không có một ngưỡng lag hoặc p99 đúng cho mọi hệ thống. Ngưỡng phải xuất phát từ SLA, tốc độ phát, thời gian lưu trữ và khả năng phục hồi mà sản phẩm yêu cầu.

Một bộ tiêu chí mẫu có thể gồm:

| Hạng mục | Tiêu chí cần xác định |
|---|---|
| Tải mục tiêu | Ingress rate duy trì trong khoảng tải đã chọn |
| Throughput | Completion rate không thấp hơn nhu cầu nghiệp vụ |
| Backlog | Không tăng liên tục ở tải steady-state |
| Latency | p95/p99 và oldest message age nằm trong SLA |
| Lỗi | Tỷ lệ lỗi nghiệp vụ và retry không vượt giới hạn |
| DLQ | Không có sự kiện hợp lệ bị chuyển DLQ ngoài dự kiến |
| Recovery | Consumer khởi động lại, tiếp tục xử lý và tiêu backlog trong RTO |
| Tính đầy đủ | Tất cả event ID hợp lệ đều có kết quả cuối cùng |
| Tính duy nhất | Xử lý trùng không tạo tác dụng phụ trùng lặp |
| Tài nguyên | CPU, heap, GC, connection và broker storage còn trong giới hạn |

Ghi rõ cửa sổ đo và điều kiện loại bỏ warm-up. Một hệ thống có thể đạt throughput trong 30 giây nhưng không giữ được tải trong 30 phút. Tiêu chí phải phản ánh thời gian vận hành cần thiết.

## 14. Kiểm tra lag trong lúc tải ổn định

Khi chạy steady-state:

1. Ghi lại ingress rate từ producer hoặc broker.
2. Ghi completion rate từ metric nghiệp vụ.
3. Lấy lag/backlog theo partition, queue hoặc subscription theo chu kỳ.
4. Ghi processing p50/p95/p99 và end-to-end p95/p99.
5. Theo dõi retry, DLQ, redelivery và rebalance.
6. Ghi CPU, heap, GC, thread, connection pool, database latency và broker resource.
7. So sánh xu hướng trong nhiều cửa sổ liên tiếp.

Nếu ingress rate cao hơn completion rate trong thời gian dài, backlog sẽ tăng. Nếu throughput tương đương nhưng oldest message age tăng, hãy kiểm tra phân phối message, retry kéo dài, partition bị nóng hoặc một số sự kiện bị giữ lâu.

Khi một partition có lag lớn hơn rõ rệt, kiểm tra key distribution và thời gian xử lý theo loại nghiệp vụ. Không nên tăng concurrency trước khi hiểu giới hạn partition và dependency; thêm thread có thể làm tăng contention hoặc tải database mà không tăng completion rate.

## 15. Kiểm chứng consumer dừng và khởi động lại

Đây là kịch bản cơ bản để xác nhận consumer có tiếp tục từ tiến độ broker đã lưu:

1. Phát một lượng sự kiện có event ID duy nhất và ghi lại tổng số.
2. Chờ consumer hoạt động ổn định, ghi nhận lag ban đầu.
3. Dừng toàn bộ instance consumer trong khi producer vẫn phát ở tốc độ đã định.
4. Quan sát backlog tăng và xác nhận producer vẫn có thể phát dữ liệu theo kịch bản.
5. Khởi động lại consumer với cùng group hoặc subscription.
6. Theo dõi consumer assignment, completion rate, lag và oldest message age.
7. Chờ backlog trở về ngưỡng bình thường theo tiêu chí đã đặt.
8. Đối soát toàn bộ event ID và kết quả nghiệp vụ.

Với Kafka, giữ nguyên group ID để consumer tiếp tục từ committed offset của group. Tạo group mới có thể khiến consumer đọc lại từ vị trí khác tùy cấu hình offset reset, làm sai kết quả thử nghiệm.

Với RabbitMQ, kiểm tra message chưa ack được giao lại sau khi channel hoặc connection đóng. Với Pulsar, kiểm tra subscription backlog và redelivery theo subscription đang dùng. Không so sánh trực tiếp số liệu của ba broker như thể chúng có cùng ngữ nghĩa.

## 16. Kiểm chứng lỗi xảy ra giữa xử lý và xác nhận message

Một lỗi quan trọng là consumer đã tạo tác dụng phụ nhưng chưa xác nhận tiến độ với broker. Ví dụ:

1. Consumer nhận sự kiện `order-123`.
2. Database commit thay đổi đơn hàng.
3. Process bị dừng trước khi offset hoặc ack được xác nhận.
4. Broker giao lại sự kiện sau khi consumer khởi động lại.

Trong mô hình giao nhận at-least-once, tình huống này có thể tạo xử lý lặp. Đây là hành vi cần được kiểm soát bằng idempotency. Hãy thiết kế một test có chủ đích để dừng process ở ranh giới sau khi ghi dữ liệu nhưng trước khi ack/commit, rồi xác nhận lần giao lại không tạo thêm tác dụng phụ.

Không được giả định mọi cấu hình binder đều có cùng thời điểm commit hoặc ack. Hãy kiểm tra ack mode, auto commit, transaction và error handling của binder đang dùng. Nếu xác nhận tiến độ xảy ra trước khi nghiệp vụ bền vững, lỗi có thể gây mất dữ liệu; nếu xác nhận sau khi nghiệp vụ bền vững, lỗi có thể gây giao lại. Chính sách phải phù hợp với yêu cầu của hệ thống.

## 17. Kiểm chứng retry và dead-letter

Tạo một loại payload thử nghiệm có thể chủ động gây lỗi, ví dụ một event có trường nghiệp vụ không hợp lệ hoặc một mã làm dịch vụ phụ thuộc trả lỗi. Thực hiện các bước:

1. Phát một sự kiện hợp lệ và một sự kiện lỗi có chủ đích.
2. Xác nhận sự kiện hợp lệ được xử lý thành công.
3. Xác nhận sự kiện lỗi được retry đúng số lần và theo backoff đã cấu hình.
4. Kiểm tra log và metric để phân biệt lần thử với event duy nhất.
5. Xác nhận sự kiện vượt chính sách retry đi vào DLQ hoặc dead-letter topic/queue theo binder.
6. Kiểm tra payload, header, exception metadata và event ID còn đủ để điều tra.
7. Khắc phục nguyên nhân rồi replay DLQ theo quy trình có kiểm soát.
8. Đối soát tác dụng phụ để bảo đảm replay không tạo đơn hàng hoặc giao dịch trùng.

DLQ là nơi cô lập sự kiện chưa xử lý được, không phải nơi tự động sửa dữ liệu. Không replay toàn bộ DLQ vào topic chính khi chưa xác định nguyên nhân, thứ tự, tốc độ replay và khả năng idempotent. Một payload lỗi có thể tạo vòng lặp retry hoặc làm backlog mới tăng nhanh.

## 18. Kiểm chứng broker reconnect và rebalance

Mô phỏng broker tạm thời không truy cập được hoặc làm gián đoạn kết nối mạng giữa consumer và broker trong môi trường thử nghiệm. Theo dõi:

- Thời điểm lỗi kết nối xuất hiện trong log và metric.
- Số lần reconnect và thời gian phục hồi kết nối.
- Trạng thái consumer group hoặc subscription.
- Rebalance, assignment và số consumer đang hoạt động.
- Lag/backlog trong thời gian gián đoạn.
- Tốc độ xử lý sau khi kết nối phục hồi.
- Số event ID duy nhất hoàn tất và số tác dụng phụ trùng.

Không chỉ kiểm tra việc process vẫn chạy. Một container có thể ở trạng thái running nhưng consumer không nhận được message. Health check nên phản ánh điều kiện cần thiết của ứng dụng, còn dashboard cần thể hiện tiến độ tiêu thụ và độ trễ.

Nếu restart liên tục, kiểm tra timeout, heartbeat, session timeout, max poll interval và thời gian xử lý một batch đối với Kafka; với RabbitMQ kiểm tra connection/channel recovery và consumer acknowledgement timeout; với Pulsar kiểm tra consumer reconnect, subscription và redelivery policy. Chọn tham số theo phiên bản broker và binder thực tế.

## 19. Kiểm chứng consumer chậm và partition lệch tải

Tạo một kịch bản làm chậm một phần xử lý, chẳng hạn tăng thời gian gọi dịch vụ phụ thuộc hoặc dùng một nhóm key tập trung vào cùng partition. Quan sát:

- Lag có tăng ở mọi partition hay chỉ một partition?
- Consumer nào có processing p95/p99 cao?
- Database connection pool hoặc thread pool có bão hòa không?
- Tăng concurrency có cải thiện completion rate hay chỉ tăng contention?
- Khi bỏ điều kiện làm chậm, backlog có tiêu hết không?

Nếu chỉ một partition bị nóng, tăng số instance có thể không giải quyết được vì một partition tại một thời điểm chỉ được gán cho một consumer trong cùng group. Xem lại key, partition strategy và kích thước partition. Thay đổi key có thể ảnh hưởng thứ tự sự kiện của cùng một thực thể, vì vậy phải giữ đúng yêu cầu nghiệp vụ.

Nếu mọi partition đều lag và database đã bão hòa, tăng consumer thread có thể khiến tình trạng xấu hơn. Cần tìm giới hạn thực sự ở dependency, batch, connection pool, CPU, network hay broker.

## 20. Idempotency và đối soát dữ liệu

Trong pipeline phân tán, consumer có thể nhận lại cùng một sự kiện sau timeout, crash hoặc retry. Đếm tổng số lần function chạy không cho biết số nghiệp vụ duy nhất đã hoàn tất.

Mỗi sự kiện nên có một định danh ổn định, ví dụ `eventId`. Ở hệ thống đích, dùng unique constraint hoặc bảng inbox để ghi nhận event ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ.

Ví dụ ý tưởng:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Trong transaction xử lý, ứng dụng cố gắng ghi `event_id`. Nếu khóa đã tồn tại, sự kiện đã được xử lý trước đó; ứng dụng có thể bỏ qua tác dụng phụ lặp theo chính sách nghiệp vụ. Việc ghi dấu và cập nhật dữ liệu cần nằm trong transaction phù hợp để tránh trường hợp ghi dấu thành công nhưng nghiệp vụ chưa commit, hoặc nghiệp vụ commit mà dấu idempotency không được lưu.

Khi đối soát, dùng các tập hợp:

- `sentIds`: các event ID producer đã phát theo kết quả test.
- `completedIds`: các event ID có kết quả nghiệp vụ cuối cùng.
- `duplicateAttempts`: số lần cùng event ID được giao hoặc xử lý lại.
- `failedIds`: event ID chưa có kết quả cuối cùng và đang ở retry/DLQ.

Kiểm tra `sentIds - completedIds` để tìm sự kiện còn thiếu; kiểm tra event ID lặp trong tác dụng phụ để tìm duplicate. Một count bằng nhau không bảo đảm tập ID giống nhau.

## 21. Đo thời gian phục hồi và đặt RTO/RPO

**RTO** là thời gian mục tiêu để dịch vụ trở lại mức hoạt động chấp nhận được sau sự cố. Với pipeline event, cần định nghĩa rõ mốc kết thúc: consumer đã kết nối lại, completion rate đã phục hồi, hay backlog đã được tiêu hết. Nếu mục tiêu là xử lý hết backlog thì RTO phải tính đến thời gian drain.

**RPO** là mức mất dữ liệu tối đa có thể chấp nhận. Với test event, đo số event ID producer xác nhận đã phát nhưng không có kết quả cuối cùng sau khi recovery hoàn tất. Đồng thời phân loại event đang nằm trong DLQ, hết hạn retention hoặc chưa được replay để không nhầm trạng thái.

Ghi timeline cho mỗi lần thử:

| Mốc | Thời điểm cần ghi |
|---|---|
| T0 | Bắt đầu phát tải |
| T1 | Bắt đầu tạo lỗi |
| T2 | Consumer hoặc broker phát hiện lỗi |
| T3 | Kết nối/consumer phục hồi |
| T4 | Completion rate trở lại mức yêu cầu |
| T5 | Backlog và oldest message age trở về ngưỡng bình thường |
| T6 | Đối soát dữ liệu hoàn tất |

Từ timeline, tính thời gian phát hiện, thời gian khôi phục consumer và thời gian drain backlog. Đây là các thành phần khác nhau; một hệ thống có thể reconnect trong vài giây nhưng cần nhiều phút để xử lý hết backlog.

## 22. Ví dụ tính toán một kịch bản phục hồi

Giả sử bài test có các số liệu sau:

- Producer duy trì 900 event/s.
- Consumer group hoàn tất 1.200 event/s khi không có sự cố.
- Consumer bị dừng trong 120 giây.
- Không có giới hạn retention làm mất message trong thời gian thử.

Backlog tăng gần đúng:


`B = 900 × 120 = 108.000 sự kiện`.


Sau khi consumer khởi động lại, năng lực dư là:


`μ - λ = 1.200 - 900 = 300 sự kiện/giây`.


Thời gian tiêu backlog ước lượng:


`T_drain = 108.000 / 300 = 360 giây`.


Nếu mục tiêu recovery là 5 phút thì năng lực 1.200 event/s chưa đủ trong kịch bản này. Cần giảm ingress trong thời gian recovery, tăng năng lực xử lý thực sự, hoặc điều chỉnh RTO dựa trên yêu cầu sản phẩm. Nếu tăng completion rate lên 1.500 event/s thì năng lực dư là 600 event/s và thời gian drain gần đúng còn 180 giây.

Kết luận phải được xác nhận bằng số liệu sau khi chạy: tốc độ xử lý có giữ được mức 1.500 event/s không, database có chịu được không, p99 có vượt SLA không, và kết quả nghiệp vụ có đầy đủ không.

## 23. Dashboard và cảnh báo

Một dashboard vận hành nên có các nhóm biểu đồ:

1. **Traffic:** ingress rate, consume rate, completion rate.
2. **Backlog:** Kafka lag theo group/partition; RabbitMQ ready và unacked; Pulsar subscription backlog.
3. **Latency:** processing p50/p95/p99, end-to-end p95/p99, oldest message age.
4. **Reliability:** error rate, retry rate, redelivery, DLQ rate, rebalance và reconnect.
5. **Resources:** CPU, heap, GC pause, thread pool, connection pool, database latency và broker storage.

Cảnh báo nên kết hợp xu hướng và tác động. Ví dụ, cảnh báo khi lag tăng liên tục trong nhiều cửa sổ và oldest message age vượt SLA; cảnh báo riêng khi DLQ tăng; cảnh báo khi completion rate thấp hơn ingress rate kéo dài. Một ngưỡng lag cố định có thể không phù hợp với topic có tốc độ phát khác nhau.

Dùng tag có tập giá trị giới hạn như tên function, binder, environment hoặc kết quả xử lý. Tránh tag theo event ID, user ID, order ID hay exception message. Để điều tra một sự kiện cụ thể, dùng log có correlation ID hoặc trace, không tạo một time series cho mỗi sự kiện.

## 24. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Lag tăng đồng đều | Consumer capacity thấp hơn ingress | So sánh ingress và completion rate, CPU, DB latency |
| Chỉ một partition lag cao | Key skew hoặc consumer xử lý partition đó chậm | Xem lag từng partition, phân bố key và processing time |
| Lag thấp nhưng end-to-end latency cao | Sự kiện xử lý lâu sau khi được nhận | Đo processing timer và thời gian dependency |
| Ready tăng, unacked thấp ở RabbitMQ | Consumer thiếu hoặc không nhận message | Kiểm tra consumer count, binding và prefetch |
| Unacked tăng liên tục | Xử lý chậm hoặc ack bị giữ | Kiểm tra thời gian xử lý, timeout, channel và exception |
| Pulsar backlog tăng | Subscription không theo kịp hoặc consumer không hoạt động | Xem subscription stats, consumer và redelivery |
| Retry tăng nhưng throughput giảm | Dependency lỗi hoặc poison message | Phân loại exception, backoff và tỷ lệ retry |
| DLQ tăng | Payload lỗi hoặc chính sách xử lý không phù hợp | Đọc metadata lỗi, schema và event ID |
| Rebalance lặp lại | Consumer restart, heartbeat hoặc poll timeout | Kiểm tra log group, thời gian xử lý và cấu hình |
| Restart xong có dữ liệu trùng | Message được giao lại sau khi nghiệp vụ đã commit | Kiểm tra ranh giới commit/ack và idempotency |
| Restart xong thiếu dữ liệu | Ack/commit sớm, retention hoặc lỗi ghi đích | Đối soát event ID, offset, transaction và broker retention |
| CPU thấp nhưng lag tăng | Consumer đang chờ I/O hoặc dependency | Kiểm tra thread dump, DB/network latency và connection pool |

## 25. Quy trình thực hành hoàn chỉnh

Thực hiện lần lượt và lưu lại kết quả của mỗi bước:

1. Tạo topic/queue thử nghiệm và cấu hình consumer group hoặc subscription ổn định.
2. Bật metrics cho processing latency, end-to-end latency và processing failures.
3. Bật endpoint metrics/Prometheus trong môi trường thử nghiệm.
4. Chuẩn bị producer tạo event ID duy nhất và ghi lại tập ID đã phát.
5. Chạy baseline, xác nhận dữ liệu đi qua pipeline và đối soát thành công.
6. Chạy ramp-up rồi steady-state; ghi ingress, completion, lag và p95/p99.
7. Tạo burst; quan sát backlog tăng và thời gian trở lại bình thường.
8. Dừng consumer trong khi producer tiếp tục phát; đo tốc độ tăng backlog.
9. Khởi động consumer; đo reconnect, completion rate và thời gian drain.
10. Tạo lỗi sau khi ghi dữ liệu nhưng trước ack/commit; kiểm tra redelivery và idempotency.
11. Tạo poison message; kiểm tra retry, DLQ và quy trình replay.
12. Đối soát event ID, tác dụng phụ và kết quả cuối cùng; so sánh với RTO/RPO đã đặt.

Mỗi kịch bản nên được chạy lại ít nhất một lần sau khi thay đổi cấu hình quan trọng. Ghi rõ thay đổi nào tạo ra khác biệt; không thay đồng thời partition, concurrency, batch size và connection pool nếu muốn biết nguyên nhân cải thiện.

## 26. Bài tập mở rộng

**Bài tập 1 — Xác định giới hạn throughput**

Tăng tải theo từng nấc và tìm mức ingress cao nhất mà completion rate vẫn theo kịp, backlog không tăng liên tục và p99 nằm trong SLA. Lặp lại với payload nhỏ và payload gần kích thước thực tế. Giải thích yếu tố giới hạn ở mỗi trường hợp.

**Bài tập 2 — Tính thời gian drain**

Tại một thời điểm, backlog là 240.000 event, producer tiếp tục gửi 600 event/s và consumer hoàn tất 1.000 event/s. Tính thời gian drain gần đúng. Sau đó giả sử producer tăng lên 1.000 event/s; giải thích điều gì xảy ra với backlog.

**Bài tập 3 — Tìm partition nóng**

Phát tải với key phân bố đều, sau đó chuyển sang một key chiếm phần lớn message. So sánh lag theo partition, completion rate và p99. Đề xuất cách phân phối key mà vẫn giữ đúng thứ tự nghiệp vụ cần thiết.

**Bài tập 4 — Kiểm tra duplicate**

Tạo lỗi ngay sau khi database commit nhưng trước khi consumer xác nhận message. Ghi lại số lần event được giao, số lần function chạy và số tác dụng phụ được tạo. Thêm cơ chế idempotency rồi chạy lại để chứng minh kết quả chỉ được áp dụng một lần.

**Bài tập 5 — Kiểm tra DLQ**

Tạo một event không hợp lệ, xác nhận số lần retry, metadata trong DLQ và quy trình replay sau khi sửa dữ liệu. Chứng minh các event hợp lệ khác vẫn tiếp tục được xử lý theo chính sách của hệ thống.

## 27. Điều kiện kết thúc bài thực hành

Bài đo chỉ được xem là hoàn tất khi có bằng chứng cho các điểm sau:

- Tải mục tiêu và điều kiện thử nghiệm được ghi lại.
- Ingress rate, completion rate, lag/backlog và latency được quan sát trong steady-state.
- Có ít nhất một lần tạo backlog và đo thời gian drain sau recovery.
- Có ít nhất một lần consumer restart hoặc broker reconnect được kiểm chứng.
- Retry và DLQ hoạt động theo chính sách đã cấu hình.
- Event ID được đối soát để phát hiện cả thiếu dữ liệu và xử lý trùng.
- Kết quả đạt hoặc không đạt RTO/RPO và SLA được ghi rõ cùng số liệu hỗ trợ.

Nếu chưa đạt, ghi lại giới hạn đã tìm thấy, ví dụ partition skew, database throughput, retry storm hoặc consumer concurrency. Một báo cáo tốt chỉ ra được số liệu nào chứng minh giới hạn và phép đo tiếp theo nào sẽ xác nhận hướng khắc phục.

## 28. Tài liệu tham khảo

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Spring Cloud Stream Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/)
- [Spring Boot Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer Concepts](https://micrometer.io/docs/concepts)
- [Apache Kafka Operations — Consumer Groups](https://kafka.apache.org/documentation/#basic_ops_consumer_group)
- [RabbitMQ Monitoring](https://www.rabbitmq.com/docs/monitoring)
- [Apache Pulsar — Topic Stats](https://pulsar.apache.org/docs/next/administration-stats/)

Đối chiếu tài liệu theo đúng phiên bản Spring Boot, Spring Cloud Stream, binder và broker mà module đang sử dụng. Các tên metric do broker exporter cung cấp, cấu hình retry và dead-letter có thể khác theo phiên bản.
