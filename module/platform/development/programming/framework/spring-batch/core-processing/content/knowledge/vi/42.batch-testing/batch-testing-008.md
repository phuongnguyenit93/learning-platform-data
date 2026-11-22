# Assert `JobExecution` status khi kiểm thử Spring Batch

Trong Spring Batch, chạy được một `Job` chưa đủ để kết luận quy trình đã thành công. Bài kiểm thử cần lấy `JobExecution` của **lần chạy cụ thể**, đối chiếu trạng thái thực tế với kết quả mong đợi và, khi cần, kiểm tra cả trạng thái của từng `Step` cùng dữ liệu đầu ra. Đây là trọng tâm của thao tác **assert `JobExecution` status** trong nhóm chủ đề *Testing batch*.

Sau bài này, bạn có thể kiểm tra một job thành công, một job thất bại có chủ đích, phân biệt `BatchStatus` với `ExitStatus` và tránh các phép assert cho kết quả sai khi test chạy nhiều lần.

## 1. `JobExecution` phản ánh điều gì?

Một `Job` là định nghĩa công việc, ví dụ `importCustomersJob`. `JobInstance` là một lần xử lý logic được xác định bởi tên job và các **identifying job parameters**. `JobExecution` là **một lần thực thi** của `JobInstance` đó; nếu job lỗi rồi được restart, một `JobInstance` có thể có nhiều `JobExecution`.

`JobExecution` mang các thông tin hữu ích cho kiểm thử:

| Thuộc tính | API | Ý nghĩa khi kiểm thử |
| --- | --- | --- |
| Trạng thái thực thi | `getStatus()` | Trả về enum `BatchStatus`, ví dụ `COMPLETED` hoặc `FAILED`. |
| Mã kết thúc | `getExitStatus().getExitCode()` | Trả về chuỗi, mặc định thường là `COMPLETED`/`FAILED`; có thể được tùy biến. |
| Chi tiết kết thúc | `getExitStatus().getExitDescription()` | Thông tin bổ sung để chẩn đoán kết quả. |
| Thời điểm bắt đầu/kết thúc | `getStartTime()`, `getEndTime()` | Hỗ trợ nhận biết một lần chạy đã kết thúc. |
| Lỗi của job và step | `getAllFailureExceptions()` | Tập hợp ngoại lệ gây lỗi, gồm ngoại lệ ở các step. |
| Các lần chạy step | `getStepExecutions()` | Kiểm tra step nào chạy, kết quả và số lượng bản ghi xử lý. |

Ví dụ một lần chạy thành công:

```text
Job: importCustomersJob
  JobInstance: importCustomersJob + {inputFile=customers.csv}
    JobExecution #42
      status: COMPLETED
      exitCode: COMPLETED
      StepExecution(validateFileStep): COMPLETED
      StepExecution(importRowsStep): COMPLETED
```

**Cần lấy trạng thái của đúng `JobExecution` vừa chạy.** Một job từng thành công trong quá khứ không chứng minh lần chạy hiện tại thành công.

## 2. `BatchStatus` và `ExitStatus` khác nhau ra sao?

`BatchStatus` là trạng thái vận hành do Spring Batch quản lý. Các giá trị thường gặp:

| `BatchStatus` | Diễn giải | Cách dùng trong assert |
| --- | --- | --- |
| `STARTING`, `STARTED` | Job đang khởi động hoặc thực thi. | Chưa thể khẳng định job đã hoàn tất. |
| `STOPPING` | Đang xử lý yêu cầu dừng. | Chưa phải trạng thái dừng cuối cùng. |
| `COMPLETED` | Job hoàn tất thành công theo điều kiện luồng công việc. | `isEqualTo(BatchStatus.COMPLETED)` |
| `FAILED` | Job kết thúc do thất bại. | `isEqualTo(BatchStatus.FAILED)` |
| `STOPPED` | Job đã dừng. | `isEqualTo(BatchStatus.STOPPED)` |
| `ABANDONED` | Thực thi bị bỏ, thường không thể restart theo cơ chế thông thường. | Chỉ mong đợi trong kịch bản được thiết kế rõ. |
| `UNKNOWN` | Không xác định chắc chắn trạng thái. | Thường cần điều tra metadata và hạ tầng. |

`ExitStatus` là kết quả kết thúc có **exit code** (kiểu `String`) và phần mô tả. Nó hỗ trợ phân nhánh luồng và trao đổi kết quả với bên ngoài. Ví dụ:

```java
assertThat(execution.getStatus())
        .isEqualTo(BatchStatus.COMPLETED);

assertThat(execution.getExitStatus().getExitCode())
        .isEqualTo(ExitStatus.COMPLETED.getExitCode());
```

Hai phép assert kiểm tra hai ý khác nhau:

- `getStatus()` xác nhận trạng thái thực thi của job.
- `getExitStatus().getExitCode()` xác nhận **mã kết thúc** mà job công bố.

Một job có thể có `BatchStatus.COMPLETED` nhưng exit code tùy chỉnh như `COMPLETED_WITH_WARNINGS` do listener hoặc cấu hình flow đặt ra. Khi đó assert `COMPLETED` cho `BatchStatus` vẫn đúng, còn assert exit code phải theo hợp đồng thực tế. Khi so sánh mã lỗi, thường chỉ cần `getExitCode()`: so sánh cả đối tượng `ExitStatus` có thể nhạy với `exitDescription` khác nhau.

## 3. Chuẩn bị môi trường kiểm thử

Dùng **JUnit Jupiter**, **AssertJ** và thư viện `spring-batch-test`. Trong ứng dụng Spring Boot, project thường cần các dependency test tương ứng:

```groovy
// Ví dụ trong build.gradle; các phiên bản do Spring Boot/BOM quản lý.
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.batch:spring-batch-test'
```

Bài test tích hợp cần có `ApplicationContext` chứa job, `JobRepository` và hạ tầng Spring Batch. Nên dùng cơ sở dữ liệu test riêng (chẳng hạn H2 hoặc test database chuyên dụng), với schema batch phù hợp phiên bản. `@SpringBatchTest` cung cấp các tiện ích khởi chạy và kiểm tra batch. `@SpringBootTest` nạp ngữ cảnh ứng dụng; nếu không sử dụng Spring Boot, có thể dùng `@SpringJUnitConfig` với cấu hình Spring thích hợp.

Ví dụ chính dưới đây dùng **Spring Batch 6.x**; mục 7 đưa ra biến thể cho **Spring Batch 5.x**, vì gói Java và công cụ test khác nhau giữa hai dòng phiên bản.

## 4. Assert job chạy thành công với Spring Batch 6.x

Giả sử ứng dụng đã có bean `Job` tên `importCustomersJob`. Test sau khởi chạy job với một tham số xác định duy nhất cho mỗi lần chạy và kiểm tra kết quả:

```java
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.JobExecution;
import org.springframework.batch.core.job.parameters.JobParameters;
import org.springframework.batch.core.job.parameters.JobParametersBuilder;
import org.springframework.batch.test.JobOperatorTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportCustomersJobStatusTest {

    @Autowired
    private JobOperatorTestUtils jobOperatorTestUtils;

    @Autowired
    @Qualifier("importCustomersJob")
    private Job importCustomersJob;

    @BeforeEach
    void selectJob() {
        // Chọn đúng job nếu application context có nhiều Job bean.
        jobOperatorTestUtils.setJob(importCustomersJob);
    }

    @Test
    void shouldCompleteSuccessfully() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobOperatorTestUtils.startJob(parameters);

        assertThat(execution.getStatus())
                .as("Trạng thái thực thi của importCustomersJob")
                .isEqualTo(BatchStatus.COMPLETED);

        assertThat(execution.getExitStatus().getExitCode())
                .as("Mã kết thúc của importCustomersJob")
                .isEqualTo(ExitStatus.COMPLETED.getExitCode());

        assertThat(execution.getEndTime())
                .as("Thời điểm job kết thúc")
                .isNotNull();
    }
}
```

Giải thích chuỗi thao tác:

1. `setJob(importCustomersJob)` bảo đảm tiện ích chạy đúng bean `Job` cần kiểm thử.
2. `testRunId` là tham số **identifying** theo mặc định. Giá trị mới tạo một `JobInstance` riêng, tránh đụng với lần chạy `COMPLETED` trước đó trong `JobRepository`.
3. `startJob(parameters)` trả về một `JobExecution` để test đọc kết quả.
4. `getStatus()` là assert chính của bài; `getExitCode()` và `getEndTime()` là các điều kiện bổ sung, tùy yêu cầu nghiệp vụ.

Thuộc tính `spring.batch.job.enabled=false` ngăn cơ chế tự khởi chạy job khi Spring Boot khởi tạo test context. Khi chạy bộ test, phải bảo đảm fixture (dữ liệu nhập, file, database) được thiết lập đúng để `importCustomersJob` thực sự có thể thành công; tham số `testRunId` chỉ giúp phân biệt lần chạy, không thay thế tham số nghiệp vụ mà job yêu cầu.

> **Ghi chú:** Nếu `startJob(...)` trả về trước khi job kết thúc do launcher/operator được cấu hình bất đồng bộ, `getStatus()` có thể vẫn là `STARTING` hoặc `STARTED`. Với test tích hợp thông thường, ưu tiên cấu hình thực thi đồng bộ. Nếu yêu cầu chạy bất đồng bộ, hãy chờ trạng thái cuối bằng cơ chế polling có timeout, đọc lại `JobExecution` từ repository/explorer; đừng dùng `Thread.sleep(...)` cố định rồi đoán job đã xong.

## 5. Assert job thất bại một cách có chủ đích

Một test đường lỗi cần tạo **đầu vào hoặc step gây lỗi có thể tái hiện**, rồi kiểm tra rằng `JobExecution` kết thúc ở `FAILED`. Ví dụ có bean `failingProbeJob` gồm một step ném `IllegalStateException` với thông báo `invalid-record`. Test sau xác nhận cả trạng thái, exit code lẫn nguyên nhân:

```java
@Test
void shouldFailForInvalidRecord() throws Exception {
    jobOperatorTestUtils.setJob(failingProbeJob);

    JobParameters parameters = new JobParametersBuilder()
            .addString("testRunId", UUID.randomUUID().toString())
            .toJobParameters();

    JobExecution execution = jobOperatorTestUtils.startJob(parameters);

    assertThat(execution.getStatus())
            .isEqualTo(BatchStatus.FAILED);

    assertThat(execution.getExitStatus().getExitCode())
            .isEqualTo(ExitStatus.FAILED.getExitCode());

    assertThat(execution.getAllFailureExceptions())
            .anySatisfy(error -> assertThat(error)
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("invalid-record"));
}
```

Đoạn này đặt trong test class đã cấu hình `@SpringBatchTest`/`@SpringBootTest` như mục 4, có thêm field `@Autowired @Qualifier("failingProbeJob") Job failingProbeJob`. Test fixture có thể định nghĩa step gây lỗi rõ ràng:

```java
@Bean("failingProbeStep")
Step failingProbeStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {
    return new StepBuilder("failingProbeStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                throw new IllegalStateException("invalid-record");
            }, transactionManager)
            .build();
}

@Bean("failingProbeJob")
Job failingProbeJob(
        JobRepository jobRepository,
        @Qualifier("failingProbeStep") Step failingProbeStep) {
    return new JobBuilder("failingProbeJob", jobRepository)
            .start(failingProbeStep)
            .build();
}
```

Các `@Bean` này nằm trong lớp `@TestConfiguration` được nạp vào test context, không nhất thiết nằm trong cấu hình production. Với Spring Batch 6, `Job` và `Step` được import từ `org.springframework.batch.core.job.Job` và `org.springframework.batch.core.step.Step`; `JobBuilder` và `StepBuilder` lần lượt thuộc gói `...core.job.builder` và `...core.step.builder`. `JobRepository` thuộc `...core.repository`.

**Không dùng `assertThatThrownBy(() -> startJob(...))` để thay cho assert `FAILED`.** Khi lỗi xảy ra trong một step và được framework quản lý, phương thức khởi chạy vẫn có thể trả về `JobExecution` chứa trạng thái `FAILED`. Ngoại lệ phát sinh ngay lúc khởi chạy (ví dụ tham số không hợp lệ, job instance đã hoàn tất hoặc không tìm thấy job) là một nhóm kịch bản kiểm thử khác.

Nếu ứng dụng cố ý bắt và *skip* các bản ghi lỗi, job vẫn có thể `COMPLETED`. Khi đó cần assert `COMPLETED` và số bản ghi skip, thay vì mặc định mọi ngoại lệ bên trong xử lý đều phải làm job `FAILED`.

## 6. Assert thêm từng `StepExecution` và kết quả nghiệp vụ

Job `COMPLETED` xác nhận điều kiện kết thúc của flow, nhưng chưa cho biết job đã xử lý đúng dữ liệu hay chưa. Với job nhập dữ liệu, có thể kiểm tra step cụ thể và số lượng bản ghi:

```java
JobExecution execution = jobOperatorTestUtils.startJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

var importStep = execution.getStepExecutions().stream()
        .filter(step -> "importRowsStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow(() -> new AssertionError(
                "Không tìm thấy StepExecution của importRowsStep"));

assertThat(importStep.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(importStep.getReadCount()).isEqualTo(10);
assertThat(importStep.getWriteCount()).isEqualTo(10);
assertThat(importStep.getSkipCount()).isZero();
```

Số `10` chỉ là ví dụ tương ứng với fixture có đúng 10 bản ghi hợp lệ. Với job có **flow rẽ nhánh**, một step có thể được bỏ qua có chủ đích; không nên ép mọi step được định nghĩa đều phải xuất hiện. Với chunk processing có **lọc (filter)**, `readCount` và `writeCount` cũng không nhất thiết bằng nhau.

Tốt hơn nữa, assert dữ liệu đã ghi vào database hoặc file đầu ra:

```java
assertThat(customerRepository.count()).isEqualTo(10);
```

Phép assert này xác nhận tác động của job. Cần chuẩn bị dữ liệu và cô lập kho lưu trữ trước mỗi test để con số không bị ảnh hưởng bởi các lần chạy khác.

## 7. Nếu dự án dùng Spring Batch 5.x

Trong **Spring Batch 5.x**, công cụ thông dụng là `JobLauncherTestUtils.launchJob(...)`, còn Spring Batch 6 giới thiệu `JobOperatorTestUtils.startJob(...)`; `JobLauncherTestUtils` đã được đánh dấu deprecated trong API 6.x.

Các import chính cũng thay đổi:

| Thành phần | Spring Batch 5.x | Spring Batch 6.x |
| --- | --- | --- |
| `Job`, `JobExecution` | `org.springframework.batch.core.Job` / `JobExecution` | `org.springframework.batch.core.job.Job` / `JobExecution` |
| `JobParameters`, `JobParametersBuilder` | `org.springframework.batch.core` | `org.springframework.batch.core.job.parameters` |
| `Step`, `StepExecution` | `org.springframework.batch.core` | `org.springframework.batch.core.step` |
| Tiện ích chạy test | `JobLauncherTestUtils` | `JobOperatorTestUtils` |
| Gọi chạy job | `launchJob(parameters)` | `startJob(parameters)` |

Ví dụ cốt lõi với **5.x** (trong test class có `@SpringBatchTest` và Spring test context đã cấu hình):

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;

// @Autowired JobLauncherTestUtils jobLauncherTestUtils;
// jobLauncherTestUtils.setJob(importCustomersJob);

JobParameters parameters = new JobParametersBuilder()
        .addString("testRunId", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(execution.getExitStatus().getExitCode())
        .isEqualTo(ExitStatus.COMPLETED.getExitCode());
```

Các phép assert trên `BatchStatus` và `ExitStatus` giữ nguyên về ý nghĩa giữa hai phiên bản. Khi chuyển code từ 5.x sang 6.x, phải cập nhật cả import và tiện ích chạy test cho đúng phiên bản dependency.

## 8. Những tình huống cần chọn assert phù hợp

| Tình huống | Assert chính | Assert bổ sung có ích |
| --- | --- | --- |
| Job xử lý hết dữ liệu hợp lệ | `BatchStatus.COMPLETED` | Exit code `COMPLETED`; số bản ghi đọc/ghi; dữ liệu đầu ra. |
| Step phát sinh lỗi không được xử lý | `BatchStatus.FAILED` | Exit code `FAILED`; `getAllFailureExceptions()`; step gây lỗi. |
| Job được dừng theo yêu cầu | `BatchStatus.STOPPED` | Step cuối cùng; lưu trạng thái để có thể restart nếu thiết kế cho phép. |
| Xử lý có skip hợp lệ | Thường `BatchStatus.COMPLETED` | `skipCount` đúng; dữ liệu hợp lệ vẫn được ghi; exit code tùy hợp đồng. |
| Hoàn tất kèm cảnh báo nghiệp vụ | `BatchStatus.COMPLETED` | Exit code tùy chỉnh, ví dụ `COMPLETED_WITH_WARNINGS`. |
| Restart sau một lần thất bại | Lần đầu `FAILED`, lần restart `COMPLETED` | Hai `JobExecution` thuộc cùng `JobInstance`; step đã hoàn tất được chạy lại hay bỏ qua theo cấu hình. |

Để test trường hợp **restart**, không thêm `testRunId` mới khi cần tái sử dụng cùng `JobInstance`. Dùng cùng bộ identifying parameters giữa lần lỗi và lần restart, rồi lấy từng `JobExecution` riêng để assert. `JobInstance` mới và `JobExecution` mới là hai khái niệm khác nhau.

## 9. Các lỗi thường gặp khi assert trạng thái

**1. Test báo `JobInstanceAlreadyCompleteException` ở lần chạy thứ hai.** Bạn đang tái dùng tên job và identifying parameters của instance đã hoàn thành. Đối với test những lần chạy độc lập, cấp tham số định danh riêng hoặc quản lý/thu dọn metadata test một cách có chủ đích. Đối với test restart, cố ý dùng lại cùng parameters.

**2. Test kỳ vọng `FAILED` nhưng nhận `COMPLETED`.** Kiểm tra job có cấu hình skip, retry, listener tùy biến, hoặc transition có chủ đích chuyển lỗi của một step thành kết quả hoàn tất của flow hay không. Đối chiếu trạng thái của step với trạng thái cuối của toàn job.

**3. Test so sánh `getStatus()` với chuỗi `"COMPLETED"`.** `getStatus()` trả về `BatchStatus` (enum), vì vậy nên so sánh với `BatchStatus.COMPLETED`. Chuỗi `"COMPLETED"` dùng với `getExitStatus().getExitCode()`.

**4. Test chạy không ổn định khi chạy song song.** Nhiều test dùng chung bảng dữ liệu, chung file hoặc cùng job parameters có thể gây xung đột. Mỗi test nên có fixture độc lập; nếu khởi chạy bất đồng bộ thì cần đồng bộ hóa bằng kết quả đã ghi vào repository.

**5. Kiểm tra trạng thái nhưng bỏ qua dữ liệu.** Một job có thể hoàn tất dù không đọc được bản ghi nào, hoặc đã skip hết dữ liệu theo cấu hình. Kết hợp status với `readCount`, `writeCount`, `skipCount` và dữ liệu đích để kiểm tra đúng yêu cầu thực tế.

**6. Bắt ngoại lệ tại lời gọi chạy job rồi kết luận job thất bại.** Ngoại lệ khi *khởi chạy* khác với kết quả `FAILED` sau khi *thực thi*. Nếu mục tiêu là kiểm thử trạng thái của `JobExecution`, hãy lấy `JobExecution` và assert trạng thái trên chính đối tượng đó.

## 10. Bài tập thực hành

Giả sử job `importOrdersJob` đọc 12 đơn hàng: 10 hợp lệ, 2 không hợp lệ. Yêu cầu nghiệp vụ cho phép skip tối đa 2 đơn hàng lỗi và vẫn hoàn thành.

1. Tạo fixture với đúng 12 đầu vào và kho dữ liệu đích rỗng.
2. Khởi chạy `importOrdersJob` bằng bộ parameters mới.
3. Assert `JobExecution.getStatus() == BatchStatus.COMPLETED`.
4. Tìm `StepExecution` của step nhập đơn hàng; assert `readCount == 12`, `writeCount == 10` và `skipCount == 2` (theo đúng cấu hình reader/processor/writer của fixture).
5. Kiểm tra kho đích có chính xác 10 đơn hàng hợp lệ.
6. Thử thêm trường hợp số lỗi vượt ngưỡng skip và xác nhận kết quả `FAILED` cùng nguyên nhân liên quan.

Khi hoàn thành, bạn sẽ phân biệt được **“job kết thúc theo flow”** và **“job tạo ra kết quả dữ liệu đúng”** — hai điều kiện kiểm thử thường cần đi cùng nhau.

## Tài liệu tham khảo

- [Spring Batch – Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` và tiện ích test của Spring Batch 6.
- [Spring Batch – Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): phân biệt `BatchStatus` với `ExitStatus`.
- [Spring Batch 6 – `JobExecution` API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/job/JobExecution.html).
- [Spring Batch 6 – `JobOperatorTestUtils` API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobOperatorTestUtils.html).
- [Spring Batch 5.2 – `JobLauncherTestUtils` API](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/JobLauncherTestUtils.html).

