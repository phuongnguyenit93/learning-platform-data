# Vòng đời listener container, pause, resume và graceful shutdown

Trong Spring Kafka, một listener không chỉ là phương thức được gọi khi có record. Spring tạo và quản lý một listener container đứng giữa Kafka Consumer và phương thức xử lý của ứng dụng. Container tạo consumer, subscribe topic, tham gia consumer group, poll dữ liệu, gọi listener, quản lý offset, xử lý rebalance và đóng consumer khi ứng dụng dừng.

Hiểu vòng đời container giúp ứng dụng chủ động dừng nhận dữ liệu khi cần bảo trì, tạm ngưng một topic hoặc partition khi downstream quá tải, tiếp tục xử lý sau khi hệ thống phục hồi và shutdown có kiểm soát khi deploy. Các thao tác pause/resume/stop phải được phân biệt rõ: pause giữ consumer trong group và tạm ngưng fetch; stop đóng consumer và rời group; shutdown của cả ứng dụng còn phải phối hợp với listener đang xử lý và các dependency như database/API.

## 1. Listener container nằm ở đâu trong Spring Kafka?

Với annotation @KafkaListener, Spring Kafka đăng ký endpoint và tạo container tương ứng. Container sở hữu Kafka Consumer và điều phối việc poll record rồi gọi listener method.

~~~mermaid
flowchart TD
    A[Spring Application Context] --> B[KafkaListenerEndpointRegistry]
    B --> C[Listener container]
    C --> D[Kafka Consumer]
    D --> E[Kafka broker]
    C --> F[@KafkaListener method]
    F --> G[Business service]
    G --> H[Database / API]
~~~

Các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| @KafkaListener | Khai báo endpoint, topic, group ID, concurrency và listener method |
| KafkaListenerEndpointRegistry | Lưu và quản lý các container được tạo từ @KafkaListener |
| MessageListenerContainer | Giao diện điều khiển lifecycle, pause/resume và trạng thái container |
| KafkaMessageListenerContainer | Container dùng một Kafka Consumer |
| ConcurrentMessageListenerContainer | Container cha tạo và điều phối nhiều child container/consumer |
| ConsumerFactory | Tạo Kafka Consumer với cấu hình bootstrap, deserializer, group và security |
| ContainerProperties | Cấu hình poll timeout, ack mode, shutdown timeout và hành vi container |

Khi dùng concurrency lớn hơn một, ConcurrentMessageListenerContainer quản lý nhiều consumer instance. Mỗi child container có consumer và thread riêng; các consumer cùng tham gia group và chia partition theo assignment của Kafka.

## 2. Vòng đời của listener container

Một container thường trải qua các trạng thái và hoạt động sau:

1. **Created:** Spring tạo endpoint/container từ cấu hình listener.
2. **Started:** container tạo consumer, subscribe/assign và bắt đầu poll.
3. **Assigned:** consumer tham gia group và nhận partition assignment.
4. **Running:** container poll record và gọi listener theo ack mode.
5. **Paused:** container tạm dừng fetch từ một hoặc nhiều partition nhưng vẫn duy trì vòng poll cần thiết.
6. **Resumed:** container tiếp tục fetch sau khi được resume.
7. **Stopping:** container ngừng nhận công việc mới, hoàn tất phần đang chạy theo lifecycle và đóng consumer.
8. **Stopped:** consumer đã đóng; khi start lại, container tham gia group và có thể nhận assignment mới.

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Running: start
    Running --> Paused: pause
    Paused --> Running: resume
    Running --> Stopping: stop
    Paused --> Stopping: stop
    Stopping --> Stopped: consumer closed
    Stopped --> Running: start again
~~~

Pause không phải một trạng thái đóng container. Container vẫn tồn tại, vẫn giữ consumer và membership trong group. Stop mới kết thúc consumer lifecycle; khi consumer rời group, Kafka có thể rebalance và giao partition cho member khác.

## 3. Container được quản lý bởi Spring như thế nào?

Listener container triển khai lifecycle của Spring, bao gồm SmartLifecycle. Điều này cho phép Spring ApplicationContext tự start container khi ứng dụng khởi động và stop container khi context đóng.

### Tự động khởi động

Ví dụ:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.events",
    groupId = "order-service",
    autoStartup = "true",
    concurrency = "3"
)
public void onOrderCreated(OrderCreated event) {
    orderService.handle(event);
}
~~~

autoStartup mặc định thường là true. Có thể đặt false để Spring đăng ký container nhưng chưa tự chạy; ứng dụng sẽ gọi start khi điều kiện vận hành đã sẵn sàng.

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.events",
    groupId = "order-service",
    autoStartup = "false"
)
public void onOrderCreated(OrderCreated event) {
    orderService.handle(event);
}
~~~

### Quản lý container bằng KafkaListenerEndpointRegistry

Container được tạo bởi @KafkaListener thường được tra cứu qua KafkaListenerEndpointRegistry. Registry quản lý các endpoint container và cung cấp API để start/stop từng listener.

~~~java
@Service
public class ListenerLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerLifecycleService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
            requireContainer("ordersListener");
        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
            requireContainer("ordersListener");
        if (container.isRunning()) {
            container.stop();
        }
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer container =
            registry.getListenerContainer(id);
        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener container: " + id);
        }
        return container;
    }
}
~~~

Không phải mọi container đều nằm trong registry. Container được tạo thủ công như một bean từ ConcurrentKafkaListenerContainerFactory có thể được inject và điều khiển trực tiếp. Với listener annotation, dùng registry là cách thông thường.

### Lifecycle phase và thứ tự shutdown

SmartLifecycle có phase để phối hợp thứ tự start/stop giữa các thành phần Spring. Thành phần có phase cao hơn thường được start muộn hơn và stop sớm hơn. Khi listener cần database hoặc HTTP client để hoàn tất record, cần thiết kế thứ tự dừng sao cho listener được dừng trước khi các dependency đó bị đóng.

Không nên đóng connection pool hoặc client downstream trước khi container đã dừng và listener đang chạy đã hoàn tất. Có thể dùng lifecycle phase hoặc một shutdown coordinator của ứng dụng để điều phối thứ tự rõ ràng.

## 4. Pause và resume toàn listener container

Pause tạm dừng việc fetch record từ Kafka cho container. Resume yêu cầu container tiếp tục fetch.

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("ordersListener");

if (container == null) {
    throw new IllegalStateException("Listener not found");
}

container.pause();
// ... thực hiện bảo trì hoặc chờ downstream phục hồi ...
container.resume();
~~~

API container được thiết kế để có thể yêu cầu pause/resume từ thread ứng dụng. Container sẽ áp dụng thao tác lên Kafka Consumer ở consumer thread phù hợp; không lấy KafkaConsumer bên trong container rồi gọi pause/resume trực tiếp từ thread khác.

### Pause không đóng consumer và không rời group

Khi container được pause:

- Consumer không fetch thêm record từ partition đã pause.
- Container vẫn tiếp tục poll theo cơ chế cần thiết để duy trì membership và heartbeat.
- Consumer vẫn thuộc group; partition chưa bị giao cho member khác chỉ vì pause.
- Record mới tiếp tục được broker lưu trong topic, consumer sẽ đọc sau khi resume.
- Consumer lag có thể tăng trong thời gian pause.

Điểm này làm pause phù hợp cho bảo trì ngắn, backpressure hoặc chờ downstream phục hồi. Nếu dừng container, consumer đóng và rời group; Kafka có thể rebalance partition sang member khác.

### Kiểm tra pause đã được áp dụng

Pause request và trạng thái consumer thực tế không nhất thiết thay đổi cùng thời điểm:

~~~java
container.pause();

boolean pauseRequested = container.isPauseRequested();
boolean consumerPaused = container.isConsumerPaused();
~~~

- isPauseRequested() cho biết container đã nhận yêu cầu pause.
- isConsumerPaused() cho biết consumer thread đã áp dụng pause.

Với concurrent container, trạng thái cha phản ánh trạng thái điều phối của các child; cần quan sát thêm log/event của container nếu muốn chẩn đoán một child cụ thể. Không coi pause request là bằng chứng rằng mọi partition đã dừng fetch ngay tại dòng code tiếp theo.

## 5. Pause theo từng partition

Đôi khi chỉ một partition bị lỗi dữ liệu, downstream theo một tenant bị nghẽn hoặc một partition cần được bảo trì. Dừng cả listener container có thể làm gián đoạn các partition khác đang xử lý bình thường. Spring Kafka hỗ trợ pause/resume theo TopicPartition:

~~~java
TopicPartition partition =
    new TopicPartition("orders.events", 2);

MessageListenerContainer container =
    registry.getListenerContainer("ordersListener");

container.pausePartition(partition);

// Sau khi điều kiện đã được khắc phục:
container.resumePartition(partition);
~~~

Các API trạng thái tương ứng có thể dùng để kiểm tra yêu cầu và trạng thái pause của partition:

~~~java
boolean requested = container.isPartitionPauseRequested(partition);
boolean paused = container.isPartitionPaused(partition);
~~~

Partition phải thuộc assignment của container để consumer thực hiện pause trên partition đó. Với concurrent container, partition cụ thể được một child consumer sở hữu; container cha điều phối yêu cầu tới child phù hợp. Nếu assignment thay đổi do rebalance, ứng dụng cần kiểm tra lại partition owner và chính sách pause sau khi partition được giao lại.

Không nên lưu giả định rằng partition luôn thuộc một consumer/thread cố định. Kafka có thể chuyển partition sang child khác hoặc instance khác sau rebalance.

### Khi nào nên pause toàn container, khi nào pause partition?

| Tình huống | Cách phù hợp |
|---|---|
| Database dùng chung đang quá tải, mọi record đều bị ảnh hưởng | Pause toàn container hoặc điều chỉnh concurrency/backpressure |
| Một partition có poison record cần điều tra | Pause partition đó nếu muốn giữ các partition khác tiếp tục |
| Bảo trì toàn bộ service hoặc chuẩn bị shutdown | Pause toàn container rồi stop theo kế hoạch |
| Một tenant/aggregate có lỗi nhưng các tenant khác vẫn chạy | Cân nhắc partition pause nếu key/partitioning cho phép cô lập |
| Cần deploy phiên bản mới và rời group | Stop container có kiểm soát, không chỉ pause |

## 6. Pause và poll: vì sao consumer vẫn sống?

Kafka Consumer cần tiếp tục gọi poll để duy trì hoạt động group protocol. Khi pause qua container, Spring Kafka gọi các thao tác consumer ở đúng thread và tiếp tục vòng poll, nhưng không lấy thêm record từ partition đã pause.

Điều này khác với việc ứng dụng tự sleep consumer thread hoặc chặn thread quá lâu. Nếu listener thread không quay lại poll trong khoảng thời gian vượt max.poll.interval.ms, consumer có thể bị xem là không còn tiến triển và group sẽ rebalance. Pause container không phải là lời giải cho listener method bị block vô hạn; nó chỉ kiểm soát việc fetch record giữa các lần poll.

Nếu downstream chậm:

1. Đo thời gian xử lý record và thời gian poll.
2. Dùng pause để ngừng fetch thêm khi cần backpressure.
3. Đảm bảo listener hiện tại có thể kết thúc trong giới hạn thời gian.
4. Giám sát lag và tình trạng group.
5. Resume khi downstream đủ khả năng nhận thêm công việc.

Không dùng pause/resume như một cơ chế thay thế timeout, circuit breaker hoặc giới hạn hàng đợi nội bộ.

## 7. pauseImmediate và record đang nằm trong poll batch

Một lần poll có thể trả về nhiều record. Theo hành vi mặc định, yêu cầu pause thường có hiệu lực sau khi container xử lý xong các record đã nhận trong poll trước đó. Điều này có nghĩa sau khi gọi pause, listener có thể vẫn xử lý một số record đã được poll và đang chờ trong batch.

Spring Kafka từ phiên bản 2.9 hỗ trợ thuộc tính pauseImmediate. Khi bật, container áp dụng pause sau record hiện tại thay vì chờ xử lý hết các record còn lại từ poll trước. Các record chưa xử lý trong batch vẫn cần được giữ lại để xử lý sau khi resume; pause không được hiểu là xóa hoặc bỏ qua chúng.

~~~java
factory.getContainerProperties().setPauseImmediate(true);
~~~

Hãy cân nhắc:

- pauseImmediate=false: có thể hoàn tất phần còn lại của poll batch trước khi pause; phù hợp khi muốn giảm số lần gián đoạn giữa batch.
- pauseImmediate=true: phản ứng nhanh hơn với pause request; hữu ích khi cần dừng sớm do backpressure hoặc bảo trì.
- Với batch listener, một batch được giao như một đơn vị; hành vi dừng giữa các record phụ thuộc listener/container mode và phiên bản. Cần kiểm thử đúng loại listener đang dùng.

Pause không hủy một record mà listener đã bắt đầu xử lý. Nếu cần hủy công việc đang chạy, ứng dụng phải có cơ chế cancellation riêng và bảo đảm side effect/offset không bị ghi nhận sai.

## 8. Cấu hình container factory

Container factory định nghĩa cấu hình chung cho listener được tạo từ annotation. Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);

    ContainerProperties properties = factory.getContainerProperties();
    properties.setPollTimeout(1_000L);
    properties.setAckMode(ContainerProperties.AckMode.RECORD);
    properties.setShutdownTimeout(20_000L);
    properties.setPauseImmediate(true);

    return factory;
}
~~~

Các thuộc tính trong ví dụ:

| Thuộc tính | Mục đích |
|---|---|
| concurrency | Số child consumer container được tạo |
| pollTimeout | Thời gian chờ của một lần poll |
| ackMode | Thời điểm container commit offset sau xử lý |
| shutdownTimeout | Thời gian container chờ khi đóng consumer |
| pauseImmediate | Áp dụng pause sau record hiện tại thay vì chờ hết poll batch |

Giá trị cấu hình cần dựa trên thời gian xử lý thực tế và SLO. Không tăng shutdown timeout vô hạn để che listener bị treo; cần có timeout cho database/API và giới hạn thời gian xử lý record.

## 9. Graceful shutdown là gì?

Graceful shutdown là quá trình dừng service sao cho listener có cơ hội hoàn tất công việc đang xử lý, offset được ghi nhận theo đúng semantics và consumer đóng sạch. Mục tiêu là giảm số record phải giao lại, tránh side effect trùng và tránh mất dữ liệu do commit sai.

Một shutdown đột ngột có thể xảy ra khi:

- JVM bị kill ngay lập tức.
- Container runtime hết thời gian termination grace period.
- Pod bị xóa cưỡng bức.
- Process crash do lỗi bộ nhớ hoặc lỗi native.
- Listener bị block và không kết thúc trước shutdown deadline.

Kafka giữ record trong topic theo retention; nếu consumer chưa commit offset sau khi xử lý, record thường sẽ được giao lại khi group tiếp tục. Vì vậy, shutdown không nên commit offset của công việc chưa hoàn tất chỉ để làm group trông như đã xử lý xong.

### Trình tự shutdown khuyến nghị

1. Đưa instance ra khỏi trạng thái nhận request mới nếu service còn phục vụ HTTP/API.
2. Ngừng nhận command mới hoặc ngừng tạo công việc mới vào listener nội bộ.
3. Có thể pause listener để ngăn fetch thêm record và cho phép backlog nằm lại trong Kafka.
4. Chờ listener đang xử lý hoàn tất trong giới hạn timeout.
5. Stop container và chờ callback xác nhận consumer đã đóng.
6. Sau khi listener dừng, đóng database pool, HTTP client và các dependency khác.
7. Kết thúc process trước khi orchestration buộc kill.

Pause là bước tùy theo yêu cầu: nếu muốn listener xử lý hết batch hiện tại rồi dừng, có thể gọi stop trực tiếp theo lifecycle; nếu muốn tạo một khoảng drain có kiểm soát trước khi stop, pause trước rồi chờ công việc hiện tại hoàn tất.

## 10. Dừng container có callback

MessageListenerContainer hỗ trợ stop với callback để biết khi container đã dừng. Đây là cách hữu ích khi shutdown coordinator cần chờ listener kết thúc trước khi đóng dependency.

~~~java
public void stopListenerAndNotify() {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

    if (container == null || !container.isRunning()) {
        shutdownSignal.complete(null);
        return;
    }

    container.stop(() -> {
        log.info("ordersListener stopped");
        shutdownSignal.complete(null);
    });
}
~~~

shutdownSignal là completion primitive do ứng dụng quản lý, ví dụ CompletableFuture. Callback chỉ báo container đã hoàn tất stop; không dùng callback để giả định mọi nghiệp vụ trong hệ thống khác cũng đã hoàn tất nếu chúng không nằm trong listener lifecycle.

Nếu gọi stop từ listener thread hoặc một callback đang được thực thi bởi chính container, cần tránh chờ đồng bộ theo cách gây deadlock. Điều phối shutdown từ thread quản lý ứng dụng và không block consumer thread chờ chính nó dừng.

## 11. Offset và acknowledgment khi shutdown

Offset commit phụ thuộc AckMode, transaction và việc listener đã hoàn tất hay chưa.

| Ack mode | Hành vi liên quan shutdown |
|---|---|
| RECORD | Offset record được commit sau khi listener xử lý thành công theo container policy |
| BATCH | Offset được commit sau khi các record của poll batch xử lý thành công |
| MANUAL | Ứng dụng phải acknowledge đúng thời điểm sau khi side effect hoàn tất |
| MANUAL_IMMEDIATE | Acknowledge có thể yêu cầu commit ngay theo consumer-thread/container semantics |
| Transactional listener | Offset được đưa vào Kafka transaction theo cấu hình transaction; transaction phải commit thành công |

Nếu listener chưa hoàn tất và offset chưa commit, lần chạy sau có thể nhận lại record. Đây là hành vi an toàn của at-least-once nếu consumer idempotent. Nếu database đã cập nhật nhưng offset chưa commit, inbox/unique constraint phải ngăn side effect bị áp dụng hai lần.

Không commit offset trước khi side effect hoàn tất chỉ để giảm thời gian shutdown. Làm vậy biến shutdown thành cửa sổ mất xử lý.

### Xử lý bất đồng bộ

Nếu listener gửi record sang worker pool rồi trả về ngay, container có thể xem listener method đã hoàn tất và commit offset trong khi tác vụ thực tế vẫn đang chạy. Với xử lý bất đồng bộ, cần thiết kế acknowledgment và tracking công việc để offset chỉ tiến qua các record đã hoàn tất liên tục theo từng partition.

Khi shutdown:

- Ngừng submit tác vụ mới.
- Chờ worker pool drain trong timeout giới hạn.
- Chỉ acknowledge các record đã hoàn tất.
- Nếu hết timeout, để record chưa hoàn tất được replay và bảo vệ side effect bằng idempotency.

## 12. Spring Boot và cấu hình shutdown

Spring Boot quản lý ApplicationContext shutdown và các SmartLifecycle bean. Khi nhận tín hiệu dừng hợp lệ, Spring gọi lifecycle stop theo phase. Có thể bật graceful shutdown cho web server để ngừng nhận request mới và chờ request đang chạy:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
  kafka:
    listener:
      ack-mode: record
      concurrency: 3
~~~

server.shutdown: graceful điều khiển web server, không tự đảm bảo toàn bộ Kafka listener và downstream đã drain theo chính sách nghiệp vụ. timeout-per-shutdown-phase giới hạn thời gian Spring chờ từng lifecycle phase; cần phối hợp với shutdown timeout của Kafka container và orchestration termination grace period.

Ví dụ nếu listener có thể xử lý một record tối đa 8 giây, container có nhiều child và downstream cần thêm thời gian đóng, hãy đặt ngân sách shutdown đủ lớn cho drain và close, đồng thời đặt timeout nghiệp vụ hữu hạn. Không lấy một con số cố định áp dụng cho mọi service.

## 13. Graceful shutdown trong Kubernetes

Khi chạy trong Kubernetes, thời gian dừng thực tế bị giới hạn bởi terminationGracePeriodSeconds. Sau khi Pod nhận tín hiệu terminate, kubelet có thể chạy preStop hook, gửi SIGTERM và sau thời hạn sẽ gửi SIGKILL nếu process chưa thoát.

Ví dụ Deployment:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: order-service
      image: example/order-service:1.0
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
~~~

Sleep chỉ là ví dụ về khoảng thời gian orchestration trước khi gửi tín hiệu tiếp theo; production nên dùng readiness/endpoint hoặc hook có chủ đích để ngừng traffic và drain. Không dựa vào sleep đơn thuần để chứng minh listener đã pause hoặc hoàn tất.

Thời gian Kubernetes phải lớn hơn tổng ngân sách cần cho:

- Ngừng nhận request mới và cập nhật readiness.
- Drain listener/record đang xử lý.
- Đóng Kafka consumer và các dependency.
- Biên độ dự phòng cho scheduler, GC và network.

Nếu terminationGracePeriodSeconds ngắn hơn thời gian container cần, Pod có thể bị kill giữa lúc xử lý; record chưa commit sẽ được giao lại. Điều này cần được dự liệu bằng idempotent consumer.

## 14. Pause để backpressure và bảo trì

Pause có thể được dùng khi hệ thống phía sau không còn đủ năng lực nhận thêm công việc:

~~~mermaid
flowchart TD
    A[Downstream latency/error tăng] --> B[Đánh giá backlog và in-flight work]
    B --> C[Pause listener/container hoặc partition]
    C --> D[Kafka tiếp tục giữ record]
    D --> E[Khắc phục database/API]
    E --> F[Kiểm tra capacity và consumer health]
    F --> G[Resume container/partition]
    G --> H[Theo dõi lag giảm và throughput ổn định]
~~~

Khi pause dài:

- Theo dõi consumer lag và retention headroom.
- Bảo đảm group vẫn hoạt động và container tiếp tục poll.
- Không để dữ liệu tồn tại lâu hơn retention nếu cần xử lý đầy đủ.
- Đặt cảnh báo khi pause vượt thời gian dự kiến.
- Có người hoặc automation chịu trách nhiệm resume sau khi điều kiện phục hồi.

Nếu consumer bị pause lâu hơn retention, record cũ có thể bị xóa trước khi được đọc. Pause không kéo dài retention và không tạo bản sao dữ liệu.

## 15. Pause/resume bằng actuator hoặc API vận hành

Một ứng dụng có thể cung cấp endpoint nội bộ hoặc lệnh vận hành để pause/resume listener. Nếu tạo REST endpoint, cần bảo vệ bằng authentication, authorization và audit; không để người dùng bên ngoài tùy ý dừng consumer.

Ví dụ service layer:

~~~java
@Service
public class KafkaListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerOperations(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public ListenerStatus pause(String listenerId) {
        MessageListenerContainer container = require(listenerId);
        container.pause();
        return status(listenerId, container);
    }

    public ListenerStatus resume(String listenerId) {
        MessageListenerContainer container = require(listenerId);
        container.resume();
        return status(listenerId, container);
    }

    private MessageListenerContainer require(String id) {
        MessageListenerContainer container =
            registry.getListenerContainer(id);
        if (container == null) {
            throw new IllegalArgumentException("Unknown listener: " + id);
        }
        return container;
    }

    private ListenerStatus status(
            String id, MessageListenerContainer container) {
        return new ListenerStatus(
            id,
            container.isRunning(),
            container.isPauseRequested(),
            container.isConsumerPaused());
    }
}
~~~

ListenerStatus là DTO do ứng dụng định nghĩa. Endpoint vận hành nên trả về trạng thái yêu cầu và trạng thái đã áp dụng riêng biệt, vì pause/resume có thể cần một khoảng thời gian mới được thực hiện trên consumer thread.

Không nên để endpoint pause/resume nhận tùy ý topic/partition mà không kiểm tra allowlist. Ghi audit ai yêu cầu, listener nào, lý do, thời điểm và kết quả.

## 16. Theo dõi lifecycle và tình trạng listener

Những tín hiệu cần theo dõi:

| Tín hiệu | Ý nghĩa |
|---|---|
| Container running/stopped | Listener có đang hoạt động không |
| Pause requested / consumer paused | Yêu cầu pause đã được áp dụng chưa |
| Assigned partitions | Container đang sở hữu partition nào |
| Consumer lag | Backlog tăng hay giảm |
| Record processing duration | Listener có bị chậm hoặc block không |
| Poll interval / max poll violations | Consumer có nguy cơ rời group do xử lý quá lâu không |
| Rebalance count/duration | Membership có thay đổi liên tục không |
| Commit success/failure | Tiến độ group có được lưu không |
| Shutdown duration | Container có dừng trong ngân sách không |
| In-flight work at shutdown | Có record đang xử lý khi nhận tín hiệu dừng không |

Spring Kafka phát các application event liên quan đến container/consumer lifecycle và idle state tùy phiên bản. Có thể dùng event listener để ghi log hoặc cập nhật trạng thái vận hành; không dùng event bất đồng bộ làm cơ chế duy nhất để bảo đảm commit offset hoặc hoàn tất side effect.

Ví dụ quan sát idle event:

~~~java
@Component
public class KafkaContainerEvents {

    @EventListener
    public void onIdle(ListenerContainerIdleEvent event) {
        log.info(
            "Listener idle: id={}, topicPartitions={}",
            event.getListenerId(),
            event.getTopicPartitions());
    }
}
~~~

Idle event chỉ nói container không nhận record trong khoảng thời gian cấu hình; nó không chứng minh consumer đã pause hoặc group bị lỗi. Cần đối chiếu assignment, lag và trạng thái broker.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Gọi pause nhưng listener vẫn xử lý vài record | Các record đã được poll trước khi pause có hiệu lực | Cân nhắc pauseImmediate, hiểu poll batch và chờ trạng thái consumer paused |
| Gọi resume nhưng chưa thấy record | Consumer chưa áp dụng resume, partition chưa có dữ liệu hoặc group đang rebalance | Kiểm tra trạng thái container, assignment, lag và poll |
| Pause toàn container làm mọi partition ngừng | Pause áp dụng cho tất cả child/partition của listener | Dùng pausePartition nếu chỉ cần cô lập một partition |
| Stop làm group rebalance | Consumer đóng và rời group | Đây là hành vi bình thường; dùng pause nếu chỉ muốn tạm dừng fetch |
| Consumer bị loại khỏi group khi listener xử lý lâu | Poll thread không gọi poll kịp max.poll.interval.ms | Giảm thời gian xử lý, chia batch hoặc thiết kế async có kiểm soát |
| Shutdown hết timeout rồi Pod bị kill | Listener/downstream bị treo hoặc grace period quá ngắn | Đặt timeout nghiệp vụ, tăng ngân sách hợp lý, kiểm tra in-flight work |
| Record được giao lại sau restart | Offset chưa commit trước khi process dừng | Thiết kế at-least-once và idempotent side effect |
| Offset commit nhưng side effect chưa hoàn tất | Ack/commit quá sớm hoặc async listener trả về trước worker | Điều chỉnh ack/transaction và theo dõi công việc thực tế |
| Pause partition không có tác dụng | Partition không thuộc assignment của container hoặc assignment đã đổi | Kiểm tra owner và yêu cầu pause sau rebalance |

## 18. Runbook bảo trì listener

Một quy trình bảo trì ngắn có thể thực hiện như sau:

1. Xác định listener ID, consumer group và các partition đang được giao.
2. Kiểm tra consumer lag, record đang xử lý và downstream health.
3. Đánh dấu instance không nhận request mới nếu cần.
4. Gọi pause toàn container hoặc partition theo phạm vi bảo trì.
5. Xác minh pause request và trạng thái consumer paused.
6. Thực hiện bảo trì database/API hoặc thay đổi cấu hình.
7. Kiểm tra dependency phục hồi và khả năng xử lý backlog.
8. Gọi resume.
9. Theo dõi lag, throughput, commit và rebalance cho tới khi ổn định.
10. Ghi lại thời gian pause, lý do, người thực hiện và kết quả.

Nếu mục tiêu là deploy phiên bản mới, sau khi drain và stop container, để ApplicationContext khởi động lại listener theo cấu hình mới. Không giữ consumer paused vô thời hạn rồi cho rằng service đã được deploy xong.

## 19. Bài thực hành: pause, resume và graceful shutdown

Tạo Spring Boot service với @KafkaListener trên topic orders.events, concurrency bằng hai và group ID riêng trong môi trường lab.

1. Khởi động ứng dụng và xác minh hai consumer instance được tạo.
2. Dùng Kafka CLI xem member/partition assignment của group.
3. Gọi registry để pause listener; xác minh pause requested rồi consumer paused.
4. Gửi thêm record trong lúc pause và xác minh backlog tăng nhưng listener không fetch record mới.
5. Resume listener và quan sát lag giảm.
6. Pause một partition, gửi record vào nhiều partition và xác minh các partition khác vẫn xử lý.
7. Bật pauseImmediate và so sánh số record đang được xử lý sau khi gửi pause request.
8. Gọi stop với callback; xác minh callback chỉ chạy sau khi container đã dừng.
9. Dừng ứng dụng khi một record đang xử lý; thử crash trước commit trong lab và xác minh record được giao lại.
10. Bật inbox/idempotency ở database và lặp lại thử nghiệm để xác minh side effect không bị nhân đôi.
11. Mô phỏng downstream timeout và đo thời gian shutdown so với ngân sách lifecycle/Kubernetes.

Chỉ thử nghiệm trên môi trường lab. Không pause hoặc stop consumer production khi chưa xác định tác động tới lag, retention, SLA và các member còn lại trong group.

## 20. Checklist triển khai

- Đặt ID rõ ràng cho mỗi @KafkaListener cần điều khiển riêng.
- Dùng KafkaListenerEndpointRegistry để điều khiển listener được tạo từ annotation.
- Phân biệt pause/resume với start/stop.
- Kiểm tra trạng thái pause request và consumer paused.
- Dùng pausePartition khi chỉ cần cô lập partition và theo dõi rebalance.
- Hiểu các record đã được poll có thể tiếp tục được xử lý sau pause request.
- Chỉ bật pauseImmediate khi semantics phù hợp với record/batch listener và đã kiểm thử.
- Đặt timeout hữu hạn cho listener và downstream.
- Chọn AckMode/transaction phù hợp; không commit offset trước side effect.
- Đảm bảo consumer idempotent để chịu record được giao lại sau crash.
- Đặt shutdownTimeout và Spring lifecycle timeout theo ngân sách xử lý thực tế.
- Đặt Kubernetes terminationGracePeriodSeconds đủ cho drain và close.
- Đóng listener trước khi đóng database pool hoặc HTTP client mà listener cần.
- Bảo vệ endpoint vận hành pause/resume và ghi audit.
- Theo dõi lag, rebalance, commit, pause duration và shutdown duration.

## 21. Những nhầm lẫn thường gặp

- **Pause giống stop:** pause giữ consumer trong group; stop đóng consumer và có thể kích hoạt rebalance.
- **Pause dừng heartbeat:** container vẫn poll để duy trì group membership trong lúc paused.
- **Pause có hiệu lực ngay lập tức:** các record đã được poll có thể vẫn được xử lý; pauseImmediate thay đổi thời điểm pause có hiệu lực.
- **Resume tạo consumer mới:** resume tiếp tục consumer đang tồn tại; start mới khởi động lifecycle của container đã stopped.
- **Pause partition luôn giữ owner cố định:** rebalance có thể chuyển partition sang consumer khác.
- **Stop bảo đảm mọi record đã xử lý:** record chưa commit có thể được giao lại.
- **Graceful shutdown bảo đảm exactly-once:** nó chỉ điều phối lifecycle; idempotency/transaction vẫn cần để xử lý cửa sổ lỗi.
- **Tăng shutdown timeout sửa listener bị treo:** cần timeout cho downstream và giới hạn xử lý, không chỉ kéo dài thời gian chờ.
- **Spring Boot graceful web shutdown tự dừng Kafka theo đúng nghiệp vụ:** web server và Kafka listener là hai lifecycle cần phối hợp.
- **Pause lâu không ảnh hưởng dữ liệu:** retention vẫn tiếp tục; record có thể hết hạn trước khi consumer resume.

Spring Kafka listener container là nơi quản lý consumer lifecycle, polling, assignment, acknowledgment và shutdown. Pause/resume phù hợp để điều tiết fetch mà vẫn giữ membership; pause theo partition giúp giới hạn phạm vi gián đoạn; stop kết thúc consumer và cho phép group rebalance. Một graceful shutdown đúng cần drain công việc, commit offset theo kết quả thực tế, đóng container trước dependency và dự trù thời gian orchestration. Khi vẫn có khả năng crash hoặc timeout, consumer phải idempotent để record được giao lại mà không tạo side effect trùng.
