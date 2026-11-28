# Xác nhận khác biệt giữa API thay thế ký tự lỗi và API báo ngoại lệ

## 1. Mục tiêu: biết API đang sửa, bỏ hay từ chối dữ liệu

Trong module **JAVA_VERSION_JAVA18**, Java 18 chuẩn hóa UTF-8 thành charset mặc định cho nhiều API Java theo [JEP 400](https://openjdk.org/jeps/400). Thay đổi này giúp mã nguồn và dữ liệu văn bản có hành vi nhất quán hơn trên JDK hiện đại. Tuy nhiên, UTF-8 mặc định không làm cho mọi byte đều hợp lệ, và cũng không bảo đảm mọi ký tự Java đều biểu diễn được trong mọi charset đích.

Bài thuộc chương **Kiểm chứng mã hóa**. Trọng tâm là phân biệt hai nhóm API:

- **API tiện dụng của String** như `new String(bytes, charset)` và `text.getBytes(charset)` thay thế chuỗi byte hoặc ký tự không hợp lệ bằng giá trị thay thế mặc định của charset. Chúng không ném `CharacterCodingException` để báo rằng nội dung đã bị thay đổi.
- **API kiểm soát của NIO Charset** như `CharsetDecoder` và `CharsetEncoder` cho phép chọn chính sách `REPORT`, `REPLACE` hoặc `IGNORE`. Khi đặt `REPORT`, lỗi được trả về dưới dạng `CharacterCodingException` (hoặc lớp con) để ứng dụng quyết định cách xử lý.

Có ba dạng vấn đề cần tách biệt:

1. **Malformed input:** dữ liệu đầu vào không tạo thành chuỗi mã hợp lệ theo charset. Ví dụ byte UTF-8 `C3 28`, hoặc một Java `String` chứa high surrogate đứng riêng.
2. **Unmappable character:** dữ liệu nguồn hợp lệ nhưng charset đích không thể biểu diễn ký tự đó. Ví dụ mã hóa emoji `🚀` sang ISO-8859-1.
3. **Thay thế hoặc bỏ dữ liệu:** API có thể âm thầm thay bằng ký tự/byte thay thế (`REPLACE`) hoặc loại bỏ phần lỗi (`IGNORE`). Đây là hành vi có chủ đích của chính sách, không phải bằng chứng dữ liệu gốc được bảo toàn.

Sau bài này, bạn có thể xác định lúc nào API tự thay thế, lúc nào API báo ngoại lệ, kiểm tra giá trị thay thế và chọn chính sách phù hợp với hợp đồng dữ liệu.

## 2. Hai chiều chuyển đổi và hai loại lỗi

### 2.1. Giải mã: byte thành String

Ở chiều giải mã, nguồn là `byte[]`, đích là `String`:

```text
byte[]  ── CharsetDecoder ──>  String
  │                              │
  │ malformed byte sequence     │ code point sau giải mã
  │                              │
  └──── REPORT / REPLACE / IGNORE┘
```

Ví dụ `C3 A9` là UTF-8 hợp lệ của U+00E9 (`é`). Nhưng `C3 28` không hợp lệ: `C3` mở đầu chuỗi hai byte, trong khi `28` không phải continuation byte.

### 2.2. Mã hóa: String thành byte

Ở chiều mã hóa, nguồn là `String` (các đơn vị mã UTF-16), đích là `byte[]`:

```text
String  ── CharsetEncoder ──>  byte[]
  │                              │
  │ surrogate lẻ                 │ ký tự không có trong charset đích
  │                              │
  └──── REPORT / REPLACE / IGNORE┘
```

Có hai tình huống khác nhau:

- **Malformed UTF-16 input:** String chứa high surrogate hoặc low surrogate không ghép cặp. Ví dụ một high surrogate U+D800 đứng riêng.
- **Unmappable character:** String có code point hợp lệ, nhưng charset đích không có cách biểu diễn. Ví dụ `🚀` là U+1F680 hợp lệ nhưng không thể biểu diễn trong ISO-8859-1.

Không gộp hai loại lỗi này thành một: `CharsetEncoder` có hai cấu hình riêng là `onMalformedInput` và `onUnmappableCharacter`.

## 3. API String tự thay thế ký tự lỗi

### 3.1. `new String(bytes, charset)`

Constructor này giải mã byte theo charset đã chỉ định. Nếu gặp malformed hoặc unmappable input, nó thay phần dữ liệu lỗi bằng chuỗi thay thế mặc định của charset. Với UTF-8, ký tự thay thế mặc định là U+FFFD (REPLACEMENT CHARACTER, thường hiển thị là `�`).

```java
import java.nio.charset.StandardCharsets;

byte[] malformed = {(byte) 0xC3, 0x28};

// API tiện dụng: thay byte lỗi bằng U+FFFD, rồi tiếp tục với '('.
String replaced = new String(malformed, StandardCharsets.UTF_8);

// Code point kỳ vọng: U+FFFD U+0028
System.out.println(replaced.codePoints()
        .mapToObj(cp -> String.format("U+%04X", cp))
        .toList());
```

Kết quả là một String có thể sử dụng tiếp, nhưng không còn biểu diễn chính xác byte đầu vào. Nếu chỉ in chuỗi ra terminal, ký tự `�` có thể bị font hiển thị thành ô vuông hoặc bị che khuất; kiểm tra code point sẽ rõ hơn.

### 3.2. `String.getBytes(charset)`

Phương thức này mã hóa String theo charset đã chỉ định. Nếu một ký tự không thể mã hóa hoặc chuỗi có surrogate không hợp lệ, API thay phần lỗi bằng dãy byte thay thế mặc định của charset.

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

String rocket = "🚀";

// ISO-8859-1 không biểu diễn được U+1F680.
byte[] replacedBytes = rocket.getBytes(StandardCharsets.ISO_8859_1);

System.out.println(HexFormat.of().formatHex(replacedBytes));
System.out.println(HexFormat.of().formatHex(
        StandardCharsets.ISO_8859_1.newEncoder().replacement()));
```

Với encoder ISO-8859-1 tiêu chuẩn trên JDK hiện đại, byte thay thế mặc định thường là `3f` (ký tự `?`). Ví dụ in cả byte đầu ra lẫn replacement của encoder để kiểm chứng chính sách đang dùng, thay vì suy đoán từ hình ảnh terminal.

`String.getBytes(charset)` không cung cấp tham số để yêu cầu ném ngoại lệ. Khi cần từ chối dữ liệu không thể biểu diễn, dùng `CharsetEncoder` và đặt `REPORT`.

### 3.3. Thay thế khác với bảo toàn

Giả sử input UTF-8 là `C3 28`. Sau khi `new String(bytes, UTF_8)`, ứng dụng nhận U+FFFD và `(`. Nếu ghi String này ra UTF-8, ứng dụng sẽ tạo byte UTF-8 hợp lệ cho U+FFFD và `(`; byte lỗi ban đầu đã không còn.

Tương tự, nếu mã hóa emoji sang ISO-8859-1 bằng `getBytes`, ký tự có thể bị thay bằng `?`. Khi đọc lại byte `3F`, không có cách nào biết ký tự ban đầu là `🚀`, `漢` hay một code point khác. **Một lần thay thế có thể làm mất thông tin không thể khôi phục.**

## 4. `CharsetDecoder` và `CharsetEncoder`: chủ động chọn chính sách

Các đối tượng decoder/encoder cung cấp ba hành động cho lỗi:

| Chính sách | Hành vi | Khi phù hợp |
| --- | --- | --- |
| `CodingErrorAction.REPORT` | Báo lỗi; thao tác giải mã/mã hóa dừng với `CharacterCodingException` | Xác thực dữ liệu, import, giao thức, dữ liệu cần bảo toàn |
| `CodingErrorAction.REPLACE` | Thay phần lỗi bằng giá trị thay thế | Hệ thống hiển thị hoặc xử lý có chính sách thay thế được chấp thuận |
| `CodingErrorAction.IGNORE` | Bỏ phần lỗi và tiếp tục | Chỉ khi hợp đồng cho phép mất phần dữ liệu lỗi |

`CharsetDecoder` và `CharsetEncoder` mới tạo có hành động mặc định là `REPORT`. Dù vậy, nên cấu hình rõ chính sách trong mã quan trọng để người đọc biết lỗi sẽ được xử lý như thế nào.

### 4.1. Giải mã nghiêm ngặt với `REPORT`

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

`decode(ByteBuffer)` thực hiện giải mã toàn bộ buffer như input đã kết thúc. Nếu có malformed input và chính sách là `REPORT`, nó ném `MalformedInputException` (là lớp con của `CharacterCodingException`). Dữ liệu không bị thay bằng U+FFFD một cách âm thầm.

### 4.2. Mã hóa nghiêm ngặt với `REPORT`

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static byte[] encodeStrict(String text)
        throws CharacterCodingException {
    ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(text));

    byte[] bytes = new byte[encoded.remaining()];
    encoded.get(bytes);
    return bytes;
}
```

Với UTF-8, mọi Unicode scalar value đều biểu diễn được. Nhưng một `String` Java có thể chứa surrogate lẻ, không tạo thành một Unicode scalar value hợp lệ. Encoder nghiêm ngặt sẽ báo `MalformedInputException` thay vì thay ký tự đó.

Nếu dùng ISO-8859-1 để mã hóa `🚀`, encoder sẽ báo `UnmappableCharacterException`: code point nguồn hợp lệ nhưng charset đích không thể biểu diễn.

## 5. Chương trình kiểm chứng cả thay thế và ngoại lệ

Lớp sau tái hiện ba trường hợp: byte UTF-8 malformed, ký tự không biểu diễn được trong ISO-8859-1 và surrogate lẻ trong String. Chương trình không cần thư viện ngoài và dùng API có sẵn từ lâu trước Java 18, vẫn áp dụng trên JDK hiện đại.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;
import java.util.HexFormat;
import java.util.Locale;

public final class CodingErrorPolicyLab {
    public static void main(String[] args) throws Exception {
        byte[] malformedUtf8 = {(byte) 0xC3, 0x28};

        // String API thay byte lỗi bằng replacement character.
        String viaString = new String(
                malformedUtf8, StandardCharsets.UTF_8);
        show("STRING_DECODE_CODE_POINTS", codePoints(viaString));

        // Decoder REPORT từ chối cùng byte.
        try {
            decodeStrict(malformedUtf8, StandardCharsets.UTF_8);
            throw new AssertionError("Decoder strict đã chấp nhận byte lỗi");
        } catch (MalformedInputException expected) {
            show("DECODER_REPORT", "MALFORMED_INPUT");
        }

        // Decoder REPLACE và IGNORE thể hiện hai chính sách khác nhau.
        String withReplace = decodeWithAction(
                malformedUtf8, CodingErrorAction.REPLACE);
        String withIgnore = decodeWithAction(
                malformedUtf8, CodingErrorAction.IGNORE);
        show("DECODER_REPLACE", codePoints(withReplace));
        show("DECODER_IGNORE", codePoints(withIgnore));

        // Ký tự hợp lệ nhưng không biểu diễn được trong ISO-8859-1.
        String rocket = "🚀";
        byte[] viaGetBytes = rocket.getBytes(StandardCharsets.ISO_8859_1);
        show("GET_BYTES_REPLACEMENT", hex(viaGetBytes));
        show("ISO_ENCODER_REPLACEMENT",
                hex(StandardCharsets.ISO_8859_1.newEncoder().replacement()));

        try {
            encodeStrict(rocket, StandardCharsets.ISO_8859_1);
            throw new AssertionError("Encoder strict đã mã hóa được rocket");
        } catch (UnmappableCharacterException expected) {
            show("ENCODER_REPORT", "UNMAPPABLE_CHARACTER");
        }

        // String chứa high surrogate không có low surrogate đi kèm.
        String loneSurrogate = String.valueOf((char) 0xD800);
        byte[] surrogateReplacement =
                loneSurrogate.getBytes(StandardCharsets.UTF_8);
        show("SURROGATE_GET_BYTES_REPLACEMENT",
                hex(surrogateReplacement));

        try {
            encodeStrict(loneSurrogate, StandardCharsets.UTF_8);
            throw new AssertionError("Encoder strict đã chấp nhận surrogate lẻ");
        } catch (MalformedInputException expected) {
            show("SURROGATE_ENCODER_REPORT", "MALFORMED_INPUT");
        }
    }

    private static String decodeStrict(byte[] bytes, Charset charset)
            throws CharacterCodingException {
        return charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static String decodeWithAction(byte[] bytes,
            CodingErrorAction action) throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static byte[] encodeStrict(String text, Charset charset)
            throws CharacterCodingException {
        ByteBuffer encoded = charset.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(text));

        byte[] bytes = new byte[encoded.remaining()];
        encoded.get(bytes);
        return bytes;
    }

    private static String codePoints(String text) {
        StringBuilder result = new StringBuilder();
        text.codePoints().forEach(cp -> {
            if (result.length() > 0) result.append(' ');
            result.append(String.format(Locale.ROOT, "U+%04X", cp));
        });
        return result.toString();
    }

    private static String hex(byte[] bytes) {
        return HexFormat.of().withUpperCase().formatHex(bytes);
    }

    private static void show(String key, String value) {
        System.out.println(key + "=" + value);
    }
}
```

Biên dịch và chạy trên JDK 18 hoặc mới hơn:

```bash
javac -encoding UTF-8 CodingErrorPolicyLab.java
java CodingErrorPolicyLab
```

Kết quả cần đối chiếu:

| Nhãn | Ý nghĩa |
| --- | --- |
| `STRING_DECODE_CODE_POINTS` | Chứa U+FFFD và U+0028: constructor String đã thay byte lỗi. |
| `DECODER_REPORT` | Decoder strict ném `MalformedInputException`. |
| `DECODER_REPLACE` | Decoder thay phần lỗi bằng replacement string. |
| `DECODER_IGNORE` | Decoder bỏ phần byte lỗi, có thể làm mất nội dung. |
| `GET_BYTES_REPLACEMENT` | Byte thay thế khi `🚀` không biểu diễn được trong ISO-8859-1. |
| `ENCODER_REPORT` | Encoder strict ném `UnmappableCharacterException`. |
| `SURROGATE_ENCODER_REPORT` | Encoder strict từ chối surrogate lẻ bằng `MalformedInputException`. |

Chương trình in byte replacement thực tế của charset thay vì giả định mọi charset đều dùng cùng một dãy byte thay thế.

## 6. Hiểu đúng hai ngoại lệ của encoder và decoder

### 6.1. `MalformedInputException`

Ngoại lệ này xuất hiện khi đầu vào không hợp lệ theo cách biểu diễn mà decoder/encoder mong đợi:

- Decoder UTF-8 nhận `C3 28`: byte mở đầu hai byte bị theo sau bởi byte không phải continuation.
- Encoder UTF-8 nhận một `String` chứa high surrogate U+D800 đứng riêng: chuỗi UTF-16 không có cặp surrogate hợp lệ.

Cả hai đều là malformed input, nhưng một trường hợp lỗi ở byte và trường hợp kia lỗi ở đơn vị mã UTF-16.

### 6.2. `UnmappableCharacterException`

Ngoại lệ này xuất hiện khi encoder nhận một ký tự nguồn hợp lệ nhưng charset đích không thể biểu diễn. Ví dụ `🚀` là Unicode scalar value hợp lệ, nhưng ISO-8859-1 không có byte tương ứng.

Đừng dùng `MalformedInputException` để mô tả mọi trường hợp không mã hóa được. Hai ngoại lệ giúp phân biệt dữ liệu nguồn hỏng với giới hạn của charset đích.

### 6.3. Vì sao decoder UTF-8 thường báo malformed, không phải unmappable?

UTF-8 có thể biểu diễn tất cả Unicode scalar values. Với decoder UTF-8, các chuỗi byte sai cấu trúc thường là `malformed input`. Với encoder UTF-8, một ký tự hợp lệ không bị unmappable; vấn đề có thể là malformed UTF-16 như surrogate lẻ.

`UnmappableCharacterException` dễ quan sát hơn khi chọn charset đích có tập ký tự hạn chế, chẳng hạn ISO-8859-1.

## 7. Khi nào nên dùng REPLACE, REPORT hoặc IGNORE?

| Bối cảnh | Chính sách phù hợp | Lý do |
| --- | --- | --- |
| Nhận dữ liệu từ API hoặc file cần bảo toàn | `REPORT` | Từ chối dữ liệu lỗi để không âm thầm biến đổi nội dung. |
| Nhập dữ liệu người dùng, cần hiển thị nội dung còn đọc được | `REPLACE` có ghi nhận | Có thể hiển thị phần hợp lệ, nhưng phải thông báo hoặc lưu dấu việc thay thế. |
| Log/telemetry có chính sách loại bỏ byte lỗi | `IGNORE` chỉ khi được chấp thuận | Bỏ dữ liệu là mất mát; không dùng làm mặc định chung. |
| Chuyển đổi sang charset đích hạn chế | `REPORT` hoặc quy tắc fallback được đặc tả | Tránh ký tự bị đổi thành `?` mà không ai biết. |
| Kiểm tra file/giao thức có hợp đồng UTF-8 | `REPORT` | Xác nhận byte thật sự tuân theo UTF-8. |

`REPLACE` hữu ích khi sản phẩm có chính sách hiển thị dữ liệu lỗi, nhưng hãy lưu lại số lần thay thế hoặc vị trí lỗi nếu cần audit. `IGNORE` thường nguy hiểm hơn vì nội dung biến mất mà kết quả cuối có thể trông vẫn hợp lệ.

Không nên chọn `REPORT` cho mọi luồng hiển thị một cách máy móc nếu sản phẩm đã định nghĩa rõ chính sách thay thế. Điều quan trọng là hành vi phải có chủ đích và được kiểm thử, không phụ thuộc vào overload tiện dụng mà người viết không để ý.

## 8. Kiểm chứng byte và chuỗi sau khi xử lý lỗi

Khi API thay thế, so sánh String cuối cùng với nguồn có thể không đủ để biết phần nào đã bị thay. Hãy giữ byte gốc và kiểm tra code point của kết quả.

Ví dụ với byte malformed:

```java
byte[] source = {(byte) 0xC3, 0x28};
String result = new String(source, StandardCharsets.UTF_8);

System.out.println(HexFormat.of().formatHex(source)); // c328
System.out.println(result.codePoints()
        .mapToObj(cp -> String.format("U+%04X", cp))
        .toList()); // [U+FFFD, U+0028]
```

Byte nguồn vẫn là `C3 28`; String sau giải mã chứa U+FFFD và dấu ngoặc mở. Đây là bằng chứng rằng API đã thay dữ liệu. Nếu chỉ lưu String sau xử lý, bạn không còn biết byte nào đã bị lỗi.

Với encoder, giữ String nguồn và đối chiếu byte được tạo với charset đích. Khi dùng `REPORT`, chỉ tiếp tục nếu encode thành công. Khi dùng `REPLACE`, hãy ghi nhận replacement byte và vị trí/ký tự không biểu diễn được nếu nghiệp vụ cần truy vết.

Một phép round-trip chỉ chứng minh dữ liệu sau xử lý có thể đi qua cùng quy trình mà không đổi thêm. Nó không chứng minh byte ban đầu chưa từng bị thay thế.

## 9. Bài thực hành và tiêu chí hoàn thành

1. **Decoder thay thế:** giải mã byte `C3 28` bằng `new String(bytes, UTF_8)`. Xem code point và xác định U+FFFD xuất hiện ở đâu.
2. **Decoder báo ngoại lệ:** dùng `CharsetDecoder` với `REPORT` cho cùng byte. Xác nhận `MalformedInputException`.
3. **Encoder thay thế:** mã hóa `🚀` sang ISO-8859-1 bằng `getBytes`. Đối chiếu byte kết quả với `ISO_8859_1.newEncoder().replacement()`.
4. **Encoder báo ngoại lệ:** dùng encoder `REPORT` với cùng chuỗi. Xác nhận `UnmappableCharacterException`.
5. **Surrogate lẻ:** tạo `String.valueOf((char) 0xD800)`. So sánh `getBytes(UTF_8)` với encoder strict; xác định đây là malformed UTF-16 input.
6. **IGNORE:** giải mã byte lỗi với `CodingErrorAction.IGNORE`, rồi chỉ ra ký tự nào đã biến mất so với byte nguồn.
7. **Hợp đồng dữ liệu:** chọn một file UTF-8 hoặc HTTP payload. Quyết định chính sách `REPORT`, `REPLACE` hay `IGNORE` và giải thích tác động của nó lên nội dung, log và khả năng khôi phục.

**Tiêu chí hoàn thành:** phân biệt được API String thay thế dữ liệu với decoder/encoder báo ngoại lệ; phân loại đúng `MalformedInputException` và `UnmappableCharacterException`; kiểm tra được replacement string/byte; và lựa chọn `REPORT`, `REPLACE`, `IGNORE` theo hợp đồng của ứng dụng. Đây là kỹ năng vẫn áp dụng trên JDK hiện đại, kể cả khi UTF-8 đã trở thành charset mặc định từ Java 18.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ Java 18.
- [Java SE String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): hành vi thay thế của constructor giải mã và `getBytes(Charset)`.
- [Java SE CharsetDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): chính sách malformed/unmappable input và replacement string.
- [Java SE CharsetEncoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): chính sách malformed/unmappable input và replacement bytes.
- [Java SE CodingErrorAction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CodingErrorAction.html): `REPORT`, `REPLACE` và `IGNORE`.
