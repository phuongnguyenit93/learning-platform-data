# Tasklet thực hiện một tác vụ trong Step

Trong Spring Batch, `Tasklet` là cách định nghĩa một đơn vị công việc bên trong `Step` khi logic có thể được mô tả như một tác vụ hoàn chỉnh. Ví dụ: xóa dữ liệu tạm, gọi stored procedure, kiểm tra hoặc chuẩn bị file, gửi một yêu cầu tới hệ thống khác, tạo bản ghi tổng hợp hay di chuyển một file đã xử lý.

Khác với chunk-oriented processing, nơi Step đọc, xử lý và ghi nhiều item theo từng chunk, Tasklet tập trung vào việc thực hiện một tác vụ. Spring Batch gọi phương thức `execute()` của Tasklet và dựa vào giá trị `RepeatStatus` để biết Step đã xong hay cần thực hiện tiếp.

## 1. Tasklet là gì?

`Tasklet` là interface đơn giản của Spring Batch với phương thức:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

Phương thức `execute()` nhận hai đối tượng:

- **`StepContribution`:** đại diện cho phần đóng góp của lần thực thi Tasklet vào `StepExecution`. Có thể dùng nó để truy cập `StepExecution`, cập nhật các bộ đếm hoặc bổ sung ExitStatus.
- **`ChunkContext`:** cung cấp context của lần thực thi, trong đó có `StepContext` và các thuộc tính context có phạm vi chunk. Có thể dùng để truy cập JobParameters, StepExecutionContext hoặc dữ liệu context phù hợp.

Phương thức trả về `RepeatStatus`:

- **`RepeatStatus.FINISHED`:** Tasklet đã hoàn thành công việc; Step không cần gọi lại Tasklet nữa.
- **`RepeatStatus.CONTINUABLE`:** Tasklet yêu cầu Spring Batch gọi `execute()` thêm lần nữa.

Nếu tác vụ chỉ cần chạy một lần, thường trả về `FINISHED`. Nếu tác vụ được chia thành nhiều lượt và mỗi lần chỉ xử lý một phần công việc, có thể trả về `CONTINUABLE` cho đến khi hoàn tất.

## 2. Tasklet được thực thi trong Step như thế nào?

Một `Tasklet` được Spring Batch chạy bên trong `TaskletStep`. Step quản lý vòng đời thực thi, transaction, trạng thái và metadata. Luồng đơn giản:

```text
Job bắt đầu
    |
    v
TaskletStep tạo StepExecution
    |
    v
Tasklet.execute(contribution, chunkContext)
    |
    v
Thực hiện tác vụ
    |
    v
Trả về RepeatStatus
    |
    +---- FINISHED ------> Step hoàn tất
    |
    +---- CONTINUABLE ---> Gọi execute() tiếp
```

Với Tasklet thông thường trả về `FINISHED`, `execute()` được gọi một lần cho lần thực thi Step đó. Nếu trả về `CONTINUABLE`, Spring Batch tiếp tục vòng lặp và gọi Tasklet lần nữa. Cần bảo đảm mỗi lần lặp có tiến triển rõ ràng; nếu luôn trả về `CONTINUABLE` mà không thay đổi trạng thái hoặc điều kiện dừng, Step có thể chạy vô hạn.

Trong `TaskletStep`, mỗi lần gọi Tasklet được thực hiện trong transaction do transaction manager của Step quản lý. Với Tasklet lặp nhiều lần bằng `CONTINUABLE`, các lần gọi được quản lý theo các transaction riêng của vòng lặp. Vì vậy, nên hiểu rõ tác vụ nào được commit ở mỗi lần gọi và trạng thái nào cần lưu để có thể tiếp tục sau sự cố.

## 3. Khai báo Tasklet bằng Java configuration

Trong Spring Batch 5, có thể tạo Step bằng `StepBuilder` và truyền `JobRepository` cùng `PlatformTransactionManager`:

```java
@Bean
Step cleanupTemporaryDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CleanupTemporaryDataTasklet tasklet) {

    return new StepBuilder("cleanupTemporaryDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

`tasklet(tasklet, transactionManager)` cho biết Step sử dụng Tasklet được cung cấp và transaction manager nào để quản lý transaction của mỗi lần thực thi Tasklet.

Định nghĩa Tasklet có thể là một bean riêng:

```java
@Component
public class CleanupTemporaryDataTasklet implements Tasklet {

    private final TemporaryDataService temporaryDataService;

    public CleanupTemporaryDataTasklet(
            TemporaryDataService temporaryDataService) {
        this.temporaryDataService = temporaryDataService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int deleted = temporaryDataService.deleteExpiredRecords();
        contribution.incrementWriteCount(deleted);

        return RepeatStatus.FINISHED;
    }
}
```

Ví dụ này gọi service để xóa dữ liệu hết hạn, cập nhật write count và kết thúc Step. Việc cập nhật bộ đếm giúp metadata phản ánh một phần kết quả, nhưng `writeCount` không thay thế log nghiệp vụ hoặc báo cáo chi tiết nếu cần lưu số bản ghi đã xóa theo từng nhóm.

## 4. Dùng lambda khi tác vụ đơn giản

Nếu công việc ngắn và không cần class riêng, có thể khai báo Tasklet bằng lambda:

```java
@Bean
Step generateControlFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ControlFileService controlFileService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        controlFileService.generateControlFile();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("generateControlFileStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

Lambda phù hợp với tác vụ ngắn, ít trạng thái và dễ hiểu. Nếu logic có nhiều nhánh, phụ thuộc phức tạp, cần checkpoint hoặc cần kiểm thử riêng, một class triển khai `Tasklet` thường rõ ràng hơn.

## 5. RepeatStatus và tác vụ cần nhiều lượt

Một Tasklet không nhất thiết chỉ được gọi một lần. Có thể dùng `CONTINUABLE` để xử lý công việc theo nhiều lượt. Ví dụ, một tác vụ dọn dẹp xóa tối đa 1.000 bản ghi mỗi lần gọi để giới hạn thời gian transaction:

```java
@Component
public class DeleteExpiredRecordsTasklet implements Tasklet {

    private final TemporaryDataService service;

    public DeleteExpiredRecordsTasklet(TemporaryDataService service) {
        this.service = service;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        int deleted = service.deleteNextBatch(1_000);
        contribution.incrementWriteCount(deleted);

        if (deleted == 0) {
            return RepeatStatus.FINISHED;
        }

        return RepeatStatus.CONTINUABLE;
    }
}
```

Mỗi lần gọi xử lý tối đa 1.000 bản ghi. Khi không còn bản ghi cần xóa, service trả về 0 và Tasklet trả `FINISHED`. Những lần gọi trước đó trả `CONTINUABLE` để Step tiếp tục.

Thiết kế này cần một điều kiện dừng chắc chắn. Nếu service luôn trả số lượng lớn hơn 0 do truy vấn không loại được bản ghi đã xử lý, Tasklet có thể lặp vô hạn. Nên ghi log số lượng xử lý, giới hạn số lượt nếu cần và xác định rõ cách tiếp tục sau restart.

`CONTINUABLE` chỉ yêu cầu lặp lại Tasklet trong Step hiện tại. Nó không có nghĩa Spring Batch tự động khởi chạy một Job mới hoặc tự động đợi một sự kiện bên ngoài.

## 6. Đọc JobParameters và StepExecutionContext trong Tasklet

Tasklet có thể lấy tham số đầu vào của Job qua `ChunkContext` hoặc `StepContribution`. Ví dụ, một Tasklet nhận ngày nghiệp vụ và mã file:

```java
@Bean
@StepScope
Tasklet validateInputFileTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") LocalDate businessDate,
        InputFileService inputFileService) {

    return (contribution, chunkContext) -> {
        inputFileService.validate(inputFile, businessDate);
        return RepeatStatus.FINISHED;
    };
}
```

`@StepScope` cho phép Spring tạo bean trong phạm vi StepExecution, vì vậy các JobParameters có thể được late-bind khi Step bắt đầu. Không nên cố đọc tham số của một lần chạy tương lai trong một singleton bean được khởi tạo lúc ứng dụng khởi động.

Nếu cần lưu một giá trị để sử dụng trong Step tiếp theo hoặc khi restart, có thể dùng `ExecutionContext`:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    ExecutionContext context = contribution
            .getStepExecution()
            .getExecutionContext();

    context.putString("validatedFileVersion", "v3");
    return RepeatStatus.FINISHED;
}
```

ExecutionContext ở cấp StepExecution có thể được lưu cùng metadata và khôi phục khi restart, tùy thời điểm cập nhật/commit và cấu hình Step. Nếu dữ liệu cần được Step tiếp theo sử dụng, có thể lưu ở JobExecutionContext thông qua cơ chế phù hợp, chẳng hạn `ExecutionContextPromotionListener` để promote các khóa được chọn từ Step context lên Job context.

## 7. Transaction và xử lý lỗi trong Tasklet

Transaction manager được truyền vào `tasklet()` xác định transaction mà `TaskletStep` sử dụng khi gọi Tasklet. Nếu Tasklet thực hiện các thao tác database tham gia cùng transaction manager, các thay đổi có thể được commit khi lần gọi thành công hoặc rollback khi exception làm transaction thất bại.

Ví dụ, nếu Tasklet cập nhật trạng thái lô dữ liệu rồi ném exception trước khi transaction commit, thay đổi database trong cùng transaction có thể được rollback:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    batchRepository.markAsProcessing(batchId);
    batchRepository.updateSummary(batchId);

    if (hasInvalidState(batchId)) {
        throw new IllegalStateException("Batch state is invalid");
    }

    return RepeatStatus.FINISHED;
}
```

Nếu exception thoát khỏi `execute()`, Step thường chuyển sang `FAILED` và transaction hiện tại được rollback theo cấu hình. Spring Batch ghi trạng thái lỗi vào metadata. Cần tránh bắt exception rồi bỏ qua nếu tác vụ thực tế chưa hoàn thành; điều đó có thể khiến Step được đánh dấu `COMPLETED` dù kết quả nghiệp vụ không đúng.

Không phải mọi tác dụng phụ đều nằm trong transaction database. Gọi REST API, gửi email, ghi file hoặc publish message thường không được rollback cùng database. Nếu Tasklet gọi service ngoài rồi gặp lỗi ở bước tiếp theo, hành động bên ngoài có thể đã xảy ra. Hãy thiết kế idempotency key, ghi trạng thái trung gian, dùng outbox hoặc có bước đối soát để xử lý restart an toàn.

## 8. Restart và tính idempotent của Tasklet

Khi Tasklet thất bại, Job có thể được restart nếu cấu hình Job và trạng thái Step cho phép. Tuy nhiên, Tasklet không tự động biết một tác vụ bên ngoài đã thực hiện đến đâu. Khả năng restart đáng tin cậy phụ thuộc cách Tasklet lưu tiến độ và cách nó xử lý tác dụng phụ.

Ví dụ, Tasklet gửi một file sang hệ thống đối tác. Nếu đối tác nhận file thành công nhưng ứng dụng dừng trước khi Spring Batch lưu trạng thái Step hoàn tất, lần restart có thể gửi file lần nữa.

Một số biện pháp:

- Gắn mã lô hoặc idempotency key ổn định cho mỗi lần gửi.
- Lưu trạng thái đã gửi và mã xác nhận từ hệ thống đích.
- Dùng tên file/version bất biến để phát hiện file đã được tiếp nhận.
- Tách tác vụ thành các bước có thể đối soát, chẳng hạn tạo file, gửi file và xác nhận kết quả.
- Nếu Tasklet lặp nhiều lần, lưu checkpoint sau mỗi đơn vị công việc đã commit.

Không nên tạo một UUID mới cho mỗi lần restart nếu mục tiêu là nhận diện cùng một tác vụ nghiệp vụ. Khóa phải giữ ổn định giữa các lần thực thi của cùng công việc.

## 9. Tasklet và chunk-oriented processing khác nhau thế nào?

Hai mô hình đều chạy trong Step nhưng phù hợp với dạng công việc khác nhau.

| Tiêu chí | Tasklet | Chunk-oriented processing |
|---|---|---|
| Mô hình | Thực hiện một tác vụ trong `execute()` | Đọc, xử lý và ghi nhiều item theo chunk |
| Thành phần chính | `Tasklet` | `ItemReader`, `ItemProcessor`, `ItemWriter` |
| Điều khiển kết thúc | `RepeatStatus.FINISHED` hoặc `CONTINUABLE` | Reader trả `null` khi hết input |
| Transaction | Mỗi lần gọi Tasklet được quản lý trong transaction của TaskletStep | Transaction thường bao quanh một chunk |
| Phù hợp | Cleanup, stored procedure, tạo file, tác vụ điều phối | Import/export, chuyển đổi và ghi số lượng lớn item |
| Theo dõi tiến độ | Cần tự ghi nhận nếu tác vụ có nhiều phần | Có bộ đếm item và checkpoint theo cơ chế chunk/reader |

Ví dụ:

- Dọn bảng staging bằng một lệnh SQL hoặc stored procedure: Tasklet thường phù hợp.
- Đọc 2 triệu dòng CSV, kiểm tra từng dòng rồi ghi vào database: chunk-oriented processing thường phù hợp hơn.
- Tạo một file manifest sau khi các Step import đã hoàn thành: Tasklet có thể phù hợp.

Tasklet vẫn có thể xử lý nhiều bản ghi, nhưng nếu logic chủ yếu là lặp qua từng item và cần reader, processor, writer, skip, retry và checkpoint theo item, chunk-oriented processing thường thể hiện ý định rõ ràng hơn.

## 10. Dùng TaskletAdapter cho phương thức có sẵn

Khi đã có một service hoặc phương thức legacy thực hiện tác vụ, có thể dùng `MethodInvokingTaskletAdapter` để gọi phương thức đó thay vì viết một class Tasklet mới. Adapter cấu hình target object và tên method cần gọi.

Ví dụ khái quát:

```java
@Bean
MethodInvokingTaskletAdapter archiveTaskletAdapter(
        ArchiveService archiveService) {

    MethodInvokingTaskletAdapter adapter =
            new MethodInvokingTaskletAdapter();
    adapter.setTargetObject(archiveService);
    adapter.setTargetMethod("archiveCompletedFiles");
    return adapter;
}
```

Adapter phù hợp khi phương thức hiện có tương thích với cách adapter gọi và không cần logic điều khiển `RepeatStatus` phức tạp. Nếu cần xử lý trạng thái, kiểm soát nhiều lượt, cập nhật context hoặc phân loại lỗi, triển khai `Tasklet` trực tiếp thường linh hoạt và dễ đọc hơn. API và cách cấu hình adapter có thể khác theo phiên bản Spring Batch.

## 11. Logging, listener và quan sát Tasklet

Vì Tasklet thường đại diện cho một tác vụ có ý nghĩa nghiệp vụ, nên log rõ bước bắt đầu, kết quả và nguyên nhân thất bại. Có thể dùng `StepExecutionListener` để ghi nhận thời điểm trước và sau Step:

```java
public class TaskletStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Starting step {} for job execution {}",
                stepExecution.getStepName(),
                stepExecution.getJobExecutionId());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info("Finished step {} with status {}",
                stepExecution.getStepName(),
                stepExecution.getStatus());
        return null;
    }
}
```

Ngoài trạng thái `BatchStatus`, cần phân biệt `ExitStatus` là mã kết quả dùng để điều khiển flow Job. Listener có thể bổ sung ExitStatus nếu nghiệp vụ cần phân nhánh sau Step, nhưng không nên thay đổi kết quả tùy tiện để che giấu lỗi.

Các thông tin hữu ích khi theo dõi:

- JobExecution ID và StepExecution ID.
- Mã nghiệp vụ hoặc batch ID mà Tasklet đang xử lý.
- Thời gian bắt đầu, thời gian hoàn thành và số lượt gọi `execute()`.
- Số bản ghi hoặc file đã xử lý, nếu có.
- Mã xác nhận từ hệ thống ngoài và số lần retry.
- Exception và trạng thái transaction khi thất bại.

Không log password, access token hoặc payload nhạy cảm. Nếu Tasklet gọi service ngoài, nên theo dõi latency và tỷ lệ lỗi của dependency để phân biệt lỗi của tác vụ với lỗi của hệ thống phụ thuộc.

## 12. Kiểm thử Tasklet

Tasklet có thể được kiểm thử như một class Java thông thường bằng cách mock service phụ thuộc và tạo `StepContribution`, `ChunkContext` phù hợp. Các trường hợp nên kiểm tra gồm:

- Tác vụ thành công và trả `RepeatStatus.FINISHED`.
- Tác vụ cần nhiều lượt và trả `CONTINUABLE` cho đến điều kiện dừng.
- Service ném exception và lỗi được truyền ra để Step có thể đánh dấu thất bại.
- JobParameters hoặc ExecutionContext được đọc/ghi đúng.
- Tác vụ có thể được thực hiện lại mà không tạo tác dụng phụ trùng lặp.

Với kiểm thử tích hợp, có thể chạy Step trong một JobRepository và transaction manager thử nghiệm để xác nhận metadata, trạng thái và restart. Không cần gọi hệ thống production; dùng database và service giả lập dành cho test.

## 13. Các lỗi thường gặp khi dùng Tasklet

**Luôn trả về `CONTINUABLE`:** Step lặp mãi nếu không có điều kiện dừng. Hãy xác định tiến độ và điều kiện hoàn tất cho mỗi lượt.

**Trả về `FINISHED` trước khi tác vụ thực sự hoàn tất:** Step được đánh dấu hoàn thành dù công việc còn dang dở. Chỉ trả `FINISHED` sau khi xác nhận kết quả cần thiết.

**Dùng Tasklet cho vòng lặp dữ liệu lớn:** một phương thức duy nhất tự đọc hàng triệu bản ghi có thể làm mất lợi ích của chunk, checkpoint, skip và retry theo item. Hãy cân nhắc chunk-oriented processing.

**Giữ transaction quá lâu:** Tasklet thực hiện toàn bộ công việc lớn trong một lần gọi có thể giữ connection và khóa lâu. Chia công việc thành nhiều lượt có checkpoint hoặc dùng chunk khi phù hợp.

**Cho rằng REST call rollback cùng database:** hệ thống ngoài không tự tham gia transaction của Step. Cần idempotency và cơ chế đối soát.

**Bắt exception rồi vẫn trả `FINISHED`:** lỗi bị che giấu và Job có thể báo thành công trong khi tác vụ thất bại. Chỉ xử lý exception khi có chính sách rõ ràng và ghi nhận kết quả tương ứng.

**Không lưu tiến độ của Tasklet nhiều lượt:** sau restart, Tasklet có thể làm lại từ đầu hoặc bỏ sót công việc. Hãy lưu checkpoint hoặc thiết kế tác vụ idempotent.

## Kết luận

`Tasklet` cho phép một Step thực hiện một tác vụ thông qua `execute(StepContribution, ChunkContext)`. Tasklet trả `RepeatStatus.FINISHED` khi hoàn tất hoặc `CONTINUABLE` khi cần thêm lượt. `TaskletStep` quản lý transaction, trạng thái và metadata cho các lần gọi. Tasklet phù hợp với cleanup, stored procedure, tạo file và các công việc điều phối có phạm vi rõ ràng; chunk-oriented processing phù hợp hơn khi cần đọc, xử lý và ghi lượng lớn item với checkpoint theo chunk. Khi Tasklet gọi service ngoài hoặc thực hiện tác vụ có thể lặp lại, cần kiểm soát transaction boundary, idempotency, tiến độ và logging để restart an toàn.
