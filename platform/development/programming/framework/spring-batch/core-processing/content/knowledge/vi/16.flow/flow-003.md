# Conditional transition theo ExitStatus

Trong Spring Batch, Job có thể chọn Step tiếp theo dựa trên kết quả của Step vừa chạy. Cơ chế này được gọi là *conditional transition*. Thay vì luôn chạy một chuỗi Step cố định, Job flow kiểm tra `ExitStatus` của Step hiện tại rồi đi theo nhánh phù hợp.

Ví dụ, một Step kiểm tra file đầu vào có thể tạo ra ba kết quả: dữ liệu hợp lệ, không có dữ liệu hoặc có bản ghi bị bỏ qua. Job có thể tiếp tục nhập dữ liệu khi kết quả hợp lệ, kết thúc bình thường khi không có dữ liệu, hoặc chuyển sang Step kiểm tra thủ công khi có bản ghi bị skip.

Conditional transition giúp tách logic thực thi của Step khỏi logic điều phối Job. Step báo kết quả; Job flow quyết định bước tiếp theo.

## 1. ExitStatus là gì?

`ExitStatus` mô tả kết quả thoát của một lần thực thi Step. Nó gồm exit code và mô tả, trong đó exit code thường được Job flow dùng để chọn transition.

Một số exit code chuẩn thường gặp:

| Exit code | Ý nghĩa thường gặp |
|---|---|
| `COMPLETED` | Step hoàn tất bình thường |
| `FAILED` | Step thất bại |
| `STOPPED` | Step bị dừng |
| `EXECUTING` | Step đang thực thi trong một số ngữ cảnh |
| `UNKNOWN` | Không xác định được kết quả |

Ứng dụng có thể tạo exit code riêng theo nghiệp vụ, ví dụ `NO_DATA`, `COMPLETED_WITH_SKIPS` hoặc `NEEDS_REVIEW`. Những mã này không phải `BatchStatus`; chúng là kết quả dùng để mô tả Step và định tuyến flow.

## 2. Phân biệt BatchStatus và ExitStatus

Hai khái niệm thường bị nhầm lẫn:

- `BatchStatus` phản ánh trạng thái vòng đời do Spring Batch quản lý, chẳng hạn `STARTED`, `COMPLETED`, `FAILED` hoặc `STOPPED`.
- `ExitStatus` mô tả mã kết quả và thông tin bổ sung sau khi Step kết thúc. Job flow thường so khớp exit code của trường này.

Một Step có thể có `BatchStatus.COMPLETED` nhưng `ExitStatus` là `COMPLETED_WITH_SKIPS`. Về mặt thực thi, Step đã kết thúc thành công theo framework; về mặt nghiệp vụ, nó có cảnh báo cần được xử lý ở nhánh khác.

Ngược lại, không nên chỉ đổi `ExitStatus` thành `COMPLETED` để che giấu một lỗi thực thi. Nếu Step thực sự thất bại, `BatchStatus` và exception phải phản ánh đúng tình trạng đó.

## 3. Job flow dùng on() để chọn nhánh

Java flow builder cho phép khai báo transition theo exit code bằng `.on(pattern)`:

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step validateOrdersStep,
        Step importOrdersStep,
        Step reviewSkippedOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateOrdersStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedOrdersStep)
            .from(validateOrdersStep)
                .on("COMPLETED").to(importOrdersStep)
            .from(validateOrdersStep)
                .on("NO_DATA").end()
            .from(validateOrdersStep)
                .on("FAILED").fail()
            .from(validateOrdersStep)
                .on("*").fail()
            .end()
            .build();
}
```

Trong ví dụ:

- `COMPLETED_WITH_SKIPS`: chuyển sang `reviewSkippedOrdersStep`.
- `COMPLETED`: chuyển sang `importOrdersStep`.
- `NO_DATA`: kết thúc Job theo trạng thái hoàn tất.
- `FAILED`: kết thúc Job với trạng thái thất bại.
- `*`: nhánh dự phòng cho exit code chưa được khai báo cụ thể.

`.start(step)` xác định Step đầu tiên. `.from(step)` tiếp tục khai báo transition xuất phát từ cùng Step. `.on(...)` chọn pattern để so khớp exit code, còn `.to(...)` chuyển sang Step tiếp theo.

## 4. Exit code chuẩn và exit code tùy chỉnh

Nếu không tùy chỉnh, Step thường kết thúc với exit code chuẩn như `COMPLETED` hoặc `FAILED`. Khi nghiệp vụ cần phân biệt thêm kết quả, có thể tạo `ExitStatus` tùy chỉnh.

Ví dụ, listener kiểm tra số item bị skip và số item đã đọc:

```java
public class ValidationResultListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Không cần xử lý trước Step.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() != BatchStatus.COMPLETED) {
            return stepExecution.getExitStatus();
        }

        if (stepExecution.getReadCount() == 0) {
            return new ExitStatus("NO_DATA", "Input contained no records");
        }

        if (stepExecution.getSkipCount() > 0) {
            return new ExitStatus(
                    "COMPLETED_WITH_SKIPS",
                    "Some records were skipped"
            );
        }

        return stepExecution.getExitStatus();
    }
}
```

Đăng ký listener vào Step:

```java
@Bean
public Step validateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer,
        ValidationResultListener listener) {

    return new StepBuilder("validateOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(listener)
            .build();
}
```

`afterStep()` chỉ trả exit code tùy chỉnh khi `BatchStatus` là `COMPLETED`. Nếu Step đã `FAILED`, listener giữ nguyên ExitStatus hiện tại để Job flow có thể xử lý nhánh lỗi.

## 5. Quy tắc so khớp transition

Transition được khai báo bằng pattern so khớp với exit code. Các mã cụ thể nên được đặt trước pattern tổng quát hoặc wildcard để ý định điều phối dễ đọc và không bị nhánh dự phòng che lấp.

Ví dụ:

```java
.start(validateStep)
    .on("COMPLETED_WITH_SKIPS").to(reviewStep)
.from(validateStep)
    .on("COMPLETED").to(importStep)
.from(validateStep)
    .on("*").fail()
```

`*` là wildcard khớp các exit code còn lại. Có thể dùng pattern có wildcard để nhóm các mã theo quy ước, nhưng cần đặt pattern đủ cụ thể và kiểm tra thứ tự ưu tiên khi có nhiều pattern cùng có thể khớp.

Một flow nên có nhánh cho mọi kết quả có thể phát sinh. Nếu Step trả về một custom exit code mà không có transition phù hợp, Job có thể kết thúc với lỗi định nghĩa flow thay vì đi theo nhánh mà người viết mong đợi. Wildcard cuối cùng là cách tạo nhánh dự phòng rõ ràng.

## 6. Phân biệt to(), end(), fail() và stop()

Sau `.on(...)`, flow builder có thể chuyển đến một Step khác hoặc kết thúc flow theo một trạng thái cụ thể.

| Phương thức | Ý nghĩa điều phối |
|---|---|
| `.to(nextStep)` | Chuyển sang Step được chỉ định |
| `.end()` | Kết thúc Job flow với kết quả hoàn tất |
| `.fail()` | Kết thúc Job flow với trạng thái thất bại |
| `.stop()` | Dừng Job flow với trạng thái dừng |

Ví dụ, khi không có dữ liệu, Job có thể kết thúc bình thường mà không cần chạy Step nhập dữ liệu:

```java
.from(validateStep)
    .on("NO_DATA").end()
```

Nếu kết quả yêu cầu xử lý lỗi và Job phải được đánh dấu thất bại:

```java
.from(validateStep)
    .on("FAILED").fail()
```

Nếu cần dừng để chờ thao tác bên ngoài hoặc một điều kiện vận hành, có thể dùng `.stop()`; trạng thái dừng có thể được restart theo quy tắc của Job và Step.

Không nhầm `.end()` với `.to(nextStep)`. `.end()` kết thúc Job flow; `.to(nextStep)` tiếp tục chạy một Step khác. Việc chọn terminal state cần phản ánh đúng kết quả nghiệp vụ và yêu cầu vận hành.

## 7. Ví dụ flow đầy đủ với nhiều nhánh nghiệp vụ

Giả sử Job nhập đơn hàng có các Step:

1. `validateInputStep`: kiểm tra dữ liệu đầu vào.
2. `importOrdersStep`: nhập dữ liệu hợp lệ.
3. `reviewSkippedStep`: tạo danh sách bản ghi cần kiểm tra.
4. `sendNoDataNoticeStep`: ghi nhận trường hợp file không có dữ liệu.

Flow có thể được cấu hình như sau:

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importOrdersStep,
        Step reviewSkippedStep,
        Step sendNoDataNoticeStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateInputStep)
                .on("COMPLETED").to(importOrdersStep)
            .from(validateInputStep)
                .on("COMPLETED_WITH_SKIPS").to(reviewSkippedStep)
            .from(validateInputStep)
                .on("NO_DATA").to(sendNoDataNoticeStep)
            .from(validateInputStep)
                .on("FAILED").fail()
            .from(validateInputStep)
                .on("*").fail()
            .from(importOrdersStep)
                .on("*").end()
            .from(reviewSkippedStep)
                .on("*").end()
            .from(sendNoDataNoticeStep)
                .on("*").end()
            .end()
            .build();
}
```

Flow trên minh họa cách định tuyến theo kết quả validation. Nhánh nhập dữ liệu, review và no-data đều kết thúc Job sau khi Step tương ứng hoàn tất. Trong hệ thống thực tế, có thể bổ sung transition riêng cho lỗi của từng Step thay vì dùng `*` để kết thúc chung.

## 8. Transition theo ExitStatus không phải điều kiện trực tiếp trên BatchStatus

Một lỗi thường gặp là nghĩ rằng `.on("COMPLETED")` kiểm tra `BatchStatus.COMPLETED`. Trên thực tế, transition pattern so khớp exit code của `ExitStatus`.

Trong trường hợp thông thường, Step thành công có ExitStatus `COMPLETED`, nên hai khái niệm trông giống nhau. Nhưng khi listener trả `COMPLETED_WITH_SKIPS`, BatchStatus vẫn có thể là `COMPLETED`; transition `.on("COMPLETED")` sẽ không khớp exit code tùy chỉnh đó.

Hãy xác định rõ mã mà Step thực sự trả về:

```java
ExitStatus exitStatus = stepExecution.getExitStatus();
String exitCode = exitStatus.getExitCode();
```

Sau đó dùng đúng chuỗi trong `.on(...)`. Nếu muốn định tuyến theo nhiều trạng thái hoặc điều kiện phức tạp hơn, có thể dùng `JobExecutionDecider`; decider trả về `FlowExecutionStatus`, đây là cơ chế khác với ExitStatus của Step.

## 9. Dùng JobExecutionDecider khi điều kiện không chỉ là exit code

Conditional transition theo ExitStatus phù hợp khi Step đã thực hiện xong và kết quả có thể biểu diễn bằng một exit code. Nếu điều kiện điều phối cần truy vấn dữ liệu, xem JobParameters, đọc JobExecutionContext hoặc tính toán theo nhiều giá trị, `JobExecutionDecider` có thể phù hợp hơn.

Ví dụ decider kiểm tra tham số chế độ:

```java
public class ImportModeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        String mode = jobExecution.getJobParameters().getString("mode");

        if ("FULL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("FULL_IMPORT");
        }

        return new FlowExecutionStatus("DELTA_IMPORT");
    }
}
```

Flow builder có thể định tuyến theo trạng thái do decider trả về:

```java
return new JobBuilder("importOrdersJob", jobRepository)
        .start(importModeDecider)
            .on("FULL_IMPORT").to(fullImportStep)
        .from(importModeDecider)
            .on("DELTA_IMPORT").to(deltaImportStep)
        .end()
        .build();
```

Decider không thay đổi ExitStatus của Step. Nó trả về một `FlowExecutionStatus` để điều khiển flow tại vị trí decider. Nếu kết quả đã được Step biểu diễn rõ bằng ExitStatus, transition trực tiếp thường đơn giản và dễ quan sát hơn.

## 10. ExitStatus được tạo ở đâu?

Một Step có thể nhận ExitStatus từ quá trình thực thi và listener. Một số cách thường dùng:

- `StepExecutionListener.afterStep()` trả về `ExitStatus` tùy chỉnh.
- Logic trong Tasklet hoặc chunk có thể đặt exit status qua `StepContribution` khi phù hợp với API của phiên bản framework.
- Framework thiết lập các exit code chuẩn dựa trên kết quả thực thi.

Ví dụ trong Tasklet, có thể đặt kết quả nghiệp vụ trước khi kết thúc:

```java
public class CheckInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        if (inputHasNoRecords()) {
            contribution.setExitStatus(
                    new ExitStatus("NO_DATA", "No input records found")
            );
        }

        return RepeatStatus.FINISHED;
    }
}
```

Đây là cách để Step công bố kết quả ngay trong logic Tasklet. Nếu dùng listener, cần nhớ `afterStep()` chạy sau phần xử lý Step và có thể tổng hợp trạng thái dựa trên counter cuối cùng.

## 11. Thiết kế exit code có quy ước

Custom exit code là giao diện giữa Step và Job flow. Nếu đặt tên tùy tiện hoặc thay đổi không nhất quán, flow có thể không match hoặc khó bảo trì.

Một số quy tắc hữu ích:

- Dùng tên mô tả kết quả nghiệp vụ, ví dụ `NO_DATA`, `COMPLETED_WITH_SKIPS`, `NEEDS_REVIEW`.
- Giữ nguyên chữ hoa/thường theo quy ước; transition phải dùng đúng code Step trả về.
- Phân biệt kết quả thành công có cảnh báo với thất bại thực sự.
- Tránh dùng cùng một code cho hai ý nghĩa khác nhau ở các Step.
- Có wildcard fallback để xử lý code chưa được dự kiến.
- Ghi log `stepName`, `BatchStatus`, `ExitStatus.exitCode` và mô tả để dễ điều tra.
- Khi đổi code, cập nhật tất cả transition phụ thuộc và kiểm tra các Job flow liên quan.

Nếu nhiều Step dùng chung một bộ mã kết quả, có thể định nghĩa constant để tránh lỗi chính tả:

```java
public final class StepExitCodes {
    public static final String NO_DATA = "NO_DATA";
    public static final String COMPLETED_WITH_SKIPS = "COMPLETED_WITH_SKIPS";
    public static final String NEEDS_REVIEW = "NEEDS_REVIEW";

    private StepExitCodes() {
    }
}
```

Sau đó dùng cùng constant trong listener và flow builder:

```java
.from(validateStep)
    .on(StepExitCodes.NEEDS_REVIEW).to(reviewStep)
```

## 12. Restart và terminal transition

Conditional transition không chỉ chọn Step tiếp theo mà còn ảnh hưởng trạng thái kết thúc của Job. `.end()`, `.fail()` và `.stop()` tạo các terminal state khác nhau.

- Kết thúc bằng `.end()` đánh dấu flow hoàn tất. Một JobInstance đã hoàn tất thường không thể được chạy lại với cùng identifying JobParameters như một lần mới; muốn xử lý công việc mới cần JobInstance mới.
- Kết thúc bằng `.fail()` làm Job thất bại. Nếu Job và Step cho phép restart, lần chạy sau có thể tiếp tục theo metadata đã lưu.
- Kết thúc bằng `.stop()` đánh dấu Job dừng. Job có thể được restart theo cấu hình và trạng thái đã lưu.

Hãy chọn terminal transition theo ý nghĩa nghiệp vụ. Ví dụ `NO_DATA` có thể là kết quả hoàn tất bình thường nếu không có dữ liệu là tình huống hợp lệ. Nếu dữ liệu bắt buộc phải có, cùng kết quả đó có thể cần `.fail()` để yêu cầu vận hành xử lý.

## 13. Những nhầm lẫn thường gặp

**Cho rằng `.on("COMPLETED")` kiểm tra BatchStatus.** Transition so khớp exit code của ExitStatus. Khi code được tùy chỉnh, cần dùng đúng chuỗi mới.

**Không khai báo transition cho custom exit code.** Nếu Step trả `NO_DATA` nhưng flow chỉ có `COMPLETED` và `FAILED`, Job không có nhánh phù hợp. Hãy khai báo code cụ thể và fallback.

**Đặt wildcard quá sớm hoặc không rõ ý định.** Wildcard có thể bắt các kết quả mà người viết muốn xử lý riêng. Hãy ưu tiên các pattern cụ thể và để nhánh tổng quát làm fallback.

**Dùng `.end()` khi muốn chạy Step tiếp theo.** `.end()` kết thúc Job flow; dùng `.to(nextStep)` để chuyển sang Step khác.

**Đổi ExitStatus để che giấu lỗi.** ExitStatus không thay thế BatchStatus. Hãy để lỗi thực thi phản ánh đúng trạng thái và dùng mã tùy chỉnh cho kết quả nghiệp vụ phù hợp.

**Dùng ExitStatus cho điều kiện quá phức tạp.** Nếu cần tính toán hoặc kiểm tra nhiều nguồn dữ liệu tại điểm điều phối, cân nhắc `JobExecutionDecider`.

## 14. Cách thiết kế conditional transition

Trước tiên, xác định các kết quả mà Step có thể trả về. Dùng exit code chuẩn khi kết quả chỉ là thành công/thất bại; tạo custom ExitStatus khi Job cần phân biệt các kết quả nghiệp vụ như không có dữ liệu hoặc cần review. Đăng ký listener hoặc đặt exit status trong logic Step, sau đó khai báo transition cụ thể cho từng code và wildcard fallback cuối cùng.

Kiểm tra riêng ba khía cạnh: `BatchStatus` có phản ánh đúng vòng đời thực thi hay không, `ExitStatus.exitCode` có đúng với kết quả nghiệp vụ hay không, và terminal transition có đưa Job về trạng thái phù hợp hay không. Khi ba phần này nhất quán, conditional transition giúp Job flow điều phối rõ ràng, dễ mở rộng và dễ theo dõi.
