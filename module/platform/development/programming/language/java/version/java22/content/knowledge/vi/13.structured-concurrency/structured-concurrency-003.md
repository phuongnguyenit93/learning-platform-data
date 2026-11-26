# StructuredTaskScope theo API preview của đúng JDK đang dùng

## 1. Học mô hình bền vững, gắn mã nguồn với một phiên bản cụ thể

Một endpoint cần lấy hồ sơ người dùng và số thông báo chưa đọc từ hai nguồn độc lập. Hai lời gọi có thể chạy đồng thời, nhưng đều phục vụ cùng một request. Khi một nhánh bắt buộc thất bại hoặc request bị hủy, ta cần kết thúc các công việc liên quan trước khi rời phạm vi xử lý.

`StructuredTaskScope` biểu diễn nhóm công việc đó thành một phạm vi có vòng đời rõ ràng. Tuy nhiên, khi API còn ở trạng thái **preview**, cùng một tên lớp hoặc phương thức không bảo đảm có cùng chữ ký hay hành vi trên các bản JDK khác nhau.

Trong module Java 22, phần kiến thức còn hữu ích là quan hệ cha–con giữa tác vụ, thời hạn sống của nhóm công việc, chính sách chờ kết quả và cơ chế hủy hợp tác. Java 22 cung cấp Structured Concurrency ở lần preview thứ hai, không phải là lần xuất hiện đầu tiên của tính năng.

**Mốc phiên bản của bài: ngày 25/11/2026.** Java 27 đã phát hành và Structured Concurrency vẫn là preview lần thứ bảy, JEP 533. Các chương trình hoàn chỉnh dưới đây dành cho **JDK 27**, nhằm học cách sử dụng hiện đại. Nếu dự án của bạn dùng JDK 22, 25 hoặc 26, phải đối chiếu API của đúng phiên bản đó; không chép nguyên các ví dụ JDK 27 vào rồi chỉ đổi cờ biên dịch. Xem [ghi chú phát hành JDK 22](https://www.oracle.com/java/technologies/javase/22-relnote-issues.html) và [thông báo phát hành Java 27](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/).

Mục tiêu của bài là giúp bạn chọn đúng tài liệu, cấu hình đúng toolchain và hiểu những gì xảy ra trong chuỗi `open → fork → join → close`.

## 2. Nhận diện đúng thế hệ API

### 2.1. Bảng đối chiếu để tránh trộn các lần preview

| JDK | Dấu hiệu nhận diện API | Ý nghĩa khi đọc ví dụ |
| --- | --- | --- |
| 22 | `StructuredTaskScope<T>` là lớp; có các chính sách như `ShutdownOnFailure` và `ShutdownOnSuccess` | Đây là thiết kế preview ở thời điểm Java 22; không dùng nó làm mẫu API hiện đại cho JDK 27 |
| 25 | `StructuredTaskScope<T, R>` là sealed interface; mở bằng `open`, dùng `Joiner` | Đã chuyển sang mô hình API mới, nhưng vẫn cần đọc chữ ký và ngoại lệ riêng của JDK 25 |
| 26 | Vẫn là `StructuredTaskScope<T, R>`; tiếp tục có thay đổi trong `Joiner`, kết quả gom nhóm và timeout | Một ví dụ có `open` chưa đủ để kết luận nó tương thích với JDK 25 hoặc 27 |
| 27 | `StructuredTaskScope<T, R, R_X extends Throwable>`; kiểu ngoại lệ là một phần của API | Đây là mốc cho toàn bộ chương trình trong bài |

Bảng này giúp nhận diện nguồn mã, không phải hướng dẫn viết mới theo các thiết kế preview cũ. Tham chiếu trực tiếp: [API JDK 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html), [API JDK 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html), [API JDK 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html), [API JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

Ví dụ, với `open()` mặc định, JDK 25–26 sử dụng `StructuredTaskScope.FailedException` để biểu diễn lỗi tác vụ. JDK 27 sử dụng `ExecutionException`, là checked exception. Vì vậy, cả phần `catch` hoặc `throws` cũng cần được xem lại khi chuyển phiên bản. Không chỉ tên phương thức tạo scope thay đổi.

Một số dấu hiệu cần dừng lại để kiểm tra phiên bản:

- Mã dùng constructor hoặc các lớp chính sách của thế hệ API trước, nhưng tài liệu bạn đang đọc dành cho JDK 27.
- `StructuredTaskScope` được khai báo với số tham số kiểu khác tài liệu của JDK đang biên dịch.
- `join()` trả về một kiểu khác với biến nhận kết quả.
- Khối `catch` tham chiếu một ngoại lệ không có trong API đang dùng.
- Một ví dụ tùy biến `Joiner` có phương thức timeout khác với giao diện mà compiler yêu cầu.

### 2.2. Ba tham số kiểu trong JDK 27

Trong JDK 27, có thể đọc dạng tổng quát như sau:

```java
StructuredTaskScope<T, R, R_X>
```

| Tham số | Vai trò |
| --- | --- |
| `T` | Giới hạn kiểu kết quả của các tác vụ con |
| `R` | Kiểu kết quả của `join()` |
| `R_X` | Kiểu ngoại lệ kết quả mà chính sách của scope có thể làm `join()` ném ra |

`InterruptedException` vẫn được khai báo riêng bởi `join()`. Nó không bị thay thế bởi `R_X`.

Trong ví dụ thông thường, dùng `var` tại nơi mở scope giúp giảm khai báo kiểu dài. Bạn vẫn cần hiểu `Joiner` đang chọn để biết `join()` trả gì và có thể ném lỗi nào.

## 3. Compiler, runtime và tài liệu phải cùng phiên bản

### 3.1. Xác định JDK thực sự được sử dụng

Trước khi chạy ví dụ JDK 27, kiểm tra:

```shell
java -version
javac -version
```

Cả hai cần trỏ tới JDK 27. Trong PowerShell, có thể xem đường dẫn chương trình đang được chọn:

```powershell
(Get-Command java).Source
(Get-Command javac).Source
```

JDK của terminal, JDK dự án trong IDE và Java toolchain của công cụ build có thể khác nhau. Việc terminal báo Java 27 chưa chứng minh tiến trình test hoặc ứng dụng do IDE khởi chạy cũng dùng Java 27.

### 3.2. Bật preview ở cả hai giai đoạn

Với file `DashboardDemo.java` ở phần tiếp theo, biên dịch và chạy bằng:

```shell
javac --enable-preview --release 27 -encoding UTF-8 DashboardDemo.java
java --enable-preview DashboardDemo
```

Hoặc chạy trực tiếp file nguồn bằng JDK 27:

```shell
java --enable-preview --source 27 DashboardDemo.java
```

| Cấu hình | Tác dụng |
| --- | --- |
| `--enable-preview` của `javac` | Cho phép biên dịch mã phụ thuộc tính năng preview |
| `--release 27` | Chọn mức ngôn ngữ, API và định dạng class đích theo Java 27 |
| `--enable-preview` của `java` | Cho phép JVM nạp và chạy mã phụ thuộc preview của phiên bản đó |

Bật preview khi biên dịch không tự bật preview cho JVM chạy ứng dụng. Class phụ thuộc preview phải được chạy bằng đúng major release phù hợp, với preview được bật. Không coi việc đổi sang JVM mới hơn là cách chạy nguyên binary preview từ release cũ; hãy biên dịch lại theo API của JDK đích.

Tương tự, một compiler mới không cung cấp chế độ dựng lại tùy ý các API preview cũ chỉ nhờ `--release`. Khi cần làm việc với preview của release nào, hãy chọn toolchain của release đó. Tham khảo [hướng dẫn `javac` JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) và [hướng dẫn `java` JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

## 4. Vòng đời của một scope trong API JDK 27

Một scope có **owner thread**: luồng mở scope. Owner điều phối công việc và chịu trách nhiệm kết thúc phạm vi.

```text
Owner mở scope
    ├── fork tác vụ A ───────────► A thực thi
    ├── fork tác vụ B ───────────► B thực thi
    ├── join: nhận kết quả hoặc lỗi theo chính sách
    ├── xử lý kết quả nếu có
    └── close: bảo đảm các luồng con đã kết thúc
Owner tiếp tục công việc ngoài scope
```

Bốn bước có trách nhiệm khác nhau:

| Bước | Trách nhiệm |
| --- | --- |
| `open(...)` | Tạo scope với chính sách kết quả và cấu hình đã chọn |
| `fork(...)` | Giao một tác vụ con cho scope; trả về một `Subtask` làm handle |
| `join()` | Chờ điều kiện kết quả theo chính sách; trả kết quả hoặc ném ngoại lệ |
| `close()` | Kết thúc scope và đợi các luồng chạy tác vụ con chấm dứt |

Dùng `try`-with-resources để `close()` được gọi khi rời khối, kể cả khi xử lý kết quả ném lỗi. Trong API này, owner là bên gọi `fork`, `join` và `close`; scope không phải một hàng đợi dùng chung để mọi thread gửi công việc vào.

Cấu hình mặc định tạo virtual thread cho tác vụ con. Đây là cách thực thi của scope mặc định, không phải giới hạn số lần gọi dịch vụ ngoài. Nếu một endpoint chỉ được phép mở một số lượng kết nối nhất định, nó vẫn cần cơ chế kiểm soát tương ứng.

## 5. Ví dụ hoàn chỉnh: cần cả hai kết quả

Chương trình `DashboardDemo.java` mô phỏng hai lời gọi I/O độc lập. `Thread.sleep` chỉ biểu diễn thời gian chờ, không phải phép đo hiệu năng.

```java
import java.io.IOException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;

public class DashboardDemo {
    private record User(long id, String name) {}
    private record Dashboard(User user, int unreadMessages) {}

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        boolean failMessages = args.length > 0 && "fail".equals(args[0]);
        Dashboard dashboard = loadDashboard(failMessages);
        System.out.println(dashboard);
    }

    private static Dashboard loadDashboard(boolean failMessages)
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open()) {
            var user = scope.fork(() -> loadUser());
            var messages = scope.fork(() -> loadUnreadMessages(failMessages));

            scope.join();

            return new Dashboard(user.get(), messages.get());
        }
    }

    private static User loadUser() throws InterruptedException {
        Thread.sleep(120);
        return new User(42L, "An");
    }

    private static int loadUnreadMessages(boolean fail)
            throws InterruptedException, IOException {
        Thread.sleep(80);
        if (fail) {
            throw new IOException("message service unavailable");
        }
        return 3;
    }
}
```

Chạy bằng các lệnh ở phần 3. Khi hai tác vụ đều thành công, kết quả dự kiến:

```text
Dashboard[user=User[id=42, name=An], unreadMessages=3]
```

Chạy nhánh có lỗi:

```shell
java --enable-preview DashboardDemo fail
```

Với `open()` mặc định trong JDK 27:

- Nếu mọi tác vụ con thành công, `join()` hoàn tất bình thường và trả `null`; chương trình đọc hai kết quả qua các handle.
- Nếu một tác vụ con thất bại, scope hủy công việc chưa hoàn tất và `join()` ném `ExecutionException`, có nguyên nhân là lỗi tác vụ con.
- `close()` vẫn được thực hiện trước khi `loadDashboard` thực sự trả về hoặc truyền ngoại lệ ra ngoài.

Trong nhánh lỗi của ví dụ, nguyên nhân là `IOException`. Không cần tự thu thập kết quả từng nhánh để quyết định rằng dashboard thiếu dữ liệu bắt buộc. Chính sách mặc định đã thể hiện yêu cầu cần tất cả cùng thành công.

### 5.1. `Subtask.get()` không thay cho bước chờ

Đừng chuyển `get()` lên trước `join()` để chờ từng tác vụ. `Subtask.get()` không phải thao tác chờ như `Future.get()`. Trong cách dùng của owner ở đây, hãy gọi nó sau khi đã join và chỉ khi tác vụ thành công.

| Trạng thái handle | Ý nghĩa khi xử lý kết quả |
| --- | --- |
| `SUCCESS` | Có kết quả thành công để lấy bằng `get()` |
| `FAILED` | Có lỗi để xem bằng `exception()` |
| `UNAVAILABLE` | Không có kết quả thành công hoặc lỗi khả dụng qua handle tại thời điểm xét; có thể liên quan đến tác vụ chưa xong hoặc scope đã hủy |

Gọi `get()` sai thời điểm hoặc trên tác vụ không thành công sẽ ném `IllegalStateException`. Các trạng thái và điều kiện truy cập được quy định trong [API `StructuredTaskScope.Subtask` JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Subtask.html).

Ở ví dụ dashboard, `join()` mặc định hoàn tất bình thường bảo đảm hai nhánh đã thành công, nên owner có thể đọc hai handle ngay sau đó. Không suy rộng bảo đảm này cho mọi `Joiner` tùy biến.

## 6. Chọn `Joiner` theo yêu cầu kết quả

Một `Joiner` quyết định khi nào nhóm công việc đã có kết quả cần thiết, có hủy các nhánh còn lại hay không và `join()` trả về điều gì.

### 6.1. Các lựa chọn thường gặp trong JDK 27

| Yêu cầu | Lựa chọn | Kết quả khi thành công |
| --- | --- | --- |
| Cần tất cả tác vụ thành công, giữ các handle vì kết quả khác kiểu | `open()` mặc định, hoặc `Joiner.awaitAllSuccessfulOrThrow()` | `join()` trả `null`; đọc từng handle sau đó |
| Cần tất cả kết quả cùng kiểu | `Joiner.<T>allSuccessfulOrThrow()` | `join()` trả `List<T>` theo thứ tự fork |
| Chỉ cần một tác vụ thành công | `Joiner.<T>anySuccessfulOrThrow()` | `join()` trả kết quả của một nhánh thành công và hủy các nhánh không còn cần thiết |

Với lựa chọn cần một kết quả, một nhánh thất bại chưa đủ để kết luận cả nhóm thất bại nếu nhánh khác vẫn có thể thành công. Đây cũng không phải chính sách lấy tác vụ kết thúc đầu tiên bất kể thành công hay thất bại.

Tạo một `Joiner` mới cho mỗi scope. Các đối tượng này tham gia theo dõi tiến trình của nhóm công việc; không giữ một instance để chia sẻ cho nhiều request. Chi tiết chính sách và kiểu kết quả nằm trong [API `Joiner` JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Joiner.html).

### 6.2. Ví dụ lấy danh sách và lấy một kết quả thành công

Chương trình `JoinerDemo.java`:

```java
import java.io.IOException;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class JoinerDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        System.out.println(loadAllSections());
        System.out.println(loadFromAnySource());
    }

    private static List<String> loadAllSections()
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String>allSuccessfulOrThrow())) {
            scope.fork(() -> "profile");
            scope.fork(() -> "settings");

            return scope.join();
        }
    }

    private static String loadFromAnySource()
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String>anySuccessfulOrThrow())) {
            scope.fork(() -> {
                throw new IOException("primary unavailable");
            });
            scope.fork(() -> "mirror response");

            return scope.join();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --enable-preview --release 27 -encoding UTF-8 JoinerDemo.java
java --enable-preview JoinerDemo
```

Kết quả dự kiến:

```text
[profile, settings]
mirror response
```

Danh sách đầu tiên theo thứ tự fork, dù thứ tự hoàn thành hai nhánh có thể khác. Ở lần gọi thứ hai, chỉ một nguồn có kết quả thành công, nên kết quả là `mirror response`; lỗi từ nguồn primary không tự làm cả nhóm thất bại.

Nếu nhiều nguồn đều có thể thành công, không viết logic dựa vào giả định một nguồn cụ thể luôn thắng chỉ vì được fork trước. Việc chọn chính sách phải xuất phát từ yêu cầu nghiệp vụ về kết quả chấp nhận được.

## 7. Cấu hình timeout theo API của JDK 27

Cấu hình scope gồm thread factory, tên tùy chọn và timeout tùy chọn. Các phương thức `with...` trả về cấu hình mới. Khi viết lambda cấu hình, cần trả lại cấu hình đã chỉnh, chẳng hạn:

```java
config -> config.withName("dashboard-load")
                .withTimeout(Duration.ofSeconds(2))
```

Timeout bắt đầu khi mở scope. Thời gian làm việc của owner giữa `open` và `join` cũng nằm trong khoảng này. Xem [API `StructuredTaskScope.Configuration`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.Configuration.html).

### 7.1. Phân biệt lỗi nguồn dữ liệu và timeout

Chương trình `TimeoutDemo.java` dùng chính sách cần một kết quả thành công:

```java
import java.time.Duration;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Joiner;

public class TimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        try (var scope = StructuredTaskScope.open(
                Joiner.<String>anySuccessfulOrThrow(),
                config -> config.withName("slow-source")
                        .withTimeout(Duration.ofMillis(100)))) {

            scope.fork(() -> {
                Thread.sleep(2_000);
                return "slow response";
            });

            System.out.println(scope.join());
        } catch (ExecutionException ex) {
            if (ex.getCause()
                    instanceof StructuredTaskScope.CancelledByTimeoutException) {
                System.out.println("request timed out");
            } else {
                throw ex;
            }
        }
    }
}
```

Dùng JDK 27:

```shell
javac --enable-preview --release 27 -encoding UTF-8 TimeoutDemo.java
java --enable-preview TimeoutDemo
```

Khi timeout xảy ra trước lúc tác vụ hoàn tất, nhánh xử lý trong ví dụ in:

```text
request timed out
```

Với `Joiner.anySuccessfulOrThrow()` không truyền hàm tạo ngoại lệ, timeout được biểu diễn bằng `ExecutionException` có cause là `StructuredTaskScope.CancelledByTimeoutException`. Đây là kiểu nguyên nhân cần kiểm tra trong ví dụ JDK 27; không chép nguyên một nhánh bắt timeout từ ví dụ preview trước đó. Xem [API `CancelledByTimeoutException`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.CancelledByTimeoutException.html).

Nếu bạn dùng `Joiner` khác hoặc truyền một hàm tạo ngoại lệ tùy chỉnh, phải đọc lại hợp đồng kết quả và timeout của chính sách đó. Không phải mọi `Joiner` đều ném cùng một ngoại lệ trong mọi tình huống timeout.

### 7.2. Timeout không phải thời hạn cưỡng chế dừng mọi mã

Scope hủy công việc chưa hoàn tất bằng cách ngắt các luồng đang chạy tác vụ con. Tác vụ cần hợp tác với tín hiệu đó. Trong ví dụ, `Thread.sleep` có thể kết thúc bằng `InterruptedException`, giúp nhánh con thoát sớm.

Nếu một thư viện bỏ qua interrupt hoặc chặn ở thao tác không có khả năng ngắt phù hợp, `close()` vẫn phải đợi. Vì vậy, timeout 100 ms không bảo đảm toàn bộ phương thức đã trả về trong 100 ms. Để có hành vi thực tế phù hợp, cần phối hợp timeout của scope với timeout và khả năng hủy của thao tác I/O đang dùng.

Tương tự, trong chính sách lấy một nguồn thành công, `join()` có thể đã có kết quả trong khi một nhánh khác đang kết thúc sau khi nhận tín hiệu hủy. Khối `try` chỉ được rời hoàn toàn sau bước đóng scope.

## 8. Trách nhiệm của owner và tác vụ con

### 8.1. Owner điều phối một lần xử lý có ranh giới rõ

Với API JDK 27 trong bài:

1. Owner mở scope và fork các nhánh thuộc lần xử lý đó.
2. Owner join để nhận kết quả theo chính sách.
3. Owner tổng hợp dữ liệu hoặc xử lý lỗi.
4. Scope được đóng khi rời `try`.

Không fork thêm công việc sau khi đã join và không tái sử dụng scope đã đóng. Nếu một tác vụ con cần chia nhỏ công việc của chính nó, nó có thể mở một scope riêng cho các nhánh của nó, tạo thành quan hệ lồng nhau.

Đừng trả một `Subtask` ra ngoài với kỳ vọng một bên khác sẽ tiếp tục dùng scope như cơ chế lập lịch nền. Giá trị trả về hữu ích thường là dữ liệu đã tổng hợp, chẳng hạn `Dashboard`, một `List<String>` hoặc kết quả nguồn dữ liệu đã chọn.

### 8.2. Tác vụ con phải thoát được khi bị hủy

Một tác vụ chờ I/O nên dùng API có hợp đồng timeout hoặc hủy phù hợp. Khi `InterruptedException` có thể truyền lên, khai báo `throws` là cách rõ ràng để tác vụ kết thúc thay vì bỏ qua tín hiệu.

Với xử lý CPU theo vòng lặp dài, có thể kiểm tra interrupt tại các điểm hợp lý và kết thúc sớm. Ví dụ sau minh họa một phương thức có thể dùng làm tác vụ con:

```java
private static long computeTotal(int limit) throws InterruptedException {
    long total = 0;
    for (int i = 0; i < limit; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("computation cancelled");
        }
        total += i;
    }
    return total;
}
```

Không bắt `InterruptedException` rồi tiếp tục vòng lặp như chưa có gì xảy ra. Nếu ở một ranh giới không thể truyền ngoại lệ này lên, cần tuân theo hợp đồng của tầng đó, thường gồm khôi phục cờ interrupt và kết thúc xử lý. Hành vi interrupt phụ thuộc thao tác đang thực thi; tham khảo [API `Thread` JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html).

Hủy tác vụ cũng không hoàn tác các tác dụng phụ đã thực hiện. Nếu hai nhánh ghi dữ liệu hoặc gửi yêu cầu tới hệ thống ngoài, yêu cầu về tính nhất quán vẫn cần được thiết kế riêng.

### 8.3. Một scope gắn với một ngữ cảnh gọi

Khi kết hợp với `ScopedValue`, scope ghi nhận ràng buộc tại thời điểm mở để các tác vụ con kế thừa. Đặt scope bên trong phạm vi ngữ cảnh của request và đóng scope trước khi rời phạm vi đó. Không đổi ràng buộc ở owner giữa lúc mở scope và fork rồi giả định các tác vụ con sẽ tùy ý nhận ngữ cảnh mới.

Phạm vi sống của nhóm tác vụ là cơ sở để dữ liệu ngữ cảnh không hết hiệu lực trong khi các nhánh con vẫn chạy. Với dự án dùng cơ chế truyền ngữ cảnh của framework, cần đối chiếu thêm hợp đồng tích hợp của framework đó.

## 9. Đưa vào IDE và hệ thống build

Để chạy đúng mã JDK 27, các tầng sau cần thống nhất:

| Tầng | Điều cần cấu hình |
| --- | --- |
| JDK dự án | Java 27 |
| Compiler hoặc Java toolchain của build | JDK 27, release/source tương ứng và bật preview |
| JVM chạy ứng dụng | Java 27 với `--enable-preview` |
| JVM chạy test có nạp mã phụ thuộc preview | Java 27 với `--enable-preview` |
| IDE language level | Java 27 và hỗ trợ preview phù hợp |
| CI hoặc môi trường chạy ứng dụng | Cùng major release và cờ runtime cần thiết |

Cấu hình compiler trong Maven hoặc Gradle và cấu hình JVM chạy test là hai phần khác nhau. IDE có thể dùng cấu hình riêng khi chạy trực tiếp một lớp; cần kiểm tra run configuration nếu lệnh terminal chạy được nhưng nút Run trong IDE báo lỗi.

`StructuredTaskScope` trong các ví dụ nằm trong `java.util.concurrent`, thuộc `java.base`. Không cần tìm một thư viện Maven để import lớp này. Nếu tên lớp không được nhận diện, trước hết kiểm tra JDK thực sự dùng để biên dịch và phiên bản API.

Khi thay đổi major release của JDK, hãy cập nhật toolchain, đối chiếu chữ ký API, chỉnh kiểu kết quả và xử lý ngoại lệ, rồi biên dịch lại toàn bộ phần mã phụ thuộc preview. Đổi riêng một số phiên bản trong lệnh chạy không thay thế các bước đó.

## 10. Đọc lỗi để xác định đúng nguyên nhân

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Compiler báo preview API bị vô hiệu hóa | Chưa bật preview ở bước compile | Bật `--enable-preview` cùng mức source/release đúng JDK |
| JVM báo chưa bật preview hoặc không chấp nhận class preview | Thiếu cờ runtime hoặc binary thuộc release khác | Dùng runtime đúng major release, bật preview và biên dịch lại khi cần |
| Không tìm thấy `open`, lớp chính sách hoặc kiểu ngoại lệ | Đang trộn tài liệu và JDK khác thế hệ API | Mở API reference có số phiên bản trùng toolchain |
| Sai số tham số kiểu của `StructuredTaskScope` | Khai báo lấy từ lần preview khác | Kiểm tra chữ ký của đúng JDK; có thể dùng `var` tại nơi mở scope |
| Không gán được kết quả `join()` | `Joiner` cho kiểu kết quả khác giả định | Xem kiểu `R` của chính sách đang chọn |
| `get()` ném `IllegalStateException` | Chưa join hoặc tác vụ không có kết quả thành công | Chờ đúng chỗ và chỉ đọc kết quả theo hợp đồng của chính sách |
| `WrongThreadException` | Gọi thao tác điều phối từ thread không phải owner | Giữ việc fork, join và close ở owner |
| Có timeout nhưng phương thức vẫn chưa thoát | Tác vụ con chưa kết thúc, `close()` còn đợi | Kiểm tra khả năng phản hồi interrupt và timeout I/O |
| Test lỗi nhưng ứng dụng chạy được | Tiến trình test có JDK hoặc cờ runtime khác | Kiểm tra Java toolchain và JVM của test |

Tên thông báo chi tiết có thể khác theo công cụ. Điều cần làm là phân biệt lỗi **cấu hình preview**, lỗi **không tương thích API**, và lỗi **vòng đời tác vụ**; mỗi nhóm có cách sửa khác nhau.

Khi áp dụng vào một request thật, hãy viết rõ chính sách trước khi chọn `Joiner`: cần tất cả nhánh hay chỉ một nhánh thành công, kết quả trả về là gì, lỗi nào được truyền ra và các tác vụ sẽ phản ứng thế nào khi bị hủy. Sau đó gắn phần triển khai với tài liệu của đúng JDK mà dự án đang dùng.
