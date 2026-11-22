# EOS trong Spring Kafka

**Exactly-once semantics (EOS)** trong Spring Kafka là khả năng bảo đảm rằng một chuỗi **đọc record từ Kafka → xử lý → ghi record mới vào Kafka** có thể được quan sát như một lần xử lý thành công duy nhất trong phạm vi Kafka, kể cả khi consumer hoặc producer gặp lỗi ở những thời điểm nhạy cảm. Cơ chế cốt lõi là **Kafka transaction**, trong đó các output record và offset tiêu thụ của consumer được commit **nguyên tử**: hoặc cả hai cùng được xác nhận, hoặc cả hai không được xác nhận.

Điều đó không có nghĩa listener chỉ được gọi đúng một lần. Trong các tình huống crash, rebalance hoặc abort transaction, một input record có thể được listener xử lý lại. EOS bảo vệ kết quả **Kafka-to-Kafka** khỏi việc hiển thị output trùng do các transaction đã abort; nó không tự tạo exactly-once cho cập nhật database, HTTP API, email hay các side effect nằm ngoài Kafka transaction.

Bài học này giải thích phạm vi cam kết của EOS, cách cấu hình transaction trong Spring Kafka, xử lý lỗi, producer fencing, tương tác với offset và retry, giới hạn khi tích hợp database, cách kiểm thử, cùng các lưu ý vận hành trong production.

## 1. Exactly-once cần được hiểu đúng phạm vi

Kafka cung cấp những tính năng liên quan nhưng không đồng nhất:

| Tính năng | Giải quyết vấn đề gì? | Không tự bảo đảm điều gì? |
|---|---|---|
| Producer idempotence | Giảm nguy cơ ghi trùng do producer tự retry request trong một producer session | Không gộp việc commit consumer offset với output |
| Kafka transaction | Commit hoặc abort một tập ghi Kafka và offset trong cùng transaction | Không giao dịch nguyên tử với database bên ngoài |
| `read_committed` isolation | Consumer không nhìn thấy dữ liệu từ Kafka transaction đã abort | Không sửa các side effect ngoài Kafka |
| Spring Kafka transactional listener container | Bao quanh quá trình nhận và xử lý record bằng Kafka transaction, đưa offset vào transaction khi thành công | Không làm listener chỉ được gọi một lần |
| Idempotent business handler | Không tạo tác động nghiệp vụ trùng khi record được xử lý lại | Không thay thế yêu cầu transaction để atomic output và offset |

Một phát biểu chính xác là: **EOS của Kafka cho luồng read-process-write bảo đảm kết quả ghi vào Kafka và vị trí tiêu thụ của input được commit cùng nhau**, khi dùng đúng producer transactional, container transactional và consumer đọc output ở chế độ phù hợp.

### 1.1. Vì sao tên gọi dễ gây hiểu lầm?

Giả sử consumer đọc `OrderCreated`, tính toán và ghi `InvoiceRequested` vào topic khác. Listener có thể đã chạy lần đầu, gửi output nhưng process chết trước khi Kafka transaction commit. Sau restart, cùng `OrderCreated` được đọc lại và listener chạy lần hai. Nếu transaction lần đầu bị abort, một downstream consumer `read_committed` chỉ thấy output của transaction lần hai đã commit. **Kết quả Kafka chỉ được xác nhận một lần, nhưng code có thể chạy hai lần.**

Nếu listener trong ví dụ còn gọi một API gửi email trước khi transaction commit, email có thể đã được gửi hai lần. Kafka không có quyền rollback email.

## 2. Vấn đề khi chỉ dùng at-least-once

Với consumer truyền thống, đọc input, gửi output và commit offset là các hoạt động có thể độc lập.

~~~text
Input: orders.events, partition 0, offset 40
       |
       v
Consumer xử lý OrderCreated
       |
       v
Producer gửi InvoiceRequested -> output được ghi
       |
       X Process crash trước khi commit input offset
       |
       v
Restart: consumer lại đọc offset 40
       |
       v
Producer gửi InvoiceRequested lần nữa
~~~

Nếu output là một side effect Kafka bình thường và không có transaction hoặc deduplication, downstream có thể nhận hai bản ghi `InvoiceRequested`.

Một lỗi theo chiều ngược lại cũng nguy hiểm: nếu ứng dụng commit offset 41 **trước khi** output được ghi thành công, process crash có thể khiến input offset 40 bị bỏ qua mà không có output.

Hai thao tác phải được ràng buộc nguyên tử:

1. Ghi output Kafka.
2. Commit vị trí đọc input Kafka.

Đó là lý do cần Kafka transaction thay vì chỉ bật retry hoặc idempotent producer.

## 3. Cơ chế read-process-write với Kafka transaction

Một listener container có transaction manager sẽ bắt đầu transaction trước khi gọi listener. Listener dùng `KafkaTemplate` thuộc producer factory transactional để gửi output. Nếu listener hoàn tất thành công, container đưa offset input vào transaction và commit. Nếu listener ném exception, transaction bị rollback; output của transaction không được consumer `read_committed` nhìn thấy, và input có thể được đọc lại sau recovery.

~~~text
Consumer poll -> Input offset 40
                   |
                   v
           BEGIN Kafka transaction
                   |
                   v
          Listener xử lý event
                   |
                   v
         KafkaTemplate.send(output)
                   |
            +------+------+
            |             |
         Thành công       Exception
            |             |
            v             v
    Gắn input offset    Abort Kafka transaction
    vào transaction     (output bị abort)
            |             |
            v             v
    Commit transaction  Record có thể được
    (output + offset)   giao lại sau rollback
            |
            v
  Downstream read_committed
  thấy output đã commit
~~~

### 3.1. Atomicity thực sự bao gồm gì?

Kafka transaction cho phép các write đến **nhiều topic hoặc partition Kafka** và việc commit offset của input consumer cùng nằm trong một transaction. Commit thành công thì các record đầu ra và offset tiêu thụ được xác nhận cùng nhau; abort thì output không trở thành committed output và offset từ transaction đó không tiến lên.

Điều này không biến toàn bộ microservice thành một distributed transaction. Database transaction, cache update, HTTP request, filesystem write hoặc gửi thông báo không tự tham gia Kafka transaction.

### 3.2. Offset được commit là vị trí tiếp theo

Với input ở offset 40, consumer group commit offset 41 khi đã xử lý thành công record đó. Nếu có nhiều record trong cùng transaction, offset được commit cho từng partition là vị trí tiếp theo sau record cuối cùng được xử lý thành công trong phạm vi đó.

Trong container transaction, Spring Kafka điều phối việc gửi offset đến transaction. Listener thông thường không tự gọi KafkaConsumer.commitSync() hoặc dùng một Kafka producer khác để commit offset.

## 4. Các thành phần Spring Kafka cần có

Một cấu hình EOS read-process-write thường gồm:

1. **ConsumerFactory** tạo Kafka consumer cho input.
2. **ProducerFactory** hỗ trợ Kafka transaction, với transactional ID prefix.
3. **KafkaTransactionManager** hoặc transaction manager tương thích.
4. **Transactional listener container** sử dụng manager đó.
5. **KafkaTemplate** gửi output qua producer transactional tương ứng.
6. Downstream consumers sử dụng `isolation.level=read_committed` nếu cần quan sát chỉ những transaction đã commit.

~~~text
ConsumerFactory
      |
      v
Listener container ---> KafkaTransactionManager
      |                         |
      v                         v
@KafkaListener            Transactional ProducerFactory
      |                         |
      v                         v
KafkaTemplate -----------------> Kafka broker
                                 |
                                 +-- Output records
                                 +-- Consumer offsets
                                 +-- Commit/abort marker
~~~

Không đủ khi chỉ tạo `KafkaTemplate` có transaction manager nhưng listener container vẫn commit offset riêng. Ngược lại, nếu container transactional nhưng output producer không tham gia transaction đó, output cũng không được ràng buộc nguyên tử với offset.

## 5. Cấu hình Spring Boot

Một ví dụ cấu hình cho ứng dụng chuyển đổi event từ topic đầu vào sang topic đầu ra:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-processor
      enable-auto-commit: false
      isolation-level: read_committed
      auto-offset-reset: earliest
    producer:
      transaction-id-prefix: billing-tx-
      acks: all
    listener:
      ack-mode: record
~~~

Ý nghĩa của các thuộc tính:

| Property | Ý nghĩa |
|---|---|
| `spring.kafka.producer.transaction-id-prefix` | Bật cơ chế transactional producer trong cấu hình Spring Boot phù hợp, làm cơ sở tạo transactional ID |
| `enable-auto-commit: false` | Để container kiểm soát offset thay vì Kafka consumer tự động commit theo timer |
| `isolation-level: read_committed` | Consumer đọc Kafka transaction đã commit, không đọc output transaction bị abort |
| `acks: all` | Producer chờ xác nhận từ broker theo chính sách acks |
| `ack-mode: record` | Minh họa ack mode của container; với transaction, offset vẫn được gửi vào transaction theo container |
| `group-id` | Định danh consumer group, cần ổn định theo nghiệp vụ và deployment |

Lưu ý: việc bật `read_committed` trên **input consumer** bảo vệ nó khi input topic có transactional producers. Để downstream chỉ thấy output đã commit, **downstream consumer cũng phải dùng `read_committed`**. Chỉ chỉnh input consumer không thay đổi isolation của các service khác.

### 5.1. Transaction ID prefix phải được thiết kế theo deployment

Trong production có nhiều pod/instance chạy đồng thời, phải bảo đảm các transactional ID do chúng tạo ra không đụng nhau ngoài ý muốn. Một prefix theo ứng dụng chưa chắc đủ nếu các instance dùng cùng không gian transactional ID.

Ví dụ chiến lược:

~~~text
billing-tx-<deployment-instance-id>-
~~~

Mỗi pod nhận một instance identifier phù hợp với vòng đời deployment, sau đó Spring Kafka tạo transactional IDs với suffix cho các producer trong cache. Không dùng cùng transactional ID cho hai producer hoạt động đồng thời vì broker có thể fence một producer.

Tính duy nhất phải được bảo đảm trên tất cả instance đang chạy, không chỉ giữa các thread trong một pod. Khi scale out, rolling update hoặc blue/green deployment, cần kiểm tra không gian ID ở cả phiên bản cũ lẫn mới.

### 5.2. Spring Boot auto-configuration và custom factory

Trong một cấu hình Spring Boot thông thường, transaction ID prefix cho phép Boot tạo transactional producer support và `KafkaTransactionManager` nếu điều kiện auto-configuration thỏa mãn. Tuy nhiên, khi ứng dụng khai báo `ConcurrentKafkaListenerContainerFactory` riêng hoặc thay đổi manager/producer factory, cần **xác nhận listener container thật sự được gắn Kafka transaction manager**.

Không kết luận EOS hoạt động chỉ vì file YAML có `transaction-id-prefix`. Hãy xác nhận bean thực tế, listener container factory và đường send của `KafkaTemplate`.

## 6. Ví dụ listener đọc Kafka và ghi Kafka trong một transaction

Giả sử input topic `orders.created` chứa `OrderCreated`, còn output `billing.requests` chứa `BillingRequested`. Logic chỉ chuyển đổi sự kiện và ghi Kafka, không gọi database hay HTTP API.

~~~java
@Component
public class BillingRequestListener {

    private final KafkaTemplate<String, BillingRequested> kafkaTemplate;

    public BillingRequestListener(
            KafkaTemplate<String, BillingRequested> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "billing-processor",
            containerFactory = "ordersTransactionalFactory")
    public void onOrder(
            ConsumerRecord<String, OrderCreated> record)
            throws Exception {

        OrderCreated source = record.value();
        BillingRequested result = new BillingRequested(
                source.orderId(),
                source.customerId(),
                source.total());

        kafkaTemplate.send(
                "billing.requests",
                record.key(),
                result).get(10, TimeUnit.SECONDS);
    }
}
~~~

Đây là ví dụ Java minh họa; các record type và serializer cần được khai báo trong ứng dụng thực tế. `get(10, TimeUnit.SECONDS)` giúp lỗi gửi Kafka xuất hiện trong lần xử lý listener thay vì bị bỏ qua trong future. Cần chọn timeout dựa trên SLA và transaction timeout của hệ thống.

Trong cơ chế container transaction:

1. Container bắt đầu Kafka transaction.
2. Listener gọi `kafkaTemplate.send(...)`.
3. KafkaTemplate dùng producer transactional tham gia transaction hiện hành khi được cấu hình đúng ProducerFactory.
4. Listener trả thành công.
5. Container gửi offset input vào transaction và commit transaction.

Nếu send thất bại hoặc listener ném exception, container abort transaction theo quy trình xử lý lỗi.

### 6.1. Không bắt exception rồi trả thành công

Một lỗi thường gặp:

~~~java
@KafkaListener(topics = "orders.created")
public void wrong(OrderCreated event) {
    try {
        sendOutput(event);
    }
    catch (Exception ex) {
        log.error("Failed to send output", ex);
        // Sai: trả thành công dù nghiệp vụ gửi output thất bại.
    }
}
~~~

Nếu listener kết thúc bình thường và transaction được commit mà không có output mong muốn, offset có thể được xác nhận như đã xử lý. Hãy để exception đi lên container, hoặc thực hiện recovery bền vững rõ ràng trước khi coi record thành công.

### 6.2. Tạo transactional listener factory rõ ràng

Trong ứng dụng có nhiều factory, có thể cấu hình riêng factory có transaction manager:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersTransactionalFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaAwareTransactionManager<?, ?> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);

    return factory;
}
~~~

Ví dụ dùng API cấu hình container của các phiên bản Spring Kafka có `setKafkaAwareTransactionManager(...)`. Một số phiên bản cũ có API đặt transaction manager với tên khác. Hãy đối chiếu phiên bản dependency đang dùng. Manager phải quản lý ProducerFactory tương thích với `KafkaTemplate` được listener sử dụng.

Trong đoạn ví dụ, listener dùng container factory có transaction, chứ không chỉ gửi Kafka trong một transaction tự mở không liên kết offset input.

## 7. Có cần @Transactional trên @KafkaListener?

Khi **listener container** được cấu hình Kafka transaction manager, container đã tạo transaction trước khi gọi listener. Vì vậy, đối với luồng Kafka-to-Kafka thông thường, không nhất thiết phải thêm `@Transactional` vào listener chỉ để mở Kafka transaction một lần nữa.

`@Transactional` ở service có thể phục vụ database transaction hoặc một transaction boundary khác, nhưng cần hiểu rõ:

- Transaction nào bắt đầu trước?
- KafkaTemplate có tham gia transaction của container không?
- Offset consumer được commit trong Kafka transaction nào?
- Database transaction có được commit trước hoặc sau Kafka transaction không?
- Khi một trong hai commit thất bại, hệ thống có thể phục hồi thế nào?

Không nên kết hợp nhiều transaction manager hoặc chú thích `@Transactional` không xác định manager rồi mặc nhiên coi đó là một giao dịch nguyên tử giữa Kafka và database.

## 8. Producer idempotence chưa đủ cho read-process-write EOS

Kafka producer có idempotence để tránh một producer retry request làm broker ghi lặp cùng batch trong phạm vi bảo đảm của producer session. Nhưng:

~~~text
Consume offset 40
      |
      v
Producer idempotent gửi output
      |
      v
Crash trước commit consumer offset
      |
      v
Consume lại offset 40
      |
      v
Application gửi một output mới
~~~

Producer idempotence không nhận diện hai lần gọi nghiệp vụ đó là cùng một event; đây có thể là hai hành động send khác nhau. Cần Kafka transaction gộp output và offset, hoặc dùng chiến lược deduplication ở consumer downstream phù hợp.

Transactions xây trên các cơ chế của Kafka producer, nhưng không thể thay thế bằng việc chỉ bật `enable.idempotence`.

## 9. Isolation level: read_committed và read_uncommitted

Kafka consumer có thể cấu hình `isolation.level`:

| Isolation | Dữ liệu được trả về |
|---|---|
| `read_uncommitted` | Có thể đọc record thuộc transaction sau đó bị abort |
| `read_committed` | Không trả record từ các transaction đã abort; chỉ trả transactional output đã commit cùng các non-transactional record hợp lệ |

Ví dụ:

~~~text
Producer T1: begin
Producer T1: send output X
Producer T1: abort

Consumer read_uncommitted: có thể thấy X
Consumer read_committed: không thấy X
~~~

Nếu downstream vẫn dùng `read_uncommitted`, nó có thể quan sát output từ transaction bị abort, làm mất ý nghĩa EOS ở cấp độ kết quả downstream. Các consumer cần kết quả transactional nên dùng `read_committed`.

### 9.1. Last Stable Offset

Consumer `read_committed` không đọc vượt quá ranh giới được xác định bởi những transaction đang mở, thường được gọi là **Last Stable Offset (LSO)**. Nếu một transaction kéo dài hoặc bị treo, downstream có thể bị chậm nhận cả những record khác nằm sau nó trong partition.

Vì vậy, transaction dài không chỉ làm listener chậm; nó còn có thể tăng độ trễ nhìn thấy record ở consumer downstream. Cần theo dõi transaction duration, lag và tuổi record.

### 9.2. read_committed không có nghĩa topic toàn bộ là EOS

Một topic có thể nhận cả record từ transactional producer lẫn non-transactional producer. `read_committed` chỉ giúp xử lý visibility của Kafka transactions; nó không chứng minh mọi record được tạo bởi một workflow EOS hoặc mọi producer đều có logic đúng.

## 10. Cơ chế EOS V2 trong Spring Kafka

Các phiên bản Spring Kafka hiện đại sử dụng cơ chế EOS V2 của Kafka cho listener containers, dựa trên việc broker quản lý transactional producer và metadata consumer group để bảo đảm producer fencing và offset commit thích hợp. Các tài liệu/phiên bản cũ có thể nhắc đến mô hình EOS trước đây.

Những điểm vận hành cần nắm:

- Kafka transaction dùng `transactional.id` để nhận diện producer transactional.
- Broker sử dụng producer identity/epoch nhằm fence producer cũ khi một producer có cùng transactional ID thay thế.
- Consumer group metadata liên quan được dùng khi offset được gửi vào transaction.
- Container cần đồng bộ với vòng đời consumer group và rebalance để tránh một producer cũ tiếp tục commit kết quả không hợp lệ.
- API, yêu cầu tối thiểu của broker và tùy chọn EOS mode có thể khác giữa các phiên bản Spring Kafka.

Không sao chép cấu hình EOS mode từ bài viết cũ mà không kiểm tra phiên bản hiện tại. Trong các phiên bản mới, cấu hình cũ có thể đã được bỏ hoặc thay thế.

### 10.1. Transactional ID và fencing

Nếu hai producer đồng thời sử dụng cùng `transactional.id`, broker có thể fence producer cũ. Fencing là tính năng an toàn, tránh hai instance cùng cam kết transaction dưới một identity.

Ví dụ lỗi thường gặp:

~~~text
Pod A -> transactional.id = billing-tx-0
Pod B -> transactional.id = billing-tx-0
                         |
                         v
               Producer cũ bị fenced
                         |
                         v
             Transaction của Pod A thất bại
~~~

Giải pháp không phải tắt fencing, mà là thiết kế không gian ID đúng, quản lý producer cache và hiểu tình huống rolling deployment.

## 11. Quản lý transaction timeout và vòng đời producer

Kafka transactions có timeout do producer và broker quản lý. Nếu transaction kéo dài quá ngưỡng, broker có thể abort, và lần commit từ ứng dụng thất bại.

Các nguyên nhân phổ biến:

- Listener thực hiện I/O downstream chậm.
- Chờ HTTP timeout lâu trong cùng Kafka transaction.
- Batch xử lý quá nhiều record.
- Worker hoặc thread bị block.
- Broker/network bất ổn.
- Transactional producer không được dùng trong thời gian dài rồi gặp tình trạng transactional ID expiration hoặc lỗi liên quan cache.

### 11.1. Không kéo transaction qua công việc bất đồng bộ không kiểm soát

Một pattern nguy hiểm:

~~~java
@KafkaListener(topics = "orders.created")
public void listen(OrderCreated event) {
    executor.execute(() -> publishOutput(event));
    // Listener trả về trước khi worker gửi output.
}
~~~

Khi listener trả về, container có thể xem công việc đã hoàn tất và commit input offset. Worker chạy sau đó không nhất thiết còn nằm trong Kafka transaction của consumer thread. Kết quả có thể mất tính atomic.

Nếu muốn song song hóa, cần thiết kế transaction boundaries riêng, đồng bộ kết quả của các task trước commit hoặc chọn mô hình khác có kiểm soát. Không giả định Kafka transaction context tự lan qua thread pool.

### 11.2. Producer cache và maxAge

Spring Kafka có thể cache transactional producers. Với môi trường mà producer ít được sử dụng, một producer cache lâu có thể gặp sự cố liên quan trạng thái transactional ID ở broker. Các phiên bản Spring Kafka hỗ trợ thuộc tính `maxAge` trên `DefaultKafkaProducerFactory` để làm mới transactional producer trước khi nó trở nên quá cũ.

Không tăng hay giảm tùy tiện. Hãy đối chiếu phiên bản Spring Kafka, broker-side transactional ID expiration, tần suất xử lý, transaction timeout và producer cache metrics.

## 12. Consumer group rebalance khi dùng EOS

Khi scale out, scale in, rolling deploy hoặc consumer mất heartbeat, group rebalance có thể xảy ra. Partition chuyển chủ sở hữu, transaction đang xử lý có thể bị abort hoặc không thể commit như mong đợi.

Trong trường hợp đó:

1. Record chưa được xác nhận bằng committed Kafka transaction có thể được giao lại.
2. Output thuộc transaction đã abort không hiển thị với downstream `read_committed`.
3. Listener mới xử lý lại record và có thể tạo committed output hợp lệ.
4. Mọi side effect ngoài Kafka của lần xử lý cũ vẫn phải được bảo vệ bằng idempotency.

EOS không loại bỏ nhu cầu graceful shutdown hoặc điều chỉnh `max.poll.interval.ms`. Một listener kéo dài quá khả năng của consumer group có thể kích hoạt rebalance và tạo abort/redelivery không cần thiết.

### 12.1. Scale out không đồng nghĩa tăng throughput vô hạn

Số consumer có thể xử lý song song bị giới hạn bởi số partition. Với transactional listeners, còn có chi phí bắt đầu/commit Kafka transaction, producer cache và coordination với broker. Tăng số replica vượt số partition có thể tạo member nhàn rỗi mà không tăng throughput.

## 13. Khi listener ném exception: rollback và recovery

Trong listener transactional, exception cần kích hoạt **rollback Kafka transaction**. Sau rollback, container và các thành phần xử lý sau rollback quyết định seek, retry hoặc recovery record.

Trong nhiều cấu hình transactional Spring Kafka, `DefaultAfterRollbackProcessor` đóng vai trò quan trọng để điều khiển record được giao lại sau rollback. Đừng áp dụng nguyên xi hướng dẫn cho `DefaultErrorHandler` của non-transactional container vào listener transactional mà không kiểm tra error-handling path.

~~~text
Listener xử lý input
         |
         +-- Thành công
         |      |
         |      v
         |  Output + input offset cùng commit
         |
         +-- Exception
                |
                v
           Abort transaction
                |
                v
         AfterRollbackProcessor
                |
           Retry / Seek / Recover
~~~

### 13.1. Lỗi retryable và non-retryable

Timeout tạm thời có thể cần retry hữu hạn với backoff. Payload sai schema hoặc vi phạm contract thường không tự sửa bằng retry. Policy nên phân loại:

| Nhóm lỗi | Hướng xử lý |
|---|---|
| Network timeout tạm thời | Retry có backoff và giới hạn |
| Broker transaction error | Rollback/khôi phục theo semantics của producer và container |
| Validation lỗi vĩnh viễn | Recovery/DLT theo policy, không retry vô ích |
| Schema/serialization lỗi trước listener | `ErrorHandlingDeserializer` và recovery phù hợp nếu cần |
| Lỗi database ngoài Kafka | Cần idempotency/đối soát, tránh giả định rollback Kafka cũng rollback DB |

## 14. DLT và recovery trong luồng transactional

Khi record cuối cùng không thể xử lý thành công, có thể ghi nó vào DLT để tiếp tục xử lý các record khác. Trong transactional setup, quá trình **publish DLT và xác nhận offset nguồn** cần được thiết kế cẩn thận để tránh mất record hoặc nhân đôi recovery ngoài ý muốn.

Một cách tiếp cận là cấu hình after-rollback recovery sử dụng transactional KafkaTemplate và commit offset của record đã recover trong **một Kafka transaction mới** phù hợp. Các tùy chọn như `commitRecovered` của `DefaultAfterRollbackProcessor` và transaction manager liên quan có semantics/version requirements riêng; cần kiểm tra cấu hình cụ thể.

### 14.1. Không ack nguồn khi DLT publish thất bại

Nếu gửi DLT không thành công nhưng offset nguồn lại được commit, record có thể bị mất khỏi luồng xử lý mà không còn bản lưu phục hồi. Do đó:

- Chờ hoặc quan sát kết quả publish DLT theo recoverer.
- Không nuốt exception của DLT producer.
- Bảo đảm record được retry/redeliver nếu recovery không lưu được.
- Theo dõi DLT send failures và transaction aborts.
- Kiểm thử broker DLT unavailable hoặc ACL không hợp lệ.

### 14.2. Non-blocking retry topic không kết hợp tùy ý với container transactions

Spring Kafka có các giới hạn tương thích giữa **non-blocking retry topics** và **container transactions**. Không mặc định rằng thêm `@RetryableTopic` vào transactional listener sẽ tạo EOS cho tất cả bước chuyển topic. Trong các dòng Spring Kafka phổ biến, non-blocking retries không được hỗ trợ với container transactions.

Khi cần Kafka-to-Kafka EOS, ưu tiên cơ chế rollback/retry phù hợp với transactional container và thiết kế DLT transactional. Nếu cần delayed retries kéo dài qua nhiều topic, phải đánh giá topology và atomicity riêng, không áp dụng nhãn EOS chỉ dựa vào annotation.

## 15. EOS và database: giới hạn quan trọng nhất

Giả sử listener thực hiện hai việc:

1. Ghi trạng thái đơn hàng vào PostgreSQL.
2. Ghi event `OrderProcessed` vào Kafka và commit input offset.

Kafka transaction có thể bao gồm bước 2 và offset, nhưng không tự bao gồm bước 1:

~~~text
             Kafka input
                 |
                 v
              Listener
             /        \
            v          v
       Database      Kafka output
       transaction   + input offset
            |          |
         COMMIT      Kafka txn commit
            |
    Có thể xảy ra crash ở giữa
~~~

Nếu database commit rồi Kafka transaction abort, input record có thể được đọc lại và database update chạy lại. Nếu Kafka transaction commit nhưng database không hoàn tất, downstream thấy output còn database chưa có trạng thái tương ứng.

Không có một transaction manager Spring đơn giản nào biến hai resource này thành một giao dịch XA phân tán thực sự chỉ bằng cách đặt `@Transactional` trên listener. Phối hợp commit giữa Kafka và database vẫn có cửa sổ thất bại.

### 15.1. Outbox pattern

Khi database là hệ thống nguồn của sự thật và cần publish event Kafka đáng tin cậy, **transactional outbox** thường là lựa chọn mạnh:

1. Trong một database transaction, cập nhật bảng nghiệp vụ.
2. Cùng transaction đó, ghi một row vào outbox table.
3. Commit database transaction.
4. Một outbox publisher hoặc CDC phát event từ outbox sang Kafka.
5. Đánh dấu hoặc dọn outbox theo chính sách an toàn.

~~~text
Business request
      |
      v
DB transaction:
   update orders
   insert outbox_event
      |
      v
DB COMMIT (atomic)
      |
      v
Outbox publisher / CDC
      |
      v
Kafka topic
~~~

Outbox giữ trạng thái nghiệp vụ và ý định publish trong một database transaction. Việc phát outbox sang Kafka có thể diễn ra at-least-once, vì vậy consumer vẫn cần idempotency.

### 15.2. Inbox/idempotent consumer

Khi Kafka consumer cập nhật database, một **inbox table** với event id duy nhất có thể ngăn xử lý trùng:

~~~sql
CREATE TABLE consumed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Trong cùng database transaction:

1. Insert event id; nếu đã tồn tại, nhận diện record đã xử lý.
2. Thực hiện cập nhật nghiệp vụ cho event mới.
3. Commit transaction.
4. Để consumer hoàn tất và commit Kafka offset theo cấu hình.

Nếu Kafka giao lại record sau database commit, event id giúp tránh update lần hai. `Exactly-once effect` ở database phụ thuộc transaction và ràng buộc idempotency ở database, không phụ thuộc duy nhất Kafka EOS.

## 16. HTTP API, thanh toán và tác động bên ngoài

Gọi API thanh toán, gửi email, phát push notification hoặc ghi file nằm ngoài Kafka transaction. Nếu listener gọi API trước khi Kafka transaction commit và Kafka transaction abort, record có thể được chạy lại.

Ví dụ:

~~~text
Consumer nhận PaymentRequested
          |
          v
HTTP payment API -> charge thành công
          |
          v
Kafka output send
          |
          X Kafka transaction abort
          |
          v
Record được xử lý lại
          |
          v
HTTP payment API được gọi lần nữa
~~~

Đối với API hỗ trợ **idempotency key**, hãy gửi key ổn định theo nghiệp vụ (ví dụ request ID) để các lần retry không tạo charge thứ hai. Với API không hỗ trợ idempotency, cần trạng thái request, đối soát và cách xử lý timeout không rõ kết quả.

Không dùng transactional ID của Kafka làm idempotency key nghiệp vụ. Transactional ID nhận diện producer, không phải một lệnh thanh toán.

## 17. Khác biệt giữa EOS và thứ tự xử lý

Kafka vẫn bảo đảm record trong một partition có thứ tự offset. Tuy nhiên, một hệ thống có nhiều partition hoặc xử lý bất đồng bộ có thể tạo side effects hoàn tất khác thứ tự nghiệp vụ.

EOS không tự giải quyết:

- Hai event cùng aggregate bị chia sang hai partition do key không ổn định.
- Worker executor xử lý song song rồi ghi side effect lệch thứ tự.
- Retry topic cho phép record mới vượt qua record cũ đang chờ retry.
- Hai service khác nhau cùng cập nhật một entity mà không có version check.

Nếu yêu cầu `OrderCreated` trước `OrderPaid`, hãy dùng key partition theo aggregate, xử lý tuần tự theo key hoặc kiểm tra version/sequence trong state store. Kafka EOS bảo vệ atomic output + offset trong một transaction; nó không thay thế state machine nghiệp vụ.

## 18. Transaction failure matrix

Một cách hiểu EOS tốt là xét các điểm crash cụ thể:

| Thời điểm sự cố | Kafka output | Offset input | Hành vi sau khi phục hồi |
|---|---|---|---|
| Trước khi bắt đầu transaction | Chưa gửi | Chưa commit | Record được đọc lại |
| Sau khi mở transaction, trước output | Chưa committed | Chưa commit | Transaction abort/timeout; đọc lại |
| Sau khi gửi output, trước commit transaction | Uncommitted/abort | Chưa commit | `read_committed` không thấy output abort; đọc lại |
| Khi commit transaction thất bại | Không thể mặc định committed | Không thể mặc định committed | Cần để client/container xử lý kết quả và tái khởi tạo khi cần |
| Sau khi transaction commit thành công | Output committed | Offset committed cùng transaction | Group tiến từ offset tiếp theo |
| Sau database commit, trước Kafka transaction commit | DB side effect đã có | Kafka có thể chưa commit | Kafka redelivery; DB phải idempotent |
| Producer bị fenced | Transaction hiện hành không thể tiếp tục commit | Offset không được commit bởi transaction lỗi | Container cần xử lý fatal fencing và khôi phục ownership |

Không cố “tự sửa” một commit failure bằng cách gọi một send hoặc commit ngoài transaction đang lỗi mà không hiểu trạng thái producer. Điều đó có thể làm mất atomicity.

## 19. Monitoring cho transactional Spring Kafka

Metrics hữu ích phải cho biết cả **tiến độ xử lý** và **trạng thái transaction**.

| Metric/log | Mục đích |
|---|---|
| Kafka transaction begin/commit/abort rate | Đo tỷ lệ giao dịch thành công và thất bại |
| Transaction commit latency | Phát hiện broker/network chậm |
| Producer fencing errors | Phát hiện transactional ID collision hoặc producer thay thế |
| Producer send errors | Phát hiện record output không gửi được |
| Consumer lag/oldest record age | Phát hiện backlog và vi phạm SLA |
| Rebalance count/duration | Liên hệ abort với thay đổi group membership |
| Downstream read_committed lag | Phát hiện transaction kéo dài hoặc open transaction |
| After-rollback retry/recovery rate | Đo record bị giao lại |
| DLT publish failures | Phát hiện đường recovery không an toàn |
| Listener processing duration | Theo dõi thời gian transaction có thể kéo dài |

Không phải metric nào cũng được Spring Kafka xuất ra tự động với đúng tên bảng trên. Có thể cần Micrometer, Kafka client metrics, container events, log cấu trúc hoặc instrumentation riêng.

### 19.1. Alert nên có

- Transaction abort tăng kéo dài.
- `ProducerFencedException` hoặc transaction errors xuất hiện bất thường.
- Consumer lag tăng cùng listener processing time.
- Commit latency tăng mạnh.
- DLT/recovery publisher thất bại.
- Một pod restart/rebalance liên tục và tạo abort.
- Downstream `read_committed` không nhận record mới dù broker có uncommitted data.

Đặt ngưỡng theo baseline của workload; một lượng transaction abort nhỏ trong triển khai rolling update có thể chấp nhận, nhưng abort liên tục gây backlog cần điều tra.

## 20. Runbook: ProducerFencedException

Khi gặp producer fencing:

1. Xác định `transactional.id` hoặc prefix mà lỗi liên quan.
2. Kiểm tra có hai instance cùng dùng transactional ID không.
3. Kiểm tra rolling update, blue/green và số replica thực tế.
4. Kiểm tra producer cache và cách suffix được cấp trong mỗi process.
5. Xác định consumer group rebalance có xảy ra gần thời điểm lỗi không.
6. Không tiếp tục dùng producer đã bị fenced để commit transaction.
7. Khôi phục container/producer theo lifecycle được Spring Kafka hỗ trợ.
8. Xác nhận output downstream không trùng và offset tiến sau khi ứng dụng ổn định.

Fencing giúp bảo vệ tính đúng đắn; không nên tìm cách vô hiệu hóa fencing để bỏ qua lỗi. Sửa nguyên nhân ID collision hoặc sự phối hợp ownership mới là hướng xử lý.

## 21. Runbook: Input lag tăng nhưng output không xuất hiện

1. Kiểm tra input consumer group và partition assignment.
2. Kiểm tra listener có thực sự được gọi không.
3. Kiểm tra exception có làm Kafka transaction abort liên tục không.
4. Kiểm tra producer send timeout, broker transaction coordinator và ACL.
5. Kiểm tra downstream đang dùng `read_committed`, và có transaction dài/open transaction nào đang chặn LSO không.
6. Kiểm tra offset commit thực tế thay vì chỉ nhìn listener invocation count.
7. Kiểm tra sau-rollback processor và DLT routing nếu record là poison pill.
8. Đối soát input event id với output event id nếu contract hỗ trợ.

Không thay đổi `read_committed` sang `read_uncommitted` chỉ để “nhìn thấy output” trong production: việc đó có thể đưa output từ transaction đã abort vào xử lý downstream.

## 22. Runbook: Output trùng dù đã bật transactions

Một số câu hỏi cần xác định:

1. Các output trùng có phải từ hai **committed** Kafka transactions khác nhau không?
2. Có phải input ban đầu chứa hai event cùng business id?
3. Listener có gửi output qua KafkaTemplate dùng đúng transactional producer factory không?
4. Listener container có thực sự transactional, hay chỉ producer tự mở transaction?
5. Có service khác publish cùng loại output ngoài transactional flow không?
6. Downstream có dùng `read_committed` không?
7. Có manual replay hoặc DLT replay đã tạo event mới không?
8. Event id được giữ ổn định và consumer downstream có idempotency không?

EOS không deduplicate hai sự kiện **khác nhau nhưng có payload giống nhau** được producer gửi như hai business commands. Cần event id và deduplication nghiệp vụ nếu điều đó được yêu cầu.

## 23. Kiểm thử EOS trong môi trường tích hợp

Unit test chỉ mock KafkaTemplate không đủ để chứng minh atomic offset + output. Nên dùng broker test thực hoặc môi trường tích hợp (ví dụ Testcontainers) có transaction support.

### 23.1. Happy path: output và offset cùng commit

1. Tạo topic input và output.
2. Cấu hình transactional listener container, transactional KafkaTemplate.
3. Gửi một event input có event id.
4. Chờ listener xử lý thành công.
5. Xác nhận output có thể đọc bởi consumer `read_committed`.
6. Xác nhận consumer group offset input tiến qua record đó.
7. Restart consumer, xác nhận không tạo thêm output từ input đã commit.

### 23.2. Listener lỗi sau khi gửi output

1. Listener gửi output trong Kafka transaction.
2. Cố tình ném exception trước khi listener trả thành công.
3. Quan sát transaction abort.
4. Dùng consumer `read_committed` xác nhận không thấy output của transaction abort.
5. Xác nhận input chưa được commit bởi transaction thất bại.
6. Cho listener xử lý lại thành công và kiểm tra chỉ output committed được thấy.

### 23.3. Process crash trước commit

1. Dùng fault injection ở thời điểm sau khi output gửi nhưng trước commit transaction.
2. Dừng process hoặc làm transaction abort theo kịch bản test.
3. Khởi động lại consumer.
4. Xác nhận input được redeliver.
5. Xác nhận downstream `read_committed` chỉ thấy output hợp lệ sau commit.
6. Nếu listener có database side effect, xác nhận inbox/idempotency ngăn duplicate.

### 23.4. Producer fencing khi scale out

1. Tạo hai instance dùng cùng transactional ID trong môi trường test.
2. Kích hoạt tình huống producer thay thế/fencing.
3. Xác nhận một producer không thể commit transaction cũ.
4. Sửa ID strategy để hai instance có ID riêng.
5. Kiểm thử rolling deploy và rebalance.

### 23.5. DLT failure và recovery

1. Buộc listener ném exception non-retryable.
2. Kích hoạt after-rollback recovery theo policy.
3. Làm DLT producer gửi lỗi hoặc thiếu ACL.
4. Xác nhận input offset không bị xác nhận mất record.
5. Khôi phục DLT, xác nhận record được lưu an toàn.

### 23.6. Cần kiểm tra gì ngoài log?

Khi assert kết quả, cần kiểm tra:

- Transactional output thực sự đã commit hay abort.
- Offset consumer group thực tế.
- Dữ liệu nhìn thấy qua `read_committed`.
- Số side effect trong database nếu có.
- Event id và thứ tự business events.
- Error handling/fencing/recovery sau crash.

Chỉ log “Kafka transaction started” hoặc “listener invoked once” không đủ chứng minh EOS.

## 24. Những sai lầm thường gặp

**Chỉ bật producer idempotence rồi gọi là EOS.** Idempotence chưa gộp output và consumer offset vào một transaction.

**Chỉ bật `transaction-id-prefix` mà không kiểm tra listener container.** Custom factory có thể không nhận transaction manager, khiến offset vẫn commit riêng.

**Cho rằng `@Transactional` trên method tự bảo đảm DB + Kafka atomicity.** Hai resource không có distributed commit chỉ nhờ một annotation.

**Gọi KafkaTemplate từ worker thread sau khi listener trả về.** Worker có thể không tham gia transaction container; offset đã commit trước send.

**Nuốt send exception và cho listener trả thành công.** Có thể commit offset mà không có output mong muốn.

**Downstream dùng `read_uncommitted`.** Có thể nhìn thấy Kafka output từ transaction đã abort.

**Hai pod dùng cùng transactional ID.** Có thể gây fencing và abort liên tục.

**Transaction chạy quá lâu.** Có thể timeout, tăng lag và làm `read_committed` consumer chờ lâu.

**Dùng non-blocking retry topics tùy tiện với transactional container.** Cần xem giới hạn tương thích và thiết kế lại EOS/recovery đúng semantics.

**Quên idempotency cho HTTP, database, email.** Kafka transaction không rollback tác động bên ngoài.

**Cho rằng một event id được tạo mới sau replay vẫn là cùng event.** Deduplication nghiệp vụ cần ID ổn định.

## 25. Checklist triển khai EOS

### Phạm vi và hợp đồng

- [ ] Đã xác định mục tiêu là Kafka-to-Kafka read-process-write hay cần side effect ngoài Kafka.
- [ ] Đã mô tả rõ transaction bao gồm những topic/offset nào.
- [ ] Đã xác định luồng nào phải dùng `read_committed`.
- [ ] Đã thiết kế event id và idempotency khi có thể redelivery.

### Cấu hình Spring Kafka

- [ ] ProducerFactory có transaction support và transactional ID strategy không va chạm giữa instance.
- [ ] KafkaTransactionManager được tạo đúng và gắn vào listener container.
- [ ] KafkaTemplate sử dụng producer factory tham gia transaction tương ứng.
- [ ] Consumer auto commit tắt khi container quản lý offset.
- [ ] Ack mode, concurrency và partition assignment phù hợp workload.
- [ ] Transaction timeout và producer cache được quản lý theo phiên bản.

### Error handling

- [ ] Exception từ listener làm transaction abort thay vì bị nuốt.
- [ ] After-rollback retry/recovery đã được cấu hình đúng.
- [ ] DLT publish/offset recovery có đường xử lý an toàn.
- [ ] Không dùng retry topology không tương thích với container transactions.
- [ ] Fencing/rebalance được kiểm thử và có runbook.

### Hệ thống bên ngoài

- [ ] Database consumer có inbox/idempotent handler hoặc pattern tương đương.
- [ ] Khi DB là source of truth, đã cân nhắc transactional outbox.
- [ ] HTTP/API side effect dùng idempotency key hoặc đối soát.
- [ ] Không hứa EOS toàn end-to-end nếu có resource nằm ngoài Kafka transaction.

### Kiểm thử và quan sát

- [ ] Happy path kiểm tra offset cùng output commit.
- [ ] Crash trước commit được fault-inject và thử redelivery.
- [ ] Abort transaction không hiển thị output với `read_committed`.
- [ ] Đã thử producer fencing, transaction timeout, rebalance và DLT failure.
- [ ] Metrics/alert cho transaction abort, commit latency, lag và producer errors.
- [ ] Có hướng đối soát event id, committed offset và side effect nghiệp vụ.

## Kết luận

EOS trong Spring Kafka không phải lời hứa rằng Java listener chỉ được gọi một lần. Với **transactional listener container**, **transactional KafkaTemplate/ProducerFactory**, **Kafka transaction manager** và **downstream `read_committed`**, một luồng đọc Kafka rồi ghi Kafka có thể commit output và consumer offset nguyên tử. Khi transaction thất bại, output đã abort không trở thành committed output và input có thể được xử lý lại. Vì vậy, Kafka-to-Kafka EOS là cam kết về **kết quả đã commit**, không phải số lần thực thi hàm.

Để vận hành đáng tin cậy, cần quản lý transactional IDs, fencing, transaction timeout, producer cache, rebalance, after-rollback recovery và DLT. Nếu listener còn cập nhật database hoặc gọi HTTP API, Kafka transaction không bao trùm các side effect đó: hãy dùng inbox/idempotency, outbox hoặc workflow đối soát phù hợp. Kiểm thử crash ngay trước commit và quan sát thực tế bằng consumer `read_committed` cùng committed offsets là cách phân biệt một cấu hình có EOS thật với một cấu hình chỉ mang tên “transactional”.
