# Kiểm thử tích hợp Batch, sự kiện và lỗi hạ tầng

Trong chương **Kiểm thử** của module **SPRING_CLOUD_TASK**, một ứng dụng chạy hữu hạn thường không đứng một mình. Nó được scheduler hoặc API khởi chạy, thực hiện một **Spring Batch Job**, ghi kết quả nghiệp vụ vào database, cập nhật `TaskRepository` rồi có thể phát thông tin qua **Spring Cloud Stream**. Khi tất cả thành phần đều hoạt động, một bài thử thành công rất dễ viết. Khó hơn là chứng minh hệ thống xử lý đúng khi một thành phần **không hoạt động**, phản hồi bị mất hoặc JVM bị dừng trước lúc ghi nhận kết thúc.

Mục tiêu của kiểm thử tích hợp không phải chỉ kiểm tra phương thức `process()` trả đúng giá trị. Cần kiểm tra **đường đi thực sự của dữ liệu và metadata** qua Spring Cloud Task, Spring Batch, transaction, JDBC, event broker và bộ điều phối. Đồng thời phải phân biệt: một test chạy được trong cùng Spring `ApplicationContext` **chưa chứng minh** mã thoát JVM và sự kiện kết thúc của một tiến trình độc lập được ghi chính xác.

Bài này giới thiệu chiến lược theo tầng, ví dụ Spring Batch 5.x với PostgreSQL Testcontainers, kiểm thử contract message bằng Spring Cloud Stream Test Binder, và kịch bản end-to-end dùng **tiến trình Java riêng** cùng Kafka/bộ điều phối. Các ví dụ chọn Spring Boot 3.x, Spring Batch 5.x và bản Spring Cloud Task tương thích; cần điều chỉnh khi dùng Spring Batch 6.x hoặc một release train khác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Chọn đúng lớp kiểm thử cho logic nghiệp vụ, `JobExecution`, `TaskExecution`, event và runtime.
- Sử dụng `@SpringBatchTest`, `JobLauncherTestUtils` và `JobRepositoryTestUtils` của **Spring Batch 5.x** trong bài tích hợp.
- Kiểm tra cả `BatchStatus`, `ExitStatus`, `StepExecution` và **kết quả đã commit**, không chỉ một dòng log.
- Thử cấu hình `spring.cloud.task.batch.fail-on-job-failure=true` để lỗi Batch được phản ánh ở tầng Task/process.
- Phân biệt `task-events` với `job-execution-events`; thử cả **message contract** và **broker thật**.
- Sử dụng Testcontainers để kiểm tra hành vi thực tế của PostgreSQL, khóa duy nhất, transaction và Kafka.
- Thiết kế test cho mất kết nối DB/broker, lỗi bootstrap, timeout, SIGKILL và commit không rõ kết quả.
- Đánh giá retry/idempotency, thiếu sự kiện cuối, metadata chưa hoàn tất và các quy tắc phân loại trạng thái `UNKNOWN`.
- Xây dựng test matrix và tiêu chí chạy trong CI với dữ liệu cô lập, timeout hữu hạn và bằng chứng đầy đủ.

## 2. Những gì một bài kiểm thử cần chứng minh

Trong ứng dụng Spring Cloud Task tích hợp Batch và event, có ít nhất bốn lớp kết quả khác nhau:

| Lớp | Nguồn sự thật chính | Kiểm tra tối thiểu |
| --- | --- | --- |
| **Nghiệp vụ** | Bảng/file/API đầu ra | Dữ liệu đúng, đủ, không trùng, đã commit hoặc đã được xác nhận |
| **Spring Batch** | `JobRepository`, `JobExecution`, `StepExecution` | `BatchStatus`, `ExitStatus`, read/write/skip count, restart |
| **Spring Cloud Task** | `TaskRepository`, `TaskExecution` | Một lần thực thi, start/end, exit code/message, liên kết với Batch khi được cấu hình |
| **Runtime và sự kiện** | Process/pod, broker, consumer và scheduler | Exit code hệ điều hành, event nhận được, retry/timeout/duplicate |

Ví dụ một Job Batch thất bại nhưng process vẫn thoát với mã `0` nếu không có cơ chế phản ánh lỗi Batch sang Task phù hợp. Ngược lại, process có thể thoát lỗi sau khi bảng nghiệp vụ đã ghi thành công. Vì vậy, **một assertion không thể thay thế những assertion còn lại**.

~~~mermaid
flowchart TD
    A["Bộ điều phối khởi chạy Task"] --> B["Spring Boot / Spring Cloud Task"]
    B --> C["Spring Batch Job / Step"]
    C --> D["Database nghiệp vụ"]
    C --> E["JobRepository: JobExecution / StepExecution"]
    B --> F["TaskRepository: TaskExecution"]
    B --> G["Spring Cloud Stream: task-events"]
    C --> H["Spring Cloud Stream: job/step events"]
    G --> I["Kafka / Consumer"]
    H --> I
    D --> J["Bộ assertion tích hợp"]
    E --> J
    F --> J
    I --> J
    A --> J
~~~

**Không đồng nhất các repository**: `TaskRepository` theo dõi vòng đời ứng dụng Task; `JobRepository` theo dõi Job/Step và checkpoint của Batch. Hai repository có thể dùng chung một database nhưng vẫn lưu những loại metadata khác nhau.

## 3. Ma trận kiểm thử tích hợp nhiều tầng

Chia bài kiểm thử thành những nhóm có mục tiêu rõ:

| Nhóm | Công cụ hoặc môi trường | Cần chứng minh | Điều chưa đủ để chứng minh |
| --- | --- | --- | --- |
| Unit test | JUnit 5, Mockito hoặc fake service | Validation, mapping, idempotency policy | JDBC commit/broker hoạt động |
| Batch integration | `@SpringBatchTest` + PostgreSQL | Job/Step status, transaction, dữ liệu nghiệp vụ | Mã thoát của **JVM riêng** |
| Event contract | Spring Cloud Stream Test Binder | Consumer parse đúng payload, binding và schema | Kafka ACL, network, retry/redelivery thực |
| Broker integration | Kafka Testcontainers | Producer ↔ topic ↔ consumer thực sự tương tác | Task hoàn tất nghiệp vụ nếu không kiểm tra DB |
| Process end-to-end | `ProcessBuilder`/container Job chạy JAR thật | Bootstrap, auto-config, exit code, `TaskExecution` | Điều kiện nghiệp vụ nếu chỉ xem exit code |
| Fault injection | Proxy mạng, kill process, tạm ngắt broker/database | Không treo vô hạn, trạng thái UNKNOWN, retry/idempotency | Chính xác nếu chỉ sleep tùy tiện |

Một bộ CI hiệu quả thường chạy **unit và Batch integration** trên mỗi commit; các test Kafka/process/fault injection có thể dùng pipeline riêng nếu thời gian và hạ tầng lớn hơn. Nhưng những đường lỗi quan trọng vẫn phải được thực thi định kỳ trước khi phát hành.

## 4. Chuẩn bị bài toán demo và các bất biến

Giả sử có một Spring Cloud Task xử lý báo cáo cho `businessKey=shop-01|2026-11-24`. Spring Batch chỉ có một Step ghi nhận kết quả vào bảng `daily_import`. Task có thể được chạy lại do scheduler/Job retry, nhưng không được tạo hàng trùng cho cùng business key.

### 4.1. Bất biến nghiệp vụ

- **Một business key tạo tối đa một kết quả**, kể cả khi hai tiến trình cùng chạy.
- Cùng key + cùng đầu vào → lần thử sau trả kết quả đã có, không phát sinh side effect mới.
- Cùng key + dữ liệu đầu vào khác → báo conflict theo policy, không âm thầm ghi đè.
- Job Batch thất bại trước commit → không có hàng kết quả của attempt đó.
- Khi mất phản hồi commit → trạng thái caller là **chưa biết**, phải đọc lại DB trước khi retry mù.
- Metadata Batch/Task và broker chỉ được dùng để đối soát quá trình chạy, không thay thế kiểm tra kết quả nghiệp vụ.

### 4.2. Bảng dùng trong bài học

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE daily_import (
    business_key VARCHAR(160) PRIMARY KEY,
    result       VARCHAR(32) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Khóa chính `business_key` là cơ chế chặn ghi trùng **ở database**, không phải chỉ kiểm tra `SELECT` trước `INSERT`. Script tạo bảng trên thuộc **schema nghiệp vụ**, tách khỏi các bảng `TASK_EXECUTION` và `BATCH_JOB_EXECUTION` do framework quản lý.

### 4.3. Ranh giới transaction

Trong ví dụ, một Step theo dạng tasklet ghi một hàng vào PostgreSQL. Dữ liệu ghi và trạng thái Job/Step sẽ được kiểm tra qua các nguồn riêng. Không mặc định việc tạo `TaskExecution` và transaction của Step là **một transaction nguyên tử duy nhất**, kể cả khi các bảng cùng nằm trong một database.

## 5. Các dependency và phiên bản

Bài thử bên dưới lấy **Spring Batch 5.x** làm baseline. Khi dùng Spring Boot 3.x, dự án cần Spring Boot parent/BOM và Spring Cloud BOM **tương thích**; không trộn tùy tiện phiên bản Boot, Task, Stream và Batch.

Dependency Maven chính:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.batch</groupId>
        <artifactId>spring-batch-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Để **kiểm thử Spring Cloud Stream events** ở những mục sau, bổ sung các dependency tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Các module Spring Cloud Task/Stream phụ trợ cho việc phát event có thể cần thêm tùy release train; hãy xác minh **dependency tree và auto-configuration thực tế**. Test Binder nằm trong test scope để không vô tình thay Kafka binder của ứng dụng production.

Dùng `spring-boot-maven-plugin` để tạo JAR thực thi nếu chạy bài test process end-to-end. Không pin một chuỗi version độc lập trong ví dụ này; phiên bản thực tế phải được quản lý thống nhất bởi BOM của dự án.

**Phiên bản Testcontainers:** các artifact `org.testcontainers:junit-jupiter` và `org.testcontainers:postgresql` cùng package `org.testcontainers.containers.PostgreSQLContainer` trong ví dụ là cách dùng của **Testcontainers 1.x** (chẳng hạn dòng 1.21.x). Từ **Testcontainers 2.x**, artifact đổi thành `testcontainers-junit-jupiter` và `testcontainers-postgresql`, đồng thời một số package/class API đã thay đổi. Nếu BOM của dự án quản lý Testcontainers 2.x, hãy dùng dependency và import đúng tài liệu 2.x; đừng trộn artifact 1.x với version 2.x.

> **Khác biệt quan trọng:** Ở Spring Batch **5.x**, `@SpringBatchTest` cung cấp `JobLauncherTestUtils`. Từ Spring Batch **6.x**, tài liệu chuyển sang `JobOperatorTestUtils` và API có thay đổi. Không dùng nguyên tên class/builder ví dụ 5.x với dự án 6.x mà chưa đối chiếu tài liệu.

## 6. Ứng dụng mẫu: một Job và một Step có thể gây lỗi

Tạo `src/main/java/com/example/task/DailyImportTaskApplication.java`:

~~~java
package com.example.task;

import java.util.Map;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class DailyImportTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(DailyImportTaskApplication.class, args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    Job dailyImportJob(JobRepository jobRepository, Step importStep) {
        return new JobBuilder("dailyImportJob", jobRepository)
                .start(importStep)
                .build();
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("importStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    Map<String, Object> params =
                            chunkContext.getStepContext().getJobParameters();

                    Object keyValue = params.get("businessKey");
                    if (!(keyValue instanceof String businessKey)
                            || businessKey.isBlank()) {
                        throw new IllegalArgumentException(
                                "businessKey phải là chuỗi không rỗng");
                    }

                    boolean failDemo = Boolean.parseBoolean(
                            String.valueOf(params.get("failDemo")));

                    if (failDemo) {
                        throw new IllegalStateException(
                                "DEMO_UPSTREAM_FAILURE");
                    }

                    // PostgreSQL: phép ghi idempotent có khóa duy nhất.
                    jdbc.update("""
                        INSERT INTO daily_import (business_key, result)
                        VALUES (?, 'DONE')
                        ON CONFLICT (business_key) DO NOTHING
                        """, businessKey);

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }
}
~~~

### Giải thích

- `Job` tên `dailyImportJob` có một `Step` tên `importStep`.
- `JobParameters.businessKey` là khóa nghiệp vụ ổn định.
- `failDemo` tạo lỗi **trước khi ghi dữ liệu**, chỉ để kiểm tra đường thất bại.
- `ON CONFLICT DO NOTHING` là cú pháp PostgreSQL, **không phải SQL chung cho mọi DB**.
- `StepBuilder.tasklet(..., transactionManager)` là dạng API của Spring Batch **5.x**. Trong một hệ thống nhiều datasource, transaction manager của Step phải được chọn đúng nguồn ghi nghiệp vụ.
- `SpringApplication.exit(context)` nhằm cho phép cơ chế exit code của Boot/Task được áp dụng; phải chạy **tiến trình riêng** mới kiểm tra được exit code hệ điều hành.
- Ví dụ không thêm `ApplicationRunner` tự gọi `JobLauncher` vì Spring Boot/Task có thể tự chạy `Job` khi được cấu hình; thêm cả hai có thể khiến Job chạy hai lần.

Dùng `spring.cloud.task.batch.fail-on-job-failure=true` khi cần Batch failure được phản ánh thành Task exit code khác `0` theo khả năng phiên bản đang dùng.

### Cấu hình production-like

~~~yaml
spring:
  application:
    name: daily-import-task
  main:
    web-application-type: none

  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: never

  cloud:
    task:
      name: daily-import-task
      initialize-enabled: false
      batch:
        fail-on-job-failure: true
~~~

Cấu hình này giả định database đã có **schema Batch + Task phù hợp version**, và bảng `daily_import` đã được migration. Trong production, tránh để mỗi process tự động tạo lại các bảng schema.

## 7. Kiểm thử tích hợp Batch với PostgreSQL Testcontainers

Một unit test dùng mock `JdbcTemplate` có thể kiểm tra method được gọi, nhưng **không chứng minh** PostgreSQL đã commit hoặc ràng buộc unique có tác dụng. Với test tích hợp, dùng PostgreSQL Testcontainers để có database thực mà không phụ thuộc database chia sẻ giữa các developer.

### 7.1. Cấu hình test

Ví dụ sau áp dụng **Spring Batch 5.x**. Tạo `src/test/java/com/example/task/DailyImportBatchIT.java`:

~~~java
package com.example.task;

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
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBatchTest
@Testcontainers
@SpringBootTest(
        classes = DailyImportTaskApplication.class,
        properties = {
            "spring.batch.job.enabled=false",
            "spring.batch.jdbc.initialize-schema=always",
            "spring.cloud.task.initialize-enabled=true",
            "spring.cloud.task.events.enabled=false",
            "spring.cloud.task.batch.events.enabled=false"
        })
class DailyImportBatchIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JobLauncherTestUtils launcher;

    @Autowired
    JobRepositoryTestUtils batchCleaner;

    @Autowired
    Job dailyImportJob;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void setUp() {
        launcher.setJob(dailyImportJob);

        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS daily_import (
                business_key VARCHAR(160) PRIMARY KEY,
                result VARCHAR(32) NOT NULL
            )
            """);

        batchCleaner.removeJobExecutions();
        jdbc.update("DELETE FROM daily_import");
    }

    @Test
    void jobHoanTatVaGhiDuLieu() throws Exception {
        JobExecution job = launcher.launchJob(
                params("shop-01|2026-11-24", "attempt-1", false));

        assertEquals(BatchStatus.COMPLETED, job.getStatus());
        assertEquals("COMPLETED", job.getExitStatus().getExitCode());
        assertEquals(1, count("shop-01|2026-11-24"));
    }

    @Test
    void jobThatBaiKhongGhiDuLieu() throws Exception {
        JobExecution job = launcher.launchJob(
                params("shop-02|2026-11-24", "attempt-fail", true));

        assertEquals(BatchStatus.FAILED, job.getStatus());
        assertEquals(0, count("shop-02|2026-11-24"));
    }

    @Test
    void retryVoiCungBusinessKeyKhongTaoTrung() throws Exception {
        JobExecution first = launcher.launchJob(
                params("shop-03|2026-11-24", "attempt-1", false));

        JobExecution second = launcher.launchJob(
                params("shop-03|2026-11-24", "attempt-2", false));

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertEquals(1, count("shop-03|2026-11-24"));
    }

    private int count(String businessKey) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM daily_import WHERE business_key=?",
                Integer.class, businessKey);
    }

    private static JobParameters params(
            String key, String attemptId, boolean failDemo) {
        return new JobParametersBuilder()
                .addString("businessKey", key, true)
                .addString("attemptId", attemptId, true)
                .addString("failDemo",
                        Boolean.toString(failDemo), false)
                .toJobParameters();
    }
}
~~~

### 7.2. Những gì test trên đã kiểm tra

- Spring tạo `Job`, `Step`, transaction manager, Batch repository và JDBC datasource thực.
- `JobLauncherTestUtils.launchJob(...)` thực thi Job trong **Spring test context** rồi trả `JobExecution`.
- Trường hợp thành công có `BatchStatus.COMPLETED`, `ExitStatus.COMPLETED` và **một row đã commit**.
- Trường hợp lỗi giả lập trả `BatchStatus.FAILED` và không ghi row.
- Hai lần launch với cùng `businessKey` nhưng khác `attemptId` tạo **hai JobInstance/attempt độc lập theo identifying parameters**; unique key giữ lại đúng một kết quả.

**Điểm quan trọng về Spring Batch:** nếu dùng **cùng bộ identifying `JobParameters`** cho một JobInstance đã hoàn tất, Batch có thể từ chối launch lại với `JobInstanceAlreadyCompleteException`. Ví dụ dùng `attemptId` là identifying parameter **chỉ để mô phỏng hai lần chạy độc lập cùng business key**. Khi cần kiểm thử **restart đúng một JobInstance**, phải giữ bộ identifying parameters và sử dụng cơ chế restart/chính sách JobRepository thích hợp, không tự tạo instance mới rồi gọi đó là restart.

`@SpringBatchTest` không tự xác minh `TaskExecution` của một JVM độc lập. Spring test context có vòng đời khác process do scheduler khởi tạo; phần kiểm tra Task exit code thuộc nhóm process end-to-end.

### 7.3. Lưu ý về cách cô lập test

- Dùng container riêng hoặc schema riêng, không xóa bảng của database ngoài test.
- `JobRepositoryTestUtils.removeJobExecutions()` chỉ làm sạch metadata **Batch**; không xóa bảng nghiệp vụ hay `TASK_EXECUTION`.
- Không gắn `@Transactional` một cách mặc định lên toàn bộ test nếu điều đó che kết quả commit của Step; đọc lại database **sau** khi job hoàn tất.
- Tránh chạy song song test cùng database/JobParameters nếu không có isolation.
- Kích hoạt schema bằng `initialize-schema=always` trong **test**, không suy ra đây là policy production.
- Đối với dự án Spring Batch **6.x**, chuyển ví dụ sang `JobOperatorTestUtils` và các API đúng phiên bản.

## 8. Kiểm tra dữ liệu StepExecution và liên kết Batch–Task

Ngoài `BatchStatus`, bài test có thể kiểm tra Step đã thật sự chạy:

~~~java
assertEquals(1, job.getStepExecutions().size());

var step = job.getStepExecutions().iterator().next();
assertEquals("importStep", step.getStepName());
assertEquals(BatchStatus.COMPLETED, step.getStatus());
~~~

Trong một Job chỉ có một tasklet Step, không nhất thiết có read/write count như chunk-oriented step. Nếu chuyển sang `ItemReader`/`ItemWriter`, hãy kiểm tra thêm `readCount`, `writeCount`, `skipCount` và checkpoint `ExecutionContext` khi restart.

Spring Cloud Task có thể liên kết một `JobExecution` với `TaskExecution` khi tính năng Task–Batch được cấu hình đúng (bao gồm listener và dependency tích hợp thích hợp). **Không tự suy ra rằng chỉ thêm `spring-batch-test` sẽ tạo liên kết này**.

Có thể kiểm chứng từ các bảng metadata trong môi trường chạy JAR thực:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC;
~~~

~~~sql
SELECT JOB_EXECUTION_ID,
       JOB_INSTANCE_ID,
       STATUS,
       EXIT_CODE,
       START_TIME,
       END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

Liên kết Task–Batch có thể được lưu qua bảng mapping riêng trong schema Spring Cloud Task theo phiên bản. Hãy dùng schema/SQL chính thức tương ứng, thay vì giả định mỗi bảng có cột join trực tiếp. Một `JobExecution` thành công không tự chứng minh process đã thoát thành công hoặc event được broker nhận.

## 9. Kiểm thử sự kiện: contract khác broker integration

Theo tài liệu Spring Cloud Task, với Spring Cloud Stream và binder phù hợp, listener có thể phát `TaskExecution` ở lúc **bắt đầu** và **kết thúc** qua binding logic `task-events`. Tích hợp Batch có các luồng event như `job-execution-events`, `step-execution-events` và `chunk-events` khi được cấu hình.

Phải phân biệt **hai loại bài test**:

| Test | Cách thực hiện | Có thể kết luận |
| --- | --- | --- |
| **Consumer contract** | Đưa payload test vào Spring Cloud Stream Test Binder | Consumer parse, validate và xử lý đúng kiểu message |
| **Producer/broker/process integration** | Chạy JAR thật, Kafka thật trong Testcontainers, consumer đọc topic | Task listener và binder thực sự phát message tới broker, consumer thực sự nhận |
| **Reliability/failure** | Mất kết nối broker, kill JVM, redelivery | Ứng dụng ứng xử ra sao khi sự kiện thiếu, trễ hoặc lặp |

Một contract test giả lập message **không đủ** để tuyên bố rằng Spring Cloud Task đã phát hai sự kiện vòng đời thành công qua Kafka.

### 9.1. Cấu hình destination

Producer:

~~~yaml
spring:
  cloud:
    task:
      events:
        enabled: true
      batch:
        events:
          enabled: true
    stream:
      bindings:
        task-events:
          destination: it.task.lifecycle
          contentType: application/json
        job-execution-events:
          destination: it.batch.jobs
          contentType: application/json
~~~

`task-events` và `job-execution-events` là **binding output** của tích hợp Task/Batch trong cấu hình tương ứng. Khi chạy với Kafka, chúng trỏ tới các topic `it.task.lifecycle` và `it.batch.jobs`. Cần có binder trên classpath và cấu hình broker. Những tên topic trên chỉ dùng cho môi trường test.

Để cô lập lỗi:

~~~properties
spring.cloud.task.events.enabled=false
spring.cloud.task.batch.events.enabled=false
~~~

Công tắc đầu tắt **Task lifecycle events**, công tắc sau tắt **Batch events**; không tương đương việc tắt `TaskRepository` hoặc `JobRepository`.

## 10. Ví dụ kiểm thử consumer contract bằng Test Binder

Spring Cloud Stream cung cấp Test Binder để thử consumer mà **không cần Kafka thật**. Dưới đây là một bài test tối giản, sử dụng một function `Consumer<Message<byte[]>>`; payload được đọc như JSON text để tránh phụ thuộc vào class Java nội bộ của producer.

~~~java
package com.example.task;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.beans.factory.annotation.Autowired;

@SpringBootTest(
        classes = TaskEventConsumerContractIT.TestApp.class,
        properties = {
            "spring.cloud.function.definition=captureTask",
            "spring.cloud.stream.bindings.captureTask-in-0.destination=it.task.lifecycle",
            "spring.cloud.stream.bindings.captureTask-in-0.contentType=application/octet-stream",
            "spring.cloud.task.autoconfiguration.enabled=false",
            "spring.batch.job.enabled=false"
        })
@EnableTestBinder
class TaskEventConsumerContractIT {

    @Autowired
    InputDestination input;

    @Autowired
    BlockingQueue<String> captured;

    @Test
    void consumerNhanDuocJsonPayload() throws Exception {
        String json = """
            {"executionId":42,"taskName":"daily-import-task",
             "exitCode":0,"endTime":"2026-11-24T01:00:00Z"}
            """;

        input.send(
                new GenericMessage<>(
                        json.getBytes(StandardCharsets.UTF_8)),
                "it.task.lifecycle");

        String received = captured.poll(3, TimeUnit.SECONDS);
        assertNotNull(received);
        assertTrue(received.contains("\"executionId\":42"));
        assertTrue(received.contains("\"taskName\":\"daily-import-task\""));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {

        @Bean
        BlockingQueue<String> captured() {
            return new LinkedBlockingQueue<>();
        }

        @Bean
        Consumer<Message<byte[]>> captureTask(
                BlockingQueue<String> captured) {
            return message -> captured.add(
                    new String(
                            message.getPayload(),
                            StandardCharsets.UTF_8));
        }
    }
}
~~~

Đây là **contract test của consumer**, không tự kích hoạt `TaskExecutionListener`. Payload JSON được cung cấp trực tiếp bởi test; nó chỉ minh họa những trường thường cần cho dashboard. Khi triển khai, nên thay phép kiểm chuỗi bằng kiểm tra JSON schema/DTO đã được chốt theo **payload thật** mà version Spring Cloud Task phát ra.

Nếu converter trong version Stream cụ thể xử lý payload không phải `byte[]`, hãy sử dụng `Message<String>` hoặc cấu hình content type tương ứng và kiểm tra thực tế. Không ép consumer runtime giả định `TaskExecution` mọi version đều có biểu diễn JSON giống ví dụ.

## 11. Kiểm thử end-to-end sự kiện với Kafka thật

Để chứng minh **producer Task** phát event đến broker, nên có test cấp tiến trình:

1. Khởi động Kafka bằng **Testcontainers** hoặc môi trường Kafka riêng cho integration test.
2. Tạo topic riêng (ví dụ `it.task.lifecycle`, `it.batch.jobs`) theo chính sách test.
3. Tạo Kafka consumer với group riêng, `auto.offset.reset=earliest` và chuẩn bị đọc trước hoặc cùng lúc launch.
4. Chạy **JAR Spring Cloud Task trong process khác**, trỏ cả JDBC và Kafka binder đến container.
5. Đợi process kết thúc với deadline hữu hạn; thu exit code và stdout/stderr.
6. Đọc topic với timeout, lọc theo `executionId`/`runId`, so sánh event bắt đầu/kết thúc.
7. Truy vấn bảng `TASK_EXECUTION` và `BATCH_JOB_EXECUTION` để đối chiếu nội dung event.
8. Kiểm tra consumer xử lý được duplicate, reordering và trạng thái thiếu end event.

**Đừng chỉ chạy `@SpringBootTest` và chờ sự kiện tự xuất hiện sau khi test method bắt đầu.** Listener startup có thể đã phát event từ lúc context khởi tạo; nếu consumer được tạo quá muộn, test có thể bỏ lỡ sự kiện hoặc phụ thuộc offset/retention.

Ví dụ cấu hình đầu vào cho JAR test:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/task_it
spring.datasource.username=task_it
spring.datasource.password=from-test-secret
spring.cloud.stream.bindings.task-events.destination=it.task.lifecycle
spring.cloud.stream.bindings.job-execution-events.destination=it.batch.jobs
spring.cloud.stream.kafka.binder.brokers=localhost:9092
spring.cloud.task.events.enabled=true
spring.cloud.task.batch.events.enabled=true
spring.cloud.task.batch.fail-on-job-failure=true
~~~

Các địa chỉ/credential trên là **giá trị minh họa**. Khi dùng Testcontainers, host/port thực tế do container runtime cấp động; chương trình test phải truyền **đúng mapped endpoints** vào tiến trình con. Cần kiểm tra Kafka `advertised.listeners` và thiết lập TLS/SASL nếu môi trường yêu cầu.

### 11.1. Nhận dạng event bắt đầu và kết thúc

Khi event chứa dữ liệu về cùng một `TaskExecution`, có thể kiểm tra:

- Cùng `executionId`/task name phù hợp với record trong DB.
- Event bắt đầu có dữ liệu nhận diện lần chạy; metadata kết thúc có thể chưa có.
- Event hoàn tất có `endTime`/`exitCode` theo cách serializer của phiên bản đã chọn biểu diễn.
- Có thể có **hai thông điệp trở lên** liên quan cùng execution ID; không được deduplicate chỉ theo execution ID và làm mất event cuối.
- Không giả định thứ tự giữa **hai topic khác nhau** (Task và Batch) được bảo đảm toàn cục.

Với một run bình thường và điều kiện broker ổn định, kiểm thử có thể kỳ vọng đủ hai mốc. Nhưng **mất event cuối là kịch bản phải được kiểm thử riêng**, không phải lý do đánh dấu ứng dụng chưa từng chạy.

### 11.2. Tại sao cần Kafka Testcontainers?

Test Binder không kiểm tra được:

- Producer authentication và topic ACL.
- Kết nối network, timeout, retry và advertised listeners.
- Serialization thực tế qua Kafka binder.
- Consumer group, offset, partition và redelivery sau restart.
- Tác động khi producer JVM đóng quá nhanh trước khi message được gửi/ack theo cấu hình.

Vì vậy, dùng Test Binder cho **contract nhanh**, Kafka thật cho **khả năng tương tác thực tế**.

## 12. Lỗi hạ tầng: ma trận kịch bản cần thử

Không phải mọi lỗi đều có thể tái hiện bằng cách cho mock ném exception. Một số lỗi chỉ xuất hiện ở boundary transaction/network/process:

| Kịch bản | Cách tạo lỗi trên môi trường test | Bằng chứng cần xác minh |
| --- | --- | --- |
| DB chưa sẵn sàng khi JVM khởi động | Cố tình chặn JDBC endpoint trước bootstrap | Process fail/timeout đúng, có log hạ tầng; TaskExecution có thể chưa tồn tại |
| Thiếu schema Task/Batch | Tắt khởi tạo schema trên DB trống | Lỗi rõ, không được báo success |
| DB mất kết nối trong Step | Proxy ngắt kết nối JDBC ở thời điểm ghi | Transaction và Job status theo thực tế; không tạo dữ liệu sai |
| Mất phản hồi sau COMMIT | Fault injection tại boundary hoặc mô phỏng caller mất ACK sau commit | Retry cùng business key không tạo row thứ hai |
| Broker chưa sẵn sàng | Chặn Kafka endpoint hoặc ACL | Phân loại lỗi publish/consumer; không tự suy ra mọi message đã gửi |
| Consumer bị ngừng | Stop consumer, rồi khởi động lại khi retention còn dữ liệu | Đọc lại theo offset/group, không xử lý trùng |
| JVM bị SIGKILL | Kill process đúng lúc đang làm việc | Có thể thiếu end event/END_TIME; runtime và business DB giúp đối soát |
| Task vượt deadline | Kill/cancel qua scheduler với timeout hữu hạn | Phân biệt TIMEOUT/UNKNOWN; giải quyết retry an toàn |
| Hai process cùng business key | Chạy đồng thời hai JAR/Job | Ràng buộc unique không cho kết quả trùng |
| Upstream trả 429/503 | Stub API, Toxiproxy hoặc môi trường giả lập | Retry/backoff có giới hạn, không nhân số lần gọi quá mức |

**Cảnh báo:** không gây lỗi mạng, kill tiến trình hoặc xóa bảng trên môi trường có người dùng thật. Kiểm thử fault injection phải sử dụng tài nguyên cô lập, có thời hạn, tài khoản riêng và lệnh phục hồi.

## 13. Trường hợp commit không xác định và idempotent retry

Một exception quanh `COMMIT` có thể xuất hiện **sau khi database đã ghi thay đổi** nhưng trước khi ứng dụng nhận phản hồi. Vì thế:

~~~text
SQLException / connection reset  !=  chắc chắn transaction rollback
~~~

Ví dụ test theo hai nhánh:

- **Nhánh A:** lỗi được tạo **trước khi commit**, dữ liệu chưa được lưu → retry cùng key được phép ghi lần đầu.
- **Nhánh B:** dữ liệu đã commit rồi test cố tình làm caller “mất phản hồi” → retry cùng key phải đọc hoặc ghi idempotent và **không tạo thêm kết quả**.

Nhánh B có thể được mô phỏng trong một test có kiểm soát: thực hiện commit thật, chủ động trả exception giả lập cho caller, sau đó launch lại cùng business key. Đây là kiểm tra **chính sách retry khi kết quả không rõ**, **không thay thế** kiểm thử lỗi mạng thật ngay trong giao thức `COMMIT`.

Trong PostgreSQL, một unique key kết hợp `INSERT ... ON CONFLICT DO NOTHING` ngăn tạo row trùng. Nhưng nếu cùng key chứa payload khác, phải kiểm tra fingerprint và báo conflict thay vì trả success giả. Với nghiệp vụ ghi nhiều bảng hoặc tác động ngoài DB, thiết kế transaction/outbox/idempotency phải được kiểm tra ở từng ranh giới.

### Quy trình ra quyết định khi kết quả chưa rõ

~~~mermaid
flowchart TD
    A["Mất kết nối / JVM crash / task timeout"] --> B["Lấy business key từ request"]
    B --> C{"Có thể kiểm tra nguồn dữ liệu chính?"}
    C -->|"Không"| D["UNKNOWN, backoff và cảnh báo"]
    C -->|"Có"| E["Đọc dữ liệu đã commit theo key"]
    E --> F{"Có đúng kết quả?"}
    F -->|"Có"| G["Đã xử lý: không tạo tác động mới"]
    F -->|"Có nhưng khác dữ liệu"| H["CONFLICT: điều tra"]
    F -->|"Chưa có"| I["Thực hiện thao tác idempotent với cùng key"]
    I --> J["Xác minh lại DB / broker / file"]
    J --> G
~~~

`TaskRepository` là **nguồn quan sát bổ sung**, không phải nguồn duy nhất để quyết định liệu dữ liệu nghiệp vụ đã commit.

## 14. Kiểm thử process exit code và lỗi bootstrap

`@SpringBatchTest` chỉ chạy Job trong một Spring `ApplicationContext` của quá trình test. Nó không mô phỏng đầy đủ việc mở một JVM mới và hệ điều hành nhận exit code. Vì vậy cần **process-level integration test**.

Một harness Java có thể sử dụng `ProcessBuilder`:

~~~java
ProcessBuilder builder = new ProcessBuilder(
        "java",
        "-jar", "target/daily-import-task.jar",
        "--businessKey=shop-01|2026-11-24",
        "--attemptId=process-it-1",
        "--failDemo=true");

builder.environment().put("TASK_DB_URL", jdbcUrlFromTestContainer);
builder.environment().put("TASK_DB_USER", testDbUsername);
builder.environment().put("TASK_DB_PASSWORD", testDbPassword);
builder.redirectErrorStream(true);

Process child = builder.start();

// Một reader riêng phải drain stdout/stderr để tránh deadlock
// nếu buffer pipe đầy trong lúc chờ process.
boolean finished = child.waitFor(90, TimeUnit.SECONDS);
if (!finished) {
    child.destroy();
    if (!child.waitFor(5, TimeUnit.SECONDS)) {
        child.destroyForcibly();
    }
    throw new AssertionError("Task vượt timeout kiểm thử");
}
int exitCode = child.exitValue();
~~~

Đây là **khung minh họa**, chưa phải một test class độc lập có đủ imports, đọc log và cleanup. Với process thật, bắt buộc:

1. Dùng đường dẫn JAR đã được build, không giả định JAR sẽ có ngay khi Maven chạy unit tests.
2. Draining stdout/stderr **đồng thời** hoặc chuyển hướng đến file log trong thư mục test riêng.
3. Không log giá trị `TASK_DB_PASSWORD` hoặc secret Kafka.
4. Ghi nhận exit code, PID, thời lượng, log và DB sau khi process dừng.
5. Có timeout tổng, dọn process/container khi test lỗi.
6. Phân biệt **non-zero exit do lỗi Batch**, **non-zero exit do bootstrap**, **timeout** và **SIGKILL**.

### 14.1. Assertions cho ba trường hợp

| Trường hợp | Exit code process | Task metadata | Kết quả nghiệp vụ |
| --- | --- | --- | --- |
| Job thành công | Kỳ vọng `0` theo policy | Có record hoàn tất khi JDBC sẵn sàng | Có row đúng |
| Batch Job FAILED | Kỳ vọng khác `0` nếu `fail-on-job-failure=true` được hỗ trợ/cấu hình đúng | Có mã lỗi, có thể có thông tin thất bại | Không có dữ liệu sai/được ghi dở |
| Lỗi ApplicationContext rất sớm | Thường khác `0` | **Có thể không có record** vì hạ tầng Task chưa hoạt động | Tùy lỗi, không được tự suy luận |

Một test chỉ assert `exitCode != 0` cho trường hợp lỗi **chưa đủ**; nó có thể pass vì JAR thiếu dependency, classpath sai hoặc không kết nối được database, chứ không phải do Batch Job thất bại như dự định. Hãy kiểm tra **log/error code và trạng thái Job trong DB** để xác nhận đúng nguyên nhân.

## 15. Batch failure, Task failure và sự kiện phải được đối chiếu

Theo tài liệu Spring Cloud Task, khi Spring Batch Job kết thúc với `BatchStatus.FAILED`, hành vi mã thoát Task phụ thuộc chính sách tích hợp; đặt:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

để Spring Cloud Task hỗ trợ chuyển thất bại Batch sang mã thoát khác `0` ở phiên bản tương ứng.

Test cần kiểm tra **ba kết quả khác nhau**:

1. `BATCH_JOB_EXECUTION.STATUS = FAILED` và `EXIT_CODE` phù hợp.
2. `TASK_EXECUTION.EXIT_CODE` cùng exit code hệ điều hành phản ánh thất bại theo cấu hình.
3. Event `job-execution-events`/`task-events` nhận được trạng thái hợp lý **khi việc publish thành công**.

Không nên kết luận Batch Job đã chạy thành công chỉ từ việc có `task-events` lúc kết thúc. Task event và Batch event có phạm vi khác nhau, và thứ tự message trên **hai topic** không nhất thiết được bảo đảm.

### Chú ý thứ tự listener

Spring Cloud Task cung cấp các callback `onTaskStartup`, `onTaskFailed`, `onTaskEnd`. Chúng được gọi quanh thao tác ghi metadata; callback xảy ra **không phải bằng chứng transaction lưu metadata sau đó đã commit**. Nếu cần giám sát toàn bộ sự cố, phải kết hợp log/runtime, repository và broker.

## 16. Đánh giá sự kiện thiếu, lặp, đến trễ và sai thứ tự

Sự kiện là thông báo, không phải một giao dịch phân tán bảo đảm tuyệt đối. Trong môi trường bất ổn:

- Task phát sự kiện **bắt đầu** nhưng JVM chết trước khi phát sự kiện **kết thúc**.
- Event đã được broker nhận nhưng producer không nhận ACK; khi retry có thể phát **lặp**.
- Consumer restart và đọc lại một offset, xử lý lại event.
- Event kết thúc đến consumer trước event bắt đầu nếu dữ liệu qua nhiều topic/partition hoặc hệ thống chuyển tiếp không bảo toàn thứ tự toàn cục.
- Task hoàn tất nhưng message bị lỗi serialize, sai destination hoặc thiếu quyền publish.

### Một bảng dữ liệu quan sát ở consumer

~~~sql
CREATE TABLE task_event_observation (
    execution_id BIGINT NOT NULL,
    lifecycle_phase VARCHAR(20) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (execution_id, lifecycle_phase)
);
~~~

Đây là **bảng nghiệp vụ của hệ thống quan sát**, không phải bảng do Spring Cloud Task tạo. `lifecycle_phase` có thể là `START` hoặc `END` theo quy tắc parser đã được kiểm chứng; payload framework có thể không mang field phase sẵn. Nếu nhận lại cùng key/phase và cùng hash, consumer có thể bỏ qua. Nếu cùng key/phase nhưng hash khác, cần xác định có event cập nhật hợp lệ hay conflict.

Không deduplicate chỉ theo `execution_id`, vì như thế có thể loại bỏ event kết thúc sau khi đã nhận event bắt đầu. Khi event kết thúc vắng mặt quá một khoảng thời gian, đối chiếu TaskRepository và scheduler trước khi kết luận task vẫn còn chạy.

## 17. Tổ chức CI và làm sạch dữ liệu kiểm thử

Một bộ tích hợp tốt phải có kết quả tái lập, không chỉ pass trên máy tác giả.

### 17.1. Phân nhóm pipeline

| Giai đoạn | Mục tiêu | Tần suất đề xuất |
| --- | --- | --- |
| Unit/contract | Validation, mapping, message schema | Mỗi commit |
| Batch + PostgreSQL Testcontainers | SQL, transaction, unique key, status | Mỗi PR hoặc mỗi commit |
| Kafka + process E2E | Start/end event, TaskRepository, exit code, binder thật | Pipeline tích hợp |
| Fault injection | Crash, timeout, DB/broker unavailable, uncertain commit | Trước release hoặc định kỳ |
| Staging smoke | Artifact, secrets, broker ACL, schema, deployer thật | Mỗi bản triển khai |

### 17.2. Nguyên tắc cô lập

- Mỗi test dùng **business key riêng**; dữ liệu phải được cleanup hoặc nằm trong container có vòng đời rõ ràng.
- Tránh `Thread.sleep` cố định để chờ Kafka/process; dùng polling có deadline và message condition.
- Cấp port/container động, không mặc định `localhost:5432` hoặc `9092` luôn rảnh.
- Không dùng token hoặc DB production trong test.
- Lưu log, container output, `TaskExecution` và `JobExecution` để điều tra test thất bại; lọc secret.
- Test bị fail phải dọn tài nguyên của chính nó, không xóa schema của test đang chạy song song.
- Chia test có thể chạy song song và test cần exclusive resource; đừng tạo race ngẫu nhiên giữa các case.
- Thử cả kết nối từ **JVM của test** và từ **JVM con** vì Docker networking/host port có thể khác.

### 17.3. Bằng chứng khi test fail

Một báo cáo integration test nên lưu:

~~~text
testCase=postgresCommitReplyLost
requestId=it-20261124-007
attemptId=2
businessKey=shop-01|2026-11-24
processExit=1
batchStatus=FAILED
taskExitCode=1|UNKNOWN
businessRows=1
receivedTaskEvents=1
reconciliation=ALREADY_APPLIED
~~~

Đây là **ví dụ về định dạng báo cáo**, không phải kết quả chạy thực tế. Trường `UNKNOWN` không phải lỗi cần giấu; nó nói rõ một nguồn dữ liệu chưa cung cấp đủ bằng chứng, trong khi dữ liệu nghiệp vụ có thể đã tồn tại.

## 18. Checklist nghiệm thu

- [ ] Có ít nhất một test Batch thành công và một test Batch thất bại trên JDBC thực.
- [ ] Kiểm tra `JobExecution`/`StepExecution` **và** dữ liệu đã commit.
- [ ] Retry cùng business key không tạo bản ghi trùng; đã kiểm tra cả concurrency nếu có.
- [ ] Đã kiểm tra version `@SpringBatchTest` và utility tương ứng (5.x/6.x).
- [ ] Có test consumer contract bằng Test Binder hoặc test converter tương đương.
- [ ] Có test Kafka thật: đúng binding, destination, group, payload và broker.
- [ ] Không coi event start/end là bằng chứng duy nhất của thành công nghiệp vụ.
- [ ] Có test process riêng để xác minh exit code và lỗi bootstrap.
- [ ] Có tình huống DB/broker mất kết nối, timeout hoặc SIGKILL trong môi trường cô lập.
- [ ] Với commit không rõ, hệ thống thực hiện đối soát trước khi retry mù.
- [ ] Có deadline/backoff trong test; không phụ thuộc sleep cố định hoặc thứ tự ngẫu nhiên.
- [ ] Không đưa secret/PII vào log kiểm thử hoặc message được thu thập.
- [ ] Bảng Task/Batch được tạo bằng schema đúng phiên bản; không dùng chung tài nguyên production.
- [ ] Kết quả test cho biết chính xác lỗi ở tầng nào: Batch, Task, broker, runtime hay nghiệp vụ.

## 19. Câu hỏi và bài tập

**Câu hỏi 1.** Một `@SpringBatchTest` trả `BatchStatus.COMPLETED`. Điều này đã chứng minh JVM chạy bằng `java -jar` sẽ trả exit code `0` và Kafka nhận hai event Task chưa? Vì sao?

**Câu hỏi 2.** Vì sao test dùng `JobLauncherTestUtils` với identifying parameters giống hệt một JobInstance đã hoàn thành có thể bị từ chối? Khác biệt với retry toàn bộ Task là gì?

**Câu hỏi 3.** Khi Kafka consumer nhận event bắt đầu nhưng không nhận event kết thúc, điều đó có đủ chứng minh Task vẫn chạy không? Cần kiểm tra ở đâu?

**Câu hỏi 4.** Một connection reset xảy ra ngay lúc database `COMMIT`. Tại sao kiểm thử chỉ mock `JdbcTemplate.update(...)` ném exception là không đủ để đánh giá tính an toàn của retry?

**Câu hỏi 5.** Spring Batch 6.x thay đổi utility kiểm thử nào so với ví dụ Spring Batch 5.x ở bài này?

**Bài tập A — Batch và rollback.** Sửa `importStep` để ghi một hàng rồi ném exception **trong cùng transaction**. Chứng minh transaction rollback với PostgreSQL và giải thích khác biệt khi transaction manager bị cấu hình sai.

**Bài tập B — Process-level exit code.** Đóng gói JAR rồi chạy thành công và `--failDemo=true` bằng `ProcessBuilder`. Thu exit code, JobExecution và TaskExecution; không được chỉ nhìn log để kết luận.

**Bài tập C — Kafka thật.** Dùng Kafka Testcontainers, chạy task có event listener, đọc `task-events` và `job-execution-events`. Tạo assertion cho identity của lần chạy và khả năng consumer parse payload.

**Bài tập D — Broker outage.** Tạm làm broker không truy cập được khi Task bắt đầu hoặc kết thúc. Quan sát hành vi publish/exit thực tế theo cấu hình; đối chiếu với kết quả nghiệp vụ và xây cơ chế đối soát khi event thiếu.

**Bài tập E — Unknown commit.** Mô phỏng DB đã commit nhưng caller nhận lỗi. Chạy lại cùng business key và chứng minh chỉ còn một kết quả, dù Task/Job có thể có nhiều lần thực thi.

**Bài tập F — Chuẩn hóa CI.** Định nghĩa test matrix cho lỗi schema, timeout, SIGKILL, broker redelivery và hai tiến trình cạnh tranh; đề xuất timeout, cleanup, tag nhóm và bằng chứng cần lưu khi fail.

## 20. Ghi nhớ

- **Kiểm thử Batch, Task, event và runtime là bốn phạm vi khác nhau.** Một test pass ở phạm vi này không tự chứng minh phạm vi kia hoạt động.
- Với **Spring Batch 5.x**, `@SpringBatchTest` và `JobLauncherTestUtils` giúp chạy Job/Step trong context; sang **6.x** phải kiểm tra `JobOperatorTestUtils` và API mới.
- Test phải kiểm tra **`BatchStatus` + `ExitStatus` + dữ liệu commit**; process-level test mới đo được mã thoát thực của JVM và lỗi bootstrap.
- `task-events` và `job-execution-events` phục vụ mục đích khác nhau; Test Binder xác minh **contract**, Kafka Testcontainers xác minh **binder/broker thực tế**.
- **Không có event cuối hoặc `TaskExecution.END_TIME` không chứng minh một tác vụ chưa hoàn thành**; JVM có thể bị kill hoặc lưu metadata thất bại.
- **Lỗi kết nối quanh `COMMIT` có kết quả không xác định**. Retry cần business key ổn định, unique constraint và bước đối soát.
- Kiểm thử tích hợp đáng tin cậy phải **cô lập tài nguyên, có deadline, dọn dẹp, lưu bằng chứng và tránh gây lỗi hạ tầng production**.

## Tài liệu tham khảo

- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils`, Job/Step integration test.
- [Spring Batch 6.x — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `JobOperatorTestUtils` và thay đổi API so với 5.x.
- [Spring Cloud Task — Batch](https://docs.spring.io/spring-cloud-task/reference/batch.html): liên kết Task–Batch và `spring.cloud.task.batch.fail-on-job-failure`.
- [Spring Cloud Task — Spring Cloud Stream Integration](https://docs.spring.io/spring-cloud-task/reference/stream.html): `task-events`, Batch events và cấu hình bật/tắt listeners.
- [Spring Cloud Task — Features](https://docs.spring.io/spring-cloud-task/reference/features.html): `TaskRepository`, `TaskExecution` và giới hạn ghi nhận khi lỗi khởi tạo.
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html): Test Binder, `InputDestination` và `OutputDestination`.
- [Testcontainers for Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): tạo JDBC database cô lập cho integration tests.
- [Testcontainers for Java — Kafka](https://java.testcontainers.org/modules/kafka/): thử broker Kafka thực tế trong test.

**Giới hạn bài học:** mã Java/YAML là mẫu giảng giải cho tổ hợp phiên bản đã nêu, chưa được compile hoặc chạy trong repo của người học. Khi triển khai, phải xác minh version Spring Boot, Spring Cloud Task/Stream, Spring Batch, driver, serializer và khả năng kết nối Docker trong CI. Một vòng Content QA và test tích hợp chuyên sâu sẽ kiểm chứng chi tiết theo môi trường dự án.
