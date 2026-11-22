# Kiểm thử JobInstance trong Spring Batch

## 1. Mục tiêu

Khi kiểm thử một batch job, việc khẳng định job trả về `COMPLETED` mới chỉ cho biết **một lần thực thi** thành công. Để kiểm tra cơ chế chạy lại và khởi động lại đúng, cần kiểm thử cả **JobInstance**: Spring Batch xác định hai yêu cầu chạy có thuộc cùng một instance hay không, tạo bao nhiêu lần thực thi và cho phép chạy lại trong trường hợp nào.

Sau bài này, bạn có thể:

- Phân biệt `Job`, `JobInstance` và `JobExecution` trong các phép kiểm thử.
- Chủ động tạo `JobParameters` để kiểm soát danh tính của một `JobInstance`.
- Kiểm tra các trường hợp chạy lần đầu, chạy lại sau thành công, chạy với tham số khác và khởi động lại sau thất bại.
- Dùng `JobExplorer`, `JobRepository` và `spring-batch-test` để quan sát metadata thay vì chỉ kiểm tra log.
- Nhận diện các trường hợp kiểm thử cho kết quả sai do tham số ngẫu nhiên, metadata tồn dư hoặc job tự khởi chạy.

## 2. JobInstance là gì và vì sao phải kiểm thử?

Một `Job` là định nghĩa công việc, gồm các step và luồng xử lý. Mỗi lần yêu cầu chạy job, Spring Batch xác định `JobInstance` từ **tên job** và **các JobParameters được đánh dấu identifying**.

Về mặt khái niệm:

```text
JobInstance = Job name + identifying JobParameters

Job: importOrdersJob
    |
    +-- JobInstance A: businessDate=2026-11-16
    |      +-- JobExecution 101: FAILED
    |      +-- JobExecution 102: COMPLETED (restart)
    |
    +-- JobInstance B: businessDate=2026-11-17
           +-- JobExecution 103: COMPLETED
```

| Thành phần | Ý nghĩa | Điều cần khẳng định khi test |
| --- | --- | --- |
| `Job` | Định nghĩa quy trình xử lý | Đúng job được gọi |
| `JobParameters` | Đầu vào của lượt chạy; mỗi tham số có cờ identifying | Các tham số định danh được thiết lập có chủ đích |
| `JobInstance` | Danh tính logic của một lần xử lý dữ liệu theo bộ tham số định danh | Cùng tham số định danh cho cùng instance; khác tham số định danh cho instance khác |
| `JobExecution` | Một lần cố gắng thực thi của instance | Mỗi lần restart hợp lệ tạo execution mới |
| `StepExecution` | Lần thực thi một step trong một JobExecution | Step nào được chạy lại hoặc được bỏ qua khi restart |
| `JobRepository` | Nơi lưu và quản lý metadata batch | Metadata tồn tại, không bị tạo trùng instance ngoài ý muốn |
| `JobExplorer` | API đọc metadata đã được lưu | Số instance, số execution và trạng thái đúng như kỳ vọng |

**Lưu ý:** `BatchStatus` (chẳng hạn `COMPLETED`, `FAILED`, `STOPPED`) biểu thị trạng thái xử lý; `ExitStatus` là kết quả kết thúc có thể được tùy biến để phục vụ luồng điều khiển hoặc báo cáo. Không đồng nhất hai khái niệm này.

### Identifying và non-identifying parameters

Theo mặc định, các cách thêm tham số thông thường trong `JobParametersBuilder` sử dụng tham số định danh. Có thể chỉ định tường minh:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true) // Định danh instance
    .addString("requestId", "req-001", false)      // Chỉ để truy vết
    .toJobParameters();
```

Đổi `businessDate` làm đổi danh tính instance. Chỉ đổi `requestId` thì **không** tạo instance mới.

Điều này cũng giải thích một lỗi thiết kế phổ biến: thêm `run.id` hoặc timestamp ngẫu nhiên như tham số **identifying** vào mỗi lần chạy sẽ khiến Spring Batch tạo instance mới, nên bài kiểm thử không còn kiểm tra được hành vi chạy lại cùng instance.

## 3. Các kịch bản cần kiểm thử

Giả sử job tên `importOrdersJob`, tham số định danh là `businessDate`:

| Tình huống | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Chạy lần đầu | Chưa có instance với `businessDate=D1` | Tạo một `JobInstance` và một `JobExecution` |
| Chạy lại khi đã thành công | Instance với `D1` đã `COMPLETED` | Từ chối lần chạy mới, thường bằng `JobInstanceAlreadyCompleteException` |
| Chạy với ngày khác | Instance `D1` đã có; gọi với `D2` | Tạo instance mới, có ID khác |
| Thay tham số không định danh | Giữ `D1`, đổi `requestId` | Vẫn là cùng instance; nếu đã hoàn tất thì bị từ chối |
| Restart sau thất bại | Execution trước của `D1` là `FAILED`, job cho phép restart | Instance ID giữ nguyên; có thêm JobExecution mới |
| Chạy trùng khi job còn hoạt động | Một execution của cùng instance đang chạy | Từ chối khởi chạy đồng thời, thường bằng `JobExecutionAlreadyRunningException` |
| Restart job không restartable | Instance đã tồn tại và job đặt `restartable=false` | Từ chối restart, thường bằng `JobRestartException` |

Các ngoại lệ cần được kiểm tra trong **điều kiện gây ra ngoại lệ thực sự**. Chẳng hạn, không nên dùng một job hoàn tất quá nhanh để kiểm thử chạy đồng thời, vì job có thể đã kết thúc trước khi yêu cầu thứ hai được gửi.

## 4. Chiến lược kiểm thử

Bài kiểm thử JobInstance thường là **integration test**: phải có `JobLauncher`, `JobRepository` và kho metadata thực (ví dụ cơ sở dữ liệu H2 dành cho test). Mock toàn bộ repository rồi tự gán instance ID chỉ kiểm tra hành vi mock, không xác minh thuật toán nhận dạng instance và quy tắc restart của Spring Batch.

Với ứng dụng Spring Boot 3.x và Spring Batch 5.x, các dependency thông dụng (Gradle) là:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-batch'
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.batch:spring-batch-test'
testRuntimeOnly 'com.h2database:h2'
```

Trong môi trường thử nghiệm:

- Tắt việc tự động chạy job khi application context khởi động bằng `spring.batch.job.enabled=false`.
- Khởi tạo schema metadata dành cho cơ sở dữ liệu test, ví dụ `spring.batch.jdbc.initialize-schema=always` khi dùng H2 riêng cho test.
- Cô lập metadata giữa các test, chẳng hạn dùng `JobRepositoryTestUtils.removeJobExecutions()` hoặc một cơ sở dữ liệu độc lập.
- Dùng bộ `JobParameters` **cố định** trong phép kiểm tra chạy lại, và bộ khác ở phép kiểm tra tạo instance mới.
- Kiểm tra đồng thời kết quả trả về từ launcher và metadata đọc qua `JobExplorer`.

`@SpringBatchTest` cung cấp các tiện ích như `JobLauncherTestUtils` và `JobRepositoryTestUtils`. Tuy nhiên, `JobLauncherTestUtils.launchJob()` **không truyền tham số** thường tạo các tham số duy nhất để hỗ trợ test chạy độc lập. Để kiểm tra tính đồng nhất của JobInstance, hãy truyền tham số xác định vào `launchJob(parameters)` hoặc trực tiếp gọi `jobLauncher.run(job, parameters)`.

## 5. Ví dụ tích hợp với JUnit 5

Ví dụ sau tạo job đơn giản có một tasklet. Biến `failNextExecution` cho phép chủ động làm lần thực thi kế tiếp thất bại để kiểm tra restart. Ứng dụng test có H2 và Spring Batch metadata, không cần truy cập hệ thống bên ngoài.

> Ví dụ hướng tới Spring Boot 3.x / Spring Batch 5.x. Khi ứng dụng dùng phiên bản khác, cần điều chỉnh cách khai báo hạ tầng batch và dependency tương ứng.

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = JobInstanceIntegrationTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:job_instance_test;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
    }
)
class JobInstanceIntegrationTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("instanceDemoJob")
    private Job job;

    @Autowired
    private AtomicBoolean failNextExecution;

    @BeforeEach
    void cleanBeforeEachTest() {
        repositoryTestUtils.removeJobExecutions();
        failNextExecution.set(false);
    }

    private JobParameters businessDate(String date) {
        return new JobParametersBuilder()
            .addString("businessDate", date, true)
            .toJobParameters();
    }

    @Test
    void completedInstanceCannotBeExecutedAgain() throws Exception {
        JobParameters parameters = businessDate("2026-11-16");

        JobExecution first = jobLauncher.run(job, parameters);

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertThrows(
            JobInstanceAlreadyCompleteException.class,
            () -> jobLauncher.run(job, parameters)
        );

        List<JobInstance> instances =
            jobExplorer.getJobInstances(job.getName(), 0, 10);

        assertEquals(1, instances.size());
        assertEquals(1, jobExplorer.getJobExecutions(instances.get(0)).size());
    }

    @Test
    void differentIdentifyingParametersCreateDifferentInstances()
            throws Exception {
        JobExecution first =
            jobLauncher.run(job, businessDate("2026-11-16"));
        JobExecution second =
            jobLauncher.run(job, businessDate("2026-11-17"));

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertEquals(BatchStatus.COMPLETED, second.getStatus());
        assertNotEquals(
            first.getJobInstance().getInstanceId(),
            second.getJobInstance().getInstanceId()
        );
        assertEquals(
            2,
            jobExplorer.getJobInstances(job.getName(), 0, 10).size()
        );
    }

    @Test
    void nonIdentifyingParameterDoesNotCreateAnotherInstance()
            throws Exception {
        JobParameters firstParameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-16", true)
            .addString("requestId", "req-001", false)
            .toJobParameters();

        JobParameters secondParameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-16", true)
            .addString("requestId", "req-002", false)
            .toJobParameters();

        JobExecution first = jobLauncher.run(job, firstParameters);

        assertEquals(BatchStatus.COMPLETED, first.getStatus());
        assertThrows(
            JobInstanceAlreadyCompleteException.class,
            () -> jobLauncher.run(job, secondParameters)
        );
        assertEquals(
            1,
            jobExplorer.getJobInstances(job.getName(), 0, 10).size()
        );
    }

    @Test
    void failedExecutionCanRestartWithinSameInstance() throws Exception {
        JobParameters parameters = businessDate("2026-11-16");
        failNextExecution.set(true);

        JobExecution failed = jobLauncher.run(job, parameters);
        JobExecution restarted = jobLauncher.run(job, parameters);

        assertEquals(BatchStatus.FAILED, failed.getStatus());
        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

        assertEquals(
            failed.getJobInstance().getInstanceId(),
            restarted.getJobInstance().getInstanceId()
        );
        assertNotEquals(failed.getId(), restarted.getId());

        JobInstance instance =
            jobExplorer.getJobInstances(job.getName(), 0, 1).get(0);
        assertEquals(2, jobExplorer.getJobExecutions(instance).size());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        AtomicBoolean failNextExecution() {
            return new AtomicBoolean(false);
        }

        @Bean
        Job instanceDemoJob(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                AtomicBoolean failNextExecution) {

            Step step = new StepBuilder("instanceDemoStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    if (failNextExecution.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Simulated failure for restart test"
                        );
                    }
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();

            return new JobBuilder("instanceDemoJob", jobRepository)
                .start(step)
                .build();
        }
    }
}
```

### Giải thích các assertion

**Phép thử 1 — Chạy lại instance đã hoàn tất.** `jobLauncher.run(job, parameters)` đầu tiên phải thành công; lần thứ hai với đúng bộ tham số định danh bị từ chối. Hai assertion đọc metadata xác nhận chỉ có một instance và một execution, nên không có execution thừa được tạo sau ngoại lệ.

**Phép thử 2 — Tham số định danh khác nhau.** Hai giá trị `businessDate` tạo hai instance khác ID. Việc cả hai execution đều `COMPLETED` là điều kiện bổ sung: hai instance thực sự đã được chạy.

**Phép thử 3 — Tham số không định danh.** `requestId` thay đổi nhưng `businessDate` giữ nguyên. Nếu test chỉ so sánh toàn bộ đối tượng `JobParameters`, bạn có thể kết luận sai rằng đây là hai instance khác nhau. Kiểm tra metadata giúp khẳng định quy tắc định danh của Spring Batch.

**Phép thử 4 — Restart sau lỗi.** Tasklet được cấu hình thất bại đúng một lần; lần chạy tiếp theo hoàn tất. Hai `JobExecution` có ID khác nhau, nhưng cả hai trỏ về cùng `JobInstance`. Đây là khác biệt cốt lõi giữa **restart** và **tạo một instance mới**.

Test cố ý dùng một job chạy đồng bộ và một biến điều khiển lỗi để kịch bản restart xác định được kết quả. Khi đưa vào dự án thật, thay `instanceDemoJob` bằng job cần kiểm thử; giữ nguyên ý tưởng điều khiển đầu vào và truy vấn metadata. Nếu bộ test chạy song song hoặc chia sẻ database, phải cô lập context và dữ liệu để không có test nào xóa metadata của test khác.

## 6. Kiểm tra metadata trực tiếp

Trong môi trường sử dụng `JdbcJobRepository`, có thể đối chiếu thông tin trong các bảng metadata:

- `BATCH_JOB_INSTANCE`: ghi nhận instance, tên job và khóa định danh.
- `BATCH_JOB_EXECUTION`: ghi nhận từng lần thực thi và trạng thái của nó, liên kết tới instance.
- `BATCH_JOB_EXECUTION_PARAMS`: ghi nhận tham số của execution, gồm dấu hiệu tham số identifying.
- `BATCH_STEP_EXECUTION`: phục vụ phân tích step nào đã chạy, thất bại hoặc được xử lý lại.

Ví dụ truy vấn chỉ để quan sát, không cần đưa SQL này vào assertion chính:

```sql
SELECT
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'instanceDemoJob'
ORDER BY ji.JOB_INSTANCE_ID, je.JOB_EXECUTION_ID;
```

Khi restart sau lỗi, bạn mong đợi hai dòng có cùng `JOB_INSTANCE_ID` nhưng khác `JOB_EXECUTION_ID`. Nếu các lần chạy lại sinh ra `JOB_INSTANCE_ID` khác, hãy kiểm tra tham số identifying và các cơ chế tự tăng `run.id`.

Ưu tiên `JobExplorer` trong test Java để tránh phụ thuộc trực tiếp vào tên bảng, kiểu dữ liệu và biến thể schema giữa các phiên bản. SQL phù hợp hơn khi điều tra lỗi hoặc kiểm tra dữ liệu vận hành.

## 7. Kiểm thử các trường hợp biên

### 7.1. Hai yêu cầu cùng lúc cho cùng instance

Đây là phép thử về kiểm soát đồng thời, khác với việc gọi hai lần liên tiếp. Một cách tiếp cận có thể kiểm soát:

1. Tạo step đầu tiên chờ tại một `CountDownLatch`, để execution thứ nhất thực sự đang chạy.
2. Dùng launcher hoặc cơ chế thực thi phù hợp chạy yêu cầu thứ nhất trên một luồng riêng.
3. Chỉ sau khi xác nhận execution thứ nhất đang `STARTED`, gửi yêu cầu thứ hai với **cùng tham số định danh**.
4. Khẳng định yêu cầu thứ hai bị từ chối bằng `JobExecutionAlreadyRunningException` và không có hai execution đang hoạt động cho cùng instance.
5. Giải phóng latch, chờ luồng thứ nhất kết thúc và dọn tài nguyên trong `finally`.

Không dùng `Thread.sleep` để *đoán* khi nào step bắt đầu; phụ thuộc thời gian dễ gây test không ổn định. Không dùng test với step kết thúc tức thì, vì yêu cầu thứ hai có thể gặp trường hợp instance đã hoàn tất thay vì đang chạy.

### 7.2. Job không cho phép restart

Có thể định nghĩa một job không restartable:

```java
Job nonRestartableJob = new JobBuilder("nonRestartableJob", jobRepository)
    .start(step)
    .preventRestart()
    .build();
```

Cho execution đầu thất bại có kiểm soát, rồi gọi lại cùng tham số. Khẳng định `JobRestartException` và không phát sinh execution mới. Cần dùng **instance đã thực thi**, vì một job `preventRestart()` vẫn được phép chạy lần đầu cho bộ tham số mới.

### 7.3. Step đã hoàn tất khi restart

JobInstance không đồng nghĩa với việc mọi step đều chạy lại. Với job nhiều step, các step đã `COMPLETED` thường được bỏ qua khi restart, trừ khi cấu hình cho phép chạy lại (ví dụ `allowStartIfComplete(true)`). Bài kiểm thử nên đọc `StepExecution` hoặc kiểm tra số lần gọi thật để xác nhận step bị lỗi được chạy lại và step đã hoàn tất không bị thực thi ngoài ý muốn.

### 7.4. Metadata khớp nhưng dữ liệu nghiệp vụ vẫn sai

Một `JobInstance` duy nhất không tự đảm bảo không ghi trùng đơn hàng hoặc không gửi thông báo hai lần. Job có thể ghi một phần dữ liệu trước khi thất bại; khi restart, các bước ghi phải có transaction, checkpoint hoặc cơ chế idempotent phù hợp. Vì vậy, với bài toán thực tế, kết hợp kiểm thử metadata với assertion trên bảng hoặc đầu ra nghiệp vụ sau mỗi lần chạy.

## 8. Các lỗi thường gặp khi viết test

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Hai lần gọi luôn tạo instance mới | Mỗi lần thêm timestamp, UUID hoặc `run.id` mang tính identifying | Truyền lại đúng các identifying parameters của lượt đầu |
| Test chạy lại không xuất hiện ngoại lệ | `JobLauncherTestUtils.launchJob()` tự tạo tham số duy nhất | Dùng `launchJob(parameters)` hoặc `jobLauncher.run(job, parameters)` |
| Test độc lập thì đạt, chạy cả suite thì lỗi | Metadata từ test trước còn tồn tại hoặc nhiều test dùng chung DB | Dọn metadata có kiểm soát; dùng database/context riêng |
| Job chạy trước khi test gọi launcher | Spring Boot tự khởi chạy job lúc startup | Đặt `spring.batch.job.enabled=false` |
| Tham số `requestId` làm tăng số instance | Đánh dấu nó là identifying | Dùng `addString("requestId", value, false)` |
| Restart tạo instance mới | Tham số định danh đã thay đổi | Giữ nguyên identifying parameters; không tự tăng run ID |
| Không thấy bảng metadata | Schema batch chưa khởi tạo | Cấu hình schema cho DB test và kiểm tra dependency |
| Test chạy song song thất thường | Dùng cùng DB, cùng job name hoặc biến điều khiển lỗi | Cô lập trạng thái và tránh dọn dữ liệu của luồng khác |

## 9. Bài tập vận dụng

Hãy mở rộng `instanceDemoJob` thành job có hai step: `validateInputStep` và `persistDataStep`. Lần đầu, cho step thứ nhất hoàn tất và step thứ hai thất bại; lần thứ hai, cho job restart thành công với cùng `businessDate`.

Xác minh cả ba kết quả: chỉ có **một JobInstance**, có **hai JobExecution** và `validateInputStep` không thực thi lại nếu step đó đã hoàn tất và không được cấu hình `allowStartIfComplete(true)`. Sau đó thử đánh dấu thêm `sourceSystem` là identifying và quan sát khi giá trị tham số này thay đổi thì số instance tăng lên như thế nào.

## 10. Kết luận

Điểm chính của kiểm thử JobInstance là **danh tính và vòng đời**: cùng tên job cộng cùng tập tham số định danh xác định cùng instance; một instance có thể có nhiều execution khi restart hợp lệ; instance đã hoàn tất không được chạy lại với cùng danh tính. Kết hợp `JobLauncher` để kích hoạt hành vi với `JobExplorer` để kiểm tra metadata sẽ giúp phát hiện lỗi cấu hình tham số, chạy trùng và restart sớm hơn so với cách chỉ quan sát trạng thái `COMPLETED`.
