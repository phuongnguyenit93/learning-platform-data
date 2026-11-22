# Đưa job vào scheduler trong Spring Batch: dự án thực hành từ cấu hình đến vận hành

Trong ứng dụng Spring Batch, việc chạy `Job` bằng tay trong IDE chỉ là bước đầu. Khi đưa vào vận hành, công việc thường cần **tự động khởi chạy theo một lịch**, chẳng hạn 02:15 mỗi ngày để nhập đơn hàng của ngày trước, 05:00 để đối soát giao dịch, hoặc cuối tháng để kết xuất báo cáo. Bài toán lúc này không chỉ là viết cron expression: hệ thống còn phải biết **chạy job nào**, **kỳ dữ liệu nào**, **làm gì nếu job đã chạy**, **tránh kích hoạt trùng**, **xử lý lịch bị bỏ lỡ** và **theo dõi kết quả**.

Bài thực hành này xây dựng một ứng dụng Spring Boot chạy `importOrders` theo lịch. Ta sẽ dùng `@Scheduled` để kích hoạt, `JobLauncher` để khởi chạy, `JobParameters` để định danh kỳ nghiệp vụ, và `JobRepository` để lưu metadata thực thi. Sau đó so sánh với Quartz, Kubernetes CronJob và scheduler bên ngoài để biết khi nào nên chuyển sang một giải pháp bền vững hơn.

**Mốc API:** ví dụ Java nhắm tới **Spring Batch 5.2.x, Spring Boot 3.4+/3.5.x và Java 17**. Các đoạn code tập trung vào phần scheduling nên step nghiệp vụ được minh họa bằng một `Tasklet`; trong dự án thật có thể thay bằng chunk step với `ItemReader`/`ItemProcessor`/`ItemWriter`. Đừng trộn mã Spring Batch 5.x với import/API của Spring Batch 6.x mà không đối chiếu lại.

## 1. Hiểu ba thành phần trước khi lập lịch

Một công việc batch được kích hoạt bởi **scheduler**, nhưng được **Spring Batch** quản lý thực thi.

```text
                 Đồng hồ / Cron / Event
                          |
                          v
                       Scheduler
             (quyết định KHI NÀO chạy)
                          |
                          v
                    Launch service
          (chọn job, dựng JobParameters)
                          |
                          v
                      JobLauncher
               (bắt đầu JobExecution)
                          |
              +-----------+-----------+
              |                       |
              v                       v
          Job/Step               JobRepository
       (xử lý nghiệp vụ)      (metadata, status,
                                checkpoint)
              |
              v
          JobExecution
      (COMPLETED/FAILED/...)
                          |
                          v
                  Logs / Dashboard
```

| Thành phần | Trả lời câu hỏi | Không nên gánh nhiệm vụ gì? |
| --- | --- | --- |
| `@Scheduled`/`TaskScheduler`/Quartz/CronJob | **Khi nào** kích hoạt? | Không thay thế transaction và checkpoint của Batch |
| `JobLauncher` | Bắt đầu thực thi một `Job` với `JobParameters` nào? | Không quyết định lịch chạy nghiệp vụ |
| `Job` và `Step` | Xử lý dữ liệu, trạng thái xử lý, retry/skip/restart? | Không tự lưu lịch phải chạy vào ngày nào |
| `JobRepository` | Instance/execution nào đã được ghi nhận? | Không biết một kỳ “đáng lẽ phải chạy” nếu scheduler chưa tạo execution |
| `JobExplorer` | Đọc lịch sử/trạng thái từ repository | Không tự chứng minh worker còn sống chỉ vì status là `STARTED` |
| Orchestrator/SLA registry | Kỳ nào dự kiến chạy, deadline và phụ thuộc? | Không tự hoàn tác side effect nghiệp vụ đã commit |

**Nguyên tắc:** scheduler chỉ phát lệnh khởi chạy; `JobRepository` là nguồn trạng thái của các execution đã tồn tại. Nếu scheduler không kích hoạt, có thể **không có bản ghi lỗi nào trong repository**. Vì vậy production còn cần giám sát *missing run*, không chỉ giám sát `FAILED`.

## 2. Yêu cầu của dự án thực hành

Giả sử có quy trình `importOrders`:

- Mỗi ngày lúc **02:15** theo múi giờ `Asia/Ho_Chi_Minh`, xử lý đơn hàng của **ngày trước đó**.
- Tên job là `importOrders`; `businessDate` xác định kỳ dữ liệu được xử lý.
- Một kỳ đã `COMPLETED` thì cron kích hoạt lần nữa **không được nạp trùng**.
- Nếu lần chạy trước `FAILED` và điều kiện restart cho phép, lần tiếp theo với **cùng identifying parameters** được xử lý theo chính sách restart.
- Không tự chạy job khi Spring Boot khởi động ứng dụng chỉ vì context có một bean `Job`.
- Có log chứa `businessDate`, `jobExecutionId` và status; có hướng giám sát, backfill và xử lý lỗi.
- Cấu hình local dùng H2 cho dễ thử; production cần database metadata bền vững (thường PostgreSQL hoặc database mà tổ chức hỗ trợ).

Phạm vi phần thực hành:

```text
src/main/java/com/example/batch/
    BatchSchedulerApplication.java
    config/BatchClockConfig.java
    config/ImportOrdersJobConfig.java
    service/ImportOrdersLaunchService.java
    schedule/ImportOrdersSchedule.java

src/main/resources/
    application.yml

src/test/java/com/example/batch/
    ImportOrdersLaunchServiceTest.java
```

Ta sẽ triển khai từng phần. Trong ví dụ, step chỉ ghi log; mục tiêu là quan sát cách scheduler và Batch phối hợp. Khi nối với dữ liệu thật, hãy thay nội dung tasklet bằng reader/processor/writer được cấu hình transaction và idempotency phù hợp.

## 3. Dependencies và cấu hình Spring Boot

Ví dụ Gradle dùng Spring Boot dependency management đã có ở project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dependency `spring-boot-starter-batch` cung cấp hạ tầng Spring Batch, `spring-boot-starter-jdbc` hỗ trợ datasource/JDBC và transaction. Một số dependency có thể đã được starter Batch kéo theo; đoạn trên nêu tường minh những thành phần dùng trong bài. H2 chỉ phù hợp demo/test; trong production thay bằng JDBC driver và database đã được vận hành/backup.

Cấu hình `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: orders-batch

  datasource:
    url: jdbc:h2:mem:ordersbatch;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

app:
  batch:
    import-orders:
      cron: "0 15 2 * * *"
      zone: "Asia/Ho_Chi_Minh"
```

Hai property quan trọng:

- `spring.batch.job.enabled=false`: ngăn cơ chế tự động chạy job của Spring Boot lúc ứng dụng khởi động. **Không tắt bean Job hoặc JobLauncher**. Scheduler của ta sẽ chủ động gọi `JobLauncher`.
- `spring.batch.jdbc.initialize-schema=always`: tạo bảng metadata Spring Batch trong H2 demo khi ứng dụng start. **Không mặc định dùng `always` trên database production**, nơi schema cần được quản lý và nâng cấp bằng migration có kiểm soát.

H2 in-memory **không giữ metadata sau khi JVM thoát**. Vì thế bài demo có thể thể hiện việc cron kích hoạt và `JobInstanceAlreadyCompleteException` trong cùng lần chạy ứng dụng, nhưng **không kiểm chứng restart qua lần khởi động JVM mới**. Muốn thử restart bền vững phải dùng repository trên database có lưu trữ thực sự.

### Spring Boot tự chạy job và scheduler là hai cơ chế khác nhau

Không bật `spring.batch.job.enabled=true` rồi thêm `@Scheduled` cho cùng job nếu mục tiêu là chỉ chạy đúng lịch. Cách đó có thể làm job chạy **một lần ngay khi startup** và **nhiều lần theo cron**, dẫn tới trùng trigger hoặc thông số kỳ dữ liệu không như mong muốn.

Bài này dùng Spring Boot auto-configuration của Batch; **không cần thêm `@EnableBatchProcessing`** chỉ để scheduler hoạt động. Ở Spring Boot 3.x, việc thêm annotation đó có thể làm thay đổi phạm vi Batch auto-configuration nên nên chỉ dùng khi chủ động cấu hình hạ tầng.

## 4. Bật scheduling trong ứng dụng

Tạo entrypoint:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class BatchSchedulerApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchSchedulerApplication.class, args);
    }
}
```

`@EnableScheduling` cho phép Spring xử lý các phương thức có `@Scheduled` trong những bean được quản lý bởi application context. Nó không cần hay biết Spring Batch trước; đó là một khả năng của Spring Framework.

Nếu ứng dụng có nhiều scheduled tasks, nên chú ý thread pool của scheduler. Một lịch mặc định có thể chạy trên số lượng thread hạn chế; nếu một job chạy đồng bộ vài giờ, các tác vụ khác có thể bị trì hoãn. Có thể khai báo scheduler pool khi thực sự cần nhiều lịch:

```yaml
spring:
  task:
    scheduling:
      pool:
        size: 4
      thread-name-prefix: "batch-schedule-"
```

Cấu hình này cho phép nhiều scheduled invocations được xử lý song song hơn ở lớp scheduler, **không đồng nghĩa JobRepository cho phép cùng JobInstance chạy đồng thời**. Cần thêm chính sách chống chồng lấn; không tăng pool size như cách sửa lỗi job bị trễ khi chính database đang nghẽn.

## 5. Cron expression và timezone

Spring `@Scheduled` dùng cron **6 trường** (đầu tiên là **giây**):

```text
second minute hour day-of-month month day-of-week
   0      15    2       *        *         *
```

Ví dụ:

| Cron của Spring | Diễn giải |
| --- | --- |
| `0 15 2 * * *` | 02:15 hằng ngày |
| `0 0 6 * * MON-FRI` | 06:00 từ thứ Hai đến thứ Sáu |
| `0 30 23 L * *` | 23:30 ngày cuối tháng (nếu phiên bản parser hỗ trợ ký hiệu `L`) |
| `0 0 */4 * * *` | Đầu mỗi khoảng bốn giờ |
| `0 0 3 1 * *` | 03:00 ngày đầu tháng |

**Đừng nhầm cron 5 trường của Linux/Kubernetes với cron 6 trường của Spring**. Linux `15 2 * * *` tương ứng Spring `0 15 2 * * *`.

Luôn chọn múi giờ theo nghiệp vụ. Trong ví dụ:

```java
@Scheduled(
        cron = "${app.batch.import-orders.cron}",
        zone = "${app.batch.import-orders.zone}")
```

`zone` điều khiển cách lịch được diễn giải; nó không tự điều khiển cách ứng dụng tính `businessDate`. Để hai việc khớp nhau, ta tạo một `Clock` theo đúng múi giờ đó.

Việt Nam hiện không có chuyển đổi DST, nhưng nếu triển khai lịch ở vùng có DST, giờ như 02:15 có thể **không tồn tại** hoặc **lặp** trong ngày chuyển giờ. Lịch, deadline và business date cần quy tắc rõ ràng; không tự cho rằng mọi “ngày” đều dài đúng 24 giờ.

## 6. Tạo `Clock` để tính ngày nghiệp vụ nhất quán

Thay vì gọi `LocalDate.now()` theo timezone mặc định của JVM, inject một `Clock` đã cấu hình:

```java
package com.example.batch.config;

import java.time.Clock;
import java.time.ZoneId;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BatchClockConfig {

    @Bean
    public Clock batchClock(
            @Value("${app.batch.import-orders.zone}") String zone) {
        return Clock.system(ZoneId.of(zone));
    }
}
```

Khi cron chạy lúc 02:15 ngày 16/11 tại Việt Nam:

```text
LocalDate.now(batchClock) = 2026-11-16
businessDate = 2026-11-15
```

Dùng `Clock` cũng giúp viết test với `Clock.fixed(...)`, không phụ thuộc ngày máy CI đang chạy. Trong production, ý nghĩa “ngày trước” có thể thay bằng **business calendar** nếu hệ thống xử lý ngày làm việc, ngân hàng hoặc ngày lễ. Ví dụ thứ Hai có thể cần đối soát thứ Sáu trước đó; `minusDays(1)` không phù hợp trong mọi domain.

## 7. Tạo `Job` và `Step` mẫu

Tạo `ImportOrdersJobConfig` để chạy một step `Tasklet` đơn giản. Trong dự án thật, thay tasklet bằng chunk-oriented step đọc đơn hàng, validate và ghi cơ sở dữ liệu.

```java
package com.example.batch.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersJobConfig {

    private static final Logger log =
            LoggerFactory.getLogger(ImportOrdersJobConfig.class);

    @Bean
    public Step importOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager) {

        return new StepBuilder("importOrdersStep", repository)
                .tasklet((contribution, context) -> {
                    String businessDate =
                            contribution.getStepExecution()
                                    .getJobParameters()
                                    .getString("businessDate");

                    log.info("Importing orders for businessDate={}",
                            businessDate);

                    // Demo: thay bằng xử lý dữ liệu thực trong dự án.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository repository,
            @Qualifier("importOrdersStep") Step step) {

        return new JobBuilder("importOrders", repository)
                .start(step)
                .build();
    }
}
```

Trong code:

- Bean Spring tên `importOrdersJob`, trong khi **tên logic** của Batch job là `importOrders` (do `JobBuilder("importOrders", ...)`).
- `StepBuilder("importOrdersStep", repository)` tạo step, `tasklet(..., transactionManager)` cung cấp transaction manager của step.
- `businessDate` được đọc từ `JobParameters` của execution. Không đọc trực tiếp `LocalDate.now()` bên trong tasklet để quyết định dữ liệu cần xử lý, vì nếu restart vào một ngày khác, step phải xử lý **cùng kỳ**.
- Tasklet không chứng minh restart ở mức item. Với file reader/DB writer, cần thiết kế `ItemStream`/`ExecutionContext` và transaction/idempotency theo nguồn dữ liệu.

Giả sử project có đúng một `JobRepository` và một transaction manager được Boot cấu hình. Với nhiều datasource hoặc transaction manager, cần `@Qualifier` rõ ràng và kiểm tra dữ liệu nghiệp vụ/metadata có cùng transaction hay không.

## 8. Tách việc launch job khỏi lớp scheduler

Không đặt mọi logic trong một phương thức `@Scheduled`. Tạo một service nhận **ngày nghiệp vụ** để cron, CLI, endpoint nội bộ hoặc bộ điều phối bên ngoài có thể cùng sử dụng mà không thay đổi `JobParameters` một cách tùy tiện.

```java
package com.example.batch.service;

import java.time.LocalDate;
import java.util.Objects;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ImportOrdersLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public ImportOrdersLaunchService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public static JobParameters parametersFor(LocalDate businessDate) {
        Objects.requireNonNull(businessDate, "businessDate");

        return new JobParametersBuilder()
                .addString("businessDate",
                        businessDate.toString(), true)
                .addString("triggerSource", "scheduler", false)
                .toJobParameters();
    }

    public JobExecution launch(LocalDate businessDate)
            throws JobExecutionAlreadyRunningException,
                   JobRestartException,
                   JobInstanceAlreadyCompleteException,
                   JobParametersInvalidException {

        return jobLauncher.run(
                importOrdersJob,
                parametersFor(businessDate));
    }
}
```

**Vì sao chỉ `businessDate` là identifying parameter ở ví dụ?** Mỗi ngày nghiệp vụ tương ứng một công việc logic. Nếu cron kích hoạt hai lần cho cùng ngày, cả hai yêu cầu sẽ nhắm cùng `JobInstance` và repository có thể từ chối trường hợp đã hoàn tất/đang chạy. `triggerSource` là thông tin theo dõi, không làm thay đổi danh tính.

Đừng thêm `System.currentTimeMillis()`, UUID hay `run.id` identifying vào mỗi lần schedule trigger nếu ý định là **restart hoặc ngăn chạy trùng cho cùng kỳ**. Những tham số đó tạo `JobInstance` mới ở mỗi lần kích hoạt, khiến repository không còn áp dụng bảo vệ “instance này đã `COMPLETED`”.

Nếu nghiệp vụ cho phép **chạy lại một ngày với nguồn dữ liệu phiên bản mới**, hãy thiết kế `sourceVersion`/`importVersion` như identifying parameter bổ sung **với ý nghĩa nghiệp vụ**, cùng quy tắc bảo đảm writer không tạo dữ liệu trùng. Không dùng tham số ngẫu nhiên để che lỗi phục hồi.

## 9. Kích hoạt từ `@Scheduled`

Tạo component nối cron với launch service:

```java
package com.example.batch.schedule;

import java.time.Clock;
import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.example.batch.service.ImportOrdersLaunchService;

@Component
public class ImportOrdersSchedule {

    private static final Logger log =
            LoggerFactory.getLogger(ImportOrdersSchedule.class);

    private final ImportOrdersLaunchService launchService;
    private final Clock clock;

    public ImportOrdersSchedule(
            ImportOrdersLaunchService launchService,
            Clock batchClock) {
        this.launchService = launchService;
        this.clock = batchClock;
    }

    @Scheduled(
            cron = "${app.batch.import-orders.cron}",
            zone = "${app.batch.import-orders.zone}")
    public void startDailyImport() {
        LocalDate businessDate = LocalDate.now(clock).minusDays(1);

        try {
            JobExecution execution =
                    launchService.launch(businessDate);

            log.info("Submitted importOrders: date={} " +
                            "jobExecutionId={} status={}",
                    businessDate,
                    execution.getId(),
                    execution.getStatus());

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info("importOrders already completed for date={}",
                    businessDate);

        } catch (JobExecutionAlreadyRunningException ex) {
            log.warn("importOrders already running for date={}",
                    businessDate);

        } catch (JobRestartException
                 | JobParametersInvalidException ex) {
            log.error("Cannot start importOrders for date={}",
                    businessDate, ex);

        } catch (Exception ex) {
            // Giữ log chẩn đoán cho lỗi runtime/hạ tầng ngoài dự kiến.
            log.error("Unexpected scheduler launch failure: date={}",
                    businessDate, ex);
        }
    }
}
```

Khi chạy ứng dụng qua `BatchSchedulerApplication`:

1. Spring khởi động context, cấu hình `JobRepository`, `JobLauncher`, `Job` và step.
2. `spring.batch.job.enabled=false` tránh Spring Boot tự chạy job lúc startup.
3. `@EnableScheduling` kích hoạt hạ tầng lịch.
4. Đến 02:15 `Asia/Ho_Chi_Minh`, Spring gọi `startDailyImport()`.
5. Lớp schedule tính ngày nghiệp vụ rồi gọi `ImportOrdersLaunchService.launch(...)`.
6. `JobLauncher` tạo hoặc nối tiếp một execution phù hợp với trạng thái repository và cấu hình job.
7. Log chứa `businessDate`/`jobExecutionId`; trạng thái cuối đọc từ `JobRepository`/`JobExplorer`.

**Một điểm quan trọng:** tên log “Submitted” có chủ ý. `JobLauncher` có thể chạy **đồng bộ hoặc bất đồng bộ** tùy `TaskExecutor` và cấu hình. Nếu bất đồng bộ, `JobExecution` trả về có thể vẫn là `STARTING` hoặc `STARTED`; log “Submitted” **không được diễn giải thành “job đã thành công”**.

Với launcher đồng bộ, lời gọi trong `@Scheduled` có thể chờ đến khi job hoàn tất và chiếm một thread scheduler trong suốt thời gian đó. Với launcher bất đồng bộ, phương thức schedule trả về sớm nhưng cần một cơ chế khác để theo dõi execution cuối cùng. Hai trường hợp đều cần chính sách chống chạy chồng lấn và quan sát trạng thái.

### Tại sao lại bắt từng loại exception?

| Exception | Thông điệp vận hành | Nên làm |
| --- | --- | --- |
| `JobInstanceAlreadyCompleteException` | Cùng `JobInstance` đã hoàn tất | Xem là trigger lặp hợp lệ hoặc sự kiện cần giám sát; không tự chạy lại |
| `JobExecutionAlreadyRunningException` | Repository ghi nhận execution đang hoạt động | Không khởi chạy trùng; xác minh liveness nếu status quá lâu |
| `JobRestartException` | Không thể restart theo quy tắc Job/Step/metadata | Kiểm tra trạng thái, restartability, `ExecutionContext` |
| `JobParametersInvalidException` | Tham số không qua validation | Sửa logic tính ngày/đầu vào, tránh retry mù |
| Lỗi DB/hạ tầng khác | Không tạo hoặc điều phối execution theo kỳ vọng | Alert, kiểm tra metadata DB, transaction và hệ thống phụ thuộc |

Ở production, nên có alert/event riêng cho lỗi launch nghiêm trọng. Nếu chỉ bắt rồi log mà không có hệ thống giám sát log, scheduler có thể bỏ lỡ cả kỳ mà người vận hành không biết.

## 10. Restart, rerun và backfill là ba thao tác khác nhau

**Restart:** job `FAILED` hoặc `STOPPED` được khởi chạy lại với identifying parameters thuộc **cùng `JobInstance`** để tiếp tục dựa trên metadata.

**Rerun với một instance mới:** nghiệp vụ cố ý tạo lần xử lý logic khác, ví dụ input source version mới. Phải xác định rõ dữ liệu cũ được thay thế, hợp nhất hay giữ phiên bản.

**Backfill:** chạy các kỳ lịch sử bị thiếu, chẳng hạn từ 10/11 đến 15/11. Backfill có thể là restart, instance mới hoặc bỏ qua kỳ đã hoàn tất tùy metadata.

```text
Business date 2026-11-15
    |
    +-- JobInstance A
          |
          +-- Execution 100 FAILED
          +-- Execution 101 COMPLETED (restart)

Business date 2026-11-14
    |
    +-- JobInstance B
          |
          +-- Execution 102 COMPLETED (backfill kỳ thiếu)

Business date 2026-11-15, sourceVersion=v2
    |
    +-- JobInstance C, nếu sourceVersion là identifying
          |
          +-- Execution 103 COMPLETED (rerun phiên bản mới)
```

Một cron “mỗi ngày 02:15” không tự chạy lại những lịch đã **bỏ lỡ khi ứng dụng tắt**. Sau downtime 3 ngày, cron đơn giản chỉ kích hoạt lại ở mốc kế tiếp và tính “ngày hôm qua”; các ngày ở giữa có thể không có `JobExecution` nào.

Muốn hỗ trợ backfill, thiết kế một entrypoint nhận `businessDate` **tường minh**, chỉ cho phép nhóm vận hành đã được phân quyền kích hoạt, kiểm tra trạng thái lịch sử và chọn có được restart hay cần manual recovery hay không. Không dùng ngày hiện tại khi job nhận một backfill date rõ ràng.

## 11. Lựa chọn scheduler phù hợp

`@Scheduled` rất thuận tiện, nhưng không phải giải pháp duy nhất.

| Giải pháp | Phù hợp khi | Hạn chế/cần bổ sung |
| --- | --- | --- |
| **Spring `@Scheduled`** | Một service chạy lâu dài, ít lịch, lịch đơn giản, một instance scheduler | Không tự lưu misfire/missed tick, không có persistent job trigger, không tự xử lý cluster |
| **Spring `TaskScheduler`** | Cần lên lịch động/điều chỉnh trigger trong ứng dụng | Lịch và trạng thái cần tự lưu nếu muốn khôi phục sau restart |
| **Quartz với JDBC JobStore** | Nhiều lịch, misfire policy, persistent triggers, cluster coordination | Phải quản trị Quartz tables, trigger/job details và mapping tới Batch |
| **Kubernetes CronJob** | Batch container chạy một lần rồi thoát, hạ tầng Kubernetes quản lý lịch | Pod/process lifecycle riêng; CronJob không thay thế Batch metadata/checkpoint |
| **Linux cron / systemd timer** | Job CLI đơn giản trên host được quản lý | Cần logging, lock, retry và phân quyền; không hợp lý cho cluster lớn nếu không có điều phối |
| **Workflow orchestrator (Airflow, Argo, v.v.)** | Nhiều job phụ thuộc, DAG, SLA, backfill và theo dõi xuyên job | Thêm hạ tầng và hợp đồng dữ liệu, mapping execution IDs |
| **Managed scheduler/cloud event service** | Hạ tầng đã cung cấp trigger, queue và retry chính sách rõ | Cần endpoint/consumer idempotent, bảo mật và xử lý duplicate |

Một trường hợp dễ quyết định: nếu chỉ có `importOrders` chạy hằng ngày trên **một JVM duy nhất**, `@Scheduled` thường đủ để bắt đầu. Nếu cần **đảm bảo trigger được lưu bền vững khi service down**, nhiều node cùng chạy, lịch do người dùng thay đổi, hoặc retry misfire có kiểm soát, Quartz/external scheduler thường dễ quản trị hơn về lâu dài.

### `@Scheduled` không phải lịch bền vững

Khi JVM dừng lúc 02:15, phương thức `@Scheduled` không chạy. Sau khi JVM khởi động lại lúc 09:00, nó **không tự backfill tick 02:15**. Cần:

- Một job/trigger bên ngoài có cơ chế ghi nhận missed run.
- Hoặc một **reconciliation process** định kỳ so các kỳ dự kiến với metadata `JobRepository` và chủ động đưa các kỳ thiếu vào hàng đợi điều phối.
- Hoặc runbook backfill thủ công có kiểm soát nếu SLA và tần suất cho phép.

**Không dựa vào “không có dòng `FAILED`” để kết luận không có sự cố.** Job chưa từng được launch sẽ không có execution để thất bại.

## 12. Triển khai trên nhiều instance: chống kích hoạt trùng

Trong mô hình HA có hai hoặc nhiều JVM/pod chạy cùng code `@Scheduled`:

```text
02:15:00
  Pod A --> @Scheduled --> launch(importOrders, 2026-11-15)
  Pod B --> @Scheduled --> launch(importOrders, 2026-11-15)
                  |
                  v
            Shared JobRepository
```

Hai pod đều có scheduler riêng. **`@Scheduled` không phải distributed lock.** `JobRepository` áp dụng quy tắc instance/execution để chống một số trường hợp trùng trên cùng định danh, nhưng không nên xem đó là chính sách orchestration cluster hoàn chỉnh. Việc cùng lúc tạo execution có thể ném exception tranh chấp; nếu thay identifying parameter bằng UUID ở từng pod thì cả hai có thể khởi chạy **hai `JobInstance` khác nhau**, rất nguy hiểm.

Các lựa chọn:

1. Chỉ chạy scheduler trên **một instance/leader** được quản lý rõ; các worker khác chỉ thực thi job.
2. Dùng **Quartz JDBC cluster** với trigger được lưu bền vững và cấu hình cluster theo tài liệu Quartz.
3. Dùng **Kubernetes CronJob** hoặc một external scheduler làm một điểm tạo trigger.
4. Dùng distributed lock/lease khi trigger, với thời hạn, failure handling và fencing phù hợp; tránh tự viết khóa bằng một cột Boolean không có atomicity.
5. Dù scheduler có khóa, vẫn dùng **stable JobParameters và idempotent writer** vì retry/network fault có thể tạo lại thông điệp.

**Đừng chỉ dựa vào `synchronized` trong Java** để ngăn chạy trùng trên nhiều pod; nó chỉ đồng bộ các thread trong cùng JVM. Cũng đừng nghĩ `concurrencyPolicy: Forbid` của một Kubernetes CronJob sẽ ngăn toàn bộ job được chạy bởi API tay hoặc một CronJob object khác.

## 13. Nếu dùng Quartz: kết hợp thế nào?

Quartz có khái niệm `JobDetail` và `Trigger` riêng, khác với `org.springframework.batch.core.Job`. Một Quartz job class thường là **adapter**: lấy lịch và dữ liệu từ Quartz `JobDataMap`, rồi gọi `ImportOrdersLaunchService.launch(businessDate)`. `JobRepository` vẫn tiếp tục quản lý metadata của Spring Batch.

```text
Quartz CronTrigger (persistent JDBC)
        |
        v
Quartz Job (adapter)
        |
        v
ImportOrdersLaunchService
        |
        v
JobLauncher -> Spring Batch Job -> JobRepository
```

Cần phân biệt tên “Job” của Quartz với tên Batch job. Quartz không tự biết `StepExecution`, chunk checkpoint hoặc `JobInstance` identity của Spring Batch.

Khi cần cluster, cấu hình **Quartz JDBC JobStore**, clustering và misfire behavior đúng phiên bản. Annotation `@DisallowConcurrentExecution` của Quartz ngăn thực thi song song **cùng JobDetail key** ở mức Quartz trong điều kiện hạ tầng quản lý đúng; nó không thay thế bảo vệ nghiệp vụ/metadata Spring Batch và không chặn một entrypoint khác gọi `JobLauncher`.

Nếu Quartz chạy adapter mà `JobLauncher` dùng executor **bất đồng bộ**, Quartz có thể coi callback adapter đã kết thúc trong khi Batch vẫn chạy; vì vậy cơ chế chống chồng lấn phải theo dõi **lifecycle thực của Batch execution**, không chỉ thời gian thực thi phương thức Quartz.

## 14. Nếu dùng Kubernetes CronJob

Một lựa chọn production là đóng gói ứng dụng thành chương trình **run-once**: container khởi động, chạy một `Job` cho một kỳ, kết thúc process với exit code phản ánh kết quả. Kubernetes tạo Pod theo lịch.

Ví dụ manifest mang tính minh họa:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: import-orders
spec:
  schedule: "15 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 3600
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: import-orders
              image: registry.example.com/orders-batch:1.0.0
              args:
                - "--spring.profiles.active=cronjob"
                - "--spring.batch.job.enabled=false"
```

**Manifest này là khung triển khai, chưa phải chương trình run-once hoàn chỉnh.** Image phải có entrypoint chạy đúng `importOrders`, tính `businessDate` theo lịch/đầu vào của orchestrator, chờ `JobExecution` terminal rồi trả exit code thích hợp. Phải dùng database `JobRepository` bền vững. Nếu dùng chính ứng dụng có `@EnableScheduling` mà không tắt lịch in-process, pod run-once có thể không thoát hoặc tạo hai cơ chế trigger; tách cấu hình theo profile/entrypoint.

Kubernetes `spec.timeZone` chỉ được hỗ trợ ở các phiên bản Kubernetes phù hợp; kiểm tra version cluster và chính sách múi giờ. `concurrencyPolicy: Forbid` ngăn chồng lấn các Job do **cùng một CronJob controller** quản lý theo chính sách đó, nhưng không đảm bảo một kỳ không được trigger từ hệ thống khác. `startingDeadlineSeconds` và `backoffLimit` ảnh hưởng đến lịch bị trễ và số lần Kubernetes thử tạo lại pod; chúng phải phối hợp với chính sách restart/idempotency của Spring Batch.

### Một entrypoint run-once nên làm gì?

```text
Start application ở profile cronjob
   |
   v
Tính/đọc businessDate được cấp
   |
   v
JobLauncher.run(importOrders, stable JobParameters)
   |
   v
Chờ JobExecution về trạng thái cuối
   |
   +-- COMPLETED: exit 0 (và quality gates đạt)
   +-- FAILED / STOPPED / UNKNOWN: exit khác 0
   +-- already COMPLETED: chính sách duplicate có thể exit 0
   +-- launch error: exit khác 0, alert
```

Nếu container bị kill giữa chừng, metadata có thể còn `STARTED`; cần runbook kiểm tra trạng thái và checkpoint trước khi cho phép restart. Không sửa metadata bằng SQL tùy tiện để ép Kubernetes retry.

## 15. Job chạy lâu và chồng lịch

Giả sử cron kích hoạt 02:15 mỗi ngày nhưng `importOrders` có lúc mất 27 giờ. Đến 02:15 ngày sau, execution của kỳ trước vẫn chạy:

```text
2026-11-16 02:15 -> businessDate=2026-11-15 STARTED
2026-11-17 02:15 -> businessDate=2026-11-16 NEW INSTANCE
```

Vì identifying `businessDate` khác nhau, `JobRepository` **có thể cho phép hai `JobInstance` chạy đồng thời**, tùy job/step và hạ tầng. Nếu writer dùng chung bảng, file hoặc API rate limit, điều này có thể gây tranh chấp dù mỗi instance đều có identity hợp lệ.

Phải chọn chính sách ở **mức toàn bộ job loại `importOrders`**, không chỉ “cùng businessDate”:

| Chính sách | Khi kỳ trước còn chạy | Khi nào dùng |
| --- | --- | --- |
| **Allow overlap** | Chạy đồng thời hai kỳ | Đầu vào/output được phân vùng hoàn toàn và hệ thống chịu tải tốt |
| **Forbid overlap** | Không tạo execution mới khi kỳ trước còn chạy | Job cần độc quyền resource hoặc tránh chồng transaction |
| **Queue** | Ghi yêu cầu kỳ mới vào hàng đợi bền vững; chạy sau kỳ cũ | Không muốn bỏ lỡ kỳ và không cho overlap |
| **Catch-up** | Sau khi kỳ trước kết thúc, rà soát các kỳ thiếu | Thích hợp SLA có thể chấp nhận xử lý muộn |
| **Skip with alert** | Không chạy kỳ mới; cảnh báo để người vận hành quyết định | Công việc không được tự replay hoặc có rủi ro cao |

`@Scheduled` tự nó không áp dụng đầy đủ các chính sách trên cho **mọi `JobInstance` và mọi node**. Hãy triển khai ở scheduler/orchestrator hoặc một dịch vụ điều phối có lock/state bền vững, đồng thời giữ tên kỳ và ID execution để audit.

## 16. Lịch chạy không đồng nghĩa “dữ liệu đã sẵn sàng”

Một cron 02:15 chỉ biểu diễn mốc **thời gian**, không chứng minh file nguồn đã đến hoặc báo cáo upstream đã hoàn tất. Nếu job cần file `orders-2026-11-15.csv` nhưng hệ thống đối tác trễ 40 phút, có vài lựa chọn:

- **Fail-fast với lỗi nguồn chưa sẵn sàng**, scheduler/orchestrator retry có giới hạn theo chính sách; không tự tạo một tập dữ liệu rỗng.
- **Đợi sự kiện “file ready”** hoặc marker/checksum của nhà cung cấp, rồi kích hoạt job.
- **Dependency-aware orchestration**: chỉ launch sau khi job upstream `COMPLETED` và quality gate đạt.
- **Kiểm tra nguồn trước khi tạo JobExecution** nếu không muốn tạo hàng loạt failure vì input chưa sẵn sàng, nhưng phải bảo đảm kiểm tra và launch không có race.
- **Chờ theo deadline**: chấp nhận dữ liệu đến muộn trong grace period, quá hạn thì alert.

Nếu nguồn thay đổi sau khi job đã bắt đầu, đặc biệt khi reader sử dụng checkpoint theo offset, restart có thể đọc tập dữ liệu khác. Cần source version/checksum/snapshot ổn định trong mọi lần chạy của cùng `JobInstance`.

## 17. Giám sát job được scheduler khởi chạy

Một scheduled method đã được gọi không chứng minh job hoàn tất. Phân biệt ba sự kiện:

```text
batch.schedule.triggered
    Scheduler đã đến mốc và quyết định gọi launch.

batch.job.started / JobExecution created
    JobRepository ghi nhận execution và Batch bắt đầu xử lý.

batch.job.finished
    Execution có kết quả cuối: COMPLETED / FAILED / STOPPED...
```

Có thể bổ sung `JobExecutionListener` để ghi kết quả cuối độc lập với việc launcher sync/async:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class JobOutcomeListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(JobOutcomeListener.class);

    @Override
    public void afterJob(JobExecution execution) {
        log.info(
                "Job ended: name={} instance={} execution={} " +
                "businessDate={} status={} exitCode={}",
                execution.getJobInstance().getJobName(),
                execution.getJobInstance().getId(),
                execution.getId(),
                execution.getJobParameters().getString("businessDate"),
                execution.getStatus(),
                execution.getExitStatus().getExitCode());
    }
}
```

Gắn bằng `new JobBuilder(...).listener(new JobOutcomeListener()).start(...).build()` trong cấu hình job. Trong hệ thống thực, nên ghi structured logs và alert dựa trên trạng thái, không chỉ in console. Nếu JVM bị kill trước `afterJob`, callback có thể không chạy; khi đó repository + liveness/heartbeat và quy trình recovery là cần thiết.

Các số liệu nên theo dõi:

| Góc nhìn | KPI | Nguồn |
| --- | --- | --- |
| Lịch | Expected vs actual trigger, missing run, lateness | Scheduler/orchestrator + business calendar |
| Job | `JobExecution` status, duration, restart count | `JobRepository`/`JobExplorer` |
| Step | read/write/filter/skip, commit/rollback | `StepExecution` |
| Chất lượng | số bản ghi kỳ vọng, số bản ghi thực tế, giới hạn skip | Validation của ứng dụng + metadata |
| Hiệu năng | duration, active job, throughput | Micrometer, logs, tracing |
| Hạ tầng | metadata DB availability, connection pool, thread/pod health | Metrics/health checks |

Nếu application đã tắt khi đến giờ cron, repository **không có execution**, vì vậy phải so lịch kỳ vọng với lịch sử thực thi để phát hiện `MISSING_RUN`. Một `JobExecution` còn `STARTED` sau crash cũng chưa chắc còn process chạy; cần xác minh liveness trước recovery.

## 18. Kiểm thử với `Clock.fixed` và mock JobLauncher

Tách launch service giúp test tạo `JobParameters` một cách deterministic. Với test JUnit Jupiter:

```java
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;

import com.example.batch.service.ImportOrdersLaunchService;

import static org.junit.jupiter.api.Assertions.*;

class ImportOrdersParametersTest {

    @Test
    void sameBusinessDateProducesStableIdentity() {
        LocalDate date = LocalDate.of(2026, 11, 15);

        JobParameters first =
                ImportOrdersLaunchService.parametersFor(date);
        JobParameters second =
                ImportOrdersLaunchService.parametersFor(date);

        assertEquals(first, second);
        assertEquals("2026-11-15",
                first.getString("businessDate"));
        assertTrue(first.getParameter("businessDate").isIdentifying());
        assertFalse(first.getParameter("triggerSource").isIdentifying());
    }

    @Test
    void distinctBusinessDatesProduceDifferentIdentities() {
        JobParameters dayA = ImportOrdersLaunchService.parametersFor(
                LocalDate.of(2026, 11, 14));
        JobParameters dayB = ImportOrdersLaunchService.parametersFor(
                LocalDate.of(2026, 11, 15));

        assertNotEquals(dayA, dayB);
    }
}
```

Test giá trị ngày được scheduler tính bằng `Clock.fixed`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SchedulerBusinessDateTest {

    @Test
    void usesPreviousDayInConfiguredTimezone() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-16T00:30:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        LocalDate businessDate = LocalDate.now(clock).minusDays(1);

        assertEquals(LocalDate.of(2026, 11, 15), businessDate);
    }
}
```

Có thể thêm unit test mock `JobLauncher` để khẳng định service truyền đúng `Job` và `JobParameters`:

```java
import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

import com.example.batch.service.ImportOrdersLaunchService;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class ImportOrdersLaunchServiceTest {

    @Test
    void launchPassesCorrectBusinessDate() throws Exception {
        JobLauncher launcher = mock(JobLauncher.class);
        Job job = mock(Job.class);
        JobExecution execution = mock(JobExecution.class);

        when(launcher.run(eq(job), any(JobParameters.class)))
                .thenReturn(execution);

        ImportOrdersLaunchService service =
                new ImportOrdersLaunchService(launcher, job);

        service.launch(LocalDate.of(2026, 11, 15));

        ArgumentCaptor<JobParameters> captor =
                ArgumentCaptor.forClass(JobParameters.class);
        verify(launcher).run(eq(job), captor.capture());

        assertEquals("2026-11-15",
                captor.getValue().getString("businessDate"));
    }
}
```

Những test này không cần chạy cron thật hoặc chờ đến 02:15. Chúng kiểm tra logic tạo identity và gọi launcher, tránh tạo test phụ thuộc đồng hồ thực.

### Integration test nên chứng minh điều gì?

Với `spring-batch-test` và repository test có thể kiểm soát, cần thêm các kịch bản:

1. Khởi chạy `importOrders` cho `businessDate=2026-11-15`, xác nhận execution `COMPLETED`.
2. Khởi chạy lại **cùng identifying params**, xác nhận Spring Batch từ chối nếu instance đã hoàn tất.
3. Gây lỗi chủ động ở một step sau khi chunk đã commit; chạy lại cùng params, xác nhận restart không gây trùng dữ liệu.
4. Kiểm tra `spring.batch.job.enabled=false`: context khởi động không tự tạo execution.
5. Hai yêu cầu concurrent cùng kỳ: repository/scheduling policy không tạo hai tác động nghiệp vụ trùng.
6. Bỏ lỡ hai ngày cron: cơ chế reconciliation/backfill phát hiện đủ kỳ thiếu.
7. Test process crash/mất kết nối metadata và recovery đúng quy trình.
8. Test lịch ở timezone được cấu hình; nếu có DST, thêm test ngày chuyển giờ.

Một test restart cần **giữ metadata giữa lần `FAILED` và lần retry**; không dùng database H2 được dựng lại trong mỗi nửa test rồi kết luận checkpoint đã hoạt động. Các số liệu `writeCount` không thay thế đối chiếu số business IDs duy nhất ở dữ liệu đích.

## 19. Quy trình vận hành: khi lịch bị bỏ lỡ hoặc job thất bại

Với production, nên có runbook:

### Trường hợp A — Qua giờ lịch nhưng không có `JobExecution`

1. Kiểm tra scheduler/pod có hoạt động ở mốc dự kiến không.
2. Kiểm tra cron expression, timezone, feature flag/profile và configuration.
3. Kiểm tra input/dependency và cơ chế retry/misfire của scheduler.
4. Tính những `businessDate` bị thiếu từ **lịch kỳ vọng**, không chỉ từ các execution có trong DB.
5. Backfill từng kỳ qua launch service/orchestrator với stable identifying params; theo dõi hoàn tất.

### Trường hợp B — `JobInstanceAlreadyCompleteException`

Đây có thể là tình huống cron phát lại cùng kỳ nhưng job đã `COMPLETED`. Kiểm tra đúng instance và kết quả chất lượng. Nếu nghiệp vụ thật sự cần nhập lại dữ liệu phiên bản mới, tạo quy trình rerun có version/idempotency và audit; không thêm UUID bất kỳ.

### Trường hợp C — `FAILED`

Kiểm tra `JobExplorer`, lỗi step, checkpoint, nguồn có ổn định không, dữ liệu đích đã commit những gì và liệu writer có hỗ trợ replay. Nếu phù hợp, restart **cùng identifying parameters**. Nếu không chắc về side effect ngoài transaction, đối soát trước khi gọi lại API/ghi lại file.

### Trường hợp D — `STARTED` quá lâu hoặc sau khi process chết

Đừng tự `UPDATE BATCH_JOB_EXECUTION SET STATUS='FAILED'` chỉ vì `LAST_UPDATED` cũ. Xác minh process/worker đã chết, DB/transaction còn hoạt động không, kết quả side effect nào đã tồn tại, rồi dùng cơ chế recovery được hỗ trợ bởi phiên bản Batch và runbook.

### Trường hợp E — Hai lần lịch chồng nhau

Kiểm tra định danh nghiệp vụ, có hai instance khác nhau hay một instance bị trigger trùng, nguồn dữ liệu và tài nguyên chung. Áp dụng chính sách concurrency ở orchestrator/leader, không chỉ thêm `synchronized` trong một JVM.

## 20. Checklist đưa scheduler lên production

| Hạng mục | Cần xác nhận trước khi vận hành |
| --- | --- |
| Lịch | Cron đúng loại 5/6 trường, timezone rõ ràng, policy ngày nghỉ/DST |
| Danh tính | `JobParameters` có identifying fields ổn định, không có random run ID ngoài chủ ý |
| Startup | Không tự chạy ngoài lịch khi khởi động application |
| Repository | JDBC metadata DB bền vững, schema migration/backup, phân quyền đúng |
| Restart | Reader/writer có checkpoint hoặc chiến lược replay/idempotency phù hợp |
| Concurrency | Quy tắc overlap giữa các kỳ và giữa các node được xác định |
| Missing run | Có lịch kỳ vọng và cơ chế phát hiện/backfill sau downtime |
| Monitoring | Log job/step IDs, status cuối, duration, counts và alert |
| Quality gates | `COMPLETED` về kỹ thuật chưa chắc đạt yêu cầu dữ liệu |
| Security | Chỉ scheduler/nhóm được phép launch; không lộ toàn bộ JobParameters |
| Operations | Có runbook FAILED/STARTED/misfire, backfill và manual rerun |
| Tests | Unit test lịch/param, integration test duplicate và restart |
| Deployment | Một source of truth cho scheduling (in-process hoặc external), không tạo hai trigger |
| Cost/performance | Scheduler thread pool, datasource load và SLA được quan sát |

Một nguyên tắc quan trọng là **phải có một “nguồn chân lý” cho lịch chạy**. Nếu chuyển từ `@Scheduled` sang Quartz hoặc Kubernetes CronJob, cần tắt cơ chế cũ theo profile/feature flag; để cả hai hoạt động song song sẽ tạo nhiều trigger cạnh tranh, dù `JobRepository` đôi khi ngăn được một số trường hợp trùng.

## 21. Các bài tập mở rộng dự án

Sau khi demo chạy được, có thể mở rộng từng phần:

**Bài tập 1 — Tách ngày chạy ra khỏi đồng hồ.** Tạo lệnh nội bộ nhận `businessDate` và gọi cùng `ImportOrdersLaunchService`; chỉ cho phép người vận hành có quyền kích hoạt. Kiểm tra cùng kỳ đã `COMPLETED` thì không tạo instance mới ngoài chủ đích.

**Bài tập 2 — Chuyển H2 sang PostgreSQL.** Tạo metadata schema bằng migration, bảo đảm JobRepository giữ dữ liệu sau khi restart JVM. Gây lỗi ở step giữa, khởi động lại ứng dụng rồi restart cùng JobInstance.

**Bài tập 3 — Missing run detector.** Lưu danh sách những kỳ bắt buộc xử lý; mỗi sáng so với `JobExplorer` để tìm kỳ chưa có execution hoặc chưa hoàn tất trước deadline. Thử tắt ứng dụng trong hai lần cron liên tiếp rồi khôi phục.

**Bài tập 4 — Scheduler cluster.** Chạy hai replica với cùng cron, quan sát hai trigger và thiết kế leader/external scheduler hoặc Quartz clustered JobStore. Thử cạnh tranh launch cùng kỳ và xác minh không có side effect bị nhân đôi.

**Bài tập 5 — Externalized scheduling.** Chuyển lịch sang Kubernetes CronJob hoặc Quartz; chỉ giữ `ImportOrdersLaunchService` làm điểm launch chung. Tách profile để không còn cả cron nội bộ và cron ngoài chạy song song.

**Bài tập 6 — Workflow nhiều job.** Sau khi import thành công và quality gate đạt, kích hoạt job `reconcileOrders` theo cùng kỳ và output version. Giả lập import `FAILED`, bảo đảm downstream không chạy sớm, kể cả khi `JobLauncher` hoạt động bất đồng bộ.

## 22. Những lỗi thường gặp khi đưa job vào scheduler

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Job chạy ngay khi mở ứng dụng | Spring Boot auto-run job lúc startup | `spring.batch.job.enabled=false` khi dùng lịch do ứng dụng điều khiển |
| Cron không được gọi | Thiếu `@EnableScheduling`, bean không thuộc context, cron sai | Kiểm tra annotation, profile, property, múi giờ |
| Cron chạy sai giờ | Nhầm cron 5 và 6 trường hoặc timezone JVM | Dùng 6 trường cho `@Scheduled`, đặt `zone` rõ |
| Xử lý sai ngày | Dùng `LocalDate.now()` trong step hoặc timezone sai | Dựng `businessDate` từ `Clock` theo nghiệp vụ và đưa vào JobParameters |
| Mỗi ngày chạy nhiều instance cùng kỳ | Thêm UUID/timestamp làm identifying parameter | Stable identifying params, idempotency và cluster scheduling |
| Job không chạy lần 2 dù đã sửa code | Cùng instance đã `COMPLETED` | Phân biệt restart, rerun version mới và backfill |
| Trigger báo thành công nhưng job sau đó `FAILED` | Nhầm launcher submission với terminal execution | Giám sát `JobExecution` cuối qua listener/repository |
| Scheduler bỏ lỡ lịch khi downtime | `@Scheduled` không lưu missed ticks | Misfire-aware scheduler hoặc reconciliation/backfill |
| Hai pod cùng kích hoạt | `@Scheduled` chạy trên mỗi instance | Một scheduler leader/Quartz cluster/external trigger |
| Job dài làm các lịch khác chậm | Scheduler thread bị chiếm bởi launcher đồng bộ | Cấu hình execution/monitoring phù hợp; không tăng concurrency mù |
| Job của ngày sau chồng ngày trước | Mỗi ngày có identifying param khác nhau | Quy tắc overlap/queue ở cấp scheduler/orchestrator |
| Restart từ đầu và ghi trùng | Reader không checkpoint hoặc writer thiếu idempotency | `ItemStream`, nguồn bất biến, transaction/idempotency |
| Không thấy run bị bỏ lỡ trong dashboard | Repository chỉ lưu các run được tạo | So expected schedule với lịch sử Batch |
| Pod chết, metadata còn `STARTED` | Không kịp ghi terminal status | Xác minh liveness, recovery an toàn; không sửa SQL tùy tiện |
| Quartz cho phép khởi chạy lại khi Batch còn chạy | Adapter Quartz trả về trước vì launcher async | Theo dõi trạng thái Batch và chống overlap ở cấp workflow |
| CronJob trên Kubernetes chạy mãi không thoát | Image vẫn bật scheduler in-process/web server | Tách entrypoint run-once và profile phù hợp |

## 23. Tài liệu tham khảo

Các URL dưới đây là tài liệu nền tảng; khi triển khai bằng Spring Batch 6.x hoặc phiên bản Spring Boot khác, đối chiếu API theo đúng dependency đang dùng.

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — `@Scheduled` annotation](https://docs.spring.io/spring-framework/reference/integration/scheduling/annotations.html)
- [Spring Framework — Cron Expressions](https://docs.spring.io/spring-framework/reference/integration/scheduling.html#scheduling-cron-expression)
- [Spring Batch 5.2 — Configuring a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html)
- [Spring Batch 5.2 — Job Domain, JobInstance, JobExecution](https://docs.spring.io/spring-batch/reference/5.2/domain.html)
- [Spring Batch 5.2 — Advanced Metadata Usage and JobOperator](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch 5.2 — JobRepository Configuration](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html)
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Boot — Batch Applications](https://docs.spring.io/spring-boot/how-to/batch.html)
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Quartz Scheduler — Documentation](https://www.quartz-scheduler.org/documentation/)
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Java 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)

**Kết luận:** Đưa một Spring Batch job vào scheduler không chỉ là viết `@Scheduled(cron=...)`. Cần tách rõ việc **xác định lịch**, **chọn kỳ nghiệp vụ**, **khởi chạy với identifying `JobParameters` ổn định**, **ghi metadata vào repository bền vững** và **theo dõi kết quả cuối**. Với một JVM và lịch đơn giản, `@Scheduled` là điểm khởi đầu phù hợp. Khi có nhiều node, missed run, SLA phức tạp hoặc workflow nhiều job, hãy dùng Quartz/Kubernetes/external orchestrator kết hợp chiến lược idempotency, backfill và recovery rõ ràng.
