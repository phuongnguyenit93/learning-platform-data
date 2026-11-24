# Chọn Job và truyền JobParameters

Trong một ứng dụng **Spring Cloud Task**, tiến trình Spring Boot khởi động, chạy công việc hữu hạn rồi kết thúc; **TaskRepository** ghi lịch sử của lần chạy bằng `TaskExecution`. Khi công việc cần đọc dữ liệu theo chunk, checkpoint, retry và khởi động lại sau lỗi, ta thường tích hợp **Spring Batch**. Khi đó, ứng dụng có thể chứa **nhiều `Job`**, và mỗi lần khởi chạy phải xác định **Job nào được chạy** cùng **`JobParameters` nào được truyền vào**.

Bài này thuộc chương **Spring Batch**. Mục tiêu là phân biệt việc chọn `Job` với việc truyền `JobParameters`, nắm cách chọn Job khi Spring Boot tự chạy Batch Job hoặc khi ứng dụng chủ động gọi `JobLauncher`, hiểu tác động của tham số tới **`JobInstance`**, cách chạy lại và đối chiếu kết quả giữa **TaskRepository** và **JobRepository**. Ví dụ xuyên suốt là hệ thống có hai Job: `importOrdersJob` để nhập đơn hàng và `dailyReportJob` để tổng hợp báo cáo theo ngày.

> **Phạm vi phiên bản:** Ví dụ Java dùng các API quen thuộc của **Spring Boot 3.x / Spring Batch 5.x** và Spring Cloud Task tương thích, như `JobBuilder`, `StepBuilder`, `JobLauncher`, `JobParametersBuilder`. Những nhánh mới hơn có thể thay đổi API, bộ starter hoặc cách tự cấu hình. Hãy dùng BOM và tài liệu đúng phiên bản trước khi sao chép vào dự án.

## 1. Phân biệt ba đối tượng: Task, Job và JobInstance

Một lần khởi chạy JAR thường tạo một `TaskExecution`. Bên trong, ứng dụng có thể chạy một hoặc nhiều `Job` của Spring Batch, mỗi Job có một `JobExecution` riêng. Spring Batch xác định `JobInstance` theo **tên Job + tập JobParameters có thuộc tính `identifying=true`**.

| Khái niệm | Đại diện cho | Ví dụ |
| --- | --- | --- |
| `TaskExecution` | Một lần chạy tiến trình Spring Cloud Task | Tiến trình nhập dữ liệu khởi chạy lúc 02:00 |
| `Job` | Định nghĩa xử lý theo các Step | `importOrdersJob`, `dailyReportJob` |
| `JobParameters` | Các giá trị truyền **cho một JobExecution** | `businessDate=2026-11-23`, `sourceId=partner-A` |
| `JobInstance` | Một lần thực thi *logic* được phân biệt bằng tên Job và tham số identifying | `importOrdersJob` cho ngày 2026-11-23 và nguồn partner-A |
| `JobExecution` | Một lần **thử chạy** một JobInstance (kể cả lần restart) | Thử lần 1 thất bại; thử lần 2 thành công |
| `JobRepository` | Lưu metadata của Job, Step, tham số và checkpoint | Bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` |
| `TaskRepository` | Lưu vòng đời tiến trình Task và liên kết Task–Batch | `TASK_EXECUTION`, `TASK_TASK_BATCH` |

Ví dụ cùng một JobInstance được thử chạy hai lần:

~~~text
TaskExecution #101
  └── Job: importOrdersJob
      ├── identifying: businessDate=2026-11-23
      ├── identifying: sourceId=partner-A
      └── JobExecution #501: FAILED

TaskExecution #102 (lần chạy lại tiến trình)
  └── Job: importOrdersJob
      ├── identifying: businessDate=2026-11-23
      ├── identifying: sourceId=partner-A
      └── JobExecution #502: COMPLETED
             (cùng JobInstance với #501)
~~~

Ở ví dụ này, **TaskExecution ID thay đổi** giữa hai tiến trình nhưng **JobInstance không đổi** vì tên Job và tham số identifying không đổi. Đây là cơ sở để Spring Batch tìm lại trạng thái đã checkpoint khi Job có hỗ trợ restart.

### Sơ đồ chọn và khởi chạy

~~~mermaid
flowchart TD
    A["Cron / API / người vận hành"] --> B["Chạy Spring Boot Task"]
    B --> C["TaskRepository: TaskExecution"]
    B --> D{"Chọn Job nào?"}
    D --> E["importOrdersJob"]
    D --> F["dailyReportJob"]
    E --> G["JobLauncher + JobParameters"]
    F --> G
    G --> H[("JobRepository: JobInstance, JobExecution, StepExecution")]
    G --> I["Xử lý theo Step / chunk / tasklet"]
    I --> J["Đọc trạng thái COMPLETED / FAILED / STOPPED"]
    J --> K["Cập nhật kết quả Task; kết thúc tiến trình"]
    H -. "Liên kết Task–Batch" .-> C
~~~

**Chọn Job** quyết định quy trình nào chạy. **JobParameters** quyết định dữ liệu/kỳ nào được xử lý và, tùy cờ identifying, JobInstance nào được tra cứu. Hai quyết định khác nhau nhưng đều cần chính xác.

## 2. Cách một ứng dụng có nhiều Job được tổ chức

Giả sử ứng dụng có các bean:

~~~java
@Configuration
public class BatchJobsConfiguration {

    @Bean
    Job importOrdersJob(JobRepository repo,
                        @Qualifier("importOrdersStep") Step step) {
        return new JobBuilder("importOrdersJob", repo)
                .start(step)
                .build();
    }

    @Bean
    Job dailyReportJob(JobRepository repo,
                       @Qualifier("dailyReportStep") Step step) {
        return new JobBuilder("dailyReportJob", repo)
                .start(step)
                .build();
    }
}
~~~

Các bean `importOrdersStep` và `dailyReportStep` phải được định nghĩa ở phần cấu hình Step; đoạn trên minh họa **tên Job**. Trong thực tế, Spring Batch nhận diện bằng **`Job.getName()`** (chuỗi truyền vào `new JobBuilder(...)`), không nên luôn giả định tên bean và tên Job chắc chắn giống nhau.

Chẳng hạn cùng một image chứa hai quy trình sẽ có hai yêu cầu vận hành:

- Đúng nguồn đối tác gửi tệp: chọn **`importOrdersJob`** và truyền `sourceId`, `businessDate`.
- Đến giờ chốt số liệu: chọn **`dailyReportJob`** và truyền `businessDate`, có thể thêm `tenantId`.

Nếu chạy sai Job, tham số vẫn có thể được parse thành công nhưng nghiệp vụ thực hiện sai mục đích. Bởi vậy, khi ứng dụng có nhiều Job, phải có cơ chế lựa chọn **tường minh** và kiểm tra tên hợp lệ.

## 3. Cách A: Spring Boot tự khởi chạy Job đã chọn

Spring Boot có cơ chế tự chạy Spring Batch Job khi ứng dụng khởi động, nếu Batch auto-configuration đang hoạt động. Khi chỉ có một `Job`, Boot thường tự khởi chạy Job đó. Khi có **nhiều Job bean**, cần chọn bằng thuộc tính:

~~~properties
spring.batch.job.name=importOrdersJob
~~~

Đây là thuộc tính **Spring Boot / Spring Batch**, không phải `spring.cloud.task.job-name`. Nhánh Spring Cloud Task cũ có `spring.cloud.task.batch.job-names`, nhưng thuộc tính này đã **deprecated**; nên dùng `spring.batch.job.name` khi bản Spring Boot đang chạy hỗ trợ.

Ví dụ cấu hình:

~~~yaml
spring:
  application:
    name: order-processing-task
  main:
    web-application-type: none
  datasource:
    url: ${BATCH_DB_URL}
    username: ${BATCH_DB_USER}
    password: ${BATCH_DB_PASSWORD}
  batch:
    job:
      enabled: true
  cloud:
    task:
      initialize-enabled: false
      batch:
        fail-on-job-failure: true
~~~

`spring.batch.job.enabled=true` yêu cầu Boot thực hiện cơ chế tự khởi chạy khi đủ điều kiện; trên các nhánh Boot thông dụng, đây là hành vi mặc định. `spring.cloud.task.batch.fail-on-job-failure=true` giúp tích hợp Spring Cloud Task phản ánh Job thất bại thành mã thoát Task khác `0`, để bộ điều phối phát hiện lỗi. Thuộc tính này cần **đúng module tích hợp Task–Batch và phiên bản hỗ trợ**.

### 3.1. Lệnh chạy chọn Job và truyền tham số

~~~bash
java -jar batch-task.jar \
  --spring.batch.job.name=importOrdersJob \
  businessDate=2026-11-23 \
  sourceId=partner-A

java -jar batch-task.jar \
  --spring.batch.job.name=dailyReportJob \
  businessDate=2026-11-23
~~~

**Cú pháp đáng chú ý:**

| Đối số trong lệnh | Thuộc loại nào? | Tác dụng |
| --- | --- | --- |
| `--spring.batch.job.name=importOrdersJob` | Spring Boot property | Chọn Job để startup runner khởi chạy |
| `businessDate=2026-11-23` | Batch JobParameter | Truyền ngày nghiệp vụ cho Job |
| `sourceId=partner-A` | Batch JobParameter | Truyền định danh nguồn cho Job |

Spring Boot đưa các đối số mở đầu bằng **`--`** vào `Environment` như cấu hình ứng dụng. Cơ chế tự chạy Batch Job mặc định dùng các đối số dạng **`key=value` không có `--`** làm `JobParameters`.

Do đó, lệnh này **không truyền ngày vào Batch Job theo cơ chế mặc định**:

~~~bash
# Không dùng cú pháp này nếu muốn startup runner tự map
# businessDate vào JobParameters:
java -jar batch-task.jar \
  --spring.batch.job.name=dailyReportJob \
  --businessDate=2026-11-23
~~~

`--businessDate=...` là **property của Spring Boot**, nên có thể xuất hiện trong `Environment` nhưng không tự biến thành `JobParameter`. Đây là nguồn gốc của nhiều lỗi khi Job dùng `@StepScope` nhưng `jobParameters['businessDate']` lại rỗng.

### 3.2. Cách nhận JobParameters trong Step

Bean có `@StepScope` có thể lấy tham số theo expression:

~~~java
@Bean
@StepScope
Tasklet importTasklet(
        @Value("#{jobParameters['sourceId']}") String sourceId,
        @Value("#{jobParameters['businessDate']}") String date,
        OrderImportService service) {

    return (contribution, chunkContext) -> {
        if (sourceId == null || sourceId.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing sourceId JobParameter");
        }
        LocalDate businessDate = LocalDate.parse(date);
        service.importSource(sourceId, businessDate);
        return RepeatStatus.FINISHED;
    };
}
~~~

Đây là ví dụ **Tasklet** đơn giản; ứng dụng cần bean `OrderImportService`, một Step sử dụng Tasklet, và cấu hình Job/JobRepository/transaction manager tương ứng. Import liên quan: `org.springframework.batch.core.configuration.annotation.StepScope`, `org.springframework.batch.core.step.tasklet.Tasklet`, `org.springframework.batch.repeat.RepeatStatus`, `org.springframework.beans.factory.annotation.Value`, `java.time.LocalDate`.

`@StepScope` bảo đảm giá trị được giải quyết **khi Step thực thi** và đã có `JobParameters`. Nếu tạo bean singleton và cố dùng `jobParameters` từ lúc khởi động context, expression có thể không có scope phù hợp.

**Chú ý giao dịch:** bước nhập dữ liệu thật thường dùng chunk-oriented processing với `ItemReader`, `ItemProcessor`, `ItemWriter` và `ExecutionContext` để có checkpoint; ví dụ Tasklet trên chỉ nhằm minh họa nhận tham số.

### 3.3. Kiểm soát khi có nhiều Job

Nếu ứng dụng có hai Job nhưng không truyền `spring.batch.job.name`, không nên kỳ vọng startup runner tự biết Job nào cần chạy. Trên các bản Boot hiện hành, trường hợp nhiều Job yêu cầu chỉ định Job; khi thiếu hoặc tên không hợp lệ, ứng dụng có thể lỗi ở bước khởi chạy.

Để vận hành dễ kiểm soát:

1. Đặt tên Job ổn định, khác nhau và phản ánh nghiệp vụ.
2. Truyền **tên Job** tại launcher, deployment hoặc lịch.
3. Truyền đủ JobParameters bắt buộc theo Job đã chọn.
4. Quan sát log Job được chạy cùng tên và bộ tham số identifying sau khi khởi động.
5. Khi Job thất bại, đảm bảo **mã thoát tiến trình** được phản ánh cho scheduler.

## 4. Cách B: chọn và chạy Job chủ động bằng JobLauncher

Nếu cần áp dụng quy tắc điều hướng phức tạp hơn như `--job=importOrdersJob`, kiểm tra whitelist theo người gọi hoặc ánh xạ tham số khác nhau theo Job, có thể **tắt Boot tự chạy Job** rồi tự viết runner để chọn:

~~~yaml
spring:
  application:
    name: controlled-batch-task
  main:
    web-application-type: none
  batch:
    job:
      enabled: false
  cloud:
    task:
      initialize-enabled: false
~~~

Khi `spring.batch.job.enabled=false`, Boot không tự chạy Job lúc startup; code của ứng dụng chịu trách nhiệm **chọn và gọi `JobLauncher` chính xác một lần**. Tránh bật auto-run đồng thời với runner tự gọi, nếu không cùng Job có thể bị chạy trùng hoặc xảy ra `JobExecutionAlreadyRunningException`.

Ví dụ điều hướng theo hai Job cố định, Spring Batch 5.x:

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchTaskDispatcher {

    @Bean
    ApplicationRunner launchSelectedJob(
            @Qualifier("importOrdersJob") Job importJob,
            @Qualifier("dailyReportJob") Job reportJob,
            JobLauncher jobLauncher) {

        return args -> {
            String requested = required(args, "job");
            String date = LocalDate
                    .parse(required(args, "business-date"))
                    .toString();

            Job selected = switch (requested) {
                case "importOrdersJob" -> importJob;
                case "dailyReportJob" -> reportJob;
                default -> throw new IllegalArgumentException(
                        "Unsupported job: " + requested);
            };

            JobParametersBuilder builder = new JobParametersBuilder()
                    .addString("businessDate", date, true)
                    .addString(
                            "requestedBy",
                            optional(args, "requested-by", "scheduler"),
                            false);

            if ("importOrdersJob".equals(requested)) {
                builder.addString(
                        "sourceId", required(args, "source-id"), true);
            }

            JobParameters parameters = builder.toJobParameters();
            JobExecution execution = jobLauncher.run(selected, parameters);

            // Mẫu này yêu cầu JobLauncher chạy đồng bộ.
            if (execution.isRunning()) {
                throw new IllegalStateException(
                        "JobLauncher returned before job completed");
            }
            if (execution.getStatus() != BatchStatus.COMPLETED) {
                throw new IllegalStateException(
                        "Batch job ended with " + execution.getStatus());
            }
        };
    }

    private static String required(
            ApplicationArguments args, String key) {

        List<String> values = args.getOptionValues(key);
        if (values == null || values.size() != 1 ||
                values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Expected one --" + key + "=value");
        }
        return values.get(0);
    }

    private static String optional(
            ApplicationArguments args, String key, String fallback) {
        if (!args.containsOption(key)) {
            return fallback;
        }
        return required(args, key);
    }
}
~~~

Chạy với **đối số ứng dụng** (khác cú pháp ở Cách A):

~~~bash
java -jar batch-task.jar \
  --job=importOrdersJob \
  --business-date=2026-11-23 \
  --source-id=partner-A \
  --requested-by=scheduler

java -jar batch-task.jar \
  --job=dailyReportJob \
  --business-date=2026-11-23
~~~

Trong cách này, `ApplicationArguments` đọc các option `--job`, `--business-date`, `--source-id`. Chương trình **tự xây dựng** `JobParameters` qua `JobParametersBuilder`. Không có bước chuyển đổi tự động từ các option `--business-date` thành Batch JobParameter nếu không viết mã như trên.

**Giới hạn quan trọng của ví dụ:** `JobLauncher` **không cam kết** thực thi đồng bộ trong mọi cấu hình. Ví dụ yêu cầu launcher trả về khi Job đã hoàn tất; nếu JobLauncher dùng executor bất đồng bộ, không được coi `run()` trả về là Job đã xong. Cần cấu hình JobLauncher đồng bộ cho tiến trình Task hữu hạn, hoặc có cơ chế chờ/quan sát JobExecution đến trạng thái kết thúc **trước khi Task thoát**, xử lý timeout và exception. Điều kiện `execution.isRunning()` ở ví dụ là phép kiểm tra phòng vệ, không thay thế một chiến lược chờ hoàn tất.

Ngoài ra, khi chọn Job bằng code, `spring.cloud.task.batch.fail-on-job-failure` của cơ chế tích hợp mặc định không phải lý do để bỏ qua việc kiểm tra `JobExecution`. Đoạn trên **tự ném exception** khi Job kết thúc không thành công để phần Task biết có lỗi.

## 5. JobParameters: identifying và non-identifying

`JobParameters` không chỉ là một `Map<String, String>`. Trong Spring Batch, mỗi tham số còn có **kiểu giá trị** và cờ **`identifying`**. Tập identifying cùng **Job name** xác định `JobInstance`.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-23", true)
        .addString("sourceId", "partner-A", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

| Tham số | Identifying? | Ý nghĩa |
| --- | --- | --- |
| `businessDate` | **true** | Chọn kỳ dữ liệu cần xử lý |
| `sourceId` | **true** | Chọn nguồn dữ liệu cần nhập |
| `requestedBy` | **false** | Ghi ai hoặc hệ thống nào yêu cầu chạy; không đổi danh tính JobInstance |

Ví dụ, lần 1 `requestedBy=scheduler`, lần restart `requestedBy=operator` vẫn chỉ tới **cùng JobInstance**, nếu tên Job và hai identifying params giữ nguyên. Thay `businessDate` hoặc `sourceId` sẽ tạo **JobInstance khác**.

### 5.1. Vì sao có thể dùng tham số non-identifying?

Một số thông tin hữu ích cho kiểm toán nhưng không xác định **bộ dữ liệu logic**:

- Tên hệ thống yêu cầu chạy (`requestedBy`).
- Mã yêu cầu vận hành (`requestId`), nếu mục tiêu là truy vết mà không thay JobInstance.
- Cờ hiển thị hoặc mức logging không ảnh hưởng tới tập dữ liệu nghiệp vụ.

Ngược lại, thông tin quyết định dữ liệu đầu vào như `sourceVersion` hoặc `tenantId` có thể cần identifying nếu chúng làm thay đổi tập dữ liệu mà Job xử lý. Lựa chọn phải xuất phát từ **quy tắc nghiệp vụ**, không phải vì một tham số “quan trọng” về mặt hiển thị.

### 5.2. Không tự thêm run.id ở mỗi lần retry

Một lỗi phổ biến là luôn thêm thời điểm hiện tại:

~~~java
// Cẩn thận: mặc định addLong sử dụng identifying = true.
new JobParametersBuilder()
        .addString("businessDate", "2026-11-23")
        .addLong("run.id", System.currentTimeMillis())
        .toJobParameters();
~~~

Mỗi lần thử có `run.id` khác sẽ tạo **JobInstance mới**, nên Spring Batch không còn coi đó là retry/restart của JobInstance trước, và checkpoint tương ứng có thể không được dùng lại. Chỉ tạo instance mới khi chủ đích là xử lý một lần logic khác; đừng dùng `run.id` để “né” lỗi `JobInstanceAlreadyCompleteException` mà chưa hiểu hậu quả.

### 5.3. Kiểu dữ liệu JobParameters

Trong API Spring Batch 5, `JobParametersBuilder` hỗ trợ nhiều kiểu như `String`, `Long`, `Double`, `Date` và khả năng chuyển đổi kiểu tùy phiên bản. Với ngày nghiệp vụ, truyền chuỗi ISO `yyyy-MM-dd` rồi parse ở Step giúp đơn giản hóa ví dụ, đồng thời tránh nhầm timezone với thời điểm UTC.

Có thể dùng tham số có kiểu cụ thể qua converter/CLI được phiên bản hỗ trợ. Với lệnh Boot startup runner, **cú pháp kiểu dữ liệu của Batch 5/6 không đồng nhất mọi phiên bản**; nên kiểm tra `JobParametersConverter` thực tế. Trong thực hành cơ bản, `businessDate=2026-11-23` được hiểu là tham số chuỗi và được kiểm tra bởi ứng dụng.

## 6. Chạy lại và xử lý khi Job đã hoàn thành

Spring Batch áp dụng các quy tắc quan trọng:

| Tình huống khi gọi cùng Job name | Identifying params | Kết quả điển hình |
| --- | --- | --- |
| Chưa có JobInstance | Mới | Tạo JobInstance và JobExecution mới |
| Lần trước FAILED, Job cho phép restart | Giữ nguyên | Tạo **JobExecution mới trên cùng JobInstance** |
| Lần trước COMPLETED | Giữ nguyên | Không cho chạy lại cùng JobInstance; có thể ném `JobInstanceAlreadyCompleteException` |
| Một JobExecution còn đang chạy | Giữ nguyên | Có thể ném `JobExecutionAlreadyRunningException` |
| Thay ngày hoặc sourceId identifying | Khác | Tạo **JobInstance mới** |
| Chỉ thay `requestedBy` non-identifying | Không đổi | Vẫn coi là cùng JobInstance; áp dụng quy tắc trạng thái trước |

Những quy tắc trên giả định **JobRepository là kho dùng chung, bền vững** và cấu hình nhận diện Job nhất quán. Nếu mỗi tiến trình dùng CSDL metadata riêng hoặc xóa bảng Batch, Spring Batch không thể nhận ra JobInstance cũ.

### 6.1. Restart phải giữ nguyên identifying params

Giả sử import tệp `partner-A` ngày 2026-11-23 bị lỗi khi đã đọc 70%:

~~~text
Lần 1:
  importOrdersJob
  businessDate=2026-11-23 (identifying)
  sourceId=partner-A        (identifying)
  requestedBy=scheduler     (non-identifying)
  JobExecution #501 = FAILED

Lần 2:
  importOrdersJob
  businessDate=2026-11-23 (identifying)
  sourceId=partner-A        (identifying)
  requestedBy=operator      (non-identifying)
  JobExecution #502 = COMPLETED
~~~

Nếu ItemReader/Step được thiết kế restartable và lưu checkpoint đúng cách, lần hai có thể đọc tiếp từ trạng thái trước. **Trùng JobInstance không tự đảm bảo exactly-once** đối với API bên ngoài hoặc các side effect không tham gia transaction. Vẫn cần khóa nghiệp vụ, idempotency key và chính sách retry.

Với cơ chế chạy từ CLI của Spring Boot, khi restart phải **truyền lại cả tham số identifying và non-identifying cần sử dụng**; không kỳ vọng runner tự sao chép toàn bộ non-identifying params từ lần trước.

### 6.2. Chạy lại một kỳ đã hoàn thành

Nếu báo cáo cho ngày 2026-11-23 đã `COMPLETED`, gọi lại cùng Job name và identifying params không phải cách mặc định để phát hành báo cáo lần nữa. Nếu nghiệp vụ thực sự cần phiên bản mới, hãy bổ sung một **tham số identifying có ý nghĩa**, ví dụ `reportVersion=2`, hoặc thiết kế quy trình rerun rõ ràng. Đừng âm thầm thay `run.id` ngẫu nhiên vì sẽ phá khả năng kiểm soát phiên bản nghiệp vụ.

## 7. Ranh giới giữa Task arguments và JobParameters

Khi chạy ứng dụng tích hợp Task–Batch có hai bộ tham số cần phân biệt:

| Dữ liệu | Ai nhận? | Lưu ở đâu? |
| --- | --- | --- |
| Raw arguments của tiến trình Java | Spring Boot / Spring Cloud Task | `TASK_EXECUTION_PARAMS` (các chuỗi đã truyền cho Task) |
| `spring.batch.job.name` | Spring Boot property để chọn Job auto-run | Nguồn cấu hình và có thể có trong task arguments khi truyền CLI |
| `JobParameters` | Spring Batch `JobLauncher` | `BATCH_JOB_EXECUTION_PARAMS` |
| Thông tin checkpoint | Spring Batch Step/Job | `BATCH_STEP_EXECUTION_CONTEXT`, `BATCH_JOB_EXECUTION_CONTEXT` |
| Trạng thái nghiệp vụ | Logic import/report | Bảng nghiệp vụ hoặc kho kết quả riêng |

Trong **Cách A**, `businessDate=...` dạng non-option được startup runner chuyển sang JobParameters. Trong **Cách B**, `--business-date=...` chỉ thành JobParameter khi **mã Java chủ động ánh xạ** qua `JobParametersBuilder`.

Không đồng nhất `TaskExecution ID` với `JobExecution ID`. Một lần chạy Task có thể liên kết với một hay nhiều JobExecution; các ID thuộc các repository khác nhau và không nhất thiết bằng nhau.

### 7.1. Liên kết TaskExecution với JobExecution

Khi có **`spring-cloud-task-batch`** và cơ chế liên kết `TaskBatchExecutionListener` được cấu hình thích hợp, Spring Cloud Task ghi quan hệ giữa TaskExecution và Batch JobExecution. Schema mặc định có bảng **`TASK_TASK_BATCH`** với hai cột:

- `TASK_EXECUTION_ID`.
- `JOB_EXECUTION_ID`.

Có thể truy vấn để điều tra:

~~~sql
SELECT t.TASK_EXECUTION_ID,
       t.TASK_NAME,
       l.JOB_EXECUTION_ID,
       i.JOB_NAME,
       e.STATUS
FROM TASK_EXECUTION t
JOIN TASK_TASK_BATCH l
  ON l.TASK_EXECUTION_ID = t.TASK_EXECUTION_ID
JOIN BATCH_JOB_EXECUTION e
  ON e.JOB_EXECUTION_ID = l.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE i
  ON i.JOB_INSTANCE_ID = e.JOB_INSTANCE_ID
WHERE t.TASK_EXECUTION_ID = :task_execution_id;
~~~

`:task_execution_id` là named parameter của JDBC/JPA client; khi chạy trực tiếp trong SQL console, thay bằng cú pháp placeholder được hỗ trợ. Truy vấn này giả định **TaskRepository và JobRepository nằm trong cùng DB/schema truy vấn được**; nếu chúng dùng hai DataSource khác nhau, cần tra cứu từng kho rồi đối chiếu ID ở tầng ứng dụng hoặc công cụ quản trị.

API `TaskExplorer.getJobExecutionIdsByTaskExecutionId(id)` cũng giúp tra danh sách JobExecution ID liên quan khi liên kết đang được lưu.

### 7.2. Truy vấn tham số ở JobRepository

Trong schema Spring Batch 5.x, có thể đối chiếu các tham số Job:

~~~sql
SELECT e.JOB_EXECUTION_ID,
       i.JOB_NAME,
       e.STATUS,
       p.PARAMETER_NAME,
       p.PARAMETER_VALUE,
       p.PARAMETER_TYPE,
       p.IDENTIFYING
FROM BATCH_JOB_EXECUTION e
JOIN BATCH_JOB_INSTANCE i
  ON i.JOB_INSTANCE_ID = e.JOB_INSTANCE_ID
LEFT JOIN BATCH_JOB_EXECUTION_PARAMS p
  ON p.JOB_EXECUTION_ID = e.JOB_EXECUTION_ID
WHERE e.JOB_EXECUTION_ID = :job_execution_id;
~~~

Cấu trúc cột khác nhau giữa các thế hệ Spring Batch; **kiểm tra DDL đúng phiên bản**. Nếu truy vấn trả nhiều hàng, đó thường là do một JobExecution có nhiều JobParameters.

## 8. Chọn Job khi khởi chạy theo lịch hoặc theo yêu cầu

Spring Cloud Task không tự lập lịch theo ngày. Một CronJob, scheduler hoặc API launcher bên ngoài có thể chọn Job và cung cấp kỳ dữ liệu cụ thể:

~~~text
Bộ điều phối theo lịch:
    Job name = dailyReportJob
    businessDate = 2026-11-23

Yêu cầu nhập dữ liệu:
    Job name = importOrdersJob
    businessDate = 2026-11-23
    sourceId = partner-A
~~~

Hai lựa chọn triển khai phổ biến:

**Một JAR, nhiều Job, tự chạy của Spring Boot:** mỗi lịch truyền `--spring.batch.job.name=<name>` và các JobParameters dạng `key=value`.

**Một JAR, tự dispatch bằng code:** mỗi lịch truyền `--job=<name>` và các option ứng dụng, sau đó một `ApplicationRunner` xây JobParameters và gọi `JobLauncher`.

Trong cả hai cách, bộ điều phối cần truyền ngày nghiệp vụ **cụ thể**. Tránh tham số mơ hồ `businessDate=today` khi muốn restart, bởi ngày thực tại thời điểm chạy lại có thể khác. Cần xác định timezone khi tính ngày báo cáo, rồi truyền giá trị ISO `yyyy-MM-dd` bất biến cho kỳ đó.

Nếu ứng dụng hỗ trợ nhiều tenant, phải quyết định `tenantId` có làm thay đổi danh tính JobInstance hay không; đa số trường hợp báo cáo tenant khác nhau cần được nhận diện tách biệt.

## 9. Xử lý lỗi và mã thoát của Spring Cloud Task

`JobExecution.getStatus()` có thể là `COMPLETED`, `FAILED`, `STOPPED` hoặc trạng thái trung gian. Đừng coi một lần gọi `JobLauncher.run()` không ném exception là Batch Job thành công: với launcher đồng bộ, **JobExecution có thể trả về ở trạng thái FAILED** khi lỗi xảy ra trong Step.

Mặc định, tiến trình Spring Boot chạy Batch Job có thể **kết thúc mã `0`** dù Batch Job có `BatchStatus.FAILED`. Khi dùng tích hợp Spring Cloud Task tương thích và cơ chế tự chạy Batch Job, cấu hình:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

để phản ánh thất bại của Job thành mã thoát Task khác `0`. Với launcher tự viết, hãy **chủ động kiểm tra trạng thái JobExecution** và phát ra tín hiệu lỗi đúng cho Task/lịch.

| Tình huống | Kết quả cần kiểm tra |
| --- | --- |
| Không tìm được Job đã chọn | Fail fast, ghi tên Job hợp lệ, không chạy Job khác |
| Thiếu JobParameter bắt buộc | Từ chối trước khi vào xử lý hoặc dùng JobParametersValidator |
| Cùng JobInstance đang chạy | Xử lý `JobExecutionAlreadyRunningException` theo chính sách retry phù hợp |
| JobInstance đã COMPLETED | Không âm thầm tạo bản khác bằng run.id ngẫu nhiên |
| Job bị lỗi giữa Step | `JobExecution.status`, lỗi và checkpoint, exit code Task |
| JobLauncher chạy bất đồng bộ | Theo dõi đến trạng thái kết thúc trước khi Task hữu hạn thoát |
| Task chết do bị kill | Kiểm tra trạng thái Pod/Job, JobRepository và TaskRepository; metadata có thể chưa được cập nhật cuối |

**Lưu ý riêng về runner:** `ApplicationRunner` và `CommandLineRunner` có thứ tự thực thi. Khi dùng auto-run và thêm runner nghiệp vụ, phải xác định runner nào xử lý tham số, runner nào khởi chạy Job và chúng có tương tác hay không. Không tạo thêm runner gọi `JobLauncher` nếu startup runner đã được bật và thực hiện cùng công việc.

## 10. Bảo mật và độ tin cậy khi truyền JobParameters

Cả Task arguments và Batch JobParameters có thể được lưu **bền vững** trong database và xuất hiện trong log. Không truyền mật khẩu, token, connection string chứa bí mật hoặc dữ liệu cá nhân nhạy cảm qua CLI/JobParameters.

Thay vì:

~~~bash
# Tránh: token có thể bị lưu trong Batch/Task metadata.
java -jar batch-task.jar --spring.batch.job.name=importOrdersJob \
  sourceId=partner-A apiToken=SECRET_VALUE
~~~

hãy dùng:

~~~bash
java -jar batch-task.jar --spring.batch.job.name=importOrdersJob \
  sourceId=partner-A credentialRef=partner-a-service
~~~

`credentialRef` chỉ là **khóa tham chiếu không bí mật** tới secret store có kiểm soát quyền; bước xử lý lấy credential từ kênh bảo mật. Nếu khóa tham chiếu cũng nhạy cảm, không ghi nó vào metadata/log công khai.

Các yêu cầu vận hành nên có:

- **Validation:** tên Job thuộc whitelist, `businessDate` parse được, `sourceId` đúng định dạng và giới hạn độ dài.
- **Idempotency:** ghi dữ liệu đích bằng unique constraint hoặc business key rõ ràng; JobInstance giúp restart nhưng không tự loại trừ mọi side effect.
- **Quyền database:** tài khoản Task/Batch chỉ có quyền cần thiết trên schema tương ứng; quản lý DDL qua migration.
- **Đối soát:** ghi nhận `TaskExecution ID`, `JobExecution ID`, job name, identifying params không nhạy cảm, tổng số đọc/ghi/từ chối và lý do lỗi.
- **Retention:** lưu metadata đủ lâu để restart và điều tra; không dọn lịch sử Batch JobInstance đang cần dùng để phục hồi.
- **Đồng thời:** khóa theo tên Task (nếu bật single-instance) khác với giới hạn JobInstance của Spring Batch và khóa nghiệp vụ; kiểm thử khi có nhiều Pod.

## 11. Kịch bản kiểm chứng thực tế

Có thể kiểm tra bằng một CSDL thử nghiệm, đã tạo schema Task và Batch phù hợp với phiên bản thư viện.

| Thử nghiệm | Thực hiện | Kết quả kỳ vọng |
| --- | --- | --- |
| **A. Chọn đúng Job** | Gọi `--spring.batch.job.name=importOrdersJob` | Chỉ Job import được tự khởi chạy |
| **B. Chọn Job báo cáo** | Gọi `--spring.batch.job.name=dailyReportJob` | Chỉ Job report được tự khởi chạy |
| **C. Thiếu tham số** | Bỏ `sourceId` của Job import | Không âm thầm nhập dữ liệu sai; Job lỗi rõ ràng |
| **D. Dùng sai tiền tố** | Truyền `--businessDate=2026-11-23` ở cách auto-run | Không có JobParameter theo cơ chế mặc định; quan sát và sửa cú pháp |
| **E. Chạy lại Job FAILED** | Giữ nguyên identifying params, thay requestedBy | Có JobExecution mới thuộc cùng JobInstance nếu Job restartable |
| **F. Chạy lại Job COMPLETED** | Giữ nguyên identifying params | JobRepository từ chối việc chạy lại cùng instance |
| **G. Đổi kỳ nghiệp vụ** | Đổi `businessDate` | Tạo JobInstance mới |
| **H. Tắt auto-run** | `spring.batch.job.enabled=false`, dùng dispatcher | Chỉ launcher chủ động chạy Job |
| **I. Lỗi Batch** | Chủ động làm Step thất bại | Scheduler nhận exit code khác 0 theo cấu hình / mã xử lý lỗi |
| **J. Truy vết** | Truy vấn `TASK_TASK_BATCH` và Batch repository | Tìm được JobExecution tương ứng TaskExecution khi listener liên kết bật |

Đối với thử nghiệm E, cần có Step thực sự restartable và có checkpoint đáng tin cậy. Không suy luận tính restart chỉ từ việc tạo lại JobParameters giống nhau.

### Bài tập: hệ thống nhập dữ liệu và phát hành báo cáo

Một hệ thống có hai Job:

- `importOrdersJob` nhập đơn hàng từ từng `sourceId` theo `businessDate`.
- `dailyReportJob` tổng hợp báo cáo theo `tenantId` và `businessDate`.

Hãy thực hiện:

1. Xác định JobParameters identifying của từng Job và thông tin non-identifying phù hợp.
2. Dùng `spring.batch.job.name` để tạo hai lệnh gọi startup-run riêng biệt.
3. Dùng `ApplicationRunner` và `JobLauncher` để hiện thực cùng thao tác chọn Job, nhưng với `spring.batch.job.enabled=false`.
4. Thêm `@StepScope` để đọc `businessDate` trong Step và kiểm tra giá trị.
5. Giả lập `importOrdersJob` lỗi giữa chừng. Chạy lại cùng identifying params và giải thích tại sao cần JobRepository bền vững.
6. Thử cố ý thêm `run.id=timestamp` vào mỗi lần retry. Quan sát JobInstance mới và giải thích vì sao có thể mất khả năng restart đúng.
7. Liên kết JobExecution với TaskExecution, tìm trạng thái cuối và xác nhận launcher phản ánh Job lỗi thành mã thoát phù hợp.

**Tiêu chí đạt:** phân biệt rõ `TaskExecution`, `Job`, `JobInstance`, `JobExecution`, `JobParameters`; chỉ ra được khác biệt giữa **`--spring.batch.job.name`** và **`businessDate=...`** ở cơ chế tự chạy, cũng như tác động của tham số identifying lên restart.

## 12. Tổng kết

1. Khi một ứng dụng có nhiều Batch Job, hãy **chọn Job rõ ràng** bằng `spring.batch.job.name` (cơ chế tự chạy của Boot) hoặc logic chọn Job cùng `JobLauncher` (cơ chế chủ động).
2. Với tự chạy của Spring Boot, **`--property=value` là cấu hình ứng dụng**, còn **`key=value` không có `--`** là cách truyền Batch JobParameters mặc định trên dòng lệnh.
3. Khi tự gọi `JobLauncher`, đặt `spring.batch.job.enabled=false` và tự chuyển các option ứng dụng thành `JobParameters`.
4. **`JobInstance = Job name + identifying JobParameters`**. Giữ nguyên identifying params để restart một JobInstance đã lỗi; thay chúng sẽ tạo instance mới.
5. Job đã hoàn thành thường **không được chạy lại với đúng identifying params**. Phát hành một phiên bản nghiệp vụ mới cần tham số định danh có ý nghĩa, không dùng random `run.id` để bỏ qua kiểm soát.
6. Spring Cloud Task và Spring Batch có **repository khác vai trò**. `TaskExecution` và `JobExecution` có thể được liên kết qua `TaskBatchExecutionListener`/`TASK_TASK_BATCH`.
7. Luôn kiểm tra **trạng thái Batch Job và mã thoát Task**, nhất là khi launcher bất đồng bộ hoặc runner mặc định không phản ánh lỗi Batch.

### Nguồn tham khảo chính thức

- [Spring Boot — Running Spring Batch Jobs on Startup](https://docs.spring.io/spring-boot/reference/io/spring-batch.html)
- [Spring Boot — Batch Applications / Running From the Command Line](https://docs.spring.io/spring-boot/how-to/batch.html)
- [Spring Cloud Task — Batch Integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/appendix-task-repository-schema.html)
- [Spring Batch — Domain Language: JobInstance và JobParameters](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch — Running a Job](https://docs.spring.io/spring-batch/reference/job/running.html)
