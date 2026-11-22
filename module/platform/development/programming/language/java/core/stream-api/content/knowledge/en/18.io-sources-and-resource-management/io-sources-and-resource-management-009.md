# Tránh giữ tài nguyên mở khi trả về Stream hoặc nối nhiều nguồn

Stream API giúp xử lý dữ liệu theo kiểu khai báo bằng pipeline lazy như `filter`, `map`, `reduce` và `collect`. Tuy nhiên, **không phải Stream nào cũng chỉ nằm trong bộ nhớ**. Một `Stream<String>` tạo từ `Files.lines(path)` hoặc `Stream<Path>` tạo từ `Files.list(directory)` có thể nắm giữ *file descriptor*, kênh đọc hay handle của thư mục. Nếu chỉ gọi một terminal operation mà không đóng Stream, tài nguyên liên quan có thể tiếp tục mở. Lỗi này đặc biệt khó phát hiện khi phương thức **trả về một Stream còn mở** hoặc khi ghép nhiều nguồn I/O bằng `Stream.concat`.

Bài thuộc chương **Nguồn vào ra và quản lý tài nguyên** của module **JAVA_STREAM_API**. Mục tiêu là phân biệt vòng đời dữ liệu với vòng đời tài nguyên, xác định bên nào sở hữu trách nhiệm đóng, áp dụng `try-with-resources` cho cả pipeline đơn lẻ lẫn nhiều nguồn, và chọn cách viết phù hợp với hiệu năng, xử lý song song và giới hạn tài nguyên. Các ví dụ sử dụng Java 8 trở lên, trừ nơi có ghi rõ khác.

## 1. Phân biệt Stream trong bộ nhớ và Stream gắn tài nguyên

Hai dòng dưới đây đều trả `Stream<String>`, nhưng không có cùng trách nhiệm quản lý tài nguyên:

```java
// Nguồn trong bộ nhớ: không có file handle phát sinh từ lệnh này.
Stream<String> names = Arrays.asList("An", "Bình").stream();

// Nguồn file: phải đóng Stream sau khi sử dụng.
Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8);
```

Các phương thức I/O thường gặp:

| API nguồn | Đối tượng Stream tạo ra | Vì sao cần đóng |
|---|---|---|
| `Files.lines(Path, Charset)` | `Stream<String>` các dòng | Đóng file được mở để đọc |
| `Files.list(Path)` | `Stream<Path>` các entry trực tiếp trong thư mục | Giải phóng tài nguyên duyệt thư mục |
| `Files.walk(Path, ...)` | `Stream<Path>` trong cây thư mục | Giải phóng các tài nguyên duyệt cây thư mục |
| `Files.find(Path, int, BiPredicate<...>, ...)` | `Stream<Path>` lọc kết quả tìm file | Giải phóng tài nguyên duyệt cây thư mục |
| `Collection.stream()` | Stream từ collection | Bản thân lời gọi không mở một file hoặc thư mục |
| `Stream.of(...)`, `IntStream.range(...)` | Stream từ giá trị/dãy trong bộ nhớ | Thông thường không có tài nguyên I/O cần giải phóng |

Với Stream gắn I/O, **hãy đóng bằng `close()`**, thường thông qua `try-with-resources`. Điều này không phủ nhận việc Stream trong bộ nhớ vẫn có thể được gắn `onClose` handler hoặc tài nguyên tự quản khác; hãy đọc hợp đồng của **nguồn tạo Stream**, không suy đoán chỉ từ kiểu `Stream<T>`.

### 1.1. Lazy không có nghĩa mở tài nguyên muộn

`Files.lines(path)` thiết lập một Stream gắn với file khi phương thức được gọi. Các thao tác trung gian như `filter` và `map` thường chỉ chạy lúc tiêu thụ, nhưng **nguồn I/O có thể đã được mở trước terminal operation**:

```java
Stream<String> lines = Files.lines(path);
Stream<String> selected = lines.filter(line -> line.startsWith("ERROR"));
// Chưa gọi count()/findFirst()/collect(), nhưng file có thể đang mở.
```

Do đó, trì hoãn việc tiêu thụ pipeline mà không có cơ chế đóng thích hợp vẫn có nguy cơ giữ tài nguyên mở. Tính lazy của việc xử lý phần tử không tự quản lý vòng đời file.

## 2. Quy tắc nền tảng: mở và đóng trong cùng một phạm vi

Cách an toàn mặc định là `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countErrors(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

Đoạn trên minh họa **một phương thức** (dấu `}` sau cùng đóng phương thức); các import đặt ở đầu file khi dùng trong lớp hoàn chỉnh. `try-with-resources` bảo đảm `lines.close()` được gọi khi rời block, kể cả khi terminal operation ném ngoại lệ.

Vòng đời:

```text
try (mở nguồn Files.lines)
        |
        v
    filter/map/...       <- pipeline được thực thi khi terminal chạy
        |
        v
    count/findFirst/...
        |
        v
close() từ try-with-resources
        |
        v
file handle được giải phóng
```

### 2.1. Terminal operation không đồng nghĩa close

`count()`, `findFirst()`, `forEach()` hay `collect()` **kết thúc việc tiêu thụ pipeline**, nhưng **không tự bảo đảm đóng Stream gắn tài nguyên**:

```java
// KHÔNG NÊN: không đóng Stream do Files.lines trả về.
long count = Files.lines(path).filter(s -> !s.isEmpty()).count();

// NÊN: đóng kể cả khi có lỗi.
try (Stream<String> lines = Files.lines(path)) {
    long safeCount = lines.filter(s -> !s.isEmpty()).count();
    System.out.println(safeCount);
}
```

Đặc biệt, terminal operation **ngắn mạch** như `findFirst()` có thể dừng sau vài dòng, trong khi file vẫn cần được đóng:

```java
Optional<String> firstError;
try (Stream<String> lines = Files.lines(path)) {
    firstError = lines
            .filter(line -> line.startsWith("ERROR"))
            .findFirst();
}
// Đến đây file đã đóng; firstError là giá trị đã tách khỏi nguồn.
```

Phép tìm kiếm ngắn mạch và việc giải phóng tài nguyên là **hai trách nhiệm riêng**.

### 2.2. onClose là handler, không phải cơ chế tự đóng

`Stream.onClose(Runnable)` đăng ký một hành động để chạy **khi Stream được đóng**. Nó không biến việc duyệt Stream thành tự động gọi `close()`:

```java
try (Stream<String> lines = Files.lines(path)
        .onClose(() -> System.out.println("Đã đóng stream"))) {
    lines.limit(1).forEach(System.out::println);
}
// Sau khi rời try: onClose handler được gọi.
```

Đừng dùng `onClose` như một thay thế cho `try-with-resources`. Khi Stream có nhiều handler và xảy ra lỗi trong lúc đóng, Java vẫn cố gắng chạy các handler theo hợp đồng đóng; lỗi bổ sung có thể được ghi nhận dưới dạng *suppressed exception*. Tránh đặt hành động nghiệp vụ không thể hoàn tác trong handler.

## 3. Lỗi số một: trả Stream ra khỏi khối try đã đóng

Ví dụ sau **không an toàn**:

```java
// SAI: return đối tượng Stream đã bị đóng bởi try-with-resources.
public static Stream<String> readLinesBroken(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank());
    }
}
```

Mã minh họa `String.isBlank()` yêu cầu Java 11+. Vấn đề quản lý tài nguyên **không phụ thuộc** phương thức lọc: rời `try` thì `lines` đã đóng; phía gọi nhận một pipeline không còn hợp lệ để duyệt. Vì thế, cố tiêu thụ nó có thể ném `IllegalStateException` như “stream has already been operated upon or closed”.

Để giữ tương thích Java 8, cùng lỗi có thể được minh họa bằng `line -> !line.trim().isEmpty()`. **Không** sửa lỗi bằng cách xóa `try` rồi im lặng trả Stream mở: điều đó chỉ chuyển nguy cơ rò rỉ sang phía gọi.

### 3.1. Trả Stream còn mở: chỉ khi chuyển quyền sở hữu rõ ràng

Nếu thực sự cần API trả Stream để bên gọi tự xây pipeline, có thể chọn hợp đồng **caller owns stream**:

```java
/**
 * Mở Stream đọc dòng. Người gọi BẮT BUỘC đóng Stream trả về.
 * Mỗi lần gọi mở một nguồn I/O riêng.
 */
public static Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

// Phía gọi:
try (Stream<String> lines = openLines(path)) {
    lines
            .filter(line -> !line.trim().isEmpty())
            .forEach(System.out::println);
}
```

Điểm mấu chốt là **không ai được “quên” quyền sở hữu**:

- Phương thức tạo ra Stream phải nêu rõ nghĩa vụ đóng trong tên API, Javadoc hoặc hợp đồng.
- Phía gọi phải dùng `try-with-resources` quanh **toàn bộ quá trình tiêu thụ**.
- Không lưu một Stream mở trong một trường sống lâu, cache hoặc trả xuyên nhiều lớp khi các lớp ấy không xác định rõ ai sẽ đóng.
- Không trả một Stream rồi hy vọng bộ gom rác (*garbage collector*) hoặc thao tác kết thúc sẽ kịp đóng file.

Đây là lựa chọn có thể chấp nhận được khi API của ứng dụng thật sự có mục tiêu **streaming**, nhưng thường khó sử dụng an toàn hơn một API trả dữ liệu đã tính hoặc nhận callback.

## 4. Ba mẫu API an toàn khi muốn đưa kết quả ra khỏi phương thức

### 4.1. Mẫu A: xử lý xong rồi trả kết quả đã tách tài nguyên

Khi kích thước dữ liệu phù hợp để lưu:

```java
public static List<String> loadErrors(Path path) throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.startsWith("ERROR"))
                .collect(Collectors.toList());
    }
}
```

Phía gọi nhận một `List<String>` không phụ thuộc vào file handle. Đổi lại, chương trình phải cấp phát bộ nhớ cho các dòng được giữ trong List. Nếu file rất lớn hoặc dòng lỗi nhiều, cân nhắc tổng hợp/thống kê theo luồng thay vì tải tất cả.

### 4.2. Mẫu B: nhận phép xử lý và thực thi trong phạm vi mở file

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;
import java.util.stream.Stream;

public static <R> R withLines(
        Path path, Function<Stream<String>, R> operation)
        throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return operation.apply(lines);
    }
}

// Sử dụng:
long count = withLines(path, lines ->
        lines.filter(line -> line.startsWith("ERROR")).count());
```

Mẫu callback giữ việc **mở/đóng trong một nơi**, trong khi vẫn cho caller quyết định cách tính qua Stream. Hợp đồng phải quy định `operation` **tiêu thụ và hoàn thành việc dùng Stream ngay trong callback**; không được trả chính Stream, một iterator hay đối tượng lazy khác còn phụ thuộc nguồn đã đóng.

Nếu việc xử lý cần trả về kết quả bất đồng bộ như `CompletableFuture` phụ thuộc Stream, phải thiết kế vòng đời khác để tài nguyên còn hợp lệ cho đến khi công việc hoàn tất. Đừng giả định callback trả Future là mọi thao tác đọc đã kết thúc.

### 4.3. Mẫu C: chuyển quyền sở hữu một cách tường minh

`openLines(path)` như ở phần 3 phù hợp khi caller cần xử lý lazy ở nhiều bước, nhưng phải được tài liệu hóa và kiểm soát điểm đóng. Trường hợp chỉ cần số lượng, tập hợp hoặc kết quả thống kê, **mẫu A hoặc B thường ít rủi ro hơn**.

| Kiểu API | Ai đóng? | Ưu điểm | Rủi ro/đánh đổi |
|---|---|---|---|
| Trả `List` / `Map` / số liệu | Phương thức nguồn | Dễ sử dụng, không lộ handle | Có thể tốn RAM nếu materialize nhiều dữ liệu |
| `withLines(path, operation)` | Phương thức nguồn | Có thể xử lý streaming, quyền sở hữu rõ | Callback không được để dữ liệu lazy thoát ra |
| `openLines(path)` trả Stream | Caller | Cho phép ghép pipeline ở ngoài | Dễ rò rỉ nếu caller quên đóng |
| Trả `Supplier<Stream<T>>` | Caller của mỗi lần `get()` | Có thể hoãn thời điểm mở I/O | Mỗi lần gọi phải tạo và đóng Stream riêng; không giảm trách nhiệm đóng |

`Supplier<Stream<T>>` chỉ diễn đạt “cách mở mới” chứ không biến Stream thành tài nguyên tự đóng. Nếu chọn cách này, cần tài liệu hóa cách dùng `try (Stream<T> s = supplier.get()) { ... }`.

## 5. Nối hai nguồn: Stream.concat không thay bạn quyết định vòng đời

`Stream.concat(first, second)` tạo một Stream **lazy concatenation**: các phần tử của `first` rồi đến các phần tử của `second` (khi cả hai có encounter order). Theo hợp đồng Java, **khi Stream kết hợp được đóng, các close handler của cả hai Stream đầu vào cũng được gọi**.

Nhưng `concat` **không tự đóng vì đã chạy xong `count()`, `findFirst()` hoặc `forEach()`**. Và nếu bạn đã gọi `Files.lines` để mở cả hai đầu vào, file thứ hai có thể đang mở **ngay cả khi xử lý dừng trong file thứ nhất**.

### 5.1. Mẫu sai: mở hai nguồn, ghép rồi quên đóng

```java
// SAI: cả hai Stream nguồn có thể giữ file handle sau terminal operation.
long total = Stream.concat(
        Files.lines(firstPath),
        Files.lines(secondPath))
        .filter(line -> line.startsWith("ERROR"))
        .count();
```

Ngoài rò rỉ do không đóng, còn một lỗi tinh vi: nếu mở `firstPath` thành công nhưng mở `secondPath` **ném `IOException`**, Stream thứ nhất đã mở có thể không được đóng vì lời gọi `Stream.concat(...)` chưa kịp tạo ra kết quả để quản lý.

### 5.2. Mẫu đúng: khai báo hai nguồn trong cùng try-with-resources

```java
public static long countErrorsInTwoFiles(
        Path firstPath, Path secondPath) throws IOException {
    try (Stream<String> first =
                 Files.lines(firstPath, StandardCharsets.UTF_8);
         Stream<String> second =
                 Files.lines(secondPath, StandardCharsets.UTF_8);
         Stream<String> combined = Stream.concat(first, second)) {

        return combined
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

Lợi ích:

- Nếu mở file thứ hai thất bại, `try-with-resources` đóng file thứ nhất đã mở thành công.
- Khi xử lý xong hoặc có ngoại lệ, các resource được đóng **theo thứ tự ngược với lúc khai báo**.
- Đóng `combined` gọi đóng các nguồn; sau đó `try-with-resources` cũng đóng `second` và `first`. `Stream.close()` không xử lý lại các close handler đã chạy trong lần đóng trước, nên cách bảo vệ nhiều tầng này an toàn và làm rõ quyền sở hữu khi xảy ra lỗi lúc mở.
- Nếu muốn chỉ mở hai nguồn rồi xử lý trong cùng scope, có thể giữ `first` và `second` trong `try` và không khai báo thêm `combined` làm resource riêng; vẫn phải bảo đảm cả hai được đóng.

**Không nên dựa vào thứ tự đóng Stream như một thứ tự nghiệp vụ.** Đóng tài nguyên là công việc dọn dẹp, không phải cam kết thứ tự thực thi các thao tác `filter` hoặc `map`.

### 5.3. Short-circuit vẫn phải đóng cả hai

```java
public static Optional<String> firstErrorFromTwoFiles(
        Path firstPath, Path secondPath) throws IOException {
    try (Stream<String> first = Files.lines(firstPath);
         Stream<String> second = Files.lines(secondPath);
         Stream<String> combined = Stream.concat(first, second)) {

        return combined
                .filter(line -> line.startsWith("ERROR"))
                .findFirst();
    }
}
```

Nếu phần tử lỗi đầu tiên nằm ngay trong file thứ nhất, `findFirst` có thể kết thúc sớm mà không cần đọc nội dung file thứ hai. **File thứ hai vẫn có thể đã mở** vì `Files.lines(secondPath)` được gọi lúc thiết lập pipeline. `try-with-resources` giải phóng cả hai bất kể file nào đã được đọc.

## 6. Ví dụ Java 8 hoàn chỉnh: tạo hai file tạm, nối nguồn và dọn dẹp

Chương trình dưới đây tạo hai file tạm để có dữ liệu tự kiểm chứng, đếm dòng bắt đầu bằng `ERROR`, tìm dòng lỗi đầu tiên, rồi xóa các file tạm trong `finally`. Ví dụ chỉ dùng Java 8+ và không cần thư viện bên ngoài.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Optional;
import java.util.stream.Stream;

public class MultiFileResourceDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;

    static long countErrors(Path a, Path b) throws IOException {
        try (Stream<String> first = Files.lines(a, UTF8);
             Stream<String> second = Files.lines(b, UTF8);
             Stream<String> joined = Stream.concat(first, second)) {

            return joined
                    .filter(line -> line.startsWith("ERROR"))
                    .count();
        }
    }

    static Optional<String> firstError(Path a, Path b)
            throws IOException {
        try (Stream<String> first = Files.lines(a, UTF8);
             Stream<String> second = Files.lines(b, UTF8);
             Stream<String> joined = Stream.concat(first, second)) {

            return joined
                    .filter(line -> line.startsWith("ERROR"))
                    .findFirst();
        }
    }

    public static void main(String[] args) throws IOException {
        Path a = Files.createTempFile("stream-logs-a-", ".txt");
        try {
            Path b = Files.createTempFile("stream-logs-b-", ".txt");
            try {
                Files.write(a,
                        Arrays.asList("INFO begin", "ERROR first"),
                        UTF8);
                Files.write(b,
                        Arrays.asList("ERROR second", "INFO end"),
                        UTF8);

                System.out.println(countErrors(a, b)); // 2
                System.out.println(
                        firstError(a, b).orElse("(không có)"));
                // ERROR first
            } finally {
                Files.deleteIfExists(b);
            }
        } finally {
            Files.deleteIfExists(a);
        }
    }
}
```

Điểm cần phân tích:

1. `Files.lines` mở **nguồn mới** mỗi khi gọi `countErrors` hoặc `firstError`. Không thể dùng lại một Stream đã tiêu thụ.
2. `Stream.concat` bảo toàn thứ tự file A rồi B nếu cả hai là Stream có thứ tự. Vì vậy `findFirst` chọn `ERROR first`.
3. Hai nguồn đầu vào và Stream ghép đều được quản lý trong `try-with-resources`; việc dừng sớm không làm bỏ qua bước đóng.
4. Cả hai file tạm được xóa ở các `finally` riêng, kể cả nếu bước ghi/đọc thất bại sau khi tạo file.
5. Nếu một thao tác đọc trong khi duyệt thất bại, runtime có thể ném `UncheckedIOException`; khối `try-with-resources` vẫn đóng tài nguyên trong quá trình unwind. Lỗi có thể được chuyển tiếp, chứ không bị coi là kết quả trống.

**Chú ý:** việc tạo *file tạm* trong ví dụ nhằm tự chuẩn bị dữ liệu kiểm thử; trong ứng dụng thực tế, các path thường đến từ cấu hình hoặc tham số. Không mở/ghi file tạm chỉ để dùng `Stream.concat` khi đã có dữ liệu trong bộ nhớ.

## 7. Nối nhiều file: tránh mở tất cả cùng lúc

Với hai file, `Stream.concat` đơn giản. Nhưng nếu có hàng trăm hoặc hàng nghìn file, cách “mở tất cả `Files.lines` rồi concat” có thể **giữ quá nhiều file descriptor đang mở**, kể cả các nguồn chưa tới lượt đọc.

Thay vào đó, có thể lấy một Stream đường dẫn và `flatMap` từng path sang Stream các dòng:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countErrorsInDirectory(Path directory)
        throws IOException {
    try (Stream<Path> paths = Files.list(directory)) {
        return paths
                .filter(path -> path.getFileName()
                        .toString().endsWith(".log"))
                .filter(Files::isRegularFile)
                .flatMap(path -> {
                    try {
                        return Files.lines(path, StandardCharsets.UTF_8);
                    } catch (IOException e) {
                        throw new UncheckedIOException(
                                "Không mở được file: " + path, e);
                    }
                })
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

Trong pipeline **tuần tự** này:

- `Files.list(directory)` là nguồn I/O ngoài cùng và được đóng bằng `try-with-resources`.
- `flatMap` mở Stream dòng cho từng path khi đến lượt xử lý. Theo hợp đồng `Stream.flatMap`, các Stream con do mapper tạo ra được đóng sau khi nội dung của chúng được đưa vào luồng kết quả.
- Không cần tích lũy toàn bộ nội dung file thành một `List` chỉ để đếm dòng lỗi.
- `IOException` khi **mở file** bên trong lambda phải được chuyển sang một ngoại lệ không kiểm tra như `UncheckedIOException`, vì `Function<T, Stream<R>>` không khai báo `throws IOException`.
- Lỗi đọc phát sinh **trong lúc duyệt** `Files.lines` cũng có thể xuất hiện dưới dạng `UncheckedIOException`. Không nên nuốt lỗi và xem một file không đọc được như file rỗng, trừ khi đó là chính sách nghiệp vụ được công bố.

**Không tùy tiện thêm `parallel()`** vào ví dụ trên nếu mục tiêu là giới hạn số file mở đồng thời. Một pipeline song song có thể gọi mapper trên nhiều path cùng lúc, làm tăng số luồng file đang mở và gây tranh chấp I/O. Nếu thực sự cần song song, hãy giới hạn mức đồng thời, đo hiệu năng và kiểm soát số handle theo tải thực tế.

### 7.1. Thứ tự xử lý của Files.list không được bảo đảm

`Files.list(directory)` không cam kết thứ tự các entry. Nếu muốn ghép các file theo tên rồi chọn **dòng lỗi đầu tiên**, cần đặt quy tắc thứ tự, ví dụ:

```java
try (Stream<Path> paths = Files.list(directory)) {
    Optional<String> firstError = paths
            .filter(path -> path.getFileName().toString().endsWith(".log"))
            .filter(Files::isRegularFile)
            .sorted()
            .flatMap(path -> {
                try {
                    return Files.lines(path, StandardCharsets.UTF_8);
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            })
            .filter(line -> line.startsWith("ERROR"))
            .findFirst();
}
```

`sorted()` áp dụng thứ tự tự nhiên của `Path`, là thứ tự đường dẫn theo provider; nếu nghiệp vụ cần thứ tự riêng, hãy truyền `Comparator<Path>` thích hợp. Việc sắp xếp có chi phí về thời gian/bộ nhớ theo số path. `findFirst` trên nguồn đã được sắp xếp có ý nghĩa “đầu tiên theo thứ tự file đã chọn”, không phải “dòng lỗi xuất hiện sớm nhất về thời gian” trừ khi thứ tự file và nội dung phản ánh điều đó.

### 7.2. Không nối hàng nghìn Stream bằng các concat lồng sâu

Một chuỗi rất sâu của `Stream.concat(Stream.concat(...), ...)` có thể tạo cây concat sâu, gây chi phí và trong trường hợp cực đoan có nguy cơ `StackOverflowError` khi duyệt hoặc đóng. Với danh sách nhiều nguồn, mô hình “Stream các path → `flatMap` thành Stream dòng” hoặc một thiết kế đọc tuần tự có giới hạn thường dễ quản lý tài nguyên hơn.

## 8. Những nguồn liên quan nhưng có hợp đồng đóng khác nhau

### 8.1. BufferedReader.lines không tự quyết định quyền sở hữu BufferedReader

Nếu bạn tự mở `BufferedReader`, hãy đóng **reader** bằng `try-with-resources`. Đừng giả định chỉ gọi `close()` trên một Stream lấy từ `reader.lines()` là đã đóng mọi tài nguyên của reader theo cách `Files.lines` quản lý:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static long countNonEmpty(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> !line.trim().isEmpty())
                .count();
    }
}
```

Ở đây, người sở hữu tài nguyên I/O là `BufferedReader`. Stream được dùng trong phạm vi reader còn mở; rời `try` thì reader được đóng. Các ngoại lệ đọc phát sinh khi duyệt Stream có thể được đóng gói thành `UncheckedIOException`.

### 8.2. Files.walk và Files.find cũng cần try-with-resources

`Files.walk` và `Files.find` có thể nắm giữ các tài nguyên duyệt thư mục. Ví dụ:

```java
public static long countJavaFiles(Path root) throws IOException {
    try (Stream<Path> paths = Files.walk(root)) {
        return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .count();
    }
}
```

Đoạn code này không tự giới hạn độ sâu hay số file. Trên cây thư mục lớn, cần cân nhắc giới hạn độ sâu, xử lý symbolic link và quyền truy cập. Việc duyệt có thể phát sinh lỗi khi chương trình đang chạy, không chỉ ở lúc gọi `Files.walk`.

### 8.3. Files.readAllLines không phải phương án tốt cho mọi file

`Files.readAllLines(path)` đọc toàn bộ nội dung vào danh sách và không trả Stream đang giữ file mở cho caller. Điều này có thể đơn giản hóa vòng đời tài nguyên với file nhỏ, nhưng phải đổi lấy **bộ nhớ tỷ lệ theo kích thước dữ liệu**. Với file lớn, nên đọc theo Stream trong `try-with-resources` và tổng hợp từng phần thay vì tải toàn bộ.

## 9. Ngoại lệ trong lúc xử lý và đóng

Tài nguyên có thể gặp lỗi ở ba giai đoạn khác nhau:

| Giai đoạn | Ví dụ | Cách xử lý |
|---|---|---|
| **Mở nguồn** | `Files.lines(path)` ném `IOException` | Để `try-with-resources` đóng các nguồn trước đó đã mở thành công |
| **Đọc trong pipeline** | Lỗi I/O sau vài dòng, có thể là `UncheckedIOException` | Không bỏ qua lỗi vô tình; tài nguyên vẫn phải được đóng |
| **Đóng nguồn** | Close handler hoặc thao tác giải phóng tài nguyên gặp lỗi | Ghi nhận/lan truyền lỗi thích hợp; không làm mất thông tin lỗi chính |

Ví dụ xử lý và chuyển lỗi ở ranh giới ứng dụng:

```java
public static long countOrReport(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> line.startsWith("ERROR")).count();
    } catch (UncheckedIOException e) {
        // Có thể phát sinh khi đọc trong lúc terminal operation duyệt.
        throw e.getCause();
    }
}
```

Các import tương ứng là `java.io.IOException`, `java.io.UncheckedIOException`, `java.nio.file.Files`, `java.nio.file.Path` và `java.util.stream.Stream`. Cách xử lý ngoại lệ phải phù hợp với hợp đồng phương thức; không nên trả `0` hoặc `Optional.empty()` khi đọc file thất bại trừ khi nghiệp vụ cố ý coi lỗi I/O là thiếu dữ liệu.

### 9.1. Đóng ở đúng phạm vi cả khi findFirst hoặc limit dừng sớm

`limit`, `findFirst` và `anyMatch` có thể khiến pipeline dừng trước khi đọc hết file. Điều đó giúp tiết kiệm xử lý, nhưng **không thay thế việc đóng**. `try-with-resources` là ranh giới rõ ràng bảo đảm việc giải phóng nguồn kể cả khi pipeline bị dừng sớm hoặc ngoại lệ.

## 10. Thiết kế API, hiệu năng và xử lý song song

Việc giữ nguồn mở có thể gây cạn *file descriptor*, khiến xóa/đổi tên file bị cản trở trên một số hệ điều hành và làm tải hệ thống tăng khó dự đoán. Với các nguồn trong bộ nhớ, `parallelStream()` có thể thích hợp khi công việc CPU đủ lớn; nhưng với nhiều file I/O nhỏ, song song không tự động nhanh hơn vì chi phí mở/đóng, giới hạn thiết bị và tranh chấp tài nguyên.

Một số nguyên tắc:

1. **Xác định chủ sở hữu** ngay tại API tạo nguồn I/O. Nếu trả Stream thì phía gọi phải đóng; nếu không cần streaming ra ngoài, ưu tiên trả kết quả đã tính hoặc dùng callback.
2. **Giữ phạm vi mở ngắn và rõ ràng**. Thực thi pipeline trong `try-with-resources`, không lưu Stream mở trong singleton hoặc cache.
3. **Đừng tự động mở tất cả nguồn** khi chỉ cần dữ liệu của một vài file. Khi số file lớn, ưu tiên cách mở theo nhu cầu và đóng từng Stream con.
4. **Đừng gọi `parallel()` để chữa bottleneck I/O** nếu chưa đo. Nhiều worker có thể mở nhiều file đồng thời, vượt giới hạn handle.
5. **Kiểm soát số lượng kết quả**. `collect(toList())` sẽ giữ toàn bộ dữ liệu đã lọc, có thể gây áp lực RAM ngay cả khi file được đóng đúng cách; `count`, `sum` hoặc collector thống kê có thể cần ít bộ nhớ hơn.
6. **Phân biệt thứ tự file với thứ tự dòng**. `Stream.concat` trên hai nguồn có thứ tự diễn đạt “file A rồi file B”; `Files.list` không cam kết một thứ tự file nghiệp vụ.
7. **Không tạo tác dụng phụ khó kiểm soát** trong `filter`, `map` hoặc close handler. Các bước Stream có thể bị tối ưu hoặc chạy song song; các phép xử lý I/O phải được thiết kế dựa trên hợp đồng đã công bố.

## 11. Các lỗi thường gặp

| Cách làm | Vấn đề | Giải pháp |
|---|---|---|
| Trả `Files.lines(path)` mà không ghi rõ ai đóng | Caller dễ quên, giữ file mở | Tài liệu hóa caller ownership hoặc chuyển sang callback/kết quả đã tính |
| `return lines.filter(...)` bên trong `try (lines)` | Stream trả ra đã bị đóng | Tiêu thụ bên trong scope hoặc trả Stream có trách nhiệm đóng rõ ràng |
| `Files.lines(path).count()` không bọc `try` | Terminal không tự đóng | Dùng `try-with-resources` |
| `Stream.concat(Files.lines(a), Files.lines(b))` trực tiếp | Có thể rò rỉ khi nguồn thứ hai mở lỗi | Khai báo từng nguồn trong `try-with-resources` trước khi concat |
| `findFirst` rồi không đóng | Short-circuit không đồng nghĩa close | Đóng cả hai nguồn bằng `try-with-resources` |
| Mở hàng nghìn file trước khi nối | Cạn file descriptor | Mở theo nhu cầu, dùng Stream<Path> và `flatMap` |
| Dùng `flatMap` song song không giới hạn | Nhiều file đang mở cùng lúc | Giới hạn mức đồng thời hoặc xử lý tuần tự |
| Cho rằng `onClose` tự chạy sau `count` | Handler chưa chắc được gọi | Gọi `close` hoặc dùng `try-with-resources` |
| Dùng lại Stream sau terminal | `IllegalStateException` | Tạo nguồn Stream mới cho lần xử lý kế tiếp |
| Duyệt `Files.list` rồi dựa vào thứ tự file bất kỳ | Kết quả `findFirst` không ổn định theo nghiệp vụ | `sorted`/Comparator trước khi đọc |
| Dùng `Files.readAllLines` cho file rất lớn | Tăng chi phí bộ nhớ | Tổng hợp theo Stream trong scope có đóng |
| Bắt mọi `UncheckedIOException` rồi trả kết quả rỗng | Che giấu lỗi I/O | Báo lỗi hoặc áp dụng chính sách fallback có chủ đích |

## 12. Bài tập tự kiểm tra

### Bài 1. Stream bị đóng quá sớm

```java
Stream<String> getLines(Path path) throws IOException {
    try (Stream<String> s = Files.lines(path)) {
        return s.filter(line -> line.startsWith("A"));
    }
}
```

**Câu hỏi:** Vì sao phương thức sai?

**Đáp án:** Trước khi caller nhận kết quả, khối `try-with-resources` đã đóng `s`; pipeline trả về không còn hợp lệ để duyệt. Hãy tiêu thụ trong scope rồi trả dữ liệu đã tính, dùng callback hoặc trả nguồn mở với hợp đồng caller phải đóng.

### Bài 2. Dừng sớm có thay thế close không?

```java
Optional<String> value = Files.lines(path)
        .filter(line -> line.startsWith("ERROR"))
        .findFirst();
```

**Đáp án:** Không. `findFirst` có thể dừng sớm nhưng không chịu trách nhiệm đóng file. Bọc nguồn `Files.lines` trong `try-with-resources`.

### Bài 3. Mở hai file trước khi concat

Nếu `Files.lines(a)` thành công nhưng `Files.lines(b)` ném `IOException` trong biểu thức `Stream.concat(Files.lines(a), Files.lines(b))`, chuyện gì có thể xảy ra?

**Đáp án:** File A đã mở nhưng không có scope đóng bảo vệ, nên có nguy cơ rò rỉ. Mở A và B bằng các khai báo tài nguyên liên tiếp trong cùng `try-with-resources`; nếu B lỗi, Java tự đóng A.

### Bài 4. Nhiều file và giới hạn handle

Cho danh sách 10.000 file log. Nên mở tất cả `Files.lines` rồi ghép, hay lấy Stream<Path> và `flatMap` mở từng file khi cần?

**Đáp án:** Với mục tiêu xử lý tuần tự và hạn chế file đang mở, nên mở theo nhu cầu bằng Stream<Path> và `flatMap`, đồng thời đóng Stream ngoài cùng. Tránh bật song song không kiểm soát vì có thể tăng số nguồn mở đồng thời.

### Bài 5. Ai đóng BufferedReader?

`BufferedReader reader = Files.newBufferedReader(path)` rồi `reader.lines().count()`. Có thể dựa vào terminal operation hoặc chỉ Stream đóng reader không?

**Đáp án:** Không. Hãy quản lý `BufferedReader` trong `try-with-resources`; terminal operation không có hợp đồng tự đóng reader.

### Bài 6. Đọc hai nguồn, chỉ cần một kết quả

Hãy sửa đoạn mã sau để trả số dòng lỗi mà vẫn đóng tất cả nguồn:

```java
long total = Stream.concat(Files.lines(a), Files.lines(b))
        .filter(line -> line.startsWith("ERROR"))
        .count();
```

**Đáp án:**

```java
long total;
try (Stream<String> first = Files.lines(a);
     Stream<String> second = Files.lines(b);
     Stream<String> both = Stream.concat(first, second)) {
    total = both.filter(line -> line.startsWith("ERROR")).count();
}
```

Nếu nguồn thứ hai mở lỗi, nguồn thứ nhất vẫn được đóng; nếu tính toán thất bại, cả hai nguồn cũng được giải phóng.

## 13. Checklist trước khi trả về hoặc ghép Stream I/O

Trước khi hoàn thiện phương thức xử lý file hay thư mục, hãy tự hỏi:

1. **Nguồn nào đang mở file, kênh đọc, reader hay directory handle?**
2. **Ai là chủ sở hữu việc đóng?** Có `try-with-resources` hoặc hợp đồng caller-close rõ ràng chưa?
3. **Stream có bị trả về sau khi scope đóng đã kết thúc không?** Hay ngược lại, nó được trả về đang mở mà không ai biết phải đóng?
4. **Nếu mở nguồn thứ hai thất bại, nguồn thứ nhất có được đóng không?**
5. **Nếu terminal operation dừng sớm hoặc ném ngoại lệ, nguồn có vẫn được đóng không?**
6. **Nếu số nguồn rất lớn, có đang mở tất cả quá sớm không?** Mức đồng thời có giới hạn không?
7. **Nếu gọi `findFirst` trên nhiều file, thứ tự file có được quy định rõ chưa?**
8. **Nếu cần trả kết quả ra ngoài, có thể trả giá trị đã tính thay vì để lộ một Stream gắn tài nguyên không?**

**Ghi nhớ:** `Stream` là một mô hình xử lý phần tử; nó **không tự động thay thế quyền sở hữu tài nguyên I/O**. Khi dùng `Files.lines`, `Files.list`, `Files.walk` hoặc `Files.find`, hãy đặt điểm mở và điểm đóng trong một phạm vi dễ nhìn thấy. Với `Stream.concat`, bảo vệ từng nguồn ngay từ lúc mở để xử lý cả lỗi mở nguồn sau. Với nhiều file, cân nhắc `flatMap` để mở theo nhu cầu thay vì giữ hàng loạt handle. Tách rõ trách nhiệm **tiêu thụ dữ liệu**, **giải phóng tài nguyên** và **quản lý lỗi** là nền tảng cho pipeline Java Stream an toàn, đúng nghĩa và có thể vận hành lâu dài.
