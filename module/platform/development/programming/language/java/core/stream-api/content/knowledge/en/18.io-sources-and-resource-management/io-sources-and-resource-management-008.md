# Đóng nguồn khi dừng sớm hoặc khi pipeline phát sinh ngoại lệ

## Mục tiêu

Khi dùng **Java Stream API** để xử lý dữ liệu khai báo, ta thường ghép các bước `filter`, `map`, `reduce`, `collect` thành một pipeline rồi kích hoạt xử lý bằng terminal operation. Đối với nguồn từ tệp hoặc thư mục, việc xử lý lười (*lazy evaluation*) đặt ra một trách nhiệm bổ sung: **đóng tài nguyên I/O dù pipeline kết thúc bình thường, dừng sớm hay ném ngoại lệ**.

Sau bài học này, bạn có thể:

- Giải thích vì sao `findFirst()`, `anyMatch()` hoặc `limit(...)` không tự đóng tệp đang mở.
- Đặt `try-with-resources` đúng phạm vi để nguồn được đóng cả khi `return` hoặc có ngoại lệ.
- Phân biệt ngoại lệ lúc mở nguồn với ngoại lệ phát sinh khi stream đọc dữ liệu lười.
- Xác định tài nguyên thật sự cần đóng, kể cả khi stream được tạo từ `BufferedReader`.
- Thiết kế phương thức trả về kết quả an toàn, không để rò rỉ tài nguyên hoặc trả ra stream đã đóng.

## 1. Kết thúc pipeline khác với đóng tài nguyên

Stream gồm **nguồn dữ liệu**, các thao tác trung gian (*intermediate operations*) và một thao tác kết thúc (*terminal operation*). Phần lớn thao tác trung gian chỉ mô tả cách xử lý; dữ liệu được lấy từ nguồn khi thao tác kết thúc chạy.

Với `List.stream()` hoặc `Stream.of(...)`, thường không có tài nguyên hệ điều hành cần giải phóng. Nhưng những API như `Files.lines(...)`, `Files.list(...)` hay `Files.walk(...)` có thể giữ tệp, luồng thư mục hoặc handle hệ điều hành đang mở. Java Stream triển khai `AutoCloseable` để người gọi chủ động đóng các nguồn như vậy.

```text
Mở nguồn I/O
    |
    v
Stream (có thể giữ file descriptor / directory handle)
    |
    +--> filter / map / ... (xử lý lười)
    |
    +--> terminal operation
             |
             +--> đọc hết dữ liệu
             +--> dừng sớm (short-circuit)
             +--> phát sinh ngoại lệ
                         |
                         v
             Không có bước tự động close ở đây
                         |
                         v
             Đóng nguồn bằng try-with-resources
```

Một terminal operation **tiêu thụ** pipeline; nó không mặc nhiên gọi `Stream.close()`. Ngay cả khi đã đọc đến cuối tệp, không nên suy đoán tài nguyên được đóng. Vì thế, phải quản lý vòng đời của nguồn I/O một cách tường minh.

| Nguồn stream | Tài nguyên cần quản lý | Cách quản lý |
| --- | --- | --- |
| `Stream.of(...)`, `list.stream()` | Thông thường không có handle I/O | Không cần `try-with-resources` chỉ để đóng nguồn này |
| `Files.lines(path)` | Tệp đang mở phục vụ việc đọc lười | Đóng `Stream<String>` |
| `Files.list(dir)` | Tài nguyên duyệt thư mục | Đóng `Stream<Path>` |
| `Files.walk(dir)`, `Files.find(...)` | Tài nguyên duyệt cây thư mục | Đóng `Stream<Path>` |
| `reader.lines()` từ `BufferedReader` | Chính `BufferedReader` sở hữu nguồn đọc | Đóng `BufferedReader`; đừng chỉ trông chờ vào `Stream.close()` |

Quy tắc thực dụng: **nguồn nào mở tài nguyên thì phải xác định rõ ai sở hữu và ai đóng nó**. Với một stream trả về bởi API I/O, hãy đọc hợp đồng của API và thường bọc stream đó bằng `try-with-resources`.

## 2. Dừng sớm vẫn phải đóng nguồn

Các thao tác `findFirst()`, `findAny()`, `anyMatch()`, `allMatch()` và `noneMatch()` có thể dừng sau khi đã đọc một phần dữ liệu. `limit(n)` và `takeWhile(...)` là *intermediate operations* có thể khiến việc tiêu thụ ở downstream kết thúc sớm. Khả năng dừng sớm còn phụ thuộc các bước khác của pipeline; chẳng hạn, `sorted()` thường cần nhìn toàn bộ đầu vào trước khi trả kết quả.

Giả sử cần tìm dòng đầu tiên chứa mã lỗi trong một tệp log lớn:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public class LogSearch {
    public static Optional<String> firstError(Path logFile) throws IOException {
        try (Stream<String> lines = Files.lines(logFile, StandardCharsets.UTF_8)) {
            return lines
                    .map(String::trim)
                    .filter(line -> line.contains("ERROR"))
                    .findFirst();
        }
    }
}
```

Điều gì xảy ra?

1. `Files.lines(...)` mở nguồn đọc và trả về stream có thể đóng.
2. `map` và `filter` chưa đọc tệp ngay; `findFirst()` mới kích hoạt pipeline.
3. Khi thấy dòng lỗi đầu tiên, `findFirst()` có thể dừng mà không đọc phần còn lại.
4. Khi rời khối `try`, Java gọi `close()`, kể cả trường hợp có `return` ở bên trong.
5. Giá trị `Optional<String>` chứa dữ liệu đã thu được nên vẫn dùng được sau khi tệp đóng.

**Phản ví dụ – để nguồn mở sau khi dừng sớm:**

```java
// Không nên: terminal operation không tự đóng stream của Files.lines.
Optional<String> result = Files.lines(logFile, StandardCharsets.UTF_8)
        .filter(line -> line.contains("ERROR"))
        .findFirst();
```

Lệnh trên có thể trả đúng kết quả, nhưng không bảo đảm tài nguyên tệp được giải phóng đúng lúc. Nếu gọi lặp đi lặp lại, ứng dụng có thể tích lũy file descriptor/handle, gặp lỗi mở tệp hoặc bị cản trở khi đổi tên, xóa tệp trên một số hệ điều hành.

Mẫu tương tự áp dụng cho việc tìm một tệp đầu tiên trong cây thư mục:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public static Optional<Path> firstJavaFile(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .findFirst();
    }
}
```

Khi `findFirst()` dừng sớm, việc duyệt cây còn dang dở; đóng stream là bước cần thiết để giải phóng những tài nguyên mà `Files.walk` đang giữ. Đừng dựa vào việc thao tác kết thúc đã trả về `Optional<Path>`.

## 3. Ngoại lệ trong pipeline cũng phải đóng nguồn

Ngoại lệ có thể đến từ nhiều vị trí:

- **Khi mở nguồn:** `Files.lines(path)` hoặc `Files.walk(path)` có thể ném `IOException`.
- **Khi đọc lười:** lỗi I/O xảy ra lúc terminal operation tiêu thụ dữ liệu thường được bọc trong `UncheckedIOException`.
- **Trong logic xử lý:** hàm truyền cho `map`, `filter`, `forEach` hay collector có thể ném ngoại lệ runtime, ví dụ `IllegalArgumentException`.
- **Khi đóng:** thao tác giải phóng tài nguyên hoặc close handler cũng có thể ném ngoại lệ.

`try-with-resources` giúp bảo đảm gọi `close()` khi thoát khỏi khối, kể cả khi một bước của pipeline ném ngoại lệ:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countValidRecords(Path input) throws IOException {
    try (Stream<String> lines = Files.lines(input, StandardCharsets.UTF_8)) {
        return lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .map(line -> {
                    if (line.equals("INVALID")) {
                        throw new IllegalArgumentException("Bản ghi không hợp lệ");
                    }
                    return line;
                })
                .count();
    } // Stream được đóng dù count() ném IllegalArgumentException.
}
```

Điểm quan trọng: `catch` **không phải điều kiện để tài nguyên được đóng**. Khối `try-with-resources` tự thực hiện việc đóng khi thoát khỏi `try`. Bạn chỉ thêm `catch` khi cần chuyển đổi, ghi nhận hoặc xử lý ngoại lệ ở tầng thích hợp.

Chẳng hạn, để phân biệt lỗi mở tệp và lỗi đọc phát sinh muộn:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.count();
    } catch (UncheckedIOException ex) {
        // Lỗi I/O xảy ra khi stream đang được tiêu thụ.
        throw ex.getCause();
    }
    // IOException lúc mở nguồn đã là checked exception,
    // được khai báo bởi throws IOException ở chữ ký phương thức.
}
```

Trong thực tế, cách API và thao tác cụ thể đọc dữ liệu có thể khác nhau; đừng giả định mọi lỗi I/O trong pipeline đều xuất hiện dưới dạng checked `IOException`. Khi cần bao quát, xem xét cả `UncheckedIOException` ở lúc thực hiện terminal operation.

### Nếu xử lý lỗi và đóng nguồn cùng thất bại?

Giả sử `map` ném một ngoại lệ, rồi `close()` cũng ném ngoại lệ khi giải phóng tài nguyên. Với `try-with-resources`, ngoại lệ ban đầu từ khối `try` vẫn là ngoại lệ chính; ngoại lệ khi đóng thường được lưu trong danh sách *suppressed exceptions*, truy xuất qua `getSuppressed()`. Điều này giúp giữ nguyên nguyên nhân gây thất bại đầu tiên.

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(line -> process(line));
} catch (RuntimeException ex) {
    System.err.println("Lỗi chính: " + ex);
    for (Throwable suppressed : ex.getSuppressed()) {
        System.err.println("Lỗi khi đóng tài nguyên: " + suppressed);
    }
    throw ex;
}
```

Ở ví dụ này, `process` là một hàm xử lý do ứng dụng cung cấp. Nếu dùng `catch` rồi bỏ qua ngoại lệ, chương trình có thể che mất lỗi nghiệp vụ hoặc lỗi I/O. Nên ghi nhận đủ ngữ cảnh và để tầng thích hợp quyết định cách phục hồi.

## 4. Đóng đúng đối tượng sở hữu tài nguyên

Đối tượng cần đóng không phải lúc nào cũng là đối tượng `Stream`.

### `Files.lines()`: stream quản lý việc đóng nguồn

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(line -> !line.isBlank()).forEach(System.out::println);
}
```

Trong trường hợp này, đóng stream từ `Files.lines` là đúng hợp đồng API.

### `BufferedReader.lines()`: đóng reader

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static boolean hasHeader(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .anyMatch(line -> line.startsWith("HEADER:"));
    }
}
```

Ở đây, chính `BufferedReader` là tài nguyên cần đóng. Không nên giả định gọi `close()` trên stream sinh bởi `reader.lines()` sẽ đóng reader. Bọc `BufferedReader` trong `try-with-resources` giúp giữ quyền sở hữu và thời điểm đóng rõ ràng, kể cả khi `anyMatch()` kết thúc sớm.

### Nếu phương thức tạo stream cho bên gọi thì sao?

Đoạn sau dễ gây rò rỉ vì không xác định rõ ai đóng:

```java
// Không nên nếu hợp đồng API không buộc caller đóng stream.
static Stream<String> errorLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8)
            .filter(line -> line.contains("ERROR"));
}
```

Nếu phương thức cần trả kết quả sẵn sàng sử dụng, hãy tiêu thụ dữ liệu khi nguồn còn mở rồi trả về giá trị độc lập:

```java
static java.util.List<String> loadErrors(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.contains("ERROR"))
                .toList();
    }
}
```

Nếu thực sự cần trả một stream lười để xử lý từ bên ngoài, API phải nêu rõ **caller sở hữu trách nhiệm đóng** và bên gọi phải dùng `try-with-resources`:

```java
try (Stream<String> errors = errorLines(path)) {
    errors.limit(10).forEach(System.out::println);
}
```

Không được tạo stream trong khối `try`, đóng tài nguyên, rồi trả stream đó để tiêu thụ sau: pipeline lười sẽ truy cập nguồn đã đóng. Việc chọn trả `List` hay trả `Stream` có hợp đồng đóng rõ ràng phụ thuộc nhu cầu bộ nhớ, độ trễ và khả năng xử lý dữ liệu lớn.

## 5. `onClose()` hữu ích, nhưng không tự động kích hoạt

`BaseStream.onClose(Runnable)` đăng ký một hành động sẽ chạy **khi stream được đóng**. Nó hữu ích để ghi log, đếm lần đóng hoặc dọn tài nguyên phụ trong pipeline do mình xây dựng. Tuy nhiên, `findFirst()`, `count()` hoặc `forEach()` không tự gọi close handler này.

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

AtomicBoolean closed = new AtomicBoolean(false);

try (Stream<Integer> numbers = Stream.of(10, 20, 30)
        .onClose(() -> closed.set(true))) {
    boolean found = numbers.anyMatch(number -> number == 10);
    System.out.println(found); // true: dừng sau khi khớp phần tử đầu
}

System.out.println(closed.get()); // true: do try-with-resources gọi close()
```

Đây là ví dụ kiểm tra callback, không mô phỏng file descriptor thật. Với `Files.lines`, `onClose` chỉ nên bổ sung hành vi cần thiết; vẫn phải bảo đảm stream được đóng bằng cơ chế quản lý vòng đời thích hợp. Nếu nhiều close handler ném ngoại lệ, Java thực hiện các handler và có thể giữ ngoại lệ phụ dưới dạng suppressed.

## 6. Các lỗi thiết kế dễ gặp

| Tình huống | Vấn đề | Cách làm đúng |
| --- | --- | --- |
| Gọi `Files.lines(...).findFirst()` trực tiếp | Dừng sớm nhưng nguồn có thể còn mở | Bọc stream nguồn trong `try-with-resources` |
| Nghĩ `forEach()` hoặc `collect()` tự đóng | Terminal operation không bảo đảm đóng tài nguyên | Đóng nguồn cả khi xử lý hết dữ liệu |
| Gọi `stream.close()` sau dòng xử lý | Nếu dòng xử lý ném ngoại lệ, lệnh `close()` bị bỏ qua | Dùng `try-with-resources` |
| Bọc `reader.lines()` nhưng không đóng reader | Có thể bỏ sót tài nguyên thật sự sở hữu nguồn | Bọc `BufferedReader` trong `try-with-resources` |
| Trả stream vừa tạo trong khối `try` đã kết thúc | Caller nhận stream dựa trên nguồn đã đóng | Trả kết quả đã materialize hoặc chuyển rõ trách nhiệm đóng cho caller |
| Chỉ xử lý `IOException` khi đọc bằng `Files.lines` | Lỗi đọc lười có thể được bọc thành `UncheckedIOException` | Xem xét cả ngoại lệ được bọc |
| Dùng `parallel()` và nghĩ việc đóng tự xảy ra | Parallelism không thay đổi hợp đồng quản lý tài nguyên | Đóng nguồn sau terminal operation, xem lại chi phí I/O |

Việc sử dụng `parallelStream()` hoặc `stream.parallel()` không thay đổi quy tắc vòng đời: nếu nguồn giữ tài nguyên, nó vẫn phải được đóng. Cần đo đạc trước khi song song hóa I/O vì chi phí đồng bộ, đọc đĩa và xử lý lỗi có thể lớn hơn lợi ích.

## 7. Checklist áp dụng khi viết code thực tế

Khi review một pipeline đọc tệp hoặc thư mục, hãy tự hỏi:

1. **Nguồn đến từ đâu?** `Files.lines`, `Files.walk`, `BufferedReader` hay chỉ từ collection trong bộ nhớ?
2. **Ai sở hữu tài nguyên?** Là stream do API trả về, reader bên dưới hay một đối tượng khác?
3. **Chỗ nào phát sinh terminal operation?** `findFirst` và các phép dừng sớm đã nằm trong phạm vi `try-with-resources` chưa?
4. **Nếu pipeline ném ngoại lệ thì sao?** Tài nguyên có vẫn được đóng? Lỗi đọc lười được báo cáo đúng dạng chưa?
5. **Giá trị trả về có còn cần tài nguyên không?** `String`, `Optional<String>`, `List<String>` đã thu thập có thể tồn tại sau `close`; stream lười thì cần một vòng đời rõ ràng.

Ví dụ hoàn chỉnh kết hợp tìm sớm, đóng nguồn và xử lý lỗi đọc lười:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public final class AuditLog {
    private AuditLog() {}

    public static Optional<String> firstWarning(Path file) throws IOException {
        try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
            return lines
                    .map(String::trim)
                    .filter(line -> line.startsWith("WARN"))
                    .findFirst();
        } catch (UncheckedIOException ex) {
            throw ex.getCause(); // trả lỗi đọc I/O về hợp đồng throws IOException
        }
    }
}
```

Hàm này phù hợp cho log lớn vì thường chỉ đọc đến dòng `WARN` đầu tiên; đồng thời nguồn vẫn được đóng nếu không tìm thấy dòng nào hoặc phát sinh ngoại lệ. Việc trả `Optional<String>` giúp caller không phải quản lý một stream còn gắn với tệp.

**Ghi nhớ:** Trong Java Stream API, *short-circuiting* quyết định có thể dừng **đọc dữ liệu** sớm đến đâu; `try-with-resources` quyết định **khi nào tài nguyên được đóng**. Hai cơ chế phục vụ hai mục đích độc lập và thường phải dùng cùng nhau khi pipeline làm việc với nguồn I/O.
