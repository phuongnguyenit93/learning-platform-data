# Listener không được che lỗi chính

Trong Spring Batch, listener cho phép quan sát và phản ứng với các sự kiện trong vòng đời job, step, chunk và item. Ví dụ, `ItemWriteListener` có thể ghi log khi writer thất bại, `SkipListener` có thể lưu thông tin bản ghi bị bỏ qua, còn `StepExecutionListener` có thể tổng hợp số liệu sau khi step kết thúc.

Listener thường chạy sát với luồng xử lý chính. Vì vậy, một lỗi phát sinh trong listener có thể xuất hiện đúng lúc reader, processor, writer hoặc step đang xử lý một lỗi khác. Nếu listener ném một exception mới trong callback xử lý lỗi, exception mới có thể làm lu mờ nguyên nhân ban đầu. Người vận hành nhìn thấy lỗi audit/logging thay vì lỗi database, dữ liệu hoặc nghiệp vụ đã khiến job thất bại.

Nguyên tắc quan trọng là **không để lỗi phụ trong listener che mất lỗi chính**. Listener cần giữ nguyên exception gốc, bổ sung thông tin chẩn đoán một cách an toàn và có chính sách rõ ràng cho những tác vụ listener thực hiện. Với side effect bắt buộc phải thành công, hãy đặt nó trong luồng nghiệp vụ có transaction và retry phù hợp thay vì dựa vào callback quan sát.

## Lỗi chính và lỗi phụ trong batch processing

Giả sử `ItemWriter` ghi một chunk vào database nhưng database ném `DeadlockLoserDataAccessException`. Spring Batch nhận lỗi này để rollback transaction, retry hoặc đánh dấu step thất bại theo cấu hình.

Trong lúc xử lý lỗi, `ItemWriteListener.onWriteError` được gọi để ghi audit. Nếu dịch vụ audit cũng gặp lỗi và listener ném `RuntimeException("Cannot write audit")`, log hoặc trạng thái lỗi có thể tập trung vào exception của listener. Nguyên nhân ban đầu là deadlock dễ bị che khuất hoặc khó truy vết.

```text
ItemWriter ghi chunk
        |
        v
Database ném lỗi deadlock       <- lỗi chính
        |
        v
onWriteError(exception, chunk)
        |
        v
Listener ghi audit
        |
        +---- audit thành công: giữ nguyên lỗi writer
        |
        +---- audit thất bại: lỗi phụ
                    |
                    v
           Gắn lỗi phụ vào lỗi gốc
           bằng addSuppressed(...)
                    |
                    v
           Để framework xử lý lỗi writer
```

Hai lỗi có vai trò khác nhau:

| Loại lỗi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Lỗi chính (primary exception) | Writer deadlock, processor dữ liệu sai, reader mất kết nối | Giữ nguyên để Spring Batch áp dụng rollback, retry, skip hoặc đánh dấu thất bại |
| Lỗi phụ (secondary exception) | Ghi audit thất bại, metrics backend không phản hồi, gửi thông báo lỗi thất bại | Ghi nhận bổ sung mà không thay thế lỗi chính, trừ khi nghiệp vụ quy định rõ listener operation là điều kiện bắt buộc |

Không phải mọi lỗi listener đều là lỗi phụ. Nếu listener thực hiện một kiểm tra bắt buộc quyết định dữ liệu có được xử lý hay không, lỗi của nó có thể là lỗi chính của thao tác đó. Điều cần tránh là vô tình thay thế exception đã xảy ra trước bằng một exception khác trong lúc xử lý lỗi.

## Các callback listener và thời điểm xảy ra lỗi

Spring Batch có nhiều loại listener. Cần hiểu callback nào được gọi trước/sau thao tác chính và callback nào được gọi khi có exception.

| Listener | Callback liên quan | Mục đích |
| --- | --- | --- |
| `ItemReadListener` | `beforeRead`, `afterRead`, `onReadError` | Quan sát thao tác đọc từng item và lỗi đọc |
| `ItemProcessListener` | `beforeProcess`, `afterProcess`, `onProcessError` | Quan sát transformation và lỗi processor |
| `ItemWriteListener` | `beforeWrite`, `afterWrite`, `onWriteError` | Quan sát ghi chunk và lỗi writer |
| `SkipListener` | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Ghi nhận item cuối cùng được skip theo skip policy |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Quan sát vòng đời chunk |
| `StepExecutionListener` | `beforeStep`, `afterStep` | Xử lý trước và sau step, đọc hoặc bổ sung exit status |
| `JobExecutionListener` | `beforeJob`, `afterJob` | Xử lý trước và sau job execution |

Các callback không có cùng transaction boundary. Ví dụ, `afterChunk` được gọi sau khi chunk đã commit; một lỗi trong callback này không thể rollback phần dữ liệu đã commit. Ngược lại, một số callback item nằm trong quá trình xử lý chunk và lỗi của chúng có thể làm chunk thất bại tùy vị trí gọi và cơ chế transaction.

Vì vậy, không nên coi mọi listener là một hook có cùng khả năng rollback. Khi triển khai, cần xác định callback được gọi ở thời điểm nào, lỗi của nó được framework xử lý ra sao và side effect của listener có thể lặp lại hay không.

## Vì sao error listener cần giữ nguyên exception gốc?

Các callback như `onReadError`, `onProcessError` và `onWriteError` được gọi khi thao tác chính đã ném exception. Callback nhận được exception đó để ghi log, metrics hoặc thông tin chẩn đoán.

Nếu callback tự ném exception khác, có thể xuất hiện các vấn đề:

- Stack trace hiển thị lỗi audit hoặc logging thay vì lỗi reader/processor/writer.
- Phân loại retry/skip không còn dựa trên exception ban đầu như dự kiến.
- Skip policy có thể không nhận đúng loại exception mà ứng dụng đã cấu hình.
- Nguyên nhân gốc khó tìm trong log khi job chạy trên nhiều node.
- Một lỗi phụ tạm thời ở hệ thống quan sát có thể làm gián đoạn xử lý chính.

Ví dụ không nên dùng:

```java
@Override
public void onWriteError(Exception exception, Chunk<? extends Order> items) {
    auditService.recordFailure(items);
    throw new IllegalStateException("Could not record write failure");
}
```

Nếu `recordFailure` ném exception, listener kết thúc trước khi xử lý được thông tin gốc. Nếu listener tiếp tục ném `IllegalStateException`, exception mới có thể trở thành lỗi mà framework quan sát ở callback này.

Error listener nên cố gắng ghi nhận lỗi phụ nhưng giữ nguyên exception được truyền vào. Nếu việc ghi nhận phụ thất bại, thêm exception phụ vào lỗi gốc bằng `Throwable.addSuppressed(...)` rồi để luồng xử lý tiếp tục theo exception ban đầu.

## Mẫu an toàn: ghi nhận lỗi phụ bằng addSuppressed

Java cung cấp `Throwable.addSuppressed(Throwable)` để gắn một exception phụ vào exception chính. Khi stack trace được in, suppressed exception vẫn xuất hiện cùng lỗi gốc.

Ví dụ với `ItemWriteListener`:

```java
public class OrderWriteListener implements ItemWriteListener<Order> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderWriteListener.class);

    private final FailureAuditService auditService;

    public OrderWriteListener(FailureAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onWriteError(
            Exception primaryException,
            Chunk<? extends Order> items) {

        try {
            auditService.recordWriteFailure(items, primaryException);
        } catch (RuntimeException auditException) {
            primaryException.addSuppressed(auditException);
            log.error(
                    "Could not record write failure; preserving the original writer exception",
                    auditException);
        }
    }
}
```

Trong ví dụ:

- `primaryException` là exception writer đã ném.
- Listener thử ghi audit để bổ sung thông tin.
- Nếu audit thất bại, exception audit được gắn vào exception gốc.
- Listener không ném exception audit ra ngoài để thay thế lỗi writer.
- Spring Batch tiếp tục xử lý lỗi writer theo cấu hình retry, skip hoặc rollback.

Chỉ bắt loại exception mà listener dự kiến có thể xử lý, thường là `RuntimeException` từ dịch vụ audit. Không nên bắt `Throwable` một cách rộng rãi vì có thể nuốt cả lỗi nghiêm trọng của JVM như `OutOfMemoryError`.

### Dùng helper để thống nhất cách xử lý

Nếu nhiều listener cùng ghi audit, có thể tạo helper dùng chung:

```java
public final class ListenerFailureSupport {

    private static final Logger log =
            LoggerFactory.getLogger(ListenerFailureSupport.class);

    private ListenerFailureSupport() {
    }

    public static void runSafely(
            Throwable primaryException,
            String operation,
            Runnable action) {

        try {
            action.run();
        } catch (RuntimeException secondaryException) {
            primaryException.addSuppressed(secondaryException);
            log.error(
                    "Listener operation '{}' failed; primary exception is preserved",
                    operation,
                    secondaryException);
        }
    }
}
```

Listener có thể gọi helper:

```java
@Override
public void onProcessError(OrderInput item, Exception primaryException) {
    ListenerFailureSupport.runSafely(
            primaryException,
            "record-process-failure",
            () -> auditService.recordProcessFailure(item, primaryException));
}
```

Helper giúp quy tắc xử lý lỗi phụ nhất quán giữa các listener. Nó không thay thế logging/monitoring của Spring Batch; nó bổ sung thông tin nếu chính thao tác ghi nhận lỗi cũng thất bại.

## Không che lỗi bằng cách catch rồi bỏ qua

Một cách xử lý nguy hiểm khác là bắt exception trong listener hoặc trong tasklet rồi chỉ ghi log:

```java
try {
    writer.write(chunk);
} catch (Exception ex) {
    log.error("Write failed", ex);
    // Không ném lại exception
}
```

Nếu exception bị nuốt và phương thức trả về bình thường, Spring Batch có thể xem thao tác là thành công, tiếp tục cập nhật metadata và commit transaction theo luồng hiện tại. Khi đó, step có thể hoàn thành dù dữ liệu chưa được ghi đầy đủ.

Trong listener, đặc biệt là callback error, không nên tự gọi lại writer hoặc biến lỗi thành kết quả thành công. Listener quan sát lỗi; framework và cấu hình fault tolerance chịu trách nhiệm điều phối retry/skip. Nếu lỗi chính không thể phục hồi, phải để nó tiếp tục được truyền tới framework.

Nếu cần chuyển exception sang loại nghiệp vụ khác, phải giữ nguyên nguyên nhân bằng cause:

```java
throw new BatchProcessingException(
        "Could not process order " + orderId,
        originalException);
```

Chỉ làm việc này ở nơi có chủ đích phân loại exception. Không bọc lỗi gốc bằng exception của thao tác audit/logging.

## Phân biệt error callback và SkipListener

`onReadError`, `onProcessError` và `onWriteError` được gọi khi thao tác tương ứng gặp exception. Nếu step được cấu hình retry, một lỗi có thể được thử lại nhiều lần; error callback có thể được gọi cho từng lần lỗi.

`SkipListener` có mục đích khác: nó nhận thông tin khi một item thực sự được skip theo skip policy, tức là ứng dụng quyết định bỏ qua item sau khi áp dụng các quy tắc retry/skip.

| Callback | Thời điểm/ý nghĩa | Sử dụng phù hợp |
| --- | --- | --- |
| `onProcessError` | Processor ném exception | Chẩn đoán một lần xử lý lỗi; có thể được gọi lại trong quá trình retry |
| `onWriteError` | Writer ném exception | Ghi nhận lỗi của lần ghi chunk; cần phân biệt retry với lỗi cuối cùng |
| `onSkipInProcess` | Item bị skip sau khi áp dụng skip policy | Lưu bản ghi reject cuối cùng hoặc audit quyết định skip |
| `onSkipInWrite` | Item bị skip trong giai đoạn ghi | Ghi nhận item không được ghi sau khi chính sách skip chấp nhận |

Nếu mục tiêu là lưu một bản ghi reject khi item đã được quyết định skip, `SkipListener` thường phù hợp hơn việc ghi một bản ghi lỗi cuối cùng trong mỗi `onProcessError`. Nếu ghi audit trong error callback, cần tránh tạo nhiều audit record cho cùng một item qua các lần retry.

Các phương thức `SkipListener` có thể được gọi gần thời điểm commit của chunk theo lifecycle Spring Batch. Nếu listener ghi reject record vào cùng transaction resource, record có thể được commit cùng chunk. Nếu ghi sang hệ thống ngoài, side effect đó không tự động rollback và vẫn cần idempotency.

## Retry có thể gọi listener nhiều lần

Một lỗi tạm thời có thể được retry. Ví dụ writer gặp deadlock ở lần đầu, retry lần hai thành công. `onWriteError` có thể đã được gọi cho lần đầu dù chunk cuối cùng hoàn tất.

Nếu listener gửi email hoặc tạo ticket cho mọi lần `onWriteError`, hệ thống có thể tạo nhiều thông báo cho một sự cố tạm thời đã được retry thành công.

Hãy phân biệt:

- **Attempt failure:** một lần thử đọc/process/write thất bại.
- **Final skip:** item được skip sau khi hết retry hoặc theo skip policy.
- **Step failure:** step không thể hoàn tất và chuyển sang trạng thái lỗi.

Chọn callback theo ý nghĩa cần ghi nhận. Nếu muốn đo số lần retry, error callback là nơi phù hợp. Nếu muốn ghi reject record cho item bị bỏ qua cuối cùng, dùng `SkipListener`. Nếu muốn gửi một thông báo tổng kết về step thất bại, cân nhắc `StepExecutionListener` hoặc `JobExecutionListener` với trạng thái cuối.

Khi tạo audit record, nên dùng khóa idempotent như job execution ID, step execution ID, item business key và loại sự kiện. Nếu callback được gọi lại, khóa này giúp tránh tạo dữ liệu trùng.

## Transaction boundary của listener

Một lỗi listener có thể xảy ra trước, trong hoặc sau transaction chính. Cần biết thời điểm callback để hiểu tác động.

| Callback | Vị trí tương đối | Hệ quả cần lưu ý |
| --- | --- | --- |
| `beforeChunk` | Sau khi transaction chunk bắt đầu, trước khi xử lý chunk | Lỗi callback có thể làm chunk thất bại và transaction rollback |
| `afterWrite` | Sau thao tác writer trong quá trình xử lý chunk | Lỗi callback có thể làm chunk hiện tại thất bại trước commit |
| `afterChunk` | Sau khi chunk đã commit | Lỗi callback không thể rollback chunk đã commit; side effect cần idempotent |
| `afterChunkError` | Đường xử lý chunk error/rollback | Không được thay thế exception gốc bằng lỗi ghi nhận phụ |
| `afterStep` | Khi step đã hoàn tất phần xử lý chính | Không phải nơi thích hợp để thực hiện business write cần cùng transaction với chunk |
| `afterJob` | Sau khi job execution kết thúc | Thích hợp cho tổng kết/notification; không nên coi là transaction của các step |

Chi tiết transaction và cách framework xử lý exception của từng callback phụ thuộc listener type và phiên bản Spring Batch. Nguyên tắc an toàn là không dựa vào một callback sau commit để rollback dữ liệu đã commit, và không giả định listener lifecycle nằm trong cùng transaction với mọi thao tác nghiệp vụ.

### Đặc biệt với afterChunk

`afterChunk` được gọi sau khi chunk transaction đã commit. Nếu listener thất bại khi gửi metrics hoặc thông báo sau commit, dữ liệu chunk đã ghi vẫn còn. Việc retry step hoặc restart sau lỗi listener có thể khiến ứng dụng gặp lại chunk hoặc bước tiếp theo tùy checkpoint và trạng thái đã lưu.

Vì vậy, callback `afterChunk` nên thực hiện tác vụ quan sát nhẹ, có khả năng lặp an toàn. Nếu phải gửi một event quan trọng tương ứng với dữ liệu vừa commit, hãy cân nhắc transactional outbox thay vì gửi trực tiếp trong callback sau commit.

### Đặc biệt với afterStep

`StepExecutionListener.afterStep` trả về `ExitStatus` và có thể bổ sung hoặc thay đổi exit code để điều khiển flow. Trong lifecycle của Spring Batch, exception phát sinh từ callback `afterStep` được framework ghi nhận như lỗi callback; không nên dựa vào việc ném exception ở đây để rollback các chunk đã commit hoặc bảo đảm step chuyển thành thất bại theo cách mong muốn.

Nếu kết quả kiểm tra sau step cần điều khiển luồng job, hãy trả về một `ExitStatus` rõ ràng và cấu hình transition tương ứng. Ví dụ:

```java
public class ValidationSummaryListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getFilterCount() > 1_000) {
            return new ExitStatus("FILTER_LIMIT_EXCEEDED");
        }
        return null;
    }
}
```

Flow có thể xử lý exit code đó:

```java
return new JobBuilder("importJob", jobRepository)
        .start(importStep)
            .on("FILTER_LIMIT_EXCEEDED").fail()
        .from(importStep)
            .on("*").to(summaryStep)
        .end()
        .build();
```

Ví dụ minh họa việc dùng exit code để định tuyến flow; cần cấu hình đúng các transition cho mọi trạng thái còn lại trong job. Nếu điều kiện kiểm tra là điều kiện nghiệp vụ bắt buộc trước khi ghi dữ liệu, nên thực hiện validation trong tasklet/processor hoặc một step validation riêng thay vì đợi `afterStep`.

## Listener quan sát và listener thực hiện nghiệp vụ

Một listener nên có trách nhiệm nhỏ, dễ dự đoán. Có thể chia theo mức độ quan trọng của công việc:

| Loại công việc | Ví dụ | Cách thiết kế |
| --- | --- | --- |
| Quan sát | Log thời gian, tăng metrics, trace execution ID | Nên tránh làm thất bại job chỉ vì backend quan sát tạm thời không khả dụng |
| Chẩn đoán lỗi | Ghi exception, item key và step ID | Giữ exception gốc; lỗi ghi nhận là suppressed hoặc được gửi tới kênh dự phòng |
| Audit bắt buộc | Ghi nhận quyết định skip hoặc thay đổi nghiệp vụ phải kiểm toán | Dùng transaction/resource phù hợp, idempotency và quy tắc fail rõ ràng |
| Business operation | Cập nhật trạng thái, tạo dữ liệu, gửi lệnh quan trọng | Đặt trong tasklet/processor/writer hoặc service nghiệp vụ được điều phối bởi transaction |
| Điều khiển flow | Chọn exit code sau step | Trả `ExitStatus` tường minh và khai báo transition |

Nếu listener phải thực hiện một thay đổi dữ liệu mà job không được phép bỏ qua, hãy cân nhắc đưa thay đổi đó vào writer hoặc tasklet. Khi đó exception trở thành lỗi của thao tác nghiệp vụ, có thể được quản lý bằng transaction và fault tolerance rõ ràng.

Không nên dùng `afterJob` để thực hiện một cập nhật database bắt buộc rồi giả định cập nhật đó sẽ rollback cùng job. Các step có thể đã commit từ trước và job listener chạy ở giai đoạn lifecycle khác.

## Ghi audit lỗi mà không thay thế lỗi chính

Một audit record nên lưu đủ thông tin để truy vết mà không cần nhúng toàn bộ payload hoặc secret.

Các trường thường hữu ích:

- Job name và `jobExecutionId`.
- Step name và `stepExecutionId`.
- Loại callback hoặc giai đoạn xử lý.
- Business key của item hoặc định danh chunk nếu có.
- Tên class của exception chính và thông điệp đã được lọc dữ liệu nhạy cảm.
- Correlation ID hoặc trace ID.
- Thời điểm và số lần attempt nếu ứng dụng theo dõi được.

Không nên log toàn bộ entity, token, thông tin xác thực hoặc dữ liệu cá nhân chỉ để phục vụ debug. Nếu audit database không khả dụng, ghi lỗi phụ vào suppressed exception và logger/monitoring dự phòng, đồng thời giữ exception chính cho Spring Batch.

Ví dụ một listener xử lý lỗi processor:

```java
public class OrderProcessListener
        implements ItemProcessListener<OrderInput, Order> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderProcessListener.class);

    private final FailureAuditService auditService;

    public OrderProcessListener(FailureAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onProcessError(OrderInput item, Exception primaryException) {
        try {
            auditService.recordProcessFailure(
                    item.orderId(),
                    primaryException.getClass().getName(),
                    primaryException.getMessage());
        } catch (RuntimeException auditException) {
            primaryException.addSuppressed(auditException);
            log.error(
                    "Failure audit unavailable for order {}; original processing error is preserved",
                    item.orderId(),
                    auditException);
        }
    }
}
```

Listener không ném lại `primaryException` vì framework đã có exception đó và sẽ tiếp tục xử lý nó sau callback. Listener chỉ bảo đảm rằng lỗi audit không thay thế exception ban đầu.

## Khi nào listener failure phải làm job thất bại?

Có trường hợp lỗi trong listener không thể được xem là phụ. Ví dụ, một listener xác nhận điều kiện bảo mật hoặc audit bắt buộc trước khi cho phép bước tiếp theo. Nếu thao tác đó thất bại, ứng dụng có thể cần dừng job.

Hãy làm rõ hợp đồng:

1. Nếu listener chỉ ghi metrics hoặc log, lỗi thường nên fail-open: ghi nhận lỗi phụ và giữ luồng chính.
2. Nếu audit là yêu cầu bắt buộc, hãy dùng một thao tác nghiệp vụ có transaction và exception policy rõ ràng; không dựa vào callback error để thực hiện audit bắt buộc.
3. Nếu kết quả listener dùng để điều khiển flow sau step, trả `ExitStatus` cụ thể và cấu hình transition.
4. Nếu callback chạy sau commit, xác định cách phục hồi vì dữ liệu đã commit không thể rollback.

Không nên tự động nuốt mọi exception listener. Fail-open chỉ phù hợp với tác vụ phụ không quyết định tính đúng đắn của business data. Với công việc bắt buộc, hãy làm cho lỗi đó trở thành một phần minh bạch của luồng xử lý chính.

## Logging exception đúng cách

Log listener nên giúp tìm nguyên nhân mà không tạo thêm nhiễu.

- Ghi exception gốc cùng stack trace ở nơi framework hoặc error handler có trách nhiệm ghi nhận.
- Nếu lỗi phụ xảy ra, log nó kèm job/step execution ID và ghi rõ đây là lỗi trong listener.
- Tránh log cùng stack trace nhiều lần ở mọi callback nếu framework đã ghi đầy đủ.
- Không log toàn bộ payload hoặc dữ liệu nhạy cảm.
- Dùng structured logging để lọc theo job name, step name, execution ID, business key và correlation ID.
- Giữ suppressed exception khi truyền lỗi tới nơi xử lý cuối cùng để cả nguyên nhân chính và lỗi phụ đều có thể được chẩn đoán.

Ví dụ log có cấu trúc:

```java
log.error(
        "Listener audit failed: jobExecutionId={}, stepExecutionId={}, itemKey={}",
        jobExecutionId,
        stepExecutionId,
        itemKey,
        auditException);
```

Thông điệp nên phân biệt rõ `primaryException` và `auditException`. Điều này đặc biệt quan trọng khi nhiều job chạy đồng thời trên nhiều node.

## Listener và retry, skip, rollback

Listener có thể được gọi nhiều lần tùy vị trí callback và chính sách fault tolerance. Cần tránh để tác vụ listener tạo side effect trùng lặp.

| Tình huống | Hành vi cần dự kiến |
| --- | --- |
| Processor lỗi và được retry | `onProcessError` có thể được gọi cho các attempt lỗi; không tạo audit cuối cùng trùng cho mỗi attempt nếu chỉ cần một reject record |
| Writer lỗi và chunk rollback | `onWriteError` quan sát lỗi; side effect ngoài transaction của listener có thể vẫn tồn tại |
| Item cuối cùng bị skip | `SkipListener` phù hợp để ghi nhận quyết định skip cuối cùng |
| Chunk commit rồi `afterChunk` lỗi | Business data của chunk đã commit; listener không thể rollback nó |
| Step kết thúc rồi `afterStep` lỗi | Không thể rollback các chunk đã commit trước đó; dùng exit status/flow hoặc xử lý nghiệp vụ phù hợp |

Nếu listener ghi audit vào cùng database transaction, cần xác nhận nó thực sự dùng cùng transaction manager và resource. Nếu listener gửi email, HTTP request hoặc message, transaction database không tự thu hồi side effect đó.

Với side effect cần giao hàng đáng tin cậy sau commit, transactional outbox thường phù hợp hơn: ghi event vào bảng outbox trong transaction business, sau đó publisher độc lập gửi event và retry bằng event ID ổn định.

## Kiểm thử listener không che lỗi chính

Nên kiểm thử cả trường hợp listener thành công lẫn trường hợp chính listener thất bại.

### Error callback và lỗi audit phụ

Tạo một writer hoặc processor ném exception xác định. Cho audit service trong listener cũng ném exception. Xác nhận:

- Exception gốc vẫn là exception được framework xử lý.
- Exception audit xuất hiện trong `getSuppressed()` của exception gốc nếu được gắn bằng `addSuppressed`.
- Retry/skip policy vẫn nhìn thấy đúng loại exception chính.
- Log thể hiện rõ lỗi audit là lỗi phụ.

Ví dụ unit test helper:

```java
@Test
void keepsPrimaryExceptionWhenListenerActionFails() {
    RuntimeException primary = new RuntimeException("database deadlock");
    RuntimeException secondary = new RuntimeException("audit database unavailable");

    ListenerFailureSupport.runSafely(
            primary,
            "record-failure",
            () -> { throw secondary; });

    assertEquals("database deadlock", primary.getMessage());
    assertEquals(1, primary.getSuppressed().length);
    assertSame(secondary, primary.getSuppressed()[0]);
}
```

### Listener sau commit

Cho `afterChunk` ném lỗi có kiểm soát sau khi chunk commit. Xác nhận business data đã commit vẫn tồn tại và quy trình restart/điều tra xử lý trạng thái step phù hợp. Test này giúp tránh giả định rằng lỗi callback sau commit có thể rollback chunk.

### SkipListener

Tạo item bị skip theo policy và xác nhận audit skip được ghi đúng một lần theo hợp đồng ứng dụng. Kiểm tra retry trước khi skip để bảo đảm error callback không tạo reject record trùng.

### afterStep và ExitStatus

Kiểm tra listener trả custom exit code và job flow định tuyến đúng. Nếu callback có lỗi phụ, xác nhận chính sách logging/monitoring không làm mất trạng thái lỗi chính của step.

### Side effect ngoài transaction

Giả lập listener gửi message thành công rồi chunk hoặc step thất bại. Xác nhận message không tự rollback và consumer/outbox có cơ chế idempotency phù hợp.

## Các lỗi thiết kế thường gặp

### Ném exception mới trong onError callback

Lỗi ghi audit hoặc gửi thông báo thay thế exception reader/processor/writer. Giữ exception gốc và gắn lỗi phụ bằng `addSuppressed`.

### Nuốt exception của thao tác chính

Catch exception rồi chỉ log có thể khiến framework xem chunk/tasklet thành công. Để lỗi chính tiếp tục tới Spring Batch nếu thao tác không thể hoàn thành đúng.

### Ghi audit cuối cùng trong mỗi lần retry

Error callback có thể được gọi nhiều lần. Dùng attempt metrics cho từng lần thử; dùng `SkipListener` hoặc một khóa idempotent cho quyết định skip cuối cùng.

### Dùng afterChunk để làm business operation bắt buộc

Callback này chạy sau commit. Nếu thao tác thất bại, dữ liệu chunk đã commit không thể rollback. Dùng writer/outbox hoặc một step tiếp theo có retry rõ ràng.

### Ném exception trong afterStep để mong step tự chuyển FAILED

Không nên dựa vào exception của callback này để thay đổi trạng thái theo cách mong muốn. Dùng `ExitStatus` tường minh và cấu hình transition, hoặc đưa kiểm tra bắt buộc vào step nghiệp vụ.

### Listener thực hiện quá nhiều việc

Listener gọi nhiều API, ghi nhiều database hoặc xử lý logic nghiệp vụ lớn sẽ làm tăng failure modes và khó xác định transaction boundary. Giữ listener nhỏ; chuyển nghiệp vụ sang service/tasklet/writer phù hợp.

### Log toàn bộ item hoặc exception message không lọc

Payload có thể chứa thông tin nhạy cảm và làm log quá lớn. Ghi business key, execution ID và thông tin lỗi đã được lọc.

## Nguyên tắc triển khai

Khi viết listener cho production, hãy thống nhất các nguyên tắc sau:

1. Xác định callback là quan sát, audit, business operation hay điều khiển flow.
2. Phân biệt exception chính của reader/processor/writer với lỗi phụ của listener.
3. Trong error callback, không ném lỗi audit mới để thay thế exception gốc.
4. Gắn lỗi phụ vào exception chính bằng `addSuppressed` và log có ngữ cảnh.
5. Không catch rồi bỏ qua exception của thao tác chính.
6. Thiết kế audit và notification idempotent vì listener có thể được gọi lại.
7. Dùng `SkipListener` cho quyết định skip cuối cùng thay vì coi mọi attempt error là một skip.
8. Hiểu transaction boundary; `afterChunk` chạy sau commit và không thể rollback chunk.
9. Dùng `ExitStatus` cùng flow transition khi cần điều khiển kết quả sau step.
10. Đặt business operation bắt buộc trong tasklet/processor/writer hoặc outbox có transaction rõ ràng.
11. Kiểm thử listener khi chính dịch vụ audit/metrics/notification gặp lỗi.

## Ghi nhớ

Listener giúp quan sát và phản ứng với vòng đời job, step, chunk và item, nhưng lỗi phụ của listener không được che mất exception chính. Trong `onReadError`, `onProcessError` hoặc `onWriteError`, hãy giữ exception được truyền vào; nếu ghi audit thất bại, gắn exception phụ bằng `addSuppressed` và ghi log có ngữ cảnh thay vì ném exception mới. Phân biệt attempt error với item thực sự bị skip, hiểu callback nào chạy trước hay sau commit, và thiết kế side effect có idempotency. Với thao tác nghiệp vụ bắt buộc, dùng transaction của tasklet/writer hoặc transactional outbox; với điều khiển flow sau step, trả `ExitStatus` rõ ràng và cấu hình transition thay vì dựa vào exception trong callback để thay đổi trạng thái.
