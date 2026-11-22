# Chạy job test với `JobParameters` trong Spring Batch

Trong Spring Batch, cùng một `Job` có thể xử lý những bộ dữ liệu khác nhau tùy vào các tham số được truyền lúc khởi chạy. Vì vậy, kiểm thử batch không chỉ dừng ở việc xác nhận job chạy thành công: bài test cần truyền đúng `JobParameters`, kiểm tra job đã nhận tham số nào, quan sát kết quả xử lý và hiểu điều gì xảy ra khi chạy lại với cùng bộ tham số.

Bài học này sử dụng **Spring Batch 5.x, Spring Boot 3.x và JUnit 5**. Trọng tâm là kiểm thử tích hợp với `@SpringBatchTest`, `JobLauncherTestUtils` và `JobParametersBuilder`.

## 1. `JobParameters` có vai trò gì trong một bài test?

`JobParameters` là tập các cặp tên–giá trị được truyền cho một lần chạy job. Ví dụ, job lập báo cáo có thể nhận:

| Tên tham số | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `businessDate` | `2026-11-16` | Ngày nghiệp vụ cần xử lý |
| `region` | `VN` | Khu vực cần lập báo cáo |
| `run.id` | `test-001` | Phân biệt các lần chạy độc lập khi cần |

Một bài test điển hình thực hiện chuỗi sau:

```text
JUnit test
  └── Tạo JobParameters
        └── JobLauncherTestUtils.launchJob(parameters)
              └── JobLauncher → JobRepository → Job
                    └── Step → Reader / Processor / Writer hoặc Tasklet
              └── JobExecution
                    ├── BatchStatus / ExitStatus
                    ├── JobParameters thực tế
                    ├── StepExecutions
                    └── Kết quả quan sát được
```

Cần phân biệt ba khái niệm:

- **`Job`**: định nghĩa luồng công việc, ví dụ `reportJob`.
- **`JobInstance`**: một phiên bản công việc xác định bởi **tên job và các tham số có thuộc tính `identifying=true`**.
- **`JobExecution`**: một lần cố gắng thực thi `JobInstance`. Một instance có thể có nhiều execution trong tình huống thất bại rồi chạy lại (restart), nhưng một instance đã hoàn thành thông thường không được chạy lại.

Do đó, việc thay đổi `JobParameters` có thể tạo `JobInstance` mới hoặc vẫn trỏ vào instance cũ, tùy **tham số nào là identifying**. Đây là điểm dễ gây lỗi nhất khi viết test.

## 2. Chuẩn bị môi trường kiểm thử

Với dự án Spring Boot đã sử dụng `spring-boot-starter-batch`, bổ sung các dependency kiểm thử (ví dụ Gradle):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Spring Boot quản lý phiên bản dependency tương thích khi sử dụng BOM/plugin tương ứng. H2 ở đây là một cơ sở dữ liệu thử nghiệm để lưu metadata của Spring Batch; ứng dụng dùng cơ sở dữ liệu khác có thể thay bằng một test database hoặc Testcontainers riêng.

Trong test, cần lưu ý hai cấu hình:

```properties
spring.batch.job.enabled=false
spring.batch.jdbc.initialize-schema=always
```

- `spring.batch.job.enabled=false`: ngăn Spring Boot tự chạy job ngay khi test context khởi tạo; test sẽ chủ động gọi `launchJob(...)`.
- `spring.batch.jdbc.initialize-schema=always`: tạo các bảng metadata `BATCH_*` trong database kiểm thử. Chỉ dùng khi phù hợp với cách quản lý schema của môi trường test; nếu schema đã do migration/Testcontainers chuẩn bị thì không cần bật.

`@SpringBatchTest` cung cấp các tiện ích như `JobLauncherTestUtils` và `JobRepositoryTestUtils`, đồng thời đăng ký hỗ trợ test cho bean sử dụng job/step scope. `@SpringBootTest` nạp application context để chạy kiểm thử tích hợp thực tế.

## 3. Một job mẫu nhận tham số lúc chạy

Giả sử có `reportJob` nhận `businessDate` và `region`. Để tập trung vào cơ chế truyền tham số, step mẫu sẽ kiểm tra đầu vào rồi ghi thông tin đã xử lý vào `ExecutionContext` của job. Trong ứng dụng thực tế, step có thể đọc file, truy vấn dữ liệu, gọi processor hoặc ghi vào database.

```java
package com.example.batch;

import java.time.LocalDate;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ReportJobConfig {

    @Bean
    public Job reportJob(JobRepository jobRepository, Step reportStep) {
        return new JobBuilder("reportJob", jobRepository)
                .start(reportStep)
                .build();
    }

    @Bean
    public Step reportStep(JobRepository jobRepository,
                           PlatformTransactionManager transactionManager,
                           Tasklet reportTasklet) {
        return new StepBuilder("reportStep", jobRepository)
                .tasklet(reportTasklet, transactionManager)
                .build();
    }

    @Bean
    @StepScope
    public Tasklet reportTasklet(
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{jobParameters['region']}") String region) {

        return (contribution, chunkContext) -> {
            if (businessDate == null || businessDate.isBlank()) {
                throw new IllegalArgumentException("businessDate is required");
            }
            if (region == null || region.isBlank()) {
                throw new IllegalArgumentException("region is required");
            }

            // Kiểm tra định dạng yyyy-MM-dd; ngày không hợp lệ sẽ làm step FAILED.
            String normalizedDate = LocalDate.parse(businessDate).toString();

            JobExecution execution = contribution.getStepExecution()
                    .getJobExecution();
            execution.getExecutionContext()
                    .putString("processedDate", normalizedDate);
            execution.getExecutionContext()
                    .putString("processedRegion", region);

            return RepeatStatus.FINISHED;
        };
    }
}
```

Điểm mấu chốt là `@StepScope`. Bean `reportTasklet` phải được tạo theo **lần thực thi step** thì biểu thức `#{jobParameters['...']}` mới lấy được giá trị của job đang chạy. Nếu bỏ scope rồi cố gắng đọc job parameter ngay lúc application context khởi tạo, quá trình late binding có thể thất bại hoặc không có giá trị đúng. Tên trong biểu thức phải khớp chính xác với tên tham số test truyền vào.

Trong ví dụ trên, ghi vào `ExecutionContext` giúp bài học có một kết quả dễ quan sát. `ExecutionContext` vốn chủ yếu phục vụ trạng thái xử lý và restart của batch; với job sản xuất, test nên ưu tiên kiểm tra **đầu ra nghiệp vụ thực sự** như bản ghi database, file xuất hoặc số lượng item đã ghi.

## 4. Viết integration test với tham số cụ thể

Giả định ứng dụng có lớp `@SpringBootApplication` quét được `ReportJobConfig` và có test datasource. Bài test sau chủ động chọn job, dựng bộ tham số, chạy và kiểm tra cả trạng thái lẫn giá trị được truyền tới step.

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
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
})
class ReportJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    @Qualifier("reportJob")
    private Job reportJob;

    @BeforeEach
    void setUp() {
        // Nêu rõ job cần test, đặc biệt khi context có nhiều Job.
        jobLauncherTestUtils.setJob(reportJob);

        // Chỉ xóa metadata trên database test riêng biệt.
        jobRepositoryTestUtils.removeJobExecutions();
    }

    @Test
    void runsJobWithBusinessParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .addString("region", "VN")
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getExitStatus().getExitCode())
                .isEqualTo("COMPLETED");
        assertThat(execution.getJobParameters().getString("businessDate"))
                .isEqualTo("2026-11-16");
        assertThat(execution.getJobParameters().getString("region"))
                .isEqualTo("VN");

        // Chứng minh step thực sự đọc và xử lý các tham số.
        assertThat(execution.getExecutionContext().getString("processedDate"))
                .isEqualTo("2026-11-16");
        assertThat(execution.getExecutionContext().getString("processedRegion"))
                .isEqualTo("VN");
    }

    @Test
    void failsWhenRegionIsMissing() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .addString("run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
        assertThat(execution.getAllFailureExceptions())
                .anySatisfy(error -> assertThat(error)
                        .isInstanceOf(IllegalArgumentException.class));
    }
}
```

### Vì sao các dòng trong bài test quan trọng?

1. `new JobParametersBuilder()` tạo bộ dữ liệu đầu vào mới; `.addString(...)` bổ sung tham số kiểu `String` và `.toJobParameters()` tạo đối tượng `JobParameters`.
2. `jobLauncherTestUtils.setJob(reportJob)` tránh chọn nhầm job nếu context có nhiều bean kiểu `Job`.
3. `launchJob(parameters)` thực thi toàn bộ job bằng đúng bộ tham số truyền vào và trả về `JobExecution` để kiểm tra.
4. Kiểm tra `BatchStatus.COMPLETED` xác nhận job kết thúc thành công; kiểm tra `ExecutionContext` cho thấy tham số đã ảnh hưởng đến bước xử lý, vượt ra ngoài việc chỉ xác nhận đối tượng đầu vào.
5. Test thiếu `region` minh họa **lỗi phát sinh bên trong step**, nên `JobExecution` tồn tại và có trạng thái `FAILED`. Nếu dùng `JobParametersValidator` từ đầu job, tham số không hợp lệ có thể khiến `launchJob(...)` ném `JobParametersInvalidException` ngay trước khi chạy step; test cần bắt exception phù hợp thay vì luôn mong đợi `FAILED`.

`JobLauncherTestUtils` thường chạy đồng bộ với cấu hình `JobLauncher` mặc định. Nếu hệ thống cấu hình launcher bất đồng bộ, việc nhận được `JobExecution` không nhất thiết có nghĩa job đã kết thúc; khi đó cần cơ chế chờ hoàn thành có timeout trước khi assert kết quả.

## 5. Phân biệt identifying và non-identifying parameters

Trong `JobParametersBuilder`, overload cuối cùng cho phép chỉ định một tham số có tham gia xác định `JobInstance` hay không:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("region", "VN", true)
        .addString("traceId", "trace-A", false)
        .toJobParameters();
```

Hai tham số `businessDate` và `region` ở đây là `identifying=true`. `traceId` là `identifying=false`, nên thay `traceId` **không** tạo một `JobInstance` mới. Khi bỏ đối số `identifying`, các phương thức `addString`, `addLong` ... mặc định dùng `true`.

Giả sử tên job luôn là `reportJob`:

| Lần chạy | `businessDate` | `region` | `traceId` (`identifying=false`) | Hệ quả |
| --- | --- | --- | --- | --- |
| A | `2026-11-16` | `VN` | `trace-A` | Instance thứ nhất |
| B | `2026-11-16` | `VN` | `trace-B` | **Vẫn là instance của A** |
| C | `2026-11-17` | `VN` | `trace-C` | Instance mới |
| D | `2026-11-16` | `SG` | `trace-D` | Instance mới |

Nếu A đã `COMPLETED`, việc thử B thường dẫn tới `JobInstanceAlreadyCompleteException`, bởi instance đó đã hoàn thành. Đổi một tham số non-identifying không giúp chạy lại job đã xong.

Trong các test cần chạy job nhiều lần độc lập, có thể dùng `run.id` identifying với giá trị duy nhất:

```java
private JobParameters paramsFor(String date, String region) {
    return new JobParametersBuilder()
            .addString("businessDate", date)
            .addString("region", region)
            .addString("run.id", UUID.randomUUID().toString())
            .toJobParameters();
}
```

Tuy nhiên, **không được đổi `run.id` khi đang kiểm thử restart của cùng một instance**: việc đổi identifying parameter sẽ tạo instance mới và khiến test không còn kiểm tra hành vi restart. Khi test restart, hãy giữ nguyên các identifying parameters và tạo lần chạy tiếp theo trên instance đã `FAILED` hoặc `STOPPED` theo chính sách restart của job.

## 6. Những kịch bản test cần có

Tùy nghiệp vụ, có thể bao phủ các lớp tình huống sau:

| Kịch bản | Cách truyền tham số | Điều cần xác nhận |
| --- | --- | --- |
| Dữ liệu hợp lệ | Đủ `businessDate`, `region` | Job `COMPLETED` và tạo đúng kết quả |
| Thiếu bắt buộc | Bỏ `region` | Validator từ chối hoặc step `FAILED` như thiết kế |
| Sai định dạng | `businessDate=not-a-date` | Lỗi parse/validation được xử lý đúng |
| Đổi dữ liệu đầu vào | Chạy với các `region` khác nhau | Đầu ra thay đổi tương ứng, không bị dùng nhầm giá trị giữa lần chạy |
| Chạy lại tham số cũ | Giữ toàn bộ identifying parameters | Hoạt động restart/ràng buộc instance đúng với trạng thái trước đó |
| Tham số non-identifying | Chỉ đổi `traceId` | Không tạo instance mới |
| Nhiều job cùng context | Gọi `setJob(...)` rõ ràng | Test chạy đúng job dự định |

### Kiểm tra cùng một bộ tham số sau khi job hoàn thành

Trong **một test riêng**, bỏ thao tác xóa metadata giữa hai lần launch và sử dụng lại chính đối tượng `JobParameters`:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .addString("region", "VN")
        .addString("run.id", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution first = jobLauncherTestUtils.launchJob(parameters);
assertThat(first.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThrows(JobInstanceAlreadyCompleteException.class,
        () -> jobLauncherTestUtils.launchJob(parameters));
```

Đoạn trên giả định job hoàn thành thành công và repository vẫn lưu metadata của lần chạy đầu. Test này khẳng định quy tắc nhận diện instance, không phải hành vi xử lý dữ liệu lần thứ hai.

### Kiểm tra đầu ra nghiệp vụ thay vì chỉ trạng thái

Với một job ghi database hoặc xuất file, phép assert quan trọng nhất thường nằm ở kết quả bên ngoài `JobExecution`. Ví dụ, nếu job ghi các bản ghi báo cáo vào repository:

```java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(reportRepository.findByBusinessDateAndRegion(
        LocalDate.parse("2026-11-16"), "VN"))
        .hasSize(3);
```

Đây là **mẫu assert minh họa**: `reportRepository` và phương thức truy vấn là thành phần nghiệp vụ cần có trong dự án thực tế, không thuộc API có sẵn của Spring Batch. Tương tự, khi test chunk-oriented step, có thể kiểm tra thêm các chỉ số trên `StepExecution` (`getReadCount()`, `getWriteCount()`, `getSkipCount()`) nếu phù hợp.

## 7. Dùng `launchStep(...)` khi chỉ cần kiểm tra một step

`JobLauncherTestUtils` còn có thể chạy một step cụ thể của job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .addString("region", "VN")
        .addString("run.id", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution execution =
        jobLauncherTestUtils.launchStep("reportStep", parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

`launchStep` phù hợp để cô lập một step, nhưng chạy step qua cơ chế job kiểm thử do framework tạo ra. Vì vậy, kết quả của nó không đại diện đầy đủ cho thứ tự, điều kiện chuyển bước, listener cấp job hay luồng restart của toàn bộ `reportJob`. Nếu bài test cần đánh giá các quan hệ đó, hãy dùng `launchJob(parameters)`.

## 8. Quản lý dữ liệu test và metadata để tránh test ảnh hưởng lẫn nhau

Spring Batch lưu lịch sử job trong các bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_JOB_EXECUTION_PARAMS`, `BATCH_STEP_EXECUTION` và các bảng liên quan. Điều này làm cho test có trạng thái ngay cả khi logic nghiệp vụ chỉ đọc/ghi dữ liệu đơn giản.

Có hai chiến lược phổ biến:

1. **Cô lập repository test:** mỗi suite/test có database riêng, chuẩn bị schema và dữ liệu test độc lập; có thể dùng `jobRepositoryTestUtils.removeJobExecutions()` trong `@BeforeEach` khi chắc chắn database chỉ dành cho test. Phương thức này xóa lịch sử thực thi batch, vì vậy không được gọi vào repository đang dùng chung với môi trường thật hoặc test song song khác.
2. **Tạo identifying parameters duy nhất:** thêm `run.id` cho các trường hợp muốn tạo instance mới. Cách này tránh va chạm định danh nhưng **không tự dọn** lịch sử batch, dữ liệu nghiệp vụ hay file xuất; vẫn cần chiến lược cleanup phù hợp.

Nếu test chạy song song trên cùng database, việc một test xóa metadata của test khác sẽ gây lỗi khó tái hiện. Khi đó nên dùng database/schema riêng hoặc kiểm soát tính song song, thay vì xóa toàn bộ repository một cách không phân biệt.

`@Transactional` ở phương thức JUnit cũng không mặc nhiên rollback được toàn bộ công việc batch vì job/step có thể sử dụng transaction độc lập. Hãy xác định rõ nơi cần cleanup dữ liệu và dùng test database cô lập.

## 9. Các lỗi thường gặp khi test với `JobParameters`

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `JobInstanceAlreadyCompleteException` | Chạy job đã hoàn thành với cùng identifying parameters | Dùng instance mới cho test độc lập; giữ nguyên tham số nếu cố ý kiểm tra ràng buộc chạy lại |
| `JobExecutionAlreadyRunningException` | Một execution của instance vẫn đang chạy | Kiểm tra launcher bất đồng bộ, trạng thái repository và cơ chế chờ hoàn thành |
| `JobParametersInvalidException` | Validator của job từ chối tham số | Kiểm tra tên, kiểu, điều kiện bắt buộc; assert exception ở ranh giới launch |
| Step không đọc được tham số | Sai tên key, thiếu `@StepScope`, cấu hình scope chưa phù hợp | Đối chiếu `addString("name", ...)` với `#{jobParameters['name']}` |
| Job tự chạy khi context khởi tạo | Spring Boot tự kích hoạt job | Đặt `spring.batch.job.enabled=false` trong test |
| `JobRepository` báo thiếu bảng `BATCH_*` | Schema metadata chưa có | Tạo schema riêng cho test hoặc bật initialize-schema ở test datasource |
| Assert `COMPLETED` nhưng dữ liệu sai | Test mới kiểm tra trạng thái kỹ thuật | Assert bản ghi/file/số lượng item và giá trị nghiệp vụ thực sự |
| Test chỉ chạy tốt khi chạy riêng | Metadata hoặc dữ liệu từ test khác còn sót | Cô lập datasource, dọn dữ liệu đúng phạm vi và kiểm soát parallel execution |

**Lưu ý về phiên bản:** Các ví dụ trên dùng API Spring Batch 5 (`JobBuilder` nhận `JobRepository`, `StepBuilder` nhận `JobRepository`, tasklet step nhận `PlatformTransactionManager`). Nếu dự án còn dùng Spring Batch 4, cách cấu hình builder và một số chi tiết về tham số có thể khác; nên dùng API đúng với phiên bản của dự án.

## 10. Bài thực hành tự áp dụng

Hãy dùng `reportJob` ở trên để thực hiện lần lượt các thao tác sau:

1. Chạy với `businessDate=2026-11-16`, `region=VN` và một `run.id` mới; xác nhận job hoàn thành và `processedRegion=VN`.
2. Giữ ngày nhưng đổi `region=SG` và dùng `run.id` mới; xác nhận kết quả step tương ứng là `SG`.
3. Bỏ `businessDate`, sau đó truyền `businessDate=16/11/2026`; với mỗi tình huống, xác nhận lỗi xảy ra đúng chỗ thiết kế.
4. Chạy job hoàn thành hai lần với **cùng** identifying parameters trong cùng một test, không xóa repository giữa hai lần; quan sát exception của lần chạy thứ hai.
5. Thêm tham số `traceId` với `identifying=false`; thử đổi duy nhất `traceId` và giải thích vì sao việc đổi này không tạo instance mới.

Khi triển khai một job thực tế, nguyên tắc cần giữ là: **test truyền tham số có chủ đích, xác nhận `JobInstance` được nhận diện đúng, kiểm tra trạng thái thực thi và kiểm tra cả kết quả nghiệp vụ do tham số đó tạo ra**. Cách kiểm thử này giúp phát hiện các lỗi mà một test chỉ gọi `launchJob()` rồi assert `COMPLETED` thường bỏ sót.
