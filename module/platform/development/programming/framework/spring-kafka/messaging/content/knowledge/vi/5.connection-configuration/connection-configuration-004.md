# Cấu hình consumer cơ bản trong Spring Kafka

Consumer là thành phần đọc record từ Kafka và chuyển chúng tới logic xử lý của ứng dụng. Trong Spring Kafka, cấu hình consumer thường được khai báo qua `spring.kafka.consumer` trong `application.yml` hoặc `application.properties`; `@KafkaListener` dùng cấu hình đó để tạo listener container và quản lý vòng đời Kafka consumer.

Một cấu hình cơ bản cần xác định broker, consumer group, deserializer, chính sách bắt đầu đọc khi chưa có offset hợp lệ và cách commit offset sau khi xử lý. Các thông số poll và concurrency giúp điều chỉnh khả năng tiêu thụ khi tải tăng.

## 1. Luồng khởi tạo và nhận record

Khi ứng dụng Spring Boot khởi động, Spring Kafka tạo `ConsumerFactory` từ cấu hình consumer. Listener container được tạo cho mỗi phương thức `@KafkaListener`; container dùng consumer từ factory để đăng ký vào group, nhận partition được phân công và gọi phương thức listener khi có record.

```mermaid
flowchart TD
    A[application.yml] --> B[Spring Boot Kafka properties]
    B --> C[ConsumerFactory]
    C --> D[Listener container]
    D --> E[Kafka consumer]
    E --> F[Join consumer group]
    F --> G[Nhận partition và poll record]
    G --> H[Deserializer tạo key/value Java]
    H --> I[Record converter và listener adapter]
    I --> J[@KafkaListener]
    J --> K[Xử lý nghiệp vụ]
    K --> L[Commit offset theo AckMode]
```

Kafka client thực hiện giao tiếp với broker, poll record và quản lý vị trí đọc. Spring Kafka quản lý listener container, chuyển record tới phương thức ứng dụng và điều phối acknowledgment/commit theo cấu hình. Phân biệt hai lớp này giúp xác định đúng nơi cần đặt một thuộc tính cấu hình.

## 2. Cấu hình tối thiểu trong application.yml

Ví dụ sau dùng chuỗi làm key và value để tập trung vào các thuộc tính consumer cơ bản:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: orders-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
    listener:
      ack-mode: record
      concurrency: 3

app:
  kafka:
    topics:
      orders: orders
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `bootstrap-servers` | Địa chỉ một hoặc nhiều broker để client tìm cụm Kafka và lấy metadata |
| `consumer.group-id` | Định danh consumer group; các consumer cùng group chia nhau partition và dùng tiến độ đọc chung theo từng partition |
| `key-deserializer` | Chuyển byte của key thành kiểu Java |
| `value-deserializer` | Chuyển byte của value thành kiểu Java |
| `auto-offset-reset` | Chính sách khi group không có offset hợp lệ hoặc offset không còn khả dụng |
| `enable-auto-commit` | Bật/tắt cơ chế commit tự động của Kafka client |
| `listener.ack-mode` | Cách listener container xác định thời điểm commit offset |
| `listener.concurrency` | Số consumer container con cho listener trong một instance ứng dụng |

`bootstrap-servers` nên được đưa ra biến môi trường để cùng một bản build có thể chạy ở local, staging và production với các cụm Kafka khác nhau. Một broker trong danh sách chỉ là điểm khởi đầu; client sẽ lấy metadata để kết nối các broker cần thiết.

## 3. Consumer group và group-id

`group.id` xác định danh tính logic của một nhóm consumer. Các consumer có cùng group ID và cùng subscription sẽ tham gia cơ chế phân công partition. Mỗi partition được giao cho tối đa một consumer trong cùng group ở trạng thái ổn định; các group khác nhau có thể đọc cùng topic với offset độc lập.

Ví dụ, một topic `orders` có thể được đọc bởi các group riêng:

```text
Topic: orders
  ├── orders-service       -> cập nhật read model
  ├── billing-service      -> tạo dữ liệu thanh toán
  └── analytics-service    -> tổng hợp số liệu
```

Tên group nên phản ánh một ứng dụng hoặc một luồng xử lý logic. Nếu hai instance của cùng một dịch vụ cần chia tải, chúng thường dùng chung group ID. Nếu hai ứng dụng cần nhận độc lập mọi sự kiện, chúng cần group ID khác nhau.

Có thể đặt group ID ở cấu hình chung:

```yaml
spring:
  kafka:
    consumer:
      group-id: orders-service
```

Hoặc chỉ định tại listener:

```java
@KafkaListener(
        topics = "${app.kafka.topics.orders}",
        groupId = "orders-audit"
)
public void audit(String value) {
    // Xử lý độc lập trong group orders-audit.
}
```

`groupId` trên `@KafkaListener` xác định group cho listener đó và có thể ghi đè group ID được cấu hình chung. Nếu không khai báo riêng, listener sử dụng group ID từ consumer factory. Tránh vô tình đặt một group ID khác nhau cho từng instance khi mục tiêu là scale theo chiều ngang; điều đó khiến mỗi instance hoạt động như một group độc lập và cùng đọc toàn bộ luồng.

## 4. Deserializer: chuyển byte thành kiểu dữ liệu ứng dụng

Kafka lưu record dưới dạng byte. Consumer cần deserializer tương ứng với cách producer đã serialize dữ liệu.

| Dữ liệu | Serializer phía producer | Deserializer phía consumer |
|---|---|---|
| Chuỗi | `StringSerializer` | `StringDeserializer` |
| Byte array | `ByteArraySerializer` | `ByteArrayDeserializer` |
| Số nguyên 32-bit | `IntegerSerializer` | `IntegerDeserializer` |
| Số nguyên 64-bit | `LongSerializer` | `LongDeserializer` |
| JSON object theo Spring Kafka | `JsonSerializer` | `JsonDeserializer` |

Kiểu generic của listener cần phù hợp với kiểu mà deserializer trả về. Nếu consumer dùng `StringDeserializer`, listener nên nhận `String` hoặc `ConsumerRecord<K, String>`. Nếu consumer dùng `JsonDeserializer<OrderCreated>`, listener có thể nhận `OrderCreated` hoặc `ConsumerRecord<K, OrderCreated>`.

### Cấu hình JSON deserializer

Với event có cấu trúc, có thể dùng JSON deserializer của Spring Kafka:

```yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.value.default.type: com.example.orders.OrderCreated
        spring.json.trusted.packages: com.example.orders
```

`spring.json.value.default.type` chỉ định kiểu mặc định cho value khi deserializer cần kiểu đích và không lấy được kiểu phù hợp từ type header. Với hệ thống có nhiều loại event, cần dùng type mapping hoặc một chiến lược deserialization đa kiểu rõ ràng. Không nên ép tất cả event về một class nếu topic chứa nhiều schema khác nhau.

`spring.json.trusted.packages` giới hạn các package mà JSON deserializer được phép dùng khi diễn giải type metadata. Chỉ tin cậy package thuộc ứng dụng hoặc nguồn mà hệ thống kiểm soát. Không nên mở rộng thành `*` một cách tùy tiện.

Nếu producer không dùng `JsonSerializer` của Spring Kafka hoặc không gửi type header, hãy cấu hình kiểu mặc định hoặc converter theo schema đã thống nhất. Consumer và producer phải đồng ý về định dạng byte, schema và version event; cùng gọi payload là JSON không đủ để bảo đảm hai bên tương thích.

## 5. auto-offset-reset và vị trí bắt đầu đọc

Kafka lưu offset đã commit cho từng group và partition. Khi group chưa có offset hợp lệ, hoặc offset đã commit không còn nằm trong vùng dữ liệu có thể đọc, `auto.offset.reset` quyết định cách consumer bắt đầu.

Các lựa chọn thường dùng:

| Giá trị | Hành vi |
|---|---|
| `earliest` | Bắt đầu từ offset sớm nhất còn được lưu trong partition |
| `latest` | Bắt đầu từ dữ liệu mới ở cuối partition |
| `none` | Ném lỗi nếu không tìm thấy offset hợp lệ |

Ví dụ:

```yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
```

Điểm quan trọng: `auto-offset-reset` **không phải** lệnh tua lại một group đã có offset hợp lệ. Nếu group đã commit offset, consumer tiếp tục từ offset đó. Đổi `latest` thành `earliest` không tự làm group đọc lại toàn bộ topic.

Để đọc lại dữ liệu, có thể dùng một group ID mới, hoặc chủ động reset offset bằng công cụ quản trị Kafka khi consumer group đã ở trạng thái phù hợp. Reset offset là thao tác vận hành có ảnh hưởng đến tiến độ xử lý; cần xác định rõ partition và offset đích trước khi thực hiện.

Chọn chính sách theo mục đích:

- `earliest` phù hợp với consumer mới cần dựng lại dữ liệu từ phần lịch sử còn lưu.
- `latest` phù hợp với consumer chỉ quan tâm sự kiện phát sinh sau khi bắt đầu chạy.
- `none` phù hợp khi thiếu offset là lỗi cấu hình hoặc lỗi vận hành cần được phát hiện rõ ràng.

## 6. Commit offset và acknowledgment mode

Commit offset ghi nhận vị trí tiếp theo mà group cần đọc. Nếu xử lý record offset `25` thành công, commit `26` nghĩa là lần đọc tiếp theo bắt đầu từ `26`.

Với Spring Kafka, nên để listener container quản lý commit và đặt `enable-auto-commit: false` để tránh Kafka client tự commit theo bộ đếm thời gian trong lúc logic nghiệp vụ có thể chưa hoàn tất.

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Các chế độ acknowledgment phổ biến:

| AckMode | Thời điểm commit do container quản lý |
|---|---|
| `RECORD` | Sau khi từng record được listener xử lý thành công |
| `BATCH` | Sau khi các record của một lần poll được xử lý thành công |
| `MANUAL` | Ứng dụng gọi `Acknowledgment.acknowledge()`; container xử lý commit theo cơ chế manual |
| `MANUAL_IMMEDIATE` | Yêu cầu commit ngay khi ứng dụng gọi acknowledge, tùy ngữ cảnh thread và cấu hình |

Ví dụ `RECORD` dễ hiểu với listener xử lý từng event. `BATCH` có thể giảm số lần commit khi xử lý theo lô. Chế độ manual hữu ích khi ứng dụng cần quyết định thời điểm acknowledgment, nhưng phải hiểu rõ thứ tự xử lý và hành vi commit của container.

Ví dụ listener xử lý một record:

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "orders")
    public void onOrder(OrderCreated event) {
        // Xử lý nghiệp vụ. Nếu phương thức kết thúc bình thường,
        // container có thể commit theo AckMode đã cấu hình.
    }
}
```

Nếu listener ném exception, kết quả retry, recovery và commit phụ thuộc error handler cùng cấu hình container. Không nên cho rằng record lỗi sẽ luôn được retry vô hạn hoặc luôn tự động chuyển sang dead-letter topic; các hành vi đó cần được cấu hình riêng.

### Vì sao cần xử lý idempotent?

Nếu ứng dụng xử lý xong nhưng dừng trước khi commit, record có thể được đọc lại. Vì vậy, consumer thông thường nên chịu được việc cùng một event được giao nhiều lần. Có thể dùng `eventId` duy nhất, unique constraint trong database hoặc inbox table để ngăn tác động nghiệp vụ bị lặp.

Commit trước khi xử lý xong có thể khiến group bỏ qua record sau sự cố; commit sau xử lý thường ưu tiên tránh mất xử lý nhưng cho phép duplicate. Commit Kafka và transaction database không tự động là một transaction nguyên tử nếu không có thiết kế phối hợp riêng.

## 7. Cấu hình poll và giới hạn xử lý

Kafka consumer gọi `poll()` để lấy record. Một số thuộc tính quan trọng kiểm soát lượng dữ liệu nhận mỗi lần và khoảng thời gian consumer được phép không poll.

| Thuộc tính Kafka client | Ý nghĩa | Khi cần điều chỉnh |
|---|---|---|
| `max.poll.records` | Số record tối đa trả về trong một lần poll | Khi batch quá lớn hoặc quá nhỏ so với năng lực xử lý |
| `max.poll.interval.ms` | Khoảng tối đa giữa các lần gọi poll trước khi consumer bị xem là không còn tiến triển | Khi xử lý batch lâu và cần đánh giá lại thời gian xử lý |
| `session.timeout.ms` | Thời gian broker chờ heartbeat trước khi xem consumer mất kết nối | Khi cần điều chỉnh phát hiện consumer chết và điều kiện mạng |
| `heartbeat.interval.ms` | Chu kỳ consumer gửi heartbeat | Khi điều chỉnh cùng session timeout theo yêu cầu client |
| `fetch.min.bytes` | Lượng dữ liệu tối thiểu broker cố gắng gom cho một fetch | Khi tối ưu throughput và độ trễ đọc |
| `fetch.max.wait.ms` | Thời gian broker chờ để đáp ứng fetch tối thiểu | Khi cân bằng độ trễ với gom dữ liệu |

Có thể đặt các thuộc tính Kafka client chưa có property riêng trong `spring.kafka.consumer.properties`:

```yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 100
        max.poll.interval.ms: 300000
        session.timeout.ms: 15000
        heartbeat.interval.ms: 5000
```

Các giá trị trên chỉ là ví dụ để minh họa cách khai báo, không phải cấu hình tối ưu chung. Nếu một batch cần nhiều thời gian hơn `max.poll.interval.ms`, consumer có thể rời group và kích hoạt rebalance. Có thể giảm `max.poll.records`, tối ưu xử lý, hoặc tăng khoảng poll phù hợp với SLA và thời gian xử lý thực tế.

`session.timeout.ms` và `max.poll.interval.ms` giải quyết hai tình huống khác nhau. Session timeout phát hiện mất heartbeat; max poll interval phát hiện consumer không gọi poll đủ thường xuyên. Không nên tăng cả hai một cách máy móc vì có thể làm thời gian phát hiện sự cố dài hơn.

## 8. Concurrency và số partition

Spring Kafka cho phép cấu hình số consumer con cho một listener container:

```yaml
spring:
  kafka:
    listener:
      concurrency: 3
```

Nếu một instance ứng dụng chạy listener với concurrency bằng ba, container có thể tạo ba consumer trong group. Với topic có sáu partition, ba consumer có thể chia nhau partition. Nếu topic chỉ có hai partition, tối đa hai consumer nhận partition trong trạng thái ổn định; consumer còn lại không có partition để đọc topic đó.

Khi chạy nhiều instance, tổng số consumer được tạo là tổng concurrency của các instance cho listener đó. Mức song song hữu ích của một group bị giới hạn bởi số partition mà group đăng ký đọc. Thêm consumer vượt quá giới hạn này không làm tăng throughput.

Concurrency cao hơn cũng tiêu thụ thêm kết nối, thread và tài nguyên xử lý. Hãy chọn concurrency dựa trên partition count, tốc độ xử lý, tài nguyên ứng dụng và lag đo được. Nếu listener đăng ký nhiều topic, cần tính tổng partition trong subscription thay vì chỉ nhìn một topic riêng lẻ.

## 9. Listener nhận payload và metadata

Sau khi deserializer chuyển byte thành kiểu Java, `@KafkaListener` có thể nhận payload trực tiếp:

```java
@Component
public class OrderListener {

    @KafkaListener(topics = "${app.kafka.topics.orders}")
    public void onOrder(OrderCreated event) {
        // Xử lý event đã được deserialize.
    }
}
```

Nếu cần topic, partition, offset hoặc key, nhận `ConsumerRecord`:

```java
@KafkaListener(topics = "${app.kafka.topics.orders}")
public void onOrder(ConsumerRecord<String, OrderCreated> record) {
    OrderCreated event = record.value();
    String orderId = record.key();
    String topic = record.topic();
    int partition = record.partition();
    long offset = record.offset();

    // Log tọa độ record khi cần truy vết.
}
```

Hoặc nhận payload cùng các header cần thiết:

```java
@KafkaListener(topics = "${app.kafka.topics.orders}")
public void onOrder(
        @Payload OrderCreated event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic,
        @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
        @Header(KafkaHeaders.OFFSET) long offset) {

    // Xử lý event với metadata.
}
```

Chọn kiểu tham số theo dữ liệu listener thực sự cần. Nếu chỉ cần payload, kiểu POJO giữ phương thức gọn và ít phụ thuộc Kafka. Nếu cần metadata để truy vết, dùng `ConsumerRecord` hoặc `@Header`.

## 10. Tách cấu hình theo môi trường

Không nên ghi cứng địa chỉ broker hoặc thông tin xác thực trong mã nguồn. Dùng biến môi trường và Spring profile để thay đổi kết nối theo môi trường.

Ví dụ `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    consumer:
      group-id: ${KAFKA_CONSUMER_GROUP:orders-service}
```

Môi trường production có thể cung cấp biến `KAFKA_BOOTSTRAP_SERVERS` và `KAFKA_CONSUMER_GROUP` qua hệ thống triển khai. Không commit password, token, private key hoặc JAAS config chứa secret vào Git.

Nếu cụm Kafka yêu cầu SASL hoặc TLS, khai báo các thuộc tính client tương ứng trong cấu hình Spring Kafka hoặc secret store của nền tảng triển khai. Ví dụ, các thuộc tính `security.protocol`, `sasl.mechanism`, `sasl.jaas.config` và `ssl.*` thuộc cấu hình Kafka client; giá trị bí mật cần được inject lúc chạy. Chỉ bật `security.protocol: SASL_SSL` khi broker và tài khoản đã được cấu hình tương ứng.

Có thể dùng profile riêng:

```yaml
# application-local.yml
spring:
  kafka:
    bootstrap-servers: localhost:9092

---
# application-prod.yml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
```

Kích hoạt profile bằng `SPRING_PROFILES_ACTIVE=prod` hoặc cấu hình tương đương trong môi trường chạy. Cần bảo đảm profile production có đủ thông tin broker, group ID, deserializer và bảo mật.

## 11. Cấu hình isolation khi producer dùng transaction

Nếu producer gửi record trong Kafka transaction và consumer chỉ được phép nhìn thấy record đã commit, đặt isolation level thành `read_committed`:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

`read_committed` khiến consumer chỉ đọc các record thuộc transaction đã commit và dừng ở last stable offset khi còn transaction chưa kết thúc. `read_uncommitted` cho phép đọc cả record từ transaction chưa commit hoặc đã abort; đây là hành vi mặc định của Kafka client. Isolation level này chỉ liên quan đến transaction của Kafka, không biến thao tác ghi database bên ngoài thành exactly-once.

Nếu ứng dụng không dùng Kafka transaction hoặc không có yêu cầu đọc committed-only, không cần thêm cấu hình này chỉ vì muốn consumer ổn định.

## 12. Kiểm tra consumer khi chạy

Sau khi ứng dụng khởi động, nên xác minh:

- Consumer kết nối đúng bootstrap servers và tham gia đúng group ID.
- Topic tồn tại, subscription đúng và partition đã được phân công.
- Key/value deserializer tạo đúng kiểu mà listener mong đợi.
- Offset bắt đầu đúng với chính sách đã chọn.
- Listener xử lý thành công và commit theo acknowledgment mode.
- Lag không tăng liên tục ngoài dự kiến.
- Không xảy ra rebalance lặp lại do xử lý lâu hoặc mất heartbeat.

Kafka CLI có thể mô tả consumer group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-service
```

Kết quả giúp kiểm tra partition, consumer ID, offset đã commit, log end offset và lag. Nếu group không xuất hiện, hãy kiểm tra ứng dụng có khởi tạo listener, group ID có đúng và consumer có subscribe topic hay không.

Khi cần kiểm tra topic:

```bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
```

Log ứng dụng nên có topic, partition, offset và event ID khi xử lý lỗi. Tránh ghi toàn bộ payload hoặc thông tin nhạy cảm vào log. Metric hữu ích gồm consumer lag, số lần rebalance, tốc độ xử lý, số lỗi listener và thời gian xử lý mỗi record/batch.

## 13. Các lỗi cấu hình thường gặp

**Sai bootstrap servers:** ứng dụng không kết nối được broker hoặc lấy metadata. Kiểm tra DNS, port, network policy và địa chỉ advertised listener mà broker công bố.

**Không cấu hình group ID:** consumer không có định danh group hợp lệ trong khi listener cần quản lý offset theo group. Đặt `spring.kafka.consumer.group-id` hoặc `groupId` rõ ràng trên listener.

**Group ID khác nhau giữa các instance:** mỗi instance có thể trở thành một group riêng và nhận toàn bộ dữ liệu. Nếu mục tiêu là chia tải, các instance cần dùng chung group ID.

**Deserializer không khớp serializer:** lỗi deserialize hoặc `ClassCastException` xảy ra trước hoặc trong lúc phân giải tham số listener. Kiểm tra cấu hình producer, consumer và schema payload.

**Hiểu nhầm auto-offset-reset:** đổi `earliest` nhưng group vẫn tiếp tục ở offset đã commit. Dùng group mới hoặc quy trình reset offset có kiểm soát nếu cần đọc lại.

**Commit quá sớm:** ứng dụng có thể bỏ qua record nếu sự cố xảy ra sau commit nhưng trước khi hoàn tất nghiệp vụ. Để container quản lý commit sau xử lý và thiết kế handler idempotent.

**Concurrency lớn hơn số partition:** một số consumer không được giao partition và không tạo thêm mức song song hữu ích.

**Batch xử lý quá lâu:** consumer có thể vượt `max.poll.interval.ms`, rời group và kích hoạt rebalance. Điều chỉnh kích thước batch, thời gian xử lý và poll interval dựa trên số đo thực tế.

**Cấu hình security không khớp broker:** lỗi xác thực hoặc TLS thường xuất hiện dù bootstrap server có thể truy cập được. Kiểm tra protocol, mechanism, chứng thư, credential và quyền truy cập topic/group.

## 14. Checklist trước khi đưa consumer lên môi trường dùng thật

- Bootstrap servers được inject theo môi trường và có thể truy cập từ ứng dụng.
- Group ID được đặt có chủ đích và giống nhau giữa các instance cần chia tải.
- Key/value deserializer tương thích với định dạng producer gửi.
- `auto-offset-reset` phản ánh yêu cầu khi group chưa có offset hợp lệ.
- `enable-auto-commit` và `AckMode` được chọn theo cách listener xử lý dữ liệu.
- Listener idempotent để chịu được record được giao lại.
- Concurrency phù hợp với số partition và tài nguyên của ứng dụng.
- Poll settings phù hợp với thời gian xử lý record/batch thực tế.
- Security settings và secret được quản lý qua môi trường triển khai.
- Có metric/log để theo dõi lag, rebalance, lỗi deserialize và lỗi listener.

Một consumer được cấu hình tốt phải biết đọc từ cụm nào, thuộc group nào, chuyển byte thành kiểu dữ liệu nào và commit tiến độ vào thời điểm nào. Khi bốn quyết định này rõ ràng, các tham số concurrency, poll, bảo mật và quan sát có thể được bổ sung theo tải vận hành thực tế.
