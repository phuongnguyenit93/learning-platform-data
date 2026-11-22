# CharsetDecoder, CharsetEncoder và CodingErrorAction trong Java

## 1. Vì sao biết UTF-8 vẫn chưa đủ?

Khi một ứng dụng Java đọc file, nhận HTTP payload hoặc lấy dữ liệu từ hệ thống cũ, chuỗi ký tự phải đi qua một **ranh giới mã hóa**:

- **Đọc:** các byte từ file/mạng → ký tự Unicode trong Java.
- **Ghi:** các ký tự Unicode từ Java → các byte của một charset để gửi/lưu.

Nếu dữ liệu hợp lệ, việc chuyển đổi có vẻ đơn giản. Nhưng dữ liệu thực tế có thể chứa **byte bị cắt dở**, **chuỗi UTF-8 không hợp lệ**, **ký tự Unicode không biểu diễn được trong charset đích**, hoặc **surrogate pair UTF-16 bị tách**. Khi gặp những tình huống đó, ứng dụng phải quyết định **báo lỗi, thay ký tự hay bỏ dữ liệu**.

Java 17 cung cấp bộ API có cấu hình rõ ràng:

- `CharsetDecoder`: chuyển **byte → char** theo một `Charset`.
- `CharsetEncoder`: chuyển **char → byte** theo một `Charset`.
- `CodingErrorAction`: chọn chính sách khi gặp lỗi, với ba lựa chọn `REPORT`, `REPLACE`, `IGNORE`.
- `CoderResult`: mô tả trạng thái khi chuyển đổi bằng API tăng dần, gồm `UNDERFLOW`, `OVERFLOW`, `MALFORMED` và `UNMAPPABLE`.

Bài học này tập trung vào Java 17+, các trường hợp I/O thực tế và **độ toàn vẹn dữ liệu quốc tế hóa**. Mục tiêu không phải chỉ “làm hết lỗi dấu tiếng Việt”, mà là **không âm thầm phá hỏng văn bản** khi charset đầu vào hoặc đầu ra không phù hợp.

## 2. Sơ đồ luồng dữ liệu và vai trò từng API

```text
File / Network / Legacy System                Java Application
        BYTES                                        Unicode
  54 69 E1 BA BF 6E 67      decode UTF-8     "Tiếng"
             -------------------------------> String/CharBuffer
             <-------------------------------
                 encode UTF-8                UTF-8 bytes

ByteBuffer          CharsetDecoder          CharBuffer / String
CharBuffer / String CharsetEncoder          ByteBuffer
```

Các thuật ngữ:

| Khái niệm | Kiểu/API | Ý nghĩa |
| --- | --- | --- |
| Charset | `java.nio.charset.Charset` | Quy tắc ánh xạ byte với văn bản Unicode |
| Decoder | `CharsetDecoder` | Bộ giải mã một charset cụ thể, có trạng thái |
| Encoder | `CharsetEncoder` | Bộ mã hóa một charset cụ thể, có trạng thái |
| Byte buffer | `ByteBuffer` | Bộ nhớ chứa byte nguồn/đích, có `position/limit` |
| Character buffer | `CharBuffer` | Bộ nhớ chứa các UTF-16 code unit `char` |
| Error action | `CodingErrorAction` | Hành động khi dữ liệu malformed/unmappable |
| Conversion result | `CoderResult` | UNDERFLOW, OVERFLOW hoặc loại lỗi |
| Standard charsets | `StandardCharsets.UTF_8`, `US_ASCII`, `ISO_8859_1` | Các charset có sẵn và được hỗ trợ chuẩn |
| Unicode replacement | `U+FFFD` | Ký tự thường dùng để thay dữ liệu không giải mã được |

`CharsetDecoder` và `CharsetEncoder` có thể được tạo từ một `Charset`:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder();
CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder();
```

Hai dòng trên là code minh họa **bên trong method**, cần import từ `java.nio.charset`. Mỗi instance giữ trạng thái của một quá trình chuyển đổi; **không chia sẻ một encoder/decoder với nhiều request đồng thời**.

### Điểm rất quan trọng

`CharsetDecoder` không phải “bộ phát hiện ngôn ngữ” và `CharsetEncoder` không phải “bộ dịch ngôn ngữ”. UTF-8 là cách **mã hóa ký tự**, không phải tiếng Việt/tiếng Anh/tiếng Nhật. Locale và charset là hai khía cạnh khác nhau của localization.

`Charset.forName("UTF-8")` hoặc `StandardCharsets.UTF_8` mô tả cùng charset chuẩn. Khi biết trước UTF-8, `StandardCharsets.UTF_8` tránh lỗi chính tả tên charset và cho code rõ ràng hơn.

## 3. Hai loại lỗi: malformed và unmappable

Java phân biệt hai lỗi chính trong quá trình chuyển đổi.

### 3.1. Malformed input

Dữ liệu đầu vào **không hợp lệ về cấu trúc** theo encoding được khai báo.

Ví dụ khi decode UTF-8:

- Byte `0xC3` yêu cầu byte tiếp theo thích hợp để tạo một chuỗi UTF-8 hai byte.
- Nếu nó đứng trước `0x28` (ký tự `(` trong ASCII), chuỗi `C3 28` không phải một chuỗi mã hóa UTF-8 hợp lệ.
- Nếu stream kết thúc ngay sau `0xC3`, input bị thiếu byte kết thúc, cũng có thể thành malformed khi đã xác nhận hết input.

Ví dụ khi encode từ Java `String`: một **high surrogate** UTF-16 đứng một mình như `"\uD83D"` không đại diện cho một Unicode scalar value hoàn chỉnh. Nó là **malformed UTF-16 input** cho bộ mã hóa.

### 3.2. Unmappable character

Input có thể **hợp lệ về cấu trúc**, nhưng **charset đích không có byte sequence biểu diễn ký tự đó**.

Ví dụ:

- Chuỗi Java `"A€B"` hợp lệ về Unicode.
- Charset `ISO-8859-1` không biểu diễn ký tự `€` (U+20AC).
- Khi encode sang ISO-8859-1, `€` là **unmappable**.
- Nếu encode cùng chuỗi sang UTF-8 thì `€` được biểu diễn bình thường.

Một số charset cũng có thể báo **unmappable** khi decode một chuỗi byte hợp lệ về cấu trúc nhưng không ánh xạ sang ký tự Unicode. Không giả định **mọi** lỗi decoder đều malformed hoặc **mọi** lỗi encoder đều unmappable.

| Tình huống | Hướng | Loại điển hình |
| --- | --- | --- |
| Byte `C3 28` khi đọc UTF-8 | Decode | Malformed |
| Byte `C3` ở cuối UTF-8 stream | Decode | Malformed khi end-of-input được xác nhận |
| `"A€B"` chuyển sang ISO-8859-1 | Encode | Unmappable |
| Chuỗi chứa high surrogate đơn lẻ chuyển sang UTF-8 | Encode | Malformed |
| `"Tiếng Việt"` chuyển sang UTF-8 | Encode | Hợp lệ |
| `"A€B"` chuyển sang UTF-8 | Encode | Hợp lệ |

**Không giải quyết sai charset bằng cách bỏ lỗi.** Ví dụ nếu file thực ra dùng Windows-1258 nhưng bị đọc như UTF-8, `REPLACE` có thể tạo dấu `�` và làm mất thông tin. Việc đúng phải là xác định/nhận biết charset nguồn từ metadata đáng tin và decode lại đúng.

## 4. CodingErrorAction: REPORT, REPLACE, IGNORE

`java.nio.charset.CodingErrorAction` có ba hằng số:

| Action | Khi gặp dữ liệu sai | Đánh đổi |
| --- | --- | --- |
| `REPORT` | Báo lỗi cho caller qua `CoderResult` hoặc ném `CharacterCodingException` | Bảo toàn nguyên tắc không âm thầm làm mất dữ liệu |
| `REPLACE` | Loại đoạn input sai, ghi giá trị thay thế vào output rồi tiếp tục | Pipeline vẫn chạy, **nhưng mất dữ liệu gốc** |
| `IGNORE` | Loại đoạn input sai, **không ghi ký tự/byte thay thế** | Mất dữ liệu, khó biết chỗ nào bị xóa |

Cấu hình **riêng** cho hai loại lỗi:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.ISO_8859_1.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);
```

Tất cả đều là **đoạn mã trong method** với import phù hợp.

**Theo API Java SE 17, encoder/decoder mới tạo mặc định dùng `REPORT` cho cả malformed và unmappable.** Việc viết hai cấu hình `REPORT` tường minh vẫn hữu ích để biểu đạt policy trong code và tránh nhầm với các API tiện dụng có thể áp dụng replacement.

### 4.1. Sự khác biệt mặc định rất dễ gây nhầm

Hai cách decode sau có thể có hành vi khi lỗi khác nhau:

```java
// API tiện dụng tạo String có thể dùng ký tự thay thế:
String convenient = new String(bytes, StandardCharsets.UTF_8);

// Decoder mới, mặc định REPORT:
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder();
CharBuffer decoded = strict.decode(ByteBuffer.wrap(bytes));
```

Với input UTF-8 malformed, constructor `new String(byte[], Charset)` thay malformed/unmappable byte sequences bằng replacement string mặc định của charset, còn `CharsetDecoder.decode(ByteBuffer)` với `REPORT` ném `CharacterCodingException` phù hợp. **Đừng giả định mọi API Java mặc định hành xử giống nhau chỉ vì cùng UTF-8.**

Tương tự, `String.getBytes(Charset)` có thể dùng replacement bytes cho ký tự không biểu diễn được. Nếu cần phát hiện lỗi mất dữ liệu, dùng `CharsetEncoder` cấu hình `REPORT`.

## 5. CharsetDecoder: đọc byte không hợp lệ một cách có kiểm soát

Dưới đây là ví dụ Java 17 độc lập cho cùng một dãy byte:

```text
41 C3 28 42

41 = 'A'
C3 = byte đầu của một UTF-8 sequence hai byte, bị lỗi khi gặp 28
28 = '('
42 = 'B'
```

### Chương trình 1 — ba chính sách khi decode

Lưu tệp `DecoderActionsDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.stream.Collectors;

public class DecoderActionsDemo {

    private static final byte[] BYTES = {
            0x41, (byte) 0xC3, 0x28, 0x42
    };

    static String codePoints(String text) {
        return text.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    static String decode(CodingErrorAction action)
            throws CharacterCodingException {

        CharBuffer chars = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action)
                .decode(ByteBuffer.wrap(BYTES));

        return chars.toString();
    }

    public static void main(String[] args) throws Exception {
        try {
            decode(CodingErrorAction.REPORT);
            System.out.println("REPORT=unexpected");
        } catch (CharacterCodingException ex) {
            System.out.println("REPORT=error");
        }

        String replaced = decode(CodingErrorAction.REPLACE);
        String ignored = decode(CodingErrorAction.IGNORE);

        System.out.println("REPLACE=" + codePoints(replaced));
        System.out.println("IGNORE=" + codePoints(ignored));
        System.out.println("convenience=" + codePoints(
                new String(BYTES, StandardCharsets.UTF_8)));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 DecoderActionsDemo.java
java DecoderActionsDemo
```

Stdout xác định:

```text
REPORT=error
REPLACE=U+0041 U+FFFD U+0028 U+0042
IGNORE=U+0041 U+0028 U+0042
convenience=U+0041 U+FFFD U+0028 U+0042
```

Giải thích:

- `REPORT` dừng và ném lỗi với API `decode(ByteBuffer)`.
- `REPLACE` chèn một ký tự `U+FFFD` cho phần input malformed được phát hiện, tiếp tục đọc dấu `(` và chữ `B`.
- `IGNORE` bỏ byte lỗi, nên output chỉ còn `A(B`.
- Constructor `new String(BYTES, UTF_8)` cũng dùng replacement cho dữ liệu hỏng.

**Một cảnh báo:** output `A�(B` không xác nhận rằng văn bản gốc đã được khôi phục. Byte bị hỏng đã không còn thông tin. Trong các lĩnh vực yêu cầu độ chính xác dữ liệu, chọn `REPORT` rồi xử lý file/network protocol đúng cách.

### 5.1. Tùy chỉnh decoder replacement

Mặc định decoder replacement string là `"\uFFFD"`, nhưng có thể thay:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("[invalid]");
```

Đây là code minh họa trong method. `replaceWith(String)` yêu cầu chuỗi thay thế **không null, không rỗng và có độ dài không vượt `maxCharsPerByte()`** của decoder. Với UTF-8, `maxCharsPerByte()` thường là 1; vì vậy **chuỗi thay thế dài `"[invalid]"` không được phép** và sẽ ném `IllegalArgumentException`. Để tránh sai, dùng replacement một ký tự như `"?"` hoặc `"\uFFFD"` cho decoder UTF-8.

**Ví dụ cấu hình hợp lệ cho UTF-8**:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("?");
```

Khi dùng replacement dễ nhìn như dấu `?`, vẫn phải ghi nhận rằng dữ liệu gốc đã bị thay. Không dùng dấu hỏi replacement trong hợp đồng dữ liệu mà có thể gây nhập nhằng với dấu hỏi thật của người dùng.

## 6. CharsetEncoder: ký tự hợp lệ nhưng charset đích không hỗ trợ

Với Unicode `"A€B"`, UTF-8 có thể biểu diễn được toàn bộ. Nhưng `ISO-8859-1` không chứa ký hiệu euro. Khi encode sang ISO-8859-1:

- `REPORT`: ném `UnmappableCharacterException` qua one-shot API.
- `REPLACE`: ghi replacement byte (thường là `?`); có thể cấu hình `!` để biết chắc output.
- `IGNORE`: bỏ ký tự `€`, chỉ xuất `AB`.

### Chương trình 2 — mã hóa ISO-8859-1 và lỗi unmappable

Tệp `EncoderActionsDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class EncoderActionsDemo {

    static String hex(ByteBuffer bytes) {
        StringBuilder result = new StringBuilder();
        while (bytes.hasRemaining()) {
            if (result.length() > 0) {
                result.append(' ');
            }
            result.append(String.format(
                    Locale.ROOT, "%02X",
                    Byte.toUnsignedInt(bytes.get())));
        }
        return result.toString();
    }

    static ByteBuffer encode(
            String text, CodingErrorAction action)
            throws CharacterCodingException {

        CharsetEncoder encoder = StandardCharsets.ISO_8859_1
                .newEncoder()
                .onMalformedInput(action)
                .onUnmappableCharacter(action)
                .replaceWith(new byte[]{0x21}); // 0x21 = '!'

        return encoder.encode(CharBuffer.wrap(text));
    }

    public static void main(String[] args) throws Exception {
        String text = "A\u20ACB"; // A€B

        try {
            encode(text, CodingErrorAction.REPORT);
            System.out.println("REPORT=unexpected");
        } catch (CharacterCodingException ex) {
            System.out.println("REPORT=error");
        }

        System.out.println("REPLACE=" +
                hex(encode(text, CodingErrorAction.REPLACE)));
        System.out.println("IGNORE=" +
                hex(encode(text, CodingErrorAction.IGNORE)));

        System.out.println("UTF8=" + hex(
                StandardCharsets.UTF_8.newEncoder()
                        .encode(CharBuffer.wrap(text))));
    }
}
```

```bash
javac -encoding UTF-8 EncoderActionsDemo.java
java EncoderActionsDemo
```

Stdout xác định:

```text
REPORT=error
REPLACE=41 21 42
IGNORE=41 42
UTF8=41 E2 82 AC 42
```

`41 21 42` là `A!B`; dấu `!` chỉ là replacement được lập trình viên cấu hình, **không phải ký tự euro**. `41 E2 82 AC 42` là biểu diễn UTF-8 hợp lệ của `A€B`.

**Ghi nhớ:** một input hợp lệ nhưng charset output không biểu diễn được vẫn là lỗi **UNMAPPABLE**, không phải lỗi malformed. Nếu yêu cầu bảo toàn nhiều hệ chữ quốc tế, dùng UTF-8 khi giao thức cho phép, thay vì ép text đa ngôn ngữ xuống bảng mã chỉ hỗ trợ một phần Unicode.

### 6.1. Encoder replacement không giống decoder replacement

| Coder | API replacement | Đơn vị replacement |
| --- | --- | --- |
| Decoder | `CharsetDecoder.replaceWith(String)` | **Chuỗi `char`** (ký tự Unicode) |
| Encoder | `CharsetEncoder.replaceWith(byte[])` | **Mảng byte** hợp lệ trong charset đích |

Encoder không nhận `replaceWith("€")`; nó cần **byte[]**. Byte replacement phải là một chuỗi byte **hợp lệ** với charset, không null/rỗng và không vượt giới hạn `maxBytesPerChar()`. Không tự chọn một byte bất kỳ khi charset có cấu trúc nhiều byte hoặc stateful; hãy dùng replacement mặc định hoặc kiểm tra khả năng biểu diễn.

### 6.2. canEncode có thay được encode thật không?

`CharsetEncoder.canEncode(char)` hoặc `canEncode(CharSequence)` giúp kiểm tra liệu coder có thể biểu diễn một chuỗi. Nhưng đó không phải cơ chế xử lý lỗi thay cho encoding thật:

- Coder có trạng thái, một số mã hóa có giới hạn/chế độ đặc biệt.
- `canEncode` không thay thế việc kiểm tra nội dung đầu vào đã được xác thực.
- Chính sách chuyển đổi vẫn cần xử lý `CharacterCodingException` khi `REPORT`.
- Với Unicode ngoài BMP, nên kiểm tra cả chuỗi/cặp surrogate thay vì thử một `char` cao hoặc thấp đơn lẻ.

Không dùng `canEncode` cho từng `charAt(i)` rồi cho rằng một emoji hai code unit là hai ký tự không hợp lệ; hãy xử lý toàn bộ Unicode string hoặc code point đúng cách.

## 7. Malformed UTF-16 trong String và tác động đến encoder

Java `char` là một **UTF-16 code unit**. Một ký tự ngoài BMP như `😀` (U+1F600) là cặp `\uD83D\uDE00`:

```text
High surrogate = U+D83D
Low surrogate  = U+DE00
Full code point = U+1F600

Cặp đúng   : D83D DE00 → biểu diễn hợp lệ
High lẻ    : D83D      → malformed UTF-16
Low lẻ     : DE00      → malformed UTF-16
```

Java `String` có thể chứa một `char` surrogate lẻ; nó không nhất thiết ném lỗi khi chuỗi được tạo. Việc **encode** mới là một trong các ranh giới phát hiện input không hợp lệ.

### Chương trình 3 — Encoder phân biệt malformed

Tệp `MalformedUtf16EncoderDemo.java`:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class MalformedUtf16EncoderDemo {
    public static void main(String[] args) throws Exception {
        String validEmoji = "\uD83D\uDE00";
        String loneHigh = "\uD83D";

        byte[] utf8Valid = validEmoji.getBytes(
                StandardCharsets.UTF_8);

        System.out.println("validUtf8Bytes=" +
                utf8Valid.length);

        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(loneHigh));
            System.out.println("REPORT=unexpected");
        } catch (CharacterCodingException ex) {
            System.out.println("REPORT=error");
        }

        int remaining = StandardCharsets.UTF_8
                .newEncoder()
                .onMalformedInput(CodingErrorAction.IGNORE)
                .encode(CharBuffer.wrap(loneHigh))
                .remaining();

        System.out.println("IGNOREbytes=" + remaining);
        System.out.println("inputUnits=" + loneHigh.length());
    }
}
```

```bash
javac -encoding UTF-8 MalformedUtf16EncoderDemo.java
java MalformedUtf16EncoderDemo
```

Stdout xác định:

```text
validUtf8Bytes=4
REPORT=error
IGNOREbytes=0
inputUnits=1
```

Dù `loneHigh` có độ dài 1, nó không phải Unicode scalar value hoàn chỉnh. Việc `IGNORE` tạo 0 byte không giúp “chữa” chuỗi: dữ liệu đã bị **bỏ**.

### 7.1. Không cắt giữa surrogate pair khi chia buffer

Nếu stream/chunk đầu kết thúc bằng **high surrogate** và chunk tiếp theo bắt đầu bằng **low surrogate**, khi xử lý bằng cùng `CharsetEncoder` ở chế độ incremental, phải **giữ code unit chưa đủ** để ghép với phần tiếp theo, không tự coi nó là malformed ngay lập tức.

Ngược lại, nếu đã gọi encode với `endOfInput=true` mà chỉ còn high surrogate lẻ, coder có thể báo malformed.

Điểm này tương tự UTF-8 decoder khi byte sequence bị chia giữa hai network packets: không phải lỗi chỉ vì **gói hiện tại** kết thúc giữa một ký tự; lỗi xuất hiện khi đã biết hết input hoặc gặp bytes vi phạm quy tắc.

## 8. Streaming và trạng thái CoderResult

Đối với stream lớn hoặc giao thức có dữ liệu đến từng phần, ứng dụng không nhất thiết có toàn bộ input trong một buffer. Cả decoder lẫn encoder có API incremental:

```java
CoderResult decoderResult = decoder.decode(
        ByteBuffer input,
        CharBuffer output,
        boolean endOfInput);

CoderResult encoderResult = encoder.encode(
        CharBuffer input,
        ByteBuffer output,
        boolean endOfInput);
```

Đây là **chữ ký minh họa**; khi đưa vào Java cần các biến đúng kiểu đã khai báo. Các phương thức nhận `endOfInput`, sau đó thường cần gọi `flush` để kết thúc một operation.

`CoderResult` có bốn trạng thái chính:

| Kết quả | Phương thức kiểm tra | Ý nghĩa | Xử lý điển hình |
| --- | --- | --- | --- |
| `UNDERFLOW` | `isUnderflow()` | Hết input hiện có hoặc chưa đủ input để tạo đơn vị tiếp theo | Nạp thêm input; nếu hết thật thì kết thúc operation |
| `OVERFLOW` | `isOverflow()` | Output buffer không đủ chỗ | Đẩy/đọc output, rồi thử tiếp |
| `MALFORMED` | `isMalformed()` | Dữ liệu input sai cấu trúc | REPORT/REPLACE/IGNORE theo policy |
| `UNMAPPABLE` | `isUnmappable()` | Input hợp lệ nhưng không ánh xạ được | REPORT/REPLACE/IGNORE theo policy |

**UNDERFLOW không đồng nghĩa lỗi.** Đối với UTF-8, 0xC3 chưa đủ để biết code point hoàn chỉnh. Với `endOfInput=false`, decoder có thể trả UNDERFLOW và để lại byte chờ phần sau; nếu stream kết thúc thật, ở lần gọi cuối `endOfInput=true` có thể chuyển thành malformed.

**OVERFLOW cũng không đồng nghĩa lỗi charset.** Nó chỉ có nghĩa output buffer hết chỗ. Hệ thống phải chuyển/giải phóng output buffer rồi gọi tiếp, không tự vứt input hay nâng `endOfInput` sai.

### Vòng đời coder chuẩn

```text
new Decoder/Encoder
      |
      v
reset() nếu coder đã dùng trước
      |
      v
decode/encode(input, output, false)
      |        |
      |        +-- UNDERFLOW: chờ/nạp thêm input
      |        +-- OVERFLOW: xả output, thử lại
      |        +-- ERROR: xử lý theo chính sách
      v
decode/encode(input, output, true)  // xác nhận hết input
      |
      v
flush(output)                       // có thể cần nhiều lần nếu OVERFLOW
      |
      v
Hoàn tất; reset trước operation tiếp theo
```

Theo Oracle Java 17, decoder/encoder là **stateful** và không thread-safe. Sau khi dùng xong một operation, reset trước operation mới; không dùng chúng như hàm thuần có thể gọi chồng chéo từ nhiều thread.

## 9. Streaming UTF-8 decoder: byte bị chia đôi không phải lỗi

Chúng ta sẽ đưa hai byte UTF-8 của `é` (U+00E9) thành **hai đợt input**: `C3` rồi `A9`. Trong đợt đầu, không thể decode ký tự hoàn chỉnh; sau đợt hai, mới có đủ dữ liệu.

### Chương trình 4 — ByteBuffer.compact và decoder

Tệp `StreamingDecoderDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class StreamingDecoderDemo {
    public static void main(String[] args) throws Exception {
        CharsetDecoder decoder = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.allocate(4);
        CharBuffer output = CharBuffer.allocate(4);

        input.put((byte) 0xC3);
        input.flip();

        CoderResult first = decoder.decode(
                input, output, false);

        System.out.println("firstUnderflow=" +
                first.isUnderflow());
        System.out.println("bytesWaiting=" +
                input.remaining());

        // Giữ byte C3 chưa xử lý, nối A9 từ chunk sau.
        input.compact();
        input.put((byte) 0xA9);
        input.flip();

        CoderResult second = decoder.decode(
                input, output, true);
        CoderResult flushed = decoder.flush(output);

        output.flip();
        char decoded = output.get();

        System.out.printf(Locale.ROOT,
                "decoded=U+%04X%n", (int) decoded);
        System.out.println("secondUnderflow=" +
                second.isUnderflow());
        System.out.println("flushedUnderflow=" +
                flushed.isUnderflow());
        System.out.println("bytesLeft=" +
                input.remaining());
    }
}
```

```bash
javac -encoding UTF-8 StreamingDecoderDemo.java
java StreamingDecoderDemo
```

Stdout:

```text
firstUnderflow=true
bytesWaiting=1
decoded=U+00E9
secondUnderflow=true
flushedUnderflow=true
bytesLeft=0
```

Diễn giải:

- Lần đầu `endOfInput=false`, chỉ có byte C3, decoder giữ byte chưa xử lý và trả UNDERFLOW.
- `input.compact()` dồn **byte chưa tiêu thụ** về đầu buffer; không được gọi `clear()` rồi đánh mất nó.
- Sau khi thêm A9, chuỗi UTF-8 `C3 A9` hợp lệ và được giải thành `é`.
- Chỉ **sau đợt cuối** mới gọi `decode(..., true)` rồi `flush`.
- Ví dụ dùng buffer đủ lớn nên không có OVERFLOW; chương trình streaming production phải xử lý cả trường hợp output buffer đầy.

**Một lỗi thường gặp:** tưởng rằng `input.remaining()==0` sau UNDERFLOW. Khi thiếu byte kết thúc một sequence, decoder có thể **để nguyên bytes chưa tiêu thụ**. Đọc `position/limit` để biết còn gì trước khi nạp thêm. Không chỉ dựa vào `CoderResult.isUnderflow()` mà quên giữ input remainder.

## 10. Streaming encoder: hai UTF-16 surrogate units đến ở hai đợt

Encoder cũng có trạng thái tương tự. Giả sử muốn ghi emoji `😀` có code point U+1F600, được Java biểu diễn bằng hai UTF-16 code units `\uD83D\uDE00`. Nếu chunk đầu chỉ có high surrogate, coder chưa đủ dữ liệu.

### Chương trình 5 — giữ high surrogate qua ranh giới chunk

Tệp `StreamingEncoderDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class StreamingEncoderDemo {

    private static String hex(ByteBuffer bytes) {
        StringBuilder result = new StringBuilder();
        while (bytes.hasRemaining()) {
            if (result.length() > 0) {
                result.append(' ');
            }
            result.append(String.format(
                    Locale.ROOT, "%02X",
                    Byte.toUnsignedInt(bytes.get())));
        }
        return result.toString();
    }

    public static void main(String[] args) throws Exception {
        CharsetEncoder encoder = StandardCharsets.UTF_8
                .newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT);

        CharBuffer input = CharBuffer.allocate(4);
        ByteBuffer output = ByteBuffer.allocate(8);

        input.put('\uD83D');
        input.flip();

        CoderResult first = encoder.encode(
                input, output, false);
        System.out.println("firstUnderflow=" +
                first.isUnderflow());
        System.out.println("charsWaiting=" +
                input.remaining());

        // Đưa high surrogate còn lại về đầu, nạp low surrogate.
        input.compact();
        input.put('\uDE00');
        input.flip();

        CoderResult second = encoder.encode(
                input, output, true);
        CoderResult flushed = encoder.flush(output);

        output.flip();
        System.out.println("secondUnderflow=" +
                second.isUnderflow());
        System.out.println("flushedUnderflow=" +
                flushed.isUnderflow());
        System.out.println("utf8=" + hex(output));
    }
}
```

```bash
javac -encoding UTF-8 StreamingEncoderDemo.java
java StreamingEncoderDemo
```

Stdout:

```text
firstUnderflow=true
charsWaiting=1
secondUnderflow=true
flushedUnderflow=true
utf8=F0 9F 98 80
```

Các byte `F0 9F 98 80` là UTF-8 của U+1F600. Coder không nên “chữa” high surrogate lẻ trong chunk đầu bằng replacement khi **chưa xác nhận kết thúc input**. Trong ứng dụng thật, hãy dùng buffer đủ chỗ hoặc logic OVERFLOW và giữ nguyên những `char` chưa được tiêu thụ.

### Khi một buffer nhỏ hơn đơn vị cần tạo?

- UTF-8 encoder có thể cần tối đa bốn byte cho một supplementary code point.
- Một output `ByteBuffer` quá nhỏ để chứa ngay một đơn vị output có thể khiến coder trả OVERFLOW **mà không tiêu thụ input tương ứng**.
- Nếu retry với buffer vẫn quá nhỏ và không bao giờ có chỗ, vòng lặp có thể kẹt.
- Cần kích thước buffer hợp lý, hoặc cơ chế quản lý vùng đệm có thể lớn lên.

Những lỗi đó là **lỗi sử dụng API/buffer**, khác với input malformed hoặc unmappable. Chọn `CodingErrorAction.IGNORE` không giải quyết được output OVERFLOW.

## 11. CoderResult: báo lỗi khác ném exception

Khi dùng API one-shot:

```java
CharBuffer result = decoder.decode(bytes);
ByteBuffer resultBytes = encoder.encode(chars);
```

Với `REPORT`, những phương thức này có thể ném `CharacterCodingException`, cụ thể hơn là `MalformedInputException` hoặc `UnmappableCharacterException`.

Khi dùng API incremental:

```java
CoderResult result =
        decoder.decode(input, output, endOfInput);
```

Coder trả về `CoderResult` để caller biết trạng thái. Với `REPORT`, trường hợp malformed hoặc unmappable được mô tả bằng **CoderResult lỗi**, **không tự ném exception từ lần gọi này**. Caller có thể dùng:

```java
if (result.isMalformed()) {
    // Báo byte sequence hỏng.
}
if (result.isUnmappable()) {
    // Báo ký tự không ánh xạ được.
}
if (result.isError()) {
    result.throwException();
}
```

Đây là đoạn mã minh họa trong method, `throwException()` có thể ném `CharacterCodingException`; caller cần khai báo hoặc bắt phù hợp.

### API của CoderResult

| Phương thức | Ý nghĩa |
| --- | --- |
| `isUnderflow()` | Thiếu input hiện có hoặc đã hết input để xử lý |
| `isOverflow()` | Output buffer không còn đủ dung lượng |
| `isMalformed()` | Input có sequence sai cấu trúc |
| `isUnmappable()` | Input hợp lệ nhưng không thể ánh xạ |
| `isError()` | True cho malformed hoặc unmappable |
| `length()` | Độ dài **đoạn input sai** (đơn vị theo coder) |
| `throwException()` | Ném loại exception phù hợp với trạng thái |

`CoderResult.length()` chỉ có ý nghĩa với result lỗi; không gọi với UNDERFLOW/OVERFLOW rồi coi giá trị là “bao nhiêu byte đã đọc”. Số bytes/chars tiêu thụ được biết qua **`position` của buffer** trước và sau encode/decode.

**Chú ý đơn vị:** decoder nhận `ByteBuffer`, nên length của lỗi liên quan byte input; encoder nhận `CharBuffer`, nên length liên quan UTF-16 code units input. Không mặc định error length = số Unicode graphemes.

## 12. REPORT, REPLACE, IGNORE trong thiết kế nghiệp vụ

Quyết định lỗi không nên chỉ nhằm “tránh ném exception”. Nó ảnh hưởng tính đúng đắn, bảo mật và trải nghiệm.

| Ngữ cảnh | Hướng thường thích hợp | Lý do |
| --- | --- | --- |
| Đọc file cấu hình, JSON, dữ liệu hợp đồng | `REPORT` | Không chấp nhận silently corrupt giá trị khóa/định danh |
| Nhận API payload có charset xác định | `REPORT` | Trả lỗi 4xx/validation nếu byte không hợp lệ |
| Import dữ liệu lịch sử cần khám phá lỗi | `REPORT` + log/report vị trí; có pipeline repair riêng | Phát hiện và truy vết dữ liệu lỗi |
| Hiển thị bản preview không đáng tin, ưu tiên best effort | Có thể `REPLACE` theo policy | Người đọc thấy dấu `�` báo có dữ liệu hỏng |
| Tìm kiếm nội dung có dung sai | Cân nhắc `REPLACE` nếu được công bố | Có thể hiển thị một phần nhưng không lưu đè gốc |
| Bỏ chuỗi không hợp lệ không quan trọng | Chỉ dùng `IGNORE` khi được phép mất dữ liệu | Không biết dữ liệu nào đã bị xóa |
| Password, token, chữ ký số, khóa map | Tránh `REPLACE`/`IGNORE` | Những thay đổi âm thầm có thể tạo collision hoặc sai xác thực |
| Export sang charset legacy | `REPORT` hoặc đường dẫn transliteration rõ ràng | Không thay tên/dữ liệu khách hàng bằng `?` vô thức |

**Transliteration không đồng nghĩa charset replacement.** Ví dụ ứng dụng chuyển chữ có dấu thành ASCII theo một bộ quy tắc nghiệp vụ là **biến đổi ngôn ngữ chủ đích**, cần được công bố và kiểm thử riêng; `CodingErrorAction.REPLACE` chỉ đơn giản ghi replacement khi không mã hóa được, không tạo bản chuyển tự có ý nghĩa.

### 12.1. Khi nào nên ghi lại lỗi?

Với `REPORT`, có thể báo rằng payload có byte không hợp lệ, ghi tên nguồn và offset byte nếu có. Nhưng không log toàn bộ văn bản chứa dữ liệu bí mật hoặc PII một cách không kiểm soát. Một chiến lược tốt là:

- Trả lỗi có ý nghĩa cho bên cung cấp dữ liệu.
- Ghi metric số lỗi decode/encode theo nguồn.
- Giữ bản gốc để có thể xử lý lại nếu chính sách cho phép.
- Không tự thử nhiều charset liên tiếp rồi chọn “cái không ném exception” như bằng chứng chắc chắn đã chọn đúng charset.

Chọn một charset hợp lệ nhưng sai vẫn có thể decode được thành chữ vô nghĩa (**mojibake**) mà coder **không** báo lỗi. Cần metadata/protocol và kiểm tra ngữ nghĩa phù hợp, không chỉ kiểm tra exception.

## 13. I/O với file và network: gắn decoder/encoder vào Reader/Writer

Khi đọc từ stream, có thể dùng `InputStreamReader` với decoder được cấu hình, và `OutputStreamWriter` với encoder được cấu hình:

```java
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

// Ví dụ trong method:
InputStreamReader reader = new InputStreamReader(
        inputStream,
        StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT));

OutputStreamWriter writer = new OutputStreamWriter(
        outputStream,
        StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT));
```

Đây là mã minh họa có `inputStream` và `outputStream` tồn tại từ bên ngoài; trong ứng dụng nên dùng `try-with-resources` khi sở hữu stream.

Với I/O streaming, các lớp reader/writer quản lý buffer và trạng thái coder bên trong; bạn không phải tự viết `ByteBuffer.compact()`/`CoderResult` chỉ để đọc một file thông thường. Nhưng **cấu hình hành động lỗi** vẫn quan trọng.

### 13.1. Ví dụ Reader nghiêm ngặt có thể chạy độc lập

Tệp `StrictReaderDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictReaderDemo {
    public static void main(String[] args) throws Exception {
        byte[] badUtf8 = {0x41, (byte) 0xC3, 0x28};

        boolean rejected = false;
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(badUtf8),
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT))) {

            char[] buf = new char[8];
            while (reader.read(buf) != -1) {
                // Chỉ đọc để kiểm tra nguồn hợp lệ.
            }
        } catch (CharacterCodingException ex) {
            rejected = true;
        }

        System.out.println("rejected=" + rejected);
    }
}
```

```bash
javac -encoding UTF-8 StrictReaderDemo.java
java StrictReaderDemo
```

Stdout:

```text
rejected=true
```

Nếu dùng overload `InputStreamReader(input, StandardCharsets.UTF_8)` tiện dụng, chính sách gặp malformed/unmappable input có thể không tương đương với decoder `REPORT` được truyền tường minh. Khi yêu cầu đầu vào nghiêm ngặt, nên cung cấp decoder đã được cấu hình để không âm thầm thay ký tự.

### 13.2. Files.readString và Files.writeString

API `Files.readString(path, charset)` và `Files.writeString(path, text, charset)` cung cấp thao tác file tiện lợi. Theo Java 17, `Files.readString` báo lỗi cho malformed/unmappable byte sequences bằng `IOException` thích hợp, và `Files.writeString` cũng báo lỗi khi không thể encode văn bản theo charset được chọn. Tuy nhiên, **đừng đánh đồng** tất cả overload file API với `new String(bytes, charset)` hoặc `String.getBytes(charset)`: mỗi API có contract khác nhau về xử lý dữ liệu không hợp lệ.

Khi cần streaming lớn, quản lý buffered reader/writer và charset tường minh; khi cần hiểu chính xác từng action, dùng coder/reader/writer hỗ trợ cấu hình. Trên server đa ngôn ngữ, không để charset mặc định của host quyết định cách đọc dữ liệu nếu giao thức đã nêu UTF-8.

## 14. Đừng nhầm charset, BOM và locale

Một số lỗi sản phẩm dễ được mô tả nhầm thành “lỗi tiếng Việt”:

- **Sai charset:** một file UTF-8 bị đọc như Windows-1252, gây mojibake.
- **Dữ liệu byte malformed:** một UTF-8 sequence bị cắt/mất byte.
- **BOM:** một byte-order mark ở đầu luồng có thể cần quy tắc phát hiện/bỏ qua phù hợp với charset và parser; coder không tự là bộ phát hiện mọi kiểu BOM.
- **Sai Unicode normalization:** `"é"` có thể là precomposed hoặc `"e\u0301"`, nhìn giống nhưng `String.equals` khác.
- **Sai locale:** thứ tự số, ngày, tên tháng hoặc chữ hoa/thường không đúng ngôn ngữ người dùng.
- **Sai font/rendering:** glyph không tồn tại hoặc shaping thiếu; Unicode text có thể hoàn toàn hợp lệ nhưng vẫn hiển thị ô vuông.

`CharsetDecoder`/`CharsetEncoder` chủ yếu giải quyết **chuyển đổi byte ↔ ký tự**. Chúng **không** dịch ngôn ngữ, không tự chuyển ký tự decomposed sang NFC, không tự chọn phông và không xử lý collation theo locale.

Ví dụ: sau khi decode đúng UTF-8, bạn có thể dùng `Normalizer.normalize(text, Normalizer.Form.NFC)` **nếu hợp đồng dữ liệu yêu cầu**. Đó là một bước riêng; đừng tự normalize password, chữ ký hoặc các token khi protocol không cho phép.

## 15. UTF-8 và supplementary characters

Java `String` dùng UTF-16 code units. Một supplementary Unicode code point như `😀` (U+1F600) có:

- **Hai UTF-16 code units**: `D83D DE00`.
- **Bốn UTF-8 bytes**: `F0 9F 98 80`.
- **Một Unicode code point**.
- Thường **một grapheme cluster** với emoji đơn, nhưng emoji ghép có thể chứa nhiều code points.

Không dùng `String.length()` để dự đoán UTF-8 byte size. Không cắt UTF-8 byte stream tùy ý rồi gọi `new String(chunk, UTF_8)` cho mỗi chunk: một code point có thể bị chia giữa hai chunk, mỗi lần decode riêng có thể tạo replacement và **làm hỏng dữ liệu dù toàn bộ stream ban đầu hợp lệ**.

**Quy tắc cho streaming:**

1. Giữ byte sequence còn thiếu sau UNDERFLOW, nối với chunk tiếp theo.
2. Chỉ thông báo end-of-input ở chunk cuối thực sự.
3. Flush coder sau khi kết thúc.
4. Không dùng output OVERFLOW làm dấu hiệu dữ liệu sai.
5. Giữ dữ liệu theo **cùng một Charset và coder state** trong một operation.

Với văn bản có ký tự combining marks/emoji ZWJ, việc decode đúng chỉ bảo đảm Unicode code points; việc cắt/grapheme segmentation thuộc tầng xử lý text riêng.

## 16. Một checklist kiểm thử hiệu quả

### 16.1. Kiểm thử decoder

| Input | Charset | Action | Kỳ vọng |
| --- | --- | --- | --- |
| `41 42` | UTF-8 | REPORT | `AB` |
| `C3 A9` | UTF-8 | REPORT | U+00E9 |
| `41 C3 28 42` | UTF-8 | REPORT | Lỗi malformed |
| `41 C3 28 42` | UTF-8 | REPLACE | `A\uFFFD(B` |
| `41 C3 28 42` | UTF-8 | IGNORE | `A(B` |
| `C3`, sau đó `A9` ở hai chunk | UTF-8 | REPORT + incremental | U+00E9 |
| `C3` ở **cuối thực** stream | UTF-8 | REPORT | Lỗi malformed |

### 16.2. Kiểm thử encoder

| Input | Charset | Action | Kỳ vọng |
| --- | --- | --- | --- |
| `"AB"` | ISO-8859-1 | REPORT | Bytes `41 42` |
| `"A€B"` | UTF-8 | REPORT | `41 E2 82 AC 42` |
| `"A€B"` | ISO-8859-1 | REPORT | Lỗi unmappable |
| `"A€B"` | ISO-8859-1 | REPLACE + `!` | `41 21 42` |
| `"A€B"` | ISO-8859-1 | IGNORE | `41 42` |
| High surrogate đơn lẻ | UTF-8 | REPORT | Lỗi malformed |
| High + low surrogate hợp lệ hai chunk | UTF-8 | REPORT + incremental | `F0 9F 98 80` |

### 16.3. Test nghiệp vụ

- Import/export file phải chỉ định charset chuẩn, không dựa default hệ thống.
- Với `REPORT`, lỗi không được bị bắt rồi silently bỏ qua/ghi file trống.
- Với `REPLACE`/`IGNORE`, UI hoặc log phải thể hiện việc có thể mất dữ liệu khi có yêu cầu.
- Input bị chia nhiều chunk phải decode giống input đầy đủ, với các chunk boundaries khác nhau.
- Không parse charset chỉ dựa vào locale người dùng; language tag `vi-VN` không xác định file dùng UTF-8 hay Windows-1258.
- Kiểm tra dấu tiếng Việt, CJK, emoji và ký tự ngoài BMP.
- Với charset legacy, kiểm tra cả khả năng encode những ký tự thực tế xuất hiện.
- Kiểm thử UTF-8 malformed, isolated surrogate, overlong encodings và illegal code point sequences; không chấp nhận byte malformed chỉ vì “nhìn có vẻ đúng”.
- Bảo toàn bản gốc khi pipeline cần audit hoặc sửa dữ liệu từ nguồn.
- Xác minh đúng kiểu exception và không để error action thay đổi giữa các luồng.

### 16.4. Lỗi thường gặp

| Lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| `new String(bytes)` không chỉ rõ charset | Phụ thuộc default charset/JDK context | Truyền `StandardCharsets.UTF_8` theo contract |
| Dùng `new String(bytes, UTF_8)` rồi tin input luôn hợp lệ | Malformed bytes có thể thành U+FFFD | Dùng decoder `REPORT` khi cần strict |
| Dùng `String.getBytes(ISO_8859_1)` cho dữ liệu đa ngôn ngữ | Ký tự không thể mã hóa bị thay | Dùng encoder `REPORT` hoặc UTF-8 |
| Chỉ cấu hình `onMalformedInput`, quên `onUnmappableCharacter` | Chính sách không nhất quán | Cấu hình cả hai theo policy |
| Coi UNDERFLOW là lỗi | Từ chối stream có code point bị chia chunk | Giữ remainder, nạp thêm input |
| Coi OVERFLOW là lỗi | Dừng khi chỉ hết output buffer | Xả output và thử lại |
| Gọi `clear()` sau khi còn input remainder | Mất byte/chars của một ký tự | Dùng `compact()` rồi nạp tiếp |
| Đánh `endOfInput=true` trước chunk cuối | Incomplete sequence có thể bị coi malformed | Chỉ kết thúc ở cuối stream thực |
| Quên `flush` sau lần gọi cuối | Có thể mất dữ liệu trong stateful charset | Hoàn thành đúng vòng đời coder |
| Dùng `IGNORE` để “sửa lỗi font” | Xóa dữ liệu không thể phục hồi | Sửa charset/font nguồn, không che lỗi |
| Chia sẻ coder giữa nhiều thread | Race/state corruption | Coder riêng cho operation |
| Trộn Unicode normalization với decode | Sai chức năng, có thể sửa dữ liệu không được phép | Tách các tầng rõ ràng |
| Dự đoán UTF-8 bytes bằng `String.length()` | Sai với dấu, CJK, emoji | Đếm bytes đã mã hóa |
| Xem decode không lỗi là charset chắc chắn đúng | Mojibake vẫn có thể hợp lệ | Dựa metadata/protocol, kiểm tra ngữ nghĩa |

## 17. Bài tập và đáp án

**Bài 1 — phân loại lỗi.** Byte `C3 28` được khai báo UTF-8 nhưng không phải UTF-8 hợp lệ. Đây là malformed hay unmappable?

**Đáp án:** Malformed, vì byte sequence không đúng cấu trúc UTF-8.

**Bài 2 — phân loại lỗi.** Chuỗi `"A€B"` được encode sang ISO-8859-1. Ký tự euro hợp lệ nhưng không thuộc bộ mã này. Đây là gì?

**Đáp án:** Unmappable. Chuyển sang UTF-8 thì chuỗi này mã hóa được.

**Bài 3 — chính sách.** Khi nhận file dữ liệu kế toán từ nhà cung cấp, nên dùng `IGNORE` để tránh phát sinh lỗi không?

**Đáp án:** Thông thường không. Nếu tính toàn vẹn quan trọng, dùng `REPORT`, thông báo file không hợp lệ và sửa nguồn. `IGNORE` âm thầm xóa byte/ký tự và có thể đổi số tài khoản, mã hoặc tên.

**Bài 4 — default.** `StandardCharsets.UTF_8.newDecoder()` mặc định dùng hành động nào khi malformed/unmappable theo Java 17? `new String(bytes, UTF_8)` có giống hệt không?

**Đáp án:** Decoder mới mặc định `REPORT`. Constructor String tiện dụng dùng replacement cho malformed/unmappable bytes, nên không tương đương.

**Bài 5 — streaming.** Một chunk kết thúc bằng byte `0xC3`; chunk sau bắt đầu bằng `0xA9`. Có nên báo lỗi ngay chunk đầu?

**Đáp án:** Không nếu stream chưa kết thúc. Với decoder incremental, `endOfInput=false` cho phép giữ byte còn thiếu; khi nhận A9, giải thành `é`.

**Bài 6 — CoderResult.** Decoder trả `OVERFLOW`. Có phải dữ liệu bị sai mã hóa không?

**Đáp án:** Không. Output buffer không đủ chỗ; cần xả/đọc output và gọi tiếp.

**Bài 7 — replacement.** `CharsetEncoder.replaceWith` nhận `String` hay `byte[]`? Còn `CharsetDecoder.replaceWith`?

**Đáp án:** Encoder nhận `byte[]`; decoder nhận `String`.

**Bài 8 — unicode.** Một emoji U+1F600 có hai UTF-16 code units. Nếu encode hai nửa ở hai request độc lập thì điều gì có thể xảy ra?

**Đáp án:** Mỗi nửa là surrogate lẻ và có thể bị báo malformed/thay thế. Muốn encode thành `F0 9F 98 80`, phải giữ cả cặp trong một operation hoặc nối input còn thiếu trong stateful encoder.

**Bài 9 — exceptions.** API incremental có `CoderResult.isError()`; khi nào cần `throwException()`?

**Đáp án:** Với `REPORT`, caller có thể chủ động gọi `throwException()` để chuyển CoderResult lỗi thành exception tương ứng. One-shot `decode(ByteBuffer)`/`encode(CharBuffer)` có thể ném trực tiếp.

**Bài 10 — charset và locale.** Người dùng chọn `vi-VN`. Có thể từ đó suy byte file của họ chắc chắn UTF-8 không?

**Đáp án:** Không. Locale là ngôn ngữ/khu vực; charset của file do hợp đồng, metadata hoặc nguồn xuất quyết định. Có thể là UTF-8 hoặc charset legacy khác.

**Bài 11 — IO.** Khi dùng `InputStreamReader(inputStream, decoder)` với `REPORT`, malformed byte được thay bằng U+FFFD và tiếp tục hay phát sinh lỗi?

**Đáp án:** Phát sinh `CharacterCodingException` thích hợp (thường là `MalformedInputException`) từ thao tác đọc; không tự chuyển sang replacement vì đã chỉ định `REPORT`.

**Bài 12 — kiểm thử thực tế.** Tại sao test chỉ có chữ ASCII không đủ để xác minh charset pipeline?

**Đáp án:** Nhiều charset cùng mã hóa ASCII giống nhau. Cần thêm tiếng Việt, CJK, euro, supplementary characters, malformed bytes và các điều kiện streaming để thấy khác biệt.

## 18. Tổng kết

- **`CharsetDecoder` = byte → UTF-16 chars**, **`CharsetEncoder` = UTF-16 chars → byte**. Cả hai cần một `Charset` xác định và giữ trạng thái trong quá trình chuyển đổi.
- Hai lỗi chính là **MALFORMED** (input sai cấu trúc) và **UNMAPPABLE** (input hợp lệ nhưng không biểu diễn được trong charset/ánh xạ đích).
- `CodingErrorAction.REPORT` báo lỗi; `REPLACE` dùng replacement; `IGNORE` bỏ đoạn lỗi. **REPLACE và IGNORE có thể làm mất dữ liệu.**
- Encoder/decoder mới của Java 17 mặc định **REPORT**, trong khi các API tiện dụng như `new String(bytes, charset)` và `String.getBytes(charset)` có thể sử dụng replacement: **cần kiểm tra contract từng API**.
- One-shot coder có thể ném `CharacterCodingException`; incremental coder trả `CoderResult`. `UNDERFLOW` và `OVERFLOW` là trạng thái buffer bình thường, không phải lỗi charset.
- Với dữ liệu chia chunk, **giữ remainder**, không đánh dấu hết input quá sớm, xử lý OVERFLOW, gọi final encode/decode và `flush` đúng thứ tự.
- UTF-8 là encoding, **không phải ngôn ngữ**; không lấy `Locale` làm phương pháp xác định charset.
- Với dữ liệu quan trọng, ưu tiên **REPORT + xử lý lỗi rõ ràng**; không che lỗi hoặc sửa byte âm thầm.
- Không dùng chung các coder mutable giữa nhiều luồng; tạo coder cho mỗi operation hoặc quản lý ownership đúng cách.

### Tài liệu Java SE 17 chính thức

- [CharsetDecoder — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [CharsetEncoder — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html)
- [CodingErrorAction — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html)
- [CoderResult — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html)
- [String — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Files — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
