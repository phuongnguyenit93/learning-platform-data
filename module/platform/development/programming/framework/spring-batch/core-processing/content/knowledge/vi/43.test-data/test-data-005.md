# Dữ liệu lỗi cho retry trong Spring Batch

Khi kiểm thử một batch job, dữ liệu đầu vào hợp lệ chỉ cho thấy luồng xử lý thông thường có thể hoàn thành. Một hệ thống xử lý theo lô còn phải ứng phó với các lỗi xảy ra tạm thời: dịch vụ phụ trợ mất kết nối trong chốc lát, database từ chối một transaction vì deadlock, thao tác ghi bị timeout hoặc một lần gọi API trả về lỗi có thể khôi phục. Để xác nhận cấu hình **retry** hoạt động đúng, bài test cần tạo ra lỗi **có kiểm soát**, theo dõi số lần thử và xác nhận kết quả sau khi thành công hoặc hết giới hạn thử lại.

Trong module **Spring Batch Core Processing**, bài này tập trung vào **thiết kế dữ liệu lỗi phục vụ kiểm thử retry**: lựa chọn trường hợp lỗi, tổ chức fixture, mô phỏng lỗi theo số lần thử, chạy một chunk step với chính sách retry và viết các phép kiểm tra xác định. Ví dụ dùng Spring Batch 5.x, Spring Boot 3.x, Java 17 và JUnit 5.

## 1. Dữ liệu lỗi cho retry khác dữ liệu sai thông thường

Điều đầu tiên cần quyết định là: **thử lại cùng một item có khả năng thành công hay không?**

| Nhóm lỗi | Tình huống mẫu | Sau khi thử lại | Cách kiểm thử |
| --- | --- | --- | --- |
| Lỗi tạm thời (*transient*) | Một lần gọi dịch vụ trả `503`, deadlock ngắn hạn, kết nối database chập chờn | Có thể thành công khi điều kiện bên ngoài phục hồi | Cho lỗi xuất hiện trong N lần đầu rồi thành công |
| Lỗi tạm thời kéo dài | Dịch vụ vẫn không khả dụng sau nhiều lần thử | Vượt giới hạn retry | Cho lỗi xuất hiện liên tục, kiểm tra bước/job thất bại hoặc đi vào nhánh skip/recovery được cấu hình |
| Lỗi dữ liệu không thể khôi phục (*permanent*) | Ngày không hợp lệ, thiếu mã bắt buộc, vi phạm quy tắc nghiệp vụ | Thử lại cùng dữ liệu vẫn sai | Kiểm tra lỗi không được retry nếu không có chính sách sửa dữ liệu |
| Lỗi không nằm trong tập được retry | Một exception chưa được đăng ký retry | Không nên thử lại theo chính sách hiện tại | Kiểm tra chỉ có một lần xử lý và trạng thái thất bại/skip phù hợp |
| Lỗi khi ghi | Timeout hoặc deadlock trong `ItemWriter` | Có thể ghi thành công sau retry | Kiểm tra số lần gọi writer **và** đầu ra không bị ghi trùng |

**Một bản ghi CSV sai định dạng không tự tạo thành bài test retry có ý nghĩa.** Nếu đọc cùng bản ghi mười lần mà lỗi vẫn như cũ, đây thường là trường hợp validate/skip/fail. Muốn kiểm thử retry, cần một nguồn lỗi có thể đổi trạng thái giữa các lần thử, chẳng hạn stub của API trả lỗi hai lần rồi trả thành công ở lần thứ ba.

Phân biệt thêm ba khái niệm có quan hệ nhưng không đồng nhất:

- **Retry:** thử lại thao tác đã thất bại trong quá trình xử lý, có thể kèm rollback transaction của chunk.
- **Skip:** bỏ qua item lỗi theo chính sách skip, tiếp tục với dữ liệu khác nếu chưa vượt giới hạn skip.
- **Restart:** khởi chạy lại một `JobInstance` đã thất bại hoặc dừng; lần chạy lại là một `JobExecution` khác, có liên quan đến metadata và checkpoint đã lưu.

Một job có thể cấu hình đồng thời retry và skip. Khi lỗi vẫn tồn tại sau các lần retry, framework có thể chuyển sang skip nếu loại lỗi đó được cho phép skip. Vì vậy, kỳ vọng **`FAILED` hay `COMPLETED`** trong test phụ thuộc cả cấu hình retry, skip và transaction chứ không chỉ vào input.

## 2. Tạo bộ dữ liệu kiểm thử theo kịch bản

Một bộ dữ liệu hữu ích cần mô tả **item nào gây lỗi, lỗi xảy ra ở đâu, trong bao nhiêu lần thử, loại exception nào phát sinh và kết quả mong đợi**. Có thể lập ma trận trước khi triển khai fixture:

| Mã test | Item | Vị trí lỗi | Quy tắc phát lỗi | Chính sách giả định | Kỳ vọng |
| --- | --- | --- | --- | --- | --- |
| `OK` | `order-001` | Không có | 0 lần | Retry 3 attempts | `COMPLETED`, xử lý 1 lần |
| `TEMP_ONCE` | `order-002` | Processor | Lần đầu lỗi tạm thời; lần hai thành công | Retry exception tạm thời, tối đa 3 attempts | `COMPLETED`, xử lý 2 lần |
| `TEMP_TWICE` | `order-003` | Processor | Hai lần đầu lỗi, lần ba thành công | Tối đa 3 attempts | `COMPLETED`, xử lý 3 lần |
| `TEMP_EXHAUSTED` | `order-004` | Processor | Luôn ném lỗi tạm thời | Tối đa 3 attempts, không skip | `FAILED`, xử lý 3 lần |
| `PERMANENT` | `order-005` | Processor | Lỗi validation ngay lần đầu | Không retry loại lỗi này, không skip | `FAILED`, xử lý 1 lần |
| `WRITE_ONCE` | `order-006` | Writer | Writer lỗi ở lần đầu, sau đó ghi được | Retry lỗi ghi, tối đa 3 attempts | `COMPLETED`, đầu ra có đúng 1 item |

> Trong bài này, **`retryLimit(3)` nghĩa là tối đa ba attempts, tính cả lần thử đầu tiên**. Vì thế, item lỗi hai lần rồi thành công có ba lần gọi xử lý; item lỗi liên tục đạt giới hạn ở lần thử thứ ba. Không lấy một giá trị cấu hình rồi tự cộng thêm một attempt khi lập expected result.

Có thể đặt dữ liệu nghiệp vụ và kế hoạch gây lỗi trong hai nguồn tách biệt:

```text
src/test/resources/
└── fixtures/
    └── retry/
        ├── orders.csv
        └── fault-plan.csv
```

Nội dung `orders.csv`:

```csv
order_id,customer_id,amount
order-001,c-01,100.00
order-002,c-02,250.00
order-003,c-03,180.00
order-004,c-04,420.00
order-005,c-05,0.00
order-006,c-06,310.00
```

Nội dung `fault-plan.csv` chỉ để test đọc và điều khiển stub hoặc test double:

```csv
case_id,order_id,stage,exception_kind,fail_first_attempts
OK,order-001,PROCESS,NONE,0
TEMP_ONCE,order-002,PROCESS,TRANSIENT,1
TEMP_TWICE,order-003,PROCESS,TRANSIENT,2
TEMP_EXHAUSTED,order-004,PROCESS,TRANSIENT,999
PERMANENT,order-005,PROCESS,VALIDATION,1
WRITE_ONCE,order-006,WRITE,TRANSIENT,1
```

`fail_first_attempts=999` là cách biểu diễn lỗi kéo dài trong một test có ngân sách retry nhỏ, không phải yêu cầu chương trình thật thử 999 lần. Với `PERMANENT`, giá trị `amount=0.00` chỉ là ví dụ dữ liệu có thể vi phạm quy tắc nghiệp vụ; exception validation phải đến từ logic hoặc test double tương ứng.

**Không nên đưa `case_id`, `exception_kind` hoặc `fail_first_attempts` vào model nghiệp vụ sản xuất chỉ để khiến code thực phát lỗi.** Những cột đó thuộc *kịch bản kiểm thử*. Trong test, có thể nạp chúng vào một `FaultPlan` rồi dùng stub/mock/test processor để mô phỏng sự cố cho từng `order_id`. Nhờ vậy, cùng một bản ghi đầu vào có thể kiểm thử cả đường thành công và đường lỗi mà không làm méo dữ liệu nghiệp vụ.

## 3. Cấu hình chunk step có retry

Trong Spring Batch 5, một chunk-oriented step có thể cấu hình retry bằng `faultTolerant()`, `retry(...)` và `retryLimit(...)`. Ví dụ:

```java
@Bean
Step importOrderStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrderStep", jobRepository)
            .<Order, Order>chunk(10, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TemporaryProcessingException.class)
            .retryLimit(3)
            .build();
}
```

Đây là cấu hình minh họa: `Order`, `TemporaryProcessingException`, reader, processor và writer phải được định nghĩa trong ứng dụng tương ứng.

Trong ví dụ:

1. Một chunk có tối đa 10 item.
2. `TemporaryProcessingException` được phép retry.
3. Tổng số attempts cho thao tác lỗi được giới hạn ở ba.
4. Không cấu hình `skip(...)`, nên một lỗi không thể giải quyết khi hết retry sẽ khiến step thất bại.

Khi ném exception ở processor hoặc writer, framework có thể rollback transaction của chunk và gọi lại một phần pipeline. Không nên suy ra số lần `read()`, `process()` và `write()` phải bằng nhau trong mọi tình huống: cách buffering reader, vị trí lỗi, tính giao dịch của reader và việc rollback đều ảnh hưởng đến số lời gọi.

Để minh họa một phép kiểm tra **đếm chính xác số attempts của processor**, phần tiếp theo dùng chunk size bằng 1, một item duy nhất và một processor mô phỏng lỗi trong bộ nhớ. Đây là một fixture nhỏ, xác định, dành riêng cho test.

## 4. Dùng bộ gây lỗi có thể lập trình trong test

Một bộ gây lỗi (*fault injector*) nên có bốn đặc tính:

- Cấu hình được item cần gây lỗi và số lần lỗi đầu tiên.
- Phát ra đúng loại exception mà retry policy phân loại.
- Ghi nhận số lần item được xử lý để test có thể assert.
- Làm sạch trạng thái trước mỗi test; state đếm attempts phải tồn tại qua rollback để mô phỏng dịch vụ bên ngoài đã phục hồi.

Ví dụ sau viết trong package test, dùng Java 17 `record`. Nó không phụ thuộc thời gian thực, không gọi mạng và không sử dụng `Thread.sleep()`:

```java
package com.example.batch;

import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.batch.item.ItemProcessor;

record TestOrder(String id, BigDecimal amount) {}

class TemporaryProcessingException extends RuntimeException {
    TemporaryProcessingException(String message) {
        super(message);
    }
}

class InvalidOrderException extends RuntimeException {
    InvalidOrderException(String message) {
        super(message);
    }
}

class FaultInjectingProcessor
        implements ItemProcessor<TestOrder, TestOrder> {

    private record Rule(int failFirstAttempts, boolean transientError) {}

    private final ConcurrentMap<String, Rule> rules =
            new ConcurrentHashMap<>();
    private final ConcurrentMap<String, AtomicInteger> attempts =
            new ConcurrentHashMap<>();

    void reset() {
        rules.clear();
        attempts.clear();
    }

    void failFirst(String orderId, int failures, boolean transientError) {
        if (failures < 0) {
            throw new IllegalArgumentException("failures must be >= 0");
        }
        rules.put(orderId, new Rule(failures, transientError));
    }

    int attemptCount(String orderId) {
        AtomicInteger counter = attempts.get(orderId);
        return counter == null ? 0 : counter.get();
    }

    @Override
    public TestOrder process(TestOrder item) {
        int current = attempts.computeIfAbsent(
                item.id(), ignored -> new AtomicInteger()
        ).incrementAndGet();

        Rule rule = rules.get(item.id());
        if (rule != null && current <= rule.failFirstAttempts()) {
            if (rule.transientError()) {
                throw new TemporaryProcessingException(
                        "Simulated outage for " + item.id()
                        + ", attempt " + current
                );
            }
            throw new InvalidOrderException(
                    "Invalid order " + item.id()
            );
        }
        return item;
    }
}
```

Cách sử dụng:

```java
faults.failFirst("order-003", 2, true);
// process(order-003) lần 1 -> TemporaryProcessingException
// process(order-003) lần 2 -> TemporaryProcessingException
// process(order-003) lần 3 -> trả về item hợp lệ

faults.failFirst("order-005", 1, false);
// process(order-005) lần 1 -> InvalidOrderException
// Nếu chính sách không retry loại này, chỉ có một attempt.
```

Biến `attempts` ở đây nằm trong bộ nhớ của test, **không nằm trong transaction xử lý item**. Nếu dùng một bản ghi database có transaction rollback để đếm số lần gặp lỗi, việc rollback có thể xóa cả dấu vết của các lần thử trước; fixture “lỗi hai lần rồi thành công” sẽ không vận hành như mong đợi. Trong test tích hợp với các dịch vụ thật, có thể dùng WireMock hoặc một HTTP stub có state đếm request tương tự.

## 5. Ví dụ job kiểm thử có thể chạy độc lập

Để tập trung vào test data và retry, ta tạo một job thử nghiệm chỉ đọc **một đơn hàng** từ `JobParameters`. Writer lưu danh sách item đã nhận vào bộ nhớ. Cách này đủ để kiểm tra lỗi ở processor; nó không được dùng để chứng minh rollback của writer với cơ sở dữ liệu thật.

File `src/test/java/com/example/batch/RetryFixtureJobConfig.java`:

```java
package com.example.batch;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class RetryFixtureJobConfig {

    @Bean
    FaultInjectingProcessor faultInjectingProcessor() {
        return new FaultInjectingProcessor();
    }

    static class RecordingWriter implements ItemWriter<TestOrder> {
        private final List<TestOrder> written =
                new CopyOnWriteArrayList<>();

        @Override
        public void write(Chunk<? extends TestOrder> chunk) {
            written.addAll(chunk.getItems());
        }

        void clear() {
            written.clear();
        }

        List<String> writtenIds() {
            return written.stream().map(TestOrder::id).toList();
        }
    }

    @Bean
    RecordingWriter recordingWriter() {
        return new RecordingWriter();
    }

    @Bean
    @StepScope
    ItemReader<TestOrder> testOrderReader(
            @Value("#{jobParameters['orderId']}") String orderId) {
        return new ListItemReader<>(List.of(
                new TestOrder(orderId, new BigDecimal("100.00"))
        ));
    }

    @Bean
    Step retryFixtureStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            @Qualifier("testOrderReader") ItemReader<TestOrder> reader,
            FaultInjectingProcessor processor,
            RecordingWriter writer) {
        return new StepBuilder("retryFixtureStep", jobRepository)
                .<TestOrder, TestOrder>chunk(1, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .faultTolerant()
                .retry(TemporaryProcessingException.class)
                .retryLimit(3)
                .build();
    }

    @Bean
    Job retryFixtureJob(
            JobRepository jobRepository,
            @Qualifier("retryFixtureStep") Step step) {
        return new JobBuilder("retryFixtureJob", jobRepository)
                .start(step)
                .build();
    }
}
```

Trong cấu hình trên:

- `@StepScope` cho phép `testOrderReader` nhận `orderId` tại thời điểm step chạy. Giá trị này đến từ bộ tham số của **chính lần chạy test**.
- `FaultInjectingProcessor` được giữ trong test context để test thiết lập quy tắc gây lỗi rồi đọc số lần xử lý sau khi job chạy.
- `RecordingWriter` chỉ ghi khi processor trả về thành công. Nếu processor luôn ném exception, danh sách ghi phải rỗng.
- `retry(TemporaryProcessingException.class)` chỉ chọn nhóm exception tạm thời. `InvalidOrderException` không được thêm vào nhóm retry.
- `chunk(1, ...)` giúp cô lập một item và làm kết quả dễ quan sát. Với chunk lớn hoặc chạy nhiều luồng, không thể dùng mọi giả định đơn giản về số lời gọi trong ví dụ này.

## 6. Viết JUnit test xác nhận dữ liệu retry

Dependency kiểm thử cơ bản trong dự án Spring Boot sử dụng Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Ví dụ integration test sau nạp một Spring Boot test context gọn, dùng H2 để lưu bảng metadata của Spring Batch và chủ động chạy job bằng `JobLauncherTestUtils`. File `src/test/java/com/example/batch/RetryDataIntegrationTest.java`:

```java
package com.example.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

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
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBatchTest
@SpringBootTest(
        classes = RetryDataIntegrationTest.TestApp.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always",
                "spring.datasource.url=jdbc:h2:mem:retry_cases;DB_CLOSE_DELAY=-1"
        }
)
class RetryDataIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(RetryFixtureJobConfig.class)
    static class TestApp {}

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    private FaultInjectingProcessor faults;

    @Autowired
    private RetryFixtureJobConfig.RecordingWriter writer;

    @Autowired
    @Qualifier("retryFixtureJob")
    private Job job;

    @BeforeEach
    void prepare() {
        launcher.setJob(job);

        // Chỉ xóa metadata trong database H2 dành riêng cho test.
        repositoryTestUtils.removeJobExecutions();
        faults.reset();
        writer.clear();
    }

    private JobParameters params(String orderId) {
        return new JobParametersBuilder()
                .addString("orderId", orderId)
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();
    }

    @Test
    void succeedsImmediatelyWhenInputHasNoFailure() throws Exception {
        JobExecution execution = launcher.launchJob(params("order-001"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(faults.attemptCount("order-001")).isEqualTo(1);
        assertThat(writer.writtenIds()).containsExactly("order-001");
    }

    @Test
    void succeedsAfterTwoTransientFailures() throws Exception {
        faults.failFirst("order-003", 2, true);

        JobExecution execution = launcher.launchJob(params("order-003"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(faults.attemptCount("order-003")).isEqualTo(3);
        assertThat(writer.writtenIds()).containsExactly("order-003");
    }

    @Test
    void failsWhenTransientErrorExhaustsRetryLimit() throws Exception {
        faults.failFirst("order-004", 999, true);

        JobExecution execution = launcher.launchJob(params("order-004"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.FAILED);
        assertThat(faults.attemptCount("order-004")).isEqualTo(3);
        assertThat(writer.writtenIds()).isEmpty();
    }

    @Test
    void doesNotRetryPermanentError() throws Exception {
        faults.failFirst("order-005", 1, false);

        JobExecution execution = launcher.launchJob(params("order-005"));

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.FAILED);
        assertThat(faults.attemptCount("order-005")).isEqualTo(1);
        assertThat(writer.writtenIds()).isEmpty();
    }
}
```

`@SpringBatchTest` cung cấp các tiện ích chạy job và quản lý metadata test. `spring.batch.job.enabled=false` tránh cho job tự chạy khi context mới khởi tạo. Cấu hình H2 trong đoạn code dành cho môi trường test: database thật có thể dùng script migration hoặc Testcontainers để tạo bảng `BATCH_*` thay cho chế độ khởi tạo schema tự động.

Phương thức `params()` tạo `run.id` mới để mỗi test có thể chạy một `JobInstance` độc lập. Khi **kiểm thử restart cùng instance**, phải giữ nguyên các identifying parameters thay vì tự đổi `run.id`; đó là một kịch bản khác với retry trong cùng lần chạy.

Các kiểm tra trên cố ý quan sát **ba chiều**: `BatchStatus` của job, số lần processor được gọi và các item writer nhận được. Nếu chỉ assert `COMPLETED`, test không thể phân biệt “thành công sau retry” với “chưa từng phát sinh lỗi”.

## 7. Dữ liệu lỗi ở Reader, Processor và Writer

Vị trí lỗi quyết định cách chuẩn bị dữ liệu và điều gì cần quan sát:

### 7.1. Lỗi đọc dữ liệu

Một file chứa ngày sai như `2026-99-99` thường gây lỗi parse ổn định. Dùng nó để kiểm tra validation hoặc skip có ý nghĩa hơn là chờ retry tự sửa dữ liệu. Để kiểm thử lỗi đọc *tạm thời*, có thể mô phỏng nguồn đọc từ API/database bị timeout lần đầu rồi trả về bản ghi hợp lệ. Khi đó cần kiểm tra có bỏ sót hoặc đọc trùng item sau transaction rollback hay không.

Ví dụ fixture lỗi dữ liệu cố định:

```csv
order_id,created_at,amount
order-bad-01,2026-99-99,100.00
order-bad-02,,200.00
```

Đây là nhóm nên test bằng parse/validation expectation riêng. Nếu chính sách của dự án vẫn retry một số exception ở reader, cần chứng minh điều kiện tạm thời thực sự thay đổi giữa các lần thử.

### 7.2. Lỗi xử lý

Processor là vị trí thuận tiện để mô phỏng lỗi có kiểm soát. Có thể ép một item cụ thể ném `TemporaryProcessingException` trong N attempts đầu và trả kết quả ở attempt tiếp theo. Khi không có skip và chỉ có một item, ta dễ quan sát các trạng thái `COMPLETED`/`FAILED` như ví dụ JUnit.

Với processor có logic nghiệp vụ thực, nên bọc **dependency bên ngoài** bằng stub (ví dụ payment gateway hoặc service tra cứu tỷ giá) để test vẫn chạy qua processor thật. Test double của toàn bộ processor phù hợp khi mục tiêu cụ thể là kiểm tra **cơ chế retry của step**.

### 7.3. Lỗi ghi dữ liệu

Lỗi khi ghi cần thử thêm **tính idempotent**. Một service có thể đã nhận request nhưng client timeout trước khi nhận response: việc retry có thể gửi lại cùng request, dẫn đến ghi đôi nếu phía nhận không hỗ trợ idempotency key.

Một bộ test cho writer nên chứa ít nhất:

| Kịch bản | Lỗi mô phỏng | Điều cần kiểm tra |
| --- | --- | --- |
| Ghi thành công lần đầu | Không có | Đúng số dòng/bản ghi đích |
| Ghi lỗi tạm thời rồi thành công | Timeout/deadlock lần đầu | Retry thành công, số bản ghi đích vẫn đúng |
| Trạng thái commit chưa chắc chắn | Server đã nhận request nhưng client bị timeout | Gửi lại không tạo tác động nghiệp vụ trùng |
| Lỗi ghi kéo dài | Exception ở mọi attempt | Job fail/skip theo chính sách, dữ liệu commit không bị dang dở |

Với JDBC writer dùng cùng transaction manager và datasource, rollback thường có thể hoàn tác thao tác SQL của chunk. Với API, message broker hoặc file hệ thống, rollback database **không tự hoàn tác được** tác động bên ngoài. Khi test, hãy dùng dữ liệu có khóa nghiệp vụ (`order_id`) và xác nhận mỗi khóa chỉ được ghi hoặc xử lý đúng một lần theo yêu cầu, thay vì chỉ đếm số request.

`RecordingWriter` bằng bộ nhớ trong ví dụ trên không tham gia transaction; nó đủ cho kịch bản lỗi **trước khi writer được gọi**, nhưng không thể thay thế phép kiểm tra rollback/idempotency của writer thật.

## 8. Sắp xếp test data để kết quả không phụ thuộc thứ tự chạy

Dữ liệu retry dễ làm test bị ảnh hưởng chéo vì vừa có **lịch sử `JobRepository`**, vừa có trạng thái đếm attempts trong stub/mock:

1. Đặt tên case, ID item và expected outcome rõ ràng; mỗi test chỉ nạp những item cần thiết cho case đó. Nếu trộn item `PERMANENT` và `TEMP_ONCE` trong cùng job, job có thể dừng trước khi tới item cần quan sát.
2. Reset bộ đếm fault injector và dữ liệu đích trước mỗi test; không lưu counter dùng chung trong biến `static` thiếu cơ chế reset.
3. Sử dụng database/schema riêng cho integration test. `JobRepositoryTestUtils.removeJobExecutions()` **xóa metadata các lần chạy**, nên chỉ dùng trong repository test cô lập, không dùng trên database đang chia sẻ với môi trường hoặc suite khác.
4. Với test độc lập, dùng identifying `JobParameters` riêng biệt. Với test restart, cố ý giữ lại metadata từ lần chạy `FAILED` và giữ nguyên các identifying parameters.
5. Nếu chạy test song song, tạo context/database/fault state độc lập hoặc điều phối đồng bộ. Một singleton `FaultInjectingProcessor` chia sẻ cho các test chạy song song có thể khiến số attempts sai lệch.
6. Tránh dùng `Thread.sleep()` hoặc phụ thuộc vào độ trễ mạng để tạo “lỗi một lần”. Stub có state và số attempts cố định sẽ tạo lỗi ổn định hơn, dễ tái hiện trong CI.

Trường hợp job dùng `backOffPolicy` có delay dài, nên tạo cấu hình test với delay rất ngắn hoặc bằng 0 để các phép thử không bị kéo dài. Tuy nhiên, test riêng cho cơ chế backoff cần giữ phép đo/thời gian có kiểm soát và ngưỡng chấp nhận phù hợp.

## 9. Khi test thất bại, đọc kết quả thế nào?

Spring Batch cung cấp `JobExecution`, các `StepExecution`, `ExitStatus` và exception để quan sát lần chạy. Ví dụ:

```java
JobExecution execution = launcher.launchJob(params("order-004"));

System.out.println("Job status = " + execution.getStatus());
System.out.println("Exit status = " + execution.getExitStatus());

execution.getStepExecutions().forEach(step -> {
    System.out.println("Step = " + step.getStepName());
    System.out.println("Read = " + step.getReadCount());
    System.out.println("Write = " + step.getWriteCount());
    System.out.println("Rollback = " + step.getRollbackCount());
    System.out.println("Skip = " + step.getSkipCount());
});

execution.getAllFailureExceptions()
        .forEach(Throwable::printStackTrace);
```

Để chẩn đoán **số lần retry thực tế**, trong ví dụ này nên xem `faults.attemptCount(orderId)` vì đó là counter đặt ngay tại điểm gây lỗi. `StepExecution.getReadCount()` hay `getProcessSkipCount()` không thay thế trực tiếp cho số attempts: chúng có ý nghĩa khác và chịu ảnh hưởng của commit/rollback, skip và chunk.

Nếu job dùng `RetryListener`, có thể ghi nhận mỗi lần retry và exception tương ứng để test nhận diện đúng loại lỗi; không nên suy luận số lần từ số dòng log chung của job. Ngoài ra, exception từ HTTP/JDBC đôi khi bị framework hoặc lớp ứng dụng bọc lại: policy retry phải khớp với **loại exception thực tế nhìn thấy tại ranh giới step**, không chỉ với thông báo lỗi trong log.

## 10. Bài thực hành mở rộng

Dựa trên bộ fixture và integration test bên trên, hãy mở rộng theo thứ tự sau:

1. Thêm case `TEMP_ONCE` cho `order-002`, cho lỗi đúng một lần rồi thành công; kiểm tra `attemptCount=2` và chỉ một item được ghi.
2. Thử `retryLimit(2)` với case lỗi hai lần rồi thành công ở lần thứ ba. Quan sát vì sao step thất bại trước lần thành công dự kiến; điều chỉnh expected attempts cho phù hợp.
3. Thêm một nhánh `.skip(InvalidOrderException.class).skipLimit(1)` và kiểm tra kết quả khác gì so với case `PERMANENT` đang thất bại. Với một item invalid được skip, step có thể `COMPLETED` nhưng có skip count bằng 1.
4. Thay test processor bằng processor nghiệp vụ thật nhưng dùng API stub trả `503` hai lần, sau đó trả `200`. Kiểm tra kết quả nghiệp vụ và số request stub ghi nhận.
5. Thử writer dùng database test có unique constraint trên `order_id`, mô phỏng lỗi transient ở lần ghi đầu; sau job, kiểm tra chỉ tồn tại một bản ghi và kết quả không bị ghi trùng.
6. Tạo case job `FAILED` rồi **restart với cùng identifying parameters**, quan sát checkpoint của reader/step và phân biệt hành vi restart với retry trong một execution.

Điều cốt lõi khi thiết kế **dữ liệu lỗi cho retry** là biến sự cố từ điều khó đoán thành một quy tắc có thể tái hiện: **item nào lỗi, ở thao tác nào, lỗi thuộc loại gì, lỗi trong bao nhiêu attempts và cuối cùng dữ liệu phải ở trạng thái nào**. Nhờ vậy, kiểm thử Spring Batch có thể chứng minh cả việc retry được kích hoạt đúng lúc lẫn việc hệ thống dừng đúng giới hạn và không làm hỏng dữ liệu.
