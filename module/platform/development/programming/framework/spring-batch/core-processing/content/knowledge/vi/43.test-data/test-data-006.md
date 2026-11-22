# Dữ liệu để kiểm tra restart trong Spring Batch

## 1. Restart cần được kiểm tra bằng dữ liệu như thế nào?

Trong Spring Batch, **restart** là tiếp tục một `JobInstance` đã bị gián đoạn, thường do một lần chạy có trạng thái `FAILED` hoặc `STOPPED`. Một lần restart tạo ra `JobExecution` mới cho **cùng `JobInstance`**, và các Step cần chạy lại có thể khôi phục trạng thái từ `ExecutionContext` đã được lưu tại checkpoint trước đó.

Kiểm thử restart không chỉ hỏi: “Chạy lại có `COMPLETED` không?”. Câu hỏi quan trọng hơn là:

- Dữ liệu đã **commit trước khi lỗi** có được giữ nguyên không?
- Dữ liệu thuộc **chunk lỗi chưa commit** có được xử lý lại không?
- Dữ liệu **chưa đến lượt xử lý** có được xử lý sau restart không?
- Kết quả cuối cùng có **đủ bản ghi, đúng giá trị, không bị mất hoặc ghi trùng** không?
- Spring Batch có thực sự tạo lần thực thi mới cho cùng `JobInstance` và khôi phục checkpoint không?

Để trả lời được, bộ dữ liệu test phải có **thứ tự xác định, mã định danh dễ đối chiếu, ranh giới chunk rõ ràng và vị trí phát sinh lỗi được kiểm soát**. Bài này xây dựng một ví dụ đầy đủ theo hướng đó trong ngữ cảnh Spring Batch Core Processing.

## 2. Phân biệt restart với chạy một Job mới

Spring Batch nhận diện `JobInstance` bằng **tên Job và các JobParameters mang tính identifying**. Ví dụ:

```text
Job: importCustomersJob
Identifying parameters:
  businessDate = 2026-11-15
  inputFile    = /tmp/customers.csv
```

Giả sử lần chạy đầu tiên thất bại:

```text
JobInstance J1
  ├─ JobExecution E1: FAILED
  └─ JobExecution E2: COMPLETED   <-- restart thành công
```

Nếu thay `businessDate` hoặc thêm một tham số identifying mới có giá trị khác trước khi chạy lần thứ hai, Spring Batch sẽ nhận diện **JobInstance mới**, thay vì restart J1:

```text
JobInstance J1 (businessDate=2026-11-15)
  └─ JobExecution E1: FAILED

JobInstance J2 (businessDate=2026-11-16)
  └─ JobExecution E2: COMPLETED   <-- Job mới, không phải restart của J1
```

Vì vậy, khi kiểm tra restart, **giữ nguyên identifying JobParameters giữa hai lần launch**. Nếu test cần một tham số ngẫu nhiên để tránh đụng dữ liệu chạy trước, hãy tạo nó **một lần khi bắt đầu test** rồi tái sử dụng đúng đối tượng `JobParameters` cho cả hai lần chạy.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", inputFile.toAbsolutePath().toString(), true)
        .addString("testCaseId", UUID.randomUUID().toString(), true)
        .toJobParameters();

JobExecution firstRun = jobLauncherTestUtils.launchJob(parameters);
JobExecution restartRun = jobLauncherTestUtils.launchJob(parameters);
```

Hai lệnh `launchJob` trên chỉ thực sự minh họa restart khi **lần đầu đã kết thúc bằng trạng thái có thể restart**, cấu hình Job cho phép restart, và `JobRepository` còn giữ metadata của lần chạy đầu. Nếu lần đầu đã `COMPLETED`, khởi chạy lại với cùng identifying parameters thông thường bị từ chối bằng `JobInstanceAlreadyCompleteException`.

Đừng dùng `RunIdIncrementer`, timestamp hiện tại hoặc `UUID.randomUUID()` **mới cho lần launch thứ hai** trong test restart: thay đổi identifying parameters có thể âm thầm biến bài test thành kiểm thử một Job mới.

## 3. Thiết kế fixture: 7 bản ghi, chunk size = 3, lỗi ở bản ghi thứ 5

Giả sử Step đọc file CSV, chuyển đổi dữ liệu qua `ItemProcessor`, rồi ghi vào bảng `imported_customer`. Ta chọn dữ liệu nguồn như sau:

**File `customers.csv`:**

```csv
id,name
101,An
102,Binh
103,Chi
104,Dung
105,Ha
106,Minh
107,Thao
```

**Bảng đích** có khóa chính trên `id`:

```sql
CREATE TABLE imported_customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

Step được cấu hình với `chunk(3)`, và processor cố tình ném exception **đúng một lần** khi gặp `id = 105`. Exception này không nằm trong chính sách skip/retry của kịch bản, nên lần đầu Step sẽ `FAILED`.

| Thời điểm | Dữ liệu liên quan | Kết quả giao dịch kỳ vọng |
| --- | --- | --- |
| Chunk 1 | 101, 102, 103 | Writer ghi 3 item, transaction **commit**. |
| Chunk 2 | 104, 105, 106 | Processor lỗi tại 105; chunk hiện tại **không commit**. |
| Sau lần chạy 1 | 101, 102, 103 | Chỉ ba bản ghi đầu tiên tồn tại trong bảng đích. |
| Sau restart | 104, 105, 106, 107 | Reader tiếp tục từ checkpoint; ghi nốt bốn bản ghi. |
| Kết quả cuối | 101 đến 107 | Có đủ bảy bản ghi, mỗi `id` xuất hiện đúng một lần. |

Vì processor dừng ngay khi xử lý 105, writer của chunk 2 chưa được gọi trong kịch bản này. Các item 104 và 105 đã được reader/processor tiếp cận nhưng vẫn thuộc chunk **chưa commit**; chúng phải được xử lý lại khi restart. Item 106 và 107 sẽ được đọc trong lần chạy tiếp theo.

```text
LẦN 1

101 -> 102 -> 103 -> [COMMIT / CHECKPOINT]
104 -> 105 -> [LỖI] -> [ROLLBACK CHUNK 2] -> FAILED

BẢNG ĐÍCH SAU LẦN 1
101, 102, 103

LẦN 2: RESTART CÙNG JOBINSTANCE

[khôi phục checkpoint sau 103]
104 -> 105 -> 106 -> [COMMIT]
107 -> [COMMIT] -> COMPLETED

BẢNG ĐÍCH CUỐI CÙNG
101, 102, 103, 104, 105, 106, 107
```

**Tại sao chọn lỗi ở bản ghi thứ 5?** Nếu lỗi xảy ra ngay ở bản ghi đầu tiên, ta không kiểm tra được khả năng giữ lại một chunk đã commit. Nếu chỉ gây lỗi sau khi tất cả dữ liệu đã ghi, ta cũng không kiểm tra được việc xử lý phần chưa hoàn tất. Vị trí 105 buộc test kiểm tra đồng thời **dữ liệu đã commit**, **dữ liệu cần chạy lại** và **dữ liệu chưa đọc**.

## 4. Điều kiện để fixture thật sự kiểm tra được restart

### 4.1. Input cố định giữa các lần chạy

File `customers.csv` phải giữ nguyên nội dung và thứ tự giữa lần thất bại và lần restart. Nếu xóa, thêm hoặc đổi thứ tự dòng sau khi checkpoint đã lưu, reader khôi phục theo vị trí cũ có thể bỏ sót hoặc đọc lại nhầm bản ghi. Với production batch, có thể dùng file bất biến, phiên bản dữ liệu cố định hoặc cơ chế staging để bảo vệ dữ liệu nguồn.

Với reader lấy dữ liệu từ database, cần có thứ tự đọc ổn định (ví dụ `ORDER BY id`/sort key duy nhất khi dùng paging) và kiểm soát thay đổi của tập dữ liệu trong thời gian restart. Đừng dùng truy vấn có thứ tự không xác định rồi kỳ vọng checkpoint luôn trỏ tới cùng bản ghi.

### 4.2. Reader phải lưu trạng thái

Các reader có khả năng restart như `FlatFileItemReader` thường sử dụng `ExecutionContext` để lưu vị trí đọc. Trong ví dụ này, cần:

- Đặt `name` ổn định cho reader (key lưu trạng thái dựa trên tên).
- Bật `saveState(true)`; các reader hỗ trợ thường bật mặc định, nhưng khai báo tường minh giúp thể hiện mục tiêu test.
- Không tự xóa dữ liệu `BATCH_*` trong `JobRepository` giữa hai lần chạy.
- Đảm bảo reader được mở lại trong một `StepExecution` mới khi restart.

Nếu dùng một reader tự viết, reader đó phải thực hiện đúng contract `ItemStream` (`open`, `update`, `close`) để lưu và nạp vị trí checkpoint. Chỉ `ItemReader#read()` không đảm bảo reader sẽ tự nhớ vị trí khi restart.

### 4.3. Writer và transaction nhất quán

Ví dụ dùng JDBC writer và bảng đích trong transaction phù hợp với Step. Nếu chunk 2 lỗi trước khi commit, dữ liệu chunk 2 không xuất hiện trong bảng đích; nếu chunk 1 đã commit thì ba bản ghi đầu còn nguyên.

Nếu writer gọi HTTP API, gửi message, ghi file ngoài transaction hoặc làm side effect không rollback được, tính chất trên **không còn tự động được bảo đảm**. Lúc đó fixture cần kiểm tra khả năng idempotent, khóa deduplication, trạng thái outbox hoặc cơ chế khôi phục riêng của hệ thống đích.

### 4.4. Lỗi phải có thể lặp lại theo kịch bản

Không nên dựa vào ngắt mạng thật, timeout ngẫu nhiên hay kill process ngoài kiểm soát để viết bài test restart cơ bản. Một fault được tiêm có chủ đích, ví dụ ném `IllegalStateException` đúng lần đầu gặp `id = 105`, làm kết quả dự đoán được. Ở lần restart phải vô hiệu hóa fault này để Step có cơ hội hoàn tất.

## 5. Cấu hình Spring Batch minh họa

Ví dụ dưới đây dùng **Java 17, Spring Boot 3.x, Spring Batch 5.x, JDBC và JUnit 5**. Những đoạn code là fixture minh họa để tích hợp vào ứng dụng đã có `JobRepository`, `DataSource`, transaction manager và cấu hình Batch. Có thể đặt các bean test trong một lớp `@TestConfiguration` và `@Import` vào bài test; bảng `imported_customer` cần được khởi tạo trước khi test chạy.

### 5.1. Model của dòng CSV

```java
public record Customer(long id, String name) {
}
```

### 5.2. Reader có checkpoint

```java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Customer>()
            .name("customerCsvReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)        // Bỏ qua dòng tiêu đề: id,name
            .saveState(true)       // Lưu vị trí đọc vào ExecutionContext
            .delimited()
            .names("id", "name")
            .fieldSetMapper(fields -> new Customer(
                    fields.readLong("id"),
                    fields.readString("name")))
            .build();
}
```

`@StepScope` bảo đảm bean reader được tạo theo lần thực thi Step và có thể nhận JobParameters. Một input file thực sự cần ổn định giữa các lần launch; ví dụ này đọc đường dẫn file từ identifying parameter `inputFile`.

### 5.3. Processor ném lỗi một lần

Trong fixture kiểm thử, một `AtomicBoolean` sống xuyên suốt **hai lần launch trong cùng application context** được dùng để kiểm soát fault. Đây là cơ chế thử nghiệm, không phải quy tắc triển khai processor nghiệp vụ:

```java
@Bean
AtomicBoolean failOnceAt105() {
    return new AtomicBoolean(true);
}

@Bean
ItemProcessor<Customer, Customer> customerProcessor(
        AtomicBoolean failOnceAt105) {

    return item -> {
        if (item.id() == 105L && failOnceAt105.compareAndSet(true, false)) {
            throw new IllegalStateException("Simulated failure at id=105");
        }
        return item;
    };
}
```

Khi processor gặp 105 lần đầu, flag đổi từ `true` sang `false` và ném exception. Khi Step restart và đọc lại 105, processor trả về item bình thường. Nếu thử nghiệm được thực thi nhiều lần trong cùng context, cần đặt lại flag trước mỗi kịch bản để không vô tình bỏ qua lỗi đã dự kiến.

### 5.4. JDBC writer và Step

```java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("INSERT INTO imported_customer (id, name) VALUES (:id, :name)")
            .itemSqlParameterSourceProvider(customer ->
                    new MapSqlParameterSource()
                            .addValue("id", customer.id())
                            .addValue("name", customer.name()))
            .build();
}

@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        JdbcBatchItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(3, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}

@Bean
Job importCustomersJob(JobRepository jobRepository, Step importCustomersStep) {
    return new JobBuilder("importCustomersJob", jobRepository)
            .start(importCustomersStep)
            .build();
}
```

Để kiểm tra **failure rồi restart**, Step ở trên không khai báo `.faultTolerant().skip(...)` cho `IllegalStateException`. Nếu cấu hình bỏ qua exception đó, Step có thể kết thúc `COMPLETED`, làm cho test không còn là kịch bản restart do lỗi nữa.

Bảng đích nên nằm trên cùng cơ chế quản lý transaction phù hợp với `transactionManager` truyền vào `chunk(...)`. Một khóa chính duy nhất trên `id` vừa giúp xác nhận dữ liệu đầy đủ, vừa khiến việc ghi trùng có thể xuất hiện dưới dạng lỗi rõ ràng.

## 6. Integration test: tạo dữ liệu, fail, restart, đối chiếu kết quả

Ví dụ dùng `@SpringBatchTest` để có `JobLauncherTestUtils`, `@SpringBootTest` để khởi tạo context và `JdbcTemplate` để đọc dữ liệu đã ghi. Giả định test import cấu hình các bean ở phần 5 và chạy Job đồng bộ. Nếu context có nhiều Job, set rõ `Job` cần kiểm thử.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
})
class ImportCustomersRestartTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("importCustomersJob")
    private Job importCustomersJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private AtomicBoolean failOnceAt105;

    @BeforeEach
    void setup() {
        jobLauncherTestUtils.setJob(importCustomersJob);
        failOnceAt105.set(true);
        jdbcTemplate.update("DELETE FROM imported_customer");
    }

    @Test
    void shouldRestartFromLastCommittedChunk(@TempDir Path tempDir) throws Exception {
        // Bước 1: Chuẩn bị input fixture bất biến trong suốt test.
        Path inputFile = tempDir.resolve("customers.csv");
        Files.writeString(inputFile, """
                id,name
                101,An
                102,Binh
                103,Chi
                104,Dung
                105,Ha
                106,Minh
                107,Thao
                """, StandardCharsets.UTF_8);

        // Bước 2: Khởi tạo identifying parameters đúng một lần.
        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", inputFile.toAbsolutePath().toString(), true)
                .addString("testCaseId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        // Bước 3: Lần chạy đầu thất bại tại id=105.
        JobExecution firstRun = jobLauncherTestUtils.launchJob(params);
        assertThat(firstRun.getStatus()).isEqualTo(BatchStatus.FAILED);

        // Chỉ chunk đầu tiên (101..103) đã commit.
        assertThat(storedIds()).containsExactly(101L, 102L, 103L);

        StepExecution firstStep = findStep(firstRun, "importCustomersStep");
        assertThat(firstStep.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(firstStep.getWriteCount()).isEqualTo(3);

        // Bước 4: Restart với CHÍNH XÁC params cũ.
        JobExecution secondRun = jobLauncherTestUtils.launchJob(params);
        assertThat(secondRun.getStatus()).isEqualTo(BatchStatus.COMPLETED);

        // Restart là JobExecution mới của cùng JobInstance.
        assertThat(secondRun.getId()).isNotEqualTo(firstRun.getId());
        assertThat(secondRun.getJobInstance().getInstanceId())
                .isEqualTo(firstRun.getJobInstance().getInstanceId());

        StepExecution secondStep = findStep(secondRun, "importCustomersStep");
        assertThat(secondStep.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(secondStep.getWriteCount()).isEqualTo(4);

        // Bước 5: Đối chiếu dữ liệu cuối cùng; không thiếu, không trùng.
        assertThat(storedIds()).containsExactly(
                101L, 102L, 103L, 104L, 105L, 106L, 107L);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM imported_customer", Long.class))
                .isEqualTo(7L);
    }

    private List<Long> storedIds() {
        return jdbcTemplate.queryForList(
                "SELECT id FROM imported_customer ORDER BY id", Long.class);
    }

    private StepExecution findStep(JobExecution execution, String stepName) {
        return execution.getStepExecutions().stream()
                .filter(step -> stepName.equals(step.getStepName()))
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "Missing StepExecution: " + stepName));
    }
}
```

Đoạn test cần `spring-batch-test`, Spring Boot test starter, JDBC driver và database kiểm thử (chẳng hạn H2). Bảng `imported_customer` có thể được tạo qua `schema.sql` hoặc công cụ migration của dự án; `spring.batch.jdbc.initialize-schema=always` chỉ liên quan đến việc khởi tạo các bảng metadata của Batch cho loại database được Spring Boot hỗ trợ. **Không dùng** thuộc tính đó để kỳ vọng Boot tự tạo bảng nghiệp vụ.

Ở ví dụ này, `@BeforeEach` xóa dữ liệu đích **trước lần chạy đầu** để kịch bản độc lập. Tuyệt đối không xóa bảng đích hoặc metadata Batch **giữa `firstRun` và `secondRun`**: làm vậy sẽ phá checkpoint hoặc xóa dấu vết dữ liệu đã commit, dẫn tới một bài test không còn mô phỏng restart.

Để đảm bảo output ổn định, `ItemProcessor` dùng flag giả lập đã được reset trong `setup()`, còn định danh `testCaseId` được tạo duy nhất cho từng test. Nếu test không chạy đồng bộ, cần đợi Job kết thúc rồi mới kiểm tra trạng thái; trong ví dụ này giả định `JobLauncher` đồng bộ.

## 7. Những điều assertion đang chứng minh

| Assertion | Ý nghĩa |
| --- | --- |
| `firstRun.getStatus() == FAILED` | Lỗi giả lập thực sự khiến lần chạy đầu dừng thất bại. |
| Bảng đích chỉ có `101, 102, 103` | Transaction của chunk đầu đã commit; chunk đang lỗi không làm thay đổi dữ liệu đích. |
| `firstStep.getWriteCount() == 3` | Lần thực thi đầu đã ghi nhận ba item được ghi thành công. |
| `secondRun.getId() != firstRun.getId()` | Hai lần chạy tạo hai `JobExecution` khác nhau. |
| Hai execution có cùng `JobInstance` id | Lần thứ hai là restart của cùng JobInstance, không phải Job mới. |
| `secondStep.getWriteCount() == 4` | Step sau restart ghi tiếp bốn item còn lại trong fixture này. |
| Bảng đích có đúng 7 ID duy nhất | Không bỏ sót hoặc nhân đôi dữ liệu qua ranh giới lỗi và restart. |

Trong một job tổng quát, các count `readCount` và `writeCount` thuộc về **từng `StepExecution`**, không tự đại diện cho tổng tất cả các lần chạy của JobInstance. Ở kịch bản cố định này, `writeCount` lần đầu là 3 và lần restart là 4; con số 7 trong database mới là kết quả cuối cùng của toàn bộ quá trình.

`readCount` của một lần thất bại có thể khó suy diễn chính xác khi lỗi, transaction rollback hoặc retry xảy ra. Vì thế, ở test restart trọng tâm là **checkpoint, trạng thái, dữ liệu đã commit và kết quả cuối cùng**. Chỉ assert chính xác các count khác nếu chính chúng là hành vi mà test đã thiết kế để kiểm chứng.

## 8. Test data cần phủ những trường hợp restart nào?

Một fixture minh họa là điểm khởi đầu tốt. Để phát hiện các lỗi thực tế, nên tạo nhiều bộ dữ liệu ứng với **những vị trí gián đoạn** khác nhau:

| Kịch bản | Ví dụ data và vị trí lỗi | Điều cần kiểm tra sau restart |
| --- | --- | --- |
| Lỗi trước commit đầu tiên | 7 item, chunk 3, lỗi tại item 2 | Bảng đích ban đầu rỗng; restart đọc và ghi đủ 7 item. |
| Lỗi sau ít nhất một commit | 7 item, chunk 3, lỗi tại item 5 | 3 item đã commit được giữ nguyên; 4 item còn lại được ghi. |
| Lỗi ngay đầu chunk kế tiếp | 7 item, chunk 3, lỗi tại item 4 | Checkpoint không bỏ qua item 4. |
| Lỗi ở chunk cuối chưa đủ kích thước | 7 item, chunk 3, lỗi tại item 7 | Sau khi hai chunk đã commit, restart ghi item 7. |
| Có filter trong processor | 7 item, một item trả `null` | Không nhầm filtered item với item thất lạc; output bằng tập hợp kỳ vọng. |
| Có exception được skip | Một item hỏng nhưng được phép skip | Nếu Job vẫn `COMPLETED`, đó là skip flow chứ không phải failed restart. |
| Writer có khả năng ghi trùng | Thử ghi lại item vừa commit | Khóa duy nhất hoặc cơ chế idempotency chặn trùng dữ liệu. |
| Có nhiều Step | Step A hoàn thành, Step B thất bại | Step A đã hoàn thành thường được bỏ qua ở restart, Step B được chạy lại. |
| Dữ liệu nguồn thay đổi | Thay thứ tự hoặc thêm/xóa dòng sau failure | Phát hiện quy tắc ổn định input bị vi phạm; kiểm thử chính sách của hệ thống thay vì mặc định vẫn an toàn. |

Các trường hợp này không cần gộp vào một test duy nhất. Mỗi test nên ghi rõ vị trí lỗi, tập dữ liệu trước lỗi và tập dữ liệu kỳ vọng sau restart. Khi lỗi xảy ra quá sớm, bài test có thể bỏ sót bug chỉ xuất hiện sau checkpoint; khi lỗi xảy ra quá muộn, bài test có thể bỏ sót bug khôi phục phần chunk chưa commit.

## 9. Kiểm tra restart với nhiều Step

Giả sử Job có hai Step:

```text
importCustomersJob
  Step A: validateInput     --> COMPLETED
  Step B: importCustomers   --> FAILED (lần 1)
```

Nếu Step A đã hoàn thành và dùng cấu hình mặc định, khi restart Spring Batch thường **bỏ qua Step A** và chạy lại Step B. Đó là hành vi khác với chạy một `JobInstance` mới, nơi Step A có thể chạy lại từ đầu.

Bộ dữ liệu test nên chứa dấu vết rõ ràng của Step A, chẳng hạn một bản ghi audit test có `validationId`. Sau restart, ta có thể assert audit không được ghi lần thứ hai. Đồng thời, các dòng Step B còn lại phải được ghi đủ.

Lưu ý rằng `.allowStartIfComplete(true)` cho phép một Step đã `COMPLETED` chạy lại trong lần thực thi Job tiếp theo của cùng JobInstance; nếu cấu hình này được bật, kỳ vọng về Step A phải thay đổi. `startLimit(...)` và `.preventRestart()` ở mức Job cũng ảnh hưởng khả năng restart. Test fixture phải khớp với **chính sách restart đã định nghĩa**, không dựa vào giả định rằng mọi Step đều luôn chạy lại hay luôn được bỏ qua.

## 10. Dữ liệu kiểm tra restart với `JdbcPagingItemReader` hoặc nguồn database

Khi nguồn là database, lựa chọn dữ liệu kiểm thử cần quan tâm tới **ordering và biến động tập kết quả**. Ví dụ:

```sql
CREATE TABLE source_customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL
);

INSERT INTO source_customer (id, name, status) VALUES
    (101, 'An', 'NEW'),
    (102, 'Binh', 'NEW'),
    (103, 'Chi', 'NEW'),
    (104, 'Dung', 'NEW'),
    (105, 'Ha', 'NEW'),
    (106, 'Minh', 'NEW'),
    (107, 'Thao', 'NEW');
```

Nếu reader truy vấn `WHERE status = 'NEW'`, còn writer/processor đổi ngay status của các bản ghi đã xử lý trong bảng nguồn, thì tập kết quả cho lần restart **không còn giống lần đầu**. Tùy cách paging và checkpoint, reader có thể bỏ sót bản ghi. Đây là lỗi thiết kế dữ liệu và chiến lược đọc, không phải vấn đề có thể giải quyết bằng cách cố định một assertion `readCount`.

Đối với paging reader, cần sort key ổn định và duy nhất (thường dùng `id`) để hỗ trợ khôi phục vị trí một cách xác định. Nếu yêu cầu nghiệp vụ đòi cập nhật chính dữ liệu nguồn trong khi đọc, cân nhắc snapshot, staging table, đánh dấu version hoặc chiến lược reader phù hợp, đồng thời đưa biến động đó vào dữ liệu test.

Một tập dữ liệu mạnh nên có thêm các bản ghi không thuộc phạm vi truy vấn, ví dụ `status = 'DONE'`, để chứng minh rằng reader không vô tình lấy toàn bộ bảng. Tuy nhiên, các bản ghi ngoài phạm vi phải được đưa vào **kỳ vọng riêng**; không cộng chúng vào `readCount` của Step.

## 11. Restart an toàn và kiểm tra idempotency

Trong kịch bản JDBC, transaction và checkpoint giúp hạn chế xử lý trùng trong phạm vi chunk. Nhưng trong hệ thống tích hợp, một writer có thể gọi API bên ngoài, ghi vào queue hoặc tạo file, trong khi transaction của Batch chỉ quản lý cơ sở dữ liệu địa phương. Nếu API đã nhận request rồi Step lỗi trước khi lưu checkpoint, restart có thể gọi API lần nữa.

Ví dụ, dùng mã nghiệp vụ `customerId + businessDate` làm **idempotency key** khi gửi sang hệ thống ngoài:

```text
Lần 1: gửi customer=104, businessDate=2026-11-15
        -> hệ thống ngoài tiếp nhận
        -> Batch lỗi trước checkpoint

Restart: gửi lại cùng customer=104, businessDate=2026-11-15
         -> hệ thống ngoài nhận ra idempotency key cũ
         -> không tạo thêm một bản ghi trùng
```

Một bộ dữ liệu test cho writer kiểu này cần mô phỏng **side effect đã xảy ra nhưng checkpoint chưa commit**. Kỳ vọng không chỉ là `BatchStatus.COMPLETED` mà còn là **chính xác một kết quả nghiệp vụ** cho mỗi key. Khóa chính database, upsert, outbox hoặc idempotency key đều có thể là cơ chế bảo đảm tùy kiến trúc.

## 12. Checklist chuẩn bị dữ liệu test restart

Trước khi đưa một kịch bản restart vào test suite, nên định nghĩa rõ:

1. **Bộ input:** tập bản ghi, thứ tự, các ID và phiên bản dữ liệu nguồn.
2. **Chunk size:** mỗi chunk có bao nhiêu item và item nào nằm ngay trước/sau ranh giới commit.
3. **Điểm lỗi:** lỗi tại reader, processor, writer hay sau một side effect; xảy ra chính xác ở lần xử lý nào.
4. **Loại lỗi:** exception làm Step fail hay được skip/retry theo cấu hình.
5. **Checkpoint:** reader/writer nào có trạng thái; `ExecutionContext` được lưu ở đâu và có còn tồn tại sau failure hay không.
6. **Dữ liệu sau lần 1:** xác định bản ghi nào đã commit, bản ghi nào chưa commit.
7. **Tham số Job:** giữ nguyên identifying parameters để restart đúng `JobInstance`.
8. **Dữ liệu sau restart:** đối chiếu cả ID, giá trị và tổng số bản ghi; kiểm tra không trùng lặp và không thiếu sót.
9. **Isolation:** test dùng dữ liệu nguồn, repository và bảng đích độc lập với những lần chạy khác.
10. **Tính giao dịch:** xác định hệ thống đích có rollback cùng chunk hay cần cơ chế idempotency riêng.

Điều quan trọng nhất khi thiết kế **dữ liệu để kiểm tra restart** là chọn bản ghi và vị trí lỗi sao cho có thể nhìn thấy rõ **trạng thái trước failure và trạng thái sau restart**. Khi fixture chứa một chunk đã commit, một chunk bị gián đoạn và một phần dữ liệu còn chờ xử lý, test có thể xác nhận được giá trị cốt lõi của Spring Batch restart: **tiếp tục từ checkpoint phù hợp và tạo ra kết quả cuối cùng chính xác**.
