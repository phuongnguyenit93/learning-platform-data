# Thử nhóm tác vụ có thời gian chờ trên API preview Java 27

*Tình trạng API được đối chiếu với Java SE 27, JEP 533 và Oracle JDK 27.0.1.1 tại ngày 28/11/2026.*

Bài thực hành này xây dựng một thao tác fan-out/fan-in: một request cần lấy hồ sơ khách hàng, giỏ hàng và trạng thái đủ điều kiện từ ba dịch vụ độc lập. Các lời gọi chạy đồng thời trong một scope, dùng chung deadline hai giây. Nếu tất cả hoàn tất thành công, request tổng hợp kết quả; nếu một tác vụ lỗi hoặc deadline hết hạn, scope hủy các tác vụ còn lại và thu hồi chúng trước khi request tiếp tục.

API được dùng là `java.util.concurrent.StructuredTaskScope` trong JDK 27, thuộc **Structured Concurrency (JEP 533, Seventh Preview)**. Tại ngày đối chiếu, Java 27 đã phát hành GA và bản cập nhật Oracle JDK mới nhất là 27.0.1.1; riêng Structured Concurrency vẫn là preview API, chưa phải API ổn định. Ví dụ bên dưới dùng đúng API Java 27, không dùng chữ ký hoặc ngoại lệ của các preview cũ.

## 1. Mục tiêu của bài thực hành

Sau khi hoàn thành, bạn có thể:

- Nhận diện một thao tác phù hợp với mô hình structured concurrency.
- Mở scope và khởi chạy các subtask bằng virtual thread.
- Thiết lập timeout chung cho toàn bộ nhóm tác vụ.
- Chờ kết quả bằng `join()` và lấy kết quả bằng `Subtask.get()`.
- Phân biệt lỗi của subtask với lỗi do timeout.
- Hiểu cancellation dựa trên interrupt và trách nhiệm của code trong subtask.
- Chạy thử cả trường hợp thành công và trường hợp quá thời gian trên JDK 27.
- Nhận biết các thay đổi của API Java 27 so với preview Java 26.

Tình huống giả định: trang checkout cần ba dữ liệu độc lập. Không dữ liệu nào cần kết quả của dữ liệu khác, nên có thể gọi song song. Chỉ khi cả ba lời gọi thành công thì mới tạo được đối tượng kết quả hoàn chỉnh.

## 2. Structured concurrency giải quyết điều gì?

Với concurrency không có cấu trúc, request cha thường tạo nhiều task rồi giữ các Future hoặc callback ở nhiều nơi. Nếu request bị timeout, lỗi hoặc bị hủy, code phải tự theo dõi từng task để tránh chúng tiếp tục chạy ngoài vòng đời của request.

Structured concurrency nhóm các task con vào một scope có vòng đời gắn với thao tác cha:

- Mở scope trong một khối `try`.
- Fork các subtask trong scope.
- Gọi `join()` để chờ kết quả hoặc một điều kiện kết thúc.
- Xử lý kết quả sau khi join.
- Đóng scope khi rời khỏi khối.

Scope hoạt động như một đơn vị công việc. Khi scope kết thúc, các thread của subtask phải kết thúc trước khi luồng điều khiển đi tiếp ra ngoài scope. Cấu trúc này giúp quản lý lỗi, cancellation và quan sát thread theo quan hệ cha-con.

Trong JDK 27, `StructuredTaskScope` mặc định tạo một virtual thread cho mỗi subtask được fork. Virtual thread phù hợp với nhiều tác vụ I/O đồng thời, chẳng hạn gọi HTTP service hoặc đọc dữ liệu. Chúng không tự làm một phép tính CPU-bound chạy nhanh hơn; hiệu quả đến từ việc quản lý nhiều thao tác chờ I/O với chi phí thread thấp.

## 3. Trạng thái preview và phiên bản JDK phải dùng

| Thành phần | Trạng thái tại ngày 28/11/2026 |
|---|---|
| Java 27 | Đã phát hành GA |
| Oracle JDK 27.0.1.1 | Bản cập nhật phát hành ngày 17/11/2026 |
| Structured Concurrency | JEP 533, preview lần thứ bảy |
| API package | `java.base`, package `java.util.concurrent` |
| Có cần module incubator? | Không |
| Có cần bật preview? | Có, cả khi compile và khi chạy |

Preview API đã có thiết kế, đặc tả và implementation để thử nghiệm, nhưng chưa phải hợp đồng API ổn định. Nó có thể thay đổi hoặc bị loại bỏ ở release sau. Do đó:

- Dùng JDK 27 để biên dịch và chạy bài này.
- Thêm `--enable-preview` ở cả hai bước.
- Không đưa API preview vào public library contract hoặc artifact dùng chung cho môi trường không bật preview.
- Khóa đúng JDK build trong CI để kết quả compile và runtime có thể tái lập.
- Khi chuyển sang một JDK release khác, đọc lại API specification và biên dịch lại mã nguồn.

JDK 26 có Structured Concurrency ở preview lần thứ sáu. Bài này dùng preview lần thứ bảy của JDK 27; không lấy ví dụ JDK 26 rồi giả định có thể biên dịch nguyên trạng trên JDK 27.

## 4. Cấu trúc API Java 27 cần biết

Các thành phần chính:

| API | Vai trò |
|---|---|
| `StructuredTaskScope<T, R, R_X>` | Scope quản lý nhóm subtask |
| `StructuredTaskScope.open(...)` | Mở scope và cấu hình policy |
| `Configuration.withTimeout(Duration)` | Đặt deadline cho scope |
| `Configuration.withName(String)` | Đặt tên scope để quan sát và quản lý |
| `Configuration.withThreadFactory(ThreadFactory)` | Chọn cách tạo thread chạy subtask |
| `scope.fork(Callable)` | Khởi chạy subtask có kết quả |
| `scope.fork(Runnable)` | Khởi chạy subtask không có kết quả |
| `scope.join()` | Chờ nhóm tác vụ và trả kết quả hoặc ném lỗi |
| `scope.close()` | Hủy tác vụ còn chạy và chờ chúng kết thúc |
| `Subtask.get()` | Lấy kết quả của subtask thành công sau khi join |
| `Subtask.exception()` | Lấy exception của subtask thất bại sau khi join |

Trong JDK 27, interface có ba tham số kiểu:

- `T`: kiểu kết quả của từng subtask.
- `R`: kiểu kết quả do `join()` trả về.
- `R_X`: kiểu exception mà `join()` có thể ném.

Ba tham số này làm rõ hợp đồng kiểu của kết quả và lỗi. `StructuredTaskScope` là scope có owner: thread mở scope là thread duy nhất được gọi `fork`, `join` và `close`. Subtask không được tự điều khiển scope của cha.

### Cấu hình mặc định

`StructuredTaskScope.open()` tạo scope với:

- Một virtual thread không đặt tên cho mỗi lần `fork`.
- Không có tên scope.
- Không có timeout.
- Policy mặc định chờ tất cả subtask thành công; nếu một subtask thất bại, scope bị hủy và `join()` ném `ExecutionException`.

JDK 27 bổ sung overload `open(UnaryOperator<Configuration>)`, cho phép thay đổi cấu hình mặc định mà vẫn giữ policy mặc định. Đây là cách ngắn gọn để đặt timeout và tên scope cho trường hợp cần tất cả subtask thành công.

## 5. Deadline của scope hoạt động như thế nào?

Đặt timeout bằng `Configuration.withTimeout(Duration)`:

```java
try (var scope = StructuredTaskScope.open(
        config -> config
                .withName("checkout")
                .withTimeout(Duration.ofSeconds(2)))) {
    // Fork các subtask và join.
}
```

Có bốn điểm quan trọng:

1. **Đồng hồ bắt đầu khi scope được mở.** Timeout bao trùm vòng đời scope, không bắt đầu lại khi gọi `join()`.
2. **Một deadline áp dụng cho cả nhóm.** Các subtask cùng chia sẻ thời hạn hai giây; đây không phải timeout riêng hai giây cho từng subtask.
3. **Khi timeout hết hạn, scope bị hủy.** Các subtask chưa hoàn tất bị interrupt.
4. **Kết quả timeout phụ thuộc Joiner.** Với policy mặc định của `open(configOperator)`, `join()` ném `ExecutionException`, trong đó cause là `StructuredTaskScope.CancelledByTimeoutException`.

Ví dụ: nếu scope mở lúc 10:00:00 và timeout là hai giây, deadline là 10:00:02. Nếu code mất 700 ms để chuẩn bị hoặc fork task, các subtask còn khoảng 1,3 giây. Không được hiểu timeout là “chờ thêm hai giây kể từ lúc join”.

## 6. Bài thực hành: tổng hợp dữ liệu checkout trong hai giây

Tạo file `CheckoutPreview.java`. Ví dụ mô phỏng ba dịch vụ độc lập bằng `Thread.sleep()` để tạo độ trễ có thể kiểm soát. Trong ứng dụng thật, thay các hàm mô phỏng bằng HTTP/database client có timeout riêng.

```java
import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

record CustomerProfile(String customerId, String displayName) {}
record CartSummary(int itemCount, long totalCents) {}
record Eligibility(boolean allowed) {}

record CheckoutView(
        CustomerProfile profile,
        CartSummary cart,
        Eligibility eligibility) {}

public class CheckoutPreview {

    static CheckoutView loadCheckout(
            String customerId,
            boolean simulateSlowEligibility)
            throws InterruptedException, ExecutionException {

        try (var scope = StructuredTaskScope.open(
                config -> config
                        .withName("checkout-request")
                        .withTimeout(Duration.ofSeconds(2)))) {

            // Ba lời gọi độc lập được chạy đồng thời.
            var profile = scope.fork(
                    () -> fetchProfile(customerId));

            var cart = scope.fork(
                    () -> fetchCart(customerId));

            var eligibility = scope.fork(
                    () -> checkEligibility(
                            customerId, simulateSlowEligibility));

            // Policy mặc định: tất cả phải thành công.
            // Timeout hoặc lỗi subtask sẽ làm join ném ExecutionException.
            scope.join();

            // Chỉ đọc kết quả sau khi join hoàn tất thành công.
            return new CheckoutView(
                    profile.get(),
                    cart.get(),
                    eligibility.get());
        }
    }

    private static CustomerProfile fetchProfile(String customerId)
            throws InterruptedException {
        Thread.sleep(250);
        return new CustomerProfile(customerId, "Nguyen An");
    }

    private static CartSummary fetchCart(String customerId)
            throws InterruptedException {
        Thread.sleep(400);
        return new CartSummary(2, 1_250_000);
    }

    private static Eligibility checkEligibility(
            String customerId,
            boolean simulateSlow)
            throws InterruptedException {
        Thread.sleep(simulateSlow ? 5_000 : 350);
        return new Eligibility(true);
    }

    public static void main(String[] args) {
        boolean simulateSlow =
                args.length > 0 && args[0].equalsIgnoreCase("slow");

        try {
            CheckoutView view =
                    loadCheckout("CUS-100", simulateSlow);
            System.out.println("Checkout ready: " + view);

        } catch (ExecutionException e) {
            Throwable cause = e.getCause();

            if (cause instanceof
                    StructuredTaskScope.CancelledByTimeoutException) {
                System.err.println(
                        "Checkout timed out; unfinished calls were cancelled.");
            } else {
                System.err.println(
                        "A checkout subtask failed: " + cause);
            }

        } catch (InterruptedException e) {
            // join() ném InterruptedException và clear interrupt status.
            Thread.currentThread().interrupt();
            System.err.println("Checkout owner was interrupted.");
        }
    }
}
```

Trong ví dụ:

- `profile`, `cart` và `eligibility` là ba subtask có kiểu kết quả khác nhau.
- `fork()` trả về một handle `Subtask` cho mỗi tác vụ.
- `join()` theo policy mặc định chờ tất cả thành công hoặc dừng khi có lỗi/timeout.
- Sau khi join thành công, `get()` lấy đúng kiểu kết quả của từng subtask.
- `try-with-resources` đảm bảo scope được đóng kể cả khi có exception hoặc interruption.

### Chạy trường hợp thành công

Ba tác vụ mô phỏng mất 250 ms, 400 ms và 350 ms. Chúng chạy đồng thời nên tổng thời gian thường gần với tác vụ chậm nhất cộng overhead, thay vì tổng ba độ trễ.

```bash
javac --enable-preview --release 27 CheckoutPreview.java
java --enable-preview CheckoutPreview
```

Kết quả là một `CheckoutView` chứa hồ sơ, giỏ hàng và trạng thái đủ điều kiện.

### Chạy trường hợp timeout

Đối số `slow` làm tác vụ kiểm tra eligibility ngủ năm giây trong khi deadline scope là hai giây:

```bash
java --enable-preview CheckoutPreview slow
```

Khi timeout xảy ra:

1. Scope chuyển sang trạng thái cancelled.
2. Thread chạy `checkEligibility` nhận interrupt.
3. `Thread.sleep()` ném `InterruptedException`, khiến tác vụ mô phỏng kết thúc.
4. `join()` ném `ExecutionException` với cause là `CancelledByTimeoutException`.
5. Khi rời khỏi khối `try`, `close()` bảo đảm các subtask đã kết thúc trước khi code bên ngoài tiếp tục.
6. `catch` nhận diện timeout qua cause và trả thông báo phù hợp.

Không coi thời điểm `join()` phát hiện timeout là thời điểm mọi thread đã kết thúc. Cancellation gửi interrupt; việc kết thúc thực tế còn phụ thuộc subtask có phản hồi interrupt hay không.

## 7. Phân biệt timeout, lỗi subtask và interruption

Ba tình huống này cần được xử lý riêng:

| Tình huống | Kết quả từ `join()` theo policy mặc định | Cách xử lý |
|---|---|---|
| Tất cả subtask thành công | Trả về bình thường (`null`) | Đọc `Subtask.get()` |
| Một subtask thất bại | `ExecutionException`, cause là lỗi đầu tiên | Log/ánh xạ cause thành lỗi nghiệp vụ |
| Timeout scope | `ExecutionException`, cause là `CancelledByTimeoutException` | Trả timeout hoặc fallback được nghiệp vụ cho phép |
| Owner thread bị interrupt khi join | `InterruptedException` | Khôi phục interrupt status sau khi cleanup |

Ví dụ phân nhánh lỗi:

```java
catch (ExecutionException e) {
    Throwable cause = e.getCause();

    if (cause instanceof
            StructuredTaskScope.CancelledByTimeoutException) {
        // Deadline chung của nhóm đã hết.
    } else if (cause instanceof java.io.IOException io) {
        // Một dịch vụ phụ thuộc gặp lỗi I/O.
    } else {
        // Lỗi subtask khác.
    }
}
```

Không chỉ kiểm tra message của exception. Hãy dùng kiểu cause để phân biệt timeout với lỗi từ service con. Nếu cần ánh xạ sang exception nghiệp vụ, có thể dùng overload Joiner nhận exception-supplying function; function phải tạo exception và giữ lỗi gốc làm cause.

## 8. Chọn Joiner theo yêu cầu kết quả

`Joiner` quyết định khi nào scope dừng và `join()` trả về gì. JDK 27 có các policy dựng sẵn:

| Joiner | Khi thành công | Khi có subtask lỗi | Khi timeout |
|---|---|---|---|
| `allSuccessfulOrThrow()` | Trả `List<T>` theo thứ tự fork | Hủy scope và ném `ExecutionException` | Ném `ExecutionException`, cause là `CancelledByTimeoutException` |
| `awaitAllSuccessfulOrThrow()` | Trả `null`; dùng `Subtask` handle để lấy kết quả | Hủy scope và ném `ExecutionException` | Ném `ExecutionException`, cause là `CancelledByTimeoutException` |
| `anySuccessfulOrThrow()` | Trả kết quả của subtask thành công đầu tiên | Chỉ lỗi khi tất cả đều thất bại | Ném `ExecutionException`, cause là `CancelledByTimeoutException` |

Dùng `awaitAllSuccessfulOrThrow()` hoặc policy mặc định khi các subtask có kiểu kết quả khác nhau và bạn cần giữ từng handle. Dùng `allSuccessfulOrThrow()` khi tất cả subtask trả cùng kiểu và muốn nhận một `List` trực tiếp.

Ví dụ với cùng kiểu kết quả:

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

static List<String> fetchBoth() throws InterruptedException, ExecutionException {
    try (var scope = StructuredTaskScope.open(
            Joiner.<String>allSuccessfulOrThrow(),
            config -> config.withTimeout(Duration.ofSeconds(2)))) {

        scope.fork(() -> "price=125000");
        scope.fork(() -> "stock=available");

        // List theo thứ tự fork, không theo thứ tự hoàn thành.
        return scope.join();
    }
}
```

`anySuccessfulOrThrow()` phù hợp khi có nhiều nguồn thay thế và chỉ cần một kết quả tốt, chẳng hạn hỏi nhiều replica. Khi một subtask thành công, Joiner hủy các subtask còn lại. Không dùng policy này cho checkout nếu nghiệp vụ yêu cầu đủ cả hồ sơ, giỏ hàng và eligibility.

## 9. Hủy tác vụ phải hợp tác với interrupt

Timeout không giết thread ngay lập tức. Scope gửi interrupt đến thread đang chạy subtask chưa hoàn tất. Subtask phải phản hồi tín hiệu đó.

Các nguyên tắc khi viết task:

- Không bắt `InterruptedException` rồi bỏ qua.
- Nếu không thể xử lý interrupt tại chỗ, ném tiếp exception hoặc khôi phục interrupt status trước khi kết thúc.
- Với HTTP client, đặt request timeout phù hợp với deadline scope.
- Với JDBC hoặc client thư viện khác, dùng timeout của chính driver/API nếu có.
- Không giữ lock lâu trong khi chờ I/O.
- Tránh vòng lặp CPU vô hạn không kiểm tra trạng thái hủy.
- Không để task tạo thêm thread không thuộc scope rồi trả về ngay.

Ví dụ xử lý interrupt đúng:

```java
static Result callRemote() throws InterruptedException {
    try {
        return doInterruptibleCall();
    } catch (InterruptedException e) {
        // Cho caller và scope biết tác vụ bị hủy.
        throw e;
    }
}
```

Nếu API cấp thấp không ném `InterruptedException` mà trả về trạng thái hoặc dùng cancellation token riêng, cần chuyển tín hiệu interrupt thành cơ chế hủy tương ứng. Không giả định mọi thư viện native hoặc blocking API đều phản hồi interrupt.

## 10. Vì sao close() có thể chờ lâu?

`close()` của `StructuredTaskScope` hủy scope nếu chưa bị hủy, interrupt các subtask chưa xong rồi đợi tất cả thread kết thúc. Đây là bảo đảm quan trọng: code cha không đi tiếp trong khi task con vẫn chạy ngoài scope.

Nhưng điều đó cũng có nghĩa `close()` có thể chờ rất lâu nếu một subtask:

- Chặn trong API không interruptible.
- Bắt `InterruptedException` rồi tiếp tục chạy.
- Gọi HTTP/database client không có timeout và không phản hồi interrupt.
- Chờ một native call không có cơ chế cancellation.
- Tạo tác vụ phụ không thuộc scope và không quản lý vòng đời của chúng.

Do đó, deadline của scope cần đi cùng timeout của dependency. Nếu scope có hai giây, mỗi HTTP request nên có request timeout không vượt quá ngân sách còn lại; không nên để một socket read vô hạn rồi kỳ vọng `close()` luôn trở về đúng hai giây.

Timeout scope giới hạn thời điểm bắt đầu cancellation. Nó không phải bảo đảm hard kill toàn bộ code ở đúng mili giây deadline.

## 11. Quy tắc cấu trúc và quyền sở hữu scope

Để tránh `StructureViolationException`, `WrongThreadException` và lỗi vòng đời:

1. Thread mở scope phải là thread gọi `fork`, `join` và `close`.
2. Không gọi `fork` sau khi đã gọi `join`.
3. Sau khi fork subtask, phải gọi `join` để nhận outcome trước khi scope đóng bình thường.
4. Chỉ gọi `Subtask.get()` sau khi join và khi subtask đã thành công.
5. Chỉ gọi `Subtask.exception()` sau khi join và khi subtask thất bại.
6. Dùng try-with-resources để scope được đóng kể cả khi có exception.
7. Nếu dùng nested scopes, đóng scope con trước scope cha.
8. Không chia sẻ cùng một Joiner instance cho nhiều scope.

Scope cũng ghi nhận các `ScopedValue` binding tại thời điểm mở. Các binding được kế thừa vào subtask. Khi chia sẻ object qua `ScopedValue`, object nên immutable hoặc mọi truy cập phải được đồng bộ phù hợp.

## 12. Những thay đổi quan trọng từ Java 26 sang Java 27

Structured Concurrency đã trải qua nhiều vòng preview. Để không dùng nhầm ví dụ cũ, chú ý các khác biệt sau:

| Chủ đề | Java 26 – Sixth Preview | Java 27 – Seventh Preview |
|---|---|---|
| Kiểu `StructuredTaskScope` | Hai tham số kiểu `T, R` | Ba tham số `T, R, R_X` |
| Kiểu `Joiner` | Hai tham số kiểu | Ba tham số, khai báo kiểu exception từ `join()` |
| Lỗi subtask theo Joiner dựng sẵn | `FailedException` | `ExecutionException` |
| Lỗi timeout | `TimeoutException` trong API preview | `CancelledByTimeoutException` làm cause |
| Callback timeout của Joiner tùy chỉnh | `onTimeout()` | `timeout()` |
| Mở scope với cấu hình mặc định tùy chỉnh | Truyền Joiner và config operator | Có thêm `open(configOperator)` dùng policy mặc định |
| Kiểu kết quả từ `allSuccessfulOrThrow()` | Trả danh sách kết quả | Vẫn trả `List<T>` theo thứ tự fork |

Mã Java 26 có thể không biên dịch trên Java 27 vì thay đổi type parameters, exception và callback. Khi nâng preview, phải đọc lại Javadoc của đúng JDK mục tiêu và sửa mã nguồn theo API mới. Không giữ các tên như `FailedException`, `TimeoutException` hoặc `onTimeout()` trong ví dụ Java 27.

## 13. Chạy preview trong CI và môi trường phát triển

Compile và run phải dùng cùng release có preview:

```bash
javac --enable-preview --release 27 -Xlint:preview -d out CheckoutPreview.java
java --enable-preview -cp out CheckoutPreview
```

Với Maven hoặc Gradle, cấu hình compiler release 27 và bật preview cho cả compile/test/runtime fork. Đừng chỉ bật preview cho compiler mà quên JVM chạy test. Nên khóa JDK 27 vendor/build trong toolchain và lưu `java -version` trong log CI.

Preview không cần `--add-modules` cho ví dụ này vì API nằm trong module `java.base`. Không thêm module incubator chỉ vì đây là API chưa ổn định; preview và incubator là hai trạng thái khác nhau.

Khi triển khai production:

- Chỉ bật preview nếu đã chấp nhận rủi ro API thay đổi.
- Không phát hành thư viện công khai phụ thuộc preview API như thể đó là hợp đồng ổn định.
- Tách mã thử nghiệm khỏi module cần tương thích lâu dài.
- Kiểm thử lại khi cập nhật JDK hoặc chuyển sang preview round tiếp theo.
- Lập kế hoạch thay thế bằng API ổn định nếu preview bị đổi hoặc bỏ.

## 14. Khi nào nên dùng StructuredTaskScope?

**Phù hợp khi:**

- Một request cha gọi nhiều dịch vụ độc lập rồi tổng hợp kết quả.
- Các tác vụ con phải kết thúc trước khi request cha hoàn tất.
- Cần hủy các tác vụ còn lại khi một tác vụ thất bại hoặc khi deadline hết.
- Cần quan sát nhóm thread theo quan hệ scope.
- Tác vụ chủ yếu chờ I/O và có thể phản hồi interrupt.

**Cần cân nhắc cách khác khi:**

- Công việc là background job phải tiếp tục sau khi request cha kết thúc.
- Các task không có quan hệ cha-con hoặc có vòng đời độc lập.
- Cần queue, retry, rate limit hoặc scheduling dài hạn.
- Dependency không có cơ chế timeout/cancellation đáng tin cậy.
- Sản phẩm không thể bật preview feature.

Với JDK 26 hoặc runtime không bật preview, dùng API ổn định như `ExecutorService`, virtual-thread-per-task executor và `Future`/`invokeAll` với timeout; hoặc `CompletableFuture` với policy timeout phù hợp. Các lựa chọn đó vẫn được hỗ trợ, nhưng ứng dụng phải tự quản lý việc hủy, chờ và liên kết vòng đời task cẩn thận hơn. Không dùng API JDK 27 preview trong artifact cần chạy trên JDK 26.

## 15. Mở rộng bài thực hành

Sau khi chạy được ví dụ, thử các thay đổi sau:

1. **Giảm timeout:** đổi hai giây thành 100 ms và quan sát tác vụ nào bị interrupt.
2. **Tạo lỗi service:** cho `fetchCart()` ném `IOException`; xác nhận `join()` ném `ExecutionException` và cause là `IOException`.
3. **Đổi Joiner:** dùng `Joiner.allSuccessfulOrThrow()` với ba tác vụ trả cùng kiểu `String`, rồi kiểm tra thứ tự danh sách theo thứ tự fork.
4. **Dùng nguồn thay thế:** gọi hai replica bằng `anySuccessfulOrThrow()`; quan sát replica còn lại bị hủy khi có kết quả đầu tiên.
5. **Đặt tên scope:** đổi tên scope và xem thông tin trong thread dump/JFR của JDK 27.
6. **Kiểm thử interruption:** interrupt thread owner khi nó đang join; xác nhận cleanup hoàn tất và interrupt status được khôi phục.
7. **Kiểm thử task không hợp tác:** tạm thời mô phỏng một subtask bỏ qua interrupt; quan sát vì sao `close()` có thể chờ lâu. Không chạy tình huống này trên môi trường production.

Với mỗi lần thử, ghi lại JDK build, timeout, số subtask, thời gian hoàn thành, exception và thời gian từ lúc cancellation đến khi scope đóng xong.

## 16. Checklist hoàn thành

- [ ] Đã xác nhận dùng JDK 27 và đúng build mục tiêu.
- [ ] Đã bật preview khi compile và khi chạy.
- [ ] Đã phân biệt preview API với incubator module.
- [ ] Đã mở scope trong try-with-resources.
- [ ] Đã fork các tác vụ độc lập trước khi join.
- [ ] Đã cấu hình tên scope và timeout.
- [ ] Đã hiểu timeout bắt đầu ngay khi scope mở.
- [ ] Đã lấy kết quả sau join, không gọi `Subtask.get()` trước đó.
- [ ] Đã phân biệt lỗi subtask với `CancelledByTimeoutException`.
- [ ] Đã bảo đảm task phản hồi interrupt.
- [ ] Đã đặt timeout cho HTTP/database client ở tầng dependency.
- [ ] Đã xác nhận `close()` đợi mọi subtask kết thúc.
- [ ] Đã kiểm tra thay đổi API từ Java 26 preview sang Java 27 preview.
- [ ] Đã ghi lại JDK build và kết quả chạy để tái lập.

## Tài liệu tham chiếu

1. [Oracle Java SE 27 API – StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
2. [Oracle Java SE 27 API – StructuredTaskScope.Joiner](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html)
3. [Oracle Java SE 27 – Structured Concurrency Developer Guide](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html)
4. [JEP 533 – Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533)
5. [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
6. [Oracle Consolidated JDK 27 Release Notes – JDK 27.0.1.1](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
7. [Oracle Java SE 26 API – StructuredTaskScope (Sixth Preview, để đối chiếu thay đổi)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)

