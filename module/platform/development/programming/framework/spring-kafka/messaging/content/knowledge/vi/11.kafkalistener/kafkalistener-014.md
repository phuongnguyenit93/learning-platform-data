# Đặt clientIdPrefix cho listener

Khi một ứng dụng Spring Kafka có nhiều `@KafkaListener`, log và metrics cần cho biết consumer nào đang tạo request, đọc partition hoặc gặp lỗi. Kafka cung cấp thuộc tính `client.id` để nhận diện client trong log và số liệu giám sát. Spring Kafka cho phép đặt tiền tố này ngay trên listener bằng thuộc tính `clientIdPrefix` của `@KafkaListener`.

`clientIdPrefix` giúp đặt tên có chủ đích cho các Kafka consumer do listener container tạo ra. Khi listener chạy với concurrency lớn hơn một, Spring Kafka thêm hậu tố số vào prefix để mỗi consumer con có client ID riêng. Thuộc tính này phục vụ nhận diện và quan sát client; nó không quyết định consumer group, partition assignment hoặc tiến độ offset.

## 1. `client.id` dùng để làm gì?

`client.id` là tên định danh tùy chọn mà Kafka client gửi trong các request tới broker. Giá trị này hữu ích để:

- Phân biệt request và log của các ứng dụng hoặc consumer khác nhau ở phía broker.
- Nhóm metrics của Kafka client theo từng consumer instance.
- Đối chiếu log ứng dụng với metrics khi điều tra consumer chậm, lỗi kết nối hoặc tải không đồng đều.
- Nhận biết consumer nào đang tạo lưu lượng đọc trong một hệ thống có nhiều listener.

Ví dụ, hai dịch vụ cùng đọc Kafka có thể dùng các client ID như sau:

| Dịch vụ | `client.id` |
|---|---|
| Dịch vụ dựng dữ liệu đơn hàng | `orders-projection-consumer` |
| Dịch vụ tổng hợp báo cáo | `orders-analytics-consumer` |

Kafka không dùng `client.id` làm danh tính thành viên của consumer group. Đổi client ID không tự tạo group mới, không thay đổi group offset và cũng không làm thay đổi cách partition được phân phối.

## 2. Đặt `clientIdPrefix` trên `@KafkaListener`

Spring Kafka cung cấp thuộc tính `clientIdPrefix` trên `@KafkaListener`. Prefix này được dùng làm cơ sở tạo `client.id` cho Kafka consumer do listener container quản lý.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    @KafkaListener(
            id = "orders-projection-listener",
            topics = "orders.events",
            groupId = "order-projection",
            clientIdPrefix = "orders-projection"
    )
    public void consume(String payload) {
        process(payload);
    }

    private void process(String payload) {
        // Xử lý sự kiện đơn hàng.
    }
}
```

Với listener có concurrency bằng một, consumer được tạo sẽ dùng prefix làm client ID, ví dụ `orders-projection`. Thuộc tính `id` của listener là định danh endpoint trong Spring Kafka; `clientIdPrefix` là prefix cho client ID Kafka. Hai giá trị có thể giống nhau nhưng phục vụ hai mục đích khác nhau.

Nếu không khai báo `clientIdPrefix`, consumer có thể sử dụng giá trị `client.id` trong cấu hình `ConsumerFactory` hoặc cấu hình Kafka consumer. Khi cần nhận diện rõ từng listener, khai báo prefix ngay trên annotation giúp cấu hình dễ đọc và dễ đối chiếu hơn.

## 3. Hậu tố khi listener dùng concurrency

Một listener có thể tạo nhiều consumer đồng thời bằng thuộc tính `concurrency`. Khi concurrency lớn hơn một, Spring Kafka thêm hậu tố dạng `-n` vào prefix, trong đó `n` bắt đầu từ `0`.

```java
@KafkaListener(
        id = "orders-projection-listener",
        topics = "orders.events",
        groupId = "order-projection",
        clientIdPrefix = "orders-projection",
        concurrency = "3"
)
public void consume(String payload) {
    process(payload);
}
```

Với concurrency bằng ba, các consumer con có client ID:

```text
orders-projection-0
orders-projection-1
orders-projection-2
```

Mỗi consumer con có thể được gán một hoặc nhiều partition tùy số partition và partition assignor. Hậu tố chỉ giúp phân biệt client; nó không có nghĩa consumer `-0` luôn đọc partition 0 hoặc consumer `-1` luôn đọc partition 1.

Ví dụ, topic có sáu partition và concurrency bằng ba có thể phân phối hai partition cho mỗi consumer. Nếu topic chỉ có hai partition mà concurrency bằng ba, một consumer có thể không được gán partition. Việc đặt `clientIdPrefix` không làm tăng số partition và không tạo thêm khả năng đọc song song ngoài giới hạn assignment.

## 4. Dùng placeholder để đặt prefix theo môi trường

Tên client nên thể hiện dịch vụ và vai trò listener. Khi chạy nhiều instance, có thể bổ sung tên pod hoặc định danh instance để log và metrics phân biệt được các tiến trình.

`@KafkaListener` hỗ trợ property placeholder trong các thuộc tính cấu hình. Ví dụ:

```java
@KafkaListener(
        id = "orders-projection-listener",
        topics = "orders.events",
        groupId = "order-projection",
        clientIdPrefix = "${spring.application.name:orders}-projection-${HOSTNAME:local}",
        concurrency = "${app.kafka.orders.concurrency:3}"
)
public void consume(String payload) {
    process(payload);
}
```

Với ứng dụng chạy trong Kubernetes, `HOSTNAME` thường có thể phản ánh tên pod. Có thể dùng biến môi trường riêng như `POD_NAME` nếu deployment đã cấu hình biến đó. Giá trị prefix sau khi phân giải sẽ được Spring Kafka dùng để tạo client ID; concurrency ba tiếp tục tạo hậu tố `-0`, `-1`, `-2`.

Nên chọn quy ước ổn định, dễ tìm kiếm và không chứa dữ liệu nhạy cảm. Ví dụ:

```text
orders-service-projection-pod-a-0
orders-service-projection-pod-a-1
orders-service-projection-pod-b-0
orders-service-projection-pod-b-1
```

Kafka không yêu cầu mọi `client.id` phải duy nhất trên toàn cluster như yêu cầu duy nhất của static member ID. Tuy nhiên, nếu nhiều instance dùng cùng client ID, metrics hoặc log được gắn nhãn theo client ID có thể khó phân biệt. Thêm instance name giúp quan sát rõ hơn trong môi trường nhiều replica.

## 5. Phân biệt client ID với các định danh khác

Các thuộc tính định danh Kafka có tên gần nhau nhưng ý nghĩa khác nhau:

| Thuộc tính | Vai trò | Có quyết định partition assignment không? |
|---|---|---|
| `client.id` / `clientIdPrefix` | Nhận diện Kafka client trong request, log và metrics | Không |
| `group.id` | Xác định consumer group và namespace lưu offset | Có, thông qua membership và group assignment |
| `group.instance.id` | Định danh ổn định cho static member trong group | Có, ảnh hưởng membership và cơ chế static membership |
| `member.id` | Định danh thành viên consumer do group coordinator quản lý | Có, gắn với membership hiện tại |
| `@KafkaListener(id = ...)` | Định danh listener endpoint trong Spring Kafka registry | Không trực tiếp |

Ví dụ, hai consumer có thể dùng cùng `group.id=order-projection` nhưng có client ID khác nhau:

```text
group.id = order-projection

Consumer A: client.id = orders-projection-pod-a-0
Consumer B: client.id = orders-projection-pod-b-0
```

Hai consumer thuộc cùng group nên Kafka phân phối partition giữa chúng. Client ID khác nhau chỉ giúp nhận diện từng consumer trong log và metrics.

Không dùng `clientIdPrefix` thay cho `group.instance.id`. Nếu cần static membership để giảm rebalance khi restart, phải cấu hình `group.instance.id` đúng cách và bảo đảm mỗi static member trong group có ID riêng. Đặt client ID duy nhất không tạo ra static membership.

## 6. Cấu hình client ID mặc định trong Spring Boot

Nếu muốn đặt client ID cơ sở cho các consumer được tạo từ cấu hình chung, Spring Boot hỗ trợ `spring.kafka.consumer.client-id`:

```yaml
spring:
  application:
    name: orders-service
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-projection
      client-id: orders-service-consumer
      enable-auto-commit: false
```

Giá trị này được chuyển thành cấu hình `client.id` cho consumer. Với listener cần tên riêng, `clientIdPrefix` trên `@KafkaListener` cho phép đặt prefix riêng cho các consumer do container đó tạo. Khi cấu hình cả hai, prefix của listener được dùng cho consumer thuộc listener tương ứng; các consumer không có prefix riêng vẫn có thể dùng cấu hình mặc định từ `ConsumerFactory`.

Ví dụ một ứng dụng có hai listener:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders.events",
        groupId = "order-projection",
        clientIdPrefix = "orders-projection"
)
public void consumeOrder(String payload) {
    processOrder(payload);
}

@KafkaListener(
        id = "payments-listener",
        topics = "payments.events",
        groupId = "payment-projection",
        clientIdPrefix = "payments-projection"
)
public void consumePayment(String payload) {
    processPayment(payload);
}
```

Khi xem log hoặc metrics, hai luồng đọc có prefix khác nhau nên dễ nhận diện. Các listener vẫn có group ID và assignment độc lập theo cấu hình của chúng.

## 7. Quan sát client ID trong vận hành

`client.id` hữu ích nhất khi được dùng nhất quán giữa log ứng dụng, broker và hệ thống metrics. Khi điều tra một consumer chậm, hãy đối chiếu client ID với group ID, topic, partition và thời điểm xảy ra sự cố.

Một log có cấu trúc có thể bao gồm:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderConsumerLogging {

    private static final Logger log =
            LoggerFactory.getLogger(OrderConsumerLogging.class);

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection",
            clientIdPrefix = "orders-projection"
    )
    public void consume(ConsumerRecord<String, String> record) {
        log.info(
                "Kafka consumer activity: groupId={}, topic={}, partition={}, offset={}",
                "order-projection",
                record.topic(),
                record.partition(),
                record.offset()
        );
    }
}
```

Trong ví dụ, log ứng dụng cung cấp group ID và vị trí record; Kafka client metrics/broker logs cung cấp client ID thực tế. Trong hệ thống có concurrency, client ID thực tế có hậu tố theo consumer con; nếu cần log đúng client ID thực tế, hãy lấy thông tin từ Kafka consumer metrics hoặc cấu hình container/consumer tương ứng thay vì giả định prefix chính là ID cuối cùng.

Metrics Kafka client thường có nhãn `client-id`, giúp phân biệt request rate, fetch rate, bytes consumed, latency và các chỉ số consumer khác theo client. Tên metric cụ thể tùy phiên bản Kafka client và cơ chế metrics đang dùng. Spring Boot Actuator/Micrometer có thể xuất các chỉ số này nếu ứng dụng bật và cấu hình instrumentation phù hợp.

Để client ID hỗ trợ quan sát hiệu quả:

- Dùng prefix mô tả dịch vụ và vai trò listener, ví dụ `orders-projection`.
- Bổ sung instance name khi cần phân biệt nhiều replica.
- Giữ quy ước đặt tên ổn định qua các lần deploy để so sánh metrics.
- Không nhúng user ID, access token hoặc dữ liệu nhạy cảm vào client ID.
- Kết hợp client ID với group ID và partition khi tìm nguyên nhân lag hoặc rebalance.

## 8. Những nhầm lẫn thường gặp

1. **Cho rằng `clientIdPrefix` tạo consumer group mới.** Group được xác định bằng `group.id`; client ID chỉ nhận diện Kafka client.
2. **Cho rằng hậu tố `-0`, `-1` là số partition.** Đây là chỉ số consumer con do concurrency tạo ra, không phải partition ID.
3. **Dùng một prefix chung rồi mong metrics tự phân biệt pod.** Nếu nhiều instance cùng prefix và concurrency, client ID có thể trùng; hãy thêm định danh instance khi cần phân biệt.
4. **Dùng client ID thay cho `group.instance.id`.** Hai thuộc tính phục vụ mục đích khác nhau; client ID duy nhất không bật static membership.
5. **Cho rằng tăng concurrency chỉ cần đổi prefix.** Concurrency điều khiển số consumer con; prefix chỉ đặt tên cho chúng. Khả năng song song còn phụ thuộc số partition và assignment.
6. **Đổi client ID để sửa lỗi offset hoặc rebalance.** Client ID không sửa group membership, commit offset hoặc thời gian poll. Hãy kiểm tra đúng thuộc tính gây ra vấn đề.

Đặt `clientIdPrefix` giúp mỗi luồng `@KafkaListener` có danh tính rõ ràng trong log và metrics. Hãy kết hợp prefix mô tả vai trò, hậu tố concurrency do Spring Kafka tạo và định danh instance phù hợp; đồng thời giữ riêng biệt `client.id`, `group.id` và `group.instance.id` để cấu hình consumer dễ hiểu và vận hành chính xác.
