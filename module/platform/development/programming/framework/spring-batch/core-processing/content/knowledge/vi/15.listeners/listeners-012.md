# Listener và transaction callback

Trong Spring Batch, **listener** và **transaction callback** đều cho phép ứng dụng phản ứng khi một giai đoạn xử lý xảy ra, nhưng chúng không có cùng vai trò và không chạy ở cùng một thời điểm.

- **Spring Batch listener** quan sát vòng đời Job, Step, chunk hoặc từng item. Ví dụ: beforeStep, afterChunk, afterWrite, onSkipInProcess.
- **Transaction callback** quan sát vòng đời transaction do Spring quản lý. Ví dụ: beforeCommit, afterCommit, afterCompletion.
- **Transactional event listener** nhận application event tại một phase của transaction, chẳng hạn AFTER_COMMIT hoặc AFTER_ROLLBACK.

Điều quan trọng là chọn callback theo thời điểm tác động nghiệp vụ cần xảy ra. Nếu cần ghi log một item vừa được đọc, dùng item listener. Nếu cần gửi thông báo chỉ sau khi dữ liệu database đã commit, dùng after-commit callback hoặc transactional event. Nếu cần bảo đảm sự kiện không bị mất khi tiến trình crash, cân nhắc transactional outbox.

Không phải callback nào có chữ after cũng có nghĩa transaction đã commit. Phải hiểu rõ vị trí callback trong vòng đời chunk và transaction.

## 1. Spring Batch listener là gì?

Listener là các interface hoặc annotation cho phép gắn logic vào những điểm xác định trong quá trình Job và Step chạy. Listener thường được dùng để:

- Ghi log bắt đầu và kết thúc Job/Step.
- Thu thập metrics về số item đọc, xử lý và ghi.
- Ghi nhận item bị skip.
- Quan sát lỗi đọc, xử lý hoặc ghi.
- Cập nhật ExitStatus của Step.
- Ghi trạng thái vận hành hoặc phát sự kiện.

Các listener phổ biến:

| Listener | Phạm vi quan sát |
|---|---|
| **JobExecutionListener** | Trước và sau một JobExecution |
| **StepExecutionListener** | Trước và sau một StepExecution |
| **ChunkListener** | Trước/sau chunk và khi chunk gặp lỗi |
| **ItemReadListener** | Trước/sau mỗi lần đọc và khi đọc lỗi |
| **ItemProcessListener** | Trước/sau mỗi item được xử lý và khi xử lý lỗi |
| **ItemWriteListener** | Trước/sau một lần ghi chunk và khi ghi lỗi |
| **SkipListener** | Khi một item bị bỏ qua theo skip policy |

Listener của Spring Batch giúp gắn logic quan sát vào đúng giai đoạn, nhưng bản thân việc triển khai một listener không tự tạo ra transaction mới. Callback thường chạy trong transaction đang được Step quản lý hoặc ở ngoài transaction, tùy loại listener.

## 2. Transaction callback là gì?

Spring transaction cung cấp callback để ứng dụng biết transaction đang ở giai đoạn nào.

| Phase | Thời điểm |
|---|---|
| **beforeCommit** | Ngay trước khi transaction được commit |
| **beforeCompletion** | Trước khi transaction hoàn tất, dù commit hay rollback |
| **afterCommit** | Sau khi commit thành công |
| **afterCompletion** | Sau khi transaction hoàn tất, có thể committed, rolled back hoặc unknown |

Transaction callback phù hợp khi logic cần phụ thuộc trực tiếp vào kết quả commit/rollback của transaction hiện tại. Ví dụ: chỉ phát thông báo khi dữ liệu đã commit, xóa cache sau khi transaction thành công, ghi nhận trạng thái cuối cùng hoặc cleanup dù transaction commit hay rollback.

Các callback này thuộc Spring transaction infrastructure, không phải Spring Batch listener. Một Step có thể sử dụng cả hai cơ chế: Batch listener để quan sát tiến trình, transaction callback để phản ứng theo kết quả transaction.

## 3. Không phải mọi callback after đều chạy sau commit

Trong chunk-oriented Step, một chunk thường được xử lý trong transaction riêng. Một số callback được gọi khi transaction vẫn đang hoạt động; một số callback chỉ được gọi sau khi transaction đã hoàn tất.

~~~text
Bắt đầu transaction của chunk
        |
        v
ChunkListener.beforeChunk
        |
        v
ItemReadListener
        |
        v
ItemProcessListener
        |
        v
ItemWriteListener.beforeWrite
        |
        v
ItemWriter.write
        |
        v
ItemWriteListener.afterWrite
        |
        v
Cập nhật stream / checkpoint / metadata
        |
        v
Transaction commit
        |
        v
ChunkListener.afterChunk
        |
        v
Chunk tiếp theo
~~~

Nếu chunk thất bại và transaction rollback, Spring Batch có thể gọi các callback xử lý lỗi tương ứng, bao gồm afterChunkError.

Các quy tắc cần nhớ:

- **ItemWriteListener.afterWrite** được gọi sau lời gọi writer thành công, nhưng vẫn trước khi transaction chunk commit.
- **ChunkListener.afterChunk** được gọi sau khi chunk đã commit thành công.
- **ChunkListener.afterChunkError** được gọi sau khi chunk rollback.
- **SkipListener** được gọi ở giai đoạn ngay trước khi transaction commit để có thể sử dụng tài nguyên transactional.
- **StepExecutionListener.afterStep** và **JobExecutionListener.afterJob** là callback vòng đời Step/Job; không nên mặc định chúng nằm trong transaction chunk.

Nếu cần thực hiện hành động chỉ sau commit, đừng dùng afterWrite chỉ vì tên phương thức có chữ after. Hãy dùng afterChunk hoặc transaction callback phù hợp với yêu cầu, đồng thời xem xét khả năng mất sự kiện sau commit.

## 4. Item listener chạy trong giai đoạn nào?

Item listeners quan sát từng thao tác của pipeline.

### ItemReadListener

Các callback:

- **beforeRead()**: trước khi reader được gọi.
- **afterRead(item)**: sau khi reader trả về một item.
- **onReadError(exception)**: khi reader ném exception.

~~~java
@Component
public class CustomerReadListener
        implements ItemReadListener<RawCustomer> {

    private static final Logger log =
            LoggerFactory.getLogger(CustomerReadListener.class);

    @Override
    public void beforeRead() {
        log.debug("About to read a customer");
    }

    @Override
    public void afterRead(RawCustomer item) {
        log.debug("Read customer id={}", item.id());
    }

    @Override
    public void onReadError(Exception ex) {
        log.error("Customer read failed", ex);
    }
}
~~~

Reader được gọi trong quá trình xử lý chunk. Các callback đọc thường nằm trong phạm vi transaction của chunk, nếu Step đang dùng transaction. Tuy nhiên, việc reader đọc file hoặc gọi API không làm nguồn bên ngoài tự động trở thành tài nguyên transactional.

### ItemProcessListener

Các callback:

- **beforeProcess(item)**: trước khi gọi processor.
- **afterProcess(item, result)**: sau khi processor trả về.
- **onProcessError(item, exception)**: khi processor ném exception.

~~~java
@Component
public class CustomerProcessListener
        implements ItemProcessListener<RawCustomer, Customer> {

    @Override
    public void beforeProcess(RawCustomer item) {
        // Có thể ghi log hoặc bắt đầu đo thời gian.
    }

    @Override
    public void afterProcess(RawCustomer item, Customer result) {
        // result có thể null nếu item bị filter.
    }

    @Override
    public void onProcessError(RawCustomer item, Exception ex) {
        // Ghi nhận lỗi xử lý.
    }
}
~~~

Nếu processor trả về null, afterProcess vẫn được gọi với kết quả null. Điều này không đồng nghĩa item bị skip do exception; filter và skip là hai hành vi khác nhau.

### ItemWriteListener

Các callback:

- **beforeWrite(chunk)**: trước khi gọi writer.
- **afterWrite(chunk)**: sau khi writer trả về thành công.
- **onWriteError(exception, chunk)**: khi writer ném exception.

~~~java
@Component
public class CustomerWriteListener
        implements ItemWriteListener<Customer> {

    @Override
    public void beforeWrite(Chunk<? extends Customer> items) {
        // Ghi nhận số item sắp ghi.
    }

    @Override
    public void afterWrite(Chunk<? extends Customer> items) {
        // Writer đã trả về thành công; chunk chưa chắc đã commit.
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Customer> items) {
        // Ghi log lỗi ghi chunk.
    }
}
~~~

afterWrite không phải after-commit callback. Nếu sau đó framework cập nhật metadata hoặc transaction commit gặp lỗi, chunk vẫn có thể rollback. Một hành động bên ngoài được thực hiện trong afterWrite có thể đã xảy ra dù dữ liệu database cuối cùng không được commit.

## 5. ChunkListener và ranh giới transaction

ChunkListener cung cấp ba callback: beforeChunk, afterChunk và afterChunkError.

~~~java
@Component
public class ImportChunkListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportChunkListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        log.info("Chunk started");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.info("Chunk committed successfully");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("Chunk rolled back");
    }
}
~~~

Trong chunk-oriented Step:

- beforeChunk được gọi sau khi transaction bắt đầu và trước khi đọc dữ liệu của chunk.
- afterChunk được gọi sau khi chunk commit thành công.
- afterChunkError được gọi sau khi chunk rollback.

Đây là listener hữu ích để đo số chunk thành công/thất bại hoặc ghi log vận hành. Tuy nhiên, callback sau commit không thể làm cho transaction đã commit quay lại trạng thái rollback. Nếu afterChunk gọi API rồi API thất bại, dữ liệu database của chunk vẫn đã commit. Nếu callback ghi database, thao tác đó cần transaction riêng nếu muốn có commit độc lập.

## 6. SkipListener và thời điểm ghi nhận bản ghi bị bỏ qua

SkipListener được gọi khi một item bị bỏ qua theo cấu hình fault-tolerant của Step.

~~~java
public interface SkipListener<T, S> {

    void onSkipInRead(Throwable t);

    void onSkipInWrite(S item, Throwable t);

    void onSkipInProcess(T item, Throwable t);
}
~~~

Ví dụ ghi nhận item bị skip:

~~~java
@Component
public class CustomerSkipListener
        implements SkipListener<RawCustomer, Customer> {

    private final RejectedCustomerRepository repository;

    public CustomerSkipListener(
            RejectedCustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        // Không có item hợp lệ để lưu nếu reader không tạo được item.
    }

    @Override
    public void onSkipInProcess(RawCustomer item, Throwable t) {
        repository.save(
                RejectedCustomer.from(item, t.getMessage()));
    }

    @Override
    public void onSkipInWrite(Customer item, Throwable t) {
        repository.save(
                RejectedCustomer.from(item, t.getMessage()));
    }
}
~~~

SkipListener được gọi ngay trước khi transaction commit để có thể ghi dữ liệu skip vào tài nguyên transactional. Nếu việc ghi nhận bản ghi lỗi dùng cùng transaction manager và database với Step, dữ liệu skip có thể commit cùng chunk.

Spring Batch có cơ chế bảo đảm SkipListener được gọi một lần cho mỗi item bị skip trong ngữ cảnh xử lý của framework, tránh ghi nhận lặp do một số lần rollback/retry nội bộ. Tuy nhiên, không nên dựa vào listener để tạo exactly-once cho tác động tới hệ thống bên ngoài. Nếu listener gọi API hoặc gửi email, những tác động đó không tự động rollback cùng database.

Nếu onSkipInRead không có item đầu vào do reader không parse được, callback chỉ nhận Throwable. Nếu cần lưu chi tiết dòng nguồn, hãy lấy thông tin từ exception cụ thể, ví dụ line number của FlatFileParseException, hoặc thiết kế reader/listener để cung cấp metadata phù hợp.

## 7. StepExecutionListener và JobExecutionListener

Hai listener này quan sát vòng đời ở cấp cao hơn chunk.

### StepExecutionListener

- **beforeStep(stepExecution)**: trước khi Step thực thi.
- **afterStep(stepExecution)**: sau khi Step kết thúc; có thể trả về ExitStatus bổ sung hoặc tùy chỉnh.

~~~java
@Component
public class ImportStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        stepExecution.getExecutionContext()
                .putString("startedBy", "batch-service");
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getWriteCount() == 0
                && stepExecution.getStatus() == BatchStatus.COMPLETED) {
            return new ExitStatus("NO_DATA");
        }

        return stepExecution.getExitStatus();
    }
}
~~~

afterStep có thể điều chỉnh ExitStatus để flow transition sử dụng mã kết quả nghiệp vụ. Nó không phải callback sau commit của từng chunk và không nên dùng để giả định một transaction chunk vẫn đang mở.

### JobExecutionListener

- **beforeJob(jobExecution)**: trước khi Job chạy.
- **afterJob(jobExecution)**: sau khi Job kết thúc.

~~~java
@Component
public class ImportJobListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportJobListener.class);

    @Override
    public void beforeJob(JobExecution jobExecution) {
        log.info("Job started, executionId={}", jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        log.info(
                "Job finished, executionId={}, status={}",
                jobExecution.getId(),
                jobExecution.getStatus());
    }
}
~~~

Job listener phù hợp để ghi log, cập nhật monitoring hoặc tổng hợp kết quả cuối. Không nên đặt hành động cần tham gia transaction của một chunk vào afterJob, vì lúc đó các transaction chunk đã kết thúc.

## 8. Đăng ký listener với Step hoặc Job

Có thể đăng ký listener khi xây dựng Step:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> reader,
        ItemProcessor<RawCustomer, Customer> processor,
        ItemWriter<Customer> writer,
        ImportChunkListener chunkListener,
        CustomerReadListener readListener,
        CustomerProcessListener processListener,
        CustomerWriteListener writeListener,
        CustomerSkipListener skipListener) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(chunkListener)
            .listener(readListener)
            .listener(processListener)
            .listener(writeListener)
            .listener(skipListener)
            .faultTolerant()
            .skip(InvalidCustomerException.class)
            .skipLimit(100)
            .build();
}
~~~

Đăng ký listener cho Job:

~~~java
@Bean
public Job customerImportJob(
        JobRepository jobRepository,
        Step importCustomersStep,
        ImportJobListener jobListener) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(importCustomersStep)
            .listener(jobListener)
            .build();
}
~~~

Spring Batch hỗ trợ đăng ký listener thông qua builder và annotation tương ứng. Với listener được khai báo bằng annotation, hãy bảo đảm bean được Spring quản lý và nằm trong phạm vi phù hợp. Không cần tự gọi các phương thức listener trong reader hoặc writer; Spring Batch sẽ gọi chúng theo lifecycle khi listener được đăng ký đúng.

## 9. TransactionSynchronization: callback trực tiếp của Spring transaction

Nếu cần biết transaction hiện tại đã commit hay rollback, có thể đăng ký TransactionSynchronization.

~~~java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {

                @Override
                public void beforeCommit(boolean readOnly) {
                    // Transaction sắp commit.
                }

                @Override
                public void afterCommit() {
                    // Transaction đã commit thành công.
                }

                @Override
                public void afterCompletion(int status) {
                    if (status == STATUS_COMMITTED) {
                        // Transaction hoàn tất với kết quả commit.
                    } else if (status == STATUS_ROLLED_BACK) {
                        // Transaction hoàn tất với kết quả rollback.
                    }
                }
            });
}
~~~

Các callback quan trọng:

- **beforeCommit**: transaction sắp commit; vẫn có thể rollback nếu commit không thành công.
- **beforeCompletion**: transaction chuẩn bị hoàn tất, dù commit hay rollback.
- **afterCommit**: chỉ chạy khi commit thành công.
- **afterCompletion**: chạy sau khi transaction hoàn tất và cung cấp trạng thái kết thúc.

Nên kiểm tra isSynchronizationActive() trước khi đăng ký. Nếu không có synchronization đang hoạt động, callback không thể được gắn vào transaction như mong muốn.

### afterCommit không thể rollback dữ liệu đã commit

Khi afterCommit được gọi, transaction chính đã commit. Nếu callback gọi API và API lỗi, transaction database đã hoàn tất; không thể rollback lại dữ liệu đã commit.

Nếu callback cần ghi thêm dữ liệu database và muốn thao tác đó được commit độc lập, hãy gọi một service có @Transactional(propagation = Propagation.REQUIRES_NEW) phù hợp. Tài nguyên của transaction trước có thể vẫn được giữ trong quá trình callback; một transaction mới giúp tạo ranh giới commit riêng.

Không nên thực hiện công việc nặng hoặc chờ hệ thống ngoài quá lâu ngay trong callback đồng bộ sau commit. Điều đó có thể kéo dài thời gian hoàn tất request hoặc luồng xử lý.

## 10. @TransactionalEventListener

Spring cung cấp @TransactionalEventListener để xử lý application event theo phase của transaction.

| Phase | Ý nghĩa |
|---|---|
| **BEFORE_COMMIT** | Xử lý trước khi transaction commit |
| **AFTER_COMMIT** | Xử lý sau khi commit thành công |
| **AFTER_ROLLBACK** | Xử lý sau khi transaction rollback |
| **AFTER_COMPLETION** | Xử lý sau khi transaction hoàn tất, bất kể kết quả |

Ví dụ phát event khi xử lý đơn hàng:

~~~java
public record OrderImportedEvent(Long orderId) {
}
~~~

Service phát event trong transaction:

~~~java
@Service
public class OrderImportService {

    private final ApplicationEventPublisher eventPublisher;
    private final OrderRepository orderRepository;

    public OrderImportService(
            ApplicationEventPublisher eventPublisher,
            OrderRepository orderRepository) {
        this.eventPublisher = eventPublisher;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void importOrder(Order order) {
        orderRepository.save(order);

        eventPublisher.publishEvent(
                new OrderImportedEvent(order.getId()));
    }
}
~~~

Listener chỉ nhận event sau khi transaction commit:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderImported(OrderImportedEvent event) {
        // Gửi thông báo sau khi dữ liệu đơn hàng đã commit.
    }
}
~~~

Mặc định, @TransactionalEventListener sử dụng phase AFTER_COMMIT. Nếu event được phát ra khi không có transaction đang hoạt động, listener thường không được gọi. Có thể cấu hình fallbackExecution = true nếu muốn listener vẫn chạy trong trường hợp đó, nhưng phải hiểu rằng lúc này không có transaction để ràng buộc thời điểm thực thi.

Chọn phase theo mục tiêu:

- **BEFORE_COMMIT**: kiểm tra hoặc bổ sung công việc cần hoàn tất trước khi commit; exception có thể khiến transaction không commit.
- **AFTER_COMMIT**: gửi thông báo hoặc cập nhật cache sau khi dữ liệu đã được xác nhận.
- **AFTER_ROLLBACK**: ghi nhận hoặc kích hoạt xử lý khi transaction thất bại.
- **AFTER_COMPLETION**: cleanup cần chạy dù transaction commit hay rollback.

Không dùng AFTER_COMPLETION nếu chỉ muốn phản ứng với commit thành công; hãy dùng AFTER_COMMIT hoặc kiểm tra trạng thái completion.

## 11. Listener và transaction callback trong chunk Step

Xét một chunk ghi dữ liệu khách hàng:

~~~text
Transaction chunk bắt đầu
        |
        v
ChunkListener.beforeChunk
        |
        v
ItemReadListener.beforeRead / afterRead
        |
        v
ItemProcessListener.beforeProcess / afterProcess
        |
        v
ItemWriteListener.beforeWrite
        |
        v
ItemWriter.write
        |
        v
ItemWriteListener.afterWrite
        |
        v
SkipListener (nếu có item bị skip)
        |
        v
Cập nhật ItemStream / ExecutionContext
        |
        v
Transaction commit
        |
        +--> TransactionSynchronization.afterCommit
        |
        +--> ChunkListener.afterChunk
        |
        v
Chunk tiếp theo
~~~

Sơ đồ thể hiện thứ tự khái niệm của các giai đoạn quan trọng; không nên coi nó là thứ tự tuyệt đối giữa mọi listener và mọi transaction synchronization trong mọi cấu hình. Các listener lỗi và retry có thể khiến một số callback được gọi nhiều lần.

Điều cần phân biệt:

- Item listeners quan sát thao tác read/process/write.
- SkipListener quan sát item bị skip ở giai đoạn xử lý lỗi.
- ChunkListener quan sát ranh giới chunk.
- TransactionSynchronization quan sát transaction.
- Step/Job listeners quan sát lifecycle cấp cao.

Hãy chọn callback có ranh giới phù hợp thay vì dùng một listener duy nhất cho mọi mục đích.

## 12. Side effect trước commit có thể bị lặp

Giả sử afterWrite gửi email:

~~~java
@Override
public void afterWrite(Chunk<? extends Customer> items) {
    for (Customer customer : items) {
        emailService.sendWelcomeEmail(customer.email());
    }
}
~~~

Trình tự có thể xảy ra:

1. Writer ghi dữ liệu database thành công.
2. afterWrite gửi email thành công.
3. Framework cập nhật metadata.
4. Transaction commit thất bại.
5. Chunk rollback.
6. Job retry hoặc restart và xử lý lại item.
7. Email có thể được gửi lần nữa.

Email không tham gia transaction database nên rollback không thu hồi email đã gửi. Tình huống tương tự xảy ra với HTTP request, gửi message tới broker không transactional, ghi file thông thường hoặc gọi hệ thống ngoài.

Đối với side effect quan trọng, hãy cân nhắc:

- Chỉ phát event sau commit.
- Dùng idempotency key để chống xử lý trùng.
- Ghi outbox record trong cùng transaction với dữ liệu nghiệp vụ.
- Worker riêng đọc outbox và thực hiện tác động ngoài.
- Có cơ chế retry và đối soát khi hệ thống ngoài tạm thời không hoạt động.

## 13. afterCommit và transactional outbox khác nhau thế nào?

afterCommit bảo đảm callback chỉ chạy sau khi transaction hiện tại commit thành công. Tuy nhiên, callback vẫn chạy trong cùng tiến trình ứng dụng. Nếu JVM crash ngay sau commit nhưng trước callback thực hiện xong, tác động bên ngoài có thể bị mất.

Transactional outbox giải quyết vấn đề này bằng cách lưu yêu cầu phát sự kiện trong cùng database transaction với dữ liệu nghiệp vụ.

~~~text
Transaction chunk
       |
       +--> INSERT customer
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
Gửi tới hệ thống bên ngoài
       |
       v
Đánh dấu event đã xử lý
~~~

Nếu transaction rollback, cả customer và outbox event đều rollback. Nếu commit thành công rồi ứng dụng dừng, outbox event vẫn nằm trong database để worker gửi sau khi hệ thống hoạt động lại.

Outbox không tự bảo đảm exactly-once ở hệ thống đích. Worker có thể gửi lại nếu không nhận được xác nhận hoặc crash trước khi đánh dấu hoàn tất. Hệ thống đích vẫn nên hỗ trợ idempotency hoặc nhận diện event ID.

## 14. Exception trong listener ảnh hưởng thế nào?

Tác động của exception phụ thuộc callback xảy ra ở giai đoạn nào.

| Callback | Khi callback ném exception |
|---|---|
| Item listener trong xử lý chunk | Có thể làm chunk thất bại và transaction rollback; fault-tolerant policy có thể ảnh hưởng cách xử lý |
| beforeChunk | Có thể ngăn chunk bắt đầu xử lý bình thường |
| afterWrite | Writer đã trả về nhưng transaction chưa commit; exception có thể làm chunk rollback |
| SkipListener | Có thể làm chunk thất bại và không hoàn tất việc ghi nhận skip |
| afterChunk | Chunk đã commit; exception không thể rollback dữ liệu đã commit |
| afterCommit | Transaction đã commit; exception không thể hoàn tác transaction đó |
| afterStep / afterJob | Không nên dựa vào exception để rollback các chunk đã hoàn tất |

Đối với callback sau commit, hãy xử lý lỗi như lỗi hậu commit: ghi log, retry bằng cơ chế bền vững hoặc chuyển việc sang hàng đợi/outbox. Không giả định ném exception sẽ khiến dữ liệu đã commit quay lại.

Với listener nằm trong chunk, hãy tránh để logging hoặc metrics không quan trọng ném exception làm hỏng dữ liệu nghiệp vụ. Nếu listener cần ghi dữ liệu quan trọng, xác định rõ nó nên tham gia transaction chunk hay có transaction riêng.

## 15. Callback sau commit có transaction đang hoạt động không?

Spring transaction có thể vẫn giữ resource binding trong một phần quá trình callback sau commit để cleanup được thực hiện sau đó. Tuy nhiên, transaction chính đã commit và không có lần commit thứ hai cho những thay đổi được thực hiện trong callback.

Do đó, nếu afterCommit gọi một repository và thao tác đó cần được lưu bền vững, không nên giả định nó tự động được commit cùng transaction vừa hoàn tất. Hãy dùng transaction mới:

~~~java
@Service
public class AuditAfterCommitService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordCommittedOrder(Long orderId) {
        // Ghi audit trong transaction độc lập.
    }
}
~~~

Gọi service qua Spring proxy để propagation được áp dụng. Nếu gọi một phương thức REQUIRES_NEW bằng self-invocation trong cùng bean, proxy có thể không được kích hoạt.

Với tác vụ có thể retry hoặc cần bảo đảm không mất, outbox vẫn là lựa chọn bền vững hơn callback trong bộ nhớ.

## 16. Phân biệt listener callback với @Transactional

@Transactional và listener không phải hai cách gọi khác nhau của cùng một cơ chế.

- **@Transactional** xác định ranh giới transaction cho phương thức được Spring proxy quản lý.
- **Spring Batch listener** được framework gọi tại lifecycle hook của Job/Step/chunk/item.
- **TransactionSynchronization** đăng ký callback với transaction hiện tại.
- **@TransactionalEventListener** xử lý application event theo transaction phase.

Ví dụ service transactional:

~~~java
@Transactional
public void updateCustomer(Customer customer) {
    customerRepository.save(customer);
}
~~~

Nếu phương thức được gọi từ processor trong cùng transaction manager, nó thường tham gia transaction chunk theo propagation mặc định REQUIRED.

Một ItemProcessListener.afterProcess không tự mở transaction chỉ vì nó là listener. Nó chạy trong ngữ cảnh xử lý mà Spring Batch gọi. Nếu listener gọi service transactional, service đó áp dụng propagation theo transaction hiện tại và transaction manager tương ứng.

Tương tự, @TransactionalEventListener không tự tạo một transaction mới cho event. Nó ràng buộc thời điểm xử lý event với transaction đã phát event.

## 17. Kiểm thử listener và transaction callback

Test nên xác nhận callback xảy ra ở đúng thời điểm tương đối với commit/rollback.

### Kiểm thử ItemWriteListener

Có thể dùng Mockito để xác nhận listener được gọi khi writer được thực thi:

~~~java
@Test
void itemWriteListenerReceivesWrittenChunk() throws Exception {
    ItemWriteListener<Customer> listener =
            mock(ItemWriteListener.class);

    Chunk<Customer> chunk =
            new Chunk<>(List.of(customer));

    listener.beforeWrite(chunk);
    listener.afterWrite(chunk);

    verify(listener).beforeWrite(chunk);
    verify(listener).afterWrite(chunk);
}
~~~

Đây chỉ là unit test cho listener interface. Để xác nhận vị trí callback so với transaction, cần chạy Step integration test với transaction manager thực tế và quan sát trạng thái dữ liệu.

### Kiểm thử afterCommit

Có thể đăng ký synchronization trong một transaction test:

~~~java
@Test
void callbackRunsAfterSuccessfulCommit() {
    AtomicBoolean committed = new AtomicBoolean(false);

    transactionTemplate.execute(status -> {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        committed.set(true);
                    }
                });

        assertFalse(committed.get());
        return null;
    });

    assertTrue(committed.get());
}
~~~

Test này xác nhận callback chỉ chạy sau khi transaction template hoàn tất commit thành công.

### Kiểm thử rollback

Tạo một transaction cố ý rollback và xác nhận afterCommit không được gọi, còn afterCompletion nhận trạng thái rollback.

~~~java
@Test
void afterCommitIsNotCalledWhenTransactionRollsBack() {
    AtomicBoolean committed = new AtomicBoolean(false);
    AtomicInteger completionStatus = new AtomicInteger(-1);

    transactionTemplate.execute(status -> {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        committed.set(true);
                    }

                    @Override
                    public void afterCompletion(int status) {
                        completionStatus.set(status);
                    }
                });

        status.setRollbackOnly();
        return null;
    });

    assertFalse(committed.get());
    assertEquals(
            TransactionSynchronization.STATUS_ROLLED_BACK,
            completionStatus.get());
}
~~~

Trong test thực tế, cần dùng transaction manager và transaction template được cấu hình cho cùng DataSource với Step.

## 18. Những lỗi thường gặp

### Dùng afterWrite như afterCommit

afterWrite chạy sau lời gọi writer nhưng trước khi transaction chunk được commit. Side effect trong callback có thể xảy ra rồi chunk rollback.

### Gửi email trong ItemProcessListener

Processor có thể được gọi lại khi retry hoặc rollback. Email đã gửi không tự động được thu hồi. Hãy chuyển side effect sang outbox hoặc xử lý sau commit với cơ chế chống trùng.

### Nghĩ afterChunk có thể rollback chunk

afterChunk được gọi sau khi chunk commit thành công. Exception trong callback không thể rollback transaction đã hoàn tất.

### Nghĩ afterJob nằm trong transaction cuối cùng

afterJob là callback vòng đời Job. Các transaction của Step đã kết thúc; không nên dùng nó để tham gia transaction của chunk.

### Dùng transaction callback khi không có transaction

TransactionSynchronizationManager.registerSynchronization cần synchronization đang hoạt động. Hãy kiểm tra trạng thái trước khi đăng ký và xác định fallback khi callback không thể gắn với transaction.

### Ghi database trong afterCommit nhưng mong nó commit cùng transaction cũ

Transaction cũ đã commit. Nếu cần ghi độc lập, dùng transaction mới. Nếu cần độ tin cậy qua crash, cân nhắc outbox.

### Dùng afterCompletion mà không kiểm tra status

afterCompletion chạy cả khi commit và rollback. Nếu chỉ muốn hành động sau commit, hãy kiểm tra completion status hoặc dùng afterCommit.

### Dựa vào callback để bảo đảm exactly-once với hệ thống ngoài

Callback không thay thế idempotency hoặc transactional outbox. Process crash và lỗi mạng vẫn có thể tạo mất hoặc lặp side effect.

## 19. Chọn đúng callback theo mục tiêu

| Mục tiêu | Cơ chế nên xem xét |
|---|---|
| Log trước/sau Job | JobExecutionListener |
| Thay đổi ExitStatus của Step | StepExecutionListener.afterStep |
| Đếm chunk thành công/thất bại | ChunkListener |
| Quan sát item đọc được | ItemReadListener |
| Quan sát item đã xử lý hoặc bị lỗi | ItemProcessListener |
| Quan sát lần ghi chunk | ItemWriteListener |
| Lưu bản ghi bị skip trong transaction | SkipListener |
| Chạy logic ngay trước commit | TransactionSynchronization.beforeCommit hoặc event BEFORE_COMMIT |
| Chỉ chạy khi commit thành công | TransactionSynchronization.afterCommit hoặc event AFTER_COMMIT |
| Chạy khi transaction rollback | afterCompletion kiểm tra status hoặc event AFTER_ROLLBACK |
| Cleanup sau mọi kết quả transaction | TransactionSynchronization.afterCompletion |
| Phát sự kiện bền vững tới hệ thống ngoài | Transactional outbox |

Không có một callback phù hợp cho mọi trường hợp. Hãy chọn theo câu hỏi: cần quan sát lifecycle nào, callback chạy trước hay sau commit, và tác động được gọi có tham gia transaction hay không?

## 20. Quy trình thiết kế listener an toàn

Khi thêm listener hoặc transaction callback vào một Job, hãy xác định:

1. Listener thuộc cấp Job, Step, chunk hay item?
2. Callback chạy trước writer, sau writer, trước commit hay sau commit?
3. Transaction hiện tại có đang hoạt động khi callback chạy không?
4. Tác động callback thực hiện có dùng cùng transaction manager và tài nguyên không?
5. Nếu chunk rollback, side effect có bị hoàn tác hay có thể bị lặp?
6. Nếu callback sau commit thất bại, ứng dụng có cách retry không?
7. Nếu JVM crash sau commit nhưng trước callback, sự kiện có bị mất không?
8. Có cần idempotency key hoặc transactional outbox không?
9. Listener có thể ném exception làm ảnh hưởng chunk không?
10. Test đã xác nhận callback ở cả nhánh commit và rollback chưa?

Hãy dùng Spring Batch listener để quan sát các mốc của Job, Step, chunk và item. Dùng transaction callback khi logic phụ thuộc vào kết quả commit/rollback của transaction. Với tác động bên ngoài cần độ tin cậy, hãy lưu yêu cầu phát sự kiện trong cùng transaction bằng outbox và xử lý idempotent. Khi phân biệt đúng các lifecycle này, ứng dụng sẽ tránh được tình trạng gửi thông báo trước khi dữ liệu được commit, ghi nhận skip sai thời điểm hoặc giả định một callback có thể rollback dữ liệu đã xác nhận.
