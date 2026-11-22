# Nhận biết stream gắn tài nguyên và đóng đúng vòng đời trong Java 17

Stream API giúp xử lý dữ liệu theo pipeline: lọc, ánh xạ, sắp xếp, gom nhóm hoặc tính toán kết quả. Nhưng không phải stream nào cũng chỉ là một chuỗi phần tử nằm trong bộ nhớ. Một số stream giữ **tài nguyên bên ngoài** như file, thư mục, reader hoặc nguồn dữ liệu có vòng đời riêng. Nếu không đóng chúng đúng lúc, ứng dụng có thể giữ file handle, directory handle hoặc kết nối lâu hơn cần thiết.

Trong Java 17, hợp đồng chung `BaseStream` cung cấp `close()` và `onClose(...)`. Những API như `Files.lines`, `Files.list`, `Files.walk` và `Files.find` trả về stream gắn với tài nguyên I/O; người gọi phải đảm bảo stream được đóng. Cách thông dụng nhất là dùng **try-with-resources**.

Bài này tập trung vào cách nhận biết stream có tài nguyên, hiểu khi nào terminal operation kết thúc nhưng tài nguyên vẫn mở, đóng đúng chủ sở hữu, xử lý lỗi và thiết kế API không làm rò rỉ stream.

## 1. Không phải stream nào cũng giữ tài nguyên

Hai ví dụ sau đều trả về `Stream<String>`, nhưng vòng đời khác nhau:

~~~java
Stream<String> inMemory =
        List.of("An", "Bình", "Chi").stream();

Stream<String> fromFile = Files.lines(Path.of("names.txt"));
~~~

Stream đầu tiên đọc từ collection trong bộ nhớ. Nó không mở file hoặc kết nối I/O. Stream thứ hai đọc nội dung file và giữ tài nguyên file trong lúc pipeline hoạt động.

| Nguồn tạo stream | Có tài nguyên bên ngoài cần đóng? | Cách xử lý |
| --- | --- | --- |
| `collection.stream()` | Thông thường không | Không cần try-with-resources chỉ để đóng stream |
| `Arrays.stream(array)` | Không | Không cần đóng |
| `Stream.of(...)` | Không | Không cần đóng |
| `IntStream.range(...)` | Không | Không cần đóng |
| `Files.lines(path)` | Có, reader/file | Đóng stream |
| `Files.list(path)` | Có, directory stream | Đóng stream |
| `Files.walk(path)` | Có, directory traversal | Đóng stream |
| `Files.find(path, ...)` | Có, directory traversal | Đóng stream |
| `BufferedReader.lines()` | Reader được dùng làm nguồn | Đóng `BufferedReader` sở hữu reader |
| Stream từ API ngoài | Tùy hợp đồng API | Đọc tài liệu và đóng đúng resource owner |

Điểm quan trọng là **kiểu trả về `Stream<T>` không cho biết stream có tài nguyên hay không**. Cần xem API tạo stream và hợp đồng ownership của nó.

## 2. Vì sao terminal operation không tự đóng stream?

Stream pipeline thường có hai nhóm thao tác:

- **Intermediate operation:** `filter`, `map`, `sorted`, `distinct`, `limit`... tạo pipeline tiếp theo và thường được thực thi lazy.
- **Terminal operation:** `forEach`, `count`, `collect`, `toList`, `findFirst`, `anyMatch`... kích hoạt xử lý và tiêu thụ stream.

Một hiểu nhầm phổ biến là sau `count()` hoặc `forEach()`, stream tự động đóng tài nguyên. Điều đó **không đúng**. Terminal operation tiêu thụ pipeline; nó không thay thế lời gọi `close()`.

~~~java
Stream<String> lines = Files.lines(Path.of("names.txt"));

long count = lines.count(); // Đọc hết dữ liệu.
                                // File stream vẫn cần được đóng.
~~~

Ngay cả thao tác short-circuit như `findFirst()` hoặc `anyMatch()` cũng không đảm bảo đóng stream:

~~~java
Stream<String> lines = Files.lines(Path.of("large.txt"));

Optional<String> first = lines.findFirst();
// Chỉ đọc phần cần thiết; tài nguyên vẫn cần đóng.
~~~

Đây là lý do phải đặt resource-backed stream trong một cấu trúc quản lý vòng đời, thay vì trông chờ terminal operation tự dọn dẹp.

## 3. Dùng try-with-resources với Files.lines

`Files.lines(Path)` trả về `Stream<String>` được đọc lazy từ file. Stream này giữ tài nguyên đọc file và **phải được đóng** sau khi xử lý.

Ví dụ:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class ReadLinesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("names.txt");

        try (Stream<String> lines =
                     Files.lines(path, StandardCharsets.UTF_8)) {
            lines.filter(line -> !line.isBlank())
                    .map(String::strip)
                    .forEach(System.out::println);
        }
    }
}
~~~

Khi rời khỏi khối `try`, kể cả khi pipeline ném ngoại lệ, Java gọi `close()` trên stream. Close action của stream từ `Files.lines` đóng reader và tài nguyên file liên quan.

Dùng charset tường minh như `StandardCharsets.UTF_8` giúp việc đọc file nhất quán giữa các môi trường.

### 3.1. Thu thập kết quả rồi đóng file

Nếu cần trả về danh sách đã đọc, hãy thực hiện terminal operation bên trong khối quản lý tài nguyên:

~~~java
static List<String> readAllLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.toList();
    }
}
~~~

`toList()` có từ Java 16 và trả về danh sách không thể sửa. Sau khi tạo danh sách, stream được đóng khi thoát khỏi khối `try`.

Nếu cần danh sách mutable, có thể dùng collector phù hợp:

~~~java
static List<String> readMutableLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.collect(Collectors.toCollection(ArrayList::new));
    }
}
~~~

Việc trả về collection đã materialize giúp API không chuyển trách nhiệm đóng file sang nơi gọi.

### 3.2. Xử lý IOException khi mở và UncheckedIOException khi đọc

`Files.lines` có thể ném `IOException` khi mở file. Việc đọc nội dung diễn ra lazy trong quá trình thực thi pipeline; nếu I/O lỗi khi đang đọc, lỗi có thể được bọc trong `UncheckedIOException`.

~~~java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
} catch (IOException ex) {
    System.err.println("Không thể mở hoặc đóng file: " + ex.getMessage());
} catch (UncheckedIOException ex) {
    System.err.println("Lỗi khi đọc nội dung: " + ex.getMessage());
}
~~~

Trong ứng dụng thực tế, nên xử lý exception ở tầng có đủ ngữ cảnh để quyết định retry, báo lỗi hoặc dừng xử lý. Đừng bắt mọi exception rồi bỏ qua, vì như vậy lỗi đọc dữ liệu có thể bị che khuất.

## 4. Các stream của Files cũng cần được đóng

Không chỉ `Files.lines` mới mở tài nguyên. Một số phương thức khác trong `java.nio.file.Files` cũng trả về stream gắn với tài nguyên.

### 4.1. Files.list: liệt kê một cấp thư mục

~~~java
try (Stream<Path> entries = Files.list(Path.of("data"))) {
    entries.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

`Files.list` trả về stream các entry trực tiếp trong thư mục. Nó không đệ quy xuống thư mục con. Stream giữ directory stream mở cho đến khi được đóng.

### 4.2. Files.walk: duyệt cây thư mục

~~~java
try (Stream<Path> paths = Files.walk(Path.of("data"))) {
    paths.filter(Files::isRegularFile)
            .forEach(System.out::println);
}
~~~

`Files.walk` duyệt cây thư mục theo chiều sâu. Nó có thể mở nhiều directory trong quá trình duyệt, nên cần đóng stream để giải phóng tài nguyên.

Nếu chỉ cần một cấp, dùng `Files.list`. Nếu cần đệ quy, dùng `Files.walk` và giới hạn độ sâu khi phù hợp:

~~~java
try (Stream<Path> paths = Files.walk(Path.of("data"), 2)) {
    paths.forEach(System.out::println);
}
~~~

Tham số `2` là độ sâu tối đa tính từ thư mục gốc theo hợp đồng của `Files.walk`.

### 4.3. Files.find: duyệt và lọc theo thuộc tính

~~~java
import java.nio.file.attribute.BasicFileAttributes;

try (Stream<Path> matches = Files.find(
        Path.of("data"),
        5,
        (path, attributes) ->
                attributes.isRegularFile()
                        && path.getFileName().toString().endsWith(".csv"))) {
    matches.forEach(System.out::println);
}
~~~

`Files.find` cung cấp cả đường dẫn và `BasicFileAttributes` cho predicate. Nó cũng trả về stream cần đóng sau khi sử dụng.

### 4.4. Bảng tổng hợp

| API | Phạm vi | Resource cần đóng |
| --- | --- | --- |
| `Files.lines(path)` | Các dòng trong file | Reader/file stream |
| `Files.list(directory)` | Entry trực tiếp của thư mục | Directory stream |
| `Files.walk(start)` | Cây thư mục | Các directory stream trong quá trình duyệt |
| `Files.find(start, depth, matcher)` | Cây thư mục có predicate thuộc tính | Các directory stream trong quá trình duyệt |

Đừng bỏ qua try-with-resources chỉ vì terminal operation đã hoàn tất hoặc chỉ tìm được một kết quả.

## 5. BufferedReader.lines(): đóng reader sở hữu nguồn

`BufferedReader.lines()` cũng trả về `Stream<String>`, nhưng cần hiểu rõ resource owner: `BufferedReader` là đối tượng sở hữu reader/file.

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines()
            .filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

Khối try quản lý `BufferedReader` và bảo đảm `reader.close()` được gọi sau khi pipeline hoàn thành. `BufferedReader.lines()` đọc lazy từ reader đó; không được dùng reader đồng thời ở nơi khác trong khi terminal operation của stream đang chạy.

Không nên giả định rằng đóng một stream bất kỳ tạo từ `BufferedReader.lines()` sẽ tự động đóng reader. API `BufferedReader.lines()` tạo stream để đọc reader; hợp đồng quản lý resource vẫn thuộc về `BufferedReader`. Vì thế, cách rõ ràng là giữ reader trong try-with-resources như ví dụ.

### 5.1. Khác biệt với Files.lines

| API | Stream đọc từ | Cần đóng gì? |
| --- | --- | --- |
| `Files.lines(path)` | Reader do API tạo bên trong | Đóng stream trả về |
| `reader.lines()` | `BufferedReader` đã được tạo bên ngoài | Đóng `BufferedReader` |

Một mẫu khác là dùng `Files.lines` trực tiếp khi chỉ cần stream. Dùng `BufferedReader` khi cần các thao tác reader khác, hoặc muốn quản lý rõ reader ở cấp ứng dụng.

## 6. Scanner và các nguồn đọc có vòng đời riêng

`Scanner` có phương thức `tokens()` để tạo stream token. `Scanner` thường được tạo từ file, input stream hoặc reader; cần đóng scanner mà ứng dụng sở hữu.

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.Scanner;

try (Scanner scanner = new Scanner(Path.of("numbers.txt"), "UTF-8")) {
    scanner.tokens()
            .filter(token -> !token.isBlank())
            .forEach(System.out::println);
}
~~~

Đóng scanner sẽ đóng nguồn mà scanner quản lý, vì vậy cần thận trọng khi scanner được tạo từ `System.in` hoặc một stream dùng chung. Nếu ứng dụng không sở hữu nguồn đó, đừng tùy tiện đóng nó qua wrapper.

Nguyên tắc tổng quát: **đóng resource ở nơi sở hữu hoặc nơi nhận trách nhiệm sở hữu rõ ràng**. Một stream view không tự động cho biết ai sở hữu file, socket hoặc reader nằm phía sau.

## 7. Stream.close() và onClose(...)

`BaseStream` định nghĩa:

- `close()`: đóng stream và chạy close handlers đã đăng ký.
- `onClose(Runnable closeHandler)`: trả về stream tương đương có đăng ký thêm hành động khi stream được đóng.

Ví dụ với một stream tự tạo:

~~~java
Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("Đã đóng stream"));

try (stream) {
    stream.forEach(System.out::println);
}
~~~

Kết quả:

~~~text
A
B
Đã đóng stream
~~~

`onClose` hữu ích khi xây dựng abstraction cần chạy cleanup khi người gọi đóng stream. Tuy nhiên, đăng ký handler **không làm handler chạy ngay khi terminal operation kết thúc**; vẫn phải gọi `close()` hoặc dùng try-with-resources.

### 7.1. Close handler không thay thế resource ownership

Ví dụ:

~~~java
Stream<String> lines = Files.lines(path)
        .onClose(() -> audit("closed"));
~~~

Khi stream được đóng, handler audit chạy cùng quy trình đóng stream nguồn. Nhưng nếu không gọi close, handler cũng không chạy. Do đó vẫn phải quản lý stream trong try-with-resources.

### 7.2. Đóng nhiều lần

`close()` được thiết kế để đóng pipeline; nên tránh gọi nhiều nơi hoặc chia sẻ quyền đóng không rõ ràng. Hãy xác định một chủ sở hữu có trách nhiệm đóng. Khi nhiều thành phần cùng đăng ký cleanup, `onClose` giúp gắn cleanup vào vòng đời stream; thứ tự và exception của các close handler tuân theo hợp đồng API của `BaseStream`.

## 8. try-with-resources bảo đảm điều gì?

Cấu trúc:

~~~java
try (Stream<String> stream = Files.lines(path)) {
    stream.filter(...).forEach(...);
}
~~~

đảm bảo `close()` được gọi khi rời khỏi khối, cả khi:

- Pipeline chạy hết bình thường.
- Predicate hoặc mapper ném runtime exception.
- Terminal operation ném exception.
- Có lệnh `return` hoặc exception làm thoát khối.

Đây là cách quản lý resource tiêu chuẩn trong Java. Không cần viết `finally` thủ công để gọi close trong các trường hợp thông thường.

### 8.1. Nhiều resource

Có thể khai báo nhiều resource trong cùng try:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8);
     Stream<String> lines = reader.lines()) {

    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

Các resource được đóng theo thứ tự ngược với thứ tự khai báo. Trong ví dụ, stream được đóng trước rồi reader được đóng. Vì `BufferedReader.lines()` không chuyển quyền sở hữu reader sang stream, việc quản lý reader trong cùng khối vẫn rất quan trọng.

### 8.2. Suppressed exceptions

Nếu thân khối try ném một exception và việc đóng resource cũng gặp lỗi, Java giữ exception từ thân khối làm exception chính; lỗi trong quá trình đóng được gắn dưới dạng suppressed exception. Điều này giúp không mất lỗi ban đầu khi cleanup cũng thất bại.

Có thể đọc các suppressed exception bằng `getSuppressed()` nếu cần chẩn đoán. Thông thường, chỉ cần để try-with-resources quản lý quy trình này.

## 9. Short-circuit và pipeline dừng sớm

Các terminal operation như `findFirst`, `findAny`, `anyMatch`, `allMatch` và `noneMatch` có thể dừng pipeline trước khi đọc hết dữ liệu.

~~~java
try (Stream<String> lines = Files.lines(path)) {
    Optional<String> firstError = lines
            .filter(line -> line.contains("ERROR"))
            .findFirst();

    firstError.ifPresent(System.out::println);
}
~~~

Khi tìm được dòng lỗi đầu tiên, stream có thể ngừng đọc sớm. Nhưng file vẫn cần được đóng khi thoát khỏi khối try.

Tương tự, `limit(10)` là intermediate operation; nó giới hạn số phần tử xử lý nhưng không tự đóng stream:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    lines.limit(10).forEach(System.out::println);
}
~~~

Không dùng `limit` hoặc `findFirst` như một cách thay thế cho close. Chúng điều khiển lượng dữ liệu đọc, không sở hữu vòng đời tài nguyên.

## 10. Không trả về stream đã đóng

Một lỗi thiết kế API phổ biến là tạo stream trong try-with-resources rồi trả nó ra ngoài:

~~~java
// Sai về vòng đời:
static Stream<String> badRead(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank());
    }
}
~~~

Ngay khi phương thức thoát, try-with-resources đóng stream. Bên gọi nhận được pipeline đã đóng và không thể thực thi terminal operation như mong đợi.

Có hai hướng thiết kế tốt hơn.

### 10.1. Thực thi và materialize bên trong

~~~java
static List<String> readNames(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank())
                .map(String::strip)
                .toList();
    }
}
~~~

Phương thức sở hữu file, xử lý dữ liệu, đóng stream rồi trả về collection độc lập.

### 10.2. Trả stream và chuyển trách nhiệm cho caller một cách rõ ràng

~~~java
static Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path);
}
~~~

Nếu chọn thiết kế này, hợp đồng API phải nói rõ **caller chịu trách nhiệm đóng stream**. Cách gọi:

~~~java
try (Stream<String> lines = openLines(path)) {
    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

Không nên trả resource-backed stream từ API công khai mà không ghi rõ ownership. Người gọi khó nhận ra rằng một terminal operation không tự đóng file.

## 11. flatMap và stream con

Một trường hợp đặc biệt là `flatMap`: khi mapper tạo stream con, Stream API bảo đảm mỗi stream được ánh xạ sẽ được đóng sau khi các phần tử của nó được đưa vào stream kết quả.

Ví dụ đọc nhiều file:

~~~java
try (Stream<Path> files = Files.list(Path.of("logs"))) {
    long errorCount = files
            .filter(Files::isRegularFile)
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })
            .filter(line -> line.contains("ERROR"))
            .count();

    System.out.println(errorCount);
}
~~~

Trong pipeline này:

- Stream ngoài từ `Files.list` được đóng bởi try-with-resources.
- Mỗi stream con từ `Files.lines` được `flatMap` đóng sau khi nội dung của nó được tiêu thụ.
- Nếu việc mở file con thất bại, ví dụ chuyển `IOException` thành `UncheckedIOException` để truyền qua mapper.

Đây là quy tắc riêng của `flatMap`, không nên suy rộng thành “mọi stream con được tạo ở bất cứ đâu đều tự đóng”. Nếu tạo stream con trong `map` rồi giữ lại như dữ liệu, hoặc lưu vào collection, caller phải quản lý vòng đời từng stream theo hợp đồng nguồn.

Với nhiều file, cũng cần quyết định chính sách khi một file không đọc được: dừng toàn bộ pipeline, ghi nhận lỗi và bỏ qua file đó, hay retry. Không nên âm thầm bỏ qua lỗi I/O.

## 12. Không dùng parallel stream để né quản lý tài nguyên

Stream gắn tài nguyên vẫn phải được đóng khi xử lý song song:

~~~java
try (Stream<String> lines = Files.lines(path).parallel()) {
    long count = lines
            .filter(line -> line.contains("WARN"))
            .count();

    System.out.println(count);
}
~~~

`parallel()` thay đổi cách pipeline thực thi; nó không làm mất nghĩa vụ đóng file. Ngoài ra, xử lý song song có thể làm thứ tự hành động không xác định và không phải lúc nào cũng nhanh hơn, đặc biệt với nguồn I/O hoặc file nhỏ.

Không nên chia sẻ một resource-backed stream để nhiều pipeline cùng tiêu thụ. Một stream chỉ dùng cho một pipeline và một lần terminal operation.

## 13. Khi nào không cần Stream?

Nếu chỉ cần đọc toàn bộ file nhỏ thành danh sách, `Files.readAllLines` có thể đơn giản hơn:

~~~java
List<String> lines =
        Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

Phương thức này quản lý việc mở/đóng file bên trong và trả về danh sách đã đọc. Đổi lại, toàn bộ nội dung được nạp vào bộ nhớ.

Nếu cần xử lý từng dòng với kiểm soát rõ ràng, có thể dùng `BufferedReader` và vòng lặp:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        if (!line.isBlank()) {
            System.out.println(line);
        }
    }
}
~~~

Chọn API theo nhu cầu:

| Nhu cầu | API gợi ý |
| --- | --- |
| File nhỏ, cần tất cả dòng trong bộ nhớ | `Files.readAllLines` |
| Pipeline filter/map/reduce lazy trên file | `Files.lines` trong try-with-resources |
| Đọc tuần tự và điều khiển từng bước | `BufferedReader` trong try-with-resources |
| Liệt kê một cấp thư mục | `Files.list` trong try-with-resources |
| Duyệt đệ quy | `Files.walk` hoặc `Files.find` trong try-with-resources |

## 14. Ví dụ tổng hợp: đếm lỗi trong nhiều file log

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class LogScanner {

    private LogScanner() {
    }

    public static long countErrors(Path directory) throws IOException {
        try (Stream<Path> files = Files.list(directory)) {
            return files
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName()
                            .toString().endsWith(".log"))
                    .flatMap(path -> readLines(path))
                    .filter(line -> line.contains("ERROR"))
                    .count();
        }
    }

    private static Stream<String> readLines(Path path) {
        try {
            return Files.lines(path, StandardCharsets.UTF_8);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Path.of("logs");
        System.out.println("Errors: " + countErrors(directory));
    }
}
~~~

Trong ví dụ:

- `Files.list` tạo stream ngoài cần đóng.
- `Files.lines` tạo stream con cho mỗi file.
- `flatMap` tiêu thụ và đóng stream con theo hợp đồng của nó.
- Stream ngoài được đóng trong try-with-resources.
- Việc mở file có thể ném `IOException`, được chuyển thành `UncheckedIOException` để truyền qua mapper.

Nếu muốn xử lý từng file lỗi độc lập và tiếp tục file khác, hãy thiết kế rõ nhánh xử lý lỗi thay vì chỉ đổi exception. Ví dụ này chọn chính sách lỗi làm hỏng toàn bộ phép đếm.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| File vẫn bị giữ sau khi gọi `count()` | Terminal operation không tự đóng stream | Đặt stream trong try-with-resources |
| `findFirst()` xong nhưng file vẫn mở | Short-circuit chỉ dừng đọc | Đóng stream sau terminal operation |
| Xóa/đổi tên file thất bại trên một số hệ điều hành | File handle còn mở | Đảm bảo resource-backed stream đã đóng |
| Trả về stream từ phương thức nhưng caller đọc lỗi | Stream đã bị đóng khi phương thức thoát try | Trả collection hoặc chuyển quyền đóng rõ ràng |
| Nghĩ mọi stream phải đóng | Stream từ collection/array thường không có resource | Chỉ quản lý close khi nguồn hoặc close handler yêu cầu |
| `BufferedReader.lines()` làm reader bị rò rỉ | Không đóng reader sở hữu nguồn | Đặt `BufferedReader` trong try-with-resources |
| `Files.walk` không giải phóng thư mục | Quên đóng stream traversal | Dùng try-with-resources |
| Lỗi I/O xuất hiện trong terminal operation dưới dạng unchecked | Đọc lazy nên lỗi xảy ra khi pipeline thực thi | Xử lý `UncheckedIOException` ở tầng phù hợp |
| Dùng parallel nhưng vẫn giữ file handle | `parallel()` không quản lý resource | Đóng stream như bình thường |
| Chỉ gọi `onClose` nhưng handler không chạy | Handler chỉ chạy khi close được gọi | Dùng try-with-resources hoặc gọi close có chủ đích |
| Đóng stream con sai chỗ | Không hiểu ownership của nguồn | Đọc hợp đồng API; chú ý quy tắc riêng của `flatMap` |

## 16. Bài tập thực hành

### Bài 1 — Đọc file an toàn

Viết phương thức nhận `Path`, dùng `Files.lines` đếm số dòng không trống và trả về số lượng. Đảm bảo file stream được đóng ngay cả khi predicate ném lỗi.

### Bài 2 — Phân biệt nguồn stream

Tạo một stream từ `List.of` và một stream từ `Files.lines`. Giải thích stream nào giữ file resource và vì sao terminal operation không thay thế `close()`.

### Bài 3 — Liệt kê thư mục

Dùng `Files.list` để in file trực tiếp trong một thư mục. Sau đó dùng `Files.walk` để liệt kê đệ quy. Đảm bảo cả hai stream được đóng.

### Bài 4 — BufferedReader.lines

Tạo `BufferedReader` bằng `Files.newBufferedReader`, gọi `lines()` để lọc dữ liệu. Quản lý reader bằng try-with-resources và giải thích vì sao reader là resource owner.

### Bài 5 — Short-circuit

Dùng `Files.lines` tìm dòng đầu tiên chứa `ERROR` bằng `findFirst`. Sau khi tìm thấy, đảm bảo tài nguyên được đóng. Thử trường hợp không có dòng phù hợp.

### Bài 6 — onClose

Tạo một stream có `onClose` ghi log. Chạy terminal operation, quan sát handler chưa chạy nếu không gọi close; sau đó thêm try-with-resources và quan sát cleanup.

### Bài 7 — API ownership

Viết hai phương thức: một phương thức trả về `List<String>` đã đọc và đóng file bên trong; phương thức còn lại trả về `Stream<String>` và ghi rõ caller phải đóng. So sánh trách nhiệm của hai bên.

## 17. Nguyên tắc cần nhớ

- Xác định nguồn stream trước khi quyết định có cần đóng hay không.
- `Files.lines`, `Files.list`, `Files.walk` và `Files.find` là các stream gắn với tài nguyên; đóng chúng bằng try-with-resources.
- Terminal operation tiêu thụ pipeline nhưng không tự đảm bảo giải phóng resource.
- `BufferedReader.lines()` đọc từ reader; đóng `BufferedReader` sở hữu nguồn.
- `onClose` đăng ký cleanup, nhưng cleanup chỉ chạy khi stream được đóng.
- Nếu phương thức trả resource-backed stream, phải chuyển trách nhiệm đóng cho caller một cách rõ ràng.
- `flatMap` có quy tắc đóng stream con sau khi tiêu thụ; không suy rộng quy tắc đó cho mọi stream lồng nhau.
- Xử lý cả lỗi khi mở nguồn và lỗi xảy ra trong lúc pipeline đọc lazy.

Quản lý đúng vòng đời stream giúp ứng dụng Java 17 giải phóng file handle và các tài nguyên liên quan đúng lúc, tránh rò rỉ khi pipeline kết thúc sớm hoặc gặp lỗi, đồng thời làm rõ trách nhiệm giữa API tạo stream và nơi tiêu thụ stream.
