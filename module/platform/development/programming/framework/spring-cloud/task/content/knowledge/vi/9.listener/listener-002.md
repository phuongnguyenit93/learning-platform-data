# onTaskStartup, onTaskEnd và onTaskFailed

## 1. Vì sao Spring Cloud Task cần listener?

**Spring Cloud Task** được dùng để xây dựng ứng dụng Spring Boot có **thời gian chạy hữu hạn**: khởi động, thực hiện tác vụ, ghi nhận kết quả thực thi vào **TaskRepository** rồi kết thúc. Ví dụ, mỗi ngày hệ thống xuất báo cáo, nhập một tệp dữ liệu hoặc đối soát giao dịch theo tham số ngày.

Ở chương **Listener**, chúng ta cần quan sát **những thời điểm quan trọng của vòng đời** mà không phải chèn cùng một đoạn mã kiểm tra vào mọi `ApplicationRunner` hay `CommandLineRunner`. Spring Cloud Task cung cấp giao diện **`TaskExecutionListener`** với ba phương thức:

- **`onTaskStartup(TaskExecution)`:** được gọi khi bắt đầu vòng đời task.
- **`onTaskEnd(TaskExecution)`:** được gọi khi task đi đến giai đoạn hoàn tất, **cả thành công lẫn thất bại** trong các đường đi được framework xử lý.
- **`onTaskFailed(TaskExecution, Throwable)`:** được gọi khi framework ghi nhận một lỗi **không được xử lý** trong lúc thực thi task.

Một listener thích hợp để **ghi log gắn execution ID, cung cấp thông tin kiểm toán ngắn gọn, cập nhật exit message hoặc phát metric**. Nó không thay thế xử lý nghiệp vụ, trình lập lịch, cơ chế retry hoặc transaction của dữ liệu nghiệp vụ.

**Kết quả mong đợi của bài học:** bạn có thể viết một listener Java, dự đoán thứ tự callback ở trường hợp thành công và lỗi, liên kết log với bản ghi `TASK_EXECUTION`, đồng thời tránh những lỗi vận hành phổ biến khi listener ném exception hoặc ghi đè thông tin thất bại.

## 2. Ba callback khác nhau ở điểm nào?

| Callback | Thời điểm và điều kiện | Tham số | Cách dùng thường gặp |
| --- | --- | --- | --- |
| `onTaskStartup` | Khi Spring Cloud Task đã có đối tượng `TaskExecution` cho lần chạy, trước phần xử lý nghiệp vụ của các runner | `TaskExecution` | Ghi execution ID, tên task và thời điểm bắt đầu; chuẩn bị ngữ cảnh quan sát |
| `onTaskEnd` | Trước bước framework cập nhật trạng thái cuối của lần chạy trong repository; được gọi trên cả đường hoàn tất bình thường và lỗi được framework xử lý | `TaskExecution` | Ghi log kết thúc, đo thời gian, đặt exit message nếu phù hợp |
| `onTaskFailed` | Khi có exception chưa xử lý khiến task thất bại; được gọi **trước `onTaskEnd`** | `TaskExecution` và `Throwable` | Ghi loại lỗi, stack trace, bổ sung thông điệp thất bại và metric |

**Lưu ý về thời điểm `onTaskStartup`:** tài liệu hướng dẫn *Features* của một số phiên bản mô tả callback này xảy ra trước khi lưu `TaskExecution`, trong khi **Javadoc TaskExecutionListener 3.0.4** mô tả callback được gọi **sau khi bản ghi đã được lưu**, phù hợp với trình tự của `TaskLifecycleListener` trong mã nguồn tương ứng. Nếu ứng dụng phụ thuộc chính xác vào thời điểm transaction commit/ID xuất hiện, phải kiểm tra mã và thử nghiệm **trên phiên bản thực tế của dự án**. Dù phiên bản nào, không xây logic nghiệp vụ dựa vào giả định rằng listener và commit cơ sở dữ liệu thuộc cùng một giao dịch.

### 2.1. Luồng thành công

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant T as Spring Cloud Task
    participant L as TaskExecutionListener
    participant R as Runner
    participant DB as TaskRepository

    B->>T: Khởi tạo vòng đời task
    T->>DB: Tạo / bắt đầu TaskExecution
    T->>L: onTaskStartup(execution)
    T->>R: Chạy nghiệp vụ
    R-->>T: Hoàn tất bình thường
    T->>L: onTaskEnd(execution)
    T->>DB: Cập nhật END_TIME, EXIT_CODE và thông điệp
    Note over T,DB: Không gọi onTaskFailed trên đường thành công bình thường
~~~

Thứ tự quan trọng: **startup → runner → end → cập nhật trạng thái cuối**. Nếu các runner chỉ khởi tạo công việc bất đồng bộ rồi trả về ngay, listener có thể ghi kết thúc **trước khi công việc nền thật sự xong**.

### 2.2. Luồng lỗi chưa được xử lý

~~~mermaid
sequenceDiagram
    participant T as Spring Cloud Task
    participant L as TaskExecutionListener
    participant R as Runner
    participant DB as TaskRepository

    T->>DB: Tạo / bắt đầu TaskExecution
    T->>L: onTaskStartup(execution)
    T->>R: Chạy nghiệp vụ
    R--xT: Exception chưa xử lý
    T->>L: onTaskFailed(execution, throwable)
    T->>L: onTaskEnd(execution)
    T->>DB: Lưu kết quả cuối và error message
~~~

**Không dùng `onTaskEnd` như đồng nghĩa với “thành công”.** Khi có lỗi, callback này vẫn có thể được gọi sau `onTaskFailed`. Cũng không mặc định callback chạy khi JVM bị **kill -9**, mất điện, hết bộ nhớ hoặc Spring Boot thất bại quá sớm để thiết lập lifecycle.

## 3. TaskExecution trong callback chứa gì?

Đối tượng **`TaskExecution`** chứa metadata của **một lần chạy cụ thể**:

| Thuộc tính | Ý nghĩa và lưu ý |
| --- | --- |
| `getExecutionId()` | ID dùng để liên kết log với bản ghi TaskRepository; mỗi lần chạy có ID riêng |
| `getTaskName()` | Tên task, có thể trùng giữa nhiều lần chạy |
| `getStartTime()` | Thời điểm framework ghi nhận bắt đầu |
| `getEndTime()` | Thời điểm kết thúc được xác lập trong lifecycle; chưa đảm bảo đã commit vào database ngay trong callback |
| `getExitCode()` | Mã trạng thái do framework xác định; đọc theo tình huống và phiên bản |
| `getExitMessage()`, `setExitMessage(...)` | Thông điệp kết quả có thể bổ sung từ listener |
| `getErrorMessage()` | Thông tin lỗi do framework ghi nhận, không thay thế log/stack trace đầy đủ |
| `getArguments()` | Các tham số chạy; có thể chứa dữ liệu nhạy cảm, không log nguyên danh sách một cách tùy tiện |

**Execution ID** là định danh kỹ thuật của từng lần chạy, còn **business key** (ví dụ ngày đối soát) là định danh nghiệp vụ. Nếu chạy lại task với cùng ngày, repository vẫn có thể tạo một execution ID mới. Listener chỉ quan sát; nó **không tự chặn xử lý trùng**.

Trong các phiên bản hiện hành, framework có thể truyền **bản sao của `TaskExecution`** cho listener rồi thu hồi những thay đổi được hỗ trợ như `exitMessage` để đưa vào kết quả cuối. Vì vậy không nên coi đối tượng nhận được là entity có thể tùy ý sửa và được repository tự lưu toàn bộ trường đã thay đổi. Dùng API chính thức và kiểm chứng hành vi trên phiên bản đang dùng.

## 4. Tạo listener bằng giao diện TaskExecutionListener

Để học rõ ba callback, cách trực tiếp nhất là triển khai **`org.springframework.cloud.task.listener.TaskExecutionListener`** và đăng ký lớp đó thành một bean Spring.

### 4.1. Cấu hình minh họa

Ví dụ `application.yml` cho một ứng dụng CLI không khởi động web server:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-import-task

logging:
  level:
    root: INFO
~~~

Để xem lịch sử sau khi process kết thúc, bạn cần cấu hình **DataSource bền vững và schema Spring Cloud Task phù hợp** với phiên bản thư viện. Ví dụ YAML trên chỉ cấu hình vòng đời và tên task, chưa cấp kết nối database; khi thực hành, bổ sung DataSource theo môi trường của bạn, không commit password hoặc secret vào source code.

### 4.2. Listener đầy đủ ba phương thức

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class TaskAuditListener implements TaskExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(TaskAuditListener.class);

    @Override
    public void onTaskStartup(TaskExecution task) {
        log.info("TASK_START executionId={} name={} startedAt={}",
                task.getExecutionId(),
                task.getTaskName(),
                task.getStartTime());
    }

    @Override
    public void onTaskFailed(TaskExecution task, Throwable error) {
        log.error("TASK_FAILED executionId={} errorType={}",
                task.getExecutionId(),
                error.getClass().getSimpleName(),
                error);

        // Exit message nên ngắn và không chứa dữ liệu bí mật.
        task.setExitMessage("FAILED: " + error.getClass().getSimpleName());
    }

    @Override
    public void onTaskEnd(TaskExecution task) {
        log.info("TASK_END executionId={} exitCode={} endedAt={}",
                task.getExecutionId(),
                task.getExitCode(),
                task.getEndTime());

        // Không ghi đè thông điệp lỗi do onTaskFailed đã đặt.
        if (task.getExitCode() != null
                && task.getExitCode() == 0
                && task.getExitMessage() == null) {
            task.setExitMessage("COMPLETED");
        }
    }
}
~~~

**Tại sao triển khai theo cách này?**

- `@Component` cho phép Spring phát hiện listener trong quá trình component scan; framework nhận các bean `TaskExecutionListener` đã đăng ký.
- `onTaskStartup` ghi ID và tên để kết nối các dòng log với một lần chạy.
- `onTaskFailed` giữ lại exception gốc trong log, đồng thời đặt exit message ngắn gọn. Không đặt toàn bộ stack trace chứa secret vào message.
- `onTaskEnd` luôn được gọi trên các đường kết thúc được framework xử lý, nên đặt `exitMessage` **có điều kiện**: chỉ viết “COMPLETED” khi exit code cho biết hoàn tất bình thường, và không ghi đè thông điệp lỗi hiện có.
- Listener **không gọi `System.exit(...)`**, không tự sửa `TaskRepository`, không gọi job nền và không ném ngoại lệ chỉ để thử thông báo lỗi.

Ở một số phiên bản API, cả ba phương thức trong interface có implementation mặc định, vì vậy bạn có thể override riêng callback cần dùng. Việc triển khai đầy đủ như trên giúp nhìn rõ mối quan hệ của ba giai đoạn.

### 4.3. Runner minh họa thành công và thất bại

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyImportTaskApplication {

    private static final Logger log =
            LoggerFactory.getLogger(DailyImportTaskApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(DailyImportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner importRunner() {
        return args -> {
            List<String> dates = args.getOptionValues("businessDate");
            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                        "Can truyen --businessDate=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));
            log.info("IMPORT_BEGIN businessDate={}", date);

            if (args.containsOption("fail")) {
                throw new IllegalStateException("Simulated import failure");
            }

            // Thay bằng xử lý nhập dữ liệu đồng bộ thật.
            log.info("IMPORT_DONE businessDate={}", date);
        };
    }
}
~~~

Các import Java và cấu trúc bean trong hai đoạn trên dùng cách viết tương thích với dòng Spring Boot/Spring Cloud Task hiện đại; cần chọn BOM/dependency cùng phiên bản theo dự án. Nội dung `IMPORT_DONE` chỉ chứng minh runner đi tới nhánh đó trong ví dụ; không thay cho kiểm tra kết quả thực tế tại database nghiệp vụ.

## 5. Thực hành đọc log trên hai lần chạy

Giả sử bạn đóng gói mã thành `daily-import-task.jar`, đã chuẩn bị schema `TaskRepository` và chạy:

~~~bash
java -jar daily-import-task.jar --businessDate=2026-11-23
~~~

Một chuỗi log **minh họa**:

~~~text
2026-11-24 09:00:00 INFO ... TASK_START executionId=41 name=daily-import-task startedAt=...
2026-11-24 09:00:00 INFO ... IMPORT_BEGIN businessDate=2026-11-23
2026-11-24 09:00:01 INFO ... IMPORT_DONE businessDate=2026-11-23
2026-11-24 09:00:01 INFO ... TASK_END executionId=41 exitCode=0 endedAt=...
~~~

Trường `executionId=41` trong ví dụ được dùng nhất quán để tìm log và bản ghi của cùng một lần chạy. Không mặc định lần chạy đầu tiên luôn có ID bằng `1`; nhiều ứng dụng hoặc nhiều process có thể dùng chung repository.

Chạy tình huống lỗi:

~~~bash
java -jar daily-import-task.jar --businessDate=2026-11-24 --fail
~~~

Log minh họa:

~~~text
2026-11-24 09:10:00 INFO  ... TASK_START executionId=42 name=daily-import-task startedAt=...
2026-11-24 09:10:00 INFO  ... IMPORT_BEGIN businessDate=2026-11-24
2026-11-24 09:10:00 ERROR ... TASK_FAILED executionId=42 errorType=IllegalStateException
java.lang.IllegalStateException: Simulated import failure
    at ...DailyImportTaskApplication...
2026-11-24 09:10:00 INFO  ... TASK_END executionId=42 exitCode=1 endedAt=...
~~~

Lỗi chưa xử lý được chuyển ra khỏi runner, nên đường thất bại của lifecycle có thể lần lượt gọi **`onTaskFailed` rồi `onTaskEnd`**. Mã thoát và cách hiển thị lỗi cụ thể phụ thuộc phiên bản và cấu hình Spring Boot; `exitCode=1` trong log là **kết quả minh họa**, không phải ràng buộc bất biến.

Các tiền tố `TASK_START`, `TASK_FAILED`, `TASK_END` và `IMPORT_BEGIN` được **mã ví dụ tự ghi ra**; chúng không phải chuỗi log cố định do Spring Cloud Task phát ra trong mọi dự án.

### Vì sao cần quan sát cả TaskRepository?

Với schema mặc định, bạn có thể truy vấn:

~~~sql
SELECT
    TASK_EXECUTION_ID, TASK_NAME,
    START_TIME, END_TIME,
    EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-import-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Sau đó đối chiếu theo ID của log:

~~~sql
SELECT TASK_EXECUTION_ID, EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_EXECUTION_ID = 42;
~~~

Đối với lần chạy thất bại, `EXIT_MESSAGE` có thể chứa `FAILED: IllegalStateException` do listener đặt; `ERROR_MESSAGE` do framework ghi nhận có thể chứa thông tin bổ sung về exception. **Chỉ sau khi vòng đời kết thúc và transaction ghi metadata commit**, công cụ đọc độc lập mới có thể thấy đầy đủ kết quả. Nếu query ngay trong `onTaskEnd`, repository có thể **chưa có dữ liệu cuối**, bởi callback chạy trước lần cập nhật kết thúc.

## 6. Một lựa chọn khác: annotation @BeforeTask, @AfterTask, @FailedTask

Thay vì triển khai interface, Spring Cloud Task hỗ trợ đánh dấu phương thức trong một bean:

| Interface callback | Annotation tương ứng |
| --- | --- |
| `onTaskStartup(TaskExecution)` | `@BeforeTask` |
| `onTaskEnd(TaskExecution)` | `@AfterTask` |
| `onTaskFailed(TaskExecution, Throwable)` | `@FailedTask` |

Ví dụ:

~~~java
import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.listener.annotation.BeforeTask;
import org.springframework.cloud.task.listener.annotation.FailedTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AnnotatedTaskAudit {

    @BeforeTask
    public void before(TaskExecution execution) {
        System.out.println("Starting execution " + execution.getExecutionId());
    }

    @FailedTask
    public void failed(TaskExecution execution, Throwable error) {
        System.err.println(
                "Failed execution " + execution.getExecutionId()
                + ": " + error.getClass().getSimpleName());
    }

    @AfterTask
    public void after(TaskExecution execution) {
        System.out.println("Ending execution " + execution.getExecutionId());
    }
}
~~~

Trong ứng dụng thực tế, ưu tiên logger thay vì `System.out` và `System.err`; cách viết trên ngắn gọn để dễ thấy sự tương ứng giữa annotation và callback. Cả hai cơ chế **đều gắn với vòng đời Spring Cloud Task**, vì vậy không cần đăng ký cùng một logic dưới cả hai dạng rồi vô tình ghi log/metric hai lần.

**Không nhầm `@AfterTask` với `@PreDestroy`.** `@AfterTask` là callback của vòng đời thực thi task và được gọi trước khi repository cập nhật trạng thái cuối; `@PreDestroy` là callback dọn bean khi `ApplicationContext` đóng, có thể xảy ra ở thời điểm khác.

## 7. Exit message: quy tắc ưu tiên khi nhiều callback cùng đặt

`TaskExecution.setExitMessage(...)` là một cách được Spring Cloud Task hỗ trợ để bổ sung thông tin kết quả. Theo tài liệu framework, nếu nhiều callback đặt exit message thì thứ tự ưu tiên là:

1. **`onTaskEnd`** có ưu tiên cao nhất.
2. Sau đó đến **`onTaskFailed`**.
3. Cuối cùng là **`onTaskStartup`**.

Ví dụ một task lỗi:

~~~java
@Override
public void onTaskStartup(TaskExecution task) {
    task.setExitMessage("STARTED");
}

@Override
public void onTaskFailed(TaskExecution task, Throwable error) {
    task.setExitMessage("FAILED");
}

@Override
public void onTaskEnd(TaskExecution task) {
    task.setExitMessage("DONE");
}
~~~

Trường hợp ba callback đều chạy, thông điệp cuối được ghi có thể là **`DONE`**, khiến người đọc nhầm lẫn dù task đã thất bại. Vì vậy **không nên** đặt `DONE` vô điều kiện trong `onTaskEnd`. Có hai lựa chọn an toàn hơn: chỉ đặt thông điệp thành công nếu exit code phù hợp và chưa có thông điệp lỗi, hoặc dùng những thông điệp trung lập không khiến người vận hành kết luận sai.

Exit message chỉ là **metadata mô tả**. Nó không thay đổi việc dữ liệu nghiệp vụ có được commit thành công hay không. Nếu muốn kiểm soát exit code hoặc ánh xạ lỗi, cần tuân theo cơ chế exit code của Spring Boot/Spring Cloud Task và thử nghiệm trên phiên bản đang dùng.

## 8. Điều gì xảy ra nếu chính listener ném exception?

**Listener là một phần của vòng đời task.** Ngoại lệ từ listener có thể khiến ứng dụng thất bại hoặc ảnh hưởng ghi nhận trạng thái cuối. Theo tài liệu Spring Cloud Task:

- Khi một handler listener ném exception, việc xử lý các listener khác cho **cùng loại callback** sẽ dừng tại đó.
- Các pha callback khác vẫn được framework cố gắng xử lý theo đường lifecycle tương ứng; thứ tự và mức độ hoàn tất phụ thuộc trạng thái khởi tạo.
- Lỗi tại `onTaskStartup` thường khiến task có exit code lỗi (`1` trong kịch bản mặc định).
- Với lỗi tại `onTaskEnd` hoặc `onTaskFailed`, mã thoát tuân theo cơ chế tính mã thoát đã được xác định bởi framework và sự kiện lỗi; không nên trông chờ một `ExitCodeExceptionMapper` luôn sửa được mã thoát trong trường hợp lỗi listener.

Ví dụ lỗi cần tránh:

~~~java
@Override
public void onTaskEnd(TaskExecution task) {
    notificationClient.sendBlocking(task.getExecutionId());
    // Nếu dịch vụ thông báo lỗi, listener có thể ném exception,
    // làm rối thêm trạng thái của một task đã xử lý xong.
}
~~~

Nếu thông báo là **tác động nghiệp vụ bắt buộc**, hãy đưa nó vào runner hoặc workflow có chính sách retry, timeout và idempotency rõ ràng; lúc đó lỗi sẽ được phản ánh đúng trong việc hoàn thành task. Nếu chỉ để **quan sát**, listener nên hoạt động nhanh và tránh phụ thuộc một dịch vụ ngoài có độ tin cậy thấp.

Một listener để thu thập metric có thể xử lý lỗi phát metric riêng và ghi cảnh báo có kiểm soát; tuy nhiên việc nuốt mọi exception vô điều kiện cũng không phù hợp nếu metric là nghĩa vụ kiểm toán quan trọng. Hãy định nghĩa rõ ranh giới giữa **side effect quan sát được phép thất bại** và **điều kiện thành công của nghiệp vụ**.

## 9. Những tình huống cần đặc biệt chú ý

### 9.1. Exception bị bắt rồi bỏ qua

Nếu runner tự bắt exception và **không ném lại**:

~~~java
try {
    importData();
} catch (Exception ex) {
    log.error("Import failed", ex);
    // Không ném lại và không đánh dấu kết quả thất bại.
}
~~~

Spring Boot có thể xem runner đã hoàn tất bình thường, vì vậy **`onTaskFailed` không nhất thiết được gọi**. `onTaskEnd` vẫn có thể chạy và repository ghi trạng thái thành công. Khi yêu cầu nghiệp vụ là “không nhập đủ dữ liệu thì thất bại”, hãy phát tín hiệu lỗi đúng cách (ví dụ ném lại ngoại lệ hoặc dùng cơ chế exit code phù hợp).

### 9.2. Runner khởi động async rồi trả về

~~~java
@Bean
ApplicationRunner riskyRunner(ImportService service) {
    return args -> service.startAsync();
}
~~~

Nếu `startAsync()` bắt đầu một công việc nền rồi trả về ngay, lifecycle có thể kết thúc trước khi dữ liệu thực sự xử lý xong. Khi đó `onTaskEnd` sẽ báo hoàn tất sớm, dù background job có thể lỗi sau này. Với task hữu hạn, nên **đợi kết quả thật** trước khi runner trả về hoặc thiết kế hai quy trình riêng với trạng thái độc lập.

Ví dụ nếu API trả về `CompletableFuture` đại diện toàn bộ công việc:

~~~java
@Bean
ApplicationRunner awaitedRunner(ImportService service) {
    return args -> service.startAsync().join();
}
~~~

Cần có timeout và chính sách hủy/khôi phục khi chạy thật. `join()` đơn lẻ không đủ nếu future không đại diện toàn bộ công việc.

### 9.3. Process bị kill hoặc lỗi khởi tạo quá sớm

Khi tiến trình bị `SIGKILL`, OOM kill hoặc gặp lỗi trước khi lifecycle được thiết lập, có thể **không có đủ callback** hoặc không có bản ghi metadata kết thúc. Không dựa vào `onTaskEnd` như cơ chế duy nhất để giải phóng khóa nghiệp vụ, hoàn tiền hay đảm bảo sự kiện “đã chạy xong”.

Thiết kế vận hành cần timeout, heartbeat hoặc theo dõi pod/process, trạng thái dữ liệu thực tế và quy trình xử lý những bản ghi `END_TIME` còn trống.

### 9.4. Nhiều listener trong cùng ứng dụng

Framework có thể nhận nhiều bean `TaskExecutionListener` và các phương thức annotation. Nếu một handler ném exception, các handler khác ở cùng pha có thể không chạy. Vì vậy:

- Tránh phân tán điều kiện nghiệp vụ bắt buộc ra nhiều listener với thứ tự phụ thuộc nhau.
- Giữ mỗi listener có chức năng rõ ràng và không ghi đè message của listener khác thiếu kiểm soát.
- Nếu cần thứ tự chính xác, phải kiểm tra quy ước ordering và hành vi phiên bản đang dùng; tốt hơn là thiết kế không phụ thuộc thứ tự giữa nhiều listener.
- Log cần có execution ID, không chỉ task name, bởi nhiều tiến trình có thể chạy đồng thời.

### 9.5. Spring Batch bên trong Spring Cloud Task

Khi task khởi chạy **Spring Batch**, phải tách hai vòng đời:

- `TaskExecutionListener` phản ánh **lần chạy ứng dụng task**.
- `JobExecutionListener` và `StepExecutionListener` của Spring Batch phản ánh **job hoặc step**.

Một Batch job chạy bất đồng bộ có thể còn đang hoạt động khi runner của task trả về. Khi đó `onTaskEnd` của Spring Cloud Task không chứng minh Batch job đã thành công. Cần chờ kết quả job hoặc quản lý trạng thái job độc lập qua `JobRepository`/`JobExplorer`.

## 10. Mẫu quyết định dùng callback nào

| Nhu cầu | Callback phù hợp | Lý do |
| --- | --- | --- |
| Gắn execution ID vào log đầu lần chạy | `onTaskStartup` | Có đối tượng TaskExecution để nhận diện lần chạy |
| Ghi nhận mọi lần task đi đến pha kết thúc | `onTaskEnd` | Bao phủ cả đường thành công và nhiều đường thất bại |
| Ghi stack trace khi runner ném exception chưa xử lý | `onTaskFailed` | Có `Throwable` gốc để phân tích lỗi |
| Ghi exit message thất bại ngắn | `onTaskFailed` | Không làm mất nguyên nhân lỗi trong thông điệp |
| Ghi thông điệp thành công | `onTaskEnd`, **có điều kiện** | Tránh ghi đè message của pha failed |
| Đóng tài nguyên bean khi Spring context hủy | `@PreDestroy` hoặc lifecycle bean | Đây là trách nhiệm đóng context, khác với task callback |
| Thực hiện giao dịch nghiệp vụ trọng yếu | **Runner/service nghiệp vụ** | Bảo đảm lỗi tác động đến kết quả task và retry hợp lý |
| Theo dõi chunk hoặc step của Spring Batch | **Batch listeners** | Quan sát đúng cấp độ job/step |

## 11. Bài thực hành tự kiểm chứng

Với mã Java đã trình bày, thực hiện trong môi trường học tập:

1. Cấu hình một `TaskRepository` sử dụng database lưu bền vững, kiểm tra bảng `TASK_EXECUTION` đã tồn tại.
2. Chạy **thành công** với `--businessDate=2026-11-23`; ghi lại execution ID.
3. Tìm ba sự kiện trong log: `TASK_START`, `IMPORT_DONE` và `TASK_END`; không kỳ vọng `TASK_FAILED`.
4. Chạy **thất bại** bằng `--fail`; xác nhận thứ tự `TASK_START → TASK_FAILED → TASK_END` và exception gốc xuất hiện trong log.
5. Tra cứu hai execution ID ở bảng `TASK_EXECUTION`; đối chiếu `EXIT_CODE`, `EXIT_MESSAGE`, `ERROR_MESSAGE` và `END_TIME`.
6. Thử tạm đặt `exitMessage` vô điều kiện trong `onTaskEnd` **chỉ trên môi trường thử nghiệm**; quan sát vì sao thông tin lỗi có thể bị che rồi sửa lại thành điều kiện an toàn.
7. Thử runner bắt rồi bỏ qua exception; quan sát rằng callback failed có thể không được gọi. Khôi phục cách truyền lỗi phù hợp.
8. Nếu cần kiểm thử nhiều listener, tách thử nghiệm khỏi nghiệp vụ thật và quan sát hành vi khi một callback ném exception.

**Checklist đạt yêu cầu:**

- [ ] Đã xác nhận listener được Spring đăng ký và nhận đúng `TaskExecution`.
- [ ] Log startup/end/failed sử dụng execution ID của lần chạy.
- [ ] Không coi `onTaskEnd` là bằng chứng thành công khi chưa kiểm tra exit code.
- [ ] Khi lỗi, `onTaskFailed` được gọi trước `onTaskEnd` trong đường lifecycle thông thường.
- [ ] Exit message thất bại không bị callback end ghi đè.
- [ ] Kết quả đọc từ TaskRepository được kiểm tra **sau khi cập nhật đã commit**.
- [ ] Listener không làm công việc blocking dài, không giữ secret trong log/message.
- [ ] Có quy trình riêng cho process chết đột ngột và task chạy lại cùng tham số.

## 12. Ghi nhớ

Ba phương thức `onTaskStartup`, `onTaskFailed` và `onTaskEnd` giúp mở rộng vòng đời **Spring Cloud Task** theo từng lần thực thi. Thứ tự quan trọng nhất là **startup → end** khi hoàn tất bình thường và **startup → failed → end** khi lỗi chưa xử lý được framework ghi nhận.

Hãy dùng listener để quan sát, kiểm toán gọn và bổ sung metadata; để runner/service xử lý nghiệp vụ, TaskRepository lưu metadata, TaskExplorer đọc lịch sử và scheduler quyết định thời điểm chạy. Với Spring Batch, sử dụng listener của Batch để quan sát job/step. Thiết kế như vậy cho phép theo dõi trạng thái và kết quả tác vụ trong cơ sở dữ liệu mà vẫn giữ mã lỗi, thông điệp và cơ chế khôi phục rõ ràng.

### Tài liệu tham khảo

- [Spring Cloud Task — Task Execution Listener (Features)](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/features.html)
- [TaskExecutionListener — Javadoc 3.0.4](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/listener/TaskExecutionListener.html)
- [TaskLifecycleListener — mã nguồn](https://github.com/spring-cloud/spring-cloud-task/blob/main/spring-cloud-task-core/src/main/java/org/springframework/cloud/task/listener/TaskLifecycleListener.java)
