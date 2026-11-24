# Thứ tự bộ chạy Job, chạy lại Job và tham số định danh

## 1. Ba câu hỏi cần giải quyết khi kết hợp Spring Cloud Task với Spring Batch

Một ứng dụng **Spring Cloud Task** thường được khởi chạy theo lịch hoặc theo yêu cầu, thực hiện một công việc hữu hạn rồi kết thúc. Nếu công việc có nhiều bước, xử lý theo chunk hoặc cần checkpoint và restart, ứng dụng có thể sử dụng **Spring Batch** để thực thi Job.

Khi kết hợp hai framework, người phát triển cần tách bạch ba vấn đề:

1. **Ai chạy Job và chạy vào thời điểm nào?** Spring Boot có cơ chế tự chạy một Job lúc khởi động; ứng dụng cũng có thể dùng `ApplicationRunner` hoặc `CommandLineRunner` để tự gọi `JobLauncher`. Nếu kết hợp sai, Job có thể bị khởi chạy hai lần.
2. **Khi Job thất bại, lần chạy sau là restart hay JobInstance mới?** Spring Batch dựa vào lịch sử của `JobRepository` cùng trạng thái `JobExecution` và khả năng restart của Job để quyết định.
3. **Những tham số nào xác định “cùng một JobInstance”?** `JobParameters` có cờ **identifying**. Đổi một tham số identifying sẽ tạo định danh JobInstance khác; đổi tham số non-identifying không làm thay đổi định danh.

Ví dụ: task `daily-close-task` chốt doanh thu cho tenant `tenant-A` vào ngày `2026-11-23`. CronJob chạy lúc 02:00 nhưng tiến trình chết giữa bước ghi file. Hôm sau người vận hành chạy bù cùng ngày. Nếu dùng đúng identifying parameters, Spring Batch có thể nhận ra **JobInstance trước đó**, tạo lần thực thi mới để restart theo checkpoint. Nếu vô tình gắn timestamp mới vào tham số định danh, Batch sẽ coi đó là **JobInstance khác** và có thể xử lý từ đầu.

**Spring Cloud Task theo dõi lần chạy ứng dụng; Spring Batch theo dõi Job và Step.** Hai cấp metadata này liên quan nhưng không đồng nhất.

## 2. Sơ đồ các lớp thực thi và repository

~~~mermaid
flowchart TB
    C["CronJob / API / CLI"] --> T["Tiến trình Spring Boot + Spring Cloud Task"]
    T --> TR["TaskRepository: TaskExecution"]
    T --> R["Batch startup runner hoặc runner tự viết"]
    R --> JL["JobLauncher / JobOperator"]
    JL --> JR["JobRepository"]
    JR --> JI["JobInstance = Job name + identifying parameters"]
    JI --> JE["Một hoặc nhiều JobExecution"]
    JE --> S["StepExecution + checkpoint"]
    S --> B["Business DB / file / external service"]
    TR -. "TaskBatchExecutionListener khi có integration" .-> JR
~~~

| Khái niệm | Đơn vị được theo dõi | ID và chức năng |
|---|---|---|
| `TaskExecution` (Spring Cloud Task) | Một lần thực thi **ứng dụng task** | `taskExecutionId`, start/end, exit code của process/task |
| `JobInstance` (Spring Batch) | Một Job có **cùng tên và cùng bộ identifying parameters** | Định danh công việc batch logic |
| `JobExecution` (Spring Batch) | Một lần chạy hoặc chạy lại của `JobInstance` | Kết quả `STARTED`, `FAILED`, `COMPLETED`, `STOPPED`... |
| `StepExecution` | Một lần thực thi Step trong JobExecution | Bộ đếm đọc/ghi/skip và trạng thái Step |
| `ExecutionContext` | Trạng thái được lưu để hỗ trợ restart | Checkpoint của reader, thông số tiến độ… nếu cấu hình đúng |
| Kết quả nghiệp vụ | Dữ liệu thực sự đã xử lý | Cần idempotency/transaction riêng |

Một `TaskExecution` có thể chạy một hoặc nhiều Job tùy thiết kế. Một `JobInstance` có thể được thực thi lại qua nhiều lần khởi chạy ứng dụng và vì vậy liên quan đến **nhiều TaskExecution** khác nhau. Quan hệ hai chiều giữa task và batch có thể được lưu nhờ module tích hợp `spring-cloud-task-batch`.

## 3. Ai chạy Job lúc Spring Boot khởi động?

### 3.1. Bộ chạy Job tự động của Spring Boot

Khi Spring Boot tự cấu hình Spring Batch và có **một bean `Job`**, cơ chế startup runner có thể **tự động chạy Job**. Trong các dòng Spring Boot 3.x và 4.x, lớp được tài liệu nhắc đến là **`JobLauncherApplicationRunner`**. Nó tham gia vòng gọi startup runner như các `ApplicationRunner` khác, có thứ tự thực thi riêng và dùng hạ tầng Batch để khởi chạy Job.

Với **nhiều bean Job**, cần chỉ định Job cần khởi chạy, ví dụ:

~~~properties
spring.batch.job.name=closeDayJob
~~~

Để **tắt cơ chế tự khởi chạy** khi ứng dụng muốn tự quyết định Job, đặt:

~~~properties
spring.batch.job.enabled=false
~~~

Chẳng hạn với một task có hai Job `importCustomersJob` và `closeDayJob`, đừng giả định Spring Boot sẽ tự chạy cả hai theo thứ tự bean được khai báo. Hãy chỉ rõ Job cần chạy hoặc viết một cơ chế điều phối có chủ đích.

**Lưu ý theo phiên bản:**

- Spring Boot 3.x có lớp `JobLauncherApplicationRunner` trong package `org.springframework.boot.autoconfigure.batch` và tích hợp Spring Batch 5.x.
- Spring Boot 4.x di chuyển một số package auto-configuration và sử dụng API phù hợp Spring Batch 6.x; đọc Javadoc đúng release khi custom runner.
- Tài liệu cũ Spring Boot 2.x có thể dùng `spring.batch.job.names`, hoặc tên runner cũ `JobLauncherCommandLineRunner`. Không sao chép thuộc tính/lớp cũ sang project mới mà chưa kiểm tra.
- Việc thêm `@EnableBatchProcessing` hoặc kế thừa `DefaultBatchConfiguration` có thể khiến Spring Boot **ngừng tự cấu hình Batch**, kể cả cấu hình khởi tạo schema; chỉ dùng khi chủ động quản lý toàn bộ hạ tầng.

### 3.2. Runner do ứng dụng tự viết

Nếu muốn parse tham số theo quy tắc riêng, kiểm tra dữ liệu đầu vào, chọn Job động, xác nhận trạng thái và trả mã lỗi nhất quán, có thể tự gọi Job từ `ApplicationRunner`. Khi đó phải **tắt auto-launch** để tránh khởi chạy trùng:

~~~yaml
spring:
  main:
    web-application-type: none

  application:
    name: daily-close-task

  batch:
    job:
      enabled: false

  cloud:
    task:
      name: daily-close-task
~~~

Lựa chọn giữa runner tự động và runner tự viết:

| Yêu cầu | Cách hợp lý |
|---|---|
| Ứng dụng chỉ chứa một Job và không cần kiểm soát phức tạp | Auto-launch của Spring Boot |
| Chứa nhiều Job nhưng mỗi lần chỉ chạy một Job cố định | `spring.batch.job.name` |
| Cần kiểm tra đầu vào, chọn Job, tính business key và kiểm tra `JobExecution` | Tắt auto-launch; tự viết runner |
| Cần nhiều Job chạy theo quan hệ phụ thuộc | Dùng Job/Step flow có cấu trúc, hoặc orchestrator riêng |
| Cần chạy lại JobInstance đã thất bại | Giữ identifying parameters và sử dụng cơ chế restart/JobOperator thích hợp |

Không nên dùng hai cơ chế launch độc lập chỉ để “chắc chắn Job được chạy”: nếu cả auto-runner và custom runner cùng gọi một Job, lần gọi sau có thể gặp `JobExecutionAlreadyRunningException`, `JobInstanceAlreadyCompleteException` hoặc tạo một JobInstance khác không mong muốn.

## 4. “Thứ tự bộ chạy Job” là ba loại thứ tự khác nhau

Dễ nhầm giữa **thứ tự startup runner**, **thứ tự nhiều Job**, và **thứ tự Step trong một Job**.

### 4.1. Thứ tự ApplicationRunner và CommandLineRunner

Spring Boot tập hợp các bean `ApplicationRunner` và `CommandLineRunner`, sắp xếp theo `Ordered` / `@Order`, rồi gọi trong quá trình khởi động. Giá trị order nhỏ hơn được ưu tiên chạy trước.

Ví dụ để một bước kiểm tra điều kiện chạy trước phần điều phối Job:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
class PreflightRunner implements ApplicationRunner {

    @Override
    public void run(
            org.springframework.boot.ApplicationArguments args) {
        // Kiểm tra secret, nguồn dữ liệu, tham số nghiệp vụ.
        System.out.println("Preflight OK");
    }
}
~~~

Nếu runner chạy Job có order `20`, bước kiểm tra ở `10` sẽ chạy trước. Nhưng **không nên dựa vào thứ tự mặc định** giữa các runner chưa được gán order; và thứ tự startup không thay thế transaction hay dependency đúng trong một Job.

### 4.2. Thứ tự runner của Spring Cloud Task + Batch

Spring Cloud Task có cấu hình riêng cho khả năng **phản ánh Job thất bại thành mã thoát task**:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

Theo tài liệu Spring Cloud Task, khi bật tính năng này, framework thay thế runner Batch startup mặc định bằng runner hỗ trợ nhận biết thất bại; Job có `BatchStatus.FAILED` có thể khiến mã thoát task khác 0 (giá trị mặc định thường là `1`, hoặc theo cấu hình mã thoát phù hợp).

Tài liệu cũng công bố thuộc tính cấu hình thứ tự runner tích hợp:

~~~properties
spring.cloud.task.batch.applicationRunnerOrder=100
~~~

Đây là **thứ tự của runner khởi chạy batch job trong chuỗi startup runner**; nó **không sắp lại Step** và **không quyết định thứ tự các Job độc lập trên cluster**. Property và cách hoạt động cụ thể phụ thuộc phiên bản Spring Cloud Task. Nếu phải dựa vào thứ tự, kiểm tra dependency, configuration metadata và log startup của ứng dụng triển khai.

Ví dụ một `PreflightRunner` có `@Order(10)` và runner tích hợp có order `100`: preflight được ưu tiên chạy trước Job. Tuy nhiên, khi preflight thất bại, phải để exception lan lên startup để Job không bị chạy tiếp.

### 4.3. Thứ tự Step bên trong Job

Nếu yêu cầu là “phải kiểm tra trước rồi mới xuất dữ liệu”, mô tả ở **Job flow**:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CloseDayJobConfiguration {

    @Bean
    Job closeDayJob(
            JobRepository jobRepository,
            Step validateInputStep,
            Step calculateRevenueStep,
            Step publishResultStep) {

        return new JobBuilder("closeDayJob", jobRepository)
            .start(validateInputStep)
            .next(calculateRevenueStep)
            .next(publishResultStep)
            .build();
    }
}
~~~

Ví dụ trên minh họa **Spring Batch 5 / Spring Boot 3**; ba bean Step là các thành phần cần cài đặt riêng. Spring Batch điều phối Step theo flow và chính sách restart, còn runner chỉ khởi động Job. Nếu các Step nằm trong cùng quy trình có checkpoint và điều kiện thất bại, đặt thứ tự ở flow đáng tin cậy và dễ kiểm tra hơn việc tạo ba startup runner độc lập.

## 5. JobInstance, JobExecution và JobParameters

### Định nghĩa danh tính

Spring Batch nhận diện một JobInstance bằng:

**`JobInstance = tên Job + tập JobParameters có identifying=true`**

Ví dụ:

~~~text
Job name: closeDayJob

identifying:
  tenant = tenant-A
  businessDate = 2026-11-23
  revision = 1

non-identifying:
  traceId = trace-91
  requestedBy = operator
~~~

Nếu khởi chạy `closeDayJob` hai lần với bộ identifying parameters như trên, cả hai lần cùng thuộc **một JobInstance** (với điều kiện repository giống nhau và metadata chưa bị xóa). Nếu lần đầu thất bại và Job cho phép restart, lần sau có thể sinh **JobExecution mới** cho cùng JobInstance.

Bảng minh họa:

| Lần gọi | Job name | Identifying parameters | Non-identifying | Quan hệ |
|---|---|---|---|---|
| A | `closeDayJob` | tenant=A, date=23, rev=1 | traceId=t1 | JobInstance 101, JobExecution 201 |
| B sau khi A FAILED | `closeDayJob` | tenant=A, date=23, rev=1 | traceId=t2 | **Cùng** JobInstance 101, JobExecution 202 (restart) |
| C | `closeDayJob` | tenant=A, date=24, rev=1 | traceId=t3 | JobInstance mới 102 |
| D | `closeDayJob` | tenant=A, date=23, rev=2 | traceId=t4 | JobInstance mới 103 |
| E | `otherJob` | tenant=A, date=23, rev=1 | traceId=t5 | JobInstance riêng vì tên Job khác |

Đây là số ID giả định để giải thích quan hệ, không phải kết quả chạy thật.

### Non-identifying parameters có vô nghĩa không?

Không. Chúng có thể ảnh hưởng **log, tracing, đích thông báo hoặc lựa chọn tối ưu hiệu năng**, nhưng không tham gia xác định JobInstance. Vì thế **không nên** để một non-identifying parameter thay đổi **ngữ nghĩa dữ liệu nghiệp vụ** giữa hai lần restart.

Ví dụ: nếu `sourceFile` thực sự quyết định tập dữ liệu nhập, thường nó phải được định danh ổn định bằng một identifying parameter, fingerprint hoặc snapshot rõ ràng. Nếu chỉ coi `sourceFile` là non-identifying và thay sang file khác khi restart, một JobInstance có thể tiếp tục checkpoint cũ nhưng đọc một nguồn mới, làm sai dữ liệu.

## 6. Khai báo identifying và non-identifying trong Java

Trong Spring Batch 5, có thể dùng `JobParametersBuilder` để xác định cờ identifying rõ ràng:

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
    .addString("tenant", "tenant-A", true)
    .addString("businessDate", "2026-11-23", true)
    .addLong("revision", 1L, true)
    .addString("traceId", "request-8eaf", false)
    .toJobParameters();
~~~

Giá trị `true` nghĩa là identifying; `false` là non-identifying. Với các overload thông dụng nếu không truyền cờ, identifying mặc định thường là `true`. Vì vậy đừng đưa `System.currentTimeMillis()`, `UUID.randomUUID()` hay `run.id` vào JobParameters theo thói quen rồi ngạc nhiên vì Batch cứ tạo JobInstance mới.

Ví dụ sai khi muốn restart **cùng một kỳ**:

~~~java
new JobParametersBuilder()
    .addString("businessDate", "2026-11-23")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
~~~

Ở đây `run.id` mặc định identifying, nên mỗi lần chạy có thể là JobInstance mới, mất ý nghĩa restart cùng checkpoint.

Thay bằng:

~~~java
new JobParametersBuilder()
    .addString("businessDate", "2026-11-23", true)
    .addString("tenant", "tenant-A", true)
    .addString("traceId", java.util.UUID.randomUUID().toString(), false)
    .toJobParameters();
~~~

Mã minh họa dành cho **Batch 5**; API package có thay đổi ở Batch 6. Khi áp dụng bản mới, xác minh constructor, kiểu tham số và JobOperator với tài liệu đúng phiên bản.

### Kiểm tra cờ trong JobRepository

Metadata của Spring Batch thường lưu cờ định danh trong bảng tham số của mỗi lần chạy. Với schema tương ứng của Spring Batch 5, có thể kiểm tra:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_TYPE,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = :execution_id
ORDER BY PARAMETER_NAME;
~~~

Nếu đã đổi prefix/schema, thay tên bảng và cột theo DDL release đang triển khai. **TaskRepository** của Spring Cloud Task có nhóm bảng khác, như `TASK_EXECUTION`, và không thay thế metadata JobParameters của Spring Batch.

## 7. Restart Job và tạo JobInstance mới: khác nhau thế nào?

| Trạng thái trước đó | Gọi lại cùng tên + identifying parameters | Kết quả thường gặp |
|---|---|---|
| Chưa có JobInstance | Bắt đầu mới | JobInstance mới và JobExecution đầu tiên |
| `FAILED` | Restart được phép, repository/step có trạng thái phù hợp | JobExecution **mới cùng JobInstance**; Step phù hợp tiếp tục theo checkpoint |
| `STOPPED` | Restart được phép | JobExecution mới cùng JobInstance |
| `COMPLETED` | Gọi lại cùng identifying parameters | Thường ném `JobInstanceAlreadyCompleteException` |
| `STARTED` và đang chạy thật | Gọi đồng thời | Thường gặp `JobExecutionAlreadyRunningException` |
| `STARTED` nhưng JVM đã chết đột ngột | Gọi lại ngay | Repository có thể nghĩ job còn chạy; cần quy trình recovery có kiểm chứng |
| Job được cấu hình không cho restart | Gọi lại sau FAILED | `JobRestartException` hoặc từ chối theo chính sách |
| Thay một identifying parameter | Gọi lại | **JobInstance mới**; không dùng checkpoint của instance trước |

**Restart** có nghĩa tiếp tục **cùng JobInstance**, có thể bỏ qua các Step đã hoàn thành và khôi phục trạng thái reader/processor/writer từ `ExecutionContext` nếu Job/Step được thiết kế restartable. Nó **không bảo đảm** không lặp side effect bên ngoài transaction.

**New instance** có nghĩa một công việc logic khác theo định nghĩa Batch: Job được khởi tạo từ đầu với bộ identifying parameters khác. Đó có thể là thao tác hợp lệ khi chạy ngày mới hoặc revision mới, nhưng **không phải retry đúng nghĩa** của kỳ cũ.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu chạy closeDayJob"] --> B["Tạo identifying JobParameters ổn định"]
    B --> C{"JobInstance cùng key đã tồn tại?"}
    C -- "Chưa" --> D["JobInstance mới + JobExecution đầu"]
    C -- "Đã có" --> E{"Trạng thái lần trước?"}
    E -- "FAILED / STOPPED" --> F["Restart: JobExecution mới cùng instance"]
    E -- "COMPLETED" --> G["Không khởi chạy lại cùng instance"]
    E -- "Đang STARTED" --> H["Từ chối trùng / xác minh tiến trình"]
    D --> I["JobRepository theo dõi step/checkpoint"]
    F --> I
    G --> J["Đối chiếu kết quả nghiệp vụ, trả kết quả cũ"]
    H --> K["Điều tra / recovery nếu tiến trình thật sự chết"]
~~~

Các exception thuộc nhánh khởi động như `JobInstanceAlreadyCompleteException` khác với một `JobExecution` được tạo rồi hoàn tất ở trạng thái `FAILED`. Phải xử lý cả **lỗi không khởi chạy được** và **lỗi sau khi Job đã chạy**.

## 8. Chạy lại bằng JobLauncher và JobOperator

### 8.1. Gọi lại với JobLauncher trong Spring Batch 5

`JobLauncher.run(job, parameters)` tạo hoặc chạy lại JobExecution tùy repository và trạng thái JobInstance. Nếu JobLauncher chạy đồng bộ, sau khi phương thức trả về, người gọi có thể đọc `JobExecution.getStatus()`.

~~~java
JobExecution execution = jobLauncher.run(job, parameters);
if (execution.getStatus() != BatchStatus.COMPLETED) {
    throw new IllegalStateException(
        "Batch job ended with " + execution.getStatus());
}
~~~

Lưu ý: **Job có thể chạy thất bại nhưng `JobLauncher.run` vẫn trả `JobExecution`**, thay vì ném exception. Exception thường xuất hiện khi không thể khởi chạy hợp lệ (chẳng hạn tham số sai hoặc instance đã hoàn thành); vì vậy **bắt buộc kiểm tra trạng thái JobExecution** nếu task cần trả mã thất bại.

Nếu JobLauncher được cấu hình **bất đồng bộ**, `run(...)` có thể trả về khi Job vẫn `STARTING/STARTED`. Khi đó không thể dùng code trên như cơ chế “chờ hoàn tất”; cần chờ/poll theo ID với timeout, hoặc dùng launcher đồng bộ cho ứng dụng task ngắn hạn khi phù hợp.

### 8.2. JobOperator và thao tác quản trị

`JobOperator` cung cấp những khả năng như khởi chạy, truy vấn, dừng, restart và start-next-instance. API chính xác thay đổi theo dòng Spring Batch:

- **Restart failed/stopped JobExecution**: tiếp tục **JobInstance cũ** nếu đủ điều kiện.
- **Start next instance**: dùng `JobParametersIncrementer` để sinh identifying parameters **mới**, nhằm bắt đầu **JobInstance mới**.
- **Stop**: yêu cầu dừng có kiểm soát khi Job còn chạy, không phải kill tức thời.
- **Recover**: với những release hỗ trợ API recovery cho trạng thái treo sau crash, phải xác minh process đã chết và xử lý đúng điều kiện trước khi recover.

`RunIdIncrementer` hoặc một `JobParametersIncrementer` tùy chỉnh là phù hợp khi muốn **thực sự tạo một phiên bản JobInstance mới**. Nó không nên được gọi tự động cho mọi retry mà nghiệp vụ chỉ muốn tiếp tục cùng ngày.

Đối với ứng dụng có Spring Batch 5, một cách restart sau lỗi là khởi chạy lại cùng tên Job và **cùng identifying parameters**, nếu cấu hình job hỗ trợ. Có thể dùng `JobOperator.restart(executionId)` theo API của phiên bản. Với Spring Batch 6, một số API `JobLauncher`/`JobOperator` đã được đổi hoặc đánh dấu deprecated; không nên nhầm hai bộ chữ ký.

## 9. Cấu hình task thủ công khởi chạy một Job và kiểm tra kết quả

Phần này minh họa phương án **không sử dụng auto-launch của Spring Boot**. Với Spring Boot 3 / Spring Batch 5, ta tự kiểm soát xác thực tham số và kết quả của Job. Code giả định đã có bean `closeDayJob` và hạ tầng `JobRepository`/`JobLauncher` của Spring Batch.

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CloseDayRunnerConfiguration {

    @Bean
    ApplicationRunner launchCloseDayJob(
            JobLauncher jobLauncher,
            @Qualifier("closeDayJob") Job closeDayJob) {

        return args -> {
            String tenant = oneRequired(args.getOptionValues("tenant"), "tenant");
            String dateString = oneRequired(args.getOptionValues("date"), "date");
            LocalDate businessDate = LocalDate.parse(dateString);

            JobParameters params = new JobParametersBuilder()
                .addString("tenant", tenant, true)
                .addString("businessDate", businessDate.toString(), true)
                .addLong("revision", 1L, true)
                .addString("traceId", UUID.randomUUID().toString(), false)
                .toJobParameters();

            // Giả định JobLauncher đồng bộ (mặc định thường gặp).
            JobExecution result = jobLauncher.run(closeDayJob, params);

            if (result.getStatus() != BatchStatus.COMPLETED) {
                throw new IllegalStateException(
                    "Job failed: " + result.getStatus()
                    + ", executionId=" + result.getId());
            }
        };
    }

    private static String oneRequired(List<String> values, String name) {
        if (values == null || values.size() != 1
                || values.get(0) == null || values.get(0).isBlank()) {
            throw new IllegalArgumentException("Missing --" + name + "=...");
        }
        return values.get(0);
    }
}
~~~

Cấu hình kèm theo:

~~~yaml
spring:
  main:
    web-application-type: none
  batch:
    job:
      enabled: false
  cloud:
    task:
      name: close-day-task
~~~

Chạy:

~~~bash
java -jar close-day-task.jar --tenant=tenant-A --date=2026-11-23
~~~

**Tại sao đây là một ví dụ chạy lại hợp lý?**

- `tenant`, `businessDate` và `revision` là identifying, giữ ổn định khi retry.
- `traceId` là non-identifying, có thể khác ở mỗi TaskExecution nhưng không tạo JobInstance mới.
- Runner chỉ hoàn tất thành công khi `JobExecution` đã `COMPLETED`; khi Job lỗi, exception lan ra vòng đời Spring Boot/Spring Cloud Task.
- Nếu chạy lại sau khi JobInstance đã `COMPLETED`, Batch có thể ném `JobInstanceAlreadyCompleteException`. Trong một quy trình **idempotent** muốn coi “đã hoàn tất trước đó” là kết quả hợp lệ, cần chủ động **tra JobRepository và kết quả nghiệp vụ** để trả `ALREADY_COMPLETED` theo chính sách, chứ không nuốt mọi exception.
- Ví dụ không định nghĩa hành vi khi JobLauncher bất đồng bộ; nếu thay executor hoặc launcher, phải thiết kế chờ/quan sát status cho phù hợp.

Để mã thoát của JVM được hệ điều phối đọc đúng, cần đảm bảo ứng dụng task đóng context và có exit-code policy phù hợp với việc runner ném lỗi. Không chỉ `System.out.println("failed")` rồi trở về bình thường.

## 10. Khi dùng auto-runner: mã thoát task và trạng thái Job có thể lệch nhau

Một lỗi thường gặp: Spring Batch Job chạy, chuyển `BatchStatus.FAILED`, nhưng ứng dụng Spring Boot không có exception lan lên runner và **mã thoát tiến trình vẫn là 0** trong cấu hình mặc định. Spring Cloud Task có thể ghi nhận trạng thái tác vụ thành công ở mức process mặc dù Job Batch thất bại.

Với Spring Cloud Task batch integration hỗ trợ tính năng này, cấu hình:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

cho phép framework phản ánh Job `FAILED` thành mã thoát task khác 0 theo cơ chế tương ứng. Nếu cần kiểm soát **mã thoát cụ thể theo từng loại lỗi Job**, hãy kiểm tra cơ chế `ExitCodeGenerator` và API runner của chính release, hoặc tự viết runner/logic ánh xạ có kiểm soát.

Đặc biệt tránh nhầm:

| Trạng thái quan sát | Nói lên điều gì? | Chưa chứng minh |
|---|---|---|
| `TaskExecution.exitCode=0` | Ứng dụng task nhìn nhận lần chạy theo chính sách exit code | Job Batch chắc chắn `COMPLETED` |
| `JobExecution.status=COMPLETED` | Batch job hoàn tất theo flow | Side effect ra hệ thống ngoài đã xử lý exactly-once |
| `JobExecution.status=FAILED` | Job Batch có bước thất bại | Toàn bộ dữ liệu nghiệp vụ đều rollback |
| Không có `TaskExecution.endTime` | Task chưa được chốt trong metadata | Process đã chết (nó có thể vẫn đang chạy) |
| `JobInstanceAlreadyCompleteException` | JobInstance cùng identifying parameters đã hoàn tất trước đó | Thực thi lần này đã chạy và hoàn tất một vòng nghiệp vụ mới |

Nếu cả TaskRepository và JobRepository tồn tại, hãy giám sát **cả hai** và đối chiếu với dữ liệu nghiệp vụ. Framework không thể ghi metadata sau `SIGKILL`; một Job có thể còn `STARTED` trong repository khi JVM thực tế đã chết.

## 11. Quan hệ TaskExecution và JobExecution

Khi tích hợp module `spring-cloud-task-batch` và có Job bean phù hợp, Spring Cloud Task có thể tự cấu hình **`TaskBatchExecutionListener`** để liên kết JobExecution với TaskExecution đã khởi chạy nó. Quan hệ này phục vụ truy vết, không thay thế metadata của riêng từng framework.

~~~mermaid
sequenceDiagram
    participant O as CronJob / CLI
    participant T as Spring Cloud Task
    participant B as Spring Batch
    participant R as Repositories
    O->>T: Khởi chạy tiến trình lần 1
    T->>R: TaskExecution 501
    T->>B: closeDayJob / identifying key K
    B->>R: JobInstance 88, JobExecution 901
    B-->>T: FAILED
    T-->>O: Task kết thúc theo exit policy
    O->>T: Retry cùng key K
    T->>R: TaskExecution 502
    T->>B: closeDayJob / identifying key K
    B->>R: Cùng JobInstance 88, JobExecution 902
    B-->>T: COMPLETED
    T-->>O: Task hoàn tất
~~~

Một TaskExecution mới **không đồng nghĩa** với JobInstance mới. Khi muốn đối chiếu những lần chạy lại, sử dụng:

- `TaskRepository` để biết có bao nhiêu lần khởi chạy ứng dụng.
- `JobRepository` để biết JobInstance, các JobExecution và StepExecution.
- Bảng liên kết của integration (nếu được cấu hình và hỗ trợ trong schema) để nối hai nguồn metadata.
- Bảng kết quả nghiệp vụ để xác nhận dữ liệu thực sự đã được commit và tránh tác động trùng.

Nếu một lần chạy task chứa nhiều Job, quan hệ có thể là **một TaskExecution → nhiều JobExecution**. Không dựa vào giả định một-một trong truy vấn hoặc dashboard.

## 12. Command-line parameters: phân biệt Spring properties và JobParameters

Với **auto-runner** trong Spring Boot 3.x, các option có tiền tố `--` được Spring Boot xử lý như **application properties**. Job parameters thường được truyền ở dạng **không có `--`**:

~~~bash
java -jar batch-task.jar --spring.batch.job.name=closeDayJob tenant=tenant-A businessDate=2026-11-23
~~~

Trong ví dụ này:

- `--spring.batch.job.name=closeDayJob` là lựa chọn cấu hình startup.
- `tenant=tenant-A` và `businessDate=2026-11-23` là các tham số để bộ chuyển đổi của batch runner nhận.
- Quy tắc xác định kiểu và cờ identifying của **JobParametersConverter** phụ thuộc phiên bản và cú pháp converter; với nhu cầu kiểm soát chặt, dùng `JobParametersBuilder` trong custom runner.

**Không trộn lẫn** ví dụ auto-runner ở trên với ví dụ custom `ApplicationRunner` mục 9: custom runner đọc `--tenant` và `--date` bằng `ApplicationArguments`, rồi **tự xây JobParameters**. Hai cách dùng CLI khác nhau và cần được thiết kế nhất quán.

Với Spring Boot 3.5, tài liệu yêu cầu truyền lại **cả identifying lẫn non-identifying job parameters** khi restart từ CLI: non-identifying parameters của lần thực thi trước không được tự sao chép nguyên trạng. Cần đảm bảo non-identifying fields như tracing hoặc cấu hình runtime không vô tình làm thay đổi ý nghĩa xử lý khi restart.

## 13. Các tình huống thực tế và hướng xử lý

### Job hoàn tất rồi CronJob chạy lại cùng ngày

Nếu bộ identifying parameters không đổi, Spring Batch từ chối tạo JobExecution mới cho JobInstance đã `COMPLETED`. Nếu nghiệp vụ muốn **chạy bù an toàn**, hãy kiểm tra kết quả cũ và trả trạng thái `ALREADY_COMPLETED` theo chính sách, đồng thời đảm bảo kết quả nghiệp vụ đã tồn tại. Không thêm `run.id` ngẫu nhiên để bỏ qua quy tắc này.

### Job thất bại giữa Step rồi restart

Giữ lại cùng identifying parameters. Spring Batch tạo JobExecution mới cùng JobInstance nếu cho phép restart, dùng `ExecutionContext` để khôi phục Step. Reader/writer phải được thiết kế restartable; dữ liệu được ghi ngoài transaction hoặc ở bước không checkpoint vẫn cần idempotency.

### Đang chạy nhưng bị kill, repository còn STARTED

Không chạy lại ngay chỉ vì process cũ không thấy trên máy hiện tại. Đối chiếu Pod/Job/process của toàn cluster, kho dữ liệu, lease và repository. Khi chắc chắn instance cũ đã chết, sử dụng **quy trình recovery của đúng phiên bản Spring Batch**. Spring Batch 6 có API recovery ở một số release; phiên bản trước cần cơ chế vận hành khác. Không tự ý cập nhật hàng loạt `BATCH_JOB_EXECUTION.STATUS` bằng SQL mà không điều tra.

### Hai tiến trình cùng khởi chạy JobInstance

JobRepository có cơ chế kiểm soát concurrency và có thể từ chối một lần launch bằng `JobExecutionAlreadyRunningException`. Tuy nhiên, **vẫn cần khóa nghiệp vụ/unique constraint** ở bảng kết quả để bảo vệ side effect và các tiến trình không thuộc cùng repository hoặc ngoài Spring Batch.

### Yêu cầu chạy revision mới sau khi điều chỉnh số liệu

Tạo identifying parameter `revision=2` có chủ đích. Một JobInstance mới là hợp lý; cần xác định cách kết quả revision 2 thay thế hoặc điều chỉnh revision 1, và đảm bảo bảng nghiệp vụ ghi đúng quy tắc phiên bản.

### Nhiều Job cần thứ tự hoặc phụ thuộc

Không dựa vào thứ tự tạo bean hoặc tên bean. Nếu các bước thuộc cùng công việc batch, dùng Job flow/Step transition. Nếu là hai Job độc lập có quan hệ phụ thuộc, dùng orchestrator riêng hoặc runner điều phối có xử lý trạng thái, retry và idempotency rõ ràng.

## 14. Chẩn đoán qua JobRepository và TaskRepository

Với schema Spring Batch tương ứng và prefix mặc định, những câu SQL sau giúp điều tra lần chạy (điều chỉnh tên bảng/cột theo release):

~~~sql
-- Danh sách JobInstance theo tên job.
SELECT JOB_INSTANCE_ID, JOB_NAME, JOB_KEY
FROM BATCH_JOB_INSTANCE
WHERE JOB_NAME = 'closeDayJob'
ORDER BY JOB_INSTANCE_ID DESC;

-- Các lần thực thi và trạng thái của một JobInstance.
SELECT JOB_EXECUTION_ID, JOB_INSTANCE_ID,
       STATUS, EXIT_CODE, START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
WHERE JOB_INSTANCE_ID = :job_instance_id
ORDER BY JOB_EXECUTION_ID;

-- Những tham số có và không tham gia nhận diện.
SELECT JOB_EXECUTION_ID, PARAMETER_NAME,
       PARAMETER_VALUE, IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = :job_execution_id;
~~~

Dòng Spring Batch 5 sử dụng một tập cột như trên trong schema JDBC quen thuộc. Những release mới có thể thay tên cột/cấu trúc repository hoặc loại datastore, do đó cần đối chiếu DDL thực tế. Với Spring Cloud Task, truy vấn riêng bảng `TASK_EXECUTION` theo `TASK_EXECUTION_ID`.

**Đừng suy ra “Job đã hoàn thành nghiệp vụ” chỉ từ `EXIT_CODE=COMPLETED`** nếu có side effect ngoài CSDL, bước xử lý bất đồng bộ hoặc retry message. Cần so kết quả nghiệp vụ và bộ nhận bên ngoài.

## 15. Bảng lỗi thường gặp

| Biểu hiện | Nguyên nhân khả dĩ | Khắc phục |
|---|---|---|
| Job chạy hai lần ngay khi ứng dụng boot | Auto-runner và custom runner đều được bật | Chọn một cơ chế launch, tắt auto-run khi tự gọi |
| Có hai Job bean, không chạy đúng Job | Chưa chỉ định tên Job | `spring.batch.job.name` hoặc orchestration có chủ đích |
| Preflight chạy sau Job | Thứ tự ApplicationRunner không được cấu hình | `@Order` và cấu hình order của runner tích hợp khi có |
| Restart thất bại vì `JobInstanceAlreadyCompleteException` | Cùng identifying params đã completed | Trả kết quả cũ / đánh giá reprocess thay vì đổi khóa tùy tiện |
| Mỗi retry lại đọc từ đầu | Thêm timestamp hoặc `run.id` identifying mới | Giữ khóa định danh ổn định, xem lại JobParametersBuilder |
| Job FAILED nhưng task exit 0 | Mặc định không truyền trạng thái Job vào mã thoát task | Bật `fail-on-job-failure` hoặc custom runner kiểm tra JobExecution |
| Job bị kill, repository vẫn STARTED | Không kịp ghi trạng thái cuối | Xác minh process, recovery có kiểm soát |
| Restart báo instance đang chạy | Có run thật hoặc metadata chưa được phục hồi | Kiểm tra cluster và JobRepository trước khi recover |
| Non-identifying param thay đổi làm dữ liệu sai | Dùng param ảnh hưởng nguồn dữ liệu nhưng không identifying | Thêm vào khóa / cố định snapshot / validate |
| Bảng TaskExecution và Batch metadata không khớp | Đang nhìn hai cấp repository khác nhau | Dùng ID liên kết, Batch listener, đối chiếu business state |
| Job dùng Step async nhưng task thoát sớm | Launcher/runner kết thúc trước khi Job terminal | Chờ kết quả thực sự và kiểm tra `BatchStatus` |
| Không thể restart Step | Job/Step không restartable hoặc thiếu checkpoint | Kiểm tra cấu hình, reader/writer, ExecutionContext |

## 16. Bài thực hành kiểm chứng

Tạo ứng dụng Spring Cloud Task + Spring Batch có `closeDayJob` gồm hai Step: kiểm tra input và ghi kết quả. Dùng `JobRepository` bền vững, một business key gồm tenant/ngày/revision và kết quả nghiệp vụ có unique constraint.

1. Cấu hình `spring.batch.job.enabled=false`, tự viết runner theo ví dụ mục 9 và bảo đảm JobLauncher đồng bộ.
2. Chạy ngày `2026-11-23` nhưng chủ động gây lỗi giữa bước ghi. Quan sát TaskExecution, JobInstance và JobExecution có trạng thái FAILED.
3. Chạy lại **cùng identifying parameters**, đổi duy nhất `traceId`. Xác minh JobInstance ID giữ nguyên nhưng JobExecution ID thay đổi.
4. Xác minh Step restart thực hiện đúng theo checkpoint và kết quả nghiệp vụ không nhân đôi.
5. Chạy lại một lần sau khi JobInstance đã COMPLETED. Quan sát `JobInstanceAlreadyCompleteException` hoặc chính sách “đã hoàn tất” của wrapper.
6. Đổi `revision` thành 2: đây là **JobInstance mới**; kiểm tra nó không bị nhầm là restart của revision 1.
7. Bật auto-runner trong một môi trường thử riêng, cấu hình `spring.batch.job.name` và `spring.cloud.task.batch.fail-on-job-failure=true` nếu hỗ trợ; xác minh hệ điều phối nhìn thấy lỗi Job.
8. Thử hai tiến trình cùng JobInstance để kiểm tra kiểm soát concurrency; đừng chỉ chạy hai lần tuần tự.
9. Diễn tập crash/kill giữa Step, đối chiếu metadata với tiến trình thực tế trước khi thao tác recovery.

| Điều cần quan sát | Kỳ vọng |
|---|---|
| Lần đầu FAILED, retry cùng identifying params | Cùng JobInstance, thêm JobExecution |
| Thay non-identifying `traceId` | Không đổi JobInstance |
| Thay identifying `revision` | Tạo JobInstance mới |
| Chạy lại JobInstance COMPLETED | Không tự chạy lại cùng instance |
| Batch Job FAILED | Mã thoát task phản ánh lỗi theo cấu hình hoặc logic custom |
| JVM bị kill | Metadata có thể chưa được chốt; cần đối chiếu trước retry |
| Business result | Không ghi trùng nhờ key, transaction, idempotency |

## 17. Kết luận và checklist triển khai

- **Chọn một cách khởi chạy Job:** startup runner tự động hoặc custom runner; không vô tình chạy cả hai.
- **Định nghĩa thứ tự đúng tầng:** `@Order` cho startup runner, thuộc tính runner order của Spring Cloud Task nếu có, Job flow cho Step, orchestrator cho các Job độc lập.
- **Dùng identifying JobParameters ổn định** để cùng kỳ và cùng tenant tạo cùng JobInstance khi retry.
- **Không dùng `run.id` hoặc timestamp identifying mới** cho một lần chạy lại cần tiếp tục checkpoint cũ.
- **Kiểm tra trạng thái JobExecution** và ánh xạ lỗi Batch thành kết quả task/JVM; không coi `JobLauncher.run` trả về là đồng nghĩa Job thành công.
- **Xác minh điều kiện restart:** trạng thái trước, Job restartable, Step checkpoint, tình trạng tiến trình đang chạy và JobRepository.
- **Giữ kết quả nghiệp vụ idempotent** qua nhiều TaskExecution, JobExecution và side effect bên ngoài.
- **Đối chiếu TaskRepository, JobRepository, business DB và bộ điều phối** khi sự cố hoặc khi cần chạy bù.

**Spring Cloud Task** cho biết một lần chạy ứng dụng đã diễn ra thế nào; **Spring Batch** quyết định một JobInstance được định danh và restart ra sao. Thiết kế đúng thứ tự runner, tham số định danh và cơ chế xử lý lỗi giúp các tác vụ có thời gian chạy hữu hạn hoạt động an toàn khi chạy theo lịch hoặc yêu cầu.

### Tài liệu đối chiếu

- [Spring Boot 3.5 — Batch Applications](https://docs.spring.io/spring-boot/3.5/how-to/batch.html)
- [Spring Boot — Spring Batch startup and auto-configuration](https://docs.spring.io/spring-boot/reference/io/spring-batch.html)
- [Spring Cloud Task — Spring Batch integration and exit codes](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Batch — Advanced Metadata Usage and JobOperator](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch — Metadata schema and identifying parameters](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
