# String.getBytes(Charset) và new String(byte[], Charset): định nghĩa rõ hai chiều chuyển đổi

## 1. Bài toán: văn bản đi qua ranh giới byte

Trong Java, `String` lưu văn bản dưới dạng chuỗi ký tự Unicode, còn `byte[]` lưu các byte không tự mang thông tin về cách diễn giải thành văn bản. Khi gửi dữ liệu qua HTTP, message queue, socket hoặc lưu file, chương trình phải thống nhất **charset** ở cả hai chiều:

```text
String trong Java
    │
    ├── text.getBytes(charset) ── mã hóa (encode) ──► byte[] trên đường truyền / đĩa
    │
    └── new String(bytes, charset) ◄── giải mã (decode) ── byte[] từ đường truyền / đĩa
```

Chủ đề thuộc nhóm **API văn bản** của module Java 18. Từ Java 18, JEP 400 đưa UTF-8 thành charset mặc định trong cấu hình JVM thông thường, nhưng hợp đồng dữ liệu giữa các hệ thống vẫn cần được mô tả rõ. Hai overload nhận `Charset` là cách trực tiếp để thể hiện hợp đồng đó trong mã nguồn, đồng thời vẫn hữu ích trên các phiên bản JDK hiện đại.

Sau bài này, bạn cần:

- Hiểu chính xác `String.getBytes(Charset)` và `new String(byte[], Charset)` xử lý gì và trả về gì.
- Chọn charset theo quy định của giao thức/định dạng; mã hóa và giải mã nhất quán ở hai đầu.
- Kiểm tra byte kết quả, nhận diện lỗi giải mã sai charset và dữ liệu không hợp lệ.
- Biết giới hạn của overload tiện lợi và chuyển sang `CharsetEncoder`/`CharsetDecoder` khi cần phát hiện lỗi nghiêm ngặt.

## 2. Hợp đồng của hai API

### 2.1. Chiều mã hóa: `String.getBytes(Charset)`

```java
import java.nio.charset.StandardCharsets;

String text = "Tiếng Việt";
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
```

- **Đầu vào:** `Charset` xác định cách chuyển nội dung `String` thành byte.
- **Đầu ra:** `byte[]` mới chứa các byte được mã hóa.
- **Tính quyết định:** cùng nội dung `String` và cùng charset, kết quả có cùng chuỗi byte, không dựa vào `Charset.defaultCharset()`.
- **Giới hạn quan trọng:** overload này **thay thế** đầu vào UTF-16 lỗi hoặc ký tự không biểu diễn được trong charset đích bằng chuỗi byte thay thế mặc định; nó không tự động ném lỗi trong các tình huống đó.

### 2.2. Chiều giải mã: `new String(byte[], Charset)`

```java
import java.nio.charset.StandardCharsets;

byte[] payload = {(byte) 0x63, (byte) 0x61, (byte) 0x66,
                  (byte) 0xC3, (byte) 0xA9};
String decoded = new String(payload, StandardCharsets.UTF_8); // café
```

- **Đầu vào:** các byte và `Charset` để diễn giải chúng thành ký tự.
- **Đầu ra:** một đối tượng `String` mới; phương thức không gắn charset vào `String` để giữ dùng về sau.
- **Tính quyết định:** kết quả giải mã không phụ thuộc default charset của JVM.
- **Giới hạn quan trọng:** byte không hợp lệ hoặc không thể ánh xạ theo charset đã chọn được **thay thế** bằng chuỗi ký tự thay thế mặc định; không nên dùng overload này để xác thực byte hợp lệ một cách nghiêm ngặt.

| Chiều xử lý | API rõ charset | Overload dựa trên default charset | Câu hỏi cần trả lời |
| --- | --- | --- | --- |
| `String → byte[]` | `text.getBytes(charset)` | `text.getBytes()` | Bên nhận mong đợi byte theo charset nào? |
| `byte[] → String` | `new String(bytes, charset)` | `new String(bytes)` | Bên gửi đã mã hóa byte theo charset nào? |
| Một đoạn byte | `new String(bytes, off, len, charset)` | `new String(bytes, off, len)` | Đoạn byte này có trùng ranh giới ký tự theo charset đó không? |

**Điểm cốt lõi:** `Charset` mô tả quy tắc chuyển đổi, không phải bộ lọc tự phát hiện encoding. Hai bên phải có thông tin về charset từ hợp đồng, metadata hoặc định dạng dữ liệu.

## 3. Chọn `Charset` thay vì để chương trình đoán

Java cung cấp các hằng charset tiêu chuẩn trong `java.nio.charset.StandardCharsets`:

| Hằng | Ý nghĩa | Dùng khi nào? |
| --- | --- | --- |
| `UTF_8` | UTF-8, mã hóa Unicode có độ dài biến đổi | Giao thức/file quy định UTF-8; lựa chọn phổ biến cho dữ liệu văn bản mới. |
| `US_ASCII` | ASCII 7 bit | Định dạng thực sự giới hạn ở ASCII. |
| `ISO_8859_1` | Mỗi ký tự trong bảng ISO-8859-1 ánh xạ đến một byte | Tương thích với dữ liệu được *đặc tả rõ* là ISO-8859-1. |
| `UTF_16LE` / `UTF_16BE` | UTF-16 theo thứ tự byte little-endian / big-endian | Định dạng quy định rõ thứ tự byte này. |
| `UTF_16` | Charset UTF-16 theo quy tắc BOM/thứ tự byte của charset | Khi định dạng bên ngoài yêu cầu đúng quy tắc UTF-16, không tự thay bằng UTF-16LE/BE. |

Với charset tiêu chuẩn, ưu tiên `StandardCharsets.UTF_8` (một đối tượng `Charset`) thay vì chuỗi tên như `"UTF-8"`. Các overload nhận tên charset cũng tồn tại, nhưng dùng hằng rõ kiểu giúp tránh lỗi gõ tên và không cần xử lý ngoại lệ kiểm tra tên charset không được hỗ trợ.

Nếu hệ thống bên ngoài gửi tên charset bằng metadata, có thể chuyển tên thành `Charset` bằng `Charset.forName(name)`, nhưng cần kiểm tra giá trị cho phép và xử lý `IllegalCharsetNameException`/`UnsupportedCharsetException` theo yêu cầu hệ thống.

**Không mặc định chọn UTF-8 khi hợp đồng nói khác.** Ví dụ, payload có byte `E9` đại diện cho `é` trong ISO-8859-1 thì phải dùng `StandardCharsets.ISO_8859_1` để giải mã đúng.

## 4. Ví dụ hoàn chỉnh: một charset cho cả hai chiều

Chạy chương trình sau trên Java 18 hoặc JDK mới hơn:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class ExplicitCharsetDemo {
    public static void main(String[] args) {
        Charset wireCharset = StandardCharsets.UTF_8;
        String original = "café";

        byte[] payload = original.getBytes(wireCharset);
        String restored = new String(payload, wireCharset);

        System.out.println("Bytes (hex): " + HexFormat.of().formatHex(payload));
        System.out.println("Restored: " + restored);

        byte[] expected = {
                (byte) 0x63, (byte) 0x61, (byte) 0x66,
                (byte) 0xC3, (byte) 0xA9
        };
        if (!Arrays.equals(payload, expected) || !original.equals(restored)) {
            throw new AssertionError("Không khớp hợp đồng UTF-8");
        }

        // Cùng byte UTF-8 nhưng dùng sai charset ở đầu nhận:
        System.out.println("Wrong decode: "
                + new String(payload, StandardCharsets.ISO_8859_1));
    }
}
```

Kết quả chính:

```text
Bytes (hex): 636166c3a9
Restored: café
Wrong decode: cafÃ©
```

Giải thích:

1. `c`, `a`, `f` có byte lần lượt là `63`, `61`, `66` trong UTF-8.
2. `é` có mã điểm Unicode `U+00E9`, được mã hóa trong UTF-8 thành `C3 A9`.
3. Khi giải mã UTF-8, `C3 A9` được ghép thành `é`.
4. Khi giải mã ISO-8859-1, `C3` và `A9` được coi là hai ký tự riêng, tạo ra `Ã©`.

Với nội dung Unicode rộng hơn, ví dụ `"Tiếng Việt 😀"`, UTF-8 sử dụng nhiều byte cho một số ký tự; vì vậy **không lấy `text.length()` làm số byte**. `String.length()` đếm đơn vị mã UTF-16, còn `payload.length` đếm số byte mã hóa thực.

## 5. Hai đầu hệ thống phải có cùng hợp đồng dữ liệu

Giả sử producer và consumer thỏa thuận payload văn bản dùng UTF-8:

```java
import java.nio.charset.StandardCharsets;

// Producer
String message = "Đơn hàng: Ứng dụng Java";
byte[] outgoingPayload = message.getBytes(StandardCharsets.UTF_8);

// Consumer (outgoingPayload đến từ mạng, queue hoặc lưu trữ)
String incomingMessage =
        new String(outgoingPayload, StandardCharsets.UTF_8);
```

Lời gọi `getBytes(StandardCharsets.UTF_8)` và `new String(bytes, StandardCharsets.UTF_8)` ghi rõ **định dạng byte trên đường truyền**. Với ứng dụng có nhiều lớp, nên định nghĩa charset từ hợp đồng ở điểm serialize/deserialize thay vì để mỗi lớp tự chọn.

Lưu ý `String` khôi phục đúng **không đồng nghĩa** với việc đã tuân thủ giao thức. Nếu hai đầu cùng dùng nhầm ISO-8859-1, một số nội dung vẫn round-trip được giữa hai đầu đó, nhưng chuỗi byte phát ra có thể sai yêu cầu của giao thức UTF-8. Kiểm thử tích hợp cần kiểm tra cả **byte mẫu đúng định dạng** và **văn bản sau giải mã**.

### Ví dụ dữ liệu cũ có charset khác UTF-8

```java
import java.nio.charset.StandardCharsets;

byte[] latin1Payload = {
        (byte) 0x63, (byte) 0x61, (byte) 0x66, (byte) 0xE9
};

String latin1Text =
        new String(latin1Payload, StandardCharsets.ISO_8859_1);
System.out.println(latin1Text); // café

// Chuyển dữ liệu sau khi đã giải mã đúng sang hợp đồng UTF-8 mới:
byte[] utf8Payload = latin1Text.getBytes(StandardCharsets.UTF_8);
```

Đây là **chuyển mã** qua `String`: giải mã byte theo charset nguồn, sau đó mã hóa văn bản thành byte theo charset đích. Không thể chuyển mã an toàn bằng cách đơn thuần đổi tên `Charset` hoặc lấy các byte cũ và tuyên bố chúng đã là UTF-8.

## 6. Xử lý byte lỗi và ký tự không biểu diễn được

Hai overload nhận `Charset` thuận tiện cho luồng dữ liệu tin cậy, nhưng theo hợp đồng API, chúng dùng **replacement** khi gặp dữ liệu không hợp lệ. Điều này tránh lỗi tức thời ở một số tình huống hiển thị, nhưng có thể làm mất thông tin khi lưu hoặc đồng bộ dữ liệu.

### 6.1. Giải mã byte UTF-8 không hợp lệ

```java
import java.nio.charset.StandardCharsets;

byte[] brokenUtf8 = {(byte) 0xE9}; // E9 đơn lẻ không tạo thành UTF-8 hợp lệ.
String text = new String(brokenUtf8, StandardCharsets.UTF_8);
System.out.println(text.equals("\uFFFD")); // true: ký tự thay thế U+FFFD
```

`new String(byte[], Charset)` không báo lỗi để người gọi biết byte đầu vào hỏng. Việc mã hóa lại ký tự thay thế bằng UTF-8 sẽ tạo dữ liệu khác, và **không thể phục hồi** byte gốc chỉ từ `String` đã bị thay thế.

### 6.2. Mã hóa ký tự ngoài khả năng của charset

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

byte[] ascii = "café".getBytes(StandardCharsets.US_ASCII);
System.out.println(HexFormat.of().formatHex(ascii)); // 6361663f
```

Byte `3F` là dấu hỏi `?` thay cho ký tự `é` mà US-ASCII không biểu diễn được. Dù đã ghi charset rõ ràng, chọn **sai charset theo nhu cầu dữ liệu** vẫn có thể làm mất nội dung.

### 6.3. Khi cần từ chối dữ liệu không hợp lệ: decoder/encoder nghiêm ngặt

Nếu hợp đồng yêu cầu UTF-8 hợp lệ tuyệt đối, sử dụng `CharsetDecoder` để chuyển lỗi thành ngoại lệ:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String strictDecodeUtf8(byte[] payload)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(payload))
            .toString();
}
```

`strictDecodeUtf8(new byte[] {(byte) 0xE9})` ném `MalformedInputException` (thuộc nhóm `CharacterCodingException`). Ứng dụng có thể từ chối message, báo cho đối tác hoặc kiểm tra lại nguồn dữ liệu.

Tương tự, `CharsetEncoder` có thể bắt lỗi ký tự không biểu diễn được:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static void validateAsciiEncoding(String text)
        throws CharacterCodingException {
    StandardCharsets.US_ASCII.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(text));
}
```

Gọi `validateAsciiEncoding("café")` sẽ ném `UnmappableCharacterException`, thay vì âm thầm thay `é` bằng `?`. API `getBytes(Charset)` cũng có thể thay thế **surrogate UTF-16 không ghép cặp** trong `String`; khi dữ liệu đầu vào cần được kiểm tra chặt chẽ, `CharsetEncoder` với `REPORT` là giải pháp tương ứng ở chiều mã hóa.

**Tiêu chí lựa chọn:** với log hoặc nội dung hiển thị có thể chấp nhận ký tự thay thế; với dữ liệu cần giữ nguyên tuyệt đối như import có đối soát, định danh hay chữ ký, hãy báo lỗi rõ ràng để không làm mất dữ liệu.

## 7. Áp dụng ở ranh giới I/O thật

Nếu byte đến từ tệp, stream hoặc socket, hãy xác định charset ngay tại lớp I/O:

```java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

// Giả sử input và output là các stream đã được tạo bởi tầng kết nối.
InputStreamReader reader =
        new InputStreamReader(input, StandardCharsets.UTF_8);
OutputStreamWriter writer =
        new OutputStreamWriter(output, StandardCharsets.UTF_8);
```

Hoặc khi có `Path`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

Path path = Path.of("message.txt");
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);
String restored = Files.readString(path, StandardCharsets.UTF_8);
```

Các overload `Files.readString(Path)` và `Files.writeString(Path, CharSequence)` vốn đã **định nghĩa UTF-8 trong hợp đồng API**, nên không cần đồng nhất mọi overload thiếu charset với `Charset.defaultCharset()`. Chỉ định charset tường minh khi nó làm rõ hợp đồng định dạng hoặc khi cần xử lý định dạng khác.

### Không chia cắt ký tự đa byte một cách tùy ý

UTF-8 có thể dùng 2–4 byte cho một mã điểm Unicode. Nếu dữ liệu từ socket đến thành các khối byte tùy ý, một ký tự có thể bắt đầu ở khối thứ nhất và kết thúc ở khối sau. **Không** giải mã từng khối bằng `new String(chunk, UTF_8)` rồi nối `String`: đoạn kết thúc giữa chừng có thể bị thay thế.

Dùng `InputStreamReader` với charset rõ ràng, hoặc `CharsetDecoder` ở chế độ xử lý gia tăng để giữ trạng thái giữa các khối. Nếu dùng `new String(bytes, offset, length, charset)`, phải chắc chắn đoạn byte được cắt theo ranh giới hợp lệ của định dạng.

### Charset không tự phát hiện BOM hoặc chuẩn hóa Unicode

- `new String(bytes, UTF_8)` **không phải công cụ dò charset**. Nếu payload có UTF-8 BOM (`EF BB BF`), các byte này được giải mã thành `U+FEFF`; việc chấp nhận hay xử lý BOM phụ thuộc hợp đồng tệp/giao thức.
- Encode/decode không tự chuẩn hóa các chuỗi Unicode tương đương về cùng một dạng. Nếu cần chuẩn hóa để so khớp, tìm kiếm hoặc kiểm tra định danh, hãy xét `java.text.Normalizer` theo yêu cầu nghiệp vụ.

## 8. Kiểm thử hợp đồng hai chiều độc lập với môi trường

Một bộ kiểm thử tốt kiểm tra đồng thời: byte mong đợi, văn bản khôi phục và cách phản ứng với dữ liệu hỏng. Ví dụ:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class CharsetContractCheck {
    public static void main(String[] args) {
        String input = "café";
        byte[] expected = {
                (byte) 0x63, (byte) 0x61, (byte) 0x66,
                (byte) 0xC3, (byte) 0xA9
        };

        byte[] actual = input.getBytes(StandardCharsets.UTF_8);
        if (!Arrays.equals(expected, actual)) {
            throw new AssertionError("Sai byte UTF-8 của giao thức");
        }

        String decoded = new String(expected, StandardCharsets.UTF_8);
        if (!input.equals(decoded)) {
            throw new AssertionError("Không đọc lại được nội dung UTF-8");
        }
    }
}
```

Bổ sung thêm các trường hợp `"Tiếng Việt"`, emoji, ký tự kết hợp dấu, byte UTF-8 bị cắt, dữ liệu ISO-8859-1 từ đối tác và chuỗi chứa ký tự không biểu diễn được trong charset đích. Kiểm thử byte hex phát hiện lỗi ngay cả khi cả producer và consumer vô tình dùng cùng một charset sai.

Khi rà soát mã nguồn đang chạy trên Java 18+:

1. Xác định nơi `String` được chuyển thành byte và nơi byte được chuyển thành `String`.
2. Tra quy định của tệp/giao thức/API bên ngoài để biết charset thực; ưu tiên hằng `StandardCharsets` nếu phù hợp.
3. Chỉ rõ `Charset` ở cả hai đầu mà bạn kiểm soát, và kiểm tra byte thực tế trên đường truyền.
4. Chọn chính sách khi dữ liệu hỏng: chấp nhận replacement hay bắt buộc `REPORT`.
5. Đặc biệt kiểm tra dữ liệu ngoài ASCII và các ranh giới chunk/stream; không dựa vào việc chương trình chỉ chạy thành công trên máy phát triển.

## 9. Những nhầm lẫn cần tránh

| Nhận định | Vì sao sai hoặc chưa đủ? |
| --- | --- |
| “JDK 18 mặc định UTF-8 rồi, chỉ định charset là thừa.” | Đặc tả bên ngoài vẫn quyết định charset của payload; giá trị mặc định có thể chịu cấu hình tương thích. |
| “`String` là UTF-8.” | `String` là văn bản Unicode ở mức API; UTF-8 là quy tắc mã hóa dữ liệu thành byte. |
| “Cùng charset encode/decode thì chắc chắn đúng.” | Một định dạng có thể yêu cầu charset khác; và replacement có thể làm hỏng round-trip. |
| “`getBytes(US_ASCII)` báo lỗi nếu có tiếng Việt.” | Overload này thay thế ký tự không mã hóa được; dùng `CharsetEncoder` để yêu cầu báo lỗi. |
| “`new String(bytes, UTF_8)` kiểm tra byte có hợp lệ.” | Overload này thay thế byte không hợp lệ; dùng `CharsetDecoder` với `REPORT` để kiểm tra nghiêm ngặt. |
| “Chia byte thành các đoạn tùy ý rồi decode từng đoạn vẫn đúng.” | Ký tự đa byte có thể bị cắt giữa các đoạn; dùng decoder gia tăng hoặc reader có trạng thái. |

## 10. Câu hỏi tự luyện

1. Một API yêu cầu payload UTF-8. Vì sao chỉ kiểm tra `new String(text.getBytes(ISO_8859_1), ISO_8859_1).equals(text)` chưa đủ để khẳng định API đúng?
2. Bạn nhận một `byte[]` có hex `63 61 66 E9`; nếu đối tác xác nhận ISO-8859-1, hãy viết lời gọi khôi phục `"café"` rồi mã hóa lại thành UTF-8.
3. Trong quy trình import dữ liệu quan trọng, bạn muốn từ chối byte UTF-8 không hợp lệ thay vì hiển thị `�`. Nên dùng API nào và cấu hình xử lý lỗi gì?
4. Một ký tự UTF-8 gồm ba byte nhưng bị tách sang hai lần đọc socket. Vì sao `new String()` trên từng khối byte có thể làm mất nội dung?

## 11. Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi và lý do thay đổi default charset từ Java 18.
- [`String` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): mô tả chính thức các overload `getBytes(Charset)` và `String(byte[], Charset)`.
- [`StandardCharsets` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset tiêu chuẩn.
- [`CharsetDecoder` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [`CharsetEncoder` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): xử lý đầu vào lỗi và ký tự không ánh xạ được.
