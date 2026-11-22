# Start job từ scheduler trong Spring Batch

## 1. Mục tiêu và bối cảnh

Một batch job hiếm khi chỉ chạy theo cách thủ công. Hệ thống thực tế thường cần **tự khởi chạy job theo lịch**: tổng hợp đơn hàng cuối ngày, đối soát thanh toán mỗi sáng, đồng bộ dữ liệu theo giờ hoặc xuất báo cáo cuối tháng. Trong Spring Batch, nhiệm vụ này được chia thành hai phần: scheduler phát yêu cầu chạy theo thời điểm định sẵn; Spring Batch thực thi, lưu metadata và quyết định khả năng chạy lại của job.

Bài học này giải thích cách **start job từ scheduler** trong nhóm kiến thức *Execution control* của *Spring Batch Core Processing*. Bạn sẽ học:

- Cách scheduler phối hợp với `JobLauncher`, `JobRepository`, `JobInstance` và `JobExecution`.
- Cách dùng `@Scheduled` để gọi một job Spring Batch trong Spring Boot.
- Cách tạo `JobParameters` xác định để phân biệt ngày xử lý, tránh chạy trùng và hỗ trợ restart.
- Cách xử lý lỗi, trạng thái job, lịch chồng nhau, nhiều replica và những lần chạy bị bỏ lỡ.
- Khi nào nên thay scheduler nội bộ bằng Quartz, Kubernetes CronJob hoặc một hệ thống điều phối bên ngoài.
- Cách kiểm thử logic kích hoạt mà không phải chờ cron chạy thật.

Ví dụ chính dựa trên Java 17+, Spring Boot 3.x và Spring Batch 5.x. Ứng dụng demo có job `dailyOrdersJob`, chạy lúc 01:10 sáng theo giờ Việt Nam và xử lý dữ liệu của ngày trước đó.

## 2. Scheduler và Spring Batch đảm nhiệm những phần nào?

Scheduler không thay thế các khái niệm Job và Step của Spring Batch. Nó chủ yếu xác định **khi nào** cần yêu cầu thực thi, còn các thành phần Batch chịu trách nhiệm xử lý **cái gì**, **với tham số nào** và **trạng thái ra sao**.

```text
   Lịch cron / Trigger / Scheduler bên ngoài
                        |
                        v
                   Scheduler
                        |
           xác định businessDate
           tạo JobParameters
                        |
                        v
                   JobLauncher
                        |
                        v
                   JobRepository
                /                \
               v                  v
          JobInstance        JobExecution
                                  |
                                  v
                         Job -> Step(s)
                                  |
                                  v
                      Reader / Processor / Writer
                                  |
                                  v
                           Kết quả xử lý
```

| Thành phần | Trách nhiệm |
| --- | --- |
| Scheduler | Phát yêu cầu chạy theo cron, chu kỳ hoặc sự kiện |
| `JobLauncher` | Nhận `Job` và `JobParameters` để yêu cầu chạy job |
| `JobRepository` | Quản lý metadata job instance, execution, step execution và trạng thái |
| `JobInstance` | Định danh logic của job theo tên và identifying parameters |
| `JobExecution` | Một lần cố gắng chạy của instance, có trạng thái và thời điểm riêng |
| `StepExecution` | Dữ liệu thực thi, số đếm, trạng thái và lỗi của từng step |
| Job/Step listener hoặc hệ thống monitoring | Nhận trạng thái cuối, ghi log, metric, cảnh báo |

Một trigger scheduler **không nhất thiết tạo JobInstance mới**. Nếu job đã hoàn tất với cùng bộ tham số định danh, Spring Batch sẽ từ chối chạy lại instance đó. Khi job đã thất bại, một lần kích hoạt sau có thể restart cùng instance và tạo JobExecution mới nếu điều kiện restart cho phép.

## 3. Các lựa chọn scheduler

| Phương pháp | Thích hợp | Điều cần cân nhắc |
| --- | --- | --- |
| Spring `@Scheduled` | Một ứng dụng luôn chạy, lịch đơn giản, ít workflow | Lịch phụ thuộc vòng đời ứng dụng; mỗi replica có thể cùng kích hoạt |
| Quartz Scheduler | Trigger phức tạp, lưu lịch bền vững, nhiều node | Cấu hình JobStore và cluster; viết adapter gọi `JobLauncher` |
| Kubernetes CronJob | Chạy batch theo container/process độc lập | Mỗi lịch tạo workload; cần thiết kế mã thoát, retry, lịch bị bỏ lỡ |
| Cron của hệ điều hành | Script hoặc ứng dụng chạy độc lập | Tự quản lý môi trường chạy, logging, lock và cảnh báo |
| Airflow, Control-M, Jenkins, hệ orchestration | Workflow nhiều phụ thuộc, backfill và quan sát tập trung | Hệ ngoài kích hoạt ứng dụng; Spring Batch vẫn giữ metadata thực thi |

Với batch đơn giản trong một service, `@Scheduled` là khởi đầu thuận tiện. Khi cần lịch bền vững sau restart, điều phối nhiều node hoặc phụ thuộc giữa nhiều pipeline, có thể cân nhắc scheduler chuyên dụng.

## 4. JobParameters là yếu tố quyết định danh tính instance

Spring Batch dùng tên job và **các JobParameters được đánh dấu identifying** để nhận diện một `JobInstance`:

```text
JobInstance = Job name + identifying JobParameters
```

Giả sử batch tổng hợp ngày 15/11/2026 được kích hoạt lúc 01:10 sáng ngày 16/11/2026:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedAt", "2026-11-15T18:10:00Z", false)
    .toJobParameters();
```

`businessDate` là tham số **identifying**: cùng ngày là cùng một JobInstance. `requestedAt` là tham số **non-identifying**: thời điểm gửi yêu cầu có thể khác nhau nhưng không đổi instance.

| Lần yêu cầu | businessDate | requestedAt | Kết quả điển hình |
| --- | --- | --- | --- |
| Lần đầu | 2026-11-15 | t1 | Tạo instance và execution mới |
| Gửi trùng sau khi hoàn tất | 2026-11-15 | t2 | Bị từ chối vì instance đã `COMPLETED` |
| Yêu cầu restart sau thất bại | 2026-11-15 | t3 | Có thể tạo JobExecution mới thuộc cùng instance |
| Yêu cầu khi lần trước đang chạy | 2026-11-15 | t4 | Bị từ chối vì execution đang chạy |
| Sang ngày khác | 2026-11-16 | t5 | Tạo JobInstance mới |

Không nên thêm `run.id`, timestamp hoặc UUID ngẫu nhiên dưới dạng identifying chỉ để bảo đảm mỗi lần cron đều chạy được. Cách đó vô tình tạo instance mới cho cùng một ngày nghiệp vụ, có thể dẫn đến nhập dữ liệu hoặc đối soát trùng.

Ngược lại, nếu yêu cầu nghiệp vụ thật sự coi **mỗi lần kích hoạt** là một đợt xử lý độc lập, sử dụng một định danh riêng cho lần chạy có thể hoàn toàn hợp lý. Quy tắc phải xuất phát từ ý nghĩa nghiệp vụ của JobInstance.

## 5. Cấu hình Spring Boot và bật scheduling

### 5.1. Dependency

Ví dụ Gradle dùng Spring Boot starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Spring Batch cần một `JobRepository` có thể lưu metadata. Trong production, nên dùng database bền vững và triển khai schema batch qua migration hoặc quy trình quản trị tương ứng.

### 5.2. Không tự khởi chạy job khi mở ứng dụng

Nếu scheduler sẽ quyết định lúc chạy, tắt cơ chế auto-run job của Spring Boot:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never

# Các thông số DataSource được cấu hình ở môi trường triển khai.
```

`spring.batch.job.enabled=false` ngăn Spring Boot tự chạy job qua runner của Boot lúc khởi động. Thiết lập `initialize-schema: never` giả định metadata schema đã tồn tại, phù hợp với deployment dùng migration. Trong môi trường test H2 mới, schema có thể được khởi tạo theo profile riêng.

### 5.3. Bật scheduler

```java
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

`@EnableScheduling` kích hoạt xử lý các phương thức `@Scheduled` thuộc bean trong Spring context. Phương thức mang annotation nhưng nằm trong object do code tự tạo ngoài context sẽ không tự chạy theo lịch.

## 6. Định nghĩa job để scheduler gọi

Ví dụ sau tạo một job với tasklet minh họa. Trong ứng dụng thực tế, thay phần thân tasklet bằng thao tác đọc, xử lý và lưu báo cáo theo `businessDate`.

```java
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
public class DailyOrdersJobConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(DailyOrdersJobConfiguration.class);

    @Bean("dailyOrdersStep")
    Step dailyOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager) {

        return new StepBuilder("dailyOrdersStep", repository)
            .tasklet((contribution, chunkContext) -> {
                Object businessDate = chunkContext
                    .getStepContext()
                    .getJobParameters()
                    .get("businessDate");

                log.info("Processing orders for {}", businessDate);

                // TODO: Thay bằng xử lý đơn hàng thật theo businessDate.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean("dailyOrdersJob")
    Job dailyOrdersJob(
            JobRepository repository,
            @Qualifier("dailyOrdersStep") Step step) {

        return new JobBuilder("dailyOrdersJob", repository)
            .start(step)
            .build();
    }
}
```

Tên `dailyOrdersJob` giữ nguyên qua các ngày. Các ngày xử lý khác nhau được phân biệt bằng `businessDate`, không phải bằng cách nối ngày vào tên job.

## 7. Khởi chạy job theo cron với @Scheduled và JobLauncher

### 7.1. Thiết lập nguồn thời gian

Dùng `Clock` được quản lý bởi Spring để dễ kiểm thử thời gian và thay thế bằng `Clock.fixed(...)`:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Cron trong ví dụ đặt ở 01:10 sáng theo `Asia/Ho_Chi_Minh`. Ngày nghiệp vụ cũng phải tính theo cùng múi giờ này để tránh lệch ngày khi máy chủ chạy ở UTC hay múi giờ khác.

### 7.2. Lớp scheduler

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
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
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DailyOrdersScheduler {

    private static final Logger log =
        LoggerFactory.getLogger(DailyOrdersScheduler.class);

    private static final ZoneId BUSINESS_ZONE =
        ZoneId.of("Asia/Ho_Chi_Minh");

    private final JobLauncher jobLauncher;
    private final Job dailyOrdersJob;
    private final Clock clock;

    public DailyOrdersScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailyOrdersJob") Job dailyOrdersJob,
            Clock clock) {

        this.jobLauncher = jobLauncher;
        this.dailyOrdersJob = dailyOrdersJob;
        this.clock = clock;
    }

    // Spring cron: giây - phút - giờ - ngày - tháng - thứ.
    // 01:10 sáng mỗi ngày, theo múi giờ Việt Nam.
    @Scheduled(cron = "0 10 1 * * *", zone = "Asia/Ho_Chi_Minh")
    public void runOnSchedule() {
        LocalDate businessDate =
            LocalDate.now(clock.withZone(BUSINESS_ZONE)).minusDays(1);

        runForDate(businessDate);
    }

    // Dùng chung cho lịch tự động và yêu cầu chạy bù có kiểm soát.
    public void runForDate(LocalDate businessDate) {
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("requestedAt", Instant.now(clock).toString(), false)
            .toJobParameters();

        try {
            JobExecution execution =
                jobLauncher.run(dailyOrdersJob, parameters);

            BatchStatus status = execution.getStatus();

            log.info(
                "dailyOrdersJob date={} executionId={} status={}",
                businessDate,
                execution.getId(),
                status
            );

            if (status == BatchStatus.FAILED ||
                status == BatchStatus.STOPPED) {

                log.error(
                    "Batch date={} không thành công, exitStatus={}",
                    businessDate,
                    execution.getExitStatus()
                );
                // TODO: Ghi metric hoặc phát cảnh báo vận hành.
            }

        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info(
                "Ngày {} đã được xử lý thành công; bỏ qua trigger trùng",
                businessDate
            );
        } catch (JobExecutionAlreadyRunningException ex) {
            log.info(
                "Ngày {} đang được xử lý; bỏ qua trigger trùng",
                businessDate
            );
        } catch (JobRestartException |
                 JobParametersInvalidException ex) {
            log.error(
                "Không thể start/restart batch ngày {}",
                businessDate,
                ex
            );
        } catch (Exception ex) {
            log.error(
                "Lỗi khi yêu cầu chạy batch ngày {}",
                businessDate,
                ex
            );
        }
    }
}
```

Trong cấu hình này:

1. Spring gọi `runOnSchedule()` theo lịch cron.
2. Phương thức chọn `businessDate` là ngày trước đó tính theo giờ Việt Nam.
3. `runForDate()` tạo `JobParameters`, trong đó ngày nghiệp vụ là identifying.
4. `JobLauncher.run(...)` yêu cầu tạo hoặc restart execution.
5. `JobRepository` kiểm tra instance và quản lý metadata.
6. Scheduler ghi nhận execution ID, trạng thái và ngoại lệ liên quan.

**Phân biệt lỗi khởi chạy với lỗi xử lý:** `JobLauncher.run(...)` có thể ném ngoại lệ khi instance đã hoàn tất, đang chạy, restart không hợp lệ hoặc tham số không đúng. Với launcher đồng bộ, lỗi trong step thường làm `JobExecution` có trạng thái `FAILED`, không có nghĩa mọi lỗi xử lý đều được ném ra từ `run(...)`. Vì vậy cần kiểm tra `BatchStatus` và `ExitStatus`, đồng thời theo dõi trạng thái cuối.

Nếu cấu hình launcher dùng task executor bất đồng bộ, `run(...)` có thể trả về khi job vẫn `STARTING` hoặc `STARTED`. Khi đó status vừa trả về **không phải kết quả cuối**. Cần dùng `JobExplorer`, listener, log hoặc monitoring để xác nhận job thực sự hoàn tất.

## 8. Hiểu cú pháp cron và những lựa chọn về thời điểm

Spring `@Scheduled` hỗ trợ cron với **sáu trường**:

```text
second minute hour day-of-month month day-of-week
  0      10    1        *         *         *
```

Một số ví dụ:

| Cron của Spring | Ý nghĩa |
| --- | --- |
| `0 10 1 * * *` | Mỗi ngày lúc 01:10:00 |
| `0 0 * * * *` | Đầu mỗi giờ |
| `0 0 2 * * MON-FRI` | 02:00 từ thứ hai đến thứ sáu |
| `0 30 23 L * *` | 23:30 ngày cuối cùng của mỗi tháng |

Với `@Scheduled`, có thể cấu hình lịch bằng thuộc tính bên ngoài ứng dụng thay vì hardcode:

```yaml
app:
  batch:
    cron: "0 10 1 * * *"
    zone: "Asia/Ho_Chi_Minh"
```

Sau đó đặt giá trị annotation theo placeholder cấu hình, ví dụ `@Scheduled(cron = "${app.batch.cron}", zone = "${app.batch.zone}")`. Khi làm vậy, logic tính `businessDate` cũng phải sử dụng cùng zone được cấu hình; ví dụ ở phần trước cố định cả hai theo giờ Việt Nam để minh họa nhất quán.

### Cron so với fixedRate và fixedDelay

```java
// Chạy theo mốc thời gian cố định.
@Scheduled(cron = "0 10 1 * * *", zone = "Asia/Ho_Chi_Minh")
void daily() { /* launch */ }

// Khoảng giữa các lần bắt đầu lời gọi theo lịch.
@Scheduled(fixedRate = 60_000)
void pollEveryMinute() { /* launch */ }

// Chờ 60 giây sau khi lời gọi phương thức trước kết thúc.
@Scheduled(fixedDelay = 60_000)
void pollAfterCompletion() { /* launch */ }
```

`fixedDelay` tính thời gian sau khi **phương thức @Scheduled** hoàn tất. Nếu phương thức chỉ khởi động job bất đồng bộ rồi trả về, fixedDelay không có nghĩa đợi toàn bộ batch hoàn tất. Tương tự, cron kích hoạt ở mốc thời gian không bảo đảm job trước đã kết thúc.

Với các vùng có daylight saving time (DST), mốc giờ địa phương có thể không tồn tại hoặc lặp ở ngày chuyển giờ; hãy chọn zone và quy tắc nghiệp vụ rõ ràng. `Asia/Ho_Chi_Minh` hiện không áp dụng DST nhưng hệ thống đa quốc gia vẫn cần cân nhắc.

## 9. Chống chạy trùng khi nhiều replica cùng bật scheduler

Một điểm dễ bị bỏ sót là **@Scheduled hoạt động trong từng application instance**. Nếu triển khai cùng service lên ba node, cả ba node đều có thể phát trigger vào 01:10.

```text
             01:10
               |
      +--------+--------+
      |        |        |
    Node A   Node B   Node C
      |        |        |
      +--------+--------+
               |
          JobRepository
               |
      Cùng businessDate
```

Một `JobRepository` dùng database chia sẻ và cấu hình đúng có thể giúp Spring Batch ngăn nhiều execution hoạt động đồng thời cho cùng JobInstance. Tuy nhiên, cơ chế danh tính instance **không thay thế hoàn toàn** yêu cầu chỉ có một node chịu trách nhiệm phát trigger trong cluster.

Có thể áp dụng:

- Dành một instance/service riêng chịu trách nhiệm lập lịch.
- Dùng distributed lock để chỉ một node gửi yêu cầu tại một kỳ.
- Dùng Quartz với JDBC JobStore và cấu hình cluster.
- Đặt lịch ở hệ thống điều phối bên ngoài thay vì trên từng replica.

Các khóa chỉ tồn tại trong một JVM như `synchronized` hoặc `ReentrantLock` không bảo vệ khỏi trigger phát ra từ JVM khác.

### Chạy chồng giữa các kỳ khác nhau

Job chạy theo giờ nhưng mỗi lần kéo dài 90 phút là trường hợp cần quyết định riêng. Nếu job của kỳ 10:00 chưa xong mà scheduler kích hoạt kỳ 11:00, hai kỳ có **khác identifying parameters** nên vẫn có thể là hai JobInstance riêng và có thể chạy đồng thời.

Hãy xác định rõ:

- Có cho phép hai kỳ dữ liệu khác nhau chạy chồng không?
- Reader/writer có dùng chung file, bảng tạm hoặc khóa xử lý không?
- Có giới hạn connection pool, thread pool, CPU, bộ nhớ, thời gian hoàn tất không?
- Nếu không cho phép chồng lịch, scheduler sẽ chờ, bỏ qua hay xếp hàng trigger?

Không nên phụ thuộc hoàn toàn vào quy tắc “một JobInstance chỉ có một execution đang chạy” để giải quyết các xung đột tài nguyên giữa **nhiều JobInstance**.

## 10. Restart, retry và chạy bù theo lịch

Có ba khái niệm cần phân biệt:

| Tình huống | Cơ chế | JobParameters |
| --- | --- | --- |
| Lỗi tạm thời trong reader/processor/writer | Retry hoặc fault tolerance ở step | Vẫn là execution hiện tại |
| Job thất bại và được khởi chạy lại | Restart của Spring Batch | Giữ nguyên identifying parameters |
| Muốn xử lý kỳ đã bỏ lỡ | Backfill theo danh sách kỳ nghiệp vụ | Mỗi kỳ có business key xác định |

Một ví dụ dễ mắc lỗi:

```java
// Không phù hợp với mục tiêu restart cùng ngày nếu run.id là identifying.
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
```

Tham số do `addLong` thêm theo mặc định mang tính identifying. Khi gọi lại, `run.id` đổi và Spring Batch có thể tạo instance mới thay vì restart instance thất bại. Nếu job đã ghi dữ liệu từng phần trước khi lỗi, việc chạy một instance mới có thể ghi trùng.

### Khi application dừng và bỏ lỡ lịch

`@Scheduled` không bảo đảm tự xử lý đủ tất cả kỳ bị bỏ lỡ lúc ứng dụng không chạy. Ví dụ service dừng ba ngày, rồi khởi động lại: scheduler theo cron có thể chỉ phát trigger tiếp theo trong tương lai. Việc gọi `LocalDate.now().minusDays(1)` cũng chỉ chọn một ngày, không bao quát cả khoảng lịch sử cần chạy bù.

Một cơ chế backfill nên:

1. Xác định danh sách kỳ nghiệp vụ bắt buộc đã đến hạn.
2. Dùng `JobExplorer`/metadata và dữ liệu nghiệp vụ để xác định kỳ chưa thành công.
3. Với kỳ chưa tồn tại, khởi chạy một instance mới với business key của kỳ đó.
4. Với kỳ `FAILED` và restartable, dùng lại identifying parameters để restart.
5. Với kỳ `COMPLETED`, bỏ qua hoặc xử lý theo quy trình reprocess riêng.
6. Lưu log lý do chạy bù và kết quả cuối cùng.

Ví dụ gọi hàm trong scheduler với một ngày cụ thể:

```java
dailyOrdersScheduler.runForDate(
    LocalDate.parse("2026-11-11")
);
```

Lệnh này tái sử dụng cùng quy tắc JobParameters như cron, tránh hai cơ chế chạy độc lập với hai kiểu định danh khác nhau.

### Reprocess không giống restart

Restart dùng chính JobInstance đã thất bại hoặc dừng. Nếu một JobInstance đã `COMPLETED`, việc chạy lại với cùng identifying parameters thông thường bị từ chối. Tái xử lý một kỳ đã hoàn tất là quyết định nghiệp vụ riêng, có thể cần version dữ liệu, chiến lược thay thế kết quả và audit. Không nên ngầm tăng `run.id` để vượt qua bảo vệ này.

## 11. Khi dùng Quartz hoặc scheduler bên ngoài

### Quartz

Quartz phù hợp khi yêu cầu trigger bền vững, lịch phức tạp, misfire policy hoặc cluster. Quartz Job không phải Spring Batch Job; một lớp adapter thường nhận `JobExecutionContext` của Quartz rồi gọi `JobLauncher` với `JobParameters` cần thiết.

Cấu trúc:

```text
Quartz Trigger
     |
     v
Quartz Job.execute(context)
     |
     v
Tính businessDate / job parameters
     |
     v
JobLauncher.run(springBatchJob, parameters)
     |
     v
JobRepository + Step(s)
```

Nếu dùng Quartz cluster, cần cấu hình đúng JobStore chung và misfire policy. Bảo đảm sự kiện Quartz được chuyển sang business key ổn định, tránh chỉ lấy timestamp làm identifying mỗi khi Quartz retry.

### Kubernetes CronJob và process chạy một lần

Một cách khác là scheduler bên ngoài khởi động ứng dụng theo chế độ chạy một lần:

```text
Kubernetes CronJob / Airflow / Cron
                  |
                  v
        Chạy process Java
                  |
                  v
     ApplicationRunner hoặc CLI entry point
                  |
                  v
       JobLauncher + JobParameters
                  |
                  v
       Theo dõi trạng thái cuối
                  |
                  v
        Exit code / Logs / Metrics
```

Ví dụ một lệnh chạy ứng dụng kiểu one-shot:

```bash
java -jar daily-orders.jar --app.batch.mode=once --app.batch.business-date=2026-11-15
```

Hai option `app.batch.mode` và `app.batch.business-date` là **thuộc tính tùy biến của ứng dụng**, không phải option Spring Batch tự hiểu. Cần triển khai một `ApplicationRunner` hoặc entry point đọc ngày, tạo `JobParameters`, gọi `JobLauncher`, đợi trạng thái cuối và trả exit code phù hợp.

Với Kubernetes CronJob, `concurrencyPolicy: Forbid` giúp hạn chế chạy chồng các Kubernetes Job thuộc cùng một CronJob. Nó không bảo đảm mọi hệ thống bên ngoài đều không gửi trùng và cũng không thay thế tính idempotent của Spring Batch. Một lần lịch có thể bị bỏ lỡ hoặc được kích hoạt lặp trong các tình huống vận hành; business key vẫn cần ổn định.

### Trigger bằng API

Một service batch chạy liên tục có thể expose API nội bộ cho scheduler bên ngoài hoặc trang vận hành. API nên nhận `businessDate` hoặc mã kỳ xử lý, kiểm tra quyền, xác định identifying parameters, gọi launcher và trả JobExecution ID để tra cứu trạng thái. Không nên thiết kế API chỉ nhận “chạy ngay” mà không biết rõ đang xử lý kỳ dữ liệu nào.

## 12. Theo dõi trạng thái cuối và xử lý thất bại

Thành công của việc gọi một hàm `@Scheduled` không đồng nghĩa batch đã thành công. Ít nhất cần quan sát:

| Dữ liệu | Mục đích |
| --- | --- |
| Ngày nghiệp vụ, tên job | Biết chính xác kỳ nào được xử lý |
| JobInstance ID | Nhận diện một kỳ logic |
| JobExecution ID | Phân biệt các lần chạy/restart |
| `BatchStatus` và `ExitStatus` | Xác định trạng thái và kết quả kết thúc |
| Thời gian bắt đầu/kết thúc | Tính thời lượng và phát hiện quá SLA |
| `readCount`, `writeCount`, `skipCount` | Quan sát hoạt động của từng step |
| Kỳ dự kiến nhưng không có execution thành công | Phát hiện scheduler bỏ lỡ trigger |

Có thể tích hợp `JobExecutionListener` để ghi log/metric khi job thực sự kết thúc:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class DailyJobListener implements JobExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(DailyJobListener.class);

    @Override
    public void afterJob(JobExecution execution) {
        log.info(
            "Batch finished: id={}, status={}, exitStatus={}",
            execution.getId(),
            execution.getStatus(),
            execution.getExitStatus()
        );
    }
}
```

Đăng ký listener vào job builder với `.listener(...)`. Trong launcher bất đồng bộ, listener hoặc tiến trình đọc metadata cuối cùng phù hợp hơn việc chỉ kiểm tra trạng thái lúc `JobLauncher.run` vừa trả về.

Một hệ thống vận hành nên cảnh báo cả trường hợp **không có job thành công đúng hạn**. Nếu scheduler không kích hoạt vì service tắt hoặc cấu hình cron sai, có thể không có lỗi `FAILED` nào để phát hiện.

## 13. Kiểm thử logic scheduler

Không cần đợi đến 01:10 để kiểm thử việc chọn ngày nghiệp vụ và tham số định danh. Với `Clock.fixed(...)` và launcher giả lập, có thể gọi trực tiếp `runOnSchedule()`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class DailyOrdersSchedulerTest {

    @Test
    void schedulesPreviousBusinessDate() throws Exception {
        JobLauncher launcher = mock(JobLauncher.class);
        Job job = mock(Job.class);
        JobExecution execution = mock(JobExecution.class);

        when(launcher.run(eq(job), any(JobParameters.class)))
            .thenReturn(execution);
        when(execution.getStatus())
            .thenReturn(BatchStatus.COMPLETED);

        // 18:10 UTC 15/11 tương ứng 01:10 ngày 16/11 tại Việt Nam.
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-15T18:10:00Z"),
            ZoneOffset.UTC
        );

        DailyOrdersScheduler scheduler =
            new DailyOrdersScheduler(launcher, job, clock);

        scheduler.runOnSchedule();

        ArgumentCaptor<JobParameters> captor =
            ArgumentCaptor.forClass(JobParameters.class);
        verify(launcher).run(eq(job), captor.capture());

        JobParameters parameters = captor.getValue();

        assertEquals(
            "2026-11-15",
            parameters.getString("businessDate")
        );
        assertTrue(
            parameters.getParameter("businessDate").isIdentifying()
        );
        assertFalse(
            parameters.getParameter("requestedAt").isIdentifying()
        );
    }
}
```

Test này xác minh cách scheduler tạo yêu cầu chạy. Nó chưa xác minh việc cron thực sự kích hoạt hay khả năng restart từ Spring Batch. Để kiểm thử toàn luồng, cần integration test dùng `JobRepository` thật, database metadata dành riêng cho test và job có trạng thái được kiểm soát.

Các kịch bản tích hợp nên có:

| Kịch bản | Assertion chủ đạo |
| --- | --- |
| Kỳ đầu tiên chưa có instance | Tạo một JobInstance, một execution đúng kỳ |
| Lặp lại trigger sau `COMPLETED` | Không tạo execution mới của instance đã hoàn tất |
| Trigger khi execution đang chạy | Yêu cầu trùng bị từ chối |
| Restart sau `FAILED` | Instance ID giữ nguyên, execution ID mới |
| Đổi `businessDate` | JobInstance ID khác |
| Kỳ trước chưa kết thúc khi kỳ mới tới | Tuân theo chính sách chạy đồng thời |
| Gần ranh giới 00:00 ở các zone | Chọn đúng businessDate |
| Mất lịch vài ngày | Cơ chế backfill xử lý đúng các kỳ thiếu |

Với test chạy đồng thời, dùng `CountDownLatch` hoặc tín hiệu kiểm soát tương đương để chờ execution đầu **thực sự đang chạy** rồi mới kích hoạt lần hai. Tránh phụ thuộc vào `Thread.sleep` vì test dễ không ổn định. Dọn metadata giữa các test hoặc cô lập database để lịch sử cũ không làm sai kết quả.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| Job chạy lúc app khởi động và lại chạy lúc cron | Boot auto-run còn bật | Đặt `spring.batch.job.enabled=false` |
| Cron không gọi phương thức | Thiếu `@EnableScheduling`, bean không được quản lý, app dừng hoặc cron sai | Kiểm tra Spring context, lịch, log |
| Batch chạy lệch ngày | Cron và cách tính businessDate dùng zone khác nhau | Dùng múi giờ nhất quán và tiêm `Clock` |
| Cùng ngày có nhiều JobInstance | Timestamp/`run.id` là identifying | Định danh theo khóa nghiệp vụ ổn định |
| Nhiều node cùng kích hoạt | Mỗi replica có `@Scheduled` | Chọn scheduler leader/lock/scheduler ngoài |
| Scheduler báo chạy thành công nhưng job `FAILED` | Không theo dõi trạng thái cuối | Kiểm tra `JobExecution`, listener, metadata |
| Chạy chồng gây xung đột tài nguyên | Nhiều kỳ khác nhau chạy đồng thời | Chính sách concurrency và khóa tài nguyên |
| Không chạy bù các ngày bỏ lỡ | Scheduler in-process không lưu đủ missed triggers | Xây dựng backfill hoặc dùng scheduler bền vững |
| Retry ghi dữ liệu trùng | Tạo instance mới hoặc writer thiếu idempotency | Restart cùng identity, dùng transaction/idempotency |
| Test cron lúc đúng lúc sai | Phụ thuộc đồng hồ thực và lệnh sleep | Dùng `Clock.fixed`, kiểm thử logic trực tiếp |

## 15. Bài tập thực hành

Hãy mở rộng `dailyOrdersJob` thành job đọc đơn hàng theo `businessDate`, tính tổng doanh thu và lưu vào bảng `daily_order_summary`. Giữ lịch 01:10 theo múi giờ Việt Nam.

Thực hiện các kịch bản: chạy kỳ mới; phát lại trigger cho kỳ đã hoàn tất; làm một step thất bại rồi restart cùng kỳ; chạy kỳ tiếp theo; mô phỏng app dừng hai ngày và chạy bù đúng các ngày còn thiếu. Với mỗi kịch bản, kiểm tra cả metadata (JobInstance, JobExecution, BatchStatus) và dữ liệu trong bảng đích.

Sau đó giả lập hai replica cùng phát trigger vào một kỳ và lựa chọn một chiến lược phối hợp scheduler. Mục tiêu là dữ liệu đầu ra không bị nhân đôi và lịch sử execution phản ánh đúng điều đã xảy ra.

## 16. Kết luận

Khởi chạy Spring Batch job từ scheduler không chỉ là gắn `@Scheduled` vào một phương thức. Thiết kế cần xác định **thời điểm chạy, kỳ dữ liệu, danh tính JobInstance và chính sách chạy lại**. Scheduler gọi `JobLauncher` với identifying parameters ổn định; `JobRepository` lưu trạng thái để hỗ trợ chống chạy trùng và restart; hệ thống vận hành theo dõi kết quả cuối, xử lý missed schedules và giới hạn concurrency. Khi những nguyên tắc đó được giữ nhất quán, có thể chuyển giữa `@Scheduled`, Quartz hoặc scheduler bên ngoài mà không làm thay đổi tính đúng đắn của job.
