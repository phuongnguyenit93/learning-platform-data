# Khởi chạy tác vụ con, chờ hoàn tất và truy xuất kết quả theo hợp đồng của scope

## 1. Phạm vi và mốc API sử dụng

Trong chương **Đồng thời có cấu trúc** của module `JAVA_VERSION_JAVA22`, bài này tập trung vào chu trình mở scope, khởi chạy tác vụ con, chờ kết quả và đóng scope. Đây là kiến thức hữu ích khi một yêu cầu cần thực hiện nhiều công việc liên quan, chẳng hạn tải hồ sơ và đếm thông báo để tạo một trang người dùng.

Java 22 cung cấp Structured Concurrency dưới dạng preview lần hai qua JEP 462. Trong **JDK 27**, API này vẫn là preview, ở lần thứ bảy qua JEP 533. Vì yêu cầu chỉ dùng kiến thức còn áp dụng, mã trong bài sử dụng **API của JDK 27**; không giả định mã preview của Java 22 có thể được giữ nguyên trên JDK hiện đại. [Oracle: Structured Concurrency trong Java 22](https://docs.oracle.com/en/java/javase/22/core/structured-concurrency.html), [Oracle: thay đổi trong JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html).

Để chạy ví dụ `PageDemo.java` ở mục 3, dùng đúng JDK 27 và bật preview khi biên dịch lẫn thực thi:

```powershell
javac --enable-preview --release 27 PageDemo.java
java --enable-preview PageDemo
```

Hoặc chạy từ nguồn:

```powershell
java --enable-preview --source 27 PageDemo.java
```

Preview chưa phải hợp đồng API vĩnh viễn. Khi nâng JDK, cần đối chiếu lại tài liệu của phiên bản đích. [Oracle: sử dụng preview features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html).

## 2. Ba thao tác phục vụ ba trách nhiệm

| Thao tác | Trách nhiệm trong chương trình |
| --- | --- |
| `fork(...)` | Khởi chạy công việc con và trả về handle `Subtask<T>` |
| `join()` | Chờ outcome chung theo policy của scope |
| `Subtask.get()` | Đọc giá trị thành công sau khi đã join đúng hợp đồng |

Mở scope bằng `StructuredTaskScope.open()` trong `try`-with-resources. Theo cấu hình mặc định, mỗi tác vụ con chạy trên một virtual thread. Sau khi fork các tác vụ, owner gọi `join()`, xử lý outcome rồi để `close()` đóng scope. [Oracle: cách sử dụng Structured Concurrency](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html).

Một thứ tự dễ kiểm tra khi đọc mã là:

```text
Mở scope
    → fork tác vụ A
    → fork tác vụ B
    → join theo policy
    → đọc hoặc xử lý outcome
    → close trước khi rời phạm vi
```

Điểm cần xác định trước khi viết mã là **điều kiện đủ để công việc cha thành công**. Nếu trang người dùng cần cả hồ sơ lẫn số thông báo, thiếu một trong hai thì chưa có trang hoàn chỉnh. Nếu chỉ cần dữ liệu từ một trong hai bản sao, điều kiện thành công sẽ khác.

## 3. Ví dụ đầy đủ: kết hợp hai kết quả khác kiểu

Lưu nội dung sau vào `PageDemo.java`. Hai hàm có `Thread.sleep` chỉ mô phỏng thời gian chờ dịch vụ; ví dụ không gọi mạng.

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

public class PageDemo {
    record User(long id, String name) {}
    record Page(User user, int unreadCount) {}

    static User findUser(long userId) throws InterruptedException {
        if (userId <= 0) {
            throw new IllegalArgumentException("userId must be positive");
        }
        Thread.sleep(100);
        return new User(userId, "Lan");
    }

    static int countUnread(long userId) throws InterruptedException {
        Thread.sleep(180);
        return 3;
    }

    static Page loadPage(long userId)
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open()) {
            Subtask<User> user = scope.fork(() -> findUser(userId));
            Subtask<Integer> unread = scope.fork(() -> countUnread(userId));

            scope.join();

            return new Page(user.get(), unread.get());
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        System.out.println(loadPage(42));
    }
}
```

Kết quả dự kiến:

```text
Page[user=User[id=42, name=Lan], unreadCount=3]
```

Với policy mặc định của JDK 27, `join()` trả `null` khi mọi tác vụ thành công. Một tác vụ thất bại khiến scope hủy công việc còn lại và join ném `ExecutionException`. Dòng tạo `Page` chỉ chạy khi cả hai kết quả thành công. [Javadoc JDK 27: StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

Hai lệnh `fork` xuất hiện trước `join`, nên các công việc có cơ hội chạy đồng thời. Thứ tự khai báo không cam kết thứ tự hoàn tất. Nếu thay `loadPage(42)` bằng `loadPage(-1)`, trang sẽ không được tạo; không nên khẳng định tác vụ đếm thông báo đã chạy đến đâu tại thời điểm hủy.

Biểu thức `return new Page(...)` cũng không làm bỏ qua việc đóng tài nguyên: `try`-with-resources vẫn thực hiện `close()` trước khi phương thức thực sự trả về cho bên gọi. [JLS 27, §14.20.3](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.20.3).

## 4. Handle không phải giá trị, và `get()` không phải bước chờ

Với khai báo:

```java
Subtask<User> user = scope.fork(() -> findUser(userId));
```

`user` là handle của công việc trả về `User`; nó chưa phải đối tượng hồ sơ cần hiển thị. Trong mã owner, phải join trước khi dùng `get()` hoặc `exception()`. `get()` chỉ trả kết quả thành công; gọi quá sớm hoặc gọi trên tác vụ không thành công sẽ gây `IllegalStateException`. Một kết quả thành công vẫn có thể là `null`. [Javadoc: Subtask](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html).

Không dùng cách sau để chờ:

```java
Subtask<User> user = scope.fork(() -> findUser(userId));
User result = user.get(); // Sai: owner chưa join.
```

Ngay cả khi tác vụ chạy rất nhanh và đã có trạng thái `SUCCESS`, owner vẫn phải tuân thủ bước join. Kiểm tra trạng thái hoặc thêm `Thread.sleep` vào owner không thay thế được bước này.

Tên phương thức dễ gây nhầm với `Future.get()`: phương thức đó có thể chặn để chờ kết quả. Với `Subtask`, hãy dùng `scope.join()` làm bước đồng bộ của nhóm, rồi đọc outcome đã sẵn sàng. [Javadoc: Future.get](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html#get()).

Trong bài này, mọi thao tác đọc outcome đều được thực hiện ngay trong owner sau join. Cơ chế callback của custom `Joiner` có ngữ cảnh truy cập riêng và không phải mẫu sử dụng đang minh họa.

## 5. Đọc trạng thái trước khi chọn phương thức truy xuất

`Subtask` có ba trạng thái:

| Trạng thái | Ý nghĩa | Truy xuất phù hợp sau join |
| --- | --- | --- |
| `SUCCESS` | Tác vụ hoàn tất thành công | `get()` |
| `FAILED` | Tác vụ thất bại với exception hoặc error | `exception()` |
| `UNAVAILABLE` | Chưa có outcome dùng được; có thể chưa hoàn tất hoặc liên quan đến việc hủy scope | Không gọi hai phương thức trên để lấy outcome |

`UNAVAILABLE` cũng có thể xuất hiện nếu tác vụ được fork sau khi scope đã bị hủy, hoặc hoàn tất sau thời điểm hủy. Nó không phải bằng chứng rằng luồng vẫn đang chạy; sau khi scope đóng, handle cũng không bắt buộc chuyển thành `SUCCESS` hoặc `FAILED`. [Javadoc: Subtask.State](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.State.html).

Với ví dụ `loadPage`, policy mặc định đã bảo đảm cả hai thành công khi join trả về bình thường, nên có thể gọi trực tiếp hai `get()`. Với policy cho phép lỗi hoặc dừng sớm, phải xem lại điều kiện đó. **Join trả về bình thường có ý nghĩa theo policy, không tự động đồng nghĩa mọi handle đều đọc được bằng `get()`.**

## 6. Policy quyết định hợp đồng của `join()`

JDK 27 dùng `Joiner` để mô tả cách kết hợp outcome và điều kiện hủy:

| Cách mở scope hoặc chọn joiner | Outcome khi join thành công | Khi tác vụ thất bại |
| --- | --- | --- |
| `StructuredTaskScope.open()` | `null`; giữ handle để đọc từng giá trị | Một lỗi làm scope bị hủy và join ném `ExecutionException` |
| `Joiner.<T>allSuccessfulOrThrow()` | `List<T>` theo thứ tự fork | Một lỗi làm join ném `ExecutionException` |
| `Joiner.<T>anySuccessfulOrThrow()` | Một giá trị thành công | Chỉ thất bại nếu không có tác vụ nào thành công |
| `Joiner.<T>allUntil(predicate)` | Danh sách handle để tự xử lý | Lỗi của tác vụ không tự làm join ném exception |

`anySuccessfulOrThrow()` hủy scope khi có tác vụ thành công. `allUntil` hủy khi predicate trả về `true`; nó cũng có thể trả danh sách handle khi timeout. Mỗi scope cần một joiner mới. [Javadoc JDK 27: Joiner](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html).

### 6.1. Thu thập các kết quả cùng kiểu

Nếu muốn danh sách nhãn từ nhiều tác vụ, có thể để joiner trả kết quả trực tiếp. Đặt phương thức sau trong `PageDemo`, đồng thời thêm import `java.util.List` và `java.util.concurrent.StructuredTaskScope.Joiner`:

```java
static List<String> loadLabels()
        throws InterruptedException, ExecutionException {
    try (var scope = StructuredTaskScope.open(
            Joiner.<String>allSuccessfulOrThrow())) {
        scope.fork(() -> {
            Thread.sleep(100);
            return "Ho so";
        });
        scope.fork(() -> "Thong bao");

        return scope.join();
    }
}
```

Kết quả là `[Ho so, Thong bao]`. Thứ tự này phản ánh thứ tự fork, dù tác vụ thứ hai có thể hoàn tất sớm hơn. Không cần tự lập danh sách handle chỉ để lấy cùng một loại kết quả.

### 6.2. Chấp nhận outcome hỗn hợp

Để quan sát cả kết quả thành công và lỗi, thêm các import sau vào `PageDemo` nếu chưa có:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.StructuredTaskScope.Joiner;
```

Sau đó thêm phương thức:

```java
static void inspectBoth() throws InterruptedException {
    Callable<String> failingTask = () -> {
        throw new IllegalStateException("Khong doc duoc thong bao");
    };

    try (var scope = StructuredTaskScope.open(
            Joiner.<String>allUntil(task -> false))) {
        scope.fork(() -> "Da doc ho so");
        scope.fork(failingTask);

        var tasks = scope.join();

        for (var task : tasks) {
            switch (task.state()) {
                case SUCCESS -> System.out.println(task.get());
                case FAILED -> System.out.println(task.exception().getMessage());
                case UNAVAILABLE -> System.out.println("Khong co outcome");
            }
        }
    }
}
```

Kết quả dự kiến khi gọi `inspectBoth()`:

```text
Da doc ho so
Khong doc duoc thong bao
```

Predicate luôn trả về `false` và ví dụ không cấu hình timeout, nên cả hai công việc được chờ để xử lý. Nhánh `FAILED` là outcome có chủ đích của ví dụ. Nhánh `UNAVAILABLE` giúp biểu đạt rõ cách xử lý nếu sau này thêm điều kiện hủy hoặc timeout.

Từ hai cách triển khai trên, có thể thấy code đọc kết quả phải đi cùng policy: `loadPage` cần đầy đủ dữ liệu, còn `inspectBoth` chủ động chấp nhận kết quả hỗn hợp.

## 7. `join()` và `close()` bảo đảm những điều khác nhau

`join()` có thể kết thúc vì policy đã có outcome, trong khi luồng của tác vụ bị hủy chưa dừng xong. `close()` hủy phần việc còn lại và chờ mọi luồng do scope khởi chạy kết thúc. Vì vậy, thoát khỏi khối `try` là ranh giới về vòng đời luồng, kể cả khi join ném exception. [Oracle: vòng đời và hủy tác vụ](https://docs.oracle.com/en/java/javase/27/core/structured-concurrency.html).

Xét tình huống hai công việc: A báo lỗi, còn B đang dọn tài nguyên sau khi bị interrupt. Policy mặc định đã có thể xác định thất bại từ A; việc rời phương thức vẫn phải đợi B dừng. Đây là lý do xử lý lỗi sớm không đồng nghĩa phương thức trả về tức thì.

Tác vụ con cần hợp tác với interruption. Những thao tác như `Thread.sleep` có thể ném `InterruptedException`; vòng lặp tính toán dài cần kiểm tra trạng thái interrupt phù hợp. Không nuốt tín hiệu rồi tiếp tục công việc vô hạn. [Javadoc: Thread và interruption](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html#interrupt()).

Scope quản lý vòng đời tác vụ; nó không hoàn tác một email đã gửi hay một bản ghi đã commit. Khi dùng tác vụ có tác dụng phụ, ứng dụng vẫn cần thiết kế giao dịch hoặc xử lý bù theo nghiệp vụ.

## 8. Phân biệt lỗi tác vụ, owner bị interrupt và lỗi dùng API

Trong ví dụ mặc định của JDK 27:

| Tình huống | Cách xử lý trong ứng dụng |
| --- | --- |
| Tác vụ con ném lỗi | Xử lý `ExecutionException`, xem `getCause()` |
| Owner bị interrupt khi đang join | Truyền tiếp `InterruptedException`, hoặc khôi phục interrupt nếu bắt lại |
| Gọi `get()` sai thời điểm hoặc sai trạng thái | Sửa thứ tự đồng bộ và logic đọc outcome |

`ExecutionException` bao bọc lỗi từ công việc bất đồng bộ; `getCause()` giúp truy cập nguyên nhân. Không nên ghi nhận nó như thể đó luôn là lỗi tạo luồng hoặc lỗi của chính owner. [Javadoc: ExecutionException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutionException.html).

Ví dụ phương thức ở ranh giới hiển thị, đặt thêm trong `PageDemo`:

```java
static void printPage(long userId) {
    try {
        System.out.println(loadPage(userId));
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        System.err.println("Da dung cho trang nguoi dung");
    } catch (ExecutionException e) {
        System.err.println("Khong tao duoc trang: " + e.getCause());
    }
}
```

`loadPage` đã đóng scope trước khi các nhánh `catch` này chạy. Ví dụ dùng thông báo console để dễ quan sát; ở tầng dịch vụ, có thể chuyển lỗi sang kiểu lỗi nghiệp vụ phù hợp.

Nếu chính tác vụ con ném `InterruptedException`, đó là lỗi của tác vụ dưới góc nhìn policy mặc định. Hãy phân biệt trường hợp này với việc owner bị interrupt trong lúc chờ.

## 9. Timeout là điều kiện hủy, không phải cam kết thời gian trả về

Có thể cấu hình timeout khi mở scope. Thêm import `java.time.Duration`, rồi thêm phương thức sau vào `PageDemo`:

```java
static Page loadPageWithTimeout(long userId)
        throws InterruptedException, ExecutionException {
    try (var scope = StructuredTaskScope.open(
            config -> config.withTimeout(Duration.ofMillis(150)))) {
        Subtask<User> user = scope.fork(() -> findUser(userId));
        Subtask<Integer> unread = scope.fork(() -> countUnread(userId));

        scope.join();
        return new Page(user.get(), unread.get());
    }
}
```

Timeout bắt đầu khi mở scope, bao gồm thời gian chuẩn bị và fork. Hết hạn trước hoặc trong lúc join có thể làm scope bị hủy. [Javadoc: cấu hình scope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html), [Javadoc: mở scope với timeout](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

Trong policy mặc định của JDK 27, timeout khiến join ném `ExecutionException` với `StructuredTaskScope.CancelledByTimeoutException` làm cause. Khi phân loại lỗi, có thể kiểm tra cause này. [Javadoc: CancelledByTimeoutException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.CancelledByTimeoutException.html).

Không lấy `150 ms` làm khẳng định về thời gian tối đa của cả phương thức: `close()` vẫn phải chờ tác vụ kết thúc. Với I/O thực tế, cần cấu hình timeout của thao tác I/O và bảo đảm tác vụ có thể dừng khi bị hủy.

## 10. Hợp đồng sở hữu và thứ tự thao tác

Chỉ owner gọi `fork`, `join`, `close`; tác vụ con cần scope riêng để chia nhỏ công việc. Đã fork thì phải thử join trước khi đóng, và không fork thêm sau join. Join lấy outcome một lần, trừ khi lần trước ném `InterruptedException`.

Sai hợp đồng có thể gây `WrongThreadException` hoặc `IllegalStateException`. Khi thiếu join, close vẫn dọn scope trước khi báo lỗi. Vì vậy, chuỗi `fork A → join → fork B` cần được thiết kế lại. [Javadoc: hợp đồng StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

## 11. Áp dụng hợp đồng vào thiết kế kết quả

Khi triển khai một nhóm tác vụ, hãy quyết định bốn điểm trước khi đọc `get()`:

1. Công việc cha cần tất cả kết quả, một kết quả, hay chấp nhận outcome hỗn hợp?
2. Policy được chọn có thực sự bảo đảm điều kiện đó khi join trả về bình thường?
3. Nếu một handle không ở trạng thái `SUCCESS`, ứng dụng cần xử lý lỗi hay bỏ qua theo nghiệp vụ?
4. Tác vụ còn chạy sẽ dừng và giải phóng tài nguyên bằng cách nào khi scope bị hủy?

Với trang người dùng ở mục 3, cả hồ sơ và số thông báo đều bắt buộc, nên policy mặc định và việc đọc hai `get()` sau join phù hợp với nhau. Nếu thông báo trở thành phần tùy chọn, cần thiết kế lại outcome và cách ghép trang; chỉ bắt lỗi rồi tiếp tục gọi mọi `get()` sẽ không tạo ra dữ liệu thay thế hợp lệ.

Các ví dụ bổ sung là phương thức độc lập để đặt trong `PageDemo`; có thể lần lượt gọi chúng từ `main` để quan sát từng hợp đồng. Khi tích hợp vào ứng dụng thật, giữ kết quả nghiệp vụ làm đầu ra của hàm và giữ scope trong phạm vi điều phối công việc.
