# Tách group để phát broadcast

## 1. Broadcast trong Kafka được hiểu như thế nào?

Trong Kafka, producer ghi một record vào topic. Nhiều consumer group có thể đăng ký đọc cùng topic đó và mỗi group duy trì tiến độ đọc riêng. Vì vậy, cùng một record có thể được nhiều nhóm nghiệp vụ nhận và xử lý độc lập.

Đây là cách triển khai mô hình broadcast (phát một sự kiện để nhiều subscriber độc lập cùng nhận) bằng consumer group:

- Consumer có cùng `group.id` chia nhau các partition. Các thành viên trong nhóm cạnh tranh xử lý công việc chung.
- Consumer có `group.id` khác nhau tạo thành các subscription độc lập. Mỗi group có thể đọc toàn bộ record trong topic theo offset của chính nó.
- Producer chỉ cần gửi sự kiện một lần vào topic. Kafka giữ record theo chính sách retention để các group đọc ở tiến độ riêng.

Ví dụ, khi có sự kiện `OrderCreated` trong topic `orders`, hệ thống có thể cần cập nhật màn hình đơn hàng, kiểm tra gian lận và tính toán doanh thu. Ba nghiệp vụ này đều cần nhận sự kiện, nhưng không nên chia record cho nhau vì mỗi nghiệp vụ phải thực hiện công việc riêng.

~~~mermaid
flowchart TD
    P["Order service<br/>Producer"] --> T["Topic orders"]
    T --> G1["Group: order-projection"]
    T --> G2["Group: fraud-monitor"]
    T --> G3["Group: sales-analytics"]
    G1 --> C1["Consumer instances<br/>Projection"]
    G2 --> C2["Consumer instances<br/>Fraud detection"]
    G3 --> C3["Consumer instances<br/>Analytics"]
~~~

Trong sơ đồ, mỗi group có thể đọc cùng luồng sự kiện `orders`. Bên trong từng group, nhiều consumer vẫn chia nhau partition để tăng khả năng xử lý song song. Các group không chia offset cho nhau.

Broadcast ở đây là hành vi tiêu thụ độc lập của các group. Kafka không tạo một bản sao vật lý riêng của mỗi record cho từng group; record nằm trong log của topic và các group đọc log đó theo offset riêng.

## 2. Vì sao phải tách group ID?

Giả sử topic `orders` có bốn partition và có hai dịch vụ cùng cần nhận mọi sự kiện:

- `order-projection` cập nhật dữ liệu đọc phục vụ truy vấn đơn hàng.
- `fraud-monitor` phân tích rủi ro của từng đơn hàng.

Nếu cả hai dịch vụ dùng chung `group.id=orders-service`, Kafka xem tất cả consumer của hai dịch vụ là thành viên cùng một group. Mỗi partition chỉ được giao cho tối đa một consumer trong group tại một thời điểm. Kết quả là dịch vụ projection có thể nhận một số record, còn fraud monitor nhận số khác. Cả hai dịch vụ không còn nhận đầy đủ mọi sự kiện.

Nếu tách thành hai group:

| Topic | Consumer group | Mục đích |
|---|---|---|
| `orders` | `order-projection` | Cập nhật dữ liệu đọc đơn hàng |
| `orders` | `fraud-monitor` | Phân tích gian lận |
| `orders` | `sales-analytics` | Tổng hợp số liệu bán hàng |

Mỗi group có offset riêng cho từng partition. Khi `order-projection` đã xử lý đến offset 120 của P0, `fraud-monitor` vẫn có thể đang ở offset 95 của P0. Một group chậm không làm group khác phải chờ hoặc mất tiến độ.

Quy tắc thiết kế:

- Dùng chung group ID khi các instance thực hiện cùng một nhiệm vụ và cần chia tải.
- Dùng group ID riêng khi mỗi dịch vụ hoặc nghiệp vụ cần nhận toàn bộ sự kiện để xử lý độc lập.
- Giữ group ID ổn định qua các lần triển khai để consumer tiếp tục offset đã commit.
- Phân biệt group ID giữa các môi trường nếu chúng cùng kết nối vào một Kafka cluster.

Không nên tạo group ID theo từng pod hoặc instance nếu mục tiêu là scale ngang một subscriber. Mỗi pod có group ID khác nhau sẽ trở thành một subscriber độc lập, khiến tất cả cùng đọc toàn bộ luồng và có thể lặp lại tác động nghiệp vụ.

## 3. Cấu hình nhiều consumer group trong Spring Kafka

Trong Spring Kafka, thuộc tính `groupId` của `@KafkaListener` cho phép xác định group riêng cho từng listener. Có thể khai báo tên group tập trung theo môi trường trong `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest

app:
  kafka:
    consumer:
      groups:
        order-projection: "order-projection-${spring.profiles.active:local}"
        fraud-monitor: "fraud-monitor-${spring.profiles.active:local}"
        sales-analytics: "sales-analytics-${spring.profiles.active:local}"
~~~

Listener thứ nhất tham gia group cập nhật dữ liệu đọc:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    @KafkaListener(
        topics = "orders",
        groupId = "${app.kafka.consumer.groups.order-projection}"
    )
    public void handle(OrderCreatedEvent event) {
        orderProjectionService.apply(event);
    }
}
~~~

Listener thứ hai tham gia group kiểm tra gian lận:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class FraudMonitorListener {

    @KafkaListener(
        topics = "orders",
        groupId = "${app.kafka.consumer.groups.fraud-monitor}"
    )
    public void inspect(OrderCreatedEvent event) {
        fraudDetectionService.inspect(event);
    }
}
~~~

Hai listener cùng đăng ký topic `orders`, nhưng group ID khác nhau. Khi producer gửi một `OrderCreatedEvent`, cả hai group đều có thể đọc và xử lý sự kiện đó theo tiến độ riêng.

Nếu một ứng dụng có nhiều listener, hãy chỉ định `groupId` rõ ràng cho từng subscription độc lập. Không dựa vào một group ID mặc định chung nếu các listener cần nhận toàn bộ cùng một luồng sự kiện.

### Scale từng group độc lập

Có thể chạy nhiều instance của cùng listener để chia tải trong chính group đó. Ví dụ, ba instance của dịch vụ projection đều dùng `order-projection-prod`; hai instance của fraud monitor đều dùng `fraud-monitor-prod`.

~~~mermaid
flowchart LR
    T["Topic orders<br/>P0 · P1 · P2 · P3"]
    T --> G1["order-projection-prod"]
    T --> G2["fraud-monitor-prod"]
    G1 --> A["Projection A<br/>P0, P1"]
    G1 --> B["Projection B<br/>P2, P3"]
    G2 --> C["Fraud A<br/>P0, P1"]
    G2 --> D["Fraud B<br/>P2, P3"]
~~~

Mỗi group phân chia partition bên trong nhóm của mình. Cùng một partition có thể được một consumer trong `order-projection-prod` và một consumer khác trong `fraud-monitor-prod` đọc độc lập. Giới hạn một consumer cho mỗi partition áp dụng bên trong từng group, không áp dụng xuyên qua các group.

## 4. Offset và thời điểm bắt đầu của group mới

Mỗi group lưu committed offset riêng cho từng partition. Kafka lưu thông tin offset của group trong topic nội bộ `__consumer_offsets`. Nhờ vậy, một subscriber có thể tạm dừng hoặc xử lý chậm trong khi các subscriber khác tiếp tục.

Khi tạo group mới hoặc group không còn offset hợp lệ, `auto.offset.reset` quyết định vị trí bắt đầu:

| Giá trị | Hành vi |
|---|---|
| `earliest` | Đọc từ record cũ nhất còn được giữ trong partition |
| `latest` | Bắt đầu ở cuối log khi khởi tạo vị trí đọc, thường chỉ nhận record mới được ghi sau đó |
| `none` | Phát sinh lỗi nếu không tìm thấy offset hợp lệ |

Nếu muốn subscriber mới nhận cả lịch sử đang còn trong Kafka, cấu hình `earliest` trước khi group bắt đầu đọc. Nếu chỉ muốn nhận sự kiện mới từ lúc subscriber được triển khai, có thể chọn `latest`.

`auto.offset.reset` chỉ áp dụng khi group không có offset hợp lệ. Nó không ghi đè tiến độ đã commit của một group đang tồn tại. Nếu một group cũ quay lại sau khi dừng, Kafka tiếp tục từ offset đã lưu nếu offset đó vẫn hợp lệ.

`earliest` cũng không thể khôi phục record đã bị xóa bởi retention. Vì vậy, thời gian lưu topic phải đủ dài để các subscriber chậm hoặc tạm ngừng có thể bắt kịp.

## 5. Một group chậm có ảnh hưởng group khác không?

Về tiến độ đọc, mỗi group hoạt động độc lập. Nếu `fraud-monitor` xử lý chậm, committed offset và consumer lag của nó tăng lên; `order-projection` vẫn có thể tiếp tục đọc và commit theo tốc độ riêng.

Tuy nhiên, các group vẫn dùng chung tài nguyên Kafka cluster. Một số lượng lớn group cùng đọc một topic có thể làm tăng tải đọc broker, mạng và I/O. Vì vậy, broadcast bằng nhiều group không có nghĩa chi phí bằng không.

Khi thiết kế, cần xem xét:

- **Số subscriber:** mỗi nghiệp vụ độc lập thường cần một group riêng; tránh tạo group không có người vận hành hoặc mục đích rõ ràng.
- **Retention:** giữ record đủ lâu để group chậm có thể bắt kịp.
- **Thông lượng:** theo dõi tốc độ ghi, tốc độ đọc và lag riêng của từng group.
- **Số partition:** chọn đủ partition cho mức song song mong muốn của từng subscriber quan trọng.
- **Tính độc lập:** lỗi xử lý ở một group không nên làm dừng hoặc thay đổi offset của group khác.

Nếu một subscriber không cần toàn bộ lịch sử, hãy cân nhắc `latest` khi khởi tạo group mới hoặc một quy trình replay có kiểm soát. Không đổi group ID tùy tiện để xử lý lag vì group mới có thể bắt đầu từ vị trí khác và tạo ra việc xử lý lại hoặc bỏ qua lịch sử.

## 6. Kiểm thử hành vi broadcast

Một bài kiểm thử tích hợp nên chứng minh hai điều:

1. Hai consumer group khác nhau đều nhận được cùng record được producer gửi một lần.
2. Hai consumer trong cùng một group chia việc, không phải mỗi consumer đều nhận bản sao của tất cả record.

Ví dụ với Embedded Kafka hoặc Testcontainers, tạo hai listener có group ID riêng và dùng bộ đếm hoặc test probe để chờ mỗi listener nhận cùng `eventId`:

Sự kiện kiểm thử có thể mang ID duy nhất để đối chiếu giữa các subscriber:

~~~java
public record OrderCreatedEvent(
    String eventId,
    String orderId,
    String customerId
) {}
~~~

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class BroadcastTestListeners {

    private final BlockingQueue<OrderCreatedEvent> projectionEvents =
        new LinkedBlockingQueue<>();

    private final BlockingQueue<OrderCreatedEvent> fraudEvents =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        topics = "orders",
        groupId = "test-order-projection"
    )
    public void projection(OrderCreatedEvent event) {
        projectionEvents.offer(event);
    }

    @KafkaListener(
        topics = "orders",
        groupId = "test-fraud-monitor"
    )
    public void fraud(OrderCreatedEvent event) {
        fraudEvents.offer(event);
    }

    public BlockingQueue<OrderCreatedEvent> projectionEvents() {
        return projectionEvents;
    }

    public BlockingQueue<OrderCreatedEvent> fraudEvents() {
        return fraudEvents;
    }
}
~~~

Trong test, gửi một record có `eventId` duy nhất vào topic rồi chờ cả hai queue nhận được sự kiện đó với timeout:

~~~java
import java.util.concurrent.TimeUnit;

var event = new OrderCreatedEvent(
    "evt-1001",
    "ORD-1001",
    "CUS-42"
);

kafkaTemplate.send("orders", event.orderId(), event).get(10, TimeUnit.SECONDS);

var projectionEvent =
    broadcastTestListeners.projectionEvents().poll(10, TimeUnit.SECONDS);

var fraudEvent =
    broadcastTestListeners.fraudEvents().poll(10, TimeUnit.SECONDS);

assertThat(projectionEvent).isNotNull();
assertThat(fraudEvent).isNotNull();
assertThat(projectionEvent.eventId()).isEqualTo(event.eventId());
assertThat(fraudEvent.eventId()).isEqualTo(event.eventId());
~~~

Ví dụ chỉ minh họa cách quan sát hai subscriber độc lập; test thực tế cần bảo đảm listener đã được khởi tạo, topic sẵn sàng và group thử nghiệm chưa có offset cũ ngoài dự kiến. Nên dùng topic hoặc group ID riêng cho từng test để tránh ảnh hưởng giữa các lần chạy.

## 7. Theo dõi từng consumer group

Khi vận hành broadcast, cần kiểm tra từng group riêng biệt. Kafka CLI cho phép xem committed offset, log end offset, lag và partition assignment:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-projection-prod
~~~

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group fraud-monitor-prod
~~~

So sánh hai kết quả để biết subscriber nào đang chậm hoặc không có consumer hoạt động. Lag của `fraud-monitor-prod` không phải offset của `order-projection-prod`; mỗi group có tiến độ riêng.

Các chỉ số nên theo dõi:

- Consumer lag theo từng group và partition.
- Số consumer đang hoạt động và số partition được gán.
- Tốc độ xử lý record và thời gian xử lý trung bình.
- Số lần rebalance và lỗi listener.
- Thời gian từ khi record được ghi đến khi từng subscriber xử lý xong.

## 8. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Các dịch vụ cần broadcast nhưng dùng chung `group.id` | Các dịch vụ chia record cho nhau, mỗi dịch vụ không nhận đủ sự kiện | Dùng group ID riêng theo nghiệp vụ |
| Mỗi replica dùng group ID khác nhau | Mỗi replica đọc toàn bộ topic, gây xử lý lặp ngoài ý muốn | Các replica cùng subscriber dùng chung group ID |
| Đổi group ID khi triển khai thường xuyên | Group mới có thể đọc lại lịch sử hoặc bắt đầu ở cuối log | Dùng group ID ổn định và chỉ đổi khi cần subscription mới |
| Group mới dùng `latest` trong khi cần lịch sử | Các record cũ còn trong topic có thể không được đọc | Chọn `earliest` khi cần replay dữ liệu còn retention |
| Retention ngắn hơn thời gian subscriber có thể ngừng | Subscriber không thể bắt kịp record đã hết hạn | Thiết kế retention theo thời gian phục hồi tối đa |
| Không theo dõi lag riêng từng group | Một subscriber có thể tụt lại lâu mà không được phát hiện | Dashboard và cảnh báo theo group ID |

## 9. Checklist thiết kế broadcast

- [ ] Mỗi nghiệp vụ cần nhận toàn bộ sự kiện có group ID riêng.
- [ ] Các replica của cùng một nghiệp vụ dùng chung group ID.
- [ ] Group ID ổn định và có phân biệt môi trường.
- [ ] Xác định `earliest` hay `latest` cho group chưa có offset.
- [ ] Retention đủ dài cho subscriber chậm hoặc tạm dừng.
- [ ] Đánh giá tải broker khi có nhiều group cùng đọc topic.
- [ ] Kiểm thử một record được nhiều group nhận độc lập.
- [ ] Theo dõi offset và consumer lag riêng từng group.
- [ ] Thiết kế listener idempotent để chịu được việc nhận lại record.

Tách group ID là cách đơn giản để triển khai broadcast trong Kafka: producer ghi sự kiện một lần vào topic, mỗi nghiệp vụ có một consumer group riêng để đọc độc lập, còn các replica trong cùng nghiệp vụ chia partition để xử lý song song. Nắm vững ranh giới này giúp hệ thống Spring Kafka mở rộng subscriber mà không vô tình chia sự kiện giữa các nghiệp vụ cần nhận đầy đủ dữ liệu.
