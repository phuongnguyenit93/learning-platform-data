# Giảm log trên job lớn trong Spring Batch

## 1. Vì sao một batch job lớn dễ tạo quá nhiều log?

Trong một ứng dụng Spring Batch, số lượng bản ghi cần xử lý có thể lên đến hàng triệu hoặc hàng chục triệu. Nếu `ItemReader`, `ItemProcessor` và `ItemWriter` đều ghi một dòng `INFO` cho mỗi item, lượng log sẽ tăng theo số bản ghi ngay cả khi job vận hành bình thường. Khi có retry, skip, rollback hoặc chạy song song, cùng một item còn có thể xuất hiện trong log nhiều lần.

Giả sử một job xử lý **10 triệu đơn hàng**:

| Chiến lược log | Số log xấp xỉ | Đặc điểm |
|---|---:|---|
| Một dòng cho mỗi item | 10.000.000 | Rất nhiều I/O và dữ liệu cần lưu trữ, khó tìm sự kiện quan trọng. |
| Một dòng cho mỗi chunk 1.000 item | 10.000 | Ít hơn nhưng có thể vẫn lớn với nhiều job chạy liên tục. |
| Một dòng mỗi 10.000 item được xử lý | Khoảng 1.000 | Phù hợp để theo dõi tiến độ ở tần suất thấp. |
| Log bắt đầu/kết thúc của từng step | Vài dòng mỗi step | Gọn, dễ tìm thông tin cuối cùng, nhưng không phản ánh tiến độ giữa chừng. |

Những chi phí chính của log quá nhiều không chỉ nằm ở dung lượng file. Mỗi lần log có thể kéo theo việc chuẩn bị tham số, format nội dung, tạo exception stack trace, đồng bộ hóa appender, ghi stdout, chuyển dữ liệu qua container runtime, gửi đến log collector, index và lưu trữ dài hạn.

Đối với một job lớn, mục tiêu là **giữ được thông tin để vận hành và điều tra lỗi** với số log vừa đủ. Ta cần có khả năng xác định *job nào đang chạy, tiến độ đến đâu, bao nhiêu item thành công/thất bại và lỗi cụ thể là gì* mà không biến log thành bản sao của toàn bộ dữ liệu xử lý.

```text
                  Batch job rất lớn
                          |
          +---------------+---------------+
          |               |               |
       Item/Chunk      Step/Job         Hạ tầng
          |               |               |
    Log chi tiết     Log bắt đầu,     Metrics / traces /
    khi cần debug    tiến độ, kết quả  JobRepository
          |               |               |
       Sampling      INFO/WARN/ERROR   Theo dõi liên tục
          +---------------+---------------+
                          |
               Có đủ dữ liệu chẩn đoán
               với khối lượng log thấp
```

## 2. Nhận diện nguồn log gây ồn

Trong Spring Batch, log có thể xuất phát từ code nghiệp vụ, framework và các thư viện phụ thuộc. Trước khi giảm log, cần biết nguồn tạo ra dòng log nào.

| Nguồn | Mẫu log thường gặp | Nguy cơ khi xử lý dữ liệu lớn |
|---|---|---|
| `ItemReader` | `Read item ID=...` ở mỗi lượt `read()` | Có thể tạo hàng triệu dòng log. |
| `ItemProcessor` | In input/output của từng lần `process()` | Vừa tốn chi phí, vừa có nguy cơ lộ dữ liệu. |
| `ItemWriter` | `Writing ...` cho từng item | Log lặp khi chunk rollback/retry. |
| `ItemReadListener`/`ItemProcessListener`/`ItemWriteListener` | Log trong `afterRead`, `afterProcess`, `afterWrite` | Được gọi rất thường xuyên trong chunk-oriented step. |
| `SkipListener` | Stack trace cho từng item bị skip | Nếu lỗi dữ liệu hàng loạt, log tăng đột biến. |
| `ChunkListener` | Log mỗi commit hoặc mỗi lần chunk lỗi | Có thể gây ồn khi chunk size nhỏ hoặc retry nhiều. |
| `StepExecutionListener` | Log lúc bắt đầu/kết thúc step | Thường ít log, thích hợp làm nơi ghi tổng kết. |
| `JobExecutionListener` | Log lúc bắt đầu/kết thúc job | Phù hợp ghi kết quả ở cấp job. |
| Spring Batch/JDBC/SQL logger | Chi tiết transaction, SQL, binding hoặc execution | `DEBUG`/`TRACE` có thể rất lớn. |
| HTTP client, Kafka, ORM hoặc thư viện ngoài | Request/response, truy vấn và exception | Có thể nhân số log theo số lần gọi bên ngoài. |

Hai tình huống cần phân biệt:

1. **Log quá nhiều vì ứng dụng chủ động ghi từng item**: giải quyết chủ yếu bằng cách đổi vị trí phát log, gom số liệu, lấy mẫu và giới hạn tần suất.
2. **Log quá nhiều vì framework/library đang ở `DEBUG` hoặc `TRACE`**: giải quyết trước tiên bằng cấu hình `logging.level`, sau đó mới xem các appender hoặc sampling.

Chỉ nâng level của logger framework sẽ không xử lý hết các dòng `INFO` do mã nghiệp vụ tự phát. Ngược lại, bỏ log trong processor nhưng để `org.springframework.jdbc` ở `TRACE` vẫn có thể tạo lượng output rất lớn.

## 3. Xác định mục tiêu observability trước khi tối ưu

Không phải dòng log nào cũng có giá trị như nhau. Một thiết kế cân bằng thường giữ các nhóm thông tin sau:

| Sự kiện | Tần suất gợi ý | Level gợi ý | Dữ liệu cần giữ |
|---|---|---|---|
| Job bắt đầu | Một lần cho mỗi `JobExecution` | `INFO` | `jobName`, `jobExecutionId`, khóa nghiệp vụ đã được phép log. |
| Step bắt đầu | Một lần cho mỗi `StepExecution` | `INFO` | `stepName`, `stepExecutionId`, `jobExecutionId`. |
| Step đang chạy | Theo mốc số chunk/item hoặc thời gian | `INFO` hay `DEBUG` | Các bộ đếm tổng hợp, thời gian, tiến độ nếu biết tổng. |
| Step hoàn tất | Một lần khi callback được gọi | `INFO` hoặc `WARN` | `BatchStatus`, `ExitStatus`, read/write/skip/rollback, duration. |
| Job hoàn tất | Một lần khi callback được gọi | `INFO` hoặc `ERROR` tùy trạng thái | Trạng thái cuối và thời gian. |
| Lỗi quan trọng làm thất bại step | Mỗi failure event quan trọng, có kiểm soát trùng lặp | `ERROR` | Loại lỗi, ID execution, stack trace ở một vị trí thống nhất. |
| Item bị skip | Tổng kết theo step, hoặc mẫu có giới hạn | `WARN`/`DEBUG` | Số skip theo loại, mã lỗi, định danh kỹ thuật cho phép. |
| Chi tiết item để debug | Chỉ khi chủ động bật | `DEBUG`/`TRACE` | ID không nhạy cảm, dữ liệu đã che/mask. |

**Không lấy log làm nguồn sự thật duy nhất về kết quả batch.** `JobRepository` lưu `JobExecution`, `StepExecution` và `ExecutionContext`; hệ thống metrics giúp quan sát các số đo theo thời gian; dữ liệu nghiệp vụ đã commit mới xác nhận kết quả xử lý. Log nên làm rõ các sự kiện có ý nghĩa và hỗ trợ liên kết tới những nguồn đó.

## 4. Bước đơn giản nhất: cấu hình logging level hợp lý

Ứng dụng Spring Boot dùng SLF4J làm API logging với backend thường là Logback khi dùng các starter thông thường. Có thể cấu hình level bằng `application.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example.batch: INFO
    com.example.batch.reader: WARN
    com.example.batch.processor: WARN
    org.springframework.batch: WARN
    org.springframework.jdbc: WARN
    org.hibernate.SQL: WARN
```

Đây là **cấu hình minh họa**, cần thay `com.example.batch` bằng package thực tế. Ý nghĩa:

- Giữ các sự kiện kinh doanh và tổng kết chủ động phát ở `INFO`.
- Hạn chế log item-level `INFO` từ reader/processor nếu dự án đang dùng các logger riêng theo package.
- Không cho các logger framework phát `DEBUG`/`TRACE` khi vận hành job lớn.
- `WARN` và `ERROR` vẫn được ghi nếu logger/appender được cấu hình tương ứng.

Điều cần hiểu: nâng `com.example.batch.processor` lên `WARN` có thể **ẩn cả một số sự kiện `INFO` thực sự cần thiết** nếu tất cả code dùng chung một logger/package. Vì vậy, lâu dài nên phân biệt logger phục vụ **tổng kết vòng đời** với logger phục vụ **chi tiết per-item**, hoặc chuyển chi tiết item xuống `DEBUG`.

### 4.1. Chuyển log thường xuyên xuống DEBUG/TRACE

Mẫu ban đầu gây ồn:

```java
@Override
public Order process(Order order) {
    log.info("Processing order {}", order.getId());
    return normalize(order);
}
```

Đổi thành:

```java
@Override
public Order process(Order order) {
    log.debug("Processing order id={}", order.getId());
    return normalize(order);
}
```

`Order` và `normalize(...)` là thành phần giả định của ứng dụng. Với level mặc định `INFO`, dòng `DEBUG` không được phát. Khi điều tra, có thể bật `DEBUG` có giới hạn phạm vi/thời gian để xem thêm chi tiết. Tuy nhiên **bật DEBUG trên hàng triệu item vẫn tạo lượng log rất lớn**; nên kết hợp với sampling khi cần.

### 4.2. Tránh tạo thông điệp đắt tiền trước khi logger kiểm tra level

SLF4J hỗ trợ placeholder `{}`:

```java
log.debug("Processing order id={} status={}",
        order.getId(), order.getStatus());
```

Đây thường là cách tốt hơn nối chuỗi thủ công:

```java
log.debug("Processing order " + order.getId()
        + ", payload=" + expensiveJsonSerialization(order));
```

Ngay cả khi `DEBUG` đang tắt, Java vẫn phải đánh giá **các biểu thức tham số** trước khi gọi logger. Vì vậy, placeholder không tự ngăn việc gọi `expensiveJsonSerialization(order)` nếu hàm đó được truyền vào. Khi chuẩn bị dữ liệu log đắt tiền, dùng guard:

```java
if (log.isDebugEnabled()) {
    log.debug("Order id={} snapshot={}",
            order.getId(), safeDebugSnapshot(order));
}
```

`safeDebugSnapshot(...)` nên được thiết kế để tránh secrets/payload nhạy cảm và không phải là phép xử lý nghiệp vụ bắt buộc. `isDebugEnabled()` giúp tránh phép tạo snapshot khi DEBUG tắt, nhưng không giảm lượng log khi DEBUG được bật; sampling vẫn cần nếu số sự kiện lớn.

## 5. Chuyển từ log từng item sang log tổng kết ở step

`StepExecutionListener` là nơi phù hợp để phát **một thông điệp tổng kết** cho một lần thực thi step. Trong Spring Batch 5.x, callback `afterStep` nhận `StepExecution`, từ đó có thể lấy các bộ đếm read/write/filter/skip/commit/rollback và trạng thái.

Ví dụ dùng Java 17+ và Spring Batch 5.2.x:

```java
import java.time.Duration;
import java.time.LocalDateTime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class StepSummaryLogListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepSummaryLogListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        log.info("batch.step.started jobExecutionId={} stepExecutionId={} stepName={}",
                step.getJobExecution().getId(),
                step.getId(),
                step.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        long durationMs = elapsedMillis(step);

        String message = "batch.step.finished jobExecutionId={} "
                + "stepExecutionId={} stepName={} status={} exitCode={} "
                + "read={} written={} filtered={} skipped={} "
                + "commits={} rollbacks={} durationMs={}";

        Object[] fields = {
                step.getJobExecution().getId(),
                step.getId(),
                step.getStepName(),
                step.getStatus(),
                step.getExitStatus().getExitCode(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount(),
                durationMs
        };

        if (step.getStatus() == BatchStatus.COMPLETED) {
            log.info(message, fields);
        } else {
            log.warn(message, fields);
        }

        return null; // Listener chỉ quan sát, không đổi ExitStatus.
    }

    private static long elapsedMillis(StepExecution step) {
        LocalDateTime start = step.getStartTime();
        LocalDateTime end = step.getEndTime();
        return start != null && end != null
                ? Duration.between(start, end).toMillis()
                : -1L;
    }
}
```

Listener này phát **hai log lifecycle cho mỗi step** theo đường chạy thông thường: một khi bắt đầu và một khi callback kết thúc được gọi. Số log không tăng theo số item được xử lý. `durationMs=-1` là ký hiệu minh họa khi không đủ mốc thời gian; trường này không đại diện cho thời gian âm thực tế.

`afterStep` có thể được gọi sau một lỗi xử lý bình thường, nhưng **không được bảo đảm** nếu JVM/process bị kill hoặc crash. Khi job ngừng bất thường, cần kiểm tra trạng thái repository và hệ thống giám sát; không coi việc thiếu log kết thúc là bằng chứng duy nhất cho trạng thái job.

`afterStep` trả về `ExitStatus` để framework có thể điều chỉnh exit code khi cần. Nếu listener chỉ làm nhiệm vụ logging, **trả `null`** tránh vô tình thay đổi kết quả hoặc flow của batch job.

### 5.1. Đăng ký listener đúng step

Ví dụ TaskletStep trong Spring Batch 5.x:

```java
@Bean
StepSummaryLogListener stepSummaryLogListener() {
    return new StepSummaryLogListener();
}

@Bean
Step importOrdersStep(JobRepository repository,
                      PlatformTransactionManager transactionManager,
                      StepSummaryLogListener summaryListener) {
    return new StepBuilder("importOrders", repository)
            .tasklet((contribution, chunkContext) -> {
                // Business tasklet ở đây.
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .listener(summaryListener)
            .build();
}
```

Các import tương ứng ở Spring Batch 5.x: `org.springframework.batch.core.Step`, `org.springframework.batch.core.repository.JobRepository`, `org.springframework.batch.core.step.builder.StepBuilder`, `org.springframework.batch.repeat.RepeatStatus`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.context.annotation.Bean`. Đây là mẫu phần thân cấu hình `@Configuration`, giả định hạ tầng Batch đã được Spring tạo.

Với chunk-oriented step, `.listener(summaryListener)` cũng dùng được khi đặt trên builder tương ứng. Đừng kỳ vọng một bean `@Component` tự động nhận callback nếu chưa được gắn với step hoặc chưa có cơ chế đăng ký listener.

### 5.2. `readCount` và `writeCount` không nhất thiết bằng nhau

Đừng coi sự khác biệt giữa read và write là lỗi mặc định. Một processor có thể trả `null` để lọc item, một số item có thể bị skip, hoặc một tasklet có thể tự cập nhật SQL mà không đi qua thống kê item của chunk. Log tổng kết nên giữ `filtered` và `skipped` để người vận hành hiểu thêm về chênh lệch đó.

## 6. Theo dõi tiến độ có giới hạn: log mỗi N chunk thành công

Chỉ ghi log đầu/cuối step có thể chưa đủ với một job chạy nhiều giờ. Có thể ghi **tiến độ theo khoảng**, chẳng hạn một lần mỗi 200 chunk commit thành công, thay vì một lần mỗi item.

Trong Spring Batch 5.x, `ChunkListener.afterChunk(ChunkContext)` được gọi sau khi chunk thực thi thành công và ngoài transaction của chunk; `afterChunkError(ChunkContext)` báo lỗi ở cấp chunk. Vì thế, `afterChunk` phù hợp để đếm **những chunk hoàn tất thành công**, còn lỗi sẽ được tổng kết/ghi riêng.

Ví dụ sau dùng `ConcurrentHashMap` và `AtomicLong` để một bean listener có thể phục vụ nhiều `StepExecution` mà không sử dụng một bộ đếm chung gây trộn lẫn tiến độ:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public final class ThrottledChunkLogListener
        implements ChunkListener, StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ThrottledChunkLogListener.class);

    private final long everyChunks;
    private final ConcurrentMap<Long, AtomicLong> counters =
            new ConcurrentHashMap<>();

    public ThrottledChunkLogListener(long everyChunks) {
        if (everyChunks <= 0) {
            throw new IllegalArgumentException("everyChunks must be positive");
        }
        this.everyChunks = everyChunks;
    }

    @Override
    public void beforeStep(StepExecution step) {
        counters.put(step.getId(), new AtomicLong());
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();
        long count = counters.computeIfAbsent(
                step.getId(), ignored -> new AtomicLong())
                .incrementAndGet();

        if (count % everyChunks == 0) {
            log.info("batch.step.progress jobExecutionId={} "
                            + "stepExecutionId={} stepName={} successfulChunks={} "
                            + "read={} written={} skipped={}",
                    step.getJobExecution().getId(),
                    step.getId(),
                    step.getStepName(),
                    count,
                    step.getReadCount(),
                    step.getWriteCount(),
                    step.getSkipCount());
        }
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        counters.remove(step.getId());
        return null;
    }
}
```

Với step có commit interval 500 item, log mỗi 200 chunk sẽ cho một điểm tiến độ xấp xỉ mỗi 100.000 item xử lý thành công trong điều kiện bình thường. Con số này chỉ để **ước lượng**; retry/skip, rollback, lọc item và logic reader/writer có thể khiến read/write count không tăng đều như vậy. Mẫu code sử dụng ID `StepExecution` đã được cấp khi step thực sự chạy qua `JobRepository`; nếu unit test tạo step chưa có ID thì cần cấp một ID giả trong fixture.

Đăng ký listener với builder:

```java
@Bean
ThrottledChunkLogListener throttledChunkLogListener() {
    return new ThrottledChunkLogListener(200);
}

// Trong StepBuilder của step thực tế:
// .listener(throttledChunkLogListener)
```

Một listener triển khai đồng thời hai interface lifecycle được đăng ký thông qua `.listener(...)` tương ứng. Nếu dùng nhiều listener trong một step, tránh tạo hai instance độc lập của cùng một listener rồi mong chúng chia sẻ bộ đếm.

**Lưu ý về concurrency:** `AtomicLong` giúp mỗi bước tăng bộ đếm an toàn khi callbacks có thể được gọi gần nhau. Các count từ `StepExecution` tại một thời điểm là *snapshot tiến độ*; khi multi-threaded step chạy song song, chúng có thể là số liệu đang thay đổi. Log tổng kết cuối step và metrics/repository là nguồn thích hợp hơn để xác nhận số liệu cuối cùng. Với partitioning trên nhiều process, mỗi worker có listener và `StepExecution` riêng, không dùng bộ đếm local để suy ra tổng toàn job.

**Lưu ý về restart:** Khi restart sinh `StepExecution` mới, bộ đếm chunk trong listener bắt đầu lại từ 0. Đó là số chunk thành công **trong execution hiện tại**, không phải tổng cộng cho mọi lần chạy của cùng job instance. Giữ `jobExecutionId` và `stepExecutionId` trong log để đọc số liệu đúng phạm vi.

### 6.1. Khi log mỗi N chunk chưa phù hợp

Mốc theo số chunk có thể cho quá nhiều log khi chunk rất nhỏ hoặc quá ít log khi một chunk xử lý cực lâu. Các lựa chọn khác:

- **Theo item count:** chỉ ghi khi số item vượt một ngưỡng mới, ví dụ mỗi 50.000 item; cần cơ chế nhớ mốc trước để không log lặp khi đọc count giống nhau.
- **Theo thời gian:** tối đa một log mỗi 30–60 giây cho từng step execution; phù hợp job có tốc độ thay đổi, nhưng cần thời gian monotonic và cơ chế atomic khi có nhiều thread.
- **Kết hợp:** log khi qua một mốc item lớn **hoặc** khi khoảng thời gian đã hết, dùng rate limiter theo từng execution; vẫn phải bảo đảm log lỗi/tổng kết không bị chặn.
- **Không log tiến độ:** dùng metrics để dashboard hiển thị throughput/latency, chỉ để log sự kiện lifecycle và lỗi.

Đừng dùng `Thread.sleep(...)` trong reader/processor chỉ để giảm tần suất log. Nó làm chậm công việc chính; cơ chế giới hạn phải nằm ở **quyết định có phát log hay không**.

## 7. Sampling log item mà vẫn hỗ trợ chẩn đoán

Trong vài hệ thống, cần giữ một số log item-level để phát hiện dữ liệu bất thường hoặc tái hiện lỗi. Khi đó, **sampling** giúp giảm số bản ghi log.

### 7.1. Sampling định kỳ

Ví dụ chỉ ghi một dòng `DEBUG` cho mỗi 10.000 item đi qua một processor:

```java
public final class SamplingOrderProcessor
        implements ItemProcessor<Order, Order> {

    private static final Logger log =
            LoggerFactory.getLogger(SamplingOrderProcessor.class);

    private final AtomicLong seen = new AtomicLong();

    @Override
    public Order process(Order item) {
        long count = seen.incrementAndGet();

        if (log.isDebugEnabled() && count % 10_000 == 0) {
            log.debug("batch.item.sample count={} orderId={}",
                    count, item.getId());
        }

        return normalize(item);
    }
}
```

Ví dụ sử dụng `org.springframework.batch.item.ItemProcessor`, `java.util.concurrent.atomic.AtomicLong`, `org.slf4j.Logger/LoggerFactory`; `Order` và `normalize(...)` là thành phần của ứng dụng. Cách này đơn giản để minh họa sampling, **nhưng có giới hạn cần hiểu**:

- `AtomicLong` thuộc **instance processor**, không tự reset theo `StepExecution`. Nếu bean processor là singleton được dùng qua nhiều execution, counter có thể tiếp tục tăng giữa các lần chạy; cần chọn phạm vi bean hoặc cơ chế reset rõ ràng.
- Nếu processor được gọi lại do retry/rollback, counter biểu thị **số lần gọi processor**, không phải số item đã commit thành công.
- Sampling theo vị trí có thể bỏ qua sự kiện hiếm hoặc có quy luật trùng chu kỳ lấy mẫu.
- Nếu muốn phân tích lỗi của *mọi item không hợp lệ*, sampling các dòng lỗi không thay thế được bảng audit/quarantine hoặc hệ thống lưu lỗi có cấu trúc.

Với job lớn, chiến lược chắc chắn hơn thường là **log tổng hợp từ `StepExecution`**, chỉ lấy mẫu item khi thực sự cần. Nếu cần sampling ổn định theo ID để cùng item luôn nằm trong tập mẫu qua nhiều lần chạy, có thể chọn item bằng hash của **khóa nghiệp vụ không nhạy cảm**, thay vì counter toàn cục. Phải biết rõ cơ chế hash và không làm lộ danh tính/PII trong log.

### 7.2. Sampling không áp dụng máy móc cho ERROR

Không nên áp cùng tỷ lệ lấy mẫu cho mọi loại log. Chẳng hạn:

- `DEBUG` thông tin item bình thường: có thể sampling mạnh hoặc tắt hoàn toàn.
- `INFO` tiến độ: giới hạn tần suất ở mỗi step execution.
- `WARN` dữ liệu không hợp lệ: tổng hợp theo loại lỗi, chỉ log một số ví dụ được phép hiển thị.
- `ERROR` làm thất bại step/job: cần có sự kiện tổng kết đầy đủ và mã lỗi/ID để tra cứu, tránh bỏ qua tất cả log lỗi do sampling.

Nếu một batch gặp 500.000 dòng dữ liệu lỗi giống nhau, ghi 500.000 stack trace ở `ERROR` thường không giúp chẩn đoán hơn so với ghi **lỗi đại diện** và các bộ đếm/nhóm nguyên nhân. Khi yêu cầu nghiệp vụ là lưu đầy đủ các dòng bị từ chối, nên ghi vào **quarantine table, error file hoặc dead-letter destination** với quy tắc transaction/restart riêng; log không phải nơi lưu dữ liệu nghiệp vụ đáng tin cậy.

## 8. Gom lỗi và thống kê skip thay vì in stack trace mỗi lần

Trong fault-tolerant step, các callback đọc/xử lý/ghi có thể gọi lặp lại quanh retry và rollback. Nếu mỗi callback đều ghi cùng exception với stack trace, log thường chứa nhiều bản sao của một lỗi.

`StepExecution` cung cấp bộ đếm tổng, có thể dùng ở cuối step:

```java
@Override
public ExitStatus afterStep(StepExecution step) {
    if (step.getSkipCount() > 0) {
        log.warn("batch.step.skips stepExecutionId={} "
                        + "readSkips={} processSkips={} writeSkips={} "
                        + "totalSkips={}",
                step.getId(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount());
    }
    return null;
}
```

Đây là **một mẫu callback độc lập**; nếu đã có `afterStep` trong `StepSummaryLogListener`, hãy đưa phần tổng kết skip vào phương thức đó, không khai báo hai `afterStep` cùng chữ ký trong một class.

Nếu cần phân loại nguyên nhân lỗi, có thể dùng `SkipListener` hoặc listener ở nơi lỗi xuất hiện để **tăng bộ đếm theo loại lỗi**, sau đó phát một bản tổng kết. Để không tạo bộ nhớ tăng không giới hạn, tránh lưu toàn bộ object/exception của từng item trong một `Map`. Giữ tập loại lỗi có giới hạn và chỉ ghi một số ví dụ đại diện có kiểm soát.

Ví dụ nguyên tắc chọn trường log lỗi:

```text
batch.step.skips stepExecutionId=4102 totalSkips=231
batch.step.skip-categories stepExecutionId=4102 invalidFormat=170 missingReference=61
batch.step.failed stepExecutionId=4102 exceptionType=IllegalStateException
```

Không in toàn bộ JSON, SQL bind parameters, token truy cập, dữ liệu thanh toán hay thông tin khách hàng chỉ để phục vụ debug. Hệ thống log thường có số người đọc và thời gian lưu khác với database nghiệp vụ.

### 8.1. Chọn một vị trí ghi stack trace đầy đủ

Một quy tắc vận hành dễ hiểu:

1. Nơi bắt lỗi ở mức cao ghi một stack trace đầy đủ **cho mỗi failure có ý nghĩa**.
2. Listener khác ghi `exceptionType`/`errorCode` và execution ID nhưng không in stack trace lặp lại.
3. Nếu step khôi phục thành công bằng retry, log tổng kết phản ánh kết quả cuối; không dùng mọi lỗi tạm thời để kết luận step đã thất bại.

Đối với exception chứa nội dung nhạy cảm trong message hoặc cause, cần áp dụng chính sách lọc dữ liệu trước khi phát log. Việc ném lỗi đã được framework xử lý đúng không đồng nghĩa mọi message ngoại lệ đều an toàn để ghi nguyên văn.

## 9. Structured logging giúp ít dòng nhưng vẫn dễ tra cứu

Khi log tập trung được đưa vào OpenSearch, Elasticsearch, Loki hoặc một nền tảng observability, cấu trúc nhất quán giúp tìm kiếm nhanh mà không cần in nhiều dòng diễn giải. Ví dụ một event tổng kết:

```json
{
  "event": "batch.step.finished",
  "jobName": "importOrdersJob",
  "jobExecutionId": 701,
  "stepName": "importOrders",
  "stepExecutionId": 902,
  "status": "COMPLETED",
  "exitCode": "COMPLETED",
  "readCount": 1000000,
  "writeCount": 995000,
  "filterCount": 5000,
  "skipCount": 0,
  "durationMs": 178200
}
```

Đây là **định dạng dữ liệu minh họa**, không phải kết quả mặc định của `StepSummaryLogListener` ở mục 5. Muốn có JSON fields thực sự, cần cấu hình logging backend/encoder hoặc sử dụng cơ chế structured logging mà phiên bản Spring Boot hỗ trợ.

Với Spring Boot 3.4+ có cấu hình structured logging tích hợp, có thể bắt đầu bằng:

```yaml
logging:
  structured:
    format:
      console: ecs
```

`ecs` là định dạng Elastic Common Schema; các key bổ sung phụ thuộc cách ứng dụng tạo log và hỗ trợ của logging backend. Nếu cần gửi dữ liệu có tên trường cố định, có thể sử dụng SLF4J 2 fluent API và một encoder cấu hình để giữ key-value pairs:

```java
log.atInfo()
        .addKeyValue("event", "batch.step.finished")
        .addKeyValue("stepExecutionId", step.getId())
        .addKeyValue("status", step.getStatus())
        .addKeyValue("readCount", step.getReadCount())
        .addKeyValue("writeCount", step.getWriteCount())
        .log("Step finished");
```

Không phải mọi appender sẽ xuất các pair này thành JSON field. Cần chọn và cấu hình encoder tương thích. Trường `jobExecutionId` hoặc `stepExecutionId` hữu ích để tìm log nhưng **không nên dùng làm tag của mọi metric** vì tạo high cardinality.

## 10. MDC và correlation ID: dùng vừa đủ

MDC (*Mapped Diagnostic Context*) cho phép gắn ngữ cảnh như job/step execution ID với các log trong thread hiện tại. Trong một callback ngắn, có thể dùng:

```java
import org.slf4j.MDC;

void logSummary(StepExecution step) {
    try (MDC.MDCCloseable jobId = MDC.putCloseable(
                    "jobExecutionId",
                    String.valueOf(step.getJobExecution().getId()));
         MDC.MDCCloseable stepId = MDC.putCloseable(
                    "stepExecutionId", String.valueOf(step.getId()))) {

        log.info("batch.step.finished stepName={} status={}",
                step.getStepName(), step.getStatus());
    }
}
```

Nếu logging backend đưa MDC vào pattern/JSON, ta có thể lọc theo ID mà không phải chèn thủ công ID vào mọi message. Tuy nhiên:

- MDC có phạm vi **thread**. Trong multi-threaded step, partitioning hoặc asynchronous processing, MDC không tự truyền đáng tin cậy tới các thread khác.
- Đặt MDC ở `beforeStep` rồi chỉ xóa trong `afterStep` dễ để sót trạng thái khi luồng chạy không kết thúc bình thường hoặc khi callback khác nằm trên thread khác.
- Cần dọn MDC bằng `try-with-resources`/`finally`, và có cơ chế propagation riêng nếu muốn correlation xuyên thread.
- Không dùng MDC như một cách ghi mọi `JobParameters` vào log; chỉ đưa các key đã được phép xuất.

Số lượng log giảm chủ yếu nhờ **ít sự kiện hơn**; MDC và structured fields giúp những sự kiện còn lại dễ tra cứu, chứ bản thân chúng không làm giảm lượng log.

## 11. Metrics thay cho log tiến độ liên tục

Một yêu cầu vận hành thường gặp là “job đang chạy được bao lâu?”, “bao nhiêu step đang active?”, “thời gian đọc/ghi có tăng bất thường không?”. Đây là câu hỏi phù hợp với **metrics** và dashboard hơn là phát log mỗi vài giây cho mọi item.

Spring Batch 5.2 cung cấp hỗ trợ Micrometer với các metric có prefix `spring.batch`, chẳng hạn:

| Metric | Loại đo | Ý nghĩa |
|---|---|---|
| `spring.batch.job` | Timer | Thời gian thực thi job, có các tag như tên và trạng thái. |
| `spring.batch.job.active` | Long task timer | Job đang hoạt động. |
| `spring.batch.step` | Timer | Thời gian thực thi step. |
| `spring.batch.step.active` | Long task timer | Step đang hoạt động. |
| `spring.batch.item.read` | Timer | Thời gian đọc item. |
| `spring.batch.item.process` | Timer | Thời gian xử lý item. |
| `spring.batch.chunk.write` | Timer | Thời gian ghi chunk. |

Các metric built-in hữu ích cho độ trễ và trạng thái. Chúng không tự thay thế mọi bộ đếm nghiệp vụ theo ý muốn. Nếu cần đo thông lượng/tổng số bản ghi hợp lệ, có thể xây dựng counter/gauge riêng theo hợp đồng ứng dụng và bảo đảm chúng phản ánh đúng semantics khi retry/rollback. Chẳng hạn, đếm mỗi lần gọi `process()` **không luôn bằng** số item đã commit.

Trong Spring Boot, hệ thống metrics thường được xuất qua Micrometer/Actuator khi đã có dependency và registry phù hợp (ví dụ Prometheus registry), đồng thời endpoint được cấu hình và bảo vệ đúng cách. Không nên tự suy luận “đã có Micrometer thì dashboard chắc chắn đang thu thập”.

**Giữ cardinality thấp:** tag hợp lý là tên job, tên step và trạng thái thuộc tập hữu hạn. Không tạo metric tag với từng `orderId`, `fileName` tùy ý hay `jobExecutionId`; hàng triệu giá trị khác nhau có thể gây tốn tài nguyên ở metrics backend. Execution ID nên nằm trong log/trace, còn metric phản ánh tổng hợp theo loại workload.

Một mô hình vận hành thường hợp lý:

```text
Metrics     -> cảnh báo độ trễ, throughput, failure rate
Logs        -> sự kiện lifecycle và lỗi cần điều tra
JobRepository -> trạng thái job/step và checkpoint
Business DB -> kết quả nghiệp vụ đã commit
Traces      -> đường đi giữa service khi cần phân tích latency
```

## 12. Async logging: giảm ảnh hưởng I/O nhưng phải hiểu rủi ro

Khi lượng log vẫn đáng kể, backend logging có thể hỗ trợ **asynchronous appender** để thread xử lý batch đưa log event vào hàng đợi và một thread khác ghi ra đích. Điều này giảm thời gian thread chính trực tiếp chờ I/O trong nhiều tình huống, nhưng **không làm mất chi phí tạo log** và không làm giảm tổng bytes được gửi đi nếu số event giữ nguyên.

Ví dụ cấu hình Logback đơn giản trong `src/main/resources/logback-spring.xml`:

```xml
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>

    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <neverBlock>false</neverBlock>
        <appender-ref ref="STDOUT"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC"/>
    </root>
</configuration>
```

Mẫu này dùng `queueSize=2048`, `neverBlock=false` để ưu tiên không bỏ event chỉ vì queue đầy: khi backlog quá lớn, producer có thể **bị chặn** cho tới khi queue có chỗ. Đây là trade-off quan trọng vì throughput job có thể bị ảnh hưởng. Nếu dùng `neverBlock=true`, ứng dụng có thể bỏ log khi queue đầy; cần đánh giá xem có chấp nhận mất event hay không. `discardingThreshold` cũng ảnh hưởng chính sách drop event ưu tiên thấp trong Logback; một cấu hình sai có thể khiến thông tin chẩn đoán bị thiếu.

Những rủi ro cần cân nhắc:

- Process crash có thể làm mất các event còn trong queue chưa ghi được.
- Queue quá nhỏ khiến producer bị block/drop; queue quá lớn chiếm bộ nhớ và tăng thời gian shutdown/flushing.
- Async appender thường chỉ giảm chờ I/O; vẫn phải tránh log per-item hoặc serialization đắt tiền.
- Stack trace và event chứa nhiều dữ liệu vẫn tốn chi phí encode và lưu trữ.
- Nếu dùng cấu hình `logback-spring.xml`, cần hiểu tương tác với logging settings và appenders sẵn có của Spring Boot.

Ưu tiên giảm **số lượng sự kiện** trước khi tuning async queue; đây thường là thay đổi đem lại hiệu quả lớn nhất và dễ kiểm soát nhất.

## 13. Log rotation, retention và bộ thu thập log

Ngay cả khi ứng dụng đã giảm log, quá trình lưu trữ và tìm kiếm vẫn cần chính sách quản lý vòng đời phù hợp:

| Biện pháp | Lợi ích | Điều cần cân nhắc |
|---|---|---|
| Ghi stdout trong container | Dễ tích hợp log collector | Phải giới hạn kích thước/retention tại container runtime hoặc nền tảng log. |
| Rotate file theo size/thời gian | Tránh một file log tăng không giới hạn | Cần bảo đảm log collector theo dõi file mới và xóa file cũ đúng cách. |
| Retention theo loại log | Giảm chi phí lưu trữ | Không cắt ngắn dữ liệu phục vụ audit/compliance bắt buộc. |
| Collector filtering/sampling | Giảm traffic/indexing | Log đã được tạo ở ứng dụng; filtering tại collector không trả lại CPU/I/O mà ứng dụng đã tiêu tốn. |
| Structured fields và index hợp lý | Tìm sự cố nhanh | Tránh index mọi giá trị cardinality cao hoặc nội dung item lớn. |

Nếu ứng dụng đã gửi một triệu dòng qua stdout, việc log collector giữ lại chỉ một phần **không xóa được chi phí format và ghi stdout ban đầu**. Sampling tại application boundary thường tiết kiệm hơn khi đã xác định rõ các event có thể bỏ qua.

Trong hệ thống có yêu cầu audit từng giao dịch, log phục vụ observability và audit nghiệp vụ là hai luồng khác nhau. Không giảm audit bắt buộc bằng tỷ lệ sampling ngẫu nhiên; thiết kế audit record có schema, quyền truy cập, transaction và retention riêng.

## 14. Kiểm thử chiến lược giảm log

Không nên kiểm thử bằng cách chờ một job hàng chục triệu bản ghi trong mỗi lần build. Có thể kiểm tra logic phát log ở quy mô nhỏ, sau đó kiểm chứng tác động hiệu năng ở môi trường tải phù hợp.

### 14.1. Unit test cho listener tổng kết

Spring Boot Starter Test cung cấp `OutputCaptureExtension` để bắt console log trong test. `spring-batch-test` có `MetaDataInstanceFactory` giúp tạo `StepExecution` mà không phải chạy toàn job.

Dependencies minh họa cho Spring Boot 3.x:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Ví dụ JUnit Jupiter:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class StepSummaryLogListenerTest {

    private final StepSummaryLogListener listener =
            new StepSummaryLogListener();

    @Test
    void logsOneSummaryForACompletedStep(CapturedOutput output) {
        StepExecution step = MetaDataInstanceFactory
                .createStepExecution("importOrders", 636L);
        step.setStatus(BatchStatus.COMPLETED);
        step.setReadCount(100_000);
        step.setWriteCount(99_500);
        step.setFilterCount(500);

        listener.beforeStep(step);
        assertNull(listener.afterStep(step));

        assertThat(output.getOut())
                .contains("batch.step.started")
                .contains("batch.step.finished")
                .contains("stepExecutionId=636")
                .contains("read=100000")
                .contains("written=99500");
    }
}
```

Test trên giả định logger `INFO` được bật và console appender phát nội dung ra stdout. Nếu cấu hình test không có console appender hoặc level của class cao hơn `INFO`, cần điều chỉnh môi trường kiểm thử. Unit test này chỉ xác nhận callback phát thông điệp mong muốn, không chứng minh listener đã được gắn vào một step thực tế.

### 14.2. Test throttling bằng số chunk giả lập

Đối với `ThrottledChunkLogListener(200)`, có thể tạo `StepExecution` bằng `MetaDataInstanceFactory`, dựng `ChunkContext` và gọi `afterChunk` 199 lần để xác minh chưa có progress log, sau đó gọi lần thứ 200 để xác minh có log. Sau khi gọi `afterStep`, chạy một `StepExecution` khác để bảo đảm bộ đếm thuộc execution mới.

Test nên xác nhận **hành vi tại ngưỡng** (199, 200, 201), cùng việc dọn state giữa các execution. Không cần tạo hàng triệu item thật để kiểm tra phép giới hạn tần suất.

Nếu muốn kiểm tra thread-safety, có thể gọi callback qua nhiều thread với các execution riêng và kiểm tra mỗi execution có tần suất riêng. Bài test đó đo logic bộ đếm, không phải hiệu năng toàn bộ Spring Batch.

### 14.3. Đo hiệu quả khi tối ưu

Khi đánh giá một thay đổi giảm log, nên chạy cùng workload/input ở môi trường test tải và so sánh các chỉ số:

| Chỉ số | Trước tối ưu | Sau tối ưu cần quan sát |
|---|---|---|
| Số log event mỗi 1.000 item | Rất cao nếu có log per-item | Giảm theo mục tiêu đã chọn. |
| Bytes log phát ra/phút | Có thể tăng tỷ lệ với số item | Giảm đáng kể trong đường chạy bình thường. |
| Throughput (items/s) | Bị ảnh hưởng bởi logging overhead | Ổn định hoặc tăng khi I/O giảm. |
| CPU sử dụng cho serialization/logging | Cao khi log payload | Giảm nhờ bỏ format không cần thiết. |
| Latency chunk p95/p99 | Có thể tăng khi appender/collector chậm | Giảm nếu log là bottleneck. |
| Thời gian tìm nguyên nhân lỗi | Log nhiều nhưng khó tra | Giữ hoặc cải thiện nhờ event và ID rõ ràng. |
| Số alert/incident bị bỏ lỡ | Là tiêu chí chất lượng quan sát | Không tăng sau sampling. |

Nếu không biết log là bottleneck, đừng kết luận chỉ từ việc giảm số dòng. Hãy đo throughput, I/O và chất lượng chẩn đoán trước/sau, vì ở một số workload khác, database hoặc API ngoài mới là điểm nghẽn chính.

## 15. Restart, retry, partitioning và log tổng hợp

### 15.1. Retry/rollback có thể làm một item xuất hiện nhiều lần

Trong fault-tolerant step, một item có thể được đọc/xử lý/ghi lại. Nếu processor log `INFO` theo mỗi lần gọi, log có thể đếm trùng một item sau rollback. Do đó không sử dụng **số dòng log per-item** như số item đã commit.

`StepExecution.getReadCount()`, `getWriteCount()`, `getSkipCount()` và các trường liên quan phản ánh thống kê do Batch quản lý theo semantics của step. Trong trường hợp cần số record ghi thực vào database, kiểm chứng thêm bằng dữ liệu nghiệp vụ hoặc một bộ đếm nghiệp vụ đúng transaction semantics.

### 15.2. Restart tạo execution ID mới

Một lần restart thường tạo `JobExecution` mới trong cùng `JobInstance`, và các step được chạy lại có `StepExecution` mới. Ví dụ:

```text
jobInstanceId=51, jobName=nightlyImport
  jobExecutionId=901
    stepExecutionId=1101 status=FAILED
  jobExecutionId=902
    stepExecutionId=1105 status=COMPLETED
```

Khi log progress, luôn kèm `jobExecutionId` và `stepExecutionId`; số liệu progress trong execution mới không nhất thiết tiếp nối bộ đếm trong execution cũ. Muốn theo dõi chuỗi restart của một instance, có thể bổ sung `jobInstanceId`.

### 15.3. Partitioning và multi-threaded step

Mỗi partition thường có một `StepExecution` riêng. Đừng để tất cả partition cùng ghi một log tiến độ toàn job ở mỗi chunk; có thể tạo log gấp số partition. Thay vào đó, để mỗi worker phát event thưa với ID partition/step execution, và tổng hợp toàn job qua metrics hoặc JobRepository.

Với multi-threaded step, bộ đếm tiến độ đọc giữa chừng có thể thay đổi đồng thời. Một `AtomicLong` lưu trong singleton listener mà không tách theo execution sẽ dễ trộn hai job đang chạy. Sử dụng state theo ID execution, đồng bộ phù hợp hoặc một bean có phạm vi phù hợp. Tránh lưu toàn bộ item vào state chỉ để tổng hợp log.

### 15.4. Step tạm dừng, lỗi nặng và thiếu log cuối

Nếu process mất điện/crash hoặc hạ tầng chấm dứt JVM, `afterStep`/`afterJob` có thể không chạy. Một hệ thống giảm log quá mạnh có thể không có thông tin tiến độ gần nhất. Hãy giữ metrics thời gian thực, trạng thái job/step trong repository và alert giám sát job chạy quá lâu; chúng bổ sung cho log lifecycle.

## 16. Những lỗi giảm log thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Đã đổi `root` sang WARN nhưng console vẫn đầy | Code/library dùng cấu hình logger riêng hoặc appender khác; một số message ở WARN/ERROR | Tìm logger/class phát sinh, cấu hình level đúng và sửa log per-item. |
| Job nhanh hơn nhưng mất dấu lỗi quan trọng | Sampling/rate limit áp dụng cả log lỗi cuối | Giữ event tổng kết thất bại và định danh execution; sampling chỉ với log có thể bỏ. |
| `DEBUG` tắt mà CPU vẫn cao vì logging | Serialization hoặc method argument được tính trước khi logger kiểm tra | Dùng parameterized logging và guard `isDebugEnabled()` cho tác vụ đắt tiền. |
| Log progress trùng nhiều lần | Nhiều listener cùng đăng ký hoặc threshold không nhớ mốc đã phát | Rà soát listener, dùng counter/state theo `StepExecution`. |
| Dòng progress nhảy lùi sau restart | Bộ đếm của lần thực thi mới bắt đầu lại | Kèm execution ID; không ghép counter của nhiều executions mà không có quy tắc. |
| Số dòng log “thành công” không khớp DB | Retry/rollback hoặc processor log trước commit | Dùng thống kê step và dữ liệu đã commit, không đếm log item. |
| Appender async làm mất log | Queue overflow, `neverBlock=true`, crash trước khi flush | Cân nhắc chính sách drop/block, theo dõi queue và shutdown. |
| Giảm log bằng sampling nhưng storage vẫn cao | Nhiều job/replica cùng phát, payload dài hoặc framework ở TRACE | Giảm event từ ứng dụng, rút trường không cần thiết, kiểm soát level và collector. |
| Khi bật DEBUG để điều tra job lại chậm | Processor log từng item | Bật ở phạm vi nhỏ, dùng sampling, đặt thời hạn tắt DEBUG. |
| Log lộ dữ liệu nhạy cảm | In toàn bộ item, params, context, exception body | Chỉ log allowlist, mask trường nhạy cảm; tách audit khi cần. |
| Không thấy tiến độ giữa chừng | Chỉ log bắt đầu/kết thúc của step chạy nhiều giờ | Bổ sung progress log giới hạn hoặc dashboard metrics. |
| Metrics backend quá tải | Dùng item ID/execution ID làm metric tags | Giữ tag thấp cardinality; execution ID chỉ đưa vào log/trace. |

## 17. Quy trình áp dụng để giảm log trên một job lớn

Một cách thực tế để cải thiện khả năng quan sát mà vẫn giảm chi phí:

1. **Đo lượng log hiện tại:** xác định tổng dòng/bytes log mỗi phút, log theo logger, thời gian job và throughput.
2. **Nhận diện nguồn log nhiều nhất:** reader, processor, writer, item listeners, SQL logger hay framework.
3. **Phân loại sự kiện cần giữ:** log vòng đời, lỗi, kết quả tổng hợp và tiến độ; phân biệt với chi tiết phục vụ debug.
4. **Thay log per-item bằng log ở step/job:** giữ ID execution, status, exit code và bộ đếm để có điểm điều tra rõ.
5. **Chọn chiến lược progress:** log theo mốc item, chunk hoặc thời gian; đặt ngưỡng theo tốc độ và thời lượng job.
6. **Tổng hợp skip/retry:** ghi số liệu và nguyên nhân chính; tránh in lặp stack trace/payload cho hàng nghìn item lỗi giống nhau.
7. **Thiết lập logger level:** tắt DEBUG/TRACE mặc định ở framework/package nóng, vẫn hỗ trợ bật lại có kiểm soát khi điều tra.
8. **Dùng metrics cho dashboard:** theo dõi latency, active jobs, throughput và alert thay cho một dòng log mỗi item.
9. **Kiểm thử giới hạn log:** kiểm tra event ở ngưỡng và cuối step, đặc biệt trong retry/restart và multi-threaded step.
10. **Đo lại hiệu quả:** so sánh log volume, throughput, độ trễ và khả năng tìm nguyên nhân sự cố; điều chỉnh ngưỡng theo thực tế.

### Bài tập thực hành

**Bài 1 — Từ một triệu log xuống vài dòng tổng kết**

Giả sử `ItemProcessor` đang log `INFO` cho mỗi item. Chuyển log item thành `DEBUG`, bổ sung `StepSummaryLogListener` và đưa các trường `read`, `written`, `filtered`, `skipped`, `durationMs` vào log cuối step. Unit test với `MetaDataInstanceFactory` để xác minh thông điệp chứa thông tin đúng.

**Bài 2 — Progress sau mỗi 100 chunk**

Đăng ký `ThrottledChunkLogListener(100)` vào một chunk-oriented step. Chạy test với nhiều chunk nhỏ và quan sát không có progress log ở các chunk 1–99, có một event ở chunk thứ 100 và một event cuối step. Cân nhắc rollback: lỗi chunk không nên tự được coi là một chunk commit thành công.

**Bài 3 — Job có nhiều lỗi dữ liệu**

Mô phỏng 1.000 item không hợp lệ cùng loại. Thiết kế cách tổng hợp `readSkips`, `processSkips`, `writeSkips` và một số lỗi mẫu. So sánh với cách ghi 1.000 stack trace, xác định nơi lưu đầy đủ các item bị từ chối nếu nghiệp vụ cần đối soát.

**Bài 4 — Đo chi phí logging**

Chạy cùng bộ dữ liệu với ba cấu hình: log item ở `INFO`, log item ở `DEBUG` nhưng DEBUG tắt, và chỉ log tổng kết + progress theo mốc. So sánh số sự kiện, bytes log, throughput và thời gian xử lý. Giữ database/input/chunk size tương đương để kết quả có ý nghĩa.

## 18. Tài liệu tham khảo chính thức

- [Spring Batch 5.2 — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html): cách dùng `StepExecutionListener`, `ChunkListener` và listener theo item.
- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html): Micrometer metrics tích hợp và các loại số đo có sẵn.
- [Spring Batch 5.2 — `ChunkListener` Javadoc](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/ChunkListener.html): thời điểm gọi callbacks của chunk và lưu ý rollback.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): `logging.level`, cấu hình Logback và structured logging.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): công cụ quan sát metrics khi tích hợp Micrometer/Actuator.
- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders.html#AsyncAppender): queue, discarding policy và các trade-off của logging bất đồng bộ.
- [SLF4J Manual](https://www.slf4j.org/manual.html): placeholder logging, MDC và fluent API.

