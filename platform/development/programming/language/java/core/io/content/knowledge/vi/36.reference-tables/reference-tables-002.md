# Bảng charset và quy tắc chuyển byte sang ký tự trong Java I/O

## 1. Mục đích và mô hình cần nhớ

Khi đọc tệp, luồng mạng hoặc dữ liệu nhị phân chứa văn bản, chương trình nhận **byte**, còn ứng dụng muốn xử lý **ký tự Unicode**. Muốn chuyển đúng phải biết **charset (bộ mã ký tự)** mà bên tạo dữ liệu đã dùng. Một chuỗi byte có thể cho ra văn bản khác nhau tùy charset; nhiều trường hợp không thể suy ra charset một cách chắc chắn chỉ từ byte.

Luồng chuyển đổi:

~~~text
Văn bản Unicode --[encoder + charset]--> dãy byte
Dãy byte        --[decoder + charset]--> văn bản Unicode
~~~

- **Charset** quy định cách mã hóa (encode) ký tự thành byte và giải mã (decode) byte thành ký tự.
- **Unicode code point** là số định danh một ký tự trừu tượng, ví dụ U+0041 (A), U+00E9 (é), U+4E2D (中), U+1F600 (😀).
- **Java String và char** biểu diễn chuỗi bằng các đơn vị mã **UTF-16**. Một code point ngoài BMP, chẳng hạn 😀, dùng **hai char** (surrogate pair); vì vậy số byte, số char và số code point có thể khác nhau.
- **CharsetDecoder** biến byte thành chuỗi đơn vị UTF-16. **CharsetEncoder** làm chiều ngược lại.
- **Malformed input** là dãy byte sai cấu trúc charset; **unmappable character** là đầu vào không biểu diễn được ở đích. Hai loại lỗi cần được phân biệt và xử lý có chủ đích.

Công thức tư duy: **byte + charset + quy tắc xử lý lỗi → văn bản**. Không có phép tra cứu đúng cho mọi byte khi thiếu charset.

## 2. Bảng tra cứu các charset thường gặp

| Charset trong Java | Quy tắc và miền biểu diễn | Một ký tự / code point chiếm bao nhiêu byte? | Cần chú ý |
|---|---|---|---|
| **US-ASCII** (StandardCharsets.US_ASCII) | Mã 0x00–0x7F ánh xạ sang U+0000–U+007F | 1 byte cho ký tự biểu diễn được | Byte từ 0x80 trở lên không hợp lệ trong ASCII chuẩn |
| **ISO-8859-1** (StandardCharsets.ISO_8859_1) | Mỗi byte 0x00–0xFF ánh xạ trực tiếp tới code point U+0000–U+00FF | Luôn 1 byte khi mã hóa ký tự thuộc tập này | Byte 0x80 là U+0080 (ký tự điều khiển), **không phải** dấu € |
| **windows-1252** (Charset.forName("windows-1252")) | Mã 8-bit kiểu Windows Tây Âu; nhiều vị trí 0x80–0x9F khác Latin-1 | 1 byte cho ký tự biểu diễn được | Byte 0x80 là €; một số byte như 0x81 không được gán |
| **UTF-8** (StandardCharsets.UTF_8) | Biến độ dài, giữ nguyên ASCII 0x00–0x7F | 1–4 byte/code point Unicode hợp lệ | Byte tiếp diễn 0x80–0xBF không thể tự đứng đầu một ký tự |
| **UTF-16BE** (StandardCharsets.UTF_16BE) | UTF-16 theo thứ tự byte cao trước | 2 hoặc 4 byte/code point | Không tự yêu cầu BOM; thứ tự byte phải được biết |
| **UTF-16LE** (StandardCharsets.UTF_16LE) | UTF-16 theo thứ tự byte thấp trước | 2 hoặc 4 byte/code point | Khác UTF-16BE ở thứ tự byte |
| **UTF-16** (StandardCharsets.UTF_16) | UTF-16 có quy tắc nhận diện BOM để xác định thứ tự byte khi decode | 2 hoặc 4 byte/code point, cộng BOM nếu có | Decoder nhận BOM; nếu không có BOM, mặc định big-endian theo Java |

**UTF-8 và UTF-16 là các Unicode Transformation Format**, có thể biểu diễn toàn bộ Unicode scalar values hợp lệ. Ngược lại, ASCII/Latin-1/Windows-1252 chỉ chứa những tập ký tự hữu hạn; không thể encode mọi chuỗi Unicode vào chúng mà không có xử lý lỗi.

Cách viết "ANSI" trong tài liệu cũ không xác định một charset duy nhất. Cần hỏi rõ mã trang (ví dụ windows-1252, windows-1258) và môi trường đã tạo dữ liệu.

## 3. Bảng ví dụ: cùng ký tự, byte khác nhau

Các chuỗi hex dưới đây mô tả **riêng byte của ký tự**, không kèm BOM:

| Ký tự | Unicode | UTF-8 | ISO-8859-1 | windows-1252 | UTF-16BE | UTF-16LE |
|---|---|---|---|---|---|---|
| A | U+0041 | 41 | 41 | 41 | 00 41 | 41 00 |
| é | U+00E9 | C3 A9 | E9 | E9 | 00 E9 | E9 00 |
| € | U+20AC | E2 82 AC | Không biểu diễn | 80 | 20 AC | AC 20 |
| 中 | U+4E2D | E4 B8 AD | Không biểu diễn | Không biểu diễn | 4E 2D | 2D 4E |
| 😀 | U+1F600 | F0 9F 98 80 | Không biểu diễn | Không biểu diễn | D8 3D DE 00 | 3D D8 00 DE |

**Giải thích các trường hợp dễ nhầm:**

1. UTF-8 mã hóa A bằng 41 giống ASCII, nhưng **é** cần hai byte C3 A9.
2. Byte **E9** trong ISO-8859-1/windows-1252 là é; một byte E9 đứng đơn lẻ **không phải UTF-8 hợp lệ**.
3. Byte **80** trong windows-1252 là €, trong ISO-8859-1 là U+0080, còn trong UTF-8 là byte tiếp diễn đứng sai vị trí.
4. UTF-16 biểu diễn 😀 bằng cặp surrogate **D83D DE00**. Java **String.length()** trả 2 cho ký tự này, trong khi **codePointCount(...)** trả 1.
5. “Không biểu diễn” có nghĩa encoder chuẩn với chính sách **REPORT** phải báo lỗi, không có byte hợp lệ để điền vào bảng. Encoder ở chế độ thay thế có thể phát ra ký tự thay thế như dấu hỏi.

**Tra ngược từ byte cần biết charset:** byte 0xE9 không mặc nhiên là é trong UTF-8; chuỗi E2 82 AC chỉ là € khi giải bằng UTF-8, không phải khi giải bằng Latin-1.

## 4. Quy tắc giải mã UTF-8 theo bit

UTF-8 mã hóa một Unicode code point bằng 1–4 byte. Các mẫu bit:

| Số byte | Byte đầu | Byte tiếp theo | Phạm vi code point |
|---|---|---|---|
| 1 | 0xxxxxxx | Không có | U+0000–U+007F |
| 2 | 110xxxxx | 10xxxxxx | U+0080–U+07FF |
| 3 | 1110xxxx | 10xxxxxx 10xxxxxx | U+0800–U+FFFF, trừ vùng surrogate |
| 4 | 11110xxx | 10xxxxxx 10xxxxxx 10xxxxxx | U+10000–U+10FFFF |

Quy trình giải mã một code point:

1. Xem byte đầu để xác định cần 1, 2, 3 hay 4 byte; kiểm tra còn đủ byte.
2. Với chuỗi đa byte, mọi byte sau phải có tiền tố bit **10**.
3. Bỏ các bit tiền tố và ghép các bit dữ liệu theo thứ tự từ trái sang phải.
4. Kiểm tra giá trị tối thiểu cho độ dài đó, không cho phép dạng **overlong**, code point surrogate U+D800–U+DFFF hoặc giá trị vượt U+10FFFF.
5. Chuyển code point thu được sang một hoặc hai đơn vị UTF-16 để đặt vào Java String.

Ví dụ **é = U+00E9**: C3 (11000011) và A9 (10101001) có các bit dữ liệu **00011 101001** → nhị phân 11101001 → U+00E9. Ví dụ **€ = U+20AC**: E2 82 AC → U+20AC.

Một số lỗi UTF-8 phổ biến: byte đầu 0x80–0xBF (chỉ hợp lệ ở vị trí tiếp diễn); chuỗi thiếu byte tiếp diễn; C0/C1 dẫn tới mã hóa quá dài; F5–FF không hợp lệ; mẫu ba byte mã hóa surrogate; mẫu bốn byte vượt U+10FFFF. Decoder nghiêm ngặt phải báo lỗi thay vì tự ý đoán ký tự.

## 5. Quy tắc giải mã UTF-16, thứ tự byte và BOM

UTF-16 gồm các **đơn vị 16 bit**:

- Code point U+0000–U+D7FF và U+E000–U+FFFF mã hóa bằng một đơn vị 16 bit.
- Code point U+10000–U+10FFFF mã hóa bằng hai đơn vị: **high surrogate** (D800–DBFF) rồi **low surrogate** (DC00–DFFF).
- Một surrogate đứng đơn lẻ không phải Unicode scalar value hợp lệ.
- Với **UTF-16BE**, đơn vị 0x0041 thành 00 41; với **UTF-16LE**, thành 41 00.

**BOM (Byte Order Mark)** là dấu chỉ thứ tự byte ở đầu dữ liệu:

| Dữ liệu | Byte BOM | Ý nghĩa |
|---|---|---|
| UTF-8 | EF BB BF (tùy chọn) | Không cần cho thứ tự byte; nếu xuất hiện, cần có quy tắc xử lý nhất quán |
| UTF-16BE | FE FF | Thường dùng làm dấu hiệu big-endian |
| UTF-16LE | FF FE | Thường dùng làm dấu hiệu little-endian |

Trong Java, **StandardCharsets.UTF_16** hiểu BOM khi giải mã; nếu không có BOM, bộ giải mã UTF-16 mặc định big-endian. Các charset **UTF_16BE** và **UTF_16LE** có thứ tự byte cố định: không dựa vào BOM để đổi thứ tự. Khi encode bằng **UTF_16** của Java, output thường bắt đầu bằng BOM FE FF; muốn byte không BOM theo thứ tự đã biết thì chọn **UTF_16BE** hoặc **UTF_16LE**.

BOM UTF-8 không phải dấu bắt buộc, cũng không phải cách nhận diện charset chắc chắn cho mọi tệp. Tùy bộ đọc và định dạng dữ liệu, EF BB BF có thể trở thành U+FEFF ở đầu String; nếu chuẩn đầu vào yêu cầu bỏ BOM, hãy xử lý có chủ đích. Không xóa U+FEFF ở giữa văn bản một cách mù quáng.

## 6. Java 17+: giải mã đúng và kiểm tra kết quả

Ví dụ sau **độc lập, biên dịch và chạy được** bằng Java 17+. Mỗi lần giải mã đều dùng charset được chỉ định và **REPORT** để tránh âm thầm thay byte hỏng bằng ký tự khác.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetLookupDemo {
    private static String decodeStrict(byte[] bytes, Charset charset)
            throws CharacterCodingException {
        CharsetDecoder decoder = charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        return decoder.decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static void main(String[] args) throws CharacterCodingException {
        byte[] utf8 = HexFormat.of().parseHex("41C3A9E4B8ADF09F9880");
        String text = decodeStrict(utf8, StandardCharsets.UTF_8);

        System.out.println("text=" + text);
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));

        byte[] latin1 = HexFormat.of().parseHex("E9");
        System.out.println("latin1=" +
                decodeStrict(latin1, StandardCharsets.ISO_8859_1));

        byte[] cp1252 = HexFormat.of().parseHex("80");
        System.out.println("cp1252=" +
                decodeStrict(cp1252, Charset.forName("windows-1252")));

        String hex = HexFormat.of().withUpperCase()
                .formatHex(text.getBytes(StandardCharsets.UTF_8));
        System.out.println("hex=" + hex);

        byte[] invalidUtf8 = HexFormat.of().parseHex("C328");
        try {
            decodeStrict(invalidUtf8, StandardCharsets.UTF_8);
        } catch (MalformedInputException e) {
            System.out.println("invalidUtf8=" +
                    e.getClass().getSimpleName());
        }
    }
}
~~~

Lưu với tên **CharsetLookupDemo.java** trong UTF-8, chạy:

~~~bash
javac -encoding UTF-8 CharsetLookupDemo.java
java CharsetLookupDemo
~~~

Đầu ra:

~~~text
text=Aé中😀
utf8Bytes=10
utf16Units=5
codePoints=4
latin1=é
cp1252=€
hex=41C3A9E4B8ADF09F9880
invalidUtf8=MalformedInputException
~~~

Chú ý **HexFormat.parseHex(...)** nhận chuỗi hex liền nhau trong ví dụ trên. Nếu đầu vào có dấu cách như “41 C3 A9”, cần bỏ dấu cách hoặc phân tích theo delimiter phù hợp; không truyền trực tiếp rồi giả định hàm luôn bỏ mọi whitespace.

So sánh **new String(bytes, StandardCharsets.UTF_8)**: tiện lợi với dữ liệu đã xác thực, nhưng constructor dạng này có thể thay dãy malformed/unmappable bằng chuỗi thay thế. Khi yêu cầu tính toàn vẹn (cấu hình, giao thức, nội dung cần xác nhận byte chính xác), hãy dùng **CharsetDecoder** với **CodingErrorAction.REPORT** để nhận **CharacterCodingException**.

## 7. Áp dụng trong I/O: đọc/ghi luôn nêu charset

Với tệp văn bản UTF-8, các API mức cao của Java nhận charset rõ ràng:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileUtf8Demo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("sample-utf8.txt");
        Files.writeString(path, "Tiếng Việt và 😀",
                StandardCharsets.UTF_8);

        String result = Files.readString(path, StandardCharsets.UTF_8);
        System.out.println(result);
    }
}
~~~

Lưu **TextFileUtf8Demo.java** dưới UTF-8, chạy **javac -encoding UTF-8 TextFileUtf8Demo.java** rồi **java TextFileUtf8Demo**. Stdout là:

~~~text
Tiếng Việt và 😀
~~~

Mẫu đọc luồng bằng Reader khi xử lý dần: **new InputStreamReader(inputStream, StandardCharsets.UTF_8)**. Đối với dữ liệu cần kiểm tra nghiêm ngặt, dùng constructor nhận **CharsetDecoder** đã đặt REPORT. Bởi vì Reader có thể giữ một phần dãy UTF-8 ở cuối buffer để chờ byte tiếp theo, không tự cắt mỗi chunk thành một String riêng bằng **new String(chunk, UTF_8)**: nếu cắt giữa các byte của cùng ký tự, ký tự sẽ hỏng. Giữ một decoder xuyên suốt luồng hoặc đọc qua Reader phù hợp.

Nếu dữ liệu là **binary** (ZIP, ảnh, protobuf, file byte thuần), không decode toàn bộ như văn bản. Chỉ những trường được đặc tả là text mới dùng charset.

Đừng để việc đọc/ghi phụ thuộc charset mặc định của hệ thống: **new String(bytes)** và **String.getBytes()** không truyền charset có thể phụ thuộc runtime/cấu hình. Từ JDK 18, default charset theo JEP 400 thông thường là UTF-8, nhưng dữ liệu và môi trường vẫn có các ngoại lệ; với Java 17 đặc biệt không nên suy đoán. Viết rõ charset mà định dạng tệp/giao thức yêu cầu.

## 8. Xử lý lỗi: REPORT, REPLACE và IGNORE

| Hành động | Khi dữ liệu sai | Khi nên dùng |
|---|---|---|
| **CodingErrorAction.REPORT** | Ném lỗi (ví dụ MalformedInputException, UnmappableCharacterException) | Đọc giao thức/cấu hình, import cần phát hiện dữ liệu hỏng, kiểm thử |
| **CodingErrorAction.REPLACE** | Chèn chuỗi thay thế do decoder/encoder cấu hình | Hiển thị dữ liệu có thể chấp nhận mất thông tin, cần cảnh báo người dùng |
| **CodingErrorAction.IGNORE** | Bỏ qua phần không hợp lệ | Chỉ khi đặc tả cho phép mất dữ liệu; khó dùng cho dữ liệu quan trọng |

Ví dụ C3 28 không phải dãy UTF-8 hợp lệ: C3 là byte đầu cần thêm một byte dạng 10xxxxxx nhưng 28 là dấu mở ngoặc ASCII. Nếu decoder thay thế lỗi, kết quả thông thường là **�(** (U+FFFD rồi dấu ngoặc); với REPORT, Java báo **MalformedInputException**.

Trường hợp encode cũng có lỗi: chuỗi chứa **€** hoặc **中** không biểu diễn được trong ISO-8859-1. Encoder với REPORT báo **UnmappableCharacterException**; nếu thay thế, byte thu được không còn tái tạo nguyên văn Unicode ban đầu. Bất kỳ pipeline cần round-trip chính xác đều nên dùng charset đủ khả năng biểu diễn dữ liệu, thường là UTF-8, và quy định xử lý lỗi rõ ràng.

## 9. Mojibake: ký tự bị biến thành “Ã©”, “â‚¬” và cách chẩn đoán

**Mojibake** là văn bản bị rối do byte tạo bởi charset này nhưng giải bằng charset khác. Ví dụ chữ **é** có UTF-8 hex **C3 A9**. Nếu hai byte ấy được giải bằng windows-1252, chúng thành hai ký tự **Ã©**, không còn é. Tương tự **€** có UTF-8 **E2 82 AC**, đọc nhầm windows-1252 thường hiển thị **â‚¬**.

Quy trình tìm nguyên nhân:

1. Giữ **byte gốc**; kiểm tra các byte hex ở vùng lỗi và nguồn phát sinh dữ liệu (tệp, HTTP, database, message queue).
2. Lấy charset từ **quy ước/metadata đáng tin** (đặc tả file, header Content-Type có charset hợp lệ, schema/giao thức, cấu hình bên ghi).
3. Giải thử với charset được khai báo và kiểm tra cả ký tự đại diện ngoài ASCII; đừng chỉ nhìn đoạn tiếng Anh vì ASCII 0x00–0x7F giống nhau ở nhiều charset.
4. Nếu dữ liệu đã bị decode sai và encode lại nhiều lần, cần biết **từng bước chuyển đổi** mới có thể phục hồi; chỉ “đổi charset lúc hiển thị” có thể không đủ.
5. Khi thấy U+FFFD hoặc dấu hỏi đã được lưu thành byte, có thể thông tin gốc **đã mất**. Sửa đúng lỗi ở nơi đọc/ghi và tạo lại dữ liệu từ byte nguồn nếu còn.

Không có bộ dò charset nào bảo đảm đúng cho mọi byte. Dùng heuristic chỉ khi thiếu đặc tả và chấp nhận khả năng đoán sai; với dữ liệu quan trọng, yêu cầu nguồn cung cấp charset chính xác.

**Đừng nhầm charset với normalization.** Chữ nhìn giống **é** có thể là U+00E9 hoặc tổ hợp U+0065 U+0301; UTF-8 sẽ tạo byte khác nhau dù cả hai đều giải mã đúng. Charset không tự bảo đảm NFC/NFD, và việc chuẩn hóa Unicode là bước xử lý riêng khi nghiệp vụ cần.

## 10. Checklist tra cứu nhanh

- Xác định **byte gốc** và **charset nguồn** trước khi viết lệnh decode.
- Nếu cần chuyển trực tiếp byte → String trong Java: **new String(bytes, charset)** cho trường hợp thông thường; **charset.newDecoder() + REPORT** khi muốn phát hiện lỗi.
- Nếu cần String → byte: **text.getBytes(charset)**; dùng **CharsetEncoder + REPORT** khi sợ mất ký tự.
- Đọc/ghi tệp: ưu tiên **Files.readString/writeString** với **StandardCharsets.UTF_8** hoặc charset đặc tả.
- Gặp dữ liệu UTF-16: kiểm tra thứ tự byte, BOM, surrogate pair.
- Gặp lỗi tiếng Việt: kiểm tra charset phía tạo byte và phía decode, không tự sửa bằng phép replace các ký tự hiển thị.
- Khi ghi log kiểm tra: in hex byte, code point (ví dụ **text.codePoints()**), charset và cách xử lý lỗi; phân biệt **String.length()** với số code point.
- Với dữ liệu đa chunk hoặc streaming: giữ decoder qua các lần đọc để không làm đứt một ký tự UTF-8.
- Chỉ convert văn bản; dữ liệu nhị phân không có charset tổng quát.

## 11. Nguồn tra cứu chuẩn

- [Java 17 — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): quy tắc encode/decode và charset.
- [Java 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed/unmappable và CodingErrorAction.
- [Java 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn được hỗ trợ.
- [Unicode — UTF-8 / UTF-16 (Unicode Standard)](https://www.unicode.org/versions/latest/core-spec/chapter-3/): định dạng và kiểm tra tính hợp lệ của encoding.
