# Không mở transaction kéo dài qua toàn bộ job

Trong Spring Batch, một Job có thể gồm nhiều Step và mỗi Step có thể xử lý một lượng dữ liệu lớn. Không nên mở một transaction duy nhất bao trùm toàn bộ Job rồi giữ transaction đó cho đến khi tất cả Step kết thúc. Cách làm này giữ connection và lock quá lâu, làm tăng chi phí rollback, gây tranh chấp tài nguyên và khiến một lỗi ở cuối quy trình có thể ảnh hưởng đến toàn bộ công việc đã chạy trước đó.

Spring Batch được thiết kế để quản lý transaction ở phạm vi phù hợp với đơn vị xử lý. Với chunk-oriented Step, transaction thường được mở và commit theo từng chunk. Với Tasklet Step, transaction được quản lý cho từng lần gọi `Tasklet.execute()`. Job đóng vai trò điều phối các Step; việc một Job có nhiều Step không có nghĩa toàn bộ Job cần nằm trong một transaction chung.

## 1. Transaction boundary trong Spring Batch

Một transaction xác định nhóm thao tác dữ liệu cần được commit hoặc rollback cùng nhau. Transaction càng kéo dài thì tài nguyên càng bị giữ lâu và phạm vi ảnh hưởng khi rollback càng lớn.

Trong Spring Batch, nên đặt transaction boundary theo đơn vị công việc có thể commit độc lập:

```text
Job: importOrdersJob
  |
  +--> validateInputStep
  |       Transaction của Tasklet / từng lần execute
  |
  +--> importOrdersStep
  |       Chunk 1: BEGIN --> READ/PROCESS/WRITE --> COMMIT
  |       Chunk 2: BEGIN --> READ/PROCESS/WRITE --> COMMIT
  |       Chunk 3: BEGIN --> READ/PROCESS/WRITE --> COMMIT
  |
  +--> archiveFileStep
          Transaction của Tasklet / từng lần execute
```

Các transaction của Step hoặc chunk có thể kết thúc độc lập. Nếu chunk 3 thất bại, những chunk đã commit trước đó vẫn giữ kết quả. Job có thể được restart dựa trên metadata và checkpoint đã lưu, thay vì phải rollback mọi thay đổi của toàn bộ Job.

### Transaction của chunk

Với chunk-oriented processing, Spring Batch gom một số item theo commit interval. Mỗi chunk được thực hiện trong transaction do transaction manager của Step quản lý. Ví dụ, `chunk(500, transactionManager)` tạo transaction theo từng nhóm tối đa 500 item.

```text
Chunk 1: BEGIN -> read/process/write 500 items -> COMMIT
Chunk 2: BEGIN -> read/process/write 500 items -> COMMIT
Chunk 3: BEGIN -> read/process/write 500 items -> ROLLBACK
```

Khi chunk 3 rollback, các thay đổi trong transaction của chunk 3 bị hoàn tác. Dữ liệu từ chunk 1 và 2 đã commit không bị rollback theo. Đây là một trong những lý do chunk processing phù hợp với xử lý dữ liệu lớn.

### Transaction của Tasklet

Với Tasklet Step, `TaskletStep` dùng transaction manager được khai báo cho Step để quản lý từng lần gọi `execute()`. Tasklet thường trả về `RepeatStatus.FINISHED` sau một thao tác. Nếu trả về `CONTINUABLE`, Tasklet có thể được gọi thêm lần nữa; mỗi lần gọi được quản lý theo transaction boundary của TaskletStep.

Một Tasklet thực hiện stored procedure lớn vẫn có thể giữ transaction lâu trong thời gian procedure chạy. Nếu thao tác cần nguyên tử ở cấp toàn bộ procedure, thời gian transaction đó có thể là yêu cầu nghiệp vụ. Tuy nhiên, không nên mở rộng transaction này ra toàn bộ các Step khác trong Job.

## 2. Vì sao không nên mở transaction qua toàn bộ Job?

Một Job có thể chạy vài phút, vài giờ hoặc lâu hơn. Nếu transaction được mở trước khi launch Job và chỉ kết thúc sau khi Job hoàn thành, các tài nguyên database có thể bị giữ trong toàn bộ khoảng thời gian đó.

Những rủi ro thường gặp:

1. **Giữ connection lâu:** một connection bị chiếm dụng trong thời gian Job chạy, làm giảm số connection sẵn có cho request và batch khác.
2. **Giữ lock lâu:** transaction có thể giữ row lock, table lock hoặc các loại lock khác, khiến tiến trình đồng thời phải chờ hoặc bị deadlock.
3. **Tăng chi phí rollback:** nếu lỗi xảy ra ở Step cuối, database có thể phải hoàn tác một lượng lớn thay đổi chưa commit.
4. **Tăng log và vùng undo:** database phải duy trì thông tin cần thiết để rollback và đảm bảo isolation trong thời gian dài.
5. **Tăng nguy cơ timeout:** transaction có thể vượt giới hạn timeout của database, transaction manager hoặc connection pool.
6. **Giảm khả năng phục hồi:** các kết quả trung gian chưa commit không bền vững; tiến trình dừng có thể làm mất toàn bộ thay đổi trong transaction dài.
7. **Tăng tranh chấp giữa các Job:** một batch giữ lock lâu có thể cản trở batch khác hoặc giao dịch online.

Ví dụ, Job nhập một triệu bản ghi với commit interval 500. Nếu transaction bao trùm cả Job, 2.000 chunk về mặt xử lý có thể vẫn nằm trong một transaction lớn. Khi lỗi ở chunk cuối, database có thể phải rollback gần như toàn bộ công việc. Khi transaction được chia theo chunk, mỗi chunk đã commit là một đơn vị kết quả bền vững.

## 3. Tránh đặt @Transactional quanh lời gọi JobLauncher

Một lỗi thiết kế thường gặp là đánh dấu phương thức launch Job bằng `@Transactional`:

```java
@Service
public class BatchLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public BatchLaunchService(
            JobLauncher jobLauncher,
            Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    @Transactional
    public void launch(JobParameters parameters) throws Exception {
        jobLauncher.run(importOrdersJob, parameters);
    }
}
```

Nếu JobLauncher chạy đồng bộ trên cùng thread, transaction được mở ở phương thức bên ngoài có thể vẫn đang hoạt động khi Step bắt đầu. Khi Step dùng cùng transaction manager và propagation mặc định `REQUIRED`, transaction của Step có thể tham gia transaction bên ngoài thay vì tạo boundary độc lập cho từng chunk. Kết quả là các chunk tưởng như đã commit có thể chưa thực sự commit cho đến khi phương thức launch kết thúc.

Hành vi cụ thể phụ thuộc loại JobLauncher (đồng bộ hay bất đồng bộ), transaction manager, propagation và cấu hình repository/Step. Không nên dựa vào giả định rằng lời gọi `JobLauncher.run()` luôn tự tách khỏi transaction đang tồn tại.

### Cách viết phù hợp hơn

Thông thường, phương thức chỉ chịu trách nhiệm launch Job không cần `@Transactional`. Hãy để từng Step quản lý transaction theo cấu hình của nó:

```java
@Service
public class BatchLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public BatchLaunchService(
            JobLauncher jobLauncher,
            Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public JobExecution launch(JobParameters parameters) throws Exception {
        return jobLauncher.run(importOrdersJob, parameters);
    }
}
```

Phương thức này không tự mở transaction bao quanh thời gian chạy Job. Các Step sử dụng transaction manager riêng theo cấu hình Step.

## 4. Cấu hình transaction theo chunk

Với Spring Batch 5 trở lên, truyền `PlatformTransactionManager` vào `StepBuilder` khi khai báo chunk Step:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersJobConfig {

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, Order> orderProcessor,
            ItemWriter<Order> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, Order>chunk(500, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
```

`chunk(500, transactionManager)` chỉ ra transaction manager và commit interval cho Step. Spring Batch thực hiện commit sau mỗi chunk thành công. Nếu một chunk gặp exception cần rollback, transaction của chunk đó được rollback theo policy.

Commit interval nên được lựa chọn theo kích thước item, thời gian xử lý, khả năng chịu tải của database và yêu cầu restart. Interval nhỏ tạo transaction ngắn và giới hạn phạm vi rollback nhưng tăng số lần commit. Interval lớn giảm số lần commit nhưng giữ transaction lâu hơn và tăng số item có thể cần xử lý lại khi lỗi.

## 5. Cấu hình transaction cho Tasklet Step

Tasklet Step cũng cần được cung cấp transaction manager:

```java
@Bean
public Step archiveStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet archiveTasklet) {

    return new StepBuilder("archiveStep", jobRepository)
            .tasklet(archiveTasklet, transactionManager)
            .build();
}
```

Tasklet Step quản lý transaction cho mỗi lần gọi Tasklet. Nếu một Tasklet thực hiện một câu lệnh database ngắn, transaction có thể ngắn và dễ kiểm soát. Nếu Tasklet thực hiện một vòng lặp dài, đọc và cập nhật hàng trăm nghìn bản ghi trong một lần `execute()`, transaction của lần gọi đó vẫn có thể kéo dài.

Trong trường hợp cần xử lý nhiều bản ghi, hãy cân nhắc chuyển sang chunk-oriented Step hoặc chia công việc thành các Step/tasklet nhỏ với ranh giới commit rõ ràng. Nếu một stored procedure cần chạy nguyên tử như một thao tác duy nhất, cần đánh giá thời gian chạy và lock của chính procedure thay vì bọc thêm cả Job vào transaction đó.

## 6. Transaction propagation trong service được gọi từ Step

Một processor, writer hoặc Tasklet có thể gọi service nghiệp vụ có annotation `@Transactional`. Cần hiểu propagation để không vô tình phá vỡ transaction boundary của Step.

### REQUIRED

`Propagation.REQUIRED` là mặc định. Nếu đã có transaction của chunk hoặc Tasklet, lời gọi service thường tham gia transaction đang có. Đây thường là lựa chọn phù hợp khi service thực hiện một thao tác database ngắn thuộc cùng đơn vị công việc của chunk.

```java
@Service
public class OrderUpdateService {

    @Transactional
    public void updateOrder(Order order) {
        // Thao tác database ngắn, tham gia transaction của chunk nếu có.
    }
}
```

### REQUIRES_NEW

`Propagation.REQUIRES_NEW` tạm treo transaction hiện tại và mở một transaction độc lập. Dữ liệu được commit trong transaction mới có thể vẫn tồn tại dù chunk bên ngoài rollback.

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord(AuditRecord record) {
    // Commit độc lập với transaction của chunk gọi phương thức này.
}
```

Chỉ dùng `REQUIRES_NEW` khi thực sự cần tính độc lập đó, ví dụ lưu audit cần tồn tại kể cả khi xử lý nghiệp vụ thất bại. Nếu dùng cho từng bản ghi trong writer mà không có lý do rõ ràng, có thể tạo dữ liệu đã commit một phần và làm phức tạp restart.

### NOT_SUPPORTED

`Propagation.NOT_SUPPORTED` tạm treo transaction hiện tại trong thời gian thực hiện phương thức. Nó có thể hữu ích cho thao tác không nên chạy trong transaction, nhưng cũng đồng nghĩa các thay đổi của thao tác đó không được bảo vệ bởi transaction của chunk. Không nên áp dụng đại trà cho processor hoặc writer.

Không dùng propagation như một cách sửa nhanh cho toàn bộ Job. Hãy xác định rõ thao tác nào cần nguyên tử cùng chunk, thao tác nào có thể commit độc lập và tác động đến khả năng retry/restart.

## 7. JobRepository không yêu cầu một transaction cho toàn bộ Job

`JobRepository` lưu metadata của JobInstance, JobExecution, StepExecution và ExecutionContext. Các thao tác metadata cần được quản lý transaction để trạng thái thực thi không bị ghi dở hoặc mất nhất quán.

Điều đó không có nghĩa toàn bộ Job phải nằm trong một transaction. Metadata của Job và Step được cập nhật tại các điểm phù hợp trong vòng đời thực thi; dữ liệu nghiệp vụ của chunk được quản lý bởi transaction manager của Step.

Nên phân biệt:

| Thành phần | Mục đích |
|---|---|
| Transaction của JobRepository | Lưu metadata thực thi và trạng thái batch một cách nhất quán. |
| Transaction của chunk | Commit hoặc rollback thay đổi nghiệp vụ trong một chunk. |
| Transaction của Tasklet | Quản lý thao tác database trong một lần gọi Tasklet. |
| Transaction nghiệp vụ bên ngoài | Quản lý cập nhật trước/sau khi launch theo yêu cầu riêng của ứng dụng. |

Trong cấu hình phổ biến, repository và dữ liệu nghiệp vụ có thể dùng cùng database nhưng vẫn có các transaction boundary khác nhau. Không nên tự mở một transaction lớn chỉ để bao trùm cả metadata lẫn toàn bộ dữ liệu nghiệp vụ.

## 8. Launch đồng bộ và bất đồng bộ

`JobLauncher` có thể được cấu hình chạy Job đồng bộ hoặc bất đồng bộ. Điều này ảnh hưởng đến thời điểm phương thức gọi Job trả về, nhưng không phải lý do để mở một transaction dài.

- **Synchronous launcher:** phương thức launch chờ Job thực thi xong. Nếu phương thức gọi được đánh dấu `@Transactional`, transaction bên ngoài có thể tồn tại trong suốt thời gian chờ và có thể ảnh hưởng đến transaction của Step nếu dùng cùng transaction manager.
- **Asynchronous launcher:** phương thức launch có thể trả về khi Job mới được gửi cho executor. Transaction bên ngoài của caller thường kết thúc sau khi gửi yêu cầu; nó không tự bao trùm công việc chạy ở thread khác.

Không nên dựa vào asynchronous launcher để thay thế thiết kế transaction đúng. Cần bảo đảm dữ liệu đầu vào và trạng thái yêu cầu đã commit trước khi worker bắt đầu đọc chúng.

### Trường hợp launch sau khi transaction nghiệp vụ commit

Giả sử một API tạo yêu cầu nhập file trong database rồi muốn khởi chạy Job. Nếu launch Job trước khi transaction tạo yêu cầu commit, worker bất đồng bộ có thể bắt đầu đọc dữ liệu khi bản ghi chưa hiển thị.

Một giải pháp là phát tín hiệu launch sau khi transaction commit, hoặc ghi một sự kiện vào transactional outbox trong cùng transaction với yêu cầu. Một worker riêng đọc outbox sau khi commit rồi khởi chạy Job. Cách này tách transaction ngắn của request khỏi transaction xử lý batch.

```text
API request
    |
    v
Transaction ngắn
  - lưu BatchRequest
  - lưu OutboxEvent
    |
    v
COMMIT
    |
    v
Outbox dispatcher
    |
    v
JobLauncher
    |
    v
Job / Step transactions
```

Outbox dispatcher cần có cơ chế chống gửi lặp và Job vẫn cần identifying JobParameters ổn định. Đây là cách phối hợp bền vững giữa transaction của ứng dụng và việc launch Job.

## 9. Giao dịch database và tác dụng phụ bên ngoài

Transaction database không tự động rollback file system, email, HTTP request hoặc message broker nếu các tài nguyên đó không tham gia cùng cơ chế transaction.

Ví dụ, chunk cập nhật đơn hàng trong database rồi gọi HTTP để gửi thông tin sang hệ thống khác. Nếu HTTP thành công nhưng database rollback, hệ thống ngoài vẫn có thể đã nhận thông tin. Khi retry, request có thể được gửi lần nữa.

Các kỹ thuật thường dùng:

1. **Idempotency key:** gắn mã yêu cầu duy nhất để hệ thống nhận không xử lý lặp.
2. **Transactional outbox:** ghi sự kiện cần phát trong cùng transaction với dữ liệu nghiệp vụ, sau đó gửi sau commit.
3. **Compensation:** thực hiện thao tác bù khi không thể rollback hệ thống ngoài.
4. **Phân tách Step:** lưu kết quả database trước, sau đó dùng Step riêng gửi thông điệp với chính sách retry rõ ràng.

Không nên giữ transaction database mở trong lúc chờ một HTTP request chậm nếu thao tác đó không cần tính nguyên tử với database. Thời gian chờ mạng có thể làm connection và lock bị giữ lâu, đồng thời rollback database cũng không thể thu hồi yêu cầu đã được hệ thống ngoài xử lý.

## 10. Thiết kế restart khi transaction chia theo Step hoặc chunk

Khi Job thất bại, Spring Batch lưu metadata để có thể restart cùng JobInstance nếu cấu hình cho phép. Transaction boundary ngắn giúp các phần đã commit trở thành mốc phục hồi rõ ràng.

Ví dụ:

```text
importOrdersJob
  |
  +--> Chunk 1: COMMITTED
  +--> Chunk 2: COMMITTED
  +--> Chunk 3: FAILED / ROLLED BACK
  +--> Chunk 4: chưa chạy

Restart cùng identifying JobParameters
  |
  +--> JobExecution mới
         +--> khôi phục từ checkpoint đã commit
         +--> xử lý lại phần cần thiết
```

Để restart an toàn:

- Dùng cùng identifying JobParameters để xác định đúng JobInstance.
- Dùng reader hỗ trợ lưu trạng thái nếu cần tiếp tục từ checkpoint.
- Thiết kế writer và thao tác nghiệp vụ để chịu được retry hoặc chạy lại.
- Kiểm soát tác dụng phụ ngoài transaction bằng idempotency hoặc outbox.
- Tránh commit độc lập cho từng item nếu điều đó phá vỡ tính nhất quán mong muốn của chunk.

Nếu một Step đã hoàn thành ở lần chạy trước, Spring Batch thường bỏ qua Step đó khi restart, trừ khi Step được cấu hình `allowStartIfComplete(true)`. Chỉ bật tùy chọn này khi thực sự muốn Step chạy lại và logic của Step an toàn khi thực hiện nhiều lần.

## 11. Cách nhận biết transaction đang kéo dài quá lâu

Khi điều tra hiệu năng hoặc lock contention, nên quan sát cả application và database:

| Dấu hiệu | Điều cần kiểm tra |
|---|---|
| Connection pool cạn trong lúc Job chạy | Connection bị giữ bao lâu, có transaction bên ngoài bao quanh launcher không. |
| Lock tồn tại đến cuối Job | Transaction nào đang giữ lock, Step/chunk nào chưa commit. |
| Rollback mất nhiều thời gian | Kích thước transaction và số thay đổi chưa commit. |
| Deadlock tăng khi batch chạy song song | Thứ tự cập nhật, phạm vi lock và transaction duration. |
| Transaction timeout | Timeout của database, transaction manager và connection pool. |
| Chunk đã xử lý nhưng chưa thấy dữ liệu commit | Có transaction bên ngoài đang bao bọc Job hoặc Step không. |

Có thể ghi log thời gian bắt đầu/kết thúc của Step và chunk, theo dõi transaction duration ở database, connection pool active count, lock wait và deadlock. Không nên chỉ tăng timeout để che một transaction có phạm vi quá lớn.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đặt `@Transactional` trên phương thức gọi `JobLauncher.run()` | Transaction bên ngoài có thể bao trùm Job đồng bộ và làm các Step join cùng transaction. | Để phương thức launch không transactional; cấu hình transaction tại Step. |
| Dùng một Tasklet để xử lý hàng triệu item trong một lần gọi | Transaction Tasklet có thể kéo dài và khó restart. | Chuyển sang chunk hoặc chia thành các đơn vị nhỏ có checkpoint. |
| Dùng `REQUIRES_NEW` cho mọi item | Dữ liệu có thể commit một phần dù chunk rollback. | Chỉ dùng khi cần transaction độc lập có chủ đích. |
| Gọi HTTP trong transaction chunk rồi chờ lâu | Giữ connection/lock trong lúc chờ; HTTP không tự rollback cùng database. | Dùng outbox, idempotency hoặc Step gửi thông điệp riêng. |
| Nghĩ JobRepository cần transaction toàn Job | Phạm vi transaction metadata bị hiểu nhầm với transaction nghiệp vụ. | Để repository và Step quản lý metadata/transaction theo cơ chế Spring Batch. |
| Dùng transaction dài để bảo đảm toàn bộ Job all-or-nothing | Rollback rất lớn và không thể bao trùm file/API nếu không có distributed transaction. | Chia transaction theo đơn vị nghiệp vụ và thiết kế restart/compensation. |

## Kết luận

Không nên mở một transaction duy nhất kéo dài qua toàn bộ Job. Job có nhiệm vụ điều phối, còn transaction nên được quản lý ở phạm vi Step, chunk hoặc một lần thực thi Tasklet. Tránh đặt `@Transactional` quanh lời gọi `JobLauncher` vì với launcher đồng bộ, transaction bên ngoài có thể làm transaction của Step tham gia cùng một transaction dài. Chia transaction theo đơn vị xử lý giúp giới hạn lock, connection, chi phí rollback và tạo checkpoint rõ ràng cho restart. Với tác dụng phụ ngoài database, cần dùng idempotency, outbox hoặc compensation thay vì kỳ vọng rollback database sẽ hoàn tác mọi hệ thống.
