# Partition key duy nhất trong Spring Batch

> **Chương:** Partitioner
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán phù hợp. Bài này tập trung vào cách đặt **partition key duy nhất và ổn định**, chia dữ liệu không giao thoa, hỗ trợ retry/restart và giám sát các worker khi chạy job ở quy mô lớn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích partition key trong kết quả của `Partitioner.partition(int gridSize)` là gì, nó khác khóa bản ghi và `StepExecutionId` ở đâu.
2. Xác định các bất biến cần giữ: **tên duy nhất**, **phạm vi dữ liệu không giao nhau**, **bao phủ đủ input**, và **ánh xạ ổn định qua restart**.
3. Tạo `Partitioner` chia khoảng ID bằng Java/Spring Batch, lưu ranh giới trong `ExecutionContext` và đọc theo ranh giới đó bằng reader `@StepScope`.
4. Nhận biết lỗi khi dùng tên sinh ngẫu nhiên, tên bị trùng, thay đổi số partition hoặc dữ liệu nguồn giữa các lần chạy.
5. Kiểm tra, theo dõi và vận hành partitioning đúng khi có nhiều thread, nhiều JVM, retry và restart.

## 1. Partition key là gì?

Trong mô hình **partitioning** của Spring Batch, một **manager step** phân chia công việc thành các đơn vị nhỏ. `Partitioner` được gọi qua phương thức:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Mỗi phần tử trong `Map` là **một partition**:

- **Key (`String`):** Tên/định danh logic của partition, ví dụ `range-0000`, `range-0001`, `file-0003`. Manager dùng tên này để phân biệt các worker step execution, từ đó nhận diện công việc khi điều phối và restart.
- **Value (`ExecutionContext`):** Dữ liệu cấu hình cần để worker xử lý đúng phạm vi, chẳng hạn `minIdInclusive`, `maxIdExclusive`, file input, shard ID hoặc tenant ID. Mỗi partition có context riêng.
- **`gridSize`:** Gợi ý số partition mà manager muốn tạo/điều phối; đây **không phải** tên partition và cũng không mặc nhiên là số thread chạy đồng thời.

~~~mermaid
flowchart TB
    P["Manager step<br/>Partitioner.partition(gridSize)"]
    P --> A["range-0000<br/>ExecutionContext: ID [1, 25001)"]
    P --> B["range-0001<br/>ExecutionContext: ID [25001, 50001)"]
    P --> C["range-0002<br/>ExecutionContext: ID [50001, 75001)"]
    P --> D["range-0003<br/>ExecutionContext: ID [75001, 100001)"]
    A --> W1["Worker StepExecution A"]
    B --> W2["Worker StepExecution B"]
    C --> W3["Worker StepExecution C"]
    D --> W4["Worker StepExecution D"]
~~~

Trong Spring Batch, tên `StepExecution` của worker partition thường được ghép từ tên worker step và partition key, chẳng hạn `orderWorkerStep:range-0000`. Vì vậy, tên partition cần **phân biệt được trong cùng tập partition của manager** và **không thay đổi tùy tiện giữa những lần khôi phục cùng JobInstance**.

**Phân biệt các loại khóa:**

| Khái niệm | Ví dụ | Phạm vi và mục đích |
| --- | --- | --- |
| Partition key (`Map` key) | `range-0002` | Định danh **một phần việc** do `Partitioner` tạo ra |
| Khóa dữ liệu nghiệp vụ | `order_id = 58213` | Định danh **một bản ghi/sự kiện**, dùng để đối soát hoặc chống ghi trùng |
| Khóa chia dữ liệu | Khoảng `id >= 50001 AND id < 75001` | Xác định **bản ghi thuộc partition nào** |
| `StepExecutionId` | ID metadata do repository cấp | Định danh **một lần thực thi step cụ thể**, có thể khác sau restart |
| `JobInstance` và `JobExecution` | Job cùng bộ identifying parameters và lần thực thi của job | Phân biệt **bài toán cần xử lý** với **lần chạy/thử chạy** |

Tên partition **không cần duy nhất trên toàn hệ thống mãi mãi**: nhiều `JobInstance` có thể đều có partition `range-0000`. Điều quan trọng là nó không bị trùng trong tập của **một manager step cần điều phối**, và ý nghĩa của tên được giữ nguyên khi restart cùng tập công việc.

## 2. Bốn bất biến của partitioning đúng

Một `Partitioner` tốt cần đảm bảo đồng thời các yêu cầu sau.

### 2.1. Tên partition phải duy nhất

Vì `partition()` trả về `Map<String, ExecutionContext>`, hai lần `put()` với cùng key **không tạo ra hai partition**. Phần tử sau sẽ **ghi đè** phần tử trước mà không có cảnh báo mặc định:

~~~java
Map<String, ExecutionContext> partitions = new HashMap<>();
partitions.put("range-0000", firstContext);
partitions.put("range-0000", secondContext);

System.out.println(partitions.size()); // 1, không phải 2
~~~

Nếu `firstContext` mô tả ID 1–100 còn `secondContext` mô tả ID 101–200, partition đầu có thể **biến mất âm thầm** và 100 bản ghi đầu bị bỏ sót. Với logic sinh key phức tạp, nên dùng `putIfAbsent` để phát hiện xung đột:

~~~java
if (partitions.putIfAbsent(partitionName, context) != null) {
    throw new IllegalStateException(
        "Trùng partition key: " + partitionName);
}
~~~

### 2.2. Phạm vi dữ liệu phải không giao nhau

Hai partition có tên khác nhau **vẫn có thể đọc trùng item** nếu predicate lọc dữ liệu chồng lấn. Ví dụ:

~~~text
range-0000: id BETWEEN 1 AND 100
range-0001: id BETWEEN 100 AND 200
                             ^ id=100 xuất hiện hai lần
~~~

Với khoảng số, quy ước **nửa mở** `[minInclusive, maxExclusive)` giúp tránh lỗi biên:

~~~sql
SELECT id, order_code
FROM orders
WHERE id >= :minIdInclusive
  AND id < :maxIdExclusive
ORDER BY id;
~~~

Hai khoảng liền nhau `[1, 101)` và `[101, 201)` không có ID nào chung. Nếu input có nhiều tenant dùng chung ID cục bộ, predicate còn phải bao gồm `tenant_id` hoặc khóa chia vùng phù hợp.

### 2.3. Các partition phải bao phủ đủ tập input

Không giao nhau là chưa đủ nếu còn **khoảng hở**:

~~~text
range-0000: [1, 101)
range-0001: [201, 301)
              ^ thiếu [101, 201)
~~~

Gọi `D` là tập item cần xử lý, `Pᵢ` là tập item thuộc partition thứ `i`. Mục tiêu là:

\[
\bigcup_i P_i = D
\quad\text{và}\quad
P_i \cap P_j = \varnothing\ (i \neq j)
\]

Với ID không liên tục (ví dụ một số dòng đã xóa), khoảng `[min, max)` vẫn có thể đúng: phạm vi được chia **theo không gian khóa**, không bắt buộc số lượng bản ghi ở mỗi partition bằng nhau. Kiểm tra tính bao phủ cần dựa trên **tập dữ liệu đầu vào thực tế**, không chỉ đếm số partition.

### 2.4. Tên và phạm vi phải ổn định qua restart

Ví dụ, lần chạy đầu:

| Tên partition | Dải ID |
| --- | --- |
| `range-0000` | `[1, 25001)` |
| `range-0001` | `[25001, 50001)` |

Nếu job lỗi, sau đó bạn thay số partition hoặc ranh giới mà vẫn gọi partition `range-0000` nhưng chuyển thành `[1, 40001)`, tên cũ đã đại diện **công việc khác**. Manager có thể cố sử dụng lịch sử worker execution với định danh không còn đúng; checkpoint và kết quả xử lý lại sẽ khó kiểm soát.

**Quy tắc:** Đối với cùng công việc cần restart, giữ ổn định *partition key → phạm vi dữ liệu*. Nếu phải chia lại toàn bộ dữ liệu, hãy xác định đó là **kế hoạch chạy mới** với `JobParameters`/JobInstance hoặc chiến lược khôi phục riêng, thay vì thay ánh xạ một cách âm thầm.

## 3. Mẫu đặt tên partition key

Định danh tốt cần **ngắn gọn, ổn định, dễ quan sát và không phụ thuộc thread hay thời điểm chạy**.

| Cách đặt | Ví dụ | Đánh giá |
| --- | --- | --- |
| Số thứ tự có độ rộng cố định | `range-0000`, `range-0001` | Tốt với dải dữ liệu cố định; dễ xem log, dashboard |
| Định danh file từ manifest bất biến | `file-0012` | Tốt khi ánh xạ đến một file cố định trong manifest của job |
| Shard ID đã cấu hình | `shard-ap-03` | Tốt nếu shard là đơn vị xử lý ổn định |
| Timestamp hiện tại | `partition-20261126-091530` | Kém nếu mỗi restart tạo tên mới |
| UUID ngẫu nhiên mỗi lần gọi | `b7d9...` | Kém nếu không lưu ánh xạ bền vững ngay từ lúc lập kế hoạch |
| Tên thread | `pool-2-thread-1` | Sai mục đích: thread có thể được tái sử dụng và thay đổi khi chạy |
| Mỗi partition đều tên `default` | `default` | Sai: các giá trị trong `Map` có thể ghi đè nhau |

Không nhất thiết đưa mọi chi tiết của dữ liệu vào key. Có thể dùng `range-0003` làm tên và đặt chính xác `minIdInclusive`/`maxIdExclusive` trong `ExecutionContext`. Nếu có metadata nhạy cảm (định danh khách hàng, đường dẫn nội bộ), nên giữ ở context hoặc hệ thống cấu hình phù hợp thay vì đưa toàn bộ vào tên xuất hiện trong log.

**Lưu ý:** Nếu một partition lấy dữ liệu theo file, đừng tự động dùng riêng `file.getName()` làm key: hai thư mục khác nhau có thể chứa file cùng tên. Cần một ID duy nhất của **manifest đầu vào** hoặc key được tạo từ vị trí file đã chuẩn hóa theo quy tắc ổn định.

## 4. Ví dụ Java: Partitioner chia dải ID với key duy nhất

Giả sử nguồn `orders` có ID từ 1 đến 100.000; cần xử lý bằng bốn worker partition. Ta dùng các khoảng nửa mở và ranh giới xác định trước, không lấy số thread hoặc thời gian hiện tại làm khóa.

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class OrderRangePartitioner implements Partitioner {

    private final long firstIdInclusive;
    private final long lastIdExclusive;
    private final int fixedPartitionCount;

    public OrderRangePartitioner(
            long firstIdInclusive,
            long lastIdExclusive,
            int fixedPartitionCount) {

        if (firstIdInclusive >= lastIdExclusive) {
            throw new IllegalArgumentException("Dải ID phải không rỗng");
        }
        if (fixedPartitionCount <= 0) {
            throw new IllegalArgumentException("Số partition phải > 0");
        }

        this.firstIdInclusive = firstIdInclusive;
        this.lastIdExclusive = lastIdExclusive;
        this.fixedPartitionCount = fixedPartitionCount;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        // Ví dụ: số partition và biên dữ liệu được cố định theo JobInstance.
        // gridSize là gợi ý từ manager; ở đây cố ý dùng fixedPartitionCount
        // để giữ ánh xạ partition key -> range ổn định khi restart.
        long total = lastIdExclusive - firstIdInclusive;
        long width = (total + fixedPartitionCount - 1L) / fixedPartitionCount;

        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        for (int index = 0; index < fixedPartitionCount; index++) {
            long min = firstIdInclusive + index * width;
            if (min >= lastIdExclusive) {
                break; // Tránh tạo partition rỗng khi ID ít hơn số vùng.
            }
            long max = Math.min(lastIdExclusive, min + width);

            String key = String.format(Locale.ROOT, "range-%04d", index);
            ExecutionContext context = new ExecutionContext();
            context.putLong("minIdInclusive", min);
            context.putLong("maxIdExclusive", max);

            if (result.putIfAbsent(key, context) != null) {
                throw new IllegalStateException("Trùng partition key: " + key);
            }
        }
        return result;
    }
}
~~~

Trong ví dụ `new OrderRangePartitioner(1L, 100_001L, 4)`, kết quả là:

| Key trả về | `minIdInclusive` | `maxIdExclusive` | ID được chọn |
| --- | ---: | ---: | --- |
| `range-0000` | 1 | 25.001 | 1–25.000 |
| `range-0001` | 25.001 | 50.001 | 25.001–50.000 |
| `range-0002` | 50.001 | 75.001 | 50.001–75.000 |
| `range-0003` | 75.001 | 100.001 | 75.001–100.000 |

Đây là **ví dụ để học**, với dải số hữu hạn và tương đối nhỏ. Ở production cần chống tràn số khi tính ranh giới lớn, và xác định `firstIdInclusive`, `lastIdExclusive`, `fixedPartitionCount` từ một kế hoạch/snapshot **được lưu bền vững theo JobInstance**. Nếu input rỗng, xử lý có chủ đích bằng skip/no-op hoặc một kế hoạch không tạo worker, tùy mô hình orchestration đang dùng.

### Gắn Partitioner vào manager step

Ví dụ cấu hình ý tưởng trên Spring Batch 5.x:

~~~java
@Bean
Partitioner orderRangePartitioner() {
    return new OrderRangePartitioner(1L, 100_001L, 4);
}

@Bean
ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(4);
    executor.setThreadNamePrefix("orders-partition-");
    executor.initialize();
    return executor;
}

@Bean
Step orderManagerStep(
        JobRepository jobRepository,
        Step orderWorkerStep,
        Partitioner orderRangePartitioner,
        ThreadPoolTaskExecutor partitionExecutor) {

    return new StepBuilder("orderManagerStep", jobRepository)
            .partitioner(orderWorkerStep.getName(), orderRangePartitioner)
            .step(orderWorkerStep)
            .gridSize(4)
            .taskExecutor(partitionExecutor)
            .build();
}
~~~

Các kiểu `Step`, `JobRepository`, `StepBuilder` và `ThreadPoolTaskExecutor` được import từ Spring Batch/Spring Framework theo phiên bản dự án. `orderWorkerStep` là chunk step được cấu hình riêng với reader/processor/writer phù hợp. Trong ví dụ, `gridSize(4)` chỉ phản ánh mức chia công việc mong muốn; số thread chạy đồng thời còn phụ thuộc `TaskExecutor` và tài nguyên runtime.

### Reader của mỗi worker phải dùng đúng ranh giới

Nếu có bốn context khác nhau nhưng reader vẫn dùng `SELECT * FROM orders` không lọc, cả bốn partition sẽ đọc **toàn bộ bảng**. Reader phải sử dụng dữ liệu đã gán từ manager:

~~~java
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

record OrderRow(long id, String orderCode) {}

@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersByPartition(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minIdInclusive']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("ordersByPartition")
            .dataSource(dataSource)
            .selectClause("SELECT id, order_code")
            .fromClause("FROM orders")
            .whereClause("WHERE id >= :minId AND id < :maxId")
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) ->
                    new OrderRow(rs.getLong("id"), rs.getString("order_code")))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

Mỗi **worker `StepExecution`** nhận `ExecutionContext` của partition tương ứng và tạo reader riêng nhờ `@StepScope`. Tên `ordersByPartition` dùng cho checkpoint của reader vẫn có thể giống nhau giữa các partition vì mỗi `StepExecution` có `ExecutionContext` riêng. Khi dùng paging, `ORDER BY id` phải dựa trên **khóa sắp xếp duy nhất và ổn định** để phân trang/restart có ý nghĩa; `id` trong ví dụ được giả định là khóa duy nhất của bảng.

Mã trên không bao gồm `ItemProcessor` và `ItemWriter` của worker; chúng vẫn phải xử lý an toàn với giao dịch, tải DB và yêu cầu idempotency của hệ thống.

## 5. Unique partition key khác unique business key

Hai khái niệm thường bị đánh đồng:

- **Unique partition key:** Không có hai partition cùng tên trong `Map` manager tạo ra.
- **Unique business key:** Mỗi bản ghi/sự kiện có một ID nghiệp vụ để phân biệt và chống tác dụng phụ trùng ở đích.

Ví dụ `range-0001` và `range-0002` là hai tên duy nhất nhưng cả hai đều truy vấn `WHERE region = 'HCM'`. Chúng vẫn đọc cùng item. Ngược lại, có thể các range không giao nhau nhưng writer nhận lại một event nguồn đã được job trước ghi; phân chia partition đúng không tự chặn ghi lặp ở đích.

| Tầng | Phương pháp kiểm soát | Nếu thiếu |
| --- | --- | --- |
| Điều phối | Partition key duy nhất, ổn định | Key trùng ghi đè partition hoặc tên đổi khi restart |
| Chia nguồn | Predicate/tệp/shard không chồng lấn và bao phủ | Cùng item bị đọc nhiều lần hoặc bị bỏ qua |
| Checkpoint | `ExecutionContext` riêng theo worker, partition identity ổn định | Restart khó xác định phần việc đã hoàn tất |
| Ghi dữ liệu | Unique constraint, idempotency key hoặc upsert có kiểm soát | Retry/replay có thể sinh bản ghi/tác dụng phụ trùng |
| Quan sát | Ghi log key + range + `StepExecutionId` + status | Không biết partition nào chậm/lỗi/mất dữ liệu |

Khi partition theo tenant, file hoặc thời gian, không chỉ kiểm tra số lượng partition. Phải đối soát **tổng tập bản ghi đích dự kiến** với nguồn theo business key, bao gồm các trường hợp lỗi và restart.

## 6. Khi dữ liệu nguồn thay đổi trong lúc chạy

Một partition có thể dùng đúng key và khoảng ID nhưng kết quả vẫn thiếu hoặc trùng do nguồn **thay đổi**.

Ví dụ: manager xác định `[1, 100001)` lúc 01:00, worker A bắt đầu đọc lúc 01:01, worker B bắt đầu lúc 01:10. Trong khoảng thời gian đó, hệ thống nguồn tạo thêm/đổi bản ghi có ID nằm trong một range hoặc thay đổi trạng thái khiến bản ghi ra/vào điều kiện query. Hai worker đang quan sát **hai thời điểm khác nhau**.

Các chiến lược phù hợp tùy dữ liệu:

1. **Snapshot/cutoff ổn định:** Chốt `maxIdExclusive`, watermark hoặc `snapshotId` cho một JobInstance, áp dụng điều kiện chọn bản ghi thống nhất cho mọi partition.
2. **Manifest bất biến:** Với input theo file, tạo danh sách file, đường dẫn/ID và phiên bản/checksum trước khi phân vùng; khi restart, đọc lại đúng manifest đó.
3. **Truy vấn nhất quán:** Nếu yêu cầu snapshot chính xác của database, dùng cơ chế snapshot/snapshot isolation/CDC phù hợp. Chỉ chốt `maxId` **không** ngăn bản ghi cũ bị update trong lúc chạy.
4. **Idempotent writer:** Khi restart hoặc re-run vẫn có thể gặp replay; dùng business key và chính sách ghi trùng rõ ràng tại hệ thống đích.

Không nên giả định `ORDER BY id` hoặc khóa partition duy nhất tự mang lại **exactly-once processing**. Đây chỉ là một phần của kiến trúc an toàn dữ liệu.

## 7. Restart, retry và PartitionNameProvider

Spring Batch lưu lịch sử thực thi của manager/worker trong `JobRepository`. Khi job lỗi, partition đã hoàn tất và partition chưa hoàn tất cần được nhận diện theo **identity của partition**, trong khi `StepExecutionId` mới có thể xuất hiện khi một worker thực thi lại.

Các nguyên tắc để restart:

- Không sinh UUID hay timestamp mới để làm tên partition sau mỗi lần gọi `partition()`.
- Không thay đổi `partitionCount`, cách gán range hoặc tập file cho cùng một `JobInstance` đã bắt đầu chạy nếu chưa có chiến lược migration/recovery.
- Giữ tên và phạm vi input của partition ổn định theo metadata/kế hoạch đã chốt; checkpoint của reader có hiệu lực trong phạm vi phần việc đó.
- Mỗi worker có context và transaction riêng; lỗi một worker không nhất thiết rollback những partition khác đã commit.
- Writer phải xử lý được replay/idempotency nếu có khả năng ghi bên ngoài transaction hoặc job phải chạy lại dữ liệu đã xử lý.

Với cấu hình nâng cao, Spring Batch có `PartitionNameProvider` để cung cấp **tập tên partition** ở một số đường đi restart mà không phải sinh lại toàn bộ `ExecutionContext`. Nếu implementation vừa cung cấp tên vừa làm `Partitioner`, danh sách tên phải **khớp chính xác** với khóa của các partition được tạo ban đầu. Đây là tối ưu hóa cho identity/restart, không phải cơ chế tự sửa lỗi overlap hoặc thay đổi dataset.

### Một kịch bản restart có thể gây lỗi

Giả sử lần đầu có bốn partition `range-0000` đến `range-0003` và `range-0000`/`range-0001` đã hoàn tất. Sau lỗi, người vận hành đổi cấu hình chia thành hai range nhưng tái sử dụng `range-0000`/`range-0001`. Có nguy cơ hệ thống coi phần việc mới tương ứng với lịch sử cũ dù phạm vi đã thay đổi, dẫn đến mất hoặc lặp dữ liệu.

**Cách xử lý:** Khôi phục với **kế hoạch phân vùng ban đầu** và giữ nguyên ID nguồn; nếu quyết định chia lại từ đầu, hãy tạo một lượt xử lý mới với quy tắc chống trùng tại đích, thay vì trộn kết quả của hai kế hoạch dưới cùng định danh partition.

## 8. Kiểm thử partition key và tính đúng của phân vùng

### 8.1. Kiểm tra nhanh logic partitioner

Với bốn partition giả định:

~~~java
OrderRangePartitioner partitioner =
        new OrderRangePartitioner(1L, 100_001L, 4);

Map<String, ExecutionContext> result = partitioner.partition(4);

if (result.size() != 4) {
    throw new AssertionError("Phải có đúng bốn partition");
}

// Có đủ bốn key dự kiến?
for (int i = 0; i < 4; i++) {
    String name = String.format(Locale.ROOT, "range-%04d", i);
    if (!result.containsKey(name)) {
        throw new AssertionError("Thiếu partition: " + name);
    }
}

// Kiểm tra theo thứ tự dự kiến: không trùng và không hở ranh giới.
long expectedMin = 1L;
for (ExecutionContext ctx : result.values()) {
    long min = ctx.getLong("minIdInclusive");
    long max = ctx.getLong("maxIdExclusive");
    if (min != expectedMin || max <= min) {
        throw new AssertionError("Range hở/trùng/không hợp lệ");
    }
    expectedMin = max;
}
if (expectedMin != 100_001L) {
    throw new AssertionError("Chưa bao phủ hết tập ID đầu vào");
}
~~~

Đoạn kiểm tra này dựa vào thứ tự chèn của `LinkedHashMap` trong implementation ví dụ; nếu dùng loại `Map` không bảo toàn thứ tự, cần sắp xếp partition theo `minIdInclusive` trước khi đối chiếu. Kiểm tra số lượng/key **không thay thế** kiểm thử SQL predicate và dữ liệu thực tế.

### 8.2. Các trường hợp cần thử

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Hai lần tạo partition với cùng kế hoạch | Cùng tập key, cùng ranh giới và cùng nguồn |
| `gridSize` thay đổi ngoài dự tính | Một restart không vô tình đổi ánh xạ key → input |
| ID đầu/cuối và khoảng biên | Mỗi item thuộc đúng một partition, không lặp ở biên |
| ID nguồn bị khuyết | Không mất những ID có thật dù dải có lỗ hổng |
| Số partition lớn hơn số ID | Không tạo quá nhiều partition rỗng hoặc lỗi chia 0 |
| Hai file trùng tên ở thư mục khác nhau | Manifest tạo partition key khác nhau và ổn định |
| Worker lỗi rồi restart | Chỉ phần việc cần retry được xử lý lại theo identity đúng |
| Hai worker cùng ghi đích | Writer tránh trùng và transaction giữ nhất quán |
| Nguồn thay đổi trong khi đọc | Snapshot/watermark chính sách chọn dữ liệu được thực thi |

Một kiểm thử đối soát mạnh là so sánh **tập business key đầu vào kỳ vọng** với **tập business key đã xử lý thành công**, đồng thời kiểm tra các khóa xuất hiện nhiều hơn một lần. Chỉ thấy `writeCount` của các worker cộng lại bằng số dòng nguồn chưa đủ để kết luận đúng.

## 9. Quan sát và lựa chọn kiến trúc khi tải lớn

Trong multi-threaded step, nhiều thread có thể dùng chung một `StepExecution`; trong partitioning, mỗi partition là **một worker `StepExecution` riêng**, giúp chia checkpoint và theo dõi theo phần việc rõ ràng hơn.

Nên ghi nhận theo partition:

- Tên partition, worker step name, `JobExecutionId`/`StepExecutionId`, range hoặc file ID và phiên bản kế hoạch nguồn.
- Status (`STARTED`, `COMPLETED`, `FAILED`, ...), thời gian bắt đầu/kết thúc, thời lượng.
- `readCount`, `writeCount`, filter/skip/rollback count, tốc độ item/giây.
- CPU, I/O, độ trễ database, mức sử dụng connection pool và số lần retry.

Ví dụ, nếu `range-0003` luôn chậm hơn ba partition còn lại, nguyên nhân có thể là **phân bố dữ liệu không đều** (range cuối chứa nhiều hàng), query plan khác biệt hoặc tranh chấp khóa khi ghi. Việc tăng `gridSize` không luôn giúp, vì số partition logic, số thread và tài nguyên database có những giới hạn riêng.

| Bài toán | Cân nhắc |
| --- | --- |
| Dữ liệu phân bố đều theo ID và truy vấn theo index | Range partitioning là lựa chọn dễ hiểu |
| ID phân bố lệch lớn | Chia theo số hàng khảo sát trước, shard key hoặc hash/bucket phù hợp |
| Nhiều file độc lập | Mỗi file/nhóm file dùng một manifest key ổn định |
| Dữ liệu nằm trên nhiều máy/shard | Remote partitioning, với định danh partition/nguồn và checkpoint bền vững |
| Một partition tạo bottleneck lớn | Tái thiết kế kế hoạch partition **cho lần chạy mới**, thay vì âm thầm đổi kế hoạch của restart |

Chiến lược hash có thể cân bằng dữ liệu hơn range trong một số trường hợp, nhưng biểu thức hash/modulo trên cột có thể khiến database khó dùng index hiệu quả. Hãy đo query plan, số hàng từng partition và throughput trước khi chọn.

## 10. Tình huống tự kiểm tra

**Bối cảnh:** Job xử lý một triệu đơn hàng, chia theo bốn partition. Lập trình viên tạo tên bằng `UUID.randomUUID()` mỗi lần `partition()` được gọi, rồi đặt range ID trong `ExecutionContext`. Khi job lỗi và chạy lại, key mới được tạo. Ở lượt khác, họ đổi số partition từ 4 thành 8 và giữ tên `partition-0` tới `partition-7`.

**Câu hỏi:**

1. Vì sao UUID mới mỗi lần gọi lại làm khó restart?
2. Nếu tên `partition-0` vẫn tồn tại nhưng range đã đổi, điều gì có thể xảy ra?
3. Nếu tất cả key là duy nhất nhưng hai range cùng chứa `id=250000`, liệu partitioning đã đúng?
4. Muốn tăng worker mà vẫn giữ kết quả đúng và khả năng khôi phục, cần kiểm soát những yếu tố nào?

**Định hướng trả lời:** Tên partition là thành phần identity của worker step và cần ổn định khi restart. Tái sử dụng tên với range khác có thể khiến lịch sử/checkpoint không còn ứng với phần việc mới. Key duy nhất không ngăn overlap; phải đảm bảo bao phủ và không giao thoa theo predicate. Khi scale, cố định kế hoạch phân vùng theo JobInstance, dùng reader riêng theo `ExecutionContext`, writer idempotent và kiểm thử dữ liệu cùng các chỉ số hiệu năng.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, worker/manager steps và phân phối công việc.
- [Spring Batch API — Partitioner](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/support/Partitioner.html): hợp đồng `partition(int gridSize)` và kết quả `Map<String, ExecutionContext>`.
- [Spring Batch API — PartitionNameProvider](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/support/PartitionNameProvider.html): hợp đồng danh sách tên partition hỗ trợ restart.
- [Spring Batch Reference — Step Scope](https://docs.spring.io/spring-batch/reference/step/late-binding.html): sử dụng `stepExecutionContext` để bind dữ liệu theo worker.

> **Ghi nhớ:** Một partition key cần **duy nhất trong tập partition và ổn định theo kế hoạch công việc**, nhưng tính đúng đắn còn đòi **input không giao nhau, bao phủ đủ, checkpoint gắn đúng phạm vi và writer chịu được replay**. Đây là nền tảng để Spring Batch scale mà vẫn restart và đối soát được.
