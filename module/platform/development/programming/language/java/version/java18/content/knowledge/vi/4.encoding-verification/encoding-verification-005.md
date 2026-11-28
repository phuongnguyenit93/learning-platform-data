# Phân biệt lỗi đọc sai charset, ghi sai charset và mã hóa lặp hai lần

## 1. Mục tiêu: xác định dữ liệu bị sai ở bước nào

Trong module **JAVA_VERSION_JAVA18**, Java 18 chuẩn hóa UTF-8 thành charset mặc định cho các API Java chịu ảnh hưởng theo [JEP 400](https://openjdk.org/jeps/400). Điều này giúp chương trình mới có hành vi nhất quán hơn giữa các hệ điều hành. Tuy nhiên, một ứng dụng vẫn có thể đọc byte bằng charset không đúng, ghi văn bản theo charset trái với hợp đồng, hoặc biến một chuỗi đã bị giải mã sai thành một dãy byte UTF-8 mới.

Bài thuộc chương **Kiểm chứng mã hóa**. Ta sẽ phân biệt ba lỗi dễ bị gọi chung là “lỗi encoding”:

1. **Đọc sai charset:** byte nguồn còn nguyên, nhưng chuyển byte thành String bằng charset sai nên nội dung trong bộ nhớ đã sai.
2. **Ghi sai charset:** String trong bộ nhớ đúng, nhưng mã hóa nó thành byte bằng charset không đúng với định dạng đích.
3. **Mã hóa lặp hai lần (double encoding theo nghĩa thường gặp):** dữ liệu byte bị diễn giải thành ký tự sai, rồi chuỗi sai đó lại được mã hóa thành byte mới. Kết quả có thể là UTF-8 hoàn toàn hợp lệ nhưng biểu diễn sai nội dung ban đầu.

Sau bài này, bạn có thể dùng byte hex, code point và hợp đồng charset để tìm đúng điểm gây lỗi; giải thích vì sao round-trip đôi khi vẫn đạt; và chọn cách khắc phục mà không làm hỏng thêm dữ liệu.

## 2. Phân biệt ba loại lỗi bằng cùng một ví dụ

Dùng chuỗi ngắn **café**. Ký tự **é** ở dạng dựng sẵn là U+00E9. UTF-8 của nó gồm hai byte **C3 A9**; ISO-8859-1 biểu diễn U+00E9 bằng một byte **E9**.

| Trạng thái | Chuỗi / code point | Byte hex | Nhận xét |
| --- | --- | --- | --- |
| Văn bản gốc | **café** — U+0063 U+0061 U+0066 U+00E9 | UTF-8: **63 61 66 C3 A9** | Chuỗi và byte chuẩn theo hợp đồng UTF-8. |
| Đọc UTF-8 bằng ISO-8859-1 | U+0063 U+0061 U+0066 U+00C3 U+00A9 | Byte nguồn vẫn **63 61 66 C3 A9** | Byte không đổi; String đã sai do giải mã nhầm. |
| Ghi chuỗi gốc bằng ISO-8859-1 | **café** — U+0063 U+0061 U+0066 U+00E9 | **63 61 66 E9** | String đúng; byte không tuân theo hợp đồng UTF-8. |
| Mã hóa lại chuỗi đọc sai bằng UTF-8 | U+0063 U+0061 U+0066 U+00C3 U+00A9 | **63 61 66 C3 83 C2 A9** | Chuỗi sai đã được biến thành một dãy UTF-8 mới, hợp lệ nhưng sai nội dung. |

Bảng ghi code point để tránh phụ thuộc cách font hiển thị ký tự mojibake.

### 2.1. Lỗi đọc sai charset

Luồng byte được tạo theo UTF-8 nhưng đầu nhận dùng ISO-8859-1:

```java
byte[] source = "café".getBytes(StandardCharsets.UTF_8);

// Sai: byte UTF-8 bị diễn giải như ISO-8859-1.
String wrong = new String(source, StandardCharsets.ISO_8859_1);

// Đúng: dùng charset mà bên phát đã cam kết.
String correct = new String(source, StandardCharsets.UTF_8);
```

Điểm quan trọng: **source vẫn chứa byte UTF-8 ban đầu**. Sai lệch xuất hiện ở bước tạo String. ISO-8859-1 ánh xạ từng byte sang một ký tự, nên không báo lỗi; nó tạo ra một chuỗi khác nhưng vẫn hợp lệ trong Java.

Nếu còn byte nguồn, cách sửa đúng là giải mã lại chính byte đó bằng charset đã được quy định. Đừng sửa bằng cách thay chuỗi mojibake theo cảm tính, vì ký tự đó có thể là dữ liệu thật trong một trường hợp khác.

### 2.2. Lỗi ghi sai charset

Ở chiều ngược lại, String có thể hoàn toàn đúng nhưng byte được ghi sai định dạng:

```java
String text = "café";

// Sai nếu file hoặc giao thức yêu cầu UTF-8.
byte[] wrongOutput = text.getBytes(StandardCharsets.ISO_8859_1);

// Đúng theo hợp đồng UTF-8.
byte[] correctOutput = text.getBytes(StandardCharsets.UTF_8);
```

Trong ví dụ, byte ISO-8859-1 là **63 61 66 E9**, còn UTF-8 là **63 61 66 C3 A9**. Nếu phía nhận chờ UTF-8, byte E9 đứng riêng không phải một chuỗi UTF-8 hợp lệ và decoder nghiêm ngặt sẽ báo lỗi.

Một lỗi ghi có thể bị bỏ sót khi dữ liệu chỉ gồm ASCII: các ký tự ASCII có cùng byte trong UTF-8 và nhiều charset phổ biến. Vì vậy, test chỉ có **Hello 123** không đủ để xác nhận hợp đồng UTF-8; hãy thêm tiếng Việt, ký tự có dấu hoặc emoji.

### 2.3. Mã hóa lặp hai lần sau khi đã đọc sai

Một quy trình thường gặp là:

```text
Byte UTF-8 gốc:             63 61 66 C3 A9
       |
       | decode nhầm ISO-8859-1
       v
String sai:                 U+0063 U+0061 U+0066 U+00C3 U+00A9
       |
       | encode String sai thành UTF-8
       v
Byte UTF-8 mới:             63 61 66 C3 83 C2 A9
       |
       | decode UTF-8 đúng
       v
Văn bản vẫn sai:            U+0063 U+0061 U+0066 U+00C3 U+00A9
```

Dãy byte mới là UTF-8 hợp lệ. Vì vậy, decoder UTF-8 nghiêm ngặt **không thể phát hiện rằng nội dung ban đầu đã bị đọc sai**. Nó chỉ xác nhận byte mới hợp lệ theo UTF-8.

Cụm từ “mã hóa hai lần” đôi khi được dùng chưa chính xác. Chỉ gọi `getBytes(UTF_8)` hai lần không tự làm hỏng một String: mỗi lần mã hóa cùng một String đúng sẽ tạo cùng byte. Lỗi thường xảy ra khi byte của lần mã hóa trước bị chuyển ngược thành String bằng charset sai, hoặc một lớp trung gian coi byte như văn bản rồi mã hóa lại.

## 3. Ví dụ Java tái hiện và đo byte ở từng bước

Lưu lớp dưới đây thành **CharsetMistakeLab.java** bằng UTF-8. Chương trình in chuỗi, code point và byte hex cho cả ba trường hợp. Các phép mã hóa/giải mã nghiêm ngặt dùng `CodingErrorAction.REPORT`, giúp phát hiện dữ liệu không thể biểu diễn theo charset đã chọn.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.Locale;

public final class CharsetMistakeLab {
    public static void main(String[] args) throws Exception {
        String original = "café";
        byte[] utf8 = encodeStrict(original, StandardCharsets.UTF_8);

        // 1. Đọc sai charset: byte vẫn giữ nguyên, String đổi nghĩa.
        String wrongRead = decodeStrict(utf8, StandardCharsets.ISO_8859_1);

        // 2. Ghi sai charset: String gốc đúng, byte không phải UTF-8.
        byte[] wrongWrite = encodeStrict(
                original, StandardCharsets.ISO_8859_1);

        // 3. Mã hóa lại String mojibake thành UTF-8.
        byte[] reencodedMojibake = encodeStrict(
                wrongRead, StandardCharsets.UTF_8);

        show("ORIGINAL_TEXT", original);
        show("ORIGINAL_CODE_POINTS", codePoints(original));
        show("ORIGINAL_UTF8", hex(utf8));

        show("WRONG_READ_TEXT", wrongRead);
        show("WRONG_READ_CODE_POINTS", codePoints(wrongRead));
        show("SOURCE_BYTES_UNCHANGED", hex(utf8));

        show("WRONG_WRITE_BYTES_ISO_8859_1", hex(wrongWrite));
        show("WRONG_WRITE_STRING_UNCHANGED", codePoints(original));

        show("REENCODED_MOJIBAKE_UTF8", hex(reencodedMojibake));
        show("REENCODED_TEXT_CODE_POINTS", codePoints(wrongRead));

        // UTF-8 strict decoder từ chối byte E9 đơn lẻ trong ví dụ này.
        try {
            decodeStrict(wrongWrite, StandardCharsets.UTF_8);
            throw new AssertionError("Không mong đợi byte E9 là UTF-8 hợp lệ");
        } catch (CharacterCodingException expected) {
            show("WRONG_WRITE_AS_UTF8", "REJECTED");
        }

        // Phục hồi minh họa: chỉ an toàn khi biết chính xác charset đọc sai
        // là ISO-8859-1 và phép ánh xạ byte <-> ký tự đã bảo toàn mọi byte.
        byte[] recoveredBytes = encodeStrict(
                wrongRead, StandardCharsets.ISO_8859_1);
        String recoveredText = decodeStrict(
                recoveredBytes, StandardCharsets.UTF_8);
        show("RECOVERED_TEXT", recoveredText);
        show("RECOVERY_MATCHES_ORIGINAL", original.equals(recoveredText));
    }

    private static byte[] encodeStrict(String text, Charset charset)
            throws CharacterCodingException {
        ByteBuffer buffer = charset.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(text));

        byte[] bytes = new byte[buffer.remaining()];
        buffer.get(bytes);
        return bytes;
    }

    private static String decodeStrict(byte[] bytes, Charset charset)
            throws CharacterCodingException {
        return charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ").withUpperCase().formatHex(bytes);
    }

    private static String codePoints(String text) {
        StringBuilder result = new StringBuilder();
        text.codePoints().forEach(cp -> {
            if (result.length() > 0) result.append(' ');
            result.append(String.format(Locale.ROOT, "U+%04X", cp));
        });
        return result.toString();
    }

    private static void show(String label, String value) {
        System.out.println(label + "=" + value);
    }
}
```

Biên dịch và chạy trên JDK 18 hoặc mới hơn:

```bash
javac -encoding UTF-8 CharsetMistakeLab.java
java CharsetMistakeLab
```

Kết quả quan trọng cần đối chiếu:

| Nhãn | Kết quả kỳ vọng |
| --- | --- |
| `ORIGINAL_UTF8` | `63 61 66 C3 A9` |
| `WRONG_READ_CODE_POINTS` | `U+0063 U+0061 U+0066 U+00C3 U+00A9` |
| `WRONG_WRITE_BYTES_ISO_8859_1` | `63 61 66 E9` |
| `REENCODED_MOJIBAKE_UTF8` | `63 61 66 C3 83 C2 A9` |
| `WRONG_WRITE_AS_UTF8` | `REJECTED` |
| `RECOVERY_MATCHES_ORIGINAL` | `true` |

Ví dụ phục hồi trong chương trình chỉ chứng minh trường hợp ISO-8859-1 cụ thể. Không áp dụng nó tự động cho dữ liệu người dùng hoặc dữ liệu đã đi qua nhiều hệ thống.

## 4. Cách nhận biết lỗi ở đúng ranh giới

| Câu hỏi | Đọc sai charset | Ghi sai charset | Mã hóa lặp sau mojibake |
| --- | --- | --- | --- |
| String trước bước lỗi | Đang được tạo từ byte nguồn | Đúng | Đã sai từ bước giải mã trước |
| Byte tại đầu vào | Có thể đúng theo hợp đồng | Không phải trọng tâm; String đã đúng | Ban đầu có thể đúng, nhưng sau đó bị thay bằng byte mới |
| Bước gây lỗi | `new String(bytes, wrongCharset)` hoặc Reader sai charset | `getBytes(wrongCharset)`, Writer sai charset | Encode lại một String mojibake, thường bằng UTF-8 |
| Dấu hiệu byte | Byte gốc đúng, String/code point sai | Byte đầu ra khác định dạng đích | Byte mới có thể là UTF-8 hợp lệ nhưng dài hơn |
| Cách khắc phục | Đọc lại byte gốc bằng charset đúng | Ghi lại String đúng bằng charset đích yêu cầu | Sửa tại bước đọc đầu tiên; nếu cần phục hồi thì chứng minh phép đảo ngược chính xác |

### 4.1. Đọc sai charset không phải lúc nào cũng bị decoder báo lỗi

Một điểm dễ nhầm: chế độ nghiêm ngặt `REPORT` chỉ báo khi byte **không hợp lệ theo charset được chọn**. Nó không thể biết người viết đã chọn nhầm charset.

Ví dụ, byte UTF-8 `C3 A9` cũng là hai byte hợp lệ trong ISO-8859-1. Decoder ISO-8859-1 không có lý do kỹ thuật để ném lỗi; nó ánh xạ từng byte thành ký tự U+00C3 và U+00A9. Đây là lỗi hợp đồng/diễn giải, không phải lỗi cú pháp byte.

Ngược lại, nếu byte `E9` được đưa vào decoder UTF-8 nghiêm ngặt, decoder sẽ báo malformed input vì một byte continuation đơn lẻ không thể bắt đầu chuỗi UTF-8. Bằng chứng này phát hiện được byte sai theo UTF-8, nhưng không tự xác định charset đúng là ISO-8859-1 hay một charset khác.

### 4.2. Không thể tự động đoán charset chỉ từ một chuỗi byte bất kỳ

- Byte ASCII thường hợp lệ dưới nhiều charset, nên không đủ để phân biệt UTF-8 với ISO-8859-1 hoặc các charset tương thích ASCII.
- Một chuỗi byte có thể hợp lệ dưới nhiều charset nhưng mang ý nghĩa khác nhau.
- BOM, header HTTP, khai báo trong định dạng file, metadata của cơ sở dữ liệu hoặc tài liệu API có thể cung cấp manh mối; hãy tuân theo quy tắc của định dạng cụ thể.
- Nếu không có metadata hay hợp đồng từ bên phát, việc đoán charset chỉ là suy luận xác suất, không phải bằng chứng chắc chắn.

## 5. Khắc phục đúng theo loại lỗi

### 5.1. Nếu còn byte nguồn: giải mã lại ngay tại điểm đọc

Khi byte nguồn còn nguyên, hãy dùng đúng charset được bên phát hoặc định dạng dữ liệu quy định:

```java
byte[] sourceBytes = Files.readAllBytes(Path.of("input.txt"));

// Nếu hợp đồng của input.txt là UTF-8:
String text = decodeStrict(sourceBytes, StandardCharsets.UTF_8);
```

Với stream, nêu charset ngay khi tạo Reader:

```java
try (var reader = new java.io.InputStreamReader(
        Files.newInputStream(Path.of("input.txt")),
        StandardCharsets.UTF_8)) {
    // Đọc ký tự từ Reader.
}
```

Đừng sửa mojibake sau khi đã chuyển thành String nếu bạn vẫn có thể quay lại byte gốc. Đọc đúng ngay từ đầu giúp giữ được bằng chứng và tránh một lần chuyển đổi có thể làm mất dữ liệu.

### 5.2. Nếu String đúng: mã hóa theo hợp đồng của đích

Khi định dạng file là UTF-8, dùng API có charset tường minh:

```java
Path output = Path.of("output.txt");
Files.writeString(output, text, StandardCharsets.UTF_8);

String restored = Files.readString(output, StandardCharsets.UTF_8);
if (!text.equals(restored)) {
    throw new IllegalStateException("Nội dung file không khớp");
}
```

`Files.writeString(Path, CharSequence)` và `Files.readString(Path)` có quy tắc UTF-8 cố định từ Java 11. Dùng overload có `Charset` giúp hợp đồng thể hiện ngay tại nơi gọi, đặc biệt khi dự án có nhiều định dạng file khác nhau.

Đối với HTTP, hãy gửi byte được mã hóa theo charset mà media type và API quy định, đồng thời khai báo metadata phù hợp khi định dạng yêu cầu. Đối với tiến trình con, dùng charset mà chương trình con cam kết ở stdin/stdout. Không mặc định mọi giao thức hoặc công cụ ngoài đều nhận UTF-8 chỉ vì JVM hiện tại dùng UTF-8 mặc định.

### 5.3. Nếu đã có String mojibake: chỉ phục hồi khi chứng minh được tính đảo ngược

Trong ví dụ ISO-8859-1, mỗi byte có ánh xạ một-một sang ký tự U+0000 đến U+00FF. Nếu String sai được tạo **chính xác** bằng cách giải mã byte nguồn theo ISO-8859-1, có thể mã hóa String đó ngược lại bằng ISO-8859-1 để khôi phục byte rồi giải mã byte theo UTF-8:

```java
String mojibake = new String(originalUtf8Bytes, StandardCharsets.ISO_8859_1);

byte[] recoveredBytes = encodeStrict(
        mojibake, StandardCharsets.ISO_8859_1);

String recovered = decodeStrict(
        recoveredBytes, StandardCharsets.UTF_8);
```

Chỉ thực hiện khi biết chắc charset đã dùng nhầm, phép ánh xạ không thay thế hoặc bỏ ký tự, và không có bước chỉnh sửa/chuẩn hóa trung gian. Nếu một decoder hoặc encoder trước đó đã thay ký tự không biểu diễn được bằng `?` hoặc U+FFFD, byte ban đầu có thể đã mất vĩnh viễn.

Cũng cần phân biệt ISO-8859-1 với Windows-1252: vùng byte 80–9F có cách ánh xạ khác nhau. Không dùng ISO-8859-1 để đảo ngược dữ liệu vốn được đọc bằng Windows-1252, hoặc ngược lại, rồi giả định kết quả chính xác.

## 6. Những API Java cần dùng rõ charset trên JDK hiện đại

| API / cách gọi | Hành vi | Khuyến nghị |
| --- | --- | --- |
| `new String(bytes, charset)` | Giải mã byte bằng charset chỉ định | Dùng charset của định dạng hoặc bên phát. |
| `new String(bytes)` | Dùng default charset của JVM | Tránh trong code xử lý dữ liệu có hợp đồng; chỉ dùng khi thật sự muốn default. |
| `text.getBytes(charset)` | Mã hóa String bằng charset chỉ định | Dùng charset đích quy định. |
| `text.getBytes()` | Dùng default charset của JVM | Tránh phụ thuộc cấu hình runtime. |
| `Files.readString(path, charset)` | Đọc file theo charset chỉ định | Phù hợp cho file văn bản có encoding đã biết. |
| `Files.writeString(path, text, charset)` | Ghi file theo charset chỉ định | Phù hợp cho file văn bản có encoding đã biết. |
| `InputStreamReader(input, charset)` | Chuyển byte stream thành Reader | Đặt charset ngay tại ranh giới stream. |
| `OutputStreamWriter(output, charset)` | Chuyển ký tự thành byte stream | Đặt charset ngay tại ranh giới output. |

Từ Java 18, `Charset.defaultCharset()` là UTF-8 theo JEP 400 trong cấu hình thông thường. Điều đó làm các API dựa vào default nhất quán hơn trên JDK hiện đại, nhưng **không thay thế hợp đồng charset của dữ liệu**. Mã dùng charset tường minh dễ đọc, dễ review và ít phụ thuộc vào môi trường chạy hơn.

Nếu xử lý dữ liệu không tin cậy hoặc cần phát hiện ký tự không hợp lệ, dùng `CharsetDecoder`/`CharsetEncoder` với `CodingErrorAction.REPORT`. Với dữ liệu đã có charset được xác định rõ nhưng chứa byte hợp lệ theo nhiều charset, vẫn cần metadata hoặc byte mẫu chuẩn để phát hiện việc diễn giải sai.

## 7. Quy trình kiểm chứng trong ứng dụng thật

Khi phát hiện chuỗi mojibake, không sửa trực tiếp chuỗi trước khi xác định bước sai. Hãy lấy bằng chứng theo thứ tự:

1. **Xác định hợp đồng nguồn:** dữ liệu ban đầu đến từ file, HTTP, database, classpath hay tiến trình con? Charset được quy định ở đâu?
2. **Chụp byte trước khi decode:** ghi hex hoặc lưu bản sao byte ở ranh giới nhận.
3. **Kiểm tra String ngay sau decode:** dùng `codePoints()` để xem nội dung thực tế trong bộ nhớ.
4. **Chụp byte ở ranh giới ghi:** xác minh charset encoder và byte đầu ra có đúng với hợp đồng đích.
5. **Đối chiếu với golden bytes hoặc nội dung chuẩn:** không chỉ so hai phía cùng dùng một giả định charset.
6. **Tìm bước chuyển đổi lặp:** xem có nơi nào biến byte thành String bằng charset sai rồi lại encode thành UTF-8 hay không.

Sơ đồ xác định điểm lỗi:

```text
Byte nguồn có đúng theo hợp đồng?
   |-- Không --> Sai ở bên phát hoặc tầng tạo dữ liệu.
   |
   +-- Có
        |
        v
String ngay sau decode có đúng code point?
   |-- Không --> Đọc sai charset / sai bước decode.
   |
   +-- Có
        |
        v
Byte sau encode có đúng hợp đồng đích?
   |-- Không --> Ghi sai charset / sai bước encode.
   |
   +-- Có
        |
        v
Consumer có decode cùng charset?
   |-- Không --> Sai ở bên nhận.
   |
   +-- Có --> Kiểm tra biến đổi nghiệp vụ hoặc cách hiển thị.
```

Một hệ thống có thể có nhiều ranh giới liên tiếp. Hãy kiểm tra byte và String tại từng ranh giới thay vì chỉ kiểm tra đầu vào và đầu ra cuối cùng; nếu không, lỗi ở hai bước khác nhau có thể che lấp nhau.

## 8. Bài thực hành và tiêu chí hoàn thành

1. **Tái hiện lỗi đọc:** tạo byte UTF-8 của `café`, giải mã bằng ISO-8859-1, in code point của String nhận được. Xác nhận byte gốc vẫn là `63 61 66 C3 A9`.
2. **Tái hiện lỗi ghi:** mã hóa String `café` bằng ISO-8859-1 rồi thử giải mã byte bằng UTF-8 strict. Xác nhận byte `E9` bị từ chối theo UTF-8.
3. **Tái hiện mã hóa lặp:** mã hóa String mojibake bằng UTF-8. Xác nhận byte mới `63 61 66 C3 83 C2 A9` là UTF-8 hợp lệ nhưng code point không còn giống chuỗi gốc.
4. **Thử phục hồi có kiểm soát:** đảo ngược chính xác bước ISO-8859-1 đã dùng nhầm rồi giải mã byte theo UTF-8. So sánh kết quả với String gốc.
5. **Thử trường hợp không thể kết luận:** chỉ dùng chuỗi ASCII. Giải thích vì sao byte ASCII không đủ để nhận biết một hệ thống đang đọc/ghi theo charset nào.
6. **Kiểm tra một ranh giới thực tế:** chọn một file hoặc HTTP payload, ghi lại byte nguồn, String sau decode và byte đầu ra; chỉ ra chính xác bước nào có nguy cơ dùng charset không đúng.

**Tiêu chí hoàn thành:** phân biệt được lỗi đọc, lỗi ghi và mã hóa lặp; xác định byte nào còn nguyên và String nào đã sai; giải thích vì sao UTF-8 strict không phát hiện mọi trường hợp đọc nhầm charset; và chỉ phục hồi mojibake khi phép chuyển đổi ngược đã được chứng minh là không mất dữ liệu. Đây là kỹ năng cần thiết để áp dụng UTF-8 mặc định từ Java 18 mà vẫn giữ đúng hợp đồng dữ liệu trên các JDK hiện đại.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi thay đổi default charset từ Java 18.
- [Java SE Charset](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html): charset, encoder và decoder.
- [Java SE CharsetDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [CharsetEncoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): chính sách REPORT khi byte hoặc ký tự không hợp lệ.
- [Java SE StandardCharsets](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn có sẵn trong Java.
