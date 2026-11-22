# Reader transactional queue

Trong Spring Batch, một ItemReader thông thường thường đọc dữ liệu từ file hoặc database. Khi chunk bị rollback, những nguồn này không tự động đưa item vừa đọc trở lại như một message queue. Spring Batch vì thế có cơ chế buffer item đã đọc để có thể dùng lại khi cần xử lý lại chunk.

Với một **transactional queue reader**, tình huống khác đi: việc nhận message tham gia transaction của queue. Nếu transaction rollback, broker có thể đưa các message đã nhận trở lại trạng thái sẵn sàng để consumer đọc lại. Khi đó Spring Batch không nên giữ một bản sao item trong buffer nội bộ, vì bản sao này có thể trùng với message mà queue sẽ redeliver.

Để khai báo hành vi này, Spring Batch cung cấp phương thức **readerIsTransactionalQueue()** trong cấu hình chunk Step. Cấu hình này báo cho framework rằng reader lấy dữ liệu từ một nguồn transactional có khả năng phát lại item khi rollback. Nó điều chỉnh cơ chế buffering của Spring Batch; bản thân lời gọi này không tạo transaction cho broker và không bảo đảm queue được cấu hình đúng.

## 1. Transactional queue reader là gì?

Một transactional queue reader đọc message từ queue trong một transaction. Message được xem là đã tiêu thụ thành công khi transaction commit. Nếu transaction rollback trước khi hoàn tất, message có thể được broker giao lại cho consumer.

Luồng xử lý cơ bản:

~~~text
Queue / Broker
     |
     v
ItemReader nhận message
     |
     v
ItemProcessor
     |
     v
ItemWriter ghi kết quả
     |
     v
Commit transaction
     |
     +--> Queue xác nhận message đã tiêu thụ
     +--> Dữ liệu đích được commit
~~~

Nếu một thao tác trong chunk thất bại:

~~~text
Queue / Broker
     |
     v
Reader nhận message A, B, C
     |
     v
Processor / Writer gặp lỗi
     |
     v
Rollback transaction
     |
     +--> Message chưa được xác nhận tiêu thụ
     |
     v
Broker có thể giao lại A, B, C
~~~

Khả năng redelivery là đặc điểm quan trọng của transactional queue. Nó cho phép một message chưa được xử lý thành công quay lại luồng xử lý sau rollback.

Không phải mọi queue đều có semantics giống nhau. JMS transacted session, RabbitMQ channel transacted/acknowledgement và các dịch vụ queue dựa trên visibility timeout có cơ chế khác nhau. Cần xác nhận adapter và transaction manager đang dùng thực sự hỗ trợ hành vi rollback/redelivery như thế nào.

## 2. Vì sao Spring Batch cần biết reader dùng transactional queue?

Với reader không transactional, Spring Batch thường buffer các item đã đọc trong chunk. Khi writer hoặc processor làm transaction rollback, framework có thể lấy lại item từ buffer thay vì yêu cầu reader đọc nguồn một lần nữa.

Điều này hữu ích với nguồn như file hoặc một số reader database. Đọc lại từ nguồn có thể không trả đúng item cũ nếu nguồn thay đổi, cursor đã tiến hoặc thao tác đọc không thể rollback.

Với transactional queue, queue tự chịu trách nhiệm phát lại message sau rollback. Nếu Spring Batch vẫn giữ item đã đọc trong buffer, hai luồng có thể tạo ra bản sao:

1. Chunk rollback, broker đưa message trở lại queue.
2. Spring Batch giữ item cũ trong buffer.
3. Lần xử lý tiếp theo dùng item trong buffer và commit.
4. Message vẫn còn trong queue vì lần nhận trước đã rollback.
5. Reader đọc message đó thêm lần nữa, dẫn đến xử lý trùng.

Vì vậy, với transactional queue reader, cần báo cho Spring Batch không buffer item đã đọc. Framework sẽ gọi reader lại sau rollback và queue sẽ cung cấp message được redeliver.

## 3. Cấu hình readerIsTransactionalQueue()

Trong Spring Batch 5, có thể bật chế độ transactional queue trên chunk Step:

~~~java
@Bean
public Step consumeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderMessage> queueReader,
        ItemProcessor<OrderMessage, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("consumeOrdersStep", jobRepository)
            .<OrderMessage, Order>chunk(20, transactionManager)
            .reader(queueReader)
            .readerIsTransactionalQueue()
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Trong ví dụ:

- Reader lấy message từ queue.
- Chunk size bằng 20, nên một chunk có thể chứa tối đa khoảng 20 message đã đọc thành công.
- readerIsTransactionalQueue() báo rằng reader sử dụng transactional queue.
- Nếu transaction rollback, framework không giữ các item đọc được trong buffer thông thường; reader được gọi lại và queue có thể giao lại message.

Trong cấu hình XML của các phiên bản Spring Batch hỗ trợ thuộc tính tương ứng, có thể khai báo reader-transactional-queue="true" trên phần tử chunk. Tên API Java/XML cụ thể phụ thuộc phiên bản; hãy dùng cấu hình tương ứng với version của dự án.

Điều quan trọng là gọi cấu hình này chỉ khi reader thực sự đọc từ một nguồn có semantics rollback/redelivery. Không bật cho file reader hoặc database reader thông thường chỉ vì muốn giảm bộ nhớ.

## 4. Cơ chế buffering mặc định và transactional queue

Có thể so sánh hai kiểu reader:

| Tình huống | Reader thông thường | Transactional queue reader |
| --- | --- | --- |
| Nguồn dữ liệu | File, cursor, truy vấn hoặc nguồn không rollback được | Queue có transaction nhận message |
| Khi chunk rollback | Spring Batch thường dùng item đã buffer để xử lý lại | Queue có thể redeliver message |
| Buffer item trong framework | Thường được dùng để tránh đọc lại nguồn | Tắt bằng readerIsTransactionalQueue() |
| Điều kiện quan trọng | Item đọc lại hoặc giữ trong buffer phải nhất quán | Queue receive phải tham gia transaction đúng cách |

Ví dụ chunk size bằng 3:

**Reader thông thường**

~~~text
Đọc A, B, C
    |
    v
Buffer A, B, C
    |
    v
Writer lỗi -> rollback
    |
    v
Framework dùng lại A, B, C từ buffer
~~~

**Transactional queue reader**

~~~text
Nhận A, B, C trong queue transaction
    |
    v
Writer lỗi -> rollback
    |
    v
Broker đưa A, B, C trở lại
    |
    v
Reader được gọi lại và nhận A, B, C
~~~

Nếu transactional queue reader vẫn dùng buffer nội bộ, item được xử lý lại từ buffer có thể tách khỏi trạng thái thực tế của queue. Đây là lý do cần cấu hình đúng.

## 5. Transaction của queue và transaction của database

Một chunk thường vừa nhận message từ queue vừa ghi dữ liệu vào database. Muốn việc nhận message và ghi kết quả có tính nguyên tử, hai thao tác cần tham gia cùng một transaction có khả năng phối hợp cả hai resource.

### Một transaction điều phối cả queue và database

Với transaction manager hỗ trợ phối hợp resource, chẳng hạn JTA/XA khi broker và database hỗ trợ XA, có thể thiết kế:

~~~text
Chunk transaction
    |
    +-- nhận message từ queue
    |
    +-- ghi dữ liệu vào database
    |
    +-- commit transaction chung
           |
           +--> Queue xác nhận message
           +--> Database commit dữ liệu
~~~

Nếu transaction chung rollback, cả việc nhận message và ghi database có thể được hoàn tác theo giao thức transaction mà các resource hỗ trợ. Đây là mô hình giúp tránh tình trạng message đã bị xác nhận nhưng dữ liệu đích chưa được commit.

### Hai transaction manager độc lập

Nếu queue và database dùng hai transaction manager độc lập, một rollback không tự động hoàn tác cả hai resource:

~~~text
JMS transaction              Database transaction
     |                              |
 nhận message                   ghi dữ liệu
     |                              |
 commit                          rollback
     |                              |
 message đã ack                không có dữ liệu
~~~

Trong tình huống này, message có thể đã bị xác nhận tiêu thụ nhưng dữ liệu nghiệp vụ không tồn tại. Chiều ngược lại cũng có thể xảy ra: database commit nhưng queue receive chưa được xác nhận, nên message được giao lại và có nguy cơ ghi trùng.

Chỉ truyền một PlatformTransactionManager vào Step không tự động phối hợp mọi resource. Cần hiểu transaction manager đó quản lý resource nào và cách queue client tham gia transaction.

Nếu không dùng XA/JTA, có thể thiết kế theo hướng at-least-once với xử lý idempotent, inbox table, unique message key hoặc outbox tùy luồng nghiệp vụ. Mục tiêu là bảo đảm message được xử lý ít nhất một lần mà việc nhận lại không tạo kết quả trùng.

## 6. Ví dụ với JMS và JmsTemplate

Một custom reader có thể dùng JmsTemplate để nhận message đồng bộ:

~~~java
public class JmsOrderReader implements ItemReader<OrderMessage> {

    private final JmsTemplate jmsTemplate;
    private final String destination;

    public JmsOrderReader(
            JmsTemplate jmsTemplate,
            String destination) {
        this.jmsTemplate = jmsTemplate;
        this.destination = destination;
    }

    @Override
    public OrderMessage read() {
        Message message = jmsTemplate.receive(destination);

        if (message == null) {
            return null;
        }

        return convert(message);
    }

    private OrderMessage convert(Message message) {
        // Chuyển JMS Message thành model của ứng dụng.
        // Phần triển khai phụ thuộc message format.
        throw new UnsupportedOperationException("Implement conversion");
    }
}
~~~

Đây là ví dụ khung về cách đọc đồng bộ. Phần chuyển đổi message phải được triển khai theo payload thực tế. Quan trọng hơn, JmsTemplate phải tham gia đúng JMS transaction đang được quản lý cho chunk. Cấu hình readerIsTransactionalQueue() không tự cấu hình JmsTemplate, ConnectionFactory hoặc acknowledgement mode.

Với JMS, có thể dùng JmsTransactionManager để quản lý local JMS transaction. Nếu chunk đồng thời ghi database, cần xác định transaction manager nào được dùng và database transaction được phối hợp ra sao. Nếu yêu cầu atomicity giữa nhận message và ghi database, cần một giải pháp phối hợp resource thích hợp hoặc thiết kế idempotency/compensation.

Không nên tự acknowledge message hoặc commit JMS session ngay trong reader trước khi writer hoàn tất. Nếu message bị xác nhận quá sớm, lỗi ở processor/writer không thể khiến queue redeliver message đó.

## 7. Empty queue và ý nghĩa của read() trả null

Trong Spring Batch, ItemReader trả null để báo không còn item trong input. Với một file hoặc truy vấn có phạm vi hữu hạn, điều này thường có nghĩa Step đã đọc hết dữ liệu.

Với queue, cần phân biệt:

- Queue đã được xử lý hết tại thời điểm hiện tại.
- Queue tạm thời chưa có message nhưng có thể nhận message mới sau đó.

Nếu reader dùng receive timeout và trả null khi hết thời gian chờ, Spring Batch có thể xem đó là end-of-input và kết thúc Step. Điều này phù hợp với một Job có mục tiêu drain queue đến khi queue tạm hết message. Nó không phù hợp với một consumer chạy liên tục chờ message mới mãi mãi.

Với quy trình liên tục, nên cân nhắc mô hình message-driven consumer hoặc một cơ chế polling/điều phối được thiết kế rõ. Không nên giả định một chunk Step thông thường sẽ tự chờ vô hạn sau khi reader trả null.

Khi xây dựng Job drain queue, cần định nghĩa rõ tiêu chí kết thúc: queue rỗng tại thời điểm kiểm tra, đạt một số lượng message, hết một khoảng thời gian, hoặc hoàn thành một batch ID cụ thể. Tiêu chí đó là quy tắc nghiệp vụ của Job.

## 8. Rollback và redelivery trong một chunk

Giả sử chunk size là 3 và queue đang có các message A, B, C, D, E:

~~~text
Queue ban đầu: [A, B, C, D, E]

Chunk 1:
  receive A
  receive B
  receive C
  process A, B, C
  write A, B, C
  commit

Queue sau commit: [D, E]

Chunk 2:
  receive D
  receive E
  writer lỗi
  rollback

Queue sau rollback có thể redeliver: [D, E]
~~~

Khi chunk 2 rollback, message D và E chưa được xác nhận tiêu thụ trong transaction queue. Lần đọc tiếp theo có thể nhận lại D và E. Message A, B, C đã commit trước đó không nên bị redeliver từ cùng transaction.

Nếu chunk có nhiều message và chỉ một item gây lỗi, rollback có thể làm tất cả message trong transaction của chunk được giao lại, không chỉ message lỗi. Vì vậy, retry hoặc skip ở một item có thể khiến các item khác trong chunk cũng được đọc lại tùy cách transaction và fault-tolerant processing hoạt động.

Processor và writer nên idempotent hoặc có cơ chế xử lý lại an toàn. Đừng giả định chỉ item lỗi mới được giao lại.

## 9. Skip và retry với transactional queue

Skip và retry có thể phối hợp với transactional queue, nhưng cần hiểu ảnh hưởng của rollback đến toàn bộ message đang nằm trong chunk.

### Retry

Nếu lỗi tạm thời xảy ra khi xử lý hoặc ghi, Spring Batch có thể rollback transaction và thử lại theo retry policy. Với transactional queue, message được broker redeliver khi reader được gọi lại. Cấu hình readerIsTransactionalQueue() giúp framework dựa vào redelivery thay vì buffer item cũ.

Ví dụ:

~~~java
return new StepBuilder("consumeOrdersStep", jobRepository)
        .<OrderMessage, Order>chunk(20, transactionManager)
        .reader(queueReader)
        .readerIsTransactionalQueue()
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Ví dụ minh họa retry lỗi database tạm thời. Cần xác nhận exception thực tế và transaction manager để bảo đảm queue receive được rollback và message được redeliver.

### Skip

Nếu message không hợp lệ vĩnh viễn, có thể skip exception dữ liệu:

~~~java
return new StepBuilder("consumeOrdersStep", jobRepository)
        .<OrderMessage, Order>chunk(20, transactionManager)
        .reader(queueReader)
        .readerIsTransactionalQueue()
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderMessageException.class)
        .skipLimit(100)
        .build();
~~~

Khi skip, Step cần hoàn tất transaction theo chính sách. Message lỗi phải được xác nhận tiêu thụ hoặc chuyển sang nơi xử lý lỗi theo thiết kế; nếu không, broker có thể tiếp tục redeliver message và tạo vòng lặp lỗi.

Nên dùng SkipListener hoặc cơ chế quarantine/dead-letter để lưu message lỗi và lý do. Nếu việc ghi rejected record nằm ở resource khác transaction queue, cần thiết kế để không xác nhận message trước khi thông tin lỗi được lưu bền vững.

## 10. Poison message và dead-letter queue

Poison message là message luôn gây lỗi khi xử lý, ví dụ payload sai định dạng, thiếu trường bắt buộc hoặc vi phạm quy tắc không thể phục hồi. Với transactional queue, nếu mỗi lần xử lý đều rollback, message có thể được redeliver liên tục.

~~~text
Queue
  |
  v
Nhận message lỗi
  |
  v
Processor ném exception
  |
  v
Rollback
  |
  v
Message redeliver
  |
  +---- lặp lại vô hạn nếu không có giới hạn
~~~

Để tránh vòng lặp:

- Phân loại lỗi dữ liệu không thể phục hồi.
- Giới hạn retry hoặc số lần delivery theo khả năng broker.
- Dùng SkipListener hoặc error handler để lưu thông tin lỗi.
- Chuyển message sang dead-letter queue (DLQ) hoặc quarantine khi đạt điều kiện.
- Giữ message ID, correlation ID, delivery count và nguyên nhân lỗi để điều tra.
- Có quy trình sửa và phát lại message sau khi dữ liệu được khắc phục.

Không nên chuyển message sang DLQ trước khi có bằng chứng rằng việc lưu message lỗi đã bền vững. Nếu thao tác ghi DLQ và xác nhận queue gốc không được phối hợp transaction, cần cơ chế idempotent hoặc đối soát để tránh mất message.

## 11. Khác biệt giữa JMS, RabbitMQ và queue visibility timeout

Khái niệm transactional queue có thể được triển khai khác nhau theo broker:

| Công nghệ | Cơ chế thường gặp | Điểm cần xác nhận |
| --- | --- | --- |
| JMS transacted session | Receive và acknowledge được quản lý bởi JMS transaction; rollback có thể redeliver | JmsTransactionManager/JTA có thực sự quản lý session của reader không |
| RabbitMQ | Manual acknowledgement; channel transaction hoặc acknowledgement sau xử lý tùy cấu hình | Message có được ack sau commit nghiệp vụ không; channel có được quản lý transaction đúng không |
| Queue dựa trên visibility timeout | Message tạm ẩn sau khi nhận; nếu không delete/ack trước hạn có thể xuất hiện lại | Visibility timeout, delete timing, lease extension và khả năng nhận trùng |

Không nên coi các cơ chế này là giống nhau. Ví dụ, visibility timeout không nhất thiết là transaction rollback của database. Một message có thể xuất hiện lại vì consumer chết hoặc lease hết hạn, kể cả khi không có lệnh rollback rõ ràng.

readerIsTransactionalQueue() chỉ điều chỉnh buffering của Spring Batch. Việc broker xác nhận, rollback, redelivery hoặc hết visibility timeout vẫn do client, adapter và transaction/acknowledgement configuration quyết định.

## 12. Chunk size và số message đang được giữ

Chunk size quyết định số message mà một transaction chunk có thể nhận trước khi commit. Chunk lớn có thể tăng throughput nhưng cũng làm số message đang ở trạng thái in-flight tăng và transaction kéo dài hơn.

Ví dụ:

| Chunk size | Hệ quả thường gặp |
| ---: | --- |
| 1 | Mỗi transaction xử lý một message; commit thường xuyên |
| 10 | Một transaction xử lý tối đa khoảng 10 message |
| 100 | Ít lần commit hơn nhưng nhiều message cùng rollback nếu chunk lỗi |
| 500 | Transaction dài và số message in-flight có thể lớn hơn |

Khi chọn chunk size, xem xét:

- Thời gian xử lý mỗi message.
- Độ trễ commit của queue và database.
- Số message có thể redeliver cùng lúc khi rollback.
- Memory của payload và object đã chuyển đổi.
- Prefetch/buffer của broker client.
- Khả năng chịu tải của writer và database.
- Retry/skip và chi phí xử lý lại.

Không chọn chunk size lớn chỉ để giảm số lần commit. Một chunk quá lớn có thể khiến nhiều message bị redeliver sau một lỗi đơn lẻ và làm tăng tải xử lý lại.

## 13. Checkpoint và trạng thái queue

Với file reader, Spring Batch thường lưu vị trí đọc vào ExecutionContext để restart tiếp tục từ checkpoint. Với transactional queue, broker thường giữ trạng thái message chưa được xác nhận và có thể redeliver khi transaction queue rollback.

Hai cơ chế này khác nhau:

- **ExecutionContext checkpoint:** trạng thái thực thi do reader/Step lưu trong JobRepository.
- **Queue delivery/ack state:** trạng thái message do broker và transaction/acknowledgement quản lý.

Không nên tự lưu một số offset trong ExecutionContext rồi cho rằng nó thay thế được transaction nhận message. Queue có thể có thứ tự, partition, consumer group hoặc redelivery semantics riêng.

Khi Job restart sau khi process chết:

- Message đã được commit/ack thường không còn trong queue của consumer đó.
- Message chưa được commit/ack có thể được redeliver theo broker.
- Message đã ghi vào database nhưng chưa được ack có thể xuất hiện lại và cần idempotency để tránh ghi trùng.
- Message đã ack nhưng database chưa commit có thể bị mất khỏi queue nếu hai resource không cùng transaction.

Vì vậy, cần thiết kế transaction boundary giữa queue, JobRepository và dữ liệu nghiệp vụ. JobRepository lưu trạng thái Job/Step, nhưng không tự quản lý acknowledgement của mọi broker.

## 14. Idempotency và xử lý message trùng

Transactional queue giúp redelivery khi rollback, nhưng không đồng nghĩa hệ thống bảo đảm exactly-once end-to-end. Message có thể được giao lại khi consumer mất kết nối, broker không nhận được acknowledgement hoặc tiến trình dừng ở thời điểm commit không xác định.

Một cách phổ biến là lưu message ID hoặc business key với unique constraint:

~~~java
public void process(OrderMessage message) {
    if (processedMessageRepository.existsByMessageId(
            message.getMessageId())) {
        return;
    }

    orderRepository.save(toOrder(message));
    processedMessageRepository.save(
            new ProcessedMessage(message.getMessageId()));
}
~~~

Ví dụ trên minh họa ý tưởng; hai thao tác kiểm tra và ghi phải được bảo vệ bởi transaction và unique constraint phù hợp để tránh race condition khi nhiều consumer xử lý cùng message.

Có thể dùng bảng inbox:

~~~text
inbox_message
---------------------------------
message_id (UNIQUE)
received_at
processed_at
status
error_code
~~~

Khi xử lý message, ứng dụng ghi nhận message ID và cập nhật dữ liệu nghiệp vụ trong cùng transaction database. Nếu message được giao lại, unique key giúp nhận ra message đã được xử lý.

Idempotency đặc biệt quan trọng với remote API, email, thanh toán hoặc message publish. Một transaction queue local không thể thu hồi side effect đã hoàn tất ở hệ thống khác.

## 15. Những lỗi thường gặp

### Bật readerIsTransactionalQueue cho reader không transactional

Framework không buffer item nữa, nhưng nguồn không bảo đảm redelivery. Sau rollback, item có thể bị mất hoặc reader tiến sang vị trí khác. Chỉ bật khi queue/client thực sự hỗ trợ rollback hoặc redelivery phù hợp.

### Nghĩ readerIsTransactionalQueue tạo transaction cho broker

Phương thức này chỉ báo hành vi buffering của Spring Batch. Cần cấu hình transaction manager, connection factory, session hoặc acknowledgement riêng.

### Queue commit độc lập với database commit

Message có thể bị ack trong khi database rollback hoặc ngược lại. Dùng XA/JTA nếu cần atomicity và resource hỗ trợ; nếu không, thiết kế at-least-once cùng idempotency/outbox/inbox.

### Ack message trước khi writer hoàn tất

Nếu message được xác nhận trước khi dữ liệu đích commit, lỗi writer có thể làm mất message. Ack phải được gắn với transaction hoặc chỉ thực hiện sau khi xử lý bền vững.

### Không xử lý poison message

Message lỗi có thể được redeliver vô hạn. Dùng retry limit, skip policy, DLQ và quy trình quarantine.

### Trả null khi queue tạm thời rỗng

Spring Batch hiểu null là hết input. Nếu Job cần chờ message mới, cần mô hình polling/consumer phù hợp thay vì kết thúc Step ngoài ý muốn.

### Cho rằng rollback chỉ redeliver item gây lỗi

Một transaction chunk có thể chứa nhiều message. Rollback có thể khiến toàn bộ message chưa được xác nhận trong chunk được giao lại.

### Không chống xử lý trùng

Redelivery có thể xảy ra sau crash hoặc trạng thái acknowledgement không xác định. Dùng message ID, business key, unique constraint và thao tác idempotent.

### Bỏ qua broker prefetch và in-flight limit

Broker có thể giao trước nhiều message hơn chunk hiện tại. Kiểm soát prefetch, concurrency và số message in-flight để tránh tăng memory hoặc làm broker quá tải.

## 16. Quy trình cấu hình transactional queue reader

Khi xây dựng Step đọc queue, hãy lần lượt xác định:

1. Broker và client đang dùng có transaction receive/ack hoặc cơ chế redelivery nào?
2. Reader thực sự tham gia transaction của chunk hay đang auto-ack?
3. Transaction manager được truyền vào Step quản lý JMS, AMQP, database hay JTA?
4. Queue receive và database write có cần atomicity trong cùng transaction không?
5. Nếu không có transaction chung, idempotency/inbox/outbox sẽ xử lý trường hợp commit lệch nhau ra sao?
6. Có cần gọi readerIsTransactionalQueue() để tắt buffering của Spring Batch không?
7. Queue rỗng có nghĩa kết thúc Job hay consumer phải tiếp tục chờ?
8. Retry, skip, redelivery count và DLQ được cấu hình thế nào?
9. Chunk size và broker prefetch có phù hợp với memory, throughput và số message in-flight không?
10. Reader, processor và writer có an toàn khi message được giao lại không?
11. Job restart có thể chạy lại message hoặc partition nào?
12. Log có lưu message ID, delivery count và Job/Step execution để đối soát không?

Nên kiểm thử ít nhất các tình huống: writer lỗi trước commit, database mất kết nối, broker mất kết nối, process bị dừng giữa chunk, message không hợp lệ, message bị giao lại và queue tạm thời rỗng. Quan sát cả dữ liệu database lẫn trạng thái message trên broker để xác nhận hành vi thực tế.

## Kết luận

readerIsTransactionalQueue() báo cho Spring Batch rằng reader lấy item từ một transactional queue có thể redeliver message khi chunk rollback. Khi bật, framework không buffer item đã đọc theo cách thông thường mà gọi reader lại để queue cung cấp message được giao lại. Cấu hình này chỉ đúng khi việc receive/ack thực sự tham gia transaction hoặc cơ chế redelivery của broker được thiết lập phù hợp. Cần phân biệt transaction queue với transaction database, xử lý empty queue đúng semantics của ItemReader, kiểm soát poison message và thiết kế idempotency để chịu được redelivery.
