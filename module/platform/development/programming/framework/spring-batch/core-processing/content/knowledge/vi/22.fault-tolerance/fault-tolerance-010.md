# Xử lý lỗi khi writer ghi một phần

Trong Spring Batch, ItemWriter thường nhận cả một chunk và ghi nhiều item trong cùng một lần gọi. Nếu writer ghi được một số item rồi gặp lỗi, kết quả phụ thuộc vào tài nguyên mà writer đang sử dụng và việc tài nguyên đó có tham gia transaction của chunk hay không.

Với database dùng cùng transaction manager của Step, các câu lệnh ghi đã thực hiện trước exception thường được rollback cùng chunk. Với file ghi trực tiếp, HTTP API, message broker hoặc database độc lập, các thay đổi đã được hệ thống bên ngoài chấp nhận có thể vẫn tồn tại sau khi transaction của Step rollback.

Vì vậy, xử lý lỗi ghi một phần cần trả lời ba câu hỏi:

1. Writer đã thực hiện được những thao tác nào trước khi lỗi?
2. Những thao tác đó có nằm trong transaction của chunk không?
3. Khi retry, skip hoặc restart, writer có thể được gọi lại mà không tạo dữ liệu trùng hoặc trạng thái không nhất quán không?

## 1. Writer ghi theo chunk

Trong chunk-oriented Step, Spring Batch đọc item, xử lý item rồi chuyển các kết quả cho writer. Transaction thường bao quanh toàn bộ lần xử lý chunk.

~~~text
Bắt đầu transaction
        |
        v
ItemReader đọc các item
        |
        v
ItemProcessor xử lý item
        |
        v
ItemWriter.write(chunk)
        |
        +---- Ghi thành công
        |         |
        |         v
        |   Cập nhật checkpoint
        |         |
        |         v
        |       COMMIT
        |
        +---- Ghi thất bại
                  |
                  v
          Rollback policy
                  |
                  v
              ROLLBACK
                  |
                  v
          Retry / Skip / FAILED
~~~

Ví dụ cấu hình Step:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Với chunk size 100, writer thường nhận tối đa 100 item trong một lần gọi. Nếu writer thất bại, Spring Batch xử lý exception theo transaction và fault-tolerance policy của Step.

Một chunk không phải là một chuỗi commit độc lập cho từng item. Trong trường hợp database writer tham gia cùng transaction, các thao tác ghi trong chunk được xác nhận khi transaction commit. Nếu transaction rollback, toàn bộ thay đổi tham gia transaction đó được hoàn tác.

## 2. Ví dụ writer ghi được một phần rồi ném exception

Giả sử chunk chứa bốn đơn hàng A, B, C và D. Writer ghi từng đơn hàng:

~~~java
public class OrderWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            repository.save(order);

            if ("C".equals(order.orderNumber())) {
                throw new OrderWriteException(
                        "Simulated failure at order C");
            }
        }
    }
}
~~~

Nếu repository sử dụng cùng database và transaction manager với Step, diễn biến có thể là:

~~~text
Transaction chunk bắt đầu
        |
        v
Ghi A -> thành công trong transaction
        |
        v
Ghi B -> thành công trong transaction
        |
        v
Ghi C -> phát sinh exception
        |
        v
Exception thoát khỏi writer
        |
        v
Transaction rollback
        |
        v
A, B và các thay đổi khác
trong transaction đều bị hoàn tác
~~~

Cần phân biệt “câu lệnh SQL đã chạy thành công” với “dữ liệu đã commit”. A và B có thể đã được database xử lý, nhưng chưa được transaction xác nhận. Nếu transaction rollback thành công, các thay đổi đó không còn trong database.

Nếu repository tự mở transaction mới hoặc tự commit từng item, kết quả sẽ khác. Khi đó A và B có thể đã được commit độc lập và transaction của chunk không thể hoàn tác chúng.

## 3. Điều kiện để rollback toàn bộ phần đã ghi

Muốn rollback phần ghi trước exception, các thao tác cần tham gia cùng transaction có thể rollback.

Các điều kiện quan trọng:

- Writer sử dụng database hoặc tài nguyên có transaction.
- Writer dùng cùng transaction manager và resource được Step quản lý.
- Các thao tác ghi không tự commit độc lập.
- Exception được truyền ra ngoài writer để framework nhận biết.
- Rollback policy của Step phân loại exception là lỗi cần rollback.
- Không có thao tác đã commit trong một transaction độc lập trước khi chunk thất bại.

Ví dụ JDBC writer:

~~~java
@Bean
public JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO orders (id, order_number, amount)
                VALUES (:id, :orderNumber, :amount)
                """)
            .beanMapped()
            .build();
}
~~~

Transaction manager phải quản lý đúng DataSource mà writer sử dụng:

~~~java
@Bean
public PlatformTransactionManager transactionManager(
        DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
~~~

Với cấu hình phù hợp, JdbcBatchItemWriter sử dụng hạ tầng Spring JDBC để tham gia transaction hiện tại. Nếu một lệnh trong batch thất bại và exception được truyền ra, transaction chunk có thể rollback các thay đổi đã thực hiện trước đó.

Với JPA, việc flush EntityManager có thể gửi SQL xuống database trước khi commit. Flush không đồng nghĩa commit; nếu transaction vẫn hoạt động và sau đó rollback, các thay đổi database thuộc transaction đó được hoàn tác.

## 4. Không tự commit từng item trong writer

Một custom writer có thể vô tình phá vỡ transaction của chunk nếu tự lấy connection mới và commit từng item.

Ví dụ không phù hợp khi muốn rollback toàn chunk:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) throws Exception {
    for (Order order : chunk) {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            saveOrder(connection, order);

            connection.commit();
        }
    }
}
~~~

Mỗi item được commit trong một transaction độc lập. Nếu item C thất bại, transaction chunk bên ngoài không thể rollback các transaction đã commit của A và B.

Với custom JDBC writer, hãy dùng JdbcTemplate, NamedParameterJdbcTemplate hoặc DataSourceUtils để sử dụng connection gắn với transaction Spring hiện tại. Tránh gọi commit trực tiếp nếu muốn writer tham gia transaction chunk.

Cũng cần kiểm tra propagation của service mà writer gọi. Một phương thức dùng REQUIRES_NEW tạo transaction độc lập; nếu transaction đó commit thì dữ liệu có thể tồn tại dù chunk bên ngoài rollback.

## 5. Exception phải được truyền tới Spring Batch

Spring Batch cần biết writer thất bại để thực hiện rollback và áp dụng retry/skip policy.

Cách không an toàn là bắt exception rồi chỉ ghi log:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    try {
        repository.saveAll(chunk.getItems());
    } catch (DataAccessException exception) {
        log.error("Could not write order chunk", exception);
        // Trả về bình thường dù thao tác ghi đã thất bại.
    }
}
~~~

Khi writer trả về bình thường, framework có thể coi lời gọi write đã thành công và tiếp tục cập nhật checkpoint/commit. Nếu một phần dữ liệu đã được ghi, trạng thái có thể không nhất quán với ý định của ứng dụng.

Cách phù hợp hơn:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    try {
        repository.saveAll(chunk.getItems());
    } catch (DataAccessException exception) {
        log.error("Could not write order chunk", exception);
        throw exception;
    }
}
~~~

Nếu cần chuyển exception sang loại riêng, hãy giữ nguyên cause:

~~~java
throw new OrderWriteException(
        "Could not persist the current chunk",
        exception);
~~~

Không nên chuyển mọi lỗi thành một exception chung mà làm mất thông tin cần cho retry classifier, skip classifier hoặc log chẩn đoán.

## 6. Phân biệt write failure với commit failure

Có hai thời điểm thất bại khác nhau.

**Write failure** xảy ra khi ItemWriter.write() đang thực hiện và ném exception. Framework nhận được lỗi ngay trong quá trình ghi, sau đó áp dụng rollback và fault-tolerance policy.

**Commit failure** xảy ra sau khi writer trả về thành công, trong khi transaction manager đang commit. Ví dụ connection bị ngắt đúng lúc database xử lý commit.

Với write failure, ứng dụng thường biết writer đã ném exception trước khi commit. Với commit failure do mất kết nối, kết quả có thể không rõ: database có thể đã commit nhưng client không nhận được xác nhận.

Khi kết quả commit không xác định:

- Không giả định chắc chắn dữ liệu đã rollback.
- Không lặp thao tác không idempotent một cách mù quáng.
- Dùng business key hoặc unique constraint để kiểm tra trạng thái.
- Truy vấn lại database khi kết nối phục hồi.
- Thiết kế writer để có thể chạy lại an toàn.

Idempotency là một phần quan trọng của khả năng phục hồi khi không thể xác định kết quả commit từ phía client.

## 7. Retry khi writer ghi một phần

Retry phù hợp với lỗi tạm thời mà lần thử tiếp theo có khả năng thành công, chẳng hạn database deadlock hoặc lỗi kết nối ngắn hạn.

Ví dụ:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
~~~

Nếu writer ghi được một số item rồi gặp deadlock, transaction hiện tại được rollback theo policy. Framework có thể thử lại công việc theo retry policy. Các thay đổi database từ lần thử bị rollback sẽ không còn, nếu chúng thực sự tham gia cùng transaction.

Retry có thể khiến writer được gọi lại với cùng chunk. Vì vậy, writer không nên giả định mỗi chunk chỉ được gọi đúng một lần. Nếu writer thực hiện side effect ngoài transaction, lần gọi lại có thể tạo tác động trùng.

Hãy retry exception cụ thể, đặt giới hạn hữu hạn và cân nhắc backoff. Không retry mọi RuntimeException vì lỗi lập trình, lỗi SQL hoặc dữ liệu sai thường không tự biến mất.

## 8. Write skip khi một item làm hỏng cả chunk

Write skip cho phép bỏ qua một item gây lỗi ghi nếu nghiệp vụ chấp nhận loại item đó.

Ví dụ:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(DuplicateOrderException.class)
        .skipLimit(20)
        .build();
~~~

Vì writer thường nhận cả chunk, framework có thể không biết ngay item nào gây lỗi. Với write skip, Spring Batch có thể rollback lần ghi thất bại rồi thử lại writer với các tập item nhỏ hơn để xác định item gây lỗi.

Minh họa:

~~~text
Writer nhận [A, B, C, D]
          |
          v
Ghi chunk thất bại
          |
          v
Rollback lần ghi
          |
          v
Cô lập item gây lỗi
          |
          +--> A ghi được
          +--> B lỗi -> skip
          +--> C ghi được
          +--> D ghi được
          |
          v
Chunk tiếp tục theo policy
~~~

Đây là mô hình khái niệm. Số lần gọi writer và cách chia nhóm phụ thuộc cơ chế fault-tolerant, loại writer và phiên bản Spring Batch.

Vì writer có thể được gọi lại với các tập item khác nhau, nó phải có transaction semantics rõ ràng và tránh side effect không idempotent.

## 9. Retry và skip có thể được kết hợp

Một exception có thể vừa retryable vừa skippable. Framework có thể thử lại trước; nếu retry hết giới hạn, item chỉ được skip nếu exception cũng được phép skip và skip limit chưa bị vượt.

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

Hãy phân loại lỗi theo nguyên nhân:

| Lỗi writer | Hướng xử lý |
|---|---|
| Deadlock | Retry có giới hạn |
| Kết nối database tạm thời bị mất | Retry hoặc fail sau giới hạn |
| Một item vi phạm constraint do dữ liệu | Skip nếu nghiệp vụ cho phép |
| SQL sai hoặc schema không tương thích | Fail |
| Database hết dung lượng | Fail và xử lý sự cố hạ tầng |
| Không xác định được item lỗi trong batch ngoài | Fail hoặc dùng quy trình đối soát riêng |

Không skip lỗi hạ tầng diện rộng chỉ để Job hoàn tất. Database không ghi được là vấn đề của toàn Step, không phải một item riêng lẻ có thể loại bỏ an toàn.

## 10. Ghi nhận item bị skip

SkipListener cung cấp callback riêng cho lỗi đọc, xử lý và ghi:

~~~java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable exception);
    void onSkipInProcess(I item, Throwable exception);
    void onSkipInWrite(O item, Throwable exception);
}
~~~

Ví dụ ghi nhận item bị lỗi khi writer:

~~~java
@Component
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository repository;

    public OrderSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        // Ghi nhận lỗi đọc nếu có source metadata.
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        // Ghi nhận lỗi xử lý.
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        repository.save(
                RejectedOrder.from(item, exception.getMessage()));
    }
}
~~~

Nếu rejected record được ghi vào cùng database và transaction manager với Step, nó có thể tham gia transaction thích hợp của quá trình skip. Nếu listener gửi email hoặc gọi API, tác động đó không tự rollback cùng database.

Nên lưu business key, exception type, thông tin nguồn và JobExecution/StepExecution liên quan. Hạn chế lưu payload nhạy cảm hoặc stack trace lớn trong bảng rejected.

## 11. File writer và ghi một phần

File thông thường không tham gia transaction JDBC. Nếu writer ghi một số dòng rồi ném exception, rollback database không tự xóa các dòng đã ghi vào file.

~~~text
Chunk bắt đầu
    |
    v
Ghi dòng A vào file
    |
    v
Ghi dòng B vào file
    |
    v
Ghi dòng C thất bại
    |
    v
Database transaction rollback
    |
    v
File có thể vẫn chứa A và B
~~~

Với FlatFileItemWriter, Spring Batch cung cấp cơ chế transactional buffering để phối hợp output với transaction của chunk khi cấu hình phù hợp. Hãy dùng writer dựng sẵn và kiểm tra các tùy chọn transactional, saveState và restart thay vì tự giả định stream file có thể rollback.

Với custom file writer, có thể dùng các chiến lược:

- Ghi vào file tạm theo JobExecution hoặc partition.
- Chỉ publish/đổi tên thành file chính khi Job hoàn tất.
- Lưu checkpoint và vị trí ghi để khôi phục.
- Truncate phần chưa commit khi restart nếu thiết kế cho phép.
- Có bước kiểm tra và đối soát output sau lỗi.

Không nên mở file với chế độ truncate mỗi lần writer được gọi nếu cần ghi nhiều chunk. Cũng không nên đóng file sau mỗi chunk nếu writer được quản lý theo ItemStream lifecycle.

## 12. HTTP API, message broker và side effect bên ngoài

Khi writer gửi dữ liệu tới API hoặc broker, transaction database của Step không tự động điều khiển transaction của hệ thống đích.

Ví dụ:

~~~text
Writer xử lý chunk
       |
       +--> API nhận order A thành công
       |
       +--> API nhận order B thành công
       |
       +--> API order C timeout
       |
       v
Chunk thất bại
       |
       v
Database rollback
       |
       v
API có thể vẫn giữ A và B
~~~

Nếu framework retry chunk, request A và B có thể được gửi lại. Nếu API không hỗ trợ idempotency, hệ thống đích có thể tạo bản ghi hoặc tác động trùng.

Các biện pháp bảo vệ:

- Dùng idempotency key ổn định theo business key.
- Yêu cầu hệ thống đích nhận diện request đã xử lý.
- Ghi yêu cầu gửi ra vào outbox trong cùng transaction với dữ liệu nghiệp vụ.
- Worker riêng đọc outbox và gửi request.
- Lưu external request ID và trạng thái phản hồi để đối soát.
- Thiết kế thao tác bù trừ nếu không thể tránh side effect một phần.

Không thể bảo đảm exactly-once giữa database và một API tùy ý chỉ bằng cách gọi HTTP trong ItemWriter.

## 13. Transactional outbox cho writer nhiều đích

Nếu dữ liệu nghiệp vụ cần được lưu database và sau đó gửi sang hệ thống khác, outbox giúp lưu yêu cầu gửi trong cùng transaction.

~~~text
Transaction chunk
       |
       +--> INSERT order
       |
       +--> INSERT outbox_event
       |
       v
     COMMIT
       |
       v
Outbox worker đọc event chưa gửi
       |
       v
Gửi tới hệ thống ngoài
       |
       v
Đánh dấu event đã xử lý
~~~

Nếu transaction rollback, cả order và outbox event đều rollback. Nếu commit thành công rồi JVM dừng, event vẫn còn trong database để worker xử lý sau.

Outbox không tự bảo đảm exactly-once ở hệ thống đích. Worker có thể gửi lại nếu không nhận được xác nhận hoặc crash trước khi cập nhật trạng thái. Vì vậy, hệ thống đích vẫn nên hỗ trợ idempotency hoặc nhận diện event ID.

## 14. Composite writer và nhiều delegate

Một composite writer có thể ghi cùng chunk tới nhiều đích:

~~~text
Composite ItemWriter
       |
       +--> JDBC writer
       |
       +--> File writer
       |
       +--> HTTP writer
~~~

Nếu JDBC writer ghi thành công rồi file writer thất bại:

- Thay đổi JDBC có thể rollback nếu tham gia transaction chunk.
- File có thể giữ nội dung đã ghi nếu không có transactional buffering.
- HTTP request đã thành công có thể không thể thu hồi.
- Delegate dùng transaction riêng có thể đã commit độc lập.

Composite writer không tự biến các delegate thành một distributed transaction. Hãy xác định thứ tự gọi, tài nguyên được sở hữu và transaction semantics của từng delegate.

Nếu các đích phải nhất quán, cân nhắc ghi vào một nguồn transactional trước rồi dùng outbox hoặc quy trình publish riêng. Tránh ghi trực tiếp nhiều tài nguyên độc lập rồi giả định một rollback sẽ hoàn tác tất cả.

## 15. Listener nào giúp quan sát lỗi ghi?

Một số listener hữu ích:

- ItemWriteListener.onWriteError: được gọi khi writer ném exception.
- ChunkListener.afterChunkError: quan sát nhánh lỗi của chunk sau rollback.
- SkipListener.onSkipInWrite: ghi nhận item bị skip khi ghi.
- StepExecutionListener.afterStep: tổng hợp kết quả Step.

Ví dụ:

~~~java
@Component
public class OrderWriteListener
        implements ItemWriteListener<Order> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderWriteListener.class);

    @Override
    public void beforeWrite(Chunk<? extends Order> items) {
        log.debug("Writing {} orders", items.size());
    }

    @Override
    public void afterWrite(Chunk<? extends Order> items) {
        log.debug("Writer returned for {} orders", items.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> items) {
        log.error(
                "Writer failed for chunk with {} items",
                items.size(),
                exception);
    }
}
~~~

afterWrite chỉ cho biết lời gọi writer trả về thành công. Nó không chứng minh transaction đã commit. Nếu transaction commit thất bại sau đó, chunk vẫn có thể rollback.

Nên gắn JobExecution ID, StepExecution ID, partition name và business key vào log để xác định chính xác chunk hoặc worker gặp lỗi.

## 16. Theo dõi rollback và kết quả ghi

StepExecution cung cấp các counter hữu ích:

| Counter | Ý nghĩa |
|---|---|
| writeCount | Số item được ghi theo thống kê Step |
| writeSkipCount | Số item bị skip ở giai đoạn ghi |
| commitCount | Số lần commit được ghi nhận |
| rollbackCount | Số lần rollback được ghi nhận |
| readCount | Số item đọc thành công theo thống kê |
| filterCount | Số item bị processor lọc |
| status | Trạng thái thực thi Step |
| exitStatus | Mã kết quả của Step |

Có thể tổng hợp sau Step:

~~~java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    log.info(
            "Step result: writes={}, writeSkips={}, commits={}, rollbacks={}",
            stepExecution.getWriteCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount());

    return stepExecution.getExitStatus();
}
~~~

Counter giúp phát hiện nhiều lần rollback, write skip tăng bất thường hoặc Step hoàn tất với số item ghi thấp hơn dự kiến. Để biết nguyên nhân, cần kết hợp counter với exception log và business key.

Không nên suy luận rằng writeCount bằng số câu lệnh SQL đã commit nếu writer ghi nhiều bảng hoặc có side effect ngoài transaction. Counter là số liệu thực thi của Step, không thay thế đối soát dữ liệu đích.

## 17. Kiểm thử writer ghi một phần rồi thất bại

Một integration test nên chạy Step với database transactional và xác nhận các thay đổi đã thực hiện trước exception không còn sau rollback.

Ví dụ minh họa:

~~~java
@Test
void rollsBackEarlierWritesWhenWriterFailsMidChunk() {
    ItemWriter<Order> failingWriter = chunk -> {
        jdbcTemplate.update(
                "INSERT INTO orders(id, order_number) VALUES (?, ?)",
                1L, "ORD-A");

        jdbcTemplate.update(
                "INSERT INTO orders(id, order_number) VALUES (?, ?)",
                2L, "ORD-B");

        throw new OrderWriteException("Failure after two inserts");
    };

    JobExecution execution = launchStepWith(failingWriter);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    assertEquals(0, countOrders());
}
~~~

Test này giả định jdbcTemplate dùng cùng DataSource và transaction manager với Step, các lệnh insert không tự commit, và exception dẫn tới rollback. Sau khi Job kết thúc, truy vấn bằng connection độc lập để xác nhận dữ liệu không tồn tại.

Không nên bọc test bằng một transaction ngoài khiến kết quả kiểm tra bị ảnh hưởng bởi transaction test. Hãy quan sát database sau khi transaction của Step đã kết thúc.

### Các trường hợp nên kiểm thử

- Writer lỗi trước khi ghi item đầu tiên.
- Writer ghi một phần rồi ném exception.
- Writer ghi thành công nhưng transaction commit thất bại.
- Deadlock được retry rồi thành công.
- Retry hết giới hạn.
- Write skip xác định được item lỗi.
- Skip limit bị vượt.
- Writer ghi file và thất bại giữa chừng.
- Writer gọi API và bị retry.
- Composite writer có delegate thất bại ở giữa.
- Job restart sau rollback và khôi phục checkpoint đúng.

## 18. Kiểm thử writer có side effect ngoài transaction

Với file hoặc API, test cần chứng minh rollback database không tự thu hồi side effect bên ngoài.

Ví dụ dùng mock API client:

~~~java
@Test
void externalRequestCanRemainAfterDatabaseRollback() {
    when(shippingClient.createShipment(any()))
            .thenReturn("TRACK-001");

    // Chạy Step: API được gọi, sau đó writer/database thất bại.
    JobExecution execution = launchJobWithFailingWriter();

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    verify(shippingClient).createShipment(any());
    assertEquals(0, countCommittedOrders());
}
~~~

Test minh họa rằng API có thể đã nhận request dù dữ liệu database rollback. Trong ứng dụng thực tế, cần bổ sung test cho idempotency key hoặc outbox để bảo đảm lần restart không tạo vận đơn trùng.

## 19. Những lỗi thường gặp

### Nghĩ rằng writer ghi được một phần thì database giữ phần đó

Nếu tất cả thao tác tham gia cùng transaction và rollback thành công, phần ghi trước exception cũng được hoàn tác. Chỉ các thao tác đã commit độc lập hoặc nằm ngoài transaction mới có thể còn lại.

### Writer bắt exception rồi trả về bình thường

Framework có thể coi write thành công và commit. Hãy truyền exception ra ngoài khi thao tác ghi thất bại.

### Tự commit từng item

Các transaction độc lập đã commit không thể được transaction chunk bên ngoài rollback. Dùng hạ tầng Spring JDBC để tham gia transaction hiện tại.

### Nghĩ file và HTTP API rollback cùng database

File thông thường và API ngoài không tự động tham gia transaction JDBC. Dùng transactional buffering, staging, idempotency hoặc outbox.

### Retry writer không idempotent

Writer có thể được gọi lại sau rollback hoặc khi framework cô lập item lỗi. Side effect có thể bị lặp.

### Dùng skip cho lỗi hạ tầng diện rộng

Database down hoặc hết dung lượng không phải lỗi riêng của một item. Skip có thể làm mất dữ liệu trên diện rộng.

### Dùng noRollback để giữ phần ghi dở

noRollback thay đổi rollback classification, không sửa trạng thái một phần. Nếu writer đã ghi một số item rồi ném exception, transaction có thể commit kết quả không mong muốn.

### Nhầm afterWrite với commit thành công

afterWrite xảy ra sau lời gọi writer nhưng trước khi chunk transaction hoàn tất. Dữ liệu vẫn có thể rollback sau callback.

### Không kiểm tra commit failure

Mất kết nối trong lúc commit có thể khiến client không biết chắc transaction đã được xác nhận hay chưa. Writer cần có business key và tính idempotent.

## 20. Quy trình xử lý lỗi ghi một phần

Khi writer thất bại, hãy lần theo các điểm sau:

1. Exception xảy ra bên trong write() hay trong lúc transaction commit?
2. Writer đã thực hiện những thao tác nào trước khi lỗi?
3. Những thao tác đó dùng cùng transaction manager và resource với Step không?
4. Writer có tự mở connection hoặc commit transaction riêng không?
5. Exception có được truyền ra ngoài writer không?
6. Rollback policy có yêu cầu rollback cho exception đó không?
7. Lỗi có thể retry an toàn không và retry limit là bao nhiêu?
8. Nếu retry hết giới hạn, item có được phép skip không?
9. Write skip có thể xác định chính xác item lỗi không?
10. Writer có side effect ngoài transaction cần idempotency không?
11. File hoặc API có cần staging, outbox hay đối soát không?
12. StepExecution counter và log có đủ để xác định chunk lỗi không?
13. Sau restart, reader/writer có khôi phục từ checkpoint phù hợp không?

Khi writer dùng tài nguyên transactional đúng cách và exception được truyền tới Spring Batch, rollback có thể hoàn tác toàn bộ thay đổi của chunk trên tài nguyên đó, kể cả phần đã ghi trước khi lỗi. Với file, API hoặc hệ thống độc lập, cần thêm cơ chế transactional buffer, staging, idempotency, outbox hoặc đối soát. Phân biệt rõ write failure, commit failure và side effect ngoài transaction là nền tảng để Job có thể retry, skip hoặc restart mà không tạo dữ liệu trùng hay trạng thái dở dang.
