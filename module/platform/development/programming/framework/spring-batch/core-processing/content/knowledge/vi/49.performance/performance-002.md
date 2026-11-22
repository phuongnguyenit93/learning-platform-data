# Latency của reader, processor và writer trong Spring Batch

## 1. Hiểu đúng độ trễ ở ba giai đoạn của một batch step

Một Spring Batch job có thể xử lý đúng dữ liệu nhưng không đạt yêu cầu thời gian: nhập 2 triệu giao dịch mất 4 giờ thay vì 20 phút, số bản ghi mỗi giây thấp, hoặc tiến độ bị đứng nhiều phút trước khi tiếp tục. Muốn tối ưu hiệu quả, trước hết phải biết thời gian thực sự nằm ở **reader**, **processor** hay **writer**, và phần thời gian nào thuộc transaction, checkpoint, framework hoặc hệ thống bên ngoài.

Với chunk-oriented step, luồng xử lý điển hình là:

```text
                      Chunk-oriented Step
                               |
                 +-------------v-------------+
                 | ItemReader.read()         |
                 | lấy một item hoặc null    |
                 +-------------+-------------+
                               |
                 +-------------v-------------+
                 | ItemProcessor.process()   |
                 | đổi/lọc item, có thể null  |
                 +-------------+-------------+
                               |
                 | lặp đến đủ chunk / EOF |
                               |
                 +-------------v-------------+
                 | ItemWriter.write(Chunk)   |
                 | ghi cả nhóm output items  |
                 +-------------+-------------+
                               |
                 +-------------v-------------+
                 | transaction commit,       |
                 | checkpoint, metadata...   |
                 +---------------------------+
```

Trong cấu hình đồng bộ thông thường, reader được gọi nhiều lần, mỗi item được processor xử lý rồi được gom thành chunk trước khi writer được gọi. Một chunk có thể chứa ít item hơn chunk size nếu processor lọc bớt hoặc đã đến cuối input.

**Latency** là thời gian một thao tác cụ thể hoàn tất. Cần định nghĩa thao tác đó trước khi đo:

- **Reader latency**: thời gian một lần `ItemReader.read()` trả về item/`null` hoặc ném lỗi.
- **Processor latency**: thời gian một lần `ItemProcessor.process(item)` trả về output/`null` hoặc ném lỗi.
- **Writer latency**: thời gian một lần `ItemWriter.write(chunk)` xử lý một **chunk**; đây không phải phép đo theo từng item.
- **Step wall time**: khoảng thời gian step chạy từ lúc bắt đầu đến khi kết thúc, bao gồm cả overhead mà ba phép đo trên có thể chưa nắm bắt.

Mục tiêu của bài là xây dựng cách đo có ý nghĩa, sử dụng các số đo để xác định bottleneck và lựa chọn hướng tối ưu phù hợp, đồng thời không làm sai checkpoint, restart hoặc kết quả nghiệp vụ.

Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Batch 5.x, Micrometer và JUnit 5**. API của Spring Batch 6.x có một số thay đổi; khi nâng cấp cần đối chiếu import và builder theo phiên bản đang dùng.

---

## 2. Latency, throughput và tổng thời gian liên quan thế nào?

### 2.1. Các khái niệm nền tảng

| Thuật ngữ | Ý nghĩa | Đơn vị ví dụ |
| --- | --- | --- |
| Reader latency | Thời gian một lần `read()` | ms/call hoặc ms/item |
| Processor latency | Thời gian một lần `process()` | ms/call hoặc ms/item |
| Writer latency | Thời gian một lần `write(chunk)` | ms/chunk |
| Effective writer cost | Writer time chia số item ghi, dùng để so sánh sơ bộ | ms/output item |
| Throughput | Số item hoàn tất trong một đơn vị thời gian | items/s |
| End-to-end duration | Thời gian toàn bộ step/job hoàn tất | s, phút, giờ |
| Queue/wait time | Thời gian chờ connection, lock, thread, network, buffer | ms |
| Tail latency | Các lần gọi chậm bất thường, thường quan sát qua p95/p99 | ms |

**Đừng cộng trực tiếp số p95** của reader, processor và writer để suy ra p95 step. p95 của mỗi stage đến từ các lần gọi khác nhau; phép cộng không mô tả một phân phối end-to-end chính xác.

### 2.2. Mô hình thời gian cho một step đồng bộ

Đặt:

- \(N_r\): số lần reader được gọi.
- \(N_p\): số lần processor được gọi.
- \(N_w\): số lần writer được gọi, thường là số chunk có output.
- \(\bar t_r\), \(\bar t_p\): trung bình thời gian một lần read/process.
- \(\bar t_w\): trung bình thời gian một lần write(chunk).
- \(T_o\): các overhead còn lại (transaction commit/rollback, callback, checkpoint, scheduling, logging...).

Mô hình gần đúng trong một step đơn luồng tuần tự:

\[
T_{\mathrm{step}} \approx N_r\bar t_r + N_p\bar t_p + N_w\bar t_w + T_o
\]

Đây là **mô hình chẩn đoán**, không phải đẳng thức cứng trong mọi trường hợp. Với retry, skip, item filtering, I/O prefetch hoặc xử lý song song, số lần gọi, thời gian chờ và concurrency có thể làm các đại lượng khác nhiều so với số item đầu ra.

### 2.3. Ví dụ tính bottleneck

Giả sử step xử lý 10.000 item, chunk size 100, không filter/skip và không retry; các số đo minh họa:

| Thành phần | Số lần gọi xấp xỉ | Trung bình | Tổng thời gian gọi |
| --- | ---: | ---: | ---: |
| Reader | 10.001 (gồm EOF) | 1,5 ms | ~15 s |
| Processor | 10.000 | 0,3 ms | 3 s |
| Writer | 100 | 40 ms/chunk | 4 s |
| Transaction + framework | — | — | 2 s |
| **Toàn step** | — | — | **~24 s** |

Throughput xấp xỉ \(10.000 / 24 \approx 417\) item/s. Trong tình huống này, ưu tiên điều tra reader vì tổng reader time lớn hơn processor và writer, dù mỗi writer call riêng lẻ mất 40 ms, lớn hơn một reader call.

Không được kết luận “writer chậm nhất” chỉ vì 40 ms > 1,5 ms: **đơn vị đo khác nhau**.

### 2.4. Writer latency per item chỉ là phép chuẩn hóa

Nếu một chunk 100 item mất 40 ms để ghi, chi phí trung bình gần đúng là:

\[
40\ \mathrm{ms/chunk}\;/\;100\ \mathrm{items/chunk}
=0{,}4\ \mathrm{ms/item}
\]

Nhưng phép chia này không nói rằng mỗi item được ghi mất 0,4 ms thật. Writer có thể gửi một lệnh JDBC batch, chờ lock, serialize một payload hay flush toàn bộ buffer theo lô. Một chunk 1 item và 100 item có thể có chi phí cố định khác nhau; vì vậy nên giữ **cả writer latency per chunk, chunk item count và throughput**.

---

## 3. Chọn vị trí đo để không kết luận nhầm

### 3.1. Các ranh giới có thể đo

```text
read() ─┐  measured read latency
        └─> process() ─┐ measured process latency
                       └─> add to chunk
                            ...
                            write(chunk) ─┐ measured writer latency
                                         └─> ItemStream.update()
                                              DB commit
                                              Batch metadata update
                                              Step listener...
```

Đo bao quanh đúng ba method sẽ thấy thời gian **bên trong hoặc do lời gọi delegate chờ**, nhưng thường không gồm mọi thời gian commit sau writer.

Ví dụ writer gọi `jdbcTemplate.batchUpdate(...)` mất 20 ms; sau đó transaction manager commit mất 300 ms vì database flush WAL. Một timer chỉ bao quanh `writer.write(...)` có thể báo 20 ms trong khi step vẫn chậm vì commit. Cần phối hợp metric transaction/JDBC và step wall time để giải thích phần còn thiếu.

### 3.2. Mỗi loại số đo trả lời một câu hỏi

| Cần biết | Đo ở đâu |
| --- | --- |
| Một lần đọc chậm ở đâu? | Bao quanh `ItemReader.read()`; JDBC/query/network profiling bên trong |
| Processor tốn CPU hay I/O? | Timer quanh `process()` kết hợp CPU profiler, network/client metric |
| Ghi một chunk mất bao lâu? | Timer quanh `ItemWriter.write(Chunk)` |
| Commit chậm? | Transaction/JDBC metrics, connection pool, database logs |
| Step hoàn tất sau bao lâu? | Step execution duration hoặc wall-clock timer |
| Có retry/rollback làm tăng số lần gọi? | `StepExecution` counts, retry metrics, lỗi theo stage |
| Tác vụ thực sự phục vụ bao nhiêu record/s? | Số record nghiệp vụ thành công / end-to-end duration |
| Batch có bị scheduler khởi động trễ? | Scheduled time so với actual `JobExecution` start time |

**Một số đo đơn lẻ không đại diện cho toàn bộ pipeline.** Cần đồng thời xem latency, call count, throughput, error/rollback counts và tài nguyên hệ thống.

---

## 4. Spring Batch metadata hữu ích nhưng chưa phải profiler

`StepExecution` tích lũy các counter vận hành:

```java
StepExecution step = ...;

long read = step.getReadCount();
long write = step.getWriteCount();
long filtered = step.getFilterCount();
long readSkipped = step.getReadSkipCount();
long processSkipped = step.getProcessSkipCount();
long writeSkipped = step.getWriteSkipCount();
long rollback = step.getRollbackCount();
long commits = step.getCommitCount();
```

Các counter cho biết **kết quả xử lý theo semantics của Spring Batch**, không phải trực tiếp các sample thời gian của `read()`, `process()` hay `write()`. Đừng suy luận rằng `readCount` luôn đúng bằng số lần gọi Java khi có retry/rollback, EOF hoặc các cơ chế reader đặc thù.

Trong nhiều trường hợp, `StepExecution.getStartTime()` và `getEndTime()` cung cấp thời gian bắt đầu/kết thúc ở metadata:

```java
import java.time.Duration;

StepExecution step = ...;
if (step.getStartTime() != null &&
    step.getEndTime() != null) {
    Duration duration =
        Duration.between(step.getStartTime(), step.getEndTime());

    System.out.println("Step elapsed = "
        + duration.toMillis() + " ms");
}
```

Phép tính này hữu ích cho lịch sử job và kiểm tra SLA. Khi đo latency nhỏ trong tiến trình Java, dùng **`System.nanoTime()`** hoặc Micrometer `Timer` vì đây là nguồn đo thời gian trôi qua có tính monotonic, phù hợp hơn `System.currentTimeMillis()` hay việc trừ wall-clock ở độ phân giải thấp.

Spring Batch 5.x có khả năng tích hợp Micrometer/observability tùy cấu hình. Tên metric built-in, tag và độ bao phủ stage có thể khác giữa minor version; hãy kiểm tra metrics thực tế của ứng dụng rồi bổ sung custom timer cho yêu cầu chưa được đáp ứng, tránh phát ra nhiều timer trùng nội dung.

---

## 5. Đo latency bằng Micrometer `Timer`

### 5.1. Dependency và registry

Trong Spring Boot 3.x, thường bổ sung Actuator để quản lý Micrometer registry:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Dùng khi export Prometheus qua Actuator:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Spring Boot tạo `MeterRegistry` theo cấu hình dependency/observability. Trong unit test có thể dùng `SimpleMeterRegistry` mà không cần chạy Prometheus.

### 5.2. Timer dùng trong ứng dụng

Một utility trung tâm giúp đo thời gian của các delegate:

```java
package example.batch.metrics;

import java.util.concurrent.Callable;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class BatchStageTimer {

    private final MeterRegistry registry;

    public BatchStageTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T measure(
            String stage,
            Callable<T> operation) throws Exception {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return operation.call();
        } catch (Exception exception) {
            outcome = "error";
            throw exception;
        } finally {
            sample.stop(registry.timer(
                "app.batch.stage.latency",
                "stage", stage,
                "outcome", outcome));
        }
    }
}
```

Cách dùng:

```java
InputRow item = timer.measure("reader", delegate::read);

OutputRow output = timer.measure(
    "processor",
    () -> delegate.process(item));

timer.measure("writer", () -> {
    delegate.write(chunk);
    return null;
});
```

**Giá trị đo:** mỗi `Timer` lưu count và tổng thời gian; histogram/percentile tùy cấu hình. `stage` nên thuộc tập nhãn giới hạn: `reader`, `processor`, `writer`. `outcome` chỉ gồm `success` và `error` trong ví dụ.

Một lần `read()` trả `null` (EOF) hoặc `process()` trả `null` (lọc item) vẫn là **lời gọi thành công** ở timer này. Nếu muốn phân biệt EOF/filtered, có thể thêm bộ counter giới hạn nhãn riêng; đừng gọi đó là exception.

**Độ chính xác:** bắt đầu sample ngay trước lời gọi delegate và kết thúc trong `finally` để cả lời gọi ném exception cũng được ghi nhận. Ngoại lệ nghiêm trọng kiểu `Error` không được phân nhóm lỗi bởi `catch (Exception)` ở ví dụ, dù `finally` vẫn chạy; nếu có yêu cầu quan sát JVM fatal errors, cần thiết kế thêm cơ chế phù hợp.

### 5.3. Vì sao không dùng `StopWatch` chung không đồng bộ?

Nếu bạn tạo một `StopWatch` hoặc một biến `startTime` dùng chung cho toàn bộ reader/processor/writer, nhiều thread hoặc nhiều step song song sẽ ghi đè mốc đo của nhau.

Micrometer `Timer.Sample` được tạo **mới cho mỗi lời gọi** nên an toàn hơn để tách thời gian từng invocation. Timer/registry được chia sẻ cho nhiều thread và lưu aggregate. Việc đo tất cả item cũng có chi phí CPU/allocations; với step có hàng chục triệu lời gọi siêu ngắn, cần kiểm tra overhead đo và cân nhắc sampling, aggregate theo chunk hoặc dùng profiler phù hợp.

---

## 6. Decorator cho `ItemReader`: đo nhưng giữ checkpoint

### 6.1. Vì sao không đơn giản thay reader bằng lambda?

Reader có trạng thái thường implement `ItemStream` để framework gọi `open`, `update` và `close`. Nếu dùng wrapper chỉ implement `ItemReader` mà không chuyển tiếp `ItemStream`, bạn có thể vô tình làm mất logic checkpoint/restart của delegate.

Một decorator đo latency nên:

1. Đo quanh `read()`.
2. Trả về nguyên item/`null` và giữ nguyên exception.
3. Delegate các lifecycle callback của `ItemStream`.
4. Được đăng ký đúng vào step.

Ví dụ:

```java
package example.batch.metrics;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemStream;
import org.springframework.batch.item.ItemStreamReader;

public final class TimedReader<T> implements ItemStreamReader<T> {

    private final ItemReader<T> delegate;
    private final BatchStageTimer timer;

    public TimedReader(
            ItemReader<T> delegate,
            BatchStageTimer timer) {
        this.delegate = delegate;
        this.timer = timer;
    }

    @Override
    public T read() throws Exception {
        return timer.measure("reader", delegate::read);
    }

    @Override
    public void open(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.open(context);
        }
    }

    @Override
    public void update(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.update(context);
        }
    }

    @Override
    public void close() {
        if (delegate instanceof ItemStream stream) {
            stream.close();
        }
    }
}
```

Do wrapper implement `ItemStreamReader`, step có thể quản lý lifecycle trên wrapper. Khi delegate cũng implement `ItemStream`, callback được chuyển tiếp đến delegate. Không đăng ký cả wrapper và delegate làm stream riêng biệt nếu điều đó khiến `open/update/close` bị gọi hai lần.

### 6.2. Hiểu latency của reader có buffering

Một `JdbcCursorItemReader` hoặc reader có page/fetch buffer có thể đọc dữ liệu theo nhóm từ JDBC nhưng trả về từng item:

```text
read #1  -> lấy 200 row từ JDBC rồi trả item đầu -> 120 ms
read #2  -> lấy từ buffer                     -> 0,05 ms
read #3  -> lấy từ buffer                     -> 0,04 ms
...
read #201 -> fetch nhóm tiếp theo             -> 115 ms
```

Đây không nhất thiết là lỗi: reader call latency có phân phối nhiều đỉnh do fetch theo nhóm. Cần xem **tổng thời gian đọc, số query, fetch/page size, network round-trip, p95/p99** thay vì mặc định mỗi lời gọi phải có thời gian như nhau.

---

## 7. Decorator cho `ItemProcessor`: đo cả item bị filter

Processor có thể transform một item hoặc trả `null` để Spring Batch bỏ qua item đó. Cả hai đều tiêu tốn thời gian và nên được tính trong stage latency.

```java
package example.batch.metrics;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemStream;

public final class TimedProcessor<I, O>
        implements ItemProcessor<I, O>, ItemStream {

    private final ItemProcessor<I, O> delegate;
    private final BatchStageTimer timer;

    public TimedProcessor(
            ItemProcessor<I, O> delegate,
            BatchStageTimer timer) {
        this.delegate = delegate;
        this.timer = timer;
    }

    @Override
    public O process(I item) throws Exception {
        return timer.measure(
            "processor",
            () -> delegate.process(item));
    }

    @Override
    public void open(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.open(context);
        }
    }

    @Override
    public void update(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.update(context);
        }
    }

    @Override
    public void close() {
        if (delegate instanceof ItemStream stream) {
            stream.close();
        }
    }
}
```

Ở đây wrapper cố ý implement `ItemStream` để chuyển tiếp callback nếu processor thực tế có state. Khi cấu hình step, **đăng ký wrapper bằng `.stream(timedProcessor)`** nếu muốn Spring Batch gọi các lifecycle callback của processor; việc processor tự implement `ItemStream` không nên được coi là bằng chứng nó đã được đăng ký đúng trong mọi kiểu builder.

Cách đo này bao gồm thời gian kiểm tra hợp lệ, mapping, gọi service hoặc truy vấn do processor trực tiếp thực hiện. Nếu processor trả `null`, timer vẫn ghi outcome `success`; dùng `StepExecution.getFilterCount()` hoặc counter riêng để theo dõi số item bị lọc.

### 7.1. Phân biệt processor chậm do CPU và do I/O

Hai processor cùng có mean 4 ms có thể rất khác:

- Processor A parse/serialize JSON, tính toán hàm thuần: chủ yếu dùng CPU và heap.
- Processor B gọi HTTP để lấy tỷ giá cho từng item: chủ yếu chờ network, thường kèm tail latency và rate-limit.

Với A: dùng CPU profiler, allocation profiler, tối ưu biểu thức, cache dữ liệu bất biến hoặc xử lý theo nhóm.

Với B: tránh network call cho từng item khi có thể, preload/batch lookup, cache có TTL rõ ràng, giới hạn concurrency và timeout/retry. Tăng thread không có kiểm soát có thể đẩy vấn đề sang API downstream.

---

## 8. Decorator cho `ItemWriter`: đo theo chunk

Ở Spring Batch 5.x, `ItemWriter.write` nhận `Chunk<? extends T>`. Một lần gọi có thể chứa hàng chục, hàng trăm hoặc hàng nghìn output items. Phép đo phải ghi rõ đơn vị **call/chunk**.

```java
package example.batch.metrics;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStream;
import org.springframework.batch.item.ItemStreamWriter;
import org.springframework.batch.item.ItemWriter;

public final class TimedWriter<T> implements ItemStreamWriter<T> {

    private final ItemWriter<T> delegate;
    private final BatchStageTimer timer;

    public TimedWriter(
            ItemWriter<T> delegate,
            BatchStageTimer timer) {
        this.delegate = delegate;
        this.timer = timer;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        timer.measure("writer", () -> {
            delegate.write(chunk);
            return null;
        });
    }

    @Override
    public void open(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.open(context);
        }
    }

    @Override
    public void update(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.update(context);
        }
    }

    @Override
    public void close() {
        if (delegate instanceof ItemStream stream) {
            stream.close();
        }
    }
}
```

Một `write()` có thể kết thúc trước khi Spring Batch thực hiện transaction commit. Vì vậy, nếu writer timer thấp nhưng step vẫn chậm, hãy xem JDBC transaction metrics, database commit, WAL/fsync, connection pool và checkpoint update.

### 8.1. Đo cả số item mỗi chunk

Nếu cần, thêm `DistributionSummary` để quan sát phân phối kích thước chunk được writer nhận:

```java
DistributionSummary chunkItems =
    DistributionSummary.builder("app.batch.writer.chunk.items")
        .baseUnit("items")
        .register(registry);

chunkItems.record(chunk.size());
```

Với Micrometer, `chunk.size()` đếm **output items trong writer call**, có thể thấp hơn chunk size đã cấu hình nếu processor filter hoặc input đến EOF. Nó cũng không nhất thiết bằng số dòng database thực sự affected bởi SQL khi dùng upsert/constraint.

Khi so sánh writer latency qua các lần deploy, cần biết chunk size thực tế có thay đổi không. Writer 60 ms/chunk với 1.000 item có thể tốt hơn writer 20 ms/chunk với 10 item về throughput.

---

## 9. Tích hợp ba decorator vào `StepBuilder`

Giả sử ứng dụng đã có các thành phần nghiệp vụ `ItemReader<InputRow>`, `ItemProcessor<InputRow,OutputRow>` và `ItemWriter<OutputRow>`; class `InputRow`/`OutputRow` là model do ứng dụng định nghĩa.

Cấu hình một chunk step Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRow> businessReader,
        ItemProcessor<InputRow, OutputRow> businessProcessor,
        ItemWriter<OutputRow> businessWriter,
        BatchStageTimer stageTimer) {

    TimedReader<InputRow> timedReader =
        new TimedReader<>(businessReader, stageTimer);

    TimedProcessor<InputRow, OutputRow> timedProcessor =
        new TimedProcessor<>(businessProcessor, stageTimer);

    TimedWriter<OutputRow> timedWriter =
        new TimedWriter<>(businessWriter, stageTimer);

    return new StepBuilder("importStep", jobRepository)
        .<InputRow, OutputRow>chunk(100, transactionManager)
        .reader(timedReader)
        .processor(timedProcessor)
        .writer(timedWriter)
        .stream(timedProcessor)
        .build();
}
```

Điểm cần hiểu:

- Reader/writer wrapper implement `ItemStreamReader`/`ItemStreamWriter`, nên có thể được framework đăng ký lifecycle tương ứng.
- Processor wrapper được đăng ký rõ ràng bằng `.stream(timedProcessor)` để hỗ trợ delegate có `ItemStream`.
- `chunk(100, transactionManager)` đặt commit interval 100 cho ví dụ; không mặc định 100 luôn tốt.
- Các timer đo lời gọi delegate, không thay đổi giá trị trả về, exception hoặc nội dung `ExecutionContext`.
- Nếu component gốc sử dụng `@StepScope`, hãy bảo đảm bean proxy/delegate được resolve đúng trong execution scope. Không khởi tạo tùy tiện một `@StepScope` component bên ngoài scope đang hoạt động.
- Nếu một delegate vốn được đăng ký `.stream(delegate)` ở nơi khác, tránh đăng ký hai lần gây callback lặp.

Ví dụ thực tế có thể cần `@Qualifier` hoặc bean name để phân biệt raw reader và timed reader trong application context. Tên import/step và metric nên ổn định theo phiên bản triển khai để so sánh lịch sử.

---

## 10. Quan sát metric qua Actuator

### 10.1. Cấu hình YAML

Nếu muốn expose metrics và Prometheus cho môi trường quan sát đã được bảo vệ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus

  metrics:
    distribution:
      percentiles-histogram:
        app.batch.stage.latency: true
      slo:
        app.batch.stage.latency: 10ms,50ms,100ms,500ms,1s
```

Cấu hình SLO buckets/histogram làm tăng số chuỗi time series; cần cân nhắc backend monitoring. Nếu ứng dụng không có Prometheus registry dependency, endpoint `prometheus` có thể không xuất hiện như mong đợi.

Trong môi trường vận hành, chỉ expose Actuator endpoints theo chính sách authentication/network phù hợp. Không phát hành dữ liệu nhạy cảm qua meter tags.

### 10.2. Đọc count và mean

Trong test hoặc service:

```java
Timer readerSuccess = registry.get("app.batch.stage.latency")
    .tag("stage", "reader")
    .tag("outcome", "success")
    .timer();

long calls = readerSuccess.count();
double totalSeconds =
    readerSuccess.totalTime(java.util.concurrent.TimeUnit.SECONDS);

double meanMs =
    calls == 0 ? 0.0
        : readerSuccess.mean(java.util.concurrent.TimeUnit.MILLISECONDS);
```

Đây là mean của các lời gọi **thành công**. Nên đọc riêng outcome `error`; số lần retry có thể làm số call error tăng đáng kể.

Ví dụ metric ở Prometheus có thể được chuyển tên từ dấu chấm sang dấu gạch dưới và biểu diễn thành series `_seconds_count`, `_seconds_sum` và histogram `_bucket` theo convention của registry. Không giả định tên metric Prometheus trùng nguyên chuỗi Java; hãy xem output thực tế của endpoint trước khi viết dashboard/query.

### 10.3. p95 và p99 đọc như thế nào?

- **p50**: một nửa số call không vượt mức này.
- **p95**: 95% số call không vượt mức này; nhấn mạnh 5% call chậm nhất.
- **p99**: giúp quan sát tail latency của lời gọi hiếm gặp.
- **mean**: phản ánh mức tiêu thụ thời gian trung bình nhưng có thể che đỉnh.
- **max**: hữu ích khi điều tra sự cố ngắn, nhưng dễ biến động và phụ thuộc cửa sổ đo.

Với histogram Prometheus, có thể tính quantile theo rate trong khoảng thời gian. Đơn vị phải đồng nhất và nhãn lọc phải tương ứng stage/job phù hợp; không lấy p95 của reader cộng p95 processor và writer làm p95 toàn step.

### 10.4. Tag nào nên dùng?

| Tag | Gợi ý | Vì sao |
| --- | --- | --- |
| `stage` | `reader` / `processor` / `writer` | Cardinality cực thấp |
| `job.name` | Danh sách tên job hữu hạn | So sánh workload khác nhau |
| `step.name` | Danh sách step hữu hạn | Xác định bottleneck theo step |
| `outcome` | `success` / `error` | Phân loại lỗi |
| `environment` | `test` / `staging` / `prod` | Phân biệt nơi chạy khi cần |
| `jobExecutionId` | **Tránh làm meter tag** | Mỗi execution tạo series mới |
| `customerId`/`orderId` | **Tránh** | Cardinality lớn và có thể nhạy cảm |
| `inputFilePath` | **Tránh** | Đường dẫn biến động, có thể lộ thông tin |

Nếu chỉ có một `BatchStageTimer` dùng chung registry như ví dụ, cần cân nhắc thêm job/step tag **ổn định và được cấu hình từ bean/wrapper**, không tự thêm một trường ID duy nhất cho mỗi item hoặc execution.

---

## 11. Đọc số liệu theo tổng thời gian và độ phân phối

Ví dụ dashboard cho một step đã chạy:

| Chỉ số | Reader | Processor | Writer |
| --- | ---: | ---: | ---: |
| Successful calls | 100.001 | 100.000 | 1.000 |
| Mean per call | 2 ms | 0,2 ms | 18 ms |
| p95 per call | 7 ms | 0,5 ms | 45 ms |
| Total duration các call thành công | ~200 s | ~20 s | ~18 s |
| Error calls | 35 | 0 | 4 |

Đây là dữ liệu **minh họa**. Dù writer p95 45 ms lớn hơn reader p95 7 ms, reader tổng cộng ~200 giây, nên có thể là giới hạn throughput chính.

Tuy nhiên cần điều tra 35 read errors: retry có thể tạo nhiều lời gọi bổ sung. Nếu retry policy phải backoff, thời gian ngủ giữa các attempt không nằm trong timer của chính `read()` và có thể là phần lớn step duration.

### 11.1. Tại sao tổng timer có thể khác wall time?

- Transaction commit, rollback, checkpoint và metadata update không nằm trong ba timer.
- Step startup/teardown, reader `open/close`, writer flush khi `close` có thời gian riêng.
- Retry backoff, thread-pool queue, throttle hoặc lock acquisition có thể nằm ngoài wrapper.
- Một client library có asynchronous work, timer quanh method có thể đo **thời gian gửi yêu cầu** thay vì thời gian remote hoàn tất.
- Với multi-threaded step, tổng thời gian các call song song có thể **lớn hơn wall time**.
- Reader có prefetch/background fetch, nên một số I/O xảy ra ngoài lời gọi `read()`.
- GC hoặc CPU scheduling có thể gián đoạn bất kỳ stage nào.

Đừng coi chênh lệch giữa tổng ba timer và step wall time là “thời gian bị mất” mà chưa biết pipeline đang đồng bộ hay đồng thời.

### 11.2. Đo waiting time

Nếu reader chờ JDBC connection, timer quanh `read()` sẽ có thể bao gồm connection acquisition. Để xác định lý do cụ thể, cần bổ sung metrics từ connection pool như HikariCP, JDBC spans, database slow query logs hoặc thread dumps. Tương tự, processor gọi HTTP nên quan sát HTTP client metrics, timeout, retry và downstream latency.

**Stage timer cho biết nơi biểu hiện chậm; component-specific metric/profiler cho biết vì sao chậm.**

---

## 12. Tối ưu reader latency

### 12.1. Reader đọc SQL

Những vấn đề thường gặp:

- Query không dùng index cho điều kiện lọc/ORDER BY.
- Truy vấn trả quá nhiều cột hoặc quá nhiều row cho một lần xử lý.
- N+1 lookup do reader/processor gọi SQL thêm cho từng item.
- `fetchSize` hoặc `pageSize` chưa phù hợp.
- Paging query dùng thứ tự không ổn định, dẫn đến thiếu/trùng item khi dữ liệu nguồn thay đổi.
- Database lock, network round-trip hoặc connection pool nghẽn.
- Map row phức tạp, deserialize dữ liệu lớn.

Hướng xử lý:

1. Xem query plan/`EXPLAIN` và slow query log bằng dữ liệu gần production.
2. Chọn index phù hợp với WHERE/ORDER BY; tránh `SELECT *` nếu không cần.
3. Đo thời gian fetch, số rows/query, số connection đang chờ.
4. Thử `fetchSize`/`pageSize` theo từng mức có kiểm soát.
5. Với paging, dùng sort key duy nhất/ổn định và xử lý thay đổi dữ liệu đầu vào theo yêu cầu nhất quán.
6. Nếu data source hỗ trợ, cân nhắc partitioning theo key range thay vì một reader nghẽn.

`chunk size`, `fetch size` và `page size` là **ba tham số khác nhau**. `chunk size` quyết định ranh giới transaction/writer; fetch/page size là hành vi lấy dữ liệu của reader. Không mặc định tăng chunk size sẽ giảm số query của reader.

### 12.2. Reader từ file

Với file CSV/JSON/XML lớn, latency có thể đến từ:

- Ổ đĩa hoặc object storage có I/O throughput thấp.
- Giải nén và parse từng dòng.
- Encoding, line tokenizer hoặc mapping/validation quá phức tạp.
- Đọc file qua network share có tail latency.
- Nhiều file nhỏ tạo overhead mở/đóng lặp lại.

Có thể đo riêng thời gian mở resource, parse, read buffer và network download. Buffering hợp lý giúp giảm syscall nhưng tăng bộ nhớ; kiểm tra cả heap usage và GC.

### 12.3. Chú ý các reader có state

Đổi reader hoặc wrapper để tối ưu phải giữ `ItemStream.open/update/close` và key trong `ExecutionContext`. Một reader nhanh hơn nhưng mất checkpoint có thể làm hàng triệu bản ghi bị xử lý lại sau failure. Performance và restart correctness cần được xem đồng thời.

---

## 13. Tối ưu processor latency

### 13.1. CPU-bound processor

Ví dụ processor tính hash, parse JSON, áp dụng rule engine và tạo object mới. Khi CPU là giới hạn:

- Dùng CPU profiler để định vị hotspot trong parse/map/validation.
- Tránh deserialize lại cùng dữ liệu hoặc compile regex trên mỗi item.
- Cache cấu hình/rule bất biến theo job/step nếu đúng semantics.
- Giảm allocation không cần thiết, nhất là object tạm lớn và string conversions.
- Xem GC pause, heap pressure và CPU saturation.
- Đánh giá vectorization hoặc xử lý theo nhóm nếu thuật toán cho phép.

**Không kết luận tăng số thread luôn cải thiện throughput**: nếu CPU đã bão hòa, thêm thread có thể làm tăng context switching và độ trễ.

### 13.2. I/O-bound processor

Một processor gọi HTTP/Redis/SQL cho mỗi item thường có tail latency lớn. Hãy kiểm tra:

- Số request/item; có thể thay bằng batch API không?
- Timeout và retry: có đang retry một request chậm quá nhiều lần?
- Connection pooling, rate limit, circuit breaker.
- Cache có hạn sử dụng, eviction policy và consistency.
- Có thể preload lookup table nhỏ trước step không?
- Downstream có hỗ trợ idempotency key và backpressure không?

Nếu sử dụng async processing, `ItemProcessor` có thể thực thi ngoài thread Step chính; cần đo method thực thi công việc, không chỉ đo thời gian enqueue một future. Với `AsyncItemProcessor`/`AsyncItemWriter`, gọi `process()` thường trả về future nhanh nhưng thực hiện transform ở thread khác; stage timer bao quanh lời gọi submit sẽ **không phản ánh độ trễ xử lý thật** nếu không bám theo quá trình thực thi/hoàn tất future.

### 13.3. Processor trả `null`

`null` là cơ chế filter item hợp lệ. Nếu 80% input bị loại, writer nhận ít output hơn reader/process. So sánh `readCount` với `writeCount` phải tính `filterCount`, skip và rollback, tránh coi đây là “throughput writer thấp bất thường”.

---

## 14. Tối ưu writer latency

### 14.1. JDBC writer

Các nguyên nhân phổ biến:

- SQL từng row thay vì batch update.
- Network round-trip cho từng item.
- Index/foreign key/constraint trigger làm write nặng.
- Lock contention, deadlock, transaction duration dài.
- Commit/fsync/WAL bottleneck.
- Unique key/upsert gây tranh chấp giữa các job.
- Connection pool nhỏ hoặc chờ acquire connection.

Đối với JDBC, có thể dùng `JdbcBatchItemWriter` hoặc batching phù hợp. Tuy nhiên, tăng chunk size từ 100 lên 10.000 không bảo đảm tối ưu: query lớn, memory pressure, lock duration và rollback cost có thể tăng.

### 14.2. File writer

Những yếu tố thường ảnh hưởng:

- Encoding và serialization.
- Buffer size và flush frequency.
- Nén dữ liệu theo block.
- File system/network file system.
- Atomic rename/fsync và độ bền dữ liệu cần thiết.

Một writer ghi file có thể trả về nhanh vì OS buffering, trong khi thực sự flush xuống disk ở checkpoint hoặc close. Đo method `write()` nên kết hợp đo flush/close và end-to-end time để hiểu độ bền dữ liệu.

### 14.3. Writer gọi API

Nếu ghi lên service bên ngoài, cần tính batch API size, timeout, rate limit, idempotency và retry. Một writer gửi 1.000 item trong một request có thể tiết kiệm network round-trip nhưng cũng tăng payload size, timeout hoặc kích thước partial-failure.

Đặc biệt, Spring Batch transaction của JobRepository không tự làm cho remote API nằm trong cùng transaction. Khi restart, chunk có thể xử lý lại, nên output cần dedup/idempotency theo business key.

---

## 15. Điều chỉnh chunk size theo số liệu

`chunk(size)` quyết định số input item tối đa trong một chunk transaction theo cách xử lý mặc định. Sau một chu kỳ read/process, writer được gọi với một chunk output và framework thực hiện checkpoint/commit.

| Chunk size | Lợi ích có thể đạt | Chi phí/rủi ro |
| --- | --- | --- |
| 10 | Transaction ngắn, rollback ít item, low memory | Nhiều write/commit calls, overhead cao |
| 100 | Mức trung bình thường dùng làm baseline | Có thể chưa tối ưu với workload thực |
| 1.000 | Ít commit và write calls hơn | Tăng heap, lock duration, rollback cost |
| 10.000 | Có thể giảm overhead với writer batch hiệu quả | Transaction lớn, dài, rủi ro timeout và áp lực bộ nhớ |

Các mức là **candidate để benchmark**, không phải khuyến nghị cố định.

### 15.1. Ví dụ ảnh hưởng của fixed overhead

Giả sử writer có overhead cố định 15 ms/chunk và thêm 0,05 ms/item:

\[
T_{\mathrm{writer}}(c) \approx 15 + 0{,}05c\ \mathrm{ms}
\]

Khi chunk có 10 item, writer mất khoảng 15,5 ms/chunk, tức khoảng 1,55 ms/item. Với 100 item, mất 20 ms/chunk, tương đương 0,20 ms/item. Với 1.000 item, mất 65 ms/chunk, tương đương 0,065 ms/item.

Mô hình chỉ là giả định để hiểu **amortize fixed overhead**. Trong thực tế, SQL batch size, network, database limits, transaction log và memory khiến chi phí không tăng tuyến tính mãi mãi.

### 15.2. Tối ưu chunk size thế nào?

Một quy trình thực nghiệm:

1. Chạy baseline với dataset và môi trường cố định.
2. Chọn các mức 20, 100, 500, 1.000 hoặc mức phù hợp workload.
3. Mỗi mức đo total wall time, writer mean/p95, read/process mean/p95, commit duration, rollback, heap/GC và throughput.
4. Test failure giữa chunk để xác minh restart và idempotent writer.
5. Chọn mức đáp ứng SLA với biên độ tài nguyên và khả năng phục hồi chấp nhận được.

Đừng chọn chunk size chỉ dựa trên mean writer latency. Chunk size lớn đôi khi làm writer call chậm hơn nhưng tổng thời gian toàn step ngắn hơn; đôi khi chiều ngược lại xảy ra do lock contention.

---

## 16. Retry, skip và rollback làm méo latency ra sao?

### 16.1. Timer đếm lời gọi, counter đếm kết quả

Khi process một item bị lỗi rồi retry:

```text
process(item 42) attempt 1 -> error, 80 ms
retry backoff                    200 ms
process(item 42) attempt 2 -> error, 70 ms
retry backoff                    400 ms
process(item 42) attempt 3 -> success, 5 ms
```

Custom timer ở processor ghi **3 calls** với latency lần lượt 80, 70, 5 ms; khoảng backoff 600 ms có thể không nằm trong ba timer đó. Nhưng `StepExecution` có thể cuối cùng chỉ ghi một output item thành công.

Vì vậy, khi latency tăng cần xem đồng thời:

- `success/error` timer count cho từng stage.
- Retry count, backoff duration và exception type (tag loại lỗi chỉ khi cardinality kiểm soát được).
- `readSkipCount`, `processSkipCount`, `writeSkipCount`.
- `rollbackCount` và `commitCount`.
- End-to-end duration và số output item thực sự ghi thành công.

### 16.2. Rollback khiến công việc lặp lại

Một chunk đã đọc/process có thể cần xử lý lại sau rollback, tùy reader, transaction và retry policy. Tổng số method invocations có thể lớn hơn `readCount`, `writeCount` hoặc số unique business records. Khi báo cáo throughput, cần xác định mẫu số là **attempts** hay **unique completed records**.

### 16.3. Khi nào timeout quan trọng hơn mean?

Nếu một API downstream thường trả trong 5 ms nhưng 1% request mất 30 giây, mean có thể trông chấp nhận được trong một vài đợt test nhỏ. Với batch xử lý hàng triệu item, các outlier lặp lại rất nhiều và có thể phá SLA. p95/p99, timeout, error rate và retry policy thường quan trọng hơn tối ưu một phép toán Java từ 1 ms xuống 0,8 ms.

---

## 17. Parallelism và giới hạn phép cộng latency

### 17.1. Step đơn luồng

Trong chunk step đơn luồng, reader/process/write phần lớn nối tiếp nhau. Tổng thời gian gọi stage có thể dùng để phân tích sơ bộ bottleneck và overhead ngoài stage, với các hạn chế đã nêu.

### 17.2. Multi-threaded step

Spring Batch có thể dùng `TaskExecutor` cho step để xử lý các chunk đồng thời (tùy cơ chế builder/phiên bản). Khi đó:

- Nhiều chunk cùng đọc, process hoặc write.
- Tổng thời gian Timer across threads có thể **lớn hơn step wall time**.
- Reader/writer dùng state chia sẻ có thể không thread-safe.
- Thứ tự item và checkpoint có thể khó đảm bảo như single-threaded processing.
- Database contention và connection pool wait có thể trở thành bottleneck mới.

Không giả định mọi `ItemReader` đều an toàn khi đa luồng. Có các wrapper đồng bộ như `SynchronizedItemStreamReader` cho một số trường hợp, nhưng đồng bộ hóa reader cũng có thể gây nghẽn và ảnh hưởng tới đặc tính restart/order khi nhiều chunk xử lý song song. Cần kiểm tra đúng loại reader và semantics yêu cầu.

### 17.3. Partitioning và remote chunking

Khi một step được partition theo vùng key hoặc file, có nhiều `StepExecution` độc lập. Để so sánh latency:

- Dùng tag stage/job/step có cardinality hữu hạn.
- Quan sát độ lệch giữa partition nhanh/chậm.
- Xem skew dữ liệu, partition size và database access pattern.
- Không chỉ lấy average của mọi partition nếu một partition cuối kéo dài toàn job.

Trong remote chunking, mạng, serialization, message broker, queue time và worker backlog có thể chiếm phần lớn wall time; timer quanh local reader/processor/writer không bao hết.

### 17.4. Công thức throughput khi có concurrency

Nếu công việc CPU-bound và có đủ core, concurrency có thể tăng số item/s cho đến khi CPU bão hòa. Nếu I/O-bound, tăng đồng thời có thể giúp che latency chờ nhưng chỉ đến giới hạn của downstream connection, rate limit, DB locks và memory.

**Throughput không luôn tỉ lệ nghịch với latency một call** khi có nhiều request đồng thời. Muốn tối ưu cần đo cả concurrency đang hoạt động, throughput toàn job và giới hạn tài nguyên.

---

## 18. Thiết kế benchmark để có kết luận đáng tin

### 18.1. Dữ liệu và môi trường cần kiểm soát

Một benchmark Spring Batch có ý nghĩa nên ghi lại:

- Số lượng input items và kích thước bản ghi.
- Tỷ lệ filtered/skipped/retried.
- Phiên bản Java/JVM, Spring Batch, Spring Boot, JDBC driver.
- Chunk size, reader fetch/page size, DB pool size, thread count.
- Dữ liệu source và index/schema tại thời điểm đo.
- Số CPU, RAM, GC, disk/network và load đồng thời.
- Cấu hình logging/tracing/metrics.
- Thời gian warm-up, cache cold/warm, kết quả của nhiều lần chạy.

Nếu lần A đọc 100.000 item đã nằm trong cache nhưng lần B đọc 500.000 item từ database lạnh, so sánh mean reader latency giữa A/B không chứng minh code B kém hơn.

### 18.2. Baseline và thay đổi từng biến

Thực nghiệm tốt thường gồm:

1. Cố định dữ liệu và cấu hình.
2. Đo baseline có thông tin đủ về latency/call counts/throughput.
3. Chọn bottleneck lớn nhất.
4. Đổi **một tham số có chủ đích** (ví dụ fetch size hoặc JDBC batching).
5. Chạy lại nhiều lần; so sánh median, tail latency và total duration.
6. Kiểm tra kết quả nghiệp vụ, memory và restart correctness.
7. Chỉ sau khi có kết quả đáng tin mới thay đổi tham số khác.

Nếu đổi cùng lúc chunk size, thread count, query, cache và timeout, khó biết thay đổi nào mang lại lợi ích hoặc làm phát sinh lỗi.

### 18.3. Tránh microbenchmark sai ngữ cảnh

Một processor đơn giản chạy trong JUnit loop không đại diện cho Batch step chạy thật với database, transaction và GC. Nếu muốn benchmark micro-level Java code, cân nhắc **JMH** để có warm-up và đo phù hợp JIT. Nếu mục tiêu là SLA 20 phút của toàn job, cần integration/performance test trên workload đại diện.

### 18.4. Nơi chọn threshold

Không đặt một assertion JUnit kiểu “reader luôn dưới 2 ms” trong CI chia sẻ tài nguyên rồi coi nó là kiểm thử chức năng. Latency tuyệt đối chịu ảnh hưởng nhiều từ VM, tải CI, database và network.

Có thể dùng performance regression test chuyên biệt với môi trường được kiểm soát và threshold thống kê phù hợp, tách khỏi unit test xác minh logic instrument.

---

## 19. Kiểm thử cơ chế đo latency

### 19.1. Unit test Timer không cần ngủ chờ

Thử utility `BatchStageTimer` với `SimpleMeterRegistry`:

```java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BatchStageTimerTest {

    @Test
    void recordsSuccessfulProcessorCall() throws Exception {
        try (SimpleMeterRegistry registry =
                new SimpleMeterRegistry()) {

            BatchStageTimer timer = new BatchStageTimer(registry);

            String result = timer.measure(
                "processor",
                () -> "normalized");

            assertEquals("normalized", result);

            Timer sample = registry.get("app.batch.stage.latency")
                .tag("stage", "processor")
                .tag("outcome", "success")
                .timer();

            assertEquals(1L, sample.count());
            assertTrue(sample.totalTime(
                java.util.concurrent.TimeUnit.NANOSECONDS) >= 0);
        }
    }

    @Test
    void recordsFailureAndPropagatesException() {
        try (SimpleMeterRegistry registry =
                new SimpleMeterRegistry()) {

            BatchStageTimer timer = new BatchStageTimer(registry);

            IllegalStateException thrown = assertThrows(
                IllegalStateException.class,
                () -> timer.measure("writer", () -> {
                    throw new IllegalStateException("database down");
                }));

            assertEquals("database down", thrown.getMessage());

            Timer failures = registry.get("app.batch.stage.latency")
                .tag("stage", "writer")
                .tag("outcome", "error")
                .timer();

            assertEquals(1L, failures.count());
        }
    }
}
```

Test này kiểm tra instrument không làm thay đổi kết quả, exception vẫn đi ra và timer ghi call. Không dùng `Thread.sleep` rồi assert chính xác số milliseconds, vì thời gian trên máy CI biến động.

### 19.2. Integration test quanh Spring Batch step

Với một fixture có 5 input items, processor luôn trả output và chunk size 3, test có thể:

- Chạy job bằng `JobLauncherTestUtils.launchJob` trên repository test.
- Assert `BatchStatus.COMPLETED`.
- Assert `StepExecution.getReadCount() == 5` và `getWriteCount() == 5`.
- Đọc `MeterRegistry` và kiểm tra có timer cho reader/processor/writer.
- Kiểm tra các successful call counts phù hợp với fixture, có tính đến lời gọi `read()` nhận EOF.
- Đọc output thực tế để chắc chắn decorator không làm sai kết quả.
- Nếu reader/writer có `ItemStream`, chạy test failure/restart để bảo đảm `open/update` được chuyển tiếp và checkpoint không bị mất.

Một integration test với DB thật còn giúp phát hiện nếu wrapper vô tình không được Spring Batch đăng ký lifecycle; unit test timer thuần Java không thể bắt lỗi wiring này.

### 19.3. Xác minh overhead của instrument

Với processor chỉ tốn vài microseconds, ghi một metric cho mỗi item có thể trở thành phần đáng kể của tổng thời gian. So sánh throughput cùng workload khi bật/tắt custom metrics hoặc đo sampling tỷ lệ cố định; tránh gắn tag động cho từng record. Với task rất nóng, có thể đo một nhóm item/chunk rồi báo cáo mean thay vì tạo timer sample cho mọi call, nhưng cần ghi rõ sampling policy.

---

## 20. Các dấu hiệu bottleneck thường gặp

| Quan sát | Khả năng | Việc cần kiểm tra |
| --- | --- | --- |
| Reader p95 rất cao theo đợt | Fetch/page/database query hoặc network | Query plan, fetch size, connection pool |
| Reader mean thấp nhưng step lâu | Commit/metadata/retry/backoff/GC | Step wall time vs sum timer, DB transaction |
| Processor mean tăng khi dữ liệu lớn | CPU hoặc allocations | CPU/heap profiler, xử lý quy tắc |
| Processor p99 tăng theo traffic | HTTP/Redis/SQL downstream chờ | Client metrics, rate limit, N+1 |
| Writer call cao nhưng writer throughput tốt | Writer ghi chunk lớn | ms/chunk cùng items/chunk |
| Writer thấp nhưng commit chậm | WAL/fsync/locks | Transaction timing, DB logs |
| Khi tăng chunk size, tốc độ tăng rồi giảm | Overhead commit giảm nhưng lock/heap tăng | So sánh nhiều chunk sizes |
| Khi tăng thread, latency tăng và throughput không tăng | Resource saturation hoặc contention | CPU, pool, DB locks, queue depth |
| Sau lỗi, số processor calls tăng mạnh | Retry/rollback khiến item xử lý lặp | Retry count, exceptions, step counters |
| Mỗi job đều chậm lúc đầu | Cold start, JIT, cache, resource initialization | Warm-up, reader.open, connection setup |
| Tổng timer vượt step wall time | Parallel execution | Concurrency và aggregation |
| Có nhiều item đọc nhưng ít item ghi | Filter/skip hoặc logic writer | `filterCount`, skip counts, business output |

### 20.1. Một quy trình điều tra từng bước

Giả sử job xử lý 5 triệu item trong 90 phút:

1. Ghi **job/step wall time** và số unique completed items để biết throughput thực.
2. Đo hoặc kiểm tra stage timer của reader, processor và writer.
3. Với writer, luôn xem số items/chunk và số write calls.
4. Nếu stage time không giải thích được wall time, đo commit, backoff, queue, thread/connection pool.
5. Dùng CPU profiler cho CPU-bound, slow query log/JDBC spans cho DB-bound, network metrics cho I/O-bound.
6. Thay một cấu hình, chạy baseline tương đương và đối chiếu p95, throughput, memory, rollback.
7. Kiểm tra lại correctness: unique output, checkpoint và restart.

Một tối ưu giúp giảm latency nhưng làm dữ liệu trùng khi retry không phải cải tiến hợp lệ của batch processing.

---

## 21. Bài tập thực hành

### Bài 1 — Tính stage contribution

Một step có 20.000 input items, 10% bị filter, chunk size 200. Reader mean 0,8 ms/call; processor mean 2 ms/call; writer mean 30 ms/chunk; transaction overhead 5 ms/commit.

Yêu cầu: ước lượng read/process/write calls, tổng thời gian các stage và điểm đáng điều tra đầu tiên. Giải thích vì sao writer call count dựa trên **output item count** và phép ước lượng có thể sai khi retry/skip/EOF.

### Bài 2 — Instrument mà không mất restart

Viết `TimedReader<T>` bao quanh reader có `ItemStream`. Dùng một fixture reader khôi phục offset trong `open` và ghi `ExecutionContext` trong `update`.

Yêu cầu: đọc qua wrapper, lưu checkpoint, tạo wrapper/reader instance mới và assert reader khôi phục đúng offset. Đồng thời kiểm tra timer read success/error.

### Bài 3 — Phân biệt writer call và commit

Tạo `JdbcBatchItemWriter` với chunk size 20 và 200. Đo `write(chunk)` timer, step duration, database transaction timings và write throughput.

Yêu cầu: giải thích trường hợp writer timer giảm nhưng tổng step time không giảm vì commit hoặc lock.

### Bài 4 — Processor I/O-bound

Giả lập processor gọi service HTTP mất 50 ms mỗi item. Đo số request, p95, throughput và retry khi service trả 429.

Yêu cầu: đề xuất batch lookup/cache/timeout, kiểm tra idempotency và tác động của tăng concurrency lên downstream.

### Bài 5 — Benchmark theo workload

Chuẩn bị fixture 100.000 bản ghi. Thử chunk size 20, 100, 500; giữ nguyên dataset, fetch size, số thread và pool size.

Yêu cầu: lập bảng mean/p95 các stage, wall time, throughput, commit count, heap peak và rollback count. Lựa chọn một cấu hình dựa trên mục tiêu SLA và restart reliability.

### Bài 6 — Đo overhead custom metrics

Viết processor thuần Java xử lý một phép map rất nhanh, đo batch có và không có Micrometer timer cho mỗi item.

Yêu cầu: ghi rõ environment, nhiều lượt chạy và kết luận khi nào nên sampling/aggregate theo chunk.

---

## 22. Tổng kết về phương pháp đo

Khi phân tích hiệu năng của một Spring Batch step, hãy nhớ ba tầng số liệu:

1. **Stage call latency** cho reader, processor và writer: đo lời gọi delegate và phân phối thời gian. Reader/processor thường theo item, writer theo chunk.
2. **Batch execution metadata**: `readCount`, `writeCount`, `filterCount`, skips, rollback, commit và lifecycle status.
3. **End-to-end và infrastructure**: step wall time, throughput, transaction commit, database/network wait, CPU/GC và scheduler delays.

Chỉ tối ưu khi phép đo chỉ ra tác nhân chi phối thời gian. Reader chậm cần xem query/fetch, processor chậm cần phân biệt CPU và I/O, writer chậm cần xem batch size, transaction và hệ thống đích. Mọi thay đổi phải giữ nguyên contract nghiệp vụ, idempotency và khả năng restart.

## 23. Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html).
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html).
- [Spring Batch Reference — Scalability and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html).
- [Spring Batch Reference — ItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-reader.html).
- [Spring Batch Reference — ItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-writer.html).
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html).
- [Micrometer Documentation — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
