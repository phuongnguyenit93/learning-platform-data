# Commit offset trước và sau listener

## 1. Vì sao thời điểm commit offset quan trọng?

Kafka consumer đọc record từ partition và lưu tiến độ theo consumer group. Khi ứng dụng xử lý một record, có hai việc khác nhau:

1. Thực hiện công việc nghiệp vụ, ví dụ cập nhật database, tính toán hoặc gọi service khác.
2. Commit offset để Kafka biết group sẽ đọc tiếp từ vị trí nào.

Hai việc này thường không nằm trong cùng một transaction. Vì vậy, thứ tự giữa xử lý listener và commit offset quyết định cách ứng dụng phản ứng khi process bị crash, listener ném exception, broker mất kết nối hoặc consumer bị rebalance.

Có hai lựa chọn cơ bản:

- **Commit trước listener**: lưu tiến độ đọc trước khi chạy logic nghiệp vụ. Nếu ứng dụng dừng sau commit nhưng trước khi xử lý xong, record có thể bị bỏ qua ở lần chạy sau.
- **Commit sau listener**: chỉ lưu tiến độ sau khi listener xử lý thành công. Nếu ứng dụng dừng sau side effect nhưng trước commit, record có thể được giao lại và xử lý lần nữa.

Đây là sự đánh đổi giữa nguy cơ mất record và nguy cơ xử lý trùng. Với phần lớn listener nghiệp vụ, commit sau khi xử lý thành công thường phù hợp hơn, kết hợp với xử lý idempotent để chịu được redelivery.

## 2. Hiểu offset được commit là gì

### 2.1. Committed offset là vị trí tiếp theo sẽ đọc

Mỗi partition có một dãy offset riêng. Consumer group lưu committed offset theo tổ hợp group ID, topic và partition. Giá trị offset được commit thường là vị trí tiếp theo consumer cần đọc, không phải offset của record cuối cùng đã xử lý.

Ví dụ consumer xử lý record offset 10 thành công và commit offset 11:

~~~text
Partition orders-0

Offset:       8    9    10   11   12   13
Record:       A    B     C    D    E    F
                         |
                         +-- record đã xử lý: 10
                              committed offset: 11
                              lần đọc tiếp theo: 11
~~~

Nếu commit offset 11, Kafka hiểu rằng group đã xác nhận tiến độ qua record 10. Nếu consumer restart, nó tiếp tục từ offset 11 khi offset này vẫn hợp lệ.

### 2.2. Consumer position khác committed offset

Consumer có thể đã fetch hoặc xử lý một số record trong bộ nhớ nhưng chưa commit. Vì vậy cần phân biệt:

- **Consumer position**: vị trí tiếp theo mà consumer sẽ đọc trong phiên hiện tại.
- **Committed offset**: vị trí đã được lưu bền vững cho group trên Kafka.
- **Log end offset**: vị trí tiếp theo sau record mới nhất của partition.
- **Log start offset**: vị trí sớm nhất còn được giữ trong log.

Consumer position có thể tiến lên khi poll trả record, dù committed offset chưa thay đổi. Nếu process dừng trước commit, consumer khác có thể đọc lại từ committed offset cũ.

### 2.3. Offset được lưu theo từng partition

Một group có thể xử lý nhiều partition và mỗi partition có committed offset riêng. Không có một offset duy nhất đại diện cho toàn topic.

Nếu listener xử lý song song hoặc có công việc bất đồng bộ, ứng dụng cần bảo đảm chỉ commit một offset phản ánh các record đã hoàn tất liên tục theo thứ tự cần thiết của partition. Không thể commit vượt qua một record chưa xử lý xong rồi kỳ vọng Kafka tự biết record đó còn dang dở.

## 3. Commit trước listener: at-most-once

### 3.1. Trình tự xử lý

Commit trước listener nghĩa là ứng dụng lưu offset của record tiếp theo trước khi thực hiện side effect nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant K as Kafka
    participant L as Listener
    participant D as Database

    C->>K: Fetch record offset 10
    K-->>C: Record 10
    C->>K: Commit offset 11
    K-->>C: Commit success
    C->>L: Invoke listener(record 10)
    L->>D: Update business data
    D-->>L: Success
    L-->>C: Listener returns
~~~

Nếu ứng dụng crash sau khi commit offset 11 nhưng trước khi database cập nhật xong, lần chạy sau sẽ bắt đầu từ offset 11. Record 10 không được giao lại theo committed offset đó, dù nghiệp vụ có thể chưa hoàn tất.

### 3.2. Cửa sổ mất dữ liệu

~~~text
Fetch record 10
      |
      v
Commit offset 11
      |
      |  <-- process crash ở đây
      v
Listener xử lý record 10
      |
      v
Database commit
~~~

Nếu crash ở vùng giữa commit offset và xử lý nghiệp vụ, group đã tiến qua record 10 nhưng side effect chưa xảy ra. Đây là nguy cơ mất xử lý (message loss ở góc nhìn nghiệp vụ).

Vì vậy, commit trước listener thường tương ứng với at-most-once delivery: một record có thể không được xử lý nếu lỗi xảy ra sau commit, nhưng consumer không chủ động giao lại record đó chỉ vì listener chưa hoàn tất.

### 3.3. Khi nào commit trước có thể phù hợp?

Một số luồng có thể chấp nhận bỏ qua một phần record hơn là xử lý lặp:

- Telemetry hoặc metrics có thể được tổng hợp từ nhiều nguồn và chấp nhận mất một mẫu nhỏ.
- Thông báo không quan trọng, nơi duplicate gây tác động lớn hơn việc bỏ lỡ một thông báo.
- Dữ liệu tạm thời có thể được tái tạo từ nguồn khác.
- Một hệ thống downstream đã có cơ chế bù hoặc snapshot độc lập.

Đây phải là quyết định nghiệp vụ có chủ đích. Không nên chọn commit trước chỉ để tránh duplicate nếu record chứa lệnh thanh toán, thay đổi trạng thái đơn hàng hoặc một sự kiện cần xử lý đầy đủ.

## 4. Commit sau listener: at-least-once

### 4.1. Trình tự xử lý

Commit sau listener nghĩa là chỉ lưu offset khi phương thức listener đã hoàn tất thành công theo acknowledgment mode.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant K as Kafka
    participant L as Listener
    participant D as Database

    C->>K: Fetch record offset 10
    K-->>C: Record 10
    C->>L: Invoke listener(record 10)
    L->>D: Update business data
    D-->>L: Success
    L-->>C: Listener returns successfully
    C->>K: Commit offset 11
    K-->>C: Commit success
~~~

Nếu listener ném exception trước khi hoàn tất, offset chưa được commit theo đường xử lý thành công. Error handler có thể retry, recover hoặc chuyển record sang dead-letter topic tùy cấu hình.

### 4.2. Cửa sổ xử lý trùng

~~~text
Fetch record 10
      |
      v
Listener xử lý record 10
      |
      v
Database commit
      |
      |  <-- process crash ở đây
      v
Commit offset 11
~~~

Nếu process crash sau khi database đã commit nhưng trước khi Kafka offset được commit, group vẫn giữ committed offset cũ. Khi consumer hoạt động lại, record 10 có thể được giao lại. Database có thể nhận cùng một thao tác lần thứ hai.

Đây là at-least-once delivery: ứng dụng ưu tiên không bỏ qua record, nhưng một record có thể được xử lý nhiều lần. Listener cần idempotency để việc nhận lại cùng event không tạo side effect trùng.

### 4.3. Vì sao at-least-once thường được chọn?

Trong nhiều hệ thống nghiệp vụ, xử lý lại một event có thể được phát hiện và kiểm soát bằng event ID, unique constraint hoặc upsert. Mất một event có thể khó phát hiện và khó khôi phục hơn.

Commit sau listener tạo ra một ranh giới rõ ràng: chỉ tiến offset khi listener đã báo thành công. Tuy nhiên, nó không làm cho database và Kafka trở thành một transaction duy nhất. Cần thiết kế idempotency hoặc cơ chế phối hợp nếu listener ghi ra hệ thống bên ngoài.

## 5. So sánh commit trước và sau listener

| Tiêu chí | Commit trước listener | Commit sau listener |
|---|---|---|
| Thời điểm lưu offset | Trước side effect | Sau khi listener hoàn tất thành công |
| Delivery semantics thường thấy | At-most-once | At-least-once |
| Crash sau commit, trước xử lý | Có thể mất xử lý record | Chưa áp dụng nếu chưa đến commit |
| Crash sau side effect, trước commit | Thường không giao lại theo offset đã tiến | Có thể giao lại và tạo duplicate |
| Yêu cầu idempotency | Có thể vẫn cần cho các lần gửi lặp từ producer | Rất quan trọng cho redelivery |
| Phù hợp với | Dữ liệu có thể bỏ qua | Nghiệp vụ cần xử lý đầy đủ |
| Rủi ro chính | Mất xử lý | Xử lý trùng |

Không có một thời điểm commit đơn lẻ nào đồng thời loại bỏ cả hai cửa sổ lỗi khi side effect nằm ngoài Kafka. Để có độ tin cậy cao, phải thiết kế cả offset, transaction và side effect nghiệp vụ.

## 6. Spring Kafka quản lý commit offset như thế nào?

### 6.1. Listener container là nơi điều phối

Với **@KafkaListener**, ứng dụng thường không tự gọi **poll()** hoặc tự commit offset. Spring Kafka tạo listener container, container quản lý consumer, poll, chuyển record đến listener, xử lý exception và commit offset theo cấu hình.

Trong Spring Kafka, **enable.auto.commit** thường được đặt thành **false** nếu ứng dụng không khai báo rõ. Từ Spring Kafka 2.3, framework đặt mặc định này để container có thể quản lý commit. Nếu bật auto commit tường minh, commit do Kafka client thực hiện theo cơ chế auto-commit và không còn được gắn chặt với kết quả thành công của từng lần gọi listener.

Với listener nghiệp vụ, nên để container quản lý commit và chọn acknowledgment mode phù hợp. Điều này giúp tránh việc consumer tự commit theo timer trong khi listener vẫn đang thực hiện side effect.

### 6.2. Acknowledgment mode

Spring Kafka có các chế độ commit phổ biến sau. Tên và chi tiết có thể thay đổi theo phiên bản; hãy đối chiếu Javadoc khi nâng cấp.

| AckMode | Thời điểm commit |
|---|---|
| **RECORD** | Sau khi từng record được listener xử lý thành công |
| **BATCH** | Sau khi toàn bộ record trong một lần poll được xử lý |
| **TIME** | Khi đạt khoảng thời gian đã cấu hình và có offset cần commit |
| **COUNT** | Khi đạt số record đã xử lý theo ngưỡng |
| **COUNT_TIME** | Khi đạt ngưỡng số record hoặc thời gian |
| **MANUAL** | Listener gọi acknowledge; container commit theo quy tắc của mode manual |
| **MANUAL_IMMEDIATE** | Commit ngay khi acknowledge được gọi trên consumer thread; nếu gọi từ thread khác, yêu cầu được xử lý theo cơ chế container |

**BATCH** là mode mặc định thường gặp của listener container. **RECORD** phù hợp với record listener khi muốn commit sau từng record thành công. Với batch listener, cần hiểu rằng listener nhận cả batch; việc commit thường gắn với kết quả xử lý batch.

### 6.3. RECORD và BATCH khác nhau ra sao?

Giả sử một lần poll trả về record offset 10, 11 và 12 của cùng partition.

Với **RECORD**:

~~~text
Listener xử lý 10 thành công -> commit offset 11
Listener xử lý 11 thành công -> commit offset 12
Listener xử lý 12 thành công -> commit offset 13
~~~

Nếu lỗi ở record 11, offset 11 chưa được commit theo lần xử lý đó. Record 10 đã có thể được commit, còn 11 và các record tiếp theo sẽ được xử lý theo error handler và trạng thái consumer.

Với **BATCH**:

~~~text
Poll trả về 10, 11, 12
        |
        v
Listener xử lý các record
        |
        +-- Tất cả thành công
        |       |
        |       v
        |   Commit offset 13
        |
        +-- Có lỗi
                |
                v
           Error handler xử lý
~~~

**BATCH** giảm số lần commit, có thể tăng hiệu quả khi throughput cao. Đổi lại, nếu batch lỗi, phạm vi record cần retry hoặc phục hồi có thể lớn hơn tùy error handler.

## 7. Cấu hình Spring Boot cho commit sau listener

Một cấu hình cơ bản:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
    listener:
      ack-mode: record
~~~

Các thuộc tính có vai trò khác nhau:

- **enable-auto-commit: false** để container điều phối commit.
- **ack-mode: record** commit sau mỗi record listener thành công.
- **auto-offset-reset** chỉ được dùng khi group không có offset hợp lệ; nó không quyết định commit trước hay sau listener.
- Serializer/deserializer phải tương thích với event producer gửi.

Ví dụ listener đồng bộ:

~~~java
@Component
@RequiredArgsConstructor
public class OrderListener {

    private final OrderService orderService;

    @KafkaListener(
        topics = "orders",
        groupId = "billing-service"
    )
    public void onOrderCreated(OrderCreated event) {
        orderService.applyIdempotently(event);
    }
}
~~~

Khi phương thức trả về bình thường, container xem lần xử lý thành công và commit theo acknowledgment mode. Nếu phương thức ném exception, container chuyển lỗi qua error handler; offset không được xem là thành công chỉ vì listener đã được gọi.

## 8. Manual acknowledgment: listener chủ động báo hoàn tất

### 8.1. MANUAL

Khi cần kiểm soát thời điểm xác nhận, listener có thể nhận tham số **Acknowledgment** và gọi **acknowledge()** sau khi hoàn tất công việc cần thiết.

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual
~~~

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    orderService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
~~~

Với **MANUAL**, lời gọi acknowledge đánh dấu record đã được xử lý; container quản lý việc commit theo semantics của manual mode, thường gắn với việc xử lý hết các record từ poll hiện tại. Nó không có nghĩa mọi lời gọi acknowledge đều lập tức phát một commit request.

### 8.2. MANUAL_IMMEDIATE

Nếu cần commit ngay khi acknowledge trên consumer thread, dùng **MANUAL_IMMEDIATE**:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    orderService.applyIdempotently(event);
    acknowledgment.acknowledge();
}
~~~

Điều quan trọng là gọi acknowledge sau khi side effect đã hoàn tất. Nếu acknowledge trước khi database commit, ứng dụng tự tạo cửa sổ mất xử lý giống commit trước listener.

**MANUAL_IMMEDIATE** có semantics phụ thuộc thread. Khi gọi trên consumer thread, container có thể commit ngay; khi gọi từ thread khác, acknowledgment được xếp hàng để xử lý theo cơ chế container. Không gọi acknowledge tùy tiện từ thread nền mà không hiểu hợp đồng của phiên bản Spring Kafka đang dùng.

### 8.3. Không nuốt exception rồi acknowledge

Ví dụ không nên dùng:

~~~java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(
    OrderCreated event,
    Acknowledgment acknowledgment
) {
    try {
        orderService.apply(event);
    } catch (Exception ex) {
        log.error("Cannot process order", ex);
    }

    acknowledgment.acknowledge();
}
~~~

Đoạn code bắt lỗi, ghi log rồi vẫn acknowledge. Container sẽ được báo rằng record đã hoàn tất, vì vậy offset có thể tiến lên dù nghiệp vụ thất bại. Nếu muốn retry hoặc chuyển DLT, để exception được truyền đến error handler hoặc gọi acknowledge chỉ sau một quyết định phục hồi có chủ đích.

## 9. Xử lý exception và commit offset

### 9.1. Listener ném exception

Khi listener ném exception, container chuyển quyền xử lý cho error handler. Với **DefaultErrorHandler**, ứng dụng có thể cấu hình số lần retry, backoff và recoverer.

Một số hướng xử lý:

- Retry lỗi tạm thời như timeout database hoặc service chưa sẵn sàng.
- Không retry vô hạn lỗi dữ liệu không thể khắc phục.
- Chuyển record sang dead-letter topic sau khi hết retry.
- Ghi metadata gốc như topic, partition, offset và exception để điều tra.
- Chỉ coi record đã phục hồi khi chính sách recoverer hoàn tất theo cấu hình.

Nếu listener bắt exception và trả về bình thường, container thường xem listener call là thành công. Đây là nguyên nhân phổ biến khiến offset được commit dù nghiệp vụ không hoàn tất.

### 9.2. Commit khi error handler phục hồi

Khi error handler xử lý được lỗi, hành vi commit phụ thuộc acknowledgment mode và các thuộc tính của error handler, ví dụ việc commit sau khi handler xử lý xong và chính sách commit record đã recover. Một số tình huống cần bật cấu hình phù hợp như **ackAfterHandle** hoặc **commitRecovered**; khả năng và yêu cầu cụ thể phụ thuộc phiên bản và ack mode.

Không nên mặc định rằng chuyển record sang DLT tự động có nghĩa offset nguồn đã commit theo cách mong muốn. Hãy xác nhận cả hai kết quả: record đã được publish sang DLT và tiến độ consumer group đã được lưu.

### 9.3. Retry blocking và retry topic

Retry blocking thực hiện các lần thử lại trong luồng xử lý partition. Nó có thể giữ partition lại trong lúc chờ backoff và ảnh hưởng record phía sau.

Retry topic chuyển record lỗi sang topic khác để xử lý lại sau. Mô hình này giúp partition chính tiếp tục, nhưng có thể thay đổi thứ tự xử lý: record phía sau có thể hoàn tất trước record đang chờ retry.

Dù dùng chiến lược nào, commit offset phải phản ánh đúng việc record đã được xử lý hoặc được phục hồi theo chính sách. Nếu yêu cầu ordering nghiêm ngặt theo key, hãy đánh giá tác động của retry topic.

## 10. Side effect database và Kafka offset không phải một transaction

Một listener thường cập nhật database rồi mới commit Kafka offset:

~~~text
Kafka record
    |
    v
Listener
    |
    v
Database transaction commit
    |
    v
Kafka offset commit
~~~

Nếu database commit thành công nhưng offset commit thất bại, record được giao lại. Nếu offset commit trước database commit, ứng dụng có thể mất xử lý khi database thất bại.

Kafka offset commit và database transaction là hai thao tác riêng. Chọn commit sau listener giúp ưu tiên at-least-once nhưng không tạo atomicity xuyên hệ thống.

### 10.1. Idempotency bằng event ID

Mỗi event nên có ID ổn định, ví dụ **eventId**. Database có thể lưu ID đã xử lý với unique constraint. Khi event được giao lại, thao tác ghi nhận ID phát hiện duplicate và không lặp side effect.

Ví dụ khái quát:

~~~java
@Transactional
public void applyIdempotently(OrderCreated event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderRepository.apply(event);
}
~~~

Hai thao tác ghi inbox và cập nhật nghiệp vụ phải nằm trong cùng database transaction. Nếu cập nhật nghiệp vụ thất bại, bản ghi inbox cũng phải rollback để lần giao lại có thể thử lại. Cách triển khai cụ thể phụ thuộc database và cách insert-if-absent được hỗ trợ.

### 10.2. Inbox pattern

Inbox table lưu event ID đã tiếp nhận. Khi consumer nhận event:

1. Bắt đầu database transaction.
2. Insert event ID vào inbox với unique constraint.
3. Nếu ID đã tồn tại, coi đây là redelivery và không lặp side effect.
4. Nếu insert thành công, thực hiện cập nhật nghiệp vụ.
5. Commit database transaction.
6. Listener trả về thành công để container commit Kafka offset.

Nếu process crash sau bước 5 nhưng trước bước 6, record được giao lại. Lần sau inbox phát hiện event ID đã có và listener có thể trả về thành công mà không chạy lại side effect.

### 10.3. Transactional outbox

Nếu listener cập nhật database và cần phát một event Kafka tiếp theo, transactional outbox giúp ghi thay đổi nghiệp vụ và outbox record trong cùng database transaction. Một publisher riêng đọc outbox và gửi Kafka.

Outbox không làm Kafka offset và database thành một transaction phân tán. Nó tạo một nguồn sự thật bền vững để publisher gửi lại khi gặp lỗi. Publisher và consumer vẫn cần idempotency vì gửi lại có thể tạo duplicate.

## 11. Exactly-once và Kafka transaction

Trong luồng Kafka-to-Kafka, Kafka transaction có thể kết hợp việc gửi output record với commit offset input trong cùng transaction. Nếu transaction commit, output và offset cùng được công nhận; nếu abort, chúng không được xem là đã commit một nửa.

Spring Kafka có thể phối hợp transactional producer factory và listener container để thực hiện consume-process-produce trong một Kafka transaction. Consumer downstream dùng isolation level **read_committed** để chỉ đọc record từ transaction đã commit.

Cơ chế này giúp đạt exactly-once semantics trong phạm vi Kafka transaction. Nó không bao gồm cập nhật database, gửi email hoặc gọi HTTP. Nếu listener có side effect ngoài Kafka, vẫn cần inbox/outbox hoặc idempotency.

Không nên mô tả at-least-once listener có database side effect là exactly-once chỉ vì offset được commit sau khi listener trả về. Khoảng hở giữa database commit và offset commit vẫn tồn tại.

## 12. Commit sync và async

Kafka consumer có thể commit offset theo cách đồng bộ hoặc bất đồng bộ:

- **commitSync()** chờ broker phản hồi kết quả commit. Cách này dễ xác định commit đã thành công hay lỗi nhưng có thể tăng latency.
- **commitAsync()** gửi commit request bất đồng bộ và nhận callback khi kết quả được trả về. Cách này giảm thời gian chờ ở luồng gọi nhưng cần xử lý lỗi và thứ tự commit cẩn thận.

Spring listener container có thể điều khiển kiểu commit qua cấu hình container như **syncCommits**. Giá trị mặc định và hành vi có thể khác theo phiên bản; cần kiểm tra cấu hình đang chạy.

Ví dụ Kafka API cấp thấp:

~~~java
consumer.commitSync(
    Map.of(
        new TopicPartition("orders", 0),
        new OffsetAndMetadata(11)
    )
);
~~~

Offset được commit ở ví dụ là 11, tức vị trí đọc tiếp theo. Khi dùng trực tiếp Kafka Consumer, cần lưu ý **KafkaConsumer** không thread-safe; các thao tác consumer phải tuân thủ thread sở hữu consumer.

Trong Spring Kafka, nên để listener container quản lý commit qua ack mode hoặc **Acknowledgment**. Tránh tự gọi commit trực tiếp trong listener nếu không có thiết kế rõ ràng về quyền sở hữu offset, vì có thể xung đột với commit do container thực hiện.

## 13. Rebalance và commit offset

Khi partition bị revoke, consumer có thể có record đã xử lý nhưng chưa commit. Listener container thường có cơ chế commit offset pending theo acknowledgment mode và callback rebalance trước khi nhả partition.

Ứng dụng có thể dùng **ConsumerAwareRebalanceListener** hoặc callback rebalance tương ứng để hoàn tất công việc cục bộ trước khi partition được chuyển. Cần giữ callback ngắn và không chờ vô hạn.

Trong cooperative rebalancing, callback revoke có thể chỉ nhận partition đang được chuyển. Không giả định toàn bộ assignment sẽ bị thu hồi. Với partition bị mất quyền sở hữu, không nên cố commit như thể consumer vẫn còn quyền kiểm soát.

Nếu listener chạy task bất đồng bộ, phải theo dõi task theo partition. Không để task cũ tiếp tục cập nhật database sau khi partition đã được giao cho consumer khác; nếu không, hai consumer có thể tạo side effect đồng thời cho cùng một record.

## 14. Cấu hình minh họa cho các lựa chọn commit

### 14.1. Commit sau mỗi record thành công

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
~~~

Với record listener, container commit sau khi từng record được xử lý thành công. Đây là lựa chọn dễ hiểu khi cần giảm phạm vi record chưa commit sau lỗi.

### 14.2. Commit sau cả batch poll

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
~~~

Container commit sau khi xử lý thành công tất cả record trong một lần poll. Mode này giảm số lần commit, nhưng một batch lỗi có thể cần xử lý lại phạm vi lớn hơn tùy error handler.

### 14.3. Manual immediate

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: manual_immediate
~~~

Listener gọi **acknowledge()** sau khi side effect cần thiết hoàn tất. Cần gọi trên consumer thread để có semantics immediate rõ ràng.

Không nên dùng **auto.offset.reset** để điều khiển thời điểm commit. Reset policy chỉ chọn vị trí bắt đầu khi không có committed offset hợp lệ; ack mode và acknowledgment điều khiển việc lưu tiến độ trong lúc xử lý.

## 15. Các lỗi thường gặp

**Commit trước khi database transaction hoàn tất:** offset tiến lên dù side effect chưa bền vững. Nếu process dừng, record có thể bị bỏ qua.

**Acknowledge trước khi xử lý:** listener báo thành công quá sớm. Nếu xử lý phía sau thất bại, container có thể đã commit offset.

**Bắt exception rồi trả về bình thường:** container không biết nghiệp vụ thất bại và có thể commit theo ack mode.

**Giả định commit sau listener loại bỏ duplicate:** crash sau database commit nhưng trước offset commit vẫn khiến record được giao lại.

**Dùng auto commit cho listener cần kiểm soát chặt:** timer commit không phản ánh chính xác kết quả của từng lần xử lý nghiệp vụ.

**Commit offset vượt qua record chưa hoàn tất:** đặc biệt nguy hiểm khi xử lý song song trong cùng partition; lần restart có thể bỏ qua record chưa xử lý.

**Tự commit trong listener cùng lúc container cũng commit:** tạo hai luồng điều khiển offset, khó dự đoán và dễ commit sai tiến độ.

**Coi DLT publish thành công là nguồn đã commit:** cần kiểm tra cấu hình recoverer và hành vi commit của error handler.

**Nhầm commit offset với xóa record:** commit chỉ lưu tiến độ group. Record vẫn được giữ theo retention hoặc cleanup policy của topic và có thể được group khác đọc.

## 16. Quy trình điều tra khi record bị mất hoặc xử lý trùng

Khi một record không được xử lý hoặc xuất hiện nhiều lần, lần theo các mốc thời gian:

1. Xác định topic, partition, offset và event ID của record.
2. Xác nhận consumer group đã fetch record hay chưa.
3. Xem listener có bắt đầu xử lý và side effect có commit hay không.
4. Kiểm tra committed offset trước và sau lần xử lý.
5. Đọc log exception và error handler để biết record được retry, recover hay bỏ qua theo cấu hình nào.
6. Kiểm tra rebalance hoặc restart có xảy ra giữa side effect và offset commit không.
7. Xác định listener có idempotency key, inbox hoặc unique constraint không.
8. Nếu offset đã tiến qua record nhưng side effect chưa có, điều tra auto commit hoặc commit trước listener.
9. Nếu side effect đã có nhưng offset chưa tiến, xác định redelivery có xảy ra và side effect có được bảo vệ idempotent không.

Nên log event ID, group ID, topic, partition, offset và correlation ID. Không log toàn bộ payload nếu có dữ liệu nhạy cảm. Đối chiếu timestamp của database transaction với commit offset giúp xác định cửa sổ lỗi.

## 17. Kiểm thử thời điểm commit

Dùng topic thử nghiệm và consumer group riêng để kiểm tra các cửa sổ lỗi mà không tác động dữ liệu production.

### Kịch bản commit sau listener

1. Gửi một record có event ID dễ nhận diện.
2. Listener ghi event ID vào database.
3. Tạo một điểm dừng có kiểm soát sau database commit nhưng trước khi container commit offset.
4. Dừng process tại điểm đó.
5. Khởi động lại consumer với cùng group ID.
6. Xác nhận record được giao lại từ committed offset cũ.
7. Xác nhận inbox/unique constraint ngăn side effect được thực hiện lần hai.

### Kịch bản commit trước listener

1. Dùng consumer test có thể commit offset tường minh trước khi xử lý.
2. Gửi một record mới.
3. Commit offset tiếp theo trước side effect.
4. Dừng process trước khi listener hoàn tất.
5. Khởi động lại với cùng group ID.
6. Xác nhận consumer tiếp tục từ offset đã commit và record cũ không được giao lại.

### Kịch bản exception

1. Cho listener ném exception trước side effect.
2. Xác nhận error handler retry hoặc chuyển DLT theo cấu hình.
3. Cho listener ném exception sau khi side effect đã commit.
4. Xác nhận record có thể được giao lại và thao tác idempotent không tạo duplicate.
5. Kiểm tra committed offset và DLT record sau mỗi kịch bản.

Kiểm thử phải quan sát cả trạng thái Kafka và database. Chỉ xác nhận log listener được gọi là chưa đủ để chứng minh commit offset đúng thời điểm.

## 18. Nguyên tắc lựa chọn trong production

- Ưu tiên commit sau khi listener hoàn tất thành công cho nghiệp vụ cần xử lý đầy đủ.
- Dùng **enable.auto.commit=false** để Spring listener container điều phối commit.
- Chọn **RECORD** hoặc **BATCH** theo ranh giới xử lý và throughput.
- Dùng **MANUAL** hoặc **MANUAL_IMMEDIATE** khi cần điều khiển acknowledgment tường minh.
- Chỉ acknowledge sau khi side effect cần thiết đã bền vững.
- Để exception đi đến error handler khi muốn retry hoặc recover.
- Thiết kế listener idempotent bằng event ID, inbox, unique constraint hoặc upsert.
- Không giả định Kafka offset và database transaction được commit nguyên tử cùng nhau.
- Dùng Kafka transaction cho luồng Kafka-to-Kafka cần atomicity; dùng outbox/inbox cho ranh giới database.
- Theo dõi committed offset, consumer lag, retry, DLT, rebalance và thời gian xử lý listener.

Commit trước listener ưu tiên tránh giao lại record nhưng có thể làm mất xử lý khi process dừng sau commit. Commit sau listener ưu tiên không bỏ qua record nhưng cần chấp nhận redelivery nếu offset chưa được lưu. Spring Kafka cung cấp acknowledgment mode và listener container để điều phối commit; ứng dụng cần kết hợp chúng với idempotency và transaction phù hợp để bảo vệ side effect nghiệp vụ.
