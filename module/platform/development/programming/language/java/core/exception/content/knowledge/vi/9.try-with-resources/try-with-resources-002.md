# `AutoCloseable` và `Closeable` trong Java: nền tảng của `try-with-resources`

Một chương trình Java thường làm việc với những tài nguyên phải được kết thúc sử dụng đúng lúc: luồng đọc/ghi tệp, kết nối cơ sở dữ liệu, socket, channel hoặc một phiên làm việc có trạng thái. Garbage collector quản lý bộ nhớ của các đối tượng Java, nhưng **không phải cơ chế thay thế cho việc đóng tài nguyên kịp thời**. Để biểu đạt khả năng “đóng được”, Java có interface `java.lang.AutoCloseable` và interface chuyên biệt hơn `java.io.Closeable`.

Khi một tài nguyên được khai báo trong phần đầu của câu lệnh `try-with-resources`, Java tự động gọi phương thức `close()` của tài nguyên đó lúc rời khối. Cơ chế này giúp giảm lỗi quên đóng, xử lý thứ tự đóng nhiều tài nguyên và bảo toàn thông tin khi cả thao tác chính lẫn thao tác đóng cùng thất bại.

**Phạm vi bài học:** hiểu chính xác mối quan hệ `AutoCloseable` – `Closeable`, chữ ký `close()`, quy tắc checked exception, hợp đồng đóng nhiều lần, cách sử dụng với `try-with-resources`, cách tự viết lớp tài nguyên và những lỗi thiết kế cần tránh. Các ví dụ hoàn chỉnh dùng **Java 17+**, không cần file hay dịch vụ bên ngoài.

## 1. Hai interface liên hệ với nhau thế nào?

`AutoCloseable` có trong `java.lang` (không cần import). `Closeable` có trong `java.io` và **kế thừa `AutoCloseable`**:

```java
public interface AutoCloseable {
    void close() throws Exception;
}

public interface Closeable extends AutoCloseable {
    @Override
    void close() throws IOException;
}
```

Đây là **bản lược giản chữ ký API để học**, không phải mã nguồn đầy đủ của JDK; `IOException` nằm trong `java.io`. Interface con `Closeable` khai báo lại phương thức với kiểu checked exception **hẹp hơn**: `IOException` là lớp con của `Exception`.

```text
AutoCloseable  (java.lang)
  └─ close() throws Exception
       ▲
       │ extends
Closeable      (java.io)
  └─ close() throws IOException
       ▲
       ├─ InputStream / OutputStream
       ├─ Reader / Writer
       └─ nhiều kiểu tài nguyên I/O khác
```

Không phải mọi đối tượng `AutoCloseable` đều là `Closeable`. Ví dụ, nhiều API JDBC như `java.sql.Connection` triển khai `AutoCloseable` với lỗi đặc thù `SQLException`; chúng không bắt buộc phải triển khai `java.io.Closeable`.

Bất kỳ lớp nào triển khai `Closeable` cũng là `AutoCloseable`, nên đều có thể xuất hiện trong phần khai báo tài nguyên của `try-with-resources`.

## 2. So sánh hợp đồng chính

| Điểm so sánh | `AutoCloseable` | `Closeable` |
| --- | --- | --- |
| Gói | `java.lang` | `java.io` |
| Quan hệ | Interface tổng quát cho tài nguyên có thể đóng | `extends AutoCloseable` |
| Chữ ký `close()` | `void close() throws Exception` | `void close() throws IOException` |
| Ngữ cảnh điển hình | I/O, JDBC, channel, giao dịch/phạm vi tự quản lý, đối tượng cần cleanup | Chủ yếu luồng và nguồn/đích dữ liệu I/O |
| Gọi `close()` nhiều lần | Không bắt buộc phải idempotent; tài liệu **khuyến khích** làm idempotent | Hợp đồng: đã đóng thì gọi lại **không có tác dụng** |
| Dùng với `try-with-resources` | Có | Có, vì kế thừa `AutoCloseable` |
| Checked exception nhìn từ biến kiểu interface | `Exception` | `IOException` |
| Có thể override `close()` với ít lỗi hơn? | Có, ví dụ không `throws` gì | Có, ví dụ không `throws` gì |

**Idempotent** đối với `close()` ở đây nghĩa là gọi lại sau khi tài nguyên đã đóng không tạo thêm hiệu ứng quan sát được theo hợp đồng đóng. `Closeable.close()` được Javadoc yêu cầu nếu stream đã đóng thì lời gọi tiếp theo không có tác dụng. Với `AutoCloseable` thuần túy, điều đó **không phải yêu cầu bắt buộc**, dù cách triển khai an toàn thường vẫn nên làm.

Cả hai interface **không hứa** rằng mọi thao tác `close()` luôn thành công. Ngay cả khi đóng thất bại, trách nhiệm về trạng thái và quyền sở hữu tài nguyên vẫn phải được thiết kế rõ ràng.

## 3. Vì sao `try-with-resources` cần `AutoCloseable`?

Cấu trúc căn bản:

```java
try (Resource resource = createResource()) {
    useResource(resource);
}
```

Đây là **mẫu minh họa**, giả định `Resource implements AutoCloseable` và các hàm liên quan đã được định nghĩa. Quy trình khi chạy:

1. Java đánh giá biểu thức `createResource()` để khởi tạo biến tài nguyên trong dấu `(...)`.
2. Nếu khởi tạo thành công, Java thực thi thân `try`.
3. Khi rời thân `try` theo đường Java thông thường — kết thúc bình thường, `return`, `throw`, `break` hoặc `continue` phù hợp — Java gọi `resource.close()`.
4. Sau bước đóng, câu lệnh `try-with-resources` hoàn tất; nếu có `catch` hoặc `finally` cùng cấu trúc, chúng được thực hiện theo quy tắc riêng, **sau khi việc đóng tự động đã được tiến hành**.
5. Nếu một lỗi phát sinh lúc đóng, Java xử lý ngoại lệ chính và `suppressed exceptions` theo quy tắc đặc biệt.

Khác với lời gọi `close()` thủ công, lập trình viên không cần lặp cùng logic giải phóng trong từng nhánh `catch`, `return` hay cuối phương thức.

**Lưu ý:** `AutoCloseable` là điều kiện về **kiểu** để một đối tượng có thể được đưa vào danh sách tài nguyên. Nó không tự có cơ chế đóng khi đối tượng bị thu gom rác. Tài nguyên đặt ngoài `try-with-resources` vẫn cần được quản lý theo hợp đồng API.

## 4. Ví dụ Java 17+: tự tạo một `AutoCloseable` đơn giản

Lưu thành `SimpleAutoCloseableDemo.java`:

```java
public class SimpleAutoCloseableDemo {
    static class Session implements AutoCloseable {
        private boolean closed;

        Session() {
            System.out.println("open session");
        }

        void work() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            System.out.println("session work");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("close session");
            }
        }
    }

    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.work();
        }
        System.out.println("after try");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 SimpleAutoCloseableDemo.java
java SimpleAutoCloseableDemo
```

Kết quả xác định:

```text
open session
session work
close session
after try
```

`Session implements AutoCloseable`, vì vậy có thể khai báo trong `try (...)`. Trình biên dịch tự tạo logic tương đương với một khối `finally` thích hợp để gọi `close()` khi kết thúc. Chữ ký thực tế `Session.close()` **không khai báo checked exception**, nên `main()` không cần `throws Exception` chỉ vì tự động đóng `Session`.

Ví dụ chủ động đánh dấu `closed = true` và chỉ in khi đóng lần đầu. Điều đó làm `close()` idempotent, dù interface `AutoCloseable` không bắt buộc. Phương thức `work()` kiểm tra trạng thái để từ chối dùng tài nguyên sau khi đóng.

Đừng tự gọi `session.close()` thêm một lần trong thân `try` chỉ để “chắc ăn”. Nếu đã khai báo ở phần đầu `try-with-resources`, Java sẽ gọi nó khi rời khối; gọi thủ công có thể dẫn tới double-close ở lớp triển khai không idempotent.

## 5. `throws Exception` và `throws IOException` ảnh hưởng compiler thế nào?

Khác biệt chữ ký `close()` liên quan trực tiếp tới cơ chế checked exception:

- `AutoCloseable.close()` được khai báo `throws Exception`. Nếu tài nguyên được nhìn qua **kiểu tĩnh `AutoCloseable`**, việc đóng tự động có thể gây `Exception` checked; người gọi phải xử lý hoặc khai báo phù hợp.
- `Closeable.close()` được khai báo `throws IOException`. Nếu tài nguyên được nhìn qua **kiểu tĩnh `Closeable`**, loại checked exception từ việc đóng hẹp hơn.
- Một **lớp triển khai cụ thể** được phép override `close()` mà **không ném checked exception**. Khi `try-with-resources` dùng chính kiểu cụ thể đó, nghĩa vụ compile-time liên quan riêng tới việc đóng có thể biến mất.
- Ngoại lệ từ **thân `try` hoặc lời gọi khởi tạo tài nguyên** vẫn được kiểm tra riêng. Chữ ký `close()` không xóa nghĩa vụ đối với những ngoại lệ đó.

### Chương trình Java 17+: cùng một hành động, hai hợp đồng `close()`

Lưu thành `CloseContractDemo.java`:

```java
import java.io.Closeable;
import java.io.IOException;

public class CloseContractDemo {
    static class GeneralResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            System.out.println("general-close");
        }
    }

    static class IoResource implements Closeable {
        @Override
        public void close() throws IOException {
            System.out.println("io-close");
        }
    }

    static void usingGeneral() throws Exception {
        try (AutoCloseable resource = new GeneralResource()) {
            System.out.println("general-work");
        }
    }

    static void usingIo() throws IOException {
        try (Closeable resource = new IoResource()) {
            System.out.println("io-work");
        }
    }

    public static void main(String[] args) throws Exception {
        usingGeneral();
        usingIo();
    }
}
```

```bash
javac -encoding UTF-8 CloseContractDemo.java
java CloseContractDemo
```

Kết quả:

```text
general-work
general-close
io-work
io-close
```

`usingGeneral()` khai báo `throws Exception` do tham chiếu `AutoCloseable` có chữ ký `close() throws Exception`. `usingIo()` chỉ cần `throws IOException` vì `Closeable.close()` thu hẹp hợp đồng. Trong demo, cả hai thao tác `close()` đều không thực sự ném lỗi, nhưng **khả năng ném theo chữ ký** vẫn được xét lúc biên dịch.

Sự khác nhau thể hiện rõ khi dùng lớp tự viết:

```java
static class QuietResource implements AutoCloseable {
    @Override
    public void close() { }
}

static void useQuiet() {
    try (QuietResource resource = new QuietResource()) {
        System.out.println("work");
    }
}
```

Đây là **đoạn phương thức/lớp lồng minh họa**, không phải tệp chạy độc lập. `useQuiet()` không cần `throws Exception` chỉ vì `QuietResource` implements `AutoCloseable`: compiler biết `QuietResource.close()` cụ thể không khai báo checked exception.

**Lỗi thiết kế thường gặp:** mọi nơi đều lưu resource qua biến `AutoCloseable` dù tài nguyên thật có chữ ký `close()` hẹp hơn. Điều đó có thể buộc khai báo/bắt `Exception` rộng không cần thiết. Nếu hợp đồng thực tế là I/O, dùng `Closeable` hoặc kiểu cụ thể thường chính xác hơn.

## 6. Tự triển khai `Closeable` khi nào hợp lý?

`Closeable` phù hợp với lớp đại diện cho nguồn hoặc đích dữ liệu có khả năng đóng và có thể thất bại vì lỗi I/O:

```java
import java.io.Closeable;
import java.io.IOException;

class TextChannel implements Closeable {
    private boolean closed;

    void send(String text) throws IOException {
        if (closed) {
            throw new IOException("channel closed");
        }
        System.out.println(text);
    }

    @Override
    public void close() throws IOException {
        if (!closed) {
            closed = true;
            // Ở ứng dụng thật: giải phóng stream/socket liên quan.
        }
    }
}
```

Đây là **lớp minh họa hợp lệ**, không có `main` độc lập. `TextChannel` mô hình hóa nguồn/đích dữ liệu và trả lỗi I/O dưới dạng `IOException`. Trạng thái `closed` ngăn sử dụng sai sau khi đóng. Lời gọi `close()` lặp lại không tạo hành động mới, đúng tinh thần hợp đồng `Closeable`.

Không phải mọi đối tượng đóng được đều là I/O. Nếu lớp đại diện cho một transaction scope hoặc một cấu trúc tài nguyên riêng, `AutoCloseable` có thể phù hợp hơn. Nếu muốn hợp đồng đóng ném `SQLException`, không thể chọn `Closeable.close() throws SQLException` vì `SQLException` không phải lớp con của `IOException`. `AutoCloseable` cho phép thiết kế ngoại lệ chuyên biệt đó.

## 7. Ví dụ `Closeable` trong thư viện chuẩn: `BufferedReader`

Các loại như `InputStream`, `OutputStream`, `Reader` và `Writer` triển khai `Closeable`. Vì vậy, có thể dùng trực tiếp với `try-with-resources`. Để có ví dụ độc lập không cần tệp trên đĩa, dùng `StringReader` làm nguồn ký tự rồi bọc bằng `BufferedReader`.

Lưu thành `ReaderDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ReaderDemo {
    public static void main(String[] args) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader("alpha\nbeta"))) {
            System.out.println("line1=" + reader.readLine());
            System.out.println("line2=" + reader.readLine());
        }
        System.out.println("reader closed");
    }
}
```

```bash
javac -encoding UTF-8 ReaderDemo.java
java ReaderDemo
```

Kết quả:

```text
line1=alpha
line2=beta
reader closed
```

Trong ví dụ này, `BufferedReader` là **tài nguyên sở hữu wrapper**, được khai báo ở đầu `try-with-resources`. Khi `BufferedReader.close()` chạy, nó cũng đóng `StringReader` được bọc theo hợp đồng của lớp đọc. Vì vậy không cần khai báo thêm một tài nguyên `StringReader` riêng chỉ để đóng lại cùng underlying reader.

Điều đó không có nghĩa mọi lớp wrapper trong Java đều tự động chịu trách nhiệm đóng tài nguyên được truyền vào. Khi dùng thư viện bên ngoài, **đọc hợp đồng ownership của API** để biết wrapper có đóng đối tượng gốc hay không.

Với tệp thật, có thể dùng `Files.newBufferedReader(path)` hoặc `Files.newInputStream(path)` trong `try-with-resources`; các API này có thể ném `IOException` khi mở, đọc và đóng. Không nên dùng nguồn tệp phụ thuộc máy trong ví dụ học thuật có stdout cố định.

## 8. Nhiều tài nguyên: khởi tạo từ trái sang phải, đóng ngược lại

Với danh sách nhiều tài nguyên:

```java
try (
    Resource first = new Resource("A");
    Resource second = new Resource("B");
    Resource third = new Resource("C")
) {
    doWork();
}
```

Đây là mẫu minh họa, giả định các kiểu đã tồn tại. Java **khởi tạo A → B → C**, chạy thân `try`, sau đó **đóng C → B → A**. Thứ tự LIFO này hữu ích khi tài nguyên tạo sau phụ thuộc tài nguyên tạo trước. Có thể đặt dấu `;` cuối cùng trong danh sách tài nguyên, nhưng không bắt buộc.

Lưu thành `CloseOrderDemo.java`:

```java
public class CloseOrderDemo {
    static class Step implements AutoCloseable {
        private final String name;

        Step(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Step a = new Step("A");
             Step b = new Step("B");
             Step c = new Step("C")) {
            System.out.println("body");
        }
        System.out.println("after");
    }
}
```

```bash
javac -encoding UTF-8 CloseOrderDemo.java
java CloseOrderDemo
```

Kết quả:

```text
open A
open B
open C
body
close C
close B
close A
after
```

Từng biến tài nguyên được khai báo trong phần `try (...)` là biến chỉ gán một lần trong phạm vi đó; không được gán lại nó trong thân `try`. Sau khi câu lệnh `try-with-resources` hoàn tất, những biến khai báo trực tiếp trong danh sách tài nguyên không còn nằm trong phạm vi sử dụng phía sau.

## 9. Nếu mở tài nguyên thứ hai thất bại thì tài nguyên thứ nhất ra sao?

Đặc tả Java bảo đảm những tài nguyên **đã khởi tạo thành công** trong cùng `try-with-resources` được đóng nếu một tài nguyên phía sau **không thể khởi tạo**. Không cần vào thân `try` để cơ chế đóng bắt đầu.

Lưu thành `FailedOpenDemo.java`:

```java
import java.io.IOException;

public class FailedOpenDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name, boolean fail) throws IOException {
            this.name = name;
            System.out.println("init " + name);
            if (fail) {
                throw new IOException("open " + name + " failed");
            }
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource a = new Resource("A", false);
             Resource b = new Resource("B", true)) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 FailedOpenDemo.java
java FailedOpenDemo
```

Kết quả:

```text
init A
init B
close A
caught=open B failed
```

A được khởi tạo xong nên được đóng. B ném ngoại lệ ngay trong constructor trước khi trở thành một tài nguyên được khởi tạo thành công trong `try-with-resources`, vì vậy Java **không có đối tượng B đã nhận được để gọi `close()` tự động**. Thân `try` không chạy.

**Giới hạn quan trọng:** nếu constructor của một tài nguyên tạo ra một tài nguyên nội bộ rồi thất bại trước khi trả về đối tượng hoàn chỉnh, chính constructor/factory đó phải có biện pháp dọn dẹp những phần đã cấp phát. `try-with-resources` ở bên ngoài chỉ tự động đóng được các resource đã khởi tạo thành công và được quản lý trong danh sách.

## 10. Ngoại lệ chính và `suppressed exceptions`

Một lợi ích đặc biệt của `try-with-resources` là giữ dấu vết lỗi khi **cả thân `try` lẫn `close()`** cùng thất bại.

- Nếu thân `try` ném ngoại lệ `E`, sau đó `close()` ném ngoại lệ `C`, Java tiếp tục ném **E là ngoại lệ chính**, đồng thời gắn **C vào `E.getSuppressed()`**.
- Nếu thân `try` hoàn tất bình thường nhưng `close()` ném `C`, thì `C` có thể trở thành ngoại lệ chính đi ra ngoài.
- Nếu có nhiều tài nguyên và nhiều `close()` thất bại, Java vẫn cố đóng các tài nguyên còn lại, và những lỗi bổ sung được ghi lại trong danh sách `suppressed` theo cơ chế của JLS.
- `getSuppressed()` **khác `getCause()`**. Cause mô tả quan hệ nguyên nhân giữa các ngoại lệ; suppressed ghi các ngoại lệ bổ sung bị giữ lại khi xử lý một ngoại lệ chính.

### Chương trình Java 17+: hai lỗi `close()` đi kèm một lỗi ở thân `try`

Lưu thành `SuppressedDemo.java`:

```java
public class SuppressedDemo {
    static class Faulty implements AutoCloseable {
        private final String name;

        Faulty(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
            throw new IllegalStateException("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (Faulty a = new Faulty("A");
             Faulty b = new Faulty("B")) {
            System.out.println("body");
            throw new IllegalArgumentException("work failed");
        } catch (Exception ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("count=" + ex.getSuppressed().length);
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
```

Kết quả:

```text
open A
open B
body
close B
close A
primary=work failed
count=2
suppressed=close B failed
suppressed=close A failed
```

Cả hai tài nguyên đều được yêu cầu đóng theo thứ tự B rồi A. Lỗi từ thân `try` vẫn là `IllegalArgumentException("work failed")` chính; hai lỗi đóng được đính kèm theo thứ tự chúng xảy ra. Không có lần gọi `catch` độc lập cho từng ngoại lệ suppressed.

Nếu bỏ câu lệnh `throw new IllegalArgumentException("work failed")` trong thân `try`, lỗi đóng B sẽ trở thành ngoại lệ chính và lỗi đóng A sẽ bị suppress vào lỗi B. Đây là trường hợp **thân `try` thành công nhưng cleanup thất bại**.

Đừng che giấu lỗi đóng bằng một `catch (Exception ex) { }` rỗng. Trong hệ thống thực, tùy mức nghiêm trọng, ứng dụng cần lưu cả ngoại lệ chính và những suppressed errors để điều tra.

## 11. Thứ tự `catch` và `finally` khi dùng `try-with-resources`

Có thể thêm `catch` và `finally` sau một câu lệnh `try-with-resources`:

```java
try (Resource resource = openResource()) {
    useResource(resource);
} catch (IOException ex) {
    handleIoFailure(ex);
} finally {
    finishOperation();
}
```

Đây là **mẫu cú pháp**; các tên `Resource` và phương thức phải được định nghĩa với chữ ký phù hợp. Quy tắc thứ tự:

1. Khởi tạo tài nguyên.
2. Chạy thân `try` nếu khởi tạo thành công.
3. Tự động đóng những tài nguyên đã khởi tạo, theo thứ tự ngược.
4. Chọn nhánh `catch` đầu tiên phù hợp nếu có ngoại lệ đang được ném.
5. Thực hiện `finally` nếu có, trước khi hoàn tất chuyển quyền điều khiển.

Nếu lỗi `IOException` xảy ra **ngay khi đóng** mà thân `try` không ném lỗi, `catch (IOException ex)` vẫn có thể nhận ngoại lệ này. Nếu thân `try` ném `IllegalStateException`, còn `close()` ném `IOException` bị suppress, `catch (IOException)` **không** được chọn chỉ vì suppressed exception.

`finally` thông thường **không thay thế** cơ chế đóng tự động. Cách quản lý resource hợp lý thường là cho `try-with-resources` chịu trách nhiệm đóng, còn `finally` thực hiện các bước cuối không thuộc việc đóng cùng resource đó.

## 12. Dùng lại biến `final` hoặc *effectively final* từ Java 9

Có hai cách đặt tài nguyên vào danh sách:

**Khai báo tài nguyên tại `try`:**

```java
try (MyResource resource = new MyResource()) {
    use(resource);
}
```

**Dùng tham chiếu đến biến đã tồn tại (Java 9+):**

```java
MyResource resource = new MyResource();
try (resource) {
    use(resource);
}
```

Hai đoạn là **mẫu minh họa** với `MyResource implements AutoCloseable` và `use(...)` đã định nghĩa. Ở cách thứ hai, biến `resource` phải được gán và là `final` hoặc **effectively final**: không bị gán lại sau lần gán ban đầu.

Ví dụ sai nếu cố gán lại trước khối:

```java
MyResource resource = new MyResource();
resource = new MyResource();
try (resource) {       // Compile error: biến không effectively final.
    use(resource);
}
```

Đây là **ví dụ cố ý không biên dịch**. Trong trường hợp mã chạy được, sau khi khối `try (resource)` kết thúc, tên biến `resource` bên ngoài có thể vẫn còn trong phạm vi, nhưng **đối tượng đã được gọi `close()`**. Việc biến còn tham chiếu tới đối tượng không có nghĩa nó còn dùng an toàn.

Lưu ý **ownership:** một tài nguyên chỉ nên được đóng ở nơi chịu trách nhiệm sở hữu vòng đời. Dùng `try (existingResource)` có nghĩa đoạn mã này **đang nhận trách nhiệm đóng** đối tượng khi ra khỏi khối. Nếu tài nguyên đó phải tiếp tục được chủ sở hữu khác sử dụng, không nên tùy tiện đưa vào `try-with-resources`.

Ngoài ra Java 10+ cho phép dùng `var` khi khai báo resource, ví dụ `try (var resource = factory()) { ... }`, nếu phép suy luận kiểu hợp lệ. Dùng `var` có thể bảo toàn kiểu cụ thể của tài nguyên, do đó giúp compiler suy ra đúng kiểu checked exception từ `close()`.

## 13. Tài nguyên `null` và các trường hợp đặc biệt

Nếu một biến tài nguyên hợp lệ được khởi tạo thành `null`, Java **không gọi `close()` cho giá trị `null`**:

```java
try (MyResource resource = null) {
    System.out.println("body");
}
```

Đây là đoạn minh họa khi `MyResource implements AutoCloseable`. Nó không ném `NullPointerException` chỉ vì resource bằng `null`; nhưng nếu thân `try` tự gọi `resource.someMethod()` thì vẫn có thể phát sinh NPE theo quy tắc bình thường.

Dùng resource `null` hiếm khi là cách thiết kế tốt; nó có thể che một lỗi khởi tạo. Nếu tài nguyên là tùy chọn, nên thiết kế điều kiện và vòng đời rõ ràng.

**Không lạm dụng suy luận rằng “mọi đối tượng có phương thức `close()` đều dùng được trong `try-with-resources`”.** Java yêu cầu kiểu của resource là lớp/interface gán được cho `AutoCloseable`. Một lớp tự tạo có `void close()` nhưng **không implements `AutoCloseable`** sẽ bị từ chối làm resource.

Ví dụ cố ý không biên dịch:

```java
class FakeResource {
    void close() { }
}

class InvalidResourceDemo {
    void run() {
        try (FakeResource resource = new FakeResource()) {
            System.out.println("work");
        }
    }
}
```

Để sửa, triển khai `AutoCloseable` hoặc `Closeable` thích hợp rồi override `close()` với hợp đồng đúng.

## 14. Các nguyên tắc triển khai `close()` an toàn

Khi tự thiết kế lớp tài nguyên, cần quan tâm nhiều hơn một câu lệnh `implements AutoCloseable`.

### 14.1. Bảo đảm cleanup thực sự xảy ra

`close()` phải thực hiện việc giải phóng tài nguyên theo hợp đồng: đóng file handle, hủy đăng ký listener, kết thúc phiên sử dụng hoặc hoàn trả tài nguyên được cấp phát. **Đừng tạo một `close()` rỗng để khiến kiểu dữ liệu đi qua compiler** nếu đối tượng thực sự sở hữu tài nguyên cần dọn dẹp.

Nếu cần nhiều bước dọn dẹp, phải quyết định thứ tự và cách giữ thông tin lỗi. Một bước lỗi không nhất thiết được phép làm bỏ qua mọi bước còn lại.

### 14.2. Đánh dấu trạng thái đóng và tránh đóng lặp

Mặc dù `AutoCloseable` không bắt buộc idempotent, Javadoc khuyến khích làm thế. `Closeable` có yêu cầu rõ ràng rằng đóng lại một stream đã đóng không có hiệu ứng.

Mẫu đơn giản:

```java
@Override
public void close() {
    if (closed) {
        return;
    }
    closed = true;
    releaseOwnedResources();
}
```

Đây là **mẫu thiết kế**, giả định có trường `closed` và hàm `releaseOwnedResources()` phù hợp. Đánh dấu trước cleanup giúp giảm rủi ro tái nhập hay đóng hai lần trong một số lớp tài nguyên; nhưng cần thiết kế kỹ nếu cleanup có khả năng thất bại giữa chừng. Với tài nguyên có vòng đời phức tạp, một cờ boolean có thể chưa đủ để mô tả trạng thái đang đóng, đóng thất bại, hoặc tính an toàn đa luồng.

### 14.3. Không biến `close()` thành điểm làm mất ngoại lệ quan trọng

Nếu `close()` có khả năng ném checked exception, nên khai báo **kiểu hẹp có ý nghĩa** hoặc không khai báo checked exception nếu không thể thất bại. `AutoCloseable` cho phép `throws Exception`, nhưng không nên lạm dụng điều đó để trả bất kỳ lỗi nào không liên quan tới nhiệm vụ đóng.

Theo Javadoc `AutoCloseable`, tránh thiết kế `close()` ném `InterruptedException`: khi nó bị suppress do một lỗi chính khác, việc xử lý trạng thái interrupt có thể trở nên khó đoán. Nếu cleanup có thể bị ngắt, cần hợp đồng và cách duy trì tín hiệu hủy phù hợp.

### 14.4. Trách nhiệm đóng thuộc về ai?

Các thư viện thường có nhiều tầng wrapper. Nếu một wrapper sở hữu stream/kết nối gốc, việc đóng wrapper **có thể** đóng stream/kết nối gốc. Nhưng không thể mặc định điều đó cho mọi thư viện. Đọc tài liệu lớp cụ thể trước khi cho nhiều tầng cùng sở hữu quyền đóng.

Cần tránh:
- Hai thành phần đều nhận “quyền sở hữu” và đóng cùng một đối tượng không idempotent.
- Trả ra ngoài một đối tượng tài nguyên đã bị đóng trong phạm vi `try-with-resources`.
- Đưa một đối tượng dùng chung vào `try-with-resources` của một lời gọi nhỏ, làm người dùng khác nhận tài nguyên đã đóng.
- Dựa vào finalizer, garbage collector hay kết thúc JVM thay cho cleanup đúng lúc.

## 15. Khi nào không cần `try-with-resources`?

Không phải mọi đối tượng implements `AutoCloseable` đều luôn thực sự nắm tài nguyên bên ngoài. Một số API dùng chung interface vì có cả trường hợp cần đóng và không cần đóng.

Ví dụ, `java.util.stream.Stream` có liên hệ với `AutoCloseable` qua `BaseStream`. Stream được tạo từ nguồn I/O như `Files.lines(path)` cần được đóng theo hợp đồng tài nguyên. Nhưng một stream thuần trong bộ nhớ, chẳng hạn `List.of(1, 2, 3).stream()`, thường không sở hữu file handle nên không cần thiết phải bọc `try-with-resources` cho riêng nó.

Ngược lại, `Connection`, `PreparedStatement`, `ResultSet`, `BufferedReader` hoặc file stream trong các API thích hợp thường có tài nguyên cần giải phóng. Ngay cả khi tài nguyên không ném checked exception khi đóng, `try-with-resources` vẫn có thể là cách rõ ràng để xác định vòng đời.

**Quy tắc chọn:** không phải “hễ implements AutoCloseable thì bọc mọi lúc”, mà là “khi mã hiện tại có trách nhiệm đóng tài nguyên này và muốn bảo đảm cleanup theo luồng Java thông thường, ưu tiên `try-with-resources`”.

## 16. Những lỗi phổ biến

| Lỗi hoặc hiểu sai | Thực tế và cách sửa |
| --- | --- |
| “`Closeable` là interface hoàn toàn tách rời `AutoCloseable`.” | Sai; `Closeable extends AutoCloseable`. |
| “Hai phương thức `close()` đều khai báo `throws Exception`.” | Sai; `Closeable.close() throws IOException`. |
| “Một lớp có phương thức tên `close` thì tự động dùng được với `try-with-resources`.” | Sai; kiểu resource phải triển khai `AutoCloseable` trực tiếp hoặc gián tiếp. |
| “`AutoCloseable.close()` bắt buộc idempotent.” | Sai; chỉ được khuyến khích. `Closeable.close()` có hợp đồng gọi lại không tác dụng. |
| “Tài nguyên thứ hai mở lỗi thì tài nguyên thứ nhất bị quên.” | Sai; Java tự đóng các tài nguyên trước đó đã khởi tạo thành công. |
| “Đóng theo thứ tự A → B → C vì đã khai báo như thế.” | Sai; đóng C → B → A. |
| “`catch` chạy trước khi đóng tài nguyên.” | Sai; đóng tự động được thực hiện trước `catch`/`finally` của cùng `try-with-resources`. |
| “Lỗi `close()` luôn ghi đè lỗi trong thân `try`.” | Sai; khi đã có lỗi chính, lỗi đóng thường được lưu trong `getSuppressed()`. |
| “Lỗi bị suppress sẽ tự kích hoạt một `catch` riêng.” | Sai; chọn `catch` dựa trên ngoại lệ chính được ném. |
| “Biến còn trong scope tức là resource vẫn mở.” | Sai; tài nguyên có thể đã được đóng khi ra khỏi khối. |
| “`try-with-resources` bảo đảm `close()` chạy cả khi JVM bị kill.” | Không; nó dựa vào việc quyền điều khiển còn đi qua cơ chế Java. |
| “Không cần đọc hợp đồng wrapper vì Java biết tự đóng mọi thành phần liên quan.” | Không; Java đóng các resource được đăng ký; quan hệ sở hữu bên trong wrapper là hợp đồng API. |
| “Chỉ cần bắt `IOException` cho mọi `AutoCloseable`.” | Không; kiểu checked exception phụ thuộc chữ ký `close()` của kiểu tài nguyên và hoạt động trong thân. |

## 17. Quy trình áp dụng trong code review

Khi gặp một đối tượng có `close()`, kiểm tra theo thứ tự:

1. **Kiểu tài nguyên:** có implements `AutoCloseable` không? Có phải `Closeable` hoặc lớp chuyên biệt có `close()` hẹp hơn không?
2. **Ownership:** phương thức hiện tại có sở hữu và chịu trách nhiệm kết thúc vòng đời đối tượng không?
3. **Cách sử dụng:** có thể khai báo resource ngay trong `try (...)`, hoặc dùng một biến `final`/effectively final đã tồn tại từ Java 9 không?
4. **Ngoại lệ khi mở, khi dùng, khi đóng:** API công bố những kiểu checked nào? Cần `catch` tại chỗ hay `throws` lên tầng ngoài?
5. **Thứ tự phụ thuộc:** nếu nhiều tài nguyên, thứ tự khởi tạo và đóng ngược có đúng với quan hệ wrapper không?
6. **Khi thất bại:** có giữ ngoại lệ chính và `getSuppressed()` không? Có làm mất `cause` khi dịch lỗi không?
7. **Tính idempotent và tái sử dụng:** tài nguyên có được dùng sau khi đóng không, có khả năng double-close không?
8. **Khả năng phục hồi:** nếu cleanup thất bại, hệ thống có chính sách ghi nhận, hủy thao tác hoặc dừng dịch vụ phù hợp không?

Một cấu trúc thông thường đáng ưu tiên:

```java
try (SomeCloseable resource = open()) {
    return process(resource);
} catch (IOException ex) {
    throw new DataAccessException("Cannot process resource", ex);
}
```

Đây là **mẫu minh họa không độc lập**, giả định `SomeCloseable implements Closeable`, `open()`/`process(...)` có chữ ký thích hợp và `DataAccessException` là loại ngoại lệ có constructor nhận `cause`. Tài nguyên được đóng **trước khi nhánh `catch` cùng cấu trúc xử lý lỗi**. Bọc lại ngoại lệ giúp tầng trên nhận hợp đồng có ý nghĩa, đồng thời giữ lỗi gốc.

Nếu `process(resource)` trả về một đối tượng vẫn cần dùng tài nguyên sau khi phương thức kết thúc (ví dụ stream lười hoặc iterator trực tiếp phụ thuộc file), việc đóng ngay trước `return` có thể làm kết quả không sử dụng được. Khi đó phải thiết kế lại ownership và vòng đời thay vì áp dụng mẫu máy móc.

## 18. Tự kiểm tra

**Câu 1.** `Closeable` và `AutoCloseable` có quan hệ kế thừa thế nào?  
`Closeable extends AutoCloseable`. Mọi `Closeable` đều dùng được với `try-with-resources`.

**Câu 2.** Chữ ký `close()` trên hai interface khác nhau ở đâu?  
`AutoCloseable.close() throws Exception`; `Closeable.close() throws IOException`.

**Câu 3.** Vì sao `try (AutoCloseable r = ...)` có thể cần `throws Exception` dù object thật đóng không ném lỗi?  
Do compile-time dựa vào **kiểu tĩnh** và chữ ký `AutoCloseable.close()`, không chỉ vào hành vi một lần chạy.

**Câu 4.** Khai báo A, B, C trong cùng `try (...)` thì đóng theo thứ tự nào?  
**C, B, A**, ngược với thứ tự khởi tạo.

**Câu 5.** Nếu khởi tạo B thất bại sau khi A đã được khởi tạo, A có được đóng không?  
**Có**, A được tự đóng theo quy tắc của `try-with-resources`.

**Câu 6.** Nếu thân `try` ném lỗi và `close()` ném lỗi khác, lỗi nào được ưu tiên?  
Lỗi thân `try` thường là **ngoại lệ chính**; lỗi đóng được đính kèm qua `getSuppressed()`.

**Câu 7.** Gọi `close()` hai lần trên `AutoCloseable` luôn an toàn và không có hiệu ứng không?  
**Không có bảo đảm chung.** `AutoCloseable` khuyến khích idempotent, trong khi `Closeable` quy định gọi lại sau khi đã đóng không có tác dụng.

**Câu 8.** Một class có `public void close()` nhưng không implements interface thích hợp có dùng được trong `try (...)` không?  
**Không**. Java kiểm tra kiểu của resource phải là subtype của `AutoCloseable`.

**Câu 9.** Với `try-with-resources` có `catch` và `finally`, thứ tự “close → catch → finally” đúng không?  
**Đúng về các giai đoạn**, nếu có nhánh `catch` phù hợp thì nó chạy sau đóng; `finally` chạy sau giai đoạn bắt lỗi, theo ngữ nghĩa Java.

**Câu 10.** Khi dùng `try (existing)` từ Java 9, biến `existing` cần điều kiện gì?  
Biến phải được gán trước, là `final` hoặc **effectively final**, và có kiểu thích hợp. Việc khối kết thúc đồng nghĩa tài nguyên đã được yêu cầu đóng dù tên biến có thể còn trong scope.

## Tài liệu chuẩn

- [Java SE 21 API — `AutoCloseable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html).
- [Java SE 21 API — `Closeable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Closeable.html).
- [JLS Java SE 21 — §14.20.3 `try-with-resources`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3).
- [JLS Java SE 21 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).

**Ghi nhớ:** `AutoCloseable` là hợp đồng đóng tài nguyên tổng quát; `Closeable` là hợp đồng I/O cụ thể hơn với `IOException` và hành vi gọi lại `close()`. Cả hai cho phép `try-with-resources` tự đóng đúng thứ tự, quản lý ngoại lệ khi cleanup thất bại và làm rõ ai sở hữu vòng đời tài nguyên.
