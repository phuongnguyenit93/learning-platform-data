# MalformedInputException, ký tự thay thế và mất dữ liệu

Đọc hoặc ghi văn bản trong Java không đơn thuần là chuyển một mảng byte thành một `String`. Giữa byte và ký tự có **charset** (bộ mã), bộ giải mã `CharsetDecoder`, bộ mã hóa `CharsetEncoder` và **chính sách xử lý lỗi**. Nếu một chuỗi byte không hợp lệ đối với charset đã chọn, Java có thể **báo lỗi**, **thay thế đoạn sai bằng ký tự khác**, hoặc **bỏ qua đoạn đó**. Những lựa chọn này tạo ra khác biệt rất lớn về tính toàn vẹn dữ liệu.

Một chương trình có thể đọc “thành công” nhưng nội dung đã **mất thông tin không thể khôi phục**. Ví dụ chuỗi byte `41 C3 28 42` không phải UTF-8 hợp lệ. Một API đọc dễ dùng có thể đưa ra chuỗi chứa:

~~~text
A�(B
~~~

Dấu `�` ở đây thường là **U+FFFD REPLACEMENT CHARACTER**. Trong khi đó, một bộ giải mã UTF-8 được cấu hình chế độ `REPORT` sẽ phát sinh `MalformedInputException` thay vì âm thầm sửa byte.

Bài học thuộc **Java core - localization / Charset và I/O**, tập trung vào:

- Phân biệt **byte sai cú pháp** (*malformed input*) với **ký tự không thể ánh xạ** (*unmappable character*).
- Hiểu `MalformedInputException`, `UnmappableCharacterException`, `CharacterCodingException` và ba chính sách `CodingErrorAction.REPORT`, `REPLACE`, `IGNORE`.
- Biết những API nào **mặc định thay thế** và API nào **báo lỗi** trên Java 17+.
- Hiểu ký tự `U+FFFD`, dấu hỏi `?` khi mã hóa và hiện tượng *mojibake*.
- Thiết kế luồng đọc/ghi file, HTTP payload hoặc dữ liệu nhập khẩu sao cho **phát hiện sai charset**, lưu được byte gốc khi cần, không chuyển mất dữ liệu thành nội dung được coi là hợp lệ.

**Thông điệp cốt lõi:** Việc một `String` được tạo ra **không chứng minh dữ liệu byte đầu vào hợp lệ**, và việc một chuỗi không xuất hiện U+FFFD **không chứng minh charset đã được chọn đúng**.

## 1. Cơ chế: hai chiều byte ↔ Unicode

Sơ đồ cơ bản:

~~~text
Đọc:
byte[] / file / network
      ↓ [CharsetDecoder + charset + error policy]
Unicode text (String/CharBuffer)
      ↓
xử lý, hiển thị, lưu vào database

Ghi:
Unicode text (String/CharBuffer)
      ↓ [CharsetEncoder + charset + error policy]
byte[] / file / network
~~~

Ở chiều **đọc**, một UTF-8 decoder sẽ xem các byte có tuân theo cấu trúc UTF-8 không; các chuỗi byte sai cấu trúc có thể sinh `MalformedInputException`. Ở chiều **ghi**, một encoder US-ASCII không thể biểu diễn `à` hay `ộ`; đây thường là lỗi **unmappable character**, có thể sinh `UnmappableCharacterException`.

Điều quan trọng:

1. **Charset không tự được “nhìn thấy” từ byte.** Nhiều định dạng byte không chứa metadata charset; phải biết từ giao thức, cấu hình, BOM khi hợp lệ, hoặc quyết định của hệ thống.
2. **Unicode text** và **encoded bytes** là hai tầng. `String` của Java không phải “một chuỗi UTF-8”; UTF-8 là một cách mã hóa chuỗi thành byte.
3. **Thay thế** có thể khiến code sau đó không biết đoạn gốc là gì.
4. **Báo lỗi** cho phép giữ byte gốc và quyết định cách khắc phục trước khi dữ liệu bị sửa.

Một ứng dụng quốc tế thường ưu tiên **UTF-8 tường minh**, nhưng dùng UTF-8 không đủ nếu nguồn thật sự là Windows-1252, Shift_JIS hay một định dạng khác và không có hợp đồng rõ ràng.

## 2. Thế nào là malformed input?

`Malformed input` là một dãy byte **không hợp lệ về cú pháp đối với charset đã chọn**. Với UTF-8, một số byte đứng đầu cần có các byte tiếp diễn hợp lệ. Nếu byte tiếp diễn sai hoặc dãy bị cắt cụt, decoder không thể biến dãy đó thành code point Unicode hợp lệ.

Ví dụ:

~~~text
41 C3 28 42
^^ ^^ ^^ ^^
 A  ?  (  B
~~~

`0x41` là `A`. Byte `0xC3` trong UTF-8 thường bắt đầu một dãy hai byte, nhưng `0x28` là ký tự `(` chứ không phải byte tiếp diễn `10xxxxxx`. Vì vậy dãy trên bị sai cấu trúc UTF-8.

- Với **`REPORT`**, decoder báo lỗi khi gặp byte sai.
- Với **`REPLACE`**, decoder chèn replacement string, thường là `U+FFFD`, rồi tiếp tục.
- Với **`IGNORE`**, decoder bỏ phần lỗi và tiếp tục.

Không nên đồng nhất “malformed” với “ký tự không đọc được bằng font”. Một code point hợp lệ có thể bị font hiển thị thành ô vuông do thiếu glyph; đó là **vấn đề render**, không phải lỗi giải mã.

### Một ví dụ Java hoàn chỉnh

Tạo file **`MalformedUtf8Demo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;

public class MalformedUtf8Demo {
    public static void main(String[] args) {
        byte[] bytes = {
                0x41, (byte) 0xC3, 0x28, 0x42
        };

        String forgiving =
                new String(bytes, StandardCharsets.UTF_8);

        System.out.println(forgiving.codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList());

        try {
            String strict = StandardCharsets.UTF_8
                    .newDecoder()
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
            System.out.println(strict);
        } catch (CharacterCodingException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac MalformedUtf8Demo.java
java MalformedUtf8Demo
~~~

Kết quả trên Java 17:

~~~text
[U+0041, U+FFFD, U+0028, U+0042]
MalformedInputException
~~~

Chúng ta in **code point** để tránh phụ thuộc font console có hiển thị dấu `�` giống nhau hay không. Dòng đầu chứng minh một API **đã có dữ liệu Unicode sau replacement**, không phải bytes ban đầu đã được giải mã nguyên vẹn.

## 3. Lớp `MalformedInputException` nằm ở đâu?

`java.nio.charset.MalformedInputException` thuộc hệ ngoại lệ của Charset API:

~~~text
java.lang.Exception
  └── java.io.IOException
       └── java.nio.charset.CharacterCodingException
            ├── MalformedInputException
            └── UnmappableCharacterException
~~~

`MalformedInputException` có phương thức `getInputLength()` cho biết độ dài **đoạn đầu vào sai** mà coder báo cáo, thường tính bằng đơn vị đầu vào của quá trình mã hóa/giải mã: với decoder là byte, với encoder là `char` input units.

Không nên xem `getInputLength()` là **vị trí trong file**. Nó **không** cung cấp byte offset toàn cục hoặc toàn bộ các byte sai. Nếu cần điều tra lỗi trên stream dài, phải giữ offset và các byte liên quan theo logic I/O riêng, bảo đảm không tiết lộ dữ liệu nhạy cảm vào log.

Một `catch (CharacterCodingException ex)` có thể bắt cả hai loại lỗi coding cơ bản. Muốn phân biệt cụ thể:

~~~java
try {
    decoder.decode(ByteBuffer.wrap(bytes));
} catch (MalformedInputException ex) {
    // Dãy byte/char đầu vào không hợp lệ với charset.
} catch (UnmappableCharacterException ex) {
    // Đơn vị đầu vào hợp lệ nhưng không ánh xạ được.
}
~~~

Đây là **snippet trong method**; cần import các lớp `java.nio.charset` và `java.nio.ByteBuffer`, và có sẵn biến `decoder` / `bytes`.

Đừng bắt `Exception` rồi bỏ qua như một “lỗi font”. Nó là tín hiệu chất lượng dữ liệu đầu vào hoặc sai charset.

## 4. Malformed và unmappable: khác nhau thế nào?

Hai loại lỗi thường bị đánh đồng:

| Khái niệm | Bản chất | Ví dụ |
| --- | --- | --- |
| **Malformed input** | Đơn vị đầu vào không tạo thành chuỗi hợp lệ theo charset hoặc UTF-16 đầu vào | UTF-8 có byte mở đầu mà không có byte tiếp diễn hợp lệ |
| **Unmappable character** | Chuỗi đầu vào hợp lệ nhưng **không có ánh xạ trong charset đích** | Cố mã hóa chữ `à` vào US-ASCII |
| **Mojibake** | Byte được giải mã **hợp lệ nhưng theo charset sai**, tạo chữ lạ | UTF-8 của `é` bị đọc theo ISO-8859-1 thành `Ã©` |
| **Thiếu glyph** | Unicode text đúng nhưng font không có biểu diễn phù hợp | Ô vuông/tofu trong ứng dụng |
| **Normalization difference** | Hai biểu diễn Unicode canonical-equivalent nhưng khác dãy code point | `é` và `e` + U+0301 |

`MalformedInputException` không phải ngoại lệ chung cho mọi nội dung “trông bị lỗi”. Một văn bản có dấu `Ã©` có thể đã trải qua **giải mã thành công hoàn toàn**. Chuyển một chuỗi chữ sang charset nhỏ hơn có thể thất bại ở **encoder** chứ không phải ở decoder.

Việc xác định đúng tầng lỗi là bước đầu để tránh sửa dữ liệu sai cách.

## 5. `CharsetDecoder` và ba `CodingErrorAction`

`java.nio.charset.CharsetDecoder` cho phép chọn chính sách cho **hai nhóm lỗi riêng biệt**:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Các action:

- **`REPORT`:** phát hiện lỗi, trả `CoderResult` trong API tăng dần (*incremental*) hoặc ném `CharacterCodingException` trong convenience decode của `CharsetDecoder`. Dùng khi **tính toàn vẹn dữ liệu quan trọng**.
- **`REPLACE`:** bỏ đoạn lỗi, chèn replacement string tương ứng rồi tiếp tục. Đọc được phần văn bản hợp lệ còn lại, nhưng **mất thông tin**.
- **`IGNORE`:** bỏ đoạn lỗi hoàn toàn rồi tiếp tục. Có thể nối hai đoạn văn bản vốn bị ngăn bởi dữ liệu hỏng, làm thay đổi ý nghĩa.

Tạo file **`DecodePoliciesDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class DecodePoliciesDemo {
    private static String decode(
            byte[] input, CodingErrorAction action) throws Exception {

        CharsetDecoder decoder = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action);

        return decoder.decode(ByteBuffer.wrap(input)).toString();
    }

    public static void main(String[] args) throws Exception {
        byte[] bad = {0x41, (byte) 0xC3, 0x28, 0x42};

        System.out.println(decode(bad, CodingErrorAction.REPLACE)
                .codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList());

        System.out.println(decode(bad, CodingErrorAction.IGNORE));
    }
}
~~~

~~~bash
javac DecodePoliciesDemo.java
java DecodePoliciesDemo
~~~

Kết quả:

~~~text
[U+0041, U+FFFD, U+0028, U+0042]
A(B
~~~

**`IGNORE` không phải phương pháp sửa charset**: nó chỉ bỏ đoạn hỏng. Nếu dữ liệu là tên người, mô tả thanh toán hay văn bản pháp lý, việc bỏ một ký tự có thể làm đổi ý nghĩa mà ứng dụng không có dấu vết.

## 6. Mặc định của decoder mới là `REPORT`

Điều dễ gây nhầm nhất là **`StandardCharsets.UTF_8.newDecoder()`** có chính sách mặc định **`REPORT`** cho malformed và unmappable, còn nhiều API convenience dùng **`REPLACE`**.

Ví dụ:

~~~java
CharsetDecoder decoder =
        StandardCharsets.UTF_8.newDecoder();

System.out.println(decoder.malformedInputAction());
System.out.println(decoder.unmappableCharacterAction());
~~~

Đây là snippet trong method với import `java.nio.charset.*`. Kết quả:

~~~text
REPORT
REPORT
~~~

Lời gọi:

~~~java
decoder.decode(ByteBuffer.wrap(bytes));
~~~

trong trường hợp lỗi sẽ ném `CharacterCodingException`, cụ thể có thể là `MalformedInputException`.

Nhưng:

~~~java
new String(bytes, StandardCharsets.UTF_8);
~~~

với bytes UTF-8 không hợp lệ **thường không ném coding exception**. Constructor nhận `Charset` được tài liệu Java quy định sẽ **thay thế các dãy malformed/unmappable bằng replacement string mặc định**.

Tương tự, `StandardCharsets.UTF_8.decode(ByteBuffer.wrap(bytes))` là convenience API của `Charset`, theo tài liệu cũng hoạt động với chính sách thay thế. **Không được suy luận default của mọi API từ default của `newDecoder()`.**

## 7. `new String(byte[], Charset)` có thể che lỗi

Tạo **`StringDecodeReplacementDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;

public class StringDecodeReplacementDemo {
    public static void main(String[] args) {
        byte[] bytes = {(byte) 0xC3, (byte) 0x28};

        String value =
                new String(bytes, StandardCharsets.UTF_8);

        System.out.println(value.length());
        System.out.println(value.codePointAt(0) == 0xFFFD);
        System.out.println(value.codePointAt(1) == '(');
    }
}
~~~

~~~bash
javac StringDecodeReplacementDemo.java
java StringDecodeReplacementDemo
~~~

Kết quả:

~~~text
2
true
true
~~~

Chuỗi hợp lệ ở tầng `String`, nhưng phần đầu đã được thay bằng `U+FFFD`. Nếu ứng dụng lưu nó vào cơ sở dữ liệu và xóa byte gốc, **không thể biết chắc byte nào đã dẫn tới dấu thay thế đó**.

### Phân biệt replacement có thật với dữ liệu chứa U+FFFD

Một `String` chứa U+FFFD **không chứng minh** nguồn đầu vào hỏng. Người dùng có thể cố tình gửi ký tự U+FFFD đã được encode hợp lệ trong UTF-8. Ngược lại, một luồng có thể đã bị thay bằng `?` hoặc xóa ký tự trước khi đến ứng dụng, nên chuỗi cuối **không có U+FFFD** vẫn có thể đã mất dữ liệu.

Vì vậy, kiểm tra:

~~~java
text.indexOf('\uFFFD') >= 0
~~~

chỉ hữu ích như một **cờ nghi vấn**, không phải bộ xác thực dữ liệu byte gốc. Muốn chứng minh dữ liệu nguồn hợp lệ, phải **kiểm tra strict tại thời điểm decode**, trước khi replacement xảy ra.

## 8. `Files.readString`: strict với byte không hợp lệ

Một khác biệt API quan trọng trong Java 17:

- `Files.readString(path)` mặc định dùng UTF-8.
- `Files.readString(path, charset)` dùng charset tường minh.
- Theo Javadoc Java 17, chúng có thể ném `IOException` khi gặp **malformed hoặc unmappable byte sequence**.

Đây **không** phải hành vi “đương nhiên thay thế giống `new String(bytes, charset)`”.

Ví dụ **`StrictFileReadDemo.java`**:

~~~java
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StrictFileReadDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("utf8-demo-", ".bin");

        try {
            Files.write(file, new byte[]{
                    0x41, (byte) 0xC3, 0x28, 0x42
            });

            try {
                System.out.println(
                        Files.readString(file, StandardCharsets.UTF_8));
            } catch (MalformedInputException ex) {
                System.out.println("Invalid UTF-8");
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac StrictFileReadDemo.java
java StrictFileReadDemo
~~~

Kết quả khi chạy với Java 17:

~~~text
Invalid UTF-8
~~~

Chương trình tạo một file tạm, ghi byte hỏng, thử đọc theo UTF-8 rồi xóa file trong `finally`. Bài học không phải mọi Java file API đều giống nhau; **phải đọc hợp đồng của phương thức cụ thể**.

Nếu cần điều khiển chi tiết `REPORT/REPLACE/IGNORE`, cấu hình `CharsetDecoder` tường minh thay vì đoán hành vi của API convenience.

## 9. `InputStreamReader` có thể thay thế lỗi mặc định

`InputStreamReader(InputStream, Charset)` là cầu nối từ luồng byte sang luồng ký tự. Với constructor nhận `Charset`, các dãy malformed/unmappable thường được xử lý bằng **replacement** theo hợp đồng của Reader.

Ví dụ **`ReaderReplacementDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ReaderReplacementDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = {
                0x41, (byte) 0xC3, 0x28, 0x42
        };

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8)) {

            for (int c; (c = reader.read()) != -1;) {
                System.out.print("U+%04X ".formatted(c));
            }
            System.out.println();
        }
    }
}
~~~

~~~bash
javac ReaderReplacementDemo.java
java ReaderReplacementDemo
~~~

Kết quả:

~~~text
U+0041 U+FFFD U+0028 U+0042
~~~

Nếu cần **Reader báo lỗi**, có thể dùng constructor nhận **`CharsetDecoder` đã cấu hình** thay vì overload nhận `Charset`:

~~~java
CharsetDecoder strict =
        StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

Reader reader = new InputStreamReader(inputStream, strict);
~~~

Đây là **snippet trong method**, cần import `java.io.Reader`, `java.io.InputStreamReader` và các lớp `java.nio.charset`. Biến `inputStream` là luồng đầu vào đã có; phải đóng Reader bằng try-with-resources khi sử dụng.

## 10. Lỗi mã hóa khi ghi: `UnmappableCharacterException`

Chiều ngược lại cũng có rủi ro. `String` Java có thể chứa những ký tự Unicode mà **charset đích không hỗ trợ**.

Ví dụ:
- US-ASCII chỉ biểu diễn tập 7 bit ASCII.
- Chữ `à` (U+00E0) và `ộ` (U+1ED9) không thể biểu diễn thành byte US-ASCII tương ứng.
- Một `CharsetEncoder` được tạo bằng `newEncoder()` mặc định chọn **`REPORT`**, có thể ném `UnmappableCharacterException`.

Tạo **`UnmappableEncodingDemo.java`**:

~~~java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;

public class UnmappableEncodingDemo {
    public static void main(String[] args) {
        String text = "H" + (char) 0x00E0
                + " N" + (char) 0x1ED9 + "i";

        try {
            StandardCharsets.US_ASCII.newEncoder()
                    .encode(CharBuffer.wrap(text));
        } catch (CharacterCodingException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac UnmappableEncodingDemo.java
java UnmappableEncodingDemo
~~~

Kết quả:

~~~text
UnmappableCharacterException
~~~

Đây không phải lỗi UTF-8 và cũng không phải lỗi Java compiler. Bộ mã hóa đích **US-ASCII không có biểu diễn** cho những ký tự nguồn.

### Tại sao nên dùng `CharsetEncoder` khi cần giữ dữ liệu?

Dùng strict encoder giúp phát hiện ký tự không thể chuyển **trước khi ghi file**. Nếu dùng một API mặc định thay thế, thông tin chữ gốc có thể biến thành `?` và bản gốc sẽ mất nếu không được lưu lại.

## 11. `String.getBytes(Charset)` và ký tự `?`

Tương tự convenience decoder, `String.getBytes(Charset)` có thể **thay thế các ký tự không mã hóa được** bằng byte mặc định của charset đích.

Tạo **`QuestionMarkLossDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class QuestionMarkLossDemo {
    public static void main(String[] args) {
        String vietnamese = "H" + (char) 0x00E0
                + " N" + (char) 0x1ED9 + "i";

        byte[] output =
                vietnamese.getBytes(StandardCharsets.US_ASCII);

        System.out.println(Arrays.toString(output));
        System.out.println(new String(
                output, StandardCharsets.US_ASCII));
    }
}
~~~

~~~bash
javac QuestionMarkLossDemo.java
java QuestionMarkLossDemo
~~~

Kết quả:

~~~text
[72, 63, 32, 78, 63, 105]
H? N?i
~~~

Byte thập phân `63` tương ứng dấu hỏi ASCII `?`. Hai ký tự tiếng Việt đã không được biểu diễn; sau khi chỉ còn các byte ASCII này, không thể biết chúng vốn là `à` và `ộ`.

**Lưu ý:** Replacement byte của mỗi charset có thể khác nhau; không được mặc định mọi mã hóa thay lỗi bằng `?`. Với `UTF-8` decoder, ký tự thay thế thường là U+FFFD; với US-ASCII encoder trong ví dụ, replacement là byte cho `?`.

Nếu dữ liệu cần nguyên vẹn, hãy **không dùng đường chuyển đổi âm thầm thay thế** cho những trường hợp mã hóa có thể thất bại.

## 12. Ký tự thay thế U+FFFD là gì?

**U+FFFD REPLACEMENT CHARACTER** là một code point Unicode được sử dụng để biểu thị **dữ liệu ký tự không thể diễn giải đúng** trong nhiều quy trình.

Nó thường hiển thị là:

~~~text
�
~~~

Nhưng hình thức biểu tượng phụ thuộc font, và việc chuỗi chứa U+FFFD chỉ cho biết **giá trị Unicode đã có**. Nó không chứng minh rằng chính ứng dụng hiện tại là bên tạo replacement, vì dữ liệu có thể đã bị thay từ bước trước.

Tìm U+FFFD:

~~~java
boolean containsReplacement =
        text.codePoints().anyMatch(cp -> cp == 0xFFFD);
~~~

Đây là **snippet**, biến `text` là String đã có. Với dữ liệu được truyền qua nhiều tầng, có thể lưu:
- bytes nguồn;
- charset được tuyên bố;
- decoder/policy đã dùng;
- số lượng và vị trí các lỗi nếu thiết kế ghi nhận được;
- hash của bytes gốc để đối chiếu.

Không ghi thẳng dữ liệu nhạy cảm vào log để “debug U+FFFD”. Vị trí byte và mã sự cố thường đủ hơn việc lưu toàn bộ nội dung PII/secret.

## 13. Byte sai, charset sai và *mojibake* là ba chuyện cần tách

Giả sử bạn có ký tự `é`. Mã UTF-8 của nó là hai byte:

~~~text
C3 A9
~~~

Nếu hai byte này được giải mã như **ISO-8859-1**, chúng tương ứng lần lượt U+00C3 và U+00A9. Chuỗi kết quả thường nhìn thành `Ã©`.

**Điểm mấu chốt:** cả hai byte trên đều có ánh xạ hợp lệ theo ISO-8859-1, nên quá trình giải mã **không nhất thiết ném `MalformedInputException`**. Đầu ra sai về ý nghĩa do **đặt sai charset**, không phải do byte trái luật của charset đã chọn.

Tạo **`WrongCharsetDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;

public class WrongCharsetDemo {
    public static void main(String[] args) {
        byte[] bytes = {
                (byte) 0xC3, (byte) 0xA9
        };

        String correct = new String(
                bytes, StandardCharsets.UTF_8);
        String wrong = new String(
                bytes, StandardCharsets.ISO_8859_1);

        System.out.println(correct.codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList());

        System.out.println(wrong.codePoints()
                .mapToObj(cp -> "U+%04X".formatted(cp))
                .toList());
    }
}
~~~

~~~bash
javac WrongCharsetDemo.java
java WrongCharsetDemo
~~~

Kết quả:

~~~text
[U+00E9]
[U+00C3, U+00A9]
~~~

Đây là **mojibake** do thông tin charset sai. Strict decoder không thể tự kết luận byte `C3 A9` “phải là UTF-8” nếu ta đã yêu cầu giải mã ISO-8859-1 và cấu trúc đầu vào hợp lệ theo charset ấy.

**Kết luận:** Báo lỗi strict là cần để phát hiện **byte không hợp lệ**, nhưng **không đủ** để bảo đảm đã chọn **đúng encoding theo nghĩa của nguồn**.

## 14. UTF-8 hợp lệ không có nghĩa đúng ngôn ngữ

Một chuỗi byte có thể hợp lệ đồng thời theo nhiều charset. Thậm chí việc giải mã theo charset sai vẫn có thể tạo những ký tự Unicode nhìn “bình thường”.

Ví dụ:
- Byte ASCII `41` biểu diễn `A` trong cả UTF-8 và US-ASCII.
- Dãy UTF-8 nhiều byte có thể trùng các mã hợp lệ trong ISO-8859-1, nhưng cho các ký tự khác.
- Một file được lưu theo Windows-1252 có thể bị coi là UTF-8 và báo malformed ở các vị trí có byte riêng lẻ cao.
- Một nội dung UTF-8 bị double-encoding có thể tạo ra toàn bộ byte UTF-8 **hợp lệ nhưng text sai**.

Để chọn charset đúng, ưu tiên **hợp đồng dữ liệu**: HTTP `Content-Type`/charset khi áp dụng, định dạng file, cấu hình nguồn, protocol đối tác, BOM và quy tắc của chính định dạng.

Không tự phát minh một heuristic “không có lỗi thì đây chắc là UTF-8” để thay thế metadata của hệ thống. Với dữ liệu di sản, một detector encoding chỉ đưa ra **ước lượng**, cần kiểm thử/đối soát và đôi khi cần can thiệp của con người.

## 15. Chính sách `REPORT`, `REPLACE`, `IGNORE` dùng khi nào?

| Chính sách | Điều xảy ra | Phù hợp hơn với | Rủi ro |
| --- | --- | --- | --- |
| **REPORT** | Dừng hoặc báo coding error | Nhập khẩu dữ liệu nghiệp vụ, thanh toán, định danh, audit, migration | Cần quy trình xử lý lỗi |
| **REPLACE** | Đổi phần lỗi thành replacement | Preview/log có chủ đích, công cụ xem dữ liệu hỏng | Người đọc dễ tưởng đã giữ nguyên nội dung |
| **IGNORE** | Bỏ phần lỗi | Một số pipeline khám phá dữ liệu không quan trọng, có gắn nhãn mất dữ liệu | Mất ký tự âm thầm, nối nội dung không mong muốn |

**Không dùng IGNORE mặc định** cho nội dung quan trọng vì nguy cơ bỏ ký tự hoặc ngăn cách giữa các trường.

Khi phải cho phép dữ liệu hỏng được xem tạm, ứng dụng có thể:
1. Lưu **bytes gốc** ở vùng cách ly.
2. Ghi nhận lỗi decode và charset được dùng.
3. Tạo **bản preview** với `REPLACE`, được gắn nhãn “dữ liệu chưa đầy đủ”.
4. Không dùng bản preview đã thay ký tự để tự động quyết định hóa đơn, số tiền, tên người hoặc khóa định danh.

Mục tiêu là không để một đường xử lý **mất dữ liệu** bị hiểu nhầm là nhập thành công.

## 16. Cấu hình replacement string trên decoder

`CharsetDecoder` có phương thức `replaceWith(String)` để chọn replacement text, nếu giá trị hợp lệ với encoder/decoder tương ứng.

Ví dụ:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("?");

String output = decoder.decode(
        ByteBuffer.wrap(badBytes)).toString();
~~~

Đây là **snippet**; cần import `CharsetDecoder`, `StandardCharsets`, `CodingErrorAction`, `ByteBuffer`; biến `badBytes` là mảng byte đã có.

Việc đặt dấu hỏi ở chiều decode làm **khó chẩn đoán hơn** U+FFFD, vì dữ liệu đầu vào thật có thể vốn chứa dấu hỏi. Dù replacement là U+FFFD, `?` hay chuỗi khác, bản chất vẫn là **không bảo toàn nội dung gốc**.

Với encoder, phương thức `CharsetEncoder.replaceWith(byte[])` đặt **replacement bytes** cho lỗi không thể mã hóa; replacement string và replacement bytes là hai khái niệm ở hai chiều.

## 17. Kiểm tra encoder trước khi ghi

Có thể dùng:

~~~java
CharsetEncoder encoder =
        StandardCharsets.US_ASCII.newEncoder();

boolean supported = encoder.canEncode(text);
~~~

Đây là snippet; biến `text` là `CharSequence`. `canEncode` có thể giúp xác định đoạn Unicode có thể được biểu diễn trong charset đích, nhưng không nên xem nó thay thế hoàn toàn việc mã hóa strict cuối cùng trong một pipeline đồng thời hoặc với dữ liệu được sửa sau kiểm tra.

Thiết kế vững chắc là **mã hóa bằng strict encoder ngay ở bước tạo byte**:

~~~java
ByteBuffer buffer = StandardCharsets.US_ASCII
        .newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .encode(CharBuffer.wrap(text));
~~~

Đây là snippet với `CharBuffer`, `ByteBuffer` và charset imports. `encode` có thể ném `CharacterCodingException`; phải xử lý ở method có `throws` hoặc `try/catch`. Nếu thành công, các byte còn lại trong `ByteBuffer` là kết quả cần ghi.

Đừng gọi `String.getBytes(StandardCharsets.US_ASCII)` sau khi kiểm tra strict rồi nghĩ hai quá trình chắc chắn luôn dùng cùng chính sách; hãy giữ nhất quán trong toàn bộ bước chuyển đổi.

## 18. Ví dụ encode strict và replacement cạnh nhau

Tạo **`EncodePoliciesDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class EncodePoliciesDemo {
    private static byte[] bytes(ByteBuffer buffer) {
        byte[] result = new byte[buffer.remaining()];
        buffer.get(result);
        return result;
    }

    public static void main(String[] args) throws Exception {
        String input = "H" + (char) 0x00E0 + " Noi";

        CharsetEncoder strict =
                StandardCharsets.US_ASCII.newEncoder();

        try {
            strict.encode(CharBuffer.wrap(input));
        } catch (CharacterCodingException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }

        CharsetEncoder replacing =
                StandardCharsets.US_ASCII.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPLACE)
                    .onUnmappableCharacter(CodingErrorAction.REPLACE);

        ByteBuffer encoded =
                replacing.encode(CharBuffer.wrap(input));

        System.out.println(Arrays.toString(bytes(encoded)));
    }
}
~~~

~~~bash
javac EncodePoliciesDemo.java
java EncodePoliciesDemo
~~~

Kết quả:

~~~text
UnmappableCharacterException
[72, 63, 32, 78, 111, 105]
~~~

Đầu ra thứ hai cho thấy `à` đã thành dấu hỏi. Nếu người nhận chỉ nhìn bytes đó, không còn biết bản gốc có dấu. Khi dữ liệu quan trọng, hãy coi lỗi strict là tín hiệu cần **giữ bản gốc** hoặc đổi sang charset phù hợp, thường UTF-8.

## 19. Không chỉ U+FFFD: dấu hỏi và việc bỏ byte là mất dữ liệu

Có ít nhất ba kiểu hỏng phổ biến:

1. **UTF-8 decoding với replacement**: một hoặc nhiều byte hỏng trở thành `U+FFFD`.
2. **Encoding về charset hẹp**: chữ Unicode không thể biểu diễn có thể thành replacement byte, ví dụ `?` trong US-ASCII.
3. **IGNORE**: byte hoặc ký tự lỗi biến mất hoàn toàn.

Sau khi đã chuyển sang kết quả mất thông tin, phép encode ngược không thể phục hồi đầu vào ban đầu. Ví dụ:

~~~java
byte[] malformed = {
        (byte) 0xC3, (byte) 0x28
};

String repaired = new String(
        malformed, StandardCharsets.UTF_8);

byte[] roundTrip = repaired.getBytes(
        StandardCharsets.UTF_8);
~~~

Đây là snippet; `roundTrip` chứa bytes UTF-8 hợp lệ của `U+FFFD` và dấu `(`, chứ không bằng mảng `malformed` lúc đầu.

**Không có phép “khôi phục” duy nhất từ U+FFFD**: nhiều dãy byte khác nhau có thể bị ánh xạ về cùng replacement character. Tương tự, dấu `?` có thể xuất hiện do nguồn thật chứa `?` hoặc do encoder thay ký tự không biểu diễn được.

Vì vậy chỉ có **bytes gốc**, bản sao lưu hoặc metadata nguồn đáng tin mới cho phép sửa lại chính xác.

## 20. Kiểm tra round-trip và giới hạn của nó

Một thử nghiệm để phát hiện mất dữ liệu cụ thể:

~~~java
byte[] original = {/* original bytes */};

String value = strictDecode(original, charset);
byte[] encoded = strictEncode(value, charset);

boolean identical = Arrays.equals(original, encoded);
~~~

Đây là **pseudocode Java dạng snippet**, `strictDecode` và `strictEncode` là hàm do ứng dụng định nghĩa; nó minh họa chiến lược chứ không phải chương trình hoàn chỉnh.

Nếu đầu vào là một charset **có nhiều cách mã hóa cùng nội dung**, hoặc một pipeline thực hiện Unicode normalization, newline conversion, thay BOM hay quy tắc serialize khác, thì **byte-identical round-trip** có thể không phải hợp đồng đúng. Cần phân biệt:

- **Giữ bytes nguyên vẹn**: file/archive/chữ ký số phải có byte equality.
- **Giữ giá trị Unicode**: nội dung text tương đương sau decode/encode có thể đủ, nhưng phải xác định equivalence.
- **Giữ nghĩa nghiệp vụ**: văn bản còn phải qua validation, không chỉ hợp lệ Unicode.

Đừng dùng round-trip như cách phát hiện charset sai tuyệt đối: khi cùng một dãy byte hợp lệ theo charset sai, giải mã và mã hóa lại theo chính charset sai có thể vẫn cho bytes y hệt, dù text đã bị diễn giải sai.

## 21. File charset và default JVM ở Java 17

Java 17 **không mặc định UTF-8 trên mọi hệ điều hành/cấu hình theo cùng một cách**. Các API phụ thuộc `Charset.defaultCharset()` có thể chịu ảnh hưởng môi trường. Từ Java 18, JEP 400 làm UTF-8 trở thành default charset của nhiều API Java SE theo chính sách được định nghĩa, nhưng vẫn cần quan tâm API cụ thể và ngoại lệ.

Trong bài học Java 17+, cách rõ ràng nhất là **truyền charset tường minh**:

~~~java
Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, text, StandardCharsets.UTF_8);
new String(bytes, StandardCharsets.UTF_8);
text.getBytes(StandardCharsets.UTF_8);
~~~

Lưu ý bốn lời gọi này **không có cùng chính sách lỗi** chỉ vì cùng truyền UTF-8. Hai lời gọi `String` thường thay lỗi; `Files.readString` có thể báo lỗi nếu byte không hợp lệ.

Ngoài ra, `Files.writeString` xử lý encoding khác với `String.getBytes` ở một số tình huống. Với dữ liệu cần strict, kiểm tra hợp đồng write method hoặc chủ động dùng `CharsetEncoder` có `REPORT`.

**Không lấy `file.encoding` mặc định làm metadata charset của file đã tồn tại**. File có thể được sinh từ một hệ thống khác trước đó, với charset độc lập.

## 22. BOM, UTF-8 và dữ liệu bị cắt

**BOM (byte order mark)** có thể giúp nhận biết byte order với UTF-16/UTF-32 hoặc xuất hiện trong một số file UTF-8. Nhưng:
- Không phải mọi file có BOM.
- Không nên tin BOM nếu giao thức quy định encoding khác.
- Dữ liệu có BOM không có nghĩa mọi byte phía sau đều hợp lệ.
- Một file bị cắt ngang dãy UTF-8 nhiều byte vẫn có thể gây malformed input.
- Cách API xử lý hoặc giữ U+FEFF phụ thuộc charset và reader/cấu hình.

Nếu dữ liệu đến theo **stream/chunk**, một ký tự UTF-8 có thể nằm vắt qua hai chunk. Chỉ đọc một chunk rồi tự decode nó như **văn bản hoàn chỉnh** có thể nhầm đoạn kết thúc giữa chừng thành malformed, dù byte tiếp diễn nằm ở chunk kế tiếp.

Cách đúng là:
- Giữ `CharsetDecoder` có trạng thái qua các chunk;
- Dùng API decode incremental với `endOfInput=false` cho đến khi nguồn thật kết thúc;
- Chỉ đặt `endOfInput=true` khi không còn byte;
- Xử lý `CoderResult.UNDERFLOW`, `OVERFLOW`, malformed và unmappable theo hợp đồng;
- Gọi `flush` theo quy trình của decoder.

Đừng tự chia `byte[]` ở vị trí bất kỳ rồi gọi `new String(chunk, UTF_8)` nhiều lần nếu mục tiêu là ghép lại text gốc **không mất byte**.

## 23. Streaming decoder và `CoderResult`

`CharsetDecoder.decode(ByteBuffer in, CharBuffer out, boolean endOfInput)` là API **incremental**. Thay vì luôn ném exception, nó có thể trả `CoderResult`:

| Kết quả | Ý nghĩa |
| --- | --- |
| `UNDERFLOW` | Đã xử lý được phần input hiện có; có thể cần thêm byte |
| `OVERFLOW` | Output buffer không còn chỗ |
| `isMalformed()` | Dãy input sai cú pháp theo charset |
| `isUnmappable()` | Input hợp lệ nhưng không ánh xạ được |
| `length()` | Số đơn vị input thuộc đoạn lỗi theo coder |
| `throwException()` | Chuyển result lỗi thành ngoại lệ tương ứng |

Với chế độ `REPORT`, một lỗi không nhất thiết tự ném ra ngay trong overload incremental; caller cần **kiểm tra `CoderResult`**. Nếu code gọi `decode(in,out,endOfInput)` rồi bỏ qua result, dữ liệu có thể bị xử lý sai hoặc vòng lặp không tiến.

Đối với ứng dụng không cần stream lớn, dùng convenience `CharsetDecoder.decode(ByteBuffer)` với strict decoder thường đơn giản và rõ hơn.

## 24. Vấn đề UTF-16 surrogate khi encode

`String` chứa UTF-16 code units và có thể chứa một **unpaired surrogate** (high surrogate hoặc low surrogate không có cặp hợp lệ), ví dụ do dữ liệu bị cắt hoặc API thao tác `char` không an toàn.

Một unpaired surrogate **không tạo thành một Unicode scalar value hợp lệ** để biểu diễn bằng UTF-8. Trong chiều mã hóa, `CharsetEncoder` có thể xem đây là **malformed input**.

Ví dụ:

~~~java
String broken = String.valueOf((char) 0xD800);

CharsetEncoder strict = StandardCharsets.UTF_8.newEncoder();
strict.encode(CharBuffer.wrap(broken));
~~~

Đây là **snippet minh họa lỗi**; gọi `encode` có thể ném `MalformedInputException`. Có thể dùng `Character.isHighSurrogate`, `isLowSurrogate` và logic duyệt code point để kiểm tra cấu trúc UTF-16 khi cần.

**Không phải mọi lỗi encoder đều là `UnmappableCharacterException`**: nếu Unicode đầu vào tự nó có cấu trúc UTF-16 sai, đó là malformed input; nếu code point hợp lệ nhưng charset đích không biểu diễn được, đó là unmappable character.

## 25. Ví dụ strict decoding dùng trong service

Tạo file **`StrictTextDecoder.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.util.Objects;

public final class StrictTextDecoder {
    private StrictTextDecoder() {}

    public static String decode(byte[] bytes, Charset charset)
            throws CharacterCodingException {

        Objects.requireNonNull(bytes, "bytes");
        Objects.requireNonNull(charset, "charset");

        return charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    public static void main(String[] args) {
        byte[] good = {
                (byte) 0x43, (byte) 0x61,
                (byte) 0x66, (byte) 0xC3, (byte) 0xA9
        };
        byte[] bad = {(byte) 0xC3, (byte) 0x28};

        try {
            String result = decode(
                    good, java.nio.charset.StandardCharsets.UTF_8);
            System.out.println(result.codePointCount(
                    0, result.length()));
        } catch (CharacterCodingException ex) {
            System.out.println("Good input rejected");
        }

        try {
            decode(bad, java.nio.charset.StandardCharsets.UTF_8);
            System.out.println("Bad input accepted");
        } catch (CharacterCodingException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac StrictTextDecoder.java
java StrictTextDecoder
~~~

Kết quả:

~~~text
4
MalformedInputException
~~~

Trong chương trình, `good` là UTF-8 của `Café` gồm bốn code point; `bad` chứa byte `0xC3` không có byte tiếp diễn UTF-8 hợp lệ.

Điểm thiết kế:
- Charset do caller truyền tường minh;
- Mọi lỗi coding được xử lý theo `REPORT`;
- Dữ liệu không hỏng có thể dùng như text;
- Dữ liệu hỏng được chuyển sang quy trình xử lý lỗi **trước khi lưu bản thay thế**.

Hàm này **không tự phát hiện charset thật** của bytes. Nếu bytes được mã hóa theo ISO-8859-1 và caller truyền ISO-8859-1, decoding có thể thành công nhưng vẫn cần xác minh protocol nguồn.

## 26. Lỗi nghiệp vụ do replacement

Trong hệ thống thực tế, mất ký tự có thể tạo lỗi không đơn thuần là “chữ hiển thị xấu”:

- **Tên người/địa chỉ**: `Nguyễn` hoặc tên quốc tế có dấu trở thành ký tự `?` hoặc `�`, gây khó đối chiếu hồ sơ.
- **Mã sản phẩm**: nếu ký tự đặc biệt bị bỏ hoặc thay, hai mã khác nhau có thể thành một mã giống nhau.
- **Hóa đơn/thanh toán**: một ký tự bị mất trong thông tin thanh toán có thể dẫn tới kiểm toán khó khăn.
- **CSV import**: dòng được xem là hợp lệ mặc dù một trường đã bị hỏng; sửa downstream không còn biết dữ liệu gốc.
- **Tìm kiếm**: replacement làm từ khóa không còn khớp hoặc làm xuất hiện token mới không có ý nghĩa.
- **Dữ liệu pháp lý**: bản đã thay thế không tương đương nguyên văn chứng cứ.
- **Log bảo mật**: replacement hoặc IGNORE có thể làm mất dấu vết byte đầu vào; nhưng log không nên lưu lộ PII nếu không được phép.

Khi thiết kế import pipeline, hãy xác định rõ **giới hạn được phép mất dữ liệu**. Với dữ liệu cốt lõi, chính sách phù hợp thường là **từ chối lô hoặc cách ly bản ghi**, báo lỗi có vị trí và giữ byte gốc theo quy định.

## 27. Không chỉ charset: phân biệt encoding, normalization và rendering

Có ba tầng khác nhau:

1. **Encoding/decoding:** byte ↔ Unicode; có thể xảy ra `MalformedInputException`, `UnmappableCharacterException`, replacement.
2. **Unicode normalization:** `Normalizer` NFC/NFD/NFKC/NFKD đưa về dạng tương đương theo chuẩn Unicode, **không phải sửa byte mã hóa sai**.
3. **Rendering:** font, layout, Unicode bidi và grapheme shaping quyết định nội dung trông thế nào trên màn hình.

Ví dụ chuỗi `e` + U+0301 và `é` có thể khác code point nhưng cả hai đều **UTF-8 hợp lệ**. Normalizer xử lý canonical equivalence; không phải `MalformedInputException`.

Một chuỗi UTF-8 hợp lệ chứa code point hiếm có thể hiển thị bằng hình vuông vì font không hỗ trợ; không nên “sửa charset” để làm glyph xuất hiện. Chọn font/render engine phù hợp.

**Không gọi Unicode normalization trên U+FFFD để lấy lại ký tự gốc.** Khi byte đã bị thay, normalization không biết các byte bị mất.

## 28. Logging và quan sát lỗi mà không rò rỉ dữ liệu

Khi xử lý lỗi charset trong server/import:
- Ghi **charset được tuyên bố**, nguồn metadata, tên pipeline và mã lỗi.
- Ghi **độ dài input, vị trí tương đối, số lượng đoạn lỗi** nếu được kiểm soát/đo đạc chính xác.
- Giữ **raw bytes** ở nơi cách ly có quyền truy cập và thời hạn lưu phù hợp, khi pháp lý/nghiệp vụ cho phép.
- Với log thông thường, có thể ghi **hex sample được giới hạn/ẩn dữ liệu** thay vì toàn bộ nội dung chứa thông tin nhạy cảm.
- Phân biệt **malformed**, **unmappable**, và **wrong-but-decodable charset** trong thống kê.

Ví dụ thông báo lỗi có ích:

~~~text
Text import rejected:
declaredCharset=UTF-8
error=MalformedInputException
record=42
action=QUARANTINED
~~~

Đây là mẫu thông điệp, không phải stdout của Java demo. Không ghi rằng “record 42 đã sửa xong” nếu decoder chỉ mới phát hiện lỗi hoặc bản preview đã thay ký tự.

## 29. Chiến lược tránh mất dữ liệu trong I/O

Một checklist thực hành:

1. **Dùng charset tường minh** theo hợp đồng, ví dụ `StandardCharsets.UTF_8`, trên cả producer và consumer.
2. **Giữ byte gốc** khi nguồn không tin cậy hoặc cần forensic/retry.
3. **Decode strict** với `CharsetDecoder.newDecoder()` + `REPORT` cho nội dung quan trọng.
4. **Xử lý lỗi rõ ràng**: từ chối, cách ly, hỏi nguồn gửi lại, hoặc cho phép preview có cảnh báo.
5. **Không tự chuyển malformed thành dấu hỏi** rồi ghi đè nội dung gốc.
6. **Encode strict** khi xuất sang charset đích không chắc biểu diễn được tất cả ký tự.
7. **Không đánh đồng “đọc thành công” và “đúng charset”**; kiểm chứng metadata/giao thức.
8. **Không chia byte tùy tiện** trước khi decode trong streaming.
9. **So sánh round-trip đúng hợp đồng** nếu cần byte equality.
10. **Test với tiếng Việt, emoji, surrogate, BOM, UTF-8 hỏng, và các charset legacy**.
11. **Tách mã lỗi kỹ thuật và thông báo người dùng**; người dùng cần biết file sai hoặc phải gửi lại, không cần stack trace.
12. **Đảm bảo các bước trước đó chưa thay thế dữ liệu** trước khi bạn bắt đầu strict decode; nếu byte đã mất ở upstream, decoder không thể phục hồi.

## 30. Bài tập có đáp án

**Câu 1.** `MalformedInputException` cho biết gì?

**Đáp án:** Đơn vị đầu vào không hợp lệ theo cấu trúc charset/encoding đang xử lý, ví dụ UTF-8 sai dãy byte tiếp diễn.

**Câu 2.** `UnmappableCharacterException` khác gì?

**Đáp án:** Đầu vào hợp lệ nhưng không có ánh xạ phù hợp trong charset đích, chẳng hạn cố mã hóa `à` sang US-ASCII.

**Câu 3.** `new String(invalidUtf8, UTF_8)` mặc định có báo lỗi coding không?

**Đáp án:** Với constructor nhận `Charset`, Javadoc quy định thay thế các chuỗi malformed/unmappable bằng replacement string; không dùng nó để xác thực strict.

**Câu 4.** `StandardCharsets.UTF_8.newDecoder()` mặc định dùng action gì?

**Đáp án:** `REPORT` cho malformed và unmappable.

**Câu 5.** `Files.readString(path, UTF_8)` có thể ném gì khi gặp malformed UTF-8?

**Đáp án:** `IOException`, trong trường hợp minh họa có thể là `MalformedInputException`.

**Câu 6.** `CodingErrorAction.IGNORE` có giữ nguyên data không?

**Đáp án:** Không. Nó bỏ phần lỗi; có thể làm thay đổi dữ liệu và không thể khôi phục byte đã bỏ.

**Câu 7.** Có U+FFFD trong chuỗi có chắc nguồn byte hỏng không?

**Đáp án:** Không; U+FFFD có thể vốn là một ký tự hợp lệ đã nằm trong nguồn.

**Câu 8.** Không có U+FFFD trong chuỗi có chứng minh charset đúng không?

**Đáp án:** Không. Mojibake có thể tạo ra toàn các ký tự hợp lệ, hoặc bước trước đã thay bằng dấu hỏi.

**Câu 9.** Byte UTF-8 của `é` là `C3 A9`; nếu đọc theo ISO-8859-1 thì sao?

**Đáp án:** Nhận hai code point `U+00C3` và `U+00A9`, thường nhìn thành `Ã©`, mà không nhất thiết ném exception.

**Câu 10.** Dữ liệu tiếng Việt bị `getBytes(US_ASCII)` thay bằng dấu hỏi. Có thể khôi phục từ kết quả không?

**Đáp án:** Không thể khôi phục duy nhất nếu chỉ còn bytes đã thay. Cần bản gốc hoặc dữ liệu nguồn đáng tin.

**Câu 11.** Nếu một ký tự UTF-8 bị chia giữa hai lần nhận dữ liệu mạng, nên làm gì?

**Đáp án:** Giữ trạng thái decoder hoặc buffer byte chưa đủ; đừng giải mã mỗi chunk như đầu vào đã kết thúc.

**Câu 12.** Khi import dữ liệu định danh quan trọng, nên chọn `REPORT` hay `IGNORE`?

**Đáp án:** Thường chọn `REPORT` và xử lý lỗi theo quy trình để tránh mất nội dung âm thầm.

## 31. Bảng chọn API nhanh

| Nhu cầu | Cách dùng gợi ý | Mức bảo toàn |
| --- | --- | --- |
| Decode byte đã chắc chắn hợp lệ và chấp nhận replacement ở tình huống bất thường | `new String(bytes, charset)` | Có thể mất dữ liệu |
| Decode và **báo mọi coding error** | `charset.newDecoder().decode(ByteBuffer.wrap(bytes))` với `REPORT` | Phát hiện lỗi |
| Decode file nhỏ UTF-8 và báo byte không hợp lệ | `Files.readString(path, UTF_8)` | Phát hiện lỗi theo hợp đồng API |
| Đọc byte stream và tùy chỉnh policy | `InputStreamReader` với `CharsetDecoder` | Tùy decoder |
| Xem preview file hỏng có cảnh báo | `CharsetDecoder` với `REPLACE` | Chỉ bản xem, không lossless |
| Encode strict sang charset đích | `charset.newEncoder().encode(CharBuffer.wrap(text))` | Phát hiện unmappable/malformed |
| Encode nhanh cho dữ liệu đã hợp lệ và chấp nhận replacement | `text.getBytes(charset)` | Có thể mất dữ liệu |
| Đọc văn bản UTF-8 nhưng nhận kết quả sai chữ | Xác minh charset nguồn, kiểm tra raw bytes | Strict không đảm bảo chọn đúng charset |
| Debug bản gốc | Lưu bytes + metadata nguồn theo quyền hạn | Có khả năng xử lý lại |

Lưu ý: chính sách của **một API cụ thể** quan trọng hơn tên charset. `UTF-8` không bảo đảm đường đọc là strict; `US_ASCII` không bảo đảm đường ghi sẽ báo lỗi nếu API chọn replacement.

## 32. Tóm tắt

**Phân biệt ba tầng để tránh lỗi:**

~~~text
Byte malformed?
    → CharsetDecoder REPORT → MalformedInputException
    → REPLACE/IGNORE → dữ liệu có thể mất

Ký tự không mã hóa được?
    → CharsetEncoder REPORT → UnmappableCharacterException
    → REPLACE/IGNORE → ký tự có thể mất

Byte hợp lệ nhưng chọn sai charset?
    → Có thể KHÔNG có exception
    → Chuỗi sai nghĩa (mojibake)
~~~

**Năm điều phải ghi nhớ:**

1. `MalformedInputException` cho biết dãy đầu vào **không hợp lệ** theo charset/coder đang dùng; `UnmappableCharacterException` cho biết đầu vào **hợp lệ nhưng không ánh xạ được**.
2. `CharsetDecoder.newDecoder()` mặc định `REPORT`, còn `new String(bytes, charset)` và một số convenience API có thể **âm thầm thay thế** lỗi.
3. `U+FFFD` là **dấu hiệu của chuỗi đã chứa replacement character**, không phải cơ chế khôi phục byte đã mất.
4. `CodingErrorAction.IGNORE` và `REPLACE` là **chính sách có khả năng mất dữ liệu**, phải được lựa chọn có chủ đích và có nhãn phù hợp.
5. **Charset đúng + chính sách lỗi phù hợp + giữ raw bytes khi cần** mới tạo ra hệ thống I/O đa ngôn ngữ đáng tin; chỉ nhìn thấy một `String` không đủ để chứng minh điều đó.

**Tài liệu chuẩn Java SE 17:**
- [MalformedInputException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/MalformedInputException.html)
- [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).