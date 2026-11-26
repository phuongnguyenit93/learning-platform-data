# ExecutionContext của Step trong Spring Batch

> **Chương:** ExecutionContext
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán; đồng thời bảo đảm thread safety, retry/restart và vận hành theo tài nguyên thực tế. Bài này đi sâu vào **ExecutionContext thuộc StepExecution**: nơi lưu tham số phạm vi công việc, checkpoint và state phục vụ khôi phục.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Step ExecutionContext** với **Job ExecutionContext**, `JobParameters` và bộ nhớ Java tạm thời.
2. Đọc/ghi `StepExecution.getExecutionContext()` và hiểu khi nào framework lưu context vào `JobRepository`.
3. Kết hợp `@StepScope`, `stepExecutionContext` và `ItemStream` để truyền ranh giới dữ liệu và checkpoint cho từng worker.
4. Giải thích vì sao các context riêng trong partitioning hỗ trợ restart, nhưng không tự cung cấp thread safety hoặc exactly-once side effect.
5. Thiết kế dữ liệu context gọn, có thể serialize, ổn định qua phiên bản và kiểm thử phục hồi sau lỗi.

## 1. Step ExecutionContext là gì?

Trong Spring Batch, `ExecutionContext` là một tập **key–value có thể lưu bền vững** gắn với vòng đời execution. Một `StepExecution` có **ExecutionContext của chính nó**, dùng để lưu các giá trị như:

- Ranh giới dữ liệu được giao: `minIdInclusive`, `maxIdExclusive`, `fileId` hoặc `tenantId`.
- Vị trí đã xử lý để restart: số dòng, index, checkpoint của reader hoặc writer.
- State nhỏ của một bước xử lý: watermark, trạng thái cần phục hồi, phiên bản input.
- Thông tin kỹ thuật hữu ích, có thể ghi lại qua `JobRepository`.

Ví dụ worker partition có:

~~~text
StepExecution: ordersWorkerStep:range-0002
ExecutionContext:
  minIdInclusive = 50001
  maxIdExclusive = 75001
  sourceVersion = "orders-snapshot-v4"
  ordersReader.read.count = 12000   (tên key minh họa)
~~~

Ở đây, ba key đầu mô tả **công việc cần làm**, còn key cuối minh họa **tiến độ đã lưu**. Tên checkpoint thực tế do reader/`ItemStream` và phiên bản thư viện quyết định; không nên xây logic nghiệp vụ dựa trên tên key nội bộ nếu không kiểm soát implementation.

### Bốn loại thông tin dễ bị nhầm

| Đối tượng | Phạm vi | Điển hình chứa gì? | Có phải nơi lưu checkpoint của step? |
| --- | --- | --- | --- |
| `JobParameters` | Định danh và cấu hình một lần khởi chạy; identifying parameters xác định `JobInstance` | Ngày xử lý, mã nguồn, input version | **Không**; tham số đầu vào không phải state mutable để cập nhật khi xử lý |
| `JobExecution.getExecutionContext()` | Một lần `JobExecution` ở cấp job | Giá trị cần chuyển giữa các step, kết quả trung gian nhỏ | Không phải checkpoint riêng của mỗi worker |
| `StepExecution.getExecutionContext()` | **Một lần `StepExecution` cụ thể** | Phạm vi partition, reader/writer checkpoint | **Có**, thường là vị trí lưu state restart của step |
| Field Java / `ThreadLocal` | Instance hoặc thread hiện tại | Biến tạm thời khi chương trình chạy | **Không**; có thể mất khi tiến trình kết thúc |

`ExecutionContext` không phải một database nghiệp vụ, một cache phân tán hay một hàng đợi message. Nó chủ yếu phục vụ **vòng đời, recovery và phối hợp execution** trong Spring Batch.

## 2. Một StepExecution có context riêng như thế nào?

Một job có thể gồm nhiều step tuần tự, hai parallel steps hoặc nhiều partition của một worker step. Mỗi execution có context riêng, dù các worker dùng cùng một định nghĩa `Step`:

~~~mermaid
flowchart TB
    J["JobExecution"] --> M["Manager StepExecution"]
    M --> PM["Manager ExecutionContext"]
    M --> A["Worker StepExecution A"]
    M --> B["Worker StepExecution B"]
    M --> C["Worker StepExecution C"]
    A --> CA["ExecutionContext A<br/>range A + checkpoint A"]
    B --> CB["ExecutionContext B<br/>range B + checkpoint B"]
    C --> CC["ExecutionContext C<br/>range C + checkpoint C"]
    CA --> R[("JobRepository")]
    CB --> R
    CC --> R
    PM --> R
~~~

Không nên nhầm **một bean worker `Step`** với **một `StepExecution`**. Trong partitioning, framework có thể chạy cùng worker definition nhiều lần, mỗi lần với một partition name và context khác nhau:

| Worker execution | Partition key | Context đầu vào |
| --- | --- | --- |
| `importWorker:range-0000` | `range-0000` | `[1, 25001)` |
| `importWorker:range-0001` | `range-0001` | `[25001, 50001)` |
| `importWorker:range-0002` | `range-0002` | `[50001, 75001)` |

Việc context riêng cho phép worker A restart từ checkpoint của A mà không lấy nhầm checkpoint của B, **miễn là** tên partition, phạm vi input và cách lưu checkpoint được duy trì nhất quán.

### ExecutionContext khác StepContext

`StepExecution.getExecutionContext()` trả về đối tượng `ExecutionContext` chứa dữ liệu. Còn các expression như `#{stepExecutionContext['key']}` được resolve trong **step scope** của Spring Batch. Đừng nhầm `StepContext` (đối tượng hỗ trợ binding/điều phối scope) với `ExecutionContext` (dữ liệu trạng thái lưu trong repository).

## 3. Đọc và ghi Step ExecutionContext

Từ một `StepExecution` đã được framework cung cấp:

~~~java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;

void inspectStep(StepExecution stepExecution) {
    ExecutionContext ctx = stepExecution.getExecutionContext();

    long minId = ctx.getLong("minIdInclusive");
    long maxId = ctx.getLong("maxIdExclusive");

    // Lưu một giá trị tiến độ nhỏ, thuộc riêng StepExecution này.
    ctx.putLong("lastValidatedId", minId);

    System.out.printf("step=%s range=[%d, %d)%n",
            stepExecution.getStepName(), minId, maxId);
}
~~~

API thường dùng:

| API | Vai trò |
| --- | --- |
| `getString(key)`, `getLong(key)`, `getInt(key)`, `getDouble(key)` | Đọc giá trị với kiểu tương ứng |
| `putString(key, value)`, `putLong(...)`, `putInt(...)` | Lưu giá trị theo kiểu rõ ràng |
| `containsKey(key)` | Kiểm tra sự tồn tại của khóa trước khi đọc |
| `remove(key)` | Xóa state khi thật sự cần; cần xét ảnh hưởng restart |
| `isDirty()` | Cho biết context đã được thay đổi thông qua API của nó |
| `clearDirtyFlag()` | Phục vụ quản lý cờ thay đổi; thường để framework xử lý |

**Không tự cập nhật progress tùy tiện trên mỗi item rồi coi nó đã được commit.** Nếu state cần an toàn khi restart, nên để một `ItemStream` ghi checkpoint bằng `update(ExecutionContext)` ở vòng đời chunk hoặc thiết kế cơ chế cập nhật phù hợp với transaction.

### Cẩn thận khi ghi giá trị mutable

Một trường hợp dễ lỗi:

~~~java
// Không nên lấy một List mutable từ context rồi thêm item và
// mặc định việc thay đổi sâu đó luôn được framework phát hiện.
List<String> ids = (List<String>) ctx.get("ids");
ids.add("A-123");
~~~

Nếu bạn sửa nội dung của đối tượng mà **không gọi lại `put(...)`**, dirty flag có thể không được đánh dấu như mong đợi. Hơn nữa, việc lưu một danh sách tăng mãi còn khiến serialized context phình to. Nên lưu **vị trí/checkpoint nhỏ** (ví dụ last committed sequence) hoặc ghi dữ liệu nghiệp vụ vào bảng/đích phù hợp, thay vì tích lũy hàng triệu item trong `ExecutionContext`.

## 4. Khi nào ExecutionContext được lưu bền vững?

Với `JobRepository` dùng database quan hệ, Spring Batch lưu metadata của step và serialized context theo vòng đời execution. Trong **chunk-oriented step**, `ItemStream.update(...)` và việc lưu step context thường được phối hợp tại **ranh giới commit chunk**; state chưa commit không nên được xem là checkpoint bền vững.

~~~mermaid
sequenceDiagram
    participant R as ItemReader / ItemStream
    participant W as ItemWriter
    participant S as StepExecution
    participant J as JobRepository
    R->>R: open(ExecutionContext) lúc bắt đầu
    loop Chunk processing
        R->>R: read() nhiều item
        R->>W: write(chunk)
        R->>S: update(ExecutionContext)
        S->>J: Lưu context/counters theo ranh giới commit
        Note over J: Metadata bền vững sau commit phù hợp
    end
    R->>R: close()
    S->>J: Lưu trạng thái cuối của step
~~~

Sơ đồ là **mô hình khái niệm**. Thứ tự cập nhật chi tiết, thời điểm transaction bắt đầu và mức độ atomic phụ thuộc `TaskletStep`, transaction manager, reader/writer, repository và cấu hình hạ tầng.

### Ví dụ checkpoint

Job xử lý ID `[1, 1001)` bằng chunk size 100:

~~~text
Chunk 1: xử lý 1..100      -> commit -> checkpoint "nextId = 101"
Chunk 2: xử lý 101..200    -> commit -> checkpoint "nextId = 201"
Chunk 3: đọc 201..300      -> lỗi, transaction rollback

Restart:
  - trạng thái bền vững cuối có thể là nextId = 201
  - đọc lại 201..300 (không coi chunk lỗi đã hoàn thành)
~~~

Nếu reader là stateful nhưng không lưu checkpoint, restart có thể đọc lại từ đầu hoặc cần logic phục hồi riêng. Nếu input thay đổi trong thời gian dừng, checkpoint dựa trên **vị trí** có thể không còn chỉ tới cùng dữ liệu. Vì vậy cần snapshot, manifest, watermark hoặc stable sort key khi công việc yêu cầu tính nhất quán cao.

### Transaction giữa metadata và đích dữ liệu

Không được mặc định rằng `JobRepository` và hệ thống đích luôn dùng **cùng transaction**:

- Nếu metadata và business write tham gia cùng transaction có tính atomic phù hợp, chunk rollback có thể trả cả tiến độ và dữ liệu chưa commit về trạng thái trước đó.
- Nếu worker ghi sang **datasource khác** không cùng transaction, checkpoint có thể khác trạng thái ghi nghiệp vụ khi lỗi xảy ra.
- Nếu writer gọi HTTP, gửi message hoặc email, side effect ở bên nhận thường **không** rollback theo transaction database của Batch.

Do đó, **Step ExecutionContext không tự cung cấp exactly-once processing/effect**. Cần unique business key, idempotency key, transaction/outbox hoặc đối soát tùy yêu cầu.

## 5. Ví dụ: dùng ItemStream để lưu checkpoint vào Step Context

Khi tự viết một reader có state, cách chuẩn là triển khai `ItemStream` để framework biết **open/update/close**. Ví dụ đơn giản dưới đây tạo một reader trả về ID tăng dần trong một range, giúp nhìn rõ checkpoint; nó không thực hiện truy vấn database.

~~~java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public final class RangeIdReader implements ItemStreamReader<Long> {
    private static final String NEXT_ID_KEY = "rangeIdReader.nextId";

    private final long startInclusive;
    private final long endExclusive;
    private long nextId;

    public RangeIdReader(long startInclusive, long endExclusive) {
        if (startInclusive >= endExclusive) {
            throw new IllegalArgumentException("Khoảng ID phải không rỗng");
        }
        this.startInclusive = startInclusive;
        this.endExclusive = endExclusive;
    }

    @Override
    public void open(ExecutionContext context) {
        nextId = context.containsKey(NEXT_ID_KEY)
                ? context.getLong(NEXT_ID_KEY)
                : startInclusive;
        if (nextId < startInclusive || nextId > endExclusive) {
            throw new IllegalStateException("Checkpoint nằm ngoài range");
        }
    }

    @Override
    public Long read() {
        if (nextId >= endExclusive) {
            return null; // Hết dữ liệu theo hợp đồng ItemReader.
        }
        return nextId++;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(NEXT_ID_KEY, nextId);
    }

    @Override
    public void close() {
        // Không có resource cần đóng trong ví dụ.
    }
}
~~~

Vòng đời cần hiểu:

1. `open()` đọc checkpoint đã lưu hoặc bắt đầu từ `startInclusive`.
2. `read()` trả item và cập nhật vị trí **trong RAM của reader instance**.
3. `update()` chép vị trí vào `ExecutionContext`; framework lưu state phù hợp với chu kỳ commit.
4. Khi chunk rollback và worker cần restart, vị trí bền vững cuối cùng mới là cơ sở khôi phục.

**Ràng buộc của mẫu này:** Khi nhiều reader `RangeIdReader` cùng tồn tại trong **một StepExecution**, chúng phải dùng tên key checkpoint khác nhau để tránh đè state. Khi chạy **mỗi partition là một StepExecution riêng**, cùng `NEXT_ID_KEY` có thể tồn tại trong các context riêng biệt. Reader có state như trên **không thread-safe** nếu nhiều thread cùng gọi `read()` trên *cùng instance*.

Với database hoặc file thật, ưu tiên dùng reader có sẵn của Spring Batch như `JdbcPagingItemReader`, `FlatFileItemReader` và kiểm tra tùy chọn checkpoint/`saveState` của từng implementation. Mã custom chỉ minh họa hợp đồng `ItemStream`.

## 6. Lấy giá trị Step Context với @StepScope

`@StepScope` tạo một **target bean theo `StepExecution`**. Khi manager tạo các worker partition, mỗi worker có thể được cấp `minIdInclusive`/`maxIdExclusive` khác nhau và dùng **cùng một cấu hình reader**.

Ví dụ Spring Batch 5.x với một reader JDBC được bind theo range:

~~~java
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcPagingItemReader;
import org.springframework.batch.item.database.Order;
import org.springframework.batch.item.database.builder.JdbcPagingItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

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
            .rowMapper((rs, rowNum) ->
                    new OrderRow(
                            rs.getLong("id"),
                            rs.getString("order_code")))
            .pageSize(500)
            .saveState(true)
            .build();
}
~~~

`OrderRow` là record/POJO nghiệp vụ của ứng dụng; cần khai báo/import tương ứng. `orders.id` được giả định là **sort key duy nhất, ổn định** để paging và restart có ý nghĩa. Câu SQL và tên cột là ví dụ, không phải bảng metadata của Batch.

**Điểm then chốt:**

- `stepExecutionContext['minIdInclusive']` và `['maxIdExclusive']` được resolve khi **step scope của worker** hoạt động.
- Reader không dựa vào một field singleton `currentMinId` có thể bị worker khác sửa.
- Tên reader `ordersReader` có thể giống nhau giữa các worker vì `ExecutionContext` của từng `StepExecution` riêng biệt.
- Trả về kiểu `JdbcPagingItemReader<OrderRow>` giúp scoped proxy thể hiện rõ các giao diện cần thiết, gồm lifecycle `ItemStream`.
- `saveState(true)` cho phép reader lưu state phù hợp. Cần test restart, không chỉ test chạy thành công lần đầu.

### Step scope không phải thread scope

Nếu bạn gắn `TaskExecutor` vào **chính worker chunk step** để nhiều thread xử lý chunk trong cùng `StepExecution`, các thread đó có thể dùng chung **một target `@StepScope`** và **một ExecutionContext**. Đừng suy rằng có scope là reader stateful tự thread-safe. Với multi-threaded step, phải đánh giá concurrency của reader/writer và thiết kế checkpoint riêng.

## 7. ExecutionContext trong partitioning

Ở mô hình partitioning, `Partitioner.partition(gridSize)` trả `Map<String, ExecutionContext>`. Mỗi entry định danh một phần việc và cung cấp context đầu vào của nó.

~~~java
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public class OrderPartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        // Kế hoạch cố định cho ví dụ: 4 partition, ID từ 1 đến 100000.
        for (int index = 0; index < 4; index++) {
            long min = 1L + index * 25_000L;
            long maxExclusive = min + 25_000L;

            String key = String.format(Locale.ROOT, "range-%04d", index);
            ExecutionContext context = new ExecutionContext();
            context.putLong("minIdInclusive", min);
            context.putLong("maxIdExclusive", maxExclusive);
            context.putString("sourceVersion", "snapshot-2026-11-26");

            if (result.putIfAbsent(key, context) != null) {
                throw new IllegalStateException("Trùng partition key: " + key);
            }
        }
        return result;
    }
}
~~~

Mã cố định các biên để tập trung vào cách context được giao. Ở production, phải tạo và **lưu kế hoạch phân vùng ổn định** theo `JobInstance`; không đổi một key cũ sang phạm vi khác khi restart.

| Thành phần | Trách nhiệm đối với context |
| --- | --- |
| `Partitioner` | Tạo context **khởi đầu** của mỗi partition |
| `StepExecutionSplitter` | Tạo/chọn worker executions dựa trên kế hoạch và lịch sử trong repository |
| `PartitionHandler` | Điều phối worker tại chỗ hoặc từ xa; không tự sửa dữ liệu partition |
| Worker `ItemStream` | Đọc checkpoint đã lưu và cập nhật state trước commit |
| `JobRepository` | Lưu execution metadata và serialized context phục vụ restart |

### Hai bất biến quan trọng

**Một: phạm vi dữ liệu không giao nhau và bao phủ đầy đủ.** Tên partition `range-0000`, `range-0001` khác nhau chưa đủ nếu reader của cả hai cùng đọc `SELECT * FROM orders`. Reader phải dùng đúng predicate `id >= :minId AND id < :maxId`.

**Hai: tên partition → phạm vi dữ liệu ổn định khi restart.** Một worker đã checkpoint ở ID 39.000 cho `range-0001` không thể an toàn tiếp tục nếu lần sau chính key đó đại diện `[40001, 80001)`.

## 8. Step Context và restart cùng JobInstance

Ví dụ một job có 4 partition, trong đó A và C `COMPLETED`; B `FAILED` sau khi commit một phần, D `STOPPED`.

~~~mermaid
sequenceDiagram
    participant M as Manager/PartitionHandler
    participant S as StepExecutionSplitter
    participant J as JobRepository
    participant W as Worker partition B
    M->>S: Restart cùng JobInstance
    S->>J: Đọc worker history / ExecutionContext
    J-->>S: A,C COMPLETED; B FAILED; D STOPPED
    S-->>M: Các worker execution cần chạy
    M->>W: Thực thi lại B khi được chọn
    W->>J: open(checkpoint của B)
    W->>W: Tiếp tục hoặc replay theo reader
    W->>J: update(context) và status
~~~

Trên restart, `JobExecution` và worker `StepExecution` được tạo mới khi cần; **ID của lần thực thi có thể khác**, nhưng partition key và input logic cần giữ nguyên. Spring Batch thường bỏ qua các partition đã `COMPLETED` theo chính sách restart thông thường, đồng thời xét những partition chưa hoàn tất. Quyết định cụ thể còn tùy `BatchStatus`, `allowStartIfComplete` và cấu hình job.

**Không nhầm restart với JobInstance mới:** Nếu đổi identifying `JobParameters`, Spring Batch thường tạo một `JobInstance` khác. Context/checkpoint của job cũ không tự được tái sử dụng như một lần restart, dù nguồn đầu vào trùng nhau. Nếu muốn reprocess, cần chính sách idempotency/đối soát.

### Vì sao không nên lưu “last processed ID” tùy tiện?

Nếu reader đọc các bản ghi không theo ID tăng dần, nhưng worker lại ghi `lastProcessedId` vào context dựa trên **item được xử lý gần nhất**, một chunk có thể hoàn tất out-of-order, đặc biệt khi dùng nhiều thread. Dùng ID lớn nhất để restart theo `WHERE id > lastProcessedId` khi chưa có bảo đảm về thứ tự commit có thể **bỏ sót item**.

Chỉ thiết kế checkpoint theo cách có thể chứng minh:

- Thứ tự dữ liệu ổn định, có unique sort key.
- Vị trí được lưu tương ứng với **phần đã commit**, không chỉ phần đã đọc trong RAM.
- Retry/skip/filter được xử lý đúng theo hợp đồng reader.
- Reader và checkpoint phù hợp với mô hình một thread hay nhiều thread thực tế.

## 9. Metadata của Step ExecutionContext trong JobRepository

Trong schema database **mặc định** của Spring Batch:

| Bảng | Nội dung |
| --- | --- |
| `BATCH_JOB_INSTANCE` | Định danh `JobInstance` |
| `BATCH_JOB_EXECUTION` | Các lần chạy/restart của job |
| `BATCH_STEP_EXECUTION` | Mỗi manager/worker `StepExecution`: ID, status, read/write/skip/rollback counters |
| `BATCH_STEP_EXECUTION_CONTEXT` | Serialized `ExecutionContext` **riêng theo `STEP_EXECUTION_ID`** |
| `BATCH_JOB_EXECUTION_CONTEXT` | Context cấp job, không phải context của từng worker |

Tra metadata theo một `JobExecution`:

~~~sql
SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.ROLLBACK_COUNT,
    ec.SHORT_CONTEXT
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_STEP_EXECUTION_CONTEXT ec
  ON ec.STEP_EXECUTION_ID = se.STEP_EXECUTION_ID
WHERE se.JOB_EXECUTION_ID = :jobExecutionId
ORDER BY se.STEP_EXECUTION_ID;
~~~

Lưu ý:

- Tên bảng phụ thuộc table prefix; mặc định chỉ được sử dụng nếu repository dùng schema mặc định.
- `SHORT_CONTEXT` và `SERIALIZED_CONTEXT` được tạo bằng **serializer của repository**. Không giả định các cột luôn là JSON thuần hoặc có thể chỉnh sửa thủ công.
- Query trả cả manager execution nếu nó có trong `JobExecution`; không gộp nhầm với các worker.
- `JobExplorer` là API chỉ đọc được khuyến nghị khi ứng dụng muốn tra lịch sử/metadata mà không tự phụ thuộc định dạng SQL.

**Tránh sửa `ExecutionContext`/`STATUS` trực tiếp bằng SQL để “ép” job tiếp tục.** Điều đó có thể phá versioning, tính nhất quán checkpoint và cơ chế restart. Nếu đổi serializer/schema hoặc nâng cấp Spring Batch, cần kiểm thử khả năng đọc lại metadata của các job chưa hoàn tất trước khi rollout.

## 10. Job Context và Step Context: chuyển dữ liệu giữa các step

Ví dụ job có bước 1 xác định watermark, bước 2 nhập dữ liệu theo watermark đó. Nếu cần chuyển một giá trị nhỏ từ step trước sang step sau, có thể dùng `ExecutionContextPromotionListener` hoặc chuyển vào job context theo cơ chế có kiểm soát.

~~~java
// Minh họa: cấu hình listener để promote một key lên JobExecutionContext.
@Bean
ExecutionContextPromotionListener watermarkPromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[]{"acceptedWatermark"});
    return listener;
}
~~~

Listener được đăng ký trên **step tạo ra giá trị**, còn step sau có thể bind `#{jobExecutionContext['acceptedWatermark']}`. Giá trị nên được ghi vào Step ExecutionContext trước thời điểm promotion, và cách promote theo `ExitStatus`/policy cần được kiểm chứng trên job thật.

**Không promote vô tội vạ từ nhiều partition cùng một key.** Nếu worker A và B đều có `acceptedWatermark` nhưng giá trị khác nhau, việc đẩy chúng lên **một job context dùng chung** có nguy cơ mâu thuẫn dữ liệu, nhất là khi các worker hoàn tất khác thứ tự. Thay vì mỗi worker tùy tiện ghi cùng key ở cấp job, manager nên **tổng hợp kết quả một cách xác định** (ví dụ watermark an toàn là min/max theo quy tắc nghiệp vụ) sau khi thu đủ worker executions.

## 11. Thiết kế dữ liệu context an toàn và hiệu quả

### Nên lưu gì?

| Nên lưu | Không nên lưu |
| --- | --- |
| ID file/partition, range ID, snapshot version | Toàn bộ dữ liệu file hoặc một danh sách hàng triệu item |
| Offset/index/checkpoint nhỏ và có kiểu rõ ràng | `DataSource`, cursor, HTTP client, socket, stream đang mở |
| Watermark và state đủ để phục hồi | Mật khẩu, token, dữ liệu nhạy cảm không cần thiết |
| Các số đếm/lũy kế nhỏ thực sự cần restart | Cache mutable chia sẻ không có phân vùng |
| Giá trị tương thích serializer của ứng dụng | Object phức tạp không ổn định giữa các phiên bản deploy |

**Mẫu đặt key:** sử dụng tên có namespace như `ordersReader.nextId`, `invoiceWriter.lastBatchId` để tránh va chạm với component khác cùng một step. Một key nên có mục đích rõ ràng, ý nghĩa ổn định và được thay đổi có kiểm soát khi nâng cấp.

### Serialization và tương thích phiên bản

`JobRepository` lưu context bằng serializer đã cấu hình. Vì vậy:

1. Ưu tiên primitive/string và giá trị nhỏ; nếu lưu custom object phải hiểu rõ format và khả năng khôi phục.
2. Không mặc định một phiên bản class/serializer mới đọc được state do phiên bản cũ ghi.
3. Duy trì khả năng restart của job đang dở trong kế hoạch nâng cấp; kiểm tra migration trước khi thay đổi kiểu dữ liệu/key.
4. Giới hạn kích thước context: context lớn làm tăng overhead cập nhật metadata ở nhiều chunk/partition.
5. Không ghi toàn bộ context ra log hoặc dashboard nếu có dữ liệu nội bộ cần bảo vệ.

## 12. Concurrency: context riêng chưa đủ bảo đảm thread safety

### Partitioning: mỗi worker một context

Khi manager chia dữ liệu thành nhiều worker `StepExecution`, mỗi worker có context riêng. Reader `@StepScope` nhận range riêng giúp giảm nguy cơ **cross-talk** khi các worker cùng chạy trong một JVM.

Tuy nhiên:

- Một **singleton processor** có mutable field `currentTenant` vẫn có thể bị nhiều worker cùng sửa.
- Hai worker có context khác nhau nhưng SQL predicate trùng vẫn đọc cùng dữ liệu.
- Writer của nhiều worker vẫn có thể cạnh tranh cùng bảng/aggregate/unique constraint.

### Multi-threaded step: nhiều thread cùng StepExecution

Trong mô hình **multi-threaded step** (nhiều chunk thread của **một** `StepExecution`), các thread thường dùng chung `ExecutionContext` và target `@StepScope`. `ExecutionContext` không được thiết kế như một bộ đếm concurrent tổng quát cho việc gọi `putLong` từ nhiều thread mà không kiểm soát. Nếu hai thread cùng đọc–sửa–ghi cùng key, có thể mất cập nhật; checkpoint theo thứ tự không bảo đảm an toàn.

Không sửa race bằng cách mỗi thread tự lưu “last item seen” vào cùng một key. Cần chọn kiến trúc nhất quán (partitioning để tách StepExecution; reader thread-safe/synchronized khi thật sự phù hợp; hoặc checkpoint theo cơ chế được hỗ trợ).

### Remote partitioning: khác JVM

Remote worker thường dùng chung `JobRepository` để đọc/cập nhật metadata tương ứng. Mỗi worker xử lý context theo đúng `StepExecution` được điều phối. Nhưng khi broker gửi lại request hoặc worker cũ chưa thật sự dừng, có nguy cơ **hai tiến trình cố thực hiện cùng partition**; context riêng không phải distributed lock hay bằng chứng side effect chưa xảy ra.

Cần kiểm soát lifecycle worker/ack/retry và đảm bảo idempotency tại hệ thống đích, đặc biệt với API hoặc message không cùng transaction với metadata.

## 13. Kiểm thử Step ExecutionContext

### 13.1. Unit test vòng đời ItemStream

Với `RangeIdReader` ở phần 5, không cần database để kiểm tra checkpoint:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class RangeIdReaderTest {

    @Test
    void tiepTucTuCheckpointDaLuu() throws Exception {
        ExecutionContext saved = new ExecutionContext();
        RangeIdReader first = new RangeIdReader(1, 6);
        first.open(saved);

        assertEquals(Long.valueOf(1L), first.read());
        assertEquals(Long.valueOf(2L), first.read());
        first.update(saved); // Giả lập state được ghi ở commit boundary.
        first.close();

        RangeIdReader restarted = new RangeIdReader(1, 6);
        restarted.open(saved);
        assertEquals(Long.valueOf(3L), restarted.read());
        restarted.close();
    }
}
~~~

Trong test này, `saved` mô phỏng context đã ghi bền vững; đây **chưa** là integration test transaction/`JobRepository`. Ngoài ca thành công, nên thử missing key, checkpoint ngoài range, input thay đổi và khi reader được tạo lại theo tên khác.

### 13.2. Test late binding theo StepExecution

Với Spring Batch Test, `StepScopeTestUtils.doInStepScope(...)` giúp gọi logic dưới một `StepExecution` giả lập:

~~~java
JobExecution job = new JobExecution(42L);

StepExecution workerA =
        new StepExecution("ordersWorker:range-0000", job, 101L);
workerA.getExecutionContext().putLong("minIdInclusive", 1L);
workerA.getExecutionContext().putLong("maxIdExclusive", 101L);

StepExecution workerB =
        new StepExecution("ordersWorker:range-0001", job, 102L);
workerB.getExecutionContext().putLong("minIdInclusive", 101L);
workerB.getExecutionContext().putLong("maxIdExclusive", 201L);

// Giả định workerScopedProbe là bean @StepScope trong Spring test context,
// đã inject dưới dạng scoped proxy.
Long aStart = StepScopeTestUtils.doInStepScope(
        workerA, () -> workerScopedProbe.getMinId());
Long bStart = StepScopeTestUtils.doInStepScope(
        workerB, () -> workerScopedProbe.getMinId());

assertEquals(1L, aStart);
assertEquals(101L, bStart);
~~~

Ví dụ là **đoạn test tích hợp với bean có sẵn**, không phải class hoàn chỉnh có thể chạy độc lập; cần JUnit, `spring-batch-test` và `@StepScope` probe phù hợp. Mục tiêu là xác minh bean nhận đúng context theo worker, không phụ thuộc singleton mutable.

### 13.3. Integration test restart trên JobRepository thật

| Kịch bản | Kết quả cần kiểm tra |
| --- | --- |
| Một worker fail sau vài chunk commit | Context lưu checkpoint hợp lệ; chunk lỗi có thể được xử lý lại |
| Hai worker có key khác nhau | Context/checkpoint không đè lẫn nhau |
| Restart cùng JobInstance | Partition `COMPLETED` thường không chạy lại; partition lỗi được xử lý theo policy |
| Thay key/range của partition | Test phải phát hiện kế hoạch không khớp, tránh reuse checkpoint sai |
| Reader/writer dùng resource ngoài transaction | Dedupe/idempotency tránh side effect trùng dù checkpoint chưa lưu |
| Nhiều thread trong cùng step | Không mất cập nhật/race trên context; hoặc không dùng chiến lược checkpoint không an toàn |
| Thay serializer sau nâng cấp | Context cũ vẫn được đọc hoặc migration có kế hoạch |
| Hàng đợi/broker phát lại request remote | Không tạo tác dụng phụ trùng/worker chồng nhau không kiểm soát |

Integration test cần `JobRepository` và transaction thật hoặc tương đương gần production, không chỉ mocked map. Ngoài việc assert `BatchStatus`, phải đối soát **business key đầu vào/đầu ra** và số hàng thật sự thay đổi.

## 14. Runbook khi nghi ngờ Step Context bị sai

Nếu một partition restart sai vị trí hoặc job báo `COMPLETED` nhưng mất dữ liệu:

1. **Xác định identity:** Ghi lại `JobInstance`, `JobExecution`, `StepExecutionId`, step/partition name, identifying parameters và input snapshot/version.
2. **Đọc lịch sử metadata:** Kiểm tra `BATCH_STEP_EXECUTION` và `BATCH_STEP_EXECUTION_CONTEXT` hoặc dùng `JobExplorer`; không tự sửa serialized context.
3. **Đối chiếu partition plan:** Key → range/file có còn đúng như lượt đầu không? Có thay đổi `gridSize`, sort key hoặc câu SQL không?
4. **Kiểm tra ItemStream:** Reader có `open/update/close` và `saveState` đúng? Key checkpoint có va chạm với reader khác không?
5. **Kiểm tra transaction:** Metadata và dữ liệu đích có commit/rollback cùng cơ chế phù hợp không? Có side effect ngoài transaction không?
6. **Kiểm tra concurrency:** Reader/processor có mutable singleton, shared cursor, `ThreadLocal` không cleanup hoặc nhiều chunk thread cùng ghi một key không?
7. **Đối soát nghiệp vụ:** So sánh tập business key nguồn–đích, duplicate/no-op, skip/filter, tổng tiền/checksum khi cần.
8. **Khôi phục có kiểm soát:** Dùng restart API/policy được hỗ trợ, giữ partition identity và kế hoạch nguồn; nếu phải reprocess, tạo kế hoạch mới và bảo đảm idempotency.

### Các metric và cảnh báo nên có

| Metric/Quan sát | Mục tiêu |
| --- | --- |
| `readCount`, `writeCount`, skip/rollback theo worker | Xem tiến độ và phát hiện lỗi, nhưng không thay thế đối soát |
| Thời gian commit/context persistence | Tìm bottleneck ở repository hoặc transaction |
| Số partition `FAILED` / `STOPPED` / `COMPLETED` | Xác định phạm vi restart |
| Kích thước serialized context, thời gian lưu metadata | Ngăn context quá lớn, metadata DB bão hòa |
| Partition key, input range, checkpoint version trong log có kiểm soát | Điều tra restart sai phạm vi |
| Số unique business key và duplicate/no-op tại đích | Phát hiện mất/trùng dữ liệu dù counters trông hợp lý |

## 15. Câu hỏi tự kiểm tra

**Tình huống:** Job nhập 1 triệu đơn hàng bằng 8 partition. Worker `range-0003` có context `minId=375001`, `maxIdExclusive=500001` và checkpoint tới ID 410.000 sau một số chunk đã commit. Job lỗi vì database timeout. Khi restart, kỹ sư đổi `gridSize` từ 8 xuống 4 nhưng giữ tên `range-0003`; đồng thời writer gửi API mà không có idempotency key.

Hãy trả lời:

1. Vì sao checkpoint của `range-0003` có nguy cơ không còn hợp lệ?
2. `@StepScope` có tự bảo đảm dữ liệu không trùng hay không?
3. Nếu API đã nhận thành công nhưng worker rollback trước khi lưu checkpoint, điều gì xảy ra khi retry?
4. Nên kiểm thử và vận hành thế nào để khôi phục an toàn?

**Định hướng trả lời:** Khi kế hoạch key → input thay đổi, checkpoint cũ có thể nằm trong miền dữ liệu khác và gây thiếu/trùng item. `@StepScope` chỉ tách target bean theo `StepExecution`; không bảo đảm range không giao nhau hoặc side effect exactly-once. API không idempotent có thể nhận lệnh lặp khi retry/replay. Cần giữ partition plan/snapshot theo JobInstance, kiểm tra transaction và checkpoint, dùng idempotency key ở đích và đối soát business key sau restart.

## Tài liệu tham khảo

- [Spring Batch Reference — ExecutionContext](https://docs.spring.io/spring-batch/reference/domain.html#executioncontext): vai trò state và vòng đời Step/Job context.
- [Spring Batch API — ExecutionContext](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/item/ExecutionContext.html): API key–value và dirty flag.
- [Spring Batch API — ItemStream](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/item/ItemStream.html): `open`, `update`, `close` và checkpoint.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): restart và persistent state.
- [Spring Batch Reference — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope`, `stepExecutionContext` và `@Value`.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_STEP_EXECUTION_CONTEXT` và bảng liên quan.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, concurrency, remote workers.

> **Ghi nhớ:** Step `ExecutionContext` là **trạng thái bền vững của một `StepExecution`**, không phải biến singleton hay kho dữ liệu nghiệp vụ. Trong partitioning, nó giữ ranh giới và checkpoint **riêng cho từng worker**; để restart chính xác, còn cần identity ổn định, transaction/`ItemStream` phù hợp, thread safety và idempotency của kết quả ghi.
