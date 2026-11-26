# Kiểm thử scope trong partition của Spring Batch

> **Chương:** Step scope
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán. Bài này hướng dẫn kiểm thử việc cách ly bean/state theo worker `StepExecution`, đồng thời xác minh concurrency, checkpoint, retry/restart và tính đúng đắn của dữ liệu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **singleton**, `@JobScope`, `@StepScope` và cách Spring Batch xác định vòng đời của target bean trong một worker partition.
2. Dùng `StepScopeTestUtils.doInStepScope(...)` với các `StepExecution` giả lập để kiểm tra **late binding** từ `stepExecutionContext` và cách ly state.
3. Viết integration test chạy nhiều partition đồng thời, kiểm tra mỗi worker chỉ xử lý dữ liệu thuộc phạm vi được cấp.
4. Gây lỗi một worker, restart cùng `JobInstance` và xác minh những partition `COMPLETED` không bị chạy lại trái chính sách.
5. Phân biệt test scope trong JVM với kiểm thử **thread safety**, idempotency và transaction của toàn hệ thống.

## 1. Vì sao phải kiểm thử scope khi partitioning?

Manager của một partitioned step có thể tạo nhiều worker `StepExecution` sử dụng **cùng một định nghĩa `Step`**. Mỗi worker có context riêng, chẳng hạn:

| Worker | Partition key | `ExecutionContext` | Dữ liệu phải xử lý |
| --- | --- | --- | --- |
| A | `tenant-A` | `tenantId=A`, `minId=1`, `maxIdExclusive=1001` | Đơn hàng A, ID `[1,1001)` |
| B | `tenant-B` | `tenantId=B`, `minId=1001`, `maxIdExclusive=2001` | Đơn hàng B, ID `[1001,2001)` |

Nếu reader/processor là singleton có trường mutable `currentTenant`, worker B có thể ghi đè giá trị mà worker A đang sử dụng. Lỗi **cross-talk** như vậy thường không xuất hiện khi chạy tuần tự nhưng sẽ lộ ra khi tăng số worker.

~~~mermaid
flowchart TB
    M["Manager PartitionStep"] --> P["Partitioner: tên + ExecutionContext"]
    P --> H["PartitionHandler"]
    H --> A["Worker StepExecution A"]
    H --> B["Worker StepExecution B"]
    A --> PA["Target @StepScope A<br/>tenant=A; state A"]
    B --> PB["Target @StepScope B<br/>tenant=B; state B"]
    PA --> DA["Chỉ dữ liệu A"]
    PB --> DB["Chỉ dữ liệu B"]
~~~

Một bài test có ý nghĩa phải chứng minh **cả hai vế**: (1) target bean của hai `StepExecution` không trộn lẫn state, **và** (2) reader/writer thực sự xử lý đúng dữ liệu. Chỉ nhìn trạng thái job `COMPLETED` hoặc đếm số item là chưa đủ.

### Các loại lỗi cần phân biệt

| Lỗi | Dấu hiệu | Scope test có tự phát hiện không? |
| --- | --- | --- |
| Singleton mutable dùng chung | Tenant/cursor của A bị B sửa | Có thể, khi kiểm tra instance/state hoặc ép interleaving |
| Partition range chồng lấn | Cùng ID được hai worker đọc | **Không**; cần kiểm tra partitioner, SQL predicate và input |
| Reader stateful dùng đa luồng trong **một** worker | Cursor/checkpoint bị race | **Không tự động**; `@StepScope` không tạo target theo thread |
| Worker retry gây ghi trùng | DB có hai tác dụng phụ cho một event | Cần kiểm thử transaction và idempotency tại đích |
| ThreadLocal/MDC bị tái sử dụng | Log hoặc routing mang tenant của worker trước | Cần kiểm thử thread reuse và cleanup |
| Remote worker dùng chung file output | Worker khác JVM ghi đè file | Cần test shared resource/namespace ở đích |

## 2. Hiểu đúng vòng đời trước khi viết test

`@StepScope` tạo **target bean theo `StepExecution` đang hoạt động**, thông qua scoped proxy trong Spring container. Proxy có thể là một bean được inject một lần, nhưng **target phía sau proxy** thay đổi tùy step execution.

~~~text
Một bean proxy: ordersReader (được inject trong định nghĩa worker Step)
    |
    +-- StepExecution A đang active --> target reader A
    |
    +-- StepExecution B đang active --> target reader B
~~~

Vì thế:

- **Hai proxy reference giống nhau không chứng minh hai worker dùng chung target.** Hãy kiểm tra state/identity của target khi active ở từng scope.
- **Hai `StepExecution` khác nhau phải có dữ liệu ràng buộc riêng.** `@Value("#{stepExecutionContext['tenantId']}")` được resolve khi target được tạo trong step scope, không phải khi ứng dụng khởi động.
- **Một `StepExecution` có thể dùng nhiều thread chunk.** Các thread đó vẫn thuộc **cùng step execution**, vì vậy có thể chia sẻ cùng target step-scoped; thread safety phải xét riêng.
- **`@JobScope` không thay `@StepScope`.** Job-scoped bean sống theo `JobExecution`, không tạo instance riêng cho từng partition và còn có hạn chế trong môi trường multi-threaded/partitioned step.
- **`StepExecutionId` khác với partition key.** Khi một partition được restart, execution ID mới có thể xuất hiện dù tên và phạm vi partition không đổi.

| Mức kiểm thử | Mục đích | Công cụ thích hợp |
| --- | --- | --- |
| Unit test Java thuần | Kiểm tra hàm biến đổi, kiểm tra predicate và key | JUnit 5; không cần Spring context |
| Scope-focused Spring test | Kiểm tra late binding, instance/state theo execution | `StepScopeTestUtils`, `StepExecution` giả lập |
| Partition integration test | Chạy manager + worker và kiểm tra dữ liệu/metadata | `@SpringBatchTest`, `JobLauncherTestUtils` hoặc `JobOperator` |
| Concurrency/stress test | Phát hiện race khi nhiều worker chạy cùng lúc | `TaskExecutor` nhiều slot, latch/barrier, test lặp |
| Restart/failure test | Kiểm tra checkpoint, status và không chạy lại sai | `JobRepository` thực, lỗi có kiểm soát, restart cùng JobInstance |

Nên đi từ test scope nhỏ, dễ chẩn đoán tới bài test tích hợp đầy đủ. Test nhỏ xác định **vòng đời bean**; test tích hợp mới xác định được **tính đúng của job**.

## 3. Thiết lập bộ kiểm thử Spring Batch

Với dự án Gradle dùng Spring Batch 5.x và JUnit 5, cần thư viện hỗ trợ kiểm thử (thường do Spring Boot dependency management quản lý phiên bản tương thích):

~~~groovy
dependencies {
    implementation 'org.springframework.batch:spring-batch-core'

    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là ví dụ dependency cho dự án **Spring Boot + Gradle**, không bắt buộc mọi ứng dụng Batch phải dùng Boot. Với Maven hoặc ứng dụng Spring thuần, sử dụng dependency tương đương và cấu hình context/JUnit phù hợp. Bộ test thật có thể cần H2/Testcontainers và driver database để chạy `JobRepository` và reader/writer.

Các tiện ích đáng biết:

- `StepScopeTestUtils.doInStepScope(stepExecution, callable)`: kích hoạt một `StepExecution` trong thời gian gọi callback, sau đó dọn liên kết scope.
- `StepScopeTestExecutionListener`: hỗ trợ cung cấp một `StepExecution` cho test method qua Spring Test lifecycle.
- `@SpringBatchTest`: cung cấp các tiện ích/liên kết test của Batch, trong đó thường dùng `JobLauncherTestUtils` và scope test listeners.
- `JobLauncherTestUtils.launchJob(...)` hoặc `launchStep(...)`: chạy job/step được cấu hình trong application context; phải đảm bảo đúng bean job/step được chọn.
- `JobExplorer`: đọc metadata đã lưu mà không cần sửa trực tiếp bảng Batch.

**Đối với test chỉ tập trung vào scoped bean**, có thể dựng Spring Test context nhỏ và đăng ký `StepScope`, không bắt buộc khởi động một job thật. Đối với test restart, cần repository và transaction phù hợp vì mock in-memory đơn giản thường không mô phỏng chính xác lịch sử `JobInstance`.

## 4. Test A: hai StepExecution nhận hai target khác nhau

Đây là bài test cốt lõi. Ta tạo hai `StepExecution` có ID khác nhau, truyền `tenantId` tương ứng, rồi gọi **cùng một scoped proxy** trong hai scope.

### 4.1. Bean kiểm thử có state theo step

~~~java
import java.util.UUID;

public class PartitionProbe {
    private final String tenantId;
    private final String targetId = UUID.randomUUID().toString();
    private int calls;

    public PartitionProbe(String tenantId) {
        this.tenantId = tenantId;
    }

    public String tenantId() {
        return tenantId;
    }

    public String targetId() {
        return targetId;
    }

    public int increment() {
        return ++calls;
    }
}
~~~

`targetId` chỉ dùng làm dấu hiệu nhận diện instance trong **test**; không dùng UUID này làm tên partition hoặc idempotency key của job production. Field `calls` cố ý mutable để kiểm tra **không bị chia sẻ giữa hai worker**.

### 4.2. JUnit 5 với StepScopeTestUtils

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.scope.StepScope;
import org.springframework.batch.test.StepScopeTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PartitionScopeTest.Config.class)
class PartitionScopeTest {

    @Autowired
    private PartitionProbe probe; // Scoped proxy, không phải target cố định.

    @Test
    void targetVaStateDuocCachLyTheoWorker() throws Exception {
        JobExecution jobExecution = new JobExecution(42L);

        StepExecution a = new StepExecution(
                "ordersWorkerStep:tenant-A", jobExecution, 101L);
        a.getExecutionContext().putString("tenantId", "A");

        StepExecution b = new StepExecution(
                "ordersWorkerStep:tenant-B", jobExecution, 102L);
        b.getExecutionContext().putString("tenantId", "B");

        String targetA = StepScopeTestUtils.doInStepScope(a, () -> {
            assertEquals("A", probe.tenantId());
            assertEquals(1, probe.increment());
            assertEquals(2, probe.increment());
            return probe.targetId();
        });

        String targetB = StepScopeTestUtils.doInStepScope(b, () -> {
            assertEquals("B", probe.tenantId());
            assertEquals(1, probe.increment()); // State mới, không phải 3.
            return probe.targetId();
        });

        assertNotEquals(targetA, targetB);
    }

    @Configuration
    static class Config {

        // Đăng ký scope cho Spring Test context tối giản.
        @Bean
        static StepScope stepScope() {
            return new StepScope();
        }

        @Bean
        @StepScope
        PartitionProbe partitionProbe(
                @Value("#{stepExecutionContext['tenantId']}")
                String tenantId) {
            return new PartitionProbe(tenantId);
        }
    }
}
~~~

**Cách hiểu assertion:**

1. Hai callback cùng gọi `probe` là **proxy được inject một lần**.
2. Khi `StepExecution A` active, target có `tenantId=A` và tăng bộ đếm từ 0 tới 2.
3. Khi `StepExecution B` active, target khác có `tenantId=B` và bộ đếm bắt đầu từ 0.
4. Hai `targetId` khác nhau chứng minh target không phải singleton trong ngữ cảnh bài test.

`StepScopeTestUtils` bảo đảm kích hoạt/dọn step context xung quanh callback. Không gọi method trên scoped proxy **ngoài một step scope active** rồi coi lỗi “Scope 'step' is not active” là lỗi của partitioning; đây là hành vi cần mong đợi nếu target không có execution context.

**Giới hạn của test:** Hai scope được kích hoạt **tuần tự**. Test xác minh binding và lifetime, nhưng chưa ép thực thi đồng thời nên **chưa chứng minh không có race** ở các singleton/helper khác.

## 5. Test B: dùng StepScopeTestExecutionListener

Nếu một test method chỉ cần **một** worker context, có thể dùng `StepScopeTestExecutionListener`, được hỗ trợ qua `@SpringBatchTest` hoặc đăng ký bằng Spring Test. Test class có thể cung cấp method `getStepExecution()` để listener lấy context:

~~~java
// Khung minh họa: dùng cùng một Spring Test context có @StepScope bean.
public StepExecution getStepExecution() {
    JobExecution job = new JobExecution(99L);
    StepExecution worker = new StepExecution(
            "ordersWorkerStep:tenant-A", job, 199L);
    worker.getExecutionContext().putString("tenantId", "A");
    return worker;
}

@Test
void readerNhanDungThamSoBangLateBinding() {
    assertEquals("A", probe.tenantId());
}
~~~

Đoạn trên **không phải một test class độc lập**: nó cần nằm trong lớp được cấu hình với listener và `probe` tương ứng. Khi muốn so sánh hai `StepExecution` khác nhau ngay trong một test, cách rõ ràng hơn là sử dụng `StepScopeTestUtils.doInStepScope(...)` chủ động như phần 4. Không dựa vào tên thread để giả lập step context.

## 6. Test C: integration test với manager và worker thật

Scope-focused test có thể đạt trong khi manager partitioning vẫn **đọc trùng dữ liệu**. Ví dụ reader được tạo riêng cho từng worker nhưng SQL không sử dụng `minId`/`maxId`: cả hai reader sẽ chạy `SELECT * FROM orders`.

Đối với integration test cần cấu hình gần giống production:

~~~mermaid
flowchart TB
    T["JUnit / JobLauncherTestUtils"] --> J["Job"]
    J --> M["Partition manager"]
    M --> S["Partitioner: tenant-A, tenant-B"]
    S --> H["TaskExecutorPartitionHandler<br/>ít nhất 2 worker slots"]
    H --> A["StepExecution A<br/>@StepScope reader A"]
    H --> B["StepExecution B<br/>@StepScope reader B"]
    A --> DB[("Test database")]
    B --> DB
    DB --> V["Assertions: phạm vi, output,<br/>partition status, duplicates"]
~~~

Một khung integration test điển hình:

~~~java
@SpringBatchTest
@SpringJUnitConfig(classes = PartitionedOrdersJobConfig.class)
class PartitionedOrdersJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Test
    void workersKhongDocLanDuLieuCuaNhau() throws Exception {
        // Chuẩn bị dữ liệu test A/B đã biết business key và số hàng.
        // PartitionedOrdersJobConfig phải định nghĩa Job, reader/writer,
        // JobRepository và transaction manager cho test.
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", "partition-isolation-001")
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        // Assertion quan trọng nhất nằm ở dữ liệu ĐÍCH:
        // - toàn bộ event A được ghi với tenant A, event B với tenant B;
        // - mỗi business key chỉ xuất hiện đúng theo nghiệp vụ;
        // - tổng tập ID nguồn và đích khớp, không thiếu/không overlap.
        // Đọc JobExplorer/StepExecution để bổ sung thông tin lỗi/tiến độ.
    }
}
~~~

Đây là **khung tích hợp cần hoàn thiện bằng fixture SQL và bean cấu hình thật**, không phải file Java có thể chạy độc lập. Với Spring Batch 5.x, kiểm tra cấu hình `JobLauncherTestUtils` chọn đúng `Job` khi application context có nhiều job. Không dùng cùng identifying `JobParameters` cho các bài test độc lập mà không dọn database, vì Batch có thể từ chối chạy lại một `JobInstance` đã hoàn tất.

### Nên assert điều gì?

| Phạm vi assertion | Ví dụ |
| --- | --- |
| Worker identity | Mỗi `StepExecution` mang tên partition và context chính xác |
| Không overlap | `input(A) ∩ input(B) = ∅` theo business key |
| Bao phủ | `input(A) ∪ input(B)` bằng tập input dự kiến |
| Không cross-talk | Output của A không có tenant/file/routing key B |
| Counters | `readCount`, `writeCount`, filter/skip phù hợp mô hình nghiệp vụ |
| Kết quả đích | Unique business key, checksum/tổng tiền, số hàng insert/update/no-op đúng |
| Trạng thái | Manager và các worker đạt `COMPLETED` trong bài test thành công |

Đếm tổng `writeCount` **không chứng minh** tất cả bản ghi đã được insert mới: writer có thể dùng `ON CONFLICT DO NOTHING` hoặc thực hiện nhiều tác dụng phụ cho một item. Assertion về kết quả nghiệp vụ quan trọng hơn assertion về metric.

## 7. Test D: ép chạy đồng thời để lộ cross-talk

Chạy integration test với executor một thread có thể che giấu race. Khi cần phát hiện state bleed, hãy cấu hình **ít nhất hai worker slot** và buộc các worker tới một điểm đồng bộ trước khi xử lý.

Ví dụ helper được **dùng trong test**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class WorkerOverlapGate {
    private final CountDownLatch arrived = new CountDownLatch(2);

    public void awaitBoth() throws InterruptedException {
        arrived.countDown();
        if (!arrived.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Không đủ hai worker tới điểm đồng bộ");
        }
    }
}
~~~

Có thể gọi `gate.awaitBoth()` tại một điểm kiểm thử được chọn của **mỗi worker đầu tiên**, sau khi context partition đã bind, trước khi thực hiện phần xử lý cần kiểm tra. Gate cần là **test-only shared helper**, và cần thiết kế để chỉ chắn đúng một lần/worker: nếu gọi cho *mọi item* hoặc dùng hai partition nhưng executor có một slot, test sẽ treo hoặc timeout mà không chứng minh scope sai.

**Không đặt latch/barrier vào production processor** để chữa race. Tác dụng của gate là ép interleaving trong test và làm lỗi tái hiện có kiểm soát. Dùng timeout hữu hạn, đóng pool/dọn kết nối sau test và báo rõ worker ID khi timeout.

Một chiến thuật khác là lặp bài test dưới nhiều mức concurrency (1, 2, 4, 8 slots), dữ liệu có ID xen kẽ và chunk size nhỏ. Khi test lặp lại nhiều lần, không dùng trạng thái `JobInstance`/database còn sót từ lượt trước làm đầu vào cho lượt mới nếu không chủ ý kiểm thử restart.

### Test âm tính: chứng minh vì sao singleton mutable không an toàn

Giả sử singleton processor có field `currentTenant` và các worker gọi `beforeStep` để gán A/B:

~~~java
class UnsafeProcessor {
    private volatile String currentTenant;

    void begin(String tenant) {
        currentTenant = tenant;
    }

    String process() {
        return currentTenant;
    }
}
~~~

Ngay cả `volatile` cũng **không tạo một instance riêng** cho từng execution. Nếu worker A gọi `begin("A")`, worker B gọi `begin("B")` rồi A gọi `process()`, A có thể nhận `B`. Sau khi chuyển processor thành stateless hoặc step-scoped, bài test đồng thời phải chứng minh lỗi đã được loại bỏ. Đừng coi `synchronized` trên từng method là cách xử lý chắc chắn: giá trị vẫn có thể bị worker khác thay đổi giữa hai lời gọi.

## 8. Test E: restart và checkpoint theo đúng partition

Trong bài toán scaling, **state isolation phải tiếp tục đúng qua restart**. Một target `@StepScope` mới không được nhận state của partition khác hoặc một dải dữ liệu đã đổi ý nghĩa.

### Kịch bản cần kiểm tra

Giả sử job có bốn partition:

| Partition | Lần chạy #1 | Lần restart #2 thường mong đợi |
| --- | --- | --- |
| `range-0000` | `COMPLETED` | Không thực thi lại khi giữ chính sách mặc định |
| `range-0001` | `FAILED` sau một số chunk đã commit | Chạy lại/tiếp tục từ checkpoint phù hợp |
| `range-0002` | `COMPLETED` | Không thực thi lại |
| `range-0003` | `STOPPED` | Có thể tiếp tục theo chính sách restart |

**Cách thiết lập bài test:**

1. Tạo dữ liệu test cố định và một kế hoạch partition key → range/file không thay đổi.
2. Cho processor/writer test **thất bại có chủ đích đúng một lần** tại partition `range-0001` sau một số chunk đã commit; bảo đảm lỗi ở bước đầu khiến job kết thúc không thành công.
3. Kiểm tra `JobRepository` ghi các `StepExecution` đã `COMPLETED` và execution `FAILED` cùng `ExecutionContext` của nó.
4. Khắc phục lỗi test, restart **chính JobInstance cũ** bằng cơ chế `JobOperator.restart(failedExecutionId)` hoặc công cụ tương đương.
5. Kiểm tra những partition `COMPLETED` không xuất hiện như worker execution mới trái chính sách, partition chưa hoàn tất tiếp tục với context/identity đúng.
6. Đối soát dữ liệu đích: không thiếu business key, không nhân đôi side effect và số hàng thực tế phù hợp.

~~~mermaid
sequenceDiagram
    participant J as JobExecution #1
    participant R as JobRepository
    participant O as JobOperator
    participant N as JobExecution #2
    J->>R: Worker A COMPLETED; B FAILED; C COMPLETED
    O->>R: restart(failedExecutionId)
    R-->>N: Cùng JobInstance, JobExecution mới
    N->>R: Splitter tra lịch sử worker/context
    Note over N: Chọn B (và phần chưa hoàn tất phù hợp)
    N->>R: Lưu execution/checkpoint/status mới
~~~

**Tình huống phân biệt:** Nếu thay đổi identifying `JobParameters`, bạn thường tạo **JobInstance mới**, không còn cùng tập worker history. Nếu thay `gridSize` khiến một partition key cũ đại diện range khác, checkpoint cũ có thể không còn hợp lệ. Test restart phải cố định cả identifying parameters và kế hoạch phân vùng.

### Checkpoint đúng không đồng nghĩa exactly-once effect

Với reader lưu `ItemStream` state và writer ghi chung transaction phù hợp, lỗi trong chunk có thể rollback phần chưa commit rồi tiếp tục từ checkpoint trước đó. Nhưng nếu writer gửi HTTP/message/email hoặc dùng transaction manager khác, đã có thể xuất hiện side effect ở đích mà metadata chưa ghi nhận.

Vì thế test restart nên bao gồm **duplicate/no-op và idempotency key**, không chỉ so sánh `readCount`/`writeCount`. Khi dữ liệu nguồn thay đổi trong thời gian job chạy, cần kiểm tra snapshot, watermark hoặc manifest để tránh input lệch giữa hai lần thực thi.

## 9. Local, remote và các giới hạn của scope test

### Local partitioning

`TaskExecutorPartitionHandler` chạy worker bằng thread trong cùng JVM. Đây là môi trường dễ tái hiện nhất cho cross-talk do **singleton/static mutable field** được các worker trực tiếp chia sẻ. Một scope test tuần tự chứng minh bean per-step; concurrency test mới chứng minh không có singleton helper bị race.

### Remote partitioning

Với `MessageChannelPartitionHandler`, worker có thể nằm ở nhiều JVM. Các bean singleton ở **hai JVM khác nhau** không trực tiếp chia sẻ heap, nhưng mỗi worker JVM có thể xử lý **nhiều partition**, vẫn cần `@StepScope`. Ngoài ra, shared DB/cache/object storage/API vẫn có thể bị hai worker tranh chấp.

| Phạm vi | Điều test step scope chứng minh | Điều phải kiểm thử thêm |
| --- | --- | --- |
| Trong một Spring context | Target per-StepExecution và late binding | Mutable singleton/static helper, thread reuse |
| Một worker nhiều chunk thread | Vẫn target theo StepExecution | Reader/thread safety, race checkpoint |
| Nhiều JVM | Scope được kích hoạt đúng trên từng JVM | Shared resource và idempotency xuyên JVM |
| Mất message reply | Không liên quan trực tiếp tới scope | Broker retry/ack, worker claim, metadata reconciliation |
| Restart với execution mới | Context được bind vào target mới | Plan identity, checkpoint, dedupe tại hệ thống đích |

### Đừng dùng JobScope để cách ly các worker

`@JobScope` tạo target theo `JobExecution`; nhiều worker trong cùng job không có target riêng. Hơn nữa, Spring Batch lưu ý việc dùng job-scoped bean trong multi-threaded/partitioned step cần đặc biệt thận trọng vì việc liên kết context với thread phụ có thể không được bảo đảm như mong đợi. Đối với tham số per-partition, ưu tiên `@StepScope` và `stepExecutionContext`.

## 10. Debug khi test thất bại

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Scope 'step' is not active` | Gọi proxy ngoài step execution, hoặc context không được liên kết tới thread | Dùng `StepScopeTestUtils`/listener đúng, không tự gọi reader khi context chưa active |
| `@Value` cho `tenantId` ra `null` | Sai tên key trong context hoặc khai báo sai scope | Kiểm tra `stepExecutionContext['tenantId']` và context từng worker |
| Hai worker cùng nhận tenant B | Singleton/static mutable state hoặc helper được chia sẻ | Chuyển sang state theo step, truyền tham số bất biến |
| Bị timeout tại latch | Chỉ một worker có slot hoặc không đủ hai partition tới gate | Tăng executor slot ở test; dùng timeout và đặt gate đúng vị trí |
| Reader test chạy đúng nhưng job thực ghi trùng | SQL range overlap, writer dedupe chưa có | Test partitioner và đối soát business key nguồn/đích |
| Restart bắt đầu sai vị trí | Reader không save state, key checkpoint đổi, input plan thay đổi | Kiểm tra `ItemStream` và context trong repository |
| Một worker dùng nhiều chunk thread bị lỗi | `@StepScope` không phải thread scope | Kiểm tra reader thread safety hoặc thay cách chia concurrency |
| Test pass độc lập nhưng fail khi chạy cả suite | JobInstance/test data/DB state dùng chung | Cô lập fixture, dọn database và tham số run giữa các test không-restart |
| Remote test thấy hai request cho cùng partition | Delivery retry hoặc worker cũ chưa dừng | Kiểm tra broker ack, metadata/claim, idempotency |

Khi log trong test, nên ghi `JobExecutionId`, `StepExecutionId`, partition key, tenant ID đã được phép sử dụng và scope target ID của **test probe**. Không dùng một mình tên thread để định danh worker vì executor có thể tái sử dụng thread giữa các partition.

### Đọc metadata sau integration test

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Truy vấn theo schema metadata mặc định, có thể thay prefix theo cấu hình. Nó bao gồm manager và worker executions. Trong lần restart mới, chỉ nhìn `JobExecutionId` hiện tại không phản ánh toàn bộ lịch sử của `JobInstance`; cần xem thêm các JobExecution trước đó nếu muốn xác định partition nào đã hoàn tất trước lỗi.

## 11. Checklist kiểm thử tối thiểu trước production

| Bài test | Tiêu chí PASS |
| --- | --- |
| Hai worker context khác nhau | `@StepScope` target khác nhau, `tenantId` đúng và state không truyền chéo |
| Late binding `@Value` | Mỗi worker nhận đúng partition key/range theo `stepExecutionContext` |
| Reader `ItemStream` | Lifecycle `open/update/close` và checkpoint hoạt động qua proxy đúng kiểu |
| Mutable singleton helper | Test đồng thời phát hiện cross-talk; refactor loại bỏ shared state |
| Pool tái sử dụng thread | Tenant/MDC/ThreadLocal từ worker cũ không rò vào worker mới |
| Input không chồng lấn | Mỗi business key thuộc đúng partition theo predicate/manifest |
| Tăng 1 → 2 → 4 worker | Không xuất hiện output sai tenant/duplicate; throughput được đo, không đoán |
| One worker fails, others complete | Metadata/status đúng, các chunk đã commit được đối soát |
| Restart cùng JobInstance | Key → phạm vi giữ nguyên; chỉ phần việc cần thiết được thực thi |
| Writer có side effect ngoài transaction | Replay/timeout không tạo tác dụng phụ trùng không kiểm soát |
| Remote workers | Context đúng ở từng JVM; shared cache/file/API có namespace và cơ chế đồng bộ |

### Câu hỏi tự kiểm tra

Một job có bốn partition, sử dụng reader `@StepScope` và processor singleton chứa `private String currentTenant`. Test với `StepScopeTestUtils` xác nhận reader của A/B khác target và nhận đúng range. Tuy nhiên khi chạy bốn worker đồng thời, output của A đôi khi mang tenant B.

1. Vì sao scope-focused reader test đã pass mà job vẫn sai?
2. Nếu sửa processor thành `@StepScope`, có đủ kết luận toàn bộ job thread-safe không?
3. Nếu worker B lỗi sau 10 chunk commit rồi restart, cần thêm những assertion gì?
4. Nếu remote worker gửi thành công một request nhưng phản hồi bị mất, scope có giải quyết duplicate side effect không?

**Định hướng trả lời:** Reader được cách ly nhưng processor singleton vẫn có mutable state dùng chung. Cần kiểm tra mọi thành phần stateful, helper, shared output và concurrency **bên trong mỗi worker**. Test restart phải xác nhận partition identity, checkpoint, kết quả theo business key và writer idempotent. Scope không thay thế transaction, dedupe hay cơ chế xác nhận của hệ thống ngoài JVM.

## Tài liệu tham khảo

- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `spring-batch-test`, `@SpringBatchTest` và các tiện ích test step scope.
- [Spring Batch API — StepScopeTestUtils](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/StepScopeTestUtils.html): chạy code dưới một `StepExecution` được chỉ định.
- [Spring Batch Reference — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope`, `@Value` và context.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và mô hình remote.
- [Spring Batch API — StepExecution](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/StepExecution.html): state, status và counters của worker.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `ItemStream`, checkpoint và restart.

> **Ghi nhớ:** Test `@StepScope` phải chứng minh **state/target riêng theo StepExecution**, rồi tiếp tục kiểm chứng **input/output đúng trong khi chạy song song** và **checkpoint/idempotency đúng khi restart**. Một unit test scope thành công không tự chứng minh job phân tán an toàn.
