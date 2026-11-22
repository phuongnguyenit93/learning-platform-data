# Step flow và điều kiện chuyển tiếp trong Spring Batch

Một job Spring Batch thường gồm nhiều step. Các step có thể chạy lần lượt theo một thứ tự cố định, nhưng trong thực tế luồng xử lý còn phụ thuộc vào kết quả của từng step, dữ liệu đầu vào hoặc một điều kiện nghiệp vụ. Spring Batch biểu diễn cách các step liên kết với nhau bằng **flow** và dùng **transition** để quyết định bước tiếp theo.

Hiểu step flow giúp thiết kế job có nhánh xử lý thành công, thất bại, dữ liệu rỗng hoặc các tình huống đặc biệt. Thay vì viết toàn bộ logic điều phối trong một step lớn, ứng dụng có thể chia quy trình thành các step nhỏ và khai báo rõ đường đi giữa chúng.

## 1. Step flow là gì?

`Step` là một đơn vị xử lý trong job, chẳng hạn đọc và ghi dữ liệu theo chunk, chạy một tasklet hoặc thực hiện một công việc nghiệp vụ riêng. **Flow** mô tả thứ tự và các nhánh mà job có thể đi qua khi thực thi những step đó.

Có thể hình dung flow như một đồ thị có hướng:

- Mỗi step là một trạng thái xử lý.
- Mỗi transition là một cạnh nối từ step hiện tại đến step tiếp theo hoặc đến trạng thái kết thúc.
- Điều kiện của transition quyết định cạnh nào được chọn dựa trên kết quả của step hoặc quyết định từ một thành phần điều phối.

Một job đơn giản có thể chạy theo trình tự:

```text
Start
  |
  v
ValidateStep
  |
  v
ImportStep
  |
  v
ReportStep
  |
  v
End
```

Nếu mọi step luôn chạy theo một thứ tự cố định, có thể khai báo bằng `start()` và `next()`:

```java
@Bean
Job importJob(JobRepository jobRepository,
              Step validateStep,
              Step importStep,
              Step reportStep) {
    return new JobBuilder("importJob", jobRepository)
        .start(validateStep)
        .next(importStep)
        .next(reportStep)
        .build();
}
```

`start()` chọn step đầu tiên của job. Mỗi lời gọi `next()` thêm step kế tiếp vào chuỗi. Cách viết này phù hợp với luồng tuyến tính, dễ đọc và không cần khai báo từng nhánh. Khi cần rẽ nhánh dựa trên kết quả, nên khai báo transition tường minh.

## 2. ExitStatus và điều kiện chuyển tiếp

Spring Batch dùng `ExitStatus` của step để đối chiếu điều kiện chuyển tiếp. `ExitStatus` chứa exit code và mô tả kết quả kết thúc. Những exit code phổ biến là `COMPLETED` và `FAILED`, nhưng ứng dụng có thể tạo exit code riêng để biểu diễn kết quả nghiệp vụ.

Điều kiện trong `.on("...")` được so khớp với **exit code của `ExitStatus`**, không phải trực tiếp với `BatchStatus`. Hai khái niệm này liên quan nhưng khác nhau:

| Khái niệm | Vai trò |
| --- | --- |
| `BatchStatus` | Trạng thái vòng đời do framework quản lý, ví dụ `COMPLETED`, `FAILED`, `STOPPED`. |
| `ExitStatus` | Mã và mô tả kết quả dùng để thể hiện kết quả kết thúc của step hoặc job; có thể có mã tùy chỉnh. |
| Transition pattern | Mẫu được dùng để so khớp với exit code nhằm chọn đường đi tiếp theo. |

Ví dụ, một step có `BatchStatus.COMPLETED` nhưng `ExitStatus` là `COMPLETED WITH SKIPS`. Transition `.on("COMPLETED*")` có thể khớp với exit code này, trong khi `.on("FAILED")` không khớp.

Thông thường, nếu step kết thúc thành công, exit code mặc định là `COMPLETED`; nếu step thất bại do exception không được xử lý, exit code thường là `FAILED`. Tuy nhiên, listener hoặc logic xử lý có thể thay đổi `ExitStatus`, vì vậy cần hiểu giá trị thực tế mà step trả về khi thiết kế transition.

## 3. Khai báo transition bằng on() và to()

Trong flow builder, `.on(pattern)` chỉ định mẫu exit code cần khớp; `.to(target)` chỉ định step hoặc trạng thái tiếp theo. Có thể dùng `.from(step)` để khai báo thêm transition xuất phát từ một step đã xuất hiện trong flow.

Ví dụ, sau bước kiểm tra dữ liệu:

- Nếu kiểm tra thành công, tiếp tục nhập dữ liệu.
- Nếu kiểm tra thất bại, chuyển sang step ghi nhận lỗi.

```java
@Bean
Job importJob(JobRepository jobRepository,
              Step validateStep,
              Step importStep,
              Step validationErrorStep) {
    return new JobBuilder("importJob", jobRepository)
        .start(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("FAILED").to(validationErrorStep)
        .from(importStep)
            .on("*").end()
        .from(validationErrorStep)
            .on("*").fail()
        .end()
        .build();
}
```

Luồng có thể hình dung như sau:

```text
                 +--------------------+
                 |                    |
                 v                    v
          COMPLETED                 FAILED
                 |                    |
                 v                    v
           ImportStep        ValidationErrorStep
                 |                    |
                 v                    v
                End                  Fail
```

Ở đây:

- `.start(validateStep)` xác định step đầu tiên.
- `.on("COMPLETED").to(importStep)` chuyển sang `importStep` khi exit code của `validateStep` khớp `COMPLETED`.
- `.from(validateStep)` khai báo một nhánh khác cũng xuất phát từ `validateStep`.
- `.on("FAILED").to(validationErrorStep)` chuyển sang step xử lý lỗi nếu bước kiểm tra thất bại.
- `.end()` và `.fail()` xác định trạng thái kết thúc của job, được giải thích ở phần sau.

Trong cấu hình flow, cần bảo đảm mọi kết quả có thể phát sinh đều có đường đi phù hợp. Nếu không có transition nào khớp exit code của trạng thái hiện tại, flow không thể xác định bước tiếp theo và job có thể kết thúc bằng lỗi điều phối.

## 4. Pattern khớp exit code

Transition có thể dùng mẫu cụ thể hoặc wildcard. Spring Batch hỗ trợ các pattern phổ biến:

| Pattern | Ý nghĩa |
| --- | --- |
| `COMPLETED` | Khớp chính xác exit code `COMPLETED`. |
| `FAILED` | Khớp chính xác exit code `FAILED`. |
| `COMPLETED*` | Khớp exit code bắt đầu bằng `COMPLETED`, chẳng hạn `COMPLETED WITH SKIPS`. |
| `*` | Khớp mọi exit code. |

Ví dụ, nếu step có thể kết thúc với `COMPLETED`, `COMPLETED WITH SKIPS` hoặc `FAILED`, có thể khai báo:

```java
.start(importStep)
    .on("COMPLETED WITH SKIPS").to(reviewStep)
.from(importStep)
    .on("COMPLETED").to(reportStep)
.from(importStep)
    .on("FAILED").to(errorStep)
```

Khi sử dụng pattern rộng như `*`, hãy đặt nó sau những điều kiện cụ thể hơn để nhánh tổng quát không che mất nhánh cần xử lý riêng. Ví dụ, nếu khai báo `*` cho `importStep` trước các pattern `FAILED` và `COMPLETED`, nhánh tổng quát có thể nhận cả những kết quả vốn cần đi theo đường riêng. Hãy đọc và sắp xếp transition sao cho các trường hợp đặc biệt được xử lý rõ ràng trước fallback.

Một transition fallback thường hữu ích khi muốn mọi kết quả chưa được phân loại đi đến một step xử lý chung:

```java
.from(importStep)
    .on("FAILED").to(errorStep)
.from(importStep)
    .on("*").to(reviewStep)
```

Fallback không nên được dùng để che giấu lỗi thiết kế. Nếu có exit code mới xuất hiện, cần xác định xem đó là kết quả hợp lệ và nên đi đến đâu.

## 5. Kết thúc flow: end(), fail() và stop()

Transition có thể dẫn đến một step khác hoặc dẫn đến trạng thái kết thúc job. Các thao tác kết thúc phổ biến có ý nghĩa khác nhau:

| Thao tác | Kết quả của job | Ý nghĩa vận hành |
| --- | --- | --- |
| `.end()` | `BatchStatus.COMPLETED` | Đánh dấu job đã hoàn tất. Instance được xem là hoàn thành và không thể restart như một job chưa hoàn tất. |
| `.fail()` | `BatchStatus.FAILED` | Đánh dấu job thất bại. Nếu job được cấu hình restartable và đáp ứng điều kiện restart, có thể chạy lại cùng instance. |
| `.stop()` | `BatchStatus.STOPPED` | Dừng job theo trạng thái có kiểm soát; việc tiếp tục được thực hiện theo quy tắc restart của flow. |
| `.stopAndRestart(step)` | `BatchStatus.STOPPED` | Dừng job và chỉ định step làm điểm bắt đầu khi restart. |

Ví dụ, một step phát hiện không có dữ liệu mới. Đây có thể là kết quả hợp lệ của nghiệp vụ, vì vậy job vẫn nên được đánh dấu hoàn tất:

```java
.start(checkDataStep)
    .on("NO_DATA").end()
.from(checkDataStep)
    .on("DATA_FOUND").to(processStep)
```

Ngược lại, nếu bước xử lý dữ liệu thất bại và cần được chạy lại sau khi khắc phục nguyên nhân, có thể chuyển đến `.fail()`:

```java
.start(processStep)
    .on("FAILED").fail()
.from(processStep)
    .on("COMPLETED").end()
```

`end()` là quyết định về trạng thái hoàn tất của job, không đơn thuần có nghĩa “không còn step tiếp theo”. Ví dụ, một step có thể trả về exit code nghiệp vụ `NO_DATA`; nếu transition của job dẫn đến `.end()`, job vẫn kết thúc với trạng thái hoàn thành. Vì job instance đã hoàn thành, muốn xử lý một đơn vị nghiệp vụ mới cần có identifying parameters phù hợp để tạo `JobInstance` mới.

Khi cần dừng để tiếp tục từ một vị trí đã xác định, có thể dùng `.stopAndRestart(restartStep)`. Hãy chọn điểm restart dựa trên dữ liệu đã commit và cách các step lưu checkpoint. Việc restart còn phụ thuộc vào metadata, trạng thái execution và khả năng khôi phục của các thành phần đọc/ghi dữ liệu.

## 6. Tạo exit code tùy chỉnh cho step

Các nhánh flow không chỉ giới hạn ở `COMPLETED` và `FAILED`. Ứng dụng có thể đặt exit code riêng để thể hiện kết quả như `COMPLETED WITH SKIPS`, `NO_DATA`, `VALIDATION_ERROR` hoặc `REQUIRES_REVIEW`.

Một cách thường dùng là triển khai `StepExecutionListener` và trả về `ExitStatus` tùy chỉnh trong `afterStep()`:

```java
public class SkipStatusListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getSkipCount() > 0) {
            return new ExitStatus("COMPLETED WITH SKIPS");
        }
        return null;
    }
}
```

Sau đó, flow có thể chuyển các bản ghi có skip sang bước kiểm tra:

```java
.start(importStep)
    .on("COMPLETED WITH SKIPS").to(reviewStep)
.from(importStep)
    .on("COMPLETED").to(reportStep)
```

Trong ví dụ listener, trả về `null` khi không cần thay đổi exit status hiện có. Khi có skip, listener trả về mã tùy chỉnh để flow nhận biết và chọn nhánh phù hợp.

Hãy chọn exit code có ý nghĩa ổn định, thống nhất quy ước giữa các step và tránh dùng những chuỗi khó phân biệt. Exit code là một phần của hợp đồng điều phối job; khi thay đổi tên hoặc ý nghĩa của chúng, cần xem lại các transition đang phụ thuộc vào mã đó.

## 7. Dùng JobExecutionDecider cho điều kiện nghiệp vụ

Transition dựa trên `ExitStatus` phù hợp khi quyết định phụ thuộc vào kết quả của step vừa chạy. Tuy nhiên, có những quyết định cần xem xét thông tin khác, ví dụ tham số job, dữ liệu đã lưu trong `ExecutionContext`, số lượng bản ghi hoặc một điều kiện nghiệp vụ được tính riêng. Khi đó, có thể dùng `JobExecutionDecider`.

`JobExecutionDecider` nhận `JobExecution` và `StepExecution` (nếu có), sau đó trả về một `FlowExecutionStatus`. Flow dùng giá trị này để chọn transition.

Ví dụ, job nhận tham số `mode` để quyết định chạy xử lý thường hay chạy lại:

```java
@Bean
JobExecutionDecider modeDecider() {
    return (jobExecution, stepExecution) -> {
        String mode = jobExecution.getJobParameters().getString("mode");
        if ("REPROCESS".equals(mode)) {
            return new FlowExecutionStatus("REPROCESS");
        }
        return new FlowExecutionStatus("NORMAL");
    };
}
```

Có thể sử dụng decider trong job flow:

```java
@Bean
Job conditionalJob(JobRepository jobRepository,
                   Step prepareStep,
                   Step reprocessStep,
                   Step normalStep,
                   JobExecutionDecider modeDecider) {
    return new JobBuilder("conditionalJob", jobRepository)
        .start(prepareStep)
        .next(modeDecider)
            .on("REPROCESS").to(reprocessStep)
        .from(modeDecider)
            .on("NORMAL").to(normalStep)
        .from(reprocessStep)
            .on("*").end()
        .from(normalStep)
            .on("*").end()
        .end()
        .build();
}
```

Trong ví dụ này, `modeDecider` tạo ra một kết quả điều phối độc lập. Khi trả về `REPROCESS`, flow chuyển đến `reprocessStep`; khi trả về `NORMAL`, flow chuyển đến `normalStep`.

`FlowExecutionStatus` của decider và `ExitStatus` của step đều cung cấp mã để flow đối chiếu, nhưng chúng đến từ hai nguồn khác nhau. Decider không phải là một step xử lý dữ liệu; nó là thành phần quyết định đường đi. Nên dùng decider khi điều kiện thực sự cần logic điều phối riêng, thay vì nhồi nhiều nhánh nghiệp vụ vào một step.

## 8. Tổ chức flow thành thành phần có thể tái sử dụng

Khi job có nhiều step hoặc nhiều job dùng chung một chuỗi xử lý, có thể tách flow thành một bean riêng. Một `Flow` gom các step và transition thành một đơn vị có tên, sau đó được sử dụng như một phần của job.

Ví dụ tạo flow xử lý đơn hàng:

```java
@Bean
Flow orderProcessingFlow(Step validateStep,
                        Step importStep,
                        Step reportStep) {
    return new FlowBuilder<SimpleFlow>("orderProcessingFlow")
        .start(validateStep)
        .next(importStep)
        .next(reportStep)
        .build();
}
```

Job có thể bắt đầu từ flow này:

```java
@Bean
Job orderJob(JobRepository jobRepository,
             Flow orderProcessingFlow) {
    return new JobBuilder("orderJob", jobRepository)
        .start(orderProcessingFlow)
        .end()
        .build();
}
```

Tách flow giúp cấu hình job dễ đọc, cho phép tái sử dụng một chuỗi xử lý và giảm sự lặp lại khi nhiều job có chung một quy trình con. Với flow có nhánh, các transition được khai báo trong bean flow; job chỉ cần kết hợp flow với các thành phần khác.

## 9. Restart và ảnh hưởng của transition

Flow quyết định step tiếp theo trong một lần chạy, nhưng cũng ảnh hưởng đến cách job có thể được restart. Spring Batch lưu `JobExecution`, `StepExecution`, trạng thái và `ExecutionContext` trong `JobRepository`. Khi một job thất bại hoặc dừng, lần chạy tiếp theo với cùng `JobInstance` sẽ dựa vào metadata và cấu hình flow để xác định phần việc cần tiếp tục.

Một số điểm cần lưu ý:

- Nếu transition kết thúc bằng `.end()`, job được đánh dấu hoàn tất. Không thể restart cùng instance như một job thất bại.
- Nếu transition kết thúc bằng `.fail()`, job có trạng thái thất bại và có thể restart nếu job cho phép restart, step liên quan đáp ứng điều kiện và metadata hợp lệ.
- Nếu job dừng bằng `.stop()` hoặc `.stopAndRestart(...)`, cần hiểu rõ điểm tiếp tục của flow và dữ liệu đã commit.
- Một step đã hoàn thành có thể được bỏ qua khi restart theo mặc định, trừ khi flow hoặc cấu hình cho phép thực thi lại trong tình huống đó.
- Reader, writer và các thao tác bên ngoài phải được thiết kế để phục hồi an toàn; transition đúng không tự bảo đảm side effect không bị lặp.

Ví dụ, nếu `importStep` đã commit một số chunk rồi thất bại, lần restart có thể tiếp tục từ checkpoint nếu reader hỗ trợ lưu và khôi phục trạng thái. Nếu writer gọi API bên ngoài, cần có cơ chế idempotency hoặc nhận diện bản ghi đã ghi để tránh tạo kết quả trùng khi một chunk được thực hiện lại.

Không nên dùng `.end()` chỉ để làm cho job hiển thị thành công khi có lỗi kỹ thuật chưa được xử lý. Chỉ kết thúc thành công khi nhánh đó thể hiện một kết quả nghiệp vụ được chấp nhận, chẳng hạn không có dữ liệu mới hoặc đã chuyển các bản ghi lỗi sang hàng chờ kiểm tra theo đúng quy trình.

## 10. Lỗi thường gặp khi khai báo flow

**Dùng sai mã để so khớp:** `.on("COMPLETED")` so khớp exit code, không phải tên trạng thái Java hay `BatchStatus` được truyền trực tiếp. Nếu listener thay đổi exit code, transition cần khớp với mã mới hoặc dùng pattern phù hợp.

**Thiếu nhánh cho exit code:** nếu step có thể trả về nhiều exit code nhưng flow chỉ khai báo một trường hợp, một kết quả khác có thể không tìm được transition. Hãy liệt kê các kết quả có thể xảy ra và quyết định rõ nhánh fallback.

**Wildcard che mất nhánh cụ thể:** transition `*` quá rộng có thể nhận cả kết quả cần xử lý riêng. Hãy khai báo các pattern cụ thể trước fallback và giữ cho nhánh tổng quát có mục đích rõ ràng.

**Nhầm `.end()` với `.fail()`:** hai thao tác tạo trạng thái job khác nhau và ảnh hưởng đến khả năng restart. Chọn trạng thái kết thúc dựa trên ý nghĩa nghiệp vụ và kế hoạch vận hành.

**Dùng quá nhiều logic trong một step:** nếu step vừa xử lý dữ liệu vừa tự quyết định toàn bộ luồng nghiệp vụ, job khó quan sát và kiểm thử. Có thể tách thành các step nhỏ, dùng exit code hoặc decider để thể hiện quyết định.

**Không kiểm tra luồng restart:** một flow chạy đúng từ đầu chưa chắc restart đúng sau khi lỗi. Cần thử tình huống lỗi ở giữa job, xác nhận metadata, checkpoint và step được thực thi lại như dự kiến.

## 11. Cách thiết kế step flow trong một job thực tế

Khi thiết kế flow, trước hết hãy liệt kê các bước nghiệp vụ và kết quả có thể xảy ra ở mỗi bước. Với từng kết quả, quyết định job nên tiếp tục, chuyển sang bước xử lý khác, kết thúc thành công, thất bại hay dừng để chờ thao tác tiếp theo.

Sau đó, chọn cơ chế biểu diễn điều kiện:

- Dùng `next()` cho chuỗi step tuyến tính.
- Dùng `.on(...).to(...)` khi cần rẽ nhánh theo exit code của step.
- Dùng exit code tùy chỉnh khi step cần báo một kết quả nghiệp vụ cụ thể cho flow.
- Dùng `JobExecutionDecider` khi quyết định phụ thuộc vào dữ liệu hoặc điều kiện ngoài trạng thái step.
- Tách thành `Flow` khi cần đóng gói và tái sử dụng một quy trình con.

Cuối cùng, xác định rõ trạng thái kết thúc và hành vi restart. Kiểm tra rằng mọi exit code có thể xuất hiện đều có transition phù hợp, các nhánh kết thúc mang đúng ý nghĩa vận hành và checkpoint đủ để tiếp tục sau sự cố. Với các nhánh có tác động đến hệ thống ngoài, hãy thiết kế thao tác ghi có thể xử lý an toàn khi được thực hiện lại.

Step flow giúp job Spring Batch thể hiện quy trình xử lý dưới dạng các bước và đường đi có thể quan sát được. Khi kết hợp đúng `ExitStatus`, transition pattern, `JobExecutionDecider` và trạng thái kết thúc, ứng dụng có thể điều phối cả luồng tuyến tính lẫn luồng nghiệp vụ nhiều nhánh một cách rõ ràng và có khả năng vận hành tốt.
