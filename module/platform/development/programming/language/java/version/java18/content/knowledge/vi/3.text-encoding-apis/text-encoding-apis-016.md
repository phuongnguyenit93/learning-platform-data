# CharsetEncoder: xử lý ký tự không biểu diễn được và surrogate không hợp lệ

## 1. CharsetEncoder giải quyết bước mã hóa ký tự thành byte

Trong Java, `String`, `CharBuffer` và `Reader` làm việc với ký tự UTF-16; file, socket và `OutputStream` thường nhận byte. Khi cần ghi văn bản theo một charset cụ thể, ứng dụng phải mã hóa chuỗi ký tự thành byte.

`java.nio.charset.CharsetEncoder` là bộ mã hóa cho một charset xác định. Nó cho phép ứng dụng kiểm soát cách xử lý hai nhóm lỗi:

- **Malformed input:** chuỗi đơn vị mã UTF-16 không hợp lệ, thường gặp nhất là surrogate đứng lẻ.
- **Unmappable character:** chuỗi ký tự UTF-16 hợp lệ nhưng charset đích không có cách biểu diễn tương ứng.

```text
String / CharBuffer
       |
       | CharsetEncoder của UTF-8, US-ASCII, ...
       v
     ByteBuffer
       |
       v
 File / OutputStream / network
```

Ví dụ, UTF-8 biểu diễn được mọi Unicode scalar value hợp lệ, nhưng vẫn không thể mã hóa một surrogate đứng lẻ vì đó không phải chuỗi UTF-16 hợp lệ. Ngược lại, US-ASCII không thể biểu diễn ký tự `€` dù ký tự đó hoàn toàn hợp lệ trong Unicode.

`CharsetEncoder` là API nền tảng từ Java 1.4 và vẫn được hỗ trợ trên JDK hiện đại. Trong bối cảnh Java 18, cần hiểu thêm rằng JEP 400 đặt UTF-8 làm default charset thông thường; điều đó không khiến mọi encoder tự chuyển sang UTF-8. Encoder luôn gắn với charset được dùng để tạo nó.

## 2. Tạo encoder từ Charset

Thông thường, tạo encoder bằng `Charset.newEncoder()`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.charset.CharsetEncoder;

CharsetEncoder utf8Encoder = StandardCharsets.UTF_8.newEncoder();
CharsetEncoder asciiEncoder = StandardCharsets.US_ASCII.newEncoder();
```

Một số charset thường gặp:

| Charset | Có thể biểu diễn | Ví dụ không biểu diễn được |
| --- | --- | --- |
| UTF-8 | Mọi Unicode scalar value hợp lệ | Surrogate UTF-16 đứng lẻ là malformed input |
| US-ASCII | Ký tự ASCII | `é`, `€`, tiếng Việt |
| ISO-8859-1 | Các ký tự Latin-1 | `€`, emoji, phần lớn chữ tiếng Việt |
| UTF-16 | Unicode scalar value hợp lệ | Surrogate đứng lẻ là malformed input |

Nên chỉ rõ charset khi định dạng dữ liệu hoặc giao thức đã quy định. Ví dụ:

```java
CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder();
```

Nếu thật sự muốn dùng default charset của JVM, có thể tạo encoder từ `Charset.defaultCharset()`:

```java
import java.nio.charset.Charset;

CharsetEncoder encoder = Charset.defaultCharset().newEncoder();
```

Từ Java 18, default charset là UTF-8 trong cấu hình thông thường theo JEP 400. Tuy nhiên, default charset có thể bị cấu hình theo chế độ tương thích được JDK hỗ trợ. Vì vậy, với dữ liệu trao đổi, file cấu hình hoặc giao thức cần encoding ổn định, hãy dùng `StandardCharsets.UTF_8` hoặc charset được đặc tả.

## 3. Hai loại lỗi mã hóa cần phân biệt

`CharsetEncoder` phân biệt tính hợp lệ của chuỗi UTF-16 với khả năng biểu diễn của charset đích.

### 3.1. Malformed input: surrogate không tạo thành cặp hợp lệ

Java biểu diễn `String` bằng các đơn vị mã UTF-16. Ký tự nằm ngoài Basic Multilingual Plane được biểu diễn bằng cặp:

- High surrogate nằm trong khoảng `U+D800` đến `U+DBFF`.
- Low surrogate nằm trong khoảng `U+DC00` đến `U+DFFF`.

Một high surrogate phải đứng ngay trước low surrogate tương ứng. Một low surrogate không có high surrogate đứng trước cũng không hợp lệ.

Ví dụ tạo chuỗi có high surrogate đứng lẻ:

```java
String malformed = new String(new char[] {
        'A',
        (char) 0xD800,
        'B'
});
```

Đây là chuỗi Java có thể tồn tại trong bộ nhớ, nhưng không phải chuỗi UTF-16 hợp lệ để mã hóa như một dãy Unicode scalar value. Khi encoder dùng `CodingErrorAction.REPORT`, thao tác mã hóa báo malformed input.

UTF-8 không thể sửa vấn đề này chỉ vì UTF-8 biểu diễn được mọi ký tự Unicode hợp lệ. Surrogate đứng lẻ không phải Unicode scalar value.

### 3.2. Unmappable character: ký tự hợp lệ nhưng charset không hỗ trợ

Ví dụ `€` là ký tự Unicode hợp lệ, nhưng US-ASCII không có byte biểu diễn ký tự này:

```java
String text = "Price: 10 €";
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder();
```

Nếu encoder báo lỗi, đây là unmappable character, không phải malformed input.

Một ví dụ khác là tiếng Việt có dấu khi mã hóa bằng US-ASCII hoặc ISO-8859-1. Dữ liệu vẫn là Unicode hợp lệ; charset đích quá hạn chế để biểu diễn nó.

| Đầu vào | Charset đích | Loại tình huống |
| --- | --- | --- |
| High surrogate đứng lẻ | UTF-8 | Malformed input |
| Low surrogate đứng lẻ | UTF-8 | Malformed input |
| Cặp surrogate hợp lệ biểu diễn `🌍` | UTF-8 | Hợp lệ |
| `€` | US-ASCII | Unmappable character |
| `Tiếng Việt` | US-ASCII | Unmappable character ở các ký tự ngoài ASCII |

## 4. Chính sách lỗi CodingErrorAction

`CharsetEncoder` có hai chính sách độc lập:

- `onMalformedInput(...)`: áp dụng khi chuỗi UTF-16 đầu vào không hợp lệ.
- `onUnmappableCharacter(...)`: áp dụng khi ký tự hợp lệ không biểu diễn được trong charset đích.

Cả hai nhận một trong ba giá trị `CodingErrorAction`:

| Hành động | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| `REPORT` | Báo lỗi cho caller | Dữ liệu cần chính xác, không chấp nhận mất ký tự |
| `REPLACE` | Ghi byte thay thế cho phần lỗi | Chấp nhận đầu ra gần đúng và có quy ước thay thế |
| `IGNORE` | Bỏ qua phần đầu vào lỗi | Chỉ dùng khi nghiệp vụ cho phép mất dữ liệu |

**Mặc định:** Cả malformed input và unmappable character đều dùng `REPORT` khi tạo encoder mới.

Cấu hình tường minh giúp người đọc hiểu chính sách của ứng dụng:

```java
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

Không nhầm hành động của encoder với decoder. Encoder thay thế bằng **byte sequence**; decoder thay thế bằng **chuỗi ký tự**. Hai phía có cùng tên `CodingErrorAction`, nhưng kiểu dữ liệu thay thế khác nhau.

## 5. REPORT: từ chối dữ liệu không thể mã hóa chính xác

Khi dùng `REPORT`, encoder không tự thay hoặc bỏ ký tự lỗi. Với overload tiện ích `encode(CharBuffer)`, lỗi được ném dưới dạng `CharacterCodingException` hoặc lớp con cụ thể.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    ByteBuffer bytes = encoder.encode(CharBuffer.wrap("Price: 10 €"));
    System.out.println("Encoded bytes: " + bytes.remaining());
} catch (CharacterCodingException e) {
    System.err.println("Không thể mã hóa nội dung: " + e);
}
```

Trong ví dụ, `€` không thể biểu diễn bằng US-ASCII nên `encode` ném `UnmappableCharacterException`, là lớp con của `CharacterCodingException`.

Với chuỗi chứa surrogate đứng lẻ, lỗi là `MalformedInputException`. Việc phân biệt hai loại ngoại lệ giúp ứng dụng báo nguyên nhân đúng cho dữ liệu nguồn hoặc người dùng.

### Khi nào nên dùng REPORT?

- Ghi dữ liệu cần bảo toàn chính xác, chẳng hạn dữ liệu tài chính hoặc định danh.
- Tạo file theo một đặc tả encoding nghiêm ngặt.
- Kiểm tra dữ liệu nhập trước khi gửi qua giao thức.
- Phát hiện chuỗi UTF-16 lỗi do tích hợp hoặc xử lý chuỗi không đúng.
- Tránh âm thầm thay ký tự bằng `?` hoặc bỏ ký tự.

## 6. REPLACE: chủ động chọn byte thay thế

Khi chọn `REPLACE`, encoder ghi replacement byte sequence cho phần malformed hoặc unmappable. Giá trị thay thế mặc định thường là byte `?`, nhưng không nên giả định mọi charset đều có cùng giá trị mặc định.

Có thể cấu hình byte thay thế bằng `replaceWith(byte[])`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith(new byte[] { (byte) '?' });

ByteBuffer encoded = encoder.encode(CharBuffer.wrap("Giá: 10 €"));
byte[] bytes = new byte[encoded.remaining()];
encoded.get(bytes);

System.out.println(new String(bytes, StandardCharsets.US_ASCII));
// Giá trị không biểu diễn được được thay bằng dấu ?.
```

`replaceWith` yêu cầu replacement:

- Không được `null`.
- Phải có ít nhất một byte.
- Không dài hơn `maxBytesPerChar()`.
- Phải là chuỗi byte hợp lệ theo chính charset của encoder.

Ví dụ, byte `?` hợp lệ trong US-ASCII. Một chuỗi byte tùy ý không hợp lệ cho charset không thể được dùng làm replacement.

`replaceWith` chỉ thay giá trị byte thay thế; nó không tự chuyển chính sách từ `REPORT` sang `REPLACE`. Muốn thay thế, phải gọi `onMalformedInput(REPLACE)` và/hoặc `onUnmappableCharacter(REPLACE)`.

## 7. IGNORE: bỏ qua phần đầu vào lỗi

`IGNORE` yêu cầu encoder không tạo byte cho phần malformed hoặc unmappable:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.IGNORE)
        .onUnmappableCharacter(CodingErrorAction.IGNORE);

ByteBuffer encoded = encoder.encode(
        CharBuffer.wrap("Cafe\u0301 - Giá 10 €"));
```

Các phần không thể mã hóa sẽ bị bỏ khỏi đầu ra. Đây là mất dữ liệu có chủ ý. Nếu dữ liệu được dùng để ký, đối chiếu, lưu trữ hoặc truyền cho hệ thống khác, `IGNORE` có thể làm thay đổi ý nghĩa và khiến hai bên không còn cùng nội dung.

Chỉ dùng `IGNORE` khi đặc tả nghiệp vụ cho phép loại bỏ những ký tự đó. Trong nhiều hệ thống, `REPORT` và xử lý lỗi ở tầng ứng dụng là lựa chọn dễ kiểm soát hơn.

## 8. encode(CharBuffer): cách mã hóa trọn một vùng dữ liệu

`CharsetEncoder.encode(CharBuffer)` là overload tiện ích cho một lần mã hóa hoàn chỉnh:

1. Reset encoder.
2. Mã hóa phần còn lại của `CharBuffer`.
3. Báo kết thúc đầu vào.
4. Flush encoder.
5. Trả về `ByteBuffer` mới chứa byte đã mã hóa.

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;

String text = "Xin chào, Tiếng Việt 🌍";

try {
    ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder()
            .encode(CharBuffer.wrap(text));

    byte[] bytes = new byte[encoded.remaining()];
    encoded.get(bytes);
} catch (CharacterCodingException e) {
    throw new IllegalArgumentException("Chuỗi không hợp lệ", e);
}
```

Với UTF-8 và chuỗi Unicode hợp lệ, ví dụ mã hóa thành công. Overload tiện ích này dùng chính sách lỗi hiện tại của encoder; encoder mới mặc định `REPORT`.

Kết quả `ByteBuffer` có position bằng 0 và limit ở cuối dữ liệu. Vì vậy, `remaining()` cho biết số byte có thể đọc. Sau khi lấy byte bằng `get`, position của buffer tiến lên.

### Giới hạn của overload tiện ích

- Mã hóa toàn bộ phần còn lại của một buffer đầu vào.
- Tạo một `ByteBuffer` mới, nên cần bộ nhớ cho toàn bộ kết quả.
- Reset encoder trước khi bắt đầu; không gọi khi một encoding operation khác đang diễn ra.
- Nếu dùng `REPORT`, lỗi được ném dưới dạng `CharacterCodingException`.
- Phù hợp với nội dung vừa phải; xử lý dữ liệu lớn nên cân nhắc API streaming.

## 9. canEncode: kiểm tra trước khi mã hóa

Có thể dùng `canEncode` để hỏi encoder có thể biểu diễn một ký tự hoặc một chuỗi hay không:

```java
import java.nio.charset.StandardCharsets;

var ascii = StandardCharsets.US_ASCII.newEncoder();
var utf8 = StandardCharsets.UTF_8.newEncoder();

System.out.println(ascii.canEncode("Hello")); // true
System.out.println(ascii.canEncode("€"));     // false
System.out.println(utf8.canEncode("€"));      // true
System.out.println(utf8.canEncode("🌍"));     // true
```

`canEncode(CharSequence)` hữu ích hơn `canEncode(char)` khi kiểm tra Unicode vì một ký tự ngoài BMP cần cả cặp surrogate. `canEncode(char)` trả về `false` nếu tham số là surrogate; một `char` đơn lẻ không đủ ngữ cảnh để xác định cặp hợp lệ.

Ví dụ:

```java
String validPair = "🌍";
String unpaired = new String(new char[] { (char) 0xD800 });

var encoder = StandardCharsets.UTF_8.newEncoder();

System.out.println(encoder.canEncode(validPair)); // true
System.out.println(encoder.canEncode(unpaired));  // false
```

`canEncode` chỉ trả lời có/không; nếu trả `false`, hãy thực hiện một lần mã hóa với `REPORT` để nhận loại lỗi cụ thể. Phương thức này có thể làm thay đổi trạng thái encoder, vì vậy không gọi nó trong khi encoder đang thực hiện một encoding operation. Cũng không chia sẻ encoder đang dùng giữa nhiều luồng.

## 10. Malformed surrogate có thể xuất hiện trong String như thế nào?

Một `String` Java không tự bảo đảm mọi đơn vị mã UTF-16 tạo thành Unicode scalar value hợp lệ. Chuỗi lỗi có thể đến từ:

- Tạo `String` từ `char[]` có surrogate đứng lẻ.
- Cắt chuỗi ở giữa cặp surrogate bằng index UTF-16.
- Ghép dữ liệu từ nhiều nguồn ở ranh giới surrogate.
- Đọc hoặc biến đổi dữ liệu từ thư viện không bảo toàn cặp surrogate.
- Tự thao tác trên `char` mà không xét quy tắc cặp surrogate.

Ví dụ cắt chuỗi có emoji ở giữa cặp:

```java
String original = "A🌍B";

// Một phần tử char có thể là high surrogate mà thiếu low surrogate.
String broken = original.substring(0, 2);
```

`String.substring` dùng chỉ số theo đơn vị `char` UTF-16, không theo code point. Nếu cắt đúng sau high surrogate, `broken` chứa chuỗi UTF-16 không hoàn chỉnh. UTF-8 encoder ở chế độ `REPORT` sẽ báo malformed input.

Nếu cần thao tác theo code point, dùng các API như `codePointAt`, `offsetByCodePoints` và `codePoints()` thay vì giả định một code point luôn bằng một `char`.

## 11. Quy trình encode nhiều lần bằng CoderResult

Khi xử lý dữ liệu theo khối hoặc cần kiểm soát buffer, dùng overload:

```java
CoderResult encode(CharBuffer input, ByteBuffer output, boolean endOfInput)
```

Phương thức mã hóa nhiều ký tự nhất có thể rồi trả về `CoderResult`:

| Kết quả | Ý nghĩa | Việc caller cần làm |
| --- | --- | --- |
| `UNDERFLOW` | Đã xử lý hết phần đầu vào hiện có, hoặc cần thêm input khi `endOfInput=false` | Cấp input tiếp theo hoặc chuyển sang bước flush nếu đã kết thúc |
| `OVERFLOW` | Output buffer không còn đủ chỗ | Đọc/ghi hết byte đã tạo, clear hoặc cấp buffer lớn hơn rồi gọi lại |
| `isMalformed()` | Có chuỗi UTF-16 không hợp lệ khi action là REPORT | Từ chối hoặc xử lý phần lỗi |
| `isUnmappable()` | Có ký tự hợp lệ không biểu diễn được khi action là REPORT | Từ chối hoặc xử lý phần lỗi |

Với error result, `length()` cho biết số đơn vị `char` thuộc phần đầu vào lỗi. Có thể gọi `throwException()` để chuyển kết quả lỗi thành `MalformedInputException` hoặc `UnmappableCharacterException` (đều là `CharacterCodingException`).

Một encoding operation có thứ tự:

```text
reset()
   |
   v
encode(input, output, false)  -- có thể lặp
   |
   v
encode(input, output, true)   -- lần cuối, báo hết input
   |
   v
flush(output)                 -- hoàn tất encoder
```

Không gọi `flush()` trước lần `encode(..., true)` cuối cùng. Encoder có thể là charset có trạng thái và cần phát byte cuối cùng khi flush.

### 11.1. Ví dụ xử lý overflow với một CharBuffer hoàn chỉnh

Ví dụ dưới đây mã hóa UTF-8 bằng buffer đầu ra nhỏ, lặp khi gặp `OVERFLOW` và thu byte đã tạo:

```java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CoderResult;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static byte[] encodeUtf8(CharSequence text)
        throws CharacterCodingException {
    var encoder = StandardCharsets.UTF_8.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    CharBuffer input = CharBuffer.wrap(text);
    ByteBuffer output = ByteBuffer.allocate(8);
    ByteArrayOutputStream resultBytes = new ByteArrayOutputStream();

    CoderResult result = encoder.encode(input, output, true);

    while (true) {
        output.flip();
        while (output.hasRemaining()) {
            resultBytes.write(output.get());
        }
        output.clear();

        if (result.isError()) {
            result.throwException();
        }
        if (result.isUnderflow()) {
            break;
        }
        // OVERFLOW: output đã được drain; tiếp tục với input còn lại.
        result = encoder.encode(input, output, true);
    }

    while (true) {
        result = encoder.flush(output);

        output.flip();
        while (output.hasRemaining()) {
            resultBytes.write(output.get());
        }
        output.clear();

        if (result.isUnderflow()) {
            break;
        }
        if (result.isError()) {
            result.throwException();
        }
        // OVERFLOW: cấp chỗ trống rồi flush tiếp.
    }

    return resultBytes.toByteArray();
}
```

Buffer 8 byte đủ cho một phần đầu ra UTF-8 trong ví dụ; vòng lặp xử lý khi tổng nội dung dài hơn buffer. Với charset khác, chọn buffer phù hợp với `maxBytesPerChar()` và nhu cầu xử lý của ứng dụng.

`CoderResult.throwException()` chuyển lỗi được báo thành `CharacterCodingException`. Nếu action được đặt thành `REPLACE` hoặc `IGNORE`, encoder tự thực hiện hành động đó và thường trả `UNDERFLOW`/`OVERFLOW` thay vì trả error result cho phần đã xử lý.

## 12. endOfInput và cặp surrogate qua ranh giới buffer

Khi dữ liệu đến theo khối, một high surrogate có thể nằm ở cuối buffer hiện tại và low surrogate nằm ở buffer kế tiếp.

Nếu caller gọi `encode(input, output, false)`, encoder biết rằng có thể còn input tiếp theo. Một high surrogate ở cuối buffer có thể được giữ lại như phần chưa xử lý để chờ low surrogate ở khối tiếp theo.

Caller phải giữ lại các ký tự còn lại trong input buffer và ghép chúng với dữ liệu tiếp theo. Không bỏ phần `remaining()` chỉ vì lần encode hiện tại trả `UNDERFLOW`.

Ở lần cuối, phải gọi `encode(..., true)`. Nếu vẫn còn high surrogate không có low surrogate, encoder sẽ phân loại là malformed input khi action là `REPORT`.

Quy tắc này quan trọng khi tự viết bộ mã hóa streaming: ranh giới của `CharBuffer` không nhất thiết là ranh giới của code point. Với ứng dụng thông thường, `OutputStreamWriter` đã quản lý việc nhận ký tự theo từng lần `write`; chỉ tự điều khiển `CharsetEncoder` khi cần pipeline byte/char chuyên biệt.

## 13. flush, reset và trạng thái encoder

`CharsetEncoder` có trạng thái. Một chuỗi gọi phương thức không hợp lệ có thể ném `IllegalStateException`.

- `reset()` đưa encoder về trạng thái ban đầu để bắt đầu một encoding operation mới.
- `encode(..., false)` cho phép tiếp tục nhận thêm input.
- `encode(..., true)` báo rằng không còn input nào nữa.
- `flush()` hoàn tất operation và cho encoder cơ hội ghi các byte cuối cùng.
- Sau khi đã flush xong, muốn bắt đầu operation mới bằng overload streaming, gọi `reset()`.

Overload tiện ích `encode(CharBuffer)` tự thực hiện reset, encode với kết thúc input và flush. Không gọi overload tiện ích đó giữa một operation đang xử lý thủ công.

Một encoder cũng giữ cấu hình `onMalformedInput`, `onUnmappableCharacter` và replacement qua các operation; `reset()` chủ yếu reset trạng thái xử lý và trạng thái nội bộ theo charset, không phải cách để đổi charset.

## 14. averageBytesPerChar và maxBytesPerChar

Hai phương thức giúp ước lượng kích thước output:

- `averageBytesPerChar()` trả số byte trung bình ước lượng trên mỗi đơn vị ký tự đầu vào.
- `maxBytesPerChar()` trả số byte tối đa có thể tạo trên mỗi đơn vị ký tự đầu vào theo hợp đồng encoder, bao gồm các byte prefix/suffix không phụ thuộc nội dung nếu charset cần.

Có thể dùng các giá trị này để ước lượng buffer:

```java
var encoder = StandardCharsets.UTF_8.newEncoder();

float average = encoder.averageBytesPerChar();
float maximum = encoder.maxBytesPerChar();

System.out.println("Average: " + average);
System.out.println("Maximum: " + maximum);
```

Đây là giá trị theo encoder cụ thể, không nên tự giả định một số cố định cho mọi charset. Với dữ liệu lớn, streaming và xử lý `OVERFLOW` thường hữu ích hơn việc cấp một buffer khổng lồ theo worst case.

## 15. Kết hợp CharsetEncoder với OutputStreamWriter

Khi muốn ghi ký tự ra `OutputStream` nhưng cần chính sách encoding rõ ràng, có thể truyền `CharsetEncoder` vào `OutputStreamWriter`:

```java
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

OutputStream output = obtainOutputStream();

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(output, encoder)) {
    writer.write("Price: 10 €");
}
```

`OutputStreamWriter` dùng encoder đã cấu hình. Nếu nội dung không hợp lệ hoặc không biểu diễn được, thao tác ghi có thể ném `IOException` với lỗi chuyển mã ở nguyên nhân bên dưới. Đây là lựa chọn khi muốn API Writer nhưng vẫn cần từ chối mất dữ liệu.

Nếu dùng `new OutputStreamWriter(output, StandardCharsets.UTF_8)`, charset đã rõ ràng nhưng ứng dụng không trực tiếp cấu hình `CodingErrorAction` của encoder. Khi cần strict encoding, truyền encoder đã cấu hình.

## 16. So sánh với String.getBytes và PrintStream/PrintWriter

| API | Charset | Kiểm soát malformed/unmappable |
| --- | --- | --- |
| `String.getBytes(Charset)` | Charset truyền vào | Dùng cơ chế thay thế của API, không cho chọn REPORT |
| `CharsetEncoder.encode(CharBuffer)` | Charset của encoder | Chọn REPORT, REPLACE hoặc IGNORE riêng cho từng loại lỗi |
| `OutputStreamWriter(OutputStream, Charset)` | Charset truyền vào | Dùng encoder nội bộ của Writer |
| `OutputStreamWriter(OutputStream, CharsetEncoder)` | Encoder truyền vào | Có thể cấu hình chính sách encoder trước |
| `PrintStream`/`PrintWriter` | Charset theo constructor hoặc Writer bên dưới | Phương thức in tiện lợi thay thế ký tự không mã hóa được; không dùng để yêu cầu REPORT |

Khi dữ liệu có thể chứa ký tự không biểu diễn được và việc thay thế là không chấp nhận được, `CharsetEncoder` cung cấp khả năng kiểm soát rõ ràng hơn `String.getBytes(Charset)` hoặc các lớp in tiện lợi.

Không nhầm `CharsetEncoder` với `CharsetDecoder`: encoder đi từ ký tự sang byte; decoder đi từ byte sang ký tự. Nếu ứng dụng cần strict round-trip, cần xác định chính sách cho cả hai chiều.

## 17. Luồng sử dụng encoder an toàn

Một quy trình thực tế:

1. Xác định charset theo định dạng hoặc giao thức, ví dụ UTF-8.
2. Tạo encoder mới từ charset đó.
3. Chọn chính sách cho malformed input và unmappable character.
4. Nếu cần kiểm tra trước, gọi `canEncode(CharSequence)` khi encoder chưa có operation đang chạy.
5. Với dữ liệu vừa phải, dùng `encode(CharBuffer)` và xử lý `CharacterCodingException`.
6. Với dữ liệu lớn, dùng `encode(..., false/true)` và xử lý `CoderResult`, `OVERFLOW`, `UNDERFLOW`.
7. Kết thúc operation bằng `flush()`.
8. Không dùng cùng một encoder đồng thời từ nhiều luồng.

Một encoder không an toàn cho nhiều thread cùng thao tác. Tạo encoder riêng cho mỗi operation hoặc mỗi thread thay vì chia sẻ một instance đang mã hóa.

## 18. Kiểm thử các trường hợp quan trọng

Một bộ kiểm thử nên tách hai loại lỗi và ba chính sách:

| Dữ liệu | Charset | Action | Kết quả mong đợi |
| --- | --- | --- | --- |
| `"Hello"` | US-ASCII | REPORT | Thành công |
| `"€"` | US-ASCII | REPORT | `UnmappableCharacterException` |
| Surrogate đứng lẻ | UTF-8 | REPORT | `MalformedInputException` |
| `"🌍"` | UTF-8 | REPORT | Thành công |
| `"€"` | US-ASCII | REPLACE | Có byte thay thế |
| `"€"` | US-ASCII | IGNORE | Ký tự không tạo byte |

Ví dụ kiểm tra strict encoding:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    encoder.encode(CharBuffer.wrap("€"));
    throw new AssertionError("US-ASCII phải từ chối ký tự euro");
} catch (java.nio.charset.UnmappableCharacterException expected) {
    // Đúng: ký tự hợp lệ nhưng không có trong US-ASCII.
}
```

Nên bổ sung:

- High surrogate đứng lẻ ở cuối chuỗi.
- Low surrogate đứng lẻ ở đầu chuỗi.
- Cặp surrogate hợp lệ bị chia qua hai input buffer.
- Output buffer quá nhỏ để tạo `OVERFLOW`.
- `replaceWith` với byte hợp lệ và byte không hợp lệ cho charset.
- Gọi `flush` đúng thứ tự và `reset` trước operation mới.
- Kiểm tra byte đầu ra thực tế thay vì chỉ so sánh chuỗi hiển thị.

## 19. Những nhận định dễ nhầm

- **“UTF-8 biểu diễn mọi Unicode nên không thể có lỗi malformed.”** Sai. UTF-8 biểu diễn mọi Unicode scalar value hợp lệ, nhưng chuỗi Java có thể chứa surrogate UTF-16 đứng lẻ.
- **“Ký tự không có trong charset là malformed input.”** Sai. Nếu chuỗi UTF-16 hợp lệ nhưng charset không ánh xạ được, đó là unmappable character.
- **“Encoder mới tự thay ký tự lỗi bằng `?`.”** Sai. Mặc định cả hai loại lỗi là `REPORT`; replacement chỉ áp dụng khi chọn `REPLACE`.
- **“replaceWith tự bật chế độ REPLACE.”** Sai. Phải cấu hình `onMalformedInput` hoặc `onUnmappableCharacter` tương ứng.
- **“REPLACE luôn dùng byte `?`.”** Không bảo đảm. Giá trị mặc định tùy encoder; có thể thay bằng byte sequence hợp lệ qua `replaceWith`.
- **“`canEncode(char)` kiểm tra được một emoji.”** Sai. Một `char` đơn lẻ không thể đại diện cả cặp surrogate; dùng `canEncode(CharSequence)`.
- **“UNDERFLOW luôn có nghĩa là đã mã hóa xong toàn bộ dữ liệu.”** Chỉ khi không còn input bổ sung và `endOfInput=true`; với `false`, caller có thể cần cung cấp thêm dữ liệu.
- **“Có thể flush trước encode cuối cùng.”** Sai. Hãy encode lần cuối với `endOfInput=true`, sau đó mới flush.
- **“Một CharsetEncoder có thể dùng đồng thời từ nhiều thread.”** Sai. Instance không thread-safe.
- **“JEP 400 khiến mọi encoder mặc định là UTF-8.”** Sai. Encoder luôn gắn với Charset dùng để tạo nó; JEP 400 chỉ thay đổi default charset thông thường của JVM.

## 20. Tài liệu tham khảo chính thức

- [CharsetEncoder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html): vòng đời encode, `CoderResult`, error actions, replacement, `canEncode`, `averageBytesPerChar` và `maxBytesPerChar`.
- [CodingErrorAction — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CodingErrorAction.html): `REPORT`, `REPLACE`, `IGNORE`.
- [CoderResult — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CoderResult.html): `UNDERFLOW`, `OVERFLOW`, malformed/unmappable và `throwException()`.
- [Charset — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/Charset.html): tạo encoder qua `newEncoder()` và charset chuẩn.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset thông thường từ Java 18 và phạm vi tương thích.

