# Ghi exitMessage và thứ tự ưu tiên cập nhật

Trong **Spring Cloud Task**, một tác vụ có thời gian chạy hữu hạn được biểu diễn bằng `TaskExecution`. Ngoài thời điểm bắt đầu, thời điểm kết thúc và mã thoát, mỗi lần thực thi còn có thuộc tính **`exitMessage`** để mô tả ngắn gọn kết quả hoặc ngữ cảnh kết thúc. Khi ứng dụng nhập dữ liệu, tạo báo cáo hoặc bảo trì hệ thống, trường này giúp người vận hành đọc nhanh trạng thái của một lần chạy mà không phải xem toàn bộ log.

Bài học thuộc chương **Listener**, tập trung vào ba câu hỏi: làm thế nào ghi `exitMessage` qua listener, vì sao nhiều callback có thể cập nhật cùng một thông báo và **giá trị nào được lưu cuối cùng trong TaskRepository**. Nội dung sử dụng cơ chế `TaskExecutionListener`, các annotation `@BeforeTask`, `@FailedTask`, `@AfterTask`, đồng thời phân biệt `exitMessage` với `exitCode` và `errorMessage`.

## 1. exitMessage dùng để làm gì?

Giả sử một tác vụ xử lý tệp đơn hàng chạy mỗi đêm. Nó có thể kết thúc với một trong các kết quả:

- `IMPORTED; source=orders-2026-11-23; accepted=980; rejected=20`.
- `FAILED; phase=VALIDATION; reason=UNSUPPORTED_HEADER`.
- `SKIPPED; reason=SOURCE_ALREADY_IMPORTED`.

Thông điệp có cấu trúc, ngắn gọn như trên giúp xác định **kết quả nghiệp vụ của một lần chạy**, còn các con số đối soát và lịch sử nguồn nhập vẫn nên nằm trong bảng nghiệp vụ hoặc hệ thống giám sát riêng.

Trong mô hình `TaskExecution`:

| Thuộc tính | Nội dung | Cách sử dụng |
| --- | --- | --- |
| `exitMessage` | Chuỗi do ứng dụng hoặc listener đặt | Diễn giải kết quả, lý do bỏ qua, lỗi nghiệp vụ ở mức khái quát |
| `exitCode` | Mã kết thúc, thường `0` khi thành công và khác `0` khi thất bại | Bộ điều phối quyết định thành công/thất bại và retry |
| `errorMessage` | Thông tin exception khi tác vụ lỗi, có thể gồm stack trace | Chẩn đoán lỗi kỹ thuật, cần kiểm soát quyền truy cập |
| `taskName` và `executionId` | Loại tác vụ và mã lần thực thi | Tra cứu đúng lượt chạy |
| `arguments` | Đối số ứng dụng truyền vào lúc khởi chạy | Đối soát nguồn, kỳ dữ liệu, chế độ chạy |

**`exitMessage` không quyết định `exitCode`.** Ghi `taskExecution.setExitMessage("SUCCESS")` không làm tiến trình thành công nếu exception vẫn xảy ra. Ngược lại, một thông điệp có chữ `FAILED` không tự chuyển mã thoát từ `0` sang `1`.

Spring Cloud Task thường lưu thông điệp cuối cùng vào cột **`TASK_EXECUTION.EXIT_MESSAGE`** của TaskRepository. Theo schema tham khảo chính thức, cột này có kiểu **`VARCHAR(2500)`**; độ dài thực tế còn phụ thuộc phiên bản và DDL của CSDL đang triển khai. Vì thế, chỉ ghi chuỗi tóm tắt ngắn, không nhét JSON lớn, stack trace hay dữ liệu nhạy cảm vào đây.

## 2. Vòng đời listener liên quan đến exitMessage

`TaskExecutionListener` cung cấp ba callback:

1. **`onTaskStartup(TaskExecution)`**: được gọi khi Task bắt đầu, trước phần xử lý chính của các runner.
2. **`onTaskFailed(TaskExecution, Throwable)`**: được gọi khi có lỗi chưa được xử lý trong tác vụ.
3. **`onTaskEnd(TaskExecution)`**: được gọi khi Task kết thúc, trước khi kết quả cuối được cập nhật vào TaskRepository.

Có thể dùng interface hoặc các annotation tương ứng:

| Phương thức của interface | Annotation tương ứng | Vai trò khi ghi thông điệp |
| --- | --- | --- |
| `onTaskStartup` | `@BeforeTask` | Đặt thông điệp dự phòng ban đầu, ví dụ `STARTED` |
| `onTaskFailed` | `@FailedTask` | Ghi nguyên nhân thất bại gọn và đã được phân loại |
| `onTaskEnd` | `@AfterTask` | Ghi thông điệp tổng kết; có thể ghi đè thông điệp đã đặt trước đó |

Các callback ở thời điểm khởi động và kết thúc liên quan đến việc tạo/cập nhật TaskExecution; thứ tự chi tiết giữa thao tác tạo bản ghi ban đầu và callback startup cần kiểm tra theo phiên bản. **Không nên giả định rằng thông điệp `STARTED` đã hiện trong CSDL ngay khi `onTaskStartup` vừa chạy.** Giá trị được quan tâm trong bài này là `EXIT_MESSAGE` của **TaskExecution sau khi hoàn tất cập nhật cuối cùng**.

~~~mermaid
flowchart TD
    A["Khởi động Spring Boot + Spring Cloud Task"] --> B["onTaskStartup / @BeforeTask"]
    B --> C["ApplicationRunner / CommandLineRunner xử lý nghiệp vụ"]
    C --> D{"Phát sinh lỗi chưa xử lý?"}
    D -- "Không" --> F["onTaskEnd / @AfterTask"]
    D -- "Có" --> E["onTaskFailed / @FailedTask"]
    E --> F
    F --> G[("TaskRepository cập nhật TaskExecution<br/>EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE")]
~~~

Trong luồng lỗi thông thường, callback **`onTaskFailed` chạy trước `onTaskEnd`**. Vì vậy, nếu cả hai cùng đặt `exitMessage`, cần hiểu rõ quy tắc ghi đè để không làm mất thông tin thất bại.

## 3. Quy tắc quan trọng nhất: thứ tự ưu tiên cập nhật

Spring Cloud Task quy định thứ tự ưu tiên của `exitMessage` từ **cao xuống thấp**:

```text
onTaskEnd     (@AfterTask)     : ưu tiên 1 — cao nhất
onTaskFailed  (@FailedTask)    : ưu tiên 2
onTaskStartup (@BeforeTask)    : ưu tiên 3 — thấp nhất
```

Đây là **thứ tự ưu tiên đối với thông điệp được ghi**, không phải một quy tắc phân loại lỗi. Trong một lần chạy thất bại, `onTaskFailed` nhận exception trước, rồi `onTaskEnd` vẫn có cơ hội cập nhật `exitMessage` lần cuối.

### 3.1. Bảng tình huống

Giả sử từng callback đặt giá trị sau:

- Startup: `STARTED`.
- Failed: `FAILED: CSV_INVALID`.
- End: `FINISHED`.

| Điều kiện | Startup ghi | Failed ghi | End ghi | `exitMessage` được lưu |
| --- | --- | --- | --- | --- |
| Thành công, chỉ startup viết | `STARTED` | Không gọi | Không sửa | `STARTED` |
| Thành công, end viết | `STARTED` | Không gọi | `FINISHED` | **`FINISHED`** |
| Thất bại, không sửa ở end | `STARTED` | `FAILED: CSV_INVALID` | Không sửa | **`FAILED: CSV_INVALID`** |
| Thất bại, end cũng viết | `STARTED` | `FAILED: CSV_INVALID` | `FINISHED` | **`FINISHED`** |
| Chỉ failed viết khi thất bại | Không sửa | `FAILED: CSV_INVALID` | Không sửa | **`FAILED: CSV_INVALID`** |
| Không callback nào đặt thông điệp | Không sửa | Không sửa | Không sửa | Không có thông điệp tùy biến |

**Trường hợp dễ mắc lỗi:** xử lý thất bại đã được `@FailedTask` ghi `FAILED: CSV_INVALID`, nhưng `@AfterTask` lại đặt vô điều kiện `FINISHED`. Người vận hành khi đọc `EXIT_MESSAGE` sẽ chỉ thấy `FINISHED`, dù mã thoát và `ERROR_MESSAGE` vẫn cho biết tác vụ đã lỗi.

### 3.2. Quy tắc ghi đè và giá trị null

Trong cách `TaskLifecycleListener` xử lý lifecycle của Spring Cloud Task, listener được truyền một `TaskExecution` để cập nhật. Sau khi các callback chạy, framework lấy `exitMessage` mới để cập nhật TaskExecution đang được quản lý; giá trị **khác `null`** có thể thay thế giá trị trước đó.

Điều này dẫn đến hai lưu ý:

- **Không gọi `setExitMessage`** ở `onTaskEnd` nếu muốn giữ nguyên thông điệp đã được callback trước thiết lập.
- Đừng dùng `setExitMessage("")` để diễn đạt “không thay đổi”: chuỗi rỗng vẫn là một chuỗi, có thể **ghi đè thành rỗng**. Khi không cần cập nhật, hãy giữ nguyên giá trị hiện có.

Quy tắc ưu tiên là giữa **ba thời điểm lifecycle**. Nếu có **nhiều listener cùng ghi `exitMessage` ở một thời điểm**, giá trị cuối tùy thuộc thứ tự các listener được gọi trong phiên bản/cấu hình đang chạy. Không nên thiết kế dựa trên một thứ tự ngầm định giữa nhiều bean; hãy chỉ định **một nơi sở hữu thông điệp kết quả cuối**, hoặc phối hợp rõ ràng rồi kiểm thử thứ tự callback.

## 4. Ví dụ 1: ghi thông điệp bằng TaskExecutionListener

Giả sử ứng dụng `invoice-report-task` tạo báo cáo hóa đơn theo ngày. Ta muốn:

- `onTaskStartup`: đặt thông điệp dự phòng `STARTED`.
- `onTaskFailed`: mô tả lỗi bằng **loại exception**, không ghi nội dung dữ liệu nhạy cảm.
- `onTaskEnd`: chỉ thay bằng `COMPLETED` khi không có dấu hiệu thất bại; trên nhánh lỗi, **giữ nguyên thông điệp thất bại**.

~~~java
package example.task;

import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class ExitSummaryListener implements TaskExecutionListener {

    @Override
    public void onTaskStartup(TaskExecution execution) {
        execution.setExitMessage("STARTED");
    }

    @Override
    public void onTaskFailed(
            TaskExecution execution, Throwable failure) {
        // Không đưa failure.getMessage() hoặc stack trace vào
        // exitMessage vì có thể chứa thông tin nhạy cảm.
        execution.setExitMessage(
                "FAILED; errorType=" + failure.getClass().getSimpleName());
    }

    @Override
    public void onTaskEnd(TaskExecution execution) {
        String existing = execution.getExitMessage();

        // @AfterTask vẫn chạy sau @FailedTask, nên phải
        // tránh ghi đè thông điệp lỗi vừa được thiết lập.
        if (existing != null && existing.startsWith("FAILED;")) {
            return;
        }

        Integer code = execution.getExitCode();
        if (Integer.valueOf(0).equals(code)) {
            execution.setExitMessage("COMPLETED; exitCode=0");
        } else {
            // Không gắn nhãn SUCCESS khi mã thoát là lỗi/chưa rõ.
            execution.setExitMessage("ENDED; exitCode=" + code);
        }
    }
}
~~~

Đây là **một bean Spring** nên các callback sẽ được framework phát hiện qua `TaskExecutionListener`. Trong ứng dụng thực tế, cần có `spring-cloud-starter-task`, một DataSource/TaskRepository phù hợp nếu muốn lưu metadata bền vững và một runner thực hiện công việc. Không cần tự gọi `onTaskStartup`, `onTaskFailed`, `onTaskEnd` trong mã nghiệp vụ.

Ví dụ cấu hình tối thiểu cho tác vụ sử dụng PostgreSQL đã được tạo schema:

~~~yaml
spring:
  application:
    name: invoice-report-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      initialize-enabled: false
~~~

Các biến `TASK_DB_*` lấy từ môi trường/secret store; phải tạo bảng metadata theo đúng DDL Spring Cloud Task được triển khai. Đây không phải mã có thể chạy riêng nếu chưa cung cấp dependency, runner và database.

### 4.1. Kịch bản chạy thành công

Giả sử runner nhận `--date=2026-11-23`, tạo báo cáo và trả về bình thường:

~~~text
onTaskStartup: exitMessage = STARTED
runner: tạo báo cáo thành công
onTaskEnd:     exitMessage = COMPLETED; exitCode=0
TaskRepository.EXIT_MESSAGE = COMPLETED; exitCode=0
~~~

Giá trị `COMPLETED` là mô tả **kết quả kết thúc của lần chạy**, không phải thông tin chứng minh bảng báo cáo đã phát hành đúng cho người dùng. Kết quả nghiệp vụ vẫn cần kiểm tra ở nơi lưu báo cáo.

### 4.2. Kịch bản chạy thất bại

Giả sử runner ném `IllegalArgumentException` vì ngày báo cáo sai:

~~~text
onTaskStartup: exitMessage = STARTED
runner: ném IllegalArgumentException
onTaskFailed:  exitMessage = FAILED; errorType=IllegalArgumentException
onTaskEnd:     giữ nguyên vì thông điệp đã bắt đầu bằng FAILED;
TaskRepository.EXIT_MESSAGE =
    FAILED; errorType=IllegalArgumentException
~~~

**Giá trị thất bại được giữ lại vì ta chủ động không ghi đè ở `onTaskEnd`**, chứ không phải vì Spring Cloud Task bỏ qua `onTaskEnd` sau lỗi.

### 4.3. Tình huống không phải exception

Một tác vụ có thể chủ động phát ra mã thoát khác `0` mà không ném exception chưa xử lý. Trong trường hợp đó, `onTaskFailed` có thể không được gọi. Nhánh `onTaskEnd` của ví dụ ghi `ENDED; exitCode=...` để tránh thông báo “thành công” sai. Tùy nhu cầu nghiệp vụ, có thể đặt kết quả chi tiết hơn khi đã biết nguồn gốc mã thoát.

## 5. Ví dụ 2: dùng annotation @BeforeTask, @FailedTask và @AfterTask

Không bắt buộc implement interface. Spring Cloud Task hỗ trợ annotation trên các phương thức bean:

~~~java
package example.task;

import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedExitMessages {

    @BeforeTask
    public void before(TaskExecution execution) {
        execution.setExitMessage("STARTED");
    }

    @FailedTask
    public void failed(
            TaskExecution execution, Throwable cause) {
        execution.setExitMessage(
                "FAILED; errorType=" + cause.getClass().getSimpleName());
    }

    @AfterTask
    public void after(TaskExecution execution) {
        // Chỉ minh họa cách giữ giá trị từ @FailedTask.
        String current = execution.getExitMessage();
        if (current != null && current.startsWith("FAILED;")) {
            return;
        }
        if (Integer.valueOf(0).equals(execution.getExitCode())) {
            execution.setExitMessage("COMPLETED");
        }
    }
}
~~~

**Chọn một trong hai cách đăng ký listener cho ví dụ thực hành.** Nếu đồng thời đăng ký cả `ExitSummaryListener` ở mục trước và `AnnotatedExitMessages` trong cùng một ứng dụng, cả hai sẽ ghi lên cùng một `TaskExecution`. Bạn phải giải quyết rõ ai sở hữu trường `exitMessage` để tránh kết quả phụ thuộc thứ tự bean/callback.

Annotation `@FailedTask` nhận thêm `Throwable` để người viết có thể phân loại lỗi; không nên trả nguyên văn `Throwable.getMessage()` nếu chưa kiểm soát nội dung. Exception có thể chứa email, đường dẫn nội bộ, thông tin kết nối hoặc một phần dữ liệu đầu vào.

## 6. Thiết kế thông điệp kết thúc hữu ích trong nghiệp vụ

### 6.1. Quy ước thông điệp

Một thông điệp tốt thường trả lời **đã làm gì, kết quả ra sao và có thể truy vết ở đâu**. Có thể dùng biểu diễn ngắn, cố định theo `key=value`:

~~~text
COMPLETED; operation=import; sourceId=abc-20261123; accepted=980; rejected=20
FAILED; operation=report; reason=INVALID_DATE; reportDate=2026-11-23
SKIPPED; operation=cleanup; reason=NO_ELIGIBLE_ROWS; cutoff=2026-10-01
~~~

Không cần đặt mọi chi tiết vào một dòng. Với báo cáo lớn, chỉ lưu `reportId` hoặc `artifactId` an toàn; với nhập dữ liệu, lưu `sourceId`, số dòng hợp lệ/từ chối. Tránh thông điệp “Task done” chung chung khiến người đọc không thể phân biệt tác vụ đã làm gì.

| Trường hợp | Đặt `exitMessage` ở đâu? | Gợi ý |
| --- | --- | --- |
| Nhập thành công | `onTaskEnd`, khi đã có kết quả tổng hợp | `IMPORTED; sourceId=...; accepted=...` |
| Lỗi đọc tệp | `onTaskFailed` | `FAILED; reason=INPUT_UNREADABLE` |
| Lỗi kết nối tạm thời | `onTaskFailed` | `FAILED; reason=DEPENDENCY_UNAVAILABLE` |
| Báo cáo đã tồn tại | `onTaskEnd` hoặc trạng thái nghiệp vụ được cung cấp | `SKIPPED; reason=ALREADY_GENERATED` |
| Xóa không có bản ghi đủ điều kiện | `onTaskEnd` | `COMPLETED; deleted=0` |
| Kiểm tra cấu hình đầu vào | `onTaskStartup` chỉ đặt thông điệp dự phòng | `STARTED`; kết quả cuối nên đến sau runner |

Nếu cần đưa số lượng bản ghi, checksum hay report ID từ runner sang listener, nên truyền qua **một bean lưu kết quả có phạm vi phù hợp với một lần chạy**, hoặc một cơ chế trả kết quả nội bộ rõ ràng. Với ứng dụng Spring Cloud Task thông thường, mỗi tiến trình chỉ thực hiện một lượt rồi thoát; trong môi trường phức tạp vẫn phải tránh chia sẻ biến mutable giữa các lượt chạy đồng thời.

### 6.2. Ví dụ chia sẻ kết quả từ runner sang listener

Đoạn dưới đây là **mẫu thiết kế**, không phải tính năng của TaskRepository. Bean `RunSummary` thuộc tiến trình hiện tại; runner ghi kết quả, listener đọc để tạo `exitMessage`.

~~~java
@Component
public class RunSummary {
    private long accepted;
    private long rejected;

    public void record(long accepted, long rejected) {
        this.accepted = accepted;
        this.rejected = rejected;
    }

    public String asExitMessage() {
        return "IMPORTED; accepted=" + accepted
                + "; rejected=" + rejected;
    }
}

@Component
public class ImportSummaryListener {

    private final RunSummary summary;

    public ImportSummaryListener(RunSummary summary) {
        this.summary = summary;
    }

    @AfterTask
    public void after(TaskExecution execution) {
        if (Integer.valueOf(0).equals(execution.getExitCode())) {
            execution.setExitMessage(summary.asExitMessage());
        }
        // Không ghi đè thông điệp lỗi nếu execution đã thất bại.
    }
}
~~~

Đoạn ví dụ giả định `RunSummary` được khởi tạo **mỗi tiến trình Task** và chỉ được runner cập nhật trước khi kết thúc. Trong ứng dụng có xử lý bất đồng bộ, phải chờ mọi tác vụ con hoàn thành và bảo đảm hiển thị bộ nhớ/kết quả trước khi listener chạy. Nếu không, thông điệp có thể chứa số đếm chưa hoàn tất.

Một ứng dụng thực tế cũng cần phân biệt trường hợp runner **bỏ qua xử lý** vì dữ liệu đã hoàn tất; đừng tự đặt `IMPORTED` chỉ vì mã thoát bằng `0` nếu chưa có hành động nhập.

## 7. Khi nào exitMessage được ghi xuống cơ sở dữ liệu?

Với một Task bình thường, framework mở `TaskExecution` ở đầu vòng đời và cập nhật các trường kết thúc khi task hoàn tất. `onTaskEnd` chạy **trước lần cập nhật kết quả cuối**. Vì thế, việc gọi:

~~~java
taskExecution.setExitMessage("COMPLETED; rows=980");
~~~

trong callback thay đổi đối tượng TaskExecution mà listener nhận. Spring Cloud Task tổng hợp kết quả các callback rồi chuyển `exitMessage` cho `TaskRepository` khi hoàn tất.

Dữ liệu mong đợi sau khi kết thúc có thể kiểm tra bằng truy vấn SQL sau, dùng trong ứng dụng với named parameter:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_EXECUTION_ID = :execution_id;
~~~

`:execution_id` là placeholder của lớp truy cập dữ liệu, không phải cú pháp SQL chạy nguyên văn ở mọi công cụ. Nếu đã cấu hình `table-prefix` hoặc schema khác, tên bảng cần được điều chỉnh tương ứng.

| Quan sát ở TaskRepository | Cách hiểu |
| --- | --- |
| `EXIT_CODE=0`, `EXIT_MESSAGE=COMPLETED...` | Tiến trình có mã thoát thành công; tiếp tục đối soát kết quả nghiệp vụ nếu cần |
| `EXIT_CODE<>0`, `EXIT_MESSAGE=FAILED...` | Có kết quả thất bại được mô tả ngắn; dùng log và `ERROR_MESSAGE` để chẩn đoán |
| `EXIT_MESSAGE=FINISHED` dù task thất bại | Nghi ngờ `onTaskEnd` đã ghi đè nội dung do `onTaskFailed` đặt |
| `EXIT_MESSAGE` rỗng/`NULL` | Không có thông điệp tùy biến, callback chưa chạy hoặc không ghi thành công |
| `END_TIME` rỗng rất lâu | Có thể tiến trình chưa kết thúc hoặc đã chết trước khi cập nhật; kiểm tra container/launcher |

Không nên hiểu `EXIT_MESSAGE` là log liên tục theo thời gian. Trong mô hình mặc định, nó là **trường tóm tắt lần thực thi**, thường có ý nghĩa chính sau khi TaskRepository hoàn tất cập nhật. Nếu cần tiến độ trực tiếp theo từng phút, hãy dùng log có cấu trúc, bảng tiến độ nghiệp vụ hoặc hệ thống metrics.

### Phân biệt message với trạng thái của Spring Batch

Trong một tác vụ phối hợp **Spring Batch**, `JobExecution.exitStatus.exitDescription` thuộc metadata **JobRepository** của Batch, còn `TaskExecution.exitMessage` thuộc **TaskRepository** của Spring Cloud Task. Hai giá trị không tự động đồng nhất. Nếu Batch Job lỗi nhưng tiến trình Task vẫn thoát với mã `0`, chỉ sửa `exitMessage` thành `FAILED` sẽ không giúp scheduler coi tiến trình thất bại. Cần cấu hình cơ chế chuyển thất bại Batch Job thành mã thoát phù hợp (ví dụ `spring.cloud.task.batch.fail-on-job-failure` khi phiên bản và tích hợp Batch hỗ trợ), hoặc chủ động phản ánh lỗi theo luồng thiết kế.

## 8. Ngoại lệ trong listener và tác động tới kết quả

Listener là một phần của quá trình kết thúc Task. Nếu một callback tự ném exception, các listener còn lại **trong cùng pha callback** có thể không tiếp tục được gọi. Framework có cơ chế ghi nhận lỗi listener và xác định mã thoát, nhưng không nên dùng exception của listener như cách thường xuyên để tạo thông điệp nghiệp vụ.

Theo hướng dẫn Spring Cloud Task:

- Nếu exception phát sinh tại `onTaskStartup`, quá trình khởi động có thể thất bại và exit code được xử lý là `1`.
- Nếu exception phát sinh tại `onTaskFailed` hoặc `onTaskEnd`, mã thoát tuân theo cơ chế tính exit code của framework (bao gồm `ExitCodeEvent` hoặc `ExitCodeGenerator` trong các trường hợp phù hợp).
- Khi exception phát sinh **trong callback listener**, không nên trông chờ `ExitCodeExceptionMapper` để điều chỉnh mã thoát theo cách áp dụng cho exception nghiệp vụ thông thường.

Điều này dẫn tới nguyên tắc: **callback ghi exitMessage phải ngắn, ổn định và hạn chế phụ thuộc bên ngoài**. Không nên thực hiện API call chậm, ghi dữ liệu lớn hoặc chờ một dịch vụ không thiết yếu trong `onTaskEnd` chỉ để tạo chuỗi mô tả; thất bại của chính hoạt động đó có thể làm phức tạp trạng thái cuối.

Nếu thông điệp được tổng hợp từ dữ liệu nghiệp vụ, phần nghiệp vụ cần tự ghi trạng thái và số liệu trước. Listener chỉ định dạng kết quả đã có, tránh tạo ra “nguồn chân lý thứ hai”.

## 9. Bảo mật và giới hạn dữ liệu

### 9.1. Đừng đưa dữ liệu nhạy cảm vào exitMessage

Tránh:

~~~text
FAILED; dbPassword=secret123
FAILED; customerEmail=person@example.com; rawRecord=...
FAILED; jdbcUrl=jdbc:...; token=...
~~~

Thay bằng:

~~~text
FAILED; reason=DB_UNAVAILABLE; incidentRef=INC-20261124-001
FAILED; reason=INPUT_VALIDATION; sourceId=orders-20261123
~~~

Người vận hành có thể dựa vào **incidentRef**, **sourceId** hoặc **reportId** không nhạy cảm để truy vấn hệ thống chi tiết đã được phân quyền. Đừng lấy nguyên văn `Throwable.getMessage()` đưa vào `EXIT_MESSAGE` nếu chưa bảo đảm nó được làm sạch.

### 9.2. Chống tràn trường và thông điệp khó tra cứu

Schema tham khảo đặt `EXIT_MESSAGE` là `VARCHAR(2500)`. Vì hệ CSDL và phiên bản có thể khác nhau, nên đặt **giới hạn ứng dụng thấp hơn giới hạn DB** (ví dụ một vài trăm ký tự), đồng thời định nghĩa danh sách `reason code` ổn định.

Nếu muốn lưu hàng nghìn lỗi theo dòng CSV, hãy ghi chi tiết vào bảng kết quả hoặc tệp lỗi có đường dẫn quản lý, rồi để `exitMessage` chứa tóm tắt:

~~~text
FAILED; reason=ROW_VALIDATION; rejected=147; errorReportId=err-20261124-01
~~~

Tách này giúp tránh lỗi ghi repository ngay tại bước kết thúc vì thông điệp quá dài. Không dùng `exitMessage` để truyền payload cho tác vụ khác hoặc làm khóa dữ liệu.

## 10. Những sai lầm thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể xảy ra | Cách sửa |
| --- | --- | --- |
| Thất bại nhưng `EXIT_MESSAGE=FINISHED` | `@AfterTask` ghi đè vô điều kiện | Chỉ ghi thông điệp thành công khi xác định thành công; giữ nguyên thông điệp lỗi |
| Thông điệp `STARTED` vẫn còn sau khi task đã thành công | Chỉ startup ghi thông điệp | Bổ sung thông điệp kết quả ở end |
| `EXIT_CODE=0` nhưng message có chữ `FAILED` | Listener tự đặt chuỗi mà không phản ánh lỗi qua mã thoát | Thiết kế lại quy tắc thành công/thất bại, kiểm tra đường dẫn exception và batch exit |
| Trường `EXIT_MESSAGE` trống | Không có listener ghi thông điệp hoặc giá trị bị ghi rỗng | Kiểm tra bean/annotation, thứ tự callback, `setExitMessage("")` |
| Nhiều listener cho kết quả thay đổi khi refactor | Nhiều callback cùng sở hữu message ở một pha | Gom về một listener tổng kết; kiểm thử khi cần nhiều listener |
| Callback cuối ném exception | I/O không cần thiết, định dạng lỗi không an toàn | Thu gọn callback, xử lý dữ liệu trước đó, dùng chuỗi bảo đảm hợp lệ |
| `exitMessage` bị cắt hoặc DB báo lỗi độ dài | Chuỗi dài quá schema | Chỉ ghi tóm tắt, link ID tới dữ liệu chi tiết |
| Không tìm được bản ghi TaskExecution | ApplicationContext không khởi tạo hoàn chỉnh hoặc repository sai | Kiểm tra startup logs, DataSource, migration và môi trường |
| Sau khi Task chết, `END_TIME` vẫn trống | Tiến trình bị kill trước callback cuối | Dùng trạng thái Job/Pod và timeout để phát hiện; không kỳ vọng listener luôn chạy |

## 11. Kịch bản kiểm chứng thứ tự ưu tiên

Sau khi đăng ký **một** listener theo ví dụ mục 4 hoặc 5, hãy chạy các kiểm chứng sau trên CSDL thử nghiệm.

**Kịch bản A — thành công:**

1. Runner nhận dữ liệu hợp lệ và kết thúc bình thường.
2. `onTaskStartup` ghi `STARTED`; `onTaskEnd` ghi `COMPLETED`.
3. Truy vấn `TASK_EXECUTION` xác nhận `EXIT_CODE=0` và `EXIT_MESSAGE=COMPLETED...`.

**Kịch bản B — thất bại:**

1. Runner ném `IllegalArgumentException` do tham số sai.
2. `onTaskFailed` đặt `FAILED; errorType=IllegalArgumentException`.
3. `onTaskEnd` giữ nguyên thông điệp.
4. Truy vấn repository để thấy message lỗi, mã thoát khác `0` và `ERROR_MESSAGE` nếu framework ghi nhận exception.

**Kịch bản C — cố ý ghi đè:**

1. Trong môi trường thử nghiệm, sửa `onTaskEnd` thành `execution.setExitMessage("FINISHED")` vô điều kiện.
2. Chạy lại kịch bản lỗi.
3. Xác nhận `EXIT_MESSAGE=FINISHED` trong khi `EXIT_CODE` vẫn phản ánh lỗi; sau đó khôi phục logic bảo toàn message.

**Kịch bản D — nhiều listener:**

1. Đăng ký hai listener cùng ghi message ở `onTaskEnd`.
2. Quan sát callback nào ghi cuối trong phiên bản hiện dùng.
3. Thay thiết kế để chỉ một listener chịu trách nhiệm kết quả cuối, tránh phụ thuộc vào thứ tự đăng ký.

**Kịch bản E — tiến trình chết đột ngột:**

1. Dùng môi trường thử nghiệm để kill tiến trình khi runner đang chạy.
2. Kiểm tra TaskExecution và log bộ điều phối.
3. Giải thích vì sao có thể không thấy `onTaskEnd` hay thông điệp cuối và vì sao cần timeout/giám sát độc lập.

Tiêu chí đạt: bạn **dự đoán đúng giá trị `EXIT_MESSAGE`** với mỗi kịch bản và phân biệt được message, exit code, error message mà không coi chuỗi message là nguồn đánh giá thành công duy nhất.

## 12. Các điểm cần nhớ

1. Ghi `exitMessage` thông qua `TaskExecution#setExitMessage(String)` trong `TaskExecutionListener` hoặc `@BeforeTask`, `@FailedTask`, `@AfterTask`.
2. **Thứ tự ưu tiên khi cập nhật:** `onTaskEnd` **cao hơn** `onTaskFailed`, và `onTaskFailed` **cao hơn** `onTaskStartup`.
3. `onTaskEnd` vẫn có thể chạy sau thất bại; nếu nó đặt message mới, nội dung do `onTaskFailed` ghi có thể bị thay thế.
4. Tránh nhiều listener cùng sở hữu `exitMessage`; kiểm thử khi phải dùng nhiều callback và không dùng chuỗi rỗng để biểu diễn “giữ nguyên”.
5. **`exitMessage`, `exitCode`, `errorMessage` khác vai trò**. Một message giống “thành công” không chứng minh tiến trình đã thành công.
6. Giữ thông điệp ngắn, an toàn, có mã lý do ổn định và tham chiếu tới dữ liệu chi tiết ngoài repository.
7. Listener nên hoàn thành nhanh và không phụ thuộc nhiều tài nguyên bên ngoài; tiến trình chết bất thường có thể không ghi trạng thái kết thúc.

### Tài liệu tham khảo

- [Spring Cloud Task — Features: Task Execution Listener, Exit Messages](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — TaskRepository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html)
- [Javadoc: TaskExecutionListener](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/listener/TaskExecutionListener.html)
- [Javadoc: TaskExecution](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExecution.html)
