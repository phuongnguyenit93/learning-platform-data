# autoStartup và lifecycle

Spring Kafka tạo listener container cho mỗi endpoint khai báo bằng `@KafkaListener`. Container quản lý consumer, vòng lặp `poll()`, việc gọi listener và quá trình tham gia consumer group. Mặc định, container được khởi động cùng Spring application context. Thuộc tính **`autoStartup`** cho phép kiểm soát hành vi tự khởi động này; lifecycle API cho phép ứng dụng chủ động start hoặc stop container khi cần.

Khả năng điều khiển lifecycle hữu ích khi ứng dụng cần chờ dependency sẵn sàng, bật consumer theo feature flag, tạm dừng một luồng xử lý trong lúc bảo trì hoặc đóng consumer có trật tự khi ứng dụng dừng.

## 1. Listener container và autoStartup

Khi Spring xử lý `@KafkaListener`, framework đăng ký endpoint và tạo listener container thông qua `KafkaListenerEndpointRegistry`. Container quản lý Kafka consumer và chạy listener trên các consumer thread.

`autoStartup` quyết định container có tự động start trong lifecycle của Spring hay không:

- `true`: container được khởi động tự động khi application context khởi động.
- `false`: container vẫn được tạo và đăng ký, nhưng không tự start. Ứng dụng có thể start nó sau bằng lifecycle API.

Mặc định của listener container là tự khởi động. Trong annotation, `autoStartup` là thuộc tính dạng chuỗi để hỗ trợ placeholder hoặc SpEL. Nếu không khai báo thuộc tính này, container dùng giá trị mặc định từ listener container factory.

Điểm quan trọng: `autoStartup=false` không xóa endpoint và không vô hiệu hóa toàn bộ Kafka trong ứng dụng. Nó chỉ ngăn listener container tương ứng tự chạy. Các producer dùng `KafkaTemplate` hoặc consumer được tạo thủ công vẫn hoạt động theo cấu hình riêng.

## 2. Cấu hình autoStartup bằng Spring Boot

Với Spring Boot auto-configuration, có thể đặt mặc định cho listener container factory bằng `spring.kafka.listener.auto-startup`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
    listener:
      auto-startup: false
```

Trong ví dụ, các listener container dùng factory mặc định sẽ không tự khởi động. Ứng dụng có thể chủ động start từng container qua registry sau khi kiểm tra điều kiện sẵn sàng.

Nếu muốn phần lớn listener tự chạy nhưng có một listener cần khởi động muộn, hãy để mặc định là `true` và override ở annotation của listener đó. Ngược lại, nếu muốn mặc định dừng, có thể bật riêng các listener cần thiết bằng `autoStartup="true"`.

## 3. Cấu hình autoStartup ở @KafkaListener

Annotation hỗ trợ thuộc tính `autoStartup`. Ví dụ sau đặt listener không tự khởi động:

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "order-projection",
            autoStartup = "false"
    )
    public void onOrderEvent(OrderCreatedEvent event) {
        // Cập nhật projection từ event.
    }
}
```

Ở đây:

- `id="ordersListener"` là ID của listener container, dùng để tra cứu container qua registry.
- `groupId="order-projection"` là ID consumer group dùng để quản lý membership và committed offset.
- `autoStartup="false"` giữ container ở trạng thái chưa chạy khi context khởi động.

`id` và `groupId` phục vụ hai mục đích khác nhau. Đừng dùng group ID để tìm container trong registry; hãy dùng listener `id`.

Có thể điều khiển thuộc tính bằng cấu hình ngoài:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-projection",
        autoStartup = "${app.kafka.listeners.orders.auto-startup:true}"
)
public void onOrderEvent(OrderCreatedEvent event) {
    // Xử lý event.
}
```

Và trong `application.yml`:

```yaml
app:
  kafka:
    listeners:
      orders:
        auto-startup: false
```

Placeholder cho phép bật/tắt listener theo profile hoặc môi trường mà không phải sửa mã nguồn. Giá trị mặc định sau dấu `:` là `true` nếu property chưa được khai báo.

## 4. Đặt mặc định ở listener container factory

Nếu không dùng Spring Boot auto-configuration hoặc cần một factory riêng, có thể gọi `setAutoStartup(false)` trên `ConcurrentKafkaListenerContainerFactory`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreatedEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();
        factory.setConsumerFactory(consumerFactory);
        factory.setAutoStartup(false);
        factory.setConcurrency(3);
        return factory;
    }
}
```

Chỉ định factory này trong annotation:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders.events",
        groupId = "order-projection",
        containerFactory = "ordersListenerFactory"
)
public void onOrderEvent(OrderCreatedEvent event) {
    // Xử lý event.
}
```

Khi `autoStartup` không được chỉ định ở annotation, endpoint dùng giá trị từ factory. Nếu annotation có khai báo `autoStartup`, giá trị ở endpoint sẽ override mặc định của factory đó.

## 5. Quản lý container bằng KafkaListenerEndpointRegistry

Các container được tạo từ `@KafkaListener` do `KafkaListenerEndpointRegistry` quản lý. Chúng không phải các bean độc lập để lấy bằng `applicationContext.getBean(...)` theo class container. Hãy inject registry rồi tìm container theo `id` của annotation.

Ví dụ service điều khiển listener:

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class KafkaListenerLifecycleService {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerLifecycleService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void startOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null) {
            throw new IllegalStateException("Không tìm thấy ordersListener");
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
```

`getListenerContainer(id)` trả về container nếu ID tồn tại, hoặc `null` nếu không tìm thấy. Kiểm tra kết quả trước khi gọi lifecycle method để tránh lỗi khi ID bị đổi hoặc endpoint chưa được đăng ký.

Registry cũng cung cấp danh sách ID và các container đã đăng ký, hữu ích khi cần hiển thị trạng thái hoặc điều khiển nhiều listener. Chỉ nên start/stop những container mà ứng dụng thực sự có quyền điều khiển.

## 6. Khởi động listener sau khi ứng dụng sẵn sàng

Một trường hợp thường gặp là consumer chỉ được phép bắt đầu đọc sau khi ứng dụng đã khởi tạo database, cache hoặc dependency khác. Có thể đặt `autoStartup=false`, sau đó start listener khi Spring phát `ApplicationReadyEvent`:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class KafkaListenerStartup {

    private final KafkaListenerLifecycleService lifecycleService;

    public KafkaListenerStartup(KafkaListenerLifecycleService lifecycleService) {
        this.lifecycleService = lifecycleService;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        lifecycleService.startOrdersListener();
    }
}
```

`ApplicationReadyEvent` được phát khi Spring Boot hoàn tất quá trình khởi động ứng dụng. Cách này phù hợp khi listener phải chờ toàn bộ bước startup và application runners hoàn thành. Nếu chỉ cần chờ một dependency cụ thể, có thể dùng cơ chế readiness hoặc lifecycle riêng của dependency đó thay vì trì hoãn tất cả listener đến cuối startup.

Không đặt `autoStartup=false` rồi quên start listener. Khi container chưa chạy, ứng dụng vẫn có thể báo trạng thái HTTP healthy nhưng consumer group không nhận record. Hãy đưa trạng thái listener quan trọng vào health/readiness hoặc monitoring phù hợp.

## 7. Phân biệt start/stop với pause/resume

Lifecycle và pause/resume giải quyết hai nhu cầu khác nhau:

| Thao tác | Hành vi | Consumer group |
|---|---|---|
| `start()` | Khởi chạy container và consumer thread. | Consumer tham gia group, nhận partition assignment. |
| `stop()` | Dừng container, đóng consumer và rời group. | Partition có thể được rebalance sang member khác. |
| `pause()` | Tạm ngừng nhận record mới từ partition qua consumer pause; container vẫn duy trì vòng poll cần thiết. | Consumer tiếp tục duy trì membership/assignment trong lúc pause. |
| `resume()` | Tiếp tục nhận record sau khi pause. | Giữ assignment hiện tại nếu group không có thay đổi khác. |

Nếu cần bảo trì ngắn hoặc điều tiết tải trong khi vẫn muốn giữ membership, pause/resume thường phù hợp hơn stop/start. Nếu muốn giải phóng consumer và cho member khác nhận partition, dùng stop.

Pause không nhất thiết dừng xử lý record đang chạy tại thời điểm gọi. Hãy thiết kế để listener hiện tại hoàn tất an toàn và kiểm tra API pause/resume của phiên bản Spring Kafka đang sử dụng.

## 8. Graceful shutdown và lifecycle của Spring

Listener container tham gia lifecycle của Spring thông qua `KafkaListenerEndpointRegistry` và cơ chế `SmartLifecycle`. Khi application context đóng bình thường, registry dừng các container do nó quản lý để consumer ngừng poll và giải phóng tài nguyên.

Trong lúc shutdown:

1. Ứng dụng ngừng nhận công việc mới theo quy trình stop của container.
2. Listener đang xử lý được tạo cơ hội hoàn tất theo cấu hình shutdown và thời gian chờ của container.
3. Consumer đóng và rời group; coordinator có thể rebalance partition cho member còn lại.
4. Producer và các tài nguyên Spring khác tiếp tục đóng theo lifecycle của chúng.

Không nên gọi `System.exit()` hoặc kill process ngay sau khi yêu cầu stop nếu muốn graceful shutdown. Hãy để Spring context đóng bình thường và cấu hình thời gian dừng phù hợp với thời gian xử lý tối đa của listener. Nếu listener gọi hệ thống bên ngoài, cần bảo đảm side effect idempotent và xử lý được việc record được giao lại sau khi consumer dừng đột ngột.

`stop()` đồng bộ có thể chờ container dừng; API lifecycle cũng hỗ trợ callback khi quá trình stop hoàn tất. Với orchestration hoặc endpoint quản trị, hãy tránh giữ request thread quá lâu nếu shutdown cần thời gian, và chỉ báo trạng thái dừng hoàn tất khi container thực sự đã dừng.

## 9. Kiểm tra trạng thái listener

Có thể đọc trạng thái container qua registry:

```java
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");

if (container != null) {
    boolean running = container.isRunning();
    // Ghi nhận trạng thái cho health indicator hoặc monitoring.
}
```

Registry có thể cung cấp `getListenerContainerIds()`, `getListenerContainers()` và `getAllListenerContainers()` để quan sát listener đã đăng ký. Lưu ý rằng `isRunning()` chỉ cho biết trạng thái lifecycle của container; nó không khẳng định consumer đang có partition assignment, không có lag hoặc đang xử lý thành công. Muốn đánh giá sức khỏe đầy đủ, cần kết hợp consumer group state, lag, lỗi listener và trạng thái dependency.

## 10. Kiểm thử autoStartup và lifecycle

Với integration test, nên kiểm tra rõ hai tình huống:

- Khi `autoStartup=false`, container được đăng ký nhưng không chạy ngay sau khi context khởi tạo.
- Sau khi gọi `start()`, consumer bắt đầu nhận record; sau `stop()`, consumer dừng theo lifecycle.

Ví dụ kiểm tra trạng thái container:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;

import static org.assertj.core.api.Assertions.assertThat;

class ListenerLifecycleTest {

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Test
    void startsAndStopsListenerOnDemand() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        assertThat(container).isNotNull();
        assertThat(container.isRunning()).isFalse();

        container.start();
        assertThat(container.isRunning()).isTrue();

        container.stop();
        assertThat(container.isRunning()).isFalse();
    }
}
```

Đây là ví dụ khung; test hoàn chỉnh cần tạo Spring context với `autoStartup=false`, cấu hình broker test/Embedded Kafka và bảo đảm container đã hoàn tất chuyển trạng thái trước khi assert nếu môi trường khởi động bất đồng bộ. Nên có thêm test gửi một record sau khi start để xác nhận listener thực sự nhận được dữ liệu.

## 11. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Listener không nhận record sau khi ứng dụng khởi động | `autoStartup=false` nhưng chưa gọi `start()`. | Dùng registry để start container hoặc bật auto startup. |
| Không tìm thấy container qua registry | Dùng nhầm group ID thay vì listener ID, hoặc ID không được khai báo như dự kiến. | Đặt `id` rõ ràng trong `@KafkaListener` và tra cứu đúng ID. |
| Một listener vẫn tự chạy dù factory đặt `autoStartup=false` | Annotation đã override bằng `autoStartup="true"`. | Kiểm tra cấu hình ở cấp endpoint và placeholder. |
| Đổi property nhưng listener không đổi trạng thái khi ứng dụng đang chạy | Placeholder được phân giải khi endpoint/container được tạo; thay file cấu hình không tự cập nhật lifecycle. | Dùng actuator/management flow hoặc cơ chế cấu hình động được thiết kế riêng. |
| Gọi `stop()` nhưng partition được giao cho consumer khác | Consumer đã rời group và coordinator rebalance. | Đây là hành vi bình thường; bảo đảm xử lý/commit an toàn trước khi stop. |
| `isRunning()` là true nhưng không có record | Container có thể chưa được gán partition, topic chưa có dữ liệu hoặc consumer có lag/lỗi khác. | Kiểm tra assignment, group state, lag, subscription và log listener. |
| Shutdown bị kéo dài | Listener đang xử lý lâu hoặc dependency bên ngoài không phản hồi. | Đặt timeout hợp lý, giới hạn thời gian I/O và hỗ trợ hủy/hoàn tất công việc an toàn. |

## 12. Ghi nhớ

- `autoStartup` quyết định listener container có tự khởi động cùng Spring context hay không; mặc định thường là `true`.
- `spring.kafka.listener.auto-startup` đặt mặc định cho factory do Spring Boot cấu hình.
- `@KafkaListener(autoStartup="...")` có thể override mặc định của factory và hỗ trợ property placeholder/SpEL.
- Đặt `id` ổn định cho listener để tìm container qua `KafkaListenerEndpointRegistry`; listener ID khác consumer group ID.
- Dùng `start()`/`stop()` để quản lý lifecycle; dùng `pause()`/`resume()` khi cần tạm ngừng nhận record mà vẫn giữ consumer membership.
- Spring quản lý listener container qua registry và dừng chúng trong lifecycle của application context.
- `isRunning()` không thay thế kiểm tra assignment, lag và lỗi xử lý.
- Nếu tắt auto startup, phải có quy trình start rõ ràng và kiểm thử để tránh listener bị bỏ quên.

Khi thiết kế lifecycle cho listener, hãy xác định thời điểm consumer được phép tham gia group, ai chịu trách nhiệm start/stop và hệ thống sẽ xác nhận trạng thái hoạt động ra sao. Một cấu hình `autoStartup` rõ ràng kết hợp registry, readiness và graceful shutdown giúp luồng Kafka khởi động đúng lúc và dừng an toàn.

## Tài liệu tham khảo

- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — @KafkaListener Annotation](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html)
- [Spring Boot — Kafka Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#application-properties.integration.spring.kafka.listener.auto-startup)
