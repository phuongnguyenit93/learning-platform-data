# Assert `ExecutionContext` khi kiểm thử Spring Batch

## 1. Mục tiêu bài học

Khi kiểm thử một batch job, việc thấy `JobExecution` hoặc `StepExecution` có trạng thái `COMPLETED` chưa đủ để kết luận dữ liệu trạng thái được lưu đúng. Một step có thể xử lý thành công nhưng ghi sai checkpoint, lưu nhầm vào job context hoặc không chuyển kết quả sang step kế tiếp. Những lỗi này thường chỉ lộ ra khi job phải chạy lại sau sự cố.

**Assert `ExecutionContext`** là viết các phép kiểm tra khẳng định rằng trạng thái thực thi được tạo, cập nhật, truyền tiếp và khôi phục theo đúng hợp đồng của batch job. Sau bài này, bạn có thể:

- Phân biệt `JobExecution.getExecutionContext()` với `StepExecution.getExecutionContext()` và chọn đúng đối tượng để assert.
- Kiểm tra sự tồn tại, kiểu dữ liệu, giá trị, điều kiện vắng mặt và sự thay đổi của các key.
- Kiểm thử độc lập một thành phần dùng `ExecutionContext`, kể cả `ItemStream.open/update`.
- Chạy job/step thực bằng `spring-batch-test`, assert context sau thực thi và đọc lại dữ liệu từ repository.
- Kiểm tra việc chuyển dữ liệu từ step context sang job context, cũng như checkpoint khi restart.
- Tránh những phép assert chỉ đúng trên object trong bộ nhớ nhưng không chứng minh được trạng thái đã được lưu bền vững.

Các ví dụ đầy đủ bên dưới sử dụng **Java 17+, JUnit Jupiter, Spring Boot 3.x và Spring Batch 5.x**. Ở cuối bài có ghi chú khi chuyển lên Spring Batch 6.

## 2. `ExecutionContext` là gì và assert ở đâu?

`org.springframework.batch.item.ExecutionContext` là một kho dữ liệu dạng key–value mà Spring Batch dùng để lưu trạng thái cần thiết cho một lần thực thi và cho khả năng restart. Giá trị có thể được đọc bằng API có kiểu như `getString`, `getInt`, `getLong`, hoặc API tổng quát `get`. Khi lưu vào metadata repository, các giá trị phải phù hợp với cơ chế serialization đang cấu hình.

Một `JobExecution` và mỗi `StepExecution` có **`ExecutionContext` riêng**:

| Đối tượng cần kiểm tra | Cách truy cập | Vòng đời / thời điểm lưu | Ví dụ key |
| --- | --- | --- | --- |
| Step context | `stepExecution.getExecutionContext()` | Gắn với một lần chạy step; thường được đồng bộ vào repository tại các checkpoint/commit của chunk và khi step kết thúc | `reader.offset`, `page.number`, `processed.count` |
| Job context | `jobExecution.getExecutionContext()` | Gắn với một lần chạy job, được duy trì xuyên các step; thường được lưu tại ranh giới các step | `source.file`, `import.total` |
| Job parameters | `jobExecution.getJobParameters()` | Đầu vào định danh/điều khiển job; **không phải** `ExecutionContext` | `businessDate`, `inputPath` |

Ví dụ, step `readCustomers` đọc được 120 bản ghi và ghi:

```java
stepExecution.getExecutionContext().putLong("reader.offset", 120L);
```

Lúc này, phép assert phải đọc **step context**:

```java
assertEquals(
    120L,
    stepExecution.getExecutionContext().getLong("reader.offset")
);
```

Không thể suy ra job context cũng có `reader.offset`. Nếu step sau cần dữ liệu này, ứng dụng phải chủ động sao chép hoặc sử dụng `ExecutionContextPromotionListener` để chuyển key từ step context sang job context sau khi step hoàn tất.

### 2.1. Đừng nhầm trạng thái nghiệp vụ với trạng thái framework

Spring Batch cũng có các metadata như `BatchStatus`, `ExitStatus`, `readCount`, `writeCount`, `commitCount` và `rollbackCount`. Chúng có ích cho test nhưng không thay thế phép assert business key trong `ExecutionContext`.

Một test tốt thường trả lời đồng thời ba câu hỏi:

1. **Batch có chạy đến điểm mong đợi không?** Ví dụ `BatchStatus.COMPLETED`.
2. **Dữ liệu trạng thái có đúng không?** Ví dụ `processed.count = 120` và `reader.offset = 120`.
3. **Giá trị có ở đúng phạm vi và được lưu đúng thời điểm không?** Ví dụ `import.total` xuất hiện trong job context sau step thành công, còn checkpoint vẫn nằm trong step context.

## 3. Chọn hợp đồng assert trước khi viết test

Giả sử có job nhập dữ liệu khách hàng:

```text
customerImportJob
    |
    +-- readCustomersStep
    |      step context:
    |        reader.offset = 120
    |        processed.count = 120
    |        source.file = "customers-2026.csv"
    |
    +-- createReportStep
           đọc job context:
             import.total = 120
```

Hợp đồng có thể được diễn đạt thành bảng sau:

| Thời điểm | Phạm vi | Điều kiện cần assert |
| --- | --- | --- |
| Trước khi chạy | Step | `reader.offset` chưa có, hoặc có giá trị checkpoint được khôi phục |
| Sau khi đọc 120 dòng | Step | `reader.offset == 120L` và `processed.count == 120L` |
| Sau `readCustomersStep` thành công | Job | `import.total == 120L` nếu có cấu hình promotion |
| Khi step thất bại trước khi promotion | Job | `import.total` không được quảng bá ngoài chính sách đã cấu hình |
| Trước khi đọc tiếp trong lần restart | Step | Reader nhận checkpoint đã commit từ lần chạy trước |
| Sau khi đọc lại từ repository | Step/Job | Các key cần bền vững còn nguyên giá trị và kiểu |

Cách chọn key nên có ý nghĩa ổn định: dùng `reader.offset`, `import.total`, `source.file` thay cho `x`, `value1`. Tránh assert mọi entry trong context nếu framework hoặc component khác có thể thêm metadata hợp lệ.

## 4. Assert cơ bản bằng JUnit 5

`ExecutionContext` hỗ trợ `containsKey`, `getString`, `getInt`, `getLong`, `getDouble`, `get` và các phiên bản getter có default. `putString`, `putInt` và `putLong` giúp thể hiện rõ kiểu dữ liệu dự kiến.

Ví dụ một phép kiểm tra nhiều điều kiện cùng lúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

import static org.junit.jupiter.api.Assertions.*;

class ExecutionContextAssertionsTest {

    @Test
    void assertsValuesAndMissingKeys() {
        ExecutionContext context = new ExecutionContext();
        context.putString("source.file", "customers.csv");
        context.putLong("reader.offset", 120L);
        context.putInt("retry.count", 2);

        assertAll("batch checkpoint",
            () -> assertTrue(context.containsKey("source.file")),
            () -> assertEquals("customers.csv", context.getString("source.file")),
            () -> assertEquals(120L, context.getLong("reader.offset")),
            () -> assertEquals(2, context.getInt("retry.count")),
            () -> assertFalse(context.containsKey("fatal.error")),
            () -> assertEquals(0, context.getInt("missing.count", 0))
        );
    }

    @Test
    void nullRemovesTheKey() {
        ExecutionContext context = new ExecutionContext();
        context.putString("temporary.marker", "PENDING");
        context.put("temporary.marker", null);

        assertFalse(context.containsKey("temporary.marker"));
    }
}
```

**Ý nghĩa từng cách assert:**

- `containsKey("k")` kiểm tra key có tồn tại, kể cả khi giá trị được đọc có thể bằng giá trị mặc định.
- `getLong("k")` kiểm tra giá trị đúng kiểu `Long`; không nên so số bằng cách chuyển thành chuỗi.
- `getInt("k", 0)` phù hợp khi hợp đồng cho phép key chưa tồn tại và coi đó là 0.
- `assertFalse(context.containsKey("secret"))` thể hiện một bất biến: key nhạy cảm hoặc marker tạm không được giữ lại.
- `assertAll` giúp xem các lỗi assertion liên quan cùng một trạng thái trong một lần chạy test.

Đừng dùng default getter để che một key **bắt buộc**. Với `reader.offset` phải tồn tại, hãy assert cả `containsKey` rồi mới assert giá trị. Nếu key không tồn tại, `getLong("reader.offset", 0L)` có thể khiến test pass sai khi giá trị mong đợi cũng bằng 0.

### 4.1. `isDirty()` kiểm tra điều gì?

`ExecutionContext` có dirty flag dùng để ghi nhận thay đổi map:

```java
ExecutionContext context = new ExecutionContext();

assertFalse(context.isDirty());

context.putLong("reader.offset", 5L);
assertTrue(context.isDirty());

context.clearDirtyFlag();
assertFalse(context.isDirty());
```

Điều này chỉ chứng minh object đã được thay đổi kể từ lần clear flag; **không chứng minh** transaction đã commit hoặc repository đã lưu thành công. Vì vậy, `isDirty()` hữu ích khi test logic thay đổi context, nhưng phải có test integration riêng nếu yêu cầu là persistence.

## 5. Unit test thành phần ghi vào Step `ExecutionContext`

Khi logic thuộc một class nhỏ, có thể test nhanh mà không cần khởi động toàn bộ Spring context. `MetaDataInstanceFactory` trong module `spring-batch-test` tạo sẵn `StepExecution` và `JobExecution` giả lập metadata.

Ví dụ một class ghi tiến độ sau khi xử lý nhóm bản ghi:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;

public class ImportProgressRecorder {

    public void record(StepExecution stepExecution,
                       long lastCustomerId,
                       int successfulRecords) {
        ExecutionContext context = stepExecution.getExecutionContext();
        context.putLong("customer.lastId", lastCustomerId);
        context.putInt("customer.successCount", successfulRecords);
        context.putString("customer.phase", "PROCESSED");
    }
}
```

Test đặt kỳ vọng lên **StepExecution do logic thật cập nhật**:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.junit.jupiter.api.Assertions.*;

class ImportProgressRecorderTest {

    private final ImportProgressRecorder recorder =
        new ImportProgressRecorder();

    @Test
    void writesExpectedCheckpointIntoStepContext() {
        StepExecution stepExecution =
            MetaDataInstanceFactory.createStepExecution();

        recorder.record(stepExecution, 1088L, 35);

        ExecutionContext actual = stepExecution.getExecutionContext();

        assertAll("recorded progress",
            () -> assertTrue(actual.containsKey("customer.lastId")),
            () -> assertEquals(1088L, actual.getLong("customer.lastId")),
            () -> assertEquals(35, actual.getInt("customer.successCount")),
            () -> assertEquals("PROCESSED", actual.getString("customer.phase"))
        );

        assertFalse(stepExecution.getJobExecution()
                                 .getExecutionContext()
                                 .containsKey("customer.lastId"));
    }
}
```

Phép assert cuối đặc biệt có ý nghĩa: nó xác nhận recorder chỉ ghi vào step context như thiết kế, không vô tình làm rò trạng thái checkpoint sang job context.

**Giới hạn của ví dụ:** `MetaDataInstanceFactory` không tạo việc commit chunk hay lưu database. Test này xác nhận *logic ghi giá trị*, còn độ bền của checkpoint cần test chạy step/job thực với `JobRepository`.

## 6. Assert checkpoint của `ItemStream.open()` và `update()`

Đối với reader/writer có trạng thái, Spring Batch gọi `ItemStream.open(executionContext)` khi khởi tạo và `ItemStream.update(executionContext)` tại checkpoint. Một lỗi thường gặp là thành phần ghi đúng offset ở `update` nhưng không đọc offset đó khi `open` ở lần chạy sau.

Ví dụ thành phần minh họa quản lý offset:

```java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStream;

public class OffsetTracker implements ItemStream {

    private long currentOffset;

    @Override
    public void open(ExecutionContext context) {
        currentOffset = context.getLong("reader.offset", 0L);
    }

    public void advance(long recordsProcessed) {
        currentOffset += recordsProcessed;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("reader.offset", currentOffset);
    }

    @Override
    public void close() {
        // Không giữ resource trong ví dụ này.
    }

    public long currentOffset() {
        return currentOffset;
    }
}
```

Test phải kiểm tra cả hai chiều **restore rồi save**:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OffsetTrackerTest {

    @Test
    void restoresAndUpdatesCheckpoint() {
        ExecutionContext previousCheckpoint = new ExecutionContext();
        previousCheckpoint.putLong("reader.offset", 100L);

        OffsetTracker tracker = new OffsetTracker();
        tracker.open(previousCheckpoint);

        assertEquals(100L, tracker.currentOffset());

        tracker.advance(20);
        tracker.update(previousCheckpoint);

        assertEquals(120L, previousCheckpoint.getLong("reader.offset"));

        OffsetTracker restartedTracker = new OffsetTracker();
        restartedTracker.open(new ExecutionContext(previousCheckpoint));

        assertEquals(120L, restartedTracker.currentOffset());
    }
}
```

`new ExecutionContext(previousCheckpoint)` ở đây mô phỏng việc đưa snapshot trạng thái sang instance mới. Đây vẫn là **unit test trong bộ nhớ**. Để chứng minh một restart thật, phải tạo lần chạy thứ hai qua cùng `JobRepository` và sử dụng **cùng JobParameters định danh JobInstance**.

Trong production, `ItemStream` phải được đăng ký với step; nếu một reader/writer có trạng thái bị bọc trong delegate hoặc không được framework quản lý đúng, các callback `open/update` có thể không được gọi như kỳ vọng. Khi đó unit test ở trên vẫn pass nhưng integration test về checkpoint sẽ phát hiện vấn đề.

## 7. Integration test: chạy job và assert Step/Job context

### 7.1. Thư viện và môi trường

Với một dự án Spring Boot 3.x dùng Gradle Groovy DSL, các dependency liên quan thường là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`spring-batch-test` cung cấp `@SpringBatchTest`, `JobLauncherTestUtils`, `MetaDataInstanceFactory` và các tiện ích scope. Trong ví dụ sau, database H2 chỉ dùng cho test; ứng dụng thực tế có thể dùng database khác cho metadata repository.

### 7.2. Ví dụ test có repository thật

Ví dụ này tạo một job nhỏ gồm step ghi `import.total` và `import.phase`. Listener được cấu hình để chỉ promote `import.total` sang job context. Test khẳng định ba mức: kết quả step, kết quả job và dữ liệu được đọc lại qua `JobExplorer`.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = ExecutionContextIntegrationTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:batch_context_test;DB_CLOSE_DELAY=-1"
    }
)
class ExecutionContextIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Test
    void stepValueIsPromotedAndPersisted() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("test.run", UUID.randomUUID().toString())
            .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
            .filter(s -> s.getStepName().equals("importStep"))
            .findFirst()
            .orElseThrow();

        ExecutionContext stepContext = step.getExecutionContext();
        assertEquals(7L, stepContext.getLong("import.total"));
        assertEquals("READY", stepContext.getString("import.phase"));

        ExecutionContext jobContext = execution.getExecutionContext();
        assertEquals(7L, jobContext.getLong("import.total"));
        assertFalse(jobContext.containsKey("import.phase"));

        // Đọc lại từ JobRepository qua một API truy vấn metadata.
        JobExecution restored = jobExplorer.getJobExecution(execution.getId());
        assertNotNull(restored);

        assertEquals(7L,
            restored.getExecutionContext().getLong("import.total"));

        StepExecution persistedStep = restored.getStepExecutions().stream()
            .filter(s -> s.getStepName().equals("importStep"))
            .findFirst()
            .orElseThrow();

        assertEquals(7L,
            persistedStep.getExecutionContext().getLong("import.total"));
        assertEquals("READY",
            persistedStep.getExecutionContext().getString("import.phase"));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(BatchTestConfig.class)
    static class TestApplication {
    }

    @TestConfiguration
    static class BatchTestConfig {

        @Bean
        ExecutionContextPromotionListener importPromotionListener() {
            ExecutionContextPromotionListener listener =
                new ExecutionContextPromotionListener();
            listener.setKeys(new String[] {"import.total"});
            return listener;
        }

        @Bean
        Step importStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                ExecutionContextPromotionListener importPromotionListener) {

            return new StepBuilder("importStep", repository)
                .tasklet((contribution, chunkContext) -> {
                    ExecutionContext context = contribution
                        .getStepExecution()
                        .getExecutionContext();

                    context.putLong("import.total", 7L);
                    context.putString("import.phase", "READY");

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .listener(importPromotionListener)
                .build();
        }

        @Bean
        Job importJob(JobRepository repository, Step importStep) {
            return new JobBuilder("importJob", repository)
                .start(importStep)
                .build();
        }
    }
}
```

**Những điểm quan trọng khi đọc test:**

- `spring.batch.job.enabled=false` ngăn Spring Boot tự chạy job trong lúc khởi tạo test; test chủ động gọi `launchJob`.
- `test.run` có giá trị duy nhất cho mỗi test, tránh đụng `JobInstance` của lần thử trước.
- `@SpringBatchTest` đăng ký các test utility của Spring Batch. Khi context chỉ chứa một bean `Job`, utility có thể được gắn với job đó tự động; nếu có nhiều job, cần gọi `jobLauncherTestUtils.setJob(jobUnderTest)` trước khi launch.
- Hai phép assert trên step context kiểm tra logic ghi dữ liệu; phép assert trên job context kiểm tra **promotion**. `import.phase` không có trong job context vì không nằm trong `setKeys`.
- `jobExplorer.getJobExecution(id)` lấy metadata từ repository. Đọc lại là bằng chứng mạnh hơn việc chỉ kiểm tra cùng `JobExecution` object do `launchJob` trả về.
- Test database cần schema Spring Batch tương ứng với phiên bản thư viện và transaction manager được cấu hình đúng. Đối với ứng dụng dùng database thật, nên chạy integration test trên cùng loại database khi muốn kiểm tra riêng hành vi JDBC/serializer.

### 7.3. Trường hợp chỉ muốn chạy một step

`JobLauncherTestUtils` của Spring Batch 5 cho phép chạy một step cụ thể:

```java
JobExecution execution = jobLauncherTestUtils.launchStep("importStep");

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution step = execution.getStepExecutions().stream()
    .filter(s -> s.getStepName().equals("importStep"))
    .findFirst()
    .orElseThrow();

assertEquals(7L, step.getExecutionContext().getLong("import.total"));
```

`launchStep` chạy step trong một job bao ngoài phục vụ test; nó không thực thi toàn bộ flow của job gốc. Vì vậy, nếu yêu cầu là kiểm tra step kế tiếp có nhận dữ liệu đã promotion hay không, hãy chạy **toàn job** hoặc test rõ đường truyền dữ liệu giữa các step.

## 8. Assert `ExecutionContextPromotionListener`

Khi cần chuyển dữ liệu sang step kế tiếp, `ExecutionContextPromotionListener` sao chép các key được cấu hình từ step context sang job context sau khi step kết thúc. Mặc định listener chỉ promote khi **exit code của step khớp `COMPLETED`**. Điều kiện này dựa trên `ExitStatus`, không chỉ dựa trên việc map có key.

Có thể test trực tiếp listener mà không cần database:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.junit.jupiter.api.Assertions.*;

class PromotionListenerTest {

    private ExecutionContextPromotionListener listener() throws Exception {
        ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
        listener.setKeys(new String[] {"report.total"});
        listener.afterPropertiesSet();
        return listener;
    }

    @Test
    void promotesAfterSuccessfulStep() throws Exception {
        StepExecution step = MetaDataInstanceFactory.createStepExecution();
        step.getExecutionContext().putLong("report.total", 42L);
        step.setExitStatus(ExitStatus.COMPLETED);

        listener().afterStep(step);

        assertEquals(42L,
            step.getJobExecution().getExecutionContext()
                .getLong("report.total"));
    }

    @Test
    void doesNotPromoteAfterFailedStepByDefault() throws Exception {
        StepExecution step = MetaDataInstanceFactory.createStepExecution();
        step.getExecutionContext().putLong("report.total", 42L);
        step.setExitStatus(ExitStatus.FAILED);

        listener().afterStep(step);

        assertFalse(step.getJobExecution().getExecutionContext()
            .containsKey("report.total"));
    }
}
```

Nếu muốn promote thêm các exit code khác, dùng `setStatuses(...)` và viết test cho từng exit code nghiệp vụ. `setStrict(true)` yêu cầu các key đã khai báo phải tồn tại; khi kiểm thử trường hợp key thiếu, cần xét cả hành vi của listener và cách framework xử lý ngoại lệ phát sinh trong callback `afterStep`.

Không giả định rằng `put` vào step context sẽ tự đồng bộ sang job context. Sự khác nhau này là lý do rất nhiều test về `ExecutionContext` cần một cặp assertion: **step có giá trị** và **job có/không có giá trị đúng chính sách**.

## 9. Assert trong `@StepScope` và `@JobScope`

Các bean `@StepScope` có thể nhận dữ liệu qua Spring Expression Language:

```java
@Value("#{stepExecutionContext['tenant.id']}")
String tenantId;
```

Trong khi đó, một giá trị ở job context được đọc qua:

```java
@Value("#{jobExecutionContext['import.total']}")
Long importTotal;
```

Nếu test bean phụ thuộc step scope nhưng không tạo scope, bạn có thể gặp lỗi không có step context hiện hành. `StepScopeTestUtils.doInStepScope` giúp kích hoạt scope cho một `StepExecution` kiểm thử.

Ví dụ với một bean có `@StepScope` đã được Spring quản lý:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;

// tenantFormatter là bean @StepScope đã được inject vào test.
StepExecution step = MetaDataInstanceFactory.createStepExecution();
step.getExecutionContext().putString("tenant.id", "tenant-A");

String displayName = StepScopeTestUtils.doInStepScope(
    step,
    () -> tenantFormatter.formatTenant()
);

assertEquals("TENANT-A", displayName);
```

Trong ví dụ, `tenantFormatter.formatTenant()` là method của component nghiệp vụ chuyển ID thành tên hiển thị. Test cần khẳng định **đầu ra của component sử dụng giá trị trong context**, không chỉ đọc lại chính key vừa tự đặt vào `StepExecution`.

Với `@JobScope`, sử dụng `JobScopeTestUtils` theo cùng nguyên tắc. Trước khi viết assertion, xác định rõ bean lấy dữ liệu từ `stepExecutionContext`, `jobExecutionContext` hay `jobParameters`; ba nguồn này có hợp đồng khác nhau.

## 10. Assert restart: checkpoint phải đến từ lần chạy trước

Mục tiêu quan trọng của `ExecutionContext` là hỗ trợ tiếp tục công việc sau khi batch bị gián đoạn. Một test restart có giá trị phải chứng minh trạng thái **đã lưu ở lần chạy thất bại** được cấp lại cho reader/writer của lần tiếp theo.

### 10.1. Trình tự một bài test restart thực sự

1. Chuẩn bị dữ liệu đầu vào cố định và tạo một bộ `JobParameters`.
2. Cho job chạy, commit được một hoặc vài chunk, sau đó cố ý gây lỗi ở một vị trí xác định.
3. Kiểm tra lần đầu có `BatchStatus.FAILED`; đọc metadata đã persisted và xác định checkpoint cuối cùng **đã commit**.
4. Bỏ điều kiện gây lỗi, chạy lại **cùng job và cùng bộ identifying JobParameters** qua repository cũ.
5. Ghi nhận checkpoint mà `ItemStream.open` thực sự nhận khi restart; assert checkpoint này trùng với trạng thái đã lưu ở bước 3.
6. Assert lần hai `COMPLETED`, không mất hoặc lặp hiệu ứng nghiệp vụ (ví dụ tập ID đầu ra đúng), và checkpoint cuối cùng phản ánh dữ liệu đã xử lý.

Có thể hình dung như sau:

```text
Lần 1:
read 1..50  -> COMMIT -> context offset=50
read 51..75 -> FAIL   -> transaction chưa commit

Repository: checkpoint đã lưu = 50
                |
                v
Lần 2 (cùng JobInstance):
ItemStream.open(context offset=50)
read tiếp từ 51 -> hoàn thành
```

Số offset chỉ là ví dụ: khi lỗi và rollback xảy ra giữa chunk, bạn phải đối chiếu với **ranh giới commit thực tế**. Không được lấy biến offset trong bộ nhớ ngay trước exception rồi mặc định đó là checkpoint bền vững.

### 10.2. Khung assertion cho test restart

Trong test tích hợp, giả sử job đã được cấu hình với một reader checkpointable và một test probe ghi lại giá trị offset nhận ở `open`:

```java
JobParameters sameParameters = new JobParametersBuilder()
    .addString("business.date", "2026-11-16")
    .toJobParameters();

// Cấu hình fixture khiến job lỗi sau khi đã commit một chunk.
failureSwitch.failAfterFirstCommittedChunk();

JobExecution first = jobLauncherTestUtils.launchJob(sameParameters);
assertEquals(BatchStatus.FAILED, first.getStatus());

JobExecution persistedFirst =
    jobExplorer.getJobExecution(first.getId());
assertNotNull(persistedFirst);

StepExecution failedStep = persistedFirst.getStepExecutions().stream()
    .filter(s -> s.getStepName().equals("readCustomersStep"))
    .findFirst()
    .orElseThrow();

long committedOffset =
    failedStep.getExecutionContext().getLong("reader.offset");

// Lần chạy tiếp theo dùng cùng JobParameters, nhưng tắt lỗi mô phỏng.
failureSwitch.disableFailure();
checkpointProbe.reset();

JobExecution second = jobLauncherTestUtils.launchJob(sameParameters);

assertEquals(BatchStatus.COMPLETED, second.getStatus());
assertEquals(
    first.getJobInstance().getId(),
    second.getJobInstance().getId()
);
assertEquals(committedOffset, checkpointProbe.offsetSeenInOpen());

// Ngoài checkpoint, assert dữ liệu đầu ra có tập ID chính xác,
// không trùng do xử lý lại phần đã commit.
```

Đây là **khung test cho fixture restart**: `failureSwitch` và `checkpointProbe` là các test double do ứng dụng định nghĩa. Muốn dùng ví dụ này, cần cài đặt chúng vào reader/writer thực trong test. Không có probe, việc chỉ nhìn context sau lần chạy thứ hai không chứng minh được reader đã *bắt đầu* ở checkpoint mong đợi.

Lưu ý thêm: restart chỉ hợp lệ khi job được cho phép restart, lần trước có trạng thái cho phép chạy lại, identifying parameters không đổi và metadata repository còn dữ liệu. Nếu thay một parameter định danh bằng timestamp mới ở lần hai, hệ thống có thể tạo **JobInstance mới**; đó là một lần chạy mới, không phải restart.

## 11. Các tình huống nâng cao cần kiểm tra

### 11.1. Giá trị có thật sự được persist không?

Hai phép kiểm tra có sức mạnh khác nhau:

```java
// Kiểm tra trạng thái object trong bộ nhớ.
assertEquals(100L, execution.getExecutionContext().getLong("count"));

// Kiểm tra trạng thái được tái tạo từ metadata repository.
JobExecution reloaded = jobExplorer.getJobExecution(execution.getId());
assertNotNull(reloaded);
assertEquals(100L,
    reloaded.getExecutionContext().getLong("count"));
```

Khi test độ bền của checkpoint, hãy đọc lại `StepExecution` từ `JobExplorer` hoặc chạy một lần restart thực tế. Một test chỉ sửa `ExecutionContext` bằng `put` rồi assert trên cùng object không đi qua serializer, transaction hay `JobRepository`.

Không nên assert trực tiếp chuỗi trong các cột `SHORT_CONTEXT` / `SERIALIZED_CONTEXT` của `BATCH_STEP_EXECUTION_CONTEXT` hoặc `BATCH_JOB_EXECUTION_CONTEXT`: định dạng serialization là chi tiết hạ tầng có thể thay đổi. Nên kiểm tra qua API Spring Batch, trừ khi bài test dành riêng để xác minh schema hoặc serializer.

### 11.2. Kiểu giá trị và serialization

Ưu tiên key có giá trị nhỏ, rõ kiểu: chuỗi, số nguyên, timestamp dạng chuỗi chuẩn, định danh nghiệp vụ. Khi cần lưu object tùy biến, cấu hình serializer tương thích và viết test integration kiểm tra object có thể được ghi/đọc lại nguyên vẹn. Một phép assert trong bộ nhớ không đảm bảo class đó được serialize thành công.

Các phép assert nên mô tả hợp đồng kiểu dữ liệu:

```java
assertEquals(200L, context.getLong("reader.offset")); // Long
assertEquals(3, context.getInt("retry.count"));        // Integer
assertEquals("READY", context.getString("phase"));     // String
```

Không giả định `"200"` và `200L` là một giá trị tương đương trong `ExecutionContext`.

### 11.3. Chunk retry, skip và rollback

Trong một chunk có retry/rollback, trạng thái đối tượng trong bộ nhớ có thể tiến xa hơn checkpoint đã commit. Cần assert theo thứ tự:

- `readCount` / `writeCount` / `rollbackCount` của `StepExecution` để hiểu kết quả xử lý.
- Context sau chunk thành công hoặc sau khi job kết thúc, theo đúng ranh giới giao dịch.
- Context **đọc lại từ repository** nếu yêu cầu là khả năng restart.
- Dữ liệu nghiệp vụ để đảm bảo không nhân đôi hiệu ứng khi chạy lại.

Nếu muốn kiểm tra key `lastSuccessfulId`, hãy định nghĩa rõ “successful” là đã xử lý trong JVM, đã gửi cho writer hay đã commit transaction. Assertion chỉ đáng tin khi định nghĩa đó khớp với nơi code cập nhật context.

### 11.4. Partitioning và parallel steps

Mỗi partition/step execution có thể có context riêng. Vì vậy, đừng chọn `jobExecution.getStepExecutions().iterator().next()` một cách tùy ý khi có nhiều step hoặc nhiều partition. Hãy lọc theo tên step/partition, và xác định key nào là kết quả của từng partition, key nào do aggregator hoặc listener đưa lên job context. Thứ tự trong một `Set<StepExecution>` không phải hợp đồng nghiệp vụ.

Ví dụ lọc đúng step trước khi assert:

```java
StepExecution target = execution.getStepExecutions().stream()
    .filter(step -> step.getStepName().equals("importStep"))
    .findFirst()
    .orElseThrow();

assertEquals(7L,
    target.getExecutionContext().getLong("import.total"));
```

Trong job song song, còn phải cân nhắc việc truy cập dữ liệu chia sẻ và thứ tự kết thúc không xác định; phép assert nên dựa trên trạng thái cuối cùng và tiêu chí tổng hợp đã định nghĩa.

## 12. Những lỗi phổ biến khi assert `ExecutionContext`

| Sai lầm | Vì sao test kém tin cậy | Cách sửa |
| --- | --- | --- |
| Chỉ assert `BatchStatus.COMPLETED` | Job có thể hoàn tất nhưng checkpoint/metadata nghiệp vụ sai | Assert thêm key và giá trị cụ thể |
| Đọc job context để tìm key chỉ được ghi ở step | Hai context độc lập | Xác định đúng phạm vi hoặc cấu hình promotion |
| Dùng default getter cho key bắt buộc | Thiếu key vẫn có thể trả về giá trị mong đợi | Assert `containsKey` trước |
| Tự `put` vào context rồi assert lại chính giá trị đó | Chỉ kiểm tra getter/setter của thư viện, không kiểm tra logic ứng dụng | Gọi recorder, reader, listener hoặc chạy step thực |
| Dùng `isDirty()` để khẳng định đã persist | Dirty flag chỉ phản ánh thay đổi object | Đọc lại từ `JobExplorer` hoặc restart |
| Chạy restart với `JobParameters` mới | Tạo `JobInstance` khác thay vì tiếp tục lần cũ | Giữ nguyên identifying parameters |
| Assert checkpoint ngay trước khi transaction rollback | Giá trị đó có thể chưa được commit | Assert checkpoint đã lưu qua repository |
| So toàn bộ map context với map cố định | Framework/reader có thể thêm key hợp lệ | Assert các key thuộc hợp đồng của bài |
| Lấy phần tử đầu tiên trong tập `StepExecution` | Thứ tự không xác định với nhiều step | Lọc theo step name hoặc partition |
| Nhét object không serialize được vào context | Unit test vẫn pass, integration có thể lỗi khi ghi metadata | Dùng kiểu phù hợp và test đọc/ghi thật |

Một phép assert có thông báo lỗi rõ ràng giúp điều tra nhanh:

```java
String key = "reader.offset";
ExecutionContext context = step.getExecutionContext();

assertTrue(
    context.containsKey(key),
    () -> "Missing key '" + key
        + "' in step " + step.getStepName()
        + "; actual keys: " + context.toMap().keySet()
);

assertEquals(
    120L,
    context.getLong(key),
    "Wrong checkpoint in " + step.getStepName()
);
```

Ở Spring Batch 5.1+, `toMap()` trả về góc nhìn chỉ đọc của nội dung context; ở phiên bản cũ hơn có thể lấy các key qua `entrySet()`. Không in toàn bộ giá trị context trong log lỗi nếu nó có dữ liệu nhạy cảm.

## 13. Bài thực hành

**Bài 1 — Unit test key hợp đồng.** Viết một `InvoiceProgressRecorder` ghi `invoice.lastId` (Long), `invoice.successCount` (Integer) và `invoice.phase` (String) vào step context. Sử dụng `MetaDataInstanceFactory` và `assertAll` để kiểm tra đúng giá trị, đúng phạm vi và một key không được xuất hiện.

**Bài 2 — Promotion.** Một step tạo `invoice.total = 250L`; step sau cần đọc tổng đó. Cấu hình `ExecutionContextPromotionListener` cho `invoice.total`. Viết test cho cả `ExitStatus.COMPLETED` và `ExitStatus.FAILED`, xác nhận trường hợp nào job context nhận key.

**Bài 3 — Persist và restart.** Tạo chunk step xử lý 100 dòng với commit interval 20, cố ý lỗi sau khi ít nhất một chunk đã commit. Kiểm tra checkpoint được đọc lại từ `JobExplorer`, sau đó restart với cùng identifying `JobParameters`. Ghi nhận offset tại `ItemStream.open` và assert toàn bộ 100 dòng xuất hiện đúng một lần trong kết quả cuối.

Tiêu chí hoàn thành không chỉ là “test xanh” mà là: **assert được giá trị ở đúng context, đúng thời điểm, và đúng mức kiểm thử (memory, repository hoặc restart)**.

## 14. Ghi chú phiên bản và tài liệu tham khảo

- Các đoạn code trên hướng đến **Spring Batch 5.x**: `ExecutionContext` nằm tại `org.springframework.batch.item`; `@SpringBatchTest` cung cấp `JobLauncherTestUtils`.
- **Spring Batch 6.x** đã thay đổi một số package và test API. `JobLauncherTestUtils` được đánh dấu deprecated để chuyển sang `JobOperatorTestUtils`; `JobExplorer` cũng có thay đổi liên quan đến `JobRepository`. Khi nâng cấp, phải kiểm tra import, chữ ký API và cách tạo test infrastructure theo đúng phiên bản. Các khái niệm hai context, checkpoint, promotion và restart vẫn là cơ sở thiết kế assertion.

Tài liệu chính thức:

- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 5.2 — `ExecutionContext` API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/ExecutionContext.html)
- [Spring Batch 5.2 — `MetaDataInstanceFactory`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/test/MetaDataInstanceFactory.html)
- [Spring Batch 5.2 — `StepScopeTestUtils`](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/test/StepScopeTestUtils.html)
- [Spring Batch — Common Batch Patterns / Passing Data to Future Steps](https://docs.spring.io/spring-batch/reference/common-patterns.html)
- [Spring Batch 6 — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
