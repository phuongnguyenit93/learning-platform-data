# Chọn tầng chịu trách nhiệm ghi log để tránh lặp cùng một lỗi trong Java

Một ngoại lệ có thể đi qua nhiều tầng: repository → service → controller → global exception handler. Nếu **mỗi tầng đều ghi `ERROR` kèm toàn bộ stack trace rồi ném tiếp**, một thất bại nghiệp vụ sẽ tạo nhiều sự kiện log giống nhau. Log trở nên nhiễu, tốn chi phí lưu trữ, khó đếm số sự cố thực và có thể khiến hệ thống cảnh báo nhiều lần cho cùng một request.

Bài này thuộc **Java Core – Exception / Chẩn đoán và ghi log**. Mục tiêu là xác định **tầng nào sở hữu quyết định xử lý lỗi và chịu trách nhiệm ghi log**, đồng thời giữ thông tin nguyên nhân xuyên các tầng. Ví dụ thuần JDK chạy trên **Java 17+**; các đoạn có `logger` là mã tích hợp minh họa cho logging framework.

## 1. Nguyên tắc chính: ghi log tại nơi chịu trách nhiệm xử lý kết quả

Hãy bắt đầu bằng câu hỏi: **“Tầng nào có đủ ngữ cảnh và thực sự quyết định điều gì xảy ra với thất bại này?”**

- Nếu một tầng **không giải quyết được** lỗi và chỉ truyền tiếp, thông thường **giữ cause, bổ sung ngữ cảnh có ích rồi ném tiếp; không ghi một stack trace `ERROR` tại đây**.
- Nếu một tầng **thật sự xử lý/phục hồi** lỗi và không còn truyền nó như lỗi tới caller, tầng đó là nơi có thể cần một log phù hợp (`DEBUG`, `INFO`, `WARN` hoặc `ERROR` tùy tác động).
- Nếu lỗi **vượt đến ranh giới đầu cuối** và request/job/message bị đánh dấu thất bại, ranh giới xử lý cuối cùng thường là nơi **ghi một sự kiện lỗi giàu ngữ cảnh**, sau đó trả mã lỗi hoặc hoàn tất xử lý.
- Nếu một thành phần khác đã chắc chắn ghi log thất bại cuối cùng (ví dụ framework exception resolver, job runner), cần biết **hợp đồng log sẵn có** để không tạo bản sao nữa.

“Ghi log một lần” ở đây là **một sự kiện lỗi chính cho một lần thất bại trong một phạm vi sở hữu**, thường là một request, một job hoặc một thao tác nghiệp vụ. Đây không phải lệnh cấm mọi log ở các tầng khác: log tiến trình, metric, cảnh báo về phục hồi, audit có mục đích, hay thông tin khác ngữ nghĩa vẫn có giá trị.

Một sơ đồ xử lý:

```text
Request R-100
   │
   ▼
Controller ───────────────┐
   │                     │
   ▼                     │
Service                  │
   │                     │
   ▼                     │
Repository               │
   └── ném IOException   │
          │              │
          ├─ Repository: giữ nguyên lỗi; không ERROR trùng
          ▼              │
      Service: thêm ngữ cảnh bằng cause; không ERROR trùng
          │              │
          ▼              │
     Controller / global handler
          │
          ├─ ghi một ERROR + Throwable + requestId
          └─ trả kết quả lỗi thích hợp
```

Điều cần tối ưu không phải “ít log nhất” mà là **mỗi log có một mục đích và một chủ sở hữu rõ ràng**.

## 2. Vì sao “log rồi throw” dễ gây trùng?

Giả sử các tầng đều làm như sau:

```java
try {
    repository.load();
} catch (IOException e) {
    logger.error("Repository failed", e);
    throw e;
}
```

Đây là **mảnh mã minh họa**, giả định `repository` và `logger` có sẵn. Nếu service lại:

```java
try {
    repository.load();
} catch (IOException e) {
    logger.error("Service failed", e);
    throw new IllegalStateException("Không tải được hồ sơ", e);
}
```

và controller/global handler thêm `logger.error("Request failed", e)`, một lỗi I/O đã thành **ba stack trace**. Các log có thể khác câu chữ nhưng vẫn cùng một failure chain, khiến người vận hành tưởng có ba sự cố độc lập.

Hệ quả thường gặp:

1. **Sai số đếm lỗi:** dashboard đếm log `ERROR` thấy ba dòng trong khi chỉ một request thất bại.
2. **Khó phân nhóm:** cùng lỗi hiện diện với nhiều message và wrapper exception.
3. **Tăng chi phí:** ba stack trace dài, đặc biệt nếu hệ thống log tập trung tính phí theo dữ liệu ingest.
4. **Nhiễu cảnh báo:** rule theo số lượng `ERROR` báo động nhanh hơn số lượng request lỗi thực tế.
5. **Lộ dữ liệu nhiều nơi:** mỗi bản sao có thể chứa stack, message, tham số hoặc thông tin nhạy cảm.
6. **Khó đọc timeline:** log trùng làm che các sự kiện khác thực sự hữu ích trước thời điểm thất bại.

Nguyên tắc thực hành thường được diễn đạt là **“log or throw”**: nếu tầng hiện tại phải ném tiếp, hãy để tầng chịu trách nhiệm sau ghi log. Đây là nguyên tắc thiết kế mặc định, **không phải quy tắc tuyệt đối**; trường hợp bảo mật, audit, chuẩn vận hành hoặc ranh giới hệ thống có thể cần sự kiện bổ sung với ý nghĩa khác biệt.

## 3. Tầng thấp: truyền ngoại lệ và giữ `cause`

Một repository thường biết rằng việc đọc dữ liệu thất bại nhưng chưa chắc biết request cuối cùng sẽ thất bại: service có thể thử cache, retry hoặc chọn nguồn dự phòng. Vì vậy repository nên **trả lỗi đúng hợp đồng** để tầng có đủ ngữ cảnh quyết định.

Ở các tầng trung gian, có hai lựa chọn chính:

- **Truyền nguyên ngoại lệ:** khi kiểu exception và hợp đồng API cho phép.
- **Bọc ngoại lệ và giữ cause:** khi cần chuyển từ lỗi kỹ thuật sang ngữ cảnh nghiệp vụ của tầng hiện tại.

Ví dụ:

```java
try {
    return dataSource.read();
} catch (IOException e) {
    throw new IllegalStateException("Không nạp được cấu hình của khách hàng", e);
}
```

Đây là **mảnh mã minh họa** bên trong phương thức có kết quả phù hợp, không phải chương trình độc lập. Constructor `IllegalStateException(message, e)` giữ liên kết `getCause()` để handler ngoài cùng vẫn nhìn được `IOException`.

Không nên bọc kiểu này:

```java
throw new IllegalStateException("Không nạp được cấu hình");
```

nếu đó là hành động thay thế cho một ngoại lệ vừa bắt, vì như vậy **làm mất cause**. Cũng không nên tạo wrapper ở mọi bước mà không thêm ngữ cảnh thực sự; một chuỗi wrapper quá sâu khiến stack khó đọc.

**Mục tiêu:** giữ được nguyên nhân và ngữ cảnh cần thiết để **một điểm ghi log cuối cùng** có thể cung cấp đầy đủ câu chuyện lỗi.

## 4. Ví dụ Java 17 chạy độc lập: một lỗi, một điểm ghi nhận

Tạo tệp `SingleBoundaryLogDemo.java`:

```java
import java.io.IOException;

public class SingleBoundaryLogDemo {
    static String readProfile() throws IOException {
        throw new IOException("database unavailable");
    }

    static String loadProfile() {
        try {
            return readProfile();
        } catch (IOException e) {
            throw new IllegalStateException(
                    "không tải được hồ sơ", e);
        }
    }

    static String controller() {
        return loadProfile();
    }

    public static void main(String[] args) {
        try {
            controller();
        } catch (IllegalStateException failure) {
            // Minh họa sự kiện log tại ranh giới request.
            System.out.println(
                    "ERROR requestId=R-100 operation=profile.load");
            System.out.println("outer = "
                    + failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());

            Throwable cause = failure.getCause();
            System.out.println("cause = "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SingleBoundaryLogDemo.java
java SingleBoundaryLogDemo
```

Output chính xác:

```text
ERROR requestId=R-100 operation=profile.load
outer = IllegalStateException: không tải được hồ sơ
cause = IOException: database unavailable
```

`readProfile()` phát sinh một `IOException`, `loadProfile()` bọc thêm ngữ cảnh **mà không tự ghi log**, `controller()` truyền tiếp. `main()` đóng vai trò **ranh giới request**, chịu trách nhiệm ghi một sự kiện cuối cùng. Các lệnh `System.out` chỉ nhằm cho đầu ra minh họa dễ kiểm tra; **ứng dụng production nên dùng logging framework** và truyền chính đối tượng Throwable để giữ stack trace.

Nếu dùng API logging kiểu SLF4J tại ranh giới, câu lệnh tương ứng có thể là:

```java
logger.error(
        "Không tải được hồ sơ, requestId={}",
        requestId,
        failure);
```

Đây là **mã tích hợp**, giả định `logger` tương thích với SLF4J và `requestId`, `failure` đã tồn tại. Trong một cấu hình logging thông dụng, đối tượng Throwable ở đối số cuối sẽ được in cùng stack trace và cause. Cần kiểm tra overload cụ thể của API/logger đang dùng; không dựa vào việc ghép `failure.getMessage()` để thay thế Throwable.

## 5. Tầng nào là ranh giới xử lý lỗi?

Tùy loại ứng dụng, “tầng cuối” có thể là:

| Ứng dụng | Điểm chịu trách nhiệm thường gặp | Kết quả xử lý |
|---|---|---|
| HTTP/REST | Exception handler toàn cục hoặc HTTP filter được giao quyền | Phản hồi HTTP hợp lệ, mã lỗi/correlation ID, ghi nhận request thất bại |
| Batch/CLI | Job runner hoặc entry point `main()` | Ghi kết quả job thất bại, exit status/chính sách retry |
| Consumer queue | Handler tại ranh giới tiêu thụ message | Quyết định ack/nack, retry, dead-letter, log lần thất bại cuối |
| Scheduler | Khung thực thi của scheduled job | Xác định task failure và theo dõi lịch chạy |
| Executor/Future | Thành phần **quan sát kết quả** `get()`/`join()` hoặc callback quản lý lỗi | Đọc cause, quyết định retry/hủy/fallback và log |
| Thư viện dùng lại | Thường **không** sở hữu kết quả cuối của ứng dụng | Ném exception có ý nghĩa, giữ cause; không tự log ERROR cho mọi caller |

Đây là **các vị trí thường gặp**, không phải tên lớp bắt buộc. Một framework có thể đã tự log exception chưa được xử lý; nhiều deployment còn có service mesh, tracing hoặc centralized error reporting. Trước khi tự thêm logger mới, phải xác định ai đã ghi sự kiện thất bại.

### Ví dụ Spring MVC (mảnh mã tích hợp)

Trong ứng dụng Spring Web có thể chọn một `@RestControllerAdvice` tập trung việc chuyển lỗi không mong đợi sang phản hồi chuẩn:

```java
@RestControllerAdvice
class ApiExceptionHandler {
    private static final org.slf4j.Logger LOG =
            org.slf4j.LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiError> handle(Exception error,
                                    HttpServletRequest request) {
        String requestId = request.getHeader("X-Request-Id");
        LOG.error("Unhandled request failure, requestId={}",
                  requestId, error);

        return ResponseEntity.status(500)
                .body(new ApiError("INTERNAL_ERROR", requestId));
    }
}
```

Đây là **ví dụ kiến trúc, không chạy độc lập**: cần Spring MVC, Jakarta Servlet, import tương ứng và record/class `ApiError`. Đoạn này cố ý chỉ minh họa **vị trí ownership**; trong thực tế cần phân loại 4xx/5xx, lấy request ID từ nguồn đáng tin (không tin mù quáng header do client nhập), quản lý security và tránh để framework hoặc filter khác ghi cùng stack trace lần nữa.

Không nên đưa nguyên `error.getMessage()` và stack trace của lỗi nội bộ vào HTTP response. Phản hồi cho client nên có mã lỗi an toàn cùng correlation ID; thông tin chi tiết thuộc hệ thống log được kiểm soát quyền.

## 6. Nếu tầng trung gian xử lý được lỗi, log tại đó có thể đúng

Một ngoại lệ **đã được xử lý và không truyền lên** không còn là request failure. Ví dụ remote API tạm lỗi nhưng service có cache hợp lệ. Chính service **sở hữu quyết định fallback**, nên có thể ghi một `WARN` hoặc metric về degraded mode; controller nhận dữ liệu thành công và không nên ghi `ERROR` cho cùng nguyên nhân.

Tạo tệp `RecoveredFailureLogDemo.java`:

```java
import java.io.IOException;

public class RecoveredFailureLogDemo {
    static String remoteName() throws IOException {
        throw new IOException("upstream unavailable");
    }

    static String loadName() {
        try {
            return remoteName();
        } catch (IOException e) {
            // Service quyết định phục hồi bằng dữ liệu cache.
            System.out.println(
                    "WARN fallback=cache reason=upstream_unavailable");
            return "Tên trong cache";
        }
    }

    public static void main(String[] args) {
        System.out.println("response = " + loadName());
    }
}
```

Chạy:

```bash
javac RecoveredFailureLogDemo.java
java RecoveredFailureLogDemo
```

Kết quả:

```text
WARN fallback=cache reason=upstream_unavailable
response = Tên trong cache
```

Ở đây `main` không nhận exception và không cần ghi thêm `ERROR`. Tầng service thực sự **đổi kết quả từ failure sang success có suy giảm chất lượng**, vì vậy log ở đó mang ý nghĩa khác: hệ thống đã dùng fallback. Với lỗi remote thường xuyên và có thể phục hồi, metric `fallback_count` hoặc log có lấy mẫu còn hiệu quả hơn hàng nghìn stack trace giống nhau.

Tùy nghiệp vụ, lỗi được phục hồi có thể không cần log ở mức `WARN`: một cache miss thông thường, `FileNotFoundException` dự kiến hoặc tín hiệu đóng worker thường nên là `INFO`/`DEBUG` hoặc không log. **Mức độ log phụ thuộc tính bất thường và tác động**, không chỉ phụ thuộc việc có exception.

## 7. Một thất bại được thử lại nhiều lần: đếm attempt khác đếm operation

Retry làm bài toán khó hơn: **một operation** có thể gồm nhiều **attempt**. Nếu mỗi attempt đều log `ERROR` kèm stack trace rồi tầng ngoài cùng cũng log tổng thất bại, dashboard dễ nhầm bốn sự cố thành một.

Phân biệt:

- **Attempt failure:** một lần thử bị lỗi, nhưng policy có thể thử tiếp. Có thể ghi metric `retry_attempts`, `DEBUG` hay log ngắn nếu cần điều tra.
- **Operation failure:** sau khi hết số lần thử, toàn bộ thao tác không đạt mục tiêu. Đây thường là nơi ghi `ERROR` cuối cùng, có đủ số attempt và cause cuối.
- **Operation success after retry:** không nên có `ERROR` “không thể hoàn thành” cho thao tác rốt cuộc đã thành công; có thể ghi metric hoặc `INFO/WARN` về độ trễ và việc sử dụng retry.

### Ví dụ độc lập: ba attempt, một log lỗi cuối

Tệp `RetryOnceLogDemo.java`:

```java
import java.io.IOException;

public class RetryOnceLogDemo {
    static String attemptRead(int attempt) throws IOException {
        throw new IOException("upstream unavailable");
    }

    static String readWithRetry() {
        IOException last = null;

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return attemptRead(attempt);
            } catch (IOException e) {
                last = e;
                // Ghi metric retry tại đây nếu cần, không ERROR mỗi lần.
            }
        }

        throw new IllegalStateException(
                "thất bại sau 3 lần thử", last);
    }

    public static void main(String[] args) {
        try {
            readWithRetry();
        } catch (IllegalStateException failure) {
            System.out.println(
                    "ERROR operation=remote.read attempts=3");
            System.out.println("error = " + failure.getMessage());
            System.out.println("cause = "
                    + failure.getCause().getClass().getSimpleName()
                    + ": " + failure.getCause().getMessage());
        }
    }
}
```

Lệnh:

```bash
javac RetryOnceLogDemo.java
java RetryOnceLogDemo
```

Output:

```text
ERROR operation=remote.read attempts=3
error = thất bại sau 3 lần thử
cause = IOException: upstream unavailable
```

Tác vụ được thử ba lần, nhưng log `ERROR` cho operation chỉ xuất hiện **một lần** ở cuối. Đoạn mẫu cố ý không ngủ để output dễ kiểm tra; retry production cần giới hạn attempt, timeout, exponential backoff/jitter phù hợp, kiểm tra lỗi nào thật sự có thể retry và **tính idempotent** để tránh lặp tác dụng phụ (ví dụ gửi thanh toán hai lần).

Nếu cần truy vết chi tiết từng attempt, hãy ghi `DEBUG` hoặc metric với `attempt`, `operationId`, kết quả phân loại; **không nhất thiết lặp toàn bộ stack trace**. Các attempt là sự kiện kỹ thuật riêng có ích, không phải ba operation failure độc lập.

## 8. Bất đồng bộ: ai quan sát và ai log exception?

Với `ExecutorService.submit(...)`, lỗi từ `Callable` thường được giữ trong `Future`. Nếu không ai gọi `get()`, lỗi có thể bị bỏ sót. Nếu nhiều component cùng đọc và log cùng một Future, lỗi có thể bị nhân bản.

Các điểm cần phân biệt:

- `Future.get()` có thể ném `ExecutionException`; **cause** nằm ở `getCause()`.
- `CompletableFuture.join()` thường báo exceptional completion qua `CompletionException`; cần xem cause bên dưới.
- `CompletableFuture.whenComplete(...)` thích hợp ghi nhận/quan sát kết quả mà không thay giá trị, nhưng **nếu vừa log ở callback vừa log tại `join()` của caller**, dễ trùng.
- `CompletableFuture.exceptionally(...)` và `handle(...)` có thể phục hồi lỗi thành kết quả bình thường; khi đó callback phục hồi có thể là nơi ghi nhận degraded mode, còn caller không ghi thêm operation failure.
- `cancel(...)`, `InterruptedException` và `CancellationException` là tín hiệu vòng đời quan trọng; không tự động xem là `ERROR`.

### Ví dụ độc lập: log tại nơi quan sát stage cuối

Tạo tệp `AsyncBoundaryLogDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncBoundaryLogDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> parsed =
                CompletableFuture.completedFuture("abc")
                        .thenApply(Integer::parseInt);

        CompletableFuture<Integer> processed =
                parsed.thenApply(value -> value + 1);

        try {
            System.out.println(processed.join());
        } catch (CompletionException failure) {
            Throwable cause = failure.getCause();
            System.out.println(
                    "ERROR operation=parseAndIncrement");
            System.out.println("cause = "
                    + cause.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac AsyncBoundaryLogDemo.java
java AsyncBoundaryLogDemo
```

Kết quả:

```text
ERROR operation=parseAndIncrement
cause = NumberFormatException
```

`thenApply(Integer::parseInt)` thất bại; các stage downstream mang exceptional completion. Không có `ERROR` trung gian ở mỗi `thenApply`. `main`, nơi sở hữu kết quả cuối, ghi một sự kiện. Nếu dùng `whenComplete` để log ngay tại `parsed`, thì tầng quan sát cuối cần **không ghi lại cùng lỗi**, hoặc callback đó chỉ đo metric và không in stack trace.

Trong ứng dụng có nhiều Future độc lập, phải có chiến lược **quan sát từng operation**: một thất bại của hai job khác nhau thật sự là hai sự kiện cần log. “Log once” không có nghĩa bỏ qua nhiều operation chỉ vì chúng tình cờ ném cùng loại exception.

## 9. Phân loại mức log theo kết quả thật

Có exception không đồng nghĩa `ERROR`. Một ma trận quyết định có thể áp dụng:

| Tình huống | Mức ghi nhận thường hợp lý | Lý do |
|---|---|---|
| Request thất bại bất ngờ, chưa được phục hồi | `ERROR` ở boundary | Cần điều tra một operation failure |
| Lỗi tạm thời đã dùng fallback, dịch vụ còn hoạt động | `WARN`, đôi khi `INFO`/metric | Chất lượng suy giảm nhưng operation hoàn tất |
| Retry attempt chưa hết ngân sách | `DEBUG`/metric hoặc log ngắn | Chưa phải thất bại cuối |
| Đầu vào không hợp lệ dự kiến, trả HTTP 400 | Có thể `INFO`/metric hoặc không log | Đây có thể là hành vi client bình thường |
| Tác vụ bị hủy có chủ đích khi shutdown | `DEBUG`/`INFO` hoặc không log | Lifecycle bình thường |
| Lỗi bảo mật/audit cần dấu vết riêng | Log bảo mật có kiểm soát, mức theo chính sách | Mục đích khác với stack trace lỗi kỹ thuật |
| Lỗi đóng tài nguyên gây ảnh hưởng lớn | `ERROR` tại boundary chịu trách nhiệm | Có nguy cơ dữ liệu/tài nguyên bị hỏng |
| Exception đã bị propagate qua nhiều tầng | Một error log chính, giữ cause | Tránh lặp cùng một failure chain |

Mức log phải phù hợp SLA, yêu cầu vận hành và sự kỳ vọng của hệ thống. Ví dụ 404 thông thường không cần stack trace, nhưng 404 do dữ liệu hệ thống bất ngờ mất có thể cần điều tra.

Đừng chỉ dựa vào tên exception như `IllegalArgumentException` để tự động xem là lỗi do client; phải phân loại theo **ngữ cảnh**: exception này có thể do bug trong service chứ không phải input HTTP.

## 10. Ghi log đầy đủ một lần: nội dung nào là đủ?

Một sự kiện lỗi ở boundary nên có những trường thiết yếu, tùy hệ thống:

- **`operation`**: thao tác bị thất bại (`order.create`, `invoice.export`, `message.consume`).
- **`requestId` / `correlationId` / `traceId`**: nối sự kiện với request hoặc trace, dùng nguồn đáng tin.
- **`service`, `environment`, `version`**: nơi và bản build xảy ra lỗi (thường logger hạ tầng bổ sung).
- **`exception`**: Throwable đầy đủ, có cause và suppressed, được truyền tới logging API đúng overload.
- **`errorCode` / `failureClass`**: phân loại lỗi có thể tổng hợp, không phụ thuộc message biến động.
- **Kết quả thật**: HTTP status, job status, retry exhausted, fallback used, dead-letter route nếu liên quan.
- **Thông tin hữu ích nhưng an toàn**: mã đối tượng đã kiểm soát, attempt count, duration, dependency name.

Không nên đưa password, token, secret, key, cookie hoặc payload chứa dữ liệu cá nhân vào log. Exception message từ thư viện đôi khi đã chứa dữ liệu nội bộ; cần policy sanitization, quyền truy cập và retention phù hợp.

Ví dụ phương thức gọi logging theo placeholder (mã tích hợp, yêu cầu logger tương thích SLF4J):

```java
logger.error(
        "operation={} requestId={} errorCode={} attempts={}",
        operation,
        requestId,
        errorCode,
        attempts,
        failure);
```

Chỗ `failure` là **Throwable**, không phải `failure.toString()` hoặc `failure.getMessage()`. Chỉ string hóa message thường bỏ mất stack, `Caused by`, `Suppressed` và dòng nguồn. Một số hệ thống log JSON có field dành riêng cho exception; nên cấu hình encoder/appender để giữ thông tin này thay vì tự nối chuỗi dài.

### Correlation ID không phải chìa khóa duy nhất để đếm lỗi

Một request có thể có **nhiều failure độc lập** hoặc chứa nhiều item; một job có thể chạy nhiều operation. Nếu muốn chống duplicate logic, thiết kế khóa phân biệt `operationId + failureClass + attempt/phase`, cùng cơ chế sở hữu sự kiện. Không được tự động xóa mọi log có cùng `requestId` vì có thể loại bỏ thông tin khác nhau.

Một biến thể hữu ích là theo dõi **metric tổng số request thất bại** tại boundary, còn log chỉ là kênh điều tra. Metric nên đếm operation cuối cùng thay vì đếm số dòng `ERROR` vốn có thể thay đổi theo cấu hình.

## 11. `Caused by` và `Suppressed` cần được giữ nguyên xuyên các tầng

Khi một tầng bọc exception bằng constructor có `cause`, hệ thống có thể in:

```text
java.lang.IllegalStateException: Không tạo được báo cáo
    at app.ReportService.export(ReportService.java:40)
Caused by: java.io.IOException: Hết dung lượng ổ đĩa
    at app.FileWriter.save(FileWriter.java:20)
    ... 1 more
```

Đây là stack trace **minh họa**, số dòng chỉ để mô tả. `... 1 more` nói về frame trùng ở cuối stack, không phải một exception khác.

Nếu dùng `try-with-resources`, lỗi `close()` có thể nằm dưới `Suppressed:`. Một điểm log ở cuối với **toàn bộ Throwable** có thể giữ cả outer message, cause và suppressed. Nếu mỗi tầng tự log `e.getMessage()` rồi bỏ cause, sẽ vừa tạo duplicate vừa mất dữ liệu quan trọng.

Không phải log một lần thì thông tin ít hơn: **một stack trace đầy đủ có chuỗi cause/suppressed** thường giá trị hơn nhiều dòng lỗi rời rạc không có liên hệ.

## 12. Tránh trùng khi framework và runtime đã log

Trong nhiều framework, exception không xử lý có thể được ghi bởi:

- Bộ xử lý lỗi HTTP hoặc error dispatcher.
- Job scheduler, executor wrapper hoặc task framework.
- Consumer framework khi message handler ném lỗi.
- Container/app server khi request hoặc task thoát ra ngoài.
- Bộ thu thập telemetry/APM tạo exception event tự động.

Vì vậy, cần **đọc behavior của đường xử lý lỗi đang dùng**. Nếu global handler của bạn log rồi trả response bình thường, framework có thể không log stack lần nữa; nhưng nếu handler log rồi `throw` để framework xử lý, duplicate có thể xuất hiện.

Các hướng thiết kế thông thường:

1. **Cho framework sở hữu:** tầng ứng dụng thêm ngữ cảnh và ném tiếp; framework ghi lỗi tại boundary nếu đủ dữ liệu.
2. **Ứng dụng sở hữu:** một global handler ghi log và chuyển lỗi sang kết quả cuối; tránh tự log lại tại filter/controller/service.
3. **Tách metric/audit khỏi error log:** instrumentation có thể ghi metric hoặc span status mà không phải copy nguyên stack trace.

Không thể chọn đúng một cách chỉ bằng tên công nghệ. Cần kiểm tra cấu hình logger, exception resolver, code của middleware và log thực tế của một request lỗi đã kiểm soát.

## 13. Khi nào ngoại lệ cần được ghi nhiều lần?

Có những tình huống **khác mục đích hoặc khác ranh giới** nên nhiều sự kiện là hợp lý:

- Một service A gọi service B. B cần ghi lỗi operation của **chính B**; A cũng có thể ghi lỗi request của **chính A** nếu hợp đồng của A thất bại. Đây là **hai operation tại hai service**, dù cùng một nguyên nhân kỹ thuật, và nên được nối bằng trace/correlation ID.
- Một retry attempt có log mức `DEBUG` diễn giải thời điểm và backoff, trong khi exhaustion là một log `ERROR` cuối. Đây là **sự kiện khác ý nghĩa**, không phải lặp nguyên stack.
- Một sự kiện audit/security bắt buộc ghi độc lập với operation error; cấu trúc, retention và quyền đọc có thể khác.
- Một lỗi được phục hồi có `WARN` về fallback; một phần việc khác độc lập về sau lại thất bại. Chúng không phải cùng một thất bại để gộp.

Điều cần tránh là **sao chép cùng một exception stack với cùng kết luận “operation failed” ở từng tầng liên tiếp**, không thêm thông tin hoặc sở hữu kết quả mới.

Nếu có một lý do thực sự cần log trước khi ném tiếp, thông điệp phải nói rõ **sự kiện khác biệt** (ví dụ rollback thất bại riêng), lý do và mức độ. Đừng biến ngoại lệ này thành ngoại lệ được log ba lần chỉ vì ba nơi đều có `catch`.

## 14. Ranh giới transaction, rollback, cleanup

Một exception có thể khiến transaction rollback hoặc `close()` thất bại. Không phải mọi lỗi cùng xuất hiện trong một luồng đều là duplicate:

- **Lỗi chính:** thao tác nghiệp vụ bị thất bại.
- **Lỗi rollback/cleanup:** một thao tác khôi phục hệ thống khác cũng thất bại, có hậu quả riêng.
- **Ngoại lệ suppressed:** Java có thể lưu lỗi đóng tài nguyên bổ sung trong Throwable chính.

Tại boundary, cần ghi một sự kiện đủ chi tiết giữ các nhánh này. Nếu cleanup tạo **một incident độc lập** đòi hỏi alert hoặc can thiệp riêng, có thể ghi sự kiện riêng với nhãn rõ ràng, tránh dùng cùng câu “request failed” như lỗi chính.

Ví dụ dạng thiết kế (mảnh mã minh họa, `cleanup` do ứng dụng định nghĩa):

```java
try {
    performOperation();
} catch (Exception primary) {
    try {
        cleanup();
    } catch (Exception cleanupFailure) {
        primary.addSuppressed(cleanupFailure);
    }
    throw primary;
}
```

Phương thức bao ngoài phải xử lý/khai báo `Exception`; đoạn code không độc lập. `addSuppressed(...)` bảo toàn lỗi cleanup cùng exception chính, cho phép tầng có trách nhiệm ghi đầy đủ một lần. Nếu `cleanupFailure` có hậu quả riêng cần alert, instrumentation có thể ghi một metric hoặc sự kiện có nghĩa khác.

## 15. Logging, propagation và `InterruptedException`

`InterruptedException` là tín hiệu rằng **luồng hiện tại bị yêu cầu ngắt khi chờ**, thường liên quan shutdown/hủy tác vụ. Không nên mặc định log `ERROR` kèm stack ở mỗi tầng.

Trong một worker muốn ngừng hợp tác (mảnh mã đặt trong `Runnable` hoặc phương thức phù hợp):

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

`queue` là một `BlockingQueue` đã khai báo. `Thread.currentThread().interrupt()` khôi phục cờ interrupt vì thao tác chờ thường xóa cờ khi ném ngoại lệ. Nếu shutdown này là **dự kiến**, log ở mức `DEBUG/INFO` hoặc không log; nếu là sự kiện không dự kiến, ranh giới worker có thể ghi chi tiết sau khi phân loại.

Đừng bắt `Exception` chung, in stack, rồi tiếp tục vòng lặp vô hạn: thao tác chờ có thể ném lại liên tục khi cờ interrupt vẫn đặt, đồng thời hệ thống bị log storm.

`CancellationException` của Future bị hủy cũng thường là lifecycle, không tự đồng nghĩa với lỗi nghiệp vụ. `ExecutionException` và `CompletionException` báo thất bại của tác vụ bất đồng bộ và thường chứa cause cần phân loại.

## 16. Đo lường và kiểm tra rằng log không bị trùng

Cách kiểm tra một thay đổi logging nên dựa trên **tình huống có thể lặp lại**:

1. Tạo một request/job có lỗi xác định, gắn một `requestId` duy nhất.
2. Xác nhận kết quả cuối đúng: status thất bại hoặc fallback, không chỉ nhìn console.
3. Đếm **sự kiện `ERROR` chính cho operation** theo requestId và event code. Thông thường mong một sự kiện cho một operation failure.
4. Kiểm tra `Throwable` được in đầy đủ với cause và suppressed khi cần, không chỉ một chuỗi message.
5. Kiểm tra cả retry: nhiều attempt nhưng chỉ một log `ERROR` nếu cuối cùng thất bại; nếu thành công thì không còn kết luận operation failed.
6. Kiểm tra async `get()`/`join()` và callback: tránh log cả callback lẫn boundary cho cùng thất bại.
7. Kiểm tra một lỗi được phục hồi: có thể xuất hiện `WARN`/metric về fallback, nhưng không tự tạo thêm error event ở controller.
8. Kiểm tra PII/secret và correlation ID; bảo đảm hệ thống log tập trung không tự sao chép event do pipeline.
9. So sánh **metric số operation thất bại** với số log lỗi cuối theo cùng cửa sổ thời gian; hai con số không bắt buộc luôn bằng nhau nếu có sampling hoặc nhiều event độc lập, nhưng sai lệch lớn cần giải thích.

Trong automated test, có thể dùng in-memory appender của logging framework để kiểm tra message/code, level, throwable và số event ở boundary. **Đừng chỉ so khớp toàn bộ stack trace từng ký tự** vì số dòng, tên frame và lớp JDK có thể thay đổi; điều cần xác nhận là ownership, cause và số lượng log chính.

### Quan sát với phân tán

Một service có thể nhận cùng requestId qua nhiều hop. Hãy gắn `service`, `operation` hoặc span ID để phân biệt event của mỗi hop. Log aggregation thường cung cấp khả năng group các event có cùng trace ID; nó không thay thế việc kiểm soát duplicate tại nguồn.

## 17. Các anti-pattern và cách sửa

### A. `catch` chỉ để log rồi throw nguyên

```java
try {
    repository.save(entity);
} catch (Exception e) {
    logger.error("save failed", e);
    throw e;
}
```

Đây là mảnh mã tích hợp giả định `repository`, `entity`, `logger` đã có. Nếu tầng này không làm gì thêm, hãy **bỏ `catch`** hoặc chỉ bọc lỗi có ý nghĩa theo hợp đồng và giữ cause. Để boundary chịu trách nhiệm log.

### B. In `printStackTrace()` đồng thời gọi logger

```java
e.printStackTrace();
logger.error("failed", e);
```

Hai cơ chế có thể cùng in stack, gây duplicate qua stdout/stderr và logger. Chọn cơ chế logging chuẩn của hệ thống.

### C. Log message nhưng bỏ Throwable

```java
logger.error("Request failed: {}", e.getMessage());
```

Nó có thể thiếu stack, cause và suppressed. Ở nơi chịu trách nhiệm ghi lỗi, truyền **đối tượng exception** vào đúng overload của logger.

### D. Bọc lỗi nhưng cắt cause

```java
throw new IllegalStateException("Service failed");
```

Nếu đang chuyển đổi một exception vừa bắt, truyền cause: `new IllegalStateException("Service failed", e)`. Không chuyển các lỗi thuộc kiểu checked thành thông điệp trần rồi bỏ chuỗi nguyên nhân.

### E. Retry mọi lỗi và log mọi lần

Retry cả lỗi validate dữ liệu bất biến có thể vô ích; `ERROR` từng attempt tạo storm. Phân loại lỗi retryable, đặt số lần, timeout/backoff, thống nhất operation ID và ghi kết luận ở cuối.

### F. Dùng một log level cho mọi exception

Một 404 hợp lệ hoặc thao tác hủy theo yêu cầu không giống DB outage. Chọn level theo **tác động vận hành** và kết quả, không theo tên kiểu Java.

### G. Không xác định owner khi dùng global handler

Controller log `ERROR`, service log `ERROR`, global advice cũng log `ERROR`, rồi container in thêm stack. Chọn rõ một nơi và kiểm tra framework có log mặc định không.

### H. Che lỗi bằng fallback không được giám sát

Nếu service trả cache thay cho dữ liệu mới, operation có thể thành công nhưng chất lượng suy giảm. Có thể ghi metric hoặc `WARN` để biết degraded mode mà không biến request thành `ERROR`.

### I. Coi log line là đơn vị đo sự cố

Đếm số `ERROR` dễ bị thay đổi do cấu hình và nhân bản. Dùng metric về **operation outcome**, request status, trace và event code ổn định; log để điều tra nguyên nhân.

### J. Tự tạo khóa chống trùng quá rộng

Nếu deduplicate theo mỗi `requestId`, có thể nuốt mất những lỗi độc lập trong cùng request. Thiết kế event identity theo **operation/failure phase/service**, không coi mọi Throwable cùng correlation ID là một lỗi.

## 18. Bảng quyết định khi review một `catch`

| Tình huống trong `catch` | Hành động thường đúng | Có ghi stack trace ở đây? |
|---|---|---|
| Không thể xử lý, ném tiếp nguyên lỗi | Truyền tiếp | Thường **không** |
| Chuyển lỗi kỹ thuật thành exception ngữ cảnh | Bọc exception giữ cause, ném tiếp | Thường **không** |
| Phục hồi thành công nhờ fallback | Trả dữ liệu/response dự phòng, cập nhật metric | Có thể `WARN`/`INFO`, không nhất thiết toàn stack |
| Hết retry và operation thất bại | Ném lên boundary hoặc xử lý tại chính boundary | **Có**, một sự kiện lỗi cuối |
| Handler HTTP quyết định response cuối | Phân loại, ghi sự kiện nếu chưa có chủ sở hữu khác | Có thể **có** |
| Worker bị interrupt theo shutdown | Khôi phục cờ/thoát theo hợp đồng | Thường không `ERROR` |
| Cleanup cũng thất bại | Giữ suppressed, đánh giá hậu quả độc lập | Chỉ tách log nếu có ý nghĩa độc lập |
| Audit bắt buộc bởi chính sách | Ghi sự kiện audit có cấu trúc | Theo policy, khác error log |

**Ghi nhớ:** Một Throwable có thể đi qua nhiều `catch`, nhưng mỗi `catch` không nhất thiết cần một log. Tầng trung gian giữ **cause và ngữ cảnh**, tầng phục hồi ghi nhận **điều đã xử lý**, còn ranh giới sở hữu kết quả thất bại ghi **một sự kiện chính giàu thông tin**. Rõ ownership giúp log đủ để điều tra và vẫn phản ánh đúng số operation thực sự thất bại.
