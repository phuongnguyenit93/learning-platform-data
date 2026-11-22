# ConsumerStartingEvent

Trong Spring Kafka, một listener không bắt đầu nhận record ngay lập tức tại thời điểm ứng dụng tạo bean hoặc gọi `start()` trên listener container. Container còn cần khởi tạo tác vụ consumer, đưa tác vụ vào executor, bắt đầu consumer thread và tiến vào vòng lặp `poll()`. Để ứng dụng quan sát các mốc này, Spring Kafka phát **application events**. `ConsumerStartingEvent` là tín hiệu sớm cho biết **consumer thread đã bắt đầu khởi tạo, trước khi consumer bắt đầu polling**.

Event này hữu ích khi vận hành nhiều listener, nhiều partition và nhiều replica: nó giúp xác định consumer thread đã được executor chạy hay chưa, liên kết việc khởi động với một listener container cụ thể và hỗ trợ chẩn đoán trường hợp consumer không start. Nhưng nó **không phải bằng chứng listener đã nhận partition, đã poll thành công, đã xử lý record hay đã sẵn sàng phục vụ nghiệp vụ**.

Bài học tập trung vào cách hiểu thời điểm phát event, cách lắng nghe bằng Spring `@EventListener`, phân biệt với các application events liền kề, kết hợp với timeout và task executor, và xây quan sát startup phù hợp với Spring Kafka Reliability Operations.

## 1. ConsumerStartingEvent nằm ở đâu trong vòng đời consumer?

Với `@KafkaListener`, Spring tạo listener container để quản lý Kafka consumer và vòng đời xử lý record. Mỗi consumer cần một task/thread phục vụ `poll()` cùng việc dispatch record tới listener.

Một trình tự đơn giản hóa:

~~~text
Spring application context khởi tạo
             |
             v
Kafka listener container được tạo
             |
             v
Container nhận lệnh start()
             |
             v
Task consumer được executor thực thi
             |
             v
ConsumerStartingEvent
    (consumer thread bắt đầu, trước polling)
             |
             v
ConsumerStartedEvent
    (consumer sắp bắt đầu poll)
             |
             v
Kafka consumer poll(), join group, assignment...
             |
             v
Nhận records / gọi @KafkaListener
             |
             v
Khi shutdown: các sự kiện stopping/stopped
~~~

Các bước trên là mô hình để hiểu lifecycle, không phải lời hứa rằng mọi phiên bản Spring Kafka luôn có cùng số lần gọi nội bộ hoặc cùng chuỗi thao tác chi tiết. Đặc biệt, **việc có `ConsumerStartingEvent` không đảm bảo ngay sau đó consumer sẽ poll thành công**: authentication, authorization, network, broker availability hoặc lỗi khởi tạo có thể xảy ra ở các bước tiếp theo.

Theo tài liệu Spring Kafka, event được phát **khi consumer thread mới được khởi động, trước khi nó bắt đầu poll**. Do đó đây là mốc thích hợp để quan sát **thread startup**, không phải mốc business readiness.

## 2. ConsumerStartingEvent là một Spring application event

Class của event:

~~~java
org.springframework.kafka.event.ConsumerStartingEvent
~~~

Đây là một lớp kế thừa `KafkaEvent` và tham gia cơ chế `ApplicationEvent` của Spring. Spring Kafka listener container publish event vào application context; các bean có thể lắng nghe thông qua `@EventListener` hoặc `ApplicationListener<ConsumerStartingEvent>`.

Những thành phần cần phân biệt:

| Thành phần | Vai trò |
|---|---|
| `@KafkaListener` | Định nghĩa phương thức xử lý record |
| `MessageListenerContainer` | Quản lý consumer thread, poll và xử lý listener |
| `KafkaListenerEndpointRegistry` | Giữ references tới containers tạo bởi `@KafkaListener` |
| `ConsumerStartingEvent` | Báo hiệu thread của consumer bắt đầu khởi tạo |
| `ConsumerStartedEvent` | Báo hiệu consumer sắp bắt đầu polling |
| `ConsumerFailedToStartEvent` | Báo timeout khi chưa quan sát `ConsumerStartingEvent` theo chính sách startup |
| `ConsumerStoppedEvent` | Báo consumer đã dừng; có thông tin reason ở các phiên bản hỗ trợ |
| `ContainerStoppedEvent` | Báo container đã dừng |

`ConsumerStartingEvent` được Spring Kafka đưa vào từ nhánh phiên bản 2.3. API cụ thể cần được đối chiếu với dependency `spring-kafka` của ứng dụng; không nên dựa vào tài liệu của bản mới nếu codebase dùng bản cũ hơn.

## 3. Những thông tin có thể lấy từ event

`ConsumerStartingEvent` cung cấp hai tham chiếu container quan trọng thông qua API kế thừa từ `KafkaEvent`:

- **`source`:** listener container trực tiếp phát event.
- **`container`:** listener container tương ứng với event; khi source là child container của concurrent container, giá trị này có thể là **parent container**.

Ví dụ:

~~~java
MessageListenerContainer source =
        event.getSource(MessageListenerContainer.class);

MessageListenerContainer container =
        event.getContainer(MessageListenerContainer.class);
~~~

Các phương thức generic `getSource(Class<T>)` và `getContainer(Class<T>)` giúp lấy reference đúng kiểu mà không tự cast `Object`. Tham số `MessageListenerContainer.class` phù hợp khi muốn làm việc với container ở cấp interface.

Các dữ liệu mang ý nghĩa:

| Dữ liệu | Cách sử dụng | Điều không nên suy luận |
|---|---|---|
| `event.getSource(...)` | Xác định child/container nào phát event | Không nhất thiết là parent quản lý toàn bộ group |
| `event.getContainer(...)` | Xác định container tương ứng, có thể là parent | Không phải một Kafka `Consumer` instance |
| `event.getTimestamp()` | Thời điểm Spring tạo event | Không phải thời điểm Kafka partition được assign |
| `source.getListenerId()` | Nhận diện listener/container trong logging, theo API hỗ trợ | Không phải business event ID |
| `source.isRunning()` | Quan sát trạng thái lifecycle tại thời điểm gọi | Không chứng minh consumer đã poll/đọc record |

Event này **không phải `ConsumerRecord`**. Vì nó phát trước polling, không có payload business event, Kafka key/value, original offset hay một partition được xử lý cụ thể. Nếu cần biết assignment, hãy quan sát consumer rebalance/assignment bằng API thích hợp thay vì kỳ vọng `ConsumerStartingEvent` chứa thông tin đó.

## 4. Lắng nghe bằng @EventListener

Một cách đơn giản để ghi nhận consumer startup:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerStartingEvent;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerStartupObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerStartupObserver.class);

    @EventListener
    public void onConsumerStarting(ConsumerStartingEvent event) {
        MessageListenerContainer source =
                event.getSource(MessageListenerContainer.class);

        MessageListenerContainer parent =
                event.getContainer(MessageListenerContainer.class);

        log.info(
            "Kafka consumer starting: source={} parent={} time={}",
            source.getListenerId(),
            parent.getListenerId(),
            event.getTimestamp()
        );
    }
}
~~~

Mỗi khi ứng dụng phát `ConsumerStartingEvent` và listener bean đã được đăng ký, method `onConsumerStarting` được gọi. `source` và `parent` có thể cùng một container nếu đây không phải child của một concurrent container.

Điều code trên **không** làm:

- Không thay đổi Kafka offset.
- Không can thiệp consumer poll.
- Không khởi động container khác.
- Không gửi hoặc nhận record.
- Không tự tạo health/readiness pass.
- Không tự retry lỗi startup.

Vai trò của nó là **quan sát trạng thái**. Ưu tiên giữ handler ngắn, không blocking để không làm chậm đường khởi động consumer.

## 5. Ví dụ listener được theo dõi

Đặt listener ID ổn định để quan sát:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
        id = "orders-consumer",
        topics = "orders",
        groupId = "order-projection")
    public void onOrder(OrderEvent event) {
        orderService.apply(event);
    }
}
~~~

Khi `orders-consumer` khởi động, Spring Kafka listener container tạo task consumer. Startup observer có thể log event tương ứng. Trên một ứng dụng có nhiều listener IDs, observer sẽ nhận events từ **mọi container trong application context**, không chỉ riêng `orders-consumer`.

Nếu cần giới hạn phạm vi, nên lọc theo ID của parent/source và tên instance như các phần sau.

## 6. Phân biệt với ConsumerStartedEvent

Tên hai event gần giống nhau nhưng mốc được biểu đạt khác nhau:

| Event | Khi nào xảy ra? | Cách hiểu đúng |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread bắt đầu khởi tạo, trước khi poll | Consumer task đã được chạy |
| `ConsumerStartedEvent` | Consumer sắp bắt đầu polling | Consumer đã tiến gần vòng poll |
| Consumer nhận assignment | Sau quá trình poll/join group/rebalance tương ứng | Có partition được gán theo group |
| Listener xử lý record đầu tiên | Khi poll có record và dispatch | Đã bắt đầu xử lý dữ liệu nghiệp vụ |

Cả `ConsumerStartingEvent` và `ConsumerStartedEvent` đều là **lifecycle events**, không phải phép xác nhận Kafka đang có record, business dependency đã khỏe hoặc consumer lag bằng 0.

Nếu ứng dụng khởi động khi topic rỗng, consumer vẫn có thể phát các event startup và poll bình thường mà không bao giờ nhận record. Vì vậy không được buộc “phải nhận record đầu tiên” mới coi thread startup hợp lệ; readiness của hệ thống cần xác định theo yêu cầu riêng.

## 7. ConsumerFailedToStartEvent có quan hệ gì?

Spring Kafka có `ConsumerFailedToStartEvent` để phát hiện tình huống **container đã yêu cầu khởi động consumer nhưng chưa nhận `ConsumerStartingEvent` trong khoảng `consumerStartTimeout`**.

Dòng thời gian khái niệm:

~~~text
Container start() gọi
        |
        +-- Executor nhận consumer task
        |      |
        |      +-- Thread được chạy kịp thời
        |             |
        |             v
        |       ConsumerStartingEvent
        |
        +-- Chưa thấy ConsumerStartingEvent
               trong thời gian consumerStartTimeout
               |
               v
          ConsumerFailedToStartEvent
          + log cảnh báo/lỗi startup
~~~

Một nguyên nhân thường gặp là **task executor không đủ thread** so với số listener containers và concurrency. Ví dụ executor có 2 threads nhưng cần chạy 5 consumer tasks lâu dài: một số task có thể chờ mãi trong queue, dẫn tới timeout.

Cần hiểu chiều suy luận:

- **Có `ConsumerStartingEvent`:** task đã được chạy tới mốc khởi tạo; không chứng minh consumer có thể poll thành công.
- **Có `ConsumerFailedToStartEvent`:** timeout khi chưa thấy starting event; cần điều tra executor/lifecycle. Không kết luận ngay broker Kafka đã down.
- **Không có cả hai event trong log:** có thể do event listener chưa đăng ký, container chưa được start, log filtering hoặc ứng dụng không nhận được sự kiện đúng context.

Đừng sử dụng `ConsumerFailedToStartEvent` để tự động tạo thêm executor threads vô giới hạn; cần tính concurrency và tài nguyên rõ ràng.

## 8. Cấu hình consumerStartTimeout

`consumerStartTimeout` thuộc `ContainerProperties`. Tùy phiên bản, thời gian mặc định thường được mô tả là **30 giây**; ứng dụng có thể đặt giá trị theo năng lực startup thực tế.

Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
           .setConsumerStartTimeout(Duration.ofSeconds(45));

    return factory;
}
~~~

Import bổ sung:

~~~java
import java.time.Duration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
~~~

Ý nghĩa:

- Container chờ consumer thread phát tín hiệu startup trong khoảng thời gian thiết lập.
- Nếu không quan sát được starting event, framework có thể phát `ConsumerFailedToStartEvent`.
- Việc tăng timeout giúp giảm cảnh báo giả nếu executor startup chậm trong thời gian ngắn, **nhưng không sửa được thread starvation** hoặc task executor luôn thiếu threads.
- `consumerStartTimeout` không phải Kafka broker request timeout, `max.poll.interval.ms`, `session.timeout.ms` hoặc thời hạn đợi partition assignment.

Nếu ứng dụng startup nhanh nhưng tiêu thụ không được vì broker/ACL/authorization, việc chỉ tăng consumer start timeout có thể không giải quyết được vấn đề đó.

## 9. Ví dụ chẩn đoán thread starvation

Giả sử ứng dụng có:

~~~text
Listener orders: concurrency = 3
Listener payments: concurrency = 2

Tổng consumer tasks dài hạn: tối đa 5
Executor chung: chỉ 2 threads hoạt động
~~~

Một Kafka consumer task thường tồn tại lâu, liên tục poll; nó không trả thread ngay sau vài milliseconds. Nếu cả năm tasks buộc chia sẻ một fixed executor chỉ có hai worker threads, ba tasks có thể nằm trong queue mà không được chạy.

Khi đó:

1. Một số child consumers có thể phát `ConsumerStartingEvent` bình thường.
2. Những tasks khác chưa có thread chạy nên chưa phát event.
3. Container chờ tới `consumerStartTimeout` và có thể phát `ConsumerFailedToStartEvent`.
4. Một số partitions không có consumer hoạt động đúng như cấu hình mong muốn.
5. Lag tăng ở những luồng không được phục vụ đầy đủ.

Cách xử lý:

- Kiểm tra số lượng child consumers cần chạy đồng thời.
- Xem loại `AsyncTaskExecutor`/listener task executor thực tế được factory/container cấu hình.
- Đảm bảo executor có đủ threads cho các tasks dài hạn, hoặc dùng executor riêng phù hợp.
- Kiểm tra queue backlog, rejected tasks, thread states và CPU/thread quotas.
- Kiểm tra một task có bị block do khởi tạo Kafka producer, deserializer, credential hay dependency khác không.
- Không chỉ tăng `consumerStartTimeout` để che nguyên nhân.

Đây là một nguyên nhân startup failure nằm **trong process**, không phải Kafka broker.

## 10. ConsumerStartingEvent với ConcurrentMessageListenerContainer

Khi dùng `@KafkaListener(concurrency = "3")` hoặc factory concurrency, Spring Kafka tạo một **concurrent container** quản lý nhiều child Kafka consumers.

~~~text
ConcurrentMessageListenerContainer: orders-consumer
          |
          +-- child-0 -> ConsumerStartingEvent
          |
          +-- child-1 -> ConsumerStartingEvent
          |
          +-- child-2 -> ConsumerStartingEvent
~~~

Trong tình huống này, `event.getSource(MessageListenerContainer.class)` có thể là child container phát event; `event.getContainer(MessageListenerContainer.class)` thường trỏ tới parent container quản lý cả nhóm child consumers.

Mỗi child thread có thể khởi động ở thời điểm khác nhau. Vì thế:

- Không đếm một event cho toàn bộ parent rồi kết luận tất cả child consumers đã chạy.
- Không nhầm listener concurrency với số partitions của topic.
- Nếu concurrency vượt số partitions, một số child consumers có thể không được assign partition dù vẫn khởi động.
- Việc tăng concurrency có thể tăng số events startup quan sát được.
- Sau restart/stop-start, events có thể xuất hiện lại; chúng không đại diện cho event business duy nhất.

Ví dụ listener:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders",
    groupId = "order-projection",
    concurrency = "3")
public void onOrder(OrderEvent event) {
    orderService.apply(event);
}
~~~

Khi vận hành nhiều replicas, mỗi replica có registry và child containers riêng. Không tổng hợp số starting events chỉ theo một listener ID mà bỏ qua instance ID nếu muốn phân tích số task thực sự trên toàn cluster.

## 11. Lọc event theo listener container mong muốn

Nếu ứng dụng có hàng chục listeners, nên lọc từ đầu để tránh log quá nhiều hoặc cập nhật metric sai.

~~~java
@Component
public class OrdersConsumerStartingObserver {

    private static final Logger log =
            LoggerFactory.getLogger(OrdersConsumerStartingObserver.class);

    @EventListener
    public void onStarting(ConsumerStartingEvent event) {
        MessageListenerContainer parent =
                event.getContainer(MessageListenerContainer.class);

        if (!"orders-consumer".equals(parent.getListenerId())) {
            return;
        }

        MessageListenerContainer source =
                event.getSource(MessageListenerContainer.class);

        log.info(
            "Orders consumer thread starting: source={} parent={}",
            source.getListenerId(),
            parent.getListenerId()
        );
    }
}
~~~

Tùy cách đặt tên parent/child và cơ chế tạo container của phiên bản, cần xác định listener ID trả về là gì. Vì `source` có thể là child, so sánh ID của `source` với `orders-consumer` có thể không khớp, ngay cả khi event thuộc listener gốc đó.

Không dùng phần hậu tố child ID làm định danh business cố định. Hậu tố hoặc mapping giữa task và partition có thể thay đổi khi concurrency/rebalance/restart.

## 12. Sử dụng ApplicationListener thay @EventListener

Ngoài annotation, có thể dùng interface `ApplicationListener` để nhận đúng loại event:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ConsumerStartingEvent;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class ConsumerStartAuditListener
        implements ApplicationListener<ConsumerStartingEvent> {

    @Override
    public void onApplicationEvent(ConsumerStartingEvent event) {
        MessageListenerContainer source =
                event.getSource(MessageListenerContainer.class);

        auditLogger.recordConsumerThreadStarting(
                source.getListenerId(),
                event.getTimestamp()
        );
    }
}
~~~

`auditLogger` là service ví dụ do ứng dụng cung cấp. Nếu audit ghi qua network/database, hãy cân nhắc đẩy thông tin tối thiểu tới hàng đợi nội bộ có giới hạn rồi xử lý ngoài consumer thread. Không để logging/audit chậm khiến startup bị kẹt.

Chọn `@EventListener` khi muốn method listener gọn trong bean Spring. Chọn `ApplicationListener<ConsumerStartingEvent>` khi class được thiết kế chuyên nhận sự kiện này. Cả hai đều dùng Spring application event mechanism, không phải một Kafka topic chứa sự kiện startup.

## 13. Event được phát ở thread nào?

Theo mặc định, Spring `ApplicationEventMulticaster` thường gọi event listeners **đồng bộ trên thread phát event**. Với những Kafka listener container events, đây thường là consumer-related thread.

Điều đó có một hệ quả rất thực tế: nếu `@EventListener` thực hiện một thao tác blocking dài, thread consumer có thể bị chậm ngay trong quá trình khởi động.

Ví dụ không nên làm:

~~~java
@EventListener
public void onStarting(ConsumerStartingEvent event) {
    externalAuditApi.callAndWaitForMinutes(...);
    Thread.sleep(60_000L);
}
~~~

Một event handler như vậy có thể kéo dài thời gian từ lúc consumer task bắt đầu đến lúc polling, dù `ConsumerStartingEvent` đã được phát.

Nên làm:

~~~java
@EventListener
public void onStarting(ConsumerStartingEvent event) {
    MessageListenerContainer source =
            event.getSource(MessageListenerContainer.class);

    log.info("Consumer thread starting: {}", source.getListenerId());
    startupMetricRecorder.increment(source.getListenerId());
}
~~~

Nếu cần gửi notification hoặc lưu audit từ xa, ưu tiên cơ chế bất đồng bộ **không làm chậm consumer thread**, và giới hạn kích thước queue/tài nguyên. Không sử dụng event lifecycle như một điểm chèn tác vụ vận hành nặng vào đường nóng của consumer.

## 14. Thread safety khi custom event multicaster chạy bất đồng bộ

Có thể cấu hình Spring application event multicaster sử dụng executor bất đồng bộ. Khi đó event handler có thể được gọi trên thread **khác** consumer thread.

Quy tắc:

- Kafka `Consumer` không thread-safe.
- Không gọi các method của Kafka `Consumer` từ event handler async chỉ vì event object có reference tới một consumer trong một số loại events.
- `ConsumerStartingEvent` chủ yếu mang references tới container; không giả định nó cung cấp KafkaConsumer để thao tác.
- Nếu cần pause/resume, dùng API của `MessageListenerContainer` thay vì chạm trực tiếp `KafkaConsumer` từ một thread tùy ý.
- Nếu cần làm việc với assignment/seek, dùng callback được Spring Kafka thiết kế cho consumer thread, chẳng hạn `ConsumerSeekAware` hoặc rebalance listener phù hợp.

Đặc biệt, handler được viết cho `ListenerContainerIdleEvent` hoặc `NonResponsiveConsumerEvent` có thể có consumer reference; nếu multicaster chuyển async mà code vẫn gọi `consumer.pause()`/`seek()` tùy tiện, sẽ phát sinh lỗi thread safety.

Một nguyên tắc an toàn cho `ConsumerStartingEvent` là **chỉ đọc metadata container và ghi observability**, không điều khiển trực tiếp consumer state ngay trong callback.

## 15. ConsumerStartingEvent không phải readiness signal

Một ứng dụng có thể phát `ConsumerStartingEvent` khi:

- Kafka cluster đang tạm mất kết nối.
- DNS/broker bootstrap chưa sẵn sàng.
- Consumer chưa join group.
- Partition assignment chưa xảy ra.
- Topic đang trống và không có record nào để xử lý.
- Dependency downstream chưa sẵn sàng.
- Listener còn đang khởi tạo những phần việc khác trước poll.

Do đó, một health/readiness probe chỉ kiểm tra “đã thấy starting event” có thể trả **READY** quá sớm.

Nên phân biệt các cấp readiness:

| Điều kiện quan sát | Điều gì được chứng minh? | Chưa chứng minh |
|---|---|---|
| Application context refresh | Spring beans đã được tạo | Kafka consumer thread chạy |
| `ConsumerStartingEvent` | Consumer thread bắt đầu startup | Poll, assignment, business readiness |
| `ConsumerStartedEvent` | Consumer sắp poll | Đã có partition assignment |
| Assignment callback | Consumer được gán partition theo group | Đã xử lý được record đầu tiên |
| Poll/record processing thành công | Data path đang hoạt động | Tất cả partitions hoặc dependency khác đều khỏe |
| Consumer lag/SLO đạt ngưỡng | Tiến độ xử lý phù hợp một tiêu chí vận hành | Không thay thế toàn bộ health checks |

Một readiness policy tốt cần dựa trên **yêu cầu dịch vụ cụ thể**. Ví dụ, một dịch vụ API không phụ thuộc Kafka consumer để phục vụ HTTP có thể ready trước khi Kafka stream bắt kịp. Một background worker quan trọng có thể cần đảm bảo consumer running, assignment hợp lệ và downstream khỏe trước khi được coi là sẵn sàng thực hiện nhiệm vụ.

Không có một event lifecycle đơn lẻ đủ để xác nhận mọi điều kiện này.

## 16. Phân biệt ConsumerStartingEvent với ApplicationReadyEvent

Spring Boot `ApplicationReadyEvent` báo giai đoạn Spring Boot application startup đã hoàn tất theo framework. `ConsumerStartingEvent` do Spring Kafka container phát ở mốc consumer thread khởi động.

Hai sự kiện có scope khác nhau:

~~~text
Spring Boot application startup
    |
    +-- Tạo bean / register @KafkaListener
    |
    +-- Start SmartLifecycle containers theo phase
    |
    +-- ConsumerStartingEvent (có thể xảy ra trong startup)
    |
    +-- ApplicationReadyEvent (lifecycle của Spring Boot)
~~~

Không nên dựa vào thứ tự tuyệt đối giữa mọi lifecycle event của mọi container và `ApplicationReadyEvent` trong mọi cấu hình. `autoStartup=false`, custom lifecycle phase, dynamic listener creation hoặc stop/restart có thể khiến consumer event xảy ra **sau** Spring Boot đã ready.

Với container tạo động, một service chạy nền có thể phát `ConsumerStartingEvent` bất kỳ lúc nào trong vòng đời ứng dụng, không chỉ lúc process khởi động.

## 17. Vì sao một event có thể xuất hiện nhiều lần?

Một số tình huống tạo thêm `ConsumerStartingEvent`:

1. Ứng dụng restart và container start lại.
2. Operator gọi `stop()` rồi `start()` trên listener container.
3. Một child consumer được tạo lại theo lifecycle/error recovery tương ứng.
4. Một listener khác hoặc dynamic listener mới được đăng ký và khởi động.
5. Nhiều child consumers trong một concurrent container cùng start.
6. Nhiều application instances cùng chạy một listener ID.

Không được suy luận rằng mỗi listener ID chỉ có duy nhất một starting event trong suốt đời hệ thống.

Một số sự kiện **không đồng nghĩa** tạo starting event mới:

- Một Kafka record mới được poll.
- Một retry của `DefaultErrorHandler` trên cùng consumer đang chạy.
- Một rebalance thông thường khi consumer thread vẫn tồn tại.
- Pause/resume container mà không stop/start consumer thread.

Nếu một service đếm starting event như “consumer đã xử lý xong 1 batch”, metric sẽ hoàn toàn sai. Đây là metric về **consumer task lifecycle**, không phải record throughput.

## 18. Kết hợp ConsumerStartedEvent và ConsumerStoppedEvent

Để quan sát một vòng đời thay vì chỉ mốc bắt đầu, lắng nghe nhiều loại event:

~~~java
@Component
public class KafkaConsumerLifecycleLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerLifecycleLogger.class);

    @EventListener
    public void onStarting(ConsumerStartingEvent event) {
        log.info(
            "Kafka consumer STARTING: {}",
            event.getSource(MessageListenerContainer.class).getListenerId()
        );
    }

    @EventListener
    public void onStarted(ConsumerStartedEvent event) {
        log.info(
            "Kafka consumer STARTED: {}",
            event.getSource(MessageListenerContainer.class).getListenerId()
        );
    }

    @EventListener
    public void onStopped(ConsumerStoppedEvent event) {
        log.info(
            "Kafka consumer STOPPED: source={} reason={}",
            event.getSource(MessageListenerContainer.class).getListenerId(),
            event.getReason()
        );
    }
}
~~~

Import các event:

~~~java
import org.springframework.kafka.event.ConsumerStartingEvent;
import org.springframework.kafka.event.ConsumerStartedEvent;
import org.springframework.kafka.event.ConsumerStoppedEvent;
~~~

`ConsumerStoppedEvent` có `reason` mô tả một số nguyên nhân dừng như normal, error, fencing, authentication hoặc no-offset tùy phiên bản. Không cần tự đoán reason bằng cách parse log exception.

Nếu muốn tính startup latency, cần ghép event cùng **lifecycle instance** một cách hợp lý. Chỉ dùng listener ID cho toàn bộ cluster có thể trộn dữ liệu của các pods hoặc nhiều child consumers.

## 19. Ví dụ theo dõi startup latency

Một ứng dụng có thể đo thời gian từ khi nhận `ConsumerStartingEvent` tới `ConsumerStartedEvent`. Đây là thời gian giữa **hai mốc lifecycle**, không phải thời gian từ application start đến khi business processing ready.

Ý tưởng:

~~~text
ConsumerStartingEvent at t0
ConsumerStartedEvent  at t1

startup_transition_duration = t1 - t0
~~~

Để kết quả đáng tin:

- Dùng container source identity và instance identity để ghép hai event.
- Không dùng timestamp hệ thống từ các pod khác nhau làm cùng một khoảng đo nếu clock chưa đồng bộ.
- Lưu trạng thái ghép cặp với cấu trúc thread-safe nếu có concurrent events.
- Loại bỏ entries hết hạn khi consumer không tới mốc started.
- Không dùng dynamic consumer ID quá chi tiết làm metric tag không giới hạn.

Với metric aggregated, dùng các labels như application, listener ID hoặc container type; tránh event ID, Kafka offset, thread ID ngẫu nhiên ở cardinality lớn. Nếu cần điều tra một consumer cụ thể, dùng log hoặc tracing.

Lưu ý: nếu consumer bị block **sau `ConsumerStartedEvent` nhưng trước poll thành công**, phép đo trên không phản ánh toàn bộ thời gian đạt readiness. Muốn đo readiness, phải có thêm điều kiện quan sát khác.

## 20. Những metric và alert nên xây dựng

| Tín hiệu | Ý nghĩa |
|---|---|
| Số `ConsumerStartingEvent` theo listener/instance | Consumer threads thực sự bắt đầu |
| Số `ConsumerStartedEvent` | Threads đến mốc trước polling |
| Số `ConsumerFailedToStartEvent` | Consumer task startup quá timeout |
| Số `ConsumerStoppedEvent` theo reason | Vòng đời consumer kết thúc vì nguyên nhân gì |
| Khoảng thời gian starting → started | Phát hiện startup bị chậm ở giai đoạn khởi tạo |
| Listener container running state | Container đã start chưa |
| Executor active threads và queue size | Phát hiện consumer task thiếu worker |
| Consumer group members/assignment | Consumer có tham gia group và nhận partitions không |
| Consumer lag | Tiến độ thực tế so với producer |
| Poll/processing error rate | Consumer có xử lý records thành công không |
| Authentication/authorization failures | Lỗi credential/ACL, không nhầm executor starvation |

Một alert hữu ích: `ConsumerFailedToStartEvent` tăng sau khi nâng `concurrency` hoặc thêm listeners. Khi đó ưu tiên kiểm tra executor, thread capacity và container configuration.

Một alert khác: nhiều starting events xuất hiện liên tiếp trên cùng instance cùng với stopped events bất thường. Đây có thể là dấu hiệu lifecycle churn hoặc container restart loop; điều tra reason và thời điểm deploy.

## 21. ConsumerStartingEvent và executor sizing

Một mô hình sizing ban đầu:

~~~text
orders listener concurrency = 4
payments listener concurrency = 3
shipments listener concurrency = 2

Tổng số consumer tasks dài hạn: 9
~~~

Nếu tất cả sử dụng chung một fixed executor 4 worker threads, tối đa bốn tasks có thread chạy đồng thời; các tasks còn lại có nguy cơ không bao giờ bắt đầu nếu tasks đang chạy luôn giữ thread. Một số containers có thể tạo `ConsumerFailedToStartEvent` khi vượt `consumerStartTimeout`.

Không có một công thức sizing thread duy nhất cho mọi hệ thống: Spring Kafka phiên bản, loại executor, container concurrency và workload có thể khác nhau. Nhưng cần bảo đảm executor phục vụ **đầy đủ những consumer tasks chạy lâu dài**.

Các bước sizing:

1. Liệt kê số `@KafkaListener` và concurrency của từng container.
2. Xác định factory/container nào dùng chung listener task executor.
3. Kiểm tra executor core/max pool size, queue capacity và rejection policy.
4. Đo số consumer threads đang sống sau startup.
5. Quan sát starting/failed-to-start events khi tăng tải.
6. Phân biệt executor listener với executor khác như Kafka producer callback, database hoặc application async jobs.
7. Không chia sẻ pool nhỏ với tác vụ blocking dài nếu nó làm consumer task bị starve.

Tăng `consumerStartTimeout` có thể giảm báo động ở startup chậm nhẹ; nó không thể tạo thêm threads khi pool đã bị chiếm toàn bộ.

## 22. Xử lý ConsumerFailedToStartEvent

Một observer có thể log/alert:

~~~java
@Component
public class ConsumerStartupFailureObserver {

    private static final Logger log =
            LoggerFactory.getLogger(ConsumerStartupFailureObserver.class);

    @EventListener
    public void onFailed(ConsumerFailedToStartEvent event) {
        MessageListenerContainer container =
                event.getContainer(MessageListenerContainer.class);

        log.error(
            "Kafka consumer failed to start before timeout: container={}",
            container.getListenerId()
        );

        startupAlertPublisher.publish(container.getListenerId());
    }
}
~~~

`startupAlertPublisher` là component ví dụ do ứng dụng định nghĩa. Trong production, nên gửi alert bất đồng bộ hoặc qua cơ chế an toàn không làm chậm thread đang phát event.

Khi nhận event này, hãy phân loại:

- **Executor starvation:** tasks không có threads.
- **Task rejected:** executor shutdown hoặc queue/rejection policy.
- **Container không thật sự start:** `autoStartup`, lifecycle phase, lỗi cấu hình.
- **Startup block:** một phần khởi tạo chiếm thread hoặc dependency bị block.
- **Monitoring/config mismatch:** event listener chưa đăng ký đúng context, config timeout quá ngắn cho môi trường thật.

`ConsumerFailedToStartEvent` là **triệu chứng chưa quan sát starting event đúng hạn**. Nó không tự chỉ ra exception gốc hoặc xác nhận broker down.

## 23. Tác động tới Kubernetes readiness/liveness

Một Kubernetes pod có thể chạy Spring Boot HTTP server nhưng Kafka consumer chưa start do thiếu executor thread. Nếu readiness probe chỉ kiểm tra HTTP 200 của endpoint chung, hệ thống có thể đánh dấu pod ready dù background Kafka processing chưa hoạt động.

Ngược lại, nếu liveness probe phụ thuộc consumer phải luôn luôn processing records, một topic rỗng hoặc maintenance pause có thể kích hoạt restart không cần thiết.

Một hướng thiết kế:

- **Liveness:** process và framework còn vận hành, không dùng việc chưa có record làm lý do kill pod.
- **Readiness:** phụ thuộc vai trò service; có thể cần kiểm tra consumer container running, assignment, downstream capacity hoặc startup failure.
- **Startup probe:** cho phép thời gian khởi động phù hợp với deployment và Kafka group joining.
- **Business health:** theo dõi lag, processing success, DLT, retry và SLA trong observability.

`ConsumerStartingEvent` có thể bổ sung thông tin cho readiness, nhưng **không nên là điều kiện duy nhất**. Nếu hệ thống yêu cầu phải có partition assignment, cần kiểm tra assignment qua callback/API phù hợp. Nếu consumer cố ý pause do backpressure, health policy cần diễn giải pause đúng thay vì coi đó là crash.

## 24. Sử dụng event để làm gì và không nên làm gì?

### Nên làm

- Ghi log structured cho consumer thread startup.
- Tăng counter consumer starting theo listener/instance.
- Theo dõi thời gian chuyển từ starting sang started.
- Liên kết event với deployment/rollout và thay đổi concurrency.
- Phát hiện executor starvation qua `ConsumerFailedToStartEvent`.
- Theo dõi lifecycle churn khi consumer được stop/start thường xuyên.
- Kết hợp với container state, assignment và consumer lag trong dashboard.

### Không nên làm

- Đánh dấu mọi listener và business flow đã READY chỉ từ starting event.
- Tự commit offset, reset offsets hoặc seek Kafka consumer trong callback startup.
- Gọi HTTP/database đồng bộ dài hoặc sleep trong event handler.
- Tự restart container ngay trong callback mà không có lifecycle ownership.
- Đếm event này thành số Kafka records đã tiêu thụ.
- Giả định một event tương ứng một partition.
- Giả định source luôn là parent container.
- Đọc event rồi tự động mở thêm consumer concurrency vô hạn.
- Dùng event lifecycle để thay thế error handler, retry, DLT hoặc monitoring poll errors.

## 25. Tình huống: consumer bắt đầu nhưng không nhận record

Giả sử log ghi:

~~~text
11:00:01 ConsumerStartingEvent source=orders-consumer-0
11:00:01 ConsumerStartedEvent  source=orders-consumer-0
11:03:01 Không có business record nào được xử lý
~~~

Các khả năng:

1. Topic rỗng và không có record mới.
2. Consumer group đã commit offset ở cuối log.
3. Consumer chưa có partition assignment hoặc partition được giao cho member khác.
4. Consumer bị pause.
5. Deserializer/poll gặp lỗi sau startup.
6. Kafka ACL/authentication hoặc broker connectivity gặp sự cố.
7. Listener container vẫn running nhưng listener xử lý chậm hoặc đang retry record lỗi.

Cách điều tra: kiểm tra assignment, lag, `isConsumerPaused()`, consumer group membership, poll error log và exception của error handler. Không kết luận consumer khỏe chỉ vì đã thấy `ConsumerStartingEvent`.

## 26. Tình huống: ConsumerFailedToStartEvent sau khi tăng concurrency

Giả sử trước deploy:

~~~text
Listener orders concurrency=2
Executor active threads=2 / max=4
Starting events=2
Failed-to-start events=0
~~~

Sau deploy:

~~~text
Listener orders concurrency=8
Executor active threads=4 / max=4
Starting events=4
Failed-to-start events tăng
~~~

Đây là dấu hiệu dễ liên hệ với executor thiếu threads. Giảm concurrency về mức phù hợp hoặc dùng executor đủ capacity có thể giải quyết; chỉ tăng timeout không khiến bốn consumer tasks còn lại được chạy nếu pool có bốn threads bị giữ lâu dài.

Nếu `concurrency` lớn hơn số partitions, cũng cần cân nhắc hiệu quả: tăng consumer threads chưa chắc tăng throughput. Nhưng thiếu partitions **không tự giải thích** tại sao task không có thread để phát starting event; đó là hai giới hạn khác nhau.

## 27. Tình huống: start/stop liên tục khi rollout

Ví dụ log:

~~~text
12:00:00 STARTING orders-consumer-0
12:00:00 STARTED  orders-consumer-0
12:00:20 STOPPED  orders-consumer-0 reason=ABNORMAL
12:00:21 STARTING orders-consumer-0
12:00:21 STARTED  orders-consumer-0
12:00:42 STOPPED  orders-consumer-0 reason=ABNORMAL
~~~

Một số khởi động lặp là bình thường khi rolling deployment hoặc operator restart có chủ đích. Nhưng **repeated abnormal stops** cần điều tra: producer fencing, auth failure, consumer exceptions, shutdown hooks hoặc container lifecycle logic.

Đừng đo số starting events mà không xem stopped reasons và phiên bản deploy. Counter starting tăng có thể do hệ thống scale out hoặc do crash loop; ý nghĩa vận hành rất khác.

## 28. Hướng dẫn kiểm thử event trong ứng dụng

Khi phát triển một listener startup observer, có thể thiết kế integration tests để quan sát event:

1. Khởi động Spring application context với `@KafkaListener` và container factory được cấu hình rõ ràng.
2. Đăng ký `@EventListener(ConsumerStartingEvent.class)` trước khi container bắt đầu.
3. Bắt đầu container, chờ event bằng latch hoặc bộ thu thập test events.
4. Xác nhận event có source/container reference phù hợp.
5. Nếu dùng concurrent container, quan sát nhiều child consumer starting events.
6. Cho listener container stop rồi start lại, xem startup event mới.
7. Kiểm tra không coi `ConsumerStartingEvent` là đồng nghĩa với partition assignment.
8. Tạo môi trường executor thiếu threads có chủ đích để quan sát startup timeout.
9. Kiểm tra event handler không làm treo consumer startup.
10. Sau test, shutdown container/executor để không rò rỉ threads.

Ví dụ một component thu event cho mục đích test:

~~~java
@Component
public class ConsumerStartingEventCollector {

    private final BlockingQueue<String> startedSources =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onStarting(ConsumerStartingEvent event) {
        String sourceId = event
                .getSource(MessageListenerContainer.class)
                .getListenerId();

        startedSources.offer(sourceId);
    }

    public String awaitStarting(long timeout, TimeUnit unit)
            throws InterruptedException {
        return startedSources.poll(timeout, unit);
    }
}
~~~

Trong production, không cần giữ unbounded queue các events nếu không có consumer đọc chúng. Collector ở trên là ví dụ dùng cho test có vòng đời ngắn; hệ thống thật nên dùng metrics/logging hoặc bounded data structures.

Các tình huống nêu trên chỉ giải thích cách xây kiểm thử; bước soạn bài này không chạy content QA hoặc test application.

## 29. Runbook: không thấy ConsumerStartingEvent

Khi một `@KafkaListener` dự kiến chạy nhưng không phát event:

1. **Kiểm tra listener được đăng ký chưa:** đúng `@KafkaListener`, bean scan và configuration.
2. **Kiểm tra container có tồn tại:** dùng `KafkaListenerEndpointRegistry` với listener ID.
3. **Kiểm tra lifecycle:** `isRunning()`, `autoStartup`, lifecycle phase, có ai gọi `stop()` không.
4. **Kiểm tra concurrency:** cần bao nhiêu child consumers thực sự?
5. **Kiểm tra task executor:** pool size, active threads, queue length và rejection.
6. **Kiểm tra startup timeout:** `consumerStartTimeout` và có `ConsumerFailedToStartEvent` không.
7. **Kiểm tra logging/event registration:** bean `@EventListener` có trong đúng application context không.
8. **Kiểm tra startup blockers:** initialization của consumer factory, deserializer, metrics hooks và thread startup.
9. **Nếu đã thấy ConsumerStartedEvent nhưng vẫn không có record:** chuyển sang điều tra assignment, polling, auth và lag; không tiếp tục coi đó là lỗi thread startup.
10. **Khắc phục và giám sát:** confirm starting/started events và consumer group hoạt động theo yêu cầu.

Không reset Kafka offset hoặc thay `auto.offset.reset` chỉ vì thiếu starting event: hai cơ chế này giải quyết vấn đề khác nhau.

## 30. Runbook: event có nhưng consumer vẫn không sẵn sàng

Một event đã đến không đồng nghĩa Kafka data path hoạt động. Hãy kiểm tra theo thứ tự:

1. Consumer thread còn sống, container còn running?
2. Consumer đã bắt đầu poll chưa, có error log khi poll không?
3. Consumer group đã join và được assign partitions chưa?
4. Topic, group ID, ACL và broker bootstrap configuration đúng chưa?
5. Consumer có bị pause do backpressure hoặc maintenance không?
6. Deserializer có gặp poison record khiến poll fail tại offset cố định không?
7. Listener có đang retry một record và giữ partition không?
8. Database/HTTP downstream có đáp ứng không?
9. Lag có giảm hoặc tiến độ offset có đạt yêu cầu không?
10. DLT có tăng bất thường không?

Nếu nguyên nhân là schema/deserialization lỗi, giải pháp nằm ở `ErrorHandlingDeserializer`, exception classification và recovery. Nếu nguyên nhân là executor starvation trước khi startup, giải pháp nằm ở thread capacity. Không dùng một event để thay thế toàn bộ chẩn đoán.

## 31. Checklist thiết kế ConsumerStartingEvent

- [ ] Hiểu event phát khi consumer thread bắt đầu, trước polling.
- [ ] Phân biệt `ConsumerStartingEvent` với `ConsumerStartedEvent` và `ConsumerFailedToStartEvent`.
- [ ] Dùng `@EventListener` hoặc `ApplicationListener<ConsumerStartingEvent>`.
- [ ] Hiểu `getSource(Class)` là container phát event và `getContainer(Class)` có thể là parent.
- [ ] Xử lý concurrency: nhiều child consumers có thể phát nhiều events.
- [ ] Lọc theo listener/container ID phù hợp, không giả định source luôn là parent.
- [ ] Không coi starting event là partition assignment, record processing hoặc readiness.
- [ ] Không chạy blocking I/O dài trong callback synchronous.
- [ ] Không thao tác KafkaConsumer từ event handler chạy async.
- [ ] Quan sát `consumerStartTimeout` và `ConsumerFailedToStartEvent`.
- [ ] Sizing executor đủ cho các consumer tasks dài hạn.
- [ ] Theo dõi running state, assignment, lag, stopped reason và retry/DLT cùng startup events.
- [ ] Phân biệt startup sau restart/scale với startup loop bất thường.
- [ ] Có runbook khi thiếu event và khi có event nhưng consumer chưa hoạt động.

## 32. Nguồn tham khảo

- [Spring Kafka Reference — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
- [Spring Kafka API — ConsumerStartingEvent](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/event/ConsumerStartingEvent.html)
- [Spring Kafka API — KafkaEvent](https://docs.spring.io/spring-kafka/docs/current/api/org/springframework/kafka/event/KafkaEvent.html)

**Kết luận:** `ConsumerStartingEvent` là tín hiệu rất sớm về lifecycle của Spring Kafka consumer: **thread bắt đầu khởi tạo trước khi polling**. Nó hỗ trợ tracing startup, giám sát số consumer threads và kết hợp với `ConsumerFailedToStartEvent` để chẩn đoán thiếu thread trong executor. Để xác nhận consumer thực sự sẵn sàng, cần thêm các chỉ số về container running, polling, assignment, dependency health, lag và business processing. Một ứng dụng reliability tốt phải phân biệt rõ **đã khởi động thread**, **đã bắt đầu poll** và **đã có khả năng xử lý dữ liệu an toàn**.
