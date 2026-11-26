# Cross-talk giữa worker instance trong Spring Batch

> **Chương:** Step scope
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán. Bài học tập trung vào hiện tượng **cross-talk (rò rỉ/trộn trạng thái)** giữa worker, cách dùng `@StepScope` đúng chỗ, và việc bảo đảm tính đúng đắn khi có concurrency, retry/restart.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cross-talk giữa các worker instance và phân biệt nó với việc hai partition đọc trùng dữ liệu.
2. Nhận diện mutable singleton, `static` field, bộ đệm chung, `ThreadLocal` và scope sai gây truyền nhầm cấu hình hoặc state giữa các `StepExecution`.
3. Dùng `@StepScope` và late binding qua `stepExecutionContext` để tạo reader/processor theo **đúng worker execution**, không theo thread hay toàn job.
4. Xây dựng kiểm thử chạy nhiều partition đồng thời và phát hiện tenant/range/state bị trộn.
5. Thiết kế metric, log, giao dịch và restart/idempotency để phát hiện lỗi mà không nhầm isolation trong JVM với an toàn ghi dữ liệu ở đích.

## 1. Cross-talk là gì?

Trong Spring Batch **partitioning**, manager tạo các partition có tên và `ExecutionContext` riêng, chẳng hạn hai tenant khác nhau:

| Worker partition | `ExecutionContext` | Kỳ vọng |
| --- | --- | --- |
| `ordersWorkerStep:tenant-A` | `tenantId = "A"`, `minId = 1`, `maxIdExclusive = 1001` | Chỉ xử lý đơn hàng của A thuộc khoảng ID |
| `ordersWorkerStep:tenant-B` | `tenantId = "B"`, `minId = 1001`, `maxIdExclusive = 2001` | Chỉ xử lý đơn hàng của B thuộc khoảng ID |

**Cross-talk** xảy ra khi trạng thái hoặc cấu hình **thuộc riêng worker A** bị worker B nhìn thấy/sửa, hoặc ngược lại. Ví dụ:

- Worker A bắt đầu với `tenantId = A` nhưng processor đọc nhầm một biến đã bị worker B thay thành `B`.
- Reader A sử dụng cursor/offset do B cập nhật nên bỏ qua hoặc đọc lại trang dữ liệu.
- Bộ đệm đầu ra chung gom item từ hai tenant rồi writer gửi về một đích của tenant sau cùng.
- `ThreadLocal` chứa partition ID của một task cũ không được xóa khi thread pool tái sử dụng thread.

Cross-talk có thể gây **rò rỉ dữ liệu giữa tenant, ghi sai bảng, sai tính tổng, mất item, duplicate hoặc checkpoint sai**. Đây là lỗi **cách ly state giữa execution**, không nhất thiết là lỗi chia phạm vi dữ liệu đầu vào.

### Cross-talk khác dữ liệu nguồn chồng lấn

| Lỗi | Ví dụ | Nguyên nhân chính |
| --- | --- | --- |
| **Cross-talk trạng thái** | B đọc biến `currentTenant` do A thiết lập | Bean/state được chia sẻ giữa các worker |
| **Partition overlap** | A và B đều truy vấn `id BETWEEN 1 AND 100` | Partitioner/predicate chia dữ liệu sai |
| **Replay khi retry/restart** | A gửi lệnh API hai lần sau timeout | Transaction, checkpoint hoặc idempotency chưa phù hợp |
| **Race khi ghi đích** | Hai worker cùng update một aggregate row | Concurrency/locking hoặc transaction tại đích |

Các vấn đề có thể kết hợp với nhau. `@StepScope` giải quyết **lifetime của bean theo step execution**, nhưng không tự sửa SQL overlap hoặc cung cấp exactly-once effect.

## 2. Vì sao lỗi hay xảy ra khi scale?

Spring Framework tạo bean `@Component` / `@Bean` theo **singleton scope mặc định**. Nếu một worker step được tái sử dụng trong nhiều partition, các worker `StepExecution` có thể cùng gọi **một instance singleton** của reader, processor, writer hoặc listener.

Nếu singleton **stateless** và implementation thread-safe thì việc chia sẻ có thể an toàn. Rủi ro xuất hiện khi nó có **mutable state phụ thuộc partition**, ví dụ `currentTenant`, `currentFile`, `cursor`, `List` kết quả tích lũy hoặc cache không có isolation.

~~~mermaid
sequenceDiagram
    participant A as Worker A / StepExecution A
    participant P as Singleton processor
    participant B as Worker B / StepExecution B
    A->>P: beforeStep(): currentTenant = A
    B->>P: beforeStep(): currentTenant = B
    A->>P: process(order of A)
    Note over P: currentTenant vẫn là B
    P-->>A: Output bị gắn tenant B
    B->>P: process(order of B)
    P-->>B: Output tenant B
~~~

Trong bước tuần tự, lỗi có thể **không lộ ra** vì từng step chạy xong mới tới step khác. Khi tăng số worker, nhiều method bị gọi đan xen và lỗi xuất hiện không ổn định. Vì vậy “chạy đúng với một thread” không chứng minh an toàn khi partitioning.

### Mã có nguy cơ cross-talk

~~~java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

@Component  // Mặc định singleton: tất cả worker có thể dùng chung instance.
public class UnsafeTenantProcessor
        implements ItemProcessor<OrderRow, OutputRow>,
                   StepExecutionListener {

    private String currentTenant; // Mutable state của từng partition!

    @Override
    public void beforeStep(StepExecution stepExecution) {
        currentTenant = stepExecution
                .getExecutionContext()
                .getString("tenantId");
    }

    @Override
    public OutputRow process(OrderRow item) {
        // Worker A có thể đọc currentTenant của worker B.
        return new OutputRow(item.id(), currentTenant, item.amount());
    }
}
~~~

Trong ví dụ, `OrderRow` và `OutputRow` là kiểu dữ liệu nghiệp vụ tự định nghĩa. Vấn đề **không nằm ở việc thiếu `volatile`**: đặt `volatile` chỉ cải thiện khả năng nhìn thấy giá trị, **không tạo mỗi worker một bản `currentTenant`**. `synchronized` có thể loại bỏ race đối với từng method, nhưng nếu `beforeStep()` và `process()` không được khóa như một giao dịch dài suốt phần việc thì giá trị vẫn có thể bị worker khác đổi.

## 3. Step scope cách ly điều gì?

`@StepScope` là scope của Spring Batch: **mỗi `StepExecution` có một instance thực của bean được đánh dấu step-scoped** khi được dùng trong scope đó. Spring thường tiêm một **scoped proxy** vào cấu hình step; proxy tìm target ứng với `StepExecution` đang hoạt động.

~~~mermaid
flowchart TD
    D["Một định nghĩa worker Step"] --> PA["Proxy bean @StepScope"]
    PA --> A["StepExecution A<br/>target reader/processor A"]
    PA --> B["StepExecution B<br/>target reader/processor B"]
    A --> CA["ExecutionContext A"]
    B --> CB["ExecutionContext B"]
    CA --> IA["Input/State riêng của A"]
    CB --> IB["Input/State riêng của B"]
~~~

Với local partitioning, A và B có thể chạy trong **cùng JVM nhưng trên các thread khác nhau**; target step-scoped thường vẫn riêng vì chúng là **hai `StepExecution`**. Trong remote partitioning, mỗi JVM có container Spring của nó, nhưng vẫn cần scope đúng bên trong worker, nhất là khi một JVM xử lý nhiều partition.

**Step scope không phải thread scope.** Nếu một worker `StepExecution` tự chạy **nhiều chunk đồng thời** bằng multi-threaded step, các thread chunk đó vẫn thuộc **cùng worker execution**, có thể cùng dùng một target `@StepScope`. Reader stateful **không tự trở thành thread-safe** chỉ vì có `@StepScope`.

| Scope/lifetime | Chia sẻ ở đâu? | Dùng cho trường hợp nào? |
| --- | --- | --- |
| Singleton | Một instance trong mỗi Spring application context | Dịch vụ stateless, dependency đã được thiết kế thread-safe |
| `@JobScope` | Instance theo `JobExecution` trong phạm vi scope hoạt động | State cấp job; **không** cách ly từng partition/worker |
| `@StepScope` | Instance theo `StepExecution` | Reader, processor, writer hoặc state/config riêng từng worker |
| `ThreadLocal` | Theo thread, không theo `StepExecution` | Hỗ trợ context thread có lifecycle quản lý chặt; dễ rò khi thread được tái sử dụng |
| Key nghiệp vụ tại DB | Theo constraint/transaction của hệ thống đích | Chống side effect trùng/ghi cạnh tranh giữa nhiều JVM |

Tài liệu Spring Batch lưu ý **job-scoped bean không được khuyến nghị** trong các step đa luồng hoặc partitioned step vì framework không kiểm soát đầy đủ mọi thread do người dùng tạo. Đừng thay `@StepScope` bằng `@JobScope` để chia sẻ cursor hoặc tenant ID của từng partition.

## 4. Cấu hình đúng: bind ExecutionContext vào bean step-scoped

Giả sử mỗi worker có:

~~~text
ordersWorkerStep:tenant-A
  tenantId       = "A"
  minIdInclusive = 1
  maxIdExclusive = 1001

ordersWorkerStep:tenant-B
  tenantId       = "B"
  minIdInclusive = 1001
  maxIdExclusive = 2001
~~~

### 4.1. Partitioner cấp context riêng

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.context.annotation.Bean;

@Bean
Partitioner tenantPartitioner() {
    return gridSize -> {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        ExecutionContext tenantA = new ExecutionContext();
        tenantA.putString("tenantId", "A");
        tenantA.putLong("minIdInclusive", 1L);
        tenantA.putLong("maxIdExclusive", 1001L);

        ExecutionContext tenantB = new ExecutionContext();
        tenantB.putString("tenantId", "B");
        tenantB.putLong("minIdInclusive", 1001L);
        tenantB.putLong("maxIdExclusive", 2001L);

        partitions.put("tenant-A", tenantA);
        partitions.put("tenant-B", tenantB);
        return partitions;
    };
}
~~~

Đây là ví dụ cố định hai partition để minh họa. Trong production, key và phạm vi phải **duy nhất, không giao nhau, bao phủ input và ổn định theo kế hoạch của `JobInstance`**. `gridSize` là gợi ý về số phần việc, không bắt buộc partitioner luôn trả đúng giá trị đó.

### 4.2. Reader đúng tenant và range

~~~java
import java.math.BigDecimal;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record OrderRow(long id, String tenantId, BigDecimal amount) {}
record OutputRow(long id, String tenantId, BigDecimal amount) {}

@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['tenantId']}") String tenantId,
        @Value("#{stepExecutionContext['minIdInclusive']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("ordersReader")
            .dataSource(dataSource)
            .selectClause("SELECT id, tenant_id, amount")
            .fromClause("FROM orders")
            .whereClause(
                "WHERE tenant_id = :tenantId "
                + "AND id >= :minId AND id < :maxId")
            .parameterValues(Map.of(
                "tenantId", tenantId,
                "minId", minId,
                "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderRow(
                rs.getLong("id"),
                rs.getString("tenant_id"),
                rs.getBigDecimal("amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

**Vì sao cách này tránh cross-talk:**

1. `@StepScope` làm cho Spring tạo target reader theo **worker `StepExecution`**.
2. `@Value("#{stepExecutionContext['...']}")` được giải quyết **lúc step scope hoạt động**, thay vì khi ứng dụng khởi tạo toàn bộ singleton.
3. Reader dùng các giá trị đã bind để query đúng tenant và khoảng ID, không dựa vào biến `currentTenant` có thể bị worker khác sửa.
4. Mỗi worker có `ExecutionContext`/checkpoint riêng. Tên reader `ordersReader` giống nhau vẫn có thể phù hợp vì state của các `StepExecution` được tách biệt.

Reader phân trang cần **sort key duy nhất và ổn định** trong phạm vi query; ví dụ giả định `orders.id` là khóa duy nhất. Nếu ID chỉ duy nhất theo tenant, vì query cố định `tenant_id` thì `id` phải duy nhất trong tập đã lọc; nếu query không cố định tenant cần khóa sắp xếp phù hợp hơn.

**Chú ý về khai báo bean:** Với reader là `ItemStream`, nên để method `@Bean @StepScope` trả về kiểu cụ thể như `JdbcPagingItemReader<OrderRow>` (hoặc ít nhất kiểu có giao diện `ItemStream`) để Spring Batch có thể thấy đúng các callback `open/update/close` qua scoped proxy. Trả về interface quá hẹp như `ItemReader` có thể làm mất khả năng đăng ký lifecycle cần thiết.

### 4.3. Processor stateless theo worker

~~~java
import org.springframework.batch.item.ItemProcessor;

@Bean
@StepScope
ItemProcessor<OrderRow, OutputRow> tenantProcessor(
        @Value("#{stepExecutionContext['tenantId']}") String tenantId) {

    // tenantId là biến local không đổi trong target của worker này.
    return item -> {
        if (!tenantId.equals(item.tenantId())) {
            throw new IllegalStateException(
                    "Sai tenant: expected=" + tenantId
                    + ", actual=" + item.tenantId());
        }
        return new OutputRow(item.id(), tenantId, item.amount());
    };
}
~~~

Processor không cần field `currentTenant` có thể bị ghi đè trong singleton. Tác dụng phụ của processor cũng được giảm thiểu; đối chiếu tenant tại đây cung cấp **phòng vệ bổ sung**, nhưng không thay thế việc lọc đúng nguồn.

Trong trường hợp processor hoàn toàn stateless và tất cả thông tin cần thiết đã nằm trên item, **singleton thread-safe cũng có thể là lựa chọn đúng**. Không áp đặt `@StepScope` cho mọi bean chỉ vì step chạy song song.

### 4.4. Worker step và manager step

~~~java
@Bean
Step ordersWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcPagingItemReader<OrderRow> ordersReader,
        ItemProcessor<OrderRow, OutputRow> tenantProcessor,
        ItemWriter<OutputRow> ordersWriter) {

    return new StepBuilder("ordersWorkerStep", jobRepository)
            .<OrderRow, OutputRow>chunk(200, transactionManager)
            .reader(ordersReader)
            .processor(tenantProcessor)
            .writer(ordersWriter)
            .build();
}

@Bean
Step ordersManagerStep(
        JobRepository jobRepository,
        @Qualifier("ordersWorkerStep") Step workerStep,
        @Qualifier("tenantPartitioner") Partitioner partitioner,
        TaskExecutor partitionExecutor) {

    return new StepBuilder("ordersManagerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(2)
            .taskExecutor(partitionExecutor)
            .build();
}
~~~

Đoạn code mang tính ghép nối cấu hình: `ordersWriter` và `partitionExecutor` là bean do ứng dụng cung cấp; các kiểu `Step`, `StepBuilder`, `JobRepository`, `PlatformTransactionManager`, `ItemWriter`, `TaskExecutor`, `Qualifier` import từ Spring tương ứng. Nếu writer có state thay đổi theo tenant/partition, writer cũng phải thiết kế per-step state hoặc khai báo `@StepScope` phù hợp. Một singleton writer **stateless, thread-safe** có thể được chia sẻ an toàn.

## 5. Những nguyên nhân khác của cross-talk dù đã có @StepScope

`@StepScope` không cô lập mọi dữ liệu mà bean tham chiếu. Hãy xem các trường hợp sau.

| Nguyên nhân | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Mutable `static` state | `static String tenantId` | Loại bỏ state static theo worker; lưu trong target/context riêng |
| Singleton helper có field mutable | `sharedHelper.setTenant(...)` | Truyền tenant qua tham số; dùng helper stateless hoặc per-step instance |
| Shared cache không phân biệt tenant | Cache key chỉ là `orderId` | Cache key phải bao gồm namespace/tenant hoặc tách cache đúng phạm vi |
| Shared mutable collection | `ArrayList<OutputRow>` dùng chung các worker | Tránh gom output vào list chung; nếu cần dùng cơ chế đồng bộ **và** phân vùng dữ liệu rõ |
| `ThreadLocal` không được dọn | Thread tái sử dụng còn `tenant=A` | `remove()` trong `finally`; ưu tiên truyền context tường minh |
| `@JobScope` cho reader theo tenant | Một instance cấp job phục vụ nhiều worker | Đổi sang `@StepScope` cho bean có state của partition |
| Async task tự tạo thread | `CompletableFuture` gọi scoped proxy ở thread khác | Không giả định step context tự được truyền; truyền dữ liệu bất biến và quản lý execution context theo API phù hợp |
| Writer dùng một tài nguyên đích toàn cục | Ghi vào cùng file tạm/FTP path | Đặt đích theo partition hoặc đồng bộ/merge theo thiết kế |

### ThreadLocal không phải chìa khóa thay thế StepScope

Spring Batch liên kết step scope với `StepExecution` đang hoạt động qua cơ chế quản lý context của framework, sử dụng thông tin gắn với thread thực thi. **Điều này không có nghĩa** ứng dụng được phép tự đặt một `ThreadLocal<String> currentTenant` rồi coi nó là lifetime của partition:

~~~java
private static final ThreadLocal<String> CURRENT_TENANT =
        new ThreadLocal<>();

void processWithTenant(String tenantId, Runnable task) {
    CURRENT_TENANT.set(tenantId);
    try {
        task.run();
    } finally {
        CURRENT_TENANT.remove(); // Nếu dùng ThreadLocal, luôn cleanup.
    }
}
~~~

Ví dụ chỉ nhấn mạnh **quy tắc cleanup**, không đề xuất thay `@StepScope` bằng tự quản lý `ThreadLocal`. Khi task bất đồng bộ chạy ở thread khác, giá trị này không được lan truyền đáng tin cậy nếu không có cơ chế rõ ràng. Ưu tiên tham số bất biến hoặc context được bind đúng vòng đời worker.

### Cảnh báo cho multi-threaded chunk bên trong worker

Giả sử một partition có một `StepExecution` nhưng bản thân worker step sử dụng thêm `TaskExecutor` để chạy nhiều chunk đồng thời. Khi đó:

- `@StepScope` tạo **một target reader cho StepExecution đó**, không phải một reader cho mỗi thread.
- `JdbcPagingItemReader` hoặc các reader stateful khác có thể không an toàn khi nhiều thread cùng sửa cursor/index/checkpoint.
- Chunk có thể hoàn tất không theo thứ tự; restart và việc theo dõi vị trí đọc cần đánh giá riêng.

Vì vậy, **local partitioning nhiều worker step** và **multi-threaded step nhiều thread trong một worker** có mô hình chia state khác nhau. Cần xem xét thiết kế reader/thread safety cụ thể, thay vì tăng concurrency ở cả hai tầng cùng lúc.

## 6. Step scope, restart và checkpoint

Mỗi worker `StepExecution` có `ExecutionContext` chứa thông tin phạm vi và state cần để tiếp tục khi restart, ví dụ:

~~~text
ordersWorkerStep:tenant-A
  input context:
    tenantId = A
    minIdInclusive = 1
    maxIdExclusive = 1001
  reader checkpoint:
    vị trí đọc đã commit (key/format tùy reader)
~~~

Nếu worker A lỗi sau một số chunk đã commit:

1. `JobRepository` lưu lịch sử `StepExecution` và checkpoint theo cơ chế transaction/`ItemStream`.
2. `StepExecutionSplitter` xác định worker executions cần chạy lại theo trạng thái và chính sách restart; những partition `COMPLETED` thường được bỏ qua.
3. Worker mới tạo bean `@StepScope` trong **StepExecution mới**, với partition identity/input đúng như kế hoạch ban đầu, đồng thời nhận state checkpoint phù hợp.
4. Reader/writer tiếp tục hoặc replay theo hỗ trợ restart của chúng và tính nhất quán dữ liệu nguồn/đích.

**Sai lầm nguy hiểm:** Sau khi worker A fail, bạn thay cấu hình để `tenant-A` có range mới, nhưng vẫn tái sử dụng partition key. Checkpoint cũ có thể chỉ tới vị trí **không còn thuộc phạm vi hiện tại**. `@StepScope` tách state nhưng không đảm bảo kế hoạch partition ổn định; cần cố định key → input theo `JobInstance`.

### Không biến ExecutionContext thành shared cache

`ExecutionContext` là metadata để truyền tham số và lưu checkpoint của một step. Đừng dùng một `Map` mutable toàn cục làm bản thay thế rồi cho worker cùng đọc/ghi. Khi gọi `stepExecutionContext`, dữ liệu được resolve theo worker, nhưng nếu bạn đặt **cùng một tham chiếu đối tượng mutable tự tạo** vào nhiều nơi thì việc quản lý scope không tự thực hiện deep copy mọi cấu trúc tùy ý.

Nên lưu giá trị nhỏ, có thể serialize, cần thiết cho restart; không lưu `DataSource`, socket, cursor, đối tượng sống hoặc hàng triệu bản ghi trong context.

## 7. Local partitioning và remote partitioning

### Local: cùng JVM, nguy cơ chia sẻ object trực tiếp

`TaskExecutorPartitionHandler` thực thi nhiều worker trên executor trong cùng JVM. Các singleton/static mutable state có thể trực tiếp gây cross-talk. Cấu hình `@StepScope` cho reader/processor có state per-worker và dùng immutable configuration giúp cách ly.

### Remote: khác JVM nhưng vẫn có thể cross-talk qua tài nguyên chung

Với `MessageChannelPartitionHandler` và remote worker, mỗi JVM thường có heap riêng; hai JVM không cùng giữ một Java field singleton. Nhưng một worker JVM có thể chạy **nhiều partition đồng thời**, nên vẫn cần scope đúng. Ngoài ra, hai worker vẫn chia sẻ tài nguyên bên ngoài:

- Database table/sequence/cache phân tán;
- Queue/topic và routing key;
- S3/object storage prefix, đường dẫn file hoặc bucket;
- API bên ngoài và idempotency key;
- `JobRepository` lưu trạng thái mọi worker.

Ví dụ nếu hai worker khác JVM cùng ghi vào `output.csv` trong một bucket, việc chúng có `@StepScope` riêng **không** ngăn ghi đè file. Cần đặt tên output theo partition/JobInstance hoặc dùng cơ chế merge atomic, transaction/unique constraint phù hợp.

~~~mermaid
flowchart TB
    M["Manager partition step"] --> H["PartitionHandler"]
    H --> A["Worker A JVM<br/>@StepScope target A"]
    H --> B["Worker B JVM<br/>@StepScope target B"]
    A --> R[("JobRepository dùng chung")]
    B --> R
    A --> D[("Business DB / shared API")]
    B --> D
    D --> Q["Ràng buộc idempotency,<br/>transaction và namespace"]
~~~

**Kết luận:** Step scope giải quyết phạm vi **bean trong Spring application context**. Tính đúng đắn giữa các máy cần được đảm bảo ở **hệ thống đích** và giao thức điều phối nữa.

## 8. Làm sao chứng minh không có cross-talk?

### 8.1. Test cố tình cho hai partition đan xen

Với một processor singleton lỗi như phần 2, một test chạy tuần tự có thể vẫn xanh. Nên buộc hai worker chạy **cùng lúc** và kiểm tra tenant của mọi output.

Ví dụ đoạn mã mô phỏng race trong lớp lỗi, sử dụng `CountDownLatch` để hai task ghi đè biến trước khi xử lý:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

class BadSharedState {
    volatile String currentTenant;

    String processFor(String tenant, CountDownLatch bothReady)
            throws InterruptedException {
        currentTenant = tenant;
        bothReady.countDown();
        bothReady.await(); // Cả hai đã thiết lập biến dùng chung.
        return currentTenant; // Có thể trả sai tenant cho một task.
    }
}

void demoRace() throws Exception {
    BadSharedState shared = new BadSharedState();
    CountDownLatch ready = new CountDownLatch(2);
    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
        Future<String> a = pool.submit(
                () -> shared.processFor("A", ready));
        Future<String> b = pool.submit(
                () -> shared.processFor("B", ready));
        String resultA = a.get();
        String resultB = b.get();

        // Ít nhất một kết quả sẽ khác tenant mà task kỳ vọng.
        if (!"A".equals(resultA) || !"B".equals(resultB)) {
            System.out.println("Phát hiện cross-talk");
        }
    } finally {
        pool.shutdownNow();
    }
}
~~~

Đây là **mô phỏng race của một field chung**, không phải integration test Spring Batch. `volatile` không giải quyết được vấn đề. Với test thật, cho hai worker có context khác nhau chạy đồng thời, kiểm tra:

- Từng `StepExecution` đọc đúng **tenant/range** và có `ExecutionContext` độc lập.
- Không có output của A mang tenant B, không có record trùng business key hoặc thiếu dữ liệu.
- Các reader/processor/writer có instance đúng theo scope mong muốn.
- Bài test lặp nhiều lần, thay đổi thứ tự scheduling, chunk size, số worker và mức tải.
- Có thể dừng/restart một worker giữa chunk rồi đối soát dữ liệu sau khi hoàn tất.

### 8.2. Kiểm chứng instance theo StepExecution

Trong listener hoặc log có kiểm soát, có thể ghi:

~~~java
@Override
public void beforeStep(StepExecution stepExecution) {
    log.info("stepExecutionId={} step={} tenant={}",
            stepExecution.getId(),
            stepExecution.getStepName(),
            stepExecution.getExecutionContext()
                         .getString("tenantId", "N/A"));
}
~~~

Lưu ý method `ExecutionContext.getString(key, defaultValue)` lấy giá trị mặc định khi key không tồn tại; mục đích ví dụ là **ghi nhận identity**, không dùng log để quyết định phạm vi query. Trên production, chỉ log các identifier đã được đánh giá an toàn, tránh lộ tenant hoặc dữ liệu nhạy cảm nếu chính sách không cho phép.

**Không dùng mỗi `Thread.currentThread().getName()` để xác định partition.** Thread pool có thể tái sử dụng thread cho nhiều worker. Dùng `JobExecutionId`, `StepExecutionId`, partition key và source version có kiểm soát.

## 9. Quan sát cross-talk trong vận hành

Cross-talk có thể không tạo exception: worker vẫn `COMPLETED` nhưng ghi sai tenant. Vì vậy phải kết hợp **metric framework** và **đối soát nghiệp vụ**.

| Quan sát | Khả năng | Cách kiểm chứng |
| --- | --- | --- |
| Worker A tạo output mang tenant B | Singleton/static mutable state hoặc shared cache | Log identity, kiểm tra code và nguồn/đích theo tenant |
| Cùng business ID xuất hiện ở hai partition | Overlap, reader sai predicate hoặc reuse cursor | Đối soát partition key + input range + business key |
| `readCount` hợp lý nhưng hàng đích thiếu | Dedupe/no-op, filter/skip hoặc ghi nhầm đích | SQL đối soát và metric insert/update/no-op |
| Lỗi chỉ xuất hiện khi tăng thread | Race condition trong processor/listener/reader | Test stress, thay scheduling, kiểm tra bean scope |
| Một worker đọc sai vị trí sau restart | Checkpoint/context sai hoặc partition plan thay đổi | So sánh JobInstance, key, range, read state |
| Log hiển thị tenant của task trước | `ThreadLocal`/MDC không cleanup | Kiểm tra cleanup và context propagation |
| Remote worker ghi đè cùng file | Shared resource name không được namespace | Output path, manifest, khóa/merge strategy |

Các metric cần thu gồm `readCount`, `writeCount`, `filterCount`, skip/rollback count, duration theo partition, cùng số bản ghi **sai tenant**, duplicate/no-op và tỷ lệ business key khớp nguồn. Không lấy tổng `writeCount` làm bằng chứng toàn bộ dữ liệu đã được ghi đúng partition.

Với Prometheus/Grafana, cân nhắc cardinality của nhãn. Partition/`StepExecutionId` là những thông tin tốt cho **log/tracing và truy vấn JobRepository**, nhưng có thể gây nhiều time series nếu gắn vào mọi metric dài hạn.

### Thread safety và idempotency có phải một?

**Không.** Một bean thread-safe tránh race trên state trong JVM, nhưng hai worker vẫn có thể gửi cùng request nghiệp vụ khi dữ liệu đầu vào overlap hoặc broker phát lại message. Một writer idempotent tránh tác dụng phụ trùng, nhưng không sửa tình trạng A gắn nhầm tenant B. Cần cả **isolation**, **predicate phân vùng đúng**, **transaction/locking** và **idempotency** phù hợp.

## 10. Những sai lầm cần tránh

1. **Đánh dấu `@StepScope` nhưng đọc cấu hình từ biến `static`.** Target riêng vẫn tham chiếu state dùng chung; hãy late-bind từ `stepExecutionContext` hoặc truyền tham số bất biến.
2. **Dùng `@JobScope` cho reader của từng partition.** Bean cấp job không bảo đảm một target riêng cho mỗi worker và còn khó tương thích với nhiều thread; ưu tiên step scope.
3. **Cho rằng một worker = một thread vĩnh viễn.** Handler/executor có thể dùng lại thread; identity phải dựa vào StepExecution.
4. **Thêm `synchronized` vào mọi reader để chữa lỗi.** Cách đó có thể triệt tiêu parallelism nhưng không sửa partition boundary hay scope lẫn lộn.
5. **Dùng step scope để thay thế transaction hoặc unique constraint.** Dedupe cần thực hiện tại đích nếu có retry/replay hoặc nhiều JVM.
6. **Thay đổi partition key/range khi restart.** Checkpoint sẽ không còn tương ứng với input logic cũ; chốt partition plan theo JobInstance.
7. **Giữ `ThreadLocal` hoặc MDC sau khi task kết thúc.** Thread pool có thể tái sử dụng thread cho partition khác; cần cleanup trong `finally`.
8. **Mở thêm đa luồng bên trong mỗi worker mà không kiểm tra stateful reader.** Step scope không tự nhân bản reader theo thread chunk.

## 11. Checklist kiểm thử trước production

| Tình huống | Điều phải kiểm chứng |
| --- | --- |
| Chạy 2 partition khác tenant cùng lúc | Mỗi output có tenant đúng, không có cross-talk |
| Chạy 8 partition trên pool 4 thread | Reuse thread không làm leak tenant/context giữa các worker |
| Reader stateful có `@StepScope` | Instance theo StepExecution, checkpoint riêng |
| Processor singleton stateless | Không có mutable field theo partition, an toàn khi gọi đồng thời |
| Processor singleton mutable dùng chung | Test phát hiện race; chuyển thiết kế sang per-step/immutable |
| Một worker tự chạy multi-threaded chunk | Reader/writer được đánh giá thread safety trong chính worker |
| Restart sau một số chunk commit | Context và partition plan không đổi, không bỏ sót/duplicate |
| Remote workers trên nhiều JVM | Shared DB/file/cache/queue có namespace và idempotency |
| Output dùng business key duy nhất | Writer chặn trùng và báo conflict đúng nghiệp vụ |
| Metrics bằng nhau nhưng dữ liệu sai tenant | Đối soát business key/tenant phát hiện lỗi mà counters bỏ sót |

### Bài tập tình huống

Một job xử lý 10 triệu giao dịch bằng 8 partition. Processor được khai báo `@Component` mặc định singleton và có field `private String activeTenant`. Listener `beforeStep` của mỗi worker sửa field này bằng `tenantId` của partition. Job chạy tuần tự ổn, nhưng chạy 8 thread thì nhiều giao dịch tenant A được ghi vào tenant B. Nhóm vận hành đề xuất tăng DB connection pool hoặc đổi từ local sang remote partitioning.

**Câu hỏi:**

1. Vì sao tăng connection pool không giải quyết lỗi?
2. `@StepScope` giúp ở đâu và có giới hạn gì?
3. Nếu processor được sửa đúng nhưng writer dùng một tên file output chung cho mọi worker, cross-talk đã hết chưa?
4. Cần những phép kiểm tra nào để khẳng định an toàn sau sửa lỗi?

**Định hướng trả lời:** Lỗi gốc là **mutable singleton state của mỗi partition**, không phải thiếu connection. Có thể chuyển processor thành step-scoped với `tenantId` late-bind hoặc làm processor stateless nhận tenant trực tiếp từ item. Step scope tạo target theo `StepExecution`, không đảm bảo an toàn khi nhiều chunk thread của **cùng một step** cùng dùng target. Writer file chung vẫn có thể gây ghi đè; cần output tách theo partition hoặc hợp nhất có kiểm soát. Kiểm thử song song và restart phải đối soát business key, tenant, hàng bị trùng và số kết quả hợp lệ, không chỉ dựa vào `COMPLETED` hay `writeCount`.

## Tài liệu tham khảo

- [Spring Batch Reference — Step Scope](https://docs.spring.io/spring-batch/reference/step/step-scoped.html): bean step-scoped và context theo `StepExecution`.
- [Spring Batch Reference — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope`, `stepExecutionContext` và `@Value`.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, partitioning và remote patterns.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint và yêu cầu restart.
- [Spring Batch API — ExecutionContext](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/item/ExecutionContext.html): state theo execution.

> **Ghi nhớ:** `@StepScope` giúp mỗi **worker StepExecution** có target bean và state riêng; đó là cách phòng cross-talk khi nhiều partition chạy đồng thời. Nó **không** tự biến stateful bean thành thread-safe trong cùng một worker, cũng không thay thế chia dữ liệu không giao nhau, kiểm soát shared resource, transaction và idempotency giữa các hệ thống.
