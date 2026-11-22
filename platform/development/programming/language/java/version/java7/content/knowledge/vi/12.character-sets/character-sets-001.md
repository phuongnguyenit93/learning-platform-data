# Java 7 — Bảng mã: Vai trò của StandardCharsets trong xử lý văn bản

## 1. Vì sao cần StandardCharsets?

Văn bản trong chương trình Java là `String`, nhưng file, gói tin mạng và nhiều API bên ngoài truyền **byte**. Muốn chuyển giữa hai dạng này, chương trình phải chọn đúng **charset (bảng mã ký tự)**. Nếu phía ghi dùng UTF-8 nhưng phía đọc giải mã theo một charset khác, văn bản tiếng Việt có thể bị hiển thị sai, mất dấu hoặc biến thành ký tự thay thế.

Từ **Java 7**, `java.nio.charset.StandardCharsets` cung cấp những hằng `Charset` được bảo đảm có sẵn trên nền tảng Java. Thay vì phụ thuộc charset mặc định của máy hay một tên charset viết bằng chuỗi, ta có thể chỉ rõ:

```java
byte[] data = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(data, StandardCharsets.UTF_8);
```

Đây là **hai dòng minh họa trong một phương thức**, cần có biến `String text` và import `java.nio.charset.StandardCharsets`. Dòng đầu là **encode** (ký tự → byte); dòng sau là **decode** (byte → ký tự). Cả hai đầu dùng cùng charset, vì vậy văn bản hợp lệ được khôi phục chính xác.

**Giá trị của StandardCharsets** là sự rõ ràng và khả năng tái lập: source code thể hiện hợp đồng byte của dữ liệu, không phải “đoán encoding dựa theo máy”. Class này vẫn hữu ích trên JDK 17+; kiến thức bài học không yêu cầu chạy JDK 7 đã cũ.

## 2. Unicode, Java String, UTF-8 và charset là các khái niệm khác nhau

- **Unicode code point** là giá trị định danh ký tự, ví dụ `U+00E0` cho “à”, `U+2615` cho “☕”.
- **String trong Java** có ngữ nghĩa dãy UTF-16 code units; ký tự Unicode ngoài BMP có thể chiếm **hai `char`**. Điều này không có nghĩa Java luôn xuất byte UTF-16 khi ghi file.
- **Charset** định nghĩa phép chuyển đổi giữa chuỗi ký tự và byte. `UTF-8`, `UTF-16`, `ISO-8859-1` và `US-ASCII` là các charset khác nhau.
- **Encoding** biến String thành byte. **Decoding** biến byte thành String. Charset phải phù hợp với định dạng dữ liệu thực tế.

```text
String Java
   │ encode với StandardCharsets.UTF_8
   ▼
byte[]  ───── ghi file / gửi HTTP / truyền qua mạng ─────► byte[]
                                                           │ decode UTF-8
                                                           ▼
                                                        String Java
```

Chẳng hạn ký tự “à” được mã hóa bằng UTF-8 thành `C3 A0`, còn ISO-8859-1 thành `E0`. Nếu hai byte UTF-8 được giải mã như ISO-8859-1, có thể xuất hiện “Ã” và một ký tự khoảng trắng đặc biệt thay vì “à”. Đây là **lỗi charset**, không thể sửa chắc chắn bằng đổi font.

`String.length()` đo số UTF-16 code units, **không phải số byte UTF-8 hay số Unicode code points**. Một ký tự có thể cần nhiều byte tùy charset.

## 3. Các hằng charset chuẩn và phạm vi phiên bản

Trên **Java 17**, có sáu hằng `Charset` trong `StandardCharsets`:

| Hằng | Ý nghĩa | Trường hợp sử dụng |
| --- | --- | --- |
| `UTF_8` | Unicode dưới dạng UTF-8 | **Ưu tiên cho văn bản mới** khi không có ràng buộc khác |
| `UTF_16` | UTF-16 có quy tắc BOM/byte order | File hoặc giao thức quy định UTF-16 |
| `UTF_16BE` | UTF-16 big-endian | Định dạng quy định thứ tự byte BE |
| `UTF_16LE` | UTF-16 little-endian | Định dạng quy định thứ tự byte LE |
| `ISO_8859_1` | Latin-1, biểu diễn U+0000..U+00FF | Dữ liệu cũ hoặc giao thức thực sự dùng Latin-1 |
| `US_ASCII` | ASCII 7-bit | Định dạng chỉ cho phép ASCII |

Dùng `StandardCharsets.UTF_8` thay vì một chuỗi ngẫu nhiên giúp tránh lỗi gõ tên và không phải xử lý tình huống Java không hỗ trợ UTF-8. Trong JDK 17, tất cả sáu charset trên đều được bảo đảm có sẵn.

**Ghi chú cập nhật:** Từ **JDK 22**, `StandardCharsets` bổ sung `UTF_32`, `UTF_32BE` và `UTF_32LE`. Đây là API có thật trên JDK mới, nhưng **không dùng trực tiếp trong code biên dịch bằng `--release 17`**. Cần phân biệt “API hiện hành” với “API đã có trong target release”.

`StandardCharsets` **không tự nhận diện** charset từ byte. Nó chỉ cung cấp các hằng để chương trình dùng charset đã biết theo đặc tả file, protocol hoặc cấu hình đáng tin.

## 4. UTF-8 là lựa chọn thường dùng nhưng phải hiểu charset mặc định

Với dữ liệu Unicode mới, UTF-8 có nhiều ưu điểm: tương thích byte ASCII cơ bản, biểu diễn đầy đủ Unicode, được dùng rộng rãi trong trao đổi dữ liệu. Hãy dùng UTF-8 nếu hệ thống không yêu cầu charset khác.

Tuy nhiên, đừng hiểu nhầm các quy tắc default:

- **JDK 17 trở xuống:** `Charset.defaultCharset()` thường phụ thuộc môi trường, locale hoặc hệ điều hành.
- **JDK 18 trở đi:** JEP 400 đặt UTF-8 thành **charset mặc định của các Java SE API phụ thuộc default charset**. Có trường hợp chạy theo cấu hình tương thích hoặc thiết lập riêng.
- Một số API, ví dụ `Files.readString(path)` và `Files.writeString(path,text)` từ JDK 11, **đã được đặc tả dùng UTF-8** khi không truyền Charset, không phải lấy charset mặc định.
- Không suy luận mọi terminal, console, driver, database hoặc giao thức mạng đều tự dùng UTF-8. Các ranh giới đó có hợp đồng riêng.

Hai ví dụ sau **không có lời hứa giống nhau**:

```java
byte[] explicit = text.getBytes(StandardCharsets.UTF_8);
byte[] implicit = text.getBytes(); // Charset mặc định của runtime.
```

Đây là snippet trong phương thức có `String text`. Với file và protocol được quy định UTF-8, ưu tiên bản `explicit`. Thay đổi default charset có thể gây lỗi khó tái hiện nếu phụ thuộc `getBytes()`, `new String(bytes)` hoặc `new InputStreamReader(in)` không nhận charset.

Không phải lúc nào dùng `Charset.defaultCharset()` cũng sai: nó hợp lý cho code **cố ý thao tác theo encoding của môi trường** hoặc diagnostic. Nhưng nó không thay thế được metadata về charset của dữ liệu ngoài.

## 5. Chương trình Java 17+ đầy đủ và đầu ra chính xác

Chương trình dùng `HexFormat` (có từ Java 17) để hiển thị bytes dưới dạng hex, không phụ thuộc font của terminal. Nó kiểm tra encode/decode UTF-8, Latin-1, ASCII, BOM UTF-16, cách xử lý byte lỗi và round-trip qua file tạm.

Tạo file **`StandardCharsetsDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;
import java.util.Locale;

public class StandardCharsetsDemo {
    public static void main(String[] args) throws Exception {
        String text = "Ch\u00E0o \u2615";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 bytes = " +
                HexFormat.of().formatHex(utf8));
        System.out.println("UTF-8 round-trip = " +
                text.equals(new String(utf8, StandardCharsets.UTF_8)));

        System.out.println("Latin-1 bytes = " +
                HexFormat.of().formatHex(
                        "caf\u00E9".getBytes(StandardCharsets.ISO_8859_1)));
        System.out.println("ASCII fallback = " +
                HexFormat.of().formatHex(
                        "caf\u00E9".getBytes(StandardCharsets.US_ASCII)));
        System.out.println("UTF-16 bytes = " +
                HexFormat.of().formatHex(
                        "A".getBytes(StandardCharsets.UTF_16)));

        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
        String lenient = new String(invalidUtf8, StandardCharsets.UTF_8);
        System.out.println("Lenient first = U+" +
                String.format(Locale.ROOT, "%04X", lenient.codePointAt(0)));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8));
        } catch (CharacterCodingException ex) {
            System.out.println("Strict error = " +
                    ex.getClass().getSimpleName());
        }

        Path temp = Files.createTempFile("standard-charsets-demo-", ".txt");
        try {
            Files.writeString(temp, text, StandardCharsets.UTF_8);
            String loaded = Files.readString(temp, StandardCharsets.UTF_8);
            System.out.println("File round-trip = " + text.equals(loaded));
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StandardCharsetsDemo.java
java StandardCharsetsDemo
```

**Stdout chính xác:**

```text
UTF-8 bytes = 4368c3a06f20e29895
UTF-8 round-trip = true
Latin-1 bytes = 636166e9
ASCII fallback = 6361663f
UTF-16 bytes = feff0041
Lenient first = U+FFFD
Strict error = MalformedInputException
File round-trip = true
```

**Giải thích:**

1. `"Ch\u00E0o \u2615"` là “Chào ☕”. “à” thành `C3 A0`, “☕” thành `E2 98 95` trong UTF-8. Dãy byte toàn chuỗi là `4368c3a06f20e29895`.
2. Round-trip sử dụng cùng `UTF_8` nên `text.equals(restored)` trả true.
3. “é” là `E9` trong ISO-8859-1 nhưng **không biểu diễn được trong US-ASCII**; overload `getBytes(Charset)` dùng byte thay thế, nên `caf?` thành `6361663f`.
4. `UTF_16` khi encode “A” dùng big-endian kèm BOM `FE FF`, tạo `FE FF 00 41`.
5. `C3 28` không phải chuỗi UTF-8 hợp lệ. Constructor `String(byte[], UTF_8)` thay phần sai bằng U+FFFD, còn strict decoder với `REPORT` ném `MalformedInputException`.
6. Đọc/ghi file tạm với cùng UTF-8 thành công. Khối `finally` dọn file. Trong ứng dụng thật phải xử lý `IOException` theo hợp đồng; `throws Exception` ở `main` chỉ để gọn cho chương trình demo.

Dùng Java 17 trở lên để chạy code trên. Những phần cốt lõi của `StandardCharsets` có từ Java 7, còn `HexFormat` và `Files.readString/writeString` là API mới hơn và đều phù hợp JDK 17+.

## 6. Đọc và ghi file văn bản đúng charset

### 6.1. File nhỏ: Files.readString / Files.writeString

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("notes.txt");
Files.writeString(path, "Nội dung tiếng Việt", StandardCharsets.UTF_8);
String contents = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là snippet Java 17+ trong phương thức có xử lý `IOException`. Với file lớn, cần tránh nạp toàn bộ nội dung vào RAM. API này không tự bảo đảm thao tác ghi là giao dịch nguyên tử; nếu đang tạo file cấu hình quan trọng, cần thiết kế xử lý lỗi và ghi an toàn riêng.

### 6.2. File lớn: newBufferedReader/newBufferedWriter

```java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

Đây là snippet trong phương thức có `Path path`, phương thức `process`, imports và xử lý `IOException`. `var` có từ Java 10. TWR đóng reader dù gặp lỗi. Với ghi nhiều dòng:

```java
try (var writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Dòng 1");
    writer.newLine();
    writer.write("Dòng 2");
}
```

Đoạn này cũng cần có `Path path` và xử lý IOException. Việc truyền charset tường minh đặc biệt quan trọng khi file phải được đọc ở nhiều hệ điều hành hoặc dịch vụ khác nhau.

### 6.3. Đổi byte stream thành character stream

```java
Reader reader = new InputStreamReader(inputStream, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_8);
```

Đây là snippet có `InputStream inputStream`, `OutputStream outputStream` và import `java.io.*`. Wrapper chuyển đổi byte ↔ ký tự; đóng reader/writer cũng có thể đóng stream bên dưới, nên cần xác định **ai sở hữu stream**. Nếu caller vẫn cần dùng stream sau phương thức, không đóng nó tùy tiện.

Với file/protocol Unicode mới, không nên chọn các overload `new InputStreamReader(in)` hoặc `new OutputStreamWriter(out)` không truyền charset khi yêu cầu thực sự là UTF-8.

## 7. Chọn đúng API; không phải overload nào cũng có cùng mặc định

| API | Khi không truyền Charset | Khi yêu cầu UTF-8 tường minh |
| --- | --- | --- |
| `text.getBytes()` | Dùng charset mặc định của runtime | `text.getBytes(StandardCharsets.UTF_8)` |
| `new String(bytes)` | Dùng charset mặc định của runtime | `new String(bytes, StandardCharsets.UTF_8)` |
| `new InputStreamReader(in)` | Dùng default charset | `new InputStreamReader(in, StandardCharsets.UTF_8)` |
| `new OutputStreamWriter(out)` | Dùng default charset | `new OutputStreamWriter(out, StandardCharsets.UTF_8)` |
| `Files.readString(path)` | **UTF-8 theo đặc tả API Java 11+** | `Files.readString(path, StandardCharsets.UTF_8)` |
| `Files.writeString(path, text)` | **UTF-8 theo đặc tả API Java 11+** | `Files.writeString(path, text, StandardCharsets.UTF_8)` |
| `Files.newBufferedReader(path)` | **UTF-8 theo đặc tả API** | `Files.newBufferedReader(path, StandardCharsets.UTF_8)` |

Đừng ghi quy tắc “mọi API Java đều phụ thuộc `Charset.defaultCharset()`” hoặc “mọi API Java đều luôn UTF-8”; cả hai đều sai nếu không xét chính overload và phiên bản JDK.

## 8. Thay thế ký tự hay từ chối dữ liệu không hợp lệ?

Overload tiện lợi của `String`:

```java
String decoded = new String(bytes, StandardCharsets.UTF_8);
byte[] encoded = decoded.getBytes(StandardCharsets.US_ASCII);
```

là snippet trong phương thức có `byte[] bytes`. Theo Javadoc, cả decode lẫn encode với overload nhận `Charset` này có thể **thay dữ liệu malformed/unmappable** bằng ký tự/byte thay thế mặc định. Nếu dùng cho xác thực nội dung hoặc định dạng yêu cầu chính xác tuyệt đối, thay thế thầm lặng có thể che lỗi.

### 8.1. Giải mã UTF-8 nghiêm ngặt

```java
static String strictUtf8(byte[] source)
        throws java.nio.charset.CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(java.nio.ByteBuffer.wrap(source))
            .toString();
}
```

Đây là phương thức minh họa trong class có import `StandardCharsets` và `CodingErrorAction`. Với byte sai UTF-8, decoder có thể ném `MalformedInputException`. Dùng `REPORT` khi một payload/configuration bắt buộc là UTF-8 hợp lệ. Không dùng `IGNORE` chỉ để ứng dụng tiếp tục chạy nếu không có yêu cầu nghiệp vụ rõ.

### 8.2. Mã hóa nghiêm ngặt nếu đích không biểu diễn được ký tự

```java
static java.nio.ByteBuffer strictEncode(
        String text, java.nio.charset.Charset charset)
        throws java.nio.charset.CharacterCodingException {
    return charset.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(java.nio.CharBuffer.wrap(text));
}
```

Đây là phương thức minh họa dùng `CodingErrorAction` trong một class. Nếu encode “é” bằng US-ASCII, lựa chọn REPORT báo `UnmappableCharacterException` thay vì âm thầm biến thành dấu hỏi. Kết quả là `ByteBuffer`; dữ liệu hợp lệ nằm giữa `position` và `limit`, không mặc định mọi byte trong capacity đều là payload.

**Phân biệt:** `malformed` là byte/code unit không hợp lệ theo quy tắc charset; `unmappable` là ký tự hợp lệ nhưng charset đích không có cách biểu diễn. `Charset` là immutable và dùng chung an toàn; `CharsetDecoder/Encoder` có trạng thái, không nên chia sẻ đồng thời giữa nhiều luồng.

## 9. UTF-16, byte order và BOM

Chữ “UTF-16” cần được hiểu kèm thứ tự byte (*endianness*), vì mỗi UTF-16 code unit gồm hai byte.

- `StandardCharsets.UTF_16` khi encode dùng **big-endian** và ghi **BOM `FE FF`**. Khi decode, nó nhận biết BOM nếu có và mặc định big-endian nếu không có.
- `StandardCharsets.UTF_16BE` dùng big-endian cố định và không tự tạo BOM khi encode.
- `StandardCharsets.UTF_16LE` dùng little-endian cố định và không tự tạo BOM khi encode.

Ví dụ “A” (U+0041):

| Charset | Hex khi encode |
| --- | --- |
| `UTF_8` | `41` |
| `UTF_16` | `FE FF 00 41` |
| `UTF_16BE` | `00 41` |
| `UTF_16LE` | `41 00` |

**BOM không phải yêu cầu chung của mọi file Unicode.** UTF-8 thường không cần BOM. Nếu file UTF-8 có ba byte đầu `EF BB BF`, không mặc định tất cả reader sẽ tự loại bỏ chúng; có thể chúng được giải mã thành ký tự `U+FEFF` ở đầu chuỗi. Khi dữ liệu có thể mang BOM, hãy quy định và kiểm thử chính sách chấp nhận/bỏ BOM.

Không được nhầm việc Java `String` có ngữ nghĩa UTF-16 với việc file cần ghi UTF-16. Nếu giao thức quy định UTF-8, dùng `UTF_8` dù Java sử dụng UTF-16 code units trong API ký tự.

## 10. ISO-8859-1, US-ASCII và các charset khác

**ISO-8859-1** biểu diễn một tập ký tự Latin-1 giới hạn. Nó phù hợp khi tệp/giao thức **thật sự được mã hóa ISO-8859-1**, không phù hợp với phần lớn văn bản Unicode/tiếng Việt hiện đại.

**US-ASCII** chỉ biểu diễn 7-bit. Nó hợp lý cho giao thức chỉ cho phép ASCII, chẳng hạn một số định danh kỹ thuật. Nếu nhận văn bản tự do của người dùng, nên validate thay vì âm thầm chuyển ký tự ngoài ASCII thành dấu hỏi.

**Windows-1252 không phải ISO-8859-1**, dù có nhiều byte giống nhau. Nếu dữ liệu từ đối tác yêu cầu charset khác sáu hằng trên:

```java
java.nio.charset.Charset sourceCharset =
        java.nio.charset.Charset.forName("windows-1252");
String content = new String(bytes, sourceCharset);
```

Đây là snippet trong phương thức có `byte[] bytes`. `Charset.forName(name)` có thể ném `IllegalCharsetNameException` hoặc `UnsupportedCharsetException` nếu tên không hợp lệ/không được hỗ trợ. Dùng khi charset thực sự do định dạng bên ngoài quyết định; không thay `StandardCharsets.UTF_8` bằng `Charset.forName("UTF-8")` không cần thiết.

Không áp đặt UTF-8 cho file cũ đã xác nhận dùng charset khác rồi kết luận file hỏng khi giải mã sai.

## 11. Charset trong HTTP, JSON, CSV và JDBC

**HTTP và API:** charset phải tuân theo tiêu chuẩn media type và hợp đồng endpoint. Một payload JSON mới thường dùng UTF-8; code nên làm rõ byte khi tạo body:

```java
String json = "{\"message\":\"Xin chào\"}";
byte[] body = json.getBytes(StandardCharsets.UTF_8);
```

Đây là snippet minh họa. Nó không phải JSON serializer hoàn chỉnh; với dữ liệu thực tế, hãy dùng thư viện JSON để escape/serialize đúng. Charset của dữ liệu không thể thay thế kiểm tra header, content type và schema.

**CSV:** CSV mô tả cách phân tách dòng/cột, không tự bảo đảm charset. Cần biết đối tác xuất CSV bằng UTF-8, UTF-16 hay encoding khác trước khi parse.

**JDBC:** driver và cấu hình database thường xử lý ánh xạ Java `String` sang cột text. Không tự đổi String thành byte rồi nhét vào cột văn bản nếu không có lý do thuộc hợp đồng binary; `StandardCharsets.UTF_8` không tự sửa sai charset/collation của DB.

**Console/log:** nếu byte round-trip đúng mà terminal hiển thị lỗi, hãy xem cấu hình console/font/encoding riêng. Không thay đổi byte của giao thức chỉ để một terminal hiển thị vừa mắt.

## 12. Xác định và sửa lỗi chữ có dấu bị hỏng (mojibake)

Triệu chứng như “ChÃ o”, ký tự thay thế `�` hoặc dấu hỏi có thể do chọn sai charset, hoặc do dữ liệu **đã bị thay đổi không thể phục hồi** từ một bước trước.

Quy trình debug:

1. **Tìm ranh giới đầu tiên bị sai**: String trước encode, byte trong file, byte khi nhận, String sau decode hay UI.
2. **Xem byte thực tế ở dạng hex** trong môi trường test an toàn. Không log toàn bộ dữ liệu cá nhân/bí mật trên production.
3. **Tìm charset thật** từ metadata/giao thức/đối tác; đừng lấy charset mặc định của máy làm bằng chứng.
4. **Decode từ byte gốc bằng charset đúng**, kiểm tra kết quả với mẫu đã biết.
5. **Kiểm tra quá trình chuyển đổi lặp**: có hệ thống decode sai rồi encode lại kết quả sai thành UTF-8; khi đó bytes mới vẫn có thể là UTF-8 hợp lệ nhưng nội dung vẫn hỏng.
6. **Kiểm tra replacement**: nếu ký tự gốc đã biến thành `?` hoặc U+FFFD ở bước trước, đổi charset sau đó không đảm bảo khôi phục được.
7. **Thêm test hồi quy** với tiếng Việt, ký tự ngoài BMP, dữ liệu malformed, file có BOM và file không BOM.

Dùng strict decoder với `REPORT` giúp phát hiện byte UTF-8 không hợp lệ từ sớm. Nhưng **UTF-8 hợp lệ không có nghĩa dữ liệu đã được kiểm tra bảo mật, Unicode normalized hay phù hợp schema**. Những việc đó cần validation riêng.

## 13. Checklist để review code xử lý văn bản

- [ ] Xác định nơi chuyển giữa `String` và `byte[]`.
- [ ] Charset lấy từ **hợp đồng dữ liệu**, không suy đoán theo máy.
- [ ] Dữ liệu mới dùng UTF-8 khi không có ràng buộc khác.
- [ ] Các lời gọi `getBytes`, constructor `String`, reader/writer truyền charset rõ ràng nếu cần.
- [ ] Phân biệt API default UTF-8 với API dùng `Charset.defaultCharset()`.
- [ ] Đọc/ghi file lớn bằng buffered stream/reader thay vì luôn nạp hết file vào RAM.
- [ ] Đóng tài nguyên bằng try-with-resources và xử lý `IOException`.
- [ ] Kiểm tra malformed/unmappable; quyết định `REPORT` hay `REPLACE` có chủ đích.
- [ ] Không dùng US-ASCII hoặc Latin-1 nếu cần giữ đầy đủ tiếng Việt/Unicode.
- [ ] Với UTF-16, xác định rõ BOM, BE/LE và test byte thực tế.
- [ ] Nếu đầu vào có thể có UTF-8 BOM, quyết định cách xử lý và test rõ.
- [ ] Xem quyền truy cập file, giới hạn kích thước dữ liệu và schema ngoài việc chọn charset.
- [ ] Test round-trip và so sánh hex thay vì dựa riêng vào console hiển thị.
- [ ] Kiểm tra JDK mục tiêu: StandardCharsets từ Java 7, `Files.readString` từ Java 11, `HexFormat` từ Java 17, UTF-32 constants từ JDK 22.

## 14. Các hiểu lầm và lỗi phổ biến

**“StandardCharsets tự đoán file dùng encoding gì.”** Sai. Nó cung cấp charset có sẵn, không có cơ chế nhận diện encoding tin cậy từ byte tùy ý.

**“Từ JDK 18 không cần truyền charset nữa.”** Sai với API/giao thức bên ngoài. Default UTF-8 giúp giảm khác biệt môi trường nhưng hợp đồng dữ liệu vẫn nên explicit.

**“Mọi API không truyền charset đều dùng default charset.”** Sai. Một số API `Files` được đặc tả UTF-8.

**“Cứ là Unicode thì dùng UTF-16LE.”** Sai. Unicode là tập code points, còn file/giao thức phải chọn UTF-8 hoặc một biến thể UTF-16 cụ thể.

**“Dùng ISO-8859-1 rồi chuyển ngược sẽ luôn giữ tiếng Việt.”** Sai. Nhiều ký tự tiếng Việt không biểu diễn được bằng Latin-1.

**“ASCII chỉ cần cast `char` sang `byte`.”** Sai với ký tự ngoài ASCII; cần encode theo charset và chính sách lỗi đúng.

**“`new String(bytes, UTF_8)` luôn ném lỗi nếu UTF-8 sai.”** Sai. Overload này thay thế malformed input mặc định; dùng `CharsetDecoder` với `REPORT` khi cần nghiêm ngặt.

**“Nếu charset sai thì đổi font là xong.”** Không chắc. Trước tiên kiểm tra byte và cách decode.

**“UTF_16, UTF_16BE và UTF_16LE là các hằng tương đương.”** Sai, chúng có byte order/BOM khác nhau.

**“Có `Charset.defaultCharset() == UTF-8` nghĩa là mọi output của chương trình đều UTF-8.”** Không chắc. Terminal, thư viện, giao thức và API đặc biệt có thể có quy tắc khác.

**“String.length() là số byte sau encode.”** Sai. Nó là số UTF-16 code units.

**“StandardCharsets.UTF_32 có từ Java 7.”** Sai. Ba hằng UTF-32 được thêm từ JDK 22.

## 15. Câu hỏi tự kiểm tra

**1.** `StandardCharsets.UTF_8` có kiểu gì? — **`Charset`**, không phải String hay enum.

**2.** StandardCharsets có từ khi nào? — **Java 7**, và vẫn dùng trên Java 17+.

**3.** Encode String thành byte UTF-8 bằng lệnh nào? — `text.getBytes(StandardCharsets.UTF_8)`.

**4.** Decode byte UTF-8 thành String bằng lệnh nào? — `new String(bytes, StandardCharsets.UTF_8)`, hoặc decoder nghiêm ngặt nếu dữ liệu có thể sai.

**5.** Vì sao “à” có hai byte trong UTF-8 nhưng một byte Latin-1? — Vì **bảng mã khác nhau**, cùng một ký tự được biểu diễn bằng dãy byte khác.

**6.** Dùng US-ASCII để encode “é” có bảo toàn không? — Không; API tiện lợi có thể thay bằng `?`; dùng strict encoder để từ chối.

**7.** `Files.readString(path)` trên JDK 17 dùng charset nào nếu không truyền? — **UTF-8 theo đặc tả**.

**8.** `getBytes()` không tham số có phải luôn UTF-8 trên JDK 17 không? — **Không**. Nó phụ thuộc default charset.

**9.** JDK 18 thay đổi default charset ra sao? — Theo JEP 400, **UTF-8 là mặc định của những API Java SE phụ thuộc default charset**, với khả năng cấu hình tương thích.

**10.** Strict UTF-8 decoder gặp byte `C3 28` có thể ném gì? — **`MalformedInputException`**.

**11.** Vì sao `"A".getBytes(UTF_16)` tạo `FE FF 00 41`? — Vì BOM big-endian và mã UTF-16 của “A”.

**12.** UTF_16LE có tự ghi BOM như UTF_16 không? — **Không** theo hợp đồng Java charset này.

**13.** Một file CSV UTF-8 đọc theo Latin-1 hiển thị lỗi: sửa ở đâu? — **Decode theo UTF-8 tại ranh giới đọc**; xác minh bytes gốc và hợp đồng đối tác.

**14.** JDK 17 có `StandardCharsets.UTF_32` không? — **Không**. Hằng được thêm từ JDK 22.

**15.** Charset đúng có bảo đảm dữ liệu đã sạch về bảo mật không? — **Không**, vẫn cần validation, giới hạn kích thước và kiểm tra quyền.

## Tài liệu chính thức

- [Java SE 17 StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các hằng charset chuẩn có từ Java 7.
- [Java SE 17 Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): quy tắc charset, UTF-16, BOM và tên charset.
- [Java SE 17 String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `getBytes(Charset)`, `String(byte[],Charset)` và replacement behavior.
- [Java SE 17 CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát malformed/unmappable input.
- [Java SE 17 Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): đọc và ghi file với charset.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset ở JDK 18.
- [JDK 22 Release Notes](https://www.oracle.com/java/technologies/javase/22all-relnotes.html): các hằng UTF-32 mới trong StandardCharsets.

**Ghi nhớ:** Vai trò của `StandardCharsets` là làm rõ và cố định **charset tại ranh giới văn bản ↔ byte**. Dùng UTF-8 cho dữ liệu mới khi phù hợp, tôn trọng encoding thực tế của dữ liệu cũ, tránh phụ thuộc default charset trong protocol và từ chối dữ liệu sai định dạng nếu không chấp nhận việc thay ký tự.