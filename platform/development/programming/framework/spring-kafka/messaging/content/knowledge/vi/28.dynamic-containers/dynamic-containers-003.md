# Đăng ký endpoint động

Trong nhiều ứng dụng, danh sách Kafka listener được biết trước khi ứng dụng khởi động và có thể khai báo trực tiếp bằng `@KafkaListener`. Tuy nhiên, một số hệ thống cần tạo subscription khi chạy: tenant mới được kích hoạt, người dùng đăng ký một luồng sự kiện, một tác vụ vận hành cần nghe topic trong thời gian giới hạn hoặc cấu hình subscription được tải từ database.

Spring Kafka hỗ trợ đăng ký listener endpoint bằng `KafkaListenerEndpointRegistry`. Mỗi endpoint mô tả listener cần chạy trên topic, partition hoặc topic pattern nào; container factory tạo consumer container tương ứng. Cách này cho phép tạo, tra cứu, dừng và gỡ container trong vòng đời ứng dụng mà không phải tự gọi `KafkaConsumer.poll()`.

## 1. Phân biệt endpoint, container và consumer group

Ba khái niệm cần được tách biệt:

- **Listener endpoint:** mô tả cấu hình subscription và message listener, ví dụ endpoint ID, group ID, topic và callback xử lý record.
- **Listener container:** thành phần Spring Kafka tạo và quản lý Kafka consumer, poll loop, thread, acknowledgment, error handler và lifecycle.
- **Consumer group:** nhóm consumer được Kafka điều phối để phân chia partition. Group ID là định danh ở phía Kafka, khác với endpoint ID của ứng dụng.

`KafkaListenerEndpointRegistry` giữ các container được tạo từ endpoint, bao gồm endpoint khai báo bằng `@KafkaListener` và endpoint đăng ký bằng code. Registry giúp tìm container theo ID và quản lý lifecycle của chúng.

| Định danh | Phạm vi | Ví dụ |
| --- | --- | --- |
| Endpoint ID | Duy nhất trong registry của một application context | `tenant-orders-42` |
| Consumer group ID | Được Kafka dùng để phối hợp consumer | `orders-tenant-42` |
| Topic | Luồng record trong Kafka | `orders` |

Không dùng endpoint ID như thể nó tự tạo ra một consumer group. Nếu nhiều endpoint có cùng group ID và cùng subscribe một topic, Kafka xem chúng là consumer trong cùng group và chia partition giữa chúng. Nếu mỗi tenant cần nhận toàn bộ record độc lập, mỗi tenant thường cần group ID riêng.

## 2. Chuẩn bị listener container factory

Endpoint động vẫn cần một `KafkaListenerContainerFactory`. Factory dùng `ConsumerFactory` để tạo consumer và áp dụng cấu hình chung như deserializer, concurrency, error handler, acknowledgment và transaction.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
class DynamicKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    dynamicOrderListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(2);
        return factory;
    }
}
```

Ví dụ đặt concurrency là hai consumer thread cho mỗi container. Concurrency thực tế bị giới hạn bởi số partition được assign và tài nguyên của ứng dụng. Nếu nhiều endpoint cùng được tạo, tổng số consumer và thread có thể tăng nhanh; không nên chọn concurrency cao chỉ vì factory cho phép.

Factory có thể dùng chung cho nhiều endpoint nếu chúng có cùng cấu hình deserializer và chính sách xử lý. Nếu mỗi loại subscription cần cấu hình bảo mật, transaction hoặc error handling khác nhau, hãy dùng factory riêng hoặc một cấu hình endpoint phù hợp.

## 3. Đăng ký endpoint bằng KafkaListenerEndpointRegistry

`SimpleKafkaListenerEndpoint` phù hợp khi ứng dụng muốn gắn trực tiếp một `MessageListener` vào endpoint. Ví dụ sau tạo một subscription cho một tenant:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.config.SimpleKafkaListenerEndpoint;
import org.springframework.kafka.listener.MessageListener;
import org.springframework.stereotype.Service;

@Service
class DynamicOrderSubscriptions {

    private final KafkaListenerEndpointRegistry registry;
    private final ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory;
    private final OrderRecordHandler orderRecordHandler;

    DynamicOrderSubscriptions(
            KafkaListenerEndpointRegistry registry,
            ConcurrentKafkaListenerContainerFactory<String, OrderCreated> factory,
            OrderRecordHandler orderRecordHandler) {
        this.registry = registry;
        this.factory = factory;
        this.orderRecordHandler = orderRecordHandler;
    }

    public synchronized void registerTenant(String tenantId) {
        String endpointId = "tenant-orders-" + tenantId;
        String groupId = "orders-tenant-" + tenantId;

        if (registry.getListenerContainer(endpointId) != null) {
            throw new IllegalStateException(
                    "Endpoint đã được đăng ký: " + endpointId);
        }

        SimpleKafkaListenerEndpoint<String, OrderCreated> endpoint =
                new SimpleKafkaListenerEndpoint<>();
        endpoint.setId(endpointId);
        endpoint.setGroupId(groupId);
        endpoint.setTopics("orders");
        endpoint.setMessageListener(
                (MessageListener<String, OrderCreated>) orderRecordHandler::handle);

        // true: khởi động container ngay sau khi đăng ký.
        registry.registerListenerContainer(endpoint, factory, true);
    }
}
```

`OrderRecordHandler` là service nghiệp vụ nhận record, ví dụ:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;

interface OrderRecordHandler {
    void handle(ConsumerRecord<String, OrderCreated> record);
}
```

Trong ví dụ, `tenantId` tạo ra endpoint ID và group ID riêng. Cách đặt tên chỉ mang tính minh họa; ứng dụng nên chuẩn hóa và kiểm tra giá trị trước khi dùng. `registerListenerContainer(endpoint, factory, true)` đăng ký endpoint vào registry và khởi động container ngay. Nếu đăng ký trước khi application context bắt đầu lifecycle, có thể dùng `false` để container được registry khởi động theo lifecycle của context.

Để dùng registry, ứng dụng cần bật hạ tầng listener của Spring Kafka. Spring Boot thường tự cấu hình hạ tầng này khi có các dependency Kafka phù hợp; ứng dụng Spring cấu hình thủ công có thể dùng `@EnableKafka` và khai báo factory/registry theo cấu hình tương ứng.

## 4. Chọn subscription theo topic, pattern hoặc partition

Endpoint có thể subscribe theo nhiều cách:

| Cách đăng ký | API trên endpoint | Khi phù hợp |
| --- | --- | --- |
| Một hoặc nhiều topic | `setTopics("orders", "payments")` | Danh sách topic đã biết |
| Topic pattern | `setTopicPattern(pattern)` | Muốn subscribe các topic khớp regex, ví dụ `tenant-.*-events` |
| Partition cụ thể | `setTopicPartitions(...)` | Cần chỉ định rõ topic-partition và offset bắt đầu |

Ví dụ dùng topic pattern:

```java
endpoint.setTopicPattern(Pattern.compile("tenant-.*-orders"));
```

Khi dùng pattern, consumer có thể phát hiện topic mới khớp biểu thức theo chu kỳ metadata refresh. Hãy giới hạn pattern đủ chặt để listener không vô tình subscribe topic ngoài phạm vi.

Với `TopicPartitionOffset`, ứng dụng có thể chỉ định partition và offset hoặc cách bắt đầu tương đối theo API của Spring Kafka. Đây là chế độ assignment cụ thể; không nên đồng thời giả định consumer group tự chia partition như khi subscribe topic thông thường. Hãy kiểm tra cấu hình group management và offset reset trước khi dùng assignment thủ công.

Đăng ký endpoint không đồng nghĩa topic đã tồn tại. Nên provision topic, partition, replication và ACL qua quy trình quản trị hạ tầng. Không dựa vào broker auto-create để tạo topic động từ dữ liệu đầu vào của người dùng.

## 5. Tra cứu, dừng, khởi động lại và gỡ container

Sau khi đăng ký, registry cho phép tra cứu container theo endpoint ID:

```java
import org.springframework.kafka.listener.MessageListenerContainer;

public void stopTenant(String tenantId) {
    String endpointId = "tenant-orders-" + tenantId;
    MessageListenerContainer container =
            registry.getListenerContainer(endpointId);

    if (container != null) {
        container.stop();
    }
}

public void startTenant(String tenantId) {
    String endpointId = "tenant-orders-" + tenantId;
    MessageListenerContainer container =
            registry.getListenerContainer(endpointId);

    if (container != null && !container.isRunning()) {
        container.start();
    }
}

public synchronized void unregisterTenant(String tenantId) {
    String endpointId = "tenant-orders-" + tenantId;
    MessageListenerContainer container =
            registry.getListenerContainer(endpointId);

    if (container != null) {
        container.stop();
        registry.unregisterListenerContainer(endpointId);
    }
}
```

`stop()` dừng container nhưng vẫn giữ đăng ký trong registry, vì vậy có thể `start()` lại. `unregisterListenerContainer(id)` gỡ container đã đăng ký khỏi registry; sau đó muốn nghe lại cần đăng ký endpoint mới. Hãy xác minh API có sẵn trong đúng phiên bản Spring Kafka đang dùng khi nâng cấp framework.

Khi dừng container, cần tính đến record đang xử lý và chính sách acknowledgment. Dùng lifecycle stop của container để Spring Kafka hoàn tất quá trình dừng; không tự đóng `KafkaConsumer` từ một thread khác. Với ứng dụng cần phản hồi nhanh, có thể cung cấp trạng thái `STARTING`, `RUNNING`, `STOPPING` và `STOPPED` thay vì coi lời gọi stop/start là trạng thái đã hoàn tất ngay lập tức.

## 6. Endpoint ID và group ID phải được quản lý riêng

Endpoint ID là khóa quản lý container trong application context. Nó phải duy nhất trong registry và ổn định để ứng dụng tra cứu hoặc gỡ đúng container. Group ID là danh tính consumer ở phía Kafka, ảnh hưởng đến việc chia partition, offset đã commit và hành vi khi consumer restart.

Hai mô hình thường gặp:

| Mục tiêu | Group ID | Kết quả |
| --- | --- | --- |
| Nhiều container chia tải trên cùng subscription | Dùng chung một group ID | Kafka phân chia partition giữa các consumer trong group |
| Mỗi tenant cần nhận toàn bộ sự kiện độc lập | Mỗi tenant có group ID riêng | Mỗi group có offset và nhận bản sao luồng record riêng |

Không tạo group ID mới mỗi lần ứng dụng restart nếu muốn tiếp tục từ offset đã commit. Group ID nên đại diện cho một subscription logic có vòng đời rõ ràng. Nếu thay group ID, consumer bắt đầu một vị trí đọc khác theo `auto.offset.reset` khi chưa có committed offset.

## 7. Tránh tạo container không giới hạn

Dynamic container hữu ích nhưng mỗi container có chi phí: consumer connection, poll loop, thread, heartbeat, metrics và bộ nhớ. Một container có concurrency cao còn tạo nhiều consumer. Nếu tạo một container cho mỗi HTTP request hoặc mỗi lần người dùng mở màn hình, số consumer có thể tăng nhanh và làm broker cùng ứng dụng quá tải.

Nên thiết kế một subscription manager có chính sách rõ ràng:

1. Xác thực tenant, topic và quyền truy cập trước khi đăng ký.
2. Dùng endpoint ID xác định và kiểm tra trùng trước khi tạo container.
3. Giới hạn số subscription và concurrency theo tenant/ứng dụng.
4. Lưu cấu hình subscription bền vững nếu cần khôi phục sau restart.
5. Dừng và gỡ container khi subscription hết hạn hoặc tenant bị vô hiệu hóa.
6. Theo dõi số container đang chạy, số consumer, lag và lỗi khởi động.

Registry là bộ quản lý trong bộ nhớ của một application context; nó không phải kho cấu hình phân tán. Nếu ứng dụng restart hoặc chạy nhiều replica, mỗi replica có registry riêng. Muốn tái tạo subscription sau restart, hãy lưu cấu hình ở database/config service rồi khôi phục khi ứng dụng khởi động. Nếu nhiều replica cùng nhận lệnh tạo subscription, cần cơ chế điều phối để tránh tạo trùng hoặc để các replica không mong muốn cùng đăng ký.

## 8. Đăng ký lúc startup và đăng ký runtime

Không phải mọi trường hợp đều cần đăng ký runtime:

- Nếu danh sách listener cố định, dùng `@KafkaListener` giúp code dễ đọc và lifecycle được framework quản lý tự nhiên.
- Nếu danh sách endpoint được xác định khi cấu hình application context, có thể dùng `KafkaListenerEndpointRegistrar` qua `KafkaListenerConfigurer` để đăng ký endpoint trong giai đoạn cấu hình.
- Nếu subscription được tạo hoặc gỡ khi ứng dụng đang chạy, dùng `KafkaListenerEndpointRegistry.registerListenerContainer()` và các API lifecycle của container.

`KafkaListenerEndpointRegistrar` chủ yếu phục vụ việc đăng ký endpoint trong quá trình cấu hình listener. `KafkaListenerEndpointRegistry` là điểm quản lý các container và hỗ trợ đăng ký runtime. Chọn đúng cơ chế giúp tránh tự quản lý container khi annotation đã đáp ứng yêu cầu.

## 9. Xử lý lỗi và cấu hình bảo mật

Container động dùng chính sách error handler của factory hoặc cấu hình endpoint tương ứng. Hãy bảo đảm listener có retry/backoff và recoverer/DLT phù hợp; việc đăng ký động không thay đổi nguyên tắc xử lý lỗi của Spring Kafka.

Các dữ liệu đầu vào dùng để tạo endpoint cần được kiểm soát:

- Không cho phép client truyền tùy ý topic hoặc regex mà không có allowlist.
- Không ghép tenant ID trực tiếp vào group ID nếu chưa chuẩn hóa ký tự và giới hạn độ dài.
- Kiểm tra quyền subscribe topic và quyền đọc dữ liệu theo tenant.
- Không coi group ID là ranh giới bảo mật; quyền truy cập phải được broker ACL và ứng dụng kiểm soát.
- Không log credential, payload nhạy cảm hoặc toàn bộ cấu hình bảo mật của consumer.

Nếu endpoint không khởi động do topic không tồn tại, ACL sai, deserializer lỗi hoặc group cấu hình sai, hãy ghi nhận endpoint ID và nguyên nhân. Có thể cung cấp trạng thái đăng ký thất bại để vận hành retry sau khi cấu hình được sửa.

## 10. Kiểm thử dynamic endpoint

Kiểm thử tích hợp nên xác minh lifecycle và hành vi Kafka thực tế:

1. Đăng ký endpoint mới; xác minh container xuất hiện trong registry và được start khi `startImmediately=true`.
2. Gửi record vào topic; xác minh đúng handler nhận record.
3. Đăng ký endpoint thứ hai cùng group ID; xác minh các consumer chia partition thay vì mỗi endpoint nhận toàn bộ record.
4. Đăng ký hai endpoint với group ID riêng; xác minh mỗi group có thể nhận toàn bộ luồng record theo offset riêng.
5. Gọi stop rồi start; xác minh container dừng và tiếp tục theo offset/group đã cấu hình.
6. Unregister endpoint; xác minh container không còn trong registry và không tiếp tục poll.
7. Thử endpoint ID trùng, topic không hợp lệ, ACL thiếu và lỗi khởi động; xác minh ứng dụng trả trạng thái rõ ràng.
8. Khởi động lại ứng dụng; xác minh subscription được tái tạo từ nguồn cấu hình bền vững nếu yêu cầu nghiệp vụ cần điều đó.

## 11. Checklist triển khai

- [ ] Đã chọn `@KafkaListener`, `KafkaListenerEndpointRegistrar` hay runtime registry đúng với thời điểm cần tạo subscription.
- [ ] Endpoint ID duy nhất trong registry và khác biệt với group ID.
- [ ] Endpoint có topic/topic pattern/partition assignment đúng yêu cầu.
- [ ] Container factory cấu hình đúng ConsumerFactory, deserializer, concurrency, acknowledgment và error handler.
- [ ] `registerListenerContainer()` dùng `startImmediately` phù hợp với lifecycle.
- [ ] Stop/start/unregister có trạng thái và xử lý record đang chạy rõ ràng.
- [ ] Group ID phản ánh đúng mô hình chia tải hoặc nhận luồng độc lập.
- [ ] Có giới hạn số container, consumer và thread.
- [ ] Topic, ACL và tenant được xác thực trước khi đăng ký.
- [ ] Subscription cần tồn tại qua restart được lưu và khôi phục từ nguồn bền vững.
- [ ] Đã kiểm thử registration, delivery, group behavior, stop/start và unregister.

`KafkaListenerEndpointRegistry` giúp tạo listener container từ endpoint trong lúc ứng dụng đang chạy. Khi endpoint ID, group ID, topic subscription và lifecycle được quản lý rõ ràng, ứng dụng có thể hỗ trợ subscription động mà vẫn tận dụng consumer factory, container, acknowledgment và error handling của Spring Kafka.
