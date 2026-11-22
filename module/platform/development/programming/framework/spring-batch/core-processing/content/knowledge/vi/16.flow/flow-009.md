# Decider quyết định bước tiếp theo

Trong Spring Batch, `JobExecutionDecider` cho phép Job chọn Step hoặc nhánh xử lý tiếp theo dựa trên dữ liệu của lần chạy hiện tại. Thay vì luôn đi theo một chuỗi Step cố định, Job có thể rẽ nhánh theo JobParameters, kết quả của Step trước đó hoặc một điều kiện nghiệp vụ đã được tính toán.

Ví dụ, một Job nhập dữ liệu có thể chọn một trong ba hướng: nhập toàn bộ dữ liệu, chỉ nhập phần thay đổi hoặc kết thúc sớm khi không có dữ liệu cần xử lý. `Decider` đưa ra kết quả quyết định; flow của Job ánh xạ kết quả đó tới Step tiếp theo.

## 1. JobExecutionDecider là gì?

`JobExecutionDecider` là interface dùng để quyết định trạng thái flow tại một điểm trong Job. Interface có phương thức:

```java
public interface JobExecutionDecider {
    FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution);
}
```

Phương thức `decide()` nhận hai đối tượng:

- `JobExecution`: thông tin của lần chạy Job, bao gồm JobParameters, Job ExecutionContext và trạng thái thực thi.
- `StepExecution`: thông tin lần thực thi Step ngay trước điểm quyết định, nếu có. Giá trị này có thể là `null` khi Decider được gọi ở vị trí chưa có StepExecution trước đó.

Decider trả về `FlowExecutionStatus`. Flow sử dụng status này để chọn transition đã khai báo, từ đó chuyển đến Step, kết thúc, thất bại hoặc dừng Job.

Decider không đọc và xử lý từng item như `ItemProcessor`; nó cũng không phải một Step. Nó là một điểm điều khiển luồng nằm giữa các Step hoặc ở đầu một flow.

## 2. FlowExecutionStatus dùng để làm gì?

`FlowExecutionStatus` biểu diễn kết quả tại cấp flow. Spring Batch có một số giá trị phổ biến:

| Giá trị | Ý nghĩa khái quát |
|---|---|
| `COMPLETED` | Flow đã hoàn thành bình thường. |
| `FAILED` | Flow thất bại. |
| `STOPPED` | Flow được dừng. |
| `UNKNOWN` | Không xác định được kết quả flow. |

Decider cũng có thể trả về status tùy chỉnh bằng cách tạo `FlowExecutionStatus` mới:

```java
return new FlowExecutionStatus("FULL_IMPORT");
```

Tên status tùy chỉnh nên ngắn, rõ nghĩa và ổn định vì nó được dùng trong cấu hình transition của Job. Ví dụ `FULL_IMPORT`, `INCREMENTAL_IMPORT` hoặc `NO_DATA`.

### Phân biệt FlowExecutionStatus, ExitStatus và BatchStatus

Ba khái niệm này thường xuất hiện cùng nhau nhưng có mục đích khác nhau:

| Khái niệm | Thuộc về | Vai trò |
|---|---|---|
| `BatchStatus` | JobExecution hoặc StepExecution | Trạng thái vòng đời thực thi như `COMPLETED`, `FAILED`, `STOPPED`. |
| `ExitStatus` | JobExecution hoặc StepExecution | Mã kết quả thoát; có thể chứa mã nghiệp vụ tùy chỉnh. |
| `FlowExecutionStatus` | Flow và kết quả từ Decider | Trạng thái dùng để chọn transition tiếp theo trong flow. |

Ví dụ, một Step có thể kết thúc với `ExitStatus` là `NO_DATA`, sau đó Decider đọc thông tin cần thiết và trả về `FlowExecutionStatus("SKIP_IMPORT")`. Flow có thể dùng `SKIP_IMPORT` để đi thẳng đến Step tổng kết. Không nên giả định mã ExitStatus của Step tự động chính là FlowExecutionStatus của Decider.

## 3. Ví dụ đơn giản: chọn chế độ nhập dữ liệu

Giả sử `customerImportJob` hỗ trợ hai chế độ:

- `FULL`: nhập lại toàn bộ dữ liệu khách hàng.
- `INCREMENTAL`: chỉ nhập các thay đổi kể từ lần đồng bộ trước.

Chế độ được truyền bằng JobParameter tên `importMode`. Decider đọc tham số và trả về status tương ứng:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.flow.FlowExecutionStatus;
import org.springframework.batch.core.job.flow.JobExecutionDecider;
import org.springframework.stereotype.Component;

@Component
public class ImportModeDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        String mode = jobExecution.getJobParameters()
                .getString("importMode", "INCREMENTAL");

        if ("FULL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("FULL_IMPORT");
        }

        if ("INCREMENTAL".equalsIgnoreCase(mode)) {
            return new FlowExecutionStatus("INCREMENTAL_IMPORT");
        }

        return new FlowExecutionStatus("INVALID_MODE");
    }
}
```

Decider không tự gọi Step. Nó chỉ trả status để Job flow quyết định hướng đi. Nếu giá trị không hợp lệ, Decider trả `INVALID_MODE`; cấu hình Job cần ánh xạ status này tới một transition rõ ràng.

## 4. Khai báo transition trong JobBuilder

Với Spring Batch 5 trở lên, có thể nối Step và Decider bằng `JobBuilder` cùng các phương thức `start()`, `next()`, `from()` và `on()`.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CustomerImportJobConfig {

    @Bean
    public Job customerImportJob(
            JobRepository jobRepository,
            Step validateInputStep,
            Step fullImportStep,
            Step incrementalImportStep,
            Step summaryStep,
            ImportModeDecider importModeDecider) {

        return new JobBuilder("customerImportJob", jobRepository)
                .start(validateInputStep)
                .next(importModeDecider)
                .from(importModeDecider).on("FULL_IMPORT").to(fullImportStep)
                .from(importModeDecider).on("INCREMENTAL_IMPORT").to(incrementalImportStep)
                .from(importModeDecider).on("INVALID_MODE").fail()
                .from(fullImportStep).on("*").to(summaryStep)
                .from(incrementalImportStep).on("*").to(summaryStep)
                .end()
                .build();
    }
}
```

Flow của Job trên có thể hình dung như sau:

```text
                 validateInputStep
                        |
                        v
                 ImportModeDecider
                  /      |       \
          FULL_IMPORT  INCREMENTAL  INVALID_MODE
               |          |             |
               v          v             v
          fullImport  incremental    Job FAILED
               |       ImportStep
               |          |
               +----+-----+
                    |
                    v
                summaryStep
                    |
                    v
                Job end
```

Ý nghĩa các phương thức:

- `.start(validateInputStep)`: chỉ định Step đầu tiên.
- `.next(importModeDecider)`: gọi Decider sau khi Step kiểm tra đầu vào hoàn thành.
- `.from(importModeDecider).on("FULL_IMPORT").to(fullImportStep)`: nếu Decider trả `FULL_IMPORT`, flow đi đến Step nhập toàn bộ.
- `.from(importModeDecider).on("INCREMENTAL_IMPORT").to(incrementalImportStep)`: chọn Step nhập phần thay đổi.
- `.from(importModeDecider).on("INVALID_MODE").fail()`: đánh dấu flow thất bại nếu chế độ không hợp lệ.
- Các transition từ hai Step nhập dữ liệu đến `summaryStep` nối hai nhánh về cùng một Step tổng kết.
- `.end().build()`: hoàn tất định nghĩa Job flow.

Các mẫu `on()` hỗ trợ pattern matching. Có thể dùng `*` làm nhánh dự phòng cho mọi status còn lại, nhưng nên khai báo rõ các trường hợp quan trọng để tránh một status chưa dự kiến bị điều hướng nhầm sang nhánh thành công.

## 5. Quyết định dựa trên kết quả của Step trước

Decider có thể dùng `StepExecution` để xem kết quả của Step vừa chạy. Ví dụ, Step kiểm tra file lưu số bản ghi hợp lệ vào `ExecutionContext`; Decider đọc số lượng đó để quyết định có cần chạy Step import hay không.

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.flow.FlowExecutionStatus;
import org.springframework.batch.core.job.flow.JobExecutionDecider;

public class DataAvailabilityDecider implements JobExecutionDecider {

    @Override
    public FlowExecutionStatus decide(
            JobExecution jobExecution,
            StepExecution stepExecution) {

        if (stepExecution == null) {
            return new FlowExecutionStatus("UNKNOWN_INPUT");
        }

        int validCount = stepExecution.getExecutionContext()
                .getInt("validRecordCount", 0);

        if (validCount > 0) {
            return new FlowExecutionStatus("HAS_DATA");
        }

        return new FlowExecutionStatus("NO_DATA");
    }
}
```

Step trước có thể ghi số lượng vào Step ExecutionContext:

```java
int validCount = validateInputFile();
contribution.getStepExecution()
        .getExecutionContext()
        .putInt("validRecordCount", validCount);
return RepeatStatus.FINISHED;
```

Nếu Job cần dữ liệu này ở cấp Job hoặc nhiều Step cần dùng, có thể đưa một giá trị phù hợp vào Job ExecutionContext thông qua cơ chế promotion hoặc cập nhật context ở nơi phù hợp. Cần bảo đảm dữ liệu đã được lưu vào metadata trước khi dựa vào nó ở lần restart.

Flow có thể ánh xạ kết quả như sau:

```java
.start(validateInputStep)
.next(dataAvailabilityDecider)
.from(dataAvailabilityDecider).on("HAS_DATA").to(importStep)
.from(dataAvailabilityDecider).on("NO_DATA").to(summaryStep)
.from(dataAvailabilityDecider).on("UNKNOWN_INPUT").fail()
```

Trong ví dụ, file không có bản ghi hợp lệ không nhất thiết là lỗi kỹ thuật. Nếu nghiệp vụ cho phép, Job có thể bỏ qua Step import và đi đến tổng kết. Ngược lại, nếu không có StepExecution hoặc thiếu dữ liệu đầu vào bắt buộc, flow có thể thất bại.

## 6. Dùng Decider để kết thúc hoặc dừng Job

Không phải mọi quyết định đều phải chuyển đến một Step khác. Transition của flow có thể kết thúc Job hoặc đánh dấu thất bại/dừng tùy theo yêu cầu.

Ví dụ:

```java
.start(checkRequestStep)
.next(requestDecider)
.from(requestDecider).on("PROCESS").to(processRequestStep)
.from(requestDecider).on("ALREADY_DONE").end()
.from(requestDecider).on("INVALID").fail()
.end()
.build();
```

Trong cấu hình trên:

- `PROCESS`: tiếp tục xử lý yêu cầu.
- `ALREADY_DONE`: kết thúc flow bình thường mà không chạy Step xử lý.
- `INVALID`: kết thúc flow với kết quả thất bại.

`end()` và `fail()` là các transition action của flow. Cần phân biệt việc kết thúc bình thường với việc đánh dấu thất bại: `end()` hoàn tất flow theo cách bình thường, còn `fail()` kết thúc flow với trạng thái lỗi. Nếu cần dừng Job để chờ restart hoặc can thiệp, có thể cấu hình transition dừng phù hợp thay vì xem tình huống đó là thành công.

Một Job kết thúc bằng `end()` có thể có `BatchStatus.COMPLETED` ngay cả khi Step nghiệp vụ không chạy. Nếu muốn thể hiện một mã kết quả nghiệp vụ riêng như `ALREADY_DONE`, có thể cấu hình ExitStatus phù hợp trong flow và kiểm tra nó ở cấp Job.

## 7. Decider và điều kiện theo ExitStatus của Step

Spring Batch có thể rẽ nhánh trực tiếp theo ExitStatus của Step mà không cần Decider. Nếu điều kiện chỉ là một mã kết quả đã được Step tạo ra, transition trực tiếp thường ngắn gọn hơn.

Ví dụ, nếu Step kiểm tra đầu vào trả `ExitStatus("NO_DATA")`, flow có thể dùng:

```java
return new JobBuilder("importJob", jobRepository)
        .start(validateInputStep)
        .on("COMPLETED").to(importStep)
        .from(validateInputStep).on("NO_DATA").to(summaryStep)
        .from(validateInputStep).on("FAILED").fail()
        .end()
        .build();
```

Khi cần tính toán điều kiện từ nhiều nguồn, đọc JobParameters, kết hợp trạng thái Step trước với dữ liệu nghiệp vụ hoặc áp dụng logic quyết định riêng, `JobExecutionDecider` giúp tập trung logic đó ở một điểm.

| Nhu cầu | Cách phù hợp |
|---|---|
| Chỉ rẽ nhánh theo ExitStatus mà Step đã trả về | Transition trực tiếp với `.on(...)`. |
| Quyết định dựa trên nhiều JobParameters hoặc metadata | `JobExecutionDecider`. |
| Quyết định dựa trên dữ liệu đã lưu trong ExecutionContext | `JobExecutionDecider`. |
| Điều kiện cần truy vấn hoặc tính toán nghiệp vụ riêng | Decider gọi một service phù hợp, giữ thao tác ngắn và có thể lặp an toàn. |

Không nên thêm Decider cho một điều kiện đơn giản đã được biểu diễn rõ bằng ExitStatus của Step. Ngược lại, tránh nhồi logic phức tạp vào chuỗi transition nếu logic đó cần unit test độc lập.

## 8. Đọc JobParameters và ExecutionContext an toàn

Decider thường dùng dữ liệu của JobExecution để quyết định. Khi đọc JobParameters, cần xác định rõ tham số bắt buộc hay tùy chọn và xử lý trường hợp thiếu hoặc sai định dạng.

Ví dụ:

```java
String mode = jobExecution.getJobParameters().getString("importMode");
if (mode == null || mode.isBlank()) {
    return new FlowExecutionStatus("INVALID_MODE");
}
```

Nếu Decider đọc dữ liệu từ StepExecution, cần xử lý trường hợp `stepExecution == null` trước khi truy cập context. Không nên giả định mọi vị trí trong flow đều có một StepExecution trước đó.

ExecutionContext được lưu theo phạm vi JobExecution hoặc StepExecution. Hãy chọn đúng phạm vi:

- Step ExecutionContext dành cho dữ liệu checkpoint hoặc kết quả riêng của một Step.
- Job ExecutionContext dành cho dữ liệu nhỏ cần chia sẻ giữa các Step trong cùng một JobExecution.

Không dùng ExecutionContext để lưu dữ liệu nghiệp vụ lớn. Nếu Decider cần đọc nhiều dữ liệu, nên lưu khóa hoặc thông tin tóm tắt rồi truy vấn nguồn dữ liệu phù hợp.

## 9. Thiết kế Decider ổn định khi restart

Decider có thể được gọi lại khi Job được restart, tùy vị trí trong flow và trạng thái các Step. Do đó, kết quả quyết định nên ổn định với cùng một đơn vị công việc, hoặc trạng thái cần thiết phải được lưu bền vững.

Ví dụ rủi ro: Decider đọc giờ hiện tại để quyết định nhập toàn bộ hay nhập tăng dần. Nếu lần chạy đầu chọn `FULL_IMPORT`, thất bại ở giữa Job, rồi restart vào ngày hôm sau, Decider có thể chọn nhánh khác. Điều này khiến một JobInstance tiếp tục theo flow khác với lần chạy ban đầu.

Các nguyên tắc hữu ích:

1. Dựa vào identifying JobParameters hoặc dữ liệu nghiệp vụ đã lưu cho JobInstance khi quyết định một nhánh cần ổn định.
2. Nếu quyết định được tính từ một Step, lưu kết quả vào ExecutionContext hoặc một bảng trạng thái có thể truy vấn lại.
3. Tránh phụ thuộc vào thời gian hiện tại, random value hoặc trạng thái ngoài không được ghi nhận.
4. Nếu Decider gọi service hoặc database, ưu tiên thao tác đọc; nếu có tác dụng phụ, thiết kế idempotent.
5. Khi thay đổi điều kiện quyết định, xem xét ảnh hưởng tới các JobInstance đang restart.

Một cách đơn giản là tính mode trước khi launch, truyền nó thành JobParameter và giữ nguyên giá trị đó khi restart. Nếu mode thay đổi thì đó có thể là một đơn vị công việc khác, cần cân nhắc định danh và quy trình nghiệp vụ.

## 10. Unit test cho JobExecutionDecider

Decider là một thành phần Java có thể kiểm thử trực tiếp mà không cần chạy toàn bộ Job. Tạo `JobExecution` với JobParameters mong muốn, gọi `decide()` rồi kiểm tra `FlowExecutionStatus`.

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.job.flow.FlowExecutionStatus;

class ImportModeDeciderTest {

    private final ImportModeDecider decider = new ImportModeDecider();

    @Test
    void selectsFullImport() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("importMode", "FULL")
                .toJobParameters();
        JobExecution execution = new JobExecution(
                new JobInstance(1L, "customerImportJob"), parameters);

        FlowExecutionStatus status = decider.decide(execution, null);

        assertEquals("FULL_IMPORT", status.getName());
    }

    @Test
    void selectsIncrementalImport() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("importMode", "INCREMENTAL")
                .toJobParameters();
        JobExecution execution = new JobExecution(
                new JobInstance(2L, "customerImportJob"), parameters);

        FlowExecutionStatus status = decider.decide(execution, null);

        assertEquals("INCREMENTAL_IMPORT", status.getName());
    }
}
```

Unit test nên bao phủ cả mode hợp lệ, mode không hợp lệ, tham số thiếu và trường hợp StepExecution là `null` nếu Decider có sử dụng nó. Với logic quyết định phức tạp, có thể dùng parameterized test để kiểm tra nhiều bộ input.

## 11. Integration test cho flow có Decider

Unit test xác nhận logic của Decider, nhưng chưa chứng minh JobBuilder đã ánh xạ đúng status tới Step. Integration test nên launch Job với từng JobParameters và xác nhận StepExecution nào được tạo.

Ví dụ định hướng:

```java
JobParameters fullParameters = new JobParametersBuilder()
        .addString("importMode", "FULL")
        .addString("testRun", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution fullExecution = jobLauncherTestUtils.launchJob(fullParameters);

assertEquals(BatchStatus.COMPLETED, fullExecution.getStatus());
assertTrue(fullExecution.getStepExecutions().stream()
        .anyMatch(step -> step.getStepName().equals("fullImportStep")));
assertFalse(fullExecution.getStepExecutions().stream()
        .anyMatch(step -> step.getStepName().equals("incrementalImportStep")));
```

Để chạy test này, test context cần đăng ký Job có Decider và các Step tương ứng; `JobLauncherTestUtils` phải được cấu hình trỏ đúng Job. Với mỗi lần launch, dùng identifying parameter riêng như `testRun` để tránh xung đột với JobInstance đã hoàn tất trong lần test trước. Có thể viết test tương tự cho `INCREMENTAL` và `INVALID_MODE`.

Integration test cần xác nhận ít nhất:

- Status do Decider trả về dẫn đến đúng Step.
- Nhánh không được chọn không có StepExecution.
- Status lỗi được ánh xạ thành flow thất bại nếu đó là chính sách mong muốn.
- Job kết thúc với BatchStatus và ExitStatus như dự kiến.
- Khi restart, nhánh được chọn phù hợp với JobParameters và trạng thái đã lưu.

## 12. Những lỗi thường gặp khi dùng Decider

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trả về status nhưng không khai báo transition | Flow không biết phải đi đâu với kết quả đó. | Khai báo `.from(decider).on("STATUS").to(...)` hoặc nhánh kết thúc phù hợp. |
| Nhầm FlowExecutionStatus với ExitStatus | Hai loại status thuộc hai phần khác nhau của flow. | Dùng FlowExecutionStatus cho kết quả Decider; ExitStatus cho Step/Job execution. |
| Chỉ khai báo nhánh thành công | Status bất ngờ có thể không được xử lý rõ ràng. | Thêm nhánh dự phòng hoặc nhánh fail cho trường hợp không hợp lệ. |
| Truy cập StepExecution mà không kiểm tra null | Decider có thể chạy ở vị trí không có StepExecution trước. | Kiểm tra null trước khi đọc StepExecution. |
| Dùng thời gian hiện tại hoặc random để chọn nhánh | Kết quả có thể thay đổi khi restart. | Dùng JobParameters ổn định hoặc lưu kết quả quyết định. |
| Đưa xử lý dữ liệu dài vào Decider | Không có transaction/checkpoint của Step cho phần công việc đó. | Chuyển xử lý vào Step; Decider chỉ chọn hướng đi. |
| Dùng Decider cho điều kiện ExitStatus đơn giản | Cấu hình flow phức tạp hơn cần thiết. | Dùng transition trực tiếp khi kết quả đã có ở Step. |
| Cho rằng nhánh không chạy sẽ có StepExecution | Step không được chọn thường không tạo StepExecution trong lần chạy đó. | Kiểm tra tập StepExecution thực tế thay vì giả định có đủ mọi Step. |

## Kết luận

`JobExecutionDecider` cho phép Job chọn bước tiếp theo bằng cách trả về `FlowExecutionStatus`. Decider có thể dựa trên JobParameters, StepExecution hoặc ExecutionContext; Job flow ánh xạ status đó tới Step, kết thúc hoặc thất bại. Dùng transition trực tiếp khi chỉ cần rẽ nhánh theo ExitStatus đã có, và dùng Decider khi cần logic quyết định riêng. Để flow dễ vận hành, hãy khai báo rõ mọi nhánh quan trọng, xử lý trường hợp không hợp lệ, giữ quyết định ổn định khi restart và kiểm thử cả logic Decider lẫn flow tích hợp.
