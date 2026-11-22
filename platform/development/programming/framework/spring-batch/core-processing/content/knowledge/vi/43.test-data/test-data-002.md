# Database test schema trong Spring Batch

## 1. Database test schema là gì?

Trong kiểm thử Spring Batch, **database test schema** là cấu trúc các đối tượng cơ sở dữ liệu mà môi trường test cần để một batch job hoặc step có thể hoạt động và để test có dữ liệu xác định. Schema ở đây bao gồm bảng, cột, khóa chính, khóa ngoại, sequence hoặc bảng sinh ID, chỉ mục và các ràng buộc cần thiết. Tùy hệ quản trị cơ sở dữ liệu, từ *schema* còn có nghĩa là một namespace, chẳng hạn `batch_test` trong PostgreSQL; cần phân biệt namespace đó với tập lệnh DDL tạo bảng.

Một bài kiểm thử batch dùng JDBC thường cần **hai nhóm schema**:

1. **Schema metadata của Spring Batch**: những bảng `BATCH_*` do `JobRepository` sử dụng để ghi nhận job instance, job execution, step execution, tham số và `ExecutionContext`.
2. **Schema nghiệp vụ của ứng dụng**: những bảng chứa dữ liệu đầu vào, kết quả xử lý, bảng tạm hoặc bảng đối soát mà reader, processor, writer hay tasklet thao tác.

Ví dụ, job xử lý đơn hàng có thể đọc các bản ghi trong `TEST_ORDER` và cập nhật `STATUS`. Trong cùng lúc, Spring Batch ghi metadata của lần chạy vào `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION`. **Có bảng nghiệp vụ chưa đủ để chạy job bằng JDBC `JobRepository`**, và ngược lại, có bảng `BATCH_*` chưa có nghĩa là reader có dữ liệu để đọc.

```text
                   Spring Batch job
                          |
             +------------+------------+
             |                         |
     JobRepository (metadata)     Reader / Writer / Tasklet
             |                         |
    +--------v---------+       +-------v---------+
    | BATCH_JOB_*      |       | TEST_ORDER      |
    | BATCH_STEP_*     |       | TEST_PAYMENT ...|
    +------------------+       +-----------------+
       Schema framework          Schema nghiệp vụ
```

Các bảng có thể cùng nằm trong một test database, hoặc được tách sang database/schema khác khi cấu hình ứng dụng đòi hỏi. Trong các ví dụ sau, cả hai nhóm cùng dùng một **H2 in-memory database**, đủ cho nhiều integration test cơ bản.

## 2. Khi nào cần database schema trong test?

| Loại kiểm thử | Có cần schema thật? | Lý do |
|---|---|---|
| Unit test thuần cho processor, validator hoặc hàm nghiệp vụ | Thường không | Truyền trực tiếp object, mock dependency; không chạy repository. |
| Unit test listener với `MetaDataInstanceFactory` | Không | Tạo `StepExecution` trong bộ nhớ; không dùng JDBC. |
| Test DAO/reader/writer truy vấn SQL | Có schema nghiệp vụ | Cần bảng, dữ liệu fixture và câu lệnh SQL thực sự chạy. |
| Test chạy step/job với JDBC `JobRepository` | Có schema metadata và thường có schema nghiệp vụ | Framework phải lưu trạng thái thực thi và code ứng dụng cần các bảng của nó. |
| Test restart/checkpoint sau lỗi | Có schema metadata bền qua các lần chạy trong test | Cần kiểm tra `ExecutionContext`, trạng thái và quan hệ giữa các lần thực thi. |
| Test tương thích SQL, khóa, transaction với PostgreSQL/MySQL/Oracle | Nên dùng đúng loại database mục tiêu | H2 không mô phỏng đầy đủ cú pháp SQL, locking, isolation và cơ chế sinh ID. |

Điểm quan trọng của chương **Test data**: schema quyết định *dữ liệu test có thể tồn tại như thế nào*, còn fixture quyết định *các bản ghi cụ thể tồn tại trước mỗi test*. Không trộn hai trách nhiệm khi thiết kế test.

## 3. Các bảng metadata cốt lõi của Spring Batch

Spring Batch dùng các bảng metadata để quản lý quá trình thực thi. Với dòng Spring Batch 5.x, các bảng chính là:

| Bảng | Nội dung lưu trữ | Liên hệ chính |
|---|---|---|
| `BATCH_JOB_INSTANCE` | Một job instance logic: tên job, job key, ID và version | Một instance có thể có nhiều job execution. |
| `BATCH_JOB_EXECUTION` | Một lần chạy: ID, thời gian, `BatchStatus`, `ExitStatus`, version... | Tham chiếu `BATCH_JOB_INSTANCE`. |
| `BATCH_JOB_EXECUTION_PARAMS` | Các `JobParameters`: tên, kiểu, giá trị và cờ `IDENTIFYING` | Thuộc về một job execution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | `ExecutionContext` cấp job | Gắn với một job execution. |
| `BATCH_STEP_EXECUTION` | Một lần chạy step: số lượng read/write/skip/commit/rollback, trạng thái, thời gian... | Tham chiếu `BATCH_JOB_EXECUTION`. |
| `BATCH_STEP_EXECUTION_CONTEXT` | `ExecutionContext` cấp step, thường chứa checkpoint | Gắn với một step execution. |

Quan hệ logic:

```text
BATCH_JOB_INSTANCE
      |
      +--< BATCH_JOB_EXECUTION
                 |
                 +--< BATCH_JOB_EXECUTION_PARAMS
                 +--- BATCH_JOB_EXECUTION_CONTEXT
                 +--< BATCH_STEP_EXECUTION
                           |
                           +--- BATCH_STEP_EXECUTION_CONTEXT
```

`BATCH_JOB_INSTANCE` đại diện cho một lần chạy logic được định danh bởi tên job và các *identifying job parameters*; khi chạy lại một instance, repository có thể có thêm `JobExecution`. `BATCH_STEP_EXECUTION` tương ứng lần thực thi step, nên một step cùng tên có thể có nhiều bản ghi qua các lần chạy/restart.

Để sinh ID, DDL còn tạo các đối tượng như `BATCH_JOB_SEQ`, `BATCH_JOB_EXECUTION_SEQ` và `BATCH_STEP_EXECUTION_SEQ`. Tùy database, chúng là **sequence thực** hoặc **bảng mô phỏng sequence**; không nên tự giả định mọi hệ quản trị dùng cùng cú pháp.

### 3.1. Schema metadata có phiên bản

DDL phải khớp với **phiên bản Spring Batch** đang chạy. Ví dụ, Spring Batch 5.x dùng các cột `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE`, `IDENTIFYING` trong `BATCH_JOB_EXECUTION_PARAMS`. Schema Spring Batch 4.x dùng cấu trúc cũ với những cột như `KEY_NAME`, `TYPE_CD`, `STRING_VAL`, `LONG_VAL`, `DATE_VAL` và `DOUBLE_VAL`.

Vì vậy, không lấy một file `schema-*.sql` bất kỳ trên Internet rồi áp vào phiên bản mới. Khi nâng phiên bản Spring Batch, xem **migration scripts** và hướng dẫn nâng cấp chính thức, nhất là nếu cần giữ dữ liệu metadata của các job cũ.

Các file DDL tương ứng hệ quản trị được phân phối cùng `spring-batch-core`, chẳng hạn:

```text
org/springframework/batch/core/schema-h2.sql
org/springframework/batch/core/schema-postgresql.sql
org/springframework/batch/core/schema-mysql.sql
```

Các ví dụ cấu hình dưới đây nhắm tới **Spring Boot 3.x + Spring Batch 5.x + JUnit 5**. Tên package/API và cách cấu hình có thể khác ở Spring Boot 4.x/Spring Batch 6.x; hãy sử dụng tài liệu của phiên bản dự án.

## 4. Thiết kế test database: H2, database thật và migrations

### 4.1. H2 in-memory

H2 nhanh, phù hợp các test cần xác minh luồng đơn giản, JDBC CRUD, số bản ghi và trạng thái batch. Database được tạo khi test kết nối đến URL `jdbc:h2:mem:...` và tồn tại theo vòng đời kết nối/quá trình như được cấu hình.

Lợi ích:

- Không cần khởi động database server riêng.
- Dễ tạo mới schema trong lúc Spring context khởi động.
- Dễ làm sạch dữ liệu giữa các test.

Giới hạn: cú pháp SQL, kiểu dữ liệu, sequence, transaction isolation, locking và cơ chế concurrency của H2 **không hoàn toàn giống** PostgreSQL/MySQL/Oracle. Một test chạy đúng trên H2 chưa đủ chứng minh SQL của ứng dụng tương thích production.

### 4.2. Database thật qua Testcontainers

Với câu lệnh SQL đặc thù, `JdbcPagingItemReader`, `JdbcBatchItemWriter`, transaction hoặc restart nhạy cảm theo vendor, có thể chạy PostgreSQL/MySQL trong container và tạo schema test trong đó. Database vẫn tạm thời, nhưng engine và dialect gần với production hơn.

### 4.3. Schema do Flyway/Liquibase quản lý

Nếu hệ thống đã dùng Flyway hoặc Liquibase, integration test nên thực thi **cùng migration cần thiết** để tạo schema. Khi migration quản lý cả bảng `BATCH_*`, hãy tắt cơ chế tự khởi tạo schema Spring Batch để tránh lỗi *table already exists*. Những bài test migration cần kiểm tra chính các bước nâng cấp, không chỉ schema mới nhất.

## 5. Ví dụ đầy đủ: tạo schema test bằng Spring Boot và H2

Giả sử cần test một batch job cập nhật `TEST_ORDER.STATUS` từ `NEW` sang `DONE`. Ta muốn Spring Batch lưu metadata trong chính database H2 này.

### 5.1. Dependencies Gradle

Ví dụ `build.gradle` dạng Groovy, với Spring Boot BOM/plugin đã quản lý dependency versions:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Nếu ứng dụng đang dùng Spring Boot Starter Test, hãy giữ dependency hiện có, không cần khai báo trùng. Đảm bảo `spring-batch-test` cùng dòng tương thích với `spring-batch-core`.

### 5.2. Cấu hình riêng cho profile test

Tạo file `src/test/resources/application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ''

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  sql:
    init:
      mode: always
      schema-locations: classpath:sql/schema-test.sql
```

Ý nghĩa:

| Cấu hình | Vai trò |
|---|---|
| `spring.datasource.url` | Kết nối tới H2 in-memory tên `batch_test`. |
| `DB_CLOSE_DELAY=-1` | Giữ database trong bộ nhớ khi kết nối cuối đóng, cho tới khi JVM kết thúc. |
| `spring.batch.job.enabled=false` | Không tự khởi chạy job lúc Spring Boot khởi động; test sẽ chủ động gọi launcher. |
| `spring.batch.jdbc.initialize-schema=always` | Khởi tạo các bảng/sequence metadata `BATCH_*` từ script tương ứng platform, kể cả trên database không phải embedded. |
| `spring.sql.init.schema-locations` | Chạy DDL tạo **bảng nghiệp vụ** của test. |
| `spring.sql.init.mode=always` | Yêu cầu Boot chạy SQL initialization; hữu ích khi đổi sang test database ngoài tiến trình. |

Hai cơ chế khởi tạo SQL ở đây có mục đích khác nhau: `spring.batch.jdbc.*` cho metadata Spring Batch, `spring.sql.init.*` cho schema nghiệp vụ do ứng dụng kiểm soát. Với ví dụ này, DDL nghiệp vụ không phụ thuộc các bảng `BATCH_*`, nên không cần chỉ định thứ tự giữa chúng.

**Không dùng `initialize-schema: always` trên database production đang có metadata thật.** Ở production, quản lý DDL theo migration/chính sách triển khai của ứng dụng; property trên chỉ được kích hoạt trong profile test cô lập.

### 5.3. File DDL nghiệp vụ

Tạo `src/test/resources/sql/schema-test.sql`:

```sql
CREATE TABLE TEST_ORDER (
    ID BIGINT PRIMARY KEY,
    CUSTOMER_CODE VARCHAR(40) NOT NULL,
    AMOUNT DECIMAL(12, 2) NOT NULL,
    STATUS VARCHAR(16) NOT NULL
);

CREATE INDEX IDX_TEST_ORDER_STATUS ON TEST_ORDER (STATUS);
```

Đây là schema nhỏ để tập trung vào hành vi batch. Trong dự án thật, nên phản ánh các ràng buộc mà logic đang phụ thuộc: `NOT NULL`, unique key, foreign key, độ dài, precision, index và các kiểu dữ liệu quan trọng. Nếu lược bớt ràng buộc so với production, test có thể bỏ sót lỗi chỉ xuất hiện trên database thật.

### 5.4. Tách dữ liệu seed khỏi DDL

Tạo `src/test/resources/sql/seed-test-order.sql`:

```sql
INSERT INTO TEST_ORDER (ID, CUSTOMER_CODE, AMOUNT, STATUS) VALUES
    (1, 'CUSTOMER-A', 150.00, 'NEW'),
    (2, 'CUSTOMER-B', 245.75, 'NEW'),
    (3, 'CUSTOMER-C', 399.00, 'HOLD');
```

Tạo `src/test/resources/sql/cleanup-test-order.sql`:

```sql
DELETE FROM TEST_ORDER;
```

Không nên đưa dữ liệu fixture chuyên biệt này vào `schema-test.sql`: schema chỉ tạo cấu trúc một lần khi context khởi động, còn seed cần được tạo lại cho từng test method. Với `@Sql`, dữ liệu của từng test sẽ được tái tạo ở thời điểm thích hợp.

## 6. Job mẫu dùng test schema

Để làm rõ ý nghĩa của schema, đây là một job tối giản dùng `JdbcTemplate` cập nhật các đơn hàng `NEW`. Ví dụ tương thích với builder API Spring Batch 5.x:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderProcessingJobConfig {

    @Bean
    public Step processOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbcTemplate) {

        return new StepBuilder("processOrdersStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    jdbcTemplate.update("""
                            UPDATE TEST_ORDER
                            SET STATUS = 'DONE'
                            WHERE STATUS = 'NEW'
                            """);
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    public Job processOrdersJob(
            JobRepository jobRepository,
            Step processOrdersStep) {

        return new JobBuilder("processOrdersJob", jobRepository)
                .start(processOrdersStep)
                .build();
    }
}
```

Ví dụ chỉ dùng một tasklet để quan sát dữ liệu; với chunk-oriented step, reader/processor/writer cũng có thể dùng cùng schema. Bean `JobRepository`, `PlatformTransactionManager`, `JdbcTemplate` được cung cấp bởi Spring Boot/JDBC auto-configuration tương ứng. Trong test, có thể import cấu hình này nếu nó chưa nằm trong component scan của ứng dụng.

Một điểm dễ nhầm: câu `UPDATE` thay đổi **hai dòng** trong `TEST_ORDER`, nhưng `StepExecution.getWriteCount()` của tasklet không tự tăng lên 2. Những bộ đếm read/write của Spring Batch gắn với cách xử lý item/chunk; không suy ra chúng từ số dòng mà câu SQL tùy ý đã sửa.

## 7. Integration test chạy job và xác minh dữ liệu

Spring Batch cung cấp `@SpringBatchTest` và `JobLauncherTestUtils` cho test tích hợp. Test này kiểm tra cả dữ liệu nghiệp vụ lẫn metadata được lưu trong test database.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.AfterEach;
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
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
@Import(OrderProcessingJobConfig.class)
@Sql(scripts = "/sql/seed-test-order.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(scripts = "/sql/cleanup-test-order.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_METHOD)
class OrderProcessingJobIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("processOrdersJob")
    private Job processOrdersJob;

    @BeforeEach
    void setUp() {
        jobRepositoryTestUtils.removeJobExecutions();
        jobLauncherTestUtils.setJob(processOrdersJob);
    }

    @AfterEach
    void tearDown() {
        jobRepositoryTestUtils.removeJobExecutions();
    }

    @Test
    void processesOnlyNewOrdersAndPersistsExecutionMetadata()
            throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addLong("run.id", 565L)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        Integer doneCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM TEST_ORDER WHERE STATUS = 'DONE'",
                Integer.class);
        Integer holdCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM TEST_ORDER WHERE STATUS = 'HOLD'",
                Integer.class);

        assertEquals(2, doneCount);
        assertEquals(1, holdCount);

        Long persistedExecutions = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM BATCH_JOB_EXECUTION
                WHERE JOB_EXECUTION_ID = ?
                """,
                Long.class,
                execution.getId());

        assertEquals(1L, persistedExecutions);
    }
}
```

Với Spring Boot application có một `@SpringBootApplication` hợp lệ, `@SpringBootTest` sẽ tạo context, `@ActiveProfiles("test")` nạp `application-test.yml`, còn `@Import` đưa job demo vào context. Nếu job này đã có sẵn trong component scan, không cần import lại.

Diễn biến của test:

1. Spring tạo H2 datasource; các bảng metadata `BATCH_*` và `TEST_ORDER` được khởi tạo.
2. `@Sql` chèn ba đơn hàng trước test method.
3. Test chuẩn bị `JobParameters`, sau đó gọi `JobLauncherTestUtils.launchJob(...)`.
4. `JobRepository` ghi `JobExecution`/`StepExecution`; tasklet cập nhật hai đơn hàng có trạng thái `NEW`.
5. Assertion xác minh job `COMPLETED`, dữ liệu nghiệp vụ đúng và có bản ghi metadata phù hợp.
6. Phần cleanup xóa metadata của test repository và xóa dữ liệu nghiệp vụ của test.

`JobRepositoryTestUtils.removeJobExecutions()` có phạm vi **toàn bộ các job executions trong repository đó**. Chỉ sử dụng nó khi database/repository dành riêng cho test và không chạy các test dùng chung repository song song. Đoạn test không gắn `@Transactional` cho cả test method: khi chạy một batch job thật, transaction của step cần được quản lý theo cấu hình batch; transaction bao ngoài test có thể làm kết quả khác hành vi production.

## 8. Xác minh schema metadata bằng SQL

Các câu truy vấn đọc có thể hữu ích để xác định job/step nào đã chạy. Ví dụ:

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
ORDER BY je.JOB_EXECUTION_ID;
```

Đọc thông tin step:

```sql
SELECT
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
ORDER BY STEP_EXECUTION_ID;
```

Đọc tham số trong schema Spring Batch 5.x:

```sql
SELECT PARAMETER_NAME, PARAMETER_TYPE, PARAMETER_VALUE, IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = ?;
```

Các truy vấn này hữu ích khi debug test, nhưng assertion chính nên ưu tiên API công khai (`JobExecution`, `StepExecution`, `JobRepository`) nếu mục tiêu không trực tiếp liên quan đến cấu trúc SQL. Cách đó tránh làm test phụ thuộc quá chặt vào chi tiết schema nội bộ vốn có thể thay đổi sau nâng cấp.

### 8.1. Không cập nhật trực tiếp metadata để giả lập trạng thái

Một anti-pattern thường gặp:

```sql
-- Không nên dùng để giả lập restart trong test thông thường:
UPDATE BATCH_JOB_EXECUTION SET STATUS = 'FAILED'
WHERE JOB_EXECUTION_ID = 123;
```

Trạng thái batch còn liên quan đến `ExitStatus`, step executions, version dùng cho optimistic locking và `ExecutionContext`. Sửa một cột trực tiếp có thể tạo metadata thiếu nhất quán. Để kiểm tra restart, hãy chủ động gây lỗi trong step đầu tiên, để framework lưu trạng thái, sau đó thực hiện lần chạy lại với cùng identifying parameters và kiểm tra kết quả.

## 9. Cô lập dữ liệu giữa các test

**Test data phải có vòng đời rõ ràng.** Nếu test A để lại `BATCH_JOB_EXECUTION` hoặc `TEST_ORDER`, test B có thể thất bại khi chạy chung suite, dù chạy riêng thì thành công.

Một số cơ chế thường dùng:

| Cơ chế | Ưu điểm | Lưu ý |
|---|---|---|
| Mỗi suite/class dùng database in-memory khác nhau | Cô lập dữ liệu, tránh xung đột ID | Tốn thêm thời gian tạo Spring context và schema. |
| `@Sql` tạo seed trước và cleanup sau mỗi test | Fixture dễ đọc, kết quả có thể dự đoán | Cleanup phải đúng thứ tự với khóa ngoại. |
| `JobRepositoryTestUtils.removeJobExecutions()` | Xóa metadata của các executions để test độc lập | Xóa toàn repository; chỉ dùng với repository test riêng. |
| `@DirtiesContext` | Khởi tạo lại Spring context sau test | Chi phí cao; không phải giải pháp mặc định cho mọi test. |
| Một database/container riêng mỗi lớp hoặc nhóm test | Gần hệ quản trị production, giảm rò dữ liệu | Cần quản lý vòng đời container và thời gian khởi động. |

Không tự `TRUNCATE BATCH_JOB_INSTANCE` trước các bảng con. Khóa ngoại và sequence/table sinh ID khiến việc xóa metadata bằng SQL dễ sai hoặc lệch giữa database vendors. Nếu bắt buộc phải cleanup SQL, hãy định nghĩa rõ dependency order và giới hạn trong database test độc lập. Với ứng dụng đa luồng hoặc test song song, một database chung cộng với cleanup toàn cục là nguyên nhân rất phổ biến gây test không ổn định.

### 9.1. `JobInstanceAlreadyCompleteException` và identifying parameters

Đối với `JobRepository` dùng JDBC, tên job và các `JobParameters` có cờ `IDENTIFYING` quyết định job instance logic. Chạy lại một instance đã `COMPLETED` thường bị từ chối bằng `JobInstanceAlreadyCompleteException`.

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .addLong("run.id", 1L)
        .toJobParameters();
```

Nếu hai test tạo cùng tham số và không xóa metadata, chúng có thể đụng cùng job instance. Có ba hướng chính: tạo database/repository riêng, dọn metadata sau test, hoặc dùng tham số định danh khác nhau nếu mỗi lượt **thực sự** đại diện cho một instance mới. Đối với test restart, cố ý giữ cùng identifying parameters để kiểm tra hành vi chạy lại; không thêm `run.id` mới chỉ để né xung đột.

### 9.2. Transaction và `@Sql`

`@Sql` có thể tham gia vào transaction của test, tùy `SqlConfig` và cấu hình transaction manager. Khi job chạy thật, step cũng có transaction riêng. Để test thực tế dễ hiểu, ví dụ trên không đặt `@Transactional` ở test class/method và dùng seed/cleanup rõ ràng. Nếu cần kiểm tra rollback, hãy thiết kế riêng tình huống transaction của **step** hoặc **chunk**, rồi kiểm tra dữ liệu được commit/rollback cùng metadata sau khi job kết thúc.

## 10. Khi cần PostgreSQL thực tế: Testcontainers

Nếu sản phẩm dùng PostgreSQL, cấu trúc tạo bảng từ H2 có thể chưa phát hiện lỗi SQL vendor-specific. Với Spring Boot 3.1+ và Testcontainers, có thể chạy một database PostgreSQL tạm thời cho integration test.

Khai báo dependencies (Boot BOM/Testcontainers BOM quản lý các phiên bản tương thích):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

Ví dụ khung test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test-postgres")
class PostgreSqlBatchSchemaIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void contextStartsWithDatabaseSchema() {
        // Tại đây có thể chạy job và kiểm tra dữ liệu như ví dụ H2.
    }
}
```

Với profile `test-postgres`, không gán URL H2 cố định. `@ServiceConnection` cung cấp connection details từ container. Nếu không sử dụng Flyway/Liquibase, thiết lập `spring.batch.jdbc.initialize-schema=always` trong profile này và khởi tạo DDL nghiệp vụ tương ứng PostgreSQL; Spring Boot sẽ chọn script metadata theo database platform. Nếu đã quản lý `BATCH_*` bằng migrations, đặt `initialize-schema=never` để tránh tạo lặp.

Testcontainers cần Docker/container runtime khả dụng. Tùy yêu cầu, có thể dùng một container cho mỗi class hoặc cấu hình tái sử dụng trong suite; khi chia sẻ database phải đồng thời thiết kế isolation. Code trên minh họa kết nối database; để chứng minh bảng/schema và job hoạt động, cần bổ sung assertion thực tế như ở mục 7.

## 11. Migrations và tùy biến tên schema

Trong dự án dùng PostgreSQL, có thể tổ chức metadata trong một schema riêng, ví dụ `batch_meta`, và dữ liệu nghiệp vụ trong `app_data`. Việc tách này có ích cho quyền truy cập và tổ chức dữ liệu, nhưng cả DDL, JDBC schema/search path và cấu hình prefix của `JobRepository` phải đồng nhất.

Nếu thay prefix bảng mặc định `BATCH_`, cần chuẩn bị DDL tương ứng và điều chỉnh cấu hình repository, gồm cả cách sinh ID. Chỉ đổi tên bảng trong SQL test là chưa đủ. Các SQL script mặc định của Spring Batch không tự hiểu mọi prefix/schema tùy biến.

Một chiến lược dễ bảo trì:

1. Định nghĩa các migration cho metadata (nếu ứng dụng chịu trách nhiệm quản lý) và bảng nghiệp vụ.
2. Trong test, khởi động database sạch, chạy migrations như production.
3. Nạp fixture thông qua `@Sql`, builder hoặc factory tạo test data.
4. Chạy job/step và assert dữ liệu đầu ra.
5. Cleanup hoặc hủy database sau khi test hoàn tất.

**Không kết hợp hai chủ sở hữu DDL cho cùng bảng.** Ví dụ, nếu Flyway đã tạo `BATCH_JOB_INSTANCE`, đồng thời chạy `spring.batch.jdbc.initialize-schema=always` có thể khiến startup thất bại vì bảng đã tồn tại. Spring Batch schema initializer phù hợp với test database sạch khi không có migration khác quản lý metadata.

## 12. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `Table BATCH_JOB_INSTANCE not found` | Chưa khởi tạo metadata hoặc datasource/schema sai | Kiểm tra `spring.batch.jdbc.initialize-schema`, active profile, platform và datasource của `JobRepository`. |
| `Table TEST_ORDER not found` | Chưa chạy DDL nghiệp vụ | Kiểm tra `spring.sql.init.schema-locations`, đường dẫn classpath và tên/schema bảng. |
| `BATCH_JOB_SEQ`/`BATCH_STEP_EXECUTION_SEQ` không tồn tại | DDL thiếu đối tượng sinh ID hoặc dùng script của database khác | Sử dụng toàn bộ schema script tương ứng vendor và phiên bản Batch. |
| `Table ... already exists` lúc khởi động | Schema bị tạo hai lần hoặc database cũ còn tồn tại | Kiểm tra Flyway/Liquibase, Batch initializer, SQL initializer và vòng đời DB. |
| `JobInstanceAlreadyCompleteException` | Chạy lại cùng identifying parameters của job đã hoàn thành | Cleanup metadata hoặc dùng job instance mới đúng mục tiêu; với restart test phải giữ instance. |
| Sai kiểu cột `BATCH_JOB_EXECUTION_PARAMS` | Schema khác phiên bản Spring Batch | Đối chiếu schema/migration của bản đang dùng. |
| Test riêng lẻ qua nhưng chạy cả suite thất bại | Fixture/metadata rò giữa các test hoặc cleanup xung đột | Tách database, reset dữ liệu đúng phạm vi, tránh chia sẻ repository khi chạy song song. |
| Truy vấn H2 thành công nhưng PostgreSQL lỗi | Khác dialect, kiểu dữ liệu, khóa hoặc transaction semantics | Chạy integration test trên engine mục tiêu bằng Testcontainers hoặc database test thật. |
| Job chạy khi vừa khởi động Spring context | Auto-run job đang bật | Đặt `spring.batch.job.enabled=false` trong profile test. |

Một số trường hợp thông báo lỗi chỉ xuất hiện khi gọi `launchJob()`, chứ không xuất hiện khi context tạo xong. Vì vậy, smoke test chỉ kiểm tra context load không thay thế được một integration test có thực thi job và assertion trên dữ liệu.

## 13. Quy tắc thiết kế database test schema đáng tin cậy

Khi tạo một bộ test mới cho module Spring Batch, nên xác định rõ:

1. **Loại test:** Unit test có thực sự cần database không? Nếu không, dùng các object đơn giản hoặc `MetaDataInstanceFactory`.
2. **Phiên bản framework:** Schema `BATCH_*` phải khớp Spring Batch 5.x/6.x của ứng dụng; không lấy DDL từ phiên bản khác.
3. **Hệ quản trị:** H2 cho vòng lặp test nhanh; PostgreSQL/MySQL/... thực cho các hành vi phụ thuộc dialect.
4. **Ai tạo schema:** Spring Batch initializer, Spring SQL initialization, Flyway hay Liquibase? Mỗi bảng nên chỉ có một cơ chế sở hữu việc khởi tạo.
5. **Dữ liệu khởi tạo:** Phân biệt DDL với seed fixture, ràng buộc rõ expected rows và tình huống biên.
6. **Vòng đời test:** Trước mỗi test tạo lại fixture; sau mỗi test dọn dữ liệu và metadata trong đúng database test.
7. **Khả năng chạy song song:** Không dùng một `JobRepository` chung nếu các test đồng thời xóa toàn bộ executions của nhau.
8. **Assertion:** Kiểm tra cả trạng thái job/step lẫn dữ liệu nghiệp vụ; chỉ kiểm tra `BatchStatus.COMPLETED` thường chưa đủ.
9. **Restart test:** Chạy lỗi rồi chạy lại thật, giữ metadata/checkpoint và identifying parameters; không sửa thủ công một cột trạng thái để giả lập restart.

### Bài tập thực hành

Mở rộng ví dụ `TEST_ORDER`:

- Thêm ràng buộc `CHECK (AMOUNT >= 0)` và viết test kiểm tra bản ghi không hợp lệ bị từ chối.
- Thêm một test seed chỉ có đơn hàng `HOLD`; xác minh job hoàn thành nhưng không sửa dòng nào.
- Tạo job thất bại có chủ đích sau khi lưu checkpoint; kiểm tra trạng thái `FAILED` trong metadata, sau đó khởi chạy lại cùng identifying parameters để quan sát restart theo cấu hình step.
- Chạy lại bài test SQL trên PostgreSQL Testcontainers và kiểm tra DDL/transaction behavior tương ứng.

Qua các bài tập này, schema không chỉ là bước khởi tạo bắt buộc: nó là một phần của **hợp đồng kiểm thử**, bảo đảm dữ liệu đầu vào, ràng buộc, metadata thực thi và trạng thái sau khi batch chạy đều có thể được kiểm chứng.

## 14. Tài liệu tham khảo

- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): cấu trúc bảng, sequence và các quan hệ metadata.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, kiểm thử step scope.
- [Spring Boot Reference — Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): SQL initialization, Batch schema initialization, Flyway và Liquibase.
- [Spring Boot Reference — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection`, kết nối database dùng trong test.

