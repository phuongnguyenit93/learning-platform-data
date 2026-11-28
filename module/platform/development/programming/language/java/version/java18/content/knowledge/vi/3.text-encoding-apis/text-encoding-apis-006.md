# Files.readString() và Files.writeString(): UTF-8 đã là hợp đồng của overload không truyền charset

## 1. API tiện lợi cho file văn bản và điểm dễ nhầm về UTF-8

`Files.readString()` và `Files.writeString()` là các phương thức của `java.nio.file.Files`, được bổ sung từ **Java 11**. Chúng giúp đọc toàn bộ nội dung file vào một `String` hoặc ghi một `CharSequence` ra file bằng một lời gọi.

Điểm quan trọng của bài học Java 18 này là: **overload không truyền `Charset` của hai phương thức đã quy định UTF-8 trong hợp đồng API**. Ví dụ:

```java
String text = Files.readString(Path.of("notes.txt"));
Files.writeString(Path.of("notes.txt"), "Xin chào");
```

Hai lời gọi trên dùng UTF-8 ngay cả khi `Charset.defaultCharset()` của JVM có giá trị khác. Điều này đã đúng từ Java 11, trước khi Java 18 đưa UTF-8 thành default charset thông thường theo JEP 400.

Vì thế, có hai khái niệm cần tách biệt:

- **Default charset của JVM:** giá trị trả về bởi `Charset.defaultCharset()`, áp dụng cho các API thật sự quy định sử dụng charset mặc định.
- **UTF-8 trong hợp đồng của `Files.readString`/`writeString`:** lựa chọn cố định của overload không truyền charset, không lấy theo default charset của JVM.

Sau bài này, bạn có thể chọn đúng overload, đọc và ghi UTF-8 ổn định, dùng charset khác khi định dạng file yêu cầu, kiểm soát chế độ ghi đè/append, xử lý lỗi và biết khi nào nên dùng API streaming.

## 2. Các overload và charset được chọn

Hai phương thức có các overload chính sau:

| API | Cách gọi | Charset |
| --- | --- | --- |
| Đọc toàn bộ file | `Files.readString(path)` | UTF-8 theo hợp đồng API |
| Đọc toàn bộ file | `Files.readString(path, charset)` | Charset truyền vào |
| Ghi nội dung | `Files.writeString(path, text, options...)` | UTF-8 theo hợp đồng API |
| Ghi nội dung | `Files.writeString(path, text, charset, options...)` | Charset truyền vào |

Các overload này có từ Java 11 và tiếp tục được hỗ trợ trên các JDK hiện đại. Khi không truyền charset, API hoạt động tương đương với việc truyền `StandardCharsets.UTF_8`:

```java
String a = Files.readString(path);
String b = Files.readString(path, StandardCharsets.UTF_8);

// Hai cách đọc có cùng hợp đồng charset UTF-8.
```

```java
Files.writeString(path, content);
Files.writeString(path, content, StandardCharsets.UTF_8);

// Hai cách ghi có cùng hợp đồng charset UTF-8.
```

Overload có `Charset` tồn tại để làm rõ định dạng khi file không dùng UTF-8. Ví dụ, nếu một hệ thống cũ quy định file ISO-8859-1, hãy truyền `StandardCharsets.ISO_8859_1` thay vì cố thay đổi default charset toàn JVM.

## 3. Vì sao đây không phải là hệ quả của JEP 400?

JEP 400 — UTF-8 by Default — có hiệu lực từ Java 18 và đặt UTF-8 làm default charset trong cấu hình thông thường của Java SE. Thay đổi đó ảnh hưởng đến các API dựa trên default charset.

`Files.readString(path)` và `Files.writeString(path, text)` lại có hợp đồng UTF-8 riêng từ Java 11. Chúng không cần chờ JEP 400 để có hành vi UTF-8.

Có thể kiểm tra hai giá trị độc lập:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

System.out.println(Charset.defaultCharset());
System.out.println(StandardCharsets.UTF_8);
```

Trên cấu hình thông thường của JDK 18+, dòng đầu thường in `UTF-8`. Tuy nhiên, điều đó không có nghĩa mọi API không nhận tham số charset đều dùng UTF-8. Một API có thể dùng default charset, API khác có thể quy định UTF-8, và một API khác có thể yêu cầu charset từ cấu hình hoặc giao thức.

### So sánh hành vi

| Lời gọi | Charset |
| --- | --- |
| `Files.readString(path)` | UTF-8 cố định theo hợp đồng |
| `Files.readString(path, charset)` | `charset` được truyền |
| `Files.writeString(path, text)` | UTF-8 cố định theo hợp đồng |
| `Files.writeString(path, text, charset)` | `charset` được truyền |
| `new String(bytes)` | `Charset.defaultCharset()` |
| `text.getBytes()` | `Charset.defaultCharset()` |
| `new InputStreamReader(input)` | `Charset.defaultCharset()` |
| `new OutputStreamWriter(output)` | Thông thường là default charset; có ngoại lệ với `PrintStream` |

Vì vậy, không nên suy luận charset của một API chỉ từ việc overload có hoặc không có tham số `Charset`. Hãy đọc Javadoc của đúng phương thức.

## 4. Đọc file với `Files.readString()`

### 4.1. Đọc UTF-8 bằng overload mặc định

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path config = Path.of("config.txt");

try {
    String content = Files.readString(config);
    System.out.println(content);
} catch (IOException e) {
    // Xử lý lỗi đọc file hoặc dữ liệu UTF-8 không hợp lệ.
    throw new IllegalStateException("Không đọc được config", e);
}
```

Không cần tự tạo `FileReader`, `InputStreamReader` hay `BufferedReader` khi chỉ cần lấy toàn bộ nội dung của một file vừa phải. `Files.readString` tự quản lý việc mở và đóng file trong quá trình đọc.

### 4.2. Đọc với charset cụ thể

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path legacyFile = Path.of("legacy-export.txt");

String content = Files.readString(
        legacyFile,
        StandardCharsets.ISO_8859_1);
```

Chỉ dùng charset đã được quy định bởi định dạng file hoặc hệ thống tạo file. Không tự chọn ISO-8859-1, Windows-1252 hay charset khác chỉ vì nó làm cho một vài ký tự hiển thị “có vẻ đúng”.

### 4.3. `readString` giữ nguyên nội dung dòng

`Files.readString` đọc toàn bộ nội dung, bao gồm các ký tự xuống dòng ở giữa và ở cuối file. Ví dụ file có nội dung byte UTF-8 tương ứng với:

```text
dòng một\r\n
dòng hai\n
dòng ba
```

Chuỗi kết quả vẫn chứa `\r\n` giữa dòng một và dòng hai, `\n` giữa dòng hai và dòng ba, và không tự thêm newline vào cuối.

Điều này khác `BufferedReader.readLine()` hoặc `Files.readAllLines()`, vốn tách dòng và không trả lại dấu kết thúc dòng trong từng phần tử. Nếu cần giữ nguyên newline để so sánh, phân tích cú pháp hoặc ghi lại, `readString` là lựa chọn thuận tiện.

## 5. Ghi file với `Files.writeString()`

### 5.1. Ghi UTF-8 theo hợp đồng API

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path report = Path.of("report.txt");
String content = "Báo cáo\nTiếng Việt có dấu 🌍\n";

try {
    Files.writeString(report, content);
} catch (IOException e) {
    throw new IllegalStateException("Không ghi được báo cáo", e);
}
```

Overload không truyền charset mã hóa nội dung bằng UTF-8. Nội dung được ghi đúng như chuỗi cung cấp, bao gồm cả các ký tự xuống dòng đã có trong chuỗi.

`Files.writeString` **không tự thêm newline** sau nội dung. Nếu muốn file kết thúc bằng dấu xuống dòng, hãy thêm `\n`, `\r\n` hoặc `System.lineSeparator()` tùy hợp đồng định dạng.

### 5.2. Ghi bằng charset khác

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path export = Path.of("partner-export.txt");

Files.writeString(
        export,
        "café",
        StandardCharsets.ISO_8859_1);
```

Nếu charset đích không thể biểu diễn nội dung, API báo `IOException` do lỗi mã hóa. Ví dụ, ISO-8859-1 không biểu diễn được ký tự `🌍`. Không nên âm thầm đổi charset để ghi được dữ liệu nếu điều đó phá vỡ hợp đồng với hệ thống nhận.

## 6. Chế độ mở file: ghi đè hay append?

`Files.writeString` nhận các `OpenOption` ở tham số cuối. Khi **không truyền option**, hành vi mặc định tương đương:

- `CREATE`: tạo file nếu chưa tồn tại.
- `TRUNCATE_EXISTING`: nếu file đã tồn tại, cắt nội dung về 0 byte trước khi ghi.
- `WRITE`: mở file để ghi.

Do đó, lời gọi:

```java
Files.writeString(path, "Nội dung mới");
```

thường có nghĩa là tạo file mới hoặc **thay toàn bộ nội dung** file hiện có. Đây không phải append.

### 6.1. Append nội dung UTF-8

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path log = Path.of("events.log");

Files.writeString(
        log,
        "Sự kiện mới\n",
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
```

Overload không charset vẫn dùng UTF-8. `CREATE` cho phép tạo file nếu chưa có; `APPEND` ghi nội dung ở cuối file. Nếu cần charset khác, thêm đối số `Charset` trước các `OpenOption`:

```java
Files.writeString(
        log,
        "Sự kiện cũ\n",
        StandardCharsets.ISO_8859_1,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
```

Không trộn charset khi append vào cùng file. Nếu phần đầu file là UTF-8 thì nội dung nối thêm cũng phải theo UTF-8; nếu file đang dùng charset khác, tiếp tục dùng đúng charset đó hoặc chuyển đổi toàn bộ file một cách có kiểm soát.

### 6.2. Append không tự thêm dấu phân cách

`APPEND` chỉ xác định vị trí ghi ở cuối file. Nếu nội dung cũ không kết thúc bằng newline, phần mới có thể dính liền:

```java
// Nếu file cũ kết thúc bằng "old" không có newline,
// kết quả có thể là "oldnew".
Files.writeString(
        log,
        "new",
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
```

Ứng dụng cần tự quản lý dấu phân cách record, ví dụ `"\n"` hoặc `System.lineSeparator()`, theo định dạng thực tế.

### 6.3. Kết hợp option hợp lệ

| Mục tiêu | Options thường dùng |
| --- | --- |
| Tạo mới hoặc ghi đè file | Không truyền options |
| Append, tạo nếu chưa có | `CREATE`, `APPEND` |
| Chỉ ghi nếu file chưa tồn tại | `CREATE_NEW` |
| Ghi vào file đã tồn tại, không tạo mới | `WRITE`, `TRUNCATE_EXISTING` |

`APPEND` không được kết hợp với `TRUNCATE_EXISTING`. Nếu truyền tổ hợp option không hợp lệ, API ném `IllegalArgumentException`. Khi chỉ định options, hãy chủ động hiểu tác dụng của từng option thay vì nghĩ rằng API tự bổ sung toàn bộ mặc định.

## 7. Đọc và ghi trong một chương trình hoàn chỉnh

Ví dụ sau tạo file tạm, ghi UTF-8, nối thêm một dòng, đọc lại bằng overload mặc định và xác nhận nội dung. Ví dụ sử dụng `Path.of`, `Files.readString` và `Files.writeString`, đều có từ Java 11.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FilesStringDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("files-string-", ".txt");

        try {
            // Tạo nội dung đầu tiên; mặc định UTF-8 và ghi đè.
            Files.writeString(file, "Cà phê\n");

            // Append thêm nội dung; vẫn UTF-8 theo hợp đồng overload.
            Files.writeString(
                    file,
                    "Tiếng Việt 🌍\n",
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);

            // Đọc toàn bộ nội dung bằng UTF-8 theo hợp đồng.
            String actual = Files.readString(file);
            String expected = "Cà phê\nTiếng Việt 🌍\n";

            if (!expected.equals(actual)) {
                throw new AssertionError("Nội dung đọc lại không khớp");
            }

            System.out.println(actual);
            System.out.println("Round-trip OK");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Để kiểm tra byte thực tế, có thể đọc byte file và in hex:

```java
import java.util.HexFormat;

byte[] bytes = Files.readAllBytes(file);
System.out.println(HexFormat.of().formatHex(bytes));
```

`HexFormat` có từ Java 17. Kiểm tra byte hữu ích khi cần xác minh file tuân theo hợp đồng UTF-8 thay vì chỉ nhìn chữ hiển thị trên terminal, nơi encoding của console có thể có quy tắc riêng.

## 8. Xử lý dữ liệu sai định dạng và lỗi I/O

### 8.1. Byte đầu vào không phải UTF-8 hợp lệ

`Files.readString(path)` dùng UTF-8 và ném `IOException` nếu gặp chuỗi byte malformed hoặc unmappable. Nó không âm thầm đoán charset khác và không thay byte lỗi bằng một ký tự hiển thị tùy ý.

Ví dụ một byte `E9` đứng riêng không phải một chuỗi UTF-8 hợp lệ:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("invalid-utf8.bin");

try {
    String text = Files.readString(file);
} catch (java.io.IOException e) {
    // Có thể là lỗi I/O hoặc byte không hợp lệ theo UTF-8.
    System.err.println("Không thể đọc nội dung theo UTF-8: " + e);
}
```

Nếu file thực sự được tạo bằng ISO-8859-1, dùng overload có charset:

```java
import java.nio.charset.StandardCharsets;

String text = Files.readString(
        file,
        StandardCharsets.ISO_8859_1);
```

Việc chọn charset phải dựa trên hợp đồng hoặc metadata đáng tin cậy, không dựa trên thử lần lượt nhiều charset đến khi kết quả trông hợp lý.

### 8.2. Ký tự không thể mã hóa khi ghi

Khi gọi overload có charset, nếu nội dung không thể mã hóa theo charset đó, `Files.writeString` ném `IOException`. Ví dụ:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Files.writeString(
        Path.of("ascii.txt"),
        "Tiếng Việt",
        StandardCharsets.US_ASCII);
```

US-ASCII không biểu diễn được các ký tự tiếng Việt. Hãy chọn encoding đúng theo hệ thống nhận, hoặc từ chối dữ liệu nếu hợp đồng không cho phép thay thế ký tự.

### 8.3. Lỗi I/O có thể xảy ra sau khi file đã bị tạo hoặc cắt ngắn

`Files.writeString` đảm bảo đóng file sau khi ghi xong hoặc khi lỗi xảy ra, nhưng không phải transaction. Nếu đang ghi đè một file đã tồn tại, lỗi có thể xảy ra sau khi file bị cắt ngắn hoặc sau khi một phần dữ liệu đã được ghi.

Với cấu hình hoặc dữ liệu quan trọng, cân nhắc quy trình an toàn hơn:

1. Ghi nội dung hoàn chỉnh vào file tạm trong cùng hệ thống file.
2. Đóng file và kiểm tra nội dung.
3. Di chuyển file tạm sang vị trí đích bằng `Files.move`, yêu cầu `ATOMIC_MOVE` nếu hệ thống file hỗ trợ và nghiệp vụ cần thay thế nguyên tử.
4. Xử lý trường hợp atomic move không được hỗ trợ hoặc file đích không thể thay thế theo chính sách của nền tảng.

Đừng coi một lần gọi `writeString` là giao dịch nguyên tử hoặc bảo đảm dữ liệu đã được đồng bộ vật lý xuống thiết bị lưu trữ.

## 9. Khi nào không nên dùng `readString`/`writeString`?

Hai API này rất tiện khi toàn bộ nội dung phù hợp để nằm trong một `String`. Tuy nhiên, `readString` đọc **toàn bộ file vào bộ nhớ**. Javadoc nêu rõ phương thức không dành cho file rất lớn; file cực lớn có thể gây `OutOfMemoryError`, ví dụ vượt quá khoảng 2 GB.

Dùng API streaming nếu:

- File lớn, không thể giữ toàn bộ nội dung trong heap.
- Cần xử lý từng dòng hoặc từng khối.
- Muốn kiểm soát thời điểm đọc/ghi và flush.
- Cần xử lý dữ liệu tăng dần từ file hoặc pipeline.

Ví dụ streaming UTF-8:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("large-input.txt");
Path target = Path.of("filtered-output.txt");

try (BufferedReader reader =
             Files.newBufferedReader(source, StandardCharsets.UTF_8);
     BufferedWriter writer =
             Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        if (line.contains("ERROR")) {
            writer.write(line);
            writer.newLine();
        }
    }
}
```

Các phương thức `Files.newBufferedReader` và `Files.newBufferedWriter` cũng cho phép truyền charset rõ ràng. Chúng phù hợp khi cần xử lý file lớn theo dòng, trong khi `readString`/`writeString` phù hợp với nội dung vừa phải.

## 10. Phân biệt với các API Files gần tên

| API | Hành vi |
| --- | --- |
| `Files.readString(path)` | Đọc toàn bộ file thành một `String`, UTF-8 |
| `Files.readString(path, charset)` | Đọc toàn bộ file bằng charset chỉ định |
| `Files.readAllLines(path)` | Đọc các dòng thành `List<String>`, UTF-8; dấu kết thúc dòng không nằm trong từng phần tử |
| `Files.readAllBytes(path)` | Đọc byte thô, không decode charset |
| `Files.writeString(path, text)` | Ghi nguyên nội dung chuỗi, UTF-8; không tự thêm newline |
| `Files.writeString(path, text, charset)` | Ghi nguyên nội dung chuỗi bằng charset chỉ định |
| `Files.write(path, lines)` | Ghi từng phần tử như một dòng và thêm line separator của nền tảng |
| `Files.write(path, bytes)` | Ghi byte thô, không encode văn bản |

Không thay `readString` bằng `readAllBytes` rồi `new String(bytes)` nếu mục tiêu là UTF-8 rõ ràng. `new String(bytes)` dùng default charset của JVM; nếu muốn tự giải mã byte, phải truyền charset:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

Tuy nhiên, nếu mục tiêu chỉ là đọc file văn bản UTF-8 vào một chuỗi, `Files.readString(path)` thể hiện đúng ý định và có hợp đồng charset rõ ràng hơn.

## 11. Kiểm thử độc lập với default charset

Một phép kiểm thử tốt xác minh cả nội dung và byte, không dựa vào `Charset.defaultCharset()`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

Path file = Files.createTempFile("utf8-contract-", ".txt");

try {
    String text = "café - Tiếng Việt 🌍";
    Files.writeString(file, text);

    byte[] actual = Files.readAllBytes(file);
    byte[] expected = text.getBytes(StandardCharsets.UTF_8);

    if (!Arrays.equals(expected, actual)) {
        throw new AssertionError("writeString không tạo byte UTF-8 mong đợi");
    }

    String restored = Files.readString(file);
    if (!text.equals(restored)) {
        throw new AssertionError("readString không khôi phục đúng nội dung");
    }
} finally {
    Files.deleteIfExists(file);
}
```

Bài kiểm thử xác nhận overload không charset tuân theo UTF-8. Để kiểm tra rằng hành vi này không bị nhầm với default charset, có thể chạy chương trình trong môi trường kiểm thử hỗ trợ cấu hình default charset tương thích; kết quả byte của `Files.writeString(path, text)` vẫn phải là UTF-8, trong khi các API thực sự dùng default charset có thể cho kết quả khác.

Nên bổ sung các trường hợp:

1. File rỗng và file không tồn tại.
2. File chứa tiếng Việt, emoji và newline `\r\n`, `\n`.
3. File có byte UTF-8 sai định dạng, xác nhận `IOException`.
4. Ghi bằng charset không thể biểu diễn nội dung, xác nhận lỗi mã hóa.
5. Ghi đè, append, `CREATE_NEW` và file đích đã tồn tại.
6. File lớn để quyết định chuyển sang streaming.

## 12. Những nhận định dễ nhầm

- **“Java 18 mới làm `Files.readString(path)` dùng UTF-8.”** Sai. API có từ Java 11 và overload không charset đã quy định UTF-8 trước Java 18.
- **“`Files.readString(path)` lấy `Charset.defaultCharset()`.”** Sai. Nó tương đương overload truyền `StandardCharsets.UTF_8`.
- **“Mọi API Java bỏ trống charset đều dùng UTF-8.”** Sai. Hợp đồng phụ thuộc từng API; `new String(bytes)` và `getBytes()` không tham số vẫn phụ thuộc default charset.
- **“`writeString` tự thêm newline.”** Sai. Nó ghi các ký tự đúng như chuỗi cung cấp.
- **“`writeString` mặc định append.”** Sai. Nếu không truyền options, file cũ bị truncate.
- **“Đọc file sai UTF-8 sẽ tự đoán charset.”** Sai. `readString` ném `IOException` khi gặp byte malformed hoặc unmappable.
- **“`readString` phù hợp với file lớn bất kỳ.”** Sai. Phương thức đưa toàn bộ nội dung vào `String`; dùng streaming cho file lớn.
- **“Ghi xong nghĩa là file đã được cập nhật nguyên tử.”** Sai. `writeString` không cung cấp transaction và lỗi có thể xảy ra sau khi file đã bị tạo hoặc truncate.

## 13. Tài liệu tham khảo chính thức

- [Files — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): hợp đồng của `readString`, `writeString`, charset, `OpenOption`, lỗi I/O và giới hạn kích thước.
- [StandardOpenOption — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE`, `CREATE_NEW`, `APPEND`, `TRUNCATE_EXISTING`, `WRITE`.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18 và phạm vi ảnh hưởng.
- [StandardCharsets — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn như UTF-8, ISO-8859-1 và US-ASCII.

