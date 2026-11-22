# Bảng kết quả của try, catch, finally và try-with-resources

Khi đọc hoặc viết mã Java xử lý ngoại lệ, câu hỏi quan trọng không chỉ là “exception nào được ném?”, mà còn là **“sau toàn bộ cấu trúc `try`/`catch`/`finally`, phương thức thực sự trả về gì hoặc để exception nào thoát ra?”**. Thứ tự thực thi có thể khác trực giác: `finally` chạy sau đường `return` đã được chuẩn bị; nếu `finally` tự ném hoặc `return` thì kết quả đang chờ của `try` hoặc `catch` có thể bị thay thế. Với `try-with-resources`, Java đóng tài nguyên trước khi thực thi `catch`/`finally` gắn với cấu trúc đó, và lỗi khi đóng thường được giữ là *suppressed exceptions* thay vì che exception chính.

Bài tra cứu này trình bày **bảng kết quả** cho các tổ hợp phổ biến trong Java 17+, thứ tự chạy, ngoại lệ ưu tiên, giá trị trả về và cách xác minh bằng chương trình độc lập. Các ví dụ có stdout giải thích được; quy tắc nào phụ thuộc giả định sẽ được nói rõ.

## 1. Những thuật ngữ cần thống nhất

Một statement Java có thể **hoàn thành bình thường** (*normal completion*) hoặc **hoàn thành bất thường** (*abrupt completion*). Các lý do hoàn thành bất thường quan trọng với bài này gồm:

- `return` — yêu cầu trả kết quả khỏi method.
- `throw` — ném một `Throwable`.
- `break` hoặc `continue` — chuyển điều khiển trong vòng lặp/switch phù hợp.
- Exception phát sinh trong biểu thức, ví dụ `parseInt`, gọi hàm hoặc `close()`.

Để đọc bảng, giả định các phương thức có những đoạn mã đại diện:

```java
try {
    work();
} catch (IOException ex) {
    recover(ex);
} finally {
    cleanup();
}
```

Đây là **mã minh họa theo ngữ cảnh**, với `work`, `recover` và `cleanup` do ứng dụng định nghĩa. Việc bắt được `IOException` hay không phụ thuộc loại exception thực tế; `catch` chỉ bắt exception từ vùng `try` tương ứng và phù hợp với kiểu bắt.

Một từ khóa quan trọng là **kết quả đang chờ** (*pending completion*): khi `try` hoặc `catch` đã chuẩn bị `return`/`throw` nhưng chưa rời cấu trúc vì còn `finally`, kết quả đó vẫn có thể bị thay bởi completion của `finally`.

## 2. Bảng kết quả cơ bản của try/catch/finally

Đọc bảng với các quy ước:

- **T**: giá trị được chuẩn bị để `return` trong `try`.
- **C**: giá trị được chuẩn bị để `return` trong `catch`.
- **F**: giá trị được `return` trong `finally`.
- **E1**: exception ném từ `try`; **E2**: exception ném từ `catch`; **E3**: exception ném từ `finally`.
- “`finally` hoàn tất bình thường” nghĩa là bản thân `finally` không `throw`/`return`/`break`/`continue` làm thay đổi hướng thoát.
- Bảng giả định không có lỗi khác phát sinh từ xử lý class loading, VM termination hoặc hệ thống bên ngoài.

| Kết quả trong `try` | `catch` | Kết quả trong `finally` | Kết quả quan sát bên ngoài |
| --- | --- | --- | --- |
| Hoàn tất bình thường | Không chạy | Bình thường | Thực thi tiếp sau statement. |
| `return T` | Không chạy | Bình thường | Method trả **T**. |
| Ném **E1**, có catch phù hợp | Catch hoàn tất bình thường | Bình thường | Thực thi tiếp sau statement. |
| Ném **E1**, có catch phù hợp | `return C` | Bình thường | Method trả **C**. |
| Ném **E1**, có catch phù hợp | Ném **E2** | Bình thường | **E2** thoát ra. |
| Ném **E1**, không có catch phù hợp | Không chạy | Bình thường | **E1** thoát ra. |
| Hoàn tất bình thường | Không chạy | `return F` | Method trả **F**. |
| `return T` | Không chạy | `return F` | Method trả **F**; T bị thay. |
| `return T` | Không chạy | Ném **E3** | **E3** thoát; giá trị T không được trả. |
| Ném **E1** | Có hoặc không có catch | Ném **E3** | **E3** thắng completion đang chờ, trừ khi một cơ chế bên trong đã tự quản lý lỗi riêng. |
| Ném **E1**, catch trả C | `return C` | `return F` | Trả **F**; C bị thay. |
| Ném **E1**, catch ném E2 | Ném **E2** | Ném **E3** | **E3** thoát; E2 bị thay trong luồng exception tự nhiên. |

**Quy tắc trọng tâm:** nếu `finally` **hoàn tất bình thường**, kết quả đang chờ của `try` hoặc `catch` được giữ nguyên. Nếu `finally` **hoàn tất bất thường**, kết quả của `finally` quyết định đường thoát, còn completion trước đó có thể mất khỏi đường truyền.

Điều đó không có nghĩa JVM tự thêm exception bị che thành suppressed. **Thông thường `finally` ném lỗi mới sẽ che lỗi cũ mà không tự động liên kết chúng.** Cơ chế suppressed tự động là đặc điểm quan trọng của `try-with-resources` (và chỉ trong các trường hợp được đặc tả), không phải mọi khối `finally`.

## 3. Thứ tự thực thi: finally chạy trước khi method rời khỏi

Xét:

```java
static int example() {
    try {
        System.out.println("inside try");
        return 10;
    } finally {
        System.out.println("inside finally");
    }
}
```

Đây là phương thức Java hợp lệ khi đặt trong class. Nếu gọi và in kết quả, thứ tự là:

```text
inside try
inside finally
```

Sau hai dòng trên, caller mới nhận giá trị `10`. `finally` không chạy “sau khi caller đã thấy return” mà chạy **trước khi method hoàn thành**.

Một điều tương tự xảy ra khi `catch` chuẩn bị `return`:

```java
static int example() {
    try {
        throw new IllegalArgumentException("invalid");
    } catch (IllegalArgumentException ex) {
        return -1;
    } finally {
        System.out.println("cleanup");
    }
}
```

Khi caller nhận `-1`, dòng `cleanup` đã được in. Nếu `finally` ném exception khác, caller không nhận `-1`.

## 4. Ví dụ Java 17 hoàn chỉnh: các đường kết quả của try/catch/finally

Tạo file `TryCatchFinallyOutcomesDemo.java`:

```java
public class TryCatchFinallyOutcomesDemo {

    private static String normalReturn() {
        try {
            System.out.println("normal: try");
            return "T";
        } finally {
            System.out.println("normal: finally");
        }
    }

    private static String caughtReturn() {
        try {
            throw new IllegalArgumentException("bad input");
        } catch (IllegalArgumentException ex) {
            System.out.println("caught: catch");
            return "C";
        } finally {
            System.out.println("caught: finally");
        }
    }

    private static void uncaughtThrow() {
        try {
            throw new IllegalStateException("original");
        } catch (IllegalArgumentException ex) {
            System.out.println("unreachable catch");
        } finally {
            System.out.println("uncaught: finally");
        }
    }

    private static void catchThrows() {
        try {
            throw new IllegalArgumentException("input");
        } catch (IllegalArgumentException ex) {
            System.out.println("catchThrows: catch");
            throw new IllegalStateException("from catch", ex);
        } finally {
            System.out.println("catchThrows: finally");
        }
    }

    private static String finallyReturns() {
        try {
            System.out.println("finallyReturns: try");
            return "T";
        } finally {
            System.out.println("finallyReturns: finally");
            return "F"; // Cố ý minh họa anti-pattern.
        }
    }

    private static void finallyThrows() {
        try {
            throw new IllegalArgumentException("original");
        } finally {
            throw new IllegalStateException("finally wins");
        }
    }

    public static void main(String[] args) {
        System.out.println("normal result: " + normalReturn());
        System.out.println("caught result: " + caughtReturn());

        try {
            uncaughtThrow();
        } catch (IllegalStateException ex) {
            System.out.println("outer caught: " + ex.getMessage());
        }

        try {
            catchThrows();
        } catch (IllegalStateException ex) {
            System.out.println("outer catchThrows: " + ex.getMessage());
            System.out.println(
                    "cause: " + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("finallyReturns result: " + finallyReturns());

        try {
            finallyThrows();
        } catch (IllegalStateException ex) {
            System.out.println("outer finallyThrows: " + ex.getMessage());
            System.out.println(
                    "suppressed: " + ex.getSuppressed().length);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 TryCatchFinallyOutcomesDemo.java
java TryCatchFinallyOutcomesDemo
```

Stdout:

```text
normal: try
normal: finally
normal result: T
caught: catch
caught: finally
caught result: C
uncaught: finally
outer caught: original
catchThrows: catch
catchThrows: finally
outer catchThrows: from catch
cause: IllegalArgumentException
finallyReturns: try
finallyReturns: finally
finallyReturns result: F
outer finallyThrows: finally wins
suppressed: 0
```

**Đọc kết quả:**

1. `normalReturn()` chuẩn bị trả T; `finally` chạy rồi T mới tới caller.
2. `caughtReturn()`: exception trong `try` được `catch` xử lý, catch chuẩn bị trả C; `finally` vẫn chạy và C được giữ.
3. `uncaughtThrow()`: catch không phù hợp với `IllegalStateException`, nhưng `finally` vẫn chạy. `IllegalStateException("original")` đi ra đến catch bên ngoài.
4. `catchThrows()`: exception mới được ném **trong catch**. Catch cùng cấp không bắt lại exception do chính nó ném; `finally` chạy và exception mới được catch bên ngoài. Cause đã được code gắn tường minh.
5. `finallyReturns()` cố ý dùng `return` trong `finally` để minh họa việc trả F thay vì T. Đây là cách viết **không nên dùng trong production** vì làm mất hướng thoát đang chờ.
6. `finallyThrows()`: lỗi `IllegalStateException("finally wins")` che `IllegalArgumentException("original")` do `try` ném. `suppressed: 0` chứng minh **finally thông thường không tự thêm lỗi cũ vào suppressed**.

Chương trình cố ý minh họa hai cách viết nguy hiểm (`return`/`throw` trong `finally`). Không sao chép chúng vào cleanup production trừ khi muốn thay thế outcome một cách có chủ đích và đã xác định hậu quả.

## 5. Bảng riêng: return, throw, break và continue với finally

Ngoài `return` và `throw`, `finally` còn có thể tác động đến `break`/`continue` trong vòng lặp. Cơ chế chung vẫn là: hoàn thành bình thường giữ hướng thoát cũ; hoàn thành bất thường mới có thể thay hướng cũ.

| Điều đang chờ | `finally` hoàn tất bình thường | `finally` thay hướng điều khiển |
| --- | --- | --- |
| `return value` | Giữ giá trị đã đánh giá trước đó | `return` mới hoặc `throw` mới thay thế. |
| `throw E` | Giữ E | `return`/`throw` mới che E. |
| `break` | Tiếp tục break tới đích | `return`/`throw`/`continue` hợp lệ trong ngữ cảnh có thể thay. |
| `continue` | Tiếp tục vòng lặp theo đích continue | `return`/`throw`/`break` hợp lệ có thể thay. |
| Hoàn tất bình thường | Chạy statement tiếp theo | Hướng chuyển mới do finally quyết định. |

**Không đặt `return`, `break` hoặc `continue` trong `finally` để “xử lý cho gọn”.** Các câu lệnh đó có thể vô tình nuốt exception hoặc phá logic vòng lặp.

Ví dụ phản mẫu:

```java
for (int i = 0; i < 3; i++) {
    try {
        process(i);   // Có thể throw.
    } finally {
        continue;     // Có thể che throw đang chờ.
    }
}
```

Đây là snippet minh họa, `process` chưa định nghĩa. `continue` bên trong finally cố ý làm thay đổi hướng thoát của vòng lặp; nhiều bộ phân tích mã nguồn/linter cảnh báo kiểu này. Chỉ dùng `finally` để cleanup và để nó kết thúc bình thường khi có thể.

## 6. Giá trị return được đánh giá trước khi finally thực thi

Khi gặp `return expression`, Java tính **giá trị của expression** trước. Nếu sau đó `finally` hoàn tất bình thường, giá trị đã tính được trả cho caller. Thay đổi một biến local trong `finally` không tự tính lại expression.

Ví dụ:

```java
static int value() {
    int x = 5;
    try {
        return x;
    } finally {
        x = 99;
    }
}
```

Method trả **5**, không phải 99. Tuy nhiên, nếu expression trả **reference tới object mutable**, `finally` có thể sửa object đó và caller quan sát dữ liệu đã sửa, vì reference trả về vẫn trỏ cùng object.

Cần phân biệt:

- **Giá trị primitive hoặc reference được chọn khi đánh giá return.**
- **Nội dung của object mutable được reference ấy trỏ tới có thể thay đổi sau thời điểm đánh giá.**

`return` cũng không loại bỏ lỗi mới: nếu `finally` ném exception, giá trị đã chuẩn bị sẽ không đến caller.

## 7. Ví dụ Java 17 hoàn chỉnh: primitive và mutable object

Tạo file `ReturnAndFinallyValueDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ReturnAndFinallyValueDemo {

    private static int primitiveValue() {
        int number = 5;
        try {
            return number;
        } finally {
            number = 99;
            System.out.println("primitive finally: " + number);
        }
    }

    private static List<String> mutableResult() {
        List<String> result = new ArrayList<>();
        result.add("try");
        try {
            return result;
        } finally {
            result.add("finally");
        }
    }

    private static int returnInterruptedByThrow() {
        try {
            return 42;
        } finally {
            throw new IllegalStateException("cleanup failed");
        }
    }

    public static void main(String[] args) {
        System.out.println("primitive returned: " + primitiveValue());
        System.out.println("mutable returned: " + mutableResult());

        try {
            System.out.println(returnInterruptedByThrow());
        } catch (IllegalStateException ex) {
            System.out.println("no returned value: " + ex.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 ReturnAndFinallyValueDemo.java
java ReturnAndFinallyValueDemo
```

Stdout:

```text
primitive finally: 99
primitive returned: 5
mutable returned: [try, finally]
no returned value: cleanup failed
```

Ở dòng cuối, lời gọi `System.out.println(returnInterruptedByThrow())` **không in 42**, vì biểu thức argument không trả về bình thường: `finally` đã ném lỗi. `println` bên ngoài chỉ được gọi nếu việc đánh giá argument hoàn thành bình thường.

Với `mutableResult`, reference được chọn để return trước finally; sau đó finally sửa chính list ấy, vì vậy caller nhìn thấy cả hai phần tử. Điều này có thể phá hợp đồng nếu API lộ collection mutable nội bộ. Trả immutable snapshot khi caller không được phép quan sát mutation sau return.

## 8. Một finally không phải lúc nào cũng chắc chắn chạy

Trong vận hành Java bình thường, `finally` được thực hiện khi code rời `try`/`catch` theo các đường `return`, `throw`, `break`, `continue`. Nhưng **không nên nói finally chạy trong mọi hoàn cảnh tuyệt đối**:

- `System.exit` có thể kết thúc JVM trước khi stack hiện tại đi qua finally.
- `Runtime.halt` có thể dừng JVM ngay.
- JVM crash, tiến trình bị OS kill hoặc mất điện không bảo đảm chạy cleanup.
- Một thread bị kẹt vô hạn trong `try` không rời scope nên finally chưa chạy.
- `Thread.stop` cũ bị xem là không an toàn; không dùng để thiết kế cleanup tin cậy.

Vì vậy, finally là cơ chế cleanup rất quan trọng **trong luồng điều khiển ngôn ngữ**, nhưng không thay thế cơ chế phục hồi sau crash, transaction, lease expiration hoặc ghi bền vững.

## 9. try-with-resources: khác gì finally tự viết?

`try-with-resources` (TWR) được giới thiệu để đóng tài nguyên có kiểu `AutoCloseable` một cách có cấu trúc:

```java
try (InputStream in = Files.newInputStream(path)) {
    parse(in);
}
```

Đây là snippet minh họa; cần import `InputStream`, `Files` và định nghĩa `path`/`parse` theo ứng dụng.

Các quy tắc quan trọng:

1. Tài nguyên được **khởi tạo từ trái sang phải** trong khai báo.
2. Tài nguyên khởi tạo thành công được **đóng theo thứ tự ngược** khi rời phần thân.
3. Đóng tài nguyên diễn ra trên cả đường hoàn tất bình thường, `return` và exception (trong phạm vi các đường điều khiển Java bình thường).
4. Tài nguyên đã khởi tạo vẫn được đóng nếu quá trình tạo tài nguyên tiếp theo thất bại.
5. Exception từ body có ưu tiên làm **primary**; lỗi close phù hợp được thêm vào **suppressed** của exception chính.
6. Nếu body hoàn tất bình thường và close đầu tiên theo thứ tự đóng ném lỗi, lỗi close có thể là **primary**; các lỗi close sau đó được thêm vào suppressed.
7. `catch`/`finally` gắn với **toàn bộ TWR statement** thực thi sau khi các tài nguyên của statement đã được đóng theo quy tắc. Điều này khác với đặt một `catch` bên trong body.

Không tự hiểu TWR là “finally cũng tốt như nhau”: với finally viết thủ công, lỗi close mới có thể che lỗi body trừ khi code tự gắn suppressed. TWR giúp bảo toàn cả hai nguyên nhân.

## 10. Bảng tra cứu kết quả try-with-resources

Quy ước:

- **Ebody**: Throwable ném từ body.
- **Einit**: Throwable ném khi khởi tạo một resource.
- **Eclose-B**, **Eclose-A**: lỗi khi đóng B và A, với resource khai báo A rồi B nên **đóng B trước A**.
- “Suppressed” nghĩa là có thể truy cập qua `primary.getSuppressed()`; thông thường mỗi lỗi close được đưa vào mảng theo thứ tự xảy ra.
- Bảng giả định object exception thông thường có suppression enabled, các lỗi được ném là object khác nhau và không có xử lý tùy biến can thiệp.

| Kết quả body/khởi tạo | Đóng resource | Kết quả TWR |
| --- | --- | --- |
| Body bình thường | Tất cả close thành công | TWR bình thường, thực thi tiếp. |
| Body `return V` | Tất cả close thành công | Method trả V sau khi close. |
| Body ném **Ebody** | Tất cả close thành công | Ebody thoát; không có lỗi close. |
| Body ném **Ebody** | B close ném **Eclose-B** | Ebody vẫn primary; Eclose-B suppressed. |
| Body ném **Ebody** | B và A đều close ném | Ebody primary; lỗi B rồi A suppressed. |
| Body bình thường | B close ném Eclose-B, A đóng bình thường | Eclose-B thoát. |
| Body bình thường | B và A đều close ném | Eclose-B primary; Eclose-A suppressed của Eclose-B. |
| Body `return V` | Một close ném Eclose | Eclose thoát; V **không được trả**. |
| Khởi tạo A thành công; khởi tạo B ném Einit | A close bình thường | Einit thoát; body không chạy. |
| Khởi tạo A thành công; B ném Einit | A close cũng ném Eclose-A | Einit primary; Eclose-A suppressed. |
| Resource duy nhất khởi tạo thất bại | Không có resource ấy để close | Exception khởi tạo thoát; body không chạy. |

### Tại sao lỗi close không che Ebody?

TWR được đặc tả để bảo tồn lỗi công việc chính. Nếu body ném `IOException("read failed")` và `close()` cũng ném `IOException("close failed")`, exception ra ngoài là **"read failed"**; còn "close failed" nằm trong `getSuppressed()`.

Trái lại:

```java
Resource resource = open();
try {
    work(resource);   // Ném Ebody.
} finally {
    resource.close(); // Ném Eclose.
}
```

Đây là snippet minh họa; với cách viết này nếu `close()` ném, Eclose có thể thay Ebody. Muốn bảo toàn như TWR phải viết thêm code quản lý suppressed đúng cách. Vì vậy với tài nguyên sở hữu theo scope, **ưu tiên try-with-resources**.

## 11. Ví dụ Java 17 hoàn chỉnh: body lỗi và nhiều close lỗi

Tạo file `TryWithResourcesOutcomesDemo.java`:

```java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class TryWithResourcesOutcomesDemo {

    private static final class Resource implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;
        private final List<String> events;

        Resource(String name, boolean failOnClose, List<String> events) {
            this.name = name;
            this.failOnClose = failOnClose;
            this.events = events;
            events.add("open " + name);
        }

        @Override
        public void close() throws IOException {
            events.add("close " + name);
            if (failOnClose) {
                throw new IOException("close " + name + " failed");
            }
        }
    }

    private static void printFailure(Throwable primary) {
        System.out.println("primary: " + primary.getMessage());
        System.out.println("suppressed count: "
                + primary.getSuppressed().length);
        for (Throwable s : primary.getSuppressed()) {
            System.out.println("suppressed: " + s.getMessage());
        }
    }

    private static void bodyFails() {
        List<String> events = new ArrayList<>();
        try (Resource a = new Resource("A", true, events);
             Resource b = new Resource("B", true, events)) {
            events.add("body failed");
            throw new IllegalStateException("body error");
        } catch (IllegalStateException ex) {
            events.forEach(System.out::println);
            printFailure(ex);
        } catch (IOException ex) {
            throw new AssertionError("unexpected close-only", ex);
        }
    }

    private static void closeFails() {
        List<String> events = new ArrayList<>();
        try (Resource a = new Resource("A", true, events);
             Resource b = new Resource("B", true, events)) {
            events.add("body OK");
        } catch (IOException ex) {
            events.forEach(System.out::println);
            printFailure(ex);
        }
    }

    private static String returnButCloseFails() throws IOException {
        List<String> events = new ArrayList<>();
        try (Resource x = new Resource("X", true, events)) {
            System.out.println("body returns");
            return "VALUE";
        }
    }

    private static Resource openSecond(List<String> events)
            throws IOException {
        events.add("open B failed");
        throw new IOException("init B failed");
    }

    private static void initFails() {
        List<String> events = new ArrayList<>();
        try (Resource a = new Resource("A", true, events);
             Resource b = openSecond(events)) {
            events.add("body unreachable");
        } catch (IOException ex) {
            events.forEach(System.out::println);
            printFailure(ex);
        }
    }

    public static void main(String[] args) {
        System.out.println("CASE: BODY FAILURE");
        bodyFails();

        System.out.println("CASE: CLOSE FAILURE");
        closeFails();

        System.out.println("CASE: RETURN/CLOSE");
        try {
            System.out.println(returnButCloseFails());
        } catch (IOException ex) {
            printFailure(ex);
        }

        System.out.println("CASE: INIT FAILURE");
        initFails();
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 TryWithResourcesOutcomesDemo.java
java TryWithResourcesOutcomesDemo
```

Stdout:

```text
CASE: BODY FAILURE
open A
open B
body failed
close B
close A
primary: body error
suppressed count: 2
suppressed: close B failed
suppressed: close A failed
CASE: CLOSE FAILURE
open A
open B
body OK
close B
close A
primary: close B failed
suppressed count: 1
suppressed: close A failed
CASE: RETURN/CLOSE
body returns
primary: close X failed
suppressed count: 0
CASE: INIT FAILURE
open A
open B failed
close A
primary: init B failed
suppressed count: 1
suppressed: close A failed
```

Giải thích kết quả:

- **BODY FAILURE:** Ebody là `IllegalStateException("body error")`. Đóng B và A đều ném `IOException`, nhưng body error vẫn primary và hai lỗi đóng được suppressed theo thứ tự B rồi A.
- **CLOSE FAILURE:** body thành công; B là resource đóng đầu tiên và thất bại, nên lỗi B là primary. A cũng đóng dù B đã lỗi; lỗi A là suppressed.
- **RETURN/CLOSE:** body đã chuẩn bị trả `"VALUE"` nhưng `close X` ném, nên caller nhận `IOException` và **không in `VALUE`**. `Resource X` ghi event vào danh sách riêng mà demo không in; vì thế stdout của case này bắt đầu trực tiếp ở “body returns”.
- **INIT FAILURE:** A đã tạo, mở B thất bại. Body không chạy. Java đóng A; vì A cũng ném, lỗi đóng A được suppressed vào lỗi khởi tạo B.

Các `Resource` trong demo chỉ ghi event và ném exception có kiểm soát, nên thứ tự output không phụ thuộc vào luồng bất đồng bộ. Trong production, `close()` có thể đóng một phần rồi lỗi; việc “đã gọi close” **không đồng nghĩa cleanup chắc chắn thành công**.

## 12. Khi TWR có catch và finally bên ngoài thì thứ tự là gì?

Xét:

```java
try (Resource r = openResource()) {
    System.out.println("body");
} catch (IOException ex) {
    System.out.println("catch");
} finally {
    System.out.println("finally");
}
```

Đây là snippet minh họa, `Resource`/`openResource` do ứng dụng định nghĩa. Trong hình thức này, resource được đóng **trước khi vào catch hoặc finally của TWR statement**. Nếu `close` ném `IOException` và body không có lỗi, catch có thể bắt chính exception do close tạo ra.

Trình tự:

```text
khởi tạo resource
body
close resource
catch phù hợp (nếu có exception)
finally
tiếp tục hoặc truyền exception ra ngoài
```

Nếu body bình thường và close bình thường thì `catch` không chạy, chỉ có `finally`. Nếu body ném Ebody và close ném Eclose, catch phù hợp với **Ebody** có thể đọc `Ebody.getSuppressed()` để biết Eclose.

**Phân biệt catch bên trong body:**

```java
try (Resource r = openResource()) {
    try {
        work(r);
    } catch (IOException ex) {
        recover(ex);
    }
}
```

Đây là snippet minh họa. Catch **bên trong body** chỉ bắt lỗi phát sinh trong vùng `try` nội bộ; nó **không bắt lỗi từ `r.close()`** xảy ra sau khi body hoàn tất. Nếu muốn bắt close exception, cần catch ngoài TWR hoặc try bao ngoài thích hợp.

## 13. finally sau TWR vẫn có thể thay exception chính

Nếu TWR tạo exception đã có suppressed, và `finally` gắn ngoài TWR tiếp tục ném một exception khác, thì **exception finally có thể thay exception từ TWR**, làm caller không còn trực tiếp quan sát Ebody cùng suppressed.

Ví dụ phản mẫu:

```java
try (Resource r = openResource()) {
    throw new IOException("body");
} finally {
    throw new IllegalStateException("finally failed");
}
```

Đây là snippet minh họa; các type/import cần có trong project và method phải xử lý checked exception theo contract. Kết quả thoát tự nhiên là `IllegalStateException("finally failed")` chứ không phải `IOException("body")`. Vì vậy **TWR giúp giữ lỗi đóng tài nguyên, nhưng không bảo vệ khỏi một finally ngoài có completion bất thường**.

Trong production, không gọi code cleanup dễ ném mà không xử lý trong `finally` theo cách vô tình che lỗi gốc. Ưu tiên scope tài nguyên rõ và cơ chế ghi nhận/ghép lỗi có kiểm soát.

## 14. Phân biệt cause và suppressed exception

Hai cơ chế phục vụ mục đích khác nhau:

| Cơ chế | API | Ý nghĩa |
| --- | --- | --- |
| **Cause** | `Throwable.getCause()`, constructor nhận cause hoặc `initCause` theo contract | Exception này được tạo để bao/diễn giải exception nguyên nhân ở tầng thấp hơn. |
| **Suppressed** | `Throwable.getSuppressed()`, `addSuppressed` | Những exception phụ bị giữ lại vì một exception khác có ưu tiên, điển hình lỗi close trong TWR. |

Ví dụ:

```java
IOException original = new IOException("read failed");
IllegalStateException wrapper =
        new IllegalStateException("service failed", original);

wrapper.addSuppressed(new IOException("cleanup failed"));
```

Đoạn trên là snippet Java hợp lệ khi đặt trong một method với import `IOException`. `wrapper.getCause()` là `original`; `wrapper.getSuppressed()[0]` là lỗi cleanup. Chúng không phải cùng một chuỗi liên kết.

Trong một exception thực tế, cả cause và suppressed đều có thể tồn tại. Stack trace khi in đầy đủ thường biểu diễn cả hai, nhưng không nên kiểm tra test chỉ bằng việc tìm chuỗi trong log. Dùng chính các API `getCause()` và `getSuppressed()` để kiểm tra cấu trúc lỗi.

### Một số giới hạn của suppressed

- `addSuppressed` không cho phép suppress **chính object Throwable đang nhận lời gọi**; hành vi đó có thể ném `IllegalArgumentException`.
- Suppression có thể bị tắt bằng constructor đặc biệt của `Throwable`; khi đó việc thêm suppressed có thể bị bỏ qua theo contract.
- `getSuppressed()` trả một mảng; đừng mặc định mọi exception bất kỳ đều có suppressed.
- TWR có quy tắc tự động xử lý những exception đóng tài nguyên trong trường hợp thích hợp; `finally` thông thường không có bảo đảm tương đương.

Một số hệ thống tạo lỗi domain với suppression disabled hoặc sử dụng exception đặc biệt. Nếu cần log tất cả cleanup failures, phải hiểu contract của Throwable và tài nguyên đang dùng.

## 15. Nhiều resource: mở trái sang phải, đóng phải sang trái

Ví dụ:

```java
try (A a = new A();
     B b = new B(a);
     C c = new C(b)) {
    doWork(a, b, c);
}
```

Đây là snippet minh họa, các type và hàm được giả định. Thứ tự bình thường:

```text
open A
open B
open C
body
close C
close B
close A
```

Nếu B khởi tạo thất bại, A đã có phải được đóng; C **chưa được khởi tạo**, không có C để đóng. Nếu C khởi tạo thất bại, B rồi A được đóng.

Đóng theo thứ tự ngược giúp phản ánh dependency: resource tạo sau thường phụ thuộc resource tạo trước. Tuy nhiên, không phải mọi resource đều có thể đóng an toàn theo quy tắc đó nếu contract đặc biệt; khi cần chủ động điều phối cleanup, phải thiết kế scopes/thứ tự tương ứng.

### AutoCloseable và Closeable

`AutoCloseable.close()` có thể khai báo `throws Exception`. `java.io.Closeable.close()` khai báo `throws IOException` và có hợp đồng chi tiết riêng. Khi định nghĩa class implement `AutoCloseable`, có thể override `close()` với kiểu exception hẹp hơn, kể cả không khai báo checked exception.

Ví dụ:

```java
final class InMemoryHandle implements AutoCloseable {
    @Override
    public void close() {
        // Cleanup không ném checked exception.
    }
}
```

Đây là đoạn khai báo class độc lập hợp lệ về cú pháp. Kiểu được khai báo của resource và `close` ảnh hưởng tới các checked exceptions mà compiler yêu cầu caller xử lý hoặc khai báo.

## 16. Return từ body TWR không bỏ qua close

Một hiểu lầm phổ biến:

```java
try (Resource r = acquire()) {
    return calculate(r);
}
```

Đây là snippet minh họa. Java **tính `calculate(r)` trước**, chuẩn bị giá trị return, sau đó đóng r. Nếu đóng thành công thì trả giá trị. Nếu `close()` ném, lỗi close có thể thay completion `return`.

Do đó khi API đọc file:

```java
try (InputStream input = Files.newInputStream(path)) {
    return parse(input);
}
```

return chỉ thành công nếu `parse` hoàn thành và quá trình đóng resource không phát sinh exception vượt ra ngoài theo contract. Điều này thường mong muốn: ví dụ output stream có thể cần flush/close và lỗi đóng là tín hiệu dữ liệu chưa được lưu đầy đủ.

Không tự đặt `return` trong finally để “giữ kết quả bằng mọi giá” vì như vậy có thể nuốt mất lỗi I/O quan trọng.

## 17. Nếu catch xử lý lỗi body rồi close lại lỗi?

Xét:

```java
try (Resource r = acquire()) {
    try {
        work(r);
    } catch (IOException ex) {
        recover(ex);
    }
}
```

Nếu `work` ném `IOException` nhưng `recover` xử lý và **body hoàn tất bình thường**, resource được đóng sau đó. Nếu close ném, exception close trở thành lỗi quan sát bên ngoài TWR.

Ngược lại, nếu `recover` **ném exception mới**, đó là lỗi của body TWR và close exception sẽ có thể bị suppressed vào nó. Điều này cho thấy bảng chỉ có thể trả lời đúng khi biết **completion cuối cùng của body**, không chỉ exception ban đầu ở `work`.

Ví dụ:

| Hành vi trong body | Hành vi close | Kết quả |
| --- | --- | --- |
| `work` lỗi, catch nội bộ xử lý rồi body bình thường | Close bình thường | TWR bình thường. |
| `work` lỗi, catch nội bộ xử lý rồi body bình thường | Close lỗi Eclose | Eclose là primary. |
| `work` lỗi, catch nội bộ ném Enew | Close bình thường | Enew thoát. |
| `work` lỗi, catch nội bộ ném Enew | Close lỗi Eclose | Enew primary; Eclose suppressed. |

Đừng chỉ đếm “có exception được ném ở đâu đó” để dự đoán kết quả cuối; phải theo dõi **nó có được bắt/phục hồi trước khi rời scope không**.

## 18. Exception trong biểu thức khởi tạo resource

TWR có thể thất bại **trước khi phần body được thực thi**:

```java
try (Resource a = openA();
     Resource b = openB()) {
    work();
}
```

Nếu `openB()` ném exception:

- A đã mở sẽ được đóng theo quy tắc TWR.
- B không được tạo thành công thì không có object B để đóng.
- `work()` không chạy.
- Nếu đóng A cũng ném, exception do `openB` tạo là primary, lỗi đóng A là suppressed.
- Catch ngoài TWR có thể xử lý exception khởi tạo và xem suppressed.

Nếu chính `openB` có side effect **trước khi ném nhưng chưa trả về resource object**, TWR ở caller không thể tự đóng thứ đã mở bên trong openB mà chưa trả handle. **Hàm factory phải tự cleanup tài nguyên nội bộ đã acquire thành công trước khi thất bại.**

## 19. Resource null và biến resource đã có

Trong `try-with-resources`, biến resource có thể chứa `null`; Java bỏ qua lời gọi `close` tương ứng khi reference null, thay vì tự tạo `NullPointerException` vì close. Nhưng dùng resource null thường khiến logic và ownership khó đọc; nên lựa chọn rõ hợp đồng.

Từ Java 9, TWR có thể sử dụng biến final hoặc **effectively final** đã được khai báo bên ngoài:

```java
InputStream stream = Files.newInputStream(path);
try (stream) {
    consume(stream);
}
```

Đây là snippet minh họa; cần import các lớp và khai báo `path`, `consume` thích hợp. Java sẽ đóng resource được tham chiếu khi rời scope. Dù biến khai báo ở ngoài, **lệnh `try (stream)` vẫn có nghĩa TWR sở hữu trách nhiệm gọi close**; không áp dụng bừa cho shared resource do caller khác quản lý.

Nếu caller chỉ cho mượn một stream, đừng đưa nó vào TWR trừ khi hợp đồng cho phép API đó đóng stream. Nếu cần dùng tài nguyên xuyên nhiều bước có ownership rộng hơn, scope đóng phải thuộc owner thực sự.

## 20. IOException hay Error trong close có được suppressed không?

TWR làm việc theo cơ chế `Throwable`, không chỉ IOException. Một `close()` có thể ném unchecked exception hoặc một `Error`; nếu body đã hoàn thành bằng một Throwable khác, lỗi close phù hợp có thể được ghi vào suppressed của lỗi chính.

Tuy nhiên, **không nên dùng cơ chế này để nuốt Error** hoặc đảm bảo có thể phục hồi sau `OutOfMemoryError`/lỗi VM nghiêm trọng. Những lỗi như vậy có thể khiến runtime không còn đủ tài nguyên để vận hành đúng. Tránh tự viết `catch(Throwable)` để chuyển tất cả thành kết quả thành công.

Với tài nguyên ngoài JVM, việc close ném Error cũng không nói rằng dữ liệu đã rollback. Mục tiêu của TWR là quản lý lời gọi đóng và ưu tiên exception **trong luồng điều khiển Java**, không phải transaction phân tán.

## 21. finally và cleanup khi return hoặc throw: tránh thay kết quả

Một khối cleanup tốt có xu hướng:

```java
Resource r = acquire();
try {
    work(r);
} finally {
    r.close();
}
```

Đây là cấu trúc minh họa. Nó giải phóng tài nguyên trên nhiều đường rời scope, nhưng vẫn có nguy cơ lỗi close che lỗi work như đã giải thích. Khi resource là `AutoCloseable`, ưu tiên TWR.

Nếu buộc phải tự quản lý nhiều lỗi cleanup, thiết kế rõ exception primary và suppressed, hoặc tạo một outcome có cấu trúc. Không được tự viết logic “nếu có lỗi thì `return null` trong finally” vì nó xóa đường thất bại.

**Cũng không nên gọi logging code có thể ném trong finally mà không có phương án:** nếu logger/appender phát sinh lỗi và finally ném, exception nghiệp vụ chính có thể bị che. Hãy giữ cleanup đơn giản, có kiểm soát và theo dõi failures bằng tầng phù hợp.

## 22. finally có phải nơi khôi phục interrupt không?

`InterruptedException` thường được ném từ thao tác blocking như `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await` hoặc `Future.get`, làm kết thúc thao tác chờ. Khi catch `InterruptedException`, có thể truyền tiếp hoặc khôi phục cờ interrupt nếu không thể truyền checked exception:

```java
try {
    waitForWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} finally {
    cleanupOwnedResources();
}
```

Đây là snippet minh họa, với `waitForWork`/`cleanupOwnedResources` giả định. Lưu ý: **khôi phục cờ trước finally** có thể khiến cleanup blocking interruptible bị ngắt ngay. Nếu cleanup cần chờ trong thời hạn nhất định, phải thiết kế thứ tự bắt/đóng/phục hồi cờ có chủ đích.

TWR với `catch` bên ngoài có ưu điểm là resource `close` xảy ra trước khi catch khôi phục flag. Nhưng close vẫn có thể ném exception và cần policy tương ứng. Không dùng `return` trong finally để xóa `InterruptedException`; như vậy caller có thể không biết yêu cầu dừng.

## 23. TWR không tự làm thao tác I/O hoặc transaction trở nên atomic

TWR bảo đảm **đóng tài nguyên theo scope khi flow Java rời block**, không bảo đảm:

- Ghi file bị rollback nếu phần thân thất bại.
- Request HTTP bị hủy ở server khi client đóng socket.
- Database đã rollback sau khi connection `close()` nếu transaction chưa có hợp đồng rõ.
- Message đã gửi được thu hồi khi lỗi xảy ra sau publish.
- Giải phóng lock/permit đúng nếu code acquire sai phạm vi.
- Một task async đã dừng khi caller đóng resource chung.

Nếu việc ghi file phải atomic theo hợp đồng, cần chiến lược tệp tạm và commit/rename phù hợp filesystem, không chỉ try-with-resources. Với database, cần transaction/rollback được thiết kế; với mạng, cần idempotency và trạng thái UNKNOWN/PENDING khi kết quả không thể xác minh.

Phần “result” trong bảng TWR là **kết quả điều khiển Java của method**, không phải lời bảo đảm mọi side effect ngoài tiến trình chưa xảy ra.

## 24. Checked exception của close và giới hạn biên dịch

Một class có kiểu `AutoCloseable` nói chung khai báo `close() throws Exception`. Vì vậy TWR sử dụng resource kiểu `AutoCloseable` có thể yêu cầu method:

- Khai báo `throws Exception` thích hợp; hoặc
- Catch loại checked exception cần thiết.

Ví dụ:

```java
static void demo(AutoCloseable r) throws Exception {
    try (r) {
        System.out.println("using resource");
    }
}
```

Đây là phương thức hợp lệ khi đặt trong class; tham số `r` là effectively final nếu không bị gán lại. `throws Exception` xuất phát từ khả năng `AutoCloseable.close()` ném checked `Exception`.

Nếu subtype override `close()` không ném checked exception và biến resource có static type subtype, compiler có thể không yêu cầu `throws Exception` chỉ do `close`. Loại cụ thể của resource, không chỉ hành vi runtime, ảnh hưởng kiểm tra exception lúc biên dịch.

`catch` được chọn theo **runtime class của Throwable**, nhưng tính hợp lệ của nhiều checked `catch` còn chịu kiểm tra của compiler dựa trên các exception có thể được ném theo static types. Đừng thêm `catch(IOException)` khi compiler đã xác định đoạn `try` không có đường nào ném loại checked ấy.

## 25. Bảng chọn cấu trúc khi thiết kế API

| Nhu cầu | Cấu trúc nên cân nhắc | Lý do |
| --- | --- | --- |
| Chạy code có thể lỗi và xử lý lỗi được xác định | `try/catch` với loại exception cụ thể | Phục hồi/đổi nghĩa đúng ranh giới. |
| Luôn chạy một phần cleanup không phải resource close | `try/finally`, finally cố gắng kết thúc bình thường | Cleanup trên các đường thoát thông thường. |
| Quản lý `AutoCloseable` do scope sở hữu | `try-with-resources` | Đóng theo thứ tự chuẩn, bảo toàn suppressed. |
| Có nhiều resource phụ thuộc nhau | TWR với khai báo theo thứ tự acquire | Đóng ngược thứ tự, kể cả khi acquire sau lỗi. |
| Muốn kết quả trả về cùng dữ liệu sau cleanup | `return` trong try; finally không return/throw ngoài ý muốn | Giá trị tính trước cleanup, chỉ đến caller nếu cleanup không thay outcome. |
| Muốn preserve lỗi body lẫn lỗi close | TWR hoặc cơ chế explicit addSuppressed đúng | Tránh che nguyên nhân chính. |
| Cần transaction nhiều bước | Transaction/domain workflow, thường kết hợp TWR cho connection | TWR không thay transaction. |
| Cần observability khi lỗi | Log/counter tại boundary có quyền sở hữu | Không làm finally tự ném khiến mất lỗi gốc. |

Một cấu trúc có thể đúng cú pháp nhưng sai contract. Chọn theo loại resource, quyền sở hữu, exception cần giữ, trạng thái sau lỗi và cách caller xử lý.

## 26. Những lỗi nhận thức thường gặp

**“Có return trong try thì finally không chạy.”** Sai. Return được chuẩn bị, finally chạy rồi method mới trả nếu finally hoàn tất bình thường.

**“Return trong finally chỉ là ghi đè biến local.”** Sai. Return trong finally có thể thay hẳn return/throw đang chờ.

**“Finally luôn chạy, kể cả JVM bị kill.”** Sai. Nó là cơ chế ngôn ngữ trong luồng điều khiển bình thường, không phải bảo đảm khi process crash/halt.

**“Lỗi trong catch được catch khác cùng statement bắt tiếp.”** Sai. Các catch clause của cùng try không được tổ chức thành chuỗi xử lý cho lỗi ném từ một catch clause; lỗi mới đi qua finally và caller/outer catch.

**“Finally ném exception sẽ tự lưu exception cũ vào suppressed.”** Sai với finally thông thường. Nếu Efinally thắng, Etry có thể mất khỏi đường truyền tự nhiên.

**“TWR chỉ đóng khi không có return.”** Sai. TWR đóng resource trước khi rời scope, kể cả khi body return.

**“TWR đóng từ trái qua phải.”** Sai. Tạo trái sang phải, đóng phải sang trái.

**“Nếu resource thứ hai tạo thất bại thì resource thứ nhất không đóng.”** Sai. Những resource đã khởi tạo thành công vẫn được cleanup theo TWR.

**“Lỗi close lúc body throw sẽ thay lỗi body.”** Không phải quy tắc TWR thông thường; close lỗi thường được suppressed vào body exception.

**“Nếu body return và close fail thì vẫn trả được giá trị.”** Sai; lỗi close có thể thay pending return.

**“Cause và suppressed là giống nhau.”** Sai. Cause biểu diễn chuỗi nguyên nhân/wrapping; suppressed giữ các lỗi phụ không được chọn làm primary.

**“Catch đặt trong body có thể bắt lỗi resource close.”** Không, nếu close xảy ra sau khi vùng try nội bộ đã hoàn tất; cần catch ngoài statement TWR.

**“Có TWR là database transaction chắc rollback.”** Sai. Cleanup resource không tương đương transaction commit/rollback.

**“TWR đóng resource mượn là vô hại.”** Sai. Scope phải sở hữu trách nhiệm đóng; resource dùng chung có thể bị thành phần khác sử dụng.

**“Dùng `catch(Throwable)` là cách an toàn để lấy mọi exception.”** Thường sai cho business recovery: có thể nuốt Error nghiêm trọng, bug hoặc interruption/cancellation bị chuyển nghĩa sai.

## 27. Checklist đọc một đoạn mã try/catch/finally

Khi phải dự đoán kết quả, làm theo trình tự:

1. **Xác định exception hoặc return thật sự phát sinh trong try.** Đừng đoán theo tên method.
2. **Xác định catch phù hợp đầu tiên** trong cùng try, nếu có.
3. **Theo dõi completion của catch**: xử lý bình thường, return hay throw mới?
4. **Nếu là TWR, trước khi đến catch ngoài, xử lý resource close** theo thứ tự ngược khởi tạo.
5. **Phân loại lỗi đóng:** body/init có primary Throwable hay không? Nếu có, close errors thường suppressed; nếu không, close exception đầu tiên theo thứ tự đóng có thể primary.
6. **Xác định finally gắn với scope nào**: finally của TWR bên ngoài khác try/finally nằm bên trong body.
7. **Xác định completion của finally**: bình thường giữ kết quả trước; throw/return mới thay.
8. **Nếu có return expression**, nó được đánh giá trước cleanup; check xem finally có mutate object được trả hay không.
9. **Kiểm tra exception còn đi ra caller** và quan hệ cause/suppressed.
10. **Phân biệt kết quả Java với side effect bên ngoài**: close không bảo đảm transaction rollback.
11. **Kiểm tra ownership/lifecycle**: resource được scope tạo hay chỉ mượn?
12. **So với contract**, hỏi method sau lỗi có còn dùng được và state có hợp lệ không.

Đừng giải bài bằng câu ngắn “finally luôn thắng”. **Finally chỉ thay completion khi nó tự hoàn tất bất thường**; khi hoàn tất bình thường, nó giữ pending return/throw.

## 28. Bài tập tra cứu kết quả

**Câu 1.** `try` chuẩn bị `return 7`, `finally` chỉ in một dòng và hoàn tất bình thường. Method trả gì?

**Đáp án:** 7, sau khi finally chạy.

**Câu 2.** `try` ném `IllegalArgumentException`, catch phù hợp trả `-1`, finally hoàn tất bình thường. Kết quả?

**Đáp án:** -1. Exception đã được catch xử lý và pending return của catch không bị thay.

**Câu 3.** `try` ném E1, không có catch phù hợp, finally ném E2. Caller thấy gì? E1 có tự thành suppressed không?

**Đáp án:** Caller thấy E2; E1 không được tự gắn suppressed bởi finally thường.

**Câu 4.** `try` trả tham chiếu tới `ArrayList` rồi finally thêm phần tử vào list. Caller thấy list trước hay sau thay đổi?

**Đáp án:** Reference đã được chọn trước, nhưng object mutable bị sửa trong finally nên caller thấy phần tử được thêm.

**Câu 5.** TWR khai báo A, B, C; body hoàn tất bình thường. Close C và A ném IOException, B đóng bình thường. Exception nào primary?

**Đáp án:** Lỗi close C primary vì C đóng trước. Lỗi close A trở thành suppressed của lỗi C.

**Câu 6.** Body TWR ném Ebody, close B và A đều lỗi. Bảng ưu tiên?

**Đáp án:** Ebody primary; lỗi B rồi A được suppressed theo thứ tự đóng, giả định suppression enabled và các Throwable hợp lệ.

**Câu 7.** A tạo thành công, tạo B ném Einit, đóng A cũng lỗi. Body có chạy không? Caller thấy gì?

**Đáp án:** Body không chạy; Einit primary, lỗi close A suppressed.

**Câu 8.** TWR body return `"OK"`, close ném `IOException`. Caller nhận `"OK"` hay IOException?

**Đáp án:** IOException; pending return bị thay bởi exceptional completion của close.

**Câu 9.** Có `try (r) { try {work();} catch(IOException e) {recover();} }`. Close r ném IOException sau khi body hoàn tất. Catch nội bộ có bắt được không?

**Đáp án:** Không; close xảy ra sau body. Cần catch ngoài TWR để bắt exception từ close.

**Câu 10.** Có `try (r) {throw Ebody;} finally {throw Efinally;}` và r.close cũng ném lỗi. Caller thấy gì?

**Đáp án:** Trong xử lý TWR, lỗi close có thể được suppressed vào Ebody; sau đó finally ném Efinally và thay kết quả đang chờ. Caller thấy Efinally, không tự nhận chuỗi Ebody/suppressed nếu code không giữ riêng chúng.

## 29. Tổng kết

Có thể nhớ các quy tắc cốt lõi qua hai câu:

- **`try/catch/finally`:** xác định completion của try hoặc catch, sau đó xem finally có hoàn tất bình thường hay có một completion mới thay thế.
- **`try-with-resources`:** resource khởi tạo trái→phải và đóng phải→trái; exception body/khởi tạo được giữ làm primary, lỗi close được suppressed khi đã có primary; nếu chưa có primary thì lỗi close có thể trở thành lỗi chính và thay cả pending return.

Hãy dùng bảng để **dự đoán luồng điều khiển**, rồi kiểm tra thêm **state, tài nguyên, cause, suppressed và quyền sở hữu** để đánh giá API có thật sự an toàn. Trong mã production, tránh `return`/`throw` ngoài ý muốn trong `finally` và ưu tiên `try-with-resources` cho `AutoCloseable`, nhưng vẫn thiết kế transaction/rollback riêng khi thao tác có side effect ngoài JVM.