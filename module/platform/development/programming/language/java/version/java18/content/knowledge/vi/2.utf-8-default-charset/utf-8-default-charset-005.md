# `StandardCharsets.UTF_8` và lý do khai báo charset rõ ràng trong hợp đồng dữ liệu

## 1. Vì sao nên khai báo charset rõ ràng?

Một chương trình Java có thể chạy trên nhiều hệ điều hành, container, máy CI và máy chủ. Nếu cùng một dữ liệu văn bản được ghi hoặc đọc bằng charset mặc định của JVM, hành vi có thể phụ thuộc cấu hình khởi động hoặc môi trường tương thích.

Từ JDK 18, **JEP 400** đặt UTF-8 làm charset mặc định trong cấu hình thông thường. Điều này cải thiện tính nhất quán, nhưng một hợp đồng dữ liệu vẫn cần nói rõ byte được diễn giải theo charset nào. Một file do ứng dụng cũ tạo ra có thể vẫn là Windows-1258; một giao thức có thể quy định UTF-8; một hệ thống tích hợp có thể yêu cầu ISO-8859-1. Charset của máy chạy không thể thay thế đặc tả của dữ liệu.

Trong Java, cách thể hiện phổ biến và an toàn cho dữ liệu UTF-8 là:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
```

`StandardCharsets.UTF_8` là hằng charset chuẩn của Java. Nó giúp người đọc thấy ngay quy tắc mã hóa/giải mã và tránh phụ thuộc vào `Charset.defaultCharset()`.

Bài học này thuộc chương **UTF-8 mặc định** của `JAVA_VERSION_JAVA18`. Trọng tâm là dùng charset tường minh theo hợp đồng dữ liệu, hiểu các giới hạn của charset, và kiểm chứng byte thực tế trên JDK hiện đại.

## 2. `StandardCharsets` cung cấp những gì?

`java.nio.charset.StandardCharsets` là lớp tiện ích chứa các hằng `Charset` được Java SE bảo đảm hỗ trợ. Những hằng này có sẵn từ Java 7 và tiếp tục là API hiện hành.

| Hằng | Tên charset chuẩn | Công dụng thường gặp |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | `UTF-8` | Trao đổi văn bản Unicode; lựa chọn phổ biến cho file và giao thức hiện đại. |
| `StandardCharsets.UTF_16` | `UTF-16` | Chỉ dùng khi định dạng hoặc giao thức quy định UTF-16. |
| `StandardCharsets.UTF_16BE` | `UTF-16BE` | UTF-16 theo thứ tự byte big-endian. |
| `StandardCharsets.UTF_16LE` | `UTF-16LE` | UTF-16 theo thứ tự byte little-endian. |
| `StandardCharsets.US_ASCII` | `US-ASCII` | Giao thức hoặc dữ liệu giới hạn trong ASCII. |
| `StandardCharsets.ISO_8859_1` | `ISO-8859-1` | Tương thích định dạng cũ có quy định charset này. |

Các hằng trên là đối tượng `Charset` có thể truyền trực tiếp cho API. Không cần dò charset bằng tên chuỗi mỗi lần sử dụng:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset charset = StandardCharsets.UTF_8;
System.out.println(charset.name()); // UTF-8
```

Khi charset đến từ cấu hình bên ngoài, `Charset.forName(name)` có thể hữu ích, nhưng tên không hợp lệ hoặc charset không được hỗ trợ có thể gây `IllegalCharsetNameException` hoặc `UnsupportedCharsetException`. Với charset chuẩn đã biết lúc viết code, dùng `StandardCharsets` giúp tránh lỗi chính tả và đảm bảo charset được Java SE hỗ trợ.

`Charset.availableCharsets()` liệt kê các charset mà runtime hiện tại hỗ trợ; danh sách đó có thể bao gồm nhiều charset bổ sung ngoài các hằng chuẩn. Không nên dựa vào một charset mở rộng nếu ứng dụng cần chạy portable mà chưa xác nhận mọi môi trường đều có nó.

## 3. `UTF_8` khác gì `Charset.defaultCharset()`?

Hai biểu thức có ý nghĩa khác nhau:

- `StandardCharsets.UTF_8` luôn tham chiếu charset UTF-8 theo hợp đồng Java SE.
- `Charset.defaultCharset()` trả về charset mặc định của JVM đang chạy.

Từ Java 18, default charset thông thường là UTF-8 theo JEP 400. Tuy nhiên, tùy chọn `-Dfile.encoding=COMPAT` vẫn có thể yêu cầu hành vi tương thích với môi trường trước JDK 18. Khi đó, default charset có thể khác UTF-8.

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

System.out.println("default = " + Charset.defaultCharset().name());
System.out.println("explicit = " + StandardCharsets.UTF_8.name());

byte[] explicit = "cà phê".getBytes(StandardCharsets.UTF_8);
byte[] implicit = "cà phê".getBytes();
```

Trong cấu hình JDK 18+ thông thường, hai mảng byte thường giống nhau. Nhưng chúng không có cùng hợp đồng:

- `explicit` luôn được mã hóa bằng UTF-8.
- `implicit` dùng default charset hiện tại của JVM.

Nếu định dạng dữ liệu yêu cầu UTF-8, chọn `StandardCharsets.UTF_8` ngay cả khi hiện tại `Charset.defaultCharset()` đã trả về UTF-8. Điều đó giúp ứng dụng giữ đúng hợp đồng khi thay đổi môi trường hoặc cấu hình tương thích.

## 4. Charset là một phần của hợp đồng dữ liệu

Một hợp đồng dữ liệu cần mô tả cách hai bên hiểu cùng một dãy byte. Với dữ liệu văn bản, tối thiểu cần xác định:

1. **Charset:** ví dụ UTF-8, UTF-16LE hoặc một charset legacy được quy định.
2. **Cách đóng khung dữ liệu:** ranh giới bản ghi, delimiter, độ dài byte, newline hoặc framing của giao thức.
3. **Quy tắc văn bản:** Unicode normalization có bắt buộc không; có chấp nhận BOM không; có cho phép ký tự điều khiển không.
4. **Chính sách lỗi:** từ chối byte sai, thay thế ký tự lỗi hay cách ly bản ghi.
5. **Giới hạn kích thước:** tính theo byte đã mã hóa, code point hay grapheme cluster.

Charset chỉ giải quyết ánh xạ giữa byte và ký tự. Nó **không tự quy định** dấu xuống dòng, delimiter CSV, chuẩn hóa Unicode, BOM hoặc giới hạn ký tự theo giao diện người dùng.

### 4.1. Ví dụ hợp đồng file UTF-8

Giả sử hai ứng dụng trao đổi file `customers.csv`. Hợp đồng có thể quy định:

| Thuộc tính | Quy định ví dụ |
| --- | --- |
| Encoding | UTF-8 |
| BOM | Không có BOM ở đầu file |
| Dòng | Một khách hàng mỗi dòng, kết thúc bằng LF |
| Header | Có dòng tiêu đề |
| Dấu phân cách | Dấu phẩy; trường chứa dấu phẩy hoặc dấu nháy được quote theo quy tắc CSV |
| Unicode normalization | Không yêu cầu chuẩn hóa khi truyền; dữ liệu được bảo toàn như nhận |
| Byte lỗi | Từ chối file nếu không phải UTF-8 hợp lệ |
| Giới hạn | Tối đa 10 MiB theo số byte của file |

Những quy định này làm cho hai bên triển khai độc lập mà vẫn có cách hiểu thống nhất. Nếu chỉ ghi “file là text”, bên nhận không biết phải giải mã thế nào, xử lý BOM ra sao hoặc đo giới hạn kích thước theo đơn vị nào.

### 4.2. Hợp đồng giao thức có thể yêu cầu charset khác

UTF-8 là lựa chọn mặc định tốt cho nhiều hệ thống mới, nhưng không phải lý do để bỏ qua đặc tả hiện hữu. Nếu thiết bị hoặc giao thức cũ yêu cầu `windows-1258`, `ISO-8859-1` hay `UTF-16LE`, ứng dụng phải tuân theo charset đó ở đúng ranh giới tích hợp.

Không chuyển một giao thức sang UTF-8 đơn phương nếu bên kia chưa đồng ý. Thay đổi charset có thể làm byte thay đổi, phá vỡ chữ ký, checksum, parser hoặc dữ liệu đã lưu.

## 5. Khai báo UTF-8 rõ ràng khi đọc và ghi file

`Files` cung cấp API hiện đại để đọc/ghi văn bản. Các overload không nhận charset của `Files.readString` và `Files.writeString` đã dùng UTF-8 theo hợp đồng API từ Java 11; không phải chờ JEP 400 mới có hành vi này.

Dù vậy, overload nhận `StandardCharsets.UTF_8` thể hiện ý định rõ hơn:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("greeting.txt");
String original = "Xin chào Việt Nam 🇻🇳";

Files.writeString(file, original, StandardCharsets.UTF_8);

String restored = Files.readString(file, StandardCharsets.UTF_8);
if (!original.equals(restored)) {
    throw new IllegalStateException("Nội dung đọc lại không khớp");
}
```

Với file lớn, có thể xử lý theo luồng bằng reader/writer:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("input.txt");
Path output = Path.of("output.txt");

try (var reader = Files.newBufferedReader(input, StandardCharsets.UTF_8);
     var writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

Ví dụ này xử lý nội dung theo dòng, nên có thể thay đổi cách biểu diễn dấu xuống dòng của file. Nếu yêu cầu là sao chép byte nguyên vẹn, hãy dùng API byte như `Files.copy(input, output)` thay vì decode rồi encode lại.

## 6. Khai báo charset rõ ràng khi chuyển đổi byte

### 6.1. Mã hóa và giải mã phải cùng charset

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String message = "Cà phê";
byte[] payload = message.getBytes(StandardCharsets.UTF_8);

System.out.println(HexFormat.of().withUpperCase().formatHex(payload));
// 43C3A0207068C3AA

String decoded = new String(payload, StandardCharsets.UTF_8);
System.out.println(message.equals(decoded)); // true
```

Nếu dùng một charset khác để giải mã payload UTF-8, kết quả có thể sai dù chương trình không báo lỗi. Đối với dữ liệu từ đối tác, charset cần được xác định bởi tài liệu giao thức hoặc metadata đáng tin cậy, không được đoán từ default charset của máy.

### 6.2. Dữ liệu legacy phải giải mã theo charset gốc

Giả sử file cũ được tạo theo ISO-8859-1. Đổi JDK lên 18 không chuyển byte trong file thành UTF-8. Cần đọc theo charset nguồn rồi ghi lại theo charset đích:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path legacy = Path.of("legacy.txt");
Path modern = Path.of("modern-utf8.txt");

// Chỉ dùng ISO-8859-1 nếu hợp đồng của file cũ quy định như vậy.
String text = Files.readString(legacy, StandardCharsets.ISO_8859_1);

// File mới được quy định UTF-8.
Files.writeString(modern, text, StandardCharsets.UTF_8);
```

Quy trình chuyển đổi cần kiểm tra dữ liệu đầu vào, số bản ghi, nội dung sau đọc lại và byte đầu ra. Không thể phục hồi văn bản gốc nếu dữ liệu đã bị giải mã sai và lưu đè trước đó.

## 7. Xử lý byte sai: thay thế hay từ chối?

Một chi tiết quan trọng: `new String(bytes, StandardCharsets.UTF_8)` thay thế chuỗi byte lỗi hoặc không ánh xạ được bằng ký tự thay thế theo hợp đồng của constructor. Điều đó tiện cho một số tình huống hiển thị, nhưng không thích hợp nếu hệ thống phải từ chối dữ liệu không hợp lệ.

Dùng `CharsetDecoder` với `CodingErrorAction.REPORT` để phát hiện byte lỗi:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

byte[] received = {(byte) 0xC3, (byte) 0x28};

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    String value = decoder.decode(ByteBuffer.wrap(received)).toString();
    System.out.println(value);
} catch (CharacterCodingException e) {
    System.out.println("Từ chối payload UTF-8 không hợp lệ");
}
```

`C3 28` không phải một chuỗi UTF-8 hợp lệ: byte `C3` bắt đầu một ký tự nhiều byte nhưng byte `28` không phải byte tiếp diễn hợp lệ. Decoder nghiêm ngặt giúp hệ thống phát hiện lỗi thay vì âm thầm thay thế.

### 7.1. Encoder cũng có thể cần chế độ nghiêm ngặt

UTF-8 có thể biểu diễn mọi Unicode scalar value, nhưng `String` Java có thể chứa surrogate đơn lẻ không ghép cặp. Nếu ứng dụng nhận chuỗi không hợp lệ như vậy, một encoder có chế độ thay thế có thể không đáp ứng yêu cầu toàn vẹn dữ liệu.

```java
import java.nio.CharBuffer;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

String text = "Tên: " + '\uD800'; // High surrogate đơn lẻ

var encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    ByteBuffer encoded = encoder.encode(CharBuffer.wrap(text));
    byte[] bytes = new byte[encoded.remaining()];
    encoded.get(bytes);
} catch (CharacterCodingException e) {
    System.out.println("Không mã hóa: String chứa UTF-16 lỗi");
}
```

Nếu hợp đồng yêu cầu dữ liệu Unicode hợp lệ, việc báo lỗi sớm thường tốt hơn thay thế âm thầm bằng ký tự khác. Chính sách cụ thể cần phù hợp với ứng dụng: dữ liệu hiển thị có thể chấp nhận thay thế, trong khi dữ liệu định danh, chữ ký hoặc trao đổi nghiệp vụ có thể phải từ chối.

## 8. Charset không quy định BOM và Unicode normalization

Hai khái niệm này thường bị nhầm với encoding.

### 8.1. BOM trong UTF-8

UTF-8 không cần BOM để xác định thứ tự byte. Một số công cụ vẫn ghi ba byte `EF BB BF` ở đầu file như một dấu hiệu nhận diện UTF-8. Đây là quy ước của định dạng hoặc công cụ, không phải yêu cầu bắt buộc cho mọi file UTF-8.

Với decoder UTF-8 chuẩn của Java, ba byte BOM `EF BB BF` được giải mã thành ký tự `U+FEFF` ở đầu `String`; decoder không tự tiêu thụ và loại bỏ nó. Encoder `StandardCharsets.UTF_8` cũng không tự thêm BOM khi mã hóa một chuỗi thông thường. Nếu file cần BOM hoặc cần loại bỏ BOM, hãy quy định rõ trong hợp đồng và xử lý tại biên file; không giả định `StandardCharsets.UTF_8` tự động xử lý BOM.

Ví dụ nhận diện BOM sau khi đọc:

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
    text = text.substring(1); // Chỉ làm khi hợp đồng cho phép bỏ BOM.
}
```

### 8.2. Unicode normalization

Hai chuỗi có thể hiển thị giống nhau nhưng có dãy code point khác nhau. Ví dụ chữ `ắ` có thể được biểu diễn bằng code point dựng sẵn `U+1EAF` hoặc chuỗi `a + U+0306 + U+0301`.

```java
import java.text.Normalizer;

String composed = "\u1EAF";
String decomposed = "a\u0306\u0301";

System.out.println(composed.equals(decomposed)); // false

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
```

UTF-8 mã hóa từng dãy code point đó thành byte. Nó không tự chuẩn hóa nội dung. Nếu hệ thống cần so sánh tên, khóa hoặc dữ liệu người dùng theo chuẩn hóa NFC, hãy ghi rõ quy tắc normalization trong hợp đồng riêng.

### 8.3. Dấu xuống dòng và delimiter

UTF-8 không quy định một dòng kết thúc bằng LF hay CRLF, cũng không quy định dấu phân cách cột trong CSV. Nếu một file phải được xử lý giống nhau trên nhiều nền tảng, cần quy định các yếu tố này riêng.

Đặc biệt, dùng `BufferedReader.readLine()` rồi `BufferedWriter.newLine()` có thể thay đổi dấu xuống dòng. Nếu yêu cầu bảo toàn byte, không giải mã file thành `String` rồi ghi lại.

## 9. Áp dụng vào HTTP, JSON và thông điệp giữa dịch vụ

Với payload văn bản trên mạng, charset phải khớp với giao thức.

### 9.1. JSON trao đổi giữa các hệ thống

JSON trên mạng sử dụng UTF-8 theo RFC 8259. Khi tạo body JSON trong Java, hãy chọn charset rõ ràng ở API chuyển `String` thành byte:

```java
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String json = "{\"message\":\"Xin chào Việt Nam\"}";

HttpRequest request = HttpRequest.newBuilder()
        .uri(java.net.URI.create("https://api.example.test/messages"))
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
```

`BodyPublishers.ofString(json, UTF_8)` đảm bảo body được mã hóa bằng UTF-8. Header mô tả loại nội dung; việc chọn charset cho body cần tuân theo quy tắc JSON và hợp đồng API. Không dựa vào default charset của JVM để quyết định byte gửi đi.

### 9.2. Message queue và giao thức nội bộ

Một message broker thường vận chuyển byte payload. Hai dịch vụ cần thống nhất charset trong schema hoặc phiên bản giao thức. Nếu một dịch vụ phát UTF-8 và dịch vụ khác giải mã theo Windows-1252, lỗi có thể chỉ xuất hiện với dữ liệu có dấu hoặc emoji.

Nên kiểm thử bằng dữ liệu đại diện như tiếng Việt, ký tự ngoài BMP, dấu tổ hợp và payload sát giới hạn byte. Không chỉ thử chuỗi ASCII vì các charset phổ biến đều biểu diễn ASCII giống nhau và có thể che giấu lỗi.

### 9.3. Chữ ký số và checksum

Chữ ký và hash hoạt động trên byte. Nếu hai bên ký cùng một nội dung nhìn thấy nhưng mã hóa hoặc normalization khác nhau, byte đầu vào của thuật toán có thể khác và chữ ký không khớp.

Hợp đồng chữ ký cần xác định chính xác:
- Charset của văn bản.
- Quy tắc normalization nếu có.
- Quy tắc xuống dòng và canonicalization.
- Byte nào được ký hoặc hash, bao gồm BOM hay không.

Không đổi charset hoặc chuẩn hóa dữ liệu sau khi đã tạo chữ ký nếu giao thức không quy định việc đó.

## 10. Kiểm thử hợp đồng UTF-8 bằng byte cụ thể

Một test hữu ích không chỉ kiểm tra `String.equals()`. Hãy xác nhận byte theo một mẫu đã biết:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String value = "Cà";
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);

String actualHex = HexFormat.of()
        .withUpperCase()
        .formatHex(bytes);

if (!"43C3A0".equals(actualHex)) {
    throw new AssertionError("Byte UTF-8 không đúng: " + actualHex);
}
```

Trong UTF-8, `C` là `43`, còn `à` là `C3 A0`. Kết quả hex mong đợi là `43C3A0`.

Một bộ test thực tế nên bao gồm:

| Dữ liệu | Điều cần kiểm tra |
| --- | --- |
| ASCII như `ABC123` | Tương thích ASCII và không phát sinh byte ngoài dự kiến |
| Tiếng Việt có dấu như `Tiếng Việt` | Byte UTF-8 nhiều byte và đọc lại chính xác |
| Ký tự ngoài BMP như `🙂` | Bốn byte UTF-8 và bảo toàn code point |
| Dấu tổ hợp như `a + U+0306 + U+0301` | Chính sách normalization có được giữ đúng không |
| Byte UTF-8 không hợp lệ | Decoder có từ chối theo hợp đồng không |
| File có BOM | Chính sách BOM được thực thi nhất quán |
| File lớn sát giới hạn | Giới hạn được đo theo byte, không theo `String.length()` |

### 10.1. Kiểm tra cả byte lẫn văn bản sau round-trip

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String original = "Tiếng Việt 🙂";
byte[] encoded = original.getBytes(StandardCharsets.UTF_8);
String decoded = new String(encoded, StandardCharsets.UTF_8);

if (!Arrays.equals(encoded,
        decoded.getBytes(StandardCharsets.UTF_8))) {
    throw new AssertionError("Byte round-trip không khớp");
}

if (!original.equals(decoded)) {
    throw new AssertionError("Văn bản round-trip không khớp");
}
```

Kiểm tra round-trip này xác nhận chuyển đổi nhất quán với UTF-8. Đối với dữ liệu đầu vào không tin cậy, cần thêm kiểm tra decoder nghiêm ngặt vì phép giải mã mặc định có thể thay thế byte lỗi.

## 11. Chọn charset theo tình huống

| Tình huống | Lựa chọn | Lý do |
| --- | --- | --- |
| File văn bản mới, hợp đồng quy định UTF-8 | `StandardCharsets.UTF_8` | Rõ ràng, portable |
| JSON trao đổi giữa dịch vụ | UTF-8 theo RFC 8259 | Tuân thủ chuẩn JSON trên mạng |
| Đọc file legacy | Charset gốc của file | Tránh giải mã sai dữ liệu cũ |
| Giao thức yêu cầu UTF-16LE | `StandardCharsets.UTF_16LE` | Tuân thủ đặc tả của giao thức |
| File properties UTF-8 | `Reader` UTF-8 + `Properties.load(Reader)` | Overload `load(InputStream)` có quy tắc ISO-8859-1 riêng |
| Payload có yêu cầu từ chối byte lỗi | `CharsetDecoder` với `REPORT` | Không thay thế âm thầm |
| Tính hash hoặc chữ ký văn bản | Charset và canonicalization theo giao thức | Hai bên phải tạo đúng cùng dãy byte |

### Những lỗi nên tránh

1. Dùng `getBytes()` vì “JDK 18 mặc định đã là UTF-8”, trong khi dữ liệu là một hợp đồng lâu dài cần khai báo rõ.
2. Đổi file legacy sang UTF-8 chỉ bằng cách đổi JDK, không giải mã theo charset gốc.
3. Nghĩ rằng UTF-8 tự loại BOM, chuẩn hóa Unicode hoặc thống nhất newline.
4. Dùng `String.length()` để kiểm tra giới hạn byte của payload.
5. Dùng constructor `String(byte[], UTF_8)` khi hệ thống bắt buộc từ chối byte sai mà không kiểm tra chính sách thay thế.
6. Thay charset giao thức mà không phối hợp với bên gửi và bên nhận.

## 12. Bài tập tự kiểm tra

**Bài 1.** Vì sao nên dùng `StandardCharsets.UTF_8` thay cho `Charset.defaultCharset()` khi ghi file mà đặc tả yêu cầu UTF-8?

*Đáp án:* `StandardCharsets.UTF_8` luôn chỉ định UTF-8, không thay đổi theo cấu hình JVM. `Charset.defaultCharset()` phụ thuộc cấu hình khởi động, có thể khác khi dùng `COMPAT`.

**Bài 2.** Một file cũ được tạo theo Windows-1258. Có thể đọc bằng UTF-8 vì ứng dụng đã nâng lên JDK 18 không?

*Đáp án:* Không. Phải giải mã bằng charset thực tế của file cũ. JEP 400 không chuyển byte cũ sang UTF-8.

**Bài 3.** `StandardCharsets.UTF_8` có tự loại bỏ BOM hoặc chuẩn hóa chữ tiếng Việt về NFC không?

*Đáp án:* Không. Charset chỉ ánh xạ byte và ký tự. BOM và normalization cần quy tắc riêng của định dạng hoặc ứng dụng.

**Bài 4.** `new String(bytes, StandardCharsets.UTF_8)` có bảo đảm từ chối mọi byte UTF-8 sai không?

*Đáp án:* Không. Constructor thay thế chuỗi byte lỗi theo hợp đồng API. Dùng `CharsetDecoder` với `CodingErrorAction.REPORT` nếu phải phát hiện và từ chối byte không hợp lệ.

**Bài 5.** Một dịch vụ giới hạn request body ở 1 MiB. Nên kiểm tra `text.length()` hay số byte sau khi mã hóa UTF-8?

*Đáp án:* Nếu giới hạn là kích thước body truyền qua mạng, phải đo byte sau khi mã hóa UTF-8 hoặc giới hạn luồng byte trực tiếp. `String.length()` đếm UTF-16 code unit, không phải byte.

## 13. Ghi nhớ

`StandardCharsets.UTF_8` là lựa chọn rõ ràng khi hợp đồng dữ liệu yêu cầu UTF-8. JEP 400 làm UTF-8 trở thành default charset thông thường từ Java 18, nhưng default charset vẫn là thuộc tính môi trường của JVM và có thể chịu chế độ tương thích.

Một hợp đồng dữ liệu tốt xác định charset cùng với các quy tắc liên quan như BOM, normalization, newline, framing, giới hạn byte và chính sách dữ liệu lỗi. Khi đọc hoặc ghi, chọn đúng overload có charset; khi cần toàn vẹn nghiêm ngặt, cấu hình encoder/decoder báo lỗi; và khi kiểm thử, xác nhận cả byte lẫn văn bản.

### Tài liệu tham khảo

- [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
- [Oracle Java SE 27 — StandardCharsets](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [Oracle Java SE 27 — Charset](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html).
- [Oracle Java SE 27 — CharsetEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetEncoder.html).
- [Oracle Java SE 27 — CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Oracle Java SE 27 — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html).
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259).
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/).
