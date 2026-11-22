# Rủi ro khi tạo container không kiểm soát

Spring Kafka cho phép tạo listener container trong lúc ứng dụng đang chạy. Khả năng này hữu ích khi hệ thống cần bật/tắt subscription theo tenant, topic được cấu hình động hoặc một tác vụ vận hành yêu cầu listener riêng. Tuy nhiên, mỗi container đang chạy thường sở hữu một hoặc nhiều Kafka consumer, thread, kết nối mạng và trạng thái trong consumer group. Nếu tạo container theo từng request, từng message hoặc theo một nguồn dữ liệu không có giới hạn, số consumer có thể tăng nhanh hơn khả năng quản lý của ứng dụng và Kafka cluster.

Rủi ro không chỉ là tốn bộ nhớ. Container tạo thêm consumer group hoặc member có thể làm tăng tải group coordinator, gây rebalance thường xuyên, tăng số lần kết nối broker, làm offset khó quản lý và khiến việc shutdown/redeploy không giải phóng đầy đủ tài nguyên. Một container không được dừng đúng cách có thể tiếp tục poll dù tenant đã bị xóa; một container mới có thể được tạo trùng và cùng xử lý một topic ngoài ý muốn.

Nguyên tắc quan trọng là mỗi container phải có lý do tồn tại, định danh ổn định, giới hạn tài nguyên, chính sách offset và vòng đời rõ ràng. Trước khi tạo nhiều container, hãy cân nhắc một listener dùng nhiều topic hoặc `topicPattern`; chỉ dùng dynamic containers khi các subscription thực sự cần lifecycle hoặc cấu hình độc lập.

## 1. Listener container là tài nguyên chạy nền

Trong Spring Kafka, `KafkaMessageListenerContainer` quản lý một Kafka consumer và luồng xử lý của nó. `ConcurrentMessageListenerContainer` quản lý nhiều child container để tăng concurrency. Container không chỉ là một object Java nhẹ; khi chạy, nó tạo và quản lý consumer, poll loop, heartbeat, fetch, offset commit và kết nối tới broker.

Với một `ConcurrentMessageListenerContainer` có concurrency bằng 4, ứng dụng thường có bốn child consumer. Nếu tạo 30 container như vậy trên mỗi instance ứng dụng, số consumer có thể lên tới khoảng 120 cho instance đó. Nếu chạy 5 instance, tổng số có thể lên tới khoảng 600 consumer. Con số thực tế còn phụ thuộc loại container, partition assignment và thời điểm start/stop, nhưng phép tính này giúp nhìn thấy tác động nhân lên.

```text
Ứng dụng có 5 instance
  mỗi instance tạo 30 container
  mỗi container concurrency = 4

5 x 30 x 4 = tối đa khoảng 600 consumer
```

Mỗi consumer có thể tạo thread, buffer, socket/network traffic, heartbeat và metadata request. Vì vậy, số container cần được xem như một ngân sách tài nguyên chứ không phải một biến cấu hình có thể tăng vô hạn.

## 2. Những rủi ro khi tạo container không kiểm soát

| Rủi ro | Nguyên nhân | Hậu quả |
|---|---|---|
| Cạn thread và bộ nhớ | Mỗi container/concurrency tạo thêm consumer và poll loop | CPU, heap, GC và context switching tăng |
| Quá nhiều kết nối broker | Nhiều consumer đồng thời fetch, heartbeat và metadata | Broker chịu thêm tải network và request |
| Consumer group bùng nổ | Mỗi tenant/container dùng group ID riêng | Group coordinator phải quản lý nhiều group và offset state |
| Rebalance liên tục | Start/stop consumer hoặc thay đổi subscription thường xuyên | Partition bị revoke/assign lặp lại, xử lý bị gián đoạn |
| Consumer thừa | Số consumer lớn hơn số partition có thể được gán | Nhiều consumer không có partition nhưng vẫn tốn tài nguyên |
| Container bị rò rỉ | Tạo container nhưng không stop hoặc unregister đúng cách | Consumer cũ tiếp tục chạy, đọc trùng hoặc giữ kết nối |
| Trùng listener | Hai request đồng thời cùng tạo container cho một tenant | Hai consumer ngoài ý muốn cùng tham gia group hoặc cùng đọc dữ liệu |
| Offset khó dự đoán | Group ID được tạo ngẫu nhiên hoặc tái sử dụng sai | Replay ngoài ý muốn hoặc bỏ qua dữ liệu |
| Topic/ACL không hợp lệ | Đầu vào động không được kiểm tra | Container liên tục lỗi, retry metadata hoặc không thể consume |
| Khó shutdown/redeploy | Lifecycle không gắn với Spring context hoặc registry | Consumer còn hoạt động khi ứng dụng đóng |

Các rủi ro này có thể xuất hiện cùng lúc. Ví dụ, một API tạo listener cho mỗi tenant nhưng không có idempotency có thể tạo container trùng khi retry HTTP request; nếu mỗi container lại dùng group ID ngẫu nhiên, số group và consumer tăng nhanh, đồng thời offset mới bắt đầu theo `auto.offset.reset`.

## 3. Ước lượng số consumer trước khi tạo

Trước khi cho phép tạo container động, cần tính số consumer có thể chạy đồng thời:

```text
total consumers
  = application instances
  x active listener containers per instance
  x concurrency per container
```

Ví dụ:

| Tham số | Giá trị |
|---|---:|
| Số application instance | 3 |
| Container động tối đa mỗi instance | 20 |
| Concurrency mỗi container | 2 |
| Tổng consumer ước lượng | 120 |

Đây là mức trần lý thuyết nếu mọi container đều active. Cần cộng thêm consumer của listener tĩnh, reply container, retry topic, DLT consumer và các service khác dùng chung cluster. Ngoài số consumer, hãy tính số group ID, partition assignment, lượng fetch, số thread và số kết nối.

Với một topic có 8 partition trong một group, concurrency hữu ích tối đa thường không vượt quá 8 consumer được assign partition. Tạo 20 consumer cho topic đó không làm tăng throughput tương ứng; consumer thừa vẫn tạo overhead nhưng không có partition để xử lý. Nếu mỗi tenant có group riêng, mỗi group có thể đọc lại toàn bộ dữ liệu của topic và làm tăng tải broker theo số group.

## 4. Tạo container động bằng ContainerFactory

Spring Kafka hỗ trợ tạo container tại runtime từ `ConcurrentKafkaListenerContainerFactory`. Ví dụ đơn giản:

```java
public ConcurrentMessageListenerContainer<String, String> createContainer(
        ConcurrentKafkaListenerContainerFactory<String, String> factory,
        String topic,
        String groupId,
        MessageListener<String, String> listener) {

    ConcurrentMessageListenerContainer<String, String> container =
            factory.createContainer(topic);
    container.getContainerProperties().setGroupId(groupId);
    container.getContainerProperties().setMessageListener(listener);
    container.setBeanName("dynamic-" + groupId + "-" + topic);
    container.start();
    return container;
}
```

`factory.createContainer(topic)` tạo container theo cấu hình của factory. Ứng dụng phải cung cấp listener, group ID phù hợp và gọi `start()`. Container được tạo trực tiếp theo cách này không tự động trở thành Spring bean và không tự động được `KafkaListenerEndpointRegistry` quản lý. Thành phần tạo nó phải giữ reference và chịu trách nhiệm stop/destroy khi không còn cần.

Đoạn code trên chỉ minh họa API. Không nên để `topic` và `groupId` đến trực tiếp từ request chưa xác thực; cần validate topic, tenant, quyền và quota trước khi tạo. Cũng cần lưu container vào một registry quản lý nội bộ thay vì trả container rồi mất reference.

## 5. Quản lý container bằng một registry của ứng dụng

Một cách an toàn hơn là có một service chịu trách nhiệm tạo, tra cứu và dừng container. Dùng ID ổn định để bảo đảm cùng một tenant/topic không tạo nhiều listener trùng nhau.

```java
@Service
public class DynamicListenerManager {

    private final ConcurrentKafkaListenerContainerFactory<String, String> factory;
    private final Map<String, MessageListenerContainer> containers =
            new ConcurrentHashMap<>();

    public DynamicListenerManager(
            ConcurrentKafkaListenerContainerFactory<String, String> factory) {
        this.factory = factory;
    }

    public MessageListenerContainer start(
            String listenerId,
            String topic,
            String groupId,
            MessageListener<String, String> listener) {

        return containers.computeIfAbsent(listenerId, id -> {
            var container = factory.createContainer(topic);
            container.getContainerProperties().setGroupId(groupId);
            container.getContainerProperties().setMessageListener(listener);
            container.setBeanName(id);
            container.start();
            return container;
        });
    }

    public void stop(String listenerId) {
        containers.computeIfPresent(listenerId, (id, container) -> {
            container.stop();
            return null;
        });
    }
}
```

`computeIfAbsent` giúp tránh tạo hai container cho cùng một key trong một JVM khi có nhiều request đồng thời. Tuy nhiên, nó không giải quyết race giữa nhiều application instance. Nếu chỉ một instance được phép sở hữu listener cho tenant, cần distributed lease/lock hoặc cơ chế leader assignment bên ngoài JVM.

Ví dụ trên cũng cần bổ sung validation, xử lý lỗi khi `start()` thất bại, giới hạn số container và dừng tất cả container khi Spring context shutdown. Khi container start không thành công, không nên để một entry lỗi nằm mãi trong map khiến lần yêu cầu sau tưởng listener đã hoạt động. `computeIfAbsent` chỉ bảo vệ thao tác tạo theo key; ứng dụng vẫn cần phối hợp start/stop/shutdown bằng lifecycle lock hoặc state machine để tránh container vừa được tạo trong lúc shutdown đang duyệt map.

## 6. Dừng container và giải phóng tài nguyên

Tạo container mà không có đường dừng tương ứng là một nguồn rò rỉ phổ biến. Khi tenant bị xóa, topic không còn được consume hoặc subscription được thay thế, ứng dụng cần dừng container và loại bỏ reference quản lý.

```java
public void stop(String listenerId) {
    containers.computeIfPresent(listenerId, (id, container) -> {
        container.stop();
        return null;
    });
}

@PreDestroy
public void stopAll() {
    containers.forEach((id, container) -> container.stop());
    containers.clear();
}
```

`stop()` yêu cầu container dừng và kết thúc consumer lifecycle. Nếu cần chờ callback hoặc xử lý shutdown bất đồng bộ, dùng overload lifecycle phù hợp với phiên bản Spring Kafka và chỉ xóa trạng thái quản lý sau khi việc dừng đã được xác nhận. Khi shutdown, không bỏ qua container đang trong quá trình start hoặc stop.

Nên có timeout shutdown rõ ràng và log container ID, topic, group ID, trạng thái cuối cùng. Không giữ consumer chạy chỉ vì một map hoặc cache còn reference tới container.

## 7. Dùng KafkaListenerEndpointRegistry khi cần endpoint động

Với listener cần được quản lý theo mô hình endpoint của Spring Kafka, có thể đăng ký `KafkaListenerEndpoint` vào `KafkaListenerEndpointRegistry`. Ví dụ dùng `SimpleKafkaListenerEndpoint`:

```java
public void registerEndpoint(
        KafkaListenerEndpointRegistry registry,
        ConcurrentKafkaListenerContainerFactory<String, String> factory,
        String id,
        String topic,
        String groupId,
        MessageListener<String, String> listener) {

    SimpleKafkaListenerEndpoint<String, String> endpoint =
            new SimpleKafkaListenerEndpoint<>();
    endpoint.setId(id);
    endpoint.setGroupId(groupId);
    endpoint.setTopics(topic);
    endpoint.setMessageListener(listener);

    registry.registerListenerContainer(endpoint, factory, true);
}
```

Registry tạo container theo endpoint và quản lý lifecycle của container đã đăng ký. ID endpoint phải duy nhất. Cách này phù hợp khi muốn dùng cơ chế endpoint, container factory và registry thống nhất với `@KafkaListener`.

Khi gỡ endpoint, cần nhớ `unregisterListenerContainer(id)` chỉ gỡ container khỏi registry; phương thức này không gọi `stop()` hoặc `destroy()` thay cho ứng dụng. Phải dừng container trước hoặc sau khi unregister theo thứ tự lifecycle đã chọn. API unregister có từ Spring Kafka 2.8.9; với phiên bản cũ hơn, không giả định phương thức này tồn tại.

```java
public void unregisterEndpoint(
        KafkaListenerEndpointRegistry registry,
        String id) {

    MessageListenerContainer container = registry.getListenerContainer(id);
    if (container != null) {
        container.stop();
        registry.unregisterListenerContainer(id);
    }
}
```

Không gọi `unregisterListenerContainer` trước rồi bỏ reference mà không stop container. Container có thể tiếp tục chạy dù registry không còn quản lý nó.

## 8. Phân biệt container do registry quản lý và container là Spring bean

Các container do `@KafkaListener` tạo ra được đăng ký trong `KafkaListenerEndpointRegistry`; chúng không phải Spring bean thông thường trong application context. Ngược lại, container được khai báo trực tiếp bằng `@Bean` là bean do Spring quản lý và không thuộc danh sách lifecycle container của registry.

Điều này ảnh hưởng đến việc tìm và dừng container:

| Loại container | Cách truy cập/quản lý |
|---|---|
| Tạo bởi `@KafkaListener` | `KafkaListenerEndpointRegistry.getListenerContainer(id)` |
| Đăng ký động qua registry | Registry quản lý lifecycle; dùng ID endpoint để truy cập và unregister |
| Khai báo bằng `@Bean` | Lấy từ ApplicationContext hoặc inject bean; Spring quản lý lifecycle bean |
| Tạo trực tiếp bằng `factory.createContainer()` | Ứng dụng phải giữ reference và tự quản lý start/stop |

Không giả định `registry.getListenerContainers()` sẽ trả về mọi container từng được tạo. Registry chỉ quản lý các container thuộc nó. `getAllListenerContainers()` ở các phiên bản hỗ trợ có thể bao gồm cả container là bean, nhưng không tự khởi tạo bean lazy chưa được tạo.

## 9. Late registration và autoStartup

Một điểm dễ gây bất ngờ là endpoint đăng ký sau khi application context đã refresh có thể được start ngay để tuân theo lifecycle contract, bất kể `autoStartup` của endpoint. Từ Spring Kafka 2.8.7, registry có thuộc tính `alwaysStartAfterRefresh`; đặt `false` cho phép `autoStartup` quyết định container có start hay không khi đăng ký muộn.

Nếu ứng dụng cần đăng ký listener trước nhưng chỉ bật sau khi tenant được kích hoạt, hãy kiểm tra hành vi theo đúng version Spring Kafka. Không cho rằng `autoStartup=false` luôn bảo đảm container mới đăng ký sẽ dừng sau khi context đã refresh.

Thông thường Spring Boot đã cung cấp registry infrastructure. Không khai báo một `KafkaListenerEndpointRegistry` mới chỉ để đổi thuộc tính, vì có thể tạo ra registry thứ hai không quản lý các endpoint hiện có. Hãy inject registry do framework cung cấp và đặt `alwaysStartAfterRefresh` trước khi context refresh hoàn tất, chẳng hạn trong một bean cấu hình khởi tạo sớm. Nếu chỉ muốn điều khiển một endpoint cụ thể, cân nhắc tham số `startImmediately` của `registerListenerContainer(...)` cùng hành vi late registration của phiên bản đang dùng.

## 10. Rủi ro khi tạo một container cho mỗi tenant

Một thiết kế thường gặp là mỗi tenant có topic riêng và ứng dụng tạo một listener container cho tenant đó. Cách này có thể phù hợp khi mỗi tenant có lifecycle, quyền truy cập, group ID và chính sách xử lý độc lập. Nhưng nếu số tenant tăng từ vài chục lên vài nghìn, số consumer và group cũng tăng theo.

Ví dụ với 1.000 tenant, mỗi tenant một container, concurrency 1 và 4 application instance:

```text
1.000 containers/instance x 1 consumer x 4 instances
= khoảng 4.000 consumer
```

Nếu mỗi tenant có một group ID ổn định, cluster còn phải quản lý hàng nghìn group và offset state. Nếu mỗi application instance lại tạo group ID khác nhau cho cùng tenant, mỗi group sẽ là subscriber độc lập và có thể đọc lại toàn bộ dữ liệu, làm tải tăng theo số instance.

Trước khi chọn mô hình này, hãy xác định tenant nào thực sự cần consumer riêng. Nếu mọi tenant dùng cùng schema, cùng chính sách retry và cùng lifecycle, một consumer có thể subscribe nhiều topic hoặc một topic có key tenant thường đơn giản hơn.

## 11. Thay thế bằng một listener subscribe nhiều topic

Nếu nhiều topic dùng chung listener, serializer, group ID và error policy, có thể cấu hình một `@KafkaListener` đọc nhiều topic:

```java
@KafkaListener(
        id = "tenantEventsListener",
        topics = {"tenant-a.events", "tenant-b.events", "tenant-c.events"},
        groupId = "tenant-events-reader")
public void onEvent(ConsumerRecord<String, TenantEvent> record) {
    tenantEventService.handle(record.topic(), record.key(), record.value());
}
```

Một container có thể consume nhiều topic và Kafka phân phối các partition được subscribe cho consumer group. Điều này giảm số container và group so với tạo một container cho từng topic. Đổi lại, các topic chia sẻ cùng lifecycle, concurrency và error policy của listener; nếu tenant cần cô lập mạnh, cần đánh giá kỹ.

Nếu danh sách topic thay đổi theo thời gian, có thể cân nhắc pattern subscription thay vì tạo container mới cho từng topic.

## 12. Thay thế bằng topicPattern

`@KafkaListener(topicPattern = "...")` cho phép subscribe các topic khớp regular expression. Kafka consumer cập nhật metadata và phát hiện topic mới khớp pattern theo cơ chế metadata refresh.

```java
@KafkaListener(
        id = "tenantPatternListener",
        topicPattern = "tenant\\.[a-z0-9-]+\\.events",
        groupId = "tenant-events-reader")
public void onEvent(ConsumerRecord<String, TenantEvent> record) {
    tenantEventService.handle(record.topic(), record.value());
}
```

Pattern cần đủ hẹp để không subscribe nhầm topic hệ thống hoặc topic của tenant không được phép. Một listener pattern không tạo một container cho mỗi topic; nó dùng một subscription có thể khớp nhiều topic. Đây thường là lựa chọn gọn khi topic được tạo động nhưng các topic cùng contract và chính sách xử lý.

Không dùng regex rộng như `.*` trên cluster nhiều topic nếu consumer chỉ được phép đọc một nhóm topic nhỏ. Pattern subscription cũng không thay thế ACL; broker vẫn phải kiểm soát quyền READ cho principal của consumer.

## 13. Rủi ro khi dùng group ID động

Group ID quyết định vị trí committed offset và phạm vi chia partition. Nếu tạo group ID ngẫu nhiên mỗi lần container khởi động, consumer có thể được xem như group mới. Khi chưa có committed offset, `auto.offset.reset` quyết định bắt đầu từ `earliest` hay `latest`.

Hệ quả:

- `earliest`: group mới có thể đọc lại nhiều dữ liệu cũ, gây tải tăng và side effect trùng.
- `latest`: group mới có thể bỏ qua dữ liệu đã tồn tại trước khi group bắt đầu đọc.
- Group ID ổn định: consumer tiếp tục từ committed offset của group, phù hợp khi muốn giữ tiến độ giữa các lần restart.

Không tạo group ID bằng UUID cho mỗi lần start trừ khi thật sự muốn một subscription độc lập mới. Nếu một tenant cần offset riêng, tạo group ID ổn định theo tenant và môi trường, ví dụ `orders-tenant-42-prod`; không dùng dữ liệu tùy ý từ request làm group ID nếu chưa validate ký tự và độ dài.

Nếu nhiều container dùng chung group ID và cùng subscribe một topic, Kafka phân phối partition giữa chúng. Nếu số consumer vượt partition, một số consumer không được gán partition. Nếu các container có subscription khác nhau nhưng dùng chung group, cần hiểu assignment strategy và tập topic union trước khi triển khai.

## 14. Rebalance storm do start/stop liên tục

Mỗi lần member mới gia nhập hoặc rời consumer group, Kafka có thể thực hiện rebalance để phân phối lại partition. Nếu ứng dụng tạo và dừng container liên tục theo HTTP request hoặc sự kiện tenant, group có thể rebalance thường xuyên.

Rebalance có thể gây:

- Partition bị revoke trong lúc listener đang xử lý.
- Consumer phải commit offset hoặc xử lý lại record tùy ack/commit strategy.
- Listener tạm ngừng nhận record trong thời gian assignment mới.
- Tăng duplicate processing nếu side effect không idempotent.
- Consumer lag tăng dù lượng message đầu vào không đổi.
- Tăng tải group coordinator và log churn.

Không nên start/stop container theo từng message hoặc từng request ngắn. Nếu một tenant chỉ tạm thời không cần xử lý, cân nhắc pause container hoặc dùng cơ chế filter/routing ở tầng ứng dụng thay vì liên tục tạo và hủy consumer.

## 15. Concurrency không phải cách nhân container tùy ý

`ConcurrentKafkaListenerContainerFactory.setConcurrency(n)` tạo nhiều consumer con cho một listener container. Số consumer hữu ích bị giới hạn bởi số partition có thể được gán trong group. Ví dụ topic có 6 partition, concurrency 12 sẽ không tạo throughput gấp đôi concurrency 6; một số consumer không có partition.

Nếu tạo 10 dynamic containers và mỗi container concurrency 5, ứng dụng có thể tạo tới khoảng 50 consumer cho một loại subscription. Hãy tính concurrency ở cấp toàn hệ thống, không chỉ ở từng container.

Chọn concurrency dựa trên:

- Số partition của các topic được subscribe.
- Throughput và thời gian xử lý trung bình mỗi record.
- CPU, memory, connection pool và giới hạn downstream.
- Số application instance và số container động đồng thời.
- Khả năng chịu rebalance và thời gian poll.

Tăng concurrency không sửa được bottleneck database hoặc HTTP dependency. Nếu downstream chỉ xử lý được 20 request đồng thời, tạo 200 consumer có thể làm downstream quá tải và retry tăng mạnh.

## 16. Race condition khi nhiều request cùng tạo container

Một API như `POST /tenants/{id}/listeners` có thể nhận hai request đồng thời. Nếu code kiểm tra `containsKey()` rồi mới tạo container, cả hai request có thể cùng thấy chưa tồn tại và tạo hai container.

Anti-pattern:

```java
if (!containers.containsKey(listenerId)) {
    MessageListenerContainer container = createContainer(...);
    containers.put(listenerId, container);
}
```

Hãy dùng thao tác atomic như `computeIfAbsent`, lock theo listener ID hoặc một state machine quản lý `CREATING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED`. Không chỉ lưu container reference; lưu cả trạng thái start, thời điểm tạo, topic, group ID, owner và lỗi gần nhất.

Trong môi trường nhiều application instance, `ConcurrentHashMap` chỉ bảo vệ một JVM. Muốn bảo đảm một listener owner trên toàn cluster, cần distributed coordination hoặc phân vùng tenant rõ ràng để mỗi instance chỉ quản lý một tập tenant.

## 17. Validate topic và giới hạn đầu vào động

Không tạo container từ topic name do client gửi trực tiếp. Topic có thể chứa ký tự không hợp lệ, không tồn tại hoặc nằm ngoài phạm vi tenant. Một API không kiểm tra có thể bị dùng để tạo hàng nghìn consumer đọc các topic không liên quan.

Trước khi tạo container, kiểm tra:

- Tenant tồn tại và caller có quyền quản lý tenant đó.
- Topic nằm trong allowlist hoặc được tạo bởi quy trình quản trị đáng tin cậy.
- Topic tồn tại và có partition/replication phù hợp.
- Principal Kafka của ứng dụng có quyền READ và DESCRIBE cần thiết.
- Group ID tuân thủ naming policy và không xung đột với tenant khác.
- Tenant chưa vượt quota container/concurrency.
- Cấu hình deserializer, error handler và offset policy phù hợp với contract topic.

Không tự động bật `allow.auto.create.topics` hoặc tạo topic cho mọi request đến API. Topic creation nên có quota, naming convention, retention, replication factor và ACL được quản trị riêng.

## 18. Quản lý trạng thái và quota

Dynamic listener manager nên có quota rõ ràng:

| Giới hạn | Ví dụ chính sách |
|---|---|
| Container tối đa mỗi application instance | Không vượt ngân sách consumer đã kiểm thử |
| Container tối đa mỗi tenant | Một listener active cho mỗi subscription được phê duyệt |
| Concurrency tối đa mỗi container | Không vượt số partition hữu ích hoặc downstream capacity |
| Tần suất tạo/hủy | Không cho phép churn liên tục theo request |
| Thời gian tồn tại | Container phải có owner và điều kiện dừng |
| Thời gian start | Nếu không start trong deadline, chuyển `FAILED` và phát cảnh báo |
| Shutdown deadline | Dừng container trong thời gian grace period trước khi process exit |

Trạng thái subscription nên được lưu bền vững nếu cần khôi phục sau restart. Nếu chỉ lưu trong memory, ứng dụng không biết tenant nào cần listener khi process khởi động lại. Tuy nhiên, không tự động khôi phục mọi container mà không kiểm tra quota và trạng thái tenant; số lượng container có thể tăng đột biến sau deploy.

## 19. Quan sát container động trong production

Mỗi container nên có ID và metadata có thể truy vết. Tối thiểu cần quan sát:

- Số container đang `running`, `stopped`, `starting` và `failed`.
- Tổng số consumer/child container theo application instance.
- Concurrency, topic subscription và group ID.
- Consumer lag theo topic/partition/group.
- Số lần rebalance và thời gian rebalance.
- Số lần start/stop trong một khoảng thời gian.
- Thời gian xử lý record, poll interval và lỗi listener.
- Số consumer không được gán partition.
- Số container quá thời gian tồn tại hoặc không còn owner.
- Lỗi shutdown/stop và số consumer còn chạy khi ứng dụng đóng.

Có thể dùng `KafkaListenerEndpointRegistry.getListenerContainers()` để kiểm tra các container registry quản lý; `getAllListenerContainers()` trên phiên bản hỗ trợ giúp bao gồm thêm container được khai báo dạng bean. Với container tạo trực tiếp từ factory, phải quan sát qua registry quản lý nội bộ của ứng dụng.

Không đưa tenant ID, topic ID hoặc listener ID có cardinality cao vào metric label nếu số lượng lớn. Dùng structured log hoặc trace cho ID chi tiết; metric nên tập trung vào số lượng theo trạng thái, loại listener, nhóm topic và exception category.

## 20. Kiểm thử vòng đời và tải container

Kiểm thử dynamic container cần bao phủ cả việc tạo, sử dụng, dừng và giải phóng. Không chỉ kiểm tra `start()` không ném exception.

| Kịch bản | Kỳ vọng |
|---|---|
| Tạo một container hợp lệ | Consumer được tạo, subscribe đúng topic và xử lý record |
| Gọi start hai lần cùng listener ID | Không tạo container thứ hai |
| Hai request tạo cùng listener đồng thời | Chỉ một container được đăng ký/chạy |
| Topic không tồn tại hoặc ACL thiếu | Container báo lỗi rõ, manager đánh dấu `FAILED` và giải phóng reference phù hợp |
| Dừng tenant | Container stop, consumer đóng và không nhận record mới |
| Dừng ứng dụng | Tất cả container động được stop trong shutdown grace period |
| Unregister registry endpoint | Container đã stop trước/sau unregister theo quy trình; không còn consumer mồ côi |
| Tạo vượt quota | Request bị từ chối trước khi tạo consumer mới |
| Tăng concurrency vượt partition | Không kỳ vọng throughput vượt số partition; metric thể hiện consumer idle |
| Start/stop liên tục | Theo dõi rebalance, lag và resource để xác nhận không có churn bất thường |
| Restart ứng dụng | Chỉ các subscription được phê duyệt và còn hiệu lực được khôi phục |
| Nhiều application instance | Một tenant không bị tạo consumer trùng ngoài chiến lược ownership |

Nên chạy integration test với Kafka qua Testcontainers hoặc Embedded Kafka và đo số consumer/thread trước, trong và sau test. Kiểm tra cả broker group membership và việc offset tiếp tục đúng sau khi container được stop rồi tạo lại.

## 21. Quy trình tạo và hủy container có kiểm soát

1. Nhận yêu cầu subscription từ nguồn đã xác thực.
2. Xác thực tenant, topic, group ID, ACL, quota và cấu hình xử lý.
3. Tạo listener ID ổn định và kiểm tra trạng thái hiện tại.
4. Đánh dấu trạng thái `CREATING` để chặn yêu cầu tạo trùng.
5. Tạo container từ factory hoặc endpoint registry.
6. Gắn listener, group ID, concurrency, ack/error policy và bean name.
7. Start container và xác nhận trạng thái chạy/assignment theo yêu cầu.
8. Lưu trạng thái `RUNNING` cùng owner và timestamp.
9. Khi subscription hết hạn hoặc tenant bị xóa, đánh dấu `STOPPING`.
10. Stop container, chờ hoàn tất shutdown cần thiết rồi unregister/xóa reference.
11. Xác nhận consumer đã rời group và trạng thái chuyển `STOPPED`.
12. Ghi audit event để truy vết ai tạo, thay đổi hoặc dừng subscription.

Nếu start thất bại, chuyển sang `FAILED`, log nguyên nhân và cho phép retry tạo container theo backoff có giới hạn. Không giữ entry `RUNNING` giả hoặc tiếp tục tạo container mới sau mỗi request khi container cũ chưa được giải phóng.

## 22. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| Container chỉ là object Java nhẹ | Container đang chạy quản lý consumer, thread, poll loop và kết nối broker |
| Tạo thêm container luôn tăng throughput | Throughput bị giới hạn bởi partition, downstream và tài nguyên |
| Mỗi tenant một group ID là miễn phí | Mỗi group có offset và lifecycle riêng, làm tăng tải coordinator/broker |
| `KafkaListenerEndpointRegistry` quản lý mọi container | Registry chỉ quản lý container được đăng ký với nó; container tạo trực tiếp phải được ứng dụng quản lý |
| Unregister tự động dừng container | `unregisterListenerContainer` chỉ gỡ khỏi registry; phải stop riêng |
| `autoStartup=false` luôn ngăn endpoint đăng ký muộn chạy | Late registration có hành vi riêng; kiểm tra `alwaysStartAfterRefresh` và version |
| Tăng concurrency không có giới hạn | Consumer hữu ích bị giới hạn bởi partition và downstream capacity |
| `ConcurrentHashMap` ngăn tạo trùng trên toàn cluster | Nó chỉ đồng bộ trong một JVM; nhiều instance cần distributed coordination |
| Dừng container chỉ cần xóa khỏi map | Phải stop consumer và giải phóng lifecycle trước khi bỏ reference |
| Topic pattern có thể thay thế ACL | Pattern chỉ lọc tên topic; broker ACL vẫn quyết định quyền đọc |

## Checklist trước khi đưa dynamic containers vào production

- Có lý do rõ ràng để dùng container riêng thay vì một listener nhiều topic/topicPattern.
- Ước lượng tổng consumer theo số application instance, container và concurrency.
- Đặt quota cho container, group ID, tenant và tần suất start/stop.
- Dùng listener ID và group ID ổn định; tránh UUID ngẫu nhiên mỗi lần start.
- Có registry nội bộ hoặc `KafkaListenerEndpointRegistry` quản lý lifecycle.
- Xử lý race condition khi nhiều request tạo cùng subscription.
- Validate topic, tenant, ACL, partition và naming policy trước khi tạo.
- Có quy trình stop, unregister và shutdown toàn bộ container.
- Không giả định unregister tự stop container.
- Kiểm tra late registration/autoStartup theo phiên bản Spring Kafka.
- Theo dõi consumer count, group count, rebalance, lag và container state.
- Kiểm thử start/stop, duplicate creation, quota, restart và cleanup.
- Có runbook xử lý container mồ côi, group tăng bất thường và rebalance storm.

Dynamic listener containers là công cụ quản lý subscription ở runtime, không phải cách nhân consumer không giới hạn. Mỗi container bổ sung consumer và lifecycle cần quản lý; số lượng lớn có thể gây cạn tài nguyên, rebalance liên tục, consumer idle và khó kiểm soát offset. Hãy ưu tiên listener nhiều topic hoặc topic pattern khi các subscription có cùng chính sách; khi thật sự cần container riêng, quản lý bằng ID ổn định, quota, coordination và quy trình stop/unregister có kiểm chứng.

## Tài liệu tham khảo

- [Spring for Apache Kafka – Dynamically Creating Containers](https://docs.spring.io/spring-kafka/reference/kafka/dynamic-containers.html)
- [Spring for Apache Kafka – @KafkaListener Lifecycle Management](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/kafkalistener-lifecycle.html)
- [KafkaListenerEndpointRegistry API](https://docs.spring.io/spring-kafka/api/org/springframework/kafka/config/KafkaListenerEndpointRegistry.html)
