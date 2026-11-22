# start, stop và quản lý container

Trong Spring Kafka, `@KafkaListener` không trực tiếp chạy vòng lặp poll. Spring tạo listener endpoint và listener container để quản lý Kafka consumer, poll record, gọi phương thức listener, xử lý acknowledgement và đóng consumer khi dừng. Khi cần bật/tắt một luồng nhận dữ liệu theo trạng thái ứng dụng hoặc điều kiện vận hành, ta quản lý vòng đời của listener container.

Với listener khai báo bằng annotation, thành phần trung tâm là `KafkaListenerEndpointRegistry`. Registry giữ các listener container được tạo từ `@KafkaListener` và cho phép tìm container theo `id` để gọi `start()`, `stop()`, `pause()` hoặc `resume()`. Với container được khai báo trực tiếp thành bean, có thể inject bean và quản lý vòng đời qua Spring.

Cần phân biệt dừng container với tạm dừng tiêu thụ. `stop()` dừng container và đóng consumer theo quy trình lifecycle; consumer rời group, partition có thể được gán cho member khác. `pause()` tạm ngừng nhận record nhưng consumer vẫn tiếp tục poll để duy trì membership. Chọn đúng thao tác giúp tránh rebalance không cần thiết và kiểm soát lưu lượng nhận vào.

Bài học thuộc chương **Listener container** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Listener container trong kiến trúc Spring Kafka

Listener container là thành phần thực thi listener. Nó tạo consumer từ `ConsumerFactory`, gọi `poll()`, chuyển record đến phương thức listener và phối hợp commit offset theo cấu hình.

Hai loại container thường gặp:

| Loại | Vai trò |
| --- | --- |
| `KafkaMessageListenerContainer` | Quản lý một Kafka consumer và luồng xử lý listener tương ứng. |
| `ConcurrentMessageListenerContainer` | Container cha quản lý nhiều child container/consumer theo concurrency. |

Khi dùng `@KafkaListener`, ta thường không tự tạo hai loại container này. `ConcurrentKafkaListenerContainerFactory` tạo container theo cấu hình, còn `KafkaListenerEndpointRegistry` đăng ký và quản lý các container được tạo từ listener endpoint.

Sơ đồ quan hệ:

~~~mermaid
flowchart TD
    A[ApplicationContext] --> B[@KafkaListener endpoint]
    B --> C[KafkaListenerEndpointRegistry]
    C --> D[Listener container]
    D --> E[ConsumerFactory]
    E --> F[Kafka Consumer]
    F --> G[Kafka Broker]
    D --> H[Listener method]
    H --> I[Xử lý nghiệp vụ]
~~~

Registry quản lý container theo listener ID. Container quản lý consumer và vòng poll. Phương thức listener chỉ tập trung xử lý dữ liệu nhận được.

## 2. Đặt id cho @KafkaListener

Muốn tìm và điều khiển một listener cụ thể, hãy khai báo `id` rõ ràng:

~~~java
@Component
public class OrderEventListener {

    @KafkaListener(
        id = "orderListener",
        topics = "order-events",
        groupId = "order-service"
    )
    public void onOrderCreated(OrderCreated event) {
        orderService.handle(event);
    }
}
~~~

`id` là định danh endpoint trong Spring Kafka, được dùng để tra container trong registry. `groupId` là định danh consumer group của Kafka. Hai giá trị này phục vụ hai mục đích khác nhau:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `id` | Định danh listener endpoint/container trong ứng dụng Spring. |
| `groupId` | Tên consumer group lưu offset và điều phối partition trong Kafka. |
| `clientIdPrefix` | Tiền tố client ID của consumer được tạo cho listener, hữu ích khi theo dõi nhiều consumer. |

Không nên dùng groupId để gọi `getListenerContainer()`. Registry tra cứu theo listener ID.

Nếu không khai báo ID tường minh, Spring Kafka có thể tạo ID dựa trên endpoint theo cơ chế của framework. Với listener cần điều khiển runtime, đặt ID ổn định giúp code dễ đọc, dễ kiểm thử và tránh phụ thuộc vào ID sinh tự động.

## 3. KafkaListenerEndpointRegistry

`KafkaListenerEndpointRegistry` là registry quản lý các listener container được tạo bởi các endpoint như `@KafkaListener`. Spring đăng ký registry trong application context khi bật cơ chế xử lý annotation listener.

Có thể inject registry vào service quản trị:

~~~java
@Service
@RequiredArgsConstructor
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public void startOrderListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orderListener");

        if (container != null && !container.isRunning()) {
            container.start();
        }
    }

    public void stopOrderListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("orderListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
~~~

`getListenerContainer(id)` trả về container tương ứng hoặc null nếu không tìm thấy ID. Vì vậy, cần xử lý trường hợp null thay vì giả định listener luôn tồn tại.

Registry cũng cung cấp các API để xem các container đã đăng ký, chẳng hạn `getListenerContainers()`. Khi ứng dụng có nhiều listener, có thể dùng registry để quản lý theo từng ID hoặc quan sát tập container đang chạy.

Không nên giữ một tham chiếu container trước khi listener endpoint được đăng ký nếu code khởi chạy quá sớm. Registry và container được tạo trong quá trình khởi tạo Spring context; thời điểm điều khiển phải bảo đảm endpoint đã được đăng ký.

## 4. Tự động khởi động với autoStartup

Mặc định, listener container được cấu hình để tự khởi động theo lifecycle của Spring. Có thể điều khiển bằng thuộc tính `autoStartup` trên `@KafkaListener`:

~~~java
@KafkaListener(
    id = "orderListener",
    topics = "order-events",
    groupId = "order-service",
    autoStartup = "false"
)
public void onOrderCreated(OrderCreated event) {
    orderService.handle(event);
}
~~~

Khi `autoStartup = "false"`, container không tự chạy trong quá trình khởi động thông thường. Ứng dụng có thể khởi động listener sau khi một điều kiện được đáp ứng: dependency đã sẵn sàng, cấu hình nghiệp vụ đã tải, bước kiểm tra readiness hoàn tất hoặc người vận hành đã bật luồng nhận dữ liệu.

`autoStartup` trong annotation là thuộc tính dạng chuỗi, vì vậy có thể dùng property placeholder. Ví dụ, giá trị có thể được externalize trong application.yml và tham chiếu trong annotation. Cần kiểm tra cách cấu hình này với phiên bản Spring Kafka đang dùng.

~~~yaml
app:
  kafka:
    order-listener:
      auto-startup: false
~~~

~~~java
@KafkaListener(
    id = "orderListener",
    topics = "order-events",
    groupId = "order-service",
    autoStartup = "${app.kafka.order-listener.auto-startup:true}"
)
public void onOrderCreated(OrderCreated event) {
    orderService.handle(event);
}
~~~

Với Spring Boot, cũng có thể cấu hình auto startup ở cấp listener container properties cho các container mặc định. Khi cần điều khiển từng listener riêng, thuộc tính trên annotation hoặc cấu hình container factory phù hợp sẽ rõ ràng hơn. Cần kiểm tra precedence giữa cấu hình mặc định và giá trị đặt trên endpoint theo phiên bản Spring Kafka đang dùng.

## 5. Start container theo yêu cầu

Khi container không tự khởi động, ứng dụng có thể gọi `start()` sau khi tìm nó trong registry:

~~~java
@Service
@RequiredArgsConstructor
public class ListenerControlService {

    private final KafkaListenerEndpointRegistry registry;

    public void start(String listenerId) {
        MessageListenerContainer container =
            registry.getListenerContainer(listenerId);

        if (container == null) {
            throw new IllegalArgumentException(
                "Không tìm thấy listener: " + listenerId
            );
        }

        if (!container.isRunning()) {
            container.start();
        }
    }
}
~~~

`start()` yêu cầu container bắt đầu hoạt động theo lifecycle. Với concurrent container, thao tác trên container cha sẽ quản lý các child container và consumer tương ứng.

Sau khi start, consumer cần kết nối broker, tham gia consumer group, nhận partition assignment và bắt đầu poll. Do đó, lời gọi start không có nghĩa listener lập tức nhận record ngay trong cùng thời điểm. Có thể cần thời gian để hoàn tất group join và rebalance.

Nếu cần xác nhận listener đã sẵn sàng trước khi mở một luồng nghiệp vụ khác, hãy theo dõi trạng thái container và assignment qua event/metric phù hợp thay vì chỉ dựa vào việc phương thức start đã trả về.

## 6. Stop container và callback hoàn tất

`stop()` dừng listener container. Container kết thúc hoạt động consumer theo lifecycle, ngừng nhận record mới, xử lý shutdown theo cấu hình và đóng consumer. Consumer rời group; Kafka có thể thực hiện rebalance để phân phối partition cho các member còn lại.

Có thể gọi stop đồng bộ:

~~~java
container.stop();
~~~

Hoặc dùng callback để biết khi quá trình dừng hoàn tất:

~~~java
container.stop(() ->
    log.info("Order listener đã dừng")
);
~~~

Callback hữu ích khi cần phối hợp các bước tiếp theo sau khi container hoàn tất shutdown. Không nên giả định mọi công việc dừng consumer đã xong ngay khi gọi phương thức stop nếu đang sử dụng overload bất đồng bộ với callback.

Khi stop, cần hiểu ảnh hưởng tới consumer group. Nếu container dừng lâu, partition sẽ được giao cho consumer khác trong group. Khi start lại, consumer tham gia group và nhận assignment mới; nó tiếp tục từ offset đã commit theo chính sách consumer.

## 7. Pause và resume khác stop/start thế nào?

Pause/resume phù hợp khi muốn tạm thời ngừng nhận record nhưng vẫn duy trì consumer trong group.

| Thao tác | Hành vi | Ảnh hưởng group |
| --- | --- | --- |
| `start()` | Khởi động container đã dừng. | Consumer tham gia group và nhận assignment. |
| `stop()` | Dừng container và đóng consumer. | Consumer rời group; có thể gây rebalance. |
| `pause()` | Yêu cầu tạm dừng fetch/dispatch record từ partition. | Consumer vẫn tiếp tục poll để duy trì membership. |
| `resume()` | Tiếp tục nhận record sau khi pause. | Consumer tiếp tục dùng assignment hiện có nếu group không đổi. |

Ví dụ:

~~~java
public void pauseOrderListener() {
    MessageListenerContainer container =
        registry.getListenerContainer("orderListener");

    if (container != null && container.isRunning()) {
        container.pause();
    }
}

public void resumeOrderListener() {
    MessageListenerContainer container =
        registry.getListenerContainer("orderListener");

    if (container != null && container.isRunning()) {
        container.resume();
    }
}
~~~

Pause thường thích hợp khi database downstream đang quá tải hoặc ứng dụng cần điều tiết nhận dữ liệu trong thời gian ngắn. Consumer vẫn poll nhưng không lấy thêm record từ các partition đã pause theo cơ chế container. Nhờ đó, membership có thể được duy trì và tránh rebalance do stop/start liên tục.

Pause không đồng nghĩa listener đã xử lý xong mọi record đang nằm trong batch hoặc đang được dispatch. Cần hiểu thời điểm pause có hiệu lực theo vòng poll và cấu hình container của phiên bản đang dùng.

### 7.1. Kiểm tra trạng thái pause

Container cung cấp các API quan sát trạng thái pause. Tùy phiên bản Spring Kafka, có thể dùng các phương thức như `isPauseRequested()` và `isContainerPaused()` để phân biệt yêu cầu pause đã được đặt với trạng thái consumer thực tế đã pause.

~~~java
MessageListenerContainer container =
    registry.getListenerContainer("orderListener");

if (container != null) {
    log.info(
        "running={}, pauseRequested={}, paused={}",
        container.isRunning(),
        container.isPauseRequested(),
        container.isContainerPaused()
    );
}
~~~

`isPauseRequested()` phản ánh yêu cầu pause. `isContainerPaused()` phản ánh trạng thái pause đã được container áp dụng. Vì pause được phối hợp với vòng poll của consumer, hai trạng thái có thể không đổi cùng một thời điểm.

## 8. Pause/resume theo partition

Ngoài pause toàn container, một số loại container cho phép pause/resume từng topic-partition. Cách này hữu ích khi một partition có vấn đề nhưng các partition khác vẫn có thể tiếp tục xử lý.

~~~java
TopicPartition partition = new TopicPartition("order-events", 2);

MessageListenerContainer container =
    registry.getListenerContainer("orderListener");

if (container != null) {
    container.pausePartition(partition);
}
~~~

Resume partition:

~~~java
if (container != null) {
    container.resumePartition(partition);
}
~~~

API cụ thể và khả năng sử dụng phụ thuộc loại container và phiên bản Spring Kafka. Cần kiểm tra partition có thực sự được gán cho container hay không. Nếu partition không thuộc assignment hiện tại, thao tác pause có thể không có hiệu lực như mong đợi.

Pause partition không chuyển partition sang consumer khác trong cùng group. Nó chỉ tạm dừng xử lý tại consumer đang sở hữu partition đó. Nếu cần chuyển ownership, đó là bài toán rebalance hoặc thay đổi membership/assignment.

## 9. Quản lý nhiều listener bằng registry

Ứng dụng có thể có nhiều listener cho các domain khác nhau:

~~~java
@KafkaListener(
    id = "orderListener",
    topics = "order-events",
    groupId = "order-service"
)
public void onOrder(OrderEvent event) {
    orderService.handle(event);
}

@KafkaListener(
    id = "paymentListener",
    topics = "payment-events",
    groupId = "payment-service"
)
public void onPayment(PaymentEvent event) {
    paymentService.handle(event);
}
~~~

Có thể điều khiển riêng:

~~~java
public void stopPaymentOnly() {
    MessageListenerContainer paymentContainer =
        registry.getListenerContainer("paymentListener");

    if (paymentContainer != null && paymentContainer.isRunning()) {
        paymentContainer.stop();
    }
}
~~~

Dùng ID riêng giúp không ảnh hưởng listener khác. Không nên gọi dừng tất cả container chỉ vì một luồng gặp sự cố nếu các luồng còn lại vẫn hoạt động bình thường.

Nếu cần điều khiển theo nhóm, có thể duyệt danh sách container trong registry và lọc theo quy ước ID hoặc metadata ứng dụng. Nên xây dựng một lớp quản lý rõ ràng thay vì để controller HTTP truy cập registry tùy tiện.

## 10. Lifecycle của Spring và SmartLifecycle

Listener container tham gia lifecycle của Spring. Khi application context khởi động, các thành phần lifecycle được start theo thứ tự phase; khi context dừng, chúng được stop theo thứ tự lifecycle tương ứng.

Các container của Spring Kafka tích hợp cơ chế lifecycle để phối hợp start/stop và callback. Có thể cấu hình phase qua container properties trong trường hợp cần điều phối thứ tự với những thành phần khác.

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setPhase(100);
    return factory;
}
~~~

Giá trị phase chỉ là ví dụ. Cần chọn phase dựa trên thứ tự dependency: listener nên start sau khi các thành phần cần thiết đã sẵn sàng và stop trước khi những dependency mà nó cần bị đóng.

Spring dùng SmartLifecycle để phối hợp start/stop và callback. Với ứng dụng có nhiều thành phần phụ thuộc lẫn nhau, nên hiểu phase và shutdown timeout thay vì tự gọi start/stop ở nhiều nơi không phối hợp.

Không nên lạm dụng phase để thay thế readiness check. Phase điều khiển thứ tự lifecycle; nó không chứng minh database, remote service hoặc Kafka broker đã sẵn sàng cho nghiệp vụ.

## 11. Graceful shutdown khi ứng dụng dừng

Khi application context đóng, Spring dừng listener container theo lifecycle. Container cần kết thúc consumer một cách có trật tự để tránh cắt ngang xử lý đang chạy.

Các yếu tố cần cân nhắc:

- Thời gian tối đa listener xử lý một record hoặc batch.
- Thời gian container được cấp để dừng.
- Thời điểm commit offset.
- Retry/backoff đang diễn ra.
- Consumer có đang tham gia Kafka transaction hay không.
- Dependency downstream có còn hoạt động trong lúc listener dừng không.

Với Spring Boot, có thể cấu hình thời gian graceful shutdown ở cấp ứng dụng:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

`server.shutdown` chủ yếu điều khiển graceful shutdown của web server. `spring.lifecycle.timeout-per-shutdown-phase` đặt giới hạn cho mỗi phase lifecycle của Spring. Đây không phải bảo đảm độc lập rằng mọi listener xử lý sẽ hoàn tất trong 30 giây; cần đối chiếu timeout của container và thời gian xử lý thực tế.

Khi triển khai Kubernetes hoặc nền tảng điều phối khác, termination grace period phải đủ lớn để Spring hoàn tất shutdown. Nếu orchestrator kill process trước khi lifecycle kết thúc, listener có thể bị dừng đột ngột và record chưa commit có thể được đọc lại.

### 11.1. Commit offset trong lúc shutdown

Nếu listener xử lý thành công nhưng offset chưa commit trước khi process dừng, record có thể được đọc lại khi consumer khác tiếp nhận partition. Đây là hành vi thường gặp của at-least-once.

Nếu offset được commit trước khi tác vụ nghiệp vụ hoàn tất, có thể xảy ra mất xử lý khi process dừng. Vì vậy, shutdown cần phối hợp với ack mode, error handler và transaction; không nên chỉ tăng timeout mà bỏ qua semantics commit.

Listener nên xử lý idempotent khi nghiệp vụ có thể nhận lại record. Việc dừng container đúng cách giảm rủi ro nhưng không loại bỏ mọi khả năng duplicate do crash, network failure hoặc rebalance.

## 12. Đăng ký listener động

Trong một số ứng dụng, danh sách listener không biết đầy đủ tại compile time. Spring Kafka có API để đăng ký endpoint/container bằng chương trình thông qua registry và listener container factory.

Đây là trường hợp nâng cao. Trước khi chọn cách này, hãy cân nhắc liệu một listener có thể subscribe nhiều topic hoặc dùng topicPattern hay không. Dynamic endpoint làm tăng độ phức tạp về lifecycle, ID, configuration và quan sát.

Khi đăng ký động, cần bảo đảm:

- Mỗi endpoint có ID duy nhất.
- ConsumerFactory và container factory phù hợp kiểu key/value.
- Subscription/topic được xác định hợp lệ.
- Chính sách auto startup được chọn rõ ràng.
- Container được start/stop theo lifecycle ứng dụng.
- Có cơ chế dừng/xóa container khi cấu hình listener không còn hiệu lực.

Không nên tạo container mới mỗi lần có request đến. Listener container là tài nguyên dài hạn, không phải đối tượng tạm thời cho từng HTTP request.

## 13. Điều khiển listener qua API quản trị

Một số hệ thống cung cấp API nội bộ để vận hành listener, chẳng hạn tạm dừng một consumer khi downstream bảo trì. Nếu xây dựng API này, cần bảo vệ quyền truy cập và giới hạn listener ID được phép điều khiển.

Ví dụ service điều khiển:

~~~java
@Service
@RequiredArgsConstructor
public class ListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public void pause(String id) {
        MessageListenerContainer container = requireContainer(id);
        if (container.isRunning()) {
            container.pause();
        }
    }

    public void resume(String id) {
        MessageListenerContainer container = requireContainer(id);
        if (container.isRunning()) {
            container.resume();
        }
    }

    public void start(String id) {
        MessageListenerContainer container = requireContainer(id);
        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stop(String id) {
        MessageListenerContainer container = requireContainer(id);
        if (container.isRunning()) {
            container.stop();
        }
    }

    private MessageListenerContainer requireContainer(String id) {
        MessageListenerContainer container =
            registry.getListenerContainer(id);

        if (container == null) {
            throw new IllegalArgumentException(
                "Unknown listener id: " + id
            );
        }

        return container;
    }
}
~~~

Service trên minh họa việc gom lifecycle operations vào một nơi. Controller có thể gọi service này sau khi xác thực quyền quản trị. Không nên mở endpoint start/stop không xác thực ra internet hoặc cho phép caller truyền ID tùy ý mà không kiểm tra.

Nên trả trạng thái thực tế của container sau thao tác và ghi audit log: ai thực hiện, listener nào, thời điểm nào, lý do và kết quả. Với thao tác pause, có thể cần theo dõi đến khi container thực sự paused trước khi báo trạng thái hoàn tất.

## 14. Kiểm thử start, stop, pause và resume

Lifecycle behavior nên được kiểm thử ở mức container/integration thay vì chỉ kiểm tra service gọi đúng một method.

Một số tình huống cần xác nhận:

1. Listener có autoStartup=false không nhận record trước khi start.
2. Gọi start làm listener tham gia group và nhận record.
3. Gọi pause khiến listener tạm ngừng nhận record mới theo semantics container.
4. Gọi resume làm listener tiếp tục xử lý.
5. Gọi stop làm container dừng và consumer được đóng.
6. Container có thể start lại sau stop.
7. Dừng context kích hoạt shutdown theo lifecycle.
8. Với concurrency, các child container được quản lý đúng.

Có thể dùng Embedded Kafka hoặc Testcontainers để chạy broker trong integration test. Test nên dùng latch hoặc điều kiện chờ có timeout thay vì sleep cố định.

Ví dụ kiểm tra container chưa chạy khi autoStartup=false:

~~~java
@SpringBootTest
@EmbeddedKafka(topics = "order-events", partitions = 1)
class ListenerLifecycleTest {

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Test
    void listenerCanBeStartedAndStopped() {
        MessageListenerContainer container =
            registry.getListenerContainer("orderListener");

        assertThat(container).isNotNull();
        assertThat(container.isRunning()).isFalse();

        container.start();
        await().atMost(Duration.ofSeconds(10))
            .until(container::isRunning);

        container.stop();
        await().atMost(Duration.ofSeconds(10))
            .until(() -> !container.isRunning());
    }
}
~~~

Ví dụ sử dụng Awaitility để chờ trạng thái. Test thực tế cần cấu hình listener autoStartup=false và có dependency/test setup phù hợp. Trạng thái isRunning không đồng nghĩa partition assignment đã hoàn tất; nếu test cần xác nhận consumer đã sẵn sàng nhận record, hãy chờ assignment hoặc dùng một record kiểm chứng.

## 15. Các lỗi thường gặp khi quản lý container

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| getListenerContainer trả về null | ID không đúng hoặc endpoint chưa được đăng ký | Kiểm tra id trên @KafkaListener và thời điểm gọi registry |
| Gọi start nhưng chưa thấy record | Consumer đang kết nối, join group, rebalance hoặc topic chưa có dữ liệu | Kiểm tra group state, assignment, topic và offset |
| Container tự chạy dù muốn khởi động thủ công | autoStartup vẫn true hoặc cấu hình endpoint override giá trị mặc định | Kiểm tra annotation và listener container factory |
| Stop gây rebalance | Consumer rời group và partition được giao lại | Đây là hành vi bình thường của group membership |
| Pause rồi vẫn thấy listener xử lý thêm record | Pause có thể có hiệu lực tại vòng poll tiếp theo hoặc batch đang xử lý | Kiểm tra trạng thái pause và semantics container/version |
| Pause lâu rồi consumer bị loại khỏi group | Consumer không tiếp tục poll hoặc broker/network không ổn định | Kiểm tra heartbeat, poll loop và log consumer |
| Stop không hoàn tất trước khi process bị kill | Shutdown timeout hoặc termination grace period quá ngắn | Kiểm tra lifecycle timeout, listener duration và orchestrator |
| Start lại nhưng nhận record cũ | Offset chưa commit trước khi dừng | Kiểm tra ack mode, commit và idempotency |
| Điều khiển nhầm listener | Dùng groupId thay vì listener id hoặc ID bị trùng | Đặt listener ID riêng và dùng registry theo ID |
| Tăng concurrency nhưng không tăng throughput | Số partition ít hoặc downstream đã bão hòa | Kiểm tra assignment, partition count và dependency |

## 16. Checklist vận hành listener container

Trước khi đưa cơ chế quản lý container vào production, hãy kiểm tra:

1. Mỗi listener cần điều khiển có ID ổn định và duy nhất.
2. Đã chọn autoStartup phù hợp cho từng listener.
3. Registry được inject ở đúng thời điểm sau khi endpoint đăng ký.
4. Service quản trị xử lý trường hợp không tìm thấy container.
5. Đã phân biệt stop/start với pause/resume.
6. Đã xác định tác động rebalance khi consumer rời group.
7. Đã kiểm tra pause state và thời điểm pause có hiệu lực.
8. Đã cấu hình graceful shutdown và termination grace period phù hợp.
9. Ack mode, retry và transaction tương thích với quy trình shutdown.
10. Có metric/log/audit cho lifecycle operation.
11. API điều khiển listener được bảo vệ quyền truy cập.
12. Integration test xác nhận start, stop, pause, resume và shutdown.

Quản lý listener container là cách kiểm soát vòng đời consumer ở tầng Spring. Registry giúp tìm đúng container theo listener ID; start/stop thay đổi membership và lifecycle của consumer; pause/resume điều tiết nhận dữ liệu trong khi giữ consumer hoạt động. Khi phối hợp đúng với offset, acknowledgement, rebalance và graceful shutdown, ứng dụng có thể vận hành các luồng Kafka linh hoạt mà vẫn giữ được tiến độ xử lý có thể quan sát và phục hồi.

