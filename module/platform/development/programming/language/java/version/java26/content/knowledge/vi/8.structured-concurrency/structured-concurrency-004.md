# Mở scope trong try-with-resources

`StructuredTaskScope` được thiết kế để mở trong câu lệnh `try-with-resources`. Scope gom các tác vụ con liên quan thành một đơn vị công việc: task cha fork các subtask, chờ kết quả bằng `join()`, xử lý kết quả rồi rời khỏi block. Khi block kết thúc, Java tự gọi `close()` để hủy các subtask còn chạy và chờ chúng kết thúc. Nhờ đó, luồng con không tiếp tục chạy ngoài vòng đời của công việc đã tạo ra nó.

Trong Java 26, Structured Concurrency là **JEP 525 — Sixth Preview**. API vẫn là preview trong JDK 27 qua **JEP 533 — Seventh Preview**. Bài này dùng API factory `StructuredTaskScope.open(...)` hiện hành, đồng thời chỉ rõ khác biệt exception/API giữa hai JDK để khi nâng cấp không dùng nhầm ví dụ từ các vòng preview cũ.

## 1. Vì sao scope nằm trong try-with-resources?

`StructuredTaskScope` là interface triển khai `AutoCloseable`. Việc đặt scope làm resource của `try-with-resources` tạo ra một ranh giới vòng đời rõ ràng:

1. `open()` tạo scope và gán luồng hiện tại làm **owner thread**.
2. Owner gọi `fork()` để chạy các subtask trong scope.
3. Owner gọi `join()` để chờ kết quả theo chính sách của scope.
4. Owner xử lý kết quả sau khi join.
5. Khi rời block, Java tự gọi `close()`; scope hủy công việc còn dang dở và chờ các thread con kết thúc.

Mỗi `fork()` mặc định tạo một virtual thread cho subtask. Scope không chỉ quản lý kết quả mà còn quản lý thời gian sống của các thread này. Khi block kết thúc, không có subtask nào được phép tiếp tục chạy như một công việc độc lập ngoài scope.

## 2. Mở scope cơ bản bằng `open()`

Ví dụ dưới đây mô phỏng một trang tổng quan cần lấy hồ sơ người dùng và số đơn hàng từ hai nguồn độc lập. Hai tác vụ có thể chạy đồng thời vì chúng không phụ thuộc kết quả của nhau.

```java
import java.util.concurrent.StructuredTaskScope;

public class StructuredScopeDemo {
    record UserProfile(String name) {}
    record OrderSummary(int count) {}

    static UserProfile fetchProfile(String userId) throws InterruptedException {
        Thread.sleep(150); // Mô phỏng I/O có thể bị interrupt
        return new UserProfile("An");
    }

    static OrderSummary fetchOrders(String userId) throws InterruptedException {
        Thread.sleep(250); // Mô phỏng I/O có thể bị interrupt
        return new OrderSummary(3);
    }

    static String loadDashboard(String userId) throws InterruptedException {
        try (var scope = StructuredTaskScope.open()) {
            var profileTask = scope.fork(() -> fetchProfile(userId));
            var ordersTask = scope.fork(() -> fetchOrders(userId));

            // Chờ cả hai subtask thành công; nếu một subtask lỗi,
            // chính sách mặc định sẽ hủy các subtask còn lại.
            scope.join();

            // Chỉ đọc kết quả sau khi join hoàn tất thành công.
            UserProfile profile = profileTask.get();
            OrderSummary orders = ordersTask.get();

            return profile.name() + " - " + orders.count() + " orders";
        }
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println(loadDashboard("user-42"));
    }
}
```

Ở ví dụ này, `open()` dùng chính sách mặc định: chờ tất cả subtask thành công; nếu một subtask thất bại thì scope bị hủy và các subtask chưa hoàn tất bị interrupt. Khi tất cả thành công, `join()` trả về `null`, còn kết quả riêng được lấy từ `Subtask.get()`.

`Subtask.get()` chỉ được gọi bởi owner sau khi đã `join()` và subtask tương ứng hoàn tất thành công. Gọi `get()` trước `join()` hoặc lấy kết quả của subtask thất bại là sai thứ tự sử dụng API.

## 3. `open()` tạo cấu hình mặc định nào?

`StructuredTaskScope.open()` tạo scope với cấu hình mặc định:

- Dùng `ThreadFactory` tạo virtual thread không đặt tên cho từng subtask.
- Không đặt tên scope để theo dõi.
- Không đặt timeout.
- Owner là thread đã gọi `open()`.
- Chính sách mặc định chờ mọi subtask thành công hoặc hủy khi có subtask thất bại.

Các cách mở scope phổ biến:

| Cách mở | Mục đích | Giá trị `join()` |
| --- | --- | --- |
| `StructuredTaskScope.open()` | Dùng chính sách mặc định; phù hợp khi cần các subtask khác kiểu kết quả | `null` nếu tất cả thành công |
| `StructuredTaskScope.open(joiner)` | Chọn chính sách kết quả/cancellation bằng `Joiner` | Phụ thuộc Joiner; có thể là một kết quả hoặc danh sách |
| `StructuredTaskScope.open(joiner, configOperator)` | Chọn Joiner và cấu hình tên, timeout hoặc thread factory | Phụ thuộc Joiner và timeout |

JDK 27 bổ sung `open(configOperator)` để dùng chính sách mặc định nhưng tùy chỉnh cấu hình mà không cần truyền Joiner. Overload này chưa có trong JDK 26.

## 4. Chọn Joiner khi mở scope

`Joiner` quyết định khi nào scope được xem là hoàn tất, khi nào cần hủy các subtask còn lại và `join()` trả về kết quả gì.

### Chờ tất cả subtask cùng kiểu kết quả

Nếu các subtask trả về cùng kiểu và muốn nhận một danh sách kết quả, dùng `Joiner.allSuccessfulOrThrow()`:

```java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

static List<String> loadSections() throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow())) {

        scope.fork(() -> "profile section");
        scope.fork(() -> "orders section");
        scope.fork(() -> "recommendations section");

        // Trả về danh sách theo thứ tự fork nếu tất cả đều thành công.
        return scope.join();
    }
}
```

Joiner này tự thu thập kết quả, vì vậy không cần giữ từng `Subtask` chỉ để gọi `get()`. Nếu bất kỳ subtask nào thất bại, scope hủy các subtask còn lại và `join()` ném exception theo phiên bản JDK.

### Chỉ cần kết quả thành công đầu tiên

Khi nhiều nguồn có thể cung cấp cùng một kết quả và ứng dụng chỉ cần nguồn trả về thành công đầu tiên, dùng `Joiner.anySuccessfulOrThrow()`:

```java
static String fetchFromFirstAvailable() throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>anySuccessfulOrThrow())) {

        scope.fork(() -> queryPrimary());
        scope.fork(() -> queryReplica());

        return scope.join();
    }
}
```

Khi một subtask thành công, Joiner hủy các subtask còn lại và `join()` trả kết quả thành công đó. Nếu tất cả đều thất bại, `join()` ném exception. Các subtask phải phản hồi interrupt để scope có thể đóng nhanh.

### Các subtask khác kiểu kết quả

Nếu mỗi subtask trả về một kiểu khác nhau, dùng `open()` mặc định hoặc `Joiner.awaitAllSuccessfulOrThrow()`, giữ lại các `Subtask` và lấy kết quả sau `join()`:

```java
try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.awaitAllSuccessfulOrThrow())) {

    var userTask = scope.fork(() -> fetchUser());       // User
    var paymentTask = scope.fork(() -> fetchPayment()); // Payment

    scope.join();

    User user = userTask.get();
    Payment payment = paymentTask.get();
    return new CheckoutContext(user, payment);
}
```

Joiner này chờ tất cả subtask thành công nhưng không tạo danh sách kết quả chung. Đây là cách phù hợp khi các kiểu kết quả khác nhau và owner cần giữ từng handle.

## 5. Tùy chỉnh tên, timeout và thread factory

Overload nhận `configOperator` cho phép thay đổi cấu hình mặc định. Ví dụ đặt tên scope để theo dõi và giới hạn thời gian:

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.StructuredTaskScope;

static List<String> loadWithDeadline() throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow(),
            config -> config
                    .withName("dashboard-load")
                    .withTimeout(Duration.ofSeconds(2)))) {

        scope.fork(() -> fetchProfileSection());
        scope.fork(() -> fetchOrderSection());

        return scope.join();
    }
}
```

Timeout bắt đầu khi scope được mở, không phải lúc gọi `join()`. Nếu thời hạn hết trước hoặc trong khi join, scope bị hủy và các subtask chưa hoàn tất bị interrupt. Chính sách Joiner quyết định `join()` trả kết quả dự phòng hay ném exception khi timeout.

Có thể cung cấp `ThreadFactory` riêng nếu cần đặt tên virtual thread hoặc có yêu cầu tạo thread đặc thù:

```java
var factory = Thread.ofVirtual().name("dashboard-task-", 0).factory();

try (var scope = StructuredTaskScope.open(
        StructuredTaskScope.Joiner.<String>allSuccessfulOrThrow(),
        config -> config.withThreadFactory(factory))) {

    scope.fork(() -> fetchProfileSection());
    scope.fork(() -> fetchOrderSection());
    List<String> sections = scope.join();
}
```

Không cần tự tạo executor chỉ để chạy các subtask thông thường; nếu không cấu hình factory, scope đã tạo virtual thread cho từng subtask.

## 6. Điều gì xảy ra khi block kết thúc?

`try-with-resources` tự gọi `scope.close()` ở mọi đường thoát khỏi block, kể cả khi có `return` hoặc exception. `close()` thực hiện các bước:

1. Hủy scope nếu scope chưa bị hủy.
2. Ngăn không cho bắt đầu subtask mới.
3. Gửi interrupt đến các thread đang chạy subtask chưa hoàn tất.
4. Chờ tất cả thread của subtask kết thúc rồi mới cho owner tiếp tục ra ngoài block.

Nếu `join()` đã chờ tất cả subtask hoàn tất, `close()` chủ yếu hoàn tất việc đóng scope. Nếu Joiner đã hủy scope sau kết quả đầu tiên hoặc lỗi, `close()` vẫn đợi các thread bị interrupt kết thúc.

Đây là lý do scope phải nằm trong `try-with-resources`: block định nghĩa chính xác phạm vi mà các subtask được phép sống. Không giữ scope trong một field toàn cục hoặc trả scope cho code bên ngoài block để sử dụng sau đó.

## 7. Quy tắc owner, join và close

Các quy tắc sau là một phần của hợp đồng API:

- Chỉ **owner thread** đã gọi `open()` được gọi `fork()`, `join()` và `close()`.
- Gọi tất cả `fork()` trước khi gọi `join()`; không fork thêm sau khi đã join.
- Sau khi fork subtask, owner phải gọi `join()` để lấy outcome trước khi scope đóng.
- `join()` chỉ được gọi một lần để lấy outcome; có thể gọi lại nếu lần trước ném `InterruptedException`.
- `Subtask.get()` chỉ được gọi sau join và khi subtask ở trạng thái thành công.
- Nếu rời block sau khi fork mà chưa gọi `join()`, `close()` vẫn hủy và chờ các subtask, sau đó ném `IllegalStateException`.

Không gọi `close()` thủ công trong block nếu đã dùng `try-with-resources`; Java sẽ tự đóng resource. Gọi thủ công dễ tạo thứ tự đóng khó đọc và các thao tác tiếp theo trên scope đã đóng sẽ không hợp lệ.

## 8. Cancellation và xử lý interrupt

Cancellation trong Structured Concurrency dựa trên interrupt. Nó là tín hiệu yêu cầu subtask dừng, không phải thao tác cưỡng bức kết thúc thread ngay lập tức.

Subtask nên:

- Dùng API blocking có hỗ trợ interrupt khi phù hợp.
- Không bắt `InterruptedException` rồi bỏ qua.
- Nếu không thể truyền tiếp exception, khôi phục trạng thái interrupt bằng `Thread.currentThread().interrupt()` rồi thoát.
- Giải phóng tài nguyên trong `finally` hoặc try-with-resources.

Ví dụ:

```java
static String fetchData() throws InterruptedException {
    try {
        // Mô phỏng công việc chờ có thể bị interrupt.
        Thread.sleep(5_000);
        return "data";
    } catch (InterruptedException e) {
        // Có thể ghi log hoặc dọn dẹp trước khi kết thúc.
        throw e;
    }
}
```

Nếu subtask chờ mãi trong một API không phản hồi interrupt, `close()` cũng phải chờ thread đó kết thúc và có thể chặn vô thời hạn. Scope bảo đảm không bỏ rơi thread, nhưng không thể ép một tác vụ không hợp tác phải dừng.

`join()` có thể ném `InterruptedException` nếu owner bị interrupt trong khi chờ. Khi exception này được ném, trạng thái interrupt của owner đã được xóa theo hợp đồng `InterruptedException`. Nếu bắt exception để xử lý tại chỗ mà không truyền tiếp, hãy cân nhắc khôi phục trạng thái interrupt trước khi thoát:

```java
try (var scope = StructuredTaskScope.open()) {
    scope.fork(() -> fetchData());
    scope.join();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", e);
}
```

`close()` vẫn chờ các thread con kết thúc ngay cả khi chính thread owner bị interrupt trong lúc đóng; sau khi đợi xong, close hoàn tất với trạng thái interrupt được đặt lại.

## 9. Xử lý lỗi theo phiên bản JDK

API đã thay đổi exception contract giữa các vòng preview. Cùng một mẫu `try-with-resources` vẫn dùng được, nhưng kiểu exception cần xử lý khác nhau.

| Nội dung | JDK 26 — JEP 525, Sixth Preview | JDK 27 — JEP 533, Seventh Preview |
| --- | --- | --- |
| Kiểu scope | `StructuredTaskScope<T,R>` | `StructuredTaskScope<T,R,R_X extends Throwable>` |
| `open()` mặc định khi subtask thất bại | Ném `StructuredTaskScope.FailedException` (unchecked) | Ném `ExecutionException` (checked) |
| `join()` | Có thể ném `InterruptedException` và `FailedException` tùy outcome | Ném kiểu exception `R_X` của Joiner và `InterruptedException` |
| `Joiner.allSuccessfulOrThrow()` | Trả `List<T>` theo thứ tự fork | Vẫn trả `List<T>` theo thứ tự fork |
| Joiner lấy kết quả thành công đầu tiên | Tên `anySuccessfulOrThrow()` | Giữ tên `anySuccessfulOrThrow()` |
| Cấu hình chỉ timeout, không custom Joiner | Chưa có `open(configOperator)` riêng | Có `open(configOperator)` |
| Custom Joiner xử lý timeout | Hook `onTimeout()` | Hook `timeout()` |

Trong JDK 26, có thể bắt lỗi của chính sách mặc định như sau:

```java
try (var scope = StructuredTaskScope.open()) {
    scope.fork(() -> fetchProfile());
    scope.fork(() -> fetchOrders());
    scope.join();
} catch (StructuredTaskScope.FailedException e) {
    Throwable cause = e.getCause();
    throw new IllegalStateException("A subtask failed", cause);
}
```

Trong JDK 27, lỗi của `open()` mặc định là checked `ExecutionException`:

```java
try (var scope = StructuredTaskScope.open()) {
    scope.fork(() -> fetchProfile());
    scope.fork(() -> fetchOrders());
    scope.join();
} catch (java.util.concurrent.ExecutionException e) {
    Throwable cause = e.getCause();
    throw new IllegalStateException("A subtask failed", cause);
}
```

Với Joiner, exception phụ thuộc chính sách và có thể là kiểu do exception-supplying function chỉ định. Trong JDK 27, kiểu exception này là tham số generic `R_X`; đây là thay đổi cần chú ý khi tự triển khai `Joiner` hoặc khai báo kiểu scope tường minh.

## 10. Bật preview trên JDK 26 và JDK 27

Structured Concurrency chưa phải API permanent. Cần bật preview ở cả compile time và runtime, đồng thời biên dịch và chạy bằng cùng phiên bản JDK.

Với JDK 26:

```bash
javac --enable-preview --release 26 -d out src/StructuredScopeDemo.java
java --enable-preview -cp out StructuredScopeDemo
```

Với JDK 27:

```bash
javac --enable-preview --release 27 -d out src/StructuredScopeDemo.java
java --enable-preview -cp out StructuredScopeDemo
```

Preview class file gắn với phiên bản JDK đã biên dịch. Khi chuyển từ JDK 26 sang JDK 27, hãy biên dịch lại và kiểm tra các điểm khác biệt exception/API ở phần trước.

Các ví dụ cũ dùng constructor như `new StructuredTaskScope.ShutdownOnFailure()` hoặc `new StructuredTaskScope.ShutdownOnSuccess()` thuộc những vòng preview trước. Từ API hiện hành, mở scope bằng static factory `StructuredTaskScope.open(...)` và chọn chính sách bằng `Joiner`.

## 11. Checklist khi mở scope

- [ ] Scope được mở ngay trong `try-with-resources`.
- [ ] Chọn đúng `open()` mặc định hoặc `open(Joiner, ...)` theo outcome cần lấy.
- [ ] Tất cả `fork()` được gọi trước `join()`.
- [ ] Owner thread là nơi gọi `fork()`, `join()` và đóng scope.
- [ ] Chỉ đọc `Subtask.get()` sau khi join thành công.
- [ ] Mọi subtask đều phản hồi interrupt và giải phóng tài nguyên.
- [ ] Đã xử lý `InterruptedException` và exception theo đúng JDK đích.
- [ ] Bật preview ở cả biên dịch và runtime.
- [ ] Không dùng constructor/Joiner cũ từ các vòng preview trước.

## Ghi nhớ

- `try (var scope = StructuredTaskScope.open())` mở scope và tự gọi `close()` khi block kết thúc.
- `fork()` khởi chạy subtask; mặc định mỗi subtask chạy trên virtual thread.
- `join()` chờ kết quả theo chính sách Joiner; phải gọi sau khi fork và trước khi scope đóng.
- `close()` hủy công việc còn lại, interrupt thread con chưa xong và đợi chúng kết thúc.
- Subtask phải hợp tác với interrupt; nếu không, `close()` có thể chờ vô thời hạn.
- Chỉ owner thread được thao tác với scope; không fork sau join.
- Structured Concurrency vẫn là preview: JDK 26 dùng JEP 525, JDK 27 dùng JEP 533.
- Exception mặc định đổi từ `FailedException` ở JDK 26 sang `ExecutionException` ở JDK 27.

## Tài liệu tham khảo

- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525) — phiên bản preview trong JDK 26.
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533) — phiên bản preview trong JDK 27.
- [StructuredTaskScope, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) — `open`, `fork`, `join`, `close`, Joiner và cấu hình scope.
- [StructuredTaskScope.FailedException, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.FailedException.html) — exception contract trong JDK 26.
- [Structured Concurrency, Java SE 26 Core Libraries](https://docs.oracle.com/en/java/javase/26/core/structured-concurrency.html) — quy trình sử dụng scope, Joiner và timeout.
- [StructuredTaskScope, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) — generic exception type, `ExecutionException`, overload `open(configOperator)` và vòng đời scope.
- [StructuredTaskScope.Joiner, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html) — các Joiner chuẩn và hook `timeout()`.
- [Structured Concurrency, Java SE 27 Core Libraries](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html) — hướng dẫn thực hành hiện hành và các chính sách Joiner.
