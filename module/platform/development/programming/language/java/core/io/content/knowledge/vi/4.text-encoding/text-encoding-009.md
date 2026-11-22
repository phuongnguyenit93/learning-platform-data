# CharsetEncoder, CharsetDecoder và CodingErrorAction trong Java

Khi Java làm việc với file, HTTP, socket hoặc các định dạng văn bản, hệ thống phải chuyển đổi giữa **ký tự Unicode** và **byte**. `CharsetEncoder` chuyển ký tự sang byte; `CharsetDecoder` chuyển byte về ký tự; `CodingErrorAction` quy định phải làm gì khi đầu vào không hợp lệ hoặc không biểu diễn được trong charset đích.

Đây là phần **mã hóa văn bản** thuộc Java Core I/O, tập trung vào `java.nio.charset` và cách kết hợp bộ mã hóa/giải mã với `ByteBuffer`, `CharBuffer`, `Reader` và `Writer`. Các ví dụ sử dụng Java 17+.

## 1. Ba thành phần giải quyết ba vấn đề khác nhau

```text
Java String / char[] / CharBuffer
        |
        | CharsetEncoder (ví dụ UTF-8)
        v
  ByteBuffer: các byte mã hóa
        |
        | file, mạng, thiết bị, bộ nhớ
        v
  ByteBuffer: các byte nhận được
        |
        | CharsetDecoder (cùng charset)
        v
Java String / char[] / CharBuffer

CodingErrorAction:
  REPORT   → báo lỗi mã hóa/giải mã
  REPLACE  → thay đoạn không hợp lệ bằng giá trị thay thế
  IGNORE   → bỏ đoạn không hợp lệ
```

Các API chính:

| Thành phần | Hướng chuyển đổi | Input → output | Khởi tạo thông dụng |
| --- | --- | --- | --- |
| `Charset` | Định nghĩa ánh xạ ký tự ↔ byte | Không phải một tiến trình độc lập | `StandardCharsets.UTF_8` |
| `CharsetEncoder` | Mã hóa | `CharBuffer` → `ByteBuffer` | `charset.newEncoder()` |
| `CharsetDecoder` | Giải mã | `ByteBuffer` → `CharBuffer` | `charset.newDecoder()` |
| `CodingErrorAction` | Chính sách khi lỗi | `REPORT`, `REPLACE`, `IGNORE` | `onMalformedInput(...)` / `onUnmappableCharacter(...)` |
| `CoderResult` | Trạng thái một lần xử lý tăng dần | `UNDERFLOW`, `OVERFLOW` hoặc kết quả lỗi | Kết quả `encode(..., ..., ...)` / `decode(..., ..., ...)` |

Một ví dụ đơn giản: chữ `é` là một code point Unicode và thường chiếm một đơn vị `char` Java, nhưng trong UTF-8 mã hóa thành **hai byte** `C3 A9`. Emoji `😀` chiếm hai đơn vị `char` Java (một cặp surrogate) và bốn byte UTF-8 `F0 9F 98 80`. Vì thế:

- `String.length()` đếm **UTF-16 code unit**, không đếm byte đầu ra.
- `CharBuffer` làm việc với các đơn vị `char`, không bảo đảm mỗi phần tử là một Unicode code point hoàn chỉnh.
- `ByteBuffer` làm việc với byte. Ranh giới một lần nhận/gửi mạng có thể cắt giữa dãy byte của cùng một ký tự.
- Thỏa thuận charset giữa bên ghi và bên đọc là điều kiện cần để diễn giải byte đúng. Charset không được suy ra đáng tin chỉ bằng cách nhìn một mảng byte bất kỳ.

## 2. Tạo coder từ Charset

```java
Charset charset = StandardCharsets.UTF_8;
CharsetEncoder encoder = charset.newEncoder();
CharsetDecoder decoder = charset.newDecoder();
```

Đây là mảnh mã; cần import `java.nio.charset.*`. Mỗi lần `newEncoder()`/`newDecoder()` tạo một đối tượng mã hóa/giải mã có **trạng thái** riêng. Với UTF-8, encoder đọc đơn vị UTF-16, kiểm tra cặp surrogate và tạo byte hợp lệ. Decoder đọc byte UTF-8, kiểm tra dãy byte và tạo `char` tương ứng.

Có hai kiểu dùng coder:

1. **Một lần, toàn bộ nội dung**: `encoder.encode(CharBuffer)` và `decoder.decode(ByteBuffer)`. Hai phương thức này thực hiện một phiên chuyển đổi hoàn chỉnh, bao gồm reset và flush nội bộ; rất thích hợp khi đã có đủ dữ liệu.
2. **Tăng dần, nhiều phần dữ liệu**: `encoder.encode(CharBuffer, ByteBuffer, boolean endOfInput)` và `decoder.decode(ByteBuffer, CharBuffer, boolean endOfInput)`, sau đó `flush(output)`. Thích hợp khi dữ liệu đến từng khối, bộ đệm đầu ra có dung lượng hữu hạn hoặc cần kiểm soát tiến trình chuyển đổi.

Không dùng lẫn hai cách trong **cùng một phiên coder đang xử lý**: phương thức tiện ích một lần reset và hoàn tất phiên chuyển đổi, nên gọi nó giữa quá trình tăng dần có thể dẫn đến `IllegalStateException` hoặc làm sai logic.

## 3. Malformed input khác unmappable character như thế nào?

Cả hai đều là lỗi chuyển đổi, nhưng nguyên nhân khác nhau.

### 3.1. Malformed input: đầu vào không hợp lệ với quy tắc mã hóa

- **Khi giải mã UTF-8**: byte `C3` cần có byte tiếp theo dạng continuation, nhưng chuỗi `C3 28` là không hợp lệ (byte `28` là dấu ngoặc mở, không phải continuation byte). Đây là lỗi **malformed**.
- **Khi mã hóa từ ký tự Java**: một `char` surrogate cao (`\uD800`–`\uDBFF`) không được theo sau bởi surrogate thấp hợp lệ sẽ tạo dãy UTF-16 lỗi; encoder có thể báo **malformed**.
- UTF-8 bị cắt dở ở cuối dữ liệu cũng là lỗi malformed **khi đã xác nhận không còn byte đến nữa**. Nếu có thể còn dữ liệu ở lần đọc kế, coder có thể giữ lại phần chưa đủ và trả `UNDERFLOW`.

### 3.2. Unmappable character: đầu vào hợp lệ nhưng charset đích không biểu diễn được

- Chuỗi Java `"café"` là Unicode hợp lệ, nhưng **US-ASCII** không có mã byte cho `é`; khi mã hóa US-ASCII, đây là lỗi **unmappable**.
- Khi giải mã, một số charset có thể chứa dãy byte được coi là hợp lệ về cấu trúc nhưng không có ký tự Unicode tương đương; decoder cũng có thể phát hiện **unmappable**. Không suy diễn rằng mọi byte ngoài ASCII được decoder US-ASCII phân loại giống nhau; cách phân loại cụ thể thuộc về codec.

Hai nhánh được cấu hình riêng: `onMalformedInput(action)` và `onUnmappableCharacter(action)`. Gọi một nhánh **không tự động** thay đổi nhánh kia.

### 3.3. Ngoại lệ tương ứng

Cả `MalformedInputException` và `UnmappableCharacterException` đều là con của `CharacterCodingException`; `CharacterCodingException` là con của `IOException`. Với cách gọi một lần `encode(CharBuffer)` / `decode(ByteBuffer)` và chính sách `REPORT`, lỗi thường xuất hiện dưới dạng những ngoại lệ này. Với cách gọi tăng dần, lỗi được báo trong **`CoderResult`**, trừ khi bên gọi dùng `throwException()` để chuyển thành ngoại lệ.

## 4. CodingErrorAction: REPORT, REPLACE và IGNORE

```java
encoder.onMalformedInput(CodingErrorAction.REPORT);
encoder.onUnmappableCharacter(CodingErrorAction.REPORT);

decoder.onMalformedInput(CodingErrorAction.REPLACE);
decoder.onUnmappableCharacter(CodingErrorAction.REPLACE);
```

Các dòng trên là mảnh mã, trong đó `encoder`/`decoder` đã được tạo bằng `Charset.newEncoder()` / `newDecoder()`.

| Hành động | Điều xảy ra khi gặp đầu vào lỗi | Lợi ích | Rủi ro |
| --- | --- | --- | --- |
| `REPORT` | Trả `CoderResult` lỗi hoặc ném `CharacterCodingException`, tùy API | Phát hiện lỗi, tránh mất dữ liệu âm thầm | Cần kiểm soát luồng lỗi |
| `REPLACE` | Bỏ đoạn lỗi và ghi chuỗi/byte thay thế | Có thể hiển thị tiếp dữ liệu hỏng | Thông tin gốc không còn nguyên vẹn |
| `IGNORE` | Bỏ hẳn đoạn lỗi và xử lý phần tiếp theo | Chỉ thích hợp khi được phép bỏ dữ liệu | Làm mất ký tự, có thể gây hiểu sai nội dung |

**Giá trị thay thế không giống nhau ở hai hướng**:

- Encoder thay ký tự lỗi bằng **byte[]**; US-ASCII thường dùng byte `3F` (ký tự `?`), nhưng giá trị thực tế tùy charset/encoder. Có thể gọi `encoder.replaceWith(byte[])` với chuỗi byte hợp lệ được codec chấp nhận.
- Decoder thay byte lỗi bằng **String**; giá trị mặc định thường là Unicode Replacement Character `U+FFFD` (ký hiệu `�`). Có thể gọi `decoder.replaceWith(String)` với chuỗi thay thế hợp lệ.

Không suy ra rằng encoder có thể đặt `U+FFFD` làm byte thay thế; replacement của encoder là **byte đã mã hóa**, còn replacement của decoder là **ký tự Unicode**. Chính sách thay thế và giá trị thay thế là hai cấu hình riêng.

**Mặc định của đối tượng coder mới** (`newEncoder()` / `newDecoder()`) là **`REPORT` cho cả malformed và unmappable**. Tuy nhiên, nhiều API tiện ích cấp cao lại có mặc định **thay thế**. Đừng lấy kết quả từ `new String(bytes, UTF_8)` hay `String.getBytes(UTF_8)` để kết luận rằng coder mới cũng tự `REPLACE`.

## 5. Ví dụ chạy được: so sánh ba chính sách lỗi

Lưu thành file `CodingErrorPolicies.java`, sử dụng JDK 17+:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class CodingErrorPolicies {
    public static void main(String[] args) {
        CodingErrorAction[] actions = {
                CodingErrorAction.REPORT,
                CodingErrorAction.REPLACE,
                CodingErrorAction.IGNORE
        };

        // "AéB" là Unicode hợp lệ, nhưng US-ASCII không mã hóa được 'é'.
        for (CodingErrorAction action : actions) {
            CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
                    .onMalformedInput(action)
                    .onUnmappableCharacter(action);
            try {
                ByteBuffer encoded = encoder.encode(
                        CharBuffer.wrap("A\u00E9B"));
                byte[] bytes = new byte[encoded.remaining()];
                encoded.get(bytes);
                System.out.println("encode " + action + ": "
                        + new String(bytes, StandardCharsets.US_ASCII));
            } catch (CharacterCodingException e) {
                System.out.println("encode " + action + ": "
                        + e.getClass().getSimpleName());
            }
        }

        // UTF-8 lỗi: C3 phải đi với continuation byte, nhưng 28 không hợp lệ.
        byte[] invalidUtf8 = {
                0x41, (byte) 0xC3, 0x28, 0x42
        };
        for (CodingErrorAction action : actions) {
            CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(action)
                    .onUnmappableCharacter(action);
            try {
                String decoded = decoder.decode(
                        ByteBuffer.wrap(invalidUtf8)).toString();
                // In rõ ký tự thay thế thay vì phụ thuộc font console.
                System.out.println("decode " + action + ": "
                        + decoded.replace("\uFFFD", "<U+FFFD>"));
            } catch (CharacterCodingException e) {
                System.out.println("decode " + action + ": "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac CodingErrorPolicies.java
java CodingErrorPolicies
```

Stdout đã kiểm chứng với JDK:

```text
encode REPORT: UnmappableCharacterException
encode REPLACE: A?B
encode IGNORE: AB
decode REPORT: MalformedInputException
decode REPLACE: A<U+FFFD>(B
decode IGNORE: A(B
```

Giải thích từng trường hợp:

- `"AéB"` gồm ba ký tự hiển thị; chữ `é` không thuộc US-ASCII. Với `REPORT` ta nhận `UnmappableCharacterException`; `REPLACE` biến nó thành `?`; `IGNORE` bỏ hẳn chữ `é`.
- Byte đầu vào cho decoder là `41 C3 28 42`. `41`/`42` lần lượt là `A`/`B` và `28` là `(`. Byte `C3` không tạo được dãy UTF-8 hợp lệ với byte ngay sau, nên `REPORT` báo `MalformedInputException`; `REPLACE` thay riêng đoạn lỗi và vẫn đọc được `(B`, còn `IGNORE` xóa đoạn lỗi.
- Demo tạo **một coder mới cho mỗi lần chuyển đổi**. Đây là cách an toàn khi thay đổi chính sách cho các đầu vào độc lập; không tái sử dụng coder có trạng thái dở dang.

## 6. Khác biệt giữa coder trực tiếp và API tiện ích

Các API trông giống nhau nhưng có **chính sách lỗi khác nhau**:

| API | Công dụng | Chính sách lỗi thường áp dụng |
| --- | --- | --- |
| `charset.newEncoder().encode(CharBuffer)` | Mã hóa một lần với coder mới | Mặc định `REPORT`, có thể ném `CharacterCodingException` |
| `charset.newDecoder().decode(ByteBuffer)` | Giải mã một lần với coder mới | Mặc định `REPORT`, có thể ném `CharacterCodingException` |
| `charset.encode(CharBuffer)` / `charset.decode(ByteBuffer)` | Hàm tiện ích trên `Charset` | Dùng chính sách `REPLACE` |
| `String.getBytes(charset)` | Mã hóa toàn bộ `String` thành byte | Có thể thay thế UTF-16 lỗi; không phù hợp nếu bắt buộc từ chối dữ liệu lỗi |
| `new String(byte[], charset)` | Giải mã toàn bộ byte thành `String` | Thay thế chuỗi byte lỗi; không phải trình kiểm chứng tính hợp lệ của UTF-8 |
| `new OutputStreamWriter(stream, charset)` | Ghi ký tự ra stream byte | Mặc định thay thế dữ liệu lỗi trong quá trình ghi |
| `new InputStreamReader(stream, charset)` | Đọc byte thành ký tự | Mặc định thay thế dữ liệu lỗi trong quá trình đọc |

Ví dụ, đoạn này **không phải xác thực UTF-8 nghiêm ngặt**:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

`bytes` là `byte[]` có sẵn; nếu byte UTF-8 không hợp lệ, Java có thể thay bằng `U+FFFD` rồi trả `String`. Khi yêu cầu từ chối dữ liệu sai định dạng, dùng:

```java
CharsetDecoder strict = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
String text = strict.decode(ByteBuffer.wrap(bytes)).toString();
```

Đây là mảnh mã; cần import `java.nio.*`, `java.nio.charset.*` và xử lý `CharacterCodingException`. Nó báo lỗi thay vì làm mất dấu vết lỗi đầu vào. Điều này đặc biệt hữu ích cho kiểm tra upload, định dạng cấu hình yêu cầu UTF-8 hợp lệ, hoặc giao thức không cho phép tự sửa ký tự.

## 7. Bộ đệm và CoderResult trong chuyển đổi tăng dần

Trường hợp đọc mạng/file theo từng khối, không thể mặc định một lần `read` kết thúc đúng ranh giới ký tự. API tăng dần:

```java
CoderResult result = decoder.decode(
        inputBytes, outputChars, endOfInput);
```

Ở đây `inputBytes` là `ByteBuffer`, `outputChars` là `CharBuffer` và `endOfInput` là `boolean`. Với encoder, hướng bộ đệm đảo lại:

```java
CoderResult result = encoder.encode(
        inputChars, outputBytes, endOfInput);
```

`CoderResult` có bốn nhóm trạng thái:

- **`UNDERFLOW`**: đã xử lý được mọi dữ liệu hiện có **hoặc** dữ liệu còn lại chưa đủ để tạo ký tự/byte tiếp theo. Khi vẫn còn nguồn, cần nhận thêm dữ liệu; không tự coi `UNDERFLOW` là EOF.
- **`OVERFLOW`**: buffer đầu ra không còn đủ chỗ. Cần đọc/ghi (drain) nội dung của buffer đầu ra, tạo thêm chỗ rồi gọi coder tiếp; **không** coi là lỗi codec.
- **`isMalformed()`**: chuỗi input sai cấu trúc theo charset. Chỉ trả nhóm này khi chính sách tương ứng là `REPORT`.
- **`isUnmappable()`**: input hợp lệ nhưng không thể biểu diễn. Chỉ trả nhóm này khi chính sách tương ứng là `REPORT`.

`result.length()` ở một `CoderResult` lỗi cho biết **số đơn vị đầu vào gây lỗi** (byte với decoder, `char` với encoder), không phải tổng byte đã đọc từ đầu luồng. `result.throwException()` chuyển trạng thái lỗi tương ứng thành `MalformedInputException`/`UnmappableCharacterException`. Không gọi `throwException()` một cách mù quáng với `UNDERFLOW` hoặc `OVERFLOW`.

### Quy trình coder một phiên

```text
reset() nếu tái sử dụng coder đã hoàn tất phiên trước
   |
   v
encode/decode(input, output, false)
   |                 |
   | UNDERFLOW       | OVERFLOW
   v                 v
thêm input          xả output, tiếp tục
   |
   | đến khi biết chắc không còn input
   v
encode/decode(input còn lại, output, true)
   |
   | xử lý OVERFLOW nếu có, cho tới UNDERFLOW
   v
flush(output)
   |
   | nếu OVERFLOW: xả output và gọi flush lần nữa
   v
phiên kết thúc; reset trước phiên mới
```

`endOfInput == true` có nghĩa **đây là byte/char cuối cùng trong toàn phiên chuyển đổi**, không phải “cuối buffer hiện tại”. Đặt cờ này quá sớm có thể biến ký tự đang chờ phần kế thành malformed hoặc vi phạm trạng thái coder. Nếu dữ liệu cuối thực sự còn dang dở, khi `endOfInput == true` codec phải áp dụng chính sách lỗi đã cấu hình.

### Buffer: flip, compact và clear

- `input.flip()` chuyển input từ **chế độ ghi dữ liệu mới vào buffer** sang **chế độ coder đọc**.
- Sau khi coder trả `UNDERFLOW` nhưng input vẫn còn byte/char của chuỗi dở, dùng `input.compact()` để giữ phần chưa tiêu thụ ở đầu buffer rồi **thêm dữ liệu mới** phía sau. `input.clear()` lúc này sẽ làm **mất** phần còn lại.
- Đối với output, khi có dữ liệu cần lấy/ghi xuống đích, gọi `output.flip()`, tiêu thụ hết `output.remaining()`, rồi `output.clear()` để nhận thêm kết quả. Nếu chỉ tiêu thụ một phần output, dùng `compact()` hoặc giữ phần còn lại.
- `position`/`limit` được coder dịch chuyển theo số đơn vị đã đọc/ghi; không dùng `array().length` thay cho `remaining()` để xác định nội dung hợp lệ.
- Nếu một đơn vị mã hóa hoặc trạng thái codec đòi hỏi nhiều chỗ hơn bộ đệm hiện tại, cần buffer lớn hơn hoặc chiến lược nạp/xả phù hợp. Đừng lặp lại `OVERFLOW` với output vẫn đầy mà không giải phóng dung lượng.

## 8. Ví dụ Java 17+ chạy được: UTF-8 chia giữa hai khối

Ký tự euro `€` (code point `U+20AC`) có UTF-8 là `E2 82 AC`. Giả sử mạng chỉ gửi byte đầu `E2` trong lần đầu, còn `82 AC` đến ở lần thứ hai. Decoder phải **giữ byte dở dang** giữa hai lần, và chỉ kết thúc khi đã biết hết dữ liệu.

Lưu thành `IncrementalUtf8Decoder.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class IncrementalUtf8Decoder {
    public static void main(String[] args) throws Exception {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.allocate(8);
        CharBuffer output = CharBuffer.allocate(8);

        // Khối 1: byte đầu tiên của ký tự €, chưa đủ để giải mã.
        input.put((byte) 0xE2);
        input.flip();
        CoderResult first = decoder.decode(input, output, false);
        System.out.println("first: " + first
                + ", remaining=" + input.remaining()
                + ", chars=" + output.position());

        // compact() giữ E2; thêm 82 AC để có đủ E2 82 AC.
        input.compact();
        input.put((byte) 0x82).put((byte) 0xAC);
        input.flip();

        // Bây giờ đã nhận được byte cuối cùng.
        CoderResult last = decoder.decode(input, output, true);
        CoderResult flushed = decoder.flush(output);
        output.flip();

        int codePoint = Character.codePointAt(output, 0);
        System.out.println("finish: " + last
                + ", flush=" + flushed
                + ", codepoint=U+"
                + Integer.toHexString(codePoint).toUpperCase(Locale.ROOT));
    }
}
```

Chạy:

```bash
javac IncrementalUtf8Decoder.java
java IncrementalUtf8Decoder
```

Stdout đã kiểm chứng với JDK:

```text
first: UNDERFLOW, remaining=1, chars=0
finish: UNDERFLOW, flush=UNDERFLOW, codepoint=U+20AC
```

Ở lần `decode(..., false)` đầu, `UNDERFLOW` và `remaining=1` nghĩa là byte `E2` **chưa bị tiêu thụ**; decoder cần thêm byte để xác định ký tự. `compact()` giữ nguyên byte này, sau đó chương trình thêm `82 AC`. Lần `decode(..., true)` thứ hai xử lý đầy đủ thành `U+20AC` và `flush` hoàn tất phiên. Demo dành cho hai khối cụ thể với buffer đủ chỗ; khi xử lý luồng dài, bạn cần vòng lặp xử lý `OVERFLOW`, lần đọc rỗng, EOF và lỗi I/O theo nguồn dữ liệu thực tế.

## 9. Chính sách lỗi trong trường hợp chuyển đổi tăng dần

Giả sử đã chọn `REPORT`:

```java
CoderResult result = decoder.decode(input, output, false);

if (result.isMalformed() || result.isUnmappable()) {
    int invalidUnitCount = result.length();
    // Ghi nhận offset và độ dài lỗi nếu ứng dụng cần.
    // Không tự tăng position mà không biết rõ cách xử lý dữ liệu.
    result.throwException();
}
```

Đây là mảnh mã; `input`/`output`/`decoder` phải được khởi tạo phù hợp và phương thức gọi xử lý `CharacterCodingException`. Khi coder phát hiện lỗi, `input.position()` chỉ tới đầu chuỗi byte lỗi theo hợp đồng thông thường của API; `result.length()` có thể giúp xác định đoạn cần báo, nhưng **đừng tự động bỏ qua** những byte đó nếu chính sách dữ liệu yêu cầu từ chối toàn bộ bản ghi.

Nếu ứng dụng thực sự cần bỏ qua lỗi và tiếp tục, tốt hơn chọn rõ `IGNORE` hoặc `REPLACE` và kiểm tra chính sách có phù hợp nghiệp vụ hay không. Cố gắng tự dịch `ByteBuffer.position` để “chữa lỗi” có thể khiến bỏ sót byte, lặp vô hạn hoặc biến đầu vào độc hại thành văn bản khác với ý định.

**Lưu ý tính nguyên tử:** Khi `REPORT` xảy ra sau một phần dữ liệu hợp lệ, output có thể đã chứa các ký tự/byte được tạo trước lỗi. Không coi phép chuyển đổi tăng dần là transaction tự rollback. Nếu hệ thống chỉ chấp nhận dữ liệu hợp lệ hoàn toàn, xác thực trước rồi mới commit kết quả hoặc giữ output ở vùng tạm.

## 10. Tùy biến giá trị thay thế

Ví dụ kiểm soát encoder US-ASCII:

```java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith(new byte[] { (byte) '!' });
ByteBuffer bytes = encoder.encode(CharBuffer.wrap("A\u00E9B"));
// Kết quả ASCII là "A!B".
```

Ví dụ kiểm soát decoder UTF-8:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("[?]");
CharBuffer chars = decoder.decode(ByteBuffer.wrap(
        new byte[] { 0x41, (byte) 0xC3, 0x28, 0x42 }));
// Với charset/giới hạn thay thế cho phép, kết quả sẽ là "A[?](B".
```

**Hai ví dụ trên là mảnh mã minh họa; không dùng nguyên văn ví dụ decoder thứ hai mà bỏ qua ràng buộc độ dài replacement:** `CharsetDecoder.replaceWith(String)` chỉ nhận chuỗi thay thế không rỗng có độ dài không vượt `maxCharsPerByte()`; với decoder UTF-8 của JDK thông thường, chuỗi `"[?]"` dài 3 **vượt giới hạn** và sẽ ném `IllegalArgumentException`. Một cấu hình **chạy được và hợp lệ** là `decoder.replaceWith("?")`, khi đó kết quả `"A?(B"`.

Vì vậy, khi thay thế decoder thực tế, viết:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .replaceWith("?");
```

Mảnh mã này cấu hình thay thế byte UTF-8 lỗi bằng ký tự `?`. Tương tự, `CharsetEncoder.replaceWith(byte[])` kiểm tra mảng byte không rỗng, độ dài/giá trị hợp lệ theo charset; không thể truyền tùy tiện chuỗi byte khác encoding.

## 11. Dùng cùng Reader và Writer ở ranh giới I/O

Có thể gắn coder được cấu hình vào các luồng Java:

```java
CharsetDecoder strictDecoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(inputStream, strictDecoder)) {
    // Đọc ký tự; khi nhận byte UTF-8 không hợp lệ có thể ném IOException.
}

CharsetEncoder strictEncoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(outputStream, strictEncoder)) {
    // Ghi ký tự; UTF-16 lỗi có thể gây IOException.
}
```

Đây là hai **mảnh mã riêng**: cần import `java.io.*`, `java.nio.charset.*`; `inputStream`, `outputStream` là các luồng đã mở và được code hiện tại sở hữu. `InputStreamReader`/`OutputStreamWriter` sẽ quản lý bộ đệm và sử dụng coder đã cấu hình. Đóng wrapper cũng đóng luồng phía dưới; nếu luồng do nơi khác sở hữu (chẳng hạn `System.out` hoặc socket được quản lý chung) thì phải có thỏa thuận về lifecycle.

Không chia sẻ **cùng một instance** `CharsetEncoder` hoặc `CharsetDecoder` cho nhiều luồng đồng thời: coder có trạng thái và API **không đảm bảo thread-safe**. Dùng mỗi tiến trình/chuyển đổi một coder riêng, hoặc đồng bộ nghiêm ngặt khi buộc phải dùng lại. `reset()` cho phép khởi tạo phiên mới khi phiên trước đã kết thúc/được hủy có kiểm soát; nó không thay cho cơ chế khóa.

## 12. Chọn chính sách theo yêu cầu nghiệp vụ

| Tình huống | Gợi ý | Vì sao |
| --- | --- | --- |
| Đọc dữ liệu giao thức yêu cầu UTF-8 hợp lệ | `CharsetDecoder` + `REPORT` | Không âm thầm biến dữ liệu sai thành dữ liệu khác |
| Xử lý tệp import cần ghi nhận dòng hỏng | `REPORT`, quản lý offset và báo lỗi | Giữ bằng chứng lỗi để người dùng sửa |
| Xem trước văn bản lỗi trong giao diện | Có thể dùng `REPLACE`, kèm thông báo dữ liệu đã được thay | Vẫn hiển thị được nội dung còn lại |
| Xuất văn bản tiếng Việt sang codec chỉ có ASCII | Ưu tiên UTF-8; nếu bắt buộc ASCII, dùng `REPORT` hoặc chính sách mất dữ liệu rõ ràng | Tránh mất dấu/tên người âm thầm |
| Làm sạch dữ liệu theo quy định cho phép loại bỏ ký tự lỗi | `IGNORE` chỉ khi đặc tả cho phép | Bỏ dữ liệu là quyết định nghiệp vụ, không phải khôi phục nguyên vẹn |
| Đọc các chunk từ mạng, kênh NIO | Coder tăng dần, giữ phần buffer dở, xử lý `UNDERFLOW`/`OVERFLOW` | Chunk không bảo đảm trùng ranh giới ký tự |

Không dùng `IGNORE` như một biện pháp “sửa an toàn” cho đầu vào không đáng tin. Ví dụ chuỗi định danh, chữ ký số, kiểm tra đường dẫn, quyền truy cập hoặc cú pháp giao thức có thể thay đổi ý nghĩa khi byte/char bị xóa. Với dữ liệu quan trọng, ưu tiên **từ chối đầu vào không hợp lệ** và báo rõ offset/lỗi; nếu dùng `REPLACE`, công khai rằng dữ liệu không còn nguyên bản.

## 13. Những giới hạn cần phân biệt

### Charset không tự sửa dữ liệu đã mã hóa sai

Nếu trước đó file bị ghi sai charset, `CharsetDecoder` không thể tự suy ra “đúng lẽ ra là” gì. Chẳng hạn giải mã byte UTF-8 bằng charset khác có thể cho ký tự **hợp lệ về mặt kỹ thuật nhưng sai nội dung** (*mojibake*), nên `REPORT` cũng có thể **không** phát hiện được. Việc giải mã đúng phụ thuộc metadata/protocol, không chỉ kiểm tra lỗi cú pháp byte.

### Charset không đồng nghĩa Unicode normalization

`"é"` có thể biểu diễn bằng một code point `U+00E9` hoặc hai code point `U+0065 U+0301`. Cả hai mã hóa UTF-8 hợp lệ, nhưng byte khác nhau. `CharsetEncoder` không tự chuẩn hóa NFC/NFD; nếu nghiệp vụ cần so sánh canonical, dùng `java.text.Normalizer` với yêu cầu rõ ràng trước/sau bước chuyển đổi. Không chuẩn hóa định danh nhạy cảm một cách tùy tiện.

### Byte Order Mark (BOM) và phát hiện charset

Một số định dạng có thể dùng BOM để báo thứ tự byte hoặc encoding. `CharsetDecoder` không phải thư viện tự phát hiện encoding từ nội dung bất kỳ; việc có/không xử lý BOM tùy charset và cách bạn chọn decoder. Đối với UTF-8, đừng mặc định mọi file đều có BOM hoặc sẽ được bỏ BOM theo cùng một cách. Định nghĩa chính sách BOM rõ khi đọc/ghi giao thức.

### Đếm kích thước và kết thúc luồng

`encoder.averageBytesPerChar()`, `maxBytesPerChar()`, `decoder.averageCharsPerByte()` và `maxCharsPerByte()` là thông tin ước lượng/giới hạn hữu ích cho cấp phát buffer; **không thay thế** kết quả chuyển đổi thực tế khi cần kích thước chính xác. Với trạng thái codec và `OVERFLOW`, vẫn phải xử lý đúng cơ chế buffer.

`flush()` trên coder **không phải** `OutputStream.flush()`: coder.flush ghi dữ liệu còn trong trạng thái mã hóa ra **buffer output do bạn cấp**, thường được gọi **sau lần encode/decode cuối với `endOfInput=true`**. Sau đó, ứng dụng vẫn phải lấy dữ liệu từ `ByteBuffer`/`CharBuffer` và ghi xuống nơi đích. Khi dùng `Reader`/`Writer`, tầng wrapper quản lý nhiều phần của quy trình này.

### Không coi coder là công cụ xác thực bảo mật toàn diện

`REPORT` chỉ xác thực tính hợp lệ **theo charset cụ thể**. Nó không kiểm tra JSON đúng schema, URL an toàn, Unicode confusable, ký tự điều khiển bị cấm, HTML escaping hoặc checksum. Sau bước mã hóa/giải mã vẫn cần kiểm tra theo ngữ pháp và yêu cầu an toàn của dữ liệu.

## 14. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `new String(bytes, UTF_8)` để xác thực UTF-8 | Byte sai có thể bị thay mà không báo | `UTF_8.newDecoder()` + `REPORT` |
| Nghĩ `newDecoder()` mặc định `REPLACE` | Ngoại lệ bất ngờ | Biết coder mới mặc định `REPORT` |
| Chỉ cấu hình `onMalformedInput` nhưng quên `onUnmappableCharacter` | Hai nhóm lỗi bị xử lý khác nhau | Chọn cả hai chính sách rõ ràng |
| Cho rằng malformed và unmappable là cùng một lỗi | Báo sai nguyên nhân | Phân biệt input sai cấu trúc với ký tự không biểu diễn được |
| Dùng `input.clear()` khi decoder trả `UNDERFLOW` với byte còn lại | Mất nửa ký tự UTF-8 | `compact()` trước khi nạp byte mới |
| Truyền `endOfInput=true` cho từng khối mạng | Xem byte chưa đủ là input bị cắt | Chỉ đặt `true` khi đã xác nhận EOF |
| Lặp lại `OVERFLOW` mà không xả output | Không thể tiến triển | `flip`, drain, `clear/compact` rồi tiếp tục |
| Quên `flush(output)` của coder ở cuối phiên | Có thể thiếu output của charset có trạng thái | Hoàn tất lần mã hóa/giải mã cuối rồi flush coder |
| Dùng một instance coder đồng thời ở nhiều thread | Trạng thái lỗi/race | Mỗi phiên/thread một coder hoặc đồng bộ |
| Chọn `IGNORE` để “khắc phục” dữ liệu quan trọng | Mất ký tự, thay đổi ý nghĩa | `REPORT` và xử lý lỗi theo đặc tả |
| Nhầm `replaceWith(byte[])` với `replaceWith(String)` | Sai hướng chuyển đổi hoặc exception | Encoder thay byte; decoder thay String, tuân thủ giới hạn |
| Cho rằng decoder bảo đảm nội dung đúng nghĩa | Mojibake vẫn có thể hợp lệ theo charset sai | Thống nhất charset ngoài giao thức và xác thực dữ liệu sau giải mã |

## 15. Câu hỏi tự kiểm tra

1. **Khác nhau về chiều dữ liệu?** `CharsetEncoder` nhận `char` để tạo byte, `CharsetDecoder` nhận byte để tạo `char`.
2. **Tại sao `"AéB"` mã hóa US-ASCII bằng `REPORT` thất bại?** `é` là Unicode hợp lệ nhưng không biểu diễn được trong US-ASCII: `UnmappableCharacterException`.
3. **Vì sao byte `C3 28` không giải mã UTF-8 chuẩn được?** `C3` khởi đầu chuỗi hai byte nhưng `28` không phải continuation byte: malformed.
4. **`REPORT` khác `REPLACE` và `IGNORE` ra sao?** Báo lỗi thay vì thay đoạn lỗi hoặc xóa đoạn lỗi.
5. **`newDecoder()` mặc định chính sách gì?** `REPORT`; đừng nhầm với `Charset.decode(...)` hoặc `new String(bytes, charset)` thường thay thế lỗi.
6. **`UNDERFLOW` có chắc là EOF không?** Không; có thể chỉ đang thiếu byte/char cho ký tự kế tiếp.
7. **Tại sao phải gọi `compact()` cho input có byte dở?** Để giữ byte chưa tiêu thụ và nối với byte của khối tiếp theo.
8. **`endOfInput=true` được đặt lúc nào?** Khi chắc chắn không còn input trong **phiên** chuyển đổi, không phải khi hết một chunk tạm thời.
9. **`flush(output)` thuộc bộ phận nào?** Thuộc `CharsetEncoder`/`CharsetDecoder`, xả trạng thái codec vào output buffer sau pha input cuối.
10. **Cần chống mất dữ liệu âm thầm khi đọc UTF-8 cần làm gì?** Tạo `UTF_8.newDecoder()`, cấu hình hai nhóm lỗi `REPORT`, xử lý `CharacterCodingException` và không commit nội dung khi thất bại.

## Tài liệu API Java 17

- [`CharsetEncoder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html).
- [`CharsetDecoder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [`CodingErrorAction` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CodingErrorAction.html).
- [`CoderResult` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CoderResult.html).
- [`Charset` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html).
- [`InputStreamReader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html).
- [`OutputStreamWriter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html).

**Ghi nhớ:** Coder thực hiện chuyển đổi theo một charset; `CodingErrorAction` quyết định có báo, thay hay bỏ dữ liệu lỗi; `CoderResult` hướng dẫn cách xử lý từng lần chuyển đổi tăng dần. Để xử lý văn bản đúng, cần thống nhất charset, chọn chính sách lỗi phù hợp và tôn trọng trạng thái/bộ đệm của coder.