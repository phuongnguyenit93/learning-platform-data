# Đóng nguồn bằng try-with-resources

Trong chương **Nguồn vào ra và quản lý tài nguyên** của **Java Stream API**, các pipeline khai báo có thể lấy dữ liệu từ `List`, mảng, bộ sinh số hoặc trực tiếp từ tệp và thư mục. Cùng một cách viết `filter`, `map`, `reduce` hay `collect` có thể được áp dụng cho nhiều nguồn, nhưng **trách nhiệm quản lý tài nguyên phụ thuộc vào cách Stream được tạo ra**.

Với các nguồn I/O như `Files.lines`, `Files.list` hoặc `Files.walk`, Stream có thể giữ tệp hay thư mục đang mở trong lúc duyệt. Chạy terminal operation không đồng nghĩa với việc nguồn được đóng. Quy tắc an toàn là **đặt Stream sở hữu tài nguyên vào `try-with-resources` và thực hiện toàn bộ pipeline bên trong phạm vi đó**. Kể cả khi pipeline dừng sớm, gặp lỗi hay trả về kết quả, Java vẫn gọi `close()` khi ra khỏi khối `try`.

Bài này giải thích hợp đồng đóng Stream, nguồn nào cần đóng, cách truyền quyền sở hữu tài nguyên giữa các phương thức, xử lý ngoại lệ và các lỗi thường gặp. Những nguyên tắc này vẫn quan trọng khi thêm `parallel()`, dùng Spliterator hoặc mở rộng pipeline bằng Stream Gatherers: một pipeline hoạt động đúng về dữ liệu vẫn có thể gây rò rỉ tài nguyên nếu vòng đời I/O không được kiểm soát.

## 1. Vì sao một Stream cần được đóng?

Stream là **mô tả quá trình xử lý phần tử**, không nhất thiết là bản sao dữ liệu đã nằm trong bộ nhớ.

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> names = List.of("Lan", "Minh", "An");

Stream<String> fromList = names.stream();
Stream<String> fromValues = Stream.of("A", "B", "C");
~~~

Hai Stream trên dùng dữ liệu đã có sẵn. Thông thường, chúng **không sở hữu** tệp, socket hay tài nguyên hệ điều hành cần giải phóng khi duyệt xong. Trong các trường hợp này, một khối `try-with-resources` thường không cần thiết.

Ngược lại:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path file = Path.of("logs/app.log");

Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8);
~~~

`Files.lines` tạo một Stream đọc các dòng tệp khi pipeline yêu cầu. Nguồn này có tài nguyên I/O phải được đóng. Nếu chương trình để Stream sống quá lâu hoặc quên đóng, tệp có thể còn bị giữ mở, khiến ứng dụng cạn file descriptor/handle hoặc khó thực hiện một số thao tác với tệp trên hệ điều hành.

**Không nên mặc định rằng mọi Stream đều phải đóng một cách bắt buộc như nhau.** Tuy nhiên, với nguồn được mô tả là gắn tài nguyên I/O, phải tuân thủ hướng dẫn đóng của phương thức tạo nguồn.

## 2. Hợp đồng AutoCloseable và try-with-resources

`Stream<T>` kế thừa `BaseStream`, còn `BaseStream` kế thừa `AutoCloseable`. Vì vậy, một biến kiểu `Stream<String>` có thể được khai báo trong `try-with-resources`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path file = Path.of("logs/app.log");

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    long warnings = lines
            .filter(line -> line.startsWith("WARN"))
            .count();

    System.out.println("Số dòng cảnh báo: " + warnings);
} // Java tự gọi lines.close() tại đây.
~~~

Trình tự:

1. `Files.lines(...)` mở nguồn I/O và trả về Stream.
2. Stream được khai báo làm **resource** trong dấu ngoặc của `try`.
3. Các thao tác trung gian `filter` được ghép thành pipeline; `count` là terminal operation.
4. Khi khối `try` kết thúc, Java gọi `lines.close()`, dù quá trình duyệt thành công hay xảy ra ngoại lệ.
5. Tài nguyên do Stream sở hữu được giải phóng theo hợp đồng của nguồn.

Cú pháp khai báo resource hoạt động từ Java 7; Stream API và `Files.lines` có từ Java 8. `Path.of` xuất hiện ở Java 11; trên Java 8 có thể dùng `Paths.get("logs/app.log")`.

> **Quy tắc cốt lõi:** Đặt **việc mở nguồn, sử dụng Stream và đóng nguồn** trong cùng một phạm vi sở hữu tài nguyên rõ ràng.

## 3. Terminal operation không thay thế close()

Sự khác biệt quan trọng nhất là giữa **kết thúc pipeline** và **đóng tài nguyên**.

| Hành động | Ý nghĩa | Có bảo đảm đóng nguồn I/O không? |
| --- | --- | --- |
| `filter`, `map`, `limit` | Xây dựng thao tác trung gian, thường lazy | Không |
| `count`, `collect`, `toList`, `reduce` | Thực thi và kết thúc pipeline | Không |
| `findFirst`, `anyMatch` | Terminal operation có khả năng dừng sớm | Không |
| `Stream.close()` | Đóng Stream và chạy các close handler đã đăng ký | Có thực hiện hành động đóng mà nguồn định nghĩa |
| Ra khỏi `try-with-resources` | Java tự gọi `close()` trên resource | Có, kể cả khi đường đi có ngoại lệ hoặc `return` |

Đoạn mã sau **có nguy cơ rò rỉ tài nguyên**, dù `count()` đã trả về:

~~~java
// Không dùng cách này với nguồn Files.lines.
Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8);

long total = lines.count();

// Không có lines.close(): vòng đời tài nguyên chưa được xử lý đúng.
~~~

Thay bằng:

~~~java
long total;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    total = lines.count();
}
~~~

Kể từ khi terminal operation kết thúc, **đối tượng Stream không được sử dụng lại**, ngay cả khi chưa gọi `close()`. Ngược lại, sau khi gọi `close()`, Stream cũng không còn được phép thực thi pipeline mới dù chưa có terminal operation nào chạy.

Hai trạng thái khác nhau nhưng đều không cho phép tiếp tục sử dụng cùng đối tượng Stream.

## 4. Dừng sớm vẫn phải đóng nguồn

Một số terminal operation như `findFirst`, `findAny` và `anyMatch` có thể dừng sau khi nhận đủ bằng chứng. `limit` cũng có thể khiến upstream chỉ cần cung cấp một phần dữ liệu.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

Path file = Path.of("logs/app.log");

Optional<String> firstError;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    firstError = lines
            .filter(line -> line.startsWith("ERROR"))
            .findFirst();
}

firstError.ifPresent(System.out::println);
~~~

Nếu dòng lỗi đầu tiên xuất hiện gần đầu tệp, Stream có thể không cần đọc hết. Nhưng dù chỉ lấy một dòng, **nguồn vẫn phải được đóng** khi ra khỏi khối `try`.

Tương tự:

~~~java
boolean containsCritical;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    containsCritical = lines.anyMatch(
            line -> line.contains("CRITICAL")
    );
}
~~~

Nếu đã tìm thấy `CRITICAL` thì `anyMatch` có thể trả về sớm. Nếu không tìm thấy, nó phải tiếp tục duyệt cho tới khi hết nguồn. Trong cả hai trường hợp, `try-with-resources` xử lý việc đóng.

**Không nên dựa vào việc “đã đọc hết tệp” như tín hiệu tự đóng:** ngay cả phép duyệt toàn bộ cũng không thay thế `close()` theo hợp đồng của Stream I/O.

## 5. Những factory Stream I/O thường cần try-with-resources

Các nguồn từ `java.nio.file.Files` đặc biệt quan trọng:

| Factory | Dữ liệu cung cấp | Rủi ro tài nguyên | Cách dùng |
| --- | --- | --- | --- |
| `Files.lines(path)`, `Files.lines(path, charset)` | Các dòng văn bản từ tệp | Giữ nguồn đọc tệp mở trong lúc duyệt | `try (Stream<String> s = Files.lines(...))` |
| `Files.list(dir)` | Các mục trực tiếp trong thư mục | Có tài nguyên gắn với việc duyệt thư mục | `try (Stream<Path> s = Files.list(dir))` |
| `Files.walk(root)`, `Files.walk(root, depth)` | Các đường dẫn theo duyệt cây thư mục | Có thể giữ tài nguyên phục vụ việc duyệt cây | `try (Stream<Path> s = Files.walk(root))` |
| `Files.find(root, depth, matcher)` | Đường dẫn thỏa điều kiện tìm kiếm | Có tài nguyên phục vụ truy cập hệ thống tệp | `try (Stream<Path> s = Files.find(...))` |

`Files.list` chỉ cung cấp các mục **trực tiếp** bên trong thư mục. `Files.walk` có thể đi sâu vào các thư mục con theo phạm vi đã chọn. Đây là khác biệt nghiệp vụ về nguồn, còn **yêu cầu đóng Stream** là giống nhau.

Ví dụ liệt kê tệp trong một thư mục:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<Path> listRegularFiles(Path directory) throws IOException {
    try (Stream<Path> entries = Files.list(directory)) {
        return entries
                .filter(Files::isRegularFile)
                .collect(Collectors.toList());
    }
}
~~~

Danh sách `Path` được materialize **bên trong** khối `try`; sau khi khối kết thúc, danh sách vẫn có thể sử dụng. Các `Path` chỉ là đối tượng biểu diễn đường dẫn, không cần giữ Stream thư mục mở để truy cập nội dung các phần tử đã thu.

Nếu cần duyệt sâu:

~~~java
static long countJavaFiles(Path projectRoot) throws IOException {
    try (Stream<Path> paths = Files.walk(projectRoot)) {
        return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .count();
    }
}
~~~

Duyệt cây thư mục có thể gặp lỗi quyền truy cập hoặc I/O; cần xử lý lỗi phù hợp với nghiệp vụ và tránh giả định hệ thống tệp không thay đổi trong lúc đang duyệt.

## 6. BufferedReader.lines: ai sở hữu tài nguyên?

`BufferedReader.lines()` cũng tạo một `Stream<String>`, nhưng **tài nguyên trực tiếp cần quản lý là `BufferedReader`**. Không nên mặc định việc gọi `close()` trên Stream do `reader.lines()` trả về sẽ đóng `reader`.

Cách rõ ràng:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static long countNonEmptyLines(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

        return reader.lines()
                .filter(line -> !line.isEmpty())
                .count();
    }
}
~~~

`try-with-resources` đóng `reader` khi ra khỏi khối. Stream từ `reader.lines()` được duyệt khi reader còn mở; vì vậy không xảy ra tình huống sử dụng reader sau khi đã đóng trong đường đi hợp lệ.

Nếu muốn quản lý cả Stream và reader một cách tường minh, có thể khai báo nhiều resource:

~~~java
import java.util.stream.Stream;

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8);
     Stream<String> lines = reader.lines()) {

    long total = lines.count();
    System.out.println(total);
}
~~~

Resource được đóng theo **thứ tự ngược với lúc khai báo**: `lines.close()` trước, sau đó `reader.close()`. Java vẫn cố gắng đóng những resource còn lại nếu một thao tác đóng gặp lỗi.

Điều quan trọng khi dùng wrapper như `BufferedReader`, `Scanner` hoặc một Stream tùy chỉnh là: **đối tượng nào thực sự sở hữu tài nguyên bên dưới phải có cơ chế đóng rõ ràng**. Không suy ra vòng đời của wrapper chỉ từ việc nó trả về một Stream.

## 7. Không trả về Stream đã bị đóng

Đây là lỗi dễ xảy ra khi tách mã thành nhiều phương thức.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// Sai: trả về pipeline phụ thuộc vào Stream đã đóng.
static Stream<String> badRead(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank());
    }
}
~~~

`filter` là thao tác trung gian *lazy*. Trong thời điểm `return`, chưa có terminal operation nào cần đọc dữ liệu. Nhưng trước khi phương thức trả về đối tượng Stream cho caller, khối `try` đã kết thúc và `lines.close()` đã được gọi. Caller nhận một pipeline không còn dùng được.

Ví dụ này sử dụng `String.isBlank()` (Java 11+); trên Java 8 có thể thay bằng `!line.trim().isEmpty()`.

Có hai cách thiết kế đúng, tùy người sở hữu nguồn.

### Cách A: Đọc và thu kết quả trước khi trả về

Khi API cần trả một danh sách hữu hạn, hãy thực thi pipeline **bên trong** phạm vi tài nguyên:

~~~java
import java.util.List;
import java.util.stream.Collectors;

static List<String> readNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> !line.isBlank())
                .collect(Collectors.toList());
    }
}
~~~

Khối `try` thực thi terminal operation trước, tạo ra `List<String>` độc lập với vòng đời nguồn. Sau đó Stream được đóng và phương thức trả danh sách.

Đổi lại, cách này giữ toàn bộ kết quả trong bộ nhớ; không phù hợp để thu vô hạn dữ liệu hoặc tệp rất lớn nếu ứng dụng không cần lưu hết.

### Cách B: Trả Stream đang mở và giao rõ trách nhiệm đóng cho caller

Nếu API cần xử lý từng dòng một cách lazy, phương thức có thể trả về Stream **chưa đóng**:

~~~java
/**
 * Trả Stream đọc tệp theo nhu cầu.
 * Caller phải đóng Stream bằng try-with-resources.
 */
static Stream<String> openNonBlankLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8)
            .filter(line -> !line.isBlank());
}
~~~

Caller bắt buộc sở hữu việc đóng:

~~~java
try (Stream<String> lines = openNonBlankLines(path)) {
    lines.limit(100).forEach(System.out::println);
}
~~~

Cách này không cần giữ toàn bộ kết quả trong bộ nhớ, nhưng hợp đồng API **phải nêu rõ ai đóng Stream**. Không để caller tưởng rằng đây là một Stream từ collection có thể bỏ qua `close()`.

> **Nguyên tắc chuyển quyền sở hữu:** Một phương thức hoặc **sở hữu Stream và đóng trước khi trả dữ liệu đã tính**, hoặc **trả Stream còn mở và buộc caller chịu trách nhiệm đóng**. Không trả lazy pipeline từ một khối đã đóng nguồn.

## 8. Xử lý ngoại lệ khi mở, đọc và đóng Stream

Đường đi I/O có thể gặp lỗi ở nhiều giai đoạn:

1. **Mở nguồn:** `Files.lines(...)`, `Files.list(...)` hoặc `Files.walk(...)` có thể ném `IOException` ngay lúc khởi tạo.
2. **Duyệt nguồn:** thao tác I/O bị trì hoãn có thể thất bại khi terminal operation yêu cầu phần tử. Một số factory chuyển lỗi checked thành `UncheckedIOException` trong quá trình duyệt.
3. **Đóng nguồn:** quá trình giải phóng tài nguyên hoặc close handler có thể phát sinh lỗi.

Ví dụ phương thức công khai:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countErrors(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
~~~

`throws IOException` bao gồm lỗi checked khi mở nguồn. Nếu đọc dữ liệu trong terminal operation phát sinh `UncheckedIOException`, caller có thể cần xử lý runtime exception đó riêng. Không nên nuốt mọi lỗi rồi trả về tổng bằng 0, vì điều đó làm một file lỗi bị hiểu nhầm thành file hợp lệ không có dòng lỗi.

Một ví dụ xử lý ở tầng gọi:

~~~java
try {
    long errors = countErrors(path);
    System.out.println("Errors: " + errors);
} catch (IOException | UncheckedIOException ex) {
    System.err.println("Không đọc được tệp: " + path);
    // Ghi log/lan truyền lỗi theo chính sách ứng dụng.
}
~~~

Không nên bắt mọi `RuntimeException` và gán chúng cho lỗi I/O: `NullPointerException` hoặc lỗi trong mapper/predicate là những lỗi khác cần điều tra riêng.

### Ngoại lệ bị suppressed khi đóng

Nếu phần thân `try` đã ném một ngoại lệ và `close()` cũng ném ngoại lệ, Java giữ ngoại lệ từ thân khối làm **nguyên nhân chính**, còn ngoại lệ khi đóng được **đính kèm** bằng `getSuppressed()`. Điều này giúp không làm mất dấu lỗi đầu tiên.

~~~java
try (Stream<String> stream = Stream.of("A")
        .onClose(() -> {
            throw new IllegalStateException("close failed");
        })) {

    throw new IllegalArgumentException("processing failed");
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage()); // processing failed
    System.out.println(ex.getSuppressed().length); // 1
}
~~~

Đây là ví dụ về cơ chế ngoại lệ, không phải gợi ý cố ý ném lỗi trong close handler. Việc sử dụng `try-with-resources` giúp đóng tài nguyên và giữ thông tin lỗi chính xác hơn so với `try/finally` viết thủ công nhưng bỏ qua ngoại lệ đóng.

## 9. onClose: gắn hành động dọn dẹp với vòng đời Stream

`BaseStream.onClose(Runnable closeHandler)` đăng ký một tác vụ chạy khi gọi `close()` trên Stream. Ví dụ:

~~~java
import java.util.stream.Stream;

try (Stream<String> words = Stream.of("Java", "Stream")
        .onClose(() -> System.out.println("Stream đã đóng"))) {

    System.out.println(words.count()); // 2
} // In thêm "Stream đã đóng"
~~~

Có hai ý quan trọng:

- `count()` là terminal operation, **không tự gọi close handler**.
- Close handler chạy khi `try-with-resources` gọi `close()` lúc ra khỏi khối.

`onClose` hữu ích khi xây một Stream tùy chỉnh có tài nguyên riêng cần dọn dẹp, hoặc cần ghi nhận hành động đóng để chẩn đoán. Các close handler được chạy theo thứ tự đăng ký. Nếu một handler ném ngoại lệ, các handler còn lại vẫn được gọi; ngoại lệ sau có thể trở thành suppressed exception.

**Không nên lạm dụng `onClose` để sửa trạng thái nghiệp vụ** như “đơn hàng đã xử lý thành công”. Một Stream có thể đóng vì exception hoặc vì pipeline dừng sớm, nên “đã đóng” không đồng nghĩa với “đã xử lý hết và thành công”.

### Tài nguyên có exception checked trong close()

`onClose` nhận `Runnable` nên handler không được khai báo ném trực tiếp `IOException`. Nếu tự bọc một tài nguyên I/O vào Stream, cần thiết kế rõ cách chuyển và báo cáo lỗi, ví dụ dùng `UncheckedIOException` khi thích hợp. Trong trường hợp đơn giản, nên ưu tiên API nguồn đã biết cách đóng như `Files.lines` và đặt đúng tài nguyên gốc trong `try-with-resources`.

## 10. flatMap và nhiều nguồn con: phân biệt stream ngoài, stream trong

Khi dùng `flatMap`, mỗi phần tử của Stream ngoài có thể tạo ra một Stream con:

~~~java
outer.flatMap(item -> openChildStream(item))
~~~

Theo hợp đồng `flatMap`, Stream con do mapper trả về sẽ được **đóng sau khi nội dung của nó được đưa vào pipeline**. Điều này có ích nếu mỗi phần tử nguồn dẫn đến một tệp cần đọc.

Tuy nhiên, không được suy rằng việc quản lý các Stream con **thay thế** nghĩa vụ đóng Stream ngoài hoặc nguồn I/O riêng mà chương trình sở hữu.

Ví dụ ghép nội dung hai tệp văn bản:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readAllFrom(List<Path> files) {
    return files.stream()
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            })
            .collect(Collectors.toList());
}
~~~

Ở ví dụ này, Stream ngoài là `files.stream()` từ collection; các Stream con đến từ `Files.lines`. `flatMap` quản lý việc đóng Stream con theo hợp đồng của nó khi xử lý. Nếu việc mở tệp thất bại, lambda chuyển `IOException` thành `UncheckedIOException` để đưa lỗi ra khỏi pipeline.

Với bài toán I/O phức tạp, nhiều tệp lớn hoặc các nguồn có khả năng bị chặn, có thể chọn một cấu trúc vòng lặp với `try-with-resources` rõ ràng cho từng tệp để dễ kiểm soát lỗi, khả năng hủy và giới hạn tài nguyên. Ưu tiên **vòng đời tài nguyên rõ** hơn việc cố dùng một pipeline lồng nhau cho mọi trường hợp.

## 11. Đóng nguồn và kết quả đã materialize là hai chuyện khác nhau

Khi gọi `collect` hoặc `toList` trong phạm vi `try`, kết quả hữu hạn nằm trong bộ nhớ. Việc đóng Stream sau đó **không xóa** `List` đã được tạo.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> firstThreeLines(Path file) throws IOException {
    try (Stream<String> lines =
                 Files.lines(file, StandardCharsets.UTF_8)) {

        return lines.limit(3).collect(Collectors.toList());
    }
}
~~~

Hàm trên trả được danh sách ba dòng đầu tiên sau khi đóng nguồn, vì `collect` đã hoàn tất bên trong khối. Mặt khác, nếu trả về iterator, spliterator hoặc Stream được tạo trực tiếp từ nguồn I/O và chỉ duyệt sau khi nguồn đóng, caller sẽ gặp trạng thái không hợp lệ.

Từ Java 16 có thể dùng `lines.limit(3).toList()`, nhưng cần chú ý kết quả `Stream.toList()` là danh sách không sửa đổi được; `Collectors.toList()` không bảo đảm kiểu triển khai hay khả năng sửa đổi theo đặc tả.

Một điểm nữa: Stream có thể chứa **tham chiếu tới đối tượng mutable**. Đóng nguồn không biến những đối tượng đó thành bất biến hay tự sao chép sâu chúng.

## 12. Sử dụng Stream một lần và không tái sử dụng sau close()

Vòng đời logic:

~~~text
MỞ NGUỒN
   |
TẠO STREAM
   |
filter/map/flatMap/...  (thường lazy)
   |
terminal operation     (count, collect, findFirst, ...)
   |
ĐÓNG STREAM           (try-with-resources)
   |
KHÔNG SỬ DỤNG LẠI
~~~

Không thể gọi terminal operation thứ hai trên cùng một Stream đã kết thúc:

~~~java
try (Stream<String> lines =
             Files.lines(file, StandardCharsets.UTF_8)) {

    long count = lines.count();
    // lines.findFirst(); // Sai: Stream đã được dùng.
}
~~~

Nếu cần hai phép tính độc lập, có thể:

- Tính **nhiều kết quả trong một lượt duyệt** bằng collector phù hợp.
- Thu một tập dữ liệu hữu hạn vào List, sau đó tạo nhiều Stream mới từ List nếu đủ bộ nhớ.
- **Mở một Stream I/O mới** trong một khối `try-with-resources` khác nếu nguồn còn sẵn và có thể đọc lại.

Ví dụ mở tệp hai lần:

~~~java
long total;
long warnings;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    total = lines.count();
}

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    warnings = lines.filter(s -> s.startsWith("WARN")).count();
}
~~~

Đây là hai Stream và hai lần mở tệp khác nhau. Đổi lại, dữ liệu có thể thay đổi giữa hai lần đọc và I/O được thực hiện lại; chọn phương án dựa trên yêu cầu nhất quán và chi phí.

## 13. Java 9+: sử dụng biến resource có sẵn

Từ Java 9, `try-with-resources` cho phép dùng một biến đã khai báo bên ngoài nếu biến đó `final` hoặc *effectively final*:

~~~java
import java.util.stream.Stream;

Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8);

try (lines) {
    System.out.println(lines.findFirst().orElse("Tệp rỗng"));
}
~~~

Sau khối này, Stream đã đóng. Trong mã mới, việc khai báo resource trực tiếp trong dấu ngoặc của `try` thường giúp **nhìn thấy quyền sở hữu rõ hơn**:

~~~java
try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    System.out.println(lines.findFirst().orElse("Tệp rỗng"));
}
~~~

Cần đặc biệt chú ý khi mở resource **trước** khối `try`: nếu còn thao tác khác có thể ném ngoại lệ trong khoảng từ lúc mở đến lúc vào khối `try`, chương trình có thể bỏ qua việc đóng. Tốt nhất giữ khoảng thời gian đó ngắn nhất hoặc khai báo trực tiếp bên trong resource specification.

## 14. Xử lý song song có làm thay đổi trách nhiệm đóng không?

Không. Ví dụ:

~~~java
long count;

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    count = lines
            .parallel()
            .filter(line -> !line.isEmpty())
            .count();
}
~~~

`parallel()` chỉ yêu cầu chế độ thực thi song song cho pipeline; nó **không** làm Stream tự động đóng khi terminal operation hoàn tất. Tài nguyên vẫn được đóng khi ra khỏi `try-with-resources`.

Đối với dữ liệu tệp, song song có thể tăng chi phí điều phối, chia nguồn và xử lý I/O. Nếu mapper/predicate có trạng thái chia sẻ, kết quả còn có nguy cơ race condition. Không nên bật `parallel()` chỉ với kỳ vọng nguồn I/O sẽ đọc nhanh hơn. Hãy xét khả năng chia của Spliterator, chi phí xử lý mỗi phần tử và đo hiệu năng với nguồn thực.

Tương tự, một gatherer hoặc collector tùy chỉnh không thay thế quyền sở hữu tài nguyên: ngay cả khi một pipeline xử lý ít phần tử hơn hoặc dừng sớm, **nguồn đang mở vẫn cần được đóng**.

## 15. Bảng lỗi thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cạn file handle khi đọc nhiều tệp | Tạo nhiều `Files.lines` nhưng quên đóng | Bao toàn bộ pipeline trong `try-with-resources`. |
| `findFirst()` đã trả về nhưng tài nguyên vẫn mở | Terminal dừng sớm không tự gọi `close()` | Đóng Stream ngay sau khi hoàn tất, tốt nhất bằng `try-with-resources`. |
| Trả Stream từ phương thức nhưng caller không duyệt được | Stream đã đóng trước khi caller dùng | Thu kết quả trong khối hoặc chuyển quyền sở hữu Stream còn mở cho caller. |
| `BufferedReader.lines()` dùng được nhưng reader không được đóng | Chỉ quản lý Stream, bỏ quên reader gốc | Đặt `BufferedReader` vào `try-with-resources`. |
| Khối `try` đóng Stream trước khi collector chạy | Trả lazy pipeline ra ngoài phạm vi resource | Gọi terminal operation khi resource còn mở. |
| Lỗi khi duyệt tệp không bị bắt bởi `catch(IOException)` | Lỗi I/O phát sinh lazy dưới dạng `UncheckedIOException` | Xử lý đúng dạng ngoại lệ mà nguồn công bố. |
| Ngoại lệ khi đóng che mất nguyên nhân xử lý | Đóng thủ công và ghi đè lỗi trước đó | Dùng `try-with-resources` và xem `getSuppressed()` khi cần. |
| Kết quả sai sau khi dùng lại Stream | Stream chỉ dùng được một pipeline | Tạo Stream mới từ nguồn đọc lại được hoặc thiết kế một lượt duyệt. |
| Nguồn vô hạn hoặc quá lớn không hoàn tất | `collect` cần xử lý mọi phần tử đầu ra | Thêm giới hạn hữu hạn, xử lý theo lô hoặc đổi yêu cầu tổng hợp. |
| Bật `parallel()` nhưng CPU/I/O tăng mạnh | Chi phí điều phối, chia dữ liệu và trạng thái | Chọn chế độ theo kết quả đo và tính độc lập của các lambda. |

## 16. Bài tập tự kiểm tra

### Bài 1 — Nhận diện tài nguyên cần đóng

~~~java
List<String> words = List.of("a", "b");

long x = words.stream().count();
long y = Files.lines(file).count();
~~~

**Câu hỏi:** Lời gọi nào cần thiết kế lại để bảo đảm đóng tài nguyên?

**Đáp án:** `Files.lines(file)`. Nó tạo Stream gắn với nguồn I/O. Sửa:

~~~java
long y;

try (Stream<String> lines = Files.lines(file)) {
    y = lines.count();
}
~~~

`words.stream()` từ danh sách bộ nhớ thường không giữ tài nguyên I/O cần đóng.

### Bài 2 — Short-circuit có giúp giải phóng tệp không?

~~~java
Stream<String> lines = Files.lines(file);

boolean found = lines.anyMatch(s -> s.startsWith("ERROR"));
~~~

**Đáp án:** Không. Dù `anyMatch` dừng sớm khi tìm thấy dòng phù hợp, nó không tự đóng Stream. Dùng `try (Stream<String> lines = Files.lines(file)) { ... }` để bảo đảm đóng.

### Bài 3 — Vì sao phương thức này sai?

~~~java
static Stream<String> read(Path file) throws IOException {
    try (Stream<String> stream = Files.lines(file)) {
        return stream.filter(s -> !s.isEmpty());
    }
}
~~~

**Đáp án:** `filter` lazy; phương thức đóng Stream trước khi caller kích hoạt terminal operation. Nên thu kết quả vào `List` trong khối hoặc trả Stream còn mở và yêu cầu caller dùng `try-with-resources`.

### Bài 4 — File đã thu vào List còn sử dụng được không?

~~~java
List<String> cached;

try (Stream<String> lines = Files.lines(file)) {
    cached = lines.limit(10).collect(Collectors.toList());
}

System.out.println(cached.size());
~~~

**Đáp án:** Có. Danh sách đã được tạo trước khi nguồn đóng; các chuỗi nằm trong `cached` không phụ thuộc vào Stream để tồn tại.

### Bài 5 — Lỗi I/O khi đọc trễ

**Câu hỏi:** Nếu `Files.lines` mở thành công nhưng phát sinh lỗi khi terminal operation đang đọc các dòng, có phải mọi trường hợp đều chỉ ném `IOException` checked không?

**Đáp án:** Không. Một số lỗi khi duyệt lazy được đóng gói thành `UncheckedIOException`. Cần đọc hợp đồng nguồn và xử lý lỗi ở tầng thích hợp, đồng thời vẫn dùng `try-with-resources` để đóng nguồn.

### Bài 6 — Thử nghiệm close handler

~~~java
try (Stream<String> s = Stream.of("x")
        .onClose(() -> System.out.print("CLOSED"))) {

    s.findFirst();
}
~~~

**Câu hỏi:** Khi nào `CLOSED` được in?

**Đáp án:** Khi ra khỏi khối `try` và Java gọi `close()`. `findFirst()` tự nó không kích hoạt close handler.

## 17. Ghi nhớ

- `Stream` triển khai `AutoCloseable` thông qua `BaseStream`; tài nguyên I/O cần đóng thường được quản lý bằng `try-with-resources`.
- `Files.lines`, `Files.list`, `Files.walk` và `Files.find` là các nguồn Stream gắn với tài nguyên; bao toàn bộ quá trình xử lý trong phạm vi đóng rõ ràng.
- Terminal operation như `count`, `collect`, `findFirst` và `anyMatch` **không tự động đóng** Stream.
- Khi sử dụng `BufferedReader.lines()`, phải quản lý **BufferedReader** gốc; chỉ đóng Stream chưa chắc đóng reader.
- Không trả về lazy Stream đã đóng; hoặc trả dữ liệu đã materialize, hoặc chuyển quyền sở hữu Stream còn mở cho caller.
- `try-with-resources` đóng resource khi xử lý bình thường, khi `return` hoặc khi ném ngoại lệ; lỗi khi đóng có thể được gắn vào ngoại lệ chính dưới dạng suppressed.
- `onClose` có thể thêm hành động khi đóng, nhưng không chứng minh pipeline hoàn tất hay xử lý nghiệp vụ thành công.
- Dừng sớm, xử lý song song, collector tùy chỉnh và Stream Gatherers không loại bỏ nghĩa vụ quản lý nguồn I/O.

**Ý chính:** Với Java Stream API, hãy tách bạch **khi pipeline kết thúc** với **khi tài nguyên được đóng**. Một Stream đọc từ I/O phải có chủ sở hữu rõ ràng; `try-with-resources` là cách mặc định, dễ kiểm chứng để bảo đảm nguồn được đóng đúng lúc, kể cả khi xử lý dừng sớm hoặc gặp lỗi.
