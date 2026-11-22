# ConsumerFailedToStartEvent

Trong một ứng dụng Spring Kafka, việc gọi `start()` trên listener container hoặc để Spring Boot tự khởi động các `@KafkaListener` không đồng nghĩa tất cả consumer thread đã thực sự bắt đầu. Một listener container có thể được yêu cầu chạy nhưng consumer tương ứng vẫn chưa khởi động kịp thời, chẳng hạn do executor không còn thread trống. Nếu không phân biệt được “đã yêu cầu start” và “consumer đã start”, ứng dụng rất dễ báo healthy trong khi thực tế không có consumer nào đọc message.

`ConsumerFailedToStartEvent` là **application event** của Spring Kafka được phát khi một consumer **không khởi động trong khoảng chờ do `consumerStartTimeout` quy định**. Event này đặc biệt hữu ích để phát hiện thiếu năng lực của thread executor hoặc startup bị chậm/bế tắc, từ đó đưa ra cảnh báo và xác định lỗi trước khi consumer lag tăng quá lâu.

Đây là **tín hiệu timeout trong quá trình khởi động consumer**, không phải một loại Kafka record, không phải exception do listener nghiệp vụ ném ra và cũng không đồng nghĩa chắc chắn broker đang down. Bài học giải thích điều kiện phát event, cách lắng nghe, cách phân biệt với những event khác, cấu hình timeout/executor, quan sát ở production và runbook xử lý.

## 1. Vị trí của ConsumerFailedToStartEvent trong vòng đời listener

Spring Kafka tạo các listener container để quản lý consumer. Với `@KafkaListener`, container thường được đăng ký trong `KafkaListenerEndpointRegistry`. Một `ConcurrentMessageListenerContainer` có thể quản lý nhiều consumer con, tùy cấu hình `concurrency` và số partition.

Trong đường khởi động thông thường:

~~~text
Spring ApplicationContext khởi động
               |
               v
KafkaListenerEndpointRegistry
               |
               v
Listener container start()
               |
               v
Giao nhiệm vụ chạy consumer cho task executor
               |
      +--------+---------+
      |                  |
 Consumer thread      Consumer không start
 bắt đầu đúng hạn     trong consumerStartTimeout
      |                  |
      v                  v
 ConsumerStarting/   ConsumerFailedToStartEvent
 ConsumerStarted     (cảnh báo startup)
      |
      v
 Poll Kafka records
      |
      v
 @KafkaListener
~~~

Sơ đồ mô tả quan hệ chức năng. Các event trong quá trình start có thể phát trên những thread và thời điểm khác nhau; không được giả định một chuỗi event cố định tuyệt đối cho mọi version/container implementation.

### 1.1. “Không start đúng hạn” nghĩa là gì?

Spring Kafka có một khoảng chờ để nhận biết consumer thread đã bắt đầu. Nếu điều kiện start không được hoàn tất trong giới hạn này, container có thể công bố `ConsumerFailedToStartEvent`.

Tình huống điển hình:

- Một executor dùng chung đã hết thread.
- `concurrency` cao hơn số worker threads được phép chạy.
- Task executor xếp hàng nhiều công việc và consumer task phải chờ.
- Một tác vụ lâu dài đang chiếm thread lẽ ra dùng cho Kafka consumer.
- Startup bị trì hoãn bởi lifecycle hoặc khởi tạo tài nguyên ở thời điểm không phù hợp.

Event phản ánh **quá trình start**. Nó không trực tiếp mô tả lỗi xử lý một record, lỗi deserialize, một record bị retry hay việc commit offset thất bại.

### 1.2. Event không đồng nghĩa toàn bộ ứng dụng đã chết

Về mặt vận hành, ứng dụng có thể vẫn phục vụ HTTP hoặc một số listener khác vẫn chạy khi một consumer không start đúng hạn. Vì vậy, cần quyết định tác động của event lên:

- Log và cảnh báo.
- Trạng thái readiness.
- Dashboard số consumer mong đợi so với consumer đã khởi động.
- Quy trình khôi phục hoặc rollback deployment.

Không nên mặc định mỗi lần nhận event là lập tức `System.exit()`; hành động đó có thể tạo restart loop và che khuất nguyên nhân thiếu thread.

## 2. Vì sao application event này quan trọng?

Không có event start failure, lỗi có thể chỉ biểu hiện gián tiếp:

- Consumer lag tăng.
- Topic có dữ liệu nhưng không thấy log của listener.
- Request downstream chờ kết quả Kafka quá lâu.
- Dashboard có số replica đúng nhưng throughput bằng không.
- Một pod được đánh dấu Ready quá sớm.

`ConsumerFailedToStartEvent` cung cấp tín hiệu gần với nguồn sự cố hơn: container không đạt mốc khởi động consumer đúng hạn.

Điều này giúp phân biệt ba tình huống:

| Tình huống | Biểu hiện | Hướng điều tra |
|---|---|---|
| Consumer không start đúng hạn | `ConsumerFailedToStartEvent` có thể phát | Task executor, concurrency, lifecycle và startup |
| Consumer đã start nhưng không có record | Listener im lặng, có thể không có lag | Topic, partition assignment, offset, subscription |
| Consumer đã start nhưng bị kẹt poll/processing | Lag hoặc processing time tăng | Broker/network, listener block, `NonResponsiveConsumerEvent` và metrics |

Khi consumer không start, chỉ tăng `max.poll.records` hoặc điều chỉnh batch size thường không sửa được nguyên nhân.

## 3. Các application events liên quan

Spring Kafka công bố nhiều event theo vòng đời container. Một runbook nên hiểu chúng khác nhau.

| Event | Thời điểm/ý nghĩa chính | Khác gì với ConsumerFailedToStartEvent? |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread bắt đầu quá trình chạy | Chưa chắc đã hoàn tất khởi động |
| `ConsumerStartedEvent` | Consumer đã start thành công | Tín hiệu positive thay vì startup timeout |
| `ConsumerFailedToStartEvent` | Consumer chưa start trong ngưỡng chờ | Chẩn đoán khởi động chậm/không chạy |
| `ConsumerStoppedEvent` | Consumer đã chạy rồi dừng | Liên quan shutdown hoặc lỗi sau khi start |
| `ContainerStoppedEvent` | Container đã dừng | Cấp container, không nhất thiết là startup failure |
| `ListenerContainerIdleEvent` | Listener không nhận record trong khoảng idle được cấu hình | Consumer có thể vẫn khỏe và poll đều |
| `NonResponsiveConsumerEvent` | Consumer không poll đúng hạn theo cơ chế giám sát | Có thể xảy ra trong lúc đang chạy, khác timeout start |
| `ConsumerPausedEvent` / `ConsumerResumedEvent` | Consumer pause/resume | Điều tiết delivery, không phải start/stop |

Mục tiêu là xác định **lifecycle stage** xảy ra lỗi. Một consumer đã nhận `ConsumerStartedEvent` rồi sau đó `ConsumerStoppedEvent` không nhất thiết là trường hợp tương ứng `ConsumerFailedToStartEvent`.

### 3.1. Start timeout khác poll timeout

Kafka có nhiều ngưỡng thời gian:

- `consumerStartTimeout`: khoảng chờ do Spring Kafka container dùng để nhận biết consumer start.
- `pollTimeout`: khoảng chờ của một lời gọi poll ở container.
- `max.poll.interval.ms`: giới hạn khoảng thời gian giữa những lần poll theo cơ chế Kafka consumer group.
- `session.timeout.ms`: cơ chế liveness của group membership.
- `request.timeout.ms`: timeout cho request của Kafka client.

Chúng bảo vệ những giai đoạn khác nhau. Tăng `session.timeout.ms` không phải cách trực tiếp chữa consumer task chưa được executor chạy.

## 4. Lắng nghe ConsumerFailedToStartEvent bằng @EventListener

Spring application events có thể được nhận bằng Spring `@EventListener` trong một bean do application context quản lý.

Ví dụ đơn giản:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerFailedToStartEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerStartupEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerStartupEvents.class);

    @EventListener
    public void onConsumerFailedToStart(
            ConsumerFailedToStartEvent event) {

        log.error(
                "Kafka consumer did not start within configured " +
                "timeout; source={}, timestamp={}",
                event.getSource(),
                event.getTimestamp());
    }
}
~~~

Trong ví dụ:

- Spring tự chuyển event đúng type đến method.
- `event.getSource()` là nguồn phát event theo Spring `ApplicationEvent`.
- `event.getTimestamp()` là thời điểm event được tạo.
- Handler chỉ log ngắn, tránh chặn startup lâu hơn.

Không cần tự gọi method xử lý event từ listener. `ConsumerFailedToStartEvent` được Spring Kafka công bố khi container gặp điều kiện tương ứng.

### 4.1. Đừng suy diễn metadata không có trong event

Không nên tự giả định event có đầy đủ Kafka client ID, topic, consumer group và exception cause giống một failure record. Consumer có thể chưa khởi động nên nhiều thông tin runtime còn chưa sẵn sàng.

Khi cần thêm ngữ cảnh, lấy từ:

- Cấu hình listener/container đã khai báo.
- `KafkaListenerEndpointRegistry`.
- Logs giai đoạn start.
- Task executor metrics và thread dumps.
- Cấu hình deployment (pod, instance, release version).

Không gắn offset hoặc record key không tồn tại vào báo cáo startup timeout.

## 5. Lắng nghe bằng ApplicationListener

Nếu dự án thích listener dạng interface, có thể khai báo:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ConsumerFailedToStartEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerStartFailureListener
        implements ApplicationListener<ConsumerFailedToStartEvent> {

    @Override
    public void onApplicationEvent(
            ConsumerFailedToStartEvent event) {
        startupHealthRecorder.recordFailure(
                "consumer_start_timeout",
                event.getTimestamp());
    }
}
~~~

`startupHealthRecorder` trong ví dụ tượng trưng cho service nội bộ do ứng dụng cung cấp. Nếu viết thành class thực tế, cần khai báo dependency qua constructor injection hoặc một implementation tương ứng.

Hai cách `@EventListener` và `ApplicationListener` đều phù hợp. Không cần đăng ký cả hai chỉ để ghi cùng một sự cố, tránh duplicate alert.

## 6. Cấu hình consumerStartTimeout

`consumerStartTimeout` là thuộc tính trên `ContainerProperties` dùng để quyết định khoảng thời gian container chờ consumer start. Giá trị mặc định thường được tài liệu Spring Kafka mô tả là **30 giây** ở những phiên bản có tính năng này. Với phiên bản cụ thể, nên kiểm tra API và default trong dependency đang chạy.

Ví dụ cấu hình qua factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    factory.getContainerProperties()
            .setConsumerStartTimeout(Duration.ofSeconds(45));

    return factory;
}
~~~

Ví dụ dùng API `ContainerProperties.setConsumerStartTimeout(Duration)` trong các phiên bản Spring Kafka hỗ trợ kiểu `Duration`. Với phiên bản khác, tham chiếu Javadoc chính xác trước khi áp dụng.

### 6.1. Đừng tăng timeout để che thiếu thread

Tăng 30 giây lên 120 giây có thể hữu ích nếu application có startup thật sự chậm nhưng hợp lệ. Nhưng nếu executor chỉ có hai threads cho sáu long-lived consumer tasks, đợi thêm vài phút có thể vẫn không khởi động được những consumer còn lại.

Thứ tự xử lý hợp lý:

1. Xác định consumer start timeout đã bị vượt.
2. Kiểm tra executor đang dùng.
3. Xác định số thread cần thiết cho tất cả container chia sẻ executor.
4. Kiểm tra queue và những tác vụ chiếm thread.
5. Sửa cấu hình executor/concurrency trước khi nới timeout.

### 6.2. Timeout không phải giới hạn retry nghiệp vụ

`consumerStartTimeout` không quyết định số lần `@KafkaListener` xử lý lại record và không điều khiển `DefaultErrorHandler`. Đừng nhầm nó với `FixedBackOff`, `@RetryableTopic` hay thời hạn publish DLT.

## 7. Nguyên nhân điển hình: task executor thiếu threads

Kafka consumer task thường chạy dài hạn để liên tục poll records. Nếu listener container được giao một executor có quá ít worker threads, các consumer tasks có thể chờ trong queue mà không bao giờ có thread chạy.

Giả sử hai listener cùng dùng executor:

~~~text
ordersListener:
  concurrency = 3  -> cần 3 consumer threads

paymentsListener:
  concurrency = 2  -> cần 2 consumer threads

Executor shared:
  maxPoolSize = 3

Các consumer tasks cần chạy đồng thời: 5
Thread tối đa: 3
Phần còn lại chờ -> có thể quá consumerStartTimeout
~~~

Đây chỉ là mô hình nhu cầu threads của container; một deployment thật còn có scheduler, executor khác và những thread phụ trợ. Không tính capacity bằng số pod nhân concurrency rồi so trực tiếp với max threads **trong một pod**: cần tính riêng từng executor trên từng JVM.

### 7.1. Vì sao queue lớn có thể gây hại?

Với một số `ThreadPoolExecutor` hoặc `ThreadPoolTaskExecutor`, nếu core pool đã đủ, task có thể được đưa vào queue trước khi executor tăng thread tới max pool. Vì consumer tasks chạy lâu, queue không được giải phóng nhanh.

Ví dụ:

~~~text
corePoolSize = 1
maxPoolSize  = 10
queueCapacity = 100

Consumer task A chiếm core thread lâu dài.
Consumer tasks B, C, D vào queue.
Không tạo thêm thread vì queue còn chỗ.

Kết quả: các consumer B/C/D không start đúng hạn.
~~~

Nếu mỗi consumer cần thread lâu dài, hãy thiết kế pool theo số consumers đồng thời và hiểu rõ cách executor cấp phát threads.

## 8. Ví dụ executor phù hợp với concurrency

Ví dụ tạo executor riêng cho một listener có `concurrency = 4`:

~~~java
@Bean("ordersConsumerExecutor")
ThreadPoolTaskExecutor ordersConsumerExecutor() {
    var executor = new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("orders-kafka-");

    return executor;
}
~~~

Gắn executor vào listener factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        @Qualifier("ordersConsumerExecutor")
        ThreadPoolTaskExecutor ordersConsumerExecutor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    factory.getContainerProperties()
            .setListenerTaskExecutor(ordersConsumerExecutor);
    factory.getContainerProperties()
            .setConsumerStartTimeout(Duration.ofSeconds(45));

    return factory;
}
~~~

Các phương thức setter có thể khác trong những phiên bản Spring Kafka cũ. Ví dụ dùng `setListenerTaskExecutor(...)` và `setConsumerStartTimeout(...)` trong các phiên bản cung cấp những API này. Trong production, cần kiểm tra executor có được Spring khởi tạo và shutdown đúng lifecycle.

### 8.1. Không phải cứ thread pool lớn hơn là tốt hơn

Consumer concurrency phải phù hợp:

- Số partition của topic.
- Tổng số Kafka containers trên JVM.
- CPU và memory.
- Khả năng xử lý của database/downstream.
- Giới hạn connections của Kafka brokers và downstream.

Một topic có ba partitions sẽ không tăng throughput tuyến tính chỉ nhờ mười consumer threads trong cùng group; nhiều consumer có thể không được assign partition.

Vì vậy, xử lý startup timeout không đồng nghĩa tăng `concurrency` không giới hạn. Cần cấp đủ threads **cho concurrency có ích**, đồng thời quản lý CPU/downstream capacity.

### 8.2. Shared executor phải tính tổng nhu cầu

Nếu cùng executor phục vụ ba listener containers lần lượt có concurrency 2, 4 và 3, nhu cầu thread dài hạn có thể là tổng 9 khi cả ba đang chạy. Dùng một pool chỉ có 4 thread sẽ gây chờ ngay cả khi từng listener factory nhìn riêng có vẻ đúng.

Với hệ thống nhiều listener, dành executor riêng hoặc lập capacity plan rõ cho shared executor; tránh dùng chung một pool nhỏ còn phục vụ HTTP request hay batch background tasks.

## 9. Cần phân biệt consumer thread và những loại thread khác

Spring Boot và ứng dụng có thể có nhiều thread pools:

| Pool / thread | Thường phục vụ | Có liên quan startup không? |
|---|---|---|
| Kafka listener task executor | Chạy consumer loop của container | Trực tiếp |
| Task scheduler | Chạy job định kỳ, backpressure coordinator | Gián tiếp, không thay consumer loop |
| HTTP server worker | Xử lý request | Có thể gây tranh tài nguyên nếu share executor bất hợp lý |
| Async executor | `@Async` hoặc background jobs | Có thể gây thiếu thread nếu dùng chung |
| Kafka producer network thread | I/O producer | Không phải listener task executor |
| Kafka consumer heartbeat/network internals | Các hoạt động nội bộ của Kafka client | Không thay thế consumer polling thread |

Nếu listener consumer task chưa start, tăng HTTP worker threads thường không giúp gì, trừ khi cả hai thực sự sử dụng chung executor hoặc cùng thiếu tài nguyên JVM.

## 10. ConsumerFailedToStartEvent có phải luôn do executor?

**Không.** Executor thiếu thread là một nguyên nhân quan trọng và thường được nhắc tới trong tài liệu Spring Kafka. Tuy nhiên, event cho biết consumer không start trong khoảng chờ, chứ không chứng minh nguyên nhân duy nhất là thread pool.

Các nhóm nguyên nhân khác nên xem xét:

- Startup bị block bởi custom lifecycle callback.
- Một công đoạn khởi tạo dependency hoặc deserializer lâu bất thường.
- Lỗi cấu hình consumer factory.
- Áp lực CPU, GC pause dài, memory pressure.
- Deadlock hoặc thread starvation do shared application resources.
- Deployment shutdown hoặc lifecycle bị thay đổi trong khi start.

Với lỗi broker unreachable, consumer có thể vẫn start và sau đó liên tục gặp lỗi kết nối trong quá trình poll/metadata fetch. Vì vậy, **không thể kết luận broker unreachable chắc chắn phát `ConsumerFailedToStartEvent`**.

### 10.1. Lỗi auth hoặc deserialization có thể có event khác

Một consumer đã start và gặp authentication/authorization problem khi poll có thể báo lỗi theo đường consumer runtime và event dừng/lỗi khác. Lỗi deserialize record trong `poll()` cũng khác startup timeout.

Hãy đọc exception thực tế, client logs và event timeline trước khi quy trách nhiệm cho một cấu hình Kafka broker.

## 11. Spring application event delivery

Theo cơ chế Spring application events thông thường, các listener có thể được gọi đồng bộ trên thread publish event, trừ khi ứng dụng cấu hình event multicaster bất đồng bộ. Điều này quan trọng vì code trong event listener có thể ảnh hưởng thời gian phản hồi của container hoặc lifecycle.

### 11.1. Event handler nên nhẹ

Nên làm:

- Ghi structured log.
- Tăng counter có tag cố định.
- Lưu last-start-failure timestamp vào một trạng thái thread-safe nhẹ.
- Gửi tín hiệu cho readiness/health aggregator.

Tránh:

- Gọi HTTP API lâu trong event callback.
- Sleep hoặc retry trực tiếp từ event handler.
- Truy vấn database nặng để “xác nhận lỗi”.
- Ngay lập tức stop/start liên tiếp chính container phát event.
- Lấy KafkaConsumer từ event rồi gọi consumer operations trên thread khác.

Nếu muốn tạo ticket/notification, nên chuyển thông tin tối thiểu sang một pipeline giám sát có timeout và bounded queue.

### 11.2. Không nên thay đổi consumer lifecycle một cách đệ quy

Ví dụ không nên:

~~~java
@EventListener
public void onConsumerFailedToStart(
        ConsumerFailedToStartEvent event) {
    // Không nên start/stop/restart lặp trong callback này
    // khi chưa xác định nguyên nhân và trạng thái lifecycle.
}
~~~

Nếu nguyên nhân là pool hết threads, restart liên tục có thể tạo thêm tasks bị xếp hàng hoặc gián đoạn những consumer đang hoạt động. Hãy dùng một coordinator bên ngoài event callback với rate limit và điều kiện phục hồi rõ ràng.

## 12. Ghi metric và cảnh báo từ event

Không phải mọi hệ thống quan sát đều có metric mặc định riêng tên “consumer failed to start”. Có thể tự instrument:

~~~java
@Component
public class KafkaStartupMetrics {

    private final Counter consumerStartTimeouts;

    public KafkaStartupMetrics(MeterRegistry meterRegistry) {
        this.consumerStartTimeouts = Counter.builder(
                "app.kafka.consumer.start.timeout.total")
                .description(
                        "Number of Kafka consumer start timeouts")
                .register(meterRegistry);
    }

    @EventListener
    public void onStartTimeout(
            ConsumerFailedToStartEvent event) {
        consumerStartTimeouts.increment();
    }
}
~~~

Ví dụ dùng Micrometer; dự án phải có dependency và imports tương ứng. Counter có tên do ứng dụng lựa chọn, không phải cam kết Spring Kafka xuất metric đó mặc định.

### 12.1. Những metric nên kết hợp

| Metric | Mục đích |
|---|---|
| `consumer_start_timeout_total` | Đếm sự kiện không start đúng hạn |
| Expected consumer count | Số consumer dự kiến theo cấu hình |
| Started/running consumer count | Số consumer thực sự bắt đầu |
| Executor active threads | Pool đã dùng hết capacity hay chưa |
| Executor pool size/max size | Ngưỡng threads hiện tại |
| Executor queue depth | Consumer tasks có đang xếp hàng không |
| Container running state | Container có được start không |
| Consumer assignment count | Consumer có được assign partitions không |
| Consumer lag/oldest record age | Tác động lên dữ liệu |
| JVM CPU/GC/heap | Tài nguyên có đang làm startup chậm không |

Một event đơn lẻ giúp cảnh báo nhanh, nhưng **sức khỏe consumer** nên được xác minh bằng cả start state, partition assignment và tiến độ xử lý dữ liệu.

### 12.2. Metric tags không nên quá chi tiết

Có thể gắn nhãn hữu hạn như `application`, `environment`, `listenerId` và `instance` khi cardinality được kiểm soát. Không gắn exception message nguyên văn, event timestamp, offset, record key hoặc event id vào metric tag.

Một số startup errors không có record context; việc cố tạo offset hoặc message ID giả sẽ làm dashboard gây hiểu nhầm.

## 13. Tạo trạng thái readiness dựa trên event và consumer state

Một ứng dụng có thể đã khởi động HTTP server nhưng Kafka listener quan trọng chưa sẵn sàng. Nếu Kafka consumption là chức năng bắt buộc, có thể có readiness policy:

- Chỉ Ready khi các listener quan trọng đang running.
- Consumer start timeout phải được đánh dấu lỗi.
- Có partition assignment phù hợp hoặc trạng thái connected đủ tin cậy.
- Cho phép thời gian khởi động bình thường trước khi đánh giá thất bại.
- Phân biệt listener bắt buộc với listener optional.

### 13.1. Không đánh giá chỉ từ isRunning()

`container.isRunning()` phản ánh lifecycle của container nhưng không nhất thiết chứng minh mọi consumer con đã start và đang xử lý thành công. Khi `concurrency > 1`, cần nhìn startup events và trạng thái từng child consumer.

### 13.2. Không đánh giá chỉ từ consumer lag

Lag = 0 có thể do không có record hoặc do chưa được assign theo trạng thái nào đó; lag cao có thể là hậu quả hợp lệ của planned pause. Dùng lag cùng event, assignment, processing rate và container health.

### 13.3. Tránh restart loop do readiness nhầm với liveness

Kubernetes thường dùng readiness để quyết định nhận traffic, còn liveness có thể khiến pod restart. Nếu đưa event startup timeout vào liveness quá khắt khe, pod có thể restart liên tục khi executor thiếu thread.

Hãy dùng readiness để biểu diễn tạm thời chưa sẵn sàng, alert để gọi operator, và chỉ quyết định restart khi có bằng chứng restart là hành động khôi phục có ích. Với một Kafka-only worker không có HTTP traffic, cần thiết kế probe theo tính chất ứng dụng thay vì sao chép liveness của web service.

## 14. Concurrency và partition count

Khi đặt:

~~~java
factory.setConcurrency(6);
~~~

container có thể cố chạy tới sáu consumer con cho một listener. Điều này không có nghĩa topic có đủ sáu partition để consumer nào cũng có assignment.

Ví dụ:

~~~text
Topic orders.events có 3 partitions.

Container concurrency = 6.

Một số consumer có thể không được assign partition
vì có nhiều consumers hơn partitions.

Nhưng startup vẫn cần quản lý consumer threads theo
concurrency thực tế mà container tạo.
~~~

Không tăng concurrency chỉ để làm consumer “khởi động nhanh hơn”. Nếu thiếu executor capacity, tăng concurrency có thể làm số consumer chưa start còn nhiều hơn.

### 14.1. Tính capacity theo tất cả listener containers

Ví dụ một JVM có:

| Listener | Concurrency | Nhu cầu threads dài hạn |
|---|---:|---:|
| Orders | 4 | Tối đa 4 |
| Billing | 3 | Tối đa 3 |
| Notifications | 2 | Tối đa 2 |
| Tổng | 9 | Tối đa 9 |

Nếu ba listener dùng chung một executor có tối đa bốn threads, ít nhất một phần consumer tasks khó có thể start khi tất cả container chạy cùng lúc.

Nên dành capacity cho các consumer tasks và dự phòng cho shutdown/restart/rollout phù hợp; đừng chia pool nhỏ với các background tasks có thể block lâu.

## 15. Một ví dụ lỗi do shared ThreadPoolTaskExecutor

Giả sử ứng dụng cấu hình:

~~~java
@Bean("sharedExecutor")
ThreadPoolTaskExecutor sharedExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(100);
    return executor;
}
~~~

Hai Kafka listener containers cùng có concurrency 2 và dùng executor này:

~~~text
orders listener    -> consumer task 1, 2
billing listener   -> consumer task 3, 4

Pool có 2 threads.
Tasks 1, 2 chạy lâu dài.
Tasks 3, 4 nằm trong queue.
Billing consumer không start kịp.
~~~

Nếu `consumerStartTimeout` ngắn hơn thời gian task chờ, có thể phát `ConsumerFailedToStartEvent`.

Giải pháp tốt hơn là cấp bốn threads hoặc sử dụng executor riêng cho từng listener. Chỉ tăng queue capacity từ 100 lên 1000 không giúp consumer task đang chờ được chạy.

## 16. Không nhầm ConsumerFailedToStartEvent với mất broker

Một consumer có thể tạo client và khởi động polling thread dù Kafka broker chưa thể kết nối ngay. Kafka client sau đó retry metadata, network requests hoặc báo authentication errors tùy trường hợp. Do đó:

- Startup event không phải “broker health check” trực tiếp.
- Không có event chưa chắc broker sẵn sàng.
- Có event chưa chắc broker hỏng.

Khi điều tra broker-related symptoms, kiểm tra thêm:

1. Bootstrap servers và DNS.
2. Network connectivity tới broker advertised listeners.
3. SASL/SSL credentials.
4. ACL của consumer group và topics.
5. Kafka client logs về metadata, authentication, coordinator.
6. Partition assignments và group rebalance.

Nhưng hãy bắt đầu từ **executor/lifecycle startup state** vì đó là ngữ cảnh trực tiếp của `ConsumerFailedToStartEvent`.

## 17. Runbook: nhận ConsumerFailedToStartEvent sau deploy

Một quy trình điều tra nên có thứ tự:

1. Ghi thời điểm event và pod/instance phát event.
2. Xác định listener/container bị ảnh hưởng, theo logs và registry.
3. Xác nhận có thay đổi `concurrency`, executor config hoặc number of listeners.
4. Kiểm tra executor thread pool: active count, max size, queue depth.
5. Xem thread dump để phát hiện consumer tasks chiếm thread lâu hoặc task bị chờ.
6. Kiểm tra CPU/heap/GC pause và resource limits của pod.
7. Xem các `ConsumerStartedEvent` khác có được phát trong cùng đợt startup không.
8. Đối chiếu Kafka group membership và partition assignment.
9. Sửa capacity hoặc cấu hình sai trước khi thử restart.
10. Sau khôi phục, xác minh listener nhận record và lag giảm.

Không chỉ nhìn một dòng `ConsumerFailedToStartEvent` rồi restart toàn cluster. Nếu các pods dùng chung executor config thiếu threads, restart chỉ lặp lại sự cố.

## 18. Runbook: ứng dụng Ready nhưng không tiêu thụ Kafka

1. Kiểm tra listener registry có container đúng ID không.
2. Kiểm tra container đã start hay còn chờ lifecycle.
3. Xác nhận có `ConsumerFailedToStartEvent` hoặc startup timeout log không.
4. Xem executor có đủ long-lived consumer threads không.
5. Xác nhận `@KafkaListener` dùng đúng factory và concurrency.
6. Kiểm tra group assignment và topic partition.
7. Kiểm tra listener có bị pause không.
8. Kiểm tra exception tại startup hoặc runtime.
9. Điều chỉnh readiness policy nếu trạng thái Ready hiện không phản ánh consumer critical.

Không coi listener im lặng là startup failure nếu topic không có record mới và lag bằng 0. Cần chứng minh consumer thực sự không start hoặc không poll.

## 19. Runbook: chỉ một số consumer con start

Với concurrency lớn hơn 1, có thể thấy một số consumer đã chạy và số còn lại không start.

1. Kiểm tra container cha và các child consumers.
2. So sánh số `ConsumerStartedEvent` với concurrency mong đợi.
3. Xem executor active threads và queue.
4. Kiểm tra có task khác dùng chung executor.
5. Kiểm tra thread names và thread dump.
6. Xác minh số partition/topic không bị hiểu nhầm thành số thread thực tế.
7. Sau khi cấp capacity, kiểm tra toàn bộ consumer con start và assignments ổn định.

Nếu executor pool có đủ threads nhưng vẫn có consumer chưa start, điều tra tiếp các bước khởi tạo phía consumer factory và lifecycle thay vì chỉ tăng pool.

## 20. Runbook: event xảy ra chỉ khi rolling deployment

Rolling deployment có thể làm tăng tải CPU/GC trong thời gian một pod mới khởi động, hoặc có nhiều listener containers được start đồng thời. Một số vấn đề chỉ bộc lộ dưới điều kiện này:

- Thread pool khởi tạo quá muộn hoặc có tác vụ batch chiếm hết threads.
- Cấu hình concurrency tăng ở release mới.
- Startup dependency chậm khi nhiều pods start cùng lúc.
- Network/DNS contention.
- Pod CPU limit quá thấp khiến thread scheduling chậm.

Cần:

1. So sánh config cũ/mới.
2. Kiểm tra thread dump, CPU throttling và startup timings của pod mới.
3. Tách consumer executor khỏi các startup tasks chạy dài.
4. Giới hạn số pods rollout đồng thời nếu cần.
5. Theo dõi event sau lần rollout tiếp theo.

Đừng chỉ tăng `consumerStartTimeout` để làm dashboard hết alert nếu thời gian start thực tế đang vi phạm SLO và consumer lag tăng.

## 21. Phục hồi: restart có phải lúc nào cũng đúng?

**Không.** Tùy nguyên nhân, chiến lược khôi phục khác nhau:

| Nguyên nhân | Phương án ưu tiên |
|---|---|
| Executor hết threads | Tăng capacity/tách executor, giảm concurrency không cần thiết |
| Consumer task bị queue bởi task nền | Cấp executor riêng, sửa thread pool queue policy |
| Startup chậm hợp lệ | Tối ưu startup, nới timeout có căn cứ |
| CPU/GC pressure | Điều chỉnh resource limits, tối ưu allocation |
| Cấu hình consumer sai | Sửa cấu hình, triển khai lại |
| Container đã dừng | Đánh giá lỗi, dùng lifecycle start đúng quy trình |
| Lỗi broker/auth sau khi start | Xử lý network/credentials, không quy nhầm startup timeout |

Nếu cần tự restart, hãy đặt cooldown, limit số lần, distributed coordination và một điều kiện hồi phục rõ. Tự gọi `stop()`/`start()` trong chính event callback có thể gây xung đột lifecycle.

### 21.1. Resume không sửa startup failure

`resume()` chỉ xử lý container đang chạy nhưng bị pause. Nếu consumer chưa start hoặc container đã stop, gọi resume không phải lệnh khởi động. Cần phân biệt:

- `start()`: mở vòng đời container.
- `pause()`: yêu cầu tạm ngừng record delivery trong container chạy.
- `resume()`: hủy yêu cầu pause.
- `stop()`: dừng container.

Đừng dùng resume như phản ứng mặc định khi gặp `ConsumerFailedToStartEvent`.

## 22. Tương tác với KafkaListenerEndpointRegistry

Registry hữu ích để quản lý một listener đã khai báo `id`:

~~~java
@KafkaListener(
        id = "ordersConsumer",
        topics = "orders.events",
        groupId = "orders-workers",
        containerFactory = "ordersListenerContainerFactory")
public void consume(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

Trong management service:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersConsumer");

if (container == null) {
    log.error("Listener container not registered");
}
else {
    log.info(
            "Listener container lifecycle running={}",
            container.isRunning());
}
~~~

`isRunning()` là lifecycle state ở cấp container; nó không phải bằng chứng mọi child consumer thread và assignment đã sẵn sàng. Khi điều tra start failure, kết hợp thêm event timeline và executor metrics.

### 22.1. Sự kiện xảy ra trước registry query?

Startup event có thể phát trong giai đoạn Spring context đang khởi động. Một listener event callback không nên phụ thuộc vào một management component chưa sẵn sàng hoặc mong tất cả container đều có final assignment. Nếu cần kiểm tra sâu, lưu một tín hiệu nhẹ và cho health reconciler chạy sau khi context sẵn sàng.

## 23. Test ConsumerFailedToStartEvent

Unit test có thể chứng minh `@EventListener` xử lý event, nhưng muốn xác nhận container thực sự publish event khi startup timeout cần integration test với listener container và executor có cấu hình chủ động.

### 23.1. Kịch bản executor starvation

1. Tạo Kafka listener container với `concurrency = 2`.
2. Cấp executor chỉ có một worker thread cho hai consumer tasks lâu dài.
3. Cấu hình `consumerStartTimeout` ngắn đủ cho integration test.
4. Khởi động container.
5. Gắn event listener hoặc event collector.
6. Xác nhận consumer còn lại không đạt start milestone trong timeout và event được phát theo phiên bản đang dùng.
7. Dừng container/test executor đúng lifecycle sau test.

Trong production, không tạo cố ý thread starvation; tình huống này chỉ phục vụ kiểm thử.

### 23.2. Kịch bản đủ capacity

1. Cấp executor đủ threads cho concurrency.
2. Start listener container.
3. Quan sát consumer startup events.
4. Xác nhận không phát startup timeout event trong trường hợp bình thường.
5. Gửi Kafka record và xác nhận listener xử lý được.

### 23.3. Kịch bản event handler chỉ ghi metric

1. Gửi event test đến Spring ApplicationContext hoặc event publisher của test.
2. Xác nhận counter/log/health state được cập nhật.
3. Xác nhận callback không gọi stop/start một cách đệ quy.
4. Xác nhận không có duplicate alerts khi ứng dụng có nhiều event subscribers.

### 23.4. Không nhầm với kiểm thử broker offline

Tắt broker có thể gây nhiều loại network/client errors, nhưng không bảo đảm tạo `ConsumerFailedToStartEvent`; vì consumer thread vẫn có thể start đúng hạn. Muốn test **event này**, hãy thao tác đúng điều kiện startup timeout thay vì chỉ làm Kafka broker unreachable.

## 24. Kiểm thử trong môi trường nhiều listener và nhiều pods

Khi production có nhiều Kafka listener containers, cần test capacity và điều phối:

1. Tổng concurrency trên một JVM.
2. Số threads của shared/dedicated executors.
3. Topic partition counts.
4. CPU/memory limits mỗi pod.
5. Số pods rolling deployment đồng thời.
6. Event collector và metric tags có thể phân biệt listener/instance.
7. Readiness không báo Ready trước khi các critical consumers start.

Ví dụ nếu mỗi pod có 3 listener với concurrency 2, 3 và 4, tổng consumer tasks có thể đạt 9 trên pod đó. Executor chỉ có 4 threads có thể hoạt động tốt khi mới bật một listener nhưng thất bại khi cả ba start đồng thời.

## 25. Những sai lầm thường gặp

**Coi ConsumerFailedToStartEvent là lỗi xử lý record.** Event thuộc giai đoạn startup consumer, không chứa một record lỗi để retry/DLT.

**Quy ngay cho Kafka broker.** Timeout start có thể do executor thiếu threads; broker mất kết nối có thể xảy ra sau khi consumer đã start.

**Chỉ tăng consumerStartTimeout.** Nếu tasks nằm trong queue vô hạn, chờ lâu hơn không giải quyết nguyên nhân.

**Chỉ nhìn maxPoolSize của ThreadPoolTaskExecutor.** Core size và queue policy có thể khiến pool không tạo thêm threads tới max size.

**Tăng concurrency để consumer chạy nhanh.** Có thể làm thiếu threads trầm trọng hơn và không tăng throughput khi partitions ít.

**Dùng chung executor nhỏ cho nhiều long-lived consumers.** Các tasks sau bị queue và không bao giờ chạy đúng hạn.

**Gọi restart ngay trong event callback.** Có thể tạo vòng lặp lifecycle và tải phụ.

**Không phân biệt container running với consumer ready.** Lifecycle state không phản ánh mọi child consumer.

**Dùng resume để sửa start failure.** Resume chỉ hủy pause của container đang chạy.

**Không có alert/readiness policy.** Ứng dụng có thể báo Ready dù consumer quan trọng không khởi động.

**Dùng broker-offline test làm bằng chứng event hoạt động.** Đây là hai lớp failure khác nhau.

**Đưa dữ liệu động vào metric tags.** Startup metrics cần cardinality thấp, không dùng exception message hay event timestamp làm tag.

## 26. Checklist triển khai

### Cấu hình container

- [ ] Đã đặt `id` rõ ràng cho các `@KafkaListener` quan trọng.
- [ ] `concurrency` phù hợp partition count và năng lực xử lý.
- [ ] Executor có đủ threads cho tất cả long-lived consumer tasks dùng chung.
- [ ] Hiểu rõ core/max pool size và queue capacity.
- [ ] `consumerStartTimeout` phản ánh ngân sách startup thực tế.
- [ ] Không dùng startup timeout để thay thế Kafka network/poll timeouts.

### Xử lý event

- [ ] Có `@EventListener` hoặc `ApplicationListener<ConsumerFailedToStartEvent>`.
- [ ] Handler log và cập nhật metrics ngắn, không block lâu.
- [ ] Không tự restart lặp ngay trong callback.
- [ ] Có thông tin listener, instance và release để điều tra.
- [ ] Đã phân biệt startup failure với ConsumerStopped/NonResponsive/Idle events.

### Production observability

- [ ] Có metric start timeout, executor threads/queue và consumer running counts.
- [ ] Có alert khi critical consumer không start.
- [ ] Readiness phản ánh consumers quan trọng nếu nghiệp vụ yêu cầu.
- [ ] Không dùng liveness restart loop thay cho sửa thiếu executor capacity.
- [ ] Có runbook điều tra rolling deploy và thread starvation.

### Kiểm thử

- [ ] Integration test chủ động tạo executor starvation và quan sát event.
- [ ] Test đủ threads và consumer startup bình thường.
- [ ] Test nhiều listener dùng chung executor.
- [ ] Test event handler không gây restart loop.
- [ ] Test recovery thực tế bằng việc listener xử lý records và lag giảm.

## Kết luận

`ConsumerFailedToStartEvent` là tín hiệu của Spring Kafka cho biết **consumer không bắt đầu chạy trong khoảng chờ `consumerStartTimeout`**. Nó thường chỉ ra vấn đề capacity của task executor hoặc sự trì hoãn ở startup, không phải bằng chứng trực tiếp Kafka broker hỏng và không liên quan tới một record đang retry. Để xử lý đúng, hãy quan sát `ConsumerStartingEvent`/`ConsumerStartedEvent`, container lifecycle, executor active threads và task queue, sau đó đối chiếu với `concurrency` của toàn bộ listeners trên mỗi JVM.

Một hệ thống đáng tin cậy nên ghi log và đo metric ngay khi event xảy ra, có readiness policy cho các consumer bắt buộc, nhưng không restart vô hạn trong chính event callback. Cần cấp đúng threads, thiết kế timeout phù hợp, kiểm tra startup bằng integration test và xác nhận consumer thực sự nhận record sau phục hồi. Như vậy, một container được yêu cầu start nhưng không có consumer chạy sẽ được phát hiện sớm trước khi biến thành backlog và vi phạm SLA của pipeline.
