# Files.readAllLines() và Files.lines(): chọn charset và đóng Stream đọc tệp đúng vòng đời

## 1. Hai cách đọc file theo dòng, hai mô hình xử lý khác nhau

`Files.readAllLines()` và `Files.lines()` đều thuộc `java.nio.file.Files`, đều đọc văn bản từ một `Path` theo từng dòng, và đều có overload cho phép truyền `Charset`. Tuy nhiên, cách chúng sử dụng bộ nhớ và quản lý tài nguyên khác nhau:

- `Files.readAllLines(path)` đọc toàn bộ file, trả về `List<String>` chứa các dòng. File được đóng trước khi phương thức trả kết quả.
- `Files.lines(path)` trả về `Stream<String>` được tiêu thụ lười. File vẫn mở trong khi stream đọc dữ liệu và phải được đóng sau khi xử lý.

Cả hai API đều dùng **UTF-8 theo hợp đồng** nếu gọi overload không truyền charset. Hành vi này đã tồn tại từ Java 8, trước khi Java 18 đưa UTF-8 thành default charset thông thường theo JEP 400.

```text
Files.readAllLines(path, charset)
       |
       | đọc hết file trước khi trả về
       v
   List<String>
       |
       v
  xử lý danh sách

Files.lines(path, charset)
       |
       | mở file, chưa đọc hết ngay
       v
   Stream<String>
       |
       | terminal operation tiêu thụ dần
       v
  xử lý từng dòng
       |
       | close stream
       v
  đóng tài nguyên file
```

Sau bài này, bạn có thể chọn mô hình phù hợp với kích thước file, xác định charset theo định dạng nguồn, xử lý lỗi đọc đúng loại, và đảm bảo stream không giữ file handle ngoài ý muốn.

## 2. Các overload và charset

### 2.1. `Files.readAllLines`

Các overload chính:

```java
List<String> readAllLines(Path path)
List<String> readAllLines(Path path, Charset cs)
```

| Cách gọi | Charset giải mã |
| --- | --- |
| `Files.readAllLines(path)` | UTF-8 theo hợp đồng API |
| `Files.readAllLines(path, StandardCharsets.UTF_8)` | UTF-8 tường minh |
| `Files.readAllLines(path, StandardCharsets.ISO_8859_1)` | ISO-8859-1 |
| `Files.readAllLines(path, charset)` | Charset được truyền |

### 2.2. `Files.lines`

Các overload chính:

```java
Stream<String> lines(Path path)
Stream<String> lines(Path path, Charset cs)
```

| Cách gọi | Charset giải mã |
| --- | --- |
| `Files.lines(path)` | UTF-8 theo hợp đồng API |
| `Files.lines(path, StandardCharsets.UTF_8)` | UTF-8 tường minh |
| `Files.lines(path, StandardCharsets.ISO_8859_1)` | ISO-8859-1 |
| `Files.lines(path, charset)` | Charset được truyền |

Các API này đã có từ Java 8 và vẫn còn dùng được trên các JDK hiện đại. Nếu file được tạo theo một charset cụ thể, truyền charset đó ở cả hai API. Đừng dùng charset mặc định của máy để đoán định dạng file.

## 3. UTF-8 theo hợp đồng Files API không phải default charset của JVM

JEP 400 thay đổi default charset thông thường của Java SE từ Java 18. Những API thật sự sử dụng `Charset.defaultCharset()` có thể chịu ảnh hưởng của cấu hình chạy, ví dụ chế độ tương thích mà JDK hỗ trợ.

`Files.readAllLines(path)` và `Files.lines(path)` lại có quy định UTF-8 riêng trong Javadoc. Chúng không lấy charset từ `Charset.defaultCharset()`.

Có thể phân biệt bằng bảng sau:

| API | Charset khi không truyền charset |
| --- | --- |
| `Files.readAllLines(path)` | UTF-8 theo hợp đồng Files API |
| `Files.lines(path)` | UTF-8 theo hợp đồng Files API |
| `Files.readString(path)` | UTF-8 theo hợp đồng Files API |
| `Files.newBufferedReader(path)` | UTF-8 theo hợp đồng Files API |
| `new String(bytes)` | `Charset.defaultCharset()` |
| `text.getBytes()` | `Charset.defaultCharset()` |
| `new InputStreamReader(input)` | `Charset.defaultCharset()` |

Vì vậy, không thể áp dụng quy tắc “không truyền charset thì dùng default JVM” cho mọi API Java. Hãy kiểm tra hợp đồng của đúng overload.

Ví dụ, nếu file đối tác được quy định là ISO-8859-1:

```java
List<String> rows = Files.readAllLines(
        path, StandardCharsets.ISO_8859_1);

try (Stream<String> rowsStream = Files.lines(
        path, StandardCharsets.ISO_8859_1)) {
    rowsStream.forEach(System.out::println);
}
```

Nếu định dạng là UTF-8, có thể dùng overload không charset hoặc ghi rõ `StandardCharsets.UTF_8` để ý định dễ đọc hơn. Với hệ thống tích hợp, ghi rõ charset thường giúp người bảo trì hiểu hợp đồng dữ liệu ngay tại chỗ mở file.

## 4. `Files.readAllLines`: đọc toàn bộ file thành List

Ví dụ cơ bản:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

Path path = Path.of("users.txt");

try {
    List<String> lines = Files.readAllLines(path);
    for (String line : lines) {
        process(line);
    }
} catch (IOException e) {
    // Lỗi mở/đọc file hoặc dữ liệu không hợp lệ theo UTF-8.
    throw new IllegalStateException("Không đọc được users.txt", e);
}
```

Khi phương thức trả về thành công, toàn bộ dòng đã được đọc và file đã được đóng. Bạn không phải gọi `close()` trên `List<String>`.

`readAllLines` phù hợp khi:

- File có kích thước vừa phải.
- Số lượng dòng và nội dung có thể giữ an toàn trong heap.
- Cần truy cập danh sách nhiều lần, ví dụ sắp xếp, lọc nhiều lượt hoặc tham chiếu theo index.
- Cần API đơn giản và muốn xử lý lỗi đọc bằng `IOException` ngay tại lời gọi.

Đổi lại, mọi dòng được giữ trong bộ nhớ cùng lúc. Bộ nhớ cần thiết tăng theo tổng kích thước văn bản và chi phí đối tượng của danh sách/dòng.

### 4.1. Dùng charset cụ thể

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

Path legacy = Path.of("legacy-data.txt");

List<String> lines = Files.readAllLines(
        legacy, StandardCharsets.ISO_8859_1);
```

Không thay charset của file chỉ để làm cho lỗi biến mất. Nếu dữ liệu được tạo bằng UTF-8 thì phải giải mã UTF-8; nếu được tạo bằng charset khác, hãy theo đúng định dạng mà bên tạo công bố.

### 4.2. Ký tự kết thúc dòng không nằm trong từng phần tử

`readAllLines` nhận diện các line terminator `\n`, `\r` và `\r\n`. Dấu kết thúc dòng không được đưa vào các phần tử `String` của danh sách.

Ví dụ file có nội dung:

```text
alpha\r\n
\r\n
beta\n
```

Danh sách nhận được tương đương:

```java
List.of("alpha", "", "beta");
```

Dòng trống ở giữa vẫn được biểu diễn bằng chuỗi rỗng. Nếu file kết thúc bằng line terminator, API không tự thêm một phần tử rỗng chỉ để biểu diễn separator cuối file. Nếu cần giữ chính xác loại newline ban đầu, dùng API đọc toàn bộ nội dung như `Files.readString` hoặc đọc theo khối ký tự thay vì tách dòng.

## 5. `Files.lines`: đọc lười bằng Stream

Ví dụ đếm các dòng chứa `ERROR`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path log = Path.of("application.log");

try (Stream<String> lines = Files.lines(log, StandardCharsets.UTF_8)) {
    long errors = lines
            .filter(line -> line.contains("ERROR"))
            .count();

    System.out.println("Số dòng lỗi: " + errors);
}
```

`Files.lines` không tải toàn bộ dòng vào `List` trước khi trả kết quả. Stream được tiêu thụ khi thực hiện terminal operation như `count()`, `forEach()`, `findFirst()` hoặc `collect()`.

Đặc điểm quan trọng:

- Việc mở file diễn ra khi gọi `Files.lines`.
- Dữ liệu dòng được đọc lười trong quá trình tiêu thụ stream.
- File vẫn mở trong khi stream sử dụng reader bên dưới.
- Đóng stream sẽ đóng tài nguyên file được stream quản lý.
- Nếu lỗi I/O hoặc byte không hợp lệ xảy ra trong lúc đọc lười, thao tác stream có thể ném `UncheckedIOException`.

Vì stream giữ tài nguyên file, hãy luôn đặt nó trong try-with-resources nếu cần quản lý vòng đời xác định.

### 5.1. Tìm dòng đầu tiên thỏa điều kiện

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

Path log = Path.of("application.log");

try (Stream<String> lines = Files.lines(log, StandardCharsets.UTF_8)) {
    Optional<String> firstError = lines
            .filter(line -> line.contains("ERROR"))
            .findFirst();

    firstError.ifPresent(System.out::println);
}
```

`findFirst()` có thể kết thúc sớm khi tìm thấy kết quả. Khối try-with-resources vẫn đóng stream và file sau khi xử lý xong.

### 5.2. Lọc và ghi kết quả mà không giữ toàn bộ danh sách

```java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

Path input = Path.of("application.log");
Path output = Path.of("errors.log");

try (Stream<String> lines = Files.lines(input, StandardCharsets.UTF_8);
     BufferedWriter writer = Files.newBufferedWriter(
             output,
             StandardCharsets.UTF_8,
             StandardOpenOption.CREATE,
             StandardOpenOption.TRUNCATE_EXISTING)) {

    lines.filter(line -> line.contains("ERROR"))
            .forEach(line -> {
                try {
                    writer.write(line);
                    writer.newLine();
                } catch (java.io.IOException e) {
                    throw new java.io.UncheckedIOException(e);
                }
            });
}
```

Ví dụ này đọc từng dòng và ghi các dòng phù hợp. Không có `List` chứa toàn bộ log. `forEach` nhận `Consumer`, nên không thể trực tiếp khai báo checked `IOException`; ví dụ chuyển lỗi ghi thành `UncheckedIOException` để truyền ra ngoài. Trong code nghiệp vụ, có thể chọn vòng lặp `Iterator` hoặc cách tổ chức khác nếu muốn giữ xử lý `IOException` trực tiếp và rõ ràng hơn.

Không đọc và ghi đè cùng một file theo cách này. Nếu output trùng input, writer có thể truncate file trong khi stream còn đọc. Hãy dùng file đích riêng hoặc chiến lược file tạm rồi thay thế sau khi đọc hoàn tất.

## 6. Vòng đời Stream và file handle

Đây là khác biệt quan trọng nhất khi chuyển từ `readAllLines` sang `lines`.

| API | Ai giữ tài nguyên file? | Khi nào đóng? |
| --- | --- | --- |
| `Files.readAllLines(path)` | Phương thức nội bộ | Đóng trước khi trả `List` |
| `Files.lines(path)` | Stream trả về | Khi gọi `close()` trên stream |
| `Files.newBufferedReader(path)` | Reader trả về | Khi gọi `close()` trên reader |
| `Files.readString(path)` | Phương thức nội bộ | Đóng trước khi trả `String` |

Không nên viết:

```java
// Sai vòng đời: stream bị đóng ngay khi thoát khỏi try.
Stream<String> lines;
try (Stream<String> opened = Files.lines(path)) {
    lines = opened;
}

// Không thể tiêu thụ stream đã đóng.
long count = lines.count();
```

Cũng không nên trả stream từ một phương thức đã đóng stream trước khi trả về:

```java
// Sai: caller nhận stream đã bị đóng.
static Stream<String> readLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank());
    }
}
```

Nếu muốn API trả về `Stream<String>`, cần chuyển trách nhiệm đóng tài nguyên cho caller và mô tả rõ điều đó:

```java
static Stream<String> openLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

// Caller phải đóng stream:
try (Stream<String> lines = openLines(Path.of("input.txt"))) {
    lines.forEach(System.out::println);
}
```

Cách đơn giản hơn trong nhiều ứng dụng là cung cấp phương thức xử lý dữ liệu ngay trong phạm vi try-with-resources, hoặc trả về `List` nếu dữ liệu nhỏ và việc giữ toàn bộ nội dung là chủ ý.

### 6.1. Đóng khi pipeline lỗi hoặc kết thúc sớm

Try-with-resources đảm bảo stream được đóng khi khối kết thúc, kể cả khi:

- Terminal operation hoàn thành bình thường.
- `findFirst()` hoặc `limit()` dừng trước khi đọc hết file.
- Lambda hoặc thao tác xử lý ném runtime exception.
- Có lỗi đọc phát sinh trong lúc tiêu thụ stream.

Không trông chờ terminal operation tự đóng stream. Theo hợp đồng `Stream`, việc kết thúc pipeline không tự thay thế `close()` cho stream có tài nguyên.

## 7. Phân biệt IOException và UncheckedIOException

Hai phương thức có khác biệt về thời điểm và loại ngoại lệ:

| Tình huống | `Files.readAllLines` | `Files.lines` |
| --- | --- | --- |
| Đường dẫn không tồn tại hoặc không mở được | Ném `IOException` ngay trong lời gọi | Ném `IOException` khi tạo stream |
| Lỗi I/O trong quá trình đọc | Ném `IOException` từ lời gọi | Ném `UncheckedIOException` khi tiêu thụ stream |
| Byte malformed/unmappable theo charset | Ném `IOException` | Ném `UncheckedIOException` trong quá trình stream đọc |
| Dữ liệu hợp lệ | Trả `List<String>` | Trả `Stream<String>` |

Với `Files.lines`, phần mở file được thực hiện trước khi trả stream; do đó lỗi mở file là checked `IOException`. Việc đọc từng dòng được thực hiện lười; lỗi phát sinh sau đó được bọc trong `UncheckedIOException`, có thể truy cập nguyên nhân gốc qua `getCause()`.

Ví dụ xử lý lỗi trong lúc tiêu thụ:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines =
        Files.lines(Path.of("input.txt"), StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
} catch (IOException e) {
    // Lỗi khi mở file.
    reportOpenFailure(e);
} catch (UncheckedIOException e) {
    // Lỗi đọc lười hoặc byte không hợp lệ.
    reportReadFailure(e.getCause());
}
```

Nếu xử lý stream bên trong lambda có thao tác I/O khác, lỗi từ thao tác đó cũng có thể được chuyển thành `UncheckedIOException` theo cách ứng dụng viết. Hãy phân biệt nguồn lỗi bằng stack trace và cause thay vì quy mọi `UncheckedIOException` cho decoder.

## 8. Byte lỗi và lựa chọn charset

Các overload của `Files.readAllLines` và `Files.lines` sử dụng charset đã chọn để decode byte. Nếu byte không hợp lệ theo charset, API báo lỗi thay vì tự đoán encoding khác.

Ví dụ, byte `E9` đứng riêng không phải một chuỗi UTF-8 hợp lệ:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;

Path file = Path.of("partner-data.txt");

try {
    // Overload mặc định dùng UTF-8.
    var lines = Files.readAllLines(file);
} catch (IOException e) {
    // Có thể do byte không hợp lệ theo UTF-8 hoặc lỗi I/O khác.
    reportInvalidFile(e);
}
```

Nếu hợp đồng của file thực sự là ISO-8859-1, chọn overload tương ứng:

```java
var lines = Files.readAllLines(
        file, StandardCharsets.ISO_8859_1);
```

Với `Files.lines`, lỗi byte malformed xảy ra trong quá trình stream tiêu thụ nên được biểu diễn bằng `UncheckedIOException`. Hãy quyết định chính sách nghiệp vụ: từ chối file, ghi nhận lỗi và yêu cầu gửi lại, hoặc chuyển đổi bằng một quy trình di trú có xác minh. Không tự động thử lần lượt các charset cho đến khi đọc ra một chuỗi trông hợp lý.

## 9. Bộ nhớ và hiệu năng: chọn đúng API

| Đặc điểm | `readAllLines` | `lines` |
| --- | --- | --- |
| Kết quả | `List<String>` | `Stream<String>` |
| Thời điểm đọc | Đọc toàn bộ trước khi trả về | Đọc lười khi stream được tiêu thụ |
| Bộ nhớ | Giữ toàn bộ dòng trong danh sách | Có thể xử lý tuần tự mà không giữ toàn bộ dòng |
| Quản lý tài nguyên | File đã đóng khi trả về | Caller phải đóng stream |
| Xử lý nhiều lượt | Có thể duyệt List nhiều lần | Stream chỉ được tiêu thụ một lần |
| Lỗi đọc | `IOException` | `UncheckedIOException` trong quá trình đọc lười |
| Phù hợp | File nhỏ/vừa, cần danh sách | File lớn, lọc/tổng hợp theo dòng |

`Files.lines` không đồng nghĩa với “luôn dùng bộ nhớ hằng số”. Stream có thể bị materialize nếu gọi `toList()`/`collect()`, hoặc giữ dữ liệu trung gian khi dùng các operation như `sorted()`; một dòng cực dài cũng cần bộ nhớ để tạo `String` của dòng đó.

Ví dụ sau vẫn giữ toàn bộ kết quả trong bộ nhớ, dù dùng `Files.lines`:

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> all = lines.toList();
}
```

Nếu mục tiêu là xử lý file lớn, hãy dùng pipeline tiêu thụ dần như `filter(...).count()` hoặc ghi kết quả ra writer. Tránh `collect` toàn bộ dòng nếu không thật sự cần.

Không nên mặc định gọi `.parallel()` để tăng tốc. Đọc file là thao tác I/O; lợi ích song song phụ thuộc cách phân tách dữ liệu, filesystem, workload và chi phí xử lý từng dòng. Đo hiệu năng trên dữ liệu thật trước khi quyết định.

## 10. So sánh với các API đọc file khác

| API | Nội dung trả về | Newline | Charset mặc định |
| --- | --- | --- | --- |
| `Files.readAllLines(path)` | `List<String>` | Bỏ separator trong từng phần tử | UTF-8 |
| `Files.lines(path)` | `Stream<String>` | Bỏ separator trong mỗi dòng | UTF-8 |
| `Files.readString(path)` | Một `String` toàn bộ file | Giữ nguyên ký tự newline | UTF-8 |
| `Files.readAllBytes(path)` | `byte[]` | Byte thô | Không decode |
| `Files.newBufferedReader(path)` | `BufferedReader` | `readLine()` bỏ separator | UTF-8 |
| `new BufferedReader(new InputStreamReader(in))` | `BufferedReader` | `readLine()` bỏ separator | Default charset của JVM ở tầng InputStreamReader |

Chọn API theo hình dạng dữ liệu cần xử lý:

- Cần một danh sách có thể duyệt nhiều lần và file vừa phải: `readAllLines`.
- Cần lọc, đếm, tìm kiếm hoặc biến đổi từng dòng trong file lớn: `lines`.
- Cần giữ newline hoặc parse toàn bộ văn bản: `readString`.
- Cần byte gốc: `readAllBytes` hoặc byte stream.
- Cần điều khiển vòng lặp, buffer hoặc xử lý lỗi theo từng bước: `newBufferedReader`.

## 11. Ví dụ thực hành: đếm dòng lỗi trong log lớn

Giả sử log UTF-8 có thể lớn và chỉ cần đếm số dòng chứa `ERROR`. Không cần tạo `List<String>`:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class CountErrors {
    public static void main(String[] args) {
        Path log = Path.of("application.log");

        try (Stream<String> lines = Files.lines(log, StandardCharsets.UTF_8)) {
            long count = lines
                    .filter(line -> line.contains("ERROR"))
                    .count();

            System.out.println("ERROR lines: " + count);
        } catch (IOException e) {
            System.err.println("Không mở được log: " + e.getMessage());
        } catch (UncheckedIOException e) {
            System.err.println("Lỗi trong lúc đọc log: " + e.getCause());
        }
    }
}
```

Nếu cần ghi các dòng lỗi sang file mới, có thể dùng `Files.newBufferedWriter` trong cùng phạm vi quản lý tài nguyên. Khi đó phải quyết định options để ghi đè hay append và đảm bảo input không bị truncate nếu vô tình trỏ output về cùng file.

## 12. Kiểm thử hợp đồng charset và vòng đời

Một kiểm thử đơn giản có thể tạo file UTF-8, xác minh hai API đọc cho kết quả tương đương:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path file = Files.createTempFile("lines-check-", ".txt");

try {
    String content = "café\n\nTiếng Việt 🌍\n";
    Files.writeString(file, content, StandardCharsets.UTF_8);

    List<String> eager = Files.readAllLines(file);
    List<String> lazy;

    try (Stream<String> lines = Files.lines(file)) {
        lazy = lines.toList();
    }

    if (!eager.equals(lazy)) {
        throw new AssertionError("readAllLines và lines phải cho cùng các dòng");
    }

    if (!eager.equals(List.of("café", "", "Tiếng Việt 🌍"))) {
        throw new AssertionError("Nội dung dòng không như mong đợi");
    }
} finally {
    Files.deleteIfExists(file);
}
```

Bài kiểm thử xác nhận:

- Hai API dùng cùng hợp đồng UTF-8 khi không truyền charset.
- Dòng trống ở giữa được giữ thành phần tử rỗng.
- Separator cuối file không tạo thêm một dòng rỗng.
- Stream được đóng ngay sau khi tiêu thụ.

Bổ sung kiểm thử byte malformed, charset ngoài UTF-8, file lớn, lỗi mở file và trường hợp pipeline kết thúc sớm như `findFirst()` để xác minh stream vẫn được đóng.

## 13. Những nhận định dễ nhầm

- **“`Files.readAllLines(path)` dùng default charset của JVM.”** Sai. Overload không charset dùng UTF-8 theo hợp đồng Files API.
- **“`Files.lines(path)` trả về List ngay lập tức.”** Sai. Nó trả `Stream<String>` và đọc lười khi tiêu thụ.
- **“Terminal operation tự đóng stream.”** Sai. Phải gọi `close()`, thường bằng try-with-resources.
- **“Không có dòng nào khớp thì `findFirst()` đóng file.”** Sai. Pipeline kết thúc, nhưng caller vẫn phải đóng stream.
- **“`Files.lines` không dùng bộ nhớ.”** Sai. Nó đệm dữ liệu và tạo String theo dòng; pipeline có thể materialize kết quả.
- **“Lỗi đọc trong `Files.lines` luôn là IOException.”** Sai. Lỗi mở file là `IOException`; lỗi phát sinh trong lúc stream đọc lười là `UncheckedIOException`.
- **“`readAllLines` giữ nguyên newline.”** Sai. Separator không nằm trong từng phần tử.
- **“Dùng `Files.lines(...).toList()` sẽ tiết kiệm bộ nhớ hơn `readAllLines`.”** Không. Cả hai cuối cùng đều giữ toàn bộ các dòng trong bộ nhớ.

## 14. Tài liệu tham khảo chính thức

- [Files — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): hợp đồng `readAllLines`, `lines`, charset, lazy stream và ngoại lệ.
- [Stream — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): terminal operations, stream lifecycle và `close()`.
- [UncheckedIOException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/UncheckedIOException.html): biểu diễn unchecked của lỗi I/O.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset từ Java 18 và phạm vi tác động.
- [StandardCharsets — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn như UTF-8 và ISO-8859-1.

