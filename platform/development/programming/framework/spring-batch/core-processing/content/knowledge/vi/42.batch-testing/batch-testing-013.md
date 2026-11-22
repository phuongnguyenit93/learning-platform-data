# Kiểm thử listener trong Spring Batch

## 1. Listener cần được kiểm thử như thế nào?

Trong Spring Batch, **listener** là nơi ứng dụng thực hiện công việc ở các mốc của vòng đời `Job`, `Step`, `Chunk` và từng item: ghi log, thu thập số liệu, đánh dấu dữ liệu lỗi, gửi thông báo hoặc điều chỉnh `ExitStatus`. Việc một phương thức listener chạy đúng khi gọi trực tiếp chưa đủ để bảo đảm listener được **đăng ký vào job/step**, được Spring Batch gọi **đúng thời điểm**, và ứng xử đúng trước **retry, skip, rollback, thất bại hoặc restart**.

Ví dụ, một job nhập ba dòng `["A", "BAD", "C"]`, trong đó processor ném lỗi với `"BAD"` và step cho phép bỏ qua một dòng. Ta cần phân biệt:

- `ItemProcessListener.onProcessError`: được gọi khi processor ném lỗi; một lỗi có thể được retry, vì vậy callback báo lỗi **không khẳng định item cuối cùng bị bỏ qua**.
- `SkipListener.onSkipInProcess`: được gọi khi hệ thống quyết định thực sự bỏ qua item `"BAD"`.
- `StepExecutionListener.afterStep`: nhận `StepExecution` để đọc `processSkipCount` hoặc điều chỉnh `ExitStatus`.
- `ChunkListener.afterChunk`: chạy sau khi chunk đã commit; `ItemWriteListener.afterWrite` chạy trước commit, nên không nên đồng nhất “đã gọi afterWrite” với “dữ liệu đã được commit”.

Một chiến lược kiểm thử hợp lý gồm ba lớp:

| Lớp kiểm thử | Cách thực hiện | Chứng minh điều gì? |
|---|---|---|
| **Unit test** | Khởi tạo listener và đối tượng `StepExecution` / `JobExecution`, gọi callback trực tiếp | Quy tắc nghiệp vụ, nhánh thành công/thất bại, cập nhật `ExecutionContext`, giá trị trả về |
| **Step integration test** | Chạy step thật bằng `spring-batch-test`, cố tình tạo lỗi ở reader/processor/writer | Listener đã đăng ký và được framework gọi đúng sự kiện; `skipCount`, `writeCount`, dữ liệu đầu ra phù hợp |
| **Job integration test** | Chạy toàn job qua `JobLauncherTestUtils.launchJob` | `JobExecutionListener`, luồng nhiều step, trạng thái cuối cùng và hiệu ứng trên hệ thống ngoài |

**Phạm vi phiên bản:** Các import và ví dụ Java bên dưới nhắm **Spring Batch 5.2.x, Spring Boot 3.x, Java 17+, JUnit Jupiter (JUnit 5)**. Ở Spring Batch 5, callback ghi dữ liệu nhận `Chunk<? extends T>`, không dùng chữ ký `List<T>` của các ví dụ Spring Batch đời cũ. Spring Batch 6 đã tổ chức lại một số package và test utility (ví dụ `JobOperatorTestUtils`), nên cần đối chiếu API của phiên bản dự án trước khi sao chép nguyên import.

## 2. Chọn đúng callback cần kiểm thử

| Listener | Callback tiêu biểu | Tình huống kiểm thử cần có |
|---|---|---|
| `JobExecutionListener` | `beforeJob`, `afterJob` | Job hoàn thành, job thất bại; thông báo/trạng thái được ghi đúng |
| `StepExecutionListener` | `beforeStep`, `afterStep` | Chuẩn bị `ExecutionContext`, đếm skip, trả về `ExitStatus` tùy điều kiện |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Chunk commit thành công; rollback; không coi callback lỗi là commit |
| `ItemReadListener<T>` | `beforeRead`, `afterRead`, `onReadError` | Đọc thành công, đọc lỗi, đọc kết thúc (reader trả `null`) |
| `ItemProcessListener<I,O>` | `beforeProcess`, `afterProcess`, `onProcessError` | Xử lý bình thường, lọc item (processor trả `null`), exception |
| `ItemWriteListener<O>` | `beforeWrite`, `afterWrite`, `onWriteError` | Ghi thành công; writer ném lỗi; retry làm callback lặp lại |
| `SkipListener<I,O>` | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Lỗi được skip thật sự ở từng giai đoạn; không nhầm với lỗi đã retry thành công |

Sơ đồ đơn giản cho một chunk thành công:

```text
beforeStep
  beforeChunk             (đã bắt đầu transaction)
    beforeRead -> afterRead
    beforeProcess -> afterProcess
    ...                   (lặp cho các item)
    beforeWrite -> afterWrite
    onSkipInX              (nếu có item được skip)
  COMMIT
  afterChunk              (sau commit)
afterStep
```

Khi chunk bị rollback, framework có thể gọi `afterChunkError`, sau đó retry/scan lại item theo cấu hình fault tolerance. Vì vậy, **đừng viết test giả định tất cả callback của listener chỉ chạy đúng một lần** trong mọi đường đi. Kiểm chứng theo loại listener, cấu hình retry/skip, số lần commit và dữ liệu cuối cùng.

## 3. Chuẩn bị môi trường test

Trong dự án Spring Boot dùng Maven, cần có thư viện chạy batch, Spring Batch Test và JUnit 5. Ví dụ dependency (phiên bản do Spring Boot BOM quản lý):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.batch</groupId>
        <artifactId>spring-batch-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Với dự án Gradle, khai báo các dependency tương ứng bằng `implementation` và `testImplementation`/`testRuntimeOnly`. H2 chỉ là lựa chọn thuận tiện cho kiểm thử tích hợp; nếu job sử dụng hành vi riêng của PostgreSQL, SQL Server hoặc Oracle, nên có thêm kiểm thử trên chính loại cơ sở dữ liệu đó.

Hai tiện ích chính của `spring-batch-test` ở dòng 5.x:

- `MetaDataInstanceFactory` tạo `JobExecution` / `StepExecution` giả lập có dữ liệu metadata hợp lệ để unit test, không cần chạy job.
- `@SpringBatchTest` hỗ trợ test context và cung cấp `JobLauncherTestUtils` / `JobRepositoryTestUtils`. `launchStep("stepName")` chạy riêng một step; `launchJob(...)` chạy toàn job. Nếu context có nhiều bean `Job`, cần chỉ định job cần kiểm thử cho `JobLauncherTestUtils`.

Không nên dùng `@SpringBootTest` cho mọi unit test vì tải toàn bộ Spring context tốn thời gian và có thể che khuất lỗi của chính listener.

## 4. Unit test `StepExecutionListener`: logic và `ExitStatus`

Giả sử yêu cầu nghiệp vụ là đánh dấu step đã bắt đầu trong `ExecutionContext`; nếu step kết thúc thành công nhưng có item bị skip, trả về exit code `COMPLETED_WITH_SKIPS`. Với step thất bại hoặc không có skip, không thay đổi exit code.

**Mã production — `ImportStepListener.java`:**

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class ImportStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        stepExecution.getExecutionContext()
                .putString("import.listener.started", "yes");
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus("COMPLETED_WITH_SKIPS");
        }
        return null; // Giữ nguyên ExitStatus hiện có.
    }
}
```

**Unit test — `ImportStepListenerTest.java`:**

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class ImportStepListenerTest {

    private ImportStepListener listener;
    private StepExecution stepExecution;

    @BeforeEach
    void setUp() {
        listener = new ImportStepListener();
        stepExecution = MetaDataInstanceFactory.createStepExecution();
    }

    @Test
    void beforeStep_shouldSetContextMarker() {
        listener.beforeStep(stepExecution);

        assertEquals(
                "yes",
                stepExecution.getExecutionContext()
                        .getString("import.listener.started")
        );
    }

    @Test
    void afterStep_shouldReturnCustomExitStatus_whenCompletedWithSkips() {
        stepExecution.setStatus(BatchStatus.COMPLETED);
        stepExecution.setProcessSkipCount(2);

        ExitStatus result = listener.afterStep(stepExecution);

        assertNotNull(result);
        assertEquals("COMPLETED_WITH_SKIPS", result.getExitCode());
    }

    @Test
    void afterStep_shouldNotHideFailure() {
        stepExecution.setStatus(BatchStatus.FAILED);
        stepExecution.setProcessSkipCount(2);

        assertNull(listener.afterStep(stepExecution));
    }

    @Test
    void afterStep_shouldKeepNormalCompletion_whenNoSkips() {
        stepExecution.setStatus(BatchStatus.COMPLETED);

        assertNull(listener.afterStep(stepExecution));
    }
}
```

Các ca trên có giá trị vì chúng kiểm tra **đầu vào và trạng thái đầu ra**, chứ không chỉ xác nhận phương thức “không ném exception”. `StepExecution.getSkipCount()` tổng hợp skip tại read/process/write; dùng `setProcessSkipCount(...)` để mô phỏng đúng một thành phần trong tổng này.

Phân biệt hai khái niệm:

- `BatchStatus` mô tả trạng thái thực thi do framework quản lý, chẳng hạn `COMPLETED` hoặc `FAILED`.
- `ExitStatus` là mã kết thúc có thể dùng để quyết định nhánh tiếp theo của job (ví dụ `.on("COMPLETED_WITH_SKIPS")`).

`afterStep` trả về `null` có nghĩa là không góp thêm exit status. Spring Batch kết hợp `ExitStatus` trả về từ listener với exit status của step; không nên giả định callback tự ý chuyển một step đã `FAILED` thành `COMPLETED`. Một unit test gọi `afterStep` trực tiếp chỉ xác nhận giá trị trả về; **muốn xác nhận flow thực tế phải chạy step/job trong integration test**.

## 5. Unit test callback lỗi và skip

Một ứng dụng có thể lưu danh sách mã bản ghi bị từ chối để xuất báo cáo. Listener nên chỉ ghi nhận sự kiện `onSkipInProcess`; quyết định bản ghi có được skip hay không thuộc cấu hình của step.

**Mã production — `RejectedItemListener.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.batch.core.SkipListener;

public class RejectedItemListener implements SkipListener<String, String> {

    private final List<String> rejectedIds = new ArrayList<>();

    @Override
    public void onSkipInProcess(String item, Throwable error) {
        rejectedIds.add(item);
    }

    public List<String> rejectedIds() {
        return List.copyOf(rejectedIds);
    }
}
```

**Unit test:**

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class RejectedItemListenerTest {

    @Test
    void onSkipInProcess_shouldRecordRejectedItem() {
        RejectedItemListener listener = new RejectedItemListener();

        listener.onSkipInProcess(
                "customer-42",
                new IllegalArgumentException("Invalid email")
        );

        assertEquals(List.of("customer-42"), listener.rejectedIds());
    }
}
```

Test này xác nhận **logic của callback**, nhưng **không chứng minh callback chỉ chạy khi skip xảy ra**, vì ta đã gọi trực tiếp phương thức. Để phân biệt một lần lỗi được retry thành công với một lần lỗi thực sự bị skip, cần chạy step fault-tolerant như phần tiếp theo.

Một lưu ý về thiết kế: `ArrayList` trong ví dụ phù hợp với unit test hoặc một listener mới được tạo cho mỗi lần thực thi. Với singleton listener dùng chung nhiều job/step chạy song song, không lưu trạng thái theo từng lần chạy trong field như vậy; ưu tiên `ExecutionContext`, vùng lưu trữ gắn với execution, hoặc một cơ chế ghi nhận an toàn theo `jobExecutionId`/`stepExecutionId`.

## 6. Integration test: xác minh listener được Spring Batch gọi thật

Ví dụ dưới đây tạo step đọc ba chuỗi `"ok", "bad", "end"`. Processor cố ý ném `IllegalArgumentException` với `"bad"`; step cho phép một lần skip. Ta kiểm tra đồng thời **trạng thái step**, **số lượng item** và **callback được gọi**.

Đây là một lớp test độc lập về cấu hình để minh họa đầy đủ việc đăng ký listener. Dùng Spring Boot 3.x, Spring Batch 5.x và H2 trong `test` classpath:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.SkipListener;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
    classes = SkipListenerIntegrationTest.TestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class SkipListenerIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private TrackingSkipListener trackingSkipListener;

    @BeforeEach
    void resetListener() {
        trackingSkipListener.clear();
    }

    @Test
    void launchStep_shouldInvokeSkipListenerForRejectedItem()
            throws Exception {

        JobExecution jobExecution =
                jobLauncherTestUtils.launchStep("importStep");

        StepExecution stepExecution = jobExecution
                .getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
        assertEquals(3L, stepExecution.getReadCount());
        assertEquals(2L, stepExecution.getWriteCount());
        assertEquals(1L, stepExecution.getProcessSkipCount());
        assertEquals(List.of("bad"), trackingSkipListener.skipped());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        TrackingSkipListener trackingSkipListener() {
            return new TrackingSkipListener();
        }

        @Bean
        ItemReader<String> reader() {
            return new ListItemReader<>(List.of("ok", "bad", "end"));
        }

        @Bean
        Step importStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                ItemReader<String> reader,
                TrackingSkipListener listener) {

            return new StepBuilder("importStep", jobRepository)
                    .<String, String>chunk(2, transactionManager)
                    .reader(reader)
                    .processor(item -> {
                        if ("bad".equals(item)) {
                            throw new IllegalArgumentException("Rejected");
                        }
                        return item.toUpperCase();
                    })
                    .writer(chunk -> { /* Writer giả lập */ })
                    .faultTolerant()
                    .skip(IllegalArgumentException.class)
                    .skipLimit(1)
                    .listener(listener)
                    .build();
        }

        @Bean
        Job importJob(JobRepository jobRepository, Step importStep) {
            return new JobBuilder("importJob", jobRepository)
                    .start(importStep)
                    .build();
        }
    }

    static class TrackingSkipListener
            implements SkipListener<String, String> {

        private final List<String> skipped = new ArrayList<>();

        @Override
        public void onSkipInProcess(String item, Throwable error) {
            skipped.add(item);
        }

        List<String> skipped() {
            return List.copyOf(skipped);
        }

        void clear() {
            skipped.clear();
        }
    }
}
```

Vì test trên chỉ khởi chạy step một lần, `ListItemReader` được tạo trong bean cấu hình là đủ để minh họa. Trong bộ test có nhiều lần khởi chạy trên cùng `ApplicationContext`, cần tạo reader mới cho từng execution (thường dùng bean `@StepScope`) hoặc dựng lại context, vì `ListItemReader` có trạng thái vị trí đọc.

**Tại sao các assertion này có ý nghĩa?**

1. `BatchStatus.COMPLETED` cho thấy một item xấu không làm step thất bại khi `skipLimit(1)` còn cho phép.
2. `readCount=3`, `writeCount=2` và `processSkipCount=1` xác nhận xử lý thực của batch, thay vì chỉ “có sự kiện được ghi lại”.
3. Danh sách `["bad"]` xác nhận dữ liệu truyền vào `SkipListener` đúng item bị từ chối.
4. Có dòng `.listener(listener)` trong step config: nếu bỏ đăng ký, test sẽ quan sát `processSkipCount=1` nhưng `skipped()` rỗng và phát hiện lỗi wiring.

Trong một ứng dụng thật, thay writer giả lập bằng writer ghi vào bảng test hoặc nơi lưu trữ có thể kiểm tra. Khi đó, nên assert thêm **không tồn tại item xấu ở đầu ra** và **chỉ có item hợp lệ được commit**.

### Test một lần lỗi chưa vượt giới hạn skip

Để xác minh listener **không được gọi** cho trường hợp lỗi khiến step thất bại, tạo một biến thể cấu hình `skipLimit(0)` (hoặc exception không thuộc `.skip(...)`). Kỳ vọng:

```text
Step BatchStatus      = FAILED
processSkipCount      = 0
TrackingSkipListener  = không ghi "bad"
failureExceptions     = chứa nguyên nhân gây lỗi
```

Điều này phân biệt rõ “đã phát sinh exception” với “đã skip”. Nếu cho phép retry, còn phải thử trường hợp lỗi lần đầu rồi thành công ở lần tiếp theo: `onProcessError` có thể được gọi, nhưng `SkipListener` không phải báo một skip đã hoàn tất.

## 7. Kiểm thử listener dựa trên annotation

Spring Batch cho phép viết callback bằng annotation trên một đối tượng Java bình thường:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.annotation.AfterStep;
import org.springframework.batch.core.annotation.BeforeStep;

public class AnnotatedAuditListener {

    @BeforeStep
    public void markStart(StepExecution stepExecution) {
        stepExecution.getExecutionContext().put("audit.started", true);
    }

    @AfterStep
    public void markEnd(StepExecution stepExecution) {
        stepExecution.getExecutionContext().put("audit.finished", true);
    }
}
```

Đăng ký đối tượng với step builder:

```java
new StepBuilder("myStep", jobRepository)
    .<String, String>chunk(10, transactionManager)
    .reader(reader)
    .writer(writer)
    .listener(new AnnotatedAuditListener())
    .build();
```

Unit test gọi `markStart(...)` và `markEnd(...)` trực tiếp **không kiểm tra annotation có được Spring Batch phát hiện hay không**. Hãy dùng `launchStep("myStep")` để xác nhận cả hai khóa `audit.started` và `audit.finished` trong `StepExecution.getExecutionContext()` đều là `true`.

Tương tự, một lớp gắn `@BeforeJob` / `@AfterJob` phải được đăng ký với **job**, rồi kiểm thử bằng `launchJob(...)`. `launchStep(...)` tạo một job bao quanh riêng để chạy step, vì vậy không dùng nó để khẳng định listener của job gốc đã được gọi.

## 8. Những ca lỗi nên mô phỏng có chủ đích

### 8.1. Listener ném exception

Thử cho một callback như `beforeStep` hoặc `beforeChunk` ném `IllegalStateException`. Chạy step thực và kiểm tra `BatchStatus.FAILED` cùng nguyên nhân lỗi được ghi lại. Đây là kiểm thử hành vi vận hành: exception ở listener có thể làm gián đoạn step.

Riêng `StepExecutionListener.afterStep` có hành vi đặc biệt theo API: exception từ callback này được framework ghi log và không tự đổi exit status của step. Vì vậy không suy diễn rằng tất cả callback “ném exception thì job fail” như nhau; phải đối chiếu hợp đồng từng callback và kiểm thử đường chạy thật.

### 8.2. Retry khác skip

Giả sử writer thất bại ở lần ghi đầu tiên nhưng thành công ở lần retry:

- `onWriteError` có thể được gọi dù sau cùng `writeCount` vẫn tăng.
- `onSkipInWrite` chỉ có ý nghĩa khi một item được quyết định skip.
- Không assert cứng số lần `beforeWrite`/`onWriteError` nếu thay đổi retry/rollback policy có thể làm thay đổi số lần thử. Hãy kiểm tra điều kiện nghiệp vụ: dữ liệu đầu ra, `writeSkipCount` và lịch sử callback thích hợp.

### 8.3. Thời điểm commit và rollback

| Callback | Mối quan hệ với transaction | Kỳ vọng test |
|---|---|---|
| `beforeChunk` | Bên trong transaction, trước khi đọc item | Ghi nhận bắt đầu chunk |
| `afterWrite` | Sau lời gọi writer, **trước commit** | Chưa kết luận dữ liệu được commit |
| `afterChunk` | Sau chunk commit thành công, ngoài transaction | Sự kiện thành công ở cấp chunk |
| `afterChunkError` | Sau khi chunk bị đánh dấu rollback; callback gọi sau rollback | Ghi nhận lỗi, không tính thành công |
| `onSkipInRead/Process/Write` | Framework trì hoãn thông báo skip tới thời điểm thích hợp trước commit | Chỉ kiểm tra item bị skip thực sự |

Nếu callback lỗi phải lưu bản ghi audit dù transaction chính rollback, cân nhắc một transaction riêng như `PROPAGATION_REQUIRES_NEW` và **test bằng cơ sở dữ liệu thực sự có transaction**; kiểm thử chỉ với mock không thể chứng minh ranh giới commit.

### 8.4. Thực thi lại và cô lập dữ liệu

Với retry/restart, một listener có thể gặp lại cùng mã nghiệp vụ trong các execution khác nhau. Thiết kế test cần phân biệt `JobInstance`, `JobExecution` và `StepExecution`. Với hiệu ứng ngoài hệ thống như email, message hoặc HTTP request, nên thử cơ chế chống gửi trùng / idempotency theo một khóa nghiệp vụ phù hợp, vì rollback của database không hoàn tác được lời gọi ra ngoài.

## 9. Kiểm thử `@StepScope` và dữ liệu runtime

Khi listener hoặc thành phần nó gọi dựa trên `jobParameters`, `StepExecution` hoặc `ExecutionContext`, test có thể cần tạo môi trường step:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;

class StepContextTest {

    @Test
    void shouldReadValueFromStepContext() throws Exception {
        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution();

        stepExecution.getExecutionContext().putString(
                "source.file", "input.csv"
        );

        String actual = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> stepExecution.getExecutionContext()
                        .getString("source.file")
        );

        assertEquals("input.csv", actual);
    }
}
```

Đoạn này minh họa cách mở step scope giả lập. Nó **không tự kiểm tra proxy `@StepScope`** vì lambda đọc trực tiếp `StepExecution`; muốn kiểm thử một bean thực sự dùng late binding, cần lấy bean `@StepScope` từ Spring test context bên trong scope này, rồi assert giá trị bean nhận được.

Ngoài `StepScopeTestUtils`, `@SpringBatchTest` có `StepScopeTestExecutionListener` hỗ trợ việc đặt `StepExecution` cho các test dùng Spring TestContext. Khi không có nhu cầu kiểm thử scope hoặc container, unit test trực tiếp thường ngắn gọn và dễ tìm nguyên nhân lỗi hơn.

## 10. Đặt assertion theo hợp đồng sự kiện

Các assertion mạnh thường kiểm tra **kết quả quan sát được**:

- **Step listener:** `ExecutionContext` sau `beforeStep`, mã `ExitStatus` sau `afterStep`; nếu chuyển nhánh job, assert step tiếp theo có/không được chạy.
- **Job listener:** trạng thái `JobExecution` và thông báo/audit được ghi đúng cho success/failure; test bằng `launchJob`.
- **Chunk listener:** không coi `afterWrite` là commit; xác minh `afterChunk` trong tình huống thành công và `afterChunkError` khi rollback.
- **Item listener:** item truyền vào callback, exception đúng loại, danh sách item được xử lý hoặc lưu ra đích.
- **Skip listener:** `readSkipCount`, `processSkipCount`, `writeSkipCount` và item thực sự bị skip; tránh dùng `on*Error` thay thế kiểm tra skip.

Nên tránh các anti-pattern sau:

| Anti-pattern | Vì sao gây test kém tin cậy? | Cách cải thiện |
|---|---|---|
| Chỉ gọi callback trực tiếp rồi kết luận listener đã được đăng ký | Bỏ sót lỗi cấu hình `.listener(...)` | Bổ sung một integration test chạy step/job |
| Assert đúng một lần gọi cho mọi callback khi có retry | Rollback/retry có thể gọi lại các callback xử lý | Kiểm tra kết quả cuối cùng và loại sự kiện |
| Dùng `Thread.sleep(...)` để đợi listener | Test chậm và không ổn định | Chạy job đồng bộ hoặc chờ bằng cơ chế đồng bộ có điều kiện rõ |
| Dùng một bean listener mutable cho nhiều test song song | Rò dữ liệu từ test khác hoặc job khác | Khởi tạo mới, reset có kiểm soát, hoặc lưu state theo execution |
| Chỉ mock database mà khẳng định transaction đã commit | Mock không thực thi transaction | Test với DB có transaction và kiểm tra dữ liệu cuối |
| Dùng lại `JobParameters` cho nhiều lần khởi chạy job đã `COMPLETED` | Spring Batch có thể chặn chạy lại cùng `JobInstance` | Tạo tham số định danh riêng cho từng execution hoặc làm sạch metadata test |

## 11. Bài tập thực hành

Thiết kế một job nhập danh sách đơn hàng có bốn dòng: `O-1` hợp lệ, `O-2` thiếu mã khách hàng, `O-3` hợp lệ và `O-4` gặp lỗi writer tạm thời. Hãy bổ sung:

1. `ItemProcessListener` ghi nhận exception của `O-2`.
2. `SkipListener` ghi nhận `O-2` nếu step được phép skip.
3. `ItemWriteListener` ghi nhận lỗi tạm thời của `O-4`; cấu hình retry một lần và writer thành công ở lần thứ hai.
4. `StepExecutionListener` trả exit code `COMPLETED_WITH_SKIPS` khi step thành công có skip.
5. Unit tests kiểm tra quy tắc từng listener và integration test kiểm tra `processSkipCount=1`, `writeSkipCount=0`, exit code mong đợi cùng đúng ba đơn hàng hợp lệ ở nơi lưu.

Khi kiểm tra, giải thích tại sao callback báo lỗi ở writer **không đồng nghĩa** với `onSkipInWrite`. Sau đó đổi policy sang không cho phép skip để quan sát việc status và listener thay đổi thế nào. Trường hợp này giúp kiểm tra cả logic riêng lẻ lẫn việc các listener phối hợp với chính sách fault tolerance.

## 12. Tài liệu đối chiếu

- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils`, step-scope test.
- [Spring Batch 5.2 — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html): các callback, thời điểm gọi và quan hệ transaction.
- [Spring Batch 5.2 — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/5.2/step/controlling-flow.html): phân biệt `BatchStatus`, `ExitStatus` và lựa chọn nhánh job.
- [Spring Batch 5.2 API — SkipListener](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/SkipListener.html) và [ChunkListener](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/ChunkListener.html): chữ ký method và lưu ý callback.
- Với Spring Batch 6, tham khảo [tài liệu testing hiện hành](https://docs.spring.io/spring-batch/reference/testing.html) trước khi đổi import/utility.
