# Worker stateless theo partition trong Spring Batch

## 1. Bối cảnh và mục tiêu

Khi một Spring Batch Job phải xử lý hàng triệu đến hàng trăm triệu bản ghi, một Step đơn luồng có thể không đáp ứng thời hạn xử lý. **Partitioning** cho phép chia tập dữ liệu thành nhiều phần độc lập; mỗi phần được thực thi bởi một **worker Step**. Worker có thể chạy trong cùng JVM với manager hoặc trên nhiều tiến trình/máy khác nhau theo mô hình remote partitioning.

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, thiết kế worker stateless theo partition là nền tảng để mở rộng workload dữ liệu lớn mà vẫn kiểm soát thread safety, retry/restart, tính đúng đắn và chi phí vận hành. Câu hỏi cốt lõi là: **Nếu một worker bị dừng giữa chừng và partition được giao cho worker khác, liệu Job có tiếp tục đúng mà không cần dữ liệu chỉ tồn tại trong bộ nhớ của worker cũ?**

Một worker được xem là **stateless ở cấp tiến trình** khi:

- Worker không giữ trạng thái nghiệp vụ hoặc tiến độ bắt buộc phải tồn tại sau khi tiến trình chết trong biến instance, biến static, cache cục bộ hay file tạm chỉ máy đó đọc được.
- Mọi partition có **định danh ổn định** và **đầu vào xác định được**; cấu hình/ngữ cảnh cần thiết lấy từ nguồn bền vững hoặc thông điệp có thể phục hồi.
- Kết quả đã commit và checkpoint được lưu ở kho trạng thái bền vững; xử lý lại sau lỗi không tạo ra tác dụng phụ sai.
- Bất kỳ instance worker tương thích nào cũng có thể nhận một partition phù hợp, không phụ thuộc worker từng xử lý nó trước đó.

**Stateless không đồng nghĩa với không có biến cục bộ.** Trong lúc xử lý một chunk, ItemReader, ItemProcessor hoặc ItemWriter có thể có cursor, buffer, connection và bộ đếm tạm. Điều quan trọng là **không cần phục hồi các giá trị này từ RAM riêng của worker cũ**. Trạng thái phải lưu sau restart, nếu có, cần được checkpoint và quản lý theo StepExecution/ExecutionContext hoặc qua kho dữ liệu bền vững thích hợp.

Sau bài này, bạn có thể thiết kế ranh giới partition, tạo worker Step độc lập, quản lý trạng thái và checkpoint, phân tích các trường hợp lỗi và xác định khi nào có thể tăng số worker an toàn.

## 2. Worker nằm ở đâu trong kiến trúc partitioning?

### 2.1. Vai trò manager, partitioner và worker

| Thành phần | Trách nhiệm | Điều không nên làm |
|---|---|---|
| Manager Step | Khởi tạo/điều phối các partition, theo dõi kết quả và trạng thái tổng thể | Chứa toàn bộ dữ liệu cần xử lý của mọi partition trong RAM |
| Partitioner | Xác định tập partition, khóa tên và dữ liệu mô tả phạm vi | Sinh phạm vi chồng lấn không có cơ chế khử trùng lặp |
| PartitionHandler | Quyết định cách thực thi/gửi StepExecution cho worker | Tự suy luận kết quả thành công khi chưa có xác nhận bền vững |
| Worker Step | Đọc, xử lý, ghi dữ liệu thuộc partition được giao | Dựa vào biến global hoặc file tạm của một worker khác |
| JobRepository | Ghi thông tin JobExecution, StepExecution và ExecutionContext phục vụ giám sát/restart | Bị coi là cache tùy ý có thể mất dữ liệu |
| Broker (nếu remote) | Chuyển yêu cầu/kết quả giữa manager và worker | Được giả định bảo đảm exactly-once cho toàn bộ nghiệp vụ |

~~~mermaid
flowchart TB
    J[Job / Manager Step] --> P[Partitioner tạo phạm vi]
    P --> S[StepExecution và ExecutionContext]
    S --> R[(JobRepository)]
    S --> H[PartitionHandler]
    H --> Q[Thực thi local hoặc broker remote]
    Q --> W1[Worker A]
    Q --> W2[Worker B]
    Q --> W3[Worker C]
    W1 --> DB[(Dữ liệu nghiệp vụ)]
    W2 --> DB
    W3 --> DB
    W1 -. checkpoint và trạng thái .-> R
    W2 -. checkpoint và trạng thái .-> R
    W3 -. checkpoint và trạng thái .-> R
~~~

Ở **local partitioning**, nhiều StepExecution chạy song song trong một JVM thông qua TaskExecutor/PartitionHandler. Ở **remote partitioning**, manager gửi yêu cầu xử lý tới worker trên các tiến trình khác; worker thường truy cập JobRepository chung và dữ liệu nghiệp vụ theo kiến trúc Spring Batch được cấu hình. Cả hai đều cần tách trạng thái **theo partition**, vì cùng một JVM cũng có thể xử lý nhiều partition đồng thời.

Phân biệt với **remote chunking**: trong remote chunking, manager thường đọc dữ liệu và gửi các chunk cho worker xử lý/ghi; còn trong remote partitioning, **mỗi worker tự thực hiện Step đối với phần dữ liệu được giao**, thường bao gồm cả đọc, xử lý và ghi.

### 2.2. Phạm vi của một partition

Một partition không phải một worker cố định. Partition là **đơn vị công việc logic** có tên và ExecutionContext riêng. Ví dụ:

~~~text
JobExecution #317
  managerStep
    workerStep:range-0000 -> id [0, 250000)
    workerStep:range-0001 -> id [250000, 500000)
    workerStep:range-0002 -> id [500000, 750000)
    workerStep:range-0003 -> id [750000, 1000000)
~~~

Tên partition **range-0000** và ranh giới khóa phải tiếp tục chỉ cùng một phạm vi đối với lần restart của JobExecution/JobInstance liên quan. Lúc đầu range-0000 có thể chạy ở Worker A; khi A hỏng, một tiến trình worker khác phải có thể nhận lại nó theo cơ chế restart của hệ thống.

Không nên đồng nhất **partition number**, **worker instance ID**, **thread ID** và **JobExecution ID**. Chúng phục vụ các mục đích khác nhau: partition ID diễn tả phần việc, worker ID diễn tả nơi thực thi ở một thời điểm, StepExecution ghi nhận một lượt thực thi, JobExecution ghi nhận lần chạy Job.

## 3. Nguyên tắc stateless theo partition

### 3.1. Tách dữ liệu nghiệp vụ khỏi trạng thái thực thi

| Loại thông tin | Ví dụ | Nơi lưu phù hợp |
|---|---|---|
| Đầu vào partition | minId, maxIdExclusive, tenantKey, shardKey, snapshot watermark | ExecutionContext của partition hoặc dữ liệu cấu hình bền vững được tham chiếu từ đó |
| Vị trí checkpoint | Số item đã đọc hợp lệ, trang/offset có thể phục hồi, trạng thái ItemStream | Step ExecutionContext trong JobRepository khi reader/writer hỗ trợ restart |
| Kết quả nghiệp vụ | Đơn hàng đã đồng bộ, bản ghi đã tính, trạng thái xuất file | Database/bucket đích bền vững; giao dịch hoặc cơ chế xác nhận thích hợp |
| Trạng thái điều phối | Step STARTED/FAILED/COMPLETED, commit/rollback count | JobRepository |
| Trạng thái tức thời | Buffer chunk, cursor JDBC, connection, thread-local tạm | RAM worker trong suốt lần xử lý; có thể tạo lại |
| Thông tin quan sát | Worker ID, host, lỗi, duration, correlation ID | Log/trace/metrics tập trung; không dùng thay checkpoint |

Điểm dễ nhầm là **StepExecution/ExecutionContext được lưu bền vững** không làm worker trở thành stateful về mặt triển khai. Worker vẫn có thể bị hủy và khởi tạo lại; runtime mới lấy ngữ cảnh partition và checkpoint từ nguồn phù hợp.

Ngược lại, chỉ đưa minId/maxId vào message chưa đủ để gọi một pipeline là stateless nếu writer lưu các bản ghi đã gửi trong cache của một pod và chỉ flush vào cuối Job.

### 3.2. Không chia sẻ trạng thái mutable giữa các partition

Một worker có thể nhận nhiều partition theo thời gian; thậm chí một instance Spring Bean singleton có thể được nhiều StepExecution gọi đồng thời. Tránh những cấu trúc như:

~~~java
// Sai: trạng thái của partition này ảnh hưởng partition khác.
@Component
class StatefulOrderProcessor implements ItemProcessor<OrderRow, OrderRow> {
    private long currentPartitionTotal = 0;

    @Override
    public OrderRow process(OrderRow item) {
        currentPartitionTotal += item.amountInCents();
        return item;
    }
}
~~~

Biến currentPartitionTotal là mutable state dùng chung nếu bean singleton được nhiều luồng gọi. Nó gây data race và không thể phục hồi sau crash.

Một processor thuần có thể biểu diễn như sau:

~~~java
@Component
class StatelessOrderProcessor implements ItemProcessor<OrderRow, PreparedOrder> {

    @Override
    public PreparedOrder process(OrderRow item) {
        return new PreparedOrder(
            item.id(),
            item.amountInCents(),
            item.amountInCents() >= 0
        );
    }
}
~~~

Mỗi lần process chỉ phụ thuộc input; việc cộng tổng/ghi kết quả cần chuyển thành bước tổng hợp có dữ liệu được lưu rõ ràng, hoặc partition lưu phần kết quả của mình tại một kho bền vững và tổng hợp sau. Nếu processor gọi dịch vụ ngoài, phải đánh giá tính lặp lại và side effect của lời gọi đó; chỉ vì processor không có field mutable không có nghĩa toàn xử lý đã idempotent.

**Quy tắc thiết kế:** mỗi StepExecution nhận **ngữ cảnh riêng**, tài nguyên stateful có vòng đời riêng, và chỉ dùng singleton cho những thành phần thực sự không giữ state thay đổi theo item/partition.

## 4. Thiết kế ranh giới partition sao cho có thể lặp lại

### 4.1. Phân vùng theo khoảng khóa

Với bảng orders có khóa id, có thể chia thành các khoảng nửa mở:

~~~sql
SELECT id, amount_in_cents
FROM orders
WHERE id >= :minId
  AND id <  :maxIdExclusive
ORDER BY id;
~~~

Khoảng nửa mở **[minId, maxIdExclusive)** giúp hai partition liền nhau không chồng lấn. Ví dụ:

~~~text
partition-000: [1, 100001)
partition-001: [100001, 200001)
partition-002: [200001, 300001)
~~~

Tuy nhiên, khoảng khóa **không tự bảo đảm tập dữ liệu bất biến**. Nếu dữ liệu nguồn bị cập nhật, thêm hoặc xóa trong lúc Job chạy, mỗi worker có thể quan sát trạng thái khác nhau. Hãy quyết định chính sách: đọc từ snapshot/replica được chốt, dùng watermark theo thời điểm, ghi nhận tập khóa đầu vào hoặc dùng cơ chế dữ liệu nguồn có tính nhất quán phù hợp.

### 4.2. Ví dụ Partitioner với phạm vi ổn định

Đoạn Java dưới đây minh họa Partitioner chia đoạn [fromInclusive, untilExclusive) thành các phần. Các giá trị biên cần đến từ tham số Job hoặc snapshot được cố định cho JobInstance; **không truy vấn MAX(id) mới mỗi lần restart** rồi lặng lẽ đổi tập dữ liệu.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public final class OrderRangePartitioner implements Partitioner {

    private final long fromInclusive;
    private final long untilExclusive;

    public OrderRangePartitioner(long fromInclusive, long untilExclusive) {
        if (fromInclusive >= untilExclusive) {
            throw new IllegalArgumentException("Empty or invalid range");
        }
        this.fromInclusive = fromInclusive;
        this.untilExclusive = untilExclusive;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long total = untilExclusive - fromInclusive;
        long size = (total + gridSize - 1) / gridSize;
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        long start = fromInclusive;
        int index = 0;
        while (start < untilExclusive) {
            long end = Math.min(untilExclusive, start + size);

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", start);
            context.putLong("maxIdExclusive", end);
            result.put("range-" + String.format("%04d", index), context);

            start = end;
            index++;
        }

        return result;
    }
}
~~~

**Giới hạn của ví dụ:** giả định dải khóa phù hợp với kiểu long và phép cộng không overflow; trong production cần xử lý cả trường hợp dải rất lớn, dataset rỗng và kiểm soát snapshot. Khi số bản ghi phân bố không đều theo khóa, chia bằng khoảng id có thể làm partition lệch tải mạnh; hãy đo số bản ghi/công việc thực tế theo miền.

Cần lưu lại **bộ partition và ranh giới ổn định** tương ứng JobInstance, đồng thời dùng tên partition có quy ước nhất quán. Đối với restart, không thay cách chia vì gridSize, số pod hay số worker được tăng giữa chừng mà chưa đánh giá ảnh hưởng lên các StepExecution đã hoàn tất và việc đọc chồng lấn.

### 4.3. Chọn khóa và kích thước partition

| Kiểu phân vùng | Phù hợp khi | Rủi ro cần kiểm tra |
|---|---|---|
| Khoảng ID | Khóa có thứ tự ổn định, truy vấn range có index | Gaps/skew, bản ghi thêm trong lúc chạy |
| Hash theo khóa nghiệp vụ | Nhiều khóa độc lập, phân bố tương đối đều | Khó quét hiệu quả nếu thiếu index/phương án lọc |
| Tenant/shard | Dữ liệu phân lập tự nhiên, kiểm soát tài nguyên theo tenant | Một tenant lớn thành straggler, nóng một shard |
| Danh sách file/object | File đầu vào độc lập, có vị trí bền vững | File quá lớn, định dạng nén khó đọc theo offset |
| Theo thời gian/snapshot | Dữ liệu có cửa sổ thời gian ổn định | Late arrivals, boundary timezone, thay đổi dữ liệu cũ |

Không phân vùng một file nén tuần tự bằng byte offset tùy ý nếu format không hỗ trợ tách an toàn. Không dùng OFFSET/LIMIT thiếu ORDER BY ổn định trên dữ liệu đang biến động làm cơ chế chia partition chính.

**Số partition logic không bắt buộc bằng số worker.** Tạo nhiều phần nhỏ hơn số worker giúp cân tải nhưng làm tăng metadata/scheduling overhead. Mục tiêu là đủ nhỏ để retry một phần khi lỗi và đủ lớn để xử lý hiệu quả.

## 5. Cấu hình worker Step tách biệt theo ExecutionContext

### 5.1. Dùng @StepScope để cấp reader riêng

Trong một worker, **StepScope** tạo bean theo vòng đời StepExecution và cho phép truy cập các giá trị của stepExecutionContext. Ví dụ dưới dùng API phổ biến của Spring Batch 5 với JDBC cursor, giới hạn dữ liệu theo khoảng id:

~~~java
import javax.sql.DataSource;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
public JdbcCursorItemReader<OrderRow> orderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxIdExclusive) {

    return new JdbcCursorItemReaderBuilder<OrderRow>()
        .name("orderReader")
        .dataSource(dataSource)
        .sql("""
            SELECT id, amount_in_cents
            FROM orders
            WHERE id >= ? AND id < ?
            ORDER BY id
            """)
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxIdExclusive);
        })
        .rowMapper((rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getLong("amount_in_cents")
        ))
        .saveState(true)
        .build();
}
~~~

Ở đây:

- Mỗi StepExecution có một bản reader riêng và đọc đúng phạm vi từ ngữ cảnh partition.
- Các tham số được bind qua PreparedStatement, tránh ghép trực tiếp giá trị động vào chuỗi SQL.
- saveState(true) cho phép reader hỗ trợ lưu thông tin cần thiết để restart thông qua cơ chế ItemStream/ExecutionContext; **không thay thế** việc xác định dữ liệu đầu vào ổn định.
- Reader dạng cursor có thể sử dụng tài nguyên kết nối lâu; phải đánh giá connection pool, fetch size và ràng buộc của driver.
- Các bean thuộc cùng StepExecution vẫn có thể bị gọi đồng thời nếu cấu hình multi-threaded step **bên trong partition**. StepScope một mình không biến ItemReader stateful thành thread-safe; chỉ thêm parallelism trong Step khi bảo đảm thread safety.

Ví dụ worker Step theo chunk:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step workerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemWriter<OrderRow> orderWriter) {

    return new StepBuilder("workerStep", jobRepository)
        .<OrderRow, OrderRow>chunk(500, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .build();
}
~~~

Đây là **các mảnh cấu hình minh họa**, cần ghép với các bean DataSource, ItemWriter, Job/Step, các record nghiệp vụ và cấu hình partitioning hoàn chỉnh. API/kích thước transaction nên được đối chiếu với phiên bản Spring Batch của dự án; không mặc định import trên áp dụng nguyên dạng cho mọi phiên bản.

### 5.2. ItemWriter phải chịu được retry/restart

Giả sử ghi đơn hàng lên database đích PostgreSQL. Một cách thường dùng để tránh bản ghi trùng là khóa duy nhất theo **business id** kết hợp upsert:

~~~sql
INSERT INTO processed_orders (order_id, amount_in_cents, source_version)
VALUES (:orderId, :amountInCents, :sourceVersion)
ON CONFLICT (order_id)
DO UPDATE SET
    amount_in_cents = EXCLUDED.amount_in_cents,
    source_version = EXCLUDED.source_version
WHERE processed_orders.source_version <= EXCLUDED.source_version;
~~~

**Không áp dụng upsert như một bảo đảm exactly-once tổng quát.** SQL trên chỉ minh họa ghi idempotent cho một dạng bản ghi có version tăng dần; còn phải kiểm tra chính sách về dữ liệu đến muộn, ghi đè và bất biến nghiệp vụ. Nếu worker vừa ghi DB vừa gọi API gửi email hoặc thanh toán, retry có thể thực hiện side effect lần thứ hai. Khi đó cần idempotency key ở dịch vụ đích, outbox/inbox pattern hoặc cơ chế giao dịch/đối soát thích hợp.

Nếu nguồn và đích ở hai database không cùng transaction, checkpoint JobRepository và kết quả nghiệp vụ có thể không commit nguyên tử. Thiết kế phải dự liệu trường hợp **kết quả đã ghi nhưng trạng thái Step chưa được xác nhận**, và xử lý lại an toàn.

### 5.3. Luồng xử lý có thể tạo lại

~~~text
1. Worker nhận tham chiếu StepExecution/partition được giao.
2. Worker lấy ngữ cảnh của partition từ nguồn đã cấu hình.
3. StepScope tạo ItemReader/ItemWriter riêng cho lượt thực thi.
4. Reader lấy dữ liệu trong phạm vi partition.
5. Chunk được xử lý và writer ghi dữ liệu; commit theo transaction.
6. ItemStream/StepExecution cập nhật checkpoint, bộ đếm và trạng thái.
7. Worker trả kết quả/thông báo cho manager theo hợp đồng điều phối.
8. Khi worker dừng, lượt thực thi lỗi được phục hồi qua cơ chế restart;
   worker khác có thể tiếp tục mà không cần RAM của worker cũ.
~~~

Các bước 5–6 có trình tự/ranh giới commit phụ thuộc transaction và repository thực tế; không được coi đây là giao thức nguyên tử đa hệ thống nếu chưa có bảo đảm giao dịch cụ thể.

## 6. Retry, restart và xử lý lỗi khi worker chết

### 6.1. Phân biệt retry của item và restart của partition

- **Retry item/chunk:** Spring Batch thử lại một thao tác thất bại tạm thời theo retry policy; có thể có backoff/skip tùy cấu hình. Retry vẫn thuộc cùng quá trình xử lý logic nhưng có thể khiến writer/processor được gọi nhiều lần.
- **Restart Step/Job:** sau khi tiến trình hoặc JobExecution thất bại, hệ thống tạo lượt thực thi tiếp theo theo cơ chế restart và dựa vào trạng thái bền vững để tiếp tục phần chưa hoàn tất.
- **Redelivery message:** broker có thể gửi lại yêu cầu chưa được xác nhận; cần tránh hai worker đồng thời xử lý cùng một partition theo cùng định danh và tránh tác dụng phụ lặp khi message được gửi lại.

Cần cấu hình launcher, JobRepository, kênh message, retry/timeout và thao tác vận hành đồng bộ. Không có một tham số “stateless=true” tự giải quyết toàn bộ các trường hợp này.

### 6.2. Các cửa sổ lỗi đáng kiểm tra

| Thời điểm xảy ra lỗi | Khả năng xảy ra | Thiết kế phục hồi |
|---|---|---|
| Trước khi worker bắt đầu | Request mất/chưa gửi hoặc pod chưa nhận | Durable request/dispatch; phát lại có kiểm soát theo StepExecution |
| Giữa chunk, trước commit | Công việc chưa commit phải làm lại | Transaction rollback; reader phục hồi từ checkpoint cũ |
| Sau commit nghiệp vụ, trước checkpoint/ack | Ghi đích đã thành công nhưng manager chưa biết | Idempotent write/dedupe; kết quả và checkpoint cần đối chiếu |
| Trong khi retry API | API có thể đã xử lý dù client timeout | Idempotency key, đối soát và backoff |
| Worker A chết sau khi giữ lock/lease | Partition bị kẹt hoặc xử lý đồng thời khi cấp lại | Timeout, ownership/fencing, quan sát lock và chính sách reclaim |
| Manager chết khi worker vẫn chạy | Trạng thái phân tán không đồng bộ tức thời | Repository bền vững, cơ chế đồng bộ kết quả khi restart |
| Một partition bị dữ liệu lỗi | Partition FAILED trong khi phần khác COMPLETED | Restart đúng partition lỗi, xác định skip/recovery policy |

Trong các hệ thống phân tán, **at-least-once delivery** là giả định an toàn để thiết kế khi không có bằng chứng bảo đảm mạnh hơn. Trên đường thực thi có thể có nhiều hệ thống (DB nguồn, DB đích, broker, JobRepository, API), nên **exactly-once nghiệp vụ phải được chứng minh bằng ranh giới transaction và idempotency**, không suy ra chỉ từ trạng thái COMPLETED hoặc một lần gửi message.

### 6.3. Điều kiện để restart đúng

1. **Đầu vào xác định:** tập dữ liệu hoặc watermark của mỗi partition vẫn mang cùng ý nghĩa khi Job được restart.
2. **Tên partition ổn định:** tránh đổi range-id hay chia lại tập partition giữa các lượt restart mà không di chuyển checkpoint có chủ đích.
3. **Reader/writer hỗ trợ restart:** kiểm tra saveState, ItemStream, sort key, thứ tự dữ liệu và khả năng tái tạo cursor.
4. **Kết quả đã commit có thể nhận diện:** khóa duy nhất, version, idempotency key hoặc bảng đối soát.
5. **Không dựa vào worker cũ:** message, checkpoint và trạng thái lỗi có thể được đọc từ kho bền vững.
6. **Có giới hạn retry:** tránh retry storm khiến database/API quá tải; phân loại lỗi tạm thời và lỗi dữ liệu vĩnh viễn.

Cần lưu ý Spring Batch thường **không tự động di chuyển một partition đang chạy giữa hai worker** giống cơ chế live migration. Khi worker chết, việc xác định và restart công việc cần được điều phối bằng JobRepository và luồng retry/restart của hệ thống. Nếu một worker mất kết nối nhưng vẫn đang xử lý, phải có cơ chế tránh hai tiến trình ghi cùng dữ liệu mà không kiểm soát.

## 7. Tính thread-safe của worker và tài nguyên liên quan

Thiết kế stateless giúp giảm phụ thuộc vào instance, nhưng **không đồng nghĩa mọi bean đều thread-safe**.

| Đối tượng | Khuyến nghị | Lỗi điển hình |
|---|---|---|
| Partition context | Mỗi partition có ExecutionContext riêng | Cùng một object mutable chứa minId/maxId cho mọi worker |
| ItemReader có cursor/page | Bean StepScope; mỗi StepExecution sở hữu reader riêng | Singleton reader bị nhiều partition đọc cùng cursor |
| ItemProcessor thuần | Singleton thường phù hợp khi không mutable state | Field cộng dồn/thay đổi kết quả giữa các thread |
| ItemWriter | Tách state; writer dùng connection/statement theo transaction | Buffer dùng chung, flush nhầm dữ liệu |
| Cache/lookup | Chỉ dùng dữ liệu bất biến hoặc cache có đồng bộ/phiên bản | Cache stale làm kết quả sai theo partition |
| Connection/DataSource | Pool được quản lý; giới hạn toàn cụm | Mỗi worker mở quá nhiều connection làm DB kiệt |
| Retry/backoff | Giới hạn tổng concurrency, thêm jitter khi cần | Retry đồng bộ gây bão request |
| File/output | Đích riêng theo partition hoặc cơ chế append/merge an toàn | Nhiều worker ghi cùng file không đồng bộ |

Nếu một worker process có thể chạy **k partition cùng lúc**, một bean StepScope giúp phân tách instance giữa các StepExecution, nhưng vẫn phải kiểm tra execution model của từng Step và library được gọi. Nếu định cấu hình thêm TaskExecutor trong chính worker Step, hãy coi đó là **một cấp song song khác** với các yêu cầu thread safety riêng.

### 7.1. Tên tài nguyên đầu ra theo partition

Với file export, nên tạo output riêng và đặt tên có tính ổn định, ví dụ:

~~~text
exports/{jobInstanceKey}/range-0000.part
exports/{jobInstanceKey}/range-0001.part
exports/{jobInstanceKey}/range-0002.part
~~~

Worker ghi vào file tạm riêng của lượt xử lý, rồi publish/rename theo cơ chế atomic của storage nếu có. Không được giả định rename trên mọi object storage đều atomic. Sau khi mọi partition thành công, một Step hợp nhất/đối soát xác nhận số lượng và nội dung rồi mới công bố bản export cuối cùng. Khi retry, định danh output tránh ghi đè kết quả hợp lệ của worker khác mà không kiểm tra ownership.

## 8. Khả năng mở rộng theo tài nguyên thực tế

Stateless cho phép thay worker dễ hơn, nhưng số worker hữu ích phụ thuộc bottleneck của cả hệ thống.

### 8.1. Phân biệt concurrency và số partition

Giả sử có 32 partition và 4 worker instance, mỗi instance xử lý 2 partition cùng lúc. Concurrency tối đa có thể khoảng **8 StepExecution**, còn 24 partition chờ. Nếu tăng số pod từ 4 lên 8 nhưng database chỉ có 12 connection cho batch, tổng 16 partition đang chạy có thể tạo nghẽn pool và không tăng throughput.

Một ước lượng ban đầu:

~~~text
concurrency = số worker instance × số partition đồng thời mỗi instance

throughput thực tế <= min(
    năng lực đọc,
    năng lực xử lý,
    năng lực ghi,
    hạn mức API/queue,
    giới hạn pool/CPU/I/O
)
~~~

Đây là cách nhìn năng lực giới hạn, không phải công thức dự báo chính xác cho mọi Job. Đo tỷ lệ tăng throughput, p95 chunk/SQL, thời gian queue, CPU/GC, lock wait, connection pending và số partition còn lại để xác định nấc scale hợp lý.

### 8.2. Cân tải và straggler

Partition theo số lượng khóa bằng nhau có thể rất khác nhau về số bản ghi và chi phí xử lý. Nếu 1 trong 32 partition cần 40 phút trong khi 31 phần còn lại chỉ 2 phút, tổng thời gian Job vẫn bị chi phối bởi partition chậm nhất.

Các cách giảm skew:

- Chia theo **khối lượng dữ liệu/công việc ước lượng**, không chỉ chiều dài dải ID.
- Tạo partition nhỏ hơn và tăng số partition logic, nhưng cân nhắc overhead metadata/broker/transaction.
- Tách tenant/file/hot key quá lớn thành các phần có ranh giới ổn định.
- Đo thời gian, records/sec và retry theo từng partition để nhìn thấy chênh lệch.

Không tự động chia lại partition đang chạy hoặc đang có checkpoint mà không xác định cách bảo toàn xử lý đúng một lần về mặt nghiệp vụ.

## 9. Quan sát và vận hành worker stateless

### 9.1. Log, metric, trace

Dữ liệu log của một worker cần đủ để trả lời **partition nào, trong Job nào, xử lý bởi instance nào, đến đâu và lỗi gì**. Nên có các trường:

~~~text
jobName, jobInstanceId, jobExecutionId,
stepExecutionId, partitionName,
workerInstanceId, attempt, status,
readCount, writeCount, skipCount, rollbackCount,
durationMs, errorType, correlationId
~~~

Không đưa item chứa dữ liệu cá nhân, secret hay payload đầy đủ vào log. **PartitionName/JobExecutionId** có thể xuất hiện trong log hoặc trace để điều tra một lượt cụ thể, nhưng tránh dùng làm tag metric phổ biến nếu gây cardinality không giới hạn.

Metric hữu ích:

- Số partition **queued, active, completed, failed, restarted**.
- Wall-clock theo partition/Step; p50/p95/p99 chunk.
- Read/write throughput, lỗi và số retry/rollback/skip.
- Worker CPU, heap/GC, concurrency đang dùng và hàng đợi nội bộ.
- Connection-pool active/idle/pending, database lock wait, query/commit latency.
- Broker queue depth, request age, redelivery count, consumer lag và thời gian ack (khi remote).

Các bộ đếm StepExecution chỉ phản ánh trạng thái mà Spring Batch đã ghi nhận; metric runtime bổ sung giúp thấy vấn đề đang diễn ra giữa các lần checkpoint.

### 9.2. Triển khai trong container

Worker có thể chạy trong pod/container tạm thời nhưng cần có:

1. Cùng phiên bản code và schema tương thích với dữ liệu partition/JobRepository.
2. Quyền truy cập hợp lệ tới database/broker/secret và endpoint đã cấu hình.
3. Graceful shutdown: ngừng nhận partition mới, hoàn tất hoặc rollback chunk đang xử lý theo giới hạn shutdown.
4. Startup/recovery rõ ràng: công việc dang dở được phát hiện và có quy trình restart, không tự ghi đè trạng thái đang chạy.
5. Giới hạn CPU, RAM, pool và concurrency theo năng lực hạ tầng; không chỉ theo số CPU node.
6. Health check phản ánh khả năng tiếp nhận công việc; không lấy việc API health còn mở làm bằng chứng Job vẫn tiến triển.

Nếu JobRepository dùng database chung, tính khả dụng và hiệu năng của database metadata trở thành một yếu tố phải giám sát. Với remote partitioning qua broker, cần cấu hình timeout, durability, ack/redelivery và tương thích cấu trúc message theo hạ tầng đang dùng. **Việc triển khai qua queue không tự tạo cơ chế restart hoàn chỉnh**; các điều kiện failover phải được thử end-to-end.

## 10. Các anti-pattern cần tránh

| Anti-pattern | Vì sao không an toàn | Hướng sửa |
|---|---|---|
| Worker lưu vị trí đọc trong biến static | Crash làm mất checkpoint, nhiều partition tranh state | ItemStream/StepExecutionContext bền vững theo partition |
| Tên partition phụ thuộc số pod đang chạy | Restart có thể ánh xạ sai dữ liệu đã hoàn tất | Partition key và biên dữ liệu ổn định theo JobInstance |
| Singleton JdbcCursorItemReader dùng chung | Cursor/position có state và không mặc nhiên thread-safe | Reader StepScope riêng cho StepExecution |
| Nhiều worker cùng xử lý một miền khóa | Duplicate/lock contention, kết quả khó đối soát | Partition không chồng lấn, fencing và idempotency |
| Ack message trước khi công việc bền vững | Request bị mất nếu worker crash | Hợp đồng ack sau hoàn tất và cơ chế recovery |
| Coi redelivery là nguyên nhân duy nhất gây duplicate | Retry sau commit và API timeout cũng tạo side effect lặp | Dedupe/idempotency tại ranh giới nghiệp vụ |
| Chỉ tăng pod khi Job chậm | Database/API/connection pool bị nghẽn nặng hơn | Baseline, đo bottleneck, tăng concurrency từng nấc |
| Chia 1 partition quá lớn | Một straggler giữ toàn Job, retry rất tốn | Dải nhỏ hơn, cân skew và giới hạn metadata |
| Chia quá nhiều partition rất nhỏ | Overhead quản lý cao, lock/connection churn | Chọn granularity theo benchmark |
| Lưu file kết quả vào ổ local duy nhất | Worker khác không thể tiếp tục, dữ liệu mất khi pod bị xóa | Shared durable storage hoặc publish cuối bước |
| Không thử crash sau commit | Dữ liệu trùng hoặc trạng thái Step sai khi restart | Fault injection ở các cửa sổ lỗi và đối soát dữ liệu |

## 11. Bài toán thực hành: đồng bộ đơn hàng theo partition

**Tình huống:** Mỗi đêm, cần đọc 4 triệu bản ghi orders và ghi sang kho dữ liệu phân tích trước 06:00. Hệ thống có 3–8 worker replica, mỗi worker xử lý được tối đa 2 partition đồng thời. Source và sink là hai database khác nhau, nên không có một transaction bao trùm mọi thao tác.

**Thiết kế đề xuất để kiểm chứng:**

1. Lúc bắt đầu Job, chốt một **snapshot watermark** cùng phạm vi ID tối thiểu/tối đa; ghi định danh snapshot bằng JobParameter hoặc kho bền vững gắn JobInstance.
2. Tạo khoảng ID nửa mở, dùng tên partition range-0000, range-0001... và giữ ổn định qua restart. Lấy mẫu phân bố để tránh một dải có quá nhiều bản ghi.
3. Worker Step nhận minId/maxIdExclusive từ ExecutionContext; reader StepScope đọc chỉ dữ liệu thuộc phạm vi và snapshot đã chốt.
4. Processor thuần biến đổi dữ liệu. Writer ghi theo business key ổn định, hỗ trợ thao tác lặp lại không làm tăng số record sai.
5. Dùng JobRepository để checkpoint Step, giám sát Job/partition. Manager theo dõi status và thời gian thực thi từ nguồn bền vững.
6. Benchmark với 2, 4, 8 rồi 12 partition active; theo dõi throughput, p95 commit, active connections, CPU/GC và straggler.
7. Kiểm tra crash trước commit, ngay sau commit, khi retry API, lúc manager mất kết nối, và khi worker restart trên host khác.
8. Đối soát số lượng, khóa duy nhất, checksum/tổng tiền và cùng tập snapshot; chỉ coi Job thành công khi các bất biến nghiệp vụ đạt yêu cầu.

### 11.1. Kịch bản kiểm thử có điều kiện chấp nhận

| Kịch bản | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Bình thường | Chạy 4 partition trên 2 worker | Mỗi bản ghi nguồn hợp lệ nằm ở đúng một partition và có kết quả đích |
| Lặp thông điệp | Gửi lại yêu cầu cùng partition theo điều kiện an toàn của hạ tầng | Không thêm duplicate và không có hai lượt ghi không kiểm soát |
| Crash giữa chunk | Dừng worker trước transaction commit | Dữ liệu chưa commit được rollback/xử lý lại; kết quả cuối chính xác |
| Crash sau commit | Dừng worker sau khi ghi đích nhưng trước xác nhận hoàn tất | Retry có thể xảy ra; writer idempotent và đối soát vẫn đúng |
| Di chuyển worker | Cho partition lỗi chạy lại trên replica mới | Không cần cache/file/field riêng từ replica cũ |
| Skew cao | Dùng 1 partition có 80% dữ liệu | Nhìn thấy straggler trên metric; thiết kế chia lại có chủ đích |
| Database bão hòa | Tăng concurrency từng nấc | Không vượt giới hạn kết nối; nhận diện điểm throughput không còn tăng |
| Restart Job | Restart cùng JobInstance sau Step thất bại | Partition hoàn tất không bị làm lại ngoài ý muốn; phần chưa hoàn tất được phục hồi đúng |

Việc thử redelivery chủ động cần tuân theo hợp đồng broker và cơ chế điều phối để tránh tạo hai StepExecution cùng hoạt động bất hợp lệ. Mục tiêu là xác minh hệ thống **chống được các lỗi có thể xuất hiện thật**, không phải ép sửa metadata JobRepository thủ công.

### 11.2. Mẫu checklist đánh giá trước khi đưa vào vận hành

- [ ] Partition không chồng lấn, tên và biên dữ liệu ổn định khi restart.
- [ ] Nguồn dữ liệu có cơ chế snapshot/watermark hoặc phương án nhất quán đã chọn.
- [ ] Reader/Writer có vòng đời đúng StepExecution và không chia sẻ mutable state nguy hiểm.
- [ ] Checkpoint được lưu bền vững; xử lý lại sau crash không phụ thuộc RAM/local disk.
- [ ] Ghi đích có chiến lược idempotency, transaction và đối soát đủ cho nghiệp vụ.
- [ ] Có retry limit, backoff và cơ chế xử lý request thất lạc/duplicate.
- [ ] Có metric theo partition cùng log tương quan Job/Step/worker.
- [ ] Đã đo bottleneck của nguồn, đích, broker, JobRepository và connection pool.
- [ ] Đã thử kill worker, manager, redelivery và restart trên replica khác.
- [ ] Runbook chỉ rõ cách điều tra FAILED/UNKNOWN/STARTED quá lâu và cách restart an toàn.

## 12. Kết luận

Worker stateless theo partition là **một hợp đồng về khả năng thay thế worker**, không chỉ là cách viết class không có field. Hợp đồng đó yêu cầu **phạm vi dữ liệu xác định**, **ngữ cảnh và checkpoint bền vững**, **tài nguyên xử lý tách riêng theo StepExecution**, **ghi kết quả có thể retry**, cùng một cơ chế điều phối và vận hành có thể phục hồi khi tiến trình chết.

Khi những điều kiện trên được đáp ứng, có thể tăng hoặc giảm số instance worker theo năng lực CPU, I/O, database và broker thực tế, áp dụng local/remote partitioning, phân tích straggler và restart partition lỗi mà vẫn giữ tính đúng đắn. Nếu thiếu idempotency, snapshot hoặc checkpoint, mở rộng theo số worker có thể làm Job nhanh hơn trong trường hợp bình thường nhưng làm phát sinh lỗi khó sửa sau failover.

**Tài liệu đối chiếu khi triển khai:** Spring Batch Reference Documentation về Scaling and Parallel Processing, Partitioning, JobRepository, ExecutionContext, StepScope, ItemStream và Restart; tài liệu Spring Batch Integration về remote partitioning; tài liệu cơ sở dữ liệu về transaction/isolation và tài liệu broker về delivery/ack. Đối chiếu API/cấu hình với phiên bản Spring Batch thực tế trong dự án.
