# Quản lý lifecycle trong ứng dụng

## Mục tiêu của bài học

Trong chương **Dynamic containers**, bài này hướng dẫn quản lý vòng đời (lifecycle) của Kafka listener container trong ứng dụng Spring Kafka. Ứng dụng có thể cần bật hoặc tắt một listener theo cấu hình, tạo consumer khi tenant được kích hoạt, dừng một luồng khi ngừng dịch vụ, hoặc tạm pause consumer khi downstream quá tải.

**SPRING_KAFKA_MESSAGING** tập trung xây dựng ứng dụng gửi và nhận sự kiện Kafka bằng Spring Kafka, KafkaTemplate và @KafkaListener; đồng thời giúp người học hiểu topic, partition, offset, consumer group, serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử. Quản lý lifecycle đúng cách giúp điều khiển consumer theo trạng thái ứng dụng mà vẫn giữ hành vi commit, retry và shutdown có thể dự đoán.

Sau bài học, người học có thể:

- Phân biệt lifecycle của listener container với lifecycle của Spring bean.
- Điều khiển container do `@KafkaListener` tạo bằng `KafkaListenerEndpointRegistry`.
- Dùng `autoStartup` để kiểm soát việc tự khởi động listener.
- Start, stop, pause và resume listener container đúng mục đích.
- Tạo container động từ `ConcurrentKafkaListenerContainerFactory`.
- Quản lý container động bằng một component có lifecycle rõ ràng.
- Chọn subscription theo topic, pattern hoặc partition assignment.
- Xử lý group ID, concurrency và tài nguyên khi có nhiều container.
- Thực hiện graceful shutdown và tránh tạo consumer bị bỏ quên.
- Quan sát trạng thái container và kiểm thử các thao tác lifecycle.

## 1. Listener container có lifecycle riêng

Trong Spring Kafka, `@KafkaListener` không trực tiếp tạo một consumer chạy trong phương thức Java. Spring phát hiện annotation, tạo endpoint và đăng ký listener container để quản lý consumer, poll loop và lời gọi listener.

Một listener container có các trạng thái và thao tác lifecycle như:

- Start: khởi động consumer và bắt đầu nhận record.
- Stop: dừng consumer một cách có kiểm soát.
- Pause: tạm dừng việc nhận record mới trong khi container vẫn tồn tại.
- Resume: tiếp tục nhận record sau khi pause.
- Kiểm tra trạng thái: biết container có đang chạy hoặc đang pause hay không.

Cần phân biệt hai đối tượng:

| Đối tượng | Vai trò |
|---|---|
| Spring bean listener | Chứa phương thức xử lý event |
| Message listener container | Quản lý Kafka consumer và gọi phương thức listener |
| Kafka consumer | Poll record từ broker, tham gia consumer group |
| Endpoint registry | Lưu và quản lý các container được đăng ký qua listener endpoint |

Một bean listener thường là singleton. Dừng container không đồng nghĩa xóa bean listener khỏi Spring ApplicationContext. Ngược lại, bean vẫn tồn tại dù container của nó đang dừng.

## 2. Quản lý container được tạo từ @KafkaListener

Spring Kafka cung cấp `KafkaListenerEndpointRegistry` để quản lý các listener container được tạo từ `@KafkaListener` và endpoint được đăng ký với registry.

Ví dụ khai báo listener có ID:

~~~java
@Service
public class OrderEventListener {

    private final BillingService billingService;

    public OrderEventListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @KafkaListener(
        id = "ordersListener",
        topics = "commerce.order.created",
        groupId = "billing-service"
    )
    public void listen(OrderCreated event) {
        billingService.process(event);
    }
}
~~~

Thuộc tính `id` định danh listener container trong registry. Có thể lấy container theo ID và điều khiển lifecycle:

~~~java
@Service
public class OrderListenerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderListenerControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container == null) {
            throw new IllegalStateException(
                "ordersListener has not been registered"
            );
        }

        if (!container.isRunning()) {
            container.start();
        }
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null && container.isRunning()) {
            container.stop();
        }
    }
}
~~~

`getListenerContainer(id)` trả về container đã đăng ký với registry. Nếu ID sai hoặc endpoint chưa được đăng ký, kết quả có thể là null. Luôn kiểm tra trước khi gọi lifecycle method.

### 2.1. Bật/tắt tự khởi động bằng autoStartup

Mặc định listener container thường được tự khởi động theo lifecycle của Spring. Nếu muốn ứng dụng quyết định thời điểm bắt đầu, đặt `autoStartup` thành false:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "commerce.order.created",
    groupId = "billing-service",
    autoStartup = "false"
)
public void listen(OrderCreated event) {
    billingService.process(event);
}
~~~

Container vẫn được đăng ký trong registry nhưng không tự chạy khi application context khởi động. Ứng dụng có thể gọi `start()` sau khi đã kiểm tra cấu hình hoặc trạng thái nghiệp vụ.

Có thể đặt giá trị `autoStartup` theo môi trường bằng cơ chế placeholder hoặc SpEL mà annotation hỗ trợ. Ví dụ giá trị mặc định là false trong môi trường development và true trong production. Thuộc tính này chỉ điều khiển việc container tự khởi động; nó không quyết định listener bean có được tạo hay không.

### 2.2. Thời điểm gọi start

Không nên lấy container từ registry trong constructor của một bean khác rồi giả định endpoint đã được đăng ký. Listener endpoint được phát hiện và đăng ký trong quá trình khởi tạo application context.

Nếu cần điều khiển sau khi ứng dụng sẵn sàng, có thể dùng `ApplicationReadyEvent`:

~~~java
@Component
public class OrdersListenerStartup {

    private final KafkaListenerEndpointRegistry registry;

    public OrdersListenerStartup(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void startListener() {
        MessageListenerContainer container =
            registry.getListenerContainer("ordersListener");

        if (container != null && !container.isRunning()) {
            container.start();
        }
    }
}
~~~

Chỉ dùng cách này khi listener cần bắt đầu sau một điều kiện startup. Nếu không có điều kiện đặc biệt, để Spring quản lý auto startup thường đơn giản hơn.

## 3. Start, stop, pause và resume khác nhau thế nào?

Các thao tác này có mục đích khác nhau:

| Thao tác | Ý nghĩa | Khi nên dùng |
|---|---|---|
| `start()` | Khởi động container | Bật listener đang dừng |
| `stop()` | Dừng container | Tắt listener hoặc shutdown |
| `pause()` | Yêu cầu consumer tạm ngừng nhận record mới | Downstream quá tải, cần giảm tải tạm thời |
| `resume()` | Tiếp tục nhận record sau pause | Downstream đã phục hồi |
| `isRunning()` | Kiểm tra container có chạy | Health/status endpoint hoặc vận hành |
| `isContainerPaused()` | Kiểm tra trạng thái pause của container | Theo dõi flow control |

Pause không giống stop. Khi pause, container vẫn tồn tại và consumer vẫn thuộc lifecycle của nó; việc nhận record mới được tạm dừng theo cơ chế container. Khi resume, consumer tiếp tục hoạt động mà không cần tạo lại container.

Ví dụ:

~~~java
public void pauseOrdersListener() {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

    if (container != null && container.isRunning()) {
        container.pause();
    }
}

public void resumeOrdersListener() {
    MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

    if (container != null && container.isRunning()) {
        container.resume();
    }
}
~~~

Pause thường phù hợp với load shedding hoặc bảo trì ngắn. Stop phù hợp khi muốn chấm dứt consumer container. Không nên stop/start liên tục để thay thế cơ chế pause/resume nếu mục tiêu chỉ là tạm giảm tải.

## 4. Điều gì xảy ra khi container dừng?

Khi gọi stop, listener container dừng việc poll và kết thúc consumer theo lifecycle của Spring Kafka. Việc xử lý record đang chạy và commit offset phụ thuộc acknowledgment mode, transaction, trạng thái xử lý và phiên bản thư viện.

Các điểm cần hiểu:

- Record đã xử lý và được commit sẽ không được giao lại theo offset đã commit.
- Record chưa commit có thể được giao lại khi consumer khởi động lại hoặc partition được gán cho consumer khác.
- Side effect đã ghi vào database trước khi offset commit có thể bị thực hiện lại nếu record được giao lại.
- Nếu listener đang xử lý khi shutdown, cần cho container đủ thời gian hoàn tất theo chính sách dừng.
- Không giả định stop đồng nghĩa mọi công việc bất đồng bộ do listener khởi tạo đã hoàn tất.

Vì vậy, listener cần idempotent khi nghiệp vụ có side effect. Với công việc bất đồng bộ, phải đợi task hoàn tất hoặc có cơ chế acknowledgment/offset riêng được thiết kế rõ ràng.

## 5. Quản lý tất cả listener qua KafkaListenerEndpointRegistry

Registry có thể lấy danh sách ID và các container đã đăng ký:

~~~java
@Service
public class KafkaListenerOperations {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerOperations(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public Map<String, Boolean> listenerStatuses() {
        Map<String, Boolean> statuses = new LinkedHashMap<>();

        for (MessageListenerContainer container :
                registry.getListenerContainers()) {
            statuses.put(
                container.getListenerId(),
                container.isRunning()
            );
        }

        return statuses;
    }

    public void stopAllRegisteredListeners() {
        registry.stop();
    }

    public void startAllRegisteredListeners() {
        registry.start();
    }
}
~~~

`getListenerContainers()` trả về các container mà registry quản lý. Các container được tạo trực tiếp từ factory và không đăng ký với registry sẽ không tự xuất hiện trong danh sách này.

Dùng thao tác start/stop toàn registry khi cần điều khiển cả nhóm listener. Nếu chỉ muốn tắt một luồng, hãy lấy container theo ID thay vì dừng tất cả.

## 6. Tạo listener container động bằng factory

Có trường hợp danh sách topic hoặc tenant chỉ biết được khi ứng dụng đang chạy. Khi đó, có thể tạo container từ `ConcurrentKafkaListenerContainerFactory`.

Factory cung cấp cấu hình chung như:

- ConsumerFactory và deserializer.
- Concurrency.
- Common error handler.
- Record interceptor.
- Container properties mặc định.
- Các tùy chọn khác đã cấu hình trên factory.

Ví dụ tạo container cho một topic:

~~~java
ConcurrentMessageListenerContainer<String, OrderCreated> container =
    listenerContainerFactory.createContainer(
        "commerce.order.created"
    );

container.getContainerProperties()
    .setGroupId("billing-service");

container.setupMessageListener(
    (MessageListener<String, OrderCreated>) record ->
        billingService.process(record.value())
);

container.start();
~~~

Trình tự quan trọng:

1. Tạo container từ factory với topic hoặc partition cần consume.
2. Thiết lập group ID nếu cần ghi đè cấu hình mặc định.
3. Gắn message listener bằng `setupMessageListener`.
4. Cấu hình các thuộc tính riêng của container.
5. Start container.
6. Lưu tham chiếu để sau này pause, resume hoặc stop.

Container tạo trực tiếp từ factory cần được ứng dụng quản lý lifecycle. Không mặc định cho rằng nó đã được đăng ký trong `KafkaListenerEndpointRegistry` hoặc tự động được Spring quản lý như một bean riêng.

## 7. Quản lý container động bằng một component

Không nên tạo container trong controller rồi bỏ mất tham chiếu. Hãy có một component chịu trách nhiệm tạo, lưu, start và stop các container.

Ví dụ sau minh họa manager quản lý một container cho mỗi tenant. Trong hệ thống thực tế, tên topic và group ID phải được xác thực theo quy ước của platform.

~~~java
@Component
public class TenantConsumerManager implements SmartLifecycle {

    private final ConcurrentKafkaListenerContainerFactory<String, TenantEvent>
        containerFactory;

    private final TenantEventHandler eventHandler;

    private final Map<String,
        ConcurrentMessageListenerContainer<String, TenantEvent>> containers =
            new HashMap<>();

    private volatile boolean running;

    public TenantConsumerManager(
            ConcurrentKafkaListenerContainerFactory<String, TenantEvent>
                containerFactory,
            TenantEventHandler eventHandler) {
        this.containerFactory = containerFactory;
        this.eventHandler = eventHandler;
    }

    public synchronized void startTenant(String tenantId) {
        if (!running) {
            throw new IllegalStateException(
                "TenantConsumerManager is not running"
            );
        }

        var existing = containers.get(tenantId);
        if (existing != null) {
            if (!existing.isRunning()) {
                existing.start();
            }
            return;
        }

        String topic = topicFor(tenantId);

        var container = containerFactory.createContainer(topic);
        container.setBeanName("tenant-" + tenantId);
        container.getContainerProperties()
            .setGroupId(groupIdFor(tenantId));

        container.setupMessageListener(
            (MessageListener<String, TenantEvent>) record ->
                eventHandler.handle(tenantId, record.value())
        );

        try {
            container.start();
            containers.put(tenantId, container);
        } catch (RuntimeException exception) {
            container.stop();
            throw exception;
        }
    }

    public synchronized void stopTenant(String tenantId) {
        var container = containers.get(tenantId);

        if (container != null) {
            container.stop();
            containers.remove(tenantId, container);
        }
    }

    @Override
    public void start() {
        running = true;
    }

    @Override
    public synchronized void stop() {
        RuntimeException failure = null;

        for (var entry : new ArrayList<>(containers.entrySet())) {
            try {
                entry.getValue().stop();
                containers.remove(entry.getKey(), entry.getValue());
            } catch (RuntimeException exception) {
                if (failure == null) {
                    failure = new IllegalStateException(
                        "One or more tenant containers could not be stopped",
                        exception
                    );
                } else {
                    failure.addSuppressed(exception);
                }
            }
        }

        running = false;

        if (failure != null) {
            throw failure;
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }

    private String topicFor(String tenantId) {
        return "tenant." + tenantId + ".events";
    }

    private String groupIdFor(String tenantId) {
        return "tenant-event-processor-" + tenantId;
    }
}
~~~

Manager này thể hiện các nguyên tắc:

- Dùng map để giữ tham chiếu tới từng container.
- Đồng bộ thao tác tạo/xóa để tránh tạo hai container cho cùng tenant trong cùng process.
- Gắn listener trước khi start.
- Start container mới và lưu lại để quản lý.
- Stop container trước khi xóa trạng thái quản lý.
- Dừng toàn bộ container con khi Spring gọi lifecycle stop.

Đây là skeleton quản lý lifecycle. Cần bổ sung validation tenant ID, giới hạn số container, logging, metrics và chính sách xử lý lỗi phù hợp với ứng dụng thực tế.
Trong ví dụ, `isRunning()` phản ánh manager đã tham gia lifecycle của Spring; nó không khẳng định mọi container con đều đang khỏe. Hãy kiểm tra trạng thái từng container và ghi nhận các container stop thất bại. Phương thức `stop()` cố gắng dừng các container còn lại ngay cả khi một container ném exception, đồng thời giữ tham chiếu tới container chưa dừng thành công để có thể quan sát và xử lý.

### 7.1. Vì sao dùng SmartLifecycle?

`SmartLifecycle` cho phép một component tham gia vòng đời start/stop của Spring ApplicationContext. Manager có thể dừng các container con khi ứng dụng shutdown.

`getPhase()` quyết định thứ tự start/stop tương đối giữa các component có lifecycle. Component phase thấp thường được start trước và stop sau; component phase cao được start sau và stop trước. Chọn phase dựa trên dependency thực tế của ứng dụng.

Nếu manager chỉ tạo container theo yêu cầu runtime và không cần tham gia lifecycle, có thể dùng `DisposableBean` hoặc `@PreDestroy` để dọn dẹp. Dù chọn cách nào, phải bảo đảm mọi container tạo thủ công đều được stop khi ứng dụng dừng.

## 8. Chọn subscription: topic, pattern hay partition assignment

Factory có thể tạo container theo nhiều kiểu subscription.

### 8.1. Subscribe một hoặc nhiều topic

~~~java
var container = containerFactory.createContainer(
    "commerce.order.created",
    "commerce.order.cancelled"
);
~~~

Consumer subscribe các topic đã khai báo và tham gia cơ chế group assignment.

Phù hợp khi tập topic được biết trước hoặc thay đổi theo cấu hình.

### 8.2. Subscribe theo topic pattern

Nếu topic được tạo động theo quy tắc tên, có thể subscribe bằng regex:

~~~java
var container = containerFactory.createContainer(
    Pattern.compile("^tenant\\..*\\.events$")
);
~~~

Consumer sẽ phát hiện topic phù hợp với pattern theo cơ chế metadata refresh của Kafka client. Cách này có thể giảm nhu cầu tạo một container cho mỗi topic khi các topic có cùng schema và cùng cách xử lý.

Cần kiểm soát regex và quyền truy cập topic. Pattern quá rộng có thể khiến consumer vô tình subscribe các topic không thuộc phạm vi nghiệp vụ.

### 8.3. Gán partition cụ thể

Nếu ứng dụng cần chỉ định chính xác partition, có thể tạo container bằng `TopicPartitionOffset`:

~~~java
var container = containerFactory.createContainer(
    new TopicPartitionOffset("commerce.order.created", 0)
);
~~~

Đây là kiểu assignment tường minh. Ứng dụng chịu trách nhiệm phân phối partition giữa các container và xử lý thay đổi topology. Nó khác với subscribe theo topic để Kafka group coordinator tự phân phối partition.

Không tự tạo nhiều consumer cùng assign một partition nếu chưa có thiết kế ownership rõ ràng. Hai consumer độc lập có thể cùng đọc một partition và gây xử lý trùng.

## 9. Group ID và concurrency của container động

Mỗi container có thể dùng group ID riêng hoặc tham gia cùng một logical consumer group tùy mục tiêu.

| Mục tiêu | Group ID |
|---|---|
| Nhiều instance cùng xử lý một luồng topic và chia partition | Cùng group ID |
| Hai service độc lập đều cần nhận toàn bộ event | Group ID khác nhau |
| Mỗi tenant là một luồng xử lý độc lập | Group ID theo tenant |
| Nhiều container trong một JVM cùng scale một subscription | Thiết kế group/subscription thống nhất và kiểm tra assignment |

Không nên tạo group ID ngẫu nhiên mỗi lần restart nếu muốn tiếp tục từ committed offsets trước đó. Group ID ổn định giúp consumer tiếp tục tiến trình đã lưu.

Concurrency được cấu hình trên factory hoặc container. Số consumer hữu ích bị giới hạn bởi số partition được gán. Ví dụ topic có 4 partition, concurrency 8 không tạo ra 8 consumer cùng xử lý dữ liệu của topic đó; một số consumer có thể không được gán partition.

Khi tạo nhiều container động, tổng consumer thực tế là tổng concurrency của tất cả container. Hãy giới hạn số container và số consumer để không vượt tài nguyên broker, network, thread và database.

## 10. Start/stop động có tính idempotent

API quản lý lifecycle có thể được gọi lặp lại do retry của HTTP request, scheduler hoặc event cấu hình. Vì vậy, thao tác nên có tính idempotent:

- Start một container đang chạy: không tạo thêm container thứ hai.
- Start một container đã tồn tại nhưng đang dừng: khởi động lại container đó.
- Stop một container đã dừng hoặc không tồn tại: trả về kết quả phù hợp mà không gây lỗi ngoài ý muốn.
- Tạo container thất bại: không để lại entry giả trong registry nội bộ.
- Stop thất bại: ghi nhận lỗi và giữ khả năng quan sát để xử lý tiếp.

Ví dụ manager ở phần trước dùng `synchronized` để bảo vệ map trong một JVM. Nếu nhiều replica cùng nhận lệnh tạo consumer, đồng bộ trong JVM không đủ để bảo đảm chỉ một replica tạo container. Cần một cơ chế điều phối bên ngoài nếu ownership phải duy nhất trên toàn hệ thống.

Không dùng local map như nguồn sự thật cho trạng thái tenant nếu nhiều instance có thể cùng quản lý. Có thể lưu cấu hình desired state trong database/config service và để mỗi instance reconcile theo thiết kế.

## 11. Pause/resume để điều tiết tải

Nếu downstream quá tải tạm thời, pause container có thể giúp ngừng nhận thêm record trong khi giữ container sống.

Ví dụ:

~~~java
public void pauseTenant(String tenantId) {
    var container = containers.get(tenantId);

    if (container != null && container.isRunning()) {
        container.pause();
    }
}

public void resumeTenant(String tenantId) {
    var container = containers.get(tenantId);

    if (container != null && container.isRunning()) {
        container.resume();
    }
}
~~~

Trong manager thực tế, hai phương thức này cần dùng cùng cơ chế đồng bộ hoặc concurrent map như các thao tác start/stop.

Pause có thể hữu ích khi:

- Database đang bảo trì.
- Downstream đang bị rate limit.
- Cần tạm dừng một tenant.
- Đang thay đổi cấu hình và muốn ngừng nhận record mới.

Pause không xóa record khỏi Kafka và cũng không làm consumer group biến mất. Record tiếp tục tích lũy trong topic và consumer lag có thể tăng. Hãy đặt ngưỡng cảnh báo và có kế hoạch resume.

## 12. Graceful shutdown và thời gian dừng

Ứng dụng Spring thường dừng listener container trong quá trình đóng application context. Với container tạo thủ công, manager phải bảo đảm stop tất cả container con.

Một quy trình shutdown nên:

1. Ngừng nhận yêu cầu tạo container mới.
2. Dừng hoặc pause các container theo chính sách.
3. Cho phép xử lý đang chạy hoàn tất trong thời gian được cấp.
4. Để container áp dụng acknowledgment/commit semantics đã cấu hình.
5. Đóng consumer và producer liên quan.
6. Ghi log container nào dừng thành công hoặc thất bại.

Container properties có thể cấu hình shutdown timeout:

~~~java
container.getContainerProperties()
    .setShutdownTimeout(15_000L);
~~~

Thời gian cụ thể phải phù hợp với thời gian xử lý record, transaction và shutdown budget của ứng dụng. Không tăng timeout vô hạn để che giấu listener bị treo.

Nếu shutdown bị ép dừng trước khi commit, record có thể được giao lại. Đây là lý do idempotency và xử lý duplicate vẫn cần thiết dù đã có graceful shutdown.

## 13. Lifecycle event và quan sát trạng thái

Spring Kafka phát ra các application event liên quan tới consumer/container lifecycle. Có thể dùng event listener để ghi log hoặc cập nhật trạng thái vận hành.

Ví dụ theo dõi consumer stopped:

~~~java
@Component
public class KafkaContainerEvents {

    private static final Logger log =
        LoggerFactory.getLogger(KafkaContainerEvents.class);

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {
        log.info("Kafka consumer stopped: {}", event);
    }

    @EventListener
    public void onContainerStopped(ContainerStoppedEvent event) {
        log.info("Kafka container stopped: {}", event);
    }
}
~~~

Tùy loại container và phiên bản, có thể quan sát thêm sự kiện idle, partition assigned/revoked, pause/resume hoặc consumer không phản hồi. Event có thể được phát cho child container/consumer; tránh giả định mỗi event tương ứng một listener endpoint duy nhất.

Các thông tin nên theo dõi:

- Listener ID hoặc bean/container name.
- Topic và partition được gán.
- Group ID.
- Container running/paused.
- Số consumer thread.
- Consumer lag.
- Số lần start/stop.
- Lỗi startup/shutdown.
- Thời gian xử lý record và retry rate.

Không chỉ kiểm tra `isRunning()`. Một container đang running vẫn có thể chưa được gán partition, bị pause hoặc không tiến triển do broker/downstream.

## 14. Phân biệt stop, pause và thay đổi subscription

Ba hành động này tác động khác nhau:

| Nhu cầu | Cách làm |
|---|---|
| Tạm ngừng nhận record nhưng sẽ tiếp tục | Pause/resume |
| Ngừng consumer hoàn toàn | Stop |
| Đổi tập topic | Stop container cũ, tạo container với subscription mới hoặc dùng pattern phù hợp |
| Đổi group ID | Tạo lại consumer/container với group ID mới |
| Chuyển partition ownership | Dùng group rebalance hoặc assignment strategy có kiểm soát |
| Tạm dừng một partition | Pause/resume partition nếu container API và thiết kế hỗ trợ |

Không thay đổi group ID hoặc subscription đang chạy bằng cách sửa một field cấu hình rồi kỳ vọng consumer tự chuyển đổi. Các thay đổi này thường cần tạo lại container hoặc dùng API được hỗ trợ rõ ràng.

## 15. Bảo vệ API điều khiển lifecycle

Nếu cung cấp endpoint HTTP để start/stop listener, endpoint đó có thể ảnh hưởng trực tiếp tới việc xử lý event. Cần bảo vệ như một thao tác quản trị.

Ví dụ controller chỉ gọi manager:

~~~java
@RestController
@RequestMapping("/admin/kafka/consumers")
public class ConsumerAdminController {

    private final TenantConsumerManager manager;

    public ConsumerAdminController(TenantConsumerManager manager) {
        this.manager = manager;
    }

    @PostMapping("/{tenantId}/start")
    public ResponseEntity<Void> start(@PathVariable String tenantId) {
        manager.startTenant(tenantId);
        return ResponseEntity.accepted().build();
    }

    @PostMapping("/{tenantId}/stop")
    public ResponseEntity<Void> stop(@PathVariable String tenantId) {
        manager.stopTenant(tenantId);
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong production:

- Xác thực và phân quyền admin.
- Validate tenant ID và tên topic theo allowlist.
- Ghi audit ai đã start/stop và thời điểm nào.
- Rate limit thao tác để tránh tạo/hủy consumer liên tục.
- Trả trạng thái thực tế thay vì chỉ phản ánh request đã được nhận.
- Không cho người dùng tùy ý truyền regex hoặc topic name để subscribe.
- Giới hạn số container động tối đa.

## 16. Kiểm thử lifecycle của listener

Nên kiểm thử cả container annotation-managed và container tạo động.

### 16.1. Kiểm thử @KafkaListener với registry

Khai báo listener `autoStartup = "false"`, sau đó:

1. Lấy container bằng listener ID.
2. Xác nhận container chưa running.
3. Gọi start.
4. Gửi record và xác nhận listener nhận được.
5. Gọi stop.
6. Xác nhận container dừng.
7. Khởi động lại và kiểm tra hành vi tiếp tục theo committed offset.

Dùng EmbeddedKafka hoặc Testcontainers để kiểm tra với broker thật. Không chỉ mock registry vì cần xác nhận consumer lifecycle thực tế.

### 16.2. Kiểm thử container động

Với manager:

1. Gọi start cho một tenant.
2. Xác nhận container được tạo và chạy.
3. Gọi start lần nữa và xác nhận không tạo container thứ hai.
4. Gửi record vào topic tenant và xác nhận handler nhận event.
5. Pause container và quan sát việc nhận record mới.
6. Resume và xác nhận xử lý tiếp tục.
7. Stop tenant và xác nhận container dừng.
8. Stop tenant lần nữa và xác nhận thao tác an toàn.
9. Dừng application context và xác nhận mọi container con được đóng.

Đồng bộ test bằng latch hoặc Awaitility. Tránh dùng `Thread.sleep()` cố định để suy đoán consumer đã subscribe hoặc nhận partition.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `getListenerContainer` trả null | Sai ID hoặc endpoint chưa đăng ký | Kiểm tra `id` và thời điểm gọi |
| Listener không tự chạy | `autoStartup=false` | Gọi start sau khi endpoint đã đăng ký |
| Container tạo động không nhận record | Chưa gắn listener hoặc subscribe sai topic | Gọi `setupMessageListener` trước start và kiểm tra subscription |
| Không dừng được consumer | Container không được lưu/quản lý | Theo dõi container trong manager |
| Start lặp tạo nhiều consumer | Không kiểm tra container đã tồn tại | Làm thao tác start idempotent |
| Consumer không có partition | Concurrency vượt partition hoặc group assignment | Kiểm tra partition và group membership |
| Record xử lý lại sau restart | Offset chưa commit trước shutdown | Thiết kế idempotency và ack phù hợp |
| Pause nhưng lag tăng | Consumer ngừng nhận record mới | Theo dõi lag và có kế hoạch resume |
| Container động tồn tại sau shutdown | Manager không stop container con | Tham gia SmartLifecycle hoặc cleanup |
| Hai replica cùng tạo consumer ngoài ý muốn | Chỉ đồng bộ trong JVM | Dùng desired state/coordination bên ngoài |
| Pattern subscribe quá nhiều topic | Regex quá rộng | Giới hạn pattern và ACL |
| Thay group ID nhưng offset không như mong đợi | Group ID mới có committed offset riêng | Kiểm tra reset/offset policy |

## 18. Checklist trước khi đưa dynamic container vào production

- [ ] Listener annotation có ID ổn định?
- [ ] Có dùng `autoStartup` khi cần điều khiển thời điểm start?
- [ ] Chỉ gọi registry sau khi endpoint đã đăng ký?
- [ ] Phân biệt container trong registry với container tạo trực tiếp từ factory?
- [ ] Container động đã được lưu để quản lý lifecycle?
- [ ] Listener được gắn trước khi container start?
- [ ] Group ID ổn định và đúng mô hình chia sẻ partition?
- [ ] Số container và concurrency có giới hạn?
- [ ] Topic/pattern được validate và có allowlist?
- [ ] Pause/resume được dùng cho tạm ngừng, stop cho dừng hẳn?
- [ ] Container con được stop khi application shutdown?
- [ ] Shutdown timeout phù hợp với thời gian xử lý?
- [ ] Đã đánh giá khả năng record được giao lại sau shutdown?
- [ ] Có metrics cho running, paused, assigned partitions và lag?
- [ ] Đã kiểm thử start/stop lặp, pause/resume, rebalance và shutdown?

## Kết luận

Spring Kafka cung cấp `KafkaListenerEndpointRegistry` để điều khiển các container được tạo từ `@KafkaListener`. Dùng listener ID để lấy container, kết hợp `autoStartup`, `start()` và `stop()` khi cần bật/tắt listener theo trạng thái ứng dụng. Với topic hoặc tenant chỉ biết lúc runtime, có thể tạo container từ `ConcurrentKafkaListenerContainerFactory`, gắn listener rồi tự quản lý tham chiếu và lifecycle.

Một container tạo trực tiếp từ factory cần được manager theo dõi và dừng khi ứng dụng shutdown. Hãy phân biệt pause với stop, chọn group ID và concurrency theo partition topology, giới hạn số container động, bảo vệ API quản trị và thiết kế idempotency vì record chưa commit có thể được giao lại. Kiểm thử lifecycle với Kafka broker thực tế giúp xác nhận consumer được start, pause, resume và stop đúng như ứng dụng mong đợi.
