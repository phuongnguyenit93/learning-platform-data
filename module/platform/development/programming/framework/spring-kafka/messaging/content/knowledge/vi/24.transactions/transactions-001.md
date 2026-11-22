# Kafka transaction giải quyết vấn đề gì

Một luồng Kafka thường có nhiều bước: producer phát sự kiện, consumer đọc sự kiện, xử lý rồi phát kết quả sang topic khác. Nếu ứng dụng dừng giữa các bước, hệ thống có thể rơi vào trạng thái chỉ hoàn thành một phần: topic đầu ra đã nhận một record nhưng topic khác chưa nhận, hoặc output đã được ghi nhưng offset input chưa được xác nhận. Khi chạy lại, consumer có thể phát lại record và tạo kết quả trùng.

**Kafka transaction** giải quyết nhóm vấn đề nhất quán bên trong Kafka bằng cách gom nhiều thao tác ghi record và xác nhận offset thành một đơn vị commit nguyên tử. Các consumer dùng chế độ đọc phù hợp chỉ nhìn thấy toàn bộ kết quả đã commit hoặc không nhìn thấy kết quả của transaction bị abort.

Bài học thuộc chương **Transactions** của module **SPRING_KAFKA_MESSAGING**, tập trung vào lý do Kafka cần transaction, phạm vi bảo đảm của transaction, cách transaction phối hợp producer/consumer và những giới hạn cần hiểu trước khi dùng Spring Kafka transaction trong hệ thống thực tế.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Nhận diện partial write và duplicate processing trong luồng Kafka.
- Giải thích Kafka transaction bảo đảm atomicity giữa nhiều record, partition và topic như thế nào.
- Phân biệt idempotent producer với transactional producer.
- Mô tả consume-transform-produce và việc commit offset input trong cùng transaction với output.
- Hiểu vai trò của `transactional.id`, transaction coordinator và producer fencing.
- Giải thích vì sao consumer cần `isolation.level=read_committed` để chỉ đọc dữ liệu đã commit.
- Cấu hình transaction trong Spring Kafka bằng transaction-capable ProducerFactory và KafkaTemplate.
- Hiểu transaction của listener container và cách offset được đưa vào transaction.
- Nhận biết transaction Kafka không tự bao phủ database, HTTP, email hoặc hệ thống bên ngoài.
- Chọn outbox, inbox và idempotency khi cần phối hợp Kafka với hệ thống khác.

## 1. Vấn đề đầu tiên: một nghiệp vụ có nhiều lần publish

Giả sử Order Service nhận yêu cầu tạo đơn hàng. Nó cần phát hai sự kiện:

1. `orders.created` để Fulfillment xử lý đơn.
2. `orders.audit` để Audit lưu lịch sử.

Nếu hai lần gửi độc lập, tình huống sau có thể xảy ra:

~~~text
Order Service
    |
    +---- send orders.created ----> SUCCESS
    |
    +---- send orders.audit ------> FAIL
                                      |
                                      v
                               Partial publication
~~~

Một topic đã có record, topic còn lại chưa có. Hệ thống downstream nhìn thấy trạng thái không đầy đủ. Nếu ứng dụng thử gửi lại cả hai record, `orders.created` có thể bị phát trùng.

Vấn đề không chỉ là producer có nhận được acknowledgement hay không. Ứng dụng cần một cách để nói với Kafka rằng các record này thuộc cùng một đơn vị công việc: hoặc tất cả được commit, hoặc transaction bị hủy.

## 2. Vấn đề thứ hai: consume rồi produce có thể tạo trạng thái lệch

Một consumer thường đọc sự kiện đầu vào, xử lý rồi phát sự kiện đầu ra.

Ví dụ:

~~~text
orders.created
      |
      v
Fulfillment Consumer
      |
      +---- publish orders.accepted
      |
      +---- commit offset orders.created
~~~

Nếu output được publish thành công nhưng process dừng trước khi commit offset input, khi khởi động lại consumer đọc lại sự kiện cũ và có thể publish `orders.accepted` lần nữa.

Nếu commit offset trước khi publish output, tình huống ngược lại có thể xảy ra: offset đã tiến lên nhưng output chưa được ghi. Khi process dừng, input record không được giao lại, trong khi output bị thiếu.

Hai thao tác cần được phối hợp:

- Ghi các output record.
- Xác nhận offset của input record đã xử lý.

Kafka transaction cho phép đưa cả hai vào cùng transaction Kafka. Khi transaction commit, output và offset cùng có hiệu lực; khi transaction abort, cả output lẫn offset thuộc transaction đó đều không được coi là đã commit.

## 3. Kafka transaction bảo đảm điều gì?

Kafka transaction cung cấp atomicity cho các thao tác Kafka nằm trong cùng transaction. Một transaction có thể ghi nhiều record lên nhiều partition, nhiều topic và có thể bao gồm offset của consumer group.

| Tình huống | Không có transaction | Có Kafka transaction |
|---|---|---|
| Ghi hai topic | Topic thứ nhất có thể thành công, topic thứ hai thất bại | Hai nhóm record cùng commit hoặc cùng abort. |
| Consumer đọc rồi phát output | Output có thể được ghi nhưng input offset chưa commit | Output và input offset có thể được commit nguyên tử. |
| Process dừng trước commit | Có thể để lại output đã ghi một phần | Transaction chưa commit bị abort/không được công bố cho consumer đọc committed. |
| Consumer đọc dữ liệu transaction bị abort | Consumer đọc không giới hạn có thể thấy record chưa commit | Consumer `read_committed` bỏ qua record thuộc transaction bị abort. |

Transaction không có nghĩa mọi thứ trong ứng dụng đều trở thành một transaction ACID toàn cục. Phạm vi nguyên tử ở đây là các thao tác Kafka được đưa vào transaction.

## 4. Atomicity trên nhiều topic và partition

Một producer transactional có thể gửi nhiều record trong cùng transaction, kể cả record thuộc các topic hoặc partition khác nhau.

~~~mermaid
flowchart TD
    A[Begin Kafka transaction] --> B[Send record A]
    B --> C[Send record B]
    C --> D[Send record C]
    D --> E{All operations succeed?}
    E -->|Yes| F[Commit transaction]
    E -->|No| G[Abort transaction]
    F --> H[read_committed consumers see all committed records]
    G --> I[read_committed consumers see none of the aborted records]
~~~

Ví dụ transaction ghi:

- Một record vào `orders.accepted-0`.
- Một record vào `orders.audit-2`.
- Một record vào `inventory.reservation-requested-1`.

Các record này có thể được ghi vào nhiều partition. Consumer dùng `read_committed` chỉ đọc các record thuộc transaction sau khi transaction commit.

Kafka không tạo một thứ tự toàn cục giữa các partition. Transaction bảo đảm tính nguyên tử về khả năng nhìn thấy các record, không tạo một log duy nhất hay một thứ tự tổng thể giữa chúng.

## 5. Idempotent producer và transaction khác nhau thế nào?

Idempotent producer và transaction có liên quan nhưng giải quyết hai vấn đề khác nhau.

| Cơ chế | Giải quyết | Không tự giải quyết |
|---|---|---|
| Producer acknowledgement | Producer biết broker đã nhận request theo mức acknowledgement cấu hình | Atomicity giữa nhiều lần gửi. |
| Idempotent producer | Ngăn bản sao do producer retry cùng request trong một producer session theo protocol Kafka | Duplicate do ứng dụng chủ động gửi lại cùng nghiệp vụ hoặc từ process khác. |
| Kafka transaction | Commit/abort nguyên tử nhiều record và có thể gồm offset input | Side effect ở database hoặc HTTP ngoài Kafka. |
| Consumer idempotency | Ngăn xử lý nghiệp vụ trùng theo event ID | Không thay thế transaction Kafka khi cần atomic output + offset. |

Idempotent producer bảo vệ việc retry ở tầng protocol bằng producer ID và sequence number. Transaction mở rộng phạm vi sang nhiều thao tác ghi và commit/abort.

Khi bật transaction trong Kafka producer, idempotence được bật theo yêu cầu của transactional producer. Không nên xem hai khái niệm này là một: idempotence xử lý duplicate do retry gửi, còn transaction xử lý atomicity giữa nhiều thao tác Kafka.

## 6. Producer transaction hoạt động như thế nào?

Một transactional producer có định danh `transactional.id`. Producer đăng ký với transaction coordinator, bắt đầu transaction, ghi record, rồi commit hoặc abort.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Producer as Transactional Producer
    participant TC as Transaction Coordinator
    participant Broker as Partition Leaders
    App->>Producer: beginTransaction
    Producer->>TC: Find/initialize transaction
    App->>Producer: send record A
    Producer->>Broker: Write A (transactional)
    App->>Producer: send record B
    Producer->>Broker: Write B (transactional)
    App->>Producer: commitTransaction
    Producer->>TC: End transaction: COMMIT
    TC-->>Producer: Commit result
~~~

Kafka dùng transaction marker để xác định trạng thái commit hoặc abort trong các partition liên quan. Consumer `read_committed` dựa vào trạng thái transaction để quyết định record nào được phép trả về ứng dụng.

Nếu ứng dụng gặp lỗi trước commit, nó có thể abort transaction. Nếu process mất kết nối hoặc dừng bất ngờ, Kafka transaction coordinator xử lý trạng thái transaction theo protocol và timeout đã cấu hình.

## 7. `transactional.id` và producer fencing

`transactional.id` nhận diện một transactional producer logic qua các lần khởi tạo. Nó cho phép Kafka nhận ra producer instance cũ đã bị thay thế và ngăn producer cũ tiếp tục ghi.

Nếu hai producer đồng thời sử dụng cùng một transactional ID, producer được khởi tạo sau có thể làm producer cũ bị **fence**. Producer cũ nhận lỗi như `ProducerFencedException` và không còn được phép tiếp tục transaction.

Quy tắc vận hành:

- Mỗi producer instance đang hoạt động đồng thời cần transactional ID duy nhất.
- Không gán cùng một transactional ID tĩnh cho mọi pod.
- Khi chạy nhiều replica, dùng prefix có tính duy nhất theo instance.
- Để Spring Kafka quản lý suffix cho các producer concurrent được tạo từ cùng factory.
- Xử lý fencing như dấu hiệu có instance khác đang sở hữu cùng transactional ID, không retry vô hạn trên producer đã bị fence.

Trong Spring Kafka, `transactionIdPrefix` thường được cấu hình ở ProducerFactory. Prefix cần duy nhất giữa các application instance chạy đồng thời; factory có thể bổ sung suffix cho producer được tạo bên trong instance.

## 8. Consumer chỉ đọc transaction đã commit

Kafka consumer có thuộc tính:

~~~properties
isolation.level=read_committed
~~~

Hai giá trị chính:

| Giá trị | Hành vi |
|---|---|
| `read_uncommitted` | Có thể trả về record thuộc transaction chưa commit hoặc đã abort. Đây là mặc định phổ biến của Kafka consumer. |
| `read_committed` | Chỉ trả về record không transactional hoặc record thuộc transaction đã commit; bỏ qua record thuộc transaction bị abort và chưa hoàn tất. |

Nếu ứng dụng dùng Kafka transaction để bảo đảm output chỉ xuất hiện khi toàn bộ transaction thành công, consumer downstream cần dùng `read_committed` để nhìn thấy đúng ranh giới commit đó.

Một transaction đang mở có thể ảnh hưởng tới Last Stable Offset (LSO). Consumer `read_committed` không đọc vượt qua LSO, vì các transaction trước đó trên partition có thể chưa hoàn tất. Transaction mở quá lâu vì vậy có thể làm tăng độ trễ nhìn thấy dữ liệu và consumer lag quan sát được.

## 9. Consume-transform-produce và offset trong cùng transaction

Đây là trường hợp Kafka transaction tạo ra bảo đảm quan trọng nhất cho pipeline xử lý:

1. Consumer đọc record input.
2. Ứng dụng chuyển đổi và gửi output record bằng transactional producer.
3. Offset tiếp theo của input partition được gửi vào cùng transaction.
4. Transaction commit.

Nếu commit thành công, output record và offset input cùng được công bố. Nếu transaction abort, offset input không được commit trong transaction đó và record có thể được đọc lại.

~~~mermaid
flowchart TD
    A[Consume input record] --> B[Transform]
    B --> C[Begin/participate in Kafka transaction]
    C --> D[Produce output records]
    D --> E[Send consumed offsets to transaction]
    E --> F{Commit transaction}
    F -->|Commit| G[Output visible + input offset advanced]
    F -->|Abort| H[Output aborted + input offset not advanced]
    H --> I[Input record can be redelivered]
~~~

Offset được commit vẫn là vị trí tiếp theo cần đọc cho từng partition. Ví dụ xử lý input offset 41 thì offset gửi vào transaction thường là 42.

Cơ chế này thường được gọi là exactly-once processing trong phạm vi Kafka consume-transform-produce. Nó không có nghĩa listener chỉ được gọi đúng một lần về mặt vật lý: listener có thể chạy lại sau abort hoặc crash. Điều được bảo đảm là output transactional và offset input có kết quả commit nhất quán đối với consumer đọc committed.

## 10. Spring Kafka: bật transactional producer

Với Spring Boot, có thể cấu hình transaction ID prefix:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${HOSTNAME:orders-service}-tx-
      acks: all
    consumer:
      properties:
        isolation.level: read_committed
~~~

Khi `spring.kafka.producer.transaction-id-prefix` được cấu hình, Spring Boot có thể tạo ProducerFactory hỗ trợ transaction và KafkaTransactionManager theo cơ chế auto-configuration của phiên bản Boot tương ứng.

Trong deployment nhiều replica, giá trị prefix phải khác nhau giữa các instance đang chạy đồng thời. Ví dụ trên dùng HOSTNAME làm thành phần định danh; trong Kubernetes, có thể dùng pod name hoặc instance ID duy nhất. Đừng để mọi pod cùng một prefix tĩnh.

Nếu tự cấu hình ProducerFactory, đặt transaction ID prefix trên factory. ProducerFactory sẽ quản lý producer transactional và suffix phù hợp cho các producer được tạo đồng thời.

## 11. Gửi nhiều record trong một transaction bằng KafkaTemplate

Khi chỉ cần gom nhiều lần publish thành một đơn vị nguyên tử, có thể dùng `KafkaTemplate.executeInTransaction`.

~~~java
public void publishOrderEvents(
        OrderCreatedEvent created,
        OrderAuditEvent audit) {

    kafkaTemplate.executeInTransaction(operations -> {
        operations.send(
                "orders.created",
                created.orderId(),
                created
        );

        operations.send(
                "orders.audit",
                audit.orderId(),
                audit
        );

        return null;
    });
}
~~~

Các lần gửi trong callback tham gia cùng transaction do `executeInTransaction` quản lý. Nếu callback hoàn tất và transaction commit thành công, cả hai record được công bố. Nếu callback ném exception, transaction bị abort.

Để dùng API này, KafkaTemplate phải được tạo từ ProducerFactory có cấu hình transaction. Nếu ProducerFactory không hỗ trợ transaction, thao tác sẽ thất bại khi cố mở transaction.

Không gọi một thao tác gửi ngoài callback rồi cho rằng nó tự tham gia transaction. Hãy dùng đúng KafkaTemplate/operations gắn với transaction đang hoạt động.

## 12. Spring Kafka transactional listener container

Với mô hình consume-transform-produce, listener container có thể bắt đầu Kafka transaction trước khi gọi listener. Các record được gửi bằng KafkaTemplate tham gia transaction đang gắn với consumer thread. Khi listener hoàn tất, container gửi offset đã xử lý vào transaction rồi commit.

Cấu hình khái quát:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
transactionalListenerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        KafkaTransactionManager<String, Object> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);

    // Gắn Kafka transaction manager vào listener container.
    // API setter cụ thể phụ thuộc phiên bản Spring Kafka.
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);

    return factory;
}
~~~

Listener có thể gửi output:

~~~java
@KafkaListener(
        topics = "orders.created",
        groupId = "orders-fulfillment",
        containerFactory = "transactionalListenerFactory"
)
public void process(OrderCreatedEvent event) {
    OrderAcceptedEvent output = fulfillmentService.accept(event);

    kafkaTemplate.send(
            "orders.accepted",
            event.orderId(),
            output
    );
}
~~~

Khi container được cấu hình transactional đúng cách, output gửi từ listener tham gia transaction của container. Offset input được đưa vào transaction khi listener xử lý thành công.

Nếu listener ném exception, transaction rollback. Spring Kafka dùng cơ chế after-rollback để redeliver hoặc recover record theo cấu hình. Với transactional listener, không áp dụng máy móc ví dụ DefaultErrorHandler non-transactional; cần cấu hình DefaultAfterRollbackProcessor phù hợp.

Tên API cấu hình transaction manager trên ContainerProperties có thể thay đổi theo phiên bản Spring Kafka. Hãy dùng setter tương thích với dependency của dự án và kiểm tra rằng KafkaTemplate cùng ProducerFactory tham gia đúng transaction.

## 13. Exactly-once có nghĩa là gì trong Kafka?

Exactly-once thường được dùng để mô tả pipeline consume-transform-produce có output và offset input được commit nguyên tử.

Ví dụ consumer đọc `orders.created`, tạo `orders.accepted` và commit offset input trong cùng transaction. Downstream dùng `read_committed` chỉ thấy output của transaction đã commit.

Các tình huống:

| Thời điểm process gặp sự cố | Kết quả |
|---|---|
| Trước khi gửi output | Không có output transactional được commit; input chưa tiến offset. |
| Sau khi gửi output nhưng trước commit | Transaction abort hoặc không được commit; output không hiển thị với read_committed, input có thể được giao lại. |
| Sau khi transaction commit | Output hiển thị và offset input đã tiến cùng transaction. |
| Listener chạy lại sau rollback | Có thể được gọi lần nữa; transaction trước không tạo output đã commit. |

Exactly-once không loại bỏ mọi lần thực thi lặp. Nó bảo đảm kết quả Kafka đã commit không bị nhân đôi do quy trình consume-transform-produce được thiết kế và cấu hình đúng.

Các điều kiện quan trọng gồm transactional producer, việc gửi offset vào transaction, consumer đọc committed khi cần, cùng một transaction boundary rõ ràng và xử lý lỗi/rollback đúng cách.

## 14. Kafka transaction không bao phủ database

Giả sử listener đọc `orders.created`, cập nhật database rồi gửi `orders.accepted` trong Kafka transaction.

Nếu database commit thành công nhưng Kafka transaction abort, database đã thay đổi trong khi output Kafka không được commit. Kafka không thể tự rollback transaction database độc lập.

Ngược lại, nếu database transaction thất bại nhưng Kafka transaction vẫn được commit do hai transaction manager có ranh giới commit độc lập hoặc thứ tự hoàn tất không được phối hợp, hai hệ thống cũng có thể lệch trạng thái. Việc đặt hai annotation `@Transactional` hoặc hai transaction manager trong cùng phương thức không tự tạo ra một transaction phân tán nguyên tử.

| Tác động | Kafka transaction bao phủ? |
|---|---|
| Gửi nhiều Kafka record | Có |
| Gửi output record ở nhiều topic/partition | Có |
| Commit offset consumer group trong cùng Kafka transaction | Có |
| Ghi database quan hệ | Không tự động |
| Gọi HTTP service | Không |
| Gửi email hoặc SMS | Không |
| Ghi file hoặc object storage | Không |

Không nên gọi đây là exactly-once end-to-end khi nghiệp vụ có database hoặc dịch vụ bên ngoài. Cần dùng outbox/inbox, idempotency hoặc một giao thức phối hợp transaction phù hợp với hệ thống.

## 15. Transactional outbox và inbox giải quyết phần nào?

Nếu ứng dụng cần cập nhật database và phát event Kafka, transactional outbox là một lựa chọn phổ biến.

Trong cùng transaction database:

1. Cập nhật bảng nghiệp vụ.
2. Ghi một hàng vào bảng outbox.
3. Commit database transaction.

Một relay hoặc CDC connector đọc outbox rồi publish record sang Kafka. Nếu relay publish lặp, consumer downstream dùng event ID để idempotent.

~~~mermaid
flowchart TD
    A[Application command] --> B[Database transaction]
    B --> C[Update business tables]
    B --> D[Insert outbox row]
    C --> E[Commit DB]
    D --> E
    E --> F[Outbox relay / CDC]
    F --> G[Kafka topic]
    G --> H[Consumer with inbox/idempotency]
    H --> I[Database transaction]
~~~

Inbox pattern giúp consumer lưu event ID đã xử lý trong cùng transaction database với thay đổi nghiệp vụ. Khi record được giao lại, ứng dụng phát hiện event đã xử lý và không lặp side effect.

Outbox/inbox không thay thế Kafka transaction trong mọi trường hợp. Chúng giải quyết ranh giới giữa database và Kafka hoặc giữa các hệ thống có transaction manager độc lập.

## 16. Timeout và transaction mở quá lâu

Kafka transaction cần được hoàn tất trong giới hạn timeout. Một transaction kéo dài quá lâu có thể bị broker đánh dấu timeout và abort.

Các cấu hình đáng chú ý:

- `transaction.timeout.ms`: thời gian tối đa producer yêu cầu cho transaction.
- `transaction.max.timeout.ms`: giới hạn broker cho phép producer cấu hình transaction timeout.
- `max.block.ms`: thời gian producer có thể chờ trong một số thao tác block như lấy metadata hoặc buffer.
- Listener processing time: thời gian nghiệp vụ thực tế nằm trong transaction.

Cần giữ transaction ngắn và tránh đặt công việc chậm như gọi HTTP lâu, chờ người dùng hoặc batch quá lớn bên trong transaction. Transaction mở lâu làm giữ tài nguyên coordinator và có thể khiến consumer `read_committed` bị chặn ở LSO trên partition liên quan.

Đừng tăng transaction timeout để che giấu listener xử lý chậm mà không đo. Hãy theo dõi transaction duration, abort rate, commit latency và consumer lag.

## 17. Fencing, abort và lỗi transaction

Transactional producer có thể gặp các lỗi như:

- Producer bị fence vì transactional ID đã được instance khác sử dụng.
- Transaction timeout.
- Broker hoặc coordinator tạm thời không khả dụng.
- Commit response bị mất khiến trạng thái kết quả cần được xử lý theo protocol của client.
- Serialization hoặc send failure trong transaction.
- Listener exception khiến container rollback transaction.

Không phải mọi lỗi đều có thể retry bằng cách gọi commit lại. Với producer bị fence, instance hiện tại không còn quyền tiếp tục; cần xử lý lifecycle và transactional ID. Với lỗi tạm thời, Kafka client và Spring Kafka có cơ chế xử lý theo từng loại lỗi, nhưng ứng dụng vẫn cần logging và recovery rõ ràng.

Nếu transaction abort, record input chưa được xác nhận trong transaction đó có thể được giao lại. Listener phải an toàn khi chạy lại và tránh side effect bên ngoài không được transaction Kafka bảo vệ.

## 18. Khi nào nên dùng Kafka transaction?

| Nhu cầu | Có nên dùng Kafka transaction? | Lý do |
|---|---|---|
| Publish hai hoặc nhiều topic phải cùng xuất hiện | Có | Atomic multi-topic/multi-partition write. |
| Consume-transform-produce trong Kafka | Có | Gộp output và input offset vào cùng transaction. |
| Chỉ gửi một record đơn giản, không có yêu cầu atomicity | Có thể không cần | Idempotent producer và acknowledgement có thể đủ. |
| Cập nhật database rồi publish Kafka | Transaction Kafka một mình không đủ | Cần outbox hoặc cơ chế phối hợp DB/Kafka. |
| Gọi HTTP rồi commit Kafka offset | Transaction Kafka không bao phủ HTTP | Cần idempotency, retry và compensation phù hợp. |
| Gửi email/SMS từ listener | Transaction Kafka không thể rollback email đã gửi | Dùng event/command workflow và idempotency. |
| Consumer chỉ đọc và không phát output | Thường không cần transaction producer | AckMode/commit strategy có thể đáp ứng. |

Transaction có chi phí phối hợp và độ trễ so với publish thông thường. Dùng khi cần atomicity cụ thể, không bật chỉ vì muốn có từ khóa exactly-once trong cấu hình.

## 19. Kiểm thử Kafka transaction

Kiểm thử cần xác minh cả dữ liệu đã commit và dữ liệu bị abort.

| Kịch bản | Điều cần xác minh |
|---|---|
| Multi-topic commit | Consumer read_committed thấy đủ tất cả output. |
| Abort trước commit | Consumer read_committed không thấy output bị abort. |
| Consume-transform-produce success | Output và input offset cùng tiến. |
| Consume-transform-produce failure | Output không commit và input có thể redeliver. |
| Duplicate producer request | Idempotent producer không tạo duplicate do retry protocol. |
| Producer fencing | Instance cũ bị từ chối khi transactional ID bị chiếm. |
| Transaction timeout | Transaction quá thời gian bị abort theo cấu hình. |
| Read isolation | read_uncommitted và read_committed có kết quả đúng semantics. |
| Listener rollback | After-rollback processor redeliver/recover đúng. |
| External DB side effect | Test chứng minh Kafka transaction không rollback database độc lập. |

Có thể dùng EmbeddedKafka hoặc Testcontainers. Khi test transaction, tạo consumer với `isolation.level=read_committed` để xác minh dữ liệu đã commit; nếu cần so sánh, chạy thêm consumer `read_uncommitted`.

Để xác minh offset, dùng AdminClient đọc committed offsets của group và chờ bằng Awaitility hoặc latch có timeout. Không dựa vào Thread.sleep cố định. Khi test abort, cần đợi transaction hoàn tất hoặc timeout trước khi kết luận record không hiển thị.

## 20. Những lỗi thường gặp khi dùng transaction

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng cùng transactional ID cho nhiều pod | Producer cũ bị fence hoặc transaction xung đột | Prefix phải duy nhất theo instance đang chạy. |
| Consumer downstream dùng read_uncommitted | Có thể thấy record chưa commit hoặc đã abort | Dùng read_committed khi cần transaction visibility. |
| Nghĩ transaction bao phủ database | DB và Kafka có thể lệch trạng thái | Dùng outbox/inbox hoặc cơ chế phối hợp phù hợp. |
| Chỉ dùng idempotent producer nhưng kỳ vọng atomic nhiều topic | Một phần publish vẫn có thể thành công | Dùng transaction cho atomic multi-record writes. |
| Listener gửi output bằng producer không tham gia transaction | Output có thể commit độc lập với input offset | Dùng KafkaTemplate/ProducerFactory tham gia transaction của container. |
| Transaction mở quá lâu | Timeout, LSO bị giữ, tăng latency và lag | Giữ transaction ngắn, đo duration. |
| Retry side effect bên ngoài sau abort | HTTP/email/DB có thể bị thực hiện lặp | Dùng idempotency hoặc outbox/inbox. |
| Coi exactly-once là listener chỉ chạy một lần | Hiểu sai khả năng redelivery | Exactly-once áp dụng cho kết quả Kafka đã commit trong pipeline được cấu hình đúng. |
| Không xử lý fencing | Instance cũ tiếp tục thử thao tác transaction | Xử lý ProducerFencedException và lifecycle producer. |

## 21. Bài tập tổng hợp: atomic consume-transform-produce

Hãy xây dựng pipeline:

- Input topic: `orders.created`.
- Output topic: `orders.accepted`.
- Audit topic: `orders.audit`.
- Consumer group: `orders-fulfillment`.

Yêu cầu:

1. Bật transactional producer trong Spring Boot bằng transaction ID prefix duy nhất cho mỗi instance.
2. Cấu hình consumer `isolation.level=read_committed`.
3. Gửi hai output record vào `orders.accepted` và `orders.audit` trong một producer transaction.
4. Kiểm tra consumer read_committed thấy cả hai record sau commit.
5. Chủ động ném exception trước commit và xác minh cả hai output không hiển thị cho read_committed.
6. Cấu hình transactional listener container với KafkaTransactionManager.
7. Gửi output từ listener và xác minh offset input được commit cùng transaction.
8. Mô phỏng crash/rollback và xác minh input có thể được giao lại.
9. Khởi tạo hai producer dùng cùng transactional ID để quan sát fencing trong môi trường test.
10. Tạo transaction kéo dài để kiểm tra timeout và tác động LSO.
11. Thêm database side effect và chứng minh Kafka transaction không tự rollback DB.
12. Thiết kế outbox hoặc inbox để xử lý ranh giới DB/Kafka.
13. Viết integration test cho commit, abort, read_committed và offset.
14. Đo transaction duration, commit latency, abort rate và consumer lag.

Bài tập hoàn thành khi bạn chứng minh được output và offset input cùng commit/abort trong Kafka, giải thích được phạm vi exactly-once và chỉ ra cơ chế cần thiết khi nghiệp vụ có database hoặc dịch vụ bên ngoài.

## 22. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Failure model | Partial write và duplicate | Nêu được hai trạng thái lệch khi publish/commit riêng lẻ. |
| 2. Atomic writes | Multi-topic/partition transaction | Chứng minh được tất cả output cùng commit hoặc abort. |
| 3. Producer identity | transactional.id và fencing | Cấu hình ID duy nhất theo instance. |
| 4. Isolation | read_committed/read_uncommitted | Giải thích được dữ liệu nào consumer nhìn thấy. |
| 5. Consume-transform-produce | Output + input offset | Đưa offset vào cùng transaction với output. |
| 6. Spring Kafka | KafkaTemplate và KafkaTransactionManager | Cấu hình producer và listener container transactional. |
| 7. Exactly-once | Phạm vi bảo đảm trong Kafka | Phân biệt kết quả commit với số lần listener thực thi. |
| 8. External systems | Outbox, inbox, idempotency | Xử lý đúng ranh giới DB/Kafka và side effect. |
| 9. Operations | Timeout, fencing, LSO | Theo dõi transaction duration và lỗi. |
| 10. Testing | Commit, abort, offset, isolation | Kiểm thử được cả nhánh thành công và thất bại. |

Bài học hoàn thành khi bạn giải thích được Kafka transaction giải quyết partial write và lệch giữa output với input offset như thế nào, cấu hình được transactional producer/consumer trong Spring Kafka và xác định đúng giới hạn khi nghiệp vụ chạm tới database hoặc dịch vụ bên ngoài.

Kafka transaction cung cấp atomicity cho dữ liệu và offset nằm trong Kafka. Nó là nền tảng cho consume-transform-produce exactly-once, nhưng không biến toàn bộ hệ thống phân tán thành một transaction duy nhất. Muốn bảo đảm nghiệp vụ xuyên database và Kafka, cần thiết kế outbox/inbox, idempotency và recovery theo đúng ranh giới của từng hệ thống.

