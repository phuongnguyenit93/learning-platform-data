# Vòng đời tiêu thụ, đóng Stream và thiết kế hàm cung cấp Stream

Trong Java Stream API, một `Stream` biểu diễn **pipeline xử lý dữ liệu**, chứ không phải một tập dữ liệu có thể duyệt lại tùy ý. Mỗi pipeline được thiết kế để thực thi **một lần**. Nếu nguồn giữ tài nguyên như tệp hoặc thư mục, chương trình còn phải quản lý **thời điểm đóng tài nguyên**. Hai trách nhiệm này liên quan nhưng khác nhau: **tiêu thụ Stream** không đồng nghĩa với **đóng Stream**.

Bài học thuộc chương **Hợp đồng và vòng đời pipeline**, tập trung vào cách dùng Stream an toàn trong xử lý khai báo: biết khi nào pipeline đã dùng xong, xác định ai sở hữu tài nguyên và thiết kế API trả về Stream sao cho người gọi biết phải làm gì. Những nguyên tắc này vẫn áp dụng khi pipeline kết hợp `filter`, `map`, `reduce`, `collect`, chạy song song hoặc có thao tác ngắn mạch.

## 1. Pipeline có một vòng đời sử dụng duy nhất

Pipeline thông thường gồm **nguồn** (source), **không hoặc nhiều thao tác trung gian** (intermediate operations) và **thao tác kết thúc** (terminal operation):

```text
Nguồn → filter(...) → map(...) → limit(...) → collect(...)
         trung gian    trung gian    trung gian    kết thúc
```

- **Nguồn** tạo Stream từ mảng, collection, dãy số, tệp hoặc nguồn tùy biến.
- **Thao tác trung gian** như `filter`, `map`, `sorted`, `limit` thường *lazy*: khai báo cách xử lý, chưa bắt đầu duyệt phần tử ngay khi được gắn vào pipeline.
- **Thao tác kết thúc** như `count`, `findFirst`, `forEach`, `reduce` hoặc `collect` kích hoạt quá trình xử lý nếu cần và kết thúc quyền sử dụng pipeline đó. Một số thao tác ngắn mạch có thể dừng trước khi duyệt hết nguồn.
- **Đóng Stream** qua `close()` hoặc `try-with-resources` đánh dấu Stream đã đóng và thực hiện các tác vụ dọn dẹp đã đăng ký (nếu có). Việc đóng tự nó không thực thi toàn bộ pipeline.

Các tình huống cần phân biệt:

| Thời điểm | Có được sử dụng lại cùng Stream? | Điều cần nhớ |
| --- | --- | --- |
| Mới tạo, chưa gắn thao tác | Có thể tiếp tục xây dựng **một** pipeline | Stream chỉ dùng cho một chuỗi xử lý |
| Đã gắn `filter`/`map` | Dùng Stream kết quả để xây dựng tiếp | Không tách nhiều nhánh từ cùng một Stream nguồn |
| Đã gọi thao tác kết thúc | **Không** | Muốn tính lần hai, tạo Stream mới |
| Đã gọi `iterator()` hoặc `spliterator()` | **Không** dùng lại pipeline | Đây là cách lấy đối tượng duyệt và cũng làm pipeline bị ràng buộc để tiêu thụ |
| Đã gọi `close()` | **Không** | Không tiếp tục duyệt hoặc gắn thao tác mới |

Ví dụ tái sử dụng sai:

```java
import java.util.stream.Stream;

Stream<String> names = Stream.of("An", "Binh", "Chi");
long total = names.count();       // Lần sử dụng duy nhất: 3
long again = names.count();       // Thường ném IllegalStateException
```

Java có thể phát hiện và ném lỗi `IllegalStateException: stream has already been operated upon or closed`. Tuy nhiên, hợp đồng API yêu cầu **không sử dụng lại Stream**; không được phụ thuộc vào việc mọi kiểu triển khai đều phát hiện mọi trường hợp dùng sai.

Muốn thực hiện nhiều phép phân tích độc lập trên cùng collection, gọi `stream()` cho từng phép:

```java
import java.util.List;

List<String> names = List.of("An", "Binh", "Chi");

long total = names.stream().count();
long longNames = names.stream()
        .filter(name -> name.length() >= 4)
        .count();
```

`names` là collection còn tồn tại sau mỗi lần tính; hai lời gọi `names.stream()` tạo **hai pipeline khác nhau**. Ngược lại, nếu dữ liệu được đọc từ một nguồn chỉ đi qua một lần, việc tạo pipeline mới có thể đòi hỏi mở lại nguồn hoặc thiết kế một bộ đệm riêng.

## 2. Tiêu thụ và đóng là hai sự kiện khác nhau

`Stream` kế thừa `BaseStream`, triển khai `AutoCloseable` nên dùng được với `try-with-resources`. Nhưng **thao tác kết thúc không tự động gọi `close()`**. Đây là khác biệt quan trọng nhất khi Stream liên kết với tài nguyên bên ngoài.

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

AtomicBoolean closed = new AtomicBoolean(false);
Stream<Integer> numbers = Stream.of(1, 2, 3)
        .onClose(() -> closed.set(true));

System.out.println(numbers.count());   // 3
System.out.println(closed.get());      // false: count() không đóng Stream

numbers.close();
System.out.println(closed.get());      // true: close() chạy onClose
```

`onClose` đăng ký hành động chạy **khi đóng Stream**, không phải khi gặp thao tác kết thúc. Có thể đăng ký nhiều handler; chúng chạy theo thứ tự đăng ký, và Java vẫn cố thực hiện các handler còn lại nếu một handler ném ngoại lệ. `close()` nhiều lần không có nghĩa handler phải chạy nhiều lần.

Một sơ đồ tư duy hữu ích:

```text
Tạo Stream ──► Xây pipeline ──► Terminal operation ──► Đã tiêu thụ
     │                │                   │                  │
     └────────────────┴───────────────────┴──────────────────┘
                              close()
                                 │
                                 ▼
                         Đã đóng / dọn dẹp
```

Có thể đóng Stream **trước** khi gọi terminal operation hoặc **sau** khi terminal operation đã xong. Đóng sớm khiến pipeline không còn sử dụng được; đóng sau giúp giải phóng tài nguyên. Với Stream thuần từ collection hay mảng, thông thường không có tài nguyên bắt buộc phải đóng; với nguồn I/O, việc đóng là trách nhiệm thực sự.

Cũng cần nhớ: `findFirst()`, `anyMatch()`, `limit()` và các phép ngắn mạch có thể không duyệt hết nguồn. Dừng duyệt sớm **không** giải phóng tệp hay thư mục đã mở. Tương tự, pipeline ném ngoại lệ giữa chừng vẫn cần được đóng.

## 3. Đóng Stream giữ tài nguyên bằng try-with-resources

Các phương thức như `Files.lines(...)`, `Files.list(...)`, `Files.walk(...)` và `Files.find(...)` trả về Stream gắn với tài nguyên I/O. Tài nguyên đó cần được đóng khi không dùng nữa. Mẫu thông dụng là mở và xử lý trong cùng một khối `try-with-resources`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countWarnings(Path logFile) throws IOException {
    try (Stream<String> lines =
                 Files.lines(logFile, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.contains("WARN"))
                .count();
    }
}
```

Ở đây:

1. `Files.lines(...)` mở nguồn phục vụ đọc tệp và trả về Stream đọc dòng theo nhu cầu.
2. `filter(...)` mô tả điều kiện; `count()` kích hoạt xử lý.
3. Khi thoát khỏi khối `try`, kể cả lúc xảy ra ngoại lệ, Java gọi `lines.close()` để giải phóng tài nguyên của nguồn.

Dùng thao tác ngắn mạch cũng cần đóng:

```java
public static boolean hasFailure(Path logFile) throws IOException {
    try (Stream<String> lines = Files.lines(logFile)) {
        return lines.anyMatch(line -> line.contains("ERROR"));
    }
}
```

Nếu thấy `ERROR` ở dòng đầu, `anyMatch` có thể dừng ngay, nhưng Stream vẫn đóng ở cuối khối `try`.

**Ngoại lệ I/O có thể xảy ra vào hai thời điểm.** Lúc mở `Files.lines`, lỗi có thể được báo bằng `IOException`; trong lúc duyệt lười, lỗi đọc tệp có thể được bọc thành `UncheckedIOException`. `try-with-resources` vẫn chạy thao tác đóng khi thoát khối. Nếu cả xử lý lẫn đóng đều ném ngoại lệ, cơ chế `try-with-resources` giữ ngoại lệ chính và lưu ngoại lệ khi đóng dưới dạng *suppressed exception*.

### Trường hợp BufferedReader.lines()

Không phải cứ gọi `close()` trên một Stream bất kỳ thì nguồn bên ngoài tự động được đóng. Với `BufferedReader.lines()`, cần quản lý **chính `BufferedReader`**:

```java
public static long countNonEmptyLines(Path file) throws IOException {
    try (var reader =
                 Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> !line.isBlank())
                .count();
    }
}
```

Quy tắc tổng quát: tìm hiểu hợp đồng đóng của **nguồn tạo ra Stream**. Stream từ `Files.lines` có cơ chế đóng tệp đi kèm; Stream sinh ra từ một đối tượng đang sở hữu tài nguyên (như `BufferedReader` hoặc con trỏ truy vấn cơ sở dữ liệu) có thể cần đóng đối tượng chủ sở hữu một cách riêng biệt hoặc gắn hành động dọn dẹp bằng `onClose`.

## 4. Thiết kế hàm cung cấp Stream: ai chịu trách nhiệm đóng?

Khi viết API, điểm quyết định là: **phương thức xử lý xong dữ liệu bên trong, hay trả pipeline ra ngoài để người gọi xử lý?** Cách viết quyết định thời gian sống của tài nguyên.

| Thiết kế API | Ai đóng tài nguyên? | Phù hợp khi |
| --- | --- | --- |
| `long countWarnings(Path)`, `List<T> load(Path)` | Phương thức triển khai | Giao diện đơn giản, trả kết quả đã tính |
| `Stream<String> openLines(Path)` | **Người gọi** | Cần cho người gọi tự chọn `filter`/`map`/`collect` |
| `<R> R withLines(Path, Function<Stream<String>, R>)` | Phương thức triển khai | Muốn tùy biến xử lý nhưng giới hạn thời gian sống của Stream |
| `Supplier<Stream<T>>` hoặc factory tạo Stream | Mỗi bên sử dụng phải quản lý Stream được tạo | Cần **pipeline mới** cho mỗi lần sử dụng |

### Cách A: Hoàn tất pipeline và trả kết quả

```java
import java.util.List;

public static List<String> loadWarnings(Path file) throws IOException {
    try (Stream<String> lines =
                 Files.lines(file, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.contains("WARN"))
                .toList();
    }
}
```

Dữ liệu được materialize thành `List` trước khi đóng tệp; người gọi nhận kết quả độc lập với vòng đời Stream. `Stream.toList()` có từ **Java 16**; trên Java 8–15 có thể dùng `collect(Collectors.toList())` (khác biệt về bảo đảm khả năng chỉnh sửa danh sách cần được xem xét khi lựa chọn).

Ưu điểm: ít rủi ro rò rỉ tài nguyên, API dễ sử dụng. Đổi lại, kết quả được giữ trong bộ nhớ; với tệp lớn, có thể nên trả kết quả gộp (`count`, `Map` thống kê...) thay vì toàn bộ dòng.

### Cách B: Trả Stream và chuyển trách nhiệm cho người gọi

```java
/**
 * Mở Stream đọc các dòng có WARN.
 * Người gọi PHẢI đóng Stream trả về bằng try-with-resources.
 */
public static Stream<String> openWarnings(Path file) throws IOException {
    return Files.lines(file, StandardCharsets.UTF_8)
            .filter(line -> line.contains("WARN"));
}

// Phía sử dụng:
try (Stream<String> warnings = openWarnings(logFile)) {
    warnings.limit(10).forEach(System.out::println);
}
```

Phương thức `openWarnings` mở tệp nhưng không đóng ngay, vì người gọi chưa dùng xong pipeline. Việc `filter` tạo một Stream trung gian vẫn giữ cơ chế đóng của pipeline chứa nguồn. Người gọi đóng Stream trả về để giải phóng tài nguyên.

**Không được trả một Stream đã đóng từ trong `try-with-resources`:**

```java
// SAI: vừa return là khối try kết thúc và Stream bị đóng.
public static Stream<String> brokenOpen(Path file) throws IOException {
    try (Stream<String> lines = Files.lines(file)) {
        return lines.filter(line -> !line.isBlank());
    }
}
```

Vì pipeline lazy, người gọi chỉ bắt đầu duyệt sau khi phương thức trả về, lúc nguồn đã bị đóng. Lỗi thường xuất hiện khi người gọi chạy terminal operation. Cách sửa là dùng Cách A (trả kết quả đã tính) hoặc Cách B (trả Stream còn mở và mô tả rõ nghĩa vụ đóng).

Khi một API công khai trả về `Stream` giữ tài nguyên, tài liệu nên nêu rõ: **người gọi cần đóng**, khi nào nguồn được mở, ngoại lệ có thể phát sinh trong khi duyệt và liệu Stream chỉ đọc được một lần hay không. Bản thân kiểu `Stream<T>` không nói cho người dùng biết nó có giữ tài nguyên hay không.

### Cách C: Nhận callback, giữ quyền sở hữu tài nguyên trong phương thức

```java
import java.util.function.Function;

public static <R> R withLines(
        Path file,
        Function<? super Stream<String>, ? extends R> operation
) throws IOException {
    try (Stream<String> lines =
                 Files.lines(file, StandardCharsets.UTF_8)) {
        return operation.apply(lines);
    }
}

// Người dùng tùy biến pipeline nhưng xử lý xong trong phạm vi an toàn:
long errors = withLines(
        logFile,
        lines -> lines.filter(line -> line.contains("ERROR")).count()
);
```

Thiết kế này phù hợp nếu muốn linh hoạt mà vẫn chắc chắn đóng tài nguyên trước khi phương thức trả về. Hợp đồng callback phải yêu cầu **tiêu thụ Stream hoàn toàn trong callback**; không trả về chính Stream, `Iterator`, `Spliterator` hay một lambda giữ Stream để dùng về sau, vì khi đó nguồn đã bị đóng. Java generics không tự cấm callback trả về những đối tượng như vậy, nên cần ghi rõ hợp đồng và cân nhắc API chặt chẽ hơn khi cần.

### Cách D: Factory tạo Stream mới cho mỗi lần duyệt

Đôi khi cần chạy nhiều truy vấn trên cùng dữ liệu. Hãy cung cấp **cách tạo Stream mới**, không cung cấp một Stream để dùng đi dùng lại.

```java
import java.util.List;
import java.util.function.Supplier;
import java.util.stream.Stream;

List<String> events = List.of("INFO start", "WARN slow", "ERROR failed");
Supplier<Stream<String>> newStream = events::stream;

long warnings = newStream.get()
        .filter(s -> s.startsWith("WARN"))
        .count();

long errors = newStream.get()
        .filter(s -> s.startsWith("ERROR"))
        .count();
```

Trái lại, `Supplier<Stream<String>> wrong = () -> existingStream;` chỉ trả lại **cùng một Stream**, không giải quyết được lỗi dùng lại.

Với nguồn tệp, việc mở mới có thể ném `IOException` (checked exception). `Supplier.get()` không khai báo ngoại lệ checked, nên có thể thiết kế interface chuyên biệt:

```java
@FunctionalInterface
interface IOStreamOpener<T> {
    Stream<T> open() throws IOException;
}

IOStreamOpener<String> opener =
        () -> Files.lines(logFile, StandardCharsets.UTF_8);

try (Stream<String> first = opener.open()) {
    System.out.println(first.count());
}
try (Stream<String> second = opener.open()) {
    System.out.println(second.findFirst().orElse("(trống)"));
}
```

**Mỗi lần mở là một Stream và một lần quản lý tài nguyên riêng.** Nhà cung cấp factory không hứa rằng nội dung tệp bất biến giữa hai lần đọc; kết quả có thể thay đổi khi nguồn thay đổi.

## 5. Các lỗi dễ gặp trong thực tế

| Mẫu sử dụng | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `stream.count(); stream.findFirst();` | Dùng lại pipeline đã tiêu thụ | Tạo Stream mới từ nguồn |
| `Stream<String> s = Files.lines(path); s.findFirst();` mà không đóng | Ngắn mạch vẫn giữ tài nguyên mở | Bọc Stream trong `try-with-resources` |
| `return stream.filter(...)` bên trong `try (stream)` | Người gọi nhận Stream đã đóng | Trả kết quả đã xử lý hoặc chuyển quyền đóng cho người gọi |
| Trả `BufferedReader.lines()` sau khi đã đóng reader | Pipeline đọc từ reader không còn dùng được | Giữ reader sống trong phạm vi xử lý hoặc định nghĩa API sở hữu tài nguyên thích hợp |
| `Supplier` luôn trả cùng biến `Stream` | Không tạo được pipeline mới | Để factory **tạo** Stream mỗi lần được gọi |
| Dựa vào GC để đóng Stream đọc tệp | Không có bảo đảm thời điểm giải phóng | Đóng tường minh, ưu tiên `try-with-resources` |
| Dùng `peek` để tự dọn tài nguyên | `peek` có thể không chạy cho mọi phần tử; một số thao tác có tối ưu hóa | Dùng `close` / `onClose` và khối quản lý nguồn |

Với `parallel()`, các quy tắc này vẫn giữ nguyên: Stream song song cũng chỉ tiêu thụ một lần, và phép kết thúc không bảo đảm tự đóng tài nguyên. Không dùng chung một instance Stream cho nhiều luồng cùng thao tác.

## 6. Ví dụ tổng hợp: thống kê mức log từ một tệp lớn

Giả sử tệp có các dòng ở dạng `INFO started`, `WARN delayed`, `ERROR failed`. Yêu cầu là đếm số dòng theo mức log, không tải toàn bộ nội dung vào bộ nhớ.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class LogStatistics {
    private LogStatistics() {}

    public static Map<String, Long> countByLevel(Path file)
            throws IOException {
        try (Stream<String> lines =
                     Files.lines(file, StandardCharsets.UTF_8)) {
            return lines
                    .map(String::strip)
                    .filter(line -> !line.isEmpty())
                    .map(line -> line.split("\\s+", 2)[0])
                    .collect(Collectors.groupingBy(
                            Function.identity(),
                            Collectors.counting()
                    ));
        }
    }
}
```

Pipeline duyệt nguồn theo nhu cầu; `collect` là thao tác kết thúc; kết quả chỉ giữ bộ đếm cho các mức log đã xuất hiện. Khi phương thức trả `Map<String, Long>`, Stream đã được đóng. Mẫu tách mức log ở đây giả định token đầu tiên là tên mức log; với định dạng log thực tế phức tạp hơn cần parser phù hợp.

Qua ví dụ có thể kiểm tra ba câu hỏi độc lập: **Ai tạo pipeline?** Phương thức `countByLevel`. **Khi nào pipeline được tiêu thụ?** Trong `collect`. **Ai đóng nguồn I/O?** Chính phương thức đó, thông qua `try-with-resources`.

## 7. Các câu hỏi tự kiểm tra

1. `count()` chạy thành công trên `Files.lines(...)` đã bảo đảm tệp được đóng chưa? **Chưa**; phải đóng Stream.
2. `findFirst()` chỉ lấy một phần tử thì có thể bỏ qua `close()` không? **Không**, nếu Stream sở hữu tài nguyên.
3. Đã gọi `close()` nhưng chưa có terminal operation, gọi `collect()` được không? **Không**; Stream đã đóng.
4. Một phương thức trả về `Stream<T>` từ tệp, ai cần dùng `try-with-resources`? **Người gọi**, nếu API chuyển quyền sở hữu và đã ghi rõ hợp đồng.
5. Muốn xử lý một collection ba lần, nên giữ một `Stream` hay gọi `collection.stream()` ba lần? **Tạo ba Stream độc lập**.
6. Trả `List<T>` từ trong `try-with-resources` có an toàn hơn trả `Stream<T>` không? **Có**, nếu dữ liệu đã được materialize đầy đủ trước khi đóng và dung lượng bộ nhớ phù hợp.

**Nguyên tắc áp dụng:** Hãy xem Stream như một phiên xử lý một lần. Thiết kế ranh giới phương thức để thời gian sống của Stream và tài nguyên nguồn rõ ràng: nếu xử lý trong phương thức, đóng trong phương thức; nếu trả Stream giữ tài nguyên ra ngoài, bắt buộc nêu trách nhiệm đóng của người gọi.
