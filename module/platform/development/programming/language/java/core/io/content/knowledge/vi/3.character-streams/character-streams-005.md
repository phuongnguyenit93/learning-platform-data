# OutputStreamWriter: cầu nối từ ký tự sang luồng byte trong Java

`OutputStreamWriter` trong `java.io` là **cầu nối giữa API ghi ký tự (`Writer`) và API ghi byte (`OutputStream`)**. Khi chương trình viết chữ bằng `write(...)`, đối tượng này sử dụng **charset** để mã hóa ký tự thành một chuỗi byte, rồi chuyển các byte đó xuống luồng đích. Đây là thành phần quan trọng khi ghi văn bản tiếng Việt, Unicode, dữ liệu dạng dòng hoặc giao thức văn bản qua tệp, bộ nhớ hay socket.

Mục tiêu: hiểu chính xác hướng chuyển đổi, vai trò của charset, cách ghép `OutputStreamWriter` với `OutputStream`/`BufferedWriter`, ý nghĩa của `flush()`/`close()`, và các lỗi khiến văn bản ghi ra không đúng.

## 1. Cầu nối hoạt động như thế nào?

Sơ đồ:

```text
String / char[] / ký tự Java
       |
       | Writer.write(...)
       v
+-------------------------+
| OutputStreamWriter      |
| CharsetEncoder          |  UTF-8, UTF-16, US-ASCII, ...
| ký tự UTF-16 -> byte    |
+-------------------------+
       |
       | các byte được mã hóa
       v
OutputStream (FileOutputStream / ByteArrayOutputStream / Socket OutputStream...)
       |
       v
Tệp, mảng byte, mạng hoặc một đích byte khác
```

Java lưu nội dung của `String` theo đơn vị **UTF-16 code unit** (`char` là đơn vị 16 bit); ký tự ngoài Basic Multilingual Plane, như emoji `😀`, dùng một **cặp surrogate** (hai `char`). `OutputStreamWriter` nhận dãy ký tự này, xử lý bằng bộ mã hóa đã chọn và phát sinh byte theo charset. Vì thế, **số `char` không nhất thiết bằng số ký tự Unicode, và cũng không bằng số byte**.

Ví dụ:

| Nội dung | Số đơn vị `char` UTF-16 | Số byte UTF-8 |
| --- | ---: | ---: |
| `A` | 1 | 1 |
| `é` | 1 | 2 |
| `中` | 1 | 3 |
| `😀` | 2 | 4 |
| Ký tự xuống dòng `\n` | 1 | 1 |

Nếu ghi `"Aé中😀\n"` theo UTF-8, chuỗi này có **6 đơn vị `char`, 5 Unicode code point và 11 byte UTF-8**. Không nên lấy `String.length()` để dự đoán số byte được lưu hoặc gửi qua mạng.

`OutputStreamWriter` chỉ **mã hóa ký tự thành byte**. Chiều ngược lại, đọc byte thành ký tự, là công việc của `InputStreamReader`.

## 2. Cấu tạo một pipeline ghi ký tự

Ví dụ cơ bản:

```java
OutputStream destination = new FileOutputStream("message.txt");
Writer writer = new OutputStreamWriter(destination, StandardCharsets.UTF_8);
writer.write("Xin chào, Java!");
writer.close();
```

Đây là **mảnh minh họa**; cần import `java.io.*`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. Khi chạy, `FileOutputStream` nhận byte; `OutputStreamWriter` chịu trách nhiệm chuyển ký tự sang UTF-8. Sau `close()`, luồng ghi đã kết thúc.

Trong code thật, hãy dùng `try-with-resources` để đóng tài nguyên kể cả khi xảy ra ngoại lệ:

```java
try (Writer writer = new OutputStreamWriter(
        new FileOutputStream("message.txt"), StandardCharsets.UTF_8)) {
    writer.write("Xin chào, Java!");
}
```

`try-with-resources` tự gọi `close()` trên `writer`. Khi đóng, `OutputStreamWriter` hoàn tất luồng mã hóa, flush phần dữ liệu còn lại và **đóng `OutputStream` bên dưới**. Do đó không cần đóng riêng `FileOutputStream` sau khi đã giao quyền sở hữu cho writer. Nếu bạn nhận `OutputStream` do nơi khác quản lý, phải thống nhất ai có quyền đóng trước khi tạo writer.

## 3. Chọn charset tường minh

Các constructor đáng biết:

```java
new OutputStreamWriter(outputStream)
new OutputStreamWriter(outputStream, StandardCharsets.UTF_8)
new OutputStreamWriter(outputStream, "UTF-8")
new OutputStreamWriter(outputStream, charsetEncoder)
```

- `OutputStreamWriter(OutputStream)` dùng **default charset** của môi trường chạy. Không nên dựa vào nó cho định dạng file, giao tiếp giữa hệ thống hoặc kết quả phải ổn định trên máy khác. Java 17 có thể có default charset phụ thuộc nền tảng/cấu hình; các phiên bản và cấu hình khác cũng ảnh hưởng đến hành vi mặc định.
- `OutputStreamWriter(OutputStream, Charset)` chọn một charset cụ thể. Thường ưu tiên `StandardCharsets.UTF_8` để tránh lỗi đánh máy tên charset và bảo đảm thống nhất.
- `OutputStreamWriter(OutputStream, String)` chấp nhận tên charset; tên không được hỗ trợ có thể gây `UnsupportedEncodingException` khi khởi tạo.
- `OutputStreamWriter(OutputStream, CharsetEncoder)` cho phép kiểm soát chính sách xử lý ký tự không mã hóa được hoặc UTF-16 không hợp lệ.

Charset **không phải loại dữ liệu `String`**, và cũng không phải thuộc tính tự động đi kèm một `OutputStream` bất kỳ. Người ghi và người đọc phải thống nhất định dạng byte. Ghi với UTF-8 nhưng phía đọc giải mã theo charset khác có thể tạo ra chữ bị lỗi (*mojibake*) hoặc ký tự thay thế.

Đọc lại bằng đúng UTF-8:

```java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

Đoạn trên mô tả cặp mã hóa/giải mã khi có sẵn toàn bộ dữ liệu trong bộ nhớ; khi cần ghi **theo luồng**, `OutputStreamWriter` cung cấp thao tác `write(...)` mà không yêu cầu tạo toàn bộ mảng byte trước. Ngược lại, có thể dùng `InputStreamReader` khi dữ liệu được đọc dưới dạng luồng.

## 4. Các thao tác quan trọng trên OutputStreamWriter

| Thao tác | Ý nghĩa |
| --- | --- |
| `write(int c)` | Ghi một **đơn vị ký tự**; tham số `int` không có nghĩa là một Unicode code point bất kỳ |
| `write(char[] chars, int offset, int length)` | Ghi một đoạn mảng `char`, độ dài theo số `char` |
| `write(String text, int offset, int length)` | Ghi một đoạn `String` tính theo chỉ số UTF-16 |
| `write(String text)` | Phương thức tiện ích thừa hưởng từ `Writer` để ghi cả chuỗi |
| `append(...)` | Ghi thêm chuỗi/ký tự thông qua giao diện `Appendable` |
| `flush()` | Đẩy byte đã được mã hóa còn trong bộ đệm và yêu cầu luồng dưới flush |
| `close()` | Hoàn tất và đóng writer, đồng thời đóng luồng đích |
| `getEncoding()` | Trả tên mã hóa (có thể là tên lịch sử); có thể trả `null` sau khi đã đóng |

Các biến thể có `offset`, `length` kiểm tra phạm vi của mảng hoặc chuỗi và ném lỗi khi phạm vi sai. `Writer.write(int)` ghi một `char`, nên **không** truyền nguyên Unicode code point `0x1F600` rồi kỳ vọng nó tự được chuyển thành cặp surrogate. Muốn ghi emoji, dùng `write("😀")` hoặc:

```java
writer.write(Character.toChars(0x1F600));
```

Đoạn này là mảnh mã, với `writer` là một `Writer` đang mở và phương thức gọi xử lý `IOException`. `Character.toChars(...)` trả về cặp `char` cần thiết cho code point ngoài BMP.

Cũng tránh vô tình cắt đôi cặp surrogate khi chia `String` theo `offset`/`length`. Khi dữ liệu được ghép từ nhiều thao tác ghi, trình mã hóa có thể phải giữ trạng thái ký tự dở dang; đừng dựa vào việc một lần `write` luôn tương ứng một số byte đã sẵn sàng bên dưới.

## 5. Ví dụ Java 17+ hoàn chỉnh: từ Unicode sang byte UTF-8

Tạo tệp `OutputStreamWriterDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class OutputStreamWriterDemo {
    public static void main(String[] args) throws IOException {
        String text = "Aé中😀\n";
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (OutputStreamWriter writer =
                     new OutputStreamWriter(destination, StandardCharsets.UTF_8)) {
            writer.write(text);
            writer.flush();
            System.out.println("Bytes after flush: " + destination.size());
        }

        byte[] result = destination.toByteArray();
        System.out.println("UTF-16 code units: " + text.length());
        System.out.println("Unicode code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 bytes: " + result.length);
        System.out.println("Hex: "
                + HexFormat.ofDelimiter(" ").withUpperCase().formatHex(result));
        System.out.println("Round trip: "
                + text.equals(new String(result, StandardCharsets.UTF_8)));
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac OutputStreamWriterDemo.java
java OutputStreamWriterDemo
```

Stdout chính xác:

```text
Bytes after flush: 11
UTF-16 code units: 6
Unicode code points: 5
UTF-8 bytes: 11
Hex: 41 C3 A9 E4 B8 AD F0 9F 98 80 0A
Round trip: true
```

Giải thích:

1. `ByteArrayOutputStream` là đích byte nằm trong bộ nhớ; nó giúp quan sát byte mà không phụ thuộc hệ thống tệp.
2. `writer.write(text)` cung cấp các đơn vị UTF-16 cho bộ mã hóa UTF-8. `writer.flush()` đẩy byte đã mã hóa xuống đích nên `destination.size()` cho kết quả **11** ngay tại thời điểm kiểm tra.
3. `HexFormat` (có trong Java 17) in từng byte ở hệ thập lục phân: `41` cho `A`, `C3 A9` cho `é`, `E4 B8 AD` cho `中`, `F0 9F 98 80` cho emoji, `0A` cho `\n`.
4. `new String(result, UTF_8)` giải mã đúng charset, phục hồi chính xác chuỗi gốc; biểu thức so sánh là `true`.
5. `close()` do `try-with-resources` gọi cũng đóng writer và đích byte. `ByteArrayOutputStream` cho phép gọi `toByteArray()` sau khi đã đóng, khác với nhiều đích I/O thực tế.

Ví dụ minh họa **encoding**, không phụ thuộc console có hiển thị đúng emoji hay không: kết quả được kiểm bằng hex và boolean, ổn định khi chạy trên JDK 17+.

## 6. OutputStreamWriter, BufferedWriter và OutputStream: phân chia trách nhiệm

Khi thực tế ghi nhiều đoạn nhỏ, thường dùng ba lớp:

```text
Ứng dụng gọi write("...")
        |
        v
BufferedWriter            đệm ký tự; hỗ trợ newLine()
        |
        v
OutputStreamWriter        mã hóa ký tự theo UTF-8 thành byte
        |
        v
FileOutputStream          ghi byte xuống tệp
```

`OutputStreamWriter` có bộ đệm **byte đã mã hóa**, nhưng không tạo một bộ đệm ký tự lớn để gộp các lần `write` nhỏ. Tài liệu Java khuyến nghị bọc nó trong `BufferedWriter` khi cần hiệu năng tốt hơn: việc gộp ký tự trước khi gọi bộ mã hóa có thể giảm số lần chuyển đổi.

Ví dụ ghi tệp văn bản:

```java
import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class WriteTextFile {
    public static void main(String[] args) throws Exception {
        Path path = Path.of("message.txt");

        try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(
                        Files.newOutputStream(path),
                        StandardCharsets.UTF_8))) {
            writer.write("Dòng đầu");
            writer.newLine();
            writer.write("Dòng thứ hai");
        }
    }
}
```

Dùng:

```bash
javac WriteTextFile.java
java WriteTextFile
```

Kết quả là một tệp `message.txt` trong thư mục đang chạy, chứa hai dòng UTF-8. `Files.newOutputStream(path)` với tùy chọn mặc định tạo tệp nếu chưa có và **xóa nội dung cũ** nếu tệp đã tồn tại. `BufferedWriter.newLine()` ghi **dấu xuống dòng theo nền tảng** (ví dụ `\r\n` trên một số hệ thống, `\n` trên hệ thống khác). Nếu định dạng/protocol yêu cầu chính xác LF, dùng `writer.write("\n")` thay cho `newLine()`.

Khi đóng `BufferedWriter`, chuỗi đóng đi theo lớp bọc: flush ký tự, hoàn tất mã hóa, rồi đóng `OutputStream`. Đối với file cấu hình, JSON Lines, văn bản trao đổi qua HTTP hoặc log có yêu cầu charset rõ ràng, phải quy định charset và quy tắc xuống dòng ở nơi thiết kế định dạng.

### Ghi thêm vào cuối tệp thay vì ghi đè

Nếu thật sự cần append, mở đích byte với `StandardOpenOption.APPEND`:

```java
Path path = Path.of("message.txt");
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(
                Files.newOutputStream(path,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.APPEND),
                StandardCharsets.UTF_8))) {
    writer.write("Một dòng được nối tiếp\n");
}
```

Đây là **mảnh mã**, cần import `java.io.*`, `java.nio.file.*`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. Khi append, không tự động thêm ký tự xuống dòng vào giữa nội dung cũ và mới; bạn phải kiểm soát ranh giới bản ghi. Nếu nhiều tiến trình/luồng cùng ghi một file, chỉ dùng chế độ append không đủ để đảm bảo mỗi bản ghi nhiều thao tác sẽ nguyên vẹn, không xen kẽ.

## 7. Flush, close và thời điểm byte xuất hiện

### `write(...)` không có nghĩa là “byte đã nằm bền vững trên đĩa”

`OutputStreamWriter` có thể tích lũy byte mã hóa trong bộ đệm nội bộ. Nếu còn `BufferedWriter` bên ngoài, ký tự cũng có thể nằm trong bộ đệm ký tự. Vì thế, việc `write(...)` trả về không đảm bảo byte đã được đẩy hết tới đích.

- `writer.flush()` yêu cầu đẩy các bộ đệm có liên quan xuống `OutputStream` và gọi flush trên luồng bên dưới. Nó giúp bên nhận thấy byte sớm hơn khi cấu trúc luồng/transport hỗ trợ.
- `writer.close()` hoàn tất chuỗi mã hóa, flush phần còn lại rồi đóng các lớp bên dưới. Dùng khi kết thúc tài nguyên.
- `flush()` **không** đồng nghĩa dữ liệu đã được đồng bộ bền vững xuống thiết bị lưu trữ (*fsync*) hoặc đã được hệ thống đầu xa xác nhận. Tính bền vững/ACK cần cơ chế riêng của file/network/protocol.
- `flush()` không đóng luồng. Có thể tiếp tục ghi sau `flush()`, nhưng sau `close()` thì không.

Nếu có `BufferedWriter` bọc ngoài, gọi `flush()` trên **writer ngoài cùng** để bảo đảm cả buffer ký tự và pipeline phía dưới được flush. Tránh chỉ gọi flush trực tiếp trên `OutputStream` nằm bên trong khi `BufferedWriter` vẫn còn ký tự chưa chuyển xuống.

Đối với mã hóa có trạng thái hoặc dữ liệu kết thúc bằng một nửa cặp surrogate, thao tác **kết thúc luồng** qua `close()` có thể có bước xử lý cuối khác với `flush()` giữa chừng. Luôn đóng writer khi đã ghi xong; đừng coi `flush()` là thay thế hoàn toàn cho `close()`.

### Quyền sở hữu tài nguyên

Một wrapper là một phần của chuỗi đóng tài nguyên. Ví dụ:

```java
try (Writer writer =
        new OutputStreamWriter(System.out, StandardCharsets.UTF_8)) {
    writer.write("Hello\n");
}
```

**Không nên** dùng kiểu trên nếu chương trình vẫn cần in ra `System.out` sau khối `try`: đóng writer có thể đóng cả chuẩn xuất mà phần còn lại của ứng dụng vẫn dùng. Với `System.out` hoặc socket stream do thành phần khác sở hữu, chỉ đóng khi chính code hiện tại sở hữu vòng đời của luồng. Nếu không, phối hợp hợp đồng sở hữu hoặc chỉ `flush()` tại chỗ phù hợp.

## 8. Ký tự không mã hóa được và dữ liệu Unicode lỗi

Không phải charset nào cũng biểu diễn được toàn bộ Unicode. `US_ASCII` chỉ biểu diễn các ký tự trong phạm vi ASCII. Chẳng hạn, chuỗi `"café"` có ký tự `é` không thể mã hóa nguyên dạng bằng `US_ASCII`.

Khi tạo `OutputStreamWriter` theo charset thông thường, mặc định lớp này **thay thế** các chuỗi ký tự không thể mã hóa hoặc surrogate không hợp lệ bằng chuỗi byte thay thế của charset. Điều này có thể làm mất thông tin nhưng không nhất thiết phát sinh exception.

Nếu định dạng dữ liệu yêu cầu **không mất ký tự**, dùng một `CharsetEncoder` được cấu hình hành động `REPORT`:

```java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(
        new ByteArrayOutputStream(), encoder)) {
    writer.write("café");
} catch (CharacterCodingException e) {
    // Ký tự không thể biểu diễn bằng US-ASCII;
    // xử lý lỗi ở tầng nghiệp vụ thay vì chấp nhận mất dữ liệu.
}
```

Đây là **mảnh mã minh họa**; cần import `java.io.*`, `java.nio.charset.*`. `CharacterCodingException` là một loại `IOException`. Lỗi có thể xuất hiện trong khi ghi, flush hoặc đóng, tùy bộ đệm và trạng thái mã hóa. Nếu thay `REPORT` bằng `REPLACE` hoặc `IGNORE`, ứng dụng đang chấp nhận thay thế/bỏ mất ký tự — đó phải là quyết định có chủ ý.

Trong phần lớn tình huống văn bản tiếng Việt và Unicode hiện đại, **UTF-8** là lựa chọn thực tế, tương thích và biểu diễn đầy đủ Unicode hợp lệ. Tuy nhiên, ngay cả với UTF-8, dữ liệu `String` chứa surrogate lẻ vẫn là UTF-16 không hợp lệ; quy tắc thay thế hoặc báo lỗi vẫn cần được hiểu.

## 9. Tình huống thực tế: ghi văn bản vào socket

Giả sử một giao thức văn bản dùng **UTF-8**, mỗi thông điệp kết thúc bằng byte LF (`0A`):

```java
OutputStream socketBytes = socket.getOutputStream();
Writer writer = new BufferedWriter(
        new OutputStreamWriter(socketBytes, StandardCharsets.UTF_8));

writer.write("HELLO Xin chào\n");
writer.flush();
```

Đây là mảnh mã: `socket` đã được kết nối; xử lý `IOException` và quản lý đóng socket tại tầng sở hữu. Ứng dụng phải thống nhất với đầu nhận rằng thông điệp dùng UTF-8 và được phân tách bằng LF. `flush()` giúp đẩy dữ liệu đang đệm để bên nhận có thể xử lý, nhưng **không xác nhận** rằng đầu nhận đã nhận hay xử lý xong.

Nếu gửi **giao thức nhị phân** trộn header độ dài, checksum và payload văn bản, phải định nghĩa thứ tự byte và ranh giới rõ ràng. Ví dụ cần khai báo độ dài payload bằng **số byte UTF-8** (`payload.getBytes(UTF_8).length`), không dùng `payload.length()`. Nếu mã hóa ra bytes trong bộ đệm trước, số byte này là chính xác; nếu stream dần, thiết kế cách truyền độ dài hoặc cơ chế framing trước khi gửi.

Không ghi đồng thời qua `OutputStreamWriter` và trực tiếp lên cùng `OutputStream` khi còn ký tự/byte đệm chưa xả: thứ tự thực tế có thể khác thứ tự lệnh ở hai lớp bọc. Đặt một chủ sở hữu pipeline hoặc có quy tắc đồng bộ/flush/đóng rõ ràng. Đối với HTTP, JSON hoặc các giao thức có serializer riêng, ưu tiên API serializer/thư viện phù hợp nếu chúng cung cấp quy tắc escaping, charset và framing đầy đủ.

## 10. Phân biệt với các API gần nhau

| API | Đơn vị xử lý | Khi nào phù hợp |
| --- | --- | --- |
| `OutputStream` / `FileOutputStream` | Byte | Ghi byte nhị phân hoặc byte đã mã hóa sẵn |
| `OutputStreamWriter` | Nhận ký tự, mã hóa ra byte | Ghi văn bản với charset xác định lên bất kỳ `OutputStream` |
| `BufferedWriter` | Ký tự, có bộ đệm ký tự | Nhiều lần ghi nhỏ, ghi theo dòng, bọc ngoài `Writer` |
| `InputStreamReader` | Nhận byte, giải mã ra ký tự | Đọc văn bản từ `InputStream` theo charset |
| `String.getBytes(charset)` | Mã hóa cả chuỗi thành `byte[]` | Khi toàn bộ chuỗi đã có sẵn trong bộ nhớ, cần mảng byte |
| `Files.newBufferedWriter(path, charset)` | `Writer` thuận tiện cho file | Ghi văn bản vào tệp khi không cần tự quản lý các lớp stream |

`FileWriter` là một lớp con của `OutputStreamWriter` thuận tiện cho file; Java 17 cũng có constructor nhận `Charset`. `OutputStreamWriter` đáng học vì nó cho thấy rõ mô hình chuyển đổi ký tự ↔ byte và áp dụng cho các đích không chỉ là file.

Ví dụ hiện đại cho tệp có thể ngắn gọn:

```java
try (BufferedWriter writer = Files.newBufferedWriter(
        Path.of("message.txt"), StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
}
```

Đoạn minh họa cần import `java.nio.file.*`, `java.nio.charset.StandardCharsets`, `java.io.BufferedWriter` và xử lý `IOException`. Cơ chế trừu tượng hóa vẫn như trên: thao tác với ký tự, cuối cùng ghi byte bằng charset.

## 11. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Không chỉ định charset | Kết quả thay đổi khi môi trường mặc định khác | Truyền `StandardCharsets.UTF_8` hoặc charset do protocol quy định |
| Ghi UTF-8 nhưng giải mã theo charset khác | Văn bản lỗi dấu, ký tự thay thế | Ghi/đọc bằng cùng charset và thỏa thuận định dạng |
| Cho rằng `String.length()` là số byte | Sai độ dài bản tin, cắt dữ liệu Unicode | Mã hóa ra bytes rồi đếm hoặc tính kích thước bằng encoder đúng |
| Gọi `write(...)` rồi đọc file/đích ngay mà chưa flush/close | Có thể chưa thấy đủ byte | `flush()` khi cần, `close()` khi hoàn tất |
| Đóng writer trên `System.out`/socket do nơi khác sở hữu | Thành phần khác không thể tiếp tục ghi | Thiết kế rõ ownership, chỉ đóng khi sở hữu đích |
| Dùng `write(int)` cho emoji code point | Cắt còn một đơn vị `char` | Dùng `write(String)` hoặc `Character.toChars(...)` |
| Đọc và ghi văn bản trên cùng stream nhưng bỏ qua charset | Dữ liệu truyền bị hỏng hoặc mất chữ | Ghép `InputStreamReader`/`OutputStreamWriter` với charset nhất quán |
| Cho rằng `flush()` đồng nghĩa file đã bền vững/đầu nhận đã ACK | Kết luận sai về trạng thái ghi | Dùng `FileDescriptor.sync`/`FileChannel.force` hoặc ACK giao thức khi thật sự cần |
| Dùng `newLine()` trong định dạng yêu cầu LF tuyệt đối | Byte cuối dòng khác giữa hệ điều hành | Dùng `write("\n")` khi protocol quy định LF |
| Mong mọi ký tự không mã hóa được sẽ ném exception | Có thể bị thay bằng byte khác và mất dữ liệu | Dùng `CharsetEncoder` với `CodingErrorAction.REPORT` |

## 12. Câu hỏi tự kiểm tra

1. **OutputStreamWriter đi theo hướng nào?** Từ ký tự Java (`Writer`) sang byte (`OutputStream`), sử dụng charset được chọn.
2. **Vì sao UTF-8 đầu ra không thể lấy kích thước bằng `String.length()`?** Vì mỗi Unicode code point có thể chiếm 1–4 byte trong UTF-8, trong khi Java `char` là đơn vị UTF-16.
3. **Vì sao nên bọc `BufferedWriter` ngoài `OutputStreamWriter`?** Để gom các lần ghi ký tự nhỏ trước khi mã hóa, giảm nhiều lần gọi chuyển đổi.
4. **`flush()` có đóng writer hay bảo đảm ACK mạng không?** Không. `flush()` đẩy các bộ đệm liên quan nhưng không đóng và không xác nhận đầu xa.
5. **`close()` trên OutputStreamWriter ảnh hưởng gì đến OutputStream?** Writer hoàn tất và đóng luồng byte bên dưới, nên phải rõ quyền sở hữu.
6. **Điều gì xảy ra khi charset không biểu diễn được ký tự?** Mặc định writer có thể thay thế; nếu cần báo lỗi, dùng `CharsetEncoder` với `REPORT`.
7. **Đoạn code ghi `"Aé中😀\n"` theo UTF-8 sinh bao nhiêu byte?** 11 byte; `String.length()` của chuỗi là 6.
8. **Nếu bản tin dùng LF (`0A`), nên dùng `newLine()` không?** Không khi yêu cầu byte chính xác; dùng `write("\n")`.

## Nguồn tra cứu API chính thức

- [Java 17 — OutputStreamWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html).
- [Java 17 — BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html).
- [Java 17 — CharsetEncoder và CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html).
- [Java 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [Java 17 — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html).

**Điểm cốt lõi:** `OutputStreamWriter` không đơn thuần “ghi String ra file”. Nó là tầng mã hóa có trạng thái, nằm giữa API ký tự và API byte. Việc chọn charset, sử dụng buffer, quản lý flush/close và quyền sở hữu luồng quyết định văn bản có đúng, đủ và được chuyển đến nơi cần ghi hay không.