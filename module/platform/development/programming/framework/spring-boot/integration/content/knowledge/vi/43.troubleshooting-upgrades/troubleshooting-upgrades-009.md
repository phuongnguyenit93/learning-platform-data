# Job chạy trùng giữa các bản sao hoặc không khởi động lại được

## 1. Nhận diện sự cố trong Spring Boot Integration

Trong một ứng dụng **Spring Boot Integration**, các luồng tích hợp thường chạy theo lịch hoặc theo lô để nhập dữ liệu từ HTTP API, đồng bộ cơ sở dữ liệu, tái tạo cache, chuyển sự kiện qua RabbitMQ/Kafka và đối soát kết quả. Một job có thể được kích hoạt bởi `@Scheduled`, Quartz, Spring Batch `JobLauncher`, thông điệp broker hoặc một API quản trị. Khi triển khai nhiều replica/pod, hai sự cố hay gặp là:

1. **Job chạy trùng**: cùng một kỳ đối soát được xử lý ở hai pod; dữ liệu bị ghi hai lần, đối tác bị gọi lặp hoặc email được gửi trùng.
2. **Job không restart được**: sau khi một execution thất bại hoặc process chết, thao tác restart báo “đã hoàn tất”, “đang chạy”, “không tìm thấy instance”, hoặc chạy lại **từ đầu** thay vì tiếp tục từ checkpoint.

Hai triệu chứng có thể có cùng nguyên nhân sâu xa: **nhận diện sai đơn vị công việc và thiếu cơ chế phối hợp trạng thái bền vững giữa các bản sao**. Ví dụ, nếu mỗi pod tự sinh tham số `run.id` mới, Spring Batch sẽ thấy các `JobInstance` khác nhau và không ngăn các pod cùng xử lý một ngày nghiệp vụ.

~~~mermaid
flowchart LR
    S["Cron 01:00"] --> A["Replica A"]
    S --> B["Replica B"]
    S --> C["Replica C"]
    A --> J1["JobLauncher"]
    B --> J2["JobLauncher"]
    C --> J3["JobLauncher"]
    J1 --> R[("JobRepository chung")]
    J2 --> R
    J3 --> R
    R --> D[("Dữ liệu nghiệp vụ")]
~~~

**Cảnh báo:** Một `JobRepository` dùng chung có thể phối hợp việc tạo execution cho **cùng JobInstance**, nhưng không có nghĩa ứng dụng đã được bảo vệ khỏi mọi trường hợp chạy trùng. Nếu các pod có **identifying parameters khác nhau**, tên job khác nhau hoặc cùng job tác động tới các khóa nghiệp vụ khác nhau được tính sai, repository sẽ xem chúng là các instance riêng.

Bài học áp dụng cho **Spring Boot 3.x và Spring Batch 5.x**, đồng thời phân biệt rõ cơ chế của `@Scheduled`, Quartz clustered scheduler và consumer message broker. Khi nâng cấp sang phiên bản khác, phải đối chiếu API, schema metadata và thay đổi cấu hình tương ứng.

## 2. Trước tiên phải xác định “job” thực chất là gì

Từ “job” bị dùng cho nhiều cơ chế khác nhau; hướng sửa phụ thuộc nơi kích hoạt và nơi lưu trạng thái:

| Kiểu công việc | Ai kích hoạt? | Trạng thái/khóa thường nằm ở đâu? | Nguy cơ trùng phổ biến |
| --- | --- | --- | --- |
| **`@Scheduled` thuần Spring** | Scheduler nội bộ từng JVM. | Không mặc định có trạng thái liên replica. | Mỗi pod cùng chạy một cron; redeploy gây overlap. |
| **Spring Batch job** | `JobLauncher`, scheduler, API hoặc operator. | `JobRepository` và các bảng metadata Batch. | Identifying JobParameters khác nhau hoặc repository không dùng chung. |
| **Quartz job** | Trigger Quartz; có RAM hoặc JDBC JobStore. | Quartz JobStore, trigger và job key. | RAMJobStore trên mỗi pod; clustering chưa bật; nhiều JobKey/trigger trùng chức năng. |
| **Consumer broker** | RabbitMQ/Kafka giao message. | Queue/offset, ack, consumer group và state ứng dụng. | Redelivery, retry, consumer group khác nhau hoặc side effect không idempotent. |
| **CronJob của Kubernetes** | Control plane của cluster khởi tạo pod. | Job/CronJob của Kubernetes. | `concurrencyPolicy` và retry/tạo pod lại; task không idempotent. |

Ví dụ, đặt `@Scheduled` trên method gọi `JobLauncher` **không biến @Scheduled thành scheduler phân tán**. Mỗi pod vẫn đến giờ là gọi launcher. Cũng không thể sửa lỗi Quartz RAMJobStore bằng cách chỉ thêm một `JobRepository` của Spring Batch: chúng là **hai hệ thống metadata độc lập**.

Hãy xác minh bằng log và cấu hình thực tế: có bao nhiêu pod, ai phát trigger, tên job/trigger, thời gian chạy, tham số nhận diện, database metadata, đường gọi tới dịch vụ đích và mã nghiệp vụ của lô.

## 3. Cơ chế nhận diện và restart của Spring Batch

Spring Batch phân biệt:

| Thành phần | Định nghĩa | Tác dụng đối với gỡ lỗi |
| --- | --- | --- |
| `Job` | Định nghĩa các `Step` và luồng điều khiển. | Tên job là một phần danh tính. |
| `JobParameters` | Tham số của lần chạy, mỗi tham số có cờ `identifying`. | **Chỉ các identifying parameter** tham gia nhận diện JobInstance. |
| `JobInstance` | Một lần xử lý logic xác định bởi tên job và identifying parameters. | Là đơn vị để quyết định đang chạy, đã hoàn thành hay có thể restart. |
| `JobExecution` | Một attempt của JobInstance. | JobInstance thất bại có thể có execution mới sau restart. |
| `StepExecution` | Attempt của một step, có số lần commit, rollback, read/write/skip. | Giúp biết step nào đã hoàn tất và checkpoint đến đâu. |
| `ExecutionContext` | Metadata state được persist cho step/job. | Cho phép reader/writer stateful tiếp tục khi restart. |
| `JobRepository` | Lưu metadata và thực hiện các thao tác phối hợp trạng thái. | **Phải bền vững và dùng chung** nếu nhiều pod cần phối hợp Spring Batch. |

Quy tắc cốt lõi:

~~~text
JobInstance = jobName + identifying JobParameters

dailySettlementJob / businessDate=2026-11-20 / source=bank-A
    JobExecution 1001 -> FAILED
    JobExecution 1002 -> COMPLETED (restart cùng instance)

dailySettlementJob / businessDate=2026-11-21 / source=bank-A
    JobExecution 1003 -> STARTED (instance khác)
~~~

**`run.id`, UUID hoặc timestamp mới** có thể hữu ích để tạo một **lô thực sự mới**, nhưng nếu được đánh dấu identifying và thay đổi trong mỗi lần retry thì nó tạo **JobInstance mới**, làm mất khả năng restart theo checkpoint cũ. Đừng sửa lỗi “already complete” bằng cách tự động tăng `run.id` khi mục đích thực sự là tiếp tục cùng kỳ dữ liệu.

### 3.1. Thông báo lỗi và ý nghĩa

| Thông báo hoặc trạng thái | Khả năng cao | Hướng kiểm tra |
| --- | --- | --- |
| `JobExecutionAlreadyRunningException` | Một execution cùng instance đang được coi là chạy. | Xem JobRepository và pod sở hữu; phân biệt thực sự chạy với `STARTED` kẹt sau crash. |
| `JobInstanceAlreadyCompleteException` | Instance đã hoàn tất; có thể caller đang cố chạy lại cùng identity. | Tra JobInstance và nhu cầu “restart” hay “reprocess” thật sự. |
| `JobRestartException` | Job không restartable, metadata/state không hợp lệ, hoặc một điều kiện restart bị chặn. | Kiểm tra cấu hình restart và stack trace đầy đủ. |
| `JobParametersInvalidException` | Parameters không hợp lệ theo validator/hợp đồng job. | So tham số cần thiết, kiểu, identifying flag và phạm vi ngày nghiệp vụ. |
| `JobInstance` không tìm thấy khi restart | Metadata ở repository khác, đã bị dọn, job name/identity đổi hoặc dùng sai execution ID. | Kiểm tra datasource/schema/prefix và migration metadata. |
| Restart “thành công” nhưng bắt đầu lại từ đầu | JobInstance mới; reader không lưu state; input thay đổi; checkpoint chưa commit. | So JOB_KEY, identifying params và `ExecutionContext` của step. |
| Step không chạy khi restart | Step đã `COMPLETED` và mặc định được bỏ qua. | Kiểm tra flow và `allowStartIfComplete` chỉ khi thật sự cần chạy lại. |

Không suy ra “job chắc chắn đang chạy” chỉ vì metadata có `STARTED`: sau sự cố, trạng thái có thể chưa được chuyển thành `FAILED` hoặc `STOPPED`. Ngược lại, **không được tự ý giải phóng** một execution còn sống chỉ vì thời gian chạy dài.

## 4. Nguyên nhân làm job chạy trùng giữa các replica

### 4.1. `@Scheduled` chạy độc lập tại mỗi JVM

~~~java
@Scheduled(cron = "0 0 1 * * *", zone = "Asia/Ho_Chi_Minh")
public void importDaily() {
    runImportForYesterday();
}
~~~

Nếu có ba pod, thông thường **cả ba** pod cùng gọi method trên lúc 01:00. `@EnableScheduling` chỉ bật lịch trong application context; nó không có cơ chế leader election hay distributed lock mặc định. Nếu mỗi pod gọi một API ngoài, giao dịch có thể bị thực hiện ba lần.

Các lựa chọn khắc phục tùy yêu cầu: chỉ một scheduler chuyên trách; distributed lock/lease; Quartz JDBC clustering; hoặc cho nhiều pod gọi `JobLauncher` nhưng dùng **JobRepository chung và identifying parameters ổn định**. Dù chọn cách nào, vẫn cần bảo vệ **khóa nghiệp vụ/idempotency** ở đầu ra.

### 4.2. Mỗi pod dùng một JobRepository khác nhau

Đây là lỗi thường gặp khi dùng datasource/schema mặc định không giống nhau, in-memory metadata, hoặc cấu hình multi-datasource thiếu qualifier. Pod A ghi metadata vào database A, pod B vào database B; cả hai đều thấy chưa có job.

Kiểm tra **URL datasource, schema, table prefix, user quyền, cấu hình profile và loại JobRepository** thực tế ở mỗi pod. Trong môi trường cluster, metadata phải nằm ở storage chung, bền vững, có transaction isolation và unique constraints đúng phiên bản. Không xóa/bỏ constraint các bảng batch để “giảm conflict” khi chạy đồng thời.

### 4.3. Identifying parameters không ổn định

~~~text
Pod A: dailySettlementJob, businessDate=2026-11-20, run.id=1001 (identifying)
Pod B: dailySettlementJob, businessDate=2026-11-20, run.id=1002 (identifying)
=> Hai JobInstance khác nhau dù cùng xử lý một ngày nghiệp vụ.
~~~

Tương tự, tên file chứa đường dẫn local tạm thời, timestamp phát sinh ở mỗi pod hoặc ID ngẫu nhiên có thể làm identity thay đổi. Hãy dùng **businessDate**, `sourceId`, ID lô/phiên bản nguồn bất biến làm identifying parameters, và chuẩn hóa timezone, định dạng ngày, case sensitivity và cách diễn giải đường dẫn.

### 4.4. Nhiều trigger hoặc lịch chồng nhau

Ngay cả khi chỉ có một scheduler, một job có thể được khởi chạy bởi cả `@Scheduled`, API quản trị, trigger Quartz và sự kiện từ broker. Một job chạy lâu hơn chu kỳ có thể bị lần kích hoạt tiếp theo đè lên nếu mỗi lần dùng identity mới.

Với Quartz, nếu cùng logic được đăng ký dưới nhiều `JobKey` hoặc nhiều trigger, `@DisallowConcurrentExecution` trên một job class không cấm chạy song song **mọi JobDetail khác nhau**; nó giới hạn concurrency theo **JobDetail/JobKey** tương ứng.

### 4.5. Broker giao lại message hoặc scheduler retry

RabbitMQ/Kafka có thể redeliver khi crash trước ack, timeout, rebalance hoặc retry. Một consumer xử lý lại message không nhất thiết là bug của broker. Nếu cùng message tạo JobInstance khác hoặc ghi dữ liệu mà không chống trùng, tác dụng nghiệp vụ sẽ lặp. Cần ổn định `eventId`/`operationId` và quan hệ với `businessKey`, dùng inbox/unique constraints khi thích hợp.

## 5. Ba tầng bảo vệ nên phối hợp

Đừng tìm một annotation duy nhất để “chạy đúng một lần toàn hệ thống”. Thiết kế tin cậy thường gồm ba lớp:

1. **Đặt lịch có chủ đích:** một trigger phân tán hoặc leader/lock hợp lệ, không mặc định mỗi pod chạy độc lập.
2. **Nhận diện instance và trạng thái bền vững:** `JobRepository` chung, identifying parameters thống nhất, kiểm soát job đang chạy hoặc đã hoàn thành.
3. **Đầu ra idempotent:** unique business key, upsert có kiểm tra xung đột, operation ID với HTTP API, event/inbox/outbox khi trao đổi qua broker.

| Mức bảo vệ | Ngăn được gì? | Không ngăn được gì? |
| --- | --- | --- |
| Distributed scheduler / leader | Giảm khả năng nhiều trigger chạy đồng thời. | Lease hết hạn khi worker vẫn sống; redelivery hoặc kích hoạt ngoài scheduler. |
| Shared JobRepository + identity ổn định | Tránh nhiều execution cùng một JobInstance theo cơ chế Spring Batch. | Hai instance khác identity nhưng xử lý cùng dữ liệu; side effect đã xảy ra trước crash. |
| Business idempotency | Giảm tác dụng lặp nếu cùng operation được xử lý nhiều lần. | Không tự giải quyết resource exhaustion, backlog hoặc việc job bị kẹt. |

~~~mermaid
flowchart TD
    A["Trigger trên nhiều replica"] --> B{"Cơ chế điều phối lịch?"}
    B -->|"Có"| C["Leader / Quartz cluster / lock"]
    B -->|"Không"| D["Mọi pod có thể gọi launcher"]
    C --> E["JobRepository chung"]
    D --> E
    E --> F["Identifying parameters bất biến theo business key"]
    F --> G["Spring Batch JobExecution/StepExecution"]
    G --> H["Writer / HTTP / broker idempotent"]
    H --> I[("Nguồn dữ liệu đích")]
~~~

## 6. Ví dụ Spring Boot: một JobInstance cho mỗi kỳ nghiệp vụ

Giả sử cần chạy `dailySettlementJob` lúc 01:10 theo múi giờ Việt Nam, xử lý **ngày nghiệp vụ trước đó** từ nguồn `bank-A`. Mục tiêu là mọi replica nếu cùng kích hoạt sẽ đưa **cùng identifying parameters** cho `JobLauncher`.

Trong Spring Boot 3.x, Spring Batch 5.x, nên cấu hình `JobRepository` JDBC trên PostgreSQL dùng chung và chủ động tắt việc Boot tự chạy tất cả job khi ứng dụng khởi động:

~~~yaml
# application.yml — giá trị cấu hình minh họa
spring:
  datasource:
    url: jdbc:postgresql://batch-db.internal:5432/batch_metadata
    username: ${BATCH_DB_USERNAME}
    password: ${BATCH_DB_PASSWORD}
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

Ở đây các bảng metadata Spring Batch **phải được tạo/migrate trước**. `initialize-schema: never` phù hợp khi quản lý bằng Flyway/Liquibase; không cho phép job chạy nếu schema chưa tồn tại. Trong môi trường nhiều DataSource, phải kiểm tra datasource nào được gắn vào `JobRepository`, transaction manager nào quản lý metadata và datasource nào được writer sử dụng.

### 6.1. Tạo identifying parameters ổn định

~~~java
package com.example.integration.batch;

import java.time.LocalDate;
import java.time.ZoneId;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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
public class DailySettlementScheduler {
    private static final Logger log =
            LoggerFactory.getLogger(DailySettlementScheduler.class);
    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private final JobLauncher jobLauncher;
    private final Job dailySettlementJob;

    public DailySettlementScheduler(
            JobLauncher jobLauncher,
            @Qualifier("dailySettlementJob") Job dailySettlementJob) {
        this.jobLauncher = jobLauncher;
        this.dailySettlementJob = dailySettlementJob;
    }

    @Scheduled(cron = "0 10 1 * * *", zone = "Asia/Ho_Chi_Minh")
    public void launchPreviousDay() {
        LocalDate businessDate =
                LocalDate.now(BUSINESS_ZONE).minusDays(1);

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .addString("sourceId", "bank-A", true)
                .toJobParameters();

        try {
            JobExecution execution = jobLauncher.run(dailySettlementJob, params);
            log.info("Settlement launch: date={}, executionId={}, status={}",
                    businessDate, execution.getId(), execution.getStatus());
        } catch (JobExecutionAlreadyRunningException ex) {
            log.info("Settlement already running for {}: {}",
                    businessDate, ex.getMessage());
        } catch (JobInstanceAlreadyCompleteException ex) {
            log.info("Settlement already completed for {}: {}",
                    businessDate, ex.getMessage());
        } catch (JobRestartException | JobParametersInvalidException ex) {
            log.error("Settlement launch rejected for {}", businessDate, ex);
            throw new IllegalStateException(
                    "Settlement requires operator attention", ex);
        }
    }
}
~~~

Ví dụ giả định bean `dailySettlementJob` đã được định nghĩa, có `@EnableScheduling` tại ứng dụng và các replica dùng **cùng metadata database**. Việc gọi `jobLauncher.run(...)` có thể chạy đồng bộ hoặc trả về khi execution còn `STARTING`/`STARTED` tùy cấu hình launcher; log status tại thời điểm trả về **không phải bằng chứng job đã hoàn thành**.

**Điểm cần hiểu đúng:** Code trên không khóa `@Scheduled` giữa các replica; tất cả vẫn có thể gọi launcher. Với `JobRepository` JDBC chung và identity trùng nhau, Spring Batch dùng metadata/transaction để từ chối hoặc phối hợp các attempt không hợp lệ cho cùng instance. Để giảm trigger dư thừa và tránh side effect trước khi launcher, vẫn nên có cơ chế điều phối scheduler phù hợp.

Tính `businessDate` theo giờ địa phương là chính sách nghiệp vụ, không thể thay thế việc xử lý lịch nghỉ, cuối tuần, DST ở múi giờ có thay đổi hoặc lô đến muộn. Nếu job cần chạy lại ngày cũ, truyền **ngày yêu cầu cụ thể** qua API/scheduler quản trị thay vì để hệ thống tự tính “hôm qua” mỗi lần restart.

### 6.2. Tránh hai lỗi nhận diện thường gặp

~~~java
// SAI cho mục tiêu restart cùng kỳ nghiệp vụ:
new JobParametersBuilder()
        .addString("businessDate", "2026-11-20", true)
        .addLong("run.id", System.currentTimeMillis(), true)
        .toJobParameters();

// ĐÚNG về mặt identity nếu thực sự restart cùng lô:
new JobParametersBuilder()
        .addString("businessDate", "2026-11-20", true)
        .addString("sourceId", "bank-A", true)
        .toJobParameters();
~~~

Không nên chỉ đổi `run.id` sang `identifying=false` mà không rõ mục đích: tham số non-identifying có thể thay đổi giữa các execution của cùng instance, nhưng nếu chúng ảnh hưởng tới **đầu vào hoặc kết quả nghiệp vụ**, restart sẽ không còn tái hiện cùng lô. Đặt identity của **toàn bộ dữ liệu logic cần xử lý** làm identifying parameters.

### 6.3. Định nghĩa Job/Step có thể restart

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job dailySettlementJob(JobRepository jobRepository, Step settlementStep) {
    return new JobBuilder("dailySettlementJob", jobRepository)
            .start(settlementStep)
            .build();
}
~~~

`JobBuilder` ở Spring Batch 5 nhận `JobRepository`; không cần dùng các factory builder kiểu cũ đã bị thay đổi qua các lần nâng cấp. Không gọi `preventRestart()` trên job nếu nghiệp vụ yêu cầu resume khi thất bại. Với các step đã `COMPLETED`, Spring Batch thường bỏ qua khi restart; `allowStartIfComplete(true)` chỉ nên bật cho bước thật sự phải chạy lại, vì nó có thể tái thực hiện side effect.

## 7. Chọn cơ chế điều phối giữa các bản sao

Không có một phương án đúng cho mọi kiến trúc:

| Phương án | Cách làm | Khi phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Một scheduler chuyên trách** | Chỉ deployment chuyên chạy lịch; worker có thể scale riêng. | Hệ thống nhỏ/vừa, topology rõ. | Scheduler đơn lẻ cần HA; rolling restart có thể tạo lịch trùng nếu không phối hợp. |
| **DB/distributed lock** | Worker chỉ chạy khi giữ lease cho khóa `jobName + businessKey`. | Muốn giữ `@Scheduled` và tránh nhiều pod kích hoạt. | Lease quá hạn lúc job còn chạy; clock skew, lock store unavailable, split-brain. |
| **Quartz JDBC clustered** | Các node cùng dùng Quartz JDBC JobStore và cùng logical scheduler. | Nhiều trigger, lịch phức tạp, misfire/failover. | Sai JobStore/JobKey, thiếu clustering, schema và clock synchronization. |
| **Spring Batch shared repository** | Launcher ở nhiều pod nhưng cùng JobInstance được điều phối bằng metadata. | Batch có job identity và checkpoint cần restart. | Không giảm mọi trigger; cần đúng identifying params và datasource chung. |
| **Kubernetes CronJob/Job** | Orchestrator tạo một nhóm pod theo lịch; `concurrencyPolicy` và retry theo Kubernetes. | Job vận hành theo lô độc lập với HTTP deployment. | Pod retry hoặc scheduled job mới vẫn có thể phát side effect trùng. |

Thông thường, **scheduler coordination và JobRepository không thay thế nhau**. Quartz giải quyết **ai nên kích hoạt trigger**, Spring Batch giải quyết **trạng thái execution/checkpoint**, còn idempotency giải quyết **đích đã nhận tác dụng nhiều lần hay chưa**.

### 7.1. Distributed lock: hiểu đúng lease và thời gian chạy

Ví dụ một lock tên `settlement:bank-A:2026-11-20` có thời hạn 30 phút:

- Pod A lấy lock và chạy job 45 phút.
- Sau phút thứ 30, lease hết hạn dù A vẫn thực thi.
- Pod B lấy lock, bắt đầu xử lý cùng ngày.

Vì vậy, `lockAtMostFor`/TTL ngắn hơn thời gian chạy thực tế có thể tạo **chạy trùng**. Cần chọn giá trị phù hợp, có **renewal/heartbeat** nếu công cụ hỗ trợ, và **fencing token hoặc ràng buộc ở đích** để worker cũ không tiếp tục ghi sau khi mất quyền sở hữu. Đồng hồ không đồng bộ và mất kết nối tới lock store cũng phải có chính sách.

Ngược lại, lease quá dài sẽ làm job không thể chạy lại trong thời gian dài khi node chết. Một lock chỉ kiểm soát việc **đi vào vùng xử lý**; nó không chứng minh mọi side effect đã commit hay có thể restart ở checkpoint nào.

### 7.2. Quartz clustering trong Spring Boot

Khi dùng Quartz JDBC với các pod chung một database, cấu hình tham khảo:

~~~yaml
spring:
  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    properties:
      org:
        quartz:
          scheduler:
            instanceName: IntegrationScheduler
            instanceId: AUTO
          jobStore:
            isClustered: true
            clusterCheckinInterval: 15000
~~~

Các node phải dùng **cùng database Quartz**, cùng logical scheduler name, job key/trigger key được tổ chức thống nhất và **instanceId khác nhau**. Tạo bảng Quartz đúng version trước khi chạy; không bật script khởi tạo có thể xóa hoặc làm mới bảng trong production. Đồng bộ clock giữa node và đánh giá misfire thresholds theo lịch.

Với Quartz, `@DisallowConcurrentExecution` giúp cấm thực thi đồng thời của **cùng JobDetail**, kể cả giữa các node khi JDBC clustering được cấu hình đúng. Nó không cấm hai JobDetail có JobKey khác nhau chạy cùng logic nghiệp vụ. Nếu Quartz trigger gọi Spring Batch, vẫn dùng identifying JobParameters ổn định và JobRepository chung.

**Không bật Quartz RAMJobStore trên mỗi replica rồi kỳ vọng cơ chế clustered**. Chế độ clustered của Quartz cần persistent JDBC JobStore được cấu hình nhất quán; cấu hình property cluster riêng lẻ không sửa được chuyện các node đang dùng storage khác nhau.

## 8. Quy trình chẩn đoán khi thấy job chạy trùng

Khi phát hiện trùng tác vụ trong production, ưu tiên **ngăn tác dụng lặp** trước khi sửa lịch:

1. **Giới hạn kích hoạt mới** qua scheduler/feature flag hoặc tạm dừng consumer liên quan. Nếu có giao dịch tiền hoặc side effect không idempotent, phối hợp với chủ sở hữu đích; không tự tạo lệnh retry.
2. **Thu thập bằng chứng**: business key, `jobName`, identifying parameters, `JobExecutionId`, pod/instance, thời điểm start/end, correlation ID và loại trigger.
3. **Xác định hai lần chạy là cùng JobInstance hay hai instance khác nhau** bằng `JobRepository`.
4. **Kiểm tra scheduler/lock**: có mấy pod bật `@Scheduled`; Quartz JDBC cluster hay RAM; lease có hết hạn giữa lúc chạy không?
5. **Kiểm tra dữ liệu nghiệp vụ**: khóa unique, upsert, outbox/inbox, idempotency key; các tác dụng ngoài đã hoàn tất ở mức nào?
6. **Đối soát trước sửa**: số bản ghi, tổng tiền, số lần gửi, trạng thái đích và những bản ghi nghi trùng.
7. **Khôi phục từng bước** với đúng identity, giới hạn concurrency và theo dõi cho tới khi backlog trở về bình thường.

### 8.1. SQL đọc-only để xem metadata Spring Batch

Các câu lệnh sau minh họa **schema metadata Spring Batch 5.x trên PostgreSQL**; cần kiểm tra tên bảng/prefix/schema và quyền read-only trong môi trường thực tế:

~~~sql
SELECT
    ji.JOB_NAME,
    ji.JOB_KEY,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailySettlementJob'
ORDER BY je.CREATE_TIME DESC
LIMIT 50;
~~~

Muốn xem identifying parameters của một execution:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_TYPE,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = :executionId
ORDER BY PARAMETER_NAME;
~~~

Ở Spring Batch 5.x, bảng parameter có các cột như `PARAMETER_NAME`/`PARAMETER_TYPE`/`PARAMETER_VALUE`; **không chép truy vấn này cho schema Spring Batch 4.x** vì định dạng metadata từng phiên bản khác nhau. Khi nhiều execution cùng ngày được tạo dưới nhiều `JOB_INSTANCE_ID`, xem ngay `JOB_KEY` và các identifying parameter bị thay đổi.

Kiểm tra step nào đã commit:

~~~sql
SELECT
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :executionId
ORDER BY STEP_EXECUTION_ID;
~~~

**Không sửa `BATCH_*` bằng SQL thủ công** để giải phóng running flag hay thay đổi execution status. Một thay đổi thiếu đồng bộ giữa các bảng có thể phá cơ chế restart, còn worker đang sống có thể tiếp tục ghi dữ liệu theo checkpoint cũ.

## 9. Quy trình restart khi job thất bại hoặc bị dừng

Spring Batch có thể restart JobInstance thất bại/dừng khi job cho phép và metadata còn nhất quán. Quy trình an toàn:

1. **Xác định JobInstance** từ tên job + identifying parameters; tránh khởi động nhầm kỳ nghiệp vụ.
2. **Xác minh trạng thái execution mới nhất** và chủ sở hữu process. Nếu `STARTED`, xác nhận worker còn sống hay đã crash.
3. **Tìm nguyên nhân gốc**: file thiếu, schema sai, lỗi HTTP, deadlock, secret hết hạn, broker dừng hoặc lỗi dữ liệu.
4. **Kiểm tra nguồn vào có bất biến không**: file/checksum, snapshot API, phân trang, schema và version của reader.
5. **Kiểm tra checkpoint**: step context có lưu vị trí hợp lệ? Những chunk nào đã commit? Các side effect ngoài DB có bị gọi trước crash?
6. **Sửa nguyên nhân**, sau đó restart **cùng JobInstance** bằng supported operation và cùng identifying parameters/JobExecution liên quan.
7. **Đối soát dữ liệu và theo dõi hoàn tất**: số lượng, tổng tiền, business key, duplicate count, external status và queue/event lag.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Job chưa hoàn tất"] --> B{"Execution mới nhất?"}
    B -->|FAILED hoặc STOPPED| C["Đối chiếu nguyên nhân + input + checkpoint"]
    B -->|STARTED| D{"Worker còn chạy?"}
    D -->|Có| E["Không restart; theo dõi hoặc stop có kiểm soát"]
    D -->|Không| F["Incident runbook: xác minh và xử lý metadata kẹt"]
    B -->|COMPLETED| G["Không restart cùng instance; đánh giá nhu cầu chạy lô mới"]
    C --> H["Restart đúng JobInstance"]
    F --> H
    H --> I["Idempotency + reconciliation"]
~~~

### 9.1. JobExecution `STARTED` kẹt sau khi pod chết

Một process chết đột ngột có thể không kịp cập nhật `JobExecution` từ `STARTED` sang `FAILED`. Spring Batch không tự đảm bảo mọi execution mồ côi được sửa trạng thái trong tất cả môi trường. Nếu gọi restart ngay, framework có thể từ chối vì xem job **vẫn đang chạy**.

Quy trình xử lý cần:

- Kiểm tra deployment, pod UID, heartbeat/log/metrics, việc container thực sự đã dừng và liệu có worker remote hoặc task async còn xử lý hay không.
- Tạm chặn trigger mới; bảo vệ output bằng fencing/idempotency nếu có khả năng worker cũ quay lại.
- Ghi nhận `executionId` và snapshot metadata cùng các giao dịch nghiệp vụ đã commit.
- Dùng **công cụ vận hành/API JobRepository được hệ thống hỗ trợ** để đưa execution mồ côi về trạng thái có thể quản trị theo runbook đã kiểm thử. Việc can thiệp metadata chỉ thực hiện sau khi chắc chắn không còn process sở hữu và có phương án rollback/audit.
- Restart đúng instance, đối soát những chunk có thể đã hoàn tất nhưng chưa được checkpoint.

`JobOperator.stop(executionId)` chủ yếu phục vụ dừng **cooperative execution còn sống**; gọi stop cho một process đã chết không bảo đảm khôi phục metadata. Không xây cơ chế “đổi mọi STARTED quá 10 phút thành FAILED” nếu job hợp lệ có thể chạy lâu hơn 10 phút.

### 9.2. `COMPLETED` không phải sự cố restart

Nếu JobInstance đã `COMPLETED`, Spring Batch chặn việc chạy lại cùng instance là hành vi đúng. Nếu cần **tái xử lý**:

1. Xác định đó là một phiên bản nguồn mới hay chỉ chạy lại cùng dữ liệu để sửa sai.
2. Định nghĩa một business version/reprocess ID mới nếu thật sự muốn tạo JobInstance mới.
3. Đảm bảo writer idempotent, có thể kiểm tra xung đột payload, không tạo trùng side effect.
4. Không sửa trạng thái `COMPLETED` thành `FAILED` chỉ để vượt qua kiểm tra của framework.

**Restart** nghĩa là tiếp tục cùng lần xử lý logic; **reprocess** là chạy một lần xử lý logic mới được phép. Hai thao tác có hợp đồng và rủi ro khác nhau.

## 10. Khi restart lại từ đầu hoặc sai checkpoint

Giả sử job đọc file 20.000 dòng theo chunk 100. Nó đã commit 120 chunk và sau đó crash. Khi restart, lý tưởng reader khôi phục từ sau checkpoint thứ 120. Tuy nhiên:

| Hiện tượng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Đọc lại từ dòng đầu | Mỗi lần dùng `run.id` khác; reader `saveState=false`; không đăng ký `ItemStream`. | Giữ identifying params và bật/stateful reader đúng lifecycle. |
| Skip sai dòng khi resume | File đã sửa hoặc thêm/xóa dòng; sorting/paging không ổn định. | Dùng nguồn immutable, checksum, snapshot ID và sắp xếp theo khóa ổn định. |
| Step đã xong lại chạy gây trùng | `allowStartIfComplete(true)` hoặc tạo instance mới. | Chỉ bật khi nghiệp vụ cần; giữ output idempotent. |
| Step mới dùng context của step cũ | Dùng sai tên reader key, phạm vi job/step context hoặc serialization thay đổi. | Tách key, `ExecutionContextPromotionListener` nếu cần chia sẻ giữa steps. |
| Checkpoint có nhưng dữ liệu đích chưa hoàn tất | Metadata và business DB dùng transaction manager khác. | Thiết kế transaction, outbox hoặc đối soát/replay an toàn. |
| Dữ liệu DB đã commit nhưng checkpoint chưa lưu | Crash giữa hai nguồn giao dịch độc lập. | Unique key/inbox/idempotent writer; không mặc định exactly once. |

Ở chunk-oriented step, `ItemStream.open(ExecutionContext)` đọc state, `ItemStream.update(...)` cập nhật state lúc checkpoint, rồi framework persist thông qua JobRepository. Nếu dùng reader/writer tự viết, phải triển khai và **đăng ký** ItemStream đúng lifecycle; không chỉ lưu biến đếm `int currentRow` trong object JVM.

### 10.1. Ranh giới transaction quyết định khả năng khôi phục

~~~mermaid
sequenceDiagram
    participant Job as Batch Step
    participant DB as Database nghiệp vụ
    participant Repo as JobRepository
    participant API as HTTP/Broker ngoài transaction
    Job->>DB: Ghi chunk
    Job->>API: Tạo side effect
    API-->>Job: Đã xử lý
    Job->>Repo: Cập nhật checkpoint
    Note over Job,Repo: Process crash trước commit metadata
    Note over DB,API: Restart có thể thực hiện lại side effect
~~~

Ví dụ minh họa rủi ro **khi tài nguyên có transaction độc lập**: rollback JDBC không tự thu hồi một payment hoặc HTTP POST đã thực hiện. Với Batch writer ghi một database khác JobRepository, checkpoint và business commit cũng có thể lệch nhau.

Thiết kế an toàn thường cần khóa nghiệp vụ duy nhất, operation ID giữ nguyên qua retry/restart, idempotency tại đích, reconciliation và **transactional outbox** nếu publish event sau commit DB. Không xem một flag “đã xử lý” trong `ExecutionContext` là giao dịch phân tán với đối tác.

## 11. Nâng cấp Spring Boot/Spring Batch mà không phá khả năng restart

Vấn đề restart thường xuất hiện ngay sau nâng cấp vì metadata không còn tương thích hoặc định danh job/step thay đổi. Một kế hoạch nâng cấp phải kiểm tra:

| Hạng mục | Điều cần xác minh | Hậu quả nếu bỏ qua |
| --- | --- | --- |
| **Phiên bản Spring Boot / Spring Batch** | Ma trận tương thích dependency, JDK, Hibernate/JPA và API builder. | Lỗi bean, lỗi class, sai transaction manager. |
| **Metadata schema** | Migration bảng `BATCH_*` theo **đúng đường nâng cấp**; backup trước thay đổi. | Không đọc được parameters/context, launch/restart thất bại. |
| **Job identity** | Tên job và identifying parameters giữ nghĩa cũ. | Tạo JobInstance mới và chạy lại dữ liệu cũ. |
| **Tên step/reader** | `Step` names, ItemStream name và các key trong `ExecutionContext` ổn định. | Reader không tìm thấy checkpoint hoặc step bị chạy lại. |
| **ExecutionContext serializer** | Định dạng và class dữ liệu đã lưu còn decode được không. | Job cũ bị lỗi deserialize sau deploy. |
| **Transaction/data source** | JobRepository dùng đúng schema, writer cùng transaction nếu dự kiến. | Checkpoint và dữ liệu nghiệp vụ lệch. |
| **Scheduler/Quartz** | Quartz JobStore, instance ID, JobKey, trigger key, misfire policies và schema. | Lịch kích hoạt trùng hoặc không fire sau nâng cấp. |
| **Application startup** | Có vô tình bật auto-run job trên mọi pod sau deploy không? | Nhiều job chạy ngay khi rollout. |

### 11.1. Spring Batch 4 → 5 có thay đổi metadata/API

Khi nâng từ stack cũ lên Spring Boot 3/Spring Batch 5, cần đối chiếu tài liệu migration tương ứng. Ví dụ, schema tham số job trong Batch 5 có các cột `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE` và `IDENTIFYING` thay cho một số cột/kiểu trong Batch 4. Nếu deploy code mới nhưng chưa migrate schema, launcher hoặc reader metadata có thể thất bại. Các API builder như `new JobBuilder(name, jobRepository)` và `new StepBuilder(name, jobRepository)` thay đổi cách khởi tạo so với kiểu dựa trên các factory trước đây.

Không tự tạo lại bảng metadata trống để “giải quyết” migration: dữ liệu checkpoint và lịch sử execution sẽ mất, trong khi tác dụng nghiệp vụ có thể đã commit. **Backup, chạy migration đúng version, kiểm thử restart trên snapshot đã ẩn dữ liệu nhạy cảm** và chuẩn bị rollback có kiểm soát.

### 11.2. Quy trình rollout an toàn

1. Liệt kê JobInstance `STARTED`/`FAILED`/`STOPPED`, xác định job kéo dài và nguồn dữ liệu không thể tái lập.
2. Ngừng trigger mới hoặc để drain các job quan trọng theo policy; tránh version cũ và mới cùng xử lý một business window.
3. Backup metadata và dữ liệu liên quan; chạy migration theo thứ tự rõ ràng.
4. Khởi động phiên bản mới trong staging với **metadata từ phiên bản cũ**, xác minh restart một instance thất bại thực sự.
5. Rollout có giới hạn, bảo đảm không có replica trỏ về schema metadata khác hoặc tên job khác ngoài kế hoạch.
6. Quan sát log launch, `JobExecutionAlreadyRunningException`, `JobRestartException`, số duplicate và freshness dữ liệu đích.
7. Có quy trình đảo phiên bản ứng dụng **và** quyết định tương thích schema; rollback application không có nghĩa database metadata đã tự trở về version trước.

## 12. Hai runbook xử lý sự cố điển hình

### 12.1. Tình huống A: mỗi ngày có ba bản ghi đối soát trùng

**Bối cảnh:** Hệ thống có ba replica, mỗi pod gọi scheduler lúc 01:00. Sau nâng cấp, bảng đối soát nhận ba bộ dữ liệu cùng ngày.

**Bằng chứng cần tìm:** Ba `JobExecution` có cùng businessDate, `JOB_INSTANCE_ID` giống hay khác, `sourceId` và `run.id` của từng attempt, cấu hình datasource của JobRepository, trigger `@Scheduled` có bật ở mọi pod hay không.

**Nhánh chẩn đoán:**

- Nếu ba instance khác `JOB_KEY` vì UUID/timestamp là identifying → sửa identity theo business key.
- Nếu mỗi pod trỏ về repository khác nhau → thống nhất metadata JDBC dùng chung và migration/schema/permission.
- Nếu có một JobInstance nhưng writer vẫn tạo side effect trùng sau crash/retry → kiểm tra transaction, idempotency, event ID và ack broker.
- Nếu Quartz chạy nhiều JobKey cho cùng một kỳ → chuẩn hóa JobDetail/trigger identity, JDBC clustering và giới hạn concurrency.

**Phục hồi:** Dừng tác vụ sinh trùng, đối soát theo `businessDate + sourceId + operationId`, sửa dữ liệu có audit và đúng quyền, rồi mở lại với một lịch chung và dữ liệu kiểm thử xác nhận không lặp. **Không xóa đại trà các dòng trùng trước khi biết giao dịch nào đã được đối tác xử lý.**

### 12.2. Tình huống B: pod chết, restart báo “already running”

**Bối cảnh:** Job đã chạy 50 phút, pod bị kill trong rolling deployment; metadata còn `STARTED`. Scheduler mới gọi lại cùng businessDate và nhận `JobExecutionAlreadyRunningException`.

**Bằng chứng cần tìm:** Pod cũ đã chết thật chưa, có task remote còn hoạt động không, execution ID cuối, step context/checkpoint, transaction DB đã commit đến đâu và lệnh gọi HTTP/broker đã có side effect hay chưa.

**Phục hồi:** Cô lập trigger mới, xác minh không còn worker cũ, tuân theo runbook can thiệp trạng thái orphan bằng API/công cụ được hỗ trợ, sau đó restart đúng JobInstance. Nếu metadata không thể khôi phục an toàn, phải lập **kế hoạch reprocess có đối soát và idempotency** thay vì tự tăng `run.id` để bỏ qua khóa.

**Điều cần phòng ngừa:** graceful shutdown/stop policy, thời gian chờ termination phù hợp, worker heartbeat/lifecycle có kiểm soát, retention metadata, checkpoint an toàn và bài kiểm thử crash giữa chunk.

## 13. Quan sát và kiểm thử ở quy mô nhiều replica

### 13.1. Metric và log nên thu thập

- **Scheduler:** số lần trigger theo pod, job key, business window, số lần lấy lock thành công/thất bại, lease expiry và số trigger bị từ chối.
- **Spring Batch:** job name, JobInstance ID, JobExecution ID, identifying parameter đã redacted, trạng thái, start/end time, duration, `readCount`/`writeCount`/`commitCount`/`rollbackCount`/`skipCount`.
- **Restart:** số execution `STARTED` quá hạn, số restart thành công/thất bại, checkpoint age, lỗi deserialize context, lỗi schema migration.
- **Broker/outbound:** event ID, duplicate count, consumer lag, retry/DLQ, lỗi 429/timeout và số side effect cần reconciliation.
- **Nghiệp vụ:** tổng bản ghi/số tiền theo `businessDate + sourceId`, các khóa trùng, bản ghi thiếu và trạng thái đối tác.

Đặt `jobName` và loại job ở label metric, nhưng tránh đưa `executionId`, `orderId` hoặc hàng triệu business key vào label có cardinality cao; những ID này phù hợp hơn với structured log/tracing có retention và quyền truy cập.

### 13.2. Các bài kiểm thử bắt buộc

| Kịch bản | Điều phải chứng minh |
| --- | --- |
| Ba application context/pod cùng gọi launcher một businessDate | Chỉ một JobInstance logic được chạy hợp lệ; số tác dụng nghiệp vụ đúng một lần theo hợp đồng. |
| Ba pod có `@Scheduled` nhưng dùng JobRepository chung | Nhiều trigger được quan sát, nhưng không tạo ba lần xử lý cùng identity. |
| Bật `run.id` identifying khác nhau | Test tái hiện lỗi tạo nhiều JobInstance để chứng minh chính sách nhận diện. |
| Crash trước commit chunk | Những ghi nhận trong transaction rollback; restart từ checkpoint đã commit. |
| Crash sau HTTP side effect nhưng trước checkpoint | Operation ID giữ nguyên; idempotency/reconciliation ngăn trùng. |
| Crash tạo `STARTED` orphan | Runbook phát hiện, không cho hai worker cùng xử lý, phục hồi metadata được kiểm soát. |
| JobInstance đã `COMPLETED` | Restart cùng identifying params bị từ chối; reprocess chỉ theo version mới có chủ đích. |
| Source file/snapshot thay đổi sau failure | Phát hiện checksum hoặc version sai, không resume từ offset không đáng tin. |
| Rollout phiên bản mới trong lúc job cũ chạy | Không có hai version cùng xử lý một kỳ; metadata/schema tương thích. |
| Quartz JDBC cluster gặp node failover | Trigger không phát tác dụng trùng trong điều kiện test; key và misfire policy chính xác. |
| Distributed lock hết hạn khi job đang chạy | Fencing/idempotent writer chặn worker cũ và mới cùng ghi sai. |
| Retry broker/redelivery | Consumer không tạo bản ghi hoặc gọi API đích trùng không kiểm soát. |

Với Spring Batch, dùng `@SpringBootTest`/`spring-batch-test`, database metadata **thật hoặc Testcontainers**, đồng thời mở hai context/tiến trình dùng chung DB để mô phỏng cạnh tranh. Không xóa `JobRepository` giữa attempt thất bại và attempt restart trong cùng bài test; làm vậy xóa đúng checkpoint cần xác minh.

Kiểm thử “chỉ có một JobExecution” chưa đủ khi worker có side effect ngoài transaction: phải assert **kết quả nghiệp vụ ở đích**, số lần HTTP được gửi và khả năng đối soát sau timeout. Dùng fault injection có kiểm soát tại điểm commit DB, update JobRepository, publish broker và ack, không chỉ mock phương thức trả `true`.

## 14. Checklist gỡ lỗi và nâng cấp

- [ ] Xác định nguồn trigger (`@Scheduled`, Quartz, Kubernetes, broker, API) và số pod có thể kích hoạt.
- [ ] Xác định khóa nghiệp vụ bất biến (`businessDate + sourceId + version`) và ánh xạ sang identifying JobParameters.
- [ ] Tất cả pod dùng **JobRepository JDBC chung**, cùng schema/prefix, transaction và metadata migration phù hợp.
- [ ] Không thêm UUID/timestamp/`run.id` identifying mới mỗi khi muốn **restart cùng lô**.
- [ ] Nếu có scheduler phân tán/lease/Quartz cluster, đã kiểm tra lock ownership, failover, JobKey, clock skew và tránh overlap.
- [ ] Writer, outbound HTTP và message consumer có idempotency/unique constraint, operation ID và reconciliation.
- [ ] Phân biệt `FAILED`/`STOPPED`/`STARTED` orphan/`COMPLETED`; có runbook khi không thể restart bằng API thông thường.
- [ ] Reader/ItemStream, ExecutionContext và input snapshot đủ ổn định để checkpoint có ý nghĩa.
- [ ] Khi nâng cấp, đã kiểm tra schema `BATCH_*`, serializer, job/step name, transaction manager và tính tương thích của job cũ.
- [ ] Đã kiểm thử hai replica chạy cùng kỳ, crash/restart giữa chunk, lease expiry, rolling deployment và dữ liệu đích trùng lặp.
- [ ] Có metric, log, alert và bảng đối soát để xác định *đã chạy gì* và *đích đã tiếp nhận gì* thay vì chỉ nhìn status scheduler.

**Kết luận:** “Job chạy trùng giữa các bản sao” là vấn đề **điều phối trigger, nhận diện JobInstance và idempotency**; “job không khởi động lại được” là vấn đề **metadata, trạng thái execution, checkpoint, transaction và khả năng tái hiện nguồn dữ liệu**. Trong Spring Boot Integration, cần giải quyết đồng thời các lớp này, nhất là khi job kết nối nhiều database, HTTP client, cache và broker. Chỉ thay cron, tăng `run.id` hoặc sửa trực tiếp một dòng metadata không đủ để bảo đảm kết quả nghiệp vụ đúng sau sự cố hay sau một lần nâng cấp.
