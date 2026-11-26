# gridSize và số partition trong Spring Batch

> **Chương:** Partitioning
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán phù hợp. Bài học làm rõ quan hệ giữa `gridSize`, số partition thực tế, số worker đồng thời và tài nguyên xử lý; từ đó lựa chọn cách chia tải an toàn, đo bottleneck và bảo đảm retry/restart.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `gridSize` là **tham số hướng dẫn chia công việc**, không phải cam kết Spring Batch sẽ tạo đúng từng ấy partition hay từng ấy thread.
2. Phân biệt **số partition logic**, **concurrency thực tế**, **số worker JVM**, **chunk size** và **kích thước dữ liệu mỗi partition**.
3. Viết `Partitioner` tôn trọng `gridSize`, chia khoảng ID không chồng lấn và xử lý cả khi số partition lớn hơn số đơn vị dữ liệu.
4. Cấu hình `gridSize` và `TaskExecutor` cho local partitioning, hiểu ràng buộc tương tự trong remote partitioning.
5. Chọn mức chia theo benchmark, sự phân bố dữ liệu, khả năng database và yêu cầu restart; tránh đổi kế hoạch phân vùng tùy tiện giữa các lần chạy.

## 1. gridSize thực sự mang ý nghĩa gì?

Trong Spring Batch, partitioning chia một **manager step** thành nhiều **worker StepExecution** độc lập. Mỗi worker đọc, xử lý và ghi một phần dữ liệu theo `ExecutionContext` riêng.

`gridSize` là một giá trị nguyên mà hạ tầng partitioning chuyển tới `StepExecutionSplitter` và `Partitioner` để **gợi ý số đơn vị công việc cần tạo**. Hợp đồng chính của partitioner là:

~~~java
public interface Partitioner {
    Map<String, ExecutionContext> partition(int gridSize);
}
~~~

Vì kết quả là một `Map`, **số partition logic được tạo bằng số phần tử thực tế trong map**, chứ không phải giá trị `gridSize`. Một partitioner có quyền tạo nhiều hoặc ít hơn số được gợi ý; ví dụ, chia theo danh sách 12 file cố định thì vẫn có thể trả về 12 partition khi `gridSize = 4`.

Trong cách cấu hình local phổ biến:

~~~java
new StepBuilder("ordersManagerStep", jobRepository)
    .partitioner("ordersWorkerStep", ordersPartitioner)
    .step(ordersWorkerStep)
    .gridSize(8)
    .taskExecutor(partitionExecutor)
    .build();
~~~

Ở đây, `gridSize(8)` đặt giá trị hướng dẫn trong cơ chế partitioning do builder cấu hình. Nó **không** tự tạo tám thread và **không** buộc `ordersPartitioner` phải trả đúng tám entry. Khả năng chạy đồng thời còn phụ thuộc `partitionExecutor` và worker step.

### Bốn con số dễ bị nhầm

| Đại lượng | Ví dụ | Ai quyết định? | Ý nghĩa |
| --- | ---: | --- | --- |
| `gridSize` | 8 | Cấu hình manager/handler | Gợi ý độ chia khi yêu cầu splitter/partitioner tạo phần việc |
| Số partition thực tế | 12 | `Partitioner` trả về `Map` 12 entry | Tổng số phần việc logic được nhận diện theo partition key |
| Số worker đồng thời | 4 | Executor hoặc sức chứa worker remote | Số phần việc có thể chạy cùng lúc tại một thời điểm |
| `chunkSize` | 500 | Cấu hình worker chunk step | Số item thường được gom vào một chu kỳ xử lý/transaction chunk |

Nếu có **12 partition** và executor chạy tối đa **4 worker** đồng thời, hệ thống sẽ xử lý công việc theo nhiều đợt. Có thể hình dung 3 đợt × 4 worker *nếu* các partition có thời lượng tương đương; thực tế các worker kết thúc không đồng thời và việc cấp phát thường được thực hiện khi có slot trống.

~~~mermaid
flowchart TB
    M["Manager step<br/>gridSize = 8"]
    M --> P["Partitioner<br/>trả 12 partition"]
    P --> S["StepExecutionSplitter<br/>tạo/chọn worker StepExecution"]
    S --> H["PartitionHandler"]
    H --> E["TaskExecutor<br/>4 slot đồng thời"]
    E --> W1["Worker slot 1"]
    E --> W2["Worker slot 2"]
    E --> W3["Worker slot 3"]
    E --> W4["Worker slot 4"]
    P -. "12 phần việc xếp hàng theo tài nguyên" .-> E
~~~

Sơ đồ thể hiện ý tưởng điều phối. Số partition được splitter **chọn chạy** ở một lần restart có thể ít hơn tổng số partition do lịch sử những partition đã hoàn thành.

## 2. Tại sao gridSize không bằng số thread?

Một worker partition thường đại diện cho một **worker `StepExecution`**, không phải một thread cố định suốt vòng đời job. `PartitionHandler` tổ chức việc chạy worker:

- Với **local partitioning**, `TaskExecutorPartitionHandler` sử dụng `TaskExecutor`. Nếu pool có bốn thread xử lý, tại một thời điểm chỉ khoảng bốn worker thực sự hoạt động, dù partitioner tạo 20 phần việc.
- Với **remote partitioning**, manager gửi yêu cầu tới các worker bên ngoài. Số phần việc chạy đồng thời phụ thuộc số tiến trình/container, số consumer/worker slot, giới hạn của broker và tài nguyên phía worker.
- Với **parallel steps**, các step độc lập cũng có thể chạy đồng thời, nhưng đó là cơ chế điều phối khác. `gridSize` của partitioning không phải số lượng parallel steps.
- Nếu bên trong từng worker còn dùng **multi-threaded chunk step**, số thread xử lý item lại là một tầng concurrency riêng; phải kiểm soát an toàn luồng và tổng số kết nối.

### Ví dụ hai tầng concurrency

Giả sử có 8 partition, tối đa 4 worker chạy đồng thời, mỗi worker lại được cấu hình multi-threaded step có tối đa 3 thread. Khi đó số chunk đang xử lý đồng thời **có thể tiến gần 12** thay vì 4, tùy cách cấu hình và trạng thái runtime.

Điều này có thể vượt khả năng database pool hoặc khiến reader stateful bị chia sẻ giữa các thread trong **cùng một worker StepExecution**. `@StepScope` tạo bean theo **step execution**, không tạo một bản reader mới trên từng thread chunk. Trong đa số bài toán, nên bắt đầu bằng một tầng partitioning có ranh giới dữ liệu rõ ràng, rồi mới xem xét concurrency bên trong worker nếu số đo chứng minh cần thiết.

## 3. Partitioner có thể sinh ra bao nhiêu partition?

`gridSize` là đầu vào; cách tính số partition là quyết định của implementation.

| Cách viết Partitioner | `gridSize = 4` | Số partition thực tế | Vì sao |
| --- | ---: | ---: | --- |
| Chia tập ID thành tối đa `gridSize` range | 4 | 4 nếu đủ dải dữ liệu | Tôn trọng gợi ý |
| Chia danh sách 12 file, mỗi file một partition | 4 | 12 | Đơn vị tự nhiên là file |
| Chia ba tenant độc lập | 4 | 3 | Chỉ có ba phần việc hợp lệ |
| Chia theo 100 shard cấu hình sẵn | 4 | 100 | `gridSize` không được dùng trong chiến lược chia |
| Chia 2 ID thành tối đa bốn range không rỗng | 4 | 2 | Tránh partition rỗng |

Không có chiến lược nào đúng cho tất cả nguồn dữ liệu. Khi input là file lớn có thể chia theo byte range nhưng mỗi dòng dài biến động, partition theo số byte còn cần xử lý chính xác ranh giới bản ghi. Khi input là database, khoảng ID đơn giản nhưng **không bảo đảm số hàng trong mỗi partition cân bằng**, nhất là nếu ID thưa hoặc dữ liệu phân bố lệch.

**Quy tắc:** Kế hoạch phải bảo đảm (1) tên partition duy nhất, (2) các tập input không chồng lấn, (3) bao phủ toàn bộ tập cần xử lý, (4) ổn định khi restart cùng một `JobInstance`. Việc trả đúng số entry bằng `gridSize` không đủ để đảm bảo bốn điều này.

## 4. Tính range từ gridSize: một ví dụ hoàn chỉnh

Giả sử bảng `orders` có các khóa ID hợp lệ trong khoảng nửa mở `[1, 101)`, tức tối đa 100 ID. Ta muốn chia thành nhiều range gần bằng nhau theo `gridSize`. Quy ước khoảng nửa mở giúp tránh đọc trùng ở ranh giới:

~~~sql
SELECT id, order_code
FROM orders
WHERE id >= :minIdInclusive
  AND id < :maxIdExclusive
ORDER BY id;
~~~

Với `gridSize = 3`:

| Partition key | min bao gồm | max loại trừ | Tập ID |
| --- | ---: | ---: | --- |
| `range-0000` | 1 | 35 | 1–34 |
| `range-0001` | 35 | 69 | 35–68 |
| `range-0002` | 69 | 101 | 69–100 |

Ba range có kích thước lần lượt 34, 34, 32; chúng không giao nhau và phủ đủ không gian khóa. Dù vậy, nếu bảng thực sự chỉ có 60 hàng vì một số ID bị xóa, **không thể dựa vào độ rộng range để kết luận khối lượng xử lý mỗi worker bằng nhau**.

### 4.1. Cài đặt Partitioner

Mẫu dưới đây viết theo Spring Batch 5.x. `gridSize` có thể thay đổi từ 1 trở lên; số partition được giới hạn để không tạo range rỗng khi số ID ít hơn gợi ý.

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class IdRangePartitioner implements Partitioner {

    private final long minInclusive;
    private final long maxExclusive;

    public IdRangePartitioner(long minInclusive, long maxExclusive) {
        if (minInclusive >= maxExclusive) {
            throw new IllegalArgumentException("Dải ID phải không rỗng");
        }
        this.minInclusive = minInclusive;
        this.maxExclusive = maxExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize phải > 0");
        }

        // Ví dụ chỉ dành cho khoảng long đủ nhỏ để phép trừ/cộng an toàn.
        long total = maxExclusive - minInclusive;
        int count = (int) Math.min((long) gridSize, total);
        long width = total / count + (total % count == 0 ? 0 : 1);

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        for (int i = 0; i < count; i++) {
            long from = minInclusive + i * width;
            if (from >= maxExclusive) {
                break;
            }
            long to = Math.min(maxExclusive, from + width);

            String key = String.format(Locale.ROOT, "range-%04d", i);
            ExecutionContext context = new ExecutionContext();
            context.putLong("minIdInclusive", from);
            context.putLong("maxIdExclusive", to);

            if (partitions.putIfAbsent(key, context) != null) {
                throw new IllegalStateException("Trùng partition key: " + key);
            }
        }
        return partitions;
    }
}
~~~

Ví dụ `new IdRangePartitioner(1L, 101L).partition(3)` sinh đúng ba entry như bảng. `partition(200)` sinh tối đa 100 partition, mỗi partition chứa một ID trong không gian khóa; việc tạo 100 worker cho bài toán nhỏ này có thể **tốn overhead nhiều hơn lợi ích tăng tốc**.

**Giới hạn của ví dụ:** Công thức giả định dải `long` đủ nhỏ để tính `max - min` và `min + i * width` không bị tràn số. Khi dùng ID rất lớn hoặc nhiều dữ liệu hơn, cần tính toán an toàn tràn số và xác định ranh giới từ kế hoạch nguồn ổn định. Đặc biệt, `maxExclusive` không phải tự nhiên luôn bằng `MAX(id) + 1` nếu `MAX(id)` ở sát giới hạn của kiểu số.

### 4.2. Kết nối với manager step và giới hạn concurrency

~~~java
@Bean
Partitioner ordersPartitioner() {
    // Với hệ thống thật, cố định những biên này theo snapshot của JobInstance.
    return new IdRangePartitioner(1L, 100_001L);
}

@Bean
ThreadPoolTaskExecutor partitionExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("orders-part-");
    executor.initialize();
    return executor;
}

@Bean
Step ordersManagerStep(
        JobRepository jobRepository,
        @Qualifier("ordersWorkerStep") Step workerStep,
        @Qualifier("ordersPartitioner") Partitioner partitioner,
        ThreadPoolTaskExecutor partitionExecutor) {

    return new StepBuilder("ordersManagerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(8)
            .taskExecutor(partitionExecutor)
            .build();
}
~~~

Với cấu hình trên, partitioner tạo **8 partition logic** (vì dải có đủ khóa), còn executor được giới hạn ở **4 worker đồng thời**. `ordersWorkerStep` là bean chunk step được định nghĩa riêng với transaction manager, reader `@StepScope`, processor và writer. Các import Spring Batch tương ứng gồm `Step`, `StepBuilder`, `JobRepository`, `Partitioner`, `ThreadPoolTaskExecutor` và `Qualifier`.

**Lưu ý quan trọng:** Bean partitioner minh họa dùng range tĩnh; khi cần lấy từ database đang thay đổi, hãy xác định snapshot/watermark và lưu **kế hoạch chia** cho cùng `JobInstance`. Nếu sau khi một số partition đã hoàn tất bạn đổi `gridSize` từ 8 thành 16 mà vẫn restart cùng job, tên `range-0004` có thể chỉ tới một khoảng khác, dẫn đến sai checkpoint hoặc bỏ sót dữ liệu.

### 4.3. Reader mỗi partition phải đọc đúng range

Khi manager tạo đúng tám partition, nếu reader ở cả tám worker cùng chạy `SELECT * FROM orders` thì hệ thống sẽ **đọc và ghi trùng** dù `gridSize` được cấu hình chuẩn.

Mỗi worker `StepExecution` cần lấy ranh giới trong `ExecutionContext` do partitioner cấp:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<OrderRow> ordersReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minIdInclusive']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<OrderRow>()
            .name("ordersReader")
            .dataSource(dataSource)
            .selectClause("SELECT id, order_code")
            .fromClause("FROM orders")
            .whereClause("WHERE id >= :minId AND id < :maxId")
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderRow(
                    rs.getLong("id"), rs.getString("order_code")))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

`OrderRow` là record/POJO nghiệp vụ. Các kiểu reader/builder/`Order` thuộc Spring Batch JDBC; `StepScope`, `Value`, `DataSource` và `Map` thuộc Spring Framework/Java tương ứng. Đây là cấu hình tập trung vào cơ chế chọn nguồn cho worker, chưa phải một job hoàn chỉnh.

Ở worker partitioning, `@StepScope` tạo reader theo **worker StepExecution**. Các partition có `ExecutionContext` và checkpoint riêng; việc này khác việc gắn `TaskExecutor` trực tiếp vào một step có nhiều thread cùng chia sẻ reader. Reader paging cũng cần sort key duy nhất, ổn định để đảm bảo tính đúng khi phân trang và restart.

## 5. Grid size lớn hơn có luôn chạy nhanh hơn?

Không. Tăng số partition có thể cân bằng tải tốt hơn và tăng khả năng tận dụng worker, nhưng cũng tăng chi phí lập kế hoạch, tạo `StepExecution`, mở reader/transaction, truy vấn database và giám sát.

Một mô hình ước lượng đơn giản:

~~~text
Tổng thời gian
  ≈ chi phí chuẩn bị partition
    + thời gian xử lý của đợt worker chậm nhất
    + chi phí commit/retry/điều phối

Số worker đồng thời thực tế
  ≤ min(slot của executor/worker, partition chưa hoàn thành, tài nguyên khả dụng)
~~~

Đây là mô hình định hướng, không phải công thức dự đoán chính xác: các worker thực tế có thể khởi động và hoàn tất lệch nhau, còn database có các pha chờ khóa hoặc bão hòa I/O.

### Ba kịch bản thường gặp

**1. Grid size quá nhỏ.** Hai partition cho máy có tám core CPU, trong khi mỗi partition xử lý CPU nặng và độc lập, có thể làm nhiều core nhàn rỗi. Tăng từ 2 lên 8 partition rồi giữ concurrency phù hợp có thể cải thiện throughput nếu dữ liệu được chia cân bằng.

**2. Grid size lớn nhưng executor nhỏ.** Tạo 100 partition với executor bốn thread: vẫn chỉ có bốn worker chạy đồng thời. Có thể tăng cân bằng tải (partition nào xong thì slot nhận partition tiếp), nhưng chi phí metadata, mở reader và checkpoint nhiều hơn. Không mặc nhiên nhanh hơn bốn partition.

**3. Database đã bão hòa.** Tăng từ 8 lên 32 partition và tăng worker làm nhiều query đồng thời tranh chấp connection pool/lock. Throughput có thể giảm, rollback hoặc timeout tăng. Đó là dấu hiệu cần tối ưu câu SQL, index, writer, transaction hoặc giới hạn concurrency trước khi tăng `gridSize`.

| Tình huống | Dấu hiệu đo được | Cách điều chỉnh |
| --- | --- | --- |
| CPU còn rảnh, worker đang bận CPU | Throughput tăng gần tuyến tính khi thêm worker ban đầu | Tăng số partition/concurrency có kiểm soát |
| Một partition kéo dài hơn phần còn lại | Worker cuối chạy rất lâu; dữ liệu phân bố lệch | Chia range nhỏ hơn hoặc chia theo số hàng/khóa tốt hơn |
| DB pool gần cạn | Thời gian chờ connection và query tăng | Giảm concurrency hoặc tăng/tối ưu pool phù hợp DB |
| Nhiều transaction nhỏ | Overhead commit/metadata cao | Cân đối partition count và chunk size; đo thời gian commit |
| Reader tải một bảng với full scan mỗi worker | I/O tăng mạnh, index không được tận dụng | Kiểm tra range predicate, query plan và index |
| Broker/remote worker có hàng đợi lớn | Message lag tăng, worker không xử lý kịp | Điều chỉnh worker slots và rate limit theo sức chứa |

**Lưu ý về tài nguyên:** Với 8 worker đồng thời, mỗi worker thường cần connection để đọc/ghi theo cách cấu hình của ứng dụng; tổng số connection có thể cao hơn 8 nếu reader và writer dùng nhiều kết nối. Không lấy `gridSize` làm kích thước database pool trực tiếp; hãy đo số kết nối đỉnh, truy vấn đồng thời, transaction và timeout.

## 6. Cân bằng tải: nhiều partition nhỏ hay ít partition lớn?

Không phải mọi partition đều tốn thời gian như nhau. Ví dụ hai khoảng ID bằng độ rộng nhưng một khoảng có 10.000 hàng, khoảng kia có 2 triệu hàng. Nếu mỗi worker chỉ xử lý một khoảng, một worker có thể trở thành **đuôi dài** khiến toàn job hoàn thành muộn.

~~~mermaid
flowchart LR
    A["Chia 4 range lớn"] --> B["Một range nhiều hàng<br/>giữ worker lâu"]
    C["Chia 16 range nhỏ"] --> D["Worker nhận phần việc tiếp<br/>khi có slot trống"]
    D --> E["Cân bằng tải có thể tốt hơn"]
    B --> F["Tail latency cao"]
~~~

Nếu nguồn có thể chia thành nhiều phần **độc lập, không giao nhau**, có thể tạo số partition **lớn hơn số worker slot** để mỗi slot tiếp tục xử lý phần việc kế tiếp. Nhưng partition quá nhỏ làm tăng overhead và số metadata entries; cần tìm điểm cân bằng bằng benchmark.

Các cách chia thường dùng:

- **ID range:** Dễ checkpoint và dùng index trên cột ID, nhưng mất cân bằng khi ID thưa hoặc dữ liệu phân bố lệch.
- **File/manifest:** Mỗi file hoặc nhóm file thành một partition; dùng key ổn định theo manifest. Cân đối file rất lớn và rất nhỏ bằng cách nhóm hợp lý.
- **Tenant/shard:** Có ranh giới tự nhiên, nhưng tenant lớn có thể trở thành hotspot; cần cân nhắc chia nhỏ trong phạm vi tenant.
- **Danh sách key đã khảo sát:** Tạo các bucket có số bản ghi gần nhau, lưu kế hoạch cố định cho job. Chi phí chuẩn bị cao hơn nhưng thường cân bằng hơn ID range thô.

Không đổi phân hoạch sau khi một phần job đã chạy chỉ để xử lý hotspot ngay trên **cùng kế hoạch restart**; có thể làm hỏng ánh xạ tên partition → phạm vi dữ liệu và checkpoint. Muốn tái chia, hãy thiết kế lượt xử lý mới với quy tắc chống ghi trùng.

## 7. Retry, restart và tính ổn định của gridSize

Splitter và repository sử dụng tên partition/`StepExecution` cùng trạng thái đã lưu để chọn worker cần thực thi khi restart. Nếu lần đầu partitioner gán:

| Key | Khi `gridSize=4` |
| --- | --- |
| `range-0000` | `[1, 25001)` |
| `range-0001` | `[25001, 50001)` |
| `range-0002` | `[50001, 75001)` |
| `range-0003` | `[75001, 100001)` |

Sau khi `range-0000` và `range-0001` hoàn tất, job lỗi ở `range-0002`. Nếu chạy lại cùng `JobInstance` với `gridSize=2`, các tên `range-0000`/`range-0001` có thể được gán khoảng mới `[1, 50001)`/`[50001, 100001)`. History và checkpoint bây giờ không còn đại diện cho đúng công việc: hệ thống có thể bỏ qua phần cần đọc hoặc xử lý lại phần đã hoàn tất.

**Cách tránh:** Chốt số partition và mọi ranh giới theo **JobInstance** hoặc một **partition plan ID** được lưu bền vững; khi restart phải tái sử dụng chính xác kế hoạch cũ. Có thể đưa tham số nhận diện kế hoạch vào identifying `JobParameters`, giữ file manifest, watermark, snapshot hoặc bảng metadata riêng để phục dựng đúng key/context.

### Phân biệt ba loại “chạy lại”

| Tình huống | `gridSize` có thể thay đổi tùy ý? | Hướng xử lý |
| --- | --- | --- |
| Retry một chunk trong worker | Không liên quan trực tiếp | Giữ partition/context; áp dụng retry và rollback của worker |
| Restart cùng `JobInstance` sau job lỗi | **Không** đổi kế hoạch partition cũ | Giữ key→range/file, checkpoint và điều kiện đọc |
| Chạy `JobInstance` mới với kế hoạch mới | Có thể chọn mức chia khác | Đảm bảo input và writer idempotent nếu tái xử lý dữ liệu cũ |

Trong remote partitioning, broker có thể giao lại request khi worker đã ghi một phần nhưng phản hồi bị mất. Thay đổi `gridSize` không khắc phục được việc phát lại; cần metadata nhất quán, kiểm soát worker chạy chồng và writer idempotent tại đích.

## 8. Chọn gridSize theo số đo thực tế

Hãy đo **baseline tuần tự** và các mức chia/concurrency có thể so sánh, thay vì chọn `gridSize` chỉ dựa trên số core CPU.

### Quy trình thử nghiệm

1. **Cố định tập input:** Dùng cùng snapshot hoặc manifest có danh sách business key, cùng chỉ số lượng dữ liệu, cùng quy tắc lọc/skip.
2. **Đo chạy tuần tự:** Thời gian job, item/giây, CPU, heap/GC, thời gian query và write, connection pool.
3. **Chọn số worker thực thi:** Ví dụ 1 → 2 → 4 → 8 slot, luôn trong giới hạn của nguồn/đích.
4. **Thử mức partition lớn hơn worker:** Ví dụ với 4 slot, so sánh 4, 8, 16 partition. Quan sát tail latency và chi phí metadata/chunk.
5. **Đối soát kết quả:** Kiểm tra business ID duy nhất, số hàng insert/update/no-op, dữ liệu bị bỏ qua, checksum/tổng tiền khi phù hợp.
6. **Kiểm tra phục hồi:** Gây lỗi một partition, restart bằng đúng kế hoạch và xác nhận không bỏ sót hoặc nhân đôi tác dụng phụ.
7. **Chốt cấu hình theo môi trường:** Lưu kế hoạch cho JobInstance, đặt ngưỡng cảnh báo và đo lại khi khối lượng dữ liệu hoặc hạ tầng thay đổi.

### Ví dụ bảng kết quả benchmark (số minh họa)

| gridSize | Partition thực tế | Worker slot | Thời gian | Throughput | Nhận xét |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1 | 1 | 80 phút | 1.000 item/s | Baseline |
| 4 | 4 | 4 | 27 phút | 2.963 item/s | Tận dụng thêm CPU |
| 8 | 8 | 4 | 24 phút | 3.333 item/s | Cân bằng tải tốt hơn |
| 32 | 32 | 4 | 25 phút | 3.200 item/s | Overhead nhiều hơn |
| 32 | 32 | 8 | 29 phút | 2.759 item/s | DB bắt đầu nghẽn |

Đây là **số liệu giả định** cho khoảng 4,8 triệu item, không phải benchmark chính thức của Spring Batch. Nó minh họa rằng `gridSize = 8` với 4 worker có thể phù hợp hơn mức 32 trong một hệ thống cụ thể. Kết quả thật cần dựa trên phép đo ở hạ tầng và dữ liệu của chính ứng dụng.

### Nên ghi metric gì?

| Tầng | Metric nên có | Mục tiêu |
| --- | --- | --- |
| Manager | Số partition tạo ra/chọn chạy, thời gian lập kế hoạch, trạng thái chung | Tìm overhead chia việc hoặc lỗi dispatch |
| Worker | Partition key, `StepExecutionId`, duration, `readCount`, `writeCount`, skip/rollback count | Phát hiện worker chậm, fail, mất cân bằng |
| Executor | Active threads, queue depth, task latency | Xác định giới hạn concurrency local |
| Remote | Worker slots, broker lag/ack, timeout, retry | Xác định bottleneck truyền nhận |
| Dữ liệu | Rows inserted/updated/no-op, business key duy nhất | Xác minh hiệu ứng ghi đúng |
| Hạ tầng | CPU, heap, GC, DB pool, lock wait, I/O/network | Chọn mức scale theo tài nguyên thực |

`readCount` và `writeCount` thuộc `StepExecution`, không đồng nghĩa số bản ghi duy nhất ở đích. Khi có restart, một partition logic có thể trải qua nhiều execution; dashboard cần phân biệt khối lượng item đã thử xử lý với kết quả cuối cùng.

## 9. Các lỗi cấu hình thường gặp

**“Đặt gridSize(16) nghĩa là chạy 16 thread.”** Sai: số worker đồng thời bị giới hạn bởi `TaskExecutor`, worker slots và sức chứa hạ tầng. Một partitioner có thể tạo ít hơn 16 partition.

**“Có 20 file thì đặt gridSize(4) sẽ tự chia thành bốn nhóm năm file.”** Không tự động. Nếu partitioner tạo một partition cho mỗi file, kết quả vẫn là 20 partition. Muốn gom file theo nhóm, phải viết logic gom nhóm và xác định ranh giới/identity ổn định.

**“Tăng gridSize sẽ luôn giảm thời gian job.”** Không đúng khi tăng overhead hoặc database đã bão hòa. Nên đo độ lệch thời gian các partition và khả năng tiêu thụ tài nguyên thật.

**“Đổi gridSize khi restart không ảnh hưởng dữ liệu.”** Nguy hiểm nếu key cũ trỏ tới range mới. Phải giữ kế hoạch gắn với JobInstance hoặc chủ động tạo lượt xử lý mới.

**“Cứ có key khác nhau là không trùng item.”** Sai: hai partition có thể có key duy nhất nhưng cùng câu SQL không lọc theo context. Cần đối soát tập đầu vào và bảo vệ idempotency của writer.

**“gridSize bằng chunk size.”** Hai thứ thuộc hai tầng khác nhau: một cái định hướng số phần việc; cái còn lại quyết định kích thước chunk của worker trong mô hình read/process/write.

## 10. Bài tập tự kiểm tra

**Bài 1.** Manager cấu hình `gridSize=10`. Partitioner lấy từ manifest 6 file và trả 6 entry; `ThreadPoolTaskExecutor` có 3 thread. Hệ thống sẽ có bao nhiêu partition logic, tối đa bao nhiêu worker chạy đồng thời, và `gridSize=10` có nghĩa gì?

**Bài 2.** Manager tạo 8 partition, pool có 4 worker, chunk size là 200. Người vận hành tăng `gridSize` từ 8 lên 16 nhưng giữ pool bằng 4. Hãy nêu hai tình huống tăng số partition có thể hữu ích, hai tình huống không cải thiện tốc độ, và cách kiểm chứng.

**Bài 3.** Job đầu tiên dùng bốn range. Hai range đã `COMPLETED` rồi job lỗi. Ở lần restart, bạn thấy một kỹ sư đổi `gridSize=2` vì “ít worker sẽ bớt áp lực DB”. Nên thay cấu hình theo cách nào để giảm concurrency **mà không đổi ánh xạ partition key → range**?

**Định hướng trả lời:**

- Bài 1: Có **6 partition logic**, tối đa khoảng **3 worker đồng thời** khi executor cấp đủ thread; `gridSize=10` chỉ là gợi ý gửi tới splitter/partitioner.
- Bài 2: Nhiều partition nhỏ có thể cải thiện cân bằng tải, lấp thời gian worker trống; không giúp nếu database đã nghẽn hoặc overhead mở/commit partition tăng. Cần đo throughput, tail latency, DB wait và đối soát business key.
- Bài 3: Giữ nguyên kế hoạch 4 range và key đã chốt cho JobInstance; điều chỉnh **concurrency executor/worker slot** theo khả năng tài nguyên, đồng thời kiểm tra handler, queue và tình trạng worker cũ trước khi restart. Không tùy tiện dùng `gridSize` mới để tái chia cùng công việc logic.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, `gridSize`, multi-threaded step và các hình thức scale.
- [Spring Batch API — Partitioner](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/support/Partitioner.html): hợp đồng `partition(int gridSize)`.
- [Spring Batch API — StepExecutionSplitter](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/StepExecutionSplitter.html): bước chọn worker executions.
- [Spring Batch API — TaskExecutorPartitionHandler](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/partition/support/TaskExecutorPartitionHandler.html): handler dùng executor để chạy worker.
- [Spring Batch Reference — Step Scope and Late Binding](https://docs.spring.io/spring-batch/reference/step/late-binding.html): bind `stepExecutionContext` cho reader theo partition.

> **Ghi nhớ:** `gridSize` là **hướng dẫn chia việc**; `Partitioner` quyết định **có bao nhiêu partition**, còn `PartitionHandler` cùng executor hoặc remote workers quyết định **bao nhiêu phần việc được chạy đồng thời**. Hãy giữ kế hoạch phân vùng ổn định khi restart, bảo đảm dữ liệu không giao nhau và chọn cấu hình từ benchmark cùng khả năng thực tế của hệ thống.
