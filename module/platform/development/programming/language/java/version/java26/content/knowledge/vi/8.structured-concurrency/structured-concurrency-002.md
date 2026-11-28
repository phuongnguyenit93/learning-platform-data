# Phần thực hành dùng hợp đồng `StructuredTaskScope` preview Java 27

Java 27 cung cấp `StructuredTaskScope` trong module `java.base`, package `java.util.concurrent`, dưới dạng **Structured Concurrency (Seventh Preview)** của JEP 533. API cho phép một tác vụ cha tạo các tác vụ con chạy đồng thời, chờ chúng như một đơn vị công việc, áp dụng chính sách kết hợp kết quả và hủy các tác vụ còn chạy khi không cần kết quả của chúng nữa. Mặc định, mỗi subtask chạy trên một virtual thread.

Trong bài thực hành này, ta xây dựng một màn hình tổng hợp hồ sơ khách hàng và đơn hàng. Hai lời gọi độc lập chạy đồng thời; màn hình chỉ trả kết quả khi cả hai thành công. Nếu một lời gọi lỗi hoặc hết thời gian, scope hủy tác vụ còn lại và chờ các thread kết thúc trước khi rời khỏi khối `try`.

**Trạng thái phiên bản tại ngày 27-11-2026:** Java 27 đã phát hành và `StructuredTaskScope` vẫn là preview, do đó cần bật preview khi biên dịch và chạy trên JDK 27. JEP 543 đã được tích hợp vào nhánh phát triển JDK 28 để đưa API thành chính thức mà không đổi API so với preview thứ bảy; JDK 28 vẫn đang trong giai đoạn phát triển, với mốc GA dự kiến tháng 3-2027. Khi triển khai trên JDK 27 đã phát hành, hãy tuân thủ hợp đồng preview Java 27 trong bài này. [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) · [JDK Releases and Support Timeline](https://ops.java/releases/?lang=en) · [OpenJDK: tích hợp JEP 543 vào JDK 28](https://mail.openjdk.org/pipermail/core-libs-dev/2026-September/153000.html).

## 1. Mô hình hoạt động

Structured concurrency coi một nhóm tác vụ con có liên quan là một đơn vị công việc. Thay vì tạo thread ở nhiều nơi rồi tự quản lý các `Future`, tác vụ cha mở một scope, fork các subtask, join để lấy kết quả, rồi đóng scope. Vòng đời các thread con được giới hạn bởi scope cha.

```text
Tác vụ cha
   |
   | StructuredTaskScope.open(...)
   v
  Scope
   |
   +---- fork(fetchProfile) ----> Subtask A / virtual thread
   |
   +---- fork(fetchOrders) -----> Subtask B / virtual thread
   |
   +---- join() ----------------> đợi chính sách kết thúc
   |                                |
   |                         +------+------+
   |                         |             |
   |                      thành công     lỗi / timeout
   |                         |             |
   |                    đọc kết quả     hủy subtask còn chạy
   |                         |             |
   +-------------------------+-------------+
   |
   +---- close() ------------> chờ mọi thread con kết thúc
   |
   v
Tiếp tục sau scope
```

Các bước chuẩn:

1. Mở scope bằng một trong các phương thức `StructuredTaskScope.open(...)`, thường trong `try-with-resources`.
2. Thread mở scope là **scope owner**. Chỉ owner được gọi `fork`, `join` và `close`.
3. Gọi `fork(Callable)` cho tác vụ trả kết quả hoặc `fork(Runnable)` cho tác vụ chỉ tạo side effect.
4. Sau khi fork xong, owner gọi `join()` để đợi chính sách của scope tạo ra kết quả hoặc exception.
5. Sau khi join thành công, owner đọc kết quả qua `Subtask.get()` hoặc dùng kết quả do `Joiner` trả trực tiếp.
6. Đóng scope. `try-with-resources` gọi `close()` tự động; scope hủy tác vụ chưa hoàn tất và đợi mọi thread con kết thúc.

Không gọi `fork()` sau `join()`. Nếu đã fork subtask, phải gọi `join()` trước khi scope đóng. `close()` vẫn dọn dẹp thread con nếu luồng điều khiển rời khỏi khối sớm, nhưng sẽ ném `IllegalStateException` sau khi đóng nếu owner chưa từng gọi `join()`.

## 2. Hợp đồng API Java 27 cần nhớ

Trong Java 27, `StructuredTaskScope` là **interface sealed** với ba tham số kiểu:

```java
public sealed interface StructuredTaskScope<T, R, R_X extends Throwable>
        extends AutoCloseable
```

| Tham số | Ý nghĩa |
|---|---|
| `T` | Kiểu kết quả của các subtask được fork trong scope. |
| `R` | Kiểu kết quả mà `join()` trả về. |
| `R_X` | Kiểu exception mà `join()` có thể ném theo chính sách `Joiner`. |

`StructuredTaskScope.Joiner<T, R, R_X>` cũng có ba tham số kiểu tương ứng. Đây là thay đổi đáng chú ý so với API Java 26, nơi `StructuredTaskScope<T, R>` và `Joiner<T, R>` chỉ có hai tham số kiểu. Java 27 đưa kiểu exception vào chữ ký API, vì vậy compiler có thể kiểm tra exception mà chính sách joiner ném ra.

Các điểm khác biệt quan trọng giữa preview Java 26 và preview Java 27:

| Nội dung | Java 26 — Sixth Preview | Java 27 — Seventh Preview |
|---|---|---|
| Tham số kiểu | `StructuredTaskScope<T, R>` và `Joiner<T, R>`. | Thêm `R_X extends Throwable`: `StructuredTaskScope<T, R, R_X>` và `Joiner<T, R, R_X>`. |
| Lỗi từ chính sách join | `join()` bọc lỗi do `Joiner.result()` ném trong `StructuredTaskScope.FailedException`. | `join()` ném trực tiếp kiểu `R_X` đã khai báo bởi `Joiner`; các joiner dựng sẵn thường dùng `ExecutionException`. |
| Chính sách mặc định | `open()` trả `null` khi thành công, ném `FailedException` khi subtask lỗi. | `open()` trả `null` khi thành công, ném `ExecutionException` khi subtask lỗi. |
| Timeout của Joiner | Callback `onTimeout()`; mặc định ném `StructuredTaskScope.TimeoutException`. | Callback `timeout()` trả kết quả hoặc ném kiểu `R_X`; lỗi timeout thường có `CancelledByTimeoutException` làm cause. |
| Mở scope chỉ với cấu hình | Cần overload nhận cả `Joiner` và toán tử cấu hình. | Có thêm `open(UnaryOperator<Configuration>)`, dùng chính sách mặc định fail-fast. |
| Joiner `awaitAll()` | Có sẵn. | Đã bỏ; dùng `allUntil(_ -> false)` nếu cần đợi mọi subtask và nhận danh sách handle. |

Vì vậy, không sao chép ví dụ Java 26 dùng `FailedException`, `onTimeout()` hoặc `Joiner.awaitAll()` vào dự án Java 27. Các tên và hợp đồng này không còn khớp với API Java 27. [Java 26 `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) · [Java 27 `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) · [Java 27 `Joiner`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html).

## 3. Bài thực hành: tải hồ sơ và đơn hàng song song

Giả sử trang tổng quan cần hai nguồn dữ liệu độc lập:

- `ProfileService` tải hồ sơ khách hàng.
- `OrderService` tải danh sách đơn hàng gần đây.

Nếu gọi tuần tự, thời gian chờ gần bằng tổng thời gian hai lời gọi. Với structured concurrency, hai subtask chạy đồng thời; thời gian hoàn thành thường gần bằng lời gọi chậm hơn, cộng chi phí điều phối.

### Mã nguồn

Ví dụ sau dùng API Java 27: `open(UnaryOperator<Configuration>)`, `withName`, `withTimeout`, `fork`, `join` và `Subtask.get()`.

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

record UserProfile(String displayName) {}
record Order(String id, long total) {}
record Dashboard(UserProfile profile, List<Order> orders) {}

interface ProfileService {
    UserProfile fetch(String userId) throws Exception;
}

interface OrderService {
    List<Order> fetchRecent(String userId) throws Exception;
}

final class DashboardService {
    private final ProfileService profiles;
    private final OrderService orders;

    DashboardService(ProfileService profiles, OrderService orders) {
        this.profiles = profiles;
        this.orders = orders;
    }

    Dashboard load(String userId)
            throws InterruptedException, ExecutionException {

        try (var scope = StructuredTaskScope.open(config ->
                config.withName("dashboard-" + userId)
                      .withTimeout(Duration.ofSeconds(3)))) {

            Subtask<UserProfile> profileTask =
                    scope.fork(() -> profiles.fetch(userId));

            Subtask<List<Order>> orderTask =
                    scope.fork(() -> orders.fetchRecent(userId));

            // Chính sách mặc định: chờ tất cả thành công hoặc hủy khi có lỗi.
            scope.join();

            // Chỉ đọc kết quả sau khi join đã hoàn tất thành công.
            return new Dashboard(profileTask.get(), orderTask.get());
        }
    }
}
```

Trong ví dụ này, scope có chính sách mặc định `awaitAllSuccessfulOrThrow()`:

- Nếu cả hai subtask thành công, `join()` trả `null`; owner lấy từng kết quả bằng `get()` và ghép thành `Dashboard`.
- Nếu một subtask thất bại, scope bị hủy và subtask còn lại bị interrupt. `join()` ném `ExecutionException` với exception từ subtask thất bại làm cause.
- Nếu timeout ba giây hết hạn trước hoặc trong lúc `join()` chờ, scope bị hủy và `join()` ném `ExecutionException` có cause là `StructuredTaskScope.CancelledByTimeoutException`.
- Nếu thread owner bị interrupt trong lúc `join()`, `join()` ném `InterruptedException`. `try-with-resources` vẫn đóng scope và đợi các subtask kết thúc.

### Xử lý lỗi ở nơi gọi

`ExecutionException` là checked exception. Hãy kiểm tra `getCause()` để phân biệt lỗi nghiệp vụ, lỗi I/O và timeout:

```java
try {
    Dashboard dashboard = dashboardService.load(userId);
    render(dashboard);
} catch (ExecutionException failure) {
    Throwable cause = failure.getCause();

    if (cause instanceof StructuredTaskScope.CancelledByTimeoutException) {
        showTemporaryMessage("Tải dữ liệu quá thời gian cho phép");
    } else if (cause instanceof java.io.IOException ioFailure) {
        log.warn("Không tải được dữ liệu từ dịch vụ", ioFailure);
        showTemporaryMessage("Dịch vụ dữ liệu đang tạm thời không khả dụng");
    } else {
        throw new IllegalStateException("Không thể tạo dashboard", cause);
    }
} catch (InterruptedException interrupted) {
    // Chuyển quyền xử lý interruption lên tầng gọi cao hơn.
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Tác vụ tải dashboard bị interrupt", interrupted);
}
```

Trong một ứng dụng thực tế, có thể để phương thức tầng service khai báo `InterruptedException` và để tầng gọi quyết định cách kết thúc request. Nếu bắt rồi không ném tiếp, hãy khôi phục interrupt status bằng `Thread.currentThread().interrupt()` để tầng trên vẫn nhận biết tín hiệu hủy.

## 4. Chọn `Joiner` theo kết quả mong muốn

`Joiner` quyết định khi nào scope hoàn tất, khi nào hủy các subtask còn chạy và `join()` trả kết quả hoặc ném exception nào. Java 27 cung cấp các factory method cho những chính sách phổ biến.

| Joiner | Kết quả của `join()` | Khi dùng |
|---|---|---|
| `Joiner.allSuccessfulOrThrow()` | `List<T>` gồm kết quả của mọi subtask theo thứ tự fork; ném `ExecutionException` nếu có subtask lỗi. | Nhiều subtask cùng kiểu kết quả và cần tất cả thành công. |
| `Joiner.anySuccessfulOrThrow()` | Kết quả của một subtask thành công; khi có kết quả đầu tiên, scope hủy các subtask còn chạy. Nếu tất cả thất bại, ném `ExecutionException`. | Gọi nhiều replica hoặc endpoint thay thế, chỉ cần một kết quả thành công. |
| `Joiner.awaitAllSuccessfulOrThrow()` | Trả `null` nếu tất cả thành công; ném `ExecutionException` nếu có lỗi. | Subtask có kiểu kết quả khác nhau và owner cần giữ từng `Subtask` để lấy kết quả. Đây cũng là chính sách mặc định của `open()`. |
| `Joiner.allUntil(predicate)` | Trả `List<Subtask<T>>` theo thứ tự fork khi mọi subtask hoàn tất hoặc predicate yêu cầu hủy scope. | Muốn quan sát kết quả một phần, trạng thái lỗi hoặc các subtask chưa kịp hoàn tất. |

### Ví dụ A: lấy tất cả kết quả cùng kiểu

Khi gọi nhiều nguồn tìm kiếm và tất cả đều phải thành công, `allSuccessfulOrThrow()` trả thẳng danh sách kết quả; không cần giữ từng `Subtask`:

```java
import java.util.List;
import java.util.concurrent.StructuredTaskScope.Joiner;

static List<String> searchEveryIndex(String keyword)
        throws InterruptedException, ExecutionException {

    try (var scope = StructuredTaskScope.open(
            Joiner.<String>allSuccessfulOrThrow())) {

        scope.fork(() -> searchIndexA(keyword));
        scope.fork(() -> searchIndexB(keyword));
        scope.fork(() -> searchIndexC(keyword));

        return scope.join();
    }
}
```

Danh sách trả về theo đúng thứ tự gọi `fork`, không phải thứ tự subtask hoàn tất. Nếu một subtask lỗi, Joiner hủy scope và không trả danh sách kết quả chưa đầy đủ.

### Ví dụ B: lấy kết quả thành công đầu tiên

Khi có nhiều replica cung cấp cùng một dữ liệu, có thể dùng `anySuccessfulOrThrow()`:

```java
import java.util.concurrent.StructuredTaskScope.Joiner;

static String readFromAnyReplica(String key)
        throws InterruptedException, ExecutionException {

    try (var scope = StructuredTaskScope.open(
            Joiner.<String>anySuccessfulOrThrow())) {

        scope.fork(() -> replicaA.read(key));
        scope.fork(() -> replicaB.read(key));
        scope.fork(() -> replicaC.read(key));

        return scope.join();
    }
}
```

Khi một replica trả kết quả thành công, scope hủy các replica còn đang chạy. Nếu tất cả đều lỗi, `join()` ném `ExecutionException`; cause là lỗi từ một subtask thất bại. Chính sách này phù hợp khi kết quả từ bất kỳ replica nào đều tương đương về mặt nghiệp vụ.

### Ví dụ C: nhận kết quả từng phần

Java 27 không còn `Joiner.awaitAll()`. Nếu cần đợi tất cả subtask dù có lỗi và sau đó kiểm tra từng trạng thái, dùng `allUntil(_ -> false)`:

```java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;
import java.util.concurrent.StructuredTaskScope.Subtask;

static List<String> collectSuccessfulResults()
        throws InterruptedException {

    try (var scope = StructuredTaskScope.open(
            Joiner.<String>allUntil(subtask -> false))) {

        scope.fork(() -> fetchSourceA());
        scope.fork(() -> fetchSourceB());
        scope.fork(() -> fetchSourceC());

        List<Subtask<String>> subtasks = scope.join();

        return subtasks.stream()
                .filter(subtask -> subtask.state() == Subtask.State.SUCCESS)
                .map(Subtask::get)
                .toList();
    }
}
```

Predicate luôn trả `false`, do đó Joiner không hủy scope vì kết quả của một subtask. Danh sách chứa các handle theo thứ tự fork; sau khi `join()` trả về, owner có thể kiểm tra `state()` và chỉ gọi `get()` với subtask ở trạng thái `SUCCESS`. Nếu scope bị hủy bởi timeout hoặc chính sách khác, một số handle có thể ở trạng thái `UNAVAILABLE`.

## 5. Timeout và hợp đồng `Joiner.timeout()`

Timeout được đặt qua `StructuredTaskScope.Configuration.withTimeout(Duration)`. Bộ đếm thời gian bắt đầu khi scope được mở, vì vậy thời gian dành cho giai đoạn fork cũng nằm trong giới hạn. Khi hết thời gian, scope bị hủy và thread thực thi các subtask chưa hoàn tất nhận interrupt.

Với các Joiner dựng sẵn như `allSuccessfulOrThrow()`, `anySuccessfulOrThrow()` và `awaitAllSuccessfulOrThrow()`, timeout khiến `join()` ném `ExecutionException` với cause là `CancelledByTimeoutException`. Không bắt `TimeoutException` như hợp đồng Java 26.

Nếu tự triển khai `Joiner`, Java 27 yêu cầu định nghĩa `timeout()` để tạo kết quả hoặc exception cho trường hợp timeout. Phương thức này thay cho `onTimeout()` của Java 26. Nếu `timeout()` ném exception, exception được ném theo kiểu `R_X` và có `CancelledByTimeoutException` làm cause. Một Joiner đặc biệt có thể trả kết quả từng phần thay vì ném lỗi timeout.

Ví dụ cấu hình scope có tên và thời hạn:

```java
try (var scope = StructuredTaskScope.open(config ->
        config.withName("catalog-search")
              .withTimeout(Duration.ofSeconds(2)))) {

    scope.fork(() -> searchCatalogA());
    scope.fork(() -> searchCatalogB());

    scope.join();
}
```

`open(UnaryOperator<Configuration>)` là overload được thêm trong Java 27. Nó dùng chính sách mặc định `awaitAllSuccessfulOrThrow()`, nên khi một subtask lỗi hoặc timeout, `join()` ném `ExecutionException`. Với Java 26, muốn cấu hình timeout phải truyền cả Joiner và toán tử cấu hình vào overload hai tham số.

## 6. Kiểu exception của `join()` và Joiner tùy chỉnh

Java 27 đưa kiểu exception vào generic parameter thứ ba `R_X`. `join()` khai báo `throws R_X, InterruptedException`. Các Joiner dựng sẵn thường chọn `ExecutionException`; các overload nhận `Function<Throwable, R_X>` cho phép ứng dụng chọn kiểu exception phù hợp.

Ví dụ, chuyển lỗi của một trong các subtask thành `IOException`:

```java
import java.io.IOException;
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

static List<String> loadAll()
        throws InterruptedException, IOException {

    try (var scope = StructuredTaskScope.open(
            Joiner.<String, IOException>allSuccessfulOrThrow(
                    cause -> new IOException("Không tải được đầy đủ dữ liệu", cause)))) {

        scope.fork(() -> loadFromA());
        scope.fork(() -> loadFromB());

        // join() có thể ném IOException do Joiner khai báo.
        return scope.join();
    }
}
```

`Function` nhận nguyên nhân lỗi của subtask đầu tiên thất bại và phải trả về exception khác `null`. Exception do function tạo ra được ném trực tiếp bởi `join()` theo kiểu `R_X`. Với timeout, function cũng có thể nhận `CancelledByTimeoutException` nếu scope được cấu hình thời hạn. Hãy để cause gốc được giữ lại khi tạo exception mới để việc chẩn đoán không mất thông tin.

Nếu tự triển khai `Joiner`, cần tuân thủ các quy tắc:

- Tạo một Joiner mới cho mỗi scope; không dùng chung một instance cho nhiều scope.
- Cài đặt `onFork(Subtask)` và `onComplete(Subtask)` khi cần theo dõi subtask hoặc quyết định hủy scope.
- `onComplete` có thể được gọi đồng thời bởi nhiều thread; mọi trạng thái chia sẻ trong Joiner phải thread-safe.
- `result()` tạo kết quả cho trường hợp bình thường; `timeout()` tạo kết quả cho trường hợp timeout.
- Giữ Joiner tổng quát, tập trung vào chính sách kết thúc và tổng hợp kết quả; xử lý nghiệp vụ ở code gọi `join()`.

## 7. Hủy tác vụ và xử lý interrupt đúng cách

Structured concurrency chỉ giữ được lợi ích về vòng đời khi subtask phản hồi với interrupt. Khi scope bị hủy, các thread chưa hoàn tất được interrupt, nhưng không bị buộc dừng ngay lập tức. `close()` đợi mọi thread con kết thúc; nếu subtask bỏ qua interrupt hoặc mắc kẹt trong API không interruptible, `close()` có thể chờ vô thời hạn.

Ví dụ tác vụ cần tôn trọng interrupt:

```java
static SearchResult searchWithPolling() throws InterruptedException {
    while (true) {
        SearchResult result = tryNextBatch();
        if (result.isComplete()) {
            return result;
        }

        // sleep là interruptible; khi scope hủy, InterruptedException thoát ra.
        Thread.sleep(50);
    }
}
```

Khi dùng thư viện mạng hoặc I/O, hãy cấu hình timeout ở chính client đó và dùng API có thể đóng hoặc interrupt. Không nuốt `InterruptedException`:

```java
try {
    doBlockingWork();
} catch (InterruptedException interrupted) {
    // Giữ hợp đồng hủy của thread và kết thúc subtask.
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Subtask bị hủy", interrupted);
}
```

Nếu subtask bắt `InterruptedException` rồi tiếp tục chạy, scope có thể không đóng được đúng lúc. Hãy để exception truyền ra khi chữ ký cho phép, hoặc khôi phục interrupt status và kết thúc công việc.

`close()` luôn đợi các thread con kết thúc, kể cả khi `join()` đã ném exception. Nếu owner bị interrupt trong khi `close()` đang chờ, close vẫn tiếp tục đợi cho đến khi thread con kết thúc rồi khôi phục interrupt status. Điều này giữ nguyên ranh giới vòng đời: code sau scope không chạy trong khi các subtask của scope vẫn còn hoạt động.

## 8. Quyền sở hữu scope, kết quả và Scoped Values

Một scope thuộc về thread đã gọi `open()`:

- Chỉ owner được gọi `fork`, `join`, `close`.
- Không chuyển scope sang thread khác để thread đó fork hoặc join.
- Chỉ đọc `Subtask.get()` sau khi owner đã join và subtask ở trạng thái `SUCCESS`.
- Chỉ đọc `Subtask.exception()` sau khi owner đã join và subtask ở trạng thái `FAILED`.
- Nếu scope đã bị hủy trước khi subtask chạy hoặc hoàn tất, handle có thể ở trạng thái `UNAVAILABLE`; không gọi `get()` hoặc `exception()` trên handle đó.

Scope chụp các binding `ScopedValue` của owner khi được mở. Các thread con được tạo bởi `fork()` kế thừa các binding đó. Nếu dùng Scoped Values, hãy mở scope trong đúng phạm vi binding và chỉ chia sẻ object bất biến hoặc object có cơ chế đồng bộ phù hợp.

Có thể lồng scope: một subtask tạo scope riêng và fork các subtask cấp thấp hơn. Việc lồng tạo thành cây công việc; khi scope cha đóng, các scope con phải đóng theo thứ tự cấu trúc. Nếu đóng scope ngoài trước khi scope lồng đã đóng hoặc thay đổi binding sai phạm vi, API có thể ném `StructureViolationException` sau khi dọn dẹp.

## 9. Biên dịch và chạy preview trên JDK 27

`StructuredTaskScope` và các nested API của nó là preview API trong Java 27. API thuộc module `java.base`, do đó không cần `--add-modules`. Cần dùng JDK 27 và bật preview cả lúc biên dịch lẫn chạy:

```bash
# Dùng javac của JDK 27
javac --release 27 --enable-preview -d out src/DashboardExample.java

# Chạy bằng java của JDK 27
java --enable-preview -cp out DashboardExample
```

Class file sử dụng preview gắn với release đã biên dịch. Không lấy class file preview của Java 27 để chạy trên JDK 28, dù JDK 28 có API cuối cùng tương thích; hãy biên dịch lại bằng JDK mục tiêu. JDK 28 Early Access đã tích hợp JEP 543 thành API chính thức không đổi so với Java 27, nên khi dùng bản JDK 28 có chứa thay đổi này, bỏ `--enable-preview` và biên dịch lại. Chờ JDK 28 GA và xác nhận bản phân phối cụ thể trước khi chuyển production. [JEP 543 — OpenJDK integration](https://mail.openjdk.org/pipermail/core-libs-dev/2026-September/153000.html) · [Lịch phát hành JDK](https://ops.java/releases/?lang=en).

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy `StructuredTaskScope` hoặc `Joiner` | Compiler hoặc `--release` thấp hơn Java 27. | Dùng JDK 27 và `--release 27`. |
| Compiler báo preview disabled | Chưa bật preview. | Thêm `--enable-preview` khi biên dịch và chạy trên cùng JDK 27. |
| Không biên dịch được `catch (StructuredTaskScope.FailedException e)` | Java 27 dùng `ExecutionException` cho Joiner dựng sẵn; kiểu exception của Joiner được biểu diễn bằng `R_X`. | Bắt `ExecutionException` hoặc kiểu `R_X` mà Joiner tùy chỉnh khai báo. |
| Không biên dịch được `onTimeout()` | Java 27 dùng `Joiner.timeout()`. | Đổi sang hợp đồng `timeout()` và xử lý `CancelledByTimeoutException` làm cause khi timeout ném lỗi. |
| Không tìm thấy `Joiner.awaitAll()` | Factory này đã bị loại khỏi API Java 27. | Dùng `Joiner.allUntil(_ -> false)` để nhận danh sách subtask sau khi tất cả hoàn tất. |
| `Subtask.get()` ném `IllegalStateException` | Gọi trước `join()`, gọi từ thread không phải owner hoặc subtask không thành công. | Gọi `get()` sau join và kiểm tra `state() == SUCCESS`. |
| `close()` chờ rất lâu | Subtask không phản hồi interrupt hoặc đang block ở thao tác không interruptible. | Dùng API interruptible, timeout I/O và kết thúc công việc khi nhận interrupt. |
| Scope ném `IllegalStateException` khi đóng | Owner đã fork nhưng không gọi `join()`. | Luôn join trước khi rời scope; vẫn dùng try-with-resources để bảo đảm đóng. |
| `StructureViolationException` | Scope lồng hoặc binding `ScopedValue` bị đóng sai thứ tự/phạm vi. | Giữ cấu trúc scope và binding theo thứ tự mở/đóng. |
| Timeout không trả dữ liệu từng phần | Joiner dựng sẵn yêu cầu tất cả thành công và ném khi timeout. | Dùng `allUntil` hoặc Joiner tùy chỉnh có `timeout()` trả partial result nếu nghiệp vụ cho phép. |

## 11. Bài tập tự thực hành

1. Viết `loadDashboard(userId)` với hai subtask khác kiểu kết quả; dùng `open(config -> config.withTimeout(...))`, `join()` và `Subtask.get()`.
2. Thay default Joiner bằng `allSuccessfulOrThrow()` cho ba nguồn tìm kiếm trả cùng kiểu `String`; xác minh danh sách trả về theo thứ tự fork.
3. Tạo hai replica và dùng `anySuccessfulOrThrow()`; cho một replica thành công nhanh hơn, xác minh replica còn lại bị interrupt.
4. Dùng `allUntil(_ -> false)` để đợi tất cả subtask và trả riêng các kết quả ở trạng thái `SUCCESS`; xử lý `FAILED` mà không gọi `get()`.
5. Cấu hình timeout ngắn hơn thời gian xử lý; bắt `ExecutionException` và phân biệt `CancelledByTimeoutException` với lỗi I/O.
6. Cho một subtask ném exception; xác minh scope hủy các subtask còn lại và `close()` chỉ kết thúc sau khi chúng đã dừng.
7. Viết một Joiner dùng `R_X` là exception nghiệp vụ riêng; kiểm tra chữ ký `join()` buộc caller xử lý đúng exception đó.

## 12. Checklist trước khi đưa vào ứng dụng

- [ ] Đã xác nhận JDK mục tiêu và preview status của đúng release.
- [ ] Đã dùng API Java 27 với ba tham số kiểu `T`, `R`, `R_X`.
- [ ] Đã chọn Joiner đúng yêu cầu: tất cả thành công, một kết quả thành công hoặc partial results.
- [ ] Đã gọi `join()` trước khi đọc `Subtask.get()` hoặc `Subtask.exception()`.
- [ ] Đã xử lý `ExecutionException`, cause của timeout và `InterruptedException`.
- [ ] Đã đặt timeout phù hợp ở scope và ở từng client I/O bên trong subtask.
- [ ] Đã bảo đảm subtask phản hồi interrupt và không giữ scope đóng vô hạn.
- [ ] Đã bảo đảm chỉ owner thao tác scope và đóng scope theo thứ tự lồng nhau.
- [ ] Nếu dùng `ScopedValue`, đã mở scope trong đúng binding và chia sẻ dữ liệu an toàn.
- [ ] Đã biên dịch và chạy với `--enable-preview` trên JDK 27; đã biên dịch lại khi chuyển sang JDK 28.

## Tài liệu tham khảo chính thức

- [JEP 533: Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533)
- [Java SE 27 — `StructuredTaskScope`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Java SE 27 — `StructuredTaskScope.Joiner`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html)
- [Java SE 27 — `StructuredTaskScope.Subtask`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html)
- [Java SE 27 — Structured Concurrency, Core Libraries](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html)
- [Java SE 27 — Preview API List](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Java SE 26 — `StructuredTaskScope` (Sixth Preview)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Java SE 26 — `StructuredTaskScope.Joiner`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html)
- [JEP 543: Structured Concurrency (JDK 28)](https://openjdk.org/jeps/543)
- [JDK Releases and Support Timeline](https://ops.java/releases/?lang=en)

*Cập nhật nội dung: 27-11-2026. Trên JDK 27 đã phát hành, Structured Concurrency vẫn là preview thứ bảy. JDK 28 Early Access đã tích hợp bản chính thức tương thích với API Java 27; chỉ bỏ cờ preview khi biên dịch lại bằng JDK 28 có chứa JEP 543.*
