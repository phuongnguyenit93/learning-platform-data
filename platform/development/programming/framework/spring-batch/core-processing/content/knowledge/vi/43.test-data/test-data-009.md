# Dọn metadata sau test trong Spring Batch

Trong **Spring Batch Core Processing**, một lần chạy Job không chỉ đọc và ghi dữ liệu nghiệp vụ mà còn tạo nhiều bản ghi **metadata** trong `JobRepository`. Metadata ghi lại Job nào đã chạy, tham số nào được sử dụng, trạng thái thực thi, từng Step đã xử lý bao nhiêu bản ghi và thông tin cần thiết để restart khi xảy ra lỗi.

Khi viết test, việc dọn metadata sau test giúp các lần thử nghiệm độc lập không vô tình sử dụng lịch sử của nhau. Tuy nhiên, dọn sai thời điểm có thể phá vỡ bài test restart hoặc xóa kết quả đang được test khác sử dụng. Bài này trình bày cách dọn metadata bằng công cụ chính thức của `spring-batch-test`, cách tổ chức vòng đời test và cách phân biệt metadata với dữ liệu nghiệp vụ.

## 1. Vì sao metadata cũ ảnh hưởng đến test?

Giả sử có Job `importOrdersJob` với một bộ tham số xác định:

```text
jobName = importOrdersJob
inputFile = orders-2026-11.csv
batchDate = 2026-11-16
```

Ở lần chạy đầu tiên, Spring Batch tạo:

```text
Job
└── JobInstance (jobName + identifying JobParameters)
    └── JobExecution #101  [COMPLETED]
        ├── JobExecutionContext
        ├── StepExecution: readOrdersStep    [COMPLETED]
        │   └── StepExecutionContext
        └── StepExecution: persistOrdersStep [COMPLETED]
            └── StepExecutionContext
```

Nếu test khác khởi chạy **cùng Job và cùng identifying parameters** trong cùng repository, Spring Batch nhận diện đó là `JobInstance` đã hoàn thành. Kết quả thường là ngoại lệ `JobInstanceAlreadyCompleteException`, bởi một JobInstance đã `COMPLETED` không được chạy lại như một instance mới.

Các vấn đề khác khi để metadata cũ tồn tại gồm:

- Test đếm số lần thực thi Job/Step có thể nhìn thấy cả những lần chạy trước.
- Bài test restart có thể tham chiếu nhầm một lần thực thi không còn thuộc ngữ cảnh đang kiểm thử.
- Dữ liệu trong `ExecutionContext` từ một lần xử lý cũ có thể tạo ra trạng thái không mong đợi khi cố tình tái sử dụng instance.
- Một tập test chạy nhiều lần trên cùng database trở nên phụ thuộc vào thứ tự chạy.

**Mục tiêu của cleanup là tạo trạng thái khởi đầu rõ ràng cho mỗi test độc lập** và giải phóng lịch sử test không còn cần dùng. Metadata là một phần của cơ chế nhận diện và restart, nên cần hiểu nó trước khi xóa.

## 2. Metadata gồm những gì?

Trong cấu hình Spring Batch dùng `JobRepository` dựa trên cơ sở dữ liệu quan hệ, schema mặc định thường có các bảng sau (tên/prefix có thể thay đổi theo phiên bản và cấu hình):

| Bảng | Nội dung chính |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Danh tính của một JobInstance: tên Job và khóa từ identifying parameters. |
| `BATCH_JOB_EXECUTION` | Mỗi lần chạy thực tế của JobInstance, trạng thái và thời điểm chạy. |
| `BATCH_JOB_EXECUTION_PARAMS` | Các JobParameters gắn với từng JobExecution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | Trạng thái được lưu ở phạm vi JobExecution, phục vụ trao đổi và restart. |
| `BATCH_STEP_EXECUTION` | Trạng thái và bộ đếm của từng StepExecution. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Trạng thái được lưu ở phạm vi StepExecution. |
| Các bảng/sequence cấp ID | Phục vụ cấp khóa định danh cho metadata, tùy cơ sở dữ liệu. |

Các bảng có quan hệ khóa ngoại từ bản ghi con về bản ghi cha. Vì vậy, **không nên xóa riêng `BATCH_JOB_EXECUTION` bằng một lệnh `DELETE` đơn giản** khi vẫn còn bản ghi tham chiếu ở bảng context, parameters hoặc step. Cách dọn thủ công cần tôn trọng thứ tự phụ thuộc và đúng schema của phiên bản đang chạy.

### Metadata khác dữ liệu nghiệp vụ

Giả sử Job nhập đơn hàng ghi vào bảng `orders`:

```text
Database test
├── BATCH_JOB_INSTANCE                ← metadata Spring Batch
├── BATCH_JOB_EXECUTION               ← metadata Spring Batch
├── BATCH_STEP_EXECUTION              ← metadata Spring Batch
├── BATCH_*_EXECUTION_CONTEXT         ← metadata Spring Batch
└── orders                            ← dữ liệu nghiệp vụ do Job ghi
```

Việc dọn metadata **không đồng nghĩa** với xóa bản ghi ở `orders`. Một test có thể đã xóa sạch lịch sử Job nhưng vẫn còn 50 đơn hàng từ test trước. Ngược lại, xóa bảng nghiệp vụ không làm biến mất các `JobExecution` `COMPLETED` trong repository.

Do đó, vòng đời test cần quản lý **hai nhóm dữ liệu riêng biệt**:

1. Metadata Spring Batch: dùng tiện ích của `spring-batch-test` hoặc cơ chế làm sạch repository được kiểm soát.
2. Dữ liệu nghiệp vụ, file đầu ra, message, cache: dùng fixture, SQL, repository test hoặc tài nguyên tạm phù hợp với ứng dụng.

## 3. Công cụ chính: `JobRepositoryTestUtils`

Thư viện `spring-batch-test` cung cấp `JobRepositoryTestUtils` để dọn những JobExecution được lưu trong repository test. API được dùng phổ biến nhất:

```java
jobRepositoryTestUtils.removeJobExecutions();
```

Phương thức này dọn metadata các lần thực thi Job mà công cụ truy xuất được qua repository/explorer, bao gồm những thông tin liên quan đến các lần thực thi đó. Với test chạy trên **database hoàn toàn riêng**, đây là cách đơn giản để bắt đầu lượt test tiếp theo mà không bị các JobInstance cũ chi phối.

Dependency cần có trong phạm vi test:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Khi dùng Spring Boot, phiên bản dependency nên được quản lý đồng bộ bởi BOM của dự án. Nếu không dùng Boot, cần cấu hình JUnit 5, Spring Test và Spring Batch tương ứng.

Annotation `@SpringBatchTest` đăng ký các thành phần hỗ trợ test, trong đó có `JobRepositoryTestUtils`. Kết hợp với `@SpringBootTest` khi cần chạy Job thật trong application context:

```java
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class BatchMetadataTest {

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    // Các test method và lifecycle method ở các mục tiếp theo.
}
```

`spring.batch.job.enabled=false` tránh việc Spring Boot tự chạy Job khi khởi tạo context của bài test. Test sẽ quyết định **khi nào** khởi chạy Job, với bộ tham số nào, và **khi nào** dọn metadata.

> Phạm vi quan trọng: `removeJobExecutions()` không phải thao tác “xóa riêng dữ liệu của test hiện tại” theo tên class JUnit. Nó có thể dọn các lần thực thi của **nhiều Job** trong cùng repository. Chỉ dùng cách dọn toàn bộ khi test sở hữu riêng schema/database hoặc được bảo đảm không có test khác chạy trên repository đó.

## 4. Đặt cleanup ở `@BeforeEach` hay `@AfterEach`?

Cả hai lifecycle hook đều hữu ích, nhưng mục đích khác nhau.

| Hook | Thời điểm | Giá trị trong test |
| --- | --- | --- |
| `@BeforeEach` | Trước mỗi test method | Dọn lịch sử sót từ lượt trước, tạo điều kiện đầu vào dễ dự đoán. |
| `@AfterEach` | Sau mỗi test method | Xóa metadata đã tạo trong test vừa hoàn thành, kể cả khi assertion không thành công và JUnit thực hiện teardown bình thường. |
| `@BeforeAll` / `@AfterAll` | Trước/sau toàn class | Phù hợp khi các method cố ý chia sẻ lịch sử hoặc mỗi class có database riêng; cần chủ động kiểm soát phụ thuộc giữa method. |

Ví dụ tối giản:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class BatchCleanupLifecycleTest {

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @BeforeEach
    void clearStaleBatchMetadata() {
        jobRepositoryTestUtils.removeJobExecutions();
    }

    @AfterEach
    void clearCreatedBatchMetadata() {
        jobRepositoryTestUtils.removeJobExecutions();
    }
}
```

Đây là cấu trúc lifecycle minh họa; class thực tế sẽ có `@Test` để khởi chạy Job và kiểm tra kết quả. Không nhất thiết lúc nào cũng gọi cả hai hook:

- Dùng `@BeforeEach` khi một test phải bắt đầu từ repository sạch, kể cả sau một lần chạy test bị dừng đột ngột khiến `@AfterEach` trước đó không thực thi.
- Dùng `@AfterEach` khi muốn bảo đảm dữ liệu của mỗi test được giải phóng ngay sau khi kiểm tra xong.
- Dùng cả hai trong database test **cô lập** nếu muốn hai hàng rào bảo vệ. Chi phí cleanup thường nhỏ trong bộ test hẹp, nhưng có thể đáng kể nếu metadata test rất lớn.

Không đặt cleanup ở giữa các bước của **cùng một bài test restart**: bước sau cần đọc lại JobInstance, ExecutionContext và lịch sử của bước trước.

## 5. Ví dụ hoàn chỉnh: chạy Job rồi dọn metadata

Ví dụ dưới đây sử dụng **Spring Batch 5.x**, JUnit Jupiter, AssertJ và Spring Boot 3.x. Giả định ứng dụng có bean `Job` tên `importOrdersJob` cùng dữ liệu fixture hợp lệ để Job chạy xong ở trạng thái `COMPLETED`.

```java
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
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

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportOrdersJobIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @BeforeEach
    void prepare() {
        // Chỉ an toàn vì đây là JobRepository dành riêng cho test.
        jobRepositoryTestUtils.removeJobExecutions();

        // Nêu rõ Job cần chạy nếu application context có nhiều Job.
        jobLauncherTestUtils.setJob(importOrdersJob);

        // Chuẩn bị input và dữ liệu nghiệp vụ tại đây.
    }

    @Test
    void shouldCompleteWithCleanMetadata() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
    }

    @AfterEach
    void cleanup() {
        // Chạy sau assertion: vẫn đọc được JobExecution trong test.
        jobRepositoryTestUtils.removeJobExecutions();

        // Dọn dữ liệu nghiệp vụ / file fixture bằng cơ chế riêng.
    }
}
```

Luồng diễn ra như sau:

```text
@BeforeEach
  ├─ Xóa metadata còn sót trong repository test
  ├─ Chọn đúng Job
  └─ Chuẩn bị dữ liệu đầu vào
@Test
  ├─ Tạo JobParameters
  ├─ launchJob(parameters)
  ├─ Spring Batch ghi metadata
  └─ Assert JobExecution.status == COMPLETED
@AfterEach
  ├─ Xóa metadata Job/Step đã tạo
  └─ Giải phóng dữ liệu nghiệp vụ / file tạm
```

Ở đây, `testRunId` mới mỗi lần chạy giúp độc lập **JobInstance** ngay cả khi repository chưa được dọn. Còn cleanup giúp test không để lại lịch sử cho những lần chạy kế tiếp. Hai cơ chế hỗ trợ nhau, nhưng phục vụ những mục đích khác nhau.

Nếu Job yêu cầu `inputFile`, `businessDate` hoặc tham số nghiệp vụ khác, phải cung cấp các tham số đó cùng fixture tương ứng; `testRunId` một mình không khiến Job bất kỳ tự động hoàn thành.

### Tùy phiên bản Spring Batch

Trong **Spring Batch 6.x**, tiện ích chạy Job trong test là `JobOperatorTestUtils` với `startJob(parameters)`. Phần cleanup tiếp tục tập trung vào `JobRepositoryTestUtils`:

```java
@Autowired
private JobOperatorTestUtils jobOperatorTestUtils;

@Autowired
private JobRepositoryTestUtils jobRepositoryTestUtils;

@Test
void shouldRun() throws Exception {
    jobOperatorTestUtils.setJob(importOrdersJob);
    JobExecution execution =
            jobOperatorTestUtils.startJob(parameters);

    assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
}

@AfterEach
void cleanup() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Đây là phần trích trong test đã cấu hình `@SpringBatchTest`, `@SpringBootTest`, bean `importOrdersJob`, `parameters` và AssertJ. Khi viết mã hoàn chỉnh cho Spring Batch 6, cập nhật import `Job`/`JobExecution` sang các gói `org.springframework.batch.core.job` và `JobParameters` sang `org.springframework.batch.core.job.parameters`. Sự khác biệt của công cụ khởi chạy không làm thay đổi nguyên tắc: **đợi Job kết thúc, assert, rồi mới dọn metadata**.

## 6. Dọn đúng phạm vi: toàn repository hay một nhóm execution?

### 6.1. Repository test dùng riêng

Nếu mỗi bộ test có database riêng, `removeJobExecutions()` thường là lựa chọn thực tế nhất:

```java
@AfterEach
void clean() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

Giải pháp này dễ dùng, không đòi tự viết SQL theo sơ đồ khóa ngoại và giữ code test tập trung vào hành vi của Job.

### 6.2. Repository chứa nhiều Job/test

Khi có nhiều bài test cùng một schema, xóa toàn bộ metadata gây nguy cơ tác động đến các Job khác. Một số phiên bản Spring Batch cũng cung cấp overload nhận tập `JobExecution` để dọn theo danh sách thực thi cần xóa:

```java
// Chỉ là minh họa về cách giới hạn phạm vi khi API của phiên bản hỗ trợ.
// jobRepositoryTestUtils.removeJobExecutions(executionsCreatedByThisTest);
```

Dù giới hạn theo execution, cần xét cả những lần restart thuộc cùng `JobInstance`. Dọn sai thứ tự hoặc bỏ sót execution có thể khiến metadata còn trạng thái không nhất quán. Cách đáng tin cậy nhất cho test chạy đồng thời vẫn là **mỗi bộ test có database/schema riêng**.

Trong một hệ thống thực tế, “repository riêng” có thể là:

- Database in-memory chỉ tồn tại trong vòng đời của test context.
- Database/container riêng cho một nhóm test tích hợp.
- Schema riêng cho mỗi luồng kiểm thử song song, với `JobRepository` trỏ đúng schema đó.

**Không chạy `removeJobExecutions()` trên JobRepository dùng chung với môi trường production, staging hoặc quá trình chạy batch thật.** Lịch sử Job là dữ liệu vận hành quan trọng và có thể cần để retry, restart, đối soát và điều tra lỗi.

## 7. Test restart: trường hợp phải giữ metadata trong cùng test

Restart là ví dụ điển hình cho việc **không dọn metadata quá sớm**. Giả sử Job chạy lần đầu bị lỗi giữa chừng, sau đó sửa đầu vào và chạy lại từ checkpoint.

```text
JobInstance (identifying parameters giống nhau)
├── JobExecution #201 -> FAILED
│   └── StepExecution chứa ExecutionContext/checkpoint
└── JobExecution #202 -> COMPLETED (restart cùng JobInstance)
```

Thứ tự đúng trong test:

1. Chuẩn bị đầu vào để gây lỗi có kiểm soát.
2. Chạy Job với bộ **identifying JobParameters** cố định và assert lần đầu `FAILED`.
3. Chỉnh điều kiện gây lỗi; **giữ nguyên metadata** của lần đầu.
4. Khởi chạy lại/restart theo cơ chế được cấu hình; assert lần thứ hai `COMPLETED` và kết quả nghiệp vụ.
5. Sau khi các phép assert kết thúc, xóa metadata trong `@AfterEach`.

Ví dụ về cấu trúc logic:

```java
@Test
void restartAfterTransientFailure() throws Exception {
    JobParameters sameParameters = /* các identifying parameters cố định */;

    // Dữ liệu test khiến Step thất bại có kiểm soát.
    prepareFailingInput();

    JobExecution first = jobLauncherTestUtils.launchJob(sameParameters);
    assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);

    // Không gọi removeJobExecutions() ở đây!
    repairInput();

    // Job phải được cấu hình restartable và điều kiện lỗi đã được khắc phục.
    JobExecution restarted =
            jobLauncherTestUtils.launchJob(sameParameters);
    assertThat(restarted.getStatus())
            .isEqualTo(BatchStatus.COMPLETED);
}

// @AfterEach mới dọn metadata cho cả hai lần chạy.
```

Đoạn minh họa dùng API Spring Batch 5.x và hai helper fixture của dự án (`prepareFailingInput`, `repairInput`). Tùy cấu hình Job, bước restart có thể được thực hiện qua `JobOperator`; điều kiện bắt buộc là lần đầu phải thất bại theo cách **cho phép restart** và những identifying parameters dùng để xác định JobInstance phải giữ nguyên.

Xóa metadata giữa lần lỗi và lần restart biến lần chạy kế tiếp thành một quá trình mới hoặc làm mất checkpoint. Khi đó test không còn kiểm tra được tính năng restart thực sự.

## 8. Cleanup không thay thế quản lý dữ liệu nghiệp vụ

Xét test Job đọc file CSV rồi ghi bảng `orders`. Nếu chỉ có:

```java
@AfterEach
void cleanup() {
    jobRepositoryTestUtils.removeJobExecutions();
}
```

thì các đơn hàng do Job tạo vẫn có thể còn trong database. Test sau sẽ bị ảnh hưởng nếu cùng đọc và ghi vào bảng này.

Một lựa chọn trong dự án Spring Boot là dùng `@Sql` với SQL dành riêng cho bảng nghiệp vụ:

```java
import org.springframework.test.context.jdbc.Sql;

@Sql(
    scripts = "/sql/clean-orders-test-data.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class ImportOrdersJobIT {
    // ...
}
```

Tệp `clean-orders-test-data.sql` do dự án tạo để xóa **dữ liệu fixture** trong `orders` và các bảng phụ thuộc; nội dung SQL phải phù hợp schema và quy tắc khóa ngoại của nghiệp vụ.

Một vài lựa chọn khác:

| Loại dữ liệu | Cách dọn phù hợp |
| --- | --- |
| Metadata Job/Step | `JobRepositoryTestUtils` trên repository test riêng. |
| Bảng đơn hàng/sản phẩm do Job ghi | Test SQL, truncate trong schema test, repository fixture hoặc reset database test. |
| File input/output | Đường dẫn tạm cho mỗi test; xóa file/thư mục tạm ở cuối. |
| Message queue/cache | Destination hoặc namespace tách biệt; dọn theo công cụ test tương ứng. |
| ID sequence | Thông thường không cần reset để assert trạng thái; tránh phụ thuộc vào số ID chính xác. |

`@DirtiesContext` chỉ yêu cầu Spring Test tái tạo application context. Nếu `JobRepository` dùng database bên ngoài còn tồn tại, annotation này **không tự đảm bảo xóa các bản ghi metadata**.

Tương tự, gắn `@Transactional` lên một test method không có nghĩa mọi giao dịch của Job đều được rollback khi test kết thúc. Spring Batch quản lý transaction ở những điểm riêng cho từng Step/chunk. Để kiểm chứng và dọn kết quả sau Job, hãy dùng cơ chế fixture rõ ràng cho từng loại tài nguyên.

## 9. Chạy test song song và test bất đồng bộ

### Test chạy song song trên cùng repository

Giả sử Test A đang chạy Job, trong khi Test B gọi `removeJobExecutions()` trên cùng schema:

```text
Test A:  startJob ─── write StepExecution ───── finish
Test B:             removeJobExecutions()
                              ↑
                    Có thể xóa metadata Test A đang cần
```

Dẫn đến lỗi không ổn định hoặc kết quả sai vì test B xóa lịch sử của test A. Những cách giảm xung đột là cô lập database/schema theo worker hoặc tắt thực thi song song đối với nhóm test dùng chung repository. Chỉ dùng một annotation điều khiển thứ tự trong một class chưa chắc ngăn được class khác đang chạy đồng thời.

### Job thực thi bất đồng bộ

Nếu Job được khởi chạy qua một `TaskExecutor` bất đồng bộ, lời gọi start có thể trả về khi `JobExecution` vẫn ở `STARTING`/`STARTED`. **Không dọn metadata ngay** khi Job còn chạy. Cần đợi đến trạng thái kết thúc bằng cơ chế chờ có timeout và đọc lại trạng thái từ `JobExplorer`/repository. Đối với test tích hợp thông thường, thực thi đồng bộ giúp lifecycle và cleanup đơn giản hơn.

Dọn metadata khi Job đang chạy có thể gây lỗi cập nhật execution context, trạng thái Step hoặc JobExecution. Việc cleanup trong `@AfterEach` chỉ an toàn khi test đã chắc chắn rằng Job thực sự kết thúc trước khi bước teardown diễn ra.

## 10. Các lỗi thường gặp và cách phân biệt

### `JobInstanceAlreadyCompleteException` khi chạy test nhiều lần

**Nguyên nhân thường gặp:** cùng Job + cùng identifying parameters đã hoàn thành trong repository. Với test độc lập, dùng tham số định danh mới và làm sạch repository test đúng phạm vi. Với test restart, không đổi identifying parameters tùy tiện; phải thiết kế test cố ý tiếp tục một instance thất bại.

### Metadata đã sạch nhưng test vẫn đọc dữ liệu cũ

**Nguyên nhân:** dữ liệu nghiệp vụ nằm ngoài các bảng metadata. Dọn bảng/domain repository và file fixture riêng; không kỳ vọng `JobRepositoryTestUtils` xử lý các bảng nghiệp vụ.

### Dọn metadata làm test restart bị thất bại

**Nguyên nhân:** gọi cleanup trước khi restart, khiến thông tin `JobInstance` và checkpoint bị xóa. Dời cleanup về cuối test, sau khi đã kiểm tra mọi `JobExecution` liên quan.

### Lỗi khóa ngoại khi dùng `DELETE FROM BATCH_JOB_EXECUTION`

**Nguyên nhân:** vẫn còn context, parameters hoặc StepExecution tham chiếu. Dùng `JobRepositoryTestUtils` với schema test tương thích, hoặc viết cơ chế SQL riêng bảo đảm thứ tự phụ thuộc theo schema cụ thể. Không tùy tiện tắt foreign key để “xóa cho được”.

### Test pass khi chạy một mình nhưng fail khi chạy cùng cả suite

**Nguyên nhân khả dĩ:** các class cùng dùng repository, fixture, file hoặc tên JobParameters; cleanup của test này xóa dữ liệu test khác. Cô lập tài nguyên hoặc điều phối chạy tuần tự cho những test không thể cô lập.

### Các ID của JobExecution tiếp tục tăng sau cleanup

**Giải thích:** xóa bản ghi metadata không nhất thiết đặt lại các sequence/table cấp ID. Điều quan trọng là không còn execution không mong đợi trong phạm vi test, **không phải** ID mới luôn bắt đầu từ 1.

### Có bản ghi cũ dù đã có `@AfterEach`

**Khả năng:** lần test trước bị buộc dừng, teardown không chạy; test dùng database khác với database đang quan sát; cleanup gọi trước khi một Job bất đồng bộ kết thúc; hoặc một tiến trình khác ghi metadata cùng lúc. Kiểm tra cấu hình datasource/job repository và giới hạn quyền sở hữu của test.

## 11. Một mô hình tổ chức test dễ duy trì

Đối với nhóm test tích hợp Spring Batch có nhiều Job, có thể tổ chức thành các lớp/bộ fixture theo nguyên tắc:

```text
BatchIntegrationTest
├── Datasource/schema dành riêng cho test
├── @SpringBatchTest + Spring test context
├── @BeforeEach
│   ├── Dọn metadata cũ
│   └── Reset dữ liệu nghiệp vụ và input fixture
├── @Test
│   ├── Khởi chạy Job
│   ├── Assert JobExecution / StepExecution
│   └── Assert đầu ra nghiệp vụ
└── @AfterEach
    ├── Chờ Job kết thúc (nếu asynchronous)
    ├── Dọn metadata
    └── Dọn tài nguyên tạm của test
```

Nếu một bài test gồm nhiều lần thực thi liên quan nhau (ví dụ retry/restart), đặt các lần chạy đó **trong cùng một test method** hoặc quản lý fixture chuyên biệt để không có cleanup xen giữa.

Với các kịch bản cần truy vết sự cố, giữ lại thông tin chẩn đoán **trước** khi xóa. Ví dụ, đưa trạng thái, exit description, failure exceptions và step counters vào thông báo assertion/log của test. Sau cleanup, không nên dựa vào việc có thể truy vấn lại cùng `JobExecution` từ database nữa.

## 12. Bài tập thực hành

Giả sử `importPaymentsJob` đọc 8 bản ghi thanh toán từ file test và lưu 8 bản ghi hợp lệ vào database.

**Kịch bản A – Test độc lập:**

1. Tạo cơ sở dữ liệu/schema test và fixture 8 giao dịch.
2. Tạo `@BeforeEach` để dọn metadata và dữ liệu `payments` trước khi khởi chạy.
3. Chạy `importPaymentsJob` với identifying parameter riêng.
4. Assert `JobExecution.getStatus()` bằng `BatchStatus.COMPLETED`; kiểm tra 8 bản ghi đầu ra.
5. Trong `@AfterEach`, gọi `JobRepositoryTestUtils.removeJobExecutions()` và dọn file fixture.
6. Chạy cùng test hai lần để thấy lần thứ hai không bị ảnh hưởng bởi metadata của lần đầu.

**Kịch bản B – Test restart:**

1. Tạo đầu vào khiến Job bị lỗi ở bản ghi thứ 5.
2. Chạy Job lần đầu, assert `FAILED`.
3. Sửa điều kiện gây lỗi rồi restart với cùng identifying parameters.
4. Assert lần thực thi thứ hai `COMPLETED` và kiểm tra dữ liệu đầu ra không bị nhân đôi.
5. Chỉ dọn metadata sau khi toàn bộ phép assert của kịch bản đã hoàn tất.

Hai kịch bản minh họa điểm cốt lõi: **test độc lập cần lịch sử sạch; test restart cần giữ lịch sử có chủ đích đến khi kiểm thử xong**.

## Ghi nhớ

- `JobRepository` giữ metadata cần thiết để xác định JobInstance, theo dõi JobExecution/StepExecution và hỗ trợ restart.
- `JobRepositoryTestUtils.removeJobExecutions()` là công cụ chính để dọn metadata trong **repository dành riêng cho test**.
- `@BeforeEach` tạo trạng thái khởi đầu nhất quán; `@AfterEach` giải phóng lịch sử sau khi các assertion đã hoàn thành.
- Metadata cleanup không thay thế việc xóa dữ liệu nghiệp vụ hoặc tài nguyên ngoài database.
- Không dọn giữa hai lần chạy thuộc một bài test restart; không dọn khi Job còn đang chạy.
- Với test song song, **cô lập repository/schema** là giải pháp an toàn nhất cho việc cleanup toàn bộ.

## Tài liệu đọc thêm

- [Spring Batch Reference – Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html) – `@SpringBatchTest` và các tiện ích kiểm thử.
- [Spring Batch Reference – Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html) – vai trò và quan hệ của các bảng metadata.
- [Spring Batch Reference – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html) – cấu hình repository.
- [Spring Batch API – `JobRepositoryTestUtils`](https://docs.spring.io/spring-batch/docs/5.2.4/api/org/springframework/batch/test/JobRepositoryTestUtils.html) – tiện ích dọn các lần thực thi trong test.

