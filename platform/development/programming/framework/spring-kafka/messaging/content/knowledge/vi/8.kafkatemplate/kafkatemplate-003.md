# send vào topic và key cụ thể

`KafkaTemplate` là API gửi dữ liệu phổ biến của Spring Kafka. Khi gọi `send(topic, key, data)`, ứng dụng chỉ rõ topic nhận record, key dùng để định tuyến và payload cần gửi. Producer serialize key/value rồi chọn partition theo key nếu ứng dụng không chỉ định partition cụ thể.

Đây là cách gửi phù hợp với phần lớn luồng event: dùng ID của thực thể làm key để các record liên quan thường đi vào cùng partition, nhờ đó consumer có thể xử lý thay đổi theo thứ tự trong partition. `send` hoạt động bất đồng bộ, vì vậy ứng dụng cần theo dõi kết quả gửi và xử lý lỗi phù hợp.

## 1. Gửi record bằng KafkaTemplate

`KafkaTemplate<K, V>` là lớp hỗ trợ gửi record của Spring Kafka. Hai tham số generic mô tả kiểu key và kiểu value mà producer factory/serializer được cấu hình để xử lý.

Ví dụ, ứng dụng gửi event đơn hàng vào topic `orders.events`:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        BigDecimal total
) {}
```

Publisher sử dụng `KafkaTemplate<String, OrderCreatedEvent>`:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private static final String TOPIC = "orders.events";

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
```

Trong lệnh `send(TOPIC, event.orderId(), event)`:

- `TOPIC` là tên topic đích.
- `event.orderId()` là key của record.
- `event` là value/payload sẽ được serialize.

KafkaTemplate tạo record và chuyển cho Kafka producer gửi đến broker. Ứng dụng không cần tự tạo `ProducerRecord` trong trường hợp đơn giản chỉ cần topic, key và value.

## 2. Chọn key để định tuyến record

Key là dữ liệu định danh nhóm record liên quan. Với partitioner mặc định của Kafka producer, key sau khi serialize được dùng để tính partition. Vì vậy, nếu các event của cùng một đơn hàng đều dùng `orderId` làm key, chúng thường được định tuyến về cùng partition khi số partition, key serializer và cách partitioning không thay đổi.

Ví dụ:

| Event | Key | Mục đích |
|---|---|---|
| `OrderCreated` của O100 | `O100` | Tạo đơn hàng |
| `OrderPaid` của O100 | `O100` | Cập nhật thanh toán |
| `OrderPacked` của O100 | `O100` | Cập nhật đóng gói |
| `OrderCreated` của O200 | `O200` | Tạo đơn hàng khác |

Các event của O100 có cùng key nên có thể được ghi vào cùng partition; O200 có key khác và có thể nằm ở partition khác. Kafka giữ thứ tự record trong mỗi partition, do đó consumer có thể xử lý các thay đổi của O100 theo offset mà vẫn xử lý O200 song song.

Chọn key theo thực thể cần tuần tự hóa:

- `orderId` cho các thay đổi của đơn hàng.
- `accountId` cho các giao dịch cần áp dụng theo thứ tự trên tài khoản.
- `deviceId` cho chuỗi trạng thái của một thiết bị.
- `customerId` cho các thay đổi của hồ sơ khách hàng.

Không mặc định dùng `eventId` làm key. `eventId` định danh một lần phát sinh event; key thường cần gom nhiều event thuộc cùng một thực thể. Hai giá trị có thể khác nhau vì phục vụ hai mục đích khác nhau.

### Điều kiện để key giữ mapping ổn định

Key chỉ giúp giữ record liên quan cùng partition khi các producer tuân thủ cùng quy ước. Cần lưu ý:

1. Mọi producer phải dùng cùng cách biểu diễn và serialize key. Ví dụ, chuỗi `O100` phải được serialize nhất quán.
2. Dùng cùng partitioning strategy. Custom partitioner có thể định tuyến khác với partitioner mặc định.
3. Không thay đổi số partition một cách tùy tiện. Khi tăng partition, phép ánh xạ key có thể thay đổi; record cũ và mới của cùng key có thể nằm ở hai partition khác nhau.
4. Key không tự sắp xếp event theo nghiệp vụ. Nếu nhiều luồng cùng gửi event cho một aggregate, thứ tự append phụ thuộc thứ tự broker nhận record. Ứng dụng cần điều phối phát hành hoặc dùng sequence/version để kiểm tra thứ tự nghiệp vụ.

## 3. Các cách gọi send thường dùng

KafkaTemplate có nhiều overload để gửi record theo mức thông tin cần thiết. Những dạng thường gặp:

| Cách gọi | Ý nghĩa |
|---|---|
| `send(topic, data)` | Gửi value vào topic, không cung cấp key. |
| `send(topic, key, data)` | Gửi value với key để partitioner định tuyến. |
| `send(topic, partition, key, data)` | Chỉ định partition, key và value. |
| `send(topic, partition, timestamp, key, data)` | Chỉ định partition và timestamp cùng key/value. |
| `send(ProducerRecord)` | Gửi record đã tạo sẵn, có thể chứa headers và các trường khác. |

Trường hợp phổ biến nhất là `send(topic, key, data)`:

```java
kafkaTemplate.send("orders.events", event.orderId(), event);
```

Nếu gọi `send(topic, data)`, key sẽ là `null`. Producer vẫn gửi được record, nhưng không thể dựa vào key để giữ các event của cùng thực thể trong một partition.

### Chỉ định partition khi thật sự cần

Có thể chỉ định partition trực tiếp:

```java
int targetPartition = 2;

kafkaTemplate.send(
        "orders.events",
        targetPartition,
        event.orderId(),
        event
);
```

Partition index bắt đầu từ 0 và phải tồn tại trong topic. Khi đã chỉ định partition, producer gửi record đến partition đó thay vì để partitioner lựa chọn. Cách này hữu ích khi ứng dụng có quy tắc phân vùng riêng, nhưng cần kiểm soát để không tạo lệch tải hoặc đưa cùng key vào nhiều partition.

Nếu cần chỉ định timestamp:

```java
long eventTimestamp = event.occurredAt().toEpochMilli();

kafkaTemplate.send(
        "orders.events",
        null,             // Để partitioner chọn partition.
        eventTimestamp,
        event.orderId(),
        event
);
```

Timestamp được tính bằng mili giây từ Unix epoch. Timestamp mà consumer nhìn thấy còn phụ thuộc `message.timestamp.type` của topic (`CreateTime` hoặc `LogAppendTime`). Timestamp không thay thế offset và không tạo thứ tự tổng thể giữa các partition.

## 4. Cấu hình serializer cho key và value

Kafka lưu dữ liệu dưới dạng byte. `KafkaTemplate` cần producer factory có key serializer và value serializer phù hợp với kiểu generic của template.

Ví dụ cấu hình Spring Boot cho key kiểu `String` và value dạng JSON:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

Với cấu hình này:

- `StringSerializer` chuyển `orderId` thành byte key.
- `JsonSerializer` chuyển `OrderCreatedEvent` thành JSON byte value.

Consumer cần deserializer hoặc message converter tương ứng để giải mã value. Hai phía cần thống nhất schema và cách xử lý type header/default type. Nếu dùng kiểu key/value khác, hãy chọn serializer tương ứng; ví dụ `LongSerializer` cho key kiểu `Long` hoặc `StringSerializer` cho value kiểu `String`.

Nếu cấu hình serializer không tương thích với generic type hoặc payload thực tế, lỗi serialization có thể xảy ra ngay ở producer trước khi record được gửi đến broker. Hãy kiểm tra cả kiểu dữ liệu lúc biên dịch lẫn cấu hình serializer lúc chạy.

## 5. Gửi bất đồng bộ và nhận kết quả

`KafkaTemplate.send(...)` không chờ broker ghi xong mới trả về. Trong Spring Kafka hiện đại, các phương thức `send` trả về `CompletableFuture<SendResult<K, V>>`. Future hoàn tất khi producer nhận kết quả thành công hoặc lỗi.

Có thể xử lý kết quả ngay tại nơi gửi:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public void publish(OrderCreatedEvent event) {
    Logger log = LoggerFactory.getLogger(getClass());

    kafkaTemplate.send("orders.events", event.orderId(), event)
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    // Ghi nhận lỗi và chuyển theo chính sách retry/error handling.
                    log.error("Không gửi được event orderId={}",
                            event.orderId(), exception);
                    return;
                }

                var metadata = result.getRecordMetadata();
                log.info("Đã gửi orderId={} vào topic={}, partition={}, offset={}",
                        event.orderId(),
                        metadata.topic(),
                        metadata.partition(),
                        metadata.offset());
            });
}
```

`SendResult` cung cấp `RecordMetadata` để biết topic, partition, offset và timestamp của record đã được broker xác nhận. Thông tin này hữu ích cho log, metric và truy vết. Offset là vị trí của record trong partition, không phải ID nghiệp vụ của event.

Một cách khác là trả future về cho tầng gọi để tầng đó quyết định chờ, kết hợp hoặc xử lý lỗi:

```java
public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
        OrderCreatedEvent event) {
    return kafkaTemplate.send("orders.events", event.orderId(), event);
}
```

Không nên bỏ qua future nếu nghiệp vụ cần biết chắc việc gửi đã được broker xác nhận. Gọi `send` thành công chỉ có nghĩa producer đã nhận yêu cầu gửi; kết quả thực tế có thể thất bại do lỗi serialization, timeout, broker không sẵn sàng hoặc lỗi mạng.

## 6. Consumer nhận lại key và value

Consumer có thể nhận `ConsumerRecord<K, V>` để truy cập cả key, value và metadata Kafka:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListener {

    @KafkaListener(
            topics = "orders.events",
            groupId = "order-projection"
    )
    public void onOrderEvent(
            ConsumerRecord<String, OrderCreatedEvent> record) {

        String orderId = record.key();
        OrderCreatedEvent event = record.value();

        System.out.printf(
                "orderId=%s, partition=%d, offset=%d%n",
                orderId,
                record.partition(),
                record.offset()
        );

        // Cập nhật projection dựa trên event.
    }
}
```

Nếu listener chỉ nhận `OrderCreatedEvent`, Spring Kafka có thể chuyển payload trực tiếp theo cấu hình deserializer/converter. Dùng `ConsumerRecord` khi cần key, partition, offset, timestamp hoặc headers.

## 7. Những điều cần tránh khi gửi theo key

### Dùng key không nhất quán

Nếu producer A dùng `orderId` nhưng producer B dùng `eventId`, các event của cùng đơn hàng có thể đi vào partition khác nhau. Hãy định nghĩa key trong hợp đồng tích hợp và dùng thống nhất ở mọi producer.

### Nghĩ key bảo đảm thứ tự nghiệp vụ tuyệt đối

Key chỉ hỗ trợ định tuyến vào cùng partition. Kafka giữ thứ tự theo thứ tự record được append trong partition, nhưng không tự hiểu rằng `OrderCreated` phải đến trước `OrderPaid`. Nếu nhiều producer phát đồng thời, cần điều phối nguồn phát hoặc thêm sequence/version để consumer xác minh.

### Thay đổi partition count mà không đánh giá tác động

Tăng partition có thể làm phép băm key thay đổi. Với topic cần ordering theo aggregate, hãy lập kế hoạch migration hoặc dùng cơ chế định tuyến ổn định đã được thiết kế trước.

### Không xử lý lỗi gửi bất đồng bộ

Producer có thể gặp lỗi sau khi phương thức `send` đã trả về future. Hãy quan sát future, log lỗi có ngữ cảnh và quyết định retry hoặc chuyển xử lý lỗi theo chính sách ứng dụng. Retry cần được thiết kế để tránh gửi trùng side effect hoặc làm sai thứ tự.

## 8. Ghi nhớ

- `kafkaTemplate.send(topic, key, data)` gửi payload vào topic với key do ứng dụng chọn.
- Key sau khi serialize được partitioner dùng để định tuyến; cùng key thường vào cùng partition nếu partition count và chiến lược không đổi.
- Chọn key theo aggregate như `orderId`, `accountId` hoặc `deviceId` khi cần giữ thứ tự thay đổi của thực thể.
- `send(topic, data)` không có key; các overload khác cho phép chỉ định partition hoặc timestamp.
- Key/value serializer phải phù hợp với kiểu dữ liệu của `KafkaTemplate` và deserializer phía consumer.
- `send` là bất đồng bộ; theo dõi `CompletableFuture<SendResult<K, V>>` để biết kết quả và lấy metadata broker.
- Key không tự sắp xếp event theo nghiệp vụ; producer phải phát đúng thứ tự và consumer phải xử lý side effect phù hợp.

Khi gửi một event bằng `KafkaTemplate`, hãy chọn topic đúng hợp đồng, dùng key đại diện cho thực thể cần định tuyến, cấu hình serializer tương thích và theo dõi kết quả bất đồng bộ. Bốn quyết định này tạo nền tảng cho luồng producer có thể mở rộng mà vẫn giữ được thứ tự cần thiết trong từng partition.
