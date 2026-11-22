# Đọc dữ liệu văn bản, chuyển byte sang hex và ghi kết quả

Một chương trình Java có thể cần đọc file văn bản, biểu diễn các byte dưới dạng hexadecimal (hex), rồi ghi kết quả ra file khác. Công việc này hữu ích khi kiểm tra encoding, xem payload, đối chiếu dữ liệu hoặc lưu một bản biểu diễn dễ đọc của nội dung nhị phân.

Java 17 có sẵn các API tiêu chuẩn để thực hiện quy trình:

- Files.readString đọc file văn bản thành String theo charset xác định.
- Files.readAllBytes đọc nguyên byte của file thành byte array.
- String.getBytes(Charset) mã hóa chuỗi thành byte.
- HexFormat chuyển byte thành hex và parse hex về byte. API này có từ Java 17.
- Files.writeString ghi văn bản; Files.write ghi byte.
- Files.newInputStream và Files.newBufferedWriter xử lý file theo từng khối.

Trước khi viết code, cần xác định rõ muốn chuyển **byte gốc của file** hay byte được tạo ra sau khi **giải mã văn bản rồi mã hóa lại**. Hai cách có thể cho kết quả khác nhau. Nếu cần biểu diễn chính xác file ở mức byte, hãy đọc byte trực tiếp.

## 1. Byte và biểu diễn hexadecimal

Một byte có 8 bit, nên có 256 giá trị từ 0 đến 255 (0x00 đến 0xFF). Hexadecimal dùng 16 ký hiệu: 0–9 và A–F. Mỗi chữ số hex biểu diễn 4 bit, do đó một byte luôn được viết bằng hai chữ số hex.

| Giá trị byte | Nhị phân | Hex |
| ---: | --- | --- |
| 0 | 00000000 | 00 |
| 10 | 00001010 | 0A |
| 65 | 01000001 | 41 |
| 127 | 01111111 | 7F |
| 255 | 11111111 | FF |

Ví dụ, các byte sau:

```text
48 65 6C 6C 6F
```

có biểu diễn hex liên tục:

```text
48656C6C6F
```

Nếu giải mã theo UTF-8, chúng tương ứng với văn bản Hello. Hex chỉ là cách viết dễ đọc của byte; chuyển byte sang hex không thay đổi dữ liệu gốc.

## 2. Chọn đúng cách đọc file

Có hai trường hợp thường gặp:

1. File được xem là văn bản theo một charset xác định.
2. Cần lấy chính xác các byte đang có trong file, bất kể chúng có phải văn bản hợp lệ hay không.

Không nên trộn hai trường hợp vì decode/encode là một bước chuyển đổi dữ liệu.

### 2.1. Đọc file văn bản bằng Files.readString

Với file văn bản UTF-8:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("data", "message.txt");
String content = Files.readString(input, StandardCharsets.UTF_8);
System.out.println(content);
```

Files.readString(Path, Charset) có từ Java 11. Phương thức đọc toàn bộ file và giải mã thành String theo charset đã chỉ định. Overload không nhận charset cũng dùng UTF-8, nhưng chỉ định StandardCharsets.UTF_8 giúp hợp đồng encoding thể hiện rõ trong code.

String là chuỗi ký tự của Java, không còn là mảng byte gốc của file.

### 2.2. Đọc toàn bộ byte bằng Files.readAllBytes

Nếu cần chuyển chính xác byte file sang hex:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("data", "message.txt");
byte[] bytes = Files.readAllBytes(input);
```

readAllBytes trả về toàn bộ nội dung file trong byte array. Phương thức không giải mã văn bản, không đổi charset và không chuẩn hóa line ending.

Đây là lựa chọn phù hợp khi cần hex dump chính xác, khi file có byte không hợp lệ theo UTF-8, hoặc khi cần bảo toàn BOM, CRLF/LF và các byte đặc biệt. Vì toàn bộ nội dung được giữ trong bộ nhớ, không dùng readAllBytes cho file rất lớn nếu không có ngân sách RAM tương ứng.

### 2.3. So sánh các API đọc

| Nhu cầu | API phù hợp |
| --- | --- |
| Đọc văn bản UTF-8 thành chuỗi | Files.readString(path, UTF_8) |
| Lấy byte nguyên gốc của file | Files.readAllBytes(path) |
| Đọc file lớn theo khối byte | Files.newInputStream(path) |
| Đọc file văn bản lớn theo dòng | Files.newBufferedReader(path, UTF_8) |

Nếu mục tiêu là chuyển nội dung file sang hex theo nghĩa byte-for-byte, hãy dùng API byte. Nếu mục tiêu là lấy chuỗi văn bản, mã hóa thành UTF-8 rồi biểu diễn byte UTF-8 dưới dạng hex, hãy đọc text trước và mã hóa lại tường minh.

## 3. Đọc văn bản rồi chuyển thành byte

String không phải byte array. Muốn chuyển nội dung chuỗi thành byte cần chọn charset:

```java
import java.nio.charset.StandardCharsets;

String content = "Hello, Java 17!";
byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
```

getBytes(StandardCharsets.UTF_8) mã hóa chuỗi thành byte UTF-8. Không nên dựa vào charset mặc định của máy khi dữ liệu được trao đổi giữa nhiều hệ thống. Hai máy có default charset khác nhau có thể tạo byte khác nhau từ cùng một chuỗi.

### 3.1. Cùng văn bản có thể có nhiều biểu diễn byte

Một ký tự có thể được mã hóa thành số byte khác nhau tùy charset. Chữ A trong UTF-8 là một byte 41; ký tự tiếng Việt có dấu thường cần nhiều byte UTF-8. Vì vậy, hex là biểu diễn của byte, không phải biểu diễn trực tiếp của ký tự Unicode.

### 3.2. Byte gốc và byte sau khi mã hóa lại

```java
byte[] original = Files.readAllBytes(input);
String text = Files.readString(input, StandardCharsets.UTF_8);
byte[] encodedAgain = text.getBytes(StandardCharsets.UTF_8);
```

Với văn bản UTF-8 hợp lệ và không có bước biến đổi chuỗi, hai mảng thường giống nhau. Tuy nhiên, không nên mặc định chúng luôn giống trong mọi tình huống: đầu vào có thể không hợp lệ theo UTF-8, code có thể chuẩn hóa Unicode hoặc thay đổi nội dung, hoặc quy trình decode/encode có thể xử lý BOM theo chính sách khác.

Khi cần byte-for-byte fidelity, đừng decode rồi encode lại. Hãy chuyển trực tiếp byte gốc.

## 4. Chuyển byte sang hex bằng HexFormat

Java 17 có java.util.HexFormat, API tiêu chuẩn để định dạng và phân tích dữ liệu hexadecimal:

```java
import java.util.HexFormat;

byte[] bytes = {
    0x48, 0x65, 0x6C, 0x6C, 0x6F
};

String hex = HexFormat.of().formatHex(bytes);
System.out.println(hex);
// 48656c6c6f
```

HexFormat.of() tạo formatter mặc định: dùng chữ số hex thường, không có dấu phân cách và không thêm tiền tố 0x. Mỗi byte luôn có hai chữ số; byte 0x0A được ghi thành 0a, không phải a.

### 4.1. Dùng chữ hoa

```java
HexFormat hexFormat = HexFormat.of().withUpperCase();
String hex = hexFormat.formatHex(bytes);
```

Kết quả: 48656C6C6F.

### 4.2. Thêm dấu phân cách giữa các byte

```java
HexFormat hexFormat = HexFormat.ofDelimiter(" ");
String hex = hexFormat.formatHex(bytes);
```

Kết quả: 48 65 6c 6c 6f.

Có thể kết hợp delimiter và chữ hoa:

```java
HexFormat hexFormat = HexFormat.ofDelimiter(" ").withUpperCase();
String hex = hexFormat.formatHex(bytes);
```

Kết quả: 48 65 6C 6C 6F.

### 4.3. Thêm prefix và suffix

```java
HexFormat hexFormat = HexFormat.ofDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

String hex = hexFormat.formatHex(bytes);
```

Kết quả: 0x48 0x65 0x6C 0x6C 0x6F. Prefix và suffix được áp dụng cho từng byte.

### 4.4. Chỉ định một đoạn byte

```java
String hex = HexFormat.of().formatHex(bytes, 1, 4);
```

Hai chỉ số là fromIndex inclusive và toIndex exclusive. Ví dụ trên định dạng các byte ở vị trí 1, 2 và 3.

## 5. Ví dụ hoàn chỉnh: đọc file và ghi chuỗi hex

Ví dụ sau đọc byte gốc của file, chuyển sang hex và ghi kết quả vào file khác:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class TextToHex {
    public static void main(String[] args) throws IOException {
        Path input = Path.of("data", "message.txt");
        Path output = Path.of("out", "message.hex");

        byte[] bytes = Files.readAllBytes(input);
        String hex = HexFormat.of().formatHex(bytes);

        Files.createDirectories(output.getParent());
        Files.writeString(
                output,
                hex + System.lineSeparator(),
                StandardCharsets.UTF_8
        );

        System.out.println("Read " + bytes.length + " bytes");
        System.out.println("Wrote hex to " + output);
    }
}
```

Luồng xử lý:

1. Path.of tạo đường dẫn file vào và file ra.
2. Files.readAllBytes đọc byte gốc.
3. HexFormat.of().formatHex tạo chuỗi hex.
4. Files.createDirectories tạo thư mục output nếu chưa có.
5. Files.writeString ghi kết quả bằng UTF-8.

Nếu không có delimiter hoặc prefix, phần hex có độ dài đúng hai lần số byte đầu vào. Ví dụ 5 byte tạo 10 ký tự hex. System.lineSeparator thêm ký tự xuống dòng ở cuối.

Không đặt input và output trỏ tới cùng một file. Files.writeString mặc định tạo hoặc truncate file đích; ghi đè file đầu vào có thể làm mất dữ liệu nguồn.

### 5.1. Ghi hex có dấu cách

Thay formatter bằng:

```java
HexFormat hexFormat = HexFormat.ofDelimiter(" ").withUpperCase();
String hex = hexFormat.formatHex(bytes);
```

Với n byte, dạng liên tục cần 2n ký tự hex. Dạng có một dấu cách giữa các byte cần 3n - 1 ký tự, chưa tính line ending.

## 6. Ghi kết quả bằng Files.writeString

Files.writeString phù hợp với output là văn bản:

```java
Files.writeString(output, hex, StandardCharsets.UTF_8);
```

Overload có charset cho phép chỉ định encoding. Nếu không truyền charset, API dùng UTF-8.

Khi không truyền OpenOption, phương thức mặc định tạo file nếu chưa có và truncate nội dung cũ nếu file đã tồn tại. Có thể chỉ định rõ:

```java
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.TRUNCATE_EXISTING;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(
        output,
        hex,
        StandardCharsets.UTF_8,
        CREATE,
        TRUNCATE_EXISTING,
        WRITE
);
```

### 6.1. Ghi nối tiếp vào file

```java
import static java.nio.file.StandardOpenOption.APPEND;
import static java.nio.file.StandardOpenOption.CREATE;

Files.writeString(
        output,
        hex + System.lineSeparator(),
        StandardCharsets.UTF_8,
        CREATE,
        APPEND
);
```

APPEND phù hợp với log hoặc kết quả của nhiều lần chạy. Nếu nhiều thread/process cùng ghi một file, cần thiết kế đồng bộ hoặc file riêng; không mặc định các lần append của nhiều writer là một giao dịch nguyên tử.

## 7. Chuyển hex ngược thành byte

HexFormat cũng hỗ trợ parse chuỗi hex thành byte array:

```java
import java.util.HexFormat;

String hex = "48656c6c6f";
byte[] bytes = HexFormat.of().parseHex(hex);
```

Nếu hex có delimiter, hãy dùng formatter tương ứng:

```java
HexFormat spaced = HexFormat.ofDelimiter(" ");
byte[] bytes = spaced.parseHex("48 65 6c 6c 6f");
```

Có thể ghi byte trở lại file:

```java
Files.write(Path.of("out", "restored.bin"), bytes);
```

Khi chuỗi hex được tạo từ byte gốc và không bị sửa đổi, parse lại sẽ khôi phục chính xác mảng byte ban đầu.

### 7.1. Kiểm tra hex không hợp lệ

Hex phải có ký tự hợp lệ và đúng định dạng. Chuỗi có ký tự không phải hex, delimiter không khớp hoặc số chữ số không hợp lệ có thể khiến parseHex ném IllegalArgumentException.

```java
try {
    byte[] bytes = HexFormat.of().parseHex(userInput);
    Files.write(output, bytes);
} catch (IllegalArgumentException ex) {
    System.err.println("Hex input is invalid");
}
```

Nếu dữ liệu hex đến từ bên ngoài, hãy giới hạn độ dài chuỗi trước khi parse. Chuỗi có 2n chữ số hex đại diện cho n byte, nên dữ liệu text có thể lớn gấp đôi dữ liệu gốc.

## 8. Đọc văn bản UTF-8 rồi xuất hex của nội dung đã mã hóa

Nếu yêu cầu là đọc văn bản thành String, sau đó xuất byte UTF-8 của chuỗi:

```java
Path input = Path.of("data", "message.txt");
Path output = Path.of("out", "message-utf8.hex");

String text = Files.readString(input, StandardCharsets.UTF_8);
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
String hex = HexFormat.of().formatHex(utf8);

Files.createDirectories(output.getParent());
Files.writeString(output, hex, StandardCharsets.UTF_8);
```

Ở đây hex biểu diễn byte UTF-8 được tạo từ chuỗi text. Nếu cần byte gốc của file, dùng Files.readAllBytes(input) thay cho chuỗi decode/encode.

Không gọi trim, strip, replace hoặc chuẩn hóa Unicode nếu mục tiêu là giữ nguyên nội dung. trim/strip có thể bỏ khoảng trắng đầu/cuối; thay CRLF bằng LF làm thay đổi byte sau khi mã hóa lại.

## 9. Xử lý file lớn theo từng khối

readAllBytes và readString đọc toàn bộ file vào bộ nhớ. Với file lớn, cách này có thể gây áp lực heap hoặc OutOfMemoryError.

Có thể đọc từng khối byte và ghi hex tuần tự:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HexFormat;

public class LargeFileToHex {
    public static void convert(Path input, Path output)
            throws IOException {

        HexFormat hexFormat = HexFormat.of();
        byte[] buffer = new byte[8192];

        Path parent = output.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        try (InputStream in = Files.newInputStream(input);
             BufferedWriter writer = Files.newBufferedWriter(
                     output,
                     StandardCharsets.UTF_8,
                     StandardOpenOption.CREATE,
                     StandardOpenOption.TRUNCATE_EXISTING,
                     StandardOpenOption.WRITE)) {

            int count;
            while ((count = in.read(buffer)) != -1) {
                hexFormat.formatHex(writer, buffer, 0, count);
            }
        }
    }
}
```

Overload formatHex(Appendable, byte[], int, int) ghi trực tiếp vào Appendable, tránh tạo một chuỗi trung gian cho toàn bộ file. BufferedWriter gom các lần ghi nhỏ để giảm số lần truy cập I/O.

Ví dụ gọi:

```java
LargeFileToHex.convert(
        Path.of("data", "large-input.bin"),
        Path.of("out", "large-input.hex")
);
```

Ví dụ ghi hex liên tục, không delimiter và không line break. Bộ nhớ dành cho buffer được giữ ở mức cố định, không tăng theo kích thước file. File đầu ra vẫn lớn xấp xỉ gấp đôi số byte đầu vào.

### 9.1. Vì sao không đọc toàn bộ file lớn?

Nếu file đầu vào có N byte:

- Mảng đầu vào cần xấp xỉ N byte, chưa tính overhead.
- Chuỗi hex cần khoảng 2N ký tự; chi phí bộ nhớ thực tế phụ thuộc cách runtime biểu diễn String.
- Nếu giữ đồng thời cả mảng và chuỗi, peak memory có thể cao hơn nhiều lần kích thước file.

Streaming tránh giữ toàn bộ input và output trong heap cùng lúc.

### 9.2. Xử lý lỗi trong lúc stream

Đọc/ghi có thể thất bại do file bị xóa, quyền thay đổi, filesystem đầy hoặc lỗi thiết bị. Try-with-resources bảo đảm stream và writer được đóng khi có lỗi.

Nếu output bị ghi dở, ứng dụng có thể để lại file chưa hoàn chỉnh. Khi cần kết quả nguyên vẹn, có thể ghi vào file tạm trong cùng filesystem, đóng file thành công rồi đổi tên sang đích cuối bằng Files.move. Cần xác định chính sách thay thế file đích và hỗ trợ atomic move của filesystem.

## 10. Ghi hex theo dòng hoặc theo nhóm byte

Với mảng đã có trong bộ nhớ:

```java
HexFormat format = HexFormat.ofDelimiter(" ").withUpperCase();
String hex = format.formatHex(bytes);
```

Nếu cần chia thành các dòng 16 byte:

```java
HexFormat format = HexFormat.ofDelimiter(" ").withUpperCase();
StringBuilder result = new StringBuilder();

for (int offset = 0; offset < bytes.length; offset += 16) {
    int end = Math.min(offset + 16, bytes.length);
    result.append(format.formatHex(bytes, offset, end))
          .append(System.lineSeparator());
}
```

Với file lớn, không tạo StringBuilder chứa toàn bộ output. Hãy format từng đoạn rồi ghi ngay vào BufferedWriter. Nếu cần mỗi dòng đúng 16 byte, phải quản lý ranh giới dòng độc lập với số byte mà một lần InputStream.read trả về, vì read không cam kết luôn lấp đầy buffer.

## 11. Charset, BOM và line ending

Encoding và cách biểu diễn byte có thể ảnh hưởng kết quả hex.

### 11.1. Chỉ định charset rõ ràng

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
```

Nếu file dùng charset khác, phải chỉ định đúng charset đó. Không thể xác định charset đáng tin cậy chỉ bằng cách nhìn một vài byte; một số định dạng có BOM hoặc metadata riêng, nhưng nhiều file không có thông tin encoding.

### 11.2. BOM

Một số file văn bản bắt đầu bằng byte order mark (BOM). Khi đọc byte gốc, BOM vẫn nằm trong mảng và được chuyển thành hex như mọi byte khác.

Khi đọc bằng decoder, cách BOM được diễn giải phụ thuộc charset và decoder. Với UTF-8, BOM có thể được giữ lại dưới dạng ký tự U+FEFF thay vì tự động bị loại bỏ. Nếu sau đó mã hóa lại, byte BOM có thể xuất hiện lại.

Nếu ứng dụng cần loại bỏ BOM theo định dạng file, hãy thực hiện thành quy tắc rõ ràng và chỉ làm khi đặc tả dữ liệu yêu cầu. Đừng tự động xóa byte đầu tiên chỉ vì nó có vẻ khác thường.

### 11.3. Line ending

Windows thường dùng CRLF, trong khi nhiều môi trường Unix dùng LF. Khi đọc byte gốc và format hex, cả byte CR và LF được giữ nguyên.

Nếu đọc văn bản rồi thay CRLF bằng LF, byte đầu ra sau khi mã hóa sẽ khác file gốc. Đừng chuẩn hóa line ending nếu đang cần so sánh hoặc lưu biểu diễn byte chính xác.

## 12. Xử lý lỗi và xác thực đường dẫn

Các thao tác file có thể ném IOException hoặc các exception cụ thể:

| Lỗi | Nguyên nhân có thể gặp |
| --- | --- |
| NoSuchFileException | File hoặc thư mục cha không tồn tại. |
| AccessDeniedException | Tiến trình không có quyền đọc hoặc ghi. |
| FileAlreadyExistsException | Thao tác tạo file không cho phép đè file hiện có. |
| InvalidPathException | Chuỗi đường dẫn không hợp lệ với filesystem hiện tại. |
| IOException | Lỗi đọc/ghi, filesystem hoặc thiết bị. |
| IllegalArgumentException từ parseHex | Chuỗi hex không hợp lệ theo formatter. |

Ví dụ:

```java
try {
    byte[] bytes = Files.readAllBytes(input);
    String hex = HexFormat.of().formatHex(bytes);
    Files.writeString(output, hex, StandardCharsets.UTF_8);
} catch (java.nio.file.NoSuchFileException ex) {
    System.err.println("Input file does not exist: " + input);
} catch (java.nio.file.AccessDeniedException ex) {
    System.err.println("Permission denied: " + ex.getFile());
} catch (IOException ex) {
    System.err.println("File processing failed: " + ex.getMessage());
}
```

Không nên bắt mọi exception rồi tiếp tục như thể kết quả đã được ghi thành công. Nếu chuyển đổi thất bại, cần báo lỗi và tránh sử dụng file output dở dang.

### 12.1. Kiểm tra file trước khi đọc

```java
if (!Files.isRegularFile(input)) {
    throw new IOException("Input is not a regular file");
}

long size = Files.size(input);
if (size > 50L * 1024 * 1024) {
    throw new IOException("Input file is too large");
}
```

Giới hạn kích thước là ví dụ; chọn theo nhu cầu ứng dụng. Kiểm tra trước không loại bỏ hoàn toàn race condition: file có thể thay đổi sau khi kiểm tra. Với file không tin cậy hoặc có thể bị tiến trình khác thay đổi, vẫn cần xử lý lỗi trong lúc đọc và giới hạn ở tầng stream.

## 13. Ví dụ tổng hợp: đọc text UTF-8, tạo hex và ghi file

Phiên bản này phù hợp với file văn bản nhỏ hoặc vừa, khi mục tiêu là biểu diễn byte UTF-8 của nội dung đã đọc:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class TextHexExporter {
    public static void main(String[] args) throws IOException {
        Path input = Path.of("input", "note.txt");
        Path output = Path.of("output", "note.hex");

        String text = Files.readString(input, StandardCharsets.UTF_8);
        byte[] utf8Bytes = text.getBytes(StandardCharsets.UTF_8);

        HexFormat formatter = HexFormat.ofDelimiter(" ")
                .withUpperCase();
        String hex = formatter.formatHex(utf8Bytes);

        Path parent = output.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        Files.writeString(
                output,
                hex + System.lineSeparator(),
                StandardCharsets.UTF_8
        );

        System.out.println("Characters: " + text.length());
        System.out.println("UTF-8 bytes: " + utf8Bytes.length);
        System.out.println("Hex output: " + output.toAbsolutePath());
    }
}
```

Nếu yêu cầu là hex của byte gốc file, thay phần đọc và mã hóa bằng:

```java
byte[] sourceBytes = Files.readAllBytes(input);
String hex = HexFormat.ofDelimiter(" ")
        .withUpperCase()
        .formatHex(sourceBytes);
```

Không thực hiện cả hai quy trình rồi giả định kết quả phải giống nhau. Hãy chọn đúng định nghĩa dữ liệu đầu ra của bài toán.

## 14. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hex thiếu số 0 ở đầu byte | Tự chuyển đổi mà không định dạng đủ hai chữ số. | Dùng HexFormat; mỗi byte luôn có hai chữ số hex. |
| Hex khác giữa hai máy | Charset mặc định hoặc cách chuẩn hóa chuỗi khác nhau. | Chỉ định charset rõ ràng, thường là UTF-8 theo hợp đồng dữ liệu. |
| Hex không giống byte gốc | Đã decode thành String rồi encode lại hoặc thay đổi nội dung. | Dùng readAllBytes/stream byte nếu cần byte-for-byte. |
| File lớn gây thiếu bộ nhớ | Dùng readAllBytes, readString hoặc giữ chuỗi hex rất lớn. | Đọc theo khối bằng InputStream và ghi qua BufferedWriter. |
| File output bị cắt nội dung cũ | writeString mặc định truncate file đích. | Dùng file tạm, hoặc chọn APPEND nếu muốn nối. |
| Kết quả có dấu cách nhưng parse thất bại | Formatter parse không dùng delimiter tương ứng. | Dùng cùng HexFormat cấu hình delimiter để parse. |
| parseHex ném IllegalArgumentException | Có ký tự không phải hex, delimiter sai hoặc dữ liệu không hợp lệ. | Xác thực input và xử lý exception. |
| Mất CRLF hoặc BOM | Quy trình text đã chuẩn hóa hoặc loại bỏ dữ liệu đặc biệt. | Chuyển byte trực tiếp nếu cần giữ nguyên file. |
| File không tìm thấy | Đường dẫn tương đối phụ thuộc thư mục làm việc hiện tại. | Xác định working directory hoặc dùng đường dẫn/resource phù hợp. |
| Output không hoàn chỉnh | Lỗi I/O xảy ra giữa lúc ghi hoặc process bị dừng. | Ghi file tạm, đóng thành công rồi đổi tên nếu cần tính nguyên vẹn. |

## 15. Bài tập thực hành

### Bài 1 — Đọc và in hex

Tạo file message.txt chứa Hello, Java 17!. Dùng Files.readAllBytes và HexFormat.of().formatHex để in hex. Giải thích vì sao mỗi byte có hai chữ số.

### Bài 2 — So sánh UTF-8 và byte gốc

Tạo file chứa tiếng Việt có dấu. So sánh hex của Files.readAllBytes với hex của Files.readString(..., UTF_8).getBytes(UTF_8). Giải thích điều kiện để hai mảng byte giống nhau.

### Bài 3 — Đổi kiểu hiển thị

Thử withUpperCase, ofDelimiter(" "), withPrefix("0x") và withSuffix. Ghi lại kết quả và dùng formatter tương ứng để parse lại.

### Bài 4 — Ghi kết quả ra file

Dùng Files.writeString để ghi hex. Chạy hai lần và quan sát hành vi truncate; sau đó dùng CREATE và APPEND để nối kết quả.

### Bài 5 — Xử lý file lớn

Tạo file binary lớn, viết chương trình đọc theo buffer và gọi HexFormat.formatHex(Appendable, ...) để ghi ra file. Quan sát heap usage so với cách dùng readAllBytes.

### Bài 6 — Khôi phục dữ liệu

Đọc file hex, parse bằng HexFormat.parseHex, ghi mảng byte trở lại file mới và so sánh checksum hoặc nội dung byte của hai file.

## 16. Tài liệu Java 17 chính thức

- [Java SE 17 API — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): định dạng byte thành hex, delimiter, prefix, suffix, chữ hoa và parse hex.
- [Java SE 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): readString, readAllBytes, writeString, stream và thao tác file.
- [Java SE 17 API — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset tiêu chuẩn như UTF-8 và UTF-16.
- [Java SE 17 API — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): biểu diễn và thao tác đường dẫn file.

Khi chuyển dữ liệu sang hex, hãy xác định rõ cần biểu diễn **byte gốc của file** hay byte UTF-8 được tạo từ văn bản đã giải mã. Với file nhỏ, Files.readAllBytes kết hợp HexFormat và Files.writeString là cách ngắn gọn, rõ ràng. Với file lớn, đọc theo từng khối và ghi trực tiếp qua writer để giữ mức sử dụng bộ nhớ ổn định. Luôn chỉ định charset khi xử lý text, không chuẩn hóa nội dung ngoài ý muốn và kiểm tra file output sau khi ghi.
