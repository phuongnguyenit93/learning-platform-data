# Tạo listener container bằng code

Spring Kafka thường tạo listener container từ phương thức có `@KafkaListener`. Tuy nhiên, có những hệ thống chỉ biết topic cần đọc khi ứng dụng đang chạy: tenant mới được kích hoạt, cấu hình subscription được cập nhật hoặc một luồng dữ liệu chỉ được mở trong một khoảng thời gian. Trong các trường hợp đó, ứng dụng có thể tạo và quản lý listener container trực tiếp bằng code.

Cách phổ biến là dùng `ConcurrentKafkaListenerContainerFactory` để tạo `ConcurrentMessageListenerContainer`, cấu hình topic, group ID, listener và các thuộc tính container, sau đó gọi `start()`. Khi không còn nhu cầu, ứng dụng gọi `stop()` và giải phóng container. Việc tạo container động cũng đồng nghĩa ứng dụng phải chịu trách nhiệm về lifecycle, định danh, giới hạn tài nguyên và xử lý lỗi khi khởi động hoặc dừng.

Bài học thuộc chương **Dynamic containers** của module **SPRING_KAFKA_MESSAGING**, tập trung vào cách tạo listener container bằng code, phân biệt subscription theo topic với assignment partition tường minh và quản lý các container động an toàn trong Spring Kafka.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích vai trò của listener container và container factory.
- Tạo `ConcurrentMessageListenerContainer` bằng `createContainer()`.
- Cấu hình `ContainerProperties`, group ID, AckMode và message listener.
- Tạo container subscription theo topic hoặc assignment theo partition.
- Bật concurrency phù hợp với số partition và năng lực xử lý.
- Khởi động, dừng và quản lý lifecycle container khi ứng dụng đang chạy.
- Phân biệt container tạo trực tiếp với container được quản lý bởi `KafkaListenerEndpointRegistry`.
- Hiểu offset, group membership và rebalance khi thêm hoặc bỏ container.
- Tránh tạo container trùng lặp, rò rỉ thread và kết nối.
- Kiểm thử dynamic start/stop, assignment và xử lý shutdown.

## 1. Listener container được tạo từ đâu?

Với `@KafkaListener`, Spring xử lý annotation thành listener endpoint rồi tạo container để poll record và gọi listener. Container factory cung cấp ConsumerFactory cùng cấu hình chung như concurrency, error handler, converter và các thuộc tính container.

~~~mermaid
flowchart TD
    A["@KafkaListener endpoint"] --> B["KafkaListenerContainerFactory"]
    B --> C["Listener container"]
    C --> D["KafkaConsumer"]
    D --> E["Poll records"]
    E --> F["Invoke listener"]
~~~

Khi tạo container bằng code, ứng dụng chủ động gọi factory thay vì chờ Spring xử lý annotation. Factory vẫn giúp tái sử dụng cấu hình consumer và các thiết lập container đã được khai báo.

Có thể dùng cách này khi:

- Topic cần subscribe phụ thuộc cấu hình runtime.
- Một tenant hoặc khách hàng mới được kích hoạt.
- Cần mở/đóng consumer theo trạng thái một workflow.
- Ứng dụng quản lý nhiều luồng subscription có vòng đời riêng.
- Muốn gán một tập partition cụ thể cho một container.

Không nên tạo container động chỉ để thay thế một listener tĩnh đơn giản. Mỗi container bổ sung có thể tạo consumer, thread, kết nối broker và chi phí group coordination.

## 2. Tạo container từ ConcurrentKafkaListenerContainerFactory

`ConcurrentKafkaListenerContainerFactory` có thể tạo container theo danh sách topic. Ví dụ:

~~~java
ConcurrentMessageListenerContainer<String, OrderCreatedEvent> container =
        factory.createContainer("orders.created");
~~~

Container được tạo nhưng chưa nhất thiết bắt đầu poll ngay. Ứng dụng cần cấu hình listener và các thuộc tính cần thiết trước khi gọi `start()`.

Factory thường được cấu hình thành bean Spring để dùng chung ConsumerFactory và chính sách xử lý:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
dynamicOrderFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        CommonErrorHandler commonErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(commonErrorHandler);
    factory.setConcurrency(2);

    return factory;
}
~~~

Factory là nơi tập trung cấu hình dùng chung. Mỗi container được tạo từ factory có thể nhận thêm cấu hình riêng trước khi khởi động.

API và các tùy chọn của factory có thể thay đổi theo phiên bản Spring Kafka. Hãy sử dụng đúng phiên bản dependency trong dự án.

## 3. Cấu hình ContainerProperties

Container có các thuộc tính điều khiển subscription, group, acknowledgment và listener callback. Các thiết lập thường cần xem xét:

| Thuộc tính | Vai trò |
|---|---|
| `groupId` | Consumer group của container khi subscribe topic. |
| `ackMode` | Cách container xác nhận offset. |
| `messageListener` | Callback nhận record hoặc batch record. |
| `pollTimeout` | Thời gian chờ trong poll. |
| `clientId` | Định danh client phục vụ quan sát và phân biệt consumer. |
| `shutdownTimeout` | Thời gian chờ khi container dừng. |

Ví dụ cấu hình trước khi start:

~~~java
ConcurrentMessageListenerContainer<String, OrderCreatedEvent> container =
        factory.createContainer("orders.created");

ContainerProperties properties = container.getContainerProperties();

properties.setGroupId("orders-dynamic-fulfillment");
properties.setAckMode(ContainerProperties.AckMode.RECORD);
properties.setPollTimeout(2_000L);
~~~

Nếu ConsumerFactory đã có group ID, cấu hình group ID ở ContainerProperties có thể được dùng để ghi đè cho container cụ thể. Hãy kiểm tra group ID hiệu lực để tránh nhiều container vô tình tham gia cùng group ngoài ý muốn.

## 4. Gắn MessageListener bằng code

Khi tạo container trực tiếp, ứng dụng có thể gắn một implementation của `MessageListener<K, V>`. Listener nhận `ConsumerRecord` và xử lý payload cùng metadata.

~~~java
properties.setMessageListener(
        (MessageListener<String, OrderCreatedEvent>) record -> {
            orderService.handle(record.value());

            log.info(
                    "Handled topic={}, partition={}, offset={}",
                    record.topic(),
                    record.partition(),
                    record.offset()
            );
        }
);
~~~

Sau khi cấu hình listener, khởi động container:

~~~java
container.start();
~~~

Khác với phương thức `@KafkaListener`, callback `MessageListener` làm việc trực tiếp với ConsumerRecord. Ứng dụng cần tự viết logic truy cập key, value, headers và metadata theo nhu cầu.

Nếu cần acknowledgment thủ công, có thể dùng loại listener hỗ trợ acknowledgment như `AcknowledgingMessageListener` và cấu hình AckMode tương ứng. Đừng gọi commit thủ công tùy tiện khi container đang quản lý offset; hãy chọn một mô hình acknowledgment nhất quán.

## 5. Ví dụ hoàn chỉnh: tạo container theo topic runtime

Giả sử ứng dụng cần bật consumer cho một topic khi tenant được kích hoạt. Manager lưu container theo topic để tránh tạo trùng và có thể dừng đúng container.

~~~java
@Component
public class DynamicOrderContainerManager {

    private final ConcurrentKafkaListenerContainerFactory<
            String, OrderCreatedEvent> factory;

    private final OrderService orderService;

    private final Map<String,
            ConcurrentMessageListenerContainer<String, OrderCreatedEvent>>
            containers = new ConcurrentHashMap<>();

    public DynamicOrderContainerManager(
            ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreatedEvent> factory,
            OrderService orderService) {
        this.factory = factory;
        this.orderService = orderService;
    }

    public synchronized void start(String topic, String groupId) {
        if (containers.containsKey(topic)) {
            return;
        }

        var container = factory.createContainer(topic);
        ContainerProperties properties = container.getContainerProperties();

        properties.setGroupId(groupId);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);
        properties.setMessageListener(
                (MessageListener<String, OrderCreatedEvent>) record ->
                        orderService.handle(record.value())
        );

        containers.put(topic, container);
        container.start();
    }

    public synchronized void stop(String topic) {
        var container = containers.remove(topic);

        if (container != null) {
            container.stop();
        }
    }

    @PreDestroy
    public synchronized void stopAll() {
        containers.values().forEach(
                MessageListenerContainer::stop
        );
        containers.clear();
    }
}
~~~

Ví dụ dùng một container cho mỗi topic và group ID được truyền vào khi start. Nếu cùng một topic có thể được chạy bởi nhiều group ID trong cùng JVM, key quản lý nên là cặp `topic + groupId` thay vì chỉ topic.

Trong ứng dụng thực tế, cần xử lý lỗi khởi động và trạng thái container. Nếu `start()` không thành công hoặc container không vào trạng thái running, manager cần ghi nhận trạng thái để có thể retry khởi tạo hoặc báo lỗi. Không nên chỉ dựa vào việc container đã được thêm vào map để kết luận consumer đang hoạt động.

## 6. Subscription theo topic và assignment partition tường minh

Spring Kafka hỗ trợ hai kiểu tạo container có semantics khác nhau.

**Subscription theo topic**:

~~~java
var container = factory.createContainer(
        "orders.created",
        "orders.updated"
);
~~~

Consumer dùng group coordinator để tham gia consumer group và nhận partition assignment theo subscription cùng assignor.

**Assignment partition tường minh**:

~~~java
var container = factory.createContainer(
        new TopicPartitionOffset("orders.created", 0),
        new TopicPartitionOffset("orders.created", 1)
);
~~~

Trong cách này, container được gán trực tiếp các partition đã chỉ định. Consumer không dùng group subscription/rebalance để phân phối các partition đó như chế độ subscribe thông thường.

Assignment tường minh phù hợp với tác vụ chuyên biệt như đọc một partition phục vụ migration hoặc công cụ vận hành. Ứng dụng phải tự quản lý quyền sở hữu partition, tránh hai container cùng xử lý một partition ngoài ý muốn và quyết định cách bắt đầu offset.

Nếu dùng group ID để commit offset trong chế độ assignment thủ công, offset vẫn có thể được lưu theo group, nhưng group coordinator không tự chia partition cho các consumer được assign trực tiếp.

## 7. Chọn concurrency cho container động

Với subscription theo topic, có thể đặt concurrency để container tạo nhiều consumer worker:

~~~java
var container = factory.createContainer("orders.created");
container.setConcurrency(3);
container.getContainerProperties().setGroupId("orders-fulfillment");
container.getContainerProperties().setMessageListener(
        (MessageListener<String, OrderCreatedEvent>) record ->
                orderService.handle(record.value())
);
container.start();
~~~

Concurrency là số consumer worker được container quản lý, không phải số listener method hay số record xử lý đồng thời tùy ý.

Khi một topic có ít partition hơn concurrency, một số consumer có thể không nhận partition assignment. Ví dụ topic có hai partition nhưng container concurrency bằng năm; container có thể tạo năm consumer, song tối đa hai consumer có partition từ topic đó tại một thời điểm nếu tất cả cùng subscription.

Nếu container dùng explicit partition assignment, số consumer có thể bị giới hạn theo số partition được giao. Hãy đối chiếu concurrency, partition count và assignment thực tế trước khi scale.

## 8. Group ID, offset và rebalance khi tạo container mới

Khi container subscribe topic với group ID, nó tham gia consumer group. Nếu một container mới được start với cùng group ID và subscription tương thích, Kafka có thể rebalance để phân phối partition giữa các member.

Kết quả phụ thuộc:

- Số partition của các topic.
- Subscription của từng member.
- Partition assignor.
- Group protocol và trạng thái member.
- Consumer đang join, rời group hay khởi động lại.

Một container mới không tự tạo group mới nếu group ID giống nhau. Ngược lại, group ID khác sẽ có offset độc lập và có thể đọc lại toàn bộ topic theo `auto.offset.reset` khi group chưa có committed offset.

Trước khi tạo container, cần xác định nó là consumer mở rộng của group hiện có hay là một consumer độc lập cần nhận toàn bộ luồng. Đây là quyết định ảnh hưởng trực tiếp tới dữ liệu được đọc và tải trên broker.

## 9. Khởi động, tạm dừng, tiếp tục và dừng container

Container hỗ trợ lifecycle operations:

~~~java
container.start();

container.pause();
container.resume();

container.stop();
~~~

- `start()`: bắt đầu consumer worker và poll.
- `pause()`: tạm dừng nhận record theo cơ chế container.
- `resume()`: tiếp tục tiêu thụ.
- `stop()`: dừng container và đóng consumer theo lifecycle.

Pause không giống stop. Pause giữ container và membership theo cơ chế của consumer/container, còn stop đóng consumer và có thể khiến group rebalance.

Nếu cần chờ container dừng xong trước khi giải phóng tài nguyên phụ thuộc, dùng callback của lifecycle stop khi API phiên bản đang dùng hỗ trợ. Đừng xóa trạng thái quản lý trước khi đã có kế hoạch xử lý việc stop thất bại hoặc dừng chưa hoàn tất.

## 10. Quản lý container bằng KafkaListenerEndpointRegistry

Các container được tạo từ `@KafkaListener` thường được Spring quản lý thông qua `KafkaListenerEndpointRegistry`. Có thể tìm container theo listener ID và điều khiển lifecycle:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null && !container.isRunning()) {
    container.start();
}
~~~

Registry quản lý các listener endpoint được đăng ký với nó, bao gồm endpoint từ annotation và endpoint được đăng ký động qua API registry.

Container tạo trực tiếp bằng `factory.createContainer(...)` không tự động xuất hiện trong registry chỉ vì nó dùng cùng factory. Ứng dụng cần tự giữ tham chiếu và quản lý lifecycle của các container đó, hoặc đăng ký endpoint động qua registry nếu muốn registry quản lý.

Không trộn hai mô hình mà không rõ owner. Một container cần có một nơi chịu trách nhiệm start, stop và shutdown.

## 11. Đăng ký listener endpoint động qua registry

Khi muốn tạo endpoint theo kiểu annotation nhưng đăng ký trong runtime, Spring Kafka cung cấp API đăng ký listener endpoint vào `KafkaListenerEndpointRegistry`.

Quy trình khái quát:

1. Tạo một `KafkaListenerEndpoint` với ID duy nhất.
2. Cấu hình group ID, topic hoặc partition và listener method/bean.
3. Chọn container factory phù hợp.
4. Gọi `registerListenerContainer(endpoint, factory, startImmediately)`.
5. Lấy container theo endpoint ID từ registry để start/stop hoặc quan sát.

Cách này phù hợp khi ứng dụng cần quản lý endpoint bằng registry. Tuy nhiên, việc tạo `MethodKafkaListenerEndpoint` yêu cầu cấu hình method, bean và message handler factory đúng với phiên bản Spring Kafka. Nếu chỉ cần callback ConsumerRecord đơn giản, tạo container trực tiếp từ factory thường dễ hiểu hơn.

ID endpoint phải duy nhất trong registry. Trước khi đăng ký, kiểm tra endpoint đã tồn tại để tránh lỗi đăng ký trùng.

## 12. Dynamic topic không đồng nghĩa tự tạo Kafka topic

Gọi `factory.createContainer("tenant-42.orders")` chỉ tạo consumer container để subscribe topic. Nó không phải API tạo topic trên broker.

Topic cần tồn tại hoặc broker phải được cấu hình cho phép auto-create. Trong production, nên provision topic bằng AdminClient, IaC hoặc quy trình quản trị topic riêng, với partition count, replication factor, retention và ACL được kiểm soát.

Quy trình kích hoạt một luồng có thể gồm:

1. Xác thực tenant và quyền tạo subscription.
2. Kiểm tra topic đã được provision.
3. Kiểm tra consumer group và chính sách offset.
4. Tạo container với cấu hình đã phê duyệt.
5. Start và xác minh container đã hoạt động.
6. Theo dõi lag, assignment và lỗi consumer.

Không cho phép request bên ngoài truyền một topic tùy ý rồi tạo container ngay. Điều đó có thể khiến ứng dụng subscribe topic không được phép hoặc tạo lượng consumer không giới hạn.

## 13. Xử lý lỗi và cấu hình chung

Container tạo từ factory có thể sử dụng các thiết lập chung được factory cấu hình, chẳng hạn ConsumerFactory, concurrency, common error handler, record filter strategy và các thuộc tính container mà factory áp dụng.

Tuy nhiên, hãy kiểm tra rõ các cấu hình riêng của container:

- Group ID.
- AckMode.
- Message listener.
- Subscription hoặc partition assignment.
- Client ID prefix.
- Error handling và retry.
- Deserializer và type mapping ở ConsumerFactory.

Nếu listener callback ném exception, container cần có error handler phù hợp. Không bắt mọi exception rồi bỏ qua trong callback, vì như vậy có thể khiến offset tiến dù nghiệp vụ thất bại.

Nếu dùng transactional listener container, phải cấu hình transaction manager và KafkaTemplate phù hợp. Không giả định container tạo bằng code tự động có transaction chỉ vì một factory khác trong ứng dụng đang dùng transaction.

## 14. Quản lý concurrency và số lượng container

Mỗi container có thể tạo một hoặc nhiều consumer worker tùy concurrency. Nếu ứng dụng tạo một container cho mỗi tenant và mỗi container concurrency bằng ba, 100 tenant có thể tạo tới 300 consumer worker.

Trước khi mở rộng, hãy tính:

~~~text
N_consumers = sum(C_i), for i = 1..N_containers
~~~

Trong đó C_i là concurrency của container thứ i. Số worker có assignment thực tế còn phụ thuộc partition count và group subscription.

Cần đặt giới hạn:

- Số container tối đa trên một application instance.
- Concurrency tối đa cho mỗi container.
- Tổng số consumer worker theo deployment.
- Số topic/tenant được phép subscribe.
- Tài nguyên heap, thread, connection và broker request.
- Số lần start/stop trong một khoảng thời gian.

Nếu nhiều tenant có cùng kiểu xử lý, cân nhắc một container subscribe nhiều topic hoặc một mô hình routing phù hợp thay vì tạo container riêng cho từng tenant. Quyết định phải xét isolation, group semantics và khả năng quản lý offset.

## 15. Tránh tạo trùng và race condition

Dynamic container manager thường nhận lệnh start/stop từ API, scheduler hoặc event quản trị. Hai request đồng thời có thể cùng tạo container cho một topic nếu không đồng bộ.

Các biện pháp:

- Dùng registry/map có khóa duy nhất theo container identity.
- Đồng bộ thao tác tạo và xóa hoặc dùng state machine rõ ràng.
- Phân biệt STARTING, RUNNING, STOPPING và STOPPED.
- Chỉ đánh dấu RUNNING sau khi container xác nhận đã start.
- Khi start thất bại, giải phóng container và cho phép retry có kiểm soát.
- Không cho stop một container đang STARTING mà không có quy tắc.
- Lưu cấu hình container để có thể khôi phục sau restart nếu cần.

Không chỉ dùng topic làm khóa nếu cùng topic có thể có nhiều group ID hoặc assignment khác nhau. Một identity có thể gồm topic subscription, group ID và loại assignment.

## 16. Shutdown và giải phóng tài nguyên

Container động không được quản lý như bean thông thường nếu ứng dụng tự tạo bằng factory rồi giữ trong map. Manager cần dừng tất cả container khi application context shutdown.

Ví dụ:

~~~java
@PreDestroy
public void shutdown() {
    containers.values().forEach(MessageListenerContainer::stop);
    containers.clear();
}
~~~

Trong hệ thống có nhiều container, có thể dừng theo thứ tự hoặc chờ callback để xác nhận từng container đã đóng consumer. Nếu cần drain record đang xử lý, hãy thiết kế shutdown timeout và xử lý in-flight record trước khi process kết thúc.

Không xóa topic hoặc group offset khi dừng container. Stop container chỉ dừng consumer; dữ liệu Kafka và committed offset vẫn tồn tại theo retention và group configuration.

Nếu container được đăng ký vào KafkaListenerEndpointRegistry, hãy để registry/Spring lifecycle quản lý theo đúng owner thay vì dừng cùng container ở nhiều nơi.

## 17. Quan sát container động

Một container động cần có định danh ổn định để vận hành. Nên lưu và xuất các thông tin:

- Container ID.
- Topic subscription hoặc partition assignment.
- Group ID.
- Concurrency.
- Trạng thái lifecycle.
- Client ID của consumer worker.
- Partition assignment hiện tại.
- Consumer lag và tốc độ xử lý.
- Số lần start/stop và lỗi khởi tạo.

Có thể quan sát các container do manager tạo qua map nội bộ. Với container được đăng ký vào registry, dùng `KafkaListenerEndpointRegistry` để truy vấn.

Ở phía Kafka, dùng AdminClient hoặc công cụ quản trị consumer group để xem member và partition assignment. Đừng coi container đang `isRunning()` là bằng chứng mọi consumer đã join group hoặc đã được gán partition.

Log nên có container ID, group ID, topic, partition và lifecycle transition. Tránh dùng tenant ID có cardinality lớn làm metric label nếu số tenant không được giới hạn.

## 18. Kiểm thử dynamic listener container

Kiểm thử nên xác minh lifecycle và semantics của consumer group, không chỉ kiểm tra object container được tạo.

| Kịch bản | Điều cần xác minh |
|---|---|
| Tạo container theo topic | Container có đúng subscription và group ID. |
| Start | Consumer được tạo và tham gia group. |
| Nhận record | MessageListener được gọi với đúng key/value. |
| Stop | Consumer đóng và member rời group. |
| Start trùng | Manager không tạo container thứ hai ngoài ý muốn. |
| Hai group ID | Offset và assignment độc lập. |
| Cùng group ID | Member chia partition theo group assignment. |
| Concurrency lớn hơn partition | Consumer dư không được gán partition. |
| Explicit assignment | Container chỉ đọc partition được chỉ định. |
| Start failure | Manager không giữ trạng thái RUNNING giả. |
| Shutdown | Tất cả container động được dừng. |
| Rebalance | Assignment thay đổi được quan sát và xử lý an toàn. |

Dùng EmbeddedKafka hoặc Testcontainers để kiểm tra broker và listener container thật. Dùng Awaitility/latch có timeout để đợi container start, assignment hoặc record đến; không dựa vào Thread.sleep cố định.

Khi kiểm tra stop, xác minh consumer group member rời đi và không còn record được xử lý bởi container đã dừng. Nếu group có member khác, group vẫn có thể tiếp tục hoạt động.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo container nhưng quên `start()` | Consumer không poll record | Gọi start sau khi cấu hình listener. |
| Không đặt group ID đúng | Consumer tham gia group ngoài ý muốn hoặc lỗi cấu hình | Xác định group ID cho từng container. |
| Tạo container trùng | Tăng consumer, duplicate processing hoặc rebalance | Dùng container identity và manager chống trùng. |
| Không stop container | Rò rỉ thread, connection và consumer | Quản lý lifecycle và shutdown. |
| Nghĩ createContainer tạo topic | Consumer subscribe topic không tồn tại hoặc bị lỗi | Provision topic riêng bằng AdminClient/IaC. |
| Nhầm subscribe với explicit assignment | Hiểu sai rebalance và quyền sở hữu partition | Chọn API theo semantics mong muốn. |
| Tạo quá nhiều container | Tăng tài nguyên và group coordination | Đặt quota, giới hạn concurrency và theo dõi. |
| Container trực tiếp nhưng chờ registry quản lý | Không tìm thấy container trong registry | Tự quản lý hoặc đăng ký endpoint động qua registry. |
| Start/stop đồng thời không đồng bộ | Container trùng hoặc trạng thái sai | Dùng state machine/lock và xử lý lifecycle. |
| Không cấu hình error handler | Listener lỗi không được phục hồi theo chính sách | Dùng factory và error handler phù hợp. |

## 20. Bài tập tổng hợp: quản lý consumer theo tenant

Hãy xây dựng một `DynamicOrderContainerManager` cho topic theo tenant.

Yêu cầu:

1. Tạo một ConcurrentKafkaListenerContainerFactory có ConsumerFactory và CommonErrorHandler.
2. Tạo container bằng `factory.createContainer(topic)` khi tenant được kích hoạt.
3. Đặt group ID theo chính sách subscription đã chọn.
4. Gắn MessageListener xử lý OrderCreatedEvent.
5. Cấu hình AckMode và concurrency.
6. Chặn tạo container trùng theo container identity.
7. Start container và ghi nhận lifecycle state.
8. Stop container khi tenant bị vô hiệu hóa.
9. Dừng tất cả container khi ứng dụng shutdown.
10. Thử tạo container theo topic và theo TopicPartitionOffset.
11. Dùng hai group ID để quan sát offset độc lập.
12. Dùng cùng group ID để quan sát rebalance và chia partition.
13. Kiểm tra concurrency lớn hơn số partition.
14. Dùng AdminClient xác minh member và assignment.
15. Viết integration test cho start, receive, stop, restart và shutdown.
16. Đặt quota số container và concurrency để tránh tạo quá nhiều consumer.

Bài tập hoàn thành khi manager có thể tạo, theo dõi và dừng container theo cấu hình runtime; không tạo trùng; không rò rỉ consumer; và có thể giải thích chính xác group membership, offset cùng partition assignment sau mỗi thay đổi.

## 21. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Container model | Factory và listener container | Giải thích được factory tạo container như thế nào. |
| 2. Programmatic creation | `createContainer()` | Tạo container từ topic bằng code. |
| 3. Listener callback | MessageListener và ConsumerRecord | Gắn callback và xử lý record. |
| 4. Container properties | Group ID, AckMode, poll timeout | Cấu hình đúng trước khi start. |
| 5. Subscription | Topics và TopicPartitionOffset | Phân biệt group subscription với manual assignment. |
| 6. Concurrency | Consumer worker và partition | Chọn concurrency theo partition và tải. |
| 7. Lifecycle | Start, pause, resume, stop | Quản lý container trong runtime. |
| 8. Registry | KafkaListenerEndpointRegistry | Phân biệt container trực tiếp và endpoint được registry quản lý. |
| 9. Operations | Quota, state, metrics, shutdown | Tránh container trùng và rò rỉ tài nguyên. |
| 10. Testing | Dynamic lifecycle và group assignment | Kiểm chứng start/stop, offset và rebalance. |

Bài học hoàn thành khi bạn có thể tạo listener container bằng `ConcurrentKafkaListenerContainerFactory`, cấu hình listener và group ID, khởi động/dừng theo runtime, đồng thời phân biệt subscription theo topic với assignment partition tường minh.

Dynamic container giúp ứng dụng phản ứng với nhu cầu subscription thay đổi trong runtime. Đổi lại, ứng dụng phải quản lý identity, lifecycle, group semantics, offset và quota tài nguyên một cách rõ ràng. Hãy tạo container từ factory đã cấu hình, chỉ start sau khi listener sẵn sàng và luôn có quy trình stop/shutdown để consumer không bị bỏ lại ngoài vòng quản lý.

