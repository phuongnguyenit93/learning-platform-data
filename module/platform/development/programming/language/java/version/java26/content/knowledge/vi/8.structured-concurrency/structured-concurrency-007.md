# Joiner để gom kết quả hoặc chọn kết quả thành công

## 1. Mục tiêu và bối cảnh phiên bản

Trong Structured Concurrency, một tác vụ cha có thể fork nhiều tác vụ con chạy đồng thời. Sau khi fork, tác vụ cha cần một chính sách rõ ràng để quyết định khi nào dừng chờ, xử lý lỗi ra sao và lấy kết quả nào. `StructuredTaskScope.Joiner` biểu diễn chính sách đó.

Bài học tập trung vào các lựa chọn phổ biến trong JDK 27:

- `Joiner.allSuccessfulOrThrow()`: gom kết quả của tất cả tác vụ con nếu tất cả đều thành công.
- `Joiner.anySuccessfulOrThrow()`: lấy kết quả của tác vụ đầu tiên hoàn thành thành công.
- `Joiner.awaitAllSuccessfulOrThrow()`: chờ tất cả tác vụ thành công, sau đó lấy kết quả từ các handle `Subtask`.
- `Joiner.allUntil(predicate)`: thu thập trạng thái các tác vụ và hủy scope khi một điều kiện hoàn thành được thỏa mãn.

Structured Concurrency vẫn là preview API:

| JDK | JEP | Trạng thái |
|---|---|---|
| JDK 26 | JEP 525 | Preview lần thứ sáu |
| JDK 27 | JEP 533 | Preview lần thứ bảy |

Tính đến ngày 27/11/2026, JDK 27 là feature release mới hơn. Theo lộ trình Oracle, JDK 26 đã kết thúc vòng đời hỗ trợ vào tháng 09/2026; chính sách hỗ trợ thực tế vẫn tùy nhà cung cấp JDK. Các ví dụ trong bài dùng API JDK 27 và cần bật preview khi biên dịch lẫn chạy. Không dùng các tên phương thức hoặc cách xử lý lỗi từ những vòng preview cũ.

## 2. Joiner quyết định kết quả của join()

Một `Joiner` được truyền vào khi mở `StructuredTaskScope`. Nó quan sát các tác vụ con được fork và các tác vụ hoàn tất. Khi các tác vụ hoàn tất hoặc scope bị hủy, Joiner tạo kết quả hoặc exception mà `scope.join()` trả về.

Luồng cơ bản:

1. Thread sở hữu scope mở scope bằng `StructuredTaskScope.open(joiner)`.
2. Thread đó gọi `scope.fork(...)` để tạo các tác vụ con.
3. Các tác vụ con chạy đồng thời, mặc định trên virtual thread.
4. Thread sở hữu gọi `scope.join()`.
5. Joiner áp dụng chính sách: chờ tất cả, lấy một kết quả thành công, hoặc hủy scope khi đạt điều kiện.
6. Kết quả của `join()` được xử lý trong thread sở hữu.
7. `try-with-resources` đóng scope và đợi các thread con kết thúc.

Một Joiner có thể trả về một giá trị tổng hợp, danh sách kết quả, danh sách handle `Subtask` hoặc không trả về giá trị hữu ích. Vì thế, kiểu trả về của `join()` phụ thuộc Joiner được chọn.

### 2.1. Chọn Joiner theo nhu cầu

| Nhu cầu | Joiner | Giá trị trả về của `join()` |
|---|---|---|
| Cần tất cả kết quả cùng kiểu và yêu cầu tất cả thành công | `allSuccessfulOrThrow()` | `List<T>`, theo thứ tự fork |
| Chỉ cần một kết quả thành công đầu tiên | `anySuccessfulOrThrow()` | `T` |
| Các tác vụ có kiểu kết quả khác nhau, cần lấy từng kết quả bằng handle | `awaitAllSuccessfulOrThrow()` | `null`; lấy qua `Subtask.get()` |
| Muốn thu thập trạng thái và tự định nghĩa điều kiện hủy | `allUntil(predicate)` | `List<Subtask<T>>` |

Không phải mọi Joiner đều phù hợp với mọi tình huống. Ví dụ, `allSuccessfulOrThrow()` tiện cho danh sách kết quả đồng kiểu; còn khi một tác vụ trả về `User`, tác vụ khác trả về `List<Order>`, hãy giữ handle và dùng `awaitAllSuccessfulOrThrow()`.

## 3. Gom kết quả của tất cả tác vụ: allSuccessfulOrThrow()

### 3.1. Hành vi

`Joiner.allSuccessfulOrThrow()` chờ tất cả tác vụ con hoàn tất thành công. Nếu tất cả thành công, `join()` trả về một `List<T>` chứa các kết quả theo đúng thứ tự gọi `fork()`, không phải thứ tự hoàn thành.

Nếu một tác vụ thất bại:

- Scope bị hủy.
- Các tác vụ chưa hoàn tất nhận tín hiệu interrupt.
- `join()` ném `ExecutionException`.
- Exception gốc từ tác vụ thất bại đầu tiên được đặt làm cause.

Nếu không fork tác vụ nào, `join()` trả về danh sách rỗng.

### 3.2. Ví dụ: lấy dữ liệu từ ba dịch vụ

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class AllResultsExample {
    static String fetch(String service) throws InterruptedException {
        // Thay bằng lời gọi I/O thực tế.
        Thread.sleep(100);
        return "result-from-" + service;
    }

    public static void main(String[] args) throws Exception {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String>allSuccessfulOrThrow())) {

            scope.fork(() -> fetch("catalog"));
            scope.fork(() -> fetch("pricing"));
            scope.fork(() -> fetch("inventory"));

            // Chỉ trả về khi cả ba tác vụ thành công.
            List<String> results = scope.join();

            // Thứ tự tương ứng: catalog, pricing, inventory.
            results.forEach(System.out::println);
        }
    }
}
~~~

Ví dụ trên không cần giữ từng đối tượng `Subtask`. Joiner thu thập kết quả và trả về danh sách trực tiếp. Điều này giảm phần code quản lý handle khi các tác vụ có cùng kiểu kết quả.

### 3.3. Thứ tự kết quả

Giả sử thứ tự fork là:

~~~java
scope.fork(() -> fetch("A"));
scope.fork(() -> fetch("B"));
scope.fork(() -> fetch("C"));
~~~

Dù tác vụ C hoàn thành trước, sau đó A và cuối cùng B, danh sách do `allSuccessfulOrThrow()` trả về vẫn theo thứ tự `A, B, C`.

Đây là điểm khác với `anySuccessfulOrThrow()`, vốn trả về kết quả của tác vụ thành công đầu tiên theo thời gian hoàn tất.

## 4. Chọn kết quả thành công đầu tiên: anySuccessfulOrThrow()

### 4.1. Hành vi

`Joiner.anySuccessfulOrThrow()` phù hợp khi có nhiều cách lấy cùng một loại dữ liệu và chỉ cần một kết quả thành công. Ví dụ:

- Gửi truy vấn tới nhiều replica và dùng replica trả lời thành công đầu tiên.
- Thử nhiều nguồn dịch vụ dự phòng.
- Gọi nhiều endpoint tương đương và chấp nhận kết quả đầu tiên hợp lệ.

Joiner không dừng ngay khi một tác vụ bất kỳ hoàn tất. Nó chỉ dừng khi có tác vụ hoàn tất thành công:

- Nếu một tác vụ thành công, scope bị hủy và `join()` trả về kết quả đó.
- Các tác vụ còn chạy bị interrupt.
- Nếu tất cả tác vụ đều thất bại, `join()` ném `ExecutionException` với exception của một tác vụ thất bại làm cause.
- Nếu không fork tác vụ nào, `join()` ném `ExecutionException` với `NoSuchElementException` làm cause.

### 4.2. Ví dụ: truy vấn các replica

~~~java
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class FirstSuccessfulExample {
    static String queryReplica(String replica)
            throws InterruptedException {
        // Thay bằng truy vấn mạng thực tế.
        Thread.sleep(replica.equals("replica-b") ? 50 : 200);
        return "data-from-" + replica;
    }

    public static void main(String[] args) throws Exception {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String>anySuccessfulOrThrow())) {

            scope.fork(() -> queryReplica("replica-a"));
            scope.fork(() -> queryReplica("replica-b"));
            scope.fork(() -> queryReplica("replica-c"));

            String result = scope.join();
            System.out.println(result);
        }
    }
}
~~~

Trong ví dụ, replica B có thể trả lời trước. Khi kết quả thành công đầu tiên được ghi nhận, scope hủy các tác vụ còn lại. Kết quả được trả về trực tiếp, không cần giữ danh sách `Subtask`.

### 4.3. “Đầu tiên thành công” không có nghĩa “hoàn tất đầu tiên”

Giả sử:

- Replica A hoàn tất sau 30 ms nhưng ném `IOException`.
- Replica B hoàn tất sau 80 ms và trả dữ liệu hợp lệ.
- Replica C vẫn đang chạy.

`anySuccessfulOrThrow()` không trả lỗi của A ngay lập tức. Nó tiếp tục chờ. Khi B thành công, Joiner hủy C và trả kết quả của B.

Nếu A, B và C đều thất bại, Joiner mới kết thúc bằng exception.

Không dùng Joiner này khi cần thu thập mọi lỗi từ mọi replica. Nếu cần phân tích toàn bộ lỗi, dùng một chính sách thu thập trạng thái phù hợp, chẳng hạn `allUntil`, hoặc một Joiner tùy chỉnh.

## 5. Chờ tất cả thành công rồi lấy kết quả qua Subtask

### 5.1. Khi nào cần awaitAllSuccessfulOrThrow?

Khi các tác vụ trả về kiểu khác nhau, một danh sách `List<T>` duy nhất không thuận tiện. Có thể dùng `awaitAllSuccessfulOrThrow()` để chỉ chờ và xác nhận tất cả thành công, sau đó lấy từng kết quả từ handle `Subtask`.

Ví dụ một màn hình dashboard cần:

- Hồ sơ người dùng kiểu `User`.
- Danh sách đơn hàng kiểu `List<Order>`.
- Quyền truy cập kiểu `Permissions`.

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;
import java.util.concurrent.StructuredTaskScope.Subtask;

record User(String name) {}
record Order(String id) {}
record Permissions(boolean canEdit) {}
record Dashboard(
        User user,
        List<Order> orders,
        Permissions permissions
) {}

public class DashboardExample {
    static User loadUser() {
        return new User("Lan");
    }

    static List<Order> loadOrders() {
        return List.of(new Order("O-100"), new Order("O-101"));
    }

    static Permissions loadPermissions() {
        return new Permissions(true);
    }

    static Dashboard loadDashboard() throws Exception {
        try (var scope = StructuredTaskScope.open(
                Joiner.<Object>awaitAllSuccessfulOrThrow())) {

            Subtask<User> userTask = scope.fork(DashboardExample::loadUser);
            Subtask<List<Order>> ordersTask =
                    scope.fork(DashboardExample::loadOrders);
            Subtask<Permissions> permissionsTask =
                    scope.fork(DashboardExample::loadPermissions);

            // join trả null nếu tất cả thành công.
            scope.join();

            return new Dashboard(
                    userTask.get(),
                    ordersTask.get(),
                    permissionsTask.get()
            );
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(loadDashboard());
    }
}
~~~

Kiểu phần tử của scope được đặt là `Object` để chấp nhận các tác vụ con có kiểu kết quả khác nhau. Các handle vẫn giữ kiểu cụ thể của từng tác vụ, nên `get()` trả về đúng kiểu mà không cần ép kiểu.

### 5.2. Không gọi Subtask.get() trước khi join

`Subtask.get()` chỉ được gọi sau khi thread sở hữu đã join và tác vụ con đã ở trạng thái `SUCCESS`. Nếu gọi trước khi join hoặc tác vụ chưa thành công, API ném `IllegalStateException`.

Trình tự đúng:

1. Fork các tác vụ.
2. Gọi `scope.join()`.
3. Nếu join thành công, gọi `get()` trên các handle đã hoàn tất thành công.
4. Xây dựng kết quả nghiệp vụ.

Nếu một tác vụ thất bại, Joiner hủy scope và `join()` ném exception. Không chạy tiếp đoạn đọc kết quả như thể mọi tác vụ đã thành công.

## 6. Thu thập trạng thái và dừng theo điều kiện: allUntil()

### 6.1. allUntil khác hai Joiner phổ biến

`Joiner.allUntil(predicate)` cung cấp chính sách linh hoạt hơn. Predicate được gọi khi một tác vụ con hoàn tất, với trạng thái `SUCCESS` hoặc `FAILED`.

- Nếu predicate trả về `true`, scope bị hủy.
- Nếu predicate luôn trả về `false`, scope tiếp tục cho tới khi tất cả tác vụ hoàn tất.
- `join()` trả về danh sách các handle `Subtask` theo thứ tự fork.
- Danh sách có thể chứa trạng thái `SUCCESS`, `FAILED` hoặc `UNAVAILABLE`.

`UNAVAILABLE` có nghĩa là kết quả chưa thể lấy được, ví dụ tác vụ bị hủy trước khi hoàn tất hoặc hoàn tất sau khi scope đã bị hủy.

### 6.2. Ví dụ: dừng khi có hai kết quả thành công

~~~java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;
import java.util.concurrent.StructuredTaskScope.Subtask;
import java.util.concurrent.atomic.AtomicInteger;

public class AllUntilExample {
    static String search(String engine, long delayMillis)
            throws InterruptedException {
        Thread.sleep(delayMillis);
        return "result-from-" + engine;
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger successfulCount = new AtomicInteger();

        try (var scope = StructuredTaskScope.open(
                Joiner.<String>allUntil(subtask ->
                        subtask.state() == Subtask.State.SUCCESS
                                && successfulCount.incrementAndGet() >= 2))) {

            scope.fork(() -> search("engine-a", 300));
            scope.fork(() -> search("engine-b", 100));
            scope.fork(() -> search("engine-c", 200));
            scope.fork(() -> search("engine-d", 500));

            List<Subtask<String>> subtasks = scope.join();

            for (Subtask<String> subtask : subtasks) {
                System.out.print(subtask.state() + " -> ");

                if (subtask.state() == Subtask.State.SUCCESS) {
                    System.out.println(subtask.get());
                } else if (subtask.state() == Subtask.State.FAILED) {
                    System.out.println(subtask.exception());
                } else {
                    System.out.println("Không có kết quả");
                }
            }
        }
    }
}
~~~

Khi có hai tác vụ thành công, predicate trả về `true` và scope bị hủy. Những tác vụ còn lại có thể ở trạng thái `UNAVAILABLE` nếu chưa hoàn tất trước khi việc hủy có hiệu lực.

Predicate có thể được gọi đồng thời từ nhiều thread. Ví dụ dùng `AtomicInteger` để đếm số thành công, tránh dùng biến đếm thông thường không đồng bộ.

### 6.3. Thu thập tất cả kết quả mà không hủy sớm

Trong JDK 27, `Joiner.awaitAll()` không còn là API. Nếu cần đợi mọi tác vụ hoàn tất và lấy trạng thái cả thành công lẫn thất bại, có thể dùng `allUntil` với predicate luôn trả về `false`:

~~~java
try (var scope = StructuredTaskScope.open(
        Joiner.<String>allUntil(subtask -> false))) {

    scope.fork(() -> search("A", 100));
    scope.fork(() -> search("B", 200));
    scope.fork(() -> search("C", 300));

    List<Subtask<String>> subtasks = scope.join();

    for (Subtask<String> subtask : subtasks) {
        switch (subtask.state()) {
            case SUCCESS -> System.out.println(subtask.get());
            case FAILED -> System.out.println(subtask.exception());
            case UNAVAILABLE -> System.out.println("Chưa có kết quả");
        }
    }
}
~~~

Không có điều kiện nào hủy scope sớm, nên nếu không đặt timeout thì Joiner chờ các tác vụ hoàn tất. Nếu có timeout, các tác vụ chưa hoàn tất có thể ở trạng thái `UNAVAILABLE`; Joiner trả danh sách thay vì ném lỗi chỉ vì timeout.

## 7. Xử lý lỗi và tùy biến exception trong JDK 27

### 7.1. join() ném ExecutionException

Với các Joiner tiêu chuẩn trong JDK 27:

- `allSuccessfulOrThrow()` ném `ExecutionException` nếu có tác vụ thất bại.
- `anySuccessfulOrThrow()` ném `ExecutionException` nếu tất cả tác vụ thất bại.
- `awaitAllSuccessfulOrThrow()` ném `ExecutionException` nếu có tác vụ thất bại.

Exception gốc được đặt trong `getCause()`. Có thể phân loại nguyên nhân:

~~~java
try (var scope = StructuredTaskScope.open(
        Joiner.<String>allSuccessfulOrThrow())) {

    scope.fork(() -> loadCatalog());
    scope.fork(() -> loadPricing());

    List<String> results = scope.join();

} catch (java.util.concurrent.ExecutionException e) {
    Throwable cause = e.getCause();

    if (cause instanceof java.io.IOException ioException) {
        System.err.println("Lỗi I/O: " + ioException.getMessage());
    } else {
        throw e;
    }
}
~~~

`join()` còn có thể ném `InterruptedException` nếu thread sở hữu bị interrupt trong lúc chờ. Đây là một tín hiệu hủy riêng, không nên gộp với lỗi nghiệp vụ từ tác vụ con.

### 7.2. Dùng exception supplying function

JDK 27 cung cấp overload nhận `Function<Throwable, R_X>` để chọn kiểu exception mà `join()` sẽ ném khi chính sách thất bại.

Ví dụ dùng `CompletionException` khi không có replica nào thành công:

~~~java
import java.util.concurrent.CompletionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class CustomFailureExample {
    static String query(String replica) {
        throw new IllegalStateException("Replica unavailable: " + replica);
    }

    public static void main(String[] args) throws InterruptedException {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String, CompletionException>anySuccessfulOrThrow(
                        CompletionException::new))) {

            scope.fork(() -> query("A"));
            scope.fork(() -> query("B"));

            String result = scope.join();
            System.out.println(result);

        } catch (CompletionException e) {
            System.err.println("Không có replica thành công: "
                    + e.getCause());
        }
    }
}
~~~

Function nhận exception gốc và phải trả về exception mới với exception gốc làm cause. Nếu function trả về `null`, `join()` ném `NullPointerException`.

Các overload tương tự có cho:

- `allSuccessfulOrThrow(Function)`
- `anySuccessfulOrThrow(Function)`
- `awaitAllSuccessfulOrThrow(Function)`

Dùng overload này để chuyển lỗi sang kiểu exception phù hợp với API của ứng dụng. Không đặt logic nghiệp vụ phức tạp vào function chuyển exception.

## 8. Timeout và cấu hình scope

JDK 27 cho phép cấu hình timeout, tên scope và ThreadFactory qua `Configuration`.

Ví dụ giới hạn thời gian chờ lấy dữ liệu từ các replica:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class TimeoutExample {
    public static void main(String[] args) throws InterruptedException {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String>allSuccessfulOrThrow(),
                config -> config
                        .withName("replica-lookup")
                        .withTimeout(Duration.ofSeconds(2)))) {

            scope.fork(() -> fetch("A"));
            scope.fork(() -> fetch("B"));

            List<String> results = scope.join();
            System.out.println(results);

        } catch (ExecutionException e) {
            if (e.getCause()
                    instanceof StructuredTaskScope.CancelledByTimeoutException) {
                System.err.println("Hết thời gian chờ các replica");
            } else {
                throw e;
            }
        }
    }

    static String fetch(String replica) throws InterruptedException {
        Thread.sleep(5_000);
        return replica;
    }
}
~~~

Timeout bắt đầu từ lúc mở scope. Khi timeout hết hạn trước hoặc trong lúc `join()` chờ, scope bị hủy và các tác vụ chưa hoàn tất nhận interrupt. Với các Joiner tiêu chuẩn không thể tạo kết quả khi timeout, `join()` ném `ExecutionException` với `CancelledByTimeoutException` làm cause.

JDK 27 cũng có overload `StructuredTaskScope.open(configOperator)` để dùng chính sách mặc định (đợi tất cả thành công hoặc thất bại ngay khi có một lỗi) mà không phải truyền Joiner:

~~~java
try (var scope = StructuredTaskScope.open(
        config -> config.withTimeout(Duration.ofSeconds(2)))) {

    scope.fork(() -> fetch("A"));
    scope.fork(() -> fetch("B"));

    scope.join();
}
~~~

Overload này được thêm trong JDK 27. Khi cần chính sách khác, tiếp tục truyền Joiner tường minh.

## 9. Vòng đời, hủy tác vụ và an toàn thread

Joiner quyết định thời điểm scope bị hủy, nhưng việc hủy không đồng nghĩa thread dừng tức thì. Scope gửi interrupt tới các tác vụ chưa hoàn tất. Mã tác vụ cần phản hồi interruption để kết thúc sớm.

Ví dụ xử lý interrupt đúng cách:

~~~java
static String fetchRemote() throws InterruptedException {
    while (true) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Request cancelled");
        }

        // Thực hiện một bước công việc có giới hạn.
        return callRemoteService();
    }
}
~~~

Một tác vụ chặn trong API không hỗ trợ interrupt hoặc bỏ qua tín hiệu interrupt có thể làm `close()` chờ rất lâu. `try-with-resources` bảo đảm scope được đóng, và `close()` đợi tất cả thread con kết thúc trước khi luồng điều khiển ra khỏi khối.

Các quy tắc cần nhớ:

- Chỉ thread mở scope mới được gọi `fork()`, `join()` và `close()`.
- Không gọi `fork()` sau khi đã `join()`.
- Gọi `join()` để lấy kết quả hoặc exception trước khi đóng scope sau khi đã fork.
- Mỗi Joiner chỉ nên được tạo và dùng cho một scope; không chia sẻ cùng một Joiner mutable giữa nhiều scope.
- `onComplete()` của Joiner có thể được gọi đồng thời bởi nhiều thread. Joiner tự cài đặt phải thread-safe.
- Predicate của `allUntil` cũng phải thread-safe.
- Không dùng kết quả của `Subtask.get()` hoặc `Subtask.exception()` trước khi scope owner đã join, trừ khi đang ở trong callback `onComplete` theo hợp đồng API.

## 10. Joiner tùy chỉnh và yêu cầu thread-safe

Các Joiner dựng sẵn đáp ứng phần lớn trường hợp phổ biến. Nếu cần chính sách riêng, có thể triển khai `StructuredTaskScope.Joiner` với các điểm mở rộng:

| Phương thức | Vai trò |
|---|---|
| `onFork(Subtask)` | Nhận thông báo khi một tác vụ con được fork |
| `onComplete(Subtask)` | Nhận thông báo khi tác vụ hoàn tất thành công hoặc thất bại |
| `result()` | Tạo kết quả hoặc ném exception cho `join()` |
| `timeout()` | Tạo kết quả hoặc ném exception khi scope hết timeout |

`onComplete()` có thể được gọi đồng thời từ nhiều thread và có thể chạy đồng thời với các phương thức khác của Joiner được gọi từ thread sở hữu. Vì vậy, trạng thái dùng chung trong Joiner cần dùng cấu trúc thread-safe như `ConcurrentLinkedQueue`, `ConcurrentHashMap`, `AtomicInteger` hoặc đồng bộ hóa phù hợp.

Một Joiner tùy chỉnh chỉ nên xử lý chính sách điều phối, thu thập kết quả và điều kiện hủy. Hãy để logic nghiệp vụ xử lý kết quả ở đoạn code sau `join()` để dễ kiểm thử và dễ đọc.

Không chia sẻ cùng một instance Joiner giữa nhiều scope. Mỗi scope cần một instance mới, với trạng thái riêng của chính sách.

## 11. Khác biệt cần biết khi chuyển JDK 26 lên JDK 27

JDK 27 (JEP 533, preview lần thứ bảy) tiếp tục thay đổi API Structured Concurrency sau JDK 26 (JEP 525, preview lần thứ sáu).

| Nội dung | JDK 26 Preview 6 | JDK 27 Preview 7 |
|---|---|---|
| Kiểu `StructuredTaskScope` | `StructuredTaskScope<T, R>` | `StructuredTaskScope<T, R, R_X extends Throwable>` |
| Kiểu `Joiner` | `Joiner<T, R>` | `Joiner<T, R, R_X extends Throwable>` |
| Exception từ chính sách thất bại tiêu chuẩn | `StructuredTaskScope.FailedException` | `ExecutionException` |
| Kiểu exception của `join()` | Chưa được biểu diễn thành type parameter riêng | Được biểu diễn bởi `R_X` |
| Joiner chọn kết quả thành công | `anySuccessfulOrThrow()` | `anySuccessfulOrThrow()` |
| Kết quả `allSuccessfulOrThrow()` | `List<T>` | `List<T>` |
| Chờ tất cả không ném lỗi tác vụ | Có `awaitAll()` | Đã loại bỏ `awaitAll()` |
| Timeout callback của Joiner | `onTimeout()` | `timeout()` |
| Chuyển đổi exception | Chưa có các overload supplying function như JDK 27 | Có overload `Function<Throwable, R_X>` |
| Mở scope với cấu hình mặc định tùy chỉnh | Truyền Joiner và config operator | Có thêm `open(configOperator)` |

Một số mã cũ có thể không biên dịch khi đổi JDK:

- Không còn dùng `StructuredTaskScope.FailedException` để bắt lỗi trong JDK 27; dùng `ExecutionException` hoặc kiểu exception tùy chỉnh của Joiner.
- Không dùng tên `anySuccessfulResultOrThrow()` từ các bản thử nghiệm sớm; tên hiện hành là `anySuccessfulOrThrow()`.
- Không dùng `awaitAll()` trong JDK 27. Nếu cần thu thập trạng thái của tất cả tác vụ, xem `allUntil(subtask -> false)`.
- Nếu tự triển khai Joiner, cập nhật type parameter thứ ba và đổi callback timeout từ `onTimeout()` sang `timeout()`.
- Kiểm tra các catch clause vì `ExecutionException` là checked exception.

Đừng sao chép code từ một vòng preview cũ mà không đối chiếu tài liệu JDK mục tiêu. Preview có thể thay đổi chữ ký, kiểu exception và chính sách kết quả giữa các feature release.

## 12. Biên dịch và chạy

Structured Concurrency là preview API trong JDK 26 và JDK 27. Cần bật preview khi biên dịch và khi chạy, đồng thời dùng cùng feature release.

JDK 27:

~~~bash
javac --release 27 --enable-preview -d out AllResultsExample.java
java --enable-preview -cp out AllResultsExample
~~~

JDK 26:

~~~bash
javac --release 26 --enable-preview -d out AllResultsExample.java
java --enable-preview -cp out AllResultsExample
~~~

Không cần thêm module incubator. Nếu IDE hoặc CI báo lỗi về `StructuredTaskScope`, `Joiner` hoặc `ExecutionException`, xác nhận compiler, runtime, `--release` và cờ preview đang cùng phiên bản.

## 13. Hướng dẫn chọn chính sách trong ứng dụng

| Tình huống | Lựa chọn |
|---|---|
| Cần tất cả kết quả mới xây dựng được response | `allSuccessfulOrThrow()` |
| Có nhiều nguồn tương đương, chỉ cần một nguồn thành công | `anySuccessfulOrThrow()` |
| Tác vụ con có kiểu kết quả khác nhau | `awaitAllSuccessfulOrThrow()` và giữ các `Subtask` |
| Muốn dừng sau một điều kiện dựa trên trạng thái hoàn tất | `allUntil(predicate)` |
| Cần thu thập cả kết quả thành công và lỗi của mọi tác vụ | `allUntil(subtask -> false)` rồi phân loại trạng thái |
| Cần ánh xạ lỗi tác vụ sang exception nghiệp vụ của ứng dụng | Overload nhận exception supplying function |
| Cần giới hạn thời gian của toàn nhóm tác vụ | `open(joiner, config -> config.withTimeout(...))` |

Đừng dùng `anySuccessfulOrThrow()` nếu yêu cầu nghiệp vụ cần mọi kết quả. Đừng dùng `allSuccessfulOrThrow()` nếu chỉ một nguồn thành công là đủ và việc chờ các nguồn còn lại làm tăng latency. Chính sách Joiner nên phản ánh chính xác điều kiện hoàn thành của tác vụ cha.

## 14. Kết luận

`Joiner` là nơi định nghĩa chính sách tổng hợp và hủy các tác vụ con trong Structured Concurrency:

- `allSuccessfulOrThrow()` trả danh sách kết quả khi mọi tác vụ thành công.
- `anySuccessfulOrThrow()` trả kết quả thành công đầu tiên và hủy các tác vụ còn lại.
- `awaitAllSuccessfulOrThrow()` chờ tất cả thành công, phù hợp khi cần đọc kết quả qua nhiều handle có kiểu khác nhau.
- `allUntil(predicate)` cho phép dừng theo điều kiện tùy chỉnh và trả về trạng thái các tác vụ.

Trong JDK 27, Joiner vẫn là preview API. Cần bật preview và chú ý các thay đổi từ JDK 26: `ExecutionException`, type parameter thứ ba cho kiểu exception, callback `timeout()`, các overload ánh xạ exception và việc loại bỏ `awaitAll()`. Khi thiết kế, hãy chọn chính sách đúng với yêu cầu kết quả, bảo đảm tác vụ phản hồi interrupt và giữ Joiner tùy chỉnh thread-safe.

## Tài liệu tham khảo chính thức

- [JEP 525 — Structured Concurrency (Sixth Preview, JDK 26)](https://openjdk.org/jeps/525)
- [JEP 533 — Structured Concurrency (Seventh Preview, JDK 27)](https://openjdk.org/jeps/533)
- [StructuredTaskScope — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [StructuredTaskScope.Joiner — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html)
- [Structured Concurrency — Java SE 26 Guide](https://docs.oracle.com/en/java/javase/26/core/structured-concurrency.html)
- [StructuredTaskScope — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [StructuredTaskScope.Joiner — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html)
- [StructuredTaskScope.Subtask — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html)
- [Structured Concurrency — Java SE 27 Guide](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html)
- [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

