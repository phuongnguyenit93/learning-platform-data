# Chạy test song song an toàn trong Spring Batch

## 1. Vì sao chạy test song song dễ gây lỗi?

Chạy nhiều bài kiểm thử cùng lúc giúp rút ngắn thời gian chạy test suite, nhất là khi mỗi integration test phải khởi tạo Spring context, tạo transaction và truy cập database. Tuy nhiên, kiểm thử Spring Batch thường dùng chung một số thành phần có trạng thái: **JobRepository**, bảng metadata **BATCH_***, database nguồn và đích, bean trong Spring context, file input/output, hoặc các tiện ích test. Nếu hai test không được tách dữ liệu đúng cách, chúng có thể ảnh hưởng lẫn nhau mặc dù logic xử lý batch hoàn toàn đúng.

Ví dụ, hai test cùng launch Job tên **importCustomersJob** với cùng identifying **JobParameters**:

~~~text
Test A: importCustomersJob + businessDate=2026-11-16
Test B: importCustomersJob + businessDate=2026-11-16
                      |
                      v
            CÙNG JobInstance
                      |
          +-----------+-----------+
          |                       |
  Một test đang chạy       Test kia launch lại
                                  |
                    JobExecutionAlreadyRunningException
                    hoặc trạng thái không như kỳ vọng
~~~

Đây không phải là một race condition ở nghiệp vụ import; hai test đã vô tình cùng điều khiển **một JobInstance**. Một tình huống khác là test A xóa toàn bộ bảng dữ liệu đích trong phần setup đúng lúc test B đang ghi dữ liệu. Test B có thể thất bại ngẫu nhiên, hoặc tệ hơn: pass nhưng kiểm tra một tập kết quả bị can thiệp.

Bài này tập trung vào **hạ tầng kiểm thử Spring Batch**: cách tổ chức dữ liệu, JobParameters, application context và tài nguyên để nhiều test chạy cạnh nhau ổn định. Đây là vấn đề khác với việc cấu hình một Step dùng nhiều thread hoặc chia partition trong chính Job; batch processing có thể tuần tự trong khi **các test launch những JobInstance riêng biệt theo cách song song**.

## 2. Những thành phần có thể bị chia sẻ

| Thành phần | Điều có thể bị chia sẻ | Nguy cơ khi các test chạy đồng thời |
| --- | --- | --- |
| **JobRepository** | Các bảng metadata về JobInstance, JobExecution, StepExecution và ExecutionContext | Cùng identifying JobParameters khiến các test tranh cùng JobInstance; xóa metadata làm hỏng test khác. |
| **Database nghiệp vụ** | Bảng input, output, staging và audit | Dữ liệu test bị xóa, ghi đè, đọc nhầm hoặc vi phạm khóa duy nhất. |
| **Spring ApplicationContext** | Singleton bean, Job, Step, processor, service, mock | Test thay đổi trạng thái bean chung khiến test khác nhận cấu hình hoặc trạng thái sai. |
| **JobLauncher / test utility** | Launcher và đối tượng cấu hình Job để launch | Một test thay đổi Job hoặc tham số tiện ích trong lúc test khác chạy. |
| **Reader / writer / processor** | Cursor, bộ đếm, buffer, cache, đường dẫn file | Một test tiêu thụ dữ liệu hoặc cập nhật trạng thái của test khác. |
| **File system** | File CSV/XML, file xuất, thư mục tạm | Ghi cùng tên file, xóa file mà test khác đang đọc. |
| **Kết nối và transaction** | JDBC pool, database lock, transaction manager | Hết connection, deadlock, timeout hoặc assertion quan sát dữ liệu chưa commit. |
| **Cấu hình test framework** | Spring context cache, global mock reset, các hook trước/sau test | Test dùng context chung nhưng gọi reset, truncate hoặc đóng tài nguyên toàn cục. |

Chạy test song song an toàn không đòi mọi test có một Spring context riêng. Thường có thể **dùng chung các bean không có trạng thái thay đổi theo test** và chia tách những dữ liệu, tham số và tài nguyên có thể bị ghi.

## 3. Quy tắc đầu tiên: mỗi test cần JobInstance riêng

Spring Batch xác định một **JobInstance** dựa trên tên Job và những JobParameters có cờ **identifying**. Hai lần launch có cùng tên Job và cùng identifying parameters trỏ tới cùng JobInstance. Điều này phù hợp khi kiểm thử restart, nhưng thường không phù hợp khi hai test độc lập chạy đồng thời.

### 3.1. Tạo định danh riêng cho mỗi test

Với Spring Batch 5.x:

~~~java
String caseId = UUID.randomUUID().toString();

JobParameters parameters = new JobParametersBuilder()
        .addString("caseId", caseId, true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importCustomersJob, parameters);
~~~

Ở đây **caseId** là một identifying parameter. Mỗi test tạo một giá trị mới, nên Spring Batch có thể tạo JobInstance riêng dù tất cả test đều dùng chung đối tượng Job.

Tránh dùng một bộ tham số cố định cho mọi test:

~~~java
// Không phù hợp cho hai test độc lập cùng launch một Job.
JobParameters parameters = new JobParametersBuilder()
        .addString("caseId", "shared-test", true)
        .toJobParameters();
~~~

Không phải mọi tham số đều tham gia xác định JobInstance. Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("caseId", caseId, true)     // identifying
        .addString("requestedBy", "junit", false) // non-identifying
        .toJobParameters();
~~~

Chỉ thay đổi **requestedBy** không tạo JobInstance mới. Vì vậy, nếu cần phân biệt các test, hãy chắc chắn tham số định danh có cờ identifying.

### 3.2. Ngoại lệ có chủ đích: kiểm thử restart

Một bài test restart phải launch lần thứ hai với **chính identifying JobParameters đã dùng ở lần đầu** để kiểm tra khả năng tiếp tục cùng JobInstance:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("caseId", UUID.randomUUID().toString(), true)
        .toJobParameters();

JobExecution failedRun = jobLauncher.run(job, parameters);
// Giả định lần đầu FAILED do một lỗi được tạo có kiểm soát.

JobExecution restartedRun = jobLauncher.run(job, parameters);
// Cùng JobInstance, JobExecution mới.
~~~

Điều cần tách là **giữa các test restart khác nhau**, mỗi test dùng caseId riêng. Bên trong **một** test restart, cả lần chạy đầu và lần restart dùng lại cùng caseId. Không xóa metadata JobRepository hoặc dữ liệu đã commit giữa hai lần chạy vì chúng chính là trạng thái mà restart cần phục hồi.

## 4. Quy tắc thứ hai: phân vùng dữ liệu nghiệp vụ theo test

Chỉ tạo JobInstance riêng **chưa đủ**. Nếu hai Job đọc cùng bảng input hoặc ghi cùng bảng đích với các khóa trùng nhau, chúng vẫn có thể xung đột.

Một cách đơn giản là thêm **case_id** vào fixture và truy vấn theo caseId, sau đó dùng khóa ghép **(case_id, id)** để mỗi test có không gian dữ liệu riêng.

~~~sql
CREATE TABLE source_customer (
    case_id       VARCHAR(64) NOT NULL,
    id            BIGINT NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (case_id, id)
);

CREATE TABLE imported_customer (
    case_id       VARCHAR(64) NOT NULL,
    id            BIGINT NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (case_id, id)
);
~~~

Ví dụ, hai test có thể đều sử dụng các ID nghiệp vụ **101** và **102**:

~~~text
source_customer

case_id   id    customer_name
--------  ----  -------------
case-A    101   An
case-A    102   Binh
case-B    101   Chi
case-B    102   Dung
~~~

Hai test không tranh khóa ghi vì cặp **(case_id, id)** là khác nhau. Tuy nhiên, cách thiết kế này chỉ giúp ích khi **mọi câu lệnh đọc, ghi, đếm và dọn dữ liệu đều tôn trọng case_id**:

~~~sql
-- Reader chỉ thấy input của test hiện tại.
SELECT id, customer_name, case_id
FROM source_customer
WHERE case_id = ?
ORDER BY id;

-- Assertion chỉ thấy output của test hiện tại.
SELECT id
FROM imported_customer
WHERE case_id = ?
ORDER BY id;

-- Dọn dữ liệu của đúng test, nếu cần.
DELETE FROM imported_customer WHERE case_id = ?;
DELETE FROM source_customer WHERE case_id = ?;
~~~

Nếu không thể thay đổi schema nghiệp vụ, có thể tách bằng **schema/database riêng**, **tenant id**, **mã run**, file riêng hoặc một namespace dữ liệu khác phù hợp với ứng dụng. Điểm cốt lõi là mỗi test có thể xác định chính xác những bản ghi mình sở hữu và những bản ghi mình được phép xóa.

### Những thao tác setup và cleanup cần tránh

Các câu lệnh sau rất nguy hiểm khi nhiều test đang dùng chung database:

~~~sql
TRUNCATE TABLE source_customer;
DELETE FROM imported_customer;
DELETE FROM BATCH_JOB_EXECUTION;
DELETE FROM BATCH_STEP_EXECUTION;
~~~

Một test có thể chạy lệnh xóa đúng lúc test khác vừa tạo metadata hoặc ghi xong một chunk. Việc sử dụng **@BeforeEach**, **@AfterEach** hay **@Sql** không tự động khiến thao tác đó an toàn khi chạy song song: các hook của hai test có thể đan xen nhau.

Nếu thực sự cần reset toàn bộ database, hãy chạy thao tác đó trước khi bắt đầu nhóm test song song, hoặc cung cấp một database/schema độc lập cho mỗi test. Với test dùng dữ liệu phân vùng, ưu tiên xóa theo caseId của chính test đó.

## 5. Quy tắc thứ ba: giữ trạng thái xử lý trong phạm vi Step

Spring mặc định tạo bean scope **singleton**. Một processor giữ trạng thái mutable sẽ được nhiều JobExecution dùng chung nếu bạn không chủ động tách biệt nó.

Ví dụ không phù hợp với các test chạy đồng thời:

~~~java
@Component
public class CountingProcessor implements ItemProcessor<Customer, Customer> {

    private int processedCount = 0;

    @Override
    public Customer process(Customer item) {
        processedCount++;
        return item;
    }

    public int getProcessedCount() {
        return processedCount;
    }
}
~~~

**processedCount** là trạng thái của singleton. Count có thể chứa item của nhiều test, bản thân phép tăng còn không an toàn khi có nhiều thread.

Các lựa chọn an toàn hơn gồm:

- Giữ processor **stateless**: kết quả chỉ phụ thuộc input và các service an toàn khi đồng thời.
- Đặt state thực sự thuộc một lần Step chạy trong bean **@StepScope** hoặc đối tượng được tạo riêng cho lần thực thi.
- Với dữ liệu cần khôi phục khi restart, dùng **ExecutionContext** và cơ chế **ItemStream** phù hợp thay vì một static field.
- Nếu buộc phải chia sẻ bộ nhớ mutable, thiết kế và kiểm thử chính sách đồng bộ rõ ràng; đồng bộ hóa chỉ xử lý race trên state, không thay thế phân vùng dữ liệu nghiệp vụ.

### Reader nên là step-scoped

Một reader có cursor/vị trí đọc cần được tạo cho từng StepExecution. Ví dụ với **JdbcCursorItemReader**:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{jobParameters['caseId']}") String caseId) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerReader")
            .dataSource(dataSource)
            .sql("""
                SELECT id, customer_name, case_id
                FROM source_customer
                WHERE case_id = ?
                ORDER BY id
                """)
            .preparedStatementSetter(ps -> ps.setString(1, caseId))
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("customer_name"),
                    rs.getString("case_id")))
            .saveState(true)
            .build();
}
~~~

Trong ví dụ, **Customer** là record:

~~~java
public record Customer(long id, String customerName, String caseId) {}
~~~

**@StepScope** tạo reader riêng theo lần thực thi Step và cho phép bind JobParameters. **saveState(true)** ghi nhận trạng thái reader khi có checkpoint. Một reader singleton mang cursor đã dùng từ test A sang test B có thể khiến test B đọc thiếu item dù caseId khác nhau.

Với các bean writer có state như file writer, output path cũng cần được phân vùng, ví dụ **outputDir/caseId/results.csv**. Tránh cho hai StepExecution ghi cùng một file mà không có một thiết kế phối hợp rõ ràng.

## 6. Mẫu cấu hình Job dùng được trong bài test song song

Ví dụ tiếp theo sử dụng **Java 17, Spring Batch 5.x, Spring Boot 3.x, Spring JDBC, JUnit 5 và AssertJ**. Giả định ứng dụng đã cấu hình **JobRepository**, **PlatformTransactionManager** và **DataSource**. Hai bảng fixture ở phần 4 được tạo qua migration hoặc SQL khởi tạo của test.

Reader ở phần 5 lọc input theo identifying **caseId**. Writer sau đây ghi cùng caseId vào đích:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_customer (case_id, id, customer_name)
                VALUES (:caseId, :id, :customerName)
                """)
            .itemSqlParameterSourceProvider(customer ->
                    new MapSqlParameterSource()
                            .addValue("caseId", customer.caseId())
                            .addValue("id", customer.id())
                            .addValue("customerName", customer.customerName()))
            .build();
}
~~~

Step xử lý theo chunk có thể được khai báo như sau:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<Customer> customerReader,
        JdbcBatchItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(2, transactionManager)
            .reader(customerReader)
            .writer(customerWriter)
            .build();
}

@Bean
Job importCustomersJob(
        JobRepository jobRepository,
        Step importCustomersStep) {

    return new JobBuilder("importCustomersJob", jobRepository)
            .start(importCustomersStep)
            .build();
}
~~~

Trong cấu hình này, các test có thể chia sẻ định nghĩa **Job** và **Step**, còn mỗi lần launch có **StepExecution**, reader theo step scope và tham số **caseId** riêng. Writer JDBC không giữ buffer mutable trên từng test trong ví dụ này; mỗi lời gọi writer sử dụng dữ liệu từ chunk hiện tại.

Nếu ứng dụng có processor hoặc listener, phải kiểm tra khả năng chia sẻ trạng thái của chính các bean đó. **@StepScope** không tự làm cho một service singleton khác trở nên an toàn nếu service tiếp tục lưu dữ liệu test vào field dùng chung.

## 7. Bật JUnit 5 parallel execution có kiểm soát

JUnit Jupiter không tự chạy mọi test song song chỉ vì máy có nhiều CPU. Có thể bật trong file **src/test/resources/junit-platform.properties**:

~~~properties
junit.jupiter.execution.parallel.enabled=true

# Mặc định chạy tuần tự; chỉ test/class được đánh dấu mới chạy song song.
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=same_thread

junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

Sau đó đánh dấu các test đã được thiết kế an toàn:

~~~java
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

@Execution(ExecutionMode.CONCURRENT)
class ParallelCustomerImportTest {
    // Các @Test trong class có thể được JUnit chạy đồng thời.
}
~~~

Cấu hình trên cần có đủ worker thread của JUnit để test thực sự có cơ hội chạy cùng lúc. **@Execution(CONCURRENT)** cho phép chạy song song, không bảo đảm mọi lần chạy đều chồng thời gian. Khi mục tiêu là chứng minh một bug chỉ xảy ra lúc hai transaction giao nhau, cần một bài test điều phối điểm giao nhau bằng **CountDownLatch**, **CyclicBarrier** hoặc cơ chế đồng bộ có timeout; không nên dựa vào **Thread.sleep** ngẫu nhiên.

Nếu muốn bật song song cho cả suite, có thể thay **mode.default=concurrent** và **mode.classes.default=concurrent**, nhưng trước đó cần bảo đảm tất cả test liên quan đều không chia sẻ state không an toàn. Việc chỉ bật đồng thời cho các class đã chuẩn bị giúp kiểm soát phạm vi thay đổi.

## 8. Integration test chạy song song trên cùng database

Trong trường hợp test dùng chung Spring ApplicationContext, có thể inject trực tiếp **JobLauncher** và **Job** rồi launch với JobParameters riêng. Cách này không yêu cầu thay đổi trạng thái bên trong tiện ích test dùng chung.

Ví dụ giả định các bean ở phần 6 nằm trong application context, JobLauncher sử dụng cơ chế **đồng bộ**, và schema nghiệp vụ đã được tạo sẵn:

~~~java
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
})
@Execution(ExecutionMode.CONCURRENT)
class ParallelCustomerImportTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("importCustomersJob")
    private Job importCustomersJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void importsThreeRows() throws Exception {
        runIsolatedScenario(List.of(101L, 102L, 103L));
    }

    @Test
    void importsFourRowsWithOverlappingBusinessIds() throws Exception {
        // ID trùng với test trên là có chủ đích.
        // Khóa ghép case_id, id giúp dữ liệu của hai test không xung đột.
        runIsolatedScenario(List.of(101L, 102L, 103L, 104L));
    }

    private void runIsolatedScenario(List<Long> expectedIds) throws Exception {
        String caseId = UUID.randomUUID().toString();

        try {
            // Fixture thuộc đúng test này.
            for (Long id : expectedIds) {
                jdbcTemplate.update(
                        """
                        INSERT INTO source_customer (case_id, id, customer_name)
                        VALUES (?, ?, ?)
                        """,
                        caseId, id, "customer-" + id);
            }

            JobParameters parameters = new JobParametersBuilder()
                    .addString("caseId", caseId, true)
                    .toJobParameters();

            JobExecution execution = jobLauncher.run(
                    importCustomersJob, parameters);

            assertThat(execution.getStatus())
                    .isEqualTo(BatchStatus.COMPLETED);

            StepExecution step = execution.getStepExecutions().stream()
                    .filter(s -> "importCustomersStep".equals(s.getStepName()))
                    .findFirst()
                    .orElseThrow();

            assertThat(step.getReadCount()).isEqualTo(expectedIds.size());
            assertThat(step.getWriteCount()).isEqualTo(expectedIds.size());
            assertThat(step.getSkipCount()).isZero();

            // Chỉ đọc output mang caseId do chính test tạo ra.
            List<Long> actualIds = jdbcTemplate.queryForList(
                    """
                    SELECT id FROM imported_customer
                    WHERE case_id = ?
                    ORDER BY id
                    """,
                    Long.class,
                    caseId);

            assertThat(actualIds).containsExactlyElementsOf(expectedIds);

        } finally {
            // Cleanup giới hạn theo caseId của chính test.
            jdbcTemplate.update(
                    "DELETE FROM imported_customer WHERE case_id = ?", caseId);
            jdbcTemplate.update(
                    "DELETE FROM source_customer WHERE case_id = ?", caseId);
        }
    }
}
~~~

### Những điểm quan trọng trong test

1. **caseId được sinh bên trong từng phương thức chạy kịch bản.** Hai test có thể dùng cùng ID nghiệp vụ nhưng luôn có JobInstance và vùng dữ liệu khác nhau.
2. **JobLauncher và Job không bị chỉnh sửa giữa các test.** Mỗi lần launch chỉ truyền JobParameters của test đó.
3. **Reader sử dụng caseId trong câu SQL.** Chỉ truyền caseId vào JobParameters mà không lọc ở reader sẽ vẫn khiến test đọc nhầm dữ liệu.
4. **Assertion truy vấn dữ liệu theo caseId.** Không dùng câu lệnh **SELECT COUNT(*) FROM imported_customer** để so với số bản ghi của một test trong database dùng chung.
5. **Cleanup chạy theo caseId.** Test A không xóa fixture của test B; bảng metadata Batch không bị xóa khi các test đang chạy.
6. **JobLauncher phải đồng bộ theo giả định của ví dụ.** Nếu Job được launch bất đồng bộ bằng TaskExecutor, lời gọi **run(...)** có thể trả về khi Job còn đang chạy. Khi đó, test phải đợi trạng thái kết thúc qua **JobExplorer** hoặc cơ chế completion có timeout trước khi assert và cleanup.
7. **Nguồn dữ liệu và đích cần được tạo trước khi các test đồng thời chạy.** Việc tạo/xóa schema không nên thực hiện riêng ở **@BeforeEach** của từng test dùng chung database.

Đoạn ví dụ sử dụng **spring.batch.jdbc.initialize-schema=always** để thiết lập metadata Batch trong môi trường test phù hợp. Thuộc tính này không tự tạo bảng nghiệp vụ **source_customer** hoặc **imported_customer**. Với database được chia sẻ bởi nhiều Spring context, tránh để nhiều context cùng thao tác khởi tạo lại schema metadata lúc các Job khác đang chạy; hãy quản lý migration/schema init tập trung theo vòng đời hạ tầng test.

## 9. Cẩn thận với tiện ích trong spring-batch-test

**spring-batch-test** cung cấp **@SpringBatchTest**, **JobLauncherTestUtils**, **JobRepositoryTestUtils** và các listener hỗ trợ Step scope. Chúng có ích, nhưng cách sử dụng quyết định test có an toàn khi chạy song song hay không.

### 9.1. JobLauncherTestUtils có state cấu hình

Một số test thường làm như sau:

~~~java
@Autowired
private JobLauncherTestUtils testUtils;

@BeforeEach
void setUp() {
    testUtils.setJob(importCustomersJob);
}

@Test
void launch() throws Exception {
    testUtils.launchJob(parameters);
}
~~~

**JobLauncherTestUtils** có thể giữ reference tới Job được cấu hình. Nếu hai test chung context cùng gọi **setJob(...)** với hai Job khác nhau, test A có thể launch Job do test B vừa đặt vào.

Đối với các integration test cần chạy đồng thời, inject trực tiếp **JobLauncher** và gọi **jobLauncher.run(targetJob, parameters)** như ví dụ phần 8 sẽ làm ranh giới dữ liệu rõ hơn. Nếu vẫn dùng **JobLauncherTestUtils**, hãy đảm bảo Job reference không bị các test khác thay đổi và mỗi test truyền JobParameters riêng.

### 9.2. Không dùng cleanup metadata toàn cục trong test đồng thời

**JobRepositoryTestUtils.removeJobExecutions()** có thể xóa metadata của nhiều lần chạy. Nếu gọi tại **@BeforeEach** hoặc **@AfterEach** trong các test dùng chung JobRepository, nó có thể xóa trạng thái mà một test khác đang sử dụng.

Nên dùng JobParameters riêng để phân biệt các lần chạy; thực hiện dọn metadata ở giai đoạn suite đã hoàn tất hoặc trong kho dữ liệu tách biệt. Nếu cần test restart, phải giữ nguyên metadata của lần chạy thất bại cho đến khi restart và assertions kết thúc.

### 9.3. Scope theo thread và StepExecution

**@StepScope** và **@JobScope** liên kết các bean với context của lần thực thi tương ứng. Khi Spring Batch chạy Step, framework thiết lập context thích hợp cho lifecycle của Step; điều này giúp state reader không bị dùng nhầm giữa các JobExecution.

Nếu unit test gọi trực tiếp một bean step-scoped mà không launch Step, có thể cần **StepScopeTestUtils** hoặc listener trong **spring-batch-test** để tạo StepExecution context giả lập. Việc tự mở thread rồi gọi một bean step-scoped ngoài lifecycle Batch không tự mang theo StepContext; phải thiết kế ranh giới context rõ ràng.

## 10. Transaction của test và transaction của Job

Một lỗi phổ biến là đánh dấu cả integration test bằng **@Transactional** với mong đợi fixture tự rollback sau test:

~~~java
@Transactional
@Test
void importsCustomers() {
    // Ghi dữ liệu fixture.
    // Launch một Job có transaction của Step.
}
~~~

Cơ chế rollback của transaction do test framework quản lý không đồng nghĩa mọi transaction bên trong Job đều rollback cùng nó. Khi Step chạy trong transaction riêng, hoặc chạy ở thread khác, Job có thể không thấy dữ liệu fixture chưa commit; ngược lại, các thay đổi đã commit bởi Job có thể vẫn tồn tại sau khi test rollback.

Đối với kiểm thử integration cần quan sát commit, retry, skip hoặc restart, cách rõ ràng là:

- Seed dữ liệu trước khi launch và đảm bảo các bản ghi input đã commit/hiển thị theo isolation của database.
- Cho Job sử dụng transaction manager giống cấu hình được kiểm thử.
- Đợi Job kết thúc trước khi kiểm tra output.
- Dọn đúng dữ liệu của test sau khi Job đã kết thúc.

Nếu lựa chọn transaction bao quanh toàn bộ test, cần hiểu rõ propagation, thread boundary, transaction manager và khả năng quan sát dữ liệu. Đừng mặc định **@Transactional** sẽ cô lập hoàn toàn test batch.

## 11. Pool connection, database lock và độ ổn định tài nguyên

Dù dữ liệu đã chia vùng, các test vẫn chia sẻ tài nguyên vật lý. Giả sử JUnit cho chạy bốn test đồng thời, mỗi Job cần kết nối cho JobRepository, reader và writer. Nếu pool có rất ít connection, một Job có thể giữ kết nối trong khi chờ connection khác; toàn bộ nhóm test dễ timeout.

Ví dụ cấu hình pool trong môi trường test:

~~~properties
spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.connection-timeout=30000
~~~

Các con số trên chỉ là **ví dụ**. Kích thước phù hợp phụ thuộc số test đồng thời, loại reader, transaction và số connection mà mỗi Job thực sự dùng. Tăng pool vô hạn cũng không giải quyết được giới hạn database; đo đạc connection usage, lock waits và thời gian chờ rồi điều chỉnh cùng mức parallelism của JUnit.

Một số lưu ý bổ sung:

- **JdbcCursorItemReader** có thể giữ một kết nối cho cursor trong suốt Step; cần tính đến khả năng giữ connection khi nhiều Job chạy.
- **JobRepository** sử dụng transaction để tạo JobExecution và cập nhật metadata. Tránh test dùng cùng JobInstance ngoài chủ đích.
- **DDL hoặc TRUNCATE toàn cục** có thể lấy lock mạnh, ảnh hưởng Job khác kể cả các Job đang xử lý caseId khác nhau.
- Khi dùng Testcontainers, có thể dùng chung một container database được khởi tạo theo class/suite rồi phân vùng dữ liệu; nếu test phải sửa schema hoặc cấu hình database theo cách không tương thích, hãy cấp schema hoặc container riêng.
- H2 in-memory có thể hữu ích cho test nhanh, nhưng hành vi lock, isolation, SQL và transaction khác PostgreSQL/MySQL. Với các race liên quan giao dịch, nên chạy những bài test quan trọng trên database engine giống môi trường thật.

### Không đóng tài nguyên đang được dùng chung

Nếu nhiều test sử dụng một static Testcontainers instance hoặc một Spring context cached chung, test A không được chủ động stop container, close DataSource hay làm mất schema khi test B còn chạy. Tài nguyên chung cần có **vòng đời riêng của class/suite**, và teardown phải xảy ra sau các test sử dụng nó.

## 12. Mock, static state và Spring context cache

**@SpringBootTest** thường dùng Spring TestContext cache, nên nhiều test class có thể sử dụng cùng một ApplicationContext. Đây là cơ chế tiết kiệm thời gian, nhưng cũng có nghĩa singleton và mock có thể tồn tại xuyên qua nhiều test.

Các nguồn gây xung đột thường gặp gồm:

- Một test thay đổi field cấu hình trên singleton rồi test khác đọc ngay field ấy.
- Hai test thay đổi hành vi của cùng một mock được đăng ký trong Spring context; test B reset mock khi test A còn đang gọi nó.
- Một **static AtomicBoolean** giả lập failure được chia sẻ giữa các bài test restart, khiến test này “tiêu thụ” failure của test khác.
- Một test đánh dấu **@DirtiesContext** để đóng và dựng lại context trong lúc test khác vẫn đang dùng cùng context.
- Một global cache, file path, system property hoặc biến môi trường bị sửa trong phạm vi một test.

Ưu tiên fixture và bean **không có mutable state xuyên test**. Nếu cần fault injection riêng cho từng JobExecution, lưu kịch bản theo **caseId**, tạo bean theo scope phù hợp hoặc đặt bộ điều khiển lỗi vào một dependency được tách theo test. Một cờ static dùng chung cho cả suite không phải cơ chế đáng tin cậy cho các test fail/restart song song.

Nếu có test di sản bắt buộc dùng state toàn cục, tạm thời bắt test đó chạy tuần tự, hoặc dùng **@ResourceLock** của JUnit để khóa những test cùng sử dụng tài nguyên được đặt tên:

~~~java
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock("shared-batch-fixture")
class LegacyBatchTest {
    // Test dùng fixture không thể tách riêng.
}
~~~

**@ResourceLock** chỉ có tác dụng nếu các test cùng tranh tài nguyên đều tuân thủ cùng quy ước lock. Nó là cách quản lý trường hợp khó cô lập; về lâu dài, dữ liệu và trạng thái độc lập vẫn giúp mở rộng parallelism tốt hơn.

## 13. Test một JobInstance được launch đồng thời có chủ đích

Có những test cần kiểm tra **chính sách ngăn hai lần chạy đồng thời của cùng JobInstance**. Khi đó, việc sử dụng chung identifying parameters là **chủ đích của kịch bản**, khác với hai test độc lập.

Giả sử một JobExecution còn ở trạng thái đang chạy, yêu cầu launch thứ hai cùng JobInstance có thể bị từ chối, chẳng hạn bằng **JobExecutionAlreadyRunningException**. Để kiểm thử đúng:

1. Tạo identifying parameters riêng cho kịch bản test, nhưng dùng **cùng bộ tham số** cho hai yêu cầu launch bên trong kịch bản.
2. Thiết lập barrier để giữ JobExecution thứ nhất ở một điểm chắc chắn đang chạy.
3. Launch yêu cầu thứ hai khi xác nhận trạng thái lần đầu là đang chạy.
4. Assert exception/trạng thái theo contract và phiên bản Spring Batch đang dùng.
5. Giải phóng barrier và đợi Job thứ nhất kết thúc; luôn có timeout để test không treo vô hạn.

Nếu cả hai Job khởi chạy và kết thúc quá nhanh, assertion dựa vào thời gian có thể không kiểm tra đúng tình huống race. Có thể dùng **CountDownLatch** để điều phối và **try/finally** để bảo đảm latch được giải phóng, kể cả khi assertion thất bại.

Loại test này nên tách khỏi những bài test chỉ muốn import dữ liệu bình thường song song, để sự trùng JobParameters không bị nhầm thành lỗi cô lập test.

## 14. Một chiến lược triển khai theo từng mức

### Mức 1: Test unit song song

Với processor, validator, mapper và các utility **stateless**, có thể chạy JUnit song song mà không cần khởi tạo toàn bộ Batch infrastructure. Tránh sử dụng database hoặc static mutable fixture trong unit test khi không cần.

### Mức 2: Integration test cùng database, dữ liệu phân vùng

Đây thường là lựa chọn cân bằng tốt: các test chia sẻ Spring context, JobRepository và database, nhưng mỗi test dùng **caseId identifying**, input/output có khóa riêng và cleanup theo caseId. Cần kiểm soát connection pool và tránh global reset.

### Mức 3: Integration test cách ly schema/database

Những test phải thay đổi schema, kiểm thử migration, chạy cleanup tổng thể hoặc thao tác database lock khó chia sẻ có thể dùng schema/database riêng. Chi phí setup cao hơn nhưng ranh giới tài nguyên rõ hơn.

### Mức 4: Kiểm thử đối kháng cạnh tranh tài nguyên

Dành cho các kịch bản như launch cùng JobInstance, deadlock, lock timeout, nhiều worker cập nhật chung record hoặc event được nhận hai lần. Những test này phải điều phối concurrency bằng cơ chế xác định và kiểm tra đúng điều kiện cạnh tranh cần mô phỏng.

Không cần nâng mọi bài test lên mức cách ly mạnh nhất. Chọn cơ chế tương ứng với loại state mà test thực sự tác động.

## 15. Dấu hiệu một test song song chưa an toàn

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| **JobInstanceAlreadyCompleteException** xảy ra ngẫu nhiên | Các test dùng cùng identifying parameters; một JobInstance đã hoàn tất | Sinh caseId identifying riêng cho từng test. |
| **JobExecutionAlreadyRunningException** | Hai lần launch cùng JobInstance diễn ra đồng thời | Tách JobInstance nếu hai test độc lập; nếu test cạnh tranh thì điều phối có chủ đích. |
| **readCount/writeCount** thay đổi theo lần chạy | Input bị thay đổi bởi test khác; reader singleton; fixture không phân vùng | Lọc theo caseId, dùng reader step-scoped, giữ input ổn định. |
| Vi phạm primary key | Hai test ghi cùng business ID vào bảng dùng chung | Khóa ghép theo caseId hoặc tách schema. |
| Test pass đơn lẻ nhưng fail trong suite | Xóa bảng toàn cục, dùng chung mock/static state, context bị đóng | Giới hạn cleanup, tránh mutable state chung, cô lập test di sản. |
| Timeout khi số test tăng | Pool connection quá nhỏ, transaction chờ lock, database quá tải | Đo connection/lock, điều chỉnh parallelism và pool. |
| Test restart không phục hồi đúng | Metadata bị xóa, JobParameters đổi, reader không lưu trạng thái | Giữ identifying parameters, giữ JobRepository, kiểm tra ItemStream/checkpoint. |
| Kết quả assertion bị lẫn | Test truy vấn toàn bộ bảng thay vì vùng dữ liệu riêng | Query/assert theo caseId của chính test. |
| Thứ tự pass/fail phụ thuộc lịch chạy | Dữ liệu hoặc bean có trạng thái dùng chung không được bảo vệ | Xác định tài nguyên chia sẻ, phân vùng hoặc dùng khóa test phù hợp. |

## 16. Checklist trước khi bật parallel test

- [ ] Mỗi bài test độc lập có **identifying JobParameters** riêng.
- [ ] Test restart dùng **cùng parameters giữa các lần chạy trong test**, nhưng khác với test restart khác.
- [ ] Reader, processor và writer không chia sẻ mutable state giữa các StepExecution ngoài chủ đích.
- [ ] Input, output và assertion được phân vùng bằng caseId, schema, database hoặc file path riêng.
- [ ] Cleanup chỉ tác động dữ liệu mà test tạo; không xóa metadata Batch giữa lúc các Job khác chạy.
- [ ] Không thay đổi Job được lưu trong utility/singleton mà nhiều test cùng sử dụng.
- [ ] Fixture đã commit trước khi Job đọc; assertions thực hiện sau khi Job kết thúc.
- [ ] Spring context, mocks và container dùng chung không bị reset/đóng từ một test đồng thời.
- [ ] Connection pool và parallelism phù hợp sức chứa của database.
- [ ] Những test cố ý tạo race dùng barrier và timeout để kiểm tra đúng điều kiện cần thiết.

Khi thiết kế đúng, **test chạy song song** vẫn có thể chia sẻ phần lớn hạ tầng Spring Batch. Mỗi test sở hữu rõ JobInstance, dữ liệu và phạm vi cleanup của mình; đồng thời các thành phần được chia sẻ phải không có state thay đổi theo test hoặc có cơ chế phối hợp rõ ràng. Nhờ đó, lỗi test sẽ phản ánh hành vi batch cần kiểm chứng thay vì phụ thuộc test nào tình cờ chạy trước.

