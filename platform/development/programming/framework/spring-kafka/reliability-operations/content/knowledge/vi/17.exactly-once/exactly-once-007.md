# read_committed consumer

Trong Kafka, producer có thể ghi nhiều record trong một **transaction** rồi quyết định `commitTransaction()` hoặc `abortTransaction()`. Consumer ở chế độ mặc định vẫn có thể nhìn thấy record thuộc một transaction cuối cùng bị abort. Đối với luồng cần đảm bảo consumer chỉ xử lý kết quả đã được producer xác nhận, Kafka cung cấp cấu hình **`isolation.level=read_committed`**.

Trong Spring Kafka, `read_committed` được đặt trên **Kafka consumer**, thường thông qua `spring.kafka.consumer.properties[isolation.level]` hoặc cấu hình `ConsumerFactory`. Nó yêu cầu consumer chỉ trả về record từ các transaction đã commit, cùng với các record được ghi ngoài transaction. Các record nằm trong transaction đang mở hoặc đã abort sẽ không được giao cho listener như dữ liệu nghiệp vụ hợp lệ.

`read_committed` là một mảnh ghép quan trọng của xử lý **exactly-once trong phạm vi Kafka**, nhưng **không tự biến toàn bộ ứng dụng thành exactly-once**. Để đạt khả năng nguyên tử giữa consume, xử lý và produce sang Kafka, ứng dụng còn phải sử dụng Kafka transaction và ghi offset đã xử lý vào cùng transaction. Nếu listener cập nhật database, gọi HTTP API hoặc gửi email, những side effect bên ngoài Kafka vẫn cần idempotency, outbox hoặc một cơ chế đối soát riêng.

## 1. `read_uncommitted` và `read_committed` khác nhau thế nào?

Thuộc tính `isolation.level` của Kafka consumer có hai giá trị chính:

| Chế độ | Record từ transaction đã commit | Record từ transaction đã abort | Record từ transaction đang mở | Record producer không dùng transaction |
|---|---|---|---|---|
| `read_uncommitted` (mặc định của Kafka consumer) | Có thể đọc | Có thể đọc | Có thể đọc khi đã có trong log và được fetch | Đọc được |
| `read_committed` | Đọc được khi transaction đã commit | Không giao cho ứng dụng | Chưa giao cho ứng dụng | Đọc được, theo giới hạn Last Stable Offset |

Lưu ý: `read_uncommitted` không có nghĩa consumer nhìn thấy dữ liệu chưa được broker ghi nhận. Nó vẫn tuân thủ giới hạn dữ liệu Kafka có thể trả về từ log, nhưng **không lọc các record theo kết quả transaction** như `read_committed`.

`read_committed` không bắt buộc mọi producer ghi vào topic đều phải dùng transaction. Record từ producer không transactional vẫn có thể đọc được. Cơ chế lọc chỉ có ý nghĩa khi topic có các transactional records và commit/abort markers tương ứng.

## 2. Ví dụ trực quan về visibility của transaction

Giả sử producer xử lý đơn hàng và cần ghi hai event cùng nhau:

```text
Producer transaction T-42
       |
       +--> orders-events: OrderAccepted
       |
       +--> orders-events: InventoryReserved
       |
       +--> commitTransaction()
```

Nếu transaction commit thành công, consumer `read_committed` có thể nhận hai event. Nếu producer abort do bước thứ hai thất bại, consumer `read_committed` không thấy hai record như các event đã xác nhận.

```text
Partition log:
  offset 100: non-transactional record
  offset 101: T-42 / OrderAccepted
  offset 102: T-42 / InventoryReserved
  offset 103: transaction COMMIT marker
  offset 104: non-transactional record

read_committed:
  nhận record 100, 101, 102, 104
  không chuyển control marker 103 cho listener nghiệp vụ
```

Với một transaction bị abort:

```text
Partition log:
  offset 200: non-transactional record
  offset 201: T-43 / OrderAccepted
  offset 202: T-43 / InventoryReserved
  offset 203: transaction ABORT marker
  offset 204: non-transactional record

read_committed:
  nhận record 200 và 204
  bỏ qua các record của T-43 đã abort và control marker

read_uncommitted:
  có thể nhận cả record 201 và 202 dù transaction đã abort
```

Các offset trên là ví dụ khái niệm. Control batches là một phần của Kafka log, không được giao như message nghiệp vụ thông thường. Vì vậy, **offset mà listener quan sát được không nhất thiết liên tiếp**: có khoảng trống do record của transaction bị abort hoặc control records. Không được coi một khoảng nhảy offset là bằng chứng chắc chắn rằng Kafka đã mất record.

## 3. Last Stable Offset (LSO): vì sao consumer có thể bị chậm?

Kafka cần tránh giao record của transaction chưa biết cuối cùng sẽ commit hay abort. Với `read_committed`, giới hạn đọc quan trọng là **Last Stable Offset (LSO)**. Có thể hình dung LSO là vị trí an toàn để Kafka trả về các record đã ổn định về trạng thái transaction: nó bị giới hạn bởi high watermark và vị trí bắt đầu của transaction đang mở sớm nhất trên partition.

Ví dụ:

| Offset | Trạng thái |
|---:|---|
| 50 | Record ngoài transaction, đã ghi ổn định |
| 51 | Transaction A bắt đầu, chưa commit/abort |
| 52 | Record khác thuộc transaction A |
| 53 | Record ngoài transaction, được ghi sau khi A bắt đầu |
| 54 | Record ngoài transaction, được ghi sau khi A bắt đầu |

Chừng nào transaction A còn mở, consumer `read_committed` có thể chỉ đọc được record trước vị trí bắt đầu transaction A, dù broker đã nhận record ở offset 53 và 54. Đây là **giới hạn ổn định của partition**, không phải việc những record ngoài transaction bị đánh dấu abort.

```text
Log offsets:     50  51  52  53  54 ...
                     ^
             transaction A mở

read_committed:
             đọc được đến trước offset 51

Khi A COMMIT hoặc ABORT:
             LSO có thể tiến lên;
             các record đủ điều kiện lại được trả về
```

Một transaction mở lâu có thể khiến consumer `read_committed` có vẻ “đứng yên” trong khi producer/broker metrics vẫn cho thấy log tiếp tục tăng. Nếu ứng dụng bật mode này mà chỉ nhìn log-end offset, có thể diễn giải nhầm vấn đề thành lỗi consumer thread hoặc network.

### Phân biệt ba vị trí thường gặp

| Khái niệm | Ý nghĩa |
|---|---|
| Log End Offset (LEO) | Vị trí cuối log trên một replica; có thể bao gồm dữ liệu chưa ổn định về transaction |
| High Watermark (HW) | Ranh giới dữ liệu đã được replicate đủ để broker trả về theo cơ chế đọc Kafka |
| Last Stable Offset (LSO) | Ranh giới cho consumer `read_committed`; không vượt qua transaction đang mở sớm nhất |

Các API và công cụ đo `endOffsets()` hoặc lag có thể phản ánh giới hạn khác nhau theo isolation level và công cụ. Với Kafka consumer `read_committed`, `endOffsets()` phản ánh LSO; nhiều công cụ giám sát broker/group lại tính lag dựa trên log-end/high-watermark khác. Khi so sánh số liệu, phải xác nhận **điểm cuối nào** được dùng làm mẫu số.

## 4. Bật `read_committed` trong Spring Boot

Với một ứng dụng Spring Boot dùng Spring Kafka, cách đơn giản nhất là cấu hình thuộc tính Kafka consumer:

```properties
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.consumer.group-id=order-materializer
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.properties[isolation.level]=read_committed
```

`enable-auto-commit=false` không phải điều kiện kỹ thuật để **đọc** với `read_committed`, nhưng thường là lựa chọn chủ động trong các hệ thống cần kiểm soát chính xác thời điểm commit offset. Với luồng transactional consume-transform-produce, hãy để container và Kafka transaction quản lý offset thay vì bật Kafka consumer auto-commit riêng.

Nếu value là JSON, còn phải cấu hình deserializer và type mapping phù hợp:

```properties
spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=org.springframework.kafka.support.serializer.JsonDeserializer
spring.kafka.consumer.properties[spring.json.trusted.packages]=com.example.events
```

Cấu hình JSON ở đây chỉ minh họa; ứng dụng thực tế cần type headers hoặc default type và schema contract nhất quán với producer. Không mở `trusted.packages=*` bừa bãi. `read_committed` không sửa lỗi deserialize hoặc tự bảo đảm schema compatibility.

### Cấu hình bằng YAML

Có thể đặt các thuộc tính tương ứng trong `application.yml`:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-materializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[isolation.level]": read_committed
```

Trong Spring Boot, các key Kafka client được truyền qua map `consumer.properties`; dạng `[isolation.level]` giữ nguyên key dấu chấm khi binding. Điều quan trọng là giá trị cuối cùng thực sự tới `ConsumerConfig.ISOLATION_LEVEL_CONFIG`, không chỉ xuất hiện trong file YAML. Khi có cấu hình nhiều profile hoặc factory riêng, cần xác minh consumer tạo ra đang dùng isolation level mong muốn.

## 5. Cấu hình theo `ConsumerFactory` để cô lập listener

Một ứng dụng có thể có cả consumer phục vụ xử lý đã commit và consumer phục vụ kiểm thử/điều tra. Nếu chỉ một nhóm listener cần `read_committed`, tạo `ConsumerFactory` và `ConcurrentKafkaListenerContainerFactory` riêng sẽ tránh vô tình đổi semantics của mọi consumer.

```java
@Bean("readCommittedConsumerFactory")
ConsumerFactory<String, OrderEvent> readCommittedConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> properties =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    properties.put(
            ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
    properties.put(
            ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

    return new DefaultKafkaConsumerFactory<>(properties);
}

@Bean("readCommittedKafkaListenerContainerFactory")
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
readCommittedKafkaListenerContainerFactory(
        @Qualifier("readCommittedConsumerFactory")
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setAckMode(
            ContainerProperties.AckMode.RECORD);

    return factory;
}
```

Ví dụ listener:

```java
@KafkaListener(
        id = "orderMaterializer",
        topics = "orders-events",
        groupId = "order-materializer",
        containerFactory = "readCommittedKafkaListenerContainerFactory")
public void materialize(OrderEvent event) {
    orderProjectionService.applyIdempotently(event);
}
```

Các class `OrderEvent` và `OrderProjectionService` là kiểu minh họa của ứng dụng. `DefaultKafkaConsumerFactory` cần deserializer thực sự tạo được `OrderEvent`; có thể dùng cấu hình JSON/schema chung từ `KafkaProperties`. API `buildConsumerProperties()` của Spring Boot có thể có overload khác theo phiên bản; dùng phương thức được dependency thực tế hỗ trợ và giữ đầy đủ TLS/SASL, bootstrap và client settings.

Trong ví dụ, `AckMode.RECORD` là một lựa chọn cho listener xử lý vào database theo hướng at-least-once + idempotency. **Nó không biến database update và Kafka offset commit thành một giao dịch nguyên tử.** Để làm điều đó cần thêm thiết kế giao dịch/đối soát phù hợp; `read_committed` chỉ ảnh hưởng việc record từ producer Kafka có được nhìn thấy hay không.

Nếu nhiều factory cùng tồn tại, đừng chỉ đặt property global rồi giả định mọi listener đều nhận được. Hãy xác nhận bean `ConsumerFactory` gắn với đúng factory và annotation `containerFactory` trỏ đúng tên bean.

## 6. `read_committed` không đồng nghĩa bật Kafka transaction cho producer

Consumer có thể bật `read_committed` trong khi producer vẫn gửi các record không transactional. Trong trường hợp đó, consumer vẫn đọc được record nhưng **không có tính nguyên tử của một nhóm thao tác** vì producer chưa tạo transaction.

Để producer phát dữ liệu giao dịch, cần một `ProducerFactory` hỗ trợ transaction, có transaction ID prefix duy nhất theo phạm vi instance và quản lý begin/commit/abort transaction.

Ví dụ minh họa với Spring Boot:

```properties
# Các instance producer đang chạy đồng thời phải có transactional.id riêng.
spring.kafka.producer.transaction-id-prefix=order-writer-instance-01-
```

`transaction-id-prefix` phải tránh xung đột giữa các application instance chạy đồng thời. Nếu hai producer hoạt động với cùng `transactional.id`, broker có thể fence producer cũ và phát sinh lỗi giao dịch. Có thể tái sử dụng ID có chủ đích trong cơ chế phục hồi producer instance, nhưng không được để hai instance thực thi đồng thời tự ý dùng cùng ID.

Khi `KafkaTemplate` được nối với transactional producer factory, Spring Kafka có thể chạy nhiều lần gửi trong một Kafka transaction. Ví dụ:

```java
public void publishOrderEvents(OrderEvent accepted, OrderEvent reserved) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders-events", accepted.orderId(), accepted);
        operations.send("orders-events", reserved.orderId(), reserved);
        return null;
    });
}
```

Nếu giao dịch commit, consumer `read_committed` có thể đọc các record được ghi. Nếu transaction abort, các record đó không được giao cho consumer `read_committed`. Đoạn code chỉ minh họa **nguyên tử giữa các lần publish Kafka**; nó chưa bao gồm việc đọc Kafka và ghi offset tiêu thụ vào cùng transaction.

Producer cũng cần cấu hình độ bền phù hợp như `acks=all`, idempotence, replication factor và `min.insync.replicas` cho topic. Chỉ bật `read_committed` ở consumer không bù được cấu hình broker/producer thiếu an toàn.

## 7. Exactly-once trong pipeline Kafka → Kafka

Một kịch bản điển hình là consumer đọc `orders-input`, biến đổi dữ liệu rồi producer ghi `orders-output`. Mục tiêu là **record đầu ra và offset của record đầu vào được commit cùng nhau** trong một Kafka transaction.

```text
orders-input
     |
     v
Spring Kafka listener
     |
     +--> tính toán / chuyển đổi
     |
     +--> KafkaTemplate gửi orders-output
     |
     +--> offset đã consume được đưa vào transaction
     |
     v
Kafka transaction COMMIT
     |
     +--> output record được đọc bởi read_committed consumer
     |
     +--> consumer group ghi nhận offset đã xử lý
```

Nếu listener lỗi hoặc transaction abort, output gửi trong transaction không hiển thị cho `read_committed` consumer; offset nguồn cũng không được commit như đã xử lý xong. Khi listener chạy lại sau rollback, ứng dụng có thể đọc lại record nguồn mà không tạo thêm **output đã commit** ngoài ý muốn nếu dùng đúng giao dịch Kafka.

Trong Spring Kafka, thiết kế này thường cần:

1. Transaction-capable `ProducerFactory` có `transactionIdPrefix`.
2. `KafkaTransactionManager` hoặc transaction manager tương đương được gắn đúng listener container.
3. `KafkaTemplate` tham gia transaction mà container tạo ra khi listener được gọi.
4. Consumer `enable.auto.commit=false` để offset không tự commit ngoài transaction.
5. Container đưa offset đã xử lý vào Kafka transaction (cơ chế `sendOffsetsToTransaction` được Spring Kafka quản lý).
6. **Consumer hạ nguồn** đọc `orders-output` với `isolation.level=read_committed` nếu cần chỉ thấy output đã commit.

Không cần gọi thủ công `sendOffsetsToTransaction` trong listener khi container đã quản lý chính xác transaction và offset. Tự commit offset bên ngoài transaction trong khi container đang quản lý transactional offset có thể phá vỡ tính nguyên tử mong muốn. Cách gắn transaction manager vào `ContainerProperties` thay đổi theo phiên bản Spring Kafka; hãy dùng API thực tế của phiên bản và kiểm thử transaction abort trước khi dựa vào bảo đảm này.

### Vì sao cần cả producer transaction và `read_committed`?

Một producer transaction có thể abort output, nhưng consumer downstream ở `read_uncommitted` vẫn có thể đọc record output đã được ghi rồi sau đó abort. Vì vậy, phía downstream muốn nhìn thấy kết quả đã xác nhận phải dùng `read_committed`. Ngược lại, downstream `read_committed` mà upstream không dùng transaction sẽ không thể tự tạo ranh giới nguyên tử cho nhiều record.

## 8. Giới hạn: database, REST API và side effect ngoài Kafka

Giả sử listener đọc một `PaymentCaptured` record rồi:

1. Ghi trạng thái thanh toán vào PostgreSQL.
2. Publish một event `InvoiceRequested` lên Kafka.
3. Commit offset nguồn.

Ngay cả khi bước 2 và 3 thuộc một Kafka transaction, bước 1 **không tự động** nằm trong cùng transaction đó. Nếu database đã commit nhưng Kafka transaction abort, listener có thể đọc lại record và ghi database thêm lần nữa.

Để tránh duplicate side effect, có thể dùng **transactional inbox/idempotent consumer**: ghi event ID vào một bảng có unique constraint trong cùng database transaction với cập nhật nghiệp vụ. Khi record được redeliver, insert inbox trùng ID cho biết thao tác đã được thực hiện và có thể kết thúc an toàn.

```text
BEGIN DB TRANSACTION
       |
       v
INSERT INTO processed_event(event_id)
       |
       +---- ID đã tồn tại ----> bỏ qua side effect trùng
       |
       v
Cập nhật trạng thái nghiệp vụ
       |
       v
COMMIT DB TRANSACTION
```

Nếu phải atomically lưu state và ý định phát Kafka event từ database, outbox pattern giúp ghi cả domain state và outbox row trong một DB transaction rồi publish bất đồng bộ. Consumer downstream vẫn phải xử lý duplicate vì publisher/outbox relay thường có semantics at-least-once.

Với email, thanh toán qua API hoặc request HTTP khác, cần idempotency key của hệ thống đích, trạng thái điều phối hoặc quy trình bù trừ. `isolation.level=read_committed` không kiểm soát những hệ thống này.

## 9. Committed offset của consumer khác transaction commit của producer

Kafka dùng từ “commit” trong hai ngữ cảnh:

| Thuật ngữ | Cái được xác nhận | Ai kiểm soát? |
|---|---|---|
| Producer transaction commit | Một nhóm record và/hoặc offset được ghi nguyên tử trong phạm vi Kafka transaction | Transactional producer / transaction manager |
| Consumer committed offset | Vị trí tiếp theo consumer group sẽ đọc sau restart hoặc rebalance | Kafka consumer/container hoặc transactional offset commit |

`read_committed` chỉ xác định **record nào được consumer nhìn thấy**. Nó không tự quyết định khi nào committed offset của consumer group tiến lên. Nếu container dùng `AckMode.RECORD`, `AckMode.BATCH`, manual acknowledgment hay Kafka transaction, tiến độ commit offset vẫn phụ thuộc từng cơ chế đó.

Ví dụ record ở offset 104 được producer commit và consumer `read_committed` nhận được. Nếu listener crash trước khi committed offset của group tiến tới 105, Kafka có thể giao lại offset 104 sau restart. Record **đã commit ở phía producer** không đồng nghĩa **đã xử lý xong ở phía consumer**.

Trong pipeline EOS Kafka→Kafka, producer transaction thường bao gồm cả output và offset nguồn. Trong pipeline Kafka→database, cần bảo vệ database side effect bằng idempotency dù topic nguồn được đọc ở `read_committed`.

## 10. Tác động tới retry, DLT và recovery

Spring Kafka có thể dùng `DefaultErrorHandler`, `DeadLetterPublishingRecoverer` hoặc `@RetryableTopic` để retry/recover record lỗi. `read_committed` hoạt động trước tầng listener ở mức Kafka consumer fetch. Nó không phân loại exception, không cấu hình backoff và không tự gửi record sang DLT.

Nếu một record **đã commit ở topic nguồn** nhưng listener không deserialize được, `read_committed` vẫn có thể nhận record đó và error handler cần xử lý lỗi định dạng. Nếu record thuộc **transaction đã abort**, record không được giao cho listener nên error handler nghiệp vụ cũng không có record đó để đưa vào DLT. Đây là hành vi mong muốn của isolation, không phải mất dữ liệu.

Với luồng recovery transactional, việc publish DLT và commit offset nguồn có thể được đặt trong một Kafka transaction phù hợp, thường qua `DefaultAfterRollbackProcessor` và transactional template. Downstream muốn chỉ nhìn thấy DLT record đã commit nên dùng `read_committed` nếu DLT publisher là transactional.

Không giả định mọi DLT publisher đều dùng transaction. Với DLT được publish ngoài transaction, `read_committed` vẫn nhận record đó như record non-transactional. Nếu publish DLT thành công nhưng commit offset nguồn thất bại trong mô hình không transactional, có thể xuất hiện duplicate DLT sau restart; dùng original topic-partition-offset hoặc stable event ID để deduplicate khi replay.

## 11. `read_committed` và thứ tự record trong partition

Kafka giữ thứ tự log theo partition. Tuy nhiên, khi consumer đọc ở `read_committed`, những record của transaction abort và control markers không được chuyển cho listener, nên dãy offset mà listener thấy có thể không liên tiếp:

```text
Partition log:
  300 -> committed transaction A
  301 -> aborted transaction B
  302 -> aborted transaction B
  303 -> committed transaction C

Listener read_committed:
  xử lý offset 300, sau đó 303
```

Điều đó không có nghĩa Kafka sắp xếp lại các record được giao. Thứ tự tương đối giữa các record **được phép nhìn thấy** trên cùng partition vẫn theo vị trí log. Nhưng những record bị bỏ qua không nên được mô hình hóa như event nghiệp vụ đã xảy ra.

Nếu có nhiều partition, `read_committed` không tạo thứ tự tổng thể giữa các partition. Nếu một business invariant yêu cầu event cùng key được xử lý theo thứ tự, producer phải partition nhất quán và consumer/state machine phải kiểm soát trạng thái. Nếu producer thay đổi partitioner hoặc partition count, chỉ bật `read_committed` không giải quyết vấn đề ordering.

## 12. Khi nào `read_committed` làm tăng độ trễ?

Khác với consumer `read_uncommitted` có thể nhìn thấy record transaction vừa được ghi, consumer `read_committed` phải chờ transaction đạt trạng thái cuối cùng. Độ trễ thường đến từ:

- Producer mở transaction quá lâu trước khi commit.
- Transaction bị treo do application lỗi hoặc network gián đoạn.
- Broker phải chờ timeout hoặc transaction coordinator xử lý abort.
- Một transaction mở sớm trên partition giữ LSO ở vị trí thấp, khiến các record phía sau chưa được trả về.
- Số lượng transaction/throughput cao làm tăng chi phí vận hành transaction coordinator.

Nếu `transaction.timeout.ms` quá dài, một transaction bị bỏ dở có thể giữ LSO của partition trong thời gian dài. Nếu timeout quá ngắn so với công việc thực tế, producer có thể bị abort và cần chạy lại. Cần chọn timeout theo thời gian transaction thực tế, giới hạn do broker cho phép và SLO của consumer downstream.

Không nên kéo dài Kafka transaction để chờ một thao tác HTTP hoặc database chậm nếu có thể tránh. Transaction cần đủ ngắn để giảm lock về visibility, thời gian hồi phục sau crash và áp lực lên broker.

## 13. Quan sát và chẩn đoán consumer `read_committed`

Dashboard consumer nên phân biệt **không có record mới**, **bị giới hạn bởi LSO** và **listener xử lý chậm**. Những hiện tượng này có cùng biểu hiện là throughput thấp nhưng nguyên nhân và cách xử lý khác nhau.

| Tín hiệu | Ý nghĩa cần tìm hiểu |
|---|---|
| Consumer group committed offset | Điểm tiến độ đã ghi của group sau xử lý |
| Last Stable Offset (LSO) | Giới hạn record ổn định có thể được đọc khi bật isolation |
| High watermark / log end | Broker đã có dữ liệu đến đâu, kể cả dữ liệu chưa ổn định về transaction |
| Consumer lag | Có thể khác nhau giữa dashboard, CLI và consumer `endOffsets()` vì điểm cuối được dùng khác nhau |
| Transaction abort rate | Producer có đang tạo nhiều record bị abort không? |
| Transaction duration / timeout | Có transaction mở lâu làm kẹt LSO không? |
| Rebalance và poll latency | Consumer có mất assignment hoặc bị chậm do xử lý không? |
| Listener error / DLT rate | Các record đã được giao có gây lỗi ở tầng ứng dụng không? |

Ví dụ có log-end offset 20.000, LSO 19.500 và committed offset của consumer group 19.500. Một công cụ dùng log-end có thể báo lag 500, trong khi consumer `read_committed` chưa có record ổn định nào để đọc sau 19.500. Chẩn đoán nên tập trung vào transaction đang mở tại ranh giới LSO thay vì chỉ tăng số consumer thread.

Log startup cần thể hiện consumer group, listener ID, topic, isolation level và factory được sử dụng. Nếu chỉ một nhóm listener phải đọc dữ liệu đã commit, hãy quan sát riêng group đó. Không dùng event ID, key hay offset riêng lẻ làm metric label cardinality cao; đặt chúng trong structured log hoặc trace khi cần điều tra.

## 14. Lỗi cấu hình và tình huống thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Consumer downstream xử lý record từ transaction đã abort | Consumer vẫn dùng mặc định `read_uncommitted` | Cấu hình `isolation.level=read_committed` trên đúng consumer/factory |
| Đã bật `read_committed` nhưng dữ liệu “một nửa giao dịch” vẫn xuất hiện | Producer không dùng Kafka transaction hoặc side effect nằm ngoài Kafka | Xác nhận producer transactional ID, transaction boundary và hệ thống liên quan |
| Group lag cao nhưng listener không nhận thêm record | LSO bị giữ bởi transaction đang mở | Đối chiếu LSO/HW/LEO, transaction duration và timeout |
| Offset listener có khoảng nhảy | Record abort/control marker không được giao | Hiểu đúng semantics offset; không tự suy ra mất message |
| Listener vẫn xử lý trùng record sau restart | Offset consumer chưa commit hoặc side effect ngoài Kafka không idempotent | Kiểm tra transactional offset commit, inbox và idempotency |
| Có `read_committed` nhưng Kafka→Kafka vẫn tạo duplicate output | Producer output và offset nguồn không chung Kafka transaction | Dùng container transaction manager và offset commit trong transaction |
| Producer bị fenced khi deploy nhiều replica | Transactional ID trùng giữa các producer sống đồng thời | Thiết kế prefix/ID duy nhất theo instance, kiểm tra rolling deployment |
| Nhiều DLT record bị lặp | DLT publish và offset nguồn không nguyên tử; recovery retry sau crash | Dùng provenance, deduplication hoặc transactional recovery phù hợp |
| Đổi cấu hình mà không tác dụng | Listener đang dùng `ConsumerFactory` khác | Xác nhận bean name, profile và Kafka client config thực tế |

Để xác định một consumer có thật sự ở `read_committed`, nên kiểm tra cấu hình client thực tế qua log khởi tạo hoặc cấu hình runtime được công cụ giám sát thu thập; không chỉ nhìn một dòng trong `application.properties` khi có nhiều profile/factory override.

## 15. Kịch bản kiểm thử tích hợp

Kiểm thử nên dùng Kafka broker có hỗ trợ transactions, producer transactional và consumer `read_committed`. Có thể dùng Kafka test container hoặc một cluster thử nghiệm. Các tình huống quan trọng:

1. **Transaction commit:** producer ghi hai record cùng transaction rồi commit; `read_committed` listener nhận đủ cả hai.
2. **Transaction abort:** producer ghi record rồi abort; `read_committed` listener không nhận record đó.
3. **Đối chứng `read_uncommitted`:** consumer khác group ở chế độ mặc định có thể nhìn thấy record abort để chứng minh khác biệt isolation.
4. **Record non-transactional:** producer thường ghi record; `read_committed` vẫn nhận đúng record ngoài transaction.
5. **Transaction còn mở:** producer giữ transaction chưa commit; xác nhận consumer chưa vượt qua LSO của partition.
6. **Commit sau khi chờ:** producer commit; xác nhận LSO tiến và record mới đủ điều kiện được giao.
7. **Producer crash/timeout:** bỏ dở transaction và kiểm tra khả năng abort/khôi phục, consumer không nhìn thấy output đã abort.
8. **Consume-transform-produce rollback:** cố ý ném exception ở listener transactional; xác nhận output trong transaction bị abort và input offset không được commit như đã xử lý xong.
9. **Crash sau database update:** kiểm tra consumer có thể nhận lại record nhưng inbox/idempotency ngăn side effect trùng.
10. **Nhiều listener factory:** xác nhận chỉ listener gắn `ConsumerFactory` tương ứng nhận isolation level đã chọn.

Với các kiểm thử, cần quan sát **record thực tế**, **producer transaction result**, **consumer group offset** và **trạng thái nghiệp vụ**. Chỉ nhìn tổng số record trong Kafka topic không đủ để chứng minh `read_committed` lọc đúng aborted records. Khi kiểm thử EOS Kafka→Kafka, downstream phải đọc ở `read_committed` để phân biệt output đã commit với output đã abort.

## 16. Runbook khi `read_committed` consumer đứng yên

Nếu consumer lag tăng nhưng listener không được gọi, có thể xử lý theo thứ tự:

1. Xác nhận listener ID, `group.id`, topic, partition và `isolation.level` thực tế của consumer.
2. Xác nhận topic có producer transactional hay không, và producer nào đang ghi.
3. So sánh committed offset của group, LSO và log-end/high-watermark nếu có metric/công cụ hỗ trợ.
4. Nếu LSO bị giữ, kiểm tra transaction mở lâu, transaction coordinator, timeout và lỗi producer.
5. Nếu LSO đã tiến nhưng listener vẫn không nhận record, kiểm tra partition assignment, pause/resume, poll thread, deserializer và error handler.
6. Kiểm tra transaction abort rate và producer fencing sau rolling deployment.
7. Không tự reset offset hoặc đổi sang `read_uncommitted` trên production để "lấy dữ liệu" khi chưa hiểu tác động tới dữ liệu đã abort.
8. Sửa producer/transaction timeout hoặc cấu hình consumer có kiểm soát; sau đó quan sát LSO, lag và throughput phục hồi.
9. Ghi lại nguyên nhân và bổ sung cảnh báo về transaction duration hoặc LSO lag.

Đổi một consumer quan trọng sang `read_uncommitted` để giải tỏa lag có thể khiến hệ thống xử lý các event vốn bị producer abort. Đó là thay đổi tính đúng đắn dữ liệu, không phải chỉ là một tối ưu hiệu năng. Nếu cần đọc raw log cho mục đích điều tra, dùng một consumer/group riêng biệt với quyền hạn và quy trình phù hợp, không thay đổi semantics của consumer nghiệp vụ.

## 17. Nguyên tắc thiết kế production

Khi dùng `read_committed` trong một hệ thống Spring Kafka Reliability Operations, cần giữ các nguyên tắc sau:

1. Xác định rõ producer có thực sự dùng Kafka transaction, và record nào nằm trong transaction.
2. Cấu hình `isolation.level=read_committed` trên **đúng consumer** cần thấy dữ liệu đã commit, không chỉ khai báo ở một factory không được sử dụng.
3. Chọn `enable.auto.commit=false` và transactional offset commit cho luồng Kafka→Kafka yêu cầu EOS trong phạm vi Kafka.
4. Đảm bảo producer transaction và offset nguồn thuộc cùng Kafka transaction nếu muốn nguyên tử giữa input progress và output.
5. Đừng đồng nhất producer transaction commit với consumer committed offset; đây là hai trách nhiệm khác nhau.
6. Thiết kế idempotency/inbox/outbox cho database, HTTP và các side effect ngoài Kafka.
7. Theo dõi LSO, transaction duration, abort rate, group lag và processing latency; hiểu sự khác nhau giữa LSO và log-end.
8. Tránh Kafka transaction kéo dài hoặc transactional ID xung đột giữa các instance đồng thời.
9. Không coi khoảng nhảy offset vì aborted/control records là mất dữ liệu.
10. Kiểm thử commit, abort, open transaction, timeout, restart, rebalance và transaction rollback trước khi dựa vào bảo đảm xử lý.

**Kết luận:** `read_committed consumer` là cấu hình kiểm soát **khả năng nhìn thấy record theo kết quả Kafka transaction**. Nó giúp listener không xử lý các record từ transaction đã abort và là điều kiện cần ở phía đọc đối với nhiều pipeline Kafka→Kafka cần exactly-once. Tuy nhiên, bảo đảm end-to-end còn phụ thuộc producer transaction, commit offset trong cùng giao dịch, idempotency và quan sát vận hành. Hiểu rõ Last Stable Offset cùng giới hạn của transaction giúp tránh cả hai sai lầm: đọc nhầm dữ liệu abort và ngộ nhận rằng bật một property đã tạo ra exactly-once cho mọi side effect.
