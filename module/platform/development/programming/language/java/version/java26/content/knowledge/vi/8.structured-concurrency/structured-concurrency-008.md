# Thất bại một phần và cách chuyển lỗi cho công việc cha

Trong một tác vụ tổng hợp dữ liệu, nhiều phần việc con có thể chạy đồng thời: lấy hồ sơ, đọc đơn hàng, tải thông báo và truy vấn gợi ý. Có phần việc là bắt buộc; chỉ cần một phần thất bại thì tác vụ cha phải thất bại. Có phần việc khác chỉ mang tính bổ sung; ứng dụng vẫn có thể trả kết quả một phần và ghi nhận phần dữ liệu bị thiếu.

Structured Concurrency cung cấp một ranh giới rõ ràng để nhóm các phần việc con, chờ kết quả và quyết định cách xử lý lỗi. `StructuredTaskScope.join()` là điểm công việc cha nhận kết quả hoặc exception từ nhóm tác vụ. `Joiner` xác định chính sách khi một hay nhiều phần việc hoàn tất hoặc thất bại.

Trong Java 26, API này ở preview lần thứ sáu qua JEP 525. Đến JDK 27, preview lần thứ bảy qua JEP 533 thay đổi cách khai báo exception của `join()`. JEP 543 đã đưa API vào trạng thái final trong JDK 28; tuy nhiên, tại ngày 27-11-2026, JDK 28 vẫn là Early Access. Bài này giải thích hành vi của Java 26, đồng thời ưu tiên các chính sách và cách viết còn phù hợp với API final để tránh phụ thuộc vào thiết kế preview đã bị thay thế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách exception từ subtask được chuyển về owner thread qua `join()`.
- Phân biệt chính sách fail-fast, cần ít nhất một kết quả thành công và thu thập kết quả từng phần.
- Giữ nguyên exception gốc làm cause khi chuyển lỗi kỹ thuật thành exception nghiệp vụ của tác vụ cha.
- Đọc trạng thái `SUCCESS`, `FAILED`, `UNAVAILABLE` và chỉ lấy kết quả hoặc exception khi trạng thái cho phép.
- Hiểu vai trò của `Joiner`, hủy các tác vụ còn chạy và yêu cầu subtask phản hồi interruption.
- Phân biệt API Java 26 preview lần 6, Java 27 preview lần 7 và API final của JDK 28.

## 1. Ranh giới lỗi giữa tác vụ con và tác vụ cha

Khi owner thread mở `StructuredTaskScope`, nó trở thành cha của các subtask được tạo bằng `fork(...)`. Các subtask chạy đồng thời trong những thread riêng; mặc định JDK sử dụng virtual thread. Owner thread tiếp tục công việc thiết lập, sau đó gọi `join()` để nhận một kết quả chung từ scope.

Một subtask có thể:

- Hoàn thành thành công và trả về giá trị.
- Ném exception hoặc error.
- Chưa có kết quả khả dụng vì scope đã bị hủy trước khi subtask hoàn tất hoặc trước khi nó được chạy.

Khi subtask thất bại, exception không tự nhảy trực tiếp vào call stack của owner thread. `Joiner` quan sát trạng thái hoàn tất, quyết định có hủy các subtask khác hay không, rồi tạo kết quả hoặc exception cho `join()`. Owner nhận exception tại điểm `join()` và có thể chuyển nó thành lỗi ở tầng nghiệp vụ.

```text
Owner thread (tác vụ cha)
    │
    ├── fork() ──> Subtask A ──> thành công
    │
    ├── fork() ──> Subtask B ──> IOException
    │
    ├── fork() ──> Subtask C ──> đang chạy
    │
    └── join()
          │
          ├── Joiner áp dụng chính sách hoàn tất/thất bại
          ├── có thể hủy Subtask C bằng interruption
          └── trả kết quả hoặc ném exception về owner
```

Đây là điểm khác biệt quan trọng so với việc khởi chạy nhiều tác vụ độc lập rồi để chúng chạy nền. Scope có vòng đời gắn với block `try` và `close()` chờ các thread con kết thúc trước khi owner thoát khỏi scope.

## 2. Chính sách mặc định: mọi subtask đều phải thành công

Với `StructuredTaskScope.open()` không truyền `Joiner`, chính sách mặc định tương đương `Joiner.awaitAllSuccessfulOrThrow()`. Scope chờ tất cả subtask thành công; nếu một subtask thất bại, scope bị hủy và `join()` ném exception.

Ví dụ một trang hồ sơ cần đồng thời thông tin người dùng và danh sách đơn hàng:

```java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

record User(String id, String name) {}
record Order(String id, long total) {}
record Profile(User user, List<Order> orders) {}

static Profile loadProfile(String userId)
        throws InterruptedException, ProfileLoadException {
    try (var scope = StructuredTaskScope.open()) {
        Subtask<User> user = scope.fork(() -> userService.find(userId));
        Subtask<List<Order>> orders =
                scope.fork(() -> orderService.findByUser(userId));

        // Nếu một subtask thất bại, join() chuyển lỗi về owner.
        scope.join();

        // Chỉ đọc kết quả sau khi join() thành công.
        return new Profile(user.get(), orders.get());
    } catch (StructuredTaskScope.FailedException e) {
        throw new ProfileLoadException(
                "Không thể tải đầy đủ hồ sơ người dùng " + userId,
                e.getCause());
    }
}

final class ProfileLoadException extends Exception {
    ProfileLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Ví dụ trên dùng API Java 26 preview lần thứ sáu. Khi cả hai subtask thành công, owner gọi `get()` để lấy dữ liệu và tạo `Profile`. Nếu một subtask ném exception, `join()` ném `StructuredTaskScope.FailedException`; exception gốc được giữ trong `getCause()`. Scope hủy subtask còn chạy bằng interruption.

`Subtask.get()` chỉ được gọi sau khi owner đã join và subtask ở trạng thái `SUCCESS`. Nếu subtask thất bại, dùng `exception()` sau khi join để lấy exception gốc. Không gọi `get()` trong nhánh thất bại.

### Chuyển lỗi kỹ thuật thành lỗi nghiệp vụ của cha

Exception từ tầng HTTP, database hoặc file system thường không nên trở thành hợp đồng công khai của tầng dịch vụ. Owner có thể giữ nguyên cause nhưng bọc bằng exception mô tả thao tác nghiệp vụ:

```java
catch (StructuredTaskScope.FailedException e) {
    Throwable cause = e.getCause();

    if (cause instanceof java.io.IOException io) {
        throw new ProfileLoadException(
                "Dịch vụ hồ sơ không đọc được dữ liệu", io);
    }

    throw new ProfileLoadException(
            "Không thể hoàn tất yêu cầu hồ sơ", cause);
}
```

Giữ cause giúp log, telemetry và tầng xử lý lỗi vẫn truy được nguyên nhân gốc. Không chỉ ghi message rồi bỏ exception gốc; như vậy sẽ mất stack trace của lỗi từ subtask.

## 3. API final của JDK 28: chuyển lỗi qua `ExecutionException` hoặc exception riêng

JDK 27 bổ sung tham số kiểu thứ ba `R_X` cho `StructuredTaskScope<T, R, R_X extends Throwable>`. Tham số này mô tả chính xác exception mà `join()` có thể ném. JEP 543 final hóa API này trong JDK 28 mà không thay đổi hình dạng API đã có ở preview lần thứ bảy.

Với chính sách mặc định của JDK 28, `join()` ném `ExecutionException` nếu một subtask thất bại. Exception của subtask nằm trong `getCause()`:

```java
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

static Profile loadProfile(String userId)
        throws InterruptedException, ProfileLoadException {
    try (var scope = StructuredTaskScope.open()) {
        Subtask<User> user = scope.fork(() -> userService.find(userId));
        Subtask<List<Order>> orders =
                scope.fork(() -> orderService.findByUser(userId));

        scope.join();
        return new Profile(user.get(), orders.get());
    } catch (ExecutionException e) {
        throw new ProfileLoadException(
                "Không thể tải đầy đủ hồ sơ người dùng " + userId,
                e.getCause());
    }
}
```

Nếu muốn `join()` ném trực tiếp exception nghiệp vụ đã định nghĩa, dùng `Joiner.awaitAllSuccessfulOrThrow(Function)`:

```java
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;
import java.util.concurrent.StructuredTaskScope.Subtask;

static Profile loadProfile(String userId)
        throws InterruptedException, ProfileLoadException {
    var joiner = Joiner.<Object, ProfileLoadException>
            awaitAllSuccessfulOrThrow(cause ->
                    new ProfileLoadException(
                            "Không thể tải đầy đủ hồ sơ người dùng " + userId,
                            cause));

    try (var scope = StructuredTaskScope.open(joiner)) {
        Subtask<User> user = scope.fork(() -> userService.find(userId));
        Subtask<List<Order>> orders =
                scope.fork(() -> orderService.findByUser(userId));

        scope.join(); // Ném ProfileLoadException nếu có subtask thất bại.
        return new Profile(user.get(), orders.get());
    }
}
```

`Object` là kiểu kết quả chung của scope nên có thể fork các subtask trả về kiểu khác nhau. `awaitAllSuccessfulOrThrow` phù hợp khi cần giữ handle từng subtask để đọc các kết quả có kiểu riêng sau khi tất cả thành công. Hàm chuyển exception của `Joiner` phải tạo exception mới với exception đầu vào làm cause.

## 4. Một lỗi làm hủy các phần việc còn lại

Fail-fast là chính sách đúng khi kết quả chỉ có ý nghĩa nếu tất cả thành phần bắt buộc đều thành công. Ví dụ, không thể tạo hóa đơn hợp lệ nếu thiếu thông tin khách hàng hoặc thiếu dữ liệu tính tiền. Khi một subtask thất bại, tiếp tục chờ các subtask khác có thể chỉ lãng phí tài nguyên.

Khi scope bị hủy:

1. Không nhận thêm subtask mới.
2. Các subtask chưa hoàn tất bị hủy; thread đang chạy được interrupt.
3. `join()` thức dậy với kết quả hoặc exception theo chính sách của `Joiner`.
4. `close()` vẫn đợi các thread con kết thúc trước khi owner thoát khỏi block.

Hủy bằng interruption là yêu cầu hợp tác. Mỗi subtask nên dùng API có thể bị interrupt và thoát nhanh khi nhận tín hiệu. Không nên nuốt `InterruptedException` rồi tiếp tục vòng lặp hoặc chờ một thao tác không thể bị hủy. Nếu subtask dùng client mạng hoặc driver có timeout riêng, cấu hình timeout để thời gian đóng scope có giới hạn thực tế.

Nếu nhiều subtask thất bại gần như đồng thời, đừng dựa vào thứ tự hoàn tất để suy ra exception nào chắc chắn được chọn làm cause. Hãy xử lý exception được báo như nguyên nhân đại diện cho lần join thất bại; nếu nghiệp vụ cần tổng hợp mọi lỗi, dùng chính sách thu thập kết quả từng phần ở phần tiếp theo.

## 5. Thất bại một phần: giữ kết quả thành công và ghi nhận phần lỗi

Không phải mọi phần việc đều bắt buộc. Một dashboard có thể hiển thị thông tin tài khoản và cảnh báo ngay cả khi phần gợi ý sản phẩm không tải được. Với trường hợp này, fail-fast mặc định quá nghiêm ngặt: một lỗi phụ sẽ hủy các phần việc khác và không cho owner xử lý kết quả thành công theo cách mong muốn.

`Joiner.allUntil(_ -> false)` cho phép chờ mọi subtask kết thúc và trả về danh sách handle theo thứ tự fork. Predicate luôn trả về `false`, vì vậy nó không yêu cầu hủy scope khi có lỗi. Owner kiểm tra trạng thái từng subtask sau `join()` và tự quyết định phần nào được hiển thị.

Ví dụ dưới đây dùng Java 26 preview lần thứ sáu; cách dùng `allUntil` và các trạng thái subtask tiếp tục có trong API final JDK 28:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;
import java.util.concurrent.StructuredTaskScope.Subtask;

record PartResult(String name, String content) {}
record PartFailure(String name, Throwable cause) {}
record Dashboard(List<PartResult> parts, List<PartFailure> failures) {}

static Dashboard loadDashboard() throws InterruptedException {
    try (var scope = StructuredTaskScope.open(
            Joiner.<PartResult>allUntil(subtask -> false))) {

        Subtask<PartResult> profile = scope.fork(() ->
                new PartResult("profile", profileService.loadSummary()));
        Subtask<PartResult> alerts = scope.fork(() ->
                new PartResult("alerts", alertService.loadRecent()));
        Subtask<PartResult> recommendations = scope.fork(() ->
                new PartResult("recommendations", recommendationService.load()));

        // allUntil(false) chờ các subtask hoàn tất; owner giữ các handle bên dưới.
        scope.join();

        List<PartResult> successful = new ArrayList<>();
        List<PartFailure> failed = new ArrayList<>();

        collect("profile", profile, successful, failed);
        collect("alerts", alerts, successful, failed);
        collect("recommendations", recommendations, successful, failed);

        return new Dashboard(List.copyOf(successful), List.copyOf(failed));
    }
}

static void collect(
        String name,
        Subtask<PartResult> subtask,
        List<PartResult> successful,
        List<PartFailure> failed) {

    switch (subtask.state()) {
        case SUCCESS -> successful.add(subtask.get());
        case FAILED -> failed.add(new PartFailure(name, subtask.exception()));
        case UNAVAILABLE -> failed.add(new PartFailure(
                name, new IllegalStateException("Subtask chưa có kết quả")));
    }
}
```

Trong ví dụ không cấu hình timeout và predicate không hủy scope, vì vậy các subtask được chờ tới khi hoàn tất. Các biến `profile`, `alerts` và `recommendations` giữ handle để owner gắn lỗi với tên thành phần. Nếu có timeout hoặc scope bị hủy bởi một chính sách khác, trạng thái `UNAVAILABLE` cho biết kết quả chưa dùng được.

Quy tắc đọc trạng thái:

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| `SUCCESS` | Subtask hoàn thành thành công | Gọi `get()` để lấy kết quả |
| `FAILED` | Subtask ném exception/error hoặc không tạo được thread | Gọi `exception()` để lấy nguyên nhân |
| `UNAVAILABLE` | Kết quả chưa khả dụng, ví dụ chưa hoàn tất trước khi scope bị hủy | Không gọi `get()` hoặc `exception()`; xử lý như phần dữ liệu chưa có |

Sau khi thu thập, owner có thể trả dashboard thiếu một số phần, ghi warning theo tên thành phần, hoặc quyết định thất bại toàn bộ nếu không đạt ngưỡng dữ liệu tối thiểu. Chính sách nghiệp vụ nằm ở owner; `Joiner` chỉ quyết định khi nào scope tiếp tục hay hủy và trả về những handle nào.

## 6. Chọn Joiner theo yêu cầu nghiệp vụ

| Chính sách | Joiner | Hành vi khi có lỗi |
|---|---|---|
| Mọi subtask đều bắt buộc, kết quả khác kiểu | `awaitAllSuccessfulOrThrow()` hoặc `open()` | Hủy phần việc còn chạy và ném exception về owner |
| Mọi subtask đều bắt buộc, kết quả cùng kiểu | `allSuccessfulOrThrow()` | Hủy khi một subtask thất bại; trả `List<T>` nếu tất cả thành công |
| Chỉ cần một kết quả thành công | `anySuccessfulOrThrow()` | Hủy các phần việc còn lại khi có kết quả thành công; chỉ ném nếu tất cả thất bại |
| Muốn thu thập thành công và thất bại của từng phần | `allUntil(_ -> false)` | Chờ hoàn tất, trả danh sách `Subtask<T>` để owner kiểm tra trạng thái |
| Muốn hủy khi đạt ngưỡng hoàn tất hoặc số lỗi | `allUntil(predicate)` | Predicate quyết định khi nào hủy; phải an toàn khi được gọi đồng thời |

Các Joiner trả về một kết quả không `null` có thể giúp owner không phải tự giữ từng handle. Nếu cần kết quả khác kiểu, cần đọc `Subtask` riêng sau join hoặc bọc các loại kết quả trong một kiểu chung. Không dùng `anySuccessfulOrThrow` nếu nghiệp vụ yêu cầu tổng hợp tất cả kết quả thành công; Joiner này dừng khi có một kết quả đủ điều kiện.

### Chuyển lỗi có chọn lọc ngay trong subtask

Một số lỗi có thể khôi phục bằng giá trị mặc định. Ví dụ, nếu phần gợi ý không tải được thì trả danh sách rỗng, nhưng lỗi tải hồ sơ vẫn phải làm tác vụ cha thất bại. Có thể xử lý đúng loại lỗi trong Callable:

```java
Subtask<List<String>> recommendations = scope.fork(() -> {
    try {
        return recommendationService.load();
    } catch (java.io.IOException recoverable) {
        return List.of();
    }
});
```

Trong trường hợp này, subtask hoàn tất thành công với giá trị fallback nên Joiner mặc định không hủy các phần việc khác. Chỉ xử lý những lỗi mà nghiệp vụ đã xác định có thể thay thế bằng fallback. Không bắt mọi `Throwable`, không che giấu lỗi lập trình và không nuốt interruption. Nếu cần hiển thị cảnh báo rằng đã dùng fallback, trả về một kiểu kết quả có metadata như `Result<T>(value, warning)` thay vì làm như dữ liệu là kết quả bình thường.

## 7. Dùng Joiner tùy chỉnh để đặt ngưỡng hủy

Với hệ thống đọc dữ liệu từ nhiều replica, có thể muốn tiếp tục khi một replica lỗi nhưng dừng sau khi đã có đủ kết quả hoặc khi số lỗi vượt ngưỡng. `Joiner.allUntil(predicate)` hỗ trợ quyết định hủy dựa trên từng subtask vừa hoàn tất.

Ví dụ dừng khi có hai replica thất bại:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.StructuredTaskScope.Joiner;
import java.util.concurrent.StructuredTaskScope.Subtask;

AtomicInteger failures = new AtomicInteger();

var joiner = Joiner.<String>allUntil(subtask ->
        subtask.state() == Subtask.State.FAILED
                && failures.incrementAndGet() >= 2);
```

`onComplete` của Joiner có thể được gọi đồng thời từ nhiều thread. Vì vậy, bộ đếm phải thread-safe; không dùng `int` thường rồi tăng trực tiếp từ predicate. Khi predicate trả `true`, scope hủy các subtask chưa hoàn tất. Danh sách trả về có thể chứa `UNAVAILABLE` cho những subtask chưa hoàn tất hoặc hoàn tất sau khi scope đã bị hủy.

Nếu nghiệp vụ yêu cầu ít nhất hai replica thành công, predicate cũng có thể theo dõi số kết quả `SUCCESS`. Hãy xác định rõ hành vi khi hết timeout, khi tất cả replica đều lỗi và khi scope bị hủy trước khi đủ kết quả. `Joiner` là nơi đặt chính sách đồng thời; owner vẫn chịu trách nhiệm diễn giải các trạng thái và tạo phản hồi nghiệp vụ.

## 8. Phân biệt lỗi subtask, lỗi của join và timeout

Không phải exception nào ở parent cũng có nghĩa là một subtask thất bại:

| Nguồn lỗi | Nơi owner nhận được | Cách xử lý |
|---|---|---|
| Callable/Runnable của subtask ném exception | `join()` theo chính sách Joiner; cause được giữ lại hoặc subtask chuyển sang `FAILED` | Ánh xạ sang lỗi nghiệp vụ hoặc thu thập theo từng phần |
| Owner thread bị interrupt khi chờ | `join()` ném `InterruptedException` | Thường truyền tiếp interruption; không gộp thành lỗi dịch vụ thông thường |
| Timeout của scope | Kết quả/exception theo Joiner và cấu hình timeout của phiên bản JDK | Phân biệt timeout với lỗi từ dịch vụ con |
| Không tạo được thread cho subtask | `fork()` có thể ném `RejectedExecutionException`; với một số Joiner, handle có thể ở `FAILED` | Xử lý như lỗi khởi chạy công việc, không giả định Callable đã chạy |
| Lỗi khi đóng scope hoặc vi phạm cấu trúc | `close()` hoặc API scope ném exception tương ứng | Kiểm tra owner thread, thứ tự scope và việc đã gọi `join()` |

Nếu `join()` ném `InterruptedException`, hãy để phương thức cha khai báo và truyền tiếp nếu không có lý do nghiệp vụ rõ ràng để xử lý tại chỗ. Nếu buộc phải bắt mà không thể ném tiếp, khôi phục trạng thái interrupt bằng `Thread.currentThread().interrupt()` trước khi kết thúc hoặc chuyển điều khiển. Không bọc interruption thành `ProfileLoadException` như thể dịch vụ từ xa đã trả lỗi.

Trong Java 26, timeout được biểu diễn bằng `StructuredTaskScope.TimeoutException` và callback `Joiner.onTimeout()`. Ở API final JDK 28, timeout được biểu diễn qua `StructuredTaskScope.CancelledByTimeoutException` làm cause của exception do Joiner ném; phương thức của Joiner là `timeout()`. Khi nâng cấp, hãy tách nhánh timeout khỏi exception của subtask để không ghi nhận sai nguyên nhân.

## 9. Ràng buộc vòng đời và an toàn khi hủy

Một số quy tắc cần giữ trong mọi chính sách:

- Chỉ owner thread mở scope mới được gọi `fork()`, `join()` và `close()`.
- Gọi `join()` sau khi fork để nhận kết quả của scope; không đọc `get()` hoặc `exception()` trước khi owner đã join.
- Không fork thêm subtask sau khi đã join.
- Dùng `try`-with-resources để scope luôn được đóng, kể cả khi owner xử lý exception.
- Khi scope bị hủy, subtask chưa hoàn tất được interrupt; code con phải phản hồi interruption và giải phóng tài nguyên.
- `close()` chờ các thread con kết thúc. Nếu một subtask mắc kẹt trong thao tác không thể interrupt, thời gian đóng scope có thể kéo dài vô hạn.
- Nếu dùng timeout, nhớ rằng timeout bắt đầu theo cấu hình scope và Joiner quyết định kết quả `join()` khi deadline hết hạn.

Không dùng scope như một cơ chế khởi chạy tác vụ nền rồi bỏ mặc. Công việc con phải thuộc vòng đời của tác vụ cha và kết thúc trước khi cha rời scope. Nếu một tác vụ cần sống độc lập sau request, hãy thiết kế một thành phần quản lý công việc nền có vòng đời riêng thay vì giữ nó trong scope của request.

## 10. Trạng thái preview và thay đổi API từ Java 26 tới JDK 28

Structured Concurrency đã trải qua nhiều lần preview. Trạng thái liên quan trực tiếp tới module này:

| JDK | JEP | Trạng thái | Khác biệt đáng chú ý về exception |
|---|---|---|---|
| Java 26 | JEP 525 | Preview lần 6 | `join()` ném `StructuredTaskScope.FailedException`; timeout dùng `TimeoutException` và `Joiner.onTimeout()` |
| Java 27 | JEP 533 | Preview lần 7 | Thêm kiểu generic `R_X`; Joiner khai báo kiểu exception của `join()`; mặc định dùng `ExecutionException` và `CancelledByTimeoutException` |
| Java 28 | JEP 543 | Final | Giữ hình dạng API của preview lần 7; `StructuredTaskScope` không còn yêu cầu bật preview |

JDK 28 đã tích hợp JEP 543 và final hóa Structured Concurrency, nhưng tại ngày 27-11-2026 JDK 28 vẫn là Early Access; lịch phát hành GA được công bố cho tháng 03-2027. Vì vậy, không coi một EA build là runtime production ổn định. JDK 26 và JDK 27 phát hành GA vẫn yêu cầu bật preview khi dùng StructuredTaskScope.

Khi nâng mã từ Java 26 lên API final JDK 28, chú ý:

- Đổi `catch (StructuredTaskScope.FailedException e)` thành `catch (ExecutionException e)` khi dùng Joiner mặc định, hoặc khai báo kiểu exception riêng qua `R_X` và Joiner tương ứng.
- `StructuredTaskScope` có ba tham số kiểu `T, R, R_X` thay vì hai tham số `T, R`.
- Timeout được báo qua `CancelledByTimeoutException` làm cause; API final dùng `Joiner.timeout()` thay cho `onTimeout()`.
- `Joiner.awaitAll()` có trong preview Java 26 nhưng không còn trong API final. Dùng `Joiner.allUntil(_ -> false)` nếu cần chờ mọi subtask và nhận danh sách handle để kiểm tra trạng thái.
- `Joiner.allUntil` vẫn là lựa chọn phù hợp để thu thập kết quả từng phần; predicate phải thread-safe vì có thể được gọi đồng thời.

## 11. Biên dịch và chạy theo JDK

Với mã dùng Structured Concurrency preview của Java 26, compiler và runtime phải là JDK 26. Ví dụ:

```bash
javac --release 26 --enable-preview -Xlint:preview DashboardService.java
java --enable-preview DashboardService
```

Với Java 27 preview lần thứ bảy, dùng JDK 27 ở cả hai bước và vẫn bật `--enable-preview`:

```bash
javac --release 27 --enable-preview -Xlint:preview DashboardService.java
java --enable-preview DashboardService
```

Với API final trong JDK 28, không cần `--enable-preview`. Tuy nhiên, tại thời điểm hiện tại chỉ dùng JDK 28 Early Access để đánh giá và thử nghiệm nâng cấp; chờ bản GA và kiểm tra chính sách hỗ trợ của môi trường triển khai trước khi đưa vào production.

Nếu dự án chưa thể dùng preview và chưa thể nâng lên JDK có API final, không đưa StructuredTaskScope preview vào hợp đồng thư viện production. Có thể tiếp tục dùng các API đồng thời chính thức sẵn có trong JDK mục tiêu với chính sách quản lý Future, hủy tác vụ và đóng executor rõ ràng.

## 12. Bài tập thực hành

Bạn đang xây dựng API dashboard gồm ba phần: hồ sơ người dùng, cảnh báo và gợi ý. Hồ sơ là dữ liệu bắt buộc; cảnh báo và gợi ý có thể thiếu mà dashboard vẫn hiển thị được.

**Yêu cầu:**

1. Tạo ba subtask chạy song song để tải ba phần dữ liệu.
2. Viết phiên bản fail-fast bằng `StructuredTaskScope.open()`; nếu hồ sơ hoặc một phần bất kỳ thất bại, giải thích cách lỗi đi qua `join()` về owner.
3. Viết phiên bản chịu lỗi một phần bằng `Joiner.allUntil(_ -> false)`; thu thập các trạng thái `SUCCESS`, `FAILED`, `UNAVAILABLE`.
4. Giữ exception gốc của mỗi phần thất bại và gắn tên phần dữ liệu vào báo cáo lỗi.
5. Nếu hồ sơ thất bại, ném exception nghiệp vụ `DashboardUnavailableException`; nếu chỉ cảnh báo hoặc gợi ý thất bại, trả dashboard kèm danh sách phần bị thiếu.
6. Thử hủy scope khi có hai phần thất bại; dùng bộ đếm thread-safe trong predicate.
7. Thử interrupt owner thread khi đang join và phân biệt `InterruptedException` với lỗi của subtask.
8. Đối chiếu mã Java 26 preview lần 6 với API final JDK 28; giải thích thay đổi từ `FailedException` sang `ExecutionException` hoặc exception type do `R_X` khai báo.

**Kết quả mong đợi:**

- Phiên bản fail-fast hủy các subtask còn chạy khi có lỗi bắt buộc và chuyển cause về owner.
- Phiên bản chịu lỗi một phần vẫn thu thập các kết quả thành công và ghi nhận lỗi của từng phần.
- Owner không gọi `get()` khi trạng thái không phải `SUCCESS`, cũng không gọi `exception()` khi trạng thái không phải `FAILED`.
- Exception nghiệp vụ của parent giữ nguyên cause gốc.
- Subtask phản hồi interruption để `close()` không bị kẹt khi hủy.
- Người học không dùng `Joiner.awaitAll()` trong mã hướng tới API final JDK 28.

## Tài liệu tham khảo

- [JEP 525: Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): trạng thái và thay đổi API của Structured Concurrency trong Java 26.
- [StructuredTaskScope — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): fail-fast mặc định, `FailedException`, vòng đời scope và cách xử lý cause.
- [StructuredTaskScope.Joiner — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): `allSuccessfulOrThrow`, `anySuccessfulOrThrow`, `awaitAll`, `allUntil` và yêu cầu thread safety.
- [StructuredTaskScope.Subtask.State — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.State.html): ý nghĩa của `SUCCESS`, `FAILED` và `UNAVAILABLE`.
- [JEP 533: Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533): thay đổi generic exception type và xử lý exception trong Java 27.
- [StructuredTaskScope — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): `ExecutionException`, `R_X` và cause của lỗi.
- [JEP 543: Structured Concurrency](https://openjdk.org/jeps/543): final hóa API trong JDK 28.
- [StructuredTaskScope — JDK 28 Early Access API](https://cr.openjdk.org/~alanb/sc-jdk28/api/java.base/java/util/concurrent/StructuredTaskScope.html) và [StructuredTaskScope.Joiner — JDK 28 Early Access API](https://cr.openjdk.org/~alanb/sc-jdk28/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html): API final, exception type, joiner và cách thu thập trạng thái subtask.
- [Structured Concurrency — Java SE 27 Core Libraries](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html): mô hình scope, fork/join/close và xử lý lỗi.
