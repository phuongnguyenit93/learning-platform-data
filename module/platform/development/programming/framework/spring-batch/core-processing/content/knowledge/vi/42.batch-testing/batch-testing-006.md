# Kiểm thử step riêng trong Spring Batch

Trong một batch job có nhiều bước, đôi khi cần xác nhận một bước xử lý dữ liệu chính xác mà không phải chạy toàn bộ job. **Kiểm thử step riêng** (testing individual steps) cho phép chuẩn bị đầu vào chỉ cho step cần kiểm tra, chạy step đó trong hạ tầng Spring Batch và đối chiếu trạng thái thực thi, dữ liệu đầu ra cũng như các tác dụng phụ. Đây là một kỹ thuật quan trọng của chủ đề **Testing batch** trong Spring Batch Core Processing.

Ví dụ, job nhập đơn hàng có ba step:

```text
importOrdersJob
    ├── downloadFileStep
    ├── validateOrdersStep       ← step đang cần kiểm thử
    └── persistOrdersStep
```

Khi kiểm thử `validateOrdersStep`, ta không muốn mỗi lần chạy test đều tải tệp từ một máy chủ bên ngoài hoặc ghi dữ liệu thật vào kho lưu trữ. Thay vào đó, ta cung cấp dữ liệu và ngữ cảnh cần thiết cho `validateOrdersStep`, chạy riêng step này rồi kiểm tra kết quả. **Kiểm thử một step không có nghĩa là bỏ qua các phụ thuộc của step**: nếu step cần cơ sở dữ liệu, transaction, `JobParameters` hay `ExecutionContext`, test vẫn phải tạo ra các phụ thuộc đó theo cách có thể kiểm soát.

## 1. Phân biệt các mức độ kiểm thử

| Mức kiểm thử | Đối tượng được chạy | Khi nên dùng | Điều cần khẳng định |
| --- | --- | --- | --- |
| Unit test | `ItemProcessor`, `Tasklet`, validator hoặc service thông thường | Kiểm tra nhanh quy tắc nghiệp vụ và các trường hợp biên | Giá trị trả về, ngoại lệ, tương tác với dependency |
| Kiểm thử component có scope | Một bean `@StepScope` hoặc `@JobScope` | Xác nhận late binding từ parameters/context | Giá trị được inject, hành vi bên trong scope |
| **Integration test một step** | Một `Step` thực sự cùng `JobRepository` và transaction | Kiểm tra reader → processor → writer, trạng thái, skip/retry, ghi dữ liệu | `StepExecution`, dữ liệu đã commit, lỗi và số lượng bản ghi |
| Integration test cả job | Toàn bộ luồng `Job` | Kiểm tra thứ tự step, flow, transition, chia sẻ context giữa các step | `JobExecution`, end-to-end output, hành vi của cả workflow |

Nếu chỉ muốn thử quy tắc chuẩn hóa mã đơn hàng, gọi thẳng `ItemProcessor.process()` là đủ. Nếu muốn chắc rằng step đọc đúng 10 bản ghi, lọc 2 bản ghi, ghi 8 bản ghi và commit đúng, cần chạy chính `Step` bằng công cụ test của Spring Batch. Hai kiểu kiểm thử bổ sung cho nhau.

## 2. Công cụ kiểm thử step

Thư viện `spring-batch-test` cung cấp các thành phần chính:

- `@SpringBatchTest`: tích hợp công cụ test Spring Batch vào Spring TestContext; đồng thời đăng ký listener hỗ trợ step/job scope.
- `JobLauncherTestUtils` trong **Spring Batch 5.x**: phương thức `launchStep(...)` chạy một step theo tên, bằng một job bao bọc chỉ chứa step đó.
- `JobOperatorTestUtils` trong **Spring Batch 6.x**: phương thức `startStep(...)` đảm nhiệm vai trò tương ứng. Trong 6.x, `JobLauncherTestUtils` đã bị deprecated.
- `JobRepositoryTestUtils`: hỗ trợ chuẩn bị hoặc dọn dữ liệu metadata của job execution trong kho lưu trữ phục vụ test.
- `MetaDataInstanceFactory`, `StepScopeTestUtils` và `StepScopeTestExecutionListener`: tạo `StepExecution` giả lập và kích hoạt step scope khi test component độc lập.

Hai điểm cần hiểu rõ:

1. `launchStep()`/`startStep()` **chạy một step qua cơ chế thực thi Spring Batch**, không chỉ gọi trực tiếp một hàm Java. Vì vậy step vẫn có trạng thái thực thi, transaction và metadata tại `JobRepository`.
2. Chúng thường sử dụng **job bao bọc chỉ có một step** cho lần thử nghiệm. Các step đứng trước hoặc sau trong job thật sẽ không tự chạy. Không nên dùng kết quả của kiểm thử step để khẳng định logic flow của cả job đã đúng.

### 2.1. Khai báo dependency

Ví dụ sau sử dụng **Spring Boot 3.x + Spring Batch 5.x + JUnit Jupiter**. Trong Gradle, project cần các dependency tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-test` cung cấp JUnit 5 và AssertJ; `spring-batch-test` cung cấp utility kiểm thử; H2 là database thử nghiệm lưu bảng metadata `BATCH_*`. Với project đã có database kiểm thử phù hợp, không bắt buộc dùng H2. Nên để Spring Boot quản lý các phiên bản dependency thống nhất qua BOM.

## 3. Ví dụ hoàn chỉnh: chạy riêng một `TaskletStep`

Giả sử `importOrdersJob` có hai bước:

1. `prepareInputStep`: chuẩn bị đầu vào.
2. `validateBusinessDateStep`: đọc tham số `businessDate`, kiểm tra không rỗng và lưu ngày hợp lệ vào `StepExecutionContext`.

Test cần bảo đảm `validateBusinessDateStep` chạy thành công khi ngày hợp lệ, thất bại khi ngày trống và **không gọi** `prepareInputStep`.

Đặt class dưới đây trong `src/test/java/.../ValidateBusinessDateStepTest.java` (điều chỉnh `package` theo project). Ví dụ cấu hình test độc lập với những job khác của ứng dụng.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = ValidateBusinessDateStepTest.TestBatchApp.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class ValidateBusinessDateStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void runsOnlyTargetStepWithValidParameter() throws Exception {
        // Arrange: tham số nhận diện lần chạy, không phụ thuộc step trước.
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-16")
            .addLong("testCaseId", 1L)
            .toJobParameters();

        // Act: chỉ chạy step được gọi tên.
        JobExecution jobExecution = jobLauncherTestUtils.launchStep(
            "validateBusinessDateStep", parameters
        );

        // Assert: trạng thái + kết quả nghiệp vụ + tính độc lập.
        assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(jobExecution.getStepExecutions()).hasSize(1);

        StepExecution stepExecution = onlyStep(jobExecution);
        assertThat(stepExecution.getStepName())
            .isEqualTo("validateBusinessDateStep");
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(stepExecution.getExitStatus()).isEqualTo(ExitStatus.COMPLETED);
        assertThat(stepExecution.getExecutionContext()
            .getString("validatedBusinessDate"))
            .isEqualTo("2026-11-16");
        assertThat(jobExecution.getExecutionContext()
            .containsKey("preparationDone"))
            .isFalse();
    }

    @Test
    void failsWhenBusinessDateIsBlank() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", " ")
            .addLong("testCaseId", 2L)
            .toJobParameters();

        JobExecution jobExecution = jobLauncherTestUtils.launchStep(
            "validateBusinessDateStep", parameters
        );

        StepExecution stepExecution = onlyStep(jobExecution);
        assertThat(jobExecution.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(stepExecution.getFailureExceptions()).isNotEmpty();
        assertThat(stepExecution.getExecutionContext()
            .containsKey("validatedBusinessDate"))
            .isFalse();
    }

    private static StepExecution onlyStep(JobExecution execution) {
        return execution.getStepExecutions().iterator().next();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestBatchApp {

        @Bean
        Job importOrdersJob(
                JobRepository repository,
                @Qualifier("prepareInputStep") Step prepareInputStep,
                @Qualifier("validateBusinessDateStep") Step validateStep) {
            return new JobBuilder("importOrdersJob", repository)
                .start(prepareInputStep)
                .next(validateStep)
                .build();
        }

        @Bean
        Step prepareInputStep(JobRepository repository,
                              PlatformTransactionManager txManager) {
            return new StepBuilder("prepareInputStep", repository)
                .tasklet((contribution, chunkContext) -> {
                    contribution.getStepExecution().getJobExecution()
                        .getExecutionContext().putString("preparationDone", "yes");
                    return RepeatStatus.FINISHED;
                }, txManager)
                .build();
        }

        @Bean
        Step validateBusinessDateStep(JobRepository repository,
                                      PlatformTransactionManager txManager,
                                      Tasklet validateBusinessDateTasklet) {
            return new StepBuilder("validateBusinessDateStep", repository)
                .tasklet(validateBusinessDateTasklet, txManager)
                .build();
        }

        @Bean
        Tasklet validateBusinessDateTasklet() {
            return (contribution, chunkContext) -> {
                StepExecution stepExecution = contribution.getStepExecution();
                String date = stepExecution.getJobParameters()
                    .getString("businessDate");

                if (date == null || date.isBlank()) {
                    throw new IllegalArgumentException("businessDate is required");
                }

                stepExecution.getExecutionContext()
                    .putString("validatedBusinessDate", date);
                return RepeatStatus.FINISHED;
            };
        }
    }
}
```

**Giải thích từng phần quan trọng:**

- `@SpringBatchTest` cung cấp `JobLauncherTestUtils`. `@SpringBootTest` khởi tạo các bean và hạ tầng Spring Batch; `spring.batch.job.enabled=false` ngăn Boot tự khởi chạy job khi context được tạo.
- `spring.batch.jdbc.initialize-schema=always` giúp khởi tạo metadata `BATCH_*` trong database test. Với database chia sẻ hoặc schema được quản lý riêng, cần cấu hình initialization phù hợp thay vì tùy ý khởi tạo lại.
- `JobBuilder` và `StepBuilder` dùng trực tiếp `JobRepository`, tương thích cách cấu hình từ Spring Batch 5. Không cần `JobBuilderFactory`/`StepBuilderFactory` của các bài viết cũ.
- Dù `importOrdersJob` khai báo `prepareInputStep` đứng trước, lần gọi `launchStep("validateBusinessDateStep", ...)` chỉ sinh một `StepExecution` tương ứng với step cần kiểm tra.
- Tham số `businessDate` đi qua `JobParameters`; kết quả nghiệp vụ được ghi vào **step execution context**. Đây là hai dữ liệu khác nhau: parameters đại diện đầu vào bất biến của job execution, context chứa trạng thái có thể cập nhật trong lúc thực thi.
- Trường hợp lỗi xác nhận cả trạng thái `FAILED` và danh sách exception. Một exception phát sinh bên trong tasklet thường được Spring Batch ghi nhận trong `StepExecution`; test không nên mặc định rằng phương thức `launchStep()` sẽ ném chính exception đó ra ngoài.

Ví dụ trên cố ý chỉ có hai test với `testCaseId` khác nhau để hai lần chạy tạo những `JobInstance` riêng. Nếu chạy lại cùng tên job với cùng *identifying JobParameters* trên một `JobRepository` vẫn giữ metadata, có thể gặp `JobInstanceAlreadyCompleteException` thay vì kiểm thử lại nghiệp vụ.

## 4. Tương đương trong Spring Batch 6.x

Spring Batch 6 chuyển sang `JobOperatorTestUtils`. Trong test tương ứng, thay field và lệnh gọi của ví dụ Spring Batch 5 bằng:

```java
import org.springframework.batch.core.repository.ExecutionContext;
import org.springframework.batch.test.JobOperatorTestUtils;

@Autowired
private JobOperatorTestUtils jobOperatorTestUtils;

// Bên trong test:
JobExecution result = jobOperatorTestUtils.startStep(
    "validateBusinessDateStep",
    parameters,
    new ExecutionContext()
);
```

Ở ví dụ này, `ExecutionContext` thứ ba là **job execution context ban đầu** cho job bao bọc. Đây không phải `StepExecutionContext`. Spring Batch 6 cũng tổ chức lại một số package của các kiểu core, nên phải dùng import theo đúng phiên bản dependency thực tế. Ví dụ: `JobExecution` nằm trong `org.springframework.batch.core.job`, `StepExecution` trong `org.springframework.batch.core.step`, và `JobParameters` trong `org.springframework.batch.core.job.parameters` ở 6.x. Không trộn import của 5.x với dependency 6.x.

Phương thức mới không thay đổi ý nghĩa kiểm thử: chuẩn bị tham số và context, khởi chạy một step, sau đó đọc `JobExecution`/`StepExecution` để đối chiếu. Đối với Spring Batch 6, tránh tiếp tục viết code mới dựa vào `JobLauncherTestUtils` đã deprecated.

## 5. Kiểm thử một step sử dụng `JobParameters` và `ExecutionContext`

Một step thường phụ thuộc dữ liệu được tạo ở bước trước:

```text
prepareFileStep
    └── jobExecutionContext["inputPath"] = "/tmp/orders.csv"
              ↓
parseFileStep
    └── reader sử dụng inputPath
```

Khi chạy riêng `parseFileStep`, `prepareFileStep` không hoạt động, vì vậy test phải cung cấp `inputPath` từ đầu. Với Spring Batch 5:

```java
JobParameters params = new JobParametersBuilder()
    .addLong("testCaseId", 100L)
    .toJobParameters();

ExecutionContext initialJobContext = new ExecutionContext();
initialJobContext.putString("inputPath", "src/test/resources/orders.csv");

JobExecution result = jobLauncherTestUtils.launchStep(
    "parseFileStep", params, initialJobContext
);
```

Trong Spring Batch 6, đổi lệnh cuối thành `jobOperatorTestUtils.startStep("parseFileStep", params, initialJobContext)`.

Cần phân biệt ba vùng dữ liệu:

| Dữ liệu | Vòng đời và phạm vi | Cách truyền trong test |
| --- | --- | --- |
| `JobParameters` | Các tham số đầu vào của lần chạy job; tham số identifying góp phần tạo danh tính `JobInstance` | `launchStep(name, params, ...)` hoặc `startStep(name, params, ...)` |
| `JobExecutionContext` | Trạng thái chia sẻ giữa các step thuộc một job execution | Tham số `ExecutionContext` thứ ba khi chạy riêng step |
| `StepExecutionContext` | Trạng thái riêng của một step execution | Do step tạo/cập nhật; kiểm tra từ `stepExecution.getExecutionContext()`; cần khởi tạo riêng khi kiểm thử component scope |

Nếu `parseFileStep` dùng `@Value("#{jobExecutionContext['inputPath']}")` trong một bean `@StepScope`, giá trị được lấy từ job context cung cấp cho lần chạy. Nếu step cần thông tin nằm trong step context từ một lần **restart**, test phải chuẩn bị metadata/context tương ứng qua fixture hoặc `JobRepository` thay vì nhầm job context với step context.

## 6. Kiểm thử riêng bean `@StepScope`

Một `ItemReader`, `ItemProcessor`, `ItemWriter` hoặc service được đánh dấu `@StepScope` chỉ được khởi tạo đúng khi có `StepContext` đang hoạt động. Gọi bean từ unit test thuần Java hoặc Spring test mà không kích hoạt scope có thể gây lỗi vì không có step execution hiện hành.

Ví dụ component nhận giá trị động:

```java
@Component
@StepScope
public class InputFileNameProvider {
    private final String fileName;

    public InputFileNameProvider(
            @Value("#{stepExecutionContext['fileName']}") String fileName) {
        this.fileName = fileName;
    }

    public String getFileName() {
        return fileName;
    }
}
```

Nếu test đã có Spring context chứa bean `InputFileNameProvider`, có thể dùng `StepScopeTestUtils` để giả lập một lần thực thi:

```java
@Autowired
InputFileNameProvider inputFileNameProvider;

@Test
void resolvesFileNameFromStepContext() throws Exception {
    StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
    stepExecution.getExecutionContext().putString("fileName", "orders.csv");

    String actual = StepScopeTestUtils.doInStepScope(
        stepExecution,
        inputFileNameProvider::getFileName
    );

    assertThat(actual).isEqualTo("orders.csv");
}
```

Các import liên quan ở Spring Batch 5 là `org.springframework.batch.test.MetaDataInstanceFactory`, `org.springframework.batch.test.StepScopeTestUtils` và `org.springframework.batch.core.StepExecution`. `@SpringBatchTest` cũng kích hoạt `StepScopeTestExecutionListener`; khi dùng listener này, test có thể cung cấp method `getStepExecution()` để tùy biến step context. Với một thao tác ngắn và rõ ràng, `doInStepScope(...)` giúp giới hạn chính xác thời điểm scope hoạt động.

Lưu ý đây là **kiểm thử một component có step scope**, chưa phải integration test của toàn `Step`. Nó giúp tìm lỗi cấu hình late binding trước khi chạy reader/processor/writer cùng nhau.

## 7. Kiểm thử `chunk-oriented Step`

Đối với step xử lý theo chunk, ví dụ:

```text
ItemReader<String>
    → ItemProcessor<String, Order>
    → ItemWriter<Order>
    → commit theo kích thước chunk
```

Test cần chuẩn bị một tập đầu vào nhỏ nhưng đủ phân biệt các trường hợp. Chẳng hạn dữ liệu giả lập gồm sáu dòng: bốn dòng hợp lệ, một dòng cần lọc và một dòng bị bỏ qua do lỗi nghiệp vụ đã được cấu hình `skip`.

Sau khi chạy step, kiểm tra đồng thời hai loại kết quả:

**Metadata của `StepExecution`:**

```java
StepExecution stepExecution = jobExecution.getStepExecutions()
    .stream()
    .filter(s -> s.getStepName().equals("importOrdersStep"))
    .findFirst()
    .orElseThrow();

assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(stepExecution.getReadCount()).isEqualTo(6);
assertThat(stepExecution.getFilterCount()).isEqualTo(1);
assertThat(stepExecution.getProcessSkipCount()).isEqualTo(1);
assertThat(stepExecution.getWriteCount()).isEqualTo(4);
```

Các con số trên **chỉ đúng với fixture mô tả và cấu hình xử lý tương ứng**: reader phải đọc thành công sáu dòng; processor trả `null` với dòng cần lọc; lỗi nghiệp vụ ở processor phải nằm trong chính sách `skip`; writer ghi bốn item còn lại. Nếu lỗi phát sinh trong reader hoặc writer thì cần kiểm tra `readSkipCount` hoặc `writeSkipCount` thay cho `processSkipCount`.

**Tác dụng phụ thực tế:**

```java
List<OrderEntity> rows = orderRepository.findAll();
assertThat(rows).hasSize(4);
assertThat(rows).extracting(OrderEntity::getOrderCode)
    .containsExactlyInAnyOrder("A001", "A002", "A003", "A004");
```

Đoạn thứ hai minh họa một test sử dụng repository của ứng dụng; `OrderEntity` và `orderRepository` cần được thay bằng model và repository thực tế của project. Không chỉ dựa vào `BatchStatus.COMPLETED`: step có thể báo hoàn tất nhưng ghi sai bản ghi, sai thứ tự hoặc ghi trùng dữ liệu.

Khi step dùng `faultTolerant()`, nên tách test theo tình huống:

- **Filter:** processor trả `null` để loại bỏ item; kiểm tra `filterCount`, không nhầm với skip do exception.
- **Skip:** reader/processor/writer ném exception thuộc chính sách `skip`; kiểm tra step tiếp tục và các bộ đếm skip đúng loại.
- **Retry:** dependency giả lập thất bại tạm thời rồi thành công; kiểm tra số lần gọi và kết quả cuối. Không mặc định `rollbackCount` phải bằng một hằng số nếu cấu hình transaction hoặc reader làm thay đổi hành vi rollback.
- **Skip/retry vượt giới hạn:** step chuyển `FAILED`; kiểm tra exception, số item đã commit và dữ liệu không được commit của transaction thất bại.

Đặc biệt, với chunk transaction, một lần rollback có thể dẫn tới xử lý lại item. Vì thế cần xác định writer hoặc lời gọi ngoài hệ thống có an toàn khi thử lại hay không; test nên kiểm tra dữ liệu cuối cùng chứ không chỉ số lần một method đã được gọi.

## 8. Chuẩn bị fixture và giữ test độc lập

Một phép thử step thường đi theo chuỗi **Arrange → Act → Assert → Cleanup**:

1. **Arrange:** tạo vài bản ghi test/fixture file, thiết lập `JobParameters`, job context và trạng thái ban đầu của database.
2. **Act:** chạy đúng tên step, bằng `launchStep` ở 5.x hoặc `startStep` ở 6.x.
3. **Assert:** kiểm tra `BatchStatus`, `ExitStatus`, bộ đếm, exception, `ExecutionContext` và dữ liệu đầu ra.
4. **Cleanup:** xóa dữ liệu thử nghiệm, đóng tài nguyên và dọn metadata nếu test dùng chung repository với các lần chạy khác.

Một số nguyên tắc giúp test lặp lại ổn định:

- **Dùng dữ liệu nhỏ, biết trước đầu ra.** File ở `src/test/resources`, database thử nghiệm tách biệt hoặc Testcontainers phù hợp với thao tác SQL thực tế. Không dựa vào API bên ngoài nếu mục tiêu là kiểm thử logic trong step.
- **Mỗi lần chạy có danh tính rõ ràng.** Đừng lặp lại identifying `JobParameters` trên một repository đã ghi nhận job hoàn tất nếu không chủ đích kiểm thử restart. Có thể thêm `testCaseId` hoặc dọn metadata trong test database.
- **Không chia sẻ mutable state giữa các test.** Reader có con trỏ, writer có buffer, static list hoặc singleton giả lập có thể làm test phụ thuộc thứ tự chạy. Reset dữ liệu đầu vào và dependency cho mỗi case.
- **Dọn metadata có chủ đích.** `JobRepositoryTestUtils.removeJobExecutions()` chỉ phù hợp khi repository thuộc phạm vi test và có thể xóa an toàn; không chạy trên dữ liệu của ứng dụng thật.
- **Hạn chế `@Transactional` bao quanh test step.** Spring Batch tự quản lý transaction cho step/chunk; transaction của method test có thể làm thay đổi khả năng nhìn thấy dữ liệu hoặc khiến rollback ở cuối test tạo cảm giác sai về dữ liệu đã commit.
- **Kiểm thử resource lifecycle.** Với `ItemStreamReader`/`ItemStreamWriter` khi test trực tiếp, cần `open(ExecutionContext)`, `update(...)` khi cần, và `close()` đúng lúc. Khi chạy toàn `Step`, framework thực hiện lifecycle này.

## 9. Những lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy step theo tên | Tên bean/`Step` khác tên truyền vào, step không nằm trong job được chọn | Kiểm tra tên step trong `StepBuilder`, cấu hình job và utility đã chọn đúng job |
| `JobLauncherTestUtils`/`JobOperatorTestUtils` không được inject | Thiếu `spring-batch-test`, thiếu `@SpringBatchTest`, hoặc dùng API sai phiên bản | Thêm dependency, annotation và class utility tương ứng với Spring Batch 5/6 |
| `JobInstanceAlreadyCompleteException` | Chạy lại cùng job name và identifying parameters trên repository còn metadata | Sử dụng parameters khác hoặc dọn repository test trước lần chạy |
| Thiếu bảng `BATCH_JOB_INSTANCE`, `BATCH_STEP_EXECUTION` | Chưa khởi tạo schema metadata | Khởi tạo schema cho database test; kiểm tra cấu hình datasource và batch JDBC |
| `ScopeNotActiveException` khi truy cập bean `@StepScope` | Chưa có step context hoạt động | Chạy component trong `StepScopeTestUtils` hoặc test listener phù hợp |
| Step báo `COMPLETED` nhưng dữ liệu sai | Chỉ kiểm tra status, chưa xác nhận output | Assert dữ liệu database/file/message và bộ đếm trên `StepExecution` |
| Test step riêng thiếu giá trị do step trước tạo ra | Chạy step độc lập không tự chạy các step upstream | Chuẩn bị fixture và `JobExecutionContext`/metadata cần thiết trước khi chạy |
| Test không ổn định khi chạy song song | Dùng chung metadata, file đầu ra hoặc mutable bean | Tách database/schema/resource theo test và tránh chia sẻ trạng thái |

## 10. Khi nào cần bổ sung kiểm thử cả job?

Kiểm thử step riêng trả lời câu hỏi: *“Với dữ liệu, tham số và context đã chuẩn bị, step này có thực thi đúng không?”* Nó không chứng minh được rằng:

- Step trước thực sự ghi đúng giá trị vào context để step sau đọc.
- Các nhánh điều kiện của job (`COMPLETED`, `FAILED`, `STOPPED`, custom exit code) chuyển đúng step tiếp theo.
- Cả job xử lý chính xác khi phải restart sau khi đã hoàn thành một số step.
- Listener hoặc logic chỉ gắn ở cấp job hoạt động đúng khi chạy luồng đầy đủ.

Vì vậy, nên kết hợp unit test cho logic khó, integration test riêng từng step cho các case dữ liệu và một số integration test chạy toàn job cho các luồng quan trọng. Cách kết hợp này tạo phản hồi nhanh khi một step thay đổi, đồng thời vẫn kiểm tra được các phụ thuộc giữa các step.

## Tài liệu tham khảo

- [Spring Batch 5.x Reference — Testing Individual Steps](https://docs.spring.io/spring-batch/docs/5.2.x/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils.launchStep` và step scope testing.
- [Spring Batch 6.x Reference — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): `JobOperatorTestUtils`, `@SpringBatchTest` và các utility test hiện hành.
- [Spring Batch 6.x API — JobOperatorTestUtils](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobOperatorTestUtils.html): chữ ký `startStep` và cách cung cấp `JobParameters`/`ExecutionContext`.
