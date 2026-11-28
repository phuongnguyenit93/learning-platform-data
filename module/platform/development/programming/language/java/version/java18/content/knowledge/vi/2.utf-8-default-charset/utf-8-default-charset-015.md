# UTF-8 mặc định không tự chuyển đổi dữ liệu hoặc tệp đã lưu bằng charset khác

## 1. UTF-8 mặc định thay đổi cách Java diễn giải byte, không sửa byte đã tồn tại

Từ **JDK 18**, theo **JEP 400**, UTF-8 là default charset thông thường của Java SE trên các hệ điều hành. Thay đổi này làm cho những API phụ thuộc default charset chọn UTF-8 khi chuyển đổi giữa byte và ký tự.

Nhưng một file đã được ghi bằng Windows-1258, Windows-1252, ISO-8859-1 hoặc UTF-16 vẫn giữ nguyên các byte cũ. Nâng cấp JDK không mở file rồi mã hóa lại nội dung, không sửa byte trên đĩa và cũng không tự gắn metadata UTF-8 cho file đó.

Ví dụ, một file cũ có byte được tạo theo Windows-1258. Trước khi nâng cấp, ứng dụng có thể đọc bằng:

```java
String text = new String(bytes);
```

Trên JDK cũ, lời gọi này có thể dùng default charset của môi trường, tình cờ khớp với encoding file. Trên JDK 18+, default charset thông thường là UTF-8, nên cùng các byte cũ được giải mã theo UTF-8. Kết quả có thể sai, dù file trên đĩa không hề thay đổi.

**Điểm cốt lõi:** JEP 400 thay đổi lựa chọn charset mặc định của JVM cho các API liên quan. Nó không phải công cụ chuyển đổi dữ liệu đã lưu. Muốn đổi một file từ charset cũ sang UTF-8, phải đọc byte bằng charset nguồn đúng, giải mã thành văn bản, sau đó mã hóa lại bằng UTF-8 và ghi ra đích.

Bài học thuộc chương **UTF-8 mặc định** của mô-đun `JAVA_VERSION_JAVA18`. Trọng tâm là hiểu sự khác nhau giữa thay đổi cấu hình runtime và chuyển đổi nội dung dữ liệu, tránh làm hỏng file legacy khi nâng cấp ứng dụng.

## 2. Byte của file không tự thay đổi khi nâng cấp JDK

Một file văn bản thông thường lưu byte. Charset là quy tắc dùng để diễn giải dãy byte đó thành ký tự; nó không phải thuộc tính mà hệ thống file tự động gắn cho mọi file.

Ví dụ, ký tự `à` có byte UTF-8:

```text
C3 A0
```

Trong ISO-8859-1, ký tự `à` có byte:

```text
E0
```

Cùng một byte `E0` có thể mang ý nghĩa khác trong một charset khác; byte `C3 A0` khi đọc theo một charset khác UTF-8 cũng có thể trở thành ký tự khác hoặc chuỗi lỗi. Byte không tự nói cho chương trình biết charset nào đã được dùng.

### 2.1. JDK không tự mở và chuyển đổi toàn bộ file

Giả sử file `customers.txt` đã được ghi theo Windows-1258. Sau khi cài JDK 18 hoặc JDK mới hơn:

- Các byte trong `customers.txt` vẫn giữ nguyên.
- JDK không quét thư mục để chuyển đổi file.
- Tên file và nội dung file không tự nhận metadata UTF-8.
- Một API đọc dùng default charset có thể giải mã byte theo UTF-8 và cho kết quả khác trước.
- Một API có hợp đồng UTF-8 cố định vẫn đọc theo UTF-8, bất kể default charset của JVM.

Việc cài JDK mới không phải thao tác migration dữ liệu. Nếu file cần chuyển đổi, ứng dụng hoặc công cụ migration phải thực hiện một quy trình đọc và ghi riêng.

### 2.2. Ví dụ phân biệt byte trước và sau khi nâng cấp

Giả sử file cũ chứa ký tự `à` theo ISO-8859-1. Byte trên đĩa là `E0`. Nâng cấp JDK không thay byte đó:

```text
Trước nâng cấp: E0
Sau nâng cấp:   E0
```

Nhưng cách giải mã có thể thay đổi:

| Cách giải mã | Byte đầu vào | Kết quả |
| --- | --- | --- |
| ISO-8859-1 | `E0` | `à` |
| UTF-8 | `E0` | Byte UTF-8 không hợp lệ nếu đứng riêng; decoder nghiêm ngặt báo lỗi |

Do đó, cần phân biệt **nội dung byte** và **cách chương trình diễn giải nội dung byte**. Khi một file cũ bỗng hiển thị sai sau khi nâng cấp JDK, hãy kiểm tra charset nguồn trước khi kết luận file đã bị thay đổi.

## 3. JEP 400 ảnh hưởng API nào?

Không phải mọi API đọc/ghi văn bản đều sử dụng default charset. Cần xem đúng overload đang gọi.

### 3.1. API phụ thuộc default charset

Các ví dụ sau dùng default charset khi không truyền charset:

| API | Chuyển đổi | Hành vi |
| --- | --- | --- |
| `new String(byte[])` | Byte → String | Giải mã bằng default charset |
| `String.getBytes()` | String → byte[] | Mã hóa bằng default charset |
| `new InputStreamReader(inputStream)` | Byte → ký tự | Dùng default charset |
| `new OutputStreamWriter(outputStream)` | Ký tự → byte | Dùng default charset |
| `new FileReader(file)` | File byte → ký tự | Constructor không charset dùng default charset |
| `new FileWriter(file)` | Ký tự → file byte | Constructor không charset dùng default charset |

Trên JDK 18+ thông thường, các overload này dùng UTF-8. Trước JDK 18, default charset có thể phụ thuộc môi trường. Đây là một nguồn thay đổi hành vi khi nâng cấp ứng dụng.

Ví dụ:

```java
byte[] bytes = Files.readAllBytes(Path.of("legacy.txt"));

// Dùng default charset của JVM hiện tại.
String text = new String(bytes);
```

Nếu file là Windows-1258 nhưng JVM hiện tại dùng UTF-8, chuỗi tạo ra có thể sai. Dùng default charset không phải cách xác định charset của file; nó chỉ chọn một quy tắc giải mã từ cấu hình JVM.

### 3.2. API UTF-8 cố định theo hợp đồng

Một số API Java đã quy định UTF-8 cố định, kể cả trước JEP 400:

- `Files.readString(path)`.
- `Files.writeString(path, text)`.
- `Files.newBufferedReader(path)`.
- `Files.newBufferedWriter(path, options...)`.
- `Files.readAllLines(path)`.

Ví dụ:

```java
Path file = Path.of("data.txt");

// Overload này đọc theo UTF-8 theo hợp đồng API.
String text = Files.readString(file);

// Overload này ghi theo UTF-8 theo hợp đồng API.
Files.writeString(file, text);
```

Nếu file thực tế là Windows-1258, `Files.readString(path)` không tự nhận ra và chuyển từ Windows-1258 sang UTF-8. Nó đọc byte theo UTF-8; nội dung có thể sai hoặc thao tác có thể báo lỗi nếu chuỗi byte không hợp lệ theo hợp đồng decoder.

Muốn đọc file legacy bằng charset nguồn, truyền charset tường minh:

```java
String legacyText = Files.readString(
        Path.of("legacy.txt"),
        Charset.forName("windows-1258"));
```

Tên charset ví dụ cần được runtime hỗ trợ. Với charset chuẩn Java bảo đảm hỗ trợ, ưu tiên các hằng trong `StandardCharsets`.

### 3.3. API xử lý ký tự không tự chuyển đổi byte

`String`, `StringBuilder`, `BufferedReader` nhận `Reader` và `BufferedWriter` nhận `Writer` làm việc với ký tự. Charset được quyết định tại điểm chuyển đổi byte–ký tự trước hoặc sau chúng.

Ví dụ:

- `StringBuilder.append(text)` nối ký tự; không chọn charset.
- `BufferedReader(reader)` đọc từ một reader đã quyết định cách giải mã.
- `BufferedWriter(writer)` ghi vào một writer đã quyết định cách mã hóa.

Khi điều tra lỗi encoding, hãy lần theo nơi byte đi vào và nơi byte đi ra, thay vì cho rằng mọi lớp xử lý chuỗi đều cần cấu hình charset.

## 4. Vì sao đổi `file.encoding` không chuyển đổi file?

`file.encoding` liên quan đến default charset của JDK. Từ JDK 18, hai giá trị cấu hình được hỗ trợ khi khởi động là `UTF-8` và `COMPAT`:

- `UTF-8`: chọn UTF-8 làm default charset.
- `COMPAT`: chọn default charset theo cách JDK 17 và các phiên bản trước đó đã xác định từ môi trường.

Ví dụ:

```bash
java -Dfile.encoding=UTF-8 -jar app.jar
java -Dfile.encoding=COMPAT -jar app.jar
```

Hai cấu hình này ảnh hưởng đến lựa chọn default charset của JVM. Chúng không chuyển đổi byte của file đã lưu. `COMPAT` có thể giúp tái hiện hành vi cũ trong quá trình điều tra, nhưng không nên dùng như một thay thế lâu dài cho hợp đồng charset rõ ràng của file và giao thức.

Cũng không thể đổi charset mặc định đang chạy bằng cách gọi:

```java
System.setProperty("file.encoding", "windows-1258");
```

Thay đổi property map sau khi JVM khởi động không phải cơ chế được hỗ trợ để cấu hình lại default charset. Dù `System.getProperty("file.encoding")` có thể hiển thị giá trị vừa gán, các API vẫn có thể tiếp tục dùng default charset đã được chọn lúc khởi động.

### 4.1. Bảng phân biệt ba thao tác

| Thao tác | Điều thực sự xảy ra | Byte file cũ có đổi không? |
| --- | --- | --- |
| Nâng cấp JDK lên 18+ | Default charset thông thường chuyển sang UTF-8 | Không |
| Khởi chạy với `-Dfile.encoding=COMPAT` | Chọn default charset tương thích môi trường cũ | Không |
| Đọc file bằng charset nguồn rồi ghi lại bằng UTF-8 | Giải mã và mã hóa lại nội dung file | Có, ở file đích được ghi |

Chỉ thao tác cuối là chuyển đổi dữ liệu. Cần thực hiện có kiểm soát và kiểm chứng kết quả.

## 5. Xác định charset nguồn trước khi chuyển đổi

Trước khi chuyển file sang UTF-8, phải xác định byte hiện tại được tạo bằng charset nào. Không thể mặc định mọi file cũ trên một máy đều dùng cùng charset.

Nguồn thông tin đáng tin cậy có thể là:

- Đặc tả định dạng file hoặc tài liệu tích hợp.
- Cấu hình của chương trình đã tạo file.
- Metadata của giao thức, ví dụ HTTP `Content-Type` khi giao thức cho phép khai báo charset.
- Hệ thống xuất dữ liệu hoặc database đã ghi file.
- Mẫu byte đã biết và đối chiếu với dữ liệu thực tế.
- BOM, nếu định dạng và quy trình tạo file có quy định sử dụng BOM.

### 5.1. Không có cách nhận diện charset hoàn hảo cho mọi file

Nhiều charset có vùng byte trùng nhau. Ví dụ, ASCII biểu diễn giống nhau trong UTF-8 và nhiều charset đơn byte. Một file chỉ chứa chữ cái tiếng Anh có thể không cung cấp đủ thông tin để phân biệt encoding.

Một số byte có thể hợp lệ trong nhiều charset nhưng tạo ra văn bản khác nhau. Vì vậy, công cụ dò encoding chỉ đưa ra dự đoán, không thay thế được hợp đồng dữ liệu.

Không nên tự động chuyển đổi hàng loạt file chỉ dựa trên một kết quả đoán charset. Với dữ liệu quan trọng, cần xác nhận nguồn tạo file hoặc yêu cầu người sở hữu dữ liệu xác nhận định dạng.

### 5.2. BOM chỉ là một dấu hiệu, không phải giải pháp phổ quát

BOM có thể giúp nhận diện một số encoding Unicode:

| BOM byte | Dạng thường gặp |
| --- | --- |
| `EF BB BF` | UTF-8 BOM |
| `FE FF` | UTF-16 big-endian |
| `FF FE` | UTF-16 little-endian |

UTF-8 không bắt buộc phải có BOM. Nhiều file UTF-8 hợp lệ bắt đầu trực tiếp bằng nội dung, không có ba byte `EF BB BF`.

BOM cũng không nhận diện được các charset legacy như Windows-1258 hoặc Windows-1252. Nếu file không có BOM, không thể kết luận nó là UTF-8 hay một charset đơn byte chỉ từ việc không thấy BOM.

Khi chuyển đổi, cần quyết định BOM của file đích theo hợp đồng. `StandardCharsets.UTF_8` không tự thêm BOM khi mã hóa một chuỗi thông thường.

## 6. Quy trình chuyển một file legacy sang UTF-8

Một quy trình chuyển đổi đúng có các bước:

1. **Giữ nguyên file nguồn:** tạo bản sao hoặc bảo đảm có thể khôi phục.
2. **Xác định charset nguồn:** dựa trên hợp đồng, metadata hoặc thông tin từ hệ thống tạo file.
3. **Đọc byte:** không giải mã bằng default charset nếu chưa xác nhận nó trùng charset nguồn.
4. **Giải mã theo charset nguồn:** chuyển byte thành `String`.
5. **Kiểm tra nội dung:** kiểm tra tiếng Việt, ký tự đặc biệt, số bản ghi, delimiter và dữ liệu nghiệp vụ.
6. **Mã hóa UTF-8:** chuyển chuỗi thành byte UTF-8.
7. **Ghi file đích riêng:** không ghi đè nguồn ngay trong lần thử đầu.
8. **Kiểm tra byte và round-trip:** đọc lại file đích bằng UTF-8 và so sánh nội dung.
9. **Chuyển sang dùng file mới:** chỉ sau khi xác nhận kết quả và có kế hoạch rollback.

Quy trình này không chỉ dành cho file. Khi chuyển payload message queue, dữ liệu import/export hoặc nội dung trao đổi giữa hai dịch vụ, cũng cần thống nhất charset nguồn và đích.

## 7. Ví dụ Java: chuyển file từ charset nguồn sang UTF-8

Ví dụ dưới đây đọc file theo Windows-1258 và ghi file mới theo UTF-8. Chỉ dùng charset này khi đã xác nhận file nguồn thực sự được tạo theo Windows-1258 và runtime hỗ trợ charset đó.

Để tránh thay thế âm thầm dữ liệu lỗi, ví dụ cấu hình decoder và encoder với `CodingErrorAction.REPORT`. Nó đọc toàn bộ file vào bộ nhớ nên phù hợp với file nhỏ hoặc vừa; file lớn nên dùng luồng xử lý ở phần tiếp theo.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ConvertLegacyFile {
    public static void main(String[] args) throws Exception {
        Path source = Path.of("legacy.txt");
        Path target = Path.of("legacy-utf8.txt");

        // Chỉ chọn charset này khi hợp đồng file xác nhận Windows-1258.
        Charset sourceCharset = Charset.forName("windows-1258");

        byte[] sourceBytes = Files.readAllBytes(source);

        var decoder = sourceCharset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        String text = decoder.decode(
                ByteBuffer.wrap(sourceBytes)).toString();

        var encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer encoded = encoder.encode(CharBuffer.wrap(text));
        byte[] utf8Bytes = new byte[encoded.remaining()];
        encoded.get(utf8Bytes);

        // Ghi sang file đích riêng; file nguồn vẫn được giữ nguyên.
        Files.write(target, utf8Bytes);

        String verified = Files.readString(
                target, StandardCharsets.UTF_8);

        if (!text.equals(verified)) {
            throw new IllegalStateException(
                    "Nội dung sau chuyển đổi không khớp");
        }

        System.out.println("Đã chuyển đổi: " + target);
    }
}
```

Trong ví dụ:

- `sourceCharset` là charset nguồn, phải lấy từ hợp đồng file.
- `CharsetDecoder` chuyển byte thành ký tự.
- `CodingErrorAction.REPORT` khiến dữ liệu byte sai hoặc không ánh xạ được báo lỗi thay vì thay thế âm thầm.
- `CharsetEncoder` tạo byte UTF-8.
- File đích có tên khác nên file nguồn được giữ nguyên.
- Bước đọc lại kiểm tra nội dung sau khi chuyển đổi.

Nếu runtime không hỗ trợ Windows-1258, `Charset.forName` sẽ báo `UnsupportedCharsetException`. Khi đó, cần chọn một runtime có charset tương ứng hoặc dùng thư viện chuyển đổi phù hợp; không đổi sang charset gần giống rồi tiếp tục mà không xác nhận.

### 7.1. Ví dụ đơn giản với charset chuẩn được Java bảo đảm

Nếu nguồn là ISO-8859-1 theo hợp đồng, có thể dùng hằng chuẩn:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("latin1.txt");
Path target = Path.of("utf8.txt");

String text = Files.readString(
        source, StandardCharsets.ISO_8859_1);

Files.writeString(
        target, text, StandardCharsets.UTF_8);
```

Đây là ví dụ đơn giản cho file nhỏ. `Files.readString(path, charset)` đọc theo charset đã chỉ định; `Files.writeString(path, text, charset)` ghi theo charset đích. Nếu cần từ chối byte sai nghiêm ngặt, hãy dùng decoder với `CodingErrorAction.REPORT` như ví dụ trước.

## 8. Chuyển đổi file lớn bằng Reader và Writer

Với file lớn, tránh `Files.readAllBytes()` và giữ toàn bộ nội dung trong một `String`. Có thể dùng `InputStreamReader` với decoder nguồn và `OutputStreamWriter` với encoder UTF-8 để xử lý theo buffer.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path source = Path.of("large-legacy.txt");
Path target = Path.of("large-utf8.txt");

Charset sourceCharset = Charset.forName("windows-1258");

var decoder = sourceCharset.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

var encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var reader = new BufferedReader(
         new InputStreamReader(Files.newInputStream(source), decoder));
     var writer = new BufferedWriter(
         new OutputStreamWriter(
             Files.newOutputStream(target,
                 StandardOpenOption.CREATE,
                 StandardOpenOption.TRUNCATE_EXISTING,
                 StandardOpenOption.WRITE),
             encoder))) {

    char[] buffer = new char[8192];
    int count;

    while ((count = reader.read(buffer)) != -1) {
        writer.write(buffer, 0, count);
    }
}
```

Ví dụ này ghi ra một file đích riêng. Trong quy trình production, nên ghi vào file tạm trên cùng filesystem, flush/close thành công, kiểm tra nội dung và sau đó thay thế đích bằng thao tác move phù hợp. Không ghi đè file nguồn khi chưa có bản sao hoặc phương án rollback.

Nếu decoder gặp byte sai theo charset nguồn, thao tác đọc sẽ báo lỗi theo chế độ `REPORT`. Khi đó, dừng migration và điều tra dữ liệu; không bỏ qua lỗi rồi tiếp tục tạo file UTF-8 thiếu nội dung.

## 9. Những điều chuyển đổi charset không tự giải quyết

### 9.1. Không sửa nội dung đã bị mojibake trước đó

Giả sử byte UTF-8 bị giải mã nhầm thành Windows-1252, sau đó chuỗi sai được ghi lại thành UTF-8. Chuyển đổi charset lần nữa không tự khôi phục văn bản gốc. Để khôi phục, phải có byte nguồn ban đầu hoặc xác định chính xác chuỗi đã bị diễn giải sai theo chuỗi bước nào.

Không chuyển đổi lặp đi lặp lại giữa UTF-8 và charset legacy để thử vận may. Hãy giữ bản gốc và kiểm tra byte cùng nội dung ở từng bước.

### 9.2. Không tự chuẩn hóa Unicode

UTF-8 mã hóa các code point; nó không tự chuẩn hóa chuỗi về NFC hoặc NFD. Hai chuỗi có thể hiển thị giống nhau nhưng có biểu diễn Unicode khác nhau.

Nếu hệ thống cần chuẩn hóa, thực hiện riêng bằng `java.text.Normalizer` theo hợp đồng ứng dụng. Không gộp normalization vào migration charset nếu chưa xác định tác động tới khóa, chữ ký, so sánh và dữ liệu định danh.

### 9.3. Không tự thay BOM hoặc newline

Chuyển charset không đồng nghĩa thay đổi:

- Có hay không có BOM.
- LF hay CRLF.
- Delimiter CSV.
- Quy tắc quote/escape.
- Cách phân chia record.
- Whitespace và ký tự điều khiển.

Một quy trình đọc theo dòng rồi ghi lại có thể thay đổi newline nếu dùng `BufferedWriter.newLine()`. Nếu yêu cầu bảo toàn chính xác nội dung, phải xác định rõ newline và xử lý theo định dạng.

### 9.4. Không chuyển đổi database hoặc giao thức chỉ bằng JEP 400

Database có encoding, collation và quy tắc chuyển đổi riêng. JDBC driver trao đổi dữ liệu theo giao thức của database; `file.encoding` của JVM không tự chuyển đổi byte đã lưu trong database.

HTTP, JSON, message queue và file trao đổi cũng có hợp đồng riêng. Nếu giao thức quy định UTF-8, dùng UTF-8 ở đúng ranh giới; nếu hệ thống cũ quy định charset khác, tuân theo hợp đồng đó cho đến khi cả hai phía phối hợp migration.

## 10. Kiểm chứng byte sau khi chuyển đổi

Không chỉ kiểm tra rằng file mở được trong editor. Hãy xác nhận byte đầu ra đúng theo một mẫu đã biết.

Ví dụ, chuỗi `Cà` được mã hóa UTF-8 thành:

```text
43 C3 A0
```

Java có thể kiểm tra bằng `HexFormat`:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

byte[] bytes = "Cà".getBytes(StandardCharsets.UTF_8);

String hex = HexFormat.of()
        .withUpperCase()
        .formatHex(bytes);

if (!"43C3A0".equals(hex)) {
    throw new AssertionError("Byte UTF-8 không đúng: " + hex);
}

System.out.println(hex);
```

Với file đã chuyển đổi, có thể đọc byte và hiển thị hex:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

byte[] bytes = Files.readAllBytes(Path.of("legacy-utf8.txt"));

System.out.println(HexFormat.of()
        .withUpperCase()
        .formatHex(bytes));
```

Một bộ kiểm tra thực tế nên bao gồm:

| Dữ liệu | Điều cần xác nhận |
| --- | --- |
| ASCII | Các byte cơ bản được bảo toàn |
| Tiếng Việt có dấu | Các ký tự nhiều byte UTF-8 được mã hóa đúng |
| Emoji/ký tự ngoài BMP | Code point được bảo toàn |
| Dấu tổ hợp | Không bị normalization ngoài ý muốn |
| Byte lỗi theo charset nguồn | Migration dừng hoặc xử lý theo chính sách đã định |
| BOM | Đúng quy định của định dạng file |
| Newline | Đúng LF/CRLF theo hợp đồng |
| File lớn | Không thiếu record hoặc dừng giữa chừng |

Kiểm tra byte và kiểm tra nội dung sau giải mã là hai bước khác nhau. Round-trip một chuỗi có thể vẫn thành công nếu cả hai lần đều dùng cùng một charset sai; vì vậy cần so sánh với byte hoặc nội dung kỳ vọng độc lập.

## 11. Quy trình rà soát ứng dụng sau khi nâng cấp JDK

Khi chuyển ứng dụng từ JDK 17 hoặc cũ hơn lên JDK 18+, hãy tìm những nơi đang dựa vào default charset:

- `new String(byte[])`.
- `String.getBytes()`.
- `new FileReader(file)`.
- `new FileWriter(file)`.
- `new InputStreamReader(stream)`.
- `new OutputStreamWriter(stream)`.
- Constructor `Scanner` hoặc `Formatter` nhận nguồn/đích byte mà không truyền charset.

Với từng vị trí, xác định:

1. Byte đến từ đâu hoặc sẽ được gửi tới đâu?
2. Hợp đồng dữ liệu quy định charset nào?
3. Overload hiện tại dùng default charset hay charset cố định?
4. Dữ liệu hiện có được tạo bởi phiên bản ứng dụng nào?
5. Có cần migration byte trên đĩa hay chỉ cần sửa cách đọc/ghi trong ứng dụng?
6. Cần giữ lại bản gốc và rollback như thế nào?

Không thay máy móc tất cả lời gọi bằng UTF-8 nếu dữ liệu nguồn thực tế là charset khác. Nếu hợp đồng quy định UTF-8, hãy dùng `StandardCharsets.UTF_8` tường minh. Nếu dữ liệu legacy, hãy giải mã bằng charset nguồn đã xác nhận rồi mới mã hóa lại.

### Các lỗi cần tránh

| Suy luận sai | Thực tế |
| --- | --- |
| Nâng cấp lên JDK 18 tự đổi file cũ sang UTF-8 | Byte file không tự thay đổi |
| `file.encoding=UTF-8` chuyển đổi mọi dữ liệu trên đĩa | Property chỉ ảnh hưởng lựa chọn default charset của JVM |
| File không có BOM chắc chắn là UTF-8 | Nhiều charset khác không dùng BOM |
| Công cụ dò encoding luôn xác định chính xác | Nhiều charset có vùng byte trùng nhau; kết quả dò chỉ là dự đoán |
| Chỉ cần đọc bằng UTF-8 rồi ghi lại là migration đúng | Cần biết charset nguồn thật sự trước khi giải mã |
| `Files.readString(path)` tự nhận diện charset cũ | Overload này dùng UTF-8 theo hợp đồng API |
| Round-trip thành công chứng minh charset nguồn đúng | Cần kiểm tra byte và dữ liệu kỳ vọng độc lập |
| Chuyển charset cũng chuẩn hóa Unicode và newline | Đây là các quy tắc riêng |

## 12. Bài tập tự kiểm tra

**Bài 1.** Một file được tạo bằng Windows-1258 trước khi nâng cấp JDK. Sau khi cài JDK 18, byte của file có tự chuyển thành UTF-8 không?

*Đáp án:* Không. JDK không tự thay đổi byte đã lưu. Chỉ cách các API phụ thuộc default charset giải mã hoặc mã hóa dữ liệu mới có thể thay đổi.

**Bài 2.** Vì sao `new String(bytes)` có thể đọc sai file legacy sau khi nâng cấp lên JDK 18?

*Đáp án:* Constructor này dùng default charset. Từ JDK 18, default charset thông thường là UTF-8, trong khi byte file cũ có thể được tạo bằng Windows-1258 hoặc charset khác.

**Bài 3.** `Files.readString(path)` có tự nhận diện Windows-1258 nếu file được tạo bằng Windows-1258 không?

*Đáp án:* Không. Overload không truyền charset dùng UTF-8 theo hợp đồng API. Muốn đọc file legacy, truyền charset nguồn đã xác nhận vào overload nhận `Charset`.

**Bài 4.** Có thể xác định charset của mọi file chỉ bằng cách kiểm tra BOM không?

*Đáp án:* Không. UTF-8 không bắt buộc BOM và nhiều charset legacy không có BOM. BOM chỉ là dấu hiệu cho một số encoding Unicode theo quy ước định dạng.

**Bài 5.** Quy trình đúng để chuyển file legacy sang UTF-8 gồm những bước nào?

*Đáp án:* Giữ bản gốc, xác định charset nguồn, đọc byte và giải mã bằng charset đó, kiểm tra nội dung, mã hóa bằng UTF-8, ghi file đích riêng và xác nhận byte cùng nội dung sau khi đọc lại.

**Bài 6.** Vì sao không nên chạy chuyển đổi hàng loạt chỉ dựa trên kết quả đoán encoding?

*Đáp án:* Nhiều charset có byte hợp lệ trùng nhau nhưng diễn giải thành ký tự khác. Kết quả đoán có thể sai; chuyển đổi hàng loạt sẽ làm hỏng dữ liệu nếu dùng sai charset nguồn.

## 13. Ghi nhớ

UTF-8 mặc định từ JDK 18 là thay đổi trong lựa chọn charset của JVM cho các API phụ thuộc default charset. Nó không sửa byte của file đã lưu, không chuyển đổi database và không thay đổi hợp đồng của HTTP, message queue hay các định dạng legacy.

Để chuyển dữ liệu sang UTF-8, phải xác định charset nguồn, giải mã byte bằng charset đó, kiểm tra văn bản, mã hóa lại bằng UTF-8 và ghi ra đích có thể kiểm chứng. Hãy giữ bản gốc, dùng decoder/encoder nghiêm ngặt khi cần toàn vẹn dữ liệu và kiểm tra byte thực tế. Đây là cách nâng cấp an toàn mà không làm mất dữ liệu tiếng Việt hoặc nội dung lịch sử.

### Tài liệu tham khảo chính thức

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle Java SE 27 — Supported Encodings and Default Charset](https://docs.oracle.com/en/java/javase/27/intl/supported-encodings.html).
- [Oracle Java SE 27 — Charset](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html).
- [Oracle Java SE 27 — CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Oracle Java SE 27 — CharsetEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetEncoder.html).
- [Oracle Java SE 27 — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html).
