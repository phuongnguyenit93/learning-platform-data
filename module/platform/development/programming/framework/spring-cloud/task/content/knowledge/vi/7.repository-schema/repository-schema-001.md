# Trách nhiệm ghi của TaskRepository và đọc của TaskExplorer

## 1. Hai thành phần cốt lõi của kho thực thi

Trong **Spring Cloud Task**, một ứng dụng Spring Boot chạy hữu hạn có thể được khởi động theo lịch hoặc theo yêu cầu, xử lý một việc rồi kết thúc. Để vận hành được các ứng dụng này, ta cần biết **lần chạy nào đã bắt đầu, kết thúc lúc nào, nhận tham số gì, thành công hay thất bại**. Spring Cloud Task lưu metadata dưới dạng **`TaskExecution`**.

Ở chương **Kho và schema**, hai giao diện phục vụ hai trách nhiệm bổ sung cho nhau:

- **`TaskRepository` — phía ghi:** tạo và cập nhật metadata của một lần thực thi. Vòng đời Spring Cloud Task gọi repository khi bắt đầu và kết thúc task.
- **`TaskExplorer` — phía đọc:** truy vấn metadata đã được lưu, theo ID, tên task, danh sách, số lượng hoặc các mối liên hệ phù hợp.

Chúng cùng làm việc với dữ liệu `TaskExecution`, nhưng **khác cách sử dụng**. Mã xử lý nghiệp vụ thường không cần trực tiếp `INSERT` hay `UPDATE` bảng task; một ứng dụng giám sát có thể dùng `TaskExplorer` để lấy lịch sử mà không cần gọi giao diện ghi.

> Tính chất “read-only” của `TaskExplorer` là **phạm vi API**, không tự động giới hạn quyền SQL của tài khoản kết nối. Muốn dashboard thực sự chỉ đọc database, hãy cấp quyền `SELECT` bằng chính sách database phù hợp.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đường **ghi metadata** qua `TaskRepository` và đường **tra cứu metadata** qua `TaskExplorer`.
2. Nhận biết thông tin chính của `TaskExecution` và các bảng schema liên quan.
3. Tra cứu execution theo ID, tên, lần gần nhất hoặc phân trang bằng Java và SQL.
4. Cấu hình database, schema, table prefix, transaction phù hợp cho hai thành phần.
5. Phân tích tình huống lỗi, tiến trình chết đột ngột, metadata chưa hoàn tất và nhiều lần chạy đồng thời.
6. Phân biệt kho metadata task với `JobRepository` và `JobExplorer` của Spring Batch.

## 2. Ghi và đọc diễn ra ở những thời điểm nào?

Mỗi lần khởi động một ứng dụng Spring Cloud Task thường tương ứng với **một TaskExecution riêng**. Giả sử công việc `daily-import` cần nhập dữ liệu đơn hàng mỗi đêm.

~~~mermaid
flowchart LR
    A["Bộ lập lịch / API"] --> B["Ứng dụng Spring Boot Task"]
    B --> C["Vòng đời Spring Cloud Task"]
    C --> D["TaskRepository (ghi)"]
    D --> E[("Database metadata")]
    E --> F["TaskExplorer (đọc)"]
    F --> G["Dashboard / Kiểm toán / Hỗ trợ"]
    B --> H[("Database nghiệp vụ")]
~~~

Luồng thông thường:

1. **Khởi tạo context:** Spring Boot khởi động thành công. Trước khi các `ApplicationRunner` hoặc `CommandLineRunner` chạy, Spring Cloud Task tạo bản ghi bắt đầu qua `TaskRepository`.
2. **Xử lý nghiệp vụ:** runner nhận tham số và thực hiện công việc hữu hạn. Đây là lúc ghi dữ liệu đơn hàng, file xuất hoặc kết quả xử lý vào hệ thống nghiệp vụ.
3. **Kết thúc:** sau khi các runner hoàn thành hoặc có lỗi được framework ghi nhận, Spring Cloud Task cập nhật metadata kết thúc qua repository.
4. **Tra cứu:** hệ thống vận hành dùng `TaskExplorer` để xem lần chạy hiện tại hoặc lịch sử, kể cả sau khi JVM của task đã thoát, miễn metadata còn được lưu trên database bền vững.

~~~mermaid
sequenceDiagram
    participant T as Spring Cloud Task
    participant R as TaskRepository
    participant DB as Cơ sở dữ liệu
    participant X as TaskExplorer
    participant U as Công cụ vận hành

    T->>R: Ghi nhận bắt đầu TaskExecution
    R->>DB: INSERT ID, tên, thời điểm, tham số
    T->>T: ApplicationRunner xử lý nghiệp vụ
    U->>X: getTaskExecution(id)
    X->>DB: SELECT theo ID
    DB-->>X: Bản ghi có thể chưa có END_TIME
    X-->>U: Thông tin hiện lưu
    T->>R: Ghi nhận kết thúc / mã thoát
    R->>DB: UPDATE kết quả thực thi
    U->>X: getTaskExecution(id) lần nữa
    X->>DB: SELECT theo ID
    DB-->>X: Metadata mới đã commit
    X-->>U: Bản ghi hoàn tất
~~~

**Cần phân biệt:** `TaskRepository` không tự quyết định *bao giờ* task chạy; đó là công việc của scheduler hoặc orchestrator. `TaskExplorer` không kích hoạt lại task và cũng không tự sửa bản ghi thất bại.

## 3. TaskExecution biểu diễn điều gì?

`TaskExecution` mô tả **một lần chạy vật lý của ứng dụng task**, không phải định nghĩa công việc, cron expression hay transaction nghiệp vụ.

| Thuộc tính | Ý nghĩa | Cách đọc |
| --- | --- | --- |
| `executionId` | ID duy nhất của một lần chạy | Dùng để đối chiếu log và metadata |
| `taskName` | Tên task được xác định từ cấu hình | Nhiều lần chạy có thể trùng tên |
| `startTime` | Thời điểm framework ghi nhận bắt đầu | Có giá trị khi khởi tạo thực thi thành công |
| `endTime` | Thời điểm hoàn tất được ghi nhận | Có thể trống khi task chưa kết thúc hoặc cập nhật không kịp |
| `exitCode` | Mã kết quả ghi khi hoàn tất | Có thể `null` trong lúc chạy; không tự thay kết quả nghiệp vụ |
| `exitMessage` | Ghi chú kết quả tùy chọn | Có thể thiết lập qua task listener |
| `errorMessage` | Thông tin lỗi chưa xử lý được ghi nhận | Hỗ trợ phân tích cùng stack trace trong log |
| `arguments` | Danh sách tham số dòng lệnh | Cần hạn chế thông tin nhạy cảm |

Ví dụ hai lần khởi chạy `daily-import` cùng tham số `--businessDate=2026-11-23` vẫn có thể tạo execution ID `101` và `102`. Chúng là **hai lần chạy riêng**, dù nghiệp vụ đều xử lý một ngày. Framework ghi lịch sử thực thi; nó **không mặc nhiên chặn xử lý trùng theo business key**.

Trong thực tế còn có thể lưu **external execution ID** hoặc **parent execution ID** để liên kết với nền tảng chạy hoặc tác vụ cha. Những trường này không thay thế execution ID nội bộ.

## 4. TaskRepository: trách nhiệm ghi

Giao diện Java `org.springframework.cloud.task.repository.TaskRepository` cung cấp các thao tác **tạo** và **hoàn tất/cập nhật** TaskExecution. Trong luồng chuẩn, Spring Cloud Task gọi các thao tác này qua bộ xử lý vòng đời. Nhà phát triển thường chỉ cần cấu hình task, thực hiện nghiệp vụ và báo lỗi đúng cách.

| Khi nào | Phía ghi làm gì? | Metadata có thể quan sát |
| --- | --- | --- |
| Bắt đầu một lần chạy | Tạo TaskExecution, cấp ID, lưu tên, thời gian và tham số | `START_TIME` có; `END_TIME` chưa có |
| Runner đang xử lý | Không có nghĩa đã ghi kết quả cuối | `EXIT_CODE` còn `NULL` hoặc chưa được cập nhật |
| Runner hoàn tất | Lưu thời gian kết thúc và kết quả | `END_TIME`, `EXIT_CODE` |
| Runner lỗi | Ghi thông tin thất bại nếu vòng đời xử lý được | Mã thoát, `EXIT_MESSAGE` hoặc `ERROR_MESSAGE` |
| JVM bị kill đột ngột | Không đảm bảo callback kết thúc kịp chạy | Metadata có thể bị kẹt ở trạng thái chưa kết thúc |

### 4.1. Vì sao không ghi SQL trực tiếp để thay trạng thái?

Câu lệnh sau **chỉ minh họa một thao tác cần tránh**:

~~~sql
-- Không dùng để "sửa" kết quả của một lần chạy trong ứng dụng bình thường:
-- UPDATE TASK_EXECUTION SET EXIT_CODE = 0 WHERE TASK_EXECUTION_ID = 101;
~~~

Việc tự sửa `EXIT_CODE` không làm cho file báo cáo đã được tạo hoặc transaction nghiệp vụ được commit; còn có thể khiến `END_TIME`, `ERROR_MESSAGE` và log mâu thuẫn nhau. Khi tác vụ thất bại, hãy xử lý nguyên nhân và quyết định chạy lại theo chính sách, thay vì biến metadata thành “thành công” bằng tay.

Spring Cloud Task có tình huống nâng cao là **tạo TaskExecution trước khi hạ tầng khởi chạy ứng dụng**, rồi truyền execution ID vào process để nó cập nhật vòng đời. Chỉ dùng cơ chế này khi kiến trúc điều phối thực sự yêu cầu, với cùng một kho metadata và quy tắc cấp ID nhất quán.

### 4.2. Thêm ghi chú vòng đời qua listener

Thay vì tự gọi SQL, có thể gắn lời nhắn vào đối tượng TaskExecution qua listener đúng điểm mở rộng:

~~~java
import org.springframework.cloud.task.listener.annotation.AfterTask;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
public class AuditSummaryListener {

    @AfterTask
    public void afterTask(TaskExecution execution) {
        if (execution.getExitMessage() == null) {
            execution.setExitMessage("Task lifecycle callback finished");
        }
    }
}
~~~

Ví dụ chỉ minh họa cách thiết lập `exitMessage`; không nên hiểu câu đó là xác nhận nghiệp vụ thành công. Callback `@AfterTask` được gọi **trước khi metadata kết thúc được cập nhật**. Nếu cần xem `END_TIME` đã lưu, hãy để công cụ vận hành tra cứu sau khi task hoàn tất và repository đã commit.

## 5. TaskExplorer: trách nhiệm đọc

Giao diện `org.springframework.cloud.task.repository.TaskExplorer` cung cấp các phương thức tìm `TaskExecution` mà không cần thao tác cập nhật. Một số API tiêu biểu:

| Cần xem gì? | Phương thức |
| --- | --- |
| Bản ghi có execution ID cụ thể | `getTaskExecution(long executionId)` |
| Danh sách tên task đã thực thi | `getTaskNames()` |
| Tổng số lần chạy của tên task | `getTaskExecutionCountByTaskName(String taskName)` |
| Lần chạy mới nhất của tên task | `getLatestTaskExecutionForTaskName(String taskName)` |
| Lịch sử theo tên và phân trang | `findTaskExecutionsByName(String taskName, Pageable pageable)` |
| Toàn bộ lịch sử có phân trang | `findAll(Pageable pageable)` |
| Các bản ghi được coi là đang chạy | `findRunningTaskExecutions(String taskName, Pageable pageable)` |

Chữ ký chính xác có thể thay đổi theo phiên bản Spring Cloud Task, đặc biệt với API phân trang. Ví dụ tiếp theo dựa trên các phiên bản dùng Spring Data `Pageable`; hãy kiểm tra Javadoc đi cùng dependency của dự án trước khi biên dịch.

### 5.1. Ví dụ Java: dịch vụ đọc lịch sử

Một service quản trị hoặc integration test có bean `TaskExplorer` được cấu hình đúng database có thể dùng:

~~~java
import java.util.Optional;

import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.cloud.task.repository.TaskExplorer;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

@Service
public class TaskHistoryReader {

    private final TaskExplorer explorer;

    public TaskHistoryReader(TaskExplorer explorer) {
        this.explorer = explorer;
    }

    public Optional<TaskExecution> find(long id) {
        return Optional.ofNullable(explorer.getTaskExecution(id));
    }

    public Optional<TaskExecution> latest(String taskName) {
        return Optional.ofNullable(
                explorer.getLatestTaskExecutionForTaskName(taskName));
    }

    public Page<TaskExecution> history(String taskName, int page) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        return explorer.findTaskExecutionsByName(
                taskName, PageRequest.of(page, 20));
    }

    public long totalRuns(String taskName) {
        return explorer.getTaskExecutionCountByTaskName(taskName);
    }
}
~~~

Ví dụ sử dụng:

~~~java
TaskExecution execution = reader.find(101L)
        .orElseThrow(() -> new IllegalArgumentException(
                "Khong tim thay TaskExecution 101"));

System.out.println("Name: " + execution.getTaskName());
System.out.println("Start: " + execution.getStartTime());
System.out.println("End: " + execution.getEndTime());
System.out.println("Exit: " + execution.getExitCode());
~~~

**Cách hiểu kết quả:**

- Nếu ID không có trong kho đang đọc, `getTaskExecution` có thể trả về `null`.
- “Latest” dựa vào thứ tự bắt đầu, **không nhất thiết là lần kết thúc gần nhất**. Những task chạy chồng lấn có thể hoàn tất khác thứ tự.
- `findRunningTaskExecutions` phản ánh dữ liệu còn được coi là đang chạy **trong repository**, không chứng minh process thật vẫn tồn tại. Một task bị kill có thể để lại metadata chưa kết thúc.
- Kết quả phân trang chỉ là một snapshot tại thời điểm truy vấn. Nếu task khác vừa commit, lần đọc sau có thể khác.

Không nên tạo dashboard chạy lâu dài bằng cách khởi động một kho H2 in-memory mới rồi kỳ vọng xem được dữ liệu của các process task đã kết thúc. Phải có database bền vững dùng chung cho ứng dụng ghi và ứng dụng đọc.

## 6. Schema: cùng một kho, hai hướng truy cập

Với cấu hình JDBC và schema chuẩn, **TaskRepository ghi** còn **TaskExplorer đọc** các bảng liên quan đến thực thi. Tên bảng mặc định thường có tiền tố `TASK_`.

~~~mermaid
erDiagram
    TASK_EXECUTION ||--o{ TASK_EXECUTION_PARAMS : "parameters"
    TASK_EXECUTION ||--o{ TASK_TASK_BATCH : "batch link"
    TASK_EXECUTION {
        BIGINT TASK_EXECUTION_ID PK
        VARCHAR TASK_NAME
        TIMESTAMP START_TIME
        TIMESTAMP END_TIME
        INTEGER EXIT_CODE
        VARCHAR EXIT_MESSAGE
        VARCHAR ERROR_MESSAGE
    }
    TASK_EXECUTION_PARAMS {
        BIGINT TASK_EXECUTION_ID FK
        VARCHAR TASK_PARAM
    }
    TASK_TASK_BATCH {
        BIGINT TASK_EXECUTION_ID FK
        BIGINT JOB_EXECUTION_ID
    }
~~~

Đây là sơ đồ **khái niệm**; cột, kiểu dữ liệu, khóa/index và DDL chi tiết tùy hệ quản trị cơ sở dữ liệu và phiên bản framework.

| Bảng hoặc thành phần | Mục đích |
| --- | --- |
| `TASK_EXECUTION` | Lưu metadata cho một lần chạy |
| `TASK_EXECUTION_PARAMS` | Lưu danh sách tham số, gắn với execution ID |
| `TASK_SEQ` hoặc cơ chế cấp ID tương đương | Hỗ trợ cấp execution ID |
| `TASK_TASK_BATCH` | Liên kết task execution và Spring Batch job execution nếu có tích hợp |
| `TASK_LOCK` | Phục vụ tính năng giới hạn một instance khi được bật cùng các dependency cần thiết |

### 6.1. Truy vấn SQL để đối chiếu

Khi làm bài lab hoặc điều tra sự cố, SQL giúp kiểm tra dữ liệu nền:

~~~sql
SELECT
    TASK_EXECUTION_ID, TASK_NAME,
    START_TIME, END_TIME, EXIT_CODE,
    EXIT_MESSAGE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-import'
ORDER BY START_TIME DESC, TASK_EXECUTION_ID DESC;
~~~

Tra cứu tham số một lần chạy:

~~~sql
SELECT TASK_EXECUTION_ID, TASK_PARAM
FROM TASK_EXECUTION_PARAMS
WHERE TASK_EXECUTION_ID = 101;
~~~

Nếu có Spring Batch:

~~~sql
SELECT TASK_EXECUTION_ID, JOB_EXECUTION_ID
FROM TASK_TASK_BATCH
WHERE TASK_EXECUTION_ID = 101;
~~~

Các ID `101` và tên task là dữ liệu minh họa. Trong code ứng dụng, nên dùng `TaskExplorer` để đọc thay vì ràng buộc trực tiếp với cấu trúc SQL; SQL phù hợp khi kiểm tra schema và đối chiếu vận hành. Nếu đã thay tiền tố bảng, cần điều chỉnh tên bảng trong các truy vấn thủ công.

## 7. Cấu hình DataSource và quản lý schema

Spring Cloud Task cung cấp cấu hình mặc định qua `DefaultTaskConfigurer`, bao gồm `TaskRepository`, `TaskExplorer` và transaction manager. Khi dùng JDBC, cần đảm bảo các thành phần này truy cập **cùng một kho metadata**. Dữ liệu trong bộ nhớ có thể hữu ích cho demo, nhưng thường không còn sau khi process kết thúc.

Ví dụ YAML cho một task dùng PostgreSQL:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-import
  datasource:
    url: jdbc:postgresql://localhost:5432/task_metadata
    username: task_writer
    password: TASK_DB_PASSWORD_FROM_ENV
  cloud:
    task:
      initialize-enabled: false
~~~

Trong ví dụ, `TASK_DB_PASSWORD_FROM_ENV` là **chỗ giữ chỗ**: ứng dụng thực tế phải lấy mật khẩu từ secret/env và không commit mật khẩu vào repository code. Cần có driver JDBC và dependency Spring Cloud Task tương thích với Spring Boot.

- `spring.application.name` đặt tên ứng dụng; tên TaskExecution thực tế còn phụ thuộc `TaskNameResolver` nếu có cấu hình riêng.
- `initialize-enabled: false` tắt tự khởi tạo bảng; chỉ dùng sau khi schema đã được tạo bằng migration phù hợp. Database trống mà tắt khởi tạo sẽ gây lỗi ghi.
- `spring.cloud.task.tablePrefix` có thể đổi tiền tố bảng, nhưng **schema và cấu hình phải khớp**; không chỉ đổi thuộc tính rồi chờ framework tự sửa DDL.
- Khi có **nhiều DataSource**, cần `TaskConfigurer` phù hợp để xác định chính xác database/transaction manager dành cho metadata task. Tránh tình huống repository ghi database A còn explorer đọc database B.

### 7.1. Giao dịch metadata khác với giao dịch nghiệp vụ

Cần phân biệt:

| Phạm vi | Vai trò |
| --- | --- |
| Transaction metadata | Ghi lần chạy task và cập nhật trạng thái trong repository |
| Transaction nghiệp vụ | Ghi đơn hàng, báo cáo, file, thanh toán hoặc dữ liệu ứng dụng |
| Điều phối | Quyết định lịch, thử lại, timeout, thứ tự các tác vụ |

Các phạm vi này **không mặc nhiên cùng một giao dịch nguyên tử**. Ví dụ task ghi file lên object storage thành công, rồi JVM chết trước khi cập nhật `END_TIME`. TaskExplorer thấy bản ghi chưa kết thúc, nhưng file vẫn đã có. Nếu scheduler tự chạy lại, file có thể bị tạo hai lần.

Để đảm bảo vận hành an toàn, hãy có **business key**, cơ chế **idempotent**, chính sách retry và cách đối soát kết quả nghiệp vụ. Không dùng duy nhất `EXIT_CODE` hoặc `END_TIME` để quyết định một công việc có thể chạy lại mà không gây tác động phụ.

### 7.2. Quyền đọc và ghi thật sự

Nếu dashboard chỉ cần xem lịch sử, có thể triển khai nó thành **dịch vụ độc lập với tài khoản database chỉ đọc**, trỏ đến kho metadata thật. Ứng dụng task sử dụng tài khoản ghi phù hợp với yêu cầu cập nhật bảng. Việc có cùng thư viện `TaskExplorer` không tự biến tài khoản SQL thành tài khoản read-only.

Cần chú ý tham số CLI, exit message và error message có thể chứa dữ liệu nhạy cảm. Không đưa token, password hoặc thông tin cá nhân vào tham số rồi hiển thị nguyên văn trên dashboard; phân quyền API đọc metadata và đặt chính sách lưu giữ dữ liệu.

## 8. Dữ liệu chưa cập nhật và tình huống thất bại

Vì `TaskExplorer` chỉ đọc điều đã commit, nó có thể phản ánh **trạng thái cũ** ngay trước khi task ghi kết quả cuối. Nếu đọc từ replica, còn có thể có độ trễ sao chép.

| Kết quả đọc | Cách hiểu an toàn | Bước kiểm tra tiếp theo |
| --- | --- | --- |
| Có `START_TIME`, `END_TIME` trống | Repository chưa ghi nhận kết thúc | Kiểm tra pod/PID, log, timeout, kết nối DB |
| Có `END_TIME` và `EXIT_CODE = 0` | Framework ghi nhận hoàn tất bình thường | Kiểm tra kết quả nghiệp vụ thực |
| Có `END_TIME` và mã thoát khác 0 | Framework ghi nhận dấu hiệu lỗi | Xem stack trace, thông điệp lỗi, phần xử lý đã commit |
| `getTaskExecution(id)` không tìm thấy | Không có ID đó ở kho đang đọc | Kiểm tra ID, DataSource, schema, table prefix |
| Nhiều execution cùng tên/đầu vào | Có nhiều lần chạy | Đối chiếu scheduler, retry và chống trùng nghiệp vụ |
| Có log nhưng không có bản ghi | Có thể task chưa bootstrap thành công hoặc sai kho | Kiểm tra lỗi khởi động, schema, quyền hoặc task config |

**Lưu ý:** `END_TIME IS NULL` **không** có nghĩa chắc chắn task đang chạy. Process bị kill đột ngột có thể không kịp cập nhật repository. Các hệ thống giám sát cần kết hợp metadata và trạng thái thật của hạ tầng.

## 9. Khác biệt với JobRepository và JobExplorer của Spring Batch

Một ứng dụng Spring Cloud Task có thể chạy Spring Batch, nhưng các repository theo dõi **cấp độ khác nhau**:

| Spring Cloud Task | Spring Batch |
| --- | --- |
| `TaskRepository` ghi **lần chạy ứng dụng** | `JobRepository` ghi **job/step execution, checkpoint** |
| `TaskExplorer` đọc **TaskExecution** | `JobExplorer` đọc **JobExecution/StepExecution** |
| Tập trung khởi động, kết thúc và exit code của process | Tập trung xử lý theo bước/chunk, restart/skip/retry theo job |
| Định danh bởi `TASK_EXECUTION_ID` | Định danh job execution bằng ID riêng |

Nếu tích hợp liên kết giữa Task và Batch, `TASK_TASK_BATCH` nối `TASK_EXECUTION_ID` với `JOB_EXECUTION_ID`. Những phiên bản hỗ trợ cũng có phương thức `TaskExplorer.getJobExecutionIdsByTaskExecutionId(...)` và `getTaskExecutionIdByJobExecutionId(...)` để tra cứu.

Không dùng `TaskExplorer` để tìm checkpoint của từng chunk; đây là trách nhiệm của `JobExplorer` và `JobRepository`. Nếu job chạy bất đồng bộ mà runner trả về sớm, TaskExecution có thể kết thúc trước Batch job; ứng dụng phải thiết kế cách chờ và phản ánh kết quả chính xác.

## 10. Ví dụ thiết kế hệ thống

### Tình huống A — Dashboard hiển thị lịch sử task

Mỗi đêm Kubernetes CronJob chạy `daily-import`, ứng dụng ghi TaskExecution qua TaskRepository vào PostgreSQL. Dashboard quản trị hoạt động liên tục dùng TaskExplorer phân trang 20 lần chạy mới nhất, hiển thị kết quả và thời gian chạy.

**Cần làm:** cả hai kết nối cùng database metadata; dashboard chỉ cần quyền đọc, API có xác thực; không dùng H2 in-memory riêng cho mỗi process.

### Tình huống B — Task chết vì OOM

Process đã tạo execution ID `57`, nhưng bị hệ thống kill vì hết bộ nhớ trước khi cập nhật `END_TIME`. TaskExplorer vẫn thấy bản ghi chưa kết thúc.

**Cần làm:** đối chiếu pod bị OOMKilled, log và kết quả nghiệp vụ đã xử lý. Xác định an toàn trước khi chạy lại; không tự đánh dấu `EXIT_CODE = 0` bằng SQL.

### Tình huống C — Ba lần chạy cùng tên

Ba tiến trình `daily-import` cùng chạy gần thời điểm nhau. TaskRepository cấp execution ID riêng; TaskExplorer có thể truy vấn đúng từng ID. Việc trùng tên **không tự chống xử lý chồng lấn**.

**Cần làm:** log kèm execution ID, đặt quy tắc khóa nghiệp vụ/idempotency và chính sách chặn chạy song song nếu yêu cầu.

### Tình huống D — Spring Batch chạy trong task

Task ghi vòng đời ứng dụng, Batch ghi job/step. Nhóm vận hành tra cứu execution ID của task, tìm job execution liên quan rồi dùng JobExplorer điều tra step thất bại.

**Cần làm:** đảm bảo vòng đời task phản ánh việc hoàn tất job theo yêu cầu; phân biệt hai tầng metadata.

## 11. Bài thực hành: kiểm chứng ghi và đọc

Giả sử schema Spring Cloud Task đã được khởi tạo đúng và `daily-import` đang dùng database bền vững.

1. **Khởi chạy** với tham số nghiệp vụ `--businessDate=2026-11-23`.
2. **Tìm execution ID** qua log hoặc `getLatestTaskExecutionForTaskName("daily-import")`; lưu lại ID thật.
3. **Đọc qua TaskExplorer** bằng `getTaskExecution(id)` và kiểm tra tên, thời gian bắt đầu.
4. **Kiểm tra SQL** ở `TASK_EXECUTION` và `TASK_EXECUTION_PARAMS` theo ID đó.
5. **Sau khi process kết thúc**, đọc lại `getTaskExecution(id)`, xác nhận end time, exit code và thông tin lỗi (nếu có).
6. **Chạy lần hai cùng businessDate** và xác minh xuất hiện execution ID mới; kiểm tra tác động nghiệp vụ có bị trùng không.
7. **Thử một lỗi có kiểm soát** trong runner, đối chiếu log với TaskExplorer thay vì chỉnh database bằng tay.
8. **Thử đọc từ công cụ riêng** và xác nhận nó sử dụng đúng DataSource/schema của ứng dụng ghi.

### Checklist trước khi vận hành

- [ ] TaskRepository và TaskExplorer trỏ đến **cùng kho metadata** dự kiến.
- [ ] Schema, tiền tố bảng và version DDL tương thích framework.
- [ ] Transaction metadata ghi thành công khi bắt đầu/kết thúc.
- [ ] TaskExplorer đọc được đúng execution ID sau khi commit.
- [ ] Tài khoản ghi và tài khoản đọc có quyền database phù hợp.
- [ ] Có cảnh báo cho lần chạy quá hạn và bản ghi chưa kết thúc.
- [ ] Retry và idempotency được thiết kế ở lớp nghiệp vụ.
- [ ] Tham số và thông điệp lỗi không để lộ secret qua log/dashboard.
- [ ] Có chính sách dọn metadata, backup và chỉ mục cho khối lượng lịch sử dự kiến.
- [ ] Nếu có Spring Batch, phân biệt TaskExecution với JobExecution.

## 12. Ghi nhớ

**`TaskRepository` là cổng ghi trạng thái thực thi; `TaskExplorer` là cổng tra cứu trạng thái đã được lưu.** Tách hai trách nhiệm giúp theo dõi ứng dụng Spring Cloud Task hữu hạn một cách rõ ràng, nhưng không thay thế transaction nghiệp vụ, scheduler, log hoặc trạng thái thật của process.

Để đọc kết quả đúng, phải đặt cả hai cổng trên **cùng database/schema**, hiểu thời điểm commit và xử lý những lần chạy bị ngắt không kịp cập nhật metadata. Với Spring Batch, tiếp tục phân biệt kho task và kho job để tìm đúng cấp độ lỗi.

### Tài liệu tham khảo

- [Spring Cloud Task — Features và TaskConfigurer](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/#_task_repository_schema)
- [Spring Cloud Task — TaskExplorer API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExplorer.html)
- [Spring Cloud Task — TaskRepository source](https://github.com/spring-cloud/spring-cloud-task/blob/main/spring-cloud-task-core/src/main/java/org/springframework/cloud/task/repository/TaskRepository.java)
