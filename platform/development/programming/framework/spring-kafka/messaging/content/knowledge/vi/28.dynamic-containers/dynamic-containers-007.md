# Container cho tenant hoặc topic động

## 1. Khi nào cần tạo listener container động?

Trong Spring Kafka, listener thường được khai báo tĩnh bằng `@KafkaListener`. Khi ứng dụng khởi động, Spring tạo listener container tương ứng với annotation và quản lý vòng đời container. Cách này phù hợp khi danh sách topic và consumer group đã biết trước.

Một số hệ thống có danh sách tenant hoặc topic thay đổi trong lúc ứng dụng đang chạy. Ví dụ:

- Nền tảng SaaS tạo một topic riêng cho mỗi tenant lớn.
- Tenant được kích hoạt hoặc ngừng sử dụng theo cấu hình quản trị.
- Dịch vụ cần bắt đầu đọc topic mới sau khi khách hàng đăng ký.
- Ứng dụng tích hợp nhận danh sách topic từ một control plane được quản lý.
- Các topic theo tenant được provision theo vòng đời hợp đồng.

Khi đó, ứng dụng có thể tạo, khởi động, dừng và loại bỏ listener container trong runtime. Spring Kafka hỗ trợ tạo container từ `ConcurrentKafkaListenerContainerFactory` hoặc đăng ký listener endpoint vào `KafkaListenerEndpointRegistry`.

Container động là tài nguyên chạy nền: nó tạo consumer, tham gia consumer group, poll broker và gọi listener. Vì vậy, việc tạo container phải gắn với chính sách lifecycle rõ ràng. Không tạo container mới cho từng request HTTP hoặc từng record Kafka.

## 2. Phân biệt container động, topic động và tenant động

Ba khái niệm có liên quan nhưng không đồng nghĩa:

| Khái niệm | Thay đổi động là gì? | Ví dụ |
|---|---|---|
| Topic động | Tên topic hoặc danh sách topic thay đổi trong runtime | `tenant-acme.orders` |
| Tenant động | Tenant được kích hoạt, tạm dừng hoặc ngừng hoạt động | `acme`, `globex` |
| Listener container động | Consumer container được tạo/dừng theo cấu hình runtime | Container riêng đọc topic của `acme` |

Một tenant không bắt buộc phải có một container. Nếu mọi tenant cùng ghi vào topic `orders` và payload có `tenantId`, thường chỉ cần một listener container đọc topic chung rồi định tuyến nghiệp vụ theo tenant. Tạo một container cho mỗi tenant trong trường hợp đó sẽ khiến các container cùng đọc cùng topic nếu mỗi container dùng group riêng, dẫn đến mỗi record được tiêu thụ nhiều lần.

Chỉ nên tạo container riêng khi topology yêu cầu consumer group, subscription, concurrency, quyền truy cập hoặc lifecycle riêng cho tenant/topic đó.

## 3. Chọn topology phù hợp

Có ba cách thiết kế thường gặp.

### Một topic chung cho nhiều tenant

Tất cả tenant ghi vào một topic, ví dụ `orders`. Record mang `tenantId` trong payload hoặc header; key có thể là `tenantId` hoặc `orderId` tùy yêu cầu partition ordering.

~~~mermaid
flowchart LR
    A["Tenant A"] --> T["Topic orders"]
    B["Tenant B"] --> T
    C["Tenant C"] --> T
    T --> L["Một listener container / consumer group"]
    L --> R["Định tuyến nghiệp vụ theo tenantId"]
~~~

Ưu điểm là ít topic, ít container và dễ mở rộng theo partition. Cần kiểm tra quyền truy cập ở tầng ứng dụng vì ACL topic không cô lập từng tenant khi họ dùng chung topic.

### Một topic cho mỗi tenant, container dùng chung

Một container có thể subscribe nhiều topic hoặc subscribe theo pattern. Cách này hữu ích khi tất cả topic có cùng schema, cùng chính sách xử lý và cùng quyền truy cập.

~~~mermaid
flowchart LR
    A["tenant-acme.orders"] --> L["Một listener container"]
    B["tenant-globex.orders"] --> L
    C["tenant-initech.orders"] --> L
    L --> R["Xử lý event"]
~~~

Dùng một container giúp giảm số consumer group và số thread. Tuy nhiên, concurrency và lỗi của một listener có thể ảnh hưởng đến các tenant cùng nằm trong container.

### Một container cho mỗi tenant hoặc nhóm topic

Mỗi container có subscription và group ID riêng. Đây là lựa chọn khi cần tách biệt lifecycle, concurrency, retry, DLT hoặc quyền vận hành.

~~~mermaid
flowchart TD
    A["Tenant A topic"] --> CA["Container A / Group A"]
    B["Tenant B topic"] --> CB["Container B / Group B"]
    C["Tenant C topic"] --> CC["Container C / Group C"]
~~~

Đổi lại, số lượng consumer, connection, thread, group metadata và chi phí giám sát tăng theo số container. Với hàng nghìn tenant nhỏ, một container cho mỗi tenant thường không phải thiết kế kinh tế.

## 4. Tạo container trực tiếp từ factory

`ConcurrentKafkaListenerContainerFactory` có thể tạo container theo tên topic lúc runtime. Sau khi tạo, ứng dụng cấu hình group ID, listener và concurrency rồi gọi `start()`.

Ví dụ listener xử lý record kiểu `OrderCreatedEvent`:

~~~java
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListener;

public class TenantContainerManager {

    private final ConcurrentKafkaListenerContainerFactory<
        String, OrderCreatedEvent> containerFactory;

    public TenantContainerManager(
            ConcurrentKafkaListenerContainerFactory<
                String, OrderCreatedEvent> containerFactory) {
        this.containerFactory = containerFactory;
    }

    public ConcurrentMessageListenerContainer<
            String, OrderCreatedEvent> create(
                    String topic,
                    String groupId,
                    int concurrency) {

        var container = containerFactory.createContainer(topic);

        container.getContainerProperties().setGroupId(groupId);
        container.setConcurrency(concurrency);

        container.setupMessageListener(
            (MessageListener<String, OrderCreatedEvent>) record -> {
                OrderCreatedEvent event = record.value();
                process(event);
            }
        );

        return container;
    }

    private void process(OrderCreatedEvent event) {
        // Gọi service nghiệp vụ.
    }
}
~~~

`createContainer(topic)` tạo container chưa chạy. `setupMessageListener()` gắn listener cho record. `setGroupId()` đặt group ID trên container properties; giá trị này được dùng thay cho group ID mặc định trong consumer factory. `setConcurrency()` đặt số consumer con mà concurrent container quản lý.

Phương thức trên chỉ tạo và cấu hình container. Caller phải quản lý vòng đời và gọi `start()` sau khi đã đăng ký container vào registry quản lý của ứng dụng.

Factory cần được cấu hình sẵn với consumer factory, deserializer, error handler, converter và các thuộc tính chung. Container tạo động kế thừa cấu hình đó. Nếu tenant cần cấu hình bảo mật hoặc deserializer khác, không thay đổi factory dùng chung trong khi các container đang chạy; hãy tạo factory riêng có cấu hình tường minh.

## 5. Quản lý lifecycle bằng registry của ứng dụng

Khi tạo container thủ công, ứng dụng cần lưu tham chiếu để tránh tạo trùng và có thể dừng container đúng lúc. Một registry đơn giản có thể dùng map theo tenant key.

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import jakarta.annotation.PreDestroy;

import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ConcurrentMessageListenerContainer;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class TenantContainerRegistry {

    private final ConcurrentKafkaListenerContainerFactory<
        String, OrderCreatedEvent> factory;

    private final TenantOrderService tenantOrderService;

    private final Map<String,
        ConcurrentMessageListenerContainer<String, OrderCreatedEvent>>
            containers = new ConcurrentHashMap<>();

    public TenantContainerRegistry(
            ConcurrentKafkaListenerContainerFactory<
                String, OrderCreatedEvent> factory,
            TenantOrderService tenantOrderService) {
        this.factory = factory;
        this.tenantOrderService = tenantOrderService;
    }

    public synchronized void startTenant(
            String tenantKey,
            String topic,
            String groupId) {

        if (containers.containsKey(tenantKey)) {
            return;
        }

        var container = factory.createContainer(topic);
        container.getContainerProperties().setGroupId(groupId);
        container.setConcurrency(2);

        container.setupMessageListener(
            (MessageListener<String, OrderCreatedEvent>) record -> {
                var event = record.value();

                if (!tenantKey.equals(event.tenantKey())) {
                    throw new IllegalArgumentException(
                        "Record không thuộc tenant của container"
                    );
                }

                tenantOrderService.process(tenantKey, event);
            }
        );

        containers.put(tenantKey, container);

        try {
            container.start();
        } catch (RuntimeException ex) {
            containers.remove(tenantKey, container);
            container.stop();
            throw ex;
        }
    }

    public synchronized void stopTenant(String tenantKey) {
        var container = containers.remove(tenantKey);
        if (container != null) {
            container.stop();
        }
    }

    public boolean isRunning(String tenantKey) {
        var container = containers.get(tenantKey);
        return container != null && container.isRunning();
    }

    @PreDestroy
    public synchronized void stopAll() {
        containers.values().forEach(
            ConcurrentMessageListenerContainer::stop
        );
        containers.clear();
    }
}
~~~

Ví dụ dùng `synchronized` để minh họa rằng thao tác kiểm tra, đăng ký và start/stop phải được điều phối nguyên tử. Trong hệ thống có nhiều thao tác quản trị đồng thời, có thể thay bằng lock theo tenant hoặc state machine có trạng thái `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED`.

`synchronized` chỉ điều phối các thread trong cùng một JVM. Nếu ứng dụng chạy nhiều replica, mỗi replica có registry riêng. Khi các replica cùng phải duy trì một container cho tenant, hãy dùng cùng group ID để Kafka chia partition giữa các member. Nếu chỉ một replica được phép sở hữu container, cần cơ chế điều phối phân tán hoặc lease trong control plane; lock trong bộ nhớ không ngăn replica khác tạo container.

`tenantKey` trong ví dụ là khóa nội bộ đã được xác thực và chuẩn hóa, không phải chuỗi tùy ý do client gửi trực tiếp. `topic` và `groupId` phải được lấy từ cấu hình tenant đáng tin cậy. Không cho phép request HTTP tự truyền tên topic bất kỳ rồi yêu cầu ứng dụng subscribe.

Nếu `startTenant()` được gọi lại với cùng tenant nhưng topic/group đã thay đổi, ví dụ đơn giản này bỏ qua lần gọi sau. Trong ứng dụng thật, registry nên so sánh cấu hình đang chạy và thực hiện quy trình thay thế có kiểm soát nếu subscription cần đổi.

## 6. Dừng và thay thế container an toàn

Khi tenant bị tạm dừng hoặc topic không còn được sử dụng, dừng container để giải phóng consumer và thread.

`container.stop()` yêu cầu container dừng; Spring Kafka thực hiện đóng consumer và rời group. Có thể dùng callback stop nếu cần biết chính xác khi quá trình dừng hoàn tất trước khi xóa tài nguyên liên quan.

`start()` khởi động lifecycle của container nhưng không đồng nghĩa consumer đã kết nối broker, nhận partition assignment hoặc bắt đầu xử lý record. Tương tự, `isRunning()` phản ánh trạng thái lifecycle chứ không phải readiness nghiệp vụ. Nếu control plane chỉ đánh dấu tenant `RUNNING` sau khi consumer thực sự được gán partition, hãy quan sát các container/consumer lifecycle event hoặc dùng `ConsumerRebalanceListener` để xác nhận assignment. Lỗi kết nối broker có thể được Kafka client retry sau khi `start()` đã trả về, nên `try/catch` quanh `start()` chỉ bắt được lỗi đồng bộ lúc khởi động.

Một quy trình thay thế container có thể gồm:

1. Đánh dấu tenant đang `STOPPING` để không nhận thêm yêu cầu start trùng.
2. Gọi stop và chờ container hoàn tất shutdown.
3. Gỡ container cũ khỏi registry.
4. Cập nhật subscription hoặc group ID theo cấu hình đã duyệt.
5. Tạo container mới, đăng ký và start.
6. Chuyển tenant sang `RUNNING` sau khi container khởi động thành công.

Trong triển khai thực tế, nên phân biệt `STARTED` với `READY`: container đã start chưa chắc đã được assign partition. Chỉ công bố trạng thái ready khi điều kiện vận hành mà ứng dụng yêu cầu đã được xác nhận.

Không đổi topic/group ID của container đang chạy bằng cách sửa consumer factory. Consumer subscription được thiết lập khi consumer khởi tạo; thay đổi cần dừng và tạo container mới hoặc dùng API quản lý subscription phù hợp.

Khi ứng dụng shutdown, dừng toàn bộ container động. Nếu không giữ tham chiếu đến container hoặc không quản lý lifecycle, consumer có thể bị bỏ lại cho đến khi tiến trình kết thúc, làm khó kiểm soát rebalance và log shutdown.

## 7. Dùng KafkaListenerEndpointRegistry cho endpoint động

Nếu muốn các listener động được quản lý theo mô hình endpoint của Spring Kafka, có thể đăng ký `KafkaListenerEndpoint` vào `KafkaListenerEndpointRegistry`. Cách này hữu ích khi ứng dụng cần quản lý listener theo ID và dùng chung cơ chế lifecycle của registry.

Ứng dụng cần bật Spring Kafka listener infrastructure, thường thông qua `@EnableKafka` hoặc auto-configuration tương ứng của Spring Boot, để registry và container factory được tạo trong application context.

Ví dụ endpoint đơn giản:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.config.SimpleKafkaListenerEndpoint;
import org.springframework.kafka.listener.MessageListener;

public void registerTenantEndpoint(
        String listenerId,
        String topic,
        String groupId,
        KafkaListenerEndpointRegistry registry,
        ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
            factory) {

    var endpoint = new SimpleKafkaListenerEndpoint<
        String, OrderCreatedEvent>();

    endpoint.setId(listenerId);
    endpoint.setGroupId(groupId);
    endpoint.setTopics(topic);

    endpoint.setMessageListener(
        (MessageListener<String, OrderCreatedEvent>) record ->
            process(record.value())
    );

    registry.registerListenerContainer(endpoint, factory, true);
}
~~~

`listenerId` phải duy nhất trong registry. Endpoint được đăng ký với `startImmediately=true` sẽ được khởi động ngay nếu registry đã sẵn sàng. Nếu endpoint được đăng ký trước khi context khởi động, lifecycle của registry sẽ khởi động container theo cấu hình.

Registry có thể tra cứu container bằng ID để kiểm tra hoặc dừng. Khi cần xóa endpoint động, dùng API unregister nếu phiên bản Spring Kafka đang dùng hỗ trợ; nếu không, dừng container và quản lý việc giải phóng endpoint theo lifecycle của ứng dụng. Kiểm tra API cụ thể của phiên bản dependency vì các method quản lý endpoint có thể khác giữa các major/minor release.

Không đăng ký cùng một listener ID nhiều lần. Hãy kiểm tra ID trong registry trước, đồng thời đồng bộ thao tác register/unregister khi có nhiều yêu cầu quản trị đồng thời.

## 8. Subscribe theo danh sách topic hoặc pattern

Không phải lúc nào cũng cần tạo một container riêng cho mỗi topic. Một container có thể subscribe một danh sách topic hoặc pattern tên topic.

### Subscribe danh sách topic

Dùng khi danh sách topic đã được cấu hình tại thời điểm tạo container:

~~~java
var container = factory.createContainer(
    "tenant-acme.orders",
    "tenant-globex.orders",
    "tenant-initech.orders"
);
~~~

Các topic trong danh sách được xử lý bởi cùng listener container và consumer group. Đây là lựa chọn gọn nếu schema, quyền, error handling và nghiệp vụ tương đồng.

### Subscribe theo regex pattern

Khi topic được tạo động theo quy tắc tên, có thể dùng pattern subscription thay vì cập nhật danh sách topic liên tục:

~~~java
import java.util.regex.Pattern;

var pattern = Pattern.compile(
    "^tenant-[a-z0-9-]+-orders$"
);

var container = factory.createContainer(pattern);
container.getContainerProperties().setGroupId("tenant-orders-discovery");
container.setupMessageListener(
    (MessageListener<String, OrderCreatedEvent>) record ->
        process(record.value())
);
container.start();
~~~

Pattern subscription cho phép Kafka consumer phát hiện topic mới khớp pattern thông qua metadata refresh. Nó không tạo topic và cũng không bảo đảm tenant mới đã được cấp quyền. Regex cần đủ chặt để chỉ subscribe đúng namespace ứng dụng.

Một container subscribe pattern phù hợp khi các topic có cùng contract và chính sách. Nếu mỗi tenant cần group ID, concurrency, credentials hoặc DLT riêng, hãy cân nhắc container riêng hoặc tách workload theo nhóm tenant.

## 9. Tenant dùng chung topic: định tuyến ở tầng ứng dụng

Nếu nhiều tenant cùng ghi vào topic `orders`, thường nên dùng một consumer group và định tuyến theo tenant ID trong payload:

~~~java
public record OrderCreatedEvent(
    String eventId,
    String tenantId,
    String orderId
) {}
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "orders-projection"
)
public void handle(OrderCreatedEvent event) {
    tenantAuthorizationService.requireKnownTenant(event.tenantId());

    tenantOrderService.process(
        event.tenantId(),
        event
    );
}
~~~

Trong mô hình này, consumer đọc mỗi record một lần trong group rồi chuyển đến service xử lý tenant. Không tạo container/group riêng cho mỗi tenant trên cùng topic trừ khi có lý do rõ ràng: mỗi group độc lập sẽ nhận toàn bộ record của topic và có thể lặp lại công việc cho tất cả tenant.

Kafka key có thể dùng `tenantId` để các record cùng tenant vào cùng partition theo partitioner mặc định. Tuy nhiên, điều đó không phải cơ chế bảo mật và cũng không bảo đảm một tenant chỉ có thể đọc partition của mình. Consumer group vẫn nhận partition theo assignment của Kafka.

Nếu yêu cầu cách ly dữ liệu nghiêm ngặt, dùng topic/cluster/credential/ACL phù hợp và kiểm tra quyền ở tầng nghiệp vụ. Không xem tenant ID trong payload là bằng chứng xác thực danh tính tenant.

## 10. Tenant có topic riêng: định tuyến và group ID

Với topic riêng, quy ước tên có thể là:

| Tenant key | Topic | Consumer group |
|---|---|---|
| `acme` | `tenant-acme.orders` | `orders-projection-acme` |
| `globex` | `tenant-globex.orders` | `orders-projection-globex` |
| `initech` | `tenant-initech.orders` | `orders-projection-initech` |

Cùng một topic có thể có nhiều consumer group nếu nhiều dịch vụ cần đọc độc lập. Trong một consumer group, nhiều instance chia nhau partition của topic. Do đó, group ID phải phản ánh semantics xử lý:

- Cùng một ứng dụng cần scale-out và chia partition: dùng chung group ID.
- Mỗi subscriber cần nhận bản sao độc lập: dùng group ID riêng.
- Mỗi tenant có subscription độc lập: có thể dùng group ID theo tenant.
- Không tạo group ID ngẫu nhiên mỗi lần restart nếu muốn tiếp tục offset đã commit.

Nếu tạo group ID mới cho mỗi lần đăng ký, consumer có thể đọc lại từ `auto.offset.reset` hoặc từ offset chưa tồn tại. Hãy dùng group ID ổn định theo subscriber và tenant, đồng thời có chính sách xóa group cũ khi tenant bị xóa vĩnh viễn.

## 11. Concurrency và giới hạn tài nguyên

Concurrency của container quyết định số consumer con được tạo trong một `ConcurrentMessageListenerContainer`. Một consumer chỉ được gán partition theo quy tắc consumer group; tăng concurrency vượt số partition không làm tăng mức song song hữu ích.

Ví dụ, topic có 4 partition và container concurrency là 8: tối đa 4 consumer có thể nhận partition tại cùng thời điểm; những consumer còn lại sẽ không có partition assignment.

Khi tạo container cho nhiều tenant, tổng số consumer có thể tăng nhanh:

\[
\text{Tổng consumer} \approx
\sum_{\text{tenant}} \text{concurrency của container}
\]

Nếu có 300 tenant và mỗi container concurrency 2, ứng dụng có thể tạo khoảng 600 consumer. Cần tính cả số application replica, consumer connection, thread, heartbeat, memory và số partition broker phải quản lý.

Một số chiến lược:

- Đặt giới hạn tổng số container đang chạy.
- Chỉ start container cho tenant đang active.
- Gom tenant nhỏ vào shared topic/container.
- Dùng concurrency thấp cho tenant có traffic nhỏ.
- Dùng pool/queue điều phối yêu cầu start/stop để tránh tạo hàng loạt consumer cùng lúc.
- Theo dõi consumer count, thread count, rebalance và lag.
- Dừng container không còn tenant subscription hợp lệ.

Không chọn concurrency theo số tenant. Chọn theo số partition, throughput, latency và khả năng xử lý song song của service.

## 12. Topic provisioning và lifecycle tenant

Tạo container không đồng nghĩa topic đã tồn tại. Trước khi start consumer, hệ thống cần xác minh topic được provision và cấu hình phù hợp.

Một quy trình kích hoạt tenant có thể gồm:

1. Kiểm tra tenant đã tồn tại và ở trạng thái được phép hoạt động.
2. Sinh topic name từ tenant key đã chuẩn hóa bằng resolver nội bộ.
3. Kiểm tra hoặc tạo topic theo chính sách quản trị Kafka.
4. Xác minh partition, replication factor, retention và ACL.
5. Tạo container với group ID ổn định.
6. Start container và chờ trạng thái running.
7. Ghi trạng thái subscription vào registry bền vững hoặc control plane.

Khi tenant bị ngừng:

1. Chuyển tenant sang trạng thái ngừng nhận event mới nếu nghiệp vụ yêu cầu.
2. Dừng container một cách graceful.
3. Xác minh offset đã được commit theo AckMode và chính sách xử lý.
4. Giữ topic theo retention/archival policy.
5. Xóa topic hoặc group chỉ qua quy trình quản trị riêng, không xóa tự động ngay khi container stop.

Không xóa topic chỉ vì một tenant tạm thời bị suspend. Topic có thể còn dữ liệu cần replay hoặc phục vụ audit. Lifecycle của topic và lifecycle của container cần được quản lý như hai tài nguyên riêng.

## 13. Error handling, retry và DLT cho container động

Container tạo từ factory có thể kế thừa common error handler, record converter, deserializer và các cấu hình chung đã đặt trên factory. Nếu các tenant cần chính sách khác nhau, có thể dùng factory riêng hoặc cấu hình container properties phù hợp trước khi start.

Với topic riêng theo tenant, DLT có thể theo quy ước:

- `tenant-acme.orders.DLT`
- `tenant-globex.orders.DLT`

Nếu DLT resolver thêm suffix từ topic nguồn, hãy bảo đảm topic đích được tạo và có đủ partition khi resolver giữ partition gốc. Nếu dùng DLT chung, metadata gốc phải đủ để xác định tenant, topic và subscriber sở hữu record lỗi.

Không tạo DLT theo từng exception hoặc request. Dùng naming convention ổn định và giới hạn số topic. Khi xử lý record lỗi, không tin tenant ID trong header để cấp quyền replay; xác thực tenant theo metadata đã được kiểm soát.

## 14. Bảo mật và cô lập tenant

Dynamic container thường làm tăng bề mặt cấu hình vì tên topic, group ID và tenant được xác định trong runtime.

Các nguyên tắc cần áp dụng:

- Chỉ tạo container từ tenant đã được xác thực và có trạng thái active.
- Resolve topic từ cấu hình nội bộ; không nhận topic tùy ý từ query parameter hoặc message payload.
- Validate tenant key và giới hạn ký tự/độ dài trước khi dùng trong tên topic/group.
- Cấp ACL tối thiểu cho principal của ứng dụng.
- Không chia sẻ credential rộng hơn phạm vi tenant nếu yêu cầu cách ly cần mức bảo vệ đó.
- Không log payload hoặc dữ liệu tenant nhạy cảm.
- Kiểm tra tenant ID trong payload khớp với tenant mà subscription được phép xử lý.
- Giới hạn số container để tránh một tenant tạo tài nguyên vô hạn.

Kafka ACL thường áp dụng ở cấp cluster, topic, group hoặc transactional ID tùy cơ chế xác thực/ủy quyền. Nếu nhiều tenant dùng chung một principal và principal có quyền đọc tất cả topic, việc tạo container riêng không tự tạo ra cách ly bảo mật. Cần chọn credential và ACL theo threat model và khả năng quản trị của cluster.

## 15. Quan sát và vận hành container động

Container tĩnh có ID từ annotation nên dễ tìm trong log. Container động cần có định danh ổn định để vận hành.

Nên ghi nhận:

| Metadata | Mục đích |
|---|---|
| Listener/container ID | Xác định container |
| Tenant key đã chuẩn hóa | Nhận diện subscription mà không lộ dữ liệu nhạy cảm |
| Topic hoặc pattern | Biết container đang đọc nguồn nào |
| Consumer group ID | Đối chiếu offset và assignment |
| Concurrency | Hiểu số consumer con |
| Lifecycle state | `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED` |
| Start/stop reason | Biết ai hoặc quy trình nào thay đổi subscription |
| Consumer lag | Theo dõi khả năng bắt kịp dữ liệu |
| Retry/DLT count | Phát hiện tenant có record lỗi tăng cao |

Metrics cần có số container active, số consumer thực tế, số lần start/stop thất bại, rebalance, lag theo group/topic/partition, listener error và DLT publish error.

Không dùng tenant ID có cardinality rất cao làm metric label nếu hệ thống có hàng chục nghìn tenant; số lượng time series có thể tăng mạnh. Dùng metric tổng hợp và log có correlation để tra cứu tenant cụ thể.

## 16. Kiểm thử dynamic container

Kiểm thử không chỉ xác nhận container được tạo. Cần xác minh lifecycle, subscription, group ID và việc dừng container không làm mất dữ liệu.

Các kịch bản quan trọng:

- Start container với topic hợp lệ và nhận được record.
- Gọi start hai lần cho cùng tenant không tạo hai container ngoài ý muốn.
- Hai tenant có topic riêng không xử lý nhầm record của nhau.
- Container dùng group ID ổn định sau khi ứng dụng restart.
- Stop container giải phóng consumer và ngừng nhận record mới.
- Start lại container tiếp tục từ offset theo chính sách commit.
- Topic chưa tồn tại hoặc ACL thiếu khiến start thất bại có quan sát rõ ràng.
- Subscription pattern phát hiện topic mới khớp regex.
- Concurrency không vượt giới hạn tài nguyên dự kiến.
- Shutdown ứng dụng dừng tất cả container động.
- DLT của tenant giữ đúng metadata và topic nguồn.

Có thể dùng Embedded Kafka hoặc Testcontainers để tạo topic và gửi record thật. Trong test, chờ trạng thái container và kết quả listener bằng Awaitility hoặc polling có timeout; không dùng `Thread.sleep()` cố định làm đồng bộ.

Ví dụ unit test lifecycle nên kiểm tra registry idempotent: start tenant một lần tạo một container; start lần thứ hai không tạo thêm; stop tenant loại bỏ registration. Integration test nên kiểm tra record thực tế đi qua broker và được xử lý bởi đúng container.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Không nhận được record | Container chưa start hoặc topic chưa tồn tại | Kiểm tra lifecycle, metadata topic và log consumer |
| Hai container cùng xử lý một record | Dùng group ID khác nhau trên cùng topic trong khi mong muốn chia tải | Dùng chung group ID nếu cần các instance chia partition |
| Tenant nhận dữ liệu tenant khác | Dùng chung topic nhưng thiếu kiểm tra tenant trong nghiệp vụ | Validate tenant ID và thiết kế authorization |
| Start container trùng | Không có registry hoặc thao tác start không idempotent | Dùng registry và đồng bộ lifecycle |
| Consumer tạo quá nhiều thread | Mỗi tenant có container/concurrency quá lớn | Giới hạn container, gom tenant và điều chỉnh concurrency |
| Container restart đọc lại record | Offset chưa commit hoặc group ID thay đổi | Chọn AckMode, group ID và idempotency phù hợp |
| Topic động không được subscribe | Regex không khớp hoặc metadata refresh chưa diễn ra | Kiểm tra pattern, quyền và metadata |
| DLT publish thất bại | Topic đích thiếu partition hoặc ACL/serializer sai | Provision DLT và kiểm thử resolver |
| Tenant bị cách ly giả tạo | Container riêng nhưng dùng chung principal có quyền đọc mọi topic | Thiết kế ACL/credential đúng threat model |

## 18. Checklist triển khai

- [ ] Chọn shared topic, shared container theo pattern hay container riêng cho tenant.
- [ ] Chỉ tạo container riêng khi cần subscription, group, lifecycle hoặc chính sách riêng.
- [ ] Tạo container qua `ConcurrentKafkaListenerContainerFactory`.
- [ ] Cấu hình group ID ổn định và phù hợp semantics xử lý.
- [ ] Gắn listener trước khi gọi `start()`.
- [ ] Lưu container vào registry để chống tạo trùng và hỗ trợ stop.
- [ ] Đồng bộ các thao tác start/stop/register/unregister.
- [ ] Dừng toàn bộ container khi tenant suspend và khi ứng dụng shutdown.
- [ ] Provision topic, partition, replication, retention và ACL trước khi start.
- [ ] Giới hạn concurrency và tổng số consumer.
- [ ] Không nhận topic tùy ý từ tenant hoặc payload không tin cậy.
- [ ] Xác thực tenant ID ở payload và tầng nghiệp vụ.
- [ ] Cấu hình retry, error handler và DLT theo chính sách.
- [ ] Theo dõi lifecycle state, consumer lag, rebalance và DLT.
- [ ] Kiểm thử start, stop, restart, duplicate registration và shutdown qua broker thật.

Dynamic listener container giúp Spring Kafka thích nghi với danh sách tenant hoặc topic thay đổi trong runtime. Hãy chọn topology trước, quản lý container bằng registry có lifecycle rõ ràng, giữ group ID ổn định và giới hạn tài nguyên. Khi tenant chỉ là metadata trong một topic chung, một listener định tuyến theo tenant thường đơn giản hơn; container riêng chỉ nên được tạo khi cần cách ly subscription, group, concurrency hoặc chính sách vận hành.
