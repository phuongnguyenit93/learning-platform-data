# Đóng consumer an toàn

Một Kafka consumer thường chạy liên tục trong nền để nhận và xử lý sự kiện. Khi ứng dụng cần dừng, ví dụ lúc deploy phiên bản mới, scale pod xuống hoặc tắt dịch vụ, consumer phải kết thúc có kiểm soát. Mục tiêu là ngừng nhận công việc mới, cho phần xử lý đang diễn ra có cơ hội hoàn tất, commit offset theo cấu hình và đóng kết nối consumer đúng cách.

Với Spring Kafka, `@KafkaListener` được quản lý bởi listener container. Container sở hữu vòng đời của Kafka consumer, bao gồm poll, phân phối record, commit offset và đóng consumer. Vì vậy, ứng dụng nên dừng container qua Spring lifecycle hoặc `KafkaListenerEndpointRegistry`, thay vì tự gọi `KafkaConsumer.close()` trên consumer mà container đang quản lý.

## 1. Vì sao cần đóng consumer an toàn?

Khi một tiến trình bị dừng đột ngột trong lúc xử lý record, có hai tình huống phổ biến:

- Record đã được xử lý nhưng offset chưa commit. Khi partition được giao cho consumer khác, record có thể được đọc và xử lý lại.
- Offset đã commit trước khi nghiệp vụ hoàn tất. Consumer mới có thể tiếp tục từ vị trí sau record đó, khiến công việc chưa hoàn thành bị bỏ qua.

Đóng consumer an toàn giúp giảm khả năng xảy ra các tình huống này bằng cách điều phối thời điểm dừng, hoàn tất listener và commit. Tuy vậy, graceful shutdown không tự tạo ra exactly-once cho mọi side effect. Nếu listener ghi database, gọi API hoặc thực hiện thao tác bên ngoài Kafka, nghiệp vụ vẫn cần transaction phù hợp hoặc idempotency để chịu được việc xử lý lại.

Ví dụ, một consumer đang xử lý `OrderPaid`:

```text
Ứng dụng nhận tín hiệu dừng
          |
          v
Ngừng nhận công việc mới / dừng listener container
          |
          v
Hoàn tất listener đang chạy và phần công việc còn lại theo cấu hình
          |
          v
Commit offset hoặc hoàn tất transaction nếu xử lý thành công
          |
          v
Đóng KafkaConsumer và rời consumer group
          |
          v
Spring context kết thúc
```

Khi consumer rời group, Kafka sẽ phân phối lại partition cho những consumer còn hoạt động. Đây là hành vi bình thường trong quá trình shutdown; mục tiêu là để việc chuyển giao diễn ra sau khi container đã kết thúc có kiểm soát.

## 2. Spring Kafka quản lý vòng đời listener container

Khi khai báo `@KafkaListener`, Spring tạo listener endpoint và đăng ký container tương ứng trong `KafkaListenerEndpointRegistry`. Container quản lý một hoặc nhiều Kafka consumer tùy cấu hình concurrency và partition assignment.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            id = "orders-listener",
            topics = "orders.events",
            groupId = "order-projection"
    )
    public void consume(String payload) {
        processOrderEvent(payload);
    }

    private void processOrderEvent(String payload) {
        // Xử lý sự kiện đơn hàng.
    }
}
```

`id` là định danh của listener endpoint trong registry. Có thể dùng ID này để lấy container và điều khiển vòng đời khi ứng dụng cần dừng một listener riêng, ví dụ tạm dừng một luồng nhập dữ liệu trong lúc bảo trì.

Thông thường, Spring quản lý lifecycle của listener container cùng ApplicationContext. Khi context đóng bình thường, container được yêu cầu dừng và đóng Kafka consumer. Nếu ứng dụng không có nhu cầu dừng listener độc lập, cơ chế lifecycle mặc định thường đã đủ; không cần tự viết một `@PreDestroy` để đóng Kafka consumer lần nữa.

## 3. Dừng listener qua KafkaListenerEndpointRegistry

Khi cần chủ động dừng một listener trước khi toàn bộ ứng dụng tắt, inject `KafkaListenerEndpointRegistry`, tìm container theo ID và gọi `stop()`.

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
class KafkaListenerControlService {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaListenerControlService.class);

    private final KafkaListenerEndpointRegistry registry;

    KafkaListenerControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            return;
        }

        container.stop();
    }
}
```

`stop()` yêu cầu container kết thúc và đợi quá trình dừng theo lifecycle của container. Có thể dùng overload `stop(Runnable callback)` nếu cần thực hiện hành động sau khi container đã dừng:

```java
container.stop(() -> log.info("orders-listener đã dừng"));
```

Đoạn code điều khiển nên chạy từ luồng quản lý hoặc luồng điều khiển riêng. Không nên gọi trực tiếp `KafkaConsumer.close()` từ listener hoặc một thread khác, vì Kafka consumer không được thiết kế để nhiều thread tùy ý cùng thao tác. Listener container là thành phần sở hữu consumer và phải điều phối việc dừng.

Nếu ứng dụng chỉ muốn ngừng nhận record tạm thời trong khi vẫn giữ container và assignment, hãy xem xét `pause()`/`resume()` của listener container. `pause()` không tương đương shutdown: container vẫn chạy, consumer vẫn tham gia group và có thể tiếp tục poll nhưng các partition được pause không cung cấp record mới cho listener theo cơ chế pause. `stop()` kết thúc container, đóng consumer và dẫn đến việc partition được giao lại.

## 4. Điều gì xảy ra với record đang xử lý?

Khi yêu cầu dừng đến trong lúc listener đang chạy, container cần phối hợp với luồng consumer. Listener đang thực thi đồng bộ thường được để chạy đến khi trả về; sau đó container hoàn tất các thao tác commit phù hợp và đóng consumer. Với record listener, một lần poll có thể đã lấy nhiều record. Container có thể còn record thuộc kết quả poll đó cần xử lý trước khi kết thúc, tùy chế độ dừng và phiên bản Spring Kafka.

Do đó, cần thiết kế listener có thời gian xử lý hữu hạn. Một listener bị treo khi gọi HTTP, truy vấn database hoặc chờ lock có thể làm quá trình shutdown kéo dài. Hãy đặt timeout cho các dependency và tránh thao tác chờ vô hạn.

### Commit offset theo acknowledgement mode

Spring Kafka quản lý thời điểm commit dựa trên acknowledgement mode. Khi dùng `AckMode.BATCH`, container thường commit offset sau khi xử lý xong các record nhận từ một lần poll. Nếu listener xử lý thành công và container có cơ hội commit trước khi đóng consumer, group có thể tiếp tục từ vị trí tiếp theo.

Nếu dùng manual acknowledgement, chỉ gọi `acknowledge()` sau khi nghiệp vụ đã hoàn tất:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
class ManualAckOrderListener {

    @KafkaListener(
            id = "manual-orders-listener",
            topics = "orders.events",
            groupId = "order-manual-projection"
    )
    public void consume(
            ConsumerRecord<String, String> record,
            Acknowledgment acknowledgment
    ) {
        processAndPersist(record.value());
        acknowledgment.acknowledge();
    }

    private void processAndPersist(String payload) {
        // Hoàn tất công việc nghiệp vụ trước khi acknowledge.
    }
}
```

Listener trên cần được cấu hình với acknowledgement mode thủ công phù hợp, ví dụ `MANUAL` hoặc `MANUAL_IMMEDIATE`. Nếu ứng dụng dừng trước khi acknowledge và offset chưa được commit, record có thể được giao lại. Đây là hành vi cần xử lý an toàn bằng idempotency hoặc transaction phù hợp.

Không nên commit offset trước khi ghi dữ liệu nghiệp vụ thành công. Nếu cần phối hợp commit offset với thao tác Kafka khác, hãy dùng Kafka transaction và transaction manager đúng mục đích. Transaction Kafka không tự động bao gồm database hoặc HTTP service bên ngoài nếu không có cơ chế phối hợp riêng.

## 5. Cấu hình thời gian shutdown

Spring Kafka có thời gian chờ shutdown cho listener container. Với Spring Boot, có thể cấu hình thời gian này trong `application.yml`. Cũng cần cấu hình thời gian chờ cho từng shutdown phase của Spring lifecycle:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
      shutdown-timeout: 30s
  lifecycle:
    timeout-per-shutdown-phase: 40s

server:
  shutdown: graceful
```

Ý nghĩa:

- `enable-auto-commit: false`: để listener container quản lý commit offset theo acknowledgement mode.
- `listener.ack-mode: batch`: commit theo batch sau khi xử lý các record nhận từ poll thành công.
- `listener.shutdown-timeout: 30s`: thời gian container chờ quá trình consumer dừng theo cấu hình Spring Kafka.
- `lifecycle.timeout-per-shutdown-phase: 40s`: giới hạn thời gian Spring chờ cho mỗi phase khi đóng context.
- `server.shutdown: graceful`: nếu ứng dụng có web server, yêu cầu web server ngừng nhận request mới và cho request đang xử lý hoàn tất theo cơ chế graceful shutdown của server.

Các giá trị trên chỉ là ví dụ. Cần chọn timeout theo thời gian xử lý thực tế và phiên bản Spring Boot/Spring Kafka. Thời gian chờ của listener container, thời gian chờ của Spring lifecycle và thời gian mà nền tảng cấp cho tiến trình trước khi kill là các giới hạn khác nhau; giới hạn bên ngoài phải đủ lớn để các bước bên trong có cơ hội hoàn tất.

Ví dụ, nếu Kubernetes gửi `SIGTERM` và chỉ cho pod 30 giây trước khi gửi `SIGKILL`, cấu hình Spring chờ 40 giây không thể bảo đảm listener có đủ 40 giây. `terminationGracePeriodSeconds` của pod cần lớn hơn tổng thời gian cần cho việc ngừng nhận request, xử lý listener đang chạy và các bước đóng ứng dụng khác.

## 6. Trình tự shutdown cho ứng dụng thực tế

Một quy trình triển khai có thể tổ chức như sau:

1. Đánh dấu instance không còn sẵn sàng nhận request mới. Với ứng dụng web, readiness probe cần phản ánh trạng thái đang shutdown.
2. Ngừng nhận công việc mới từ nguồn bên ngoài, ví dụ từ API hoặc scheduler tạo ra lệnh xử lý.
3. Yêu cầu các listener container dừng. Spring có thể thực hiện việc này khi ApplicationContext đóng; nếu cần chủ động dừng sớm, dùng `KafkaListenerEndpointRegistry`.
4. Cho listener đang chạy hoàn tất trong thời gian chờ được cấp. Mọi lời gọi database hoặc dịch vụ bên ngoài cần timeout.
5. Để container commit offset hoặc hoàn tất transaction theo acknowledgement mode và cấu hình transaction.
6. Đóng consumer, rời consumer group và cho Kafka phân phối lại partition.
7. Hoàn tất các bean và tài nguyên còn lại, sau đó tiến trình kết thúc.

Trình tự cụ thể phụ thuộc kiến trúc ứng dụng. Nếu listener cần một bean khác để hoàn tất xử lý, bean đó phải còn hoạt động trong thời gian listener dừng. Tránh đóng connection pool hoặc client phụ thuộc trước khi listener container đã kết thúc.

## 7. Retry, lỗi và khả năng xử lý lại

Graceful shutdown không bảo đảm không có record được xử lý lại. Ví dụ, listener đã ghi dữ liệu vào database nhưng tiến trình dừng trước khi commit offset. Consumer khác có thể đọc lại record. Nếu lần xử lý lại tiếp tục ghi cùng một thay đổi, dữ liệu có thể bị nhân đôi nếu nghiệp vụ không idempotent.

Một số biện pháp giúp xử lý tình huống này:

- Dùng event ID hoặc khóa nghiệp vụ duy nhất để phát hiện sự kiện đã được xử lý.
- Dùng upsert hoặc ràng buộc unique ở database khi phù hợp.
- Chỉ acknowledge/commit sau khi công việc tương ứng hoàn thành.
- Cấu hình retry và dead-letter theo chính sách lỗi; không retry vô hạn một lỗi không thể khắc phục trong lúc shutdown.
- Nếu dùng transaction, xác định rõ transaction bao phủ những tài nguyên nào và cách xử lý khi transaction rollback.

Khi shutdown xảy ra trong lúc retry hoặc backoff, thời gian chờ dừng cũng bị ảnh hưởng. Hãy chọn backoff có giới hạn, timeout dependency và thời gian shutdown đủ hợp lý. Nếu không kịp hoàn tất, để record chưa commit được giao lại thường an toàn hơn việc commit khi nghiệp vụ chưa thành công.

## 8. Phân biệt stop, pause và crash

| Hành động | Consumer container | Partition assignment | Khả năng xử lý record |
|---|---|---|---|
| `pause()` | Vẫn chạy và tiếp tục poll | Thường vẫn giữ assignment | Tạm ngừng nhận record từ partition đã pause |
| `resume()` | Tiếp tục hoạt động bình thường | Giữ assignment nếu không có thay đổi group | Nhận và xử lý record trở lại |
| `stop()` | Dừng container và đóng consumer | Consumer rời group, partition được phân phối lại | Kết thúc theo lifecycle và acknowledgement mode |
| Crash/kill đột ngột | Không có quá trình dừng có kiểm soát | Kafka phát hiện consumer rời group sau timeout hoặc đóng kết nối | Record chưa commit có thể được đọc lại; side effect đã thực hiện có thể lặp |

Nếu mục đích chỉ là bảo trì ngắn và muốn tránh rebalance, `pause()` có thể phù hợp hơn. Nếu deploy hoặc tắt instance, hãy dùng lifecycle shutdown để container đóng đúng cách. Crash là tình huống lỗi mà hệ thống vẫn phải chịu được; không nên xem graceful shutdown là cơ chế duy nhất bảo đảm độ tin cậy.

## 9. Những nhầm lẫn thường gặp

1. **Tự gọi `KafkaConsumer.close()` từ thread khác.** Consumer do Spring Kafka container sở hữu; hãy dừng container qua registry hoặc lifecycle.
2. **Cho rằng `stop()` đồng nghĩa mọi side effect đã commit.** Commit phụ thuộc acknowledgement mode, transaction và thời điểm listener hoàn tất.
3. **Cho rằng record chưa commit sẽ mất.** Khi consumer rời group, record chưa được commit thường có thể được consumer mới đọc lại, miễn dữ liệu còn trong retention.
4. **Đặt timeout bên trong dài hơn timeout của nền tảng.** Tiến trình có thể bị kill trước khi Spring hoàn tất shutdown.
5. **Đóng database client trước listener container.** Listener có thể vẫn cần dependency để kết thúc công việc đang chạy.
6. **Dùng pause như shutdown.** Pause giữ container tham gia group; stop mới kết thúc container và giải phóng assignment.
7. **Cho rằng graceful shutdown bảo đảm exactly-once.** Record có thể được xử lý lại; side effect cần idempotency hoặc transaction thích hợp.

Đóng consumer an toàn là một phần của thiết kế vận hành luồng messaging. Với Spring Kafka, hãy để listener container quản lý consumer, chọn acknowledgement mode đúng với nghiệp vụ, đặt timeout đồng bộ giữa container, Spring và nền tảng triển khai, đồng thời bảo đảm listener có thể chịu được việc xử lý lại khi shutdown không kịp hoàn tất.
