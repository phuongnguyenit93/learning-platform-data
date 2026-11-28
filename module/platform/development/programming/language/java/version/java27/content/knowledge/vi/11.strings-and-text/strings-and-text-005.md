# Charset, UTF-8 và chuyển đổi giữa byte với văn bản

## 1. Vì sao phải phân biệt byte và văn bản?

Trong ứng dụng Java 27, dữ liệu văn bản thường di chuyển qua nhiều ranh giới: file, socket, HTTP, message broker, cơ sở dữ liệu, tiến trình khác hoặc thiết bị đầu cuối. Tại ranh giới đó, chương trình nhận hoặc gửi **byte**. Bên trong mã nguồn Java, lập trình viên thường xử lý văn bản bằng **String**.

Hai dạng này không đồng nhất:

- **String** là chuỗi ký tự Unicode được biểu diễn qua các đơn vị mã UTF-16 trong API Java. Nó không mang theo nhãn “đây là UTF-8” hoặc “đây là ISO-8859-1”.
- **byte[]** là dãy byte, mỗi phần tử có 8 bit. Bản thân dãy byte không nói được nó chứa văn bản, ảnh, dữ liệu nén hay tệp nhị phân.
- **Charset** xác định quy tắc ánh xạ giữa các ký tự và các chuỗi byte. Quá trình chuyển **String → byte[]** gọi là *encoding*; chiều **byte[] → String** gọi là *decoding*.

~~~mermaid
flowchart LR
    A["String / văn bản Unicode"] -->|"Encode bằng Charset"| B["Dãy byte"]
    B -->|"Truyền / lưu trữ"| C["File, HTTP, socket, message"]
    C -->|"Nhận dãy byte"| D["Dãy byte"]
    D -->|"Decode bằng đúng Charset"| E["String / văn bản Unicode"]
~~~

**Nguyên tắc quan trọng nhất:** Hai bên trao đổi dữ liệu phải thống nhất encoding. Nếu một bên ghi byte theo UTF-8 nhưng bên đọc lại diễn giải theo charset khác, chữ có dấu có thể biến thành các ký tự sai (*mojibake*) ngay cả khi dữ liệu không bị hỏng trong quá trình truyền.

## 2. Charset, character encoding và Unicode

**Unicode** là hệ thống mã hóa khái niệm ký tự với các *code point*, ví dụ chữ **A** là U+0041, dấu **€** là U+20AC và emoji **😀** là U+1F600. **UTF-8** và **UTF-16** là các cách biểu diễn các code point thành đơn vị lưu trữ cụ thể.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Unicode code point | Định danh một điểm mã Unicode | U+0041, U+20AC, U+1F600 |
| UTF-8 | Mã hóa Unicode thành các byte có độ dài biến đổi | **A** = 41; **€** = E2 82 AC |
| UTF-16 | Biểu diễn qua các đơn vị mã 16 bit, có thể dùng surrogate pair | **😀** cần hai code unit UTF-16 |
| Charset trong Java | Đối tượng mô tả ánh xạ ký tự/byte | **StandardCharsets.UTF_8** |
| String | Giá trị văn bản bên trong ứng dụng Java | **"Chào Java"** |
| byte[] | Byte thực sự được ghi hoặc truyền đi | Kết quả của **text.getBytes(UTF_8)** |

UTF-8 là lựa chọn thông dụng và nên được ưu tiên cho dữ liệu văn bản mới vì hỗ trợ toàn bộ Unicode, tương thích với ASCII cho các ký tự ASCII, và không cần quy ước byte order.

Một số charset khác vẫn có thể xuất hiện khi tích hợp hệ thống bên ngoài. Ví dụ **ISO-8859-1** dùng một byte cho mỗi ký tự thuộc bảng mã Latin-1; nó không biểu diễn được nhiều ký tự tiếng Việt và emoji. **UTF-16LE** và **UTF-16BE** quy định thứ tự byte của các đơn vị mã UTF-16. Không được coi các charset này là hoán đổi được với nhau.

## 3. Các charset chuẩn nên dùng trong Java

Lớp **java.nio.charset.StandardCharsets** cung cấp những hằng Charset chuẩn, tránh sai chính tả và không cần tự tìm charset bằng chuỗi tên.

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset utf8 = StandardCharsets.UTF_8;
Charset ascii = StandardCharsets.US_ASCII;
Charset latin1 = StandardCharsets.ISO_8859_1;
Charset utf16le = StandardCharsets.UTF_16LE;

System.out.println(utf8.name()); // UTF-8
~~~

Một số lựa chọn:

| Charset | Dùng khi nào? | Lưu ý |
|---|---|---|
| **UTF_8** | Ghi file văn bản mới, trao đổi dữ liệu dịch vụ, nội dung Unicode | Lựa chọn mặc định nên ưu tiên cho hợp đồng dữ liệu mới |
| **US_ASCII** | Giao thức bị giới hạn rõ ràng trong dải ASCII | Không biểu diễn được chữ tiếng Việt có dấu |
| **ISO_8859_1** | Hệ thống ngoài hoặc định dạng dữ liệu quy định Latin-1 | Không hỗ trợ đầy đủ Unicode |
| **UTF_16** | Giao thức/tệp yêu cầu UTF-16 và cách xác định thứ tự byte tương ứng | Phải hiểu quy tắc BOM và byte order |
| **UTF_16LE**, **UTF_16BE** | Định dạng yêu cầu rõ kiểu little-endian/big-endian | Không đồng nhất với UTF-8 |

Khi charset được chỉ định bằng cấu hình ngoài, có thể dùng **Charset.forName(name)** rồi xử lý **UnsupportedCharsetException** hoặc **IllegalCharsetNameException**. Không nên chấp nhận tên charset bất kỳ từ đầu vào không tin cậy nếu hợp đồng hệ thống chỉ hỗ trợ một danh sách hữu hạn; hãy kiểm tra theo danh sách được phép.

Java cũng có những charset được hỗ trợ thêm ngoài danh sách hằng chuẩn, nhưng khả năng khả dụng có thể khác giữa runtime. Với giao thức mới, không nên tạo phụ thuộc không cần thiết vào một charset ngoài bộ charset chuẩn.

## 4. Chuyển String thành byte UTF-8

Phương thức thông dụng nhất:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String text = "A€😀";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

System.out.println(HexFormat.of().formatHex(bytes));
// 41e282acf09f9880
~~~

Ý nghĩa của dãy byte:

| Ký tự | Code point | UTF-8 dạng hex | Số byte |
|---|---|---|---:|
| A | U+0041 | **41** | 1 |
| € | U+20AC | **E2 82 AC** | 3 |
| 😀 | U+1F600 | **F0 9F 98 80** | 4 |
| **Tổng** | | **41 E2 82 AC F0 9F 98 80** | **8** |

Các byte UTF-8 lớn hơn 0x7F sẽ xuất hiện dưới dạng giá trị âm nếu xem trực tiếp **byte** của Java, vì kiểu **byte** là số nguyên có dấu từ -128 đến 127. Điều này **không có nghĩa dữ liệu bị hỏng**. Khi cần hiển thị giá trị hex hoặc số không dấu, dùng **HexFormat** hoặc chuyển bằng **byteValue & 0xFF**.

~~~java
for (byte value : bytes) {
    System.out.printf("%02X ", value & 0xFF);
}
~~~

Không ép từng ký tự **char** sang **byte** để tự tạo UTF-8. Phép ép kiểu đó chỉ lấy một phần giá trị số, không thực hiện quy tắc mã hóa Unicode và dễ làm mất dữ liệu.

## 5. Chuyển byte UTF-8 thành String

Khi đã biết dãy byte là UTF-8, sử dụng constructor nhận Charset:

~~~java
import java.nio.charset.StandardCharsets;

byte[] payload = {
    (byte) 0xE2, (byte) 0x82, (byte) 0xAC
};

String decoded = new String(payload, StandardCharsets.UTF_8);
System.out.println(decoded); // €
~~~

Một vòng *round-trip* cơ bản:

~~~java
String original = "Xin chào Java ☕";
byte[] encoded = original.getBytes(StandardCharsets.UTF_8);
String restored = new String(encoded, StandardCharsets.UTF_8);

System.out.println(original.equals(restored)); // true
~~~

Điều kiện để vòng round-trip giữ nguyên văn bản là dữ liệu đầu vào hợp lệ cho quá trình mã hóa và cùng charset được dùng ở hai chiều. UTF-8 có thể mã hóa các chuỗi Unicode hợp lệ. Tuy nhiên, Java String về mặt kỹ thuật có thể chứa **surrogate không ghép cặp**; các phép mã hóa thông dụng có thể thay thế chuỗi đầu vào lỗi. Khi yêu cầu bảo toàn dữ liệu nghiêm ngặt, hãy dùng **CharsetEncoder** và **CharsetDecoder** với chế độ báo lỗi.

Cú pháp **new String(bytes)** và **text.getBytes()** không chỉ định charset. Dù Java hiện mặc định UTF-8 trong phần lớn API, tốt nhất vẫn chỉ rõ **StandardCharsets.UTF_8** ở mọi ranh giới lưu trữ hoặc giao tiếp để hợp đồng dữ liệu dễ đọc, có thể kiểm thử và không phụ thuộc cấu hình chạy.

## 6. Kích thước byte không bằng số ký tự

Java String dùng chỉ số theo **UTF-16 code unit**, nên **String.length()** không trả về số byte UTF-8 và cũng không luôn bằng số Unicode code point.

~~~java
import java.nio.charset.StandardCharsets;

String sample = "A€😀";

System.out.println(sample.length()); // 4 UTF-16 code units
System.out.println(sample.codePointCount(0, sample.length())); // 3 code points
System.out.println(sample.getBytes(StandardCharsets.UTF_8).length); // 8 bytes
~~~

Trong ví dụ:

- **A** có một code unit UTF-16 và một byte UTF-8.
- **€** có một code unit UTF-16 và ba byte UTF-8.
- **😀** có hai code unit UTF-16 (một surrogate pair) và bốn byte UTF-8.

Cũng cần phân biệt **code point** với **grapheme cluster** (ký tự người dùng nhìn thấy). Một chữ có dấu đôi khi được lưu thành base letter và combining mark, gồm nhiều code point nhưng hiển thị thành một grapheme. Nếu xử lý cắt chuỗi, giới hạn độ dài giao diện hoặc đánh dấu vùng chọn, không nên mặc định mỗi phần tử **char** tương ứng với một ký tự nhìn thấy.

## 7. Điểm mới đáng chú ý trong Java 27: String.encodedLength

**Java 27** bổ sung **String.encodedLength(Charset)** để lấy độ dài của chuỗi sau khi mã hóa bằng một Charset mà không cần tự tạo một mảng byte chỉ để đo kích thước.

~~~java
import java.nio.charset.StandardCharsets;

String value = "A€😀";

int utf8Bytes = value.encodedLength(StandardCharsets.UTF_8);
System.out.println(utf8Bytes); // 8
~~~

Độ dài được tính theo cùng quy tắc thay thế đầu vào lỗi như **getBytes(Charset)**, nên:

~~~java
int length = value.encodedLength(StandardCharsets.UTF_8);
int actualLength = value.getBytes(StandardCharsets.UTF_8).length;

System.out.println(length == actualLength); // true
~~~

API này hữu ích khi cần ước tính dung lượng payload, kiểm tra giới hạn kích thước tính theo byte hoặc chuẩn bị bộ đệm. Nó không tự kiểm tra một chuỗi có hợp lệ theo chế độ *strict encoding* và cũng không tạo ra payload byte; muốn gửi hoặc ghi dữ liệu, vẫn phải mã hóa hoặc ghi qua một Writer.

**Lưu ý phiên bản:** **String.encodedLength(Charset)** được giới thiệu từ Java 27. Nếu thư viện phải biên dịch/chạy trên Java 25 hoặc các phiên bản cũ hơn, không dùng trực tiếp API này trong mã được chia sẻ cho những phiên bản đó.

## 8. Charset mặc định trên Java 27 và JEP 400

Từ Java 18, **JEP 400 — UTF-8 by Default** quy định UTF-8 là charset mặc định của các Java SE API liên quan trên mọi hệ điều hành, thay vì phụ thuộc vào code page hoặc locale của máy như nhiều môi trường Java 17 trở về trước.

Có thể kiểm tra ở runtime:

~~~java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
~~~

Thông thường kết quả là **UTF-8**. Tuy nhiên, JDK vẫn có cơ chế tương thích cho quá trình di chuyển từ hệ thống cũ. Oracle tài liệu hóa giá trị khởi chạy **-Dfile.encoding=COMPAT** để áp dụng cách chọn charset mặc định trước JDK 18; **-Dfile.encoding=UTF-8** đặt mặc định UTF-8. Các giá trị khác không được hỗ trợ như một cơ chế cấu hình charset mặc định chuẩn.

Không nên thay đổi **file.encoding** trong mã bằng **System.setProperty** và giả định điều đó sẽ thay đổi Charset.defaultCharset() của tiến trình đang chạy. Charset mặc định được xác định trong quá trình khởi động JVM; phụ thuộc vào thay đổi runtime như vậy là không đáng tin cậy.

Quan trọng hơn, không phải *mọi* con đường I/O đều nhất thiết dùng **Charset.defaultCharset()**. Một số API có charset quy định riêng, thiết bị đầu cuối và standard streams có thể có cơ chế mã hóa khác. Chẳng hạn, **Files.readString(path)** được quy định đọc UTF-8 ngay cả khi charset mặc định có cấu hình tương thích khác.

**Khuyến nghị thiết kế:** Xem charset là một phần của hợp đồng dữ liệu và ghi rõ UTF-8 tại chỗ chuyển đổi. Chỉ dùng **COMPAT** cho kiểm tra và kế hoạch di chuyển hệ thống bị phụ thuộc encoding cũ, không dùng nó như giải pháp lâu dài cho dữ liệu mới.

## 9. Đọc và ghi file UTF-8 bằng Files

Đối với file văn bản kích thước vừa phải, **java.nio.file.Files** có các API trực tiếp:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("notes.txt");

Files.writeString(path, "Chào Java 27\n", StandardCharsets.UTF_8);
String text = Files.readString(path, StandardCharsets.UTF_8);

System.out.print(text);
~~~

Các overload **Files.writeString(path, text)** và **Files.readString(path)** cũng dùng UTF-8 theo đặc tả. Việc ghi tường minh **StandardCharsets.UTF_8** vẫn có ích để người đọc thấy ngay hợp đồng encoding.

**Files.writeString** mặc định tạo file nếu chưa có và thay nội dung file hiện có. Cần cân nhắc **StandardOpenOption.APPEND** khi muốn ghi nối thay vì ghi đè. Với dữ liệu nghiệp vụ, cũng cần nghĩ đến quyền ghi, ghi đồng thời và yêu cầu ghi nguyên tử, vốn là những vấn đề khác với charset.

**Files.readString** đọc toàn bộ file vào bộ nhớ. Với file rất lớn, nên dùng API streaming và xử lý từng đoạn hoặc từng dòng. Khi byte trong file bị lỗi đối với charset đã chọn, **Files.readString** có thể ném **IOException** cho lỗi giải mã; hành vi này khác với việc sử dụng trực tiếp constructor **new String(bytes, charset)** vốn có thể thay byte không hợp lệ.

Ví dụ đọc văn bản theo dòng:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (var reader = Files.newBufferedReader(
        Path.of("events.log"), StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

**readLine()** loại bỏ ký tự kết thúc dòng của mỗi dòng khi trả kết quả. Vì vậy, khi cần bảo toàn chính xác line ending ban đầu, không nên đọc từng dòng rồi ghi lại mà không có quy tắc xử lý rõ ràng.

## 10. Đọc và ghi qua byte stream: InputStreamReader và OutputStreamWriter

Khi dữ liệu đến từ byte stream (file stream, socket, response body hoặc một InputStream khác), có thể nối một lớp chuyển đổi byte ↔ ký tự ở đúng ranh giới.

~~~mermaid
flowchart TD
    A[InputStream - byte] -->|InputStreamReader UTF-8| B[Reader - char]
    B --> C[BufferedReader]
    D[Writer - char] -->|OutputStreamWriter UTF-8| E[OutputStream - byte]
~~~

Ví dụ đọc file có charset tường minh:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (var input = Files.newInputStream(Path.of("messages.txt"));
     var reader = new BufferedReader(
         new InputStreamReader(input, StandardCharsets.UTF_8))) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

Ví dụ ghi UTF-8 qua OutputStreamWriter:

~~~java
import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

try (var output = Files.newOutputStream(Path.of("export.txt"));
     var writer = new BufferedWriter(
         new OutputStreamWriter(output, StandardCharsets.UTF_8))) {

    writer.write("Dữ liệu Unicode");
    writer.newLine();
}
~~~

Đối với các luồng tài nguyên của chính chương trình, dùng **try-with-resources** để bảo đảm đóng tài nguyên. Không đóng **System.out** hoặc **System.err** tùy tiện trong mã thư viện vì đây là các stream được chia sẻ ở phạm vi tiến trình.

Một Reader/Writer là cầu nối giữa byte và ký tự; lớp đệm (*buffered*) giảm số lần gọi I/O. Không nhầm **BufferedInputStream** (vẫn xử lý byte) với **BufferedReader** (đã xử lý ký tự).

## 11. Chế độ chuyển đổi tiện lợi có thể thay thế dữ liệu lỗi

Một số API tiện lợi chọn cách tiếp tục xử lý khi gặp input không hợp lệ:

~~~java
import java.nio.charset.StandardCharsets;

byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
String text = new String(invalidUtf8, StandardCharsets.UTF_8);

System.out.println(text); // �(
~~~

Byte **C3** ở đây mở đầu một chuỗi UTF-8 cần byte tiếp theo hợp lệ, nhưng **28** không phải byte tiếp nối. Constructor **String(byte[], Charset)** thay chuỗi lỗi bằng replacement string của charset, thay vì mặc nhiên ném lỗi.

Ở chiều ngược lại, **String.getBytes(Charset)** cũng có thể thay thế ký tự không thể biểu diễn trong charset đích:

~~~java
String vietnamese = "Tiếng Việt";
byte[] ascii = vietnamese.getBytes(StandardCharsets.US_ASCII);
System.out.println(new String(ascii, StandardCharsets.US_ASCII));
// Có ký tự bị thay thế; không giữ nguyên tiếng Việt
~~~

Đây là một cơ chế hợp lệ khi hệ thống **chấp nhận** dữ liệu bị thay thế; không phù hợp nếu yêu cầu giữ nguyên byte và thông tin người dùng. Không nên cho rằng một lần chuyển đổi thành công có nghĩa là dữ liệu ban đầu hoàn toàn hợp lệ.

Ba chính sách xử lý lỗi phổ biến trong **CodingErrorAction**:

| Chính sách | Ý nghĩa | Trường hợp nên dùng |
|---|---|---|
| **REPORT** | Báo lỗi malformed/unmappable | Dữ liệu bắt buộc chính xác; import dữ liệu có kiểm soát |
| **REPLACE** | Thay đoạn lỗi bằng chuỗi hoặc byte thay thế | Hiển thị văn bản lỗi nhưng muốn tiếp tục |
| **IGNORE** | Bỏ qua đoạn lỗi | Chỉ dùng khi có quyết định rõ ràng rằng mất dữ liệu là chấp nhận được |

## 12. Giải mã UTF-8 nghiêm ngặt với CharsetDecoder

Khi dữ liệu phải **hợp lệ UTF-8**, dùng **CharsetDecoder** và yêu cầu báo lỗi:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {

    var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

    return decoder.decode(ByteBuffer.wrap(bytes)).toString();
}
~~~

Ví dụ bắt dữ liệu lỗi:

~~~java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};

try {
    String result = decodeUtf8Strict(invalid);
    System.out.println(result);
} catch (java.nio.charset.CharacterCodingException exception) {
    System.err.println("Invalid UTF-8 input");
}
~~~

**CharsetDecoder** được cấu hình mặc định theo chính sách **REPORT**, nhưng đặt tường minh hai hành động giúp ý định xử lý trở nên rõ ràng. Các phương thức chuyển đổi có đối số ByteBuffer/CharBuffer được dùng cho dữ liệu lớn hoặc streaming có thể cần quản lý trạng thái **decode**, **flush**, **reset**; phương thức **decode(ByteBuffer)** ở ví dụ là thao tác trọn gói thuận tiện.

Decoder được tạo để dùng theo một chu trình chuyển đổi và không nên chia sẻ cùng instance giữa nhiều luồng không đồng bộ. Nếu hệ thống cần xử lý đồng thời, hãy tạo decoder cho từng lần xử lý hoặc quản lý phiên chuyển đổi độc lập.

**Giới hạn quan trọng:** Strict UTF-8 decoder chỉ phát hiện chuỗi byte **không hợp lệ theo UTF-8**. Nếu một chuỗi byte vốn dùng charset khác nhưng tình cờ cũng tạo thành UTF-8 hợp lệ, decoder không thể biết rằng nội dung đó bị gắn nhãn sai. Việc chọn đúng charset nguồn vẫn phải dựa trên metadata, giao thức hoặc hợp đồng dữ liệu.

## 13. Mã hóa nghiêm ngặt với CharsetEncoder

Tương tự, **CharsetEncoder** cho phép yêu cầu báo lỗi thay vì thay ký tự không biểu diễn được.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static byte[] encodeLatin1Strict(String text)
        throws CharacterCodingException {

    var encoder = StandardCharsets.ISO_8859_1.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

    ByteBuffer encoded = encoder.encode(CharBuffer.wrap(text));
    byte[] bytes = new byte[encoded.remaining()];
    encoded.get(bytes);

    return bytes;
}
~~~

Khi truyền chuỗi **"Café"**, Latin-1 có thể mã hóa hợp lệ. Khi truyền **"Tiếng Việt"** hoặc emoji, charset đích không biểu diễn được một số ký tự; encoder nghiêm ngặt sẽ báo lỗi thay vì âm thầm làm mất thông tin.

Với UTF-8, mọi Unicode scalar value hợp lệ đều mã hóa được. Tuy nhiên, một String chứa surrogate lẻ không tạo thành chuỗi UTF-16 hợp lệ có thể gây **MalformedInputException** trong strict encoder. Vì vậy strict encoding hữu ích ngay cả khi charset đích là UTF-8.

Nếu cần mã hóa dữ liệu lớn theo từng phần, dùng API encode có trạng thái hoặc Writer với encoder được cấu hình, thay vì tạo mảng byte lớn không cần thiết.

## 14. BOM, byte order và dấu ký tự đầu văn bản

**Byte Order Mark (BOM)** là một dấu ở đầu một số dạng văn bản Unicode. Trong UTF-8, chuỗi byte **EF BB BF** tương ứng với U+FEFF.

- UTF-8 **không cần BOM** để xác định byte order; thường nên tạo file UTF-8 **không BOM**, trừ khi hệ thống nhận yêu cầu khác.
- Một nguồn dữ liệu thực tế có thể cung cấp BOM; khi giải mã UTF-8 thông thường, dấu này có thể xuất hiện như ký tự U+FEFF ở đầu String.
- Trong UTF-16, BOM có thể cung cấp thông tin về thứ tự byte. Không nên áp dụng quy tắc BOM của UTF-8 cho UTF-16LE/UTF-16BE một cách máy móc.

Ví dụ xử lý UTF-8 BOM khi giao thức nguồn định nghĩa nó là dấu đầu file:

~~~java
String text = java.nio.file.Files.readString(
    java.nio.file.Path.of("incoming.csv"),
    java.nio.charset.StandardCharsets.UTF_8
);

if (text.startsWith("\uFEFF")) {
    text = text.substring(1);
}
~~~

Chỉ bỏ U+FEFF khi hợp đồng tệp xác định đó là BOM cần loại bỏ. Đừng tự động xóa mọi U+FEFF xuất hiện ở bất kỳ vị trí nào; việc thay đổi văn bản tùy tiện có thể làm mất dữ liệu hoặc thay đổi ý nghĩa nội dung.

Khi làm việc với tệp CSV và JSON từ nhiều nguồn, hãy ghi rõ charset, chính sách BOM và line endings của mỗi định dạng thay vì trông chờ vào suy đoán của người đọc.

## 15. Chuyển mã giữa hai charset

Một công việc thường gặp khi tích hợp hệ thống ngoài là nhận dữ liệu đã mã hóa bằng charset cũ, chuyển thành Unicode String, sau đó ghi ra UTF-8.

Ví dụ nguồn **được xác nhận là ISO-8859-1**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path source = Path.of("legacy-latin1.txt");
Path target = Path.of("converted-utf8.txt");

byte[] legacyBytes = Files.readAllBytes(source);
String text = new String(legacyBytes, StandardCharsets.ISO_8859_1);
Files.writeString(target, text, StandardCharsets.UTF_8);
~~~

~~~text
ISO-8859-1 bytes -> decode ISO-8859-1 -> String -> encode UTF-8 -> UTF-8 bytes
~~~

Trong ví dụ này, tên file biểu thị encoding nguồn đã biết. Không được áp dụng ISO-8859-1 cho mọi tệp không đọc được, vì một số bảng mã một byte có thể giải mã mọi byte thành ký tự nhưng vẫn tạo nội dung sai.

**Mã hóa lại byte trực tiếp bằng cách đổi nhãn charset không chuyển đổi dữ liệu.** Chuyển mã cần có bước giải mã theo charset gốc, sau đó mã hóa theo charset đích. Nếu tệp cực lớn, dùng Reader với charset nguồn và Writer với charset đích để chuyển từng đoạn mà không phải nạp toàn bộ file vào RAM.

## 16. Mismatch encoding và mojibake

Ví dụ chữ **é** khi mã hóa UTF-8 là hai byte **C3 A9**. Nếu hai byte ấy bị giải mã nhầm theo ISO-8859-1, chúng trở thành hai ký tự **Ã©** thay vì một chữ **é**.

~~~java
import java.nio.charset.StandardCharsets;

byte[] utf8 = "é".getBytes(StandardCharsets.UTF_8);
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);
String correct = new String(utf8, StandardCharsets.UTF_8);

System.out.println(wrong);   // Ã©
System.out.println(correct); // é
~~~

Vấn đề không phải Java “không hỗ trợ tiếng Việt”. Vấn đề là dữ liệu đã được **giải mã bằng bảng mã sai**. Để xử lý:

1. Xác định encoding từ hợp đồng giao tiếp, header HTTP, metadata tệp, cấu hình nguồn hoặc đặc tả giao thức.
2. Đọc lại **byte gốc chưa bị chuyển đổi**.
3. Giải mã bằng charset chính xác.
4. Mã hóa sang UTF-8 ở ranh giới đích nếu cần.

Không nên sửa mojibake bằng cách thay chuỗi thủ công khi vẫn còn byte gốc; phương pháp đó dễ biến sai lệch đơn giản thành mất dữ liệu không thể phục hồi.

## 17. Chuẩn hóa Unicode không phải chuyển đổi charset

Hai String có thể hiển thị cùng một ký tự nhưng chứa các code point khác nhau. Ví dụ chữ **é** có thể là một code point U+00E9, hoặc là chữ **e** U+0065 kết hợp với dấu sắc U+0301.

~~~java
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false
~~~

Mã hóa cả hai bằng UTF-8 vẫn có thể tạo **hai dãy byte khác nhau** vì thứ tự code point khác nhau. Nếu hệ thống cần chuẩn hóa để so sánh, có thể dùng **java.text.Normalizer**:

~~~java
import java.text.Normalizer;

String left = Normalizer.normalize(composed, Normalizer.Form.NFC);
String right = Normalizer.normalize(decomposed, Normalizer.Form.NFC);

System.out.println(left.equals(right)); // true
~~~

**Normalization** và **charset encoding** là hai vấn đề khác nhau:

- Normalization thay đổi hoặc chuẩn hóa **cách biểu diễn Unicode** theo chính sách cụ thể.
- Encoding chuyển **Unicode String thành byte** theo charset.

Không nên chuẩn hóa mọi văn bản một cách mù quáng. Với chữ ký số, hash, mã định danh, tài liệu pháp lý hoặc payload cần giữ nguyên byte, thay đổi normalization có thể làm đổi kết quả xác minh.

## 18. Text khác binary: khi nào dùng Base64?

Không phải mọi **byte[]** đều là văn bản. Ảnh PNG, PDF, ZIP, dữ liệu mã hóa và dữ liệu nén không nhất thiết tạo thành byte UTF-8 hợp lệ.

Nếu cần đưa dữ liệu nhị phân vào một trường văn bản theo giao thức cho phép, dùng **Base64** thay vì **new String(binary, UTF_8)**:

~~~java
import java.util.Base64;

byte[] binary = {(byte) 0x00, (byte) 0xFF, (byte) 0x80};

String base64 = Base64.getEncoder().encodeToString(binary);
byte[] restored = Base64.getDecoder().decode(base64);

System.out.println(java.util.Arrays.equals(binary, restored)); // true
~~~

Base64 biến byte thành chuỗi ký tự ASCII có thể truyền qua các môi trường văn bản. Nó **không phải charset dùng để giải mã ngôn ngữ tự nhiên**, cũng không phải cơ chế mã hóa bảo mật hoặc che giấu dữ liệu nhạy cảm. Khi giao thức hỗ trợ truyền byte trực tiếp, không cần Base64.

## 19. Charset trong HTTP, cơ sở dữ liệu và tiến trình

Khi giao tiếp giữa các hệ thống, cần xác định chính xác lớp nào chịu trách nhiệm encode/decode.

**HTTP và API:** Thống nhất charset của payload theo đặc tả giao thức và các header liên quan. Với các API JSON hiện đại giao tiếp qua mạng, UTF-8 thường là lựa chọn chuẩn. Không tự ép mọi response body thành String trước khi đọc metadata phản hồi hoặc trước khi biết payload thực sự là text.

**Cơ sở dữ liệu:** Ưu tiên driver và API truy cập dữ liệu có hỗ trợ Unicode. Với JDBC, dùng các thao tác parameter binding như **PreparedStatement.setString(...)**, thay vì tự chuyển String thành byte để chèn vào cột văn bản khi driver đã có trách nhiệm xử lý kiểu dữ liệu đó.

**Tiến trình con:** Khi Java đọc stdout của lệnh ngoài, không được giả định lệnh đó luôn xuất UTF-8, đặc biệt khi công cụ chạy trên nhiều hệ điều hành hoặc locale. Phải xác định charset đầu ra theo hợp đồng của tiến trình và sử dụng **InputStreamReader(process.getInputStream(), charset)** phù hợp.

**Terminal:** Việc in chuỗi Unicode ra **System.out** còn phụ thuộc vào encoding của standard output và khả năng hiển thị font của terminal. Mã hóa payload đúng không đồng nghĩa mọi terminal sẽ hiển thị đúng glyph. Khi tạo dữ liệu machine-readable, hãy quy định rõ UTF-8 ở ranh giới xuất và cấu hình phía nhận tương ứng.

## 20. Demo hoàn chỉnh: round-trip và từ chối UTF-8 lỗi

Mã sau là ví dụ độc lập, sử dụng API ổn định trên Java 27. Lưu thành **Utf8RoundTripDemo.java**.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class Utf8RoundTripDemo {
    private static String decodeStrict(byte[] bytes)
            throws CharacterCodingException {

        var decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

        return decoder.decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static void main(String[] args) throws Exception {
        String original = "Xin chào — 😀";
        byte[] encoded = original.getBytes(StandardCharsets.UTF_8);

        System.out.println("Hex: " + HexFormat.of().formatHex(encoded));
        System.out.println("Byte length: " + encoded.length);
        System.out.println("Java 27 encodedLength: "
            + original.encodedLength(StandardCharsets.UTF_8));

        String decoded = decodeStrict(encoded);
        Path target = Path.of("utf8-roundtrip.txt");

        Files.writeString(target, decoded, StandardCharsets.UTF_8);
        String loaded = Files.readString(target, StandardCharsets.UTF_8);

        System.out.println("Round-trip equal: " + original.equals(loaded));

        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
        try {
            decodeStrict(invalidUtf8);
            throw new AssertionError("Invalid bytes should fail");
        } catch (CharacterCodingException expected) {
            System.out.println("Invalid UTF-8 detected");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 Utf8RoundTripDemo.java
java Utf8RoundTripDemo
~~~

Các dòng kết quả quan trọng:

~~~text
Round-trip equal: true
Invalid UTF-8 detected
~~~

Dòng **Java 27 encodedLength** phải bằng giá trị **Byte length** của cùng chuỗi khi mã hóa theo UTF-8; dòng **Hex** thể hiện dãy byte chính xác. Chương trình tạo một tệp **utf8-roundtrip.txt** trong thư mục chạy.

Nếu đang biên dịch trên JDK trước 27, dòng gọi **String.encodedLength** sẽ không hợp lệ; điều đó phản ánh yêu cầu phiên bản, không phải lỗi về khái niệm encoding.

## 21. Lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Chữ Việt thành ký tự lạ | Byte được giải mã sai charset | Xác định charset nguồn và decode lại từ byte gốc |
| Byte âm khi in mảng | Java byte là kiểu số có dấu | Hiển thị hex hoặc dùng **value & 0xFF** |
| **String.length()** không bằng byte length | UTF-16 code units khác byte UTF-8 | Dùng **getBytes(UTF_8).length** hoặc **encodedLength(UTF_8)** từ Java 27 |
| Dữ liệu lỗi nhưng không ném ngoại lệ | Constructor String có chế độ replacement | Dùng **CharsetDecoder** với **REPORT** |
| Ghi ASCII làm mất dấu | Charset đích không biểu diễn được chữ Việt | Dùng UTF-8 hoặc strict encoder để phát hiện |
| File có ký tự vô hình ở đầu | UTF-8 BOM được giữ lại dưới dạng U+FEFF | Xử lý BOM theo hợp đồng nguồn |
| Đọc file lớn hết bộ nhớ | **readString/readAllBytes** tải toàn bộ nội dung | Dùng BufferedReader và Reader/Writer theo luồng |
| Ký tự hiển thị sai trên terminal | Encoding standard output và terminal không thống nhất | Kiểm tra cấu hình terminal, stdout và font |
| JSON/HTTP nhận dữ liệu lỗi | Không thống nhất charset ở ranh giới mạng | Xác định encoding theo giao thức/header và kiểm tra payload |
| Chuyển binary thành String gây mất dữ liệu | Byte nhị phân không phải văn bản UTF-8 | Giữ dạng byte hoặc dùng Base64 theo hợp đồng |
| Chữ trông giống nhau nhưng equals false | Unicode normalization khác nhau | Áp dụng Normalizer khi chính sách so sánh cho phép |
| Chuyển mã vẫn lỗi sau khi đổi tên tệp | Chỉ đổi tên/nhãn, không decode rồi encode | Giải mã đúng charset gốc, sau đó mã hóa charset đích |

## 22. Bài tập thực hành

**Bài tập 1 — Đếm byte:** Với chuỗi gồm ký tự ASCII, chữ tiếng Việt, ký hiệu tiền tệ và emoji, in **length()**, **codePointCount(...)**, độ dài UTF-8 và chuỗi hex của payload. Giải thích vì sao bốn kết quả có thể khác nhau.

**Bài tập 2 — Strict decoding:** Tạo **byte[]** hợp lệ từ một String tiếng Việt, rồi sửa một byte tiếp nối UTF-8 thành giá trị không hợp lệ. So sánh kết quả giữa **new String(bytes, UTF_8)** và **CharsetDecoder** với **REPORT**.

**Bài tập 3 — Chuyển mã có metadata:** Tạo một file ISO-8859-1 chứa chuỗi phù hợp với bảng mã, rồi chuyển sang UTF-8 bằng Reader và Writer. Sau khi chuyển, xác nhận nội dung Unicode vẫn tương đương.

**Bài tập 4 — UTF-8 BOM:** Tạo một file bắt đầu bằng ba byte **EF BB BF** rồi nối thêm nội dung UTF-8. Đọc vào String, kiểm tra ký tự đầu tiên và viết hàm bỏ BOM chỉ khi giao thức nguồn cho phép.

**Bài tập 5 — Thực hành Java 27:** Viết một phương thức kiểm tra payload có vượt giới hạn **4 KiB UTF-8** hay không bằng **String.encodedLength(StandardCharsets.UTF_8)**. So sánh với phương án cấp phát mảng byte. Ghi rõ vì sao bộ đếm này không thay thế strict encoder khi cần từ chối String lỗi.

## 23. Checklist thiết kế ứng dụng xử lý text

- [ ] Mỗi ranh giới byte ↔ text có **Charset** được xác định rõ.
- [ ] Ưu tiên **UTF-8** cho dữ liệu văn bản mới khi giao thức không bắt buộc charset khác.
- [ ] Dùng **StandardCharsets.UTF_8** thay vì phụ thuộc ngầm vào charset mặc định.
- [ ] Không nhầm số UTF-16 code units, Unicode code points và byte length.
- [ ] Dùng **String.encodedLength(Charset)** chỉ khi target Java 27 trở lên và phù hợp yêu cầu.
- [ ] Dùng **CharsetDecoder/CharsetEncoder** với **REPORT** nếu dữ liệu không được phép bị thay thế.
- [ ] Đọc file lớn theo luồng; giới hạn kích thước của file/payload khi tải toàn bộ.
- [ ] Không suy đoán charset từ nội dung khi hợp đồng nguồn có thể cung cấp metadata chính xác.
- [ ] Xử lý BOM và Unicode normalization theo quy tắc rõ ràng.
- [ ] Không chuyển byte binary thành text một cách tùy tiện.
- [ ] Kiểm thử tiếng Việt có dấu, emoji, chuỗi rỗng, surrogate lỗi và byte UTF-8 không hợp lệ.
- [ ] Xác định encoding cho log, terminal, HTTP và tiến trình con theo ranh giới thật.

Một hệ thống xử lý văn bản ổn định cần thống nhất **charset tại ranh giới dữ liệu**, bảo toàn nội dung khi chuyển qua byte và lựa chọn chính sách lỗi đúng với yêu cầu nghiệp vụ. Trong Java 27, **StandardCharsets**, **Files**, **Reader/Writer**, **CharsetDecoder/CharsetEncoder** và **String.encodedLength** cung cấp các công cụ hiện hành để thực hiện điều đó rõ ràng, hiệu quả và có thể kiểm thử.

## Tài liệu tham khảo

- [Java SE 27 — String API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): getBytes(Charset), constructor decode, encodedLength(Charset) từ Java 27.
- [Java SE 27 — Charset API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): Charset, charset mặc định và chuyển đổi văn bản.
- [Java SE 27 — CharsetDecoder API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html): REPORT/REPLACE/IGNORE và quy trình giải mã.
- [Java SE 27 — CharsetEncoder API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetEncoder.html): chính sách lỗi khi mã hóa.
- [Java SE 27 — Files API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): readString, writeString, buffered readers và writers.
- [Oracle JDK 27 Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): UTF-8 mặc định và chế độ COMPAT.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): lý do và phạm vi UTF-8 mặc định từ JDK 18.
