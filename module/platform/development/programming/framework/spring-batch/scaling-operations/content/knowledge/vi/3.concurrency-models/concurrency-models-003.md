# Multi-threaded Step trong Spring Batch

Một `Step` xử lý theo mô hình chunk mặc định thường đọc, xử lý và ghi từng chunk theo trình tự. Nếu phần lớn thời gian của mỗi chunk dùng để chờ cơ sở dữ liệu hoặc dịch vụ bên ngoài, việc cho **nhiều chunk chạy đồng thời trong cùng một step** có thể rút ngắn đáng kể thời gian hoàn tất job. **Multi-threaded Step** là một cách mở rộng như vậy trong Spring Batch.

Tuy nhiên, chỉ thêm `TaskExecutor` vào cấu hình step chưa đủ để một job vừa nhanh vừa đúng. Các thread có thể cùng truy cập `ItemReader`, `ItemProcessor`, `ItemWriter` và trạng thái step; thứ tự hoàn tất chunk không còn được bảo đảm, còn reader có cursor hoặc checkpoint có thể không an toàn khi chia sẻ. Cần hiểu rõ đơn vị đồng thời, transaction và ranh giới restart trước khi áp dụng trên dữ liệu lớn.

Bài học nằm trong chương **Mô hình đồng thời** của module **SPRING_BATCH_SCALING_OPERATIONS**. Nội dung đặt multi-threaded step trong bức tranh mở rộng Spring Batch bằng parallel steps, partitioning và các mô hình phân tán, đi cùng việc đo nút thắt, kiểm tra thread safety, retry/restart và chọn cấu hình theo tài nguyên thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mô hình nhiều thread xử lý các chunk của **một StepExecution**.
2. Cấu hình một `TaskExecutor` có giới hạn để tăng concurrency cho chunk-oriented step.
3. Nhận diện rủi ro thread safety của reader, processor, writer, listener, `ExecutionContext` và bean scope.
4. Hiểu vì sao chunk chạy song song có thể **commit không theo thứ tự đọc** và ảnh hưởng đến restart.
5. Thiết kế retry/skip/idempotency để bảo đảm kết quả nghiệp vụ khi có rollback hoặc lỗi worker.
6. Đo throughput, latency, DB connection, CPU, lock và queue để chọn mức đồng thời phù hợp.
7. So sánh multi-threaded step với parallel steps, partitioning, remote chunking và remote partitioning.

## 2. Multi-threaded Step thực chất song song hóa điều gì?

Một chunk-oriented step đọc dữ liệu thành từng nhóm, tùy chọn gọi `ItemProcessor` và truyền nhóm kết quả cho `ItemWriter`. Mỗi chunk có ranh giới giao dịch do `PlatformTransactionManager` tham gia quản lý.

Trong **step tuần tự**, một thread lần lượt đi qua các chunk:

~~~text
read chunk 1 -> process -> write -> commit
read chunk 2 -> process -> write -> commit
read chunk 3 -> process -> write -> commit
~~~

Trong **multi-threaded step**, framework dùng `TaskExecutor` để thực thi các lượt xử lý chunk trên nhiều thread, tùy cơ chế dispatch và giới hạn concurrency của phiên bản:

~~~text
                         ┌─ worker-1: chunk A -> process -> write -> commit
Step/StepExecution ──────┼─ worker-2: chunk B -> process -> write -> commit
                         ├─ worker-3: chunk C -> process -> write -> commit
                         └─ worker-4: chunk D -> process -> write -> commit
~~~

Dữ liệu trong từng chunk vẫn có thể được xử lý theo trình tự cục bộ của chunk, nhưng **các chunk khác nhau có thể chạy đồng thời** và hoàn tất lệch thứ tự. Không nên giả định rằng chunk đọc trước sẽ commit trước.

~~~mermaid
sequenceDiagram
    participant S as Step / Repeat Loop
    participant T1 as Worker thread 1
    participant T2 as Worker thread 2
    participant DB as Database
    S->>T1: Dispatch xử lý chunk A
    S->>T2: Dispatch xử lý chunk B
    T1->>T1: read/process/write A
    T2->>T2: read/process/write B
    T2->>DB: commit B
    DB-->>T2: OK
    T1->>DB: commit A
    DB-->>T1: OK
    Note over S,DB: Thứ tự commit B rồi A có thể xảy ra
~~~

**Điểm quan trọng:** Multi-threaded step vẫn là **một step logic**, một tên step, thường cùng **StepExecution** và bộ metadata chung. Nó không tự tạo ra StepExecution tách biệt cho mỗi worker thread. Đây là khác biệt lớn so với **partitioning**, nơi mỗi partition có StepExecution và `ExecutionContext` riêng.

### 2.1. Các giới hạn mà TaskExecutor không giải quyết

- `ItemReader` có thể vẫn là nút thắt tuần tự hoặc dùng cursor chung.
- Database chỉ có số lượng connection, CPU, IOPS và khả năng xử lý lock hữu hạn.
- `ItemWriter` có thể đồng bộ hóa nội bộ hoặc tranh chấp một khóa nghiệp vụ.
- Nhiều thread không tự động có thêm **CPU cores**.
- Trạng thái reader/step có thể khó checkpoint nhất quán hơn khi chunk chạy lệch thứ tự.
- Retry khi gặp lỗi có thể làm một item được xử lý lại; **single-thread hay multi-thread đều cần xem xét idempotency**.

## 3. Điều kiện nào khiến mô hình này có ích?

Multi-threaded step có ý nghĩa nhất khi:

1. Các item/chunk tương đối độc lập, không đòi hỏi thứ tự commit toàn cục.
2. Công việc chunk có phần chờ I/O có thể chồng lấp giữa các thread.
3. Reader, processor, writer và mọi tài nguyên được chia sẻ thực sự an toàn khi đồng thời.
4. Nguồn dữ liệu và đích ghi cho phép tăng concurrency mà không làm quá tải.
5. Chính sách checkpoint/restart được xác minh bằng thử nghiệm, đặc biệt sau crash và rollback.

Ví dụ: job làm giàu 500.000 khách hàng bằng cách truy vấn một API nội bộ rồi ghi kết quả theo `customer_id`. Nếu API trả lời chậm nhưng có quota đủ lớn, nhiều chunk đồng thời có thể che bớt thời gian chờ mạng. Tuy nhiên, nếu API chỉ cho phép 30 requests đồng thời hoặc writer dùng một DB có nhiều khóa nóng, tăng lên 100 thread sẽ tạo backlog và lỗi thay vì tăng tốc.

### 3.1. Ước lượng lý thuyết trước khi benchmark

Giả sử mỗi chunk có 200 item và thời gian hoàn tất trung bình 1 giây khi chạy một mình. Với bốn chunk worker độc lập, giới hạn lý tưởng của **tầng chunk** là:

\[
R_{\text{ideal}} \approx
\frac{4\ \text{chunk}}{1\ \text{s}} \times
200\ \text{item/chunk}
=800\ \text{item/s}.
\]

Đây chỉ là ước lượng. Nếu reader cung cấp tối đa 300 item/s hoặc writer commit tối đa 450 item/s, throughput thực tế không thể đạt 800 item/s dù có thêm worker threads.

Với workload dạng blocking I/O, công thức kinh nghiệm thường dùng làm điểm xuất phát là:

\[
N_{\text{threads}} \approx
N_{\text{CPU}}\left(1+\frac{T_{\text{wait}}}{T_{\text{CPU}}}\right).
\]

Ví dụ 4 core, mỗi tác vụ dùng 20 ms CPU và chờ 80 ms I/O thì công thức gợi ý khoảng 20 thread. Đây **không phải số tối ưu được bảo đảm**: ràng buộc HikariCP, giới hạn API, lock, memory và chi phí scheduling vẫn phải đo riêng. Khi các thread chờ **DB connection đã cạn**, tăng thread là sai hướng.

## 4. Cấu hình Java với Spring Batch

Ví dụ dùng **Spring Batch 5.2.x / Spring Boot 3.x**. Đây là cấu hình **khung**: `InputOrder`, `OutputOrder`, reader, processor, writer, datasource và transaction manager phải được định nghĩa phù hợp trong dự án.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class MultiThreadedStepConfig {

    @Bean
    public TaskExecutor chunkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(8);
        executor.setThreadNamePrefix("batch-chunk-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step enrichOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InputOrder> safeOrderReader,
            ItemProcessor<InputOrder, OutputOrder> safeOrderProcessor,
            ItemWriter<OutputOrder> safeOrderWriter,
            @Qualifier("chunkExecutor") TaskExecutor chunkExecutor) {

        return new StepBuilder("enrichOrdersStep", jobRepository)
                .<InputOrder, OutputOrder>chunk(200, transactionManager)
                .reader(safeOrderReader)
                .processor(safeOrderProcessor)
                .writer(safeOrderWriter)
                .taskExecutor(chunkExecutor)
                .build();
    }
}
~~~

Điều quan trọng nhất của ví dụ không nằm ở `setCorePoolSize(4)` mà ở các điều kiện dành cho ba bean mang tên `safe...`: **các bean đó phải thực sự phù hợp khi gọi đồng thời và phục hồi sau lỗi**. Đổi tên bean thành “safe” không tự tạo tính an toàn. Nếu bean reader đọc dữ liệu từ cursor chung không thread-safe, code vẫn có thể compile, job chạy thành công vài lần nhưng sai ngẫu nhiên khi tải lớn.

### 4.1. Hiểu đúng các tham số executor

| Tham số | Ý nghĩa |
| --- | --- |
| `corePoolSize` | Số thread lõi được giữ theo chính sách của executor |
| `maxPoolSize` | Trần thread executor có thể tạo |
| `queueCapacity` | Số task đang xếp hàng khi chưa có thread thực thi |
| `threadNamePrefix` | Hỗ trợ truy vết task và thread dump |
| `rejectedExecutionHandler` | Chính sách khi pool và queue đều hết sức chứa; cần chọn phù hợp với cơ chế dispatch |

Nếu `corePoolSize=4`, `maxPoolSize=4`, `queueCapacity=8` thì **4** là số thread thực thi tối đa của executor, **12 không phải mức đồng thời**. Queue 8 chỉ chứa task đợi lượt và có thể làm tăng thời gian nằm trong hệ thống.

Khi dùng `ThreadPoolTaskExecutor` mà `maxPoolSize > corePoolSize` và queue còn chỗ, executor thông thường ưu tiên đưa task vào queue trước khi tăng thêm thread vượt core. Vì vậy đặt `maxPoolSize=32` không có nghĩa job sẽ chạy ngay 32 chunk song song.

**Không dùng `SimpleAsyncTaskExecutor` không giới hạn với giả định nó là thread pool có giới hạn**. Đây là cách tạo thêm thread/tác vụ ngoài khả năng DB và API. Dùng executor có concurrency hữu hạn, đo queue/rejection và chọn cơ chế backpressure phù hợp.

### 4.2. Giới hạn đồng thời phụ thuộc phiên bản Spring Batch

Một số phiên bản Spring Batch 5.x vẫn sử dụng cơ chế throttling của repeat operations; `throttleLimit` đã được đánh dấu **deprecated từ Spring Batch 5.0**, nên không nên xem nó là giải pháp tuning lâu dài. Tài liệu khuyến nghị với nhu cầu thay thế throttling sử dụng `RepeatOperations` tùy biến qua `StepBuilder.stepOperations(...)`, có thể dựa trên executor với queue giới hạn.

Do đó, **pool size không luôn bằng số chunk thực sự chạy song song**: giới hạn tại tầng step/repeat operations, executor, reader lock, DB pool và downstream đều có thể thấp hơn. Khi sử dụng Spring Batch 6.x hoặc cấu hình mới, kiểm tra đúng API và tài liệu tương ứng. Mẫu ở mục 4 nhắm đến Spring Batch 5.2.x và không khẳng định mọi API là bất biến giữa các major version.

Không tùy tiện thêm cấu hình `throttleLimit(...)` chỉ để ép concurrency theo một ví dụ cũ, cũng không mặc nhiên suy rằng `maxPoolSize` là trần duy nhất của step.

## 5. Thread safety của ItemReader: rủi ro lớn nhất

`ItemReader.read()` thường duy trì trạng thái như vị trí cursor, số dòng hiện tại, trang tiếp theo hoặc cache. Nhiều reader được thiết kế cho một luồng gọi, không cho nhiều thread cùng gọi trên **một instance**.

Giả sử một reader dùng biến `position` không đồng bộ:

~~~java
// VÍ DỤ SAI: minh họa data race, không phải reader sản xuất.
class UnsafeReader {
    private int position;

    String read() {
        int i = position; // hai thread có thể cùng đọc i
        position = i + 1;
        return loadByIndex(i); // cùng item bị lấy hai lần
    }

    private String loadByIndex(int index) {
        return "row-" + index;
    }
}
~~~

Nếu hai thread cùng đọc `position=42` trước khi có thread nào ghi lại, cả hai có thể trả item 42. Một item khác bị bỏ qua hoặc được ghi trùng. Lỗi thường không tái lập được khi chạy một thread nên phải kiểm thử có tải đồng thời.

### 5.1. Dùng synchronized reader khi phù hợp

Spring Batch có `SynchronizedItemStreamReader` để đồng bộ hóa lời gọi `read()` trên delegate:

~~~java
import org.springframework.batch.item.ItemStreamReader;
import org.springframework.batch.item.support.SynchronizedItemStreamReader;
import org.springframework.batch.item.support.builder.SynchronizedItemStreamReaderBuilder;

public SynchronizedItemStreamReader<InputOrder> synchronizedReader(
        ItemStreamReader<InputOrder> delegate) {

    return new SynchronizedItemStreamReaderBuilder<InputOrder>()
            .delegate(delegate)
            .build();
}
~~~

Cách này có thể làm lời gọi `read()` an toàn hơn nếu delegate không thread-safe, nhưng:

- Nó **chỉ đồng bộ hóa việc đọc qua wrapper**, không biến mọi trạng thái/side effect của delegate thành an toàn khi concurrency.
- Nó có thể **serialize phần đọc**, làm reader trở thành nút thắt khi đọc lâu.
- Tài liệu Spring Batch cảnh báo rằng dùng `SynchronizedItemStreamReader` có thể làm job **không restartable một cách đúng đắn** nếu xử lý lại item gây vấn đề; checkpoint và thứ tự commit của các chunk vẫn cần được kiểm thử.
- Không sử dụng `saveState(false)` như “cách sửa đơn giản” nếu nghiệp vụ yêu cầu restart từ checkpoint. Tắt lưu trạng thái thường có nghĩa reader không thể tự resume từ vị trí đã commit.

Đây là giải pháp được cân nhắc cho workload có cách xử lý trùng an toàn, không phải bảo đảm chung rằng mọi reader stateful đã hỗ trợ multi-threaded step.

### 5.2. Paging reader cũng cần kiểm tra hợp đồng

Một số reader JDBC paging có thể hỗ trợ truy cập từ nhiều thread ở một phạm vi nhất định, nhưng khả năng thread-safe phải được kiểm tra theo **loại reader, phiên bản, điều kiện lifecycle** và `saveState`. Đừng kết luận rằng “đã dùng pagination thì mặc định restartable với nhiều thread”.

Nếu dùng query paging, cần có **sort key duy nhất, ổn định**, snapshot dữ liệu phù hợp và chiến lược chống chồng lấn khi nguồn bị thay đổi. Thêm `ORDER BY` trên một cột không duy nhất có thể làm record bị lặp/bỏ sót giữa các trang.

### 5.3. Tại sao @StepScope chưa đủ?

Trong **một multi-threaded step**, nhiều worker threads thường chia sẻ **cùng một StepExecution**. Bean đánh dấu `@StepScope` được quản lý theo **StepExecution**, không tự tạo một instance mới cho mỗi chunk thread. Vì vậy:

~~~text
Một StepExecution
    ├─ thread A -> cùng StepScopedReader instance
    ├─ thread B -> cùng StepScopedReader instance
    └─ thread C -> cùng StepScopedReader instance
~~~

`@StepScope` hữu ích để nhận `jobParameters` hoặc `stepExecutionContext`, nhưng **không mặc nhiên** giải quyết data race trong cùng StepExecution.

Với **partitioning**, mỗi partition có StepExecution riêng; khi worker step dùng `@StepScope`, các partition có thể sở hữu reader và context độc lập. Nếu dữ liệu chia thành file, khoảng ID hoặc shard rõ ràng và restart là ưu tiên cao, đây thường là phương án dễ kiểm soát hơn.

## 6. ItemProcessor, ItemWriter và listener cũng phải an toàn

Processor dạng stateless thường dễ chạy đồng thời:

~~~java
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public final class TaxProcessor implements ItemProcessor<Invoice, InvoiceTotal> {
    @Override
    public InvoiceTotal process(Invoice invoice) {
        BigDecimal tax = invoice.amount()
                .multiply(new BigDecimal("0.08"));
        return new InvoiceTotal(invoice.id(), invoice.amount().add(tax));
    }
}
~~~

Đây là ví dụ mô hình dữ liệu bất biến (`Invoice`/`InvoiceTotal` là record hoặc class immutable do ứng dụng định nghĩa). Không có biến instance `currentInvoice`, `runningTotal` mutable được chia sẻ, nên giảm rủi ro data race. Vẫn phải xét service mà processor gọi: client không thread-safe hoặc rate limit có thể là vấn đề.

Một ví dụ **sai**:

~~~java
class UnsafeProcessor {
    private long processedCount = 0; // data race nếu nhiều thread gọi

    Output process(Input input) {
        processedCount++;             // mất cập nhật, không bền vững
        return transform(input);
    }
}
~~~

`processedCount++` không nguyên tử; nhưng thay bằng `AtomicLong` cũng **không** tự tạo tính đúng đắn khi rollback, retry hoặc restart vì đó là đếm ở bộ nhớ ứng dụng, không đồng nhất với số item commit thành công. Hãy lấy số liệu giao dịch từ `StepExecution`/metric phù hợp hoặc dùng cơ chế ghi transactionally được thiết kế riêng.

Với writer cần xác định:

- Có dùng biến instance mutable hoặc buffer dùng chung không?
- SQL có ghi lên cùng bản ghi và tranh chấp row lock không?
- Writer có transaction-aware không, và có giữ connection trong lúc gọi dịch vụ bên ngoài không?
- Nếu chunk bị rollback/rerun, tác dụng ghi có lặp hoặc tăng tiền hai lần không?
- Nếu writer gọi API tạo side effect, có idempotency key hoặc outbox không?
- Listener (`ItemReadListener`, `ChunkListener`, `StepExecutionListener`...) có chia sẻ state thiếu đồng bộ không?

Không phải mọi implementation `ItemWriter` đều có cùng mức bảo đảm thread safety. Đọc hợp đồng của **implementation cụ thể** và thử nghiệm concurrency ở đúng workload, kể cả khi bean không có biến instance rõ ràng.

## 7. Transaction, commit order và retry

Mỗi chunk thông thường có transaction riêng, nhưng khi chạy nhiều thread, các transaction có thể **commit không theo thứ tự đọc**.

Giả sử chunk A chứa các event cũ của account X, chunk B chứa event mới của cùng account:

~~~text
Thread A: cập nhật trạng thái X <- phiên bản 1, xử lý chậm
Thread B: cập nhật trạng thái X <- phiên bản 2, commit trước
Thread A: commit phiên bản 1 sau đó
=> trạng thái X cuối cùng bị ghi đè bằng dữ liệu cũ
~~~

Nếu dữ liệu phụ thuộc thứ tự theo một khóa, multi-threaded step cần chiến lược giữ thứ tự theo khóa, kiểm soát version, optimistic locking hoặc phân vùng khóa sang các luồng xử lý tuần tự. Không thể dựa vào “reader đã trả phiên bản 1 trước phiên bản 2” để bảo đảm thứ tự commit.

### 7.1. Idempotency bảo vệ khi xử lý lại

Ví dụ PostgreSQL upsert kết quả tổng hợp xác định:

~~~sql
CREATE TABLE order_enrichment (
    order_id BIGINT PRIMARY KEY,
    score INTEGER NOT NULL,
    source_version BIGINT NOT NULL
);

INSERT INTO order_enrichment (order_id, score, source_version)
VALUES (:order_id, :score, :source_version)
ON CONFLICT (order_id)
DO UPDATE SET
    score = EXCLUDED.score,
    source_version = EXCLUDED.source_version
WHERE order_enrichment.source_version <= EXCLUDED.source_version;
~~~

Ví dụ giả định dữ liệu có `source_version` tăng đơn điệu theo nghiệp vụ. Điều kiện ở `WHERE` ngăn kết quả cũ ghi đè phiên bản mới, còn khóa chính giúp tránh tạo bản ghi trùng. Với **cùng phiên bản nhưng payload mâu thuẫn**, cần thêm quy tắc phát hiện conflict; không tự coi upsert là đủ cho mọi nghiệp vụ.

Ngược lại:

~~~sql
-- Không idempotent: retry cùng item có thể cộng tiền nhiều lần.
UPDATE account_balance
SET balance = balance + :amount
WHERE account_id = :account_id;
~~~

Khi cần cộng tiền, gửi email hoặc gọi thanh toán, hãy dùng khóa idempotency bền vững, unique constraint, transactional outbox hoặc cơ chế phù hợp với đích. **Một thread/transaction rollback không thể tự rollback một HTTP API đã hoàn tất ở hệ thống khác.**

### 7.2. Retry và skip với nhiều thread

Spring Batch fault-tolerant step hỗ trợ các chính sách retry/skip, nhưng khi các chunk cùng chạy:

- Retry có thể tăng tải đột ngột lên database hoặc API đang chậm.
- Một item/transaction có thể được thử lại; thiết kế writer phải chịu được lặp.
- Thứ tự log lỗi có thể khác thứ tự dữ liệu đầu vào.
- Các bộ đếm skip/retry và trạng thái step phải được quan sát bằng framework và metrics phù hợp; không tự quản lý bộ đếm toàn cục bằng biến mutable không an toàn.
- Skip một item chỉ hợp lệ khi business quy định rõ lỗi có thể chấp nhận, có log và đối soát chất lượng.

Khi timeout hoặc rate limit tăng, tăng thread và retry vô hạn sẽ tạo **retry storm**. Đặt backoff, giới hạn số lần, quota in-flight và cơ chế báo lỗi phân loại được.

## 8. Restartability và ExecutionContext: điều kiện cần kiểm chứng

Một số job sau khi thêm `taskExecutor(...)` vẫn chạy được bình thường nhưng **không phục hồi đúng sau crash**. Nguyên nhân thường không nằm ở StepBuilder mà ở cách reader/processor/writer dùng shared state và cách checkpoint liên hệ với các chunk commit không theo thứ tự.

Ví dụ reader tuần tự phát item 1–400 cho hai chunk:

~~~text
Chunk A: items 1..200 -> xử lý chậm, chưa commit
Chunk B: items 201..400 -> commit trước
          |
          v
Nếu checkpoint bị đẩy tới 400 mà A thất bại,
restart từ 401 có thể bỏ mất items 1..200.
~~~

Đây là **kịch bản rủi ro minh họa**; hành vi checkpoint chính xác phụ thuộc loại reader, cách lưu `ItemStream` state, phiên bản framework và ranh giới transaction. Bài học là phải **chứng minh** rằng checkpoint tương ứng với tập dữ liệu thực sự đã commit, không suy luận từ thứ tự gọi `read()`.

`ExecutionContext` lưu trạng thái phục vụ restart của step. Với multi-threaded step, nhiều chunk cùng tham gia một StepExecution, vì vậy không nên để các thread tự ý ghi các key context dùng chung mà không có thiết kế concurrency và transaction phù hợp.

### 8.1. Checklist restart trước khi triển khai

1. Reader có stateful không? Có chia sẻ cursor/position giữa threads không?
2. `ItemStream.open/update/close` có được sử dụng đúng lifecycle và metadata không?
3. Nếu chunk sau commit trước chunk trước, checkpoint có bảo toàn dữ liệu chưa commit không?
4. Data source có thể được đọc lại ổn định theo key/snapshot không?
5. Writer có idempotent/transaction-aware không?
6. Nếu thread crash hoặc process dừng đột ngột, output và JobRepository có thể khôi phục nhất quán không?
7. Nếu job đã phát tác dụng phụ ra API, có cơ chế dedup hoặc đối soát khi restart không?
8. Có cần chuyển sang **partitioning với StepExecution riêng** để đơn giản hóa restart không?

Một cấu hình tắt `saveState` có thể tránh xung đột checkpoint trong một số reader, nhưng thường đánh đổi khả năng khôi phục vị trí đọc. Phải cân nhắc đây là **chủ đích nghiệp vụ**, không phải cách sửa chung cho job cần restart.

## 9. Giới hạn pool size theo DB và downstream

Giả sử có 8 worker threads, mỗi chunk giao dịch lấy một connection DB, HikariCP có `maximumPoolSize=4`:

~~~text
TaskExecutor: 8 thread đang bận
             ├─ 4 thread giữ JDBC connection, xử lý DB
             └─ 4 thread chờ mượn connection
HikariCP: 4 connections tối đa
~~~

Nếu mỗi transaction giữ connection lâu, chỉ bốn chunk có thể cùng làm việc với DB. Tăng lên 16 worker threads có thể chỉ tăng thời gian chờ và nguy cơ `connectionTimeout`.

Cần dự trù connection cho cả `JobRepository`, các step khác và các pod khác dùng cùng database. Một pool 8 connection **trên mỗi pod** với 5 pod có trần lên đến 40 connection chỉ từ nhóm này, chưa kể tải online.

### 9.1. Kịch bản benchmark giả lập

Giả sử chunk size cố định 200 item, dữ liệu đại diện và DB không có tải khác:

| Worker threads | Throughput commit (items/s) | DB connection pending | p95 chunk latency | Nhận định |
| ---: | ---: | ---: | ---: | --- |
| 1 | 300 | 0 | 700 ms | Baseline |
| 2 | 570 | 0 | 750 ms | Tăng tốc rõ |
| 4 | 1.020 | 0 | 900 ms | Còn lợi ích |
| 8 | 1.160 | 3 | 1.900 ms | Bắt đầu nghẽn DB |
| 12 | 1.120 | 7 | 3.400 ms | Tăng chờ, throughput giảm |

**Đây là số giả lập**, không phải benchmark của Spring Batch. Trong tình huống này, lựa chọn 4 thread có thể tốt hơn 8 vì throughput đã gần điểm bão hòa, độ trễ thấp hơn và còn headroom cho restart.

Không quyết định chỉ bằng thời gian hoàn tất job một lần. Cần đo cả **p95/p99 chunk latency, CPU, I/O, DB locks, Hikari pending, retry rate và số item ghi đúng cuối cùng**.

### 9.2. Chunk size và concurrency là hai trục riêng

- `chunk(200)` nghĩa là mỗi chunk thường commit sau 200 item, không có nghĩa 200 threads.
- Pool size 8 nghĩa là executor có thể chạy tối đa 8 task đồng thời (theo cấu hình minh họa), không đồng nghĩa mọi task đang làm việc hiệu quả.
- Chunk lớn giảm overhead commit nhưng giữ transaction/lock lâu và làm tăng lượng dữ liệu có thể cần xử lý lại khi lỗi.
- Chunk nhỏ tạo nhiều transaction và overhead, nhưng thường rút ngắn lock duration và giảm phạm vi rollback.

Thử tuning **một biến mỗi lần**: cố định chunk size khi chọn pool, sau đó tối ưu chunk size theo throughput, bộ nhớ, lock và recovery.

## 10. So sánh các mô hình concurrency của Spring Batch

| Mô hình | Đơn vị song song | Metadata/checkpoint | Phù hợp khi |
| --- | --- | --- | --- |
| **Multi-threaded step** | Nhiều chunk của **một step** qua executor | Thường chia sẻ một StepExecution; restart với shared state phải rất thận trọng | Item/chunk độc lập, reader/writer an toàn khi đồng thời, cần tăng throughput đơn giản trong một JVM |
| **Parallel steps** | Các step/flow độc lập | Mỗi step có StepExecution của mình | Có nhiều pipeline/nhánh không phụ thuộc nhau |
| **Local partitioning** | Nhiều partition của một worker step trong một JVM | Mỗi partition có StepExecution/ExecutionContext riêng | Có thể chia dữ liệu theo file, ID range hoặc key ổn định |
| **Remote chunking** | Manager đọc/chia chunk, workers xử lý/ghi qua middleware | Manager quản lý đọc/chunk; worker request/reply cần reliability | Reader tập trung đủ nhanh, processor/writer tốn tài nguyên và cần scale sang nhiều máy |
| **Remote partitioning** | Nhiều worker step execution trên máy khác | Partition metadata và restart cần phối hợp qua JobRepository/transport | Workload phân tách shard, dữ liệu và worker phân tán được |

Không có phương án nào “luôn nhanh nhất”. Ví dụ:

- Nếu **reader DB tuần tự** đã là nút thắt, remote chunking không tự mở rộng reader.
- Nếu **reader stateful khó đồng bộ**, local partitioning có reader riêng thường dễ giữ tính đúng đắn hơn.
- Nếu có các step rõ ràng độc lập, parallel flows có thể tiết kiệm nhiều công sức hơn sửa toàn bộ step thành thread-safe.
- Nếu DB writer đã bão hòa, chuyển từ 4 threads sang 40 worker pods không tăng throughput hữu ích và có thể tạo lỗi giao dịch.

### 10.1. Lưu ý về bean scope

`@StepScope` ở partitioned worker thường tạo instance theo **StepExecution của từng partition**. Trong multi-threaded step, nhiều chunk threads có chung StepExecution nên **có thể chung instance StepScoped bean**.

Đối với `@JobScope`, Spring Batch có hạn chế thực tế khi dùng trong multi-threaded hoặc partitioned execution vì framework không luôn kiểm soát việc khởi tạo context trên các thread người dùng tạo. Tránh coi JobScope như giải pháp đồng bộ state; kiểm tra khuyến nghị của version đang chạy.

## 11. Quan sát hiệu năng và tính đúng đắn

Tối thiểu ghi metric theo job/step cùng biểu đồ tài nguyên:

| Nhóm | Chỉ số | Điều cần xác định |
| --- | --- | --- |
| Batch | `readCount`, `writeCount`, `commitCount`, `rollbackCount`, `skipCount` | Có tiến độ, lỗi, rollback bất thường không? |
| Chunk | duration p50/p95/p99, committed items/s | Thực sự hoàn tất nhiều item hơn hay chỉ submit nhiều task hơn? |
| Executor | active threads, queue size, rejected tasks | Có vượt concurrency, queue tăng không? |
| JDBC pool | active/idle/pending/acquire timeouts | Thread đang chờ connection hay DB đã bão hòa? |
| Database | CPU, locks, wait events, IOPS, query latency | Nút thắt ở DB và tranh chấp row/index? |
| HTTP/broker | concurrency, latency, rate limit, retries | Nguồn API hoặc middleware có giới hạn? |
| JVM | CPU quota, heap/GC, thread count | Tăng thread gây áp lực bộ nhớ hoặc scheduling? |
| Data quality | unique keys, totals, reconciliation | Có đọc trùng, bỏ sót hoặc ghi sai sau restart không? |

Khi dùng Micrometer/Spring Boot Actuator, metric tên cụ thể phụ thuộc phiên bản và instrumentation đã cấu hình. Không suy luận từ một metric chưa được phát ra. Nên gắn `jobExecutionId`, `stepExecutionId` và thread name trong log khi điều tra race; tránh tạo metric label có độ phân biệt quá cao cho từng item ID.

### 11.1. Không dùng StepExecution counts như bằng chứng duy nhất

Với multi-threaded step, các thread chia sẻ StepExecution nên `readCount`/`writeCount` tổng hợp có thể hữu ích để nhìn tiến độ, nhưng **chưa chứng minh được output đúng**. Cần đối soát dữ liệu nguồn và đích bằng khóa nghiệp vụ, số lượng, checksum/tổng tiền hoặc các bất biến khác. Khi chunk retry/skip, read count cũng không nhất thiết bằng số record cuối cùng được ghi bền vững.

Trong benchmark, hãy kiểm tra:

~~~text
Unique business IDs written
    == valid expected unique IDs

No missing IDs
No duplicate business effects
All committed outputs satisfy reconciliation
Job restart preserves the same final result
~~~

## 12. Kịch bản thực hành: xử lý 1 triệu đơn hàng

Bối cảnh: `orderEnrichmentJob` có 1.000.000 order, mỗi item gọi một dịch vụ chấm điểm rồi lưu `score` vào PostgreSQL. Có 8 CPU cores, HTTP API hỗ trợ tối đa 40 requests đồng thời và HikariCP giới hạn 12 connections cho batch.

**Bước 1 — xác định mục tiêu:** xử lý trong 25 phút, cần throughput hoàn tất:

\[
1{,}000{,}000/(25\times60)\approx667\ \text{item/s}.
\]

**Bước 2 — baseline:** một thread đạt 120 items/s, nhưng khi tăng lên 4 threads được 430 items/s; tăng đến 8 threads đạt 650 items/s; 12 threads chỉ đạt 670 items/s và API p95 latency tăng cao. Số đo là **giả định để giải thích**.

**Bước 3 — đánh giá nút thắt:** nếu API đã gần quota, tăng threads từ 8 lên 16 có thể chỉ làm tăng timeout. Cần phân tích API service time và số requests in-flight. Nếu mỗi item có một request và API latency trung bình 10 ms thì 667 requests/s yêu cầu trung bình khoảng 6,67 request in-flight theo Little's law; nhưng p95 và quota cũng quan trọng. Với latency trung bình 100 ms, yêu cầu cùng throughput tương ứng khoảng 67 requests in-flight, **vượt quota 40**, nên mục tiêu này không khả thi nếu không cải thiện service time/rate limit hoặc thay đổi xử lý.

**Bước 4 — bảo vệ kết quả:** dùng output `order_id` làm unique key, upsert theo version nguồn và xác minh retry không làm ghi lặp. Reader phải an toàn với nhiều chunk thread; nếu không kiểm chứng được checkpoint, chia order thành các ID ranges để chuyển sang partitioning.

**Bước 5 — kiểm tra SLA:** mục tiêu 25 phút không được coi là đạt khi job chỉ nhanh ở lần chạy đầu mà crash/restart làm mất dữ liệu hoặc kéo dài vượt cửa sổ. Đo cả recovery và downstream publish nếu chúng thuộc SLA.

### 12.1. Bộ kiểm thử concurrency tối thiểu

| Kiểm thử | Thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Baseline tuần tự | Chạy 1 thread với input cố định | Dữ liệu đúng, có số đo so sánh |
| Concurrency 2/4/8 | Tăng từng mức, giữ nguyên input/chunk size | Throughput biến đổi được đo; output cuối giống baseline |
| Race ở reader | Cố ý tạo I/O read chậm hoặc interleaving nhiều thread | Không thiếu/trùng ID hoặc xác định reader hiện tại không phù hợp |
| Commit đảo thứ tự | Làm một chunk xử lý chậm hơn chunk sau | Không ghi đè trạng thái nghiệp vụ mới bằng bản cũ |
| Rollback + retry | Gây DB timeout trong một chunk | Retry có giới hạn, dữ liệu ghi bền vững đúng |
| Kill process giữa chừng | Dừng sau một vài chunk commit, rồi restart đúng JobInstance | Không mất item, không tác dụng phụ trùng |
| Pool exhaustion | Giảm Hikari pool/giả lập DB chậm | Job không tạo hàng đợi vô hạn; có timeout và metric rõ |
| API 429/503 | Giả lập rate limit | Backoff và giới hạn concurrency; không retry storm |
| Peak và skew | Một số item xử lý lâu gấp nhiều lần | Deadline và tail latency vẫn kiểm soát được |

Đặc biệt, phải phân biệt **test một lần thành công** với **bảo đảm restart an toàn**. Nếu reader không có cơ chế checkpoint có thể chứng minh, test kill/restart thường là bằng chứng để **chọn partitioning** thay vì cố tăng thread cùng một StepExecution.

## 13. Những sai lầm phổ biến

| Nhận định | Vấn đề |
| --- | --- |
| “Thêm `taskExecutor(...)` là đủ để step thread-safe.” | Reader, processor, writer và listener có thể chứa shared mutable state. |
| “Mỗi thread có một StepExecution riêng.” | Multi-threaded step thường dùng **cùng StepExecution**; partitioning mới có StepExecution theo partition. |
| “`@StepScope` tạo reader riêng cho mỗi thread.” | Scope theo StepExecution, không theo thread chunk. |
| “Synchronized reader đồng nghĩa restart an toàn.” | Đồng bộ `read()` chưa giải quyết commit lệch thứ tự và checkpoint. |
| “Chunk A đọc trước nên chắc chắn commit trước chunk B.” | Scheduler/DB có thể cho chunk B commit trước. |
| “`maxPoolSize=32` nghĩa luôn có 32 chunk đồng thời.” | Queue, core size, throttle/repeat operations và downstream có thể giới hạn. |
| “Bị nghẽn connection thì thêm thread sẽ nhanh hơn.” | Thường chỉ làm thêm task chờ và tăng timeout. |
| “Atomic counter ở processor là tiến độ đã commit.” | Counter có thể đếm item bị rollback/retry và mất khi restart. |
| “Writer JDBC mặc nhiên chống xử lý lại.” | Cần transaction, unique key, idempotency và quy tắc version rõ ràng. |
| “Job chạy nhanh hơn nên không cần test failure.” | Concurrency có thể làm lỗi chỉ xuất hiện sau crash, retry hoặc restart. |

## 14. Checklist trước khi bật Multi-threaded Step trên production

- [ ] Có lý do định lượng để scale: CPU/I/O profile, throughput hiện tại, SLA cần đạt.
- [ ] Biết chính xác **đơn vị chạy đồng thời** là chunk trên một StepExecution.
- [ ] Reader có hợp đồng thread-safe được xác minh hoặc giải pháp đọc dữ liệu phân tách rõ ràng.
- [ ] Processor/writer/listener không dùng shared mutable state thiếu đồng bộ.
- [ ] Không dựa vào thứ tự commit toàn cục; nghiệp vụ có quy tắc order/version phù hợp.
- [ ] Writer và external side effects có giao dịch/idempotency đủ cho retry.
- [ ] Reader/checkpoint/ExecutionContext được kiểm chứng sau rollback và restart.
- [ ] Executor có trần concurrency/queue, cơ chế rejection/backpressure đã hiểu.
- [ ] Tổng JDBC/HTTP/broker connections từ tất cả steps và pod không vượt ngân sách downstream.
- [ ] Có benchmark 1, 2, 4, 8 threads với input đại diện và một biến thay đổi mỗi lần.
- [ ] Theo dõi throughput commit, tail latency, active/pending pool, DB locks và số lỗi.
- [ ] Có thử nghiệm kill/restart, đối soát output và runbook rollback về cấu hình an toàn.
- [ ] Nếu restart khó kiểm soát, đã đánh giá chuyển sang local/remote partitioning.

## 15. Câu hỏi tự kiểm tra

1. Multi-threaded step song song hóa **chunk** hay tạo nhiều `JobExecution`? Vì sao khác với partitioning?
2. Nếu một reader giữ `position` trong biến instance và được 8 chunk threads gọi cùng lúc, lỗi nào có thể xảy ra?
3. `@StepScope` có bảo đảm reader được tạo riêng cho mỗi chunk thread không?
4. Vì sao synchronized `read()` chưa đủ chứng minh restart đúng sau khi chunk sau commit trước chunk trước?
5. Executor có core=4, max=8, queueCapacity=100. Có thể suy rằng nó sẽ tăng lên 8 thread ngay sau khi có 5 task không?
6. Một step chạy 16 threads nhưng Hikari max=4; mọi chunk giữ connection trong suốt transaction. Bạn sẽ đo gì và thay đổi theo hướng nào?
7. Job xử lý event phiên bản 1 và 2 cho cùng đơn hàng. Nếu phiên bản 1 commit sau phiên bản 2, writer phải làm gì?
8. Nếu một job cần restart chính xác theo file hoặc khoảng ID, mô hình nào thường dễ cấp reader/checkpoint riêng hơn?
9. Nếu throughput ngừng tăng ở 8 threads trong khi HTTP 429 tăng, việc tăng `maxPoolSize` lên 32 sẽ có rủi ro gì?
10. Làm cách nào chứng minh kết quả cuối cùng vẫn đúng khi retry, rollback và process crash?

**Gợi ý:** (1) Nhiều chunk của một StepExecution; partitioning có StepExecution cho từng partition. (2) Đọc trùng/bỏ sót item. (3) Không, scope theo StepExecution. (4) Checkpoint có thể lệch tập item đã commit. (5) Không, queue thường được dùng trước khi tăng vượt core. (6) Hikari pending, acquire latency, connection hold time và DB wait; cân nhắc giảm threads/tối ưu transaction hoặc tăng năng lực DB sau khi đo. (7) Khóa version/optimistic locking hoặc routing theo key. (8) Partitioning. (9) Retry storm, queue/timeout và DB/API quá tải. (10) Kiểm thử failure có dữ liệu đối soát và trạng thái JobRepository thực tế.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps, partitioning và remote processing.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `ItemStream`, checkpoint và restart của step.
- [Spring Batch Reference — Step Scope](https://docs.spring.io/spring-batch/reference/step/late-binding.html): scope theo StepExecution và các giới hạn thực tế trong multi-threading/partitioning.
- [Spring Batch API — SynchronizedItemStreamReader](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/item/support/SynchronizedItemStreamReader.html): đồng bộ `read()` và cảnh báo restartability.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `ThreadPoolTaskExecutor`, queue và tham số pool.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): quan hệ giữa pool connection và năng lực database.

**Điểm cốt lõi:** Multi-threaded Step có thể cải thiện throughput bằng cách cho **nhiều chunk của cùng một step chạy đồng thời**. Lợi ích chỉ bền vững khi reader, processor, writer và trạng thái checkpoint được thiết kế đúng; thứ tự commit và tốc độ không tự động được bảo đảm. Hãy giới hạn concurrency theo tài nguyên thực, đo bằng throughput commit và đối soát dữ liệu sau retry/restart. Nếu cần cô lập state và checkpoint từng shard, cân nhắc partitioning.
