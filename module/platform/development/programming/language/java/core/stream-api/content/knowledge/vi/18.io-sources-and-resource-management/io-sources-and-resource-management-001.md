# Đọc dòng văn bản bằng Files.lines và BufferedReader.lines

Java Stream API không chỉ xử lý dữ liệu đang có trong `List` hay mảng. Nhiều hệ thống cần duyệt nhật ký, tập tin CSV, báo cáo giao dịch hoặc dữ liệu cấu hình lưu trên đĩa. Hai cách tạo `Stream<String>` thường gặp là `Files.lines(...)` và `BufferedReader.lines()`. Cả hai đều cho phép mô tả pipeline khai báo bằng `filter`, `map`, `limit`, `reduce` và `collect`, nhưng khác nhau rõ rệt ở **cách mở nguồn** và **ai chịu trách nhiệm đóng tài nguyên**.

Bài học thuộc chương **Nguồn vào ra và quản lý tài nguyên** của module `JAVA_STREAM_API`. Trọng tâm là đọc dòng theo nhu cầu (*lazy*), lựa chọn bộ mã ký tự, phân biệt ngoại lệ lúc mở tệp với lỗi xảy ra khi duyệt Stream, kết hợp với các thao tác terminal, và thiết kế mã không rò rỉ tài nguyên khi dừng sớm hay phát sinh lỗi. Hiểu đúng vòng đời nguồn I/O là tiền đề quan trọng trước khi tối ưu hiệu năng hoặc xử lý song song.

Các ví dụ dưới đây sử dụng API có từ **Java 8**. Một số đoạn mã là ví dụ phương thức hoàn chỉnh, một số đoạn sử dụng biến `path` hoặc `reader` đã tạo ở phần trước.

## 1. Hai cách tạo Stream<String> từ dòng văn bản

### Files.lines: từ đường dẫn tệp

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
```

`Files.lines(path, charset)` mở một nguồn đọc tệp và trả về `Stream<String>`. `Files.lines(path)` là overload mặc định sử dụng **UTF-8**. Dữ liệu được cung cấp cho Stream theo nhu cầu khi terminal operation chạy, thay vì bắt buộc nạp toàn bộ tệp thành danh sách ngay lúc tạo Stream.

Với nguồn này, **Stream trả về là tài nguyên cần đóng**. `try-with-resources` gọi `close()` ngay cả khi pipeline ném ngoại lệ hoặc dừng sau một `limit` hay `findFirst`.

### BufferedReader.lines: từ một Reader đã mở

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static long countNonBlankLines(Path path) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> !line.trim().isEmpty())
                .count();
    }
}
```

`BufferedReader.lines()` tạo Stream dựa trên **một BufferedReader đã tồn tại**. Khi `Files.newBufferedReader` được dùng để tạo reader, nó cũng mở tài nguyên I/O. `try-with-resources` ở đây phải **đóng chính reader**, không được giả định việc gọi `count()` hay đóng Stream do `reader.lines()` tạo sẽ tự đóng reader.

Hai mẫu trên cùng xử lý dữ liệu theo dòng nhưng có **đối tượng sở hữu tài nguyên khác nhau**.

## 2. Bảng so sánh nhanh

| Khía cạnh | `Files.lines(...)` | `BufferedReader.lines()` |
| --- | --- | --- |
| Đầu vào | `Path` tới tệp | `BufferedReader` đã mở |
| Đối tượng mở nguồn | Phương thức `Files.lines` | Mã tạo `BufferedReader`, chẳng hạn `Files.newBufferedReader` |
| Kết quả | `Stream<String>` | `Stream<String>` |
| Thời điểm đọc dòng | Khi pipeline được tiêu thụ | Khi pipeline được tiêu thụ |
| Bộ mã ký tự | `Files.lines(path, charset)` hoặc UTF-8 mặc định | Được chọn khi xây Reader |
| Cần đóng | **Stream** do `Files.lines` trả về | **BufferedReader** làm nguồn |
| Thường đóng thế nào | `try (Stream<String> lines = Files.lines(...))` | `try (BufferedReader reader = ...)` |
| Ngoại lệ khi mở nguồn | `IOException` | `IOException` khi mở Reader |
| Ngoại lệ I/O lúc duyệt | Có thể là `UncheckedIOException` | Có thể là `UncheckedIOException` |
| Khả năng dùng song song | Tùy đặc tính nguồn, charset, thao tác | Không nên giả định đọc Reader được phân tách hiệu quả |
| Trường hợp phù hợp | Đọc trực tiếp từ tệp theo đường dẫn | Đã có Reader, cần kiểm soát cấu hình hoặc tích hợp API Reader |

Điểm dễ sai nhất: **đóng Stream từ `reader.lines()` không thay thế việc đóng `reader`**. Và ngược lại, nếu nhận `Stream` trực tiếp từ `Files.lines`, người sở hữu Stream đó phải đóng nó.

## 3. Lazy I/O: khai báo pipeline chưa đồng nghĩa đã đọc hết tệp

Stream có các thao tác trung gian (*intermediate operations*) như `filter`, `map`, `peek`, `limit`. Việc lắp ghép các bước này thường chưa chạy lambda; thao tác kết thúc (*terminal operation*) như `count`, `collect`, `findFirst` hoặc `forEach` mới kích hoạt việc tiêu thụ.

```text
Path
  |
  +-- Files.lines(path, UTF_8) -> Stream<String>
                                     |
                                     +-- filter(...)
                                     |
                                     +-- map(...)
                                     |
                                     +-- limit(10)
                                     |
                                     +-- collect(...)  [terminal]
                                     |
                                     v
                                List<String>
```

Ví dụ chỉ cần năm dòng đầu:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readFirstFive(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.limit(5).collect(Collectors.toList());
    }
}
```

`limit(5)` khiến pipeline có thể hoàn thành sau khi nhận đủ năm dòng, không cần chủ động biến toàn bộ tệp thành danh sách. Tuy nhiên:

- `Files.lines` **đã mở tài nguyên** ngay khi được gọi; “lazy” ở đây nói về việc **cung cấp dòng**, không phải cam kết tệp chưa mở.
- Không được suy ra số lần đọc vật lý từ số phần tử trả ra: buffering, decoder và implementation có thể đọc trước dữ liệu.
- `try-with-resources` vẫn cần thiết ngay cả khi chỉ lấy một dòng.
- Nếu `limit(0)` hoặc một thao tác khác khiến pipeline không cần lấy phần tử, nguồn đã mở vẫn phải đóng.

Đừng dùng `peek` để xây logic nghiệp vụ buộc phải thực thi cho mọi dòng. Tùy cấu trúc pipeline và tối ưu, không phải mọi phần tử đều bắt buộc đi qua `peek` trước khi terminal trả về.

## 4. Dòng văn bản được tách và trả về như thế nào?

Với hai API, mỗi phần tử trong Stream là **nội dung một dòng văn bản**, không bao gồm ký tự kết thúc dòng. Các dấu kết thúc thông dụng được nhận diện gồm:

- `\n` (line feed);
- `\r` (carriage return);
- `\r\n` (carriage return rồi line feed).

Ví dụ một tệp có nội dung tương đương:

```text
alpha
beta
gamma
```

Stream có thể lần lượt phát ra `"alpha"`, `"beta"`, `"gamma"`. Không cần gọi `split("\n")` cho từng phần tử nữa.

Dòng trống vẫn có thể tạo một chuỗi rỗng và không nên mặc định bị bỏ. Nếu một dòng chỉ chứa khoảng trắng, `line.isEmpty()` trả `false`; có thể dùng:

```java
.filter(line -> !line.trim().isEmpty())
```

`trim()` tồn tại từ Java 8 và loại khoảng trắng ở hai đầu theo quy tắc của nó; không phải giải pháp chuẩn hóa đầy đủ mọi ký tự khoảng trắng Unicode. Từ Java 11 có `String.isBlank()` và `String.strip()`, nhưng không thể dùng các phương thức đó nếu dự án chỉ biên dịch với Java 8.

Nếu dữ liệu là CSV với dấu ngoặc kép, dấu phẩy nằm trong ô, hoặc một ô văn bản chứa ký tự xuống dòng, **một dòng vật lý không nhất thiết tương ứng một bản ghi CSV**. `Files.lines` và `BufferedReader.lines` chỉ cung cấp dòng văn bản, không phải parser CSV hoàn chỉnh.

## 5. Charset: đọc đúng byte thành ký tự

Tệp lưu **byte**, Stream trả về **chuỗi ký tự**. Vì thế cần dùng bộ mã ký tự phù hợp với dữ liệu được lưu.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEachOrdered(System.out::println);
}
```

Tương đương về việc chọn charset với Reader:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines().forEachOrdered(System.out::println);
}
```

Chọn charset là một **quyết định về định dạng tệp**, không phải tùy chọn để “sửa lỗi font” bằng cách thử đại. Một tệp tiếng Việt lưu UTF-8 nên được giải mã UTF-8; nếu tệp thật sự dùng bộ mã cũ, cần xác định chính xác charset trước khi phân tích dữ liệu.

Với charset không tương thích, việc giải mã có thể thất bại với ngoại lệ I/O (có thể bị bọc trong `UncheckedIOException` khi đang duyệt), hoặc cho kết quả sai nếu các byte vẫn tạo chuỗi hợp lệ nhưng không đúng ý nghĩa. Không nên bắt mọi lỗi giải mã rồi âm thầm bỏ dòng; làm vậy có thể khiến thống kê thiếu dữ liệu.

**BOM (byte-order mark)** và các ký tự điều khiển khác là một phần của dữ liệu/định dạng cần xử lý theo quy định của nguồn. Đừng giả định mọi tệp UTF-8 đều có BOM, hoặc mọi cách đọc dòng đều tự xóa BOM ở đầu tệp. Nếu hệ thống phải nhận nhiều định dạng, nên xây một bước xác thực và chuẩn hóa đầu vào rõ ràng.

## 6. Khác biệt vòng đời quan trọng nhất: ai đóng gì?

### 6.1. Files.lines: đóng Stream được trả về

```java
static long countErrors(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

Đây là mẫu **đúng**: Stream được mở trong phạm vi `try` và được đóng sau khi tính toán, kể cả khi `filter` hoặc `count` thất bại.

Mẫu **sai**:

```java
// SAI: stream từ Files.lines có thể giữ tài nguyên chưa được đóng.
static long countErrorsLeaky(Path path) throws IOException {
    return Files.lines(path)
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
```

`count()` tiêu thụ pipeline nhưng **không tự gọi `Stream.close()`**. Tương tự, `collect`, `findFirst` và `forEach` không tự động đóng tài nguyên nguồn.

### 6.2. BufferedReader.lines: đóng Reader

```java
static long countErrorsWithReader(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.lines()
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

Ở đây `reader.lines()` trả một Stream đọc từ trạng thái của `BufferedReader`. Đóng Reader bằng `try-with-resources` là thao tác giải phóng tài nguyên được yêu cầu.

Mẫu **sai**:

```java
// SAI: đóng Stream này không thay thế đóng BufferedReader.
static long countErrorsWrongClose(Path path) throws IOException {
    BufferedReader reader = Files.newBufferedReader(path);
    try (Stream<String> lines = reader.lines()) {
        return lines.filter(s -> s.startsWith("ERROR")).count();
    }
}
```

Khi `reader.lines()` không gắn một close handler riêng cho Reader, `lines.close()` không tự gọi `reader.close()`. Vì vậy tài nguyên underlying Reader có thể bị giữ mở.

Nếu muốn sở hữu cả `BufferedReader` và một Stream con trong cùng khối, có thể viết:

```java
try (BufferedReader reader = Files.newBufferedReader(path);
     Stream<String> lines = reader.lines()) {
    // xử lý lines...
}
```

Nhưng Reader mới là tài nguyên quan trọng phải đóng; khai báo thêm Stream không làm thay đổi quyền sở hữu đó. Java đóng tài nguyên trong danh sách `try` **theo thứ tự ngược lại**: `lines` rồi `reader`.

### 6.3. Nếu Reader do nơi khác truyền vào

Không phải mọi phương thức nhận `BufferedReader` đều nên tự đóng Reader. Ví dụ:

```java
// Hợp đồng minh họa: phương thức KHÔNG sở hữu reader được truyền vào.
static long countWarnings(BufferedReader reader) {
    return reader.lines()
            .filter(line -> line.startsWith("WARN"))
            .count();
}
```

Hàm trên không mở Reader và không đóng nó. Nơi tạo Reader nên quản lý vòng đời bên ngoài:

```java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    long totalWarnings = countWarnings(reader);
    System.out.println(totalWarnings);
}
```

Thiết kế API cần ghi rõ **ai mở, ai đóng, ai được phép đọc**, đặc biệt khi nhiều hàm dùng cùng một đối tượng Reader. Không được đồng thời gọi `readLine()` hay một pipeline `lines()` khác trên cùng Reader trong lúc terminal operation đang đọc. Sau khi một terminal operation của `BufferedReader.lines()` kết thúc, API cũng không bảo đảm Reader đã ở một vị trí cụ thể thuận tiện cho lượt đọc tiếp theo.

## 7. Trả Stream từ phương thức: vấn đề chuyển quyền sở hữu

Một phương thức trả `Stream<String>` từ `Files.lines` không nhất thiết sai, nhưng **chuyển trách nhiệm đóng sang người gọi**.

```java
// Caller PHẢI đóng Stream trả về.
static Stream<String> openTextLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

static void printFirstLine(Path path) throws IOException {
    try (Stream<String> lines = openTextLines(path)) {
        lines.findFirst().ifPresent(System.out::println);
    }
}
```

Nếu caller bỏ quên `try-with-resources`, tệp có thể bị giữ mở. Một API công khai trả Stream I/O nên ghi rõ vòng đời và điều kiện sử dụng một lần.

**Không trả Stream từ Reader đã đóng:**

```java
// SAI: Reader bị đóng trước khi caller tiêu thụ Stream lazy.
static Stream<String> brokenLines(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.lines();
    }
}
```

Khi caller chạy terminal operation, `reader` đã hết vòng đời nên việc đọc có thể thất bại.

Với một phương thức chỉ cần trả kết quả tổng hợp hoặc một tập nhỏ dữ liệu, thường dễ quản lý hơn nếu **tiêu thụ Stream ngay bên trong `try`** rồi trả kết quả đã tính:

```java
static java.util.List<String> firstTenValidLines(Path path)
        throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .limit(10)
                .collect(java.util.stream.Collectors.toList());
    }
}
```

Phương thức này trả `List<String>` đã vật chất hóa, không còn phụ thuộc vào tài nguyên mở. Tất nhiên, nếu định đọc toàn bộ một tệp rất lớn vào List, chi phí bộ nhớ có thể cao; cần cân nhắc giữa API an toàn và nhu cầu streaming.

## 8. Xử lý ngoại lệ ở lúc mở và lúc duyệt

Có hai thời điểm lỗi thường xảy ra:

| Thời điểm | Ví dụ | Kiểu ngoại lệ cần chú ý |
| --- | --- | --- |
| Mở nguồn | Tệp không tồn tại, không có quyền đọc, đường dẫn sai | `IOException` hoặc lớp con |
| Tiêu thụ Stream | I/O thất bại trong khi đang lấy dòng kế tiếp | `UncheckedIOException` (bọc `IOException`) |
| Biến đổi nội dung | `Integer.parseInt("abc")` | `NumberFormatException`, không phải `UncheckedIOException` |
| Code của caller | Predicate ném `IllegalArgumentException` | Ngoại lệ từ logic ứng dụng |
| Đóng tài nguyên | Reader hoặc Stream close thất bại | Có thể là `IOException` hoặc ngoại lệ phù hợp với tài nguyên |

Ví dụ phân biệt lỗi đọc tệp với lỗi định dạng dữ liệu:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long sumNumberLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .mapToLong(Long::parseLong)
                .sum();
    } catch (UncheckedIOException ex) {
        throw ex.getCause(); // chuyển lại lỗi đọc thành IOException
    }
}
```

Các hành vi đáng chú ý:

- Lỗi tại `Files.lines(...)` có thể ném trực tiếp `IOException`.
- Lỗi đọc khi terminal `sum()` duyệt nguồn có thể ném `UncheckedIOException`; ví dụ đổi về `IOException` để caller xử lý theo hợp đồng phương thức.
- Dòng `"abc"` ném `NumberFormatException`. Hàm trên **không** tự bỏ dòng sai: nếu cần bỏ, ghi nhận hoặc dừng khi lỗi định dạng, hãy quy định rõ.
- Khối `try-with-resources` đóng Stream trong cả trường hợp bình thường và lỗi. Nếu thao tác chính và việc đóng cùng gây lỗi, Java dùng cơ chế *suppressed exceptions* để giữ thông tin đóng thất bại cùng ngoại lệ chính.

Không nên dùng `catch (Exception ex) { return 0; }` cho tác vụ thống kê. Làm vậy khiến tệp đọc hỏng hoặc dữ liệu bẩn trông giống một tệp hợp lệ có tổng bằng 0.

### Đọc dòng lỗi nhưng vẫn muốn tiếp tục

Nếu yêu cầu là chấp nhận các dòng số hợp lệ và bỏ qua những dòng không phân tích được, có thể định nghĩa một hàm trả `OptionalLong`. Với Java 9+, `OptionalLong.stream()` cho phép làm phẳng trực tiếp; Java 8 cần cách khác.

Một phương án Java 8, chỉ để minh họa logic nghiệp vụ:

```java
import java.util.OptionalLong;

static OptionalLong parseLongSafely(String line) {
    try {
        return OptionalLong.of(Long.parseLong(line.trim()));
    } catch (NumberFormatException ex) {
        return OptionalLong.empty();
    }
}
```

Tuy nhiên, việc chuyển tất cả dòng sai thành `OptionalLong.empty()` có thể làm **mất dấu vết dữ liệu hỏng**. Nếu cần kiểm toán, hãy giữ số dòng, nội dung lỗi và số lượng dòng bị bỏ bằng một mô hình kết quả tường minh, không đặt side effect rời rạc trong `peek`.

## 9. Ví dụ thực tế: đọc log, lọc và thống kê lỗi

Giả sử tệp log gồm các dòng như:

```text
INFO start
WARN low-memory
ERROR connection-failed
ERROR request-timeout
INFO stop
```

Nhiệm vụ: đếm các dòng bắt đầu bằng `"ERROR "` và trích tối đa năm thông điệp lỗi đầu tiên.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> firstFiveErrors(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.startsWith("ERROR "))
                .map(line -> line.substring("ERROR ".length()))
                .limit(5)
                .collect(Collectors.toList());
    }
}
```

Các bước có ý nghĩa riêng:

1. `Files.lines` mở tệp và tạo nguồn Stream các dòng.
2. `filter` giữ dòng bắt đầu bằng tiền tố lỗi. Kiểm tra này không đòi hỏi tải toàn tệp vào một List.
3. `map` chỉ lấy thông điệp sau tiền tố.
4. `limit(5)` giữ tối đa năm **dòng lỗi**, không phải năm dòng đầu của toàn tệp.
5. `collect` kích hoạt pipeline; `try` luôn đóng nguồn sau đó.

Nếu đổi thành `lines.limit(5).filter(...)`, ta đang xem năm dòng **đầu tệp**, có thể nhận ít hơn năm lỗi ngay cả khi phía sau còn nhiều lỗi. Thứ tự thao tác là một phần của ý nghĩa thống kê.

Để chỉ đếm lỗi, có thể dùng `filter(...).count()`; để nhóm lỗi theo mã, có thể dùng `Collectors.groupingBy` với classifier phù hợp. Những collector đó giúp giảm việc giữ toàn bộ bản ghi khi chỉ cần số lượng theo nhóm, nhưng Map vẫn tiêu tốn bộ nhớ theo số khóa khác nhau.

## 10. Ví dụ thực tế: đọc CSV đơn giản theo dòng

Giả sử tệp văn bản có dạng đơn giản mỗi dòng là `mã,giá_trị`, không có dấu phẩy được trích dẫn và không có bản ghi trải qua nhiều dòng:

```text
C01,10
C02,20
C01,5
```

Ta muốn tính tổng theo mã:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> totalsByCode(Path path)
        throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> !line.trim().isEmpty())
                .map(line -> line.split(",", -1))
                .collect(Collectors.toMap(
                        parts -> parts[0].trim(),
                        parts -> Long.parseLong(parts[1].trim()),
                        Long::sum
                ));
    }
}
```

Ví dụ cố ý giả định **mọi dòng không rỗng đều có đúng hai cột**, mã không rỗng và cột thứ hai là số nguyên hợp lệ. Nếu một dòng thiếu cột, `parts[1]` gây `ArrayIndexOutOfBoundsException`; nếu giá trị không phải số, `parseLong` gây `NumberFormatException`. Trong chương trình thật, nên có bước xác thực số cột, mã, khả năng tràn số và chính sách báo lỗi theo số dòng.

`Long::sum` cho phép cộng khi cùng mã xuất hiện nhiều lần; việc `toMap` cần merge function là độc lập với việc dữ liệu đang được đọc bằng `Files.lines` hay từ `BufferedReader.lines`.

Đây **không phải parser CSV đầy đủ**. Khi dữ liệu có dấu phẩy trong chuỗi trích dẫn, ký tự escape, hoặc trường nhiều dòng, nên dùng parser CSV tuân thủ định dạng thay vì `String.split`.

## 11. Có nên chuyển nguồn I/O sang parallel stream?

Cú pháp cho phép:

```java
try (Stream<String> lines = Files.lines(path)) {
    long matches = lines
            .parallel()
            .filter(line -> expensivePureCheck(line))
            .count();
}
```

Đoạn trên là **phác thảo**; `expensivePureCheck` đại diện cho một hàm kiểm tra thuần, không tác dụng phụ và do ứng dụng cung cấp.

Khả năng tăng tốc phụ thuộc vào nhiều điều kiện:

- Việc đọc từ đĩa hoặc giải mã có phải nút thắt không?
- Nguồn Stream có thể chia việc hiệu quả không? Đặc điểm `Spliterator` phụ thuộc implementation và charset.
- Phép biến đổi có đủ tốn CPU để bù chi phí chia/gộp không?
- Kết quả có cần encounter order không? Các phép như `findFirst`, `forEachOrdered` và thu thập có thứ tự có thể phát sinh chi phí phối hợp.
- Có chia sẻ Reader hoặc một đối tượng mutable giữa các lambda không? Nếu có, nguy cơ tranh chấp và lỗi thứ tự tăng lên.

Không giả định `BufferedReader.lines().parallel()` có thể đọc các phần của một Reader độc lập như nhiều tệp riêng. `BufferedReader` là một luồng đọc có trạng thái; các thao tác đồng thời trực tiếp lên cùng Reader không phải chiến lược an toàn để tăng tốc.

Trong nhiều ứng dụng, cách đơn giản và dễ kiểm soát hơn là **đọc tuần tự, xử lý từng dòng nhẹ, chỉ đưa công việc CPU nặng sang một pipeline hoặc hàng đợi có thiết kế rõ ràng**. Nhưng không nên khẳng định luôn nhanh hơn; nếu cần tối ưu, phải đo trên kích thước tệp, thiết bị, charset và JDK thực tế.

## 12. Giới hạn bộ nhớ: streaming không đồng nghĩa không dùng bộ nhớ

`Files.lines` và `BufferedReader.lines` giúp tránh đọc tất cả dòng thành `List` ngay từ đầu, nhưng các thao tác downstream vẫn có thể làm bộ nhớ tăng đáng kể.

| Pipeline | Đặc điểm bộ nhớ |
| --- | --- |
| `filter(...).count()` | Không phải giữ tất cả phần tử đã lọc |
| `mapToLong(...).sum()` | Giữ kết quả tổng hợp nhỏ, không giữ mọi dòng |
| `limit(10).collect(toList())` | Chỉ giữ tối đa 10 chuỗi đầu ra (không tính buffering của nguồn) |
| `collect(toList())` trên toàn bộ tệp | Có thể giữ tất cả dòng trong bộ nhớ |
| `sorted().collect(toList())` | Có thể cần bộ đệm và danh sách lớn |
| `distinct().count()` | Có thể phải lưu tập khóa đã gặp |
| `groupingBy(..., counting())` | Giữ trạng thái theo số nhóm |
| `groupingBy(...)` mặc định | Lưu các dòng/bản ghi vào danh sách của từng nhóm |

Với tệp rất lớn, `Files.readAllLines(path)` đọc toàn bộ nội dung thành List và thường không phải lựa chọn phù hợp khi chỉ cần đếm, lọc vài dòng hoặc tổng hợp trực tiếp.

Tuy nhiên, với tệp nhỏ, `readAllLines` có thể đủ đơn giản và vẫn chính xác; chọn API theo nhu cầu, không theo một khẩu hiệu tối ưu. Tài nguyên I/O vẫn cần được đóng đối với nguồn Stream giữ tệp, cho dù pipeline đầu ra rất nhỏ.

## 13. Bẫy thường gặp khi làm việc với Stream từ Reader

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| `Files.lines(path).count()` mà không đóng Stream | Terminal operation không tự đóng tệp | `try (Stream<String> lines = Files.lines(path))` |
| `try (Stream<String> lines = reader.lines())` nhưng không đóng reader | Stream từ Reader không tự sở hữu Reader | `try (BufferedReader reader = ...)` |
| Trả `reader.lines()` từ khối `try (BufferedReader reader = ...)` | Reader đóng trước khi Stream lazy được duyệt | Trả kết quả đã tính, hoặc chuyển quyền sở hữu rõ ràng |
| Cho rằng `Files.lines` đọc hết tệp lúc gọi | Đọc dữ liệu theo nhu cầu, tài nguyên được mở trước | Hiểu lazy traversal và quản lý thời gian mở |
| Đọc tiếp `reader.readLine()` trong lúc Stream đang được tiêu thụ | Can thiệp trạng thái Reader, hành vi không được bảo đảm | Một bên duyệt dữ liệu tại một thời điểm, theo hợp đồng |
| Dùng lại Stream sau `count` hoặc `collect` | Stream chỉ dùng một lần | Tạo nguồn mới nếu cần lượt xử lý khác |
| Giả định `limit(5)` đóng nguồn sau năm dòng | Short circuit không thay thế `close()` | Đóng nguồn ngay cả khi dừng sớm |
| Bắt mọi `Exception` rồi trả danh sách rỗng | Che giấu tệp lỗi/giải mã lỗi/parse lỗi | Phân loại và truyền lỗi có ngữ cảnh |
| Không xác định charset khi nguồn không phải UTF-8 | Ký tự có thể bị giải mã sai | Chọn charset theo hợp đồng nguồn |
| `map(String::trim)` rồi xem là parser CSV | Không xử lý quoting, nhiều dòng, escape | Parser chuyên dụng khi dữ liệu phức tạp |
| `collect(toList())` toàn bộ tệp lớn và kỳ vọng ít dùng RAM | Output vẫn chứa toàn bộ dữ liệu | Tổng hợp streaming hoặc giới hạn đầu ra |
| Tự ý dùng `parallel()` với Reader dùng chung | Không bảo đảm khả năng chia nguồn và an toàn trạng thái | Đo thực tế, tránh chia sẻ trạng thái |
| `forEach` trên parallel và kỳ vọng thứ tự tệp | `forEach` không giữ encounter order | `forEachOrdered` nếu cần đúng thứ tự |

## 14. Checklist khi thiết kế API đọc dòng

Trước khi đưa một pipeline xử lý tệp vào ứng dụng, hãy trả lời:

1. **Nguồn nào phù hợp?** Có `Path` trực tiếp thì `Files.lines` thường gọn; đã có Reader do hệ thống sở hữu thì dùng `BufferedReader.lines`.
2. **Ai mở và ai đóng?** `Files.lines` → đóng Stream; `BufferedReader.lines` → đóng Reader. Ghi rõ hợp đồng nếu truyền/trả nguồn.
3. **Charset nào đúng?** Theo định dạng và hợp đồng bên cung cấp dữ liệu.
4. **Làm gì với dòng trống, dòng sai định dạng?** Lọc có chủ ý, ghi nhận lỗi hoặc dừng; tránh bỏ qua âm thầm.
5. **Có cần bảo toàn thứ tự dòng?** Nếu có, giữ encounter order và cẩn trọng với parallel, `unordered`, `forEach`.
6. **Có thể dừng sớm không?** `limit`, `findFirst` và `anyMatch` có thể giúp tránh xử lý toàn bộ, nhưng không tự đóng nguồn.
7. **Kết quả có chiếm nhiều bộ nhớ không?** `collect(toList())`, `sorted`, `distinct` và grouping có bộ nhớ tăng theo dữ liệu.
8. **Lỗi nào có thể phát sinh lúc duyệt?** Ngoài `IOException` khi mở, xem `UncheckedIOException` và lỗi parser/predicate.
9. **Có cần truyền Stream ra ngoài phương thức không?** Nếu có, người gọi cần biết rằng nó là tài nguyên một lần và phải đóng.
10. **Đã kiểm tra trường hợp nguồn rỗng và lỗi ở giữa tệp chưa?** Đặc biệt nếu hàm báo cáo trả về một tổng hoặc danh sách có thể bị nhầm với kết quả hợp lệ rỗng.

## 15. Câu hỏi tự kiểm tra

1. `Files.lines(path)` có dùng UTF-8 mặc định không? **Có**, overload không nhận charset sử dụng UTF-8.
2. `BufferedReader.lines()` tự mở một tệp theo Path không? **Không**, nó tạo Stream từ Reader đã tồn tại.
3. Trong `try (Stream<String> lines = Files.lines(path))`, tài nguyên nào được đóng? **Stream** được trả về, qua đó đóng nguồn tệp của nó.
4. `try (Stream<String> lines = reader.lines())` có tự đóng Reader không? **Không**; cần đóng Reader do mình sở hữu.
5. `count()`, `findFirst()` hoặc `collect()` có tự gọi `close()` không? **Không**.
6. Tại sao `limit(5)` vẫn cần `try-with-resources`? **Vì** nguồn có thể đã được mở và short circuit không tự đóng nguồn.
7. Ngoại lệ mở tệp và ngoại lệ đọc trong khi duyệt Stream có thể khác nhau thế nào? **IOException** khi mở, **UncheckedIOException** khi đọc lazy.
8. Nếu `Long.parseLong("abc")` lỗi, đó có phải `UncheckedIOException` không? **Không**, đó là `NumberFormatException`.
9. Khi đọc dòng văn bản, dấu `\n` có nằm trong chuỗi dòng được trả về không? **Không**, dấu kết thúc dòng không thuộc nội dung dòng.
10. Khi chỉ cần đếm các dòng lỗi trong tệp lớn, có cần `collect(toList())` không? **Không**, dùng `filter(...).count()` để tránh lưu tất cả dòng.
11. Tại sao `BufferedReader.lines()` không được dùng cùng lúc với `reader.readLine()`? **Vì** chúng cùng thay đổi trạng thái Reader và làm mất hợp đồng duyệt.
12. Một hàm trả Stream từ `Files.lines` mà không đóng có luôn sai không? **Không**, nếu hợp đồng nói rõ caller phải đóng và caller thực hiện đúng.
13. `Files.lines` có phải một CSV parser hỗ trợ ô có xuống dòng không? **Không**, nó chỉ tách dòng văn bản.
14. Có thể bật `parallel()` để mặc nhiên đọc tệp nhanh hơn không? **Không**, hiệu quả phụ thuộc nguồn, charset, CPU, bộ nhớ và chi phí phối hợp.

**Nguyên tắc áp dụng:** `Files.lines` và `BufferedReader.lines` đều giúp đưa dòng văn bản vào pipeline Stream lazy, nhưng **quyền sở hữu tài nguyên không giống nhau**. Hãy đóng Stream do `Files.lines` mở, đóng `BufferedReader` khi dùng `reader.lines()`, tiêu thụ pipeline trong phạm vi nguồn còn mở, kiểm soát charset và phân biệt lỗi I/O với lỗi dữ liệu. Tối ưu `limit`, `collect` hoặc parallel chỉ có giá trị khi vẫn đảm bảo kết quả đúng và tài nguyên luôn được giải phóng.
