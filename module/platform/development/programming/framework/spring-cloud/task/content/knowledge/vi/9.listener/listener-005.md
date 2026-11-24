# Đọc TaskExecution và Throwable trong listener của Spring Cloud Task

## 1. Mục tiêu và bài toán thực tế

Một ứng dụng **Spring Cloud Task** được chạy hữu hạn để nhập dữ liệu, xuất báo cáo, đối soát hoặc khởi động Spring Batch Job. Mỗi lần chạy có thể được biểu diễn bằng **`TaskExecution`** và lưu trong **`TaskRepository`**. Khi tác vụ lỗi, người vận hành cần biết lần chạy nào thất bại, vì sao thất bại, kết quả đã lưu đến đâu và có thể chạy lại an toàn không.

Giả sử CronJob chạy tác vụ đối soát:

~~~bash
java -jar payment-reconcile-task.jar --date=2026-11-23
~~~

Nếu CSDL tạm thời mất kết nối, **`TaskExecutionListener`** có thể nhận callback thất bại, đọc `TaskExecution` để lấy mã lần chạy, tên task, thời điểm bắt đầu, đồng thời đọc **`Throwable`** để phân loại nguyên nhân. Listener cũng có thể điền thông điệp kết thúc ngắn vào `exitMessage` trước khi metadata cuối được ghi vào repository.

Cần phân biệt ba loại thông tin: **`TaskExecution` mô tả lần thực thi ứng dụng**; **`Throwable` mô tả lỗi Java thực tế**; **dữ liệu nghiệp vụ** (ví dụ giao dịch đã đối soát) nằm ở nơi lưu kết quả riêng. Listener giúp quan sát vòng đời, không tự bảo đảm transaction, retry hay lưu toàn bộ đầu ra nghiệp vụ.

## 2. Ba callback và trình tự vòng đời

Interface `org.springframework.cloud.task.listener.TaskExecutionListener` có ba phương thức:

~~~java
public interface TaskExecutionListener {
    void onTaskStartup(TaskExecution taskExecution);
    void onTaskEnd(TaskExecution taskExecution);
    void onTaskFailed(TaskExecution taskExecution, Throwable throwable);
}
~~~

| Callback | Dữ liệu nhận | Vai trò |
|---|---|---|
| `onTaskStartup` | `TaskExecution` | Quan sát task ở giai đoạn bắt đầu; ghi thông tin định danh, metric, log |
| `onTaskFailed` | `TaskExecution` và **`Throwable`** | Phân tích exception không được xử lý, gắn loại lỗi, thông điệp kết thúc |
| `onTaskEnd` | `TaskExecution` | Quan sát task sắp kết thúc; có thể điều chỉnh `exitMessage` trước khi repository được cập nhật trạng thái cuối |

Thứ tự trên nhánh bình thường là **startup → end**. Khi task thất bại vì exception không được xử lý và cơ chế lifecycle còn hoạt động, thứ tự là **startup → failed → end**. `onTaskFailed` đến trước `onTaskEnd`.

~~~mermaid
sequenceDiagram
    participant O as CLI / Scheduler
    participant T as Spring Cloud Task
    participant L as TaskExecutionListener
    participant B as Business Service
    participant R as TaskRepository
    O->>T: Khởi chạy ứng dụng
    T->>L: onTaskStartup(TaskExecution)
    T->>R: Ghi metadata bắt đầu
    T->>B: Runner gọi nghiệp vụ
    alt Nghiệp vụ hoàn tất
        B-->>T: Hoàn thành
    else Exception không xử lý
        B-->>T: Ném exception
        T->>L: onTaskFailed(TaskExecution, Throwable)
    end
    T->>L: onTaskEnd(TaskExecution)
    T->>R: Cập nhật metadata kết thúc
    T-->>O: Trả kết quả/mã thoát
~~~

Đây là sơ đồ **khái niệm**. Tài liệu tham khảo của Spring Cloud Task có khác biệt về cách mô tả chính xác thời điểm `onTaskStartup` so với lúc lưu bản ghi đầu tiên ở một số phiên bản/Javadoc. Vì thế không giả định bản ghi đã commit và đọc được từ connection khác ngay trong `onTaskStartup`. `onTaskEnd` được gọi **trước** bước cập nhật kết quả cuối của TaskRepository, do đó các trường trạng thái tại callback cũng chưa phải bằng chứng chắc chắn về kết quả đã commit.

Spring Cloud Task ghi nhận một lần chạy khi application context bootstrap thành công đủ để hệ thống task khởi tạo; lỗi quá sớm trước thời điểm đó có thể không có TaskExecution. Khi JVM bị `SIGKILL`, crash hoặc mất điện, callback kết thúc và ghi metadata **không được bảo đảm**.

## 3. Đọc TaskExecution: ý nghĩa từng trường

`TaskExecution` thuộc package `org.springframework.cloud.task.repository`. Các getter thường dùng:

| Getter | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `getExecutionId()` | `long` | ID duy nhất của lần chạy; nên dùng làm correlation key |
| `getTaskName()` | `String` | Tên ứng dụng task do task-name resolver xác định |
| `getStartTime()` | `LocalDateTime` | Thời điểm task bắt đầu |
| `getEndTime()` | `LocalDateTime` | Thời điểm kết thúc; có thể chưa có ở startup |
| `getExitCode()` | `Integer` | Mã thoát dự kiến/được ghi; có thể `null` khi chưa chốt |
| `getExitMessage()` | `String` | Thông điệp kết thúc, có thể được listener thiết lập |
| `getErrorMessage()` | `String` | Thông tin lỗi do framework ghi nhận, có thể chứa stack trace |
| `getArguments()` | `List<String>` | Các đối số dòng lệnh của ứng dụng |
| `getExternalExecutionId()` | `String` | ID từ hệ thống ngoài nếu được cấu hình |
| `getParentExecutionId()` | `Long` | ID của lần chạy cha nếu có |

Ví dụ:

~~~java
long executionId = taskExecution.getExecutionId();
String taskName = taskExecution.getTaskName();
var startedAt = taskExecution.getStartTime();
Integer exitCode = taskExecution.getExitCode();

log.info(
    "task.lifecycle id={} name={} startedAt={} exitCode={}",
    executionId, taskName, startedAt, exitCode
);
~~~

Để kiểm tra mã thoát, hãy xử lý `Integer` có thể `null`:

~~~java
boolean success = Integer.valueOf(0)
    .equals(taskExecution.getExitCode());
~~~

Không dùng `taskExecution.getExitCode() == 0` nếu có nguy cơ unbox `null`. Cũng không đọc `getEndTime()` rồi tính duration một cách vô điều kiện trong `onTaskStartup`.

**`getArguments()` có thể chứa mật khẩu, token hoặc dữ liệu nhạy cảm.** Hạn chế log toàn bộ arguments; nếu cần biết ngày xử lý, hãy parse một option không nhạy cảm ở tầng runner và gắn context theo cơ chế được kiểm soát.

## 4. Đọc Throwable để tìm nguyên nhân lỗi

Chỉ callback `onTaskFailed` nhận **`Throwable`** trực tiếp:

~~~java
@Override
public void onTaskFailed(
        TaskExecution taskExecution,
        Throwable throwable) {
    String type = throwable.getClass().getName();
    String message = throwable.getMessage();
    Throwable cause = throwable.getCause();
}
~~~

`Throwable` là lớp cha của `Exception` và `Error`, cho phép đọc:

- `getClass().getName()`: loại exception hoặc error.
- `getMessage()`: thông điệp, có thể `null` và có thể chứa dữ liệu nhạy cảm.
- `getCause()`: nguyên nhân trực tiếp khi exception bị bọc qua các tầng.
- `getSuppressed()`: các exception bổ sung, chẳng hạn lúc đóng tài nguyên.
- `getStackTrace()`: vị trí lỗi, dùng trong hệ thống logging nội bộ được phân quyền.

Ví dụ chuỗi nguyên nhân:

~~~text
CompletionException
  └── IllegalStateException: import failed
       └── SQLTransientConnectionException: database unavailable
~~~

Có thể truy tìm root cause mà không parse text stack trace:

~~~java
private static Throwable rootCause(Throwable original) {
    Throwable current = original;
    while (current.getCause() != null
            && current.getCause() != current) {
        current = current.getCause();
    }
    return current;
}
~~~

Khi root cause là `SQLTransientConnectionException`, đó là một tín hiệu để **đánh giá** retry. Chưa thể kết luận “retry luôn an toàn” vì nghiệp vụ có thể đã commit một phần trước lỗi. Cần idempotency, checkpoint hoặc cách đối soát theo yêu cầu.

### Phân biệt Throwable với errorMessage

`Throwable` là đối tượng lỗi Java thực tế đang có tại thời điểm callback, còn `TaskExecution.getErrorMessage()` là chuỗi được framework lưu/chuẩn bị lưu vào metadata. Trường errorMessage có thể chưa được điền tại đúng thời điểm callback, bị giới hạn dung lượng hoặc phản ánh định dạng stack trace. Vì vậy, trong `onTaskFailed` hãy ưu tiên **Throwable để phân loại lỗi**; khi tra cứu các lần chạy cũ qua repository, dùng `errorMessage` làm dấu vết bổ sung.

Không đưa nguyên vẹn `throwable.getMessage()`, stack trace hoặc `getArguments()` vào `exitMessage`, dashboard hoặc log không được phân quyền; các giá trị đó có thể lộ SQL, đường dẫn, token hay dữ liệu cá nhân.

## 5. Ví dụ triển khai TaskExecutionListener

Ví dụ sau log tên task, ID, thời điểm bắt đầu, loại lỗi gốc và đặt một `exitMessage` ngắn. Bean được đăng ký bằng `@Component`.

~~~java
package example.task;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AuditTaskListener implements TaskExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(AuditTaskListener.class);

    @Override
    public void onTaskStartup(TaskExecution execution) {
        log.info(
            "task.started executionId={} taskName={} startTime={}",
            execution.getExecutionId(),
            execution.getTaskName(),
            execution.getStartTime()
        );
    }

    @Override
    public void onTaskFailed(
            TaskExecution execution, Throwable throwable) {

        Throwable cause = rootCause(throwable);
        String rootType = cause.getClass().getSimpleName();

        // Không log message gốc nếu chưa có chính sách che dữ liệu.
        log.error(
            "task.failed executionId={} name={} rootType={}",
            execution.getExecutionId(),
            execution.getTaskName(),
            rootType
        );

        execution.setExitMessage("FAILED: " + rootType);
    }

    @Override
    public void onTaskEnd(TaskExecution execution) {
        log.info(
            "task.ending executionId={} exitCode={}",
            execution.getExecutionId(),
            execution.getExitCode()
        );

        // Giữ lại thông điệp đã đặt tại onTaskFailed.
        if (execution.getExitMessage() == null) {
            execution.setExitMessage("Task execution ended");
        }
    }

    private static Throwable rootCause(Throwable original) {
        Throwable current = original;
        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

**Giải thích lựa chọn:**

1. Đọc trực tiếp đối tượng `TaskExecution` mà framework truyền vào thay vì query repository lại trong callback.
2. Gắn `executionId` vào log để đối chiếu nhiều lần chạy cùng `taskName`.
3. Khi thất bại, tìm loại lỗi gốc từ `Throwable` và đặt `exitMessage` ngắn, không chứa dữ liệu nghiệp vụ hay stack trace.
4. `onTaskEnd` tránh ghi đè thông điệp lỗi đã thiết lập; nó chỉ bổ sung thông điệp khi còn trống.
5. Không tự ý đặt lại `exitCode` trong callback; mã thoát và chính sách ánh xạ exception nên được xử lý có chủ đích ở tầng ứng dụng/framework.

Listener này chỉ giúp quan sát. Nếu `RevenueService` hoặc `ImportService` nộp công việc `@Async` vào executor rồi runner trả về, listener **không tự biết** mọi future đã hoàn tất. Runner phải chờ và kiểm tra lỗi của những công việc bắt buộc trước khi kết thúc.

## 6. Đăng ký bằng annotation thay vì interface

Spring Cloud Task hỗ trợ cách viết ngắn bằng annotation:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedTaskObserver {

    private static final Logger log =
        LoggerFactory.getLogger(AnnotatedTaskObserver.class);

    @BeforeTask
    public void before(TaskExecution execution) {
        log.info("Before task {}", execution.getExecutionId());
    }

    @FailedTask
    public void failed(
            TaskExecution execution, Throwable throwable) {
        log.warn("Task {} failed: {}",
            execution.getExecutionId(),
            throwable.getClass().getSimpleName());
        execution.setExitMessage("FAILED");
    }

    @AfterTask
    public void after(TaskExecution execution) {
        log.info("After task {}", execution.getExecutionId());
    }
}
~~~

| Interface | Annotation tương ứng |
|---|---|
| `onTaskStartup(TaskExecution)` | `@BeforeTask` |
| `onTaskFailed(TaskExecution, Throwable)` | `@FailedTask` |
| `onTaskEnd(TaskExecution)` | `@AfterTask` |

Có thể dùng hai kiểu trong cùng ứng dụng cho các trách nhiệm khác nhau, nhưng tránh vô tình đăng ký **hai listener cùng ghi metric/log** cho cùng mục đích. Không dựa vào thứ tự ngầm định giữa những bean listener độc lập. Annotation của Spring Cloud Task cũng **khác** listener của Spring Batch như `@BeforeStep` và `@AfterStep`.

## 7. ExitMessage, ErrorMessage và ExitCode

| Trường | Mục đích | Ví dụ |
|---|---|---|
| `exitMessage` | Thông điệp tổng hợp có thể đặt trong listener | `FAILED: SQLTransientConnectionException` |
| `errorMessage` | Mô tả lỗi do framework lưu, có thể chứa stack trace | `... SQLException ...` |
| `exitCode` | Giá trị mã thoát của lần chạy theo cơ chế framework/ứng dụng | `0` hoặc `1` |

Tài liệu Spring Cloud Task mô tả **thứ tự ưu tiên khi listener đặt `exitMessage`**:

1. Giá trị đặt tại `onTaskEnd` được ưu tiên cao nhất.
2. Sau đó là giá trị từ `onTaskFailed`.
3. Cuối cùng là giá trị từ `onTaskStartup`.

Vì vậy nếu `onTaskFailed` đặt `FAILED` mà `onTaskEnd` luôn đặt `SUCCESS`, metadata có thể bị ghi đè thành thông điệp gây hiểu nhầm. Nếu muốn thông điệp kết thúc phản ánh logic nghiệp vụ, hãy xác định quy tắc thống nhất và không mặc định “đã vào onTaskEnd thì thành công”.

`exitMessage` không thay thế mã thoát hoặc trạng thái nghiệp vụ. Với yêu cầu mã lỗi cụ thể, Spring Boot có các cơ chế như `ExitCodeExceptionMapper` và `ExitCodeGenerator` tùy phiên bản và cách xử lý exception. Thống nhất kết quả này với hệ thống điều phối, thay vì coi một chuỗi exitMessage là căn cứ duy nhất để retry.

## 8. Tại sao onTaskFailed đôi khi không được gọi?

Spring Cloud Task chỉ gọi `onTaskFailed` cho các lỗi **mà vòng đời task quan sát được**. Nếu runner nuốt exception rồi kết thúc bình thường, callback thất bại có thể không xuất hiện.

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@Bean
ApplicationRunner unsafeRunner(ReportService service) {
    return args -> {
        try {
            service.exportAll();
        } catch (Exception ex) {
            // Chỉ ghi log rồi trả về:
            // framework có thể coi runner đã thành công.
            System.err.println(ex.getClass().getSimpleName());
        }
    };
}
~~~

Hướng phù hợp hơn:

~~~java
@Bean
ApplicationRunner safeRunner(ReportService service) {
    return args -> {
        // Cho lỗi nghiệp vụ lan lên quá trình thực thi task.
        service.exportAll();
    };
}
~~~

Nếu cần bổ sung log theo correlation ID, có thể bắt và **ném lại exception**; không được che lỗi rồi mong listener suy đoán từ dòng log.

Đặc biệt với `CompletableFuture`, `@Async` và `TaskExecutor`, việc gửi công việc sang luồng khác rồi trả về sớm có thể khiến task bị chốt thành công. Cần chờ completion, kiểm tra exception trong future và có timeout giới hạn. Nếu yêu cầu phục hồi sau restart, cần bổ sung lưu trạng thái bền vững ngoài bộ nhớ JVM.

## 9. Khi chính listener ném exception

Đây là lỗi vận hành quan trọng. Giả sử `onTaskFailed` gọi một hệ thống gửi cảnh báo qua mạng; nếu API cảnh báo bị timeout và ném lỗi, listener có thể gây ra **exception thứ cấp** trong khi framework đang cố ghi nhận lỗi ban đầu.

Tài liệu Spring Cloud Task nêu rằng khi callback của một listener ném exception, việc gọi các listener còn lại cho loại event đó có thể dừng. Exception tại `onTaskStartup` có quy tắc mã thoát riêng; exception ở `onTaskFailed` hoặc `onTaskEnd` không nên được giả định luôn biến thành mã thoát 1. Cơ chế `ExitCodeExceptionMapper` cũng không nhất thiết xử lý được exception do chính listener ném theo cách xử lý lỗi nghiệp vụ.

Mẫu nên tránh:

~~~java
@Override
public void onTaskFailed(
        TaskExecution execution, Throwable throwable) {
    externalAlertService.send(throwable); // I/O có thể treo hoặc lỗi.
}
~~~

Mẫu chịu lỗi cho thành phần giám sát không bắt buộc:

~~~java
@Override
public void onTaskFailed(
        TaskExecution execution, Throwable throwable) {
    try {
        metrics.recordFailure(
            execution.getTaskName(),
            throwable.getClass().getSimpleName()
        );
    } catch (RuntimeException monitoringError) {
        log.warn("Cannot record metric for task {}",
            execution.getExecutionId());
    }
    execution.setExitMessage("FAILED");
}
~~~

`metrics` là service giám sát do ứng dụng cung cấp, không phải API có sẵn của `TaskExecutionListener`. Nếu audit bắt buộc phải bền vững, nên thiết kế lưu audit tại tầng nghiệp vụ cùng transaction hoặc outbox, có cơ chế retry riêng. Callback listener không phù hợp để thực hiện một giao dịch mạng dài trong lúc tiến trình cần kết thúc.

## 10. Tra cứu TaskExecution đã lưu

Sau khi một lần chạy kết thúc, dùng `TaskRepository` hoặc truy vấn metadata để xác nhận các trường đã được commit. Ví dụ SQL với tên bảng mặc định:

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    EXIT_MESSAGE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Nếu dự án đổi `table-prefix` hay schema, phải sửa tên bảng tương ứng. Đừng giả định tên bảng mặc định khi hệ thống có migration và cấu hình tùy chỉnh.

~~~mermaid
flowchart TD
    L["TaskExecutionListener"] --> A["Log: executionId, taskName, errorType"]
    L --> R["TaskRepository: trạng thái và exitMessage"]
    B["Business Service"] --> D["Kho kết quả nghiệp vụ/checkpoint"]
    O["CronJob/API/orchestrator"] --> X["Mã thoát và trạng thái tiến trình"]
    A --> I["Phân tích sự cố"]
    R --> I
    D --> I
    X --> I
~~~

**Không suy luận chỉ từ `END_TIME IS NULL` rằng task chắc chắn thất bại:** task có thể đang chạy, bị treo hoặc đã chết trước khi cập nhật metadata. Đối chiếu trạng thái container/JVM, log và dữ liệu nghiệp vụ rồi mới quyết định chạy lại.

Nếu quy trình xử lý đã ghi dữ liệu rồi JVM bị kill trước lúc `TaskRepository` chốt lần chạy, dữ liệu có thể đã hoàn tất nhưng metadata còn dở dang. Khi retry, dùng idempotency key và kiểm tra trạng thái nghiệp vụ để tránh nhân đôi kết quả.

## 11. Spring Cloud Task Listener và Spring Batch Listener

Trong ứng dụng có Spring Batch, phân biệt:

| Thành phần | Đơn vị theo dõi | Listener / nơi tra cứu |
|---|---|---|
| Spring Cloud Task | Một lần chạy **ứng dụng** | `TaskExecutionListener`, `TaskRepository` |
| Spring Batch | Một lần chạy **job** và từng step | `JobExecutionListener`, `StepExecutionListener`, `JobRepository` |
| Nghiệp vụ riêng | Giao dịch, file, report, message | Service và bảng/kho nghiệp vụ |

`TaskExecutionListener.onTaskFailed(TaskExecution, Throwable)` báo lỗi ở cấp lần chạy ứng dụng. Nó không thay thế phân tích `JobExecution` và các exception theo step của Spring Batch.

Một job Batch có thể thất bại nhưng runner không ném lỗi ra ngoài nếu ứng dụng không kiểm tra trạng thái `JobExecution`; khi đó task cấp ứng dụng có thể được nhìn nhận là thành công. Phải thiết kế cách ánh xạ kết quả job sang kết quả task một cách rõ ràng.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
|---|---|---|
| Listener không được gọi | Bean không được đăng ký/scan; Spring Cloud Task chưa bật/cấu hình đúng | Kiểm tra dependency, `@Component`/`@Bean` và quá trình bootstrap |
| Có exception nhưng không vào `onTaskFailed` | Runner nuốt lỗi hoặc lỗi nằm trong future chưa đợi | Truyền lỗi lên runner, đợi và kiểm tra future |
| `getExitCode()` là `null` | Mã cuối chưa được đặt | Xử lý nullable và kiểm tra repository sau khi chạy |
| `getEndTime()` trống ở startup | Lần chạy chưa kết thúc | Chỉ tính duration khi đủ dữ liệu |
| `getErrorMessage()` trống trong callback thất bại | Metadata chưa được điền hoặc callback ở thời điểm sớm | Đọc `Throwable` trực tiếp |
| `exitMessage` ghi trong failed bị mất | `onTaskEnd` hoặc listener khác ghi đè | Rà soát thứ tự và điều kiện gọi setter |
| Log bị lộ secret | Log toàn arguments/exception raw | Mask secret; chỉ log định danh và loại lỗi |
| DB metadata khác log listener | Callback trước commit, lỗi repository hoặc crash | Đối chiếu repository, process và dữ liệu nghiệp vụ |
| Task có exit 0 dù báo cáo thiếu | Công việc bất đồng bộ chưa xong; tiêu chí nghiệp vụ chưa được kiểm tra | Chờ completion, truyền lỗi ra ngoài |
| Callback lỗi làm mất thông tin lỗi gốc | Listener gọi API bên ngoài và ném exception | Tách audit quan trọng, giới hạn I/O, bắt lỗi phụ |

## 13. Thực hành kiểm chứng hai nhánh thành công và thất bại

Tạo một task minh họa có Spring Cloud Task, datasource và metadata schema phù hợp phiên bản, cùng listener `AuditTaskListener` ở trên. Runner nhận `--mode`:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DemoTaskConfiguration {

    @Bean
    ApplicationRunner demoRunner() {
        return args -> {
            var modes = args.getOptionValues("mode");
            if (modes == null || modes.size() != 1) {
                throw new IllegalArgumentException(
                    "Use --mode=success or --mode=fail");
            }

            switch (modes.get(0)) {
                case "success" -> System.out.println("Completed");
                case "fail" -> throw new IllegalStateException(
                    "Simulated failure");
                default -> throw new IllegalArgumentException(
                    "Unsupported mode");
            }
        };
    }
}
~~~

Chạy theo thứ tự:

~~~bash
java -jar demo-task.jar --mode=success
java -jar demo-task.jar --mode=fail
~~~

Dự kiến quan sát được:

1. Nhánh thành công có `onTaskStartup` và `onTaskEnd`, không có `onTaskFailed`.
2. Nhánh thất bại có `onTaskStartup`, `onTaskFailed` rồi `onTaskEnd` nếu ứng dụng kịp xử lý lỗi theo vòng đời thông thường.
3. `executionId` khác nhau giữa hai lần chạy.
4. `Throwable` ở nhánh lỗi có thể cho thấy `IllegalStateException` (hoặc lớp bao bọc tùy đường xử lý).
5. Sau mỗi lần, query `TaskRepository` để xác minh `exitCode`, `exitMessage` và thời điểm kết thúc.
6. Thử bắt rồi nuốt exception trong runner để quan sát vì sao callback thất bại có thể không được gọi.

Khi thử `SIGTERM`, `SIGKILL` hay tình huống database không truy cập được, không mặc định mọi listener hay bước lưu metadata luôn thực thi. Đây là giới hạn của một tiến trình có thời gian sống hữu hạn.

## 14. Kết luận và checklist

Đối với một ứng dụng **Spring Cloud Task** cần theo dõi lỗi và kết quả tác vụ trong CSDL:

- Dùng `TaskExecution` để lấy **ID lần chạy, tên, thời gian, mã thoát và thông điệp**; luôn xử lý các trường có thể `null`.
- Dùng `Throwable` trong `onTaskFailed` để đọc **loại lỗi, cause chain và stack trace khi cần**.
- Đặt `exitMessage` ngắn, an toàn; tránh ghi đè lỗi trong `onTaskEnd`.
- Cho exception nghiệp vụ lan lên runner và chờ các tác vụ bất đồng bộ bắt buộc.
- Giữ listener nhẹ, tránh I/O không giới hạn hoặc lỗi thứ cấp che nguyên nhân gốc.
- Đối chiếu log listener, metadata trong TaskRepository, kết quả nghiệp vụ và trạng thái bộ điều phối.
- Thiết kế retry/idempotency, vì callback kết thúc có thể không chạy khi JVM bị kill.

**`TaskExecutionListener` là điểm quan sát vòng đời và diễn giải lỗi; `TaskRepository` là nơi lưu metadata của lần chạy.** Sử dụng đúng hai cơ chế này cùng với xử lý exception và lưu kết quả nghiệp vụ giúp vận hành an toàn các tác vụ theo lịch hoặc yêu cầu.

### Tài liệu đối chiếu

- [Spring Cloud Task — Features: Task Execution Listener](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — API TaskExecution](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExecution.html)
- [Spring Cloud Task — API TaskExecutionListener](https://docs.spring.io/spring-cloud-task/docs/2.3.4/apidocs/org/springframework/cloud/task/listener/TaskExecutionListener.html)
