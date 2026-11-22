# Luồng dữ liệu từ producer đến consumer

Trong một ứng dụng sử dụng Kafka, producer tạo và gửi sự kiện, Kafka lưu sự kiện vào một partition của topic, còn consumer đọc sự kiện từ partition đó để thực hiện công việc tiếp theo. Spring Kafka cung cấp các thành phần như `KafkaTemplate` và `@KafkaListener` để kết nối ứng dụng Spring với luồng dữ liệu này.

Muốn vận hành messaging đáng tin cậy, cần hiểu toàn bộ đường đi của một record: dữ liệu được tạo ở đâu, được chuyển thành byte như thế nào, Kafka chọn partition ra sao, broker xác nhận việc ghi khi nào, consumer group phân phối partition cho các consumer thế nào và offset được lưu sau khi xử lý ra sao. Các bước này liên kết với nhau nhưng có ý nghĩa khác nhau. Producer gửi thành công không có nghĩa consumer đã xử lý xong; consumer đọc được record cũng không có nghĩa record đã được commit offset.

Sau bài học, người đọc có thể:

- Mô tả được đường đi của một event từ ứng dụng producer đến listener trong ứng dụng consumer.
- Phân biệt topic, partition, record, key, offset và consumer group trong luồng xử lý.
- Giải thích vai trò của serializer, partitioner, broker, deserializer, `KafkaTemplate` và `@KafkaListener`.
- Đọc được metadata của một lần gửi và xác định vị trí record trong Kafka.
- Giải thích vì sao consumer có thể nhận lại một record và vì sao thứ tự chỉ được bảo đảm trong phạm vi một partition.

## 1. Bức tranh tổng thể của luồng dữ liệu

Một luồng Kafka cơ bản có thể được nhìn theo các chặng sau:

1. Ứng dụng producer tạo một event thể hiện điều gì đó đã xảy ra trong nghiệp vụ.
2. Producer gửi event bằng Kafka client. Trong ứng dụng Spring, thao tác này thường được thực hiện qua `KafkaTemplate`.
3. Producer serializer chuyển key và value thành byte. Partitioner chọn partition đích dựa trên partition được chỉ định, key hoặc chiến lược phân vùng mặc định.
4. Kafka broker nhận record và append record vào log của partition. Broker trả kết quả gửi theo cấu hình xác nhận của producer.
5. Consumer thuộc một consumer group được gán partition và dùng `poll()` để lấy các record mới.
6. Consumer deserializer chuyển byte thành đối tượng mà ứng dụng có thể sử dụng. Spring Kafka chuyển record đến phương thức được đánh dấu `@KafkaListener`.
7. Listener xử lý event. Sau khi xử lý theo chính sách xác nhận đã cấu hình, consumer commit offset để ghi nhận vị trí có thể tiếp tục đọc.

```mermaid
flowchart LR
    A[Ứng dụng producer] --> B[KafkaTemplate.send]
    B --> C[ProducerRecord]
    C --> D[Serializer và partitioner]
    D --> E[Broker: append vào topic partition]
    E --> F[Producer nhận kết quả gửi]
    E --> G[Consumer group]
    G --> H[Consumer poll]
    H --> I[Deserializer và message conversion]
    I --> J[@KafkaListener]
    J --> K[Xử lý nghiệp vụ]
    K --> L[Commit offset]
    L -. lưu vị trí theo group .-> G
```

Kết quả gửi của producer và việc xử lý của consumer là hai nhánh khác nhau sau khi record được broker tiếp nhận. Producer có thể nhận xác nhận trong khi consumer chưa chạy, đang xử lý record trước đó hoặc thậm chí chưa được khởi động. Đây là đặc tính quan trọng của mô hình lưu trữ và đọc theo log: producer và consumer không cần hoạt động đồng thời.

## 2. Record, topic, partition, key và offset

Kafka truyền và lưu các record. Một record thường gồm các thành phần sau:

| Thành phần | Ý nghĩa |
| --- | --- |
| Topic | Tên luồng dữ liệu logic mà record được gửi vào, ví dụ `order-events`. |
| Partition | Phân đoạn log vật lý của topic. Mỗi partition có thứ tự record riêng. |
| Key | Giá trị dùng để định tuyến record đến partition và thường dùng để giữ các event cùng thực thể ở cùng một partition. |
| Value | Payload của event, chẳng hạn dữ liệu `OrderCreated`. |
| Timestamp | Mốc thời gian gắn với record; ý nghĩa cụ thể phụ thuộc cấu hình timestamp của producer và broker. |
| Headers | Các cặp key/value bổ sung để mang metadata như correlation ID hoặc loại sự kiện. |
| Offset | Vị trí tăng dần của record trong một partition. Offset không phải số thứ tự toàn topic hay toàn cluster. |

Ví dụ, topic `order-events` có ba partition. Một record có thể nằm tại `order-events-1`, offset `42`. Cách định danh vị trí đầy đủ của record là topic, partition và offset. Chỉ nói offset `42` là chưa đủ vì partition khác cũng có thể có record mang offset `42`.

```text
Topic: order-events

Partition 0:  [offset 0] [offset 1] [offset 2] [offset 3] ...
Partition 1:  [offset 0] [offset 1] ... [offset 42] ...
Partition 2:  [offset 0] [offset 1] [offset 2] ...
```

Một topic có thể có nhiều partition để tăng khả năng xử lý song song và phân tán tải. Mỗi partition là một log có thứ tự append. Kafka không sắp xếp tất cả record của mọi partition thành một thứ tự toàn cục.

Consumer đọc record không làm record biến mất khỏi topic. Record vẫn được lưu theo chính sách retention của topic hoặc cluster, chẳng hạn theo thời gian hay dung lượng. Offset của consumer group chỉ cho biết group đã xác nhận tiến độ đọc đến đâu; nó không phải lệnh xóa record.

## 3. Chặng producer: tạo và gửi event

### 3.1. Từ sự kiện nghiệp vụ đến Kafka record

Producer nên gửi một sự kiện mô tả điều đã xảy ra, thay vì gửi một lệnh yêu cầu consumer thực hiện điều gì đó. Ví dụ, sau khi đơn hàng được tạo thành công, dịch vụ đơn hàng phát ra `OrderCreated`. Dịch vụ thanh toán, kho hoặc thông báo có thể đăng ký đọc event này theo nhu cầu của mình.

Một event đơn giản có thể được biểu diễn bằng Java record:

```java
public record OrderCreated(
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
```

`orderId` là định danh nghiệp vụ của đơn hàng. `total` và `occurredAt` mô tả dữ liệu tại thời điểm sự kiện xảy ra. Trong hệ thống thực tế, event contract cần ổn định và có chiến lược tương thích khi thêm, đổi hoặc loại bỏ field. Producer và consumer có thể được triển khai, phát hành ở các thời điểm khác nhau nên không nên giả định hai bên luôn nâng cấp đồng thời.

Khi gửi, producer tạo một record gồm topic, key, value và có thể có timestamp, headers hoặc partition cụ thể. Với Spring Kafka, `KafkaTemplate` giúp thực hiện thao tác này mà không cần tự quản lý vòng đời của Kafka producer ở từng lời gọi.

```java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send(
            "order-events",
            event.orderId(),
            event
        );
    }
}
```

Trong ví dụ này:

- `String` là kiểu key trước khi serialize.
- `OrderCreated` là kiểu value trước khi serialize.
- `event.orderId()` được dùng làm key để các event của cùng một đơn hàng thường đi cùng partition.
- `send()` thực hiện gửi bất đồng bộ và trả về một `CompletableFuture` trong Spring Kafka 3.x.

Ở các phiên bản Spring Kafka cũ hơn, kiểu future trả về có thể khác. Khi áp dụng vào dự án, cần đối chiếu chữ ký API với phiên bản dependency đang dùng.

### 3.2. Gửi bất đồng bộ và kết quả gửi

Lời gọi `KafkaTemplate.send()` không nên được hiểu là ứng dụng đã chờ consumer xử lý. Producer gửi dữ liệu qua mạng đến broker và hoàn tất future khi có kết quả theo cấu hình xác nhận của producer. Ứng dụng có thể gắn callback để ghi log, cập nhật metric hoặc xử lý lỗi gửi:

```java
public void publishAndObserve(OrderCreated event) {
    kafkaTemplate.send("order-events", event.orderId(), event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Không gửi được OrderCreated: {}", event.orderId(), exception);
                return;
            }

            RecordMetadata metadata = result.getRecordMetadata();
            log.info(
                "Đã gửi orderId={} topic={} partition={} offset={}",
                event.orderId(),
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
}
```

`SendResult` chứa thông tin về record đã gửi và `RecordMetadata` mô tả vị trí record được broker ghi nhận, gồm topic, partition, offset và timestamp. Metadata này rất hữu ích khi điều tra lỗi hoặc đối chiếu một event cụ thể.

Do gửi bất đồng bộ, lỗi có thể xuất hiện sau khi phương thức nghiệp vụ đã trả về. Nếu ứng dụng cần phản hồi cho caller rằng event đã được broker xác nhận, nó phải quyết định rõ có chờ future hay không và xử lý timeout, lỗi gửi, retry như thế nào. Không nên bỏ qua future rồi mặc định mọi lần gửi đều thành công.

### 3.3. Serializer chuyển đối tượng thành byte

Kafka broker lưu byte, không lưu trực tiếp đối tượng Java. Producer serializer chịu trách nhiệm chuyển key và value thành byte trước khi gửi. Ví dụ:

- `StringSerializer` chuyển chuỗi thành byte.
- `IntegerSerializer` chuyển số nguyên thành byte theo định dạng của serializer.
- `JsonSerializer` của Spring Kafka chuyển đối tượng thành JSON byte và có thể bổ sung type information trong header theo cấu hình.
- Serializer Avro, Protobuf hoặc serializer tùy chỉnh có thể được dùng khi hệ thống quản lý schema theo một định dạng khác.

Producer và consumer phải thống nhất định dạng dữ liệu. Nếu producer ghi JSON nhưng consumer lại cố giải mã theo một định dạng không tương thích, lỗi sẽ xuất hiện ở bước deserialization hoặc message conversion, dù record đã nằm trong Kafka.

Ví dụ cấu hình serializer trong Spring Boot:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
```

`bootstrap-servers` cung cấp địa chỉ broker để client khởi tạo kết nối và lấy metadata cluster. Producer có thể kết nối tới một hoặc nhiều địa chỉ bootstrap; sau khi lấy metadata, Kafka client giao tiếp với broker sở hữu partition đích.

### 3.4. Partitioner chọn partition đích

Sau khi có record, producer phải xác định partition đích. Có ba trường hợp thường gặp:

1. Ứng dụng chỉ định partition cụ thể trong `ProducerRecord`; producer sử dụng partition đó nếu hợp lệ.
2. Ứng dụng cung cấp key; partitioner sử dụng key đã serialize để chọn partition theo thuật toán phân vùng.
3. Record không có key và không chỉ định partition; partitioner mặc định phân phối record theo chiến lược của Kafka client, có thể ưu tiên batching và phân phối tải.

Sử dụng key có ý nghĩa khi cần giữ các event liên quan đến cùng một thực thể trên cùng partition. Ví dụ, dùng `orderId` làm key giúp các thay đổi trạng thái của một đơn hàng được đọc theo thứ tự trong cùng partition, với điều kiện cấu hình partitioner và số partition không làm thay đổi ánh xạ key.

Không nên xem key là cơ chế sắp xếp toàn hệ thống. Hai đơn hàng có hai key khác nhau có thể được gửi vào hai partition và consumer có thể xử lý chúng song song. Nếu tăng số partition, ánh xạ key sang partition có thể thay đổi; vì vậy cần xem xét tác động tới thứ tự của một key khi thay đổi topology topic.

## 4. Chặng broker: append record vào partition

Producer gửi record đến broker đang giữ vai trò leader của partition đích. Broker append record vào log của partition và gán offset tiếp theo. Khi partition có replication, các broker follower sao chép dữ liệu từ leader theo cơ chế replication của Kafka.

Kafka dùng mô hình log append-only: record mới được thêm vào cuối log. Việc đọc thường dựa trên offset, vì thế consumer có thể tiếp tục từ vị trí đã lưu mà không cần producer và consumer đồng bộ thời gian hoạt động.

### 4.1. Producer nhận xác nhận ở mức nào?

Mức xác nhận của producer được điều khiển chủ yếu bởi cấu hình `acks`:

| Cấu hình | Ý nghĩa khái quát | Đánh đổi |
| --- | --- | --- |
| `acks=0` | Producer không chờ broker xác nhận record đã được ghi. | Độ trễ thấp hơn nhưng producer khó phát hiện lỗi mất gửi. |
| `acks=1` | Leader xác nhận sau khi append record vào log cục bộ của leader. | Có thể mất record nếu leader gặp sự cố trước khi replica khác sao chép dữ liệu. |
| `acks=all` | Leader chờ các replica đang nằm trong ISR xác nhận theo giao thức replication. | Độ bền tốt hơn nhưng có thể tăng độ trễ và phụ thuộc trạng thái ISR. |

`acks=all` thường được cân nhắc cho dữ liệu quan trọng. Tuy vậy, nó cần đi cùng cấu hình replication phù hợp, đặc biệt là `min.insync.replicas`. Nếu ISR không còn đủ replica theo yêu cầu, broker có thể từ chối ghi thay vì xác nhận một bản ghi có mức bảo vệ thấp hơn dự kiến.

Khi future của `KafkaTemplate.send()` hoàn tất thành công, điều đó phản ánh mức xác nhận đã chọn cho producer. Nó không chứng minh consumer đã đọc hoặc xử lý record. Việc xử lý của consumer diễn ra độc lập và được theo dõi bằng tiến độ offset của consumer group.

### 4.2. Retention và vòng đời record

Record không bị xóa ngay sau khi một consumer đọc xong. Kafka giữ record theo chính sách retention của topic, ví dụ giữ trong một khoảng thời gian hoặc đến khi đạt ngưỡng dung lượng. Vì vậy:

- Nhiều consumer group có thể đọc cùng một topic độc lập.
- Một consumer group có thể đọc lại dữ liệu cũ nếu offset được reset và record vẫn còn trong retention.
- Consumer dừng trong thời gian dài có thể không đọc được những record đã bị xóa theo retention trước khi nó quay lại.

Đây là khác biệt quan trọng giữa Kafka và một hàng đợi mà việc nhận message thường gắn với việc message được loại khỏi hàng đợi. Trong Kafka, tiến độ đọc thuộc về từng group, còn vòng đời record thuộc về chính sách lưu trữ của topic.

## 5. Chặng consumer: đọc dữ liệu bằng consumer group

### 5.1. Consumer group phân phối partition

Consumer thường tham gia một consumer group có tên xác định. Kafka quản lý việc gán partition của topic cho các consumer đang hoạt động trong group đó. Một partition tại một thời điểm chỉ được gán cho tối đa một consumer đang hoạt động trong cùng group, nhưng một consumer có thể được gán nhiều partition.

Giả sử topic có ba partition và group `billing-service` có hai consumer:

```text
Topic order-events
  Partition 0 ───────────────┐
  Partition 1 ───────────────┼──> group billing-service
  Partition 2 ───────────────┘

Một cách phân bổ có thể xảy ra:
  Consumer A: Partition 0, Partition 1
  Consumer B: Partition 2
```

Đây chỉ là một ví dụ phân bổ; kết quả thực tế phụ thuộc assignor và trạng thái group. Nếu group có nhiều consumer hơn số partition được gán, một số consumer sẽ không có partition để đọc. Vì vậy, tăng `concurrency` không tự động tăng throughput nếu số partition không đủ.

Consumer group giúp mở rộng khả năng xử lý song song. Nếu có hai group khác nhau, chẳng hạn `billing-service` và `notification-service`, mỗi group có tiến độ offset riêng và có thể đọc cùng một topic. Đây là cách nhiều dịch vụ nhận cùng một sự kiện mà không phải gửi nhiều bản sao record vào các topic khác nhau chỉ để phục vụ từng dịch vụ.

### 5.2. Poll lấy record

Kafka consumer sử dụng vòng lặp `poll()` để lấy dữ liệu từ các partition được gán. Với Spring Kafka, listener container quản lý vòng lặp này và gọi phương thức listener của ứng dụng. Người viết ứng dụng thường không cần tự tạo vòng lặp `KafkaConsumer.poll()` khi sử dụng `@KafkaListener`.

Luồng xử lý khái quát:

1. Consumer tham gia group và nhận assignment các partition.
2. Consumer fetch record từ broker bắt đầu tại offset mà group sẽ đọc tiếp.
3. Kafka client trả về một batch record cho listener container.
4. Container chuyển từng record hoặc batch đến listener tùy loại listener và cấu hình.
5. Listener xử lý record; container quản lý việc xác nhận và commit theo `AckMode` cùng error handler đã cấu hình.

Consumer có thể lấy nhiều record trong một lần poll. Các cấu hình như `max.poll.records`, `fetch.min.bytes`, `fetch.max.wait.ms` và `max.poll.interval.ms` ảnh hưởng đến kích thước batch, thời gian chờ dữ liệu và nhịp xử lý. Nếu ứng dụng xử lý quá lâu giữa các lần poll, consumer có thể vượt `max.poll.interval.ms`, khiến group xem consumer là không còn tiến triển và thực hiện rebalance.

### 5.3. Deserializer và message conversion

Consumer nhận byte từ broker. Deserializer chuyển byte thành kiểu dữ liệu mà ứng dụng có thể xử lý. Với JSON, Spring Kafka có `JsonDeserializer`; với chuỗi, có `StringDeserializer`.

```yaml
spring:
  kafka:
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.events
        spring.json.value.default.type: com.example.orders.events.OrderCreated
```

Các giá trị trong `spring.json.trusted.packages` và `spring.json.value.default.type` phải khớp package và kiểu event thực tế trong ứng dụng. Không nên mở trusted packages rộng hơn phạm vi cần thiết. Nếu producer và consumer dùng type header để xác định kiểu payload, cần thống nhất cách tạo và đọc các header đó; nếu không dùng type header, consumer phải có cấu hình kiểu mặc định hoặc cơ chế mapping tương ứng.

Serializer/deserializer chỉ giải quyết việc chuyển đổi byte và kiểu dữ liệu. Chúng không tự bảo đảm event có đủ field nghiệp vụ, hợp lệ về trạng thái hay tương thích về ý nghĩa. Những kiểm tra đó thuộc validation và logic của ứng dụng.

## 6. Spring Kafka kết nối consumer với `@KafkaListener`

`@KafkaListener` đánh dấu phương thức nhận message. Spring Kafka tạo listener container để quản lý consumer, poll dữ liệu, gọi phương thức được đánh dấu và phối hợp với cơ chế commit offset, error handler.

Ví dụ listener nhận event `OrderCreated`:

```java
@Component
public class OrderEventListener {

    @KafkaListener(
        topics = "order-events",
        groupId = "billing-service"
    )
    public void onOrderCreated(
            OrderCreated event,
            @Header(KafkaHeaders.RECEIVED_KEY) String key,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info(
            "Nhận OrderCreated orderId={} key={} partition={} offset={}",
            event.orderId(), key, partition, offset
        );

        billingService.startBilling(event);
    }
}
```

Các header được inject giúp quan sát nguồn gốc record. Trong xử lý thực tế, nên ghi nhận tối thiểu topic, partition, offset và một correlation ID phù hợp để có thể nối log producer với log consumer. Không nên log toàn bộ payload nếu payload có dữ liệu nhạy cảm hoặc quá lớn.

Một listener có thể nhận payload đã chuyển đổi, `ConsumerRecord<K,V>` nếu cần truy cập đầy đủ metadata, hoặc nhận batch nếu được cấu hình batch listener. Chọn kiểu nhận dựa trên nhu cầu nghiệp vụ và chính sách xử lý lỗi. Khi listener nhận một batch, quyết định thành công/thất bại có thể ảnh hưởng đến cả batch theo cấu hình container.

### 6.1. Concurrency của listener

Spring Kafka cho phép cấu hình concurrency để listener container chạy nhiều consumer thread. Ví dụ, một listener container có concurrency bằng ba có thể tạo ba consumer thuộc cùng group. Kafka sau đó phân phối các partition được subscribe cho những consumer này.

Concurrency hữu ích khi xử lý có thể chạy song song và topic có đủ partition. Tuy nhiên, concurrency không tạo thêm partition và không làm một partition được nhiều consumer trong cùng group xử lý đồng thời. Nếu topic chỉ có một partition, tăng concurrency của một group lên năm vẫn không tạo ra năm luồng đọc song song cho partition đó.

Khi listener xử lý song song bên trong ứng dụng, cần chú ý thứ tự hoàn thành và commit offset. Nếu các record được xử lý bất đồng bộ nhưng offset lại được commit vượt qua record chưa xử lý xong, khi tiến trình gặp sự cố có thể xảy ra mất xử lý. Thiết kế concurrency phải đi cùng chính sách xác nhận phù hợp.

## 7. Offset và thời điểm xác nhận xử lý

Offset là vị trí của record trong một partition. Consumer group lưu offset đã commit riêng cho từng partition. Offset được commit biểu thị vị trí tiếp theo mà group có thể đọc khi tiếp tục, vì thế nếu record offset `42` đã được xử lý và commit tiến độ qua record đó, vị trí tiếp tục thông thường là `43`.

Offset không phải trạng thái nghiệp vụ. Kafka biết group đã commit đến đâu, nhưng không biết ứng dụng đã gửi email, trừ tiền, cập nhật database hay hoàn tất một workflow hay chưa. Ứng dụng cần thiết kế thứ tự xử lý và commit để phù hợp với tác dụng phụ bên ngoài Kafka.

### 7.1. Auto commit và container-managed commit

Kafka client có cơ chế auto commit offset. Tuy nhiên, khi dùng Spring Kafka listener container, thông thường nên để container quản lý commit và tắt auto commit của Kafka consumer để commit gắn với kết quả xử lý listener. Cấu hình thực tế cần được kiểm tra vì hành vi phụ thuộc phiên bản và cấu hình ứng dụng.

Spring Kafka cung cấp các chế độ xác nhận (`AckMode`) phổ biến:

| Chế độ | Thời điểm commit khái quát |
| --- | --- |
| `RECORD` | Sau khi listener xử lý thành công từng record. |
| `BATCH` | Sau khi xử lý thành công các record trong batch poll. Đây là chế độ mặc định thường gặp của listener container. |
| `TIME` | Khi đạt khoảng thời gian commit được cấu hình. |
| `COUNT` | Khi đạt số record được cấu hình. |
| `MANUAL` | Ứng dụng gọi xác nhận; container thực hiện commit theo quy tắc của chế độ này. |
| `MANUAL_IMMEDIATE` | Yêu cầu commit ngay tại thời điểm ứng dụng xác nhận, trong giới hạn luồng thực thi và cấu hình container. |

Tên chế độ chỉ mô tả thời điểm commit; để hiểu đầy đủ hành vi khi listener lỗi, cần xem error handler, retry, transaction và cách container được cấu hình. Không nên chỉ nhìn `AckMode` rồi kết luận toàn bộ ứng dụng có exactly-once hay at-least-once.

### 7.2. Vì sao consumer có thể nhận lại record?

Giả sử consumer đọc record offset `42`, thực hiện xong tác vụ nghiệp vụ, nhưng tiến trình dừng trước khi commit offset. Khi consumer khởi động lại, group vẫn có thể tiếp tục từ offset cũ và đọc lại record `42`. Đây là tình huống duplicate phổ biến của xử lý at-least-once.

Ngược lại, nếu ứng dụng commit offset trước khi tác vụ nghiệp vụ hoàn tất, tiến trình có thể dừng sau commit nhưng trước khi ghi dữ liệu nghiệp vụ. Khi chạy lại, group đã chuyển qua record đó nên tác vụ có thể bị bỏ sót. Vì vậy, với xử lý thông thường, commit sau khi listener xử lý thành công thường là lựa chọn an toàn hơn.

Do duplicate có thể xảy ra, handler nghiệp vụ nên có tính idempotent khi phù hợp. Ví dụ, khi xử lý `OrderCreated`, hệ thống có thể dùng `eventId` hoặc `orderId` cùng trạng thái nghiệp vụ để phát hiện một event đã được áp dụng. Cần phân biệt idempotency của nghiệp vụ với việc Kafka commit offset: hai cơ chế giải quyết hai vấn đề khác nhau.

### 7.3. `auto-offset-reset` không phải lệnh đọc lại mỗi lần khởi động

`auto-offset-reset` quy định vị trí bắt đầu khi group không có offset hợp lệ được commit cho partition, chẳng hạn group mới hoặc offset cũ không còn nằm trong log. Hai giá trị thường gặp:

- `earliest`: bắt đầu từ record sớm nhất còn được giữ trong partition.
- `latest`: bắt đầu từ record mới nhất tại thời điểm consumer xác định vị trí bắt đầu.

Nếu group đã có offset hợp lệ, consumer tiếp tục từ offset đã commit; `auto-offset-reset` không tự đưa group về đầu topic mỗi lần ứng dụng khởi động. Muốn đọc lại dữ liệu, cần thực hiện reset offset có chủ đích và hiểu tác động tới group đang chạy.

## 8. Thứ tự, song song và delivery semantics

### 8.1. Thứ tự được bảo đảm trong partition

Kafka giữ thứ tự append trong một partition. Một consumer đọc partition theo thứ tự offset. Nếu các event của cùng một đơn hàng được gửi với cùng key và được định tuyến ổn định vào cùng partition, consumer có thể xử lý chuỗi event của đơn hàng theo thứ tự của partition đó.

Kafka không cung cấp thứ tự toàn cục giữa nhiều partition. Ví dụ, `OrderCreated` ở partition 0 có thể được xử lý sau `OrderCancelled` ở partition 2 dù producer gửi event đầu tiên sớm hơn. Nếu nghiệp vụ phụ thuộc thứ tự, cần chọn key và partitioning theo thực thể nghiệp vụ, đồng thời tránh xử lý bất đồng bộ làm đảo thứ tự hoàn thành.

### 8.2. At-most-once, at-least-once và exactly-once

Delivery semantics mô tả quan hệ giữa việc đọc record, xử lý và xác nhận tiến độ:

| Ngữ nghĩa | Hành vi | Rủi ro chính |
| --- | --- | --- |
| At-most-once | Commit trước hoặc không chờ xử lý hoàn tất. | Có thể mất xử lý khi tiến trình dừng sau commit. |
| At-least-once | Xử lý trước, commit sau khi xử lý thành công. | Có thể xử lý lặp nếu dừng trước commit. |
| Exactly-once | Kết hợp cơ chế phù hợp để kết quả quan sát được không bị nhân đôi trong phạm vi được bảo đảm. | Cần cấu hình và ranh giới transaction rõ ràng; không tự xuất hiện chỉ vì dùng Kafka. |

Trong luồng consumer thông thường, at-least-once thường là điểm xuất phát thực tế vì nó ưu tiên không bỏ qua record chưa xử lý thành công. Đổi lại, ứng dụng cần xử lý duplicate. Exactly-once trong Kafka có thể phối hợp đọc, ghi Kafka và commit offset trong transaction Kafka khi được cấu hình đúng; điều đó không tự động làm cho thao tác ghi database hoặc gọi HTTP bên ngoài trở thành một phần của transaction Kafka.

Nếu consumer cập nhật database rồi commit Kafka offset, hai thao tác thuộc hai hệ thống khác nhau và có thể gặp khoảng hở khi tiến trình dừng giữa chúng. Với yêu cầu nhất quán cao, cần xem xét thiết kế như idempotency key, transactional outbox/inbox hoặc cơ chế phối hợp transaction phù hợp với hệ thống. Những cơ chế này là phần thiết kế reliability riêng, không nên suy ra từ việc listener trả về bình thường.

## 9. Khi một chặng trong luồng bị lỗi

Lỗi có thể xuất hiện ở nhiều vị trí và mỗi loại cần cách điều tra khác nhau:

| Chặng | Ví dụ lỗi | Dấu hiệu cần kiểm tra |
| --- | --- | --- |
| Tạo event | Thiếu field, dữ liệu sai hoặc event không phản ánh trạng thái đã commit. | Log nghiệp vụ, validation và thời điểm phát event. |
| Gửi từ producer | Broker không truy cập được, timeout, authorization hoặc topic không tồn tại theo cấu hình cluster. | Exception từ future, bootstrap servers, ACL, metadata và cấu hình topic. |
| Serialize | Kiểu dữ liệu không hỗ trợ hoặc serializer không tương thích. | Stack trace serializer, kiểu key/value và cấu hình serializer. |
| Broker append | ISR không đủ, quota hoặc lỗi broker. | Producer exception, broker log, replication state và `acks`. |
| Consumer poll | Consumer không được gán partition, group liên tục rebalance hoặc không có record mới. | Group state, assignment, lag, heartbeat và poll interval. |
| Deserialize | Byte không đúng định dạng hoặc không thể tạo kiểu đích. | Deserializer exception, schema, type header và trusted packages. |
| Listener | Lỗi nghiệp vụ, timeout, dependency bên ngoài không sẵn sàng. | Log listener, error handler, retry policy và thời gian xử lý. |
| Commit offset | Commit thất bại hoặc tiến độ commit không khớp kết quả xử lý. | Commit exception, ack mode, auto commit và trạng thái group. |

### 9.1. Retry và dead-letter là nhánh xử lý lỗi

Khi listener ném exception, Spring Kafka có thể chuyển lỗi qua error handler. Tùy cấu hình, record có thể được thử lại, được seek để đọc lại, bị bỏ qua theo chính sách hoặc được chuyển đến dead-letter topic (DLT). Retry và DLT không phải một bước bắt buộc trong luồng thành công; chúng là chính sách xử lý khi một chặng thất bại.

Retry chỉ phù hợp khi lỗi có khả năng tự hết, chẳng hạn một dependency tạm thời không truy cập được. Lỗi dữ liệu không hợp lệ thường không tự hết khi gửi lại liên tục. Với retry có delay, cần cân nhắc thứ tự: một record lỗi có thể chặn các record sau trong cùng partition tùy cách xử lý. DLT giúp cô lập record cần điều tra, nhưng cần theo dõi và có quy trình sửa, phát lại dữ liệu.

Không nên xem việc gửi record vào DLT là đã giải quyết lỗi nghiệp vụ. Hệ thống vẫn cần biết record nào đã bị chuyển, lý do, số lần thử, nơi lưu payload và ai chịu trách nhiệm xử lý tiếp.

### 9.2. Rebalance và tác động tới xử lý

Rebalance xảy ra khi thành viên group thay đổi hoặc metadata/assignment cần được tính lại, ví dụ consumer khởi động, dừng, mất kết nối hoặc vượt giới hạn poll. Khi rebalance, partition có thể được thu hồi từ consumer này và gán cho consumer khác.

Nếu listener đang xử lý record trong lúc partition bị thu hồi, ứng dụng phải phối hợp shutdown, xử lý đang chạy và commit offset theo cấu hình container. Một lần rebalance có thể làm tăng độ trễ và tạo điều kiện cho duplicate nếu record đã được xử lý nhưng offset chưa commit. Theo dõi số lần rebalance và thời gian xử lý listener giúp phát hiện vấn đề sớm.

## 10. Ví dụ cấu hình và ghép các chặng

Ví dụ sau minh họa một producer phát `OrderCreated` và một consumer thuộc group `billing-service` nhận event. Các tên topic, group và package chỉ là giá trị mẫu; cần thay bằng cấu hình của ứng dụng thực tế.

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.events
        spring.json.value.default.type: com.example.orders.events.OrderCreated
```

Event contract:

```java
package com.example.orders.events;

public record OrderCreated(
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}
```

Producer:

```java
@Service
@RequiredArgsConstructor
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("order-events", event.orderId(), event);
    }
}
```

Consumer:

```java
@Component
@RequiredArgsConstructor
public class BillingOrderListener {

    private final BillingService billingService;

    @KafkaListener(topics = "order-events", groupId = "billing-service")
    public void onOrderCreated(
            OrderCreated event,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
            @Header(KafkaHeaders.OFFSET) long offset) {

        log.info(
            "Processing orderId={} partition={} offset={}",
            event.orderId(), partition, offset
        );
        billingService.startBilling(event);
    }
}
```

Khi chạy ví dụ, hãy lần theo một `orderId` cụ thể:

1. Xác nhận nghiệp vụ đã tạo `OrderCreated` với dữ liệu hợp lệ.
2. Quan sát future của `KafkaTemplate.send()` và exception nếu gửi thất bại.
3. Nếu gửi thành công, ghi nhận topic, partition và offset từ `RecordMetadata`.
4. Xác nhận group `billing-service` có assignment partition của topic `order-events`.
5. Kiểm tra listener nhận đúng `orderId`, partition và offset tương ứng.
6. Quan sát tiến độ committed offset của group sau khi listener xử lý thành công.

Nếu producer báo gửi thành công nhưng listener không nhận được record, hãy kiểm tra topic và cluster mà hai ứng dụng đang kết nối, tên group, assignment, offset đã commit, bộ lọc hoặc điều kiện xử lý trong ứng dụng và lỗi deserialization. Nếu listener nhận record nhưng xử lý lặp, hãy kiểm tra thời điểm commit, retry, rebalance và tính idempotent của tác vụ nghiệp vụ.

## 11. Đọc trạng thái luồng dữ liệu khi vận hành

Khi điều tra một luồng Kafka, nên quan sát từng chặng thay vì chỉ kiểm tra ứng dụng consumer có đang chạy hay không.

- **Producer:** số record gửi, số lần gửi lỗi, latency của send, timeout và tỷ lệ retry.
- **Broker/topic:** số partition, replication factor, ISR, dung lượng log và retention.
- **Consumer group:** trạng thái group, thành viên, partition assignment, committed offset và consumer lag.
- **Listener:** số record xử lý thành công/thất bại, thời gian xử lý, retry, DLT và exception theo loại.
- **Offset:** so sánh offset mới nhất của partition với committed offset của group để hiểu khoảng dữ liệu còn chờ xử lý.

Consumer lag thường được biểu diễn bằng chênh lệch giữa vị trí mới nhất của partition và tiến độ đọc đã commit của group. Lag tăng liên tục có thể cho thấy producer tạo dữ liệu nhanh hơn tốc độ consumer xử lý, consumer không được gán partition, listener xử lý quá chậm hoặc có lỗi khiến record liên tục được thử lại. Lag bằng không tại một thời điểm cũng không chứng minh hệ thống không có lỗi; cần kết hợp với metric lỗi và độ trễ đầu-cuối.

Correlation ID hoặc event ID xuyên suốt producer, header Kafka và log listener giúp truy vết một event qua nhiều dịch vụ. Khi log metadata, nên dùng bộ ba topic/partition/offset cùng định danh nghiệp vụ để tránh nhầm các record có cùng offset ở partition khác nhau.

## 12. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| `send()` trả về thành công nghĩa là consumer đã xử lý. | Nó chỉ phản ánh kết quả gửi theo mức `acks`; consumer xử lý độc lập. |
| Offset là số thứ tự của toàn topic. | Offset chỉ có ý nghĩa trong một partition. |
| Một consumer group có thể cho nhiều consumer cùng đọc một partition. | Trong cùng group, một partition tại một thời điểm chỉ được gán cho tối đa một consumer đang hoạt động. |
| Tăng concurrency luôn làm throughput tăng. | Mức song song còn bị giới hạn bởi số partition và năng lực xử lý. |
| Dùng cùng key bảo đảm thứ tự trên mọi partition. | Key chỉ hỗ trợ định tuyến các record liên quan vào cùng partition; thứ tự chỉ có trong partition đó. |
| Consumer đọc xong thì record bị xóa. | Record được giữ theo retention; offset được quản lý riêng theo group. |
| `auto-offset-reset: earliest` khiến consumer luôn đọc lại từ đầu. | Nó chỉ áp dụng khi group không có offset hợp lệ. |
| Listener không ném exception nghĩa là dữ liệu đã được commit. | Commit phụ thuộc ack mode, container, transaction và cấu hình thực tế. |
| Kafka mặc định cung cấp exactly-once cho mọi tác vụ. | Exactly-once có phạm vi và điều kiện cấu hình cụ thể; tác dụng phụ bên ngoài Kafka cần thiết kế riêng. |

## 13. Checklist lần theo một event từ đầu đến cuối

Khi một event không đến được nơi mong muốn, có thể dùng thứ tự kiểm tra sau:

1. Producer có tạo đúng event và đúng topic không?
2. Key/value serializer có tương thích với dữ liệu thực tế không?
3. Producer đã nhận xác nhận gửi chưa; nếu chưa, future báo exception gì?
4. Record được ghi vào partition và offset nào?
5. Consumer có subscribe đúng topic và tham gia đúng group không?
6. Partition có được gán cho consumer đang hoạt động không?
7. Group đang đọc từ committed offset nào; record còn nằm trong retention không?
8. Deserializer có tạo được kiểu event mà listener yêu cầu không?
9. Listener có được gọi và xử lý thành công không; error handler có retry hoặc chuyển DLT không?
10. Offset được commit theo chế độ nào và có phản ánh đúng kết quả xử lý không?

Khi trả lời được các câu hỏi này, có thể xác định event đang dừng ở producer, broker, consumer assignment, deserialization, listener hay commit. Đó là nền tảng để học sâu hơn về serialization, retry, dead-letter, transaction, exactly-once, concurrency và kiểm thử trong Spring Kafka.
