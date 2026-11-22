# Xác định quyền sở hữu và trách nhiệm đóng Stream trả về từ API

Một API trả về `Stream<T>` trông rất tiện lợi: bên gọi có thể nối tiếp `filter`, `map`, `limit`, `findFirst` hoặc `collect` mà không phải tải tất cả dữ liệu vào bộ nhớ. Tuy nhiên, khi Stream đọc từ **tệp, thư mục hoặc một nguồn I/O còn mở**, cách trả về đó cũng đặt ra một câu hỏi thiết kế quan trọng: **ai sở hữu tài nguyên và ai phải gọi `close()`?**

Bài học thuộc chương **Nguồn vào ra và quản lý tài nguyên** của mô-đun **JAVA_STREAM_API**. Chúng ta sẽ phân biệt Stream chỉ xử lý dữ liệu trong bộ nhớ với Stream gắn tài nguyên, thiết kế hợp đồng API trả về Stream, nhận diện lỗi đóng quá sớm hoặc rò rỉ tài nguyên, sử dụng `try-with-resources` và `onClose`, cũng như xử lý các trường hợp pipeline lazy, dừng sớm, ngoại lệ và song song. Những nguyên tắc này có liên hệ với `filter`, `map`, `reduce`, `collect`, `Spliterator` và các phép xử lý Stream nâng cao; nhưng điểm cốt lõi của bài là **vòng đời tài nguyên**, không phải cú pháp phép biến đổi.

## 1. Hai vòng đời phải phân biệt: Stream và tài nguyên bên dưới

`Stream<T>` biểu diễn một chuỗi thao tác xử lý phần tử. Một Stream có thể được tạo từ:

- `List.stream()`, `Arrays.stream(...)` hoặc `Stream.of(...)`: thông thường không nắm giữ tệp hoặc kết nối bên ngoài.
- `Files.lines(path)`: đọc các dòng từ một tệp còn mở khi duyệt dữ liệu.
- `Files.list(path)`, `Files.walk(path)` hoặc `Files.find(...)`: duyệt các mục trong hệ thống tệp với những tài nguyên I/O cần được giải phóng.
- Một API riêng dùng `BufferedReader`, cơ sở dữ liệu, socket hoặc tài nguyên khác làm nguồn dữ liệu.

Tất cả Stream đều có phương thức `close()` vì `BaseStream` mở rộng `AutoCloseable`. Nhưng **không phải mọi Stream đều cần đóng trong thực tế**. Stream chỉ từ bộ sưu tập thông thường không có tài nguyên I/O phải giải phóng; ngược lại, những Stream do `Files.lines` hoặc `Files.walk` trả về phải được đóng đúng cách.

| Nguồn | Có tài nguyên ngoài cần đóng? | Cách xử lý điển hình |
| --- | --- | --- |
| `List.of(...).stream()` | Không, trong trường hợp bình thường | Có thể gọi terminal operation mà không cần `try-with-resources` |
| `IntStream.range(...)` | Không | Không cần đóng vì I/O |
| `Stream.of(...)` | Không | Không cần đóng vì I/O |
| `Files.lines(path)` | Có, tài nguyên đọc tệp | `try (Stream<String> lines = ...) { ... }` |
| `Files.list(path)` | Có, tài nguyên duyệt thư mục | Đóng Stream khi xong |
| `Files.walk(path)` / `Files.find(...)` | Có, tài nguyên duyệt cây thư mục | Đóng Stream khi xong |
| `BufferedReader.lines()` | Tài nguyên thuộc `BufferedReader` được cung cấp | Đóng `BufferedReader` theo hợp đồng sở hữu; đừng mặc định đóng Stream sẽ đóng reader |
| Stream từ API ứng dụng | Tùy cách triển khai | **Hợp đồng API phải nói rõ** ai đóng và đóng sẽ giải phóng gì |

### Hai khái niệm thường bị nhầm

1. **Tiêu thụ (consume)**: gọi terminal operation như `count()`, `toList()` hoặc `findFirst()`. Sau đó không được tiếp tục sử dụng cùng Stream để thực hiện một terminal operation khác.
2. **Đóng (close)**: yêu cầu đóng Stream, chạy các close handler đã đăng ký và giải phóng các tài nguyên gắn với pipeline theo hợp đồng nguồn.

Hai hành động **không đồng nghĩa**. Việc terminal operation đã chạy đến cuối **không tự động bảo đảm nguồn I/O được đóng**. Ngược lại, đóng Stream khi bên gọi vẫn cần duyệt nó là đóng quá sớm.

## 2. Quy tắc sở hữu cơ bản: bên nào nhận quyền sở hữu phải đóng

Với API trả về Stream, có hai mô hình hợp lệ, miễn là được định nghĩa tường minh:

| Thiết kế API | Chủ sở hữu tài nguyên khi xử lý | Trách nhiệm đóng |
| --- | --- | --- |
| API mở tệp và **trả về Stream còn sống** | Chuyển quyền sở hữu Stream cho bên gọi | **Bên gọi** đóng Stream trả về |
| API tự mở tệp, thực hiện terminal operation, chỉ trả về `List`/`long`/kết quả domain | **API** giữ quyền sở hữu suốt thao tác | **API** đóng tài nguyên trước khi trả kết quả |
| Bên gọi tạo Stream rồi **truyền vào** phương thức xử lý mượn | Bên gọi vẫn sở hữu, trừ khi có thỏa thuận chuyển giao | Bên gọi đóng nếu Stream có tài nguyên |
| API trả Stream được xây trên tài nguyên do **bên khác quản lý** | Phụ thuộc hợp đồng của đối tượng nguồn | Không tự đóng hoặc chuyển quyền sở hữu nếu chưa được thỏa thuận |

Không có quy tắc kỹ thuật rằng “ai tạo Stream thì luôn phải đóng”. Đúng hơn: **ai tạo tài nguyên phải bảo đảm một hợp đồng sở hữu rõ ràng**; họ có thể tự đóng hoặc chủ động chuyển trách nhiệm đóng cho bên gọi khi trả Stream. Việc chuyển giao phải hiển thị trong tài liệu, vì kiểu `Stream<T>` tự nó không nói cho bên gọi rằng có tệp đang mở.

Quy ước đơn giản nên ưu tiên:

- API trả **Stream còn sống**: tài liệu ghi rõ “caller must close returned Stream”, ví dụ với `try-with-resources`.
- API trả **kết quả đã tính xong**: phương thức sở hữu và đóng tài nguyên bên trong.
- API nhận **Stream mượn từ người gọi**: không tự đóng Stream đầu vào, trừ khi hợp đồng nói quyền sở hữu được chuyển giao.

## 3. API trả Stream do `Files.lines` tạo: chuyển trách nhiệm cho caller

Ví dụ một phương thức trả về các dòng không trống, đã loại khoảng trắng đầu/cuối. API muốn giữ tính lazy: chưa đọc toàn bộ tệp thành một danh sách.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public final class TextLineApi {
    private TextLineApi() {}

    /**
     * Mở một nguồn đọc tệp và trả về Stream còn sống.
     *
     * Bên gọi sở hữu Stream trả về và PHẢI đóng bằng
     * try-with-resources, kể cả khi chỉ dùng findFirst()/limit().
     *
     * @throws IOException nếu không mở được nguồn đọc.
     */
    public static Stream<String> readNonBlankLines(Path path)
            throws IOException {
        return Files.lines(path, StandardCharsets.UTF_8)
            .map(String::strip)
            .filter(line -> !line.isEmpty());
    }
}
```

Bên gọi đúng:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class ReadNonBlankExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("notes.txt");

        try (Stream<String> lines = TextLineApi.readNonBlankLines(path)) {
            List<String> results = lines
                .limit(10)
                .toList();

            System.out.println(results);
        } // close() được gọi kể cả khi pipeline dừng sớm.
    }
}
```

Trong ví dụ trên, `TextLineApi` mở nguồn tệp và **chuyển quyền sở hữu Stream trả về** cho bên gọi. Khi đóng Stream được trả về (sau các thao tác trung gian `map` và `filter`), các close handler của pipeline sẽ được chạy, từ đó đóng tài nguyên đọc tệp do `Files.lines` quản lý.

Điểm cần nhớ: `map`, `filter` và `limit` không biến một Stream gắn tệp thành Stream độc lập với tệp. Chúng chỉ tạo pipeline xử lý trên **cùng nguồn còn mở**.

### 3.1. Vì sao cần khai báo rõ trong tài liệu API?

Chữ ký:

```java
Stream<String> readNonBlankLines(Path path) throws IOException;
```

không thể hiện quyền sở hữu ở cấp hệ thống kiểu. Nếu bên gọi chỉ nhìn phương thức trả `Stream<String>`, họ có thể tưởng `count()` tự giải phóng nguồn.

Tài liệu API nên cho biết tối thiểu:

1. **Ai đóng**: bên gọi phải đóng Stream trả về.
2. **Khi nào đóng**: sau khi hoàn thành terminal operation hoặc khi không dùng nữa, kể cả dừng sớm và khi có lỗi.
3. **Nguồn tài nguyên**: Stream duyệt tệp/thư mục và giữ tài nguyên trong vòng đời của nó.
4. **Trạng thái tiêu thụ**: Stream dùng được một lần, không được dùng lại sau terminal operation.
5. **Ngoại lệ**: lỗi mở có thể là `IOException`; lỗi đọc phát sinh khi duyệt có thể xuất hiện dưới dạng `UncheckedIOException`.
6. **Tính nhất quán**: dữ liệu tệp có thể thay đổi giữa lúc tạo Stream và lúc duyệt; không hứa ảnh chụp dữ liệu nếu API không bảo đảm điều đó.

Một tên hàm chứa chữ `open` (chẳng hạn `openLines`) có thể gợi ý có tài nguyên, nhưng **không thay thế được hợp đồng đóng**.

## 4. Lỗi nghiêm trọng: trả Stream từ bên trong `try-with-resources`

Đoạn sau **sai vòng đời tài nguyên**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static Stream<String> brokenApi(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank());
    } // lines bị đóng TRƯỚC khi caller thực hiện terminal operation!
}
```

`return` xảy ra trong khối `try` nhưng việc thoát khối vẫn đóng `lines`. Pipeline trả về chưa được tiêu thụ vì `filter` là thao tác trung gian lazy. Khi bên gọi cố gọi `toList()`, `count()` hoặc `findFirst()`, Stream đã bị đóng và không còn hợp lệ để sử dụng.

**Cách sửa A — trả Stream còn mở và chuyển quyền sở hữu:**

```java
public static Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path).filter(s -> !s.isBlank());
}

// Bên gọi:
try (Stream<String> lines = openLines(path)) {
    long count = lines.count();
    System.out.println(count);
}
```

**Cách sửa B — API tự quản lý tài nguyên và trả kết quả vật hóa:**

```java
import java.util.List;

public static List<String> loadLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank()).toList();
    }
}

// Bên gọi nhận List<String>, không giữ tài nguyên tệp.
List<String> values = loadLines(path);
```

Hai cách đều hợp lệ, nhưng chọn theo mục tiêu: muốn duyệt lazy/không giữ toàn bộ dữ liệu thì trả Stream còn sống và ghi rõ trách nhiệm đóng; muốn API che giấu tài nguyên và có kết quả độc lập thì xử lý bên trong, đóng trước khi trả.

## 5. Terminal operation, xử lý lazy và dừng sớm không tự đóng

Một nguồn `Files.lines` mở tài nguyên đọc tệp. Các thao tác `filter`, `map`, `skip`, `limit` tạo các bước trung gian; terminal operation mới kích hoạt việc xử lý phần tử.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path file = Path.of("events.log");

try (Stream<String> stream = Files.lines(file)) {
    boolean hasError = stream
        .filter(line -> !line.isBlank())
        .anyMatch(line -> line.contains("ERROR"));

    System.out.println(hasError);
}
```

`anyMatch` có thể dừng ngay khi thấy lỗi; nó không có nghĩa mọi dòng đã được đọc. Nhưng **đóng Stream vẫn cần thiết** để giải phóng tài nguyên được giữ bởi `Files.lines`.

Tương tự:

```java
try (Stream<String> stream = Files.lines(file)) {
    String first = stream
        .filter(line -> line.startsWith("WARN"))
        .findFirst()
        .orElse("không có cảnh báo");

    System.out.println(first);
}
```

Với `findFirst`, không được suy rằng hệ thống sẽ đọc đến cuối tệp trước khi đóng. Try-with-resources gọi `close()` khi rời khối, dù pipeline chỉ tiêu thụ một phần nhỏ nguồn.

### 5.1. Các tình huống thường gặp

| Pipeline | Có thể không đọc hết dữ liệu? | Cần đóng Stream gắn I/O? |
| --- | --- | --- |
| `filter(...).count()` | Thông thường phải xét dữ liệu để đếm; có thể có tối ưu | **Có** |
| `findFirst()` | Có | **Có** |
| `anyMatch(...)` | Có | **Có** |
| `limit(5).toList()` | Có | **Có** |
| `noneMatch(...)` | Có | **Có** |
| `toList()` | Thường thu thập toàn bộ phần tử đi đến cuối pipeline | **Có** |
| `reduce(...)` | Thường cần tiêu thụ mọi phần tử được giảm | **Có** |

Quy tắc không phụ thuộc số lượng phần tử đã xử lý: **nguồn có tài nguyên ngoài thì cần được đóng khi kết thúc sử dụng**, kể cả khi nguồn rỗng hoặc terminal operation trả về sớm.

## 6. Ngoại lệ trong pipeline: `try-with-resources` vẫn đóng nguồn

Lỗi có thể xuất hiện **sau lúc API trả Stream**, bởi nhiều công việc đọc và biến đổi được hoãn đến terminal operation. Ví dụ dòng có định dạng không hợp lệ:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long sumFile(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
            .filter(s -> !s.isBlank())
            .mapToLong(Long::parseLong)
            .sum();
    }
}
```

Nếu có dòng `"abc"`, `Long.parseLong` ném `NumberFormatException` trong lúc tiêu thụ pipeline. **Try-with-resources vẫn gọi `close()`**, sau đó ngoại lệ được truyền ra ngoài theo ngữ nghĩa Java.

Khi đọc từ `Files.lines` hoặc `Files.walk`, cần phân biệt:

- **Lúc mở Stream**: có thể phát sinh `IOException` được khai báo.
- **Lúc duyệt Stream**: lỗi I/O có thể được đóng gói thành `UncheckedIOException`.
- **Trong lambda**: lỗi từ logic nghiệp vụ (ví dụ `NumberFormatException`) có thể xuất hiện trong terminal operation.
- **Lúc đóng**: close handler hoặc nguồn có thể gặp lỗi; try-with-resources quản lý cơ chế *suppressed exceptions* khi vừa có lỗi xử lý vừa có lỗi đóng.

Không chỉ đóng trong nhánh xử lý thành công. Cũng không nên gọi `close()` thủ công ở nhiều nhánh `return`/`catch` khi `try-with-resources` đã thể hiện hợp đồng rõ ràng.

### 6.1. Không nên chỉ đóng trong `finally` khi đã có try-with-resources

Dạng thủ công vẫn có thể đúng nếu xử lý cẩn thận:

```java
Stream<String> lines = Files.lines(path);
try {
    return lines.count();
} finally {
    lines.close();
}
```

Nhưng dạng khuyến nghị gọn hơn và xử lý ngoại lệ đóng tốt hơn:

```java
try (Stream<String> lines = Files.lines(path)) {
    return lines.count();
}
```

## 7. API tự sở hữu tài nguyên: trả kết quả đã tính

Không phải API nào cũng nên trả Stream. Khi mục tiêu chỉ là đếm, tìm một giá trị hoặc tạo danh sách nhỏ, API có thể tự mở và đóng nguồn.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public final class LogReportApi {
    private LogReportApi() {}

    public static long countErrors(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines.filter(line -> line.contains("ERROR")).count();
        }
    }

    public static List<String> firstFiveErrors(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> line.contains("ERROR"))
                .limit(5)
                .toList();
        }
    }
}
```

Ở đây:

- API **giữ quyền sở hữu** từ khi `Files.lines` được gọi đến khi khối `try` kết thúc.
- Caller nhận `long` hoặc `List<String>`, **không phải Stream còn giữ tệp**.
- `firstFiveErrors` vẫn có thể dừng sớm nhờ `limit(5)`, nhưng nguồn luôn được đóng.
- `List` là kết quả vật hóa; nếu lọc rất nhiều phần tử và trả toàn bộ danh sách, phải cân nhắc bộ nhớ.

### 7.1. API tự đóng có thể nhận một hàm xử lý

Khi muốn cho caller linh hoạt nhưng **không chuyển trách nhiệm đóng**, một thiết kế khác là API nhận một hàm xử lý nguồn.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;
import java.util.stream.Stream;

public final class SafeFileStreams {
    private SafeFileStreams() {}

    public static <R> R withLines(
            Path path,
            Function<? super Stream<String>, ? extends R> action
    ) throws IOException {
        try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
            return action.apply(lines);
        }
    }
}
```

Bên gọi sử dụng:

```java
long count = SafeFileStreams.withLines(
    Path.of("events.log"),
    lines -> lines.filter(line -> line.contains("ERROR")).count()
);
```

Hợp đồng của `withLines`: hàm `action` phải **tiêu thụ và trả kết quả hoàn tất ngay bên trong lời gọi**, không trả ra một Stream lười hay đối tượng phụ thuộc vào Stream đó. Nếu `action` trả về một Stream chứa các phép trung gian nhưng chưa được tiêu thụ, nguồn sẽ đóng trước khi caller dùng nó. Vì vậy nên ghi rõ ràng buộc này trong JavaDoc và cân nhắc API chuyên biệt nếu muốn bảo đảm mạnh hơn ở cấp kiểu.

Thiết kế callback phù hợp khi muốn caller tùy chọn `filter`, `map`, `reduce` và `collect` mà không phải nhớ đóng tài nguyên. Đổi lại, API cần kiểm soát rõ phạm vi xử lý đồng bộ và không để rò rỉ tham chiếu nguồn.

## 8. API nhận Stream của bên gọi: tiêu thụ không đồng nghĩa sở hữu

Xét phương thức chỉ tổng hợp các dòng và **nhận** một Stream được tạo ở nơi khác:

```java
import java.util.stream.Stream;

public static long countNonBlank(Stream<String> lines) {
    return lines.filter(s -> !s.isBlank()).count();
}
```

Phương thức này **tiêu thụ** Stream được truyền vào, nhưng điều đó không có nghĩa nó được phép **đóng** tài nguyên thuộc bên gọi. Khi kiểu đầu vào chỉ là `Stream<String>`, có thể gặp cả Stream in-memory và Stream đang đọc tệp.

Quy tắc đề xuất: phương thức **mượn** Stream để tiêu thụ, **không đóng** nó; bên gọi giữ trách nhiệm đóng khi nguồn có tài nguyên I/O.

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("events.log");

try (Stream<String> lines = Files.lines(path)) {
    long number = countNonBlank(lines);
    System.out.println(number);
}
```

Nếu API muốn **nhận luôn quyền sở hữu** và tự đóng Stream đầu vào, phải nói rõ điều đó là một **ownership transfer**, ví dụ thông qua tên phương thức, tài liệu API hoặc kiểu wrapper riêng. Không được vừa cho rằng caller sẽ đóng vừa tự âm thầm đóng trong hàm mượn, đặc biệt khi tài nguyên bên dưới có thể được chia sẻ.

### 8.1. Đừng truyền một Stream đã dùng

```java
Stream<String> values = Stream.of("A", "B");

long count = countNonBlank(values); // Stream đã được tiêu thụ.

// values.findFirst(); // Không hợp lệ: Stream không thể sử dụng lần hai.
```

Ngay cả khi không đóng, terminal operation đã tiêu thụ Stream. Đây là **hạn chế sử dụng một lần**, tách biệt với hợp đồng sở hữu và việc đóng.

## 9. Đặc điểm của `BufferedReader.lines()`: ai sở hữu reader?

`BufferedReader.lines()` trả một `Stream<String>` đọc từ `BufferedReader`. Trong thiết kế này, đối tượng **reader** vẫn là tài nguyên được quản lý. Không nên giả định rằng **đóng Stream trả về từ `reader.lines()` sẽ tự đóng reader**.

Cách sử dụng đúng khi API sở hữu reader:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static long countComments(Path path) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
            .filter(line -> line.stripLeading().startsWith("#"))
            .count();
    }
}
```

Khối `try` đóng **`BufferedReader`**, là tài nguyên thật sự được mở. `reader.lines()` chỉ biểu diễn việc duyệt các dòng từ reader đó.

### 9.1. Nếu buộc phải trả Stream từ reader, gắn trách nhiệm đóng

Có thể gắn `onClose` để khi bên gọi đóng Stream, reader cũng được đóng:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static Stream<String> openReaderLines(Path path) throws IOException {
    BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);

    return reader.lines().onClose(() -> {
        try {
            reader.close();
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    });
}

// Caller:
try (Stream<String> lines = openReaderLines(Path.of("events.log"))) {
    System.out.println(lines.findFirst());
}
```

`onClose` không tự đóng reader ngay khi khai báo pipeline; nó chỉ đăng ký **hành động khi Stream được đóng**. Nếu caller quên đóng, reader vẫn có nguy cơ còn mở. Vì nguồn tệp đơn giản đã có `Files.lines` với hợp đồng đóng rõ ràng, hãy ưu tiên nó thay vì tự xây adapter từ reader nếu không có yêu cầu đặc biệt.

Với adapter thực tế phức tạp hơn, phải bảo đảm giải phóng reader nếu quá trình tạo Stream/đăng ký handler thất bại **trước khi trả quyền sở hữu** cho bên gọi; đồng thời xử lý đúng các ngoại lệ phát sinh lúc đóng.

## 10. `onClose`: close handler khác với terminal operation

Phương thức `onClose(Runnable)` đăng ký một hành động sẽ được gọi khi Stream đóng. Nó hữu ích để gắn bước giải phóng tài nguyên, đánh dấu một phiên hoặc ghi nhận sự kiện đóng.

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

AtomicInteger closed = new AtomicInteger();

try (Stream<String> words = Stream.of("A", "B")
        .onClose(() -> closed.incrementAndGet())) {
    List<String> result = words.toList();

    System.out.println(result);       // [A, B]
    System.out.println(closed.get());  // 0: chưa rời khối try.
}

System.out.println(closed.get());      // 1: close handler đã chạy.
```

Ví dụ `Stream.of` không cần đóng vì I/O; `try-with-resources` được sử dụng ở đây để **minh họa hành vi handler**. Trong ứng dụng, không nên lạm dụng `onClose` để tạo side effect thay thế cho logic nghiệp vụ.

Khi một handler ném ngoại lệ, Java vẫn phải xử lý các handler đã đăng ký khác theo hợp đồng đóng, và lỗi bổ sung có thể được ghi nhận dưới dạng suppressed exception. Đừng mặc định mọi lỗi khi đóng đều xảy ra tại thời điểm tạo Stream.

### 10.1. Đóng Stream được trả về sau `map`/`filter`

```java
AtomicInteger closeCount = new AtomicInteger();

Stream<String> source = Stream.of(" a ", " b ")
    .onClose(closeCount::incrementAndGet);

try (Stream<String> transformed = source
        .map(String::strip)
        .filter(s -> !s.isEmpty())) {
    System.out.println(transformed.toList()); // [a, b]
}

System.out.println(closeCount.get()); // 1
```

Trong pipeline này, `transformed` và `source` thuộc **cùng pipeline**, không phải hai nguồn độc lập. Đóng Stream được trả về ở cuối pipeline sẽ thực thi handler đã gắn lên nguồn.

Không giữ cả `source` và `transformed` như hai tài nguyên độc lập để tiêu thụ riêng. Sau khi kết thúc pipeline, Stream không được dùng lại.

## 11. Hoàn tất với `flatMap` và các Stream con

`flatMap` có thể tạo một Stream con cho mỗi phần tử nguồn. Theo hợp đồng Stream, từng Stream con được sinh bởi mapper sẽ được **đóng sau khi nội dung của nó được đưa vào pipeline**.

Ví dụ tách mỗi chuỗi thành các ký tự:

```java
import java.util.List;

List<String> tokens = List.of("AB", "CD");

List<String> chars = tokens.stream()
    .flatMap(text -> text.codePoints()
        .mapToObj(cp -> new String(Character.toChars(cp))))
    .toList();

System.out.println(chars); // [A, B, C, D]
```

Nhưng việc `flatMap` đóng các Stream con **không có nghĩa Stream nguồn có tài nguyên I/O luôn được tự đóng sau terminal operation**. Nếu luồng ngoài được lấy từ `Files.lines`, bên gọi vẫn phải đóng luồng ngoài:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines = Files.lines(Path.of("codes.txt"))) {
    long characterCount = lines
        .flatMapToInt(String::codePoints)
        .count();

    System.out.println(characterCount);
}
```

Trường hợp các Stream con cũng sở hữu tài nguyên riêng cần được xem xét theo hợp đồng của API tạo Stream con; đừng xây một cấu trúc phân cấp tài nguyên phức tạp mà không xác định rõ nơi phát sinh và nơi đóng từng nguồn.

## 12. Ví dụ Java 17 hoàn chỉnh: API trả Stream và API tự đóng

Ví dụ sau minh họa **hai kiểu hợp đồng** trên một tệp tạm do chương trình tạo ra. Phần `openRecords` chuyển quyền sở hữu Stream cho caller; phần `countRecords` tự đóng và chỉ trả kết quả `long`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class StreamOwnershipDemo {

    /**
     * Caller owns the returned Stream and must close it.
     */
    public static Stream<String> openRecords(Path file) throws IOException {
        return Files.lines(file, StandardCharsets.UTF_8)
            .map(String::strip)
            .filter(line -> !line.isEmpty());
    }

    /**
     * This method owns and closes the file-backed Stream.
     */
    public static long countRecords(Path file) throws IOException {
        try (Stream<String> lines = openRecords(file)) {
            return lines.count();
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("stream-ownership-", ".txt");

        try {
            Files.write(
                file,
                List.of("  A ", "  ", "B  "),
                StandardCharsets.UTF_8
            );

            // Hợp đồng 1: Caller đóng Stream trả về.
            try (Stream<String> records = openRecords(file)) {
                System.out.println(records.toList()); // [A, B]
            }

            // Hợp đồng 2: API đóng bên trong, trả số.
            System.out.println(countRecords(file));   // 2
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Những điều ví dụ chứng minh về thiết kế:

1. `openRecords` **không** đóng Stream trước khi trả về.
2. Caller luôn bao kết quả của `openRecords` trong `try-with-resources`.
3. `countRecords` tiêu thụ Stream bên trong phạm vi chính nó và tự đóng.
4. `Files.write` và `Files.deleteIfExists` chỉ phục vụ việc dựng dữ liệu minh họa; API thực tế nên áp dụng chính sách quyền tệp và lỗi I/O phù hợp.
5. Sau khi `openRecords` được tiêu thụ bằng `toList()`, danh sách là dữ liệu trong bộ nhớ; không phụ thuộc nguồn tệp đã đóng.

Nếu ứng dụng đang xử lý tệp có thể thay đổi do một tiến trình khác, cần thêm quy tắc nhất quán hoặc cách cố định dữ liệu; hợp đồng đóng tài nguyên **không tự tạo snapshot nhất quán**.

## 13. Thiết kế API theo nhu cầu: nên trả loại gì?

| Mong muốn của caller | Thiết kế khuyến nghị | Trách nhiệm đóng |
| --- | --- | --- |
| Duyệt rất nhiều dòng, tự chọn `filter`/`map`, tránh giữ toàn bộ | Trả `Stream<T>` lazy từ nguồn I/O | Caller đóng Stream; phải có tài liệu hợp đồng |
| Chỉ cần số lượng hoặc một phép tổng | Trả `long`, `int`, `BigInteger` hoặc kết quả domain | API mở, tiêu thụ, đóng bên trong |
| Cần danh sách có thể sử dụng lâu dài sau khi tệp đóng | Trả `List<T>` đã vật hóa | API đóng trước khi trả |
| Muốn linh hoạt chọn phép xử lý nhưng không muốn lộ quyền sở hữu | Nhận callback xử lý đồng bộ trong phạm vi mở nguồn | API đóng, callback không được để dữ liệu lazy thoát ra |
| Đã có `BufferedReader` thuộc caller | Phương thức nhận reader hoặc Stream mượn; không tự đóng trừ khi chuyển giao rõ | Chủ sở hữu reader đóng |
| Cần điều khiển vòng đời phức tạp nhiều tài nguyên | Thiết kế wrapper `AutoCloseable` chuyên dụng kèm hợp đồng đóng | Theo wrapper/API; không chỉ dựa vào kiểu `Stream` |

Không có một dạng API tốt cho mọi trường hợp. Đánh đổi là giữa **tính lazy và quyền kiểm soát phía caller**, **bộ nhớ khi vật hóa kết quả**, cùng **độ rõ của vòng đời tài nguyên**.

### 13.1. Một mẫu JavaDoc tối thiểu

```java
/**
 * Lazily reads records from the file.
 *
 * <p>The returned Stream owns an open file resource.
 * The caller must close it, preferably using try-with-resources.
 * Closing the returned Stream releases the underlying resource.
 * The Stream can be consumed only once.
 *
 * @throws IOException if the resource cannot be opened
 * @throws java.io.UncheckedIOException if an I/O failure occurs
 *         during traversal
 */
public static Stream<String> openRecords(Path path) throws IOException;
```

Mẫu này chỉ minh họa **hợp đồng tài liệu**, không phải một khai báo phương thức dùng để biên dịch độc lập mà không có thân hàm. Nếu API có thêm ràng buộc về encoding, thời gian sống của kết nối, thứ tự hoặc thread-safety, cũng phải ghi cụ thể.

## 14. Xử lý song song và vòng đời tài nguyên

`parallel()` thay đổi cách pipeline có thể xử lý các phần tử, **không chuyển trách nhiệm đóng** sang JVM. Nếu Stream từ `Files.lines` được xử lý song song, caller vẫn phải đóng:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines = Files.lines(Path.of("events.log"))) {
    long errors = lines.parallel()
        .filter(line -> line.contains("ERROR"))
        .count();

    System.out.println(errors);
}
```

Không nên mặc định xử lý song song nhanh hơn với I/O. Truy cập tệp, chi phí giải mã, contention và đặc tính chia nguồn của `Spliterator` đều ảnh hưởng hiệu năng. Với nhiều nguồn hoặc tài nguyên không an toàn khi đồng thời, cần xem xét hợp đồng của nguồn trước khi chuyển sang parallel Stream.

### 14.1. Không sửa hoặc đóng nguồn giữa lúc đang duyệt

Nếu một luồng khác đóng Stream hoặc tài nguyên I/O khi pipeline vẫn đang hoạt động, kết quả có thể thất bại hoặc không được bảo đảm theo hợp đồng nguồn. Tránh thiết kế mà nhiều thành phần cùng tưởng mình là chủ sở hữu được phép đóng bất kỳ lúc nào.

Đặc biệt, nếu API trả Stream từ cơ sở dữ liệu hoặc kết nối có trạng thái, cần một hợp đồng riêng về concurrency, transaction và lifetime của connection. Không suy từ việc `Stream<T>` có `parallel()` rằng nguồn bên dưới cũng hỗ trợ truy cập đồng thời.

## 15. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| API trả `Files.lines(...).filter(...)` nhưng không nói caller phải đóng | Người dùng API dễ bỏ quên tài nguyên | Viết rõ hợp đồng và mẫu `try-with-resources` |
| API `return stream` trong khối `try-with-resources` | Stream đóng trước khi caller tiêu thụ | Hoặc trả Stream còn mở, hoặc tiêu thụ trong `try` và trả kết quả |
| Cho rằng `toList()`/`count()` tự đóng Stream I/O | Tài nguyên có thể tiếp tục mở | Dùng `try-with-resources` |
| Dừng sớm bằng `findFirst`/`anyMatch` rồi bỏ qua `close()` | Không giải phóng tài nguyên | Vẫn đóng nguồn khi rời phạm vi |
| Chỉ đóng ở nhánh thành công | Rò rỉ khi mapper/terminal operation ném ngoại lệ | Bao nguồn bằng `try-with-resources` |
| Đóng `Stream` từ `reader.lines()` rồi tưởng reader đã đóng | Reader còn mở | Đóng `BufferedReader`, hoặc gắn close handler khi chuyển quyền sở hữu |
| Tạo `onClose` rồi tưởng hành động đóng sẽ tự chạy sau terminal operation | Handler không chạy nếu Stream không đóng | Caller/API vẫn phải gọi `close()` đúng trách nhiệm |
| Phương thức nhận Stream mượn rồi tự ý đóng | Phá vòng đời của caller | Chỉ đóng khi hợp đồng nói đã nhận chuyển quyền sở hữu |
| Dùng lại cùng Stream sau `count()`/`toList()` | Stream đã tiêu thụ | Tạo nguồn mới nếu cần duyệt lại |
| Đóng source rồi cố duyệt pipeline đã tạo từ source | Đóng quá sớm, không thể duyệt | Đóng **sau** toàn bộ terminal operation của pipeline |
| Dùng `Files.lines` rồi thu tất cả bằng `toList()` mà không nghĩ đến bộ nhớ | Có thể giữ dữ liệu lớn trong bộ nhớ | Chọn kết quả tổng hợp/Stream lazy tùy mục tiêu |
| Truyền Stream I/O cho API callback rồi để Stream lazy thoát khỏi phạm vi | Tài nguyên đóng trước khi pipeline được dùng | Chỉ trả kết quả đã hoàn tất trong callback |
| Bật `parallel` nhưng nghĩ framework sẽ tự quản lý đóng nguồn | Quyền sở hữu không đổi | Đóng ở chủ sở hữu đã xác định |
| Dùng `map`/`peek` để giải phóng tài nguyên của nguồn | Không bảo đảm chạy đủ, đặc biệt khi short-circuit | Dùng `close`/`onClose`/`try-with-resources` |
| Đóng nhiều thành phần chia sẻ cùng connection mà không có hợp đồng | Đóng trùng hoặc làm hỏng tác vụ khác | Thiết kế vòng đời owner/borrower rõ ràng |

## 16. Bài tập thực hành

### Bài 1: Xác định bên nào phải đóng

Phân loại sáu nguồn: `List.stream()`, `IntStream.range()`, `Files.lines()`, `Files.list()`, `BufferedReader.lines()` và một API `openRecords(path)` trả về Stream có JavaDoc “caller must close”. Nêu **tài nguyên thực sự** cần đóng và bên chịu trách nhiệm.

### Bài 2: Sửa API đóng quá sớm

Cho:

```java
Stream<String> openBadly(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> s.length() > 5);
    }
}
```

Giải thích vì sao `openBadly(path).count()` không hợp lệ. Viết hai phiên bản sửa: (a) trả Stream lazy có JavaDoc chuyển ownership và (b) trả `List<String>` đã thu thập bên trong `try-with-resources`.

### Bài 3: Dừng sớm vẫn đóng nguồn

Viết API tìm dòng đầu tiên bắt đầu bằng `"ERROR"` trong một tệp:

```java
Optional<String> firstError(Path path) throws IOException
```

Cài đặt bằng `Files.lines`, `filter` và `findFirst`. Chỉ ra vị trí đặt `try-with-resources` để nguồn luôn được đóng, kể cả khi tìm thấy dòng đầu tiên.

### Bài 4: Thiết kế API hai kiểu ownership

Triển khai hai phương thức:

```java
Stream<String> openNames(Path path) throws IOException;
long countNames(Path path) throws IOException;
```

Một phương thức chuyển trách nhiệm đóng cho caller, phương thức còn lại tự đóng. Viết ví dụ caller đúng cho cả hai và mô tả điều gì xảy ra nếu caller quên đóng kết quả của `openNames`.

### Bài 5: Callback và kết quả lazy

Cho API `withLines(path, Function<Stream<String>, R>)`. Thử callback trả `lines.filter(...)` mà chưa gọi terminal operation. Vì sao kết quả Stream không thể duyệt sau khi `withLines` trả về? Hãy thay callback bằng `lines.filter(...).count()` hoặc `toList()` rồi giải thích sự khác biệt.

### Bài 6: `onClose` và lỗi xử lý

Tạo một Stream từ `Stream.of(...)` có `onClose` tăng bộ đếm `AtomicInteger`. Bên trong `try-with-resources`, gọi một terminal operation có mapper ném `IllegalArgumentException` cho một phần tử. Kiểm tra bộ đếm sau khi bắt ngoại lệ để xác nhận handler vẫn chạy khi Stream được đóng.

### Bài 7: Quản lý `BufferedReader`

Viết `countNonBlank(Path path)` bằng `Files.newBufferedReader` và `reader.lines()`. Dùng `try-with-resources` cho đúng đối tượng owner. Sau đó giải thích vì sao `reader.lines().onClose(...)` có thể cần thiết nếu API buộc phải trả Stream từ reader cho caller.

### Bài 8: Lựa chọn cho tệp lớn

Một tệp log có hàng chục triệu dòng. Đánh giá ba API: (a) trả `List<String>` toàn bộ, (b) trả `Stream<String>` lazy có trách nhiệm đóng ở caller, và (c) nhận callback trả số liệu tổng hợp. So sánh bộ nhớ, độ linh hoạt, thời gian giữ tài nguyên và rủi ro caller quên đóng.

## 17. Tự kiểm tra kiến thức

- Vì sao tiêu thụ `Stream` bằng `count()` không có nghĩa nguồn I/O đã được đóng?
- Với API trả `Stream` từ `Files.lines`, ai phải đóng và tại sao?
- Điều gì sai khi `return stream.filter(...)` bên trong `try-with-resources`?
- `findFirst()`, `limit(5)` và `anyMatch()` có thay đổi yêu cầu đóng nguồn không?
- `onClose` có tự thực thi ngay khi đăng ký hay không?
- Đóng Stream trả về từ `BufferedReader.lines()` có tự đóng reader không?
- Phương thức chỉ **mượn** Stream từ caller nên đóng nó hay không, và phải ghi hợp đồng gì nếu muốn sở hữu?
- Trường hợp nào API nên trả `List<T>` hoặc `long` thay vì Stream?
- Khi có lỗi trong lambda sau khi mở tệp, `try-with-resources` giúp bảo vệ tài nguyên ra sao?
- Vì sao `parallel()` không thay thế hợp đồng ownership và không bảo đảm I/O nhanh hơn?
- Khi nào callback xử lý Stream trong phạm vi tài nguyên mở là một thiết kế hữu ích?
- Quy tắc nào để không nhầm “đã tiêu thụ một lần” với “đã đóng”?

**Ghi nhớ:** Với Stream gắn tệp hoặc nguồn I/O, **terminal operation không tự thay thế `close()`**. API hoặc **tự đóng sau khi tính xong** rồi trả kết quả độc lập, hoặc **trả Stream còn sống và chuyển rõ trách nhiệm đóng cho caller**. Dùng `try-with-resources` ở đúng nơi sở hữu; đừng trả Stream từ khối `try` đã đóng, đừng bỏ qua việc đóng sau short-circuit, và đừng suy rằng `BufferedReader.lines()` hay `onClose` tự giải phóng tài nguyên nếu không có lời gọi đóng thích hợp.
