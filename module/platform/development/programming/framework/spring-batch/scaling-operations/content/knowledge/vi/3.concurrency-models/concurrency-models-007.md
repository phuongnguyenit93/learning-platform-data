# Remote Step giữa các tiến trình trong Spring Batch

Khi một Spring Batch job phải xử lý hàng chục triệu bản ghi nhưng một máy không còn đủ CPU, RAM hoặc băng thông I/O, ta có thể **đưa từng lần thực thi worker step sang các tiến trình JVM độc lập**. Manager vẫn điều phối job và biết phần dữ liệu nào thuộc worker nào; worker nhận một yêu cầu chứa danh tính `StepExecution`, truy cập metadata tương ứng, chạy reader–processor–writer của phần dữ liệu được giao rồi cập nhật kết quả. Đây là cách triển khai **remote step execution theo mô hình remote partitioning**.

Trong tài liệu Spring Batch, **“Remote Step” không phải tên một loại Step chính thức riêng biệt**. Cách diễn đạt chính xác cho bài này là **remote partitioning của một StepExecution** qua middleware; không nhầm với *remote chunking* (manager đọc item, worker nhận chunk) hoặc *remote job launching* (gửi lệnh khởi chạy toàn bộ Job sang máy khác).

Bài học thuộc chương **Mô hình đồng thời** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu của module là mở rộng Spring Batch cho workload lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, dựa vào số đo nút thắt, thread safety, retry/restart, vận hành job và năng lực tài nguyên thực tế. Nội dung sau trình bày cách remote step vận hành, cấu hình mẫu và các điểm an toàn bắt buộc.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả luồng **manager → Partitioner → StepExecutionSplitter → PartitionHandler → remote worker**.
2. Giải thích `StepExecutionRequest`, `StepExecutionRequestHandler`, `StepLocator`, `JobExplorer` và `JobRepository`.
3. Phân biệt **reply aggregation** và **polling JobRepository** để manager nhận kết quả.
4. Cấu hình khung remote partitioning với Spring Batch Integration 5.2.x và worker step có `@StepScope`.
5. Thiết kế tên partition, phạm vi dữ liệu và checkpoint ổn định khi restart.
6. Phân tích sự cố message trùng, request mất, worker crash và tác dụng phụ đã commit.
7. Tính concurrency từ throughput, số partition, DB pool và quota API thay vì dựa riêng vào `gridSize`.
8. Kiểm thử dữ liệu đúng/đủ, thread safety, khả năng restart và chỉ số vận hành nhiều tiến trình.

## 2. Remote Step thực sự chạy ở đâu?

Một JobInstance có thể có `JobExecution` chạy trên **manager JVM**. Bên trong job đó, một **manager partition step** phân chia công việc thành nhiều `StepExecution` của **cùng một worker step**. Các `StepExecution` được thực thi bởi worker services/JVM khác nhau.

Ví dụ job nhập hóa đơn từ 8 file bất biến:

| Phần việc | Tiến trình thực thi | Phạm vi |
| --- | --- | --- |
| `importInvoicesManager` | Manager JVM | Điều phối 8 partition, theo dõi trạng thái |
| `invoiceWorkerStep:file-001` | Worker JVM A | Đọc, xử lý, ghi file 001 |
| `invoiceWorkerStep:file-002` | Worker JVM B | Đọc, xử lý, ghi file 002 |
| `invoiceWorkerStep:file-003` | Worker JVM C | Đọc, xử lý, ghi file 003 |
| `invoiceWorkerStep:file-004` … `file-008` | Bất kỳ worker còn năng lực | Các file còn lại |

Tên đầy đủ của một partition StepExecution thường có dạng `<workerStepName>:<partitionKey>`. **Worker A, B, C không phải ba JobInstance độc lập.** Chúng là các process thực thi những phần việc thuộc cùng job được điều phối.

~~~mermaid
flowchart LR
    subgraph MANAGER["Manager JVM"]
      J["JobExecution"] --> M["PartitionStep<br/>importInvoicesManager"]
      M --> P["Partitioner + Splitter"]
      P --> H["MessageChannelPartitionHandler"]
    end
    H --> RQ[("Request queue")]
    RQ --> WA["Worker JVM A<br/>invoiceWorkerStep"]
    RQ --> WB["Worker JVM B<br/>invoiceWorkerStep"]
    RQ --> WC["Worker JVM C<br/>invoiceWorkerStep"]
    WA --> D[("Nguồn / Đích dữ liệu")]
    WB --> D
    WC --> D
    WA --> JR[("Shared JobRepository")]
    WB --> JR
    WC --> JR
    M --> JR
    WA --> RS[("Reply queue<br/>nếu dùng replies")]
    WB --> RS
    WC --> RS
    RS --> H
~~~

Sơ đồ biểu diễn hai đường kết quả có thể dùng: worker **luôn phải cập nhật metadata phù hợp qua JobRepository**, còn reply queue là đường phản hồi khi manager sử dụng chế độ **reply aggregation**. Nếu manager **polling JobRepository**, có thể không cấu hình reply queue.

### 2.1. Tại sao khác multi-threaded step?

| Tiêu chí | Multi-threaded step | Local partitioning | **Remote Step qua partitioning** |
| --- | --- | --- | --- |
| Chạy ở đâu? | Các thread trong một JVM | Các thread trong một JVM | Nhiều JVM/pod/máy |
| Đơn vị song song | Chunk của cùng step | Worker StepExecution | Worker StepExecution |
| Metadata | Thường chung một StepExecution cho nhiều chunk | StepExecution riêng từng partition | StepExecution riêng từng partition trên shared repository |
| Reader | Có thể chia sẻ một reader mutable | Reader riêng theo partition/StepScope | Reader riêng tại remote worker/StepScope |
| Giao tiếp | Executor nội bộ | Executor nội bộ | Messaging/transport + metadata DB |
| Điểm lỗi | Shared-state race, crash một process | Thêm skew, nhiều partition | Thêm broker, network, worker lifecycle, stale status |
| Khả năng scale | Giới hạn một JVM | Giới hạn một JVM | Thêm worker JVM nếu nguồn/đích còn năng lực |

Một worker remote **tự đọc phạm vi dữ liệu của nó**. Vì vậy remote partitioning có thể mở rộng cả công đoạn đọc nếu nguồn có thể chia theo file/range/key; trong remote chunking thì reader nằm ở manager.

## 3. Thành phần cốt lõi và trách nhiệm

| Thành phần | Trách nhiệm |
| --- | --- |
| `PartitionStep` | Manager step điều phối việc chia và tổng hợp kết quả |
| `Partitioner` | Trả về `Map<String, ExecutionContext>`: tên partition và tham số dữ liệu |
| `StepExecutionSplitter` | Tạo/khôi phục những worker StepExecution cần chạy từ `JobRepository` |
| `PartitionHandler` | Truyền yêu cầu thực thi sang worker và thu nhận trạng thái |
| `MessageChannelPartitionHandler` | PartitionHandler dùng Spring Messaging/Spring Integration channels |
| `StepExecutionRequest` | DTO chứa tên step, `jobExecutionId` và `stepExecutionId` để worker tìm execution |
| `StepExecutionRequestHandler` | Nhận request, nạp metadata, xác định worker step và thực thi |
| `StepLocator` | Tìm bean `Step` theo tên; thường dùng `BeanFactoryStepLocator` |
| `JobExplorer` | Đọc thông tin JobExecution/StepExecution từ repository |
| `JobRepository` | Nguồn sự thật bền vững cho trạng thái, counters và `ExecutionContext` |
| **Worker `Step`** | Thực hiện `ItemReader` → `ItemProcessor` → `ItemWriter` và checkpoint riêng |

Spring Batch Integration cung cấp `RemotePartitioningManagerStepBuilder`, `RemotePartitioningWorkerStepBuilder` và các factory tương ứng để giảm công việc wiring.

### 3.1. Nội dung request là định danh StepExecution, không phải toàn bộ dữ liệu

Về mặt khái niệm, một message remote partitioning có thông tin:

~~~text
StepExecutionRequest
  stepName        = "invoiceWorkerStep"
  jobExecutionId  = 204
  stepExecutionId = 9018
~~~

`StepExecutionRequest` là lớp của Spring Batch Integration; không nên coi đoạn trên là JSON wire format mặc định. Worker dùng ID để tra metadata và `ExecutionContext` đã được lưu trong **shared JobRepository**. Các giá trị `inputUri`, `minId` hoặc `maxId` thuộc context của partition chứ **không bắt buộc** được nhúng nguyên bộ dữ liệu vào message.

Nhờ vậy, message điều phối thường nhỏ ngay cả khi partition chứa hàng triệu item. So sánh với remote chunking: request có thể chứa cả tập item đã đọc, gây chi phí serialization/network lớn hơn.

### 3.2. Một chu kỳ thực thi

1. Manager tạo `JobExecution` và chạy `PartitionStep`.
2. `Partitioner` quyết định các key và `ExecutionContext`; splitter tạo các `StepExecution` con có ID trong repository.
3. `MessageChannelPartitionHandler` gửi `StepExecutionRequest` tới request channel được nối với middleware.
4. Broker/router chuyển yêu cầu tới một remote worker tương thích.
5. `StepExecutionRequestHandler` dùng `JobExplorer` để tải StepExecution, `StepLocator` để tìm tên bean worker step.
6. Worker step tạo reader theo `ExecutionContext`, chạy chunk/tasklet, commit output và ghi lại trạng thái qua `JobRepository`.
7. Tùy cấu hình, worker gửi reply hoặc manager truy vấn repository để biết partition đã hoàn tất.
8. Manager tổng hợp kết quả các partition; job tiếp tục hoặc thất bại theo `BatchStatus` và luồng điều khiển.

~~~mermaid
sequenceDiagram
    participant M as Manager PartitionStep
    participant R as JobRepository
    participant B as Middleware
    participant W as Remote Worker
    participant D as Input/Output Storage
    M->>R: Tạo StepExecution + context cho partition
    M->>B: StepExecutionRequest(stepName, jobExecutionId, stepExecutionId)
    B->>W: Deliver request
    W->>R: JobExplorer đọc StepExecution + ExecutionContext
    W->>W: StepLocator tìm invoiceWorkerStep
    W->>D: Reader → Processor → Writer
    W->>R: Ghi chunk checkpoint, counters, BatchStatus
    W-->>B: Reply nếu dùng reply aggregation
    B-->>M: Kết quả worker (tùy chế độ)
    M->>R: Tổng hợp metadata và ghi manager status
~~~

**Không coi giao request thành công là hoàn thành công việc.** Một process đã nhận request vẫn có thể fail trước khi ghi dữ liệu. Kết quả cuối cùng phải được xác minh từ worker state và output.

## 4. Hai cách manager biết worker đã hoàn tất

Spring Batch Integration hỗ trợ hai mô hình khi dùng `MessageChannelPartitionHandler`.

### 4.1. Reply aggregation

~~~text
Manager outputChannel -> request queue -> remote worker
Manager inputChannel  <- reply queue   <- remote worker
                                      worker -> JobRepository
~~~

Worker gửi thông điệp phản hồi sau khi thực thi step; manager thu nhận/tổng hợp replies của partition.

**Ưu điểm:**

- Manager có đường thông báo kết quả chủ động.
- Có thể theo dõi request/reply latency, thiếu reply và worker failures.
- Phù hợp khi middleware đảm bảo routing/correlation rõ ràng.

**Điểm phải xử lý:**

- Reply trễ, mất, trùng hoặc đến sai manager.
- Manager restart nhưng queue còn reply của execution cũ.
- Reply channel/aggregator state không được vô tình dùng chung giữa nhiều manager StepExecution.

Tài liệu `MessageChannelPartitionHandler` khuyến nghị không chia sẻ reply-channel instance của handler một cách tùy tiện giữa các step instances: có nguy cơ message của execution khác bị trộn. Phải có cách định tuyến/aggregation theo run/StepExecution phù hợp.

### 4.2. Polling JobRepository

~~~text
Manager outputChannel -> request queue -> remote workers
                                              |
                                        JobRepository
                                              ^
                                        Manager poll
~~~

Manager gửi StepExecutionRequest và định kỳ dùng `JobExplorer` kiểm tra trạng thái những partition StepExecution đã lưu. Worker **không cần gửi reply message** nếu chọn chế độ này.

Các tùy chọn liên quan của `RemotePartitioningManagerStepBuilder`:

- `pollInterval(long)`: chu kỳ manager đọc trạng thái worker trong repository, đơn vị **mili giây**.
- `timeout(long)`: giới hạn thời gian chờ khi polling, đơn vị **mili giây**; cần chọn hữu hạn cho production thay vì chờ vô tận.
- `jobExplorer(JobExplorer)`: nguồn truy vấn metadata, được factory hỗ trợ cấu hình.

**Ưu điểm:** giảm phụ thuộc vào reply destination và reply correlation. **Đánh đổi:** tăng DB metadata reads theo số partition/tần suất polling, độ trễ phát hiện tối đa thường liên quan poll interval, phải xử lý trường hợp worker bị kẹt ở `STARTED` hoặc không bao giờ cập nhật terminal status.

Không nên vừa cấu hình reply aggregation vừa giả định `pollInterval` tự động được dùng làm fallback; hãy chọn và thử nghiệm **một đường hoàn tất có hợp đồng rõ ràng**. Trong môi trường có nhiều manager chạy đồng thời, polling thường đơn giản hơn về reply routing, nhưng vẫn cần timeout/alert và repository đủ capacity.

## 5. Những điều kiện trước khi chia Step ra nhiều tiến trình

Trước khi cấu hình broker, hãy kiểm tra:

- **Dữ liệu chia được:** theo file, snapshot, khoảng ID hoặc khóa nghiệp vụ.
- **Các worker đọc được input:** chung database, object storage hoặc volume phù hợp; không sử dụng đường dẫn file chỉ tồn tại trên máy manager.
- **Metadata chung:** manager và tất cả worker truy cập **cùng JobRepository**, đúng schema/prefix và version tương thích.
- **Tên step chung:** `StepLocator` của worker tìm thấy đúng `invoiceWorkerStep` đã được manager chỉ định.
- **Nguồn dữ liệu bất biến:** phạm vi mỗi partition ổn định qua các lần restart của JobInstance.
- **DB/API đủ năng lực:** không tăng số pods vượt connection limit, IOPS, lock và rate limit.
- **Side effects an toàn:** writer có transaction/idempotency hoặc đối soát có thể phục hồi.
- **Quan sát được:** có log/metric theo JobExecution và partition, cùng cảnh báo timeout, DLQ và partition mắc kẹt.
- **Vận hành được:** có cách dừng worker cũ, xử lý stale status và restart đúng JobInstance.

Nếu một bước còn phụ thuộc vào mutable state chỉ tồn tại trong heap của manager (chẳng hạn một `Map` chứa “dữ liệu đã phân” nhưng không được lưu bền), remote worker thường **không truy cập được state đó**. Hãy đặt dữ liệu cần thiết trong `ExecutionContext`, job parameters hoặc storage truy cập được và bảo đảm khả năng serialize.

## 6. Thiết kế Partitioner ổn định và không chồng lấn

Giả sử import hóa đơn với `invoice_id` từ 1 đến 800.000 của một snapshot cố định. Tạo tám partition:

| Key | minId (bao gồm) | maxId (bao gồm) |
| --- | ---: | ---: |
| `range-00` | 1 | 100.000 |
| `range-01` | 100.001 | 200.000 |
| `range-02` | 200.001 | 300.000 |
| `range-03` | 300.001 | 400.000 |
| `range-04` | 400.001 | 500.000 |
| `range-05` | 500.001 | 600.000 |
| `range-06` | 600.001 | 700.000 |
| `range-07` | 700.001 | 800.000 |

Một `Partitioner` trả về `Map<String, ExecutionContext>`, với key là tên logic và context chứa hai giới hạn:

~~~java
@Bean
public Partitioner invoiceRangePartitioner() {
    return gridSize -> {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        // Snapshot ID range cố định cho ví dụ; production lấy từ manifest.
        for (int i = 0; i < 8; i++) {
            long minId = 1L + i * 100_000L;
            long maxId = minId + 99_999L;

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", minId);
            context.putLong("maxId", maxId);

            partitions.put(String.format("range-%02d", i), context);
        }
        return partitions;
    };
}
~~~

Trong ví dụ này, partitioner **cố ý bỏ qua `gridSize`** vì manifest định nghĩa đúng tám range. Với production, có thể tham chiếu danh sách file/range cố định theo `snapshotId` thay vì hard-code. `gridSize` là **hint cho việc chia partition**, không phải số worker JVM và không cam kết phần việc được chia đúng bằng nó.

### 6.1. Bốn thuộc tính quan trọng

1. **Coverage:** mọi record thuộc snapshot nằm trong ít nhất một partition.
2. **Disjointness:** không record nào nằm trong hai partition, trừ khi nghiệp vụ chủ ý và writer xử lý đúng.
3. **Stability:** cùng JobInstance có cùng tên/phạm vi dữ liệu khi restart.
4. **Balance:** số lượng và độ khó xử lý giữa partition không quá lệch.

Tránh tạo `partition0` theo thứ tự ngẫu nhiên của file listing. Đổi `range-03` thành `partition-3` sau lần lỗi có thể làm Spring Batch không đối chiếu được StepExecution/ExecutionContext cũ. Với input liên tục thay đổi, cần snapshot/watermark và chính sách ràng buộc dữ liệu cụ thể; `WHERE id BETWEEN ...` không tự đảm bảo snapshot consistency.

## 7. Ví dụ manager JVM với Spring Batch Integration 5.2.x

Ví dụ dưới đây sử dụng **Spring Batch 5.2.x**, Java 17+ và `spring-batch-integration`/Spring Integration. Manager tạo `PartitionStep`, không chạy reader/processor/writer của worker trên JVM này.

Tệp Java minh họa **manager application**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.integration.config.annotation.EnableBatchIntegration;
import org.springframework.batch.integration.partition.RemotePartitioningManagerStepBuilderFactory;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableBatchIntegration
public class InvoiceManagerConfig {

    @Bean
    public Partitioner invoiceRangePartitioner() {
        return gridSize -> {
            Map<String, ExecutionContext> ranges = new LinkedHashMap<>();
            for (int i = 0; i < 8; i++) {
                long min = 1L + i * 100_000L;
                ExecutionContext c = new ExecutionContext();
                c.putLong("minId", min);
                c.putLong("maxId", min + 99_999L);
                ranges.put(String.format("range-%02d", i), c);
            }
            return ranges;
        };
    }

    @Bean
    public Step importInvoicesManager(
            RemotePartitioningManagerStepBuilderFactory managerFactory,
            @Qualifier("invoiceRangePartitioner") Partitioner partitioner,
            @Qualifier("outboundStepRequests") MessageChannel requests,
            @Qualifier("inboundStepReplies") MessageChannel replies) {

        return managerFactory.get("importInvoicesManager")
                .partitioner("invoiceWorkerStep", partitioner)
                .gridSize(8)
                .outputChannel(requests)
                .inputChannel(replies) // Chế độ reply aggregation
                .build();
    }

    @Bean
    public Job importInvoicesJob(
            JobRepository jobRepository,
            @Qualifier("importInvoicesManager") Step managerStep) {
        return new JobBuilder("importInvoicesJob", jobRepository)
                .start(managerStep)
                .build();
    }
}
~~~

`RemotePartitioningManagerStepBuilderFactory` được cung cấp bởi `@EnableBatchIntegration` trên hạ tầng Batch/Integration đã cấu hình. Manager phải có JobRepository/JobExplorer và middleware adapter tương thích. **Chỉ khai báo MessageChannel không làm ứng dụng tự kết nối tới broker**; chúng cần flow/outbound adapter và inbound adapter cụ thể.

Các điểm cần nắm:

- `partitioner("invoiceWorkerStep", partitioner)` xác định **tên worker step** mà remote worker phải có; tên bean/Step trong worker phải khớp.
- Manager tự động dùng `MessageChannelPartitionHandler` do builder cung cấp. Không gọi `partitionHandler(...)` để thay handler này trên `RemotePartitioningManagerStepBuilder`: API từ chối thay handler bằng cách đó.
- `outputChannel(...)` mang các `StepExecutionRequest` đi ra middleware.
- `inputChannel(...)` nhận các replies phục vụ reply aggregation; việc nối đúng reply destination cần cấu hình Spring Integration.
- `gridSize(8)` được truyền như hint cho partitioning; ví dụ đã chọn đúng tám partition từ manifest.
- Các `StepExecution` con và `ExecutionContext` được lưu trong **JobRepository chung**, trước khi worker cần chạy chúng.

### 7.1. Khi muốn polling repository thay vì dùng reply

Đây là **phương án thay thế**, không dùng đồng thời với manager bean ở ví dụ trên:

~~~java
@Bean
public Step importInvoicesManagerPolling(
        RemotePartitioningManagerStepBuilderFactory managerFactory,
        @Qualifier("invoiceRangePartitioner") Partitioner partitioner,
        @Qualifier("outboundStepRequests") MessageChannel requests) {

    return managerFactory.get("importInvoicesManager")
            .partitioner("invoiceWorkerStep", partitioner)
            .gridSize(8)
            .outputChannel(requests)
            // Không khai báo inputChannel ở chế độ polling.
            .pollInterval(5_000L)       // 5 giây
            .timeout(3_600_000L)        // tối đa 1 giờ chờ
            .build();
}
~~~

Đây là snippet **lựa chọn cấu hình**, không đặt song song hai bean cùng tên manager step trong một ứng dụng thật. Theo chế độ này, worker không bắt buộc gửi reply; manager xác định kết quả từ các worker StepExecution trong repository. Trong môi trường có timeout, cần có quy trình xác nhận các worker còn chạy hay không trước khi restart.

## 8. Ví dụ worker JVM: reader riêng cho mỗi remote StepExecution

Worker application phải định nghĩa **cùng tên step** `invoiceWorkerStep`. Khi nhận `StepExecutionRequest`, handler do Spring Batch Integration cấu hình dùng `StepLocator` tìm step này và khôi phục context chứa `minId`/`maxId`.

Tạo reader có `@StepScope` để mỗi partition/StepExecution có cursor riêng:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import javax.sql.DataSource;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.integration.config.annotation.EnableBatchIntegration;
import org.springframework.batch.integration.partition.RemotePartitioningWorkerStepBuilderFactory;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.JdbcCursorItemReader;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.messaging.MessageChannel;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchIntegration
public class InvoiceWorkerConfig {

    public record InvoiceRow(long id, BigDecimal amount) {}
    public record InvoiceTotal(long id, BigDecimal total) {}

    @Bean
    @StepScope
    public JdbcCursorItemReader<InvoiceRow> invoiceRangeReader(
            DataSource dataSource,
            @Value("#{stepExecutionContext['minId']}") Long minId,
            @Value("#{stepExecutionContext['maxId']}") Long maxId) {

        return new JdbcCursorItemReaderBuilder<InvoiceRow>()
                .name("invoiceRangeReader")
                .dataSource(dataSource)
                .sql("""
                     SELECT invoice_id, amount
                     FROM source_invoice
                     WHERE invoice_id BETWEEN ? AND ?
                     ORDER BY invoice_id
                     """)
                .preparedStatementSetter(ps -> {
                    ps.setLong(1, minId);
                    ps.setLong(2, maxId);
                })
                .rowMapper((rs, rowNumber) -> new InvoiceRow(
                        rs.getLong("invoice_id"),
                        rs.getBigDecimal("amount")))
                .fetchSize(500)
                .saveState(true)
                .build();
    }

    @Bean
    public ItemProcessor<InvoiceRow, InvoiceTotal> invoiceProcessor() {
        BigDecimal factor = new BigDecimal("1.05");
        return row -> new InvoiceTotal(
                row.id(),
                row.amount().multiply(factor)
                        .setScale(2, RoundingMode.HALF_UP));
    }

    @Bean
    public JdbcBatchItemWriter<InvoiceTotal> invoiceWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<InvoiceTotal>()
                .dataSource(dataSource)
                .sql("""
                     INSERT INTO invoice_total(invoice_id, total_amount)
                     VALUES (:id, :total)
                     ON CONFLICT (invoice_id)
                     DO UPDATE SET total_amount = EXCLUDED.total_amount
                     """)
                .itemSqlParameterSourceProvider(row ->
                        new MapSqlParameterSource()
                                .addValue("id", row.id())
                                .addValue("total", row.total()))
                .build();
    }

    @Bean
    public Step invoiceWorkerStep(
            RemotePartitioningWorkerStepBuilderFactory workerFactory,
            @Qualifier("incomingStepRequests") MessageChannel requests,
            @Qualifier("outgoingStepReplies") MessageChannel replies,
            PlatformTransactionManager transactionManager,
            JdbcCursorItemReader<InvoiceRow> invoiceRangeReader,
            ItemProcessor<InvoiceRow, InvoiceTotal> invoiceProcessor,
            JdbcBatchItemWriter<InvoiceTotal> invoiceWriter) {

        return workerFactory.get("invoiceWorkerStep")
                .inputChannel(requests)
                .outputChannel(replies)
                .<InvoiceRow, InvoiceTotal>chunk(250, transactionManager)
                .reader(invoiceRangeReader)
                .processor(invoiceProcessor)
                .writer(invoiceWriter)
                .build();
    }
}
~~~

**Giới hạn của ví dụ:** đây là cấu hình **worker step** và reader/writer, chưa có mã khởi chạy ứng dụng, tạo bảng `source_invoice`/`invoice_total`, kết nối shared JobRepository, các `MessageChannel` bean hoặc JMS/AMQP adapters. Cần thêm những thành phần đó và kiểm tra API của phiên bản cụ thể trước khi chạy.

**Các điểm kỹ thuật cần hiểu:**

- `@StepScope` mang ý nghĩa **theo StepExecution**, không theo JVM, thread hay từng item. Mỗi partition remote sử dụng một context độc lập khi scope được kích hoạt đúng.
- `JdbcCursorItemReader` là stateful; không nên dùng một singleton mutable reader cho nhiều StepExecution đồng thời.
- `ORDER BY invoice_id` có khóa định danh duy nhất để khôi phục vị trí đọc dễ kiểm soát hơn; nguồn phải giữ snapshot ổn định.
- `JdbcBatchItemWriter` và datasource dùng transaction manager phù hợp; mỗi chunk ở worker có ranh giới commit riêng.
- `ON CONFLICT` là cú pháp PostgreSQL; ví dụ upsert giúp tránh tăng số dòng khi cùng item được phát lại, nhưng không thay thế quy tắc version/đối soát khi dữ liệu nguồn thay đổi.
- Factory worker có thể tạo `StepExecutionRequestHandler`/integration wiring. Listener, message converter và kênh transport từ broker tới `incomingStepRequests` vẫn cần cấu hình.
- Khi manager dùng **repository polling**, có thể bỏ `outputChannel(replies)` ở cấu hình worker tương ứng; nên chọn một chế độ nhất quán giữa hai phía.

### 8.1. Schema ví dụ

~~~sql
-- PostgreSQL, chỉ là bảng nghiệp vụ minh họa.
CREATE TABLE source_invoice (
    invoice_id BIGINT PRIMARY KEY,
    amount NUMERIC(18,2) NOT NULL
);

CREATE TABLE invoice_total (
    invoice_id BIGINT PRIMARY KEY,
    total_amount NUMERIC(18,2) NOT NULL
);
~~~

Các bảng `BATCH_JOB_*`, `BATCH_STEP_*` và metadata context phải được tạo theo schema Spring Batch tương ứng, **không phải** tạo từ hai câu SQL trên. Manager và worker phải dùng cùng repository và tương thích với schema của phiên bản chạy.

## 9. Middleware và routing giữa các tiến trình

Các Spring Messaging channels trong ví dụ cần được nối tới một công nghệ transport như JMS/AMQP hoặc handler tuỳ biến.

~~~text
Manager JVM
  outboundStepRequests
       -> outbound adapter
       -> [remote.step.requests queue]
                |
                +-- Worker JVM A -> incomingStepRequests
                +-- Worker JVM B -> incomingStepRequests
                +-- Worker JVM C -> incomingStepRequests

Reply mode:
  Worker outgoingStepReplies
       -> outbound adapter
       -> [remote.step.replies queue]
       -> inbound adapter -> Manager inboundStepReplies

Polling mode:
  worker commits StepExecution metadata -> shared JobRepository
  manager polls statuses -> JobExplorer
~~~

Đối với **work queue**, nhiều worker là competing consumers, không phải mỗi worker đều nhận mọi request. Dùng JMS **queue** hoặc RabbitMQ queue với routing phù hợp; pub/sub fanout không phải mặc định của remote partitioning.

### 9.1. Bảo đảm vận chuyển: khác remote chunking nhưng vẫn cần thiết kế

Tài liệu Spring Batch lưu ý rằng **remote partitioning dựa vào JobRepository** để quản lý danh tính StepExecution và hỗ trợ restart, nên thông điệp phân phối **không bắt buộc** có cùng yêu cầu reliable delivery như remote chunking. Tuy nhiên, điều này **không có nghĩa** mạng/broker không thể mất request hoặc mọi broker setup đều tự phục hồi:

- Nếu request bị mất, một partition có thể không chạy trong lần thử hiện tại; manager cần timeout/fail và restart để gửi lại theo metadata.
- Nếu request bị giao trùng, chỉ lưu metadata không tự bảo đảm external side effect chạy một lần; phải kiểm tra chống lặp và ownership execution.
- Nếu reply mất ở reply mode, manager có thể chờ thất bại dù worker đã ghi metadata thành công; polling mode giảm phụ thuộc reply.
- Nếu worker crash sau khi commit DB nhưng trước khi cập nhật metadata, cần đối soát output và idempotent write.
- Nếu cả manager và worker đời cũ vẫn chạy khi restart đời mới, có rủi ro xử lý chồng; cần fencing/operational control.

Production thường có lợi từ queue durable, persistent messages, publisher confirmation, consumer acknowledgement và giới hạn redelivery, nhưng **đừng hứa exactly-once nghiệp vụ chỉ vì bật các cờ transport**. Broker transport, JobRepository và database output không tự động chia sẻ một transaction phân tán.

### 9.2. Routing và bảo vệ contract

- Kiểm tra message converter/serializer có thể giữ được `StepExecutionRequest` và đúng kiểu trong worker.
- Worker đã deploy đúng tên Step, bản code và version schema metadata.
- Xác thực và ủy quyền broker; worker chỉ truy cập queue và DB cần thiết.
- Không gửi URL/password/PII nhạy cảm trong context hay log nếu không cần thiết.
- Khi chạy nhiều manager hoặc nhiều phiên bản job, đảm bảo reply routing/correlation không trộn kết quả.
- Quy định compatibility khi rolling deploy: worker mới có đọc được `ExecutionContext`/message của job còn đang chạy hay không?

**Một request không chứa nguyên cả dữ liệu** không có nghĩa worker không cần quyền dữ liệu. Reader của worker phải có network access, credentials và query permission tới input; writer phải có quyền transaction ở đích.

## 10. Restart và xử lý partition lỗi

Ví dụ JobInstance `importInvoicesJob(snapshot=2026-11-25)` có bốn partition:

| Partition | Kết quả JobExecution #204 | Khi restart đúng JobInstance |
| --- | --- | --- |
| `invoiceWorkerStep:range-00` | `COMPLETED` | Mặc định bỏ qua |
| `invoiceWorkerStep:range-01` | `COMPLETED` | Mặc định bỏ qua |
| `invoiceWorkerStep:range-02` | `FAILED` | Được chọn thực thi lại |
| `invoiceWorkerStep:range-03` | `COMPLETED` | Mặc định bỏ qua |

Spring Batch `StepExecutionSplitter` đối chiếu tên và trạng thái partition trong `JobRepository` khi restart. Chỉ những StepExecution cần phục hồi theo chính sách mới được phân phối lại; các partition `COMPLETED` có thể được giữ kết quả ở lần trước.

**Phân biệt hai tầng restart:**

1. **Partition-level:** framework chọn partition nào cần chạy lại.
2. **Within-partition:** reader/ItemStream dùng `ExecutionContext` để tiếp tục từ checkpoint chunk đã commit khi có thể.

Giả sử partition `range-02` đã commit 8.000/10.000 bản ghi rồi thất bại. Nếu reader `saveState(true)`, context được ghi bền vững và input không đổi, restart có thể tiếp tục ở phần chưa commit; không nhất thiết phải xử lý lại từ item đầu tiên.

### 10.1. Điều kiện để restart an toàn

1. **Đúng JobInstance:** dùng lại identifying `JobParameters`; không tăng `run.id` như một cách “reset”.
2. **Metadata còn nguyên:** không xóa `BATCH_STEP_EXECUTION` hoặc context của partition chưa hoàn tất.
3. **Tên ổn định:** giữ `invoiceWorkerStep` và các key `range-00`…`range-07`.
4. **Snapshot bất biến:** không tính lại range dựa trên `MAX(id)` mới trong lần restart mà bỏ qua ranh giới cũ.
5. **Worker version tương thích:** Java classes, SQL schema và serializer được hỗ trợ.
6. **Reader checkpoint hợp lệ:** vị trí đọc tương thích với đầu vào chưa đổi.
7. **Writer chống lặp:** retry/restart hoặc ranh giới crash không tạo thêm kết quả nghiệp vụ sai.
8. **Chặn worker thế hệ cũ:** xác nhận tiến trình/consumer cũ không còn đang xử lý phần dữ liệu cần phát lại.
9. **Quy trình kiểm tra trạng thái:** nếu repository còn `STARTED`/`UNKNOWN` sau crash, không tự sửa metadata tùy tiện.

Ví dụ có thể dùng `JobOperator.restart(failedExecutionId)` sau khi xác nhận job ở trạng thái cho phép restart. `JobOperator.restart` làm việc với **JobExecution ID**, không nhận partition key và không tự đảm bảo rằng mọi remote worker cũ đã dừng.

### 10.2. `allowStartIfComplete` và chính sách chạy lại

Mặc định partition đã `COMPLETED` thường được bỏ qua khi restart cùng JobInstance. Nếu bật `allowStartIfComplete(true)` cho worker step, hành vi có thể thay đổi và partition đã hoàn tất có thể được chạy lại. Với yêu cầu “chỉ chạy lại partition lỗi”, hãy giữ chính sách mặc định và kiểm thử thực tế.

Không biến `gridSize` thành công cụ repartition khi restart. Splitter có thể khôi phục danh tính các partition cũ và bỏ qua hint mới; thay đổi tên/phạm vi trong cùng JobInstance không an toàn nếu chưa có kế hoạch migration.

## 11. Ranh giới transaction và chống ghi trùng nghiệp vụ

Một worker remote có thể commit nhiều chunk trong một StepExecution, đồng thời các worker khác đang commit vào cùng database.

~~~text
Worker A: range-00 | chunk 1 COMMIT | chunk 2 COMMIT | chunk 3 ...
Worker B: range-01 | chunk 1 COMMIT | chunk 2 FAILED -> ROLLBACK
Worker C: range-02 | chunk 1 COMMIT | chunk 2 COMMIT | ...
~~~

**Không có transaction duy nhất** bao trùm manager JVM + broker + tất cả worker JVM + database output theo mặc định. Các chunk transaction độc lập và có thể commit khác thứ tự.

### 11.1. Ba loại an toàn khác nhau

| Mức bảo vệ | Giải quyết điều gì? | Không giải quyết gì? |
| --- | --- | --- |
| Partition coverage/disjointness | Mỗi record được gán một shard phù hợp | Side effect có thể lặp khi retry |
| JobRepository + StepExecution status | Theo dõi shard và chọn restart | External API có thể bị gọi hai lần |
| Transaction + business idempotency | Dữ liệu DB/external business effect nhất quán khi phát lại | Tên partition/snapshot có thể vẫn sai |

Ví dụ upsert xác định theo khóa `invoice_id`:

~~~sql
INSERT INTO invoice_total(invoice_id, total_amount)
VALUES (:invoice_id, :total)
ON CONFLICT (invoice_id)
DO UPDATE SET total_amount = EXCLUDED.total_amount;
~~~

Nếu dữ liệu có version, thêm điều kiện ngăn phiên bản cũ ghi đè phiên bản mới. **Không dùng** phép cộng không có dedupe:

~~~sql
-- Không idempotent nếu cùng item được xử lý lại sau crash.
UPDATE customer_balance
SET amount = amount + :invoice_amount
WHERE customer_id = :customer_id;
~~~

Với thanh toán, email, HTTP API hoặc nhiều database không chung transaction, cần idempotency key, unique constraint ở đích, transactional outbox hoặc đối soát nghiệp vụ tùy thiết kế.

### 11.2. Worker chết đúng lúc commit

| Điểm crash | Trạng thái có thể có | Cách xử lý |
| --- | --- | --- |
| Trước DB commit | Chunk rollback hoặc không commit | Restart và retry an toàn |
| Sau DB commit, trước checkpoint metadata bền vững | Output có thể tồn tại nhưng cursor/status chưa phản ánh | Transaction-aware metadata nếu có, idempotency và đối soát |
| Sau checkpoint, trước reply | Worker đã hoàn tất nhưng reply mất | Polling/reconciliation; reply mode cần timeout xử lý đúng |
| Sau broker ACK nhưng trước kết quả được manager biết | Manager có thể không nhận tín hiệu | Dựa repository/timeout và quy trình khôi phục |
| Worker còn chạy sau manager fail | Có tác vụ nghiệp vụ tiếp tục ngoài tầm quan sát của manager cũ | Fencing, kiểm tra liveness/ownership trước restart |

Không viết runbook kiểu “hễ timeout là gửi lại ngay mọi partition” nếu chưa bảo vệ chống lặp. Timeout cho biết **chưa quan sát được trạng thái cần thiết**, không xác nhận rằng worker chưa tạo tác dụng nghiệp vụ.

## 12. Thread safety và state isolation trong worker JVM

Một remote worker JVM có thể nhận nhiều StepExecutionRequest qua listener concurrency. Cần kiểm tra:

- `ItemReader` stateful được tạo riêng theo StepExecution (`@StepScope`), không chia sẻ cursor giữa các partition.
- `ItemProcessor`/`ItemWriter` singleton không giữ `currentItem`, `runningTotal` hoặc buffer mutable không được đồng bộ.
- `StepExecutionContext` không bị dùng chung giữa các worker step khác nhau.
- JDBC connection pool của một pod có giới hạn rõ ràng và không giữ connection quá lâu khi gọi HTTP.
- HTTP client, serializer, retry handler, listener và cache phải có hợp đồng thread safety.
- Nếu business bắt buộc giữ thứ tự per customer/account, các key liên quan nên nằm cùng partition hoặc có version/locking/serialization phù hợp.
- Worker có thread pool cố định hoặc listener concurrency bounded; không tăng không giới hạn khi broker backlog lớn.

**`@StepScope` không đồng nghĩa một instance cho mỗi thread** trong mọi mô hình. Ở remote partitioning, nó hữu ích vì **mỗi partition có StepExecution riêng**. Trong multi-threaded step, nhiều chunk threads có thể chia sẻ cùng StepExecution và StepScoped bean.

## 13. Capacity planning theo tài nguyên và SLA

Giả sử 12 triệu hóa đơn cần hoàn tất trong 60 phút xử lý (chưa tính validation/publish):

\[
R_{\mathrm{required}} =
\frac{12{,}000{,}000}{60\times60}
\approx 3{,}333.3\ \text{items/s}.
\]

Nếu benchmark một worker StepExecution xử lý ổn định **500 items/s** trong điều kiện downstream chưa bão hòa, số worker lý tưởng ban đầu:

\[
N_{\mathrm{ideal}} =
\left\lceil\frac{3{,}333.3}{500}\right\rceil=7.
\]

Nếu muốn lập ngân sách dùng tối đa khoảng **75% hiệu suất lý tưởng** để có khoảng dự phòng, số worker thử nghiệm:

\[
N_{\mathrm{candidate}} =
\left\lceil\frac{3{,}333.3}{500\times0.75}\right\rceil=9.
\]

Đây là **ước lượng đặt giả thuyết benchmark**, không phải kết luận rằng chín pod luôn đạt 3.333 items/s. Khi nhiều worker cùng ghi vào một database, throughput/worker thường không giữ nguyên; database CPU/IOPS, locks và pool connections có thể bão hòa.

### 13.1. Số partition khác số worker

Ví dụ chọn **32 partition logic** và **9 workers concurrent**:

~~~text
32 partition StepExecutions
    |
    | 9 remote workers có thể làm việc cùng lúc
    | (phụ thuộc số process, consumers và năng lực hệ thống)
    |
    +-- phần còn lại được broker/dispatcher xếp lịch
~~~

Phân vùng mịn hơn số worker có thể giúp giảm skew nếu mỗi partition đủ lớn để bù overhead. Nhưng 32 partition tạo ra metadata, context, cursor và transaction tracking nhiều hơn; tăng lên hàng chục nghìn partition quá nhỏ có thể làm quá tải manager/JobRepository.

**`gridSize=32` không có nghĩa 32 JVM hoặc 32 concurrent tasks.** Nó là hint số phân vùng khi dùng partitioner tương ứng. Với partitioner dựa trên một manifest cố định, số partition có thể không trùng gridSize.

### 13.2. Ngân sách JDBC connection toàn cluster

Giả sử có 9 worker pods, mỗi pod có Hikari `maximumPoolSize=12` và một manager pool `maximumPoolSize=8`:

\[
C_{\max,\mathrm{configured}} = 9\times12+8=116
\]

Đây là tổng **trần connection từ các pool minh họa**, không phải số connection đồng thời luôn tồn tại. Chưa kể ứng dụng khác, replica manager, pool phụ hoặc kết nối vận hành. DB có thể không đủ CPU/IOPS dù giới hạn `max_connections` cho phép 116 connections.

Nếu reader dùng cursor connection dài hạn và writer cần transaction connection khác, số connection per worker StepExecution có thể cao hơn một. Cần đo Hikari active/pending, acquire latency và DB wait events thay vì giả sử “một worker = một DB connection”.

### 13.3. Băng thông và data locality

Trong remote partitioning, worker tự đọc dữ liệu; số message điều phối ít hơn remote chunking nhưng **lưu lượng dữ liệu nguồn** có thể tăng theo số worker. Ví dụ 9 pods cùng quét bảng không có index theo range có thể khiến database phải thực hiện 9 full table scans. Giải pháp có thể là index, snapshot được phân vùng vật lý, object storage hoặc sắp xếp partition theo data locality.

Nếu các worker chạy ở nhiều availability zones, chi phí network/cross-zone và quyền truy cập nguồn cũng có thể trở thành nút thắt cần đo.

## 14. Quan sát tiến độ và lỗi giữa các tiến trình

Ở remote step, **manager logs không đủ** vì phần lớn read/processor/write xảy ra trên worker JVM. Gắn nhãn/ID nhất quán:

| Tầng | Chỉ số cần đo |
| --- | --- |
| Manager | JobExecution ID, số partition đã tạo/gửi, pending, completed, failed, thời gian đợi replies/poll |
| Worker | Worker identity/pod, `StepExecutionId`, partition name, read/write/commit/rollback/skip counts, duration |
| Broker | Request backlog/oldest age, unacked, redelivery, DLQ, publish errors |
| JobRepository | Step status, update lag, stale `STARTED`, query/poll latency |
| Database | Connection active/pending, locks, deadlocks, query latency, IOPS, transaction TPS |
| JVM | CPU quota, GC, heap, thread count, resource saturation |
| Business output | Distinct IDs, số bản ghi bị bỏ sót, tổng tiền/checksum và freshness |
| SLA | Estimated completion, longest partition, recovery headroom, deadline risk |

### 14.1. Truy vấn metadata chỉ đọc

Ví dụ schema metadata Spring Batch mặc định:

~~~sql
SELECT
    je.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.START_TIME,
    se.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE je.JOB_EXECUTION_ID = :jobExecutionId
ORDER BY se.STEP_NAME;
~~~

Khi restart, cần xem **toàn bộ lịch sử JobExecution của cùng JobInstance**. Worker step `invoiceWorkerStep:range-02` có thể `FAILED` ở lần đầu và `COMPLETED` ở lần sau; chỉ truy vấn execution mới sẽ bỏ mất các partition đã thành công trong lần trước.

Không tự sửa `BATCH_STEP_EXECUTION.STATUS` thành `COMPLETED` khi timeout để “cho manager chạy tiếp”. Cần xác minh output, worker liveness, checkpoint và dùng quy trình recovery hợp lệ.

### 14.2. Partition skew và deadline

Nếu 31 partition hoàn tất sau 5 phút nhưng partition thứ 32 mất 40 phút, tổng job vẫn có thể đợi partition 32. Theo dõi **longest-running partition**, dữ liệu/bytes theo partition và tốc độ hoàn tất, không chỉ average worker duration.

Một ETA chỉ lấy `totalRemainingItems / aggregateRate` có thể lạc quan khi còn một shard lớn chạy tuần tự; ETA nên dựa trên critical path và kích thước partition còn lại.

## 15. Các sự cố đặc thù cần runbook

| Sự cố | Triệu chứng | Hướng xử lý có kiểm soát |
| --- | --- | --- |
| Worker chưa được deploy đúng version | StepLocator không thấy tên worker step | Khớp tên bean, contract và code version |
| Worker không vào được JobRepository | Lỗi load `StepExecutionRequest`/metadata | Kiểm tra datasource/network/credentials/schema |
| Message không được consume | Queue depth tăng, không có worker logs | Kiểm tra listener, routing, consumer count, DLQ |
| Worker crash trước commit | Partition `FAILED`/`STARTED`, output thiếu | Xác minh liveness, restart đúng JobInstance |
| Worker commit nhưng reply thất lạc | Output có dữ liệu, manager timeout | Kiểm tra repo; polling/reconciliation; không replay mù |
| Stale `STARTED` sau kill -9 | Metadata không phản ánh process đã chết | Dừng mọi worker cũ, đối soát, recovery theo thủ tục |
| Chạy đồng thời hai manager cùng snapshot | Overlap JobInstance/side effects | Khoá scheduling, kiểm tra identifying parameters |
| File input chỉ tồn tại trên manager | Worker `FileNotFoundException` | Dùng object/shared storage có URI/checksum |
| SQL range chồng lấn | Output nhân đôi/lock conflict | Unit test partitioner, biên khoảng, khóa duy nhất |
| DB connection pool cạn | Worker pending, timeout | Giảm concurrency, tối ưu transaction, tính toàn cluster |
| Broker gửi duplicate request | Nhiều execution request cho cùng ID | Metadata ownership, idempotent writer, tránh hai tiến trình cùng ghi |
| API external rate limit | 429/retry storm | Bounded retries, backoff/jitter, rate limit và idempotency |

Một lỗi remote thường xuất hiện **ở nhiều tầng**: message broker, worker runtime, JobRepository và business database. Runbook cần nêu thứ tự kiểm tra, owner và hành động được phép, không chỉ “retry job”.

## 16. Kế hoạch kiểm thử End-to-End

Tạo snapshot có 800.000 invoice với ID duy nhất, manifest cố định và một bảng kết quả có khóa `invoice_id`. Chạy manager và ít nhất ba worker JVM thực, dùng JobRepository bền vững.

| Kịch bản | Cách thực hiện | Điều cần xác minh |
| --- | --- | --- |
| Baseline một worker | Chỉ một worker process active | Output đúng, performance baseline |
| Nhiều worker | Chạy 3/6/9 replicas với 8/16/32 partitions | Throughput, scaling efficiency, DB/API budget |
| Coverage/disjointness | Test ID ở đúng biên range | Không thiếu/trùng invoice |
| Worker khác nhau nhận request | Quan sát StepExecutionRequest ID và worker pod | Worker xử lý đúng context, không dùng reader manager |
| Reply đảo thứ tự | Cố tình làm một worker chậm | Manager tổng hợp đúng theo partition, không phụ thuộc thứ tự |
| Polling repository | Chạy manager/worker không có reply channel | Manager xác nhận state bằng metadata và timeout đúng |
| Worker crash trước commit | Kill process giữa chunk | DB rollback phù hợp, restart hoàn tất |
| Worker crash sau commit | Giết ngay sau write, trước reply/metadata xác nhận | Output không nhân đôi sau replay/recovery |
| Manager crash | Kill manager khi còn partition đang chạy | Xác minh worker cũ, JobRepository, restart có kiểm soát |
| Broker restart | Restart broker khi request đang chờ | Lỗi thấy được và recoverable; không hứa delivery ngoài cấu hình |
| Mất shared repository | Chặn DB metadata tạm thời | Worker/manager không silently “success”, có alert |
| Stale worker khi restart | Cho worker cũ xử lý trễ khi manager mới bắt đầu | Chính sách fencing/ownership không gây overlap |
| Input bị sửa | Thay manifest/file giữa hai lần chạy | Từ chối phục hồi không an toàn hoặc yêu cầu reprocess |
| Partition skew | Một shard có gấp 10 lần data/CPU | Nhận diện longest partition và ETA đáng tin |
| DB throttling | Tăng lock latency/cạn Hikari pool | Backpressure, không tạo retry storm |
| Data reconciliation | So clean run với failed+restarted run | Cùng kết quả nghiệp vụ cuối cùng |

Chỉ tạo unit test cho `Partitioner.partition(gridSize)` là **chưa đủ**: phải thử worker chạy từ **một tiến trình riêng**, nạp state từ JobRepository, commit transaction thật và xử lý crash.

### 16.1. Bất biến nghiệm thu

~~~text
Distinct(output.invoice_id) == ExpectedDistinct(source.invoice_id)
No invoice outside approved snapshot is included
No invoice in approved snapshot is missing
Final amount matches independent reference calculation
Restarted run final output == clean-run final output
Each required partition has a verifiable terminal state
No unsafe concurrent old/new worker generation remains active
~~~

`BatchStatus.COMPLETED` của manager là điều kiện kỹ thuật cần thiết nhưng không thay thế đối soát dữ liệu. Với các tác dụng phụ ngoài transaction DB, còn cần các chỉ số chống gửi/trừ tiền lặp.

## 17. Khi nào không nên đưa Step ra remote JVM?

Không chọn remote partitioning chỉ vì dữ liệu nhiều. Nên cân nhắc giữ local khi:

- Job đang đạt SLA với headroom hợp lý và restart dễ kiểm soát.
- Nguồn dữ liệu không chia được an toàn hoặc mọi worker đều phải truy cập một shared mutable cursor.
- DB/API đã bão hòa; tăng JVM không tăng throughput hoàn tất.
- Workload quá nhỏ so với chi phí broker, JobRepository polling, deployment và vận hành.
- Không thể cấp quyền truy cập dữ liệu/metadata an toàn cho worker remote.
- Độ phức tạp crash/retry/rolling upgrade vượt năng lực giám sát và hỗ trợ của hệ thống hiện tại.

**Cách chọn mô hình:**

| Điều kiện | Mô hình đáng thử |
| --- | --- |
| Step tuần tự đã đủ nhanh | Chunk-oriented step local |
| Chunk độc lập, reader/processor/writer thread-safe trong một JVM | Multi-threaded step |
| Nhiều nhánh nghiệp vụ độc lập | Parallel steps |
| Input chia thành file/range, một JVM còn đủ tài nguyên | Local partitioning |
| Input chia shard, muốn scale reader và worker ra nhiều JVM | **Remote partitioning / remote StepExecution** |
| Reader tập trung đủ nhanh nhưng xử lý/ghi tốn tài nguyên | Remote chunking |
| Muốn chạy *toàn bộ job* ở process khác | Remote job launch/orchestrator — không phải remote partitioning |

Một quyết định kiến trúc tốt gồm **workload đo được, mục tiêu SLA, giới hạn downstream và kế hoạch failure recovery**, không phải chỉ số lượng pods hoặc `gridSize`.

## 18. Những hiểu nhầm phổ biến

| Nhận định | Vì sao sai hoặc chưa đủ? |
| --- | --- |
| “Remote Step là một API Spring Batch riêng.” | Tên bài mô tả execution giữa tiến trình; mô hình thường là remote partitioning của StepExecution. |
| “Worker chỉ nhận item rồi ghi output.” | Đó gần với remote chunking; remote partitioning để worker **tự đọc dữ liệu**. |
| “Mỗi remote worker là một JobInstance.” | Chúng thực thi StepExecution của job do manager điều phối. |
| “Message chứa toàn bộ file hoặc dữ liệu cần đọc.” | `StepExecutionRequest` chứa danh tính thực thi; input range nằm trong repository context. |
| “Manager không cần JobRepository chung.” | Worker cần truy cập metadata của cùng các JobExecution/StepExecution. |
| “Có reply queue thì không cần cập nhật StepExecution.” | Metadata là cơ sở phục hồi và tổng hợp trạng thái. |
| “Polling mode bắt buộc gửi reply.” | Có thể dựa trên JobRepository mà không cần reply channel. |
| “`gridSize=100` đồng nghĩa 100 worker JVM.” | Nó là hint phân vùng, không phải trần process/concurrency. |
| “Spring Batch bảo đảm mọi external effect chỉ xảy ra một lần.” | Metadata restart không tự tạo transaction phân tán với API/DB khác. |
| “Có thể đổi partition name để chạy lại partition lỗi.” | Đổi key có thể phá quan hệ StepExecution/ExecutionContext cũ. |
| “@StepScope tạo một reader duy nhất trên toàn cluster.” | Scope theo StepExecution; mỗi partition có reader và context riêng khi cấu hình đúng. |
| “Cứ mất reply là worker chưa ghi DB.” | Worker có thể đã commit nhưng manager chưa thấy tín hiệu. |

## 19. Checklist trước khi lên production

- [ ] Có mục tiêu throughput/SLA và baseline bottleneck được đo từ local implementation.
- [ ] Có chiến lược phân vùng đầy đủ, không trùng, tên ổn định và input snapshot bất biến.
- [ ] Manager và worker dùng chung JobRepository, đúng schema/prefix/version, quyền truy cập đủ và bảo mật.
- [ ] `StepExecutionRequest` được route tới đúng worker Step; `StepLocator` tìm được bean name.
- [ ] Đã chọn rõ **reply aggregation** hoặc **repository polling**; có timeout, alert và recovery.
- [ ] Middleware có competing consumers, policy durability/ACK/retry/DLQ và serialization phù hợp.
- [ ] Worker reader dùng đúng StepExecutionContext và checkpoint; các singleton processor/writer thread-safe.
- [ ] Writer có transaction/idempotency, side effect ngoài DB có cơ chế chống lặp riêng.
- [ ] Tổng DB/API connection budget tính trên **tất cả worker pods**, không riêng một JVM.
- [ ] Có metric per partition, longest partition, queue lag, stale StepExecution và SLA ETA.
- [ ] Test thành công sạch, failure trước/sau commit, manager crash, broker restart, stale worker và restart.
- [ ] Có runbook không sửa metadata tùy tiện, biết khi nào cần reconcile/reprocess.
- [ ] Tương thích code/schema khi rolling deploy được xác minh trước khi thay worker version.

## 20. Câu hỏi tự kiểm tra

1. Remote Step execution theo remote partitioning khác remote chunking ở việc **đọc item** diễn ra ở đâu?
2. `StepExecutionRequest` cần những thông tin nhận diện nào để worker tìm đúng metadata?
3. Vì sao manager và worker phải truy cập cùng một `JobRepository`?
4. Có hai cách nào để manager biết các partition remote đã hoàn tất? Khi nào polling hữu ích?
5. Nếu `range-02` đã `COMPLETED`, còn `range-03` `FAILED`, một lần restart đúng JobInstance sẽ xử lý thế nào theo chính sách mặc định?
6. `gridSize=32` nhưng chỉ có 8 consumer/worker capacity, có thể có bao nhiêu worker step chạy đồng thời?
7. Một remote worker commit dữ liệu rồi chết trước khi publish reply. Timeout có chứng minh worker chưa làm gì không?
8. Vì sao `@StepScope` giúp tránh chia sẻ cursor giữa các partition nhưng không bảo đảm writer singleton thread-safe?
9. Nếu có 9 worker pods với JDBC pool tối đa 12 connections/pod và 1 manager pool 8 connections, trần connection từ nhóm này là bao nhiêu?
10. Một bảng nguồn không có index trên cột partition key, 10 worker cùng query `BETWEEN`. Nút thắt tiềm ẩn là gì?
11. Vì sao thay `run.id` hoặc partition key sau lỗi không phải cách restart đúng?
12. Nên kiểm thử những tình huống nào để chứng minh khả năng phục hồi khi crash giữa broker, worker và DB?

**Gợi ý:** (1) Worker tự đọc shard trong remote partitioning; manager đọc trong remote chunking. (2) Tên worker step, JobExecution ID, StepExecution ID. (3) Worker tra context và cập nhật status/checkpoint đã được manager tạo. (4) Reply messages hoặc polling repository; polling tránh phụ thuộc reply route nhưng tăng reads. (5) Bỏ qua partition hoàn tất, chạy lại phần chưa hoàn tất nếu metadata/tên ổn định. (6) Khoảng 8, còn tùy listener concurrency và downstream. (7) Không, phải kiểm tra repo/output. (8) StepScope cô lập theo StepExecution; writer singleton vẫn có state/shared resources. (9) `9×12+8=116`. (10) Nhiều full table scans/I/O lock pressure. (11) Có thể tạo JobInstance khác hoặc làm mất mapping checkpoint. (12) Worker crash trước/sau commit, duplicate/lost request, mất reply, manager crash, stale execution, repository outage và đối soát output.

## Tài liệu tham khảo

- [Spring Batch 5.2 Reference — Scaling and Parallel Processing / Partitioning](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): manager/worker, `PartitionHandler`, `StepExecutionSplitter`, remote StepExecution và restart.
- [Spring Batch 5.2 Reference — Spring Batch Integration / Remote Partitioning](https://docs.spring.io/spring-batch/reference/5.2/spring-batch-integration/sub-elements.html): wiring remote partitioning, reply aggregation và JobRepository polling (kiểm tra đường dẫn theo bản tài liệu sử dụng).
- [Spring Batch 5.2 API — RemotePartitioningManagerStepBuilder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/partition/RemotePartitioningManagerStepBuilder.html): `partitioner`, `gridSize`, `outputChannel`, `inputChannel`, `pollInterval` và `timeout`.
- [Spring Batch 5.2 API — RemotePartitioningWorkerStepBuilder](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/partition/RemotePartitioningWorkerStepBuilder.html): tạo worker step, tích hợp `StepExecutionRequestHandler` và reply.
- [Spring Batch 5.2 API — StepExecutionRequest](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/partition/StepExecutionRequest.html): hợp đồng thông điệp tên step, JobExecution ID và StepExecution ID.
- [Spring Batch 5.2 API — MessageChannelPartitionHandler](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/integration/partition/MessageChannelPartitionHandler.html): hai cách nhận trạng thái từ worker và yêu cầu shared JobRepository.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint, `ItemStream` và chính sách restart.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): message channels, adapters, error channels và kết nối JMS/AMQP.

**Điểm cốt lõi:** Trong Spring Batch, **Remote Step giữa các tiến trình** chủ yếu là **remote partitioning**: manager chia dữ liệu thành những `StepExecution` có danh tính ổn định; worker ở JVM khác nhận `StepExecutionRequest`, tự đọc và xử lý shard rồi cập nhật **JobRepository chung**. Hệ thống chỉ mở rộng an toàn khi input partition không chồng lấn, checkpoint/restart đáng tin cậy, side effect idempotent, middleware được quan sát đầy đủ và concurrency được giới hạn theo khả năng thật của database/API.
