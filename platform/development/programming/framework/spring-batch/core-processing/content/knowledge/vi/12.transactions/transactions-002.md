# Transaction bắt đầu và commit ở đâu?

Trong Spring Batch, transaction được quản lý ở cấp **Step**. Với một Step xử lý theo chunk, Spring Batch thường mở một transaction cho từng chunk: transaction bắt đầu trước khi xử lý chunk, bao gồm các lần đọc, xử lý và ghi của chunk đó, rồi commit khi chunk hoàn tất thành công. Nếu chunk gặp lỗi cần rollback, những thay đổi thuộc transaction sẽ được hoàn tác.

Điều này có nghĩa một Job không chạy trong một transaction duy nhất từ đầu đến cuối. Mỗi Step có ranh giới transaction riêng; với chunk-oriented Step, mỗi chunk là một đơn vị transaction. Các chunk đã commit vẫn được giữ lại nếu một chunk sau thất bại.

Để xác định chính xác transaction bắt đầu và kết thúc ở đâu, cần xem loại Step, chunk size, transaction manager, cách reader/writer sử dụng tài nguyên và cấu hình propagation của các service được gọi trong quá trình xử lý.

## 1. Job không có một transaction bao trùm toàn bộ quy trình

Job có thể gồm nhiều Step. JobLauncher tạo yêu cầu thực thi và Spring Batch lưu metadata về JobExecution, StepExecution trong JobRepository. Sau đó Job điều phối các Step theo flow đã khai báo.

~~~text
JobLauncher
    |
    v
JobRepository: tạo JobExecution
    |
    v
Job bắt đầu
    |
    v
Step A
  transaction của Step A
    |
    v
Step A kết thúc
    |
    v
Step B
  transaction của Step B
    |
    v
Step B kết thúc
    |
    v
Job hoàn tất
~~~

Mỗi Step có thể dùng transaction manager và cấu hình transaction riêng. Khi Step A hoàn tất, các transaction của Step A đã kết thúc trước khi flow chuyển sang Step B. Nếu Step B thất bại, dữ liệu đã commit từ Step A không tự động rollback.

Ví dụ Job nhập đơn hàng:

1. **validateFileStep**: kiểm tra file đầu vào.
2. **importOrdersStep**: ghi các đơn hàng theo chunk.
3. **createSummaryStep**: tạo báo cáo.

Nếu **createSummaryStep** thất bại, các chunk đã commit của **importOrdersStep** vẫn tồn tại. Spring Batch có thể restart Job và tiếp tục theo trạng thái cùng checkpoint đã lưu; nó không mở lại một transaction duy nhất để hoàn tác toàn bộ Job.

Các thao tác quản lý JobExecution và StepExecution trong JobRepository cũng có transaction riêng theo cấu hình repository. Không nên nhầm transaction tạo JobExecution với transaction xử lý dữ liệu của một chunk.

## 2. Chunk-oriented Step: một transaction cho mỗi chunk

Với chunk processing, **chunk(size, transactionManager)** xác định kích thước chunk và transaction manager dùng để quản lý transaction của Step.

Ví dụ:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Với chunk size bằng 100, Spring Batch gom tối đa 100 item cho một đơn vị xử lý trước khi commit. Giả sử nguồn có 250 item:

| Chunk | Item | Transaction |
|---|---:|---|
| Chunk 1 | 1–100 | Transaction 1 |
| Chunk 2 | 101–200 | Transaction 2 |
| Chunk 3 | 201–250 | Transaction 3 |

Chunk cuối có thể nhỏ hơn kích thước đã cấu hình. Nếu chunk 3 thất bại, transaction của chunk 3 có thể rollback; hai transaction trước đã commit vẫn được giữ lại.

### Trình tự một chunk

Ở mức khái niệm, một chunk được thực hiện như sau:

~~~text
Bắt đầu transaction
        |
        v
ItemReader đọc item
        |
        v
ItemProcessor xử lý item
        |
        v
ItemWriter ghi các item
        |
        v
Cập nhật trạng thái ItemStream
và metadata Step
        |
        v
COMMIT transaction
        |
        v
Bắt đầu chunk tiếp theo
~~~

Spring Batch điều phối vòng lặp chunk và transaction. Transaction của chunk được mở trước khi các thao tác đọc/xử lý/ghi của chunk diễn ra. Sau khi writer hoàn tất và framework cập nhật trạng thái cần thiết, transaction được commit.

Nếu có lỗi cần rollback:

~~~text
Bắt đầu transaction
        |
        v
Reader -> Processor -> Writer
                         |
                         v
                    Exception
                         |
                         v
                      ROLLBACK
                         |
                         v
          Retry / Skip / Step thất bại
~~~

Cách reader được gọi lại sau rollback phụ thuộc vào loại reader và chính sách fault-tolerant. Ví dụ, framework có thể buffer item đã đọc trong một số tình huống; reader dựa trên nguồn transactional có thể có hành vi rollback riêng.

## 3. Transaction bắt đầu ở đâu trong chunk Step?

Spring Batch triển khai chunk-oriented Step thông qua **TaskletStep**. TaskletStep sử dụng transaction manager để thực hiện từng lần gọi tasklet trong transaction. Với chunk-oriented Step, phần xử lý chunk được triển khai bên trong tasklet đó.

Có thể hình dung:

1. Step bắt đầu.
2. Spring Batch mở transaction cho lần thực thi chunk.
3. Chunk-oriented tasklet đọc item, gọi processor và writer.
4. Framework cập nhật ExecutionContext và StepExecution.
5. Nếu không có lỗi cần rollback, transaction manager commit.
6. Step tiếp tục vòng lặp với chunk tiếp theo.

Vì vậy, khi hỏi “transaction bắt đầu ở đâu?”, câu trả lời thực tế là: **tại ranh giới thực thi chunk do TaskletStep quản lý**, sử dụng transaction manager được truyền vào cấu hình chunk.

Không cần tự gọi begin() hoặc commit() trong ItemReader, ItemProcessor hay ItemWriter. Nếu các thành phần này sử dụng Spring JDBC hoặc service có transaction propagation phù hợp, chúng sẽ tham gia transaction hiện tại.

## 4. Transaction kết thúc và commit ở đâu?

Transaction kết thúc khi callback xử lý chunk hoàn tất thành công và không có lỗi buộc rollback. Khi đó transaction manager thực hiện commit.

Một số việc xảy ra trước khi commit:

- Reader hoàn tất việc cung cấp item của chunk.
- Processor xử lý các item.
- Writer hoàn tất việc ghi kết quả.
- Các ItemStream cập nhật trạng thái vào ExecutionContext.
- StepExecution cập nhật các counter và trạng thái cần lưu.
- JobRepository lưu metadata thực thi theo transaction configuration.

Nếu mọi thao tác tham gia cùng transaction manager và cùng tài nguyên transactional, dữ liệu nghiệp vụ cùng metadata có thể được commit nhất quán. Nếu chúng nằm ở các database, transaction manager hoặc tài nguyên độc lập, không thể mặc định một commit sẽ xác nhận tất cả.

Sau commit, chunk đó được xem là hoàn tất. Step bắt đầu transaction mới cho chunk tiếp theo.

### Writer hoàn tất chưa có nghĩa transaction đã commit

Một lời gọi ItemWriter.write() trả về thành công chỉ cho biết writer đã hoàn tất lời gọi ghi. Transaction vẫn có thể gặp lỗi trong các bước tiếp theo, chẳng hạn khi cập nhật metadata hoặc trong quá trình commit.

Vì vậy:

- Writer hoàn tất không đồng nghĩa chunk đã commit.
- Flush buffer không đồng nghĩa transaction đã commit.
- Chỉ sau khi transaction commit thành công, các thay đổi thuộc transaction mới được xác nhận.

Đây là điểm quan trọng khi writer ghi file, gọi API hoặc làm việc với tài nguyên không tham gia transaction database.

## 5. Tasklet Step có ranh giới transaction như thế nào?

Tasklet Step cũng được Spring Batch quản lý transaction. Với Tasklet thông thường, mỗi lần gọi **Tasklet.execute()** được thực hiện trong một transaction của Step.

Ví dụ:

~~~java
@Bean
public Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("cleanupStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                // Xóa dữ liệu tạm trong database.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
~~~

Khi Tasklet trả về **RepeatStatus.FINISHED**, Step hoàn tất sau lần gọi đó. Nếu Tasklet trả về **RepeatStatus.CONTINUABLE**, Spring Batch có thể gọi Tasklet tiếp tục; mỗi lần thực thi được quản lý trong transaction theo cấu hình của Step.

Ví dụ Tasklet xử lý công việc theo nhiều lượt:

~~~java
@Bean
public Step rebuildIndexStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        IndexService indexService) {

    return new StepBuilder("rebuildIndexStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                ExecutionContext context = chunkContext
                        .getStepContext()
                        .getStepExecution()
                        .getExecutionContext();

                long lastId = context.getLong("lastId", 0L);
                long nextId = indexService.rebuildNextBatch(lastId, 500);

                if (nextId == lastId) {
                    return RepeatStatus.FINISHED;
                }

                context.putLong("lastId", nextId);
                return RepeatStatus.CONTINUABLE;
            }, transactionManager)
            .build();
}
~~~

Trong ví dụ này, Tasklet xử lý một nhóm dữ liệu trong mỗi lần gọi. Tiến độ được lưu vào Step ExecutionContext. Nếu một lần gọi thất bại, transaction của lần gọi đó có thể rollback. Những lần gọi trước đã commit vẫn được giữ lại.

Nếu Tasklet chỉ thực hiện một thao tác dài duy nhất, không chia thành nhiều lượt, transaction thường kéo dài trong suốt lần gọi execute(). Cần cân nhắc timeout, lock và lượng dữ liệu khi thiết kế.

## 6. Transaction manager quyết định tài nguyên nào được quản lý

Transaction manager là thành phần điều phối transaction của Step. Với ứng dụng JDBC, thường dùng **DataSourceTransactionManager** hoặc **JdbcTransactionManager** gắn với DataSource phù hợp. Với JPA, dùng transaction manager tương ứng với EntityManagerFactory.

Ví dụ cấu hình Step dùng JDBC transaction manager:

~~~java
@Bean
public Step updateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("updateOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(50, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Các thành phần dùng cùng transaction manager và tài nguyên tương ứng có thể tham gia transaction đang mở.

Ví dụ:

- JdbcTemplate dùng cùng DataSource có thể tham gia transaction JDBC hiện tại.
- JPA repository dùng cùng transaction manager JPA có thể tham gia transaction JPA tương ứng.
- Một HTTP client thông thường không tham gia transaction JDBC.
- Ghi file bằng BufferedWriter không tự động được database transaction quản lý.
- Database khác với transaction manager riêng không tự động commit/rollback cùng database chính.

Transaction manager không tự động biến mọi lời gọi Java thành thao tác transactional. Hãy xác định tài nguyên thực tế mà từng thành phần sử dụng.

## 7. JobRepository và transaction của chunk

JobRepository lưu metadata về JobInstance, JobExecution, StepExecution và ExecutionContext. Trong quá trình chunk hoàn tất, Spring Batch cập nhật metadata thực thi và trạng thái stream.

Khi JobRepository và writer dùng cùng database cùng transaction manager, các cập nhật metadata phù hợp có thể tham gia transaction của chunk. Điều này giúp trạng thái nghiệp vụ và checkpoint được xác nhận nhất quán.

Nếu JobRepository sử dụng database hoặc transaction manager khác, cần xem xét cách cấu hình transaction. Hai transaction độc lập không tự động trở thành một transaction phân tán.

Ví dụ tình huống có rủi ro:

~~~text
Transaction A: database nghiệp vụ
  |
  +--> Writer ghi đơn hàng
  |
  +--> COMMIT thành công

Transaction B: JobRepository
  |
  +--> Lưu checkpoint
  |
  +--> COMMIT thất bại
~~~

Khi dữ liệu nghiệp vụ đã commit nhưng checkpoint chưa được lưu, lần restart có thể xử lý lại một phần dữ liệu. Writer cần có chiến lược chống ghi trùng, chẳng hạn unique business key, upsert hoặc idempotency.

Nếu metadata commit nhưng dữ liệu nghiệp vụ ở tài nguyên khác không commit, tình huống cũng cần được xử lý theo kiến trúc transaction đã chọn. Với nhiều tài nguyên, hãy cân nhắc XA/JTA khi thực sự cần distributed transaction, hoặc dùng outbox, idempotency và đối soát khi phù hợp hơn.

## 8. @Transactional bên trong Reader, Processor và Writer

Các service được gọi từ reader, processor hoặc writer có thể sử dụng **@Transactional**. Tuy nhiên, cần hiểu propagation để biết chúng tham gia transaction chunk hay tạo transaction riêng.

### REQUIRED

**Propagation.REQUIRED** là mặc định. Nếu đã có transaction, phương thức tham gia transaction hiện tại; nếu chưa có, Spring tạo transaction mới.

~~~java
@Service
public class OrderService {

    @Transactional
    public void updateOrder(Order order) {
        // Tham gia transaction hiện tại của chunk
        // nếu cùng transaction manager.
    }
}
~~~

Nếu service được gọi từ processor hoặc writer trong cùng luồng thực thi và dùng cùng transaction manager, thao tác thường tham gia transaction chunk. Khi chunk rollback, thay đổi của service cũng được rollback.

### REQUIRES_NEW

**Propagation.REQUIRES_NEW** tạm ngưng transaction hiện tại và tạo một transaction độc lập:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String message) {
        // Transaction độc lập với transaction chunk.
    }
}
~~~

Nếu transaction mới commit thành công, bản ghi audit có thể vẫn tồn tại ngay cả khi chunk bên ngoài rollback. Đây có thể là hành vi mong muốn khi cần lưu dấu vết thử xử lý, nhưng không phù hợp nếu audit phải chỉ phản ánh dữ liệu đã commit.

### NOT_SUPPORTED

**Propagation.NOT_SUPPORTED** tạm ngưng transaction hiện tại khi thực thi phương thức. Những thao tác bên trong không được bảo vệ bởi transaction chunk. Nếu phương thức ghi dữ liệu, thay đổi đó có thể tồn tại dù chunk rollback.

Hãy chọn propagation theo ý nghĩa nghiệp vụ. Đừng dùng REQUIRES_NEW chỉ để tránh lỗi transaction nếu chưa xác định rõ tác động khi chunk thất bại.

Lưu ý: **@Transactional** chỉ được áp dụng theo cơ chế proxy của Spring trong các trường hợp thông thường. Gọi một phương thức transactional khác trong cùng đối tượng qua self-invocation có thể không đi qua proxy, vì vậy không kích hoạt interceptor như mong đợi.

## 9. Isolation, propagation và timeout của Step

Ngoài transaction manager, Step có thể được cấu hình transaction attribute để kiểm soát isolation, propagation và timeout.

Ví dụ:

~~~java
DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();

transactionAttribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);

transactionAttribute.setTimeout(60);

Step step = new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .transactionAttribute(transactionAttribute)
        .build();
~~~

Một số thuộc tính thường gặp:

| Thuộc tính | Tác động |
|---|---|
| Isolation level | Quy định mức cô lập khi đọc/ghi dữ liệu transactional |
| Propagation | Quy định transaction mới hay tham gia transaction hiện tại |
| Timeout | Giới hạn thời gian transaction theo hỗ trợ của transaction manager |
| Read-only | Gợi ý transaction chỉ đọc nếu phù hợp với tài nguyên |

Không nên chọn isolation level cao nhất cho mọi Step. Isolation cao có thể tăng lock contention và giảm khả năng chạy song song. Hãy chọn dựa trên yêu cầu nhất quán dữ liệu và đặc tính truy vấn.

Timeout cũng cần phù hợp với thời gian xử lý một chunk. Nếu chunk quá lớn hoặc writer chậm, transaction có thể vượt timeout. Hãy đo thời gian xử lý thực tế trước khi điều chỉnh.

## 10. Exception nào làm transaction rollback?

Khi có exception trong quá trình xử lý chunk, Spring Batch áp dụng chính sách rollback của Step và cấu hình fault-tolerant.

Các trường hợp thường khiến chunk rollback:

- Reader ném exception không được xử lý.
- Processor ném exception không được skip/retry theo cấu hình.
- Writer ném exception.
- Cập nhật trạng thái stream hoặc metadata gặp lỗi.
- Commit transaction thất bại.

Với Step có retry, framework có thể rollback transaction của lần thử rồi thực hiện lại theo retry policy. Với skip, framework có thể bỏ qua item thuộc loại lỗi được phép và tiếp tục cho tới khi chunk có thể hoàn tất.

Không phải mọi exception đều phải dẫn tới rollback trong mọi cấu hình. Fault-tolerant Step có thể cấu hình loại exception không rollback bằng **noRollback(...)**. Hãy dùng chính sách đó thận trọng, bởi nếu writer đã ghi một phần dữ liệu và transaction không rollback, kết quả có thể không nhất quán.

Ví dụ cấu hình retry và skip:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

Trong ví dụ, lỗi truy cập dữ liệu tạm thời có thể được retry tối đa theo giới hạn; dữ liệu đơn hàng không hợp lệ có thể được skip trong giới hạn cho phép. Nếu vượt giới hạn hoặc gặp lỗi không được xử lý, Step thất bại.

## 11. Reader có nằm trong transaction không?

Lời gọi **ItemReader.read()** diễn ra trong phạm vi xử lý chunk, nhưng điều đó không có nghĩa mọi nguồn đọc đều có thể rollback như database.

Ví dụ:

- Reader dùng JDBC và cùng transaction manager có thể đọc trong transaction database.
- Reader đọc file có thể tăng vị trí đọc của stream; vị trí file không tự động rollback cùng transaction database.
- Reader lấy message từ broker có transaction có thể phối hợp acknowledge/rollback theo cấu hình.
- Reader gọi REST API không thể yêu cầu server từ xa rollback chỉ vì chunk database thất bại.

Với reader có trạng thái, Spring Batch dùng **ItemStream** và **ExecutionContext** để lưu checkpoint. Nếu chunk rollback, trạng thái đọc có thể được khôi phục hoặc item đã đọc được buffer tùy loại reader và cơ chế framework.

Không nên giả định mọi lần gọi read() được hoàn tác vật lý. Hãy kiểm tra reader cụ thể và cách nó quản lý state.

## 12. Writer và transaction: ghi xong chưa chắc đã commit

Nếu writer dùng cùng transaction manager và database với Step, các câu lệnh ghi thường tham gia transaction chunk. Khi transaction rollback, các thay đổi đó được database hoàn tác.

Nhưng nếu writer:

- Ghi file bằng stream thông thường.
- Gửi HTTP request.
- Gửi email.
- Ghi vào database khác.
- Gọi service dùng REQUIRES_NEW.
- Đẩy message sang broker không tham gia transaction.

thì những tác động đó có thể không rollback cùng transaction chunk.

Ví dụ writer gửi request tạo hóa đơn tới API rồi sau đó database rollback. API đã tạo hóa đơn có thể vẫn giữ kết quả. Khi chunk được retry, API có thể nhận request lần nữa.

Cách xử lý thường dùng:

- Dùng idempotency key cho API.
- Ghi yêu cầu tác động ngoài vào outbox trong cùng transaction database.
- Worker riêng đọc outbox và gửi request.
- Dùng unique key hoặc upsert ở hệ thống đích.
- Có cơ chế đối soát khi transaction nhiều tài nguyên không thể atomic.

## 13. Listener chạy ở đâu so với transaction?

Spring Batch có các listener ở cấp Step, chunk, read, process và write. Listener giúp ghi log, thu thập metrics hoặc cập nhật trạng thái vận hành.

Tuy nhiên, không nên suy luận ranh giới transaction chỉ từ tên callback. Một số callback được gọi bên trong transaction, một số callback được gọi sau khi chunk đã hoàn tất. Timing cụ thể phụ thuộc loại listener và lifecycle của Step.

Nếu cần thực hiện một hành động chỉ sau khi transaction commit, hãy dùng cơ chế after-commit phù hợp của Spring transaction hoặc một outbox bền vững. Đừng gửi thông báo quan trọng từ callback mà chưa xác định callback đó có thể được gọi trước rollback hay không.

Ví dụ một transaction synchronization:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Chỉ chạy sau khi transaction hiện tại commit.
            }
        });
~~~

Cơ chế này chỉ hoạt động khi có transaction Spring hiện hành và callback được đăng ký đúng trong transaction đó. Với yêu cầu gửi sự kiện đáng tin cậy qua restart hoặc process crash, outbox thường an toàn hơn một callback trong bộ nhớ.

## 14. Khi nào transaction bị rollback nhưng side effect vẫn còn?

Xét ví dụ Step đọc đơn hàng, gọi API giao hàng và ghi trạng thái vào database:

~~~text
Transaction chunk bắt đầu
        |
        v
Đọc đơn hàng
        |
        v
Gọi API tạo vận đơn
        |
        v
API trả thành công
        |
        v
Ghi trạng thái đơn vào database
        |
        v
Database gặp lỗi
        |
        v
ROLLBACK transaction chunk
~~~

Sau rollback:

- Trạng thái đơn trong database có thể chưa được cập nhật.
- Vận đơn ở hệ thống bên ngoài có thể đã được tạo.
- Khi retry hoặc restart, cùng đơn hàng có thể được xử lý lại.

Đây là lý do không thể dựa vào transaction database để bảo đảm exactly-once cho toàn bộ hệ thống. Hãy thiết kế thao tác ngoài transaction theo hướng idempotent hoặc dùng cơ chế phối hợp phù hợp.

## 15. Kiểm tra transaction boundary bằng log và metrics

Để xác định transaction thực sự bắt đầu và commit ở đâu, có thể bật log cho transaction manager và theo dõi các counter của StepExecution.

Các số liệu thường hữu ích:

| Counter | Ý nghĩa |
|---|---|
| readCount | Số item đã đọc |
| writeCount | Số item đã ghi |
| filterCount | Số item bị processor lọc |
| commitCount | Số transaction chunk đã commit |
| rollbackCount | Số transaction đã rollback |
| readSkipCount | Số item bị skip khi đọc |
| processSkipCount | Số item bị skip khi xử lý |
| writeSkipCount | Số item bị skip khi ghi |

Ví dụ với chunk size 100 và 1.000 item, nếu không có skip/filter và mỗi chunk commit một lần, commitCount thường gần 10. Tuy nhiên, retry, skip, lỗi và cách reader kết thúc có thể ảnh hưởng số counter. Không dùng một phép tính đơn giản để kết luận chính xác transaction đã chạy bao nhiêu lần trong mọi trường hợp.

Log transaction có thể giúp xác định:

- Transaction được mở bởi transaction manager nào.
- Connection nào được gắn vào transaction.
- Service có tham gia transaction hiện tại hay mở transaction mới.
- Commit hoặc rollback xảy ra ở thời điểm nào.
- Có exception trong quá trình commit hay cleanup hay không.

## 16. Những nhầm lẫn thường gặp

### Nghĩ rằng một Job chạy trong một transaction

Job có thể gồm nhiều Step và mỗi Step có ranh giới transaction riêng. Chunk Step có transaction cho từng chunk.

### Nghĩ rằng transaction chỉ bắt đầu khi writer ghi

Transaction chunk được mở trước khi chunk thực hiện các thao tác đọc/xử lý/ghi. Reader và processor có thể tham gia transaction nếu dùng tài nguyên transactional phù hợp.

### Nghĩ rằng writer.write() thành công nghĩa là chunk đã commit

Sau write(), framework còn cập nhật trạng thái stream và metadata, rồi transaction manager mới commit. Lỗi trong giai đoạn sau vẫn có thể làm rollback.

### Nghĩ rằng flush là commit

Flush đẩy dữ liệu khỏi buffer của writer. Commit xác nhận transaction. Hai thao tác có ý nghĩa khác nhau.

### Nghĩ rằng @Transactional(REQUIRES_NEW) rollback cùng chunk

REQUIRES_NEW tạo transaction độc lập. Nếu transaction đó commit, dữ liệu có thể tồn tại dù transaction chunk bên ngoài rollback.

### Nghĩ rằng HTTP request và file write tự động rollback

Các tác động này không tự động tham gia transaction database. Cần idempotency, outbox hoặc cơ chế phối hợp riêng.

### Nghĩ rằng metadata và dữ liệu nghiệp vụ luôn atomic

Chỉ khi chúng thực sự tham gia cùng transaction và tài nguyên phù hợp mới có thể kỳ vọng commit/rollback nhất quán. Hai database độc lập không tự động atomic.

## 17. Quy trình xác định transaction boundary trong một Step

Khi đọc hoặc thiết kế một Step, hãy lần theo các điểm sau:

1. Xác định Step là Tasklet hay chunk-oriented.
2. Với chunk Step, đọc giá trị **chunk(size, transactionManager)**.
3. Xác định transaction manager đang được truyền vào.
4. Kiểm tra Reader, Processor và Writer sử dụng tài nguyên nào.
5. Kiểm tra service được gọi có **@Transactional** và propagation gì.
6. Xác định JobRepository có cùng database và transaction manager với dữ liệu nghiệp vụ không.
7. Kiểm tra retry, skip và noRollback có thay đổi hành vi rollback không.
8. Xác định các side effect ngoài transaction như file, HTTP, email và message.
9. Kiểm tra ExecutionContext/checkpoint được cập nhật ở ranh giới nào.
10. Theo dõi commitCount, rollbackCount và log transaction khi chạy thử.

Nếu nắm rõ các điểm này, bạn có thể trả lời chính xác transaction bắt đầu trước thao tác nào, những tài nguyên nào tham gia, khi nào commit xảy ra và dữ liệu nào còn tồn tại sau rollback.

Với chunk-oriented Step, hãy nhớ rằng **mỗi chunk là một đơn vị transaction do TaskletStep quản lý**. Với Tasklet Step, transaction bao quanh từng lần gọi Tasklet. Toàn bộ Job không được bảo vệ bởi một transaction duy nhất; tính nhất quán giữa các Step, database và hệ thống bên ngoài phải được thiết kế theo ranh giới tài nguyên thực tế.
