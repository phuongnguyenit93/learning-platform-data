# Transactional reader

Trong Spring Batch, ItemReader lấy item từ nguồn dữ liệu để đưa vào chunk. Với nhiều nguồn như file hoặc truy vấn database, thao tác đọc không làm nguồn dữ liệu “tiêu thụ” item theo nghĩa message queue. Nếu chunk rollback, Spring Batch thường giữ các item đã đọc trong buffer để có thể xử lý lại mà không phải đọc lại nguồn.

Một **transactional reader** đọc từ resource mà thao tác nhận item tham gia transaction và có thể được hoàn tác. Ví dụ điển hình là reader nhận message từ một transactional queue. Khi chunk rollback, broker có thể redeliver message chưa được xác nhận. Trong trường hợp đó, Spring Batch cần biết reader có semantics transactional để tránh giữ bản sao item trong buffer nội bộ.

Trong fault tolerance, điều này quan trọng vì retry, skip và rollback có thể khiến chunk được thực hiện lại. Cách reader tương tác với transaction quyết định item nào được đọc lại, item nào được giữ trong bộ nhớ và liệu có nguy cơ xử lý trùng hoặc mất dữ liệu hay không.

## 1. Reader nằm trong transaction của chunk như thế nào?

Với chunk-oriented Step, Spring Batch xử lý một nhóm item trong transaction. Reader, processor và writer tham gia chu kỳ xử lý của chunk:

~~~text
Mở transaction chunk
       |
       v
ItemReader.read()
       |
       v
ItemProcessor.process()
       |
       v
ItemWriter.write()
       |
       v
Cập nhật trạng thái và checkpoint
       |
       v
Commit transaction
~~~

Nếu một thao tác làm chunk thất bại, transaction hiện tại có thể rollback theo transaction policy. Khi đó Spring Batch cần xử lý lại các item của chunk chưa commit.

Điểm cần phân biệt là **reader được gọi bên trong chu kỳ transaction của chunk** không đồng nghĩa **nguồn đọc có thể rollback việc nhận item**. Một câu SELECT thường không xóa hàng khỏi database. Một cursor file cũng không tự quay lại vị trí cũ chỉ vì transaction database rollback. Ngược lại, một message queue có thể giữ message ở trạng thái chưa xác nhận và giao lại sau rollback.

Vì thế, Spring Batch có cơ chế buffering để hỗ trợ reader không transactional và một cấu hình riêng cho reader transactional queue.

## 2. Reader không transactional và cơ chế buffering mặc định

Với nguồn đọc không thể rollback, Spring Batch cần giữ lại item đã đọc để khi chunk rollback, các item đó có thể được đưa qua processor và writer lần nữa.

Ví dụ reader đọc ba bản ghi A, B, C từ file:

~~~text
Reader đọc: A, B, C
       |
       v
Spring Batch giữ các item đã đọc
       |
       v
Processor / Writer xử lý
       |
       v
Writer lỗi -> rollback chunk
       |
       v
Framework dùng lại A, B, C đã buffer
~~~

Buffering giúp tránh phụ thuộc vào khả năng rewind của nguồn. Nếu framework gọi reader lại ngay, file reader có thể đã tiến đến dòng D, còn cursor hoặc nguồn dữ liệu khác có thể đã tiến đến vị trí tiếp theo. Khi đó A, B, C có nguy cơ bị bỏ qua.

Với reader không transactional, đây là hành vi cần thiết để bảo đảm các item của chunk chưa commit có thể được xử lý lại. Ứng dụng thường không cần cấu hình thêm để bật cơ chế buffering này.

Buffering cũng có giới hạn. Item đang nằm trong chunk cần được giữ trong bộ nhớ, và reader không được tự tạo side effect không thể lặp lại nếu framework có thể gọi lại thao tác trong các tình huống fault tolerant. Với chunk size lớn, số item được giữ lại có thể làm tăng memory usage.

## 3. Transactional reader có semantics khác

Một reader transactional nhận item từ resource tham gia cùng transaction. Khi transaction rollback, resource có thể khôi phục trạng thái nhận item để item được đọc lại.

Với queue transactional:

~~~text
Queue ban đầu: [A, B, C, D]
       |
       v
Transaction nhận A, B, C
       |
       v
Processor / Writer gặp lỗi
       |
       v
Rollback transaction
       |
       v
Broker có thể giao lại A, B, C
~~~

Queue là bên giữ trạng thái message chưa được xác nhận. Nếu Spring Batch đồng thời giữ bản sao A, B, C trong buffer, lần xử lý lại có thể dùng bản sao cũ rồi sau đó nhận lại chính các message đó từ queue. Điều này có thể tạo xử lý trùng.

Với transactional queue reader, Spring Batch cần bỏ buffering item thông thường để lần đọc tiếp theo lấy message được broker redeliver. Đó là lý do cấu hình chunk có tùy chọn readerIsTransactionalQueue().

Không phải mọi reader có transaction manager đều là transactional reader theo nghĩa này. Phải xác nhận thao tác nhận item thực sự có thể rollback và resource sẽ redeliver hoặc phục hồi item tương ứng.

## 4. Cấu hình readerIsTransactionalQueue()

Với Spring Batch 5, cấu hình reader transactional queue trên chunk Step bằng phương thức readerIsTransactionalQueue():

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

Trong ví dụ, reader lấy message từ queue và chunk có tối đa khoảng 20 message. Cấu hình transactional queue báo cho Spring Batch rằng nguồn đọc có khả năng phát lại item sau rollback, do đó framework không cần buffer item theo cách thông thường.

Phương thức này điều chỉnh hành vi buffering của Spring Batch. Nó không tự tạo transaction cho broker, không cấu hình acknowledgement mode và không phối hợp transaction giữa queue với database. Các thành phần đó phải được thiết lập riêng.

Chỉ bật cấu hình này khi reader thực sự có semantics transactional queue. Không bật cho file reader, JDBC reader thông thường hoặc API reader chỉ vì muốn framework đọc lại item sau rollback.

## 5. Chọn đúng cách xử lý theo loại nguồn

Không phải mọi nguồn đọc đều có cùng khả năng rollback:

| Nguồn | Hành vi đọc thường gặp | Cách nghĩ về rollback |
| --- | --- | --- |
| File | Reader tiến qua các dòng | Framework buffer item để chunk có thể xử lý lại |
| JDBC query/paging | Truy vấn lấy các hàng theo thứ tự | Database transaction không tự đưa một hàng SELECT trở lại như message |
| JDBC cursor | Cursor tiến qua result set | Cần hiểu connection, cursor và checkpoint; không giả định cursor rewind khi rollback |
| JMS transactional receive | Message được nhận trong JMS transaction | Rollback session/transaction có thể khiến message được redeliver |
| Queue có acknowledgement/visibility timeout | Message được giao và chờ xác nhận hoặc hết lease | Redelivery phụ thuộc broker, client và thời điểm ack/delete |
| API hoặc stream từ xa | Reader có thể tiêu thụ offset hoặc token | Cần cơ chế resume/replay riêng; không mặc định transaction database điều khiển nguồn |

Điểm quan trọng là phân biệt **transaction của Step** với **transaction của nguồn đọc**. Chúng chỉ phối hợp được khi resource và transaction manager được cấu hình đúng.

## 6. Reader database có tự động là transactional reader không?

Không nên kết luận như vậy chỉ vì reader dùng JDBC. Một truy vấn SELECT thông thường không tiêu thụ hàng theo cách queue nhận message. Khi transaction rollback, database không tự chuyển con trỏ ItemReader về item trước đó theo semantics của queue.

Với JDBC paging reader, mỗi trang được truy vấn theo sort key và reader có thể lưu trạng thái để restart. Với cursor reader, cursor có vòng đời và connection riêng; cấu hình connection, isolation và transaction cần được hiểu theo loại reader đang dùng.

Ví dụ paging reader:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select order_id, customer_code, total_amount")
            .fromClause("from orders")
            .whereClause("where business_date = :businessDate")
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .parameterValues(Map.of("businessDate", businessDate))
            .rowMapper(new OrderRowMapper())
            .pageSize(100)
            .saveState(true)
            .build();
}
~~~

Ví dụ minh họa reader có sort key ổn định và lưu state để restart. Reader này không phải transactional queue reader. Không gọi readerIsTransactionalQueue() cho nó chỉ vì truy vấn chạy trong transaction của chunk.

Với database reader, cần tập trung vào:

- Thứ tự đọc xác định bằng ORDER BY hoặc sort key.
- Điều kiện lọc ổn định trong suốt Job.
- Cơ chế checkpoint và saveState.
- Isolation level và khả năng dữ liệu nguồn thay đổi trong khi Job chạy.
- Connection/cursor lifecycle của implementation cụ thể.

## 7. Transaction manager phải quản lý đúng resource

Để thao tác nhận message có thể rollback, queue client phải tham gia transaction mà Step sử dụng. Nếu reader tự mở session độc lập hoặc tự acknowledge message trước khi chunk commit, rollback của Step không thể đưa message trở lại.

Ví dụ với JMS, một JmsTransactionManager có thể quản lý local JMS transaction. Nếu Step đồng thời ghi database bằng một DataSourceTransactionManager khác, hai transaction độc lập không tự động trở thành một transaction chung.

~~~text
JMS transaction                  Database transaction
      |                                  |
  receive message                    write row
      |                                  |
  commit / rollback                  commit / rollback
      |                                  |
      +---------- không tự phối hợp ----+
~~~

Nếu yêu cầu message receive và database write phải cùng commit hoặc cùng rollback, cần cơ chế phối hợp resource phù hợp, chẳng hạn JTA/XA khi broker và database hỗ trợ. Nếu không dùng transaction phân tán, thiết kế theo hướng at-least-once với idempotency, inbox/outbox hoặc đối soát.

Chỉ truyền một PlatformTransactionManager vào Step không chứng minh mọi resource đều tham gia transaction đó. Cần kiểm tra transaction manager, ConnectionFactory, session, acknowledgement mode và cách reader gọi client.

## 8. Ví dụ reader nhận message bằng JMS

Một custom ItemReader có thể nhận message đồng bộ thông qua JmsTemplate:

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
        // Chuyển JMS Message thành DTO theo payload thực tế.
        // Xử lý lỗi parse bằng exception có ngữ nghĩa rõ ràng.
        throw new UnsupportedOperationException("Implement conversion");
    }
}
~~~

Đây là khung minh họa; phần convert cần được triển khai theo message contract. Quan trọng là JmsTemplate và ConnectionFactory phải tham gia đúng JMS transaction. Nếu receive được thực hiện bằng session không transactional hoặc message được auto-ack trước khi writer hoàn tất, reader không có khả năng redelivery như framework mong đợi.

Không tự commit hoặc acknowledge message trong read() trước khi Step hoàn tất chunk. Việc xác nhận quá sớm có thể làm message biến mất khỏi queue dù processor hoặc writer sau đó thất bại.

## 9. Rollback, retry và việc đọc lại item

Fault-tolerant Step có thể retry thao tác lỗi. Cách item được cung cấp lại phụ thuộc reader:

**Reader không transactional:** framework thường dùng item đã buffer cho lần xử lý lại. Reader không nhất thiết được gọi lại để lấy cùng item từ nguồn.

**Transactional queue reader:** framework không dùng buffer item thông thường. Sau rollback, reader được gọi lại và broker có thể redeliver message.

Ví dụ retry lỗi database tạm thời:

~~~java
return new StepBuilder("consumeOrdersStep", jobRepository)
        .<OrderMessage, Order>chunk(20, transactionManager)
        .reader(queueReader)
        .readerIsTransactionalQueue()
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Ví dụ này chỉ phù hợp nếu exception thực tế được phân loại đúng và transaction rollback thực sự khiến queue redeliver message. Retry limit không tự bảo đảm broker redelivery; đó là trách nhiệm của transaction/acknowledgement integration.

Một rollback có thể làm toàn bộ message chưa được xác nhận trong transaction chunk được giao lại, không chỉ message gây lỗi. Vì vậy processor và writer phải chịu được việc xử lý lại các message khác trong cùng chunk.

## 10. Skip và transactional reader

Nếu một message chứa dữ liệu không hợp lệ vĩnh viễn, có thể cấu hình skip exception dữ liệu. Tuy nhiên, message phải được xử lý theo cách kết thúc được vòng lặp redelivery.

Ví dụ:

~~~java
return new StepBuilder("consumeOrdersStep", jobRepository)
        .<OrderMessage, Order>chunk(20, transactionManager)
        .reader(queueReader)
        .readerIsTransactionalQueue()
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderMessageException.class)
        .skipLimit(100)
        .listener(skipListener)
        .build();
~~~

Nếu message lỗi bị skip và chunk commit, queue cần xác nhận việc tiêu thụ message theo transaction. Ứng dụng cũng nên ghi message lỗi vào rejected store hoặc DLQ theo cơ chế bền vững.

Nếu lưu rejected record ở một database khác với transaction của queue, cần xử lý trường hợp một bên commit còn bên kia rollback. Dùng idempotency key, outbox/inbox hoặc quy trình đối soát. Không để message lỗi bị rollback rồi redeliver vô hạn mà không có giới hạn.

## 11. Empty queue và thời điểm kết thúc Step

ItemReader trả null để báo không còn item. Với file hoặc tập kết quả hữu hạn, đây là dấu hiệu hết input. Với queue, queue có thể chỉ tạm thời chưa có message.

Nếu reader dùng receive timeout rồi trả null, Spring Batch có thể xem đó là end-of-input và kết thúc Step. Cách này phù hợp với Job có mục tiêu xử lý hết message đang có tại một thời điểm hoặc một batch xác định.

Nếu cần một consumer chạy liên tục chờ message mới, chunk-oriented Step thông thường không tự tiếp tục vô hạn sau khi read() trả null. Cần mô hình message-driven consumer hoặc cơ chế polling được thiết kế riêng.

Trước khi triển khai queue reader, hãy xác định rõ điều kiện kết thúc:

- Queue rỗng tại thời điểm kiểm tra.
- Đã nhận đủ số message của một batch.
- Đã xử lý hết message thuộc một business key hoặc thời gian cutoff.
- Đã hết thời gian polling được cấu hình.

Không dùng null để biểu diễn lỗi kết nối hoặc timeout không mong muốn. Lỗi nguồn cần được thể hiện bằng exception để Step có thể áp dụng retry/fail policy.

## 12. ItemStream và checkpoint

ItemStream cung cấp các callback open, update và close để reader hoặc writer lưu và khôi phục trạng thái:

- open(ExecutionContext): khôi phục trạng thái khi Step bắt đầu hoặc restart.
- update(ExecutionContext): lưu checkpoint tại ranh giới xử lý phù hợp.
- close(): giải phóng resource.

Với file reader hoặc paging reader, ExecutionContext có thể lưu dòng, offset, page hoặc sort key. Với transactional queue, trạng thái giao nhận và acknowledgement thường được broker quản lý. Không nên tự lưu một số offset trong ExecutionContext rồi cho rằng nó thay thế transaction receive của queue.

Hai loại trạng thái cần phân biệt:

| Trạng thái | Nơi quản lý | Mục đích |
| --- | --- | --- |
| Reader checkpoint | JobRepository / ExecutionContext | Khôi phục vị trí đọc của reader có hỗ trợ restart |
| Queue delivery/ack state | Broker và client transaction | Xác định message đã được xác nhận hay cần redeliver |

Khi process dừng:

- Message đã commit/ack thường được xem là đã tiêu thụ.
- Message chưa commit/ack có thể được redeliver theo broker.
- Message đã ghi database nhưng chưa ack có thể xuất hiện lại và cần idempotency.
- Message đã ack nhưng database chưa commit có thể bị mất nếu hai resource không cùng transaction.

JobRepository lưu metadata Job/Step nhưng không tự quản lý acknowledgement của mọi broker.

## 13. Idempotency khi reader giao lại item

Transactional receive và rollback không bảo đảm exactly-once end-to-end. Message có thể được giao lại khi consumer mất kết nối, acknowledgement bị mất hoặc process dừng ở thời điểm kết quả commit chưa rõ.

Một cách phổ biến là lưu message ID với unique constraint:

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

Đây là ví dụ ý tưởng. Kiểm tra và ghi phải được bảo vệ bằng transaction cùng unique constraint phù hợp để tránh race condition khi nhiều worker nhận cùng message.

Có thể dùng inbox table để ghi nhận message đã xử lý:

~~~text
inbox_message
---------------------------------
message_id (UNIQUE)
received_at
processed_at
status
error_code
~~~

Ghi inbox record và dữ liệu nghiệp vụ trong cùng transaction database giúp lần giao lại nhận diện message đã được áp dụng. Với side effect ngoài database như HTTP request, email hoặc publish message, dùng idempotency key hoặc outbox tương ứng.

## 14. Poison message và redelivery lặp

Poison message là message luôn gây lỗi, ví dụ payload sai định dạng hoặc vi phạm điều kiện không thể phục hồi. Nếu mỗi lần xử lý đều rollback, broker có thể redeliver message liên tục.

~~~text
Queue
  |
  v
Receive message lỗi
  |
  v
Processor ném exception
  |
  v
Rollback
  |
  v
Broker redeliver
  |
  +---- lặp lại nếu không có chính sách dừng
~~~

Để tránh vòng lặp:

- Phân loại lỗi dữ liệu vĩnh viễn và lỗi tạm thời.
- Retry có giới hạn với backoff cho lỗi có khả năng phục hồi.
- Dùng skip policy khi nghiệp vụ cho phép bỏ qua.
- Ghi rejected record bằng SkipListener hoặc error handler.
- Chuyển message sang dead-letter queue khi đạt điều kiện.
- Lưu message ID, delivery count và nguyên nhân lỗi để điều tra.

Việc ghi DLQ và xác nhận queue gốc cũng cần transaction hoặc idempotency phù hợp. Nếu message bị xác nhận trước khi lưu lỗi bền vững, dữ liệu có thể bị mất.

## 15. Chunk size, prefetch và số message in-flight

Chunk size ảnh hưởng đến số message được nhận trong một transaction. Chunk lớn có thể giảm số lần commit nhưng tăng số message bị redeliver khi rollback.

Ngoài chunk size, broker thường có giới hạn prefetch hoặc số message in-flight. Broker có thể giao trước message cho consumer trước khi Spring Batch cần đến chúng.

Khi chọn cấu hình, xem xét:

- Thời gian xử lý trung bình và phân vị cao của một message.
- Số message trong một chunk.
- Số message broker prefetch.
- Memory cần để giữ payload.
- Thời gian commit queue và database.
- Số worker đồng thời.
- Số message có thể bị redeliver sau một rollback.
- Retry/skip và chi phí xử lý lại.

Không nên chỉ tăng chunk size để cải thiện throughput. Một chunk lớn có thể giữ transaction lâu và làm nhiều message quay lại queue khi chỉ một thao tác thất bại.

## 16. Những lỗi thường gặp

### Gọi readerIsTransactionalQueue cho reader thông thường

Framework ngừng buffer item, nhưng nguồn không có khả năng redelivery. Sau rollback, item có thể bị mất khỏi luồng xử lý. Chỉ bật khi reader thực sự dùng transactional queue.

### Nghĩ rằng readerIsTransactionalQueue tự tạo transaction

Phương thức này chỉ điều chỉnh buffering. Cần cấu hình transaction manager, queue client, session và acknowledgement riêng.

### Nhầm transaction của Step với transaction của nguồn

Reader được gọi trong chu kỳ chunk không chứng minh thao tác nhận item có thể rollback. Kiểm tra resource thực tế và transaction manager.

### Queue và database commit độc lập

Message có thể được ack trong khi database rollback hoặc database commit nhưng message được giao lại. Dùng XA/JTA khi cần và resource hỗ trợ, hoặc thiết kế idempotency/inbox/outbox.

### Acknowledge quá sớm

Nếu message được xác nhận trước khi writer hoàn tất, lỗi sau đó có thể làm mất message. Gắn acknowledgement với transaction hoặc chỉ xác nhận sau khi dữ liệu được lưu bền vững.

### Không chống xử lý trùng

Redelivery có thể xảy ra sau rollback hoặc crash. Dùng message ID, business key, unique constraint và thao tác idempotent.

### Trả null khi queue chỉ tạm thời rỗng

Spring Batch có thể kết thúc Step vì null biểu thị hết input. Xác định rõ Job drain queue hay consumer chạy liên tục.

### Không xử lý poison message

Message lỗi có thể bị redeliver vô hạn. Dùng retry limit, skip policy, quarantine hoặc DLQ.

### Giả định rollback chỉ trả lại message gây lỗi

Rollback transaction chunk có thể làm toàn bộ message chưa được xác nhận trong chunk được giao lại. Thiết kế processor và writer để chịu được việc chạy lại.

## 17. Quy trình thiết kế transactional reader

Khi cấu hình reader, hãy xác định:

1. Nguồn đọc là file, database, queue hay API?
2. Việc đọc có tiêu thụ item khỏi nguồn hay chỉ truy vấn dữ liệu?
3. Resource có hỗ trợ rollback và redelivery không?
4. Reader có tham gia đúng transaction manager của chunk không?
5. Có nên dùng buffering mặc định hay readerIsTransactionalQueue()?
6. Nếu rollback, item nào được đưa lại và bằng cơ chế nào?
7. Retry/skip có làm reader được gọi lại không?
8. Checkpoint nằm trong ExecutionContext hay do broker quản lý?
9. Queue và database có cần transaction chung không?
10. Message có ID ổn định và xử lý idempotent không?
11. Queue rỗng có nghĩa kết thúc Step hay cần tiếp tục chờ?
12. Poison message được retry, skip hoặc chuyển DLQ như thế nào?

Nên thử nghiệm bằng cách cố ý làm writer thất bại trước commit, sau đó quan sát reader được gọi lại, item có bị buffer hay redeliver, queue acknowledgement và dữ liệu database. Kiểm thử cả trường hợp process dừng giữa chunk để xác nhận hành vi phục hồi thực tế.

## Kết luận

Transactional reader là reader lấy item từ resource có thể hoàn tác thao tác nhận trong transaction, điển hình là transactional message queue. Với reader không transactional, Spring Batch thường buffer item đã đọc để xử lý lại sau rollback. Với transactional queue reader, cấu hình readerIsTransactionalQueue() tắt buffering để lần đọc tiếp theo nhận message được broker redeliver. Cấu hình này chỉ đúng khi queue receive/ack thực sự tham gia transaction phù hợp. Cần phân biệt transaction của Step với transaction của nguồn đọc, phối hợp queue và database đúng cách, hiểu semantics của empty queue và thiết kế idempotency để xử lý redelivery an toàn.
