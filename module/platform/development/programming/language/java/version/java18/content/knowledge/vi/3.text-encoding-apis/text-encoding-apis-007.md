# Files.newBufferedReader(), Files.newBufferedWriter() và overload charset tường minh

## 1. Đọc và ghi file văn bản theo cách có buffer

Trong Java, `Files.newBufferedReader()` và `Files.newBufferedWriter()` là các phương thức tiện ích của `java.nio.file.Files`. Chúng mở file và trả về `BufferedReader` hoặc `BufferedWriter` để ứng dụng đọc/ghi văn bản theo luồng.

Hai phương thức phù hợp khi cần xử lý file lớn theo dòng hoặc theo khối, vì chương trình không phải tải toàn bộ nội dung vào một `String`. Chúng cũng gom sẵn các bước tạo byte stream, chuyển mã và đệm ký tự.

Điểm cần nắm vững trong module Java 18 là **charset phải phù hợp với định dạng file**. Các overload không truyền charset của hai phương thức này dùng UTF-8 theo hợp đồng API. Overload nhận `Charset` cho phép chỉ rõ encoding khác khi file được tạo theo một quy ước riêng.

```text
Đọc:
Path -> Files.newBufferedReader(path, charset)
     -> BufferedReader
     -> String / char / readLine()

Ghi:
String / char -> BufferedWriter
              -> Files.newBufferedWriter(path, charset, options)
              -> Path
```

Sau bài này, bạn có thể chọn overload phù hợp, hiểu cách `OpenOption` ảnh hưởng đến file, xử lý dữ liệu không hợp lệ, quản lý vòng đời reader/writer và kiểm thử byte đầu ra trên JDK hiện đại.

## 2. Hai phương thức và các overload

### 2.1. `Files.newBufferedReader`

Hai overload chính:

```java
BufferedReader newBufferedReader(Path path)
BufferedReader newBufferedReader(Path path, Charset cs)
```

| Lời gọi | Charset giải mã | Kết quả |
| --- | --- | --- |
| `Files.newBufferedReader(path)` | UTF-8 theo hợp đồng API | `BufferedReader` |
| `Files.newBufferedReader(path, StandardCharsets.UTF_8)` | UTF-8 tường minh | `BufferedReader` |
| `Files.newBufferedReader(path, StandardCharsets.ISO_8859_1)` | ISO-8859-1 | `BufferedReader` |
| `Files.newBufferedReader(path, charset)` | Charset truyền vào | `BufferedReader` |

Không truyền charset tương đương với truyền `StandardCharsets.UTF_8`. Các overload này đã có từ Java 8, vì vậy hành vi UTF-8 của overload không tham số **có trước Java 18**.

Reader bắt đầu đọc từ đầu file. Phương thức mở file và trả về reader đã có buffer mặc định; ứng dụng không cần tự bọc thêm một `BufferedReader` chỉ để có buffering.

### 2.2. `Files.newBufferedWriter`

Hai overload chính:

```java
BufferedWriter newBufferedWriter(Path path, OpenOption... options)
BufferedWriter newBufferedWriter(
        Path path, Charset cs, OpenOption... options)
```

| Lời gọi | Charset mã hóa | Chế độ mở mặc định |
| --- | --- | --- |
| `Files.newBufferedWriter(path)` | UTF-8 theo hợp đồng API | Tạo mới hoặc truncate file cũ |
| `Files.newBufferedWriter(path, UTF_8)` | UTF-8 tường minh | Tạo mới hoặc truncate file cũ |
| `Files.newBufferedWriter(path, UTF_8, CREATE, APPEND)` | UTF-8 tường minh | Nối thêm vào cuối |
| `Files.newBufferedWriter(path, ISO_8859_1)` | ISO-8859-1 | Tạo mới hoặc truncate file cũ |

`UTF_8` trong bảng là cách viết rút gọn cho `StandardCharsets.UTF_8`; `CREATE`, `APPEND` là các hằng số của `StandardOpenOption`.

Không truyền `OpenOption` tương đương với `CREATE`, `TRUNCATE_EXISTING` và `WRITE`. Nghĩa là file được tạo nếu chưa tồn tại; nếu file thường đã tồn tại thì nội dung cũ bị cắt về 0 byte trước khi ghi.

Cả hai phương thức đều trả về writer/reader đã được đệm với kích thước mặc định của API. Chúng không cung cấp tham số kích thước buffer trong chữ ký phương thức.

## 3. UTF-8 của Files API và JEP 400 là hai hợp đồng khác nhau

JEP 400 đưa UTF-8 thành default charset thông thường của Java SE từ Java 18. Thay đổi này tác động đến API dựa trên `Charset.defaultCharset()`.

Trong khi đó, `Files.newBufferedReader(path)` và `Files.newBufferedWriter(path, options...)` đã quy định UTF-8 riêng trong Javadoc từ Java 8. Vì thế:

- Không truyền charset vào hai phương thức này vẫn dùng UTF-8, kể cả khi default charset của JVM khác.
- Truyền `Charset` vào overload tương ứng sẽ dùng đúng charset đã chỉ định.
- Không thể suy luận rằng mọi API Java không có tham số charset đều dùng UTF-8. Hợp đồng phải được xem theo từng API.

Ví dụ kiểm tra hai khái niệm:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

System.out.println(Charset.defaultCharset());
System.out.println(StandardCharsets.UTF_8);
```

Trên cấu hình thông thường của JDK 18+, dòng đầu cũng thường in `UTF-8`. Nhưng đây là hai ý nghĩa khác nhau: một giá trị là default charset JVM; giá trị còn lại là charset được API/file format quy định rõ.

| API | Charset không truyền tham số |
| --- | --- |
| `Files.newBufferedReader(path)` | UTF-8 theo hợp đồng Files API |
| `Files.newBufferedWriter(path, options)` | UTF-8 theo hợp đồng Files API |
| `Files.readString(path)` | UTF-8 theo hợp đồng Files API |
| `new InputStreamReader(input)` | `Charset.defaultCharset()` |
| `new OutputStreamWriter(output)` | Thông thường là default charset; có ngoại lệ với `PrintStream` |
| `new String(bytes)` | `Charset.defaultCharset()` |
| `text.getBytes()` | `Charset.defaultCharset()` |

Đây là lý do nên chọn API theo hợp đồng dữ liệu, không theo phỏng đoán về hệ điều hành hay phiên bản JDK.

## 4. Đọc file UTF-8 theo dòng

Ví dụ đọc file văn bản UTF-8:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("messages.txt");

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

`process` đại diện cho xử lý nghiệp vụ của ứng dụng. Vòng lặp kết thúc khi `readLine()` trả về `null`, nghĩa là đã hết dữ liệu.

`readLine()` nhận diện dấu kết thúc dòng `\n`, `\r` và `\r\n`, nhưng chuỗi trả về **không chứa** dấu kết thúc dòng. Một dòng trống trả về `""`, khác với `null` ở cuối file.

Nếu file được quy định bằng ISO-8859-1, thay charset tại chính điểm mở file:

```java
try (BufferedReader reader = Files.newBufferedReader(
        Path.of("partner-export.txt"),
        StandardCharsets.ISO_8859_1)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

Không giải mã dữ liệu theo charset khác chỉ vì kết quả hiển thị trông có vẻ dễ đọc hơn. Hãy xác định encoding từ hợp đồng của bên tạo file, metadata hoặc định dạng chuẩn.

### Giữ nguyên ký tự xuống dòng

Vì `readLine()` bỏ separator, đọc từng dòng rồi ghi lại bằng `newLine()` có thể thay đổi newline ban đầu. Nếu cần giữ nguyên chuỗi ký tự bao gồm `\r`, `\n`, hãy đọc theo khối:

```java
try (var reader = Files.newBufferedReader(
        Path.of("input.txt"), StandardCharsets.UTF_8)) {
    StringBuilder content = new StringBuilder();
    char[] buffer = new char[4096];
    int count;

    while ((count = reader.read(buffer)) != -1) {
        content.append(buffer, 0, count);
    }
}
```

Cách này giữ nguyên ký tự newline sau khi decode, nhưng vẫn không bảo toàn byte gốc nếu nội dung byte đã được chuyển mã. Nếu cần copy byte-for-byte, dùng `Files.copy` hoặc byte stream thay vì reader/writer.

## 5. Ghi file UTF-8 với `Files.newBufferedWriter`

Ví dụ ghi nội dung mới:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path report = Path.of("report.txt");

try (BufferedWriter writer =
        Files.newBufferedWriter(report, StandardCharsets.UTF_8)) {
    writer.write("Báo cáo");
    writer.newLine();
    writer.write("Tiếng Việt có dấu 🌍");
    writer.newLine();
}
```

`BufferedWriter` đệm ký tự trước khi chuyển xuống tầng ghi byte. Charset UTF-8 được áp dụng bởi writer do `Files.newBufferedWriter` tạo ra. Ứng dụng không phải tự tạo `OutputStreamWriter` trong trường hợp thông thường.

`newLine()` ghi line separator của nền tảng hiện tại. Nếu file format yêu cầu LF cố định, ghi `writer.write('\n')`; nếu yêu cầu CRLF, ghi `writer.write("\r\n")`. Không giả định mọi định dạng văn bản đều cho phép thay newline theo hệ điều hành.

Nếu không truyền options, file cũ bị truncate. Hãy chọn rõ chế độ mở trước khi dùng writer trong nghiệp vụ có dữ liệu cần giữ.

## 6. Chọn `OpenOption`: tạo mới, ghi đè, append

`OpenOption` mô tả cách file được mở. Các tùy chọn phổ biến thuộc `StandardOpenOption`.

| Mục tiêu | Options | Hành vi |
| --- | --- | --- |
| Ghi mới hoặc thay nội dung file cũ | Không truyền options | Tương đương `CREATE`, `TRUNCATE_EXISTING`, `WRITE` |
| Tạo nếu chưa có rồi nối cuối file | `CREATE`, `APPEND` | Giữ byte cũ, ghi nội dung mới ở cuối |
| Chỉ tạo file mới, không ghi đè file tồn tại | `CREATE_NEW`, `WRITE` | Ném `FileAlreadyExistsException` nếu file đã có |
| Ghi vào file đã tồn tại, cắt nội dung cũ | `WRITE`, `TRUNCATE_EXISTING` | Không tự tạo file mới |
| Mở file đã tồn tại để ghi mà không truncate | `WRITE` | Bắt đầu ghi từ đầu file; không tự tạo hoặc cắt ngắn file, phần byte cũ phía sau vùng ghi có thể vẫn còn |

### 6.1. Append UTF-8

```java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path log = Path.of("events.log");

try (BufferedWriter writer = Files.newBufferedWriter(
        log,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND)) {
    writer.write("INFO|đã xử lý xong");
    writer.newLine();
}
```

`CREATE` cho phép tạo file nếu chưa tồn tại; `APPEND` yêu cầu ghi ở cuối file. Khi append vào file có sẵn, charset của phần mới phải tương thích với charset của toàn bộ nội dung cũ.

`APPEND` không tự thêm newline, delimiter, BOM hay dấu phân cách record. Ví dụ file cũ kết thúc bằng `record-A` mà không có newline, nếu writer ghi `record-B` thì kết quả có thể thành `record-Arecord-B`. Hãy tự xác định separator của định dạng.

### 6.2. `CREATE_NEW` để tránh ghi đè ngoài ý muốn

```java
try (BufferedWriter writer = Files.newBufferedWriter(
        Path.of("daily-report.txt"),
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    writer.write("Báo cáo ngày mới");
    writer.newLine();
}
```

Nếu đường dẫn đã tồn tại, thao tác mở file thất bại với `FileAlreadyExistsException`. Đây là lựa chọn hữu ích khi tên file phải duy nhất và việc ghi đè có thể làm mất dữ liệu.

### 6.3. Kết hợp option không hợp lệ

Không kết hợp `APPEND` và `TRUNCATE_EXISTING` cho cùng một lần mở vì ý nghĩa mâu thuẫn. `Files.newBufferedWriter` ném `IllegalArgumentException` nếu nhận tổ hợp options không hợp lệ. Một số option có thể không được file system provider hỗ trợ và gây `UnsupportedOperationException`.

Không truyền `READ` để kỳ vọng writer vừa đọc vừa ghi; `BufferedWriter` là API ghi ký tự. Khi cần đọc/ghi tại vị trí tùy ý, xem xét `SeekableByteChannel` hoặc API khác với hợp đồng phù hợp.

## 7. Xử lý byte không hợp lệ và lỗi chuyển mã

### 7.1. Lỗi decode khi đọc

Với overload có charset, Javadoc quy định các thao tác đọc trên reader ném `IOException` nếu gặp chuỗi byte malformed hoặc unmappable theo charset đó.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("incoming.txt");

try (BufferedReader reader =
        Files.newBufferedReader(source, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
} catch (IOException e) {
    // Có thể là lỗi mở/đọc file hoặc byte không hợp lệ theo UTF-8.
    reportInvalidInput(e);
}
```

Lỗi chuyển mã có thể xuất hiện **khi đọc**, không nhất thiết ngay lúc gọi `newBufferedReader`, bởi dữ liệu được tiêu thụ dần. Nếu file thực sự dùng ISO-8859-1, hãy dùng `StandardCharsets.ISO_8859_1` theo hợp đồng nguồn.

Không tự động thử nhiều charset cho đến khi có kết quả “đọc được”. Một chuỗi byte có thể được diễn giải theo nhiều charset khác nhau; hiển thị có vẻ hợp lý không chứng minh nội dung gốc đúng.

### 7.2. Lỗi encode khi ghi

Với `Files.newBufferedWriter(path, charset, options)`, thao tác ghi ném `IOException` nếu nội dung không thể mã hóa bằng charset chỉ định. Do writer có buffer, lỗi unmappable/malformed có thể chỉ xuất hiện khi gọi `write`, `flush` hoặc `close`.

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedWriter writer = Files.newBufferedWriter(
        Path.of("ascii.txt"), StandardCharsets.US_ASCII)) {
    writer.write("Tiếng Việt");
} catch (IOException e) {
    // US-ASCII không thể biểu diễn các ký tự tiếng Việt.
    reportEncodingFailure(e);
}
```

UTF-8 có thể biểu diễn mọi Unicode scalar value hợp lệ. Charset giới hạn như US-ASCII hoặc ISO-8859-1 không biểu diễn được toàn bộ nội dung Unicode. Chọn charset theo định dạng đích và xử lý lỗi thay vì âm thầm làm mất ký tự.

## 8. Buffer mặc định, readLine, newLine và flush

Hai phương thức `Files.newBufferedReader` và `Files.newBufferedWriter` trả về wrapper đã có buffer mặc định. Chữ ký API không có tham số `bufferSize`.

- Không cần bọc thêm `BufferedReader` hoặc `BufferedWriter` chỉ để có buffer.
- Không giả định kích thước buffer nội bộ là một con số cố định giữa các JDK.
- Chỉ tùy chỉnh buffer khi có số đo hiệu năng hoặc yêu cầu cụ thể.

Nếu cần tự điều chỉnh kích thước, có thể dựng pipeline từ byte stream và lớp chuyển mã, rồi truyền `size` cho wrapper. Ví dụ đọc:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(Path.of("large.txt")),
                StandardCharsets.UTF_8),
        16 * 1024)) {
    // Xử lý từng dòng hoặc từng khối.
}
```

Cách này tạo một buffer ký tự với kích thước do ứng dụng chọn. Chỉ nên làm khi thật sự cần; với đa số file, `Files.newBufferedReader` là đủ.

`flush()` trên `BufferedWriter` đẩy ký tự đã đệm xuống tầng ghi bên dưới. Nó không đảm bảo dữ liệu đã được đồng bộ vật lý xuống ổ đĩa. `close()` hoàn tất ghi, đóng writer và file bên dưới; try-with-resources là cách quản lý thông thường.

## 9. Trách nhiệm đóng tài nguyên

Các reader/writer do `Files` tạo ra sở hữu handle file được mở trong lời gọi. Đóng reader/writer sẽ giải phóng tài nguyên tương ứng. Hãy dùng try-with-resources:

```java
try (var reader = Files.newBufferedReader(
             Path.of("input.txt"), StandardCharsets.UTF_8);
     var writer = Files.newBufferedWriter(
             Path.of("output.txt"), StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

Khi rời khối, cả reader và writer đều được đóng, kể cả khi thân khối ném ngoại lệ. Nếu lỗi chính và lỗi khi đóng cùng xảy ra, Java giữ ngoại lệ chính và ghi nhận lỗi đóng dưới dạng suppressed exception.

Đừng giữ reader/writer mở lâu hơn cần thiết. Đặc biệt, nếu đọc file rồi ghi đè chính file đó, hãy đóng reader trước khi mở writer; nếu không, writer có thể truncate nội dung trong lúc reader vẫn còn sử dụng file. Với thao tác thay thế file quan trọng, cân nhắc file tạm và `Files.move` thay vì đọc/ghi đè cùng lúc.

## 10. Xử lý file lớn và các API liên quan

`Files.newBufferedReader`/`newBufferedWriter` là API streaming: dữ liệu được đọc hoặc ghi dần, phù hợp với file lớn. Đây là khác biệt với `Files.readString(path)` hoặc `Files.readAllLines(path)`, vốn cần giữ toàn bộ nội dung trong bộ nhớ.

Nếu chỉ cần xử lý từng dòng, dùng vòng lặp `readLine()`. Nếu cần pipeline dạng stream, có thể dùng `Files.lines(path, charset)`; stream này cần được đóng:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (var lines = Files.lines(
        Path.of("access.log"), StandardCharsets.UTF_8)) {
    long errors = lines.filter(line -> line.contains("ERROR")).count();
    System.out.println(errors);
}
```

`Files.lines` đọc lười theo nhu cầu tiêu thụ. Try-with-resources rất quan trọng vì stream giữ tài nguyên file mở. Nếu cần điều khiển buffer, exception handling hoặc xử lý tuần tự phức tạp, `BufferedReader` thường trực quan hơn.

| Nhu cầu | API gợi ý |
| --- | --- |
| Đọc file theo dòng | `Files.newBufferedReader(path, charset)` |
| Ghi file theo dòng/khối | `Files.newBufferedWriter(path, charset, options)` |
| Đọc toàn bộ file vừa phải | `Files.readString(path, charset)` |
| Ghi một chuỗi vừa phải | `Files.writeString(path, text, charset, options)` |
| Stream các dòng để lọc/tổng hợp | `Files.lines(path, charset)` |
| Copy nguyên byte | `Files.copy(source, target)` |

## 11. Ví dụ hoàn chỉnh: ghi mới, append và đọc lại

Ví dụ sau ghi một file UTF-8, nối thêm một dòng rồi đọc lại. Nó dùng file tạm để không ghi đè dữ liệu người dùng:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class BufferedFilesDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("buffered-files-", ".txt");

        try {
            // Mở mặc định: CREATE + TRUNCATE_EXISTING + WRITE.
            try (BufferedWriter writer =
                    Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                writer.write("Cà phê");
                writer.newLine();
            }

            // Append, giữ nguyên dòng cũ.
            try (BufferedWriter writer = Files.newBufferedWriter(
                    file,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND)) {
                writer.write("Tiếng Việt 🌍");
                writer.newLine();
            }

            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }

            byte[] bytes = Files.readAllBytes(file);
            System.out.println("UTF-8 bytes: " + bytes.length);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Kết quả hiển thị hai dòng. File chứa byte UTF-8, còn newline do `newLine()` tạo ra phụ thuộc nền tảng. Nếu nội dung là giao thức có newline cố định, thay `newLine()` bằng separator được quy định.

## 12. Kiểm thử hợp đồng charset và append

Một kiểm thử có ích nên xác minh byte đầu ra, không chỉ nhìn text trên terminal:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.HexFormat;

Path file = Files.createTempFile("charset-check-", ".txt");

try {
    String value = "café - Tiếng Việt 🌍";

    try (var writer = Files.newBufferedWriter(file)) {
        writer.write(value);
    }

    byte[] actual = Files.readAllBytes(file);
    byte[] expected = value.getBytes(StandardCharsets.UTF_8);

    if (!Arrays.equals(expected, actual)) {
        throw new AssertionError("Overload mặc định phải ghi UTF-8");
    }

    System.out.println(HexFormat.of().formatHex(actual));

    String restored;
    try (var reader = Files.newBufferedReader(file)) {
        char[] buffer = new char[128];
        int count = reader.read(buffer);
        restored = new String(buffer, 0, count);
    }

    if (!value.equals(restored)) {
        throw new AssertionError("Đọc lại UTF-8 không khớp");
    }
} finally {
    Files.deleteIfExists(file);
}
```

Kiểm thử này xác nhận overload không charset dùng UTF-8 theo hợp đồng API. Có thể bổ sung các ca:

1. Đọc file có charset khác UTF-8 bằng overload `Charset` tương ứng.
2. Đọc file có byte UTF-8 malformed và xác nhận thao tác đọc ném `IOException`.
3. Ghi ký tự không biểu diễn được bằng charset đích và xác nhận lỗi khi write/flush/close.
4. Append file không có newline cuối và xác nhận chương trình tự quản lý delimiter.
5. `CREATE_NEW` khi file đã tồn tại.
6. File rỗng, file lớn và file không tồn tại.

## 13. Những nhận định dễ nhầm

- **“Java 18 mới làm `Files.newBufferedReader(path)` dùng UTF-8.”** Sai. Overload không charset đã quy định UTF-8 từ Java 8.
- **“Files.newBufferedReader không truyền charset sẽ lấy default charset JVM.”** Sai. Nó tương đương overload truyền `StandardCharsets.UTF_8`.
- **“newBufferedWriter mặc định append.”** Sai. Không truyền options sẽ tạo mới hoặc truncate file cũ.
- **“Charset được quyết định bởi BufferedReader/BufferedWriter.”** Sai. Charset do hợp đồng Files API hoặc tham số `Charset` quyết định; lớp buffer chỉ đệm ký tự.
- **“APPEND tự thêm newline.”** Sai. Nó chỉ ghi ở cuối file.
- **“Lỗi charset luôn xuất hiện ngay lúc mở file.”** Sai. Lỗi decode xuất hiện khi đọc; lỗi encode có thể xuất hiện khi ghi, flush hoặc close do buffering.
- **“File lớn nên dùng readAllLines.”** Không phù hợp nếu toàn bộ danh sách dòng không thể nằm an toàn trong bộ nhớ; dùng reader streaming.
- **“Đóng writer chỉ giải phóng wrapper.”** Sai. Đóng writer do Files trả về cũng đóng file resource bên dưới.

## 14. Tài liệu tham khảo chính thức

- [Files — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): hợp đồng của `newBufferedReader`, `newBufferedWriter`, charset, buffer, options và lỗi chuyển mã.
- [StandardOpenOption — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/StandardOpenOption.html): ý nghĩa `CREATE`, `CREATE_NEW`, `APPEND`, `TRUNCATE_EXISTING`, `WRITE`.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset từ Java 18 và phạm vi tác động.
- [BufferedReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html): đọc dòng, mark/reset và buffer ký tự.
- [BufferedWriter — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedWriter.html): ghi, `newLine()`, `flush()` và `close()`.

