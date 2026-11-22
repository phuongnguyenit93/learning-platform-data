# `finally` và giới thiệu `try-with-resources` trong Java

## 1. Vì sao cần dọn dẹp khi thao tác có thể thất bại?

Một chương trình Java có thể mở tệp, kết nối mạng, sử dụng stream hoặc tài nguyên khác. Các thao tác ấy có thể hoàn tất bình thường, ném ngoại lệ hoặc thoát sớm bằng `return`. Nếu việc dọn dẹp chỉ đặt ở cuối nhánh thành công, một nhánh thất bại có thể bỏ qua nó.

Java cung cấp hai cơ chế liên quan:

- **`finally`**: khối mã có thể được dùng để thực hiện công việc khi rời cấu trúc `try`/`catch`, kể cả khi `try` gặp ngoại lệ hoặc `return`.
- **`try-with-resources`**: dạng `try` chuyên quản lý tài nguyên triển khai `AutoCloseable`; Java tự gọi `close()` khi rời khối, xử lý cả tình huống có ngoại lệ.

Đừng đồng nhất chúng: `finally` là cơ chế tổng quát; `try-with-resources` là lựa chọn nên ưu tiên để **đóng tài nguyên** có API `close()`.

## 2. Cấu trúc và luồng chạy của `finally`

Cú pháp:

```java
try {
    // Thao tác có thể thất bại
} catch (SomeException ex) {
    // Xử lý ngoại lệ phù hợp
} finally {
    // Công việc khi rời try/catch
}
```

Có thể viết `try-finally` không có `catch`:

```java
try {
    doWork();
} finally {
    cleanUp();
}
```

Hai tên `doWork()` và `cleanUp()` ở đoạn trên chỉ là **phương thức minh họa**, không phải chương trình độc lập. Với dạng `try` thông thường (không có khai báo tài nguyên), Java yêu cầu ít nhất một `catch` hoặc `finally`.

### Những đường đi phổ biến

| Điều xảy ra trong `try` | `catch` | `finally` |
| --- | --- | --- |
| Hoàn tất bình thường | Bỏ qua `catch` | Chạy trước khi đi tiếp |
| Ném ngoại lệ được `catch` phù hợp xử lý | Chạy khối `catch` đó | Chạy sau `catch` |
| Ném ngoại lệ không được bắt tại đây | Không có khối phù hợp | Thông thường vẫn chạy trước khi ngoại lệ lan ra ngoài |
| `return`, `break` hoặc `continue` làm rời cấu trúc | Tùy tình huống | Thông thường chạy trước khi thực hiện việc rời khối |

Ví dụ có `return`:

```java
static int calculate() {
    try {
        System.out.println("Trong try");
        return 7;
    } finally {
        System.out.println("Trong finally");
    }
}
```

Khi gọi `calculate()`, chương trình in `Trong try`, sau đó `Trong finally`, rồi mới trả giá trị `7` về nơi gọi. Trong `finally`, ta vẫn có thể dùng biến đang nằm trong scope; tuy nhiên **không nên đổi luồng điều khiển bằng `return` ở `finally`**.

### `finally` không phải bảo đảm tuyệt đối

Trong điều kiện thực thi Java thông thường, `finally` được thực hiện khi rời `try` hoặc `catch`. Nhưng không thể cam kết nó chạy trong **mọi** trường hợp: ví dụ khi tiến trình/JVM bị chấm dứt đột ngột, có lời gọi `System.exit(...)` dẫn tới chấm dứt VM, hoặc luồng không bao giờ rời khỏi đoạn mã đang chạy.

Vì vậy, không nên dùng `finally` để bảo đảm độ bền dữ liệu khi tiến trình có thể mất nguồn điện hay bị kill. Tùy bài toán, cần thiết kế lưu trữ, transaction và cơ chế khôi phục riêng.

## 3. `finally` có thể che mất nguyên nhân lỗi nếu viết sai

Đây là lỗi đáng chú ý:

```java
static int misleading() {
    try {
        return 10;
    } finally {
        return 99; // KHÔNG NÊN: che giá trị return trước
    }
}
```

Dù `try` có `return 10`, kết quả khi gọi `misleading()` lại là `99`. Nếu `try` ném ngoại lệ mà `finally` thực hiện `return`, ngoại lệ ban đầu cũng có thể bị che mất. Tương tự, nếu `finally` ném một ngoại lệ mới, ngoại lệ đó có thể thay thế ngoại lệ đang lan từ `try`.

Khi cần đóng một tài nguyên và cả thao tác chính lẫn `close()` đều có thể thất bại, tự gọi `close()` trong `finally` dễ làm khó việc giữ lại **ngoại lệ gốc**. Đây là một lý do quan trọng để dùng `try-with-resources`.

## 4. `try-with-resources` là gì?

Từ Java 7, có thể khai báo các tài nguyên trong phần ngoặc của `try`:

```java
try (Resource resource = acquireResource()) {
    use(resource);
}
```

Các tên `Resource`, `acquireResource()` và `use(...)` ở đây biểu diễn **mẫu cú pháp**, không phải API có sẵn. Trong mã chạy thực tế, kiểu tài nguyên phải triển khai `java.lang.AutoCloseable` (hoặc interface con phù hợp như `java.io.Closeable`).

Khi rời khối, Java sẽ gọi `close()` trên tài nguyên đã được khởi tạo thành công và không phải `null`, ngay cả khi:

- Khối `try` thực thi thành công.
- Khối `try` ném ngoại lệ.
- Luồng điều khiển dùng `return` hoặc đi ra ngoài khối theo cơ chế bình thường của ngôn ngữ.

Ví dụ với API chuẩn:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class FirstLineReader {
    static String readFirstLine(Path path) throws IOException {
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            return reader.readLine();
        }
    }
}
```

Đây là **lớp minh họa** không có `main`. `BufferedReader` triển khai `Closeable`, nên được tự đóng sau khi đọc, kể cả lúc `readLine()` ném `IOException` hoặc có `return`. Phương thức vẫn khai báo `throws IOException`: tự đóng tài nguyên **không có nghĩa lỗi I/O được tự động xử lý và biến mất**.

Không nên nhầm cơ chế đóng này với Garbage Collector. GC quản lý đối tượng Java có thể thu gom, nhưng thường không phải giải pháp để đóng file, socket hoặc kết nối đúng thời điểm.

## 5. Nhiều tài nguyên: đóng theo thứ tự ngược

Có thể khai báo nhiều tài nguyên, ngăn cách bằng dấu chấm phẩy:

```java
try (First first = new First();
     Second second = new Second()) {
    // Sử dụng cả hai tài nguyên
}
```

Các lớp `First` và `Second` trong ví dụ trên chưa được định nghĩa; đây là cú pháp minh họa. Nếu cả hai tài nguyên được tạo thành công, chúng được **đóng ngược với thứ tự khởi tạo**: `second.close()` trước, `first.close()` sau. Nếu tài nguyên thứ hai khởi tạo thất bại, các tài nguyên đã được tạo trước đó vẫn được đóng theo quy tắc try-with-resources.

Thứ tự này tương tự cách dọn dẹp một ngăn xếp tài nguyên. Nó hữu ích khi tài nguyên tạo sau phụ thuộc tài nguyên tạo trước.

Từ **Java 9**, có thể đưa một biến tài nguyên đã tồn tại vào phần ngoặc nếu đó là biến `final` hoặc *effectively final*:

```java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
```

Đây là đoạn minh họa trong phương thức có thể xử lý/khai báo `IOException` và có các import tương ứng. `reader` không được gán lại sau khi khởi tạo trong trường hợp này. Việc đưa biến vào `try (reader)` không tự tạo bản sao tài nguyên hay một đối tượng reader mới: nó quản lý chính đối tượng đó để đóng khi rời khối.

## 6. Ngoại lệ phát sinh lúc đóng và `getSuppressed()`

`AutoCloseable.close()` **có thể ném ngoại lệ**. Có hai tình huống cần phân biệt.

### Chỉ thao tác đóng thất bại

Nếu thân `try` hoàn thành bình thường nhưng `close()` ném ngoại lệ, ngoại lệ từ việc đóng có thể lan ra ngoài hoặc được bắt bởi `catch` tương ứng.

### Cả thân `try` lẫn thao tác đóng đều thất bại

Java ưu tiên giữ **ngoại lệ chính từ thân `try`** làm ngoại lệ được ném ra. Ngoại lệ xảy ra khi tự động đóng tài nguyên được gắn vào ngoại lệ chính dưới dạng **suppressed exception**, có thể đọc bằng:

```java
Throwable[] otherFailures = ex.getSuppressed();
```

Điều này tránh tình huống ngoại lệ phát sinh khi `close()` vô tình xóa mất nguyên nhân ban đầu. Với nhiều tài nguyên, có thể có nhiều suppressed exceptions; số lượng và thứ tự phụ thuộc những tài nguyên nào thực sự ném lỗi lúc đóng.

Lưu ý: `getSuppressed()` trả về mảng và có thể **rỗng**; không truy cập `getSuppressed()[0]` nếu chưa kiểm tra độ dài. Chương trình ở mục tiếp theo dùng tình huống cố định để biết chắc có một ngoại lệ phụ.

## 7. Ví dụ Java 17+ độc lập: `finally`, thứ tự đóng và suppressed exception

Tạo tệp **`FinallyResourcesDemo.java`**:

```java
public class FinallyResourcesDemo {
    static class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Tracked(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }

        void work() {
            System.out.println("work " + name);
        }

        @Override
        public void close() throws Exception {
            System.out.println("close " + name);
            if (failOnClose) {
                throw new Exception("close failed " + name);
            }
        }
    }

    static int returnWithFinally() {
        try {
            System.out.println("try return");
            return 7;
        } finally {
            System.out.println("finally return");
        }
    }

    static void reverseCloseOrder() throws Exception {
        try (Tracked a = new Tracked("A", false);
             Tracked b = new Tracked("B", false)) {
            System.out.println("work pair");
        }
    }

    static void demonstrateSuppressed() {
        try (Tracked c = new Tracked("C", true)) {
            c.work();
            throw new IllegalStateException("body failed");
        } catch (Exception ex) {
            System.out.println("caught: " + ex.getMessage());
            System.out.println("suppressed: " + ex.getSuppressed().length);
            if (ex.getSuppressed().length > 0) {
                System.out.println("detail: "
                        + ex.getSuppressed()[0].getMessage());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try {
            System.out.println("try normal");
        } finally {
            System.out.println("finally normal");
        }

        System.out.println("result: " + returnWithFinally());
        reverseCloseOrder();
        demonstrateSuppressed();

        try (Tracked d = new Tracked("D", true)) {
            d.work();
        } catch (Exception ex) {
            System.out.println("caught close: " + ex.getMessage());
        }

        System.out.println("done");
    }
}
```

Mở terminal tại thư mục chứa tệp, dùng **JDK 17 trở lên**. Chạy trên PowerShell/CMD (Windows) hoặc bash/zsh (Linux/macOS):

```bash
javac -encoding UTF-8 FinallyResourcesDemo.java
java FinallyResourcesDemo
```

**Stdout chính xác** (lệnh `javac` biên dịch thành công không in thông báo):

```text
try normal
finally normal
try return
finally return
result: 7
open A
open B
work pair
close B
close A
open C
work C
close C
caught: body failed
suppressed: 1
detail: close failed C
open D
work D
close D
caught close: close failed D
done
```

**Giải thích theo trình tự:**

1. `try normal` hoàn tất bình thường nên `finally normal` chạy tiếp.
2. `returnWithFinally()` có `return 7` trong `try`; `finally` in thông báo trước khi `result: 7` xuất hiện ở nơi gọi.
3. Hai tài nguyên `A` và `B` được mở theo thứ tự `A`, `B`, nhưng đóng ngược lại: `B`, `A`.
4. Tài nguyên `C` ném lỗi trong `close()`; đồng thời thân `try` ném `IllegalStateException("body failed")`. Ngoại lệ chính được bắt với thông điệp `body failed`; ngoại lệ `close failed C` được lưu là một suppressed exception.
5. Với tài nguyên `D`, thân `try` bình thường; **chỉ `close()` thất bại**, nên `catch` nhận trực tiếp ngoại lệ `close failed D`.
6. Chương trình vẫn in `done` vì cả hai tình huống thất bại có `catch` xử lý; không có `catch` rỗng hoặc việc bỏ qua lỗi một cách âm thầm.

Với tài nguyên `Tracked`, chữ ký `close() throws Exception` là hợp lệ vì `AutoCloseable.close()` cho phép khai báo `Exception`. Do vậy `reverseCloseOrder()` khai báo `throws Exception`, còn `main` cũng khai báo `throws Exception` để chuyển tiếp nếu có thất bại không được xử lý ở đường đi đó. Trong ví dụ, `A` và `B` không ném lỗi nên stdout đã nêu là xác định.

## 8. `try-with-resources` và `catch`/`finally` có thể kết hợp

Cú pháp hợp lệ:

```java
try (Resource resource = open()) {
    use(resource);
} catch (SomeException ex) {
    report(ex);
} finally {
    finish();
}
```

Đây là sơ đồ minh họa với các tên giả `Resource`, `open`, `use`, `report`, `finish`, không phải chương trình độc lập.

Thứ tự về bản chất là:

1. Khởi tạo các tài nguyên từ trái sang phải.
2. Thực thi phần thân `try`.
3. Tự động đóng tài nguyên đã khởi tạo theo thứ tự ngược.
4. Nếu có ngoại lệ cần xử lý, thực hiện `catch` phù hợp gắn với cấu trúc đó.
5. Thực hiện `finally` nếu có, theo quy tắc ngôn ngữ.

Như vậy, **tài nguyên đã được tự đóng trước khi code trong `catch` và `finally` gắn với `try-with-resources` thực thi**. Nếu muốn dùng tài nguyên để ghi thêm dữ liệu trong `catch`, phải thiết kế lại phạm vi/lifecycle; không thể giả định tài nguyên của `try (...)` vẫn đang mở.

Một `try-with-resources` có thể đứng riêng không cần `catch` hay `finally`. Ngược lại, `try` thông thường (không có resource specification) phải có ít nhất `catch` hoặc `finally`.

## 9. Khi nào nên dùng cơ chế nào?

| Nhu cầu | Cách ưu tiên |
| --- | --- |
| Đọc/ghi file qua `BufferedReader`, `InputStream`, `Writer` | `try-with-resources` vì các tài nguyên hỗ trợ đóng |
| Quản lý `java.sql.Connection`, `Statement`, `ResultSet` | `try-with-resources` nếu cần đóng đúng phạm vi |
| Giải phóng tài nguyên tự định nghĩa có `close()` | Triển khai `AutoCloseable` cẩn thận rồi dùng `try-with-resources` |
| Ghi log/điểm đo sau một nhánh `try`/`catch` | Cân nhắc `finally` hoặc cấu trúc rõ ràng tương đương |
| Cần kiểm tra và xử lý lỗi đầu vào | `catch` đúng loại ngoại lệ; `finally` không thay thế `catch` |
| Cần trả kết quả từ phương thức | Dùng `return` đúng chỗ; không đặt `return` trong `finally` để che đường đi khác |

`AutoCloseable` chỉ cung cấp hợp đồng có phương thức `close()`; nó **không mặc nhiên bảo đảm** tài nguyên an toàn khi chia sẻ giữa nhiều luồng hoặc có thể sử dụng lại sau khi đóng. Những điều đó phụ thuộc API thực tế.

## 10. Lỗi thường gặp và cách tự kiểm tra

1. **Cho rằng `finally` sẽ bắt ngoại lệ.** `finally` chỉ chạy công việc khi rời cấu trúc; muốn xử lý ngoại lệ phải có `catch` phù hợp hoặc cho lan đến tầng khác.
2. **Đặt `return` trong `finally`.** Có thể ghi đè giá trị trả về hoặc che ngoại lệ; tránh cách viết này.
3. **Tự đóng tài nguyên trong `finally` nhưng bỏ qua ngoại lệ ở `close()`.** Có thể mất thông tin lỗi gốc; dùng `try-with-resources` khi được hỗ trợ.
4. **Cho rằng `try-with-resources` tự nuốt `IOException`.** Ngoại lệ vẫn cần bắt hoặc khai báo `throws` thích hợp.
5. **Dùng đối tượng không triển khai `AutoCloseable` trong `try (...)`.** Đây là lỗi biên dịch; cần kiểu tài nguyên hợp lệ.
6. **Đọc `getSuppressed()[0]` mà không kiểm tra độ dài.** Có thể gây `ArrayIndexOutOfBoundsException` nếu không có ngoại lệ phụ.
7. **Giả định đóng tài nguyên theo thứ tự khai báo.** Với nhiều tài nguyên, thứ tự đóng là **ngược lại**.
8. **Dùng tài nguyên đã đóng sau khi rời `try-with-resources`.** Nhiều API sẽ ném ngoại lệ hoặc không còn cho phép thao tác; cần tránh phụ thuộc vào trạng thái đã đóng.
9. **Dựa vào `finally` khi VM bị kill hoặc máy tắt.** Không có bảo đảm dọn dẹp trong các tình huống mất khả năng thực thi Java.
10. **Nhầm tài nguyên hệ điều hành với bộ nhớ Java.** Garbage Collector không phải một cơ chế đóng file/socket đúng thời điểm.

**Ghi nhớ:** `finally` dành cho các bước phải thực hiện khi rời đường thực thi bình thường của `try`/`catch`; `try-with-resources` là công cụ chuyên biệt để đóng `AutoCloseable` an toàn hơn, kể cả khi `try` ném ngoại lệ. Khi cả thao tác chính và `close()` thất bại, xem `getSuppressed()` để không bỏ sót lỗi phụ.