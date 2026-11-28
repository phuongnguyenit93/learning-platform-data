# Xác định charset từ hợp đồng hoặc metadata thay vì suy đoán chỉ từ hình thức hiển thị

## 1. Charset là một phần của hợp đồng dữ liệu

Byte không tự mang theo tên charset. Một dãy byte chỉ có thể được diễn giải thành văn bản khi chương trình biết quy tắc ánh xạ byte sang ký tự. Cùng một dãy byte có thể tạo ra những chuỗi khác nhau dưới UTF-8, ISO-8859-1, Windows-1252 hoặc một charset khác.

Vì vậy, khi nhận một file, response HTTP, message từ queue hoặc dữ liệu từ thiết bị, câu hỏi đầu tiên không phải là “chữ đang hiển thị trông giống charset nào?”. Câu hỏi đúng là **bên tạo dữ liệu đã cam kết encoding nào, và cam kết đó được ghi ở đâu?**

Nguồn xác định charset có thể là:

- Đặc tả giao thức hoặc định dạng file.
- Metadata đi kèm payload, chẳng hạn `Content-Type` của HTTP hoặc khai báo encoding trong XML.
- Cấu hình rõ ràng giữa bên gửi và bên nhận.
- Byte Order Mark (BOM), nếu định dạng cho phép và không có metadata ưu tiên cao hơn.
- Tài liệu của hệ thống tạo file hoặc API cung cấp dữ liệu.

Hình thức hiển thị chỉ là một triệu chứng để điều tra. Nó không chứng minh byte đã được giải mã đúng.

```text
Nguồn dữ liệu
    |
    v
Tìm hợp đồng / metadata / định dạng
    |
    +--> Charset đã xác định? ---- Không ----> Dừng, yêu cầu metadata hoặc xác minh nguồn
    |          |
    |         Có
    |          v
    |     Chọn Charset tường minh
    |          |
    |          v
    |     Decode có kiểm soát
    |          |
    |          v
    |     Kiểm tra nội dung / cấu trúc
    |          |
    |          v
    |     Xử lý nghiệp vụ
    |
    +--> BOM hoặc detector chỉ là bằng chứng bổ trợ, không thay hợp đồng
```

Trong Java 18, JEP 400 đưa UTF-8 thành default charset thông thường của JVM. Thay đổi đó giúp môi trường Java nhất quán hơn, nhưng không thay thế hợp đồng encoding của từng giao thức, file hoặc API.

## 2. Thứ tự ưu tiên khi xác định charset

Khi có nhiều dấu hiệu, cần dùng một quy tắc ưu tiên rõ ràng. Thứ tự dưới đây là hướng dẫn thực tế; đặc tả của định dạng cụ thể luôn có quyền quyết định cuối cùng.

| Mức ưu tiên | Nguồn thông tin | Cách sử dụng |
| --- | --- | --- |
| 1 | Đặc tả giao thức/định dạng có thẩm quyền | Tuân theo charset bắt buộc hoặc quy tắc tự xác định của định dạng |
| 2 | Metadata được bên gửi công bố theo hợp đồng | Dùng charset ghi trong metadata sau khi kiểm tra cú pháp và phạm vi |
| 3 | Cấu hình tích hợp đã thống nhất | Dùng charset đã được cấu hình cho endpoint, đối tác hoặc nguồn cụ thể |
| 4 | BOM hoặc chữ ký định dạng | Dùng khi định dạng cho phép và không mâu thuẫn với metadata có thẩm quyền |
| 5 | Công cụ nhận diện encoding | Chỉ xem là gợi ý có xác suất, cần xác minh thêm |
| 6 | Hình thức hiển thị | Chỉ dùng để phát hiện triệu chứng, không dùng làm căn cứ quyết định |

Ví dụ, JSON trao đổi giữa các hệ thống có quy tắc UTF-8 trong RFC 8259; XML có thể khai báo encoding trong XML declaration và còn chịu quy tắc ưu tiên của giao thức vận chuyển. Một file CSV thông thường không có một charset phổ quát chỉ dựa vào phần mở rộng `.csv`; cần hợp đồng từ hệ thống xuất file hoặc metadata đi kèm.

Nếu metadata mâu thuẫn với BOM, không tự động chọn dấu hiệu “trông hợp lý hơn”. Kiểm tra đặc tả định dạng và quy tắc ưu tiên của nó. Nếu không thể giải quyết mâu thuẫn, từ chối xử lý hoặc yêu cầu nguồn gửi xác nhận.

## 3. Vì sao không thể luôn suy ra charset từ byte?

Một số charset có vùng byte trùng nhau. ASCII là ví dụ rõ ràng: byte `41 42 43` biểu diễn `ABC` trong UTF-8, ISO-8859-1 và nhiều charset khác. Chỉ nhìn byte không thể biết nguồn đã định dùng charset nào.

Ngay cả khi byte tạo thành UTF-8 hợp lệ, điều đó cũng chưa chứng minh UTF-8 là encoding ban đầu. Ví dụ:

| Byte | Giải mã UTF-8 | Giải mã ISO-8859-1 |
| --- | --- | --- |
| `43 61 66 C3 A9` | `Café` | `CafÃ©` |
| `41 42 43` | `ABC` | `ABC` |

Dãy `C3 A9` là UTF-8 hợp lệ cho `é`, nhưng cũng là hai byte hợp lệ của ISO-8859-1. Nếu bên tạo file chủ ý ghi hai ký tự `Ã` và `©` bằng Latin-1, decoder UTF-8 vẫn có thể đọc thành `é` mà không phát sinh lỗi.

Do đó:

- “Decode UTF-8 không lỗi” là bằng chứng byte hợp lệ theo UTF-8.
- Nó không phải bằng chứng tuyệt đối rằng bên tạo đã cam kết UTF-8.
- “Decode ra chữ dễ đọc” càng không phải bằng chứng về encoding đúng.
- Thử lần lượt nhiều charset rồi chọn kết quả có vẻ hợp lý là một heuristic, không phải xác minh hợp đồng.

Nếu không có đặc tả, metadata, cấu hình hoặc nguồn đáng tin cậy để xác định charset, hãy ghi nhận trạng thái chưa xác định thay vì tự chọn một charset.

## 4. BOM là dấu hiệu hữu ích nhưng không phải metadata vạn năng

Byte Order Mark là chuỗi byte ở đầu một số văn bản Unicode. BOM có thể giúp nhận diện encoding hoặc thứ tự byte, nhưng cách sử dụng phụ thuộc định dạng.

| BOM | Byte hex | Ý nghĩa thường gặp |
| --- | --- | --- |
| UTF-8 | `EF BB BF` | Dấu hiệu UTF-8 có BOM |
| UTF-16 big-endian | `FE FF` | UTF-16 BE |
| UTF-16 little-endian | `FF FE` | UTF-16 LE |
| UTF-32 big-endian | `00 00 FE FF` | UTF-32 BE |
| UTF-32 little-endian | `FF FE 00 00` | UTF-32 LE |

Khi tự kiểm tra BOM, thử mẫu UTF-32 trước mẫu UTF-16. BOM UTF-32 LE bắt đầu bằng `FF FE`, trùng hai byte đầu của BOM UTF-16 LE; nếu kiểm tra UTF-16 trước, chương trình có thể phân loại nhầm.

Một số điểm cần nhớ:

- UTF-8 không bắt buộc phải có BOM. Không có BOM không có nghĩa file không phải UTF-8.
- Một số giao thức cấm BOM; một số cho phép hoặc quy định cách xử lý riêng.
- BOM không thay thế metadata khi định dạng đã quy định nguồn charset khác.
- Không phải mọi API Java đều tự loại bỏ BOM trước nội dung.
- Chuỗi byte `FF FE` có thể là BOM UTF-16 LE, nhưng trong một định dạng khác nó có thể mang ý nghĩa khác; phải xét đúng ngữ cảnh.

Với UTF-8, decoder `StandardCharsets.UTF_8` giải mã BOM thành ký tự `U+FEFF` ở đầu chuỗi; nó không phải API tổng quát để tự động xóa BOM khỏi mọi định dạng. Nếu định dạng yêu cầu bỏ BOM, hãy nhận diện và bỏ đúng ba byte đầu trước khi decode, sau khi đã xác minh đó là BOM UTF-8 theo hợp đồng.

### 4.1. Kiểm tra BOM trên byte đầu vào

Ví dụ đọc một file nhỏ vào byte array và kiểm tra BOM UTF-8:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

byte[] bytes = Files.readAllBytes(Path.of("input.txt"));

boolean hasUtf8Bom =
        bytes.length >= 3
        && (bytes[0] & 0xFF) == 0xEF
        && (bytes[1] & 0xFF) == 0xBB
        && (bytes[2] & 0xFF) == 0xBF;

byte[] payload = hasUtf8Bom
        ? Arrays.copyOfRange(bytes, 3, bytes.length)
        : bytes;
```

Đây là ví dụ cho file có kích thước phù hợp với bộ nhớ. Với file lớn, hãy kiểm tra một prefix nhỏ qua `InputStream` hoặc `PushbackInputStream`, rồi tiếp tục streaming. Không dùng `readAllBytes()` cho file không giới hạn kích thước.

Không xóa ba byte đầu chỉ vì chúng “trông giống” BOM trong một payload nhị phân. Chỉ thực hiện bước này nếu định dạng văn bản cho phép BOM và encoding đã được xác định.

## 5. Metadata thường gặp trong các định dạng

Metadata có thể nằm ngoài payload hoặc bên trong nội dung. Hãy đọc metadata theo đúng đặc tả của định dạng.

| Nguồn | Metadata hoặc quy tắc cần kiểm tra |
| --- | --- |
| HTTP response | `Content-Type` và tham số `charset` nếu media type định nghĩa/sử dụng tham số đó; đặc tả riêng của media type |
| XML | XML declaration, BOM và quy tắc encoding của XML; đồng thời xét metadata tầng vận chuyển |
| JSON | Quy tắc encoding của JSON theo RFC 8259; JSON trao đổi giữa các hệ thống phải dùng UTF-8 |
| Database | Charset/collation của database, column type, driver và cấu hình kết nối |
| Message queue | Schema registry, message attributes, content type hoặc hợp đồng topic |
| File xuất từ ứng dụng | Cấu hình export, tài liệu sản phẩm hoặc metadata được gửi kèm |
| Properties | Hợp đồng riêng của API được dùng để đọc; không suy từ đuôi `.properties` |

Không phải mọi định dạng đều có trường `charset`. Nếu metadata không có, đặc tả có thể quy định encoding cố định. Ví dụ JSON hiện đại có quy tắc UTF-8 riêng; không cần đoán encoding từ terminal.

### 5.1. HTTP Content-Type

Một response có thể cung cấp metadata như:

```http
Content-Type: text/plain; charset=UTF-8
```

Nếu API server và client đã thống nhất charset, hãy đọc header bằng HTTP client và chuyển label charset sang `Charset` sau khi xác thực. Đừng tự parse header bằng cách tìm chuỗi con `charset=` trong một chuỗi bất kỳ; media type có quy tắc cú pháp, dấu nháy, khoảng trắng và tham số riêng.

Ví dụ sau giả định tầng HTTP đã cung cấp một charset label đã được tách và xác thực từ header:

```java
import java.nio.charset.Charset;

String charsetLabel = metadataCharset;
Charset charset = Charset.forName(charsetLabel);
String canonicalName = charset.name();

System.out.println(canonicalName);
```

`Charset.forName` có thể ném `IllegalCharsetNameException` hoặc `UnsupportedCharsetException`. Không âm thầm thay charset không hỗ trợ bằng default charset. Hãy trả lỗi cấu hình hoặc xử lý theo hợp đồng của endpoint.

### 5.2. XML và JSON

Với XML, không chỉ nhìn tên file `.xml`. Encoding có thể được khai báo trong XML declaration; BOM và metadata tầng vận chuyển cũng có thể tham gia theo quy tắc XML. Dùng XML parser tuân thủ đặc tả để xử lý encoding, thay vì tự cắt header rồi decode nội dung bằng một charset đoán được.

Với JSON theo RFC 8259, văn bản JSON được trao đổi giữa các hệ thống phải được mã hóa UTF-8. Nếu nhận JSON qua HTTP, vẫn cần tuân theo media type và hợp đồng API, nhưng không tự chọn Windows-1252 chỉ vì một terminal đang hiển thị ký tự sai.

## 6. JEP 400: UTF-8 mặc định không thay hợp đồng của payload

JEP 400 có hiệu lực từ Java 18 và đặt UTF-8 làm default charset thông thường cho Java SE. Những API thật sự dựa trên `Charset.defaultCharset()` chịu ảnh hưởng của thay đổi này.

Ví dụ các API dựa vào default charset:

```java
import java.nio.charset.Charset;

byte[] bytes = {0x41, 0x42, 0x43};
String text = "ABC";
String fromBytes = new String(bytes);
byte[] toBytes = text.getBytes();

System.out.println(Charset.defaultCharset());
```

Để tránh phụ thuộc default charset, dùng overload có charset:

```java
import java.nio.charset.StandardCharsets;

byte[] bytes = {0x41, 0x42, 0x43};
String text = "ABC";
String fromUtf8 = new String(bytes, StandardCharsets.UTF_8);
byte[] utf8Bytes = text.getBytes(StandardCharsets.UTF_8);
```

Tuy nhiên, phải dùng UTF-8 vì hợp đồng payload quy định UTF-8, không phải chỉ vì Java 18 chọn UTF-8 làm default.

Một số cấu hình tương thích của JDK có thể làm default charset khác UTF-8, chẳng hạn chế độ `COMPAT` được hỗ trợ qua `file.encoding`. Không nên đặt `file.encoding` trong ứng dụng để “sửa” một payload cụ thể. Hãy chọn charset tại API đọc/ghi dữ liệu đó.

### 6.1. API có hợp đồng charset riêng

Không thể suy luận charset của mọi API chỉ từ phiên bản Java:

| API | Charset khi không truyền charset |
| --- | --- |
| `Files.readString(path)` | UTF-8 theo hợp đồng Files API |
| `Files.newBufferedReader(path)` | UTF-8 theo hợp đồng Files API |
| `new String(bytes)` | Default charset của JVM |
| `text.getBytes()` | Default charset của JVM |
| `Properties.load(InputStream)` | ISO-8859-1 theo hợp đồng Properties |
| `PropertyResourceBundle(InputStream)` | UTF-8 trước; mặc định fallback ISO-8859-1 khi UTF-8 malformed/unmappable; `java.util.PropertyResourceBundle.encoding` có thể khóa một encoding |
| `new InputStreamReader(input)` | Default charset của JVM |

Ví dụ Properties cho thấy cùng một đuôi `.properties` nhưng API khác nhau có thể có hợp đồng byte khác nhau. Hãy xác định chính xác API đang được gọi, không dùng một quy tắc chung cho mọi file văn bản.

Với `PropertyResourceBundle(InputStream)`, system property `java.util.PropertyResourceBundle.encoding` được đọc khi lớp khởi tạo. Nếu cần cấu hình UTF-8 hoặc ISO-8859-1 cố định cho tiến trình, đặt property trước khi lớp được sử dụng; nếu mỗi file có encoding riêng, tạo `Reader` với charset tương ứng.

## 7. Xác thực charset label và chọn Charset trong Java

Sau khi lấy được label từ metadata hoặc cấu hình, chuyển nó thành đối tượng `Charset` một lần tại biên tiếp nhận:

```java
import java.nio.charset.Charset;

static Charset resolveCharset(String label) {
    if (label == null || label.isBlank()) {
        throw new IllegalArgumentException("Thiếu charset trong metadata");
    }

    return Charset.forName(label);
}

Charset payloadCharset = resolveCharset("UTF-8");
```

Một số điểm cần biết:

- `Charset.forName(label)` chấp nhận tên chuẩn và alias được provider hỗ trợ.
- `charset.name()` trả tên chuẩn tắc của đối tượng charset.
- `Charset.isSupported(label)` kiểm tra charset có được hỗ trợ hay không.
- `StandardCharsets.UTF_8`, `ISO_8859_1`, `US_ASCII` và các hằng số chuẩn khác luôn có sẵn trong Java.
- Tên không hợp lệ gây `IllegalCharsetNameException`; tên hợp lệ về cú pháp nhưng không được hỗ trợ gây `UnsupportedCharsetException`.

Không nên chuyển label lạ thành UTF-8 theo fallback ngầm. Nếu hợp đồng yêu cầu charset không có trong runtime, báo lỗi rõ ràng để cấu hình hoặc dependency được sửa.

### 7.1. Metadata thiếu hoặc mâu thuẫn

Có thể xây dựng một kết quả phân giải có trạng thái thay vì trả về một charset mặc định:

```java
import java.nio.charset.Charset;

record EncodingDecision(Charset charset, String source) {}

static EncodingDecision fromContract(Charset charset, String source) {
    if (charset == null || source == null || source.isBlank()) {
        throw new IllegalArgumentException("Thiếu charset hoặc nguồn xác nhận");
    }
    return new EncodingDecision(charset, source);
}
```

Ví dụ:

```java
import java.nio.charset.StandardCharsets;

EncodingDecision decision =
        fromContract(StandardCharsets.UTF_8, "HTTP API contract v2");

System.out.println(decision.charset().name());
System.out.println(decision.source());
```

Giữ lại nguồn xác nhận giúp truy vết vì sao payload được decode theo charset đó. Trong hệ thống thực tế, có thể ghi thêm endpoint, tên schema, phiên bản hợp đồng hoặc mã cấu hình; tránh log nội dung nhạy cảm của payload.

## 8. Decode nghiêm ngặt sau khi đã xác định charset

Sau khi biết charset, bước tiếp theo là quyết định chính sách cho byte không hợp lệ. Với dữ liệu cần chính xác, dùng `CharsetDecoder` và đặt cả malformed input lẫn unmappable character thành `REPORT`.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;

static String decodeStrict(byte[] bytes, Charset charset)
        throws CharacterCodingException {
    var decoder = charset.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    return decoder.decode(ByteBuffer.wrap(bytes)).toString();
}
```

Ví dụ dùng UTF-8 theo hợp đồng:

```java
import java.nio.charset.StandardCharsets;

String text = decodeStrict(payloadBytes, StandardCharsets.UTF_8);
```

Nếu byte không hợp lệ theo UTF-8, decoder ném `MalformedInputException` hoặc ngoại lệ chuyển mã tương ứng. Đây là tín hiệu dữ liệu không tuân thủ encoding đã chọn. Không bắt lỗi rồi thử lần lượt các charset khác trừ khi giao thức có quy định fallback cụ thể.

`new String(bytes, charset)` tiện lợi nhưng dùng hành vi thay thế cho byte malformed/unmappable; nó không cho cấu hình `CodingErrorAction.REPORT`. Khi cần từ chối dữ liệu lỗi, dùng decoder.

### 8.1. Streaming decode cho file lớn

Với file lớn, không cần đọc toàn bộ vào `byte[]`. Tạo `CharsetDecoder` nghiêm ngặt và bọc `InputStreamReader`:

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var reader = new BufferedReader(new InputStreamReader(
        Files.newInputStream(Path.of("large-input.txt")), decoder))) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

Decoder xử lý dữ liệu dần khi Reader đọc. Lỗi byte có thể chỉ xuất hiện ở một lần `read()` sau đó, nên ứng dụng phải xử lý `IOException` trong suốt vòng đời đọc chứ không chỉ lúc mở file.

Nếu nguồn là file UTF-8 và không cần tùy chỉnh `CodingErrorAction`, `Files.newBufferedReader(path, StandardCharsets.UTF_8)` là lựa chọn gọn hơn; hợp đồng của Files API cũng quy định lỗi khi gặp byte malformed hoặc unmappable.

## 9. Phân biệt lỗi decode với lỗi hiển thị

Một chuỗi hiển thị sai có thể đến từ nhiều tầng khác nhau:

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `Tiáº¿ng Viá»‡t` hoặc `cafÃ©` | Byte UTF-8 bị decode bằng charset khác | Kiểm tra byte gốc và charset ở điểm decode |
| `�` (U+FFFD) | Decoder đã thay byte malformed/unmappable | Decode lại byte gốc bằng decoder `REPORT` |
| Ô vuông hoặc ký hiệu thiếu glyph | Font/terminal không có glyph | In code point hoặc hiển thị trong font hỗ trợ |
| Ký tự đúng trong log file nhưng sai trên terminal | Charset của terminal/stdout khác với encoding file | Kiểm tra charset của output stream và terminal |
| Nội dung bị mất dấu sau khi lưu | Encoder đã thay hoặc bỏ ký tự không biểu diễn được | Kiểm tra charset đích và byte thực tế |

Phân biệt ba bước:

1. **Decode:** byte được ánh xạ thành chuỗi Java.
2. **Encode:** chuỗi Java được chuyển thành byte cho file/socket/terminal.
3. **Render:** terminal, font hoặc UI vẽ ký tự lên màn hình.

Nếu chuỗi Java đúng nhưng terminal thiếu glyph, đổi charset decode của file không giải quyết vấn đề. Nếu byte bị decode sai ngay từ đầu, đổi font cũng không sửa được chuỗi đã sai.

Từ Java 18, có thể truy vấn charset của từng `PrintStream` bằng `charset()`. Charset của `System.out`/`System.err` có thể khác `Charset.defaultCharset()`, vì luồng chuẩn có cấu hình encoding riêng:

```java
import java.nio.charset.Charset;

System.out.println("JVM default: " + Charset.defaultCharset());
System.out.println("stdout: " + System.out.charset());
System.out.println("stderr: " + System.err.charset());
```

Đây là thông tin về cách PrintStream mã hóa ký tự thành byte. Terminal hoặc UI bên ngoài vẫn cần giải mã và render byte đó đúng cách.

### 9.1. Kiểm tra code point thay vì chỉ nhìn chữ

Có thể in code point của chuỗi để biết Java đang giữ ký tự nào:

```java
String value = "Tiếng Việt";

value.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

Nếu kết quả là các code point mong đợi nhưng terminal vẫn hiển thị ô vuông, kiểm tra font/rendering. Nếu code point đã thành `U+FFFD` hoặc dãy ký tự mojibake, lỗi xảy ra trước bước render.

Không dùng ảnh chụp terminal làm bằng chứng duy nhất cho charset. Hãy kiểm tra byte gốc, code point và hợp đồng encoding.

## 10. Công cụ nhận diện charset: chỉ là heuristic

Khi file không có metadata, một công cụ nhận diện encoding có thể đề xuất charset dựa trên thống kê byte, mẫu ngôn ngữ hoặc mô hình xác suất. Kết quả thường có mức confidence, không phải chứng minh toán học.

Giới hạn của nhận diện tự động:

- ASCII giống nhau trong nhiều charset.
- Một dãy byte có thể hợp lệ trong nhiều charset.
- File ngắn không đủ dữ liệu thống kê.
- Nội dung ngôn ngữ hiếm hoặc hỗn hợp làm giảm độ tin cậy.
- File có thể chứa nhiều đoạn được tạo từ các nguồn khác nhau.
- Một số charset đơn byte có thể giải mã hầu như mọi byte nên không phát sinh lỗi.

Nếu buộc phải dùng detector:

1. Lấy mẫu đủ lớn và đại diện, không chỉ vài byte đầu.
2. Kiểm tra BOM và metadata trước.
3. Dùng detector để lập danh sách ứng viên, không tự động coi ứng viên đầu tiên là đúng.
4. Xác minh bằng cấu trúc định dạng, schema, checksum hoặc đối chiếu với bên tạo.
5. Ghi lại charset đã chọn và lý do lựa chọn.
6. Nếu độ tin cậy thấp hoặc ứng viên mâu thuẫn, yêu cầu xác nhận thay vì âm thầm decode.

Không có một API chuẩn trong Java SE có thể xác định chính xác charset của mọi mảng byte tùy ý. `Charset.availableCharsets()` liệt kê charset được hỗ trợ; nó không nhận diện charset của một payload.

## 11. Ví dụ thực tế: xử lý file được đối tác gửi

Giả sử đối tác gửi `daily-export.csv` cùng metadata trong cấu hình tích hợp. Hợp đồng quy định UTF-8. Không suy charset từ đuôi `.csv` hoặc từ việc Excel hiển thị đúng/sai.

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("daily-export.csv");

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (BufferedReader reader = new BufferedReader(new InputStreamReader(
        Files.newInputStream(file), decoder))) {
    String line;
    while ((line = reader.readLine()) != null) {
        processCsvRecord(line);
    }
}
```

Nếu cần decoder strict tùy chỉnh, dùng `InputStreamReader` như phần 8.1. Nếu file chứa BOM UTF-8 và quy ước của đối tác yêu cầu loại bỏ BOM, xử lý BOM ở tầng byte trước khi đưa phần payload cho decoder.

Khi decoder báo lỗi, ghi nhận file, nguồn gửi, charset theo hợp đồng và vị trí xử lý. Yêu cầu đối tác gửi lại hoặc sửa quy trình export. Không thử Windows-1252, ISO-8859-1, UTF-16 cho đến khi một cách hiển thị “đẹp” xuất hiện.

## 12. Ví dụ thực tế: kiểm tra metadata HTTP trước khi decode

Giả sử tầng HTTP client đã đọc response header và xác định charset label theo hợp đồng API. Phần dưới đây chỉ minh họa bước chọn charset và decode; việc parse header phải do HTTP client hoặc media type parser phù hợp đảm nhiệm.

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

static Charset charsetForResponse(String declaredCharset) {
    if (declaredCharset == null || declaredCharset.isBlank()) {
        // Chính sách này chỉ đúng nếu hợp đồng endpoint quy định UTF-8
        // khi thiếu charset; không dùng như fallback chung cho mọi HTTP.
        return StandardCharsets.UTF_8;
    }
    return Charset.forName(declaredCharset);
}
```

Nếu endpoint quy định UTF-8 khi header không có charset, có thể dùng chính sách đó. Nếu endpoint không quy định, việc thiếu metadata phải được xử lý theo media type và hợp đồng cụ thể; không tự động lấy `Charset.defaultCharset()`.

Khi charset label không hợp lệ hoặc không được hỗ trợ, trả lỗi tích hợp rõ ràng. Không decode bằng charset mặc định rồi tiếp tục xử lý dữ liệu sai.

## 13. Kiểm thử tính nhất quán của encoding

Một kiểm thử tốt nên xác minh nhiều lớp độc lập:

- Charset được chọn đúng theo hợp đồng.
- Byte đầu vào hợp lệ theo charset đã chọn.
- Nội dung Unicode sau decode khớp dữ liệu mong đợi.
- Byte đầu ra sau encode khớp encoding được công bố.
- Metadata, BOM và định dạng không mâu thuẫn.

Ví dụ kiểm tra UTF-8 bằng byte và strict decoder. Đoạn code giả sử hàm `decodeStrict` ở mục 8 đã được khai báo:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String expected = "Café - Tiếng Việt 🌍";
byte[] bytes = expected.getBytes(StandardCharsets.UTF_8);

String decoded = decodeStrict(bytes, StandardCharsets.UTF_8);

if (!expected.equals(decoded)) {
    throw new AssertionError("Decoded content differs");
}

byte[] encodedAgain = decoded.getBytes(StandardCharsets.UTF_8);
if (!Arrays.equals(bytes, encodedAgain)) {
    throw new AssertionError("UTF-8 bytes differ");
}
```

Round-trip là kiểm tra hữu ích, nhưng không thay thế metadata. Nếu cả encode và decode đều dùng cùng charset sai, round-trip vẫn có thể thành công. Vì vậy, phải đối chiếu byte với hợp đồng hoặc fixture độc lập đã biết.

### 13.1. Ma trận kiểm thử nên có

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| ASCII thuần | Không kết luận charset chỉ từ kết quả giống nhau |
| UTF-8 có tiếng Việt/emoji | Decode strict đúng UTF-8 |
| UTF-8 malformed | Decoder `REPORT` từ chối |
| UTF-8 có BOM | Xử lý BOM theo định dạng, không để U+FEFF thành dữ liệu ngoài ý muốn |
| UTF-16 có BOM | Tôn trọng BOM và quy tắc của định dạng |
| Metadata và BOM mâu thuẫn | Dừng và áp dụng quy tắc ưu tiên đã công bố |
| Charset label không hỗ trợ | Báo lỗi cấu hình, không fallback âm thầm |
| Byte Latin-1 vô tình hợp lệ UTF-8 | Xác minh bằng hợp đồng, không chỉ dựa trên decode thành công |
| Terminal thiếu glyph | Phân biệt lỗi render với lỗi decode |

## 14. Lưu lại quyết định encoding để truy vết

Trong hệ thống tích hợp, việc chỉ lưu nội dung `String` sau decode có thể làm mất thông tin về nguồn gốc encoding. Khi cần điều tra sự cố, nên lưu metadata an toàn về quyết định giải mã:

- Nguồn hoặc loại payload.
- Charset đã chọn và tên chuẩn tắc (`charset.name()`).
- Nguồn quyết định: protocol, header, file format, config hoặc BOM.
- Phiên bản hợp đồng/schema.
- Kết quả validation (strict decode thành công hay lỗi).
- Có BOM hay không, nếu định dạng cần theo dõi.

Không nhất thiết lưu payload thô nếu dữ liệu nhạy cảm. Có thể lưu hash, kích thước byte, mã lỗi và thông tin nguồn để đối chiếu. Nếu cần lưu raw payload cho điều tra, áp dụng chính sách bảo mật và retention của hệ thống.

Một kiểu dữ liệu nhỏ có thể giúp code không đánh mất nguồn quyết định:

```java
import java.nio.charset.Charset;

record DecodingContext(
        Charset charset,
        String source,
        String contractVersion,
        boolean hadBom) {
}
```

Truyền context cùng luồng xử lý giúp log và telemetry ghi nhận cùng một quyết định, thay vì mỗi tầng tự chọn charset riêng.

## 15. Những nhận định dễ nhầm

- **“Java 18 mặc định UTF-8 nên mọi payload đều là UTF-8.”** Sai. Default charset JVM không thay hợp đồng của file, protocol hoặc API.
- **“Decode UTF-8 không lỗi chứng minh nguồn đã gửi UTF-8.”** Sai. Một số byte hợp lệ trong nhiều charset; cần metadata hoặc hợp đồng.
- **“Không có BOM nghĩa là không phải UTF-8.”** Sai. UTF-8 không bắt buộc BOM.
- **“Có BOM thì luôn bỏ ba byte đầu.”** Sai. BOM có thể thuộc quy tắc định dạng; phải xác định encoding và quy tắc xử lý trước.
- **“Chuỗi hiển thị đẹp nhất là charset đúng.”** Sai. Một charset sai có thể tạo chuỗi trông hợp lý; hiển thị chỉ là dấu hiệu điều tra.
- **“Ký tự ô vuông luôn do decode sai.”** Sai. Có thể font hoặc terminal thiếu glyph.
- **“Charset detector trả confidence cao là kết luận chắc chắn.”** Sai. Đây vẫn là nhận diện xác suất, đặc biệt với dữ liệu ngắn hoặc ASCII.
- **“Round-trip thành công chứng minh encoding ban đầu đúng.”** Sai. Encode và decode cùng một charset sai vẫn có thể tạo round-trip nhất quán.
- **“Thiếu charset metadata thì dùng default charset của máy.”** Không an toàn. Hãy theo đặc tả media type hoặc yêu cầu nguồn xác nhận.
- **“Có thể dùng một charset fallback cho mọi file.”** Sai. Fallback phải được quy định bởi định dạng/API cụ thể; không áp dụng tùy tiện.

## 16. Tài liệu tham khảo chính thức

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi default charset từ Java 18 và chế độ tương thích.
- [Charset — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/Charset.html): tên charset, alias, `defaultCharset()`, `forName()` và charset được hỗ trợ.
- [CharsetDecoder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html): giải mã byte và chính sách malformed/unmappable.
- [StandardCharsets — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset chuẩn của Java.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): quy tắc UTF-8 và xử lý BOM cho JSON được trao đổi giữa các hệ thống.
- [XML 1.0 — Encoding Declaration](https://www.w3.org/TR/xml/#charencoding): quy tắc xác định encoding của XML.
- [Files — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): các API đọc file có charset tường minh.

