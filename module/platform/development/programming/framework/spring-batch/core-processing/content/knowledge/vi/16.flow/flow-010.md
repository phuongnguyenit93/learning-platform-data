# JobExecutionDecider và trạng thái quyết định

Trong Spring Batch, `JobExecutionDecider` cho phép Job flow chọn nhánh tiếp theo dựa trên một điều kiện tại thời điểm chạy. Decider nhận `JobExecution` và `StepExecution` (nếu có), sau đó trả về `FlowExecutionStatus` để Job flow so khớp và chuyển sang Step phù hợp.

Decider hữu ích khi việc điều phối phụ thuộc vào JobParameters, dữ liệu được tạo bởi Step trước, trạng thái lưu trong ExecutionContext hoặc một điều kiện nghiệp vụ cần kiểm tra tại runtime. Ví dụ, Job có thể chọn quy trình nhập toàn bộ hay nhập gia tăng, chuyển sang nhánh review khi có dữ liệu cần kiểm tra, hoặc kết thúc bình thường khi không có dữ liệu.

Điểm cốt lõi là decider quyết định **flow sẽ đi đâu tiếp theo**. Nó không phải một Step và trạng thái nó trả về là `FlowExecutionStatus`, khác với `BatchStatus` và `ExitStatus` của Step.

## 1. JobExecutionDecider là gì?

`JobExecutionDecider` là một interface của Spring Batch dành cho logic quyết định trong Job flow. Phương thức chính có dạng:

```java
public interface JobExecutionDecider {
    FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) throws Exception;
}
```

Decider nhận hai đối tượng:

- `JobExecution`: đại diện cho lần thực thi Job hiện tại. Có thể đọc JobParameters, Job-level ExecutionContext và các metadata liên quan đến lần chạy.
- `StepExecution`: đại diện cho Step gần nhất trước decider trong flow, nếu decider được gọi sau một Step. Có thể là `null` khi decider đứng đầu flow và chưa có Step nào chạy.

Kết quả trả về là `FlowExecutionStatus`. Job flow dùng tên trạng thái này để chọn transition được khai báo bằng `.on(...)`.

Decider không tạo `StepExecution` riêng, không đọc/ghi item như chunk Step và không có `BatchStatus` riêng. Nó là một trạng thái điều phối trong flow.

## 2. FlowExecutionStatus là trạng thái quyết định

`FlowExecutionStatus` biểu diễn trạng thái của flow tại vị trí decider. Spring Batch có các trạng thái chuẩn như `COMPLETED`, `FAILED`, `STOPPED`, `UNKNOWN`; ứng dụng cũng có thể trả về tên tùy chỉnh như `FULL_IMPORT`, `DELTA_IMPORT`, `NO_DATA` hoặc `NEEDS_REVIEW`.

Ví dụ:

```java
return new FlowExecutionStatus("FULL_IMPORT");
```

Flow builder sẽ tìm transition có pattern khớp với trạng thái `FULL_IMPORT`:

```java
.from(importModeDecider)
    .on("FULL_IMPORT").to(fullImportStep)
```

Tên trạng thái do decider trả về phải khớp với pattern đã khai báo. Nếu decider trả về `FULL_IMPORT` nhưng Job chỉ khai báo `DELTA_IMPORT` và `NO_DATA`, flow không có nhánh phù hợp. Nên định nghĩa rõ các trạng thái có thể phát sinh và có transition dự phòng.

## 3. Phân biệt FlowExecutionStatus, ExitStatus và BatchStatus

Ba loại trạng thái này có mục đích khác nhau:

| Loại trạng thái | Thuộc về | Mục đích |
|---|---|---|
| `BatchStatus` | JobExecution hoặc StepExecution | Mô tả vòng đời thực thi, ví dụ `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` |
| `ExitStatus` | StepExecution | Mô tả kết quả thoát của Step; exit code thường được dùng cho transition xuất phát từ Step |
| `FlowExecutionStatus` | Trạng thái của flow/decider | Mô tả kết quả quyết định tại vị trí decider để chọn nhánh tiếp theo |

Ví dụ, một Step có thể kết thúc với `BatchStatus.COMPLETED` và `ExitStatus.COMPLETED_WITH_SKIPS`. Job flow có thể dùng ExitStatus đó để quyết định có chạy Step review hay không. Sau Step đó, một decider khác có thể trả `FlowExecutionStatus("SEND_NOTIFICATION")` để chọn nhánh gửi thông báo.

Không dùng `ExitStatus` thay cho giá trị trả về của `JobExecutionDecider`. Phương thức `decide()` cần trả về `FlowExecutionStatus`.

## 4. Cài đặt decider dựa trên JobParameters

Trường hợp đơn giản là chọn flow dựa trên tham số đầu vào. Ví dụ Job nhập đơn hàng hỗ trợ hai chế độ `FULL` và `DELTA`:

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

        if ("DELTA".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("DELTA_IMPORT");
        }

        return new FlowExecutionStatus("INVALID_MODE");
    }
}
```

Decider chỉ đọc tham số và trả về trạng thái. Nó không cần giữ `mode` trong mutable field, vì JobParameters đã gắn với JobExecution hiện tại.

Đăng ký decider thành bean:

```java
@Bean
public JobExecutionDecider importModeDecider() {
    return new ImportModeDecider();
}
```

Khi tạo JobParameters, ứng dụng nên validate và chuẩn hóa `mode` trước khi khởi chạy. Trả `INVALID_MODE` giúp flow có thể xử lý đầu vào không hợp lệ theo một nhánh rõ ràng, nhưng validation quan trọng vẫn nên thực hiện sớm ở tầng khởi chạy hoặc `JobParametersValidator`.

## 5. Đặt decider giữa các Step

Một cách dùng phổ biến là chạy một Step chuẩn bị dữ liệu trước, rồi dùng decider để chọn Step tiếp theo:

```text
prepareInputStep
       |
       v
ImportModeDecider
       |
       +-- FULL_IMPORT  --> fullImportStep
       |
       +-- DELTA_IMPORT --> deltaImportStep
       |
       +-- INVALID_MODE --> invalidModeStep / fail
```

Khai báo Job flow bằng Java:

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step prepareInputStep,
        Step fullImportStep,
        Step deltaImportStep,
        Step invalidModeStep,
        JobExecutionDecider importModeDecider) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(prepareInputStep)
            .next(importModeDecider)
                .on("FULL_IMPORT").to(fullImportStep)
            .from(importModeDecider)
                .on("DELTA_IMPORT").to(deltaImportStep)
            .from(importModeDecider)
                .on("INVALID_MODE").to(invalidModeStep)
            .from(importModeDecider)
                .on("*").fail()
            .end()
            .build();
}
```

`.next(importModeDecider)` đặt decider sau `prepareInputStep`. `.from(importModeDecider)` khai báo các nhánh xuất phát từ decider. `.on(...)` so khớp `FlowExecutionStatus` mà decider trả về, còn `.to(...)` chuyển đến Step được chọn.

Trong flow thực tế, cần khai báo transition tiếp theo từ các Step đích nếu chúng không phải terminal state. Ví dụ, sau `fullImportStep` và `deltaImportStep`, Job có thể đi đến một Step tổng hợp báo cáo hoặc kết thúc bằng các transition phù hợp.

## 6. Đặt decider ở đầu Job flow

Decider cũng có thể là trạng thái đầu tiên của Job, trước khi bất kỳ Step nào chạy:

```java
@Bean
public Job initialDecisionJob(
        JobRepository jobRepository,
        JobExecutionDecider initialDecider,
        Step fullStep,
        Step deltaStep) {

    return new JobBuilder("initialDecisionJob", jobRepository)
            .start(initialDecider)
                .on("FULL").to(fullStep)
            .from(initialDecider)
                .on("DELTA").to(deltaStep)
            .from(initialDecider)
                .on("*").fail()
            .end()
            .build();
}
```

Trong trường hợp này, tham số `stepExecution` truyền vào `decide()` có thể là `null`, vì chưa có Step nào chạy. Nếu decider có thể được dùng ở đầu flow, hãy kiểm tra null trước khi truy cập:

```java
@Override
public FlowExecutionStatus decide(
        JobExecution jobExecution,
        StepExecution stepExecution) {

    if (stepExecution == null) {
        // Quyết định chỉ dựa trên JobParameters hoặc JobExecutionContext.
        return new FlowExecutionStatus("INITIAL_RUN");
    }

    return new FlowExecutionStatus("AFTER_STEP");
}
```

Không giả định `stepExecution` luôn có giá trị. Đây là điểm quan trọng khi tái sử dụng cùng một decider ở nhiều vị trí flow.

## 7. Đọc kết quả của Step trước đó

Khi decider nằm sau một Step, nó có thể sử dụng `StepExecution` được truyền vào để đọc kết quả và metadata của Step vừa chạy.

Ví dụ, sau Step kiểm tra dữ liệu, decider chọn nhánh dựa trên số item bị skip:

```java
public class ReviewRequiredDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution == null) {
            return new FlowExecutionStatus("NO_PREVIOUS_STEP");
        }

        if (stepExecution.getStatus() != BatchStatus.COMPLETED) {
            return new FlowExecutionStatus("STEP_NOT_COMPLETED");
        }

        if (stepExecution.getSkipCount() > 0) {
            return new FlowExecutionStatus("NEEDS_REVIEW");
        }

        return new FlowExecutionStatus("CONTINUE");
    }
}
```

Flow có thể chuyển đến Step review khi cần:

```java
.start(validateOrdersStep)
.next(reviewRequiredDecider)
    .on("NEEDS_REVIEW").to(reviewSkippedOrdersStep)
.from(reviewRequiredDecider)
    .on("CONTINUE").to(importOrdersStep)
.from(reviewRequiredDecider)
    .on("*").fail()
```

Ở đây, decider chỉ đọc counter của Step trước. Nó không thay đổi `BatchStatus` hoặc `ExitStatus` của Step đó.

Nếu muốn định tuyến chỉ dựa trên kết quả Step đã được mô tả trong `ExitStatus`, có thể dùng conditional transition trực tiếp theo ExitStatus. Decider phù hợp khi cần kết hợp nhiều dữ liệu hoặc tính toán một quyết định riêng tại flow.

## 8. Đọc JobExecutionContext và StepExecutionContext

Decider có thể đọc dữ liệu trong Job-level ExecutionContext:

```java
String sourceSystem = jobExecution.getExecutionContext()
        .getString("sourceSystem", "UNKNOWN");
```

Nếu được gọi sau Step, decider cũng có thể đọc Step-level ExecutionContext:

```java
if (stepExecution != null) {
    String validationResult = stepExecution.getExecutionContext()
            .getString("validationResult", "NOT_AVAILABLE");
}
```

Điều này hữu ích khi Step trước tính toán một giá trị phức tạp và lưu kết quả để decider sử dụng. Ví dụ, Step phân tích file có thể lưu `inputCategory=LEGACY`; decider đọc key đó và chọn converter phù hợp.

Chỉ nên lưu các giá trị nhỏ, cần thiết cho điều phối. Không đưa toàn bộ dữ liệu nghiệp vụ lớn vào ExecutionContext. Cũng cần hiểu thời điểm context được JobRepository lưu; thay đổi object trong bộ nhớ không có nghĩa là metadata đã được ghi bền vững ngay lập tức.

## 9. Trạng thái quyết định nên có quy ước rõ ràng

Các trạng thái do decider trả về là hợp đồng giữa decider và Job flow. Nếu code trả một chuỗi nhưng flow dùng chuỗi khác, nhánh sẽ không được chọn như mong đợi.

Có thể định nghĩa constant:

```java
public final class ImportFlowStatuses {
    public static final String FULL_IMPORT = "FULL_IMPORT";
    public static final String DELTA_IMPORT = "DELTA_IMPORT";
    public static final String NO_DATA = "NO_DATA";
    public static final String NEEDS_REVIEW = "NEEDS_REVIEW";
    public static final String INVALID_INPUT = "INVALID_INPUT";

    private ImportFlowStatuses() {
    }
}
```

Sau đó dùng cùng constant trong decider và flow builder:

```java
return new FlowExecutionStatus(ImportFlowStatuses.NEEDS_REVIEW);
```

```java
.from(reviewDecider)
    .on(ImportFlowStatuses.NEEDS_REVIEW).to(reviewStep)
```

Tên trạng thái nên diễn tả quyết định hoặc nhánh nghiệp vụ, không nên dùng các chuỗi mơ hồ như `1`, `2`, `OK` hoặc `OTHER`. Khi thay đổi tên, phải cập nhật tất cả transition phụ thuộc.

## 10. Wildcard và nhánh dự phòng

Flow nên xử lý mọi trạng thái decider có thể trả về. Một nhánh wildcard có thể dùng làm fallback:

```java
.from(importModeDecider)
    .on("FULL_IMPORT").to(fullImportStep)
.from(importModeDecider)
    .on("DELTA_IMPORT").to(deltaImportStep)
.from(importModeDecider)
    .on("NO_DATA").end()
.from(importModeDecider)
    .on("*").fail()
```

Các pattern cụ thể thể hiện rõ kết quả mong đợi; wildcard cuối cùng xử lý trạng thái chưa được dự kiến. Nếu không có transition phù hợp, Job flow có thể kết thúc với lỗi không tìm được transition thay vì tiếp tục theo một nhánh mặc định an toàn.

Không nên dùng wildcard để âm thầm đưa mọi trạng thái lạ sang nhánh thành công. Với trạng thái không nhận diện, `.fail()` thường an toàn hơn vì buộc hệ thống ghi nhận lỗi điều phối và yêu cầu điều tra.

## 11. Phân biệt JobExecutionDecider với StepExecutionListener

Hai cơ chế đều có thể ảnh hưởng đến Job flow, nhưng vai trò khác nhau:

| Tiêu chí | `StepExecutionListener` | `JobExecutionDecider` |
|---|---|---|
| Thuộc về | Một Step | Một vị trí trong Job flow |
| Callback | `beforeStep()` và `afterStep()` | `decide()` |
| Đầu vào | `StepExecution` | `JobExecution` và có thể có `StepExecution` |
| Kết quả | Có thể trả `ExitStatus` từ `afterStep()` | Trả `FlowExecutionStatus` |
| Vai trò | Theo dõi lifecycle và phân loại kết quả của Step | Chọn nhánh flow dựa trên điều kiện runtime |
| Có StepExecution riêng không? | Được gọi trong vòng đời StepExecution hiện tại | Không tạo StepExecution riêng |

Nếu điều kiện chỉ dựa trên kết quả của một Step, listener có thể trả custom ExitStatus rồi dùng transition theo ExitStatus. Nếu cần quyết định tại một điểm flow độc lập, kết hợp JobParameters, JobExecutionContext hoặc metadata của Step trước, decider thường diễn đạt rõ hơn.

## 12. Phân biệt JobExecutionDecider với conditional transition trực tiếp

Conditional transition trực tiếp dùng `.on(...)` để kiểm tra ExitStatus của Step vừa hoàn tất. `JobExecutionDecider` là một flow state riêng, được gọi để tính toán và trả về FlowExecutionStatus.

Ví dụ dùng transition trực tiếp:

```java
.start(validateStep)
    .on("COMPLETED_WITH_SKIPS").to(reviewStep)
.from(validateStep)
    .on("COMPLETED").to(importStep)
```

Ví dụ dùng decider:

```java
.start(validateStep)
.next(reviewRequiredDecider)
    .on("NEEDS_REVIEW").to(reviewStep)
.from(reviewRequiredDecider)
    .on("CONTINUE").to(importStep)
```

Transition trực tiếp phù hợp khi Step đã biết kết quả và công bố qua ExitStatus. Decider phù hợp khi muốn đặt logic quyết định riêng ở flow hoặc cần xem nhiều thông tin để chọn nhánh.

Không nên thêm decider nếu một transition đơn giản đã diễn đạt đủ yêu cầu. Giữ flow dễ đọc giúp người vận hành hiểu vì sao Job đi vào nhánh cụ thể.

## 13. Restart và tính xác định của quyết định

Job có thể được restart sau khi một nhánh đã chạy một phần. Khi flow tiếp tục, decider có thể được gọi lại tùy vị trí thực thi và metadata của Job. Vì vậy, logic quyết định cần ổn định đối với cùng một công việc nghiệp vụ.

Một decider an toàn thường:

- Dựa trên JobParameters identifying hoặc dữ liệu đã được lưu bền vững.
- Đọc kết quả từ Job/Step ExecutionContext hoặc repository theo cách nhất quán.
- Trả cùng trạng thái khi đầu vào nghiệp vụ không đổi.
- Không thực hiện side effect như tạo giao dịch, gửi email hoặc publish message.
- Không dựa vào mutable field trong singleton bean để nhớ lần gọi trước.

Ví dụ không nên làm:

```java
public class UnsafeDecider implements JobExecutionDecider {

    private boolean firstCall = true;

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (firstCall) {
            firstCall = false;
            return new FlowExecutionStatus("FIRST_BRANCH");
        }

        return new FlowExecutionStatus("SECOND_BRANCH");
    }
}
```

Kết quả phụ thuộc vào lịch sử gọi trong bộ nhớ. Khi ứng dụng restart, instance decider có thể được tạo lại và `firstCall` quay về `true`; khi có nhiều Job chạy đồng thời, các execution có thể ảnh hưởng lẫn nhau.

Nếu một quyết định phải được giữ nguyên qua restart, hãy lưu dữ liệu quyết định hoặc nguồn dữ liệu đầu vào một cách bền vững và đọc lại. Đừng dựa vào field của decider để làm checkpoint.

## 14. Không đặt side effect khó lặp trong decide()

`decide()` là nơi tính toán trạng thái điều phối. Nó có thể được gọi lại trong các tình huống restart hoặc khi flow được thực thi lại. Nếu mỗi lần gọi decider đều tạo một bản ghi mới, gửi email hoặc gọi API tạo giao dịch, hệ thống có thể lặp side effect.

Ví dụ không phù hợp:

```java
@Override
public FlowExecutionStatus decide(
        JobExecution jobExecution,
        StepExecution stepExecution) {

    notificationService.send("Import is starting");
    return new FlowExecutionStatus("CONTINUE");
}
```

Nên để decider chỉ xác định nhánh:

```java
@Override
public FlowExecutionStatus decide(
        JobExecution jobExecution,
        StepExecution stepExecution) {

    boolean needsNotification = readNotificationRequirement(jobExecution);
    return new FlowExecutionStatus(
            needsNotification ? "SEND_NOTIFICATION" : "CONTINUE"
    );
}
```

Sau đó, nếu cần gửi thông báo, chuyển đến một Step riêng có transaction, retry và idempotency được thiết kế rõ ràng. Điều này giúp phân biệt quyết định điều phối với hành động nghiệp vụ.

## 15. Kiểm thử decider

Decider thường là thành phần nhỏ, có thể unit test trực tiếp bằng `JobExecution` và `StepExecution` mẫu.

Các trường hợp nên được kiểm tra:

- Mỗi giá trị JobParameters hợp lệ trả đúng FlowExecutionStatus.
- Giá trị thiếu hoặc không hợp lệ trả trạng thái lỗi/nhánh dự phòng phù hợp.
- `stepExecution == null` được xử lý nếu decider có thể đứng đầu flow.
- Step trước `FAILED`, `COMPLETED` hoặc có skip dẫn đến quyết định đúng.
- Cùng một bộ tham số và metadata cho kết quả ổn định.
- Decider không tạo side effect khi được gọi nhiều lần.

Ví dụ test đơn giản:

```java
@Test
void selectsFullImportForFullMode() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("mode", "FULL")
            .toJobParameters();

    JobExecution jobExecution = new JobExecution(1L, parameters);
    ImportModeDecider decider = new ImportModeDecider();

    FlowExecutionStatus result = decider.decide(jobExecution, null);

    assertEquals("FULL_IMPORT", result.getName());
}
```

Ngoài unit test, nên có integration test cho Job flow để xác nhận mỗi FlowExecutionStatus thực sự chuyển đến đúng Step hoặc terminal state. Test riêng decider chưa chứng minh flow builder đã khai báo đầy đủ transition.

## 16. Những nhầm lẫn thường gặp

**Cho rằng decider là một Step.** Decider là flow state; nó không có StepExecution, reader, processor hoặc writer riêng.

**Trả về ExitStatus từ `decide()`.** Phương thức cần trả `FlowExecutionStatus`. ExitStatus thuộc StepExecution.

**Cho rằng StepExecution luôn khác null.** Khi decider đứng đầu Job flow, chưa có Step nào chạy nên đối số này có thể null.

**Dùng BatchStatus làm tên trạng thái quyết định.** Decider trả FlowExecutionStatus. Có thể dùng tên chuẩn như `COMPLETED`, nhưng đó là tên trạng thái flow, không phải việc decider thay đổi BatchStatus của Job hoặc Step.

**Không khai báo nhánh cho trạng thái tùy chỉnh.** Nếu flow không có transition khớp, Job không biết phải đi đâu. Hãy liệt kê các trạng thái có thể trả về và thêm fallback.

**Giữ quyết định trong field mutable.** Field có thể mất khi restart hoặc bị chia sẻ giữa nhiều JobExecution. Dựa trên tham số và dữ liệu bền vững.

**Thực hiện side effect trong `decide()`.** Decider có thể được gọi lại. Hãy chuyển side effect sang Step riêng và bảo vệ bằng idempotency.

## 17. Cách thiết kế JobExecutionDecider

Hãy bắt đầu bằng việc xác định các nhánh nghiệp vụ và đặt tên `FlowExecutionStatus` cho từng nhánh. Viết decider nhận `JobExecution` và `StepExecution`, kiểm tra null nếu có thể đứng đầu flow, đọc dữ liệu đầu vào hoặc kết quả Step trước, rồi trả về đúng một trạng thái. Khai báo transition cụ thể cho từng trạng thái và một nhánh fallback an toàn.

Giữ `decide()` tập trung vào việc tính toán quyết định, không thực hiện side effect. Nếu quyết định phải ổn định qua restart, dựa vào JobParameters hoặc metadata được lưu bền vững thay vì field trong bộ nhớ. Khi phân biệt rõ `FlowExecutionStatus`, `ExitStatus` và `BatchStatus`, JobExecutionDecider giúp Job flow xử lý các nhánh nghiệp vụ linh hoạt mà vẫn dễ kiểm soát.
