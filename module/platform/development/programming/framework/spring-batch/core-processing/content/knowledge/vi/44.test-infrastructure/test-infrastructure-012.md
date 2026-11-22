# Phân biệt unit test và batch integration test trong Spring Batch

Trong một ứng dụng Spring Batch, cùng một logic xử lý có thể được kiểm tra ở nhiều cấp độ. Chẳng hạn, step nhập đơn hàng gồm `ItemReader` lấy dữ liệu, `ItemProcessor` chuẩn hóa và `ItemWriter` ghi vào cơ sở dữ liệu. Ta có thể gọi trực tiếp `ItemProcessor.process()` để xác nhận quy tắc chuẩn hóa, hoặc khởi chạy một `Step` thật để biết reader, processor, writer, transaction và hạ tầng Spring Batch phối hợp có đúng hay không.

Hai phép thử đó giải quyết **hai loại rủi ro khác nhau**:

- **Unit test** xác minh một đơn vị logic trong điều kiện các dependency bên ngoài được tách riêng hoặc thay bằng test double. Nó thường không khởi tạo Spring context, `JobRepository`, database hoặc Batch runtime.
- **Batch integration test** xác minh sự phối hợp thực tế của các thành phần trong một step hoặc job, bao gồm hạ tầng thực thi Spring Batch khi thuộc phạm vi test. Nó thường tạo Spring context, `JobRepository`, transaction manager và các tài nguyên như database hoặc file thử nghiệm.

Điểm quyết định **không phải** file test có tên `*UnitTest` hay `*IntegrationTest`, cũng không chỉ là có `@SpringBootTest` hay không. Cần nhìn vào *ranh giới hệ thống được thực thi thật*: có chạy cơ chế batch, có thực sự đọc/ghi qua hạ tầng, có xác nhận trạng thái và tác dụng phụ hay chỉ gọi logic Java thuần?

Đây là kiến thức nền của chương **Test infrastructure** trong **Spring Batch Core Processing**: chọn đúng loại test sẽ giúp phát hiện lỗi chính xác, giảm thời gian chạy suite và hạn chế test mong manh.

## 1. Một ví dụ để hình dung hai cấp độ

Giả sử job nhập danh sách mã đơn hàng:

```text
importOrdersJob
  |
  +-- importOrdersStep (chunk-oriented)
        |
        +-- ItemReader<String>       đọc: " a001 ", "  ", " b002 "
        |
        +-- ItemProcessor<String,String>
        |      trim + uppercase
        |      dòng trắng -> null (filter)
        |
        +-- ItemWriter<String>       ghi các mã chuẩn hóa vào database
```

**Câu hỏi của unit test:** Với input `" a001 "`, processor có trả về `"A001"` không? Với dòng trắng, nó có trả về `null` để lọc không?

**Câu hỏi của integration test:** Khi chạy `importOrdersStep`, framework có đọc ba item, lọc một item, ghi hai item, đánh dấu step `COMPLETED` và thực sự lưu `A001`, `B002` vào database không?

Nếu processor đúng nhưng cấu hình writer sai tên bảng, unit test vẫn xanh. Nếu writer chạy đúng nhưng quy tắc chuẩn hóa sai ở một trường hợp biên, integration test với fixture quá đơn giản có thể không phát hiện. Vì vậy cả hai loại test đều cần thiết.

## 2. So sánh unit test và batch integration test

| Tiêu chí | Unit test | Batch integration test |
| --- | --- | --- |
| Mục tiêu chính | Kiểm tra logic của một class/method và hành vi được định nghĩa tại ranh giới của nó | Kiểm tra các component phối hợp trong một step, job và hạ tầng thực thi |
| Đối tượng thường gặp | `ItemProcessor`, validator, mapper, formatter, tasklet logic tách thành service | `Step`, `Job`, reader/writer thật, listener, transaction, `JobRepository` |
| Khởi tạo Spring context | Thường không cần | Thường cần, qua Spring Test hoặc Spring Boot Test |
| Dữ liệu | Object Java, collection, mock/stub | File fixture, database test, `JobParameters`, `ExecutionContext` |
| Dependency | Mock/fake/stub hoặc dependency đơn giản có thể kiểm soát | Thành phần thật trong phạm vi tích hợp; chỉ mock hệ thống ngoài phạm vi test |
| Cách chạy | Gọi method trực tiếp | Khởi chạy `Step`/`Job` bằng công cụ Batch test hoặc `JobOperator`/launcher phù hợp phiên bản |
| Kiểm tra | Giá trị trả về, exception, tương tác với collaborator | `JobExecution`, `StepExecution`, exit status, read/write/skip counts, dữ liệu đã commit |
| Transaction và restart | Không được kiểm chứng nếu chỉ gọi method | Có thể kiểm chứng trong hạ tầng Batch và repository test |
| Tốc độ | Thường nhanh, dễ cô lập | Thường chậm hơn do tạo context và dùng I/O |
| Độ chính xác về cấu hình | Không bảo đảm wiring, scope hoặc schema thật đúng | Bắt được lỗi wiring, SQL, transaction, scope và flow trong phần được thực thi |
| Khi thất bại | Thường chỉ ra ngay logic bị lỗi | Cần điều tra thêm trong cấu hình, dependency, metadata hoặc dữ liệu |

Một integration test **không nhất thiết** phải khởi chạy cả job. Chạy một step qua Spring Batch với `JobRepository` thực là một bài kiểm thử tích hợp ở phạm vi step. Ngược lại, test có `@SpringBootTest` nhưng mock toàn bộ dependency và chỉ gọi một method vẫn có thể chủ yếu kiểm tra logic component; annotation một mình không xác định độ sâu của phép thử.

## 3. Unit test: kiểm tra `ItemProcessor` mà không chạy Spring Batch

Trong Spring Batch, `ItemProcessor<I, O>` là điểm thuận tiện để đặt logic có thể unit test. Ví dụ processor chuẩn hóa mã đơn hàng và lọc dòng trống:

```java
package com.example.batch;

import java.util.Locale;
import org.springframework.batch.item.ItemProcessor;

public final class NormalizeOrderCodeProcessor
        implements ItemProcessor<String, String> {

    @Override
    public String process(String item) {
        if (item == null || item.isBlank()) {
            // Spring Batch xem null từ processor là item bị filter.
            return null;
        }

        String code = item.strip().toUpperCase(Locale.ROOT);
        if (code.length() > 20) {
            throw new IllegalArgumentException("Order code is too long");
        }
        return code;
    }
}
```

Unit test bằng JUnit Jupiter và AssertJ:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class NormalizeOrderCodeProcessorTest {

    private NormalizeOrderCodeProcessor processor;

    @BeforeEach
    void setUp() {
        processor = new NormalizeOrderCodeProcessor();
    }

    @Test
    void normalizesLeadingWhitespaceAndCase() throws Exception {
        assertThat(processor.process(" a001 ")).isEqualTo("A001");
        assertThat(processor.process("b002")).isEqualTo("B002");
    }

    @Test
    void filtersBlankOrNullInput() throws Exception {
        assertThat(processor.process("   ")).isNull();
        assertThat(processor.process(null)).isNull();
    }

    @Test
    void rejectsCodeLongerThanLimit() {
        assertThatThrownBy(() -> processor.process("X".repeat(21)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("Order code is too long");
    }
}
```

Test trên **không sử dụng** `@SpringBootTest`, `@SpringBatchTest`, database hay `JobParameters`. Nó chứng minh chính xác kết quả từng lần gọi `process()` và hành vi ở trường hợp biên. Unit test này không thể kết luận rằng step thực tế gọi processor, lọc đúng số bản ghi, ghi vào database hay commit thành công.

### 3.1. Khi nào dùng mock/stub?

Nếu processor dùng `PricingService`, `ReferenceDataClient` hoặc `OrderRepository`, trong unit test có thể thay chúng bằng Mockito mock hoặc fake để kiểm soát kết quả và lỗi:

```java
// Mẫu minh họa khi production processor có dependency PricingService.
PricingService pricing = mock(PricingService.class);
when(pricing.getRate("VIP")).thenReturn(new BigDecimal("0.90"));

OrderPriceProcessor processor = new OrderPriceProcessor(pricing);
OrderPrice actual = processor.process(new Order("A001", "VIP"));

assertThat(actual.total()).isEqualByComparingTo("90.00");
verify(pricing).getRate("VIP");
```

`PricingService`, `OrderPriceProcessor`, `Order` và `OrderPrice` là các kiểu minh họa của ứng dụng, không phải API Spring Batch. Mục đích của mẫu là nêu rõ ranh giới: test kiểm tra processor xử lý kết quả từ service ra sao, **không** kiểm tra service hay database thật. Cũng không nên mock chính `ItemProcessor` đang cần kiểm thử, vì khi đó logic của nó sẽ không được thực thi.

### 3.2. Tasklet và writer cũng có thể unit test

Không phải mọi `Tasklet` đều đòi hỏi khởi chạy một `Step`. Nếu tasklet chỉ gọi một service nghiệp vụ, tách logic khỏi API framework và unit test service đó trực tiếp. Tương tự, logic tạo dòng CSV hoặc ánh xạ bản ghi sang entity có thể kiểm thử riêng mà không mở file hoặc database. Nhưng khi cần kiểm tra lifecycle `ItemStream`, chunk transaction và cơ chế skip/retry, phải thêm integration test.

## 4. Batch integration test: khởi chạy step và kiểm tra kết quả thực

Một integration test cho `importOrdersStep` cần những thành phần sau:

```text
JUnit 5 / Spring Test
          |
    Spring ApplicationContext
          |
    JobLauncherTestUtils (Spring Batch 5)
          |
        Step / Job
          |
  Reader -> Processor -> Writer
          |
  PlatformTransactionManager
          |
     Database H2 (test)
          |
  JobRepository + bảng metadata BATCH_*
```

Ở đây H2 thay vai trò database thực trong môi trường kiểm thử. Trong các ứng dụng dùng SQL đặc thù PostgreSQL/Oracle hoặc tính năng khóa và transaction đặc biệt, Testcontainers với đúng database của ứng dụng cho kết quả thực tế hơn H2.

### 4.1. Dependency ví dụ

Ví dụ tiếp theo dùng **Spring Boot 3.x, Spring Batch 5.x, JUnit Jupiter** và Gradle. Nên để Spring Boot BOM thống nhất version giữa các thư viện:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`spring-batch-test` có `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils` và utility cho job/step scope. `@SpringBatchTest` hỗ trợ hạ tầng test; bản thân nó không thay thế hoàn toàn việc khai báo Spring context với `@SpringBootTest` hoặc cấu hình test tương đương.

### 4.2. Integration test hoàn chỉnh cho một `chunk-oriented Step`

Sau khi có `NormalizeOrderCodeProcessor` ở phần trước, tạo class kiểm thử sau trong `src/test/java/com/example/batch/NormalizeOrdersStepIntegrationTest.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = NormalizeOrdersStepIntegrationTest.TestBatchApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class NormalizeOrdersStepIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void createAndClearBusinessTable() {
        jdbcTemplate.execute("""
            CREATE TABLE IF NOT EXISTS processed_codes (
                code VARCHAR(20) NOT NULL
            )
            """);
        jdbcTemplate.update("DELETE FROM processed_codes");
    }

    @Test
    void runsReaderProcessorWriterAndCommitsResults() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            // Nhận diện mỗi lần chạy để tránh trùng JobInstance đã hoàn tất.
            .addString("testRunId", UUID.randomUUID().toString())
            .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
            "normalizeCodesStep", parameters
        );

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getStepExecutions()).hasSize(1);

        StepExecution stepExecution =
            execution.getStepExecutions().iterator().next();

        assertThat(stepExecution.getStepName()).isEqualTo("normalizeCodesStep");
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(stepExecution.getReadCount()).isEqualTo(3);
        assertThat(stepExecution.getFilterCount()).isEqualTo(1);
        assertThat(stepExecution.getWriteCount()).isEqualTo(2);

        List<String> committedCodes = jdbcTemplate.queryForList(
            "SELECT code FROM processed_codes ORDER BY code",
            String.class
        );
        assertThat(committedCodes).containsExactly("A001", "B002");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestBatchApplication {

        @Bean
        Job normalizeCodesJob(
                JobRepository jobRepository,
                @Qualifier("normalizeCodesStep") Step normalizeCodesStep) {
            return new JobBuilder("normalizeCodesJob", jobRepository)
                .start(normalizeCodesStep)
                .build();
        }

        @Bean
        @StepScope
        ItemReader<String> codesReader() {
            // Tạo reader mới cho mỗi StepExecution, tránh dùng lại cursor cũ.
            return new ListItemReader<>(List.of(" a001 ", "   ", " b002 "));
        }

        @Bean
        Step normalizeCodesStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                @Qualifier("codesReader") ItemReader<String> reader,
                JdbcTemplate jdbcTemplate) {

            return new StepBuilder("normalizeCodesStep", jobRepository)
                .<String, String>chunk(2, transactionManager)
                .reader(reader)
                .processor(new NormalizeOrderCodeProcessor())
                .writer(chunk -> {
                    for (String code : chunk) {
                        jdbcTemplate.update(
                            "INSERT INTO processed_codes(code) VALUES (?)", code
                        );
                    }
                })
                .build();
        }
    }
}
```

**Các điểm khác biệt so với unit test ở phần 3:**

1. Spring Test khởi tạo `ApplicationContext` với `Job`, `Step`, reader và các dependency đã được cấu hình. `spring.batch.job.enabled=false` ngăn Spring Boot tự chạy job ngay khi context được tạo; test sẽ chủ động chạy step.
2. `@SpringBatchTest` cung cấp `JobLauncherTestUtils`. `launchStep("normalizeCodesStep", ...)` yêu cầu Batch thực thi step với `JobRepository`, transaction và metadata. Vì đây là test một step, các step khác trong job thực sẽ không tự chạy.
3. `@StepScope` đảm bảo `ListItemReader` mới được cấp cho mỗi step execution. Điều đó đặc biệt có ích khi reader có cursor/trạng thái, vì dùng cùng instance qua nhiều test có thể làm lần chạy sau không còn item.
4. Bảng `processed_codes` là bảng nghiệp vụ thực trong H2 thử nghiệm. Chỉ kiểm tra `BatchStatus.COMPLETED` là chưa đủ; assertions còn xác minh metadata `readCount`, `filterCount`, `writeCount` và các dòng đã lưu.
5. Câu lệnh `INSERT` chạy trong transaction của chunk. Nếu muốn kiểm tra rollback, cần bổ sung một kịch bản lỗi có kiểm soát và quan sát dữ liệu đã/không được commit sau khi step kết thúc.
6. `testRunId` là identifying `JobParameter`, tránh đụng metadata của một `JobInstance` đã hoàn tất. Trong test suite thực tế, đồng thời phải cô lập bảng nghiệp vụ hoặc database giữa các test chạy song song.

Trong dự án thực, cấu hình test thường **import cấu hình step sản xuất** và thay chỉ các dependency ngoài phạm vi (chẳng hạn input file, external API). Ví dụ trên khai báo cấu hình tối giản ngay trong test để dễ học, nhưng nếu copy lại toàn bộ cấu hình step vào test, bài test có thể vô tình kiểm tra một bản cấu hình khác với ứng dụng. Với mục tiêu integration thực tế, nên inject chính `Step` production khi có thể.

### 4.3. Điều chỉnh khi dùng Spring Batch 6

Spring Batch 6.x giới thiệu `JobOperatorTestUtils` và phương thức `startStep(...)`, thay vai trò sử dụng `JobLauncherTestUtils.launchStep(...)` của 5.x (API cũ được deprecated). Một số core type đã đổi package trong 6.x. Hãy chọn một phiên bản đồng nhất với Spring Boot/dependency của project và cập nhật import, test utility tương ứng; không trộn code của Spring Batch 5 với classpath Spring Batch 6.

Về mặt khái niệm, quy trình kiểm thử không đổi: chuẩn bị dữ liệu và parameters, chạy step thực qua test utility, lấy `JobExecution` và `StepExecution`, rồi kiểm tra metadata và output.

## 5. Chọn phạm vi integration test: một step hay cả job?

Batch integration test có ít nhất hai phạm vi thường gặp:

```text
Unit test:              processor.process(" a001 ")
                             |
                             v
                            "A001"

Step integration test:  [importOrdersStep]
                       Reader -> Processor -> Writer
                             |
                             v
                       StepExecution + output

Job integration test:   [step A] -> [step B] -> [step C]
                             |
                             v
                       JobExecution + output cuối
```

**Chạy riêng step** phù hợp khi muốn kiểm tra đọc/ghi, transaction, skip, retry hoặc listener của step. Với Spring Batch 5, `JobLauncherTestUtils.launchStep(name, params)` tạo một job bao bọc để chạy step được chọn. Phạm vi này không chứng minh rằng toàn bộ flow của job đã được nối đúng.

**Chạy toàn job** phù hợp khi cần kiểm tra thứ tự step, điều kiện chuyển bước, dữ liệu được chuyển qua `JobExecutionContext`, restart và hiệu ứng cuối cùng của job. Trong Spring Batch 5, `JobLauncherTestUtils.launchJob(params)` là cách thông dụng khi test context có job thích hợp. Một test có thể cần cả hai loại: nhiều test step để bao phủ dữ liệu và một số test job cho các luồng quan trọng.

| Cần chứng minh | Phạm vi nên chọn |
| --- | --- |
| Quy tắc làm sạch mã và xử lý input null | Unit test processor |
| Reader thực mở được file và parse được dữ liệu | Integration test reader hoặc step với file fixture |
| Chunk ghi đúng database và transaction commit | Step integration test |
| Retry/skip policy áp dụng đúng | Step integration test với lỗi giả lập có kiểm soát |
| `@StepScope` nhận đúng `JobParameters` | Component scope test hoặc step integration test |
| Step B nhận đúng context do step A ghi | Job integration test hoặc integration test nhiều step |
| Chuyển nhánh job theo `ExitStatus` | Job integration test |
| Restart không xử lý lại dữ liệu đã commit | Integration test với `JobRepository` và dữ liệu tồn tại qua lần restart |

## 6. Khác nhau về phụ thuộc và test doubles

### Trong unit test

Sử dụng dependency đơn giản, fake, stub hoặc mock để kiểm soát đầu vào và xác minh tương tác. Ví dụ: processor gọi `ExchangeRateService`, test có thể làm cho service luôn trả tỷ giá cố định, tránh truy cập mạng hoặc database. Không cần dựng cả job để biết phép tính trong processor đúng hay sai.

Nhược điểm là mock chỉ hành xử như người viết test quy định. Nếu mock `OrderRepository.save()` luôn thành công, unit test không phát hiện được SQL bị sai, transaction bị rollback hay ràng buộc `UNIQUE` trong database.

### Trong batch integration test

Nên dùng thực những thành phần thuộc ranh giới cần kiểm tra:

- Nếu kiểm tra `JdbcBatchItemWriter`, dùng một database thử nghiệm và xác nhận dữ liệu đã ghi, thay vì mock `JdbcTemplate` rồi chỉ đếm số lần gọi.
- Nếu kiểm tra `FlatFileItemWriter`, ghi file vào `@TempDir` và đọc lại nội dung, encoding hoặc thứ tự dòng.
- Nếu kiểm tra restart, dùng `JobRepository` có metadata được giữ qua các lần chạy liên quan.
- Nếu kiểm tra giao tiếp với hệ thống ngoài không thuộc phạm vi test (API thanh toán, email, message broker), có thể dùng fake server hoặc test container tương ứng. Ranh giới này phải được xác định rõ.

Không phải mọi integration test đều bắt buộc kết nối tất cả hệ thống bên ngoài. Ví dụ, có thể kiểm tra trọn vẹn reader–processor–writer và transaction của batch trong H2, trong khi mock một API giá cả ở bên ngoài. Khi đó kết quả chứng minh phần tích hợp **nằm trong test**, chứ không chứng minh API thật sẽ hoạt động.

## 7. Infrastructure nào cần có để chạy batch integration test?

### 7.1. `ApplicationContext` và cấu hình bean

Spring context chịu trách nhiệm nối các bean của job, step, reader, writer, processor, listener và các hạ tầng liên quan. Các annotation như `@StepScope` và `@JobScope` giúp thực hiện late binding từ `JobParameters` hoặc `ExecutionContext`.

Unit test thông thường không cần scope. Nhưng nếu muốn kiểm tra một component riêng lẻ có `@StepScope` mà chưa chạy cả step, Spring Batch Test có `StepScopeTestUtils` và `MetaDataInstanceFactory` để thiết lập `StepExecution` trong phạm vi kiểm thử.

### 7.2. `JobRepository` và metadata

`JobRepository` lưu các thực thể như `JobInstance`, `JobExecution`, `StepExecution`, execution context và trạng thái. Batch integration test dùng repository để đánh giá hành vi start, complete, fail hoặc restart. Những bảng `BATCH_*` cần tồn tại trong database test trước khi chạy step hoặc job. Với Spring Boot 3.x và embedded database, có thể dùng `spring.batch.jdbc.initialize-schema=always` trong cấu hình test.

Sự tồn tại của metadata tạo một khác biệt quan trọng: nếu chạy lại cùng tên job và cùng **identifying `JobParameters`** trên repository đã ghi nhận lần chạy `COMPLETED`, Batch có thể báo `JobInstanceAlreadyCompleteException`. Đây là cơ chế đúng của Spring Batch, không tự nó là lỗi logic nghiệp vụ. Test phải dùng parameters khác hoặc chủ động chuẩn bị/xóa metadata trong database dành riêng cho test.

### 7.3. `PlatformTransactionManager`

Chunk-oriented step quản lý commit/rollback thông qua transaction manager. Unit test processor không mô phỏng được điều này. Integration test có thể làm writer cố tình thất bại ở một item để quan sát số record được commit trước đó, trạng thái step và tác dụng của chính sách retry/skip.

Chú ý: đánh dấu `@Transactional` trực tiếp trên method test không đồng nghĩa với kiểm chứng transaction của step. Transaction của test và transaction do Spring Batch quản lý có thể tương tác, khiến kết quả khó hiểu, đặc biệt khi chạy trên cùng thread. Với bài test cần chứng minh dữ liệu **đã commit**, nên đọc database sau khi step hoàn tất và tổ chức cleanup riêng.

### 7.4. Fixture và môi trường bên ngoài

Thiết lập một tập input nhỏ, xác định rõ output mong đợi. Với file, dùng `src/test/resources` cho fixture nguồn và `@TempDir` cho output. Với database, dùng schema/database riêng và dọn dữ liệu nghiệp vụ giữa các case. Khi H2 không hỗ trợ chính xác SQL/dialect production, có thể dùng Testcontainers với PostgreSQL, MySQL hoặc cơ sở dữ liệu tương ứng.

## 8. Cách kiểm chứng kết quả ở từng loại test

### Unit test: assert logic

Ví dụ `NormalizeOrderCodeProcessor`:

```java
assertThat(processor.process(" a001 ")).isEqualTo("A001");
assertThat(processor.process("   ")).isNull();
assertThatThrownBy(() -> processor.process("X".repeat(21)))
    .isInstanceOf(IllegalArgumentException.class);
```

Các assert tập trung vào giá trị, exception và hợp đồng của class. Nếu dependency bị mock, có thể dùng `verify(...)`, nhưng không nên ràng buộc test quá chặt với những lời gọi nội bộ không ảnh hưởng đến hành vi mà class cam kết.

### Batch integration test: assert metadata **và** output

```java
assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getReadCount()).isEqualTo(3);
assertThat(stepExecution.getFilterCount()).isEqualTo(1);
assertThat(stepExecution.getWriteCount()).isEqualTo(2);

assertThat(jdbcTemplate.queryForList(
    "SELECT code FROM processed_codes ORDER BY code", String.class
)).containsExactly("A001", "B002");
```

Ví dụ này dùng các biến `jobExecution`/`stepExecution` được lấy từ lần chạy và bảng đã chuẩn bị trong fixture, tương tự phần 4. `BatchStatus.COMPLETED` không bảo đảm dữ liệu đúng: một step có thể chạy hết nhưng ghi nhầm cột, bỏ sót record hoặc sinh ra file sai encoding. Vì vậy kiểm tra output thực là phần không thể thiếu.

Trong các case lỗi, có thể assert `FAILED`, `getFailureExceptions()`, `readSkipCount`, `processSkipCount`, `writeSkipCount`, dữ liệu đã commit và nội dung `ExecutionContext`. Mỗi bộ đếm phải gắn với fixture và chính sách batch cụ thể, tránh khẳng định một con số tùy ý.

## 9. Failure, skip, retry và restart: nên test ở đâu?

### Quy tắc ném exception: unit test

Giả sử processor phải từ chối mã dài hơn 20 ký tự. Unit test trực tiếp như phần 3 cho biết exception được ném đúng ở trường hợp biên. Đây là nơi phù hợp để bao phủ nhiều giá trị đầu vào, vì test chạy nhanh.

### Chính sách skip/retry: integration test

Spring Batch có thể cấu hình để bỏ qua một số exception hoặc thử lại thao tác lỗi tạm thời. Unit test của processor không chứng minh được step có nhận diện exception trong `skip(...)`, thực thi retry, rollback chunk và cập nhật bộ đếm đúng hay không.

Ví dụ, khi processor ném `ValidationException` cho một record và step cấu hình `skipLimit`, integration test cần chuẩn bị input có record lỗi, chạy step, assert `processSkipCount` và xác nhận các record hợp lệ vẫn được ghi. Khi retry writer, cần dùng dependency có thể thất bại một số lần rồi thành công, đồng thời xác nhận output cuối cùng không bị trùng.

### Restart: integration test có metadata và trạng thái tồn tại

Restart chỉ có ý nghĩa khi hai lần chạy liên quan tới cùng một `JobInstance`, trạng thái trước đó và execution context được giữ lại. Để kiểm thử, chạy lần đầu cho thất bại ở một điểm được thiết kế, kiểm tra dữ liệu/metadata sau khi thất bại, rồi khởi chạy lại theo cơ chế restart của phiên bản đang dùng. Sau lần chạy tiếp, kiểm tra phần việc được tiếp tục đúng và không lặp lại dữ liệu đã commit.

Nếu giữa hai lần chạy test đã xóa toàn bộ metadata hoặc thay đổi identifying parameters, đó là **một job instance mới**, không còn là restart của lần trước.

## 10. Những sai lầm thường gặp khi phân loại test

| Sai lầm | Vì sao chưa đúng | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Thêm `@SpringBootTest` và gọi `processor.process()` rồi gọi đó là full integration test | Hạ tầng batch không được thực thi | Nếu chỉ kiểm tra logic, giữ unit test thuần; nếu muốn tích hợp, chạy step/job thật |
| Mock toàn bộ `ItemReader`, `ItemProcessor`, `ItemWriter` nhưng assert step `COMPLETED` | Cấu hình có thể chạy, nhưng logic đọc/ghi thực tế chưa được kiểm chứng | Giữ implementation thật cho phần đang được kiểm tra, chỉ mock ngoại vi |
| Chỉ assert `BatchStatus.COMPLETED` | Chưa khẳng định record hoặc file đầu ra đúng | Assert cả counters, output và dữ liệu cuối |
| Dùng database production trong integration test | Test có nguy cơ thay đổi dữ liệu và phụ thuộc trạng thái bên ngoài | Dùng database/schema test riêng và cleanup có kiểm soát |
| Dùng chung `ListItemReader` stateful qua nhiều lần chạy | Cursor có thể ở cuối sau test trước | Tạo reader mới theo step execution, ví dụ `@StepScope` |
| Dùng lại identifying parameters đã hoàn tất | Batch từ chối chạy job instance hoàn tất lần nữa | Tạo danh tính test riêng hoặc làm sạch metadata test |
| Xóa output/metadata sau pha một của restart test | Mất cơ sở để kiểm tra restart | Giữ trạng thái giữa hai pha, cleanup sau assertion cuối |
| Dựa vào H2 để khẳng định SQL đặc thù production | H2 có thể khác dialect, locking hoặc isolation | Dùng Testcontainers với database tương ứng cho các điểm quan trọng |
| Chạy mọi test bằng `@SpringBootTest` | Suite chậm và lỗi khó khoanh vùng | Unit test cho logic, integration test ở các ranh giới cần thiết |
| Coi API test 5.x và 6.x giống nhau | Class/package đã thay đổi theo major version | Kiểm tra phiên bản Spring Batch và chọn test utility tương ứng |

## 11. Tổ chức test suite và chiến lược thực tế

Một dự án có thể tổ chức test theo mục tiêu (tên package chỉ là ví dụ):

```text
src/test/java/com/example/batch/
    unit/
        NormalizeOrderCodeProcessorTest.java
        OrderValidatorTest.java
        ReportLineFormatterTest.java

    integration/
        NormalizeOrdersStepIntegrationTest.java
        ExportReportStepIntegrationTest.java
        ImportOrdersJobIntegrationTest.java

src/test/resources/
    fixtures/
        orders-valid.csv
        orders-with-errors.csv
```

Nên sử dụng unit tests để bao phủ rộng rãi input hợp lệ, input biên, lỗi nghiệp vụ và phép tính. Với mỗi step quan trọng, thêm integration tests cho đường đi thành công, output thực và các failure path quan trọng. Với mỗi job có flow đáng kể, thêm một vài integration tests chạy toàn job để kiểm tra transition, context giữa các step hoặc restart.

Một cách chọn loại test trước khi viết:

1. **Muốn biết quy tắc nghiệp vụ có đúng?** Gọi thẳng method với object Java và assert; bắt đầu bằng unit test.
2. **Muốn biết reader/processor/writer có phối hợp đúng?** Chạy step thật với fixture và `JobRepository`; dùng step integration test.
3. **Muốn biết các step có liên kết/điều hướng đúng?** Chạy job thật và assert trạng thái, flow, output; dùng job integration test.
4. **Muốn biết tính năng phụ thuộc database hoặc hệ thống ngoài có hoạt động như môi trường triển khai?** Dùng integration test với dịch vụ tương thích, ưu tiên container hoặc môi trường test cô lập.

Với CI, chạy unit test thường xuyên vì nhanh; chạy batch integration test ở các bước phù hợp với dự án và khả năng cung cấp môi trường. Điều quan trọng là đảm bảo fixture, output và metadata độc lập, để một test thất bại vì hành vi bị lỗi chứ không vì test khác đã để lại trạng thái.

## 12. Kết luận về ranh giới kiểm thử

Unit test xác nhận **một thành phần thực hiện đúng trách nhiệm của nó**. Batch integration test xác nhận **các thành phần và hạ tầng Spring Batch phối hợp đúng trong lần thực thi thật của step hoặc job**. Việc kết hợp cả hai cho phản hồi nhanh về logic, đồng thời phát hiện được lỗi cấu hình, transaction, job metadata, resource scope và tác dụng phụ mà unit test không thể bao phủ.

## Tài liệu tham khảo

- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): công cụ kiểm thử job/step, scope và kỹ thuật kiểm thử component của Spring Batch.
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/docs/5.2.x/reference/testing.html): cách dùng `JobLauncherTestUtils` trên Spring Batch 5.x.
- [Spring Framework Reference — Testing](https://docs.spring.io/spring-framework/reference/testing.html): Spring TestContext, JUnit Jupiter và môi trường integration test.
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): cơ chế Spring Boot Test và quản lý context trong test.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): cách viết và tổ chức unit/integration test với JUnit Jupiter.
