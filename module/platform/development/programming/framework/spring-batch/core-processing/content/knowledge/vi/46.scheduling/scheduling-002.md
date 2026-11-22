# JobParameters từ scheduler trong Spring Batch

## 1. Vai trò của JobParameters trong một job được lập lịch

Một ứng dụng Spring Batch thường được kích hoạt theo lịch: cuối ngày tổng hợp doanh thu, mỗi giờ đồng bộ đơn hàng, mỗi tuần tạo báo cáo, hoặc đúng thời điểm chốt kỳ để tính toán công nợ. Đối với các job như vậy, **scheduler quyết định khi nào yêu cầu chạy**, còn **`JobParameters` mô tả lần chạy được yêu cầu xử lý dữ liệu nào**.

Ví dụ, lịch chạy 02:00 mỗi ngày và xử lý dữ liệu của ngày hôm trước. Vào 02:00 ngày 17/11/2026 theo giờ Việt Nam, scheduler có thể truyền:

```text
jobName = dailyOrdersJob
businessDate = 2026-11-16
triggerSource = scheduler
```

Trong đó:

- `dailyOrdersJob` là tên job.
- `businessDate` là ngày nghiệp vụ phải xử lý, có thể khác ngày ứng dụng hiện đang chạy.
- `triggerSource` cho biết nguồn kích hoạt, hữu ích cho log và audit.

Luồng thực thi thường là:

```text
Cron / @Scheduled / Quartz / external scheduler
                   |
                   v
         Tính businessDate
                   |
                   v
        JobParametersBuilder
                   |
                   v
     JobLauncher.run(Job, JobParameters)
                   |
                   v
    JobRepository tra cứu JobInstance
          |                  |
          v                  v
  Lưu JobExecution     Xử lý quy tắc
  và StepExecution     chạy lại / trùng
          |
          v
  Step đọc JobParameters để xử lý
```

Một điểm phải hiểu ngay từ đầu: annotation `@Scheduled` **không tự biến thời gian cron thành `JobParameters`**. Developer cần viết mã tính giá trị, tạo `JobParameters` và gọi `JobLauncher`, hoặc dùng một bộ điều phối batch có chức năng tương đương.

## 2. JobParameters, JobInstance và JobExecution

Trong Spring Batch, ba khái niệm này gắn chặt với quyết định có thể chạy lại một job:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| `JobParameters` | Tập tham số đầu vào cho một lần chạy | `businessDate=2026-11-16` |
| `JobInstance` | Một instance logic của job, được xác định từ tên job và các tham số **identifying** | `dailyOrdersJob` cho ngày 16/11 |
| `JobExecution` | Một lần thực thi thực tế của instance đó | Lần chạy đầu thất bại, lần chạy thứ hai tiếp tục/restart |

Quan hệ logic:

```text
JobInstance: dailyOrdersJob / businessDate=2026-11-16
    |
    +-- JobExecution #101  -> FAILED
    |
    +-- JobExecution #102  -> COMPLETED (restart)

JobInstance: dailyOrdersJob / businessDate=2026-11-17
    |
    +-- JobExecution #103  -> COMPLETED
```

Spring Batch xác định một `JobInstance` dựa trên **tên job + giá trị của các tham số có cờ identifying**. Những tham số không identifying vẫn được lưu cho `JobExecution` và vẫn có thể được step đọc, nhưng không tham gia xác định instance logic.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("triggerSource", "scheduler", false)
        .toJobParameters();
```

Ở ví dụ này, `businessDate` là identifying, còn `triggerSource` là non-identifying. Nếu lần sau thay `triggerSource` thành `manual` nhưng vẫn giữ `businessDate`, Spring Batch vẫn xem là cùng một job instance. Điều này là chủ đích khi một job thất bại cần chạy lại thủ công cho cùng ngày.

### 2.1. Kết quả khi gọi JobLauncher nhiều lần

| Trạng thái instance trước đó | JobParameters của lần gọi mới | Kết quả thường gặp |
|---|---|---|
| Chưa có instance | Identifying parameters mới | Tạo instance và execution mới |
| Đang chạy | Cùng identifying parameters | `JobExecutionAlreadyRunningException` |
| Đã hoàn tất | Cùng identifying parameters | `JobInstanceAlreadyCompleteException` |
| Thất bại và cho phép restart | Cùng identifying parameters | Tạo `JobExecution` mới để restart instance cũ |
| Đã hoàn tất | Identifying parameters khác | Tạo job instance mới |

Kết quả cụ thể còn chịu ảnh hưởng của `JobRepository`, cấu hình restartability, trạng thái step và kiểm tra tham số. Ví dụ, job được đánh dấu không restart được có thể ném `JobRestartException` khi được yêu cầu chạy lại.

### 2.2. JobParameters không phải ExecutionContext

`JobParameters` mô tả yêu cầu đầu vào, chẳng hạn ngày nghiệp vụ, tên tệp hoặc định danh đợt xử lý. `ExecutionContext` lưu trạng thái trong quá trình chạy, chẳng hạn vị trí đọc cuối cùng để restart.

Không nên cập nhật một tham số ngày để làm checkpoint. Thay vào đó:

```text
JobParameters:
    businessDate = 2026-11-16
    inputFile = orders-2026-11-16.csv

Step ExecutionContext:
    lastProcessedOrderId = 15600
    readOffset = 327680
```

Spring Batch lưu cả tham số và context vào repository khi sử dụng `JobRepository` có persistence. Tránh đưa password, token, thông tin cá nhân nhạy cảm hoặc payload lớn vào `JobParameters` vì giá trị có thể tồn tại trong metadata database và log.

## 3. Thiết kế tham số từ lịch chạy

Nên thiết kế `JobParameters` theo **đơn vị dữ liệu nghiệp vụ mà job xử lý**, thay vì chỉ lấy thời điểm scheduler vừa được kích hoạt.

| Tham số | Ví dụ | Identifying? | Lưu ý |
|---|---|---|---|
| `businessDate` | `2026-11-16` | Thường là có | Một instance cho mỗi ngày nghiệp vụ |
| `billingPeriod` | `2026-11` | Thường là có | Một instance cho mỗi kỳ kế toán |
| `tenantId` | `tenant-a` | Có khi mỗi tenant là một instance riêng | Dùng cùng `businessDate` để tách tenant |
| `inputFile` | `orders-2026-11-16.csv` | Tùy nghiệp vụ | Có thể là khóa nhận diện đợt nhập |
| `triggerSource` | `scheduler` / `manual` | Thường không | Nguồn gọi hỗ trợ audit |
| `requestedBy` | `nightly-cron` | Thường không | Không nên chứa thông tin cá nhân nhạy cảm |
| `scheduledAt` | Timestamp theo thời điểm lịch dự kiến | Tùy chính sách | Tránh vô tình biến một ngày thành nhiều instance |
| `run.id` | `25` | Chỉ khi thật sự cần mỗi lần là instance mới | Dùng tùy tiện sẽ làm hỏng ngữ nghĩa restart |

### 3.1. Tại sao không luôn dùng timestamp làm identifying parameter?

Một mẫu thường gặp nhưng không phù hợp với mọi job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLong("run.id", System.currentTimeMillis())
        .toJobParameters();
```

Mỗi lần gọi thường tạo một instance mới, kể cả hai lần đều yêu cầu xử lý **cùng ngày nghiệp vụ**. Vì vậy:

1. Một retry thủ công dễ bị xem là đợt xử lý hoàn toàn mới, thay vì restart instance thất bại.
2. Hai scheduler cùng kích hoạt có thể tạo hai instance khác nhau và xử lý trùng dữ liệu.
3. Timestamp độ phân giải millisecond không phải cách bảo đảm tính duy nhất tuyệt đối trong mọi điều kiện concurrency.
4. Dễ xuất hiện nhiều bản ghi metadata và dữ liệu đầu ra trùng nếu logic nghiệp vụ không idempotent.

Timestamp identifying phù hợp hơn với một job có ngữ nghĩa “mỗi lần kích hoạt là một công việc độc lập”. Với job tổng hợp doanh thu theo ngày, identifying parameter là `businessDate` thường thể hiện đúng ý định hơn.

### 3.2. Chọn business date theo lịch

Với cron chạy 02:00 ngày D để xử lý ngày D−1:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.now(businessZone).minusDays(1);
```

Nên tính theo timezone nghiệp vụ rõ ràng. `LocalDate.now()` không truyền zone sẽ phụ thuộc timezone mặc định của JVM; local machine, container và CI có thể cho ra ngày khác nhau.

Nếu scheduler chạy muộn qua ranh giới ngày, tính ngày nghiệp vụ từ **thời điểm thực tế callback được gọi** có thể chọn nhầm kỳ. Với yêu cầu chạy bù chính xác theo lịch dự kiến, bộ điều phối cần lưu/truyền **scheduled fire time** (thời điểm dự kiến chạy) và suy ra `businessDate` từ đó. Quartz hoặc lịch bên ngoài có thể cung cấp thông tin này, trong khi phương thức `@Scheduled` thông thường không nhận trực tiếp fire time làm đối số.

## 4. Cấu hình Spring Boot cho job chạy qua scheduler

Các ví dụ ở phần tiếp theo sử dụng **Java 17+, Spring Boot 3.x và Spring Batch 5.x**. Một số package/builder/API thay đổi trong Spring Batch 6.x; khi dùng phiên bản khác hãy đối chiếu tài liệu API tương ứng.

### 4.1. Dependencies

Ví dụ `build.gradle` (Spring Boot plugin hoặc BOM quản lý phiên bản):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-batch` hỗ trợ hạ tầng batch và JDBC repository theo cấu hình ứng dụng; database driver và `DataSource` phù hợp vẫn cần được thiết lập. Nếu dự án đã có các starter trên, không cần thêm bản khai báo trùng.

### 4.2. Properties cho lịch chạy

`src/main/resources/application.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false

app:
  jobs:
    daily-orders:
      enabled: true
      cron: "0 0 2 * * *"
      zone: "Asia/Ho_Chi_Minh"
```

`spring.batch.job.enabled=false` ngăn **Spring Boot tự chạy job khi application startup**. Nó không ngăn `@Scheduled`, cũng không cấm các nơi khác gọi `JobLauncher`. Điều này hữu ích khi muốn scheduler là nơi chủ động phát lệnh chạy.

Các key `app.jobs.daily-orders.*` do ứng dụng tự định nghĩa. Spring không tự hiểu chúng cho tới khi mã scheduler đọc bằng `@Value` hoặc `@ConfigurationProperties`.

Cron của Spring có **sáu trường**:

```text
giây  phút  giờ  ngày-trong-tháng  tháng  ngày-trong-tuần
  0     0    2         *            *         *
```

Chuỗi `0 0 2 * * *` có nghĩa là chạy lúc **02:00:00 mỗi ngày** trong timezone được chỉ định. Cần phân biệt cú pháp Spring cron với cron của Linux và một số bộ lập lịch khác.

### 4.3. Bật xử lý lịch và cung cấp Clock

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class BatchSchedulingConfiguration {

    @Bean
    Clock batchClock() {
        return Clock.systemUTC();
    }
}
```

`@EnableScheduling` kích hoạt hạ tầng xử lý `@Scheduled` trong Spring context. `Clock` là dependency thời gian được tiêm vào scheduler, nhờ đó unit test có thể dùng `Clock.fixed(...)` mà không phụ thuộc đồng hồ máy thật.

## 5. Ví dụ hoàn chỉnh: scheduler tạo JobParameters và gọi JobLauncher

Giả sử có một bean `Job` tên `dailyOrdersJob` để xử lý đơn hàng của ngày trước đó. Lớp scheduler như sau:

```java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.JobParametersInvalidException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "app.jobs.daily-orders",
        name = "enabled",
        havingValue = "true")
public class DailyOrdersScheduler {

    private static final Logger log =
            LoggerFactory.getLogger(DailyOrdersScheduler.class);

    private final JobLauncher jobLauncher;
    private final Job dailyOrdersJob;
    private final Clock clock;
    private final ZoneId businessZone;

    public DailyOrdersScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailyOrdersJob") Job dailyOrdersJob,
            Clock clock,
            @Value("${app.jobs.daily-orders.zone:Asia/Ho_Chi_Minh}")
                    String zoneId) {
        this.jobLauncher = jobLauncher;
        this.dailyOrdersJob = dailyOrdersJob;
        this.clock = clock;
        this.businessZone = ZoneId.of(zoneId);
    }

    @Scheduled(
            cron = "${app.jobs.daily-orders.cron}",
            zone = "${app.jobs.daily-orders.zone:Asia/Ho_Chi_Minh}")
    public void triggerDailyOrders() {
        LocalDate businessDate =
                LocalDate.now(clock.withZone(businessZone)).minusDays(1);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .addString("triggerSource", "scheduler", false)
                .toJobParameters();

        try {
            JobExecution execution = jobLauncher.run(
                    dailyOrdersJob, parameters);

            log.info(
                    "Submitted dailyOrdersJob: businessDate={}, "
                            + "executionId={}, status={}",
                    businessDate,
                    execution.getId(),
                    execution.getStatus());

        } catch (JobExecutionAlreadyRunningException ex) {
            log.info(
                    "dailyOrdersJob is already running for businessDate={}",
                    businessDate);

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info(
                    "dailyOrdersJob already completed for businessDate={}",
                    businessDate);

        } catch (JobRestartException | JobParametersInvalidException ex) {
            log.error(
                    "Cannot launch dailyOrdersJob for businessDate={}",
                    businessDate,
                    ex);
        }
    }
}
```

**Những điểm quan trọng trong đoạn mã:**

1. `@Scheduled` gọi method không có tham số; method tự tính `businessDate` rồi xây dựng `JobParameters`.
2. `businessDate` identifying: một ngày nghiệp vụ chỉ có một `JobInstance` cho job này.
3. `triggerSource` non-identifying: chỉ dùng để ghi nhận nguồn gọi, không tạo instance mới.
4. `@Qualifier` chọn đúng job khi ứng dụng định nghĩa nhiều bean `Job`.
5. `@ConditionalOnProperty` cho phép tắt riêng scheduler trong môi trường test bằng `app.jobs.daily-orders.enabled=false`.
6. Bắt riêng trường hợp instance đang chạy và đã hoàn thành giúp log rõ nguyên nhân. Không coi mọi trường hợp này là lỗi hạ tầng.
7. `JobLauncher.run(...)` có thể thực thi đồng bộ hoặc trả về sớm nếu được cấu hình chạy bất đồng bộ. Vì vậy log dùng từ **Submitted** và in trạng thái lúc trả về; không tự khẳng định job đã hoàn thành.

Trong hệ thống sản xuất, việc xử lý exception nên đi cùng metrics, cảnh báo và cơ chế retry có kiểm soát. Không “nuốt” `JobRestartException` hoặc `JobParametersInvalidException` mà không ghi nhận.

### 5.1. Job nhận JobParameters bằng StepScope

Đây là cấu hình demo tối giản cho bean `dailyOrdersJob`. `Tasklet` nhận `businessDate` qua Spring Expression Language (SpEL):

```java
import java.time.LocalDate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class DailyOrdersJobConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(DailyOrdersJobConfiguration.class);

    @Bean
    Job dailyOrdersJob(
            JobRepository repository,
            @Qualifier("dailyOrdersStep") Step step) {
        return new JobBuilder("dailyOrdersJob", repository)
                .start(step)
                .build();
    }

    @Bean
    Step dailyOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            @Qualifier("ordersForDateTasklet") Tasklet tasklet) {
        return new StepBuilder("dailyOrdersStep", repository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean
    @StepScope
    Tasklet ordersForDateTasklet(
            @Value("#{jobParameters['businessDate']}")
                    String dateText) {
        return (contribution, chunkContext) -> {
            LocalDate businessDate = LocalDate.parse(dateText);
            log.info("Processing orders for {}", businessDate);

            // Thực hiện xử lý nghiệp vụ cho businessDate tại đây.
            return RepeatStatus.FINISHED;
        };
    }
}
```

`@StepScope` bảo đảm việc resolve `jobParameters['businessDate']` diễn ra khi step có ngữ cảnh thực thi. Nếu tạo Tasklet singleton bằng cách resolve tham số ngay lúc application startup, giá trị runtime của từng lần chạy sẽ không có sẵn.

Ví dụ trên chỉ ghi log để minh họa cách truyền tham số. Trong batch thực tế, `businessDate` thường được dùng để giới hạn câu SQL, chọn tệp đầu vào, truyền vào reader hoặc xác định vùng dữ liệu xuất ra.

## 6. Lấy JobParameters trong các thành phần khác

Ngoài cách tiêm SpEL vào bean `@StepScope`, code có thể lấy tham số từ `StepExecution` và `JobExecution`.

### 6.1. Trong listener

```java
public class BusinessDateListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        String date = stepExecution.getJobParameters()
                .getString("businessDate");

        if (date == null) {
            throw new IllegalArgumentException(
                    "Missing required job parameter: businessDate");
        }

        LocalDate parsed = LocalDate.parse(date);
        // Kiểm tra ngày nghiệp vụ hoặc ghi log.
    }
}
```

Các kiểu import chính trong Spring Batch 5.x là `org.springframework.batch.core.StepExecution` và `org.springframework.batch.core.StepExecutionListener`.

### 6.2. Trong Tasklet qua ChunkContext

Một `Tasklet` có thể nhận `StepExecution` từ `ChunkContext`:

```java
StepExecution stepExecution =
        chunkContext.getStepContext().getStepExecution();

String businessDate = stepExecution
        .getJobParameters().getString("businessDate");
```

Không nên coi `JobParameters` là cơ chế chia sẻ mutable state giữa các step. Với trạng thái tính được trong quá trình job chạy, sử dụng `ExecutionContext` hoặc cơ chế lưu nghiệp vụ phù hợp.

## 7. Ranh giới giữa scheduled time và business date

Hai khái niệm này khác nhau:

- **Fire time**: thời điểm hệ thống phát trigger, ví dụ `2026-11-17T02:00:00+07:00`.
- **Business date**: ngày dữ liệu cần xử lý, ví dụ `2026-11-16`.

| Tình huống | Fire time | Business date mong muốn |
|---|---|---|
| Lịch bình thường: 02:00 ngày hôm sau | 17/11/2026 02:00 +07 | 16/11/2026 |
| Scheduler trễ 15 phút | 17/11/2026 02:15 +07 | 16/11/2026 |
| Máy bị dừng, cần chạy bù ngày đã bỏ lỡ | 20/11/2026 10:00 +07 | Ngày thiếu, ví dụ 17/11/2026 |
| Operator chạy lại một job lỗi | 20/11/2026 11:00 +07 | Ngày của job lỗi, ví dụ 16/11/2026 |

Ví dụ mục 5 dùng `LocalDate.now(clock.withZone(businessZone)).minusDays(1)`. Đây là quy tắc rõ ràng cho lịch hoạt động bình thường, nhưng **không phải giải pháp tự động catch-up** các kỳ đã bỏ lỡ. Nếu máy bị dừng ba ngày, Spring `@Scheduled` thông thường không tự tạo ba job instances cho các ngày cũ.

Với yêu cầu xử lý không bỏ sót kỳ, hãy có một nguồn dữ liệu bền vững xác định các business date cần chạy: bảng lịch nghiệp vụ, hàng đợi trigger, scheduler có persistence hoặc quy trình backfill. Mỗi kỳ cần được truyền qua `JobParameters` một cách rõ ràng.

### 7.1. Timezone và DST

`@Scheduled(..., zone = "...")` quyết định giờ cron được diễn giải trong timezone nào. `Clock` và `ZoneId` trong code tính ngày nghiệp vụ phải dùng cùng quy tắc nghiệp vụ.

Ở khu vực có daylight saving time, một giờ có thể bị bỏ qua hoặc lặp lại vào ngày đổi giờ. Khi đó cần quy định rõ:

- Nếu cron rơi vào giờ không tồn tại thì xử lý thế nào?
- Nếu một giờ xuất hiện hai lần thì có cho phép chạy hai lần không?
- Một ngày nghiệp vụ xác định theo timezone nào?

Đối với quy trình kế toán/tài chính, nên xác định ngày nghiệp vụ dựa trên lịch chính thức của doanh nghiệp thay vì suy ra đơn giản từ đồng hồ local.

## 8. Lập lịch định kỳ khác nhau đòi hỏi cách sinh tham số khác nhau

### 8.1. Hàng ngày

```java
LocalDate date = LocalDate.now(businessZone).minusDays(1);
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", date.toString(), true)
        .toJobParameters();
```

Một job instance cho mỗi ngày nghiệp vụ là hợp lý nếu mỗi ngày chỉ cần một kết quả cuối.

### 8.2. Hàng giờ

Nếu dữ liệu được chia thành các cửa sổ theo giờ, nên có một khóa thể hiện **đầu khoảng thời gian**:

```java
ZonedDateTime now = ZonedDateTime.now(businessZone);
ZonedDateTime previousHour = now.truncatedTo(
        java.time.temporal.ChronoUnit.HOURS).minusHours(1);

JobParameters parameters = new JobParametersBuilder()
        .addString("windowStart", previousHour.toOffsetDateTime().toString(), true)
        .toJobParameters();
```

Với timezone có DST, offset trong giá trị giúp phân biệt hai cửa sổ giờ local trùng tên. Với hệ thống phân tán, thường chuẩn hóa ranh giới thời gian bằng `Instant`/UTC trong job parameters, đồng thời lưu timezone nghiệp vụ khi cần hiển thị.

### 8.3. Theo kỳ tháng

```java
YearMonth period = YearMonth.now(businessZone).minusMonths(1);

JobParameters parameters = new JobParametersBuilder()
        .addString("billingPeriod", period.toString(), true)
        .toJobParameters();
```

Ví dụ cần `import java.time.YearMonth;`. Mỗi kỳ tháng là một job instance; chạy lại kỳ tháng đã hoàn thành phải tuân theo quy trình reprocess riêng, không chỉ đổi một `run.id` để bỏ qua quy tắc duplicate.

## 9. Restart, retry và chạy bù từ scheduler

### 9.1. Job thất bại và scheduler kích hoạt lại

Nếu job ngày 16/11 thất bại và scheduler hoặc operator gọi lại với `businessDate=2026-11-16`, Spring Batch có thể tạo một execution mới thuộc cùng instance và thực hiện restart, tùy cấu hình job/step và trạng thái repository.

Ví dụ:

```text
16/11 business date
       |
       +-- First launch -> JobExecution 200 (FAILED)
       |
       +-- Retry same identifying parameters
                         |
                         +-- JobExecution 201 (COMPLETED)
```

Không thêm một identifying `run.id` ngẫu nhiên ở retry nếu cần tận dụng checkpoint và ngữ nghĩa restart.

### 9.2. Job đã hoàn tất, scheduler gọi trùng

Nếu scheduler được gọi lại cùng `businessDate` sau khi job đã `COMPLETED`, `JobLauncher` thông thường sẽ báo `JobInstanceAlreadyCompleteException`. Đây là một lớp bảo vệ hữu ích chống chạy trùng ở mức instance, nhưng **không bảo đảm tính idempotent của mọi hệ thống bên ngoài**. Ví dụ một HTTP API có thể đã nhận yêu cầu dù database local rollback.

Đối với quy trình dễ phát sinh side effect, cần kết hợp idempotency key, unique constraint, trạng thái xuất bản hoặc cơ chế outbox tùy trường hợp.

### 9.3. Muốn chạy lại dữ liệu đã hoàn tất

Nếu yêu cầu thật sự là *reprocess* một ngày đã hoàn thành, cần quyết định cách định danh lần xử lý mới:

- Xác định một phiên bản dữ liệu hoặc `reprocessVersion` có ý nghĩa nghiệp vụ làm identifying parameter.
- Lưu lý do xử lý lại và giữ audit trail.
- Quy định có ghi đè, cộng dồn hay tạo bản kết quả mới; bảo vệ dữ liệu khỏi xử lý trùng.

Không nên sửa trạng thái bảng `BATCH_JOB_EXECUTION` trực tiếp để biến `COMPLETED` thành `FAILED`. Metadata còn có thông tin step, version và context; thao tác SQL thủ công có thể tạo trạng thái không nhất quán.

### 9.4. RunIdIncrementer có tự động chạy mỗi lần cron không?

Không. Dù job được cấu hình:

```java
new JobBuilder("someJob", jobRepository)
        .incrementer(new RunIdIncrementer())
        .start(step)
        .build();
```

thì lời gọi `jobLauncher.run(job, parameters)` vẫn dùng **chính bộ tham số được truyền vào**. Incrementer không tự chạy chỉ vì scheduler gọi `JobLauncher`. Chức năng chạy “instance kế tiếp” của `JobOperator` có thể sử dụng incrementer, nhưng cần chọn cách đó có chủ đích. Với job định danh theo `businessDate`, tự tăng `run.id` có thể phá hỏng thiết kế một instance cho mỗi ngày.

## 10. Nhiều scheduler, nhiều instance ứng dụng và chạy song song

Một ứng dụng có thể chạy nhiều replica. Nếu mọi replica đều bật `@EnableScheduling`, cùng cron có thể kích hoạt nhiều phương thức ở cùng thời điểm:

```text
Replica A -- @Scheduled 02:00 --+
                                +--> JobRepository --> dailyOrdersJob
Replica B -- @Scheduled 02:00 --+
```

Đối với job có cùng identifying parameters, `JobRepository` thường phát hiện instance đang chạy hoặc đã hoàn thành. Tuy nhiên, vẫn có race condition tại thời điểm khởi động, và repository **không thay thế hoàn toàn một hệ thống điều phối phân tán**.

Các hướng thiết kế:

| Quy mô | Hướng điều phối có thể áp dụng |
|---|---|
 Một JVM, lịch đơn giản | Spring `@Scheduled` và `JobLauncher` |
 Nhiều replica cần một nơi phát lệnh | Leader election hoặc distributed scheduling lock |
 Cần lưu lịch, misfire, clustering | Quartz với persistent job store hoặc bộ scheduler độc lập |
 Hạ tầng orchestration sẵn có | Kubernetes CronJob, Airflow, enterprise scheduler… truyền tham số cho batch |
 Nhiều kỳ cần backfill và audit | Bảng kế hoạch chạy/queue sự kiện kèm business key bền vững |

**Lưu ý:** cố tình tạo `run.id` mới ở mỗi replica sẽ khiến các replica chạy thành các job instance khác nhau, làm tăng nguy cơ nhân đôi side effect.

### 10.1. Scheduling thread và JobLauncher thread

Với launcher đồng bộ, phương thức `@Scheduled` có thể bị giữ tới khi job kết thúc; lịch khác cùng pool có thể bị trễ. Với launcher bất đồng bộ, method có thể trả về ngay khi job vẫn đang chạy. Dù theo chế độ nào, cần quyết định chính sách cho trigger mới khi lần trước còn chạy: bỏ qua, queue, từ chối hoặc chạy song song.

`spring.task.scheduling.pool.size` là property Boot có thể cấu hình số luồng scheduling khi dùng `ThreadPoolTaskScheduler` auto-configured, nhưng tăng số luồng không đồng nghĩa được phép chạy nhiều instance cùng nghiệp vụ. Quyền xử lý song song phải được thiết kế ở cả scheduler, repository và logic job.

### 10.2. Exactly-once có đạt được chỉ nhờ JobRepository?

Không thể suy ra “exactly-once end-to-end” từ việc chỉ dùng identifying parameters. `JobRepository` quản lý trạng thái batch; hiệu ứng bên ngoài như gửi email, gọi API, ghi object storage hoặc publish message có thể cần cơ chế chống trùng độc lập. Tương tự, nếu có hai job khác tên cùng sửa cùng một tập dữ liệu, khóa JobInstance của từng job không tự phối hợp được chúng.

## 11. Kết nối Quartz hoặc scheduler bên ngoài

Spring `@Scheduled` là lựa chọn gọn cho lịch đơn giản. Quartz, enterprise scheduler hoặc orchestration platform thường cung cấp metadata về trigger, bao gồm thời điểm dự kiến chạy và mã lịch. Khi nhận trigger, nên chuyển thông tin thành bộ tham số nghiệp vụ **tại ranh giới ứng dụng**:

```text
Quartz JobExecutionContext
  scheduledFireTime
  jobDataMap
        |
        v
  BusinessDateResolver
        |
        v
  JobParametersBuilder
        |
        v
  Spring Batch JobLauncher.run(...)
```

Không nhầm `org.quartz.JobExecutionContext` với `org.springframework.batch.core.JobExecution`: chúng thuộc hai framework và đảm nhận hai vai trò khác nhau.

Ví dụ logic ánh xạ khi đã có thời điểm kế hoạch từ scheduler:

```java
Instant scheduledInstant = scheduledFireTime.toInstant();

LocalDate businessDate = scheduledInstant
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toLocalDate()
        .minusDays(1);

JobParameters params = new JobParametersBuilder()
        .addString("businessDate", businessDate.toString(), true)
        .addString("triggerSource", "quartz", false)
        .toJobParameters();
```

`scheduledFireTime` trong đoạn trên tượng trưng cho `java.util.Date` lấy từ `JobExecutionContext.getScheduledFireTime()` của Quartz. Dù callback đến muộn, tham số vẫn phản ánh ngày tương ứng với lịch **được dự kiến** kích hoạt. Quy tắc trừ một ngày vẫn phải là quy tắc nghiệp vụ được thống nhất.

Nếu scheduler bên ngoài khởi chạy CLI/HTTP thay vì gọi trực tiếp `JobLauncher`, điểm nhận lệnh vẫn nên có validation, kiểm tra quyền phù hợp, ánh xạ tham số và cơ chế theo dõi instance như trên.

## 12. Kiểm tra JobParameters trước khi job bắt đầu

Lập lịch đúng cron vẫn có thể tạo tham số sai: ngày không tồn tại, format sai, không có tenant, hoặc ngày tương lai không được phép xử lý.

Có thể dùng `JobParametersValidator` khi cấu hình job để thất bại sớm nếu input không hợp lệ:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public class BusinessDateValidator implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String value = parameters.getString("businessDate");
        if (value == null || value.isBlank()) {
            throw new JobParametersInvalidException(
                    "Missing businessDate");
        }

        try {
            LocalDate.parse(value);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must use yyyy-MM-dd", ex);
        }
    }
}
```

Trong cấu hình Spring Batch 5.x, có thể gắn validator vào builder:

```java
return new JobBuilder("dailyOrdersJob", jobRepository)
        .validator(new BusinessDateValidator())
        .start(dailyOrdersStep)
        .build();
```

Validator hỗ trợ bảo vệ cả lệnh chạy từ scheduler lẫn lệnh chạy thủ công. Nếu nghiệp vụ cần kiểm tra tenant, tập kỳ được phép xử lý hoặc quan hệ giữa `startDate` và `endDate`, mở rộng validator theo hợp đồng input của job.

## 13. Unit test scheduler mà không chờ cron

Test logic sinh tham số **không cần chờ đến 02:00**, cũng không cần bật Spring scheduling thật. Ta có thể khởi tạo scheduler với `Clock.fixed(...)`, mock `JobLauncher` và kiểm tra chính xác `JobParameters` được truyền vào.

Ví dụ JUnit 5 + Mockito + `spring-batch-test`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.test.MetaDataInstanceFactory;

@ExtendWith(MockitoExtension.class)
class DailyOrdersSchedulerTest {

    @Mock
    JobLauncher jobLauncher;

    @Mock
    Job dailyOrdersJob;

    @Test
    void passesPreviousBusinessDateAsIdentifyingParameter()
            throws Exception {

        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-11-16T20:00:00Z"),
                ZoneOffset.UTC);

        DailyOrdersScheduler scheduler = new DailyOrdersScheduler(
                jobLauncher,
                dailyOrdersJob,
                fixedClock,
                "Asia/Ho_Chi_Minh");

        when(jobLauncher.run(eq(dailyOrdersJob), any(JobParameters.class)))
                .thenReturn(MetaDataInstanceFactory.createJobExecution());

        scheduler.triggerDailyOrders();

        ArgumentCaptor<JobParameters> captured =
                ArgumentCaptor.forClass(JobParameters.class);

        verify(jobLauncher).run(eq(dailyOrdersJob), captured.capture());

        JobParameters parameters = captured.getValue();

        // 20:00 UTC ngày 16/11 = 03:00 ngày 17/11 giờ Việt Nam.
        assertEquals("2026-11-16",
                parameters.getString("businessDate"));
        assertEquals("scheduler",
                parameters.getString("triggerSource"));
        assertTrue(parameters.getParameters()
                .get("businessDate").isIdentifying());
        assertFalse(parameters.getParameters()
                .get("triggerSource").isIdentifying());
    }
}
```

Test này chứng minh **scheduler tính và truyền đúng tham số**. Nó không chứng minh job được chạy thật, metadata được ghi vào database hay cron kích hoạt đúng thời gian.

### 13.1. Kiểm tra cron expression riêng

Với Spring Framework có `CronExpression`, có thể kiểm tra thời điểm kích hoạt tiếp theo theo timezone cụ thể:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.ZoneId;
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronExpression;

class DailyOrdersCronTest {

    @Test
    void nextFireOccursAtTwoAmInBusinessZone() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime after = ZonedDateTime.of(
                2026, 11, 16, 1, 30, 0, 0, zone);

        ZonedDateTime next = CronExpression
                .parse("0 0 2 * * *")
                .next(after);

        assertEquals(
                ZonedDateTime.of(2026, 11, 16, 2, 0, 0, 0, zone),
                next);
    }
}
```

Đây là test của **quy tắc cron**; ứng dụng vẫn cần cấu hình `@Scheduled`, scheduler bean và các property chính xác. Đặc biệt không sử dụng sleep nhiều giây/phút chỉ để chờ cron xảy ra trong unit test.

## 14. Integration test chạy job với tham số từ test

Kiểm thử tích hợp nên gọi `JobLauncherTestUtils` hoặc `JobLauncher` bằng `JobParameters` do test dựng, sau đó kiểm tra trạng thái thực thi và kết quả nghiệp vụ.

Ví dụ dùng job demo ở mục 5.1, profile test có H2 datasource và metadata schema:

`src/test/resources/application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:daily_orders_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ''
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

app:
  jobs:
    daily-orders:
      enabled: false
      cron: "0 0 2 * * *"
      zone: "Asia/Ho_Chi_Minh"
```

`app.jobs.daily-orders.enabled=false` tắt **scheduler bean**, nhưng không tắt định nghĩa `dailyOrdersJob`. Test chủ động chạy job:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class DailyOrdersJobIT {

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Autowired
    JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("dailyOrdersJob")
    Job dailyOrdersJob;

    @BeforeEach
    void prepare() {
        repositoryTestUtils.removeJobExecutions();
        launcherTestUtils.setJob(dailyOrdersJob);
    }

    @Test
    void completesForRequestedBusinessDate() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .addString("triggerSource", "integration-test", false)
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

Test này giả định application context đã đăng ký các bean `Job`, `Step`, `JobRepository` và transaction manager tương ứng với demo. `JobRepositoryTestUtils.removeJobExecutions()` xóa metadata của **toàn bộ repository test**; không dùng khi có test khác đang chia sẻ database đó trong lúc chạy song song.

Với ứng dụng thật, cần kiểm tra thêm dữ liệu được lưu bởi reader/writer, xử lý rollback hoặc checkpoint tùy mục tiêu. `BatchStatus.COMPLETED` riêng lẻ chưa chứng minh kết quả nghiệp vụ đúng.

### 14.1. Test restart đúng nghĩa

Để kiểm tra restart, cần:

1. Chạy cùng `businessDate` lần đầu với điều kiện khiến job/step thực sự thất bại.
2. Giữ nguyên metadata và `ExecutionContext` trong `JobRepository`.
3. Khắc phục điều kiện gây lỗi, rồi khởi chạy lại với cùng identifying parameters.
4. Kiểm tra `JobInstance` không đổi, có `JobExecution` mới, và reader/step tiếp tục theo quy tắc restart.

Không gọi cleanup giữa hai lần chạy của cùng một restart test; nếu xóa metadata thì lần sau đã trở thành instance mới.

## 15. Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Job chạy khi app vừa startup rồi lại chạy theo cron | Spring Boot auto-run và `@Scheduled` đều đang hoạt động | Đặt `spring.batch.job.enabled=false` khi scheduler phải điều phối |
| `JobInstanceAlreadyCompleteException` | Cùng identifying parameters đã `COMPLETED` | Xem đây là duplicate phù hợp, hoặc thiết kế reprocess instance mới có chủ đích |
| `JobExecutionAlreadyRunningException` | Một job instance đã chạy, có trigger khác tới | Chọn chính sách bỏ qua/queue; kiểm tra nhiều replica |
| `JobParametersInvalidException` | Thiếu hoặc sai định dạng `businessDate` | Kiểm tra builder và `JobParametersValidator` |
| Lịch chạy đúng giờ nhưng xử lý sai ngày | Dùng timezone JVM hoặc `LocalDate.now()` theo giờ hệ thống | Dùng `ZoneId` nghiệp vụ và kiểm thử bằng `Clock.fixed` |
| Chạy bù ngày cũ lại xử lý hôm qua | Scheduler chỉ tính ngày dựa trên giờ thực tế | Truyền business date cụ thể từ kế hoạch chạy bù |
| Retry tạo instance mới | Thêm `run.id`/timestamp identifying vào mọi lần gọi | Giữ cùng identifying parameters khi restart |
| `@Scheduled` không gọi method | Thiếu `@EnableScheduling`, bean không thuộc Spring context, property cron sai, scheduler bị tắt | Kiểm tra bean registration, profile và cấu hình cron |
| Method `@Scheduled` được gọi từ hai replica | Mỗi replica có scheduler riêng | Dùng điều phối phân tán hoặc một scheduler trung tâm |
| Step nhận `businessDate=null` | Thiếu tham số hoặc bean không được tạo đúng `@StepScope` | Validate input, sử dụng `@StepScope` và đọc đúng key |
| Log báo submitted nhưng không thấy hoàn thành | `JobLauncher` bất đồng bộ hoặc job lỗi sau khi launch | Tra cứu `JobExecution` cuối cùng, metrics và exception của step |
| Metadata nhiều instance không mong đợi | Identifying timestamp thay đổi ở mọi lần kích hoạt | Thiết kế khóa nghiệp vụ ổn định |
| Job trùng kết quả dù instance được bảo vệ | Side effect bên ngoài không idempotent hoặc có job khác cùng sửa dữ liệu | Thiết kế idempotency, constraints, locks và audit phù hợp |

## 16. Quy trình thiết kế tham số cho một job được lập lịch

Khi bắt đầu triển khai scheduling trong Spring Batch, nên làm rõ từng quyết định sau:

1. **Đơn vị công việc:** một ngày, một kỳ, một tenant, một tệp hay một sự kiện?
2. **Khóa nhận diện:** tham số nào identifying để tạo đúng một instance logic cho công việc?
3. **Nguồn thời gian:** tính từ fire time dự kiến hay thời điểm callback thật sự chạy? Timezone nào được dùng?
4. **Chính sách trễ và bỏ lỡ lịch:** bỏ qua, queue, backfill theo từng kỳ hay cảnh báo để xử lý?
5. **Chính sách chạy lại:** cùng instance khi `FAILED`, từ chối khi `COMPLETED`, hoặc reprocess có phiên bản riêng?
6. **Concurrency:** nhiều luồng/máy có thể phát lệnh cùng lúc không, và ai giữ quyền điều phối?
7. **Truyền tham số:** sử dụng `JobParametersBuilder`, validation, `JobLauncher` và bean `@StepScope`.
8. **Quan sát vận hành:** log job name, business key, execution ID, trạng thái cuối; cảnh báo khi job thất bại.
9. **Kiểm thử:** unit test tính business date bằng `Clock.fixed`, test cron expression, integration test repository và kết quả batch.

### Bài tập thực hành

**Bài 1 — Một job instance cho mỗi ngày**

- Cấu hình cron chạy lúc 01:30 theo `Asia/Ho_Chi_Minh`.
- Truyền `businessDate` là ngày hôm trước dưới dạng `yyyy-MM-dd` và đánh dấu identifying.
- Đánh dấu `triggerSource=scheduler` là non-identifying.
- Dùng Mockito capture `JobParameters` để xác minh ngày nghiệp vụ từ một `Clock.fixed`.

**Bài 2 — Retry và duplicate**

- Chạy integration test với cùng `businessDate` hai lần.
- Quan sát khi job đã `COMPLETED` thì lời gọi thứ hai bị từ chối theo ngữ nghĩa instance.
- Tạo một ca lỗi có chủ đích và thử restart cùng identifying parameters; kiểm tra hai `JobExecution` thuộc cùng `JobInstance`.

**Bài 3 — Backfill nhiều ngày**

- Thiết kế một service nhận danh sách ngày thiếu, ví dụ 10/11, 11/11, 12/11.
- Tạo đúng một yêu cầu `JobParameters` cho mỗi ngày; không lấy `LocalDate.now()` bên trong mỗi iteration.
- Xác định hành vi nếu một ngày đang chạy hoặc đã hoàn thành; không tạo `run.id` ngẫu nhiên để vượt qua duplicate guard.

**Bài 4 — Hai replica**

- Mô phỏng hai lần gọi `JobLauncher.run(...)` có cùng identifying parameters.
- Xác định exception/trạng thái mà `JobRepository` thực tế trả về trong môi trường test.
- Phác thảo cách bảo đảm chỉ một scheduler phát lệnh và cách chống lặp hiệu ứng nghiệp vụ ở writer.

## 17. Tài liệu tham khảo

- [Spring Batch Reference — Job Parameters](https://docs.spring.io/spring-batch/reference/job/running.html): cách truyền tham số khi chạy job và quy tắc nhận diện instance.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): cấu hình job, restartability và các thành phần liên quan.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): tiện ích kiểm thử job và step.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled`, cron, timezone và hạ tầng lập lịch.
- [Spring Framework Javadoc — `CronExpression`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronExpression.html): phân tích và tính thời điểm cron tiếp theo.
- [Spring Boot Reference — Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): tích hợp Spring Batch và cấu hình auto-run của Spring Boot.

