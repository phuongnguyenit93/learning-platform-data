# Retry listener

`RetryListener` là callback của Spring Retry cho phép quan sát vòng đời của một retry operation. Trong Spring Batch, listener này có thể được gắn vào fault-tolerant chunk step để ghi nhận lúc bắt đầu retry operation, từng lần thử thất bại và kết quả cuối cùng.

Listener hữu ích cho logging, metrics, tracing và chẩn đoán lỗi tạm thời. Nó giúp theo dõi retry mà không phải nhúng logic quan sát vào reader, processor hoặc writer. Tuy nhiên, listener không thay thế `RetryPolicy`, `BackOffPolicy`, skip policy hay transaction manager: mỗi thành phần có một trách nhiệm riêng.

## 1. RetryListener nằm ở đâu trong xử lý batch?

Trong chunk-oriented step, Spring Batch có thể thử lại thao tác khi reader, processor hoặc writer gặp exception được cấu hình là retryable. Retry mechanism gọi các callback của `RetryListener` quanh retry operation.

```text
Chunk processing
      |
      v
Reader / Processor / Writer
      |
      +-- thành công ----------------------> tiếp tục chunk
      |
      +-- exception retryable
               |
               v
        RetryListener.open()
               |
               v
        Thực hiện callback
               |
               +-- thất bại --> RetryListener.onError()
               |                    |
               |                    v
               |              RetryPolicy quyết định
               |                    |
               |                    +-- retry tiếp
               |                    +-- kết thúc retry
               |
               +-- thành công
               |
               v
        RetryListener.close()
               |
               v
        Chunk tiếp tục recovery/commit
```

`RetryListener` quan sát một retry operation. Với chunk có nhiều item lỗi hoặc có nhiều lần retry, listener có thể được gọi nhiều lần trong một step execution. Không nên hiểu đây là listener chỉ chạy một lần cho toàn bộ job.

## 2. Các callback chính

Trong Spring Batch 5, listener được dùng từ package `org.springframework.retry`. Các callback cơ bản gồm:

| Callback | Thời điểm | Mục đích |
|---|---|---|
| `open(context, callback)` | Trước lần thực thi đầu tiên của retry operation | Khởi tạo thông tin quan sát hoặc quyết định có cho phép operation bắt đầu |
| `onError(context, callback, throwable)` | Sau mỗi lần thực thi không thành công | Ghi nhận exception và attempt thất bại |
| `close(context, callback, throwable)` | Sau attempt cuối cùng, dù thành công hay thất bại | Tổng kết kết quả và dọn state tạm |

`open` trả về `boolean`. Trả về `true` để retry operation tiếp tục. Trả về `false` sẽ veto toàn bộ operation và dẫn đến `TerminatedRetryException`; đây không phải cách thông thường để biểu diễn một exception không retryable. Hãy dùng `RetryPolicy` để quyết định exception nào được retry.

`onError` được gọi sau mỗi attempt thất bại. Nếu operation được thử lại nhiều lần, callback này có thể được gọi nhiều lần cho cùng một item hoặc operation.

`close` được gọi một lần khi retry operation kết thúc. Tham số `throwable` thể hiện exception cuối cùng nếu operation kết thúc thất bại; khi operation thành công, giá trị này thường là `null`.

## 3. RetryListener trong Spring Batch 5

Các kiểu thường dùng nằm trong Spring Retry:

```java
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;
```

Có thể triển khai trực tiếp interface `RetryListener`. Các phương thức có generic để callback có thể bao quanh nhiều kiểu kết quả và exception khác nhau.

```java
public class BatchRetryListener implements RetryListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchRetryListener.class);

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context, RetryCallback<T, E> callback) {
        log.debug("Retry operation started");
        return true;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        log.warn(
            "Retry attempt {} failed: {}",
            context.getRetryCount(),
            throwable.toString()
        );
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        if (throwable == null) {
            log.debug(
                "Retry operation completed after {} retry attempt(s)",
                context.getRetryCount()
            );
        } else {
            log.error(
                "Retry operation exhausted after {} retry attempt(s)",
                context.getRetryCount(),
                throwable
            );
        }
    }
}
```

Đây là listener quan sát cơ bản. `context.getRetryCount()` cung cấp số lần retry được ghi nhận trong retry context; hãy xác nhận cách đếm bằng integration test với phiên bản Spring Retry của dự án nếu metric cần phân biệt chính xác attempt đầu tiên và các lần retry bổ sung.

Không nên giả định `onError` chỉ chạy khi đã hết retry. Callback này được gọi sau mỗi lần thất bại, kể cả khi policy vẫn cho phép thử tiếp.

## 4. Đăng ký listener vào chunk step

Trong Spring Batch 5, `FaultTolerantStepBuilder` có overload `.listener(RetryListener)` để đăng ký retry listener. Listener phải được gắn trong cấu hình fault-tolerant step.

```java
@Bean
BatchRetryListener batchRetryListener() {
    return new BatchRetryListener();
}

@Bean
Step callPartnerStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Request> reader,
        ItemProcessor<Request, Response> processor,
        ItemWriter<Response> writer,
        BatchRetryListener retryListener) {

    return new StepBuilder("callPartner", jobRepository)
        .<Request, Response>chunk(20, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientPartnerException.class)
        .retryLimit(3)
        .listener(retryListener)
        .build();
}
```

Trong ví dụ này, `TransientPartnerException` là loại lỗi được phép retry. `retryLimit(3)` đặt giới hạn retry theo cấu hình của builder; listener chỉ quan sát vòng đời retry. Nếu cần quy tắc retry khác nhau theo từng exception, cấu hình `RetryPolicy` tương ứng và giữ listener độc lập với quyết định đó.

Đừng nhầm overload `.listener(RetryListener)` với các overload dành cho `ItemReadListener`, `ItemProcessListener`, `ItemWriteListener`, `SkipListener` hoặc `ChunkListener`. Chúng có callback và phạm vi khác nhau.

## 5. Dùng RetryContext để giữ thông tin trong một retry operation

`RetryContext` chứa state của retry operation, ví dụ retry count, exception gần nhất và các attribute tạm. Có thể dùng context attribute để lưu thời điểm bắt đầu hoặc một mã tương quan phục vụ log.

```java
public class TimedRetryListener implements RetryListener {

    private static final String START_KEY = "batch.retry.startedAt";

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context, RetryCallback<T, E> callback) {
        context.setAttribute(START_KEY, System.nanoTime());
        return true;
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        Object value = context.getAttribute(START_KEY);
        if (value instanceof Long startedAt) {
            long elapsedNanos = System.nanoTime() - startedAt;
            recordRetryDuration(elapsedNanos, throwable == null);
        }
    }
}
```

`recordRetryDuration` là hàm metric do ứng dụng cung cấp. Dùng attribute trên `RetryContext` giúp state thuộc đúng retry operation thay vì lưu vào field mutable của một listener singleton.

`RetryContext` là state tạm của retry mechanism. Nó không thay thế Spring Batch `ExecutionContext`, vốn dùng để lưu checkpoint bền vững cho restart. Không lưu checkpoint nghiệp vụ duy nhất trong retry context.

## 6. RetryListener có thể quan sát attempt nào?

Các callback có phạm vi khác nhau:

- `open`: một lần trước khi bắt đầu retry operation.
- `onError`: sau mỗi lần attempt không thành công.
- `close`: một lần sau attempt cuối cùng.

Ví dụ một item thất bại hai lần rồi thành công:

```text
open()
  attempt 1 -> exception -> onError()
  attempt 2 -> exception -> onError()
  attempt 3 -> success
close(throwable = null)
```

Ví dụ một item thất bại đến hết giới hạn:

```text
open()
  attempt 1 -> exception -> onError()
  attempt 2 -> exception -> onError()
  attempt 3 -> exception -> onError()
close(throwable = lastException)
```

`onError` cho biết một attempt thất bại, không khẳng định item cuối cùng đã bị skip. Sau khi retry kết thúc, Spring Batch còn áp dụng recovery và skip policy. Một lỗi có thể hết retry nhưng làm step thất bại thay vì skip.

## 7. RetryListener không phải RetryPolicy

`RetryPolicy` quyết định có được thử lại sau exception hay không. `RetryListener` quan sát lifecycle của retry. Hai thành phần có thể được dùng cùng nhau nhưng không nên gộp trách nhiệm.

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| `RetryPolicy` | Quyết định retry có được phép tiếp tục không | Retry tối đa ba lần với timeout |
| `BackOffPolicy` | Quyết định khoảng chờ giữa các lần thử | Exponential backoff |
| `RetryListener` | Quan sát bắt đầu, lỗi từng attempt và kết thúc | Log exception, ghi metrics |
| Skip policy | Quyết định item lỗi có được loại bỏ không | Skip lỗi dữ liệu với giới hạn |
| Transaction manager | Quản lý commit/rollback | Rollback chunk khi exception yêu cầu |

Không dùng listener để đếm số lỗi rồi tự quyết định retry nếu `RetryPolicy` đã là nơi quản lý số lần thử. Cách làm đó dễ tạo hai nguồn sự thật và khó kiểm thử.

## 8. RetryListener và onSuccess trong Spring Retry 2.x

Các phiên bản Spring Retry 2.0 bổ sung callback `onSuccess(context, callback, result)`, được gọi khi callback trả về thành công. Phương thức này không có trong mọi phiên bản cũ, vì vậy chỉ override khi dependency của dự án hỗ trợ.

```java
@Override
public <T, E extends Throwable> void onSuccess(
        RetryContext context,
        RetryCallback<T, E> callback,
        T result) {
    log.debug("Retry callback returned successfully");
}
```

`onSuccess` có semantics đặc biệt: listener có thể ném exception mới để yêu cầu retry theo policy dựa trên kết quả vừa trả về. Vì vậy, nếu mục đích chỉ là logging hoặc metrics, không ném exception từ callback này. Với code cần tương thích nhiều phiên bản Spring Retry, hãy kiểm tra interface của dependency đang được quản lý trước khi thêm method này.

## 9. Listener không quyết định kết quả cuối của step

Khi retry operation kết thúc, kết quả vẫn phụ thuộc retry policy, skip policy, exception và transaction semantics của step.

Ví dụ:

- Một attempt lỗi, lần retry sau thành công: operation tiếp tục và listener đóng retry context với kết quả thành công.
- Retry hết giới hạn, exception skippable và skip limit còn: Spring Batch có thể skip item và tiếp tục step.
- Retry hết giới hạn, exception không skippable: step có thể thất bại.
- Một attempt thành công nhưng lỗi commit xảy ra sau đó: chunk vẫn có thể rollback; `RetryListener.close` không chứng minh chunk đã commit.

Do đó, không dùng `close(throwable == null)` làm bằng chứng dữ liệu đã được commit vào database. Nó chỉ cho biết retry callback kết thúc bình thường.

## 10. Phân biệt RetryListener với các listener khác

Spring Batch có nhiều listener cho các giai đoạn khác nhau. Chọn đúng loại giúp tránh đếm sai hoặc đặt logic ở sai ranh giới.

| Listener | Quan sát | Phạm vi |
|---|---|---|
| `RetryListener` | Các attempt trong retry operation | Một chuỗi retry |
| `ItemReadListener` | Trước/sau read và lỗi read | Một lần đọc item |
| `ItemProcessListener` | Trước/sau process và lỗi process | Một item qua processor |
| `ItemWriteListener` | Trước/sau writer và lỗi write | Một chunk ghi |
| `SkipListener` | Item thực sự bị skip | Một item bị loại sau recovery |
| `ChunkListener` | Trước/sau chunk và lỗi chunk | Một chunk transaction |
| `StepExecutionListener` | Bắt đầu/kết thúc step | Một StepExecution |

Ví dụ, `RetryListener.onError` có thể được gọi nhiều lần khi một item được thử lại. `SkipListener.onSkipInProcess` chỉ ghi nhận item thực sự bị skip sau recovery. Không dùng số lần `onError` để thay thế skip count.

## 11. RetryListener và SkipListener khi retry hết giới hạn

Giả sử processor gọi dịch vụ đối tác. Lần đầu và lần thứ hai bị timeout, lần thứ ba vẫn thất bại. Nếu exception được cấu hình skippable và skip limit chưa bị vượt, Spring Batch có thể loại item đó.

```text
RetryListener.open()
  attempt 1 -> timeout -> RetryListener.onError()
  attempt 2 -> timeout -> RetryListener.onError()
  attempt 3 -> timeout -> RetryListener.onError()
RetryListener.close(lastException)

Recovery:
  SkipListener.onSkipInProcess(item, lastException)
```

Trong ví dụ, retry listener ghi nhận các lần thử thất bại; skip listener ghi nhận quyết định loại item. Nếu exception không skippable, callback skip không xảy ra và step có thể kết thúc thất bại.

Không nên ghi reject record trong `RetryListener.onError` vì item có thể được retry thành công ở attempt sau. Hãy dùng `SkipListener` hoặc cơ chế recovery phù hợp khi đã xác định item thực sự bị skip.

## 12. RetryListener và transaction rollback

Retry operation có thể chạy trong chunk transaction và tương tác với rollback/recovery. Listener không mở transaction mới, không commit và không rollback dữ liệu.

```text
Chunk transaction
    |
    +--> retry operation
             |
             +--> attempt thất bại
             +--> onError
             +--> policy cho retry
             +--> attempt sau
             +--> close
    |
    v
Spring Batch tiếp tục recovery/commit/rollback chunk
```

Khi retry xảy ra qua ranh giới transaction, một số thao tác có thể được gọi lại. Writer hoặc processor có side effect ngoài transaction cần idempotency key, outbox hoặc cơ chế đối soát. Listener chỉ ghi nhận sự kiện; nó không làm cho side effect trở nên an toàn khi gọi lặp.

## 13. Logging và metrics an toàn

Retry listener thường là nơi tốt để thu thập thông tin về độ ổn định của hệ thống phụ thuộc. Các thông tin hữu ích gồm:

- Tên job/step hoặc tên dependency theo cấu hình.
- Exception category và số lần attempt.
- Thời gian của retry operation.
- Kết quả cuối: thành công hay hết retry.
- Correlation ID hoặc execution ID nếu có sẵn trong context.

Tránh ghi toàn bộ item hoặc JobParameters vào log. Payload có thể chứa thông tin cá nhân, dữ liệu thanh toán hoặc credential. Với metrics, tránh dùng order ID, request ID hoặc tenant ID làm label có cardinality cao; hãy dùng các nhãn ổn định như job, step, dependency và exception type.

Ví dụ listener có thể tăng counter trong `onError` và ghi duration trong `close`. Nếu muốn đếm số item cuối cùng bị skip, hãy dùng skip listener hoặc StepExecution skip count thay vì suy ra từ retry listener.

## 14. Thread safety và state trong listener

Listener bean thường là singleton do Spring quản lý. Một step có thể chạy nhiều item, nhiều partition hoặc nhiều job execution đồng thời. Vì vậy, không nên lưu trạng thái của một retry operation vào field mutable dùng chung.

Ví dụ không an toàn:

```java
public class UnsafeRetryListener implements RetryListener {
    private long startedAt;

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context, RetryCallback<T, E> callback) {
        startedAt = System.nanoTime();
        return true;
    }
}
```

Hai retry operation đồng thời có thể ghi đè `startedAt` của nhau. Dùng attribute trên `RetryContext` cho state thuộc operation; dùng counter/thread-safe meter cho metrics. Nếu phải dùng `ThreadLocal`, cần dọn state trong mọi đường kết thúc, bao gồm lỗi.

## 15. Nhiều RetryListener và thứ tự callback

Có thể đăng ký nhiều listener nếu cần tách logging, metrics và tracing. Spring Retry gọi `open` theo thứ tự đăng ký; các callback `onError` và `close` được gọi theo thứ tự ngược lại.

```java
.faultTolerant()
.retry(TransientPartnerException.class)
.retryLimit(3)
.listener(retryLoggingListener)
.listener(retryMetricsListener)
.build();
```

Giữ danh sách listener ngắn và tránh để listener phụ thuộc thứ tự của listener khác nếu không cần thiết. Nếu một listener ghi state mà listener khác đọc, hãy xác định rõ thứ tự và kiểm thử. Không để listener làm chậm retry path bằng thao tác mạng hoặc truy vấn nặng.

## 16. Tránh side effect trong RetryListener

Listener có thể được gọi nhiều lần và ở các thời điểm trước khi chunk commit. Vì vậy, không nên đặt các thao tác nghiệp vụ quan trọng vào callback:

- Không gửi email báo thành công từ `close` chỉ vì retry callback trả về bình thường.
- Không tạo reject record trong mỗi `onError` vì attempt sau có thể thành công.
- Không sửa dữ liệu nghiệp vụ hoặc gọi writer từ listener.
- Không gọi dịch vụ ngoài đồng bộ chỉ để gửi metric hoặc log.

Nếu cần phát thông báo sau commit, dùng outbox hoặc transaction synchronization. Nếu cần lưu item bị loại, dùng `SkipListener` và thiết kế reject write idempotent. Nếu cần quyết định retry, dùng `RetryPolicy`.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm `RetryListener` với `RetryPolicy` | Listener không kiểm soát đúng số lần retry | Đặt quyết định trong policy, listener chỉ quan sát |
| Ghi reject trong `onError` | Một item có thể được ghi reject dù attempt sau thành công | Chỉ ghi reject khi item thực sự bị skip |
| Xem `close` thành công là chunk đã commit | Có thể báo thành công trước khi transaction rollback | Phân biệt retry callback với commit boundary |
| Dùng field mutable trong singleton listener | Retry đồng thời ghi đè state của nhau | Dùng `RetryContext` attribute hoặc state thread-safe |
| Trả `false` từ `open` để từ chối một exception | Phát sinh `TerminatedRetryException`, sai tầng xử lý | Dùng `RetryPolicy` để phân loại exception |
| Retry listener gọi API ngoài đồng bộ | Tăng latency và có thể gây thêm lỗi trong retry path | Dùng metric/log nhẹ hoặc queue/outbox |
| Đếm `onError` như số item bị skip | Một item có thể lỗi nhiều lần rồi thành công | Dùng `SkipListener` và execution counters |
| Dùng `onSuccess` không kiểm tra version | Code không tương thích dependency cũ hoặc vô tình kích hoạt retry | Xác nhận Spring Retry version và không ném exception khi chỉ quan sát |

## 18. Kiểm thử RetryListener

Có thể kiểm thử listener độc lập bằng cách gọi callback với `RetryContext` mẫu, nhưng cần integration test qua một step fault-tolerant để xác nhận Spring Batch đăng ký và gọi listener đúng vòng đời.

Các trường hợp nên có:

1. Callback thành công ngay lần đầu: `open` và `close` được gọi; không có `onError`.
2. Thất bại rồi thành công: `onError` được gọi cho từng attempt lỗi và `close` nhận kết quả cuối thành công.
3. Hết retry: `onError` được gọi theo số attempt lỗi và `close` nhận exception cuối.
4. `open` trả về `false`: xác nhận operation bị veto và lỗi tương ứng được truyền ra.
5. Nhiều listener: xác nhận thứ tự callback như mong đợi.
6. Retry kết hợp skip: retry listener quan sát attempts, skip listener chỉ nhận item thực sự bị loại.
7. Chạy song song: state và metrics không bị trộn giữa các retry operation.
8. Lỗi commit sau writer: không diễn giải `close` thành bằng chứng chunk đã commit.

Test nên xác nhận cả callback count, exception cuối, retry count, skip count và dữ liệu transaction. Không chỉ kiểm tra log có một dòng warning.

## 19. Quy trình triển khai RetryListener

Khi thêm retry listener cho một step, thực hiện theo trình tự:

1. Xác định lỗi nào có thể retry và cấu hình `RetryPolicy` hoặc `.retry(...)` trước.
2. Xác định thông tin cần quan sát: attempt, exception, duration, dependency và kết quả cuối.
3. Triển khai `open`, `onError`, `close` với logic nhẹ, không có side effect nghiệp vụ.
4. Đăng ký listener trên `FaultTolerantStepBuilder` bằng `.listener(retryListener)`.
5. Dùng `RetryContext` cho state tạm của từng retry operation.
6. Dùng `SkipListener` nếu cần biết item thực sự bị skip sau recovery.
7. Kiểm thử success, retry success, retry exhaustion, skip, rollback và concurrency.
8. Kiểm tra log/metrics không chứa payload nhạy cảm hoặc label cardinality cao.

## Kết luận

`RetryListener` cung cấp callback để quan sát retry operation trong Spring Batch: `open` trước attempt đầu tiên, `onError` sau mỗi attempt thất bại và `close` sau attempt cuối cùng. Trong Spring Batch 5, có thể đăng ký listener vào fault-tolerant chunk step bằng overload `.listener(RetryListener)`.

Listener phù hợp cho logging, metrics, tracing và dọn state tạm. Nó không quyết định exception có được retry, không thay thế skip policy và không chứng minh chunk đã commit. Hãy giữ listener nhẹ và thread-safe, dùng `RetryContext` cho state theo operation, dùng `SkipListener` để ghi nhận item bị loại, và giữ mọi side effect nghiệp vụ ở thành phần có transaction/idempotency rõ ràng.
