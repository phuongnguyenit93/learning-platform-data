# PrintStream và PrintWriter: constructor charset, flush và kiểm tra lỗi xuất dữ liệu

## 1. Vì sao phải hiểu charset khi in văn bản?

`PrintStream` và `PrintWriter` cung cấp các phương thức tiện lợi như `print`, `println`, `printf` và `format`. Chúng thường được dùng để ghi log, tạo báo cáo, xuất nội dung ra file hoặc hiển thị thông tin cho người dùng.

Cả hai lớp đều nhận văn bản dạng ký tự và chuyển nó xuống đích xuất. Khi đích là `OutputStream` hoặc file, ký tự phải được **mã hóa thành byte bằng một charset**. Vì vậy, lựa chọn constructor có ảnh hưởng trực tiếp đến byte thực tế được ghi.

Hai điểm quan trọng trong phạm vi Java 18 và JDK hiện đại:

- Các constructor nhận `Charset` của `PrintStream` và `PrintWriter` đã có từ Java 10, tiếp tục được hỗ trợ.
- `PrintStream.charset()` được bổ sung từ Java 18, giúp truy vấn charset mà một `PrintStream` đang sử dụng.

`PrintStream` và `PrintWriter` có điểm chung là tiện lợi khi in văn bản, nhưng chúng có mô hình đích xuất và quy tắc tự động flush khác nhau. Cả hai cũng **không ném `IOException` từ các phương thức in thông thường**; muốn biết lỗi xuất dữ liệu, phải kiểm tra `checkError()`.

## 2. Luồng ký tự, byte và vị trí chọn charset

Khi đích là byte stream, quá trình xuất thường có cấu trúc:

```text
String / char / giá trị cần in
             |
             v
    PrintStream hoặc PrintWriter
             |
             | charset đã chọn
             v
       Encoder / chuyển mã
             |
             | byte
             v
      OutputStream / file
```

Charset được chọn tại một trong các vị trí:

- Constructor của `PrintStream` hoặc `PrintWriter` nhận `OutputStream` cùng `Charset`.
- Constructor mở file nhận `File`/tên file cùng `Charset`.
- `OutputStreamWriter` hoặc một `Writer` khác đã được cấu hình charset trước khi bọc bằng `PrintWriter`.

Nếu truyền một `Writer` đã có sẵn cho `PrintWriter`, lớp `PrintWriter` không giải mã hoặc chọn charset lại; charset đã được quyết định ở Writer bên dưới.

Ví dụ:

```java
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

PrintWriter writer = new PrintWriter(
        new OutputStreamWriter(outputStream, StandardCharsets.UTF_8));
```

Ở đây, `OutputStreamWriter` mã hóa ký tự thành byte UTF-8. `PrintWriter` chỉ cung cấp các phương thức in trên Writer đó.

## 3. Phân biệt hai lớp

| Đặc điểm | `PrintStream` | `PrintWriter` |
| --- | --- | --- |
| Kế thừa | `OutputStream` | `Writer` |
| Dữ liệu chính | In ký tự thành byte; cũng hỗ trợ ghi byte thô | In và ghi ký tự |
| Charset | Constructor có thể chọn charset; `charset()` có từ Java 18 | Charset do Writer bên dưới hoặc constructor có `Charset` quyết định |
| Ghi byte thô | Có `write(int)`, `write(byte[], ...)`, `writeBytes(byte[])` | Không có API ghi byte thô |
| Tự động flush | Có thể flush khi ghi byte array, gọi `println`, hoặc ghi newline `'\n'` | Chỉ flush khi gọi `println`, `printf` hoặc `format` nếu `autoFlush=true` |
| Lỗi I/O | Không ném `IOException` từ hoạt động thông thường; ghi nhận trạng thái lỗi | Các phương thức không ném lỗi I/O; ghi nhận trạng thái lỗi |
| Kiểm tra lỗi | `checkError()` | `checkError()` |

Chọn `PrintStream` khi cần một `OutputStream` có thêm các phương thức in và có thể cần ghi byte thô. Chọn `PrintWriter` khi làm việc chủ yếu với văn bản và muốn dùng abstraction `Writer`.

## 4. Constructor có charset của PrintStream

### 4.1. Dùng OutputStream có sẵn

Các constructor hiện hành thường dùng:

```java
PrintStream(OutputStream out)
PrintStream(OutputStream out, boolean autoFlush)
PrintStream(OutputStream out, boolean autoFlush, Charset charset)
```

| Constructor | Charset | Tự động flush |
| --- | --- | --- |
| `new PrintStream(out)` | Default charset của JVM; nếu `out` là `PrintStream`, dùng charset của stream đó | Không |
| `new PrintStream(out, true)` | Như trên | Có |
| `new PrintStream(out, false, StandardCharsets.UTF_8)` | UTF-8 tường minh | Không |
| `new PrintStream(out, true, StandardCharsets.UTF_8)` | UTF-8 tường minh | Có |

Constructor nhận `Charset` với `OutputStream` có từ **Java 10**. Nên dùng overload này thay vì truyền tên charset dưới dạng `String` khi charset đã biết lúc biên dịch.

Ví dụ:

```java
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

OutputStream destination = obtainOutputStream();

try (PrintStream out = new PrintStream(
        destination, false, StandardCharsets.UTF_8)) {
    out.println("Xin chào, Tiếng Việt 🌍");
}
```

### 4.2. Mở file trực tiếp

`PrintStream` có constructor nhận `File` hoặc tên file cùng `Charset`:

```java
PrintStream(File file, Charset charset)
PrintStream(String fileName, Charset charset)
```

Các constructor này có từ Java 10. Chúng mở file để ghi; nếu file đã tồn tại thì nội dung cũ bị truncate về 0 byte. Nếu chưa tồn tại, file mới được tạo. Chúng không cung cấp tham số append.

```java
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

try (PrintStream out = new PrintStream(
        "report.txt", StandardCharsets.UTF_8)) {
    out.println("Báo cáo");
    out.println("Dữ liệu UTF-8");
}
```

Các constructor file có thể ném `IOException` khi mở hoặc tạo file thất bại. Hãy xử lý ngoại lệ ở nơi tạo stream.

### 4.3. Kiểm tra charset đang sử dụng từ Java 18

`PrintStream.charset()` được bổ sung trong **Java 18**:

```java
import java.io.PrintStream;

PrintStream out = System.out;
System.out.println(out.charset());
```

Phương thức trả về `Charset` mà PrintStream dùng để chuyển ký tự thành byte. Đây là cách kiểm tra trực tiếp charset của stream, hữu ích khi làm việc với `System.out`, `System.err` hoặc stream được cấu hình bởi môi trường.

Không nhầm `out.charset()` với `Charset.defaultCharset()`: hai giá trị có thể khác nhau.

## 5. Constructor có charset của PrintWriter

### 5.1. Bọc Writer có sẵn

```java
PrintWriter(Writer out)
PrintWriter(Writer out, boolean autoFlush)
```

Hai constructor này không chọn charset. Writer bên dưới đã chịu trách nhiệm chuyển ký tự thành byte nếu có tầng byte:

```java
import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

var encodedWriter = new OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8);

try (PrintWriter out = new PrintWriter(
        new BufferedWriter(encodedWriter), true)) {
    out.println("Nội dung UTF-8");
}
```

### 5.2. Nhận OutputStream và Charset

Các constructor thường dùng:

```java
PrintWriter(OutputStream out)
PrintWriter(OutputStream out, boolean autoFlush)
PrintWriter(OutputStream out, boolean autoFlush, Charset charset)
```

| Constructor | Charset | Tự động flush |
| --- | --- | --- |
| `new PrintWriter(out)` | Default charset của JVM; nếu `out` là `PrintStream`, dùng charset của PrintStream đó | Không |
| `new PrintWriter(out, true)` | Như trên | Có |
| `new PrintWriter(out, false, StandardCharsets.UTF_8)` | UTF-8 tường minh | Không |
| `new PrintWriter(out, true, StandardCharsets.UTF_8)` | UTF-8 tường minh | Có |

Overload nhận `Charset` có từ **Java 10**. Khác với `PrintStream`, constructor nhận `OutputStream` của `PrintWriter` cần truyền cả boolean `autoFlush` khi muốn chỉ định charset.

### 5.3. Mở file trực tiếp

`PrintWriter` cũng có constructor nhận `File` hoặc tên file cùng `Charset`:

```java
PrintWriter(File file, Charset charset)
PrintWriter(String fileName, Charset charset)
```

Các constructor này có từ Java 10. File đã tồn tại sẽ bị truncate; file chưa có sẽ được tạo. Constructor có thể ném `IOException` nếu mở hoặc tạo file thất bại.

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;

try (PrintWriter writer = new PrintWriter(
        "users.txt", StandardCharsets.UTF_8)) {
    writer.println("Nguyễn An");
    writer.println("Trần Bình");
}
```

`PrintWriter` không có constructor file trực tiếp nhận `append=true`. Nếu cần nối tiếp file, mở một `Writer` với `APPEND` rồi bọc nó bằng `PrintWriter` (xem phần 10).

### 5.4. PrintWriter không có charset()

Trong JDK hiện đại, `PrintWriter` không cung cấp phương thức `charset()` tương tự `PrintStream.charset()`. Nếu cần biết charset, hãy giữ lại thông tin charset tại nơi tạo Writer:

```java
Charset outputCharset = StandardCharsets.UTF_8;
Writer base = Files.newBufferedWriter(path, outputCharset);
PrintWriter writer = new PrintWriter(base);
```

Đừng suy đoán charset từ nội dung đã in hoặc từ default charset của JVM.

## 6. Java 18, JEP 400 và các luồng chuẩn

JEP 400 đặt UTF-8 làm default charset thông thường của Java SE từ Java 18. Điều này ảnh hưởng đến các constructor dựa vào default charset, ví dụ `new PrintWriter(fileName)` hoặc `new PrintStream(fileName)`.

Tuy nhiên, `System.out` và `System.err` là trường hợp cần phân biệt: charset của chúng được cấu hình riêng cho standard output và standard error, thông qua các thuộc tính `stdout.encoding` và `stderr.encoding` theo môi trường. Chúng không nhất thiết bằng `Charset.defaultCharset()`.

Trên Java 18+, có thể kiểm tra trực tiếp:

```java
import java.nio.charset.Charset;

System.out.println("Default: " + Charset.defaultCharset());
System.out.println("stdout:  " + System.out.charset());
System.out.println("stderr:  " + System.err.charset());
```

`PrintStream.charset()` có từ Java 18. Vì vậy, khi cần chẩn đoán ký tự tiếng Việt hiển thị sai trên terminal, hãy kiểm tra charset của chính stream đầu ra, đồng thời xem cấu hình terminal/console.

Với file, giao thức hoặc định dạng dữ liệu cần UTF-8, hãy truyền `StandardCharsets.UTF_8` tại constructor thay vì dựa vào default charset hoặc charset của terminal.

## 7. AutoFlush: hai lớp có hành vi khác nhau

`autoFlush` không có nghĩa là mọi lệnh `print()` đều tự flush. Quy tắc của từng lớp khác nhau.

### 7.1. PrintStream

Nếu `autoFlush=true`, `PrintStream` gọi `flush()` trên output stream bên dưới khi:

- Ghi một byte array.
- Gọi một phương thức `println`.
- Ghi ký tự newline hoặc byte `'\n'`.

Do đó, với PrintStream, việc ghi newline bằng một số phương thức ghi ký tự/byte có thể kích hoạt flush ngay cả khi không gọi `println()`.

### 7.2. PrintWriter

Nếu `autoFlush=true`, `PrintWriter` chỉ tự flush khi gọi một trong các phương thức:

- `println(...)`
- `printf(...)`
- `format(...)`

Gọi `write('\n')` hoặc `print("dòng\n")` không tự kích hoạt autoFlush chỉ vì chuỗi chứa newline.

### 7.3. Bảng so sánh

| Thao tác | `PrintStream(autoFlush=true)` | `PrintWriter(autoFlush=true)` |
| --- | --- | --- |
| `print("hello")` | Không tự flush chỉ vì gọi `print` | Không |
| `println("hello")` | Có | Có |
| `write('\n')` | Newline được ghi có thể kích hoạt flush | Không |
| `print("hello\n")` | Newline được ghi có thể kích hoạt flush | Không |
| `printf("%s", "hello")` | Không tự flush chỉ vì gọi `printf` | Có |
| Ghi byte array bằng `write(byte[])` | Có | Không có API byte tương ứng |

AutoFlush hữu ích với console hoặc giao thức tương tác cần đẩy dữ liệu sớm. Với ghi file số lượng lớn, flush sau từng dòng có thể làm giảm hiệu năng. Hãy chọn theo nhu cầu và vẫn đóng tài nguyên đúng cách.

## 8. flush(), close() và try-with-resources

`flush()` đẩy dữ liệu đang đệm xuống tầng bên dưới. Nó không đồng nghĩa dữ liệu đã được đồng bộ vật lý xuống ổ đĩa hoặc đã được bên nhận mạng xác nhận.

`close()` hoàn tất việc flush rồi đóng stream và tài nguyên bên dưới. Với file hoặc stream riêng do phương thức sở hữu, dùng try-with-resources:

```java
try (PrintWriter writer = new PrintWriter(
        Path.of("report.txt").toFile(), StandardCharsets.UTF_8)) {
    writer.println("Báo cáo hoàn tất");
}
```

Ví dụ với PrintStream:

```java
try (PrintStream out = new PrintStream(
        Path.of("report.txt").toFile(), StandardCharsets.UTF_8)) {
    out.println("Báo cáo hoàn tất");
}
```

Không cần gọi `flush()` ngay trước `close()` trong trường hợp thông thường vì `close()` đã flush. Gọi `flush()` giữa chừng khi stream vẫn phải mở nhưng bên nhận cần thấy dữ liệu ngay.

**Không đóng `System.out` hoặc `System.err` trong code ứng dụng thông thường.** Đây là các stream chuẩn dùng chung của tiến trình. Đóng chúng có thể làm những phần code khác không thể tiếp tục ghi. Hãy chỉ flush khi cần; để vòng đời của tiến trình quản lý stream chuẩn.

## 9. Kiểm tra lỗi bằng checkError()

### 9.1. Vì sao không bắt IOException quanh print()?

`PrintStream` không ném `IOException` trong hoạt động in thông thường; khi có lỗi ghi, nó đặt cờ lỗi nội bộ. `PrintWriter` cũng không ném lỗi I/O từ các phương thức ghi/in.

Điều này làm code tiện hơn cho console và báo cáo đơn giản, nhưng nếu ứng dụng cần biết việc xuất dữ liệu có thành công hay không, phải gọi `checkError()`.

```java
if (out.checkError()) {
    // Stream đã gặp IOException hoặc trạng thái lỗi đã được đặt.
}
```

### 9.2. checkError() làm gì?

`checkError()`:

1. Flush stream nếu stream chưa đóng.
2. Kiểm tra cờ lỗi nội bộ.
3. Trả `true` nếu stream đã gặp `IOException` hoặc trạng thái lỗi được đặt; ngược lại trả `false`.

Vì `checkError()` tự flush khi stream còn mở, gọi nó sau khi ghi có thể khiến dữ liệu được đẩy xuống tầng bên dưới. Nếu stream đã đóng, phương thức kiểm tra trạng thái lỗi đã lưu mà không flush lại.

Cờ lỗi là trạng thái tích lũy. Các phương thức `setError()` và `clearError()` là protected; code sử dụng thông thường không thể tùy tiện reset trạng thái này.

### 9.3. Ví dụ kiểm tra PrintWriter sau khi đóng

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

PrintWriter writer = new PrintWriter(
        Path.of("report.txt").toFile(), StandardCharsets.UTF_8);

try (writer) {
    writer.println("Dòng dữ liệu");
}

// checkError() sau close kiểm tra trạng thái lỗi đã ghi nhận.
if (writer.checkError()) {
    throw new IOException("Không thể ghi report.txt");
}
```

Constructor có thể ném `IOException` nếu không mở được file. Các phương thức `println`/`write` không ném `IOException`; vì vậy cần kiểm tra trạng thái sau khi ghi/đóng nếu việc xuất dữ liệu quan trọng.

Ví dụ tương tự với PrintStream:

```java
PrintStream out = new PrintStream(
        Path.of("output.txt").toFile(), StandardCharsets.UTF_8);

try (out) {
    out.println("Kết quả");
}

if (out.checkError()) {
    throw new IOException("Không thể ghi output.txt");
}
```

Nếu không cần xử lý lỗi riêng, try-with-resources vẫn là cách đóng tài nguyên đúng; nhưng đừng nhầm việc không có ngoại lệ từ `println()` với việc ghi chắc chắn thành công.

## 10. Ghi nối tiếp (append) khi cần giữ nội dung cũ

Các constructor mở file trực tiếp của `PrintStream` và `PrintWriter` ở chế độ ghi mới: nếu file tồn tại, nội dung cũ bị truncate. Chúng không có tham số append.

Để append, hãy mở stream bằng `Files` với `CREATE` và `APPEND`, sau đó bọc bằng lớp in.

### 10.1. Append với PrintWriter

```java
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path log = Path.of("events.log");

var writer = Files.newBufferedWriter(
        log,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);

try (PrintWriter out = new PrintWriter(writer)) {
    out.println("INFO|đã xử lý");
}
```

`Files.newBufferedWriter` quyết định charset và chế độ mở file; `PrintWriter` chỉ bọc writer đã cấu hình. Nếu muốn autoFlush, dùng `new PrintWriter(writer, true)`.

### 10.2. Append với PrintStream

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path log = Path.of("events.log");

var output = Files.newOutputStream(
        log,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);

try (PrintStream out = new PrintStream(
        output, false, StandardCharsets.UTF_8)) {
    out.println("INFO|đã xử lý");
}
```

`Files.newOutputStream` mở file ở chế độ append; PrintStream mã hóa ký tự theo UTF-8. Không mở cùng file bằng một writer truncate ở nơi khác trong lúc đang append.

`APPEND` chỉ ghi ở cuối file, không tự thêm dấu phân cách. `println()` thêm line separator theo nền tảng. Nếu file log hoặc giao thức yêu cầu newline cố định, hãy ghi separator được quy định rõ ràng.

## 11. Ghi byte thô và ghi ký tự qua PrintStream

Vì `PrintStream` là một `OutputStream`, nó có cả phương thức in ký tự và phương thức ghi byte thô. Hai loại thao tác này không giống nhau:

```java
out.print("café"); // Ký tự được encode theo out.charset()
out.write(bytes);  // Byte được ghi nguyên trạng, không encode lại
```

Nếu byte trong `bytes` đã được encode bằng UTF-8 nhưng `out.charset()` là charset khác, phần output có thể chứa hai encoding không nhất quán. Với `PrintStream` từ Java 18, có thể kiểm tra charset của stream bằng `out.charset()`.

`write(int)` của PrintStream ghi **một byte**, không phải ký tự Unicode. Để in ký tự, dùng `print(char)`, `print(String)` hoặc `println(...)`.

`PrintWriter` chỉ xử lý ký tự. Nó không có `write(byte[])`; nếu cần ghi byte thô, dùng `OutputStream` hoặc `PrintStream` phù hợp.

## 12. Lỗi mã hóa và giới hạn của checkError()

Một điểm quan trọng: `PrintStream` và `PrintWriter` luôn thay thế chuỗi ký tự malformed hoặc unmappable bằng replacement string mặc định của charset. Chúng không cung cấp constructor để chọn `CodingErrorAction.REPORT`.

Vì vậy:

- `checkError()` phát hiện lỗi I/O được stream ghi nhận.
- `checkError()` **không** báo rằng ký tự đã bị thay thế trong quá trình encode.
- Kết quả `false` không chứng minh byte đầu ra bảo toàn hoàn toàn nội dung gốc.
- Nếu cần từ chối dữ liệu không mã hóa được, phải kiểm tra bằng `CharsetEncoder` hoặc dùng `OutputStreamWriter` với encoder được cấu hình `CodingErrorAction.REPORT`.

Ví dụ cấu hình encoder nghiêm ngặt:

```java
import java.io.OutputStreamWriter;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var writer = new OutputStreamWriter(outputStream, encoder)) {
    writer.write("Tiếng Việt");
    writer.flush();
}
```

Với US-ASCII, nội dung tiếng Việt không thể biểu diễn; thao tác ghi/flush sẽ báo lỗi mã hóa dưới dạng ngoại lệ I/O. `OutputStreamWriter` trực tiếp cho phép ứng dụng nhận ngoại lệ, phù hợp khi tính đúng đắn của byte quan trọng hơn sự tiện lợi của `print()`.

Nếu cần vẫn có phương thức in định dạng, có thể tự xây một tầng kiểm tra trước khi chuyển dữ liệu sang PrintWriter/PrintStream. Không dựa vào `checkError()` để xác thực chất lượng encoding.

## 13. Locale trong printf và format không phải charset

`printf` và `format` có thể định dạng số theo locale. Đây là quy tắc định dạng văn bản, khác với charset dùng để chuyển ký tự thành byte.

```java
import java.io.PrintWriter;
import java.util.Locale;

PrintWriter writer = new PrintWriter(System.out, true);
writer.printf(Locale.US, "Amount: %.2f%n", 1234.5);
writer.printf(Locale.GERMANY, "Betrag: %.2f%n", 1234.5);
writer.flush(); // Không đóng System.out vì đây là stream chuẩn dùng chung.
```

Locale ảnh hưởng dấu thập phân và cách trình bày số. Charset ảnh hưởng byte được tạo từ văn bản. Một output có thể dùng UTF-8 nhưng vẫn định dạng số theo locale không mong muốn.

Nếu định dạng file hoặc giao thức quy định dấu thập phân cụ thể, hãy truyền locale rõ ràng cho `printf(Locale, ...)` hoặc chuẩn hóa dữ liệu trước khi ghi.

## 14. Ví dụ hoàn chỉnh: ghi báo cáo UTF-8 và xác minh trạng thái lỗi

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class PrintWriterReport {
    public static void main(String[] args) throws IOException {
        PrintWriter writer = new PrintWriter(
                Path.of("report.txt").toFile(),
                StandardCharsets.UTF_8);

        try (writer) {
            writer.println("Báo cáo");
            writer.printf("Người dùng: %s%n", "Nguyễn An");
            writer.println("Trạng thái: hoàn tất");
        }

        if (writer.checkError()) {
            throw new IOException("Lỗi khi ghi report.txt");
        }
    }
}
```

Ví dụ dùng constructor charset có từ Java 10, hoạt động trên Java 18+ và JDK hiện đại. File được tạo hoặc truncate nếu đã tồn tại. Sau khi đóng, `checkError()` kiểm tra cờ lỗi mà PrintWriter đã ghi nhận.

Nếu cần append, thay constructor file bằng `Files.newBufferedWriter` với `CREATE` và `APPEND`, rồi bọc writer đó như phần 10.

## 15. Kiểm thử charset bằng byte thực tế

Đừng chỉ nhìn output trên terminal để kết luận encoding đúng. Có thể ghi vào `ByteArrayOutputStream`, sau đó so sánh byte mong đợi:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String text = "café - Tiếng Việt 🌍";
ByteArrayOutputStream bytes = new ByteArrayOutputStream();

try (PrintStream out = new PrintStream(
        bytes, false, StandardCharsets.UTF_8)) {
    out.print(text);
}

byte[] actual = bytes.toByteArray();
byte[] expected = text.getBytes(StandardCharsets.UTF_8);

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("PrintStream không ghi byte UTF-8 mong đợi");
}
```

Bài kiểm thử này xác nhận constructor đã chọn UTF-8 và các ký tự mẫu được encode thành byte mong đợi. Có thể bổ sung kiểm thử `PrintWriter` bằng `ByteArrayOutputStream` và `new PrintWriter(bytes, false, StandardCharsets.UTF_8)`.

Nên kiểm thử thêm:

1. File đã tồn tại để xác nhận constructor file truncate đúng như hợp đồng.
2. Append bằng `Files.newOutputStream`/`Files.newBufferedWriter`.
3. `autoFlush=true` với từng lớp để xác nhận khác biệt giữa `println`, `print` và `write('\n')`.
4. Một OutputStream mô phỏng lỗi I/O để xác nhận `checkError()` trả `true`.
5. Ký tự ngoài khả năng biểu diễn của charset giới hạn để hiểu hành vi replacement.
6. `System.out.charset()` so với `Charset.defaultCharset()` trên môi trường chạy thật.

## 16. Những nhận định dễ nhầm

- **“Java 18 dùng UTF-8 mặc định nên constructor không charset luôn phù hợp.”** Không. File hoặc đích xuất có thể có hợp đồng charset riêng; `System.out`/`System.err` còn có charset cấu hình riêng.
- **“PrintWriter tự chọn UTF-8 vì nó là writer.”** Sai. Charset đến từ Writer bên dưới hoặc constructor nhận Charset; overload OutputStream không charset dựa vào default charset (hoặc charset của PrintStream nếu nguồn là PrintStream).
- **“PrintStream và PrintWriter autoFlush giống nhau.”** Sai. PrintStream còn flush khi byte array hoặc newline được ghi; PrintWriter chỉ flush tự động khi gọi `println`, `printf`, `format`.
- **“println luôn ghi byte LF.”** Sai. Nó dùng line separator của nền tảng.
- **“print/write luôn ném IOException nếu file không ghi được.”** Sai. Hai lớp giữ cờ lỗi; dùng `checkError()`.
- **“checkError() kiểm tra ký tự đã bị thay thế khi encode.”** Sai. Nó kiểm tra lỗi I/O hoặc trạng thái lỗi nội bộ, không xác thực dữ liệu đã được bảo toàn.
- **“PrintStream.write(byte[]) sẽ encode byte theo charset của stream.”** Sai. Phương thức ghi byte thô nguyên trạng; chỉ các phương thức in ký tự mới thực hiện chuyển mã.
- **“Có thể append bằng constructor PrintWriter(File, Charset).”** Sai. Constructor file mở để ghi mới/truncate; muốn append hãy mở bằng `Files` với `APPEND`, sau đó bọc Writer.
- **“Có thể đóng System.out sau khi dùng PrintWriter.”** Không nên. Đóng wrapper có thể đóng stream chuẩn dùng chung của tiến trình.

## 17. Tài liệu tham khảo chính thức

- [PrintStream — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintStream.html): constructor `Charset`, `charset()`, `autoFlush`, `flush`, `close`, `checkError` và hành vi replacement.
- [PrintWriter — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintWriter.html): constructor nhận `Charset`, quy tắc autoFlush, `checkError`, `flush`, `close` và giới hạn xử lý encoding.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18.
- [System — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html): charset của `System.out`, `System.err` và các thuộc tính `stdout.encoding`, `stderr.encoding`.
- [CharsetEncoder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát lỗi encode bằng `CodingErrorAction.REPORT`.

