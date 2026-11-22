# Files.lines đọc lười và bắt buộc quản lý vòng đời Stream trong Java

## 1. Files.lines() giải quyết việc gì?

Trong Java NIO.2, **`java.nio.file.Files.lines(Path)`** trả về một **`Stream<String>`** gồm các dòng văn bản từ file. Thay vì đọc toàn bộ file thành `List<String>` trước khi xử lý, ứng dụng có thể xây dựng một chuỗi thao tác `filter`, `map`, `limit`, `findFirst`, `count`... và xử lý nội dung theo nhu cầu.

Ví dụ:

~~~java
// Mảnh code: path là Path hợp lệ; phương thức xử lý IOException.
try (java.util.stream.Stream<String> lines =
        java.nio.file.Files.lines(
                path, java.nio.charset.StandardCharsets.UTF_8)) {
    long count = lines
            .filter(line -> line.startsWith("ERROR"))
            .count();
    System.out.println(count);
}
~~~

Ở đây **`Files.lines()` tạo Stream gắn với file**, còn `filter()` chưa duyệt các dòng ngay. Khi `count()` là terminal operation được thực thi, Stream bắt đầu cần các phần tử để tính kết quả. Kết thúc khối **try-with-resources** tự gọi `close()` trên Stream, nhờ đó giải phóng tài nguyên I/O.

**Thông điệp quan trọng nhất:**

> **Đọc lười (lazy) không có nghĩa là không mở tài nguyên.** `Files.lines()` mở file để tạo Stream, nhưng nội dung được đọc theo tiến trình tiêu thụ Stream. Vì vậy `Stream<String>` nhận từ `Files.lines()` phải được đóng sau khi sử dụng.

Đây là sự khác biệt quan trọng giữa Stream **tính toán trong bộ nhớ** như `List.stream()` và Stream **gắn với tài nguyên ngoài** như `Files.lines()`. Dùng Stream API nói chung không buộc phải `close()`, nhưng tài liệu `Files.lines()` yêu cầu đóng Stream để giải phóng file đang mở.

## 2. Ba giai đoạn: mở file, xây pipeline và tiêu thụ

Sơ đồ:

~~~text
Path tới file
    |
    | Files.lines(path, UTF_8)
    v
Stream<String> đã gắn với tài nguyên I/O
    |
    | .filter(...)
    | .map(...)
    | .limit(...)
    v
Pipeline đã khai báo — chưa duyệt toàn bộ dữ liệu
    |
    | .count() / .findFirst() / .forEach() / .toList()
    v
Terminal operation khiến dữ liệu được tiêu thụ
    |
    | Kết thúc try-with-resources
    v
Stream.close() -> đóng tài nguyên file liên quan
~~~

Cần phân biệt:

1. **`Files.lines(...)` có thể ném `IOException` ngay tại thời điểm gọi**, chẳng hạn file không mở được vì quyền truy cập hoặc đường dẫn sai. Không nên nói rằng “hoàn toàn không có I/O cho đến `count()`”.
2. Các **intermediate operation** như `filter()`, `map()`, `skip()`, `limit()` thường chỉ cấu hình pipeline. Chúng không buộc toàn bộ file được đọc ngay.
3. Khi có **terminal operation**, pipeline bắt đầu được duyệt; một số thao tác như `findFirst()`, `anyMatch()`, `limit(n)` có thể **short-circuit**, nghĩa là không cần xử lý hết file.
4. **Terminal operation kết thúc không đồng nghĩa Stream tự được đóng**. Phải đóng trực tiếp hoặc ưu tiên try-with-resources.
5. Stream chỉ dùng cho **một lần tiêu thụ**. Sau terminal operation, không được chạy thêm terminal operation khác trên cùng pipeline; muốn duyệt lại file, mở Stream mới.

Việc triển khai có thể dùng buffering hoặc tối ưu cách chia dữ liệu; không dựa vào giả định “mỗi lần `map()` sẽ đọc đúng một dòng byte từ ổ đĩa”. *Lazy* mô tả cơ chế thực thi pipeline, không cam kết chi tiết số lần gọi I/O.

## 3. Chương trình Java 17+ đọc lười và đóng tài nguyên

Tạo file **LazyFileLinesDemo.java** (mã nguồn UTF-8):

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class LazyFileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lazy-lines-", ".log");

        try {
            Files.writeString(file,
                    "INFO start\n"
                    + "WARN slow\n"
                    + "ERROR disk\n"
                    + "INFO continue\n"
                    + "ERROR network\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {
                System.out.println("streamOpened=true");

                String firstError = lines
                        .filter(line -> line.startsWith("ERROR "))
                        .findFirst()
                        .orElse("not found");

                System.out.println("firstError=" + firstError);
            }

            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {
                long totalErrors = lines
                        .filter(line -> line.startsWith("ERROR "))
                        .count();

                System.out.println("totalErrors=" + totalErrors);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 LazyFileLinesDemo.java
java LazyFileLinesDemo
~~~

Kết quả stdout:

~~~text
streamOpened=true
firstError=ERROR disk
totalErrors=2
~~~

Giải thích:

- Chương trình tạo một file tạm, ghi năm dòng UTF-8, rồi dùng hai lượt `Files.lines()` **độc lập**.
- Lượt đầu dùng `filter(...).findFirst()` để lấy dòng `ERROR disk`. Vì `findFirst()` có thể dừng khi tìm được kết quả, **không nhất thiết xử lý mọi dòng còn lại**.
- Dù pipeline chỉ cần dòng lỗi đầu tiên, Stream vẫn phải **đóng**. TWR đảm nhiệm việc này khi thoát khỏi khối.
- Lượt thứ hai mở một Stream mới và dùng `count()` để đếm tất cả dòng có tiền tố `ERROR `, cho kết quả 2.
- Cuối cùng, `Files.deleteIfExists(file)` xóa file tạm do chương trình tạo. Xóa file là một thao tác riêng, **không phải thay thế cho đóng Stream**.

Các dòng demo chỉ chứa ASCII, nên stdout ổn định khi chạy từ terminal thông thường. Trong chương trình thực tế, nếu dùng tiếng Việt hoặc ký tự Unicode, hai phía đọc/ghi cần dùng cùng charset.

## 4. Vì sao cần try-with-resources?

`Files.lines()` trả một Stream giữ tài nguyên I/O của file, nên mẫu chuẩn là:

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    // Dùng lines ở đây.
}
~~~

`Stream` kế thừa cơ chế `BaseStream.close()` (BaseStream triển khai `AutoCloseable`), vì vậy nó có thể được khai báo trong try-with-resources.

Khi kết thúc khối try:

- Nếu body thành công, Stream vẫn được đóng.
- Nếu `filter`, `map`, `forEach` hay mã nghiệp vụ ném exception, TWR vẫn thử đóng Stream.
- Nếu body `return`, TWR vẫn chạy close trước khi trả về.
- Nếu đóng có lỗi đồng thời với lỗi body, quy tắc TWR về **primary/suppressed exception** được áp dụng; nguyên nhân từ body không tự bị thay bằng lỗi cleanup.

Không chỉ đóng khi bạn “đã đọc đến EOF”. Một terminal operation đọc hết file, dừng sớm, hoặc thất bại đều cần quản lý vòng đời.

**Ví dụ dễ mắc lỗi:**

~~~java
// SAI: tài nguyên file có thể không được đóng đúng hạn.
long n = Files.lines(path).filter(String::isBlank).count();
~~~

Mặc dù `count()` đã chạy xong, đoạn code không thể hiện việc đóng Stream. Không dựa vào garbage collector để đóng file descriptor. Hãy viết:

~~~java
// ĐÚNG: body có thể đọc hết hoặc ném exception, vẫn close.
try (Stream<String> lines = Files.lines(path)) {
    long n = lines.filter(String::isBlank).count();
}
~~~

**Không viết một hàm trả về Stream đã nằm trong TWR rồi kỳ vọng bên gọi dùng tiếp:**

~~~java
// SAI: Stream bị đóng khi hàm return.
static Stream<String> broken(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank());
    }
}
~~~

TWR chạy `close()` trước khi kết quả return được bàn giao cho caller. Caller nhận một pipeline gắn với nguồn đã đóng; tiêu thụ sau đó là không hợp lệ và có thể ném `IllegalStateException` hoặc lỗi liên quan tài nguyên đã đóng.

## 5. Quyền sở hữu Stream khi trả về từ phương thức

Có hai mẫu thiết kế hợp lệ, tùy nhu cầu API.

### Mẫu A — Xử lý trong phương thức, đóng tại chỗ

~~~java
// Mảnh code: thêm imports Path, Files, IOException, StandardCharsets,
// Stream khi đưa vào file nguồn của ứng dụng.
static long countNonBlank(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

Đây là mẫu **dễ hiểu và ít rò rỉ tài nguyên** nhất. Phương thức tự sở hữu file Stream, đóng hoàn chỉnh trước khi trả `long`. Caller không cần biết resource bên trong.

### Mẫu B — Trả Stream và chuyển trách nhiệm đóng cho caller

~~~java
static Stream<String> openNonBlankLines(Path path)
        throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8)
            .filter(line -> !line.isBlank());
}
~~~

Caller **phải** dùng TWR:

~~~java
try (Stream<String> lines = openNonBlankLines(path)) {
    lines.forEach(System.out::println);
}
~~~

Phương thức `openNonBlankLines` trả một Stream vẫn sống và **chuyển ownership** cho bên gọi. Vì điều này dễ bị sử dụng sai, API nên có tên/hướng dẫn rõ ràng rằng Stream phải được đóng. Không viết wrapper trả Stream mà đóng trước ở trong factory.

**Lưu ý:** Nếu muốn trả một kết quả dễ quản lý hơn, hãy cân nhắc trả danh sách, số lượng hoặc kết quả tính toán thay vì buộc bên gọi nhớ đóng Stream. Nhưng nếu dùng `toList()` cho file rất lớn, phải cân nhắc bộ nhớ.

## 6. filter/map/limit không thay thế close()

Những ví dụ sau **vẫn cần TWR**:

~~~java
// Đọc một vài dòng:
try (Stream<String> lines = Files.lines(path)) {
    lines.limit(5).forEach(System.out::println);
}
~~~

~~~java
// Tìm dòng đầu phù hợp:
try (Stream<String> lines = Files.lines(path)) {
    boolean found = lines.anyMatch(s -> s.contains("ERROR"));
    System.out.println(found);
}
~~~

~~~java
// Bỏ qua dòng đầu rồi xử lý phần còn lại:
try (Stream<String> lines = Files.lines(path)) {
    lines.skip(1).forEach(System.out::println);
}
~~~

- `limit(5)` có thể dừng đọc sau năm phần tử đầu.
- `anyMatch` có thể dừng ngay khi gặp phần tử thỏa mãn.
- `skip(1)` bỏ qua dòng đầu về mặt pipeline nhưng vẫn phải đi qua nguồn để xác định phần tử.
- **Tất cả đều phải close**, dù terminal operation có đọc hết hay không.

Đừng nghĩ rằng **`findFirst()` tự đóng file vì nó tìm thấy kết quả**. Việc pipeline hoàn tất và việc giải phóng I/O là hai mối quan tâm khác nhau.

### Derived Stream cũng dùng chung tài nguyên gốc

~~~java
try (Stream<String> errors = Files.lines(path)
        .filter(line -> line.startsWith("ERROR"))) {
    errors.forEach(System.out::println);
}
~~~

Đóng Stream thu được từ pipeline sẽ kích hoạt cơ chế đóng liên quan đến Stream gốc từ Files.lines(). Không cần và không nên mở/đóng lại file chỉ vì đã dùng một intermediate operation.

Tuy nhiên, Stream vẫn là **một lần dùng**: không thể `count()` rồi `findFirst()` trên cùng biến `errors`. Phải xây một pipeline tổng hợp hoặc mở Stream mới.

## 7. So với Files.readAllLines và Files.readString

**`Files.lines`**, **`Files.readAllLines`** và **`Files.readString`** đều phục vụ việc đọc text, nhưng cách dùng khác nhau:

| API | Kết quả | Thời điểm lấy dữ liệu | Caller có phải đóng Stream? | Phù hợp |
| --- | --- | --- | --- | --- |
| `Files.lines(path)` | `Stream<String>` | Đọc theo tiến trình tiêu thụ pipeline | **Có** | Lọc/đếm/xử lý file lớn hoặc dừng sớm |
| `Files.readAllLines(path)` | `List<String>` | Đọc toàn bộ dòng trước khi trả về | Không có Stream file cần caller đóng | File vừa/nhỏ cần danh sách |
| `Files.readString(path)` | `String` | Đọc toàn bộ file text | Không có Stream file cần caller đóng | File text đủ nhỏ, giữ nguyên nội dung gồm xuống dòng |
| `Files.newBufferedReader(path)` | `BufferedReader` | Từng thao tác đọc | **Có**, đóng Reader | Cần kiểm soát đọc dòng hoặc parse thủ công |

Một số hệ quả:

- **`readAllLines`** chứa tất cả dòng trong bộ nhớ khi trả về; với file lớn có thể tốn rất nhiều RAM. API tự quản lý tài nguyên bên trong lời gọi, caller không nhận Stream cần đóng.
- **`readString`** đọc toàn bộ text thành một String và giữ cả dấu ngắt dòng; dùng nó nếu cần nguyên nội dung thay vì từng dòng.
- **`Files.lines`** có thể tiết kiệm bộ nhớ nếu phép xử lý chỉ giữ ít trạng thái (đếm, tìm dòng đầu, ghi kết quả tới một sink). Nhưng `Files.lines(...).toList()` vẫn **tạo danh sách chứa tất cả phần tử được thu thập**: laziness của nguồn không khiến danh sách kết quả vô hạn trở nên rẻ.
- **`BufferedReader`** hỗ trợ vòng lặp `readLine()` và kiểm soát thủ công; bản thân Reader là tài nguyên phải đóng bằng TWR.

Cả ba API Files đọc văn bản nêu trên đều có overload nhận charset; overload phổ biến **không chỉ định charset sử dụng UTF-8** trong Java SE 17. Khi làm việc với định dạng ngoài hoặc file cũ, nên chỉ định rõ `StandardCharsets.UTF_8` hoặc charset được quy ước thay vì suy đoán.

## 8. Chương trình Java 17+: gộp kết quả mà không giữ toàn bộ dòng

Để thống kê số lượng dòng theo mức log, Stream có thể duyệt file và chỉ giữ các **bộ đếm** cho các nhóm, thay vì lưu cả danh sách dòng. Tạo file **LineSummaryDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LineSummaryDemo {
    static Map<String, Long> countLevels(Path file) throws IOException {
        try (Stream<String> lines =
                Files.lines(file, StandardCharsets.UTF_8)) {
            return lines
                    .filter(s -> !s.isBlank())
                    .map(s -> s.split(":", 2)[0])
                    .collect(Collectors.groupingBy(
                            Function.identity(),
                            TreeMap::new,
                            Collectors.counting()));
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("summary-", ".log");
        try {
            Files.writeString(file,
                    "INFO:started\n"
                    + "WARN:slow\n"
                    + "INFO:done\n",
                    StandardCharsets.UTF_8);

            System.out.println(countLevels(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LineSummaryDemo.java
java LineSummaryDemo
~~~

Stdout:

~~~text
{INFO=2, WARN=1}
~~~

Trong ví dụ này:

1. `Files.lines` tạo Stream đọc file.
2. `filter` bỏ dòng trắng; `map` lấy phần trước dấu hai chấm (quy ước log demo).
3. `Collectors.groupingBy` duy trì bộ đếm theo level; `TreeMap` giúp thứ tự khóa ổn định khi in ra.
4. `collect` tiêu thụ toàn bộ dòng cần xử lý. Ngay khi khối try kết thúc, Stream được đóng.
5. Hàm trả về **Map đã tính xong**, không còn phụ thuộc một Stream file đang mở.

Với số loại log ít, dữ liệu giữ lại không tỷ lệ trực tiếp với tổng số dòng. Tuy nhiên, nếu khóa nhóm không giới hạn (ví dụ nhóm theo từng dòng khác nhau), bản thân Map vẫn có thể rất lớn. **Laziness không tự bảo đảm sử dụng bộ nhớ hằng số**; điều đó phụ thuộc terminal operation và dữ liệu được lưu.

Chương trình dùng `String.split(":", 2)` như parser tối giản theo format demo. Với log sản xuất có escape, timestamp và cấu trúc phức tạp, dùng parser đúng đặc tả.

## 9. IOException khi mở Stream và UncheckedIOException khi duyệt

Có **hai giai đoạn lỗi I/O** khác nhau:

### Giai đoạn mở nguồn

~~~java
Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8);
~~~

Nếu file không mở được, lời gọi này có thể ném **`IOException`** (checked exception). Ví dụ đường dẫn không tồn tại hoặc không có quyền đọc. TWR chưa nhận một Stream được tạo thành công nên không có Stream ấy để close; API mở file có trách nhiệm tự dọn phần nội bộ nếu khởi tạo thất bại.

### Giai đoạn đang tiêu thụ

Sau khi `Files.lines()` đã trả về Stream, lỗi I/O hoặc lỗi giải mã phát sinh trong quá trình duyệt có thể được **bọc thành `UncheckedIOException`** (runtime exception). Nguyên nhân gốc có thể lấy qua `getCause()`.

Ví dụ xử lý rõ hai nhóm lỗi:

~~~java
// Mảnh code: path là Path, UTF_8 được import
try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
} catch (java.io.UncheckedIOException duringRead) {
    System.err.println("Read failed: " + duringRead.getCause());
} catch (IOException duringOpen) {
    System.err.println("Open failed: " + duringOpen);
}
~~~

Đây là mẫu minh họa chẩn đoán. Khi phát sinh nhiều lỗi cùng lúc, hãy kiểm tra thêm **suppressed exceptions**, bởi close() trong TWR có thể xảy ra trong lúc truyền một exception khác. Không nên nuốt lỗi đọc rồi báo tác vụ thành công; nếu file chưa duyệt xong vì I/O lỗi thì kết quả thống kê có thể không đầy đủ.

**Charset sai** cũng có thể khiến văn bản bị lỗi hoặc bị từ chối trong lúc đọc. `Files.lines(path, charset)` là giải mã byte theo charset được chỉ định; không tự phát hiện đúng charset gốc của mọi file. Nếu nội dung là nhị phân, dùng InputStream hoặc Files API cho byte thay vì cố giải mã thành dòng text.

## 10. Line terminator và các tình huống biên

Files.lines() tạo Stream của **các dòng văn bản**, không phải những chuỗi còn nguyên dấu kết thúc dòng. Các dấu tách dòng được hỗ trợ theo hợp đồng gồm **LF** (`\n`), **CR** (`\r`) và **CRLF** (`\r\n`). Dấu kết thúc dòng bị bỏ khỏi String đại diện cho dòng.

Ví dụ:

~~~text
Byte nội dung ASCII: A 
 B 
 
 C
Các dòng: ["A", "B", "", "C"]
~~~

Vì vậy:

- Một dòng **trống ở giữa file** là String rỗng hợp lệ, không phải EOF.
- Một file rỗng cho Stream không có dòng nào.
- Một file kết thúc bằng đúng một line terminator sau nội dung cuối **không nhất thiết tạo thêm một dòng rỗng cuối**; đừng suy count từ số ký tự xuống dòng một cách máy móc.
- Các dòng rất dài vẫn có thể khiến chương trình phải giữ một String dòng lớn trong bộ nhớ; “đọc lười” không loại bỏ giới hạn bộ nhớ cho từng dòng.
- Nếu file đang bị ghi/thay đổi đồng thời, **không giả định Files.lines cung cấp snapshot nhất quán**. Với tác vụ yêu cầu tính nhất quán, cần cơ chế snapshot/khóa hoặc thiết kế nguồn dữ liệu phù hợp.

**Phân biệt `String.lines()` với `Files.lines()`:** `String.lines()` tạo Stream từ một String đã ở trong bộ nhớ, không tự giữ file descriptor cần đóng. `Files.lines()` tạo Stream gắn với file bên ngoài; phải đóng để giải phóng tài nguyên. Hai API cùng trả Stream<String> nhưng **quyền sở hữu tài nguyên** khác nhau.

## 11. BufferedReader.lines() và vòng đời Reader

Một lựa chọn khác là mở `BufferedReader` rồi lấy Stream từ **`reader.lines()`**:

~~~java
// Mảnh code: path là Path, UTF_8 đã import.
try (java.io.BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines()
            .filter(s -> s.startsWith("ERROR"))
            .forEach(System.out::println);
}
~~~

Ở mẫu này **đối tượng cần đóng chính là BufferedReader** vì phương thức đã mở Reader và giữ ownership của nó. Đừng suy rằng chỉ gọi một terminal operation trên `reader.lines()` sẽ tự đóng Reader. Đặt Reader trong TWR bảo đảm close của Reader chạy khi rời scope.

Hai cách đều hợp lệ nhưng phải chọn đối tượng sở hữu rõ ràng:

- `Files.lines(path)`: tài nguyên do Stream từ Files.lines() quản lý; **đóng Stream**.
- `Files.newBufferedReader(path)` rồi `reader.lines()`: ứng dụng đã mở Reader; **đóng Reader**.
- Nếu bọc các lớp khác hoặc trả Stream ra ngoài, định nghĩa rõ tài nguyên gốc sẽ được đóng khi nào và bởi ai.

Không để Stream dựa trên Reader thoát khỏi scope nơi Reader đã bị đóng, vì lúc caller duyệt thì nguồn dữ liệu không còn sống.

## 12. Dùng parallel() có làm Files.lines luôn nhanh hơn không?

Stream hỗ trợ **`parallel()`**, nhưng thao tác I/O từ file không tự nhiên tăng tốc chỉ nhờ nhiều thread:

~~~java
// Mảnh code: có Path path và xử lý IOException.
try (Stream<String> lines = Files.lines(path)) {
    long n = lines.parallel()
            .filter(s -> s.contains("ERROR"))
            .count();
}
~~~

Cần cân nhắc:

- Chi phí đọc file và giải mã ký tự có thể là nút cổ chai; parallel không bảo đảm giảm thời gian.
- Khả năng chia công việc và cân bằng tải phụ thuộc charset và triển khai spliterator. Java có tối ưu cho một số charset có khả năng chia theo ranh giới dòng, nhưng không được suy rằng **mọi charset hay nguồn file đều split hiệu quả**.
- Các thao tác có side effect như ghi chung một file, tăng biến đếm mutable không đồng bộ hoặc in stdout từ nhiều thread có thể có vấn đề thứ tự và race condition.
- Với `findAny()` trong parallel, phần tử được tìm không nhất thiết là phần tử đầu tiên theo thứ tự file; nếu yêu cầu dòng đầu, hãy dùng `findFirst()` và hiểu chi phí duy trì thứ tự.

Hãy đo hiệu năng với dữ liệu thực trước khi chọn parallel. **Việc cần đóng Stream bằng try-with-resources không thay đổi khi pipeline chạy parallel.**

## 13. Quản lý tài nguyên trong ứng dụng dài hạn

Một chương trình CLI chạy xong ngay có thể khiến leak khó nhận ra. Nhưng trong server, worker, service hoặc tác vụ quét nhiều file:

~~~text
for each request:
    Files.lines(file)      -> mở tài nguyên
    findFirst()            -> đọc một phần
    không close()          -> tài nguyên có thể tích lũy
~~~

Hệ quả có thể là quá nhiều file descriptor mở, hạn chế mở file mới, tiêu tốn tài nguyên hệ điều hành, hoặc khó thay đổi/xóa file trên một số nền tảng. Vì vậy cần coi **vòng đời của Stream** là thành phần thiết kế, không phải bước tối ưu tùy chọn.

Một quy trình đúng:

1. Xác định file và charset của dữ liệu văn bản.
2. Mở Stream trong **try-with-resources** tại scope nhỏ nhất có thể.
3. Xây pipeline không có side effect khó kiểm soát; chọn terminal operation theo yêu cầu.
4. Không sử dụng lại Stream sau terminal operation và không trả Stream đã đóng.
5. Để TWR xử lý close ở mọi đường thoát; log/propagate lỗi mở, lỗi duyệt và lỗi cleanup theo chính sách.
6. Nếu chỉ cần thống kê, **trả kết quả đã tính** thay vì Stream sống.
7. Với số lượng file lớn, mở và đóng từng file theo scope, không giữ đồng thời hàng trăm Stream không cần thiết.

**Điểm nhấn:** không có “bảo đảm tự đóng” chỉ vì code đã gọi `count()`, `forEach()`, `findFirst()` hoặc `toList()`.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| `Files.lines(path).count()` không có TWR | Tài nguyên I/O có thể không được đóng kịp | TWR quanh Files.lines |
| Nghĩ Files.lines chỉ mở file khi terminal chạy | Bỏ qua lỗi mở và ownership của Stream | Hiểu file được mở khi Files.lines trả Stream |
| `findFirst()` rồi không close | Đọc dừng sớm nhưng file vẫn được giữ | Close Stream dù short-circuit |
| `limit(10)` nghĩa là tự release tài nguyên | Nhầm giới hạn phần tử với close | TWR độc lập với limit |
| Trả Stream ra khỏi TWR đã kết thúc | Caller nhận pipeline trên nguồn đã đóng | Tính kết quả tại chỗ hoặc chuyển ownership rõ |
| Dùng lại Stream sau `count()` | Có thể ném IllegalStateException | Mở Stream mới cho lượt duyệt mới |
| Dùng `toList()` cho file rất lớn và nghĩ không tốn RAM | List vẫn giữ nhiều dòng | Streaming aggregate/sink phù hợp |
| Coi `IOException` chỉ xảy ra lúc Files.lines() | Lỗi duyệt có thể thành UncheckedIOException | Bắt và truyền lỗi đúng giai đoạn |
| Lấy reader.lines() rồi quên đóng reader | Rò rỉ Reader gốc | TWR trên BufferedReader |
| Đọc file theo charset không đúng | Lỗi decoding/garbled text | Chỉ định charset phù hợp |
| Dùng Stream<String> để giữ byte binary | Có thể thay đổi byte do giải mã | Dùng byte stream |
| Giả định parallel luôn nhanh | Tăng overhead, race/khác thứ tự | Đo benchmark và giữ xử lý thread-safe |
| Thay đổi file trong khi Stream đang duyệt | Kết quả có thể không nhất quán | Dùng snapshot/đồng bộ khi cần |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `Files.lines(path)` có chờ `count()` mới mở file không?  
**Đáp án:** Không. Files.lines tạo Stream gắn với file khi gọi. Pipeline đọc các dòng theo nhu cầu khi được tiêu thụ, nhưng việc mở tài nguyên không phải chờ đến terminal operation.

**Câu 2.** Nếu dùng `findFirst()` đọc một dòng đầu, có cần close không?  
**Đáp án:** Có. Short-circuit chỉ dừng việc tiêu thụ phần tử, không tự giải phóng file.

**Câu 3.** `Files.lines(path).toList()` có luôn tiết kiệm RAM hơn `Files.readAllLines(path)` không?  
**Đáp án:** Không. Cả hai đều có thể tạo danh sách giữ toàn bộ dòng; nguồn lazy không đồng nghĩa kết quả đã collect là lazy.

**Câu 4.** Nếu một phương thức trả `Stream<String>` tạo từ Files.lines, ai phải đóng?  
**Đáp án:** Nếu muốn Stream còn dùng được sau khi trả về, caller phải nhận ownership và đóng bằng TWR hoặc close đúng lúc. API phải nói rõ contract đó.

**Câu 5.** Lỗi I/O khi đang duyệt sau khi Files.lines trả Stream có thể xuất hiện dưới dạng gì?  
**Đáp án:** `UncheckedIOException` bao bọc `IOException` gốc; lỗi mở file có thể là `IOException` ngay lúc Files.lines().

**Câu 6.** Hai lần gọi `count()` rồi `findFirst()` trên cùng một Stream có đúng không?  
**Đáp án:** Không. Một Stream chỉ được dùng cho một pipeline/terminal operation; phải mở Stream khác hoặc kết hợp yêu cầu trong một traversal.

**Câu 7.** Dùng `BufferedReader.lines()` trong một phương thức tự mở reader thì cần đóng đối tượng nào?  
**Đáp án:** `BufferedReader` mà phương thức mở, nên đặt trong TWR.

**Câu 8.** Vì sao File Stream lazy không bảo đảm bộ nhớ không tăng?  
**Đáp án:** Một dòng có thể rất dài và terminal operation như `toList()`, `groupingBy()` có thể giữ rất nhiều dữ liệu trong RAM.

## 16. Tài liệu Java SE 17

- [Files.lines(Path)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)): Stream dòng văn bản, lazy population, vòng đời file và close.
- [Files.lines(Path, Charset)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset)): lựa chọn charset và ngoại lệ.
- [BaseStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html): close, onClose và đặc tính dùng một lần.
- [BufferedReader.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#lines()): Stream dòng từ một Reader.
- [Files.readAllLines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#readAllLines(java.nio.file.Path)): đọc tất cả dòng vào List.

**Ghi nhớ:** `Files.lines()` cho phép xây pipeline Stream đọc các dòng theo nhu cầu, nhưng **mở tài nguyên file khi tạo Stream**. Mọi đường đi — đọc hết, dừng sớm, return hay exception — đều cần đóng Stream đúng lúc. Mẫu mặc định an toàn là **`try (Stream<String> lines = Files.lines(path, charset)) { ... }`**, và khi muốn chuyển Stream ra ngoài, phải chuyển luôn trách nhiệm đóng cho caller.
