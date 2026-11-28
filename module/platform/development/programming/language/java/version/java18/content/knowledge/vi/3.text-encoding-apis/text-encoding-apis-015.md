# `CharsetDecoder` và `CodingErrorAction.REPORT`: phát hiện byte không hợp lệ thay vì thay thế âm thầm

## 1. Vì sao cần giải mã nghiêm ngặt?

Khi đọc dữ liệu văn bản, chương trình nhận một dãy byte rồi dùng charset để chuyển thành ký tự Java. Nếu byte không hợp lệ theo charset đã chọn, ứng dụng cần quyết định rõ phải làm gì: báo lỗi, thay bằng ký tự thay thế hay bỏ qua phần dữ liệu lỗi.

Các API tiện lợi có thể ưu tiên tiếp tục xử lý. Ví dụ, constructor `String(byte[], Charset)` thay thế chuỗi byte không hợp lệ bằng replacement string của charset. Điều này giúp chương trình tiếp tục chạy nhưng làm mất thông tin gốc. Với dữ liệu định danh, cấu hình, giao dịch, nội dung ký số hoặc bản ghi cần toàn vẹn, thay thế âm thầm có thể gây hậu quả nghiêm trọng.

`CharsetDecoder` cho phép kiểm soát hành vi giải mã. Với `CodingErrorAction.REPORT`, decoder báo lỗi khi gặp malformed input hoặc unmappable input. Đối với UTF-8, byte sai cấu trúc thường được phân loại là malformed input.

Bài này tập trung vào cách dùng decoder nghiêm ngặt, phân biệt lỗi dữ liệu với lỗi charset, và quyết định đúng cách xử lý trong ứng dụng Java hiện đại.

## 2. Decoder và các loại lỗi

### 2.1. `CharsetDecoder` làm gì?

`CharsetDecoder` chuyển một `ByteBuffer` thành một `CharBuffer` theo quy tắc của một `Charset`.

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder();

ByteBuffer input = ByteBuffer.wrap(
        new byte[] { 0x43, (byte) 0xC3, (byte) 0xA0 });

String text = decoder.decode(input).toString();
System.out.println(text); // Cà
```

Trong ví dụ, byte `43 C3 A0` là UTF-8 của chuỗi `Cà`. Decoder đọc byte và tạo ra ký tự UTF-16 bên trong `String`.

Một decoder mới được tạo từ `Charset.newDecoder()` có hành động mặc định là `REPORT` đối với malformed input và unmappable character. Khi yêu cầu toàn vẹn dữ liệu, vẫn nên cấu hình hành động tường minh để thể hiện rõ ý định của chương trình.

### 2.2. Malformed input

Malformed input là dữ liệu đầu vào không tạo thành chuỗi byte hợp lệ theo charset. Với UTF-8, ví dụ gồm:

- Byte mở đầu nhiều byte nhưng thiếu byte tiếp nối.
- Byte tiếp nối xuất hiện khi không có byte mở đầu hợp lệ.
- Encoding overlong, dùng nhiều byte hơn quy định để biểu diễn cùng code point.
- Byte sequence cố mã hóa surrogate code point.
- Byte sequence biểu diễn code point vượt quá giới hạn Unicode.

Ví dụ byte `C3 28` không phải chuỗi UTF-8 hợp lệ: `C3` cần một byte tiếp nối hợp lệ, nhưng `28` là ký tự ASCII `(`.

```text
Hợp lệ:       43 C3 A0 20 63 61
Không hợp lệ: 43 C3 28 20 63 61
```

Với `REPORT`, decoder không tự chèn `U+FFFD` để che lỗi. Nó báo lỗi qua `CoderResult` hoặc ném `MalformedInputException` khi dùng API giải mã tiện lợi.

### 2.3. Unmappable character

Unmappable character là dữ liệu ký tự không thể biểu diễn bằng charset đích. Khái niệm này thường thấy rõ hơn ở chiều mã hóa với `CharsetEncoder`.

Ví dụ, ASCII không thể biểu diễn ký tự tiếng Việt:

```java
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    encoder.encode(CharBuffer.wrap("Tiếng Việt"));
} catch (UnmappableCharacterException ex) {
    System.out.println("Charset đích không biểu diễn được ký tự.");
}
```

Ở chiều giải mã, `CharsetDecoder` cũng có cấu hình cho malformed input và unmappable input. Với UTF-8, lỗi byte sai cấu trúc thường là malformed input; không nên gán nhầm mọi lỗi decode thành unmappable.

## 3. Ba chính sách `CodingErrorAction`

Java cung cấp ba hành động để xử lý lỗi trong decoder và encoder:

| Hành động | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `REPORT` | Báo lỗi khi gặp dữ liệu malformed hoặc unmappable | Dữ liệu cần toàn vẹn, cần xác định chính xác lỗi |
| `REPLACE` | Thay dữ liệu lỗi bằng replacement value | Chấp nhận mất một phần thông tin và có chính sách thay thế rõ ràng |
| `IGNORE` | Bỏ qua dữ liệu lỗi | Chỉ dùng khi định dạng cho phép bỏ qua |

Ví dụ đặt cả hai hành động:

```java
var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

`onMalformedInput` quy định hành vi khi byte đầu vào không hợp lệ. `onUnmappableCharacter` quy định hành vi khi dữ liệu không thể ánh xạ trong charset. Cả hai phương thức trả về chính decoder để có thể cấu hình nối tiếp.

### 3.1. Vì sao `REPORT` phù hợp với dữ liệu quan trọng?

Giả sử một file chứa mã khách hàng hoặc dữ liệu giao dịch. Nếu byte sai bị thay bằng `U+FFFD`, chương trình vẫn có thể tạo ra chuỗi và tiếp tục lưu dữ liệu. Kết quả có thể tạo ra mã định danh khác với dữ liệu gốc hoặc làm thay đổi nội dung đã ký.

Với `REPORT`, ứng dụng dừng tại điểm lỗi và có thể ghi nhận file nguồn cùng vị trí byte, từ chối bản ghi, yêu cầu gửi lại dữ liệu, đưa file vào khu vực quarantine hoặc giữ nguyên file gốc để điều tra.

Không phải ứng dụng nào cũng cần dừng toàn bộ xử lý. Có thể cô lập lỗi theo từng bản ghi nếu định dạng cho phép phân tách và khôi phục an toàn.

### 3.2. Khi nào cân nhắc `REPLACE` hoặc `IGNORE`?

`REPLACE` có thể phù hợp với công cụ xem log hỏng, nơi cần hiển thị phần còn đọc được. Tuy nhiên, phải ghi rõ rằng nội dung lỗi sẽ bị thay thế.

`IGNORE` loại bỏ dữ liệu lỗi khỏi kết quả. Việc này có thể làm hai chuỗi khác nhau trở thành giống nhau, thay đổi cấu trúc CSV/JSON hoặc làm mất nội dung. Chỉ dùng khi định dạng hoặc chính sách xử lý cho phép bỏ qua chính xác loại dữ liệu đó. Không dùng `IGNORE` chỉ để tránh exception.

## 4. Khác biệt giữa `String` tiện lợi và `CharsetDecoder` nghiêm ngặt

Không phải mọi API giải mã byte đều mặc định báo lỗi. Constructor `String(byte[], Charset)` được thiết kế tiện lợi và thay thế chuỗi byte không hợp lệ bằng replacement string của charset.

```java
import java.nio.charset.StandardCharsets;

byte[] malformed = {
        (byte) 0xC3, // Byte mở đầu UTF-8 nhưng byte tiếp theo sai
        (byte) 0x28  // '(' không phải byte tiếp nối hợp lệ
};

String tolerant = new String(malformed, StandardCharsets.UTF_8);
System.out.println(tolerant);
System.out.println(tolerant.codePoints()
        .mapToObj(Integer::toHexString)
        .toList());
```

Chuỗi kết quả chứa ký tự replacement `U+FFFD` thay cho phần byte lỗi, tiếp theo là ký tự `(`. Sau khi thay thế, chương trình không còn biết byte ban đầu đã sai ở đâu nếu không giữ lại mảng byte.

Nếu muốn từ chối byte sai, dùng decoder:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

byte[] malformed = { (byte) 0xC3, (byte) 0x28 };

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    String text = decoder.decode(ByteBuffer.wrap(malformed)).toString();
    System.out.println(text);
} catch (CharacterCodingException ex) {
    System.err.println("Dữ liệu UTF-8 không hợp lệ: " + ex);
}
```

`CharsetDecoder.decode(ByteBuffer)` xử lý toàn bộ input như dữ liệu cuối cùng và ném `CharacterCodingException` khi decoder cấu hình `REPORT` gặp lỗi. Với malformed UTF-8, exception cụ thể thường là `MalformedInputException`.

**Đừng bỏ mảng byte gốc khi dữ liệu quan trọng.** Chuỗi đã chứa replacement character không thể tự khôi phục byte sai ban đầu.

## 5. Những byte UTF-8 cần có trong test

| Byte | Trạng thái | Lý do |
| --- | --- | --- |
| `43 C3 A0` | Hợp lệ | `Cà` |
| `C3 28` | Không hợp lệ | Byte tiếp nối sai |
| `E2 82` ở cuối input | Không hợp lệ khi kết thúc input | Chuỗi 3 byte bị thiếu byte cuối |
| `80` đứng riêng | Không hợp lệ | Byte tiếp nối không có byte mở đầu |
| `C0 AF` | Không hợp lệ | Overlong encoding |
| `ED A0 80` | Không hợp lệ | Cố mã hóa surrogate |
| `F4 90 80 80` | Không hợp lệ | Code point vượt giới hạn Unicode |

UTF-8 decoder chuẩn từ chối các dạng encoding không hợp lệ này. Không tự viết validator UTF-8 bằng cách kiểm tra vài bit đầu byte; dùng charset decoder của Java để tuân theo quy tắc Unicode.

### 5.1. Byte bị thiếu chỉ có thể kết luận khi input đã kết thúc

Khi đọc theo luồng, byte mở đầu có thể xuất hiện ở cuối buffer hiện tại nhưng byte tiếp nối sẽ đến ở buffer kế tiếp. Vì vậy, decoder streaming không được coi mọi chuỗi byte chưa hoàn chỉnh ở cuối buffer là lỗi ngay lập tức.

Với API incremental `decode(input, output, endOfInput)`:

- `endOfInput=false`: decoder có thể giữ byte chưa hoàn chỉnh để chờ buffer tiếp theo.
- `endOfInput=true`: decoder biết không còn byte nào nữa; chuỗi byte bị cắt cụt trở thành malformed input.

Chỉ đánh dấu end-of-input khi thực sự đã nhận EOF hoặc kết thúc payload.

## 6. Dùng `CharsetDecoder` với `REPORT` cho một mảng byte

Ví dụ hoàn chỉnh sau giải mã UTF-8 nghiêm ngặt:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Decode {
    static String decode(byte[] bytes)
            throws CharacterCodingException {

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        return decoder.decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static void main(String[] args) throws Exception {
        byte[] valid = { 0x43, (byte) 0xC3, (byte) 0xA0 };
        System.out.println(decode(valid)); // Cà

        byte[] invalid = { (byte) 0xC3, 0x28 };

        try {
            System.out.println(decode(invalid));
        } catch (CharacterCodingException ex) {
            System.err.println("Từ chối byte lỗi: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Tạo decoder mới cho mỗi lần giải mã độc lập. `CharsetDecoder` có trạng thái và không được thiết kế để nhiều thread dùng đồng thời. API convenience `decode(ByteBuffer)` reset decoder trước khi thực hiện, nhưng tạo decoder mới cho mỗi tác vụ độc lập thường rõ ràng hơn.

## 7. Xác định vị trí byte lỗi bằng `CoderResult`

Nếu chỉ cần biết input hợp lệ hay không, `decode(ByteBuffer)` và exception là đủ. Khi cần ghi log offset của byte lỗi, dùng API incremental `decode(ByteBuffer, CharBuffer, boolean)` để nhận `CoderResult`.

Khi decoder trả kết quả lỗi, vị trí của input buffer chỉ tới byte đầu tiên của chuỗi lỗi chưa được tiêu thụ. Với UTF-8, đó là vị trí bắt đầu của byte sequence malformed.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

byte[] bytes = {
        0x41, 0x42, (byte) 0xC3, 0x28, 0x43
};

ByteBuffer input = ByteBuffer.wrap(bytes);
// UTF-8 tạo không quá một UTF-16 code unit trên mỗi byte.
CharBuffer output = CharBuffer.allocate(bytes.length);

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CoderResult result = decoder.decode(input, output, true);

if (result.isError()) {
    int byteOffset = input.position();
    System.out.println("Malformed input at byte offset " + byteOffset);
    try {
        result.throwException();
    } catch (CharacterCodingException ex) {
        throw new IllegalArgumentException("Invalid UTF-8", ex);
    }
}

if (result.isOverflow()) {
    throw new IllegalStateException("Output buffer không đủ lớn");
}

CoderResult flushResult = decoder.flush(output);
if (flushResult.isError()) {
    try {
        flushResult.throwException();
    } catch (CharacterCodingException ex) {
        throw new IllegalArgumentException("UTF-8 decoder flush failed", ex);
    }
}

output.flip();
String text = output.toString();
```

Trong ví dụ, byte `41 42` (`AB`) hợp lệ; byte lỗi bắt đầu ở offset `2` với `C3 28`. `input.position()` cho biết byte đầu tiên của chuỗi lỗi chưa được tiêu thụ.

`CoderResult` có ba trạng thái thường gặp:

- `UNDERFLOW`: buffer đầu vào đã được xử lý hết; nếu `endOfInput=false`, có thể còn byte chưa hoàn chỉnh được giữ lại.
- `OVERFLOW`: buffer đầu ra không đủ chỗ; cần lấy output ra rồi tiếp tục decode.
- `isError()`: decoder gặp malformed input hoặc unmappable input theo cấu hình.

Đoạn code trên cấp output buffer có kích thước bằng số byte đầu vào, đủ cho UTF-8 vì số UTF-16 code unit tạo ra không vượt quá số byte. Với charset khác, hãy tính kích thước dựa trên `maxCharsPerByte()` hoặc dùng vòng lặp xử lý overflow.

## 8. Đọc file lớn bằng `InputStreamReader` và decoder nghiêm ngặt

Không cần nạp toàn bộ file vào `byte[]` mới có thể dùng `REPORT`. Constructor `InputStreamReader(InputStream, CharsetDecoder)` nhận decoder đã cấu hình, nên có thể đọc tuần tự bằng buffer.

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("import.txt");

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var reader = new BufferedReader(
        new InputStreamReader(Files.newInputStream(file), decoder))) {

    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
} catch (java.nio.charset.MalformedInputException ex) {
    System.err.println("File có byte UTF-8 không hợp lệ: " + ex);
}
```

Ví dụ giả định ứng dụng có phương thức `process(String)`. Khi decoder gặp byte không hợp lệ, thao tác đọc ném exception thay vì tự thay bằng ký tự replacement. `BufferedReader` có thể đã trả về các dòng hợp lệ trước khi gặp lỗi; vì vậy, không nên ghi kết quả cuối cùng vào hệ thống đích trước khi toàn bộ file được xác thực nếu nghiệp vụ yêu cầu tính nguyên tử.

### 8.1. Ghi kết quả vào file tạm trước khi commit

Một quy trình import an toàn thường:

1. Đọc và giải mã bằng decoder `REPORT`.
2. Ghi kết quả vào file tạm hoặc transaction chưa commit.
3. Nếu toàn bộ input hợp lệ, flush và đóng tài nguyên.
4. Kiểm tra kết quả.
5. Thực hiện move/commit sang đích chính.
6. Nếu gặp lỗi decode, hủy file tạm hoặc rollback transaction, giữ file nguồn để điều tra.

`REPORT` bảo vệ ranh giới decode; nó không tự rollback những side effect mà ứng dụng đã thực hiện trước khi lỗi xuất hiện.

## 9. `REPORT` không chứng minh charset nguồn đã đúng

Đây là giới hạn quan trọng. Nếu toàn bộ byte hợp lệ theo UTF-8, decoder `REPORT` sẽ chấp nhận chúng. Nhưng điều đó không chứng minh bên tạo file thật sự định dùng UTF-8.

Ví dụ, một file chỉ chứa ASCII hợp lệ trong UTF-8 và nhiều charset khác. Decoder không thể suy ra ý định của người tạo file chỉ từ byte.

Một số chuỗi byte legacy có thể tình cờ cũng hợp lệ UTF-8 nhưng cho nội dung khác với cách giải mã theo charset nguồn. Vì vậy:

- `REPORT` kiểm tra byte có hợp lệ theo charset đã chọn hay không.
- Hợp đồng file hoặc metadata xác định charset nguồn cần dùng.
- Kiểm tra nghiệp vụ xác nhận nội dung giải mã có đúng ý nghĩa hay không.

Không dùng `REPORT` như công cụ tự phát hiện charset. Nó là chính sách phát hiện lỗi sau khi đã chọn charset.

## 10. `CharsetEncoder` cũng cần chính sách nghiêm ngặt

Khi mã hóa `String` thành byte, lỗi có thể xuất hiện nếu chuỗi có surrogate không hợp lệ hoặc charset đích không thể biểu diễn một ký tự.

Ví dụ, ASCII không thể biểu diễn chữ tiếng Việt. Dùng encoder với `REPORT`:

```java
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

var encoded = encoder.encode(CharBuffer.wrap("Tiếng Việt"));

byte[] bytes = new byte[encoded.remaining()];
encoded.get(bytes);
```

Đoạn code sẽ ném `UnmappableCharacterException` khi encoder gặp ký tự không thể biểu diễn bằng ASCII. Với UTF-8, mọi Unicode scalar value hợp lệ đều có thể biểu diễn; tuy nhiên, một `String` Java vẫn có thể chứa unpaired surrogate và encoder UTF-8 nghiêm ngặt sẽ báo malformed input.

## 11. Khi nào dùng `REPORT`, `REPLACE` hoặc `IGNORE`?

| Tình huống | Chính sách phù hợp | Lý do |
| --- | --- | --- |
| Import dữ liệu khách hàng, giao dịch hoặc định danh | `REPORT` | Không chấp nhận mất hoặc thay đổi byte âm thầm |
| Đọc cấu hình hoặc dữ liệu có chữ ký | `REPORT` | Cần biết dữ liệu đầu vào có đúng hợp đồng |
| Xem log hỏng để điều tra | Có thể `REPLACE` | Cần hiển thị phần còn đọc được, đồng thời ghi nhận dữ liệu lỗi |
| Bộ lọc văn bản có chính sách bỏ ký tự cụ thể | Có thể `IGNORE` | Chỉ khi định dạng cho phép bỏ qua |
| Chuyển file legacy sang UTF-8 | Thường `REPORT` | Tránh tạo file mới từ dữ liệu đã bị thay thế hoặc bỏ mất |

Không có chính sách nào phù hợp cho mọi ứng dụng. Hãy chọn theo hậu quả nghiệp vụ khi mất thông tin. Với dữ liệu quan trọng, bắt đầu bằng `REPORT` và chỉ chuyển sang `REPLACE` hoặc `IGNORE` khi yêu cầu sản phẩm đã quy định cách xử lý rõ ràng.

## 12. Kiểm thử decoder nghiêm ngặt

Một bộ test nên có cả dữ liệu hợp lệ, lỗi malformed và trường hợp kết thúc input giữa chuỗi nhiều byte.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8DecoderTest {
    static String decodeUtf8Strict(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    static void expectInvalid(byte[] bytes) {
        try {
            decodeUtf8Strict(bytes);
            throw new AssertionError("Expected malformed UTF-8");
        } catch (java.nio.charset.MalformedInputException expected) {
            // Đây là kết quả mong đợi.
        } catch (CharacterCodingException other) {
            throw new AssertionError("Unexpected coding error", other);
        }
    }

    public static void main(String[] args) throws Exception {
        String valid = decodeUtf8Strict(new byte[] {
                0x43, (byte) 0xC3, (byte) 0xA0
        });
        if (!"Cà".equals(valid)) {
            throw new AssertionError(valid);
        }

        expectInvalid(new byte[] { (byte) 0xC3, 0x28 });
        expectInvalid(new byte[] { (byte) 0xE2, (byte) 0x82 });
        expectInvalid(new byte[] { (byte) 0x80 });
        expectInvalid(new byte[] {
                (byte) 0xC0, (byte) 0xAF
        });
        System.out.println("Strict UTF-8 tests passed");
    }
}
```

Các trường hợp cần có trong test suite:

- UTF-8 ASCII hợp lệ.
- Tiếng Việt có dấu.
- Emoji và ký tự ngoài BMP.
- Byte tiếp nối sai.
- Byte mở đầu bị cắt cụt ở cuối input.
- Byte tiếp nối đứng riêng.
- Overlong encoding và surrogate encoding.
- BOM UTF-8 nếu định dạng cho phép.

Một UTF-8 BOM `EF BB BF` là chuỗi byte hợp lệ, giải mã thành ký tự `U+FEFF` ở đầu văn bản. `REPORT` không tự loại BOM; nếu định dạng yêu cầu bỏ BOM, hãy xử lý riêng sau khi decode.

## 13. Bài tập tự kiểm tra

**Bài 1.** Khi UTF-8 decoder gặp byte `C3 28`, điều gì xảy ra nếu đặt `onMalformedInput(REPORT)`?

*Đáp án:* Decoder báo malformed input. Nó không tự thay byte sai bằng `U+FFFD` và không tiếp tục như thể dữ liệu hợp lệ.

**Bài 2.** Vì sao `new String(bytes, StandardCharsets.UTF_8)` có thể che giấu lỗi byte?

*Đáp án:* Constructor tiện lợi thay chuỗi byte không hợp lệ bằng replacement string của charset. Muốn từ chối dữ liệu lỗi, dùng `CharsetDecoder` với `REPORT`.

**Bài 3.** `REPORT` có chứng minh file thực sự được tạo bằng UTF-8 không?

*Đáp án:* Không. Nó chỉ chứng minh byte hợp lệ theo UTF-8. Charset nguồn phải được xác định từ hợp đồng hoặc metadata của dữ liệu.

**Bài 4.** Khi giải mã theo buffer, vì sao byte mở đầu nằm ở cuối buffer chưa chắc là lỗi?

*Đáp án:* Byte tiếp nối có thể nằm trong buffer kế tiếp. Chỉ kết luận chuỗi bị cắt cụt khi decoder được báo `endOfInput=true` và không còn byte nào nữa.

**Bài 5.** Khi decoder streaming phát hiện lỗi sau khi đã xử lý nhiều dòng hợp lệ, ứng dụng nên làm gì nếu import phải nguyên tử?

*Đáp án:* Ghi kết quả vào file tạm hoặc transaction chưa commit. Chỉ commit khi toàn bộ input giải mã và kiểm tra thành công; nếu lỗi, rollback và giữ file nguồn.

## 14. Ghi nhớ

`CharsetDecoder` giúp kiểm soát cách Java xử lý byte không hợp lệ. Với `CodingErrorAction.REPORT`, decoder báo malformed input hoặc unmappable input thay vì thay thế hay bỏ qua âm thầm. `REPLACE` và `IGNORE` chỉ nên dùng khi chính sách dữ liệu cho phép mất thông tin.

Hãy dùng decoder `REPORT` ở ranh giới nhận dữ liệu quan trọng, giữ lại byte nguồn khi cần điều tra, xử lý `MalformedInputException` và kiểm soát side effect khi đọc theo luồng. Tuy nhiên, `REPORT` chỉ xác nhận byte hợp lệ theo charset đã chọn; nó không tự phát hiện charset nguồn. Hợp đồng dữ liệu vẫn là căn cứ để chọn UTF-8 hoặc charset legacy chính xác.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 27 — CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Oracle Java SE 27 — CodingErrorAction](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CodingErrorAction.html).
- [Oracle Java SE 27 — CoderResult](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CoderResult.html).
- [Oracle Java SE 27 — CharsetEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetEncoder.html).
- [Oracle Java SE 27 — String constructors and getBytes](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html).
- [Unicode — The Unicode Standard, UTF-8](https://www.unicode.org/versions/latest/core-spec/chapter-3/).
