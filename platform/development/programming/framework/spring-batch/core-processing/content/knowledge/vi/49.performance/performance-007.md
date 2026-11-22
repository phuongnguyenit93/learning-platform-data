# CPU trong processor của Spring Batch

## 1. CPU trong ItemProcessor ảnh hưởng đến hiệu năng như thế nào?

Trong Spring Batch Core Processing, một Step xử lý theo chunk thường đọc dữ liệu bằng **ItemReader**, biến đổi hoặc kiểm tra bằng **ItemProcessor**, rồi ghi kết quả bằng **ItemWriter**. Khi processor tính toán nhiều trên từng item, nó có thể trở thành điểm nghẽn chính và quyết định throughput của toàn bộ Job.

Giả sử Step xử lý **2.000.000 giao dịch**, mỗi item tốn trung bình **2 ms CPU** ở processor:

~~~text
2.000.000 item × 2 ms CPU/item
= 4.000.000 ms CPU
= 4.000 giây CPU
≈ 66,7 phút CPU trên một lõi
~~~

Đó mới là chi phí tính toán, chưa gồm đọc file, database, ghi dữ liệu, transaction, garbage collection hoặc chờ tài nguyên. Tăng chunk size có thể giảm chi phí commit nhưng không tự giảm số phép toán cần thực hiện cho từng item.

Mục tiêu của bài này là phân biệt processor **CPU-bound** và **I/O-bound**, đo CPU đúng, tìm phần code tốn tài nguyên, tối ưu thuật toán, chọn chunk size và mức độ song song hợp lý, đồng thời giữ tính đúng đắn của kết quả batch.

## 2. ItemProcessor làm gì?

Contract của processor:

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

Với mỗi item, phương thức **process** có thể:

- Trả về một output để writer ghi.
- Trả về **null** để lọc item theo nghiệp vụ.
- Ném exception; Step có thể fail, skip hoặc retry tùy cấu hình.

~~~text
         ItemReader
             |
             v
      [RawOrder input]
             |
             v
       ItemProcessor
  +----------------------+
  | Chuẩn hóa chuỗi      |
  | Validate mã          |
  | Parse ngày, số tiền  |
  | Áp dụng business rule|
  | Tính toán, mapping   |
  +----------------------+
             |
       +-----+------+
       |            |
    output         null
       |            |
   ItemWriter    filterCount
~~~

Các thao tác tốn CPU thường gặp:

| Hoạt động | Chi phí tiềm ẩn | Điểm kiểm tra |
| --- | --- | --- |
| Regex validation | CPU, backtracking | Pattern có được compile lặp lại không? |
| Parse JSON/XML | CPU và allocation | Có parse nhiều lần cùng input không? |
| Chuẩn hóa chuỗi | CPU và tạo String | Có chuỗi trung gian hoặc replace không cần thiết không? |
| Mapping DTO | CPU, reflection, allocation | Có serialize/deserialize chỉ để map field không? |
| Tính toán tài chính | CPU, BigDecimal allocation | Có tính lặp không cần thiết không? |
| Hash, mã hóa, nén | CPU | Thuật toán có phù hợp dữ liệu không? |
| Tra cứu tham chiếu | CPU hoặc I/O | Lookup trong Set/Map hay gọi DB mỗi item? |
| Ghi log per-item | CPU, object allocation, I/O | Có thể giảm mức log hoặc lấy mẫu không? |

Một processor chạy lâu chưa chắc đang dùng CPU nhiều: nó có thể đang chờ database hoặc HTTP response.

## 3. Phân biệt CPU time và wall-clock time

**Wall-clock time** đo khoảng thời gian thực từ lúc gọi process đến lúc trả về, bao gồm thời gian chờ network, lock, disk, thread scheduling. **CPU time** là thời gian CPU thực sự thực thi thread, theo khả năng đo của JVM/hệ điều hành.

~~~text
Processor A: tính toán liên tục
Wall time ≈ 100 ms
CPU time  ≈  95 ms

Processor B: gọi API bên ngoài
Wall time ≈ 100 ms
CPU time  ≈   5 ms
I/O wait  ≈  95 ms
~~~

Cả hai có latency khoảng 100 ms, nhưng giải pháp khác nhau. A cần cải thiện phép tính hoặc song song hóa nếu còn CPU; B cần giảm round-trip, cache, batch request hoặc concurrency I/O.

| Chỉ số | Cho biết | Không chứng minh |
| --- | --- | --- |
| JVM/process CPU usage | CPU đang dùng bởi toàn JVM | Mọi CPU đều thuộc processor |
| Per-thread CPU time | CPU đã dùng bởi một thread | CPU ở thread khác được gọi gián tiếp |
| Process wall time | Latency của lời gọi processor | CPU đã được tiêu thụ hết trong khoảng đó |
| Allocation rate | Tốc độ tạo object | Bản thân allocation chắc chắn là bottleneck |
| GC CPU/pause | Chi phí thu gom bộ nhớ | Nguyên nhân chính nằm tại processor |
| Step read/write throughput | Item xử lý mỗi giây | Đoạn code nào chậm |
| Chunk duration | Tổng thời gian một vòng chunk | Thời gian của riêng processor |

Khi CPU toàn process cao, cần profiler xác định thread và stack frame gây tải. Khi CPU thấp và Step chậm, nên kiểm tra database, mạng, connection pool và lock.

## 4. CPU/item ảnh hưởng throughput

Nếu một item cần **0,5 ms CPU**, năng suất lý tưởng của một lõi dành toàn thời gian cho processor là:

~~~text
CPU/item = 0,0005 giây
1 / 0,0005 ≈ 2.000 item / CPU giây
~~~

Đây không phải throughput thực tế của toàn Step vì còn reader, writer, commit, GC và các chi phí khác.

Có thể ước lượng thời gian CPU tối thiểu của N item trên c lõi thực sự có thể dùng:

~~~text
T_cpu_ideal ≈ N × cpuSecondsPerItem / c
~~~

Công thức là cận lý tưởng; không phải lời hứa sẽ tăng tốc tuyến tính theo số thread. CPU quota của container, lock, reader tuần tự và writer là các giới hạn thường gặp.

Ví dụ Step tốn 100 giây, trong đó 70 giây ở processor và 30 giây ở các phần khác. Nếu tối ưu processor nhanh gấp đôi nhưng các phần khác giữ nguyên:

~~~text
T_mới ≈ 70 / 2 + 30 = 65 giây
Speedup toàn Step ≈ 100 / 65 = 1,54 lần
~~~

Đây là trực giác của **Amdahl's law**: tăng tốc một thành phần không khiến toàn hệ thống tăng tốc cùng tỷ lệ.

## 5. Xác định CPU-bound bằng quan sát và profiler

Trước khi sửa code, thu thập **baseline**:

- Thời lượng Job/Step, readCount, writeCount, filterCount và số item/giây.
- Chunk duration p50, p95, p99.
- Process CPU usage so với số lõi và CPU quota của container.
- CPU throttling nếu chạy trong Kubernetes.
- GC time, allocation rate, heap usage.
- Database query latency, connection pool, lock waits.
- Latency của HTTP/API nếu processor gọi hệ thống ngoài.

**Thread state RUNNABLE không luôn có nghĩa đang thực thi CPU**. Một thread có thể đợi I/O trong native call nhưng vẫn được biểu diễn RUNNABLE. CPU sampling và thread CPU time mới giúp phân biệt chắc hơn.

### Java Flight Recorder

Trên JVM hỗ trợ **jcmd** và **Java Flight Recorder (JFR)**, có thể ghi profile trong thời điểm Job thực sự đang xử lý:

~~~bash
jcmd 12345 JFR.start name=batch-cpu settings=profile duration=120s filename=/tmp/batch-cpu.jfr
~~~

Trong đó **12345** là PID của JVM. Mở file JFR bằng **Java Mission Control** để xem CPU samples, allocations, GC và thread events.

Ví dụ call tree minh họa:

~~~text
OrderProcessor.process                    70% CPU samples
  normalizeAddress                        28%
    String.replaceAll                     23%
  calculateFees                           24%
    BigDecimal.multiply                   18%
  validateReference                       12%
  mapping                                  6%

Reader, writer, JVM và công việc khác        30%
~~~

Nếu normalizeAddress chiếm nhiều CPU, việc tối ưu câu lệnh ở đó có khả năng hữu ích hơn thay đổi chunk size ngẫu nhiên. **Async-profiler** và flame graph cũng có thể tìm CPU hot spots, allocations và lock contention; cần chọn profile phù hợp với môi trường.

Hãy ghi nhận phiên bản JVM, dataset, cấu hình CPU và thời điểm profile. Profile chỉ trong lúc Job khởi động có thể cho thấy class loading/JIT thay vì workload thật.

## 6. Đo latency của processor bằng Micrometer

Micrometer **Timer** đo wall-clock duration; đây là metric hữu ích cho p50/p95/p99 nhưng **không phải CPU time thuần**.

Một decorator có thể bọc processor:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.item.ItemProcessor;

public final class TimedProcessor<I, O>
        implements ItemProcessor<I, O> {

    private final ItemProcessor<I, O> delegate;
    private final Timer timer;

    public TimedProcessor(
            ItemProcessor<I, O> delegate,
            MeterRegistry registry,
            String job,
            String step) {

        this.delegate = delegate;
        this.timer = Timer.builder("app.batch.processor.duration")
                .description("Wall time per processor invocation")
                .tags("job", job, "step", step)
                .register(registry);
    }

    @Override
    public O process(I item) throws Exception {
        long start = System.nanoTime();

        try {
            return delegate.process(item);
        } finally {
            timer.record(
                    System.nanoTime() - start,
                    TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Gắn processor đã bọc vào Step:

~~~java
ItemProcessor<RawOrder, NormalizedOrder> measured =
        new TimedProcessor<>(
                rawOrderProcessor,
                meterRegistry,
                "importOrdersJob",
                "importOrdersStep");

return new StepBuilder("importOrdersStep", jobRepository)
        .<RawOrder, NormalizedOrder>chunk(500, transactionManager)
        .reader(reader)
        .processor(measured)
        .writer(writer)
        .build();
~~~

Timer đo cả lần gọi trả về output, **null** hoặc ném exception do nằm trong khối **finally**. Nếu có retry, một item có thể được đo nhiều lần vì metric biểu diễn **invocation**, không phải item nghiệp vụ duy nhất.

**Không gắn customerId, orderId, UUID hoặc jobExecutionId làm metric tag dài hạn**, vì cardinality sẽ tăng theo từng item hoặc lần chạy. Các ID ấy thích hợp cho log/tracing. Với hàng triệu item, instrumentation per-item cũng có overhead; cần cân nhắc sampling và đo chi phí của instrumentation.

## 7. Đo CPU time của thread bằng ThreadMXBean

Java cung cấp **ThreadMXBean** để lấy CPU time thread hiện tại trên nền tảng hỗ trợ.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public final class ProcessorCpuProbe {

    private final ThreadMXBean bean =
            ManagementFactory.getThreadMXBean();

    public long measureCpuNanos(Runnable operation) {
        if (!bean.isCurrentThreadCpuTimeSupported()
                || !bean.isThreadCpuTimeEnabled()) {
            throw new IllegalStateException(
                    "Thread CPU time unavailable or disabled");
        }

        long before = bean.getCurrentThreadCpuTime();
        operation.run();
        long after = bean.getCurrentThreadCpuTime();

        return after - before;
    }
}
~~~

Dùng với một phép tính:

~~~java
ProcessorCpuProbe probe = new ProcessorCpuProbe();
long nanos = probe.measureCpuNanos(
        () -> normalizationService.normalize(sampleOrder));
~~~

Giới hạn:

1. Chỉ đo CPU của **thread hiện tại**. Nếu processor gửi công việc sang thread pool, CPU của thread phụ không nằm trong kết quả đó.
2. JVM hoặc hệ điều hành có thể không hỗ trợ hoặc đang tắt thread CPU time.
3. Đo từng item rất nhỏ có thể tạo overhead đáng kể; nên đo nhiều item, lấy mẫu hoặc dùng JFR.
4. Thời gian chờ I/O, sleep hoặc lock không có cùng ý nghĩa với CPU time.
5. Warm-up, JIT và công việc khác trong JVM có thể ảnh hưởng phép đo.

CPU probe thích hợp để chẩn đoán có kiểm soát; không nhất thiết phải thêm vào đường xử lý production của mọi item.

## 8. Ví dụ tối ưu processor bị tốn CPU bởi regex

Giả sử input có mã khách hàng, số tiền và thời điểm. Các model:

~~~java
public record RawOrder(
        String orderId,
        String customerCode,
        String amount,
        String occurredAt) {}

public record NormalizedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount,
        OffsetDateTime occurredAt) {}
~~~

### Cách viết có nhiều công việc lặp

~~~java
public final class SlowOrderProcessor
        implements ItemProcessor<RawOrder, NormalizedOrder> {

    @Override
    public NormalizedOrder process(RawOrder item) {
        String code = item.customerCode()
                .trim()
                .toUpperCase(Locale.ROOT);

        // Compile regex lại cho mọi item.
        if (!Pattern.compile("[A-Z0-9]{6,20}")
                .matcher(code)
                .matches()) {
            return null;
        }

        BigDecimal amount =
                new BigDecimal(item.amount().trim());

        OffsetDateTime occurredAt =
                OffsetDateTime.parse(item.occurredAt());

        return new NormalizedOrder(
                item.orderId(), code, amount, occurredAt);
    }
}
~~~

### Tái sử dụng đối tượng bất biến

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Locale;
import java.util.regex.Pattern;
import org.springframework.batch.item.ItemProcessor;

public final class EfficientOrderProcessor
        implements ItemProcessor<RawOrder, NormalizedOrder> {

    private static final Pattern CUSTOMER_CODE =
            Pattern.compile("[A-Z0-9]{6,20}");

    @Override
    public NormalizedOrder process(RawOrder item) {
        String code = item.customerCode()
                .trim()
                .toUpperCase(Locale.ROOT);

        if (!CUSTOMER_CODE.matcher(code).matches()) {
            return null;
        }

        BigDecimal amount =
                new BigDecimal(item.amount().trim());

        OffsetDateTime occurredAt =
                OffsetDateTime.parse(item.occurredAt());

        return new NormalizedOrder(
                item.orderId(), code, amount, occurredAt);
    }
}
~~~

**Pattern** có thể chia sẻ giữa thread sau khi compile. Mỗi lời gọi vẫn tạo **Matcher** mới vì Matcher có trạng thái và không thread-safe. Với formatter của package **java.time**, có thể dùng đối tượng **DateTimeFormatter** bất biến dùng chung, khác với **SimpleDateFormat** mutable.

Cải thiện có thể đến từ giảm regex compilation; nhưng phải **benchmark** trước khi tuyên bố mức tăng cụ thể. Với dataset nhỏ, thay đổi có thể không đáng kể nếu nút thắt thực tế ở writer.

Những ý tưởng tối ưu khác:

- Tránh parse cùng dữ liệu nhiều lần trong pipeline.
- Tránh serialize DTO sang JSON rồi parse lại chỉ để map field.
- Tránh chuỗi gọi **replaceAll** không cần thiết.
- Dùng Set/Map để tra cứu tham chiếu lặp lại nếu dữ liệu phù hợp.
- Giảm phép tính hoặc object trung gian không cần thiết.
- Giữ nguyên quy tắc làm tròn BigDecimal trong nghiệp vụ tài chính.
- Tránh log per-item khi không thực sự cần.

Tối ưu code không được làm đổi semantics của **filter**, **skip**, dữ liệu đầu ra hay transaction.

## 9. Thuật toán và dữ liệu bất thường

### Regex backtracking

Các pattern có lượng từ lồng nhau và nhiều cách match có thể dùng CPU rất lớn khi gặp input bất thường. Với batch hàng triệu item, một vài chuỗi cực dài cũng có thể kéo p99 processor latency lên cao.

Cần:

- Giới hạn độ dài input khi phù hợp nghiệp vụ.
- Chọn regex đơn giản và rõ nghĩa.
- Test cả dữ liệu hợp lệ, dữ liệu lỗi và input cực trị.
- Dùng parser chuyên dụng cho ngôn ngữ phức tạp.
- Xem CPU profile để chứng minh regex là hot spot.

### Độ phức tạp của cấu trúc tra cứu

Nếu processor kiểm tra một mã trong danh sách 100.000 phần tử:

~~~java
// Tra cứu List có thể phải duyệt tuyến tính.
boolean allowed = allowedCodesList.contains(code);
~~~

Với tập mã cố định, một **HashSet** có thể giảm chi phí tra cứu trung bình:

~~~java
private final Set<String> allowedCodes =
        Set.copyOf(referenceCodes);

public boolean allowed(String code) {
    return allowedCodes.contains(code);
}
~~~

Cần cân nhắc memory và tính nhất quán: nếu tập reference thay đổi giữa chừng, các item của cùng Job có thể được đánh giá theo những phiên bản quy tắc khác nhau. Một snapshot cố định theo kỳ xử lý thường dễ kiểm thử hơn.

### Allocation và GC

Nhiều object ngắn hạn có thể khiến JVM dùng CPU đáng kể để GC. Các nguồn phổ biến là String trung gian, mapping lặp, tạo Collection tạm và parse JSON thành object tree lớn.

Dùng allocation profiler để tìm nơi tạo object rồi cải thiện. Không nên tái sử dụng một output object mutable duy nhất cho nhiều item: writer có thể giữ reference và ghi nhiều dòng từ cùng trạng thái cuối cùng.

## 10. Processor gọi database hoặc API là I/O-bound

Một processor như sau có thể chậm dù CPU thấp:

~~~java
@Override
public Output process(Input item) {
    Customer customer = repository.findById(item.customerId())
            .orElseThrow();
    return convert(item, customer);
}
~~~

Mỗi item tạo một database query; với rất nhiều item đây là **N+1 lookup**. Nếu mỗi query mất 5 ms wall-clock, tăng CPU không giải quyết được bottleneck.

Các phương án phù hợp tùy nghiệp vụ:

- Thực hiện join/lookup ngay tại câu truy vấn của reader.
- Batch query thay vì truy vấn riêng từng item.
- Tiền tải tập dữ liệu tham chiếu nhỏ vào Map/Set.
- Dùng cache có kích thước và chính sách làm mới rõ ràng.
- Kiểm tra index, query plan, connection pool và latency.
- Với HTTP API, cân nhắc batch endpoint và giới hạn concurrency.

**Cache không giới hạn** theo hàng triệu customer ID có thể làm tăng heap/GC và khiến hệ thống chậm hơn. Nếu cache chứa dữ liệu có thể thay đổi, cần quy định sự nhất quán giữa các item và giữa những lần restart.

## 11. Chunk size có giúp processor CPU-bound?

Mô hình đơn giản:

~~~text
T_total ≈ N × T_cpu_per_item
        + ceil(N / chunkSize) × T_fixed_per_chunk
        + T_other
~~~

Giả sử processor cần **1 ms CPU/item** trên một triệu item, còn overhead mỗi chunk khoảng **10 ms**:

~~~text
Processor CPU cost ≈ 1.000 giây

Chunk size 100:
  10.000 chunk × 10 ms ≈ 100 giây overhead

Chunk size 500:
   2.000 chunk × 10 ms ≈  20 giây overhead
~~~

Đổi chunk size từ 100 lên 500 giảm overhead giả định khoảng 80 giây nhưng không xóa chi phí tính toán 1.000 giây. Nếu CPU processor là thành phần chi phối, cải thiện thuật toán có thể hiệu quả hơn.

Chunk size quá lớn còn có chi phí:

- Bộ nhớ giữ nhiều item trong chunk.
- Transaction và database lock tồn tại lâu hơn.
- Khi rollback/retry có thể phải xử lý lại nhiều item.
- Checkpoint thưa hơn, tăng lượng công việc làm lại sau crash.
- Metric tiến độ chỉ cập nhật khi chunk hoàn tất.

Tốt nhất benchmark nhiều chunk size trên workload thật với cùng reader, processor và writer, rồi chọn theo throughput, memory và khả năng phục hồi.

## 12. Xử lý song song khi CPU còn dư

Nếu profiler xác nhận processor CPU-bound và từng item độc lập, chạy nhiều chunk đồng thời có thể giúp dùng nhiều CPU core. Spring Batch có thể cấu hình TaskExecutor cho Step:

~~~java
@Bean
ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setThreadNamePrefix("batch-worker-");
    executor.initialize();
    return executor;
}

@Bean
Step parallelImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> reader,
        ItemProcessor<RawOrder, NormalizedOrder> processor,
        ItemWriter<NormalizedOrder> writer,
        ThreadPoolTaskExecutor batchTaskExecutor) {

    return new StepBuilder("parallelImportStep", jobRepository)
            .<RawOrder, NormalizedOrder>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(batchTaskExecutor)
            .build();
}
~~~

Đây là ví dụ cú pháp, **chưa đủ để đưa ngay vào production**. Trước khi dùng cần xác định:

1. Reader có thread-safe và checkpoint có còn đúng khi chunk hoàn thành không theo thứ tự?
2. Processor có stateless hoặc chỉ dùng immutable shared state không?
3. Writer có hỗ trợ các chunk chạy đồng thời, có giao dịch/idempotency phù hợp không?
4. Thứ tự output có cần giữ nguyên input không?
5. JDBC pool, JobRepository, DB và CPU quota có chịu được concurrency mới không?
6. Khi retry/restart, dữ liệu có còn đúng và không bị ghi trùng không?

Nhiều reader có cursor/stateful không tự an toàn khi dùng đa luồng. Chỉ bọc synchronized không chắc giải quyết được tính chính xác của checkpoint/restart. **Partitioning theo khóa dữ liệu không giao nhau** có thể phù hợp hơn trong một số hệ thống.

### Chọn số worker

Với CPU-bound thuần, nên bắt đầu từ số worker xấp xỉ CPU core thực sự được cấp, rồi đo. Nếu container có quota 2 vCPU, tạo 16 worker CPU-bound thường chỉ tăng context switch và cạnh tranh.

Nếu 80% thời gian có thể song song hóa, bốn worker lý tưởng đem lại giới hạn:

~~~text
Speedup <= 1 / (0,2 + 0,8/4)
        = 2,5 lần
~~~

Phần xử lý tuần tự, I/O, lock và overhead đồng bộ làm tốc độ thực tế thấp hơn giới hạn lý tưởng.

## 13. Processor phải thread-safe

Một processor singleton có mutable state có thể gây race khi Step dùng nhiều thread:

~~~java
public class UnsafeProcessor
        implements ItemProcessor<RawOrder, NormalizedOrder> {

    private int processedCount;
    private String lastCode;

    @Override
    public NormalizedOrder process(RawOrder item) {
        processedCount++;
        lastCode = item.customerCode();

        // Chuyển đổi và trả về kết quả...
        return ...;
    }
}
~~~

**processedCount++** không atomic, còn **lastCode** bị các worker ghi đè. Không giữ state nghiệp vụ của item hiện tại trong field chung.

Các phương án tốt:

- Biến trung gian nằm trong phương thức process.
- Dùng **Pattern** và **DateTimeFormatter** bất biến dùng chung.
- Tạo Matcher mới cho từng lượt xử lý.
- Đặt dữ liệu reference read-only trong immutable collection.
- Nếu cần state theo StepExecution, dùng scope thích hợp và kiểm tra thêm khả năng các thread cùng chạy trong một StepExecution.
- Không tự ghi ExecutionContext từ nhiều thread nếu chưa thiết kế checkpoint.
- Dùng counters do StepExecution quản lý để theo dõi, tránh tự sửa metadata.

**@StepScope** tạo phạm vi bean theo StepExecution nhưng không tự làm mọi field mutable an toàn nếu một StepExecution xử lý nhiều chunk đồng thời.

## 14. Benchmark CPU processor

### Benchmark cấp phương thức với JMH

**JMH** hỗ trợ warm-up, đo nhiều iteration và giảm các bẫy do JVM/JIT gây ra. Ví dụ:

~~~java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
public class OrderProcessorBenchmark {

    private final EfficientOrderProcessor processor =
            new EfficientOrderProcessor();

    private final RawOrder input = new RawOrder(
            "ORD-001",
            " abc12345 ",
            "123.45",
            "2026-11-15T10:30:00Z");

    @Benchmark
    public NormalizedOrder normalize() throws Exception {
        return processor.process(input);
    }
}
~~~

Ví dụ giả định model/processor đã định nghĩa ở phần trên và dự án có dependency cùng runner JMH. Với benchmark thực, hãy tạo nhiều input đại diện; chỉ lặp một input có thể được hưởng lợi từ cache/JIT và không phản ánh production.

JMH chỉ đo phần code mục tiêu. Nó không bao gồm transaction, JDBC, writer hoặc thời lượng end-to-end của Spring Batch.

### Benchmark tích hợp Step

Một thí nghiệm đủ tin cậy nên ghi:

~~~text
dataset_version
processor_version
chunk_size
worker_threads
cpu_limit
read_count / write_count / filter_count / skip_count
duration_seconds
output_items_per_second
processor_wall_p50 / p95 / p99
cpu_seconds_per_item
gc_pause_ms / allocation_rate
rollback_count
database_latency
~~~

Quy trình:

1. Cố định dataset, reader, writer và hạ tầng.
2. Warm up hợp lý trước measurement.
3. Chạy nhiều lần cho mỗi phiên bản processor.
4. So sánh median, p95, throughput và CPU time.
5. Chỉ thay một biến chính trong một nhóm thí nghiệm.
6. Kiểm tra đầu ra có đúng và không mất/trùng item.
7. Kiểm tra lỗi, rollback, restart nếu ứng dụng có dùng.

Không đặt ngưỡng tuyệt đối kiểu “phải đạt 10.000 item/giây” làm điều kiện pass/fail trên CI chia sẻ tài nguyên, trừ khi môi trường benchmark được kiểm soát.

## 15. Kiểm tra correctness sau tối ưu

Sau khi tối ưu processor, cần đảm bảo output và quy tắc filter không đổi.

Ví dụ unit test với JUnit 5 và AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class EfficientOrderProcessorTest {

    private final EfficientOrderProcessor processor =
            new EfficientOrderProcessor();

    @Test
    void normalizesValidOrder() throws Exception {
        RawOrder input = new RawOrder(
                "ORD-001",
                " abc12345 ",
                "123.45",
                "2026-11-15T10:30:00Z");

        NormalizedOrder output = processor.process(input);

        assertThat(output).isNotNull();
        assertThat(output.customerCode()).isEqualTo("ABC12345");
        assertThat(output.amount()).isEqualByComparingTo("123.45");
    }

    @Test
    void filtersInvalidCode() throws Exception {
        RawOrder input = new RawOrder(
                "ORD-002",
                "bad!",
                "20.00",
                "2026-11-15T10:30:00Z");

        assertThat(processor.process(input)).isNull();
    }
}
~~~

Test này kiểm tra quy tắc xử lý, **không đo hiệu năng**. Trong integration test, nên assert thêm BatchStatus, read/write/filter/skip counts và dữ liệu đích. Nếu chạy đa luồng, cần kiểm thử tính đúng đắn khi nhiều thread xử lý cùng Step. Với restart và retry, phải giữ kết quả nhất quán.

## 16. Những dấu hiệu và cách chẩn đoán thường gặp

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| CPU gần quota, processor chiếm CPU profile | Thuật toán tốn CPU | Tối ưu hot methods, đo lại CPU/item |
| CPU cao, GC time cao | Allocation lớn | Lấy allocation profile, giảm object tạm |
| CPU thấp, process wall p95 cao | Chờ DB/API/lock | Đo latency và giảm I/O round-trip |
| CPU cao, thêm thread không tăng item/s | CPU saturation hoặc contention | Xem CPU quota/throttling, lock và bộ nhớ |
| Chunk size tăng nhưng throughput không đổi | CPU/item chi phối | Tối ưu processor thay vì commit |
| Một số item có p99 rất cao | Regex, parse hoặc input bất thường | Test dữ liệu biên, profile call stack |
| Thêm log làm Job chậm | Logging per-item | Giảm log hoặc sampling |
| Processor nhanh nhưng Job vẫn chậm | Reader, writer, commit | Đo riêng pipeline |
| Sau restart CPU tăng | Retry/đọc lại chunk chưa checkpoint | Xem rollback và trạng thái checkpoint |
| Output sai sau parallelism | State dùng chung hoặc thứ tự thay đổi | Làm processor stateless, kiểm tra reader/writer |

## 17. Quy trình tối ưu CPU trong processor

Một quy trình áp dụng được cho Spring Batch production:

**Bước 1 — Đo baseline.** Ghi thời lượng Job, read/write throughput, processor wall time, CPU usage, GC và database metrics.

**Bước 2 — Xác nhận bottleneck.** Dùng CPU profiler để phân biệt processor tính toán với thread chờ I/O hoặc GC.

**Bước 3 — Chọn hot spot.** Tập trung vào phương thức chiếm nhiều CPU samples, allocations hoặc thời gian xử lý dữ liệu biên.

**Bước 4 — Tối ưu nhỏ và có mục tiêu.** Bỏ parse/compile lặp, cải thiện cấu trúc dữ liệu, giảm tính toán không cần thiết. Giữ nguyên quy tắc nghiệp vụ.

**Bước 5 — Benchmark lại.** Dùng cùng workload, so CPU seconds/item, output items/giây, wall p95, GC và memory.

**Bước 6 — Xác minh correctness.** Assert dữ liệu đích, filter/skip counts, exception behavior và kết quả khi retry/restart.

**Bước 7 — Cân nhắc concurrency.** Chỉ thêm worker khi còn CPU và reader/processor/writer có khả năng xử lý đồng thời an toàn.

**Bước 8 — Tiếp tục quan sát.** Theo dõi p95 processor duration, CPU throttling, throughput và rollback khi workload thay đổi.

Ví dụ dashboard minh họa:

~~~text
Job: importOrdersJob               Status: STARTED
Step: normalizeOrdersStep          Chunk size: 500
StepExecution: 4972

Read count:            80.000
Write count:           77.500
Filter count:           2.500
Rollback count:             0

Output throughput:     3.100 items/s
Processor wall p50:    0,18 ms
Processor wall p95:    0,65 ms
JVM CPU usage:         82% of CPU quota
GC time:               1,5% of elapsed
Chunk duration p95:    190 ms
~~~

Các giá trị này chỉ để minh họa. **CPU usage 82% của JVM không đồng nghĩa processor dùng 82% CPU**; profiler theo thread và call stack mới giúp quy trách nhiệm chính xác.

Để tối ưu **CPU trong processor**, cần điều trị đúng nguyên nhân: giảm CPU/item khi thuật toán chậm, giảm chờ I/O khi processor gọi dịch vụ ngoài, giảm allocation khi GC chiếm tài nguyên và chỉ tăng concurrency khi phần còn lại của pipeline chịu được tải. Thành công cần được đo bằng **throughput thực, dữ liệu nghiệp vụ chính xác và khả năng rollback/restart đáng tin cậy**, thay vì chỉ nhìn số thread hay phần trăm CPU.

