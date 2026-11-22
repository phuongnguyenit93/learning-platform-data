# IOException có nguyên nhân và bảo toàn thông tin lỗi trong Java Console và I/O

Khi làm việc với console, tệp cấu hình, standard input và các luồng dữ liệu trong Java, một thao tác I/O có thể thất bại ở nhiều tầng: không mở được file, lỗi đọc từ thiết bị, giải mã hoặc ghi dữ liệu, mất kết nối, hoặc không đóng được tài nguyên. Việc báo một thông điệp chung chung như `"I/O failed"` nhưng **đánh mất exception gốc** sẽ khiến quá trình điều tra lỗi rất khó khăn.

`java.io.IOException` là **checked exception** dùng cho các lỗi I/O. Từ Java 6, lớp này hỗ trợ **exception chaining** bằng hai constructor `IOException(String message, Throwable cause)` và `IOException(Throwable cause)`. Những API đó **vẫn hiện hành trong Java 17+ và JDK 25/26**.

Bài học này tập trung vào việc **giữ lại nguyên nhân (`cause`), ngữ cảnh (`message`), stack trace và suppressed exceptions** khi chuyển lỗi qua các tầng ứng dụng, đặc biệt lưu ý một điểm riêng của `java.io.Console`: các phương thức đọc tương tác như `readLine()` và `readPassword()` có thể ném **`IOError`** nếu thao tác console gặp lỗi; chúng không đơn giản khai báo `throws IOException` như nhiều API stream khác.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `IOException`, `EOFException`, `UncheckedIOException` và `IOError` khi tương tác với I/O hoặc console.
2. Chọn đúng constructor `new IOException(context, cause)` và hiểu `getMessage()`, `getCause()`, `getStackTrace()`, `getSuppressed()`.
3. Wrap lỗi ở ranh giới abstraction mà **không làm mất nguyên nhân**, không thay thế exception thật bằng một bản sao chỉ có message.
4. Dùng `try-with-resources` để tránh lỗi đóng tài nguyên che mất lỗi đọc/ghi ban đầu.
5. Xử lý `Console.readLine()==null` (EOF), `System.console()==null` và `IOError` theo các nhánh khác nhau.
6. Tạo log lỗi hữu ích nhưng không để lộ password, token, đường dẫn nhạy cảm hoặc dữ liệu người dùng.
7. Biên dịch và chạy một ví dụ Java 17+ mô phỏng các lỗi có thể kiểm chứng ổn định mà không yêu cầu terminal tương tác thực.

## 2. IOException và ngoại lệ có nguyên nhân

### 2.1. `IOException` là checked exception

`IOException extends Exception`, không phải `RuntimeException`. Vì là checked exception, code gọi một method khai báo `throws IOException` phải **bắt** hoặc **khai báo tiếp** trong `throws` của method hiện tại.

Ví dụ:

```java
// Mảnh code Java minh họa, chưa phải chương trình độc lập:
static String firstLine(Path path) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
```

Các import tương ứng: `java.io.BufferedReader`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`. `Files.newBufferedReader` có thể báo `NoSuchFileException` (subclass của `IOException`), `AccessDeniedException` hoặc những lỗi I/O khác tùy tình huống.

Không bắt `IOException` chỉ để ghi một log rồi tiếp tục như thể kết quả đọc đã hợp lệ. Hãy quyết định rõ: **có thể phục hồi/retry**, **phải trả lỗi cho caller**, hay **wrap thành lỗi ở tầng nghiệp vụ**.

### 2.2. Cause mang ý nghĩa gì?

Một exception có thể xuất hiện **vì** một exception khác:

```text
IOException: Could not load console banner: missing.txt
    Caused by: NoSuchFileException: /some/path/missing.txt
```

Đây là **sơ đồ**, không phải nguyên văn stack trace trên một máy cụ thể.

- Exception ngoài cung cấp **ngữ cảnh của tầng hiện tại**: không thể nạp banner cho console.
- Exception trong cung cấp **nguyên nhân kỹ thuật**: không tìm thấy tệp.
- `getCause()` trả Throwable gốc được gắn làm nguyên nhân trực tiếp, hoặc `null` nếu chưa có/nguyên nhân không biết.
- Một cause lại có thể có cause khác, tạo thành **chuỗi nguyên nhân** (*exception chain*).
- Stack trace của exception ngoài cho biết nơi wrapper được tạo; stack trace của cause giữ lại vị trí lỗi gốc.

Một thông báo chi tiết có giá trị hơn nhưng **không thay thế** cấu trúc cause.

## 3. Bốn constructor của IOException và cách chọn

| Constructor | Khi nên dùng | Điểm cần nhớ |
| --- | --- | --- |
| `new IOException()` | Lỗi I/O không có thông điệp hoặc chưa biết nguyên nhân, ít hữu ích cho báo cáo. | `getMessage()==null`, không có cause mặc định. |
| `new IOException("message")` | Phát hiện trực tiếp một lỗi I/O mới, không có Throwable gây lỗi. | Không mang nguyên nhân trước đó nếu đang catch một exception khác. |
| `new IOException("message", cause)` | **Lựa chọn ưu tiên** khi chuyển lỗi ở tầng thấp lên tầng có ngữ cảnh rõ hơn. | Giữ `cause`; thông điệp ngoài được cung cấp độc lập. |
| `new IOException(cause)` | Muốn wrap nguyên nhân nhưng không cần thêm message đặc thù. | Message ngoài lấy theo `cause.toString()` nếu cause khác null. |

Hai constructor nhận `Throwable cause` được bổ sung từ Java 6 và vẫn tồn tại ở JDK mới. Ví dụ chuẩn:

```java
try {
    readLowerLevel();
} catch (IOException cause) {
    throw new IOException(
            "Cannot load console configuration for current session",
            cause);
}
```

Đây là **mảnh code minh họa**, giả định `readLowerLevel()` đã có. Phần message ngoài mô tả việc đang làm, không chỉ lặp lại message lỗi tầng dưới. `IOException(String, Throwable)` **không tự động thêm message của cause vào message ngoài**; thông tin cause vẫn nằm trong trường riêng và có thể được in ra bởi stack trace logger.

### Sai lầm làm mất nguyên nhân

```java
// Không nên dùng khi đang wrap một IOException có thật:
catch (IOException e) {
    throw new IOException("Cannot load input: " + e.getMessage());
}
```

Dù có nhắc lại chữ từ lỗi gốc, wrapper mới có `getCause()==null`, làm mất type, stack trace và các suppressed exceptions gắn với exception ban đầu.

Cách sửa:

```java
catch (IOException e) {
    throw new IOException("Cannot load input", e);
}
```

Với caller hiểu được `IOException` gốc và không cần thêm tầng ngữ cảnh, **`throw e;`** có thể phù hợp hơn tạo wrapper thừa. Không phải cứ catch là phải wrap.

### `initCause` còn phù hợp khi nào?

`Throwable.initCause(Throwable)` tồn tại để gắn cause cho exception đã được tạo bằng constructor **chưa khởi tạo cause**. Với `IOException` hiện đại, hãy dùng constructor nhận cause trực tiếp, thay vì tạo `new IOException("...")` rồi gọi `initCause` một cách vòng vo. Nếu cause đã được khởi tạo bởi constructor nhận `Throwable` hoặc đã gọi `initCause` một lần, gọi thêm có thể ném `IllegalStateException`.

## 4. Console khác gì API I/O thông thường?

`System.console()` có thể trả `null` nếu JVM không có console phù hợp, thường thấy khi chạy ứng dụng dưới IDE, CI, process nền, container không có TTY hoặc redirected streams. Đây **không phải một `IOException`**: đó là **khả năng console không tồn tại**, cần quyết định đường vào khác hoặc báo lỗi cấu hình.

Ngay cả khi console tồn tại:

- `Console.readLine(...)` trả một `String` hoặc `null` khi input tới **EOF**.
- `Console.readPassword(...)` trả `char[]` hoặc `null` khi EOF; phải xóa mảng secret sau khi dùng.
- Theo Java Console API, lỗi I/O trong các phương thức đọc console có thể được báo bằng **`java.io.IOError`**, một subclass của `Error`.
- `Console.reader()` trả `Reader`; các thao tác `Reader` có thể có đường báo lỗi checked `IOException` theo API cụ thể. Tránh suy ra tất cả method thuộc Console có cùng kiểu exception.
- `System.in` là byte stream riêng và có thể đọc từ pipe/file mà không cần Console; các method của input stream thường sử dụng checked `IOException`.
- EOF là **điều kiện input kết thúc**, không tự động là một sự cố hệ thống. Caller có thể xử lý EOF bình thường hoặc biến thành lỗi có ý nghĩa nếu một dòng là bắt buộc.

### Phân biệt ba trạng thái

```text
System.console() == null
    -> Không có console tương tác phù hợp: config/usage/fallback rõ ràng

console != null && console.readLine(...) == null
    -> EOF: người dùng đóng input hoặc input đã kết thúc

console.readLine(...) throws IOError
    -> Lỗi I/O khi sử dụng console: giữ cause, báo sự cố
```

Không viết `System.console().readLine()` rồi giả định luôn có terminal; cũng không dùng `Scanner(System.in)` để đọc password như một fallback bảo mật tự động.

### Nếu API của ứng dụng khai báo `throws IOException`

Ở ranh giới một **console adapter**, đôi khi ứng dụng muốn chuyển `IOError` sang checked `IOException` để thống nhất giao diện lỗi I/O, nhưng đây là **quyết định thiết kế**, không phải hành vi tự động của Console:

```java
// Method ví dụ: cần import java.io.Console, java.io.EOFException,
// java.io.IOError và java.io.IOException.
static String requiredConsoleLine(Console console) throws IOException {
    if (console == null) {
        throw new IOException("Interactive console unavailable");
    }
    try {
        String value = console.readLine("Choice: ");
        if (value == null) {
            throw new EOFException("Console input ended");
        }
        return value;
    } catch (IOError error) {
        throw new IOException("Console I/O failed", error);
    }
}
```

- Nếu không có console, ví dụ chọn tạo một `IOException` **không có cause**, vì không có Throwable gốc. Sản phẩm khác có thể dùng một lỗi cấu hình/`IllegalStateException` phù hợp hơn.
- Nếu EOF, tạo `EOFException` như một cách diễn đạt “đang bắt buộc có dòng”. `EOFException extends IOException`, nhưng EOF **không phải lúc nào cũng nên coi là lỗi**.
- Nếu có `IOError`, wrapper giữ **`IOError` là cause**; `IOError.getCause()` có thể trỏ tới lỗi I/O tầng dưới, ví dụ `IOException`. **Không bóc bỏ tầng IOError rồi làm mất ngữ cảnh của nó** nếu không có lý do rõ ràng.
- `IOError extends Error`, vì vậy đừng bắt `Error` chung hoặc `Throwable` rồi tự động giả vờ mọi sự cố đều có thể tiếp tục. Bắt **đích danh `IOError`** ở ranh giới báo lỗi khi policy ứng dụng cho phép, hoặc để lỗi truyền lên entrypoint giám sát.
- Đoạn method này không phải chương trình độc lập; chương trình đầy đủ ở mục 6 mô phỏng chính xác một chuỗi `IOError → IOException` mà không phụ thuộc thiết bị console thực.

### Password, token và dữ liệu nhạy cảm

Với `Console.readPassword`, hãy dùng `char[]` và `Arrays.fill(secret, '\0')` trong `finally` sau khi dùng. Không đưa nội dung secret vào `IOException` message, cause, suppressed exceptions, stack traces hoặc log. Không tự fallback sang input echo ở `System.in` chỉ vì Console vắng mặt. Khi không có kênh nhập secret phù hợp, dùng secret provider đã bảo vệ hoặc **fail closed**.

## 5. Bảo toàn thông tin lỗi bao gồm những gì?

Một exception mang nhiều dữ liệu độc lập:

| Thông tin | API | Ý nghĩa |
| --- | --- | --- |
| Thông điệp | `getMessage()` | Ngữ cảnh dành cho con người; có thể null. |
| Nguyên nhân trực tiếp | `getCause()` | Throwable đã gây ra exception ngoài; có thể null. |
| Stack trace | `getStackTrace()` | Các frame lúc Throwable được tạo/fill; giúp truy nơi xảy ra lỗi. |
| Các lỗi bị suppressed | `getSuppressed()` | Những lỗi khác không được dùng làm lỗi chính, thường xảy ra lúc đóng tài nguyên. |
| Kiểu exception cụ thể | `e.getClass()` hoặc `instanceof` | Phân biệt `NoSuchFileException`, `AccessDeniedException`, `EOFException`, v.v. |
| Ngữ cảnh ứng dụng | Message, operation ID, file/path hoặc domain-specific fields | Biết thao tác nào thất bại; phải kiểm soát lộ thông tin. |

`printStackTrace()` và các logging frameworks hỗ trợ ghi cause chain và suppressed exceptions nếu **truyền nguyên Throwable**. Chỉ log `e.getMessage()` hoặc `e.toString()` thường không đủ để điều tra.

**Phân biệt:** `cause` là nguyên nhân đã dẫn tới lỗi ngoài; `suppressed` là lỗi khác bị đặt xuống thứ yếu để không che mất lỗi chính. Không nên đưa lỗi `close()` vào `cause` thay cho lỗi `read()` chỉ vì xảy ra sau.

## 6. Ví dụ Java 17+ đầy đủ, độc lập và có stdout kiểm chứng

Ví dụ sau mô phỏng **ba tình huống có thể kiểm thử không cần terminal**:

1. Đọc banner cho console từ file không tồn tại: bắt `NoSuchFileException` và wrap vào `IOException` có message ngữ cảnh.
2. Thao tác đọc thất bại, sau đó `close()` cũng thất bại: `try-with-resources` giữ lỗi đọc làm chính và gắn lỗi đóng thành `suppressed`.
3. Console báo `IOError`: mô phỏng một `IOError` có nguyên nhân `IOException`, sau đó wrap ở console adapter bằng `IOException` để thấy đầy đủ hai tầng cause.

Chương trình **không tự gọi `Console.readLine()` trong `main`**, vì điều đó sẽ làm kết quả phụ thuộc terminal của người chạy. Method `readConsoleLine` được định nghĩa như adapter cho sử dụng thực tế; phần mô phỏng `IOError` tạo trực tiếp bằng constructor chuẩn.

### Tạo tệp `IOExceptionCauseDemo.java`

```java
import java.io.BufferedReader;
import java.io.Closeable;
import java.io.Console;
import java.io.EOFException;
import java.io.IOError;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class IOExceptionCauseDemo {
    private static String readBanner(Path file) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            return reader.readLine();
        } catch (IOException cause) {
            throw new IOException("Could not load console banner: "
                    + file.getFileName(), cause);
        }
    }

    private static final class FailingInput implements Closeable {
        void read() throws IOException {
            throw new IOException("input read failed");
        }
        @Override public void close() throws IOException {
            throw new IOException("input close failed");
        }
    }

    private static void readWithCleanup() throws IOException {
        try (FailingInput input = new FailingInput()) {
            input.read();
        } catch (IOException cause) {
            throw new IOException("Could not consume input", cause);
        }
    }

    // Adapter for real interactive use; the demo does not invoke it.
    private static String readConsoleLine(Console console) throws IOException {
        if (console == null) {
            throw new IOException("Interactive console unavailable");
        }
        try {
            String value = console.readLine("Choice: ");
            if (value == null) {
                throw new EOFException("Console input ended");
            }
            return value;
        } catch (IOError error) {
            throw new IOException("Console I/O failed", error);
        }
    }

    public static void main(String[] args) throws IOException {
        Path temp = Files.createTempDirectory("io-cause-example-");
        try {
            try {
                readBanner(temp.resolve("missing.txt"));
            } catch (IOException error) {
                System.out.println("context=" + error.getMessage());
                System.out.println("cause="
                        + error.getCause().getClass().getSimpleName());
            }
        } finally {
            Files.deleteIfExists(temp);
        }

        try {
            readWithCleanup();
        } catch (IOException error) {
            Throwable primary = error.getCause();
            System.out.println("readCause=" + primary.getMessage());
            System.out.println("suppressedOnCause="
                    + primary.getSuppressed().length);
            System.out.println("cleanup="
                    + primary.getSuppressed()[0].getMessage());
        }

        IOError consoleFailure =
                new IOError(new IOException("terminal disconnected"));
        IOException bridged = new IOException(
                "Console I/O failed", consoleFailure);
        System.out.println("bridgeCause="
                + bridged.getCause().getClass().getSimpleName());
        System.out.println("rootCause="
                + bridged.getCause().getCause().getClass().getSimpleName());
    }
}
```

### Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 IOExceptionCauseDemo.java
java IOExceptionCauseDemo
```

**Stdout đã kiểm chứng thực tế trên JDK 24 với source target Java 17:**

```text
context=Could not load console banner: missing.txt
cause=NoSuchFileException
readCause=input read failed
suppressedOnCause=1
cleanup=input close failed
bridgeCause=IOError
rootCause=IOException
```

Không có stack trace trên stdout vì `main` cố ý in **các trường ổn định** thay vì in `printStackTrace()`. Nếu ứng dụng có logger, bạn có thể đưa nguyên exception cho logger để xem full trace ở log chẩn đoán.

### Giải thích theo thứ tự

**Tình huống 1 — Có cause:**

- `Files.newBufferedReader(temp.resolve("missing.txt"), UTF_8)` thất bại vì tệp không có trong thư mục tạm vừa tạo.
- `readBanner` nhận exception (trong thử nghiệm là `NoSuchFileException`), rồi tạo `new IOException("Could not load console banner: missing.txt", cause)`.
- Message ngoài trả lời **đang cố làm gì**; cause trả lời **vì sao thất bại**.
- `error.getCause().getClass().getSimpleName()` là `NoSuchFileException` trong môi trường kiểm thử.
- Thư mục tạm được dọn trong `finally` sau khi kiểm tra; các file/đường dẫn thật có thể khác nhưng stdout chỉ in tên cuối `missing.txt` cho ổn định.

**Tình huống 2 — Có suppressed exception:**

- `FailingInput.read()` ném `IOException("input read failed")`.
- Khi rời khối `try-with-resources`, `close()` cũng ném `IOException("input close failed")`.
- Lỗi đọc vẫn là **primary exception**; lỗi close được attach vào primary bằng `getSuppressed()`.
- `readWithCleanup` wrap primary vào `IOException("Could not consume input", cause)`.
- `getSuppressed()` của **wrapper ngoài** có thể rỗng; suppressed được giữ **trên cause gốc**, không tự động copy sang wrapper. Vì vậy chương trình gọi `error.getCause().getSuppressed()`.
- Không nên đổi thứ tự để làm lỗi close che mất lỗi đọc, hoặc chỉ log wrapper message khiến suppressed bị bỏ qua.

**Tình huống 3 — `IOError` có cause:**

- `new IOError(new IOException("terminal disconnected"))` mô phỏng tình huống lỗi I/O từ console API.
- `new IOException("Console I/O failed", consoleFailure)` tạo checked IOException ở ranh giới adapter.
- `bridged.getCause()` là `IOError`; `bridged.getCause().getCause()` là `IOException` mô phỏng lỗi gốc.
- Đây là **mô phỏng một chuỗi Throwable hợp lệ**, không phải khẳng định tất cả `IOError` thực tế đều có cause cùng loại. Các implementation có thể cung cấp cause khác hoặc null.
- Logic sản phẩm vẫn phải quyết định có nên catch `IOError` tại boundary hay để nó truyền lên cấp giám sát, vì `IOError` là `Error`.

## 7. Try-with-resources và suppressed exceptions

`try-with-resources` có từ Java 7 và vẫn là lựa chọn mặc định để đóng `Closeable`/`AutoCloseable` được chương trình sở hữu. Nó giữ tốt hơn thông tin lỗi so với việc đóng bằng `finally` thiếu kiểm soát.

### Mẫu đúng

```java
// Mảnh code minh họa:
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    return reader.readLine();
}
```

Nếu `readLine()` ném lỗi rồi `close()` cũng ném lỗi, lỗi từ body là primary và lỗi đóng tài nguyên được **suppressed**. Nếu body không có lỗi nhưng `close()` ném exception, thì lỗi close là exception chính.

### Mẫu dễ đánh mất nguyên nhân

```java
// KHÔNG NÊN: close() trong finally có thể che lỗi đã xảy ra trong body.
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
try {
    return reader.readLine();
} finally {
    reader.close();
}
```

Mảnh code trên có thể khiến exception của `reader.close()` ghi đè exception của `reader.readLine()` khi cả hai đều thất bại. Sử dụng `try-with-resources` sẽ giữ primary và suppressed theo semantics chuẩn, đồng thời tự xử lý đóng khi có lỗi.

### Cause không giống suppressed

```text
IOException: Could not consume input             <- wrapper mới
   Caused by: IOException: input read failed      <- primary từ body
       Suppressed: IOException: input close failed <- lỗi close
```

Đây là **sơ đồ cấu trúc**, không phải chính xác stack trace in bởi Java. Lỗi close **không phải** nguyên nhân làm lỗi đọc xảy ra; nó là vấn đề độc lập phát sinh trong cleanup. Bởi vậy nó thuộc `suppressed`, không phải `cause`.

`Throwable.getSuppressed()` trả một array (có thể rỗng) chứa lỗi suppressed. Khi wrap primary bằng constructor nhận cause, **danh sách suppressed vẫn nằm ở primary**; nếu muốn hiển thị đầy đủ phải cho logger đi theo cause chain và suppressed ở từng tầng.

## 8. Cách chuyển lỗi qua tầng ứng dụng

### 8.1. Tầng truy cập tệp

Tại nơi code biết **đang mở/đọc file nào**, có thể gắn thông tin tên file và mục đích:

```java
// Mảnh code bên trong một method đã có path:
try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    return reader.readLine();
} catch (IOException e) {
    throw new IOException("Failed to load console greeting text", e);
}
```

Đừng thêm đường dẫn tuyệt đối hoặc dữ liệu nhạy cảm vào message nếu message sẽ đi vào log gửi cho người dùng không đáng tin. Thông điệp công khai có thể dùng **request ID** hoặc tên tệp tương đối đã sanitize; logger nội bộ có quyền mới được thấy chi tiết kỹ thuật cần thiết.

### 8.2. Tầng service

Nếu service chỉ biết một nghiệp vụ như “khởi tạo phiên CLI”, có thể:

- Giữ nguyên `IOException` nếu API công khai của service đã chấp nhận việc lộ loại lỗi I/O.
- Wrap thành một exception domain có constructor nhận cause để tăng tính rõ ràng (ví dụ `SessionSetupException`), **nếu tầng domain không nên phụ thuộc chi tiết I/O**.
- Không tạo 3–4 wrapper liên tiếp nếu không có ngữ cảnh mới; chuỗi dài không cần thiết làm log khó đọc.
- Phân biệt lỗi vĩnh viễn (file không tồn tại, option sai) với lỗi có thể retry (mất kết nối tạm thời). Không retry vô hạn chỉ vì loại exception là `IOException`.

Mẫu domain exception tùy chọn:

```java
// Mảnh class minh họa, không phải entrypoint chạy độc lập:
final class ConsoleSetupException extends RuntimeException {
    ConsoleSetupException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Chọn checked vs unchecked dựa trên contract của tầng. Dù đổi loại exception, **giữ cause**.

### 8.3. Tầng CLI/GUI/API

Ở boundary:

- CLI: in thông báo ngắn, hướng dẫn hành động phù hợp trên `System.err` và trả exit code có chủ đích.
- GUI: hiển thị message có ý nghĩa, cho phép người dùng retry hoặc thay cấu hình; đừng dán raw stack trace vào hộp thoại.
- HTTP API: map lỗi vào status/body phù hợp, không đưa đường dẫn filesystem hay stack trace của server ra response.
- Logging/monitoring: gửi **exception object** (không chỉ chuỗi message), kèm operation ID và metadata đã được redacted.
- Khi thật sự không thể phục hồi, đừng nuốt exception rồi tiếp tục sử dụng dữ liệu thiếu làm như thành công.

Việc log exception và rethrow ở **mỗi tầng** thường tạo nhiều bản ghi giống nhau. Quy ước phổ biến: các tầng dưới **propagate/wrap**, log một lần ở boundary chịu trách nhiệm.

## 9. UncheckedIOException và IOError: cùng “I/O” nhưng khác bản chất

| Loại | Kế thừa | Checked? | Dùng thế nào? |
| --- | --- | --- | --- |
| `IOException` | `Exception` | **Có** | API stream/file I/O truyền thống và những boundary khai báo `throws IOException`. |
| `EOFException` | `IOException` | **Có** | Biểu đạt kết thúc luồng không mong đợi trong contract yêu cầu còn dữ liệu; không có nghĩa mọi EOF là exception. |
| `UncheckedIOException` | `RuntimeException` | **Không** | Wrapper có nguyên nhân kiểu `IOException` khi API không thích hợp khai báo checked exception, ví dụ vài luồng stream/lambda. |
| `IOError` | `Error` | **Không** | Lỗi I/O nghiêm trọng, như một số thao tác `Console`; không phải subtype của `IOException`. |

`UncheckedIOException` có constructor `(IOException cause)` và `(String message, IOException cause)`; `getCause()` trả `IOException`. Không đưa nguyên nhân bất kỳ không thuộc `IOException` cho wrapper này. Nó hữu ích trong một số boundary yêu cầu unchecked error, nhưng chỉ đổi exception thành unchecked **không tự làm sự cố trở nên an toàn để bỏ qua**.

`IOError` nhận `Throwable cause` trong constructor. Nó thuộc nhánh `Error` của Java; một `catch(IOException e)` **không bắt được** `IOError`. Không nên viết `catch(Throwable t)` khắp nơi rồi chuyển mọi lỗi hệ thống thành `IOException` — có những lỗi nên dừng ứng dụng hoặc cho tầng giám sát xử lý.

Ví dụ chuyển rõ ràng:

```java
// Mảnh code: việc wrap tùy policy console adapter của bạn.
try {
    return console.readLine("Input: ");
} catch (IOError e) {
    throw new IOException("Console device read failed", e);
}
```

`console` là `Console` đã kiểm tra khác null. Nếu gọi `readLine` trả null (EOF), đoạn này trả null bình thường; caller phải xử lý riêng. Nếu nguồn I/O dưới `IOError` có cause kiểu khác, cứ giữ nguyên exception chain thay vì cast mạo hiểm.

## 10. Những mẫu xử lý lỗi nên tránh

| Mẫu sai | Hậu quả | Thay thế |
| --- | --- | --- |
| `throw new IOException(e.getMessage());` | Mất nguyên nhân, type và stack trace cũ. | `throw new IOException(context, e);` |
| `throw new IOException("I/O failed");` trong `catch` | Mất thông tin về exception thực sự. | Dùng constructor nhận `cause` nếu đang chuyển lỗi. |
| `System.err.println(e.getMessage())` rồi tiếp tục như thành công | Che dấu lỗi và có thể làm hỏng trạng thái chương trình. | Rethrow/return failure hoặc recover có kiểm soát. |
| `throw new IOException("Error: " + e);` | Chỉ sao chép text `toString()`. | Gắn `e` làm cause. |
| `throw e;` ở mọi tầng dù API cần ngữ cảnh mới | Caller không biết thao tác nghiệp vụ đang thất bại. | Wrap có context thực sự ở boundary phù hợp. |
| `catch(Exception e) { return ""; }` | Giả tạo thành công, xóa dấu vết lỗi. | Trả lỗi có kiểu, cung cấp fallback có điều kiện. |
| `catch(IOException e)` để xử lý tất cả lỗi `Console.readLine` | Không bắt `IOError` do Console ném. | Phân biệt `IOError`, EOF và absence của Console. |
| `catch(Throwable t)` rồi bỏ qua | Che lỗi nghiêm trọng như `OutOfMemoryError`. | Bắt kiểu cụ thể, để tầng phù hợp quyết định recovery. |
| `finally { resource.close(); }` thiếu bảo vệ | Lỗi close có thể che lỗi body. | `try-with-resources`. |
| Chỉ đọc `wrapper.getSuppressed()` | Không thấy suppressed gắn với **cause bên trong**. | Dùng logger đi theo cả cause chain và suppressed. |
| `e.fillInStackTrace()` trước khi rethrow | Thay đổi stack snapshot, có thể xóa dấu nơi lỗi bắt đầu. | Rethrow đúng exception hoặc wrap với cause, không sửa trace tùy tiện. |
| `new IOException(context, null)` khi có cause thật | Thông tin gây lỗi đã bị bỏ. | Truyền đúng exception thật thay vì null. |
| Log raw path/token/password trong message | Có thể rò rỉ bí mật qua log, telemetry, UI. | Redact, phân cấp diagnostic và lưu ID liên hệ. |
| Dùng type name/message để suy ra policy retry | Dễ nhầm thiếu file/quyền truy cập/mạng. | Phân loại ngoại lệ và quy tắc nghiệp vụ rõ ràng. |

## 11. Dùng exception chain trong logging và monitoring

Thực tế, caller thường cần trả câu ngắn:

```text
Cannot start interactive session: configuration unavailable
```

Nhưng logging nội bộ nên giữ đủ `Throwable`:

```java
// Mảnh code minh họa bên trong một catch(IOException e):
logger.error("Cannot start CLI session, operationId={}", operationId, e);
```

Đây là **cú pháp logger thường gặp của SLF4J**, **không nằm trong Java standard library**, nên đoạn trên **không phải chương trình chạy độc lập nếu chưa có dependency/biến logger và operationId**. Ý nghĩa quan trọng là truyền **`e` dưới dạng Throwable** cho logging API hỗ trợ, chứ không truyền duy nhất `e.getMessage()`.

Nếu chỉ có JDK standard library, có thể dùng `java.util.logging.Logger`:

```java
// Mảnh code trong catch(IOException e), giả sử có Logger logger:
logger.log(java.util.logging.Level.SEVERE,
        "Cannot start CLI session", e);
```

Đừng đưa thông tin nhạy cảm vào cause message rồi nghĩ “không log cause là an toàn”: sau này một logger khác có thể in cả chuỗi. Hãy thiết kế từ đầu để exceptions có context nhưng **không chứa raw secrets**.

### Kiểm tra cause và suppressed trong test

Các unit test có thể assert:

- Wrapper `getMessage()` nói đúng thao tác.
- `getCause()` không null và có subtype được mong đợi.
- `getCause().getSuppressed()` gồm lỗi cleanup phù hợp.
- Không leak message secret hoặc input nhạy cảm.
- Lỗi được propagate (không biến thành giá trị bình thường).
- Không phụ thuộc vào path tuyệt đối hay dòng stack trace cụ thể giữa OS/JDK.

Với integration test, khóa toolchain/JDK và filesystem fixture nếu muốn kiểm tra exact subtype. Ví dụ `NoSuchFileException` là một subtype chuẩn của `IOException`, nhưng không nên assume mọi provider filesystem đều phát đúng subtype này cho mọi hoàn cảnh.

## 12. Tính đúng đắn khi thông tin lỗi không có sẵn

`Throwable.getCause()` có thể trả `null`: một số exception được tạo tại nguồn mà không có một exception gây lỗi khác. Không viết `error.getCause().getMessage()` trong generic error formatter mà không kiểm tra null.

Đoạn helper dưới đây là **mảnh code tích hợp**, dùng để tạo bản tóm tắt chuỗi cause ở mức đơn giản:

```java
static void reportCauses(Throwable failure) {
    Throwable current = failure;
    int depth = 0;
    while (current != null && depth < 8) {
        System.err.println(current.getClass().getSimpleName()
                + ": " + current.getMessage());
        current = current.getCause();
        depth++;
    }
}
```

Giới hạn `depth` giúp tránh output vô hạn do cause graph bất thường hoặc malicious exception. Helper này chỉ mô tả chuỗi nguyên nhân, **chưa duyệt `getSuppressed()`** và không phải logger đầy đủ. Khi cần log kỹ thuật, ưu tiên logging framework hoặc `Throwable.printStackTrace` ở kênh nội bộ được kiểm soát.

### Khi nào *không có* underlying Throwable?

- `System.console()==null`: vắng thiết bị tương tác không tự phát sinh lỗi I/O tầng dưới. Có thể trả lỗi cấu hình `IllegalStateException` hoặc error result riêng.
- `readLine()==null`: EOF. Nếu nghiệp vụ yêu cầu có một dòng, có thể chủ động tạo `EOFException("Required input ended")` nhưng không bịa một cause không tồn tại.
- Giá trị input sai định dạng: thường là lỗi validation, không phải `IOException`; đừng dùng exception I/O cho mọi tình huống người dùng nhập sai.
- Missing config: có thể là lỗi cấu hình, trong khi **đọc file config thất bại do OS** mới là nguyên nhân `IOException` thích hợp.

## 13. Case study: CLI đọc file cấu hình trước khi hỏi Console

Một chương trình CLI có thể cần đọc file `prompt.txt` để hiển thị hướng dẫn:

```text
CLI entrypoint
  |
  +-- load prompt.txt
  |      |
  |      +-- IOException: Cannot load prompt for session
  |             Caused by: NoSuchFileException
  |
  +-- System.console()
         |
         +-- null  -> no interactive capability (not an IOException from OS)
         +-- Console.readLine() == null -> EOF
         +-- Console.readLine() throws IOError -> console operation failure
         +-- valid String -> continue
```

Khi log, một entry đủ hữu ích là:

```text
operation=load-console-prompt
status=failed
errorType=IOException
causeType=NoSuchFileException
userMessage=Cannot start interactive session
```

Đây là **mô hình log**, không phải output bắt buộc của Java. Nếu dùng structured logging, có thể thêm operation ID, request ID và metadata đã qua redaction, nhưng tránh in password, path tuyệt đối hoặc toàn bộ input khi dữ liệu nhạy cảm.

Ở tầng entrypoint, CLI nên kết thúc với exit code khác 0 và thông điệp hữu ích cho người vận hành. Không cần báo raw stack trace cho người dùng cuối nếu đó là path/config lỗi nhạy cảm.

## 14. Checklist khi bảo toàn thông tin I/O error

1. Xác định **nguồn thực tế** của lỗi: stream/file, Console, EOF hay không có Console.
2. Chọn loại exception phù hợp thay vì dùng `IOException` cho mọi lỗi người dùng.
3. Nếu đang catch một Throwable thật, truyền nó làm **cause** khi wrap: `new IOException(context, e)`.
4. Context message nên mô tả thao tác, không chỉ sao lại message tầng dưới.
5. Nếu caller đã hiểu lỗi I/O và không cần thêm context, cân nhắc `throw e;` thay vì wrap dư thừa.
6. Dùng `try-with-resources` cho tài nguyên ứng dụng tự sở hữu để giữ **primary + suppressed** khi cleanup thất bại.
7. Khi log, đính kèm Throwable object và giữ cause/suppressed, không chỉ string.
8. Trên Console, kiểm tra `System.console() != null`, `readLine()/readPassword() != null` và đường đi `IOError`.
9. Không bao giờ log password/token; `readPassword` sử dụng `char[]` và xóa mảng khi xong.
10. Không làm mất `InterruptedException`/cờ interrupt bằng catch chuyển đổi tùy tiện; nếu tầng I/O có semantics interruption, cần giữ chính sách hủy hợp lệ.
11. Không dùng broad `catch(Throwable)` rồi tiếp tục một cách nguy hiểm.
12. Tách thông tin kỹ thuật cho log khỏi thông điệp an toàn dành cho người dùng.
13. Test wrapper cause, suppressed, EOF, thiếu console và mã lỗi của CLI.
14. Đừng để test phụ thuộc stack trace dòng/đường dẫn tuyệt đối theo OS; assert semantic fields.

## 15. Bài tập thực hành

**Bài tập A — Hiện cause chain.** Sửa chương trình để in `bridged.getCause().getCause().getMessage()`. Dự đoán kết quả từ constructor tạo `IOException("terminal disconnected")`. Sau đó thử thay bằng một Throwable không có message và xử lý null an toàn.

**Bài tập B — So sánh constructor.** Trong một `catch(IOException e)`, tạo hai exception: `new IOException("read failed")` và `new IOException("read failed", e)`. Kiểm tra `getCause()` từng trường hợp; giải thích vì sao một cách làm mất thông tin.

**Bài tập C — Lỗi đóng tài nguyên.** Trong `FailingInput`, bỏ exception ở `read()` nhưng vẫn ném ở `close()`. Sau khi chạy, xác định exception chính và số lỗi suppressed. Vì sao khác trường hợp cả body và close đều thất bại?

**Bài tập D — Thiết kế console boundary.** Viết test cho `requiredConsoleLine` thông qua một abstraction hoặc adapter có thể inject, không phụ thuộc `System.console()` của môi trường test. Phân biệt console vắng, console EOF và lỗi I/O.

**Bài tập E — Log an toàn.** Xây hàm ánh xạ một `IOException` sang message công khai, operation ID và log nội bộ. Đảm bảo secret/token không nằm trong bất kỳ message nào được in hoặc ghi.

## 16. Câu hỏi kiểm tra kiến thức

**Câu 1.** `throw new IOException(e.getMessage())` có giữ nguyên exception gốc không?

**Đáp án:** Không. Nó chỉ sao chép text, khiến `getCause() == null`, không bảo toàn type, stack trace và suppressed của exception gốc. Dùng `new IOException(context, e)` nếu cần wrap.

**Câu 2.** Nếu `IOException(String, Throwable)` có cause, message ngoài có tự nối message của cause không?

**Đáp án:** Không. Message được lưu đúng chuỗi truyền vào; cause được lưu riêng và có thể xem qua `getCause()` hoặc logger hiển thị full chain.

**Câu 3.** Nếu body ném IOException rồi close cũng ném IOException, `try-with-resources` ưu tiên lỗi nào?

**Đáp án:** Lỗi body vẫn là **primary**; lỗi close thành **suppressed** trên primary. Nếu primary được wrap, suppressed vẫn nằm trên cause bên trong.

**Câu 4.** `Console.readLine()` có luôn ném checked `IOException` khi I/O bị lỗi không?

**Đáp án:** Không. Console API mô tả việc ném `IOError`, là subclass của `Error`. Chỉ bắt `IOException` sẽ không bắt lỗi này; cân nhắc boundary adapter và policy xử lý phù hợp.

**Câu 5.** `System.console()==null` hoặc `Console.readLine()==null` có tự có cause để wrap không?

**Đáp án:** Không. Trạng thái đầu là thiếu khả năng tương tác, trạng thái sau là EOF. Có thể báo lỗi contract nếu bắt buộc input, nhưng không được bịa một Throwable gốc.

**Câu 6.** Vì sao `getSuppressed()` của wrapper ngoài có thể rỗng dù lỗi close đã xảy ra?

**Đáp án:** Lỗi close được suppressed **trên primary**, primary sau đó trở thành cause của wrapper. Duyệt `wrapper.getCause().getSuppressed()` hoặc logger hỗ trợ toàn bộ cây lỗi.

**Câu 7.** Khi nào nên dùng `UncheckedIOException` thay vì `IOException`?

**Đáp án:** Khi boundary không thể/không thích hợp khai báo checked exception, trong khi vẫn muốn giữ một `IOException` thật làm cause. Đừng đổi sang unchecked chỉ để tránh xử lý lỗi.

## 17. Tài liệu Java chính thức vẫn còn áp dụng

- [IOException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/IOException.html): constructors `(String, Throwable)` và `(Throwable)` có từ Java 6.
- [Throwable — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Throwable.html): cause chain, `getCause`, `getSuppressed`, `getStackTrace` và `initCause`.
- [Console — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Console.html): `readLine`, `readPassword`, EOF và `IOError`.
- [IOError — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/IOError.html): lỗi I/O nghiêm trọng, kế thừa `Error` và constructor nhận cause.
- [UncheckedIOException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/UncheckedIOException.html): unchecked wrapper cho cause kiểu `IOException`.
- [Files — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): đọc dữ liệu từ file, danh sách lỗi có thể phát sinh.
- [Java Language Specification — try-with-resources](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3): cấu trúc try-with-resources và semantics suppressed exceptions.

**Ghi nhớ:** `IOException` có thể chứa **message có ngữ cảnh** và **cause có thông tin kỹ thuật gốc**. Dùng `new IOException(message, cause)` khi chuyển lỗi, `try-with-resources` để giữ primary/suppressed, và log nguyên Throwable ở boundary được bảo vệ. Riêng `Console` phải phân biệt **thiếu Console**, **EOF** và **`IOError`**; đừng đánh mất nguyên nhân hoặc nuốt những lỗi hệ thống chỉ để cho chương trình “tiếp tục chạy”.
