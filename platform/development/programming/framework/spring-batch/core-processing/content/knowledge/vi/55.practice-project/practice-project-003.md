# Cấu hình JobRepository và JobLauncher trong dự án Spring Batch

## 1. Bối cảnh dự án và mục tiêu

Khi xây dựng một ứng dụng Spring Batch, hai thành phần nền tảng cần hiểu là **`JobRepository`** và **`JobLauncher`**:

- `JobRepository` lưu metadata về `JobInstance`, `JobExecution`, `StepExecution`, trạng thái và checkpoint cần cho restart.
- `JobLauncher` nhận một `Job` cùng `JobParameters` rồi yêu cầu Spring Batch khởi chạy công việc thông qua repository.

Nếu cấu hình không đúng, một job có thể chạy được một lần nhưng không restart được, hai scheduler cùng chạy gây trùng, metadata biến mất sau khi ứng dụng khởi động lại, hoặc Spring Boot tự launch job ngoài ý muốn khi deploy.

Bài thực hành này xây dựng **ứng dụng tổng hợp doanh thu theo ngày**. Lúc được yêu cầu, ứng dụng đọc bảng `sales_order` và ghi tổng doanh thu vào `daily_sales_summary`. Cả hai là bảng nghiệp vụ; Spring Batch sử dụng các bảng metadata riêng để quản lý lịch sử chạy.

Mục tiêu sau bài:

1. Hiểu vai trò của `JobRepository` và `JobLauncher` trong hệ thống.
2. Khởi tạo dự án Spring Boot 3.x + Spring Batch 5.x + PostgreSQL.
3. Để Spring Boot tự cấu hình hạ tầng Batch khi phù hợp, tránh tự khai báo trùng bean.
4. Định nghĩa `Job` và `Step` có inject `JobRepository` và `PlatformTransactionManager`.
5. Khởi chạy job có kiểm soát bằng `JobLauncher` và `JobParameters`.
6. Quan sát metadata, phân biệt lần chạy mới, restart và yêu cầu trùng.
7. Hiểu cách cấu hình thủ công hoặc launcher bất đồng bộ khi có yêu cầu riêng.
8. Kiểm thử cấu hình repository/launcher mà không phụ thuộc dữ liệu production.

**Phạm vi:** ví dụ dùng Java 17+, Spring Boot 3.x, Spring Batch 5.x, JDBC và PostgreSQL. Phiên bản thư viện chính xác phải tương thích với bản Spring Boot mà dự án chọn. Các ví dụ chỉ thiết lập môi trường và hướng dẫn code, không yêu cầu chạy công cụ build trong quá trình đọc bài.

## 2. Kiến trúc: repository lưu gì, launcher làm gì?

Luồng khi yêu cầu chạy một job:

```text
                        CLI / API / Scheduler
                                 |
                                 v
                     JobLauncher.run(Job, params)
                                 |
                                 v
                      JobRepository (JDBC)
                    /           |           \
             JobInstance   JobExecution   StepExecution
                                 |
                                 v
                             Job / Step
                                 |
                         Business DataSource
                         /               \
                   sales_order     daily_sales_summary
                                 |
                                 v
                       JobExecution hoàn tất
                       COMPLETED / FAILED
                                 |
                                 v
                  Metadata được lưu cho lần sau
```

Về trách nhiệm:

| Thành phần | Trách nhiệm chính | Không làm thay bạn |
| --- | --- | --- |
| `JobRepository` | Lưu và truy vấn metadata execution; kiểm soát identity và trạng thái khi tạo execution | Không tự tạo bảng nghiệp vụ, không bảo đảm mọi API ngoài DB là exactly-once |
| `JobLauncher` | Nhận yêu cầu khởi chạy; phối hợp repository và thực thi job | Không tự tạo business date chính xác hoặc tự quyết định lịch chạy |
| `Job` | Mô tả luồng step và chính sách restart | Không mặc định biết nguồn dữ liệu nào cần xử lý |
| `Step` | Thực hiện tasklet hoặc chunk processing trong giao dịch phù hợp | Không mặc định chống ghi trùng vào hệ ngoài |
| `PlatformTransactionManager` | Điều khiển transaction cho step và truy cập dữ liệu theo cấu hình | Không tự gộp nhiều datasource thành một distributed transaction |
| `JobExplorer` | Đọc metadata phục vụ giám sát và điều tra | Không phải công cụ sửa trạng thái tùy ý |
| `JobParameters` | Chứa input điều khiển job và phân biệt JobInstance | Không tự xác nhận tham số có ý nghĩa nghiệp vụ |

Có thể hiểu ngắn gọn: **`JobLauncher` là cổng khởi chạy; `JobRepository` là nơi lưu lịch sử và trạng thái chính thức của Batch.**

## 3. JobInstance và JobExecution quyết định hành vi launch

Một `Job` có thể được gọi nhiều lần, nhưng không phải mỗi lời gọi đều tạo một instance mới.

- **`Job`**: định nghĩa công việc, chẳng hạn `dailySalesJob`.
- **`JobParameters`**: tham số lần chạy, có thể được đánh dấu identifying hoặc non-identifying.
- **`JobInstance`**: tên job cộng các identifying parameters.
- **`JobExecution`**: một lần thực thi của instance ấy.
- **`StepExecution`**: lần thực thi một step, gắn với JobExecution.

Ví dụ:

```text
Job: dailySalesJob
  |
  +-- JobInstance 101
  |     businessDate = 2026-11-15
  |       |
  |       +-- JobExecution 9001 : FAILED
  |       +-- JobExecution 9002 : COMPLETED (restart)
  |
  +-- JobInstance 102
        businessDate = 2026-11-16
          |
          +-- JobExecution 9003 : COMPLETED
```

Ba kết quả quan trọng:

1. Nếu chưa có instance cho ngày D, `JobLauncher` có thể tạo JobInstance mới.
2. Nếu execution trước của ngày D thất bại và job được phép restart, launch với cùng identifying parameters có thể tạo **JobExecution mới của cùng instance**.
3. Nếu instance ngày D đã `COMPLETED`, launch lại với cùng identifying parameters thường bị từ chối bằng `JobInstanceAlreadyCompleteException`.

Không nên thêm timestamp ngẫu nhiên vào identifying parameters để vượt qua trường hợp thứ ba; điều đó tạo instance khác và có thể ghi trùng dữ liệu.

## 4. Cấu trúc dự án thực hành

Ví dụ cấu trúc một ứng dụng Spring Boot:

```text
batch-demo/
  ├── build.gradle
  └── src/
      ├── main/
      │   ├── java/com/example/batchdemo/
      │   │   ├── BatchDemoApplication.java
      │   │   ├── job/DailySalesJobConfiguration.java
      │   │   └── launch/DailySalesLaunchConfiguration.java
      │   └── resources/
      │       ├── application.yml
      │       └── db/migration/V1__create_business_tables.sql
      └── test/
          └── java/com/example/batchdemo/
              └── BatchInfrastructureTest.java
```

Trong phần hướng dẫn, Spring Boot quản lý datasource, transaction manager và cơ sở hạ tầng Batch. Ứng dụng chỉ định nghĩa business job/step và entry point gọi launcher.

**Không cần tự tạo Bean `JobRepository`/`JobLauncher` nếu Boot auto-configuration đang đáp ứng yêu cầu.** Việc tự đăng ký `@EnableBatchProcessing` hoặc kế thừa `DefaultBatchConfiguration` có thể làm Boot ngừng tự cấu hình một phần hạ tầng; chỉ chuyển sang cấu hình thủ công khi có lý do rõ ràng.

## 5. Khai báo dependency

Với một project Gradle sinh từ Spring Initializr và một phiên bản Spring Boot 3.x tương thích, các dependency cốt lõi:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

test {
    useJUnitPlatform()
}
```

Spring Boot quản lý các phiên bản dependency qua BOM/plugin của dự án. Khi bắt đầu dự án, chọn một bản Spring Boot 3.x được hỗ trợ và yêu cầu Java 17 hoặc cao hơn; tránh tự ghép các bản Spring Batch và Spring Framework không tương thích.

Vai trò của mỗi dependency:

| Dependency | Chức năng |
| --- | --- |
| `spring-boot-starter-batch` | Spring Batch core, infrastructure và tích hợp Spring Boot |
| `spring-boot-starter-jdbc` | `JdbcTemplate` và hạ tầng truy cập JDBC |
| `postgresql` | JDBC driver cho PostgreSQL |
| `spring-boot-starter-test` | JUnit 5, test utilities và tích hợp Spring Boot |
| `spring-batch-test` | Các tiện ích kiểm thử job, step và metadata |
| `h2` (test) | Database tạm cho test infrastructure đơn giản |

Để quản lý migration schema nghiệp vụ và metadata ở production, có thể bổ sung Flyway hoặc Liquibase theo chuẩn hệ thống. Ví dụ sử dụng file migration nghiệp vụ; phần metadata Batch được khởi tạo bằng cấu hình Boot chỉ để minh họa môi trường thực hành.

## 6. Chuẩn bị PostgreSQL và schema

Ví dụ dùng database `batch_demo` và tài khoản DB riêng có quyền phù hợp. Cần tạo database, cấp quyền cho tài khoản ứng dụng và xác định cơ chế quản lý schema.

Có **hai nhóm bảng**:

1. **Metadata của Spring Batch:** thường có tiền tố `BATCH_`.
2. **Bảng nghiệp vụ:** do ứng dụng định nghĩa, ví dụ `sales_order` và `daily_sales_summary`.

### 6.1. Một số bảng metadata chuẩn

| Bảng | Vai trò |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Lưu danh tính JobInstance |
| `BATCH_JOB_EXECUTION` | Lưu mỗi JobExecution, thời gian và trạng thái |
| `BATCH_JOB_EXECUTION_PARAMS` | Lưu JobParameters gắn với execution |
| `BATCH_STEP_EXECUTION` | Lưu trạng thái và bộ đếm từng StepExecution |
| `BATCH_JOB_EXECUTION_CONTEXT` | Lưu context cấp job |
| `BATCH_STEP_EXECUTION_CONTEXT` | Lưu checkpoint/context cấp step |
| Các sequence `BATCH_*_SEQ` | Cấp ID cho metadata theo schema/dialect |

Tên và cấu trúc cột có thể khác giữa các phiên bản. Với Spring Batch 5.x, cấu trúc `BATCH_JOB_EXECUTION_PARAMS` khác schema Batch 4.x; cần chọn script migration đúng phiên bản, không dùng lẫn.

**Không coi metadata Batch là dữ liệu tạm có thể xóa tùy tiện.** Xóa schema sau mỗi lần deploy sẽ khiến repository quên lịch sử và mất khả năng restart đúng nghĩa.

### 6.2. Schema nghiệp vụ

Ví dụ migration PostgreSQL `V1__create_business_tables.sql`:

```sql
CREATE TABLE sales_order (
    order_id BIGINT PRIMARY KEY,
    business_date DATE NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE INDEX idx_sales_order_business_date
    ON sales_order (business_date);

CREATE TABLE daily_sales_summary (
    business_date DATE PRIMARY KEY,
    total_amount NUMERIC(20, 2) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
```

Dữ liệu mẫu:

```sql
INSERT INTO sales_order (
    order_id, business_date, amount, status
)
VALUES
    (101, DATE '2026-11-15', 120000.00, 'PAID'),
    (102, DATE '2026-11-15',  35000.00, 'PAID'),
    (103, DATE '2026-11-15',  50000.00, 'CANCELLED'),
    (104, DATE '2026-11-16',  42000.00, 'PAID');
```

Job chỉ cộng các đơn hàng `status='PAID'` trong ngày cần xử lý. Ngày 15/11 có tổng doanh thu mẫu:

```text
120000.00 + 35000.00 = 155000.00
```

Nếu migration được quản lý bởi Flyway, đặt script trong đường dẫn migration chuẩn và bật Flyway theo cấu hình dự án. Trong bài này, SQL được trình bày để bạn thấy rõ bảng nghiệp vụ nào cần có trước khi job được thực thi.

## 7. Cấu hình application.yml

Ví dụ môi trường thực hành:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/batch_demo
    username: batch_user
    password: ${BATCH_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

app:
  launch:
    enabled: false

logging:
  level:
    org.springframework.batch: INFO
```

Giải thích:

- `spring.datasource.*`: cung cấp JDBC datasource cho Batch metadata và nghiệp vụ trong ví dụ dùng chung database.
- `spring.batch.job.enabled=false`: **tắt tự khởi chạy job khi ứng dụng startup** qua cơ chế JobLauncherApplicationRunner của Spring Boot.
- `spring.batch.jdbc.initialize-schema=always`: yêu cầu Boot chạy script tạo metadata Batch nếu auto-configuration áp dụng, phục vụ demo hoặc môi trường test.
- `app.launch.enabled=false`: là property do ứng dụng tự định nghĩa để kiểm soát entry point chạy job trong phần sau.
- `logging.level.org.springframework.batch=INFO`: ghi các thông điệp vận hành Batch ở mức cơ bản.

**Phân biệt cực kỳ quan trọng:** `spring.batch.job.enabled=false` chỉ ngăn **auto-launch lúc khởi động**, không vô hiệu hóa `JobRepository`, `JobLauncher` hoặc khả năng gọi launcher thủ công.

### Không để schema initialize always trong production một cách máy móc

Ở production, nên quản lý metadata schema bằng migration có phiên bản; cấu hình thường là:

```yaml
spring:
  batch:
    jdbc:
      initialize-schema: never
```

Điều kiện: các bảng `BATCH_*` và sequence phải được tạo đúng version trước khi ứng dụng khởi chạy. Script initialize của Boot không phải công cụ di trú lịch sử/schema tùy biến giữa mọi phiên bản; `always` không có nghĩa tự nâng cấp một schema cũ an toàn.

Mật khẩu chỉ nên lấy từ secret manager/biến môi trường, không commit password thật trong YAML. Đối với production, sử dụng tài khoản DB có quyền tối thiểu; quyền tạo bảng chỉ thuộc quá trình migration nếu hệ thống yêu cầu phân tách.

## 8. Để Spring Boot cấu hình JobRepository và JobLauncher

Một application class tối thiểu:

```java
package com.example.batchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BatchDemoApplication.class, args);
    }
}
```

Khi classpath có starter Batch, datasource và transaction manager phù hợp, Spring Boot/Spring Batch có thể tạo và cấu hình các bean hạ tầng như:

- `DataSource`.
- `PlatformTransactionManager`.
- `JobRepository`.
- `JobLauncher`.
- `JobExplorer` và các thành phần cần thiết khác.

Cấu hình auto-configuration phụ thuộc phiên bản, bean đã có trong context và cách kích hoạt Batch. Với cấu hình cơ bản, **không thêm `@EnableBatchProcessing` chỉ vì thấy bài viết cũ hướng dẫn làm vậy**. Trong Spring Boot 3.x, annotation này có thể khiến auto-configuration Batch của Boot nhường quyền cho cấu hình thủ công, làm thay đổi nơi tạo bean và cơ chế khởi tạo schema.

### Kiểm tra bằng dependency injection

Khi ứng dụng khởi động thành công, có thể inject trực tiếp:

```java
@Component
public class BatchInfrastructureInspector {

    private final JobRepository repository;
    private final JobLauncher launcher;

    public BatchInfrastructureInspector(
            JobRepository repository,
            JobLauncher launcher) {

        this.repository = repository;
        this.launcher = launcher;
    }
}
```

Ví dụ chỉ minh họa việc bean sẵn có; trong project chính, không cần tạo inspector riêng để ứng dụng hoạt động. Dùng các bean này trực tiếp trong job configuration và launch service.

Nếu Spring báo `NoSuchBeanDefinitionException` cho repository hoặc launcher, hãy kiểm tra dependency, datasource, transaction manager, điều kiện auto-config và những cấu hình Batch thủ công đã được khai báo.

## 9. Định nghĩa Step có JobRepository và transaction manager

Trong Spring Batch 5.x, builder theo dạng mới nhận `JobRepository` rõ ràng. Với tasklet, transaction manager được truyền khi cấu hình step.

Ví dụ tạo step tổng hợp doanh thu:

```java
package com.example.batchdemo.job;

import java.math.BigDecimal;
import java.sql.Date;
import java.time.LocalDate;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DailySalesJobConfiguration {

    @Bean("dailySalesStep")
    Step dailySalesStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("dailySalesStep", repository)
            .tasklet((contribution, chunkContext) -> {

                String dateText = chunkContext
                    .getStepContext()
                    .getStepExecution()
                    .getJobExecution()
                    .getJobParameters()
                    .getString("businessDate");

                LocalDate businessDate =
                    LocalDate.parse(dateText);

                BigDecimal total = jdbc.queryForObject(
                    """
                    SELECT COALESCE(SUM(amount), 0)
                    FROM sales_order
                    WHERE business_date = ?
                      AND status = 'PAID'
                    """,
                    BigDecimal.class,
                    Date.valueOf(businessDate)
                );

                jdbc.update(
                    """
                    INSERT INTO daily_sales_summary (
                        business_date, total_amount, updated_at
                    )
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (business_date)
                    DO UPDATE SET
                        total_amount = EXCLUDED.total_amount,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    Date.valueOf(businessDate),
                    total
                );

                return RepeatStatus.FINISHED;

            }, transactionManager)
            .build();
    }

    @Bean("dailySalesJob")
    Job dailySalesJob(
            JobRepository repository,
            @Qualifier("dailySalesStep") Step step) {

        return new JobBuilder("dailySalesJob", repository)
            .start(step)
            .build();
    }
}
```

Để dùng nguyên file ví dụ, cần thêm các import:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
```

**Lưu ý:** Ví dụ này dùng SQL PostgreSQL `ON CONFLICT`, phù hợp với database được cấu hình ở phần trước. Với H2, Oracle, SQL Server hoặc MySQL, cú pháp upsert có thể khác.

### Vì sao tasklet ghi lại vẫn không làm nhân đôi tổng doanh thu?

Writer ở ví dụ **upsert theo `business_date`**, không tự động cộng tổng mới vào tổng cũ. Điều này giúp phép tổng hợp đạt tính idempotent ở mức bảng đích đối với cùng snapshot dữ liệu và quy tắc tính.

Tuy nhiên:

- Upsert không có nghĩa mọi side effect của job là idempotent.
- Nếu nguồn thay đổi giữa hai lần reprocess, kết quả có thể đổi; cần version nguồn và quy trình nghiệp vụ rõ ràng.
- Nếu step làm thêm việc gửi email/API ngoài transaction, phải bổ sung idempotency tương ứng.

### Transaction thực sự áp dụng vào đâu?

Trong ví dụ dùng một datasource và transaction manager JDBC, thao tác `JdbcTemplate` nằm trong transaction của tasklet step khi dùng cùng DataSource. Nếu xảy ra exception trước commit, thay đổi bảng nghiệp vụ trong transaction có thể rollback.

Metadata repository cũng có transaction riêng cho các thao tác lifecycle. Đừng suy luận rằng mọi transaction metadata và mọi side effect ngoài DB được gộp thành một transaction duy nhất.

Nếu có datasource riêng cho metadata và datasource riêng cho dữ liệu nghiệp vụ, cần cấu hình đúng transaction manager mỗi nơi và xây dựng chiến lược consistency/recovery; Spring Batch không tự cung cấp distributed transaction cho mọi datasource.

## 10. Tạo JobParameters có danh tính nghiệp vụ ổn định

Với một job chạy theo ngày:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("attemptId", "example-request-001", false)
    .toJobParameters();
```

Tham số `businessDate` là identifying; `attemptId` là non-identifying phục vụ truy vết yêu cầu. Có thể thêm mã file/snapshot, tenant hoặc revision nếu chúng thật sự xác định kỳ xử lý logic.

Không dùng cách sau để “đảm bảo lần nào cũng chạy được”:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addLong("run.id", System.currentTimeMillis())
    .toJobParameters();
```

Vì `run.id` mặc định có thể trở thành identifying, mỗi lần request sẽ tạo instance mới dù vẫn xử lý ngày cũ. Điều này không phải restart, và có thể làm lặp kết quả.

### Phân loại yêu cầu launch

| Trạng thái instance | Cùng identifying parameters | Kết quả điển hình |
| --- | --- | --- |
| Chưa có instance | Gọi lần đầu | Tạo JobInstance và JobExecution mới |
| Có execution `FAILED` | Yêu cầu lại cùng identity | Có thể restart thành JobExecution mới |
| Có execution `STOPPED` | Yêu cầu lại cùng identity | Có thể restart nếu cấu hình cho phép |
| Đang chạy | Yêu cầu lại cùng identity | `JobExecutionAlreadyRunningException` |
| Instance đã `COMPLETED` | Yêu cầu lại cùng identity | `JobInstanceAlreadyCompleteException` |

Những ngoại lệ có thể xuất hiện trước khi một JobExecution mới được tạo. Vì vậy, nếu cần audit mọi **lần cố gắng launch**, ngoài metadata Batch phải lưu riêng launch request hoặc log ở lớp điều phối.

## 11. Khởi chạy job bằng ApplicationRunner

Để thực hành mà không cần mở REST endpoint, chúng ta tạo một entry point CLI. Người vận hành sẽ truyền ngày nghiệp vụ qua argument khi chạy ứng dụng. `ApplicationRunner` chỉ được tạo khi property `app.launch.enabled=true`.

Ví dụ:

```java
package com.example.batchdemo.launch;

import java.time.LocalDate;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DailySalesLaunchConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(DailySalesLaunchConfiguration.class);

    @Bean
    @ConditionalOnProperty(
        prefix = "app.launch",
        name = "enabled",
        havingValue = "true"
    )
    ApplicationRunner launchDailySales(
            JobLauncher jobLauncher,
            @Qualifier("dailySalesJob") Job dailySalesJob,
            @Value("${app.launch.business-date}")
                String businessDateText) {

        return args -> {
            LocalDate date =
                LocalDate.parse(businessDateText);

            JobParameters parameters =
                new JobParametersBuilder()
                    .addString(
                        "businessDate",
                        date.toString(),
                        true
                    )
                    .addString(
                        "attemptId",
                        UUID.randomUUID().toString(),
                        false
                    )
                    .toJobParameters();

            log.info(
                "event=batch.launch.requested job={} date={}",
                dailySalesJob.getName(),
                date
            );

            JobExecution execution =
                jobLauncher.run(dailySalesJob, parameters);

            log.info(
                "event=batch.launch.returned job={} instanceId={} " +
                "executionId={} status={}",
                dailySalesJob.getName(),
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus()
            );
        };
    }
}
```

Property `business-date` chỉ bắt buộc khi bật cơ chế launch. Nếu thiếu hoặc có ngày không hợp lệ, Spring sẽ báo lỗi cấu hình hoặc parsing; người vận hành cần sửa input thay vì tự động đổi sang ngày hiện tại.

### Chạy theo ngày được chỉ định

Sau khi chuẩn bị Postgres, bảng và dữ liệu mẫu, ví dụ lệnh:

```bash
java -jar batch-demo.jar \
  --app.launch.enabled=true \
  --app.launch.business-date=2026-11-15
```

Đây là ví dụ cách truyền arguments tới Spring Boot. Tên file JAR và quy trình build phụ thuộc project thực tế.

Khi launcher chạy **đồng bộ**, `jobLauncher.run(...)` thường chỉ trả về sau khi execution hoàn tất; khi đó trạng thái có thể là `COMPLETED` hoặc `FAILED`. Nếu dùng launcher **bất đồng bộ**, method có thể trả về khi execution đang `STARTING`/`STARTED`. Đừng coi một lời gọi launcher trả về không ném exception là bằng chứng công việc đã thành công.

### Một lần khởi chạy trùng sẽ ra sao?

Nếu gọi cùng ngày `2026-11-15` lần nữa sau khi job đã `COMPLETED`, identifying parameter không đổi nên Spring Batch từ chối. `attemptId` mới là non-identifying, vì vậy nó không “mở khóa” instance cũ.

Trong ví dụ CLI, exception làm entry point báo lỗi. Ở API hoặc scheduler production, nên xử lý ngoại lệ theo outcome nghiệp vụ (đã hoàn tất, đang chạy, không thể restart, tham số sai...) thay vì luôn coi là hệ thống hỏng.

## 12. Dùng JobLauncher trong service và phân loại ngoại lệ

Khi job được gọi qua scheduler, REST API hoặc một orchestration service, nên tập trung code launch ở một service dùng chung. Mẫu sau phân loại những tình huống được Spring Batch hỗ trợ:

```java
import java.time.LocalDate;

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
public class DailySalesLaunchService {

    private final JobLauncher launcher;
    private final Job job;

    public DailySalesLaunchService(
            JobLauncher launcher,
            @Qualifier("dailySalesJob") Job job) {

        this.launcher = launcher;
        this.job = job;
    }

    public LaunchOutcome launch(LocalDate businessDate) {
        JobParameters params = new JobParametersBuilder()
            .addString(
                "businessDate",
                businessDate.toString(),
                true
            )
            .toJobParameters();

        try {
            JobExecution execution =
                launcher.run(job, params);

            return new LaunchOutcome(
                "ACCEPTED",
                execution.getId()
            );

        } catch (JobInstanceAlreadyCompleteException ex) {
            return new LaunchOutcome("ALREADY_COMPLETED", null);

        } catch (JobExecutionAlreadyRunningException ex) {
            return new LaunchOutcome("ALREADY_RUNNING", null);

        } catch (JobRestartException ex) {
            return new LaunchOutcome("RESTART_REJECTED", null);

        } catch (JobParametersInvalidException ex) {
            return new LaunchOutcome("INVALID_PARAMETERS", null);

        } catch (Exception ex) {
            // Có lỗi hạ tầng; không tự khẳng định không có
            // JobExecution nào đã được ghi xuống repository.
            throw new IllegalStateException(
                "Unable to confirm launch outcome", ex
            );
        }
    }

    public record LaunchOutcome(
        String status,
        Long executionId) {
    }
}
```

Các chuỗi `ACCEPTED`, `ALREADY_COMPLETED`, `RESTART_REJECTED` là mã do ứng dụng định nghĩa; chúng không phải `BatchStatus`. Một execution được chấp nhận vẫn có thể kết thúc ở `FAILED`.

Đối với API, không nên để một endpoint chạy job tự do trên Internet. Cần xác thực, phân quyền người vận hành, giới hạn tốc độ, audit và kiểm soát nguồn input. Ví dụ CLI trong bài giảm bề mặt tấn công và giúp tập trung vào hạ tầng Batch.

**Tránh đặt `@Transactional` bao quanh cả lời gọi `JobLauncher.run(...)` một cách thiếu cân nhắc.** Việc tạo JobExecution có transaction và chính sách cô lập riêng; Spring Batch có thể từ chối khởi tạo job trong một transaction gọi bên ngoài đang hoạt động, hoặc gây tương tác transaction khó đoán. Nếu cần lưu audit launch, ghi yêu cầu trước trong transaction ngắn, commit, rồi gọi launcher.

## 13. Các bảng JobRepository sau khi chạy

Sau khi chạy job, dữ liệu nghiệp vụ:

```sql
SELECT
    business_date,
    total_amount,
    updated_at
FROM daily_sales_summary
ORDER BY business_date;
```

Với dữ liệu mẫu, mong đợi:

```text
business_date  | total_amount
---------------+-------------
2026-11-15     | 155000.00
```

Để xem metadata:

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'dailySalesJob'
ORDER BY je.JOB_EXECUTION_ID;
```

Một JobInstance có thể xuất hiện nhiều dòng nếu từng restart. Đây là dấu hiệu nhiều JobExecution thuộc cùng instance, không phải nhất thiết nhiều kỳ dữ liệu.

Xem tham số của execution:

```sql
SELECT
    je.JOB_EXECUTION_ID,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_EXECUTION_PARAMS p
    ON p.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
ORDER BY je.JOB_EXECUTION_ID, p.PARAMETER_NAME;
```

Với Batch 5.x, các cột `PARAMETER_NAME`/`PARAMETER_TYPE`/`PARAMETER_VALUE`/`IDENTIFYING` là mô hình metadata tương ứng. Không dùng câu SQL dựa trên tên cột của Batch 5 cho schema Batch 4 chưa nâng cấp.

Xem chi tiết các step:

```sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID;
```

Trong ví dụ tasklet, `READ_COUNT` và `WRITE_COUNT` không phải số dòng `sales_order` được SQL aggregate xử lý. Các counter này chủ yếu có ý nghĩa trực tiếp với chunk-oriented step sử dụng `ItemReader`/`ItemWriter`. Nếu cần biết chính xác số đơn hợp lệ, hãy tính trong SQL nghiệp vụ hoặc lưu metric riêng.

## 14. Dùng JobExplorer để đọc lịch sử qua Java API

Đối với dashboard hoặc công cụ vận hành, nên dùng API `JobExplorer` để đọc metadata thay vì luôn truy vấn trực tiếp các bảng `BATCH_*`.

Ví dụ:

```java
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.explore.JobExplorer;

public class BatchHistoryService {

    private final JobExplorer explorer;

    public BatchHistoryService(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public List<JobExecution> executions(
            String jobName,
            JobParameters params) {

        JobInstance instance =
            explorer.getJobInstance(jobName, params);

        if (instance == null) {
            return List.of();
        }

        return explorer.getJobExecutions(instance);
    }
}
```

Khi hiển thị lịch sử, nên phân biệt:

- `JobInstance ID`: một kỳ xử lý logic.
- `JobExecution ID`: một lần thử.
- `BatchStatus`: tình trạng vòng đời.
- `ExitStatus`: kết quả có thể có mã nghiệp vụ tùy biến.
- Thời điểm bắt đầu/kết thúc và các StepExecution.
- Các identifying parameters đã sử dụng.

Không tự sửa `STATUS` trong repository bằng SQL để ép restart. Nếu một process chết đột ngột khiến metadata vẫn `STARTED`, cần quy trình recovery được kiểm chứng, xác nhận process cũ không còn chạy và kiểm tra dữ liệu đích trước khi khởi động lại.

## 15. Synchronous và asynchronous JobLauncher

Spring Batch có implementation `TaskExecutorJobLauncher`, sử dụng một `TaskExecutor` để thực thi job. Hành vi đồng bộ hay bất đồng bộ phụ thuộc executor mà launcher sử dụng.

### 15.1. Đồng bộ

Nếu launcher dùng `SyncTaskExecutor`:

```text
Caller thread
     |
     v
JobLauncher.run()
     |
  Job steps
     |
     v
JobExecution kết thúc
     |
     v
run() trả về
```

Đặc điểm:

- Lời gọi `run()` chiếm thread gọi trong suốt thời gian xử lý.
- Đơn giản cho CLI hoặc smoke test.
- Không phù hợp nếu HTTP request phải chờ một job chạy nhiều giờ.
- Exception trong step thường được Spring Batch phản ánh qua trạng thái JobExecution; không mặc định ném ra cho caller dưới dạng exception giống thao tác gọi method thông thường.

### 15.2. Bất đồng bộ

Nếu launcher dùng `ThreadPoolTaskExecutor` hoặc executor bất đồng bộ:

```text
HTTP / Scheduler thread
          |
          v
    JobLauncher.run()
          |
          +----> Trả JobExecution sớm
          |
          +----> Worker executor
                       |
                    Chạy steps
                       |
                    Job finished
```

Đặc điểm:

- Caller nhận execution ID rồi truy vấn trạng thái sau.
- Cần điều chỉnh thread pool, queue capacity và hạn mức chạy song song.
- Phải kiểm soát shutdown để tránh dừng đột ngột job.
- Không được ghi “job thành công” chỉ vì `run()` đã trả về.
- Phải có cơ chế giám sát kết quả cuối qua JobExecution/JobListener/JobExplorer.

Ví dụ **một cách cấu hình thủ công launcher** khi quản lý Batch infrastructure riêng:

```java
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;

import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;

public JobLauncher createLauncher(
        JobRepository repository,
        TaskExecutor executor) throws Exception {

    TaskExecutorJobLauncher launcher =
        new TaskExecutorJobLauncher();

    launcher.setJobRepository(repository);
    launcher.setTaskExecutor(executor);
    launcher.afterPropertiesSet();

    return launcher;
}

// executor = new SyncTaskExecutor()       -> đồng bộ
// executor = một ThreadPoolTaskExecutor  -> bất đồng bộ
```

Đây là **minh họa phần lắp ghép launcher**, không phải code cần thêm vào dự án đã dùng Boot auto-configuration. Nếu tự đăng ký bean `JobLauncher` trong context hiện có, phải kiểm tra auto-configuration/bean naming và bảo đảm chỉ có launcher mà từng caller thực sự cần. Không tạo hai bean cùng tên hoặc để dependency injection mơ hồ.

Trong production, một HTTP endpoint nên trả về mã request/execution phù hợp (ví dụ HTTP 202 khi đã tiếp nhận) và cung cấp API xem trạng thái; cần bảo mật và giới hạn concurrency.

## 16. Khi nào cần cấu hình JobRepository thủ công?

Cấu hình Boot mặc định phù hợp cho nhiều trường hợp một datasource và một transaction manager. Cấu hình thủ công có thể cần khi:

- Metadata Batch lưu trong database riêng với dữ liệu nghiệp vụ.
- Có nhiều datasource và cần chọn chính xác datasource dành cho JobRepository.
- Cần tiền tố bảng metadata khác `BATCH_`.
- Cần tinh chỉnh isolation khi tạo JobExecution để xử lý cạnh tranh launch trên nhiều node.
- Cần serializer/transaction settings phù hợp chính sách vận hành.
- Ứng dụng không dùng Spring Boot auto-configuration hoặc tích hợp Batch trong một hệ thống Spring tùy biến.

Có **hai hướng cấu hình hạ tầng**, cần chọn một và thực hiện nhất quán.

### Hướng A — Spring Boot auto-configuration

Trong dự án thực hành này, chỉ cần cấu hình datasource và để Spring Boot tạo hạ tầng Batch. Đây là hướng nên dùng trước nếu không có nhu cầu đặc biệt.

**Không đặt `@EnableBatchProcessing` lên application class chỉ để “bật Batch”.** Spring Boot 3.x với starter và datasource phù hợp đã có khả năng tự cấu hình.

### Hướng B — Spring Batch infrastructure thủ công

Có thể dùng `@EnableBatchProcessing` với datasource và transaction manager được chọn rõ ràng:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing(
    dataSourceRef = "batchDataSource",
    transactionManagerRef = "batchTransactionManager"
)
public class ManualBatchInfrastructureConfiguration {

    @Bean("batchTransactionManager")
    PlatformTransactionManager batchTransactionManager(
            @Qualifier("batchDataSource")
                DataSource batchDataSource) {

        return new DataSourceTransactionManager(batchDataSource);
    }
}
```

Để cấu hình trên thực sự dùng được, ứng dụng phải **có bean `batchDataSource`** với cấu hình JDBC phù hợp; ví dụ cố ý không tự tạo datasource thứ hai từ thông tin kết nối tùy ý. Cần bổ sung import `Qualifier`:

```java
import org.springframework.beans.factory.annotation.Qualifier;
```

Khi dùng hạ tầng thủ công, kiểm tra điều kiện kích hoạt và cơ chế khởi tạo schema: Boot có thể không còn quản lý metadata initialization như ở cấu hình mặc định. Lúc đó migrations cho Batch tables và transaction manager phải được thiết lập chủ động.

Có thể đi sâu hơn bằng `JobRepositoryFactoryBean`, `TaskExecutorJobLauncher` hoặc mở rộng `DefaultBatchConfiguration` khi thực sự cần custom table prefix, isolation hoặc serializer. Nhưng mỗi lựa chọn đều yêu cầu xem xét cách tạo bean và tương tác với Boot; **không dùng đồng thời nhiều cơ chế cấu hình hạ tầng mà không kiểm soát bean trùng lặp**.

## 17. Nhiều datasource: metadata và nghiệp vụ không nhất thiết nằm cùng DB

Trong ứng dụng doanh nghiệp, có thể cần:

```text
                   JobLauncher
                        |
                        v
               JobRepository
                        |
                 batchDataSource
                        |
              DB_A: BATCH_* tables

                       Job/Step
                        |
                   businessDataSource
                        |
           DB_B: sales_order, summary
```

Điều này có lợi cho phân quyền và tách tải, nhưng ảnh hưởng tới transaction:

- Metadata repository dùng transaction manager của DB_A.
- Step nghiệp vụ dùng transaction manager của DB_B.
- Giao dịch commit ở DB_B không mặc nhiên commit atomically với metadata ở DB_A.
- Khi có crash ở ranh giới giữa hai bên, kết quả nghiệp vụ và trạng thái metadata có thể tạm không nhất quán.

Để thiết kế an toàn:

1. Ưu tiên writer idempotent theo khóa nghiệp vụ.
2. Không lưu dữ liệu quan trọng chỉ trong in-memory counter.
3. Có cơ chế reconciliation theo business key và JobExecution ID.
4. Sử dụng outbox hoặc các mô hình đảm bảo chuyển trạng thái phù hợp khi liên quan hệ thống khác.
5. Có lịch sử audit và quy trình vận hành khôi phục sau crash.

Không mặc định thêm hai `DataSource` và hai `TransactionManager` là đủ để có distributed transaction. Nếu thật sự cần atomicity xuyên database, đó là quyết định kiến trúc riêng với chi phí và giới hạn tương ứng.

## 18. Isolation, lock và nhiều launcher cùng chạy

Giả sử có hai pod cùng phát trigger cho `dailySalesJob` với `businessDate=2026-11-15`:

```text
Pod A                         Pod B
  |                             |
  +-- run(job, date=D)           +-- run(job, date=D)
             \                    /
              \                  /
                Shared JobRepository
                         |
               Cùng JobInstance identity
                         |
          Một execution hợp lệ / request
          còn lại có thể bị từ chối
```

Repository sử dụng transaction và cơ chế database để phối hợp tạo JobInstance/JobExecution khi có nhiều request đồng thời. Nhưng không phải cứ chia sẻ repository là ứng dụng đã có **scheduler leader** hoặc khóa phân tán cho mọi tình huống.

Phân biệt:

- **Chống tạo execution trùng cho cùng JobInstance**: trách nhiệm của repository và database metadata.
- **Chỉ phát một trigger trên toàn cluster**: trách nhiệm của scheduler hoặc distributed lock.
- **Không ghi dữ liệu nghiệp vụ trùng khi retry/restart**: trách nhiệm transaction, writer và idempotency.

Cấu hình isolation khi tạo execution có thể quan trọng với database/khối lượng launch lớn. Không nên giảm isolation hoặc tắt khóa chỉ để xóa một lỗi cạnh tranh mà chưa hiểu hậu quả. Hãy kiểm tra khả năng tương thích với database và load test tình huống concurrent launch.

Nếu một node bị kill trong lúc job chạy, metadata có thể vẫn ở trạng thái `STARTED` và ngăn request restart. Khi đó phải xác minh node cũ không còn chạy, đối soát dữ liệu và xử lý execution treo theo quy trình được hỗ trợ; không sửa thẳng cột STATUS trong database chỉ để bỏ qua kiểm soát.

## 19. Lưu metadata bền vững và chính sách cleanup

`JobRepository` cần database tồn tại qua lần khởi động ứng dụng:

- Với local smoke test, H2 in-memory có thể phù hợp.
- Với môi trường staging/production, nên dùng PostgreSQL hay database tương đương có backup, monitoring và migration.
- Không dùng in-memory repository/datasource cho job cần restart sau khi process chết.
- Xác định retention của metadata, backup/restore và chính sách cleanup cho lịch sử JobExecution.

Khi metadata quá lớn sau nhiều tháng, có thể cần archive/purge có kiểm soát. Việc xóa metadata tùy tiện có thể làm hỏng quan hệ JobInstance → JobExecution → StepExecution và các execution context.

**Không xóa JobRepository để chạy lại một instance `COMPLETED`.** Nếu cần tái xử lý dữ liệu đã hoàn tất, phải tạo JobInstance mới với revision/version nghiệp vụ rõ ràng, đồng thời có chiến lược ghi đích và audit.

## 20. Kiểm thử JobRepository và JobLauncher

Kiểm thử tầng infrastructure nên chứng minh:

1. Ứng dụng có bean `JobRepository` và `JobLauncher`.
2. Launcher tạo JobInstance/JobExecution khi có identifying parameters mới.
3. Metadata được đọc lại từ JobRepository/JobExplorer.
4. Cùng tham số sau khi job `COMPLETED` bị từ chối.
5. Hai kỳ dữ liệu khác nhau tạo hai JobInstance khác nhau.
6. Nếu execution trước `FAILED` và job hỗ trợ restart, có thể tạo execution mới trong cùng instance.

Để tập trung vào hạ tầng, integration test có thể sử dụng H2 với một job tasklet rất đơn giản, không phụ thuộc cú pháp PostgreSQL `ON CONFLICT` của job nghiệp vụ.

### 20.1. Cấu hình test

Dùng profile test hoặc properties của `@SpringBootTest`:

```java
@SpringBootTest(properties = {
    "spring.batch.job.enabled=false",
    "spring.batch.jdbc.initialize-schema=always",
    "spring.datasource.url=jdbc:h2:mem:batch_infra_test;DB_CLOSE_DELAY=-1",
    "spring.datasource.driver-class-name=org.h2.Driver",
    "spring.datasource.username=sa",
    "spring.datasource.password="
})
```

H2 giúp test nhanh luồng metadata, nhưng **không thay thế integration test trên PostgreSQL** cho các câu SQL nghiệp vụ, isolation, connection pool hoặc cách database xử lý concurrency.

### 20.2. Một test độc lập cho Batch infrastructure

```java
package com.example.batchdemo;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;

import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = {
    "spring.batch.job.enabled=false",
    "spring.batch.jdbc.initialize-schema=always",
    "spring.datasource.url=jdbc:h2:mem:batch_infra_test;DB_CLOSE_DELAY=-1",
    "spring.datasource.driver-class-name=org.h2.Driver",
    "spring.datasource.username=sa",
    "spring.datasource.password="
})
@Import(BatchInfrastructureTest.SmokeJobConfiguration.class)
class BatchInfrastructureTest {

    @Autowired
    private JobRepository repository;

    @Autowired
    private JobLauncher launcher;

    @Autowired
    private JobExplorer explorer;

    @Autowired
    @Qualifier("smokeJob")
    private Job smokeJob;

    @Test
    void repositoryAndLauncherWorkTogether() throws Exception {
        assertNotNull(repository);
        assertNotNull(launcher);

        JobParameters firstParams = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .addString("requestId", "req-1", false)
            .toJobParameters();

        JobExecution first =
            launcher.run(smokeJob, firstParams);

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertNotNull(first.getId());
        assertNotNull(first.getJobInstance());

        JobExecution loaded =
            explorer.getJobExecution(first.getId());

        assertNotNull(loaded);
        assertEquals(BatchStatus.COMPLETED, loaded.getStatus());

        // requestId đổi nhưng non-identifying:
        // đây vẫn là JobInstance đã COMPLETED.
        JobParameters duplicateParams =
            new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .addString("requestId", "req-2", false)
                .toJobParameters();

        assertThrows(
            JobInstanceAlreadyCompleteException.class,
            () -> launcher.run(smokeJob, duplicateParams)
        );

        JobExecution anotherDay = launcher.run(
            smokeJob,
            new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .toJobParameters()
        );

        assertEquals(
            BatchStatus.COMPLETED,
            anotherDay.getStatus()
        );

        assertNotEquals(
            first.getJobInstance().getInstanceId(),
            anotherDay.getJobInstance().getInstanceId()
        );
    }

    @TestConfiguration
    static class SmokeJobConfiguration {

        @Bean("smokeStep")
        Step smokeStep(
                JobRepository repository,
                PlatformTransactionManager txManager) {

            return new StepBuilder("smokeStep", repository)
                .tasklet((contribution, context) ->
                    RepeatStatus.FINISHED, txManager)
                .build();
        }

        @Bean("smokeJob")
        Job smokeJob(
                JobRepository repository,
                @Qualifier("smokeStep") Step smokeStep) {

            return new JobBuilder("smokeJob", repository)
                .start(smokeStep)
                .build();
        }
    }
}
```

Test này tập trung vào ba hành vi: **tạo metadata**, **từ chối chạy lại instance đã completed**, và **tạo instance khác khi business key thay đổi**.

Cần cô lập database giữa các lần chạy/suite nếu test khác cũng dùng tên job và identifying parameters giống nhau. Trong một bộ test lớn có thể dùng database mới theo test, tên JobInstance riêng, hoặc công cụ dọn metadata trên **database test** theo quy trình có kiểm soát.

### 20.3. Test failure và restart

Một test bổ sung nên cho tasklet ném exception trong lần đầu rồi thành công lần hai với cùng identifying parameters.

Kỳ vọng:

```text
First launch:
  JobInstance ID = 101
  JobExecution ID = 9001
  Status = FAILED

Second launch, same identifying parameters:
  JobInstance ID = 101
  JobExecution ID = 9002
  Status = COMPLETED

Third launch, same identifying parameters:
  JobInstanceAlreadyCompleteException
```

Khi test, cần xác nhận JobInstance ID giữ nguyên, JobExecution ID khác nhau, kết quả nghiệp vụ không bị nhân đôi và metadata StepExecution phản ánh đúng trạng thái.

Nếu `JobLauncher` được cấu hình bất đồng bộ, test không nên assert `COMPLETED` ngay sau lời gọi `run()`; hãy chờ trạng thái cuối theo cách có timeout và cơ chế đồng bộ test.

## 21. Các lỗi cấu hình phổ biến

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không có bean `JobRepository` | Starter/datasource/auto-config thiếu hoặc bị override | Kiểm tra dependencies và điều kiện auto-configuration |
| Không có bean `JobLauncher` | Hạ tầng Batch chưa khởi tạo đầy đủ | Kiểm tra cấu hình Batch, repository, transaction manager |
| Job tự chạy khi ứng dụng startup | Boot auto-run được bật | Cấu hình `spring.batch.job.enabled=false` nếu muốn launch chủ động |
| Bảng `BATCH_JOB_INSTANCE` không tồn tại | Metadata schema chưa khởi tạo | Tạo schema đúng version, migration hoặc initialize-schema trong demo |
| Lỗi do bảng metadata không cùng version | Dùng script Batch 4 với Batch 5 | Cập nhật schema theo migration chính thức |
| Job chạy xong nhưng không restart được | Instance đã `COMPLETED` | Phân biệt restart và reprocess có version |
| Mỗi lần launch tạo instance mới | Timestamp/`run.id` là identifying | Sử dụng business key ổn định, trace ID non-identifying |
| Job bị từ chối vì đang chạy | Có execution hoạt động hoặc metadata treo | Đối soát state, tránh trigger trùng, xử lý crash đúng quy trình |
| `@EnableBatchProcessing` thêm vào làm Boot config thay đổi | Trộn auto và manual infrastructure | Chọn một cơ chế cấu hình nhất quán |
| Nhiều `TransactionManager` gây inject mơ hồ | Không chọn manager cho repository/step | Dùng qualifier và cấu hình rõ datasource |
| Metadata ở DB_A, nghiệp vụ ở DB_B sai lệch | Không có atomic transaction xuyên DB | Idempotency, reconciliation, outbox khi cần |
| `JobLauncher.run()` trả về nhưng job vẫn chạy | Launcher dùng executor bất đồng bộ | Theo dõi JobExecution/JobExplorer sau launch |
| Step `FAILED` nhưng caller không gặp exception | Failure được ghi thành BatchStatus | Kiểm tra status/exit code, không chỉ try/catch |
| Dữ liệu ngày D bị tổng hợp hai lần | Writer không idempotent hoặc tạo instance mới tùy tiện | Upsert/unique key và chính sách reprocess |
| Test chạy được trên H2 nhưng production lỗi | SQL dialect/isolation khác PostgreSQL | Integration test với DB tương thích production |
| Job chạy đa node gây contention | Các launcher cùng gửi cùng identity | Repository dùng chung, orchestration/lock, kiểm soát concurrency |
| Metadata mất sau deploy | Dùng database tạm/in-memory | Dùng DB bền vững và migration/backup |
| Không thể truy vết ai launch | Chỉ dùng JobExecution metadata | Log/audit launch attempt với source, request ID |
| Password DB xuất hiện trong repository/config | Lưu secret không an toàn | Dùng secret manager/env var và log redaction |

## 22. Các lựa chọn thiết kế cho production

Một hệ thống production không chỉ cần job “chạy được”; còn cần phục hồi, vận hành và kiểm soát dữ liệu.

### 22.1. Metadata database bền vững

Dùng PostgreSQL hoặc database được Spring Batch hỗ trợ, có backup, migration và giám sát. Xác định rõ ai được cấp quyền đọc/ghi/cập nhật schema.

### 22.2. Quy tắc danh tính JobInstance

Chọn identifying parameters theo business key, ví dụ `businessDate`, `sourceSnapshotId` hoặc `revision`. Không thêm timestamp identifying cho mọi lần chạy theo phản xạ.

### 22.3. Launcher và scheduler

Một ứng dụng nhiều pod có thể có nhiều scheduler phát trigger. Dùng JobRepository chung để phối hợp metadata, nhưng nếu cần đúng một trigger trên toàn cluster thì bổ sung cơ chế leader election, Quartz hoặc distributed lock phù hợp.

### 22.4. Idempotent writer và checkpoint

Các step ghi dữ liệu phải có transaction, unique key hoặc thiết kế outbox/idempotency khi có side effect ngoài transaction. Các reader cần lưu checkpoint khi restart là yêu cầu quan trọng; trong bài dùng tasklet ngắn để tập trung hạ tầng.

### 22.5. Audit và quan sát

Ghi job name, business key, request ID, JobInstance ID, JobExecution ID, trạng thái cuối, elapsed time và nguyên nhân failure. Phân biệt launch attempt với JobExecution: một yêu cầu bị từ chối có thể không tạo execution mới.

### 22.6. Quản lý schema

Đặt metadata và business schema vào quy trình migration. Không dùng `initialize-schema=always` như một cơ chế nâng cấp sản xuất giữa mọi version của Spring Batch.

### 22.7. Kiểm soát tài nguyên

Nếu dùng async launcher hoặc partitioning, giới hạn thread pool, queue capacity, connection pool, memory và số job chạy song song. Thêm timeout và cảnh báo cho execution tồn tại bất thường quá lâu.

## 23. Bài tập mở rộng

Sau khi hoàn thành ứng dụng demo, hãy mở rộng theo các nhiệm vụ:

1. Tạo `dailySalesJob` đọc doanh thu từ bảng `sales_order` và upsert vào `daily_sales_summary`.
2. Khởi chạy ngày D bằng `JobLauncher`, ghi nhận `JobInstance ID` và `JobExecution ID`.
3. Khởi chạy lại đúng ngày D sau khi job `COMPLETED`; quan sát ngoại lệ và giải thích vì sao không tạo execution mới.
4. Đổi `businessDate` sang D+1, xác minh có JobInstance khác.
5. Giả lập lỗi lần chạy đầu để job `FAILED`; sửa lỗi rồi launch lại cùng ngày, xác nhận JobExecution mới thuộc instance cũ.
6. Kiểm tra trạng thái/exit code qua `JobExplorer` và bằng câu SQL read-only trên metadata.
7. Chuyển launcher sang executor bất đồng bộ trong cấu hình riêng, thử quan sát `STARTING`/`STARTED`, sau đó mới `COMPLETED`.
8. Tạo hai yêu cầu launch đồng thời cho cùng identity; xác định outcome cho từng yêu cầu và kiểm tra dữ liệu đích không nhân đôi.
9. Thử cấu hình metadata trên một datasource riêng; mô tả transaction manager cho repository và cho step.
10. Viết một báo cáo ngắn về lý do chọn Boot auto-configuration hoặc manual configuration cho hệ thống thật của bạn.

### Kết quả cần ghi lại

| Lần thử | Business date | JobInstance ID | JobExecution ID | Outcome | Dữ liệu đích |
| --- | --- | --- | --- | --- | --- |
| Chạy ngày D lần đầu | D | Instance A | Execution A1 | `COMPLETED` | Một dòng tổng hợp |
| Chạy lại ngày D | D | Instance A | Không có execution mới | `ALREADY_COMPLETED` | Không đổi |
| Chạy ngày D+1 | D+1 | Instance B | Execution B1 | `COMPLETED` | Thêm kỳ mới |
| Lần đầu lỗi | D2 | Instance C | Execution C1 | `FAILED` | Theo transaction |
| Restart sau lỗi | D2 | Instance C | Execution C2 | `COMPLETED` | Kết quả đúng, không trùng |

Các ID trong bảng là tên đại diện. Khi thực hành, thay bằng ID thật từ metadata Spring Batch.

## 24. Tổng kết

Trong dự án Spring Batch, **`JobRepository` và `JobLauncher` là hai phần hạ tầng gắn chặt với nhau nhưng có trách nhiệm khác biệt**. Repository lưu danh tính JobInstance, trạng thái JobExecution/StepExecution và checkpoint; launcher nhận job cùng parameters, quyết định khởi chạy theo dữ liệu metadata và giao thực thi cho executor.

Với Spring Boot 3.x và Spring Batch 5.x, hướng thực hành đơn giản là cấu hình PostgreSQL, để Boot tự tạo hạ tầng, định nghĩa `Job`/`Step` bằng builder có `JobRepository` và `PlatformTransactionManager`, rồi gọi `JobLauncher.run(...)` từ entry point được kiểm soát. Khi cần cấu hình thủ công, phải chủ động quản lý datasource, transaction manager, metadata schema và bean wiring.

Để ứng dụng đủ tin cậy cho vận hành, hãy giữ identifying JobParameters ổn định theo nghiệp vụ, phân biệt restart với instance mới, quan sát trạng thái qua metadata, kiểm tra các kịch bản concurrent launch và bảo đảm writer idempotent. Cấu hình đúng không chỉ giúp job chạy được mà còn giúp **restart an toàn, điều tra được và tránh ghi trùng dữ liệu**.
