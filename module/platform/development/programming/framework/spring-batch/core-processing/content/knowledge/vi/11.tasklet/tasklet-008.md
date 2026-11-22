# Tasklet ném exception

Trong Spring Batch, Tasklet thực hiện một thao tác hoặc một lượt công việc bên trong TaskletStep. Khi thao tác không thể hoàn thành, Tasklet có thể ném exception để báo lỗi cho framework. TaskletStep nhận exception, xử lý transaction của lượt thực thi và đánh dấu Step thất bại.

Exception là cơ chế quan trọng để phân biệt một lần thực thi thành công với một lần thực thi không hoàn thành. Nếu Tasklet bắt exception rồi bỏ qua, hoặc trả về RepeatStatus.FINISHED dù thao tác thất bại, Spring Batch có thể ghi nhận Step thành công trong khi dữ liệu nghiệp vụ chưa được xử lý đúng.

Bài học này trình bày cách exception đi qua TaskletStep, ảnh hưởng đến transaction và trạng thái Job, cách phân loại lỗi, cũng như cách thiết kế retry, restart và side effect an toàn.

## 1. Tasklet báo lỗi bằng cách nào?

Tasklet khai báo phương thức execute nhận StepContribution và ChunkContext, đồng thời có thể ném Exception:

~~~java
RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) throws Exception;
~~~

Phương thức trả về RepeatStatus khi lượt xử lý kết thúc bình thường:

- **RepeatStatus.FINISHED**: Tasklet đã hoàn tất; vòng lặp thực thi Tasklet kết thúc.
- **RepeatStatus.CONTINUABLE**: Tasklet còn công việc; TaskletStep gọi lại Tasklet ở lượt tiếp theo.

Nếu Tasklet không thể hoàn thành vì một lỗi, nó có thể ném exception:

~~~java
@Bean
public Step processBatchStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        BatchService batchService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        if (!batchService.inputIsReady()) {
            throw new IllegalStateException(
                    "Input batch is not ready");
        }

        batchService.processBatch();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("processBatchStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

Nếu input chưa sẵn sàng, Tasklet ném IllegalStateException. Lệnh return FINISHED không được thực hiện, nên Step không kết thúc như một lần chạy thành công.

Điểm cần nhớ: RepeatStatus điều khiển vòng lặp Tasklet. Nó không phải trạng thái thành công/thất bại của Job. Exception báo lỗi thực thi và được TaskletStep xử lý ở cấp Step.

## 2. Exception đi qua TaskletStep như thế nào?

TaskletStep điều khiển vòng lặp gọi Tasklet và transaction cho từng lượt gọi. Khi Tasklet ném exception, exception đi ra khỏi lời gọi execute và được xử lý trong cơ chế thực thi của Step.

Luồng khái quát:

~~~text
TaskletStep bắt đầu
       |
       v
Mở transaction cho lượt Tasklet
       |
       v
Gọi Tasklet.execute(...)
       |
       +---- trả FINISHED ------> commit lượt xử lý
       |                              |
       |                              v
       |                         Kết thúc Step
       |
       +---- trả CONTINUABLE ---> commit lượt hiện tại
       |                              |
       |                              v
       |                         Gọi lượt tiếp theo
       |
       +---- ném exception -----> rollback theo transaction policy
                                      |
                                      v
                                 Step thất bại
~~~

Với cấu hình TaskletStep mặc định, exception từ Tasklet là tín hiệu rollback cho transaction của lượt thực thi. StepExecution được cập nhật với trạng thái thất bại và exception được giữ trong metadata/log để phục vụ điều tra. Nếu ứng dụng tùy chỉnh transaction attributes hoặc rollback rules, cần kiểm tra chính sách thực tế của Step.

Tasklet có thể ném checked exception vì chữ ký execute khai báo throws Exception. RuntimeException cũng có thể được ném trực tiếp. Dù dùng loại nào, hãy chọn exception phản ánh đúng nguyên nhân và không chuyển một lỗi cần rollback thành kết quả thành công.

### Tasklet ném exception khác với trả về FINISHED

Hai cách sau có ý nghĩa hoàn toàn khác nhau:

~~~java
// Công việc hoàn thành bình thường.
return RepeatStatus.FINISHED;
~~~

~~~java
// Công việc không thể hoàn thành.
throw new IllegalStateException("Cannot process batch");
~~~

Không dùng FINISHED để báo rằng Tasklet đã dừng do lỗi. Nếu một điều kiện là kết quả nghiệp vụ bình thường, hãy biểu diễn nó bằng trạng thái hoặc dữ liệu có ý nghĩa, thay vì giả vờ hoàn tất hoặc ném exception chung chung.

## 3. Ảnh hưởng đến transaction và rollback

TaskletStep thực thi Tasklet trong transaction do transaction manager quản lý. Khi Tasklet ném exception, transaction hiện tại được rollback theo rollback policy của Step. Các thao tác database tham gia cùng transaction đó được hoàn tác.

Ví dụ:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    orderRepository.markBatchAsProcessing(batchId);
    reconciliationService.reconcile(batchId);

    if (reconciliationService.hasCriticalErrors(batchId)) {
        throw new IllegalStateException(
                "Reconciliation contains critical errors");
    }

    orderRepository.markBatchAsCompleted(batchId);
    return RepeatStatus.FINISHED;
};
~~~

Nếu các thao tác repository cùng tham gia một transaction và exception làm transaction rollback, thay đổi database trong lượt đó được hoàn tác. Tuy nhiên, cần hiểu giới hạn của transaction:

- Rollback chỉ áp dụng cho resource tham gia transaction tương ứng.
- Ghi file, gọi HTTP API hoặc gửi message ra hệ thống ngoài thường không tự động được hoàn tác cùng transaction database.
- Nếu Tasklet dùng nhiều DataSource với transaction manager độc lập, rollback một transaction không tự động rollback transaction còn lại.
- Các thao tác đã commit trong những lượt Tasklet trước đó không bị rollback chỉ vì một lượt sau thất bại.

Vì Tasklet có thể trả CONTINUABLE, một Tasklet nhiều lượt có thể đã commit một số phần việc trước khi một lượt sau ném exception. Restart phải biết phần nào đã hoàn tất và phần nào cần làm lại.

### Transaction boundary của Tasklet nhiều lượt

~~~text
Lượt 1: Tasklet.execute -> xử lý trang 1 -> COMMIT
Lượt 2: Tasklet.execute -> xử lý trang 2 -> COMMIT
Lượt 3: Tasklet.execute -> lỗi -> ROLLBACK

Trạng thái sau lỗi:
  Trang 1: đã commit
  Trang 2: đã commit
  Lượt 3: transaction bị rollback
~~~

Điều này khác với một Tasklet chỉ thực hiện một thao tác trong một lượt. Khi chia công việc thành nhiều lượt, cần checkpoint hoặc trạng thái bền vững để xác định chính xác tiến độ.

## 4. Phân loại exception theo nguyên nhân

Không phải mọi exception đều cần được xử lý giống nhau. Có thể chia thành một số nhóm:

| Nhóm lỗi | Ví dụ | Cách xử lý thường phù hợp |
| --- | --- | --- |
| Dữ liệu hoặc điều kiện nghiệp vụ không hợp lệ | Input thiếu, trạng thái batch không cho phép xử lý | Fail Step hoặc ghi nhận kết quả từ chối theo quy trình nghiệp vụ |
| Lỗi tạm thời | Database tạm mất kết nối, dịch vụ từ xa timeout | Retry có giới hạn nếu thao tác an toàn |
| Lỗi cấu hình | Thiếu file cấu hình, sai endpoint, sai credentials | Fail sớm và sửa cấu hình |
| Lỗi lập trình | NullPointerException, invariant bị vi phạm | Fail và sửa code; không skip tùy tiện |
| Lỗi tài nguyên | Hết dung lượng đĩa, hết connection pool | Fail hoặc retry sau khi có điều kiện phục hồi phù hợp |

Việc phân loại giúp chọn exception type và chính sách vận hành. Ví dụ, một input không hợp lệ thường không tự trở nên hợp lệ sau vài lần thử; retry liên tục chỉ lặp lại cùng lỗi. Ngược lại, một lỗi kết nối tạm thời có thể phục hồi sau backoff.

### Tạo exception theo ngữ nghĩa nghiệp vụ

Thay vì ném RuntimeException chung chung, có thể định nghĩa exception cụ thể:

~~~java
public class InvalidBatchStateException extends RuntimeException {

    public InvalidBatchStateException(String message) {
        super(message);
    }
}
~~~

Sử dụng:

~~~java
if (batch.getStatus() != BatchStatus.READY) {
    throw new InvalidBatchStateException(
            "Batch " + batch.getId() + " is not READY");
}
~~~

Exception riêng giúp log và hệ thống giám sát phân biệt lỗi nghiệp vụ với lỗi kỹ thuật. Không nên đưa thông tin bí mật hoặc dữ liệu cá nhân không cần thiết vào message.

## 5. Bắt exception trong Tasklet: khi nào nên và không nên?

Nếu không có lý do xử lý tại chỗ, để exception đi ra khỏi Tasklet. TaskletStep cần biết lần thực thi đã thất bại để rollback, cập nhật trạng thái và cho phép luồng Job áp dụng chính sách tương ứng.

Không nên viết:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    try {
        batchService.processBatch();
    } catch (Exception ex) {
        log.error("Batch processing failed", ex);
    }

    return RepeatStatus.FINISHED;
};
~~~

Đoạn code này nuốt exception. Spring Batch thấy Tasklet trả FINISHED và có thể ghi nhận Step thành công dù batchService đã thất bại.

Nếu cần bổ sung log hoặc ngữ cảnh, có thể ghi log rồi ném lại exception:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    try {
        batchService.processBatch();
        return RepeatStatus.FINISHED;
    } catch (BatchProcessingException ex) {
        log.error("Cannot process batchId={}", batchId, ex);
        throw ex;
    }
};
~~~

Nếu cần đổi loại exception, hãy giữ nguyên cause:

~~~java
try {
    batchService.processBatch();
} catch (IOException ex) {
    throw new BatchProcessingException(
            "Unable to read batch input", ex);
}
~~~

Việc wrap exception chỉ nên thực hiện khi exception mới cung cấp ngữ nghĩa hữu ích. Giữ cause giúp điều tra stack trace và nguyên nhân gốc.

### Khi nào có thể xử lý exception tại chỗ?

Có thể bắt exception nếu Tasklet thực sự có một cách xử lý hợp lệ, chẳng hạn:

- Chuyển một loại lỗi dự kiến thành kết quả nghiệp vụ đã được ghi nhận.
- Thực hiện cleanup cần thiết rồi ném lại lỗi ban đầu.
- Chuyển một exception kỹ thuật sang exception domain cụ thể mà vẫn giữ cause.
- Thực hiện fallback được nghiệp vụ cho phép và có thể kiểm chứng.

Sau khi xử lý, nếu công việc vẫn được coi là thành công, phải bảo đảm kết quả và trạng thái phản ánh đúng sự thật. Không nên catch để tránh Job bị FAILED.

## 6. Job và Step nhận trạng thái thất bại

Khi exception thoát khỏi Tasklet, TaskletStep kết thúc ở trạng thái thất bại. Spring Batch lưu BatchStatus và ExitStatus trong metadata.

Hai khái niệm có liên quan nhưng khác nhau:

- **BatchStatus** là trạng thái vòng đời chuẩn của JobExecution hoặc StepExecution, chẳng hạn COMPLETED, FAILED, STOPPED hoặc STARTED.
- **ExitStatus** là mã kết quả được dùng trong flow và có thể mang thêm thông tin để điều hướng.

Thông thường, exception không được xử lý làm Step có BatchStatus FAILED và ExitStatus phản ánh lỗi. Job cũng có thể kết thúc FAILED nếu không có flow transition nào xử lý nhánh thất bại.

### Điều hướng Job khi Step thất bại

Job có thể khai báo flow transition để chuyển sang một Step xử lý lỗi:

~~~java
@Bean
public Job dailyBatchJob(
        JobRepository jobRepository,
        Step processBatchStep,
        Step recordFailureStep,
        Step publishResultStep) {

    return new JobBuilder("dailyBatchJob", jobRepository)
            .start(processBatchStep)
                .on("FAILED").to(recordFailureStep)
            .from(processBatchStep)
                .on("*").to(publishResultStep)
            .end()
            .build();
}
~~~

Ví dụ minh họa flow: nếu processBatchStep có ExitStatus FAILED, Job chuyển sang recordFailureStep. Với các exit code khác, flow đi đến publishResultStep. Cần thiết kế Step xử lý lỗi sao cho không che mất lỗi gốc và không vô tình đánh dấu toàn bộ Job thành thành công nếu nghiệp vụ vẫn yêu cầu Job FAILED.

Nếu muốn phân biệt nhiều loại lỗi, có thể dùng ExitStatus tùy chỉnh hoặc một bước phân loại lỗi. Hãy xác định rõ BatchStatus và ExitStatus nào sẽ được trả về cuối cùng vì chúng có thể khác nhau khi Job có flow xử lý lỗi.

## 7. Retry lỗi tạm thời trong Tasklet

Tasklet không có pipeline item-level retry/skip giống chunk-oriented Step. Nếu Tasklet gọi dịch vụ có lỗi tạm thời, ứng dụng có thể triển khai retry rõ ràng bằng Spring Retry hoặc cơ chế retry của service.

Chính sách retry nên xác định:

- Loại exception nào được retry.
- Số lần thử tối đa.
- Khoảng nghỉ và backoff giữa các lần thử.
- Timeout tổng thể.
- Điều kiện dừng khi lỗi không còn tạm thời.
- Cách bảo đảm thao tác có thể thực hiện lại an toàn.

Không nên retry mọi exception. Lỗi dữ liệu, lỗi cấu hình hoặc lỗi lập trình thường không được giải quyết bằng cách thử lại.

Ví dụ minh họa dùng RetryTemplate cho một lời gọi dịch vụ có thể phục hồi:

~~~java
public class RemoteBatchService {

    private final RetryTemplate retryTemplate;
    private final RemoteClient remoteClient;

    public RemoteBatchService(
            RetryTemplate retryTemplate,
            RemoteClient remoteClient) {
        this.retryTemplate = retryTemplate;
        this.remoteClient = remoteClient;
    }

    public void submitBatch(String batchId) {
        retryTemplate.execute(context -> {
            remoteClient.submit(batchId);
            return null;
        });
    }
}
~~~

RetryTemplate cần được cấu hình với retry policy, backoff policy và exception classifier phù hợp. Nếu hết số lần thử, exception cuối cùng thoát khỏi service và TaskletStep xử lý như lỗi Tasklet.

### Cẩn thận với transaction khi retry

Nếu RetryTemplate được gọi bên trong một Tasklet transaction, nhiều lần thử có thể diễn ra trong cùng transaction bên ngoài. Một lần thử thất bại không nhất thiết tự động rollback transaction trước khi lần thử tiếp theo bắt đầu. Điều này đặc biệt quan trọng nếu lần thử đầu đã thực hiện một phần thao tác database.

Với thao tác cần transaction riêng cho từng lần thử, hãy thiết kế transaction boundary phù hợp, ví dụ tách service với propagation phù hợp hoặc để orchestrator thực hiện từng attempt trong transaction riêng. Không thêm propagation mới theo thói quen; phải xác định rõ dữ liệu nào được commit, rollback và cách phục hồi sau crash.

Nếu remote API đã nhận request nhưng response bị timeout, client không biết chắc server đã thực hiện thao tác hay chưa. Retry có thể gửi request lần hai. Hãy dùng idempotency key ổn định, ví dụ batchId cộng operation type, để server nhận diện request lặp.

## 8. Restart sau khi Tasklet ném exception

Nếu JobExecution kết thúc FAILED và Job cho phép restart, có thể restart cùng JobInstance bằng cùng Job name và identifying JobParameters. Spring Batch tạo JobExecution mới cho instance đó.

Với TaskletStep, khi Step thất bại, Step thường được thực thi lại từ đầu trong lần restart. Tasklet tùy chỉnh không tự động có checkpoint chi tiết như một ItemStream reader. Nếu Tasklet đã hoàn thành một phần công việc trước khi thất bại, ứng dụng phải biết cách tiếp tục hoặc thực hiện lại an toàn.

Ví dụ Tasklet xử lý nhiều trang:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    ExecutionContext context =
            contribution.getStepExecution().getExecutionContext();

    int nextPage = context.getInt("nextPage", 0);

    pageService.processPage(nextPage);

    context.putInt("nextPage", nextPage + 1);
    return pageService.hasMorePages(nextPage + 1)
            ? RepeatStatus.CONTINUABLE
            : RepeatStatus.FINISHED;
};
~~~

Đây là minh họa về checkpoint. Trong ứng dụng thực tế, cần bảo đảm việc cập nhật dữ liệu của trang và checkpoint nhất quán. Nếu dữ liệu trang đã commit nhưng checkpoint chưa được lưu, lần restart có thể xử lý lại trang. Nếu checkpoint được lưu trước khi dữ liệu trang commit, lần restart có thể bỏ qua dữ liệu chưa hoàn thành.

Một lựa chọn khác là thiết kế Tasklet idempotent: xử lý lại cùng batchId hoặc pageId không tạo dữ liệu trùng và không làm sai trạng thái. Với các thao tác có side effect ngoài transaction, idempotency đặc biệt quan trọng.

### Khi restart không phù hợp

Nếu lỗi là dữ liệu đầu vào sai hoặc cấu hình không hợp lệ, restart cùng tham số thường chỉ lặp lại lỗi. Hãy sửa nguyên nhân trước khi chạy lại. Nếu dữ liệu nghiệp vụ đã thay đổi và cần một lần xử lý độc lập, xác định identifying parameters mới theo revision nghiệp vụ thay vì thêm timestamp ngẫu nhiên.

## 9. Side effect bên ngoài transaction

Một Tasklet có thể thực hiện nhiều loại thao tác:

- Cập nhật database.
- Ghi hoặc di chuyển file.
- Gọi REST API.
- Gửi message.
- Gửi email hoặc thông báo.

Không phải tất cả thao tác này đều tham gia cùng một transaction. Ví dụ:

~~~text
Tasklet
   |
   +--> UPDATE database
   |
   +--> POST remote API
   |
   +--> ghi file
   |
   +--> ném exception
          |
          v
       DB rollback

Remote API hoặc file đã hoàn thành có thể vẫn còn
~~~

Rollback database không tự xóa file hoặc thu hồi request đã được hệ thống ngoài xử lý. Khi restart, Tasklet có thể gọi lại API hoặc ghi lại file và tạo side effect trùng.

Các cách giảm rủi ro:

- **Idempotency key:** dùng một khóa ổn định để hệ thống đích nhận diện request lặp.
- **Outbox pattern:** ghi yêu cầu gửi message cùng transaction database, sau đó một publisher riêng gửi message và đánh dấu trạng thái.
- **Staging và trạng thái xử lý:** ghi nhận operation đã hoàn thành để restart biết bước nào cần tiếp tục.
- **Compensation:** thực hiện thao tác bù nếu hệ thống nghiệp vụ cho phép và không thể rollback trực tiếp.
- **Atomic file replacement:** ghi file tạm rồi đổi tên sau khi hoàn tất, nếu filesystem và yêu cầu triển khai hỗ trợ.

Chọn cơ chế phù hợp với từng side effect. Không nên giả định một transaction database có thể bao trùm mọi hệ thống bên ngoài.

## 10. Ghi nhận và quan sát lỗi

Khi Tasklet thất bại, người vận hành cần biết Job nào, Step nào, batch nào và nguyên nhân gì. Có thể kết hợp log, listener và JobExplorer.

### Ghi log với ngữ cảnh

~~~java
try {
    batchService.process(batchId);
} catch (BatchProcessingException ex) {
    log.error(
            "Tasklet failed for batchId={}, step=processBatch",
            batchId,
            ex);
    throw ex;
}
~~~

Log nên có Job name, JobExecutionId hoặc StepExecutionId khi có thể truy cập, business key và error category. Không log credentials hoặc payload nhạy cảm.

### StepExecutionListener

Listener có thể dùng để ghi nhận kết quả sau khi Step kết thúc:

~~~java
public class BatchStepListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.FAILED) {
            log.error(
                    "Step {} failed with exit status {}",
                    stepExecution.getStepName(),
                    stepExecution.getExitStatus());
        }

        return null;
    }
}
~~~

Trả về null giữ nguyên ExitStatus hiện tại. Listener phù hợp để quan sát và bổ sung thông tin. Không nên dùng listener để xóa lỗi hoặc đổi một Step FAILED thành COMPLETED chỉ nhằm làm Job xanh trên dashboard.

### JobExplorer

JobExplorer cho phép tra cứu JobExecution và StepExecution từ metadata repository:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, exitStatus={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus());
    }
}
~~~

Có thể kết hợp metadata với log correlation ID để xác định exception gốc. Tránh sửa trực tiếp bảng metadata để đổi trạng thái Job; hãy dùng API vận hành và quy trình restart phù hợp.

## 11. Phân biệt exception, skip và kết quả nghiệp vụ bình thường

Tasklet không có semantics item-level skip giống chunk-oriented Step. Nếu một bản ghi bị loại khỏi xử lý, Tasklet phải tự quyết định cách ghi nhận và tiếp tục. Ném exception thường có nghĩa lượt Tasklet thất bại; trả FINISHED có nghĩa công việc đã kết thúc bình thường.

Ví dụ, nếu batch chứa một số bản ghi bị từ chối nhưng vẫn có thể hoàn thành theo quy tắc nghiệp vụ, Tasklet có thể:

1. Ghi các bản ghi bị từ chối vào khu vực rejected.
2. Ghi số lượng accepted và rejected.
3. Xác định có lỗi nghiêm trọng hay không.
4. Hoàn tất với trạng thái nghiệp vụ phù hợp hoặc ném exception nếu điều kiện thất bại.

Nếu nghiệp vụ cần tiếp tục sau từng lỗi item, chunk-oriented Step với skip policy và SkipListener thường cung cấp cấu trúc phù hợp hơn. Không nên tự xây một cơ chế skip phức tạp trong Tasklet nếu ItemReader/ItemProcessor/ItemWriter đã mô hình hóa được công việc.

## 12. Những lỗi thường gặp

### Catch exception rồi trả FINISHED

TaskletStep có thể coi Step đã hoàn tất dù thao tác nghiệp vụ thất bại. Hãy ném lại exception nếu lỗi cần làm Step thất bại.

### Dùng CONTINUABLE để biểu diễn lỗi

CONTINUABLE chỉ yêu cầu Tasklet chạy lượt tiếp theo. Nó không phải tín hiệu lỗi. Nếu không thể tiếp tục, ném exception hoặc biểu diễn một kết quả nghiệp vụ bình thường theo flow được thiết kế.

### Retry mọi exception

Retry lỗi dữ liệu hoặc lỗi cấu hình chỉ làm Job thất bại muộn hơn. Chỉ retry exception có khả năng phục hồi và giới hạn số lần thử.

### Giả định rollback database hoàn tác HTTP hoặc file

Side effect bên ngoài transaction có thể vẫn tồn tại. Dùng idempotency key, outbox, staging hoặc compensation.

### Không lưu checkpoint cho Tasklet nhiều lượt

Sau khi một số lượt đã commit, exception ở lượt sau có thể khiến Tasklet chạy lại từ đầu khi restart. Hãy lưu tiến độ bền vững và bảo đảm checkpoint nhất quán với dữ liệu.

### Dùng exception chung chung

Exception không có ngữ nghĩa khiến việc phân loại lỗi, retry và cảnh báo khó hơn. Tạo exception domain cụ thể và giữ nguyên cause.

### Thay đổi JobParameters khi restart

Nếu identifying parameters thay đổi, Spring Batch có thể tạo JobInstance mới. Giữ nguyên định danh ban đầu khi mục tiêu là restart cùng instance.

### Chuyển Step FAILED thành COMPLETED trong listener

Điều này có thể che giấu lỗi và làm luồng vận hành hiểu sai kết quả. Listener nên quan sát hoặc bổ sung thông tin; chỉ thay đổi ExitStatus khi có quy tắc nghiệp vụ rõ ràng.

## 13. Quy trình xử lý Tasklet exception

Khi thiết kế một Tasklet có khả năng lỗi, hãy xác định:

1. Những điều kiện nào là lỗi nghiệp vụ và những điều kiện nào là lỗi kỹ thuật?
2. Exception nào cần làm transaction rollback và Step FAILED?
3. Có lỗi tạm thời nào được phép retry? Giới hạn và backoff là gì?
4. Side effect nào nằm ngoài transaction database?
5. Nếu Tasklet thất bại sau một phần công việc đã commit, restart sẽ tiếp tục từ đâu?
6. Có cần checkpoint, idempotency key, outbox hoặc compensation không?
7. Job cần dừng ngay hay chuyển sang Step ghi nhận lỗi?
8. Log và metadata có đủ thông tin để người vận hành xác định nguyên nhân không?

Một Tasklet tốt không cố che giấu mọi exception. Nó phân biệt rõ lỗi cần dừng, lỗi có thể retry và kết quả nghiệp vụ bình thường; đồng thời bảo đảm transaction, restart và side effect có hành vi có thể dự đoán.

## Kết luận

Khi Tasklet ném exception, TaskletStep xử lý lỗi trong transaction của lượt thực thi, rollback theo transaction policy và đánh dấu Step thất bại. Hãy để exception đi ra khỏi Tasklet khi công việc không hoàn thành; chỉ bắt lỗi khi có cách xử lý thực sự hợp lệ và giữ cause nếu wrap exception. Retry cần giới hạn và phân loại lỗi, còn restart cần identifying parameters ổn định, checkpoint và idempotency. Đặc biệt, rollback database không tự hoàn tác side effect như HTTP request hoặc file, nên phải thiết kế cơ chế phục hồi tương ứng.
