# StepExecutionListener trước và sau step

Trong Spring Batch, `StepExecutionListener` cho phép ứng dụng thực hiện logic tại hai thời điểm quan trọng trong vòng đời của một Step: ngay trước khi Step bắt đầu xử lý và sau khi Step kết thúc. Listener nhận đối tượng `StepExecution`, nhờ đó có thể đọc trạng thái, JobParameters, ExecutionContext, thời gian và các counter của Step.

`beforeStep()` thường dùng để ghi nhận thông tin bắt đầu, kiểm tra điều kiện runtime hoặc chuẩn bị dữ liệu phụ thuộc vào StepExecution. `afterStep()` thường dùng để ghi log kết quả, tổng hợp metric hoặc điều chỉnh `ExitStatus` nhằm định tuyến flow của Job. `afterStep()` được gọi khi Step kết thúc, kể cả khi Step thất bại, nên cần kiểm tra trạng thái trước khi thực hiện logic chỉ dành cho trường hợp thành công.

## 1. StepExecutionListener là gì?

`StepExecutionListener` là listener ở cấp Step. Nó cung cấp callback trước và sau một lần thực thi Step:

```java
public interface StepExecutionListener extends StepListener {

    void beforeStep(StepExecution stepExecution);

    ExitStatus afterStep(StepExecution stepExecution);
}
```

Hai callback nhận cùng một loại đối tượng `StepExecution`, nhưng được gọi ở hai thời điểm khác nhau:

| Callback | Thời điểm | Mục đích thường gặp |
|---|---|---|
| `beforeStep()` | Trước khi Step bắt đầu phần xử lý chính | Ghi log bắt đầu, đọc JobParameters, kiểm tra điều kiện, chuẩn bị thông tin runtime |
| `afterStep()` | Sau khi Step kết thúc xử lý | Ghi log kết quả, đọc counter, tổng hợp lỗi, trả ExitStatus tùy chỉnh |

`StepExecution` đại diện cho một lần thực thi cụ thể của Step. Nó chứa tên Step, ID, trạng thái `BatchStatus`, `ExitStatus`, thời gian bắt đầu/kết thúc, ExecutionContext và các counter như số item đã đọc, ghi, filter, skip, commit hoặc rollback.

Listener không phải là một Step riêng trong Job. Nó được đăng ký vào Step và được framework gọi trong vòng đời của Step đó.

## 2. Vòng đời gọi beforeStep và afterStep

Khi Job chạy một Step, Spring Batch tạo hoặc lấy `StepExecution` tương ứng rồi gọi listener trước khi bắt đầu xử lý Step. Sau khi Step hoàn tất hoặc thất bại, framework gọi listener sau Step với metadata của lần thực thi.

```text
JobLauncher
    |
    v
Job bắt đầu Step
    |
    v
Tạo / chuẩn bị StepExecution
    |
    v
beforeStep(stepExecution)
    |
    v
Mở stream và thực thi Step
    |
    +--> Tasklet hoặc chunk processing
    |       |
    |       +--> đọc / process / write / commit
    |
    v
Step kết thúc: COMPLETED / FAILED / STOPPED / ...
    |
    v
afterStep(stepExecution)
    |
    v
Hoàn tất cập nhật metadata và tiếp tục Job flow
```

`beforeStep()` được gọi một lần cho một StepExecution. Với chunk-oriented Step, nó không được gọi trước mỗi chunk hay trước mỗi item. Tương tự, `afterStep()` được gọi ở cấp Step, không phải sau từng lần writer ghi chunk.

`afterStep()` được gọi khi Step kết thúc, bao gồm trường hợp xử lý thất bại. Vì vậy, callback này là nơi phù hợp để ghi nhận kết quả cuối cùng hoặc phân loại trạng thái, nhưng không nên giả định Step luôn thành công khi callback được gọi.

## 3. Cài đặt StepExecutionListener bằng interface

Ví dụ listener ghi log thời điểm bắt đầu và kết quả sau Step:

```java
public class ImportStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        String businessDate = stepExecution.getJobParameters()
                .getString("businessDate");

        log.info(
                "Starting step={}, executionId={}, businessDate={}",
                stepExecution.getStepName(),
                stepExecution.getId(),
                businessDate
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Finished step={}, status={}, exitStatus={}, read={}, written={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

Trong `beforeStep()`, listener có thể đọc JobParameters thông qua `StepExecution`. Đây là cách lấy tham số runtime mà không cần giữ chúng trong mutable field của listener.

Trong `afterStep()`, listener đọc trạng thái và counter sau khi phần xử lý Step đã kết thúc. Ví dụ ghi log trên giúp liên kết log với `StepExecution` ID cụ thể, hữu ích khi một JobInstance có nhiều lần restart.

## 4. Đăng ký listener vào Step

Listener cần được đăng ký trong cấu hình Step để Spring Batch gọi callback. Với Java configuration hiện đại:

```java
@Bean
public ImportStepListener importStepListener() {
    return new ImportStepListener();
}

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer,
        ImportStepListener listener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(listener)
            .build();
}
```

Lời gọi `.listener(listener)` đăng ký listener vào Step. Khi Step được thực thi, Spring Batch gọi `beforeStep()` và `afterStep()` theo vòng đời tương ứng.

Một listener có thể được đăng ký vào nhiều Step nếu logic của nó dùng chung được. Tuy nhiên, cần tránh giữ trạng thái riêng của một lần chạy trong field mutable của singleton listener. Dữ liệu runtime nên được đọc từ `StepExecution` hoặc lưu trong ExecutionContext thích hợp.

## 5. Dùng annotation @BeforeStep và @AfterStep

Spring Batch cũng hỗ trợ annotation để khai báo callback trên bean listener. Cách này hữu ích khi muốn giữ logic listener trong một component mà không cần triển khai trực tiếp interface:

```java
@Component
public class ImportAuditListener {

    @BeforeStep
    public void beforeStep(StepExecution stepExecution) {
        log.info(
                "Starting {} with executionId={}",
                stepExecution.getStepName(),
                stepExecution.getId()
        );
    }

    @AfterStep
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Step {} ended with {}",
                stepExecution.getStepName(),
                stepExecution.getStatus()
        );

        return stepExecution.getExitStatus();
    }
}
```

Đăng ký bean này vào Step bằng `.listener(importAuditListener)`. Các annotation chỉ định phương thức callback; chúng không tự động khiến mọi bean trong application context trở thành listener của mọi Step.

Khi dùng annotation, chữ ký phương thức cần phù hợp với callback: `@BeforeStep` nhận `StepExecution` và trả về `void`; `@AfterStep` nhận `StepExecution` và có thể trả về `ExitStatus`.

## 6. Những dữ liệu có thể đọc từ StepExecution

`StepExecution` cung cấp metadata của lần thực thi Step. Một số getter thường dùng:

| Getter | Thông tin |
|---|---|
| `getId()` | ID của StepExecution |
| `getStepName()` | Tên Step |
| `getJobExecution()` | JobExecution chứa StepExecution này |
| `getJobParameters()` | JobParameters của lần chạy Job |
| `getStatus()` | BatchStatus của Step |
| `getExitStatus()` | ExitStatus hiện tại của Step |
| `getStartTime()` | Thời điểm bắt đầu |
| `getEndTime()` | Thời điểm kết thúc, nếu đã kết thúc |
| `getReadCount()` | Số item đọc thành công |
| `getWriteCount()` | Số item ghi thành công |
| `getFilterCount()` | Số item bị processor filter |
| `getSkipCount()` | Tổng số item bị skip |
| `getCommitCount()` | Số lần commit được ghi nhận |
| `getRollbackCount()` | Số lần rollback được ghi nhận |
| `getExecutionContext()` | Step-level ExecutionContext |

Ví dụ, listener có thể ghi metric sau Step:

```java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    log.info(
            "step={}, read={}, write={}, filter={}, skip={}, commit={}, rollback={}",
            stepExecution.getStepName(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getSkipCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount()
    );

    return stepExecution.getExitStatus();
}
```

Không nên suy ra số item đã commit chỉ từ `writeCount` hoặc số transaction chỉ từ `readCount`. Filter, skip, retry, rollback và chunk cuối nhỏ hơn commit interval có thể làm các counter khác nhau.

## 7. Phân biệt BatchStatus và ExitStatus

Hai trạng thái này có ý nghĩa khác nhau:

- `BatchStatus` mô tả trạng thái vòng đời Step do Spring Batch quản lý, chẳng hạn `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` hoặc `ABANDONED`.
- `ExitStatus` mô tả kết quả thoát của Step bằng exit code và mô tả. Nó thường được dùng để quyết định nhánh tiếp theo trong Job flow.

Ví dụ, Step có thể hoàn tất về mặt kỹ thuật nhưng có một số item bị skip. Khi đó, `BatchStatus` vẫn có thể là `COMPLETED`, trong khi ứng dụng muốn đặt `ExitStatus` thành `COMPLETED_WITH_SKIPS` để Job flow chuyển sang nhánh xử lý phù hợp.

`afterStep()` có thể trả về một `ExitStatus` tùy chỉnh. Spring Batch kết hợp kết quả trả về với ExitStatus hiện tại của Step. Ví dụ:

```java
public class SkipStatusListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Không cần xử lý trước Step.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Step completed with skipped items"
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

Listener chỉ gán mã kết quả để mô tả trường hợp hoàn tất có skip. Nó không biến một Step `FAILED` thành `COMPLETED`, vì điều kiện trong ví dụ chỉ áp dụng khi `BatchStatus` là `COMPLETED`.

Nếu logic nghiệp vụ thực sự thất bại, hãy để exception trong Tasklet/chunk làm Step thất bại hoặc dùng cơ chế dừng phù hợp. Không nên chỉ sửa `ExitStatus` thành `FAILED` trong listener rồi giả định `BatchStatus` cũng đã đổi theo.

## 8. Dùng ExitStatus để định tuyến Job flow

Job flow có thể dựa trên exit code của Step để chọn bước tiếp theo. Listener có thể phân loại kết quả, còn Job definition quyết định nhánh tương ứng.

Ví dụ về các nhánh logic:

```text
importOrdersStep
    |
    +-- COMPLETED ----------------------> nextStep
    |
    +-- COMPLETED_WITH_SKIPS -----------> reviewSkippedOrdersStep
    |
    +-- FAILED -------------------------> errorHandlingStep / Job failed
```

Với Java flow builder, có thể khai báo transition theo exit code:

```java
@Bean
public Job importJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step reviewSkippedOrdersStep,
        Step nextStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importOrdersStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedOrdersStep)
            .from(importOrdersStep)
                .on("COMPLETED").to(nextStep)
            .from(importOrdersStep)
                .on("*").fail()
            .end()
            .build();
}
```

Đoạn flow trên minh họa cách chọn transition theo exit code; cần khai báo đầy đủ các nhánh phù hợp với Job thực tế. Nếu dùng wildcard `*`, hãy đặt các transition cụ thể trước để kết quả được phân loại như mong muốn.

Không nên nhầm tên exit code với `BatchStatus`. Flow transition thường so khớp `ExitStatus.exitCode`, vì vậy nếu listener trả `COMPLETED_WITH_SKIPS` thì transition phải dùng đúng chuỗi đó.

## 9. Dùng beforeStep để đọc tham số và chuẩn bị dữ liệu

`beforeStep()` phù hợp để đọc tham số đầu vào hoặc chuẩn bị thông tin cần thiết cho phần xử lý của Step. Ví dụ, listener kiểm tra ngày nghiệp vụ:

```java
public class BusinessDateListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        String businessDate = stepExecution.getJobParameters()
                .getString("businessDate");

        if (businessDate == null || businessDate.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }

        log.info("Preparing Step for businessDate={}", businessDate);
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        return stepExecution.getExitStatus();
    }
}
```

Kiểm tra điều kiện trước khi Step bắt đầu giúp phát hiện lỗi cấu hình sớm. Tuy nhiên, validation quan trọng của JobParameters cũng nên được đặt ở tầng khởi chạy hoặc `JobParametersValidator` khi phù hợp, để yêu cầu không hợp lệ bị từ chối trước khi Job bắt đầu.

Không nên đặt công việc nghiệp vụ lớn hoặc side effect khó hoàn tác vào `beforeStep()`. Callback này không phải một chunk transaction; nếu nó gọi API hoặc ghi file rồi Step thất bại, side effect có thể đã xảy ra. Hãy dùng Tasklet hoặc Step riêng nếu thao tác cần transaction, retry, skip hoặc checkpoint rõ ràng.

## 10. Dùng afterStep để tổng hợp kết quả

`afterStep()` là nơi thuận tiện để đọc counter cuối cùng và ghi nhận kết quả. Ví dụ, nếu số item bị skip vượt một ngưỡng, ứng dụng có thể đặt exit code riêng để yêu cầu bước review:

```java
public class ImportResultListener implements StepExecutionListener {

    private final int warningThreshold;

    public ImportResultListener(int warningThreshold) {
        this.warningThreshold = warningThreshold;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info("Import Step started: {}", stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        int skipped = stepExecution.getSkipCount();

        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && skipped > warningThreshold) {
            return new ExitStatus(
                    "COMPLETED_WITH_WARNINGS",
                    "Skipped item count exceeded threshold: " + skipped
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

Listener này chỉ phân loại kết quả sau khi Step hoàn tất. Nếu cần gửi thông báo hoặc cập nhật hệ thống ngoài, cần cân nhắc thời điểm transaction đã commit và khả năng retry của thao tác. `afterStep()` không nên được xem là callback sau commit của mọi resource bên ngoài.

## 11. beforeStep và afterStep khác với listener ở cấp item/chunk

Spring Batch có nhiều loại listener, mỗi loại phù hợp với một phạm vi:

| Listener | Phạm vi | Callback tiêu biểu |
|---|---|---|
| `JobExecutionListener` | Một lần thực thi Job | `beforeJob`, `afterJob` |
| `StepExecutionListener` | Một lần thực thi Step | `beforeStep`, `afterStep` |
| `ChunkListener` | Một chunk | `beforeChunk`, `afterChunk`, `afterChunkError` |
| `ItemReadListener` | Một lần đọc item | `beforeRead`, `afterRead`, `onReadError` |
| `ItemProcessListener` | Một lần xử lý item | `beforeProcess`, `afterProcess`, `onProcessError` |
| `ItemWriteListener` | Một lần gọi writer cho chunk | `beforeWrite`, `afterWrite`, `onWriteError` |

Nếu muốn ghi log một lần khi Step bắt đầu, dùng `StepExecutionListener`. Nếu muốn đo thời gian từng chunk hoặc quan sát lỗi từng lần ghi, dùng listener ở phạm vi chunk hoặc item tương ứng. Không dùng `afterStep()` để thay thế `afterWrite()` hay `afterChunk()` vì callback chỉ chạy một lần ở cuối Step.

## 12. ExecutionContext và dữ liệu listener cần giữ

Nếu listener cần truyền một giá trị từ đầu Step đến cuối Step, có thể dùng field trong object khi chắc chắn listener chỉ phục vụ một execution và không chạy đồng thời. Tuy nhiên, với bean singleton dùng chung hoặc Step chạy song song, mutable field có thể bị chia sẻ ngoài ý muốn.

Đối với state cần tồn tại qua restart hoặc cần được lưu trong metadata, hãy dùng Step `ExecutionContext`:

```java
public class StepStateListener implements StepExecutionListener {

    private static final String START_MARKER = "audit.started";

    @Override
    public void beforeStep(StepExecution stepExecution) {
        stepExecution.getExecutionContext().putString(
                START_MARKER,
                Instant.now().toString()
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        String startedAt = stepExecution.getExecutionContext()
                .getString(START_MARKER, "unknown");

        log.info("Step startedAt={}", startedAt);
        return stepExecution.getExitStatus();
    }
}
```

Ví dụ trên minh họa truy cập Step context. Nếu dữ liệu chỉ phục vụ log, có thể dùng `StepExecution.getStartTime()` thay vì lưu một bản sao. Nếu cần dữ liệu bền vững qua restart, phải hiểu thời điểm context được lưu bởi JobRepository; thay đổi trong bộ nhớ không đồng nghĩa đã được ghi xuống database ngay lập tức.

## 13. Những lưu ý về exception và side effect trong listener

Listener tham gia vòng đời Step nhưng không thay thế transaction logic của Tasklet hoặc chunk. Cần cẩn thận với exception và side effect:

- Không dùng exception trong `afterStep()` làm cơ chế chính để biến một Step đã chạy thành thất bại. Hãy để lỗi nghiệp vụ xảy ra trong phần thực thi Step hoặc trả ExitStatus phù hợp cho flow.
- Không giả định `afterStep()` chỉ được gọi khi Step thành công; luôn kiểm tra `BatchStatus` trước khi xử lý kết quả thành công.
- Không gửi email, gọi API tạo giao dịch hoặc publish message mà không có cơ chế chống lặp. Listener có thể được gọi lại trong một lần thực thi Step khác khi Job restart.
- Không ghi một trạng thái thành công bên ngoài transaction rồi giả định Step metadata chắc chắn đã commit.
- Không giữ mutable state của execution trong singleton listener nếu nhiều StepExecution có thể chạy đồng thời.
- Không thay đổi `BatchStatus` tùy tiện trong listener. Dùng `ExitStatus` để phân loại kết quả và dùng cơ chế xử lý lỗi của Step để biểu diễn thất bại thực sự.

Nếu cần thực hiện side effect sau khi dữ liệu đã commit, hãy dùng cơ chế transaction synchronization phù hợp, outbox hoặc Step riêng. Dù dùng listener nào, thao tác bên ngoài vẫn cần idempotency nếu có khả năng được thử lại.

## 14. Những nhầm lẫn thường gặp

**Cho rằng `beforeStep()` chạy trước mỗi chunk.** Callback này chạy một lần ở đầu StepExecution. Muốn xử lý trước từng chunk, dùng `ChunkListener`.

**Cho rằng `afterStep()` chỉ chạy khi thành công.** Callback được gọi khi Step kết thúc kể cả khi thất bại. Hãy kiểm tra `stepExecution.getStatus()`.

**Cho rằng trả ExitStatus mới sẽ thay đổi BatchStatus.** ExitStatus mô tả kết quả và định tuyến flow; BatchStatus mô tả trạng thái vòng đời. Hai trường không đồng nhất.

**Cho rằng listener tự động được áp dụng cho mọi Step.** Cần đăng ký listener vào Step hoặc cấu hình theo cơ chế phù hợp.

**Giữ StepExecution trong field của singleton listener.** Nhiều execution có thể chạy đồng thời và ghi đè dữ liệu của nhau. Dùng tham số callback làm nguồn dữ liệu.

**Gửi thông báo thành công trong `afterStep()` mà không xét commit.** Callback sau Step không bảo đảm mọi side effect ngoài transaction đã được commit theo cùng một đơn vị atomic.

**Dùng listener để thực hiện toàn bộ nghiệp vụ của Step.** Listener phù hợp với lifecycle, quan sát và phân loại kết quả. Công việc nghiệp vụ cần transaction/restart rõ ràng nên nằm trong Tasklet hoặc reader/processor/writer.

## 15. Chọn callback phù hợp

Dùng `beforeStep()` khi cần biết StepExecution nào sắp chạy, đọc JobParameters, ghi nhận thông tin bắt đầu hoặc kiểm tra điều kiện runtime nhẹ. Dùng `afterStep()` khi cần đọc trạng thái và counter cuối cùng, ghi log kết quả hoặc trả `ExitStatus` tùy chỉnh để Job flow chọn nhánh tiếp theo.

Nếu cần xử lý theo từng chunk hoặc từng item, chọn listener đúng phạm vi. Nếu cần thực hiện nghiệp vụ có transaction, retry, skip hoặc checkpoint, đặt logic trong Step thay vì dựa vào callback lifecycle. Hiểu rõ thời điểm gọi và sự khác nhau giữa `BatchStatus` với `ExitStatus` giúp `StepExecutionListener` trở thành công cụ hữu ích để giám sát và điều khiển Job flow.
