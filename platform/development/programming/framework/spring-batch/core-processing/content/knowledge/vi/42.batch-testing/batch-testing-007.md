# MetaDataInstanceFactory trong kiểm thử Spring Batch

## 1. Vấn đề cần giải quyết

Trong một batch job, nhiều thành phần không chỉ xử lý dữ liệu đầu vào mà còn dựa vào **metadata của lần chạy**. Ví dụ:

- `StepExecutionListener` kiểm tra `readCount`, `writeCount` để quyết định trạng thái kết thúc của step.
- `ItemReader` hoặc `ItemWriter` đọc tham số chạy (`JobParameters`) để chọn tệp, ngày xử lý hoặc chế độ vận hành.
- Thành phần có `@StepScope` truy cập `stepExecutionContext` hoặc `jobParameters` bằng Spring Expression Language (SpEL).
- Mã xử lý phục hồi đọc checkpoint từ `ExecutionContext`.

Khi kiểm thử riêng các thành phần này, ta thường **không cần chạy toàn bộ job**. Tuy nhiên, `StepExecution` cần liên kết với `JobExecution`, còn `JobExecution` gắn với `JobInstance` và `JobParameters`. Nếu tự khởi tạo cả đồ thị đối tượng trong mỗi test, phần chuẩn bị sẽ dài và dễ che khuất hành vi thực sự cần kiểm tra.

`org.springframework.batch.test.MetaDataInstanceFactory` là lớp tiện ích trong mô-đun `spring-batch-test`, cung cấp các **phương thức tĩnh** để tạo metadata hợp lệ về mặt cấu trúc cho test:

```text
JobInstance (tên job, định danh instance)
    └── JobExecution (lần thực thi, JobParameters, job ExecutionContext)
            └── StepExecution (tên step, bộ đếm, step ExecutionContext)
```

Ví dụ tối giản:

```java
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
stepExecution.setReadCount(0);

// Truyền stepExecution vào listener hoặc một hàm đang được kiểm thử.
```

Factory đã tạo sẵn các đối tượng cha cần thiết. Test chỉ phải thiết lập dữ liệu liên quan tới tình huống đang xét.

> **Phạm vi:** `MetaDataInstanceFactory` tạo đối tượng metadata **trong bộ nhớ**; nó không chạy job/step, không tự ghi vào các bảng `BATCH_*`, không gọi `ItemReader`/`ItemWriter`, không bắt đầu transaction và không chứng minh rằng cấu hình batch chạy thành công. Đó là vai trò của các bài kiểm thử tích hợp.

## 2. Chuẩn bị thư viện và phân biệt phiên bản

Với Gradle, khai báo thư viện test cùng dòng phiên bản Spring Batch đang được quản lý trong dự án:

```groovy
dependencies {
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}
```

Trong dự án Spring Boot, BOM/dependency management thường quản lý phiên bản; nếu không dùng BOM, hãy chỉ định các phiên bản tương thích. Ví dụ ở các mục sau dùng **Spring Batch 5.2.x + JUnit 5**, với các import chính:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.test.MetaDataInstanceFactory;
```

**Lưu ý cho Spring Batch 6.x:** `MetaDataInstanceFactory` vẫn nằm trong `org.springframework.batch.test`, nhưng một số kiểu liên quan đã đổi package, chẳng hạn `JobExecution` thuộc `org.springframework.batch.core.job`, `StepExecution` thuộc `org.springframework.batch.core.step`, `JobParameters`/`JobParametersBuilder` thuộc `org.springframework.batch.core.job.parameters`, còn `ExecutionContext` thuộc `org.springframework.batch.infrastructure.item`. Khi sao chép ví dụ, hãy dùng import đúng với phiên bản thực tế.

## 3. Các đối tượng metadata cần hiểu trước khi dùng factory

| Đối tượng | Đại diện cho | Dữ liệu thường cần trong unit test |
|---|---|---|
| `JobInstance` | Một lần chạy *logic* của một job, được xác định trong hệ thống bởi tên job cùng các tham số định danh | Tên job, ID instance |
| `JobExecution` | Một lần thực thi/thử chạy của job instance; một instance có thể có nhiều execution khi chạy lại | ID execution, `JobParameters`, trạng thái, job-level `ExecutionContext` |
| `StepExecution` | Một lần thực thi của một step trong `JobExecution` | Tên step, ID, `readCount`, `writeCount`, skip/commit count, `ExitStatus`, step-level `ExecutionContext` |
| `JobParameters` | Giá trị đầu vào mô tả lần chạy, ví dụ tên tệp, ngày nghiệp vụ | `inputFile`, `businessDate`, `run.id` |
| `ExecutionContext` | Kho key-value lưu trạng thái thực thi/checkpoint; có phạm vi job hoặc step | Vị trí đọc cuối, cờ nghiệp vụ, giá trị phục vụ restart |

Phân biệt rõ hai trường hợp sau:

```java
StepExecution step = MetaDataInstanceFactory.createStepExecution();

// Context của step, thường dùng để lưu checkpoint của riêng step.
step.getExecutionContext().putString("cursor", "record-101");

// Context của job, chia sẻ trạng thái ở phạm vi lần thực thi job.
step.getJobExecution().getExecutionContext()
    .putString("reportPath", "/tmp/report.csv");
```

`JobParameters` không phải `ExecutionContext`: tham số đầu vào mô tả lần chạy, còn context chứa trạng thái có thể được cập nhật trong quá trình xử lý. Không nên dùng chúng thay thế cho nhau trong các phép kiểm thử.

## 4. Danh sách phương thức của `MetaDataInstanceFactory`

### 4.1. Tạo `JobInstance`

| Phương thức | Ý nghĩa |
|---|---|
| `createJobInstance()` | Tạo instance với tên/ID mặc định. |
| `createJobInstance(String jobName, Long instanceId)` | Tạo instance với tên và ID do test chỉ định. |

### 4.2. Tạo `JobExecution`

| Phương thức | Ý nghĩa |
|---|---|
| `createJobExecution()` | Tạo execution với thông tin mặc định và một `JobInstance` đi kèm. |
| `createJobExecution(Long executionId)` | Chỉ định ID của job execution, các thông tin còn lại dùng mặc định. |
| `createJobExecution(String jobName, Long instanceId, Long executionId)` | Chỉ định tên job, ID instance và ID execution; job parameters rỗng. |
| `createJobExecution(String jobName, Long instanceId, Long executionId, JobParameters jobParameters)` | Thêm tham số đầu vào tùy chỉnh. |
| `createJobExecutionWithStepExecutions(Long executionId, Collection<String> stepNames)` | Tạo một `JobExecution` và gắn các `StepExecution` mang tên đã cho. |

### 4.3. Tạo `StepExecution`

| Phương thức | Ý nghĩa |
|---|---|
| `createStepExecution()` | Tạo step execution cùng đồ thị metadata cha mặc định. |
| `createStepExecution(String stepName, Long executionId)` | Chỉ định tên step và **ID của step execution**. |
| `createStepExecution(JobExecution jobExecution, String stepName, Long executionId)` | Gắn step vào một job execution đã chuẩn bị trước. |
| `createStepExecution(JobParameters jobParameters)` | Tạo step và các đối tượng cha, sử dụng job parameters được cung cấp. |
| `createStepExecution(ExecutionContext executionContext)` | Tạo step với **step-level** execution context được cung cấp. |
| `createStepExecution(JobParameters jobParameters, ExecutionContext executionContext)` | Tạo step kết hợp cả job parameters và step-level context. |

Các overload nhận `Long` dùng ID giả phục vụ test. Chúng **không** cấp phát ID từ `JobRepository`.

### 4.4. Giá trị mặc định có sẵn

Theo API của Spring Batch 5.2.x và 6.x:

| Hằng số | Giá trị |
|---|---|
| `DEFAULT_JOB_NAME` | `"job"` |
| `DEFAULT_JOB_INSTANCE_ID` | `12L` |
| `DEFAULT_JOB_EXECUTION_ID` | `123L` |
| `DEFAULT_STEP_NAME` | `"step"` |
| `DEFAULT_STEP_EXECUTION_ID` | `1234L` |

Có thể dùng trực tiếp các hằng số này khi kiểm tra đặc tính mặc định. Tuy vậy, khi hành vi nghiệp vụ phụ thuộc tên step/job hoặc ID, nên truyền giá trị tường minh để test dễ đọc và không vô tình phụ thuộc vào default.

## 5. Ví dụ 1 — Unit test cho `StepExecutionListener`

Giả sử yêu cầu nghiệp vụ: step chỉ được coi là thành công nếu đã đọc ít nhất một bản ghi. Listener nhận `StepExecution` sau khi step kết thúc và trả về `ExitStatus.FAILED` nếu không có dữ liệu.

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class RejectEmptyInputListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getReadCount() == 0) {
            return ExitStatus.FAILED;
        }
        return ExitStatus.COMPLETED;
    }
}
```

Unit test đầy đủ với JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class RejectEmptyInputListenerTest {

    private final RejectEmptyInputListener listener =
            new RejectEmptyInputListener();

    @Test
    void failsWhenNoItemsWereRead() {
        StepExecution step = MetaDataInstanceFactory
                .createStepExecution("importOrders", 1001L);
        step.setReadCount(0);

        ExitStatus result = listener.afterStep(step);

        assertEquals(ExitStatus.FAILED, result);
    }

    @Test
    void succeedsWhenAtLeastOneItemWasRead() {
        StepExecution step = MetaDataInstanceFactory
                .createStepExecution("importOrders", 1002L);
        step.setReadCount(15);

        ExitStatus result = listener.afterStep(step);

        assertEquals(ExitStatus.COMPLETED, result);
    }
}
```

Điểm đáng chú ý:

1. `createStepExecution(...)` giải quyết phần metadata phụ thuộc; test không cần `JobLauncher`, `JobRepository` hoặc cơ sở dữ liệu.
2. `setReadCount(...)` tạo trạng thái đầu vào cần kiểm tra mà không cần thật sự đọc 15 bản ghi.
3. Tên `importOrders` và ID `1001L`, `1002L` chỉ giúp mô tả tình huống; chúng không làm step được thực thi.
4. Việc gọi `afterStep(...)` là **gọi trực tiếp phương thức của listener**. Framework không tự gọi vòng đời listener khi chỉ tạo `StepExecution`.

Trong thực tế, có thể làm tương tự với `getWriteCount()`, `getSkipCount()`, `getCommitCount()`, `getExitStatus()` hoặc cờ trạng thái do mã ứng dụng đọc.

## 6. Ví dụ 2 — Kiểm thử `JobParameters` và `ExecutionContext`

Một bộ xử lý có thể dùng tên tệp đầu vào từ `JobParameters` và vị trí xử lý gần nhất từ `ExecutionContext`. Factory hỗ trợ dựng cả hai trong một lời gọi:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.test.MetaDataInstanceFactory;

class MetaDataInstanceFactoryParametersTest {

    @Test
    void suppliesJobParametersAndStepCheckpoint() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "orders-2026-11.csv")
                .addLong("run.id", 42L)
                .toJobParameters();

        ExecutionContext checkpoint = new ExecutionContext();
        checkpoint.putString("lastProcessedKey", "ORD-0150");

        StepExecution step = MetaDataInstanceFactory
                .createStepExecution(parameters, checkpoint);

        assertEquals("orders-2026-11.csv",
                step.getJobParameters().getString("inputFile"));
        assertEquals(42L,
                step.getJobParameters().getLong("run.id"));
        assertEquals("ORD-0150",
                step.getExecutionContext().getString("lastProcessedKey"));
    }
}
```

**Tại sao truyền context qua factory?** Đối tượng `StepExecution` tạo ra sẽ có sẵn dữ liệu checkpoint mà thành phần đang kiểm thử mong đợi. Cũng có thể gọi `createStepExecution(parameters)` rồi thiết lập `step.getExecutionContext().putString(...)` nếu cách đó rõ ý định test hơn.

Khi cần **job-level** `ExecutionContext`, hãy gán vào đúng đối tượng cha:

```java
StepExecution step = MetaDataInstanceFactory.createStepExecution();

step.getJobExecution().getExecutionContext()
    .putString("archiveName", "orders-archive.zip");

// Đọc đúng job context:
String archive = step.getJobExecution()
    .getExecutionContext().getString("archiveName");
```

Nếu code sản xuất truy cập `jobExecutionContext['archiveName']`, đặt giá trị vào `step.getExecutionContext()` sẽ không dựng đúng tình huống, dù key có cùng tên.

## 7. Ví dụ 3 — Gắn `StepExecution` vào job cụ thể

Khi test cần khẳng định cả danh tính của job và thông tin step, có thể tạo `JobExecution` trước rồi tạo step từ nó:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class ExecutionRelationshipTest {

    @Test
    void stepBelongsToSpecifiedJobExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        JobExecution job = MetaDataInstanceFactory.createJobExecution(
                "dailySettlement", 88L, 890L, parameters);

        StepExecution step = MetaDataInstanceFactory.createStepExecution(
                job, "calculateTotals", 891L);

        assertSame(job, step.getJobExecution());
        assertEquals("dailySettlement", job.getJobInstance().getJobName());
        assertEquals("calculateTotals", step.getStepName());
        assertEquals("2026-11-16",
                step.getJobParameters().getString("businessDate"));
    }
}
```

Ở đây ba ID là ba thứ khác nhau: `88L` là **JobInstance ID**, `890L` là **JobExecution ID**, `891L` là **StepExecution ID**. Không nên đặt tên biến chung chung như `id`, vì nhầm lẫn ID rất dễ khiến việc đọc test trở nên khó khăn.

Muốn có một job execution chứa metadata của nhiều step ngay từ đầu, dùng `createJobExecutionWithStepExecutions`:

```java
JobExecution job = MetaDataInstanceFactory.createJobExecutionWithStepExecutions(
        900L, java.util.List.of("extract", "transform", "load"));

java.util.Set<String> names = job.getStepExecutions().stream()
        .map(StepExecution::getStepName)
        .collect(java.util.stream.Collectors.toSet());

assertEquals(java.util.Set.of("extract", "transform", "load"), names);
```

Factory tạo các `StepExecution` được liên kết với `JobExecution`, mỗi step có ID riêng. **Đừng suy ra thứ tự thực thi** từ thứ tự phần tử trong collection metadata: các step này chưa chạy và phương thức không mô phỏng flow, transition hay restart của job.

## 8. Kết hợp với kiểm thử thành phần `@StepScope`

### 8.1. Vì sao phải kích hoạt scope?

Một bean có `@StepScope` thường được khởi tạo trễ và đọc giá trị từ step đang hoạt động, chẳng hạn:

```java
@Bean
@StepScope
public OrderFileReader orderFileReader(
        @Value("#{jobParameters['inputFile']}") String fileName,
        @Value("#{stepExecutionContext['lastProcessedKey']}") String cursor) {
    return new OrderFileReader(fileName, cursor);
}
```

Đây là **ví dụ cấu hình minh họa**: `OrderFileReader` là lớp ứng dụng tự định nghĩa. Khi Spring khởi tạo bean này, nó cần `StepContext` đang được kích hoạt. Chỉ gọi `MetaDataInstanceFactory.createStepExecution()` không tự kích hoạt `@StepScope`.

### 8.2. Dùng `StepScopeTestUtils`

Trong test Spring đã cấu hình bean `orderFileReader` ở scope step, có thể mở một scope tạm thời quanh lệnh gọi:

```java
JobParameters params = new JobParametersBuilder()
        .addString("inputFile", "orders.csv")
        .toJobParameters();

ExecutionContext ctx = new ExecutionContext();
ctx.putString("lastProcessedKey", "ORD-0250");

StepExecution step = MetaDataInstanceFactory.createStepExecution(params, ctx);

// orderFileReader là Spring proxy đã được inject từ ApplicationContext.
String path = StepScopeTestUtils.doInStepScope(step,
        () -> orderFileReader.getInputFileName());

assertEquals("orders.csv", path);
```

Để dùng đoạn này, test cần `ApplicationContext` đã đăng ký `StepScope`, `orderFileReader` là bean proxy phù hợp và `getInputFileName()` là phương thức của lớp ứng dụng. `StepScopeTestUtils.doInStepScope(...)` liên kết `StepExecution` với thread trong phạm vi callback rồi khôi phục trạng thái scope sau đó; nó **không chạy step**.

### 8.3. Dùng `StepScopeTestExecutionListener`

Với test chạy qua Spring Test, `StepScopeTestExecutionListener` có thể tự tìm một phương thức trong lớp test trả về `StepExecution`, sau đó sử dụng đối tượng này làm ngữ cảnh cho test method. Từ Spring Batch 4.1, `@SpringBatchTest` đã đưa listener hỗ trợ step scope/job scope vào cấu hình test.

Ví dụ phần cốt lõi của một test đã có context và bean step-scoped:

```java
@SpringBatchTest
@SpringJUnitConfig(OrdersBatchTestConfiguration.class)
class OrderReaderScopeTest {

    @Autowired
    private OrderFileReader orderFileReader;

    // Listener nhận diện factory method theo kiểu trả về StepExecution.
    public StepExecution getStepExecution() {
        JobParameters params = new JobParametersBuilder()
                .addString("inputFile", "input/orders.csv")
                .toJobParameters();
        StepExecution step = MetaDataInstanceFactory.createStepExecution(params);
        step.getExecutionContext().putString("lastProcessedKey", "ORD-0099");
        return step;
    }

    @Test
    void readerReceivesTheCurrentInputFile() {
        assertEquals("input/orders.csv",
                orderFileReader.getInputFileName());
    }
}
```

`OrdersBatchTestConfiguration` và `OrderFileReader` ở ví dụ trên là cấu hình/lớp của ứng dụng. Phần cần ghi nhớ là cơ chế: **listener cung cấp scope**, còn **factory cung cấp metadata đầu vào** cho scope. Nếu không muốn khai báo phương thức `getStepExecution()`, listener có thể sử dụng một step execution mặc định; nhưng test sẽ không có các tham số/context chuyên biệt trừ khi tự thiết lập.

## 9. Chọn đúng công cụ kiểm thử

| Mục tiêu | Công cụ phù hợp | Có thực thi batch? |
|---|---|---|
| Tạo metadata cho unit test của listener hoặc hàm nghiệp vụ | `MetaDataInstanceFactory` | Không |
| Gọi bean `@StepScope` trong một phạm vi step giả lập | `MetaDataInstanceFactory` + `StepScopeTestUtils` hoặc `StepScopeTestExecutionListener` | Không |
| Chạy riêng một step với hạ tầng Spring Batch | `JobLauncherTestUtils.launchStep(...)` (Spring Batch 5.x) | Có |
| Chạy toàn job, kiểm tra dữ liệu và trạng thái cuối | `JobLauncherTestUtils.launchJob(...)` cùng test context (Spring Batch 5.x) | Có |
| Kiểm tra metadata đã lưu trong repository và hành vi restart | Kiểm thử tích hợp với `JobRepository`, nguồn dữ liệu và cấu hình thật/test | Có |

Ở Spring Batch 6.x, API hỗ trợ khởi chạy trong test có thay đổi, bao gồm `JobOperatorTestUtils`; hãy tham khảo tài liệu testing đúng phiên bản. `MetaDataInstanceFactory` vẫn giữ vai trò tạo metadata trong bộ nhớ.

## 10. Những lỗi thường gặp

### Lỗi 1: Cho rằng factory đã thực thi step

```java
StepExecution step = MetaDataInstanceFactory.createStepExecution();
assertEquals(10, step.getReadCount()); // Sai kỳ vọng: chưa có reader chạy.
```

Muốn test logic khi đã đọc 10 item, **gán có chủ đích** `step.setReadCount(10)`. Muốn xác nhận một reader thực sự đã đọc 10 item, phải thực thi logic reader hoặc chạy step trong một bài test thích hợp.

### Lỗi 2: Đặt nhầm key vào job context thay vì step context

```java
step.getExecutionContext().putString("cursor", "C-10");
```

Lệnh trên chỉ phù hợp khi mã được kiểm thử đọc `stepExecutionContext['cursor']`. Nếu mã đọc `jobExecutionContext['cursor']`, hãy thiết lập `step.getJobExecution().getExecutionContext()`.

### Lỗi 3: Dùng ID mặc định như ID bền vững

Các ID `12L`, `123L`, `1234L` là tiện ích tạo fixture. Không dùng chúng để suy luận sự tồn tại của bản ghi trong bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` hay `BATCH_STEP_EXECUTION`. Trong test liên quan repository, ID hợp lệ phải do repository thực sự quản lý.

### Lỗi 4: Truy cập bean `@StepScope` khi chưa có scope

`MetaDataInstanceFactory` không đăng ký hoặc kích hoạt Spring scope. Với test có bean proxy `@StepScope`, hãy dùng listener tích hợp với Spring Test hoặc `StepScopeTestUtils.doInStepScope(...)`; bảo đảm scope đã được đăng ký trong `ApplicationContext`.

### Lỗi 5: Dùng metadata giả để chứng minh restart thật

Việc đặt `ExecutionContext` chứa checkpoint chỉ giúp kiểm tra hàm xử lý **đọc và phản ứng** với checkpoint ấy. Nó không kiểm tra quá trình lưu/khôi phục checkpoint giữa hai lần chạy, cách Spring Batch xác định restartability hay cách repository xử lý cùng job instance. Những hành vi đó cần integration test.

### Lỗi 6: Trộn import Spring Batch 5.x và 6.x

Nếu IDE báo không tìm thấy `StepExecution`, `JobExecution` hoặc `ExecutionContext`, kiểm tra phiên bản thư viện trước khi thay đổi logic test. Package của một số kiểu đã dịch chuyển ở 6.x, trong khi tên phương thức của factory rất giống nhau. Cũng cần bảo đảm `spring-batch-test` và runtime Spring Batch dùng các phiên bản tương thích.

## 11. Quy trình áp dụng vào dự án

Khi viết test cho một thành phần Spring Batch, có thể đi theo thứ tự:

1. **Xác định đầu vào thực sự:** listener cần read count, processor cần job parameter, bean `@StepScope` cần execution context, hay logic cần tên step?
2. **Chọn overload ngắn nhất:** `createStepExecution()` cho test đơn giản; overload nhận `JobParameters`/`ExecutionContext` khi cần giá trị tương ứng; overload nhận `JobExecution` khi cần kiểm soát quan hệ cha–con.
3. **Thiết lập đúng phạm vi:** sử dụng getter của step, job execution, hoặc job parameters theo đúng API mà code sản xuất đọc.
4. **Gọi đúng thành phần cần test:** listener/hàm nghiệp vụ trực tiếp cho unit test; mở step scope khi test bean có `@StepScope`.
5. **Khẳng định kết quả có ý nghĩa:** status trả về, checkpoint đọc được, đường dẫn xử lý, bộ đếm, exception, hoặc giá trị nghiệp vụ.
6. **Bổ sung integration test** khi mục tiêu bao gồm lưu metadata, transaction, restart hoặc chạy flow thực.

### Bài tập thực hành

Viết một listener tên `SkipThresholdListener`: nếu `stepExecution.getSkipCount()` lớn hơn 5, `afterStep(...)` trả về `ExitStatus.FAILED`; ngược lại trả `ExitStatus.COMPLETED`.

- Dùng `MetaDataInstanceFactory.createStepExecution("validateOrders", 100L)` để dựng dữ liệu cho nhánh `skipCount = 0`.
- Dựng trường hợp ranh giới `skipCount = 5` và trường hợp vượt ngưỡng `skipCount = 6`.
- Đặt `setReadSkipCount(...)`, `setProcessSkipCount(...)` hoặc `setWriteSkipCount(...)` phù hợp với cách listener đọc số lượt skip; nếu listener đọc tổng, hãy đảm bảo fixture phản ánh tổng đó.
- Thử mở rộng: thêm `JobParameters` tên `maxSkips`, đọc giá trị từ `stepExecution.getJobParameters()`, rồi kiểm tra hai cấu hình ngưỡng khác nhau.

Bài tập này thể hiện đúng giá trị của factory: **đặt metadata vào trạng thái kiểm thử mong muốn mà không phải chạy một job để tạo ra trạng thái đó**.

## 12. Tài liệu tham khảo chính thức

- [Spring Batch 5.2.6 — `MetaDataInstanceFactory` Javadoc](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/MetaDataInstanceFactory.html): toàn bộ overload và các hằng số mặc định.
- [Spring Batch 6.0.5 — `MetaDataInstanceFactory` Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/MetaDataInstanceFactory.html): API của dòng 6.x.
- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): dùng factory trong test, kiểm thử step scope và so sánh với chạy job/step thực.
- [Spring Batch 5.2 — `StepScopeTestUtils` Javadoc](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/StepScopeTestUtils.html): mở scope tạm cho callback.

