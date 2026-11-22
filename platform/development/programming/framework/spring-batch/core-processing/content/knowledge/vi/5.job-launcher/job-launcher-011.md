# Kiểm thử JobLauncher với job test trong Spring Batch

`JobLauncher` là thành phần nhận một `Job` cùng `JobParameters` và yêu cầu Spring Batch thực thi job đó. Khi kiểm thử, ta cần xác nhận launcher phối hợp đúng với `JobRepository`, tạo execution, truyền tham số, chạy các step và trả về trạng thái phù hợp. Một cách thực tế để kiểm tra luồng này là tạo một **job test** nhỏ, chỉ dùng trong môi trường test, rồi khởi chạy nó bằng chính hạ tầng batch mà ứng dụng cấu hình.

Spring Batch cung cấp `spring-batch-test` và `JobLauncherTestUtils` để hỗ trợ công việc đó. Utility này gọi `JobLauncher` đã được cấu hình trong test context, giúp kiểm thử gần với cách ứng dụng chạy thật mà không cần viết một scheduler hoặc khởi chạy toàn bộ ứng dụng thủ công.

## 1. Phân biệt kiểm thử JobLauncher và kiểm thử logic của step

Một job batch có thể được kiểm thử ở nhiều mức:

| Mức kiểm thử | Mục tiêu | Cách thực hiện thường dùng |
| --- | --- | --- |
| Unit test cho processor hoặc service | Kiểm tra logic nghiệp vụ độc lập. | Gọi trực tiếp method, không cần khởi chạy job. |
| Kiểm thử một step | Kiểm tra reader, processor, writer hoặc tasklet trong một step. | `JobLauncherTestUtils.launchStep(...)` hoặc cấu hình step test riêng. |
| Kiểm thử job | Kiểm tra các step và flow được điều phối đúng. | `JobLauncherTestUtils.launchJob(...)`. |
| Kiểm thử tích hợp launcher | Kiểm tra `JobLauncher`, `JobRepository`, transaction manager và job cùng hoạt động trong Spring context. | Khởi chạy job test qua `JobLauncherTestUtils` hoặc gọi trực tiếp `JobLauncher`. |

Trong bài này, trọng tâm là kiểm thử luồng khởi chạy job thông qua launcher. Một job test nên nhỏ, dễ hiểu và có kết quả quan sát được. Khi mục tiêu là kiểm tra flow hoặc cấu hình launcher, không cần đưa toàn bộ xử lý nghiệp vụ production vào test job.

## 2. Thêm thư viện kiểm thử Spring Batch

Các tiện ích kiểm thử nằm trong module `spring-batch-test`. Với dự án Gradle dùng Spring Boot dependency management, có thể khai báo:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.batch:spring-batch-test")
    testRuntimeOnly("com.h2database:h2")
}
```

`spring-batch-test` nên dùng cùng phiên bản tương thích với `spring-batch-core` trong ứng dụng. Nếu dự án không dùng Spring Boot dependency management, cần khai báo version tương ứng thay vì để các module Spring Batch lệch phiên bản.

H2 là một lựa chọn cho metadata repository trong test vì có thể tạo database riêng trong bộ nhớ. Dự án có thể dùng database test khác nếu cần xác nhận hành vi SQL, locking hoặc transaction đặc thù của database production.

## 3. JobLauncherTestUtils và @SpringBatchTest

`JobLauncherTestUtils` là tiện ích trong `spring-batch-test`. Nó cung cấp các phương thức thường dùng:

- `launchJob()` khởi chạy job đã được gắn vào utility với bộ tham số được tạo cho lần chạy test.
- `launchJob(JobParameters)` khởi chạy job với tham số do test chỉ định.
- `launchStep(String stepName)` khởi chạy một step riêng trong một job test tạm thời.
- Các overload của `launchStep(...)` cho phép truyền thêm `JobParameters` và `ExecutionContext`.
- `setJob(Job job)` chọn job mà utility sẽ khởi chạy. Đây là cách rõ ràng để chỉ định job test khi context có nhiều bean `Job`.

Annotation `@SpringBatchTest` hỗ trợ đăng ký các tiện ích như `JobLauncherTestUtils` và `JobRepositoryTestUtils`, đồng thời cấu hình các listener cần thiết cho kiểm thử scope của Spring Batch như job scope và step scope. Nó được kết hợp với test context của Spring, ví dụ `@SpringBootTest` hoặc `@SpringJUnitConfig`.

`JobLauncherTestUtils` sử dụng `JobLauncher` và `JobRepository` trong application context. Vì vậy, bài test có thể kiểm tra cấu hình thực tế của ứng dụng mà không tự tạo một launcher giả. Với test context độc lập, cần cung cấp đầy đủ batch infrastructure, datasource và schema metadata phù hợp.

## 4. Tạo một job test nhỏ

Ví dụ sau dùng Spring Boot test context và khai báo một job riêng cho test. Job chỉ có một tasklet step. Khi được khởi chạy, step kết thúc bình thường để test có thể kiểm tra `JobExecution` và `StepExecution`.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@TestConfiguration
class LauncherTestJobConfiguration {

    @Bean
    Step launcherTestStep(JobRepository jobRepository,
                          PlatformTransactionManager transactionManager) {
        return new StepBuilder("launcherTestStep", jobRepository)
            .tasklet((contribution, chunkContext) -> RepeatStatus.FINISHED,
                     transactionManager)
            .build();
    }

    @Bean
    Job launcherTestJob(JobRepository jobRepository,
                        Step launcherTestStep) {
        return new JobBuilder("launcherTestJob", jobRepository)
            .start(launcherTestStep)
            .build();
    }
}
```

Đây là cách khai báo theo API builder của Spring Batch 5. Với phiên bản cũ, cách tạo `JobBuilder` và `StepBuilder` có thể khác; hãy dùng API tương ứng với phiên bản đang được dự án quản lý.

Job test có tên `launcherTestJob`, step có tên `launcherTestStep`. Tên riêng giúp tránh nhầm lẫn với job production và làm cho assertion trong test rõ ràng. Tasklet trả về `RepeatStatus.FINISHED`, vì vậy step hoàn tất sau một lần gọi.

Trong ứng dụng có nhiều `PlatformTransactionManager`, hãy dùng `@Qualifier` để chỉ định transaction manager dành cho step test. Job và step phải sử dụng cùng batch infrastructure mà test đang muốn kiểm tra.

## 5. Kiểm thử khởi chạy job bằng JobLauncherTestUtils

Test dưới đây nạp application context, đăng ký tiện ích Spring Batch và import cấu hình job test. Nó chọn rõ job cần chạy bằng `setJob()` rồi khởi chạy với một bộ tham số riêng cho lần test.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest(properties = "spring.batch.job.enabled=false")
@SpringBatchTest
@Import(LauncherTestJobConfiguration.class)
class JobLauncherIntegrationTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("launcherTestJob")
    Job launcherTestJob;

    @BeforeEach
    void selectJobUnderTest() {
        jobLauncherTestUtils.setJob(launcherTestJob);
    }

    @Test
    void launchesTestJobAndReturnsExecutionMetadata() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
            .addString("requestId", UUID.randomUUID().toString(), true)
            .addString("source", "launcher-test", false)
            .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getExitStatus()).isEqualTo(ExitStatus.COMPLETED);
        assertThat(execution.getJobInstance().getJobName())
            .isEqualTo("launcherTestJob");
        assertThat(execution.getStepExecutions()).hasSize(1);

        StepExecution stepExecution = execution.getStepExecutions()
            .iterator()
            .next();

        assertThat(stepExecution.getStepName()).isEqualTo("launcherTestStep");
        assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    }
}
```

Trong ví dụ:

1. `@SpringBootTest` nạp cấu hình ứng dụng và batch infrastructure.
2. `spring.batch.job.enabled=false` ngăn Spring Boot tự khởi chạy job khi tạo application context. Test sẽ chủ động quyết định lúc nào job chạy.
3. `@SpringBatchTest` đăng ký các tiện ích kiểm thử Spring Batch.
4. `@Import` thêm job test vào context.
5. `setJob(launcherTestJob)` bảo đảm utility chạy đúng job cần kiểm thử, kể cả khi ứng dụng có nhiều job bean.
6. `launchJob(parameters)` gọi launcher với bộ tham số đã định nghĩa.
7. Test xác nhận trạng thái job, exit status, tên job và kết quả thực thi step.

`requestId` là identifying parameter và được tạo mới cho mỗi lần chạy test. Nhờ vậy, các lần test không vô tình sử dụng lại cùng một `JobInstance`. `source` là non-identifying parameter để minh họa một tham số mô tả nguồn yêu cầu nhưng không tham gia xác định danh tính instance.

Nếu dự án không dùng Spring Boot, có thể thay `@SpringBootTest` và `@Import` bằng `@SpringJUnitConfig` cùng cấu hình test cung cấp `JobRepository`, `JobLauncher`, datasource, transaction manager và job test. Nguyên tắc vẫn là utility phải nhận đúng `Job` và dùng batch infrastructure của test context.

## 6. Vì sao cần tắt tự động chạy job trong test?

Spring Boot có thể tự khởi chạy job khi ứng dụng bắt đầu nếu batch job auto-launch được bật. Điều đó thuận tiện khi chạy ứng dụng, nhưng trong test có thể khiến job chạy ngay lúc context được tạo, trước khi test gọi `JobLauncherTestUtils`.

Kết quả là test có thể gặp các vấn đề như:

- Job bị chạy hai lần: một lần do cơ chế tự động, một lần do test.
- Job production được khởi chạy ngoài ý muốn trong test context.
- Dữ liệu test bị thay đổi trước khi assertion bắt đầu.
- Job instance đã hoàn tất khiến lần gọi tiếp theo với cùng identifying parameters bị từ chối.

Với Spring Boot, thuộc tính `spring.batch.job.enabled=false` thường được dùng để tắt cơ chế tự khởi chạy trong test. Nếu dự án cấu hình launcher hoặc scheduler theo cách riêng, cần vô hiệu hóa trigger tương ứng trong test profile.

## 7. Chọn JobParameters phù hợp cho từng test

`JobParameters` ảnh hưởng đến danh tính `JobInstance`. Nếu hai lần chạy dùng cùng job name và cùng identifying parameters, chúng thuộc cùng một instance. Khi instance đã hoàn tất, Spring Batch thường từ chối chạy lại nó như một job mới.

Có thể tạo tham số riêng cho từng lần test:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("requestId", UUID.randomUUID().toString(), true)
    .addString("businessDate", "2026-11-15", false)
    .toJobParameters();
```

Trong ví dụ này, `requestId` là identifying; `businessDate` là non-identifying. Cách đánh dấu trong bài test chỉ nhằm minh họa. Trong ứng dụng thực tế, các tham số identifying phải phản ánh đúng một đơn vị công việc nghiệp vụ.

Nếu muốn kiểm tra hành vi restart, không nên tạo identifying parameter mới ở lần chạy thứ hai. Hãy dùng lại cùng `JobParameters` cho cùng instance, làm cho lần đầu kết thúc ở trạng thái có thể restart, rồi kiểm tra execution tiếp theo theo quy tắc của job. Đây là một kịch bản riêng, cần cấu hình job test và dữ liệu sao cho có thể tái hiện thất bại có kiểm soát.

`launchJob()` không tham số có thể dùng bộ tham số duy nhất được utility tạo cho test. Khi cần xác minh logic dựa trên tham số cụ thể, nên truyền `JobParameters` rõ ràng để test thể hiện chính xác điều kiện đang kiểm tra.

## 8. Kiểm thử JobLauncher trực tiếp

`JobLauncherTestUtils` tiện lợi khi kiểm thử job, nhưng có thể inject `JobLauncher` và gọi trực tiếp nếu mục tiêu là xác nhận launcher nhận đúng job và tham số.

```java
@Autowired
JobLauncher jobLauncher;

@Autowired
@Qualifier("launcherTestJob")
Job launcherTestJob;

@Test
void launchesJobThroughConfiguredLauncher() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
        .addString("requestId", UUID.randomUUID().toString(), true)
        .toJobParameters();

    JobExecution execution = jobLauncher.run(launcherTestJob, parameters);

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    assertThat(execution.getJobInstance().getJobName())
        .isEqualTo("launcherTestJob");
}
```

Cách gọi trực tiếp cho thấy rõ hợp đồng của `JobLauncher`: nhận một đối tượng `Job` và `JobParameters`, trả về `JobExecution`. Test vẫn cần Spring context và repository phù hợp nếu muốn xác nhận tích hợp thật. Nếu chỉ mock `JobLauncher`, test chỉ xác minh cách một thành phần khác gọi launcher, không kiểm tra được transaction hay metadata repository.

Trong một test suite, nên chọn một cách khởi chạy chính cho từng mục tiêu. Dùng `JobLauncherTestUtils` khi cần các tiện ích Spring Batch và dùng `JobLauncher` trực tiếp khi cần kiểm tra API launcher ở mức tích hợp cụ thể.

## 9. Kiểm thử riêng một step bằng launchStep()

Đôi khi lỗi nằm trong reader, processor, writer hoặc tasklet chứ không nằm ở flow của toàn job. `JobLauncherTestUtils.launchStep("stepName")` giúp chạy một step riêng mà không phải thực thi tất cả step trước đó.

```java
@Test
void launchesOneStepForFocusedTest() throws Exception {
    JobExecution execution = jobLauncherTestUtils.launchStep("launcherTestStep");

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    assertThat(execution.getStepExecutions()).hasSize(1);

    StepExecution stepExecution = execution.getStepExecutions()
        .iterator()
        .next();

    assertThat(stepExecution.getStepName()).isEqualTo("launcherTestStep");
    assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
}
```

Utility tạo một job test tạm thời để chạy step được chỉ định. Vì vậy, `launchStep()` hữu ích cho việc kiểm tra hành vi của step trong batch infrastructure, nhưng không xác minh thứ tự step hoặc transition của job production. Muốn kiểm tra flow, hãy dùng `launchJob()` trên chính job cần kiểm thử.

Nếu step cần tham số hoặc execution context, dùng overload phù hợp của `launchStep(...)` để truyền dữ liệu đầu vào. Với step có `@StepScope`, `@SpringBatchTest` hỗ trợ cấu hình listener để scope được kích hoạt trong test context.

## 10. Kiểm tra kết quả của job execution

Một bài test launcher tốt nên kiểm tra nhiều khía cạnh của `JobExecution`, thay vì chỉ xác nhận method không ném exception.

| Thuộc tính | Điều cần xác nhận |
| --- | --- |
| `getStatus()` | Job kết thúc với `BatchStatus` mong đợi, chẳng hạn `COMPLETED` hoặc `FAILED`. |
| `getExitStatus()` | Exit code và mô tả phản ánh kết quả mà job thiết kế. |
| `getJobInstance().getJobName()` | Đúng job đã được yêu cầu khởi chạy. |
| `getJobParameters()` | Launcher đã sử dụng đúng tham số. |
| `getStepExecutions()` | Các step mong đợi đã được thực thi và có trạng thái phù hợp. |
| `getStartTime()` / `getEndTime()` | Execution có mốc thời gian phù hợp với trạng thái cuối. |

Ví dụ kiểm tra tham số:

```java
assertThat(execution.getJobParameters().getString("source"))
    .isEqualTo("launcher-test");
```

Với job nhiều step, có thể kiểm tra tập tên step đã chạy:

```java
assertThat(execution.getStepExecutions())
    .extracting(StepExecution::getStepName)
    .contains("validateStep", "importStep", "reportStep");
```

Nếu flow có nhánh, hãy kiểm tra đúng step của nhánh được chọn và xác nhận step của nhánh không được chọn không xuất hiện trong execution. Như vậy test mới xác nhận hành vi điều phối, không chỉ xác nhận job kết thúc thành công.

## 11. Kiểm thử job thất bại và kết quả lỗi

Một test job có thể được cấu hình để thất bại có chủ đích nhằm xác nhận launcher ghi nhận trạng thái lỗi. Ví dụ, một tasklet test có thể ném exception:

```java
@Bean
Step failingTestStep(JobRepository jobRepository,
                     PlatformTransactionManager transactionManager) {
    return new StepBuilder("failingTestStep", jobRepository)
        .tasklet((contribution, chunkContext) -> {
            throw new IllegalStateException("Expected test failure");
        }, transactionManager)
        .build();
}
```

Khi launcher chạy job chứa step này, framework thường trả về `JobExecution` có trạng thái `FAILED` sau khi ghi nhận lỗi. Test có thể kiểm tra:

```java
assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(execution.getAllFailureExceptions()).isNotEmpty();
```

Tùy `JobLauncher` và `TaskExecutor` được cấu hình đồng bộ hay bất đồng bộ, thời điểm trả về có thể khác nhau. Với launcher bất đồng bộ, test cần chờ execution hoàn tất theo một cơ chế đồng bộ có giới hạn thời gian trước khi kiểm tra trạng thái cuối. Không nên giả định một execution đã có trạng thái cuối ngay khi `run()` trả về nếu ứng dụng dùng executor bất đồng bộ.

Nếu kiểm tra exit status tùy chỉnh, hãy assertion chính xác mã kết thúc mà listener hoặc flow tạo ra. `BatchStatus.FAILED` và `ExitStatus.FAILED` thường đi cùng nhau khi có exception không xử lý, nhưng hai thuộc tính có vai trò riêng và có thể được tùy chỉnh độc lập.

## 12. Làm sạch dữ liệu test và cô lập metadata

Job test vẫn ghi metadata vào `JobRepository`. Nếu test dùng database dùng chung, các execution có thể ảnh hưởng đến những lần chạy sau hoặc đến test khác. Nên dùng database riêng cho test, chẳng hạn H2 trong bộ nhớ hoặc một schema test độc lập.

`JobRepositoryTestUtils` cung cấp các phương thức hỗ trợ xóa metadata execution trong môi trường test, ví dụ `removeJobExecutions()`. Có thể dùng tiện ích này để dọn dữ liệu giữa các test khi repository hoàn toàn thuộc quyền sở hữu của test suite.

```java
@Autowired
JobRepositoryTestUtils jobRepositoryTestUtils;

@AfterEach
void cleanUpBatchMetadata() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Chỉ dùng cách dọn này với repository test được cô lập. Không gọi `removeJobExecutions()` trên database production hoặc repository dùng chung với các job khác. Nếu test chạy song song hoặc chia sẻ database, việc xóa metadata có thể làm hỏng execution mà test khác đang sử dụng.

Một lựa chọn khác là dùng identifying parameters duy nhất cho mỗi test và chỉ dọn dữ liệu thuộc test đó bằng cơ chế phù hợp. Cần nhớ rằng xóa metadata không tự xóa dữ liệu nghiệp vụ do writer đã tạo; dữ liệu test ở bảng nghiệp vụ cũng cần được cô lập hoặc làm sạch riêng.

## 13. Kiểm thử với nhiều job trong cùng application context

Ứng dụng thực tế thường có nhiều bean `Job`. Trong trường hợp đó, không nên phụ thuộc vào việc Spring tự chọn một job duy nhất cho `JobLauncherTestUtils`. Hãy inject job cần test bằng `@Qualifier` và gọi `setJob()` trước khi launch:

```java
@Autowired
JobLauncherTestUtils jobLauncherTestUtils;

@Autowired
@Qualifier("dailyImportJob")
Job dailyImportJob;

@BeforeEach
void configureTargetJob() {
    jobLauncherTestUtils.setJob(dailyImportJob);
}
```

Nếu các test cùng dùng một instance utility và chạy song song trong cùng context, việc thay đổi job mục tiêu qua `setJob()` có thể tạo xung đột. Có thể tách test context theo job, dùng utility riêng hoặc không chạy song song những test chia sẻ cùng utility mutable.

Job test riêng là lựa chọn phù hợp khi chỉ cần kiểm tra cấu hình launcher hoặc một hành vi nhỏ. Khi mục tiêu là xác nhận job production được chọn và chạy đúng, hãy dùng chính bean production đó trong test với dữ liệu và database đã cô lập. Đừng để job test vô tình thay thế kiểm thử tích hợp của job thật.

## 14. Kiểm thử launcher bất đồng bộ

`JobLauncher` có thể được cấu hình với `TaskExecutor` để thực thi bất đồng bộ. Khi đó, lời gọi launcher có thể trả về `JobExecution` trước khi job hoàn tất. Test không nên assertion trạng thái cuối ngay lập tức nếu execution vẫn đang `STARTING` hoặc `STARTED`.

Một cách tiếp cận là chờ có giới hạn thời gian cho đến khi trạng thái chuyển sang trạng thái kết thúc, sau đó assertion. Ví dụ minh họa:

```java
JobExecution execution = jobLauncher.run(job, parameters);

long deadline = System.nanoTime() + Duration.ofSeconds(10).toNanos();
while (execution.isRunning() && System.nanoTime() < deadline) {
    Thread.sleep(50);
}

assertThat(execution.isRunning()).isFalse();
assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

Đây là minh họa đơn giản cho việc chờ một execution bất đồng bộ. Trong test suite cần độ ổn định cao, nên dùng cơ chế chờ có timeout phù hợp với dự án, tránh sleep dài hoặc vòng lặp không có giới hạn. Cũng cần lưu ý object `JobExecution` trong bộ nhớ có thể không phản ánh cập nhật mới nhất tùy cách launcher và repository cập nhật; có thể đọc lại execution bằng ID thông qua `JobExplorer` sau khi job hoàn tất.

Nếu không kiểm thử hành vi bất đồng bộ, dùng launcher đồng bộ trong test thường làm kết quả đơn giản và dễ tái hiện hơn. Tuy nhiên, khi production dùng executor bất đồng bộ, nên có ít nhất một kiểm thử tích hợp cho cấu hình đó.

## 15. Các lỗi thường gặp khi kiểm thử JobLauncher

**Không tìm thấy `JobLauncherTestUtils`:** kiểm tra dependency `spring-batch-test` và annotation `@SpringBatchTest`. Đảm bảo test chạy trong Spring context thay vì khởi tạo class test thuần JUnit.

**Utility không biết job cần chạy:** context có nhiều bean `Job` hoặc không có job được chọn. Inject đúng bean bằng `@Qualifier` và gọi `setJob()` trước khi launch.

**Job tự chạy khi context khởi tạo:** tắt auto-launch của Spring Boot bằng `spring.batch.job.enabled=false` trong cấu hình test và kiểm tra các scheduler tùy chỉnh.

**Lỗi duplicate instance hoặc instance đã hoàn tất:** kiểm tra job name và identifying parameters. Tạo identifying parameter riêng cho mỗi test nếu mục tiêu là một lần chạy mới; dùng lại tham số nếu đang kiểm tra restart.

**Không tìm thấy bảng metadata:** kiểm tra datasource test, schema script hoặc cấu hình khởi tạo schema phù hợp với phiên bản Spring Batch và database.

**Test phụ thuộc thứ tự:** dữ liệu metadata còn sót từ test trước hoặc các test dùng chung tham số. Dùng database test cô lập, tham số duy nhất và quy trình cleanup phù hợp.

**Test step pass nhưng job flow sai:** `launchStep()` chỉ kiểm tra step riêng lẻ. Dùng `launchJob()` để xác nhận các transition và thứ tự step của job thực tế.

**Assertion trạng thái quá sớm:** launcher bất đồng bộ có thể trả về trước khi job kết thúc. Chờ execution với timeout và đọc lại trạng thái sau khi hoàn tất.

## 16. Cách tổ chức một bộ kiểm thử launcher có ích

Một bộ test có thể bắt đầu bằng một job test nhỏ để xác nhận launcher, repository và transaction manager hoạt động. Sau đó, bổ sung các trường hợp theo hành vi cần bảo vệ:

1. **Khởi chạy thành công:** xác nhận đúng job, tham số, step execution và trạng thái kết thúc.
2. **Tham số đầu vào:** xác nhận identifying và non-identifying parameters được truyền và xử lý đúng.
3. **Nhánh flow:** xác nhận exit status hoặc decider đưa job đến đúng step.
4. **Thất bại:** xác nhận lỗi được ghi nhận và trạng thái execution phù hợp.
5. **Restart:** xác nhận cùng job instance có thể tiếp tục sau thất bại theo thiết kế.
6. **Nhiều job:** xác nhận test utility khởi chạy đúng bean khi context có nhiều job.
7. **Cấu hình executor:** nếu production dùng launcher bất đồng bộ, xác nhận test có thể quan sát trạng thái cuối một cách đáng tin cậy.

Mỗi test nên dùng dữ liệu nghiệp vụ có thể kiểm soát và xác nhận kết quả ở cả metadata lẫn nơi lưu dữ liệu đích khi điều đó thuộc phạm vi kiểm thử. Không nên chỉ kiểm tra `BatchStatus.COMPLETED` nếu mục tiêu của job còn bao gồm việc ghi đúng số bản ghi hoặc chọn đúng nhánh nghiệp vụ.

Kiểm thử launcher với job test giúp xác nhận đường đi từ yêu cầu khởi chạy đến `JobExecution` và `StepExecution` trong Spring Batch. Khi dùng `JobLauncherTestUtils`, chọn rõ job, tạo `JobParameters` phù hợp, cô lập metadata repository và assertion trạng thái cùng kết quả step, test có thể kiểm tra cấu hình batch một cách lặp lại và dễ chẩn đoán.
