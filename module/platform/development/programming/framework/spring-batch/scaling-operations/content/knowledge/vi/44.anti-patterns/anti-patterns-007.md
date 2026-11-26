# Anti-pattern: Ghi log toàn bộ payload lớn trong Spring Batch

## 1. Nhận diện anti-pattern

Khi triển khai **SPRING_BATCH_SCALING_OPERATIONS**, mục tiêu là mở rộng Spring Batch để xử lý khối lượng dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán, đồng thời giữ được thread safety, throughput, retry/restart và khả năng vận hành. Một anti-pattern thường làm những nỗ lực này mất tác dụng là **ghi toàn bộ payload của item, chunk, partition hoặc message vào log trong luồng xử lý bình thường**.

Ví dụ:

~~~java
// Sai: payload của từng item bị đưa vào log.
@Override
public ProcessedOrder process(Order order) {
    log.info("Processing order: {}", order);
    return transform(order);
}

// Sai: in cả chunk (có thể gồm hàng nghìn item).
@Override
public void write(Chunk<? extends ProcessedOrder> chunk) throws Exception {
    log.info("Writing all items: {}", chunk.getItems());
    delegate.write(chunk);
}
~~~

Các dòng trên trông hữu ích khi chạy dữ liệu nhỏ, nhưng trở thành điểm nghẽn khi job xử lý hàng triệu bản ghi hoặc hàng trăm chunk đồng thời. Nếu đối tượng chứa thông tin cá nhân, khóa truy cập hay dữ liệu nội bộ, việc ghi log còn làm tăng nguy cơ lộ dữ liệu ngoài phạm vi xử lý ban đầu.

**Bản chất vấn đề:** Log là kênh quan sát sự kiện và trạng thái xử lý, không phải kho sao chép toàn bộ dữ liệu đầu vào/đầu ra của batch job. Khi cần truy xuất payload cho nghiệp vụ hoặc điều tra sự cố, phải có nguồn dữ liệu hoặc cơ chế lưu bằng chứng được quản lý phù hợp, thay vì mặc định sao chép vào log.

Bài này phân tích dấu hiệu, hậu quả, cách thay bằng log có cấu trúc và metrics, cũng như quy trình chẩn đoán khi chạy Spring Batch trên nhiều thread, worker hoặc broker.

## 2. Vì sao ghi payload lớn gây hại?

### 2.1. Khối lượng log tăng theo số bản ghi

Giả sử một job xử lý **12 triệu item**, mỗi bản ghi sau khi chuyển thành chuỗi log dài trung bình **4 KB** (đơn vị thập phân). Nếu ghi toàn bộ item đúng một lần:

~~~text
12.000.000 item × 4 KB ≈ 48 GB log thô/job
~~~

Nếu log ở cả `ItemReader` và `ItemWriter`, con số có thể lên khoảng **96 GB**, chưa tính prefix, metadata, stack trace, bản sao qua log shipper, compression ratio hay retry. Một lần restart xử lý lại một phần dữ liệu làm tăng log thêm. Khi lưu log nhiều ngày và nhân bản vào nhiều đích, chi phí storage, network và hệ thống tìm kiếm sẽ tăng theo.

Trong trường hợp chia job thành tám partition, tổng số bản ghi nghiệp vụ không tự tăng gấp tám; tuy nhiên **tám worker có thể phát log cùng lúc**, tạo đỉnh thông lượng ghi log lớn hơn, gây nghẽn đĩa, mạng hoặc pipeline thu gom.

Tổng volume có thể ước lượng:

~~~text
LogVolume ≈ N × AverageSerializedPayloadSize
                × LoggingPointsPerItem
                × RetryOrReplayFactor
           + metadata + exception output

LogRate ≈ itemsPerSecond × averageLogBytesPerItem
~~~

Đây là công thức dự toán, không phải số liệu Spring Batch tự đo. Để ra quyết định nên đo kích thước log thực tế với mẫu dữ liệu an toàn và khối lượng đại diện.

### 2.2. Serialization, cấp phát bộ nhớ và garbage collection

Khi payload được stringify, JVM phải duyệt các trường, định dạng chuỗi, tạo buffer và có thể tạo nhiều đối tượng trung gian. Với JSON serializer, payload lồng nhau hoặc kiểu dữ liệu đặc biệt, việc chuyển đổi có thể tốn CPU đáng kể. Nếu mỗi item sinh ra một chuỗi vài KB, tốc độ cấp phát bộ nhớ và số lần GC sẽ tăng; khi CPU bận xử lý log, throughput nghiệp vụ giảm.

Đặc biệt nguy hiểm là **tự serialize trước lời gọi logger**:

~~~java
// Sai: writeValueAsString được tính ngay cả khi DEBUG đang tắt.
log.debug("payload={}", objectMapper.writeValueAsString(order));

// Sai: nối chuỗi được thực hiện trước khi logger kiểm tra level.
log.debug("payload=" + order);

// Khi INFO bật, logger sẽ format/toString toàn bộ chunk.
log.info("chunk payload={}", chunk.getItems());
~~~

SLF4J hỗ trợ placeholder `{}` để trì hoãn việc format khi level tắt, nhưng **không trì hoãn tính toán biểu thức tham số** như `objectMapper.writeValueAsString(order)`. Khi level bật, một `toString()` tốn kém vẫn làm tiêu hao CPU và cấp phát bộ nhớ. Cả `toString()` lẫn JSON serializer có thể vô tình truy cập lazy relation hoặc duyệt toàn bộ object graph.

### 2.3. I/O, backpressure và tranh chấp tài nguyên

Khi log đi qua console, file, container runtime, sidecar/agent, network và hệ thống tìm kiếm, mỗi tầng có giới hạn throughput và queue riêng:

~~~mermaid
flowchart LR
    A[Reader / Processor / Writer] --> B[Format log + serialize payload]
    B --> C[Logger / appender]
    C --> D[stdout hoặc file]
    D --> E[Collector / shipper]
    E --> F[Log broker / index / storage]
    G[CPU + Heap + GC] -. tài nguyên tiêu thụ .-> B
    H[Đĩa + Network + Queue] -. điểm nghẽn .-> D
~~~

- **Synchronous appender:** thread nghiệp vụ có thể chờ ghi log; trong multi-threaded step, nhiều thread cùng gây áp lực lên appender.
- **Asynchronous appender:** giúp giảm thời gian chờ trong một số điều kiện, nhưng vẫn phải format/cấp phát dữ liệu theo cấu hình, có buffer hữu hạn và chính sách khi queue đầy (chặn, loại bỏ hoặc xử lý khác tùy appender). Chuyển sang async không giải quyết lượng dữ liệu log quá lớn.
- **Container logging:** stdout/stderr được hệ thống runtime chuyển tiếp; volume lớn có thể gây tải cho node, agent và log aggregator.
- **Đường I/O chung:** nếu log và dữ liệu batch cùng sử dụng đĩa, network hoặc CPU, log cạnh tranh tài nguyên với việc đọc/ghi dữ liệu thật.

Khi thấy job “scale worker lên nhưng throughput đứng yên”, phải đo cả các thành phần quan sát như log pipeline, không chỉ CPU của `ItemProcessor` hay độ trễ database.

### 2.4. Bảo mật và chi phí vận hành

Payload thường chứa dữ liệu mà quyền đọc log rộng hơn quyền đọc nguồn dữ liệu. Các rủi ro gồm:

- Lộ PII, số tài khoản, địa chỉ, email, token, API key, thông tin thanh toán hoặc dữ liệu của tenant khác.
- Lưu thông tin nhạy cảm lâu hơn chính sách retention của nguồn; khó thực hiện xóa/ẩn thông tin đã nhân bản qua nhiều hệ thống log.
- Tăng rủi ro khi operator gửi log cho bên thứ ba hoặc tải về máy cá nhân để điều tra.
- Log injection: nội dung do bên ngoài cung cấp chứa xuống dòng/ký tự điều khiển, giả lập sự kiện khác nếu hệ thống render log không escape an toàn.
- Chi phí lưu trữ, indexing, truyền tải, truy vấn; thời gian tìm lỗi chậm vì quá nhiều bản ghi không có giá trị chẩn đoán.

**Không nên nghĩ “đã mask password là an toàn”.** Danh sách trường nhạy cảm có thể thay đổi, các trường lồng nhau khó kiểm soát, và ngay cả dữ liệu nhìn vô hại cũng có thể tiết lộ thông tin nghiệp vụ hoặc danh tính nếu kết hợp với nhau.

## 3. Những vị trí thường ghi log payload không cần thiết

| Vị trí | Anti-pattern | Hệ quả đặc thù |
|---|---|---|
| `ItemReader.read()` | `log.info("item={}", item)` | Log mỗi item, thậm chí lặp lại khi reader retry/restart |
| `ItemProcessor.process()` | Serialize toàn object trước và sau transform | Nhân đôi log và chi phí CPU trên mỗi bản ghi |
| `ItemWriter.write(Chunk)` | Log `chunk.getItems()` hoặc toàn danh sách SQL parameters | Spike bộ nhớ/IO mỗi chunk; dễ lộ giá trị nhạy cảm |
| `ChunkListener`/`ItemWriteListener` | Dùng `toString()` của cả chunk | Phần logging cản trở transaction và commit path |
| `SkipListener` | Log đầy đủ item bị skip và exception | Payload lỗi thường chứa dữ liệu hỏng/nhạy cảm; dễ ghi trùng trong retry |
| Remote chunking | Log body request/response hoặc serialized message | Cùng payload xuất hiện ở manager, broker adapter và worker |
| Remote partitioning | Log cả `ExecutionContext` hay partition data | Có thể lộ connection info, cursor, key hoặc ranh giới dữ liệu; log trùng khi worker retry |
| HTTP/API vận hành | Log JobParameters không lọc hoặc toàn request | Các tham số có thể chứa token, đường dẫn hoặc định danh nhạy cảm |
| Framework logging | Bật DEBUG/TRACE toàn package serialization/JDBC/messaging trong production | Gián tiếp log payload dù code nghiệp vụ đã được sửa |

Một câu lệnh log trong loop đơn giản dễ nhận ra; khó phát hiện hơn là thư viện tự động log body tại tầng broker, HTTP filter hoặc JDBC. Khi điều tra log volume cao, cần kiểm tra cả logging configuration và middleware.

## 4. Thông tin nào thực sự cần quan sát?

Trước khi ghi log, xác định **câu hỏi vận hành** cần trả lời. Ví dụ:

- Job nào, execution nào, step/partition nào đang chậm?
- Mỗi step đã đọc, ghi, skip bao nhiêu bản ghi; tỷ lệ lỗi có tăng không?
- Chunk nào gặp retry và lỗi thuộc loại nào?
- Worker nào đang quá tải, queue lag là bao nhiêu?
- Job dừng ở đâu và có restart an toàn được không?
- Có khả năng dữ liệu bị xử lý lặp hoặc bỏ sót không?

Phần lớn những câu hỏi này cần **metadata, counters, duration và correlation**, không cần payload đầy đủ.

| Mục đích | Nên ghi/đo | Không nên làm |
|---|---|---|
| Kiểm tra job chạy tới đâu | `jobName`, `jobExecutionId`, `stepName`, status, start/end, tổng read/write/skip | In toàn danh sách item đã qua |
| Tìm partition gặp lỗi | `stepExecutionId`, partition key đã chuẩn hóa, worker instance, reason code | Dump `ExecutionContext` nguyên vẹn |
| Đo throughput | records/sec, chunks/sec, latency, reader/writer timing, queue lag | Log từng bản ghi ở INFO |
| Điều tra chunk thất bại | request/correlation ID, work unit ID, item count, exception class, mã lỗi | Log raw chunk, PII, toàn stack trace chứa input |
| Chống xử lý trùng | business key an toàn hoặc ID đã được bảo vệ, dedup outcome | Phát toàn record nhiều lần để tự so sánh |
| Audit lệnh vận hành | Actor, action, target, authorization decision, execution outcome | Gộp audit với payload dump không kiểm soát |

**Log, metric và trace phục vụ các mục tiêu khác nhau:**

- **Log có cấu trúc:** mô tả sự kiện rời rạc (job bắt đầu, step kết thúc, lỗi cần xử lý).
- **Metrics:** tổng hợp số lượng, tốc độ, độ trễ và dấu hiệu nghẽn trong khoảng thời gian.
- **Tracing/correlation:** liên kết các hoạt động giữa manager, broker và worker để thấy đường đi của một work unit.
- **JobRepository/JobExplorer:** nguồn thông tin trạng thái execution, checkpoint và các counter chuẩn của Spring Batch.

Không biến log thành nguồn quyết định restart; căn cứ restart phải dựa vào trạng thái và metadata Spring Batch đáng tin cậy cùng tính idempotent của xử lý nghiệp vụ.

## 5. Thay log payload bằng summary và correlation

### 5.1. Một sự kiện log được khuyến nghị

Ví dụ JSON line cho sự kiện tổng kết step:

~~~json
{
  "event": "batch.step.finished",
  "jobName": "invoiceAggregationJob",
  "jobExecutionId": 7312,
  "stepName": "aggregateWorkerStep:partition3",
  "stepExecutionId": 7490,
  "status": "COMPLETED",
  "readCount": 50000,
  "writeCount": 49990,
  "readSkipCount": 2,
  "processSkipCount": 5,
  "writeSkipCount": 3,
  "commitCount": 100,
  "rollbackCount": 1,
  "workerRelease": "batch-worker-2026.11",
  "correlationId": "job-7312"
}
~~~

Một bản ghi trên phục vụ nhiều truy vấn hiệu quả hơn hàng chục nghìn dòng liệt kê invoice. Các count là ví dụ minh họa; trong vận hành thực tế hãy lấy từ `StepExecution` hoặc nguồn đo tin cậy, không tự tính bằng cách đếm log dòng.

Nếu có lỗi tại một chunk, cấu trúc ngắn gọn có thể là:

~~~json
{
  "event": "batch.chunk.write_failed",
  "jobExecutionId": 7312,
  "stepExecutionId": 7490,
  "chunkSequence": 18,
  "itemCount": 500,
  "attempt": 2,
  "workerId": "worker-03",
  "reasonCode": "DB_DEADLOCK",
  "exceptionType": "DeadlockLoserDataAccessException",
  "correlationId": "job-7312-step-7490-chunk-18"
}
~~~

`chunkSequence` và `attempt` trong ví dụ là metadata **do ứng dụng định nghĩa**, không phải trường sẵn có trên mọi `Chunk` hoặc `StepExecution`. Khi không thể gán chuỗi thứ tự ổn định, dùng work unit/correlation ID đáng tin cậy để tránh bịa định danh sau mỗi retry.

### 5.2. Ví dụ Java: summary ở cuối Step

`StepExecutionListener` ghi một bản log tóm tắt sau khi step kết thúc, tránh lặp log cho từng item:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class StepSummaryLogListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepSummaryLogListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
            "event=batch.step.finished job={} jobExecutionId={} " +
            "step={} stepExecutionId={} status={} readCount={} " +
            "writeCount={} readSkipCount={} processSkipCount={} " +
            "writeSkipCount={} commitCount={} rollbackCount={}",
            step.getJobExecution().getJobInstance().getJobName(),
            step.getJobExecution().getId(),
            step.getStepName(),
            step.getId(),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getReadSkipCount(),
            step.getProcessSkipCount(),
            step.getWriteSkipCount(),
            step.getCommitCount(),
            step.getRollbackCount()
        );

        return null; // Không thay đổi ExitStatus mà Spring Batch đã xác định.
    }
}
~~~

Cấu trúc trên phù hợp với các API `StepExecutionListener` và `StepExecution` thông dụng của Spring Batch 5.x; nếu dùng phiên bản khác, kiểm tra chữ ký phương thức tương ứng. `afterStep` là hook quan sát kết quả tại thời điểm callback; event trong log **không thay thế** trạng thái đã lưu bền vững trong `JobRepository` và không nhất thiết chứng minh mọi hệ thống ngoài đã commit. Nếu cần audit cuối cùng có tính ràng buộc, thiết kế thêm event/outbox và đối soát.

Không gửi toàn bộ `ExitStatus.getExitDescription()`, vì thông điệp lỗi có thể chứa SQL parameter hay nội dung payload.

### 5.3. Ví dụ Java: writer không log item

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

public final class BoundedLoggingWriter<T> implements ItemWriter<T> {

    private static final Logger log =
            LoggerFactory.getLogger(BoundedLoggingWriter.class);
    private final ItemWriter<T> delegate;

    public BoundedLoggingWriter(ItemWriter<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        long started = System.nanoTime();
        try {
            delegate.write(chunk);

            // DEBUG: chỉ ghi số lượng và thời gian, không serialize item.
            if (log.isDebugEnabled()) {
                log.debug(
                    "event=batch.writer.returned itemCount={} durationMs={}",
                    chunk.size(),
                    (System.nanoTime() - started) / 1_000_000
                );
            }
        } catch (Exception ex) {
            // Không tự động ghi ex.getMessage(): nó có thể chứa dữ liệu.
            log.warn(
                "event=batch.writer.failed itemCount={} durationMs={} errorType={}",
                chunk.size(),
                (System.nanoTime() - started) / 1_000_000,
                ex.getClass().getSimpleName()
            );
            throw ex; // Giữ nguyên cơ chế retry/skip/rollback của Spring Batch.
        }
    }
}
~~~

Đoạn code là wrapper minh họa: giá trị `writer.returned` chỉ nói delegate đã trả về, **không đồng nghĩa transaction của chunk đã commit**. Khi cần thống kê commit/rollback, lấy counter của step hoặc đo tại boundary transaction phù hợp. Nếu lỗi xảy ra thường xuyên, ngay cả dòng WARN mỗi lần retry cũng có thể tạo quá nhiều log: nên kết hợp điều tiết, metrics và chỉ phát event khi retry exhausted/step failed theo nhu cầu vận hành.

Với `ItemProcessor`, nên ưu tiên metrics tổng hợp hoặc log sự kiện lỗi đã được phân loại thay vì gọi `toString()` trên item.

## 6. Logging trong multi-threaded step và partitioning

### 6.1. Không chia sẻ trạng thái mutable để tổng hợp log

Một sai lầm khác là dùng biến đếm không đồng bộ trong singleton processor:

~~~java
// Sai khi nhiều thread cùng truy cập một instance.
private long processedCount;

public void processItem() {
    processedCount++; // Race condition.
}
~~~

Nếu cần đếm tạm trong nhiều thread, có thể dùng `LongAdder` hoặc hệ thống metrics; nhưng khi cần **read/write/skip count chính xác để restart**, tin vào `StepExecution` và `JobRepository` hơn một biến đếm sống trong JVM. Các counter do ứng dụng tự tạo phải định nghĩa rõ lần đếm là attempt, item duy nhất hay commit thành công, đặc biệt trong retry.

Đừng cố giảm log bằng cách gom toàn bộ payload vào `List` dùng chung rồi in một lần cuối job: cách này vẫn giữ nguyên rủi ro lộ dữ liệu và tăng memory footprint, thậm chí gây `OutOfMemoryError`.

### 6.2. Correlation ID và MDC phải được truyền đúng

Một dòng log của worker thường cần biết nó thuộc job/step/partition nào. **MDC** của SLF4J phổ biến được quản lý theo thread; các thread trong task executor không tự động nhận mọi giá trị MDC từ thread tạo job.

Quy ước mẫu:

~~~text
jobExecutionId = 7312
stepExecutionId = 7490
partitionId     = partition3
workerId        = worker-03
correlationId   = job-7312-step-7490
~~~

Ở multi-threaded step, đưa context vào tác vụ bằng cơ chế `TaskDecorator` hoặc wrapper phù hợp, rồi **khôi phục/clear MDC trong `finally`** để tránh lẫn log giữa hai job dùng chung thread pool. Với remote worker, truyền correlation qua header/envelope đã xác thực và đặt lại MDC ở consumer; không tin header định danh tenant/operator do client ngoài tự điền.

Ví dụ nguyên tắc quản lý MDC:

~~~java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("jobExecutionId", String.valueOf(jobExecutionId));
    MDC.put("stepExecutionId", String.valueOf(stepExecutionId));
    runWork();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

Với nhiều layer async, phải quyết định context nào là cần thiết và giới hạn kích thước. Không sao chép toàn bộ `ExecutionContext`, thông tin bảo mật hoặc raw payload vào MDC.

### 6.3. Phân biệt log ở manager và worker

Ở **remote chunking**, manager và worker có thể cùng log một chunk, trong khi broker/adapter cũng log nội dung request và response. Thay vì log payload:

- **Manager** ghi job/step/chunk correlation, số chunk gửi, số response đã nhận, latency và timeout.
- **Worker** ghi work unit ID, item count, độ trễ xử lý, outcome và error code đã chuẩn hóa.
- **Broker monitoring** theo dõi queue depth, consumer lag, redelivery, DLQ; không cần log body.
- **Đối soát** dựa vào work unit ID và trạng thái thực, không dựa số lượng dòng log, vì retry làm một công việc xuất hiện nhiều lần.

Ở **remote partitioning**, request có thể chỉ mang ID để worker truy metadata trong `JobRepository`; không được mặc định payload broker chứa toàn bộ dữ liệu partition. Log ID và các ranh giới đã được rà soát bảo mật (nếu thực sự cần), thay vì dump `ExecutionContext`.

## 7. Logging levels, sampling và giới hạn volume

### 7.1. Quy tắc thực hành theo level

| Level | Nội dung thích hợp | Không nên |
|---|---|---|
| `ERROR` | Job/step thất bại, lỗi không thể tự phục hồi, mã lỗi và correlation | In lại tất cả item của batch khi thất bại |
| `WARN` | Retry exhausted, skip vượt ngưỡng, timeout hoặc degradation cần theo dõi | Ghi stack trace dài trên mỗi lần retry giống nhau |
| `INFO` | Job/step started/finished, tổng kết, thay đổi vận hành đáng kể | Log từng item hay từng SQL statement chứa dữ liệu |
| `DEBUG` | Metadata chunk/partition có giới hạn khi điều tra | Tự động biến thành dump payload |
| `TRACE` | Chỉ dùng theo quy trình chẩn đoán ngắn hạn, phạm vi rất hẹp | Bật package rộng trên production trong thời gian dài |

Level không phải cơ chế bảo mật. Một thông tin bí mật vẫn không được ghi ở DEBUG/TRACE, vì cấu hình log có thể được bật trong tương lai hoặc tồn tại trong hệ thống tập trung.

### 7.2. Sampling có kiểm soát

Nếu một job tạo hàng trăm nghìn chunk và cả metadata log mỗi chunk cũng quá nhiều, có thể:

1. Ghi **mọi lỗi quan trọng** một lần ở boundary phù hợp, kèm giới hạn tần suất để tránh log storm.
2. Ghi **sự kiện thông thường theo tỷ lệ sampling** (ví dụ 1% chunk), bảo toàn correlation ID.
3. Ghi **snapshot tổng hợp định kỳ**, ví dụ mỗi khoảng thời gian cố định hoặc khi kết thúc partition/step.
4. Giới hạn kích thước một event (`maxLogEventBytes`) và số event theo job/worker trong một khoảng thời gian.
5. Cho phép tăng sampling trong một khoảng thời gian ngắn qua cấu hình có kiểm soát, nhưng vẫn loại trừ payload nhạy cảm.

Một cách sampling ổn định là băm `workUnitId` rồi chọn theo modulo; cùng work unit sẽ có quyết định sampling nhất quán giữa retry. Tỷ lệ 1% chỉ là **ví dụ cấu hình**, không phải quy tắc cố định; nên chọn dựa trên chi phí log và nhu cầu chẩn đoán. Tránh tính `hashCode()` trực tiếp từ toàn bộ object payload chỉ để quyết định lấy mẫu.

**Không sampling các event bắt buộc cho audit bảo mật hoặc bằng chứng tuân thủ**, trừ khi quy định quản trị dữ liệu cho phép. Audit có kho, retention và chính sách riêng.

## 8. Đặt số đo vào Metrics thay vì log từng item

Ví dụ bộ chỉ số cho workload dữ liệu lớn:

| Metric | Câu hỏi giải đáp | Ghi chú triển khai |
|---|---|---|
| `batch_items_read_total` | Đã đọc bao nhiêu bản ghi? | Định nghĩa counter theo attempt hay commit, tránh đếm trùng retry |
| `batch_items_written_total` | Có bao nhiêu bản ghi đã được ghi thành công? | Phải phân biệt delegate returned và transaction committed |
| `batch_items_skipped_total` | Bao nhiêu item bị loại và vì lý do gì? | reason code với tập giá trị hữu hạn |
| `batch_chunk_duration_seconds` | Chunk chạy chậm ở reader, processor hay writer? | Histogram/timer, phân biệt p95/p99 với trung bình |
| `batch_job_duration_seconds` | Thời gian end-to-end của job | So với SLA |
| `batch_retry_total` | Có tình trạng retry bùng nổ không? | Tách retryable/permanent và stage |
| `batch_worker_active` | Worker nào/nhóm nào đang bận? | Gom theo job group/environment thay vì ID vô hạn |
| `batch_message_queue_lag` | Worker đang tụt sau manager? | Theo dõi song song với error/timeout ở remote chunking |
| `batch_log_dropped_total` | Pipeline log có bị mất sự kiện? | Tùy appender/collector có hỗ trợ đo hay không |

Tên metric là **quy ước minh họa**, không khẳng định Spring Batch/Micrometer tự phát tất cả các metric với các tên này. Spring Batch có tích hợp observability tùy phiên bản và cấu hình; ứng dụng phải xác nhận những metric nào thực sự được tạo.

Metrics cần **low-cardinality tags** như `jobName` (nếu số job name hữu hạn), `stepName`, `environment`, `outcome` và `reasonCode`. Không đưa `jobExecutionId`, `itemId`, `correlationId`, `tenantId` có số lượng lớn hoặc giá trị payload vào metric labels; việc đó tạo cardinality explosion và chi phí lưu time series.

Các định danh cá thể nên xuất hiện trong **structured log/tracing hoặc audit store**, nơi chúng có thể được tra cứu theo nhu cầu, thay vì trở thành nhãn của mọi time series.

## 9. Khi thật sự cần xem nội dung bản ghi lỗi

Có những tình huống cần biết **vì sao một item cụ thể không thể parse, validate hoặc ghi ra đích**. Cách xử lý nên được thiết kế có kiểm soát:

1. Ghi mã lỗi, `jobExecutionId`/`stepExecutionId`, nguồn dữ liệu, số dòng hoặc item reference **không nhạy cảm** và thời điểm. Định danh item đôi khi cũng chứa PII, phải đánh giá trước khi ghi.
2. Truy item từ nguồn gốc theo quyền truy cập thích hợp hoặc lưu bản ghi lỗi vào **quarantine store** có RBAC, mã hóa, retention và audit người truy cập.
3. Với payload phải xem trực tiếp, dùng **dữ liệu giả lập hoặc đã khử định danh** trong môi trường không production khi tái hiện lỗi.
4. Nếu cần lấy mẫu production, giới hạn số bản ghi, phạm vi job, thời hạn, người phê duyệt và trường được phép; dùng allowlist thay vì dump object.
5. Ghi dấu người yêu cầu, mục đích và thời điểm truy cập dữ liệu sự cố. Xóa/cắt quyền đúng lịch retention.

### 9.1. Cấu trúc quarantine hợp lý

~~~json
{
  "event": "batch.item.quarantined",
  "jobExecutionId": 7312,
  "stepExecutionId": 7490,
  "sourceSystem": "invoice-import",
  "sourceRecordRef": "safe-ref-cc83",
  "reasonCode": "INVALID_DATE_FORMAT",
  "quarantineRecordId": "quar-00271",
  "retentionClass": "restricted-short-term"
}
~~~

Bản ghi log chỉ lưu **tham chiếu**, còn payload nằm trong vùng quản lý truy cập riêng. Không đưa raw input trực tiếp vào `reasonCode` hoặc chuỗi exception.

### 9.2. Redaction và giới hạn payload nếu không tránh được

Nếu một tích hợp đặc biệt bắt buộc ghi một phần payload ở mức chẩn đoán:

- Chỉ chọn **trường nằm trong allowlist** đã phân loại dữ liệu và được rà soát.
- Giới hạn độ dài từng trường và tổng dung lượng event; escape ký tự điều khiển.
- Tránh logger tự in toàn bộ Java object vì `toString()` có thể đổi khi cập nhật DTO.
- Không sử dụng hash thuần của email/số điện thoại nếu dữ liệu có không gian đoán nhỏ; cần pseudonymization có thiết kế thích hợp, có thể dùng HMAC với khóa quản lý riêng khi thật sự cần tương quan.
- Không coi masking là đủ nếu nội dung còn tiết lộ dữ liệu nhạy cảm hoặc làm lộ tenant khác.

Ví dụ logging có allowlist:

~~~java
// Chỉ những metadata đã được rà soát, không gọi order.toString().
log.debug(
    "event=batch.item.validation_failed category={} " +
    "reasonCode={} sourceRecordRef={}",
    approvedCategory,
    validationReasonCode,
    safeReference
);
~~~

`safeReference` phải được cấp theo quy ước bảo mật; không tự nhận mọi business ID là không nhạy cảm.

## 10. Case study: throughput giảm sau khi bật DEBUG trên remote chunking

Một hệ thống thanh toán chạy `paymentSettlementJob` có 16 worker. Manager đọc chunk 1.000 item, worker ghi dữ liệu vào database. Khi gặp một số lỗi timeout, nhóm vận hành bật DEBUG cho toàn bộ package messaging và thêm dòng log serialize request body ở cả manager và worker.

**Hiện tượng:**

- Throughput giảm dù worker đã tăng từ 8 lên 16.
- CPU tăng ở phần JSON serialization; GC time và memory allocation tăng.
- stdout và log shipper tăng đột biến, queue log bắt đầu tồn đọng.
- Cùng một chunk xuất hiện nhiều lần khi retry; khó phân biệt redelivery với xử lý mới.
- Một số trường nghiệp vụ xuất hiện trong log tập trung dù không cần thiết cho điều tra.

**Chuỗi nhân quả có thể kiểm chứng:**

~~~mermaid
flowchart TD
    A[DEBUG ghi toàn bộ request/response] --> B[Serialization + allocation mỗi chunk]
    B --> C[CPU / GC pressure]
    A --> D[Volume stdout + log shipper tăng]
    D --> E[Backpressure hoặc chậm ghi I/O]
    C --> F[Throughput worker giảm]
    E --> F
    F --> G[Queue lag và retry tăng]
    G --> A
~~~

Sơ đồ thể hiện **giả thuyết cần kiểm chứng bằng đo đạc**, không khẳng định mọi lỗi timeout đều xuất phát từ logging. Database lock contention, connection pool và broker cũng có thể là nguyên nhân chính.

**Cách khắc phục:**

1. Tắt đường log body ở package messaging và code nghiệp vụ; giữ DEBUG chọn lọc với metadata ngắn.
2. Duy trì correlation ID xuyên manager, request, worker và response.
3. Đo `chunk.duration`, queue lag, redelivery, DB latency và GC trước/sau thay đổi.
4. Dùng một event cho lỗi cuối cùng của chunk, kèm work unit ID, reasonCode; tra message trong quarantine store nếu cần.
5. Đặt guardrail về log bytes/sec, retention và cảnh báo queue log shipper.
6. Test lại trên khối lượng tương đương production trước khi tăng số worker.

Kết quả mong muốn là **giảm chi phí quan sát trên mỗi item và khôi phục khả năng phân biệt nghẽn thực sự**. Không nên tuyên bố “đã tăng throughput X%” nếu chưa đo có kiểm soát.

## 11. Cách đo tác hại của anti-pattern

Một thí nghiệm hiệu năng hữu ích có thể chạy ba cấu hình:

| Cấu hình | Logging |
|---|---|
| A — baseline | Chỉ log sự kiện job/step và lỗi tổng hợp |
| B — metadata | Log chunk ID, item count, duration với sampling có kiểm soát |
| C — full payload | Log mọi item/chunk (chỉ dùng dữ liệu giả lập an toàn trong môi trường test) |

Giữ ổn định dataset, chunk size, concurrency, database, broker, heap và cấu hình worker khi so sánh; nếu có warm-up JVM, áp dụng giống nhau. Chạy lặp đủ để thấy biến động và đo:

- Throughput item/giây, thời gian job và p95/p99 chunk latency.
- CPU user/system, allocated bytes, GC pause, heap usage.
- Log bytes/giây, số event, thời gian appender chờ/queue depth, dropped logs (nếu có).
- Disk I/O, network, log collector CPU và indexing latency.
- Tỷ lệ retry/timeout/rollback, DB pool saturation và broker queue lag.

**Đừng chỉ so sánh “job mất bao nhiêu phút”.** Log có thể tạo backpressure theo đợt: median ổn nhưng p99 chunk latency tăng mạnh, dẫn tới timeout và retry khi workload lớn.

Ví dụ ước lượng dung lượng để lập ngân sách:

~~~text
8.000.000 item × 2 KB/item × 2 vị trí log
    = 32.000.000.000 byte ≈ 32 GB log thô/job

Nếu chạy 12 job/ngày:
    ≈ 384 GB log thô/ngày, chưa tính overhead và replication
~~~

Đây là **phép tính minh họa** theo giả định 2 KB mỗi dòng; chi phí thực tế còn phụ thuộc compression, thời gian lưu, số bản sao, mức indexing và việc có ghi thêm log lỗi khi retry. Với 16 worker, dữ liệu này có thể được phát ra đồng thời và gây đỉnh tải cao cho collector.

## 12. Những giải pháp tưởng đúng nhưng chưa giải quyết gốc vấn đề

| Cách làm | Vì sao vẫn có rủi ro | Cách điều chỉnh |
|---|---|---|
| “Chuyển toàn bộ payload sang DEBUG” | Khi bật DEBUG, volume và nguy cơ lộ dữ liệu quay lại | DEBUG chỉ ghi metadata đã được duyệt; dùng test fixture/quarantine để xem nội dung |
| “Dùng async logger là đủ” | Buffer hữu hạn, vẫn tốn serialization và storage; khi đầy có thể chặn hoặc mất log | Giảm volume tại nguồn, đo queue saturation và chính sách mất log |
| “Giữ 3 ngày nên không sao” | Mọi bản sao, search index và người có quyền đọc vẫn thấy payload | Data classification, retention phù hợp và hạn chế log raw từ đầu |
| “Đưa tất cả vào một dòng log cho dễ tra” | Một sự kiện rất lớn khó index, có thể bị truncate và tiêu tốn bộ nhớ | Log count, checksum/metadata cần thiết và safe reference |
| “Hash ID để bảo mật” | Hash của giá trị dễ đoán có thể bị đảo qua dictionary; còn dữ liệu khác vẫn lộ | Chỉ pseudonymize khi thật cần, dùng cơ chế phù hợp và rà soát fields |
| “Log payload chỉ khi có exception” | Exception lặp nhiều lần; payload lỗi thường chứa dữ liệu nhạy cảm | Log reasonCode + correlation + quarantine reference |
| “Chỉ log một item đầu tiên của mỗi chunk” | Item mẫu vẫn có thể chứa PII; logging per chunk vẫn rất lớn | Chỉ dùng allowlist, giới hạn số mẫu, môi trường và quyền |
| “Tăng số worker để bù mất throughput” | Mở rộng đồng thời làm đỉnh log volume và contention cao hơn | Xử lý gốc chi phí log rồi mới tuning thread/partition |

Tránh biến tính năng debug thành một đường xuất dữ liệu âm thầm. Những thay đổi cấu hình quan sát có ảnh hưởng đến dữ liệu nhạy cảm cần được quản lý như thay đổi production bình thường.

## 13. Checklist vận hành và tiêu chí hoàn thành

### Trước khi triển khai

- [ ] Không có `log.info()/warn()/error()` trực tiếp với `item`, `chunk.getItems()`, toàn `JobParameters` hoặc `ExecutionContext`.
- [ ] Kiểm tra middleware (HTTP, JDBC, messaging, serializer) không tự log request/response body khi bật DEBUG/TRACE.
- [ ] Chỉ log các field metadata được phê duyệt; không ghi secret, payload, PII hoặc business ID chưa phân loại.
- [ ] Có `jobExecutionId`, `stepExecutionId`, work unit/correlation ID để truy vết manager và worker.
- [ ] MDC được truyền/clear khi dùng thread pool, partition và remote worker.
- [ ] Log level, sampling, rate limit, max event size, retention và quyền truy cập được thiết kế rõ.
- [ ] Metrics có throughput, latency, retry/skip/rollback, queue lag và GC; nhãn có cardinality kiểm soát.
- [ ] Quy trình quarantine/replay và quyền xem dữ liệu lỗi đã được định nghĩa.

### Trong kiểm thử tải

- [ ] So sánh baseline và cấu hình logging mới trên dataset đại diện, có warm-up và giữ concurrency tương đương.
- [ ] Đo log bytes/giây, appender queue, collector pressure, CPU, GC và p95/p99 chunk latency.
- [ ] Gây retry/restart/worker crash để xác minh log không gây thêm bottleneck và correlation vẫn đúng.
- [ ] Tạo dữ liệu nhạy cảm giả lập để kiểm tra không bị ghi vào log, kể cả exception và nested object.
- [ ] Kiểm tra error events không gây log storm khi nhiều partition thất bại đồng thời.
- [ ] Khi tắt logging body, điều tra một lỗi có thật vẫn tìm được job, execution, step, worker, reasonCode và safe reference.

### Khi xảy ra sự cố production

1. Xác định phạm vi job/step/worker và đo log throughput, retry, GC, queue lag.
2. Ưu tiên tăng chỉ số và correlation; **không bật dump payload tràn lan**.
3. Thu thập một số safe reference, truy nguồn dữ liệu theo quyền được cấp hoặc quarantine store.
4. Đặt thời hạn tự tắt cho logging chẩn đoán, kiểm tra volume và quyền truy cập.
5. Sau sự cố, gỡ cấu hình quá chi tiết, lưu kết quả đối soát và cập nhật guardrail.

**Nguyên tắc áp dụng:** Trong Spring Batch mở rộng, một dòng log phải phục vụ một câu hỏi quan sát cụ thể với lượng thông tin tối thiểu cần thiết. Metadata, counters, tracing và kho dữ liệu có kiểm soát thường giải quyết sự cố tốt hơn việc in toàn bộ payload. Giảm log tại nguồn giúp bảo toàn CPU, heap, I/O, chi phí vận hành và an toàn dữ liệu khi số lượng thread, partition hoặc worker tăng.

### Tài liệu tham khảo

- [Spring Batch Reference — Monitoring and metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): các hướng quan sát job/step và metric theo phiên bản.
- [Spring Batch Reference — Scalability](https://docs.spring.io/spring-batch/reference/scalability.html): các mô hình xử lý song song và phân tán.
- [SLF4J Manual](https://www.slf4j.org/manual.html): parameterized logging và cách kiểm tra log level.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): metrics, timers và quản lý tag cardinality.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ dữ liệu nhạy cảm và kiểm soát logging.
