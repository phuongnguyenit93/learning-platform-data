# Dùng listener cho metric và audit

Spring Batch cung cấp listener để ứng dụng quan sát các mốc trong vòng đời Job, Step, chunk và từng item. Đây là điểm phù hợp để đo thời gian, ghi nhận số lượng xử lý, theo dõi lỗi và tạo audit trail cho hoạt động batch.

Metric và audit có mục đích khác nhau. Metric giúp trả lời hệ thống đang chạy nhanh hay chậm, xử lý được bao nhiêu item và có bao nhiêu lỗi. Audit ghi lại tiến trình nào đã thực hiện công việc gì, trên đơn vị dữ liệu nào, vào thời điểm nào và kết quả ra sao. Listener có thể cung cấp dữ liệu cho cả hai, nhưng cần chọn đúng callback và thiết kế lưu trữ phù hợp với transaction.

## 1. Listener trong Spring Batch là gì?

Listener là callback do Spring Batch gọi tại các mốc xác định trong quá trình thực thi. Ứng dụng triển khai interface listener hoặc dùng annotation listener được hỗ trợ, sau đó đăng ký listener vào Job hoặc Step.

Các nhóm listener thường dùng:

| Listener | Phạm vi quan sát | Ví dụ sử dụng |
|---|---|---|
| JobExecutionListener | Trước và sau Job | Audit lần chạy Job, đo tổng thời gian |
| StepExecutionListener | Trước và sau Step | Metric theo Step, ghi kết quả Step |
| ChunkListener | Trước và sau chunk, khi chunk lỗi | Đếm chunk, quan sát lỗi theo chunk |
| ItemReadListener | Trước/sau đọc và khi đọc lỗi | Đếm item đọc, ghi nhận lỗi nguồn |
| ItemProcessListener | Trước/sau xử lý và khi xử lý lỗi | Đo thời gian xử lý, theo dõi filter |
| ItemWriteListener | Trước/sau ghi và khi ghi lỗi | Quan sát writer và lỗi ghi |
| SkipListener | Khi item bị skip | Audit bản ghi bị bỏ qua |

Listener không thay thế ItemReader, ItemProcessor hoặc ItemWriter. Chúng quan sát hoặc bổ sung hành động tại lifecycle; trách nhiệm đọc, xử lý và ghi vẫn thuộc các component tương ứng.

## 2. Chọn listener theo cấp độ cần đo

Không phải mọi metric đều nên được ghi ở cấp item. Chọn callback theo độ chi tiết cần thiết để tránh tạo quá nhiều log hoặc metric.

- Muốn biết tổng thời gian một Job chạy: dùng JobExecutionListener.
- Muốn đo thời gian và counters của từng Step: dùng StepExecutionListener.
- Muốn đếm chunk thành công hoặc quan sát lỗi theo chunk: dùng ChunkListener.
- Muốn biết item nào đọc hoặc xử lý lỗi: dùng ItemReadListener hoặc ItemProcessListener.
- Muốn biết writer nhận bao nhiêu item và lỗi ghi xảy ra khi nào: dùng ItemWriteListener.
- Muốn audit item được bỏ qua: dùng SkipListener.

Luồng quan sát khái quát:

~~~text
JobExecutionListener.beforeJob()
        |
        v
StepExecutionListener.beforeStep()
        |
        v
ChunkListener.beforeChunk()
        |
        v
ItemReadListener / ItemProcessListener
        |
        v
ItemWriteListener
        |
        v
ChunkListener.afterChunk()
        |
        v
StepExecutionListener.afterStep()
        |
        v
JobExecutionListener.afterJob()
~~~

Một Step có thể có nhiều chunk; trong mỗi chunk, reader, processor và writer có thể được gọi nhiều lần hoặc không được gọi nếu không có item tương ứng. Callback lỗi và skip được gọi theo tình huống cũng như cấu hình fault tolerance.

## 3. JobExecutionListener cho metric và audit cấp Job

JobExecutionListener có hai callback chính:

- beforeJob(JobExecution): được gọi trước khi Job thực hiện các Step.
- afterJob(JobExecution): được gọi khi Job kết thúc, dù kết quả là hoàn thành hay thất bại.

Listener có thể lấy tên Job, JobExecution ID, JobInstance ID, JobParameters, BatchStatus và ExitStatus để tạo bản ghi audit.

~~~java
public class JobAuditListener implements JobExecutionListener {

    private final JobAuditService auditService;

    public JobAuditListener(JobAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeJob(JobExecution execution) {
        auditService.recordStarted(
                execution.getId(),
                execution.getJobInstance().getJobName(),
                execution.getJobInstance().getId());
    }

    @Override
    public void afterJob(JobExecution execution) {
        auditService.recordFinished(
                execution.getId(),
                execution.getJobInstance().getJobName(),
                execution.getStatus().name(),
                execution.getExitStatus().getExitCode());
    }
}
~~~

Đăng ký listener khi khai báo Job:

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        JobAuditListener jobAuditListener,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .listener(jobAuditListener)
            .start(importOrdersStep)
            .build();
}
~~~

Một JobInstance có thể có nhiều JobExecution do restart; vì vậy nên lưu JobExecution ID để phân biệt từng lần chạy, đồng thời lưu JobInstance ID để liên kết các lần chạy thuộc cùng một đơn vị công việc logic.

Nếu Job được launch bất đồng bộ, HTTP request có thể kết thúc ngay sau khi nhận JobExecution. Listener cấp Job là nơi phù hợp để ghi nhận kết quả cuối cùng sau khi Job thực sự kết thúc.

## 4. StepExecutionListener đo thời gian và counters

StepExecutionListener cung cấp beforeStep và afterStep. Đối tượng StepExecution chứa nhiều thông tin hữu ích cho metric và audit:

- Tên Step và JobExecution liên quan.
- BatchStatus và ExitStatus.
- Thời điểm bắt đầu và kết thúc.
- Read count, write count và filter count.
- Read/process/write skip count.
- Commit count và rollback count.

Ví dụ listener dùng Micrometer để ghi thời gian và counters:

~~~java
public class StepMetricsListener implements StepExecutionListener {

    private final MeterRegistry registry;
    private long startedAtNanos;

    public StepMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeStep(StepExecution execution) {
        startedAtNanos = System.nanoTime();
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        String jobName =
                execution.getJobExecution().getJobInstance().getJobName();
        String stepName = execution.getStepName();
        String status = execution.getStatus().name();

        Timer.builder("batch.step.duration")
                .tag("job", jobName)
                .tag("step", stepName)
                .tag("status", status)
                .register(registry)
                .record(Duration.ofNanos(
                        System.nanoTime() - startedAtNanos));

        counter("batch.step.items.read", jobName, stepName, status)
                .increment(execution.getReadCount());
        counter("batch.step.items.written", jobName, stepName, status)
                .increment(execution.getWriteCount());
        counter("batch.step.items.filtered", jobName, stepName, status)
                .increment(execution.getFilterCount());
        counter("batch.step.items.skipped", jobName, stepName, status)
                .increment(
                        execution.getReadSkipCount()
                        + execution.getProcessSkipCount()
                        + execution.getWriteSkipCount());

        counter("batch.step.chunks.committed", jobName, stepName, status)
                .increment(execution.getCommitCount());
        counter("batch.step.chunks.rolledback", jobName, stepName, status)
                .increment(execution.getRollbackCount());

        return execution.getExitStatus();
    }

    private Counter counter(
            String name, String job, String step, String status) {
        return Counter.builder(name)
                .tag("job", job)
                .tag("step", step)
                .tag("status", status)
                .register(registry);
    }
}
~~~

Ví dụ cần các import Micrometer và Spring Batch tương ứng. Vì listener giữ startedAtNanos trong field, cần bảo đảm một instance không bị nhiều StepExecution đồng thời dùng chung. Có thể tạo listener theo scope StepExecution hoặc lưu mốc bắt đầu theo execution ID nếu dùng một listener singleton.

Đăng ký vào Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        StepMetricsListener stepMetricsListener,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .listener(stepMetricsListener)
            .build();
}
~~~

Timer đo thời gian từ beforeStep đến afterStep. Counters trong ví dụ được cộng bằng số liệu tổng hợp trên StepExecution khi Step kết thúc. Khi Job restart, lần chạy lại có execution mới; metric theo execution vì thế phản ánh từng lần thực thi, còn dashboard có thể tổng hợp theo Job và Step.

Một số phiên bản và cấu hình Spring Batch có tích hợp metric/observation qua Micrometer. Hãy kiểm tra metric sẵn có trước khi tự tạo metric trùng tên. Listener tùy chỉnh hữu ích khi cần thêm business dimension hoặc audit riêng.

## 5. Đo item ở cấp read, process và write

Các listener item cho phép quan sát chi tiết từng giai đoạn.

### ItemReadListener

Các callback:

- beforeRead(): trước khi gọi reader.
- afterRead(item): sau khi đọc được item.
- onReadError(exception): khi thao tác đọc ném lỗi.

~~~java
public class ReadAuditListener implements ItemReadListener<Order> {

    private final ItemAuditService auditService;

    public ReadAuditListener(ItemAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeRead() {
        // Có thể bắt đầu đo thời gian đọc nếu thật sự cần.
    }

    @Override
    public void afterRead(Order item) {
        auditService.recordRead(item.getId());
    }

    @Override
    public void onReadError(Exception exception) {
        auditService.recordReadFailure(
                exception.getClass().getSimpleName());
    }
}
~~~

afterRead chỉ được gọi khi reader trả về item. Khi reader trả null để báo EOF, không có item để chuyển vào callback afterRead. Không dùng afterRead để đếm số lần gọi read() hoặc nhận biết EOF.

### ItemProcessListener

Các callback:

- beforeProcess(item): trước khi processor xử lý item.
- afterProcess(item, result): sau khi processor trả kết quả.
- onProcessError(item, exception): khi processor ném lỗi.

~~~java
public class ProcessMetricsListener
        implements ItemProcessListener<Order, Order> {

    private final MeterRegistry registry;

    public ProcessMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeProcess(Order item) {
        // Không cần ghi metric cho từng item nếu counters tổng hợp đã đủ.
    }

    @Override
    public void afterProcess(Order item, Order result) {
        if (result == null) {
            registry.counter("batch.item.filtered").increment();
        }
    }

    @Override
    public void onProcessError(Order item, Exception exception) {
        registry.counter(
                "batch.item.process.errors",
                "exception", exception.getClass().getSimpleName())
                .increment();
    }
}
~~~

Processor trả null có nghĩa item bị filter. afterProcess nhận result null trong trường hợp này. Filter count của StepExecution cũng có thể được dùng để tổng hợp số item bị lọc, tránh phát metric riêng cho từng item nếu không cần chi tiết.

### ItemWriteListener

Các callback:

- beforeWrite(chunk): trước khi writer ghi chunk.
- afterWrite(chunk): sau khi writer thực hiện ghi thành công.
- onWriteError(exception, chunk): khi writer ném lỗi.

~~~java
public class WriteAuditListener implements ItemWriteListener<Order> {

    private final MeterRegistry registry;

    public WriteAuditListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeWrite(Chunk<? extends Order> chunk) {
        registry.counter("batch.writer.calls").increment();
    }

    @Override
    public void afterWrite(Chunk<? extends Order> chunk) {
        registry.counter("batch.writer.items")
                .increment(chunk.size());
    }

    @Override
    public void onWriteError(
            Exception exception,
            Chunk<? extends Order> chunk) {
        registry.counter(
                "batch.writer.errors",
                "exception", exception.getClass().getSimpleName())
                .increment();
    }
}
~~~

afterWrite cho biết lời gọi writer đã trở về thành công. Không đồng nhất callback này với việc transaction của chunk chắc chắn đã commit. Một lỗi ở bước sau trong cùng transaction vẫn có thể làm chunk rollback. Vì vậy, metric từ afterWrite nên được hiểu là số item writer đã xử lý thành công ở callback, còn số liệu cuối cùng sau Step nên lấy từ StepExecution counters.

Nếu muốn audit một thao tác chỉ khi business transaction commit, hãy thiết kế cơ chế gắn với transaction hoặc transactional outbox thay vì xem afterWrite là tín hiệu commit cuối cùng.

## 6. ChunkListener theo dõi từng chunk

ChunkListener cung cấp các callback:

- beforeChunk(context): trước khi xử lý chunk.
- afterChunk(context): sau khi chunk xử lý thành công.
- afterChunkError(context): khi xử lý chunk gặp lỗi.

~~~java
public class ChunkMetricsListener implements ChunkListener {

    private final MeterRegistry registry;

    public ChunkMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeChunk(ChunkContext context) {
        registry.counter("batch.chunk.started").increment();
    }

    @Override
    public void afterChunk(ChunkContext context) {
        registry.counter("batch.chunk.completed").increment();
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        registry.counter("batch.chunk.errors").increment();
    }
}
~~~

ChunkListener hữu ích khi cần biết số chunk hoàn tất, số chunk gặp lỗi hoặc đo thời gian theo chunk. Nếu đo thời gian, hãy dùng state riêng theo execution/thread; tránh một biến singleton dùng chung khi Step chạy song song.

ChunkListener không cung cấp danh sách item theo cùng cách ItemWriteListener. Nếu cần audit từng item, dùng listener item tương ứng hoặc service nghiệp vụ. Nếu cần số liệu tổng hợp ổn định, StepExecution counters thường đơn giản và ít tốn tài nguyên hơn.

## 7. SkipListener ghi nhận item bị bỏ qua

Khi Step được cấu hình skip, một item lỗi có thể bị bỏ qua để Job tiếp tục. Đây là sự kiện đáng ghi nhận vì đầu ra có thể không bao gồm item đó.

SkipListener có các callback:

- onSkipInRead(exception): lỗi đọc bị skip; framework không có item hợp lệ để truyền vào callback.
- onSkipInProcess(item, exception): item đọc được nhưng lỗi trong processor và được skip.
- onSkipInWrite(item, exception): item được đưa tới writer nhưng lỗi ghi và được skip.

~~~java
public class OrderSkipAuditListener
        implements SkipListener<Order, Order> {

    private final SkipAuditService auditService;

    public OrderSkipAuditListener(SkipAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        auditService.recordReadSkip(
                exception.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable exception) {
        auditService.recordItemSkip(
                item.getId(),
                "PROCESS",
                exception.getClass().getSimpleName());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable exception) {
        auditService.recordItemSkip(
                item.getId(),
                "WRITE",
                exception.getClass().getSimpleName());
    }
}
~~~

SkipListener phù hợp để ghi nhận mã định danh nghiệp vụ và giai đoạn phát sinh lỗi. Không ghi toàn bộ object hoặc nội dung nhạy cảm vào audit nếu không cần thiết.

Spring Batch điều phối callback skip trong lifecycle fault-tolerant của chunk để tránh việc một item bị báo skip lặp do các lần rollback/retry thông thường. Tuy vậy, audit service vẫn nên có khóa chống trùng dựa trên JobExecution/StepExecution, item key và loại skip, đặc biệt nếu audit được gửi sang hệ thống ngoài transaction.

## 8. Đăng ký nhiều listener trong một Step

Có thể đăng ký listener tương ứng bằng các lời gọi listener(...) trên StepBuilder.

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        StepMetricsListener stepMetricsListener,
        ChunkMetricsListener chunkMetricsListener,
        ReadAuditListener readAuditListener,
        ProcessMetricsListener processMetricsListener,
        WriteAuditListener writeAuditListener,
        OrderSkipAuditListener skipAuditListener,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(stepMetricsListener)
            .listener(chunkMetricsListener)
            .listener(readAuditListener)
            .listener(processMetricsListener)
            .listener(writeAuditListener)
            .listener(skipAuditListener)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(20)
            .build();
}
~~~

Đoạn cấu hình minh họa các loại listener có thể đăng ký cùng Step. Trong ứng dụng thật, chỉ đăng ký listener cần thiết; tránh tạo nhiều callback cho cùng một sự kiện nếu chúng ghi cùng metric hoặc audit.

Job-level listener được đăng ký trên JobBuilder, còn listener cấp Step được đăng ký trên StepBuilder. Có thể tách listener thành bean riêng để dễ kiểm thử và cấu hình theo môi trường.

## 9. Phân biệt metric, technical audit và business audit

Ba loại dữ liệu này có yêu cầu lưu trữ khác nhau.

| Loại | Câu hỏi cần trả lời | Ví dụ trường dữ liệu |
|---|---|---|
| Metric | Job chạy nhanh/chậm thế nào? | Duration, read/write count, error count |
| Technical audit | Lần thực thi nào đã xảy ra? | JobExecution ID, Step, status, thời điểm |
| Business audit | Hành động nghiệp vụ nào đã được thực hiện? | Mã lô, business key, hành động, kết quả |

Metric thường được tổng hợp và giữ theo retention ngắn hoặc trung bình. Technical audit cần truy vết execution theo thời gian. Business audit có thể phải đáp ứng yêu cầu kiểm toán hoặc lưu trữ dài hạn.

Không nên dùng metric để thay thế audit vì metric thường không lưu từng sự kiện. Ngược lại, không nên tạo một bản ghi audit cho mọi item nếu chỉ cần biết tổng số item; lượng dữ liệu audit có thể tăng rất nhanh.

## 10. Thiết kế bản ghi audit

Một bản ghi technical audit có thể chứa:

- Tên Job và Step.
- JobInstance ID, JobExecution ID và StepExecution ID.
- Mã batch hoặc business key không nhạy cảm.
- Sự kiện: STARTED, COMPLETED, FAILED, SKIPPED.
- Thời điểm phát sinh.
- BatchStatus và ExitStatus.
- Read/write/filter/skip counts khi phù hợp.
- Mã lỗi hoặc loại exception đã được chuẩn hóa.
- Correlation ID để liên kết log và request khởi chạy.

Ví dụ JSON audit:

~~~json
{
  "event": "STEP_COMPLETED",
  "jobName": "importOrdersJob",
  "jobExecutionId": 108,
  "stepExecutionId": 214,
  "stepName": "writeOrdersStep",
  "status": "COMPLETED",
  "readCount": 1200,
  "writeCount": 1185,
  "filterCount": 15,
  "skipCount": 0
}
~~~

Đây là ví dụ minh họa cấu trúc; tên trường và định dạng có thể điều chỉnh theo hệ thống audit. Nên giữ mã định danh execution để đối chiếu với JobRepository và tránh đưa dữ liệu cá nhân hoặc secret không cần thiết vào event.

## 11. Audit và transaction: listener không tự tạo tính nguyên tử

Đây là điểm cần chú ý nhất khi ghi audit từ listener.

Callback afterWrite được gọi sau khi writer trả về, nhưng transaction của chunk có thể chưa commit. Nếu listener gửi audit event đến một hệ thống ngoài rồi transaction database rollback, audit có thể nói rằng item đã được ghi trong khi business data thực tế không được commit.

Tương tự, nếu listener ghi audit bằng một transaction database độc lập, audit có thể được commit dù business transaction thất bại. Đó có thể là điều mong muốn với technical audit ghi nhận lỗi, nhưng không tương đương business audit xác nhận dữ liệu đã commit.

Cần chọn chiến lược theo mục đích:

### Technical audit ghi nhận lần chạy và lỗi

Có thể ghi sự kiện bắt đầu, kết thúc và lỗi trong một kho audit riêng. Cần xác định chính sách nếu audit store không sẵn sàng: có làm Job thất bại, retry ghi audit hay chỉ log cảnh báo. Với yêu cầu audit bắt buộc, không nên âm thầm bỏ qua lỗi ghi audit.

### Business audit phải nguyên tử với dữ liệu

Nếu cần bảo đảm business row và audit row cùng commit hoặc cùng rollback, hãy ghi cả hai trong cùng transaction resource. Một cách là ghi audit/outbox row trong writer hoặc service nghiệp vụ đang tham gia chunk transaction.

~~~text
Chunk transaction
       |
       +--> INSERT business order
       |
       +--> INSERT audit/outbox event
       |
       v
     COMMIT
       |
       v
Publisher đọc outbox và phát event
~~~

Publisher có thể gửi event sau commit. Nếu gửi thất bại, nó thử lại; phía nhận nên hỗ trợ idempotency hoặc deduplication. Cách này giảm nguy cơ audit event đã phát nhưng business transaction chưa commit.

### Audit sau commit

Có thể dùng transaction synchronization hoặc outbox để thực hiện hành động sau commit. Tuy nhiên, callback sau commit và ghi audit vào hệ thống khác vẫn có thể gặp lỗi giữa chừng. Outbox thường phù hợp khi cần bảo đảm event không bị mất sau khi business transaction đã commit.

Không dùng listener như một bảo đảm exactly-once cho tác động bên ngoài. Cần khóa chống trùng và khả năng retry/đối soát.

## 12. Ghi metric bằng Micrometer

Micrometer cung cấp các loại meter thường dùng:

- **Counter:** đếm số sự kiện hoặc số item.
- **Timer:** đo thời gian và số lần thực hiện.
- **Gauge:** quan sát giá trị hiện tại, chẳng hạn số Job đang chạy nếu có nguồn state phù hợp.
- **DistributionSummary:** thống kê phân bố giá trị như payload size hoặc số item trong chunk.

Ví dụ đo dung lượng chunk:

~~~java
DistributionSummary chunkSizeSummary =
        DistributionSummary.builder("batch.chunk.payload.bytes")
                .tag("job", "importOrdersJob")
                .tag("step", "writeOrdersStep")
                .register(registry);

chunkSizeSummary.record(payloadBytes);
~~~

Có thể ghi nhận kích thước chunk, thời gian writer hoặc số item trong mỗi chunk để tìm ra điểm nghẽn. Hãy chọn meter có ý nghĩa và đơn vị rõ ràng; ví dụ byte nên đặt tên hoặc mô tả đơn vị nhất quán.

### Tránh cardinality quá cao

Không đưa các giá trị thay đổi liên tục vào metric tag:

- JobExecution ID hoặc StepExecution ID.
- Customer ID, Order ID hoặc file path.
- Request ID hoặc correlation ID.
- Tên exception chứa nội dung động.
- Giá trị JobParameters tùy ý.

Mỗi bộ tag tạo một time series riêng. Nếu gắn ID của từng execution hoặc từng item vào metric, số lượng series có thể tăng rất lớn, làm tốn bộ nhớ và tải lên hệ thống metrics.

Hãy dùng tag có tập giá trị giới hạn như job name, step name, status, environment và loại lỗi đã chuẩn hóa. Đưa ID chi tiết vào log hoặc audit event.

## 13. Correlation ID và logging context

Khi Job được khởi chạy từ HTTP request, scheduler hoặc message broker, correlation ID giúp liên kết log của request với log trong Job và Step.

Có thể đưa correlation ID vào JobParameters dạng non-identifying nếu giá trị đó không thay đổi danh tính JobInstance. Tuy nhiên, non-identifying parameter vẫn có thể được lưu trong metadata; chỉ dùng giá trị không nhạy cảm.

Listener có thể đưa JobExecution ID hoặc correlation ID vào logging context, chẳng hạn MDC của SLF4J:

~~~java
public class StepLoggingListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution execution) {
        MDC.put("jobExecutionId",
                String.valueOf(execution.getJobExecutionId()));
        MDC.put("stepExecutionId",
                String.valueOf(execution.getId()));
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        MDC.remove("jobExecutionId");
        MDC.remove("stepExecutionId");
        return execution.getExitStatus();
    }
}
~~~

Luôn dọn MDC khi Step kết thúc để tránh dữ liệu của execution trước bị giữ lại trên thread được tái sử dụng. Nếu Step xử lý đa luồng hoặc chuyển công việc sang executor khác, MDC không tự động truyền sang thread mới; cần cơ chế truyền context phù hợp và dọn ở từng thread.

Không đưa token, password hoặc nội dung nhạy cảm vào MDC. Mọi log phát sinh trên thread có thể tự động đính kèm các giá trị MDC.

## 14. Listener và retry/skip

Trong fault-tolerant Step, một thao tác có thể được retry trước khi thành công hoặc bị skip. Vì vậy, callback listener không phải lúc nào cũng tương ứng với một kết quả nghiệp vụ cuối cùng.

Ví dụ:

~~~text
Item A:
  processor được gọi
  writer ghi thành công
  chunk commit

Item B:
  writer được gọi
  lỗi tạm thời
  rollback
  retry
  writer thành công
  chunk commit
~~~

Một số callback có thể được gọi nhiều lần do retry. Nếu mỗi lần callback đều tạo một audit event bên ngoài transaction, hệ thống audit có thể ghi nhiều sự kiện cho cùng một item.

Để tránh nhầm lẫn:

- Dùng StepExecution counters để báo cáo kết quả tổng hợp cuối Step.
- Dùng SkipListener để ghi nhận item thực sự bị skip theo lifecycle của Spring Batch.
- Gắn khóa chống trùng cho audit event theo execution, item và loại sự kiện.
- Không coi beforeWrite/afterWrite là bằng chứng chunk đã commit.
- Ghi rõ attempt number nếu cần theo dõi từng lần thử, nhưng không dùng attempt metric thay cho kết quả cuối.

Nếu cần theo dõi retry chi tiết, có thể tích hợp listener của Spring Retry hoặc cơ chế quan sát tương ứng với phiên bản/cấu hình fault tolerance. Chỉ bổ sung khi cần biết số lần thử và nguyên nhân retry; tránh ghi log cho mọi lần retry nếu lượng dữ liệu lớn.

## 15. Hiệu năng khi listener chạy trên từng item

Listener item có thể được gọi hàng triệu lần trong một Job. Một thao tác nhỏ như ghi log đồng bộ, gọi HTTP hoặc insert một audit row cho mỗi item có thể làm chậm đáng kể Step.

Các nguyên tắc:

- Không gọi dịch vụ mạng đồng bộ từ callback item nếu không thực sự cần.
- Tránh tạo object, format chuỗi hoặc serialize payload lớn cho mỗi item khi metric tổng hợp là đủ.
- Dùng counters/timers được tái sử dụng qua MeterRegistry.
- Ghi audit chi tiết theo yêu cầu nghiệp vụ; cân nhắc batch insert hoặc outbox.
- Không log từng item ở mức INFO trong Job lớn.
- Dùng sampling hoặc log mức DEBUG cho dữ liệu chẩn đoán có khối lượng cao.
- Không làm listener giữ lock chung khiến các worker thread phải chờ nhau.

Nếu listener cập nhật state mutable, cần xác định Step có chạy đa luồng không. Listener singleton có thể được nhiều execution dùng chung; không đặt state theo execution trong field mutable của singleton nếu không có cơ chế cô lập hoặc đồng bộ.

## 16. Xử lý lỗi khi ghi metric hoặc audit

Metric và audit không nên làm thay đổi kết quả Job một cách bất ngờ. Cần có chính sách rõ ràng cho từng loại dữ liệu.

| Loại ghi nhận | Khi dịch vụ đích lỗi | Chính sách có thể chọn |
|---|---|---|
| Metric vận hành | Registry/exporter tạm lỗi | Ưu tiên không chặn xử lý; dùng cơ chế buffering/export phù hợp |
| Technical audit bắt buộc | Audit store không ghi được | Có thể fail Job hoặc ghi vào durable fallback theo yêu cầu |
| Business audit nguyên tử | Ghi outbox thất bại | Rollback business transaction cùng chunk |
| Log chẩn đoán | Logging backend tạm lỗi | Dùng appender/buffering theo cấu hình; không log secret |

Không bắt và bỏ qua mọi exception trong listener. Nếu audit là yêu cầu bắt buộc, im lặng bỏ qua lỗi sẽ tạo lỗ hổng truy vết. Ngược lại, nếu metric là telemetry hỗ trợ, làm Job thất bại chỉ vì exporter tạm thời không sẵn sàng có thể không phù hợp.

Tách rõ metric, technical audit và business audit giúp quyết định đúng việc lỗi quan sát có được phép ảnh hưởng đến xử lý nghiệp vụ hay không.

## 17. Bảo vệ dữ liệu trong metric và audit

Listener thường có quyền truy cập JobParameters, item và exception. Đây là các nguồn có thể chứa thông tin nhạy cảm.

Không ghi vào metric, log hoặc audit:

- Password, API token, private key và credential.
- Toàn bộ request/response body nếu có dữ liệu cá nhân.
- Dữ liệu thanh toán hoặc định danh cá nhân không cần thiết.
- Nội dung exception có thể chứa câu SQL hoặc tham số nhạy cảm.
- Toàn bộ JobParameters nếu không kiểm soát nội dung.

Ưu tiên ghi mã định danh nghiệp vụ đã được phê duyệt, trạng thái, loại lỗi và execution ID. Giới hạn quyền đọc audit store và áp dụng retention theo yêu cầu của tổ chức.

## 18. Kiểm thử listener

Listener nên được kiểm thử ở hai cấp.

### Unit test

Kiểm tra listener nhận đúng callback và phát metric/audit đúng dữ liệu. Có thể mock AuditService hoặc dùng SimpleMeterRegistry để kiểm tra counter/timer.

~~~java
@Test
void afterStepRecordsReadAndWriteCounts() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    StepMetricsListener listener = new StepMetricsListener(registry);

    JobInstance instance = new JobInstance(1L, "importOrdersJob");
    JobExecution jobExecution = new JobExecution(instance);
    StepExecution execution =
            new StepExecution("writeOrdersStep", jobExecution);

    execution.setReadCount(120L);
    execution.setWriteCount(115L);
    execution.setFilterCount(5L);
    execution.setStatus(BatchStatus.COMPLETED);

    listener.beforeStep(execution);
    ExitStatus result = listener.afterStep(execution);

    assertEquals(ExitStatus.COMPLETED, result);
    assertEquals(
            120.0,
            registry.get("batch.step.items.read").counter().count());
    assertEquals(
            115.0,
            registry.get("batch.step.items.written").counter().count());
}
~~~

Test minh họa cách kiểm tra metric sau callback. Trong test thực tế, cần cấu hình các trường bắt buộc phù hợp với phiên bản Spring Batch đang dùng.

### Integration test

Chạy một Job/Step thật và xác nhận:

- beforeJob/afterJob được gọi ở đúng vòng đời.
- beforeStep/afterStep ghi đúng trạng thái và execution ID.
- Item listener được gọi khi đọc, xử lý và ghi item.
- SkipListener ghi nhận đúng loại skip.
- Chunk listener ghi nhận chunk hoàn tất và lỗi.
- Retry không tạo audit trùng ngoài ý muốn.
- Job thất bại vẫn có technical audit kết thúc phù hợp.
- Listener không làm thay đổi ExitStatus ngoài chủ đích.
- Metric không tạo tag có cardinality quá cao.
- MDC được dọn sau khi Step kết thúc.

Nên có test cho Job hoàn thành, Job thất bại, Step bị skip và Job restart. Với audit outbox, xác nhận business row và outbox row commit hoặc rollback cùng nhau.

## 19. Quan sát Job sau khi đã chạy

Listener ghi metric và audit trong lúc thực thi. Để truy vấn lịch sử, có thể kết hợp dữ liệu đó với metadata từ JobRepository và JobExplorer.

JobExplorer cho phép đọc JobInstance, JobExecution và StepExecution đã lưu. Metadata cung cấp trạng thái và counters chuẩn của Spring Batch; audit store cung cấp các sự kiện chi tiết hoặc business context; hệ thống metrics cung cấp xu hướng theo thời gian.

Một dashboard vận hành có thể hiển thị:

| Nhóm | Chỉ số |
|---|---|
| Job | Số lần chạy, completed/failed, duration |
| Step | Duration, read/write/filter/skip count |
| Chunk | Số chunk hoàn tất, rollback, thời gian chunk |
| Writer | Số lần gọi, item ghi, lỗi ghi |
| Audit | Execution ID, business key, kết quả, sự kiện skip |
| Hệ thống | Queue lag, database latency, CPU và memory liên quan |

Không dùng metric thay cho lịch sử execution chi tiết. Khi điều tra một lần chạy cụ thể, truy vấn theo JobExecution ID và đối chiếu metadata, log và audit event.

## 20. Quy trình triển khai listener cho metric và audit

Khi thiết kế quan sát cho một Job, hãy thực hiện theo thứ tự:

1. Xác định cần quan sát cấp Job, Step, chunk hay item.
2. Chọn listener interface phù hợp với callback cần dùng.
3. Dùng StepExecution counters cho số liệu tổng hợp thay vì đếm thủ công nếu đã có sẵn.
4. Dùng Micrometer Timer, Counter hoặc DistributionSummary cho metric cần xuất ra monitoring.
5. Giữ metric tags có cardinality thấp; đưa execution ID vào log/audit.
6. Xác định technical audit và business audit có yêu cầu transaction khác nhau ra sao.
7. Dùng outbox hoặc cùng transaction resource nếu audit phải nguyên tử với business data.
8. Tạo idempotency key cho audit event có thể được retry hoặc phát lại.
9. Xác định chính sách khi metric/audit store không sẵn sàng.
10. Kiểm thử Job thành công, thất bại, skip, retry, restart và chạy song song.

Listener giúp quan sát lifecycle của Spring Batch tại đúng điểm xử lý. StepExecutionListener và JobExecutionListener phù hợp với metric tổng hợp và audit execution; listener item và chunk cung cấp chi tiết hơn; SkipListener ghi nhận item bị bỏ qua. Khi phân biệt rõ callback, transaction boundary, metric cardinality và yêu cầu audit, ứng dụng có thể theo dõi Job hiệu quả mà không làm sai lệch kết quả xử lý.

