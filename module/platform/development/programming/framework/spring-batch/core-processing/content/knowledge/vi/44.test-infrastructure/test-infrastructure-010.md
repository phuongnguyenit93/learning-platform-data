# Executor test trong Spring Batch: kiểm thử cơ chế thực thi Job và Step

Trong Spring Batch, **executor** quyết định công việc được thực thi trên luồng (thread) nào, chạy tuần tự hay có thể chạy đồng thời. Khi xây dựng hạ tầng kiểm thử (*Test infrastructure*), cấu hình executor ảnh hưởng trực tiếp đến thời điểm một lời gọi khởi chạy Job trả về, cách xác nhận trạng thái cuối cùng, khả năng tái hiện lỗi và độ ổn định của toàn bộ bộ test.

Một phép kiểm thử executor tốt cần trả lời hai câu hỏi riêng:

1. **Executor chạy đúng cách chưa?** Chẳng hạn tác vụ có chạy trong thread gọi, hay được đưa sang worker thread; tối đa bao nhiêu tác vụ có thể chạy cùng lúc?
2. **Spring Batch chạy đúng khi dùng executor đó chưa?** Job có kết thúc ở trạng thái mong đợi, Step có xử lý đủ dữ liệu, dữ liệu có bị mất hoặc ghi trùng khi thực thi song song hay không?

Bài học đi từ kiểm thử `TaskExecutor` trực tiếp đến kiểm thử tích hợp `JobLauncher`/`JobOperator` và Step song song. Các ví dụ có kèm timeout để một test lỗi không treo mãi.

## 1. Executor là gì trong hệ sinh thái Spring Batch?

`TaskExecutor` là giao diện của Spring Framework:

```java
public interface TaskExecutor extends Executor {
    void execute(Runnable task);
}
```

Khi nhận một `Runnable`, executor chọn cách chạy tác vụ. Các triển khai thông dụng:

| Executor | Cách thực thi | Khi nào hữu ích trong test |
| --- | --- | --- |
| `SyncTaskExecutor` | Chạy `Runnable` ngay trên thread gọi. | Test logic Job/Step tuần tự, dễ quan sát trạng thái cuối, dễ truy vết lỗi. |
| `SimpleAsyncTaskExecutor` | Thực thi tác vụ ở thread khác, thường tạo thread mới cho tác vụ. | Kiểm tra hành vi khởi chạy bất đồng bộ cơ bản. |
| `ThreadPoolTaskExecutor` | Điều phối tác vụ vào nhóm worker có cấu hình pool và queue. | Kiểm tra giới hạn song song, xử lý khi tải cao và vòng đời executor. |
| Executor tùy biến | Chặn, ghi nhận, sắp lịch hoặc thực thi tác vụ theo cơ chế kiểm thử. | Kiểm tra tác vụ có được gửi đi và điều khiển thứ tự chạy một cách xác định. |

**Hai vị trí cấu hình executor thường bị nhầm lẫn:**

```text
Test / Scheduler / HTTP request
    |
    v
JobLauncher hoặc JobOperator
    |  (A) TaskExecutor khởi chạy Job
    v
Job.execute(...)
    |
    v
Step
    |  (B) TaskExecutor thực thi chunk/flow song song
    v
ItemReader -> ItemProcessor -> ItemWriter
```

- **(A) Executor của bộ khởi chạy Job:** quyết định lời gọi `run(...)` hoặc `start(...)` có chờ Job hoàn thành hay trả về khi Job vẫn đang chạy. Nó **không tự biến các chunk thành song song**.
- **(B) Executor trong Step hoặc flow:** quyết định việc xử lý chunk/nhánh có được giao cho worker threads hay không. Job có thể được khởi chạy đồng bộ nhưng các chunk vẫn xử lý song song.

Ngoài hai trường hợp này còn có partitioning, split flows và các cơ chế remote. Mỗi cơ chế có mô hình điều phối khác nhau; cần đặt phép assert đúng tầng.

## 2. Xác định hợp đồng của bài test trước khi chạy

Ví dụ với Job import 100 giao dịch:

| Mục đích | Điều cần khẳng định | Điều không nên mặc định |
| --- | --- | --- |
| Test executor đồng bộ | Tác vụ hoàn thành trước khi `execute(...)` trả về; chạy trên thread gọi. | Không cần khẳng định tốc độ cụ thể. |
| Test executor bất đồng bộ | Có thể quan sát tác vụ ở worker thread; test kiểm soát điểm chờ và hoàn thành. | `execute(...)` trả về không có nghĩa tác vụ đã xong. |
| Test Job launcher đồng bộ | `JobExecution` trả về đã đạt trạng thái cuối. | Một Job `COMPLETED` chưa đủ chứng minh dữ liệu đúng. |
| Test Job launcher bất đồng bộ | Job bắt đầu, vẫn đang chạy khi bị chặn ở test gate, rồi kết thúc sau khi được giải phóng. | `JobExecution` trả về ban đầu không nhất thiết đã `COMPLETED`. |
| Test Step song song | Có overlap thực tế giữa các xử lý và dữ liệu đầu ra chính xác. | Không đảm bảo thứ tự các bản ghi được xử lý hoặc ghi. |
| Test cấu hình thread pool | Tác vụ tuân theo giới hạn pool/queue; tài nguyên được đóng sau test. | Không đảm bảo thứ tự scheduler cho mọi lần chạy. |

Có thể phân loại phép kiểm tra thành:

- **Status assertion:** `BatchStatus.COMPLETED`, `FAILED`, `STOPPED`; có thể thêm `ExitStatus`.
- **Concurrency assertion:** số tác vụ active, thread name, số task đồng thời, dấu mốc bắt đầu/kết thúc.
- **Data assertion:** `readCount`, `writeCount`, `skipCount`, số bản ghi và tập giá trị đầu ra.
- **Lifecycle assertion:** tài nguyên executor được giải phóng và không còn tác vụ chạy khi dữ liệu test được dọn.

Không dùng thông số hiệu năng như “phải xong dưới 200 ms” để thay thế việc chứng minh concurrency; thời gian thực thi còn tùy CI, CPU và database.

## 3. Dependency và cấu hình môi trường test

Trong dự án Spring Boot sử dụng Gradle, các dependency điển hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Để test Job thật cần một `JobRepository` và `PlatformTransactionManager` được cấu hình đúng, cùng schema metadata phù hợp với phiên bản Spring Batch. Nên dùng database/schema dành riêng cho test.

Với test tích hợp sử dụng `@SpringBootTest`, tắt chế độ tự chạy Job ngay lúc khởi tạo context:

```java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class MyBatchTest {
    // Test chủ động khởi chạy Job.
}
```

`@SpringBatchTest` cung cấp các tiện ích kiểm thử Spring Batch; `@SpringBootTest` nạp ứng dụng. Không nên để Job tự chạy một lượt trước khi test chuẩn bị xong fixture.

### Chọn phiên bản API

Các ví dụ triển khai đầy đủ ở mục 4–7 dùng **Spring Batch 5.x / Spring Boot 3.x**:

- `org.springframework.batch.core.Job`, `JobExecution`, `JobParameters`.
- `JobLauncher` và `TaskExecutorJobLauncher`.
- `JobLauncherTestUtils.launchJob(...)` khi cần tiện ích khởi chạy Job trong test.

Ở **Spring Batch 6.x**, API được tổ chức lại theo các gói `...core.job`, `...core.job.parameters`, `...core.step`. `TaskExecutorJobOperator` và `JobOperatorFactoryBean` là những API phù hợp để cấu hình executor cho `JobOperator`. Các ý tưởng kiểm thử `TaskExecutor`, latch, status, timeout và cô lập dữ liệu vẫn giữ nguyên, nhưng import và công cụ khởi chạy cần đúng phiên bản. Mục 8 nêu biến thể Spring Batch 6.

## 4. Unit test `SyncTaskExecutor`: kiểm soát đồng bộ

`SyncTaskExecutor` là lựa chọn hữu ích khi bài test tập trung vào nghiệp vụ Batch, không có mục tiêu kiểm tra chạy song song.

Ví dụ JUnit Jupiter và AssertJ:

```java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.SyncTaskExecutor;

import static org.assertj.core.api.Assertions.assertThat;

class SyncExecutorTest {

    @Test
    void shouldRunOnCallingThreadBeforeExecuteReturns() {
        TaskExecutor executor = new SyncTaskExecutor();
        String callingThread = Thread.currentThread().getName();
        AtomicReference<String> actualThread = new AtomicReference<>();
        AtomicReference<String> outcome = new AtomicReference<>("not-run");

        executor.execute(() -> {
            actualThread.set(Thread.currentThread().getName());
            outcome.set("done");
        });

        assertThat(actualThread.get()).isEqualTo(callingThread);
        assertThat(outcome.get()).isEqualTo("done");
    }
}
```

Khi `execute(...)` trả về, tác vụ đã chạy xong. `SyncTaskExecutor` còn có một đặc điểm hữu ích khi kiểm thử: ngoại lệ không được bắt trong `Runnable` có thể truyền ngay về lời gọi `execute(...)`. Điều này giúp tìm nguyên nhân lỗi dễ hơn trong test tuần tự, nhưng **không có nghĩa bất kỳ ngoại lệ nào từ Step sẽ luôn được ném ra ngoài Job launcher**: Spring Batch có cơ chế ghi `FAILED` vào `JobExecution`.

Nếu mục tiêu của test là hành vi đọc/ghi hoặc phép biến đổi dữ liệu, dùng đồng bộ giúp giảm các yếu tố biến thiên từ scheduler.

## 5. Unit test `ThreadPoolTaskExecutor`: chứng minh hai tác vụ chạy đồng thời

Để kiểm tra executor thực sự có thể chạy song song, nên dùng `CountDownLatch` làm điểm hẹn. Không dựa vào `Thread.sleep(100)` rồi suy đoán tác vụ đã chạy.

Ví dụ hoàn chỉnh sau tạo hai worker, giữ cả hai ở trạng thái đang thực thi, và chỉ mở chốt cho kết thúc sau khi test quan sát đủ hai tác vụ:

```java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import static org.assertj.core.api.Assertions.assertThat;

class ThreadPoolExecutorTest {

    @Test
    void shouldRunTwoTasksAtTheSameTime() throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("batch-test-");
        executor.initialize();

        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch allowFinish = new CountDownLatch(1);
        CountDownLatch bothFinished = new CountDownLatch(2);
        Set<String> workerNames = ConcurrentHashMap.newKeySet();

        Runnable task = () -> {
            try {
                workerNames.add(Thread.currentThread().getName());
                bothStarted.countDown();

                if (!allowFinish.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Test gate timed out");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Worker interrupted", ex);
            } finally {
                bothFinished.countDown();
            }
        };

        try {
            executor.execute(task);
            executor.execute(task);

            assertThat(bothStarted.await(3, TimeUnit.SECONDS))
                    .as("Cả hai tác vụ phải bắt đầu trước khi mở chốt")
                    .isTrue();
            assertThat(workerNames).hasSize(2);
            assertThat(workerNames)
                    .allMatch(name -> name.startsWith("batch-test-"));
        } finally {
            allowFinish.countDown();
            assertThat(bothFinished.await(6, TimeUnit.SECONDS))
                    .as("Worker phải thoát trước khi kết thúc test")
                    .isTrue();
            executor.shutdown();
        }
    }
}
```

Giải thích:

1. Pool có hai core threads; cấu hình `queueCapacity=0` để không xếp hàng tác vụ thứ hai khi vẫn có worker trống.
2. Mỗi task gọi `bothStarted.countDown()` và chờ ở `allowFinish`.
3. Nếu cả hai đã gọi `countDown()` trước khi được giải phóng, có bằng chứng rằng cả hai đang ở trong `Runnable` cùng thời điểm.
4. `workerNames` là set thread-safe để kiểm tra không có hai tác vụ cùng chạy trên một thread tuần tự.
5. `finally` mở chốt ngay cả khi assertion thất bại, tránh giữ worker vô thời hạn.
6. `executor.shutdown()` kết thúc vòng đời tài nguyên sau test.

Giới hạn timeout nên có biên độ đủ rộng cho CI. Nếu runtime rất chậm, có thể cần điều chỉnh `3` và `6` giây theo môi trường thực tế, nhưng phép kiểm tra về **quan hệ xảy ra trước/sau** quan trọng hơn thời gian tuyệt đối.

### Test giới hạn tải và từ chối task

Đối với pool có kích thước/queue cố định, có thể giữ các worker bằng latch, lấp đầy queue và xác nhận lần submit vượt quá sức chứa bị từ chối, ví dụ bằng `TaskRejectedException` (tùy Spring và handler cấu hình). Cần thiết kế số lượng task, kích thước queue và điểm chặn rõ ràng; không kiểm tra dựa vào một thời điểm ngẫu nhiên.

Không nên thay toàn bộ test `ThreadPoolTaskExecutor` bằng `SyncTaskExecutor` nếu mục tiêu là phát hiện lỗi race condition hoặc giới hạn tài nguyên.

## 6. Tích hợp Spring Batch: test Job với executor đồng bộ

Trong Spring Batch 5.x, `TaskExecutorJobLauncher` có thể dùng `SyncTaskExecutor` để chạy Job ngay trên thread gọi. Bài test tích hợp sau giả định ứng dụng đã có Job bean `importOrdersJob` và fixture dữ liệu để Job hoàn thành thành công.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.support.TaskExecutorJobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.core.task.SyncTaskExecutor;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@Import(SynchronousJobLauncherIT.ExecutorConfig.class)
class SynchronousJobLauncherIT {

    @Autowired
    @Qualifier("syncTestLauncher")
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @Test
    void shouldReturnCompletedExecution() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncher.run(importOrdersJob, parameters);

        // Launcher đồng bộ: Job đã chạy xong khi run(...) trả về.
        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getEndTime()).isNotNull();
    }

    @TestConfiguration
    static class ExecutorConfig {

        @Bean("syncTestLauncher")
        JobLauncher syncTestLauncher(JobRepository repository)
                throws Exception {
            TaskExecutorJobLauncher launcher =
                    new TaskExecutorJobLauncher();
            launcher.setJobRepository(repository);
            launcher.setTaskExecutor(new SyncTaskExecutor());
            launcher.afterPropertiesSet();
            return launcher;
        }
    }
}
```

Dùng `testRunId` ngẫu nhiên để các lần chạy độc lập không tái sử dụng một `JobInstance` đã `COMPLETED` trong cùng JobRepository. Đối với test restart, giữ nguyên identifying parameters giữa các lần chạy và không dọn metadata ở giữa.

Ví dụ trên kiểm thử cách launcher kết hợp executor với Spring Batch: trạng thái cuối của `JobExecution` được quan sát **ngay sau** lời gọi đồng bộ. Đây là thiết lập phù hợp cho phần lớn test nghiệp vụ. Muốn kiểm tra launcher bất đồng bộ, cần một phép test khác với điểm chặn có thể điều khiển.

## 7. Tích hợp Spring Batch: test Job launcher bất đồng bộ

Khi Job launcher dùng executor bất đồng bộ, lời gọi khởi chạy có thể trả về trước khi Job chuyển sang trạng thái cuối:

```text
Test thread               Worker thread                 JobRepository
    |                          |                               |
    |---- run(Job, params) ----|------------------------------>|
    |<--- JobExecution ------- |      lưu STARTING             |
    |                          |---- Job.execute() ----------->|
    |                          |      STARTED                  |
    | ...test chờ có timeout   |      xử lý Step              |
    |                          |      COMPLETED/FAILED         |
    |---- đọc lại repository --------------------------------->|
```

**Không assert `BatchStatus.COMPLETED` ngay trên đối tượng vừa được trả về** nếu Job còn đang chạy. `JobExecution` là trạng thái thay đổi theo thời gian. Nên dùng `JobExplorer` để đọc lại bản ghi và polling đến trạng thái kết thúc có timeout.

### Cấu hình launcher bất đồng bộ cho test

Trong Spring Batch 5.x:

```java
@TestConfiguration
static class AsyncLauncherConfig {

    @Bean("asyncTestLauncher")
    JobLauncher asyncTestLauncher(JobRepository repository)
            throws Exception {
        TaskExecutorJobLauncher launcher =
                new TaskExecutorJobLauncher();
        launcher.setJobRepository(repository);
        launcher.setTaskExecutor(
                new SimpleAsyncTaskExecutor("batch-async-test-"));
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

Trong ứng dụng thực, có thể thay `SimpleAsyncTaskExecutor` bằng `ThreadPoolTaskExecutor` nếu muốn kiểm tra pool/queue thực tế. Với bean pool, cần bảo đảm đóng pool khi application context được đóng.

### Kiểm tra trạng thái cuối bằng polling có timeout

Nếu `asyncTestLauncher` là bean ở trên và `importOrdersJob` đã được chuẩn bị đầy đủ fixture:

```java
import java.time.Duration;
import java.util.UUID;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.explore.JobExplorer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

// Bên trong test class có @SpringBatchTest, @SpringBootTest và
// @Import(AsyncLauncherConfig.class).
//
// @Autowired @Qualifier("asyncTestLauncher") JobLauncher asyncLauncher;
// @Autowired @Qualifier("importOrdersJob") Job importOrdersJob;
// @Autowired JobExplorer jobExplorer;

@Test
void shouldEventuallyCompleteAfterAsyncLaunch() throws Exception {
    var params = new JobParametersBuilder()
            .addString("testRunId", UUID.randomUUID().toString())
            .toJobParameters();

    JobExecution accepted = asyncLauncher.run(importOrdersJob, params);
    Long executionId = accepted.getId();

    await()
            .atMost(Duration.ofSeconds(15))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                JobExecution current =
                        jobExplorer.getJobExecution(executionId);
                assertThat(current).isNotNull();
                assertThat(current.getStatus())
                        .isEqualTo(BatchStatus.COMPLETED);
            });
}
```

`Awaitility` là thư viện thường được mang vào cùng `spring-boot-starter-test`; nếu dự án không có thì bổ sung dependency test tương ứng. Ví dụ dùng `Spring Batch 5.x`; các kiểu `JobExecution`, `JobParametersBuilder` được chuyển gói ở phiên bản 6.x.

Trong test này, việc Job hoàn tất chứng minh đường chạy bất đồng bộ không bị lỗi, nhưng **chưa tự chứng minh lời gọi ban đầu trả về trước khi Job kết thúc**. Để kiểm tra thực sự bất đồng bộ, thêm một chốt `CountDownLatch` vào Tasklet/Processor có kiểm soát. Cho worker chờ chốt, kiểm tra rằng lời gọi launcher đã trả về trong lúc chốt còn đóng, sau đó mở chốt và đợi trạng thái `COMPLETED`. Điều này tránh kết luận từ việc CPU chạy nhanh hay chậm.

Ví dụ nguyên lý:

```java
CountDownLatch stepStarted = new CountDownLatch(1);
CountDownLatch allowStepToFinish = new CountDownLatch(1);

// Tasklet test fixture:
// stepStarted.countDown();
// if (!allowStepToFinish.await(10, TimeUnit.SECONDS)) {
//     throw new IllegalStateException("Gate timed out");
// }
// return RepeatStatus.FINISHED;

// Test method:
JobExecution accepted = asyncLauncher.run(gatedJob, params);

try {
    assertThat(stepStarted.await(3, TimeUnit.SECONDS)).isTrue();

    // Vì tasklet vẫn đang bị chặn, job chưa thể kết thúc.
    JobExecution current =
            jobExplorer.getJobExecution(accepted.getId());
    assertThat(current.getStatus())
            .isIn(BatchStatus.STARTING, BatchStatus.STARTED);
} finally {
    allowStepToFinish.countDown();
}

// Sau khi mở chốt, polling JobExplorer đến COMPLETED.
// Đợi đến khi Job kết thúc hẳn trước khi dọn JobRepository.
```

Lưu ý: các latch của fixture phải thuộc riêng mỗi test hoặc được reset đúng cách; không dùng chung một latch đã đếm về 0 giữa nhiều lần chạy. Với `@AfterEach`, không xóa metadata khi Job bất đồng bộ có thể vẫn đang cập nhật Step/JobExecution.

## 8. Biến thể ở Spring Batch 6.x

Spring Batch 6 tổ chức lại các API Job và dùng `JobOperator` như giao diện vận hành chính cho nhiều thao tác, trong đó có khởi chạy Job. Cấu hình executor bất đồng bộ theo tài liệu sử dụng `JobOperatorFactoryBean`:

```java
import org.springframework.batch.core.launch.support.JobOperatorFactoryBean;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Bean
JobOperatorFactoryBean asyncJobOperator(JobRepository repository) {
    JobOperatorFactoryBean factory = new JobOperatorFactoryBean();
    factory.setJobRepository(repository);
    factory.setTaskExecutor(
            new SimpleAsyncTaskExecutor("batch-operator-test-"));
    return factory;
}
```

Ví dụ này minh họa cách cấu hình *executor*; application context thực tế vẫn phải có các thành phần batch cần thiết như JobRegistry và JobRepository. `JobOperatorTestUtils` ở `spring-batch-test` có thể khởi chạy Job được cấu hình cho test qua `startJob(parameters)`.

Khi muốn kiểm tra logic Job ở chế độ đồng bộ, cấu hình `SyncTaskExecutor` thay cho `SimpleAsyncTaskExecutor` trong bean `JobOperator` dành riêng cho test. Khi muốn kiểm tra hành vi bất đồng bộ, áp dụng cùng mô hình latch và polling `JobExplorer` như mục 7.

Không nên trộn import Job/Step/JobParameters của Spring Batch 5 và 6 trong cùng một project; phải căn cứ dependency thực tế để chọn đúng API.

## 9. Kiểm thử executor ở Step xử lý song song

Ở một multi-threaded Step, executor được cấu hình ngay trên Step builder. Với Spring Batch 5.x:

```java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        TaskExecutor batchStepExecutor) {

    return new StepBuilder("importStep", jobRepository)
            .<Order, Order>chunk(10, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .taskExecutor(batchStepExecutor)
            .build();
}
```

Các biến `Order`, reader/processor/writer và `batchStepExecutor` ở đây là thành phần nghiệp vụ dự án tự cung cấp. Với Spring Batch 6.x, cách khai báo chunk/transaction manager có thể thay đổi; tham khảo API của phiên bản đang dùng.

### Các thuộc tính cần kiểm tra

- **Không mất/trùng bản ghi:** tổng số ID đầu ra phải bằng đầu vào hợp lệ, không có ID lặp.
- **Không phụ thuộc thứ tự:** thay vì assert `[1, 2, 3, 4]` đúng theo thứ tự, dùng `containsExactlyInAnyOrder(...)` hoặc so sánh tập ID.
- **Có concurrency thật:** ghi nhận số worker đang xử lý bằng `AtomicInteger`/latch; kiểm tra có ít nhất hai xử lý overlap nếu đó là yêu cầu.
- **Giới hạn tài nguyên:** dùng pool, datasource và transaction manager thích hợp; với DB, kích thước connection pool có thể hạn chế khả năng xử lý song song.
- **Tính thread-safe:** `ItemReader`, `ItemProcessor`, `ItemWriter` và các bean chia sẻ phải an toàn khi truy cập đồng thời; đặc biệt tránh dùng biến mutable không được đồng bộ.

Có thể dùng một bộ đếm vào/ra Processor như sau:

```java
AtomicInteger inFlight = new AtomicInteger();
AtomicInteger peakConcurrency = new AtomicInteger();

ItemProcessor<Integer, Integer> processor = item -> {
    int active = inFlight.incrementAndGet();
    peakConcurrency.accumulateAndGet(active, Math::max);

    try {
        // Xử lý bản ghi; có thể dùng latch test để ép overlap.
        return item * 2;
    } finally {
        inFlight.decrementAndGet();
    }
};
```

Sau khi Job kết thúc, nếu test fixture được thiết kế để chặn hai worker đồng thời:

```java
assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(peakConcurrency.get()).isGreaterThanOrEqualTo(2);
assertThat(output).containsExactlyInAnyOrder(2, 4, 6, 8);
```

Nếu processor chạy cực nhanh, `peakConcurrency` có thể vẫn là 1 dù executor có khả năng chạy song song. Vì vậy, muốn assertion `>= 2` ổn định phải tạo **điểm hẹn xác định** (ví dụ CountDownLatch hai worker hoặc barrier) trong test fixture, khởi chạy Job trên thread riêng để test mở chốt, và gắn timeout cho tất cả lệnh chờ.

### Thread safety của reader

Nhiều `ItemReader` có trạng thái nội bộ (cursor, vị trí dòng, số bản ghi), nên việc dùng trực tiếp trong multi-threaded Step có thể đọc sai hoặc làm mất tính restartability. Có thể dùng reader vốn thread-safe, phân vùng nguồn dữ liệu (*partitioning*), hoặc decorator như `SynchronizedItemReader`/`SynchronizedItemStreamReader` khi phù hợp. Đồng bộ hóa phép `read()` không tự động giải quyết mọi vấn đề trạng thái, transaction và restart; cần kiểm tra hành vi nghiệp vụ cụ thể.

### Lưu ý về transaction

Spring quản lý transaction gắn với thread. Trong một multi-threaded Step, không nên mặc định context transaction của thread gọi được truyền cho mọi worker. Kiểm tra commit/rollback, retry/skip và tính idempotent trên hạ tầng thực tế, nhất là khi ItemProcessor/Writer có thao tác database.

## 10. Kiểm thử executor cho split flows và partitioning

Executor còn xuất hiện ở cấp Job flow hoặc partition handler:

| Kiểu xử lý | Executor điều phối | Phép test gợi ý |
| --- | --- | --- |
| Split flows | Các nhánh flow có thể chạy đồng thời. | Kiểm tra cả hai nhánh bắt đầu, Job chỉ kết thúc sau khi các nhánh hoàn tất. |
| Local partitioning | Chạy các worker StepExecution theo partition. | Kiểm tra mỗi partition xử lý đúng phạm vi, không mất/trùng dữ liệu và tổng hợp status đúng. |
| Multi-threaded chunk Step | Nhiều chunk/đơn vị xử lý trên worker threads. | Kiểm tra thread safety, trạng thái Step, tổng số bản ghi và tính idempotent. |

Không suy luận rằng đã khai báo `TaskExecutor` là mọi nhánh nhất định chạy song song. Số luồng thực tế còn phụ thuộc số task, giới hạn pool, queue, cấu hình Step, tài nguyên database và cơ chế triển khai. Trong test, muốn chứng minh concurrency phải có một tình huống đủ việc để hai worker thực sự overlap.

## 11. Tổ chức test để tránh flaky test và rò rỉ thread

### 11.1. Dùng đồng bộ cho phần lớn bài test nghiệp vụ

Các test kiểm tra parse, transform, skip, retry, listener hoặc status thường có thể chạy với `SyncTaskExecutor`. Bài test dành riêng cho tính năng song song mới cần pool bất đồng bộ và cơ chế điều phối có kiểm soát.

### 11.2. Không dùng sleep cố định để suy đoán trạng thái

Cách dễ lỗi:

```java
jobLauncher.run(job, params);
Thread.sleep(300);
assertThat(jobExplorer.getJobExecution(id).getStatus())
        .isEqualTo(BatchStatus.COMPLETED);
```

Thời gian Job thực thi thay đổi theo môi trường. Một delay cố định vừa khiến test chậm, vừa không bảo đảm Job đã hoàn tất. Dùng `CountDownLatch`, `Future.get(timeout, unit)`, `CompletableFuture` hoặc polling có timeout tùy tầng cần kiểm tra.

### 11.3. Luôn giải phóng thread và điểm chặn

Khi test thất bại, `finally` vẫn cần mở latch, ngắt hoặc dừng executor nếu test sở hữu nó. Đối với `ThreadPoolTaskExecutor` tạo trong test, gọi `shutdown()`. Với executor bean do Spring quản lý, bảo đảm vòng đời application context được đóng và không còn tác vụ sử dụng tài nguyên test.

### 11.4. Cô lập JobRepository và dữ liệu nghiệp vụ

Kết quả Step/Job bất đồng bộ có thể đang được ghi vào bảng metadata. Không dọn metadata ngay sau `run(...)` chỉ vì lời gọi đã trả về. Đợi trạng thái cuối, sau đó mới gọi `JobRepositoryTestUtils.removeJobExecutions()` trên repository test riêng. Tương tự, không xóa file hoặc bảng dữ liệu nghiệp vụ khi worker còn dùng chúng.

### 11.5. Không chia sẻ trạng thái mutable giữa các test song song

`CountDownLatch`, `AtomicInteger`, queue, danh sách output, file path và tên JobParameters nên thuộc vòng đời mỗi test. Nếu Spring test context cache bean dùng chung chứa state mutable, phải thiết kế reset/cô lập rõ ràng. Cấu hình pool theo test cũng nên có thread-name prefix riêng để debug dễ hơn.

### 11.6. Tránh assert đúng thứ tự completion

Hai tác vụ được submit theo thứ tự A, B không có nghĩa hoàn thành theo thứ tự A, B. Chỉ assert thứ tự nếu đó là một hợp đồng thực sự của executor/hạ tầng và đã cấu hình để bảo đảm hợp đồng đó. Với xử lý song song, tập đầu ra và quan hệ trước/sau thường là phép đo ổn định hơn.

### 11.7. Phân biệt lỗi submit với lỗi khi chạy

Có thể có hai dạng lỗi:

- **Lỗi gửi tác vụ vào executor:** ví dụ pool đã đóng hoặc queue đầy và cấu hình từ chối. Lỗi có thể xuất hiện ngay khi gọi `execute(...)`/`run(...)`.
- **Lỗi thực thi Job/Step:** executor nhận tác vụ nhưng nghiệp vụ gặp exception; Spring Batch thường ghi `BatchStatus.FAILED` và ngoại lệ vào `JobExecution`.

Một bài test kiểm tra từ chối task không nên tự động kỳ vọng có `JobExecution.FAILED` nếu Job chưa từng được thực thi. Một bài test kiểm tra lỗi xử lý cần đọc `JobExecution`/`StepExecution` của lần chạy thực tế.

## 12. Tình huống thực hành

Ứng dụng có Job `importProductsJob` đọc 20 sản phẩm, transform và ghi vào database. Mục tiêu là kiểm thử hạ tầng executor ở hai cấu hình.

**Kịch bản A – Đồng bộ:**

1. Tạo Job/Step test, dataset 20 sản phẩm và repository riêng.
2. Dùng `SyncTaskExecutor` cho Job launcher và Step nếu test không cần song song.
3. Khởi chạy Job bằng identifying parameters mới.
4. Assert `BatchStatus.COMPLETED`, `readCount` và `writeCount` đúng, bảng đích có 20 bản ghi.
5. Dọn metadata và dữ liệu nghiệp vụ sau khi Job đã kết thúc.

**Kịch bản B – Hai worker song song:**

1. Cấu hình `ThreadPoolTaskExecutor` với hai worker và tên thread có prefix riêng.
2. Dùng ItemReader thread-safe hoặc phân vùng dữ liệu; thiết kế Processor test có latch để hai tác vụ cùng chạm điểm hẹn.
3. Khởi chạy Job trên thread riêng, tránh chặn thread test khi Processor chờ latch.
4. Chờ latch của hai worker với timeout; xác nhận hai worker thật sự hoạt động đồng thời.
5. Mở latch, chờ Job hoàn thành bằng `Future` hoặc `JobExplorer` có timeout.
6. Assert `COMPLETED`, 20 ID đầu ra không trùng, không mất bản ghi; so sánh không phụ thuộc thứ tự.
7. Đóng executor, xác nhận không còn tác vụ xử lý trước khi xóa metadata và fixture.

Sau khi hoàn thành, hãy thử thay pool hai worker bằng `SyncTaskExecutor` và quan sát sự khác nhau ở phép kiểm tra overlap. Bài tập giúp tách rõ **khả năng chạy song song của executor** khỏi **tính đúng đắn của dữ liệu và trạng thái Spring Batch**.

## Tài liệu tham khảo

- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, các triển khai executor và cấu hình thread pool.
- [Spring Batch 5.2 – Configuring a JobLauncher](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-launcher.html): executor đồng bộ/bất đồng bộ với `TaskExecutorJobLauncher`.
- [Spring Batch – Configuring a JobOperator](https://docs.spring.io/spring-batch/reference/job/configuring-operator.html): cấu hình `JobOperator` và executor ở dòng Spring Batch 6.x.
- [Spring Batch – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded Step, split flows và partitioning.
- [Spring Batch – Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): tiện ích test Job/Step và Spring Batch test context.
- [Spring Batch 6 – TaskExecutorJobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/support/TaskExecutorJobOperator.html).

