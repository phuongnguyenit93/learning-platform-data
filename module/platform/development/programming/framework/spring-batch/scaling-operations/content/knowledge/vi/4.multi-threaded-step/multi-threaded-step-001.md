# Thêm TaskExecutor vào Step

## 1. Bài toán và kết quả cần đạt

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, chúng ta tìm cách mở rộng Spring Batch cho workload dữ liệu lớn, đo đúng nút thắt, bảo đảm tính an toàn khi xử lý song song, giữ khả năng retry/restart và vận hành job phù hợp với tài nguyên thực tế. Bài thuộc chương **Step nhiều luồng** và tập trung vào thao tác cụ thể: **gắn `TaskExecutor` vào một Step**.

Giả sử một job phải lấy 100.000 đơn hàng, tính điểm rủi ro cho từng đơn rồi ghi kết quả vào cơ sở dữ liệu. Ban đầu job chạy ổn định trong một luồng nhưng mất quá nhiều thời gian vì công đoạn tính điểm. Ta muốn sử dụng thêm CPU hoặc cho nhiều tác vụ I/O độc lập chạy đồng thời. `TaskExecutor` là điểm mở rộng đơn giản, nhưng cơ chế thực thi đã thay đổi đáng kể giữa **Spring Batch 5.x và 6.x**.

Sau bài này, bạn có thể:

1. Giải thích `TaskExecutor` được gắn vào `Step` ở đâu và phần công việc nào thực sự chạy song song.
2. Cấu hình `ThreadPoolTaskExecutor` cùng một chunk-oriented Step trong Spring Batch 6.x và nhận biết cú pháp Spring Batch 5.x.
3. Xác định yêu cầu thread safety của reader, processor, writer theo **đúng phiên bản**.
4. Ước lượng độ song song dựa trên CPU, kích thước chunk, thread pool, connection pool và tải nguồn dữ liệu.
5. Thiết kế retry, restart, idempotency và kiểm thử dữ liệu khi chạy đa luồng.

## 2. TaskExecutor là gì? Vì sao không thể chỉ tăng thread pool?

`TaskExecutor` là giao diện của Spring để thực thi tác vụ. `SyncTaskExecutor` chạy ngay trên luồng gọi; `SimpleAsyncTaskExecutor` tạo tác vụ bất đồng bộ; `ThreadPoolTaskExecutor` quản lý một pool có thể cấu hình giới hạn. Chỉ khai báo một executor bean **không** khiến Step tự chạy song song: cần truyền executor vào builder của Step bằng `.taskExecutor(...)`.

**Điểm đặc biệt về phiên bản:** cùng tên phương thức `taskExecutor` nhưng phần được chạy song song không giống nhau:

| Nội dung | Spring Batch 5.2 / mô hình Step cũ | Spring Batch 6.x / mô hình chunk-oriented mới |
| --- | --- | --- |
| Builder điển hình | `.chunk(size, transactionManager)` | `.chunk(size).transactionManager(transactionManager)` |
| Đơn vị chạy trên worker | **Toàn bộ chunk**: read → process → write | **ItemProcessor**: xử lý item bất đồng bộ |
| ItemReader | Có thể được gọi từ nhiều worker; cần thread-safe nếu dùng chung | Đọc tuần tự trên luồng điều phối Step |
| ItemProcessor | Chạy trong worker của chunk | Nhiều lần `process` có thể chạy đồng thời trên worker |
| ItemWriter | Có thể được gọi từ nhiều worker; cần thread-safe nếu dùng chung | Ghi tuần tự trên luồng điều phối Step |
| Transaction | Chunk có transaction trong worker thực thi chunk | Transaction chunk ở luồng chính; **không tự truyền** sang worker chạy processor |
| Kiểm soát concurrency | Executor và cơ chế throttle cũ; `throttleLimit` đã deprecated từ 5.0 | Executor bất đồng bộ cho processor, cần quản lý pool và hàng đợi phù hợp |
| Khả năng tăng tốc phù hợp | Công việc read/process/write trong các chunk độc lập | Công việc `process` chiếm tỷ trọng đáng kể |

Từ Spring Batch 6.0, `ChunkOrientedStepBuilder` và `ChunkOrientedStep` là hướng sử dụng mới. API `taskExecutor(TaskExecutor)` của `AbstractTaskletStepBuilder` ở mô hình tasklet cũ đã deprecated; thay thế với chunk-oriented Step là `taskExecutor(AsyncTaskExecutor)`. Vì vậy **không áp dụng trực tiếp một mô tả của Spring Batch 5.x cho ứng dụng 6.x**.

### Hình dung dòng thực thi

```text
Spring Batch 5.2, mô hình multi-threaded chunk:

                      +--> worker-1: read -> process -> write -> commit
Step điều phối -------+--> worker-2: read -> process -> write -> commit
                      +--> worker-3: read -> process -> write -> commit
                  (reader/writer chia sẻ cần kiểm tra thread safety)

Spring Batch 6.x, mô hình chunk-oriented:

main thread: read 10 items -------------------------------> write chunk -> commit
                |                  ^         ^         ^
                +--> worker-1: process(item A) ------------+
                +--> worker-2: process(item B) -----+
                +--> worker-3: process(item C) --+
                ... (processor có thể được gọi đồng thời)
```

Sơ đồ là mô hình khái niệm, không mô tả chính xác lịch lập tác vụ nội bộ. Dù có nhiều worker, tốc độ tổng vẫn bị giới hạn bởi phần xử lý tuần tự, hàng đợi và các tài nguyên dùng chung.

## 3. Ví dụ cấu hình Spring Batch 6.x

Đây là cấu hình mẫu chạy tại chỗ với một tập dữ liệu nhỏ. `IteratorItemReader` và writer in ra console giúp quan sát luồng thực thi; **chúng chỉ dành cho demo, không bảo đảm restart hay tính bền vững của dữ liệu sản xuất**.

```java
import java.util.List;
import java.util.stream.LongStream;

import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.infrastructure.item.ItemProcessor;
import org.springframework.batch.infrastructure.item.ItemReader;
import org.springframework.batch.infrastructure.item.ItemWriter;
import org.springframework.batch.infrastructure.item.support.IteratorItemReader;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class OrderStepConfiguration {

    public record Order(long id, long amountInCents) {}
    public record ScoredOrder(long id, long riskScore) {}

    @Bean("orderProcessorExecutor")
    public ThreadPoolTaskExecutor orderProcessorExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-processor-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        return executor;
    }

    @Bean
    public ItemReader<Order> orderReader() {
        List<Order> input = LongStream.rangeClosed(1, 40)
                .mapToObj(id -> new Order(id, id * 1_000))
                .toList();
        return new IteratorItemReader<>(input);
    }

    @Bean
    public ItemProcessor<Order, ScoredOrder> orderProcessor() {
        return order -> {
            // Mô phỏng một phép tính tốn thời gian, chỉ để quan sát concurrency.
            Thread.sleep(25);
            System.out.printf("process id=%d, thread=%s%n",
                    order.id(), Thread.currentThread().getName());
            return new ScoredOrder(order.id(), order.amountInCents() / 100);
        };
    }

    @Bean
    public ItemWriter<ScoredOrder> orderWriter() {
        return chunk -> {
            for (ScoredOrder item : chunk.getItems()) {
                System.out.printf("write id=%d, thread=%s%n",
                        item.id(), Thread.currentThread().getName());
            }
        };
    }

    @Bean
    public Step scoreOrders(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, ScoredOrder> orderProcessor,
            ItemWriter<ScoredOrder> orderWriter,
            @Qualifier("orderProcessorExecutor")
            ThreadPoolTaskExecutor executor) {

        return new StepBuilder("scoreOrders", jobRepository)
                .<Order, ScoredOrder>chunk(10)
                .transactionManager(transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .taskExecutor(executor)
                .build();
    }
}
```

**Cách đọc cấu hình:**

- `corePoolSize(4)` và `maxPoolSize(4)` đặt mức bốn worker cho công đoạn `process`; đây là giá trị thử nghiệm, không phải con số tối ưu chung.
- `queueCapacity(100)` cho phép xếp tác vụ khi bốn worker bận. Nếu hàng đợi đầy, executor có thể từ chối tác vụ; cần kiểm tra hành vi đó dưới tải thực tế.
- `chunk(10)` cấu hình tối đa 10 item mỗi lần commit thông thường. Kích thước chunk và kích thước pool **là hai thông số khác nhau**.
- `.transactionManager(transactionManager)` chỉ định transaction manager cho chunk. Trên Spring Batch 6.x, worker chạy `process` **không thừa hưởng transaction của luồng chính**.
- `@Qualifier` chỉ định đúng executor trong trường hợp ứng dụng có nhiều bean loại `TaskExecutor`.
- Tại bước demo, phần `process` có thể xuất hiện với nhiều tên luồng bắt đầu bằng `order-processor-`, còn writer chạy trên luồng điều phối Step.

Để dùng trong production, thay `IteratorItemReader` bằng reader đọc dữ liệu có checkpoint/restart thích hợp, thay console writer bằng writer ghi dữ liệu có transaction và thiết kế phép tính trong processor là **stateless**, không phụ thuộc thứ tự thực thi.

### Vì sao có thêm thread nhưng có thể không nhanh hơn?

Giả sử đọc và ghi cùng chiếm 70% thời gian, còn xử lý item chiếm 30%. Với mô hình 6.x, ngay cả khi phần process song song hoàn hảo trên bốn worker, mức tăng tốc lý tưởng xấp xỉ:

```text
Speedup <= 1 / (0.70 + 0.30 / 4) = 1.29 lần
```

Đây là giới hạn lý thuyết theo định luật Amdahl, chưa trừ overhead tạo tác vụ, phối hợp kết quả, memory và contention. Nếu processor chỉ làm vài phép cộng rất nhanh, việc gửi item sang thread pool còn có thể khiến job **chậm hơn**.

## 4. Trường hợp dự án đang dùng Spring Batch 5.x

Với Spring Batch 5.2, mã cấu hình Step điển hình là:

```java
@Bean
public Step scoreOrdersLegacy(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, ScoredOrder> processor,
        ItemWriter<ScoredOrder> writer,
        @Qualifier("orderProcessorExecutor")
        ThreadPoolTaskExecutor executor) {

    return new StepBuilder("scoreOrdersLegacy", jobRepository)
            .<Order, ScoredOrder>chunk(10, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(executor)
            .build();
}
```

**Lưu ý về import:** ví dụ Spring Batch 5.x sử dụng các giao diện item trong package `org.springframework.batch.item.*`; với Spring Batch 6.x, các giao diện tương ứng chuyển sang `org.springframework.batch.infrastructure.item.*`. Cần chọn dependency và import đồng bộ với phiên bản thực tế.

Trong 5.x, nhiều chunk có thể cùng gọi reader, processor và writer. Vì vậy **không nên lấy `IteratorItemReader` hoặc một cursor reader thông thường của ví dụ 6.x để chạy trực tiếp trong mô hình 5.x** nếu chưa kiểm chứng thread safety và chính sách restart.

Một số bản 5.x có giới hạn throttle mặc định là **4** cho kiểu thực thi chunk cũ, kể cả khi thread pool có nhiều thread hơn. `throttleLimit(...)` đã **deprecated từ 5.0**. Hướng dẫn chính thức nêu khả năng thay cơ chế throttle bằng `RepeatOperations` tùy chỉnh được truyền qua `stepOperations(...)`. Không cấu hình tăng thread pool lên 16 rồi mặc nhiên kỳ vọng 16 chunk hoạt động đồng thời.

### Reader và writer trong Spring Batch 5.x

`SynchronizedItemStreamReader` có thể bọc một `ItemStreamReader` không thread-safe để đồng bộ lời gọi `read()`:

```java
// Spring Batch 5.x; ví dụ ở mức ý tưởng.
SynchronizedItemStreamReader<Order> synchronizedReader =
        new SynchronizedItemStreamReaderBuilder<Order>()
                .delegate(existingStreamReader)
                .build();
```

Decorator này bảo vệ lời gọi đọc nhưng không giải quyết mọi vấn đề: trạng thái checkpoint trong `ExecutionContext`, rollback, replay và thứ tự item vẫn phải được kiểm thử. Javadoc cảnh báo rằng dùng reader đồng bộ có thể làm job **không restart an toàn** nếu xử lý lại item gây hậu quả. Một writer có state hoặc truy cập nguồn tài nguyên không hỗ trợ concurrent cũng cần cơ chế an toàn tương ứng. Nếu việc khóa reader khiến toàn bộ throughput nghẽn, nên xem xét partitioning.

## 5. Thread safety: kiểm tra đúng thành phần được chia sẻ

Một lớp chỉ có annotation `@Component`, `@Bean` hoặc `@StepScope` không mặc nhiên thread-safe. Cần nhìn vào dữ liệu thay đổi khi chạy:

| Thành phần / trạng thái | Mẫu dễ lỗi | Cách xử lý |
| --- | --- | --- |
| Processor singleton (đặc biệt 6.x) | Tăng biến `long count`, dùng `HashMap`/`ArrayList` dùng chung | Ưu tiên processor stateless; nếu thực sự cần thống kê thì dùng bộ đếm concurrent, không dùng làm checkpoint |
| `SimpleDateFormat`, bộ đệm mutable | Nhiều luồng cùng sửa trạng thái | Dùng `java.time`, dữ liệu immutable hoặc tạo đối tượng riêng cho mỗi tác vụ |
| Reader / writer ở 5.x | Cursor/index thay đổi từ nhiều worker | Chọn implementation có bảo đảm concurrency; thử decorator đồng bộ hoặc partitioning |
| `ExecutionContext` | Nhiều worker cùng thay checkpoint | Không tự cập nhật shared state tùy tiện; xác định một cơ chế ghi/checkpoint nhất quán |
| Client gọi HTTP/DB | Dùng chung một connection/session không thread-safe | Dùng pool do framework quản lý; mỗi thao tác lấy tài nguyên đúng vòng đời |
| `ThreadLocal`, logging MDC | Giả định context trên luồng cha được truyền sang worker | Truyền dữ liệu cần thiết một cách tường minh, cấu hình cơ chế propagation nếu cần |

**Ví dụ processor nguy hiểm khi chạy đồng thời:**

```java
class RiskProcessor implements ItemProcessor<Order, ScoredOrder> {
    private long processedCount = 0; // Shared mutable state

    @Override
    public ScoredOrder process(Order order) {
        processedCount++; // Có thể mất cập nhật
        return new ScoredOrder(order.id(), order.amountInCents() / 100);
    }
}
```

Trong xử lý nghiệp vụ, tốt nhất hãy để `process(order)` là một hàm tính toán từ input đến output và không có side effect. Nếu cần metric, dùng Micrometer hoặc bộ đếm thread-safe; **metric không thay thế trạng thái restart lưu bền vững**.

## 6. Transaction, retry và restart khi đã thêm TaskExecutor

### Transaction theo phiên bản

**Spring Batch 6.x:** reader và writer chạy tuần tự ở luồng chính, còn processor có thể ở worker. Spring transaction gắn với thread nên một processor đang chạy trên worker **không nằm trong cùng transaction chunk** chỉ vì Step đã khai báo `transactionManager`. Nếu processor cần truy vấn DB có transaction riêng, có thể khởi tạo transaction của chính nó với `@Transactional(propagation = REQUIRED)` trên một Spring-managed bean được gọi qua proxy. `MANDATORY` có thể thất bại vì worker không có transaction sẵn. Tránh thực hiện ghi DB hoặc gọi hệ thống bên ngoài có side effect trong processor rồi tưởng rollback của chunk sẽ hoàn tác được việc đó.

**Spring Batch 5.x:** các chunk được thực thi trên worker và mỗi chunk quản lý transaction riêng. Nhưng shared reader/stream state và tài nguyên ngoài transaction vẫn phải được kiểm tra; rollback không biến mọi side effect trở thành atomic.

### Tình huống lỗi thực tế

Ví dụ: item số 29 ghi một request thanh toán bên ngoài, sau đó item số 30 làm chunk thất bại. Khi retry hoặc restart, item số 29 có thể bị thực hiện lại. Nếu request thanh toán đặt trong processor mà không có khóa idempotency, job có thể phát sinh giao dịch kép.

Thiết kế an toàn hơn:

1. Processor chỉ tính ra dữ liệu hoặc quyết định nghiệp vụ; lưu trạng thái bền vững ở writer/transaction phù hợp.
2. Đặt khóa nghiệp vụ duy nhất trên kết quả, ví dụ `order_id` hoặc `job_id + business_key`; dùng ghi idempotent, `UPSERT` hay ràng buộc unique khi phù hợp với database.
3. Nếu gọi dịch vụ bên ngoài, dùng idempotency key do dịch vụ hỗ trợ hoặc thiết kế outbox để phát sự kiện sau commit theo cơ chế riêng.
4. Chỉ retry lỗi tạm thời (timeout, deadlock có thể phục hồi) với giới hạn số lần và backoff hợp lý; lỗi dữ liệu không hợp lệ cần quyết định skip/fail rõ ràng.
5. Test restart bằng cách tiêm lỗi có chủ đích giữa các chunk, chạy lại **cùng JobInstance**, so sánh tập khóa đầu ra và xác nhận không sót/không trùng.

`ExecutionContext` giúp reader/Step lưu checkpoint, nhưng độ an toàn phụ thuộc implementation reader, tính ổn định thứ tự nguồn dữ liệu và mô hình concurrency. `IteratorItemReader` trong ví dụ trên không cung cấp cơ chế checkpoint production. Với workload lớn và yêu cầu restart mạnh, partition theo dải ID hoặc trạng thái xử lý trong database thường dễ kiểm soát hơn chia sẻ một reader stateful.

## 7. Chọn kích thước pool và chunk từ số liệu thực

Không có công thức `threads = số core × 2` luôn đúng. Cần xác định nút thắt trước:

- **CPU-bound:** processor tính toán liên tục; thử pool quanh số CPU khả dụng, đo CPU utilization, context switching và GC.
- **I/O-bound:** processor gọi API/DB; nhiều worker có thể che latency nhưng phải tôn trọng rate limit, connection pool, timeout và tải dịch vụ đích.
- **Read/write-bound (đặc biệt 6.x):** thêm worker cho processor ít giúp khi reader/writer tuần tự đã bão hòa. Cân nhắc local chunking, partitioning hoặc tối ưu SQL/index/batch write.
- **Contended:** nhiều worker tranh chấp row lock, hot partition, connection hoặc memory; tăng thread có thể làm job chậm hơn và tăng deadlock.

Ví dụ một phép thử, không phải cấu hình chuẩn cố định:

| Lần thử | Worker | Chunk size | Điều cần đo |
| --- | ---: | ---: | --- |
| Baseline | 1 | 100 | Tổng thời gian, items/s, DB/CPU, lỗi |
| Thử 1 | 2 | 100 | Có cải thiện không? Độ trễ xử lý item? |
| Thử 2 | 4 | 100 | CPU, DB connection sử dụng, queue wait |
| Thử 3 | 4 | 250 | Commit overhead, bộ nhớ và latency chunk |
| Thử 4 | 8 | 100 | Có chạm trần DB, rate limit hay GC? |

Khi đọc kết quả, so sánh trên **cùng tập dữ liệu, cùng điều kiện hạ tầng và cùng chính sách retry**. Theo dõi tối thiểu `items/second`, thời gian Step/Job, read/process/write time, số rollback/retry/skip, CPU, heap/GC, active/queued threads, Hikari active/pending connections và độ trễ database/API.

### Các giới hạn cần ghép với nhau

```text
Mức song song hữu ích <= min(
    khả năng của TaskExecutor,
    số tác vụ độc lập đang sẵn sàng,
    năng lực CPU / I/O,
    giới hạn database / API / connection pool,
    điểm tuần tự của pipeline
)
```

Với `ThreadPoolTaskExecutor`, `maxPoolSize` không có nghĩa lúc nào pool cũng đạt mức đó: còn phụ thuộc `corePoolSize`, `queueCapacity` và cách submit task. Queue quá nhỏ so với số tác vụ được gửi cùng lúc có thể gây `TaskRejectedException`; queue quá lớn có thể tăng memory và che dấu nghẽn. Cần thử mức cao nhất có thể xuất hiện trong một chunk và quan sát chính sách từ chối tác vụ. Không chỉnh connection pool bằng cách đặt một con số độc lập với số worker thực sự có dùng DB.

## 8. Cách chứng minh Step chạy đúng và nhanh hơn

Một phép kiểm tra nên trả lời đồng thời hai câu hỏi: **có song song thật không?** và **dữ liệu còn đúng không?**

**Quan sát luồng:**

- Trong Spring Batch 6.x, log tên thread ngay trong processor; kỳ vọng thấy nhiều `order-processor-*` khi công việc đủ chậm. Log trong reader/writer để xác minh chúng tuần tự ở main Step thread.
- Trong Spring Batch 5.x, log thread tại reader, processor và writer; kiểm tra các chunk được thực thi ở worker, không dựa vào thứ tự hoàn thành.
- Đối chiếu thread pool active/queue theo thời gian. Có pool bốn thread không chứng minh có bốn tác vụ cùng chạy.

**Kiểm tra tính đúng đắn:**

- Số bản ghi đầu vào = số bản ghi thành công + filtered + skipped + failed theo chính sách nghiệp vụ; kiểm tra cả khóa nghiệp vụ, không chỉ đếm tổng.
- Không có hai bản ghi kết quả cho cùng một khóa nếu nghiệp vụ đòi uniqueness.
- Inject lỗi mạng hoặc DB giữa job, kiểm tra rollback, retry/backoff và restart.
- Chạy với dữ liệu đủ lớn để phơi bày contention, thử cả dữ liệu đầu vào có thứ tự không đồng đều và item xử lý chậm bất thường.
- Kiểm tra dừng job và shutdown: không để công việc phụ tiếp tục thay đổi dữ liệu ngoài phạm vi job sau khi trạng thái đã hoàn tất.

Một truy vấn phát hiện trùng dữ liệu theo khóa nghiệp vụ (thay tên bảng/cột theo hệ thống):

```sql
SELECT order_id, COUNT(*) AS duplicate_count
FROM batch_result
GROUP BY order_id
HAVING COUNT(*) > 1;
```

Khi benchmark, so sánh tổng thời gian chạy, throughput và tỷ lệ lỗi. Tăng throughput không có giá trị nếu rollback, deadlock hoặc việc phải chạy bù tăng nhanh hơn.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Thêm `taskExecutor` nhưng chỉ một thread làm việc | `SyncTaskExecutor`, quá ít item, processor quá nhanh, không phải mô hình/phiên bản đang nghĩ | Log tên thread tại **đúng** thành phần; kiểm tra builder và executor bean |
| Có nhiều thread nhưng không tăng tốc | Reader/writer tuần tự là nút thắt (6.x), khóa DB, pool connection nhỏ, queue wait | Đo thời gian từng giai đoạn; tối ưu nguồn/đích hoặc chọn partitioning |
| Mất/trùng item khi chạy 5.x | Reader shared mutable state, checkpoint hoặc xử lý lại sau rollback | Reader thread-safe, business key duy nhất, quy trình retry/restart đã thử nghiệm |
| Processor 6.x báo không có transaction | Transaction của main thread không được propagate sang worker | Đưa write về writer; nếu cần, mở transaction độc lập qua Spring proxy trong worker |
| `TaskRejectedException` | Pool/hàng đợi đầy, submit quá nhiều tác vụ | Điều chỉnh pool/queue/cơ chế kiểm soát tải, đo tốc độ submit và xử lý |
| Kết quả biến động theo lần chạy | Shared mutable state, giả định thứ tự xử lý | Đưa processor về stateless, loại bỏ phụ thuộc order hoặc sắp xếp theo business key ở giai đoạn cần thiết |
| Retry tạo side effect kép | Gọi API hoặc ghi ngoài transaction, thiếu idempotency | Idempotency key, outbox, unique constraint, phân loại lỗi retry |

## 10. Khi nào nên chuyển sang cách mở rộng khác?

| Nhu cầu | Phương án nên đánh giá |
| --- | --- |
| Công đoạn processor chiếm đa số thời gian, các item độc lập, cùng JVM | `TaskExecutor` trên chunk-oriented Step 6.x |
| Toàn bộ read/process/write cần song song với phân đoạn dữ liệu độc lập | **Partitioning** với StepExecution/ExecutionContext theo partition |
| Các khâu nghiệp vụ tách được thành những Step độc lập | **Parallel Steps** qua split flow |
| Muốn tách việc xử lý chunk ra khỏi luồng đọc/ghi trong cùng JVM ở 6.x | **Local chunking** (tính năng từ Spring Batch 6.0) |
| Workload vượt một JVM, cần worker nhiều máy | **Remote partitioning** hoặc **remote chunking** tùy đơn vị phân phối công việc |
| Chậm do truy vấn SQL hoặc ghi từng row | Tối ưu query/index, phân trang, batch JDBC, tránh phân luồng sớm |

**Nguyên tắc lựa chọn:** ưu tiên thiết kế mà mỗi worker sở hữu phạm vi dữ liệu và cơ chế khôi phục rõ ràng. Khởi đầu với một Step tuần tự, đo bottleneck, sau đó thêm mức song song nhỏ và tăng theo số liệu. Khi tính đúng đắn phụ thuộc thứ tự, checkpoint hoặc transaction xuyên suốt, hãy quyết định kiến trúc trước khi tăng số thread.

## 11. Câu hỏi tự kiểm tra

1. Trong Spring Batch 5.2 và 6.0, cùng gọi `.taskExecutor(executor)` nhưng phần nào chạy đồng thời? Cách xác nhận bằng log là gì?
2. Vì sao `@Transactional(MANDATORY)` trong processor của Spring Batch 6.x có thể thất bại dù Step khai báo transaction manager?
3. Vì sao synchronized reader có thể bảo vệ `read()` nhưng vẫn không bảo đảm restart an toàn?
4. Khi tăng từ bốn lên tám worker mà throughput giảm, cần nhìn vào những metric nào trước?
5. Nếu job gửi yêu cầu thanh toán ra ngoài rồi bị retry, phải thiết kế khóa/idempotency thế nào?
6. Khi processor chỉ chiếm 10% thời gian còn reader/writer chiếm 90%, tăng worker có lợi đến đâu theo Amdahl?

## Tài liệu tham khảo chính thức

- [Spring Batch 6.0 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/6.0/scalability.html): hành vi multi-threaded Step, processor trên worker, transaction theo thread, các kiểu scale.
- [Spring Batch 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html): mô hình chạy toàn bộ chunk trên worker, thread safety, throttle và restart.
- [Spring Batch 6.0 — What’s New](https://docs.spring.io/spring-batch/reference/6.0/whatsnew.html): chunk-oriented model và builder mới.
- [API — ChunkOrientedStepBuilder](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/step/builder/ChunkOrientedStepBuilder.html): chữ ký `taskExecutor(AsyncTaskExecutor)`.
- [API — SynchronizedItemStreamReader](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/infrastructure/item/support/SynchronizedItemStreamReader.html): phạm vi đồng bộ và cảnh báo restart.

**Điểm cần nhớ khi triển khai:** `TaskExecutor` chỉ là cơ chế phân phối công việc. Phiên bản Spring Batch quyết định **đơn vị được chạy song song**; dữ liệu đúng, có thể khởi động lại và có thể quan sát là những tiêu chí bắt buộc trước khi coi việc mở rộng thành công.
