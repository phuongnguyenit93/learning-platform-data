# Container start và stop

Trong Spring Kafka, listener container quản lý vòng đời của Kafka consumer: tạo consumer, gọi `poll()`, chuyển record tới listener, quản lý offset và đóng consumer khi dừng. Điều khiển thời điểm container bắt đầu hoặc kết thúc là một phần quan trọng của vận hành, đặc biệt khi ứng dụng cần chờ database migration, dependency readiness, bảo trì hoặc shutdown có kiểm soát.

Spring Kafka thường tạo container cho `@KafkaListener` và quản lý chúng thông qua `KafkaListenerEndpointRegistry`. Ứng dụng có thể để container tự khởi động cùng Spring context, trì hoãn startup bằng `autoStartup`, hoặc chủ động gọi `start()` và `stop()` trên container được registry quản lý.

## 1. Vòng đời của listener container

Một listener container quản lý một hoặc nhiều Kafka consumer. Với `ConcurrentMessageListenerContainer`, thuộc tính `concurrency` quyết định số child container/consumer được tạo để xử lý song song các partition được gán cho consumer group.

Vòng đời cơ bản có thể mô tả như sau:

```text
Spring ApplicationContext khởi động
              |
              v
KafkaListenerEndpointRegistry khởi động
              |
              v
Listener container start()
              |
              v
Consumer tạo kết nối và tham gia consumer group
              |
              v
poll() -> listener xử lý -> commit offset theo AckMode
              |
              v
Listener container stop()
              |
              v
Consumer rời group và đóng tài nguyên
```

Container thực hiện các thao tác trên consumer thread. Việc gọi `start()` yêu cầu container bắt đầu hoạt động; không nên mặc định rằng ngay khi phương thức trả về thì consumer đã nhận đủ partition hoặc đã xử lý record đầu tiên. Việc kết nối broker, tham gia group và hoàn tất partition assignment diễn ra bất đồng bộ theo giao thức Kafka.

`start()` và `stop()` là thao tác quản lý vòng đời. Chúng khác với `pause()` và `resume()`, vốn tạm ngừng hoặc tiếp tục việc lấy record trong khi container vẫn đang chạy. Chọn đúng thao tác giúp tránh tạo rebalance không cần thiết khi chỉ muốn điều tiết lưu lượng.

## 2. Auto startup mặc định

Các listener container được tạo cho `@KafkaListener` thường tự khởi động khi Spring context khởi động. Đây là hành vi thuận tiện cho ứng dụng consumer thông thường: khi application sẵn sàng, consumer bắt đầu nhận record.

Có thể cấu hình mặc định qua Spring Boot:

```yaml
spring:
  kafka:
    listener:
      auto-startup: true
```

Nếu cần trì hoãn toàn bộ listener, đặt `auto-startup: false`. Khi đó container được đăng ký nhưng không tự bắt đầu khi context khởi động.

```yaml
spring:
  kafka:
    listener:
      auto-startup: false
```

Có thể ghi đè ở từng listener bằng thuộc tính `autoStartup` của `@KafkaListener`:

```java
@KafkaListener(
        id = "order-events-listener",
        topics = "orders",
        groupId = "order-projection",
        autoStartup = "false")
public void handle(OrderEvent event) {
    orderProjectionService.apply(event);
}
```

Thuộc tính `id` tạo định danh để tìm container trong registry. Khi ứng dụng cần điều khiển riêng từng listener, hãy đặt ID rõ ràng và duy nhất trong registry. `autoStartup` là thuộc tính dạng chuỗi nên có thể dùng placeholder cấu hình, ví dụ `autoStartup = "${orders.listener.auto-startup:false}"`, tùy phiên bản và cách bind cấu hình.

Giá trị mặc định nên được chọn theo lifecycle của ứng dụng. Nếu listener có thể chạy ngay khi Spring context sẵn sàng, giữ auto startup thường đơn giản nhất. Nếu listener chỉ được phép nhận record sau khi migration, warm-up hoặc kiểm tra dependency hoàn tất, hãy trì hoãn startup và kích hoạt rõ ràng sau bước chuẩn bị.

## 3. Điều khiển container qua KafkaListenerEndpointRegistry

Các container do `@KafkaListener` tạo ra được quản lý bởi `KafkaListenerEndpointRegistry`. Registry là điểm truy cập phù hợp để tìm một listener container theo ID và gọi các thao tác lifecycle.

Ví dụ một service điều khiển listener:

```java
@Service
public class ListenerLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerLifecycleService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("order-events-listener");

        if (container == null) {
            throw new IllegalStateException("Không tìm thấy order-events-listener");
        }

        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("order-events-listener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
```

`getListenerContainer(id)` trả về container tương ứng hoặc `null` nếu ID không tồn tại. Nên xử lý trường hợp không tìm thấy container và tránh gọi start/stop lặp lại không cần thiết. `isRunning()` cho biết trạng thái lifecycle mà container báo cáo; nó không khẳng định consumer đã được assign partition hoặc đang xử lý record.

Để khởi động một listener đã đặt `autoStartup = "false"`, có thể gọi service sau khi dependency sẵn sàng. Ví dụ:

```java
@Component
public class ListenerStartup implements ApplicationRunner {

    private final KafkaListenerEndpointRegistry registry;
    private final OrderDependencyReadiness readiness;

    public ListenerStartup(
            KafkaListenerEndpointRegistry registry,
            OrderDependencyReadiness readiness) {
        this.registry = registry;
        this.readiness = readiness;
    }

    @Override
    public void run(ApplicationArguments args) {
        readiness.awaitReady();

        MessageListenerContainer container =
                registry.getListenerContainer("order-events-listener");
        if (container != null && !container.isRunning()) {
            container.start();
        }
    }
}
```

`awaitReady()` chỉ là ví dụ về cơ chế chờ readiness của ứng dụng. Trong hệ thống thực tế, nên dùng cơ chế readiness có timeout, log trạng thái dependency và xử lý lỗi startup rõ ràng; không chờ vô hạn khiến ứng dụng khởi động ở trạng thái không xác định.

## 4. Khởi động và dừng toàn bộ listener

Registry cung cấp danh sách các container mà nó quản lý. Khi cần thực hiện một thao tác trên toàn bộ listener, có thể duyệt danh sách này:

```java
@Service
public class AllListenersLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public AllListenersLifecycleService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startAll() {
        registry.getListenerContainers().forEach(container -> {
            if (!container.isRunning()) {
                container.start();
            }
        });
    }

    public void stopAll() {
        registry.getListenerContainers().forEach(container -> {
            if (container.isRunning()) {
                container.stop();
            }
        });
    }
}
```

Chỉ dùng thao tác hàng loạt khi các listener thực sự có cùng điều kiện lifecycle. Nhiều ứng dụng có listener cho các luồng dữ liệu khác nhau; một listener có thể cần chạy ngay trong khi listener khác phải chờ dependency hoặc feature flag. Trong trường hợp đó, điều khiển theo ID rõ ràng hơn.

Các container được tạo bởi registry không nhất thiết là bean riêng lẻ trong `ApplicationContext`. Vì vậy, không nên giả định có thể inject trực tiếp mọi container như một Spring bean. Với `@KafkaListener`, hãy dùng registry. Nếu ứng dụng tự tạo container bằng `ConcurrentMessageListenerContainer`, cần quản lý bean và lifecycle của container theo cách phù hợp với cấu trúc ứng dụng.

## 5. Dừng container có kiểm soát

Khi gọi `stop()`, container ngừng tiêu thụ và đóng consumer. Trong lúc dừng, container cần xử lý đúng công việc đang thực hiện và tiến độ offset. Hành vi cụ thể phụ thuộc loại listener, ack mode, số record đã poll và cấu hình dừng.

Có thể dùng overload nhận callback để thực hiện bước tiếp theo khi container đã dừng:

```java
MessageListenerContainer container =
        registry.getListenerContainer("order-events-listener");

if (container != null && container.isRunning()) {
    container.stop(() -> log.info("Order listener đã dừng hoàn toàn"));
}
```

Callback hữu ích khi một quy trình quản trị cần chờ container kết thúc trước khi đóng một tài nguyên phụ trợ hoặc đánh dấu trạng thái bảo trì. Không nên giả định callback chạy ngay trong cùng thread gọi `stop()`; lifecycle của container có thể cần phối hợp với consumer thread.

### Dừng sau record hiện tại hoặc sau poll batch

Trong các phiên bản Spring Kafka có hỗ trợ `ContainerProperties.stopImmediate`, có thể điều chỉnh điểm container dừng:

```java
factory.getContainerProperties().setStopImmediate(true);
```

Với `stopImmediate = false` (mặc định trong các phiên bản hỗ trợ thuộc tính này), container xử lý hết các record còn lại từ lần poll trước khi dừng. Khi đặt `true`, container dừng sau khi xử lý record hiện tại. Cấu hình này ảnh hưởng đến thời gian shutdown và số record đang chờ trong batch; cần kiểm tra semantics theo phiên bản Spring Kafka đang sử dụng.

Không nên nhầm `stopImmediate` với việc bỏ qua commit offset. Offset vẫn được quản lý theo ack mode và cơ chế commit của container. Nếu record chưa được xác nhận hoặc commit khi container dừng, record có thể được đọc lại sau khi consumer group tiếp tục. Điều này là bình thường trong mô hình at-least-once và cần được xử lý an toàn bằng idempotency.

## 6. Shutdown của Spring ApplicationContext

Listener container tích hợp với lifecycle của Spring. Khi application context dừng, Spring yêu cầu các bean lifecycle dừng theo phase. `KafkaListenerEndpointRegistry` quản lý những container được tạo từ `@KafkaListener`, vì vậy ứng dụng thường không cần tự viết hook gọi `stop()` cho từng listener chỉ để xử lý shutdown thông thường.

Spring Boot có thể nhận tín hiệu shutdown của process/container và đóng ApplicationContext. Khi đó, các bean `SmartLifecycle` được dừng theo thứ tự phase. Nếu ứng dụng có dependency cần đóng theo thứ tự cụ thể, cần thiết kế phase và callback hợp lý để listener dừng trước khi tài nguyên mà listener đang dùng bị đóng.

Ví dụ, nếu listener cần database để hoàn tất record đang xử lý, database connection pool phải còn hoạt động trong lúc listener dừng. Dừng database trước rồi mới dừng listener có thể khiến các record đang xử lý lỗi và bị giao lại. Có thể tổ chức lifecycle để listener dừng trước database, đồng thời đặt timeout shutdown đủ lớn cho thời gian xử lý dự kiến.

Một cấu hình container minh họa:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
orderListenerFactory(ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setShutdownTimeout(20_000L);
    factory.getContainerProperties().setAckMode(ContainerProperties.AckMode.RECORD);
    return factory;
}
```

`shutdownTimeout` điều khiển khoảng thời gian container chờ quá trình shutdown hoàn tất trong các phiên bản Spring Kafka có thuộc tính này. Giá trị cần phù hợp với thời gian xử lý và giới hạn termination grace period của nền tảng. Nếu Kubernetes gửi SIGTERM rồi chỉ cho Pod một khoảng thời gian ngắn trước khi SIGKILL, timeout bên trong ứng dụng phải nằm trong ngân sách đó và chừa thời gian cho Spring đóng các bean khác.

Một quy trình shutdown điển hình:

1. Nền tảng gửi tín hiệu dừng tới process.
2. Spring Boot đóng ApplicationContext và yêu cầu các lifecycle bean dừng.
3. Listener container ngừng nhận công việc mới, hoàn tất phần công việc được phép theo cấu hình dừng.
4. Container commit offset theo ack mode và trạng thái xử lý có thể xác nhận.
5. Consumer rời group và đóng tài nguyên.
6. Các dependency khác được đóng theo lifecycle phase.

Nếu process bị kill cưỡng bức trước khi hoàn tất, record chưa commit có thể được giao lại. Không có cấu hình shutdown nào loại bỏ hoàn toàn khả năng replay khi process mất đột ngột; listener nên an toàn khi xử lý lại record.

## 7. Lifecycle phase và thứ tự khởi động

Spring dùng `SmartLifecycle` để điều khiển thứ tự start/stop của các thành phần có lifecycle. `phase` quyết định thứ tự tương đối: phase thấp thường được start trước và stop sau; phase cao được start sau và stop trước. Listener container có phase được quản lý bởi registry/container properties tùy cấu hình và phiên bản.

Nếu listener cần một service phụ trợ khởi động trước, có thể tổ chức phase để dependency sẵn sàng trước khi listener bắt đầu. Khi shutdown, thứ tự ngược lại giúp listener dừng trước dependency. Tuy nhiên, phase chỉ sắp xếp thứ tự lifecycle; nó không thay thế readiness check. Một bean có thể đã được start nhưng kết nối tới hệ thống phụ trợ vẫn chưa thực sự sẵn sàng.

Với yêu cầu startup phụ thuộc vào điều kiện nghiệp vụ như schema migration, feature flag hoặc dữ liệu cache đã nạp, cách dễ kiểm soát thường là đặt listener `autoStartup=false` rồi start rõ ràng sau khi điều kiện hoàn tất. Với yêu cầu đơn giản chỉ cần thứ tự bean, phase có thể đủ.

Không nên thay đổi phase tùy tiện trong một ứng dụng có nhiều `SmartLifecycle` bean. Hãy xác định dependency thực tế, ghi rõ thứ tự mong muốn và kiểm tra cả hai chiều startup/shutdown.

## 8. Start/stop khác pause/resume

`stop()` kết thúc vòng đời consumer container. Khi container được start lại, consumer tham gia consumer group và có thể trải qua rebalance, partition assignment mới. `pause()` chỉ tạm dừng việc lấy record trong khi consumer vẫn duy trì hoạt động và membership trong group.

| Thao tác | Tác động | Khi nên dùng |
|---|---|---|
| `start()` | Bắt đầu consumer container và tham gia consumer group | Khởi động listener sau khi ứng dụng sẵn sàng |
| `stop()` | Dừng consumer container và đóng consumer | Shutdown, bảo trì hoặc tắt hẳn một listener |
| `pause()` | Tạm dừng tiêu thụ partition được gán; container vẫn chạy | Backpressure hoặc tạm ngừng nhận thêm record |
| `resume()` | Tiếp tục tiêu thụ sau pause | Dependency đã hồi phục hoặc backpressure đã được giải tỏa |

Ví dụ pause/resume container:

```java
MessageListenerContainer container =
        registry.getListenerContainer("order-events-listener");

if (container != null && container.isRunning()) {
    container.pause();
}

// Khi điều kiện cho phép xử lý trở lại:
if (container != null && container.isRunning()) {
    container.resume();
}
```

Container pause thường được áp dụng trên consumer thread theo cơ chế nội bộ của Spring Kafka. Vì vậy, lời gọi `pause()` có thể chỉ đặt yêu cầu; trạng thái pause thực tế được thực hiện ở vòng poll tiếp theo. Có thể theo dõi các sự kiện pause/resume hoặc trạng thái container để xác nhận thay đổi.

Nếu chỉ cần tạm ngừng vì database đang quá tải, pause/resume thường phù hợp hơn stop/start. Dừng rồi start lại có thể làm consumer rời group và gây rebalance, trong khi pause giữ container hoạt động. Ngược lại, khi cần giải phóng consumer và dừng listener trong thời gian dài, stop là lựa chọn đúng.

## 9. Theo dõi trạng thái bằng lifecycle events

Spring Kafka phát các application event liên quan đến lifecycle consumer và container. Các event hữu ích gồm:

- `ConsumerStartingEvent`: consumer sắp được tạo/bắt đầu.
- `ConsumerStartedEvent`: consumer đã khởi động.
- `ConsumerStoppingEvent`: consumer đang dừng.
- `ConsumerStoppedEvent`: consumer đã dừng; event cung cấp lý do dừng trong các phiên bản hỗ trợ.
- `ContainerStoppedEvent`: container đã dừng.
- `ConsumerFailedToStartEvent`: consumer không khởi động được trong các phiên bản hỗ trợ event này.

Có thể lắng nghe event để ghi log hoặc cập nhật trạng thái vận hành:

```java
@Component
public class KafkaLifecycleEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaLifecycleEvents.class);

    @EventListener
    public void onConsumerStarted(ConsumerStartedEvent event) {
        log.info("Kafka consumer started: {}", event.getContainer());
    }

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {
        log.info("Kafka consumer stopped: {}", event.getReason());
    }

    @EventListener
    public void onContainerStopped(ContainerStoppedEvent event) {
        log.info("Kafka listener container stopped: {}", event.getSource());
    }
}
```

Tên event và thuộc tính cụ thể có thể khác giữa các phiên bản Spring Kafka; hãy đối chiếu API của phiên bản đang dùng khi viết listener event. Event consumer thường được phát cho từng consumer thread, vì vậy một container có concurrency lớn có thể tạo nhiều event start/stop. Không nên đếm mỗi event consumer như một lần start/stop duy nhất của cả container.

Event listener nên xử lý nhanh. Nếu cần thực hiện công việc quản trị kéo dài, hãy chuyển sang executor hoặc cơ chế điều phối phù hợp thay vì giữ thread phát event quá lâu.

## 10. Trạng thái running không đồng nghĩa đã sẵn sàng nhận record

`container.isRunning()` phản ánh trạng thái lifecycle. Nó không bảo đảm rằng consumer đã hoàn tất kết nối broker, được assign partition hoặc đã xử lý record. Trong hệ thống có yêu cầu readiness chặt chẽ, cần theo dõi thêm partition assignment và các event phù hợp.

Ví dụ dùng `ConsumerAwareRebalanceListener` để nhận biết partition được gán:

```java
factory.getContainerProperties().setConsumerRebalanceListener(
        new ConsumerAwareRebalanceListener() {
            @Override
            public void onPartitionsAssigned(
                    Consumer<?, ?> consumer,
                    Collection<TopicPartition> partitions) {
                log.info("Assigned Kafka partitions: {}", partitions);
            }
        });
```

Đây là hook rebalance ở cấp consumer; có thể dùng để cập nhật trạng thái readiness nếu ứng dụng thực sự cần biết partition assignment. Nếu có nhiều consumer thread, cần tổng hợp trạng thái từ tất cả consumer liên quan. Một consumer đã được assign partition cũng không có nghĩa dependency nghiệp vụ phía sau luôn sẵn sàng.

Với health/readiness probe, nên định nghĩa rõ trạng thái cần chứng minh: application context đã chạy, listener container đã start, consumer đã được assign partition hay hệ thống phụ trợ đã sẵn sàng xử lý. Không dùng một boolean `isRunning()` để đại diện cho tất cả các điều kiện này.

## 11. Quản lý lỗi khi start và restart

Startup có thể thất bại do broker không truy cập được, authentication chưa sẵn sàng, topic hoặc metadata chưa sẵn sàng, hoặc cấu hình consumer sai. Cần theo dõi log và lifecycle events để xác định container có start thành công hay liên tục gặp lỗi.

Khi cần restart một listener sau khi sửa dependency, có thể stop rồi start lại:

```java
public void restartOrdersListener() {
    MessageListenerContainer container =
            registry.getListenerContainer("order-events-listener");

    if (container == null) {
        throw new IllegalStateException("Không tìm thấy order-events-listener");
    }

    if (container.isRunning()) {
        container.stop();
    }

    container.start();
}
```

Đoạn code trên minh họa ý tưởng nhưng không bảo đảm `stop()` đã hoàn tất bất đồng bộ trước khi `start()` được gọi trong mọi tình huống. Với quy trình restart cần thứ tự nghiêm ngặt, dùng `stop(Runnable callback)` rồi gọi `start()` từ callback hoặc từ một coordinator sau khi xác nhận container đã dừng.

```java
public void restartOrdersListenerSafely() {
    MessageListenerContainer container =
            registry.getListenerContainer("order-events-listener");

    if (container == null) {
        throw new IllegalStateException("Không tìm thấy order-events-listener");
    }

    if (container.isRunning()) {
        container.stop(() -> {
            log.info("Listener đã dừng; bắt đầu lại");
            container.start();
        });
    }
    else {
        container.start();
    }
}
```

Trong ứng dụng thực tế, cần bảo vệ thao tác restart khỏi nhiều request đồng thời, ghi nhận trạng thái trung gian và đặt timeout cho quy trình. Nếu start thất bại, cần báo trạng thái rõ ràng thay vì để hệ thống nghĩ listener đang phục vụ bình thường.

Nếu consumer dừng do lỗi xử lý hoặc broker, restart có thể khiến record chưa commit được đọc lại. Listener cần idempotent đối với side effect ngoài Kafka. Restart không xóa committed offset và cũng không tự động đưa consumer về đầu topic; vị trí đọc tiếp tục phụ thuộc committed offset và `auto.offset.reset` khi chưa có offset hợp lệ.

## 12. Vận hành start/stop trong môi trường production

Điều khiển listener trong production nên có quyền truy cập phù hợp, log audit và trạng thái có thể quan sát. Nếu cung cấp endpoint quản trị để start/stop listener, endpoint đó cần được bảo vệ bằng authentication/authorization và không nên cho phép mọi người dùng ứng dụng thay đổi trạng thái consumer tùy ý.

Một quy trình bảo trì có thể thực hiện như sau:

1. Xác định listener ID và partition/topic bị ảnh hưởng.
2. Kiểm tra consumer lag, record đang xử lý và trạng thái dependency.
3. Nếu chỉ cần giảm tải tạm thời, pause container và theo dõi trạng thái pause.
4. Nếu cần dừng hẳn, gọi stop và chờ callback xác nhận container đã dừng.
5. Thực hiện thay đổi hoặc bảo trì dependency.
6. Xác nhận dependency sẵn sàng rồi start container.
7. Theo dõi partition assignment, consumer lag, lỗi listener và tốc độ xử lý sau khi start.

Khi shutdown toàn ứng dụng, ưu tiên để Spring quản lý lifecycle và dành đủ thời gian graceful shutdown cho listener. Tránh gọi `System.exit()` hoặc kill process trước khi callback dừng hoàn tất nếu ứng dụng cần xử lý nốt record đang chạy.

Các tín hiệu vận hành nên theo dõi gồm:

- Số listener container đang chạy, đang dừng hoặc bị dừng ngoài dự kiến.
- Thời gian từ yêu cầu start đến khi consumer được assign partition.
- Thời gian từ yêu cầu stop đến callback hoàn tất.
- Consumer group lag trước và sau bảo trì.
- Số lần rebalance, lỗi kết nối broker, lỗi authentication và lỗi listener.
- Số record được xử lý nhưng chưa commit khi shutdown hoặc restart.

## 13. Các lỗi thường gặp

### Không tìm thấy container trong registry

Kiểm tra `@KafkaListener` đã được đăng ký, ID có đúng chính tả và container có được tạo trong context hiện tại hay không. Đặt `id` tường minh thay vì dựa vào ID tự sinh khi cần điều khiển từ code.

### Gọi start trước khi Spring context sẵn sàng

Container cần factory, consumer factory và các dependency đã được cấu hình. Hãy thực hiện lifecycle control sau khi context đã khởi tạo phù hợp, chẳng hạn qua `ApplicationRunner`, `ApplicationReadyEvent` hoặc coordinator riêng.

### Gọi stop rồi start ngay

Nếu quá trình stop chưa hoàn tất, start ngay có thể tạo race trong quy trình restart. Dùng callback để bắt đầu lại sau khi container dừng xong.

### Dùng stop khi chỉ muốn tạm ngừng tiêu thụ

Stop làm consumer rời group và có thể gây rebalance khi start lại. Nếu cần backpressure tạm thời, pause/resume thường phù hợp hơn.

### Shutdown timeout quá ngắn

Container có thể không đủ thời gian hoàn tất xử lý hoặc đóng consumer trước khi process bị kill. Căn chỉnh timeout của Spring, termination grace period của nền tảng và thời gian xử lý tối đa.

### Nghĩ rằng start xong là đã có partition

Start là thay đổi lifecycle. Partition assignment diễn ra sau đó qua giao thức consumer group. Dùng rebalance listener hoặc lifecycle event thích hợp nếu readiness phụ thuộc assignment.

### Không xử lý record được giao lại sau restart

Nếu offset chưa commit, record có thể được đọc lại. Thiết kế idempotent cho side effect và không coi restart là bằng chứng record trước đó chưa tạo tác động.

## 14. Chọn cơ chế theo nhu cầu

| Nhu cầu | Cơ chế phù hợp | Ghi chú |
|---|---|---|
| Listener tự chạy khi ứng dụng khởi động | `autoStartup=true` | Hành vi mặc định phổ biến |
| Chờ migration hoặc dependency trước khi nhận record | `autoStartup=false` rồi gọi `start()` | Có thể điều khiển qua registry theo listener ID |
| Dừng listener trong thời gian bảo trì | `stop()` và callback | Chờ container dừng trước khi thao tác tiếp |
| Tạm ngừng nhận record vì backpressure | `pause()` / `resume()` | Container vẫn duy trì lifecycle |
| Khởi động lại listener có thứ tự | `stop(Runnable)` rồi `start()` trong callback | Tránh race giữa stop và start |
| Xác nhận listener đã được assign partition | Rebalance listener hoặc event phù hợp | `isRunning()` không đủ để chứng minh assignment |
| Shutdown ứng dụng | Spring lifecycle và graceful shutdown | Căn chỉnh timeout với nền tảng triển khai |

Quản lý `start()` và `stop()` đúng cách giúp listener chỉ nhận record khi dependency đã sẵn sàng, dừng có kiểm soát khi bảo trì và giải phóng consumer đúng vòng đời. Hãy dùng registry để điều khiển listener do `@KafkaListener` tạo ra, phân biệt stop với pause, chờ callback khi cần thứ tự nghiêm ngặt và luôn thiết kế để xử lý an toàn các record chưa commit được giao lại sau restart.
