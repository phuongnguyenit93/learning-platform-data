# Log restart point trong Spring Batch

Khi một Spring Batch job đang xử lý hàng triệu bản ghi thì xảy ra lỗi, người vận hành thường hỏi: **“Lần chạy tiếp theo sẽ tiếp tục từ đâu?”**. Một dòng log như `Read 25,000 records` hoặc `Job failed` chưa đủ trả lời. Spring Batch dùng metadata trong `JobRepository` và trạng thái checkpoint của `ItemStream` để quyết định khả năng khôi phục. Nhiệm vụ của **log restart point** là giúp con người quan sát được trạng thái đó, đối chiếu với kết quả đã commit và điều tra những lần chạy tiếp theo.

Trong chủ đề **Logging** của **Spring Batch Core Processing**, bài học này giải thích ý nghĩa restart point, nguồn dữ liệu đáng tin cậy, vị trí ghi log trong vòng đời chunk/step, cách cấu hình listener và những sai lầm dễ khiến log báo một điểm tiếp tục khác với checkpoint thực tế.

## 1. Restart point là gì?

**Restart point** là vị trí hoặc trạng thái đã được lưu đủ để một job/step có thể tiếp tục khi thực thi lại sau thất bại hoặc dừng. Với một `ItemReader` có trạng thái, đó có thể là chỉ số item tiếp theo, số dòng của file, trang dữ liệu, offset hoặc một token do reader tự quản lý. Không phải mọi step có restart point dạng “dòng thứ N”: một tasklet có thể dùng cờ hoàn tất, một reader có thể dùng khóa của bản ghi cuối và một job gồm nhiều step có thể bỏ qua các step đã hoàn tất.

Ví dụ một step xử lý theo chunk, mỗi chunk 100 bản ghi:

```text
Input: 1 ------------------------------------------------------ 1000
       |       |       |       |       |        |
       v       v       v       v       v        v
      100     200     300     400     500      600
       C       C       C       C       C        X

C = chunk commit thành công, trạng thái checkpoint được lưu
X = lỗi khi đang xử lý chunk tiếp theo

Reader có thể đã đọc thử tới record 570.
Checkpoint bền vững gần nhất có thể vẫn là vị trí sau record 500.
Restart cần dựa vào checkpoint đã lưu, không dựa vào số 570 trong log đọc.
```

Khi start lại cùng `JobInstance` theo cơ chế restart, reader được khởi tạo với `ExecutionContext` đã lưu và khôi phục trạng thái từ đó. Tùy implementation, reader có thể đọc lại những item của chunk chưa commit; điều đó đúng theo mô hình **at-least-once ở ranh giới chưa commit** và đòi hỏi writer/side effect được thiết kế an toàn khi thử lại.

**Log restart point không phải cơ chế lưu checkpoint.** Log là bằng chứng quan sát, còn Spring Batch phục hồi dựa trên metadata/trạng thái do framework và `ItemStream` ghi vào `JobRepository`. Xóa log không làm mất checkpoint; xóa `ExecutionContext` trong repository có thể làm mất khả năng restart dù log vẫn còn.

## 2. Phân biệt tiến độ đã đọc, đã ghi và checkpoint

Ba khái niệm dễ bị nhầm:

| Khái niệm | Nguồn thông tin | Có đủ để xác định điểm restart? |
| --- | --- | --- |
| **Tiến độ đọc** | `StepExecution.getReadCount()`, log trong `ItemReader.read()` | Không. Số item đã đọc có thể gồm thao tác chưa commit, và thứ tự dữ liệu có thể thay đổi |
| **Tiến độ ghi** | `getWriteCount()`, writer log, số record ở đích | Không nhất thiết. Counter không cho biết cursor lưu cho reader, còn đích ngoài transaction có thể nhận dữ liệu trước khi lỗi |
| **Checkpoint đã persist** | `ExecutionContext` do `ItemStream.update()` cập nhật và `JobRepository` lưu | Là cơ sở phục hồi đối với stream hỗ trợ restart, kết hợp với metadata trạng thái job/step |

Ví dụ, log `Processed record id=INV-570` có thể đã được viết trước khi transaction rollback. Nếu gọi record 570 là **restart point**, người vận hành có thể bỏ qua records 501–570 chưa được commit. Ngược lại, nếu log `checkpoint committed: nextIndex=500` sau khi chunk transaction thành công, thông tin đó bám sát trạng thái có khả năng phục hồi hơn.

Ngay cả thông báo “checkpoint committed” cũng nên được hiểu theo cấu hình transaction của ứng dụng. Nếu ghi dữ liệu nghiệp vụ vào một nguồn ngoài transaction của `JobRepository` (API, object storage, broker, database khác mà không có cơ chế điều phối), checkpoint và side effect có thể không commit nguyên tử.

## 3. Metadata nào liên quan đến restart?

`JobRepository` dùng các thực thể sau:

```text
Job(name = importOrdersJob)
  |
  v
JobInstance (job name + identifying JobParameters)
  |
  +-- JobExecution #101 (FAILED)
  |     |
  |     +-- StepExecution #501: importOrdersStep FAILED
  |           |
  |           +-- StepExecutionContext: checkpoint ở chunk cuối đã commit
  |
  +-- JobExecution #102 (COMPLETED sau restart)
        |
        +-- StepExecution #502: importOrdersStep COMPLETED
```

### `JobInstance` và identifying parameters

Danh tính `JobInstance` dựa trên tên job và các `JobParameters` có `identifying=true`. Ví dụ `businessDate=2026-11-16` là identifying parameter để xử lý một kỳ nghiệp vụ. Một **restart đúng nghĩa** tạo `JobExecution` mới cho **cùng JobInstance**; nếu thêm `UUID` mới vào identifying parameters mỗi lần chạy, Spring Batch sẽ tạo instance khác và có thể xử lý dữ liệu từ đầu.

### `StepExecution` và trạng thái

Mỗi lần một step được thực thi có `StepExecution` riêng, chứa `getStatus()`, `getExitStatus()`, thời gian, `readCount`, `writeCount`, `commitCount`, `rollbackCount` và các skip count. Những giá trị này giúp điều tra lần chạy nhưng không thay thế checkpoint của reader. Các step đã `COMPLETED` thường không được chạy lại trong restart nếu không cấu hình đặc biệt như `allowStartIfComplete(true)`.

### `ExecutionContext`

`StepExecution.getExecutionContext()` chứa các key/value trạng thái của step. Một `ItemStreamReader` có thể dùng key riêng để ghi vị trí đọc vào context. Với JDBC `JobRepository`, framework persist snapshot vào bảng `BATCH_STEP_EXECUTION_CONTEXT`. `JobExecutionContext` cũng tồn tại nhưng phục vụ trạng thái phạm vi job; không nên tự tiện chuyển checkpoint step sang job context.

**Không có một key chuẩn chung `restartPoint` cho mọi reader.** Key phụ thuộc implementation, cấu hình tên reader và chiến lược checkpoint. Với một số reader chuẩn, internal key liên quan số item đã đọc. Với reader tùy chỉnh, người phát triển tự định nghĩa key. Không nên cố đọc một tên key nội bộ giả định cho tất cả loại reader.

## 4. Vòng đời lưu checkpoint trong một chunk

Với step chunk-oriented và `ItemStream` được Spring Batch quản lý, luồng khái quát như sau:

```text
Step bắt đầu / restart
    |
    +-- ItemStream.open(saved ExecutionContext)
    |      khôi phục offset/position
    v
Tạo chunk transaction
    |
    +-- Reader.read() nhiều lần
    +-- Processor.process()
    +-- Writer.write(chunk)
    +-- ItemStream.update(ExecutionContext)
    +-- Spring Batch cập nhật metadata/context qua JobRepository
    |
    +-- COMMIT transaction
    |      |
    |      +-- ChunkListener.afterChunk()
    |             log điểm đã quan sát sau commit
    |
    +-- Nếu lỗi: ROLLBACK và afterChunkError()
    v
Chunk tiếp theo / kết thúc step
    |
    +-- ItemStream.close()
```

Sơ đồ thể hiện ý tưởng; một số callback và chi tiết transaction có thể khác tùy reader, writer, transaction manager, kiểu step và phiên bản Spring Batch. Quan trọng nhất là phân biệt **trạng thái được chuẩn bị trước commit** với **trạng thái đã commit thành công**.

### Vì sao không log “đã commit” trong `ItemStream.update()`?

`update(ExecutionContext)` thường được gọi để đưa giá trị checkpoint mới vào context **trước khi transaction chunk commit**. Nếu transaction sau đó rollback, giá trị mới chỉ là checkpoint ứng viên trong bộ nhớ; chưa chắc đã được persist như một điểm restart bền vững. Vì vậy log tại `update()` nên dùng nhãn `checkpoint_candidate`, tránh viết `checkpoint_committed`.

`ChunkListener.afterChunk(ChunkContext)` là vị trí thuận tiện hơn để log sau khi một chunk hoàn tất thành công. Tuy vậy, bản thân việc ghi log cũng có thể thất bại hoặc bị mất khi process crash, nên không dùng log như nguồn sự thật tuyệt đối. Khi phải xác định chính xác điểm restart, hãy đối chiếu repository với trạng thái dữ liệu/nguồn ngoài.

### Vì sao không log “điểm restart” ở `ItemReadListener.afterRead()`?

`afterRead()` chạy khi reader đã trả item, trước khi processor/writer và commit. Nếu job đọc 500 item rồi writer lỗi, log đọc item cuối không chứng minh 500 item đã được commit. Log read event hữu ích để chẩn đoán item gây lỗi, nhưng không phải log checkpoint bền vững.

## 5. Mô hình log restart point nên chứa gì?

Một bản ghi có cấu trúc nên mang các trường sau:

| Trường | Vai trò | Ví dụ |
| --- | --- | --- |
| `event` | Phân biệt loại sự kiện | `batch.checkpoint.committed` |
| `jobName` | Tên job | `importOrdersJob` |
| `jobInstanceId` | Nối các executions thuộc một lần xử lý logic | `930` |
| `jobExecutionId` | Lần chạy cụ thể | `1482` |
| `stepName` | Bước xử lý | `importOrdersStep` |
| `stepExecutionId` | Lần thực thi của step | `3419` |
| `businessDate`/`inputVersion` | Phạm vi dữ liệu được xử lý | `2026-11-16`, `v17` |
| `readerName` | Phân biệt nhiều reader/state trong cùng step | `ordersReader` |
| `checkpointKey` | Tên key của ứng dụng/reader | `orders.reader.nextIndex` |
| `checkpointValue` | Giá trị đã quan sát tại mốc log | `500` |
| `readCount`, `writeCount`, `filterCount`, `skipCount` | Tiến độ tích lũy của step | `500`, `498`, `2`, `0` |
| `commitCount`, `rollbackCount` | Chẩn đoán transaction | `5`, `0` |
| `status`, `exitCode` | Trạng thái khi step/job kết thúc | `FAILED`, `FAILED` |
| `timestamp` và `traceId` | Nối log giữa các thành phần | `2026-11-17T02:05:00Z` |

Thông thường nên tạo **sự kiện tại các mốc quan trọng**, không ghi toàn bộ `ExecutionContext` sau từng item. Ghi log mỗi item với batch lớn làm tăng I/O và che mất thông tin hữu ích; `ExecutionContext` còn có thể chứa dữ liệu nhạy cảm, chuỗi trạng thái dài hoặc đối tượng không thuận tiện để serialize.

Ví dụ bản ghi JSON **minh họa**:

```json
{
  "timestamp": "2026-11-17T02:05:00Z",
  "level": "INFO",
  "event": "batch.checkpoint.committed",
  "jobName": "importOrdersJob",
  "jobInstanceId": 930,
  "jobExecutionId": 1482,
  "stepName": "importOrdersStep",
  "stepExecutionId": 3419,
  "businessDate": "2026-11-16",
  "readerName": "ordersReader",
  "checkpointKey": "orders.reader.nextIndex",
  "checkpointValue": 500,
  "readCount": 500,
  "writeCount": 498,
  "filterCount": 2,
  "commitCount": 5
}
```

Với reader đọc theo id, thay chỉ số `500` bằng khóa như `lastCommittedOrderId` nếu đó là checkpoint thực tế của reader. Nhưng cần bảo đảm query/order của reader cho phép tiếp tục an toàn từ khóa đó. Không tự gán một id nghiệp vụ cuối vừa được log vào `ExecutionContext` nếu nó không tương ứng với trạng thái transaction đã commit.

## 6. Ví dụ: reader tùy chỉnh lưu checkpoint vào `ExecutionContext`

Để thấy cơ chế checkpoint rõ ràng, xét một reader đơn giản đọc tuần tự từ danh sách cố định. Đây là ví dụ học tập cho **Spring Batch 5.x**, thích hợp với fixture nhỏ. Trong production, reader đọc file/database thường nên dùng implementation chuẩn có hỗ trợ restart và kiểm tra dữ liệu nguồn ổn định.

```java
package com.example.batch;

import java.util.List;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public final class RestartableOrderReader
        implements ItemStreamReader<String> {

    // Key thuộc về reader này: xác định item tiếp theo phải đọc.
    public static final String NEXT_INDEX_KEY = "orders.reader.nextIndex";

    private final List<String> orders;
    private int nextIndex;

    public RestartableOrderReader(List<String> orders) {
        this.orders = List.copyOf(orders);
    }

    @Override
    public void open(ExecutionContext executionContext) {
        nextIndex = executionContext.containsKey(NEXT_INDEX_KEY)
            ? executionContext.getInt(NEXT_INDEX_KEY)
            : 0;
    }

    @Override
    public String read() {
        if (nextIndex >= orders.size()) {
            return null;
        }
        return orders.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // Framework đưa trạng thái này vào repository tại checkpoint.
        executionContext.putInt(NEXT_INDEX_KEY, nextIndex);
    }

    @Override
    public void close() {
        // Không có file/socket cần đóng trong ví dụ bộ nhớ.
    }
}
```

Trong lần chạy đầu, `open()` nhận context chưa có key nên bắt đầu từ `nextIndex=0`. Sau khi ghi thành công chunk đầu (ví dụ hai item), `update()` đưa `nextIndex=2` vào context và framework persist tại checkpoint. Nếu chunk thứ hai gặp lỗi trước commit, repository vẫn có thể lưu offset đã commit là `2`. Khi restart cùng job instance, **một reader instance mới** mở lại context và đọc từ phần tử thứ ba.

```text
Input          : [A001, A002, A003, A004, A005]
Chunk size     : 2

Chunk #1       : A001, A002  -> commit thành công
Checkpoint     : orders.reader.nextIndex = 2

Chunk #2       : A003, A004  -> writer lỗi và rollback
Persisted state: orders.reader.nextIndex = 2

Restart        : read() bắt đầu từ A003
```

Đây là ví dụ tối giản về `ItemStreamReader`; nó chưa xử lý concurrency, transaction-aware buffering hoặc input thay đổi. Nếu `List` bị sắp xếp khác ở lần chạy lại, cùng `nextIndex=2` sẽ trỏ tới dữ liệu khác. Reader dựa trên offset vì thế đòi hỏi nguồn dữ liệu được giữ bất biến trong chuỗi execution liên quan, hoặc phải có cơ chế chọn vị trí ổn định hơn.

### Đăng ký reader vào step

```java
@Bean
@StepScope
RestartableOrderReader ordersReader() {
    return new RestartableOrderReader(
        List.of("A001", "A002", "A003", "A004", "A005")
    );
}

@Bean
Step importOrdersStep(JobRepository repository,
                      PlatformTransactionManager transactionManager,
                      RestartableOrderReader ordersReader,
                      ItemWriter<String> ordersWriter,
                      RestartPointLoggingListener loggingListener) {
    return new StepBuilder("importOrdersStep", repository)
        .<String, String>chunk(2, transactionManager)
        .reader(ordersReader)
        .writer(ordersWriter)
        .listener((StepExecutionListener) loggingListener)
        .listener((ChunkListener) loggingListener)
        .build();
}
```

Đoạn này là thành phần cấu hình minh họa; `ordersWriter`, `JobRepository`, transaction manager và các import do ứng dụng cung cấp. `@StepScope` tạo reader instance theo step execution, hạn chế giữ con trỏ cũ ở singleton giữa các lần chạy. Khi reader được khai báo trực tiếp qua `.reader(...)` và triển khai `ItemStream`, step có thể quản lý `open/update/close`; khi bọc reader trong delegate không được framework nhìn thấy, phải đăng ký stream phù hợp bằng `.stream(...)` để checkpoint hoạt động.

Đối với reader chuẩn như `FlatFileItemReader` hoặc `JdbcPagingItemReader`, nên cấu hình name duy nhất và `saveState(true)` khi muốn restart; đọc tài liệu implementation để hiểu cách lưu offset. Không dùng `saveState(false)` nếu mong reader khôi phục vị trí sau lỗi.

## 7. Ghi log sau commit bằng `ChunkListener`

Một listener có thể ghi các sự kiện: khi step bắt đầu, sau mỗi chunk thành công, khi chunk lỗi và khi step kết thúc. Ví dụ Spring Batch 5.x dưới đây đọc checkpoint key đã được reader ở phần trước định nghĩa; nếu key không tồn tại, log `unknown` thay vì tạo ra một vị trí giả.

```java
package com.example.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.item.ExecutionContext;

public final class RestartPointLoggingListener
        implements StepExecutionListener, ChunkListener {

    private static final Logger log =
        LoggerFactory.getLogger(RestartPointLoggingListener.class);

    private static final String CURSOR_KEY =
        RestartableOrderReader.NEXT_INDEX_KEY;

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info(
            "event=batch.step.started jobExecutionId={} stepExecutionId={} "
                + "step={} restoredCursor={} businessDate={}",
            stepExecution.getJobExecutionId(),
            stepExecution.getId(),
            stepExecution.getStepName(),
            safeCursor(stepExecution.getExecutionContext()),
            stepExecution.getJobParameters().getString("businessDate")
        );
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();

        log.info(
            "event=batch.checkpoint.committed jobExecutionId={} "
                + "stepExecutionId={} step={} cursor={} read={} write={} "
                + "filter={} commits={} rollbacks={}",
            step.getJobExecutionId(),
            step.getId(),
            step.getStepName(),
            safeCursor(step.getExecutionContext()),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getCommitCount(),
            step.getRollbackCount()
        );
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        StepExecution step = context.getStepContext().getStepExecution();
        log.warn(
            "event=batch.chunk.rolled_back jobExecutionId={} "
                + "stepExecutionId={} step={} read={} rollbacks={} "
                + "message=Checkpoint in memory may not be committed",
            step.getJobExecutionId(),
            step.getId(),
            step.getStepName(),
            step.getReadCount(),
            step.getRollbackCount()
        );
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "event=batch.step.finished jobExecutionId={} stepExecutionId={} "
                + "step={} status={} exitCode={} read={} write={} "
                + "commits={} rollbacks={}",
            stepExecution.getJobExecutionId(),
            stepExecution.getId(),
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getExitStatus().getExitCode(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount()
        );
        return null; // Giữ nguyên exit status do step quyết định.
    }

    private static String safeCursor(ExecutionContext context) {
        return context.containsKey(CURSOR_KEY)
            ? String.valueOf(context.getInt(CURSOR_KEY))
            : "unknown";
    }
}
```

`afterChunk(...)` được gọi sau khi chunk hoàn tất thành công trong mô hình xử lý chunk chuẩn; vì vậy đây là mốc tốt để báo *đã hoàn tất một ranh giới commit*. `afterChunkError(...)` là tín hiệu lỗi của chunk, **không** nên lấy giá trị `ExecutionContext` trong bộ nhớ tại callback đó rồi khẳng định là checkpoint đã persist. Khi thất bại, việc xác định vị trí restart bền vững nên lấy từ metadata được khôi phục trong lần chạy tiếp theo hoặc từ repository sau khi transaction rollback hoàn tất.

Trong ví dụ, `safeCursor(...)` chỉ đọc key ứng dụng `orders.reader.nextIndex`. Nếu thay bằng `FlatFileItemReader`, tên key và ý nghĩa trạng thái có thể khác. Tốt hơn hết là tạo một lớp ghi log cho chính reader/step của dự án, có định nghĩa rõ ý nghĩa `cursor` và không phụ thuộc vào key nội bộ chưa được cam kết ổn định giữa các version.

### Cấu hình logging và mức log

`INFO` phù hợp với các mốc step bắt đầu/kết thúc hoặc checkpoint theo chu kỳ đủ thưa để vận hành. Nếu chunk rất nhỏ và job xử lý hàng triệu item, ghi một dòng mỗi chunk có thể tạo log rất lớn. Có thể đặt `DEBUG` cho mọi chunk, còn `INFO` theo một ngưỡng thưa hơn hoặc theo khoảng thời gian, **nhưng vẫn phải bảo đảm thông tin cuối cùng có thể được kiểm tra từ `JobRepository`**.

Ví dụ cấu hình cơ bản trong `application.yml`:

```yaml
logging:
  level:
    com.example.batch.RestartPointLoggingListener: INFO
    org.springframework.batch: INFO
```

Khi chuyển sang JSON structured logging (Logback encoder/observability stack), nên đưa `event`, `jobExecutionId`, `stepExecutionId`, `businessDate` và `checkpoint` thành các field riêng để dễ lọc. Mẫu SLF4J ở trên dùng key-value trong thông điệp để dễ đọc mà không bắt buộc một encoder cụ thể.

## 8. Log phục hồi khi step bắt đầu lại

Phần quan trọng của restart logging là một cặp sự kiện có thể đối chiếu:

```text
Execution 1482: batch.checkpoint.committed cursor=500
Execution 1482: batch.step.finished status=FAILED

Execution 1483: batch.step.started restoredCursor=500
Execution 1483: batch.checkpoint.committed cursor=600
Execution 1483: batch.step.finished status=COMPLETED
```

Nếu có cùng `JobInstance` và identifying parameters, chuỗi trên cho thấy execution thứ hai bắt đầu với checkpoint đã được khôi phục. Tuy nhiên, log từ `beforeStep` mới chỉ chứng minh giá trị context được nạp vào step; cần kiểm tra reader thực sự áp dụng `open(...)` đúng, dữ liệu output đúng và không lặp side effect.

Phân biệt ba ID:

- `jobInstanceId`: định danh công việc logic, thường giữ nguyên qua restart.
- `jobExecutionId`: mỗi lần chạy/restart có ID mới.
- `stepExecutionId`: mỗi lần step được thực thi có ID mới; step đã hoàn thành và bị bỏ qua khi restart có thể không sinh execution mới.

Nên có một sự kiện vận hành `batch.restart.requested` chứa execution gốc, requestedBy, reasonCode và business key; tiếp theo, log `batch.step.started` của execution mới. Spring Batch không tự động ghi đầy đủ “ai bấm restart” hoặc lý do nghiệp vụ theo schema audit tùy biến; ứng dụng/scheduler cần cung cấp thông tin này.

### Không nhầm restart với start mới

Giả sử `businessDate=2026-11-16` là identifying parameter:

```java
JobParameters sameInstance = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .toJobParameters();
```

Khi job trước `FAILED`/`STOPPED` và cấu hình cho phép restart, Spring Batch có thể chạy tiếp instance đó với metadata đã lưu. Nhưng nếu mã thực thi luôn làm điều này:

```java
JobParameters newInstance = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("runId", UUID.randomUUID().toString())
    .toJobParameters();
```

Tham số `runId` identifying làm xuất hiện instance mới. Nếu không muốn vậy, hãy thiết kế identifying parameters theo kỳ dữ liệu và chính sách restart của ứng dụng. Trên Spring Batch 5.x, `JobOperator.restart(failedExecutionId)` là một cách yêu cầu restart execution theo metadata; cần cấu hình `JobOperator`/registry phù hợp và xử lý các trường hợp không thể restart. Không tự tạo parameter ngẫu nhiên để “ép chạy lại” rồi gọi đó là restart.

## 9. Đọc trạng thái restart bằng `JobExplorer`

Log có thể bị rotate hoặc mất khi process chết. Nếu cần tra cứu một execution đã tồn tại, `JobExplorer` cung cấp API đọc metadata, giúp màn hình vận hành đối chiếu trạng thái.

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class BatchExecutionInspectionService {
    private final JobExplorer jobExplorer;

    public BatchExecutionInspectionService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void inspect(long jobExecutionId) {
        JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                "Unknown jobExecutionId: " + jobExecutionId);
        }

        for (StepExecution step : execution.getStepExecutions()) {
            System.out.printf(
                "step=%s, id=%d, status=%s, read=%d, write=%d%n",
                step.getStepName(),
                step.getId(),
                step.getStatus(),
                step.getReadCount(),
                step.getWriteCount()
            );
            // Đọc có chọn lọc những context key do chính ứng dụng định nghĩa.
        }
    }
}
```

Ví dụ dùng import của Spring Batch 5.x; khi lên Spring Batch 6.x, các package core có thể thay đổi. `JobExplorer` phù hợp cho thao tác đọc. Không tự sửa `BATCH_STEP_EXECUTION_CONTEXT` hoặc `BATCH_JOB_EXECUTION.STATUS` bằng SQL để di chuyển restart point: hành động này có thể làm metadata không nhất quán và tạo mất dữ liệu/đọc lại ngoài ý muốn.

### SQL phục vụ đối chiếu execution (read-only)

Với schema JDBC phổ biến trong Spring Batch 5.x, có thể xem metadata cấp step:

```sql
SELECT
    je.JOB_EXECUTION_ID,
    ji.JOB_INSTANCE_ID,
    ji.JOB_NAME,
    je.STATUS AS job_status,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS AS step_status,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.START_TIME,
    se.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE je.JOB_EXECUTION_ID = :execution_id;
```

Các bảng `BATCH_STEP_EXECUTION_CONTEXT` và `BATCH_JOB_EXECUTION_CONTEXT` lưu snapshot context dưới dạng do serializer của framework quản lý. Không giả định có thể đọc key checkpoint bằng một câu `SELECT` JSON phổ quát trên mọi database/version. Dùng API Batch hoặc serializer phù hợp với version để truy cập, và chỉ hiển thị những key được phép xem.

## 10. Những tình huống cần xử lý riêng

### 10.1. Reader không lưu trạng thái

Một số reader không phải `ItemStream`, hoặc đã cấu hình `saveState(false)`. Khi đó `readCount` và `writeCount` vẫn xuất hiện trong step metadata, nhưng **không đồng nghĩa reader sẽ phục hồi vị trí**. Trong job yêu cầu restart, cần dùng reader có hợp đồng `open/update/close` hoặc thiết kế idempotent xử lý lại từ nguồn.

### 10.2. File input bị thay đổi giữa hai lần chạy

Với offset của file, `nextIndex=500` chỉ có nghĩa nếu file và cách parse giữ nguyên. Thay tệp nguồn nhưng giữ nguyên đường dẫn có thể khiến restart bỏ qua hoặc xử lý sai record. Nên đưa `inputFileId`, object version hoặc checksum vào dấu vết execution, giữ snapshot nguồn ổn định đến khi kết thúc kỳ xử lý.

### 10.3. Paging/cursor database và thứ tự dữ liệu

Reader đọc SQL theo trang/cursor phải có thứ tự ổn định để restart đáng tin. Nếu query thiếu `ORDER BY` xác định hoặc dữ liệu nguồn thay đổi mạnh, một offset hoặc số thứ tự đã lưu có thể trỏ tới bản ghi khác. Với `JdbcPagingItemReader`, cần cấu hình sort key có tính duy nhất và phù hợp, hiểu cơ chế restart của implementation; không tự coi số hàng đã đọc là primary key cuối.

### 10.4. Writer hoặc API bên ngoài không hỗ trợ rollback

Nếu step đã gọi API đích hoặc ghi file không nằm trong cùng transaction với metadata, rollback database chưa chắc thu hồi được side effect. Log restart point phải đi kèm khóa idempotency, transaction/outbox hoặc dấu vết xác nhận của hệ thống đích. Không tuyên bố “mọi item sau checkpoint chưa từng được xử lý” khi có side effect ngoài transaction.

### 10.5. Multi-threaded step và partitioning

Khi một step chạy nhiều thread hoặc được partition, không phải lúc nào cũng có một offset tuyến tính duy nhất. Có thể cần checkpoint theo **partition key + stepExecutionId + cursor**. Các listener có thể chạy trên thread khác nhau, counters có thể thay đổi đồng thời và log không bảo đảm thứ tự nếu backend ghi bất đồng bộ. `MDC` (Mapped Diagnostic Context) cũng không tự lan truyền qua các thread; cần cơ chế propagate context tương ứng.

Ví dụ log cho partition:

```text
event=batch.checkpoint.committed
jobExecutionId=1482
stepExecutionId=3420
partition=region-HCM
cursor=orderId:45000
```

Chỉ log `cursor=45000` không có partition/step identity sẽ khó biết con số thuộc dữ liệu nào. Khi dùng remote chunking, worker và manager còn cần một correlation ID hoặc chunk/partition ID thống nhất để nối log.

### 10.6. Tasklet step không xử lý item theo chunk

Một tasklet có thể thực hiện công việc nguyên khối, cập nhật cờ hoặc business operation tùy chỉnh. `readCount`/`writeCount` có thể bằng 0 dù công việc đã hoàn tất. Với tasklet restartable, log mốc phục hồi có thể là `stage=UPLOAD_DONE`, `lastPageToken` hoặc mã giao dịch được lưu bền vững. Vị trí lưu trạng thái cần khớp chiến lược transaction và idempotency của tasklet, không áp dụng máy móc offset dòng của file.

### 10.7. Step đã hoàn tất trước khi job lỗi

Job gồm `extractStep -> transformStep -> publishStep`. Nếu `publishStep` thất bại sau khi hai step trước đã `COMPLETED`, restart có thể bỏ qua các step trước và thực thi lại step lỗi. Restart point ở đây vừa là **danh sách step đã hoàn tất** vừa là context của step đang phải tiếp tục. Log nên thể hiện luồng job và step đã skip khi restart, tránh cho rằng mọi bước đều phải mở lại offset.

### 10.8. Lỗi trước checkpoint đầu tiên

Nếu job chết trước commit đầu tiên, context có thể chỉ có trạng thái khởi đầu hoặc chưa có key. Log nên hiển thị `restoredCursor=unknown` hay trạng thái khởi đầu được định nghĩa bởi reader. Không tự suy diễn phải bắt đầu tại item đầu tiên nếu có tác động bên ngoài đã xảy ra trước transaction rollback.

## 11. Log restart point và bảo mật

`ExecutionContext` và `JobParameters` có thể chứa tên file, token truy cập, thông tin khách hàng hoặc dữ liệu trung gian. Việc log toàn bộ context bằng `context.toString()` hoặc serialize mọi key là một rủi ro đáng kể.

Hãy ưu tiên:

- **Định danh kỹ thuật:** `jobExecutionId`, `stepExecutionId`, `jobName`, `businessDate`, `partitionId` và reader name.
- **Checkpoint không nhạy cảm:** chỉ số, offset, id bản ghi dạng mã tham chiếu nếu được phép.
- **Mã lỗi và nhóm lỗi:** `READ_TIMEOUT`, `INVALID_FORMAT`, `CONSTRAINT_VIOLATION`; tránh payload nguyên văn.
- **Trace/correlation ID:** nối log với scheduler và worker mà không cần sao chép dữ liệu đầu vào.
- **Sampling/throttling:** giảm khối lượng log với chunk rất nhỏ, nhưng giữ các event bắt đầu, lỗi và kết thúc.

Nếu khóa bản ghi chứa dữ liệu nhạy cảm, sử dụng mã tham chiếu nội bộ hoặc hash/token theo chính sách của tổ chức. Đối với yêu cầu audit, log có thể được trích xuất sang hệ thống tập trung có retention và quyền truy cập riêng; không giả định log INFO là kho bằng chứng bất biến.

## 12. Kịch bản kiểm thử restart logging

Một bài integration test hữu ích phải tạo **thất bại thực sự sau ít nhất một commit**, rồi chạy lại cùng `JobInstance` và kiểm tra cả dữ liệu lẫn checkpoint. Dùng database thử nghiệm và fixture ổn định, không thao tác trên metadata production.

### Bố trí kịch bản

Giả sử có năm đơn hàng và chunk size 2:

| Pha | Hành động | Kết quả kỳ vọng |
| --- | --- | --- |
| First execution | Chunk #1 ghi A001, A002 thành công | Data output có 2 mã, checkpoint `nextIndex=2` |
| First execution | Chunk #2 cố ghi A003, A004 nhưng writer ném lỗi trước commit | Execution `FAILED`, transaction chunk #2 rollback, checkpoint persist vẫn là `2` |
| Restart | Cùng identifying `JobParameters`, reader mới mở context đã lưu | Log `restoredCursor=2`, reader tiếp tục từ A003 |
| Restart | Writer không còn lỗi và hoàn tất A003, A004, A005 | Execution mới `COMPLETED`, output có 5 mã không trùng |
| Đối chiếu | Kiểm tra `JobRepository`, output và log | Cùng `JobInstance`, hai `JobExecution`; log checkpoint hợp với dữ liệu commit |

Phần writer giả lập nên có cơ chế lỗi **một lần có chủ đích** và chuyển trạng thái khi restart. Với writer SQL, dùng transaction manager đúng datasource, unique key hoặc idempotent upsert; nếu writer gọi API ngoài transaction, cần mở rộng assertions để phát hiện tác động trùng.

### Ví dụ phần kiểm tra trạng thái

Đoạn sau minh họa các assertions có thể dùng sau khi test đã khởi chạy thất bại rồi restart (Spring Batch 5.x). `first`, `restarted`, `jdbcTemplate` là các đối tượng đã được test chuẩn bị:

```java
assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(restarted.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThat(restarted.getJobInstance().getId())
    .isEqualTo(first.getJobInstance().getId());

assertThat(restarted.getId()).isNotEqualTo(first.getId());

List<String> result = jdbcTemplate.queryForList(
    "SELECT order_code FROM imported_orders ORDER BY order_code",
    String.class
);
assertThat(result).containsExactly("A001", "A002", "A003", "A004", "A005");
```

Để kiểm tra log, có thể dùng capture appender hoặc `OutputCaptureExtension` trong Spring Boot Test. Assert sự kiện `batch.checkpoint.committed` sau chunk đầu, `batch.step.finished status=FAILED` sau lần chạy lỗi và `batch.step.started restoredCursor=2` sau restart. Tuy nhiên **thành công của test phải dựa vào output và metadata**, không chỉ đối chiếu chuỗi log, vì chính log có thể ghi sai hoặc bị mất khi tiến trình dừng đột ngột.

### Trường hợp biên nên thử

1. Lỗi trước checkpoint đầu tiên: `ExecutionContext` không có offset đã commit.
2. Lỗi sau một hoặc nhiều chunk đã commit: restart tiếp tục từ mốc cuối hợp lệ.
3. Lỗi đúng ranh giới chunk hoặc trong `ItemStream.update()`: rollback không tạo ra checkpoint giả.
4. Bị `STOPPED` thay vì `FAILED`: kiểm tra chính sách restart và log trạng thái.
5. Reader `saveState(false)`: không kỳ vọng resume từ offset cũ.
6. Input thay đổi hoặc bị thay thế: xác nhận cơ chế phát hiện version/checksum trước khi restart.
7. Nhiều partition: log và checkpoint được phân biệt cho từng partition/step execution.

## 13. Các lỗi logging và restart point thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log `readCount=570`, restart từ item 501 | Có 70 item đã đọc trong chunk rollback; read count không phải checkpoint persist | Log mốc sau commit và đọc context đã lưu |
| Log “checkpoint committed” ngay sau `read()` | Callback xảy ra trước writer/commit | Đổi thành event read progress; log committed ở `afterChunk` |
| `restoredCursor=unknown` dù dự kiến restart | Reader chưa lưu state, key sai, không đăng ký `ItemStream`, hoặc instance mới | Kiểm tra `saveState`, reader name, đăng ký stream và identifying parameters |
| Restart đọc lại toàn bộ input | Mỗi lần launch có UUID identifying mới hoặc context không được persist | Giữ cùng `JobInstance` cho restart; xác minh repository/context |
| Reader bỏ qua record sau restart | Offset được lưu sai hoặc nguồn input thay đổi | Kiểm tra `open/update`, transaction, input version, sort/order |
| Writer tạo dữ liệu trùng dù restart đúng offset | Side effect ngoài transaction hoặc writer không idempotent | Thiết kế unique key, outbox, deduplication và reconciliation |
| Một con số cursor được log cho nhiều partition | Thiếu partition ID/stepExecutionId | Log checkpoint theo từng partition |
| Thực thi thất bại nhưng không có log kết thúc | JVM/Pod chết trước listener cuối, log buffer chưa flush | Đối chiếu JobRepository và heartbeat/monitoring |
| Log quá lớn làm batch chậm | Ghi từng item/chunk rất nhỏ ở INFO | Giảm tần suất; dùng metrics cho thống kê liên tục |
| Mất dữ liệu khi “sửa” context bằng tay | Chỉnh `BATCH_*` hoặc trạng thái checkpoint trực tiếp | Dùng API restart, phục hồi theo quy trình kiểm soát |
| Lộ thông tin bí mật trong log | In toàn bộ `ExecutionContext` hoặc tham số nhạy cảm | Whitelist field được phép log và redact |

## 14. Quy trình vận hành khi có job thất bại

Khi một job `FAILED` hoặc dừng bất thường, có thể đi theo chuỗi điều tra sau:

1. **Tìm đúng execution:** xác định `jobName`, `jobExecutionId`, business key và mã nguồn input.
2. **Xác định step lỗi:** tra `StepExecution` cùng `BatchStatus`, `ExitStatus`, thời gian, exception và skip/rollback counts.
3. **Đọc checkpoint bền vững:** đối chiếu trạng thái step execution trong `JobRepository`, các key `ExecutionContext` mà reader có trách nhiệm lưu, và log commit gần nhất.
4. **Kiểm tra output đã commit:** database/file/API có những tác động nào từ các chunk thành công; có side effect nào chưa phản ánh trong repository không.
5. **Xác định chiến lược khôi phục:** restart cùng instance, chạy lại từ đầu có kiểm soát, hay cần đối soát thủ công. Không thay identifying parameters chỉ để vượt qua lỗi start.
6. **Quan sát execution tiếp theo:** log restored cursor, ID execution mới, counters và dữ liệu đầu ra; xác nhận không mất/trùng bản ghi.

Với một hệ thống quan trọng, nên có dashboard nối `JobExecution` cũ và mới theo `JobInstance`, hiển thị commit gần nhất, business key và tình trạng output. Khi log và repository không khớp sau crash, ưu tiên phân tích metadata đã persist cùng bằng chứng commit của hệ thống đích; log có thể mất hoặc được ghi trước khi transaction kết thúc.

## 15. Kết luận

`Log restart point` là kỹ thuật quan sát quá trình phục hồi Spring Batch. **Reader/step lưu trạng thái vào `ExecutionContext`, `JobRepository` persist checkpoint, còn log giúp người vận hành hiểu trạng thái đó và đối chiếu dữ liệu đã commit.** Một thiết kế tốt ghi rõ danh tính job/step execution, kỳ dữ liệu, checkpoint theo reader, counters và trạng thái lỗi; ghi sự kiện sau commit khi phù hợp; bảo vệ dữ liệu nhạy cảm; và kiểm chứng restart bằng integration test có failure thực tế.

Điểm cốt lõi là **không dùng số item cuối đã đọc hoặc một dòng log ngẫu nhiên làm “nguồn sự thật” cho vị trí tiếp tục**. Điểm restart phải phù hợp với metadata bền vững, transaction và chiến lược idempotency của toàn bộ pipeline.

## Tài liệu tham khảo

- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): vòng đời chunk và commit transaction.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): hợp đồng `open`, `update`, `close` và lưu checkpoint qua `ExecutionContext`.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobInstance`, `JobExecution`, restart và cấu hình job.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng metadata của `JobRepository`, đặc biệt step execution context.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): theo dõi execution và metrics của batch.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): kiểm thử job/step, failure và restart.
