# Chọn encoding tường minh khi chuyển giữa văn bản và byte trong Java

> **Java core — language-basics / Ký tự và chuỗi**  
> **Môi trường:** JDK 17+, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Phân biệt nội dung `String` với byte, chọn đúng `Charset` ở cả chiều mã hóa và giải mã, tránh lỗi chữ tiếng Việt/emoji, kiểm tra dữ liệu không hợp lệ và áp dụng quy tắc này cho tệp hoặc giao tiếp mạng.

## 1. Văn bản và byte là hai biểu diễn khác nhau

Một `String` Java biểu diễn văn bản bằng các đơn vị mã UTF-16. `byte[]` lại chỉ chứa các số nguyên 8 bit; **một dãy byte không tự mang theo charset** để người nhận biết phải đọc nó thế nào.

Muốn chuyển giữa hai dạng phải thống nhất **bộ mã ký tự (character encoding/charset)**:

~~~text
String --getBytes(UTF_8)--> byte[]
String <--new String(bytes, UTF_8)-- byte[]
~~~

Ví dụ chuỗi `"Aé😀"` gồm **3 Unicode code point**, **4 đơn vị UTF-16** nhưng thành **7 byte UTF-8**:

| Thành phần | Code point | UTF-8 (hex) | Số byte |
| --- | --- | --- | ---: |
| `A` | U+0041 | `41` | 1 |
| `é` | U+00E9 | `C3 A9` | 2 |
| `😀` | U+1F600 | `F0 9F 98 80` | 4 |
| **Toàn chuỗi** | 3 code point | `41 C3 A9 F0 9F 98 80` | **7** |

Do đó `String.length()` **không** cho biết số byte cần truyền hay lưu. `length()` đếm đơn vị UTF-16; byte count phải dựa trên **charset được chọn**.

## 2. Luôn truyền `Charset` tường minh

Java cung cấp các hằng charset trong `java.nio.charset.StandardCharsets`; **UTF-8** là lựa chọn mặc định hợp lý cho đa số định dạng văn bản hiện đại khi không có quy ước khác.

~~~java
import java.nio.charset.StandardCharsets;

String text = "Tiếng Việt";
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(payload, StandardCharsets.UTF_8);
~~~

**Quy tắc:** Mã hóa bằng charset nào thì giải mã phải dùng charset phù hợp với dữ liệu đó. Cả hai đầu truyền/nhận cần thỏa thuận charset trong hợp đồng dữ liệu hoặc metadata của giao thức.

So sánh những API quan trọng:

| Tác vụ | Nên viết | Tránh phụ thuộc môi trường |
| --- | --- | --- |
| `String` → `byte[]` | `s.getBytes(StandardCharsets.UTF_8)` | `s.getBytes()` |
| `byte[]` → `String` | `new String(bytes, StandardCharsets.UTF_8)` | `new String(bytes)` |
| Ghi văn bản ra tệp | `Files.writeString(path, s, StandardCharsets.UTF_8)` | Tự dựa vào charset mặc định của API khác |
| Đọc văn bản từ tệp | `Files.readString(path, StandardCharsets.UTF_8)` | Đoán encoding dựa vào hệ điều hành |

Hai phương thức `Files.writeString`/`Files.readString` khi **không** truyền charset vốn dùng UTF-8 trong Java 17; ghi tường minh vẫn làm hợp đồng dữ liệu dễ kiểm tra hơn. Không phải mọi API I/O cũ đều có cùng mặc định đó.

`StandardCharsets.UTF_16LE` hoặc `ISO_8859_1` cũng hữu ích **nếu định dạng thật sự yêu cầu**. Không chọn UTF-8 một cách mù quáng để đọc dữ liệu được quy định là UTF-16LE.

## 3. Chương trình Java 17+ runnable

Tạo tệp **EncodingDemo.java** chứa mã sau:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public final class EncodingDemo {
    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ").withUpperCase()
                .formatHex(bytes);
    }

    public static void main(String[] args) {
        String original = "Aé😀";

        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(utf8, StandardCharsets.UTF_8);

        byte[] utf16le = original.getBytes(StandardCharsets.UTF_16LE);
        String decoded16 = new String(
                utf16le, StandardCharsets.UTF_16LE);

        System.out.println("utf16Units=" + original.length());
        System.out.println("codePoints="
                + original.codePointCount(0, original.length()));
        System.out.println("utf8Bytes=" + utf8.length);
        System.out.println("utf8Hex=" + hex(utf8));
        System.out.println("utf8RoundTrip=" + original.equals(decoded));

        System.out.println("utf16leBytes=" + utf16le.length);
        System.out.println("utf16leHex=" + hex(utf16le));
        System.out.println("utf16leRoundTrip="
                + original.equals(decoded16));

        String wrong = new String(
                utf8, StandardCharsets.ISO_8859_1);
        System.out.println("wrongCharsetEqual="
                + original.equals(wrong));

        byte[] malformed = {(byte) 0xC3};
        String replaced = new String(
                malformed, StandardCharsets.UTF_8);
        System.out.printf("replacement=U+%04X%n",
                (int) replaced.charAt(0));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformed));
            System.out.println("strictUtf8=accepted");
        } catch (CharacterCodingException ex) {
            System.out.println("strictUtf8=rejected");
        }
    }
}
~~~

Tại thư mục chứa `EncodingDemo.java`, dùng Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 EncodingDemo.java
java EncodingDemo
~~~

**Expected output chính xác:**

~~~text
utf16Units=4
codePoints=3
utf8Bytes=7
utf8Hex=41 C3 A9 F0 9F 98 80
utf8RoundTrip=true
utf16leBytes=8
utf16leHex=41 00 E9 00 3D D8 00 DE
utf16leRoundTrip=true
wrongCharsetEqual=false
replacement=U+FFFD
strictUtf8=rejected
~~~

**Đọc kết quả:**

1. `"Aé😀"` có 3 code point, 4 code unit UTF-16; UTF-8 dùng 7 byte, còn UTF-16LE dùng 8 byte.
2. `UTF_16LE` ghi hai byte theo thứ tự thấp-trước cho mỗi code unit, **không tự thêm BOM**; emoji được tách thành surrogate `D83D DE00` rồi thành byte `3D D8 00 DE`.
3. Round-trip cùng charset cho `true`. Đem byte UTF-8 giải mã bằng ISO-8859-1 cho chuỗi khác nội dung, vì mỗi byte lại được hiểu như một code point Latin-1.
4. Byte `C3` đứng một mình là UTF-8 **không hoàn chỉnh**. Constructor `new String(bytes, UTF_8)` thay đoạn lỗi bằng ký tự thay thế **U+FFFD**. Decoder có `CodingErrorAction.REPORT` từ chối dữ liệu đó để chương trình có thể xử lý lỗi.

Dùng `HexFormat` (có từ Java 17) để kiểm tra **byte thực**, thay vì chỉ nhìn các ký tự đôi lúc bị terminal hiển thị sai.

## 4. Giải mã sai gây chữ lỗi, không phải “chuỗi tự hỏng”

Giả sử phía gửi dùng UTF-8 để mã hóa `é` thành hai byte `C3 A9`, nhưng phía nhận dùng ISO-8859-1. Khi đó dữ liệu có thể hiển thị thành chuỗi ký tự sai (thường gọi là **mojibake**).

Điểm cần nhớ:

- Byte **vẫn là** byte; thay đổi cách diễn giải chúng mới thay đổi chuỗi thu được.
- `new String(bytes, charset)` không “tự nhận diện charset gốc” bằng phép màu.
- Đừng chuyển qua lại nhiều charset để đoán mò; trước tiên xác định **charset trong hợp đồng dữ liệu**.
- Nếu quá trình giải mã đã thay byte lỗi bằng ký tự `U+FFFD`, chỉ nhìn chuỗi sau giải mã có thể không khôi phục được dữ liệu gốc.

Một số định dạng có metadata encoding hoặc BOM. BOM có thể xuất hiện trong dữ liệu UTF-8/UTF-16, nhưng **không phải mọi tệp đều có**; không coi BOM là thành phần bắt buộc của UTF-8. Nếu giao thức quy định có/không có BOM, phải tuân theo định dạng đó.

## 5. Dữ liệu lỗi: thay thế hay từ chối?

Nếu dữ liệu đầu vào có encoding sai hoặc chuỗi byte bị cắt dở, có hai chính sách thường gặp:

| Chính sách | Khi nào nên dùng? | Kết quả |
| --- | --- | --- |
| **Thay thế** đoạn lỗi bằng `U+FFFD` | Xem văn bản “best effort”, chấp nhận mất một phần dữ liệu | `new String(bytes, UTF_8)` thường chọn thay thế malformed input |
| **Báo lỗi** nếu byte không hợp lệ | Dữ liệu phải chính xác, nhập liệu nghiêm ngặt, kiểm tra giao thức | `CharsetDecoder` với `CodingErrorAction.REPORT` ném `CharacterCodingException` |

Ví dụ chế độ nghiêm ngặt (như trong chương trình chính):

~~~java
String decoded = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes))
        .toString();
~~~

Đoạn này cần `bytes` là `byte[]` và các import `ByteBuffer`, `CodingErrorAction` như ví dụ chính; đặt trong method khai báo `throws CharacterCodingException` hoặc xử lý exception.

**Lưu ý hai chiều:** cả **encoder** (`String` → byte) cũng có thể mất dữ liệu nếu charset không biểu diễn được ký tự (ví dụ emoji với ISO-8859-1). Nếu không được phép mất ký tự, dùng `CharsetEncoder` cấu hình `REPORT` hoặc chọn UTF-8 khi định dạng hỗ trợ.

## 6. Áp dụng cho tệp, API và môi trường chạy

Khi dữ liệu cần ghi/đọc từ tệp, cấu hình charset ở **cả hai chiều**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("message.txt");
Files.writeString(path, "Tiếng Việt 😀", StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là **đoạn minh họa thao tác tệp**, không nằm trong chương trình `EncodingDemo`; nếu bạn chạy đoạn này, nó sẽ tạo/ghi `message.txt`. Không cần thao tác tệp để thực hiện bài demo chính.

Với HTTP, JSON, CSV hoặc database, cần biết rõ charset mà giao thức, tài liệu API hoặc driver sử dụng. Tránh cố tạo `String` từ các byte vốn là **dữ liệu nhị phân** như hình ảnh, tệp nén hoặc hash: muốn biểu diễn nhị phân trong văn bản hãy dùng một cách mã hóa phù hợp như Base64/hex.

**Ba lớp encoding riêng cần phân biệt:**

1. **Encoding tệp mã nguồn:** lệnh `javac -encoding UTF-8 EncodingDemo.java` yêu cầu compiler đọc `.java` bằng UTF-8.
2. **Encoding văn bản ↔ byte trong chương trình:** `StandardCharsets.UTF_8` hoặc charset được định dạng quy định.
3. **Encoding khi terminal hiển thị/in văn bản:** do môi trường và cấu hình console quyết định. Màn hình hiển thị sai **không tự chứng minh** byte đang sai.

Vì output của `EncodingDemo` chỉ chứa ký tự ASCII và hex, bạn có thể so sánh chính xác ngay cả khi console cấu hình Unicode chưa tốt.

## 7. Lỗi thường gặp và bài tập

| Lỗi | Cách tránh |
| --- | --- |
| `text.getBytes()` / `new String(bytes)` ở điểm trao đổi dữ liệu | Truyền `Charset` tường minh thay vì phụ thuộc mặc định của môi trường |
| Mã hóa UTF-8 rồi giải mã Latin-1 | Hai phía phải thống nhất encoding |
| Dùng `String.length()` làm số byte gửi | Dùng `text.getBytes(charset).length` hoặc tính trên byte[] thực |
| Giải mã “thành công” rồi tin rằng text chắc chắn đúng | Charset sai có thể không báo lỗi nhưng nội dung sai |
| Tự giả định tệp UTF-16 luôn có BOM | Phân biệt UTF-16 có BOM và UTF-16LE/BE theo hợp đồng tệp |
| Dùng ISO-8859-1 để lưu mọi ký tự Unicode | Charset này không biểu diễn được tất cả code point; có thể mất dữ liệu |
| Đổi charset console để “sửa” byte gốc | Phải kiểm tra riêng source, byte payload, charset giải mã và terminal |

**Bài 1:** Đếm byte UTF-8 của `"ABC"`, `"é"` và `"😀"` bằng `getBytes(StandardCharsets.UTF_8).length`. Vì sao ba trường hợp không có cùng số byte trên mỗi code point?

**Bài 2:** Thử mã hóa `"Việt"` bằng `UTF_8`, giải mã cùng charset và so `equals`. Sau đó thử giải mã bằng `ISO_8859_1` và quan sát khác biệt.

**Bài 3:** Cho `byte[] invalid = {(byte) 0xC3};`. Dự đoán kết quả của constructor `new String(invalid, UTF_8)` so với decoder `REPORT`.

**Bài 4:** Nếu API quy định UTF-16LE, hãy sửa chương trình dùng `StandardCharsets.UTF_16LE` ở cả hai chiều; đo độ dài byte và in hex.

**Bài 5:** Khi nhận byte từ mạng mà không có thông tin charset, bạn có thể chứng minh được văn bản gốc chắc chắn là UTF-8 chỉ từ vẻ ngoài của chuỗi không? Bạn sẽ làm rõ yêu cầu giao thức thế nào?

### Ghi nhớ

**Encoding là quy ước chuyển giữa văn bản và byte.** Luôn chọn và truyền `Charset` **tường minh ở cả chiều mã hóa và giải mã**; với văn bản hiện đại, UTF-8 thường phù hợp trừ khi định dạng quy định khác. Dùng byte hex và kiểm tra round-trip để xác nhận dữ liệu; dùng decoder `REPORT` khi phải từ chối byte không hợp lệ, không phụ thuộc default charset hoặc cách hiển thị của terminal.
