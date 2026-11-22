# Phân biệt encode chuỗi thành byte và decode byte thành chuỗi trong Java

Khi Java trao đổi văn bản với file, mạng, HTTP, cơ sở dữ liệu hay hệ thống khác, dữ liệu thường phải đi qua ranh giới giữa **`String` (ký tự)** và **`byte[]` (byte)**. Hai thao tác đi theo **hai hướng ngược nhau**:

~~~text
                         ENCODE (mã hóa ký tự)
String (ký tự Unicode) ------------------------> byte[]
       ^                                           |
       |                 DECODE                    |
       +-------------------------------------------+
                 (giải mã byte thành ký tự)

Ví dụ với charset UTF-8:
"café" --encode--> 63 61 66 C3 A9 --decode--> "café"
~~~

Trong bài này, **encode** nghĩa là *character encoding* (chuyển ký tự sang byte theo một bộ mã ký tự, `Charset`); **decode** là đảo chiều chuyển byte sang ký tự theo `Charset`. Đây **không phải mã hóa bảo mật** (encryption/decryption). Nếu muốn bảo mật dữ liệu, cần các cơ chế mật mã riêng; chuyển mã ký tự không làm dữ liệu trở thành bí mật.

## 1. Định nghĩa và API Java

| Nội dung | Encode: chuỗi → byte | Decode: byte → chuỗi |
| --- | --- | --- |
| Đầu vào | `String` (văn bản) | `byte[]` (dữ liệu nhị phân) |
| Đầu ra | `byte[]` | `String` |
| Quy tắc chuyển đổi | Dùng `CharsetEncoder` | Dùng `CharsetDecoder` |
| API thường dùng | `text.getBytes(charset)` | `new String(bytes, charset)` |
| Ví dụ `UTF-8` | `"é"` → `C3 A9` | `C3 A9` → `"é"` |
| Sai cách xử lý | Ký tự không biểu diễn được có thể bị thay thế hoặc báo lỗi | Dãy byte lỗi có thể bị thay thế hoặc báo lỗi |

Một **charset** quy định cách biểu diễn ký tự bằng dãy byte và cách khôi phục ký tự từ dãy byte. Trong Java, dùng kiểu `java.nio.charset.Charset`, đặc biệt các hằng chuẩn ở `java.nio.charset.StandardCharsets`:

- `StandardCharsets.UTF_8`: bộ mã Unicode phổ biến, có số byte biến đổi theo ký tự, tương thích ASCII cho các ký tự ASCII.
- `StandardCharsets.UTF_16BE`, `UTF_16LE`: UTF-16 với thứ tự byte xác định.
- `StandardCharsets.UTF_16`: UTF-16 có quy tắc về BOM/thứ tự byte khác với hai biến thể chỉ rõ endian.
- `StandardCharsets.US_ASCII`: phạm vi ASCII, không biểu diễn được mọi chữ tiếng Việt.
- `StandardCharsets.ISO_8859_1`: bộ mã một byte cho tập ký tự Latin-1; không phải Unicode đầy đủ.

**`String` là văn bản Unicode trong Java**, còn các byte là **biểu diễn bên ngoài** theo charset. Không suy ra byte mã hóa từ cách JVM lưu trữ nội bộ `String`. Cùng một `String` có thể tạo ra các dãy byte **khác nhau** khi dùng UTF-8, UTF-16 hay ISO-8859-1.

## 2. Encode: từ `String` sang `byte[]`

Phương thức quen thuộc là:

~~~java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
~~~

Quá trình encode đọc nội dung ký tự của `text` và sinh dãy byte theo UTF-8. Ví dụ:

- Chữ `A` (U+0041) → byte UTF-8 `41`.
- Chữ `é` (U+00E9) → hai byte `C3 A9`.
- Emoji `😀` (U+1F600) → bốn byte `F0 9F 98 80`.

Một ký tự hiển thị **không nhất thiết bằng một byte**. Thậm chí `String.length()` trong Java trả về **số đơn vị UTF-16**, không phải số Unicode code point, số ký tự người dùng nhìn thấy hay số byte sau encode. Emoji `😀` là một code point nhưng chiếm **hai đơn vị UTF-16** và **bốn byte UTF-8**.

### Ví dụ Java 17 chạy độc lập

~~~java
// EncodingDemo.java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class EncodingDemo {
    public static void main(String[] args) {
        String original = "Aé😀";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 hex = "
                + HexFormat.of().withUpperCase().formatHex(utf8));
        System.out.println("UTF-16 units = " + original.length());
        System.out.println("Unicode code points = "
                + original.codePointCount(0, original.length()));
        System.out.println("UTF-8 bytes = " + utf8.length);

        String restored = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("Round-trip equal = " + original.equals(restored));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 EncodingDemo.java
java EncodingDemo
~~~

Kết quả:

~~~text
UTF-8 hex = 41C3A9F09F9880
UTF-16 units = 4
Unicode code points = 3
UTF-8 bytes = 7
Round-trip equal = true
~~~

`-encoding UTF-8` trong lệnh `javac` chỉ xác định **charset của tệp mã nguồn `.java`**. Tham số `StandardCharsets.UTF_8` trong chương trình mới xác định **charset khi encode/decode dữ liệu**. Đây là hai vị trí khác nhau, dù đều sử dụng UTF-8 trong ví dụ.

`HexFormat` (có từ Java 17) chỉ **hiển thị byte dưới dạng chữ số thập lục phân để kiểm tra**. Dãy `41 C3 A9 F0 9F 98 80` vẫn là bảy byte; không phải bảy ký tự của một chuỗi văn bản gốc.

## 3. Decode: từ `byte[]` sang `String`

Phương thức thường dùng:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

Decoder phải biết **cách hiểu các byte**. Bản thân `byte[]` không lưu nhãn “tôi đang ở UTF-8”; nếu không có giao ước hoặc metadata bên ngoài, máy nhận **không thể bảo đảm biết đúng charset** chỉ bằng cách nhìn mảng byte.

Ví dụ với dãy byte `63 61 66 C3 A9`:

- Giải mã bằng **UTF-8** → `"café"`.
- Giải mã bằng **ISO-8859-1** → `"cafÃ©"` (hai byte `C3` và `A9` được coi là hai ký tự Latin-1).

Các byte **không đổi**, cách diễn giải chúng thành ký tự **đổi**. Hiện tượng chữ bị hỏng do encode/decode nhầm charset gọi là **mojibake**.

### Ví dụ: cùng byte, hai cách giải mã

~~~java
// CharsetMismatchDemo.java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetMismatchDemo {
    public static void main(String[] args) {
        String original = "café";
        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);

        String correct = new String(bytes, StandardCharsets.UTF_8);
        String wrong = new String(bytes, StandardCharsets.ISO_8859_1);

        System.out.println("Bytes = "
                + HexFormat.of().withUpperCase().formatHex(bytes));
        System.out.println("Correct = " + correct);
        System.out.println("Wrong = " + wrong);
        System.out.println("Correct equal = " + original.equals(correct));
        System.out.println("Wrong equal = " + original.equals(wrong));
    }
}
~~~

Chạy `javac --release 17 -encoding UTF-8 CharsetMismatchDemo.java` và `java CharsetMismatchDemo`. Trên terminal hiển thị Unicode đúng, kết quả là:

~~~text
Bytes = 636166C3A9
Correct = café
Wrong = cafÃ©
Correct equal = true
Wrong equal = false
~~~

Nếu terminal hoặc hệ thống log còn sử dụng charset hiển thị khác, chữ in ra màn hình có thể tiếp tục bị biến dạng. Khi điều tra lỗi, hãy xem **hex của byte đầu vào**, **charset được khai báo**, **chuỗi sau decode**, và **charset của nơi xuất ra màn hình** như những bước riêng.

## 4. Vì sao phải dùng cùng charset?

Mục tiêu thường là:

~~~text
String ban đầu
   | encode theo charset X
   v
byte[]
   | lưu/truyền nguyên vẹn
   v
byte[]
   | decode theo charset X
   v
String khôi phục
~~~

Với dữ liệu Unicode hợp lệ và UTF-8, round-trip thông thường giữ nguyên nội dung:

~~~java
String input = "Tiếng Việt và 😀";
byte[] wire = input.getBytes(StandardCharsets.UTF_8);
String output = new String(wire, StandardCharsets.UTF_8);
System.out.println(input.equals(output)); // true
~~~

Tuy nhiên, “encode rồi decode cùng charset là luôn khôi phục 100%” **không đúng vô điều kiện**:

1. **Charset có thể không biểu diễn được ký tự**: ví dụ `US_ASCII` không biểu diễn được `é` hay tiếng Việt có dấu. Nếu API dùng chế độ thay thế, dữ liệu gốc bị mất ngay trong bước encode.
2. **Chuỗi Java có thể chứa surrogate UTF-16 không ghép cặp**: chuỗi đó không thể biểu diễn trực tiếp như các Unicode scalar value hợp lệ trong UTF-8; encoder có thể thay thế hoặc báo lỗi.
3. **Dãy byte có thể bị hỏng hoặc cắt giữa chừng** khi truyền/lưu, khiến decode sai hoặc lỗi.
4. **Hai đầu dùng khác charset** sẽ diễn giải byte không tương thích.
5. **Có bước biến đổi khác** giữa hai phía (chuẩn hóa Unicode, chuyển xuống dòng, sửa nội dung, thay thế ký tự...) khiến hai `String` khác nhau dù charset đúng.

UTF-8 là lựa chọn mặc định tốt cho giao thức/tệp văn bản mới khi hai phía đều thống nhất dùng UTF-8. Với dữ liệu di sản dùng charset khác, phải tuân theo charset **thực sự được dùng khi tạo byte**, không tự đổi sang UTF-8 tại bước decode.

## 5. Khi encode/decode không thể giữ nguyên dữ liệu

Ngay cả khi viết đúng hướng chuyển đổi, kết quả khứ hồi chưa chắc bằng bản gốc nếu dữ liệu không hợp lệ hoặc charset không biểu diễn được ký tự. Phân biệt ba tình huống:

| Tình huống | Điều xảy ra | Cách xử lý |
| --- | --- | --- |
| `"café"` được encode bằng US-ASCII | `é` không có mã tương ứng; `getBytes(US_ASCII)` thường thay bằng byte dấu `?` | Chọn charset biểu diễn được dữ liệu hoặc dùng `CharsetEncoder` với `REPORT` |
| Byte UTF-8 `C3 28` được decode bằng UTF-8 | Byte `C3` thiếu continuation hợp lệ; `new String` thường thêm U+FFFD (`�`) | Dùng `CharsetDecoder` với `REPORT` nếu phải từ chối byte lỗi |
| Byte UTF-8 `C3 A9` bị decode bằng ISO-8859-1 | Byte có thể hợp lệ nhưng tạo `Ã©` thay vì `é` (mojibake) | Xác nhận lại charset nguồn; kiểm tra byte gốc trước khi chuyển |

Các constructor/phương thức tiện lợi thường dùng cơ chế **thay thế**, có thể làm mất dữ liệu mà không ném lỗi. Ví dụ nhỏ sau phân biệt một decoder mềm và một decoder nghiêm ngặt:

~~~java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};
String lenient = new String(invalid, StandardCharsets.UTF_8);
System.out.println(lenient.codePointAt(0) == 0xFFFD); // true

try {
    StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(invalid));
} catch (CharacterCodingException ex) {
    System.out.println(ex.getClass().getSimpleName()); // MalformedInputException
}
~~~

Đây là đoạn đặt trong phương thức, với import `java.nio.ByteBuffer`, `java.nio.charset.CharacterCodingException`, `CodingErrorAction` và `StandardCharsets`. Bài **Dữ liệu sai mã, ký tự thay thế và mất thông tin** phân tích tình huống mất dữ liệu; bài **CharsetEncoder, CharsetDecoder và chính sách REPORT** giải thích hai API này, kể cả xử lý từng chunk qua `CoderResult`.

## 6. Charset mặc định không phải hợp đồng trao đổi dữ liệu

`text.getBytes()` và `new String(bytes)` dùng charset mặc định của JVM. Trên JDK 17 trở xuống, charset mặc định thường phụ thuộc hệ điều hành/locale; từ JDK 18, JEP 400 quy định UTF-8 trong cấu hình thông thường, nhưng dữ liệu cũ hoặc chế độ tương thích vẫn cần được xem xét. `Charset.defaultCharset()` cho biết giá trị thực tế của JVM đang chạy.

Trong giao thức/tệp mới đã chọn UTF-8, hãy luôn viết `getBytes(StandardCharsets.UTF_8)` và `new String(bytes, StandardCharsets.UTF_8)`. Nếu dữ liệu nguồn dùng charset khác, phải **decode bằng charset nguồn** thay vì tùy tiện ép UTF-8. Bài **Charset mặc định và ảnh hưởng môi trường hoặc phiên bản JDK** trình bày chi tiết JEP 400, các API chịu ảnh hưởng và cách kiểm thử khi nâng cấp.

## 7. Áp dụng encode/decode tại ranh giới thực tế

Ví dụ dữ liệu văn bản đi qua file hoặc mạng:

~~~text
String nguồn
   | getBytes(UTF_8)
   v
byte[] -- ghi file / truyền mạng / lưu nguyên byte --> byte[]
   | new String(bytes, UTF_8)
   v
String phía nhận
~~~

- Với file văn bản, `Files.writeString(path, text, StandardCharsets.UTF_8)` và `Files.readString(path, StandardCharsets.UTF_8)` định nghĩa hai chiều ngay ở API I/O. Khi so sánh toàn vẹn byte, dùng `Files.write`/`readAllBytes` rồi so sánh `byte[]`.
- Với HTTP/JSON, xác định charset theo **đặc tả định dạng hoặc giao thức** và chỉ đo `Content-Length` từ body byte thực sự được gửi đi. JSON escaping, phần header hay nén là các bước riêng, có thể làm kích thước cuối khác kích thước chuỗi ban đầu.
- Với stream, một ký tự UTF-8 nhiều byte có thể bị chia giữa hai lần đọc. Dùng `InputStreamReader` với charset đã chọn hoặc decoder giữ trạng thái; decode mỗi mảnh byte riêng lẻ có thể sinh ký tự thay thế.

Bài **Đối chiếu chuỗi qua ranh giới tệp, console và dữ liệu truyền** đưa ra bài chạy đầy đủ để kiểm tra byte tại nhiều điểm, phân biệt lỗi dữ liệu với lỗi hiển thị ở terminal.

## 8. Một vài yếu tố ngoài charset cần phân biệt

- **BOM**: UTF-8 BOM `EF BB BF` thường xuất hiện dưới dạng U+FEFF sau decode; chỉ xử lý theo quy tắc của định dạng tệp. UTF-16BE/LE cần thỏa thuận về byte order và cách dùng BOM.
- **Unicode normalization**: `é` có thể là U+00E9 hoặc `e` + U+0301. Hai cách biểu diễn có thể trông giống nhưng vẫn khác byte; charset không tự chuẩn hóa.
- **Biểu diễn nhị phân**: ảnh, tệp ZIP, âm thanh không tự nhiên là văn bản. Decode chúng thành `String` có thể làm mất byte, kể cả khi encode ngược.
- **Base64 và escaping**: Base64 chuyển byte thành các ký tự ASCII để vận chuyển; escape bảo đảm cú pháp trong Java/JSON/HTML. Cả hai đều khác chuyển mã ký tự.

## 9. Checklist trước khi tích hợp

1. Bên tạo dữ liệu đang có **văn bản** hay **byte nhị phân**?
2. Charset nguồn là gì, và nó được ghi ở đâu trong giao thức/hợp đồng?
3. Trước khi giải mã, byte có được giữ nguyên và có cần từ chối đầu vào malformed không?
4. Trước khi mã hóa, charset đích có biểu diễn được mọi ký tự cần gửi không?
5. Khi có khác biệt, đã kiểm tra byte hex, code point và charset của lớp hiển thị riêng rẽ chưa?

## 10. Phân biệt đường đi đúng và sai

~~~java
String input = "café";
byte[] utf8 = input.getBytes(StandardCharsets.UTF_8);
String right = new String(utf8, StandardCharsets.UTF_8);
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);

System.out.println(input.equals(right)); // true
System.out.println(input.equals(wrong)); // false
~~~

Đây là đoạn minh họa trong phương thức. Hai lời gọi `new String` đọc **cùng một dãy byte**; chỉ charset khác nhau. Vì thế cần bắt đầu từ hợp đồng byte nguồn, sau đó xác thực từng lớp biến đổi khi ứng dụng đi qua file, mạng hoặc môi trường mới.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `"é".getBytes(StandardCharsets.UTF_8)` sinh bao nhiêu byte? Nếu decode chúng bằng `ISO_8859_1` thì ra chuỗi nào?

**Đáp án:** Hai byte `C3 A9`; decode Latin-1 tạo `"Ã©"` vì hai byte được hiểu là hai ký tự riêng.

**Câu 2.** Vì sao `"😀".length()` bằng `2` trong Java nhưng encode UTF-8 tạo `4` byte?

**Đáp án:** `String.length()` đếm **hai đơn vị UTF-16** biểu diễn một code point U+1F600, còn UTF-8 biểu diễn code point đó bằng **bốn byte**.

**Câu 3.** Khi Java đọc hai khối byte của một socket, tại sao không nên dùng `new String(chunk, UTF_8)` riêng cho từng khối?

**Đáp án:** Một ký tự UTF-8 nhiều byte có thể vắt qua ranh giới khối; decoder độc lập cho từng khối coi byte thiếu là lỗi. Dùng decoder có trạng thái hoặc `InputStreamReader`.

**Câu 4.** Encode `"café"` bằng US-ASCII có thể gây vấn đề gì? Muốn báo lỗi thay vì thay thế ký tự, nên dùng gì?

**Đáp án:** `é` không thuộc ASCII; API encode mềm có thể thay thế nó, làm mất dữ liệu. Dùng `CharsetEncoder` và `onUnmappableCharacter(CodingErrorAction.REPORT)`.

**Câu 5.** Nếu byte của một file ZIP được đưa vào `String` bằng UTF-8 rồi encode lại, có đảm bảo giữ nguyên file gốc không?

**Đáp án:** Không. ZIP là dữ liệu nhị phân, có thể chứa chuỗi byte không hợp lệ theo UTF-8 và decoder sẽ thay thế. Giữ nguyên dạng byte hoặc byte stream.

## Ghi nhớ

**Encode** là `String → byte[]` theo charset; **decode** là `byte[] → String` theo charset. Muốn khôi phục đúng dữ liệu, phải có **byte nguyên vẹn**, **charset thống nhất**, và **chính sách xử lý lỗi phù hợp**. Dùng `StandardCharsets.UTF_8` tường minh cho dữ liệu văn bản mới khi giao thức cho phép; kiểm tra byte bằng hex khi xảy ra lỗi; dùng `CharsetEncoder`/`CharsetDecoder` ở chế độ `REPORT` khi mất dữ liệu là không chấp nhận được.
