# Lịch chạy batch trong Spring Batch

**Lịch chạy batch** (*batch scheduling*) là cơ chế quyết định **khi nào** một công việc xử lý theo lô được khởi động: hằng ngày lúc 02:00, mỗi 15 phút, sau giờ đóng sổ, vào cuối tháng hoặc khi một công việc khác hoàn tất. Trong **Spring Batch Core Processing**, cần phân biệt hai trách nhiệm:

- **Bộ lập lịch (scheduler)** xác định thời điểm kích hoạt, quản lý trigger và có thể áp dụng chính sách không chạy chồng lấp, lịch ngày nghỉ hay chạy bù.
- **Spring Batch** thực thi `Job`/`Step`, quản lý `JobParameters`, trạng thái, transaction, metadata, restart, skip và retry trong quá trình xử lý.

Spring Batch **không tự đóng vai trò một hệ thống lập lịch hoàn chỉnh**. Ta có thể dùng `@Scheduled` của Spring Framework, Quartz, cron của hệ điều hành, Kubernetes CronJob hoặc một nền tảng orchestration để kích hoạt job. Lịch chạy nằm ở tầng điều phối; công việc thực thi nằm ở Spring Batch.

```text
             LỊCH CHẠY
    @Scheduled / Quartz / CronJob
                 |
          tạo JobParameters
                 |
                 v
          JobLauncher / JobOperator
                 |
                 v
            Spring Batch Job
                 |
        Step A -> Step B -> Step C
                 |
                 v
        JobRepository + database
        (metadata / trạng thái / restart)
```

Ví dụ một hệ thống kế toán có job tổng hợp giao dịch cuối ngày. Lúc 02:00 mỗi ngày, scheduler kích hoạt `dailySettlementJob` với tham số ngày nghiệp vụ; Spring Batch đọc các giao dịch, tính tổng, ghi kết quả và lưu trạng thái. Nếu job thất bại, chính sách **có chạy lại, khởi động lại từ checkpoint hay chờ xử lý thủ công** phải được thiết kế riêng. Việc có cron không tự giải quyết được vấn đề này.

## 1. Các hình thức lập lịch thường gặp

| Hình thức | Ví dụ nhu cầu | Cơ chế phù hợp |
| --- | --- | --- |
| Theo thời điểm trong ngày | 02:00 mỗi ngày | Cron expression |
| Theo ngày trong tuần | 08:30 từ thứ Hai đến thứ Sáu | Cron expression có ngày trong tuần |
| Theo khoảng thời gian cố định | 5 phút một lần kể từ thời điểm bắt đầu | `fixedRate` hoặc interval trigger |
| Chờ một lần chạy kết thúc rồi mới đợi tiếp | 10 phút sau khi tác vụ trước kết thúc | `fixedDelay` nếu lần gọi thực sự chờ job hoàn tất |
| Theo sự kiện | Sau khi file đầu vào đã có đủ dữ liệu | Event-driven orchestrator, message/event handler hoặc polling có kiểm soát |
| Theo lịch nghiệp vụ | Ngày làm việc cuối tháng, không tính ngày nghỉ | Scheduler hỗ trợ calendar, hoặc kiểm tra lịch nghiệp vụ trước khi launch |
| Phải chạy một lần trên nhiều máy | Một job cho mỗi kỳ báo cáo, trong cluster | Scheduler phân tán hoặc cơ chế khóa/nhận diện kỳ chạy đồng nhất |

Không phải mọi hệ thống cần một scheduler phức tạp. Ứng dụng chạy một instance, lịch đơn giản và không yêu cầu lưu các trigger bỏ lỡ có thể bắt đầu với `@Scheduled`. Khi yêu cầu có nhiều node, lịch bền vững qua restart, misfire policy hay điều phối dependency giữa nhiều job, một scheduler chuyên dụng thường phù hợp hơn.

## 2. Các thành phần cần hiểu

### `Job`, `JobInstance` và `JobExecution`

`Job` là định nghĩa công việc, ví dụ `dailySettlementJob`. Trong Spring Batch, **`JobInstance` được nhận diện bởi tên job và bộ `JobParameters` đánh dấu là identifying**. Mỗi lần thực thi của một instance là một `JobExecution`.

```text
Job: dailySettlementJob

JobParameters: businessDate=2026-11-16
                 |
                 v
       JobInstance của ngày 16/11
                 |
            JobExecution #1 (FAILED)
                 |
            JobExecution #2 (COMPLETED nếu restart)
```

Nếu dùng tham số identifying mới cho mỗi lần launch, Spring Batch coi đó là **JobInstance mới**; khi đó việc chạy lại không phải restart của instance cũ. Nếu chạy lại cùng tham số identifying sau khi instance đã `COMPLETED`, Spring Batch thường từ chối bằng `JobInstanceAlreadyCompleteException`. Hai hành vi này đặc biệt quan trọng với batch có lịch chạy định kỳ.

### `JobLauncher` và `JobOperator`

Trong các ứng dụng Spring Batch 5.x, `JobLauncher.run(job, jobParameters)` là API thường dùng để bắt đầu job. `JobOperator` cung cấp các thao tác vận hành cấp cao hơn như start, stop và restart. Phương thức và package liên quan có thay đổi theo phiên bản Spring Batch; cần dùng tài liệu tương ứng với dependency của dự án.

### `JobRepository`

`JobRepository` là kho metadata chứa thông tin `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` và trạng thái. Nó phục vụ kiểm soát việc khởi chạy lại và restart. **Đây không phải nơi lưu lịch cron hay các thời điểm trigger bị bỏ lỡ**; khả năng lưu trữ lịch thuộc scheduler đã chọn.

## 3. Cron expression trong `@Scheduled`

Spring Framework hỗ trợ cron expression gồm **sáu trường**, lần lượt là:

```text
 ┌──── giây        (0-59)
 │ ┌── phút        (0-59)
 │ │ ┌ giờ         (0-23)
 │ │ │ ┌ ngày      (1-31 hoặc * / ?)
 │ │ │ │ ┌ tháng   (1-12 hoặc JAN-DEC)
 │ │ │ │ │ ┌ thứ   (0-7 hoặc SUN-SAT; 0/7 là Chủ nhật)
 │ │ │ │ │ │
 0 0 2 * * *
```

Các lịch điển hình:

| Cron của Spring | Ý nghĩa |
| --- | --- |
| `0 0 2 * * *` | Hằng ngày lúc 02:00:00 |
| `0 */15 * * * *` | Mỗi 15 phút, tại giây 0 |
| `0 30 8 * * MON-FRI` | 08:30 từ thứ Hai đến thứ Sáu |
| `0 0 0 1 * *` | 00:00 ngày đầu mỗi tháng |
| `0 0 23 L * *` | 23:00 ngày cuối mỗi tháng, nếu phiên bản Spring cron đang dùng hỗ trợ `L` |

**Lưu ý:** cron của Linux thường có **năm trường** (phút, giờ, ngày, tháng, thứ), còn cron của Spring thêm **giây** ở đầu. Không sao chép biểu thức giữa hai nơi mà không kiểm tra cú pháp. Một lịch như `0 0 2 * * *` là 02:00 hằng ngày trong Spring, nhưng không phải biểu thức Linux crontab năm trường hợp lệ.

### Chỉ định múi giờ

```java
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void runEveryMorning() {
    // Kích hoạt job.
}
```

`zone` giúp lịch không phụ thuộc múi giờ mặc định của máy chạy ứng dụng. Nếu không chỉ định, lịch có thể thay đổi thời điểm thực tế khi container hoặc server chuyển sang múi giờ khác. Với vùng có daylight saving time (DST), các thời điểm bị nhảy qua hoặc lặp lại có thể khiến số lần trigger khác với trực giác; cần xác định chính sách lịch nghiệp vụ thay vì giả định mọi ngày đều có đúng 24 giờ.

## 4. Ví dụ: lập lịch một Spring Batch Job bằng `@Scheduled`

Ví dụ sau dành cho **Spring Boot 3.x + Spring Batch 5.x**, sử dụng Java 17+, Spring Scheduling và `JobLauncher`. Một job minh họa xử lý theo `businessDate` sẽ được kích hoạt mỗi ngày lúc 02:00 theo múi giờ Việt Nam.

### 4.1. Dependency

Với Gradle và Spring Boot BOM đang được cấu hình đúng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    // Database demo để lưu metadata BATCH_*; production thường dùng DB bền vững.
    runtimeOnly 'com.h2database:h2'
}
```

`@Scheduled` thuộc Spring Framework và được cung cấp qua các starter Spring phù hợp; với cấu hình Spring Boot Batch thông thường không cần thêm một thư viện scheduler riêng cho ví dụ này. H2 chỉ phục vụ minh họa. Ở production, cần database metadata có tính bền vững, nhất quán với transaction và khả năng restart của hệ thống.

### 4.2. Bật scheduling

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }
}
```

`@EnableScheduling` kích hoạt việc phát hiện các method có `@Scheduled` trong Spring context. Nếu thiếu annotation hoặc cơ chế kích hoạt tương đương, phương thức có `@Scheduled` sẽ không tự chạy theo lịch.

### 4.3. Khai báo job và step

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportJobConfiguration {
    private static final Logger log =
        LoggerFactory.getLogger(ImportJobConfiguration.class);

    @Bean
    public Job importOrdersJob(JobRepository repository, Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", repository)
            .start(importOrdersStep)
            .build();
    }

    @Bean
    public Step importOrdersStep(JobRepository repository,
                                 PlatformTransactionManager transactionManager) {
        return new StepBuilder("importOrdersStep", repository)
            .tasklet((contribution, chunkContext) -> {
                String businessDate = contribution.getStepExecution()
                    .getJobParameters().getString("businessDate");

                if (businessDate == null || businessDate.isBlank()) {
                    throw new IllegalArgumentException(
                        "Missing job parameter: businessDate");
                }

                log.info("Processing orders for businessDate={}", businessDate);
                // Ứng dụng thật: dùng reader/processor/writer hoặc gọi service.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }
}
```

`JobBuilder` và `StepBuilder` nhận trực tiếp `JobRepository`, phù hợp với cách cấu hình trong Spring Batch 5. Tasklet trên chỉ minh họa cơ chế nhận `JobParameters`; nó không đại diện cho quy trình nhập dữ liệu đầy đủ của sản phẩm thực tế.

### 4.4. Kích hoạt job vào thời điểm đã cấu hình

```java
package com.example.batch;

import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionException;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ImportOrdersScheduler {
    private static final Logger log =
        LoggerFactory.getLogger(ImportOrdersScheduler.class);

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;
    private final ZoneId zoneId;

    public ImportOrdersScheduler(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob,
            @Value("${batch.orders.zone:Asia/Ho_Chi_Minh}") String zone) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
        this.zoneId = ZoneId.of(zone);
    }

    @Scheduled(
        cron = "${batch.orders.cron:0 0 2 * * *}",
        zone = "${batch.orders.zone:Asia/Ho_Chi_Minh}"
    )
    public void launch() {
        LocalDate businessDate = LocalDate.now(zoneId);

        JobParameters parameters = new JobParametersBuilder()
            .addString("triggerId", UUID.randomUUID().toString())
            .addString("businessDate", businessDate.toString(), false)
            .toJobParameters();

        try {
            JobExecution execution = jobLauncher.run(importOrdersJob, parameters);

            log.info("Started batch executionId={}, businessDate={}, status={}",
                execution.getId(), businessDate, execution.getStatus());

            if (execution.getStatus() != BatchStatus.COMPLETED) {
                log.error("Batch did not complete successfully: executionId={}, status={}",
                    execution.getId(), execution.getStatus());
                // Production: gửi metric/cảnh báo và áp dụng chính sách retry.
            }
        } catch (JobExecutionException ex) {
            log.error("Unable to launch importOrdersJob for {}", businessDate, ex);
            // Production: ghi nhận trigger lỗi và cảnh báo cho vận hành.
        }
    }
}
```

Giải thích:

1. `@Scheduled` chỉ định **khi nào** gọi `launch()`. Để thay đổi lịch theo môi trường, dùng property `batch.orders.cron` thay vì sửa mã Java.
2. `@Qualifier("importOrdersJob")` xác định đúng bean `Job` khi ứng dụng có nhiều job.
3. `businessDate` là tham số nghiệp vụ; ở ví dụ nó được đánh dấu `identifying=false`, còn `triggerId` ngẫu nhiên là identifying parameter. Như vậy **mỗi lần cron kích hoạt được coi là JobInstance mới**. Cách này thuận tiện cho demo, nhưng chưa đáp ứng yêu cầu *mỗi kỳ nghiệp vụ chỉ chạy một lần* nếu chạy nhiều instance ứng dụng.
4. `JobLauncher.run(...)` tạo và thực thi job. Với launcher đồng bộ thông dụng, phương thức trả về khi job đã kết thúc; với launcher cấu hình bất đồng bộ, nó có thể trả về khi công việc mới bắt đầu. Vì vậy không được suy luận từ thời điểm method `launch()` trả về rằng job luôn đã hoàn tất.
5. Không phải mọi thất bại của step đều được `JobLauncher.run(...)` ném thành exception. Job có thể trả một `JobExecution` ở trạng thái `FAILED`; do đó cần kiểm tra `BatchStatus`/`ExitStatus` và các failure exception của execution để ghi nhận kết quả vận hành.
6. `try/catch` ở đây phục vụ log và cảnh báo khi không khởi chạy được. Cơ chế retry có giới hạn, xử lý failed instance và thông báo vận hành cần thiết kế riêng.

### 4.5. Cấu hình `application.yml`

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always # chỉ dùng như ví dụ cho DB thử nghiệm

batch:
  orders:
    cron: "0 0 2 * * *"
    zone: "Asia/Ho_Chi_Minh"
```

`spring.batch.job.enabled=false` **ngăn Spring Boot tự chạy batch job ngay khi ứng dụng khởi động**. Nếu bỏ cấu hình này, trong môi trường có job được đăng ký, Boot có thể chạy job một lần lúc startup bên cạnh các lần chạy theo `@Scheduled`, gây xử lý ngoài dự kiến.

`spring.batch.jdbc.initialize-schema=always` là cấu hình minh họa cho database thử nghiệm. Trong production, quản lý schema `BATCH_*` bằng migration hoặc quy trình vận hành phù hợp; không bật tạo schema một cách tùy tiện cho database dùng chung.

**Quan trọng:** nếu ứng dụng chỉ là tiến trình chạy một job rồi thoát, `@Scheduled` trong tiến trình đó không phù hợp. Scheduler phải tồn tại để chờ thời điểm trigger. Với tiến trình batch ngắn sống theo mỗi lần chạy, dùng cron/Kubernetes CronJob hoặc orchestration bên ngoài để khởi động tiến trình đúng lúc.

## 5. Cron, `fixedRate` và `fixedDelay` khác nhau thế nào?

Spring hỗ trợ nhiều dạng `@Scheduled`:

```java
// Theo đồng hồ: 02:00 mỗi ngày trong múi giờ chỉ định.
@Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
public void cronTrigger() { /* launch job */ }

// Theo chu kỳ kể từ các mốc bắt đầu dự kiến.
@Scheduled(fixedRate = 300_000)
public void fixedRateTrigger() { /* launch job */ }

// Đợi 5 phút sau khi lần gọi trước hoàn tất mới gọi tiếp.
@Scheduled(fixedDelay = 300_000)
public void fixedDelayTrigger() { /* launch job */ }
```

| Cơ chế | Cách xác định lần tiếp theo | Tình huống phù hợp |
| --- | --- | --- |
| `cron` | Mốc giờ/ngày cụ thể trong lịch | Báo cáo ngày, đóng sổ, cuối tháng |
| `fixedRate` | Khoảng thời gian cố định giữa các lần bắt đầu được lên lịch | Polling đều đặn, nhiệm vụ ngắn, cần chú ý chạy chồng |
| `fixedDelay` | Khoảng nghỉ sau khi **method đã thực thi xong** | Xử lý lặp và cần giãn cách sau mỗi lần hoàn tất |

Với `fixedDelay`, nếu method chỉ **gửi một job sang executor bất đồng bộ rồi lập tức trả về**, khoảng delay được đo sau khi *method gửi job* hoàn tất, **không** phải sau khi batch job thực sự hoàn tất. Tương tự, `fixedRate` hoặc cron cũng không tự bảo đảm job cũ đã xong trước job mới.

Ngay cả khi scheduler chạy trên một thread, điều đó chỉ có thể giúp các lời gọi `@Scheduled` trong cùng tiến trình không chồng lấp về mặt method. Không nên dựa vào nó để bảo đảm không có hai `JobExecution` cùng chạy trên các instance ứng dụng hoặc sau một lần launch bất đồng bộ.

## 6. Thiết kế `JobParameters` theo kỳ chạy

Lập lịch batch thường gắn với **kỳ dữ liệu**: ngày giao dịch, tháng báo cáo, `windowStart/windowEnd` hoặc mã file cần nhập. Vì vậy điều quan trọng không chỉ là trigger chạy lúc mấy giờ, mà còn là job được yêu cầu xử lý **dữ liệu của kỳ nào**.

### Cách A: mỗi trigger là một job instance độc lập

```java
JobParameters params = new JobParametersBuilder()
    .addString("triggerId", UUID.randomUUID().toString())
    .addString("businessDate", "2026-11-16", false)
    .toJobParameters();
```

Ưu điểm: scheduler có thể launch lần mới mà không vướng một instance đã hoàn tất. Hạn chế: nếu chạy hai trigger cho cùng `businessDate`, Spring Batch coi đó là **hai instance** và vẫn có thể xử lý trùng dữ liệu. Muốn chống trùng cần thêm idempotency ở tầng nghiệp vụ hoặc điều phối.

### Cách B: kỳ nghiệp vụ định danh job instance

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16") // identifying mặc định
    .toJobParameters();
```

Với tên job không đổi, ngày `2026-11-16` nhận diện một instance duy nhất. Nếu job chạy thành công, một yêu cầu launch khác với cùng tham số có thể bị từ chối là đã hoàn tất. Nếu job trước đó thất bại hoặc dừng và được phép restart, việc chạy với cùng identifying parameters có thể tạo một **JobExecution mới thuộc cùng JobInstance**. Chính sách này phù hợp với bài toán xử lý một kỳ dữ liệu và cần kiểm soát chạy lại.

**Lưu ý về restart:** không tự thêm `UUID` vào identifying parameters khi mục tiêu là **tiếp tục lần chạy thất bại**. Việc thêm UUID sẽ chuyển sang một JobInstance khác và có thể khiến dữ liệu đã xử lý trước đó bị xử lý lại. Một lần *rerun từ đầu* sau thành công cũng khác với *restart từ checkpoint*; cần phân định rõ cho vận hành.

### Cách xác định ngày nghiệp vụ

Không phải job chạy lúc 02:00 ngày 17/11 đều xử lý dữ liệu ngày 17/11. Ví dụ job đóng sổ sau nửa đêm có thể xử lý **ngày trước đó**:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.now(zone).minusDays(1);
```

Quy tắc chọn `businessDate` nên dựa trên hợp đồng dữ liệu và cutoff nghiệp vụ. Với chạy bù (backfill), truyền ngày hoặc khoảng thời gian **tường minh** qua parameters, không dựa hoàn toàn vào `LocalDate.now()` vì nó sẽ tạo ra kỳ dữ liệu sai khi chạy lại ngày hôm sau.

## 7. Tránh hai lần batch chạy chồng lấp

Một job mất 90 phút nhưng lịch kích hoạt mỗi giờ có thể sinh ra hai lần chạy cùng lúc. Hậu quả có thể là đọc trùng input, khóa bảng, ghi đè output hoặc tranh chấp checkpoint.

```text
01:00  Job A bắt đầu ───────────────────────> 02:30 kết thúc
02:00  Trigger tiếp theo ──> Job B bắt đầu ?
                            |
                Cần chính sách chạy đồng thời
```

Có bốn chiến lược thường gặp:

1. **Bỏ qua trigger khi đang chạy:** phù hợp khi dữ liệu mới có thể được xử lý trong kỳ tiếp theo; cần log rõ kỳ đã bị bỏ qua và theo dõi backlog.
2. **Xếp hàng chờ:** trigger mới được giữ lại để chạy sau khi job cũ hoàn tất; cần giới hạn độ dài hàng đợi và khả năng chạy bù.
3. **Cho chạy song song có kiểm soát:** chỉ khi mỗi execution xử lý dữ liệu/partition độc lập và writer, database, output path an toàn cho concurrency.
4. **Từ chối chạy trùng kỳ:** dùng identifying `JobParameters` thống nhất cho cùng kỳ và cơ chế scheduling/locking phù hợp; tránh tạo một UUID mới cho mỗi node nếu mục tiêu là đúng một kỳ chỉ xử lý một lần.

Với một ứng dụng có nhiều instance, `@Scheduled` trên mỗi instance có thể **kích hoạt cùng một method trên tất cả các node**. `JobRepository` có thể giúp ngăn đồng thời hai execution của *cùng JobInstance*, nhưng không tự ngăn hai lần chạy với `JobParameters` khác nhau. Ngoài ra, nó không phải một hệ thống cluster-wide trigger election. Khi cần bảo đảm chỉ một node điều phối mỗi lần, dùng một scheduler phân tán như Quartz JDBC clustering, hệ thống orchestration chỉ phát một trigger hoặc cơ chế distributed lock có giới hạn thời gian và xử lý khi tiến trình chết.

Có thể quan sát job đang chạy qua `JobExplorer` (ví dụ `findRunningJobExecutions(jobName)` trong API phù hợp với phiên bản). Tuy nhiên, **kiểm tra rồi mới launch** gồm hai thao tác riêng, có thể bị race condition nếu nhiều node cùng kiểm tra; do đó chỉ kiểm tra trạng thái không đủ để xây dựng bảo đảm exactly-once.

### Exactly-once và idempotency

Lịch chạy một lần không đồng nghĩa dữ liệu chỉ bị tác động một lần. Scheduler có thể retry sau lỗi mạng, job có thể được restart, và cùng một message/file có thể được xử lý lại. Hãy thiết kế idempotency bằng khóa nghiệp vụ, ràng buộc unique, trạng thái kỳ chạy hoặc logic upsert phù hợp. Đối với file đầu ra, có thể ghi vào file tạm rồi publish kết quả cuối một cách có kiểm soát để tránh lộ file dở dang.

## 8. Điều gì xảy ra khi ứng dụng tắt đúng thời điểm lịch chạy?

`@Scheduled` là lập lịch **trong tiến trình ứng dụng đang hoạt động**. Nếu ứng dụng tắt lúc 02:00, nó không tự ghi lại trigger bị lỡ để bảo đảm chạy bù khi khởi động vào 03:00. Sau khi restart, scheduler tiếp tục tính các mốc lịch tiếp theo theo cấu hình. Metadata Spring Batch cũng chỉ biết những execution đã thực sự được tạo.

Điều này dẫn tới ba yêu cầu vận hành:

- Có **record kỳ dữ liệu phải xử lý** (ví dụ bảng `batch_schedule_period`) hoặc nguồn sự thật về các kỳ đến hạn.
- Có cơ chế **reconciliation/catch-up** để phát hiện kỳ chưa hoàn tất và tạo yêu cầu chạy bù đúng parameters.
- Có dashboard/alert theo **kỳ nghiệp vụ mong đợi**, không chỉ đếm số execution đã xảy ra. Nếu thiếu hẳn một execution, dashboard chỉ xem `JobRepository` có thể không phát hiện được.

Nếu cần trigger bền vững và misfire policy, Quartz JDBC JobStore hoặc nền tảng scheduler bên ngoài thích hợp hơn. Chúng có thể ghi nhận trigger còn chờ và quyết định xử lý sau downtime theo cấu hình; chính sách chạy bù vẫn phải gắn với bài toán dữ liệu cụ thể.

## 9. Chọn công cụ lập lịch phù hợp

### 9.1. `@Scheduled` của Spring

Phù hợp với ứng dụng Spring chạy liên tục, một node hoặc đã có cơ chế điều phối riêng, lịch không quá phức tạp. Dễ viết code, đặt cron trong property và dùng cùng Spring context với các `Job`.

Giới hạn: trigger sống trong tiến trình; không có bảng lịch bền vững, giao diện quản trị trigger hay cơ chế cluster/leader election mặc định. Đổi cron thường cần cập nhật cấu hình và làm mới ứng dụng theo cơ chế deployment.

### 9.2. Quartz Scheduler

Quartz hỗ trợ cron trigger, calendar, misfire instruction, persistent job/trigger store và clustering khi cấu hình đúng. Có thể tạo một Quartz `Job` làm adapter, chuyển `JobDataMap` sang `JobParameters`, sau đó gọi Spring Batch launcher/operator.

```text
Quartz Trigger -> Quartz Job adapter -> Spring Batch Job
       |                                    |
Quartz JobStore                    Spring Batch JobRepository
```

**Hai repository có trách nhiệm khác nhau:** Quartz lưu lịch/trigger và trạng thái scheduler; Spring Batch lưu metadata execution, checkpoint và restart. Không dùng Quartz `JobDataMap` như thay thế `ExecutionContext` của Batch, cũng không hiểu `JobRepository` là nơi Quartz lưu cron.

### 9.3. Kubernetes CronJob

Phù hợp khi batch được đóng gói trong container chạy xong rồi thoát. Kubernetes tạo một Kubernetes Job/Pod cho từng lịch, còn ứng dụng trong Pod sẽ chạy **một batch job** và thoát. Các tùy chọn như `concurrencyPolicy`, lịch, số job history được giữ và deadline giúp điều phối tiến trình. Khi muốn tránh chồng lấp các lần chạy của **cùng CronJob**, có thể dùng `concurrencyPolicy: Forbid`.

Ví dụ minh họa cấu hình hạ tầng:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: import-orders
spec:
  schedule: "0 2 * * *" # Kubernetes cron: 5 trường
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: import-orders
              image: example/import-orders:1.0.0
              args: ["--spring.batch.job.name=importOrdersJob"]
```

Mẫu YAML chỉ minh họa scheduling; image phải tồn tại, ứng dụng phải có cơ chế chạy job khi container khởi động và kết thúc process với exit code phù hợp. Tên property/entrypoint để chọn job còn phụ thuộc Spring Boot version và cách ứng dụng launch batch; nếu ứng dụng đang đặt `spring.batch.job.enabled=false` thì phải thiết kế lại điểm khởi chạy cho mô hình CronJob. Trong mô hình này không cần thêm `@Scheduled` cho cùng job vì có thể gây kích hoạt hai lần.

Kubernetes CronJob hỗ trợ timezone qua `.spec.timeZone` trên những phiên bản Kubernetes có tính năng này; biểu thức `schedule` của Kubernetes có **năm trường**, khác biểu thức Spring sáu trường.

### 9.4. Cron hệ điều hành và nền tảng orchestration

Linux cron có thể gọi một command hoặc script khởi chạy ứng dụng batch. Airflow, Control-M và các orchestrator tương tự hữu ích khi cần DAG, dependency giữa job, lịch nghiệp vụ phức tạp, quan sát nhiều hệ thống và khả năng chạy bù theo khoảng dữ liệu. Dù chọn công cụ nào, Spring Batch vẫn chịu trách nhiệm processing và lưu execution metadata.

| Lựa chọn | Ưu điểm chính | Điều cần lưu ý |
| --- | --- | --- |
| `@Scheduled` | Ít thành phần, phù hợp ứng dụng chạy liên tục | Không có durable trigger/cluster coordination mặc định |
| Quartz | Trigger linh hoạt, JDBC store, misfire và clustering | Cần cấu hình, lưu trữ và vận hành Quartz riêng |
| Kubernetes CronJob | Dễ tích hợp deployment container, tạo Pod theo lịch | Job phải biết chạy và thoát; cần xử lý missed schedules, concurrency và parameters |
| OS cron | Đơn giản với script/job độc lập | Theo dõi lỗi, retry, log và chạy nhiều máy cần tổ chức riêng |
| Orchestrator | Quản lý dependency, dữ liệu theo kỳ và backfill | Hạ tầng và quy trình vận hành phức tạp hơn |

## 10. Xử lý lỗi, retry và restart khi có lịch

Khi scheduler kích hoạt thành công nhưng step gặp lỗi, ta có một **job execution thất bại**. Khi scheduler không thể gọi launcher, đó là **lỗi khởi chạy**. Khi tiến trình tắt trước thời điểm trigger, đó là **lần chạy bị bỏ lỡ**. Ba trường hợp này cần chính sách xử lý khác nhau.

### Lỗi trong quá trình chạy job

Nếu job `FAILED`, kiểm tra `StepExecution` và failure exception để xác định lỗi. Với các lỗi tạm thời ở item, chính sách `retry` của Spring Batch xử lý tại step là một phương án. Với lỗi khiến cả job thất bại, cần quyết định khi nào restart và liệu dữ liệu đã commit trước đó có thể an toàn được tiếp tục.

### Restart và run mới

Trong Spring Batch, **restart** tiếp tục một `JobInstance` từ trạng thái trước đó theo metadata và cấu hình step. Để restart đúng instance, phải giữ repository/context và dùng định danh phù hợp; có thể sử dụng API `JobOperator.restart(executionId)` trong các phiên bản hỗ trợ. Một lần `run(...)` với `triggerId` mới là một **instance mới**, kể cả khi cùng ngày nghiệp vụ.

### Retry ở tầng scheduler

Scheduler có thể thử lại sau thời gian chờ nếu không khởi chạy được do hạ tầng. Tuy nhiên, retry không được tự động đồng nghĩa tạo một `JobInstance` mới và xử lý trùng dữ liệu. Với lịch theo kỳ, nên ghi nhận kỳ chưa hoàn tất rồi chọn rõ thao tác `restart` hoặc chạy mới có chủ đích.

### Dừng hoặc quá thời gian xử lý

Theo dõi duration và đặt ngưỡng cảnh báo nếu job lâu hơn bình thường. Khi cần dừng batch an toàn, dùng cơ chế stop của Spring Batch và để step phản hồi; việc kill Pod/process có thể làm mất cơ hội shutdown sạch, nên checkpoint và idempotency phải được thiết kế để phục hồi khi chạy lại.

## 11. Các mốc giờ, kỳ dữ liệu và lịch nghiệp vụ

Ví dụ một job chạy lúc 02:00 sáng, xử lý giao dịch ngày hôm trước:

```text
Ngày xử lý (runtime):    2026-11-17, 02:00 Asia/Ho_Chi_Minh
Kỳ dữ liệu (business):   2026-11-16, 00:00 đến hết ngày
Input:                   orders/businessDate=2026-11-16/
Output:                  settlement/2026-11-16.csv
JobParameters:           businessDate=2026-11-16
```

Nên tách rõ:

- **Trigger time:** lúc scheduler kích hoạt.
- **Execution time:** lúc job thật sự bắt đầu và kết thúc; có thể muộn hơn trigger vì chờ tài nguyên.
- **Business date/window:** khoảng dữ liệu job xử lý; có thể là ngày hôm qua, tuần trước hoặc một cửa sổ bị backlog.

Đối với batch tài chính, cân đối tồn kho hoặc báo cáo, không nên suy ra kỳ dữ liệu từ thời điểm job kết thúc. Nếu job khởi chạy muộn qua nửa đêm, cách suy luận đó có thể làm đổi kỳ khi job còn chạy. Nên tính kỳ ngay lúc tạo parameters hoặc lấy từ orchestrator và truyền bất biến cho execution.

Khi nghiệp vụ chỉ hoạt động theo ngày làm việc, cron theo thứ Hai–thứ Sáu chưa đủ để loại trừ ngày lễ hay các ngày nghỉ đặc thù. Dùng lịch nghiệp vụ được quản lý hoặc service tính ngày làm việc và kiểm tra trước khi launch. Trong khi chạy bù, cần cho phép chỉ định kỳ rõ ràng thay vì dùng ngày máy chủ mặc định.

## 12. Giám sát lịch chạy và trạng thái job

Một lịch chạy có giá trị vận hành khi có thể trả lời: **lần chạy nào đáng lẽ phải xảy ra, lần nào thực tế đã xảy ra và kết quả ra sao?**

Các trường nên quan sát:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `jobName` | Job được lập lịch |
| `businessDate` hoặc `windowStart/windowEnd` | Kỳ dữ liệu được xử lý |
| `scheduledAt` | Mốc trigger theo kế hoạch |
| `launchedAt` | Thời điểm launcher được gọi |
| `executionId` | Định danh `JobExecution` trong `JobRepository` |
| `BatchStatus`, `ExitStatus` | Trạng thái batch và exit code |
| Start/end time, duration | Phát hiện job chậm, treo hoặc lâu hơn SLA |
| Read/write/filter/skip counts | Theo dõi tính hợp lệ và chất lượng dữ liệu |
| Failure exception | Hỗ trợ điều tra và phân loại nguyên nhân lỗi |

Nên có cảnh báo tối thiểu cho các tình huống: kỳ dữ liệu quá hạn nhưng **không có execution**, execution `FAILED`/`STOPPED`, execution chạy quá lâu, tỉ lệ skip bất thường hoặc thiếu output. Ghi log theo `jobName`, `businessDate`, `executionId` để liên kết thông tin giữa scheduler và Spring Batch. Đối với monitoring, dùng Micrometer/Actuator theo cấu hình phù hợp của ứng dụng; không phụ thuộc hoàn toàn vào log khi cần theo dõi SLA.

## 13. Kiểm thử cơ chế lập lịch

Có thể chia kiểm thử thành ba phạm vi để tránh phải chờ đồng hồ chạy đến giờ cron:

1. **Test logic chuẩn bị parameters:** gọi trực tiếp service tính `businessDate`, đối chiếu timezone, ngày hôm trước, cuối tháng hoặc trường hợp chạy bù. Có thể inject `Clock` cố định để kết quả không phụ thuộc thời gian thật.
2. **Test mã kích hoạt:** gọi trực tiếp method/service launcher với `JobLauncher` giả lập rồi kiểm tra đúng `Job`, tên và identifying parameters được truyền; không cần đợi đến 02:00.
3. **Integration test batch job:** khởi chạy job thật trong Spring Test với database/file test, kiểm tra `JobExecution`, dữ liệu đầu ra và restart. Đây là kiểm thử nội dung xử lý, độc lập với việc cron có được kích hoạt đúng thời điểm hay không.

Nếu muốn kiểm tra chính cron expression, dùng các API lập lịch của Spring phù hợp phiên bản (ví dụ `CronExpression` trong Spring Framework) để tính những mốc kế tiếp từ thời điểm xác định. Kiểm thử thêm timezone, ngày cuối tháng và chuyển DST nếu vùng thời gian có DST.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân hay gặp | Hướng giải quyết |
| --- | --- | --- |
| Job chạy ngay khi ứng dụng khởi động dù chưa đến giờ | Spring Boot tự launch `Job` khi startup | Kiểm tra `spring.batch.job.enabled=false` trong mô hình `@Scheduled` |
| Method `@Scheduled` không chạy | Thiếu `@EnableScheduling`, bean không thuộc Spring context hoặc cron sai | Bật scheduling, kiểm tra component scan và property |
| Batch chạy sai giờ | Dùng timezone mặc định của host/container hoặc nhầm cron 5/6 trường | Chỉ định zone, xác nhận cú pháp Spring cron |
| Job chạy nhiều lần trong cùng một kỳ | Nhiều node cùng có `@Scheduled`, retry trigger hoặc tham số ngẫu nhiên | Dùng kỳ dữ liệu làm định danh khi phù hợp, scheduler phân tán và idempotency |
| `JobInstanceAlreadyCompleteException` | Cùng job name và identifying parameters đã `COMPLETED` | Xác định muốn bỏ qua, chạy kỳ mới hay rerun chủ đích |
| `JobExecutionAlreadyRunningException` | Cùng `JobInstance` vẫn đang chạy | Có chính sách overlap rõ ràng, không launch trùng instance |
| Job báo `FAILED` nhưng scheduler không bắt được exception | Launcher có thể trả `JobExecution` mang trạng thái thất bại | Kiểm tra `BatchStatus`/`ExitStatus`, log và alert |
| Bỏ lỡ lần chạy khi service downtime | `@Scheduled` không lưu trigger missed bền vững | Thêm reconciliation hoặc dùng scheduler durable |
| `fixedDelay` vẫn có hai job chạy đồng thời | Launcher bất đồng bộ trả về trước khi job hoàn tất | Quản lý concurrency ở cấp execution, không chỉ method |
| Job không restart đúng điểm | Thay identifying parameters hoặc metadata/context không được giữ | Thiết kế JobInstance theo kỳ, dùng repository bền vững và API restart |
| Job xử lý nhầm ngày sau nửa đêm | Lấy `LocalDate.now()` trong step tại thời điểm khác với trigger | Truyền `businessDate` rõ ràng trong JobParameters |

## 15. Một kịch bản vận hành mẫu

Giả sử hệ thống cần tổng hợp giao dịch ngày hôm trước vào 02:00 hằng ngày:

```text
Scheduler             Bộ điều phối                 Spring Batch
   |                       |                            |
   | 02:00: trigger        |                            |
   |---------------------->|                            |
   |                       | businessDate = hôm qua     |
   |                       | kiểm tra kỳ đã xử lý?      |
   |                       |--------------------------->|
   |                       |         launch             |
   |                       |                            | read/process/write
   |                       |                            | commit/checkpoint
   |                       |<---------------------------|
   |                       | JobExecution + status      |
   |                       |                            |
   |                       | ghi nhận / cảnh báo        |
```

Với yêu cầu **mỗi ngày đúng một kết quả**, thực tế nên thiết kế thêm ba thành phần: (1) bảng hoặc quy tắc xác định kỳ cần xử lý, (2) định danh job instance theo kỳ hoặc khóa điều phối tương đương, (3) quy trình phát hiện kỳ thiếu và chạy bù. Nếu job thất bại, có thể restart theo metadata và checkpoint; nếu cần làm lại dữ liệu đã hoàn tất, phải có cơ chế rerun có kiểm soát và bảo đảm kết quả đầu ra không bị nhân đôi.

Như vậy, lịch chạy batch không đơn thuần là một chuỗi cron. Một lịch ổn định cần liên kết **thời điểm kích hoạt, kỳ dữ liệu, tham số định danh, chính sách chồng lấp, phục hồi sau lỗi và khả năng quan sát** với đúng trách nhiệm của Spring Batch.

## Tài liệu tham khảo

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableScheduling`, `@Scheduled`, cron, fixed rate và fixed delay.
- [Spring Framework API — `CronExpression`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronExpression.html): cú pháp cron sáu trường và cách tính thời điểm tiếp theo.
- [Spring Batch Reference](https://docs.spring.io/spring-batch/reference/): mô hình `Job`, `JobInstance`, `JobExecution`, `JobParameters`, `JobRepository` và restart.
- [Spring Boot Reference — Spring Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): cấu hình khởi chạy job khi ứng dụng startup và Batch infrastructure.
- [Quartz Scheduler Documentation](https://www.quartz-scheduler.org/documentation/): trigger, job store, clustering và misfire handling.
- [Kubernetes Documentation — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): cron theo lịch, timezone và concurrency policy cho công việc container.
