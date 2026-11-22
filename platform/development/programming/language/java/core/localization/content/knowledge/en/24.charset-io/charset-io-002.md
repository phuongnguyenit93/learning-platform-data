# Phân biệt encode với decode trong Java: Charset và I/O

## 1. Vì sao phải phân biệt hai chiều chuyển đổi?

Một văn bản tiếng Việt, tên người dùng hoặc nội dung JSON là **chuỗi ký tự** đối với chương trình, nhưng khi ghi tệp hoặc gửi qua mạng, máy tính phải biểu diễn nó thành **dãy byte**. Đến nơi nhận, dãy byte cần được diễn giải trở lại thành văn bản. Hai chiều này có tên khác nhau:

- **Encode (mã hóa ký tự):** chuyển **văn bản Unicode → các byte** theo một `Charset` đã chọn.
- **Decode (giải mã ký tự):** chuyển **các byte → văn bản Unicode** bằng `Charset` tương ứng.

Ví dụ với chuỗi `"Café"`:

~~~text
Văn bản:          C a f é
       encode UTF-8
Byte (hex):       43 61 66 C3 A9
       decode UTF-8
Văn bản:          C a f é
~~~

Nếu cùng dãy byte UTF-8 đó được **decode như ISO-8859-1**, ta nhận `"CafÃ©"` thay vì `"Café"`. Đây là lỗi thường gọi là **mojibake**: byte không nhất thiết hỏng, mà **bộ giải mã dùng sai charset**.

Bài này giải thích hướng đi, API, cách nhận diện lỗi, chính sách thay thế hay từ chối dữ liệu lỗi, cách thao tác với tệp và những quy tắc thực hành trong Java 17+. Nội dung nằm trong chủ đề **Charset và I/O**: mục tiêu là xử lý đúng sự chuyển đổi giữa **String** và **byte[]**, không nhầm với mã hóa bảo mật hoặc dữ liệu Base64.

## 2. Mô hình tổng quát: văn bản, charset và byte

### 2.1. Unicode và String

Một `String` Java biểu diễn nội dung văn bản dưới dạng các UTF-16 code unit; `char` là một code unit 16 bit. `String.length()` trả số code unit, không phải số byte được ghi vào tệp, số Unicode code point hay số ký tự mà người dùng nhìn thấy.

Ví dụ:

| Chuỗi | UTF-16 code units trong `String.length()` | Unicode code points | UTF-8 bytes |
| --- | ---: | ---: | ---: |
| `A` | 1 | 1 | 1 |
| `é` dạng dựng sẵn | 1 | 1 | 2 |
| `😀` | 2 | 1 | 4 |
| `Café 😀` | 7 | 6 | 10 |

Số byte của văn bản không thể suy ra bằng `text.length()` nếu không biết charset. Chữ `é` có thể chiếm 2 byte UTF-8 nhưng 1 byte ISO-8859-1; emoji 😀 cần 4 byte UTF-8 và **không biểu diễn được** trong ISO-8859-1.

**Unicode** định nghĩa các giá trị code point và nhiều quy tắc văn bản; **UTF-8**, **UTF-16** và **UTF-16LE/BE** là những phương pháp mã hóa biểu diễn văn bản thành byte. `Charset` trong Java mô tả một cách chuyển đổi cụ thể giữa ký tự và byte, có tên chuẩn và các alias.

### 2.2. Encode và decode là hai chiều ngược nhau

~~~text
                         encode
String / Unicode text  ------------>  byte[]
                      CharsetEncoder
                                        |
                                        | ghi file / gửi socket / HTTP body
                                        v
String / Unicode text  <------------  byte[]
                         decode
                      CharsetDecoder
~~~

Cả hai chiều đều cần **thống nhất charset**. Nếu bên gửi encode UTF-8, bên nhận phải decode UTF-8, trừ khi một giao thức có quy tắc chuyển đổi khác rõ ràng.

Có thể viết quy tắc đơn giản:

~~~text
bytes = encode(text, UTF-8)
text2 = decode(bytes, UTF-8)
~~~

Với **văn bản đầu vào hợp lệ, biểu diễn được** và không bị sửa byte giữa đường, thông thường `text2.equals(text)` là `true`. Nhưng nếu decoder/encoder thay thế dữ liệu lỗi, bytes bị cắt, hoặc hai phía dùng charset không tương thích, điều kiện này không còn được bảo đảm.

Không dùng thuật ngữ “encode chuỗi UTF-8 thành text” một cách mơ hồ: trong Java, nếu biến đang là `String`, nó là **văn bản** trong chương trình; gọi `getBytes(UTF_8)` mới tạo **byte UTF-8**.

## 3. Những API Java thường dùng

| Nhiệm vụ | API | Kiểu kết quả |
| --- | --- | --- |
| Encode một String | `text.getBytes(StandardCharsets.UTF_8)` | `byte[]` |
| Decode một dãy byte | `new String(bytes, StandardCharsets.UTF_8)` | `String` |
| Encode bằng đối tượng Charset | `charset.encode(text)` | `ByteBuffer` |
| Decode bằng đối tượng Charset | `charset.decode(buffer)` | `CharBuffer` |
| Tùy chỉnh lỗi encode | `charset.newEncoder()` | `CharsetEncoder` |
| Tùy chỉnh lỗi decode | `charset.newDecoder()` | `CharsetDecoder` |
| Ghi văn bản vào file | `Files.writeString(path, text, charset)` | `Path` |
| Đọc văn bản từ file | `Files.readString(path, charset)` | `String` |
| Ghi/đọc nguyên bytes | `Files.write(path, bytes)` / `Files.readAllBytes(path)` | byte-level |

`StandardCharsets` cung cấp các hằng như `UTF_8`, `UTF_16`, `UTF_16BE`, `UTF_16LE`, `US_ASCII`, `ISO_8859_1`. Dùng hằng `StandardCharsets.UTF_8` thay vì chuỗi tùy ý `"UTF8"` giúp tránh lỗi chính tả và cho thấy rõ hợp đồng I/O.

**Phân biệt:** `Charset.forName("UTF-8")` chọn charset theo tên, nhưng không tự encode/decode cho tới khi gọi API tương ứng. `StandardCharsets.UTF_8` là một `Charset` có sẵn.

## 4. Ví dụ hoàn chỉnh Java 17+: encode UTF-8 rồi decode lại

Tạo file `EncodeDecodeDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class EncodeDecodeDemo {
    public static void main(String[] args) {
        String original = "Caf\u00E9 \uD83D\uDE00";

        byte[] encoded =
                original.getBytes(StandardCharsets.UTF_8);
        String decoded =
                new String(encoded, StandardCharsets.UTF_8);

        System.out.println("utf8 hex="
                + HexFormat.of().formatHex(encoded));
        System.out.println("roundtrip="
                + original.equals(decoded));
        System.out.println("chars=" + original.length()
                + ", points=" + original.codePointCount(
                        0, original.length())
                + ", bytes=" + encoded.length);
    }
}
~~~

Lưu thành `EncodeDecodeDemo.java`, biên dịch/chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 EncodeDecodeDemo.java
java EncodeDecodeDemo
~~~

Stdout đã kiểm chứng trên JVM:

~~~text
utf8 hex=436166c3a920f09f9880
roundtrip=true
chars=7, points=6, bytes=10
~~~

Giải thích chi tiết:

- `C`, `a`, `f`: các byte `43 61 66` trong UTF-8.
- `é` (U+00E9): hai byte `C3 A9` trong UTF-8.
- Khoảng trắng: byte `20`.
- Emoji 😀 (U+1F600): bốn byte `F0 9F 98 80`.
- Tổng cộng 10 byte. Trong `String`, emoji này dùng **hai UTF-16 code units**, nên `String.length()` bằng 7, trong khi code point count bằng 6.

`HexFormat` xuất hiện từ Java 17, phù hợp với phiên bản JDK của ví dụ. Hex string là **cách hiển thị các byte để kiểm tra**, không phải văn bản UTF-8 được Java tự hiểu.

Cú pháp `"\u00E9"` và `"\uD83D\uDE00"` trong mã Java là **Unicode escapes ở source code**. Chúng giúp ví dụ ổn định khi copy trên môi trường có lỗi nhập emoji; chúng không có nghĩa chương trình đã encode văn bản thành UTF-8. Việc encode thật sự diễn ra tại `getBytes(StandardCharsets.UTF_8)`.

## 5. Khi dùng sai Charset: mojibake xảy ra ở bước decode

Giả sử bytes của chữ `Café` đã được **encode bằng UTF-8**:

~~~text
43 61 66 C3 A9
~~~

Nếu decoder hiểu đó là ISO-8859-1, byte `C3` và `A9` trở thành hai ký tự riêng `Ã` và `©`, tạo chuỗi `CafÃ©`.

Chương trình độc lập `WrongCharsetDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;

public class WrongCharsetDemo {
    public static void main(String[] args) {
        String original = "Caf\u00E9";
        byte[] utf8 =
                original.getBytes(StandardCharsets.UTF_8);

        String correct =
                new String(utf8, StandardCharsets.UTF_8);
        String wrong =
                new String(utf8, StandardCharsets.ISO_8859_1);

        System.out.println("correct=" + correct);
        System.out.println("wrong=" + wrong);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 WrongCharsetDemo.java
java WrongCharsetDemo
~~~

Stdout, khi console hiển thị Unicode đúng:

~~~text
correct=Café
wrong=CafÃ©
~~~

Điểm quan trọng: `wrong` **không phải byte[]**; nó đã là một **String Java** chứa những ký tự sai. Khi render ra giao diện, kết quả có thể xuất hiện mojibake nếu tầng hiển thị không thêm lỗi mới.

**Không khắc phục một cách máy móc bằng gọi encode/decode hai ba lần.** Trước hết hãy xác định chuỗi đã sai ở đâu, bytes gốc còn giữ không, nguồn dữ liệu có được gắn charset đúng không và có quá trình double-encoding hay không.

Nếu bytes gốc vẫn là `43 61 66 C3 A9`, cách sửa chính xác là **decode lại từ bytes gốc bằng UTF-8**. Nếu các bytes đã bị thay thế/cắt hoặc chuỗi đã trải qua nhiều chuyển đổi lỗi, việc khôi phục có thể không còn chắc chắn.

### 5.1. Double encoding khác với decode sai một lần

Nếu `"CafÃ©"` đã là String rồi lại **encode bằng UTF-8**, bytes mới tương ứng với các ký tự `Ã` và `©`, không phải trực tiếp là `C3 A9` ban đầu:

~~~text
"Café" UTF-8 bytes:   43 61 66 C3 A9
"CafÃ©" UTF-8 bytes:  43 61 66 C3 83 C2 A9
~~~

Khi lỗi đã lan qua cơ sở dữ liệu hoặc nhiều dịch vụ, một thao tác `new String(bytes, UTF_8)` đơn giản không đủ nếu `bytes` không còn là byte gốc. Việc “fix mojibake” phải dựa trên nguồn và chuỗi các bước đã thực sự diễn ra.

## 6. Encode có thể thất bại nếu Charset không biểu diễn được ký tự

UTF-8 có thể mã hóa mọi Unicode scalar value hợp lệ. Một số charset cũ chỉ bao phủ một tập ký tự hữu hạn. Ví dụ `ISO-8859-1` biểu diễn `é`, nhưng **không biểu diễn được emoji 😀**.

Điều này khác lỗi **decode bytes không hợp lệ**:

- **Unmappable character khi encode:** ký tự có trong văn bản nhưng charset đích không có biểu diễn.
- **Malformed input khi decode:** byte sequence không hợp lệ theo quy tắc charset được chọn.
- **Malformed UTF-16 khi encode:** đầu vào `String` có high/low surrogate đứng lẻ hoặc cấu trúc UTF-16 lỗi.

Bộ chuyển đổi có thể **REPLACE**, **REPORT** hoặc **IGNORE** tùy API/cấu hình. Với dữ liệu quan trọng, im lặng thay ký tự bằng `?` hoặc `�` có thể gây mất thông tin mà hệ thống không hay biết.

`String.getBytes(Charset)` không phải API phù hợp nếu cần kiểm soát chặt các lỗi unmappable/malformed trong mọi hoàn cảnh; để **báo lỗi thay vì thay thế**, hãy tạo `CharsetEncoder` và cấu hình `CodingErrorAction.REPORT`.

### 6.1. Ví dụ encode strict trên Java 17+

Tạo `StrictEncodingDemo.java`:

~~~java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictEncodingDemo {
    public static void main(String[] args) {
        CharsetEncoder encoder =
                StandardCharsets.ISO_8859_1.newEncoder()
                        .onMalformedInput(
                                CodingErrorAction.REPORT)
                        .onUnmappableCharacter(
                                CodingErrorAction.REPORT);

        String emoji = "\uD83D\uDE00";
        System.out.println("canEncode="
                + encoder.canEncode(emoji));

        try {
            encoder.encode(CharBuffer.wrap(emoji));
            System.out.println("encoded");
        } catch (CharacterCodingException error) {
            System.out.println("strict="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StrictEncodingDemo.java
java StrictEncodingDemo
~~~

Stdout:

~~~text
canEncode=false
strict=UnmappableCharacterException
~~~

Với dữ liệu không biểu diễn được, `canEncode` trả `false`, và encode strict ném `UnmappableCharacterException`. Đây là tín hiệu đúng để tầng nghiệp vụ quyết định có từ chối, xin người dùng sửa, hoặc chọn một charset khác phù hợp.

Nếu dữ liệu chứa surrogate đứng lẻ, `MalformedInputException` có thể xuất hiện ở bước encode strict; điều đó khác với một **code point hợp lệ nhưng không được charset đích hỗ trợ**.

Không gọi `encoder.canEncode` như validator bảo mật/ngôn ngữ toàn năng: nó chỉ đánh giá khả năng mã hóa với charset cụ thể và không bảo đảm văn bản phù hợp yêu cầu của ứng dụng.

## 7. Decode có thể gặp dãy byte sai hoặc bị cắt

Trong UTF-8, ký tự `é` được biểu diễn bằng **hai byte** `C3 A9`. Nếu nhận mỗi `C3` nhưng không có byte tiếp theo, đó là một UTF-8 sequence thiếu. Nếu nhận `C3 28`, byte `28` (ký tự `(`) không phải continuation byte hợp lệ sau `C3`.

Đối với đầu vào sai, có hai cách xử lý chính:

1. **Lenient / replacement:** thay phần malformed bằng ký tự thay thế `U+FFFD` hoặc một cách thay thế do decoder cấu hình.
2. **Strict / report:** ném ngoại lệ hoặc trả trạng thái lỗi để chương trình từ chối dữ liệu không hợp lệ.

Đừng nhầm `new String(bytes, UTF_8)` với một validator strict. Constructor này sử dụng chính sách thay thế cho chuỗi byte malformed/unmappable. Nếu muốn yêu cầu **UTF-8 hợp lệ hoàn toàn**, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` hoặc API file có chính sách từ chối lỗi đã được kiểm chứng.

### 7.1. Ví dụ đầy đủ: decode lenient và strict

Tạo `StrictDecodingDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictDecodingDemo {
    public static void main(String[] args) {
        byte[] invalid = {
                (byte) 0xC3, (byte) 0x28
        };

        String lenient =
                new String(invalid, StandardCharsets.UTF_8);
        System.out.println("lenient=" + lenient);

        CharsetDecoder decoder =
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(
                                CodingErrorAction.REPORT)
                        .onUnmappableCharacter(
                                CodingErrorAction.REPORT);

        try {
            decoder.decode(ByteBuffer.wrap(invalid));
            System.out.println("decoded");
        } catch (CharacterCodingException error) {
            System.out.println("strict="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StrictDecodingDemo.java
java StrictDecodingDemo
~~~

Stdout với console Unicode chuẩn:

~~~text
lenient=�(
strict=MalformedInputException
~~~

Trong ví dụ này, `new String` thay phần byte lỗi bằng `�` (U+FFFD), còn ký tự `(` vẫn được diễn giải. Decoder strict báo `MalformedInputException`, cho phép ứng dụng dừng xử lý.

**Đánh giá chính sách:** nếu đang hiển thị một tệp bị lỗi encoding để người dùng tham khảo, replacement có thể hữu ích; nếu đang đọc một định danh, dữ liệu pháp lý, cấu hình chính thức hoặc input yêu cầu khớp 100%, nên xem xét từ chối lỗi thay vì âm thầm bỏ mất thông tin.

Lưu ý `�` cũng có thể là ký tự U+FFFD **được đưa vào dữ liệu gốc một cách hợp lệ**. Vì thế chỉ nhìn thấy dấu `�` trong String không đủ để khẳng định nó mới được sinh ra bởi decoder.

## 8. `ByteBuffer`, `CharBuffer` và hai bộ máy chuyển đổi

Trong NIO, `CharsetEncoder` và `CharsetDecoder` dùng buffer:

~~~text
Encode: CharBuffer -> CharsetEncoder -> ByteBuffer
Decode: ByteBuffer -> CharsetDecoder -> CharBuffer
~~~

Dùng mức thấp này khi cần:

- Kiểm soát `CodingErrorAction`: `REPORT`, `REPLACE`, `IGNORE`.
- Chuyển đổi theo từng phần với buffer giới hạn.
- Làm việc với `ByteBuffer`/channel hoặc yêu cầu hiệu năng có kiểm chứng.
- Phân biệt lỗi malformed và unmappable theo chính sách.

Ví dụ thao tác đơn giản với API của `Charset`:

~~~java
ByteBuffer bytes = StandardCharsets.UTF_8.encode(text);
CharBuffer chars = StandardCharsets.UTF_8.decode(bytes);
String restored = chars.toString();
~~~

Đây **chỉ là đoạn mã minh họa trong phương thức**, cần các import `java.nio.ByteBuffer`, `java.nio.CharBuffer`, `java.nio.charset.StandardCharsets` và biến `String text`. Nó không phải một chương trình có `main`.

**Chú ý vị trí buffer:** `ByteBuffer` có `position`, `limit`, `remaining`. Một decoder đọc từ `position` đến `limit`; nếu byte buffer đã bị tiêu thụ và bạn tái sử dụng mà không `flip`/`rewind` phù hợp, kết quả có thể rỗng hoặc thiếu. Không nhầm việc đặt lại position với một phép chuyển mã dữ liệu.

Trong streaming, một multi-byte UTF-8 sequence có thể bị chia ở ranh giới hai buffer. Bộ giải mã có trạng thái phải được sử dụng theo đúng protocol `decode` / `flush`, hoặc dùng `InputStreamReader`/API cấp cao để chúng quản lý ranh giới. Không decode độc lập mỗi chunk bằng `new String(chunk, UTF_8)` rồi nối lại: nếu chunk cắt giữa `C3` và `A9`, hai lần decode riêng có thể sinh dấu thay thế.

## 9. Tại sao encode/decode không phải Base64, nén hoặc mã hóa bảo mật?

Các thuật ngữ “mã hóa” thường bị dùng chồng chéo:

| Thao tác | Đầu vào → đầu ra | Mục tiêu |
| --- | --- | --- |
| **Character encoding** | `String -> byte[]` theo UTF-8 | Biểu diễn văn bản thành bytes |
| **Character decoding** | `byte[] -> String` theo UTF-8 | Diễn giải bytes thành văn bản |
| **Base64 encoding** | `byte[] -> chuỗi ASCII Base64` | Vận chuyển bytes qua kênh text |
| **Compression** | bytes -> bytes thường ngắn hơn | Giảm kích thước |
| **Encryption** | plaintext bytes -> ciphertext bytes | Bảo vệ tính bí mật với thuật toán/khóa |

`StandardCharsets.UTF_8` **không bảo mật** nội dung: người nhận biết UTF-8 có thể decode dữ liệu. Base64 cũng **không phải encryption**. Nếu ứng dụng gửi dữ liệu nhạy cảm, các vấn đề TLS, mã hóa dữ liệu, phân quyền và kiểm soát log là một tầng khác.

Ví dụ xử lý Base64 đúng trình tự:

~~~text
Văn bản "Café"
    -> encode UTF-8 thành bytes
    -> Base64 encode bytes thành "Q2Fmw6k="
    -> Base64 decode trở lại bytes
    -> decode bytes bằng UTF-8 thành "Café"
~~~

Mỗi bước giải quyết một nhiệm vụ riêng. Đừng đưa chuỗi Base64 vào `new String(..., UTF_8)` rồi mong nhận văn bản gốc: phải giải Base64 về bytes trước.

## 10. Đọc và ghi tệp văn bản: chọn charset một cách tường minh

Khi làm việc với file, charset phải được dùng ở **đúng điểm chuyển đổi**.

### 10.1. Ghi văn bản ra file

~~~java
Files.writeString(path, text, StandardCharsets.UTF_8);
~~~

Lệnh trên encode `text` thành bytes UTF-8 và ghi ra file. File trên đĩa lưu **bytes**, không lưu object `String` Java.

### 10.2. Đọc file thành String

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

Lệnh trên đọc bytes từ file rồi decode bằng UTF-8. Nếu file thực sự được ghi bằng charset khác, đọc bằng UTF-8 không tự động chuyển đổi đúng.

Các đoạn này là **mã minh họa** yêu cầu import `java.nio.file.Files`, `java.nio.charset.StandardCharsets` và có biến `path`, `text`. Để xem một chương trình đầy đủ có cleanup, dùng ví dụ sau.

### 10.3. Ví dụ Java 17+: vòng ghi/đọc file UTF-8

Tạo `FileCharsetDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class FileCharsetDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile(
                "charset-demo-", ".txt");

        try {
            Files.writeString(path, "Caf\u00E9",
                    StandardCharsets.UTF_8);

            String content = Files.readString(
                    path, StandardCharsets.UTF_8);
            byte[] bytes = Files.readAllBytes(path);

            System.out.println("content=" + content);
            System.out.println("hex="
                    + HexFormat.of().formatHex(bytes));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Lưu `FileCharsetDemo.java` rồi chạy:

~~~bash
javac -encoding UTF-8 FileCharsetDemo.java
java FileCharsetDemo
~~~

Stdout:

~~~text
content=Café
hex=436166c3a9
~~~

`Files.createTempFile` tạo một tệp tạm với đường dẫn khác nhau ở từng lần chạy, nhưng ví dụ **không in đường dẫn**, nên stdout dữ liệu ổn định. `finally` xóa tệp tạm ngay cả khi các bước đọc/ghi sinh lỗi.

**Khác biệt về lỗi:** `Files.readString(path, charset)` có thể ném `MalformedInputException` khi file không chứa văn bản hợp lệ theo charset được chọn. Đây không giống constructor `new String(bytes, charset)` vốn có thể thay phần malformed. Không giả định mọi API đọc text cùng một chính sách lỗi.

### 10.4. Reader/Writer và streams

Khi đọc luồng văn bản, ưu tiên khai báo charset tường minh:

~~~java
try (var reader = new java.io.InputStreamReader(
        inputStream, StandardCharsets.UTF_8)) {
    // Đọc ký tự từ reader.
}
~~~

~~~java
try (var writer = new java.io.OutputStreamWriter(
        outputStream, StandardCharsets.UTF_8)) {
    // Ghi String/char qua writer.
}
~~~

Hai đoạn trên chỉ **minh họa trong phương thức**, giả định đã có `InputStream inputStream` hoặc `OutputStream outputStream`. Chúng không phải chương trình độc lập. Reader **decode byte stream thành characters**; writer **encode characters thành byte stream**.

Để thao tác tệp theo đường dẫn, có thể dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` và `Files.newBufferedWriter(path, StandardCharsets.UTF_8)`. Với dữ liệu lớn, streaming giúp tránh đọc toàn bộ nội dung vào RAM, nhưng cần dùng decoder/reader nhất quán qua các chunk.

## 11. Cùng một charset ở hai đầu chưa đủ nếu bytes đã bị thay đổi

Quy tắc “encode và decode cùng charset” là điều kiện cần, nhưng còn phải bảo đảm:

1. Byte sequence không bị cắt, ghép sai hoặc sửa trên đường truyền.
2. Chữ đầu vào có thể biểu diễn được trong charset đích.
3. Việc chuyển đổi không âm thầm dùng chế độ `REPLACE` làm mất ký tự.
4. Encoding của file/message được thỏa thuận hoặc khai báo chính xác.
5. Không có một tầng khác tự chuyển đổi lại bytes hoặc văn bản sai cách.

Ví dụ một ứng dụng gửi UTF-8 qua API nhưng proxy, hệ thống hàng đợi hoặc database driver diễn giải byte khác charset ở giữa có thể tạo dữ liệu sai trước khi ứng dụng cuối cùng decode. Nếu xử lý Unicode quan trọng, hãy kiểm tra **bytes tại ranh giới hệ thống** cùng với charset khai báo, không chỉ kiểm tra chuỗi hiển thị cuối cùng.

Với giao thức HTTP, phần `Content-Type`, metadata của file và nội dung thực tế phải nhất quán. Đừng tin rằng chỉ có `charset=UTF-8` trong header là đủ để sửa bytes vốn được ghi theo một encoding khác.

## 12. Default Charset của môi trường có thể dẫn tới lỗi

Một cách viết ngắn dễ nhầm:

~~~java
byte[] bytes = text.getBytes();
String decoded = new String(bytes);
~~~

Hai overload không truyền charset dùng **default charset** được Java xác định cho môi trường. Với JDK 18+, JEP 400 chuẩn hóa default charset thành UTF-8 trong phần lớn trường hợp mặc định, nhưng ứng dụng cần chạy trên JDK khác, cấu hình đặc biệt, thư viện cũ hoặc công cụ ngoài vẫn có thể cho hành vi khác.

**Đừng dựa vào default charset cho giao thức hoặc dữ liệu phải trao đổi ổn định.** Nên viết:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
~~~

Đây là **đoạn mã minh họa trong phương thức**; biến `text` cần có trước khi chạy. Overload tường minh cho thấy charset là một phần hợp đồng của dữ liệu.

Cũng cần phân biệt **encoding của Java source file** với **encoding của file dữ liệu** và **encoding của console**:

- `javac -encoding UTF-8` hướng dẫn compiler đọc **source .java** theo UTF-8.
- `StandardCharsets.UTF_8` trong `getBytes`, `new String`, `Files.writeString` điều khiển **data conversion** tại runtime.
- Terminal có thể hiển thị sai chữ dù chuỗi và byte trong chương trình hoàn toàn đúng; font/code page/console configuration là vấn đề hiển thị riêng.

Không nên sửa chuỗi đúng chỉ vì PowerShell/terminal hiển thị mojibake; phải kiểm tra bytes, code points và charset ở từng bước.

## 13. UTF-16, BOM và byte order

Bản thân `String` Java được đánh chỉ số theo UTF-16 code units, nhưng không có nghĩa mọi file Java ghi ra đều là **UTF-16 bytes**.

Ví dụ:

~~~java
text.getBytes(StandardCharsets.UTF_8);
text.getBytes(StandardCharsets.UTF_16LE);
text.getBytes(StandardCharsets.UTF_16BE);
~~~

Đây là ba **dãy byte có thể khác nhau** cho cùng văn bản. UTF-16LE và UTF-16BE khác thứ tự hai byte trong từng code unit, còn charset `UTF_16` của Java có quy tắc liên quan byte-order mark (BOM).

**BOM** có thể giúp một số decoder nhận biết byte order hoặc một biến thể Unicode encoding, nhưng không phải mọi file UTF-8 đều có BOM. Không dùng BOM như bộ tự phát hiện charset phổ quát. Nếu có yêu cầu file UTF-16, hãy quy định rõ UTF-16LE/UTF-16BE, BOM hay không có BOM, và cách đọc ở các hệ thống liên quan.

Để tránh nhầm trong các dự án thông thường, UTF-8 không BOM thường là lựa chọn đơn giản cho văn bản trao đổi, nhưng **ưu tiên đặc tả giao thức/định dạng file** nếu nó yêu cầu encoding cụ thể.

## 14. Kiểm tra bytes thay vì phỏng đoán từ hình dạng văn bản

Khi nghi ngờ encoding sai, một quy trình debug hiệu quả là:

1. Chọn đoạn văn bản ngắn có ký tự ngoài ASCII, ví dụ `é`, `ấ` hoặc emoji.
2. Xác định **dữ liệu gốc đang là String hay bytes** ở mỗi điểm.
3. Với bytes, in hex bằng `HexFormat`; với String, in code points nếu cần.
4. Đối chiếu charset được khai báo ở nguồn và nơi nhận.
5. Kiểm tra xem đã có bước chuyển thành String sai charset hay bước encode lần hai chưa.
6. Quyết định nơi khắc phục đầu tiên mà không phá hủy dữ liệu nguồn.
7. Thêm regression test chứa Unicode thực tế, thay vì chỉ ASCII.

**ASCII-only test là chưa đủ.** Với ký tự `A`, UTF-8 và ISO-8859-1 đều dùng byte `41`, nên lỗi charset có thể không bộc lộ. Một test chứa `Café` hoặc chữ tiếng Việt mới giúp phát hiện mismatch sớm hơn.

Ví dụ dãy bytes `C3 A9` có thể nghĩa:

| Giải mã bằng | Kết quả |
| --- | --- |
| UTF-8 | `é` |
| ISO-8859-1 | `Ã©` |

Nếu bytes ban đầu là `E9` trong ISO-8859-1, đó có thể là `é` theo charset ấy, nhưng không phải một UTF-8 sequence hợp lệ. Một lỗi phổ biến là nhìn thấy ký tự lạ và “đoán” encoding từ văn bản đã bị decode sai; hãy ưu tiên **bytes gốc và metadata** thay vì suy diễn.

## 15. Phân biệt encode/decode với normalization

`java.text.Normalizer` làm việc ở **tầng văn bản Unicode**, ví dụ đưa `e + combining acute` về `é` trong NFC. Nó **không** thay thế `CharsetEncoder` hoặc `CharsetDecoder`.

Có ba loại biến đổi cần tách:

~~~text
Bytes UTF-8 -- decode UTF-8 --> String
String -- normalize NFC --> String
String -- encode UTF-8 --> Bytes UTF-8
~~~

Nếu đầu vào là hai chuỗi tương đương chuẩn tắc nhưng khác cách biểu diễn code point, normalization có thể đổi số byte sau encode. Vì vậy ngay cả khi encode/decode được thực hiện đúng, không thể khẳng định bytes ban đầu sẽ giống hệt nếu có thêm bước normalize.

Nếu cần **bảo toàn byte-for-byte**, giữ bytes gốc trước khi decode và trước mọi biến đổi. Nếu chỉ cần **tương đương văn bản**, có thể chọn normalization theo hợp đồng dữ liệu. Không dùng `new String(bytes, UTF_8)` để sửa lỗi Unicode normalization, cũng không dùng NFC để khắc phục bytes đã decode sai charset.

## 16. Cách chọn charset khi thiết kế ứng dụng

Trong dự án Java mới, **UTF-8** thường là lựa chọn thích hợp cho file văn bản và giao tiếp máy–máy vì hỗ trợ toàn bộ Unicode scalar values, có thể biểu diễn văn bản đa ngôn ngữ và phổ biến trong hệ sinh thái hiện đại.

Tuy nhiên, nếu làm việc với dữ liệu legacy:

- Đừng giả định mọi file đều UTF-8.
- Hãy tìm encoding được quy định trong hợp đồng, tài liệu hệ thống, metadata hoặc nguồn tạo file.
- Một số encoding cũ không có cách nhận biết chắc chắn chỉ từ bytes.
- Nếu nguồn dùng Windows-1252, Shift_JIS hoặc charset khác, cần cấu hình decoder đúng theo nguồn (khi môi trường có hỗ trợ), rồi có thể encode lại thành UTF-8 để lưu/trao đổi theo chính sách.
- Tránh decode sai rồi lại encode UTF-8 khiến mojibake trở thành dữ liệu “hợp lệ” khó khôi phục.

Khi cần chuyển file legacy sang UTF-8, quy trình đúng là:

~~~text
bytes theo charset cũ
       |
       | decode bằng charset cũ
       v
String Unicode
       |
       | encode bằng UTF-8
       v
bytes UTF-8
~~~

Đây là **transcoding**: giải mã bằng charset nguồn rồi mã hóa bằng charset đích. Không phải chỉ đổi phần mở rộng tệp hoặc header `charset` mà không chuyển bytes.

## 17. Các lỗi thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ encode/decode là một thao tác | Khó xác định vị trí lỗi | Chỉ rõ chiều `String -> bytes` hay `bytes -> String` |
| Decode UTF-8 bằng ISO-8859-1 | `Café` thành `CafÃ©` | Dùng charset thật của bytes gốc |
| Dùng `text.length()` để tính byte size | Sai với tiếng Việt/emoji | Tính `getBytes(charset).length` |
| Dùng `new String(bytes, UTF_8)` như bộ kiểm tra strict | Có thể thay byte lỗi bằng U+FFFD | Dùng `CharsetDecoder` với `REPORT` |
| Encode emoji bằng charset Latin-1 và không xử lý lỗi | Mất ký tự do unmappable | Kiểm tra hỗ trợ hoặc encoder strict |
| Đọc từng chunk UTF-8 thành String riêng | Chia đôi multibyte sequence | Dùng decoder/reader streaming có trạng thái |
| Chỉ test ASCII | Lỗi charset ẩn | Test dấu tiếng Việt, `é`, emoji |
| Không truyền charset khi gọi I/O | Phụ thuộc runtime/hệ thống | Dùng `StandardCharsets.UTF_8` tường minh |
| Tưởng `javac -encoding` quyết định charset dữ liệu file | Nhầm compile-time với runtime | Chọn charset ở API đọc/ghi |
| Tin header charset nhưng bytes thực tế khác | Vẫn hiển thị sai | Đảm bảo cả metadata và bytes đúng |
| Encode mojibake thêm lần nữa | Lỗi trở nên khó sửa | Lần ngược các bước từ bytes nguồn |
| Dùng UTF-16 code units như UTF-8 bytes | Sai độ dài/buffer | Phân biệt biểu diễn String và encoding |
| Nhầm Base64 với UTF-8 hoặc encryption | Giải mã sai tầng | Xử lý Base64, charset, crypto đúng chức năng |
| Chỉ lưu String sau decode lỗi khi cần giữ nguồn | Có thể không khôi phục bytes ban đầu | Lưu bytes/metadata gốc khi cần |

## 18. Checklist kiểm thử

Một bộ kiểm thử encode/decode đáng tin nên có:

1. **ASCII**: `"A"` → `41` trong UTF-8.
2. **Latin có dấu**: `"é"` → `C3 A9` trong UTF-8.
3. **Tiếng Việt**: chuỗi có nhiều dấu và nhiều code point trong một grapheme.
4. **Emoji ngoài BMP**: `"😀"` → `F0 9F 98 80` trong UTF-8.
5. **Round-trip**: `decode(encode(text, UTF_8), UTF_8)` phải bằng text hợp lệ.
6. **Wrong charset**: bytes UTF-8 của `Café` decode ISO-8859-1 thành `CafÃ©`.
7. **Malformed UTF-8**: `C3 28` bị decoder strict từ chối.
8. **Replacement**: constructor `new String` có thể trả `�(` thay vì ném lỗi.
9. **Unmappable**: encoder ISO-8859-1 không encode được 😀 và báo lỗi trong strict mode.
10. **File I/O**: ghi/đọc UTF-8 bằng `Files.writeString/readString` và kiểm tra bytes.
11. **Streaming**: chuỗi nhiều byte bị chia ở boundary giữa hai buffers vẫn được decode đúng khi xử lý theo trạng thái.
12. **Default charset**: không dùng default khi giao thức yêu cầu tính tái lập.
13. **UTF-16/BOM**: kiểm tra chính xác byte order và BOM nếu dùng định dạng này.
14. **Byte-level integrity**: phân biệt dữ liệu đã normalize với bytes gốc.
15. **Error policy**: mỗi đầu vào malformed/unmappable đều có chính sách từ chối hoặc thay thế được tài liệu hóa.

### Bài tập thực hành

- Thay `Café 😀` trong `EncodeDecodeDemo` bằng chuỗi tiếng Việt nhiều dấu, dự đoán sự khác biệt giữa `String.length()` và byte count; xác minh bằng Java.
- Viết hàm `hexUtf8(String text)` dùng `HexFormat` để hiển thị byte sequence, rồi giải thích tại sao một code point có thể cần nhiều bytes.
- Đổi `WrongCharsetDemo` từ `ISO_8859_1` sang một charset legacy khác (nếu JDK hỗ trợ), so sánh biểu diễn mojibake.
- Tạo byte array `{(byte) 0xC3}`; thử `new String` và decoder strict, giải thích trường hợp thiếu continuation byte.
- Gọi `StandardCharsets.ISO_8859_1.newEncoder().canEncode("😀")` và thử encode với `REPORT`. Nếu muốn ghi emoji, chọn charset nào?
- Viết file bằng UTF-8 rồi cố đọc bằng ISO-8859-1, so sánh với cách đọc lại theo UTF-8. Sau đó giữ nguyên bytes nguồn và sửa bằng cách decode đúng.
- Mô tả quy trình chuyển một file legacy sang UTF-8 qua **decode charset cũ → encode UTF-8**, giải thích tại sao chỉ sửa header không đủ.
- Với một giao thức yêu cầu xác thực text đúng UTF-8, hãy chọn decoder strict và bổ sung test malformed; không dùng constructor lenient làm validator.

## 19. Ghi nhớ

**Encode = String/characters → bytes. Decode = bytes → String/characters.** `Charset` là hợp đồng quy định ánh xạ hai chiều, và hai đầu phải thống nhất để dữ liệu round-trip đúng. UTF-8 thường là lựa chọn tốt cho dữ liệu đa ngôn ngữ, nhưng file legacy cần charset nguồn thực tế.

Trong Java 17+, dùng `getBytes(StandardCharsets.UTF_8)`, `new String(bytes, StandardCharsets.UTF_8)` cho các trường hợp phổ thông; dùng `CharsetEncoder` và `CharsetDecoder` với `CodingErrorAction.REPORT` khi phải **phát hiện lỗi thay vì thay thế im lặng**. Khi đọc/ghi file, chỉ định charset ở `Files.readString`, `Files.writeString` hoặc reader/writer; debug bằng **bytes hex và String code points** thay vì phỏng đoán từ ký tự bị hiển thị sai.

Đừng lẫn encoding với Base64, encryption, compression, normalization hoặc trình bày console. Giữ bytes nguồn khi yêu cầu bảo toàn chính xác, và bảo vệ việc chuyển đổi ở từng ranh giới hệ thống.

## Tài liệu chính thức

- [Oracle Java 21 — Charset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html)
- [Oracle Java 21 — CharsetEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [Oracle Java 21 — CharsetDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [Oracle Java 21 — CodingErrorAction](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [Oracle Java 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Oracle Java 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Oracle Java 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400)
