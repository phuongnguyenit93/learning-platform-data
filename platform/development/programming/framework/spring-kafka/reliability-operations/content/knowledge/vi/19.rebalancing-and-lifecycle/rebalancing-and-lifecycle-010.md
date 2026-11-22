# ContainerStoppedEvent

Trong Spring Kafka, mỗi listener thường được quản lý bởi một **listener container**. Container tạo Kafka consumer, điều khiển vòng `poll()`, gọi phương thức listener, quản lý offset, error handling, assignment và lifecycle. Khi ứng dụng dừng hoặc một listener được yêu cầu stop, container cần ngừng tiêu thụ, kết thúc các consumer threads và đóng tài nguyên liên quan.

**`ContainerStoppedEvent`** là Spring application event cho biết một listener container đã dừng. Ứng dụng có thể sử dụng tín hiệu này để ghi log lifecycle, cập nhật trạng thái giám sát, kết hợp với hệ thống điều phối shutdown hoặc phát hiện container dừng bất thường.

Cần hiểu đúng giới hạn: **sự kiện này không phải Kafka record, không phải callback rebalance và không chứng minh mọi nghiệp vụ đang xử lý đã thành công**. Nó chỉ phản ánh một thời điểm trong lifecycle của container trong tiến trình Spring.

## 1. Listener container và vai trò trong Spring Kafka

Một listener được khai báo như sau:

~~~java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "orders-listener",
            groupId = "orders-service",
            topics = "orders.events")
    public void onOrder(OrderEvent event) {
        orderService.process(event);
    }
}
~~~

Spring Kafka tạo container cho endpoint `orders-listener`. Với `@KafkaListener`, các container thường được quản lý qua `KafkaListenerEndpointRegistry`, còn factory như `ConcurrentKafkaListenerContainerFactory` cung cấp cấu hình concurrency, ack mode, error handler và các thuộc tính khác.

~~~text
Spring ApplicationContext
       |
       v
KafkaListenerEndpointRegistry
       |
       +---- orders-listener container
               |
               +---- KafkaConsumer / consumer thread
               +---- poll -> process -> offset handling
               +---- start / stop lifecycle
               +---- Kafka application events
~~~

Khi container dừng, Spring Kafka có thể phát `ContainerStoppedEvent` để các Spring beans đăng ký nhận event biết trạng thái lifecycle này. Event đi qua Spring `ApplicationEventPublisher` / event multicaster, không truyền qua broker Kafka.

## 2. ContainerStoppedEvent thông báo điều gì?

Sự kiện được dùng để ghi nhận **container đã thực hiện quá trình dừng**. Nó hữu ích cho những câu hỏi như:

- Stop do người vận hành yêu cầu đã dẫn đến tín hiệu lifecycle chưa?
- Một listener cụ thể có đang dừng trong quá trình application shutdown không?
- Có thể cập nhật metric số lần container stop tại thời điểm nào?
- Khi rollout, có container nào rời trạng thái running ngoài dự kiến?
- Cần lấy thêm log/event nào để giải thích nguyên nhân container dừng?

Tuy nhiên, **không nên suy diễn** từ một `ContainerStoppedEvent` rằng:

- Toàn bộ record đang xử lý đã thành công.
- Offset của tất cả partition đã commit.
- Kafka transaction và database transaction đã commit.
- Consumer group không còn member khác.
- Partition ownership đã chuyển sang instance nào.
- Stop được gây ra bởi lỗi, auth failure, producer fencing hay lệnh admin.
- Hệ thống chắc chắn đã có thời gian gửi log/metric ra ngoài.
- JVM bị kill đột ngột cũng sẽ phát ra event.

Lifecycle state và business processing state là hai vấn đề riêng. Khi cần chứng minh dữ liệu không bị mất hay xử lý trùng, vẫn phải kiểm tra committed offsets, error recovery và idempotency.

## 3. Nhận sự kiện qua @EventListener

Sử dụng class ở package Spring Kafka:

~~~java
import org.springframework.kafka.event.ContainerStoppedEvent;
~~~

Ví dụ listener:

~~~java
package com.example.kafka.monitoring;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ContainerStoppedEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaContainerStopLogger {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaContainerStopLogger.class);

    @EventListener
    public void whenContainerStopped(ContainerStoppedEvent event) {
        log.info("Kafka listener container stopped. source={}",
                event.getSource());
    }
}
~~~

Method này nhận **application event trong cùng Spring context**. Nó không tự phát event ra Kafka và cũng không đòi hỏi topic có tên `ContainerStoppedEvent`.

`getSource()` thuộc API Spring `ApplicationEvent`. Tùy event/phiên bản, API cũng có thể cung cấp tham chiếu tới container liên quan. Không nên ghi logic production phụ thuộc vào định dạng chuỗi `event.getSource().toString()`, vì chuỗi debug không phải định danh ổn định.

### 3.1. Nhận bằng ApplicationListener

Một phương án tương đương:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ContainerStoppedEvent;
import org.springframework.stereotype.Component;

@Component
public class ContainerStopObserver
        implements ApplicationListener<ContainerStoppedEvent> {

    @Override
    public void onApplicationEvent(ContainerStoppedEvent event) {
        // Cập nhật quan sát lifecycle; không commit offset ở đây.
        System.out.println("Stopped container: " + event.getSource());
    }
}
~~~

Trong ứng dụng production, nên dùng structured logging và metric thay cho `System.out.println()`. Không cần vừa khai báo `ApplicationListener` vừa tạo một `@EventListener` ghi cùng sự kiện nếu chỉ muốn một log.

## 4. Xác định listener container nào vừa dừng

Một Spring Boot service có thể có nhiều endpoint:

~~~text
orders-listener
payments-listener
inventory-listener
~~~

Nếu sử dụng một observer toàn cục, cần phân biệt các container. Có thể kiểm tra type của event source theo API được hỗ trợ:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ContainerStoppedEvent;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Component;

@Component
public class KafkaLifecycleObserver {

    @EventListener
    public void onStopped(ContainerStoppedEvent event) {
        Object source = event.getSource();

        if (source instanceof MessageListenerContainer container) {
            String listenerId = container.getListenerId();
            recordStop(listenerId);
        }
    }

    private void recordStop(String listenerId) {
        // Ví dụ: tăng counter theo listenerId hoặc ghi trạng thái.
    }
}
~~~

Khi dùng concurrent container, source có thể liên quan cấp container/child theo implementation. Nếu cần bảo đảm ánh xạ parent–child, hãy kiểm tra chính xác API và event source của phiên bản Spring Kafka đang chạy trước khi gán một ID nghiệp vụ.

Giữ `@KafkaListener(id = "...")` cố định để dashboard và registry cùng sử dụng một tên. Phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Listener ID | Định danh endpoint/container trong Spring Kafka. |
| Consumer group ID | Nhóm chia partition và lưu committed offsets trên broker. |
| Consumer client ID | Định danh client để ghi log và theo dõi metric. |
| Instance/Pod ID | Định danh tiến trình thực thi trong môi trường triển khai. |

Nếu không khai báo `groupId` riêng, một số cấu hình `@KafkaListener` có thể sử dụng listener ID làm group ID theo mặc định. Để tránh nhầm, ví dụ production nên đặt cả `id` và `groupId`.

## 5. Khi nào ContainerStoppedEvent xuất hiện?

Một số con đường lifecycle có thể dẫn đến việc container dừng:

1. **ApplicationContext đóng:** Spring lifecycle yêu cầu Kafka listeners dừng khi JVM shutdown có trật tự.
2. **Dừng bằng API:** ứng dụng gọi `stop()` trên container từ `KafkaListenerEndpointRegistry`.
3. **Lệnh vận hành:** admin/management endpoint tắt consumer để bảo trì hoặc chuyển workload.
4. **Điều kiện lỗi nghiêm trọng:** tùy Spring Kafka version và cấu hình, một số lỗi có thể khiến container stop.
5. **Concurrent container:** child consumers và parent container có các giai đoạn dừng khác nhau, có thể phát thêm event cấp consumer.

Không phải mọi sự cố Kafka đều dừng container. Ví dụ broker không phản hồi trong thời gian ngắn có thể khiến consumer retry/kết nối lại mà không có stop event.

Quan trọng hơn, **consumer group rebalance không đồng nghĩa container stop**. Rebalance thường chỉ thay đổi partition assignment khi container vẫn tiếp tục hoạt động.

## 6. Timeline dừng container và sự kiện lifecycle

Một chuỗi shutdown khái niệm:

~~~text
Application shutdown hoặc gọi container.stop()
               |
               v
Spring Kafka yêu cầu listener container dừng
               |
               v
Consumer thoát vòng poll / xử lý công việc đang chạy
               |
               v
Consumer close, container hoàn thành stop lifecycle
               |
               v
Spring Kafka publish ContainerStoppedEvent
               |
               v
Application event listeners nhận event
~~~

Sơ đồ là định hướng hiểu lifecycle, không phải hợp đồng cứng về thứ tự tất cả callbacks trong mọi phiên bản và mọi loại concurrent container. Event có thể đi qua synchronous hoặc asynchronous multicaster; timing của handler có thể khác thời điểm publisher tạo event.

Nếu listener đang gọi HTTP service trong khi stop, việc container dừng còn phụ thuộc timeout của dependency, chính sách shutdown và trạng thái consumer thread. Bản thân `ContainerStoppedEvent` không bảo đảm HTTP đã trả về thành công hoặc database transaction đã commit.

Khi quan sát shutdown, cần thu thập thêm:

- Kafka client logs và container lifecycle logs.
- Committed offset theo topic/partition và consumer group.
- Độ trễ xử lý listener và các request dependency đang mở.
- Kafka transaction commit/abort nếu listener transactional.
- Tình trạng DLT/error handler sau record xử lý thất bại.
- Thời gian Spring context shutdown và ngân sách của orchestrator.

## 7. So sánh với các sự kiện Spring Kafka khác

Spring Kafka có những event nghe gần giống nhau nhưng thể hiện các bước khác:

| Event | Ý nghĩa tổng quan | Dùng khi nào? |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread đi vào giai đoạn khởi động. | Quan sát startup. |
| `ConsumerStartedEvent` | Consumer đã bắt đầu hoạt động. | Giám sát consumer readiness. |
| `ConsumerStoppingEvent` | Consumer chuẩn bị dừng. | Phân tích thời gian stop ở cấp thread. |
| `ConsumerStoppedEvent` | Consumer đã dừng, có thể có reason. | Phân loại lý do consumer stop. |
| **`ContainerStoppedEvent`** | Listener container dừng. | Quan sát lifecycle cấp container. |
| `ConsumerFailedToStartEvent` | Consumer không khởi động được theo giới hạn chờ. | Điều tra startup failure. |
| `ListenerContainerIdleEvent` | Listener idle trong khoảng thời gian cấu hình. | Phân biệt không có record với consumer ngừng chạy. |
| `NonResponsiveConsumerEvent` | Consumer được xem không phản hồi theo cơ chế monitor của container. | Điều tra polling bị kẹt hoặc xử lý quá lâu. |

Tập event và những thuộc tính cụ thể có thể khác giữa các dòng phiên bản. Những event cấp consumer giúp nhìn sâu hơn vào từng consumer thread, còn event cấp container phục vụ việc quan sát lifecycle container.

### 7.1. ConsumerStoppedEvent và reason

`ConsumerStoppedEvent` có thể mang reason mô tả lý do consumer ngừng, ví dụ stop bình thường, error, fencing hoặc vấn đề auth tùy phiên bản. `ContainerStoppedEvent` nên được xem là tín hiệu “container stop” chứ không phải một mã lỗi chi tiết.

Nếu cần phân loại “planned shutdown” với “unexpected shutdown”, kết hợp:

- Trạng thái stop do ứng dụng yêu cầu.
- `ConsumerStoppedEvent`/reason nếu API đang dùng hỗ trợ.
- Exception và Kafka client logs gần thời điểm stop.
- Kubernetes rollout/restart signals.
- Consumer group membership, rebalance và health metrics.

### 7.2. Rebalance callback không phải stop event

Khi một consumer group thêm replica mới:

~~~text
Container RUNNING
       |
       v
Partitions revoked
       |
       v
Partitions assigned cho các member
       |
       v
Container tiếp tục poll
~~~

Đây là thay đổi partition ownership. Để xử lý state chuyển giao theo partition, dùng `ConsumerRebalanceListener` hoặc `ConsumerAwareRebalanceListener` theo API Spring Kafka tương ứng. Không dùng `ContainerStoppedEvent` để commit checkpoint khi partition revoked, vì container không bắt buộc phải dừng lúc đó.

## 8. Điều khiển stop qua KafkaListenerEndpointRegistry

Registry cho phép tìm container theo listener ID và yêu cầu dừng:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaListenerManager {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerManager(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean stopOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null) {
            return false;
        }

        container.stop();
        return true;
    }
}
~~~

`container.stop()` thể hiện yêu cầu dừng theo hợp đồng lifecycle. Không nên mặc định nó đồng nghĩa với “mọi offset đã commit” hoặc “toàn bộ nghiệp vụ đã hoàn tất” ngay khi trả về.

Nếu cần điều phối một quy trình phụ thuộc stop, có thể sử dụng callback:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container != null) {
    container.stop(() -> log.info("orders-listener stop completed"));
}
~~~

Callback stop và `ContainerStoppedEvent` đáp ứng hai nhu cầu khác nhau:

- **Stop callback:** xác nhận tiến trình của một yêu cầu stop cụ thể.
- **Application event:** quan sát container dừng, kể cả khi tác nhân khởi tạo không phải code gọi stop hiện tại.

Không giả định thứ tự thực thi callback và event listener là cố định khi multicaster chạy bất đồng bộ hoặc khi parent/child lifecycle được phối hợp.

## 9. ConcurrentMessageListenerContainer và nhiều consumer threads

Một concurrent listener factory có thể tạo nhiều consumer:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    return factory;
}
~~~

Listener cấu hình:

~~~java
@KafkaListener(
        id = "orders-listener",
        groupId = "orders-service",
        topics = "orders.events",
        containerFactory = "orderFactory")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Với concurrency bằng ba, một concurrent container quản lý tối đa ba child consumer containers. Khi stop, những consumer thread có thể hoàn tất ở các thời điểm khác nhau. Vì vậy:

- Không đếm `ConsumerStoppedEvent` như số Pod đã tắt.
- Không đếm `ContainerStoppedEvent` như số partition revoked.
- Nếu dashboard đo lifecycle theo listener, phải xác định rõ parent hay child.
- Chỉ số theo consumer nên sử dụng client ID/member metadata phù hợp.
- Không hard-code giả định event chỉ được phát đúng một lần nếu chưa xác minh bằng integration test trên phiên bản đang chạy.

Một child consumer dừng vì lỗi không nhất thiết nói lên trạng thái của toàn bộ concurrent parent container. Hãy kết hợp event với `registry.getListenerContainer(id).isRunning()` và những thông tin từ container.

## 10. Event listener có thể chạy trên thread nào?

Spring application events được phát qua `ApplicationEventMulticaster`. Với multicaster mặc định đồng bộ, listener thường được gọi trực tiếp trên luồng phát event. Với executor bất đồng bộ, handler có thể chạy ở thread khác.

Do đó, nên giữ xử lý trong `@EventListener` **nhẹ và không blocking dài**:

~~~java
@EventListener
public void onStopped(ContainerStoppedEvent event) {
    log.info("Listener container stopped, source={}", event.getSource());
    metrics.incrementContainerStopCount();
}
~~~

Không nên làm những việc sau trong event handler:

- Chờ một HTTP request vô thời hạn.
- Gọi database migration hoặc khóa tài nguyên lâu.
- Commit Kafka consumer offset hoặc thực hiện acknowledge record.
- Sử dụng KafkaConsumer từ thread không sở hữu consumer đó.
- Gọi `stop()` rồi chờ blocking trên chính container đang dừng.
- Gọi cleanup phụ thuộc một bean có thể đã đóng trong shutdown phase trước.
- Tự động restart container vô hạn khi lỗi auth/fencing chưa được sửa.

Nếu ghi log/metric thất bại, không để monitoring exception làm rối quá trình stop. Có thể bắt và ghi nhận lỗi ở phần observability:

~~~java
@EventListener
public void onStopped(ContainerStoppedEvent event) {
    try {
        lifecycleRecorder.recordStopped(event.getSource());
    } catch (RuntimeException exception) {
        log.warn("Could not record Kafka stop event", exception);
    }
}
~~~

Việc dùng asynchronous event listener cũng không bảo đảm event được xử lý trước khi JVM tắt. Executor/telemetry exporter có thể đang shutdown; do đó event handler không nên là điểm duy nhất lưu một audit record bắt buộc.

## 11. Spring Boot graceful shutdown và thời gian chờ

Spring Boot quản lý lifecycle của nhiều bean, bao gồm những container do Spring Kafka quản lý. Khi ứng dụng shutdown có trật tự, Spring dừng các bean theo phase và ngân sách chờ.

Ví dụ:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s

server:
  shutdown: graceful
~~~

`timeout-per-shutdown-phase` là ngân sách Spring lifecycle; `server.shutdown=graceful` áp dụng cho web server theo cơ chế Spring Boot. Listener Kafka vẫn có lifecycle riêng.

Spring Kafka có các thuộc tính thời gian chờ shutdown của container, chẳng hạn `ContainerProperties.shutdownTimeout` ở những phiên bản tương ứng. Chúng cần phối hợp với:

- Thời gian một record/batch listener cần để xử lý.
- HTTP/database client timeouts.
- Kafka transaction flush/commit/abort.
- Grace period của process runtime hoặc Kubernetes.
- Những lifecycle beans phụ thuộc mà listener còn cần.

Nếu thời gian shutdown quá ngắn, process có thể bị kill trước khi event xuất hiện. Nếu quá dài, rollout bị kéo chậm và instance lỗi khó được thay thế kịp thời.

### 11.1. Kubernetes SIGTERM và SIGKILL

Khi Pod bị terminate, kubelet thường gửi `SIGTERM` rồi chờ trong `terminationGracePeriodSeconds`. Nếu process chưa kết thúc, kubelet có thể dùng `SIGKILL`:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: order-consumer
      image: example/order-consumer:latest
~~~

`SIGTERM` cho ứng dụng cơ hội shutdown có trật tự, nên container có thể phát `ContainerStoppedEvent`. Ngược lại, `SIGKILL` hoặc JVM crash **không bảo đảm cleanup callbacks/application events được thực thi**.

Vì vậy, absence of stop event không có nghĩa process vẫn chạy; cần thêm tín hiệu từ orchestrator, consumer group và committed offsets. Không coi stop event là nguồn audit bền vững duy nhất.

## 12. Readiness, liveness và listener health

Có thể dùng event để phản ánh trạng thái “listener không còn hoạt động”, nhưng cần chính sách health rõ ràng.

Ví dụ ứng dụng có hai listener:

- `orders-critical` bắt buộc hoạt động để xử lý đơn hàng.
- `audit-optional` có thể dừng tạm thời mà không ảnh hưởng service chính.

Khi `orders-critical` stop ngoài dự kiến, observer có thể hạ trạng thái readiness hoặc phát alert. Khi `audit-optional` stop có kế hoạch, không nhất thiết phải coi toàn bộ service unhealthy.

| Trạng thái | Câu hỏi cần trả lời | Vai trò của ContainerStoppedEvent |
|---|---|---|
| Readiness | Instance có đủ điều kiện xử lý công việc mới? | Một input để đánh giá listener trọng yếu. |
| Liveness | Process có hoạt động và có khả năng phục hồi? | Không đủ để tự quyết định restart mọi trường hợp. |
| Consumer group assignment | Instance đang giữ partition nào? | Cần metrics/consumer APIs, không suy ra từ event. |
| Business progress | Event có được xử lý đúng SLO? | Cần lag, throughput, failure và DB state. |
| Shutdown progress | Container đã dừng theo lifecycle? | Event là một tín hiệu phù hợp. |

Với consumer-only service trên Kubernetes, HTTP readiness không trực tiếp ra lệnh Kafka broker ngừng cấp partition. Kafka group ownership và listener container lifecycle phải được điều khiển bằng những cơ chế riêng.

## 13. ContainerStoppedEvent không phải “offset checkpoint”

Một lỗi thiết kế nguy hiểm là coi stop event như điểm đánh dấu thành công của toàn bộ record:

~~~text
Sai:
ContainerStoppedEvent
     |
     +---- tự commit tất cả offsets
     +---- đánh dấu mọi event nghiệp vụ thành công
~~~

Container có thể dừng sau một exception, một transaction rollback hoặc khi consumer chưa kịp commit offset. Event không cho biết record nào đã thành công, record nào cần redelivery.

Với record listener, trách nhiệm commit offset thuộc ack mode, error handler và container. Với transactional listener, output Kafka và offset đầu vào có thể được commit cùng transaction theo cấu hình; event lifecycle nằm ngoài giao thức commit đó.

Nếu cần bảo đảm business effect, hãy:

1. Xác định offset đã commit từ consumer group.
2. Kiểm tra record output bằng consumer `read_committed` khi dùng Kafka transactions.
3. Kiểm tra database/outbox/inbox để phát hiện partial commit.
4. Thiết kế idempotency cho redelivery.
5. Kiểm tra DLT/retry khi listener bị lỗi.

Đừng triển khai commit offset hoặc thao tác record cụ thể từ một `@EventListener` chỉ nhận ContainerStoppedEvent.

## 14. Phân biệt các tình huống bất thường

### 14.1. Consumer group rebalance

Một replica mới gia nhập khiến partitions được revoked và assigned lại. Container của các replica hiện có **có thể vẫn running**. Không dùng ContainerStoppedEvent để quyết định khi nào lưu state per-partition; dùng rebalance callbacks đúng nghĩa.

### 14.2. Broker unavailable tạm thời

KafkaConsumer có thể kết nối lại, retry request hoặc đợi metadata/fetch. Không phải mọi request timeout đều dừng container. Nếu muốn phát hiện tình huống không còn tiến triển, nên theo dõi lỗi Kafka client, lag và `NonResponsiveConsumerEvent` nếu phù hợp.

### 14.3. Authentication/authorization failure

Tùy cấu hình và phiên bản, container có thể dừng hoặc thử lại sau lỗi xác thực/phân quyền. Khi dừng, stop event chỉ là tín hiệu kết quả. Cần tìm nguyên nhân từ exception, consumer stopped reason và Kafka logs; không auto-restart vô hạn để tạo vòng lỗi.

### 14.4. Producer fencing trong transaction

Khi một transactional producer mất quyền do epoch cũ, container có thể dừng theo chính sách như `stopContainerWhenFenced` ở phiên bản hỗ trợ. Phải điều tra transactional ID/owner thực tế; restart một producer bị fence trên cùng identity đang tranh chấp không giải quyết triệt để.

### 14.5. JVM crash hoặc hard kill

Một process bị kill thẳng có thể không có event dừng. Kafka consumer group và committed offsets phải đủ để instance khác tiếp tục xử lý an toàn; database side effects cần chống trùng.

### 14.6. Pause và resume

`pause()` tạm ngừng nhận thêm records theo cơ chế container nhưng vẫn duy trì vòng poll/group membership phù hợp. `resume()` tiếp tục. Pause/resume không tương đương stop/start và không nên làm dashboard báo container stopped.

## 15. ApplicationContext đóng và thứ tự lifecycle

Spring `ContextClosedEvent` và Kafka `ContainerStoppedEvent` có ý nghĩa khác nhau:

~~~text
ApplicationContext bắt đầu đóng
        |
        v
ContextClosedEvent
        |
        v
Spring lifecycle dừng containers / beans theo phase
        |
        v
Kafka listener container dừng
        |
        v
ContainerStoppedEvent được phát
~~~

Thứ tự khái niệm trên không thay thế hợp đồng event của phiên bản đang sử dụng. Với asynchronous multicaster, việc handler thực sự chạy có thể bị trễ. Nếu observer cần database connection hoặc telemetry exporter, hãy xem chúng còn sống trong shutdown phase hay không.

Không để event handler thực hiện nghiệp vụ bắt buộc sau khi phần lớn resources đã được hủy. Nếu cần điều phối thứ tự stop của nhiều service, dùng lifecycle/dependency/phases và bounded waits, thay vì dựa vào việc nhận một event in-memory.

## 16. Integration test ContainerStoppedEvent

Một test đáng tin cậy sử dụng Spring context có listener container thật và một probe nhận event. Kafka Testcontainers hoặc Embedded Kafka có thể được dùng để chạy consumer.

Probe:

~~~java
@Component
public class StoppedEventProbe {

    private final BlockingQueue<ContainerStoppedEvent> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onStopped(ContainerStoppedEvent event) {
        events.offer(event);
    }

    public ContainerStoppedEvent poll(Duration timeout)
            throws InterruptedException {
        return events.poll(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

Các import Java cần thiết: `BlockingQueue`, `LinkedBlockingQueue`, `TimeUnit`, `Duration` và Spring Kafka `ContainerStoppedEvent`.

Test:

~~~java
@Autowired
KafkaListenerEndpointRegistry registry;

@Autowired
StoppedEventProbe probe;

@Test
void stopPublishesEvent() throws Exception {
    MessageListenerContainer container =
            registry.getListenerContainer("orders-listener");

    assertThat(container).isNotNull();

    if (!container.isRunning()) {
        container.start();
    }

    container.stop();

    ContainerStoppedEvent event =
            probe.poll(Duration.ofSeconds(30));

    assertThat(event).isNotNull();
}
~~~

Với nhiều listeners, probe cần lọc theo container identity hoặc test chỉ bật một container để tránh false positive. Với concurrent container, số lượng event có thể phản ánh parent/child behavior; **đừng assert chính xác một event nếu chưa chứng minh framework contract của phiên bản đang dùng**.

### 16.1. Đợi stop callback thay vì Thread.sleep()

~~~java
CountDownLatch stopped = new CountDownLatch(1);

container.stop(stopped::countDown);

assertThat(stopped.await(30, TimeUnit.SECONDS)).isTrue();
assertThat(container.isRunning()).isFalse();
~~~

Callback kiểm tra quá trình stop trong container, còn probe xác nhận application event đã được publish/nhận. Không giả định thứ tự callback và event listener nếu event multicaster chạy bất đồng bộ.

### 16.2. Những kịch bản test cần có

1. Stop một listener đang idle: container chuyển trạng thái và event xuất hiện.
2. Stop khi listener đang xử lý record: quan sát thời gian chờ, commit/rollback và redelivery.
3. Stop concurrent listener: phân biệt consumer-level và container-level events.
4. Stop rồi start lại: listener tiếp tục nhận record mà không rò rỉ consumer thread.
5. ApplicationContext shutdown: container dừng trong giới hạn lifecycle.
6. Simulate SIGTERM trong child process: có cơ hội ghi event và thoát graceful.
7. Hard kill: event có thể vắng, nhưng hệ thống vẫn recover theo offsets/idempotency.
8. Rebalance không stop: chắc chắn application không đánh đồng partition revoke và container stop.
9. Lỗi nghiêm trọng dừng container: kết hợp reason/exception để chẩn đoán.
10. Observer telemetry ném exception: monitoring failure không làm rối shutdown.

Dùng timeout hữu hạn và điều kiện quan sát được. Đừng lấy số giây `Thread.sleep()` cố định làm bằng chứng rằng stop hoàn tất.

## 17. Structured logging và metrics

Một log vận hành hữu ích:

~~~text
event_type=ContainerStoppedEvent
application=orders-consumer
listener_id=orders-listener
instance_id=orders-worker-2
shutdown_intent=planned
timestamp=2026-11-15T16:00:00Z
~~~

`shutdown_intent` là **metadata tự quản lý của ứng dụng**, không phải thuộc tính mặc định của `ContainerStoppedEvent`. Có thể ghi intent khi admin API gọi stop hoặc khi context bắt đầu đóng, rồi đối chiếu event và Kafka client logs.

Các metrics nên xem xét:

| Metric | Ý nghĩa |
|---|---|
| Container running state | Listener đang chạy hay đã dừng. |
| Stop event count | Số lần container dừng theo ID ổn định. |
| Consumer stop reason count | Thống kê nguyên nhân nếu phiên bản Spring Kafka hỗ trợ. |
| Consumer group assignment | Số partition đang được sở hữu. |
| Consumer lag theo partition | Stop kéo dài làm backlog tăng ở đâu. |
| Listener error rate | Lỗi ngay trước khi stop. |
| Graceful shutdown duration | Thời gian từ yêu cầu stop tới hoàn tất. |
| Pod restart/termination reason | Phân biệt shutdown bình thường với hard kill. |

Không dùng offset hoặc correlation ID làm metrics label có cardinality lớn. Dùng structured log/trace để tra thông tin của từng record.

Nếu observability pipeline cũng đang shutdown, event có thể được ghi nhưng không kịp export. Với audit bắt buộc, sử dụng cơ chế bền vững riêng thay vì dựa vào log phát từ stop event.

## 18. Các sai lầm thường gặp

- **Nhầm application event với Kafka record:** `ContainerStoppedEvent` không có Kafka topic/offset của riêng nó.
- **Coi stop event là “xử lý sạch backlog”:** container có thể dừng với record chưa commit.
- **Dùng stop event thay cho rebalance listener:** rebalance không bắt buộc dừng container.
- **Gộp ConsumerStoppedEvent và ContainerStoppedEvent:** chúng mô tả các cấp lifecycle khác nhau.
- **Giả định một event tương ứng một Pod/partition:** concurrency có thể tạo nhiều tín hiệu ở cấp khác nhau.
- **Gọi HTTP/database lâu trong event handler:** có thể làm shutdown trễ hoặc thất bại.
- **Giả định event listener luôn chạy đúng consumer thread:** còn phụ thuộc event multicaster.
- **Dựa vào event để commit offset:** offset phải theo ack/transaction/recovery semantics.
- **Không phân biệt planned và unexpected stop:** phải kết hợp intent, reason, error logs.
- **Dùng event làm audit duy nhất:** SIGKILL/JVM crash có thể làm event không xuất hiện.
- **Tự restart listener vô hạn khi lỗi cấu hình:** không sửa root cause auth/fencing.
- **Dùng toString() source làm định danh ổn định:** chuỗi debug không phải API contract.
- **Cho rằng stop() luôn đồng nghĩa stop hoàn tất ngay:** kiểm tra callback/state/event.
- **Không phối hợp timeout với Kubernetes:** process có thể bị kill trước khi dừng graceful.

## 19. Thiết kế quan sát lifecycle cho production

Một kiến trúc đơn giản:

~~~text
ContainerStoppedEvent
       |
       v
Spring lifecycle observer
       |
       +---- structured log
       +---- stop counter / running-state gauge
       +---- unexpected-stop alert khi phù hợp
       |
       +---- đối chiếu Kafka group membership
       +---- đối chiếu ConsumerStoppedEvent reason
       +---- đối chiếu lag/error/transaction metrics
       +---- đối chiếu SIGTERM/restart events
~~~

Đừng để `ContainerStoppedEvent` trở thành nơi đặt logic nghiệp vụ như xử lý lại record, xác nhận offset hoặc publish dữ liệu phải bảo đảm exactly-once. Đây là sự kiện **quan sát lifecycle**, không phải transaction boundary.

Khi phối hợp event với `KafkaListenerEndpointRegistry`, consumer-level events, shutdown timeouts và dấu hiệu từ orchestrator, hệ thống Spring Kafka có thể nhận biết listener đã dừng, tìm nguyên nhân stop ngoài dự kiến và kiểm soát rollout rõ ràng hơn. Độ tin cậy xử lý record vẫn phải được bảo vệ độc lập bằng offset management, retry/DLT, Kafka transactions và idempotency của các tài nguyên bên ngoài Kafka.
