# Files.lines với Charset — đọc tệp văn bản theo dòng an toàn trong Java 8+

`Files.lines(Path, Charset)` là phương thức hiện hành trong `java.nio.file.Files`, có từ Java 8, dùng để **đọc từng dòng của tệp qua `Stream<String>`** với quy tắc giải mã byte thành ký tự được chỉ định rõ. Nó đặc biệt hữu ích khi xử lý log, dữ liệu text, tập cấu hình đơn giản hoặc thống kê trên tệp mà không cần giữ mọi dòng trong một `List` ngay từ đầu.

Tuy nhiên, dùng đúng API này còn đòi hỏi hiểu **charset**, **đọc lười**, **đóng file handle**, **quy tắc kết thúc dòng**, **ngoại lệ xảy ra khi mở khác ngoại lệ xảy ra khi duyệt**, và **thứ tự/hiệu năng khi dùng parallel stream**. Một ví dụ đọc được trên máy cá nhân nhưng dựa vào mã hóa ngẫu nhiên, bỏ `close()` hoặc dùng terminal operation sai có thể gặp lỗi chỉ khi triển khai lên production.

Bài học chỉ sử dụng những kiến thức **vẫn được hỗ trợ hiện nay**. Phần cốt lõi tương thích Java 8; các API được bổ sung sau này sẽ ghi rõ phiên bản. Chương trình độc lập cuối bài đã được biên dịch và chạy trên JDK 17 với ví dụ UTF-8, Latin-1, CRLF/LF/CR, BOM, lỗi charset và kiểm tra giải phóng tài nguyên bằng `try-with-resources`.

## 1. Hợp đồng phương thức

Chữ ký:

~~~java
public static Stream<String> lines(Path path, Charset cs)
        throws IOException
~~~

Ý nghĩa:

- `Path path`: đường dẫn tới tệp được mở; thường tạo bằng `Paths.get(...)` trong Java 8. Đây là vị trí tệp, không phải dữ liệu tệp đã được nạp sẵn.
- `Charset cs`: cách giải mã **bytes trên đĩa thành ký tự Unicode**. Phổ biến là `StandardCharsets.UTF_8`. Nó **không** phải bộ lọc chữ hay định dạng ngày/đơn vị của nội dung.
- `Stream<String>`: các phần tử là **nội dung từng dòng**; những dấu xuống dòng được nhận biết sẽ không xuất hiện trong chuỗi kết quả.
- `IOException`: có thể xảy ra khi **mở** tệp; các lỗi đọc/giải mã/đóng **sau khi stream đã trả về** thường được bọc trong `UncheckedIOException`.

Các import cơ bản:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;
~~~

Mẫu sử dụng tối thiểu:

~~~java
Path path = Paths.get("data", "employees.txt");

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.filter(s -> !s.trim().isEmpty())
         .forEach(System.out::println);
}
~~~

Ví dụ trên chỉ chạy khi có tệp tương ứng. Nó cũng **có chủ đích lọc dòng trống và trim**; không phải mọi file đều nên xử lý như vậy. Nếu khoảng trắng ở đầu dòng có ý nghĩa, phải giữ chúng.

**Quan trọng nhất:** `Stream` từ `Files.lines` tham chiếu đến **file đang mở**. Phải đóng stream khi xong, ưu tiên `try-with-resources`. Việc gọi `count()` hoặc `collect(...)` không thay thế nghĩa vụ đóng; ngay cả `findFirst()` hoặc `limit(n)` dừng sớm vẫn cần đóng file.

## 2. Tại sao cần `Charset` tường minh?

Một tệp chỉ chứa byte. Muốn nhận chuỗi `"Tiếng Việt"` chính xác, chương trình phải biết những byte đó được tạo ra theo mã hóa nào. Nếu đọc sai:

1. Các byte không hợp lệ theo charset đã chọn có thể gây `MalformedInputException`/`UncheckedIOException`.
2. Một số dãy byte vẫn hợp lệ theo charset khác nhưng cho **ký tự sai**, thường gọi là *mojibake*; không phải lúc nào có exception.
3. Dữ liệu có dấu, dấu phân cách hoặc chữ Unicode có thể hỏng, gây sai bộ lọc/so sánh hoặc lỗi logic ở bước tiếp theo.

### 2.1. UTF-8 mặc định của riêng `Files.lines`

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
}
~~~

`StandardCharsets.UTF_8` là hằng số chuẩn có từ Java 7, luôn hiện diện trên các JDK. Với dữ liệu ứng dụng có quyền kiểm soát, UTF-8 thường là hợp đồng lưu trữ nên ưu tiên.

Điểm cần nhớ: **`Files.lines(Path)` không có tham số `Charset` vẫn dùng UTF-8** theo chính tài liệu Java:

~~~java
Files.lines(path);
// Tương đương Files.lines(path, StandardCharsets.UTF_8).
~~~

Không được khẳng định `Files.lines(path)` dùng `Charset.defaultCharset()` hoặc phụ thuộc mã hóa console. Tuy nhiên, vẫn nên truyền UTF-8 tường minh trong code mẫu khi muốn nhấn mạnh hợp đồng giữa bên ghi và bên đọc.

### 2.2. Đọc tệp Latin-1 phải dùng đúng Latin-1

~~~java
Path file = Paths.get("data", "legacy-latin1.txt");

try (Stream<String> lines =
        Files.lines(file, StandardCharsets.ISO_8859_1)) {
    lines.forEach(System.out::println);
}
~~~

Với `"café"` lưu dưới dạng Latin-1, byte cuối `0xE9` biểu diễn `é`. Byte `0xE9` đơn lẻ **không phải chuỗi UTF-8 hợp lệ**. Khi ép đọc như UTF-8, một terminal operation có thể ném `UncheckedIOException` với cause `MalformedInputException`.

**Không chọn ISO-8859-1 để “cứ có byte là đọc được”:** Latin-1 không biểu diễn đầy đủ chữ tiếng Việt; với nhiều dãy byte, đọc sai vẫn không báo lỗi, khiến dữ liệu âm thầm bị biến dạng.

### 2.3. Những charset có sẵn

| Hằng số | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode UTF-8 | Dữ liệu text đa ngôn ngữ hiện đại |
| `StandardCharsets.US_ASCII` | ASCII 7-bit | Nguồn chắc chắn chỉ có ASCII |
| `StandardCharsets.ISO_8859_1` | ISO Latin-1 | Nguồn legacy được xác nhận dùng Latin-1 |
| `StandardCharsets.UTF_16` | UTF-16 có quy tắc BOM và thứ tự byte | File có hợp đồng UTF-16 |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian | Nguồn quy định byte order LE |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian | Nguồn quy định byte order BE |

Nếu một hệ thống đối tác dùng một encoding tùy chọn như `windows-1252`, có thể dùng `Charset.forName("windows-1252")` khi runtime hỗ trợ; các charset không thuộc nhóm bắt buộc cần kiểm tra khả dụng. **Không đoán charset theo tên file `.txt`, locale máy chủ hoặc nội dung hiển thị trên console**.

### 2.4. Mã hóa khi ghi và giải mã khi đọc phải tương thích

~~~java
String value = "Táo, nho, cam\n";
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
Files.write(path, bytes);

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    String restored = lines.findFirst().orElse("");
    // "Táo, nho, cam".
}
~~~

Đoạn mã tạo tệp theo UTF-8 rồi đọc lại đúng charset, nhưng dòng cuối được trả về **không còn dấu `\n`**. `Files.lines` thích hợp đọc *dòng*, không dành để tái lập nguyên vẹn các byte hoặc kiểu xuống dòng ban đầu.

## 3. Đọc lười (lazy) khác đọc toàn bộ tệp

`Files.lines(path, cs)` **không** dựng trước một `List<String>` gồm mọi dòng. Nó trả stream và populates nội dung **khi stream được tiêu thụ**.

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long nonBlank = lines
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .count();
    System.out.println(nonBlank);
}
~~~

`map` và `filter` là intermediate operations; `count()` là terminal operation kích hoạt quá trình duyệt. Cách này có thể xử lý tệp rất nhiều dòng mà không giữ mọi dòng trong RAM.

Nhưng **lazy không đồng nghĩa luôn dùng bộ nhớ O(1)**. Có một dòng cực dài vẫn cần bộ nhớ cho String tương ứng. Các operation như `sorted`, `distinct`, `groupingBy` hoặc `collect(Collectors.toList())` có thể cần giữ rất nhiều dữ liệu. Khi mục đích chỉ là đếm hoặc tìm một phần tử, ưu tiên terminal thích hợp thay vì gom tất cả dòng.

Ví dụ tìm dòng đầu tiên có tiền tố:

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    Optional<String> firstError = lines
        .filter(s -> s.startsWith("ERROR:"))
        .findFirst();
}
~~~

`Optional<String>` cho biết có tìm thấy không; không nên thay ngay bằng `""` nếu chuỗi rỗng cũng là dữ liệu hợp lệ. Đoạn này yêu cầu thêm `import java.util.Optional;`.

### Stream chỉ có thể được tiêu thụ một lần

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
    // Không gọi lines.findFirst() ở đây: stream đã qua terminal.
}
~~~

Nếu cần hai phép phân tích độc lập, có thể **mở lại tệp** bằng lần gọi `Files.lines` mới, hoặc thu gọn thành **một pass** với accumulator/collector phù hợp. Không sửa file ở giữa rồi kỳ vọng hai lần đọc nhìn thấy một snapshot cố định.

### Dừng sớm không bỏ qua yêu cầu đóng file

`findFirst()`, `anyMatch(...)`, `limit(...)` có thể short-circuit để xử lý ít phần tử hơn. Nhưng pipeline có thể đọc trước/buffer một phần và `try-with-resources` vẫn cần bảo đảm close. Không dùng `Files.lines(...).findFirst()` rời rạc ở nơi có khả năng chạy thường xuyên, vì stream cần được đóng cả khi chỉ đọc một dòng.

## 4. Quy tắc tách dòng `CRLF`, `LF` và `CR`

Theo tài liệu, `Files.lines` nhận các dòng theo cùng bộ dấu kết thúc như `Files.readAllLines`:

| Dấu kết thúc | Chuỗi escape Java | Ký tự Unicode |
| --- | --- | --- |
| LF | `\n` | `U+000A` |
| CRLF | `\r\n` | `U+000D` rồi `U+000A` |
| CR | `\r` | `U+000D` |

Hai byte `\r\n` là **một terminator**, không chia ra thành hai dòng trống. Chuỗi trả về **không giữ** terminator.

Ví dụ:

~~~java
String text = "  táo  \r\ncam\n\nnho\r";
Files.write(path, text.getBytes(StandardCharsets.UTF_8));
~~~

Dữ liệu sẽ được đọc thành bốn dòng:

~~~text
[0] "  táo  "
[1] "cam"
[2] ""
[3] "nho"
~~~

Có dòng rỗng **thật sự** giữa `cam` và `nho` vì xuất hiện `\n\n`. Tệp kết thúc bằng terminator không có thêm một dòng rỗng ảo. Một dòng cuối không có terminator vẫn được trả về.

Đừng tùy tiện `trim` hoặc `filter` nếu indent, dòng rỗng hay khoảng trắng là dữ liệu có ý nghĩa. Và không được giả định các ký tự Unicode khác như `U+2028` hiện đều được `Files.lines` nhận diện như line terminator; tài liệu chỉ bảo đảm những trường hợp đã nêu, cho phép các phiên bản tương lai hỗ trợ thêm.

**Lưu ý về định dạng:** đối với CSV có trường được trích dẫn chứa newline, JSON nhiều dòng hay định dạng record có escaping phức tạp, **dòng vật lý không phải lúc nào là một record**. `Files.lines` chỉ cung cấp luồng dòng; phần parse theo định dạng phải dùng parser có hợp đồng riêng.

## 5. Đóng tài nguyên bằng `try-with-resources`

API được Javadoc nhấn mạnh **phải dùng trong try-with-resources hoặc cấu trúc tương đương** để tệp được đóng kịp thời.

~~~java
Path file = Paths.get("data", "records.log");

try (Stream<String> lines =
        Files.lines(file, StandardCharsets.UTF_8)) {
    lines.filter(s -> s.contains("WARN"))
         .limit(100)
         .forEach(System.out::println);
}
~~~

Sự cần thiết:

- `Files.lines` trả về stream có tham chiếu tới tệp đang mở.
- Kết thúc terminal operation **không** là hợp đồng tự gọi `close()`.
- Thoát sớm, exception, hoặc lỗi giải mã đều phải đi qua cơ chế cleanup.
- Trong try-with-resources, `close()` được gọi khi rời block; nếu lỗi xuất hiện lúc close, nó có thể được biểu diễn qua `UncheckedIOException`.

**Đừng lưu trữ hoặc trả một stream đang mở ra ngoài scope của try:**

~~~java
// SAI: stream được trả ra sau khi block đã đóng.
Stream<String> loadClosed(Path file) throws IOException {
    try (Stream<String> lines =
            Files.lines(file, StandardCharsets.UTF_8)) {
        return lines;
    }
}
~~~

Nếu cần trả dữ liệu cho caller, hoặc xử lý bên trong hàm, hoặc trả một container độc lập đã thu thập (khi kích thước phù hợp), hoặc thiết kế rõ ràng rằng caller sở hữu trách nhiệm close. Một API trả `Stream` gắn file handle đòi hỏi hợp đồng tài nguyên rõ; đơn giản nhất là xử lý và đóng ngay trong cùng method.

### Một method có thể tái sử dụng mà vẫn đóng đúng

~~~java
static long countMatchingLines(Path file, String token) throws IOException {
    try (Stream<String> lines =
            Files.lines(file, StandardCharsets.UTF_8)) {
        return lines.filter(s -> s.contains(token)).count();
    }
}
~~~

Đây là snippet method cần import `java.nio.file.*`, `java.nio.charset.StandardCharsets`, `java.util.stream.Stream` và `java.io.IOException`. Method có thể ném `IOException` khi mở, và lỗi trong lúc đọc có thể là `UncheckedIOException`. Không chỉ thêm `throws IOException` rồi tin mọi lỗi đều được compile-time checking.

## 6. Phân biệt lỗi mở tệp và lỗi khi tiêu thụ stream

Một trong những sai lầm phổ biến nhất là bắt mỗi `IOException` quanh `Files.lines` rồi nghĩ đã xử lý mọi lỗi.

**Khi mở**: `Files.lines(path, cs)` có thể ném `IOException` (ví dụ `NoSuchFileException`, `AccessDeniedException` tùy môi trường) trước khi trả stream. Không phải cứ tên tệp sai là luôn nhận đúng subclass giống nhau trên mọi filesystem provider.

**Sau khi đã trả stream**: I/O failure khi đọc, byte sai mã hóa hoặc lỗi đóng file được bọc trong `UncheckedIOException`, thường phát sinh ở terminal operation kích hoạt đọc hoặc trong quá trình đóng.

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
} catch (IOException openError) {
    // Lỗi ở pha mở tệp, kiểm tra path/quyền và error policy.
} catch (UncheckedIOException streamIoError) {
    // Lỗi đọc/giải mã/đóng khi stream đã mở.
    IOException cause = streamIoError.getCause();
    // Ghi nhận cause và áp dụng chính sách lỗi của ứng dụng.
}
~~~

Ví dụ cần `import java.io.UncheckedIOException;`. Dùng `IOException` và `UncheckedIOException` ở hai nhánh riêng giúp phân biệt nguồn lỗi khi telemetry và retry.

**Không tự nuốt `UncheckedIOException` và trả 0 hoặc danh sách rỗng** nếu chưa có chính sách domain. Chẳng hạn, đọc 100 dòng rồi bị lỗi byte ở dòng 101, trả kết quả một phần như thể file hoàn chỉnh có thể dẫn tới số liệu báo cáo sai. Nếu dữ liệu phải chính xác, trả lỗi toàn bộ tác vụ hoặc đánh dấu kết quả partial rõ ràng.

### Có thể lỗi giải mã chỉ xuất hiện khi terminal operation chạy

~~~java
try (Stream<String> lines =
        Files.lines(badFile, StandardCharsets.UTF_8)) {
    long count = lines.count(); // Có thể ném UncheckedIOException ở đây.
}
~~~

`Files.lines` tạo stream trước; các lỗi hậu mở tệp được phát hiện trong lúc tiêu thụ. Trên JDK đang chạy, một tệp chứa byte UTF-8 không hợp lệ `0xC3 0x28` gây `MalformedInputException` làm cause của `UncheckedIOException` khi duyệt.

Không phụ thuộc vào text chính xác của thông điệp lỗi (như “Input length = 1”) cho business logic; nó có thể khác giữa JVM/provider. Thay vào đó xác định lớp lỗi, cause và hành động recover/logging thích hợp.

## 7. BOM: không tự coi là một phần đã được xử lý

**Byte Order Mark (BOM)** là một dấu có thể nằm ở đầu tệp Unicode. Với UTF-8, dãy byte BOM thường là `EF BB BF`. Nếu bạn xử lý một nguồn có BOM, cần **định nghĩa policy**: từ chối, loại bỏ ở đầu tệp, hoặc giữ nguyên như một ký tự dữ liệu.

Trong kiểm thử thực tế của chương trình cuối bài trên JDK 17, `Files.lines(path, StandardCharsets.UTF_8)` đọc tệp có UTF-8 BOM và **ký tự đầu tiên của dòng đầu là `\uFEFF`**. Không được lặng lẽ giả định mọi reader và mọi charset sẽ tự loại BOM giống nhau.

~~~java
String firstLine;
try (Stream<String> lines =
        Files.lines(bomFile, StandardCharsets.UTF_8)) {
    firstLine = lines.findFirst().orElse("");
}
boolean hasBom = !firstLine.isEmpty()
        && firstLine.charAt(0) == '\uFEFF';
~~~

Đoạn này **chỉ phát hiện** dấu tại ký tự đầu dòng đầu; nếu muốn bỏ BOM thì **chỉ** bỏ khi nó đúng là dấu đầu của nguồn theo policy, không xóa mọi `U+FEFF` trong file. Với một pipeline stream song song, đừng dùng một `AtomicBoolean` side effect trong `map` để “đoán dòng đầu tiên” theo thứ tự callback: callback có thể chạy ngoài encounter order.

Với `UTF_16`, semantics của BOM và byte order thuộc hợp đồng charset khác UTF-8. Nếu nguồn là UTF-16LE/BE, chọn decoder theo dữ liệu, kiểm thử sample thật và không coi việc chỉ đổi hằng số UTF-8 thành UTF-16 là một cơ chế nhận diện charset tự động.

## 8. Chọn API đọc tệp phù hợp

| API | Trả về | Nạp toàn bộ? | Ai đóng file? | Java |
| --- | --- | --- | --- | --- |
| `Files.lines(path, cs)` | `Stream<String>` | Đọc lười; pipeline quyết định RAM | Caller phải đóng stream | 8+ |
| `Files.lines(path)` | `Stream<String>` | Đọc lười, UTF-8 | Caller đóng | 8+ |
| `Files.readAllLines(path, cs)` | `List<String>` | Tất cả dòng trong bộ nhớ | Method tự đóng | 8+ |
| `Files.newBufferedReader(path, cs)` | `BufferedReader` | Đọc theo buffer | Caller đóng reader | 8+ |
| `BufferedReader.lines()` | `Stream<String>` | Đọc lười từ reader | **Caller vẫn đóng reader** | 8+ |
| `Files.readString(path, cs)` | `String` | Toàn nội dung, bao gồm terminator | Method tự đóng | **11+** |

### `Files.readAllLines`

~~~java
List<String> lines =
        Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

Phù hợp cho file nhỏ vừa và khi thực sự cần mọi dòng ở dạng list. Với file lớn, `Files.lines` hoặc `BufferedReader` theo vòng lặp sẽ thuận lợi hơn để tránh giữ quá nhiều dữ liệu.

### `Files.newBufferedReader`

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý tuần tự từng dòng.
    }
}
~~~

Có ích khi cần điều khiển vòng lặp, đọc header riêng, hay xử lý state machine giữa các dòng. Với `BufferedReader.lines()`, hãy đóng **reader** bao quanh; không dựa vào việc đóng stream trả từ `reader.lines()` để thay thế hợp đồng đóng reader.

### `Files.readString` dành cho Java 11+

`Files.readString(path, StandardCharsets.UTF_8)` đọc toàn bộ chuỗi, bao gồm newline, nhưng **không có trong Java 8**. Chỉ dùng khi target JDK 11+ và việc giữ toàn tệp trong RAM là phù hợp. Cũng không nhầm `Stream.toList()` (Java 16+) với `Collectors.toList()` (Java 8+): hai API khác nhau về phiên bản và quy tắc tính mutability của List kết quả.

## 9. Có nên dùng `parallel()` với `Files.lines`?

Câu trả lời là **có thể, nhưng không tự động tốt hơn**. Tài liệu chính thức Java hiện đại nêu triển khai `Files.lines` có khả năng chia nguồn tốt cho những charset *line-optimal*:

- `UTF-8`
- `US-ASCII`
- `ISO-8859-1`

Lý do là byte LF/CR có thể được nhận diện thuận tiện khi chia vùng byte của file; với tệp có cấu trúc dòng đều, `Spliterator` có thể chia gần một nửa số dòng.

Với một số charset khác (ví dụ những encoding không có đặc tính line-optimal), khả năng chia nguồn có thể kém, tương tự spliterator dựa trên iterator hoặc `BufferedReader.lines()`. **Good splitting không đồng nghĩa guaranteed speedup**: còn phụ thuộc số core, I/O, độ dài dòng, chi phí parse, thao tác terminal và tranh chấp tài nguyên.

~~~java
List<String> values;
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    values = lines.parallel()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());
}
~~~

Với stream có encounter order, `collect(Collectors.toList())` giữ thứ tự phần tử của kết quả phù hợp hợp đồng. Tuy nhiên, **thứ tự thực thi `map`/`filter` có thể khác thứ tự dòng**.

Không dùng:

~~~java
// Không hứa stdout theo thứ tự file:
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.parallel().forEach(System.out::println);
}
~~~

Nếu bắt buộc side effect phải theo thứ tự encounter, có thể dùng `forEachOrdered`, nhưng việc này có thể giảm lợi thế song song và vẫn không bảo đảm callback chỉ dùng một thread:

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.parallel().forEachOrdered(System.out::println);
}
~~~

**Nên benchmark thực tế trước khi chọn `parallel()`.** Với file trên ổ chậm hoặc mỗi dòng chỉ xử lý rất nhẹ, overhead chia/gộp có thể nhiều hơn lợi ích. Không mutate một `ArrayList` chung từ `parallel().forEach(list::add)`; dùng `collect` và giá trị xử lý không mang side effect.

## 10. Tệp có thể thay đổi trong lúc đọc: không có snapshot miễn phí

Javadoc quy định **không nên sửa nội dung tệp trong lúc đang thực hiện terminal stream operation**; nếu sửa, kết quả của terminal operation là **không xác định**. Không dựa vào việc stream tự đồng bộ, tự snapshot, hoặc tự “theo dõi” phần byte được ghi thêm.

Tình huống dễ gặp:

- Service A tạo `Files.lines` cho tệp log trong khi service B tiếp tục append.
- Hệ thống ETL đọc từ một file đang được ghi nửa chừng.
- File ở thư mục dùng chung bị rename/replace trong lúc đọc.
- Network file system thay đổi nội dung ngoài tiến trình.

Nếu yêu cầu kết quả chính xác, hãy đọc **tệp đã đóng ghi và được publish nguyên vẹn** (ví dụ bằng quy trình ghi file tạm rồi rename phù hợp filesystem/provider), hoặc áp dụng cơ chế snapshot/version/lock ở tầng hệ thống thích hợp. Không tự kết luận rằng vì `Stream<String>` đã được tạo nên dữ liệu luôn là bản chụp ngay tại thời điểm mở.

## 11. Hiệu năng và giới hạn bộ nhớ

`Files.lines` thường phù hợp cho tệp lớn khi tác vụ có thể xử lý tuần tự từng dòng:

~~~java
long warningCount;
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    warningCount = lines.filter(s -> s.startsWith("WARN ")).count();
}
~~~

Tránh những bước lưu tất cả dòng nếu chỉ cần count hoặc tổng hợp:

~~~java
// Tốn RAM theo toàn bộ số dòng:
List<String> all;
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    all = lines.collect(Collectors.toList());
}
~~~

Nếu cần thống kê tần suất, `collect(groupingBy(..., counting()))` sẽ giữ các key và state cần thiết; bộ nhớ phụ thuộc số key. Nếu số key vô hạn hoặc rất lớn, cân nhắc xử lý từng phần, cơ sở dữ liệu, external aggregation hoặc một hệ streaming chuyên trách.

**Giới hạn line length**: file chỉ có một dòng vài gigabyte vẫn gây áp lực dù `Files.lines` là lazy. Nếu đầu vào không tin cậy, đặt hạn mức tổng byte/kích thước file, giới hạn độ dài mỗi record, timeout, số dòng, dung lượng queue và chính sách abort theo mục tiêu bảo mật.

**Không đọc charset “mềm” chỉ để ép thành công** nếu nội dung là dữ liệu tài chính hoặc import quan trọng. Một byte lỗi cần được nhận diện và xử lý theo policy, thay vì thay ký tự âm thầm khiến dữ liệu không thể khôi phục.

## 12. Vấn đề đường dẫn và bảo mật

`Path` là tham số tài nguyên ngoài hệ thống, không phải chuỗi tin cậy. Nếu file path đến từ người dùng:

- Giới hạn thư mục đọc hợp lệ; chống path traversal (`..`), symbolic link và sự thay đổi giữa validate và open.
- Dùng root directory cho phép, normalize path và kiểm tra thực tế với chính sách filesystem; chỉ kiểm tra `normalize().startsWith(root)` có thể không đủ trước symlink/race.
- Đừng log nội dung nhạy cảm, secret hoặc nguyên tệp chỉ để debug.
- Tệp ở network share có thể bị cắt kết nối giữa quá trình đọc, nên xử lý `UncheckedIOException`.
- Không xóa/ghi đè file đầu vào trong khi stream còn đang đọc.

Trong ứng dụng nhiều tenant, **kiểm tra quyền ở tầng nghiệp vụ và filesystem**; chỉ một đường dẫn hợp lệ về mặt cú pháp không đồng nghĩa người dùng có quyền đọc.

## 13. Chương trình Java độc lập: thử charset, newline, BOM và hai loại lỗi

Tạo file **`FilesLinesCharsetDemo.java`**. Chương trình sử dụng toàn bộ API hiện hành và phù hợp Java 8; lệnh biên dịch ví dụ dùng JDK 17. Để không phụ thuộc một tệp bên ngoài, chương trình **tự tạo thư mục tạm và các file dữ liệu kiểm thử**, sau đó xóa bằng `finally`. Nó kiểm tra 11 điều kiện bằng `check(...)`, và dòng cuối `all checks passed` chỉ được in khi mọi kiểm tra đều đúng.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public final class FilesLinesCharsetDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("files-lines-demo-");
        Path utf8 = dir.resolve("utf8.txt");
        Path latin1 = dir.resolve("latin1.txt");
        Path malformed = dir.resolve("malformed.txt");
        Path bom = dir.resolve("bom.txt");
        try {
            String text = "  táo  \r\ncam\n\nnho\r";
            Files.write(utf8, text.getBytes(StandardCharsets.UTF_8));
            List<String> lines;
            try (Stream<String> input = Files.lines(utf8, StandardCharsets.UTF_8)) {
                lines = input.collect(Collectors.toList());
            }
            System.out.println("utf8 line count: " + lines.size());
            System.out.println("utf8 first: <" + lines.get(0) + ">");
            System.out.println("utf8 blank at index 2: " + lines.get(2).isEmpty());
            System.out.println("utf8 last: <" + lines.get(3) + ">");

            long nonBlank;
            try (Stream<String> input = Files.lines(utf8, StandardCharsets.UTF_8)) {
                nonBlank = input.map(String::trim).filter(s -> !s.isEmpty()).count();
            }
            System.out.println("nonblank after trim: " + nonBlank);

            String defaultFirst;
            try (Stream<String> input = Files.lines(utf8)) {
                defaultFirst = input.findFirst().orElse("");
            }
            System.out.println("default charset UTF-8 agrees: " +
                    defaultFirst.equals(lines.get(0)));

            List<String> orderedParallel;
            try (Stream<String> input = Files.lines(utf8, StandardCharsets.UTF_8)) {
                orderedParallel = input.parallel()
                        .map(String::trim)
                        .filter(s -> !s.isEmpty())
                        .collect(Collectors.toList());
            }
            System.out.println("parallel ordered result: " + orderedParallel);

            Files.write(latin1,
                    "café\nfaçade".getBytes(StandardCharsets.ISO_8859_1));
            String latinFirst;
            try (Stream<String> input = Files.lines(latin1, StandardCharsets.ISO_8859_1)) {
                latinFirst = input.findFirst().orElse("");
            }
            System.out.println("Latin-1 correct charset: " + latinFirst);

            boolean wrongCharsetError = false;
            try (Stream<String> input = Files.lines(latin1, StandardCharsets.UTF_8)) {
                input.forEach(s -> {});
            } catch (UncheckedIOException ex) {
                wrongCharsetError = true;
                System.out.println("Latin-1 bytes as UTF-8: " +
                        ex.getCause().getClass().getSimpleName());
            }

            Files.write(malformed, new byte[]{(byte) 0xC3, (byte) 0x28, (byte) '\n'});
            boolean malformedError = false;
            try (Stream<String> input = Files.lines(malformed, StandardCharsets.UTF_8)) {
                input.count();
            } catch (UncheckedIOException ex) {
                malformedError = true;
                System.out.println("invalid UTF-8: " +
                        ex.getCause().getClass().getSimpleName());
            }

            Files.write(bom, new byte[]{(byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
                    (byte) 'A', (byte) '\n', (byte) 'B'});
            String firstBom;
            try (Stream<String> input = Files.lines(bom, StandardCharsets.UTF_8)) {
                firstBom = input.findFirst().orElse("");
            }
            System.out.println("UTF-8 BOM remains in first line: " +
                    (!firstBom.isEmpty() && firstBom.charAt(0) == '\uFEFF'));

            boolean missingOpen = false;
            try (Stream<String> input = Files.lines(
                    dir.resolve("missing.txt"), StandardCharsets.UTF_8)) {
                input.count();
            } catch (NoSuchFileException ex) {
                missingOpen = true;
                System.out.println("missing at open: NoSuchFileException");
            }

            check(lines.size() == 4, "terminators");
            check(lines.get(0).equals("  táo  "), "UTF-8");
            check(lines.get(2).isEmpty(), "blank lines");
            check(lines.get(3).equals("nho"), "final terminator");
            check(nonBlank == 3L, "filter");
            check(defaultFirst.equals(lines.get(0)), "default UTF-8");
            check(orderedParallel.equals(Arrays.asList("táo", "cam", "nho")),
                    "encounter order");
            check(latinFirst.equals("café"), "Latin-1 decoding");
            check(wrongCharsetError && malformedError, "strict decoding");
            check(!firstBom.isEmpty() && firstBom.charAt(0) == '\uFEFF',
                    "UTF-8 BOM handling");
            check(missingOpen, "missing file");
            System.out.println("all checks passed");
        } finally {
            for (Path file : Arrays.asList(utf8, latin1, malformed, bom)) {
                Files.deleteIfExists(file);
            }
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 -encoding UTF-8 FilesLinesCharsetDemo.java
java FilesLinesCharsetDemo
~~~

**Stdout đã được chạy kiểm tra trên JDK 17:**

~~~text
utf8 line count: 4
utf8 first: <  táo  >
utf8 blank at index 2: true
utf8 last: <nho>
nonblank after trim: 3
default charset UTF-8 agrees: true
parallel ordered result: [táo, cam, nho]
Latin-1 correct charset: café
Latin-1 bytes as UTF-8: MalformedInputException
invalid UTF-8: MalformedInputException
UTF-8 BOM remains in first line: true
missing at open: NoSuchFileException
all checks passed
~~~

**Giải thích theo từng nhóm kết quả:**

1. Bốn dòng được đọc dù tệp kết hợp CRLF, LF, hai LF liên tiếp và CR; dấu kết thúc dòng không còn trong phần tử String. Khoảng trắng của `"  táo  "` vẫn được giữ.
2. Dòng rỗng ở vị trí 2 tồn tại trong dữ liệu. Chỉ pipeline có `trim + filter` mới giảm kết quả còn 3 dòng không rỗng.
3. `Files.lines(path)` sử dụng UTF-8 mặc định nên cùng cho dòng đầu chính xác khi tệp thực sự là UTF-8.
4. Pipeline `parallel()` cùng `collect(toList())` cho List kết quả theo encounter order; không suy từ List này rằng các callback `map` đã chạy theo thứ tự dòng.
5. Tệp Latin-1 với `café` đọc đúng `ISO_8859_1`; ép cùng byte thành UTF-8 sẽ gây lỗi giải mã trong lúc duyệt. Tệp UTF-8 malformed cũng phát sinh cùng kiểu nguyên nhân.
6. BOM trong tệp thử UTF-8 được thấy ở đầu dòng đầu theo JDK đã thử; nếu import nhận BOM, phải có policy tường minh thay vì giả định tự được xóa.
7. Tệp không tồn tại tạo lỗi `NoSuchFileException` ở bước mở trên provider được kiểm thử; các provider khác có thể chọn subclass của `IOException` thích hợp với tình huống.
8. 11 phép kiểm tra cuối bảo đảm charset, dấu xuống dòng, dòng trống, kết quả song song có order, nhận diện BOM và phân biệt lỗi mở với lỗi giải mã.

Chương trình dùng `Files.createTempDirectory`/`Files.write` để tạo input độc lập và xóa trong `finally`. Nếu chương trình bị dừng cưỡng bức trước cleanup, file tạm có thể còn; trong hệ thống thực, cần policy cleanup phù hợp. Không nên thay `finally` bằng giả định filesystem tự xóa ngay khi đóng JVM.

## 14. Ví dụ áp dụng: thống kê log lớn với Charset cụ thể

Giả sử file UTF-8 có các dòng log văn bản:

~~~text
INFO  started
WARN  slow query
INFO  finished
WARN  retry
~~~

Muốn đếm warning mà không nạp toàn bộ file:

~~~java
static long countWarnings(Path logFile) throws IOException {
    try (Stream<String> lines =
            Files.lines(logFile, StandardCharsets.UTF_8)) {
        return lines.filter(s -> s.startsWith("WARN ")).count();
    }
}
~~~

Khi file mở được và các byte hợp lệ, kết quả từ dữ liệu ví dụ là `2`. Nếu đọc bị lỗi, phải truyền lỗi lên hoặc áp dụng chính sách fail/retry rõ ràng; không tự lấy một số dòng đếm được rồi ghi là tổng cuối cùng.

Đếm các dòng chứa nhiều từ khóa theo một pass có thể dùng collector hoặc accumulator rõ ràng; tránh gọi `Files.readAllLines` chỉ để tìm vài từ khóa. Nếu log đang được ghi liên tục, `Files.lines` **không cung cấp tail -f** hoặc snapshot nhất quán: hãy đọc file đã hoàn tất hoặc dùng cơ chế log ingestion chuyên dụng.

## 15. Những lỗi phổ biến và cách sửa

| Sai lầm | Nguyên nhân/hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Files.lines` mà không đóng stream | File handle vẫn mở | `try-with-resources` |
| Tin `count()` tự đóng tệp | Terminal không thay hợp đồng close | Đóng resource block |
| Trả stream ra ngoài `try` đã đóng | Caller nhận stream đã mất tài nguyên | Xử lý bên trong, hoặc xác định rõ ownership |
| Cho rằng `Files.lines(path)` dùng charset mặc định máy | Thực tế API định nghĩa UTF-8 | Hiểu đúng overload và truyền UTF-8 khi muốn rõ hợp đồng |
| Dùng UTF-8 đọc file Latin-1 | Có thể malformed | Chọn charset theo nguồn |
| Dùng Latin-1 đọc mọi file vì ít báo lỗi | Có thể âm thầm biến ký tự sai | Validate nguồn và charset |
| Dựa vào extension `.txt` để đoán encoding | Tên file không chứa charset | Metadata/giao thức/chính sách import |
| Giả định UTF-8 BOM đã được xóa | Có thể còn `U+FEFF` | Test và xử lý riêng đầu tệp theo policy |
| Xem mỗi `\r\n` là hai dòng | CRLF là một terminator | Dùng API tách dòng |
| Nghĩ mọi newline Unicode đều được hỗ trợ | Javadoc chỉ bảo đảm một số dấu | Dựa vào contract và parser đúng định dạng |
| Mong dòng trả về còn `\n` | `Files.lines` bỏ terminator | Nếu cần nguyên văn, dùng API byte/`readString` phù hợp |
| Tự `trim` mọi dòng | Mất indent/khoảng trắng có nghĩa | Chỉ trim khi domain cho phép |
| `filter` bỏ dòng rỗng trong file CSV | Mất bản ghi hợp lệ | Parse theo định dạng |
| Dùng `Files.lines` để parse CSV quoted multiline | Record khác dòng vật lý | Dùng CSV parser |
| Bắt mỗi `IOException` nhưng bỏ `UncheckedIOException` | Lỗi khi duyệt chưa xử lý | Phân biệt pha mở và pha đọc |
| Nuốt lỗi decoder và trả dữ liệu partial như đầy đủ | Báo cáo sai | Fail/retry hoặc đánh dấu partial rõ |
| Gọi nhiều terminal trên cùng stream | Stream chỉ dùng một lần | Mở lại hoặc gộp phép tính |
| Dùng `collect(toList())` cho tệp hàng trăm GB | RAM tăng theo output | Aggregate/stream từng dòng |
| Dùng `parallel()` rồi kỳ vọng callback theo thứ tự | Scheduling không cam kết thứ tự | Ordered collector/`forEachOrdered` nếu cần |
| Dùng `parallel().forEach(sharedList::add)` | Race và thứ tự không ổn định | `collect` |
| Dùng parallel cho mọi charset và tưởng luôn nhanh | Spliterator có thể chia kém | Benchmark và xem line-optimal charset |
| Đọc file đồng thời với một writer | Kết quả operation không xác định | Snapshot/publish immutable file |
| Không hạn chế file/line size từ nguồn lạ | Có nguy cơ quá tải bộ nhớ, disk hoặc CPU | Quota và policy kích thước |
| Dùng `Files.readString` trong code Java 8 | API chỉ có từ Java 11 | Giữ API Java8 hoặc nâng target |
| Dùng `Stream.toList()` như API Java 8 | Chỉ có từ Java 16 | Java 8 dùng `Collectors.toList()` |
| Dùng `Charset.defaultCharset()` làm hợp đồng nghiệp vụ | Có thể đổi theo môi trường | Thỏa thuận charset tường minh |

## 16. Bài tập tự luyện và đáp án

### Bài 1 — Đọc và in từng dòng UTF-8

Viết code đọc `data/users.txt` với UTF-8, in các dòng không rỗng, bảo đảm đóng file.

**Đáp án:**

~~~java
try (Stream<String> lines =
        Files.lines(Paths.get("data", "users.txt"), StandardCharsets.UTF_8)) {
    lines.filter(s -> !s.trim().isEmpty())
         .forEach(System.out::println);
}
~~~

Cần có imports và xử lý `IOException`/`UncheckedIOException` theo hàm bao ngoài; không giữ stream để dùng sau khi block kết thúc.

### Bài 2 — Overload không truyền Charset

`Files.lines(path)` trên Java 8 dùng `Charset.defaultCharset()` hay UTF-8?

**Đáp án:** UTF-8, tương đương `Files.lines(path, StandardCharsets.UTF_8)` theo đặc tả. Không suy ra hành vi của các API khác từ trường hợp này.

### Bài 3 — Đếm dòng không rỗng của một tệp lớn

Có thể gọi `Files.readAllLines(...).size()` không? Cách nào tránh giữ toàn List?

**Đáp án:** Có thể với file nhỏ, nhưng đọc toàn bộ gây chi phí bộ nhớ. Với file lớn, dùng `try (Stream<String> lines=Files.lines(path,charset)) { return lines.filter(s->!s.isEmpty()).count(); }`. Nếu business định nghĩa “rỗng” là toàn khoảng trắng, cần `trim()`/kiểm tra Unicode theo quy định riêng.

### Bài 4 — CRLF và dòng cuối

Tệp gồm `"a\r\nb\n\nc\r"` có bao nhiêu dòng?

**Đáp án:** Bốn dòng: `"a"`, `"b"`, `""`, `"c"`. `\r\n` được nhận như một terminator, không tạo dòng trống phụ ở cuối.

### Bài 5 — File Latin-1

Tệp chứa `café` bằng ISO-8859-1, nhưng code đọc với UTF-8. Điều gì xảy ra?

**Đáp án:** Khi duyệt, byte `é` của Latin-1 có thể gây `UncheckedIOException` với `MalformedInputException`; phải chọn `StandardCharsets.ISO_8859_1` khi đó là charset thật của nguồn.

### Bài 6 — Vì sao `try-with-resources` vẫn cần sau `findFirst`?

**Đáp án:** Vì `findFirst()` dừng sớm không có hợp đồng tự close file handle. `Files.lines` trả stream có tài nguyên, nên luôn phải đóng sau khi xử lý.

### Bài 7 — Phân biệt ngoại lệ

Tệp không tồn tại và tệp có byte UTF-8 không hợp lệ có nhất thiết ném cùng một ngoại lệ tại cùng vị trí code?

**Đáp án:** Không. Lỗi mở thường là `IOException` như `NoSuchFileException`; lỗi đọc/decoder sau khi phương thức trả stream có thể là `UncheckedIOException` ở terminal hoặc close.

### Bài 8 — UTF-8 BOM

Tệp bắt đầu bằng `EF BB BF`. Có thể mặc định `Files.lines` luôn tự bỏ dấu này không?

**Đáp án:** Không. Trên chương trình thử JDK 17, dấu xuất hiện dưới dạng `\uFEFF` ở đầu dòng đầu. Hãy xác định chính sách BOM của dữ liệu import và test hành vi decoder; xử lý riêng vị trí đầu tệp nếu yêu cầu.

### Bài 9 — Parallel và thứ tự

`Files.lines(path,UTF_8).parallel().forEach(System.out::println)` có in đúng thứ tự dòng gốc không?

**Đáp án:** Không được bảo đảm. Với nguồn có encounter order, muốn List kết quả theo thứ tự có thể dùng `collect(Collectors.toList())`, còn side effect buộc thứ tự có `forEachOrdered` nhưng có thể giảm lợi ích parallel.

### Bài 10 — File bị writer thay đổi

Một writer append vào tệp trong lúc terminal operation của `Files.lines` đang đọc. Có thể xem kết quả là snapshot tại thời điểm gọi `Files.lines` không?

**Đáp án:** Không. Javadoc quy định không sửa file trong khi terminal operation đang chạy; nếu sửa, kết quả là undefined. Dùng quy trình publish file hoàn chỉnh, snapshot hoặc kiến trúc ingestion phù hợp.

### Bài 11 — Java 8 và `Files.readString`

Một dự án biên dịch với `--release 8` gọi `Files.readString(path)` có đúng không?

**Đáp án:** Không. `Files.readString` được bổ sung từ Java 11. Java 8 dùng `Files.lines`, `Files.readAllLines`, `Files.newBufferedReader` hoặc `Files.readAllBytes` với decode explicit tùy nhu cầu.

### Bài 12 — Tệp lớn có một dòng cực dài

Vì sao `Files.lines` vẫn có thể tốn nhiều bộ nhớ dù là lazy?

**Đáp án:** Một String đại diện cho một dòng cực dài phải có chỗ trong RAM; các terminal như `collect(toList())` còn giữ nhiều dòng. Cần hạn mức file/record và chọn xử lý phù hợp cho input không tin cậy.

## 17. Checklist trước khi đưa vào production

- [ ] Nguồn tệp có charset chính xác, được quy định tường minh?
- [ ] Dùng `StandardCharsets.UTF_8` hoặc charset thật do nguồn cung cấp, không đoán theo hệ điều hành?
- [ ] Nếu nguồn dùng BOM, đã định nghĩa hành vi giữ/loại/từ chối?
- [ ] Có phân biệt dòng vật lý và bản ghi logic của định dạng?
- [ ] Dấu CRLF/LF/CR, dòng rỗng và dòng cuối đã được test?
- [ ] `trim`/`filter` chỉ được áp dụng khi nghiệp vụ cho phép mất khoảng trắng/dòng rỗng?
- [ ] `Files.lines` nằm trong `try-with-resources` và file được close kể cả khi short-circuit?
- [ ] Code không trả stream đã đóng ra ngoài hàm?
- [ ] Có xử lý `IOException` khi mở và `UncheckedIOException` khi duyệt/đóng?
- [ ] Lỗi malformed/unmappable không bị “nuốt” thành kết quả partial giả?
- [ ] Tệp có thể bị sửa trong lúc đọc không? Nếu cần nhất quán đã có cơ chế publish/snapshot?
- [ ] Không giữ toàn bộ tệp trong RAM nếu chỉ cần count/filter/reduce?
- [ ] Đã giới hạn kích thước file và dòng từ nguồn không tin cậy?
- [ ] Nếu dùng parallel, có xem xét charset line-optimal và đo hiệu năng thực tế?
- [ ] Không suy thứ tự callback `forEach` từ encounter order?
- [ ] Không dùng container mutable dùng chung từ parallel `forEach`?
- [ ] Đường dẫn input đã được validate, kiểm soát quyền và symlink theo threat model?
- [ ] API trong dự án đã được đối chiếu version (Java 8 vs Java 11/16+)?
- [ ] Mẫu code đã biên dịch; stdout, Unicode và ngoại lệ đã được đối chiếu thực tế?

**Tóm tắt:** `Files.lines(path, charset)` giúp đọc từng dòng một cách lazy với charset do lập trình viên xác định, nhưng **người gọi phải đóng stream**. Nguồn dữ liệu nên chỉ rõ UTF-8/encoding thật; byte lỗi khi duyệt có thể trở thành `UncheckedIOException`, và việc tách dòng **không giữ terminator**. Dùng `try-with-resources`, chọn terminal operation theo dung lượng dữ liệu, lưu ý BOM và thứ tự khi parallel, đồng thời không đọc một tệp đang bị sửa nếu cần kết quả nhất quán.

### Tài liệu chính thức đang được duy trì

- [`Files` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `lines(Path,Charset)`, `lines(Path)`, lazy stream, try-with-resources, `UncheckedIOException`, parallel splitting và so sánh `readAllLines`.
- [`StandardCharsets` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset chuẩn `UTF_8`, `US_ASCII`, `ISO_8859_1`, `UTF_16`.
- [`Charset` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/Charset.html): quy tắc mã hóa/giải mã và các charset bắt buộc.
- [`Stream` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): intermediate/terminal operations, encounter order, close và stream không tái sử dụng.
- [`UncheckedIOException` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/UncheckedIOException.html): wrapper của IOException khi thao tác stream.
- [`BufferedReader` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html): `readLine` và `lines`, tài nguyên reader cần close.