# Transaction boundary của Kafka

Transaction boundary của Kafka là phạm vi các thao tác Kafka được xem như một đơn vị commit hoặc rollback. Khi transaction commit, các record được ghi trong transaction trở thành dữ liệu đã commit đối với consumer đọc ở chế độ phù hợp. Khi transaction abort, các record đó không được consumer **read_committed** nhìn thấy. Với luồng consume-transform-produce, Kafka còn có thể đưa offset của record đầu vào vào cùng transaction với các record đầu ra.

Điểm quan trọng là phải xác định chính xác ranh giới này bao trùm những gì. Kafka có thể bảo đảm tính nguyên tử cho record và offset nằm trong một Kafka transaction. Nó không tự động mở rộng ranh giới đó sang database, HTTP API, filesystem hoặc một Kafka cluster khác. Spring Kafka cung cấp các cơ chế để ứng dụng tạo và tham gia Kafka transaction, nhưng phạm vi bảo đảm vẫn phụ thuộc vào transaction manager và cách listener container được cấu hình.

## 1. Transaction boundary có nghĩa gì?

Một Kafka transaction có vòng đời cơ bản:

1. Producer khởi tạo hoặc lấy một transactional producer hợp lệ.
2. Producer bắt đầu transaction.
3. Producer gửi một hoặc nhiều record, có thể đến nhiều topic và partition.
4. Ứng dụng commit transaction nếu toàn bộ công việc thành công, hoặc abort nếu có lỗi.
5. Consumer dùng **isolation.level=read_committed** chỉ đọc những record thuộc transaction đã commit.

Ranh giới bắt đầu tại thao tác bắt đầu transaction và kết thúc tại commit hoặc abort. Những lệnh gửi nằm trong khoảng này thuộc cùng một đơn vị nguyên tử. Những lệnh gửi ngoài khoảng này không được gộp vào transaction chỉ vì chúng được gọi từ cùng một method Java hoặc cùng một request.

Ví dụ, một ứng dụng xử lý đơn hàng có thể phát hai sự kiện:

~~~
orders.created
orders.audit
~~~

Nếu hai lần gửi nằm trong cùng một Kafka transaction, Kafka có thể commit cả hai hoặc abort cả hai. Consumer đọc committed sẽ không nhận một nửa kết quả do transaction bị abort. Nếu ứng dụng gửi sự kiện thứ nhất trong transaction A rồi gửi sự kiện thứ hai trong transaction B, hai lần gửi có hai ranh giới độc lập và có thể có kết quả khác nhau.

Kafka transaction có thể bao phủ nhiều partition và nhiều topic trong cùng một Kafka cluster. Nó không tạo một transaction phân tán xuyên nhiều cluster. Việc đọc các partition khác nhau cũng không phải một snapshot toàn cục đồng thời: consumer có thể nhận record của từng partition ở các lần poll khác nhau, dù các record thuộc cùng transaction đã được commit.

## 2. Kafka bảo đảm điều gì bên trong transaction?

### 2.1. Ghi nguyên tử trên nhiều partition

Producer có thể gửi record đến nhiều partition và topic trong một transaction. Kafka ghi nhận trạng thái transaction thông qua transaction coordinator và các marker nội bộ. Sau khi transaction được commit, record được đánh dấu committed; sau khi abort, record được đánh dấu aborted.

Tính nguyên tử ở đây là tính nguyên tử về trạng thái transaction và khả năng quan sát của consumer tuân theo isolation level. Nó không tạo thứ tự tổng thể giữa các partition. Thứ tự record vẫn được bảo đảm trong từng partition theo thứ tự Kafka ghi nhận, còn các partition khác nhau không có một thứ tự toàn cục chung.

### 2.2. Đưa consumer offset vào transaction

Trong luồng xử lý consume-transform-produce, ứng dụng có thể đưa offset đã xử lý vào cùng transaction với record đầu ra bằng API **sendOffsetsToTransaction**.

Ví dụ về ý nghĩa của thao tác này:

~~~
Đọc record đầu vào ở offset 42
        |
        v
Tính toán kết quả
        |
        +---- Gửi event đầu ra
        |
        +---- Gửi offset tiếp theo (43) vào transaction
        |
        v
Commit transaction
~~~

Khi transaction commit, record đầu ra và offset đầu vào được commit cùng nhau. Nếu transaction abort, cả record đầu ra lẫn offset đó đều không được commit. Consumer group vì thế có thể đọc lại record đầu vào để xử lý lần nữa.

Khi dùng Kafka API trực tiếp, ứng dụng cần gửi offset cùng metadata của consumer group:

~~~java
producer.sendOffsetsToTransaction(
    offsetsToCommit,
    consumer.groupMetadata()
);
~~~

Không nên gọi **consumer.commitSync()** hoặc bật auto commit để thay thế cho thao tác này trong một luồng EOS. Làm như vậy sẽ tách việc commit offset ra khỏi Kafka transaction, khiến ranh giới nguyên tử bị phá vỡ.

### 2.3. Isolation level quyết định consumer nhìn thấy gì

Kafka consumer có hai chế độ đọc thường gặp:

| Isolation level | Hành vi |
|---|---|
| **read_uncommitted** | Có thể đọc record từ transaction đã commit và transaction đã abort. Đây là chế độ mặc định của Kafka consumer. |
| **read_committed** | Chỉ trả về record thuộc transaction đã commit và record không transactional. Record thuộc transaction bị abort sẽ bị bỏ qua. |

Consumer **read_committed** đọc đến **Last Stable Offset (LSO)** của partition. LSO là ranh giới mà tại đó các record phía trước đã có trạng thái transaction ổn định. Một transaction còn mở có thể khiến consumer **read_committed** phải chờ trước khi đọc các record phía sau nó trong cùng partition, ngay cả khi các record phía sau đã được producer khác gửi.

Vì vậy, nếu downstream cần dựa vào tính nguyên tử của Kafka transaction, cấu hình consumer ở **read_committed** là một phần của thiết kế. Chỉ cấu hình producer transactional là chưa đủ để mọi consumer đều có cùng góc nhìn.

## 3. Ba loại ranh giới thường gặp

### 3.1. Transaction chỉ ghi dữ liệu

Ứng dụng bắt đầu transaction, gửi nhiều record và commit. Transaction này bảo vệ các lần ghi Kafka thuộc nó.

~~~
beginTransaction
    send(topic-A)
    send(topic-B)
commitTransaction
~~~

Nếu commit thành công, consumer **read_committed** có thể đọc cả hai nhóm record. Nếu abort, consumer **read_committed** không nhận record nào trong transaction đó.

Transaction chỉ ghi dữ liệu không tự động bao gồm offset của một consumer. Nếu ứng dụng trước đó đã đọc message nhưng không đưa offset vào transaction, việc commit producer transaction không làm cho thao tác consume và produce trở thành một đơn vị nguyên tử.

### 3.2. Consume-transform-produce

Đây là ranh giới thường được nhắc đến khi nói về Kafka Exactly-Once Semantics (EOS):

~~~
Consumer đọc input
       |
       v
Ứng dụng xử lý input
       |
       v
Producer gửi output
       |
       v
Offset input + output records
       |
       v
Commit hoặc abort cùng transaction
~~~

Khi thành công, Kafka commit cả output và offset đã xử lý. Khi thất bại, Kafka abort output và giữ offset chưa commit để record đầu vào có thể được đọc lại. Cách này tránh tình huống offset đã tiến lên nhưng output chưa được ghi, hoặc output đã được commit nhưng offset vẫn chưa được commit trong cùng luồng Kafka.

Trong Spring Kafka, listener container có thể quản lý transaction này. Container bắt đầu Kafka transaction trước khi gọi listener, dùng **KafkaTemplate** để gửi output trong transaction đang hoạt động, rồi đưa offset đã xử lý vào transaction khi listener hoàn tất.

### 3.3. Transaction của một service publisher

Một service có thể dùng **@Transactional** với **KafkaTransactionManager** để gom các lệnh gửi Kafka trong một method vào một transaction:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publish(OrderCreated event) {
        kafkaTemplate.send("orders.created", event.orderId(), event);
        kafkaTemplate.send("orders.audit", event.orderId(), event);
    }
}
~~~

Method này tạo ranh giới cho các lần gửi Kafka tham gia vào transaction manager được chỉ định. Khi method kết thúc bình thường, transaction được commit; khi có exception khiến transaction rollback, các record trong transaction bị abort.

Ranh giới này không tự bao gồm offset của một consumer. Nếu service được gọi trong một listener không có Kafka transaction do container quản lý, annotation trên service không tự biến offset đầu vào thành một phần của transaction. Muốn có consume-transform-produce EOS, cần cấu hình transaction cho listener container hoặc tự quản lý offset bằng API Kafka phù hợp.

## 4. Transaction trong Spring Kafka

Spring Kafka tích hợp Kafka transaction qua **ProducerFactory**, **KafkaTemplate**, **KafkaTransactionManager** và listener container. Các thành phần cần dùng chung một **ProducerFactory** để **KafkaTemplate** tham gia đúng transaction đang hoạt động.

### 4.1. Bật transactional producer

Với Spring Boot, có thể cấu hình transaction ID prefix trong **application.yml**:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${spring.application.name:app}-${INSTANCE_ID:local}-
    consumer:
      properties:
        isolation.level: read_committed
~~~

Khi có transaction ID prefix, Spring Boot có thể tự cấu hình **KafkaTransactionManager** nếu ứng dụng chưa khai báo bean tương ứng. Nếu tự cấu hình **ProducerFactory**, hãy thiết lập transaction ID prefix trên **DefaultKafkaProducerFactory** hoặc cấu hình tương đương của phiên bản Spring Kafka đang dùng.

Prefix phải duy nhất cho mỗi instance ứng dụng đang chạy. Ví dụ, hai pod cùng dùng một prefix có thể tranh chấp cùng transactional ID. Broker sẽ fencing producer cũ khi một producer mới khởi tạo với cùng transactional ID; ứng dụng cũ có thể nhận **ProducerFencedException**. Trong môi trường nhiều replica, hãy đưa mã instance hoặc pod vào prefix.

Có thể khai báo transaction manager tường minh nếu ứng dụng cần kiểm soát bean:

~~~java
@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Không tạo một transaction manager với **ProducerFactory** khác với factory mà **KafkaTemplate** đang sử dụng. Nếu hai thành phần không chia sẻ factory, lệnh gửi có thể không tham gia transaction mà ứng dụng mong đợi.

### 4.2. Transaction ở listener container

Để mỗi lần xử lý của listener nằm trong một Kafka transaction, gắn **KafkaTransactionManager** vào listener container factory. Với các phiên bản Spring Kafka mới, cấu hình trọng tâm là:

~~~java
factory.getContainerProperties()
       .setKafkaAwareTransactionManager(kafkaTransactionManager);
~~~

Tên setter có thể khác ở các phiên bản Spring Kafka cũ; hãy dùng API tương ứng với phiên bản của dự án.

Listener có thể gửi event đầu ra như sau:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderCreated event) {
    BillingRequested result = createBillingRequest(event);
    kafkaTemplate.send("billing.requests", event.orderId(), result);
}
~~~

Khi container đã được cấu hình transactional:

1. Container bắt đầu Kafka transaction trước khi gọi listener.
2. **KafkaTemplate** dùng cùng **ProducerFactory** và tham gia transaction đang hoạt động.
3. Listener hoàn tất thành công; container gửi offset đã xử lý vào transaction.
4. Container commit transaction.

Với record listener, ranh giới thường tương ứng một lần xử lý record. Với batch listener, transaction bao trùm batch mà listener xử lý. Chi tiết về ack mode và hành vi container phụ thuộc cấu hình; cần bảo đảm container chịu trách nhiệm commit offset theo cơ chế transactional.

Nếu listener ném exception và exception được truyền về cơ chế rollback, transaction bị abort. Output Kafka bị abort và offset đầu vào chưa được commit, nên record có thể được đọc lại. Nếu listener bắt exception rồi kết thúc bình thường, container có thể xem lần xử lý là thành công và commit transaction. Khi muốn rollback, hãy để lỗi được truyền ra hoặc đánh dấu transaction rollback-only theo cách phù hợp.

### 4.3. Transaction ở method dùng **@Transactional**

**KafkaTransactionManager** có thể làm transaction manager cho một service:

~~~java
@Transactional(transactionManager = "kafkaTransactionManager")
public void publishEvents(OrderCreated event) {
    kafkaTemplate.send("orders.created", event.orderId(), event);
    kafkaTemplate.send("orders.audit", event.orderId(), toAudit(event));
}
~~~

Các lưu ý khi dùng annotation:

- Gọi method qua Spring proxy để transaction interceptor hoạt động. Lời gọi nội bộ trong cùng object (self-invocation) thường không đi qua proxy.
- Chỉ định rõ transaction manager khi ứng dụng có nhiều transaction manager, ví dụ một manager cho database và một manager cho Kafka.
- Các lệnh gửi phải dùng **KafkaTemplate** kết nối với **ProducerFactory** của transaction manager.
- Transaction của method publisher chỉ bao gồm các thao tác Kafka tham gia vào transaction đó; nó không tự đưa offset consumer hoặc thao tác database vào cùng Kafka transaction.

Trong listener đã có transaction do container quản lý, các thao tác gửi qua **KafkaTemplate** phù hợp sẽ tham gia transaction hiện tại. Tránh vô tình tạo một transaction độc lập bên trong bằng API mở transaction mới, vì khi đó các lần gửi có thể nằm ngoài ranh giới mà container dùng để commit offset.

### 4.4. **KafkaTransactionManager** quản lý phần nào?

**KafkaTransactionManager** quản lý transaction của producer. Nó không tự quản lý vòng đời consumer hoặc offset của mọi consumer trong ứng dụng. Listener container bổ sung phần tích hợp cần thiết: container theo dõi record đã xử lý và gửi offset vào transaction khi commit.

Do đó, hai trường hợp sau khác nhau:

| Cách cấu hình | Record đầu ra | Offset đầu vào |
|---|---|---|
| Service dùng **@Transactional** với Kafka transaction manager | Có thể nằm trong Kafka transaction | Không tự động nằm trong transaction |
| Listener container dùng Kafka transaction manager | Có thể nằm trong Kafka transaction | Container đưa offset đã xử lý vào cùng transaction |

Sự khác biệt này quyết định ứng dụng có đạt được consume-transform-produce EOS hay chỉ có transaction cho phần ghi dữ liệu.

## 5. Transaction trong Kafka và Exactly-Once Semantics

Exactly-Once Semantics của Kafka thường nói đến việc xử lý một record Kafka, tạo record đầu ra và commit offset đầu vào như một đơn vị nguyên tử. Mục tiêu là tránh để lần xử lý lại tạo ra một output Kafka đã được commit trùng với lần xử lý trước.

Để đạt được mục tiêu đó, luồng xử lý cần có các thành phần phù hợp:

1. Producer được cấu hình transactional và có transactional ID duy nhất cho instance.
2. Output records được gửi trong transaction.
3. Offset đầu vào được gửi vào chính transaction đó.
4. Consumer downstream đọc với **isolation.level=read_committed** nếu cần bỏ qua output đã abort.
5. Listener container hoặc code ứng dụng quản lý đúng ranh giới transaction và offset.

Kafka bật cơ chế idempotent producer khi dùng transactional producer. Idempotence giúp xử lý retry ở tầng producer để tránh ghi trùng do retry trong một producer session theo các điều kiện Kafka hỗ trợ. Transaction mở rộng khả năng này sang nhiều record và offset. Tuy nhiên, cả hai cơ chế đều không tự ngăn một nghiệp vụ bị thực hiện hai lần ở database hoặc HTTP service.

Ví dụ: listener đọc **OrderCreated**, gửi **BillingRequested** và đưa offset đầu vào vào transaction. Nếu ứng dụng gặp lỗi trước commit, transaction abort. Khi record **OrderCreated** được đọc lại, lần xử lý mới có thể gửi **BillingRequested** trong transaction mới. Consumer **read_committed** chỉ nhìn thấy output của transaction đã commit.

EOS có phạm vi cụ thể: các thao tác Kafka nằm trong transaction. Nó không có nghĩa toàn bộ hệ thống phân tán, mọi lần gọi service và mọi thay đổi dữ liệu đều được thực hiện đúng một lần.

## 6. Ranh giới Kafka không bao gồm database và dịch vụ bên ngoài

Một Kafka transaction không phải XA transaction và không tự tạo distributed two-phase commit giữa Kafka với database. **KafkaTransactionManager** và **DataSourceTransactionManager** quản lý hai tài nguyên khác nhau. Spring có thể đồng bộ vòng đời của các transaction này, nhưng việc đồng bộ đó không biến chúng thành một transaction nguyên tử có khả năng rollback đồng thời mọi tài nguyên trong mọi tình huống.

Xét tình huống một service vừa cập nhật database vừa gửi Kafka:

~~~
Database transaction                  Kafka transaction
        |                                     |
        +---- UPDATE orders                   |
        |                                     +---- SEND OrderUpdated
        |                                     |
        +---- COMMIT                          |
                                              +---- COMMIT
~~~

Nếu database commit thành công nhưng Kafka commit thất bại, database đã thay đổi trong khi event chưa được công bố. Ứng dụng không thể rollback một database transaction đã commit chỉ bằng cách abort Kafka transaction. Nếu đảo thứ tự commit, một lỗi ở tài nguyên còn lại vẫn có thể để lại trạng thái không đồng nhất theo chiều ngược lại.

Spring Kafka có thể tham gia transaction synchronization khi một transaction manager khác đang là transaction chính. Cơ chế này giúp phối hợp thứ tự commit và rollback trong các tình huống thông thường, nhưng vẫn có cửa sổ lỗi giữa các lần commit tài nguyên. Không nên mô tả nó như bảo đảm atomicity tuyệt đối giữa database và Kafka.

### 6.1. Dùng Transactional Outbox khi cần bảo đảm database và event

Khi yêu cầu nghiệp vụ là “cập nhật database thành công thì event chắc chắn có thể được phát”, Transactional Outbox thường là lựa chọn phù hợp:

1. Trong một database transaction, cập nhật dữ liệu nghiệp vụ và ghi một bản ghi vào bảng outbox.
2. Một relay hoặc CDC connector đọc outbox và publish event lên Kafka.
3. Sau khi publish, relay đánh dấu hoặc ghi nhận bản ghi đã được xử lý theo cơ chế của nó.
4. Consumer dùng event ID hoặc business key để xử lý idempotent.

Database transaction bảo đảm thay đổi nghiệp vụ và ý định phát event được lưu cùng nhau. Relay có thể publish lại nếu bị dừng sau khi publish nhưng trước khi ghi nhận đã xử lý, vì vậy phía nhận vẫn cần hỗ trợ duplicate. Dùng CDC, chẳng hạn Debezium, là một cách triển khai relay; một polling publisher cũng có thể được dùng.

Outbox không làm cho việc publish Kafka và cập nhật database thành một transaction chung. Nó biến yêu cầu thành một quy trình có thể phục hồi: event intent được lưu bền vững cùng dữ liệu, còn việc chuyển event sang Kafka được retry an toàn.

### 6.2. HTTP API và các side effect khác

Gọi HTTP API, gửi email, ghi file hoặc gọi một dịch vụ thanh toán không nằm trong Kafka transaction. Nếu listener gọi API thành công rồi Kafka transaction abort, record đầu vào có thể được đọc lại và API có thể bị gọi lần nữa.

Với side effect bên ngoài, cần thiết kế idempotency key, lưu trạng thái xử lý, dùng outbox/inbox hoặc áp dụng saga và hành động bù trừ khi phù hợp. Đừng giữ Kafka transaction mở trong lúc chờ một HTTP request dài nếu không có lý do rõ ràng: thời gian transaction kéo dài làm tăng nguy cơ timeout, retry và chặn tiến độ đọc committed ở partition liên quan.

## 7. Rollback, retry và Dead Letter Topic

Khi listener container đang chạy trong Kafka transaction và listener thất bại:

- Kafka transaction bị abort.
- Output records thuộc transaction bị abort và bị consumer **read_committed** bỏ qua.
- Offset đầu vào chưa được commit trong transaction.
- Container có thể seek hoặc để record được đọc lại theo cơ chế rollback và retry.

Spring Kafka cung cấp **DefaultAfterRollbackProcessor** để điều khiển hành vi sau rollback, ví dụ retry với backoff và phục hồi record lỗi. Khi đã vượt số lần retry, ứng dụng có thể publish record sang Dead Letter Topic (DLT). Nếu yêu cầu là việc đưa record vào DLT và commit offset gốc phải có cùng bảo đảm transactional, cần cấu hình recoverer và after-rollback processor theo chế độ transactional phù hợp với phiên bản Spring Kafka đang dùng.

Một số điểm cần quyết định rõ:

- **Retry vô hạn hay có giới hạn:** lỗi tạm thời có thể retry; lỗi dữ liệu không thể xử lý thường cần giới hạn số lần.
- **Backoff:** tránh retry liên tục gây tải lên broker hoặc dịch vụ phụ thuộc.
- **DLT:** xác định metadata cần giữ, chẳng hạn topic, partition, offset gốc, exception và thời điểm xử lý.
- **Commit offset sau recovery:** chỉ commit offset gốc khi record đã được phục hồi theo chính sách đã chọn, ví dụ đã publish thành công vào DLT.
- **Exception handling:** nếu listener nuốt exception rồi trả về bình thường, transaction có thể commit; cần phân biệt lỗi đã được xử lý thành công với lỗi cần rollback.

Không nên cho rằng “có DLT” tự động đồng nghĩa với không mất message. Kết quả phụ thuộc vào cách gửi DLT, transaction của lần phục hồi và thời điểm commit offset gốc.

## 8. Kích thước và thời lượng transaction

Transaction nên bao trùm đúng đơn vị công việc cần commit cùng nhau. Transaction quá nhỏ có thể làm tăng overhead; transaction quá lớn làm tăng thời gian giữ trạng thái mở và phạm vi rollback.

Một số yếu tố vận hành:

- **Transaction timeout:** transaction phải hoàn tất trong giới hạn **transaction.timeout.ms** của producer và giới hạn tối đa broker cho phép (**transaction.max.timeout.ms**). Giá trị producer yêu cầu cao hơn giới hạn broker sẽ không được chấp nhận.
- **Thời gian xử lý listener:** tránh chờ lâu cho HTTP, database hoặc thao tác bên ngoài trong lúc Kafka transaction đang mở.
- **Batch size:** batch lớn có thể tăng throughput nhưng làm tăng lượng công việc bị rollback cùng lúc và độ trễ hoàn tất transaction.
- **Producer cache:** Spring Kafka tái sử dụng transactional producer. Nếu có nhiều transaction đồng thời hoặc transaction lồng nhau, cần cấu hình cache và số suffix phù hợp để không thiếu producer.
- **Instance identity:** mỗi instance cần transaction ID prefix riêng để tránh fencing lẫn nhau.
- **Consumer visibility:** transaction mở lâu có thể giữ LSO ở phía sau và khiến consumer **read_committed** chờ.

Không nên tăng timeout để che một transaction bị treo hoặc listener xử lý quá lâu. Hãy tìm nguyên nhân khiến transaction không kết thúc đúng hạn trước khi thay đổi giới hạn.

## 9. Ví dụ theo dõi thành công và thất bại

Giả sử listener đọc **orders** ở partition 2, offset 42 và phát **billing.requests**.

### Trường hợp commit thành công

~~~
1. Container bắt đầu transaction T1
2. Listener đọc orders-2@42
3. KafkaTemplate gửi billing.requests
4. Container đưa offset 43 của orders-2 vào T1
5. T1 commit
~~~

Kết quả:

- Record **billing.requests** thuộc T1 được consumer **read_committed** nhìn thấy.
- Offset 43 được commit cho consumer group.
- Khi consumer khởi động lại, nó tiếp tục từ offset đã commit theo quy tắc của group.

### Trường hợp listener thất bại trước commit

~~~
1. Container bắt đầu transaction T2
2. Listener đọc orders-2@42
3. KafkaTemplate gửi billing.requests
4. Listener ném exception
5. T2 abort
6. Container xử lý rollback và đọc lại record theo chính sách retry
~~~

Kết quả:

- Record **billing.requests** trong T2 không được consumer **read_committed** nhìn thấy.
- Offset 43 không được commit trong T2.
- Record đầu vào có thể được xử lý lại.

Nếu listener đã cập nhật database hoặc gọi HTTP API trước khi ném exception, những side effect đó không tự rollback theo T2. Đây là lý do transaction boundary cần được vẽ qua từng tài nguyên, thay vì suy luận từ việc các thao tác nằm trong cùng một method.

## 10. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| **No transaction is in process** khi gửi qua **KafkaTemplate** | ProducerFactory có transaction nhưng lệnh gửi không chạy trong transaction, hoặc template không tham gia transaction đang hoạt động | Kiểm tra transaction manager, proxy, thread thực thi và ProducerFactory mà template sử dụng |
| **ProducerFencedException** | Hai producer instance dùng trùng transactional ID/prefix, hoặc producer cũ đã bị fencing | Tạo prefix duy nhất theo instance; kiểm tra vòng đời và việc khởi tạo producer |
| Consumer nhận record đã abort | Consumer đang dùng **read_uncommitted** | Đặt **isolation.level=read_committed** cho consumer cần bỏ qua aborted records |
| Output không nguyên tử với offset đầu vào | Listener container không được cấu hình transactional, hoặc offset được commit riêng | Kiểm tra Kafka transaction manager của container và cơ chế commit offset |
| Database đã đổi nhưng event không có | Database và Kafka có hai transaction độc lập; lỗi xảy ra giữa các lần commit | Xem xét Transactional Outbox và xử lý idempotent |
| Consumer **read_committed** bị chậm dù có record mới | Một transaction trước đó trong partition vẫn đang mở hoặc chưa có trạng thái ổn định | Kiểm tra transaction bị treo, timeout và producer sở hữu transaction |
| Record được xử lý lại sau rollback | Offset chưa được commit nên retry là hành vi dự kiến | Thiết kế handler và side effect có tính idempotent; xem lại retry/DLT policy |

## 11. Checklist thiết kế transaction boundary

Trước khi triển khai, hãy trả lời các câu hỏi sau:

1. Đơn vị công việc nào cần commit hoặc abort cùng nhau: một lần publish, một record listener hay một batch?
2. Transaction bao gồm những topic và partition nào? Chúng có thuộc cùng một Kafka cluster không?
3. Nếu có consume-transform-produce, offset đầu vào có được gửi vào cùng transaction với output không?
4. Consumer nào cần **read_committed** để chỉ nhìn thấy output đã commit?
5. **KafkaTemplate**, **KafkaTransactionManager** và listener container có dùng cùng **ProducerFactory** không?
6. Mỗi application instance có transaction ID prefix riêng không?
7. Điều gì xảy ra khi listener ném exception, retry hết số lần hoặc publish DLT thất bại?
8. Có thao tác database hoặc side effect bên ngoài nào nằm trong cùng method nhưng ngoài Kafka transaction không?
9. Nếu cần phối hợp database và Kafka, outbox/inbox hoặc saga có phù hợp hơn việc dựa vào transaction synchronization không?
10. Transaction có thời lượng và kích thước đủ nhỏ để tránh timeout và trì hoãn LSO không?

Một thiết kế tốt mô tả rõ điểm bắt đầu, điểm kết thúc, dữ liệu được commit cùng nhau và cách phục hồi khi commit thất bại. Trong Spring Kafka, việc chọn **KafkaTransactionManager** mới chỉ là một phần; cần cấu hình đúng listener container, offset handling và consumer isolation level để đạt được bảo đảm mong muốn.
