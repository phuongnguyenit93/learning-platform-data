# `Closeable`, `AutoCloseable` và `try-with-resources`

## Mục tiêu bài học

Khi một chương trình Java mở file, socket, stream, reader, channel hoặc kết nối cơ sở dữ liệu, tài nguyên phía sau đối tượng có thể là **file descriptor, bộ đệm, kết nối, khóa hoặc trạng thái hệ thống**. Garbage collector quản lý bộ nhớ của object Java, nhưng **không phải cơ chế đóng tài nguyên kịp thời** theo yêu cầu ứng dụng.

Java cung cấp `AutoCloseable`, giao diện chuyên biệt `Closeable` và cú pháp `try-with-resources` (TWR) để quản lý vòng đời tài nguyên có thể đóng. Mấu chốt là: **tài nguyên thuộc về ai, được đóng khi nào, theo thứ tự nào và điều gì xảy ra nếu cả thân `try` lẫn `close()` cùng phát sinh lỗi**.

Sau bài này, bạn có thể:

- Phân biệt `java.lang.AutoCloseable` và `java.io.Closeable` qua chữ ký `close()`, phạm vi áp dụng và đặc tính đóng lặp.
- Dùng `try-with-resources` với một hoặc nhiều tài nguyên, hiểu thứ tự khởi tạo **trái → phải** và đóng **phải → trái**.
- Viết chương trình xử lý chính xác ngoại lệ phát sinh trong thân `try`, khi khởi tạo, và khi đóng; biết đọc `Throwable.getSuppressed()`.
- Vận dụng cú pháp Java 9+ cho biến resource đã khai báo và quy tắc *effectively final*.
- Chọn đúng chiến lược sở hữu tài nguyên khi bọc stream/reader, dùng `System.in/out`, nhận tài nguyên từ thư viện hoặc quản lý transaction.
- Kiểm thử vòng đời tài nguyên bằng các ví dụ Java 17 độc lập, có đầu ra kiểm chứng được.

## 1. Vì sao phải đóng tài nguyên?

Xét đoạn code:

```java
InputStream in = Files.newInputStream(path);
byte[] data = in.readAllBytes();
```

Đây là **đoạn minh họa**: `path` là `Path` hợp lệ; có import `java.io.InputStream`, `java.nio.file.Files`, `java.nio.file.Path` và xử lý `IOException`. Đoạn này chưa đóng `in`. Nếu chương trình chạy lâu, lặp mở nhiều file mà không đóng, có thể hết số lượng file descriptor hoặc giữ tài nguyên hệ thống lâu hơn mong muốn. Nếu `readAllBytes()` ném ngoại lệ, không có đường đi nào trong đoạn mã đảm bảo đóng stream.

**Không nên trông chờ garbage collector**: GC có thể chưa chạy khi bạn cần giải phóng tài nguyên; một số tài nguyên không tương ứng trực tiếp một vùng heap. Việc `System.gc()` được gọi cũng không biến thành lời hứa các tài nguyên sẽ đóng đúng lúc. Hãy **gắn phạm vi sử dụng với phạm vi đóng**.

TWR cho phép viết lại:

```java
try (InputStream in = Files.newInputStream(path)) {
    byte[] data = in.readAllBytes();
    // Xử lý data khi in còn mở.
}
```

Đây là **đoạn minh họa**; biến `path` và các import/checked exception giống trên. Khi rời khối `try`, Java tự gọi `in.close()` — kể cả khi phần thân ném ngoại lệ hoặc `return`. Đối với I/O thông thường, đó là cách mặc định nên dùng.

### Vòng đời thường gặp

```text
Tạo/mở tài nguyên → Sử dụng → Đóng (kể cả nếu sử dụng thất bại)
        │                  │
        └── lỗi mở?         └── lỗi khi đóng?
                ↘       ↙
           Xử lý ngoại lệ có ngữ cảnh
```

**Đóng tài nguyên không có nghĩa dữ liệu được lưu bền vững trên ổ đĩa.** Chẳng hạn `BufferedWriter.close()` thường flush buffer và đóng underlying writer, nhưng không tương đương với việc bảo đảm filesystem đã đồng bộ dữ liệu qua `fsync`/`FileChannel.force()`. Bài này tập trung vào **vòng đời và lỗi**, không biến `close()` thành cam kết durability.

## 2. `AutoCloseable`: hợp đồng đóng tài nguyên tổng quát

`java.lang.AutoCloseable` là giao diện có phương thức:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Đây là **chữ ký rút gọn minh họa**, không phải mã cần tự khai báo thay thế lớp trong JDK. Bất kỳ kiểu đối tượng nào triển khai `AutoCloseable` đều có thể xuất hiện trong phần khai báo tài nguyên của `try-with-resources`.

Đối tượng có thể đại diện file, database connection, lock scope, session, hoặc tài nguyên không thuộc filesystem. Một object không sở hữu tài nguyên hệ điều hành vẫn có thể triển khai `AutoCloseable` nếu muốn cung cấp thao tác kết thúc vòng đời có cấu trúc.

Ví dụ về các kiểu liên quan:

| Kiểu / API | Quan hệ | Tài nguyên thường quản lý |
|---|---|---|
| `AutoCloseable` | Giao diện gốc | Tài nguyên có vòng đời đóng |
| `Closeable` | Kế thừa `AutoCloseable` | I/O thường phát sinh `IOException` |
| `InputStream`, `OutputStream`, `Reader`, `Writer` | Triển khai `Closeable` | File, luồng byte/ký tự hoặc lớp bao |
| `java.nio.channels.Channel` | Kế thừa `Closeable` | Channel I/O |
| `java.sql.Connection` | Triển khai `AutoCloseable` | Kết nối database |
| `java.sql.Statement`, `ResultSet` | Triển khai `AutoCloseable` | Statement và kết quả truy vấn |
| `Stream<String>` trả bởi `Files.lines(path)` | `Stream` là `AutoCloseable` | Stream có liên kết reader/file còn mở |

`AutoCloseable.close()` khai báo `throws Exception`, nghĩa là một triển khai có thể phát sinh checked exception. Nhưng **triển khai cụ thể được phép thu hẹp hoặc bỏ checked exception** trong chữ ký `close()`. Vì thế loại ngoại lệ bạn phải khai báo/catch tùy theo **kiểu tĩnh của biến** và các lệnh trong thân `try`.

Ví dụ:

```java
class TaskScope implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("release");
    }
}
```

Đây là **đoạn định nghĩa lớp minh họa**, có thể dùng trong một file Java thích hợp. Mặc dù `AutoCloseable` gốc có `throws Exception`, `TaskScope.close()` ở đây không ném checked exception, nên code gọi với kiểu `TaskScope` không buộc catch `Exception` chỉ bởi thao tác đóng.

**Lưu ý về đóng nhiều lần:** `AutoCloseable` không bắt buộc `close()` phải idempotent (gọi nhiều lần có cùng hiệu quả như một lần). Một tài nguyên có thể ném lỗi hoặc làm thay đổi trạng thái khi bị đóng lại. Không tự gọi `close()` trong thân TWR rồi mặc định Java đóng lần thứ hai sẽ luôn vô hại.

## 3. `Closeable`: giao diện chuyên biệt cho I/O

`java.io.Closeable` **kế thừa** `AutoCloseable` và thu hẹp checked exception:

```java
public interface Closeable extends AutoCloseable {
    @Override
    void close() throws IOException;
}
```

Đây cũng là **chữ ký rút gọn**, với `IOException` thuộc `java.io`.

| Tiêu chí | `AutoCloseable` | `Closeable` |
|---|---|---|
| Package | `java.lang` | `java.io` |
| Quan hệ | Giao diện cha | `extends AutoCloseable` |
| Checked exception từ `close()` | Khai báo `Exception` | Khai báo `IOException` |
| Phạm vi | Đóng tài nguyên nói chung | Tài nguyên I/O, đặc biệt streams/readers/channels |
| Đóng lặp | Không bắt buộc idempotent | Hợp đồng của `Closeable`: đóng đối tượng đã đóng không có tác dụng |
| Dùng trong TWR? | Có | Có |

`Closeable` nêu quy tắc: nếu stream đã đóng, gọi `close()` lần nữa không có tác dụng. Tuy nhiên điều đó **không** đồng nghĩa mọi kiểu `AutoCloseable` khác cũng có cùng cam kết; cũng không bảo đảm một lần đóng **đầu tiên** chắc chắn thành công.

Khi tự thiết kế API:

- Nếu abstraction thuần I/O, `Closeable` và `IOException` có thể giúp caller xử lý lỗi đúng miền.
- Nếu scope tài nguyên rộng hơn I/O (ví dụ session/transaction context), `AutoCloseable` phù hợp hơn. Có thể định nghĩa `close()` với checked exception hẹp, hoặc không ném checked exception khi hợp lý.
- Với cleanup phức tạp, không nên tùy tiện ném `Exception` rất rộng nếu có thể cung cấp một loại ngoại lệ ổn định, rõ nghĩa.

## 4. `try-with-resources`: cú pháp và thứ tự thực thi

Cú pháp cơ bản từ Java 7:

```java
try (ResourceType first = openFirst();
     ResourceType second = openSecond()) {
    use(first, second);
} catch (SomeException ex) {
    handle(ex);
} finally {
    afterClosing();
}
```

Đây là **mã giả Java**, không phải chương trình độc lập: `ResourceType` phải triển khai `AutoCloseable`, còn `openFirst`, `openSecond`, `use`, `handle`, `afterClosing` và `SomeException` là các tên mô tả. `catch` và `finally` là tùy chọn; bạn có thể viết TWR mà không cần một trong hai.

Trình tự chính:

1. Đánh giá và **khởi tạo tài nguyên từ trái sang phải**.
2. Khi tất cả khởi tạo thành công, chạy phần thân `try`.
3. Trước khi chạy `catch` hoặc `finally` của câu lệnh TWR, **đóng tài nguyên từ phải sang trái**.
4. Nếu có lỗi, áp dụng quy tắc **ngoại lệ chính** và **ngoại lệ bị suppress** (phần dưới).
5. `catch` bắt ngoại lệ còn lại sau khi TWR đóng tài nguyên; `finally` chạy theo quy tắc của câu lệnh try/finally.

TWR cũng đóng tài nguyên khi thoát khối bằng `break`, `continue`, `return` hoặc ngoại lệ, theo cơ chế thực thi Java bình thường. Đừng diễn giải thành bảo đảm tuyệt đối khi tiến trình bị cưỡng bức kết thúc, `Runtime.halt()`, mất điện hoặc JVM crash: khi đó chương trình có thể không thực thi cleanup.

### Ví dụ 1 — thứ tự mở, dùng và đóng tài nguyên

Lưu **`ResourceOrderDemo.java`**:

```java
public class ResourceOrderDemo {
    static final class Trace implements AutoCloseable {
        private final String name;

        Trace(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Trace first = new Trace("first");
             Trace second = new Trace("second")) {
            System.out.println("work");
        }
        System.out.println("after");
    }
}
```

Biên dịch/chạy Java 17+:

```bash
javac ResourceOrderDemo.java
java ResourceOrderDemo
```

Stdout chính xác:

```text
open first
open second
work
close second
close first
after
```

Giải thích: constructor `first` chạy trước `second`. Khi rời phần thân, Java gọi `second.close()` trước rồi `first.close()`, ngược thứ tự khởi tạo. Như vậy một lớp ngoài có thể tiếp tục tồn tại đến khi lớp trong đã đóng xong — thường phù hợp với trường hợp wrapper phụ thuộc vào stream bên dưới.

Nếu `second` không khởi tạo thành công, TWR vẫn đóng `first` đã khởi tạo xong; nó không cố đóng biến chưa nhận được tài nguyên hợp lệ.

### Khai báo resource và tính `final`

Các biến được khai báo trong header của TWR là **implicitly final**: bạn không thể gán sang đối tượng khác trong thân `try`.

Từ Java 9, có thể dùng **biến đã khai báo trước** nếu biến đó là `final` hoặc *effectively final*:

```java
InputStream input = Files.newInputStream(path);
try (input) {
    System.out.println(input.read());
}
```

Đây là **đoạn minh họa**, giả sử `path` là `Path`, có import `InputStream`/`Files` và xử lý `IOException`. `input` không bị gán lại, nên effectively final và hợp lệ trong Java 9+. Sau khối, biến vẫn nằm trong scope bên ngoài nhưng **stream đã đóng**; không dùng lại để đọc tiếp.

Ví dụ **không hợp lệ** vì biến resource bị gán lại:

```java
InputStream input = Files.newInputStream(firstPath);
input = Files.newInputStream(secondPath);
try (input) {
    // Compiler error: input is not final or effectively final.
}
```

Đây là **phản ví dụ**, với `firstPath`, `secondPath` là `Path` đã khai báo. Code không biên dịch theo cú pháp resource-variable của Java 9+. Cách thiết kế đúng là có một biến sở hữu tài nguyên duy nhất, hoặc khai báo tài nguyên trực tiếp trong header TWR. Không dùng đoạn phản ví dụ trong dự án thật vì việc ghi đè reference còn có nguy cơ làm rò rỉ stream đầu tiên.

Từ Java 10, bạn có thể dùng `var` cho tài nguyên khai báo ngay trong header:

```java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
```

Đoạn minh họa này yêu cầu có `path`, import `Files`/`StandardCharsets` và xử lý `IOException`. Dùng `var` không thay đổi quy tắc đóng; kiểu tĩnh được suy ra từ initializer.

## 5. Thân `try` và `close()` đều lỗi: suppressed exceptions

Đây là lý do quan trọng nên dùng TWR thay vì viết cleanup thủ công không cẩn thận.

Giả sử:

1. Phần thân ném `IllegalStateException("work failed")`.
2. Khi đóng tài nguyên thứ hai, `close()` ném `Exception("close second")`.
3. Khi đóng tài nguyên thứ nhất, `close()` ném `Exception("close first")`.

Nếu cleanup ở `finally` được viết sơ sài, một lỗi `close` có thể che khuất ngoại lệ trong thân — làm mất nguyên nhân gốc. TWR có quy tắc:

- Khi **thân `try` đã ném**, ngoại lệ ở thân là **primary exception**.
- Các ngoại lệ `close()` xảy ra lúc cleanup được gắn vào primary qua `Throwable.addSuppressed()`.
- Nếu **thân không ném** nhưng nhiều `close()` ném, ngoại lệ từ tài nguyên bị đóng **đầu tiên** theo thứ tự đóng ngược trở thành primary; những ngoại lệ đóng về sau bị suppress.
- `getSuppressed()` trả mảng các ngoại lệ được đính kèm; **đó không phải `getCause()`**. Cause thường mô tả chuỗi nguyên nhân; suppressed mô tả các lỗi xảy ra đồng thời lúc dọn dẹp.

### Ví dụ 2 — quan sát primary và suppressed exceptions

Lưu **`SuppressedExceptionsDemo.java`**:

```java
public class SuppressedExceptionsDemo {
    static final class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() throws Exception {
            System.out.println("close " + name);
            throw new Exception("close " + name + " failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource first = new FailingResource("first");
             FailingResource second = new FailingResource("second")) {
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primary: " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                    "suppressed: " + suppressed.getMessage()
                );
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac SuppressedExceptionsDemo.java
java SuppressedExceptionsDemo
```

Stdout chính xác:

```text
open first
open second
close second
close first
primary: work failed
suppressed: close second failed
suppressed: close first failed
```

Điểm cần nhớ: TWR **vẫn cố đóng `first`** ngay cả khi `second.close()` đã ném lỗi. Ngoại lệ chính là `IllegalStateException("work failed")`, vì thế cả hai lỗi `close` được ghi ở `getSuppressed()` theo thứ tự xảy ra.

Nếu bỏ lệnh `throw new IllegalStateException("work failed")` và phần thân hoàn thành bình thường, thì **lỗi đóng `second`** là primary và lỗi đóng `first` là suppressed.

Không nên chỉ log `ex.getMessage()` rồi bỏ qua suppressed exceptions. Khi phân tích lỗi I/O, có thể cần xem `ex.getSuppressed()`; nhiều framework logging hiển thị chúng khi log toàn bộ stack trace của ngoại lệ, nhưng mức chi tiết tùy cấu hình.

### Điều gì nếu mở tài nguyên thứ hai thất bại?

Một trường hợp khác:

```java
try (InputStream first = openFirst();
     InputStream second = openSecond()) {
    // ...
}
```

Đây là **đoạn mô tả**: `openFirst()` và `openSecond()` là hàm minh họa trả `InputStream`. Nếu `openFirst()` thành công nhưng `openSecond()` ném ngoại lệ, Java sẽ **đóng `first`**. Ngoại lệ khởi tạo `second` là primary; nếu `first.close()` cũng ném, lỗi đóng của `first` là suppressed. Phần thân `try` **không được chạy**, vì không khởi tạo đủ các tài nguyên.

Với tài nguyên đã tạo **ngoài** header trước khi vào TWR, caller phải đảm bảo chúng được đưa vào scope đóng hoặc có kế hoạch cleanup cho trường hợp khởi tạo các đối tượng khác thất bại. TWR không tự quản lý những tài nguyên mà nó chưa được giao sở hữu.

## 6. Vì sao TWR tốt hơn `finally` đóng thủ công?

Cách thủ công đơn giản sau trông có vẻ đúng:

```java
Resource resource = open();
try {
    doWork(resource);
} finally {
    resource.close();
}
```

Đây là **mã giả**, với `Resource`, `open`, `doWork` là các tên minh họa. Vấn đề: nếu `doWork` và `close` **đều ném ngoại lệ**, ngoại lệ từ `finally` có thể thay thế ngoại lệ chính, khiến debug khó hơn. Để viết cleanup thủ công đúng với nhiều resource và suppressed exceptions, phải có logic try/catch phức tạp, dễ sai thứ tự.

TWR tương đương một cơ chế `try/finally` do compiler sinh ra, có xử lý ngoại lệ và cleanup một cách hệ thống. Với tài nguyên triển khai `AutoCloseable`, hãy ưu tiên TWR để làm rõ ownership và giảm mã lặp.

Lưu ý: **TWR không thay thế catch hợp lý**. Nó tự đóng; lỗi đọc/ghi hay lỗi đóng vẫn cần được xử lý, khai báo hoặc chuyển thành exception miền nghiệp vụ tại ranh giới phù hợp.

## 7. Quản lý file bằng TWR trong Java 17

Với `Files`, `Path` và các stream thông dụng:

- `Files.newInputStream(path)` trả về `InputStream` cần đóng.
- `Files.newOutputStream(path, ...)` trả về `OutputStream` cần đóng.
- `Files.newBufferedReader(path, charset)` và `Files.newBufferedWriter(...)` trả về reader/writer có thể đóng.
- `FileChannel.open(path, ...)` trả về `FileChannel` có thể đóng.
- `Files.lines(path, charset)` trả về `Stream<String>` có liên kết đến file; **phải đóng stream**.
- `Files.list(path)`, `Files.walk(path)`, `Files.find(...)()` cũng là các luồng duyệt filesystem cần đóng sau khi dùng. Với `Files.find`, dùng chính xác cú pháp API phù hợp khi lập trình: `Files.find(path, maxDepth, matcher)`; không gọi phương thức `Files.find(...)()` theo cách in mô tả này.

Một quy trình đọc/ghi thường có **hai tài nguyên**: input và output. TWR sẽ đóng output trước input khi khai báo input trước output.

### Ví dụ 3 — sao chép nội dung qua hai stream

Lưu **`CopyWithResourcesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class CopyWithResourcesDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("twr-src-", ".txt");
        Path target = Files.createTempFile("twr-dst-", ".txt");

        try {
            Files.writeString(
                source, "Xin chào", StandardCharsets.UTF_8
            );

            try (InputStream in = Files.newInputStream(source);
                 OutputStream out = Files.newOutputStream(
                     target,
                     StandardOpenOption.WRITE,
                     StandardOpenOption.TRUNCATE_EXISTING
                 )) {
                in.transferTo(out);
            }

            System.out.println(
                "copied: " +
                Files.readString(target, StandardCharsets.UTF_8)
            );
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac CopyWithResourcesDemo.java
java CopyWithResourcesDemo
```

Stdout khi các thao tác filesystem thành công:

```text
copied: Xin chào
```

Chương trình tạo hai file tạm, ghi văn bản UTF-8 vào nguồn, sau đó dùng `InputStream.transferTo(OutputStream)` (Java 9+) sao chép byte sang đích. Nếu sao chép thất bại, TWR vẫn cố đóng cả `out` và `in`. Khi TWR kết thúc, lệnh đọc lại đích có thể mở file một lần mới. Phần `finally` dọn file tạm.

**Giới hạn của ví dụ:** cleanup ở `finally` là thao tác hệ thống độc lập, có thể ném `IOException` và làm che khuất lỗi trước đó nếu không thiết kế chính sách xử lý phù hợp. Ví dụ ưu tiên minh họa TWR trên hai stream; trong sản phẩm cần công cụ dọn temp/log lỗi có cơ chế không mất primary exception. Ngoài ra, lệnh `Files.createTempFile` thứ hai có thể thất bại sau khi tạo file thứ nhất nhưng trước khi vào `try/finally`, nên chương trình minh họa chưa bao phủ mọi tình huống thất bại của **quá trình chuẩn bị file tạm**. Thiết kế production phải bao cả bước tạo tài nguyên trong vùng dọn dẹp thích hợp.

`transferTo()` không gọi `close()` thay cho bạn; vì vậy TWR rất phù hợp để đảm bảo luồng được đóng dù thao tác đọc/ghi hoặc sao chép thất bại.

### Đóng `Files.lines` và các stream filesystem

Một cú pháp đúng:

```java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
```

Đây là **đoạn minh họa**. `path` là `Path`; cần `import java.util.stream.Stream;`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. Stream được đóng khi thoát TWR.

Đừng đồng nhất `stream.count()` hoặc một terminal operation khác với `stream.close()`. Java Stream thông thường không nhất thiết phải đóng, nhưng stream có nguồn từ file hoặc directory cần được đóng theo hợp đồng của API. Nếu dùng `Files.walk`, đóng stream cũng giải phóng các handle truy cập thư mục có liên quan.

## 8. Bọc stream: ai chịu trách nhiệm đóng?

Các kiểu như `BufferedInputStream`, `BufferedOutputStream`, `InputStreamReader`, `OutputStreamWriter`, `BufferedReader` và `BufferedWriter` thường là **wrapper/decorator** quanh một tài nguyên bên dưới:

```text
FileInputStream ──► InputStreamReader(UTF-8) ──► BufferedReader
                                              ▲
                                          caller dùng
                                              │
                                       caller close()
                                              ↓
                                       đóng các tầng dưới
```

Với các lớp wrapper I/O chuẩn nói trên, `close()` ở **wrapper ngoài cùng** thông thường đóng cả underlying stream/reader. Do đó:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line = reader.readLine();
}
```

Đây là **đoạn minh họa**, với `path` là `Path`, các import phù hợp và xử lý `IOException`. Caller sở hữu `reader` và chỉ cần đóng reader. Khi `Files.newBufferedReader` tự tạo tầng file bên dưới, việc đóng reader sẽ đảm nhiệm vòng đời theo hợp đồng đó.

Không nên tùy tiện quản lý cùng một tài nguyên bằng **nhiều owner độc lập**. Ví dụ, một thư viện nhận `OutputStream` do caller đưa vào có thể chỉ có nhiệm vụ ghi dữ liệu mà không nên đóng nó. Phải xác định rõ trong API:

- **Caller owns**: thư viện không đóng stream nhận được; người gọi đóng khi mọi người dùng đã xong.
- **Callee owns**: sau khi nhận stream, thư viện quản lý và đóng nó; caller không tiếp tục sử dụng.
- **Borrowed resource**: một đối tượng chỉ mượn tài nguyên trong thời gian xử lý và không có quyền đóng nguồn chung.

Không giả định mọi lớp wrapper thứ ba đều có hành vi đóng giống nhau; đọc hợp đồng của lớp cụ thể.

### `System.in`, `System.out`, `System.err`

Các standard stream là tài nguyên toàn cục của tiến trình. Ví dụ:

```java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
    System.out.println(reader.readLine());
}
```

Đây là **đoạn minh họa**, nhưng **cần cân nhắc kỹ**: khi TWR đóng `reader`, nó cũng đóng `System.in`. Nếu chương trình còn cần stdin cho phần khác, các thao tác đọc về sau có thể bị ảnh hưởng. Trong CLI chỉ có một lần đọc rồi kết thúc, điều này có thể được chấp nhận; trong thư viện, REPL hoặc chương trình đọc nhiều phần, đừng đóng một standard stream **được mượn** khi không sở hữu vòng đời của nó.

Tương tự, đóng `PrintWriter` hoặc `BufferedWriter` tự tạo quanh `System.out` có thể dẫn tới đóng luôn stdout, làm các lần in về sau thất bại. Với stream do caller cung cấp, API nên nói rõ có close hay chỉ flush hay không.

### `close()` so với `flush()`

`flush()` của buffered writer/stream đẩy dữ liệu đang đệm **xuống tầng bên dưới**, cho phép tiếp tục sử dụng. `close()` kết thúc vòng đời và thường flush dữ liệu còn chờ trong lúc đóng. **Không dùng `flush()` để thay `close()`** khi cần giải phóng descriptor; và **không coi `close()` là `FileChannel.force()`** để khẳng định dữ liệu đã ổn định trên thiết bị.

Nếu một giao thức yêu cầu gửi một message ngay trong khi stream còn mở, bạn có thể cần flush ở đúng ranh giới nghiệp vụ trước thời điểm close.

## 9. TWR và JDBC: đóng tài nguyên không phải commit transaction

Các tài nguyên JDBC như `Connection`, `Statement`, `PreparedStatement`, `ResultSet` có thể dùng với TWR vì triển khai `AutoCloseable`. Khai báo thứ tự thường là **Connection → Statement → ResultSet**, nhờ đó close diễn ra **ResultSet → Statement → Connection**.

Ví dụ hình thức:

```java
try (Connection conn = dataSource.getConnection();
     PreparedStatement stmt =
         conn.prepareStatement("SELECT id FROM items");
     ResultSet result = stmt.executeQuery()) {
    while (result.next()) {
        System.out.println(result.getLong("id"));
    }
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập: `dataSource`, bảng `items`, JDBC driver, import `java.sql.*` và xử lý `SQLException` phải có trong ứng dụng. Không thể dùng ví dụ này nếu chưa kết nối được database phù hợp.

Một điều rất quan trọng: **đóng Connection không phải cam kết transaction đã commit**. Với `autoCommit=false`, ứng dụng phải có chính sách commit/rollback rõ ràng. Hành vi khi đóng connection còn transaction chưa được giải quyết có thể tùy driver, pool và DBMS; không nên xây dựng quy trình tài chính dựa vào việc “close sẽ tự commit”.

Mẫu quản lý transaction thường:

```text
Mở connection → bắt đầu transaction
    → thực hiện thao tác
    ├─ thành công → commit
    └─ thất bại  → rollback (nếu còn có thể)
Cuối cùng → close / trả connection về pool
```

TWR giúp giải phóng tài nguyên; logic transaction vẫn thuộc về tầng nghiệp vụ/database.

Với connection pool, `Connection.close()` có thể trả logical connection về pool thay vì đóng hẳn kết nối vật lý. Đó là **chi tiết theo hợp đồng của pool/driver**, càng cho thấy `close()` là thao tác vòng đời abstraction, không phải luôn “đóng socket vật lý ngay”.

## 10. Xử lý ngoại lệ khi đóng

### Checked exceptions trong header và body

Nếu biến trong header có kiểu `AutoCloseable`, compiler biết rằng `close()` **có thể ném `Exception`**. Vì vậy phương thức chứa TWR phải khai báo hoặc bắt ngoại lệ phù hợp, ngay cả khi thân `try` có vẻ không ném:

```java
static void use(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("using");
    }
}
```

Đây là một **phương thức minh họa** (Java 9+) trong một lớp Java hợp lệ. `resource` là biến tham số effectively final, và `throws Exception` giải quyết chữ ký đóng tổng quát. Trong API ứng dụng, thường nên dùng kiểu resource cụ thể có `close()` khai báo ngoại lệ hẹp hơn thay vì yêu cầu mọi caller bắt `Exception` tổng quát.

Ngược lại, `Closeable` thường thu hẹp xuống `IOException`, nên chương trình có thể khai báo `throws IOException` khi dùng stream với các thao tác phù hợp.

### Khi nào `catch` và `finally` của TWR chạy?

```java
try (SomeResource r = create()) {
    work(r);
} catch (Exception ex) {
    report(ex);
} finally {
    markFinished();
}
```

Đây là **mã giả** mô tả thứ tự: tài nguyên `r` đã được đóng xong hoặc đã cố đóng xong **trước** khi chuyển tới `catch` bên ngoài phần thân resource và `finally` của câu lệnh. Nếu TWR đóng ném ngoại lệ khi thân không ném, `catch` có thể bắt lỗi đóng đó. Nếu thân đã ném, `catch` nhận primary với suppressed tương ứng.

Không đưa thêm một lời gọi `r.close()` không cần thiết trong `finally`: nó có thể đóng lại tài nguyên, gây lỗi hoặc làm khó hiểu ownership. Dùng `finally` cho hành động khác với vòng đời resource khi thật sự cần, và **tránh ném lỗi mới che khuất ngoại lệ chính**.

### Giới hạn của cleanup

TWR bảo đảm về **luồng điều khiển của ngôn ngữ Java trong thực thi bình thường**. Nó không bảo đảm:

- Máy không thể tắt điện hoặc tiến trình không thể bị kill trước khi `close()` hoàn thành.
- `close()` luôn thành công. Lỗi ở filesystem hoặc mạng vẫn có thể phát sinh.
- Một phương thức `close()` bên thứ ba sẽ không block vô hạn hoặc không có side effect.
- Khi resource được đóng, dữ liệu đã commit transaction, đồng bộ xuống đĩa hoặc xác nhận từ remote service.
- Resource có thể tái sử dụng sau khi đóng. Nhiều reader/stream/channel sẽ ném lỗi nếu tiếp tục dùng.

Vì vậy, nếu yêu cầu hệ thống là khả năng khôi phục sau crash, đảm bảo commit bền vững hoặc tính nguyên tử giữa các file, bạn vẫn cần thiết kế theo hợp đồng của filesystem, database hoặc giao thức tương ứng.

## 11. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Mở stream nhưng không đóng khi lỗi | Có thể rò file descriptor/handle | Khai báo resource trong TWR |
| Nghĩ GC tự đóng đúng lúc | GC không có lịch đảm bảo cleanup tài nguyên | Đóng chủ động khi kết thúc phạm vi |
| Chỉ đóng resource đầu tiên khi có nhiều resource | Resource còn lại có thể rò | TWR khai báo tất cả resource do scope sở hữu |
| Quên thứ tự đóng | Lớp ngoài phụ thuộc tầng dưới có thể cần đóng trước | TWR đóng ngược thứ tự khai báo |
| Gọi `close()` bằng tay bên trong TWR | Có nguy cơ đóng hai lần, `AutoCloseable` không bắt buộc idempotent | Để TWR đóng một lần trừ khi hợp đồng yêu cầu khác |
| Không quan sát `getSuppressed()` | Có thể bỏ sót lỗi khi cleanup | Log đầy đủ ngoại lệ khi cần chẩn đoán |
| Gọi `catch` xong nuốt hết lỗi | Có thể tiếp tục khi đọc/ghi/cleanup thất bại | Xác định retry, rollback, propagate hoặc báo lỗi |
| Dùng `finally` ném lỗi mới | Có thể che khuất lỗi gốc | TWR, tránh cleanup ném không kiểm soát |
| TWR quanh `System.in` trong thư viện | Có thể đóng stdin toàn cục của caller | Quản lý resource ownership |
| Đóng connection đồng nghĩa commit | Không đúng với transaction thủ công | Commit/rollback tường minh |
| Quên đóng `Files.lines`/`Files.walk` | File/directory handle có thể còn mở | `try (Stream<?> s = Files...)` |
| Dùng `flush()` thay `close()` | Flush không giải phóng mọi tài nguyên | Dùng TWR và flush chỉ khi cần đẩy dữ liệu sớm |
| Dùng `close()` để bảo đảm crash durability | Close không thay thế sync/fsync | Thiết kế durability riêng |
| Trả về resource đã được TWR đóng | Caller nhận object không còn dùng được | Không đặt vòng đời TWR bao resource cần trả |
| Bắt `Exception` quá rộng không cần thiết | Dễ giấu lỗi và làm API khó dùng | Chọn kiểu resource và checked exception phù hợp |
| Cấp tài nguyên cho nhiều owner | Một người đóng khiến người khác dùng lỗi | Quy định quyền sở hữu và chuyển giao rõ ràng |

### Lỗi tinh vi: trả object ra khỏi TWR

```java
static InputStream broken(Path path) throws IOException {
    try (InputStream in = Files.newInputStream(path)) {
        return in;
    }
}
```

Đây là **phản ví dụ về thiết kế**. Phương thức biên dịch, nhưng Java **đóng `in` trước khi hoàn tất trả về**. Caller nhận một stream đã đóng và thường không thể đọc. Có hai thiết kế đúng tùy ý định:

1. **Caller sẽ đọc**: trả về stream mới mở, ghi rõ caller sở hữu và phải đóng bằng TWR.
2. **Phương thức tự đọc**: đặt `InputStream` trong TWR, đọc đủ dữ liệu hoặc tạo đối tượng kết quả **không phụ thuộc** resource trước khi trả về.

Tương tự, không nên trả JDBC `ResultSet` ra khỏi một scope đã đóng `Statement` hoặc `Connection`.

## 12. Chiến lược thiết kế resource scope

Hãy phân loại resource theo ownership:

```text
Hàm hiện tại tự tạo tài nguyên
    └── Hàm chịu trách nhiệm đóng, nên dùng TWR.

Hàm nhận tài nguyên đang thuộc về caller
    └── Thường chỉ mượn để sử dụng, không tự đóng
        (trừ khi API nói rõ chuyển giao ownership).

Hàm tạo resource để caller dùng về sau
    └── Trả resource còn mở + tài liệu hướng dẫn caller đóng.

Wrapper sở hữu underlying resource
    └── Close wrapper ngoài cùng theo hợp đồng của wrapper.
```

Một mô hình phổ biến là **resource sống ngắn nhất có thể nhưng đủ cho toàn bộ thao tác cần nó**. Đừng mở connection từ đầu một request rồi giữ qua nhiều bước chờ không liên quan; cũng đừng đóng quá sớm khi lazy iterator, reader hoặc parser vẫn đang dùng.

Trong mã có callback hay asynchronous task, TWR có thể **đóng quá sớm** nếu phần thân chỉ *lên lịch* tác vụ rồi thoát, trong khi tác vụ nền vẫn cần resource. Khi đó, việc quản lý lifetime phải gắn với sự hoàn tất của tác vụ bất đồng bộ; không giả định callback sẽ chạy trước khi khối TWR kết thúc.

Một số thư viện cung cấp resource có thể đóng nhưng việc `close()` không idempotent, có side effect, có thể block hoặc ném exception; kiểm tra hợp đồng và đặt timeout/monitoring ở tầng thích hợp nếu có nguy cơ kẹt tài nguyên.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Closeable` khác `AutoCloseable` ở điểm cốt lõi nào?

**Đáp án:** `Closeable extends AutoCloseable`, `close()` khai báo `IOException` thay vì `Exception`, phù hợp nhiều loại I/O. `Closeable` có hợp đồng đóng lặp không hiệu lực; `AutoCloseable` không bắt buộc idempotent.

**Câu 2.** `try (A a = ...; B b = ...)` mở và đóng theo thứ tự nào?

**Đáp án:** Khởi tạo **a rồi b**, đóng **b rồi a**. Nếu khởi tạo b lỗi, a đã khởi tạo vẫn được đóng.

**Câu 3.** Thân `try` và `close()` đều ném lỗi, ngoại lệ nào là primary?

**Đáp án:** Lỗi thân là primary; lỗi lúc đóng được thêm vào `getSuppressed()`. Nếu thân thành công nhưng nhiều lần đóng lỗi, lỗi từ resource đóng đầu tiên là primary.

**Câu 4.** `Throwable.getCause()` có giống `getSuppressed()` không?

**Đáp án:** Không. Cause biểu thị nguyên nhân của một exception; suppressed chứa những exception được đính kèm, như lỗi phát sinh lúc đóng tài nguyên trong TWR.

**Câu 5.** Có thể dùng một biến khai báo bên ngoài TWR trong `try (resource)` ở Java 17 không?

**Đáp án:** Có, nếu biến là `final` hoặc effectively final (tính năng từ Java 9). Sau TWR, biến còn scope nhưng resource đã đóng.

**Câu 6.** Vì sao không đóng `System.in` trong library?

**Đáp án:** Đây thường là tài nguyên toàn cục do ứng dụng/caller sở hữu; thư viện đóng wrapper trên `System.in` có thể đóng luôn input chuẩn, làm phần khác không thể tiếp tục đọc.

**Câu 7.** `Files.lines(path)` có nên đưa trong TWR dù có terminal operation `count()` không?

**Đáp án:** Có. Stream đọc file có nguồn tài nguyên cần đóng; terminal operation không tự thay thế vòng đời close của stream.

**Câu 8.** Một `Connection` được TWR đóng có bảo đảm các lệnh ghi database đã commit không?

**Đáp án:** Không. Transaction phải theo chính sách commit/rollback riêng; close chỉ kết thúc vòng đời logical/physical connection theo driver và pool.

**Câu 9.** Khi nào không nên dùng TWR quanh một resource mới tạo?

**Đáp án:** Khi mục tiêu là **trả resource còn mở** cho caller để sử dụng về sau; lúc đó caller phải nhận ownership và có trách nhiệm đóng. Không trả một stream đã bị TWR đóng.

**Câu 10.** Có thể dùng TWR như bằng chứng file đã được lưu bền vững sau mất điện không?

**Đáp án:** Không. Đóng stream/writer là vấn đề vòng đời; durability cần đánh giá cơ chế đồng bộ xuống filesystem và thiết bị cùng yêu cầu nghiệp vụ.

**Ghi nhớ:** `AutoCloseable` định nghĩa khả năng đóng tài nguyên; `Closeable` chuyên biệt cho I/O; `try-with-resources` đưa việc đóng vào cấu trúc ngôn ngữ, theo **thứ tự ngược khi khởi tạo** và bảo toàn ngoại lệ chính qua **suppressed exceptions**. Muốn dùng đúng, hãy xác định **ai sở hữu tài nguyên, phạm vi sử dụng, chính sách xử lý lỗi và thời điểm đóng** — không dựa vào garbage collector hoặc đồng nhất close với commit/durability.
