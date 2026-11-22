# `return` trong `finally` hoặc lỗi cleanup che lỗi chính

Trong Java, `finally` thường được dùng để dọn dẹp tài nguyên. Nhưng một `return`, `throw` hoặc một lời gọi `close()` ném ngoại lệ từ bên trong `finally` có thể **thay đổi hoàn toàn kết quả mà khối `try` hoặc `catch` đang chuẩn bị trả về**. Đặc biệt nguy hiểm là tình huống thao tác nghiệp vụ đã ném một ngoại lệ có giá trị chẩn đoán, nhưng thao tác cleanup lại thất bại và **che khuất lỗi nghiệp vụ ban đầu**.

Bài thuộc **Java Core – Exception / Sai lầm thường gặp**, minh họa trên **Java 17+**. Sau khi học, bạn cần trả lời được: `finally` chạy vào thời điểm nào, tại sao `return` trong `finally` có thể nuốt lỗi, exception nào được truyền ra khi cả `try` và `finally` đều ném, cách `try-with-resources` bảo toàn lỗi qua `Suppressed`, và cách tổ chức cleanup mà không mất nguyên nhân.

## 1. Tóm tắt nguyên tắc quan trọng nhất

**Không đặt `return` vào `finally`. Không để lỗi cleanup vô tình thay thế lỗi chính mà không có chính sách rõ ràng.** Ưu tiên:

- `try-with-resources` cho tài nguyên triển khai `AutoCloseable`, vì Java có cơ chế giữ ngoại lệ phụ bằng `addSuppressed`.
- `finally` chỉ thực hiện dọn dẹp cần thiết, **không `return` hoặc cố tình thay đổi kết quả** của `try`/`catch`.
- Nếu bắt buộc cleanup thủ công có thể ném lỗi, hãy quyết định cách **giữ primary exception** và **báo cáo cleanup failure**, thay vì để lỗi nào xảy ra cuối cùng mặc nhiên thắng.
- Giữ `cause` khi bọc exception giữa các tầng; giữ `suppressed` khi có nhiều thất bại độc lập trong quá trình dọn dẹp.

Một bảng ngắn về ý nghĩa:

| Kết quả của `try`/`catch` | Điều xảy ra trong `finally` | Điều caller quan sát |
|---|---|---|
| Hoàn thành bình thường | `finally` hoàn thành bình thường | Kết quả bình thường |
| Đang chuẩn bị `return x` | `finally` hoàn thành bình thường | Trả về `x` |
| Đang chuẩn bị `return x` | `finally` thực hiện `return y` | Trả về **`y`**, thay `x` |
| Đang chuẩn bị ném lỗi A | `finally` hoàn thành bình thường | Lỗi **A** tiếp tục được ném |
| Đang chuẩn bị ném lỗi A | `finally` ném lỗi B | Lỗi **B** được truyền ra; A **không tự được giữ** dưới `Suppressed` trong `try-finally` thường |
| Đang chuẩn bị `return x` | `finally` ném lỗi B | Caller nhận lỗi **B**, không nhận `x` |

Quy tắc kỹ thuật đằng sau: nếu `finally` **hoàn thành bình thường**, lý do hoàn thành đang chờ từ `try` hoặc `catch` được tiếp tục. Nếu `finally` **hoàn thành đột ngột** (chẳng hạn `return` hoặc `throw`), lý do hoàn thành mới của `finally` **thay thế** lý do trước.

## 2. `finally` thực sự chạy khi nào?

Trong cấu trúc:

```java
try {
    performWork();
} catch (Exception e) {
    handle(e);
} finally {
    cleanup();
}
```

`finally` thông thường chạy sau khi phần `try`/`catch` kết thúc, kể cả khi có `return` hoặc exception đang được truyền đi. Đoạn trên **chỉ là ví dụ trong một phương thức**: `performWork()`, `handle(...)` và `cleanup()` là các hàm do ứng dụng định nghĩa.

Tuy nhiên, không được khẳng định `finally` **luôn luôn** được thực thi bất kể điều kiện nào. Các tình huống như JVM dừng/`Runtime.halt`, tiến trình bị hệ điều hành kết thúc, hoặc luồng không bao giờ thoát khỏi đoạn mã đang chạy có thể khiến cleanup không được thực hiện. `finally` bảo đảm theo **điều khiển thực thi Java bình thường**, không phải cơ chế phục hồi an toàn tuyệt đối trước mọi loại sự cố.

Điểm cần nhớ: `finally` không chỉ dành cho luồng **thành công**; nó còn chạy khi đang `throw` hoặc đang chuẩn bị `return`. Do đó mọi điều khiển luồng bên trong nó phải được viết rất cẩn thận.

## 3. Vì sao `return` trong `finally` ghi đè `return` của `try`?

Xem phương thức:

```java
static int calculate() {
    try {
        return 10;
    } finally {
        return 20;
    }
}
```

Java đã đánh giá `10` và đang chuẩn bị trả về. Trước khi phương thức kết thúc, khối `finally` phải chạy; lệnh `return 20` tạo ra một **kết quả trả về mới**. Giá trị cuối mà caller nhận là **20**, không phải 10.

Một trường hợp còn nguy hiểm hơn:

```java
static String hideFailure() {
    try {
        throw new IllegalStateException("primary failure");
    } finally {
        return "success";
    }
}
```

Ngoại lệ `IllegalStateException` bị **nuốt**: caller nhận chuỗi `"success"` thay vì lỗi. Không có `catch` nào phục hồi nghiệp vụ ở đây; chỉ có một lệnh `return` sai vị trí đã vô tình xóa tín hiệu thất bại.

### Ví dụ Java 17 độc lập: hai kiểu ghi đè

Tạo tệp `FinallyReturnDemo.java`:

```java
public class FinallyReturnDemo {
    static int overrideValue() {
        try {
            System.out.println("try: return 10");
            return 10;
        } finally {
            System.out.println("finally: return 20");
            return 20;
        }
    }

    static String swallowException() {
        try {
            throw new IllegalStateException("business failed");
        } finally {
            return "apparently successful";
        }
    }

    public static void main(String[] args) {
        System.out.println("result = " + overrideValue());
        System.out.println("result after error = " + swallowException());
    }
}
```

Biên dịch/chạy:

```bash
javac FinallyReturnDemo.java
java FinallyReturnDemo
```

Kết quả chuẩn:

```text
try: return 10
finally: return 20
result = 20
result after error = apparently successful
```

Ví dụ cố ý chứa **anti-pattern** để chứng minh hành vi ngôn ngữ. Trong production, không dùng hai mẫu này. Khi bật cảnh báo của trình biên dịch bằng `javac -Xlint:finally FinallyReturnDemo.java`, công cụ có thể cảnh báo rằng `finally` không hoàn thành bình thường; nên coi cảnh báo này là dấu hiệu code cần sửa.

Tác hại thực tế: một request có thể ghi trạng thái “thành công” dù logic tạo đơn hàng đã thất bại; một tác vụ batch có thể trả kết quả mặc định dù đã mất dữ liệu; hoặc exception không được ghi nhận bởi hệ thống giám sát vì caller không thấy nó.

## 4. `return` trong `try`, cleanup trong `finally` đúng cách

Không phải `return` trong `try` là sai. Mẫu sau hoàn toàn hợp lý nếu cleanup không thay đổi kết quả:

```java
static int readValue() {
    try {
        return 10;
    } finally {
        System.out.println("cleanup");
    }
}
```

Caller nhận `10`, và `"cleanup"` được in trước khi phương thức trả về. `finally` ở đây **hoàn thành bình thường**, nên không ghi đè `return`.

Chương trình độc lập `SafeFinallyReturnDemo.java`:

```java
public class SafeFinallyReturnDemo {
    static int read() {
        try {
            System.out.println("work");
            return 7;
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        int result = read();
        System.out.println("result = " + result);
    }
}
```

Chạy:

```bash
javac SafeFinallyReturnDemo.java
java SafeFinallyReturnDemo
```

Output:

```text
work
cleanup
result = 7
```

**Phân biệt quan trọng:** biểu thức sau `return` trong `try` được đánh giá **trước** khi chạy `finally`. Nếu trả tham chiếu tới một đối tượng mutable và `finally` **thay đổi chính đối tượng đó**, caller có thể thấy trạng thái đã thay đổi; đó là hiệu ứng mutation, **không phải lệnh `return` trong `finally` ghi đè giá trị**.

Ví dụ minh họa:

```java
static java.util.List<String> createList() {
    java.util.List<String> list = new java.util.ArrayList<>();
    try {
        list.add("work");
        return list;
    } finally {
        list.add("cleanup");
    }
}
```

Khi caller nhận danh sách, nó chứa `"work"` và `"cleanup"`; cùng một object được trả về. Mẫu này vẫn có thể gây bất ngờ nếu cleanup chỉnh sửa đối tượng trả về. Tốt nhất tách rõ trạng thái kết quả khỏi logic dọn dẹp.

## 5. Exception từ `finally` có thể che exception chính

Giả sử operation gặp lỗi trước:

```java
try {
    throw new IllegalArgumentException("invalid input");
} finally {
    throw new IllegalStateException("close failed");
}
```

Java sẽ truyền **`IllegalStateException("close failed")`** ra caller. `IllegalArgumentException("invalid input")` bị thay thế theo quy tắc điều khiển luồng. Với `try-finally` thủ công ở trên, Java **không tự động** thêm lỗi đầu tiên vào `getSuppressed()` của lỗi thứ hai.

Đó là lý do một log có thể chỉ hiện:

```text
java.lang.IllegalStateException: close failed
```

trong khi thật ra validation đã thất bại trước. Người điều tra có thể tốn thời gian sửa nhánh cleanup mà không biết thông tin lỗi ban đầu đã mất.

### Ví dụ Java 17 độc lập: lỗi thứ hai che lỗi đầu

Tệp `CleanupMasksPrimaryDemo.java`:

```java
public class CleanupMasksPrimaryDemo {
    static void doWork() {
        try {
            throw new IllegalArgumentException("primary: bad request");
        } finally {
            throw new IllegalStateException("cleanup: close failed");
        }
    }

    public static void main(String[] args) {
        try {
            doWork();
        } catch (RuntimeException e) {
            System.out.println("observed = "
                    + e.getClass().getSimpleName());
            System.out.println("message = " + e.getMessage());
            System.out.println("cause = " + e.getCause());
            System.out.println("suppressed count = "
                    + e.getSuppressed().length);
        }
    }
}
```

Chạy:

```bash
javac CleanupMasksPrimaryDemo.java
java CleanupMasksPrimaryDemo
```

Kết quả:

```text
observed = IllegalStateException
message = cleanup: close failed
cause = null
suppressed count = 0
```

Vì mã này **không hề nối hai exception** bằng constructor cause hay `addSuppressed`, caller không thể lấy lại `IllegalArgumentException` qua exception đã nhận. Đây không phải do logging framework cắt stack; đây là sự mất thông tin ở **logic xử lý exception**.

Sai lầm này không chỉ xảy ra khi viết `throw` trực tiếp trong `finally`. Một phương thức `close()`, `rollback()`, `flush()` hoặc `release()` được gọi tại đó có thể ném checked/unchecked exception và **ghi đè lỗi đang được truyền**, nếu không có cơ chế bảo toàn phù hợp.

## 6. Quy tắc quyết định exception nào thắng

Khái niệm “completion reason” giúp đọc những đường đi phức tạp:

1. `try` có thể hoàn thành bình thường, `return`, `break`, `continue` hoặc `throw`.
2. `catch` nếu khớp có thể thay đổi cách xử lý lỗi.
3. `finally` chạy trước khi phương thức rời cấu trúc.
4. Nếu `finally` hoàn thành bình thường, lý do hoàn thành từ `try`/`catch` được giữ.
5. Nếu `finally` hoàn thành đột ngột, lý do mới **chiếm ưu thế** so với lý do đang chờ.

Ví dụ nguy hiểm:

```java
static boolean work() {
    try {
        throw new IllegalStateException("failure");
    } catch (IllegalStateException e) {
        throw e;
    } finally {
        return true;
    }
}
```

Đây là **phương thức minh họa**, không nên dùng. Kể cả `catch` đã `throw e`, `finally` vẫn trả `true` và **hủy ngoại lệ đang được ném lại**.

Tương tự:

```java
static int read() {
    try {
        return 42;
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

Caller nhận exception, **không nhận số 42**.

**Kết luận:** đừng tin rằng `return`/`throw` ở đoạn trước luôn là kết quả cuối. Phải kiểm tra xem `finally` có thể thực hiện điều khiển luồng cạnh tranh hoặc ném lỗi không.

## 7. Tại sao `try-with-resources` thường là giải pháp tốt nhất?

Với tài nguyên `AutoCloseable`, Java có cú pháp:

```java
try (Resource resource = open()) {
    doWork(resource);
}
```

Đây là mảnh minh họa cần kiểu `Resource` và hai phương thức tương ứng. Java đóng resource khi ra khỏi phạm vi. Nếu thân `try` ném lỗi A và `close()` ném B, **A vẫn là primary**, B nằm trong `A.getSuppressed()`. Nếu chỉ đóng lỗi, B trở thành primary. Nhiều tài nguyên được đóng **ngược thứ tự khai báo**.

Điểm cần phân biệt với `finally` thủ công: một `throw` hoặc `return` trong `finally` có thể **thay** lỗi/kết quả đang chờ. Bài về *đóng tài nguyên thủ công thiếu nhánh thất bại* đi sâu vào open lỗi giữa chừng, close nhiều nguồn, ownership và kiểm thử mọi đường dọn dẹp.

## 8. Ví dụ Java 17 độc lập: primary và suppressed khi đóng hai tài nguyên

Tạo tệp `SuppressedOnCloseDemo.java`:

```java
import java.io.IOException;

public class SuppressedOnCloseDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("close " + name);
        }
    }

    static void work() throws Exception {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {
            throw new IllegalArgumentException("body failed");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (Exception e) {
            System.out.println("primary = "
                    + e.getClass().getSimpleName()
                    + ": " + e.getMessage());

            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed = "
                        + suppressed.getClass().getSimpleName()
                        + ": " + suppressed.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac SuppressedOnCloseDemo.java
java SuppressedOnCloseDemo
```

Output:

```text
primary = IllegalArgumentException: body failed
suppressed = IOException: close second
suppressed = IOException: close first
```

Đọc hành vi:

1. Thân `try` ném `IllegalArgumentException("body failed")`; đây là **primary exception**.
2. Java đóng `second` trước `first`.
3. Hai lần `close()` ném `IOException`.
4. Thay vì làm mất lỗi thân `try`, Java gắn cả hai lỗi `close()` vào **mảng suppressed** của primary.
5. Caller nhận lại primary và có thể xem các lỗi cleanup qua `e.getSuppressed()`.

Trong log do `printStackTrace()` tạo, bạn sẽ thấy nhánh thụt vào `Suppressed:` bên dưới exception chính. Điều đó không có nghĩa close error không quan trọng; nó chỉ thể hiện **vai trò phụ trong luồng thất bại cụ thể**.

### Khi thân `try` thành công nhưng `close()` thất bại

Tệp `CloseAsPrimaryDemo.java`:

```java
import java.io.IOException;

public class CloseAsPrimaryDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("close " + name);
        }
    }

    static void work() throws Exception {
        try (Resource first = new Resource("first");
             Resource second = new Resource("second")) {
            System.out.println("body: success");
        }
    }

    public static void main(String[] args) {
        try {
            work();
        } catch (Exception e) {
            System.out.println("primary = " + e.getMessage());
            for (Throwable extra : e.getSuppressed()) {
                System.out.println("suppressed = " + extra.getMessage());
            }
        }
    }
}
```

Chạy:

```bash
javac CloseAsPrimaryDemo.java
java CloseAsPrimaryDemo
```

Output:

```text
body: success
primary = close second
suppressed = close first
```

Vì không có lỗi ở thân `try`, lần đóng đầu tiên theo **thứ tự đóng ngược** (`second`) tạo primary exception. Lỗi đóng `first` trở thành suppressed của primary đó.

Không được diễn giải “primary” là “lỗi nghiệp vụ” trong mọi trường hợp. **Primary là exception được ưu tiên truyền ra theo quy tắc cấu trúc đang thực thi**. Nếu thân `try` hoàn thành, một lỗi đóng tài nguyên có thể là chính lỗi cần xử lý.

## 9. `Caused by` và `Suppressed` khác nhau như thế nào?

Dễ nhầm hai thành phần này khi đọc stack trace:

| Cơ chế | API | Ý nghĩa |
|---|---|---|
| **Cause** | `getCause()`, constructor nhận `Throwable cause` | Ngoại lệ trước đó làm phát sinh ngoại lệ đang xét, thường trong một chuỗi bọc ngữ cảnh |
| **Suppressed** | `getSuppressed()`, `addSuppressed(...)` | Lỗi bổ sung được giữ lại khi đang xử lý lỗi khác, ví dụ đóng tài nguyên sau khi thân try đã lỗi |

Một exception có thể có **một cause** và **nhiều suppressed**. Khi `try-with-resources` thấy body failure A và close failure B, B thường được đưa vào **suppressed của A**, không phải **cause của A**; cleanup B không gây ra việc body A lỗi trước đó.

Ví dụ stack trace (đường dẫn/số dòng là **minh họa**, không phải output cam kết của chương trình ở trên):

```text
java.lang.IllegalStateException: Không thể ghi báo cáo
    at app.ReportService.generate(ReportService.java:50)
    Suppressed: java.io.IOException: Không đóng được stream
        at app.ReportWriter.close(ReportWriter.java:18)
        ... 1 more
Caused by: java.io.IOException: Không ghi được dữ liệu
    at app.ReportWriter.write(ReportWriter.java:12)
    ... 1 more
```

Cách đọc đúng:

- Ngoại lệ ngoài cùng mô tả thao tác thất bại.
- `Caused by` nói về nguyên nhân đã được bọc lại.
- `Suppressed` ghi lỗi xảy ra bổ sung trong khi dọn dẹp.
- `... 1 more` là số stack frame trùng ở cuối được rút gọn so với nhánh bao ngoài; **không phải** một exception nữa.

Nếu `finally` thường ném exception mới và làm mất lỗi đầu, stack trace của caller có thể **không còn thông tin về lỗi đã bị thay thế**. Lúc ấy không thể mong `Caused by` hoặc `Suppressed` tự xuất hiện nếu mã chưa hề thiết lập chúng.

## 10. Cleanup thủ công: phải bảo toàn lỗi chính bằng chính sách tường minh

Không phải mọi tài nguyên đều triển khai `AutoCloseable`, và đôi khi cleanup có yêu cầu đặc biệt. Nếu phải dùng `finally` thủ công, đừng để lỗi cleanup tự động ghi đè lỗi trước.

Mẫu ý tưởng:

```text
Thực thi công việc
    |
    +-- thành công --------------------+
    |                                 |
    +-- thất bại: lưu primary         |
                                      v
                                  Chạy cleanup
                                      |
                         +------------+------------+
                         |                         |
                    cleanup OK                cleanup lỗi
                         |                         |
                 truyền kết quả/lỗi cũ    nếu đã có primary:
                                          gắn cleanup thành suppressed
                                         nếu chưa có primary:
                                          truyền cleanup failure
```

Ví dụ Java 17 độc lập áp dụng cho một loại checked exception cụ thể. Tệp `ManualCleanupPreserveDemo.java`:

```java
import java.io.IOException;

public class ManualCleanupPreserveDemo {
    static void work() throws IOException {
        throw new IOException("write failed");
    }

    static void cleanup() throws IOException {
        throw new IOException("close failed");
    }

    static void run() throws IOException {
        IOException primary = null;

        try {
            work();
        } catch (IOException e) {
            primary = e;
            throw e;
        } finally {
            try {
                cleanup();
            } catch (IOException closeError) {
                if (primary != null) {
                    primary.addSuppressed(closeError);
                } else {
                    throw closeError;
                }
            }
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IOException e) {
            System.out.println("primary = " + e.getMessage());

            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println(
                        "suppressed = " + suppressed.getMessage());
            }
        }
    }
}
```

Lệnh:

```bash
javac ManualCleanupPreserveDemo.java
java ManualCleanupPreserveDemo
```

Kết quả:

```text
primary = write failed
suppressed = close failed
```

Mã giữ nguyên `IOException("write failed")` để truyền ra caller, đồng thời gắn lỗi đóng tài nguyên vào `getSuppressed()`. Nếu `work()` thành công mà `cleanup()` thất bại, nhánh `primary == null` sẽ ném lỗi cleanup như lỗi chính.

**Giới hạn quan trọng:** ví dụ này chỉ bắt **`IOException`** theo hợp đồng của `work()` và `cleanup()`. Nếu một `RuntimeException` hoặc `Error` khác xuất hiện trong `work()`, rồi `cleanup()` ném `IOException`, đoạn `finally` có thể che exception không thuộc loại đã lưu. Muốn xử lý toàn diện mọi `Throwable` thủ công sẽ phức tạp, cần xem xét `Error`, suppression bị vô hiệu hóa, self-suppression và chính sách hủy. Vì vậy **ưu tiên `try-with-resources`** khi có thể, thay vì sao chép một pattern hẹp cho mọi nơi.

Nếu cleanup có nhiều bước, cân nhắc mỗi bước ném exception thế nào và tránh để bước đầu lỗi làm bỏ qua toàn bộ các bước khác khi việc dọn dẹp tiếp tục là bắt buộc.

## 11. Gọi `close()` trong `finally` có thể làm mất thông tin như thế nào?

Mẫu cổ điển:

```java
Resource resource = acquire();

try {
    use(resource);
} finally {
    resource.close();
}
```

Đây là **mảnh mã minh họa**, giả định `Resource`, `acquire`, `use` và `close` đã tồn tại. Nếu `use` ném lỗi A và `close` ném lỗi B, **B có thể thay thế A**, vì `finally` hoàn thành bằng `throw B`. Cấu trúc thường **không tự tạo suppressed exceptions**.

Còn nếu `resource` là `AutoCloseable`, hãy dùng:

```java
try (Resource resource = acquire()) {
    use(resource);
}
```

Compiler tạo logic dọn tài nguyên và suppression theo hợp đồng của `try-with-resources`. Điều này vừa ngắn hơn, vừa giảm nguy cơ rơi mất primary error.

Một số vấn đề khác với cleanup thủ công:

- `resource` có thể chưa khởi tạo xong, dẫn tới `NullPointerException` trong `finally` nếu không kiểm tra.
- Nếu tài nguyên được mở **ngoài** `try`, lỗi trước khi vào `try` có thể khiến `finally` không chạy.
- Có thể có nhiều tài nguyên cần đóng **theo thứ tự ngược** với thứ tự mở.
- Thao tác close không nhất thiết idempotent; đóng hai lần có thể gây tác dụng phụ hoặc lỗi khác.
- Cleanup cần tránh gọi dịch vụ ngoài quá lâu, vì khi gặp lỗi chính hệ thống có thể đã quá tải.

`try-with-resources` xử lý tốt các vấn đề quản lý tài nguyên theo hợp đồng Java, nhưng **không tự bảo đảm** một `close()` luôn thành công hoặc mọi tác động nghiệp vụ đã được rollback.

## 12. Phân biệt resource cleanup, transaction rollback và khôi phục nghiệp vụ

Có những thao tác được gọi trong `finally` không chỉ là `close()`:

```java
try {
    updateDatabase();
} finally {
    rollbackIfNeeded();
}
```

Đây là mảnh minh họa. Nếu `updateDatabase()` ném một lỗi và `rollbackIfNeeded()` cũng ném, nguyên nhân đầu **có thể bị che**. Nhưng bỏ qua hoàn toàn lỗi rollback cũng có thể nguy hiểm: transaction hoặc kết nối có thể ở trạng thái không xác định.

Cách xử lý đúng tùy hợp đồng của transaction manager và thư viện:

- Giữ nguyên nhân tạo ra failure đầu tiên khi đó là thông tin quan trọng.
- Gắn hoặc ghi nhận lỗi cleanup/rollback bổ sung, phân biệt rõ hậu quả của nó.
- Nếu rollback failure có mức độ nghiêm trọng hơn, có thể cần **một policy lỗi tổng hợp**. Quyết định đó phải được tường minh, không phải tác dụng phụ vô tình của `finally`.
- Không tiếp tục như thành công khi giao dịch hoặc dọn dẹp có thể thất bại.
- Không tự viết logic transaction thủ công nếu framework/transaction manager đã cung cấp ranh giới quản lý và quy tắc lỗi phù hợp.

Một số thao tác cần **phát hiện trước** chúng có thể ném checked exception, ví dụ `IOException` hoặc `SQLException`. Đưa các phương thức này vào `finally` không xóa nghĩa vụ khai báo/bắt ngoại lệ. Nếu bất cẩn bắt quá rộng rồi ghi log chung mà không xử lý, lỗi vẫn có nguy cơ mất dấu.

## 13. Ngoại lệ trong `catch` rồi bị `finally` che

Không phải chỉ exception xuất phát từ `try` mới bị che. `catch` có thể chuyển đổi hoặc ném lại ngoại lệ, rồi `finally` ném lỗi khác:

```java
try {
    perform();
} catch (Exception e) {
    throw new IllegalStateException("operation failed", e);
} finally {
    riskyCleanup();
}
```

Đây là mảnh minh họa. Nếu `riskyCleanup()` ném exception B, caller có thể chỉ thấy B dù `catch` đã cẩn thận giữ cause từ `perform()`.

Điều đó dẫn đến một quy tắc mạnh: **bọc exception đúng cách vẫn chưa đủ nếu đường cleanup cuối cùng có thể ghi đè ngoại lệ đã bọc**. Hãy kiểm tra cả `finally`, hook đóng tài nguyên, callback kết thúc request, interceptor và các bước rollback ở tầng ngoài.

Ngược lại, nếu cleanup không ném, wrapper được tạo trong `catch` sẽ giữ cause như thiết kế.

## 14. Logging: tại sao “log rồi ném” không thay thế bảo toàn exception?

Có người cố tránh mất lỗi bằng cách:

```java
try {
    perform();
} catch (Exception e) {
    logger.error("business failed", e);
    throw e;
} finally {
    cleanup();
}
```

Đây là mảnh tích hợp có `logger` được định nghĩa ở môi trường thực. Nếu `cleanup()` lại ném lỗi, caller vẫn có thể chỉ nhận cleanup error. Log ở `catch` có thể giữ một phần thông tin nhưng:

1. Không bảo toàn **đối tượng Throwable và cause/suppressed** trong luồng exception mà caller nhận.
2. Có thể tạo bản log lỗi trùng nếu tầng ngoài cũng log cleanup error.
3. Nếu hệ thống log không phát được sự kiện, thông tin ban đầu có thể vẫn mất.
4. Không thay thế việc ra quyết định đúng về **primary** và **secondary failures**.

Chiến lược tốt hơn là **giữ exception chain**, rồi để ranh giới chịu trách nhiệm báo một sự kiện lỗi đầy đủ (tùy policy). `Throwable.printStackTrace()` và logger có overload nhận đối tượng exception sẽ hiển thị cause/suppressed nếu được cấu hình đúng.

Ví dụ log tích hợp kiểu SLF4J:

```java
logger.error("Không hoàn thành operation={}, requestId={}",
        operation, requestId, failure);
```

Đây chỉ là mảnh minh họa, cần logger tương thích và biến đã có. Truyền **Throwable** thay vì chỉ `failure.getMessage()` để không mất stack và suppressed. Tránh phát tán dữ liệu nhạy cảm trong message và stack cho người dùng cuối.

## 15. Thử nghiệm: không chỉ kiểm tra message của exception ngoài cùng

Khi viết test cho xử lý cleanup, hãy xác nhận cả **nguyên nhân chính** và **ngoại lệ phụ**, thay vì chỉ kiểm tra `assertThrows(...)` có ném ra bất cứ lỗi nào.

Ví dụ JUnit 5 (đoạn tích hợp, không độc lập vì yêu cầu thư viện kiểm thử):

```java
IOException failure = assertThrows(IOException.class,
        () -> runOperation());

assertEquals("write failed", failure.getMessage());
assertEquals(1, failure.getSuppressed().length);
assertEquals("close failed",
        failure.getSuppressed()[0].getMessage());
```

`runOperation()` là hàm do ứng dụng định nghĩa. Tương tự, với các lỗi được bọc, nên kiểm tra `getCause()` cùng loại/message phù hợp. Các phép kiểm tra này giúp phát hiện regression khi ai đó thay `try-with-resources` bằng `try-finally` thủ công hoặc thêm một `return` vào cleanup.

Một bộ test thực tế nên có các tình huống:

| Công việc chính | Cleanup | Kỳ vọng |
|---|---|---|
| Thành công | Thành công | Trả kết quả thành công |
| Thất bại A | Thành công | Propagate A |
| Thành công | Thất bại B | Báo B |
| Thất bại A | Thất bại B | Với TWR: A primary, B suppressed |
| Thất bại A | Hai lần cleanup lỗi B, C | Với TWR: A primary, B/C suppressed theo thứ tự đóng |
| Có `return` từ `try` | Cleanup hoàn thành bình thường | Giữ kết quả trả về |
| Có `return` từ `try` | Cleanup ném B | Báo B, không trả giá trị |
| Có lỗi từ `try` | `finally` chứa `return` | Anti-pattern: lỗi bị nuốt; test phải phát hiện và loại bỏ |

Test về **thứ tự đóng** nên được thiết kế bằng tài nguyên giả định có output xác định. Tránh dựa vào sleep hoặc trạng thái bên ngoài khi chỉ muốn kiểm tra semantics của `finally`.

## 16. `finally` trong tác vụ bất đồng bộ vẫn có cùng quy tắc

Một `Callable` hoặc `Runnable` chạy trong `ExecutorService` cũng có thể viết `finally` sai:

```java
java.util.concurrent.Callable<String> task = () -> {
    try {
        throw new IllegalStateException("task failed");
    } finally {
        return "done";
    }
};
```

Đây là mảnh Java minh họa, với `Callable` đã sử dụng tên đầy đủ. Nếu submit vào executor, `Future.get()` có thể nhận `"done"` như **kết quả thành công** dù logic chính đã ném `IllegalStateException`. Vì `finally` trả giá trị, ngoại lệ bị nuốt **trước khi executor kịp ghi nhận failure**.

Ngược lại:

```java
java.util.concurrent.Callable<String> task = () -> {
    try {
        throw new IllegalStateException("task failed");
    } finally {
        throw new IllegalArgumentException("cleanup failed");
    }
};
```

Nếu tác vụ được submit bình thường, `Future.get()` sẽ ném `ExecutionException` chứa **`IllegalArgumentException`** từ cleanup làm cause; lỗi đầu `IllegalStateException` đã bị thay thế.

Trong `CompletableFuture`, callback ném lỗi từ cleanup có thể khiến stage hoàn thành ngoại lệ. Caller quan sát qua `join()` thường thấy `CompletionException` với cause là lỗi đang được propagate. Không nên cho rằng wrapper của async tự động khôi phục primary exception đã mất trong logic `finally`.

Nguyên tắc áp dụng rộng: **đừng dùng `return` ở `finally` trong callable**, và **giữ secondary exception bằng suppression hoặc hợp đồng xử lý rõ ràng** trước khi để task kết thúc. Điều này càng quan trọng khi lỗi được truyền qua nhiều thread và ít có cơ hội xem log trong đúng worker ban đầu.

## 17. `finally` và interrupt/cancellation: đừng vô tình phá tín hiệu dừng

Trong ứng dụng đa luồng, cleanup có thể diễn ra khi thread nhận `InterruptedException`:

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} finally {
    cleanup();
}
```

Đây là mảnh minh họa trong phương thức `void`, với `queue` và `cleanup()` đã khai báo. Phương thức `cleanup()` cần có hợp đồng phù hợp để không ném lỗi không mong đợi và che hướng xử lý interrupt. Nếu cleanup có thao tác chờ có thể ngắt, cờ interrupt đã được khôi phục có thể khiến lời gọi chờ mới lập tức ném `InterruptedException`; cần thiết kế đường dừng và dọn dẹp có chủ đích.

Với Future bị hủy, việc cancel không bảo đảm cleanup hoàn tất ngay. Nếu worker bất ngờ nuốt exception bằng `return` trong `finally`, trạng thái thực thi và trạng thái điều phối có thể khác kỳ vọng. Cần tách **yêu cầu dừng**, **việc worker thoát**, và **tình trạng tài nguyên đã được dọn**.

Không nên ghi mọi `InterruptedException` thành `ERROR` nếu đây là tín hiệu shutdown dự kiến, nhưng cũng không nên loại bỏ một lỗi cleanup nghiêm trọng chỉ vì thread đang dừng.

## 18. Những hiểu nhầm hay gặp

### “`finally` dùng để cleanup nên có thể `return` trong đó”

Sai. `return` trong `finally` thay thế cả `return`/`throw` đang chờ, khiến caller nhận sai kết quả hoặc mất ngoại lệ. `finally` nên tập trung vào cleanup **không thay đổi điều khiển luồng**.

### “Đã `throw e` trong `catch` thì chắc chắn caller thấy `e`”

Sai nếu `finally` hoàn thành đột ngột bằng `return` hoặc `throw` mới. Phải xem toàn bộ đường xử lý.

### “Exception nào xảy ra trước sẽ tự nằm trong `Caused by`”

Không đúng. Cause cần được thiết lập bằng constructor/`initCause` hoặc cơ chế tương đương. Hai exception xuất hiện liên tiếp trong `try` và `finally` **không tự có quan hệ cause**.

### “Exception ở `finally` sẽ tự suppressed vào exception gốc”

Không đúng đối với **`try-finally` thủ công thông thường**. `try-with-resources` có cơ chế suppression cho lỗi `close()` theo hợp đồng, còn `finally` tự viết cần chính sách rõ ràng.

### “Suppressed là lỗi có thể bỏ qua”

Không nhất thiết. Lỗi đóng stream/transaction có thể làm mất dữ liệu, rò kết nối hoặc che hậu quả cleanup. `Suppressed` chỉ là vai trò trong quá trình truyền lỗi, không phải mức độ nghiêm trọng.

### “Có `getSuppressed()` rỗng nghĩa là cleanup đã thành công”

Không suy ra được. Có thể ứng dụng đã dùng `try-finally` sai và làm mất lỗi, hoặc không lưu ngoại lệ thứ cấp; log cũng có thể bị cắt. Chỉ thấy `getSuppressed().length == 0` không chứng minh cleanup an toàn.

### “Thêm `catch (Exception e)` xung quanh mọi cleanup là đủ”

Nếu catch xong rồi im lặng, cleanup failure biến mất. Nếu luôn ném exception mới, nó có thể che lỗi chính. Cần policy rõ: propagate cleanup failure khi không có primary, hoặc ghi nó làm suppressed khi đã có primary, và xem xét side effect cần xử lý riêng.

### “Tự đóng tài nguyên thủ công lúc nào cũng kiểm soát tốt hơn”

Với tài nguyên `AutoCloseable`, `try-with-resources` thường an toàn, ngắn và đúng quy tắc exception hơn. Viết lại logic thủ công dễ sai thứ tự close và mất suppressed exception.

### “Đã thấy `ExecutionException` trong `Future.get()` là biết lỗi gốc”

`ExecutionException` thường chỉ là wrapper của lỗi worker. Nếu worker đã làm mất exception chính do cleanup, `getCause()` chỉ cho thấy **lỗi đã tồn tại sau khi `finally` kết thúc**, không thể tự khôi phục lỗi bị nuốt.

## 19. Checklist review một khối `finally`

Khi đọc code, kiểm tra lần lượt:

1. `finally` có **`return`**, `throw` chủ động, hoặc logic điều khiển luồng bất thường không?
2. Có phương thức cleanup nào **có thể ném checked hoặc unchecked exception** không?
3. Nếu thân `try` đã ném A, cleanup ném B thì **caller sẽ thấy gì**? A còn được bảo toàn qua cause/suppressed không?
4. Tài nguyên có triển khai `AutoCloseable` để thay bằng `try-with-resources` không?
5. Có nhiều tài nguyên? Thứ tự đóng có đúng và các lỗi đóng tiếp theo có bị mất không?
6. Nếu **không có primary**, lỗi cleanup có được báo đúng (không bị nuốt) không?
7. Nếu cleanup thất bại, có nguy cơ ảnh hưởng transaction, file, socket, lock hoặc dữ liệu đã ghi không?
8. Logging có in **Throwable đầy đủ** kèm suppressed ở đúng boundary, tránh log-and-rethrow trùng không?
9. Trong async, exception sau cleanup có được ghi nhận đúng trong `Future`/`CompletableFuture` không?
10. Test có bao phủ **đồng thời lỗi ở thân try và lỗi cleanup**, thay vì chỉ test happy path không?

## 20. Hướng thiết kế theo tình huống

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| File, stream, JDBC resource có `AutoCloseable` | **`try-with-resources`**; xem cả cause và suppressed |
| Cleanup không thể ném và rất ngắn | `finally` thường, không `return`/`throw` |
| Cleanup có thể ném checked exception nhưng tài nguyên không phải AutoCloseable | Viết policy bảo toàn primary; cân nhắc adapter `AutoCloseable` |
| Cleanup quan trọng hơn hoặc tạo sự cố độc lập | Quy định rõ precedence/aggregation và cảnh báo, không dựa vào tình cờ “throw cuối thắng” |
| Method cần trả kết quả nhưng cleanup có thể thất bại | Xác định liệu kết quả còn hợp lệ khi cleanup lỗi; giữ thông tin lỗi theo hợp đồng |
| Task executor/Future | Tránh `return` trong `finally`; đừng để cleanup vô tình che worker failure |
| Pipeline nhiều layer | Giữ cause và suppressed, log ở ranh giới có trách nhiệm |

**Kết luận:** `finally` có ưu tiên trong đường hoàn thành của `try`/`catch`, nên `return` hoặc exception trong `finally` có thể **ghi đè kết quả và làm mất lỗi chính**. Hãy dùng `try-with-resources` cho tài nguyên thích hợp, chỉ thực hiện cleanup an toàn trong `finally`, và khi có nhiều ngoại lệ, phải giữ rõ **primary** cùng **suppressed** thay vì để lỗi xảy ra cuối cùng vô tình quyết định câu chuyện mà caller và log nhìn thấy.
