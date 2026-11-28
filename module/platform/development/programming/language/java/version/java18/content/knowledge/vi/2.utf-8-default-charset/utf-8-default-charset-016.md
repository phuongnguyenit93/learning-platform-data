# BOM, ký tự thay thế và mojibake: các dấu hiệu giúp định vị lỗi mã hóa

> **Chương:** UTF-8 mặc định  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Nhận diện byte-order mark (BOM), ký tự thay thế U+FFFD và mojibake; phân biệt lỗi ở bước đọc byte, giải mã, xử lý chuỗi hay ghi dữ liệu. Biết kiểm tra byte/code point, giải mã nghiêm ngặt và xử lý BOM theo định dạng trên JDK hiện đại.

## 1. Vì sao cần phân biệt BOM, U+FFFD và mojibake?

Khi văn bản hiển thị sai, nguyên nhân thường nằm ở một trong các bước của chuỗi chuyển đổi:

1. Dữ liệu được tạo thành byte bằng một charset.
2. Byte được truyền hoặc lưu trữ.
3. Một chương trình giải mã byte thành chuỗi Unicode.
4. Chuỗi được xử lý trong ứng dụng.
5. Ứng dụng mã hóa chuỗi thành byte để ghi file, gửi HTTP hoặc lưu vào hệ thống khác.
6. Terminal, trình duyệt hoặc công cụ hiển thị byte/chuỗi đó.

Ba dấu hiệu thường gặp có ý nghĩa khác nhau:

- **BOM** là một chữ ký byte ở đầu luồng trong một số định dạng. Nó có thể giúp xác định byte order hoặc báo hiệu encoding, nhưng không phải mọi encoding đều có BOM.
- **U+FFFD REPLACEMENT CHARACTER** là ký tự Unicode được dùng để biểu diễn dữ liệu không thể giải mã đúng trong một số chính sách xử lý lỗi. Nó cũng có thể là ký tự thật có trong văn bản.
- **Mojibake** là văn bản bị hiển thị sai vì byte được giải mã bằng charset không phù hợp hoặc bị chuyển đổi sai nhiều lần. Ví dụ `café` có thể thành `cafÃ©`.

Không thể sửa mọi lỗi bằng cách xóa BOM, thay `�` hoặc đổi charset sang UTF-8. Cần xác định byte gốc và quy tắc encoding của định dạng trước.

## 2. BOM là gì?

BOM là viết tắt của *Byte Order Mark*. Trong Unicode, U+FEFF có thể được mã hóa thành một chuỗi byte đặc trưng ở đầu dữ liệu.

BOM có hai vai trò lịch sử/chức năng cần phân biệt:

- Với UTF-16/UTF-32, BOM có thể chỉ ra thứ tự byte (big-endian hoặc little-endian).
- Với UTF-8, BOM không cần thiết để xác định byte order vì UTF-8 không có nhiều byte order. Một số file vẫn đặt chữ ký UTF-8 ở đầu để nhận diện encoding.

### 2.1. Các chữ ký BOM thường gặp

| Encoding | Byte đầu luồng | Ý nghĩa |
|---|---|---|
| UTF-8 | `EF BB BF` | Chữ ký UTF-8 tùy chọn |
| UTF-16 big-endian | `FE FF` | Chỉ byte order big-endian |
| UTF-16 little-endian | `FF FE` | Chỉ byte order little-endian |
| UTF-32 big-endian | `00 00 FE FF` | Chỉ byte order big-endian |
| UTF-32 little-endian | `FF FE 00 00` | Chỉ byte order little-endian |

UTF-8 không yêu cầu BOM. Một file UTF-8 hợp lệ thường bắt đầu trực tiếp bằng byte của ký tự đầu tiên. Việc có hay không có `EF BB BF` không làm thay đổi encoding của phần nội dung còn lại.

Java bảo đảm các charset chuẩn trong `StandardCharsets`, gồm UTF-8 và UTF-16/UTF-16BE/UTF-16LE. UTF-32 không thuộc nhóm sáu charset chuẩn bắt buộc đó; nếu gặp chữ ký UTF-32, hãy kiểm tra provider/runtime và hợp đồng của định dạng trước khi giải mã.

### 2.2. BOM không phải bộ nhận diện encoding tổng quát

BOM chỉ hữu ích khi định dạng hoặc producer thực sự sử dụng nó. Nếu file không có BOM, không thể kết luận nó là UTF-8, UTF-16 hay một encoding khác chỉ dựa vào vài byte đầu.

Nhiều encoding có chung byte cho văn bản ASCII. Ví dụ chuỗi `Hello` có cùng byte trong UTF-8, US-ASCII và nhiều encoding tương thích ASCII. Vì vậy:

- Có BOM phù hợp: có thêm bằng chứng về encoding hoặc byte order.
- Không có BOM: cần metadata, đặc tả file/giao thức hoặc cấu hình đáng tin cậy.
- Byte không hợp lệ theo UTF-8: có thể file dùng encoding khác hoặc dữ liệu đã hỏng; chưa đủ để kết luận nguyên nhân.

Không dùng heuristic đoán charset làm hợp đồng dữ liệu. Nếu định dạng quy định UTF-8, hãy giải mã UTF-8 và báo lỗi khi byte không hợp lệ.

### 2.3. BOM ở đầu luồng khác U+FEFF trong nội dung

BOM có ý nghĩa chữ ký khi nằm đúng vị trí đầu luồng. U+FEFF xuất hiện ở vị trí khác có thể là một code point của nội dung, không phải chữ ký cần tự động xóa.

Do đó, không nên gọi `String.replace("\uFEFF", "")` trên toàn bộ văn bản. Cách này có thể xóa ký tự hợp lệ ở giữa nội dung. Nếu định dạng cho phép BOM, kiểm tra đúng prefix byte tại offset 0 và chỉ bỏ prefix đó theo quy tắc định dạng.

## 3. Java xử lý BOM UTF-8 như thế nào?

`StandardCharsets.UTF_8` giải mã byte UTF-8. BOM UTF-8 `EF BB BF` được giải mã thành code point U+FEFF; decoder UTF-8 không tự động coi nó là metadata phải loại bỏ.

Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;

public class Utf8BomExample {
    public static void main(String[] args) {
        byte[] bytes = {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
                0x48, 0x69
        };

        String value = new String(bytes, StandardCharsets.UTF_8);

        System.out.println(value.startsWith("\uFEFF"));
        System.out.printf("firstCodePoint=U+%04X%n",
                value.codePointAt(0));
        System.out.println(value.substring(1));
    }
}
~~~

Kết quả:

~~~text
true
firstCodePoint=U+FEFF
Hi
~~~

Chuỗi `value` có U+FEFF ở đầu. Một số công cụ hiển thị ký tự zero-width này nên người dùng chỉ nhìn thấy `Hi`, trong khi phép so sánh chuỗi hoặc parser có thể vẫn bị ảnh hưởng.

### 3.1. Khi nào nên loại bỏ UTF-8 BOM?

Chỉ loại bỏ BOM khi định dạng đầu vào cho phép hoặc quy định chữ ký UTF-8. Ví dụ, ứng dụng đọc file cấu hình có thể chủ động chấp nhận UTF-8 BOM để tương thích với file được tạo bởi editor.

Nếu giao thức hoặc định dạng yêu cầu byte đầu tiên là nội dung UTF-8, không được tự ý bỏ ba byte đầu chỉ vì chúng trùng chữ ký BOM. Quyết định phải dựa vào hợp đồng của file/giao thức.

### 3.2. Bỏ BOM ở lớp byte khi định dạng cho phép

Ví dụ helper cho file UTF-8 nhỏ:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public final class Utf8BomReader {
    private static boolean hasUtf8Bom(byte[] bytes) {
        return bytes.length >= 3
                && (bytes[0] & 0xFF) == 0xEF
                && (bytes[1] & 0xFF) == 0xBB
                && (bytes[2] & 0xFF) == 0xBF;
    }

    public static String decode(byte[] bytes)
            throws CharacterCodingException {
        int offset = hasUtf8Bom(bytes) ? 3 : 0;

        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.wrap(
                bytes, offset, bytes.length - offset).slice();

        return decoder.decode(input).toString();
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
                0x48, 0x69
        };

        System.out.println(decode(bytes));
    }
}
~~~

Kết quả:

~~~text
Hi
~~~

Helper này thể hiện một chính sách cụ thể: đầu vào được coi là UTF-8 và UTF-8 BOM ở đầu file được chấp nhận, bỏ qua. Byte còn lại được giải mã nghiêm ngặt; dữ liệu UTF-8 sai cú pháp làm phát sinh `CharacterCodingException` thay vì âm thầm thay ký tự.

Với file lớn, không nhất thiết dùng `Files.readAllBytes()`. Có thể đọc một prefix nhỏ để kiểm tra BOM, sau đó tiếp tục giải mã bằng stream/decoder theo cùng chính sách.

## 4. Nhận diện BOM bằng byte, không dựa vào ký tự nhìn thấy

Để chẩn đoán, đọc byte thô và hiển thị dạng hexadecimal. Ví dụ với file UTF-8 BOM chứa `Hi`:

~~~text
EF BB BF 48 69
~~~

Ba byte đầu là BOM; `48 69` là `Hi`.

### 4.1. Thứ tự kiểm tra khi có nhiều chữ ký prefix

UTF-32 little-endian bắt đầu bằng `FF FE 00 00`, cũng có hai byte đầu trùng prefix UTF-16 little-endian `FF FE`. Vì vậy, nếu viết bộ nhận diện chữ ký, kiểm tra mẫu dài hơn trước.

Ví dụ:

~~~java
public final class BomDetector {
    public static String detect(byte[] bytes) {
        if (startsWith(bytes, 0x00, 0x00, 0xFE, 0xFF)) {
            return "UTF-32BE";
        }
        if (startsWith(bytes, 0xFF, 0xFE, 0x00, 0x00)) {
            return "UTF-32LE";
        }
        if (startsWith(bytes, 0xEF, 0xBB, 0xBF)) {
            return "UTF-8";
        }
        if (startsWith(bytes, 0xFE, 0xFF)) {
            return "UTF-16BE";
        }
        if (startsWith(bytes, 0xFF, 0xFE)) {
            return "UTF-16LE";
        }
        return "NO_BOM";
    }

    private static boolean startsWith(byte[] bytes, int... prefix) {
        if (bytes.length < prefix.length) {
            return false;
        }
        for (int i = 0; i < prefix.length; i++) {
            if ((bytes[i] & 0xFF) != prefix[i]) {
                return false;
            }
        }
        return true;
    }
}
~~~

Đây chỉ là bộ nhận diện năm chữ ký đã liệt kê, không phải thuật toán phát hiện mọi encoding. Giá trị `UTF-32BE`/`UTF-32LE` chỉ nhận diện chữ ký; cần charset/provider hỗ trợ và quy tắc định dạng tương ứng trước khi giải mã.

### 4.2. Không strip BOM một cách mù quáng

Không được bỏ hai byte đầu chỉ vì file được cho là UTF-16, hoặc ba byte đầu chỉ vì file được cho là UTF-8. Hãy:

1. Xác định định dạng cho phép BOM hay không.
2. Kiểm tra đúng chuỗi byte ở đầu luồng.
3. Chọn charset và byte order theo metadata/đặc tả.
4. Bỏ BOM ở lớp byte nếu nó là chữ ký được định dạng quy định.
5. Giữ nguyên byte gốc khi cần điều tra hoặc lưu trữ forensic.

BOM sai vị trí hoặc không phù hợp với encoding khai báo có thể là dấu hiệu file bị ghép, bị chuyển đổi hoặc metadata không chính xác.

## 5. Ký tự thay thế U+FFFD là gì?

U+FFFD có tên Unicode là REPLACEMENT CHARACTER. Ký tự hiển thị phổ biến là `�`. Nó thường xuất hiện khi một byte sequence không thể được giải mã thành ký tự hợp lệ và API đang dùng chính sách thay thế.

Ví dụ, byte `C3 28` không phải chuỗi UTF-8 hợp lệ: `C3` mở đầu một sequence nhiều byte nhưng `28` (`(`) không phải continuation byte hợp lệ.

~~~java
import java.nio.charset.StandardCharsets;

public class ReplacementCharacterExample {
    public static void main(String[] args) {
        byte[] malformed = {
                (byte) 0xC3, 0x28
        };

        String value = new String(malformed, StandardCharsets.UTF_8);

        System.out.println(value);
        value.codePoints().forEach(codePoint ->
                System.out.printf("U+%04X%n", codePoint));
    }
}
~~~

Kết quả:

~~~text
�(
U+FFFD
U+0028
~~~

Constructor `String(byte[], Charset)` thay thế malformed hoặc unmappable input bằng replacement string của charset. Vì thế, code có thể không ném exception dù dữ liệu nguồn đã sai.

### 5.1. U+FFFD không phải bằng chứng duy nhất của lỗi decode

Một chuỗi có `�` có thể đến từ hai trường hợp:

1. Decoder thay một byte sequence không hợp lệ bằng U+FFFD.
2. Dữ liệu nguồn thực sự chứa ký tự U+FFFD và ký tự đó được mã hóa hợp lệ.

Hai trường hợp này nhìn giống nhau khi chỉ xem chuỗi cuối cùng. Muốn phân biệt, cần giữ byte gốc và giải mã nghiêm ngặt theo charset được kỳ vọng.

Ví dụ, U+FFFD thật trong UTF-8 được mã hóa bằng byte `EF BF BD`. Decoder strict vẫn chấp nhận byte này vì nó là encoding hợp lệ của code point U+FFFD. Nếu byte nguồn là `C3 28`, decoder strict báo malformed input.

### 5.2. `?` và U+FFFD không giống nhau

Dấu hỏi ASCII `?` là code point U+003F, byte UTF-8 `3F`. U+FFFD là một code point khác, có byte UTF-8 `EF BF BD`.

Dấu `?` có thể xuất hiện khi encoder phải thay một ký tự không biểu diễn được trong charset đích. Ví dụ encode `é` bằng US-ASCII có thể thay bằng `?` theo chính sách của API.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class QuestionMarkReplacement {
    public static void main(String[] args) {
        byte[] bytes = "café".getBytes(StandardCharsets.US_ASCII);
        System.out.println(HexFormat.ofDelimiter(" ").formatHex(bytes));
    }
}
~~~

Kết quả:

~~~text
63 61 66 3f
~~~

Byte `3F` không chứa đủ thông tin để khôi phục ký tự `é`. Nếu dữ liệu đã bị thay bằng `?` rồi ghi đè lên bản gốc, không thể khôi phục nội dung chỉ bằng cách đổi charset ở bước đọc.

### 5.3. Đừng xóa hoặc thay mọi U+FFFD trước khi tìm nguyên nhân

Thao tác xóa `�` có thể làm mất ký tự hợp lệ nếu U+FFFD là nội dung thật. Thay mọi U+FFFD bằng dấu hỏi cũng che mất dấu hiệu dữ liệu bị hỏng.

Giữ bản byte gốc, xác định encoding dự kiến và dùng decoder strict để kiểm tra trước khi quyết định sửa dữ liệu.

## 6. Giải mã nghiêm ngặt bằng CharsetDecoder

`CharsetDecoder` cho phép chọn cách xử lý malformed input và unmappable character. `CodingErrorAction` có ba chế độ:

| Chế độ | Hành vi | Khi nào dùng |
|---|---|---|
| `REPORT` | Báo lỗi bằng exception | Dữ liệu cần toàn vẹn, file/giao thức có encoding xác định |
| `REPLACE` | Thay bằng replacement string | Chỉ khi sản phẩm chấp nhận mất thông tin và có chính sách rõ |
| `IGNORE` | Bỏ qua dữ liệu lỗi | Hiếm khi phù hợp; có thể làm mất dữ liệu âm thầm |

Mặc định của một `CharsetDecoder` mới là `REPORT` cho malformed/unmappable input. Tuy nhiên, các API tiện lợi như constructor `String(byte[], Charset)` có thể chọn hành vi thay thế. Không suy luận chính sách lỗi của một API từ mặc định của `CharsetDecoder`.

### 6.1. Ví dụ strict decode

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Decode {
    public static void main(String[] args) {
        byte[] bytes = {(byte) 0xC3, 0x28};

        try {
            String value = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();

            System.out.println(value);
        } catch (CharacterCodingException exception) {
            System.out.println(exception.getClass().getSimpleName());
        }
    }
}
~~~

Kết quả:

~~~text
MalformedInputException
~~~

Strict decode giúp lỗi xuất hiện tại biên byte-to-text, nơi ứng dụng còn có thể ghi lại byte gốc, tên file, offset hoặc metadata để điều tra.

### 6.2. Ví dụ REPLACE có chủ đích

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class ReplaceMalformedUtf8 {
    public static void main(String[] args) throws Exception {
        byte[] bytes = {(byte) 0xC3, 0x28};

        String value = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPLACE)
                .onUnmappableCharacter(CodingErrorAction.REPLACE)
                .replaceWith("\uFFFD")
                .decode(ByteBuffer.wrap(bytes))
                .toString();

        System.out.println(value);
    }
}
~~~

Kết quả:

~~~text
�(
~~~

Dùng `REPLACE` khi yêu cầu sản phẩm cho phép hiển thị phần văn bản còn đọc được và chấp nhận thay thế phần hỏng. Với dữ liệu cần lưu trữ, định danh, chữ ký số hoặc trao đổi nghiệp vụ, nên ưu tiên `REPORT` để tránh làm mất dữ liệu mà không biết.

### 6.3. Các API đọc text không có cùng chính sách lỗi

| API | Cách xử lý malformed/unmappable input |
|---|---|
| `new String(bytes, charset)` | Thay bằng replacement string của charset |
| `String.getBytes(charset)` | Thay ký tự không biểu diễn được bằng replacement bytes |
| `CharsetDecoder` mới | Mặc định `REPORT`; có thể đổi sang `REPLACE`/`IGNORE` |
| `Files.readString(path, charset)` | Báo `MalformedInputException` hoặc `UnmappableCharacterException` khi byte không giải mã được |
| `Files.readString(path)` | Dùng UTF-8 theo hợp đồng API; vẫn báo lỗi với byte UTF-8 malformed |

Hãy đọc Javadoc của API cụ thể trước khi thiết kế test. Đừng giả định mọi API đọc/ghi đều tự thay lỗi hoặc đều ném cùng một exception.

## 7. Mojibake là gì?

Mojibake là văn bản bị biến dạng do giải mã byte bằng charset không đúng với charset đã dùng để mã hóa, hoặc do dữ liệu bị encode/decode sai nhiều lần.

Ví dụ, chuỗi `café` có byte UTF-8:

~~~text
63 61 66 C3 A9
~~~

Nếu các byte đó bị đọc như ISO-8859-1, kết quả là:

~~~text
cafÃ©
~~~

Byte `C3` được diễn giải thành `Ã`, còn `A9` thành `©`. Hai ký tự này đều hợp lệ trong ISO-8859-1, nên decoder không có lý do ném lỗi. Đây là lý do mojibake có thể trông như văn bản hợp lệ nhưng sai nội dung.

### 7.1. Tái hiện mojibake bằng Java

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class MojibakeExample {
    public static void main(String[] args) {
        String original = "café";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);

        String correct = new String(utf8, StandardCharsets.UTF_8);
        String wrong = new String(utf8, StandardCharsets.ISO_8859_1);

        System.out.println(HexFormat.ofDelimiter(" ").formatHex(utf8));
        System.out.println("correct=" + correct);
        System.out.println("wrong=" + wrong);
    }
}
~~~

Kết quả:

~~~text
63 61 66 c3 a9
correct=café
wrong=cafÃ©
~~~

Ví dụ này mô phỏng một lần giải mã sai. Trong hệ thống thực tế, lỗi có thể nằm ở HTTP client/server, import/export CSV, database connection, message broker, shell pipeline hoặc editor.

### 7.2. Những dấu hiệu mojibake thường gặp

| Dấu hiệu nhìn thấy | Nguyên nhân thường gặp | Cần kiểm tra |
|---|---|---|
| `Ã©`, `Ã¡`, `Ã´` | UTF-8 bị giải mã như ISO-8859-1/Windows-1252 | Byte UTF-8 gốc và charset ở bước đọc |
| `â€™`, `â€œ`, `â€“` | Dấu câu UTF-8 bị đọc bằng charset single-byte không phù hợp | Charset metadata của file/HTTP response |
| `Â` xuất hiện trước dấu cách/ký tự đặc biệt | Byte UTF-8 nhiều byte bị diễn giải sai | Byte sequence và bước chuyển đổi trung gian |
| `ï»¿` ở đầu văn bản | UTF-8 BOM bị đọc như ký tự của charset single-byte | Ba byte đầu `EF BB BF` |
| `�` | Decoder thay byte sequence không hợp lệ hoặc nội dung thật chứa U+FFFD | Strict decode trên byte gốc |
| `?` thay cho chữ có dấu | Encoder không biểu diễn được ký tự và đã thay bằng `?` | Charset ở bước ghi/encode; kiểm tra bản gốc |

Đây là dấu hiệu định hướng, không phải quy tắc xác định tuyệt đối. Ví dụ `Ã` có thể là ký tự thật trong ngôn ngữ hoặc dữ liệu; chỉ byte gốc và đặc tả encoding mới xác nhận được mojibake.

### 7.3. Mojibake có thể bị mã hóa lại nhiều lần

Một chuỗi đã bị đọc sai vẫn có thể được encode lại thành byte hợp lệ. Nếu hệ thống tiếp tục đọc/ghi chuỗi đó, lỗi trở nên khó phục hồi hơn.

Ví dụ chuỗi sai `cafÃ©` có thể được mã hóa thành UTF-8 hoàn toàn hợp lệ. Một decoder UTF-8 ở bước tiếp theo không biết rằng chuỗi đã sai từ trước; nó chỉ thấy byte hợp lệ của các ký tự `c`, `a`, `f`, `Ã`, `©`.

Do đó, đổi charset ở bước cuối thường không sửa được dữ liệu. Cần tìm nơi đầu tiên mà byte được giải mã bằng charset sai.

## 8. Phân biệt lỗi decode và lỗi encode

| Giai đoạn | Triệu chứng | Cách điều tra |
|---|---|---|
| Byte → String (decode) | `�`, `cafÃ©`, ký tự điều khiển lạ | Giữ byte gốc, kiểm tra charset và decoder action |
| String → byte (encode) | `?` hoặc replacement byte thay ký tự | Kiểm tra charset đích và khả năng biểu diễn |
| Byte bị cắt/ghép | `MalformedInputException`, ký tự cuối bị lỗi | Kiểm tra length, framing, chunk boundary và truncation |
| BOM xử lý sai | U+FEFF ở đầu, `ï»¿`, parser không nhận token đầu tiên | Kiểm tra prefix byte và chính sách BOM |
| Encode/decode nhiều lần | Chuỗi sai nhưng byte hiện tại vẫn hợp lệ | Truy vết từng boundary và log charset ở mỗi bước |
| Display/terminal | Byte và code point đúng nhưng hình ảnh sai | Kiểm tra font, terminal encoding và renderer |

Một ứng dụng có thể giải mã đúng nhưng terminal hiển thị sai. Ngược lại, terminal có thể hiển thị được văn bản ASCII nhưng dữ liệu Unicode đã bị mất trước đó. Vì vậy, hãy kiểm tra cả byte, code point và nội dung hiển thị.

## 9. Chẩn đoán bằng byte hex và Unicode code point

Khi có lỗi, ghi nhận byte trước khi decode. Với file nhỏ:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class InspectBytes {
    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        int length = Math.min(bytes.length, 32);

        System.out.println("length=" + bytes.length);
        System.out.println("prefix="
                + HexFormat.ofDelimiter(" ").formatHex(bytes, 0, length));
    }
}
~~~

Lệnh chạy:

~~~shell
javac --release 18 -d out InspectBytes.java
java -cp out InspectBytes sample.txt
~~~

Chỉ in prefix 32 byte giúp phát hiện BOM và xem dữ liệu đầu file. Với dữ liệu nhạy cảm, không ghi toàn bộ byte vào log; chỉ ghi phần cần thiết hoặc hash/offset phù hợp.

### 9.1. In code point của chuỗi

~~~java
public class InspectCodePoints {
    public static void main(String[] args) {
        String value = args[0];

        value.codePoints().forEach(codePoint ->
                System.out.printf("U+%04X%n", codePoint));
    }
}
~~~

Ví dụ chuỗi `café` có code point:

~~~text
U+0063
U+0061
U+0066
U+00E9
~~~

Mojibake `cafÃ©` có code point khác:

~~~text
U+0063
U+0061
U+0066
U+00C3
U+00A9
~~~

Nếu terminal không hiển thị được chữ, danh sách code point vẫn cho biết nội dung chuỗi mà JVM đang giữ. Code point không thay thế byte gốc; nó cho biết kết quả sau decode.

### 9.2. Một bảng so sánh nhanh

| Nội dung mong muốn | Byte UTF-8 | Kết quả khi decode đúng | Kết quả khi decode sai |
|---|---|---|---|
| `café` | `63 61 66 C3 A9` | `café` | `cafÃ©` khi đọc ISO-8859-1 |
| `Hi` có UTF-8 BOM | `EF BB BF 48 69` | `U+FEFF` rồi `Hi` nếu giữ BOM | `ï»¿Hi` nếu đọc BOM bằng ISO-8859-1 |
| Byte malformed | `C3 28` | Strict decoder báo lỗi | `�(` khi dùng API thay thế |
| Ký tự U+FFFD thật | `EF BF BD` | `�` | Vẫn là `�` nếu decode UTF-8 đúng |

Bảng này giúp xác định vì sao chỉ nhìn một chuỗi hiển thị không đủ để kết luận byte nguồn.

## 10. Quy trình xử lý file UTF-8 có BOM hoặc byte lỗi

Với một file được đặc tả là UTF-8 và có thể chứa BOM tùy chọn, quy trình nên là:

1. Đọc một prefix byte hoặc giữ nguyên byte gốc.
2. Kiểm tra `EF BB BF` tại offset 0.
3. Nếu định dạng cho phép UTF-8 BOM, bỏ đúng ba byte chữ ký.
4. Giải mã phần còn lại bằng UTF-8 với `CodingErrorAction.REPORT`.
5. Nếu có `MalformedInputException`, ghi vị trí/byte liên quan và từ chối hoặc đưa vào quy trình xử lý lỗi.
6. Nếu decode thành công nhưng có U+FFFD, xác định đó là nội dung thật hay byte đã bị thay thế ở bước trước.
7. Xác nhận code point/nội dung theo fixture hoặc schema.
8. Khi ghi lại, dùng `StandardCharsets.UTF_8` explicit theo định dạng.
9. Không ghi đè file gốc trước khi xác nhận dữ liệu phục hồi đúng.

Ví dụ đọc file UTF-8 nghiêm ngặt, cho phép BOM:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadUtf8FileStrict {
    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        int offset = bytes.length >= 3
                && (bytes[0] & 0xFF) == 0xEF
                && (bytes[1] & 0xFF) == 0xBB
                && (bytes[2] & 0xFF) == 0xBF
                ? 3 : 0;

        String text = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(
                        bytes, offset, bytes.length - offset).slice())
                .toString();

        System.out.println(text);
    }
}
~~~

Ví dụ phù hợp với file nhỏ. Với file lớn, dùng stream/channel và decoder incremental; không cần nạp toàn bộ dữ liệu vào heap.

## 11. Phòng tránh mojibake trong ứng dụng

### 11.1. Chỉ giải mã ở boundary

Khi byte đi vào ứng dụng, xác định charset theo giao thức/định dạng và giải mã đúng một lần. Sau đó xử lý dữ liệu ở dạng `String`/Unicode trong nội bộ. Khi gửi hoặc lưu ra ngoài, encode theo charset mà đích yêu cầu.

Không chuyển qua lại giữa byte và String bằng default charset một cách tùy tiện.

### 11.2. Chỉ định charset explicit cho định dạng dữ liệu

Ví dụ ghi/đọc UTF-8:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("message.txt");
Files.writeString(file, "Xin chào", StandardCharsets.UTF_8);
String text = Files.readString(file, StandardCharsets.UTF_8);
~~~

JEP 400 làm UTF-8 thành default charset trên JDK 18+ theo cấu hình mặc định. Tuy vậy, việc chỉ định charset explicit vẫn quan trọng vì:

- Hợp đồng file/giao thức được thể hiện ngay trong code.
- Code không phụ thuộc vào default charset hoặc compatibility option.
- Người đọc biết chính xác encoding cần dùng.
- Test có thể kiểm tra byte output ổn định.

### 11.3. Kiểm tra metadata tại mỗi boundary

Tùy loại dữ liệu, charset có thể được quy định bởi:

- HTTP `Content-Type` parameter `charset`.
- Đặc tả file hoặc metadata của file import.
- Cấu hình kết nối/database driver.
- Protocol/message schema.
- API contract của hệ thống tích hợp.

Không lấy charset từ một metadata không đáng tin cậy mà không xác thực. Nếu metadata mâu thuẫn với BOM hoặc đặc tả format, báo lỗi hoặc áp dụng quy tắc ưu tiên đã được thiết kế; đừng đoán ngẫu nhiên.

### 11.4. Không sửa mojibake bằng thay thế chuỗi toàn cục

Tránh các cách sửa như:

- Thay tất cả `Ã` thành `á`.
- Xóa mọi `Â`.
- Thay `�` thành chuỗi rỗng.
- Encode lại chuỗi sai bằng UTF-8 rồi hy vọng ký tự tự phục hồi.

Những thao tác này có thể phá văn bản hợp lệ. Nếu còn byte gốc và biết chính xác charset đã dùng sai, có thể tái dựng bằng cách đảo đúng chuỗi decode/encode. Nếu dữ liệu đã bị thay thế bằng `?` hoặc bị mất byte, có thể không thể phục hồi.

## 12. Bài tập thực hành

### Bài 1 — Nhận diện UTF-8 BOM

Tạo file chứa `EF BB BF 48 69`. Đọc bằng `new String(bytes, UTF_8)` và in code point đầu tiên.

**Tiêu chí đạt:** Nhận diện U+FEFF và giải thích vì sao nó vẫn nằm trong String.

### Bài 2 — Bỏ BOM theo chính sách file

Dùng `Utf8BomReader` với file có và không có BOM.

**Tiêu chí đạt:** Chỉ bỏ prefix ở đầu luồng khi định dạng cho phép; phần text sau decode giống nhau.

### Bài 3 — Phân biệt malformed input với U+FFFD thật

Giải mã byte `C3 28` bằng `String` constructor và bằng decoder `REPORT`. Sau đó giải mã byte `EF BF BD` bằng decoder `REPORT`.

**Tiêu chí đạt:** Giải thích vì sao trường hợp đầu có lỗi byte còn trường hợp sau là encoding hợp lệ của U+FFFD.

### Bài 4 — Tái hiện mojibake

Encode `café` bằng UTF-8 rồi decode cùng byte bằng ISO-8859-1.

**Tiêu chí đạt:** Nhận ra `cafÃ©`, kiểm tra byte hex và code point để xác định sai ở bước decode.

### Bài 5 — Phân biệt `?` và `�`

Encode `café` bằng US-ASCII và in byte hex. So sánh với chuỗi chứa U+FFFD được encode bằng UTF-8.

**Tiêu chí đạt:** Phân biệt U+003F với U+FFFD và giải thích dữ liệu có thể đã mất không thể khôi phục chỉ bằng đổi charset.

### Bài 6 — Viết báo cáo chẩn đoán

Chọn một file văn bản hiển thị sai. Ghi byte prefix, BOM, charset theo đặc tả, kết quả strict decode, code point đáng chú ý và bước chuyển đổi nghi ngờ.

**Tiêu chí đạt:** Đưa ra kết luận có bằng chứng từ byte/code point; không chỉ dựa vào ảnh chụp văn bản.

## 13. Checklist điều tra lỗi mã hóa

- [ ] Giữ bản byte gốc trước khi decode hoặc sửa file.
- [ ] Xác định encoding theo hợp đồng file/giao thức.
- [ ] Kiểm tra BOM ở đúng đầu luồng bằng byte hex.
- [ ] Không suy ra UTF-8 chỉ vì file không có BOM.
- [ ] Phân biệt U+FFFD thật với ký tự thay thế do decoder tạo.
- [ ] Phân biệt dấu `?` U+003F với U+FFFD.
- [ ] Dùng decoder `REPORT` khi cần phát hiện malformed/unmappable input.
- [ ] Kiểm tra charset của cả bước encode và decode.
- [ ] Kiểm tra metadata HTTP/file/database tại boundary.
- [ ] In code point khi terminal/font có thể hiển thị sai.
- [ ] Không strip mọi U+FEFF hoặc thay mọi `Ã`/`�` theo cách toàn cục.
- [ ] Chỉ sửa dữ liệu sau khi xác định được chuỗi chuyển đổi sai.

## 14. Tài liệu chính thức

1. [The Unicode Standard — Byte Order Mark](https://www.unicode.org/faq/utf_bom.html): ý nghĩa BOM và cách sử dụng trong Unicode.
2. [Charset — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): charset, encoder, decoder và charset chuẩn.
3. [StandardCharsets — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset Java bắt buộc hỗ trợ.
4. [CharsetDecoder — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed input, unmappable input và CodingErrorAction.
5. [CodingErrorAction — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CodingErrorAction.html): REPORT, REPLACE và IGNORE.
6. [String — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): hành vi chuyển đổi byte/charset của constructor và `getBytes`.
7. [Files — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): đọc/ghi chuỗi với charset explicit và lỗi malformed input.
8. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset UTF-8 từ JDK 18 và lưu ý tương thích.

**Kết quả cần đạt:** Có thể nhìn byte hex, BOM, U+FFFD và dấu hiệu mojibake để khoanh vùng lỗi; phân biệt lỗi decode với lỗi encode; dùng strict decoder khi cần toàn vẹn; và chỉ bỏ BOM hoặc phục hồi văn bản theo đúng hợp đồng của định dạng. UTF-8 mặc định từ JDK 18 giúp giảm khác biệt môi trường, nhưng không thay thế việc xác định charset ở từng boundary dữ liệu.
