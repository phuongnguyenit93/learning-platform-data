# Kiểm thử tích hợp vòng đời Task bằng Spring Boot

## 1. Vì sao cần kiểm thử cả vòng đời của Spring Cloud Task?

**Spring Cloud Task** giúp xây dựng ứng dụng Spring Boot có **thời gian chạy hữu hạn**: khởi tạo, thực hiện xử lý qua `ApplicationRunner` hoặc `CommandLineRunner`, lưu thông tin thực thi vào **TaskRepository**, rồi kết thúc. Ở môi trường thật, ứng dụng có thể được gọi thủ công, chạy theo lịch, do Kubernetes tạo Job hoặc do Spring Cloud Data Flow khởi chạy.

Một unit test gọi trực tiếp `runner.run(...)` chỉ kiểm tra logic Java trong runner. Nó **không chứng minh** rằng Spring Boot thực sự khởi động đúng, Spring Cloud Task ghi được metadata hoặc tiến trình phản ánh lỗi đúng cách. Chương **Kiểm thử** vì thế cần **integration test** đi qua vòng đời Spring Boot thực tế.

Giả sử ứng dụng `daily-reconciliation` nhận `--businessDate=2026-11-23`. Ta muốn kiểm chứng:

1. Spring khởi tạo `ApplicationContext` và các bean cần thiết.
2. `TaskRepository` tạo một `TaskExecution` **trước khi runner làm việc**.
3. Runner nhận tham số và thực hiện công việc đúng một lần trong một lần khởi động.
4. Sau khi runner hoàn tất, repository có `END_TIME` và `EXIT_CODE` phù hợp.
5. Nếu runner ném exception chưa xử lý, metadata phản ánh lỗi khi framework kịp ghi.
6. Trường hợp context bootstrap thất bại quá sớm **không bị nhầm** với một task đã bắt đầu rồi thất bại.
7. Khi chạy dưới Kubernetes Job hoặc scheduler, OS exit code và kết quả nghiệp vụ được đối chiếu thêm với metadata.

**Mục tiêu bài học:** tự xây được test tích hợp với **JUnit 5, Spring Boot Test, H2** cho đường thành công; viết kiểm thử **đường lỗi** bằng cách khởi động `SpringApplication` có kiểm soát; biết lúc nào phải chuyển sang **PostgreSQL/Testcontainers** và test tiến trình thật.

> Các ví dụ Java hướng tới **Spring Boot 3.x + Spring Cloud Task 3.x + JUnit Jupiter**, dùng API `TaskExplorer` và `TaskExecution` phổ biến của dòng này. Phải chọn BOM tương thích với phiên bản dự án. Bài có mã tự chứa để minh họa quy trình, nhưng chưa thay cho việc chạy test trên dependency thật của bạn.

## 2. Hiểu đúng thứ tự lifecycle trước khi viết assert

Theo Spring Cloud Task, metadata được tạo sau khi context bootstrap thành công và **trước các Spring Boot runner**. Khi các runner hoàn tất bình thường, framework cập nhật bản ghi thực thi; khi có `ApplicationFailedEvent` ở đường được hỗ trợ, framework cũng cố gắng ghi kết quả lỗi.

~~~mermaid
sequenceDiagram
    participant Test as Integration test
    participant Boot as SpringApplication
    participant Task as Spring Cloud Task
    participant DB as TaskRepository (JDBC)
    participant Runner as ApplicationRunner

    Test->>Boot: @SpringBootTest tải ApplicationContext
    Boot->>Task: Khởi tạo bean và lifecycle
    Task->>DB: INSERT TaskExecution / START_TIME
    Boot->>Runner: run(ApplicationArguments)
    Runner->>DB: Kiểm tra execution đang chạy
    Runner-->>Boot: Hoàn tất
    Boot->>Task: ApplicationReadyEvent
    Task->>DB: UPDATE END_TIME / EXIT_CODE
    Boot-->>Test: Context sẵn sàng, chạy @Test
    Test->>DB: TaskExplorer đọc kết quả cuối
~~~

| Mốc | Dấu hiệu có thể xác nhận | Điều cần tránh suy đoán |
| --- | --- | --- |
| Context bootstrap xong | Bean `TaskExplorer`, `TaskRepository` tồn tại | Tất cả nghiệp vụ đã chạy |
| Trước runner | `START_TIME` có, `END_TIME`/`EXIT_CODE` thường `null` | Process chắc chắn đã xong |
| Runner đang làm việc | Có thể truy vấn bản ghi đang chạy | TaskRepository tự lưu tiến độ từng item |
| Sau runner thành công | `END_TIME` có và exit code bình thường là `0` | Hệ thống ngoài đã nhận mọi side effect |
| Runner lỗi chưa xử lý | `SpringApplication.run(...)` thất bại, framework cố ghi lỗi | Mọi loại lỗi đều bảo đảm có TaskExecution |
| JVM bị kill hoặc lỗi bootstrap rất sớm | Có thể không có bản ghi cuối hoặc không có bản ghi nào | `END_TIME IS NULL` đồng nghĩa process còn sống |

**Hai trường hợp phải tách rõ:**

- **Runner thất bại sau khi TaskExecution được tạo:** có cơ sở để kiểm tra `ERROR_MESSAGE`, exit code và end time.
- **Ứng dụng thất bại trước khi context bootstrap đủ xa:** Spring Cloud Task **không bảo đảm** tạo được TaskExecution. Test không được kỳ vọng mọi lỗi khởi động đều có một hàng trong `TASK_EXECUTION`.

### Sơ đồ chiến lược kiểm thử

~~~mermaid
flowchart TD
    A["Logic chuyển đổi / kiểm tra tham số"] --> B["Unit test runner/service"]
    C["Spring Boot context + Task lifecycle"] --> D["@SpringBootTest + H2"]
    E["Runner ném exception"] --> F["SpringApplication.run riêng + JDBC readback"]
    G["DDL/quyền/dialect DB thật"] --> H["PostgreSQL/Testcontainers"]
    I["Exit code / SIGTERM / container"] --> J["Chạy jar trong process hoặc Kubernetes Job"]
    B --> K["Bộ kiểm thử có phân tầng"]
    D --> K
    F --> K
    H --> K
    J --> K
~~~

## 3. Những gì cần kiểm tra trong TaskExecution

`TaskExplorer` cung cấp API truy vấn lịch sử thực thi; nó thích hợp cho integration test vì kiểm tra đường **ghi và đọc** trong một kho metadata thực tế thay vì giả lập repository.

| Thuộc tính | Kiểm chứng gì? |
| --- | --- |
| `getExecutionId()` | ID được cấp và dùng để tương quan log |
| `getTaskName()` | Task đã nhận đúng tên từ cấu hình |
| `getStartTime()` | Repository đã ghi nhận bắt đầu |
| `getEndTime()` | Giai đoạn kết thúc đã được cập nhật |
| `getExitCode()` | Kết quả do framework ghi, thường `0` nếu runner thành công |
| `getErrorMessage()` | Dữ liệu lỗi khi framework xử lý được `ApplicationFailedEvent` |
| `getArguments()` | Các đối số launch được lưu theo phiên bản và cấu hình |
| `getExitMessage()` | Thông điệp bổ sung từ cơ chế listener, nếu có |

Không hardcode `executionId=1` trong assert: trình tự cấp ID phụ thuộc database, những lần test trước và các process khác. Khi test đơn lẻ dùng database riêng, có thể tìm lần chạy mới nhất bằng `TaskExplorer.getLatestTaskExecutionForTaskName("...")` hoặc ghi lại ID thực tế trong runner.

**Đọc lại sau khi SpringApplication hoàn tất** là thời điểm phù hợp để kỳ vọng `END_TIME` đã được lưu. Ngược lại, nếu gọi `TaskExplorer` **trong runner hoặc trong `onTaskEnd`**, cập nhật metadata cuối có thể chưa diễn ra.

## 4. Dependency cho môi trường kiểm thử

Ví dụ Maven, version của Boot/Cloud được quản lý bằng BOM **tương thích** của dự án:

~~~xml
<dependencies>
    <!-- Ứng dụng task hữu hạn -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>

    <!-- JDBC metadata và dữ liệu kiểm thử -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <!-- Test: JUnit Jupiter, AssertJ, Spring Boot Test -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- DB nhúng cho integration test đơn giản -->
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong production, nếu sử dụng PostgreSQL, cần thêm driver PostgreSQL phù hợp ở runtime. **H2 giúp chạy test nhanh, không chứng minh mọi câu SQL, transaction, kiểu dữ liệu hoặc quyền của PostgreSQL production đều tương thích.**

### Chọn một kho metadata được cô lập

Mỗi nhóm test nên có database riêng, ví dụ:

~~~properties
spring.datasource.url=jdbc:h2:mem:task_lifecycle_success;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.cloud.task.initialize-enabled=true
spring.cloud.task.closecontextEnabled=false
spring.cloud.task.name=it-lifecycle-success
spring.main.web-application-type=none
~~~

**Vì sao chọn các giá trị này?**

- `jdbc:h2:mem:task_lifecycle_success` tạo database nhúng **có tên**, tách khỏi database của các test khác.
- `DB_CLOSE_DELAY=-1` giữ database H2 còn trong **cùng JVM kiểm thử** ngay cả khi connection cuối đóng. Phù hợp để test lỗi đọc lại repository sau khi context bị đóng; không dùng như kho bền vững production.
- `initialize-enabled=true` cho phép Spring Cloud Task khởi tạo schema TaskRepository của môi trường lab.
- `closecontextEnabled=false` giữ context mở để JUnit và Spring Test có thể truy cập các bean sau khi runner kết thúc.
- `task.name` đặt tên nhận diện một lần chạy trong test.
- `web-application-type=none` tránh khởi động web server không cần thiết.

**Chú ý:** nếu dự án của bạn có cấu hình tự động khác về database/migration, phải thống nhất để chỉ **một thành phần** quản lý schema. Test không được vô tình chạy trên database production do kế thừa biến môi trường thật.

## 5. Kiểm thử đường thành công bằng @SpringBootTest

`@SpringBootTest` tạo `ApplicationContext` bằng `SpringApplication`. Vì vậy nó có khả năng kích hoạt các `ApplicationRunner`/`CommandLineRunner` như lúc chạy ứng dụng thật. Dùng `webEnvironment=NONE` để thể hiện đây là task CLI, không phải web endpoint.

Trong ví dụ, một **probe bean** ghi lại sự kiện mà test cần kiểm tra. Đây là dữ liệu trong **bộ nhớ JVM test**, chỉ dùng để quan sát thứ tự callback. Metadata bền vững vẫn phải được đọc từ `TaskExplorer`.

### 5.1. Mã JUnit 5 đầy đủ

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.cloud.task.repository.TaskExplorer;
import org.springframework.context.annotation.Bean;

@SpringBootTest(
    classes = TaskLifecycleSuccessIT.TestTaskApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    args = "--businessDate=2026-11-23",
    properties = {
        "spring.cloud.task.name=it-lifecycle-success",
        "spring.cloud.task.closecontextEnabled=false",
        "spring.cloud.task.initialize-enabled=true",
        "spring.datasource.url=jdbc:h2:mem:task_lifecycle_success;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.main.web-application-type=none"
    }
)
class TaskLifecycleSuccessIT {

    @Autowired TaskExplorer taskExplorer;
    @Autowired Probe probe;

    @Test
    void completesLifecycleAndPersistsMetadata() {
        // Khi @Test chạy, SpringApplication và runner đã chạy xong.
        assertThat(probe.events)
                .containsExactly("startup", "runner", "end");
        assertThat(probe.businessDate)
                .isEqualTo("2026-11-23");

        TaskExecution execution =
                taskExplorer.getTaskExecution(probe.executionId);

        assertThat(execution).isNotNull();
        assertThat(execution.getTaskName())
                .isEqualTo("it-lifecycle-success");
        assertThat(execution.getStartTime()).isNotNull();
        assertThat(execution.getEndTime()).isNotNull();
        assertThat(execution.getExitCode()).isEqualTo(0);
        assertThat(execution.getArguments())
                .contains("--businessDate=2026-11-23");
    }

    static class Probe {
        final List<String> events =
                new CopyOnWriteArrayList<>();
        volatile long executionId;
        volatile String businessDate;
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableTask
    static class TestTaskApplication {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        TaskExecutionListener probeListener(Probe probe) {
            return new TaskExecutionListener() {

                @Override
                public void onTaskStartup(TaskExecution task) {
                    probe.events.add("startup");
                }

                @Override
                public void onTaskEnd(TaskExecution task) {
                    probe.events.add("end");
                }

                @Override
                public void onTaskFailed(
                        TaskExecution task, Throwable error) {
                    probe.events.add("failed");
                }
            };
        }

        @Bean
        ApplicationRunner sampleRunner(
                TaskExplorer explorer, Probe probe) {
            return args -> {
                // TaskExecution đã tồn tại TRƯỚC runner.
                TaskExecution running =
                        explorer.getLatestTaskExecutionForTaskName(
                                "it-lifecycle-success");

                if (running == null
                        || running.getStartTime() == null
                        || running.getEndTime() != null
                        || running.getExitCode() != null) {
                    throw new IllegalStateException(
                            "Task lifecycle not initialized");
                }

                probe.executionId = running.getExecutionId();
                probe.businessDate =
                        args.getOptionValues("businessDate").get(0);
                probe.events.add("runner");
            };
        }
    }
}
~~~

### 5.2. Điều gì đã được kiểm tra thật?

Đây không chỉ là test “contextLoads”:

- Spring Boot đã tạo context và kích hoạt hạ tầng Task qua `@EnableTask`.
- Spring Cloud Task đã có `TaskRepository` và `TaskExplorer` nối tới **H2 thật**.
- `TaskExecution` **đã được ghi trước runner**: chính runner đọc bản ghi, kiểm tra `END_TIME` và `EXIT_CODE` đang trống.
- `ApplicationRunner` đã nhận đối số `--businessDate=...` từ `@SpringBootTest(args=...)`.
- Listener đã được đăng ký và ghi nhận trình tự `startup → runner → end`.
- Sau runner, test đọc **lại execution ID đã cấp** để kiểm tra kết quả cuối đã được ghi.
- Mã thoát `0` trong trường hợp không có lỗi phản ánh kết quả framework, **không tự chứng minh mọi side effect ngoài database đều thành công**.

Trong một ứng dụng có nhiều runner, thứ tự giữa các runner cần được quản lý bằng `@Order`/`Ordered` khi có phụ thuộc; bài lab cố ý chỉ dùng **một runner** để có thứ tự dễ kiểm chứng. Không áp đặt thứ tự các runner khác nhau mà framework không đảm bảo.

### 5.3. Vì sao dùng lớp @SpringBootConfiguration riêng?

Nếu test tự động quét toàn bộ ứng dụng production, nó có thể:

- Gọi API thật hoặc gửi email từ runner production.
- Khởi chạy scheduler và worker phụ.
- Đọc secret/DB không dành cho test.
- Kích hoạt Spring Batch Job hoặc một listener có side effect ngoài ý muốn.

Cấu hình nhỏ bên trong test giữ **hạ tầng lifecycle thật** nhưng thay công việc nghiệp vụ bằng probe. Đây là một integration test có **phạm vi có kiểm soát**, không phải smoke test toàn hệ thống.

**Không nên mock `TaskRepository` hoặc `TaskExplorer` trong test này**: khi đó test không còn xác minh việc ghi và đọc schema JDBC thật. Có thể mock các **dịch vụ ngoài** mà runner gọi, nhưng vẫn để repository thật hoạt động.

## 6. Kiểm thử đường lỗi: runner ném exception

Khi runner ném exception chưa được xử lý, `SpringApplication.run(...)` sẽ ném lỗi và **`@SpringBootTest` không thể đi tới phương thức `@Test` bình thường** nếu dùng chính cấu hình thất bại đó. Vì vậy kiểm thử đường lỗi thuận tiện hơn khi **chủ động gọi `SpringApplication.run(...)`** trong một test JUnit riêng.

Ta sử dụng H2 **có tên riêng** với `DB_CLOSE_DELAY=-1`. Khi Spring Boot dọn context sau lỗi, test vẫn có thể kết nối từ bên ngoài context để kiểm tra metadata đã commit.

### 6.1. Mã JUnit 5 kiểm tra lỗi sau khi context đã khởi tạo

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

class TaskLifecycleFailureIT {

    @Test
    void runnerFailureIsRecordedAfterBootstrap() throws Exception {
        String url =
                "jdbc:h2:mem:task_lifecycle_failure;DB_CLOSE_DELAY=-1";

        // SpringApplication tạo TaskExecution rồi runner ném exception.
        assertThatThrownBy(() -> SpringApplication.run(
                FailingTaskApplication.class,
                "--spring.main.web-application-type=none",
                "--spring.cloud.task.name=it-lifecycle-failure",
                "--spring.cloud.task.initialize-enabled=true",
                "--spring.cloud.task.closecontextEnabled=false",
                "--spring.datasource.url=" + url,
                "--spring.datasource.username=sa",
                "--spring.datasource.password="
        )).hasRootCauseInstanceOf(IllegalStateException.class);

        // Context có thể đã đóng, nên dùng kết nối JDBC riêng để đọc.
        try (Connection connection =
                    DriverManager.getConnection(url, "sa", "");
             PreparedStatement query =
                    connection.prepareStatement("""
                        SELECT TASK_EXECUTION_ID, END_TIME,
                               EXIT_CODE, ERROR_MESSAGE
                        FROM TASK_EXECUTION
                        WHERE TASK_NAME = ?
                        ORDER BY TASK_EXECUTION_ID DESC
                        """)) {

            query.setString(1, "it-lifecycle-failure");

            try (ResultSet rows = query.executeQuery()) {
                assertThat(rows.next()).isTrue();
                assertThat(rows.getLong("TASK_EXECUTION_ID"))
                        .isPositive();
                assertThat(rows.getTimestamp("END_TIME"))
                        .isNotNull();
                assertThat(rows.getObject("EXIT_CODE", Integer.class))
                        .isNotNull()
                        .isNotEqualTo(0);
                assertThat(rows.getString("ERROR_MESSAGE"))
                        .contains("Simulated runner failure");
            }
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableTask
    static class FailingTaskApplication {

        @Bean
        ApplicationRunner failingRunner() {
            return args -> {
                throw new IllegalStateException(
                        "Simulated runner failure");
            };
        }
    }
}
~~~

**Giới hạn của assert trên:** test mong đợi **đường lỗi sau khi TaskExecution đã được tạo** và Spring Cloud Task cập nhật metadata qua `ApplicationFailedEvent`. Cách mã hóa exception/exit code có thể phụ thuộc `ExitCodeExceptionMapper` và phiên bản; ta khẳng định **mã khác 0**, thay vì hardcode một mã lỗi tùy chỉnh.

Nếu ứng dụng chết **trước khi có context hoạt động**, database/schema chưa có hoặc repository cũng lỗi, không nên kỳ vọng `ERROR_MESSAGE` nhất thiết xuất hiện. Khi đó cần kiểm tra exception/lỗi khởi động và log hạ tầng, không ép test tìm bản ghi không được tạo.

### 6.2. Vì sao không dùng System.exit trong test?

Gọi `System.exit(...)` trực tiếp từ JVM JUnit có thể làm **kết thúc toàn bộ bộ chạy test**, không chỉ một phương thức. Để kiểm tra OS exit code, phải khởi động task như **một process riêng** hoặc dùng framework hỗ trợ process isolation.

`SpringApplication.run(...)` trong test ở trên giúp kiểm tra **lifecycle và metadata**; nó **không tự kiểm chứng mã thoát thực tế mà shell hoặc Kubernetes nhìn thấy**. Đó là mục đích của smoke test ở phần sau.

## 7. Test thứ tự callback và trạng thái đọc được

Spring Cloud Task cung cấp `TaskExecutionListener` với:

- `onTaskStartup(TaskExecution)`: giai đoạn bắt đầu task.
- `onTaskFailed(TaskExecution, Throwable)`: khi framework xử lý lỗi chưa được bắt.
- `onTaskEnd(TaskExecution)`: giai đoạn kết thúc task trên đường lifecycle tương ứng.

Mô hình kiểm thử:

| Kịch bản | Chuỗi callback mong đợi khi lifecycle xử lý bình thường |
| --- | --- |
| Runner chạy thành công | `onTaskStartup → runner → onTaskEnd` |
| Runner ném exception | `onTaskStartup → runner lỗi → onTaskFailed → onTaskEnd` |
| Exception được runner bắt rồi bỏ qua | `onTaskStartup → runner trả về → onTaskEnd`; **không bảo đảm** có `onTaskFailed` |
| Context bootstrap thất bại quá sớm | Có thể **không có** callback TaskExecution nào |
| Process bị SIGKILL/OOM kill | Callback end và cập nhật repository cuối **không được bảo đảm** |

**Điểm tinh tế:** `onTaskEnd` thường chạy **trước khi TaskRepository commit metadata cuối**. Do đó test gọi `TaskExplorer` **bên trong onTaskEnd** rồi yêu cầu `END_TIME` đã có ngay là một assert sai thời điểm. Hãy kiểm tra thứ tự callback bằng probe hoặc log, còn kết quả cuối bằng truy vấn **sau khi SpringApplication.run trả về**.

Nếu ứng dụng có nhiều listener, một listener ném exception có thể ảnh hưởng cách các listener còn lại được gọi. Trong test vòng đời, hãy dùng listener đơn giản, không phụ thuộc mạng hay thời gian; kiểm tra xử lý lỗi listener ở một case riêng thay vì để nó làm sai test cơ bản.

### Lỗi bị nuốt làm test xanh giả

~~~java
@Bean
ApplicationRunner badRunner(ExternalService service) {
    return args -> {
        try {
            service.exportReport();
        }
        catch (Exception ex) {
            // Ghi log rồi im lặng: runner vẫn kết thúc bình thường!
        }
    };
}
~~~

Với code này, Spring Cloud Task có thể ghi exit code thành công dù `exportReport()` thất bại. Test tích hợp cần có trường hợp dịch vụ ngoài trả lỗi và xác minh **runner báo thất bại đúng cách**, chẳng hạn ném lại exception hoặc chuyển lỗi thành mã thoát theo cơ chế được hỗ trợ.

## 8. Kiểm thử ApplicationArguments và dữ liệu tham số

Một task thường nhận các tham số như ngày chạy, tenant hoặc chế độ dry-run. Kiểm thử cần xác nhận:

1. Runner đọc đúng giá trị và áp dụng quy tắc validation.
2. Cấu hình runtime không vô tình ghi đè tham số.
3. `TaskRepository` lưu danh sách đối số ở bảng metadata theo contract của phiên bản.
4. Không ghi dữ liệu nhạy cảm vào command line hoặc test report.

`@SpringBootTest(args={"--businessDate=2026-11-23"})` truyền đối số vào `SpringApplication` của test. Trong runner:

~~~java
@Bean
ApplicationRunner validatingRunner() {
    return arguments -> {
        var dates = arguments.getOptionValues("businessDate");

        if (dates == null || dates.size() != 1) {
            throw new IllegalArgumentException(
                    "Required exactly one businessDate");
        }

        java.time.LocalDate day =
                java.time.LocalDate.parse(dates.get(0));

        // Thực thi nghiệp vụ theo ngày day.
    };
}
~~~

Một kiểm tra đọc metadata theo SQL:

~~~sql
SELECT e.TASK_EXECUTION_ID, e.TASK_NAME, p.TASK_PARAM
FROM TASK_EXECUTION e
JOIN TASK_EXECUTION_PARAMS p
  ON p.TASK_EXECUTION_ID = e.TASK_EXECUTION_ID
WHERE e.TASK_NAME = 'it-lifecycle-success'
ORDER BY e.TASK_EXECUTION_ID DESC;
~~~

Đừng truyền `--password=...`, token hoặc chuỗi kết nối nhạy cảm làm tham số test: framework có thể lưu chúng vào `TASK_EXECUTION_PARAMS`. Với test tích hợp môi trường thật, sử dụng secret/env được quản lý đúng quy trình.

Nếu task đồng thời khởi chạy **Spring Batch**, cần phân biệt Spring Boot arguments với **Batch JobParameters** theo launcher/phiên bản. `TaskExecution.getArguments()` không tự chứng minh `JobParameters` đã được Batch job nhận và dùng.

## 9. Transaction, TaskRepository và kết quả nghiệp vụ

Có ba điều không nên đồng nhất:

- **Task metadata transaction**: ghi `START_TIME`, `END_TIME`, `EXIT_CODE` trong TaskRepository.
- **Business transaction**: ghi đơn hàng, kết quả báo cáo hoặc bảng tổng hợp.
- **OS/process lifecycle**: JVM và container kết thúc với một trạng thái.

Một integration test tốt xác minh **cả metadata và tác động nghiệp vụ cần thiết**. Ví dụ một task có thể hoàn tất runner mà bảng kết quả không được cập nhật đúng vì code đã nuốt exception. Ngược lại, nghiệp vụ commit thành công nhưng process bị kill trước khi cập nhật TaskRepository, khiến `END_TIME` trống.

### 9.1. Test dữ liệu nghiệp vụ trong cùng DataSource

Nếu runner ghi bảng `reconciliation_result`, tạo schema nghiệp vụ bằng migration riêng cho test trước khi task chạy, rồi sau khi task hoàn tất:

~~~sql
SELECT WORK_KEY, RESULT_COUNT, COMPLETED_AT
FROM reconciliation_result
WHERE WORK_KEY = 'tenant-a:2026-11-23';
~~~

Kết hợp với:

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME,
       START_TIME, END_TIME, EXIT_CODE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'daily-reconciliation'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Dữ liệu kiểm chứng phải có **work key** không đổi giữa retry. `TASK_EXECUTION_ID` thay đổi theo mỗi lần khởi chạy; không nên dùng nó làm định danh duy nhất để kết luận công việc cùng ngày đã hoàn tất.

### 9.2. Tránh @Transactional trên test nếu muốn thấy commit thực

Trong test Spring, `@Transactional` trên phương thức kiểm thử thường tạo một transaction được rollback cuối test. Nhưng runner đã chạy **trong giai đoạn tạo context trước khi @Test bắt đầu**; các transaction nghiệp vụ của runner không nhất thiết nằm trong transaction của phương thức test.

Vì vậy:

- **Không giả định** @Transactional của test tự rollback mọi tác động từ runner.
- Dùng database/schema độc lập cho từng test hoặc làm sạch có kiểm soát.
- Đừng chạy test trên database dùng chung của người khác.
- Muốn kiểm chứng dữ liệu đã commit, đọc bằng một transaction/kết nối phù hợp **sau khi runner hoàn tất**.
- Khi metadata và nghiệp vụ dùng hai DataSource khác nhau, không mặc định chúng cùng một transaction nguyên tử.

## 10. H2 so với PostgreSQL/Testcontainers

H2 là lựa chọn hợp lý cho bài lab xác minh vòng đời cơ bản, nhưng nó không kiểm tra đầy đủ dialect, isolation, locking, sequence hoặc quyền của PostgreSQL production.

| Loại test | Cơ sở dữ liệu | Kiểm chứng chính |
| --- | --- | --- |
| Unit test runner | Không cần DB, hoặc mock | Quy tắc nghiệp vụ/validation |
| Context integration test | H2 có tên riêng | Bean wiring, lifecycle, TaskRepository ghi/đọc |
| Integration test với DB thật | PostgreSQL qua Testcontainers hoặc DB staging | Schema DDL, SQL dialect, transaction, sequence, mapping |
| Process-level smoke test | PostgreSQL bền vững | Exit code process, closecontextEnabled, log và metadata sau JVM dừng |
| Deployment test | Kubernetes Job/CronJob trên cluster thử nghiệm | Env/Secret/ServiceAccount, timeout, retries, Pod/Job status |

### 10.1. Gợi ý dùng Testcontainers

Với **JUnit Jupiter + Testcontainers PostgreSQL**, một test có thể tạo PostgreSQL container rồi đưa JDBC URL/user/password vào Spring Boot test qua `@DynamicPropertySource`.

Ví dụ mẫu cấu hình phần datasource:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest(
    classes = TaskLifecycleSuccessIT.TestTaskApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.cloud.task.name=it-lifecycle-success",
        "spring.cloud.task.closecontextEnabled=false",
        "spring.cloud.task.initialize-enabled=true"
    }
)
class PostgresDataSourceWiringExample {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("task_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }

    @Test
    void databaseIsAvailable() {
        // Chỗ này phải thêm assert TaskExplorer/TaskExecution thực.
    }
}
~~~

**Đây là đoạn minh họa wiring, không phải một test hoàn chỉnh có thể sao chép nguyên trạng.** Cần thêm dependency Testcontainers `junit-jupiter` và `postgresql` phù hợp, cùng PostgreSQL JDBC driver; file cấu hình và package của `TaskLifecycleSuccessIT.TestTaskApplication` phải truy cập được từ test mới. Vì ví dụ **tái sử dụng runner đang tìm tên `it-lifecycle-success`**, property tên task được giữ giống runner. Trên PostgreSQL container mới, `initialize-enabled=true` cho phép Spring Cloud Task tạo bảng thử nghiệm; nếu chuyển sang `initialize-enabled=false`, phải áp dụng **schema Spring Cloud Task đúng phiên bản bằng Flyway/Liquibase/test migration** trước lúc Task lifecycle ghi metadata. Không làm điều này sẽ khiến test khởi động thất bại.

Với Spring Boot mới có `@ServiceConnection`, có thể dùng cách wiring gọn hơn khi dependency phù hợp, nhưng cần kiểm tra version và lựa chọn đúng một cơ chế cấu hình DataSource.

### 10.2. Khi nào test PostgreSQL thật là bắt buộc?

- Sử dụng `TASK_SEQ`/sequence và DDL đặc thù.
- Có nhiều process task đồng thời, single-instance locking hoặc trạng thái `TASK_LOCK`.
- TaskRepository và business DataSource khác nhau.
- Cần quyền role PostgreSQL thực tế, TLS hoặc schema/search_path.
- Cần kiểm tra transaction isolation, deadlock, retry, idempotency.
- Dự án vừa nâng version Spring Cloud Task/Boot/Batch hoặc thay schema.

Một test H2 “xanh” không đủ để cho phép migration database production mà chưa có kiểm thử tương thích.

## 11. Smoke test tiến trình thật và exit code

`@SpringBootTest` xác minh lifecycle ở cấp `SpringApplication`, nhưng không chứng minh JVM **thực sự thoát** hoặc container nhận **đúng mã lỗi**. Những vấn đề như non-daemon thread, scheduler, thread pool và `System.exit` có thể không xuất hiện đầy đủ trong test cùng JVM.

### 11.1. Chạy jar ở process riêng

Với một bản jar đã build và database staging riêng, người vận hành có thể thực hiện:

~~~bash
java -jar target/daily-reconciliation.jar --businessDate=2026-11-23
echo $?
~~~

Kết quả của `echo $?` là exit code **do shell nhìn thấy** trên Linux/macOS. Trên PowerShell, xem biến `$LASTEXITCODE` theo quy tắc shell. Với một pipeline CI, nên tự động đọc exit code từ process thay vì chỉ tìm một dòng `INFO Completed`.

Khi muốn kiểm thử việc task tự đóng context, cấu hình:

~~~properties
spring.cloud.task.closecontextEnabled=true
~~~

**Khác với test `@SpringBootTest`:** thuộc tính trên phù hợp để xác minh process hữu hạn đóng context và giải phóng tài nguyên; trong test Spring Test cùng JVM, thường giữ `false` để framework còn truy cập context.

### 11.2. Mẫu Java ProcessBuilder để tích hợp CI

Ví dụ mẫu khởi chạy một jar đã được đóng gói, giả định database test ngoài process có sẵn:

~~~java
import java.io.File;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class TaskProcessSmokeExample {

    void runJarAndCheckExitCode() throws Exception {
        ProcessBuilder builder = new ProcessBuilder(
                "java",
                "-jar",
                "target/daily-reconciliation.jar",
                "--businessDate=2026-11-23"
        );

        // Chỉ chuyển cấu hình DB test được kiểm soát.
        builder.environment().put(
                "SPRING_PROFILES_ACTIVE", "integration");
        builder.redirectErrorStream(true);
        builder.redirectOutput(
                ProcessBuilder.Redirect.to(
                        new File("target/task-smoke.log")));

        Process process = builder.start();
        boolean ended = process.waitFor(
                Duration.ofMinutes(2).toMillis(),
                TimeUnit.MILLISECONDS);

        if (!ended) {
            process.destroy();
            if (!process.waitFor(10, TimeUnit.SECONDS)) {
                process.destroyForcibly();
            }
            throw new AssertionError("Task process timed out");
        }

        assertThat(process.exitValue()).isZero();

        // Tiếp theo: query DB test theo work key/TaskExecution ID.
    }
}
~~~

Đây là **mẫu minh họa**, chưa tích hợp thành một `@Test` chạy được nguyên trạng. Cần đảm bảo thư mục `target` và jar tồn tại, có DB profile tích hợp, cơ chế làm sạch dữ liệu và cách giữ log/CI artifacts phù hợp. Test lỗi dùng jar hoặc tham số được thiết kế gây lỗi có kiểm soát và xác nhận exit code khác 0.

**Không gọi `System.exit(...)` trực tiếp từ JVM chứa JUnit.** Nếu một task đang chạy mà bị timeout/SIGKILL, `TaskRepository` có thể không kịp ghi `END_TIME`; khi đó test phải đối chiếu cả database, OS exit status và log.

## 12. Spring Batch bên trong Spring Cloud Task

Nếu ứng dụng task khởi chạy Spring Batch Job, bài kiểm thử phải phân biệt **hai vòng đời**:

| Spring Cloud Task | Spring Batch |
| --- | --- |
| `TaskExecution`: một lần khởi chạy ứng dụng | `JobExecution`: một lần thực thi Job |
| `TaskRepository` lưu start/end/exit code process | `JobRepository` lưu trạng thái Job và Step |
| `TaskExplorer` đọc metadata task | `JobExplorer` đọc JobExecution/StepExecution |
| Thành công của task không tự suy ra tất cả Step thành công | Job/Step status có quy tắc riêng |

Những assert nên có:

- TaskExecution được tạo khi context task khởi động.
- JobExecution tương ứng đã có `BatchStatus.COMPLETED` hoặc `FAILED` theo kịch bản.
- `StepExecution` có `READ_COUNT`, `WRITE_COUNT` và `SKIP_COUNT` phù hợp.
- Nếu task phải đợi Batch Job hoàn tất, runner **không trả về sớm** khi Job đang chạy bất đồng bộ.
- Batch job thất bại phải được ánh xạ đúng sang exit code của task/process theo cấu hình tích hợp (ví dụ `spring.cloud.task.batch.fail-on-job-failure` trong nhánh hỗ trợ).
- Khi restart, `ExecutionContext` của Batch và dữ liệu nghiệp vụ nhất quán, không chỉ `TaskExecution.END_TIME` có giá trị.

Để tránh khởi chạy Batch Job hai lần trong integration test, xác định rõ **một cơ chế launcher**: auto-run của Spring Boot hoặc `JobLauncher` do test/ứng dụng gọi có kiểm soát. Không đồng thời để Spring Boot tự chạy Job duy nhất và một `ApplicationRunner` khác gọi `JobLauncher.run(...)` mà không chủ đích.

## 13. Tránh test không ổn định và tác dụng phụ

### 13.1. Context caching và dữ liệu H2

Spring Test cache `ApplicationContext` giữa nhiều phương thức/class có cấu hình tương đương. Điều này có nghĩa:

- Runner thường chạy **khi context được tạo**, không phải trước **mỗi phương thức `@Test`**.
- Một phương thức test mới **không tự tạo một TaskExecution mới** khi dùng lại context đã cache.
- H2 in-memory có tên và `DB_CLOSE_DELAY=-1` có thể giữ dữ liệu trong suốt JVM test.
- Nếu dùng cùng JDBC URL cho nhiều class chạy song song, kết quả test có thể bị lẫn.

Để cô lập, dùng tên database riêng cho từng trường hợp hoặc Testcontainers/DB schema riêng; làm sạch theo chiến lược được thiết kế. Chỉ dùng `@DirtiesContext` khi thực sự cần tạo lại context và hiểu chi phí khởi tạo mới.

### 13.2. Đừng giả định kết quả có ngay trong @BeforeEach

Với `@SpringBootTest`, context và runner có thể đã được khởi tạo **trước khi `@BeforeEach` chạy**. Do vậy tạo dữ liệu nguồn từ `@BeforeEach` có thể đã **quá muộn** cho runner. Hãy nạp dữ liệu test bằng migration/`@Sql` ở thời điểm thích hợp, bean chuẩn bị dữ liệu trước runner hoặc cấu hình test chuyên biệt; kiểm tra chính xác thứ tự của các cơ chế đó.

Nếu muốn thay đổi đầu vào mỗi phương thức test, cân nhắc **gọi service trực tiếp bằng unit/service integration test**, còn kiểm thử lifecycle thực hiện qua **mỗi lần khởi chạy SpringApplication** hoặc process riêng.

### 13.3. Tránh sleep và thời gian thực trong assert

Đừng viết:

~~~java
Thread.sleep(500);
assertThat(taskExplorer.getTaskExecution(id).getEndTime())
        .isNotNull();
~~~

Cách này dễ gây test chập chờn khi CI chậm hoặc database có độ trễ. Với một task đồng bộ, hãy đợi **`SpringApplication.run` trả về** rồi mới assert metadata; với công việc bất đồng bộ, phải có **cơ chế hoàn tất có kiểm soát** như `CountDownLatch`/`CompletableFuture` hoặc chờ trạng thái với timeout và điều kiện rõ ràng.

Nếu nghiệp vụ không được phép kết thúc khi async chưa xong, runner phải **đợi kết quả thật**; chỉ làm cho test chờ lâu hơn không sửa được lỗi lifecycle của ứng dụng.

### 13.4. Không dùng hàng đợi/broker hoặc dịch vụ ngoài thật khi không cần

Một integration test của **lifecycle TaskRepository** không cần gửi email, gọi hệ thống thanh toán hay tạo Kubernetes Pod thật. Mock/fake các biên giới ngoài không thiết yếu; sử dụng **repository JDBC thật**. Khi cần test toàn tuyến, làm thêm smoke test riêng bằng hạ tầng staging và credential ít quyền.

## 14. Các kịch bản lỗi nên đưa vào test suite

| Kịch bản | Thiết lập | Điều cần xác nhận |
| --- | --- | --- |
| **Đường thành công** | Runner trả về bình thường | Có TaskExecution, start/end, exit code `0` |
| **Sai tham số** | Thiếu `--businessDate` | Runner báo lỗi; repository ghi thất bại nếu lifecycle đã bắt đầu |
| **Exception chưa xử lý** | Runner ném `IllegalStateException` | `ApplicationFailedEvent`, error metadata nếu ghi được |
| **Runner nuốt lỗi** | Cố ý bắt exception không ném lại | Xác định lỗi thiết kế: exit code có thể thành công giả |
| **Listener thất bại** | Callback throw trong môi trường test riêng | Kiểm tra đường lỗi và callback khác; không làm nhiễu happy path |
| **DB không kết nối được** | JDBC URL sai/DB dừng | Có thể không tạo được TaskExecution; kiểm tra bootstrap exception |
| **Schema chưa khởi tạo** | `initialize-enabled=false`, DB trống | Context lỗi do thiếu bảng; không ép assert end time |
| **Thiếu quyền SQL** | Role chỉ đọc, không có quyền ghi | Khởi động hoặc cập nhật metadata thất bại |
| **Process timeout/SIGTERM** | Jar chạy process riêng, deadline hữu hạn | OS exit, log và khả năng metadata dang dở |
| **Task chạy lại** | Hai lần khởi chạy cùng work key | Hai execution ID, kết quả nghiệp vụ không trùng |
| **Async chưa xong** | Runner phát async rồi trả về | Phát hiện TaskExecution kết thúc sớm; sửa bằng chờ kết quả |
| **Spring Batch Job lỗi** | Batch Step ném exception | Job/Step metadata đúng, mapping exit code task được kiểm chứng |

**Không phải mọi lỗi đều cần một test rất nặng.** Unit test phụ trách biến thể validation, integration test phụ trách lifecycle/schema, process test phụ trách JVM và deployment test phụ trách môi trường.

## 15. Quy trình CI và kiểm thử trước khi phát hành

Một chu trình kiểm thử có thể tổ chức theo thứ tự:

1. **Unit tests:** chạy nhanh, không phụ thuộc DB hoặc hạ tầng.
2. **Task lifecycle integration tests:** dùng H2, kiểm tra context, runner, listener, TaskRepository/TaskExplorer.
3. **Database compatibility tests:** dùng PostgreSQL/Testcontainers với schema migration thật, kiểm tra DB role/quyền khi phù hợp.
4. **Process smoke tests:** chạy jar riêng, xác minh mã thoát, timeout và `closecontextEnabled`.
5. **Staging deployment tests:** chạy Kubernetes Job/Scheduler/SCDF trên môi trường kiểm thử, đối chiếu metadata, log và kết quả nghiệp vụ.
6. **Release checks:** xác nhận image/binary version, cấu hình secret, migration và đường rollback.

~~~mermaid
flowchart LR
    U["Unit tests"] --> I["@SpringBootTest + H2"]
    I --> D["PostgreSQL / Testcontainers"]
    D --> P["Process smoke test"]
    P --> K["Kubernetes / Scheduler staging"]
    K --> R{"Đủ điều kiện phát hành?"}
    R -->|Có| Y["Release có giám sát"]
    R -->|Không| N["Sửa lỗi + chạy lại"]
~~~

### Checklist chất lượng

- [ ] Dùng JUnit 5 và `@SpringBootTest(webEnvironment=NONE)` cho kiểm thử context task.
- [ ] Có `@EnableTask` hoặc cấu hình Task lifecycle tương ứng với version thực.
- [ ] Dùng `TaskRepository` JDBC thật, không mock repository trong lifecycle integration test.
- [ ] Tạo database/schema **cô lập**, không động tới database production.
- [ ] `closecontextEnabled=false` trong test cần giữ ApplicationContext mở.
- [ ] Runner đã kiểm tra TaskExecution tồn tại trước khi xử lý.
- [ ] Sau runner, có `END_TIME`, `EXIT_CODE` và `TASK_NAME` phù hợp.
- [ ] Có trường hợp runner ném exception và đọc lại metadata qua kết nối độc lập.
- [ ] Đã xác nhận lỗi bootstrap sớm có thể không có TaskExecution.
- [ ] Test có assert về **kết quả nghiệp vụ**, không chỉ metadata.
- [ ] Không dùng `Thread.sleep` như cơ chế đồng bộ chính.
- [ ] Context caching và dữ liệu H2 không làm các test ảnh hưởng lẫn nhau.
- [ ] Có test PostgreSQL schema/transaction và quyền khi dùng database production khác H2.
- [ ] Có process-level test cho exit code và dọn thread/context.
- [ ] Nếu tích hợp Spring Batch, đã kiểm tra cả JobRepository/JobExplorer và TaskRepository/TaskExplorer.
- [ ] Có kịch bản retry với work key/idempotency để tránh xử lý trùng.
- [ ] Không làm rò rỉ secret qua arguments, log, JDBC URL hoặc test report.

## 16. Tổng kết

**Kiểm thử tích hợp vòng đời Task bằng Spring Boot** cần chạy qua `SpringApplication` và **TaskRepository thật**, thay vì chỉ gọi một phương thức runner trong unit test. Với đường thành công, `@SpringBootTest` cho phép quan sát Spring Cloud Task **ghi bắt đầu trước runner**, sau đó cập nhật metadata khi runner kết thúc. Với đường lỗi, có thể khởi động `SpringApplication.run(...)` có kiểm soát rồi đọc H2 qua kết nối độc lập để xác minh trạng thái thất bại.

Ba phạm vi kiểm thử phải được phân biệt rõ: **lifecycle trong ApplicationContext**, **metadata/kết quả nghiệp vụ đã commit** và **mã thoát tiến trình thật**. H2 giúp test nhanh; PostgreSQL/Testcontainers kiểm tra schema và transaction; process/Kubernetes smoke test xác minh shutdown, timeout và exit code. Khi có Spring Batch, tiếp tục kiểm tra riêng `JobExecution`/`StepExecution`.

Một bộ test đáng tin cậy chỉ báo thành công khi **vòng đời được ghi đúng, kết quả nghiệp vụ được xác nhận, lỗi được phản ánh rõ và việc chạy lại không tạo tác động trùng**.

### Tài liệu tham khảo

- [Spring Cloud Task — Features: Task lifecycle, TaskExecution và closing context](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Getting started và TaskRepository với H2](https://docs.spring.io/spring-cloud-task/reference/getting-started.html)
- [Spring Cloud Task — TaskExplorer API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/TaskExplorer.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — ApplicationRunner / CommandLineRunner](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Batch — JobRepository, JobExplorer và restart](https://docs.spring.io/spring-batch/reference/domain.html)
