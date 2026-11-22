# Job, JobDetail, Trigger và vòng đời thực thi trong Quartz

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot kết nối HTTP client, database, cache, broker thông điệp và adapter của Spring Integration để tạo những luồng xử lý thực tế. Nhiều công việc cần chạy theo lịch: đồng bộ sản phẩm từ API đối tác, quét outbox chưa phát, đối soát giao dịch, tái tạo cache hoặc xóa dữ liệu quá hạn.

**Quartz Scheduler** giúp quản lý lịch chạy qua bốn thành phần chính: `Job`, `JobDetail`, `Trigger` và `Scheduler`. Bài thuộc chương **Quartz**, tập trung vào **Job, JobDetail, Trigger và vòng đời thực thi**, từ khi khai báo, đến giờ chạy, thành công/thất bại, misfire, pause/resume và recovery. Trong hệ thống tích hợp, scheduler chỉ quyết định **khi nào gọi**; hợp đồng dữ liệu, giao dịch, xử lý lỗi, retry, idempotency và observability vẫn phải được thiết kế ở tầng nghiệp vụ và adapter.

Sau bài học, bạn có thể:

- Phân biệt lớp `Job` chứa mã thực thi, `JobDetail` định danh công việc, `Trigger` đặt lịch và `Scheduler` điều phối.
- Tạo các bean `JobDetail`, `SimpleTrigger` và `CronTrigger` cho Spring Boot auto-configure.
- Đọc `JobExecutionContext` và phân biệt lần chạy dự kiến với thời điểm chạy thực.
- Giải thích misfire, concurrency, `JobDataMap`, exception, recovery và trạng thái của trigger.
- Lựa chọn `RAMJobStore` hoặc JDBC JobStore, thiết kế scheduler chạy nhiều replica an toàn.
- Kiểm thử registration, execution, lịch cron và dữ liệu nghiệp vụ, đồng thời theo dõi kết quả thực.

> **Điểm cần nhớ:** Quartz không tự bảo đảm exactly-once, transaction phân tán hay retry an toàn. Một Job chạy lại có thể gây side effect trùng nếu adapter không có idempotency.

## 1. Khi nào Quartz phù hợp hơn @Scheduled?

Spring Framework có `@Scheduled` cho các tác vụ định kỳ đơn giản; Quartz thích hợp khi lịch chạy trở thành một phần trạng thái vận hành cần quản lý độc lập.

| Nhu cầu | `@Scheduled` | Quartz |
| --- | --- | --- |
| Chạy đơn giản theo cron/fixed delay trong một app | Phù hợp | Cũng làm được |
| Định danh từng job/trigger bằng tên, nhóm | Phải tự thiết kế | `JobKey`, `TriggerKey` |
| Tạo/sửa/pause/resume lịch lúc runtime | Cần tự bổ sung | `Scheduler` API |
| Giữ lịch qua restart | Không có JobStore mặc định | JDBC JobStore |
| Cấu hình hành vi bỏ lỡ lịch (misfire) | Ít lựa chọn hơn | Chính sách theo trigger |
| Điều phối trigger trên nhiều instance | Phải tự phối hợp | Quartz clustering với JDBC store |
| Chống áp dụng một giao dịch nghiệp vụ hai lần | Phải tự thiết kế | **Vẫn phải tự thiết kế** |

Ví dụ: một tác vụ đồng bộ Catalog chạy mỗi 15 phút. Nếu triển khai 3 replica dùng RAMJobStore riêng, cả ba đều có thể chạy cùng một logic. JDBC JobStore với clustering có thể điều phối trigger, nhưng unique constraint, checkpoint và idempotency vẫn cần thiết để khôi phục sau sự cố.

## 2. Các đối tượng tham gia một lần chạy

~~~mermaid
flowchart LR
    A["Spring Boot"] --> B["Scheduler"]
    B --> C["Trigger: thời điểm chạy"]
    C --> D["JobDetail: định danh + cấu hình"]
    D --> E["Job instance: execute(context)"]
    E --> F["Application service"]
    F --> G["HTTP / SQL / cache / broker"]
    H["JobStore"] -.-> B
    I["Quartz thread pool"] -.-> B
~~~

| Thành phần | Chức năng | Không nên nhầm |
| --- | --- | --- |
| `Job` | Interface với `execute(JobExecutionContext)` | Không phải một singleton giữ business state |
| `JobDetail` | Định nghĩa job gồm Job class, identity và JobDataMap | Không phải lịch chạy |
| `Trigger` | Quy tắc khi nào một JobDetail được fire | Không phải code xử lý |
| `Scheduler` | Đăng ký, chọn và điều phối job/trigger | Không tự transaction hóa HTTP/DB |
| `JobStore` | Lưu metadata, trạng thái job/trigger | Không phải business checkpoint |
| `JobExecutionContext` | Metadata một lần fire | Không phải hợp đồng dữ liệu nghiệp vụ |

### 2.1. Job: mã thực thi

`org.quartz.Job` chỉ yêu cầu phương thức `execute(...)`:

~~~java
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;

public class SampleJob implements Job {

    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {
        var key = context.getJobDetail().getKey();
        System.out.println("Quartz đang chạy " + key);
    }
}
~~~

`System.out.println` chỉ để minh họa. Trong hệ thống thực, dùng logging có cấu trúc và không ghi secret/payload nhạy cảm. Quartz tạo một **Job instance mới cho từng lần fire** thông qua `JobFactory`. Vì vậy không đặt connection, cursor, checkpoint hoặc token vào field mutable của Job và cho rằng nó sẽ được giữ giữa các lần chạy.

### 2.2. JobDetail: định nghĩa và danh tính

~~~java
import org.quartz.JobBuilder;
import org.quartz.JobDetail;

JobDetail detail = JobBuilder.newJob(SampleJob.class)
        .withIdentity("catalogSync", "integration")
        .withDescription("Đồng bộ Catalog theo lịch")
        .usingJobData("sourceSystem", "catalog")
        .storeDurably()
        .build();
~~~

`JobKey` là cặp tên/nhóm, ví dụ `catalogSync`/`integration`, dùng để xác định đúng công việc trên scheduler. Hai JobDetail có thể dùng cùng một Java class nhưng **khác JobKey** và được Quartz xem là hai công việc khác nhau.

`storeDurably()` cho phép định nghĩa job tồn tại ngay cả khi không có trigger liên kết; nó không bảo đảm tiến độ nghiệp vụ được lưu bền vững. `usingJobData(...)` truyền giá trị cấu hình nhỏ, không phải cơ chế lưu trạng thái thay cho database.

### 2.3. Trigger: điều kiện chạy

Một JobDetail có thể gắn nhiều trigger, chẳng hạn CronTrigger định kỳ và một SimpleTrigger cho lần chạy bổ sung.

~~~java
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

Trigger once = TriggerBuilder.newTrigger()
        .withIdentity("catalogOnce", "integration")
        .forJob(detail)
        .startNow()
        .build();
~~~

`startNow()` đặt thời gian bắt đầu tại thời điểm tạo trigger. Tạo object Trigger chưa làm `execute()` chạy; scheduler phải đăng ký trigger, đang hoạt động và có thread để chạy.

| Trigger | Lịch chạy | Ví dụ |
| --- | --- | --- |
| `SimpleTrigger` | Một thời điểm hoặc khoảng lặp + repeat count | Chạy một lần, mỗi 5 phút |
| `CronTrigger` | Quartz cron + múi giờ | 02:00 mỗi ngày, mỗi 15 phút |
| `CalendarIntervalTrigger` | Theo đơn vị lịch như ngày, tuần, tháng | Chạy mỗi tháng |
| `DailyTimeIntervalTrigger` | Khoảng thời gian trong ngày và ngày phù hợp | Mỗi 10 phút trong giờ làm việc |

### 2.4. Scheduler: điều phối và quản trị

`Scheduler` lưu và tra cứu lịch, quyết định khi nào kích hoạt JobDetail, cấp thread, gọi JobFactory và cập nhật lần chạy kế tiếp.

Các API hay dùng:

- `scheduleJob(detail, trigger)`: tạo định nghĩa và lịch mới.
- `getJobDetail(jobKey)` / `getTrigger(triggerKey)`: tra metadata.
- `triggerJob(jobKey)`: yêu cầu fire thêm một lần.
- `pauseJob(jobKey)` / `resumeJob(jobKey)`: dừng/tái kích hoạt các trigger liên quan.
- `rescheduleJob(triggerKey, newTrigger)`: đổi lịch.
- `deleteJob(jobKey)`: xóa job cùng trigger liên quan.
- `start()`, `standby()`, `shutdown(waitForJobsToComplete)`: lifecycle của scheduler.

Thao tác quản trị có thể ảnh hưởng dữ liệu lịch trong JDBC JobStore, nên cần xác thực, phân quyền và audit; không cho API công khai tự tùy ý chọn class Job.

## 3. Spring Boot tự cấu hình Quartz

Với Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
}
~~~

Khi dependency và điều kiện auto-configuration phù hợp, Boot tạo `SchedulerFactoryBean` và bean `Scheduler`; các bean `JobDetail`, `Trigger` và `Calendar` được liên kết vào scheduler.

~~~yaml
spring:
  quartz:
    auto-startup: true
    startup-delay: 5s
    wait-for-jobs-to-complete-on-shutdown: true
    overwrite-existing-jobs: false
    properties:
      org.quartz.threadPool.threadCount: 5
~~~

| Property | Ý nghĩa |
| --- | --- |
| `auto-startup` | Có tự chạy scheduler khi context sẵn sàng không |
| `startup-delay` | Trì hoãn scheduler start, không phải trì hoãn riêng từng Job |
| `wait-for-jobs-to-complete-on-shutdown` | Có chờ job đang thực thi xong khi dừng app không |
| `overwrite-existing-jobs` | Có ghi đè định nghĩa JobDetail/Trigger đã tồn tại trong JobStore khi startup |
| `org.quartz.threadPool.threadCount` | Số thread Quartz cấp cho các job đồng thời |

Mặc định phổ biến là **RAMJobStore**; lịch ở trong bộ nhớ process. Phần JDBC JobStore sẽ giải thích lưu trạng thái qua restart và clustering.

Quartz là thư viện riêng được Spring Boot quản lý dependency. Giữ version thư viện tương thích với Boot, đặc biệt khi chuyển giữa các thế hệ Boot/Spring.

## 4. Ví dụ: đồng bộ Catalog API mỗi 15 phút

Giả sử hệ thống phải đọc sản phẩm cập nhật từ API đối tác, ghi projection và checkpoint vào database. Scheduler chỉ định thời gian chạy; logic đồng bộ thuộc use case riêng.

### 4.1. Hợp đồng nghiệp vụ

~~~java
// CatalogSyncUseCase.java
public interface CatalogSyncUseCase {
    void synchronizeNextBatch();
}
~~~

Một Spring service triển khai interface này chịu trách nhiệm kết nối HTTP client, kiểm tra dữ liệu, transaction và checkpoint. Bài này giả định implementation đã được cung cấp qua Spring container.

### 4.2. Job gọi use case

~~~java
// CatalogSyncJob.java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.springframework.beans.factory.annotation.Autowired;

@DisallowConcurrentExecution
public class CatalogSyncJob implements Job {

    @Autowired
    private CatalogSyncUseCase useCase;

    @Override
    public void execute(JobExecutionContext context)
            throws JobExecutionException {
        try {
            useCase.synchronizeNextBatch();
        } catch (RuntimeException exception) {
            throw new JobExecutionException(
                    "Không hoàn tất đồng bộ Catalog", exception);
        }
    }
}
~~~

Trong cấu hình Boot thông thường, `JobFactory` được tích hợp với Spring để autowire job; nếu tự thay JobFactory hoặc tự tạo scheduler, phải xác nhận việc inject dependency còn hoạt động. Không coi Job là bean singleton thông thường và không để nó giữ mutable state xuyên các lần fire.

`@DisallowConcurrentExecution` điều phối các lần chạy **cùng JobKey** để chúng không chồng lấn trong scheduler được cấu hình tương ứng; hai JobDetail khác JobKey nhưng cùng Java class vẫn có thể chạy đồng thời.

### 4.3. Định nghĩa JobDetail và CronTrigger

~~~java
// CatalogQuartzConfiguration.java
import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogQuartzConfiguration {

    @Bean("catalogSyncJobDetail")
    JobDetail catalogSyncJobDetail() {
        return JobBuilder.newJob(CatalogSyncJob.class)
                .withIdentity("catalogSync", "integration")
                .withDescription("Đồng bộ Catalog API")
                .storeDurably()
                .requestRecovery(true)
                .build();
    }

    @Bean("catalogSyncTrigger")
    Trigger catalogSyncTrigger(
            @Qualifier("catalogSyncJobDetail") JobDetail detail,
            @Value(
                    "${integrations.catalog.sync-cron:0 0/15 * * * ?}")
                    String cron) {

        return TriggerBuilder.newTrigger()
                .withIdentity("catalogSyncCron", "integration")
                .forJob(detail)
                .withSchedule(
                        CronScheduleBuilder.cronSchedule(cron)
                                .inTimeZone(
                                        TimeZone.getTimeZone(
                                                "Asia/Ho_Chi_Minh"))
                                .withMisfireHandlingInstructionDoNothing())
                .build();
    }
}
~~~

~~~yaml
# application.yml
integrations:
  catalog:
    sync-cron: "0 0/15 * * * ?"
~~~

`integrations.catalog.sync-cron` là thuộc tính ứng dụng tự định nghĩa và được inject qua `@Value`. Nó không phải property Quartz tự hiểu. Mỗi bean `JobDetail`/`Trigger` được Boot đăng ký khi cấu hình điều kiện phù hợp; **không gọi thêm `scheduler.scheduleJob(...)` cho cùng job** nếu không có chủ đích.

Biểu thức Quartz cron `0 0/15 * * * ?` có sáu trường (giây, phút, giờ, ngày tháng, tháng, ngày tuần), nghĩa là chạy ở phút 0, 15, 30, 45 của mỗi giờ, giây 0. `?` đánh dấu không chỉ định điều kiện cụ thể cho trường ngày trong tuần. Đây là cú pháp Quartz, không phải cron năm trường của Linux.

### 4.4. Thứ tự xảy ra khi khởi động

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant S as Quartz Scheduler
    participant T as CronTrigger
    participant J as CatalogSyncJob
    participant U as CatalogSyncUseCase
    B->>S: Đăng ký JobDetail và Trigger
    B->>S: start theo auto-startup
    S->>T: Tính nextFireTime
    T-->>S: Đến giờ fire
    S->>J: Tạo instance, execute(context)
    J->>U: synchronizeNextBatch()
    U-->>J: Hoàn thành hoặc lỗi
    J-->>S: Kết quả lần chạy
    S->>T: Tính lần fire tiếp theo
~~~

Một bean JobDetail được tạo không có nghĩa job đã được thực thi. Scheduler phải start, trigger đang hoạt động, có thread và không bị chặn bởi policy khác.

## 5. Vòng đời mỗi lần Job được thực thi

Quá trình có thể hình dung thành các giai đoạn:

1. **Registration**: JobDetail/Trigger được đưa vào JobStore.
2. **Waiting**: Scheduler tính `nextFireTime` và chờ đến hạn.
3. **Acquisition**: Quartz nhận trigger khả dụng, xét JobKey và thread pool.
4. **Job instantiation**: JobFactory tạo instance và inject dependency.
5. **Execution**: Gọi `execute(JobExecutionContext)` trong Quartz worker thread.
6. **Completion/error**: Handler trả về hoặc ném `JobExecutionException`; listener được thông báo.
7. **Rescheduling**: Trigger tính lịch kế, hoàn thành hoặc chuyển trạng thái khác.
8. **Pause/resume/delete/recovery**: Có thể thay đổi theo API quản trị hoặc lỗi hệ thống.

Các trạng thái public của Trigger gồm `NORMAL`, `PAUSED`, `COMPLETE`, `ERROR`, `BLOCKED` và `NONE`. Chúng diễn tả tình trạng scheduler/trigger; **không khẳng định nghiệp vụ đã commit hoặc đã gửi broker**.

### 5.1. Metadata trong JobExecutionContext

~~~java
@Override
public void execute(JobExecutionContext context)
        throws JobExecutionException {

    var jobKey = context.getJobDetail().getKey();
    var triggerKey = context.getTrigger().getKey();

    var scheduledTime = context.getScheduledFireTime();
    var fireTime = context.getFireTime();
    var nextTime = context.getNextFireTime();

    var fireId = context.getFireInstanceId();
    boolean recovering = context.isRecovering();

    // Log metadata cần thiết, giới hạn thông tin nhạy cảm.
}
~~~

| Giá trị | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| `scheduledFireTime` | Khi trigger dự kiến fire | Đo độ trễ scheduler |
| `fireTime` | Khi scheduler thực sự fire | So với thời gian dự kiến |
| `nextFireTime` | Thời điểm chạy kế tiếp nếu có | Vận hành/lịch |
| `fireInstanceId` | Mã một lần fire | Trace/log, **không làm idempotency key** |
| `isRecovering()` | Lần chạy này thuộc cơ chế recovery | Điều tra/reconciliation |
| `getRefireCount()` | Số lần refire ngay | Không phải toàn bộ số retry của HTTP/broker |

Độ trễ scheduler có thể đo sơ bộ bằng `fireTime - scheduledFireTime`. Độ trễ này khác với thời gian thực hiện nghiệp vụ từ khi job bắt đầu đến khi checkpoint được commit.

### 5.2. Job mới không có nghĩa trạng thái nghiệp vụ mới

Mỗi lần Quartz tạo Job instance mới, nhưng các effect ở database/broker có thể tồn tại từ lần chạy trước. Một job đọc một cursor lưu trong field rồi mong lần chạy sau tiếp tục sẽ không đáng tin cậy.

Dùng bảng checkpoint hoặc metadata store có transaction, ví dụ `catalog_sync_checkpoint(source, last_version, updated_at)`, để tiếp tục chính xác sau restart hoặc recovery.

## 6. JobDataMap và dữ liệu đi kèm lịch

`JobDataMap` mang tham số cấu hình nhỏ cho JobDetail và Trigger:

~~~java
JobDetail detail = JobBuilder.newJob(SampleJob.class)
        .withIdentity("export", "reports")
        .usingJobData("reportType", "sales")
        .usingJobData("batchSize", 100)
        .build();
~~~

Đọc dữ liệu trong Job:

~~~java
String reportType =
        context.getMergedJobDataMap().getString("reportType");

int batchSize =
        context.getMergedJobDataMap().getInt("batchSize");
~~~

`getMergedJobDataMap()` gộp map ở JobDetail và Trigger. Nếu cùng key xuất hiện ở cả hai, map của trigger có thể ghi đè giá trị định nghĩa tại JobDetail cho lần fire đó.

**Giữ JobDataMap nhỏ và an toàn**:

- Nên chứa chuỗi, số, tên cấu hình, ID định danh ổn định.
- Không đặt password, token, Java `DataSource`, `EntityManager`, HTTP client hay object lớn.
- Với JDBC JobStore, cân nhắc khả năng serialize/deserialize và tương thích class giữa các node/deploy.
- Không dùng JobDataMap như cơ chế xử lý transaction hoặc business checkpoint.

### 6.1. @PersistJobDataAfterExecution

~~~java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.PersistJobDataAfterExecution;

@PersistJobDataAfterExecution
@DisallowConcurrentExecution
public class CountingJob implements org.quartz.Job {
    // execute(...) có thể cập nhật JobDetail.JobDataMap.
}
~~~

`@PersistJobDataAfterExecution` yêu cầu Quartz lưu JobDataMap cập nhật sau lần thực thi theo cơ chế JobStore. `@DisallowConcurrentExecution` giúp hạn chế race giữa các lần thực thi cùng JobKey.

Tuy nhiên, lưu JobDataMap của Quartz **không atomic với các thao tác SQL nghiệp vụ hoặc HTTP bên ngoài**. Nếu tiến độ đồng bộ cần phục hồi chính xác, ghi nó trong database nghiệp vụ với transaction/unique constraint phù hợp.

## 7. SimpleTrigger, CronTrigger và cách đọc lịch

### 7.1. SimpleTrigger

Ví dụ bắt đầu sau 30 giây, lặp lại bốn lần nữa (tổng tối đa năm lần fire theo lịch):

~~~java
import java.util.Date;
import org.quartz.SimpleScheduleBuilder;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

Trigger trigger = TriggerBuilder.newTrigger()
        .withIdentity("reconcileOnceSeries", "integration")
        .forJob(detail)
        .startAt(new Date(
                System.currentTimeMillis() + 30_000L))
        .withSchedule(
                SimpleScheduleBuilder.simpleSchedule()
                        .withIntervalInMinutes(5)
                        .withRepeatCount(4))
        .build();
~~~

`repeatCount = 4` nghĩa là **bốn lượt lặp sau lần đầu**, không phải tổng cộng bốn lượt. Đây là **lịch cố định**, không phải retry chỉ khi lần trước thất bại. `repeatForever()` tạo lịch lặp không giới hạn cho tới khi bị thay đổi.

### 7.2. CronTrigger

| Quartz cron | Ý nghĩa |
| --- | --- |
| `0 0/15 * * * ?` | Mỗi 15 phút |
| `0 0 2 * * ?` | 02:00 mỗi ngày |
| `0 0 9 ? * MON-FRI` | 09:00 thứ Hai đến thứ Sáu |
| `0 30 23 L * ?` | 23:30 ngày cuối cùng mỗi tháng |

Quartz cron có trường **giây**, khác cron Linux năm trường. Cấu hình múi giờ tường minh, đặc biệt khi ứng dụng chạy nhiều region. Ở khu vực có daylight saving time, giờ như 02:30 có thể không tồn tại hoặc lặp lại khi đổi giờ; phải kiểm thử lịch theo vùng giờ thực tế.

### 7.3. Lịch chạy chậm và tác vụ kéo dài

Nếu job chạy 20 phút nhưng trigger mỗi 15 phút:

- Không có kiểm soát concurrency, các lượt chạy có thể chồng nhau.
- Với `@DisallowConcurrentExecution`, Quartz tránh chạy đồng thời cùng JobKey nhưng lịch có thể đến trễ.
- Nếu thread pool hết chỗ, trigger khác cũng chờ và có thể thành misfire.
- Job chạy lâu phải có timeout, checkpoint và khả năng dừng có kiểm soát.

Đừng dùng pool size lớn để che một adapter HTTP/SQL bị treo.

## 8. Misfire: khi Quartz bỏ lỡ thời điểm dự kiến

**Misfire** là trường hợp một trigger đến hạn nhưng không được fire kịp trong ngưỡng mà Quartz xác định. Nguyên nhân có thể là scheduler downtime, standby, nghẽn thread pool, JobStore chậm hoặc cluster failover.

Chính sách misfire của `CronTrigger`:

| API | Ý nghĩa khái quát | Khi nào phù hợp |
| --- | --- | --- |
| `withMisfireHandlingInstructionDoNothing()` | Bỏ các lần đã lỡ, chờ lịch kế tiếp | Đồng bộ định kỳ chỉ cần trạng thái mới |
| `withMisfireHandlingInstructionFireAndProceed()` | Fire một lượt bù sớm nhất có thể rồi tiếp tục lịch | Cần chạy một lượt khi dịch vụ hoạt động lại |
| `withMisfireHandlingInstructionIgnoreMisfires()` | Không dùng xử lý misfire thông thường | Chỉ khi đã kiểm soát nguy cơ dồn việc |

`SimpleTrigger` có những lựa chọn khác, chẳng hạn `FireNow`, `NextWithRemainingCount` hay `NowWithExistingCount`, làm thay đổi thời điểm và số lượt lặp còn lại. Không chuyển máy móc chính sách từ CronTrigger sang SimpleTrigger.

**Ví dụ:** job tạo báo cáo ngày lúc 02:00, nhưng scheduler ngừng 01:50–04:00. Chính sách “DoNothing” có thể bỏ qua kỳ báo cáo đó. “FireAndProceed” có thể kích hoạt một lần khi khôi phục, nhưng code chỉ gọi `LocalDate.now()` có thể lập báo cáo sai kỳ. Nếu bắt buộc xử lý mọi ngày, hãy ghi các kỳ cần xử lý vào bảng work/checkpoint rồi job quét những kỳ chưa hoàn tất.

### Misfire khác lỗi Job

Misfire nói về **lịch không được kích hoạt đúng hạn**. Exception trong `execute(...)` nói về **nội dung một lần chạy**. Một Job có thể fire đúng hạn rồi thất bại; cũng có thể fire muộn nhưng thực thi thành công. Dashboard và recovery policy nên tách hai loại sự kiện.

## 9. Concurrency và @DisallowConcurrentExecution

~~~java
import org.quartz.DisallowConcurrentExecution;

@DisallowConcurrentExecution
public class CatalogSyncJob implements org.quartz.Job {
    // execute(...)
}
~~~

Annotation ngăn những lần chạy **cùng JobDetail/JobKey** thực thi đồng thời theo cơ chế Quartz. Nhưng:

- Hai JobDetail khác JobKey cùng Java class vẫn có thể cùng chạy.
- Hai Quartz scheduler độc lập dùng JobStore riêng không có khóa chung.
- HTTP endpoint khác hoặc broker consumer khác có thể vẫn tác động cùng dữ liệu.
- Recovery/replay sau crash có thể thực hiện lại phần nghiệp vụ đã xảy ra.
- Nếu Job tự tạo tác vụ con bất đồng bộ rồi trả ngay, Quartz có thể coi Job hoàn thành khi tác vụ con còn chạy.

Với nghiệp vụ quan trọng, dùng **unique constraint, optimistic locking, claim/lease hoặc transaction** theo business key; `@DisallowConcurrentExecution` chỉ kiểm soát đồng thời ở tầng scheduler.

## 10. JobExecutionException và chính sách retry

Nếu Job ném `JobExecutionException`, Quartz nhận diện lần thực thi thất bại và thông báo cho listener. **Exception không tự biến thành một retry có exponential backoff.**

~~~java
@Override
public void execute(JobExecutionContext context)
        throws JobExecutionException {
    try {
        useCase.synchronizeNextBatch();
    } catch (RuntimeException exception) {
        throw new JobExecutionException(
                "Đồng bộ Catalog không thành công", exception);
    }
}
~~~

`JobExecutionException` hỗ trợ chỉ thị refire ngay hoặc unschedule trong một số trường hợp. Không bật `refireImmediately` bừa bãi: nếu lỗi mạng kéo dài, nó có thể gây vòng lặp nhanh, chiếm thread và làm lặp side effect.

| Lỗi | Có thể thử lại? | Lưu ý |
| --- | --- | --- |
| HTTP 503, kết nối tạm thời mất | Thường có, nhưng giới hạn | Backoff/jitter, circuit breaker |
| Password sai, quyền bị từ chối | Không retry vô hạn | Cảnh báo và sửa cấu hình |
| Schema/JSON không hợp lệ | Cần sửa hợp đồng | DLQ hoặc quarantine tùy luồng |
| SQL deadlock/serialization conflict | Có thể retry transaction có kiểm soát | Idempotency và số lần thử hữu hạn |
| Timeout sau POST ghi dữ liệu | Kết quả có thể không xác định | Truy vấn trạng thái bằng idempotency key |
| DB đã commit nhưng publish broker lỗi | Không thể rollback DB qua Quartz | Transactional outbox |

**Ngân sách retry:** nếu Job chạy lại mỗi 15 phút, HTTP client retry 3 lần, và broker tiếp tục redeliver, tổng request có thể tăng quá mức. Cần quy định số lượt thử toàn luồng, thời gian tối đa, điểm phục hồi và cảnh báo.

## 11. RAMJobStore, JDBC JobStore và sự bền vững

### 11.1. RAMJobStore

- Dễ phát triển, không cần bảng Quartz.
- JobDetail/Trigger state chỉ trong bộ nhớ tiến trình.
- Lịch tạo động không được giữ qua restart.
- Mỗi replica có scheduler riêng; có thể kích hoạt cùng logic trên nhiều node.

Phù hợp cho demo, test hoặc tác vụ không cần lịch bền vững/cluster.

### 11.2. JDBC JobStore

Cấu hình Boot kết nối Quartz tới SQL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

~~~yaml
spring:
  datasource:
    url: ${QUARTZ_DB_URL}
    username: ${QUARTZ_DB_USERNAME}
    password: ${QUARTZ_DB_PASSWORD}

  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    overwrite-existing-jobs: false
    properties:
      org.quartz.scheduler.instanceName: integrationScheduler
      org.quartz.threadPool.threadCount: 8
~~~

Trong ví dụ production, schema Quartz phải được tạo **bằng migration/provisioning có kiểm soát trước khi app chạy**. `initialize-schema: never` ngăn Boot tự chạy script khởi tạo. Script Quartz tiêu chuẩn dùng khi `initialize-schema: always` có thể **drop bảng đang tồn tại**, nên bật `always` trên database có lịch cần bảo toàn là rất rủi ro.

JDBC JobStore lưu metadata của scheduler, như bảng `QRTZ_JOB_DETAILS`, `QRTZ_TRIGGERS`, `QRTZ_CRON_TRIGGERS`. Nó **không lưu thay kết quả xử lý nghiệp vụ** nếu use case không ghi checkpoint.

### 11.3. Overwrite-existing-jobs và deploy phiên bản mới

Lịch đã lưu trong JDBC không mặc định đổi theo mọi sửa đổi trong bean Java khi deploy. Thuộc tính `spring.quartz.overwrite-existing-jobs` ảnh hưởng cách Boot xử lý định nghĩa đã tồn tại.

- Nếu **code/deploy** là nguồn chuẩn của lịch, có thể chọn overwrite và quản lý version lịch rõ ràng.
- Nếu operator có thể sửa lịch qua API quản trị, overwrite mỗi lần khởi động có thể xóa thay đổi mà operator mong muốn.
- Đổi JobKey/TriggerKey có thể tạo **lịch mới còn lịch cũ vẫn tồn tại**; cần migration hoặc cleanup có kiểm soát.

Không vừa để code và một database UI cùng quản lý schedule mà thiếu quy tắc phân quyền sở hữu.

## 12. Clustering và recovery khi chạy nhiều replica

Hai Spring Boot replica cấu hình RAMJobStore riêng có thể chạy hai Quartz scheduler độc lập. Nếu cần một cluster scheduler thực sự, các node phải sử dụng **JDBC JobStore chung** và bật clustering với nhận diện instance riêng.

~~~yaml
spring:
  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    properties:
      org.quartz.scheduler.instanceName: integrationScheduler
      org.quartz.scheduler.instanceId: AUTO
      org.quartz.jobStore.isClustered: true
      org.quartz.jobStore.clusterCheckinInterval: 10000
      org.quartz.threadPool.threadCount: 8
~~~

Điều kiện quan trọng:

1. Các node trong cùng cluster dùng bảng Quartz và scheduler name phù hợp.
2. Instance ID phải khác nhau; `AUTO` để Quartz cấp.
3. Đồng hồ hệ thống đồng bộ đủ tốt, tránh lệch giờ đáng kể.
4. Database và connection pool đủ năng lực, schema/locking đúng vendor.
5. Mọi node có Job class/version tương thích với metadata đang lưu.
6. Node ngoài cluster không truy cập cùng bảng Quartz với cấu hình không tương thích.

**Clustering phân phối trigger, không bảo đảm side effect đúng một lần.** Khi node chết giữa lúc gọi HTTP/DB, Quartz có thể thực thi lại nhưng không biết chính xác hệ thống ngoài đã nhận thay đổi hay chưa.

### 12.1. requestRecovery(true)

~~~java
JobDetail detail = JobBuilder.newJob(CatalogSyncJob.class)
        .withIdentity("catalogSync", "integration")
        .requestRecovery(true)
        .storeDurably()
        .build();
~~~

Với JobStore/recovery phù hợp, `requestRecovery(true)` báo Quartz rằng một job đang chạy trên scheduler instance bị lỗi có thể cần được thực thi lại. Nó không tiếp tục ở đúng instruction Java trước khi crash, mà **bắt đầu lại một execution**. `JobExecutionContext.isRecovering()` giúp nhận biết trường hợp này.

Vì vậy cần:

- Đọc checkpoint đã commit.
- Không lặp thay đổi nghiệp vụ dựa trên eventId/version đã xử lý.
- Đưa outbox vào cùng transaction nếu cần phát message sau SQL.
- Kiểm tra tình huống “DB đã commit nhưng Quartz không ghi nhận job hoàn thành”.

## 13. Transaction và idempotency cho scheduled integration job

Xét luồng đồng bộ qua HTTP → DB → broker:

~~~mermaid
flowchart LR
    A["CronTrigger"] --> B["CatalogSyncJob"]
    B --> C["CatalogSyncUseCase"]
    C --> D["Catalog HTTP API"]
    C --> E["SQL transaction"]
    E --> F["Update projection"]
    E --> G["Update checkpoint"]
    E --> H["Insert outbox"]
    H --> I["Outbox relay"]
    I --> J["Broker"]
~~~

Một mẫu thực thi an toàn:

1. Đọc checkpoint được lưu bền vững, không lấy từ field Job.
2. Tải batch thay đổi bằng HTTP client có timeout.
3. Validate schema/version, xác định business key và quy tắc duplicate.
4. Ghi dữ liệu, checkpoint và outbox **trong cùng transaction SQL** nếu cùng resource.
5. Khi commit thành công, lần sau bắt đầu từ checkpoint mới.
6. Publisher phát outbox; consumer downstream dùng idempotency vì sự kiện có thể được gửi lại.

Nếu checkpoint ghi **trước** thay đổi dữ liệu và transaction không cùng nhau, crash có thể bỏ qua bản ghi chưa thực sự xử lý. Nếu thay đổi dữ liệu xảy ra trước nhưng checkpoint chưa ghi, batch có thể lặp; cần thao tác idempotent.

**Quartz transaction khác transaction nghiệp vụ.** JDBC JobStore có transaction riêng để quản lý lịch/trigger. Spring `@Transactional` trên service không tự gom HTTP request, broker publish và metadata Quartz thành một ACID transaction.

### 13.1. Trường hợp không xác định kết quả

HTTP POST timeout sau khi gửi chưa chứng minh đối tác chưa nhận. Retry phải kèm idempotency key được đối tác hỗ trợ hoặc cơ chế đối soát. Tương tự, mất kết nối đúng lúc DB commit cần tra cứu lại theo business key/version, không lặp blindly.

### 13.2. Đừng giữ transaction qua HTTP call chậm

Không nên mở transaction DB dài rồi chờ hàng phút HTTP API. Cách làm đó có thể giữ connection/lock làm pool cạn. Tách bước tải, validate và ghi mỗi batch; thiết kế check-and-update checkpoint nguyên tử để vẫn chống cạnh tranh.

## 14. Điều khiển scheduler khi ứng dụng đang chạy

Một Spring service có thể inject `Scheduler` để yêu cầu chạy thêm, pause/resume và tra cứu metadata:

~~~java
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.SchedulerException;
import org.springframework.stereotype.Service;

@Service
public class QuartzAdminService {

    private final Scheduler scheduler;

    public QuartzAdminService(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    public void triggerCatalog() throws SchedulerException {
        scheduler.triggerJob(
                JobKey.jobKey("catalogSync", "integration"));
    }

    public void pauseCatalog() throws SchedulerException {
        scheduler.pauseJob(
                JobKey.jobKey("catalogSync", "integration"));
    }

    public void resumeCatalog() throws SchedulerException {
        scheduler.resumeJob(
                JobKey.jobKey("catalogSync", "integration"));
    }
}
~~~

Đây là service quản trị nội bộ; chưa có controller HTTP. Khi đưa ra API, phải xác thực quyền quản trị, audit và giới hạn tần suất run thủ công.

**Pause không có nghĩa kill job đang chạy.** `pauseJob(...)` ngăn những lần fire tương lai theo điều kiện scheduler; execution đã bắt đầu có thể tiếp tục. Nếu muốn dừng job dài, thiết kế cancellation protocol, timeouts và/hoặc `InterruptableJob` khi phù hợp. Không được giả định Quartz có thể hủy an toàn JDBC transaction hoặc HTTP call tùy ý.

Với lịch động, `checkExists(...)` rồi `scheduleJob(...)` không atomic giữa nhiều tiến trình quản trị. Cần xử lý `ObjectAlreadyExistsException` hoặc cơ chế cập nhật có lock; dùng `rescheduleJob(...)` để chỉnh trigger hiện có theo identity ổn định.

## 15. Quan sát trạng thái scheduler và kết quả nghiệp vụ

Spring Boot Actuator có Quartz endpoint trên những version hỗ trợ, ví dụ `/actuator/quartz` để xem job/trigger metadata khi endpoint được bật và có quyền truy cập. Endpoint này **không bảo đảm** luồng nghiệp vụ đã commit, gửi message thành công hoặc xử lý hết backlog.

Theo dõi hai lớp:

| Quartz/scheduler | Luồng nghiệp vụ |
| --- | --- |
| Trigger nextFireTime, state | Last successful checkpoint |
| Scheduled vs actual fire lag | Thời gian dữ liệu nguồn → projection |
| Job duration, exception count | Số record thành công/lỗi |
| Running job count, pool saturation | Outbox queue age, backlog |
| Misfire count, recovery events | Duplicate/retry/DLQ count |
| Cluster check-in | Downstream HTTP/DB error/timeout |

Quartz có `JobListener` và `TriggerListener` để quan sát lifecycle và misfire. Ví dụ:

~~~java
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.quartz.listeners.JobListenerSupport;

public class SyncJobListener extends JobListenerSupport {

    @Override
    public String getName() {
        return "catalog-sync-listener";
    }

    @Override
    public void jobWasExecuted(
            JobExecutionContext context,
            JobExecutionException exception) {
        // Ghi metric/log outcome theo JobKey và exception type.
        // Cần đăng ký listener với Scheduler.
    }
}
~~~

Đoạn trên chỉ khai báo listener; ứng dụng cần đăng ký nó thông qua Scheduler hoặc `SchedulerFactoryBeanCustomizer` theo cấu hình.

Với Micrometer Observation, đặt tên như `integration.catalog.sync`, nhãn có tập giá trị nhỏ (`job=catalogSync`, `outcome=success/failure`). Không dùng `fireInstanceId`, `orderId`, `eventId` làm metric labels có cardinality cao; ghi vào audit/log/trace có chính sách bảo vệ khi cần.

Trace của một Job chạy theo lịch thường khởi đầu trong Quartz worker thread. Không giả định trace context từ một HTTP request đã kết thúc tự động đi theo trigger đến lần chạy sau.

## 16. Kiểm thử JobDetail, Trigger và execution

Nên tách kiểm thử theo lớp:

- **Unit test use case:** fake HTTP/DB/broker để kiểm chứng idempotency, checkpoint, phân loại lỗi, giới hạn retry.
- **Spring Boot integration test:** xác minh bean JobDetail, Trigger, Scheduler, timezone và autowiring.
- **Quartz execution test:** dùng trigger/latch và fake service, đo số lần chạy, non-concurrent, thất bại.
- **Persistence/recovery test:** dùng database thật hoặc Testcontainers, kiểm tra lịch sau restart và duplicate behavior.

### 16.1. Test đăng ký job mà chưa chạy lịch

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.quartz.CronTrigger;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.TriggerKey;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
        properties = "spring.quartz.auto-startup=false")
class QuartzRegistrationTest {

    @Autowired
    Scheduler scheduler;

    @Test
    void catalogCronIsRegistered() throws Exception {
        var jobKey =
                JobKey.jobKey("catalogSync", "integration");
        var triggerKey =
                TriggerKey.triggerKey(
                        "catalogSyncCron", "integration");

        assertNotNull(scheduler.getJobDetail(jobKey));
        var trigger = scheduler.getTrigger(triggerKey);

        assertInstanceOf(CronTrigger.class, trigger);
        assertEquals("0 0/15 * * * ?",
                ((CronTrigger) trigger).getCronExpression());
    }
}
~~~

Test này chỉ kiểm tra metadata, chưa chứng minh `execute()` chạy. Khi dùng JDBC store, phải chạy trên database test riêng có Quartz tables hoặc Testcontainers.

### 16.2. Kiểm thử cron theo mốc thời gian cố định

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.TimeZone;
import org.quartz.CronExpression;

CronExpression cron =
        new CronExpression("0 0/15 * * * ?");
cron.setTimeZone(
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));

Date next = cron.getNextValidTimeAfter(
        Date.from(
                Instant.parse("2026-01-01T00:01:00Z")));

// 00:01Z = 07:01 ở Việt Nam; lần kế tiếp 07:15.
assertEquals(
        Instant.parse("2026-01-01T00:15:00Z"),
        next.toInstant());
~~~

Ví dụ là phần assertion của test (cần import JUnit và fixture tương ứng). Dùng mốc cố định để kiểm chứng logic cron, không `Thread.sleep` chờ 15 phút. Với timezone có DST, bổ sung test ngày đổi giờ.

### 16.3. Test lần chạy thật và recovery

- Trong context test, thay `CatalogSyncUseCase` bằng fake có bộ đếm.
- Bật scheduler cho test cụ thể và kích hoạt `triggerJob(...)`.
- Chờ bằng latch/event có timeout và assert số lượt gọi đúng, tránh sleep tùy tiện.
- Inject exception từ use case và xác minh listener ghi đúng lỗi, không tự retry vô hạn.
- Với `@DisallowConcurrentExecution`, dùng hai trigger cùng JobKey và theo dõi số lần song song cực đại.
- Với JDBC JobStore, restart scheduler test và xác minh định nghĩa lịch còn tồn tại.
- Test crash/recovery phải dựa trên DB/business checkpoint, không chỉ assert trạng thái của Quartz tables.

Không trỏ test scheduler vào database production hoặc endpoint HTTP thật. Đặc biệt, đừng bật `spring.quartz.jdbc.initialize-schema=always` trên DB có dữ liệu cần giữ.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không có `Scheduler` bean | Thiếu starter hoặc auto-configuration bị loại trừ | Kiểm tra classpath/điều kiện Boot |
| JobDetail có bean nhưng Job không chạy | Scheduler chưa start, trigger pause, không có thread | Kiểm tra `auto-startup` và trigger state |
| Job không được inject service | JobFactory tự dựng không autowire | Kiểm tra JobFactory/cấu hình Spring |
| Job chạy nhiều lần trên 3 replicas | RAMJobStore độc lập trên từng node | JDBC clustering hoặc locking nghiệp vụ |
| Job chạy trùng dù có annotation | Khác JobKey, scheduler khác hoặc external caller | Unique constraint và idempotency |
| Sau restart lịch bị mất | RAMJobStore hoặc dynamic jobs không đăng ký lại | JDBC JobStore khi cần persistence |
| Không chạy đúng giờ địa phương | Sai cron hoặc timezone/DST | Kiểm tra biểu thức và nextFireTime |
| Chạy dồn sau downtime | Misfire policy không phù hợp | Chọn skip, fire-once hoặc catch-up theo checkpoint |
| Exception nhưng không thấy retry | Quartz không retry backoff mặc định | Thiết kế retry budget rõ ràng |
| Job thất bại rồi mất tiến độ | Checkpoint chỉ ở field/JobDataMap | Checkpoint DB cùng transaction |
| Sửa lịch trong code không có hiệu lực | JDBC definition cũ còn tồn tại | Xem `overwrite-existing-jobs` và migration |
| Job pause nhưng vẫn tiếp tục | Execution hiện tại không bị kill | Thiết kế cancellation/timeout |
| Quartz schema bị mất | SQL init script drop bảng | Dùng migration và `initialize-schema: never` |
| Quartz báo job success nhưng broker không nhận | Side effect ngoài Quartz chưa được commit | Outbox/ack/observability nghiệp vụ |

## 18. Checklist triển khai Quartz integration job

- [ ] Job chỉ gọi use case; HTTP/SQL/cache/broker logic nằm trong adapter/service phù hợp.
- [ ] JobKey và TriggerKey duy nhất, ổn định qua deploy.
- [ ] Chọn Simple/Cron trigger đúng nhu cầu và timezone tường minh.
- [ ] Có misfire policy rõ: bỏ lỡ, bù một lượt hay xử lý bù mọi kỳ từ checkpoint.
- [ ] Kiểm soát concurrency theo JobKey và qua các nguồn kích hoạt bên ngoài.
- [ ] Chọn RAMJobStore cho tác vụ tạm thời hoặc JDBC JobStore cho lịch bền/cluster.
- [ ] Schema Quartz được migration an toàn, phân biệt metadata scheduler và data nghiệp vụ.
- [ ] Có transaction local, idempotency, checkpoint và outbox khi cần.
- [ ] Retry/timeout có giới hạn; lỗi vĩnh viễn có cảnh báo và cách khắc phục.
- [ ] Theo dõi scheduled time, fire time, job outcome và business completion riêng.
- [ ] Kiểm thử registration, execution, restart/recovery, misfire và duplicate.
- [ ] Bảo vệ JobDataMap, admin API, Actuator và logs/metrics khỏi lộ bí mật.

**Ghi nhớ:** `Job` xác định code chạy; `JobDetail` định danh và cấu hình công việc; `Trigger` mô tả thời điểm chạy; `Scheduler` điều phối các lần fire và vòng đời. Quartz có thể lưu lịch và phối hợp nhiều node qua JDBC JobStore, nhưng độ tin cậy của tích hợp còn phụ thuộc vào **hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát**.

## Tài liệu tham khảo

- [Spring Boot — Quartz Scheduler](https://docs.spring.io/spring-boot/reference/io/quartz.html): auto-configuration, JobDetail/Trigger, JDBC store, startup và overwrite policy.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Scheduled` và tích hợp Quartz.
- [Quartz Scheduler — Tutorials](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/): Job, JobDetail, Trigger, Cron, misfire, JobStore và listeners.
- [Quartz — JobDetail API](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/JobDetail.html): identity, durability, recovery và JobDataMap.
- [Quartz — CronTrigger API](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/CronTrigger.html): cron scheduling và misfire.
- [Quartz — Scheduler API](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/Scheduler.html): schedule, trigger, pause, resume và lifecycle.
