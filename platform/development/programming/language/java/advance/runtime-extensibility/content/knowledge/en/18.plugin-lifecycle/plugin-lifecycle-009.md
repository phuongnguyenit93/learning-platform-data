# Xử lý lỗi khi dừng plugin và bảo đảm đóng lặp lại có hành vi xác định

## 1. Vì sao dừng plugin khó hơn gọi close()?

Plugin trong ứng dụng Java thường sở hữu executor, thread, scheduler, socket, connection, listener, file handle, native resource hoặc đăng ký vào registry của host. Khi dừng, một thao tác cleanup có thể ném exception; nếu host ngừng ngay tại exception đầu tiên, các tài nguyên còn lại không được giải phóng. Ngoài ra cùng một plugin có thể nhận yêu cầu dừng nhiều lần: shutdown toàn ứng dụng, reload, timeout, hoặc một callback lỗi gửi đồng thời. Bởi vậy dừng plugin cần **hành vi xác định** ngay cả khi cleanup thất bại.

Thiết kế tốt cần phân biệt:

- **Idempotent stop/close:** lần gọi tiếp theo không chạy lại cùng cleanup hoặc tạo side effect mới.
- **Best-effort cleanup:** cố gắng giải phóng các tài nguyên độc lập dù một bước lỗi.
- **Error aggregation:** lưu lỗi đầu tiên và thêm các lỗi tiếp theo bằng `addSuppressed`, hoặc báo cáo trạng thái có cấu trúc.
- **Concurrency:** không để hai thread cùng dừng một tài nguyên gây double-close/race.
- **Lifecycle observability:** biết trạng thái cuối và lý do dừng, không tuyên bố “đã đóng sạch” khi có lỗi.

Idempotence **không** có nghĩa đóng lần đầu luôn thành công; nó có nghĩa các lần đóng sau có kết quả theo contract đã định, không thực thi cleanup lặp lại ngoài dự kiến.

## 2. Thiết kế state machine

```text
NEW --start()--> STARTING --success--> RUNNING
                         | failure        | stop()/close()
                         v                v
                       FAILED          STOPPING
                                          |
                                cleanup success/failure
                                          v
                                        STOPPED
```

Trong nhiều hệ thống, `FAILED` khi start cũng phải được cleanup: mọi resource đã cấp trước khi thất bại cần dừng. Một state machine chặt hơn có thể tách `STOPPED` (không còn tác vụ được chấp nhận) và `CLOSED_WITH_ERRORS` (cleanup có lỗi). Bản thiết kế cần ghi rõ trạng thái nào là terminal, trạng thái nào cho phép retry, và thời điểm host ngừng route request tới plugin.

Các bất biến tối thiểu:

1. Khi bước vào `STOPPING`, không nhận yêu cầu mới.
2. Một thread duy nhất thực hiện cleanup; những caller khác đợi hoặc lấy kết quả đã hoàn tất.
3. Cleanup được thử với từng tài nguyên một lần, theo thứ tự rõ ràng.
4. Lỗi cleanup không che mất lỗi chính đã kích hoạt shutdown.
5. Mọi caller sau khi stop hoàn tất quan sát cùng một kết quả cuối hoặc cùng một failure summary.

## 3. Thứ tự dừng an toàn

Đối với plugin có request đang xử lý:

1. Đánh dấu **quiescing** và tháo plugin khỏi routing/registry để từ chối request mới.
2. Ngừng scheduler, inbound callbacks và nguồn sinh tác vụ mới.
3. Chờ tác vụ đang chạy hoàn tất có timeout; nếu cần, hủy theo policy và quản lý interrupt.
4. Flush/commit hoặc rollback công việc đang thực hiện theo semantics của plugin.
5. Đăng ký cleanup các tài nguyên theo thứ tự phụ thuộc ngược (LIFO có thể phù hợp).
6. Unregister listener, driver, hook, metrics, resource callback và xóa reference của host.
7. Dọn thread-context-classloader (TCCL), `ThreadLocal` trên worker threads do plugin quản lý.
8. Sau khi provider không còn được sử dụng, đóng classloader nếu loại loader hỗ trợ `close`; bỏ strong references để GC có thể thu hồi.

Không nên coi `URLClassLoader.close()` là lệnh dừng toàn plugin: nó không tự ngừng thread, không xóa registry hoặc giải phóng mọi object. Tương tự `ModuleLayer` không có `close()` để unload module.

## 4. Ví dụ Java 17+: close một lần và tổng hợp lỗi

Ví dụ dưới dùng `AtomicReference<CompletableFuture<Void>>` làm **single-flight close**: một caller tạo future đại diện cho kết quả shutdown; các caller còn lại cùng chờ future ấy. Nó lưu cả failure, vì vậy gọi lại `close()` sau lỗi sẽ nhận cùng nguyên nhân, chứ không giả vờ thành công hay chạy cleanup lần nữa.

File `PluginShutdownDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicReference;

public final class PluginShutdownDemo {
    interface Step {
        void run() throws Exception;
    }

    static final class Plugin implements AutoCloseable {
        private final List<Step> cleanup;
        private final AtomicReference<CompletableFuture<Void>> closing =
                new AtomicReference<>();

        Plugin(List<Step> cleanup) {
            this.cleanup = List.copyOf(cleanup);
        }

        @Override
        public void close() throws Exception {
            CompletableFuture<Void> created = new CompletableFuture<>();
            if (closing.compareAndSet(null, created)) {
                Exception first = null;
                for (int i = cleanup.size() - 1; i >= 0; i--) {
                    try {
                        cleanup.get(i).run();
                    } catch (Exception ex) {
                        if (first == null) first = ex;
                        else first.addSuppressed(ex);
                    }
                }
                if (first == null) created.complete(null);
                else created.completeExceptionally(first);
            }

            try {
                closing.get().join();
            } catch (CompletionException ex) {
                Throwable failure = ex.getCause();
                if (failure instanceof Exception exception) throw exception;
                if (failure instanceof Error error) throw error;
                throw new IllegalStateException(failure);
            }
        }
    }

    public static void main(String[] args) {
        List<String> log = new ArrayList<>();
        Plugin plugin = new Plugin(List.of(
                () -> log.add("close-A"),
                () -> { log.add("close-B"); throw new Exception("B failed"); },
                () -> log.add("close-C")
        ));

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                plugin.close();
            } catch (Exception ex) {
                System.out.println("attempt " + attempt + ": "
                        + ex.getMessage());
            }
        }
        System.out.println("cleanup=" + log);
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 PluginShutdownDemo.java
java PluginShutdownDemo
```

Output:

```text
attempt 1: B failed
attempt 2: B failed
cleanup=[close-C, close-B, close-A]
```

Giải thích: `List.copyOf` cố định thứ tự cleanup; vòng lặp chạy từ cuối về đầu, đúng thứ tự LIFO. B lỗi nhưng A vẫn được thử. Kết quả lỗi được lưu trong future, nên lần đóng thứ hai không chạy lại bất kỳ step nào. Với nhiều lỗi, các lỗi phụ có trong `getSuppressed()` của exception đầu tiên.

**Phạm vi ví dụ:** các `Step` được giả định ngắn, không bị treo vĩnh viễn và không gọi ngược `plugin.close()` từ bên trong cleanup. Đóng đệ quy trên chính thread cleanup có thể deadlock do đợi future của mình. Hệ thống production phải quy định rõ reentrant shutdown và timeout. `Error`/`Throwable` ngoài `Exception` cũng cần chiến lược để không để future chưa complete; phần sau giải thích cách harden.

## 5. Điều gì xảy ra nếu nhiều thread gọi close() cùng lúc?

Với `AtomicReference` ở ví dụ, chỉ một caller thành công `compareAndSet(null, created)` và làm cleanup. Caller khác không thắng CAS sẽ đợi `closing.get().join()`. Tuy vậy để toàn diện trong production cần xử lý:

- **Thread bị interrupt khi chờ:** `CompletableFuture.join()` không trả `InterruptedException`; nếu cần contract phản ứng interrupt hoặc timeout, dùng `get(timeout, unit)` với xử lý rõ ràng.
- **Cleanup treo:** nếu cleanup không có timeout, các caller cùng có thể chờ vô hạn; nên đặt deadline và phân loại bước có thể hủy.
- **Exception vs Error:** bắt `Exception` sẽ không bắt `OutOfMemoryError`, `StackOverflowError` hoặc lỗi nghiêm trọng khác. Cân nhắc `try/finally` hoàn thành future với failure nếu bất kỳ `Throwable` thoát ra; tuyệt đối không nuốt lỗi JVM nghiêm trọng.
- **Reentrant close:** có thể cần kiểm tra chủ sở hữu shutdown thread hoặc thiết kế cleanup không bao giờ gọi lại close.
- **Đóng dưới lock:** không thực thi user/plugin cleanup trong synchronized lock dài; callback có thể gọi lại host và tạo deadlock.

Giải pháp thay thế là lock + enum state + `CountDownLatch`, nhưng vẫn phải có cơ chế cho caller tiếp theo nhận trạng thái/failure trước đó. Chỉ sử dụng `AtomicBoolean.compareAndSet(false, true)` rồi return ngay khi đã đóng có thể đáp ứng idempotence cơ bản nhưng **không bảo đảm caller thứ hai đợi cho cleanup thực sự kết thúc**.

## 6. Aggregation: không mất lỗi cleanup

Giả sử plugin có ba tài nguyên A, B, C. Nếu C và B cùng lỗi, stop phải cố gắng close A nhưng vẫn báo được cả hai lỗi. Một mẫu thường dùng:

```java
Exception primary = null;
for (AutoCloseable resource : resources) {
    try {
        resource.close();
    } catch (Exception ex) {
        if (primary == null) primary = ex;
        else if (primary != ex) primary.addSuppressed(ex);
    }
}
if (primary != null) throw primary;
```

Đây là đoạn minh họa trong method có biến `resources` và chính sách ordering phù hợp. Nếu cần đóng ngược thứ tự cấp phát, duyệt ngược. Tránh `addSuppressed` lên chính exception object vì Java không cho phép self-suppression.

**Try-with-resources** tự đóng các `AutoCloseable` theo thứ tự ngược và duy trì suppressed exceptions. Nhưng khi plugin giữ tài nguyên suốt nhiều request/lifecycle phases, cần logic điều phối shutdown riêng và không phải tài nguyên nào cũng có thể tạo trong cùng một scope try-with-resources.

## 7. Lỗi gốc và lỗi khi dừng

Một trường hợp quan trọng: plugin đang xử lý request thì gặp lỗi nghiệp vụ, host bắt đầu dừng plugin và cleanup cũng lỗi. **Không để cleanup failure che khuất lỗi gốc**. Có thể thêm lỗi cleanup dưới dạng suppressed của lỗi gốc, hoặc tạo một `PluginFailure` chứa hai phần: `cause` cho failure chính và `cleanupFailures` cho các lỗi dọn dẹp.

Ví dụ minh họa:

```java
Throwable original = failureFromPlugin;
try {
    plugin.close();
} catch (Exception cleanupFailure) {
    if (original != cleanupFailure) {
        original.addSuppressed(cleanupFailure);
    }
}
throw original;
```

Đoạn này là pseudocode tại ranh giới method có kiểu throws phù hợp, không phải Java method hoàn chỉnh. Trong code production có thể wrap trong exception nghiệp vụ để không mất checked exception và giữ correlation ID cho request/plugin.

## 8. Idempotence không phải retry cleanup mặc định

Có hai chính sách hợp lệ nhưng cần tách rõ:

1. **At-most-once cleanup:** mỗi step chạy tối đa một lần; close lặp lại trả cùng kết quả. Ưu điểm: tránh double-close hoặc side effect không an toàn. Nhược điểm: step lỗi không được retry tự động.
2. **Retryable cleanup:** cho phép retry có kiểm soát với bước chứng minh được idempotent (ví dụ gọi API delete có request ID). Lúc này cần state riêng từng resource, attempt count, backoff/deadline và rules rõ ràng; không thể coi là cùng contract với at-most-once đơn giản.

Ví dụ `Socket.close()` thường có thể gọi lại, nhưng việc plugin tự gọi `flushAndCommit()` hoặc `unregisterAndCharge()` không nhất thiết idempotent. Đừng mặc định mọi bước cleanup an toàn để retry. Nếu một bước vẫn đang chạy, không tạo attempt thứ hai song song.

## 9. State terminal và báo cáo vận hành

Để tránh kết luận sai, một trạng thái terminal có thể gồm:

| State | Ý nghĩa |
| --- | --- |
| `STOPPED` | Đã ngừng nhận việc và cleanup hoàn tất thành công theo contract |
| `STOPPED_WITH_ERRORS` | Đã thử các bước cleanup, có ít nhất một bước lỗi; một số tài nguyên có thể chưa giải phóng |
| `STOPPING` | Đang thực hiện cleanup; caller sau cần đợi hoặc được trả trạng thái in-progress |
| `FAILED_START` | Startup lỗi; vẫn cần cleanup các resource đã cấp phát |

Logging nên có plugin ID, phiên bản, lifecycle transition, duration, resource name, error class, số lỗi suppressed và timeout. Đừng chỉ log `close completed` khi có lỗi. Với leak, theo dõi số thread còn sống, listener/registry entries, sockets, file descriptors và reference giữ classloader.

## 10. Test cases bắt buộc

- **Double-close:** gọi `close()` hai lần; mỗi cleanup step chạy đúng một lần.
- **Concurrent-close:** nhiều thread cùng gọi; đúng một thread chạy cleanup và các caller nhận cùng kết quả.
- **First-step failure:** bước cuối theo thứ tự teardown bị lỗi, các bước còn lại vẫn được thử.
- **Multiple failures:** primary và suppressed exceptions được giữ nguyên.
- **Start partially failed:** resource đã cấp trước khi startup lỗi được dọn; không đánh dấu RUNNING.
- **Timeout:** cleanup block không khiến shutdown toàn ứng dụng treo vô hạn nếu có deadline.
- **Reentrant close:** callback không dẫn đến self-deadlock; policy nêu rõ.
- **Interrupt:** không mất interrupt status và không chuyển terminal state sai.
- **Reload:** route request mới sang plugin mới; drain plugin cũ trước khi close.

## 11. Lỗi thiết kế thường gặp

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| `catch(Exception e) {}` trong stop | Mất dấu resource leak | Aggregate và báo cáo lỗi |
| Thoát stop khi bước đầu lỗi | Bỏ sót phần cleanup còn lại | Best-effort từng bước |
| Gọi cleanup lại sau failure | Double-release/side effects | Xác định at-most-once hoặc retryable policy |
| Chỉ dùng boolean `closed=true` trước cleanup | Caller tưởng đã hoàn tất | Tách STOPPING và terminal; cho caller đợi |
| Giữ lock khi gọi plugin callbacks | Deadlock, latency | Single-flight state + cleanup ngoài lock |
| `close()` thành công nhưng vẫn route request | Race với tài nguyên đã đóng | Quiesce và drain trước cleanup |
| Chỉ đóng classloader | Thread/listener/socket còn sống | Lifecycle cleanup toàn diện |
| Đánh dấu STOPPED dù cleanup lỗi | Báo cáo trạng thái sai | STOPPED_WITH_ERRORS và metrics |

## 12. Checklist

- [ ] Có state transition rõ ràng: RUNNING → STOPPING → terminal.
- [ ] Ngừng tiếp nhận tác vụ trước teardown; drain với deadline.
- [ ] Chỉ một caller thực thi cleanup; các caller khác nhận cùng completion/failure.
- [ ] Cleanup theo thứ tự tài nguyên phụ thuộc; thử tất cả bước độc lập.
- [ ] Tập hợp suppressed exceptions, không che lỗi gốc.
- [ ] Quyết định cụ thể at-most-once hay retryable cleanup.
- [ ] Xử lý timeout, interrupt, reentrancy và Error ở production.
- [ ] Gỡ registration, dừng threads, khôi phục TCCL, bỏ classloader references.
- [ ] Log trạng thái và lỗi cleanup, không tuyên bố thành công sai.
- [ ] Test double-close, concurrent-close và nhiều failure.

**Kết luận:** dừng plugin là một giao thức vòng đời cần idempotence, thứ tự và xử lý lỗi tường minh. Thiết kế theo single-flight stop, thực hiện best-effort cleanup, tổng hợp exception và công bố terminal result nhất quán giúp `close()` lặp lại có hành vi xác định mà không che giấu resource leak.
