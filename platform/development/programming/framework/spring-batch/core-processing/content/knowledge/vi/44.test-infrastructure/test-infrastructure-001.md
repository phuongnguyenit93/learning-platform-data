# JobRepository dành cho test trong Spring Batch

## 1. Vai trò của JobRepository khi kiểm thử

Spring Batch không chỉ đọc và ghi dữ liệu nghiệp vụ. Mỗi lần Job chạy, framework còn quản lý danh tính của lần xử lý, trạng thái thực thi, lỗi, số lần thử và dữ liệu checkpoint. **JobRepository** là hạ tầng chịu trách nhiệm lưu những metadata này.

Một bài kiểm thử Job có thể kết thúc với trạng thái thành công nhưng vẫn bỏ sót lỗi nghiêm trọng: mất checkpoint, khởi tạo JobInstance sai, chạy lại Step đã hoàn thành hoặc coi lần restart là một lần xử lý mới. Vì vậy, test hạ tầng Batch cần chứng minh metadata được **ghi, đọc lại và duy trì qua các execution**.

Mục tiêu của bài học:

- Hiểu trách nhiệm của JobRepository so với JobLauncher, JobOperator và JobExplorer.
- Chọn repository phù hợp cho unit test, integration test và bài kiểm thử restart.
- Tạo **JDBC JobRepository** dành riêng cho test, cùng schema Batch và database nghiệp vụ.
- Sử dụng **@SpringBatchTest**, **JobRepositoryTestUtils** và công cụ chạy Job trong test.
- Truy vấn JobInstance, JobExecution, StepExecution và ExecutionContext sau khi Job chạy.
- Dọn metadata an toàn giữa các test mà không làm mất lịch sử trong một kịch bản restart.
- Hiểu khác biệt cấu hình giữa Spring Batch 5.x và 6.x.

## 2. Những gì JobRepository lưu giữ

~~~text
JUnit Jupiter
     |
     v
@SpringBatchTest
     |
     +--> JobLauncher / JobOperator ----> Job ----> Step
     |                                      |
     |                                      v
     |                                 Business DB
     |
     +--> JobRepository ----------------> Metadata DB
     |                                      |
     |                                      +-- BATCH_JOB_INSTANCE
     |                                      +-- BATCH_JOB_EXECUTION
     |                                      +-- BATCH_JOB_EXECUTION_PARAMS
     |                                      +-- BATCH_JOB_EXECUTION_CONTEXT
     |                                      +-- BATCH_STEP_EXECUTION
     |                                      +-- BATCH_STEP_EXECUTION_CONTEXT
     |
     +--> JobExplorer ------------------> Đọc metadata
     |
     +--> JobRepositoryTestUtils -------> Tạo/xóa test metadata
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| **JobInstance** | Một lần xử lý về mặt nghiệp vụ, được xác định bởi tên Job và các identifying JobParameters. |
| **JobExecution** | Một lần cố gắng thực thi một JobInstance; một instance có thể có nhiều execution khi restart. |
| **StepExecution** | Trạng thái của một Step tại một lần thực thi, gồm số đếm read/write, commit, rollback và lỗi. |
| **ExecutionContext** | Dữ liệu key/value được lưu ở phạm vi Job hoặc Step để khôi phục trạng thái, chẳng hạn vị trí đọc đã checkpoint. |
| **JobRepository** | API tạo, cập nhật và truy xuất metadata của các đối tượng trên. |
| **JobExplorer** | API tra cứu lịch sử Job/Step, phù hợp cho các phép kiểm chỉ đọc. |
| **JobRepositoryTestUtils** | Tiện ích của spring-batch-test để chuẩn bị hoặc dọn metadata trong test database. |

Ví dụ, với tên Job **importOrders** và identifying parameter **businessDate=2026-11-16**, lần chạy đầu thất bại và lần sau restart:

~~~text
JobInstance #25
  name = importOrders
  identifying parameter = businessDate:2026-11-16
  |
  +-- JobExecution #87: FAILED
  |     +-- validateStep: COMPLETED
  |     +-- importStep: FAILED
  |
  +-- JobExecution #88: COMPLETED
        +-- importStep: COMPLETED
~~~

Hai JobExecution khác ID nhưng cùng JobInstance ID. JobRepository phải bảo toàn điều đó; nếu test dùng một tham số định danh mới ở execution thứ hai, framework tạo JobInstance khác và test không kiểm chứng được khả năng restart.

**ExecutionContext cần được lưu thực sự**, không chỉ tồn tại trong một đối tượng Java trên heap. Chẳng hạn JDBC cursor reader có thể lưu vị trí checkpoint vào Step ExecutionContext trước khi transaction commit. Sau lỗi, StepExecution mới sẽ dùng dữ liệu đã lưu để tiếp tục.

## 3. Nên dùng loại repository nào trong test?

| Phép thử | Cách triển khai | Có thể chứng minh điều gì? |
| --- | --- | --- |
| Unit test processor/validator/listener | Mock hoặc fixture domain qua MetaDataInstanceFactory; không cần chạy Job thật | Logic cục bộ của component. |
| Integration test Job, trạng thái execution, restart | **JDBC JobRepository** trên H2 hoặc database test | Metadata được persist, JobInstance/execution ID, checkpoint, restart, Step count. |
| Test SQL, isolation, locking đặc thù production | JDBC JobRepository trên PostgreSQL/MySQL/Oracle/... bằng Testcontainers | Hành vi gần database vận hành. |
| Job đơn lẻ không cần lịch sử hoặc restart | ResourcelessJobRepository khi được hỗ trợ | Chạy một lần với hạ tầng tối giản; không dùng để khẳng định metadata bền vững. |

**H2 in-memory** phù hợp với nhiều integration test nếu mọi execution trong một test chạy trong cùng database đang sống. Nó không kiểm tra được restart sau khi **toàn bộ JVM thoát** vì dữ liệu trong RAM có thể biến mất. Muốn thử quá trình phục hồi giữa hai tiến trình, sử dụng database bền vững hoặc container database được giữ qua cả hai lần khởi động.

Một điều chỉnh quan trọng về phiên bản:

- **Spring Batch 5.2.x với Spring Boot 3.x:** ví dụ thực hành dưới đây dùng JDBC repository được cấu hình qua Boot Batch auto-configuration và tiện ích **JobLauncherTestUtils**.
- **Spring Batch 6.x:** tiện ích chạy Job trong test là **JobOperatorTestUtils**. Trong Spring Batch 6 thuần, cấu hình **@EnableBatchProcessing** mặc định cung cấp **ResourcelessJobRepository**; để dùng JDBC phải cấu hình repository JDBC, ví dụ **@EnableJdbcJobRepository**, hoặc cơ chế auto-configuration tương thích trong hệ sinh thái Spring Boot. Không giả định thêm dependency H2 thì repository tự chuyển sang JDBC.

## 4. Tạo test infrastructure với Spring Batch 5.2 và Spring Boot 3

### 4.1. Dependency

Ví dụ Gradle dùng phiên bản Spring Batch do Spring Boot BOM quản lý:

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

**spring-batch-test** cung cấp @SpringBatchTest, JobLauncherTestUtils, JobRepositoryTestUtils, MetaDataInstanceFactory và các listener hỗ trợ StepScope/JobScope trong bài kiểm thử.

### 4.2. Dùng profile riêng cho test

Tạo file **src/test/resources/application-batchtest.properties**:

~~~properties
# Database dùng riêng cho test.
spring.datasource.url=jdbc:h2:mem:batchrepo_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Khởi tạo bảng metadata BATCH_* bằng script do Boot quản lý.
spring.batch.jdbc.initialize-schema=always

# Không tự chạy các Job khi dựng application context.
spring.batch.job.enabled=false

# Khởi tạo bảng nghiệp vụ thử nghiệm.
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:batch-business-schema.sql
~~~

Tạo file **src/test/resources/batch-business-schema.sql**:

~~~sql
CREATE TABLE test_audit (
    event_name VARCHAR(100) NOT NULL
);
~~~

Các bảng **BATCH_*** do Spring Batch quản lý. **test_audit** là bảng nghiệp vụ riêng của test, cần dọn thủ công khi chuẩn bị ca kiểm thử kế tiếp.

Property **spring.batch.jdbc.initialize-schema=always** thuộc Spring Boot Batch auto-configuration. Nếu cấu hình JobRepository bằng Spring Batch thuần hoặc đã vô hiệu hóa Boot auto-configuration, phải chủ động chạy đúng script schema theo database và phiên bản Batch. Đặc biệt, thêm **@EnableBatchProcessing** vào ứng dụng Boot 3 có thể thay đổi cơ chế auto-config; ví dụ này cố ý để Boot thiết lập JDBC infrastructure.

Nếu có nhiều DataSource, cần chọn rõ DataSource cho metadata và transaction manager của JobRepository; không dựa vào thứ tự đăng ký bean. JobRepository có thể dùng database metadata khác với database nghiệp vụ, nhưng khi đó cần kiểm thử kỹ khả năng đồng bộ/rollback giữa hai nguồn.

### 4.3. Hệ thống bảng metadata

Các bảng thông dụng trong JDBC JobRepository:

~~~text
BATCH_JOB_INSTANCE
BATCH_JOB_EXECUTION
BATCH_JOB_EXECUTION_PARAMS
BATCH_JOB_EXECUTION_CONTEXT
BATCH_STEP_EXECUTION
BATCH_STEP_EXECUTION_CONTEXT
~~~

Tùy database còn có các sequence hoặc bảng mô phỏng sequence để sinh ID. Có thể cấu hình tiền tố bảng khác **BATCH_**, nhưng script khởi tạo phải tương ứng. Khi thiếu bảng, bảng sai phiên bản hoặc sequence không đúng, test thường lỗi ngay lúc tạo JobExecution.

Trong cùng một test, hãy để dữ liệu này tồn tại **giữa lần fail và lần restart**. Xóa metadata giữa hai execution sẽ làm mất lịch sử và checkpoint cần kiểm chứng.

## 5. Viết Job mẫu để kiểm metadata

Job mẫu có hai Step:

1. **preparationStep** ghi một hàng vào bảng nghiệp vụ và lưu marker vào Step ExecutionContext.
2. **unstableStep** gây lỗi đúng một lần bằng cờ AtomicBoolean; lần chạy lại sẽ thành công.

Từ đó có thể xác minh repository giữ đúng lịch sử Step: Step thứ nhất đã hoàn thành sẽ không chạy lại trên restart theo cấu hình mặc định, Step thứ hai có hai execution.

**RepositorySampleJobConfiguration.java**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class RepositorySampleJobConfiguration {

    @Bean
    AtomicBoolean failNextAttempt() {
        return new AtomicBoolean(true);
    }

    @Bean
    Step preparationStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbcTemplate) {

        return new StepBuilder("preparationStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    jdbcTemplate.update(
                        "INSERT INTO test_audit(event_name) VALUES (?)",
                        "prepared");

                    contribution.getStepExecution()
                            .getExecutionContext()
                            .putString("marker", "done");

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Step unstableStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            AtomicBoolean failNextAttempt) {

        return new StepBuilder("unstableStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    if (failNextAttempt.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Injected test failure");
                    }
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    Job repositorySampleJob(
            JobRepository jobRepository,
            @Qualifier("preparationStep") Step preparationStep,
            @Qualifier("unstableStep") Step unstableStep) {

        return new JobBuilder("repositorySampleJob", jobRepository)
                .start(preparationStep)
                .next(unstableStep)
                .build();
    }
}
~~~

AtomicBoolean là cơ chế **fault injection của test**. Đừng dùng biến bộ nhớ toàn cục tương tự như một nguồn trạng thái restart cho production: JVM có thể bị tắt hoặc ứng dụng có thể chạy nhiều instance. Trạng thái cần khôi phục phải nằm ở nơi lưu trữ thích hợp, ví dụ ExecutionContext hoặc bảng nghiệp vụ.

## 6. Test JobRepository bằng @SpringBatchTest

Ví dụ dưới đây khai báo một ứng dụng Boot tối giản, import duy nhất Job mẫu. Điều này làm test context dễ kiểm soát hơn khi ứng dụng chính có nhiều Job.

**JobRepositoryIntegrationTest.java**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
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
@SpringBootTest(classes = JobRepositoryIntegrationTest.TestApplication.class)
class JobRepositoryIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(RepositorySampleJobConfiguration.class)
    static class TestApplication {
    }

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Autowired
    JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    JobRepository jobRepository;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    AtomicBoolean failNextAttempt;

    @Autowired
    @Qualifier("repositorySampleJob")
    Job job;

    @BeforeEach
    void resetState() {
        launcherTestUtils.setJob(job);
        failNextAttempt.set(true);

        // Chỉ dùng trên database dành riêng cho test.
        repositoryTestUtils.removeJobExecutions();
        jdbcTemplate.update("DELETE FROM test_audit");
    }

    @Test
    void metadataIsPersistedAcrossJobRestart() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessKey", "case-576")
                .toJobParameters();

        // Execution 1: preparationStep hoàn thành, unstableStep lỗi.
        JobExecution first = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertNotNull(first.getId());

        JobExecution storedFirst = jobRepository.getLastJobExecution(
                "repositorySampleJob", parameters);
        assertNotNull(storedFirst);
        assertEquals(first.getId(), storedFirst.getId());

        assertEquals(1L, jobRepository.getStepExecutionCount(
                first.getJobInstance(), "preparationStep"));
        assertEquals(1L, jobRepository.getStepExecutionCount(
                first.getJobInstance(), "unstableStep"));

        // Dữ liệu lưu trong Step ExecutionContext được đọc lại.
        StepExecution savedStep = jobRepository.getLastStepExecution(
                first.getJobInstance(), "preparationStep");
        assertNotNull(savedStep);
        assertEquals(BatchStatus.COMPLETED, savedStep.getStatus());
        assertEquals("done",
                savedStep.getExecutionContext().getString("marker"));

        // Execution 2 dùng chính xác bộ JobParameters của lần 1.
        JobExecution restarted = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
        assertNotEquals(first.getId(), restarted.getId());
        assertEquals(first.getJobInstance().getInstanceId(),
                     restarted.getJobInstance().getInstanceId());

        // Step đã hoàn thành không chạy lại mặc định.
        assertEquals(1L, jobRepository.getStepExecutionCount(
                restarted.getJobInstance(), "preparationStep"));
        assertEquals(2L, jobRepository.getStepExecutionCount(
                restarted.getJobInstance(), "unstableStep"));

        // Side effect nghiệp vụ của preparationStep chỉ xuất hiện một lần.
        Integer auditCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM test_audit", Integer.class);
        assertEquals(1, auditCount);

        // Repository trả về execution mới nhất sau restart.
        JobExecution storedRestart = jobRepository.getLastJobExecution(
                "repositorySampleJob", parameters);
        assertNotNull(storedRestart);
        assertEquals(restarted.getId(), storedRestart.getId());
    }
}
~~~

Test làm rõ bốn lớp bằng chứng:

- **Trạng thái**: execution đầu FAILED và execution sau COMPLETED.
- **Danh tính**: ID JobExecution khác nhau, ID JobInstance giống nhau.
- **Lịch sử Step**: preparationStep chỉ có một StepExecution, unstableStep có hai.
- **Persistence**: metadata và ExecutionContext được đọc lại từ JobRepository; dữ liệu nghiệp vụ chỉ ghi một lần.

Với Job đã COMPLETED, thử chạy lại **cùng identifying JobParameters** phải bị từ chối theo quy tắc JobInstanceAlreadyComplete. Tạo một identifying run.id khác là một lần xử lý mới, không phải retry của instance đã hoàn thành.

### Kết quả kỳ vọng

| Thông tin | Sau lần chạy thứ nhất | Sau restart |
| --- | --- | --- |
| JobInstance | Một ID duy nhất | Giữ nguyên ID |
| JobExecution mới nhất | FAILED | COMPLETED |
| Số JobExecution | 1 | 2 |
| preparationStep executions | 1 | 1 |
| unstableStep executions | 1 | 2 |
| Step ExecutionContext marker | done | Vẫn đọc được done |
| Số dòng test_audit | 1 | 1 |

## 7. JobRepositoryTestUtils và vòng đời cleanup

**JobRepositoryTestUtils** giúp tạo/xóa metadata trong test repository. Ví dụ:

~~~java
// Xóa các JobExecution và metadata liên quan trong test repository.
repositoryTestUtils.removeJobExecutions();

// Tạo execution giả lập phục vụ một tình huống kiểm tra.
var executions = repositoryTestUtils.createJobExecutions(2);

// Xóa đúng những execution vừa tạo.
repositoryTestUtils.removeJobExecutions(executions);
~~~

Lời gọi **removeJobExecutions()** không tham số có thể xóa toàn bộ lịch sử Batch mà repository đang quản lý. Chỉ dùng khi đã biết chắc repository trỏ vào database test biệt lập. Nó **không dọn dữ liệu nghiệp vụ**; bảng test_audit, file xuất, message hoặc side effect ngoài database phải được xử lý bằng cơ chế khác.

Chu kỳ chuẩn:

~~~text
@BeforeEach
  1. Đặt lại fault injection.
  2. Dọn metadata từ test trước.
  3. Dọn và seed dữ liệu nghiệp vụ.
    |
    v
Test body
  - launchJob(params) -> FAILED
  - giữ nguyên metadata và checkpoint
  - launchJob(cùng params) -> COMPLETED
  - assert JobRepository + dữ liệu
    |
    v
Kết thúc test
  - Test khác bắt đầu với trạng thái cô lập
~~~

Đừng gọi cleanup **giữa hai execution của cùng một test restart**. Khi đó lần hai có thể trở thành một lần chạy từ đầu, dù assertion trạng thái Job vẫn xanh.

Trong test song song, hai class dùng chung một H2 database và cùng gọi removeJobExecutions có thể xóa metadata của nhau. Khi muốn parallelism, hãy dùng database/schema tách biệt, có chiến lược sở hữu riêng các execution hoặc tắt parallel cho nhóm integration test chia sẻ kho metadata.

### MetaDataInstanceFactory khác gì JDBC repository?

Unit test listener đôi khi chỉ cần một StepExecution để kiểm tra logic:

~~~java
StepExecution stepExecution =
        MetaDataInstanceFactory.createStepExecution();

stepExecution.setReadCount(0);
// Kiểm logic của StepExecutionListener trên fixture này.
~~~

Fixture này không chứng minh một StepExecution đã được lưu trong JDBC JobRepository. Chỉ những bài test thực sự chạy Job/Step và đọc lại từ repository mới kiểm tra được tính bền vững, transaction, checkpoint và restart.

## 8. Truy vấn metadata để chẩn đoán

Sau bài test trên, có thể kiểm tra trực tiếp bằng SQL:

~~~sql
SELECT ji.JOB_NAME,
       ji.JOB_INSTANCE_ID,
       je.JOB_EXECUTION_ID,
       je.STATUS,
       je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'repositorySampleJob'
ORDER BY je.JOB_EXECUTION_ID;
~~~

Kỳ vọng hai hàng kết quả có **cùng JOB_INSTANCE_ID**; execution thứ nhất FAILED, execution thứ hai COMPLETED.

Với Step:

~~~sql
SELECT se.JOB_EXECUTION_ID,
       se.STEP_NAME,
       se.STATUS,
       se.READ_COUNT,
       se.WRITE_COUNT,
       se.COMMIT_COUNT,
       se.ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION se
ORDER BY se.JOB_EXECUTION_ID, se.STEP_EXECUTION_ID;
~~~

Trong Job mẫu dùng **TaskletStep**, readCount và writeCount thường bằng 0 vì không có chunk reader/writer. Không sử dụng số đếm này như bằng chứng số dòng INSERT của một Tasklet. Khi dùng Step chunk-oriented, các count mới phản ánh item-level processing.

Truy vấn SQL trực tiếp hữu ích cho giai đoạn chẩn đoán; khi viết code kiểm thử, ưu tiên JobExplorer/JobRepository để không bị phụ thuộc chặt vào tên bảng, table prefix và serializer của từng phiên bản.

## 9. Transaction và tính đúng của bài kiểm thử

### 9.1. Không đặt @Transactional lên toàn bộ bài integration test

Nếu cả phương thức test được bao bởi transaction của test framework, rollback tự động khi test kết thúc có thể làm khó việc quan sát commit thực của Step. Hãy để Batch tự quản lý transaction, rồi xác minh dữ liệu và metadata sau khi launchJob trả về.

Trong chunk-oriented processing, Spring Batch cập nhật checkpoint ở ranh giới commit theo thiết kế Step. Nếu writer làm việc với cùng JDBC transaction, chunk lỗi sẽ rollback dữ liệu chưa commit. Nếu writer gửi HTTP request, email hoặc message tới hệ thống bên ngoài, side effect có thể không rollback theo JDBC metadata. Khi đó cần bổ sung idempotency, khóa duy nhất, outbox hoặc đối soát và bài test cho các tình huống đó.

### 9.2. H2 không mô phỏng mọi hành vi production

Sự khác biệt có thể bao gồm cú pháp SQL, sequence, kiểu dữ liệu lớn, transaction isolation, deadlock, locking và cấu hình table prefix. Với Job phụ thuộc các đặc điểm đó, sử dụng Testcontainers chạy cùng hệ database production và khởi tạo script metadata phù hợp.

### 9.3. Tránh những nguyên nhân khiến test xanh giả

| Sai sót | Hậu quả |
| --- | --- |
| Chỉ assert BatchStatus.COMPLETED | Không phát hiện metadata không tồn tại hoặc JobInstance sai. |
| Dùng launchJob() không truyền tham số khi cần restart | Tiện ích 5.x có thể tự thêm tham số ngẫu nhiên, tạo JobInstance mới. |
| Thêm run.id mới vào lần restart | Test chuyển thành chạy một instance khác. |
| Xóa BATCH_* giữa lần fail và restart | Mất checkpoint và lịch sử thực thi. |
| Chạy với ResourcelessJobRepository rồi assert phục hồi JDBC | Không có metadata JDBC để kiểm chứng. |
| Chia sẻ DB giữa các test song song | Cleanup của test này có thể phá dữ liệu test khác. |
| Dùng H2 RAM cho bài test sau khi JVM chết | Database có thể biến mất cùng tiến trình. |
| Nhầm DataSource nghiệp vụ với DataSource metadata | Quan sát nhầm database hoặc lỗi schema. |
| Chỉ kiểm đối tượng JobExecution trả về trong RAM | Bỏ sót việc metadata không được persist như kỳ vọng. |

## 10. Khác biệt với Spring Batch 6.x

Những nguyên tắc JobInstance, JobExecution, StepExecution, ExecutionContext vẫn áp dụng. Tuy vậy, khi chuyển từ Spring Batch 5.2 sang 6.x cần chú ý:

| Hạng mục | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Tiện ích chạy Job trong spring-batch-test | JobLauncherTestUtils.launchJob(params) | JobOperatorTestUtils.startJob(params) |
| Dọn metadata | JobRepositoryTestUtils | JobRepositoryTestUtils |
| Package domain chính | org.springframework.batch.core.Job/JobExecution/... | Các package con như core.job, core.step, core.job.parameters |
| Repository mặc định với @EnableBatchProcessing thuần | Theo cấu hình JDBC/Batch 5 tương ứng | Resourceless; muốn JDBC cần bật/cấu hình repository JDBC |
| JUnit | JUnit Jupiter được hỗ trợ | JUnit Jupiter; JUnit 4 không còn được hỗ trợ |

Khi chuyển ví dụ, hãy điều chỉnh import, builder và cấu hình hạ tầng theo tài liệu đúng phiên bản; đặc biệt xác nhận bean JobRepository đang là JDBC và schema metadata đã được tạo. Test chỉ có ý nghĩa kiểm persistence khi nó thực sự chạy trên một metadata store bền vững trong vòng đời kịch bản.

## 11. Bài tập

1. **Persistence cơ bản:** Tạo một Job một Step, chạy với identifying parameter cố định, dùng JobRepository.getLastJobExecution để đọc lại ID/status và so với kết quả launchJob.
2. **Restart:** Chèn lỗi ở Step thứ hai, chạy lại cùng JobParameters và chứng minh một JobInstance có hai JobExecution nhưng Step đầu không chạy lại.
3. **Giới hạn JobInstance:** Sau khi Job COMPLETED, thử launch lại cùng identifying parameters; xác minh không có lần xử lý nghiệp vụ mới.
4. **Phân biệt metadata với dữ liệu nghiệp vụ:** Chỉ xóa bảng nghiệp vụ nhưng giữ BATCH_* rồi thử chạy lại JobInstance đã hoàn thành. Giải thích vì sao repository vẫn từ chối.
5. **Test isolation:** Chạy hai test dùng chung database metadata và sửa thiết kế để mỗi test có database hoặc schema riêng.
6. **Production-like database:** Chuyển từ H2 sang Testcontainers với database thực, kiểm lại schema, transaction và khả năng lấy ExecutionContext sau restart.

Một hạ tầng test tốt cho Spring Batch cần bảo đảm **database riêng**, **JobRepository được persist**, **vòng đời metadata có kiểm soát**, và **assertion chứng minh dữ liệu đã lưu**, từ đó các bài kiểm thử Job/Step/restart mới có nền tảng đáng tin cậy.

## 12. Tài liệu tham khảo

- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 6.x — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch — Infrastructure Configuration](https://docs.spring.io/spring-batch/reference/job/configuring-infrastructure.html)
- [JobRepository API, Spring Batch 5.2](https://docs.spring.io/spring-batch/docs/5.2.4/api/org/springframework/batch/core/repository/JobRepository.html)
- [JobRepositoryTestUtils API](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/JobRepositoryTestUtils.html)
- [Spring Batch — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)

