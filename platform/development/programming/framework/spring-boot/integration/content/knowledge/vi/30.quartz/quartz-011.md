# DataSource riêng cho Quartz và ranh giới giao dịch

Một ứng dụng Spring Boot có thể vừa lưu đơn hàng trong cơ sở dữ liệu nghiệp vụ, vừa dùng **Quartz** để lên lịch gửi nhắc nhở, đối soát thanh toán hoặc gọi hệ thống đối tác. Nếu lịch được lưu bền vững bằng JDBC JobStore, Quartz cần đọc và ghi các bảng `QRTZ_*`. Từ đây xuất hiện một quyết định kiến trúc quan trọng: **Quartz dùng chung DataSource với nghiệp vụ hay có DataSource riêng?** Và nếu dùng riêng, lời gọi tạo lịch có nằm trong cùng giao dịch với thao tác ghi đơn hàng không?

Bài học thuộc chương **Quartz** của mô-đun **SPRING_BOOT_INTEGRATION**. Trong hệ thống tích hợp HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration, việc xác định đúng ranh giới giao dịch giúp ngăn lịch mồ côi, tác vụ bị bỏ sót, xử lý trùng, lỗi khó khôi phục và số liệu quan sát không phản ánh trạng thái thực tế.

## 1. Bối cảnh: Quartz lưu gì và lưu ở đâu?

Quartz tổ chức lịch thực thi theo ba khái niệm chính:

- **Job**: công việc được gọi khi đến lịch, triển khai giao diện `org.quartz.Job`.
- **JobDetail**: định nghĩa một job theo `JobKey`, lớp thực thi và `JobDataMap`.
- **Trigger**: quy tắc kích hoạt theo thời điểm, khoảng lặp hoặc biểu thức cron, có `TriggerKey`.

Với **RAMJobStore**, trạng thái lịch nằm trong bộ nhớ tiến trình và thường mất khi ứng dụng khởi động lại. Với **JDBC JobStore**, Quartz sử dụng các bảng trong RDBMS để duy trì job, trigger, trạng thái kích hoạt và thông tin phục vụ phối hợp giữa các scheduler instance.

Một số bảng thường gặp khi dùng tiền tố mặc định:

| Bảng | Vai trò |
| --- | --- |
| `QRTZ_JOB_DETAILS` | Metadata của các JobDetail |
| `QRTZ_TRIGGERS` | Metadata trigger và trạng thái chờ/kích hoạt |
| `QRTZ_SIMPLE_TRIGGERS`, `QRTZ_CRON_TRIGGERS` | Chi tiết theo loại trigger |
| `QRTZ_FIRED_TRIGGERS` | Thông tin trigger đang/đã được scheduler instance nhận thực thi |
| `QRTZ_LOCKS` | Phối hợp khóa trong JDBC JobStore |
| `QRTZ_SCHEDULER_STATE` | Trạng thái scheduler instance trong chế độ cluster |

Các bảng này thuộc **hạ tầng lập lịch**. Không nên dùng chúng làm bảng nghiệp vụ hoặc mặc định coi sự tồn tại của một trigger là bằng chứng nghiệp vụ đã hoàn tất.

### Tại sao cần DataSource riêng?

Giả sử ứng dụng có hai nhóm dữ liệu:

~~~mermaid
flowchart LR
    API["REST API / Application Service"] --> B["Business DataSource"]
    B --> BT["orders, payments, outbox"]
    API --> S["Quartz Scheduler"]
    S --> Q["Quartz DataSource"]
    Q --> QT["QRTZ_JOB_DETAILS, QRTZ_TRIGGERS, QRTZ_LOCKS..."]
    S --> J["Quartz worker: Job.execute()"]
    J --> D["Spring business service"]
    D --> B
~~~

Tách DataSource giúp quản lý độc lập **pool kết nối**, thông tin xác thực, quyền truy cập schema, cách migration, mức tải và khả năng quan sát. Có thể dùng hai database khác nhau hoặc hai schema được quản lý riêng. Tuy nhiên:

> **Hai DataSource thường là hai nguồn tài nguyên giao dịch độc lập.** Ngay cả khi chúng trỏ tới cùng một máy chủ PostgreSQL, hai bean DataSource/pool không mặc nhiên chia sẻ cùng Connection và cùng local transaction.

Ngược lại, nếu Quartz và nghiệp vụ dùng **cùng một DataSource bean**, cấu hình Spring-managed JDBC JobStore và cùng transaction manager đúng cách, một số thao tác lên lịch được gọi trong luồng giao dịch có thể tham gia cùng local transaction. Điều đó không có nghĩa mọi lần job chạy sau này sẽ ở trong giao dịch của người tạo lịch.

## 2. Chọn kiến trúc DataSource theo mục tiêu

| Lựa chọn | Thuận lợi | Rủi ro hoặc đánh đổi |
| --- | --- | --- |
| **RAMJobStore** | Không cần các bảng Quartz, thiết lập đơn giản | Lịch không bền vững qua restart, không dùng JDBC clustering |
| **JDBC JobStore dùng cùng DataSource nghiệp vụ** | Có thể phối hợp thao tác ghi DB và tạo lịch trong cùng local transaction khi cấu hình chuẩn | Chung pool/quyền/schema/tải; cần quản lý locks và migration của Quartz |
| **JDBC JobStore với DataSource riêng** | Tách kết nối, schema, quyền và vận hành; dễ cô lập tải Quartz | **Không có atomic commit mặc định** giữa DB nghiệp vụ và Quartz |
| **Hai DataSource với JTA/XA được cấu hình thực sự** | Có thể phối hợp giao dịch phân tán trong kiến trúc hỗ trợ | Phức tạp về coordinator, driver, JobStore, phục hồi và vận hành; không phải mặc định của Spring Boot |

Đối với ứng dụng tích hợp nhiều hệ thống, việc tách DataSource thường hợp lý khi Quartz là hạ tầng chung cho nhiều luồng công việc hoặc cần quyền truy cập và pool riêng. Nhưng nếu yêu cầu là **tạo đơn hàng và tạo lịch phải cùng thành công hoặc cùng thất bại**, cần thêm cơ chế đảm bảo tính nhất quán. Chỉ thêm annotation `@Transactional` vào service không thể làm hai database commit nguyên tử.

### Câu hỏi trước khi triển khai

1. Có cần giữ job/trigger khi ứng dụng restart không?
2. Có bao nhiêu instance chạy chung một lịch và có cần Quartz clustering không?
3. Lịch có thể khôi phục từ bản ghi nghiệp vụ nếu thao tác schedule thất bại không?
4. Nếu một lần chạy lặp lại sau sự cố, side effect có idempotent không?
5. Cơ sở dữ liệu nào làm **nguồn sự thật** cho trạng thái cần thực hiện?
6. Khi DB nghiệp vụ còn hoạt động nhưng Quartz DB lỗi, ứng dụng sẽ xử lý thế nào?

## 3. Cấu hình JDBC JobStore với DataSource riêng trong Spring Boot

Ví dụ dưới đây dùng **Spring Boot Quartz auto-configuration** và hai DataSource JDBC: một cho nghiệp vụ, một cho Quartz. Cần dependency hỗ trợ Quartz và JDBC, driver database phù hợp; đoạn Gradle là minh họa cho ứng dụng dùng PostgreSQL và Spring Boot quản lý phiên bản thư viện.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 3.1. application.yml

~~~yaml
app:
  datasource:
    business:
      url: jdbc:postgresql://localhost:5432/business_db
      username: business_app
      password: ${BUSINESS_DB_PASSWORD}
      configuration:
        maximum-pool-size: 15
    quartz:
      url: jdbc:postgresql://localhost:5432/quartz_db
      username: quartz_app
      password: ${QUARTZ_DB_PASSWORD}
      configuration:
        maximum-pool-size: 5

spring:
  quartz:
    job-store-type: jdbc
    jdbc:
      initialize-schema: never
    overwrite-existing-jobs: false
    properties:
      org.quartz.scheduler.instanceName: integrationScheduler
      org.quartz.scheduler.instanceId: AUTO
      org.quartz.threadPool.threadCount: 5
      org.quartz.jobStore.isClustered: true
      org.quartz.jobStore.clusterCheckinInterval: 20000
~~~

Giải thích:

- `spring.quartz.job-store-type=jdbc` yêu cầu Quartz duy trì lịch qua JDBC JobStore.
- `spring.quartz.jdbc.initialize-schema=never` phù hợp khi **schema Quartz đã được migration trước**. Trong môi trường phát triển có thể cho công cụ khởi tạo schema, nhưng không dùng `always` tùy tiện ở production: script chuẩn có thể xóa rồi tạo lại bảng, làm mất lịch đang lưu.
- `overwrite-existing-jobs=false` giúp tránh ghi đè các job đã tồn tại từ nguồn cấu hình khởi tạo khi restart; không thay thế cơ chế version/migration job.
- `instanceName` cần nhất quán giữa các scheduler trong cùng cụm; `instanceId=AUTO` tạo định danh instance phù hợp cho nhiều node.
- `isClustered=true` chỉ dành cho nhiều scheduler instance cần chia sẻ **cùng JDBC JobStore**; các node cần schema, thông số cluster và đồng hồ hệ thống nhất quán.
- `clusterCheckinInterval` là tham số theo dõi node. Đây không phải thời gian chờ một job nghiệp vụ.
- Kích thước pool là giá trị minh họa. Tối ưu theo số worker, số lịch, locks, latency DB và tổng số instance; không đồng nhất `threadCount` với `maximum-pool-size`.

**Quan trọng:** Khi để Spring Boot cấu hình Quartz qua `SchedulerFactoryBean` và `@QuartzDataSource`, Spring sử dụng đường đi JDBC JobStore tích hợp với DataSource do Spring quản lý. Không tự thêm `org.quartz.jobStore.class=org.quartz.impl.jdbcjobstore.JobStoreTX` hoặc `org.quartz.jobStore.dataSource` theo một ví dụ Quartz thuần Java rồi kỳ vọng chúng vẫn tương thích với cách Boot cấp DataSource. Thay đổi những thuộc tính đó phải có lý do rõ ràng và được kiểm thử.

### 3.2. Khai báo hai DataSource và hai transaction manager

Khi có nhiều DataSource bean, khai báo rõ đối tượng nào là **nghiệp vụ** (`@Primary`) và đối tượng nào dành cho **Quartz** (`@QuartzDataSource`). Với local JDBC transactions, có thể dùng `DataSourceTransactionManager` cho từng DataSource.

~~~java
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.autoconfigure.quartz.QuartzDataSource;
import org.springframework.boot.autoconfigure.quartz.QuartzTransactionManager;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class DataSourcesConfiguration {

    @Bean("businessDataSourceProperties")
    @Primary
    @ConfigurationProperties("app.datasource.business")
    DataSourceProperties businessDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean("quartzDataSourceProperties")
    @ConfigurationProperties("app.datasource.quartz")
    DataSourceProperties quartzDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean("businessDataSource")
    @Primary
    @ConfigurationProperties("app.datasource.business.configuration")
    HikariDataSource businessDataSource(
            @Qualifier("businessDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean("quartzDataSource")
    @QuartzDataSource
    @ConfigurationProperties("app.datasource.quartz.configuration")
    HikariDataSource quartzDataSource(
            @Qualifier("quartzDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean("businessTxManager")
    @Primary
    PlatformTransactionManager businessTxManager(
            @Qualifier("businessDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("quartzTxManager")
    @QuartzTransactionManager
    PlatformTransactionManager quartzTxManager(
            @Qualifier("quartzDataSource") DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Các điểm cần chú ý:

- `@QuartzDataSource` cho biết DataSource nào Spring Boot nên cấp cho Quartz. Nếu không chỉ rõ khi có hai nguồn, Quartz có thể chọn sai nguồn, thiếu bảng `QRTZ_*` hoặc sử dụng pool nghiệp vụ ngoài ý muốn.
- `@QuartzTransactionManager` đánh dấu transaction manager để Quartz auto-configuration lựa chọn. `businessTxManager` là transaction manager mặc định được đánh dấu `@Primary`.
- Annotation `@ConfigurationProperties` trên `DataSourceProperties` bind URL/tài khoản; annotation trên `HikariDataSource` bind thiết lập pool vào bean thực tế.
- Ví dụ dùng JDBC transaction manager ở cả hai phía. Nếu DB nghiệp vụ sử dụng **JPA/Hibernate**, có thể cần `JpaTransactionManager`, EntityManagerFactory và repository mapping phù hợp; không lấy nguyên mẫu JDBC làm cấu hình JPA đầy đủ.
- Một ứng dụng nhiều transaction manager nên ghi rõ `@Transactional(transactionManager = "...")` ở các ranh giới quan trọng. Chỉ dùng `@Transactional` không đối số dễ che giấu cấu hình ngầm.
- Mỗi nguồn có pool riêng nên số connection tối đa trên toàn cụm là tổng theo **mọi replica**. Quyền database của `quartz_app` chỉ nên đủ cho bảng và thao tác Quartz cần thiết.

**Không cần `@EnableScheduling` chỉ để sử dụng Quartz.** Quartz scheduler được Spring Boot tạo thông qua auto-configuration khi dependency và cấu hình phù hợp; `@EnableScheduling` chủ yếu phục vụ cơ chế `@Scheduled` của Spring.

### 3.3. Chuẩn bị schema Quartz

Các bảng `QRTZ_*` phải được tạo trước khi scheduler hoạt động trong chế độ `initialize-schema: never`. Hãy sử dụng script Quartz **đúng loại database và phiên bản đang dùng**, sau đó quản lý bằng Flyway/Liquibase hoặc quy trình migration có kiểm soát.

Một bố cục quản lý có thể là:

~~~text
Database business_db
  public.orders
  public.reminder_outbox
  public.processed_events

Database quartz_db
  public.QRTZ_JOB_DETAILS
  public.QRTZ_TRIGGERS
  public.QRTZ_CRON_TRIGGERS
  public.QRTZ_FIRED_TRIGGERS
  ...
~~~

Spring Boot có thể tự động cấu hình một Flyway chính cho database nghiệp vụ, nhưng **không mặc định chạy mọi migration trên Quartz DataSource riêng**. Nếu muốn quản lý hai database bằng Flyway, cần cấu hình migration runner và migration locations cho từng nguồn. Kiểm tra rằng schema Quartz tồn tại trước khi scheduler khởi động, tránh hai node tranh nhau tạo bảng.

Trong môi trường cluster, mọi scheduler node phải sử dụng cùng bảng Quartz của cùng cluster, cùng table prefix và cấu hình tương thích. Một node vô tình trỏ sang database khác sẽ tự thấy một lịch khác, dẫn tới công việc không được phối hợp như dự kiến.

## 4. Giao dịch thực sự nằm ở đâu?

Có ba ranh giới cần phân biệt:

1. **Lời gọi đăng ký lịch**: một request HTTP hoặc service method gọi `Scheduler.scheduleJob(...)`, `rescheduleJob(...)`, `deleteJob(...)`.
2. **Ghi trạng thái Quartz JDBC JobStore**: cập nhật các bảng `QRTZ_*`, có transaction liên quan đến `quartzDataSource`.
3. **Thực thi Job**: Quartz worker thread gọi `Job.execute(...)` vào một thời điểm khác, có thể trên instance khác. Mọi lệnh ghi DB nghiệp vụ khi job chạy cần giao dịch của chính lần chạy đó.

~~~mermaid
sequenceDiagram
    participant API as Business service
    participant B as Business DB
    participant S as Quartz Scheduler
    participant Q as Quartz DB
    participant W as Quartz worker
    API->>B: Ghi orders trong business transaction
    API->>S: scheduleJob(...)
    S->>Q: Lưu JobDetail/Trigger qua Quartz DataSource
    Note over B,Q: Hai local transaction riêng nếu hai DataSource riêng
    B-->>API: Business commit hoặc rollback
    Q-->>S: Quartz commit hoặc rollback
    Note over S,W: Sau đó, khi trigger đến hạn
    S->>W: Kích hoạt Job.execute()
    W->>B: Gọi Spring service và mở giao dịch nghiệp vụ mới
~~~

**Một transaction manager cục bộ chỉ điều phối các connection thuộc DataSource của nó.** Ví dụ:

~~~java
@Transactional(transactionManager = "businessTxManager")
public void createOrderAndScheduleReminder(CreateOrder command) {
    orderRepository.save(command.toOrder());
    reminderScheduler.schedule(command.orderId(), command.remindAt());
}
~~~

Nếu `reminderScheduler.schedule(...)` ghi qua `quartzDataSource` riêng, dù được gọi từ phương thức có `@Transactional("businessTxManager")`, thao tác lên lịch **không tự động tham gia transaction nghiệp vụ**. Một bên có thể commit còn bên kia rollback.

| Thời điểm thất bại | DB nghiệp vụ | Quartz DB | Hậu quả có thể xảy ra |
| --- | --- | --- | --- |
| Lưu đơn hàng thất bại trước khi schedule | Không có đơn hàng | Chưa có lịch | Thường dễ xử lý |
| Quartz tạo lịch thành công, sau đó business rollback | Không có đơn hàng | Có trigger | **Lịch mồ côi**, job chạy với dữ liệu không tồn tại |
| Business commit, Quartz schedule thất bại | Có đơn hàng | Không có trigger | **Thiếu lịch**, nghiệp vụ có thể bị bỏ sót |
| Cả hai commit nhưng ứng dụng crash trước khi trả HTTP | Có đơn hàng | Có trigger | Client có thể retry và tạo yêu cầu trùng nếu thiếu idempotency |
| Job bắt đầu chạy nhưng ghi DB thất bại | Lịch có thể đã kích hoạt | Trạng thái trigger tùy cấu hình/misfire | Job cần chính sách retry/recovery riêng, không dựa vào transaction tạo lịch |

Khi hai nguồn trỏ đến cùng PostgreSQL server, khác schema hay thậm chí dùng cùng URL nhưng **hai pool/connection riêng**, bảng trên vẫn có thể xảy ra. Để chia sẻ local transaction trong trường hợp phù hợp, Quartz cần thao tác với **chính DataSource/transaction manager được Spring quản lý cho cùng giao dịch**, không chỉ cùng tên máy chủ.

## 5. Transaction manager của Quartz được dùng thế nào?

Với JDBC JobStore được tích hợp bởi Spring qua `SchedulerFactoryBean` và DataSource, Spring có thể phối hợp các thao tác truy cập JobStore với transaction manager tương ứng khi gọi trong **Spring-managed transaction** trên cùng thread.

Ví dụ một service chỉ chịu trách nhiệm tạo lịch:

~~~java
import java.time.Instant;
import java.util.Date;

import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.SchedulerException;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.quartz.TriggerKey;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReminderSchedulingService {

    private final Scheduler scheduler;

    public ReminderSchedulingService(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    @Transactional(transactionManager = "quartzTxManager")
    public void schedule(String orderId, Instant runAt)
            throws SchedulerException {

        JobKey jobKey = JobKey.jobKey("reminder-" + orderId, "orders");
        TriggerKey triggerKey =
                TriggerKey.triggerKey("reminder-" + orderId, "orders");

        JobDetail job = JobBuilder.newJob(OrderReminderJob.class)
                .withIdentity(jobKey)
                .usingJobData("orderId", orderId)
                .build();

        Trigger trigger = TriggerBuilder.newTrigger()
                .withIdentity(triggerKey)
                .forJob(job)
                .startAt(Date.from(runAt))
                .build();

        scheduler.scheduleJob(job, trigger);
    }
}
~~~

`OrderReminderJob` là lớp `public` triển khai `org.quartz.Job` của ứng dụng; ví dụ tập trung vào phần đăng ký lịch. Các định danh `JobKey` và `TriggerKey` được xây dựng ổn định từ business key để dễ đối soát khi retry. Nếu job/trigger đã tồn tại, `scheduleJob(job, trigger)` có thể báo `ObjectAlreadyExistsException`: đây là tín hiệu để **kiểm tra và reconcile lịch hiện hữu**, không đơn giản bỏ qua mọi exception.

Điều kiện để ví dụ tham gia đúng transaction Quartz:

- `Scheduler` phải là instance Spring Boot đã cấu hình với **Quartz DataSource** và transaction manager phù hợp.
- Gọi `schedule(...)` qua Spring bean proxy để `@Transactional` thực sự có hiệu lực; gọi nội bộ qua `this.schedule(...)` không kích hoạt transaction proxy thông thường.
- Tác vụ làm trong transaction chỉ liên quan tới Quartz DataSource. Thêm `@Transactional("quartzTxManager")` **không bao phủ** repository đang dùng business DataSource.
- Với các thao tác nằm ngoài Spring transaction (ví dụ công cụ Quartz bên ngoài ứng dụng), cơ chế quản lý transaction có thể khác và cần được kiểm thử theo JobStore thực tế.

**Giao dịch khi tạo lịch không kéo dài đến lúc job chạy.** Khi trigger đến hạn, `Job.execute()` chạy trên Quartz worker thread, thường không có transaction của request gốc. Nếu job cần cập nhật đơn hàng, hãy gọi vào một **Spring-managed business service** có `@Transactional("businessTxManager")`, thay vì mặc định rằng annotation trên một lớp `Job` do Quartz khởi tạo luôn được proxy đúng.

### 5.1. Tại sao không tự chuyển JobStoreTX/JobStoreCMT theo mẹo cấu hình?

Quartz thuần Java có các kiểu JDBC JobStore như `JobStoreTX` (tự quản local transaction) và `JobStoreCMT` (được thiết kế cho giao dịch container-managed). Trong ứng dụng Spring Boot thông thường, việc đưa DataSource vào `SchedulerFactoryBean` sẽ dùng đường tích hợp **Spring LocalDataSourceJobStore**. Tự đặt `org.quartz.jobStore.class`, `org.quartz.jobStore.dataSource` hoặc các thông số xa lạ với cấu hình đang dùng có thể khiến scheduler bỏ qua DataSource hoặc transaction-aware connection do Spring cấp.

Nếu thực sự cần XA/JTA hai nguồn dữ liệu, cần kiến trúc và cấu hình nhất quán từ transaction coordinator, JDBC driver, JobStore tới Spring transaction manager. Chỉ thêm dependency JTA hoặc `@Transactional` không tạo distributed transaction.

## 6. Cách giữ nhất quán khi nghiệp vụ và Quartz dùng hai database

Vấn đề cần giải quyết: thao tác `createOrder` ghi business DB và thao tác `scheduleJob` ghi Quartz DB **không commit nguyên tử**. Có ba chiến lược, lựa chọn theo yêu cầu độ tin cậy.

### 6.1. Best effort: tạo lịch trực tiếp và có bước bù

Luồng đơn giản có thể ghi đơn hàng, rồi tạo lịch. Nếu tạo lịch thất bại, lưu trạng thái `PENDING_SCHEDULE` và retry; nếu nghiệp vụ thất bại sau khi tạo lịch, có thể xóa trigger tương ứng.

Tuy nhiên **compensating action không phải atomic rollback**. Xóa lịch có thể thất bại hoặc job đã được kích hoạt, và service có thể crash giữa hai thao tác. Chỉ phù hợp khi chấp nhận được cửa sổ bất nhất và có kiểm tra định kỳ.

### 6.2. Outbox + dispatcher idempotent: lựa chọn thực tế cho luồng quan trọng

Sử dụng **business DB làm nguồn sự thật**. Ghi đơn hàng và ý định tạo lịch vào **outbox trong cùng local business transaction**:

~~~mermaid
flowchart LR
    R["HTTP / event tạo đơn"] --> TX["Business transaction"]
    TX --> O["orders"]
    TX --> OB["reminder_outbox (PENDING)"]
    OB --> D["Dispatcher / worker"]
    D --> S["Quartz scheduleJob"]
    S --> Q["Quartz JDBC JobStore"]
    D --> M["Đánh dấu outbox PROCESSED"]
    Q --> J["Đến hạn: Quartz Job"]
    J --> V["Kiểm tra trạng thái nghiệp vụ và idempotency"]
~~~

Có thể mô tả thuật toán như sau:

1. Trong `@Transactional("businessTxManager")`, lưu `orders` và một hàng outbox có `eventId`, `orderId`, `runAt`, `status=PENDING` với ràng buộc unique.
2. Dispatcher đọc các hàng cần xử lý bằng cơ chế lock/lease phù hợp nếu nhiều replica.
3. Với từng hàng, tạo `JobKey/TriggerKey` **ổn định** từ business key, gọi `Scheduler.scheduleJob` và xác nhận Quartz đã chấp nhận.
4. Nếu có lỗi `ObjectAlreadyExistsException`, kiểm tra job/trigger hiện hữu và nội dung lịch mong đợi. Chỉ xem là thành công khi lịch đã đúng hoặc được chỉnh thành đúng.
5. Sau khi Quartz đã lưu lịch, đánh dấu hàng outbox `PROCESSED` bằng một **business transaction mới**.
6. Nếu tiến trình crash trước bước 5, dispatcher đọc lại hàng `PENDING` và reconcile với Quartz, tránh tạo job nhân đôi.
7. Khi job thực thi, kiểm tra trạng thái đơn hàng và khóa idempotency để không gửi thông báo hoặc gọi HTTP lặp ngoài ý muốn.

| Cửa sổ lỗi | Điều gì còn bền vững? | Khôi phục |
| --- | --- | --- |
| Crash trước commit business transaction | Không có order/outbox hợp lệ | Client retry request có idempotency |
| Business commit, chưa gọi Quartz | Outbox `PENDING` | Dispatcher sẽ gọi lại |
| Quartz schedule thành công, chưa đánh dấu outbox | Lịch đã có, outbox vẫn `PENDING` | Reconcile theo JobKey/TriggerKey, rồi đánh dấu hoàn tất |
| Quartz DB tạm thời lỗi | Outbox còn `PENDING` | Backoff/retry, cảnh báo nếu vượt SLA |
| Job chạy lại sau crash/recovery | Có thể thấy lần kích hoạt hoặc side effect lặp | Kiểm tra business state và dedup key trong job |

Điểm mạnh của outbox là **ý định tạo lịch không mất** khi đã commit cùng dữ liệu nghiệp vụ. Nhưng vẫn có trạng thái nhất quán cuối cùng (*eventual consistency*): lịch có thể chưa xuất hiện ngay khi transaction nghiệp vụ trả thành công. Hãy đo độ trễ từ lúc outbox được ghi đến lúc Quartz xác nhận lịch; nếu lịch cần chạy ngay, thiết kế SLA và phương án xử lý quá hạn.

### 6.3. Khi cần atomicity chặt hơn

Nếu lịch và dữ liệu nghiệp vụ phải commit cùng một lần và thực sự cùng database, cân nhắc dùng **cùng DataSource bean và một local transaction** với cấu hình Spring Quartz phù hợp. Nếu là **hai database độc lập**, muốn atomicity ở tầng transaction cần giải pháp **XA/JTA** triển khai đầy đủ, có cost và hạn chế vận hành. Nhiều hệ thống tích hợp ưu tiên outbox, cơ chế bù và idempotency vì dễ phục hồi hơn qua các dịch vụ bên ngoài.

Không kỳ vọng Quartz JDBC JobStore tự giải quyết tính nguyên tử cho **HTTP request đến đối tác**, **Kafka publish** hoặc **SQL ở database khác**; chúng là các tài nguyên giao dịch khác.

## 7. Tác vụ Quartz chạy sau đó: một giao dịch mới

Đặt lịch thành công chỉ chứng minh **JobDetail/Trigger đã được nhận và ghi theo chính sách JobStore**, không chứng minh side effect nghiệp vụ đã chạy thành công.

Khi đến hạn:

1. Quartz lấy trigger tới hạn từ JobStore và phân phối công việc lên worker thread.
2. `Job.execute()` đọc các tham số nhỏ trong `JobDataMap`, ví dụ `orderId` và `eventId`.
3. Job ủy quyền cho Spring service thực hiện nghiệp vụ, với transaction manager đúng cho business DB.
4. Service kiểm tra trạng thái và idempotency trước khi gọi API ngoài hoặc ghi DB.
5. Kết quả, lỗi và thời gian thực thi được ghi nhận để alert và reconciliation khi cần.

`JobDataMap` nên lưu **ID/giá trị nhỏ, đơn giản**, không serialize các object domain lớn, Spring bean, mật khẩu hoặc token. Đối tượng Java serialized có thể hỏng khi deploy phiên bản mới; với JDBC JobStore hãy cân nhắc cấu hình dữ liệu phù hợp (ví dụ chỉ string) theo cách lưu JobDataMap đang sử dụng.

Nếu job gọi API có thể timeout **sau khi đối tác đã xử lý thành công**, retry có thể tạo trùng side effect. Sử dụng idempotency key, bảng inbox hoặc bước truy vấn kết quả trước khi phát lại. `@DisallowConcurrentExecution` có thể ngăn các lần thực thi đồng thời của **cùng JobDetail/JobKey** trong giới hạn Quartz điều phối, nhưng không bảo đảm exactly-once sau crash, recovery, replay hoặc một job khác cùng làm nghiệp vụ.

### 7.1. Misfire và phục hồi không đồng nghĩa với retry nghiệp vụ

**Misfire** xảy ra khi trigger bị trễ so với lịch, ví dụ scheduler ngừng hoặc không đủ worker. Quartz có các chính sách xử lý misfire riêng cho simple/cron trigger (bỏ qua lịch cũ, kích hoạt ngay, cập nhật lần chạy kế tiếp tùy cấu hình).

**Job recovery** liên quan tới job được đánh dấu yêu cầu phục hồi khi scheduler gặp sự cố; nó khác với việc tự retry exception nghiệp vụ trong `execute()`. Không thiết kế hệ thống dựa trên giả định mọi job lỗi sẽ tự chạy lại đúng một lần. Với tác vụ quan trọng, lưu business state để nhận diện `PENDING/RUNNING/SUCCEEDED/FAILED` và thiết kế retry/reconciliation tường minh.

## 8. Vận hành JDBC JobStore riêng và clustering

Khi Quartz dùng schema riêng, cần coi database này là một thành phần vận hành độc lập:

| Hạng mục | Thực hành đề xuất |
| --- | --- |
| **Pool và capacity** | Đo số connection Quartz, lock contention, thời gian truy vấn và số scheduler instances |
| **Schema migration** | Version script Quartz, backup, chạy migration có kiểm soát trước khởi động |
| **Quyền truy cập** | Tài khoản Quartz chỉ có quyền cần thiết trên schema/bảng Quartz |
| **Độ sẵn sàng** | Có cảnh báo riêng khi Quartz DB lỗi, dù business DB còn hoạt động |
| **Cluster consistency** | Các node dùng cùng JobStore, `instanceName`, tiền tố bảng và cấu hình tương thích; `instanceId` riêng |
| **Đồng hồ hệ thống** | NTP/time sync và múi giờ rõ ràng với cron; lệch thời gian ảnh hưởng firing/misfire |
| **Sao lưu/khôi phục** | Kiểm tra phục hồi bảng Quartz đồng bộ với business state và outbox |
| **Dữ liệu nhạy cảm** | Không ghi token/credential trong JobDataMap hoặc log; giới hạn quyền xem lịch |

Nếu hai node chạy Quartz JDBC JobStore cùng dữ liệu mà **không cấu hình cluster đúng**, chúng có thể điều phối trigger sai hoặc xử lý lặp. Khi bật cluster, cần xác minh tất cả node đang dùng cùng database, các tham số scheduler tương thích, và cân nhắc chỉ kích hoạt scheduler trên những instance thực sự cần xử lý lịch.

Không tự sửa các bảng `QRTZ_*` để xóa lỗi hoặc thay đổi lịch nếu Quartz vẫn đang chạy: dễ phá tính nhất quán giữa trigger, job và locks. Ưu tiên Quartz Scheduler API, quy trình migration và công cụ vận hành được kiểm soát.

### Tách biệt giao dịch và giám sát

Các tín hiệu nên theo dõi:

- Số trigger `WAITING`, `ACQUIRED`, `ERROR`/blocked (tùy kiểu job và trạng thái thực tế), chênh lệch thời điểm dự kiến so với thời điểm chạy.
- Lỗi truy cập bảng Quartz, lock timeout, connection pool exhaustion và cluster check-in.
- Số hàng outbox `PENDING`, độ tuổi outbox lâu nhất, số lần retry và số lịch được reconcile.
- Tỷ lệ job thành công/thất bại, p95/p99 thời gian chạy, missed SLA và misfire.
- Mã lỗi từ HTTP/DB/Kafka adapter mà job gọi, correlation ID/job key và trạng thái idempotency.

Không phải mọi metric được xuất ra sẵn bởi mọi bản Spring Boot/Quartz. Có thể tích hợp Actuator, Micrometer, `JobListener`/`TriggerListener` và metric tự định nghĩa để tạo số liệu đủ cho mục tiêu vận hành. Tránh log dữ liệu nhạy cảm từ `JobDataMap`.

## 9. Kiểm thử ranh giới giữa hai DataSource

Để đánh giá thiết kế, test không nên chỉ kiểm tra một job được gọi đúng giờ. Phải chứng minh **sai lỗi ở từng transaction boundary** được xử lý rõ ràng. Dùng Testcontainers với hai PostgreSQL database hoặc hai schema độc lập, migration Quartz thật và Spring Boot context thật là một hướng cho integration test.

| Kịch bản | Cách dựng | Điều cần chứng minh |
| --- | --- | --- |
| **Quartz lấy đúng DataSource** | Khởi động context với hai nguồn và schema Quartz chỉ trên nguồn Quartz | Scheduler thao tác bảng `QRTZ_*` ở đúng database, business repository không trỏ nhầm |
| **Rollback business sau khi đã schedule** | Cố ý ném exception khi giao dịch nghiệp vụ chưa commit | Với hai nguồn độc lập có thể còn lịch; test ghi nhận rủi ro để bắt buộc dùng outbox/reconcile |
| **Business commit, Quartz DB offline** | Tắt/làm lỗi kết nối Quartz trước bước schedule | Order + outbox vẫn bền vững, dispatcher retry có giới hạn |
| **Crash sau schedule, trước ack outbox** | Chặn dispatcher tại điểm chuyển trạng thái | Retry không tạo trigger nhân đôi; trạng thái outbox được reconcile |
| **Cùng request được gửi hai lần** | Gửi event/HTTP request cùng idempotency key | Chỉ một business intent và một lịch mong muốn |
| **Job chạy lại** | Retry/recovery/trigger duplicate trong test | Side effect tại DB/API chỉ phát sinh một lần theo business key |
| **Hai Quartz instances** | Hai scheduler chung JDBC JobStore ở chế độ cluster | Trigger được nhận đúng theo cơ chế cluster và job xử lý idempotent |
| **Không khởi tạo lại bảng** | Restart khi đã có job/triggers persisted | Lịch còn nguyên, dữ liệu Quartz không bị drop |
| **Schema hoặc credential sai** | Chỉ cấp quyền/đường kết nối hạn chế | Startup/runtime báo lỗi rõ nguồn Quartz, không chạy nhầm vào business DB |

Với test liên quan cron/misfire, dùng đồng hồ/test window có kiểm soát, timeout assert theo điều kiện và dọn dữ liệu đúng cách. Với lỗi mạng, test cần kiểm tra trạng thái sau recovery chứ không chỉ assert `SchedulerException`. Không làm integration test bằng cách thay đổi trực tiếp `QRTZ_LOCKS` hoặc reset các offset/giá trị hệ thống không thuộc phạm vi test.

### Câu hỏi khi review pull request

- Annotation `@QuartzDataSource` có trỏ đúng bean, và `@QuartzTransactionManager` có trỏ đúng transaction manager không?
- Ai chịu trách nhiệm tạo schema `QRTZ_*`? Có nguy cơ `initialize-schema=always` xóa lịch khi deploy không?
- Từ thời điểm business commit đến Quartz schedule, hệ thống có thể crash ở đâu? Có outbox/retry/reconcile không?
- Tên `JobKey/TriggerKey` có ổn định theo business key để xử lý request lặp không?
- Job thực thi có gọi đúng Spring business service, transaction manager và chính sách idempotency không?
- Khi ứng dụng scale nhiều replica, các scheduler có thật sự chia sẻ đúng JDBC JobStore và cấu hình cluster không?
- Có theo dõi tuổi bản ghi chờ schedule và tình trạng trigger bị trễ không?

## 10. Thực hành: thiết kế luồng nhắc nhở đơn hàng

Giả sử khi đơn hàng chuyển sang `CONFIRMED`, phải gửi một thông báo sau 24 giờ. Thiết kế:

1. **Transaction nghiệp vụ:** ghi `orders.status=CONFIRMED` và một hàng `reminder_outbox(order_id, run_at, status=PENDING)`; ràng buộc `unique(order_id, reminder_type)`.
2. **Dispatcher:** poll hàng outbox bằng lock/lease; tạo `JobKey("reminder-" + orderId, "orders")` và `TriggerKey` ổn định. Nếu Quartz có lịch, kiểm tra `runAt` và trạng thái thay vì tạo lịch mới.
3. **Sau khi Quartz xác nhận:** đánh dấu outbox thành `PROCESSED` trong transaction riêng tại business DB.
4. **Khi trigger đến hạn:** job đọc `orderId`, kiểm tra đơn còn ở trạng thái phù hợp, gửi thông báo qua adapter có idempotency key, ghi `reminder_sent` hoặc inbox để chống gửi lại.
5. **Reconciliation:** chạy kiểm tra định kỳ những hàng outbox quá hạn, trigger thiếu hoặc trạng thái nghiệp vụ đã đổi; hủy/sửa lịch bằng Quartz API theo chính sách nghiệp vụ.

Thử cố tình gây bốn lỗi: (a) rollback đơn hàng; (b) mất kết nối Quartz DB; (c) crash sau `scheduleJob` trước cập nhật outbox; (d) job chạy lại sau timeout ở API thông báo. Bài làm đạt yêu cầu khi **không mất ý định tạo lịch**, **không tạo lịch mồ côi không được xử lý**, **không gửi thông báo trùng ngoài chính sách**, và có metric/alert để xác định tình trạng tồn đọng.

## 11. Checklist vận hành

- [ ] Đã chọn RAMJobStore hay JDBC JobStore theo yêu cầu bền vững và cluster.
- [ ] Quartz DataSource, pool, tài khoản và schema được cấu hình tách bạch khi cần.
- [ ] Có `@QuartzDataSource`, `@QuartzTransactionManager`, transaction manager nghiệp vụ đúng mục đích.
- [ ] Không tự cấu hình chồng chéo `JobStoreTX` với Spring-managed JDBC JobStore khi không có thiết kế riêng.
- [ ] Migration cho bảng Quartz được quản lý và bảo toàn job/trigger qua restart.
- [ ] Mọi node Quartz trong cluster dùng chung JobStore và cấu hình tương thích.
- [ ] Đã chứng minh ranh giới commit giữa database nghiệp vụ và Quartz; không dựa vào `@Transactional` một mình để đảm bảo atomicity hai nguồn.
- [ ] Nếu dùng hai nguồn độc lập, đã có outbox/compensation/reconciliation và idempotent scheduling.
- [ ] Job thực thi dùng giao dịch riêng, dữ liệu nhỏ trong `JobDataMap`, side effect có bảo vệ xử lý trùng.
- [ ] Có integration test cho rollback, crash window, mất kết nối, duplicate và failover.
- [ ] Có cảnh báo trạng thái Quartz JDBC, độ tuổi outbox, trigger trễ và tỷ lệ job lỗi.

**Kết luận:** DataSource riêng giúp Quartz có ranh giới vận hành rõ ràng, nhưng cũng tạo **ranh giới giao dịch riêng**. Trong Spring Boot, phải lựa chọn rõ dữ liệu nào là nguồn sự thật và cách phục hồi khi business DB và Quartz DB không cùng commit. Một thiết kế có **transaction manager tường minh, migration an toàn, outbox/idempotency và kiểm thử các cửa sổ crash** sẽ đáng tin cậy hơn giả định một annotation có thể bao trùm toàn bộ luồng tích hợp.
