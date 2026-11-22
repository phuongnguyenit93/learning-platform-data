# Tạo `JobParameters` ổn định trong test Spring Batch

Trong Spring Batch, `JobParameters` là tập tham số truyền vào mỗi lần chạy batch job: ngày xử lý, nguồn dữ liệu, mã tenant, chế độ xử lý hoặc một định danh nghiệp vụ. Khi kiểm thử, các tham số này cần được chuẩn bị **có chủ đích và có thể tái tạo**. Một bài test dùng `System.currentTimeMillis()`, `UUID.randomUUID()` hay `LocalDate.now()` ở mọi lần chạy có thể vô tình tạo một `JobInstance` mới, khiến khó tái hiện lỗi và làm sai ý nghĩa kiểm thử restart.

Mục tiêu của việc tạo `JobParameters` ổn định là:

- Cùng đầu vào kiểm thử sinh cùng tập tham số qua các lần chạy và trên các máy khác nhau.
- Mỗi kịch bản có dữ liệu rõ ràng để người đọc nhìn vào test biết job sẽ xử lý gì.
- Các test cần kiểm tra *cùng* một `JobInstance` giữ nguyên những tham số xác định danh tính.
- Các test cần *những* `JobInstance` khác nhau chủ động chọn giá trị khác nhau, không phụ thuộc may rủi.
- Đảm bảo lỗi kiểm thử phản ánh hành vi batch, thay vì tác động phụ của thời gian, môi trường hoặc metadata còn lại trong `JobRepository`.

## 1. `JobParameters` ảnh hưởng đến điều gì?

Trong Spring Batch, có thể hiểu danh tính logic của một lần xử lý bằng công thức:

```text
JobInstance = Job name + identifying JobParameters

JobInstance "importOrders", businessDate=2025-01-15, source=orders-v1
  |
  +-- JobExecution #1: FAILED
  |
  +-- JobExecution #2: COMPLETED   (chạy lại/restart cùng JobInstance)

JobInstance "importOrders", businessDate=2025-01-16, source=orders-v1
  |
  +-- JobExecution #3: COMPLETED   (JobInstance khác)
```

`JobExecution` là một **lần thử chạy**; một `JobInstance` có thể có nhiều `JobExecution`, chẳng hạn lần đầu thất bại rồi chạy lại thành công. Nếu một `JobInstance` đã hoàn tất, cố chạy lại nó bằng `JobRepository` thông thường sẽ bị từ chối (ví dụ `JobInstanceAlreadyCompleteException`).

Một `JobParameter` gồm tên, giá trị, kiểu và cờ **`identifying`**:

| Thuộc tính | Ví dụ | Tác động |
| --- | --- | --- |
| Tên (*key*) | `businessDate` | Dùng để truy xuất tham số qua key |
| Giá trị | `2025-01-15` | Dữ liệu job sử dụng khi xử lý |
| Kiểu | `String`, `Long`, `LocalDate`, ... | Quyết định API đọc/ghi và phép chuyển kiểu |
| `identifying=true` | `businessDate=2025-01-15` | Tham gia xác định `JobInstance` |
| `identifying=false` | `traceLabel=smoke-test` | Có thể được job đọc nhưng không làm thay đổi danh tính `JobInstance` |

Mặc định, các phương thức `addString`, `addLong`, `addDouble`... của `JobParametersBuilder` tạo **identifying parameter**. Muốn một tham số không tham gia định danh phải truyền `false` ở overload tương ứng.

> **Ổn định không đồng nghĩa với lúc nào cũng dùng một bộ tham số cho mọi test.** Trong unit test, có thể dùng bộ tham số cố định cho mọi lần chạy. Trong integration test có `JobRepository` lưu trạng thái, mỗi kịch bản chạy độc lập thường cần danh tính riêng, hoặc cần repository được cô lập/làm sạch giữa các lần chạy. Với bài test restart, ngược lại, phải giữ danh tính của cùng `JobInstance`.

## 2. Tạo bộ tham số cố định với `JobParametersBuilder`

Ví dụ dưới dùng Spring Batch 5.x, JUnit Jupiter và dữ liệu fixture tự đặt. Các giá trị được ghi rõ để tránh thay đổi theo đồng hồ hoặc máy chạy test.

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

final class BatchTestParameters {

    private BatchTestParameters() {
    }

    static JobParameters standard() {
        return forScenario("standard-import");
    }

    static JobParameters forScenario(String scenario) {
        return new JobParametersBuilder()
                .addString("businessDate", "2025-01-15", true)
                .addString("inputName", "orders-small-v1.csv", true)
                .addString("testScenario", scenario, true)
                .addString("traceLabel", "batch-test", false)
                .toJobParameters();
    }
}
```

Ý nghĩa lựa chọn:

- `businessDate`: ngày nghiệp vụ *cố định* để kết quả không phụ thuộc ngày chạy test.
- `inputName`: tên fixture *cố định*, cho biết bộ dữ liệu nào được xử lý. Nếu thay fixture làm thay đổi ý nghĩa lần xử lý, nó nên là identifying parameter.
- `testScenario`: tên kịch bản rõ ràng (`standard-import`, `empty-input`, `invalid-row`) để phân biệt các `JobInstance` khi những kịch bản này dùng chung repository.
- `traceLabel`: nhãn phục vụ quan sát; thay đổi nhãn không nên tạo `JobInstance` mới, nên đặt `identifying=false`.

`JobParametersBuilder` là đối tượng có thể thêm/sửa tham số trong quá trình dựng, còn `JobParameters` là tập tham số bất biến sau khi được tạo. Hàm factory nên tạo **builder mới cho mỗi lời gọi**. Không giữ một builder `static` rồi chỉnh sửa từ các test khác nhau, vì có thể làm rò rỉ dữ liệu giữa các test hoặc gây lỗi khi chạy song song.

Việc tạo tham số thuần túy này không cần database, `JobLauncher` hay Spring application context.

## 3. Test trực tiếp tính ổn định và cờ định danh

Một lớp test có thể xác nhận rằng hai lời gọi cùng kịch bản luôn có cùng dữ liệu, và các kịch bản khác nhau tạo identifying parameters khác nhau:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;

import static org.junit.jupiter.api.Assertions.*;

class BatchTestParametersTest {

    @Test
    void sameScenarioHasSameParameters() {
        JobParameters first = BatchTestParameters.forScenario("standard-import");
        JobParameters second = BatchTestParameters.forScenario("standard-import");

        assertEquals(first, second);
        assertEquals("2025-01-15", first.getString("businessDate"));
        assertEquals("orders-small-v1.csv", first.getString("inputName"));
        assertEquals("standard-import", first.getString("testScenario"));
    }

    @Test
    void scenarioKeyIntentionallyChangesIdentity() {
        JobParameters valid = BatchTestParameters.forScenario("valid-input");
        JobParameters empty = BatchTestParameters.forScenario("empty-input");

        assertNotEquals(
                valid.getIdentifyingParameters(),
                empty.getIdentifyingParameters());
    }

    @Test
    void tracingLabelDoesNotContributeToJobIdentity() {
        JobParameters params = BatchTestParameters.standard();

        assertFalse(params.getParameter("traceLabel").isIdentifying());
        assertTrue(params.getParameter("businessDate").isIdentifying());
        assertFalse(params.getIdentifyingParameters().containsKey("traceLabel"));
    }
}
```

`getIdentifyingParameters()` có trong Spring Batch 5.1+; với phiên bản cũ hơn, kiểm tra `isIdentifying()` trên các `JobParameter` hoặc duyệt map từ `getParameters()`. Không nên dùng phép so sánh toàn bộ `JobParameters` để kết luận rằng hai bộ tham số có cùng **danh tính job**, vì toàn bộ tập tham số còn chứa các trường `identifying=false`.

## 4. Phân biệt tham số ổn định và tham số tạo danh tính mới

Xem ba bộ tham số sau cho cùng một job tên `importOrders`:

| Bộ tham số | `businessDate` (identifying) | `testScenario` (identifying) | `traceLabel` (non-identifying) | Danh tính logic |
| --- | --- | --- | --- | --- |
| A | `2025-01-15` | `standard-import` | `run-a` | Instance A |
| B | `2025-01-15` | `standard-import` | `run-b` | **Cùng instance với A** |
| C | `2025-01-15` | `empty-input` | `run-a` | Instance khác A |

Nếu muốn **kiểm tra restart**, chuẩn bị A và dùng lại đúng tập identifying parameters sau một lần chạy thất bại. Nếu muốn kiểm tra **hai kịch bản hoàn toàn độc lập** trong cùng repository, dùng A và C. Nếu chỉ cần gắn thông tin debug mà không thay đổi instance, thay `traceLabel` như A và B.

Tuy vậy, `testScenario` là tham số tiện cho test, không nhất thiết thuộc hợp đồng nghiệp vụ của job thực tế. Đừng thêm một tham số định danh mới để né `JobInstanceAlreadyCompleteException` trong bài test vốn phải kiểm tra tính idempotent hoặc restart. Khi cần trung thực với production, giữ nguyên các tham số nghiệp vụ và cô lập `JobRepository` của test thay vì thay đổi định nghĩa danh tính.

## 5. Dùng bộ tham số trong test bean thuộc job/step scope

Các bean `@JobScope` hay `@StepScope` thường đọc tham số bằng Spring Expression Language:

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputName']}") String inputName) {
    // Chọn resource theo inputName rồi cấu hình reader.
    // Phần cấu hình FlatFileItemReader cụ thể tùy cấu trúc file fixture.
    return createReaderFor(inputName);
}
```

Trong test, giá trị phải được đặt trên **`JobExecution` gắn với scope**. Đối với test hạ tầng tối giản, `spring-batch-test` cung cấp `MetaDataInstanceFactory` để tạo metadata mà không cần chạy cả job:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.test.MetaDataInstanceFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JobExecutionParameterFixtureTest {

    @Test
    void jobExecutionCarriesTheFixedFixture() {
        JobParameters params = BatchTestParameters.forScenario("read-orders");

        JobExecution execution = MetaDataInstanceFactory.createJobExecution(
                "importOrders", 11L, 21L, params);

        assertEquals("2025-01-15",
                execution.getJobParameters().getString("businessDate"));
        assertEquals("orders-small-v1.csv",
                execution.getJobParameters().getString("inputName"));
    }
}
```

Đối với bài test thật sự gọi bean theo scope, có thể dùng `JobScopeTestUtils.doInJobScope(jobExecution, ...)` hoặc tạo `StepExecution` rồi dùng `StepScopeTestUtils.doInStepScope(stepExecution, ...)`. Cả hai cách đều giúp đưa **chính bộ tham số cố định** vào biểu thức `#{jobParameters[...]}`; không cần thay thế chúng bằng dữ liệu ngẫu nhiên.

Ví dụ tạo step metadata cho `@StepScope`:

```java
JobParameters params = BatchTestParameters.forScenario("reader-fixture");
StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution(params);

String path = StepScopeTestUtils.doInStepScope(
        stepExecution,
        () -> stepExecution.getJobParameters().getString("inputName"));

assertEquals("orders-small-v1.csv", path);
```

Đoạn trên cần thêm import `org.springframework.batch.core.StepExecution` và `org.springframework.batch.test.StepScopeTestUtils` cùng các static import JUnit tương ứng. Với bean thực tế, thay biểu thức trả về `path` bằng lời gọi đến bean `@StepScope` đã được inject trong Spring test context. Thời điểm gọi proxy thuộc scope phải nằm bên trong lambda.

## 6. Dùng trong integration test chạy job

Khi chạy job thật qua `JobLauncherTestUtils`, truyền `JobParameters` tường minh để kiểm soát đầu vào. Ví dụ sau minh họa JUnit Jupiter cùng Spring Batch 5.x trong dự án có cấu hình job và repository hợp lệ:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBatchTest
@SpringBootTest
class ImportOrdersJobIT {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void importsFixedInput() throws Exception {
        JobParameters parameters = BatchTestParameters.forScenario("importsFixedInput");

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

Ví dụ giả định application context có một job phù hợp để `JobLauncherTestUtils` chọn. Nếu có nhiều `Job`, hãy cấu hình rõ job cần chạy trong test, ví dụ `jobLauncherTestUtils.setJob(importOrdersJob)` ở `@BeforeEach`. `BatchTestParameters` ở mục 2 phải nằm trong cùng module test để sử dụng được.

**Lưu ý về repository:** Nếu `importsFixedInput` đã hoàn tất trong một `JobRepository` được giữ lại sau lần chạy trước, thực thi lại với cùng tên job và cùng identifying parameters sẽ không tạo một lần chạy mới. Đó là quy tắc bình thường của Spring Batch, không phải vì tham số được tạo sai.

Các hướng xử lý tùy mục tiêu:

1. **Integration test độc lập giữa các lần chạy CI:** dùng repository test riêng, database test độc lập hoặc làm sạch batch metadata một cách có kiểm soát giữa các kịch bản. Cố định tham số và cô lập trạng thái là cách dễ tái tạo nhất.
2. **Nhiều kịch bản trên cùng repository:** tạo một `testScenario` identifying với tên ổn định, khác nhau theo từng kịch bản. Điều này tách các test trong *một* lần chạy suite, nhưng tự nó không giải quyết việc lặp lại cả suite trên repository cũ.
3. **Kiểm tra restart:** dùng lại các identifying parameters của instance vừa thất bại và giữ trạng thái repository; không tăng `run.id`, không thêm timestamp, không tạo UUID mới.
4. **Chỉ test business logic không cần repository:** dùng fixture `JobParameters` với metadata do test tạo, và kiểm thử bean hoặc step phù hợp thay vì khởi chạy job đầy đủ.

Những overload `launchJob()` không có đối số của `JobLauncherTestUtils` có thể tự sinh tham số ngẫu nhiên để bảo đảm uniqueness. Chúng hữu ích trong một số smoke test, nhưng khi bài test phải tái tạo chính xác input hoặc kiểm tra danh tính, hãy gọi `launchJob(jobParameters)` với tham số tường minh.

## 7. Kiểm thử restart cần **cùng** identifying parameters

Giả sử một job xử lý dữ liệu ngày `2025-01-15` thất bại giữa chừng. Khi sửa lỗi hoặc thử tính restart, ta muốn lần chạy sau tiếp tục cùng công việc của ngày đó, chứ không tạo một job instance mới. Do đó, những tham số xác định instance phải được giữ nguyên:

```java
JobParameters original = new JobParametersBuilder()
        .addString("businessDate", "2025-01-15", true)
        .addString("inputName", "orders-small-v1.csv", true)
        .toJobParameters();

// Lần chạy đầu thất bại và JobRepository lưu trạng thái FAILED.
// Sau khi điều kiện gây lỗi được xử lý, chạy lại đúng instance:
JobParameters retry = new JobParametersBuilder(original)
        .toJobParameters();

assertEquals(original.getIdentifyingParameters(),
             retry.getIdentifyingParameters());
```

Đây là phần **chuẩn bị dữ liệu** cho test restart, chưa phải một test restart hoàn chỉnh. Một test restart đầy đủ cần job có khả năng restart, repository lưu lần chạy thất bại, điều kiện lỗi được giải quyết và assertion về lần thực thi tiếp theo. Nếu lần chạy đầu đã `COMPLETED`, việc gọi lại với cùng tham số sẽ bị từ chối theo chính sách hoàn tất instance; đó không phải trường hợp restart sau failure.

Không dùng `RunIdIncrementer` hoặc `.addLong("run.id", System.nanoTime())` chỉ để làm cho bài test restart chạy qua: thay đổi identifying parameter tạo một instance khác và có thể che mất lỗi liên quan đến checkpoint/`ExecutionContext`.

## 8. Thời gian, đường dẫn file và dữ liệu động

Các nguồn không ổn định thường xuất hiện ở nơi ít được chú ý:

| Dữ liệu | Dễ gây dao động | Thay bằng |
| --- | --- | --- |
| Ngày nghiệp vụ | `LocalDate.now()` | `LocalDate.of(2025, 1, 15)` hoặc một ngày cố định trong fixture |
| Timestamp | `Instant.now()` | `Instant.parse("2025-01-15T00:00:00Z")` hoặc injected `Clock.fixed(...)` |
| Định danh | `UUID.randomUUID()` | `caseId` hoặc `testScenario` ổn định, có ý nghĩa |
| Mã lần chạy | `System.currentTimeMillis()` | Hằng số/kịch bản cố định nếu test không cần một instance mới |
| Đường dẫn | Đường dẫn tuyệt đối trên máy lập trình viên | Fixture từ `src/test/resources`, tên resource tương đối hoặc `@TempDir` theo nhu cầu |
| Locale/múi giờ | Dùng format mặc định của hệ thống | Chuỗi ISO rõ ràng, `ZoneId`/`Locale` chỉ định tường minh |

Với code có phụ thuộc thời gian thực, đưa `Clock` vào thành phần dựng tham số giúp test điều khiển đồng hồ:

```java
import java.time.Clock;
import java.time.LocalDate;

static JobParameters forDay(Clock clock) {
    LocalDate day = LocalDate.now(clock);

    return new JobParametersBuilder()
            .addString("businessDate", day.toString(), true)
            .toJobParameters();
}

// Trong test:
Clock fixedClock = Clock.fixed(
        java.time.Instant.parse("2025-01-15T08:30:00Z"),
        java.time.ZoneOffset.UTC);
JobParameters params = forDay(fixedClock);
assertEquals("2025-01-15", params.getString("businessDate"));
```

`Clock.fixed(...)` giữ logic “lấy ngày hiện tại” của code nhưng khiến dữ liệu test có thể tái tạo. Nếu test không liên quan đến đồng hồ, dùng hằng số ngày thẳng trong fixture đơn giản hơn.

Khi dùng `@TempDir`, đường dẫn trên filesystem có thể khác ở mỗi lần chạy. Điều này bình thường đối với test đọc file, nhưng nếu biến đường dẫn tạm thành identifying parameter, mỗi lần chạy có thể vô tình là một `JobInstance` khác. Hãy cân nhắc truyền tham số là **tên fixture logic** và để phần đọc file resolve resource, hoặc xác nhận việc thay đổi đường dẫn thực sự có ý nghĩa định danh nghiệp vụ.

## 9. Thiết kế factory tham số cho cả bộ test

Một factory nhỏ và thuần túy giúp các test thống nhất key, kiểu dữ liệu và cờ định danh. Có thể định nghĩa các constant để tránh typo:

```java
final class JobParamKeys {
    static final String BUSINESS_DATE = "businessDate";
    static final String INPUT_NAME = "inputName";
    static final String TEST_SCENARIO = "testScenario";

    private JobParamKeys() {}
}

static JobParameters forTestCase(String scenario, String file) {
    return new JobParametersBuilder()
            .addString(JobParamKeys.BUSINESS_DATE, "2025-01-15", true)
            .addString(JobParamKeys.INPUT_NAME, file, true)
            .addString(JobParamKeys.TEST_SCENARIO, scenario, true)
            .toJobParameters();
}
```

Khi nhiều test dùng chung factory:

- Gọi factory ở mỗi test để nhận bộ `JobParameters` độc lập về cách tạo; không đưa `JobParametersBuilder` dùng chung vào field mutable.
- Gọi tên kịch bản theo hành vi cụ thể như `acceptsTwoOrders`, `rejectsMalformedPrice`, `restartsAfterReadFailure`.
- Không thêm các tham số không liên quan vào mọi test; một fixture càng nhỏ và có ý nghĩa thì lỗi càng dễ hiểu.
- Duy trì đúng kiểu dữ liệu mà code batch cần. `addLong("pageSize", 100L)` khác với `addString("pageSize", "100")` nếu downstream đọc `getLong("pageSize")`.
- Khi thêm key mới, chọn `identifying` dựa trên **danh tính nghiệp vụ của job**. Không nên mặc định tất cả các key có giá trị biến động đều là identifying, cũng không nên đặt hết thành non-identifying.

Một điểm cần phân biệt: `JobParameters` là các giá trị đầu vào của job; `ExecutionContext` là nơi Spring Batch/ứng dụng lưu trạng thái phát sinh trong quá trình xử lý. Không dùng `JobParameters` để giả lập checkpoint đã được ghi ở `ExecutionContext` trong test restart.

## 10. Những lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách tiếp cận |
| --- | --- | --- |
| Test chạy tốt trên máy cá nhân nhưng không ổn trên CI | Ngày, time zone hoặc thứ tự test ảnh hưởng tham số | Dùng giá trị cố định hoặc injected `Clock`, cô lập repository |
| Lúc chạy lại báo `JobInstanceAlreadyCompleteException` | Same job name + same identifying parameters đã `COMPLETED` | Cô lập/chuẩn bị repository cho integration test; chỉ dùng identity khác khi thật sự cần instance khác |
| Test restart thực ra xử lý từ đầu | Thêm timestamp/UUID/run ID làm thay đổi identity | Giữ nguyên identifying parameters của lần FAILED |
| Thêm nhãn debug khiến job bị coi là instance mới | `addString(key, value)` mặc định identifying | Chọn overload `addString(key, value, false)` |
| Reader không nhận được ngày hoặc đường dẫn | Sai key, sai kiểu, hoặc `JobExecution` của test không mang tham số mong muốn | Tập trung khởi tạo qua một factory và truyền vào execution thật sự được dùng |
| Hai test ảnh hưởng lẫn nhau | Dùng chung mutable builder hoặc repository có state cũ | Tạo builder mới và cô lập metadata của integration test |
| Test vẫn cho kết quả bất ngờ khi input file đổi | Tên fixture cố định nhưng nội dung file đã thay đổi | Version dữ liệu fixture, xác nhận test đang dùng đúng resource và cập nhật kỳ vọng một cách rõ ràng |

## 11. Ghi chú phiên bản và tài liệu tham khảo

Ví dụ dùng package của **Spring Batch 5.x**:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
```

Ở **Spring Batch 6.x**, các lớp liên quan đến job parameters được đặt trong package `org.springframework.batch.core.job.parameters`. Ngoài ra, một số test launcher API đổi hướng sang `JobOperatorTestUtils`; khi dùng 6.x, hãy đối chiếu API của phiên bản dự án. Các nguyên tắc về identifying parameters, deterministic fixtures và restart vẫn giữ nguyên.

Tài liệu chính thức:

- [Spring Batch Reference — Domain: JobInstance, JobExecution, JobParameters](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch 5.2 API — JobParametersBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParametersBuilder.html)
- [Spring Batch 5.2 API — JobParameters](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobParameters.html)
- [Spring Batch 5.2 API — MetaDataInstanceFactory](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/test/MetaDataInstanceFactory.html)
- [Spring Batch 5.2 API — JobLauncherTestUtils](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/test/JobLauncherTestUtils.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)

Một bộ `JobParameters` tốt cho test phải **dễ đọc, tái tạo được và thể hiện đúng danh tính job**. Hãy cố định dữ liệu đầu vào; chủ động chọn những key `identifying`; dùng factory đơn giản cho các kịch bản; và quyết định cách cô lập `JobRepository` dựa trên việc đang test chạy độc lập hay restart. Nhờ đó, cùng một bài test có thể chạy lại nhiều lần mà vẫn kiểm tra đúng hành vi Spring Batch cần chứng minh.
