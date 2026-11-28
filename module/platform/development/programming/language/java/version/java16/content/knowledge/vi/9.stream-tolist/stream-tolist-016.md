# Phân biệt kết thúc Stream với đóng tài nguyên của nguồn I/O

`Stream.toList()` là terminal operation: nó tiêu thụ pipeline và trả về một danh sách chứa các phần tử đã phát ra. Nhưng **kết thúc pipeline không đồng nghĩa với đóng tài nguyên nguồn**. Với stream đọc file hoặc duyệt thư mục như `Files.lines()`, `Files.list()` và `Files.walk()`, ứng dụng vẫn phải đóng stream, thường bằng `try-with-resources`.

Hãy phân biệt hai trạng thái: stream đã được tiêu thụ bởi terminal operation và stream đã được đóng bằng `close()`. Một stream có thể đã tiêu thụ hết dữ liệu nhưng tài nguyên I/O vẫn mở. Ngược lại, gọi `close()` sẽ đóng tài nguyên và chạy close handler mà không tự xử lý các phần tử còn lại.

## 1. Terminal operation tiêu thụ stream, không tự đóng stream

Các thao tác như `toList()`, `collect()`, `forEach()`, `count()` và `findFirst()` là terminal operation. Chúng kích hoạt pipeline và khiến stream không thể được sử dụng lại.

```java
import java.util.List;
import java.util.stream.Stream;

Stream<String> stream = Stream.of("An", "Bình", "Chi");
List<String> names = stream.toList();

System.out.println(names); // [An, Bình, Chi]

// stream đã được tiêu thụ; không được sử dụng lại.
// Nếu cố dùng lại, implementation có thể ném IllegalStateException.
```

Việc stream đã được tiêu thụ không có nghĩa `close()` đã được gọi. `Stream` kế thừa `AutoCloseable` thông qua `BaseStream`, nên có thể được đóng tường minh. Tuy nhiên, terminal operation không tự động gọi `close()` sau khi hoàn tất.

Với stream từ collection như `list.stream()`, thường không có tài nguyên bên ngoài cần giải phóng. Với stream được tạo từ file hoặc thư mục, việc đóng rất quan trọng vì stream giữ tài nguyên I/O mở trong lúc đọc.

## 2. Stream từ `Files.lines()` phải được đóng

`Files.lines()` tạo stream đọc các dòng của file. Việc đọc diễn ra lazy khi terminal operation tiêu thụ stream; stream giữ file mở và phải được đóng sau khi sử dụng.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

class LineReader {
    static List<String> readAll(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.toList();
        }
    }
}
```

Khi `toList()` hoàn tất, các dòng đã được đưa vào danh sách. Sau đó khối `try` kết thúc và `try-with-resources` gọi `close()` trên stream, giải phóng tài nguyên file. Danh sách `List<String>` đã tạo vẫn có thể được sử dụng sau khi file đóng vì nó chứa dữ liệu đã materialize.

`Files.lines()` ném `IOException` nếu không thể mở file. Nếu xảy ra lỗi I/O trong lúc stream đang đọc, lỗi được chuyển thành `UncheckedIOException`. Khai báo `throws IOException` trong ví dụ để caller xử lý lỗi mở file theo hợp đồng của ứng dụng.

## 3. Không viết `Files.lines(...).toList()` mà bỏ qua việc đóng

Đoạn mã ngắn sau có thể đọc được dữ liệu nhưng không thể hiện việc đóng stream:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

class UnsafeLineReader {
    static List<String> readAll(Path path) throws IOException {
        // Không quản lý close() cho stream được tạo từ file.
        return Files.lines(path, StandardCharsets.UTF_8).toList();
    }
}
```

Terminal operation đã tiêu thụ stream, nhưng không tự gọi `close()`. Tài nguyên file vì thế có thể vẫn mở cho đến khi được đóng rõ ràng hoặc quá trình thực thi kết thúc. Trong ứng dụng chạy lâu, việc bỏ quên nhiều stream như vậy có thể giữ file descriptor và tài nguyên hệ điều hành lâu hơn cần thiết.

Hãy đặt stream trong `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

class SafeLineReader {
    static List<String> readAll(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            List<String> result = lines.toList();
            System.out.println("Số dòng: " + result.size());
            return result;
        }
    }
}
```

`try-with-resources` gọi `close()` khi rời khỏi khối, dù khối kết thúc bình thường hay do exception. Điều này giúp tài nguyên được giải phóng trên cả đường chạy thành công lẫn đường chạy lỗi.

## 4. `findFirst()` hoặc `limit()` dừng sớm cũng không thay thế `close()`

Một terminal operation có short-circuit như `findFirst()` có thể dừng đọc trước khi nguồn được tiêu thụ hết. Nhưng dừng xử lý không đồng nghĩa với đóng tài nguyên.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

class FirstLineReader {
    static Optional<String> firstLine(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.findFirst();
        }
    }
}
```

Kể cả khi `findFirst()` chỉ đọc một dòng, khối `try` vẫn đóng stream và file. Quy tắc tương tự áp dụng cho `limit(1).toList()`, `anyMatch()` và các terminal operation có thể kết thúc sớm khác.

Không dựa vào việc stream đã đọc hết hay chưa để quyết định có cần đóng. Nếu stream sở hữu tài nguyên, hãy đóng nó sau khi hoàn tất công việc.

## 5. `Files.list()` và `Files.walk()` cũng trả về stream cần đóng

Các API duyệt thư mục cũng tạo stream gắn với tài nguyên hệ thống. Hãy quản lý chúng bằng `try-with-resources`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

class DirectoryReader {
    static List<Path> listFiles(Path directory) throws IOException {
        try (Stream<Path> paths = Files.list(directory)) {
            return paths
                .filter(Files::isRegularFile)
                .toList();
        }
    }
}
```

`Files.list()` chỉ liệt kê các entry trực tiếp trong thư mục. `Files.walk()` duyệt cây thư mục theo độ sâu, nên có thể đọc nhiều entry hơn và giữ tài nguyên mở trong suốt quá trình duyệt:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

class TreeReader {
    static List<Path> javaFiles(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .toList();
        }
    }
}
```

Danh sách `Path` được trả về vẫn dùng được sau khi stream đóng. Tuy nhiên, việc thu thập toàn bộ đường dẫn vẫn cần bộ nhớ tỷ lệ với số entry; nếu cây thư mục rất lớn và chỉ cần xử lý từng file, hãy xử lý trong khối `try` thay vì materialize tất cả.

## 6. Đóng stream ngay cả khi xử lý phát sinh exception

Ưu điểm quan trọng của `try-with-resources` là tài nguyên được đóng ngay cả khi terminal operation hoặc logic xử lý ném exception:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

class FileProcessor {
    static void process(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            lines.forEach(line -> {
                if (line.isBlank()) {
                    throw new IllegalArgumentException("Dòng không được để trống");
                }
                System.out.println(line);
            });
        }
    }
}
```

Nếu gặp dòng trống, lambda ném `IllegalArgumentException` và quá trình duyệt dừng. Khi rời khỏi khối `try`, stream vẫn được đóng. Nếu quá trình đóng cũng phát sinh exception trong lúc một exception chính đang được ném, Java quản lý exception đóng như suppressed exception theo quy tắc try-with-resources.

Không nên tự viết `close()` trong một nhánh riêng sau terminal operation; nhánh exception có thể bỏ qua lời gọi đó. `try-with-resources` làm cho vòng đời tài nguyên rõ ràng và an toàn hơn.

## 7. `onClose()` đăng ký hành động khi đóng, không phải khi terminal operation kết thúc

`onClose()` đăng ký một close handler. Handler chỉ chạy khi stream được đóng bằng `close()`; gọi `toList()` hoặc `count()` không tự kích hoạt handler.

```java
import java.util.List;
import java.util.stream.Stream;

try (Stream<String> names = Stream.of("An", "Bình")
        .onClose(() -> System.out.println("Stream đã đóng"))) {
    List<String> result = names.toList();
    System.out.println(result); // [An, Bình]
    // Close handler chưa chạy tại đây.
}
// Khi rời khỏi try, close() được gọi và handler chạy.
```

`onClose()` hữu ích khi xây dựng abstraction có tài nguyên cần giải phóng hoặc khi cần quan sát thời điểm đóng. Nó không thay thế `try-with-resources`: nơi sở hữu stream vẫn phải bảo đảm gọi `close()`.

## 8. Phân biệt `toList()`, `close()` và `try-with-resources`

| Cơ chế | Vai trò | Có giải phóng tài nguyên I/O không? |
| --- | --- | --- |
| `toList()` | Tiêu thụ pipeline và thu phần tử thành danh sách unmodifiable | Không tự đóng stream. |
| `findFirst()`, `anyMatch()` | Tiêu thụ pipeline; có thể dừng sớm | Không tự đóng stream. |
| `close()` | Đóng stream và chạy close handlers đã đăng ký | Có, nếu stream có close handler quản lý tài nguyên. |
| `onClose(handler)` | Đăng ký hành động chạy khi stream được đóng | Không tự đóng; chỉ đăng ký handler. |
| `try-with-resources` | Tự gọi `close()` khi rời khỏi phạm vi | Có, thông qua `close()` của resource. |

Vòng đời điển hình của stream đọc file:

```text
Mở nguồn I/O
    |
    v
Tạo Stream<String>
    |
    v
Thực hiện pipeline (lazy)
    |
    v
Terminal operation: toList() / findFirst() / forEach()
    |
    v
Rời khỏi try-with-resources
    |
    v
close() và giải phóng tài nguyên
```

Terminal operation đánh dấu việc tiêu thụ stream. `close()` đánh dấu việc đóng stream. Hai việc này có liên quan trong vòng đời sử dụng nhưng là hai hành động riêng biệt.

## 9. Xác định ai chịu trách nhiệm đóng stream

Khi tạo và sử dụng stream trong cùng một phương thức, phương thức đó có thể quản lý tài nguyên bằng try-with-resources. Khi trả stream ra ngoài, cần xác định rõ quyền sở hữu: bên tạo stream thường phải ghi rõ caller có trách nhiệm đóng stream hay không.

Ví dụ một factory mở file và trả stream cho caller:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

class FileStreams {
    /** Caller must close the returned stream. */
    static Stream<String> openLines(Path path) throws IOException {
        return Files.lines(path, StandardCharsets.UTF_8);
    }
}
```

Caller phải đóng stream:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

class FileStreamsClient {
    static List<String> readAll(Path path) throws IOException {
        try (Stream<String> lines = FileStreams.openLines(path)) {
            List<String> allLines = lines.toList();
            System.out.println("Số dòng: " + allLines.size());
            return allLines;
        }
    }
}
```

Nếu một phương thức nhận stream từ caller, không nên tự ý đóng stream đó trừ khi hợp đồng phương thức quy định rõ việc chuyển quyền sở hữu. Ví dụ phương thức chỉ tiêu thụ dữ liệu:

```java
import java.util.List;
import java.util.stream.Stream;

class StreamNormalizer {
    static List<String> normalize(Stream<String> input) {
        return input
            .map(String::trim)
            .toList();
    }
}
```

Phương thức `normalize()` tiêu thụ stream nhưng không đóng nó. Caller đã tạo stream vẫn chịu trách nhiệm đóng nếu stream gắn với tài nguyên:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

class NormalizeClient {
    static List<String> readAndNormalize(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            List<String> normalized = StreamNormalizer.normalize(lines);
            System.out.println("Số dòng: " + normalized.size());
            return normalized;
        }
    }
}
```

Quy tắc này giúp tránh hai lỗi: rò rỉ tài nguyên khi không ai đóng stream và đóng stream quá sớm khi một thành phần không sở hữu tài nguyên lại tự ý gọi `close()`.

## 10. Những điểm cần nhớ

- `toList()` là terminal operation; nó tiêu thụ stream nhưng không tự gọi `close()`.
- Stream từ `Files.lines()`, `Files.list()` và `Files.walk()` phải được đóng.
- Dùng `try-with-resources` để đóng stream cả khi xử lý thành công lẫn khi có exception.
- `findFirst()`, `anyMatch()` hoặc `limit()` dừng sớm cũng không thay thế việc đóng tài nguyên.
- Danh sách đã tạo bằng `toList()` vẫn dùng được sau khi stream và file nguồn được đóng.
- `onClose()` chỉ đăng ký handler; handler chạy khi có lời gọi `close()`.
- Khi trả stream cho caller, ghi rõ ai chịu trách nhiệm đóng; khi nhận stream, tôn trọng quyền sở hữu theo hợp đồng.

Hãy xem việc tiêu thụ dữ liệu và giải phóng tài nguyên là hai trách nhiệm riêng. Gọi `toList()` khi cần danh sách kết quả; dùng `try-with-resources` để quản lý vòng đời stream có tài nguyên I/O. Cách này ngăn rò rỉ file descriptor và giúp ứng dụng hoạt động ổn định khi xử lý file hoặc thư mục trong thời gian dài.

## Tài liệu tham khảo

- [Stream.toList() và BaseStream.close() – Java SE 16 API](https://docs.oracle.com/en/java/javase/16/docs/api/java.base/java/util/stream/Stream.html)
- [BaseStream – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/BaseStream.html)
- [Files.lines() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset))
- [Files.list() và Files.walk() – Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html)
- [The try-with-resources Statement – Java Tutorials](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
