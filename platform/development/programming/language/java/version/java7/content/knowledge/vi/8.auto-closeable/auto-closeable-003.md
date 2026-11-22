# Phân biệt `AutoCloseable` với `Closeable` trong Java

## 1. Mục tiêu

Trong Java, những đối tượng nắm giữ tài nguyên như luồng I/O, kết nối, phiên làm việc hay một phạm vi tác vụ thường cần được **đóng** sau khi sử dụng. Hai interface hay gặp nhất là:

- `java.lang.AutoCloseable`: hợp đồng tổng quát cho một đối tượng có thể được đóng, đồng thời là nền tảng của `try-with-resources`.
- `java.io.Closeable`: hợp đồng đóng **nguồn hoặc đích dữ liệu**, kế thừa `AutoCloseable` và thu hẹp kiểu checked exception của `close()` về `IOException`.

Hai interface có quan hệ kế thừa nhưng **không hoàn toàn giống nhau**. Sự khác biệt ảnh hưởng đến cách thiết kế API, khai báo `throws`, hành vi khi đóng nhiều lần và lựa chọn kiểu tham chiếu trong `try-with-resources`.

Sau bài này, bạn sẽ:

1. Nhìn đúng quan hệ kiểu: **`Closeable extends AutoCloseable`**, không phải ngược lại.
2. Giải thích vì sao một `try` dùng `Closeable` thường chỉ cần khai báo `IOException`, còn cùng đối tượng qua biến `AutoCloseable` có thể cần `Exception`.
3. Phân biệt **hợp đồng đóng lặp lại** (`idempotence`), và việc một interface có thể hoặc không thể ném checked exception khi đóng.
4. Dùng `try-with-resources` đúng cách cho cả hai và bảo toàn thông tin lỗi bị *suppressed*.
5. Chọn interface phù hợp cho loại tài nguyên thực tế, không dùng kiểu quá rộng chỉ để viết ít code.

**Phiên bản hiện hành:** `Closeable` có từ Java 5 và `AutoCloseable` được đưa vào Java 7 cùng `try-with-resources`. Cả hai **vẫn là API chuẩn được sử dụng trong Java hiện đại**; bài tập kiểm thử trên **Java 21** mà không phụ thuộc JDK cũ hoặc API legacy.

## 2. Bảng so sánh cốt lõi

| Tiêu chí | `AutoCloseable` | `Closeable` |
| --- | --- | --- |
| Package | `java.lang` (được import mặc định) | `java.io` (phải import khi cần) |
| Mục đích | Hợp đồng đóng **tài nguyên nói chung** | Nguồn/đích dữ liệu có thể đóng, điển hình I/O |
| Quan hệ kế thừa | Interface gốc | `extends AutoCloseable` |
| Chữ ký khai báo | `void close() throws Exception` | `void close() throws IOException` |
| Kiểu checked exception khai báo | Rộng: `Exception` | Hẹp hơn: `IOException` |
| Gọi `close()` nhiều lần | **Không bắt buộc** idempotent; được khuyến khích idempotent | Đã đóng thì gọi lại **không có tác dụng** theo hợp đồng |
| Dùng trong `try-with-resources` | Có | Có, vì là subtype của `AutoCloseable` |
| Ví dụ điển hình | Phạm vi tác vụ, resource tùy biến, API quản lý tài nguyên không phải I/O | `InputStream`, `OutputStream`, `Reader`, `Writer` |
| Có bắt buộc `close()` thực sự ném exception? | Không | Không |

**Chú ý:** `throws Exception` là **khả năng được phép khai báo**, không có nghĩa mọi lần đóng đều ném `Exception`. Một lớp triển khai `AutoCloseable` có thể dùng `close()` **không khai báo checked exception**, hoặc khai báo loại hẹp hơn, chẳng hạn `IOException`. Tương tự, lớp triển khai `Closeable` có thể có `close()` không ném checked exception nếu việc đóng không thể thất bại.

### Hai chữ ký quan trọng

~~~java
// Trong java.lang.AutoCloseable:
void close() throws Exception;

// Trong java.io.Closeable:
void close() throws IOException;
~~~

Đây là **chữ ký API minh họa**, không phải file chứa hai phương thức tự đứng độc lập. `IOException` kế thừa `Exception` nên việc `Closeable` thu hẹp tập checked exception là hợp lệ khi ghi đè/hình thành subtype.

## 3. Quan hệ kiểu: `Closeable` là một `AutoCloseable`

Trong mã Java hiện đại:

~~~java
import java.io.Closeable;
import java.io.IOException;

class Sample {
    static void consume(AutoCloseable resource) throws Exception {
        resource.close();
    }

    static void example() throws Exception {
        Closeable input = () -> System.out.println("closed");
        AutoCloseable general = input; // Hợp lệ: upcast
        consume(general);
    }
}
~~~

Đây là một lớp minh họa có thể biên dịch (lời gọi `example()` cần được thực thi từ một phương thức thích hợp). `Closeable` là *functional interface*: biểu thức lambda `() -> ...` cung cấp cách triển khai `close()` trong ví dụ.

Chiều ngược lại **không tự động hợp lệ**:

~~~java
AutoCloseable general = () -> System.out.println("closed");
// Closeable specific = general; // LỖI BIÊN DỊCH: không thể gán tổng quát vào subtype
~~~

Một `AutoCloseable` bất kỳ **không nhất thiết** là `Closeable`. Việc ép kiểu có thể phát sinh `ClassCastException` nếu đối tượng không triển khai `Closeable`; đừng ép kiểu chỉ để cố làm cho chữ ký `throws` ngắn đi.

### Kiểu giao diện ảnh hưởng tới hợp đồng API

Một API chỉ cần đóng được tài nguyên có thể nhận `AutoCloseable`, nhưng khi gọi `close()` qua tham chiếu đó, compiler phải xét khả năng `Exception`. Với API chỉ xử lý nguồn/đích dữ liệu có hợp đồng `Closeable`, nhận `Closeable` giúp biểu diễn rõ hơn bản chất I/O và ngoại lệ đã thu hẹp.

Tuy nhiên, **chọn interface theo khả năng nghiệp vụ**, không chỉ theo loại checked exception. Một đối tượng quản lý giao dịch hoặc phạm vi tác vụ không nên giả vờ là luồng dữ liệu chỉ để có `throws IOException`.

## 4. Khác biệt ở ngoại lệ checked và **kiểu tĩnh của biến**

Ví dụ:

~~~java
static void useIo() throws IOException {
    try (Closeable resource = openIoResource()) {
        process(resource);
    }
}

static void useGeneral() throws Exception {
    try (AutoCloseable resource = openIoResource()) {
        processGeneral(resource);
    }
}
~~~

Đây là **mã minh họa cấu trúc**; `openIoResource`, `process` và `processGeneral` cần được định nghĩa và bảo đảm kiểu, ngoại lệ tương thích. Giả sử hai hàm `process` không ném checked exception khác:

- `try (Closeable resource = ...)` xem chữ ký `close()` là `throws IOException`, nên `throws IOException` có thể đủ.
- `try (AutoCloseable resource = ...)` xem chữ ký `close()` là `throws Exception`, nên `throws IOException` **không đủ** nếu không bắt hoặc xử lý `Exception`.
- Dù `openIoResource()` trả cùng một đối tượng triển khai `Closeable`, **kiểu tĩnh khai báo trong header** vẫn ảnh hưởng đến phân tích ngoại lệ checked khi compiler chèn lời gọi `close()` tự động.

Đó không phải sự khác biệt trong đối tượng runtime: `close()` vẫn được điều phối động đến implementation thật. Sự khác biệt nằm ở **hợp đồng mà trình biên dịch thấy**.

### Cụ thể: lớp tùy biến có `close()` không ném checked exception

~~~java
final class TaskScope implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("scope closed");
    }
}

static void work() {
    try (TaskScope scope = new TaskScope()) {
        System.out.println("working with " + scope.getClass().getSimpleName());
    }
}
~~~

Đây là **mã minh họa phải đặt trong một lớp ngoài phù hợp**, không phải chương trình độc lập. Vì header khai báo tài nguyên với kiểu cụ thể `TaskScope` và `TaskScope.close()` **không khai báo checked exception**, phương thức `work()` không phải thêm `throws Exception` chỉ vì `TaskScope implements AutoCloseable`.

Đừng suy ra rằng **mọi** `try-with-resources` dùng đối tượng `AutoCloseable` bắt buộc phải khai báo `throws Exception`. Điều này tùy **kiểu tĩnh và chữ ký `close()`** mà compiler sử dụng.

## 5. Khác biệt ở việc gọi `close()` nhiều lần

Javadoc quy định:

- Với `Closeable.close()`, nếu đối tượng đã đóng thì **gọi lại không có tác dụng**. Đây là hợp đồng mà implementation cần thực hiện.
- Với `AutoCloseable.close()`, **không bắt buộc** gọi lại có cùng hiệu ứng như lần đầu. Một số implementation có thể có tác dụng phụ rõ ràng khi đóng nhiều lần, dù tài liệu **khuyến khích** viết `close()` idempotent.

Từ *idempotent* trong ngữ cảnh này có nghĩa là: đóng lại một resource đã đóng không tạo ra thao tác thay đổi mới có ý nghĩa. Đừng nhầm với việc các resource khác nhau có cùng trạng thái hay việc gọi `close()` lần đầu chắc chắn thành công.

Ví dụ implementation `Closeable` đơn giản:

~~~java
final class IoResource implements Closeable {
    private boolean closed;

    @Override
    public void close() throws IOException {
        if (closed) {
            return;
        }
        closed = true;
        // Giải phóng tài nguyên đang sở hữu.
    }
}
~~~

Đoạn này minh họa **thành viên lớp**, cần import `java.io.Closeable` và `java.io.IOException`, chưa phải chương trình độc lập. Cách dùng cờ `closed` là một lựa chọn thiết kế; với tài nguyên thật, cần xem việc đóng có đồng bộ, thread-safe hay không và bảo đảm giải phóng đúng handle.

**Đặc biệt:** `AutoCloseable` cho phép non-idempotent không có nghĩa nên cố tình gọi `close()` lặp lại. Trong chương trình thực tế, quản lý **quyền sở hữu** của tài nguyên rõ ràng và để một phạm vi chịu trách nhiệm đóng sẽ ít lỗi hơn.

## 6. Cả hai đều sử dụng được với `try-with-resources`

Điều kiện ngôn ngữ đối với tài nguyên trong header `try-with-resources` là kiểu của biến thuộc `AutoCloseable` hoặc subtype của nó. Do đó:

~~~java
try (Closeable io = openIoResource();
     AutoCloseable scope = openTaskScope()) {
    // Sử dụng cả hai tài nguyên.
}
~~~

Đây là **đoạn minh họa**, các hàm khởi tạo cần được định nghĩa và phải xử lý checked exception phù hợp. `Closeable` không cần thêm phương thức nào mới để dùng `try-with-resources` vì nó đã **extends AutoCloseable**.

Quy tắc `try-with-resources` giống nhau cho cả hai:

1. Khởi tạo các tài nguyên trong header **từ trái sang phải**.
2. Khi hoàn thành, Java đóng tài nguyên đã khởi tạo **theo thứ tự ngược**, ở đây đóng `scope` trước `io`.
3. Nếu một initializer thất bại, những tài nguyên khởi tạo thành công trước đó vẫn được cố gắng đóng.
4. Nếu thân `try` ném và `close()` cũng ném, lỗi thân `try` vẫn là ngoại lệ chính, còn lỗi đóng được gắn vào `getSuppressed()`.
5. Nếu đóng một tài nguyên lỗi, Java vẫn cố đóng các tài nguyên khác còn nằm trong phạm vi quản lý.
6. Một tài nguyên trả về `null` không được gọi `close()`, nhưng dùng `null` trong thân `try` mà không kiểm tra vẫn có thể gây `NullPointerException`.

`try-with-resources` không tự quyết định bạn nên dùng `AutoCloseable` hay `Closeable`; nó sử dụng **hợp đồng `close()` của kiểu tĩnh**, và runtime gọi đúng phương thức trên đối tượng. Không tự động rollback transaction, phục hồi I/O hoặc biến một operation thất bại thành thành công.

### Suppressed exception không phải cause

~~~java
catch (Exception ex) {
    System.err.println("primary=" + ex.getMessage());
    for (Throwable extra : ex.getSuppressed()) {
        System.err.println("suppressed=" + extra.getMessage());
    }
}
~~~

Đây là **đoạn mã trong khối xử lý lỗi**, không phải chương trình độc lập. `getSuppressed()` và `getCause()` là hai API khác nhau. Khi một lỗi công việc đã tồn tại, lỗi từ `close()` thường được **suppressed** để không che mất nguyên nhân ban đầu.

## 7. Chương trình Java hoàn chỉnh: cả hai interface, kiểu tĩnh, đóng lặp, lỗi bị suppress

Tạo file `src/main/java/demo/CloseableComparison.java`:

~~~java
package demo;

import java.io.Closeable;
import java.io.IOException;

public final class CloseableComparison {
    private CloseableComparison() {}

    static final class IoResource implements Closeable {
        private final String name;
        private boolean closed;

        IoResource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            if (!closed) {
                closed = true;
                System.out.println("close:io:" + name);
            }
        }
    }

    static final class TaskScope implements AutoCloseable {
        private boolean closed;

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("close:task");
            }
        }

        boolean isClosed() {
            return closed;
        }
    }

    static final class FailingCleanup implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close:fail");
            throw new IOException("cleanup failed");
        }
    }

    static void useCloseable() throws IOException {
        try (Closeable resource = new IoResource("typed")) {
            System.out.println("body:io:" + resource.getClass().getSimpleName());
        }
    }

    static void useSpecificAutoCloseable() {
        try (TaskScope scope = new TaskScope()) {
            System.out.println("body:task:closed=" + scope.isClosed());
        }
    }

    static void useBroadAutoCloseable() throws Exception {
        try (AutoCloseable resource = new IoResource("widened")) {
            System.out.println("body:auto:" + resource.getClass().getSimpleName());
        }
    }

    static void showSuppressed() {
        try (FailingCleanup cleanup = new FailingCleanup()) {
            System.out.println("body:failure:" + cleanup.getClass().getSimpleName());
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primary:" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed:" + suppressed.getMessage());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        useCloseable();
        useSpecificAutoCloseable();
        useBroadAutoCloseable();

        IoResource reusable = new IoResource("again");
        reusable.close();
        reusable.close();

        showSuppressed();
    }
}
~~~

Từ thư mục chứa `src/`, dùng JDK hỗ trợ `--release 21`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/CloseableComparison.java
java -cp out demo.CloseableComparison
~~~

Kết quả stdout chính xác:

~~~text
body:io:IoResource
close:io:typed
body:task:closed=false
close:task
body:auto:IoResource
close:io:widened
close:io:again
body:failure:FailingCleanup
close:fail
primary:work failed
suppressed:cleanup failed
~~~

### Giải thích từng phần

**`useCloseable()`:** `Closeable resource` có chữ ký `close() throws IOException`, nên phương thức chỉ cần khai báo `throws IOException` (vì thân `try` không có checked exception khác). Nó in tên class thật `IoResource`, rồi tự động đóng và in `close:io:typed`.

**`useSpecificAutoCloseable()`:** `TaskScope` triển khai `AutoCloseable` nhưng `close()` **không ném checked exception**. Hàm `useSpecificAutoCloseable()` vì thế không cần `throws`. Dòng `closed=false` cho biết body chạy trước khi đóng; khi rời `try`, `close()` mới in `close:task`.

**`useBroadAutoCloseable()`:** Runtime vẫn là một `IoResource`, nhưng biến được khai báo theo kiểu **`AutoCloseable`**. Vì chữ ký nhìn thấy là `close() throws Exception`, phương thức khai báo `throws Exception`. Việc đối tượng thực tế là `Closeable` **không tự làm compiler thu hẹp** hợp đồng kiểu tĩnh.

**`reusable.close()` hai lần:** `IoResource` có cờ `closed` và in `close:io:again` đúng **một lần**. Đó là cách ví dụ thực hiện hợp đồng gọi đóng lại không có tác dụng của `Closeable`.

**`showSuppressed()`:** công việc ném `IllegalStateException("work failed")`; khi Java cố đóng `FailingCleanup`, `close()` ném `IOException("cleanup failed")`. Kết quả nhận `primary:work failed` và `suppressed:cleanup failed`, không làm mất lỗi công việc. `FailingCleanup` vẫn là một `AutoCloseable` dù `close()` của nó khai báo kiểu hẹp `IOException`.

Chương trình dùng tài nguyên mô phỏng để kết quả ổn định, không cần mạng, file, thư viện ngoài hay cấu hình hệ thống.

## 8. Bài kiểm tra lỗi biên dịch: cùng đối tượng, khác kiểu tĩnh

Tạo **file riêng** `src/main/java/demo/InvalidNarrowThrows.java`, nằm cùng package và bên cạnh file `CloseableComparison.java`:

~~~java
package demo;

import java.io.Closeable;
import java.io.IOException;

final class InvalidNarrowThrows {
    static void correctlyNarrow() throws IOException {
        try (Closeable resource = new CloseableComparison.IoResource("fine")) {
            resource.toString();
        }
    }

    static void incorrectlyNarrow() throws IOException {
        try (AutoCloseable resource = new CloseableComparison.IoResource("wide")) {
            resource.toString();
        }
    }
}
~~~

Đây là **negative compile test**; dòng `incorrectlyNarrow` cố ý không biên dịch. Biên dịch chương trình đúng trước, rồi biên dịch file minh họa lỗi riêng:

~~~sh
javac --release 21 -encoding UTF-8 -d out src/main/java/demo/CloseableComparison.java
javac --release 21 -encoding UTF-8 -cp out -d out src/main/java/demo/InvalidNarrowThrows.java
~~~

Kết quả dự kiến là lệnh `javac` thứ hai trả mã khác 0; thông báo lỗi trọng tâm:

~~~text
error: unreported exception Exception; must be caught or declared to be thrown
~~~

Lỗi nằm ở **lời gọi `close()` ngầm định** của tài nguyên kiểu `AutoCloseable`, không phải ở `resource.toString()` hoặc ở constructor của `IoResource`. Đường dẫn, số dòng và vị trí dấu `^` trong diagnostic có thể khác.

**Cách sửa hợp lệ:** nếu đây thực chất là tài nguyên I/O, đổi khai báo về `Closeable resource` (và dùng hợp đồng I/O); hoặc để phương thức xử lý/khai báo `Exception` nếu thực sự cần chấp nhận một `AutoCloseable` tổng quát. Không nên dùng unchecked cast chỉ để né việc khai báo ngoại lệ.

### Phân biệt lỗi biên dịch với lỗi runtime

Ở ví dụ này, không có chương trình `InvalidNarrowThrows` được chạy: compiler từ chối trước khi tạo bytecode vì hợp đồng ngoại lệ checked chưa đầy đủ. Điều này khác với tình huống một `close()` thực sự ném `IOException` khi chương trình đang chạy. Lỗi thực tế ở runtime vẫn cần được xử lý, ghi nhận và/hoặc ném lại có chủ đích.

## 9. Nên chọn interface nào trong dự án?

### 9.1. Ưu tiên `Closeable` khi interface mô tả nguồn/đích dữ liệu

Với stream, reader, writer hoặc abstraction nguồn/đích dữ liệu cần giải phóng, `Closeable` có lợi thế:

- Diễn tả rõ **ngữ nghĩa I/O**.
- Giới hạn checked exception khai báo của `close()` về `IOException`.
- Quy định đóng lần nữa không có tác dụng, giúp code gọi giảm rủi ro khi tái dọn dẹp.

Ví dụ các API đang dùng phổ biến: `InputStream`, `OutputStream`, `Reader` và `Writer` thực hiện `Closeable`. Dùng trực tiếp kiểu API phù hợp thay vì luôn đổi biến về `AutoCloseable`.

### 9.2. Dùng `AutoCloseable` cho resource không nhất thiết là luồng I/O

Một phiên làm việc, đối tượng quản lý lock theo phạm vi hoặc một resource gắn với giao dịch có thể cần hành động khi ra khỏi scope mà không phải “nguồn/đích dữ liệu”. `AutoCloseable` diễn đạt hợp đồng chung này.

Tuy nhiên, việc triển khai `AutoCloseable` **không tự quy định** đóng nghĩa là commit, rollback, release lock hay cancel. Mỗi API phải công bố chính xác tác dụng của `close()`. Một số API hạ tầng như JDBC có các resource `AutoCloseable` vì vòng đời của chúng quan trọng nhưng không hoàn toàn giống một stream đơn giản.

### 9.3. Với lớp tự viết, thu hẹp checked exception của `close()`

Nếu thao tác đóng không thể phát sinh checked exception:

~~~java
final class Scope implements AutoCloseable {
    @Override
    public void close() {
        // Dọn dẹp không phát sinh checked exception.
    }
}
~~~

Nếu có thể phát sinh lỗi đóng cụ thể, khai báo đúng loại:

~~~java
final class FileLikeResource implements AutoCloseable {
    @Override
    public void close() throws IOException {
        // Việc đóng có thể ném IOException.
    }
}
~~~

Hai ví dụ trên là các lớp minh họa riêng (cần import `java.io.IOException` ở ví dụ thứ hai). Javadoc `AutoCloseable` **khuyến nghị** implementation khai báo exception cụ thể hoặc không khai báo exception nếu không cần, thay vì giữ `throws Exception` một cách không cần thiết.

Nếu resource là nguồn/đích dữ liệu thật sự, có thể cân nhắc triển khai `Closeable` thay cho `AutoCloseable` để tận dụng hợp đồng I/O/idempotence.

### 9.4. Đừng lạm dụng `InterruptedException` trong `close()`

Javadoc `AutoCloseable` khuyến nghị mạnh mẽ **không** để `close()` ném `InterruptedException`: lỗi đóng có thể bị suppress khi thân `try` đã có lỗi trước đó, trong khi `InterruptedException` có quan hệ đặc biệt với trạng thái interrupt của thread. Nếu resource cần hủy công việc có thể bị ngắt, hãy thiết kế hợp đồng và cách bảo toàn tín hiệu interrupt rõ ràng, thay vì chỉ tuyên bố `throws InterruptedException` cho mọi `close()`.

## 10. Lỗi phổ biến và cách phòng tránh

| Hiểu nhầm hoặc lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “`Closeable` và `AutoCloseable` là hai interface không liên quan” | Bỏ sót khả năng dùng cùng `try-with-resources` | Nhớ `Closeable extends AutoCloseable` |
| “Mọi `AutoCloseable.close()` đều buộc phải `throws Exception`” | API trở nên rộng và khó sử dụng | Override `close()` với kiểu checked cụ thể hoặc không ném checked exception |
| “`AutoCloseable` đảm bảo đóng hai lần an toàn như `Closeable`” | Có thể lặp tác dụng phụ ngoài ý muốn | Không tự đóng trùng; implementation nên idempotent nếu khả thi |
| “`Closeable.close()` được phép ném checked exception bất kỳ” | Không phù hợp hợp đồng Java | Chỉ khai báo `IOException` hoặc subtype checked tương ứng |
| “Chỉ runtime type quyết định `throws` cần khai báo” | Lỗi biên dịch khi biến ở header kiểu `AutoCloseable` | Đọc kiểu tĩnh và chữ ký `close()` tại điểm sử dụng |
| “`try-with-resources` chỉ chấp nhận `Closeable`” | Bỏ qua resource tùy biến không phải I/O | Chấp nhận mọi kiểu là subtype của `AutoCloseable` |
| “`close()` thất bại sẽ che lỗi thân `try`” | Dễ bỏ sót lỗi nguồn và lỗi cleanup | Xem primary exception và `getSuppressed()` |
| “Có `try-with-resources` là có thể quên quyền sở hữu” | Có thể đóng tài nguyên mà nơi khác vẫn cần | Xác định rõ ai mở, ai dùng, ai đóng |
| “`close()` tự rollback hoặc đảm bảo cleanup không thể thất bại” | Sai giả định transaction/khả năng phục hồi | Đọc hợp đồng tài nguyên và xử lý exception riêng |

## 11. Tự luyện và đáp án

**Câu 1.** Một lớp `WriterResource implements Closeable` được truyền vào tham số `AutoCloseable`. Vì sao truyền hợp lệ, và lúc gọi `close()` qua tham số đó phải cân nhắc kiểu checked nào?

**Đáp án:** Vì `Closeable` là subtype của `AutoCloseable`. Với tham số khai báo là `AutoCloseable`, chữ ký nhìn thấy là `close() throws Exception`, nên caller phải xử lý/khai báo `Exception` (trừ khi có cấu trúc xử lý khác phù hợp).

**Câu 2.** `try (TaskScope s = new TaskScope())` dùng một lớp `TaskScope.close()` không khai báo checked exception. Phương thức bao quanh có bắt buộc `throws Exception` không?

**Đáp án:** Không chỉ vì resource triển khai `AutoCloseable`. Compiler sử dụng chữ ký `TaskScope.close()` ở kiểu tĩnh `TaskScope`; nếu thân `try` và initializer cũng không ném checked exception khác, không cần `throws Exception`.

**Câu 3.** Một implementation `AutoCloseable` có hành động phụ khi gọi `close()` hai lần, có trái hợp đồng interface không?

**Đáp án:** Không nhất thiết; `AutoCloseable` không bắt buộc `close()` idempotent. Tuy nhiên, Javadoc khuyến khích implementer làm idempotent và code sử dụng nên tránh đóng nhiều lần ngoài ý muốn.

**Câu 4.** Một implementation `Closeable` làm gì nếu đã đóng rồi nhưng bị gọi `close()` tiếp?

**Đáp án:** Theo hợp đồng `Closeable.close()`, lần gọi sau khi đã đóng **không có tác dụng**. Đây là khác biệt quan trọng so với yêu cầu tối thiểu của `AutoCloseable`.

**Câu 5.** Thân `try` ném `IllegalStateException("work failed")`, `close()` ném `IOException("cleanup failed")`. Ngoại lệ nào được ném chính?

**Đáp án:** Lỗi từ thân `try` là chính; lỗi đóng được gắn trong `getSuppressed()` của ngoại lệ chính, như minh họa bằng stdout ở chương trình chạy được.

**Câu 6.** Viết một API nhận `Closeable` có giúp quản lý kết nối JDBC hoặc một scope tác vụ chung tốt hơn trong mọi trường hợp không?

**Đáp án:** Không. Interface phải thể hiện đúng bản chất và trách nhiệm resource. `Closeable` là hợp đồng nguồn/đích dữ liệu I/O; resource khác có thể phù hợp với `AutoCloseable` hoặc một subtype chuyên biệt hơn.

## 12. Checklist cuối bài

- [ ] Phân biệt đúng package, quan hệ `Closeable extends AutoCloseable` và chữ ký `close()`.
- [ ] Chọn interface theo **ngữ nghĩa resource**, không theo ý muốn né checked exception.
- [ ] Với resource kiểu cụ thể, kiểm tra chính xác `close()` khai báo exception nào; không tự mặc định mọi `AutoCloseable` phải `throws Exception`.
- [ ] Không nhầm **hợp đồng idempotence** của `Closeable` với khuyến nghị (không bắt buộc) của `AutoCloseable`.
- [ ] Dùng `try-with-resources` để đóng tự động và xem `getSuppressed()` khi cleanup cũng thất bại.
- [ ] Giao quyền sở hữu tài nguyên rõ ràng; tránh trả tài nguyên đã đóng hoặc đóng hai lần ngoài ý muốn.
- [ ] Kiểm thử đường đi bình thường, lỗi công việc và lỗi khi đóng.
- [ ] Biên dịch Java 21 với `javac --release 21 -Xlint:all` và đối chiếu stdout, tách file cố ý lỗi biên dịch khỏi chương trình hợp lệ.

**Nguồn tài liệu chính thức, vẫn còn áp dụng:**

- [AutoCloseable — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): `close() throws Exception`, khuyến nghị khai báo ngoại lệ cụ thể, và khác biệt idempotence.
- [Closeable — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Closeable.html): `extends AutoCloseable`, `close() throws IOException`, đóng lại không có tác dụng.
- [Java Language Specification SE 21 `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): yêu cầu kiểu subtype của `AutoCloseable`, thứ tự đóng và suppressed exception.

Các ví dụ dùng API và quy tắc Java vẫn được hỗ trợ hiện nay; không lấy kiến thức đã legacy làm cách triển khai được khuyến nghị.
