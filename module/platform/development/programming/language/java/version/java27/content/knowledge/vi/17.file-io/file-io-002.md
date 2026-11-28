# Đọc ghi văn bản và dữ liệu nhị phân có bộ đệm trong Java 27

**File I/O (Input/Output)** là quá trình đọc dữ liệu từ tệp và ghi dữ liệu ra tệp. Trong Java, dữ liệu thường được xử lý theo hai hướng: **văn bản** (ký tự, dòng, mã hóa Unicode) và **nhị phân** (chuỗi byte, hình ảnh, tệp nén, định dạng dữ liệu có cấu trúc). Khi thao tác nhiều lần với tệp, **buffering** (bộ đệm) giúp gom những lần đọc/ghi nhỏ thành thao tác I/O hiệu quả hơn.

Bài này thuộc chương **Tệp và nhập xuất**, trong module **Java 27 và các kiến thức liên quan**. Nội dung sử dụng những API Java hiện hành, đặc biệt là `java.nio.file.Path`, `Files`, `BufferedReader`, `BufferedWriter`, `BufferedInputStream`, `BufferedOutputStream`, `DataInputStream` và `DataOutputStream`. Không dùng cách tiếp cận legacy làm lựa chọn chính và không cần bật tính năng preview.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Phân biệt tệp văn bản, tệp nhị phân, byte, ký tự và charset.
- Sử dụng `Path` và `Files` thay vì ghép đường dẫn bằng chuỗi.
- Đọc/ghi văn bản UTF-8 bằng `Files.newBufferedReader` và `Files.newBufferedWriter`.
- Đọc/ghi byte theo khối bằng `BufferedInputStream` và `BufferedOutputStream`.
- Sử dụng `DataInputStream` và `DataOutputStream` cho các giá trị nguyên thủy trong định dạng nhị phân tự định nghĩa.
- Đóng tài nguyên bằng **try-with-resources**, hiểu `flush()` và cách xử lý `IOException`.
- Tránh nhầm lẫn bộ đệm, mã hóa, EOF, ghi đè tệp và lưu trữ dữ liệu lớn.
- Viết các ví dụ Java hoàn chỉnh để kiểm tra văn bản, copy tệp và đọc/ghi record nhị phân.

## 2. Văn bản và nhị phân không phải cùng một lớp trừu tượng

Một tệp trên hệ thống lưu trữ về cơ bản là một chuỗi byte. Cách ứng dụng **diễn giải** chuỗi byte đó quyết định nó được coi là văn bản hay nhị phân.

| Khía cạnh | Văn bản | Nhị phân |
|---|---|---|
| Đơn vị ở tầng ứng dụng | Ký tự, chuỗi, dòng | Byte hoặc cấu trúc byte |
| Ví dụ | `.txt`, `.csv`, `.json`, mã nguồn | Ảnh, âm thanh, tệp nén, định dạng record riêng |
| API thuận tiện | `Reader`, `Writer`, `BufferedReader` | `InputStream`, `OutputStream`, `DataInputStream` |
| Vai trò charset | Bắt buộc khi đổi byte thành ký tự và ngược lại | Không tự mã hóa ký tự, trừ khi định dạng nhị phân tự quy định |
| Dấu xuống dòng | Có thể quan trọng, phụ thuộc định dạng | Chỉ là byte nếu định dạng tự định nghĩa như vậy |
| Lỗi thường gặp | Sai UTF-8, mất dấu dòng, chuẩn hóa không mong muốn | Đọc thiếu byte, sai thứ tự trường, sai byte order |

Ví dụ chuỗi `"Chào"` gồm các ký tự Unicode; số **byte** của nó khi mã hóa UTF-8 không nhất thiết bằng số đơn vị `char` của Java hay số ký tự mà người dùng nhìn thấy. Nếu cần đọc nội dung văn bản, hãy dùng `Reader` và charset. Nếu cần giữ **nguyên vẹn từng byte**, hãy dùng `InputStream`.

**Nguyên tắc cốt lõi:** không đọc ảnh hoặc tệp zip bằng `BufferedReader` rồi ghi lại bằng `BufferedWriter`. Việc giải mã và mã hóa lại có thể làm thay đổi byte và phá định dạng. Ngược lại, khi xử lý văn bản, không tự ghép từng byte thành `char` mà không có charset rõ ràng.

## 3. java.nio.file.Path và Files

`Path` mô tả một đường dẫn trong hệ thống tệp; `Files` cung cấp nhiều thao tác mở, đọc, ghi, sao chép và quản lý tệp.

```java
import java.nio.file.Path;
import java.nio.file.Files;

Path directory = Path.of("data");
Path file = directory.resolve("notes.txt");

Files.createDirectories(directory);
```

Trong ví dụ:

- `Path.of("data")` tạo đối tượng đường dẫn tương đối, không tự tạo thư mục trên đĩa.
- `resolve("notes.txt")` nối một thành phần đường dẫn theo cơ chế của `Path`.
- `Files.createDirectories(directory)` tạo thư mục cần thiết nếu chưa tồn tại, và không báo lỗi chỉ vì thư mục đã tồn tại.

### 3.1. Đường dẫn tương đối và tuyệt đối

```java
Path relative = Path.of("data", "notes.txt");
Path absolute = relative.toAbsolutePath();

System.out.println(relative);
System.out.println(absolute);
```

Đường dẫn tương đối được giải quyết dựa trên working directory của tiến trình và nhà cung cấp hệ thống tệp. Không nên giả định chương trình lúc nào cũng chạy từ cùng thư mục khi triển khai ở IDE, container hay máy chủ.

`Path` trừu tượng hóa cách biểu diễn đường dẫn trên từng hệ điều hành. Tránh tự ghép các thành phần đường dẫn bằng ký tự `"/"` hoặc `"\\"` không có kiểm soát.

### 3.2. Mở tệp theo đúng ý định

Việc **đọc** một tệp có sẵn không giống việc **tạo mới** hoặc **ghi đè**:

| Nhu cầu | API / option thường dùng |
|---|---|
| Đọc văn bản UTF-8 theo dòng | `Files.newBufferedReader(path, UTF_8)` |
| Ghi văn bản, tạo mới hoặc ghi đè | `Files.newBufferedWriter(path, UTF_8)` |
| Ghi tiếp vào cuối tệp | `CREATE` và `APPEND` |
| Chỉ tạo nếu chưa có | `CREATE_NEW` |
| Đọc từng byte qua stream | `Files.newInputStream(path)` |
| Ghi byte, tạo mới hoặc ghi đè | `Files.newOutputStream(path)` |
| Sao chép trực tiếp | `Files.copy(source, target, ...)` |

Khi không truyền option, `Files.newBufferedWriter` và `Files.newOutputStream` hoạt động theo chế độ tạo tệp nếu cần và **truncate** nội dung tệp hiện có trước khi ghi. Nếu có dữ liệu cần giữ, phải chủ động chọn `APPEND` hoặc thiết kế cách cập nhật khác.

Không nên dựa trên `Files.exists(path)` như một kiểm tra quyền/điều kiện cuối cùng trước khi mở: tệp có thể thay đổi giữa lúc kiểm tra và lúc sử dụng. Hãy mở với option đúng và xử lý exception tương ứng.

## 4. Buffering là gì và giúp ích như thế nào?

Hình dung chương trình cần ghi 100.000 phần nhỏ vào tệp. Nếu mỗi phần nhỏ tạo ra thao tác I/O riêng qua nhiều tầng, chi phí tương tác với hệ thống có thể đáng kể. Buffering giữ một vùng nhớ tạm thời:

```text
Viết:
  Chương trình -> BufferedWriter/BufferedOutputStream
               -> bộ đệm trong bộ nhớ -> tầng tệp/OS

Đọc:
  Tầng tệp/OS -> bộ đệm trong bộ nhớ
              -> BufferedReader/BufferedInputStream
              -> Chương trình
```

### 4.1. Bộ đệm ghi

Khi gọi `write`:

1. Dữ liệu có thể được đưa vào buffer trong bộ nhớ.
2. Khi buffer đầy hoặc được flush/close, dữ liệu đang chờ được chuyển xuống stream/writer bên dưới.
3. Stream bên dưới giao dữ liệu cho tầng hệ thống tệp.

Nhờ đó, chương trình có thể gọi `write` nhiều lần cho các đoạn nhỏ mà không cần mỗi lần tương ứng một thao tác ghi vật lý độc lập.

### 4.2. Bộ đệm đọc

Khi gọi `read`:

1. Nếu buffer đang chứa dữ liệu, ứng dụng nhận dữ liệu ngay từ bộ đệm.
2. Khi buffer hết dữ liệu, bộ đệm có thể được nạp thêm từ nguồn.
3. Chương trình tiếp tục đọc theo từng ký tự, dòng hoặc block.

**Buffering không thay đổi ý nghĩa của dữ liệu.** Nó chỉ thay đổi cách và thời điểm dữ liệu được truyền qua các tầng.

### 4.3. Những điều buffering không bảo đảm

- Không làm chương trình tự động bất đồng bộ.
- Không bảo đảm mọi lời gọi `write` lập tức hiển thị trong tệp cho tiến trình khác.
- Không bảo đảm dữ liệu đã được lưu bền vững trên thiết bị vật lý khi `flush` trả về.
- Không biến thao tác ghi thành một transaction.
- Không tự giải quyết tranh chấp nếu nhiều thread hoặc tiến trình cùng sửa một tệp.
- Không tự giải mã UTF-8: phần mã hóa thuộc về `Reader`, `Writer` và `Charset`.

`Files.newBufferedReader` và `Files.newBufferedWriter` **đã trả về đối tượng có bộ đệm**; không cần bọc thêm một `BufferedReader` hoặc `BufferedWriter` cùng loại chỉ để "tăng hiệu năng" theo thói quen.

## 5. Đọc văn bản UTF-8 bằng Files.newBufferedReader

Ví dụ đọc từng dòng:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

class ReadTextExample {
    static void showFile(Path file) throws IOException {
        try (BufferedReader reader =
                Files.newBufferedReader(file, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
        }
    }
}
```

Giải thích:

- `Files.newBufferedReader` mở một reader có bộ đệm cho tệp.
- `StandardCharsets.UTF_8` nói rõ cách giải mã byte thành ký tự.
- `reader.readLine()` trả một dòng văn bản **không chứa dấu kết thúc dòng**.
- Khi đến cuối tệp, `readLine()` trả `null`.
- Khối `try-with-resources` gọi `close()` khi rời khối, kể cả khi xảy ra exception.

### 5.1. EOF khác dòng rỗng

Một tệp có thể chứa một dòng trống hợp lệ. Khi ấy `readLine()` có thể trả `""`, không phải `null`.

Sai:

```java
// Sai: dừng ngay khi gặp một dòng trống.
// while (!(line = reader.readLine()).isEmpty()) {
//     ...
// }
```

Đúng:

```java
String line;
while ((line = reader.readLine()) != null) {
    // line có thể là "", nhưng đây vẫn là một dòng dữ liệu.
}
```

Vì thế **EOF** là điều kiện `null`, không phải chuỗi rỗng.

### 5.2. readLine xử lý những dấu kết thúc dòng nào?

`BufferedReader.readLine()` nhận diện các dạng dấu kết thúc dòng phổ biến như LF (`\n`), CR (`\r`) hoặc CRLF (`\r\n`). Kết quả trả về đã loại bỏ dấu kết thúc dòng.

Hệ quả: đọc bằng `readLine()` rồi ghi lại bằng `newLine()` có thể **chuẩn hóa dấu kết thúc dòng** theo môi trường hiện tại. Nếu cần sao chép từng byte hoặc bảo toàn chính xác nội dung gốc, nên dùng byte stream hoặc một cơ chế đọc không làm mất thông tin dấu dòng.

### 5.3. Không dùng ready() để kiểm tra hết tệp

`BufferedReader.ready()` cho biết liệu lời gọi đọc có thể thực hiện mà không bị chặn theo hợp đồng; **không phải phương thức kiểm tra EOF**.

Không dùng:

```java
// Không nên:
// while (reader.ready()) {
//     ...
// }
```

Đọc đến EOF bằng `readLine() != null` hoặc `read(...) != -1` tùy loại dữ liệu.

### 5.4. Tệp có dòng cực dài

Buffering giúp đọc theo dòng thuận tiện nhưng mỗi lời gọi `readLine()` cần xây dựng chuỗi của cả dòng. Nếu nguồn không đáng tin cậy có một dòng dài hàng trăm MB, dùng `readLine()` vẫn có thể tiêu thụ bộ nhớ rất lớn.

Khi cần giới hạn tài nguyên, hãy áp dụng giới hạn dung lượng tệp, độ dài dòng hoặc dùng bộ phân tích dạng streaming được thiết kế cho dữ liệu lớn.

## 6. Ghi văn bản UTF-8 bằng Files.newBufferedWriter

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

class WriteTextExample {
    static void write(Path file) throws IOException {
        try (BufferedWriter writer =
                Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {

            writer.write("Dòng thứ nhất");
            writer.newLine();
            writer.write("Dòng thứ hai");
            writer.newLine();
        }
    }
}
```

`writer.write(...)` đưa ký tự qua writer có bộ đệm và bộ mã hóa; `newLine()` ghi chuỗi phân cách dòng do hệ thống xác định. Khi `try` kết thúc, writer được đóng và dữ liệu còn trong buffer được đẩy xuống writer/stream nền.

Nếu **định dạng dữ liệu bắt buộc LF** trên mọi hệ điều hành (ví dụ một giao thức cụ thể), thay `newLine()` bằng `write("\n")` theo hợp đồng của định dạng đó. Không nên giả định `newLine()` luôn là `\n` trên mọi môi trường.

### 6.1. Ghi đè, ghi tiếp và tạo mới

Các lựa chọn phổ biến của `StandardOpenOption`:

```java
import static java.nio.file.StandardOpenOption.*;

// Tạo nếu chưa có; ghi đè nội dung cũ.
try (var writer = Files.newBufferedWriter(
        file, StandardCharsets.UTF_8,
        CREATE, TRUNCATE_EXISTING, WRITE)) {
    writer.write("Nội dung mới");
}

// Tạo nếu chưa có; ghi tiếp vào cuối.
try (var writer = Files.newBufferedWriter(
        file, StandardCharsets.UTF_8,
        CREATE, APPEND)) {
    writer.write("Dòng bổ sung");
    writer.newLine();
}

// Không cho vô tình ghi đè tệp đã tồn tại.
try (var writer = Files.newBufferedWriter(
        file, StandardCharsets.UTF_8,
        CREATE_NEW, WRITE)) {
    writer.write("Tệp mới");
}
```

Ba đoạn là **các lựa chọn riêng**, không nên chạy tuần tự trên cùng tệp để mô phỏng một thao tác: đoạn `CREATE_NEW` sẽ báo lỗi nếu tệp đã tồn tại.

- `TRUNCATE_EXISTING` làm tệp cũ mất nội dung khi mở để ghi.
- `APPEND` ghi vào cuối tệp, nhưng khi có nhiều tiến trình cùng append thì mức độ nguyên tử phụ thuộc filesystem/provider.
- `CREATE_NEW` dành cho trường hợp không cho phép tệp đã tồn tại; giúp tránh cuộc đua giữa kiểm tra tồn tại và tạo tệp.
- Không kết hợp `APPEND` với `TRUNCATE_EXISTING` một cách tùy tiện: hai ý nghĩa này xung đột và tổ hợp có thể bị từ chối.

### 6.2. Một lưu ý về BOM

UTF-8 không bắt buộc có **byte order mark (BOM)**. Tệp được ghi bởi `Files.newBufferedWriter(..., UTF_8)` không cần chèn BOM để mã hóa UTF-8 hoạt động.

Nếu nguồn có BOM, tầng đọc có thể đưa ký tự `U+FEFF` vào đầu nội dung tùy cách giải mã và xử lý. Nếu dữ liệu đi qua nhiều hệ thống, hãy định nghĩa rõ chính sách BOM và kiểm thử, thay vì tự xóa ký tự đầu tiên trong mọi file.

## 7. Ví dụ hoàn chỉnh: tạo, ghi và đọc tệp văn bản

Tạo file `BufferedTextDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;

public class BufferedTextDemo {

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("java-text-demo-");
        Path file = directory.resolve("notes.txt");

        try {
            List<String> lines = List.of(
                    "Xin chào Java 27",
                    "",
                    "Đây là ví dụ I/O có bộ đệm",
                    "Dòng cuối"
            );

            try (BufferedWriter writer = Files.newBufferedWriter(
                    file,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {

                for (String line : lines) {
                    writer.write(line);
                    writer.newLine();
                }
            }

            try (BufferedReader reader = Files.newBufferedReader(
                    file, StandardCharsets.UTF_8)) {

                String line;
                int lineNumber = 0;

                while ((line = reader.readLine()) != null) {
                    lineNumber++;
                    System.out.printf("%d: [%s]%n", lineNumber, line);
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BufferedTextDemo.java
java BufferedTextDemo
```

Kết quả dự kiến:

```text
1: [Xin chào Java 27]
2: []
3: [Đây là ví dụ I/O có bộ đệm]
4: [Dòng cuối]
```

**Điểm cần quan sát:**

1. `Files.createTempDirectory` tạo thư mục demo mới, tránh ghi đè dữ liệu sẵn có.
2. `CREATE_NEW` chỉ tạo tệp `notes.txt` khi nó chưa tồn tại.
3. `try-with-resources` đóng writer trước khi reader bắt đầu đọc.
4. Dòng rỗng vẫn được in với `[]`, không bị hiểu nhầm là EOF.
5. Khối `finally` xóa tệp/thư mục demo. Đây là ví dụ học tập; ứng dụng thật cần chính sách lưu dữ liệu riêng.

Trong chương trình thực tế, lỗi xóa tệp ở `finally` cũng là một `IOException` cần được xử lý theo mục tiêu nghiệp vụ. Nếu dữ liệu quan trọng, không nên xóa tệp tự động sau khi ghi thành công.

## 8. Files.readString/writeString và Files.lines: chọn đúng trường hợp

Bên cạnh buffered reader/writer, `Files` có các API ngắn gọn hơn:

```java
Path file = Path.of("data", "message.txt");

// Khi nội dung nhỏ và có thể lưu trọn trong bộ nhớ:
Files.writeString(file, "Xin chào\n", StandardCharsets.UTF_8);
String content = Files.readString(file, StandardCharsets.UTF_8);
```

`Files.readString` tiện cho tệp nhỏ, nhưng đọc toàn bộ nội dung vào `String`. `Files.readAllLines` cũng đọc toàn bộ các dòng vào bộ nhớ. Khi nội dung lớn, nên xử lý theo dòng hoặc theo khối.

### 8.1. Files.lines là stream cần đóng

```java
import java.util.stream.Stream;

try (Stream<String> lines =
        Files.lines(file, StandardCharsets.UTF_8)) {

    long nonBlankCount = lines.filter(line -> !line.isBlank())
            .count();

    System.out.println(nonBlankCount);
}
```

`Files.lines` trả một `Stream<String>` được xây dựng từ nguồn tệp, nên phải đóng stream bằng `try-with-resources`. Một lỗi I/O xảy ra khi thực sự duyệt dòng có thể được báo bằng `UncheckedIOException` trong quá trình thực thi stream.

### 8.2. Chọn API nhanh

| Mục tiêu | Lựa chọn |
|---|---|
| Tệp cấu hình văn bản nhỏ | `Files.readString` |
| Ghi văn bản nhỏ một lần | `Files.writeString` |
| Duyệt từng dòng, có logic vòng lặp và xử lý lỗi cụ thể | `Files.newBufferedReader` |
| Xử lý dòng theo pipeline | `Files.lines` kèm try-with-resources |
| Ghi nhiều dòng khi đang tạo dữ liệu | `Files.newBufferedWriter` |
| Bảo toàn nguyên vẹn byte của tệp | `Files.copy` hoặc byte stream |

## 9. InputStream và OutputStream cho dữ liệu nhị phân

`InputStream` đọc byte, `OutputStream` ghi byte. Chúng không tự xác định charset; byte có thể là nội dung ảnh, dữ liệu nén, một giao thức nhị phân hoặc văn bản chưa giải mã.

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("data", "source.bin");
Path target = Path.of("data", "copy.bin");

try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    // Có thể đọc/ghi từng byte hoặc từng block ở đây.
}
```

Ở cấp byte stream:

- `read()` trả giá trị byte dạng `int` trong miền 0..255, hoặc `-1` tại EOF.
- `read(byte[])` trả **số byte thực sự đọc** trong lần gọi, hoặc `-1` khi EOF.
- `write(int)` ghi một byte thấp của giá trị truyền vào.
- `write(byte[], offset, length)` ghi một đoạn byte theo offset và length.

### 9.1. Đừng nhầm read(byte[]) luôn đọc đầy buffer

Đây là lỗi phổ biến:

```java
byte[] buffer = new byte[8192];

// Sai nếu coi mọi lần đọc đều đủ 8192 byte:
int read = in.read(buffer);
// out.write(buffer); // Sai: có thể ghi cả byte còn sót ở phần chưa được đọc.
```

Cách đúng là sử dụng **giá trị trả về**:

```java
int count;
while ((count = in.read(buffer)) != -1) {
    out.write(buffer, 0, count);
}
```

Giá trị `count` có thể nhỏ hơn độ dài mảng, đặc biệt với nhiều loại nguồn dữ liệu. Đối với `InputStream.read(byte[])` với buffer có độ dài dương, cách xử lý EOF là `-1`; không lấy số byte cố định làm tín hiệu kết thúc.

## 10. BufferedInputStream và BufferedOutputStream

`BufferedInputStream`/`BufferedOutputStream` bọc một byte stream khác để thêm bộ đệm:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;

try (InputStream in =
             new BufferedInputStream(Files.newInputStream(source));
     OutputStream out =
             new BufferedOutputStream(Files.newOutputStream(target))) {

    byte[] buffer = new byte[16 * 1024];
    int count;

    while ((count = in.read(buffer)) != -1) {
        out.write(buffer, 0, count);
    }
}
```

Đây là luồng **copy byte nguyên vẹn**: không decode sang ký tự nên có thể dùng cho nhiều định dạng file.

### 10.1. Có cần cả BufferedInputStream và mảng byte[] không?

Hai cơ chế có vai trò khác nhau:

- `BufferedInputStream` quản lý bộ đệm giữa nguồn I/O và các lời gọi `read`.
- Mảng `byte[] buffer` là vùng chứa do **ứng dụng** sử dụng để chuyển dữ liệu theo block.

Trong ví dụ copy, việc đọc theo block đã giúp giảm các thao tác đọc nhỏ; thêm `BufferedInputStream` có thể có ích trong một số trường hợp nhưng **không nhất thiết làm copy nhanh hơn**. Hiệu suất phụ thuộc nguồn, đích, provider và kích thước block.

Khi chỉ cần sao chép tệp, `Files.copy(source, target)` có thể đơn giản và phù hợp hơn so với tự triển khai vòng lặp. Chọn luồng thủ công khi cần đếm byte, tính checksum, áp dụng giới hạn hoặc biến đổi từng block.

### 10.2. Không dùng available() làm kích thước toàn bộ file

`InputStream.available()` chỉ là ước lượng số byte có thể đọc mà không bị chặn ở thời điểm gọi theo contract của stream. Nó **không phải** kích thước tệp và không phải điều kiện kiểm tra EOF.

Không dùng:

```java
// Không nên:
// byte[] allBytes = new byte[in.available()];
```

Nếu cần kích thước tệp, `Files.size(path)` có thể giúp đối với Path, nhưng giá trị này có thể thay đổi khi tệp được sửa đồng thời và không thay thế được việc kiểm tra số byte thực sự đọc.

## 11. Ví dụ hoàn chỉnh: sao chép file nhị phân theo block

Tạo file `BufferedCopyDemo.java`:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class BufferedCopyDemo {

    static long copy(Path source, Path target) throws IOException {
        long totalBytes = 0L;
        byte[] buffer = new byte[16 * 1024];

        try (InputStream in = new BufferedInputStream(
                    Files.newInputStream(source));
             OutputStream out = new BufferedOutputStream(
                    Files.newOutputStream(
                            target, StandardOpenOption.CREATE_NEW))) {

            int count;

            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
                totalBytes = Math.addExact(totalBytes, count);
            }
        }

        return totalBytes;
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java BufferedCopyDemo <source> <target>");
            return;
        }

        Path source = Path.of(args[0]);
        Path target = Path.of(args[1]);

        long copied = copy(source, target);

        System.out.println("Copied bytes: " + copied);
    }
}
```

Biên dịch và gọi với **hai đường dẫn khác nhau**:

```bash
javac BufferedCopyDemo.java
java BufferedCopyDemo source.bin copy.bin
```

Ví dụ tạo `copy.bin` mới, không ghi đè nếu đích đã tồn tại. Giá trị `Copied bytes` bằng số byte thực sự truyền qua vòng lặp.

**Lưu ý quan trọng:** nếu phát sinh lỗi sau khi đích đã được tạo, tệp đích có thể chỉ chứa **một phần dữ liệu**. Demo chưa có quy tắc cleanup hoặc ghi thay thế theo transaction. Hệ thống thực tế cần quyết định xóa file lỗi, ghi qua temp file rồi rename hoặc dùng chiến lược khôi phục thích hợp. Không tự động coi file đích tồn tại là bằng chứng copy thành công.

### 11.1. Nếu chỉ cần copy, dùng Files.copy

```java
import java.nio.file.StandardCopyOption;

Files.copy(
        source,
        target,
        StandardCopyOption.REPLACE_EXISTING
);
```

Cách này thể hiện ý định trực tiếp hơn và để provider xử lý việc sao chép. Tuy nhiên, tính nguyên tử hay việc xử lý file đích trong trường hợp lỗi không được tự động bảo đảm chỉ vì sử dụng `Files.copy`. Đừng áp dụng `REPLACE_EXISTING` nếu mục tiêu là không ghi đè.

## 12. DataInputStream và DataOutputStream: lưu dữ liệu có cấu trúc

Khi định dạng nhị phân có các trường kiểu nguyên thủy Java, hai class này hữu ích:

- `DataOutputStream` có `writeInt`, `writeLong`, `writeDouble`, `writeBoolean`, ...
- `DataInputStream` có `readInt`, `readLong`, `readDouble`, `readBoolean`, ...

Chúng thường được kết hợp với buffering:

```text
Ghi:
DataOutputStream
    -> BufferedOutputStream
        -> Files.newOutputStream(path)

Đọc:
DataInputStream
    -> BufferedInputStream
        -> Files.newInputStream(path)
```

### 12.1. Thứ tự đọc phải đúng thứ tự ghi

```java
// Ghi:
out.writeInt(42);
out.writeLong(150_000L);

// Đọc tương ứng:
int id = in.readInt();
long amount = in.readLong();
```

Nếu đọc `readLong()` trước `readInt()`, bạn sẽ diễn giải các byte sai trường. Đây không phải lỗi mà generic type checking của Java có thể ngăn được: định dạng file là **hợp đồng giữa nơi ghi và nơi đọc**.

`DataInputStream` và `DataOutputStream` sử dụng thứ tự byte phù hợp với Java Data Streams (big-endian cho những giá trị nhiều byte được hỗ trợ). Nếu cần tương tác với một định dạng bên ngoài có little-endian, phải dùng API có khả năng quy định byte order, chẳng hạn `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)`, hoặc mã hóa theo chuẩn của định dạng đó.

### 12.2. EOFException khi đọc cấu trúc bị cắt cụt

`DataInputStream.readInt()` cần đủ 4 byte để tạo một `int`; `readLong()` cần đủ 8 byte. Nếu luồng kết thúc trước khi đọc đủ dữ liệu, chúng có thể ném `EOFException`.

Không nên đọc trước bằng `available()` hoặc giả định rằng "đã có file" thì cấu trúc chắc chắn đầy đủ. Cần validate header, version, số lượng bản ghi và xử lý EOF bất thường.

### 12.3. Vì sao cần magic number và version?

Định dạng nhị phân do ứng dụng tự định nghĩa thường nên có:

1. **Magic number**: vài byte đầu nhận diện loại file.
2. **Format version**: phiên bản để người đọc biết cách giải mã.
3. **Count/length**: số bản ghi hoặc độ dài từng phần.
4. **Payload**: dữ liệu thực tế.
5. Nếu cần: checksum, thông tin xác thực hoặc metadata khác.

Một định dạng đơn giản:

```text
Offset        Dữ liệu             Kích thước
0             MAGIC               4 byte (int)
4             VERSION             4 byte (int)
8             COUNT               4 byte (int)
12            record[0].id        4 byte (int)
16            record[0].amount    8 byte (long)
28            record[1].id        4 byte (int)
32            record[1].amount    8 byte (long)
...
```

Ghi chú: offset các record phụ thuộc số lượng bản ghi; bảng minh họa 2 record đầu trong một định dạng có kích thước mỗi record là 12 byte.

## 13. Ví dụ hoàn chỉnh: đọc ghi record nhị phân có version

Tạo file `BufferedBinaryDemo.java`:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class BufferedBinaryDemo {

    private static final int MAGIC = 0x4A444154; // "JDAT"
    private static final int VERSION = 1;
    private static final int MAX_RECORDS = 100_000;

    record Entry(int id, long amountVnd) {
        Entry {
            if (id <= 0 || amountVnd < 0) {
                throw new IllegalArgumentException("Invalid entry");
            }
        }
    }

    static void writeEntries(Path file, List<Entry> entries)
            throws IOException {
        if (entries.size() > MAX_RECORDS) {
            throw new IllegalArgumentException("Too many entries");
        }

        try (DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(Files.newOutputStream(file)))) {

            out.writeInt(MAGIC);
            out.writeInt(VERSION);
            out.writeInt(entries.size());

            for (Entry entry : entries) {
                out.writeInt(entry.id());
                out.writeLong(entry.amountVnd());
            }
        }
    }

    static List<Entry> readEntries(Path file) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(Files.newInputStream(file)))) {

            if (in.readInt() != MAGIC) {
                throw new IOException("Wrong file format");
            }

            if (in.readInt() != VERSION) {
                throw new IOException("Unsupported format version");
            }

            int count = in.readInt();

            if (count < 0 || count > MAX_RECORDS) {
                throw new IOException("Invalid record count");
            }

            List<Entry> result = new ArrayList<>(count);

            for (int i = 0; i < count; i++) {
                int id = in.readInt();
                long amount = in.readLong();

                try {
                    result.add(new Entry(id, amount));
                } catch (IllegalArgumentException ex) {
                    throw new IOException("Invalid record at index " + i, ex);
                }
            }

            if (in.read() != -1) {
                throw new IOException("Unexpected trailing data");
            }

            return List.copyOf(result);
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("java-binary-demo-", ".dat");

        try {
            List<Entry> entries = List.of(
                    new Entry(100, 120_000L),
                    new Entry(101, 350_000L)
            );

            writeEntries(file, entries);
            List<Entry> restored = readEntries(file);

            for (Entry entry : restored) {
                System.out.printf(
                        "id=%d, amount=%d%n",
                        entry.id(),
                        entry.amountVnd()
                );
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BufferedBinaryDemo.java
java BufferedBinaryDemo
```

Kết quả:

```text
id=100, amount=120000
id=101, amount=350000
```

### 13.1. Vì sao chương trình có kiểm tra dữ liệu?

- `MAGIC` từ chối tệp không đúng định dạng.
- `VERSION` giúp phát hiện phiên bản chưa được hỗ trợ.
- `MAX_RECORDS` ngăn một count bất hợp lý khiến chương trình cấp phát bộ nhớ quá lớn.
- Constructor của record kiểm tra bất biến miền dữ liệu.
- `readInt`/`readLong` sẽ báo lỗi khi record bị cắt cụt.
- Kiểm tra `in.read() != -1` từ chối dữ liệu thừa ngoài định dạng phiên bản 1.

Điều này chưa đủ cho một định dạng chống dữ liệu độc hại toàn diện: một hệ thống sản xuất có thể cần kiểm soát kích thước file, checksum, giới hạn thời gian và ràng buộc tài nguyên bổ sung.

### 13.2. Vì sao không dùng Java object serialization?

Với định dạng file tự định nghĩa, cấu trúc nguyên thủy có version rõ ràng thường dễ quản lý hơn việc gắn tính bền vững của dữ liệu vào biểu diễn object Java. Bài này không dùng Java native object serialization làm phương án mặc định; nó không phải một định dạng dữ liệu trao đổi công khai, và việc giải tuần tự hóa dữ liệu không đáng tin cậy có rủi ro bảo mật nghiêm trọng.

Khi trao đổi dữ liệu giữa nhiều ngôn ngữ/nền tảng, nên cân nhắc các định dạng có đặc tả và quy tắc tương thích rõ ràng (ví dụ JSON cho văn bản, hoặc một định dạng nhị phân có schema), thay vì giả định bên nhận hiểu byte layout của Java.

## 14. Văn bản bên trong định dạng nhị phân

Một record nhị phân đôi khi chứa tên người dùng hoặc mô tả. Có hai cách cần phân biệt:

1. `DataOutputStream.writeUTF` / `DataInputStream.readUTF` sử dụng **modified UTF-8** và một dạng độ dài giới hạn, theo định dạng riêng của Java.
2. Nếu cần **UTF-8 tiêu chuẩn** để tương tác liên nền tảng, hãy tự quy định trường length và ghi byte được tạo bằng `StandardCharsets.UTF_8`.

**Không xem `writeUTF` là phép ghi chuỗi UTF-8 tiêu chuẩn** để ứng dụng ngoài Java tự đọc mà không biết định dạng.

### 14.1. Ví dụ length-prefixed UTF-8

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

static void writeUtf8(DataOutputStream out, String text)
        throws IOException {

    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
    out.writeInt(bytes.length);
    out.write(bytes);
}

static String readUtf8(DataInputStream in, int maxBytes)
        throws IOException {

    int length = in.readInt();

    if (length < 0 || length > maxBytes) {
        throw new IOException("Invalid text length");
    }

    byte[] bytes = new byte[length];
    in.readFully(bytes);

    return new String(bytes, StandardCharsets.UTF_8);
}
```

Hai method này là **đoạn mã để đặt trong một class chứa helper methods**. Chúng không tự cấu thành một file Java độc lập.

Quy trình: ghi **số byte** của chuỗi UTF-8, rồi ghi chính những byte đó. Lúc đọc, kiểm tra length trước khi cấp phát mảng, sau đó dùng `readFully` để nhận đủ byte.

### 14.2. Khi cần phát hiện UTF-8 không hợp lệ

`new String(bytes, StandardCharsets.UTF_8)` có thể thay thế chuỗi byte không hợp lệ bằng ký tự thay thế theo cơ chế giải mã. Nếu hợp đồng yêu cầu **báo lỗi thay vì thay thế âm thầm**, dùng `CharsetDecoder` với `CodingErrorAction.REPORT`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] data)
        throws java.nio.charset.CharacterCodingException {

    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(data))
            .toString();
}
```

Ở đây, dữ liệu nhị phân được kiểm tra ở ranh giới trước khi chuyển thành văn bản. Tương tự, với dữ liệu truyền giữa các hệ thống cần độ chính xác cao, hãy xác định rõ chính sách xử lý ký tự không thể mã hóa.

## 15. flush(), close() và độ bền dữ liệu

### 15.1. flush nghĩa là gì?

Gọi `flush()` trên buffered writer hoặc buffered output stream yêu cầu đẩy dữ liệu còn giữ trong bộ đệm xuống tầng ghi bên dưới.

```java
try (var writer = Files.newBufferedWriter(
        file, StandardCharsets.UTF_8)) {

    writer.write("Một phần dữ liệu");
    writer.flush();

    writer.write(" và phần còn lại");
}
```

`flush` có thể hữu ích khi cần cho tầng bên dưới nhận dữ liệu **trước khi writer đóng**, chẳng hạn ghi thông báo cho một bên đang đọc luồng tương tác.

### 15.2. close làm gì?

`close()` giải phóng tài nguyên I/O và xử lý dữ liệu đang đệm theo contract của stream/writer. Với `try-with-resources`, việc đóng diễn ra tự động kể cả khi code trong khối ném exception.

**Không cần gọi `flush()` ngay trước `close()` chỉ vì sợ mất dữ liệu** nếu close thành công đã thực hiện nghĩa vụ đẩy bộ đệm. Tuy nhiên, lỗi khi flush/close vẫn có thể xảy ra và cần được xử lý.

### 15.3. flush không đồng nghĩa fsync

Dữ liệu được đẩy ra khỏi bộ đệm Java chưa chắc đã được lưu bền vững xuống thiết bị vật lý. Hệ điều hành có thể vẫn giữ dữ liệu trong page cache hoặc tầng storage khác.

Khi có yêu cầu mạnh về độ bền lưu trữ, các API như `FileChannel.force(...)` có thể được cân nhắc theo contract và giới hạn của provider. Ngay cả khi ấy vẫn cần phân tích cả directory metadata, tình huống mất điện và đặc tính filesystem; không nên đưa ra cam kết "đã flush = không thể mất dữ liệu".

## 16. Try-with-resources và thứ tự đóng stream

Một tài nguyên thực hiện `AutoCloseable` có thể nằm trong `try-with-resources`:

```java
try (BufferedReader reader =
        Files.newBufferedReader(file, StandardCharsets.UTF_8)) {

    System.out.println(reader.readLine());
}
```

Nếu tạo nhiều tài nguyên trong cùng một câu lệnh `try`, chúng được đóng theo **thứ tự ngược** với thứ tự khai báo.

Nếu dùng stream bọc ngoài một stream bên dưới, thông thường chỉ cần quản lý **stream ngoài cùng**:

```java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(file)))) {

    int value = in.readInt();
}
```

Đóng `DataInputStream` cũng đóng luồng được bọc bên dưới. Cách này giúp tránh bỏ sót tài nguyên mà không cần đóng thủ công từng tầng.

### 16.1. Exception trong quá trình đóng

Nếu code trong khối `try` ném exception, đồng thời `close()` cũng ném exception, Java có thể lưu exception từ quá trình đóng dưới dạng **suppressed exception** trên exception chính. Khi điều tra lỗi I/O, xem cả `getSuppressed()` nếu cần.

Không nên bỏ qua lỗi khi đóng writer: một số lỗi ghi chỉ xuất hiện khi dữ liệu trong buffer cuối cùng được đẩy ra.

## 17. Xử lý ngoại lệ và trạng thái tệp sau lỗi

Nhóm lỗi thường gặp:

| Tình huống | Exception có thể gặp | Hướng xử lý |
|---|---|---|
| Tệp nguồn không tồn tại | `NoSuchFileException` | Kiểm tra đường dẫn/đầu vào và chính sách nghiệp vụ |
| Không có quyền truy cập | `AccessDeniedException` hoặc `IOException` tùy provider | Báo lỗi phù hợp, không tự bypass quyền |
| Không gian lưu trữ hoặc I/O hỏng | `IOException` | Không coi kết quả đã được ghi trọn vẹn |
| Dữ liệu nhị phân bị cắt cụt | `EOFException` | Báo tệp không hợp lệ, có thể cách ly tệp |
| Tệp không đúng magic/version | `IOException` do ứng dụng chủ động ném | Từ chối hoặc áp dụng đường nâng cấp được định nghĩa |
| Đường dẫn đích đã tồn tại với `CREATE_NEW` | `FileAlreadyExistsException` | Không ghi đè, chọn tên mới hoặc hỏi quyền thay thế |
| Byte không thể giải mã hợp lệ theo chính sách | `CharacterCodingException` hoặc `IOException` liên quan | Từ chối/ghi nhận lỗi encoding |

Không phải provider nào cũng ném chính xác cùng một subclass `IOException` trong mọi tình huống. Bắt `IOException` ở ranh giới ứng dụng thường phù hợp, rồi phân biệt loại lỗi nếu cần.

### 17.1. Không im lặng khi ghi thất bại

Không nên:

```java
// Không nên dùng trong code quan trọng:
// try (var writer = Files.newBufferedWriter(file, UTF_8)) {
//     writer.write(data);
// } catch (IOException ignored) {
//     // Lỗi bị nuốt và caller tưởng ghi thành công.
// }
```

Tùy nghiệp vụ, hãy trả lỗi cho caller, log với thông tin thích hợp, hoặc phục hồi có kiểm soát. Không ghi đè thông điệp lỗi nhạy cảm ra log công khai nếu đường dẫn/nội dung chứa dữ liệu riêng tư.

### 17.2. Ghi tệp tạm trước khi thay thế file quan trọng

Để giảm nguy cơ để lại một tệp đích bị ghi dở:

1. Tạo tệp tạm cùng filesystem hoặc trong thư mục đích.
2. Ghi toàn bộ nội dung và đóng writer/stream.
3. Nếu cần, xác minh nội dung/size/checksum.
4. Thử thay thế tệp đích bằng thao tác move có tính nguyên tử **nếu provider hỗ trợ**.
5. Xử lý fallback và cleanup nếu không có atomic move.

Trong Java có `Files.move` cùng `StandardCopyOption.ATOMIC_MOVE` và `REPLACE_EXISTING`. Tuy nhiên, khả năng hỗ trợ, tác dụng của tổ hợp option và tính nguyên tử phụ thuộc provider. Nếu `ATOMIC_MOVE` không được hỗ trợ, có thể gặp `AtomicMoveNotSupportedException`; fallback move không mặc nhiên nguyên tử. Một phương án ghi an toàn còn cần tính tới crash recovery và chính sách durability.

Đừng mở tệp dữ liệu quan trọng bằng chế độ truncate rồi mới hy vọng rằng mọi thao tác ghi đều thành công.

## 18. Hiệu năng, kích thước buffer và mức dùng bộ nhớ

Buffering thường giúp ích khi ứng dụng thực hiện rất nhiều I/O nhỏ, nhưng hiệu năng còn phụ thuộc vào:

- Tốc độ thiết bị lưu trữ hoặc nguồn dữ liệu.
- Hệ thống tệp, mạng, caching của OS và provider.
- Kích thước mỗi lần đọc/ghi và dung lượng tổng.
- Chi phí chuyển đổi charset, parse record hoặc nén/giải nén.
- Chi phí tính toán và đồng bộ giữa các thread.

### 18.1. Chọn kích thước buffer

Ví dụ mảng sao chép:

```java
byte[] buffer = new byte[16 * 1024];
```

`16 KiB` là lựa chọn khởi đầu minh họa, không phải kích thước tốt nhất cho mọi hệ thống. Không nên giả định Java luôn dùng cùng một kích thước bộ đệm mặc định trong mọi API và phiên bản.

Với những thao tác đặc biệt lớn hoặc nhạy hiệu năng, hãy đo trên workload thực tế và so sánh với `Files.copy` hoặc API I/O phù hợp khác.

### 18.2. Tránh tải cả tệp lớn vào RAM

`Files.readAllBytes`, `Files.readString` và `Files.readAllLines` thuận tiện nhưng có thể làm bộ nhớ tăng theo kích thước nội dung. Với file lớn hoặc file do người dùng cung cấp, hãy ưu tiên đọc theo dòng/khối, kèm giới hạn tài nguyên.

### 18.3. Không phải cứ thêm bộ đệm là tốt hơn

`Files.newBufferedReader` và `Files.newBufferedWriter` đã cung cấp buffering. Bọc một lớp cùng loại nữa có thể làm hệ thống phức tạp hơn mà không cải thiện tốc độ. Bên cạnh đó, đọc block qua `Files.newInputStream` rồi xử lý theo block cũng có thể đủ hiệu quả mà không cần bọc thêm `BufferedInputStream`.

**Đo đạc và chọn cấu trúc dễ hiểu** quan trọng hơn việc mặc định thêm mọi lớp `Buffered...`.

## 19. Bảo mật khi đọc/ghi tệp

File I/O không chỉ là hiệu năng. Với đường dẫn từ request, upload hoặc cấu hình bên ngoài, cần thiết kế bảo mật:

### 19.1. Không tin đường dẫn do client truyền vào

Không ghép trực tiếp tên file người dùng gửi với thư mục lưu trữ rồi cho phép truy cập tùy ý:

```java
// Mã phác thảo không an toàn nếu fileName không đáng tin:
// Path target = uploadDir.resolve(fileName);
```

Các thành phần như `..`, đường dẫn tuyệt đối hoặc liên kết tượng trưng (*symbolic link*) có thể gây truy cập ngoài phạm vi cho phép.

Cần kiểm tra chính sách tên file, thao tác normalize/resolve phù hợp, quyền truy cập, symlink và khả năng thay đổi đường dẫn giữa kiểm tra và mở. Chỉ so sánh chuỗi sau `normalize()` không đủ cho mọi mô hình đe dọa.

### 19.2. Giới hạn dung lượng và số lượng bản ghi

Đọc giá trị length/count từ một tệp nhị phân không đáng tin cậy mà không kiểm tra có thể khiến chương trình cấp phát bộ nhớ lớn hoặc xử lý rất lâu. Trước khi cấp phát hay lặp, cần validate giới hạn và kiểm tra các phép nhân kích thước để tránh integer overflow.

### 19.3. Không coi buffering là kiểm soát đồng thời

Hai tác vụ ghi cùng một tệp có thể đè dữ liệu hoặc tạo nội dung không nhất quán. Nếu có nhiều writer, cần chính sách khóa, version hoặc cấu trúc lưu trữ an toàn. Buffering không tự tạo transaction và cũng không bảo đảm file locking.

### 19.4. Không suy diễn an toàn dữ liệu từ phần mở rộng

Tệp có tên `report.txt` vẫn có thể chứa byte không hợp lệ hoặc dữ liệu rất lớn. Tệp `image.png` có thể không phải ảnh PNG. Nếu tính đúng định dạng quan trọng, cần kiểm tra header, parser hoặc validator phù hợp.

## 20. Bảng chọn nhanh API

| Nhu cầu | API đề xuất | Lý do |
|---|---|---|
| Đọc tệp text lớn theo dòng | `Files.newBufferedReader` | Dễ kiểm soát vòng lặp/EOF, bộ nhớ theo dòng |
| Ghi text với nhiều lần write | `Files.newBufferedWriter` | Charset rõ và buffering sẵn |
| Đọc cả text nhỏ | `Files.readString` | Ngắn gọn khi kiểm soát được kích thước |
| Viết text nhỏ một lần | `Files.writeString` | Ít mã boilerplate |
| Duyệt line bằng pipeline | `Files.lines` | Dùng Stream; nhớ đóng |
| Copy nguyên vẹn byte từ Path sang Path | `Files.copy` | Diễn đạt ý định trực tiếp |
| Copy qua luồng và tính checksum | `BufferedInputStream` / `BufferedOutputStream` hoặc loop theo block | Kiểm soát từng block |
| Đọc/ghi primitive trong format riêng | `DataInputStream` / `DataOutputStream` với buffer | Thứ tự trường rõ ràng |
| Ghi chuỗi UTF-8 trong file nhị phân liên nền tảng | `StandardCharsets.UTF_8` + length-prefixed bytes | Chuẩn mã hóa và kích thước tường minh |
| Cần durability đặc biệt | Kết hợp I/O, `FileChannel.force`, move và chính sách filesystem | `flush` không tự đảm bảo durability |

**Nguyên tắc chọn:** ưu tiên API mức cao nhất mô tả đúng nhiệm vụ; chỉ xuống API thấp hơn khi cần kiểm soát byte layout, streaming hoặc cơ chế khôi phục.

## 21. Những sai lầm phổ biến

| Sai lầm | Vấn đề | Cách tránh |
|---|---|---|
| Không chỉ định charset | Có nguy cơ phụ thuộc ngữ cảnh/khó hiểu format | Dùng `StandardCharsets.UTF_8` rõ ràng |
| Đọc file ảnh bằng `Reader` | Byte có thể bị giải mã/mã hóa sai | Dùng byte stream |
| Dùng `readLine().isEmpty()` làm EOF | Dừng ở dòng trống, có thể NPE | Dùng `readLine() != null` |
| Dùng `ready()` để phát hiện EOF | `ready` không phải cờ EOF | Kiểm tra kết quả `read` |
| Ghi cả buffer sau lần đọc ngắn | Ghi thêm byte rác hoặc byte cũ | `out.write(buffer, 0, count)` |
| Giả định `read(byte[])` luôn trả đủ mảng | Nhiều nguồn trả ít byte hơn | Lặp đến EOF hoặc dùng `readFully` |
| Dùng `available()` làm kích thước tệp | Không phải tổng số byte | `Files.size` khi phù hợp hoặc streaming |
| Quên đóng reader/writer | Rò tài nguyên, dữ liệu còn trong buffer | `try-with-resources` |
| Coi `flush` là lưu bền vững | OS và storage vẫn có tầng đệm | Thiết kế durability đúng yêu cầu |
| Ghi tệp quan trọng bằng truncate vô ý | Mất nội dung cũ nếu ghi lỗi | Dùng temp/atomic move hoặc quy trình an toàn |
| Dùng `writeUTF` như UTF-8 chuẩn | Modified UTF-8 là định dạng riêng | UTF-8 bytes + length rõ ràng |
| Đọc field nhị phân sai thứ tự | Byte bị diễn giải sai | Dùng định dạng có version/schema |
| Cấp phát theo count không kiểm tra | Nguy cơ OOM/DoS | Validate trước, giới hạn tài nguyên |
| Đọc file lớn bằng `readAllBytes` | Tăng bộ nhớ theo kích thước file | Dùng stream theo block |
| Bao nhiều lớp Buffered không cần | Phức tạp, có thể không tăng hiệu năng | Hiểu buffer đã có ở API |
| Tin rằng `Files.copy` luôn atomic | Copy có thể tạo dữ liệu đích chưa hoàn chỉnh khi lỗi | Thiết kế recovery |
| Không xử lý exception khi close | Có thể che lỗi ghi muộn | Theo dõi lỗi flush/close |
| Chấp nhận đường dẫn không đáng tin | Path traversal/symlink race | Validate tại ranh giới và áp dụng quyền truy cập |

## 22. Bài tập thực hành

### Bài 1. Ghi và đọc văn bản UTF-8

Tạo tệp `students.txt` có ba dòng tiếng Việt và một dòng rỗng. Dùng `Files.newBufferedWriter` để ghi và `Files.newBufferedReader` để đọc. In số thứ tự dòng, đồng thời chứng minh dòng rỗng không phải EOF.

### Bài 2. Ghi tiếp vào tệp

Viết method `appendLog(Path file, String message)` dùng `CREATE`, `APPEND` và UTF-8. Phân biệt kết quả khi gọi method này hai lần với kết quả mở writer mặc định hai lần. Vì sao cần chính sách khi nhiều tiến trình cùng ghi log?

### Bài 3. Sao chép tệp nhị phân

Viết `copy(Path source, Path target)` đọc theo mảng byte 8192 phần tử. Luôn dùng số byte trả về từ `read`. Thử với file có kích thước 1 byte, 8192 byte và 8193 byte. So sánh kết quả với `Files.copy`.

### Bài 4. Đếm số byte và giới hạn dung lượng

Mở rộng vòng lặp copy: dừng và báo lỗi nếu tổng byte vượt một giới hạn cấu hình, chẳng hạn 10 MiB. Sử dụng `Math.addExact` hoặc kiểm tra overflow trước khi cộng; xác định cách xử lý tệp đích nếu dừng giữa chừng.

### Bài 5. Ghi dữ liệu nhị phân

Tạo định dạng chứa magic, version, count và danh sách record `SensorReading(int sensorId, long timestamp, double value)`. Dùng `DataOutputStream` và `DataInputStream` có buffering. Kiểm tra count hợp lệ và tình huống tệp bị cắt cụt.

### Bài 6. Xử lý phiên bản file

Thay version trong bài 5 từ 1 sang 2. Thiết kế code đọc theo version: từ chối version chưa hỗ trợ hoặc cung cấp hàm chuyển đổi có kiểm soát. Giải thích vì sao không được đọc tệp version 2 như thể là version 1.

### Bài 7. So sánh readString và buffered reader

Tạo file văn bản dung lượng lớn và thử hai cách: `Files.readString` và `Files.newBufferedReader`. Giải thích mức dùng bộ nhớ khác nhau về mặt cấu trúc. Khi tự đo thời gian, hãy kiểm soát warm-up, môi trường và số lần thử.

### Bài 8. Chuỗi UTF-8 trong file nhị phân

Viết `writeUtf8` và `readUtf8` với length prefix `int`, giới hạn tối đa 4096 byte. Thử chuỗi có dấu tiếng Việt, emoji và chuỗi rỗng. Giải thích vì sao độ dài `String.length()` không phải số byte của UTF-8.

### Bài 9. Lỗi khi ghi

Giả lập một trường hợp ghi đích thất bại hoặc source bị đọc lỗi. Hãy xác định trạng thái tệp đích có thể còn lại và đề xuất chiến lược dùng tệp tạm để tránh công bố dữ liệu chưa hoàn chỉnh.

### Bài 10. Chọn API

Chọn API phù hợp cho bốn nhiệm vụ: đọc file cấu hình 2 KiB; xử lý log nhiều GB theo dòng; sao chép ảnh 20 MB mà không biến đổi; lưu 50.000 record nhị phân định dạng có version. Giải thích lý do, điều kiện đóng tài nguyên và rủi ro cần kiểm soát.

## 23. Tóm tắt

Trong Java 27, **đọc/ghi văn bản có bộ đệm** thường bắt đầu bằng `Files.newBufferedReader` và `Files.newBufferedWriter`, kèm charset rõ ràng như `StandardCharsets.UTF_8`. Dùng `readLine() != null` cho EOF, nhớ rằng `readLine` loại bỏ dấu kết thúc dòng và `newLine` có thể phụ thuộc hệ điều hành.

Với **nhị phân**, `InputStream` và `OutputStream` giữ nguyên byte. `BufferedInputStream` và `BufferedOutputStream` gom các thao tác nhỏ; khi đọc từng block phải dùng đúng số byte thực nhận. `DataInputStream` và `DataOutputStream` có ích để định nghĩa bố cục các giá trị nguyên thủy, nhưng người thiết kế phải quản lý thứ tự trường, version, count, EOF và quy tắc encoding.

**Try-with-resources** giúp đóng stream an toàn, còn `flush` chỉ chuyển dữ liệu xuống tầng bên dưới chứ không tự cam kết durability. Khi làm việc với tệp lớn hoặc đầu vào không đáng tin cậy, hãy đọc theo dòng/khối, validate kích thước và định dạng, kiểm soát đường dẫn và lên kế hoạch xử lý tệp ghi dở nếu có lỗi.

## Tài liệu tham khảo

- [Java SE 27 API — java.nio.file.Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 27 API — java.nio.file.Path](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Path.html)
- [Java SE 27 API — java.io.BufferedReader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/BufferedReader.html)
- [Java SE 27 API — java.io.BufferedWriter](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/BufferedWriter.html)
- [Java SE 27 API — java.io.BufferedInputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/BufferedInputStream.html)
- [Java SE 27 API — java.io.BufferedOutputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/BufferedOutputStream.html)
- [Java SE 27 API — java.io.DataInputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/DataInputStream.html)
- [Java SE 27 API — java.io.DataOutputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/DataOutputStream.html)
- [Java SE 27 API — java.nio.charset.StandardCharsets](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Java SE 27 API — java.nio.file.StandardOpenOption](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/StandardOpenOption.html)
