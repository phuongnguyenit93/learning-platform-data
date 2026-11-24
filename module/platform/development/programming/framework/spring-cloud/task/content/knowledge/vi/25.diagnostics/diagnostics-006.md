# Job Batch thất bại nhưng mã thoát Task vẫn thành công

## 1. Hiện tượng và tác động vận hành

**Spring Cloud Task** là nền tảng xây dựng ứng dụng Spring Boot chạy **hữu hạn**: khởi động, nhận tham số, xử lý nghiệp vụ, ghi nhận một `TaskExecution` trong **TaskRepository**, rồi kết thúc. Nhiều tác vụ như nhập CSV, đối soát, xuất báo cáo lại sử dụng **Spring Batch Job** bên trong, với `JobRepository` theo dõi job, step và các điểm restart.

Một vấn đề vận hành dễ gây hiểu lầm:

~~~text
ERROR ... Encountered an error executing step importStep
java.lang.IllegalStateException: Simulated data processing failure
...
INFO  ... Job reconciliationJob completed with status FAILED
...
INFO  ... Task batch-exit-diagnostic completed with exit code 0
~~~

Log của Spring Batch nói **`FAILED`**, nhưng hệ thống chạy task theo lịch/Kubernetes có thể thấy **mã thành công `0`**. Khi đó giám sát không cảnh báo, scheduler không retry và người vận hành dễ bỏ sót việc chỉ xử lý được một phần dữ liệu.

Điều này **không mặc nhiên là lỗi của Kubernetes hay TaskRepository**. Theo tài liệu Spring Cloud Task, mặc định Spring Boot/Batch có thể ghi JobExecution `FAILED` mà **không chuyển kết quả đó thành lỗi của ứng dụng Spring Boot**. Spring Cloud Task cung cấp thuộc tính:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

để cho phép **Batch Job có `BatchStatus.FAILED` làm Task trả mã khác 0** trong đường tích hợp được hỗ trợ.

Bài thuộc chương **Chẩn đoán** hướng dẫn nhận biết nguyên nhân, phân biệt status giữa Batch/Task/JVM, cấu hình xử lý lỗi, tái hiện bằng Job một Step, đọc lại database và kiểm chứng kết quả ở scheduler hoặc Kubernetes.

### Mục tiêu

Sau khi học, bạn có thể:

1. Phân biệt `BatchStatus`, `ExitStatus`, `TaskExecution.EXIT_CODE` và **OS exit code**.
2. Giải thích vì sao một `JobExecution.FAILED` không nhất thiết tạo exception chưa xử lý ở `SpringApplication`.
3. Bật và kiểm chứng `spring.cloud.task.batch.fail-on-job-failure` trên phiên bản hỗ trợ.
4. Phát hiện custom runner, asynchronous JobLauncher hoặc Batch flow làm sai kết luận.
5. Truy vấn `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `TASK_EXECUTION` và bảng liên kết khi có.
6. Thiết kế test và runbook để hệ thống điều phối không ghi nhận **thành công giả**.

## 2. Ba lớp kết quả không được đánh đồng

| Lớp | Đại diện | Ví dụ trạng thái | Người sử dụng |
| --- | --- | --- | --- |
| **Spring Batch** | `JobExecution`, `StepExecution` trong JobRepository | `BatchStatus.FAILED`, `ExitStatus.FAILED` | Batch runtime, JobExplorer, cơ chế restart |
| **Spring Cloud Task** | `TaskExecution` trong TaskRepository | `EXIT_CODE=0` hoặc `1` | TaskExplorer, Data Flow dashboard, giám sát Task |
| **JVM và hạ tầng** | Mã process, `terminated.exitCode`, `Job condition` | `0`/khác `0`, `Complete`/`Failed` | Shell, CI, Kubernetes, scheduler |
| **Nghiệp vụ** | Số kết quả đã commit, file, thông điệp, đối soát | Đủ/thiếu/trùng dữ liệu | Người dùng và hệ thống đích |

Ngay cả khi **tất cả các mã kỹ thuật đều bằng 0**, kết quả nghiệp vụ vẫn có thể không đúng nếu runner nuốt lỗi hoặc Batch skip quá nhiều bản ghi. Ngược lại, một Job `FAILED` có thể đã commit 90% dữ liệu theo chunk; **không** được mặc định toàn bộ dữ liệu nghiệp vụ đã rollback.

### Ma trận minh họa

| Tình huống | Batch Job | TaskExecution | Process/Pod |
| --- | --- | --- | --- |
| Xử lý thành công | `COMPLETED` | Thường `0` | Thường `0` |
| Batch lỗi, dùng hành vi mặc định | `FAILED` | **Có thể `0`** | **Có thể `0`** |
| Batch lỗi, fail-on hoạt động | `FAILED` | Mong đợi khác `0` | Cần kiểm chứng trên jar thực tế |
| Lỗi bootstrap trước khi tạo TaskExecution | Có thể chưa tạo Job | Có thể chưa tạo Task | Thường báo lỗi |
| JVM bị `SIGKILL` hoặc OOMKilled | Metadata có thể dang dở | `END_TIME` có thể trống | Container thất bại theo hạ tầng |
| Một Step lỗi nhưng flow cố ý `end()` | Step `FAILED`, Job có thể `COMPLETED` | Có thể `0` | Có thể `0` |

**Quy tắc chẩn đoán:** trước khi sửa cấu hình, hỏi rõ “thành công” đang được nhìn từ **Batch Job**, **TaskRepository**, **process exit** hay **kết quả nghiệp vụ**.

## 3. Vì sao lỗi trong Step không luôn làm Spring Boot thất bại?

Spring Batch quản lý việc thực thi Job. Khi Step ném một exception, framework thường lưu lỗi đó vào `StepExecution` và cập nhật `JobExecution` thành `FAILED`. Tùy đường khởi chạy, `JobLauncher.run(...)` **có thể trả về một `JobExecution` thất bại** thay vì ném lại exception nghiệp vụ ra ngoài runner.

Spring Cloud Task lại ghi metadata trên **vòng đời Spring Boot**. Nếu runner đã trở về bình thường và không có cơ chế ánh xạ lỗi Batch, Task có thể coi ứng dụng hoàn tất:

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant B as Spring Boot
    participant T as TaskRepository
    participant L as Batch JobLauncher
    participant J as JobRepository

    S->>B: Khởi chạy task
    B->>T: Tạo TaskExecution
    B->>L: Khởi chạy reconciliationJob
    L->>J: Ghi JobExecution STARTED
    L->>L: Step ném exception
    L->>J: Ghi StepExecution/JobExecution FAILED
    L-->>B: Runner hoàn tất theo đường mặc định
    B->>T: Ghi TaskExecution EXIT_CODE=0
    B-->>S: Process có thể trả mã 0
~~~

**Đường lỗi Batch không giống đường lỗi Runner.** Nếu `ApplicationRunner` tự ném một exception chưa xử lý, Spring Boot có thể phát `ApplicationFailedEvent` để Cloud Task ghi lỗi Task. Nhưng Batch có thể đã xử lý exception ở bên trong Job và chỉ thể hiện kết quả trên `JobExecution`.

Vì vậy:

- Dòng log `ERROR` không tự quyết định mã thoát.
- `BatchStatus.FAILED` không tự biến thành exception Java ném từ `SpringApplication.run(...)`.
- `TaskBatchExecutionListener` giúp **liên kết Task và Batch** nhưng không đồng nghĩa mặc định đã bật lan truyền mã lỗi.
- Scheduler chỉ thấy process exit status không thể suy ra tất cả trạng thái Batch trong database.

## 4. BatchStatus, ExitStatus và mã thoát OS

| Giá trị | Kiểu | Ví dụ | Nguồn |
| --- | --- | --- | --- |
| `JobExecution.getStatus()` | Enum `BatchStatus` | `FAILED`, `COMPLETED`, `STOPPED` | Spring Batch |
| `JobExecution.getExitStatus()` | Value object `ExitStatus` | `"FAILED"`, `"COMPLETED"` hoặc tùy chỉnh | Spring Batch |
| `TaskExecution.getExitCode()` | Số nguyên | `0`, `1` | Spring Cloud Task |
| **Process exit code** | Số nguyên | `0`, `1`, mã do OS/platform ghi | JVM/shell/Kubernetes |

`BatchStatus` phản ánh trạng thái xử lý trong Batch. `ExitStatus` có **mã exit dạng chuỗi** và tham gia điều kiện luồng của Job. **Hai giá trị này có thể khác nhau do Job flow tùy chỉnh.**

Ví dụ Job có một Step thất bại nhưng được cấu hình kết thúc luồng bằng `end()`:

~~~java
// Đoạn ghép flow minh họa, không phải lớp cấu hình đầy đủ.
.start(stepA)
.next(stepB)
.on("FAILED").end()
.from(stepB).on("*").to(stepC)
.end()
~~~

Trong nhánh đó, Step B lỗi nhưng **Job có thể `COMPLETED` có chủ đích**. Thuộc tính `fail-on-job-failure` nhắm tới `BatchStatus.FAILED` ở **Job**, nên nếu nghiệp vụ bắt buộc coi Step B là thất bại của toàn job, phải sửa **transition semantics** (ví dụ `fail()` theo API Batch), không chỉ thay property Task.

### Những trạng thái cần chính sách riêng

- `STOPPED`: job bị dừng; có thể phải báo cần can thiệp, không tự mặc định là `FAILED`.
- `UNKNOWN`: chưa xác định, không thể coi là thành công.
- `COMPLETED` với skip count lớn: thành công theo policy skip nhưng chưa chắc đạt SLA nghiệp vụ.
- `FAILED`: job thất bại, cần xác nhận phần dữ liệu đã được commit và có thể restart thế nào.

## 5. Thuộc tính chính thức: fail-on-job-failure

Cấu hình YAML:

~~~yaml
spring:
  cloud:
    task:
      name: batch-exit-diagnostic
      batch:
        fail-on-job-failure: true
~~~

Tương đương:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

Theo Spring Cloud Task Reference và danh mục Configuration Properties:

| Property | Mặc định được công bố | Công dụng |
| --- | --- | --- |
| `spring.cloud.task.batch.fail-on-job-failure` | `false` | Job `FAILED` làm Task trả mã khác 0 khi đường tích hợp hỗ trợ |
| `spring.cloud.task.batch.fail-on-job-failure-poll-interval` | `5000` ms | Chu kỳ kiểm tra JobExecution đã hoàn tất khi bật fail-on-job-failure |
| `spring.cloud.task.batch.listener.enabled` | `true` | Bật listener tích hợp liên kết TaskExecution với Batch JobExecution |

Khi property `fail-on-job-failure=true` hoạt động, mã lỗi Task **thường là `1`** theo tài liệu; `ExitCodeGenerator` tùy chỉnh có thể ảnh hưởng kết quả. **Không hardcode kỳ vọng mọi loại lỗi đều có mã đúng bằng 1** nếu ứng dụng có exception mapping hoặc runner tùy chỉnh.

### Điểm khác nhau giữa các đời Spring Cloud Task

Tài liệu Spring Cloud Task hiện hành mô tả cơ chế này bằng một **`ApplicationRunner` tích hợp**, có thể điều chỉnh thứ tự bởi `spring.cloud.task.batch.applicationRunnerOrder`. Một số tài liệu cũ mô tả `CommandLineRunner` và `commandLineRunnerOrder`.

Không sao chép tên class/runner property từ một phiên bản cũ sang Boot 3/Cloud Task 3 hoặc Boot 4 mà chưa kiểm tra BOM và source phiên bản thực. Bài này dùng **nhánh API phổ biến Spring Boot 3.x + Spring Batch 5.x + Spring Cloud Task 3.x** làm ví dụ học tập.

**Polling interval không phải timeout tổng thể.** Nó không tự đảm bảo hủy một worker bị treo hoặc dừng Kubernetes Pod. Nếu Batch chạy bất đồng bộ, cần timeout và quy tắc đợi Job kết thúc ở cấp ứng dụng/hạ tầng.

## 6. Điều kiện tích hợp: dependency và cách launch Job

Để dùng Spring Batch trong ứng dụng Cloud Task, ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-task-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Đoạn trên **không phải một `pom.xml` hoàn chỉnh**; version Boot và Spring Cloud release train phải được quản lý bằng BOM tương thích.

`spring-cloud-task-batch` cung cấp tích hợp Task–Batch, bao gồm `TaskBatchExecutionListener` được tự cấu hình khi đủ điều kiện (có bean kiểu `Job` và module tích hợp). Listener cho phép truy vết một `JobExecution` về `TaskExecution` tương ứng khi schema/phiên bản hỗ trợ.

Nhưng **có listener không đồng nghĩa exit mapping đang bật**. Cần xác minh thêm:

1. `spring.cloud.task.batch.fail-on-job-failure` được nạp thật trong process.
2. Job đang được chạy **qua Batch runner của Boot/Task** được tính năng hỗ trợ.
3. Ứng dụng không có một runner khác tự gọi `JobLauncher` làm Job chạy thêm hoặc bypass cơ chế mapping.
4. Job có **`BatchStatus.FAILED` ở cấp Job** khi lỗi xảy ra.
5. Process không có đoạn `System.exit(0)` hoặc script wrapper luôn trả 0.

### Tránh chạy Job hai lần

Nếu để Boot/Task tự launch Job, cần giữ cơ chế auto-run hoạt động:

~~~yaml
spring:
  batch:
    job:
      enabled: true
~~~

Nếu bạn **tự tạo ApplicationRunner** gọi `JobLauncher.run(...)`, phải chủ động quyết định tắt auto-run:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

**Chỉ một cơ chế launch chính** cho một Batch Job. Vừa auto-run vừa custom-run một Job có thể gây hai JobExecution hoặc lỗi JobInstance đã hoàn tất.

## 7. Ví dụ tái hiện: Job một Step thất bại

Để tập trung vào hiện tượng, ví dụ có **một Job và một Step**, không có flow tùy chỉnh, chạy bằng cơ chế Boot/Task auto-run.

### 7.1. Ứng dụng Spring Boot

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;

@SpringBootApplication
@EnableTask
public class BatchExitDiagnosticApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                BatchExitDiagnosticApplication.class, args);
    }
}
~~~

Không tạo một `ApplicationRunner` tự launch Job trong ví dụ này.

### 7.2. Job và Step với lỗi có thể bật/tắt

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ReconciliationJobConfiguration {

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Value("${demo.fail:false}") boolean fail) {

        return new StepBuilder("importStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    if (fail) {
                        throw new IllegalStateException(
                                "Simulated data processing failure");
                    }

                    // Demo: không có side effect ngoài database.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Job reconciliationJob(
            JobRepository jobRepository, Step importStep) {

        return new JobBuilder("reconciliationJob", jobRepository)
                .start(importStep)
                .build();
    }
}
~~~

`demo.fail` là **property của bài demo**, không phải property của Spring Cloud Task. Khi truyền `--demo.fail=true`, Step ném exception; trong flow Job một Step mặc định, Spring Batch sẽ ghi JobExecution `FAILED` theo đường xử lý tương ứng.

### 7.3. application.yml cho PostgreSQL lab

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:postgresql://localhost:5432/task_batch_metadata
    username: task_runtime
    # Password lấy từ environment/secret an toàn.
  cloud:
    task:
      name: batch-exit-diagnostic
      initialize-enabled: false
      batch:
        fail-on-job-failure: false
  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: never
~~~

**Tiền điều kiện:** đã tạo `TASK_*` và `BATCH_*` theo đúng phiên bản Spring Cloud Task/Spring Batch bằng migration, driver PostgreSQL có trong artifact, tài khoản có quyền đọc/ghi schema và database này **không chứa dữ liệu production**.

Có thể thực hành với H2 in-memory bằng schema initialization phù hợp, nhưng H2 sẽ mất dữ liệu sau khi JVM thoát. Muốn thực hiện các truy vấn SQL hậu kỳ từ một process khác, hãy dùng PostgreSQL lab hoặc database bền vững tương ứng.

## 8. Thực hành A: quan sát thành công giả

Chạy với `fail-on-job-failure=false`:

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=true \
  --spring.cloud.task.batch.fail-on-job-failure=false
~~~

Log **minh họa**, không phải chuỗi cố định:

~~~text
ERROR ... importStep ... Simulated data processing failure
INFO  ... reconciliationJob ... status: FAILED
INFO  ... batch-exit-diagnostic ... task exit code: 0
~~~

**Kỳ vọng cần xác minh:** `BATCH_JOB_EXECUTION.STATUS='FAILED'` nhưng `TASK_EXECUTION.EXIT_CODE=0` có thể xuất hiện. Trên đường mặc định, process cũng có thể trả `0`.

Linux/macOS:

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=true \
  --spring.cloud.task.batch.fail-on-job-failure=false
echo $?
~~~

PowerShell:

~~~powershell
java -jar batch-exit-diagnostic.jar --demo.fail=true --spring.cloud.task.batch.fail-on-job-failure=false
$LASTEXITCODE
~~~

**Không** dùng log có từ khóa `ERROR` như bằng chứng process exit khác 0. Cũng không so sánh `TaskExecution` từ một lần chạy với `JobExecution` của lần chạy khác.

Khi chạy lại, Spring Batch xác định `JobInstance` dựa trên **job name và identifying JobParameters**. Dùng tham số/nguồn được quản lý rõ cho từng thử nghiệm để tránh gặp lỗi restart hoặc JobInstance đã `COMPLETED` không thể chạy lại.

## 9. Thực hành B: bật lan truyền lỗi Batch → Task

Chạy tiếp trên metadata DB lab:

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=true \
  --spring.cloud.task.batch.fail-on-job-failure=true
~~~

Hoặc cấu hình:

~~~yaml
spring:
  cloud:
    task:
      batch:
        fail-on-job-failure: true
~~~

Trong đường tích hợp được hỗ trợ, Job `FAILED` **phải khiến kết quả Task được đánh dấu lỗi với mã khác 0**, thường là `1`. Hãy kiểm tra cả **OS exit code** vì scheduler/Kubernetes dựa vào process, không query JobRepository thay ứng dụng.

Khi áp dụng property trong production:

- Đừng assume lỗi Job luôn tạo `TASK_EXECUTION.ERROR_MESSAGE`: exception có thể đã được Batch xử lý và lưu ở `BATCH_STEP_EXECUTION.EXIT_MESSAGE`.
- Đừng đo trên YAML trong jar mà bỏ qua profile/CLI/environment thực tế. Property có thể bị override.
- Đừng thêm `System.exit(0)` để ép tắt JVM: nó che dấu lỗi.
- Đừng tự sửa cột `TASK_EXECUTION.EXIT_CODE` để “làm cho dashboard đỏ”; cần sửa nguyên nhân.

### Chạy cả đường thành công

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=false \
  --spring.cloud.task.batch.fail-on-job-failure=true
~~~

Với JobInstance phù hợp, kỳ vọng Job `COMPLETED` và Task `0`. Test này bảo đảm thay đổi không biến mọi task thành thất bại giả.

## 10. Truy vấn SQL: sự thật ở hai repository

### 10.1. Batch Job nào thất bại?

~~~sql
SELECT
    JOB_EXECUTION_ID, JOB_INSTANCE_ID,
    STATUS, EXIT_CODE, EXIT_MESSAGE,
    START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

Ví dụ:

| JOB_EXECUTION_ID | STATUS | EXIT_CODE |
| ---: | --- | --- |
| 3102 | FAILED | FAILED |
| 3101 | COMPLETED | COMPLETED |

`EXIT_CODE` của Batch là **chuỗi** từ `ExitStatus`.

### 10.2. Step nào gây lỗi?

~~~sql
SELECT
    STEP_EXECUTION_ID, JOB_EXECUTION_ID,
    STEP_NAME, STATUS, EXIT_CODE, EXIT_MESSAGE,
    READ_COUNT, WRITE_COUNT, ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = 3102
ORDER BY STEP_EXECUTION_ID;
~~~

Nhìn vào `ROLLBACK_COUNT`, `READ_COUNT`, `WRITE_COUNT` và lỗi Step. Một số Step đã `COMPLETED` có thể đã commit dữ liệu trước khi Step khác làm Job thất bại.

### 10.3. Task đã ghi mã gì?

~~~sql
SELECT
    TASK_EXECUTION_ID, TASK_NAME,
    START_TIME, END_TIME,
    EXIT_CODE, EXIT_MESSAGE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'batch-exit-diagnostic'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Với trường hợp báo thành công giả, có thể thấy:

| TASK_EXECUTION_ID | TASK_NAME | EXIT_CODE | END_TIME |
| ---: | --- | ---: | --- |
| 5802 | batch-exit-diagnostic | 0 | Có |

Không mặc định `ERROR_MESSAGE` khác null khi Batch Job lỗi: Task có thể không nhận một `ApplicationFailedEvent` chứa exception Batch.

### 10.4. Liên kết chính thức TaskExecution và JobExecution

Nếu ứng dụng dùng `spring-cloud-task-batch` với liên kết được hỗ trợ, bảng `TASK_TASK_BATCH` thường chứa cặp ID:

~~~sql
SELECT
    t.TASK_EXECUTION_ID,
    t.TASK_NAME,
    t.EXIT_CODE AS TASK_EXIT_CODE,
    j.JOB_EXECUTION_ID,
    j.STATUS AS BATCH_STATUS,
    j.EXIT_CODE AS BATCH_EXIT_CODE
FROM TASK_TASK_BATCH link
JOIN TASK_EXECUTION t
  ON t.TASK_EXECUTION_ID = link.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION j
  ON j.JOB_EXECUTION_ID = link.JOB_EXECUTION_ID
ORDER BY t.TASK_EXECUTION_ID DESC,
         j.JOB_EXECUTION_ID DESC;
~~~

**`TASK_EXECUTION_ID` khác `JOB_EXECUTION_ID`.** Không tự ghép hai bảng vì ID số trùng nhau. Khi thiếu `TASK_TASK_BATCH` hoặc thiếu liên kết, kiểm tra module tích hợp, `TaskBatchExecutionListener`, schema và phiên bản; đừng thay bằng phép nối suy đoán nếu có nhiều Job/Task chạy đồng thời.

### 10.5. SQL tìm trường hợp lệch trạng thái

~~~sql
SELECT
    t.TASK_EXECUTION_ID,
    t.TASK_NAME,
    t.EXIT_CODE AS TASK_EXIT_CODE,
    j.JOB_EXECUTION_ID,
    j.STATUS AS BATCH_STATUS
FROM TASK_TASK_BATCH link
JOIN TASK_EXECUTION t
  ON t.TASK_EXECUTION_ID = link.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION j
  ON j.JOB_EXECUTION_ID = link.JOB_EXECUTION_ID
WHERE j.STATUS = 'FAILED'
  AND t.EXIT_CODE = 0;
~~~

Đây là **truy vấn chẩn đoán**, không phải mọi chính sách nghiệp vụ đều yêu cầu “bất kỳ Job FAILED thì Task FAILED”. Một số Job best-effort có thể được chấp nhận thất bại, nhưng chính sách ấy cần được định nghĩa và quan sát rõ.

## 11. Khi đã bật fail-on nhưng vẫn chưa có kết quả mong muốn

Không thêm `System.exit(1)` ngay vào một listener bất kỳ. Hãy xác định **đường chạy thực tế**:

| Câu hỏi | Điều cần kiểm tra |
| --- | --- |
| Property có được nạp? | Profile, environment, CLI args, Data Flow/Kubernetes launch properties |
| Đúng phiên bản? | Spring Boot/Cloud Task/Batch BOM tương thích; property và runner API đúng đời |
| Có `spring-cloud-task-batch`? | Runtime dependency tree, auto-config đã bật |
| Job có được chạy? | Spring Batch `Job` bean, `spring.batch.job.enabled`, job names |
| Ai khởi chạy Job? | Boot/Task integrated runner, custom `ApplicationRunner` hay async JobLauncher |
| Có chạy Job hai lần? | Boot auto-run và custom runner cùng tồn tại |
| Batch Job thật sự `FAILED`? | `BATCH_JOB_EXECUTION.STATUS`, không chỉ Step `FAILED` |
| Có custom exit code mapping? | `ExitCodeGenerator`, `ExitCodeExceptionMapper`, shell wrapper |
| Có worker bất đồng bộ còn chạy? | JobExecution cuối đã được ghi chưa, có timeout không |
| Có đúng metadata DB? | DataSource/schema của TaskRepository và JobRepository |

Cây dependency có thể kiểm tra bằng:

~~~bash
mvn dependency:tree
~~~

hoặc:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Những lệnh này chỉ là **hướng dẫn thực hành**, không phải một phần của bước viết tài liệu.

### Khi custom JobLauncher trả về quá sớm

Một `JobLauncher` bất đồng bộ có thể trả về `JobExecution` còn ở `STARTING`/`STARTED`. Nếu runner đọc `getStatus()` ngay rồi trả về, Task có thể kết thúc trước khi Job chạy xong.

**Cần đợi trạng thái cuối qua JobExplorer/metadata, có timeout và xử lý kết quả rõ ràng.** Khoảng polling của fail-on-job-failure không tự thay thế deadline nghiệp vụ hoặc cơ chế dừng worker từ xa.

## 12. Nếu cần custom runner: tự ánh xạ kết quả đồng bộ

Một ứng dụng có thể cần tự chạy Batch theo tham số và **tự quyết định Task có thành công không**. Khi đó, tắt Boot auto-run để không chạy Job hai lần:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

Ví dụ `ApplicationRunner` dùng một `JobLauncher` **đồng bộ**:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationRunner implements ApplicationRunner {

    private final JobLauncher jobLauncher;
    private final Job reconciliationJob;

    public ReconciliationRunner(
            JobLauncher jobLauncher, Job reconciliationJob) {
        this.jobLauncher = jobLauncher;
        this.reconciliationJob = reconciliationJob;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        List<String> dates = args.getOptionValues("businessDate");
        if (dates == null || dates.size() != 1) {
            throw new IllegalArgumentException(
                    "Required --businessDate=yyyy-MM-dd");
        }

        String businessDate =
                LocalDate.parse(dates.get(0)).toString();

        JobParameters parameters =
                new JobParametersBuilder()
                    .addString("businessDate", businessDate)
                    .toJobParameters();

        JobExecution execution =
                jobLauncher.run(reconciliationJob, parameters);

        // Chỉ đúng khi JobLauncher đã chờ Job kết thúc.
        if (execution.getStatus() != BatchStatus.COMPLETED) {
            throw new IllegalStateException(
                "Batch job not completed: id="
                + execution.getId()
                + ", status=" + execution.getStatus());
        }
    }
}
~~~

**Ý nghĩa:** nếu `JobExecution` có trạng thái cuối không phải `COMPLETED`, runner ném exception chưa xử lý. Spring Cloud Task có thể nhận đường lỗi application để ghi trạng thái thất bại, nếu repository có thể hoạt động bình thường.

**Giới hạn cần nhớ:**

- Không bật đồng thời một runner tự động khác cho cùng Job.
- Nếu launcher **bất đồng bộ**, phải đợi trạng thái cuối theo JobExecution ID trước khi kiểm tra; `run(...)` trả về không đồng nghĩa Job đã hoàn tất.
- `JobParameters` nên gắn với **business key ổn định** để restart đúng JobInstance. Không thêm timestamp ngẫu nhiên chỉ để tránh `JobInstanceAlreadyCompleteException` mà chưa giải quyết nguy cơ xử lý trùng.
- Nếu có nhiều Job, cần xác định chính sách “fail fast”, tổng hợp mọi Job bắt buộc hoặc best-effort.
- Một Job `COMPLETED` theo Batch vẫn cần đối chiếu điều kiện nghiệp vụ (ví dụ skip count, dữ liệu đầu ra).

**Không nên trộn cơ chế custom runner này với một runner tích hợp đã tự launch Job**. Chọn một đường chạy và chứng minh bằng test.

## 13. Kiểm thử hai chiều trước khi triển khai

### 13.1. Ma trận kiểm thử bắt buộc

| Kịch bản | `demo.fail` | `fail-on-job-failure` | Batch kỳ vọng | Task kỳ vọng |
| --- | --- | --- | --- | --- |
| Baseline thành công | `false` | `false` | `COMPLETED` | `0` |
| Tái hiện thành công giả | `true` | `false` | `FAILED` | Có thể `0` |
| Bật mapping lỗi | `true` | `true` | `FAILED` | **Khác `0`** khi tích hợp hoạt động |
| Không gây thất bại giả | `false` | `true` | `COMPLETED` | `0` |
| Bootstrap DB lỗi | Bất kỳ | Bất kỳ | Có thể chưa có JobExecution | Có thể chưa có TaskExecution |
| Process-level failure | `true` | `true` | `FAILED` | Cần kiểm tra **OS exit code** riêng |

Sử dụng **metadata DB độc lập và JobParameters có chủ đích** cho mỗi test, tránh chọn nhầm bản ghi từ lần chạy khác.

### 13.2. Vì sao unit test tasklet chưa đủ?

Unit test chỉ cần gọi tasklet và xác nhận ném exception. Nhưng nó **không chứng minh**:

- Spring Batch tạo `JobExecution` có `STATUS=FAILED`.
- Spring Cloud Task ghi `TaskExecution.EXIT_CODE` khác 0.
- `spring-cloud-task-batch` được auto-config.
- JVM thật sự trả mã khác 0 cho scheduler.
- Kết quả đã commit từ các chunk trước được xử lý lại an toàn.

Phải có **integration test dùng JobRepository/TaskRepository thật**, và khi cần mã OS, thêm **process smoke test** bằng jar đã đóng gói.

### 13.3. Kiểm tra process exit

Linux/macOS:

~~~bash
java -jar batch-exit-diagnostic.jar \
  --demo.fail=true \
  --spring.cloud.task.batch.fail-on-job-failure=true
echo $?
~~~

PowerShell:

~~~powershell
java -jar batch-exit-diagnostic.jar --demo.fail=true --spring.cloud.task.batch.fail-on-job-failure=true
$LASTEXITCODE
~~~

Mục tiêu trong tình huống Batch bắt buộc thành công: **Batch `FAILED` → Task khác 0 → OS khác 0**. Nếu một mắt xích sai, phải điều tra cơ chế runner/exit mapping thay vì chỉ sửa thông điệp log.

**Không gọi `System.exit(...)` trực tiếp trong cùng JVM chứa JUnit**, vì nó có thể làm dừng toàn bộ test runner. Hãy chạy jar thành process riêng nếu cần đo OS exit.

## 14. Kubernetes Job và các hệ thống điều phối

Kubernetes không tự truy vấn `BATCH_JOB_EXECUTION`. Nó dựa vào trạng thái container và chính sách Job để kết luận thành công/thất bại. Ví dụ:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-exit-diagnostic-001
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 1800
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: task
          image: registry.example.com/batch-exit-diagnostic:1.0
          args:
            - "--demo.fail=true"
            - "--spring.cloud.task.batch.fail-on-job-failure=true"
          envFrom:
            - secretRef:
                name: batch-metadata-db
~~~

Manifest chỉ dành cho môi trường thử nghiệm: image/Secret/schema phải tồn tại, image có entrypoint Java phù hợp, không áp dụng lên dữ liệu production.

Quan sát:

~~~bash
kubectl get job batch-exit-diagnostic-001
kubectl describe job batch-exit-diagnostic-001
kubectl get pods -l job-name=batch-exit-diagnostic-001
kubectl logs job/batch-exit-diagnostic-001
~~~

Nếu label selector thay đổi theo phiên bản Kubernetes, dùng label trong Pod/Job thực tế. **Job Complete** chỉ chứng minh Pod/process đáp ứng quy tắc Job controller; nó không chứng minh dữ liệu Batch đã được xử lý đúng.

Khi bật retry từ Kubernetes:

- Một Pod mới có thể tạo **TaskExecution ID mới**.
- Spring Batch có thể restart cùng `JobInstance` nếu JobParameters giống và Job trước thất bại.
- Nhiều chunk trước đó có thể đã commit; phải có **idempotency/checkpoint**.
- Nếu Pod cũ vẫn chạy do timeout/đồng bộ chưa rõ, tránh chạy chồng cùng work key.

**Không sửa `TASK_EXECUTION.EXIT_CODE` để thay đổi Kubernetes Job condition**. Hạ tầng đã dựa vào mã process; cần sửa đường phát exit code trong ứng dụng.

## 15. Spring Cloud Data Flow và nhiều Batch Jobs

Khi khởi chạy bằng **Spring Cloud Data Flow**, có thể thấy TaskExecution và Batch JobExecution trên những màn hình khác nhau. Nếu Task trả `0` nhưng Job `FAILED`, người chỉ nhìn **Task status** có thể hiểu sai.

Cần xác minh Data Flow đang đọc đúng **metadata DB**, có `TaskBatchExecutionListener`/bảng liên kết phù hợp và đọc Batch JobExecution thực tế. Đừng coi việc có liên kết Task–Batch là bằng chứng mã lỗi được map.

### Một Task chạy nhiều Job

Các quy tắc phổ biến:

| Chính sách | Cách xác định kết quả Task |
| --- | --- |
| **Fail fast** | Một Job bắt buộc thất bại thì dừng luồng, Task thất bại |
| **Aggregate** | Chạy các Job độc lập rồi Task thất bại nếu **bất kỳ Job bắt buộc** nào thất bại |
| **Best-effort** | Job phụ có thể thất bại nhưng cần cảnh báo và retry riêng |
| **Partial success** | Nghiệp vụ cho phép kết thúc một phần, phải có trạng thái riêng cho phần chưa hoàn tất |

Một property chỉ nhắm tới `BatchStatus.FAILED` theo đường runner hỗ trợ **không thay thế** chính sách tổng hợp của ứng dụng có nhiều Job hoặc nhiều nguồn kích hoạt.

### Batch flow cố tình che lỗi Step

Nếu Step `FAILED` nhưng Job flow dùng `end()` và báo `COMPLETED`, cần xác nhận đây là **quy tắc nghiệp vụ có chủ đích** hay lỗi thiết kế. Nếu lỗi Step phải làm toàn Job thất bại, hãy chỉnh transition (`fail()` hoặc tương đương theo API version), rồi kiểm tra restart semantics trước khi chỉ sửa property Task.

## 16. Sai lầm hay gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Log có `ERROR` thì Task đương nhiên exit 1 | Thành công giả khi Batch xử lý exception nội bộ | Đọc cả Job, Task và OS code |
| `BATCH_JOB_EXECUTION.EXIT_CODE='FAILED'` nghĩa OS exit 1 | Nhầm Batch ExitStatus chuỗi với mã process | Kiểm tra process exit riêng |
| Có `spring-cloud-task-batch` là tự map lỗi | Default property vẫn `false` | Bật `fail-on-job-failure=true`, kiểm thử |
| Có `TaskBatchExecutionListener` là Task chắc chắn FAIL | Listener chủ yếu liên kết execution | Kiểm tra runner và failure mapping |
| Bật property đủ cho mọi custom runner | Có thể không đi qua Batch runner tích hợp | Tự kiểm tra JobExecution theo đường tùy chỉnh |
| Step `FAILED` thì Job luôn `FAILED` | Job flow có thể `end()` | Đọc cả Step và Job status |
| Task EXIT_CODE khác 0 nên Kubernetes chắc chắn Failed | OS process có thể trả mã khác | Kiểm tra Pod terminated exit code |
| Job thất bại nên dữ liệu đã rollback hết | Các chunk trước có thể đã commit | Đối soát/checkpoint/idempotency |
| `END_TIME IS NULL` nghĩa process còn sống | Task có thể chết trước update metadata | Đối chiếu Pod/PID/log |
| Sửa trực tiếp exit code SQL | Sai lịch sử mà không sửa nguyên nhân | Sửa config/code và lưu audit |
| Dùng `System.exit(0)` khi chạy CLI | Che thất bại khỏi scheduler | Không cưỡng ép mã thành công |
| Thêm timestamp ngẫu nhiên mỗi retry | Có thể xử lý trùng toàn bộ dữ liệu | Restart theo business key và JobParameters ổn định |

## 17. Runbook chẩn đoán trên production

1. **Thu thập định danh:** tên Task/Job, TaskExecution ID, JobExecution ID, pod/process ID, work key, thời điểm và version artifact.
2. **Xác nhận Batch:** đọc `BATCH_JOB_EXECUTION.STATUS`/`EXIT_CODE` và `BATCH_STEP_EXECUTION`; tìm step lỗi và nguyên nhân.
3. **Xác nhận Task:** đọc `TASK_EXECUTION.EXIT_CODE`/`END_TIME`/`ERROR_MESSAGE` trên đúng metadata DB.
4. **Xác nhận process:** đọc shell exit, Kubernetes `terminated.exitCode`/Job condition hoặc kết quả scheduler.
5. **Kiểm tra nghiệp vụ:** xác nhận phần dữ liệu đã commit, skip count, file/message/API đã gửi và khả năng idempotent.
6. **Xác nhận cấu hình hiệu lực:** `fail-on-job-failure`, Spring Boot/Cloud Task/Batch BOM, module `spring-cloud-task-batch`, DataSource/schema.
7. **Xác nhận launch path:** runner mặc định, custom runner, async JobLauncher, thứ tự runner, khả năng launch hai lần.
8. **Kiểm tra Batch flow:** Job thật sự `FAILED` hay chỉ một Step lỗi được `end()` chuyển thành Job `COMPLETED`?
9. **Sửa nguyên nhân:** bật mapping đúng, điều chỉnh flow, đợi Job hoàn tất, sửa wrapper/OS exit, bổ sung timeout/idempotency.
10. **Thử lại trên staging:** cả Job status, Task exit code, process exit code và dữ liệu nghiệp vụ đều phải đúng.
11. **Quyết định retry:** xác nhận process cũ đã dừng, checkpoint/JobInstance đúng và không nhân đôi side effect.
12. **Bổ sung cảnh báo:** phát hiện các bản ghi Batch `FAILED` nhưng Task `EXIT_CODE=0`, lưu tương quan chính thức Task–Batch.

### Checklist đạt yêu cầu

- [ ] Phân biệt `BatchStatus`, `ExitStatus`, Task exit code và OS exit code.
- [ ] Biết vì sao Batch `FAILED` vẫn có thể khiến Task `0`.
- [ ] Biết default và mục đích `spring.cloud.task.batch.fail-on-job-failure`.
- [ ] Xác nhận version, `spring-cloud-task-batch` và đường chạy Batch thực tế.
- [ ] Đọc được `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và `TASK_EXECUTION`.
- [ ] Khi tích hợp hỗ trợ, biết sử dụng `TASK_TASK_BATCH` để tương quan.
- [ ] Đã kiểm thử cả Job thành công và Job thất bại.
- [ ] Đã kiểm tra OS process code ngoài JVM test.
- [ ] Không quyết định kết quả Job bất đồng bộ trước khi hoàn tất.
- [ ] Biết một Step lỗi có thể không làm Job `FAILED` nếu flow quy định khác.
- [ ] Không coi rollback của một chunk là rollback toàn bộ Job.
- [ ] Có idempotency/khả năng restart và cảnh báo cho scheduler/Kubernetes/SCDF.
- [ ] Không che lỗi bằng `System.exit(0)` hoặc SQL sửa metadata.

## 18. Tổng kết

**Một Spring Batch Job thất bại không tự động có nghĩa Spring Cloud Task hoặc JVM thất bại.** `JobRepository` lưu trạng thái `JobExecution` và `StepExecution`; `TaskRepository` lưu mã thoát của lần chạy Task; còn Kubernetes/scheduler quan sát **mã process**. Ba lớp này có thể khác nhau khi lỗi Batch được xử lý thành metadata nhưng không được truyền ra vòng đời ứng dụng.

Trong nhánh tích hợp được hỗ trợ, **`spring.cloud.task.batch.fail-on-job-failure=true`** giúp chuyển `BatchStatus.FAILED` thành mã Task khác 0. Nếu có Batch flow tùy chỉnh, nhiều Job hoặc JobLauncher bất đồng bộ, phải bổ sung chính sách kết quả của ứng dụng và kiểm chứng riêng **process exit code**. Khi chẩn đoán, luôn đối chiếu **Batch, Task, process và dữ liệu nghiệp vụ**, thay vì chỉ nhìn một dòng log hoặc một con số.

### Tài liệu tham khảo

- [Spring Cloud Task — Batch Job Exit Codes và TaskBatchExecutionListener](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Cloud Task — Vòng đời và TaskExecution](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/)
- [Spring Cloud — Configuration Properties: fail-on-job-failure](https://docs.spring.io/spring-cloud/docs/current/reference/html/configprops.html)
- [Spring Batch — BatchStatus, ExitStatus và Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html)
- [Spring Batch — JobExecution, StepExecution và restart](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Boot — SpringApplication và Exit Codes](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Kubernetes — Job controller và xử lý lỗi](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
