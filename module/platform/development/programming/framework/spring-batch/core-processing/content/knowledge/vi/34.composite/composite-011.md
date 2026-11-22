# Rollback composite operation

Trong Spring Batch, một composite component có thể thực hiện nhiều thao tác cho cùng một item hoặc chunk. Ví dụ, một CompositeItemWriter có thể ghi đơn hàng vào bảng kết quả, ghi audit record và cập nhật bảng thống kê. Nếu một delegate thất bại giữa chừng, ứng dụng cần xác định những thao tác nào được rollback và những side effect nào đã xảy ra.

Điểm cốt lõi là **composite không tự tạo ra một transaction chung**. CompositeItemWriter gọi các delegate theo thứ tự; transaction của chunk Step mới là ranh giới rollback. Các thao tác chỉ được rollback cùng nhau khi chúng tham gia cùng transaction được quản lý. Ghi file, gọi API, gửi email hoặc publish message thường không tự được database transaction hoàn tác.

## 1. Composite operation trong Spring Batch

Composite operation là một thao tác được ghép từ nhiều component nhỏ. Trong Spring Batch, các ví dụ thường gặp gồm:

- CompositeItemProcessor: chuyển item qua nhiều processor theo chuỗi.
- CompositeItemWriter: chuyển cùng một chunk đến nhiều writer.
- Custom ItemWriter hoặc Tasklet: gọi nhiều service/repository trong một thao tác nghiệp vụ.
- Một Step ghi vào nhiều bảng hoặc nhiều đích dữ liệu.

Ví dụ một chunk cần thực hiện ba thao tác:

~~~text
Chunk
  |
  v
CompositeItemWriter
  |
  +--> Writer 1: insert order_result
  |
  +--> Writer 2: insert order_audit
  |
  +--> Writer 3: update batch_summary
~~~

CompositeItemWriter điều phối thứ tự gọi. Nó không tự quyết định cách undo từng delegate. Nếu Writer 3 ném exception, Spring Batch nhận exception từ lời gọi write và xử lý transaction chunk theo cấu hình Step.

## 2. CompositeItemWriter không phải transaction manager

CompositeItemWriter là một ItemWriter điều phối các ItemWriter khác. Nó không tự mở transaction database, không tạo transaction phân tán và không có một giao thức rollback riêng để đảo ngược mọi thao tác đã gọi.

Trong chunk-oriented Step, transaction manager được cấu hình tại Step:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(compositeWriter)
        .build();
~~~

Khi Step thực hiện một chunk, Spring Batch chạy phần xử lý chunk trong transaction theo cấu hình. Nếu một delegate writer ném exception và exception đó làm transaction rollback, các thay đổi database tham gia transaction sẽ được rollback.

Luồng khái quát:

~~~text
BEGIN chunk transaction
       |
       v
CompositeItemWriter.write(chunk)
       |
       +--> Delegate A ghi dữ liệu
       |
       +--> Delegate B ghi dữ liệu
       |
       +--> Delegate C thất bại
                    |
                    v
              Exception truyền ra
                    |
                    v
               ROLLBACK
                    |
                    v
       Các thay đổi transactional chưa commit bị hủy
~~~

Nếu không có transaction hoặc delegate ghi ra một hệ thống không tham gia transaction, dữ liệu đã ghi trước thời điểm lỗi có thể vẫn còn.

## 3. Ví dụ CompositeItemWriter ghi nhiều bảng

Giả sử mỗi Order cần ghi vào bảng kết quả và bảng audit. Cả hai bảng nằm trong cùng database:

~~~sql
create table order_result (
    order_id bigint primary key,
    status varchar(30) not null
);

create table order_audit (
    audit_id bigint generated always as identity primary key,
    order_id bigint not null,
    event_type varchar(40) not null
);
~~~

Writer thứ nhất ghi kết quả:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderResultWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into order_result(order_id, status)
                    values (:orderId, 'PROCESSED')
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Writer thứ hai ghi audit:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderAuditWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into order_audit(order_id, event_type)
                    values (:orderId, 'ORDER_PROCESSED')
                    """)
            .beanMapped()
            .assertUpdates(true)
            .build();
}
~~~

Ghép hai writer:

~~~java
@Bean
public CompositeItemWriter<Order> compositeOrderWriter(
        JdbcBatchItemWriter<Order> orderResultWriter,
        JdbcBatchItemWriter<Order> orderAuditWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(List.of(
                    orderResultWriter,
                    orderAuditWriter))
            .build();
}
~~~

Hai delegate nhận cùng kiểu Order và ghi hai phần dữ liệu khác nhau. Điều kiện quan trọng để rollback cùng nhau là chúng dùng DataSource được quản lý bởi cùng transaction manager của Step.

Nếu writer thứ hai lỗi sau khi writer thứ nhất đã chạy, câu lệnh insert của writer thứ nhất vẫn có thể rollback vì chưa commit và cùng tham gia transaction. Composite không cần tự xóa hàng của writer thứ nhất.

### Cấu hình transaction manager

Ví dụ Step:

~~~java
@Bean
public Step processOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        CompositeItemWriter<Order> compositeOrderWriter) {

    return new StepBuilder("processOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(compositeOrderWriter)
            .build();
}
~~~

Trong ứng dụng thật, cần xác nhận JobRepository và dữ liệu nghiệp vụ được cấu hình theo transaction strategy phù hợp. Việc hai JdbcBatchItemWriter nhận cùng một đối tượng DataSource là điều kiện quan trọng, nhưng vẫn phải bảo đảm Step dùng transaction manager quản lý DataSource đó.

## 4. Điều gì xảy ra khi một delegate thất bại?

Giả sử CompositeItemWriter có hai delegate:

1. Writer A insert vào order_result.
2. Writer B insert vào order_audit.

Nếu Writer B ném exception:

~~~text
Writer A: INSERT order_result -> thành công trong transaction
Writer B: INSERT order_audit  -> exception
Chunk transaction             -> ROLLBACK

Kết quả sau rollback:
order_result                  -> không còn insert của chunk
order_audit                   -> không có insert của chunk
~~~

Điều này đúng khi cả hai câu lệnh dùng cùng transaction database và không có thao tác commit độc lập.

Nếu Writer A đã gọi một REST API hoặc gửi email, transaction database không thể tự hoàn tác request/email đó. Kết quả thực tế có thể là:

~~~text
Writer A: REST API đã nhận request
Writer B: database write thất bại
Chunk transaction: ROLLBACK

Database: thay đổi được rollback
REST API: side effect vẫn tồn tại
~~~

Do đó, khi thiết kế composite, phải lập danh sách các resource mà mỗi delegate ghi vào và xác định resource nào thực sự transactional.

## 5. Thứ tự delegate ảnh hưởng đến side effect

CompositeItemWriter gọi delegate theo thứ tự được khai báo. Nếu một delegate ném exception, các delegate phía sau thường không được gọi trong lần thực thi đó.

Ví dụ:

~~~text
Delegate A -> thành công
Delegate B -> thất bại
Delegate C -> chưa được gọi
~~~

Thứ tự này quan trọng nếu các delegate có dependency hoặc side effect. Tuy nhiên, đổi thứ tự không tự giải quyết tính atomic. Nếu A đã gửi message ra ngoài trước khi B lỗi, việc đặt A sau B chỉ giảm một số tình huống chứ không tạo transaction chung.

Hãy thiết kế delegate độc lập khi có thể. Nếu thao tác thứ hai phụ thuộc kết quả thao tác thứ nhất, cân nhắc gom logic vào một service nghiệp vụ có transaction rõ ràng hoặc tách thành các Step với trạng thái trung gian bền vững.

Không dựa vào thứ tự delegate như một cơ chế rollback. Thứ tự chỉ quyết định trình tự thực hiện.

## 6. Retry có thể gọi lại delegate đã chạy

Khi một chunk rollback và được retry, Spring Batch có thể gọi lại thao tác ghi cho chunk đó. CompositeItemWriter sẽ bắt đầu lại chuỗi delegate theo lần gọi mới.

Ví dụ:

~~~text
Lần gọi 1:
  Writer A -> thành công
  Writer B -> timeout
  Chunk    -> rollback

Lần retry:
  Writer A -> được gọi lại
  Writer B -> được gọi lại
~~~

Nếu Writer A ghi database trong transaction đã rollback, lần retry có thể thực hiện lại an toàn theo transaction. Nếu Writer A đã gửi API hoặc publish message, lần retry có thể tạo side effect trùng.

Vì vậy, mọi delegate có thể được gọi lại cần có chiến lược idempotency phù hợp:

- Dùng business key ổn định.
- Dùng idempotency key khi gọi API.
- Dùng unique constraint để chống insert trùng.
- Dùng upsert có điều kiện nếu nghiệp vụ cho phép.
- Lưu trạng thái operation để biết side effect đã hoàn tất.
- Không tạo UUID mới cho cùng một operation mỗi lần retry nếu UUID là idempotency key.

Idempotency không thay thế transaction, nhưng giúp thao tác lặp lại không tạo thêm kết quả ngoài ý muốn.

## 7. CompositeItemProcessor và side effect

CompositeItemProcessor nối nhiều processor theo chuỗi:

~~~text
Input
  |
  v
ValidationProcessor
  |
  v
EnrichmentProcessor
  |
  v
CalculationProcessor
  |
  v
Output
~~~

Processor thường nên tập trung vào validation, mapping và tính toán, không ghi dữ liệu hoặc gọi side effect không thể đảo ngược. Nếu một processor gửi email rồi processor sau ném exception, rollback chunk database không thể thu hồi email.

Ví dụ cấu hình:

~~~java
@Bean
public CompositeItemProcessor<OrderInput, OrderOutput> orderProcessor(
        ItemProcessor<OrderInput, ValidatedOrder> validationProcessor,
        ItemProcessor<ValidatedOrder, EnrichedOrder> enrichmentProcessor,
        ItemProcessor<EnrichedOrder, OrderOutput> calculationProcessor) {

    return new CompositeItemProcessorBuilder<OrderInput, OrderOutput>()
            .delegates(
                    validationProcessor,
                    enrichmentProcessor,
                    calculationProcessor)
            .build();
}
~~~

CompositeItemProcessor không phải transaction coordinator. Nếu processor có ghi database, thao tác đó chỉ rollback khi nó tham gia transaction của chunk. Nếu processor gọi hệ thống ngoài, cần outbox, idempotency hoặc compensation.

Một thiết kế tốt thường để processor không có side effect, còn các thao tác ghi nằm trong writer hoặc service được quản lý transaction rõ ràng.

## 8. Tất cả database delegate phải tham gia cùng transaction

Để rollback nhiều database writer cùng nhau, cần kiểm tra:

- Các writer dùng cùng DataSource transaction-aware.
- Step dùng PlatformTransactionManager quản lý DataSource đó.
- Writer dùng JDBC API tham gia Spring transaction, chẳng hạn JdbcTemplate, NamedParameterJdbcTemplate hoặc JdbcBatchItemWriter.
- Không tự lấy connection qua DriverManager rồi commit riêng.
- Không mở transaction độc lập trong delegate nếu không có chủ đích.
- Không gọi commit() trực tiếp trên connection do Spring quản lý.

Ví dụ một custom writer nên dùng JdbcTemplate:

~~~java
public class CustomAuditWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public CustomAuditWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                    """
                    insert into order_audit(order_id, event_type)
                    values (?, ?)
                    """,
                    order.getOrderId(),
                    "ORDER_PROCESSED");
        }
    }
}
~~~

JdbcTemplate lấy connection thông qua cơ chế tích hợp transaction của Spring. Nếu custom code cần dùng JDBC connection trực tiếp, hãy dùng DataSourceUtils hoặc API transaction-aware phù hợp thay vì tự mở connection không được quản lý.

### Hai DataSource cùng trỏ một database không phải một transaction

Nếu writer A dùng dataSourceA và writer B dùng dataSourceB, dù hai DataSource trỏ cùng server/schema, chúng có thể dùng hai connection và hai transaction riêng. Transaction manager cục bộ quản lý một DataSource không tự điều phối transaction của DataSource còn lại.

Nếu yêu cầu atomic giữa nhiều resource database thực sự bắt buộc, có thể cân nhắc transaction manager phân tán/XA khi database, driver và hạ tầng hỗ trợ. Cần đánh giá chi phí vận hành và độ phức tạp. Nhiều hệ thống chọn outbox hoặc quy trình bù trừ để đạt tính nhất quán cuối cùng thay vì dùng XA.

## 9. Propagation có thể làm mất rollback mong đợi

Một delegate có thể gọi service được đánh dấu @Transactional. Cần chú ý transaction propagation:

| Propagation | Hành vi khái quát | Ảnh hưởng đến chunk |
| --- | --- | --- |
| REQUIRED | Tham gia transaction hiện tại hoặc tạo mới nếu chưa có | Thường phù hợp để service join chunk transaction |
| REQUIRES_NEW | Tạm ngưng transaction hiện tại và tạo transaction độc lập | Transaction con có thể commit dù chunk bên ngoài rollback |
| SUPPORTS | Tham gia transaction nếu có, nếu không thì chạy không transaction | Cần hiểu caller context |
| NOT_SUPPORTED | Tạm ngưng transaction hiện tại | Thao tác không được rollback cùng chunk |

Ví dụ:

~~~java
@Transactional
public void writeBusinessData(Order order) {
    repository.save(order);
}
~~~

Mặc định REQUIRED thường tham gia transaction đang hoạt động nếu service được gọi qua Spring proxy và dùng transaction manager phù hợp.

Ngược lại:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit(Order order) {
    auditRepository.save(new AuditRecord(order.getOrderId()));
}
~~~

Audit transaction có thể commit riêng. Nếu delegate sau đó thất bại, chunk rollback không hoàn tác audit record đã commit.

Không dùng REQUIRES_NEW chỉ để “đảm bảo audit luôn được ghi” mà không xác định semantics nghiệp vụ. Nếu audit phải tồn tại dù chunk thất bại, hãy ghi rõ đó là audit attempt/failure event và thiết kế trạng thái tương ứng.

## 10. noRollback và exception policy

Trong chunk Step, exception từ writer thường làm transaction rollback. Tuy nhiên, fault-tolerant Step có thể cấu hình retry, skip hoặc noRollback cho một số exception.

Ví dụ cấu hình:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

Skip policy và rollback policy có liên quan nhưng không đồng nghĩa. Nếu một exception được cấu hình không rollback, các thay đổi đã thực hiện trong transaction có thể vẫn được commit tùy flow và cách exception được xử lý. Không đánh dấu một exception từ delegate là noRollback nếu delegate có thể đã ghi một phần dữ liệu cần được hoàn tác.

Với lỗi dữ liệu có thể bỏ qua, hãy xác định rõ delegate nào đã chạy và liệu chunk có thể tiếp tục an toàn. Với lỗi hạ tầng như connection failure, deadlock hoặc timeout, thường cần retry/fail theo chính sách phù hợp thay vì skip như một record sai.

## 11. ItemStream lifecycle của delegate

Một số writer cũng triển khai ItemStream để quản lý resource hoặc checkpoint, chẳng hạn FlatFileItemWriter. Composite writer cần quản lý lifecycle của các delegate stream:

- open(ExecutionContext) khi Step mở writer.
- update(ExecutionContext) tại checkpoint.
- close() khi Step kết thúc.

CompositeItemWriter có cơ chế chuyển tiếp lifecycle đến các delegate ItemStream theo cấu hình của phiên bản Spring Batch. Nếu viết custom composite hoặc bọc delegate bằng decorator, phải bảo đảm delegate ItemStream được đăng ký và các callback được chuyển tiếp đúng.

Ví dụ custom wrapper:

~~~java
public class AuditingWriter<T>
        implements ItemStreamWriter<T> {

    private final ItemStreamWriter<T> delegate;

    public AuditingWriter(ItemStreamWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        delegate.open(context);
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        delegate.write(chunk);
    }

    @Override
    public void update(ExecutionContext context) throws ItemStreamException {
        delegate.update(context);
    }

    @Override
    public void close() throws ItemStreamException {
        delegate.close();
    }
}
~~~

Nếu wrapper chỉ implement ItemWriter mà không chuyển tiếp ItemStream, delegate có thể không được mở, cập nhật checkpoint hoặc đóng đúng cách. Điều này gây lỗi restart hoặc rò rỉ resource dù write() đơn lẻ có vẻ hoạt động.

Lifecycle không phải rollback. Việc close() được gọi không có nghĩa các side effect đã thực hiện được undo.

## 12. Ghi database và file trong cùng composite

Một composite có thể gồm JdbcBatchItemWriter và FlatFileItemWriter. Đây là tình huống dễ gây hiểu nhầm:

~~~text
CompositeItemWriter
      |
      +--> JdbcBatchItemWriter
      |
      +--> FlatFileItemWriter
~~~

Database có transaction rõ ràng. FlatFileItemWriter có cơ chế transactional buffering để phối hợp việc ghi chunk, nhưng filesystem không tự trở thành một resource XA chung với database. Lỗi process, lỗi I/O hoặc sự cố giữa các bước flush/commit vẫn có thể khiến hai đích không đồng bộ.

Với output file quan trọng, nên dùng staging:

1. Ghi file vào tên tạm gắn với JobInstance hoặc JobExecution.
2. Ghi dữ liệu database trong chunk transaction.
3. Hoàn tất Job và kiểm tra BatchStatus, ExitStatus cùng business validation.
4. Kiểm tra số record, kích thước và checksum của file tạm.
5. Publish file bằng rename/move hoặc cơ chế lưu trữ phù hợp.
6. Ghi nhận trạng thái publish và thông báo cho consumer.

Consumer chỉ đọc file ở trạng thái PUBLISHED. Nếu Job thất bại, file tạm có thể được giữ để điều tra hoặc xóa theo retention policy.

Nếu cần đảm bảo database và trạng thái publish nhất quán, lưu một bản ghi publication/outbox trong cùng transaction database, sau đó publisher riêng thực hiện move và đánh dấu hoàn tất theo cách idempotent.

## 13. Ghi database và gửi message

Ví dụ composite ghi order vào database rồi gửi message:

~~~text
CompositeItemWriter
      |
      +--> Database writer: INSERT order
      |
      +--> Message writer: publish OrderCreated
~~~

Nếu database insert thành công nhưng broker publish thất bại, chunk có thể rollback database. Nhưng nếu broker đã nhận message rồi transaction database thất bại, message không tự bị thu hồi.

Đây là dual-write problem. Thứ tự ghi không thể tự bảo đảm atomicity giữa database và message broker.

### Dùng transactional outbox

Trong cùng transaction database, ghi cả business data và event vào outbox:

~~~sql
insert into orders(order_id, status)
values (:orderId, 'CREATED');

insert into outbox_event(event_id, aggregate_id, event_type, payload, status)
values (:eventId, :orderId, 'ORDER_CREATED', :payload, 'PENDING');
~~~

Sau khi transaction commit, publisher riêng đọc các outbox event PENDING và gửi đến broker:

~~~text
Chunk transaction
    |
    +--> INSERT orders
    |
    +--> INSERT outbox_event
    |
    +--> COMMIT
             |
             v
      Outbox publisher
             |
             v
          Message broker
~~~

Nếu chunk rollback, cả order và outbox event đều rollback. Nếu publisher gửi message nhưng chưa kịp đánh dấu SENT rồi process dừng, event có thể được gửi lại. Consumer vẫn cần idempotency theo event_id.

Outbox không tạo exactly-once end-to-end tự động, nhưng giúp tránh mất event giữa database commit và publish.

## 14. Gọi REST API hoặc gửi email trong composite

REST API, email và nhiều dịch vụ bên ngoài không tham gia transaction database của Step. Nếu gọi trực tiếp trong writer:

- API có thể đã xử lý request dù chunk rollback.
- Email đã gửi không thể thu hồi bằng rollback.
- Retry có thể gửi lại request hoặc email.
- Timeout không chứng minh phía nhận chưa xử lý request.

Các lựa chọn:

- Gửi request với idempotency key ổn định.
- Ghi command vào outbox và xử lý bằng publisher riêng.
- Dùng API hỗ trợ transaction hoặc deduplication nếu có.
- Ghi trạng thái operation để có thể đối soát.
- Dùng compensation khi nghiệp vụ cho phép hoàn tác bằng một thao tác mới.

Không đặt lời gọi API không idempotent trong processor chỉ vì processor được gọi trước writer. Nếu processor được gọi lại sau rollback/retry, side effect vẫn có thể lặp.

## 15. Compensation khi không thể rollback

Rollback chỉ hủy thay đổi chưa commit trong transaction có hỗ trợ. Với side effect đã xảy ra ngoài transaction, có thể cần compensation.

Ví dụ:

~~~text
Operation A: reserve inventory
Operation B: create shipment
Operation C: payment request fails

Compensation:
  release inventory
  cancel shipment nếu hệ thống hỗ trợ
~~~

Compensation là một thao tác nghiệp vụ mới, không phải rollback vật lý. Nó có thể thất bại, cần retry và phải có trạng thái theo dõi riêng.

Khi dùng compensation:

- Ghi lại operation gốc và kết quả từng bước.
- Định nghĩa hành động bù cho mỗi side effect.
- Làm compensation idempotent.
- Có trạng thái PENDING/COMPLETED/FAILED cho từng hành động.
- Có quy trình xử lý thủ công khi compensation không thành công.
- Không xóa lịch sử operation gốc.

Mẫu Saga thường dùng khi một quy trình trải qua nhiều dịch vụ độc lập và không có distributed transaction chung.

## 16. Custom composite service với @Transactional

Nếu một thao tác nghiệp vụ gồm nhiều repository call trên cùng database, có thể gom vào service:

~~~java
@Service
public class OrderCompletionService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderCompletionService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public void complete(Order order) {
        orderRepository.markProcessed(order.getOrderId());
        auditRepository.insertProcessedEvent(order.getOrderId());
    }
}
~~~

Writer gọi service:

~~~java
public class OrderCompletionWriter implements ItemWriter<Order> {

    private final OrderCompletionService service;

    public OrderCompletionWriter(OrderCompletionService service) {
        this.service = service;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            service.complete(order);
        }
    }
}
~~~

Với propagation mặc định REQUIRED và cùng transaction manager, service thường tham gia transaction chunk đang hoạt động. Nếu một item trong chunk làm service ném exception, transaction chunk có thể rollback toàn bộ thao tác database của chunk.

Lưu ý:

- Service phải được gọi qua Spring proxy để transaction interceptor hoạt động.
- Self-invocation trong cùng bean có thể không đi qua proxy.
- Các repository phải dùng cùng transaction manager/resource nếu cần rollback cùng nhau.
- Không dùng REQUIRES_NEW nếu muốn thao tác service rollback cùng chunk.
- Exception cần được truyền ra writer nếu Step phải rollback.

Không bắt exception trong service rồi chỉ log và tiếp tục nếu thao tác thất bại khiến dữ liệu không nhất quán.

## 17. Rollback với nhiều database

Nếu composite ghi vào hai database độc lập:

~~~text
Composite writer
   |
   +--> DataSource A / transaction A
   |
   +--> DataSource B / transaction B
~~~

Một transaction manager cục bộ thường chỉ quản lý một resource. Nếu transaction A commit trước rồi B thất bại, rollback transaction B không thể hoàn tác A đã commit.

Các lựa chọn:

1. **JTA/XA:** phối hợp commit/rollback nhiều resource nếu tất cả resource và hạ tầng hỗ trợ. Cần chấp nhận cấu hình và vận hành phức tạp hơn.
2. **Outbox/inbox:** ghi trạng thái và yêu cầu đồng bộ trong một database transaction, sau đó đồng bộ sang database còn lại bằng consumer idempotent.
3. **Saga/compensation:** thực hiện các bước độc lập và có thao tác bù khi bước sau thất bại.
4. **Reconciliation:** ghi lại trạng thái từng đích và chạy đối soát để sửa các trường hợp lệch.

Không gọi hai transaction manager lần lượt rồi coi chúng như một transaction atomic. Cần xác định rõ trạng thái khi process dừng giữa hai commit.

## 18. Reader, checkpoint và rollback của chunk

Khi writer composite thất bại, chunk transaction có thể rollback. Reader state được lưu thông qua ItemStream/ExecutionContext tại ranh giới chunk theo cơ chế Spring Batch. Lần retry hoặc restart sẽ dựa vào checkpoint hợp lệ gần nhất.

Ví dụ:

~~~text
Chunk 1:
  delegate A + delegate B thành công
  COMMIT
  checkpoint được lưu

Chunk 2:
  delegate A thành công
  delegate B thất bại
  ROLLBACK

Restart:
  tiếp tục từ checkpoint sau chunk 1
  thực hiện lại dữ liệu của chunk 2
~~~

Nếu delegate A có side effect ngoài transaction, lần thực hiện lại chunk 2 có thể lặp side effect đó. Checkpoint chỉ quản lý tiến độ của Step, không tự hoàn tác hoặc deduplicate hệ thống ngoài.

Để restart an toàn:

- Reader và writer phải lưu state đúng nếu cần restart.
- Tên reader/writer và JobParameters identifying phải ổn định.
- Input dataset phải không đổi hoặc có version cố định.
- Writer có unique key hoặc idempotency phù hợp.
- Side effect ngoài transaction phải được ghi nhận và đối soát.

## 19. Skip và retry với composite writer

Nếu một delegate ném exception, Step có thể retry chunk hoặc skip theo fault-tolerant policy. Cần hiểu exception phát sinh ở delegate nào và trạng thái của các delegate đã chạy trước đó.

Ví dụ retry:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Nếu delegate A ghi database trong transaction chunk và delegate B gặp lỗi transient, rollback rồi retry có thể an toàn cho A. Nếu A gửi API, phải dùng idempotency key hoặc outbox.

Skip writer exception cần được thiết kế cẩn thận. Nếu một delegate đã thực hiện side effect không thể rollback rồi exception được skip, chunk có thể tiếp tục và hệ thống đích không còn đồng nhất. Chỉ skip khi đã xác định được trạng thái các thao tác và có quy tắc nghiệp vụ rõ.

Không retry vô hạn hoặc retry mọi exception. Lỗi dữ liệu vĩnh viễn không trở nên hợp lệ sau nhiều lần thử; lỗi cấu hình cần fail sớm.

## 20. Kiểm thử rollback của composite

Nên tách hai cấp kiểm thử:

**Unit test:** kiểm tra composite gọi delegate theo thứ tự và truyền đúng chunk; xác nhận exception được truyền ra khi delegate thất bại.

**Integration test:** chạy Step với transaction manager và database thật để xác nhận các thay đổi của delegate trước đó được rollback.

Unit test minh họa:

~~~java
@Test
void callsDelegatesInOrderAndPropagatesFailure() throws Exception {
    @SuppressWarnings("unchecked")
    ItemWriter<Order> first = mock(ItemWriter.class);
    @SuppressWarnings("unchecked")
    ItemWriter<Order> second = mock(ItemWriter.class);

    doThrow(new IllegalStateException("second writer failed"))
            .when(second)
            .write(any());

    CompositeItemWriter<Order> composite =
            new CompositeItemWriterBuilder<Order>()
                    .delegates(List.of(first, second))
                    .build();

    Chunk<Order> chunk = new Chunk<>(List.of(new Order(1001L)));

    assertThrows(
            IllegalStateException.class,
            () -> composite.write(chunk));

    InOrder order = inOrder(first, second);
    order.verify(first).write(chunk);
    order.verify(second).write(chunk);
}
~~~

Test này chỉ chứng minh thứ tự gọi và exception propagation. Mock không có database transaction nên không chứng minh rollback.

### Integration test xác nhận database rollback

Một test tích hợp nên:

1. Tạo database test và hai bảng kết quả/audit.
2. Cấu hình hai delegate JDBC dùng cùng DataSource.
3. Cấu hình Step dùng transaction manager quản lý DataSource đó.
4. Cho delegate thứ hai ném exception sau khi delegate thứ nhất đã ghi.
5. Chạy Step và xác nhận execution thất bại.
6. Truy vấn cả hai bảng để xác nhận các insert của chunk chưa commit không tồn tại.

Ví dụ phần assertion sau khi Step kết thúc:

~~~java
assertEquals(BatchStatus.FAILED, execution.getStatus());

Integer resultCount = jdbcTemplate.queryForObject(
        "select count(*) from order_result where order_id = ?",
        Integer.class,
        1001L);

Integer auditCount = jdbcTemplate.queryForObject(
        "select count(*) from order_audit where order_id = ?",
        Integer.class,
        1001L);

assertEquals(0, resultCount);
assertEquals(0, auditCount);
~~~

Test cần bảo đảm exception xảy ra trước commit và hai writer thực sự tham gia cùng transaction. Nếu dùng một writer lỗi giả, hãy đặt nó sau writer database trong composite. Dùng database cùng loại với production khi behavior phụ thuộc engine.

### Kiểm thử side effect không rollback

Nếu delegate thứ nhất gọi fake external API và delegate thứ hai thất bại, test nên xác nhận API fake vẫn ghi nhận request. Điều này chứng minh vì sao cần idempotency hoặc outbox, thay vì kỳ vọng database rollback sẽ xóa side effect.

## 21. Những lỗi thường gặp

### Nghĩ CompositeItemWriter tự rollback các delegate

Composite chỉ điều phối lời gọi. Transaction của Step mới quản lý rollback cho resource tham gia transaction.

### Hai writer dùng hai transaction manager độc lập

Một writer có thể commit trong khi writer kia rollback. Dùng cùng transaction manager nếu cùng database, hoặc thiết kế XA/outbox/compensation.

### Ghi database rồi gọi API trực tiếp

API không rollback cùng database. Dùng idempotency key hoặc outbox.

### Retry làm gửi message/email trùng

Delegate trước đó có thể được gọi lại sau rollback. Thiết kế operation idempotent và dùng key ổn định.

### Dùng REQUIRES_NEW trong delegate mà mong rollback cùng chunk

Transaction độc lập có thể commit riêng. Dùng REQUIRED nếu muốn join transaction chunk và cùng transaction manager.

### Bắt exception rồi tiếp tục

Step không biết thao tác thất bại và có thể commit dữ liệu không nhất quán. Truyền exception hoặc xử lý theo policy có chủ đích.

### Bỏ qua ItemStream lifecycle

Delegate có thể không lưu checkpoint hoặc không đóng resource. Chuyển tiếp open/update/close và đăng ký stream đúng cách.

### Coi footer/file tồn tại là bằng chứng commit

File system không tự atomic với database. Dùng staging và bước publish sau khi xác nhận kết quả.

### Dùng skip cho lỗi hạ tầng

Lỗi kết nối, timeout hoặc deadlock thường cần retry/fail, không phải bỏ qua record.

### Chỉ test exception propagation

Unit test không xác nhận transaction rollback. Cần integration test với database và transaction manager thật.

## 22. Quy trình thiết kế rollback cho composite operation

Trước khi ghép nhiều delegate, hãy lập bảng resource:

| Delegate | Resource đích | Transaction manager | Có rollback cùng chunk? |
| --- | --- | --- | --- |
| Database writer A | Database nghiệp vụ | Transaction manager của Step | Có, nếu cùng transaction |
| Database writer B | Cùng database/DataSource | Cùng transaction manager | Có, nếu cùng transaction |
| Writer C | Database khác | Transaction manager riêng | Không tự động |
| File writer | Filesystem | Cơ chế writer/file riêng | Không atomic với database |
| Message publisher | Broker | Broker transaction nếu cấu hình riêng | Không tự động cùng DB |
| REST/email delegate | Dịch vụ ngoài | Không thuộc DB transaction | Không |

Sau đó xác định:

1. Delegate nào có side effect và thứ tự gọi có ý nghĩa gì?
2. Exception ở từng delegate có làm rollback chunk không?
3. Các writer database có dùng cùng DataSource và transaction manager không?
4. Có service nào dùng REQUIRES_NEW hoặc transaction manager khác không?
5. Retry có gọi lại delegate đã chạy trước đó không?
6. Side effect ngoài transaction có idempotency key không?
7. Có cần outbox, staging file, compensation hoặc reconciliation không?
8. ItemStream delegate có được quản lý lifecycle không?
9. Checkpoint có thể khôi phục cùng input và output path không?
10. Unit test và integration test đã kiểm tra đúng các ranh giới rollback chưa?

Một composite operation đáng tin cậy cần có transaction boundary rõ ràng, delegate idempotent khi có thể được gọi lại và cơ chế xử lý riêng cho resource không transactional.

## Kết luận

Rollback của composite operation trong Spring Batch đến từ transaction của chunk Step, không phải từ CompositeItemWriter tự đảo ngược từng delegate. Khi các writer cùng dùng một DataSource và transaction manager, thay đổi database chưa commit có thể rollback cùng nhau nếu một delegate thất bại. Nếu composite ghi file, gửi message, gọi API hoặc ghi nhiều database độc lập, side effect có thể tồn tại sau rollback và bị lặp khi retry. Hãy phân loại resource, dùng transaction chung cho thao tác database có thể tham gia cùng transaction, thiết kế idempotency cho delegate được gọi lại, và dùng outbox, staging/publish hoặc compensation cho side effect bên ngoài. Kiểm tra thứ tự delegate bằng unit test và xác nhận rollback thực tế bằng integration test với transaction manager cùng database phù hợp.
