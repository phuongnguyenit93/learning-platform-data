# Thời gian chờ, hủy hợp tác và interruption

Structured concurrency nhóm các tác vụ con thuộc cùng một công việc vào một **StructuredTaskScope**. Scope có chủ sở hữu, thời gian sống và chính sách phối hợp rõ ràng. Khi một tác vụ thất bại, kết quả đã đủ, deadline hết hạn hoặc luồng chủ sở hữu bị ngắt, scope có thể dừng việc nhận tác vụ mới và yêu cầu các tác vụ còn chạy kết thúc bằng interruption.

Cơ chế này là **hủy hợp tác (cooperative cancellation)**. Java gửi tín hiệu ngắt đến các luồng con; mỗi tác vụ phải phản hồi tín hiệu đó và tự hoàn tất. JVM không cưỡng bức dừng luồng. Vì vậy, timeout chỉ xác định thời điểm bắt đầu hủy. Thời điểm scope đóng xong còn phụ thuộc các tác vụ có dừng đúng cách hay không.

Trong module **JAVA_VERSION_JAVA26**, Structured Concurrency được đưa vào JDK 26 ở lần preview thứ sáu theo **JEP 525**. Tại ngày 27-11-2026, JDK 27 đã tiếp tục API ở lần preview thứ bảy theo **JEP 533**. Bài này trình bày semantics timeout, cancellation và interruption dùng chung, có ví dụ đúng JDK 26 cho nội dung module, đồng thời chỉ ra khác biệt cần biết khi chạy JDK 27 hiện hành.

## 1. Trạng thái API và phiên bản cần chọn

Structured Concurrency vẫn là **preview API**, chưa phải API Java SE ổn định. Các lớp và kiểu liên quan nằm trong module `java.base`, package `java.util.concurrent`. Không cần thêm module incubator, nhưng phải bật preview ở cả compiler và JVM.

| JDK | JEP | Trạng thái và thay đổi đáng chú ý |
|---|---|---|
| Java 19–20 | JEP 428, 437 | Incubator API; không dùng các ví dụ incubator cũ làm mẫu cho API hiện tại |
| Java 21–24 | JEP 453, 462, 480, 499 | Các lần preview đầu; API đã trải qua nhiều thay đổi |
| Java 25 | JEP 505 | Preview lần thứ năm; thiết kế API được tổ chức lại quanh `open`, `Joiner`, `fork`, `join`, `close` |
| Java 26 | JEP 525 | Preview lần thứ sáu; bổ sung cấu hình timeout và xử lý timeout qua `Joiner.onTimeout()` |
| Java 27 | JEP 533 | Preview lần thứ bảy; tiếp tục thay đổi kiểu trả về/exception của API và đổi `Joiner.onTimeout()` thành `Joiner.timeout()` |

Không sao chép ví dụ từ các preview cũ dùng `ShutdownOnFailure`, `ShutdownOnSuccess`, `shutdown()`, `joinUntil(...)` hoặc `throwIfFailed()`. API hiện hành dùng `StructuredTaskScope.open(...)`, `Joiner`, `fork()`, `join()` và `close()`. Đọc tài liệu của đúng JDK đang biên dịch trước khi dùng ví dụ hoặc thư viện preview.

## 2. Ba nguồn kích hoạt cancellation

Trong API hiện hành, scope có thể bị hủy vì ba nguyên nhân chính:

1. **Chính sách Joiner:** Joiner quyết định kết quả nào đủ để kết thúc công việc. Ví dụ `allSuccessfulOrThrow()` hủy scope khi một tác vụ thất bại; `anySuccessfulOrThrow()` hủy các tác vụ còn lại khi đã có một kết quả thành công.
2. **Timeout của scope:** cấu hình `withTimeout(Duration)` đặt giới hạn thời gian cho scope. Khi hết hạn trước hoặc trong lúc `join()` chờ, scope bị hủy.
3. **Đóng scope:** `close()`, thường được gọi tự động bởi `try-with-resources`, hủy scope nếu chưa bị hủy, ngắt các tác vụ chưa kết thúc rồi chờ chúng kết thúc.

Hủy scope ngăn việc khởi chạy thêm tác vụ trong scope và gửi interrupt đến các luồng đang chạy tác vụ chưa hoàn tất. Phương thức `isCancelled()` cho biết scope đã hoặc đang bị hủy. Giá trị `true` không có nghĩa mọi luồng con đã nhận interrupt hoặc đã dừng xong; quá trình đó có thể vẫn đang diễn ra.

Không có phương thức công khai `scope.cancel()` hoặc `scope.shutdown()` trong API hiện hành. Chính sách Joiner, timeout và vòng đời `close()` là các cơ chế điều khiển cancellation.

## 3. Timeout của scope bắt đầu từ lúc nào?

Trong JDK 26, tạo scope với cấu hình timeout như sau:

    Duration timeout = Duration.ofSeconds(3);

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow(),
            config -> config.withTimeout(timeout))) {

        scope.fork(() -> fetchProfile());
        scope.fork(() -> fetchOrders());

        List<String> results = scope.join();
        return results;
    }

Timeout bắt đầu khi scope được mở, không phải khi chương trình gọi `join()`. Thời gian chuẩn bị, fork tác vụ và chờ kết quả đều nằm trong cùng ngân sách. Nếu timeout đã hết trong giai đoạn fork, các tác vụ được fork sau đó có thể không được khởi chạy; `join()` sẽ xử lý kết quả theo chính sách timeout.

Nếu ứng dụng có deadline tuyệt đối dạng `Instant`, hãy tính khoảng thời gian còn lại trước khi mở scope:

    Duration remaining = Duration.between(Instant.now(), deadline);

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow(),
            config -> config.withTimeout(remaining))) {
        // fork subtasks
        // join
    }

Hãy tính deadline tại đúng tầng điều phối để các công việc lồng nhau dùng chung ngân sách thời gian còn lại, thay vì mỗi tầng tự bắt đầu một timeout đầy đủ mới.

Timeout của scope không phải hard kill. Khi hết hạn, scope bị hủy và interrupt các tác vụ chưa xong. `join()` trả kết quả hoặc ném exception theo Joiner; sau đó `close()` vẫn phải chờ tất cả các luồng con kết thúc. Nếu một tác vụ bỏ qua interruption hoặc bị kẹt trong thao tác không thể ngắt, thời gian đóng scope có thể vượt deadline rất lâu, thậm chí vô hạn.

## 4. Xử lý timeout trong JDK 26

Ở JDK 26, `StructuredTaskScope.Joiner` có phương thức `onTimeout()`. Phương thức mặc định ném `StructuredTaskScope.TimeoutException`. Vì vậy, với Joiner chuẩn `allSuccessfulOrThrow()`, khi timeout xảy ra, `join()` ném `StructuredTaskScope.TimeoutException`.

Ví dụ hoàn chỉnh:

    import java.time.Duration;
    import java.util.List;
    import java.util.concurrent.StructuredTaskScope;

    public class ScopeTimeout26 {

        static String fetchProfile() throws InterruptedException {
            Thread.sleep(500);
            return "profile";
        }

        static String fetchOrders() throws InterruptedException {
            Thread.sleep(5000);
            return "orders";
        }

        static List<String> loadDashboard() throws InterruptedException {
            Duration timeout = Duration.ofSeconds(2);

            try (var scope = StructuredTaskScope.open(
                    StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow(),
                    config -> config.withTimeout(timeout))) {

                scope.fork(ScopeTimeout26::fetchProfile);
                scope.fork(ScopeTimeout26::fetchOrders);

                return scope.join();
            }
        }

        public static void main(String[] args) {
            try {
                System.out.println(loadDashboard());
            } catch (StructuredTaskScope.TimeoutException e) {
                System.out.println("Dashboard quá thời gian cho phép");
            } catch (StructuredTaskScope.FailedException e) {
                System.out.println("Một tác vụ thất bại: " + e.getCause());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Luồng gọi đã bị ngắt");
            }
        }
    }

Biên dịch và chạy bằng JDK 26:

    javac --enable-preview --release 26 -encoding UTF-8 -d out src/ScopeTimeout26.java
    java --enable-preview -cp out ScopeTimeout26

Trong ví dụ, tác vụ lấy profile có thể hoàn tất trước deadline, còn tác vụ lấy orders cần lâu hơn. Khi timeout hết hạn, scope hủy tác vụ orders. Joiner mặc định xử lý timeout bằng cách ném `TimeoutException`; khi thoát khỏi khối `try`, `close()` chờ tác vụ bị ngắt thực sự kết thúc.

### Trả về kết quả đã có khi timeout

Không phải ứng dụng nào cũng cần thất bại toàn bộ khi timeout. JDK 26 cho phép Joiner tùy chỉnh cách xử lý timeout. Nếu `onTimeout()` không ném exception, `join()` tiếp tục gọi `result()`; Joiner có thể trả về kết quả của các tác vụ đã hoàn tất trước deadline.

Joiner dựng sẵn `allUntil(predicate)` có thể trả về danh sách các `Subtask`. Khi scope bị hủy hoặc hết hạn, các tác vụ chưa hoàn tất có trạng thái `UNAVAILABLE`; chỉ gọi `get()` với tác vụ ở trạng thái `SUCCESS`.

    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allUntil(
                    subtask -> false
            ),
            config -> config.withTimeout(Duration.ofSeconds(2)))) {

        scope.fork(() -> fetchProfile());
        scope.fork(() -> fetchOrders());

        List<StructuredTaskScope.Subtask<String>> subtasks = scope.join();

        for (var subtask : subtasks) {
            if (subtask.state() == StructuredTaskScope.Subtask.State.SUCCESS) {
                System.out.println(subtask.get());
            }
        }
    }

Chính sách trả kết quả một phần cần được thiết kế rõ ràng. Không coi danh sách thiếu phần tử là thành công đầy đủ; caller cần biết dữ liệu nào chưa có và quyết định có thể tiếp tục nghiệp vụ với dữ liệu đó hay không.

## 5. Interruption là tín hiệu yêu cầu dừng

Java không cưỡng bức kết thúc một luồng đang chạy. Khi scope bị hủy, nó gọi `interrupt()` trên các luồng thực thi tác vụ chưa hoàn tất. Đây là một yêu cầu để mã trong luồng chủ động kết thúc công việc và giải phóng tài nguyên.

Một số thao tác chờ có thể phản hồi trực tiếp bằng cách ném `InterruptedException`, ví dụ:

- `Thread.sleep(...)`
- `Object.wait(...)`
- `Thread.join(...)`
- Một số thao tác lấy phần tử từ hàng đợi hoặc chờ khóa trong các API đồng thời
- Các thao tác I/O trên `InterruptibleChannel` có thể đóng channel và ném `ClosedByInterruptException`

Nếu tác vụ thực hiện tính toán CPU-bound hoặc gọi API không tự phản hồi interruption, nó nên kiểm tra trạng thái ngắt ở các điểm an toàn:

    static long calculate(long limit) throws InterruptedException {
        long total = 0;

        for (long i = 0; i < limit; i++) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException("Subtask was cancelled");
            }

            total += expensiveStep(i);
        }

        return total;
    }

`isInterrupted()` đọc trạng thái mà không xóa nó. Ngược lại, `Thread.interrupted()` vừa kiểm tra vừa xóa trạng thái interrupt của luồng hiện tại; chỉ dùng khi thực sự cần hành vi đó. Với vòng lặp dài, hãy kiểm tra ở ranh giới công việc có thể dừng an toàn để tránh kiểm tra quá dày làm giảm hiệu năng.

## 6. Viết subtask để dừng hợp tác và giải phóng tài nguyên

Nếu tác vụ dùng thao tác interruptible, hãy để `InterruptedException` được truyền ra khỏi Callable sau khi hoàn tất cleanup:

    static String loadRemoteData() throws InterruptedException {
        try {
            Thread.sleep(10_000);
            return "remote-data";
        } finally {
            releaseTemporaryResource();
        }
    }

Khi scope hủy tác vụ, `sleep` ném `InterruptedException`. Khối `finally` vẫn chạy để giải phóng tài nguyên, sau đó luồng kết thúc. Với HTTP client, socket hoặc tài nguyên khác, hãy dùng API có timeout hoặc khả năng đóng/hủy phù hợp; đừng để tác vụ mắc kẹt trong một lời gọi không thể ngắt.

Nếu cần bắt `InterruptedException` để cleanup, hãy ném tiếp exception sau cleanup:

    static Result perform() throws InterruptedException {
        try {
            return blockingOperation();
        } catch (InterruptedException e) {
            cleanup();
            throw e;
        }
    }

Nếu tầng hiện tại không thể ném `InterruptedException` và buộc phải chuyển nó thành một exception khác, phải khôi phục interrupt status trước khi ném:

    try {
        performBlockingWork();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Operation interrupted", e);
    }

Không bắt `InterruptedException` rồi bỏ qua để tiếp tục công việc như chưa có gì xảy ra. Thao tác ném `InterruptedException` thường đã xóa interrupt status; nếu bỏ qua exception, các tầng phía trên có thể không còn nhận biết yêu cầu hủy.

## 7. Interruption của luồng chủ sở hữu và luồng con

Cần phân biệt hai trường hợp:

| Trường hợp | Hành vi |
|---|---|
| Luồng con bị scope hủy | Nhận interrupt; tác vụ cần phản hồi và kết thúc |
| Luồng chủ sở hữu bị interrupt khi đang gọi `join()` | `join()` ném `InterruptedException`; interrupt status của owner được xóa khi exception được ném |
| Owner để `InterruptedException` thoát khỏi khối `try` | `close()` hủy scope, interrupt các tác vụ còn lại và chờ chúng kết thúc |
| Owner bắt exception và tiếp tục trong scope | Có thể gọi lại `join()` vì lần gọi trước đã kết thúc bằng `InterruptedException`; cần quyết định rõ có thực sự muốn tiếp tục chờ hay không |
| Owner bị interrupt trong lúc `close()` đang chờ | `close()` vẫn tiếp tục chờ tất cả luồng con kết thúc, sau đó trả về với interrupt status được đặt |

Ví dụ xử lý interruption ở owner:

    static List<String> loadAll() throws InterruptedException {
        try (var scope = StructuredTaskScope.open(
                StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow())) {

            scope.fork(() -> fetch("profile"));
            scope.fork(() -> fetch("orders"));

            return scope.join();
        }
    }

Nếu phương thức tầng trên có thể truyền tiếp `InterruptedException`, hãy khai báo `throws InterruptedException` và để exception đi lên. Nếu phải chuyển thành exception khác, khôi phục interrupt status trước khi chuyển đổi như ví dụ ở phần trước.

Trong JDK 26, `join()` có thể được gọi lại nếu lần gọi trước bị ngắt. Điều này hữu ích khi interruption chỉ tạm thời và ứng dụng có chính sách tiếp tục chờ. Tuy nhiên, nếu interruption có nghĩa là caller đã yêu cầu hủy request, cách đơn giản và dễ hiểu hơn là để exception thoát khỏi khối `try`; `close()` sẽ hủy các tác vụ còn lại.

## 8. close() không phải lệnh dừng tức thì

`close()` là điểm bảo đảm các tác vụ con không sống lâu hơn scope. Khi đóng, scope:

1. Hủy scope nếu scope chưa bị hủy.
2. Ngăn việc khởi chạy thêm tác vụ.
3. Interrupt các luồng đang thực thi tác vụ chưa hoàn tất.
4. Chờ tất cả các luồng đó kết thúc trước khi cho luồng owner tiếp tục.

Điều này giúp tránh thread leak: một tác vụ con không thể âm thầm chạy tiếp sau khi công việc cha đã rời khỏi scope. Nhưng nó cũng có nghĩa `close()` có thể chờ lâu nếu tác vụ không phản hồi interrupt.

Không dùng timeout của scope như một bảo đảm rằng phương thức sẽ trả về đúng sau N giây. Timeout khởi động cancellation sau N giây; thời gian dọn dẹp vẫn cần thiết. Nếu tác vụ bị kẹt trong thư viện hoặc I/O không hỗ trợ interruption, hãy cấu hình timeout riêng cho thao tác đó, đóng tài nguyên liên quan khi hủy, hoặc thay bằng API có khả năng hủy thực sự.

Cũng không bỏ qua `join()` sau khi đã fork. API yêu cầu owner gọi `join()` để lấy outcome; `close()` sẽ đóng và hủy scope, nhưng ném `IllegalStateException` sau khi đóng nếu owner đã fork mà không thử join.

## 9. Dùng isCancelled() trong giai đoạn fork dài

Một số công việc tạo nhiều subtask theo danh sách. Trong lúc owner vẫn đang fork, một subtask có thể thất bại hoặc timeout có thể làm scope bị hủy. `isCancelled()` cho phép owner ngừng tạo thêm công việc không còn cần thiết:

    try (var scope = StructuredTaskScope.open()) {
        for (var item : items) {
            if (scope.isCancelled()) {
                break;
            }

            scope.fork(() -> process(item));
        }

        scope.join();
    }

`isCancelled()` chỉ quan sát trạng thái; nó không tự hủy scope. Khi trả về `true`, một số luồng con có thể chưa nhận interrupt hoặc chưa kết thúc. Không dùng giá trị này như một phép kiểm tra rằng mọi tác vụ đã dừng.

## 10. Khác biệt quan trọng khi chuyển từ JDK 26 sang JDK 27

JDK 27 là release hiện hành tại ngày 27-11-2026 và tiếp tục Structured Concurrency ở preview lần thứ bảy theo JEP 533. Các nguyên tắc về timeout, cancellation hợp tác, interruption và việc `close()` chờ tác vụ kết thúc vẫn giữ nguyên. Tuy nhiên, API và exception đã thay đổi; không dùng nguyên code JDK 26 để biên dịch bằng JDK 27.

| Nội dung | JDK 26 — JEP 525, preview 6 | JDK 27 — JEP 533, preview 7 |
|---|---|---|
| Kiểu StructuredTaskScope | `StructuredTaskScope<T,R>` | `StructuredTaskScope<T,R,R_X extends Throwable>` |
| Cấu hình timeout | `open(joiner, config -> config.withTimeout(duration))` | Có thêm `open(config -> config.withTimeout(duration))` |
| Callback timeout của Joiner | `onTimeout()` | `timeout()` |
| Timeout với Joiner mặc định | `StructuredTaskScope.TimeoutException` | `ExecutionException` có cause `StructuredTaskScope.CancelledByTimeoutException` |
| Lỗi subtask với Joiner mặc định | `StructuredTaskScope.FailedException` | `ExecutionException` |
| API vẫn preview | Có | Có |

Ví dụ cấu hình timeout với default Joiner của JDK 27:

    import java.time.Duration;
    import java.util.concurrent.ExecutionException;
    import java.util.concurrent.StructuredTaskScope;

    static void runTasks() throws InterruptedException {
        try (var scope = StructuredTaskScope.<String>open(
                config -> config.withTimeout(Duration.ofSeconds(3)))) {

            scope.fork(() -> fetch("profile"));
            scope.fork(() -> fetch("orders"));

            scope.join();

        } catch (ExecutionException e) {
            if (e.getCause()
                    instanceof StructuredTaskScope.CancelledByTimeoutException) {
                System.out.println("Scope hết thời gian");
            } else {
                System.out.println("Subtask thất bại: " + e.getCause());
            }
        }
    }

Trong JDK 27, Joiner tùy chỉnh quyết định kết quả khi timeout qua `timeout()`. Nếu kết quả là exception, API thêm `CancelledByTimeoutException` làm cause. Vì vậy, khi nâng JDK, hãy kiểm tra kiểu exception ở `join()`, generic type của `StructuredTaskScope` và tên callback timeout trước khi sửa code.

## 11. Biên dịch đúng preview release

Structured Concurrency là preview API trong cả JDK 26 và JDK 27. Không cần `--add-modules` vì API nằm trong `java.base`; cần dùng đúng JDK release ở compiler và runtime.

Với ví dụ JDK 26:

    javac --enable-preview --release 26 -encoding UTF-8 -d out src/ScopeTimeout26.java
    java --enable-preview -cp out ScopeTimeout26

Với ví dụ JDK 27:

    javac --enable-preview --release 27 -encoding UTF-8 -d out src/ScopeTimeout27.java
    java --enable-preview -cp out ScopeTimeout27

Cờ `--enable-preview` phải có ở cả hai bước. Class file phụ thuộc preview của JDK 26 không thể chạy bằng JDK 27 chỉ bằng cách thêm cờ preview; hãy biên dịch lại theo release đích và cập nhật code theo API của release đó.

Khi dùng IDE hoặc build tool, kiểm tra riêng JDK của compiler, test worker và application runner. Chỉ bật preview ở compiler mà quên JVM chạy test sẽ khiến ứng dụng thất bại khi nạp class phụ thuộc preview.

## 12. Các lỗi thiết kế cần tránh

- **Bắt và bỏ qua InterruptedException:** làm mất tín hiệu hủy và có thể khiến `close()` chờ rất lâu.
- **Dùng tác vụ không có điểm dừng:** vòng lặp CPU-bound không kiểm tra interrupt hoặc API blocking không có timeout có thể ngăn scope đóng.
- **Coi timeout là hard deadline:** timeout khởi động cancellation, nhưng thời gian cleanup vẫn phụ thuộc tác vụ.
- **Tự tạo thread ngoài scope cho công việc con:** luồng đó không thuộc vòng đời scope và có thể sống sau khi scope đóng.
- **Dùng API từ preview cũ:** các kiểu `ShutdownOnFailure`, `ShutdownOnSuccess`, `shutdown()` hoặc `joinUntil()` trong bài viết cũ không phải mẫu API hiện hành.
- **Gọi get() trước join():** outcome của Subtask chỉ được đọc sau khi owner đã join và subtask đã hoàn tất thành công.
- **Dùng isCancelled() như xác nhận mọi task đã dừng:** trạng thái cancelled có thể được ghi nhận trước khi tất cả luồng con được interrupt hoặc kết thúc.

## 13. Checklist trước khi đưa vào ứng dụng

1. Chọn đúng JDK release và kiểm tra Structured Concurrency đang ở preview lần thứ mấy.
2. Đặt timeout ở scope theo ngân sách của toàn công việc, tính từ thời điểm mở scope.
3. Chọn Joiner đúng yêu cầu: tất cả thành công, kết quả đầu tiên thành công, hoặc chấp nhận kết quả một phần.
4. Bảo đảm mọi tác vụ có thể phản hồi interruption.
5. Với thao tác I/O, đặt timeout hoặc cung cấp cơ chế đóng/hủy tài nguyên.
6. Dùng `finally` hoặc try-with-resources bên trong subtask để cleanup.
7. Để InterruptedException truyền lên hoặc khôi phục interrupt status khi chuyển thành exception khác.
8. Luôn đóng scope bằng try-with-resources và gọi join sau khi fork.
9. Đo thời gian đóng scope dưới điều kiện cancellation để phát hiện tác vụ không hợp tác.
10. Khi nâng từ JDK 26 lên JDK 27, cập nhật Joiner timeout callback và exception mapping.

## Tài liệu chính thức

- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): phạm vi thay đổi của Structured Concurrency trong JDK 26.
- [Java SE 26 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): hợp đồng `open`, `fork`, `join`, `isCancelled`, `close` và timeout.
- [Java SE 26 API — StructuredTaskScope.Joiner](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): chính sách Joiner, `onTimeout()`, `allUntil()` và kết quả một phần.
- [Java SE 26 API — StructuredTaskScope.Configuration](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html): cấu hình timeout bằng `withTimeout(Duration)`.
- [Java SE 26 API — Thread Interruption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html): ý nghĩa interrupt status, `InterruptedException`, `isInterrupted()` và `Thread.interrupted()`.
- [Oracle — Structured Concurrency, Java SE 26 Core Libraries](https://docs.oracle.com/en/java/javase/26/core/structured-concurrency.html): quy trình sử dụng scope, join và close.
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533): thay đổi tiếp theo của API trong JDK 27.
- [Java SE 27 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): API hiện hành, timeout, cancellation, interruption và `close()`.
- [Java SE 27 API — StructuredTaskScope.Joiner](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): callback `timeout()`, chính sách kết quả và exception của Joiner trong preview thứ bảy.
- [Java SE 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận Structured Concurrency là preview lần thứ bảy theo JEP 533.

Tại ngày 27-11-2026, Structured Concurrency vẫn là preview API. Những nguyên tắc cần giữ là timeout khởi động cancellation, interruption chỉ là yêu cầu hợp tác, tác vụ phải tự dừng và `close()` chờ mọi tác vụ kết thúc. Hãy dùng đúng API của JDK 26 hoặc JDK 27 và không dựa vào các ví dụ từ preview cũ.
