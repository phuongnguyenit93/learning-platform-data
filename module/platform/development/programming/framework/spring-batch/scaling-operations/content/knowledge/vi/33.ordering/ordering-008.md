# Parallel steps không có thứ tự mặc định trong Spring Batch

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao **parallel steps không đảm bảo thứ tự bắt đầu hoặc hoàn thành** chỉ dựa trên thứ tự khai báo trong cấu hình Spring Batch.
- Phân biệt **thứ tự flow**, **thứ tự step trong từng flow**, **thứ tự hoàn thành theo thời gian thực** và **thứ tự dữ liệu bên trong một step**.
- Sử dụng `Flow`, `FlowBuilder`, `split(TaskExecutor)`, `JobBuilder` và `next(...)` trong **Spring Batch 5.x / Java 17** để biểu diễn phụ thuộc thật sự.
- Thiết kế sơ đồ phụ thuộc (DAG) và **barrier/join**: các nhánh độc lập có thể chạy song song, còn bước tổng hợp phải chờ đủ tiền điều kiện.
- Nhận diện race condition khi parallel steps cùng ghi bảng, file, `JobExecutionContext`, tài nguyên dùng chung hoặc xử lý một input không bất biến.
- Hiểu vai trò của `JobRepository`, `StepExecution`, `ExitStatus`, transition, restart và idempotency khi một trong các nhánh thành công/chậm/lỗi.
- Kiểm thử đồng thời bằng `CountDownLatch` và các sự kiện được xác nhận, tránh test dựa vào `Thread.sleep` hoặc giả định tốc độ máy.
- Đo throughput, tail latency, số worker thực chạy, tài nguyên DB/CPU/I/O và đối soát business output trước khi quyết định parallel hóa.

## 1. Một hiểu lầm rất phổ biến về parallel steps

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, ta muốn rút thời gian job ETL bằng cách cho ba bước độc lập chạy cùng lúc:

- `loadCustomersStep`: nạp dữ liệu khách hàng vào staging.
- `loadOrdersStep`: nạp dữ liệu đơn hàng vào staging.
- `loadProductsStep`: nạp dữ liệu sản phẩm vào staging.

Một người thấy cấu hình Spring Batch khai báo `customersFlow` trước `ordersFlow` nên tin rằng `loadCustomersStep` **luôn bắt đầu trước**, và sẽ hoàn thành trước khi `loadOrdersStep` chạy.

Niềm tin đó **không có cơ sở** khi các flow được chạy trong một `split` với `TaskExecutor` thực sự bất đồng bộ. Scheduling phụ thuộc thread pool, hệ điều hành, GC, database, network, checkpoint và tranh chấp tài nguyên. Bước khai báo trước có thể bắt đầu sau hoặc hoàn thành sau bước khai báo sau.

~~~mermaid
sequenceDiagram
    participant J as Job / Split
    participant C as Customers Flow
    participant O as Orders Flow
    participant P as Products Flow
    J->>C: Submit
    J->>O: Submit
    J->>P: Submit
    Note over C,P: Thứ tự được scheduler quyết định
    O-->>J: Hoàn thành trước
    P-->>J: Hoàn thành thứ hai
    C-->>J: Hoàn thành cuối cùng
~~~

**Hai ý tưởng phải tách biệt:**

1. **Thứ tự được yêu cầu bởi nghiệp vụ**: ví dụ `initializeSnapshotStep` phải commit thành công trước khi bất kỳ reader nào truy cập snapshot.
2. **Thứ tự quan sát được trong một lần chạy**: ví dụ `loadOrdersStep` tình cờ finish sớm nhất vì input nhỏ hơn.

Không biến một kết quả quan sát được thành bảo đảm kiến trúc.

## 2. Bốn loại thứ tự dễ bị nhầm lẫn

| Loại thứ tự | Ví dụ | Bảo đảm đúng là gì? |
| --- | --- | --- |
| **Thứ tự giữa các step của cùng flow tuần tự** | `A.next(B)` | B phụ thuộc transition từ A theo flow đã khai báo |
| **Thứ tự giữa hai flow trong split** | `split(executor).add(flowA,flowB)` | Hai flow được lên lịch để có thể chạy đồng thời; **không bảo đảm A trước B** |
| **Thứ tự chunk/item trong một step** | Reader `ORDER BY id`, writer commit theo chunk | Cần thiết kế riêng; split không bảo đảm thứ tự record |
| **Thứ tự hoàn tất và publish kết quả** | `aggregateStep` sau hai nhánh | Phải có barrier và điều kiện thành công rõ, không suy từ log |

Một flow có `start(stepA).next(stepB)` tạo ra **quan hệ phụ thuộc** trong chính flow đó. Khi khai báo hai flow trong split, chúng là các nhánh riêng biệt: framework có thể đưa cả hai tới executor, mỗi nhánh tự chạy theo cấu hình transition của nó.

### Thứ tự khai báo khác thứ tự thực thi

~~~text
Khai báo:
  split(Flow A, Flow B, Flow C)

Lần chạy 1:
  start B -> start A -> start C
  finish C -> finish B -> finish A

Lần chạy 2:
  start A -> start C -> start B
  finish B -> finish A -> finish C
~~~

Đây là các kịch bản **có thể xảy ra**, không phải lịch chạy bắt buộc của Spring Batch. Nếu executor chỉ có một worker thread, toàn bộ các flow có thể bị xếp hàng và chạy gần tuần tự; nhưng đó vẫn **không phải hợp đồng thứ tự nghiệp vụ** đáng dựa vào.

### Một nhầm lẫn khác: parallel steps không phải multi-threaded step

- **Parallel steps**: nhiều `Step` thuộc các `Flow` khác nhau có thể chạy cùng lúc. Mỗi step có `StepExecution` và context riêng.
- **Multi-threaded step**: một step chunk-oriented dùng executor chạy các chunk trong cùng một `StepExecution`, dẫn tới các yêu cầu thread safety riêng.
- **Partitioning**: một worker step được tạo nhiều `StepExecution` cho các miền input khác nhau.
- **Remote chunking**: manager thường đọc và gửi chunk tới worker, không tự tạo quan hệ thứ tự giữa các step nghiệp vụ.

Các mô hình đều giúp mở rộng throughput nhưng có **ngữ nghĩa ordering, state và restart khác nhau**.

## 3. Điều gì được đảm bảo trong một flow tuần tự?

Giả sử ứng dụng cần:

~~~text
validateSourceStep -> captureSnapshotStep -> publishManifestStep
~~~

Một flow tuần tự mô tả quan hệ nhân quả: bước sau chỉ được cân nhắc khi transition của bước trước cho phép.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.flow.Flow;
import org.springframework.batch.core.job.flow.support.SimpleFlow;
import org.springframework.batch.core.job.builder.FlowBuilder;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SequentialPreparationFlowConfig {

    @Bean
    Flow preparationFlow(
            Step validateSourceStep,
            Step captureSnapshotStep,
            Step publishManifestStep) {

        return new FlowBuilder<SimpleFlow>("preparationFlow")
                .start(validateSourceStep)
                .next(captureSnapshotStep)
                .next(publishManifestStep)
                .build();
    }
}
~~~

Với transition mặc định của ví dụ, `captureSnapshotStep` không được bắt đầu trước khi `validateSourceStep` hoàn tất theo đường chuyển hợp lệ. Nếu step đầu thất bại và flow không có transition xử lý lỗi để vẫn tiếp tục, đường chạy sẽ không đến step sau.

**Cần đọc cấu hình transitions**, không chỉ nhìn tên API. Một flow có `on("FAILED").to(recoveryStep)` hoặc các nhánh custom có thể chủ động xử lý lỗi theo nghiệp vụ. Không nên nói “mọi `FAILED` đều tuyệt đối ngăn mọi step kế tiếp” nếu có transitions đặc biệt.

### Thời gian không tạo ra phụ thuộc

Không dùng:

~~~java
// Anti-pattern minh họa, không phải quy tắc điều phối:
Thread.sleep(5000);
consumeSharedData();
~~~

Bước sau ngủ năm giây không bảo đảm bước trước đã commit. Dưới tải cao, DB lock, GC hay failover, bước trước có thể mất 30 giây. Phụ thuộc phải được biểu diễn bằng **flow edge** hoặc một giao thức readiness có chứng nhận bền vững, không bằng độ trễ đoán trước.

## 4. Split flows: có thể đồng thời, không hứa thứ tự

Trong Spring Batch 5.x, `FlowBuilder` có thể tạo một **split flow** gồm nhiều flow con được đưa tới `TaskExecutor`.

Ví dụ dùng Java 17:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.flow.Flow;
import org.springframework.batch.core.job.flow.support.SimpleFlow;
import org.springframework.batch.core.job.builder.FlowBuilder;
import org.springframework.core.task.TaskExecutor;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;

@Configuration
class ParallelLoadFlowsConfiguration {

    @Bean("customersFlow")
    Flow customersFlow(
            @Qualifier("loadCustomersStep") Step loadCustomersStep) {
        return new FlowBuilder<SimpleFlow>("customersFlow")
                .start(loadCustomersStep)
                .build();
    }

    @Bean("ordersFlow")
    Flow ordersFlow(
            @Qualifier("loadOrdersStep") Step loadOrdersStep) {
        return new FlowBuilder<SimpleFlow>("ordersFlow")
                .start(loadOrdersStep)
                .build();
    }

    @Bean("productsFlow")
    Flow productsFlow(
            @Qualifier("loadProductsStep") Step loadProductsStep) {
        return new FlowBuilder<SimpleFlow>("productsFlow")
                .start(loadProductsStep)
                .build();
    }

    @Bean("parallelLoads")
    Flow parallelLoads(
            @Qualifier("customersFlow") Flow customers,
            @Qualifier("ordersFlow") Flow orders,
            @Qualifier("productsFlow") Flow products,
            @Qualifier("batchParallelExecutor") TaskExecutor executor) {

        return new FlowBuilder<SimpleFlow>("parallelLoads")
                .split(executor)
                .add(customers, orders, products)
                .build();
    }
}
~~~

`.add(customers, orders, products)` **không** có nghĩa customers phải xong trước orders. Nếu executor cho phép ba công việc chạy đồng thời, cả ba flow có thể overlap; thời điểm thực tế phụ thuộc scheduler và tài nguyên.

### Chọn executor có giới hạn thay vì tạo thread vô hạn

~~~java
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class ParallelExecutorConfiguration {

    @Bean("batchParallelExecutor")
    ThreadPoolTaskExecutor batchParallelExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(3);
        executor.setQueueCapacity(3);
        executor.setThreadNamePrefix("batch-flow-");
        executor.initialize();
        return executor;
    }
}
~~~

Đây là cấu hình minh họa ba slots cho ba flow độc lập. `ThreadPoolTaskExecutor` có queue hữu hạn để tránh phát sinh số lượng thread không kiểm soát. Trong production phải đối chiếu chính sách reject, lifecycle shutdown, số kết nối JDBC và khả năng một flow phải chờ task khác — **không mặc định pool lớn hơn luôn tốt hơn**.

**Lưu ý:** `SimpleAsyncTaskExecutor` cũng có thể dùng để demo, nhưng không nên nhầm nó với một thread pool tái sử dụng/bounded thực thụ. Hãy kiểm soát concurrency theo DB, CPU, broker và resource quota toàn hệ thống.

## 5. Join/barrier: chờ các nhánh xong trước khi tổng hợp

Nếu yêu cầu nghiệp vụ là **cả customers, orders và products đều sẵn sàng trước khi tạo báo cáo**, hãy khai báo một bước tổng hợp **sau split**.

~~~mermaid
flowchart LR
    PRE["prepareSnapshotStep"] --> SPLIT{"Split"}
    SPLIT --> C["loadCustomersStep"]
    SPLIT --> O["loadOrdersStep"]
    SPLIT --> P["loadProductsStep"]
    C --> JOIN["Join / kiểm tra exit status"]
    O --> JOIN
    P --> JOIN
    JOIN --> AG["aggregateReportStep"]
    AG --> PUB["publishReportStep"]
~~~

Một cách biểu diễn trong Job DSL Spring Batch 5.x:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.flow.Flow;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.job.flow.support.SimpleFlow;
import org.springframework.batch.core.job.builder.FlowBuilder;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.beans.factory.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;

@Configuration
class SplitJoinJobConfiguration {

    @Bean("reportWorkflow")
    Flow reportWorkflow(
            @Qualifier("prepareSnapshotStep") Step prepare,
            @Qualifier("parallelLoads") Flow parallelLoads,
            @Qualifier("validateAllInputsStep") Step validate,
            @Qualifier("aggregateReportStep") Step aggregate,
            @Qualifier("publishReportStep") Step publish) {

        return new FlowBuilder<SimpleFlow>("reportWorkflow")
                .start(prepare)
                .next(parallelLoads)
                .next(validate)
                .next(aggregate)
                .next(publish)
                .build();
    }

    @Bean("orderingJob")
    Job orderingJob(
            JobRepository jobRepository,
            @Qualifier("reportWorkflow") Flow workflow) {
        return new JobBuilder("orderingJob", jobRepository)
                .start(workflow)
                .end()
                .build();
    }
}
~~~

**Giải thích đoạn code:** `prepare` là dependency chạy trước. `parallelLoads` là flow gồm một split, chỉ có thể rời split khi các nhánh đạt trạng thái kết thúc theo flow aggregation/transition. `validate`, `aggregate` và `publish` được đặt **sau** split. Khi hệ thống yêu cầu chỉ tổng hợp nếu **mọi nhánh đều thành công**, phải kiểm tra semantics của exit-status aggregation và transitions thực tế, không custom-mapping mọi lỗi thành `COMPLETED`.

**Cần xác thực cú pháp builder theo minor version** và flow transitions của ứng dụng. Đoạn trên dùng explicit `Flow` cho tuần tự `prepare → parallelLoads → validate → aggregate → publish`, rồi đưa flow đó vào `JobBuilder` để dễ kiểm soát transitions. Nó minh họa quan hệ thứ tự chính; chưa bao gồm toàn bộ cấu hình dependency injection, transaction và kiểm thử.

### Barrier không chứng minh dữ liệu đúng

Một split trả về thành công **không có nghĩa** mỗi nhánh đã ghi đủ business keys. Nếu `loadOrdersStep` có skip policy bỏ nhiều record hoặc writer ghi sai phiên bản, trạng thái `COMPLETED` có thể vẫn đạt.

Trước `aggregateReportStep`, nên có validation về:

- Snapshot/version dùng cho cả ba nhánh.
- Số lượng record dự kiến và số output hợp lệ.
- Uniqueness và absence of missing/extra business keys.
- Marker `READY`/manifest của từng nhánh đã được commit.
- Không còn retry/DLQ bắt buộc theo business policy.

Nếu validation là bước riêng, cấu hình thành `validateAllInputsStep` nằm sau split và trước aggregate.

## 6. Khi có phụ thuộc thật, không đặt vào hai nhánh song song

Một lỗi thiết kế thường gặp:

~~~text
Flow A: buildCustomerIndexStep
Flow B: enrichOrdersUsingCustomerIndexStep

Đưa cả hai vào split.
~~~

`enrichOrdersUsingCustomerIndexStep` **phụ thuộc vào** kết quả của `buildCustomerIndexStep`. Không thể cho chúng chạy “cùng lúc rồi hy vọng index kịp tạo”. Tùy scheduling, B có thể query bảng rỗng, đọc index một phần, gặp constraint chưa sẵn sàng hoặc tạo kết quả không nhất quán.

Cách đúng:

~~~mermaid
flowchart TD
    A["buildCustomerIndexStep"] --> B["enrichOrdersUsingCustomerIndexStep"]
    A --> C["buildProductIndexStep"]
    B --> JOIN["Join"]
    C --> JOIN
    JOIN --> P["publishStep"]
~~~

Nếu business yêu cầu bước A hoàn thành trước cả B và C, hãy đưa A **trước split**, rồi chạy B và C song song. Nếu chỉ B phụ thuộc A còn C độc lập, có thể cấu hình flow:

~~~text
Flow 1: A -> B
Flow 2: C

split(Flow 1, Flow 2) -> join -> publish
~~~

Ở cách thứ hai, C có thể chạy trước A, trong khi B chỉ được chạy sau A. Đây là một **partial order (thứ tự bộ phận)**, không phải thứ tự toàn cục.

### Quy tắc quyết định

- Nếu hai bước có quan hệ **producer → consumer** trên dữ liệu mutable, mặc định phải **serialize** hoặc thiết kế giao thức version/readiness rõ ràng.
- Nếu hai bước cùng đọc một **immutable snapshot**, ghi vào hai destination/namespace độc lập và không có shared mutable dependency, chúng là ứng viên chạy song song tốt.
- Nếu hai bước có thể chạy đồng thời về mặt logic nhưng cùng làm nóng DB/index, cần benchmark vì performance bottleneck có thể làm việc chạy song song **chậm hơn tuần tự**.

## 7. Biểu diễn dependency bằng DAG thay vì “thứ tự ghi code”

Một batch workflow thường là đồ thị có hướng không chu trình (DAG):

~~~mermaid
flowchart TD
    CAP["captureSnapshot"] --> VALID["validateSnapshot"]
    VALID --> LA["loadCustomers"]
    VALID --> LB["loadOrders"]
    VALID --> LC["loadProducts"]
    LA --> MERGE["reconcileStaging"]
    LB --> MERGE
    LC --> MERGE
    MERGE --> PUB["publishReport"]
~~~

DAG nêu rõ:

1. `captureSnapshot` phải trước `validateSnapshot`.
2. `validateSnapshot` phải trước mọi load step.
3. `loadCustomers`, `loadOrders` và `loadProducts` không có cạnh phụ thuộc trực tiếp, nên có thể chạy song song.
4. `reconcileStaging` phải chờ đủ các nhánh.
5. `publishReport` chỉ được thực hiện sau reconciliation thành công.

### Partial order và “happens-before”

Trong một flow tuần tự, transition cho ta quan hệ dependency ở mức workflow. Trong split, **không có happens-before theo thứ tự khai báo** giữa hai sibling flows.

Một ứng dụng không nên dựa vào đồng hồ của log:

~~~text
10:00:00.001 ordersFlow STARTED
10:00:00.002 customersFlow STARTED
10:00:00.050 customersFlow COMPLETED
10:00:00.100 ordersFlow COMPLETED
~~~

Log này mô tả **một lần chạy**, không chứng minh rằng ở lần sau customers luôn xong trước orders. Trong môi trường phân tán, clock skew còn có thể làm timestamp log từ hai host không phản ánh đúng thứ tự nhân quả.

Cần dùng **flow transitions**, database transaction/marker có điều kiện hoặc message protocol có correlation/ack rõ ràng để chứng minh dependency, không dùng thời gian log và thứ tự console output.

## 8. Tranh chấp tài nguyên và vấn đề dữ liệu dùng chung

Parallel steps tách `StepExecution`, nhưng **không** tự tách mọi tài nguyên.

| Tài nguyên | Race condition hoặc bottleneck | Biện pháp |
| --- | --- | --- |
| Cùng bảng output | Hai nhánh insert/update cùng business key | Chia namespace/key, unique constraint, idempotent write, lock khi cần |
| Cùng file path | Hai writer truncate/append đồng thời, tạo file hỏng | Mỗi nhánh ghi file tạm/version riêng, merge sau join |
| Cùng `JobExecutionContext` | Hai nhánh ghi cùng key, last-writer-wins hoặc mất update | Không dùng làm shared synchronization, tách key/step context và merge sau join |
| Cùng singleton mutable bean | Counter/list/cache không thread-safe | Immutable data, thread-safe component, scope và ownership rõ |
| Cùng JDBC pool | Pool cạn, wait/timeouts tăng | Bounded concurrency và budget connection toàn cluster |
| Cùng DB row/aggregate | Lock/deadlock và lost update | Transaction isolation, deterministic ownership, reduce sau barrier |
| Cùng broker topic/queue | Redelivery, out-of-order events | Correlation/key ordering, dedup, per-stream sequence khi nghiệp vụ cần |
| Cùng staging schema | Reader thấy dữ liệu chưa hoàn tất | Snapshot/version hoặc READY marker được publish atomically |

### Không dùng JobExecutionContext làm hàng rào đồng bộ

Ví dụ dễ sai:

~~~java
// Anti-pattern: đặt trong hai parallel steps.
jobExecution.getExecutionContext().put("stage.ready", true);

// Step khác đọc ngay:
boolean ready = jobExecution.getExecutionContext()
        .getBoolean("stage.ready");
~~~

`ExecutionContext` là metadata restart, **không phải distributed lock, latch hay một transactional message bus**. Một key được ghi trong heap của một step chưa tự chứng minh bảng output đã commit; hai nhánh cập nhật cùng key có thể tạo lost update hoặc thứ tự publish sai.

Đặt state cục bộ trong `StepExecutionContext` mỗi step; sau barrier đọc kết quả đã commit từ DB/object storage và tổng hợp sang job-level context nếu thật sự cần, theo lifecycle phù hợp. Với remote workers, càng phải dùng durable coordination thay vì shared in-memory reference.

## 9. Ví dụ nghiệp vụ: staging theo version và publish sau khi mọi nhánh thành công

Giả sử các nguồn Customers, Orders và Products cần được nạp vào ba bảng staging, rồi chỉ **công bố** một bản báo cáo hoàn chỉnh.

Một mô hình PostgreSQL:

~~~sql
CREATE TABLE batch_snapshot (
    snapshot_id VARCHAR(100) PRIMARY KEY,
    state VARCHAR(20) NOT NULL
        CHECK (state IN ('BUILDING', 'READY', 'EXPIRED'))
);

CREATE TABLE batch_stage_completion (
    snapshot_id VARCHAR(100) NOT NULL
        REFERENCES batch_snapshot(snapshot_id),
    stage_name VARCHAR(50) NOT NULL,
    expected_count BIGINT NOT NULL CHECK (expected_count >= 0),
    committed_count BIGINT NOT NULL CHECK (committed_count >= 0),
    validated BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (snapshot_id, stage_name)
);

CREATE TABLE batch_report_publication (
    snapshot_id VARCHAR(100) PRIMARY KEY
        REFERENCES batch_snapshot(snapshot_id),
    published_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Mỗi nhánh ghi vào bảng output của riêng mình, mang `snapshot_id` và primary/unique business key. Sau khi dữ liệu đã commit và được đối soát, nhánh cập nhật `batch_stage_completion` cho `stage_name` của nó.

**Không** ghi `validated=true` trước khi toàn bộ output của nhánh đã commit theo thứ tự/transaction contract. Nếu dữ liệu được nạp qua nhiều transaction, việc công bố marker cần diễn ra sau kiểm tra hoàn tất và không bị ghi sớm khi còn chunk in-flight.

### Bước validation sau barrier

~~~sql
SELECT stage_name, expected_count, committed_count, validated
FROM batch_stage_completion
WHERE snapshot_id = :snapshotId
ORDER BY stage_name;
~~~

Một query gate cụ thể cho đúng ba stage:

~~~sql
WITH required(stage_name) AS (
    VALUES ('customers'), ('orders'), ('products')
)
SELECT r.stage_name
FROM required r
LEFT JOIN batch_stage_completion c
  ON c.snapshot_id = :snapshotId
 AND c.stage_name = r.stage_name
WHERE c.stage_name IS NULL
   OR c.validated IS DISTINCT FROM TRUE
   OR c.expected_count IS DISTINCT FROM c.committed_count;
~~~

Kỳ vọng **0 hàng**. Query này dựa vào các marker đã được ghi đúng và số count được tính từ dữ liệu thật, chứ không chỉ tự khai báo. Trong production nên kiểm tra business-key reconciliation/phiên bản và không chỉ so count.

Khi gate PASS, `publishReportStep` có thể tạo/cập nhật bản ghi publication theo `snapshot_id` để chống công bố trùng khi restart. Ví dụ:

~~~sql
INSERT INTO batch_report_publication(snapshot_id)
VALUES (:snapshotId)
ON CONFLICT (snapshot_id) DO NOTHING;
~~~

**Marker publication không tự bảo đảm hiệu ứng bên ngoài exactly-once.** Nếu publish gửi email hoặc message, cần transactional outbox/ledger và correlation key với cơ chế dedup của hệ đích.

### Vì sao mô hình này tốt hơn chờ Sleep?

Dữ liệu được coi sẵn sàng dựa trên **commit và kiểm chứng**, không dựa trên việc worker trước đó “có lẽ đã chạy vài giây”. Sự khác nhau giữa một execution nhanh và một execution chậm không thay đổi correctness.

## 10. Kết quả khi một nhánh chậm hoặc lỗi

Ba tình huống phải phân biệt:

| Tình huống | Điều có thể xảy ra | Bước sau split cần làm gì? |
| --- | --- | --- |
| A xong sớm, B/C còn chạy | Split chưa thể hội tụ thành một kết quả cuối phù hợp | Chờ các nhánh theo lifecycle |
| B thất bại, A/C xong | Aggregated flow status phụ thuộc quy tắc tổng hợp và transitions | Không publish nếu yêu cầu tất cả nhánh thành công |
| A/C xong, B dừng có chủ đích | Một phần staging có thể đã commit | Dùng trạng thái restart/cleanup và gate bền vững |

Không biến “split đã trả về một exit status” thành “mọi bước đã ghi đủ”. Nếu business yêu cầu toàn bộ ba stage phải thành công, **validation sau split** là một lớp bảo vệ quan trọng.

### Fail fast có thể không đồng nghĩa cancel ngay mọi nhánh

Nếu một flow gặp `FAILED`, các flow khác **có thể đang tiếp tục** và commit output cho tới khi cơ chế phối hợp/cancel phù hợp có hiệu lực. Không mặc định một lỗi lập tức rollback các giao dịch độc lập đã commit ở sibling flow.

Ví dụ `loadCustomersStep` fail sau 10 chunk, trong khi `loadOrdersStep` đã hoàn tất 80%. Có thể cần giữ staging theo `snapshot_id` để restart/cleanup an toàn. Nếu nghiệp vụ cần all-or-nothing, phải thiết kế snapshot/version publication, compensation hoặc transaction boundaries có phạm vi phù hợp; **không có một transaction duy nhất bao trùm toàn bộ parallel flows** chỉ vì chúng nằm trong một Job.

### ExitStatus và BatchStatus

`BatchStatus` biểu thị trạng thái lifecycle của `StepExecution`/`JobExecution`, còn `ExitStatus` có thể được tùy biến để điều khiển transitions. Sử dụng wildcard/catch-all transitions sai cách có thể khiến flow đi tiếp trên một trạng thái lỗi.

Thay vì “thấy `COMPLETED` trong một step thì publish”, cần định nghĩa **các trạng thái được chấp nhận cho từng nhánh** và kiểm chứng dữ liệu đầu ra sau khi join.

## 11. Tính đúng của ordering trong một step vẫn là vấn đề độc lập

Ngay cả nếu các step được đặt tuần tự, thứ tự item bên trong một step không tự được đảm bảo khi có concurrency.

Ví dụ reader lấy giao dịch từ database:

~~~sql
SELECT transaction_id, account_id, event_at, amount
FROM transaction_snapshot
WHERE snapshot_id = :snapshotId;
~~~

Không có `ORDER BY` thì không được suy luận thứ tự trả về luôn theo primary key. Dù có:

~~~sql
ORDER BY event_at, transaction_id
~~~

khi dùng multi-threaded chunk processing, thứ tự chunk được xử lý/commit có thể khác thứ tự reader phát item. Nếu business cần “tăng số dư theo trình tự giao dịch”, không thể chỉ thêm `ORDER BY` rồi tăng concurrency tự do.

### Thứ tự toàn cục khác thứ tự cục bộ theo khóa

| Yêu cầu | Kiến trúc có thể phù hợp |
| --- | --- |
| Chỉ cần output là tập bản ghi, không quan tâm order | Split flows/partitioning độc lập, writer idempotent |
| Mọi sự kiện của một account phải theo thứ tự | Keyed partitioning theo account + sequence, xử lý tuần tự trong key |
| Cần một total order toàn hệ | Một nơi serialize, sequence coordinator hoặc protocol commit có thứ tự |
| Chỉ cần bước tổng hợp sau các nguồn | Split + join/barrier + reconciliation |

Chỉ chọn concurrent execution khi **phép toán giao hoán/độc lập hoặc ordering contract có thể được bảo vệ**. Thêm thread không thể “miễn phí” nếu nghiệp vụ yêu cầu total order chặt chẽ.

## 12. `StepExecution` và `ExecutionContext` khi các step chạy song song

Một `JobInstance` có thể có nhiều `JobExecution` qua các lần restart. Mỗi step có `StepExecution` và `StepExecutionContext` của nó; `JobRepository` là nơi lưu metadata phục vụ quan sát và phục hồi.

~~~text
JobInstance: nightly-report(snapshotId=snap-20261125)
└── JobExecution 17
    ├── preparationStep       COMPLETED
    ├── loadCustomersStep     COMPLETED
    ├── loadOrdersStep        FAILED
    ├── loadProductsStep      COMPLETED
    └── aggregateReportStep   NOT STARTED
~~~

Đây là trạng thái minh họa khi một nhánh lỗi. `aggregateReportStep` không nên được chạy trong đường thành công nếu một nhánh bắt buộc chưa đạt. Khi restart, metadata của các step đã hoàn thành phải được giữ để framework áp dụng restart policy thay vì đọc lại mọi dữ liệu như một job mới.

### Không dùng JobExecutionContext như biến global điều phối

Các nhánh được thực thi đồng thời có thể có access tới cùng job execution context. Nhưng một map context không phải cơ chế transaction/synchronization giữa thread hoặc JVM.

Anti-pattern:

~~~java
// Flow A
jobExecution.getExecutionContext()
        .putString("currentSource", "customers");

// Flow B
jobExecution.getExecutionContext()
        .putString("currentSource", "orders");

// Flow C
String source = jobExecution.getExecutionContext()
        .getString("currentSource");
~~~

`currentSource` có thể phụ thuộc nhánh nào ghi sau cùng; không có cơ sở để C luôn thấy `customers` hay `orders`. Kể cả khi map thread-safe, **ngữ nghĩa last-writer-wins vẫn không tạo ra dependency đúng**. Việc persist `JobExecutionContext` trong repository cũng không biến một key thành distributed lock hay message queue.

Dùng giải pháp:

- `StepExecutionContext` lưu state cục bộ mỗi step: reader cursor, snapshotId, partition range.
- Output của nhánh nằm trong DB/object namespace có khóa `(snapshotId,stageName,recordId)` hoặc tương đương.
- Sau khi join, bước validator truy vấn các output/marker đã commit và dựng kết quả chung.
- Nếu cần promote dữ liệu từ step context lên job context bằng `ExecutionContextPromotionListener`, tránh việc hai nhánh cùng promote một key và dựa vào thứ tự ghi; ưu tiên key tách biệt và merge sau barrier.

### Metadata không phải một clock toàn cục

`StepExecution.startTime` và `endTime` giúp quan sát nhưng thời gian ghi nhận có thể chịu lệch clock giữa host, delay repository và precision DB. Không dùng timestamp của các step để quyết định event nào “đã xảy ra trước” khi nghiệp vụ cần một total order chắc chắn.

## 13. Retry/restart: một nhánh xong, nhánh khác thất bại

Giả sử flow A và B chạy song song. A đã commit đầy đủ `customers`, B xử lý `orders` tới chunk 105 rồi chết. Trong một `JobInstance` cần restart:

~~~text
Lần chạy đầu:
  prepareSnapshotStep  COMPLETED
  loadCustomersStep    COMPLETED
  loadOrdersStep       FAILED
  aggregateStep        chưa chạy

Restart:
  prepareSnapshotStep  thường không phải chạy lại
  loadCustomersStep    thường được skip theo restart policy
  loadOrdersStep       tiếp tục từ checkpoint phù hợp
  aggregateStep        chỉ chạy sau các tiền điều kiện hoàn tất
~~~

Các từ “thường” quan trọng vì `allowStartIfComplete`, `startLimit`, step transitions và các custom policy có thể thay hành vi.

**Không** tạo identifying `run.id` mới rồi gọi đó là restart: `JobInstance` mới có thể chạy lại tất cả các nhánh và kích hoạt side effect đã xảy ra. Nếu muốn reprocess toàn bộ, cần kế hoạch dữ liệu, idempotency và đối soát khác.

### Những thứ phải ổn định qua restart

1. Input snapshot/manifest và version được đọc bởi mỗi nhánh.
2. Tên step/flow khi metadata và checkpoint cũ vẫn cần được diễn giải.
3. Ordering của reader, cursor state và serialized `ExecutionContext`.
4. Business key dùng để dedup/UPSERT hoặc ledger external operation.
5. Quy tắc công bố stage READY sau khi output đã commit đầy đủ.
6. Các transitions sau join: không publish khi vẫn còn input bắt buộc chưa hoàn tất.

### Nhánh A thành công không có nghĩa rollback được khi B lỗi

Các chunk của A có transaction và commit riêng. B thất bại **không tự rollback** output của A. Nếu cần atomic publish ở tầm report, dùng **versioned staging + publish marker**: các nhánh có thể commit vào snapshot version chưa công bố, còn bước publish duy nhất sau join quyết định bản kết quả nào được nhìn thấy.

Nếu pipeline cập nhật hệ thống bên ngoài trong mỗi branch, compensating transaction có thể cần thiết; đừng dùng một transaction lớn kéo dài hàng giờ để “gom” mọi parallel step, vì lock, connection timeout và consistency phức tạp hơn.

### Khi manager/job process mất node

Một `JobExecution` có thể bị để lại trạng thái `STARTED` vì process chết trước khi ghi status cuối. Không tự sửa bảng `BATCH_*` để chạy lại; cần runbook xác minh process cũ đã dừng, phục hồi trạng thái theo cơ chế quản lý của phiên bản Spring Batch và đối soát các chunk đã commit.

## 14. Kiểm tra scheduling bằng trace nhưng đừng phụ thuộc vào trace

Muốn chứng minh parallel steps **có thể** chạy chồng thời gian, nên ghi các sự kiện bắt đầu/kết thúc bằng công cụ thread-safe; nhưng một lần trace chỉ chứng minh một lần execution.

Ví dụ Java 17 listener dùng cho kiểm thử/điều tra trong **một JVM**:

~~~java
import java.time.Instant;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

record StepEvent(
        String stepName, String phase, Instant at,
        long threadId) {}

public final class StepTimelineListener
        implements StepExecutionListener {

    private final Queue<StepEvent> events =
            new ConcurrentLinkedQueue<>();

    @Override
    public void beforeStep(StepExecution stepExecution) {
        events.add(new StepEvent(
                stepExecution.getStepName(),
                "START",
                Instant.now(),
                Thread.currentThread().getId()));
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        events.add(new StepEvent(
                stepExecution.getStepName(),
                "END",
                Instant.now(),
                Thread.currentThread().getId()));
        return stepExecution.getExitStatus();
    }

    public Queue<StepEvent> events() {
        return events;
    }
}
~~~

Listener trên dùng `ConcurrentLinkedQueue` vì các nhánh có thể gọi đồng thời; `ArrayList` dùng chung mà không đồng bộ có thể bị race.

Trong production không nên giữ vô hạn mọi item/step event trong heap. Dùng structured logs hoặc metrics với cardinality được kiểm soát. `threadId` chỉ là tín hiệu trong JVM, không phải định danh toàn cụm; dùng thêm instance ID/worker ID nếu cần correlate.

**Không dùng event START/END để áp đặt thứ tự nghiệp vụ.** Việc A có timestamp nhỏ hơn B không phải hợp đồng future runs. `ExitStatus` ở listener không tự thay business correctness; trả lại status framework theo ví dụ tránh ghi đè sai transitions.

## 15. Kiểm thử concurrency đúng cách: đồng bộ bằng CountDownLatch

Một bài test chỉ dùng `Thread.sleep(200)` rồi assert B bắt đầu “trước 200 ms” thường flaky: máy CI có thể chậm, tải DB khác nhau, GC pause không dự báo được. Thay vào đó, dùng **latch** để xác nhận hai flow đã đi vào tasklet trước khi cho chúng thoát.

### Test double tạo bằng chứng overlap

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public final class ParallelStartGate {

    private final CountDownLatch bothStarted =
            new CountDownLatch(2);
    private final CountDownLatch allowFinish =
            new CountDownLatch(1);

    public Tasklet probedTasklet() {
        return (contribution, chunkContext) -> {
            bothStarted.countDown();

            if (!allowFinish.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Parallel-start test timed out");
            }

            return RepeatStatus.FINISHED;
        };
    }

    public boolean bothStartedInTime()
            throws InterruptedException {
        return bothStarted.await(5, TimeUnit.SECONDS);
    }

    public void release() {
        allowFinish.countDown();
    }
}
~~~

Tạo **hai Step khác tên** với cùng gate để đảm bảo cả hai đã vào `Tasklet.execute`. Một test integration có thể chạy JobLauncher trong một test thread khác:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.launch.JobLauncher;

class ParallelStepsIntegrationTest {

    private final JobLauncher launcher;
    private final Job job;
    private final ParallelStartGate gate;

    ParallelStepsIntegrationTest(
            JobLauncher launcher,
            Job job,
            ParallelStartGate gate) {
        this.launcher = launcher;
        this.job = job;
        this.gate = gate;
    }

    @Test
    void twoSplitBranchesCanEnterTheirTaskletsTogether()
            throws Exception {

        var params = new JobParametersBuilder()
                .addString("runKey", UUID.randomUUID().toString())
                .toJobParameters();

        CompletableFuture<JobExecution> run =
                CompletableFuture.supplyAsync(() -> {
                    try {
                        return launcher.run(job, params);
                    } catch (Exception e) {
                        throw new CompletionException(e);
                    }
                });

        try {
            assertTrue(gate.bothStartedInTime(),
                    "Both flow branches should reach tasklets");
        } finally {
            // Không để test thread giữ job kẹt khi assert fail.
            gate.release();
        }

        JobExecution execution =
                run.get(30, TimeUnit.SECONDS);

        assertEquals(BatchStatus.COMPLETED,
                execution.getStatus());
    }
}
~~~

Đây là **khung integration test minh họa**: test runner phải cung cấp ba dependency `JobLauncher`/`Job`/`ParallelStartGate` qua Spring test context hoặc fixture thích hợp; hai Step được tạo với `gate.probedTasklet()` và mỗi Step chỉ thuộc **một nhánh** của split. Test không tự chạy riêng nếu chưa wiring beans, transaction manager và repository.

### Ví dụ tạo hai probe steps

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.transaction.PlatformTransactionManager;

Step probeStep(
        String name, JobRepository repository,
        PlatformTransactionManager tx,
        ParallelStartGate gate) {

    return new StepBuilder(name, repository)
            .tasklet(gate.probedTasklet(), tx)
            .build();
}

// Mỗi nhánh dùng tên Step khác nhau:
// probeStep("branchA", repository, tx, gate)
// probeStep("branchB", repository, tx, gate)
~~~

**Điều kiện quan trọng:** split executor phải có tối thiểu hai execution slots và không bị chặn bởi task khác. Với pool một thread, test sẽ timeout — đó là dấu hiệu flow không thể cùng vào tasklet ở cấu hình đang test, **không chứng minh framework có thứ tự mặc định**.

### Test concurrency chưa đủ để chứng minh không có ordering guarantee

Test này chứng minh **khả năng overlap**, không phải tổng quát hóa mọi lịch chạy. Cần thêm các test cố ý làm A chậm/B nhanh và B chậm/A nhanh; output vẫn phải đúng. Không tạo test yêu cầu “B phải luôn hoàn tất trước A” trừ khi có dependency được thiết kế rõ.

### Test barrier một cách xác định

Tạo hai branch tasklet đều chờ latch. Trong lúc latch chưa release, bước `aggregateStep` **không được ghi marker đã chạy**. Sau khi release và hai branch thành công, chỉ lúc đó aggregate mới được đánh dấu.

Có thể dùng `AtomicBoolean aggregateStarted` như test probe ở một JVM; kết hợp business DB marker trong integration test để xác nhận dữ liệu cuối, nhất là khi dùng remote deployment.

## 16. Kiểm thử lỗi: một nhánh FAILED, nhánh khác còn chạy

Giả lập hai flow:

~~~text
Flow A:
  loadCustomersStep (thành công sau 1 giây)

Flow B:
  loadOrdersStep (đã commit 20 chunk, rồi FAILED)

Sau split:
  aggregateReportStep
~~~

Tùy flow-status aggregation, transitions và chính sách, các step sau split có thể bị chặn hoặc đi vào nhánh xử lý lỗi. **Yêu cầu business:** `aggregateReportStep` tuyệt đối không được publish báo cáo hoàn chỉnh khi `orders` còn thiếu dữ liệu.

Bài kiểm thử nên xác minh:

- `loadCustomersStep` có thể đã commit output riêng, không mặc định rollback khi orders fail.
- `loadOrdersStep` để lại metadata/chunk checkpoint hợp lệ và input snapshot không thay đổi.
- Split không đánh dấu hoàn tất giả thành đường success khi một nhánh bắt buộc lỗi.
- Bước validation sau split kiểm tra đúng ba stage markers, không chỉ một step `COMPLETED`.
- Restart dùng cùng `JobInstance`; các step đã hoàn tất được xử lý theo restart policy.
- Sau restart và reconciliation, publication chỉ xuất hiện một lần theo business key.

### Tình huống nguy hiểm: cố bắt lỗi để luôn trả COMPLETED

Nếu tasklet bắt mọi exception, log rồi trả `RepeatStatus.FINISHED` hoặc custom listener luôn chuyển `ExitStatus` thành `COMPLETED`, framework có thể cho nhánh coi là thành công dù dữ liệu thiếu. Điều này **không phải giải pháp cho điều phối flow** mà là che lỗi.

Xử lý lỗi có chủ đích nên phân biệt retryable/non-retryable, skip policy rõ, business validation và trạng thái publish riêng. Với output tài chính hoặc báo cáo cần tính đầy đủ, không nên cho phép silent skip.

## 17. Điều phối dependency bằng dữ liệu: event/marker có version

Khi hệ thống không thể biểu diễn toàn bộ pipeline trong một Job (ví dụ từng nguồn là service riêng), một dependency có thể được bảo vệ bằng **durable readiness marker** thay vì thread scheduling.

Ví dụ:

~~~text
Snapshot: snap-20261125
Stage: customers
  status = READY
  source_version = v23
  committed_count = 200000
  validated = true

Stage: orders
  status = READY
  source_version = v23
  committed_count = 300000
  validated = true

Stage: products
  status = READY
  source_version = v23
  committed_count = 50000
  validated = true
~~~

Một bước tổng hợp chỉ dùng các stage **đúng cùng snapshot/source version**, và chỉ chạy khi cả ba đã được commit/validate. Marker không chỉ là boolean trong cache hoặc `JobExecutionContext` mà là bản ghi bền vững gắn với dữ liệu thật.

### Tránh TOCTOU khi đọc markers

Quy trình nguy hiểm:

1. Kiểm tra ba markers cùng `READY`.
2. Một service khác xóa hoặc thay dữ liệu staging.
3. Bước aggregate đọc data đã bị đổi.

Cách thiết kế an toàn hơn:

- Giữ staging **bất biến theo version** sau khi được READY.
- Các bước aggregate đọc theo `snapshotId`/version đã chốt.
- Publication dùng unique key hoặc pointer swap có điều kiện để tránh ghi đè không nhất quán.
- Gắn kiểm tra readiness với transaction/isolation hoặc validation protocol phù hợp.

**Chỉ dùng marker không có immutable input và retention thì vẫn có race** dù split và join ở cấp flow đúng.

### Event ordering trong hệ phân tán

Nếu branch A publish `StageReady` qua broker, branch B có thể nhận event trước khi transaction DB của A commit nếu thiếu transactional outbox. Dùng outbox hoặc cơ chế publish-after-commit được bảo đảm, và consumer kiểm tra version/idempotency. Không mặc định broker bảo đảm thứ tự toàn cục giữa topics/partitions hoặc giữa các producer khác nhau.

## 18. Chọn phạm vi chạy song song để tránh phá hỏng thứ tự nghiệp vụ

| Công việc | Có thể song song? | Điều kiện |
| --- | --- | --- |
| Nạp Customers và Products từ hai immutable snapshot | **Có** | Output độc lập, không cùng namespace mutable |
| Nạp Orders sau khi Customer dimensions READY | **Không song song với bước chuẩn bị dimension** nếu cần lookup trực tiếp | Dùng dependency A → B |
| Tạo index và chạy query phụ thuộc index | Tùy yêu cầu | Nếu query cần index tồn tại/ready, phải chờ hoàn tất |
| Nạp dữ liệu hai ngày độc lập vào bảng có khóa `(date,id)` | **Có**, nếu dữ liệu/tài nguyên đủ | Partition theo key rõ, writer idempotent |
| Hai step cập nhật một global balance | Cần serialize/ledger hoặc phép cộng an toàn | Tránh lost update, xác định transaction/ordering |
| Tạo ba báo cáo độc lập rồi đóng gói ZIP | **Có cho ba nhánh** | ZIP/manifest chỉ chạy sau join |
| Gửi các event có sequence của cùng account | Không tự do đảo thứ tự | Keyed serialization/sequence gate |
| Xử lý snapshot bằng partitioning nhiều worker | **Có**, nếu item độc lập | Không cần total order hoặc có per-key ordering |

### Khi nào nên dùng parallel steps, khi nào dùng partitioning?

Nếu ba bước thực sự khác nghiệp vụ/logic (nạp customers, orders, products), **parallel steps với split flows** là một lựa chọn tự nhiên. Nếu cùng một phép biến đổi cần chia 100 triệu record thành các range, **partitioning** thường đúng abstraction hơn, với `StepExecution` riêng cho từng miền.

Nếu mọi item bắt buộc theo thứ tự toàn cục, dùng một reader/consumer có thứ tự hoặc một stage serialize ở cuối có thể hợp lý hơn. Đừng ép multi-threading khi chi phí bảo đảm ordering lớn hơn lợi ích throughput.

## 19. Đo hiệu quả thực tế thay vì chỉ đếm số nhánh

Giả sử hai step độc lập:

~~~text
Nếu chạy tuần tự:
  A = 12 phút
  B = 8 phút
  Total = 20 phút, chưa tính phần chung.

Nếu chạy song song lý tưởng:
  max(A,B) = 12 phút, cộng overhead split/join.

Nếu DB/I/O bị tranh chấp:
  A có thể tăng lên 17 phút,
  B tăng lên 13 phút.
  Total song song = 17 phút + overhead.
~~~

Lý tưởng nhất, split giảm tổng thời gian gần `T_A + T_B` xuống `max(T_A,T_B)` với hai nhánh độc lập. Nhưng resource contention, DB locks, pool saturation, GC và metadata có thể khiến thực tế kém xa lý tưởng.

### Những metric cần quan sát

| Nhóm | Ví dụ chỉ số | Ý nghĩa |
| --- | --- | --- |
| Flow timing | Start/end/duration từng branch | Nhận diện straggler; **không dùng làm dependency** |
| Job timing | End-to-end duration gồm prepare/join/reconcile | Đánh giá SLA thực |
| Worker concurrency | Executor active threads và queue | Xác nhận mức overlap thật |
| Reader | Read count/s, snapshot remaining | Có đủ input hay đang drain |
| Business output | Unique commits/s, missing/extra keys | Throughput hữu ích và correctness |
| Step metadata | `READ_COUNT`, `WRITE_COUNT`, `COMMIT_COUNT`, `ROLLBACK_COUNT` | Chẩn đoán tiến độ/retry |
| DB | Active/pending pool, lock wait, commit latency | Bottleneck shared resources |
| JVM | CPU/GC/heap/throttling | GC pause hoặc CPU quota |
| Broker | Queue depth, redelivery, reply latency | Rủi ro distributed ordering |
| Restart | RTO, replayed chunks, version mismatch | Phục hồi an toàn |

Bước split có thể tăng throughput trong thời gian đầu nhưng backlog phía DB vẫn tăng, làm thời gian cuối của job tệ hơn. Thử nghiệm phải đo cả **sustained goodput** và tail latency qua nhiều lần chạy, không chỉ peak item/s.

### Phân bổ tài nguyên

Nếu ba flow cùng mở `JdbcCursorItemReader` và writer transaction, số DB connections tiêu thụ có thể lớn hơn số flow. Với remote workers, tổng connection across JVM có thể vượt giới hạn DB dù mỗi pod có pool nhỏ. Đặt executor/pool limits dựa trên capacity thực đo và giữ headroom cho `JobRepository`.

## 20. Ma trận kiểm thử ordering trước production

Một hệ thống có split flows cần test **nhiều lịch chạy khác nhau**, không chỉ quan sát một lần flow A hoàn tất trước B rồi kết luận rằng chúng luôn theo thứ tự ấy.

| Kịch bản | Cách thử | Kỳ vọng |
| --- | --- | --- |
| A khởi động chậm hơn B | Giữ A bằng latch, cho B vào tasklet | B có thể bắt đầu trước A nếu cùng split |
| B hoàn thành trước A | Chặn A trước commit, hoàn thành B | Downstream sau join chưa được publish |
| Pool chỉ có một thread | Executor một slot | Có thể chạy gần tuần tự, nhưng không coi đó là dependency |
| A FAILED khi B còn chạy | Lỗi A sau 10 chunk | Downstream gate không publish dữ liệu thiếu |
| A STOPPED có chủ đích | Stop theo API thích hợp | Trạng thái restart và dữ liệu đã commit được giữ |
| Manager crash khi B đã commit | Kill manager trước reply | Khôi phục metadata, không tạo duplicate effect |
| Hai nhánh ghi cùng job-context key | Tạo conflict trong test | Không dựa vào last-writer-wins |
| Hai nhánh ghi cùng output key | Chèn hai business record trùng key | Unique constraint/ledger bảo vệ hoặc fail rõ |
| Marker READY quá sớm | Ghi marker trước khi output xong | Validation sau join phát hiện thiếu |
| A dùng snapshot v1, B dùng v2 | Cố tình lệch version | Downstream chặn publication |
| Restart sau A COMPLETED, B FAILED | Dùng cùng identifying params | B resume; A theo restart policy |
| Tên step thay giữa phiên bản | Rolling deployment | Compatibility hoặc migration được kiểm thử |
| Một nhánh chứa 90% dữ liệu | Tạo straggler | Job chờ nhánh còn lại, không publish sớm |
| Worker out-of-order event | Đảo thứ tự message | Per-key sequence/dedup theo business contract |
| Reconciliation thất bại | Cố tạo missing business keys | Chặn publish dù StepExecution COMPLETED |

### Kiểm thử hai lịch chạy đối nghịch

Với hai branch độc lập:

~~~text
Test 1: A bị giữ tại latch; B được chạy tới completion.
Test 2: B bị giữ tại latch; A được chạy tới completion.
~~~

Dùng latch hoặc test double có điều khiển; không dùng `Thread.sleep(5000)` để đoán chắc bước nào đã xong. Trong cả hai phép thử, **output phải giống nhau** và bước sau barrier không được publish trước khi đủ tiền điều kiện.

Nếu ứng dụng chỉ hoạt động đúng khi A “thường hoàn thành trước B”, đó là một dependency còn thiếu trong flow graph.

## 21. Runbook khi hai step chạy sai thứ tự

Khi một downstream step đọc staging chưa sẵn sàng hoặc báo cáo bị publish thiếu:

1. **Khoanh vùng:** JobInstance, JobExecution, step names, flow names, snapshot/version và thời điểm xảy ra lỗi.
2. **Xem cấu hình flow graph:** step nào nằm trong split, cạnh `next(...)` nào tồn tại và custom transition nào cho phép đi qua `FAILED`/`STOPPED`?
3. **Kiểm tra executor:** core/max pool, queue, rejected tasks, shutdown; không suy từ thứ tự khai báo Java.
4. **Đọc StepExecution states:** nhánh nào thực sự start, commit, complete, fail hoặc retry.
5. **Đọc readiness markers:** stage nào READY, version nào, marker đã được persist sau commit đầy đủ chưa.
6. **Xác minh dữ liệu nguồn/đích:** snapshot bất biến, unique keys, expected count, output mismatch và checkpoint.
7. **Tìm shared mutable state:** cùng file path, `JobExecutionContext` key, singleton reader/writer hoặc bảng aggregate.
8. **Đối soát side effects:** duplicate publish, email, payment hoặc event ngoài DB.
9. **Tạm dừng publication** nếu dữ liệu chưa đầy đủ; không cho downstream “chạy tiếp thử”.
10. **Sửa dependency:** chuyển producer ra trước split, đưa consumer sau barrier hoặc triển khai durable readiness protocol có version.
11. **Restart hợp lệ:** giữ `JobInstance`/snapshot/step identity nếu resume; không xóa `BATCH_*` tùy tiện.
12. **Tái thử lịch chạy đối nghịch:** A nhanh/B chậm, B nhanh/A chậm, branch failure, redelivery và manager crash.
13. **Đo lại capacity:** DB pool, locks, JVM GC và executor queue; không mặc định thêm thread sẽ khắc phục vấn đề.
14. **Đóng sự cố** khi business reconciliation PASS và publication xảy ra đúng theo policy.

### Dấu hiệu race condition

- Chỉ lỗi khi tăng số worker từ 1 lên 4.
- Cùng một input nhưng một số execution báo thiếu dimension table, số khác hoàn thành.
- Log thấy B đọc dữ liệu khi A vẫn `STARTED` dù nghiệp vụ đòi A xong.
- Retry làm lỗi biến mất mà không sửa dependency.
- Staging file đã xuất hiện nhưng còn thiếu record.
- `publishReportStep` đôi khi chạy trong lúc branch vẫn chưa sẵn sàng.

Không chữa bằng cách tăng thời gian `Thread.sleep` hoặc thêm retry vô hạn. Hãy sửa **flow dependency và ranh giới công bố dữ liệu**.

## 22. Bài tập tình huống: báo cáo cuối ngày chạy ba nhánh

Một job mỗi đêm nhận snapshot `snap-20261125`. Các bước:

| Step | Dữ liệu | Thời gian lý tưởng | Phụ thuộc |
| --- | --- | ---: | --- |
| `validateSourceStep` | Xác minh ba nguồn | 2 phút | Không |
| `loadCustomersStep` | 200.000 khách hàng | 6 phút | Validate |
| `loadProductsStep` | 100.000 sản phẩm | 3 phút | Validate |
| `loadOrdersStep` | 1.000.000 đơn hàng | 9 phút | Validate |
| `enrichOrdersStep` | Bổ sung customer/product dimension | 5 phút | Customers, Products, Orders |
| `publishReportStep` | Công bố báo cáo | 1 phút | Enrich và reconciliation |

Nhóm phát triển đề xuất đưa **tất cả sáu step** vào một split với sáu thread.

**Câu hỏi:**

1. Vì sao cấu hình này không đảm bảo báo cáo đúng?
2. Hãy vẽ DAG và chỉ ra các cạnh dependency bắt buộc.
3. Bước nào được chạy song song ngay sau `validateSourceStep`?
4. `enrichOrdersStep` nên ở đâu trong flow?
5. Nếu chạy hoàn toàn tuần tự, tổng thời gian lý tưởng là bao nhiêu?
6. Nếu parallel hóa ba load steps và có đủ tài nguyên, thời gian lý tưởng còn bao nhiêu?
7. Nếu Products mất 12 phút thay vì 3 phút, critical path thay đổi ra sao?
8. Nếu Customers COMPLETED và Orders FAILED sau vài chunk, có chạy enrich không?
9. Restart cùng `JobInstance` có buộc làm lại mọi branch đã COMPLETED không?
10. Nếu ba branch cùng ghi `jobExecutionContext.put("loadedRows", count)`, giá trị cuối có tin được không?
11. Nhận ba event `StageReady` nhưng source versions khác nhau có đủ điều kiện publish không?
12. Đề xuất hai test dùng latch và một phép business reconciliation chứng minh thiết kế đúng.

### Gợi ý đáp án

~~~mermaid
flowchart TD
    V["validateSourceStep"] --> C["loadCustomersStep"]
    V --> P["loadProductsStep"]
    V --> O["loadOrdersStep"]
    C --> E["enrichOrdersStep"]
    P --> E
    O --> E
    E --> R["reconcileOutputStep"]
    R --> U["publishReportStep"]
~~~

- **(1)** Split không tạo dependency giữa các sibling steps; enrich có thể chạy khi dimensions chưa sẵn sàng.
- **(2)** DAG như sơ đồ trên.
- **(3)** Customers, Products và Orders có thể chạy song song nếu cùng snapshot bất biến, output độc lập.
- **(4)** Sau join của ba load branches, kèm validation yêu cầu.
- **(5)** `2+6+3+9+5+1=26 phút`, chưa kể reconciliation riêng.
- **(6)** `2+max(6,3,9)+5+1=17 phút`, giả định đủ capacity và overhead không đáng kể.
- **(7)** `max(6,12,9)=12` phút; Products thành straggler, tổng lý tưởng `2+12+5+1=20 phút`.
- **(8)** Không; Orders là input bắt buộc chưa hợp lệ.
- **(9)** Không mặc định; step đã completed được xử lý theo restart policy.
- **(10)** Không. Last-writer-wins hoặc context persist không ổn định cho phép cộng tổng; dùng stage-specific markers và merge sau join.
- **(11)** Không; phải cùng snapshot/version, commit thành công và có reconciliation.
- **(12)** Test A nhanh/B chậm và B nhanh/A chậm, đều assert publish chỉ sau join; so business keys/version và publication unique.

**Kết luận:** parallel hóa giúp giảm thời gian **chỉ ở các bước không có cạnh dependency trực tiếp**. Thiết kế DAG là công việc đi trước chỉnh thread pool.

## 23. Checklist trước production

- [ ] Phân biệt thứ tự khai báo, thứ tự bắt đầu thực tế, thứ tự hoàn thành và thứ tự business items.
- [ ] Đã vẽ DAG và nhận diện dependency bắt buộc.
- [ ] Split chỉ chứa các nhánh độc lập hoặc có contract concurrency rõ.
- [ ] Producer đã commit/publish READY trước khi consumer bắt đầu phụ thuộc.
- [ ] Có join/barrier trước validator, aggregate và publish.
- [ ] Transitions `COMPLETED`/`FAILED`/`STOPPED` được xác minh với business contract.
- [ ] Không dựa vào `Thread.sleep`, timestamp log hoặc thứ tự `add(...)` để tạo dependency.
- [ ] `JobExecutionContext` không dùng như shared-memory latch; state step giữ ở `StepExecutionContext`.
- [ ] Không có mutable singleton, file path hay global table bị tranh chấp không kiểm soát.
- [ ] Stage output tách namespace theo snapshot/branch/version, unique key và idempotency.
- [ ] READY marker ghi sau commit và có validation/retention hợp lệ.
- [ ] Restart cùng JobInstance giữ snapshot/step identities và state reader.
- [ ] Có test A nhanh/B chậm và B nhanh/A chậm, branch failure và crash.
- [ ] Có resource budget CPU/GC, JDBC pool, JobRepository và broker.
- [ ] Đo end-to-end duration, sustained goodput, tail latency và branch skew.
- [ ] Reconciliation kiểm tra missing/extra/wrong version trước publication.
- [ ] Có runbook xử lý race, orphaned execution và partial commit.

## 24. Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): parallel steps qua split flow và `TaskExecutor`.
- [Spring Batch 5.2 Reference – Scaling](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): đối chiếu API Spring Batch 5.x.
- [Spring Batch Reference – Configuring a Job](https://docs.spring.io/spring-batch/reference/job.html): flow transitions, restart và status.
- [Spring Batch Reference – Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `StepExecution`, `ExecutionContext`.
- [Spring Batch Reference – Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): `Flow`, `split`, conditional transitions.
- [Spring Batch Reference – ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint/restart state.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): remote partitioning/chunking.
- [Spring Framework – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor` và thread pools.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries.
- [Java 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): kiểm thử concurrency.
- [PostgreSQL – Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): data visibility và consistency.
- [PostgreSQL – INSERT/ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): publication marker/idempotency.

## Ghi nhớ

**Parallel steps không có thứ tự bắt đầu hoặc hoàn thành mặc định chỉ vì chúng xuất hiện theo thứ tự trong cấu hình Java.** Với Spring Batch, `split(TaskExecutor)` **cho phép concurrency**, còn **flow transitions, `next(...)`, join/barrier và readiness validation** mới biểu diễn dependency bắt buộc. Mỗi nhánh phải sở hữu state/output rõ ràng, đọc cùng snapshot/version bất biến, có thể restart và replay an toàn. Không dùng `Thread.sleep`, `JobExecutionContext` mutable hoặc timestamp log làm cơ chế điều phối. Kiểm thử cả hai lịch chạy đối nghịch, nhánh lỗi và recovery; đo throughput cùng contention và reconciliation. **Job parallel tốt là job nhanh hơn mà vẫn giữ đúng quan hệ nhân quả và kết quả nghiệp vụ.**
