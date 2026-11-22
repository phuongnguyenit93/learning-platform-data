# `spring.quartz.*` và `SchedulerFactoryBeanCustomizer`

Trong Spring Boot Integration, nhiều tác vụ tích hợp cần chạy theo lịch: đối soát giao dịch với đối tác mỗi 5 phút, quét bản ghi trong outbox, đồng bộ dữ liệu từ hệ thống ngoài hoặc dọn trạng thái xử lý quá hạn. **Quartz** cung cấp `Job` (việc cần làm), `JobDetail` (định danh và cấu hình job), `Trigger` (thời điểm chạy) và `Scheduler` (bộ điều phối). Spring Boot kết nối các thành phần này bằng `SchedulerFactoryBean`.

Bài này tập trung vào hai điểm điều khiển bộ lập lịch: **thuộc tính `spring.quartz.*`** cho cấu hình khai báo và **`SchedulerFactoryBeanCustomizer`** cho trường hợp phải can thiệp trực tiếp vào `SchedulerFactoryBean`. Các ví dụ đặt trong bối cảnh tích hợp qua API, cơ sở dữ liệu và luồng xử lý có thể được triển khai nhiều instance.

## 1. Spring Boot tạo và cấu hình Quartz như thế nào?

Khi ứng dụng có dependency `spring-boot-starter-quartz`, Spring Boot tự cấu hình một `Scheduler` thông qua `SchedulerFactoryBean`. Các bean thuộc kiểu `JobDetail`, `Trigger` và `org.quartz.Calendar` được phát hiện và đăng ký với scheduler. Không cần tự tạo một `SchedulerFactoryBean` chỉ để khai báo lịch đơn giản.

~~~text
application.yml / biến môi trường
            |
            v
    spring.quartz.* ----------------------+
            |                             |
            v                             v
 QuartzProperties                SchedulerFactoryBeanCustomizer
            |                             |
            +----------> SchedulerFactoryBean
                              |
                    JobDetail + Trigger
                              |
                              v
                          Scheduler
                              |
                         chạy Quartz Job
                              |
                 HTTP / Database / Outbox / Broker
~~~

Một phân biệt quan trọng:

| Thành phần | Trả lời câu hỏi | Cấu hình ở đâu? |
| --- | --- | --- |
| `Job` / `JobDetail` | Chạy nghiệp vụ nào, với định danh gì? | Java bean hoặc đăng ký với `Scheduler` |
| `Trigger` | Chạy lúc nào, theo cron hay khoảng lặp? | Java bean / Quartz API |
| `spring.quartz.*` | Scheduler khởi động ra sao, dùng RAM hay JDBC, ghi đè lịch đã lưu không? | `application.yml`, `application.properties`, biến môi trường |
| `spring.quartz.properties.*` | Các thuộc tính gốc của Quartz như thread pool, cluster, misfire threshold là gì? | Configuration của Spring Boot |
| `SchedulerFactoryBeanCustomizer` | Cần điều chỉnh trực tiếp đặc tính nào của factory, ví dụ executor hoặc listener? | Bean Java |

`spring.quartz.*` cấu hình **scheduler**; nó không thay thế định nghĩa `Trigger`, cron expression riêng của từng job hay cơ chế retry/idempotency của nghiệp vụ.

## 2. Các thuộc tính `spring.quartz.*` quan trọng

| Thuộc tính | Mặc định thường gặp | Ý nghĩa và lưu ý |
| --- | --- | --- |
| `spring.quartz.scheduler-name` | `quartzScheduler` | Tên scheduler; cần thống nhất trong các node cùng cụm Quartz |
| `spring.quartz.job-store-type` | `memory` | `memory` lưu lịch trong RAM; `jdbc` lưu `JobDetail`/`Trigger` vào CSDL qua Quartz tables |
| `spring.quartz.auto-startup` | `true` | Tự khởi chạy scheduler sau khi khởi tạo |
| `spring.quartz.startup-delay` | `0s` | Hoãn bắt đầu scheduler sau khởi tạo; không thay thế kiểm tra hệ thống phụ thuộc đã sẵn sàng |
| `spring.quartz.wait-for-jobs-to-complete-on-shutdown` | `false` | Đợi job đang chạy hoàn thành trong lúc tắt scheduler; cần cân nhắc giới hạn thời gian shutdown của môi trường triển khai |
| `spring.quartz.overwrite-existing-jobs` | `false` | Có cho phép định nghĩa job/trigger do ứng dụng cấu hình ghi đè bản đã tồn tại trong JDBC job store không |
| `spring.quartz.jdbc.initialize-schema` | `embedded` | Điều khiển việc chạy script tạo bảng Quartz: `embedded`, `always`, `never` |
| `spring.quartz.jdbc.schema` | Script Quartz theo nền tảng | Đường dẫn script SQL tạo schema riêng, hữu ích khi phải điều chỉnh DDL |
| `spring.quartz.jdbc.platform` | Tự phát hiện | Chọn tên nền tảng cho placeholder `@@platform@@` trong đường dẫn schema |
| `spring.quartz.jdbc.continue-on-error` | `true` | Có tiếp tục khi script khởi tạo schema gặp lỗi; không nên dùng nó để che lỗi migration |
| `spring.quartz.properties.*` | Không có map bổ sung | Truyền các khóa gốc `org.quartz.*` cho Quartz; kiểm tra đúng tên và đơn vị của từng khóa |

Giá trị mặc định và các key hỗ trợ có thể thay đổi giữa phiên bản Spring Boot, nên khi nâng cấp cần đối chiếu metadata của phiên bản thực tế. Không có `spring.quartz.cron` chung cho mọi job: lịch của từng tác vụ thuộc về `Trigger`.

### 2.1. Chạy một instance bằng bộ nhớ

~~~yaml
spring:
  quartz:
    scheduler-name: integration-scheduler
    job-store-type: memory
    auto-startup: true
    startup-delay: 5s
    wait-for-jobs-to-complete-on-shutdown: true
    properties:
      "[org.quartz.threadPool.threadCount]": "6"
      "[org.quartz.jobStore.misfireThreshold]": "60000"
~~~

Đây là cấu hình phù hợp cho môi trường phát triển hoặc lịch có thể tạo lại hoàn toàn khi khởi động. Sau restart, job store trong RAM mất trạng thái cũ; Spring Boot đăng ký lại các `JobDetail` và `Trigger` được định nghĩa dưới dạng bean. `startup-delay: 5s` chỉ hoãn scheduler, không đảm bảo API đối tác hay broker đã sẵn sàng.

Trong YAML, phần `properties` là map chuyển tiếp tới Quartz. Cách viết key dạng `"[org.quartz.threadPool.threadCount]"` giúp giữ nguyên đầy đủ tên khóa khi Spring Boot binding. Giá trị `60000` của `misfireThreshold` là **mili giây** (60 giây), khác với cú pháp `5s` của `startup-delay`.

### 2.2. Chạy bền vững với JDBC JobStore

~~~yaml
spring:
  quartz:
    scheduler-name: integration-scheduler
    job-store-type: jdbc
    auto-startup: true
    overwrite-existing-jobs: false
    wait-for-jobs-to-complete-on-shutdown: true
    jdbc:
      initialize-schema: never
    properties:
      "[org.quartz.scheduler.instanceId]": AUTO
      "[org.quartz.jobStore.isClustered]": "true"
      "[org.quartz.jobStore.clusterCheckinInterval]": "20000"
      "[org.quartz.jobStore.misfireThreshold]": "60000"
      "[org.quartz.threadPool.threadCount]": "8"
~~~

Để cấu hình này hoạt động, ứng dụng phải có `DataSource` kết nối tới CSDL chứa các bảng `QRTZ_*` đã được tạo đúng phiên bản/dialect. Các node cùng cluster cần trỏ tới **cùng bộ bảng Quartz**, sử dụng cấu hình cluster tương thích và có `instanceId` khác nhau; giá trị `AUTO` để Quartz tự tạo định danh instance. Tham số `isClustered=true` chỉ nên dùng cùng JDBC job store, không dành cho `memory`. Nếu chỉ chạy một instance độc lập, bỏ cấu hình cluster thay vì sao chép máy móc.

**Cảnh báo vận hành:** `spring.quartz.jdbc.initialize-schema=always` có thể chạy script chuẩn chứa lệnh xóa và tạo lại bảng, làm mất trigger/job đã lưu mỗi lần khởi động. Với môi trường cần bảo toàn lịch, hãy quản lý DDL Quartz bằng migration/DBA và đặt `initialize-schema: never`. Mặc định `embedded` không có nghĩa là sẽ tự tạo bảng trong mọi CSDL production.

Nếu Quartz phải dùng database hoặc transaction manager riêng, có thể đánh dấu bean tương ứng bằng `@QuartzDataSource` hoặc `@QuartzTransactionManager`. Spring Boot sẽ sử dụng `@QuartzDataSource` cho cả scheduler và phần khởi tạo schema. Dùng cơ chế này sẽ nhất quán hơn việc tự gọi `factory.setDataSource(...)` trong customizer. Các annotation thuộc package Quartz auto-configuration của đúng phiên bản Boot.

### 2.3. Phân biệt cấu hình Boot và cấu hình Quartz gốc

~~~properties
# Các khóa do Spring Boot hiểu và chuyển thành thuộc tính của factory
spring.quartz.scheduler-name=integration-scheduler
spring.quartz.job-store-type=jdbc
spring.quartz.jdbc.initialize-schema=never

# Các khóa Quartz gốc được chuyển vào Properties của scheduler
spring.quartz.properties.org.quartz.scheduler.instanceId=AUTO
spring.quartz.properties.org.quartz.jobStore.isClustered=true
spring.quartz.properties.org.quartz.threadPool.threadCount=8
~~~

Không nên đồng thời thiết lập một ý nghĩa ở hai tầng rồi đoán giá trị nào sẽ thắng. Ví dụ, `scheduler-name` đã điều khiển tên scheduler thì không cần đặt thêm `org.quartz.scheduler.instanceName`. Nếu Spring cung cấp `DataSource` cho JDBC job store, không tự gán `org.quartz.jobStore.class=org.quartz.impl.jdbcjobstore.JobStoreTX`: điều đó có thể xung đột với `LocalDataSourceJobStore` mà Spring quản lý.

## 3. `SchedulerFactoryBeanCustomizer` giải quyết vấn đề gì?

`SchedulerFactoryBeanCustomizer` là một functional interface có phương thức:

~~~java
void customize(SchedulerFactoryBean schedulerFactoryBean);
~~~

Spring Boot gọi các bean customizer khi cấu hình `SchedulerFactoryBean`. Nó phù hợp khi cần API setter của factory mà thuộc tính `spring.quartz.*` không biểu đạt trực tiếp được, ví dụ:

- Gắn một `Executor` riêng do Spring quản lý qua `setTaskExecutor(...)`.
- Đăng ký `JobListener`, `TriggerListener` hoặc `SchedulerListener` cho quan sát và kiểm toán.
- Cấu hình `JobFactory` chuyên biệt khi ứng dụng có yêu cầu khởi tạo/inject job riêng.
- Điều chỉnh `SchedulerContext` cho một đối tượng dùng chung có chủ đích.

Đây vẫn là bước cấu hình **factory trước khi scheduler chạy**, khác với việc inject `org.quartz.Scheduler` rồi gọi API điều khiển job/trigger tại thời gian chạy.

### 3.1. Ví dụ: dùng một executor riêng cho Quartz

Mặc định, một bean `Executor` thông thường của Spring Boot **không tự động** trở thành executor của Quartz. Nếu muốn sử dụng `ThreadPoolTaskExecutor` do Spring quản lý, có thể tạo customizer:

~~~java
import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.quartz.SchedulerFactoryBeanCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class QuartzExecutorConfig {

    @Bean("integrationQuartzExecutor")
    ThreadPoolTaskExecutor integrationQuartzExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(40);
        executor.setThreadNamePrefix("quartz-integration-");
        return executor; // Spring quản lý khởi tạo và shutdown của bean.
    }

    @Bean
    SchedulerFactoryBeanCustomizer quartzExecutorCustomizer(
            @Qualifier("integrationQuartzExecutor") Executor executor) {
        return factory -> factory.setTaskExecutor(executor);
    }
}
~~~

> **Tương thích phiên bản:** import `org.springframework.boot.autoconfigure.quartz.SchedulerFactoryBeanCustomizer` ở trên dành cho Spring Boot **3.x**. Với Spring Boot **4.x**, đổi thành `org.springframework.boot.quartz.autoconfigure.SchedulerFactoryBeanCustomizer`; tên interface và ý tưởng sử dụng giữ nguyên. Kiểm tra package theo dependency thực tế khi sao chép ví dụ.

`setTaskExecutor` yêu cầu Spring/Quartz sử dụng executor đó làm backend thực thi job. Khi chọn cách này, hãy tính toán riêng kích thước pool, hàng đợi, tải API/CSDL và chính sách từ chối của executor. Không đồng thời cố chỉnh số thread bằng `org.quartz.threadPool.threadCount` rồi mặc định rằng nó điều khiển `ThreadPoolTaskExecutor` của Spring. Nếu không có nhu cầu đặc biệt về executor, cấu hình Quartz `SimpleThreadPool` bằng `spring.quartz.properties.org.quartz.threadPool.threadCount` thường đơn giản hơn.

### 3.2. Ví dụ: đăng ký listener theo dõi việc chạy job

Giả sử ứng dụng có một bean triển khai `org.quartz.JobListener` tên `IntegrationJobListener`, có thể đăng ký nó với mọi job:

~~~java
@Bean
SchedulerFactoryBeanCustomizer integrationJobListenerCustomizer(
        IntegrationJobListener listener) {
    return factory -> factory.setGlobalJobListeners(listener);
}
~~~

Đây là đoạn đặt trong lớp `@Configuration` đã import `SchedulerFactoryBeanCustomizer` và `@Bean` ở ví dụ trước. Listener có thể ghi log `JobKey`, `fireInstanceId`, thời gian chạy, kết quả và exception; nên gắn correlation ID của lần xử lý với hệ thống quan sát. Nếu có nhiều listener, truyền chúng cùng một lần gọi `setGlobalJobListeners(...)` để tránh customizer khác thiết lập lại danh sách. Đừng nhét thông tin nhạy cảm, connection hoặc dữ liệu nghiệp vụ lớn vào log.

### 3.3. Chọn đúng cơ chế cấu hình

| Nhu cầu | Nên dùng |
| --- | --- |
| Đổi tên scheduler, startup/shutdown, JDBC job store | `spring.quartz.*` |
| Điều chỉnh `threadCount`, `misfireThreshold`, `isClustered` | `spring.quartz.properties.*` |
| Tạo job định kỳ 5 phút, cron theo múi giờ | Bean `JobDetail` và `Trigger` |
| Tích hợp Spring-managed executor, global listener | `SchedulerFactoryBeanCustomizer` |
| Tạm dừng, chạy ngay hoặc thay lịch của job khi ứng dụng đang hoạt động | Inject `Scheduler` và gọi `pauseJob`, `triggerJob`, `rescheduleJob`… |
| Cấu hình Quartz dùng database riêng | `@QuartzDataSource`; nếu cần dùng transaction manager riêng thì `@QuartzTransactionManager` |

## 4. Ví dụ tích hợp hoàn chỉnh: đối soát đối tác mỗi 5 phút

Một dịch vụ tích hợp gọi API đối tác để đối soát các bản ghi đang ở trạng thái `PENDING`. Ta cần lịch cố định, job có identity ổn định, tránh chạy chồng cùng một `JobDetail` và xử lý chính xác lần chạy bị bỏ lỡ.

### 4.1. Job chứa nghiệp vụ

~~~java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.springframework.scheduling.quartz.QuartzJobBean;

@DisallowConcurrentExecution
public class PartnerReconcileJob extends QuartzJobBean {

    private PartnerReconcileService partnerReconcileService;

    // Được Spring Bean JobFactory thiết lập từ bean tương ứng.
    public void setPartnerReconcileService(
            PartnerReconcileService partnerReconcileService) {
        this.partnerReconcileService = partnerReconcileService;
    }

    @Override
    protected void executeInternal(JobExecutionContext context)
            throws JobExecutionException {
        try {
            partnerReconcileService.reconcilePending();
        } catch (RuntimeException ex) {
            throw new JobExecutionException(
                    "Không đối soát được dữ liệu đối tác", ex);
        }
    }
}
~~~

`PartnerReconcileService` là bean nghiệp vụ do ứng dụng triển khai, ví dụ chọn một lô bản ghi chưa đồng bộ, gọi HTTP client có timeout, cập nhật trạng thái và phát sự kiện theo hợp đồng dữ liệu. Quartz quyết định **khi nào gọi**; retry HTTP, idempotency, transaction và xử lý dữ liệu lỗi vẫn thuộc tầng nghiệp vụ.

`@DisallowConcurrentExecution` ngăn các lần chạy đồng thời của **cùng `JobDetail`/`JobKey`** trong cơ chế Quartz. Nó không khóa tất cả job cùng một Java class, không ngăn một dịch vụ khác xử lý cùng bản ghi và không thay thế unique constraint/idempotency key ở database hoặc phía đối tác.

### 4.2. Khai báo `JobDetail` và cron `Trigger`

~~~java
import java.util.TimeZone;

import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PartnerReconcileSchedule {

    @Bean
    JobDetail partnerReconcileJobDetail() {
        return JobBuilder.newJob(PartnerReconcileJob.class)
                .withIdentity("partner-reconcile", "integration")
                .storeDurably()
                .build();
    }

    @Bean
    Trigger partnerReconcileTrigger(
            @Qualifier("partnerReconcileJobDetail") JobDetail jobDetail) {
        return TriggerBuilder.newTrigger()
                .forJob(jobDetail)
                .withIdentity("partner-reconcile-cron", "integration")
                .withSchedule(CronScheduleBuilder
                        .cronSchedule("0 0/5 * * * ?")
                        .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                        .withMisfireHandlingInstructionDoNothing())
                .build();
    }
}
~~~

Cron Quartz `0 0/5 * * * ?` nghĩa là chạy ở giây 0, mỗi 5 phút. Dấu `?` trong trường ngày-thứ giúp tránh áp đặt đồng thời day-of-month và day-of-week. Múi giờ được gắn ở `Trigger`, không giả định múi giờ máy chủ. Với các múi giờ có daylight saving time, phải thiết kế và kiểm tra lịch khi đổi giờ.

`withMisfireHandlingInstructionDoNothing()` chọn **bỏ qua các lần kích hoạt đã lỡ**, sau đó chờ mốc cron kế tiếp. Nó phù hợp với job đối soát tự quét toàn bộ bản ghi `PENDING` mỗi lần. Nếu nghiệp vụ phải bù từng chu kỳ lịch sử, cần chính sách khác (ví dụ `FireAndProceed`, bảng trạng thái mốc thời gian và job bù riêng), không mặc định một đợt bắn lại đồng nghĩa với xử lý đủ mọi chu kỳ đã lỡ.

### 4.3. Luồng vận hành

~~~mermaid
flowchart TD
    A[Spring Boot khởi động] --> B[Đọc spring.quartz.*]
    B --> C[Tạo SchedulerFactoryBean]
    C --> D[Áp dụng customizer]
    D --> E[Đăng ký JobDetail và Trigger]
    E --> F{Đến giờ cron?}
    F -- Chưa --> F
    F -- Có --> G[Quartz gọi PartnerReconcileJob]
    G --> H[Service đọc bản ghi PENDING]
    H --> I[Gọi API đối tác có timeout]
    I --> J[Cập nhật kết quả, idempotency, log/metric]
    J --> F
~~~

Trong JDBC cluster, Quartz lưu thông tin job/trigger trong cùng database và phối hợp lấy trigger giữa các node. Nếu một node tắt, node khác có thể nhận việc theo cơ chế recovery/misfire của Quartz; nghiệp vụ vẫn phải chịu được tình huống một lần gọi API đã thành công nhưng tiến trình chết trước khi ghi nhận kết quả.

## 5. Các tình huống dễ cấu hình sai

**1. Restart làm mất toàn bộ trigger.** Nếu dùng `memory`, trạng thái chỉ có trong RAM. Nếu dùng `jdbc` nhưng đặt `initialize-schema: always` với script mặc định, các bảng Quartz có thể bị xóa/tạo lại. Xác định yêu cầu giữ lịch trước khi chọn job store; dùng migration DDL và `never` trong môi trường bền vững.

**2. Sửa cron trong code nhưng lịch JDBC không đổi.** Với `overwrite-existing-jobs=false`, lịch đã đăng ký trong database được ưu tiên giữ lại. Có thể chủ động `Scheduler.rescheduleJob(...)` qua một quy trình migration có kiểm soát; chỉ bật `overwrite-existing-jobs=true` nếu chủ đích để cấu hình lúc khởi động ghi đè các job/trigger persisted.

**3. Hai pod cùng chạy một nhiệm vụ ngoài ý muốn.** Kiểm tra chúng có thật sự dùng cùng database và bộ bảng `QRTZ_*`, `scheduler-name`, `isClustered=true` và `instanceId` riêng. Hai scheduler chạy `memory` độc lập sẽ cùng kích hoạt lịch; chỉ nhân bản deployment không tạo ra một Quartz cluster.

**4. Đặt `spring.task.execution.pool.*` nhưng Quartz không đổi số thread.** Pool chung của tác vụ bất đồng bộ Spring không mặc nhiên là pool Quartz. Dùng `org.quartz.threadPool.threadCount` cho thread pool mặc định của Quartz, hoặc chủ động `setTaskExecutor(...)` trong customizer và đo tải executor Spring.

**5. Công việc bị chồng, timeout hoặc lặp tác dụng phụ.** Dùng `@DisallowConcurrentExecution` đúng phạm vi `JobKey`; đặt giới hạn thời gian cho HTTP client; ghi idempotency key của yêu cầu hoặc áp dụng outbox. Không để transaction DB mở trong suốt một lời gọi HTTP chậm nếu không có lý do giao dịch rõ ràng.

**6. Job chạy ngay sau deploy khi phụ thuộc chưa sẵn sàng.** Có thể dùng `startup-delay` hoặc `auto-startup=false`, sau đó tự gọi `Scheduler.start()` khi có tín hiệu readiness phù hợp. Cả hai cách đều cần giám sát trạng thái scheduler; không coi trì hoãn cố định là health check.

**7. Tưởng lỗi job sẽ tự retry vô hạn.** `JobExecutionException` dùng để báo lỗi Quartz; cách khởi động lại tức thời còn phụ thuộc cờ `refireImmediately`, hành vi trigger và chính sách nghiệp vụ. Thiết kế retry có giới hạn, backoff, DLQ/bảng lỗi và phân biệt lỗi tạm thời với lỗi dữ liệu vĩnh viễn.

## 6. Kiểm tra cấu hình và quan sát khi triển khai

Các điểm cần xác minh trong môi trường thật:

1. **Scheduler:** tên, trạng thái started/standby, job store đang dùng, metadata thread pool. Có thể inject `Scheduler` và đọc `getMetaData()`; không suy ra JDBC hoạt động chỉ từ YAML.
2. **Persistence:** bảng `QRTZ_*` tồn tại và có thể truy cập; khởi động lại ứng dụng rồi kiểm tra `JobKey`/`TriggerKey` vẫn đúng. Khi sử dụng JDBC, chạy thử kịch bản ngắt giữa lúc job đang chạy.
3. **Cluster:** chạy ít nhất hai instance dùng cùng database, kiểm tra chỉ một instance lấy một lần kích hoạt của cùng trigger trong tình huống bình thường, rồi thử failover. Theo dõi cluster check-in, DB latency và độ lệch đồng hồ các node.
4. **Misfire:** cố ý dừng scheduler qua vài mốc cron, xác nhận chính sách `DoNothing` hoặc bù việc đã chọn đáp ứng yêu cầu.
5. **Observability:** log có `jobKey`, `triggerKey`, thời điểm dự kiến/thực tế, duration, kết quả; metric về lỗi, timeout, backlog, misfire và số job đang chạy. Với hệ thống tích hợp, liên hệ lần chạy Quartz với idempotency/correlation ID ở HTTP, DB hoặc broker.

Ví dụ kiểm tra lịch đã được đăng ký (test có Spring context):

~~~java
@Autowired
Scheduler scheduler;

@Test
void partnerReconcileJobIsRegistered() throws SchedulerException {
    JobKey key = JobKey.jobKey("partner-reconcile", "integration");
    assertNotNull(scheduler.getJobDetail(key));
}
~~~

Các import tương ứng: `org.quartz.Scheduler`, `org.quartz.SchedulerException`, `org.quartz.JobKey`, `org.springframework.beans.factory.annotation.Autowired`, `org.junit.jupiter.api.Test` và static `org.junit.jupiter.api.Assertions.assertNotNull`. Khi chạy test không muốn thực thi tác vụ thật, có thể đặt `spring.quartz.auto-startup=false` trong profile test. Với JDBC store, test tích hợp cần dùng database/schema riêng để không làm thay đổi lịch production.

### Ghi nhớ khi thiết kế tích hợp

- `spring.quartz.*` là nơi cấu hình vòng đời, storage và hành vi cấp scheduler của Spring Boot.
- `spring.quartz.properties.*` chuyển thuộc tính gốc `org.quartz.*` tới Quartz; chú ý đơn vị và tránh cấu hình trùng nghĩa với factory.
- `SchedulerFactoryBeanCustomizer` dùng cho các setter chuyên biệt, nhất là executor, listener và job factory; không cần tự tạo scheduler thứ hai.
- JDBC cluster giúp phối hợp kích hoạt lịch giữa nhiều instance nhưng **không bảo đảm exactly-once cho tác dụng phụ nghiệp vụ**. Hợp đồng dữ liệu, idempotency, transaction, retry và quan sát vẫn phải được thiết kế trong luồng tích hợp.

## Tài liệu tham khảo

- [Spring Boot Reference — Quartz Scheduler](https://docs.spring.io/spring-boot/reference/io/quartz.html)
- [Spring Boot — Common Application Properties, nhóm Quartz](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot 3.x API — SchedulerFactoryBeanCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/quartz/SchedulerFactoryBeanCustomizer.html)
- [Spring Boot 4.x API — SchedulerFactoryBeanCustomizer](https://docs.spring.io/spring-boot/4.2/api/java/org/springframework/boot/quartz/autoconfigure/SchedulerFactoryBeanCustomizer.html)
- [Spring Framework API — SchedulerFactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/quartz/SchedulerFactoryBean.html)
