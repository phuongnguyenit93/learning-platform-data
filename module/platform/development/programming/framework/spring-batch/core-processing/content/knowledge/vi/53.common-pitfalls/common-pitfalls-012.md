# Test chỉ kiểm tra exit code trong Spring Batch

## 1. Vì sao đây là một lỗi kiểm thử phổ biến?

Một bài test Spring Batch thường bắt đầu bằng lời gọi chạy Job và kiểm một kết quả:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);
assertEquals("COMPLETED", execution.getExitStatus().getExitCode());
~~~

Assertion này cho biết Spring Batch đã báo mã kết thúc mong đợi. **Nó không chứng minh Job đã xử lý đúng dữ liệu, ghi đủ output, commit đúng, không tạo trùng hoặc xử lý đúng kỳ nghiệp vụ.**

Ví dụ Job cần nhập các đơn hàng của ngày 16/11/2026. Reader chứa lỗi trong SQL, dùng điều kiện ngày 15/11/2026. Nếu không có bản ghi phù hợp và không có exception, Step vẫn có thể kết thúc bình thường. ExitStatus là `COMPLETED`, nhưng **không có đơn hàng nào của ngày cần nhập được ghi**. Test chỉ nhìn exit code sẽ xanh giả.

Bài học thuộc nhóm **Lỗi thường gặp** trong *Spring Batch Core Processing*. Sau bài này, bạn sẽ biết:

- Phân biệt **OS process exit code**, **BatchStatus** và **ExitStatus**.
- Hiểu khi nào `COMPLETED` không đồng nghĩa kết quả nghiệp vụ đúng.
- Kiểm metadata JobExecution, StepExecution và JobParameters.
- Kiểm kết quả trong bảng dữ liệu, file, API hoặc message broker.
- Thiết kế fixture có khả năng phát hiện sai kỳ, sai tenant, thiếu bản ghi và duplicate.
- Kiểm thử filter, skip, retry, transaction rollback và restart.
- Viết integration test bằng `@SpringBatchTest` và JDBC JobRepository.
- Tránh assertion quá sớm với Job chạy bất đồng bộ.

## 2. Ba tín hiệu khác nhau

| Tín hiệu | Đọc từ đâu? | Ý nghĩa |
| --- | --- | --- |
| **Process exit code** | Shell, OS, container runtime | Số nguyên tiến trình Java trả về khi kết thúc, theo logic ứng dụng/launcher. |
| **BatchStatus** | `JobExecution.getStatus()` | Trạng thái vòng đời do Spring Batch quản lý: STARTING, STARTED, COMPLETED, FAILED, STOPPED… |
| **ExitStatus** | `JobExecution.getExitStatus()` | Mã và mô tả kết thúc dùng cho flow hoặc hệ thống điều hành; có thể được tùy biến. |

Ví dụ Spring Batch 5.2:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

BatchStatus batchStatus = execution.getStatus();
String exitCode = execution.getExitStatus().getExitCode();
String description =
        execution.getExitStatus().getExitDescription();
~~~

**ExitStatus không phải process exit code.** Spring Batch dùng các chuỗi như `COMPLETED`, `FAILED` hoặc mã custom; hệ điều hành quan sát mã số của tiến trình. Một `ExitCodeMapper` hoặc code ứng dụng có thể ánh xạ chuỗi thành số.

~~~text
JobExecution.ExitStatus = "COMPLETED"
           |
           v
Java application / launcher / optional ExitCodeMapper
           |
           v
OS process exit code (ví dụ: 0)
~~~

Một ứng dụng Spring Boot có thể vẫn chạy sau khi Job hoàn thành; nhiều Job cũng có thể cùng tồn tại trong một JVM. Vì thế, việc kiểm `echo $?` bằng 0 không chứng minh một Job cụ thể đã ghi đủ dữ liệu.

**BatchStatus và ExitStatus cũng không phải hai tên của cùng một thuộc tính.** `BatchStatus` mô tả vòng đời thực thi, còn `ExitStatus` có thể được điều chỉnh để truyền tín hiệu chuyển nhánh flow hoặc báo các kết quả đặc biệt như `COMPLETED WITH SKIPS`. Cả hai đều cần được diễn giải theo cấu hình Job.

## 3. Trạng thái xanh nhưng kết quả sai

| Tình huống | Trạng thái Job có thể là | Lỗi bị bỏ sót |
| --- | --- | --- |
| Reader lọc nhầm ngày | COMPLETED | Không nhập dữ liệu kỳ cần chạy. |
| Query thiếu điều kiện tenant | COMPLETED | Nhập dữ liệu tenant khác. |
| Processor trả `null` sai quy tắc | COMPLETED | Bản ghi bị filter ngoài dự kiến. |
| Step cho phép skip quá rộng | COMPLETED | Dữ liệu quan trọng bị bỏ qua. |
| Writer map sai amount | COMPLETED | Số dòng đúng, giá trị tiền sai. |
| Bảng đích còn dữ liệu của test trước | COMPLETED | Test tưởng Job mới đã ghi dữ liệu. |
| Restart với identifying `run.id` mới | COMPLETED | Tạo JobInstance mới, nguy cơ xử lý trùng. |
| File xuất không có header hoặc thiếu dòng | COMPLETED | Artifact không dùng được cho downstream. |
| Mock API luôn trả success | COMPLETED | Payload/idempotency key có thể sai. |
| Step cần chạy bị bỏ qua do flow sai | COMPLETED | Job chọn nhánh không đúng. |

`COMPLETED` **thường là điều kiện cần**, nhưng **chưa phải điều kiện đủ** để kết luận một nghiệp vụ đã xử lý đúng.

## 4. Các lớp assertion nên có

~~~text
Khởi chạy Job với JobParameters rõ ràng
                    |
                    v
             Job/Exit status
                    |
                    v
       JobInstance và execution ID
                    |
                    v
         StepExecution metadata
                    |
                    v
     Dữ liệu output và business rules
                    |
                    v
        Không trùng, không sai scope
                    |
                    v
       Transaction/restart nếu cần
                    |
                    v
             Kết luận test
~~~

| Lớp kiểm | Assertion gợi ý |
| --- | --- |
| Kết quả kỹ thuật | `BatchStatus.COMPLETED`, ExitStatus phù hợp, không có failure exception ngoài dự kiến. |
| Identity | Đúng Job name, identifying JobParameters và JobInstance ID. |
| Step metadata | Step đã chạy, trạng thái Step và các count phù hợp. |
| Dữ liệu | Số lượng, business keys, giá trị, quan hệ, tổng tiền, checksum. |
| Negative assertions | Không xuất bản ghi sai ngày, sai tenant; không sửa dữ liệu ngoài scope. |
| Transaction | Chunk lỗi rollback, chunk đã commit giữ nguyên. |
| Restart | Cùng JobInstance, JobExecution mới, không duplicate. |
| Hệ thống ngoài | Đúng HTTP request/message, idempotency key, file publish. |

Không nhất thiết gộp tất cả vào một phương thức. Bộ test có thể chia unit test processor, Step integration, Job integration và recovery test.

## 5. Dữ liệu test phải có khả năng bắt lỗi

Chỉ dùng dataset rỗng khiến code đúng và code lọc sai đều có thể trả về 0 dòng. Một fixture nên có ít nhất hai item hợp lệ và một item **ngoài scope**.

Ví dụ Job chạy cho `businessDate=2026-11-16`:

| id | business_date | amount | Kỳ vọng |
| ---: | --- | ---: | --- |
| 1001 | 2026-11-16 | 120 | Có trong output. |
| 1002 | 2026-11-16 | 230 | Có trong output. |
| 1003 | 2026-11-15 | 900 | Không được ghi vào output. |

Kỳ vọng gồm **chính xác ID 1001 và 1002**, tổng amount **350**. Nếu chỉ assert số dòng bằng 2, Job vẫn có thể ghi nhầm hai ID khác hoặc amount sai. Do đó nên kiểm **key và giá trị**, không chỉ COUNT(*).

Với hệ thống multi-tenant, thêm record của tenant B cùng ngày để test rằng Job tenant A không xử lý nhầm.

## 6. Ví dụ tích hợp với Spring Batch 5.2 và Spring Boot 3

Để tập trung vào bài toán exit code, ví dụ dùng **Tasklet** thực hiện một câu SQL `INSERT ... SELECT`. Nó minh họa rõ việc một SQL trả 0 row mà không báo lỗi khiến Job có thể `COMPLETED`.

### 6.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 6.2. Schema dành cho test

File `src/test/resources/batch-test-schema.sql`:

~~~sql
CREATE TABLE source_orders (
    id BIGINT PRIMARY KEY,
    business_date VARCHAR(10) NOT NULL,
    amount BIGINT NOT NULL
);

CREATE TABLE processed_orders (
    id BIGINT PRIMARY KEY,
    business_date VARCHAR(10) NOT NULL,
    amount BIGINT NOT NULL
);
~~~

File `src/test/resources/application-batchtest.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:exitcode_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.batch.jdbc.initialize-schema=always
spring.batch.job.enabled=false

spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:batch-test-schema.sql
~~~

Ở đây Spring Boot Batch auto-configuration hỗ trợ tạo JDBC JobRepository và các bảng metadata `BATCH_*`. Nếu ứng dụng tự cấu hình repository hoặc dùng nhiều DataSource, phải chọn rõ repository, transaction manager và script schema. Ví dụ không thêm `@EnableBatchProcessing` vì đang dựa vào auto-configuration của Boot 3.

### 6.3. Job minh họa

File `CopyOrdersJobConfiguration.java`:

~~~java
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

@Configuration(proxyBeanMethods = false)
public class CopyOrdersJobConfiguration {

    @Bean
    Step copyOrdersStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("copyOrdersStep", repository)
                .tasklet((contribution, chunkContext) -> {

                    String businessDate = contribution
                            .getStepExecution()
                            .getJobParameters()
                            .getString("businessDate");

                    jdbc.update(
                        "INSERT INTO processed_orders " +
                        "(id, business_date, amount) " +
                        "SELECT id, business_date, amount " +
                        "FROM source_orders " +
                        "WHERE business_date = ?",
                        businessDate);

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Job copyOrdersJob(JobRepository repository, Step copyOrdersStep) {
        return new JobBuilder("copyOrdersJob", repository)
                .start(copyOrdersStep)
                .build();
    }
}
~~~

Nếu code dùng sai ngày trong câu SQL, nó có thể insert 0 row nhưng vẫn trả `RepeatStatus.FINISHED`. Đây chính là lỗi mà kiểm exit code không phát hiện.

### 6.4. Test yếu

~~~java
@Test
void weakTest() throws Exception {
    JobParameters params = new JobParametersBuilder()
            .addString("businessDate", "2026-11-16")
            .toJobParameters();

    JobExecution execution = launcherTestUtils.launchJob(params);

    assertEquals("COMPLETED",
            execution.getExitStatus().getExitCode());
}
~~~

Test chưa biết bảng `processed_orders` có gì, nên không thể khẳng định công việc đã hoàn tất theo hợp đồng nghiệp vụ.

### 6.5. Test xác minh kết quả

File `CopyOrdersIT.java`:

~~~java
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@ActiveProfiles("batchtest")
@SpringBootTest(classes = CopyOrdersIT.TestApplication.class)
class CopyOrdersIT {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(CopyOrdersJobConfiguration.class)
    static class TestApplication {
    }

    @Autowired JobLauncherTestUtils launcherTestUtils;
    @Autowired JobRepositoryTestUtils repositoryTestUtils;
    @Autowired JobRepository jobRepository;
    @Autowired JdbcTemplate jdbc;

    @Autowired
    @Qualifier("copyOrdersJob")
    Job job;

    @BeforeEach
    void prepare() {
        launcherTestUtils.setJob(job);

        // Chỉ xóa metadata trong database test biệt lập.
        repositoryTestUtils.removeJobExecutions();
        jdbc.update("DELETE FROM processed_orders");
        jdbc.update("DELETE FROM source_orders");

        jdbc.update("INSERT INTO source_orders VALUES (?, ?, ?)",
                1001L, "2026-11-16", 120L);
        jdbc.update("INSERT INTO source_orders VALUES (?, ?, ?)",
                1002L, "2026-11-16", 230L);
        jdbc.update("INSERT INTO source_orders VALUES (?, ?, ?)",
                1003L, "2026-11-15", 900L);
    }

    @Test
    void checksStatusAndBusinessOutcome() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(params);

        // 1. Trạng thái kỹ thuật.
        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(ExitStatus.COMPLETED.getExitCode(),
                execution.getExitStatus().getExitCode());
        assertTrue(execution.getAllFailureExceptions().isEmpty());

        // 2. Metadata đã lưu.
        assertEquals("copyOrdersJob",
                execution.getJobInstance().getJobName());

        JobExecution persisted = jobRepository.getLastJobExecution(
                "copyOrdersJob", params);

        assertNotNull(persisted);
        assertEquals(execution.getId(), persisted.getId());
        assertEquals(BatchStatus.COMPLETED, persisted.getStatus());

        // 3. Đúng tập ID nghiệp vụ.
        List<Long> ids = jdbc.queryForList(
                "SELECT id FROM processed_orders ORDER BY id",
                Long.class);
        assertEquals(List.of(1001L, 1002L), ids);

        // 4. Đúng tổng giá trị.
        Long sum = jdbc.queryForObject(
                "SELECT SUM(amount) FROM processed_orders",
                Long.class);
        assertEquals(350L, sum);

        // 5. Không làm biến đổi nguồn ngoài ý định.
        Integer sourceRows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM source_orders",
                Integer.class);
        assertEquals(3, sourceRows);
    }
}
~~~

Nếu SQL bị sửa thành đọc ngày 15/11, Job vẫn có thể `COMPLETED`, nhưng test thất bại ở assertion danh sách ID và tổng tiền.

**Lưu ý:** `removeJobExecutions()` xóa lịch sử batch trong database mà utility trỏ vào. Chỉ dùng trên database test cô lập. Không gọi giữa hai execution của cùng một test restart. Với test chạy song song, cần tách database/schema để các test không xóa dữ liệu của nhau.

## 7. Khi Step dùng chunk: kiểm metadata phù hợp

Ví dụ trên dùng Tasklet SQL. Với Tasklet, `getReadCount()` và `getWriteCount()` có thể vẫn bằng 0 dù SQL đã insert 2 row. Vì vậy, phải quan sát dữ liệu đích.

Với **chunk-oriented Step**, `StepExecution` có các count hữu ích:

~~~java
StepExecution step = execution.getStepExecutions().stream()
        .filter(s -> "importOrdersStep".equals(s.getStepName()))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, step.getStatus());

assertEquals(100, step.getReadCount());
assertEquals(98, step.getWriteCount());
assertEquals(2, step.getFilterCount());

assertEquals(0, step.getReadSkipCount());
assertEquals(0, step.getProcessSkipCount());
assertEquals(0, step.getWriteSkipCount());
~~~

Đây là assertion **minh họa** cho Step đọc 100 item, filter 2 item đúng policy và ghi 98 item; không dùng các số này cho Tasklet SQL ở trên.

| Trường StepExecution | Diễn giải |
| --- | --- |
| `READ_COUNT` | Số item đọc theo semantics của Step. |
| `WRITE_COUNT` | Số item ghi theo semantics của Step. |
| `FILTER_COUNT` | Số item bị processor lọc khi trả null. |
| `READ_SKIP_COUNT` | Số item reader bị skip theo chính sách. |
| `PROCESS_SKIP_COUNT` | Số item processor bị skip. |
| `WRITE_SKIP_COUNT` | Số item writer bị skip. |
| `COMMIT_COUNT` | Số lần commit transaction Step ghi nhận. |
| `ROLLBACK_COUNT` | Số lần rollback Step ghi nhận. |

`writeCount=98` không bảo đảm 98 record có amount đúng. Metadata giúp tìm sai lệch ở giai đoạn nào; **business assertions** mới chứng minh outcome.

## 8. Filter, skip và retry: COMPLETED không nhất thiết là đầy đủ

Giả sử trong 100 item:

- 95 item hợp lệ.
- 3 item bị filter theo business rule.
- 2 item sai được phép skip và đưa vào quarantine.

Một Job có thể báo `COMPLETED`, kể cả khi đã bỏ qua 2 item theo cấu hình skip. Nếu nghiệp vụ **không cho phép skip**, cần assert:

~~~java
assertEquals(0, step.getReadSkipCount());
assertEquals(0, step.getProcessSkipCount());
assertEquals(0, step.getWriteSkipCount());
~~~

Nếu skip được cho phép, phải kiểm **đúng ID**, lý do và kết quả quarantine; không chỉ kiểm tổng skip count vì có thể bỏ nhầm item quan trọng.

Một listener có thể gắn mã ExitStatus tùy biến như `COMPLETED WITH SKIPS`. Test cần kiểm mã nếu đó là hợp đồng flow, nhưng vẫn phải kiểm StepExecution và kết quả dữ liệu.

**Retry count khác rollback count.** Một rollback có thể khiến nhiều item được xử lý lại; một HTTP client có thể retry nhiều lần mà Step không rollback tương ứng. Không lấy `rollbackCount` đặt tên thành retry count.

## 9. Kiểm transaction bằng dữ liệu đã commit

Giả sử chunk size 2; processor gặp exception không retryable ở item 3:

~~~text
Execution #101
  item 1, 2 -> COMMIT
  item 3    -> error, ROLLBACK chunk
  Job       -> FAILED

Output đúng sau lần lỗi: [1, 2]
~~~

Test chỉ kiểm `ExitStatus.FAILED` chưa chứng minh rollback. Phải đọc dữ liệu:

~~~java
assertEquals(BatchStatus.FAILED, first.getStatus());

List<Long> ids = jdbc.queryForList(
        "SELECT id FROM target_orders ORDER BY id",
        Long.class);
assertEquals(List.of(1L, 2L), ids);
~~~

Giả định JDBC writer cùng transaction resource thích hợp, reader có thứ tự ổn định và lỗi không được skip/retry. Nếu writer gọi HTTP API nằm ngoài transaction, rollback database không tự hủy side effect đã gửi.

Tránh bọc cả bài integration test bằng `@Transactional` mà không xem xét Batch transaction; rollback của test framework có thể che khuất commit thật cần kiểm.

## 10. Restart: kiểm JobInstance thay vì chỉ exit code của lần hai

~~~text
JobInstance #42
 businessDate=2026-11-16
       |
       +-- JobExecution #101: FAILED
       |
       +-- JobExecution #102: COMPLETED
~~~

Để chứng minh restart đúng:

~~~java
assertEquals(BatchStatus.FAILED, first.getStatus());
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

assertNotEquals(first.getId(), restarted.getId());

assertEquals(
        first.getJobInstance().getInstanceId(),
        restarted.getJobInstance().getInstanceId());
~~~

Kèm kiểm dữ liệu cuối đầy đủ, không duplicate và Step đã hoàn thành có được bỏ qua theo cấu hình hay không.

Nếu lần hai thêm identifying `run.id` mới, Spring Batch có thể tạo **JobInstance mới**. Trạng thái lần hai COMPLETED không chứng minh checkpoint của instance lỗi đã được khôi phục.

Khi một JobInstance đã COMPLETED, cùng identifying JobParameters thường bị từ chối chạy lại:

~~~java
// Ví dụ trong test độc lập có Job đã COMPLETED.
assertThrows(JobInstanceAlreadyCompleteException.class,
        () -> launcherTestUtils.launchJob(sameParameters));
~~~

Kiểm thêm rằng bảng đích không bị ghi lại trong lần gọi bị từ chối. Đừng xóa metadata `BATCH_*` giữa failure và restart để làm test “chạy được”.

## 11. Nếu output là file, API hoặc message

**File CSV:** kiểm file tồn tại, header, encoding, số dòng, đúng ID/value, CSV escaping và checksum nếu cần. File staging `.part` không nên bị downstream đọc trước khi publish thành công.

~~~java
Path output = Path.of(tempDir.toString(), "orders.csv");
List<String> lines = Files.readAllLines(
        output, StandardCharsets.UTF_8);

assertEquals(3, lines.size());  // Header và 2 dòng.
assertEquals("id,amount", lines.get(0));
assertTrue(lines.contains("1001,120"));
assertTrue(lines.contains("1002,230"));
~~~

Với CSV có dấu phẩy, nháy kép hoặc newline trong field, dùng CSV parser thực sự thay cho tách chuỗi đơn giản. Thư mục output test nên được tách bằng `@TempDir`.

**HTTP API:** kiểm endpoint, method, body, số request, idempotency key và kết quả của fake server. Mock luôn trả HTTP 200 mà không kiểm payload có thể để lọt lỗi mapping.

**Message broker:** kiểm topic, message key, schema, correlation ID, side effect của consumer hoặc ACK theo giao thức. Không chỉ kiểm producer Job COMPLETED.

**Thanh toán:** nếu server đã nhận lệnh nhưng client timeout rồi retry, phải dùng idempotency key ổn định theo business operation, và test tác dụng nghiệp vụ chỉ xảy ra một lần.

## 12. Job async: phải đợi trạng thái terminal

Với `TaskExecutor` bất đồng bộ, lời gọi start/launch có thể trả về khi Job vẫn `STARTED`:

~~~text
Test thread:
  launch -> nhận execution ID -> assert quá sớm

Worker thread:
  read -> process -> write -> COMMIT -> COMPLETED
~~~

Hướng tiếp cận:

1. Nhận execution ID.
2. Đợi tới trạng thái terminal bằng synchronization hoặc polling có timeout.
3. Đọc lại JobExecution persisted từ JobRepository/JobExplorer.
4. Assert trạng thái cuối và output đã commit.

Ví dụ pseudocode dùng Awaitility nếu dự án có dependency:

~~~java
await().atMost(Duration.ofSeconds(30)).untilAsserted(() -> {
    JobExecution latest = jobExplorer.getJobExecution(executionId);
    assertNotNull(latest);

    BatchStatus s = latest.getStatus();
    assertTrue(s == BatchStatus.COMPLETED
            || s == BatchStatus.FAILED
            || s == BatchStatus.STOPPED);
});

// Tiếp tục assert trạng thái kỳ vọng cụ thể và dữ liệu.
~~~

Tránh dùng `Thread.sleep` cố định làm điều kiện hoàn tất. Không suy luận “launch không ném exception” tức Job đã xử lý thành công.

## 13. Input rỗng: COMPLETED có thể đúng

Một Job không có dữ liệu đầu vào không nhất thiết là lỗi. Test cần xuất phát từ **hợp đồng nghiệp vụ**:

| Hợp đồng | Kỳ vọng khi không có input |
| --- | --- |
| Không có đơn hàng ngày đó là bình thường | COMPLETED, output rỗng, audit no-data nếu cần. |
| Mỗi ngày bắt buộc có file input | FAILED hoặc mã cảnh báo theo thiết kế. |
| Báo cáo rỗng vẫn phải có header | File có đúng header và schema. |
| Đối soát cần dữ liệu từ hai nguồn | Thiếu một nguồn phải được phát hiện. |

Hãy có một test input rỗng **và** một test input có dữ liệu cụ thể. Chỉ kiểm kịch bản rỗng sẽ không chứng minh reader/processor/writer xử lý đúng khi có dữ liệu.

## 14. Mutation test giúp thấy test thiếu bằng chứng

Trong nhánh thử nghiệm, cố ý tạo một lỗi nhỏ:

- Đổi điều kiện ngày trong SQL.
- Xóa điều kiện tenant.
- Cho processor filter một item hợp lệ.
- Đổi phép tính amount nhân 100 thành nhân 10.
- Ghi sai cột hoặc bỏ một field trong payload API.
- Cho writer tạo duplicate sau restart.

Test chỉ kiểm `COMPLETED` có thể xanh; test kiểm **business ID, value, scope, idempotency** phải đỏ. Sau thử nghiệm phải trả code về đúng.

Đây là một cách đánh giá chất lượng assertion: test có thực sự nhạy với những thay đổi sai mà hệ thống cần phòng ngừa hay không?

## 15. Test ở các tầng khác nhau

| Cấp kiểm thử | Nội dung chính |
| --- | --- |
| Unit test ItemProcessor | Input, output, validation, filter, exception. |
| Unit test writer mapping | SQL bind parameter, file line, API payload. |
| Step integration | Read/write/filter/skip/rollback và dữ liệu. |
| Job integration | Flow, JobParameters, JobRepository và outcome. |
| Recovery integration | FAILED -> restart, checkpoint, không duplicate. |
| End-to-end | Downstream nhận dữ liệu đúng, publish/audit đầy đủ. |

Một test nhỏ không cần bao phủ tất cả. Nhưng nếu **mọi test** chỉ assert exit code, không có lớp nào chứng minh nghiệp vụ đúng.

## 16. Spring Batch 5.2 và 6.x

| Chủ đề | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Test launcher | `JobLauncherTestUtils.launchJob(params)` | `JobOperatorTestUtils.startJob(params)` |
| Domain packages | Nhiều type trong `org.springframework.batch.core` | Chia package theo job, step, job.parameters |
| Tasklet builder | `new StepBuilder(name, repo).tasklet(tasklet, tx)` | API builder tương ứng phiên bản 6.x |
| JobRepository | Boot 3 có thể dùng JDBC auto-configuration | Cần xác nhận JDBC infrastructure phù hợp; có cấu hình mặc định resourceless |
| Assertions | Status + metadata + dữ liệu | **Giữ nguyên nguyên tắc** |

Trên Spring Batch 6.x, nếu cần chứng minh metadata persisted và restart, phải dùng JDBC JobRepository đúng phiên bản và schema tương ứng. Resourceless repository không thay thế được test lịch sử bảng `BATCH_*`.

## 17. Ma trận kiểm thử

| Kịch bản | Status kỳ vọng | Ngoài status phải kiểm |
| --- | --- | --- |
| 2 item hợp lệ | COMPLETED | Đúng 2 ID và tổng tiền. |
| Input rỗng hợp lệ | COMPLETED | Output rỗng đúng hợp đồng. |
| SQL lọc sai kỳ | Có thể COMPLETED | Test phải đỏ do thiếu dữ liệu. |
| Processor filter nhầm | Có thể COMPLETED | Output ID thiếu và filterCount sai. |
| Step skip record được phép | Có thể COMPLETED | Quarantine, skip count và dữ liệu còn lại. |
| Lỗi item giữa chunk | FAILED | Chunk chưa commit rollback. |
| Restart sau FAILED | COMPLETED ở execution mới | Cùng JobInstance; không duplicate. |
| Chạy lại lô đã COMPLETED | Bị từ chối | Không có side effect mới. |
| File sai header | Có thể COMPLETED | File content/schema assertion đỏ. |
| Request API sai body | Có thể COMPLETED | Contract assertion đỏ. |
| Job async | Terminal khi đã đợi | Metadata và output persisted. |

## 18. Các sai lầm thường gặp

**Chỉ assert ExitStatus.COMPLETED.** Không chứng minh dữ liệu đúng.

**Chỉ assert process exit code 0.** Process và JobExecution không luôn ánh xạ một-một.

**Chỉ assert BatchStatus.COMPLETED.** Framework không tự biết mọi business invariant.

**Test fixture rỗng.** Query sai vẫn có thể trả 0 row.

**Chỉ assert COUNT(*).** Đúng số lượng nhưng sai ID/giá trị vẫn là lỗi.

**Tin read/writeCount của Tasklet SQL.** Những count này không tự đo tác động SQL của Tasklet.

**Không kiểm filter và skip.** Job hoàn thành sau khi bỏ nhầm record.

**Dùng identifying run.id mới trong test restart.** Tạo JobInstance khác.

**Không đợi async Job kết thúc.** Test có thể đọc trạng thái cũ.

**Không làm sạch dữ liệu giữa test độc lập.** Dữ liệu dư tạo kết quả xanh giả.

**Xóa metadata giữa failed và restart.** Mất lịch sử, checkpoint và ý nghĩa test.

**Mock writer không ghi thật mà vẫn gọi là integration test dữ liệu.** Chỉ còn kiểm wiring và flow.

## 19. Bài tập thực hành

**Bài 1 — Test xanh giả.** Viết Job nhập đơn hàng ngày 16/11, chỉ kiểm exit code. Đổi SQL sang ngày 15/11 và chứng minh test có thể vẫn xanh. Thêm assertion ID/tổng tiền để bắt lỗi.

**Bài 2 — Kiểm scope.** Seed thêm dữ liệu tenant khác và ngày khác. Đảm bảo output không chứa record ngoài scope, kể cả khi tổng row count tình cờ đúng.

**Bài 3 — Filter/skip.** Tạo Step đọc 100 item, filter 2 và skip 1 theo policy. Kiểm metadata, output và quarantine; đổi filter sai để test đỏ.

**Bài 4 — Transaction.** Với chunk size 2, gây lỗi item 3. Kiểm Job FAILED và chỉ item 1,2 được commit.

**Bài 5 — Restart.** Tắt lỗi, restart cùng identifying params. Assert cùng JobInstance ID, execution ID mới và dữ liệu cuối đủ, không trùng.

**Bài 6 — CSV.** Kiểm header, encoding, schema, ID, amount và file chưa publish trước khi hoàn tất.

**Bài 7 — API.** Giả lập server xử lý thành công nhưng client timeout. Retry/restart bằng cùng idempotency key rồi kiểm tác dụng nghiệp vụ chỉ xảy ra một lần.

**Bài 8 — Async.** Dùng executor bất đồng bộ, đợi terminal status rồi mới kiểm dữ liệu. So sánh với test assert ngay sau start.

## 20. Tài liệu tham khảo

- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 6.x — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch — Chunk-Oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch — Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [Spring Batch 5.2 — JobExecution API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobExecution.html)
- [Spring Batch 5.2 — StepExecution API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepExecution.html)

