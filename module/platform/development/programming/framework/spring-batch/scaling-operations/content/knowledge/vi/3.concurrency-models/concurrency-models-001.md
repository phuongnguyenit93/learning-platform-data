# TaskExecutor trong Spring Batch

## 1. Vì sao cần hiểu TaskExecutor khi mở rộng Spring Batch?

Một job Spring Batch thông thường xử lý các bước (`Step`) theo thứ tự; với **chunk-oriented step**, một luồng đọc một nhóm bản ghi, xử lý, ghi kết quả và commit. Mô hình này dễ kiểm soát nhưng có thể không sử dụng hết CPU hoặc phải chờ nhiều thời gian cho I/O (cơ sở dữ liệu, tệp, HTTP).

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, mục tiêu là mở rộng Spring Batch cho workload dữ liệu lớn bằng nhiều luồng, các step song song, partitioning hoặc xử lý phân tán, đồng thời đo nút thắt và giữ tính đúng đắn khi retry/restart. **`TaskExecutor` là một cơ chế nền tảng để phân phối công việc chạy đồng thời trong *một JVM*.** Nó hữu ích, nhưng tự thêm executor không bảo đảm job chạy nhanh hơn hoặc an toàn hơn.

Ví dụ: một step nạp 2 triệu giao dịch phải gọi dịch vụ chuẩn hóa dữ liệu. Nếu phần lớn thời gian của mỗi giao dịch dành cho chờ I/O, một số chunk chạy đồng thời có thể tăng throughput. Ngược lại, nếu tất cả các chunk đều chờ cùng một bảng bị khóa hoặc cùng connection pool đã hết chỗ, tăng số luồng có thể làm toàn bộ job chậm hơn.

Sau bài học, bạn cần có khả năng:

- Phân biệt **TaskExecutor**, **thread pool**, **multi-threaded step**, **parallel steps** và **partitioning**.
- Cấu hình executor có giới hạn tài nguyên và biết chính xác nó được gắn ở đâu.
- Nhận diện rủi ro với `ItemReader`, `ItemProcessor`, `ItemWriter`, `ItemStream` và trạng thái restart.
- Đánh giá throughput, contention, connection pool, memory và độ đúng đắn trước khi tăng concurrency.
- Chọn phương án xử lý phù hợp với workload và yêu cầu vận hành.

## 2. TaskExecutor là gì?

`org.springframework.core.task.TaskExecutor` là abstraction của Spring dùng để thực thi một `Runnable`. Code gửi công việc cho executor không nhất thiết quyết định nó chạy trên luồng hiện tại hay luồng khác. **Cách executor được cấu hình** quyết định cơ chế đó.

```java
public interface TaskExecutor extends Executor {
    void execute(Runnable task);
}
```

Một số lựa chọn thường gặp:

| Triển khai | Đặc điểm | Khi nào cân nhắc |
| --- | --- | --- |
| `SyncTaskExecutor` | Chạy tác vụ ngay trên luồng gọi; không tạo song song thực sự. | Đối chứng để debug hoặc kiểm tra hành vi tuần tự. |
| `SimpleAsyncTaskExecutor` | Tạo luồng thực thi tác vụ, không phải thread pool tái sử dụng theo kiểu truyền thống. | Thử nghiệm nhỏ; cần cấu hình giới hạn đồng thời nếu sử dụng thực tế. |
| `ThreadPoolTaskExecutor` | Quản lý một pool với core size, max size và hàng đợi. | Lựa chọn phổ biến khi muốn giới hạn mức song song trong một JVM. |
| `VirtualThreadTaskExecutor` | Sử dụng virtual thread trên nền Java/Spring hỗ trợ. | Tác vụ chờ I/O; vẫn phải giới hạn tài nguyên bên ngoài như DB, HTTP, memory. |

`TaskExecutor` **không phải** một hệ thống message queue, bộ lập lịch phân tán hoặc cơ chế chia dữ liệu. Nó chỉ cung cấp cách chạy tác vụ. *Spring Batch* là thành phần quyết định tác vụ đó thuộc chunk, flow, job launch hay partition nào.

### Phân biệt bốn vị trí sử dụng

| Vị trí gắn executor | Đơn vị chạy đồng thời | Phạm vi trạng thái | Chú ý chính |
| --- | --- | --- | --- |
| `StepBuilder.taskExecutor(...)` | Nhiều chunk của **cùng một step** | Một `StepExecution`, các thành phần step thường được chia sẻ | Thread safety của reader/writer và checkpoint. |
| `FlowBuilder`/job `.split(taskExecutor)` | Nhiều **flow/step độc lập** | `StepExecution` riêng theo step | Phụ thuộc dữ liệu, thứ tự và xung đột tài nguyên giữa step. |
| `TaskExecutorPartitionHandler` | Nhiều **worker step partition** trong một JVM | Mỗi partition có `StepExecution` và `ExecutionContext` riêng | Phân chia dữ liệu không trùng và quản lý retry/restart từng partition. |
| `TaskExecutorJobLauncher` | Khởi chạy job một cách bất đồng bộ | Mỗi job vẫn có cấu hình step của riêng nó | Trả quyền điều khiển sớm cho caller; **không tự làm các chunk song song**. |

Một job có thể kết hợp các cơ chế này, nhưng mỗi tầng concurrency mới đều làm tăng mức tiêu thụ tài nguyên và số tình huống lỗi phải kiểm soát.

## 3. Multi-threaded step: TaskExecutor xử lý chunk như thế nào?

Trong chunk-oriented processing, luồng đọc dữ liệu thường đi qua ba vai trò:

1. `ItemReader<T>` lấy item đầu vào.
2. `ItemProcessor<T, R>` biến đổi hoặc lọc item (`null` có thể biểu thị item bị lọc).
3. `ItemWriter<R>` ghi nhóm kết quả trong ranh giới transaction của chunk.

Khi cấu hình `TaskExecutor` cho step, Spring Batch có thể thực thi công việc xử lý các chunk trên các luồng khác nhau. **Các chunk có thể hoàn thành và commit không theo thứ tự đọc dự kiến**. Đây là thay đổi ngữ nghĩa quan trọng hơn việc chỉ tăng tốc.

```text
                       Step: importTransactions
                                  |
                       TaskExecutor (pool = 4)
                                  |
                  +---------------+---------------+
                  |               |               |
             worker-1        worker-2         worker-3 ...
                  |               |               |
              chunk A         chunk B          chunk C
                  |               |               |
             read/process     read/process      read/process
               /write           /write            /write
                  |               |               |
                Tx A            Tx B             Tx C

       ItemReader / ItemProcessor / ItemWriter có thể là shared objects.
       Commit A, B, C không nhất thiết xảy ra theo thứ tự chữ cái.
```

Ở đây mỗi chunk thường có transaction riêng. Khi chunk B thất bại, kết quả chunk A đã commit không tự động bị rollback. Bởi vậy xử lý song song không tạo ra một transaction lớn bao trùm toàn step.

### Ví dụ cấu hình bằng Java

Ví dụ sau minh họa kiểu API **Spring Batch 5.x**, dùng Java config. `InputRow`, `OutputRow` và ba thành phần reader/processor/writer là các kiểu, bean do ứng dụng cung cấp; việc dùng executor **giả định trước** các thành phần này an toàn trong môi trường nhiều luồng.

```java
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
public class BatchConcurrencyConfig {

    @Bean
    public ThreadPoolTaskExecutor batchChunkExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(12);
        executor.setThreadNamePrefix("batch-chunk-");
        executor.initialize();
        return executor;
    }

    @Bean
    public Step importTransactionsStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InputRow> reader,
            ItemProcessor<InputRow, OutputRow> processor,
            ItemWriter<OutputRow> writer,
            @Qualifier("batchChunkExecutor") TaskExecutor executor) {

        return new StepBuilder("importTransactionsStep", jobRepository)
                .<InputRow, OutputRow>chunk(100, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .taskExecutor(executor)
                .build();
    }
}
```

Trong ví dụ:

- `chunk(100, transactionManager)` đặt mục tiêu xử lý 100 item cho một lần commit (trong tình huống thông thường, không có filtering/skip đặc biệt).
- `corePoolSize = maxPoolSize = 4` giới hạn thread pool ở bốn worker cùng lúc; hàng đợi 12 tác vụ **không tương đương 12 thread bổ sung**.
- `threadNamePrefix` giúp liên hệ log, trace và thread dump với công việc batch.
- `.taskExecutor(executor)` mới là dòng kích hoạt mô hình xử lý nhiều luồng ở step này. Chỉ khai báo bean `ThreadPoolTaskExecutor` chưa làm bất kỳ step nào chạy song song.

**Đừng copy cấu hình này vào production khi chưa kiểm tra thread safety của reader/writer.** Đặc biệt, một `FlatFileItemReader` hoặc cursor reader có con trỏ đọc biến đổi theo thời gian thường không được phép để nhiều luồng truy cập vô điều kiện.

### Vì sao queue, pool size và backpressure cần được tính cùng nhau?

Với `ThreadPoolTaskExecutor`, luồng mới thường được tạo đến `corePoolSize`; sau đó tác vụ được đưa vào queue; chỉ khi queue đầy, pool mới có cơ hội mở rộng về `maxPoolSize`. Do đó cấu hình `core=4`, `max=16`, `queue=10_000` có thể giữ phần lớn tác vụ nằm chờ và hiếm khi đạt 16 worker đối với một job ngắn.

Queue giới hạn giúp tránh tích tụ công việc vô hạn nhưng khi cả pool lẫn queue đầy, executor có thể **từ chối** tác vụ. Chính sách rejection là một quyết định vận hành: báo lỗi để phát hiện quá tải, hoặc dùng cơ chế phù hợp để điều tiết phía gọi. Không nên cấu hình queue thật lớn chỉ nhằm che giấu việc downstream đã quá tải.

Trong các phiên bản Spring Batch hiện đại, không nên dựa vào cấu hình `throttleLimit` cũ như cơ chế giới hạn đồng thời lâu dài; thuộc tính này đã bị deprecate từ Spring Batch 5.0. Hãy quản lý tài nguyên qua executor phù hợp và kiểm tra API thực tế của phiên bản đang dùng.

## 4. An toàn luồng: điểm khó nhất không nằm ở executor

Khi nhiều chunk cùng chạy, Spring Batch không tự biến mọi `ItemReader`, `ItemProcessor`, `ItemWriter` hoặc collaborator của chúng thành thread-safe. Ngay cả khi bean được khai báo `@StepScope`, nó vẫn gắn với **StepExecution**, không mặc nhiên tạo một bản sao mới cho **mỗi thread** trong multi-threaded step.

| Thành phần | Rủi ro điển hình | Hướng xử lý |
| --- | --- | --- |
| Reader dựa trên cursor hoặc file | Nhiều thread thay đổi cùng vị trí đọc; item có thể bị bỏ sót/đọc lặp. | Cân nhắc reader được bảo vệ đồng bộ, hoặc tốt hơn là chia input thành partition độc lập. |
| Reader có `ExecutionContext` và `ItemStream` | State lưu checkpoint có thể không phản ánh thứ tự hoàn tất chunk. | Xem lại hợp đồng restart; thử lỗi giữa chừng, ưu tiên partition nếu cần restart chính xác. |
| Processor có bộ đếm, cache/mutable field | Data race, kết quả phụ thuộc thứ tự và thời điểm chạy. | Viết processor stateless; giữ biến cục bộ hoặc dùng thành phần đồng thời an toàn khi thật sự cần. |
| Writer gom buffer/chạy batch theo trạng thái nội bộ | Mất cập nhật, trộn bản ghi giữa các chunk. | Writer stateless hoặc đồng bộ thích hợp; tách trạng thái theo partition/transaction. |
| Dịch vụ phụ trợ, HTTP client, session | Client không thread-safe hoặc giới hạn kết nối thấp. | Kiểm tra contract của thư viện, giới hạn concurrency và timeout. |
| Database | Lock contention, deadlock, transaction kéo dài, cạn connection. | Giảm lock footprint, tạo index phù hợp, sắp thứ tự update nhất quán, đo pool và lock wait. |

### Đồng bộ hóa reader có giải quyết mọi việc không?

Spring Batch có các wrapper như `SynchronizedItemStreamReader` để đồng bộ lời gọi `read()` quanh delegate reader. Wrapper này có thể giảm race tại thao tác đọc nhưng **không bảo đảm toàn bộ pipeline và checkpoint có thể restart chính xác**. Nó cũng tuần tự hóa phần đọc: nếu reader là nút thắt chính, tăng worker chưa chắc tăng throughput.

Nếu một file phải đọc theo thứ tự tuyệt đối, mỗi record phải được ghi đúng một lần và job cần restart ở bất kỳ vị trí nào, hãy xem xét **partition file/range thành các vùng độc lập**, hoặc giữ đọc tuần tự và chuyển các tác vụ có thể song song ra một kiến trúc phù hợp. Không nên gắn `.taskExecutor(...)` trước khi xác định các bất biến dữ liệu.

Một processor thuần (pure function) thường dễ song song hóa:

```java
// Không chứa mutable field chia sẻ giữa các lần gọi.
public OutputRow process(InputRow row) {
    return new OutputRow(row.id(), normalize(row.value()));
}
```

Ngược lại, thao tác `currentId++` trên field dùng chung hoặc tích lũy vào `ArrayList` không đồng bộ có thể dẫn tới mất cập nhật và kết quả không xác định.

## 5. Transaction, retry, skip và restart trong xử lý đồng thời

### Transaction và thứ tự hoàn tất

Mỗi worker chunk có thể commit/rollback độc lập. Giả sử các chunk A, B và C chạy cùng lúc:

```text
Thời điểm 1: A bắt đầu, B bắt đầu, C bắt đầu
Thời điểm 2: C commit
Thời điểm 3: A commit
Thời điểm 4: B rollback vì timeout
Thời điểm 5: B được retry theo chính sách của step
```

Hệ quả: nếu writer cần update một số dư tuần tự hoặc phụ thuộc kết quả của chunk trước, phép xử lý này **không có tính độc lập** để chạy multi-threaded theo cách trên. Phải thiết kế lại thuật toán, khóa phù hợp hoặc chia workload sao cho các chunk không tranh chấp cùng key.

### Retry/skip không đồng nghĩa với xử lý đúng một lần

`retry` cho phép thử lại thao tác lỗi tạm thời; `skip` chấp nhận bỏ qua item theo chính sách khai báo. Nhưng khi một worker đã gửi HTTP request hoặc publish message rồi mới rollback transaction của database, side effect bên ngoài **có thể đã xảy ra**. Retry có nguy cơ gửi lại.

Để thiết kế an toàn:

1. Xác định **đơn vị idempotency** (ví dụ `transactionId` + phiên bản dữ liệu) và áp dụng unique constraint hoặc cơ chế dedup ở nơi ghi.
2. Đặt transaction boundary phù hợp, tránh trộn side effect không rollback được vào giả định ACID của database.
3. Khi cần gửi sự kiện sau commit, cân nhắc transactional outbox hay một quy trình publish có khả năng retry an toàn.
4. Đo số lần retry, skip, deadlock, timeout; giới hạn retry để tránh một dịch vụ lỗi làm tăng tải không kiểm soát.

### Restart và lưu trạng thái

Spring Batch quản lý metadata qua `JobRepository`, trong đó có `JobExecution`, `StepExecution` và `ExecutionContext`. Khi khởi chạy lại một job instance đủ điều kiện restart, framework dựa vào trạng thái đã lưu để xác định phần việc cần làm tiếp. Tuy nhiên, **metadata không thể tự sửa một reader không thread-safe, một checkpoint thiếu nhất quán hoặc một writer không idempotent**.

Trước khi chấp nhận chạy song song, cần thực nghiệm ít nhất ba kịch bản: dừng giữa chừng khi một số chunk đã commit; lỗi có thể retry trong khi các chunk khác vẫn chạy; và khởi động lại cùng job instance sau khi lỗi. Kiểm tra bằng **tập khóa nghiệp vụ thực tế**, không chỉ nhìn trạng thái `COMPLETED`.

Đặt `saveState(false)` cho một reader có thể phù hợp khi *chủ đích chấp nhận không khôi phục từ checkpoint của reader*, nhưng điều đó **không biến toàn bộ step thành restart-safe**. Nếu cần phục hồi chính xác từng vùng dữ liệu, partitioning với trạng thái riêng từng partition thường có mô hình dễ kiểm tra hơn.

## 6. Khi nào dùng TaskExecutor cho parallel steps?

Nếu một job có hai bước độc lập, ví dụ `loadCustomers` và `loadProducts`, chúng có thể chạy đồng thời ở **hai flow** bằng `split`. Đây là mức song song khác với nhiều chunk của một step.

```text
                            Job
                             |
                        split(executor)
                          /       \
                Flow customers   Flow products
                      |               |
                Step load       Step load
                customers       products
                          \       /
                       join / end
```

Một cấu hình minh họa (Spring Batch 5.x):

```java
@Bean
public Job parallelLoadJob(
        JobRepository jobRepository,
        Flow customersFlow,
        Flow productsFlow,
        @Qualifier("batchChunkExecutor") TaskExecutor executor) {

    return new JobBuilder("parallelLoadJob", jobRepository)
            .start(customersFlow)
            .split(executor)
            .add(productsFlow)
            .end()
            .build();
}
```

Ở đoạn code này, hai flow được định nghĩa độc lập và executor cung cấp luồng để chạy chúng. Điều kiện tiên quyết là không flow nào cần kết quả chưa hoàn tất của flow kia. Nếu hai flow cùng sửa một tập khóa hoặc có cùng giới hạn kết nối, cần đánh giá contention ngay cả khi mã bước riêng lẻ là thread-safe.

**Không dùng `split` để song song hóa hai step có quan hệ phụ thuộc dữ liệu** như `importOrders` phải hoàn tất trước `calculateOrderTotals`. Chúng phải có thứ tự hoặc điểm đồng bộ hóa rõ ràng.

## 7. TaskExecutor trong local partitioning

Partitioning cho phép chia input thành những phần tách biệt, ví dụ theo khoảng ID, ngày giao dịch hoặc shard. `Partitioner` tạo nhiều `ExecutionContext`; mỗi worker step dùng thông tin của partition để chỉ đọc phần dữ liệu mình sở hữu. Khi thực thi các worker trong **cùng JVM**, có thể dùng `TaskExecutorPartitionHandler`.

```text
                   Manager step
                        |
                Partitioner chia vùng
                        |
             TaskExecutorPartitionHandler
                  /      |      \
              P0        P1       P2 ...
           ID 1..999 1000..1999 2000..2999
              |         |        |
         workerStep workerStep workerStep
         (context0) (context1) (context2)
```

Điểm khác biệt chính: mỗi partition có một `StepExecution` và `ExecutionContext` riêng, giúp reader có thể nhận phạm vi cố định; với bean `@StepScope` thiết kế đúng, trạng thái theo partition cũng dễ tách riêng hơn. Tuy vậy, chia sai phạm vi có thể gây trùng hoặc mất bản ghi dù executor hoạt động bình thường.

Ví dụ cấu hình handler:

```java
@Bean
public TaskExecutorPartitionHandler localPartitionHandler(
        @Qualifier("workerStep") Step workerStep,
        @Qualifier("batchChunkExecutor") TaskExecutor executor) {

    TaskExecutorPartitionHandler handler = new TaskExecutorPartitionHandler();
    handler.setStep(workerStep);
    handler.setTaskExecutor(executor);
    handler.setGridSize(8);
    return handler;
}
```

`gridSize(8)` là gợi ý về số partition/tác vụ được tổ chức, **không có nghĩa chắc chắn tám worker chạy đồng thời**: executor, database và năng lực máy chủ vẫn giới hạn mức thực thi. Manager step còn cần `Partitioner` tạo khóa partition và các `ExecutionContext` không chồng lấn, cùng cấu hình step builder tương ứng.

Nếu cần chạy worker ở nhiều máy, local `TaskExecutor` không tự đưa tác vụ qua network. Khi đó phải cân nhắc **remote partitioning** hoặc **remote chunking** với messaging, cơ chế triển khai worker, giám sát và xử lý thông điệp lỗi. Đây là một lựa chọn kiến trúc, không chỉ thay giá trị `poolSize`.

## 8. Chọn mô hình concurrency cho workload thực tế

| Tình huống | Điểm bắt đầu hợp lý | Lý do |
| --- | --- | --- |
| Các chunk độc lập, component thread-safe, xử lý I/O chậm | Multi-threaded step với pool giới hạn | Ít thay đổi kiến trúc, tăng mức sử dụng luồng trong một step. |
| Hai hoặc nhiều bước không phụ thuộc nhau | Parallel steps/flows với `split` | Không ép các step độc lập dùng chung một reader. |
| Dữ liệu có thể chia theo ID/ngày/shard và cần restart rõ ràng | Local partitioning | Phạm vi đọc và trạng thái theo partition rõ ràng hơn. |
| Workload vượt tài nguyên của một JVM, cần worker độc lập | Remote partitioning/chunking | Cho phép scale nhiều process/host, đổi lại chi phí phối hợp và vận hành. |
| Tác vụ cần thứ tự toàn cục hoặc chung một mutable cursor | Giữ tuần tự hoặc tái thiết kế cách chia dữ liệu | Chạy nhiều luồng có thể phá vỡ tính đúng đắn. |
| Bottleneck nằm ở DB lock, connection pool hoặc downstream rate limit | Tối ưu nút thắt trước | Thêm thread chỉ tăng tranh chấp và áp lực lên dịch vụ đích. |

Một hệ thống có thể dùng *parallel steps* để xử lý các nguồn độc lập, và mỗi step dùng *partitioning*. Tuy nhiên tổng concurrency tiềm năng sẽ tăng theo các tầng. Ví dụ ba flow, mỗi flow chạy bốn partition có thể tạo áp lực từ khoảng 12 worker cùng lúc trước cả khi tính retry và job khác. Cần có **ngân sách tài nguyên tổng**, tránh cấu hình riêng từng step mà không nhìn toàn hệ thống.

## 9. Đo nút thắt và điều chỉnh thread pool

### Chỉ số cần nhìn

| Nhóm đo | Ví dụ số liệu | Câu hỏi cần trả lời |
| --- | --- | --- |
| Tiến độ batch | Items/giây, chunks/phút, tổng thời gian step/job | Tốc độ có thật sự tăng khi thêm worker? |
| Độ trễ | P50/P95/P99 của đọc, xử lý, ghi, commit | Phần nào bắt đầu chậm khi tăng tải? |
| Executor | Active threads, pool size, queue depth, rejected tasks | Pool bận hay chỉ đang xếp hàng? |
| JVM | CPU, heap, GC pause, thread count | Có tốn quá nhiều CPU/bộ nhớ cho concurrency không? |
| Database | Connection checkout wait, active connections, lock wait, deadlock | Tài nguyên DB có trở thành cổ chai mới? |
| Dịch vụ ngoài | HTTP latency, timeout, 429/503, retry rate | Downstream có giới hạn request hay tự làm quá tải? |
| Đúng đắn và ổn định | Duplicate/missing business keys, skip/retry, restart result | Tăng tốc có giữ nguyên kết quả nghiệp vụ không? |

Đặt một baseline với cấu hình tuần tự, giữ nguyên dữ liệu và hạ tầng. Sau đó tăng dần concurrency (chẳng hạn 1 → 2 → 4 → 8) và đo cùng một bộ chỉ số. Mỗi lần đổi chỉ một biến chính, như số worker hoặc chunk size, để dễ xác định nguyên nhân.

Về mặt lý thuyết, speedup và hiệu suất sử dụng worker có thể viết:

\[
S(N) = \frac{T(1)}{T(N)}, \qquad E(N) = \frac{S(N)}{N}
\]

Ở đây `T(1)` là thời gian chạy với một worker, `T(N)` là thời gian với `N` worker. Ví dụ *giả định* step mất 40 phút với một worker và 14 phút với bốn worker, thì speedup xấp xỉ `2,86×`, hiệu suất khoảng `71%`; không phải `4×` vì vẫn có chi phí tuần tự và tranh chấp.

Định luật Amdahl nhắc rằng phần không song song hóa được sẽ giới hạn tốc độ tối đa:

\[
S(N) \leq \frac{1}{(1-p) + \frac{p}{N}}
\]

Với `p` là tỷ lệ thời gian có thể song song hóa. Đây là công cụ tư duy, **không thay thế benchmark**, bởi hệ thống thực còn gặp contention, queueing, cache, GC và giới hạn I/O.

### Cách lựa chọn cấu hình ban đầu

Giả sử một step xử lý dữ liệu từ PostgreSQL rồi gọi API:

1. **Kiểm tra bottleneck trước:** nếu CPU chỉ dùng 20% còn HTTP latency lớn, concurrency có thể hữu ích; nếu database connection chờ lâu, mở thêm worker thường không có lợi.
2. **Đặt pool nhỏ:** ví dụ 2–4 worker trên một instance, rồi đo. Không lấy số core CPU làm đáp án duy nhất cho workload bị chặn bởi I/O.
3. **Cấp ngân sách kết nối:** pool DB phải đủ cho những transaction đồng thời cùng các luồng khác của ứng dụng; không lấy toàn bộ `maximumPoolSize` của database cho một batch job.
4. **Giới hạn tác vụ đang chờ:** queue và cơ chế overload phải được chọn có chủ đích. Thực nghiệm lỗi khi downstream chậm hoặc executor bão hòa.
5. **Xem lại chunk size:** chunk lớn làm tăng lượng item trong bộ nhớ và thời gian giữ transaction; chunk quá nhỏ tăng số lần commit và overhead. Chọn theo số đo.
6. **Giữ ngân sách chung:** cộng tải từ các step song song, partition, job instance khác và request ứng dụng.

Một ước lượng hữu ích cho bộ nhớ tạm chỉ là:

```text
memory cho item đang xử lý ≈ số chunk đang chạy
                          × số item/chunk
                          × kích thước trung bình/item
```

Đây là cận gần đúng cho phần dữ liệu của chunk, chưa tính buffer reader/writer, queue, cache, metadata, kết quả xử lý và overhead của JVM. Tăng đồng thời và tăng chunk size cùng lúc có thể khiến heap phình rất nhanh.

## 10. Những lỗi thường gặp khi áp dụng TaskExecutor

**Lỗi 1 — Khai báo executor nhưng không gắn vào step.** Một bean `ThreadPoolTaskExecutor` tự nó không thay đổi luồng xử lý. Cần chỉ rõ nơi sử dụng: `.taskExecutor(...)`, `.split(...)`, partition handler hoặc job launcher.

**Lỗi 2 — Cho nhiều thread cùng dùng reader có mutable cursor.** Việc đọc có thể nhảy vị trí, thiếu bản ghi hoặc hỏng state khi restart. Cần đọc tài liệu thread safety của implementation, benchmark và kiểm thử failure/restart; thường nên phân vùng input.

**Lỗi 3 — Tưởng `@StepScope` đồng nghĩa `@ThreadScope`.** Trong cùng một multi-threaded step, các thread có thể vẫn sử dụng chung bean thuộc một `StepExecution`. Nếu cần cô lập trạng thái, hãy thiết kế partition có `StepExecution` riêng.

**Lỗi 4 — Tăng max pool nhưng throughput không đổi.** Queue dài, lock DB hoặc giới hạn HTTP có thể là nguyên nhân. Đọc active thread, queue depth và thời gian chờ connection trước khi tăng số worker.

**Lỗi 5 — Giả định thứ tự item và commit được giữ nguyên.** Nhiều chunk chạy song song không bảo đảm ordering. Dùng khóa nghiệp vụ, thiết kế xử lý giao hoán/độc lập hoặc chuyển phần cần thứ tự sang pha tuần tự.

**Lỗi 6 — Job báo hoàn thành nhưng dữ liệu có duplicate hoặc thiếu.** Chỉ kiểm tra `BatchStatus` là không đủ. Đối soát số lượng, tính duy nhất, tổng tiền/hash và khóa nghiệp vụ đầu vào/đầu ra.

**Lỗi 7 — Retry tạo side effect trùng.** HTTP request, email hoặc event có thể đã được gửi trước rollback. Dùng idempotency key, outbox/dedup và thử lỗi có chủ đích.

## 11. Kịch bản thực hành: mở rộng bước nhập giao dịch

**Bối cảnh:** mỗi đêm hệ thống nhập 1,5 triệu giao dịch, xác thực định dạng, làm giàu bằng một API và ghi vào DB. Mục tiêu là giảm thời gian batch mà vẫn cho phép chạy lại sau sự cố.

**Thiết kế thử nghiệm:**

1. Chạy baseline tuần tự, ghi thời gian đọc, gọi API, ghi DB, commit và tổng số transaction ID duy nhất.
2. Xác nhận processor stateless và writer idempotent theo transaction ID. Kiểm tra reader hiện tại có hỗ trợ concurrent read và restart không.
3. Nếu reader không an toàn, ưu tiên partition theo dải ID hoặc nhóm ngày với worker step có trạng thái riêng, thay vì chia sẻ một cursor.
4. Bắt đầu với bốn worker và chunk size 100; bảo đảm DB/API có đủ capacity, logging cho biết partition/chunk và thread.
5. Chạy cùng bộ dữ liệu ở concurrency 1, 2, 4, 8; so sánh elapsed time, connection wait, HTTP 429, heap, lỗi retry và số khóa duy nhất.
6. Tiêm lỗi giữa chừng khi đã commit một số chunk; restart và đối soát số transaction ID, tổng số tiền, trạng thái cuối cùng.
7. Giữ cấu hình đạt throughput tốt mà còn đủ tài nguyên dự phòng; ghi nhận điều kiện làm giảm song song hoặc tạm dừng job khi downstream quá tải.

**Tiêu chí chấp nhận** phải bao gồm cả kết quả nghiệp vụ (không thiếu/trùng ngoài chính sách), restart thành công, mức lỗi được kiểm soát và cải thiện runtime đo được. Một kết quả chạy nhanh nhưng không đối soát được dữ liệu không đạt yêu cầu.

## 12. Checklist trước khi đưa vào vận hành

- [ ] Xác định rõ executor đang phục vụ chunk, flow, partition hay job launcher.
- [ ] Biết reader, processor, writer và collaborator nào được chia sẻ giữa thread; đã kiểm tra thread safety.
- [ ] Không dựa vào thứ tự chunk/commit nếu nghiệp vụ không bảo đảm nó.
- [ ] Có chiến lược riêng cho checkpoint, retry, skip, restart và side effect ngoài transaction.
- [ ] Executor được giới hạn về concurrency, queue và xử lý overload; có giám sát active threads/rejections.
- [ ] Đã đánh giá DB connection pool, khóa, downstream rate limit, CPU, heap và tài nguyên job chạy cùng lúc.
- [ ] Đã benchmark với dữ liệu đại diện và đối soát duplicate/missing keys ở cả lần chạy thường lẫn restart.
- [ ] Có log, metric và quy trình vận hành để chẩn đoán step chậm, thất bại hoặc executor bão hòa.

## 13. Ghi nhớ

`TaskExecutor` là công cụ thực thi tác vụ đồng thời **bên trong tiến trình Spring**. Trong Spring Batch, giá trị của nó phụ thuộc vào nơi được gắn: multi-threaded chunk step, parallel flow, local partition handler hoặc asynchronous job launcher. Chọn executor phù hợp mới chỉ giải quyết cách cấp phát luồng; khả năng scale thực tế còn do cách chia dữ liệu, thread safety, transaction, checkpoint/restart và giới hạn tài nguyên.

Hãy bắt đầu bằng đo bottleneck và xác định bất biến dữ liệu, sau đó chọn mô hình đơn giản nhất đáp ứng throughput **và** độ tin cậy. Với workload lớn, sự độc lập của các phần dữ liệu và khả năng phục hồi sau lỗi thường quan trọng hơn việc nâng số thread tối đa.
