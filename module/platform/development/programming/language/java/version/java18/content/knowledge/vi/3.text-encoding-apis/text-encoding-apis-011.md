# ByteArrayOutputStream.toString(): lựa chọn overload để tránh giải mã ngầm

## 1. ByteArrayOutputStream lưu byte, không lưu văn bản

`ByteArrayOutputStream` là một `OutputStream` ghi dữ liệu vào một vùng đệm trong bộ nhớ. Khi chương trình gọi `write(...)`, lớp này giữ lại **byte** đã nhận để có thể lấy ra sau đó. Nó không tự biết các byte đó là UTF-8, ISO-8859-1, ảnh PNG, dữ liệu nén hay một định dạng nhị phân khác.

Khi cần diễn giải nội dung vùng đệm thành văn bản, `toString()` sẽ giải mã byte. Lúc này charset trở thành yếu tố quyết định:

```text
String / dữ liệu nguồn
        |
        | encode bằng charset
        v
      byte[]
        |
        | ByteArrayOutputStream.write(...)
        v
  ByteArrayOutputStream
        |
        | toString(charset)
        v
      String
```

Trong Java 18, thay đổi đáng chú ý là UTF-8 trở thành default charset thông thường theo JEP 400. Điều đó ảnh hưởng tới overload `toString()` không tham số vì overload này dùng default charset. Tuy nhiên, một buffer có thể chứa byte theo định dạng riêng, nên ứng dụng cần chọn overload theo hợp đồng dữ liệu.

**Nguyên tắc:** chỉ gọi `toString(Charset)` khi byte trong buffer thực sự là văn bản được mã hóa bằng charset đó. Nếu buffer chứa dữ liệu nhị phân, giữ nó ở dạng `byte[]` hoặc chuyển tiếp bằng API byte.

## 2. Các overload toString và sự khác nhau

`ByteArrayOutputStream` cung cấp các cách chuyển nội dung hiện tại thành `String`:

| Lời gọi | Charset | Điểm cần biết |
| --- | --- | --- |
| `buffer.toString()` | `Charset.defaultCharset()` | Phụ thuộc default charset của JVM |
| `buffer.toString(StandardCharsets.UTF_8)` | UTF-8 tường minh | Không phụ thuộc default charset |
| `buffer.toString(charset)` | Charset truyền vào | Cách tổng quát khi định dạng quy định charset |
| `buffer.toString("UTF-8")` | Charset tra theo tên | Có thể ném `UnsupportedEncodingException` nếu tên không được hỗ trợ |

Overload nhận `Charset` có từ **Java 10**. Nếu charset đã biết, ưu tiên truyền đối tượng `Charset` hoặc hằng số `StandardCharsets` thay vì chuỗi tên.

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

ByteArrayOutputStream buffer = new ByteArrayOutputStream();

// Ghi byte UTF-8 vào buffer.
byte[] encoded = "Xin chào".getBytes(StandardCharsets.UTF_8);
buffer.write(encoded, 0, encoded.length);

// Giải mã đúng bằng UTF-8.
String text = buffer.toString(StandardCharsets.UTF_8);
```

`toString()` không tham số không nhận biết encoding đã dùng lúc ghi byte. Nó chỉ dùng default charset hiện tại. Do đó, hai lời gọi có thể cho kết quả khác nhau dù nội dung byte trong buffer không đổi.

## 3. JEP 400 và default charset từ Java 18

JEP 400 — UTF-8 by Default — đặt UTF-8 làm default charset thông thường của Java SE từ Java 18. Vì `ByteArrayOutputStream.toString()` dùng `Charset.defaultCharset()`, nên trong cấu hình thông thường của JDK 18+, overload này giải mã bằng UTF-8.

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
```

Trong cấu hình mặc định thông thường, kết quả là `UTF-8`. Tuy nhiên, cần phân biệt:

- **Default charset** là lựa chọn môi trường mà API không tham số có thể sử dụng.
- **Charset của payload** là quy ước do nơi tạo byte hoặc giao thức dữ liệu xác định.
- **Charset được truyền trực tiếp** vào `toString(Charset)` thể hiện rõ cách giải mã payload.

JDK hiện đại có thể hỗ trợ chế độ tương thích như `-Dfile.encoding=COMPAT`. Khi chạy ở chế độ đó, default charset có thể theo môi trường như trước Java 18. Vì vậy, code không nên dựa vào `toString()` để giải mã dữ liệu trao đổi giữa các thành phần.

Ví dụ, nếu buffer chứa byte UTF-8 nhưng default charset là một charset khác, `toString()` có thể tạo ra ký tự sai (mojibake). Gọi `toString(StandardCharsets.UTF_8)` vẫn giải mã theo UTF-8 như hợp đồng của dữ liệu.

## 4. Byte phải được mã hóa và giải mã bằng cùng một charset

Giả sử chương trình ghi chuỗi `café` thành byte UTF-8:

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

String original = "café";

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
buffer.write(bytes, 0, bytes.length);

String restored = buffer.toString(StandardCharsets.UTF_8);
System.out.println(restored); // café
```

Với UTF-8, chữ `é` được biểu diễn bằng hai byte `C3 A9`. Nếu cùng những byte đó bị giải mã bằng ISO-8859-1, kết quả sẽ là `cafÃ©`.

| Văn bản | Charset | Byte hex |
| --- | --- | --- |
| `café` | UTF-8 | `63 61 66 C3 A9` |
| `café` | ISO-8859-1 | `63 61 66 E9` |

Một `ByteArrayOutputStream` không lưu metadata về charset. Nếu nhiều thành phần cùng đọc buffer, hãy ghi rõ charset trong hợp đồng hoặc truyền charset cùng dữ liệu ở tầng ứng dụng.

### 4.1. Dữ liệu từ hệ thống cũ

Nếu nguồn dữ liệu quy định ISO-8859-1, hãy giải mã bằng charset đó:

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

byte[] legacyBytes = {
    (byte) 0x63, (byte) 0x61, (byte) 0x66, (byte) 0xE9
};

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
buffer.write(legacyBytes, 0, legacyBytes.length);

String text = buffer.toString(StandardCharsets.ISO_8859_1);
System.out.println(text); // café
```

Không chuyển dữ liệu sang UTF-8 chỉ bằng cách đổi tham số giải mã. Nếu byte cũ là ISO-8859-1, cần decode theo ISO-8859-1 thành `String`, rồi encode lại thành UTF-8 nếu muốn chuyển đổi định dạng:

```java
String decoded = buffer.toString(StandardCharsets.ISO_8859_1);
byte[] utf8 = decoded.getBytes(StandardCharsets.UTF_8);
```

Hai bước này có ý nghĩa khác nhau: decode diễn giải byte hiện tại; encode tạo ra byte mới theo charset đích.

## 5. ByteArrayOutputStream không phải lúc nào cũng chứa văn bản

Tên lớp có chữ `OutputStream` vì đây là luồng byte. Một số trường hợp phổ biến:

| Nội dung được ghi | Có nên gọi `toString(Charset)`? | Cách xử lý |
| --- | --- | --- |
| Văn bản UTF-8 | Có | `toString(StandardCharsets.UTF_8)` |
| Văn bản ISO-8859-1 | Có | `toString(StandardCharsets.ISO_8859_1)` |
| JSON được encode UTF-8 | Có | Giải mã UTF-8 rồi parse JSON |
| Ảnh PNG/JPEG | Không | Giữ `byte[]`, ghi file hoặc truyền tới API ảnh |
| ZIP/GZIP | Không | Dùng API giải nén |
| Ciphertext hoặc dữ liệu nén | Không | Xử lý theo định dạng nhị phân |
| Dữ liệu giao thức có cả header nhị phân và payload văn bản | Không giải mã toàn bộ | Parse cấu trúc byte, giải mã riêng phần payload văn bản |

Ví dụ sai:

```java
// Không dùng để "xem nội dung" một file PNG.
String imageText = imageBuffer.toString(StandardCharsets.UTF_8);
```

Byte ảnh không phải văn bản UTF-8. Việc giải mã tùy tiện có thể tạo ra ký tự thay thế, ký tự điều khiển hoặc chuỗi không có ý nghĩa. Hãy giữ nguyên byte:

```java
byte[] imageBytes = imageBuffer.toByteArray();
```

Nếu cần gửi toàn bộ buffer sang một `OutputStream` khác mà không cần tạo bản sao `byte[]`, dùng `writeTo`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;

static void forward(ByteArrayOutputStream buffer, OutputStream destination)
        throws IOException {
    buffer.writeTo(destination);
}
```

`writeTo` chuyển các byte hiện có sang đích; nó không decode hay encode lại.

## 6. Dữ liệu lỗi định dạng: toString thay thế byte không hợp lệ

Một điểm quan trọng trong hợp đồng API: các overload `toString()` của `ByteArrayOutputStream` **thay thế** chuỗi byte malformed hoặc unmappable bằng replacement string mặc định của charset. Chúng không cung cấp lựa chọn `CodingErrorAction.REPORT`.

Ví dụ, byte `C3 28` không phải chuỗi UTF-8 hợp lệ: `C3` mở đầu một chuỗi nhiều byte nhưng byte tiếp theo `28` không phải continuation byte hợp lệ.

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

byte[] malformed = {(byte) 0xC3, (byte) 0x28};

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
buffer.write(malformed, 0, malformed.length);

String text = buffer.toString(StandardCharsets.UTF_8);
System.out.println(text); // Có ký tự thay thế cho phần byte lỗi.
```

Điều này có thể hữu ích khi chỉ cần hiển thị văn bản tốt nhất có thể. Nhưng nó không phù hợp nếu dữ liệu cần được xác thực nghiêm ngặt, vì thông tin byte ban đầu đã bị thay thế trong kết quả `String`.

`checkError()` không tồn tại trên `ByteArrayOutputStream`; thao tác ghi vào vùng đệm trong bộ nhớ không phải cơ chế xác nhận nội dung văn bản hợp lệ. Muốn phát hiện byte sai encoding, dùng `CharsetDecoder` có `CodingErrorAction.REPORT`.

## 7. Decode nghiêm ngặt bằng CharsetDecoder

Nếu payload bắt buộc phải là UTF-8 hợp lệ, hãy decode bằng decoder được cấu hình báo lỗi:

```java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(ByteArrayOutputStream buffer)
        throws CharacterCodingException {
    byte[] bytes = buffer.toByteArray();

    var decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

    return decoder.decode(ByteBuffer.wrap(bytes)).toString();
}
```

Với byte lỗi, `decode(...)` ném `MalformedInputException` hoặc `UnmappableCharacterException` (đều thuộc `CharacterCodingException`). Ứng dụng có thể từ chối payload, ghi nhận nguồn gửi sai định dạng hoặc yêu cầu gửi lại.

Ví dụ:

```java
byte[] malformed = {(byte) 0xC3, (byte) 0x28};

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
buffer.write(malformed, 0, malformed.length);

try {
    String value = decodeUtf8Strict(buffer);
    System.out.println(value);
} catch (CharacterCodingException e) {
    System.err.println("Payload không phải UTF-8 hợp lệ: " + e);
}
```

`toByteArray()` tạo một bản sao các byte hiện có. Đối với buffer lớn, hãy tính đến chi phí bộ nhớ của bản sao này khi chọn cách giải mã. Nếu cần xử lý dữ liệu lớn theo luồng, cân nhắc thiết kế pipeline byte/decoder streaming thay vì gom toàn bộ vào một `ByteArrayOutputStream`.

## 8. So sánh toString(Charset), toString(String) và new String(byte[], Charset)

Các cách sau đều có thể giải mã byte thành văn bản, nhưng có khác biệt về API và chi phí:

| Cách làm | Ưu điểm | Điểm cần lưu ý |
| --- | --- | --- |
| `buffer.toString(charset)` | Ngắn gọn, charset tường minh, không cần lấy `byte[]` qua API công khai | Byte lỗi được thay thế |
| `buffer.toString()` | Gọn khi thật sự muốn dùng default charset | Charset phụ thuộc cấu hình JVM |
| `buffer.toString("UTF-8")` | Dùng tên charset từ cấu hình chuỗi | Có checked `UnsupportedEncodingException` |
| `new String(buffer.toByteArray(), charset)` | Làm rõ bước lấy byte và bước decode | `toByteArray()` tạo bản sao; byte lỗi cũng bị thay thế |
| `decoder.decode(ByteBuffer.wrap(bytes))` | Có thể cấu hình `REPORT`, `REPLACE` hoặc `IGNORE` | Cần xử lý `CharacterCodingException` |

Nếu charset đã biết tại thời điểm biên dịch, `StandardCharsets.UTF_8` là lựa chọn rõ ràng:

```java
String text = buffer.toString(StandardCharsets.UTF_8);
```

Nếu charset đến từ cấu hình hoặc metadata, giữ nó dưới kiểu `Charset` sau khi xác thực cấu hình:

```java
import java.nio.charset.Charset;

Charset charset = Charset.forName(configuredCharsetName);
String text = buffer.toString(charset);
```

Không dùng tên charset lấy từ dữ liệu không đáng tin cậy mà không xác thực. `Charset.forName` có thể ném `IllegalCharsetNameException` hoặc `UnsupportedCharsetException`.

## 9. Dùng toByteArray, writeTo, reset và size đúng mục đích

`ByteArrayOutputStream` có một số phương thức hữu ích để thao tác với byte:

| Phương thức | Tác dụng |
| --- | --- |
| `toByteArray()` | Trả về bản sao của vùng byte hiện có |
| `writeTo(out)` | Ghi các byte hiện có sang `OutputStream` khác |
| `size()` | Trả về số byte đang được lưu |
| `reset()` | Đặt số byte hiện có về 0 để tái sử dụng buffer |
| `toString(charset)` | Giải mã byte thành `String` theo charset |
| `close()` | Không có tác dụng với `ByteArrayOutputStream` |

`size()` đếm **byte**, không phải ký tự. Một chuỗi UTF-8 có ký tự nhiều byte sẽ có `size()` lớn hơn số ký tự nhìn thấy. `String.length()` lại đếm đơn vị mã UTF-16, nên hai con số không có quan hệ một-một.

Ví dụ tái sử dụng buffer:

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

ByteArrayOutputStream buffer = new ByteArrayOutputStream();

byte[] first = "lần một".getBytes(StandardCharsets.UTF_8);
buffer.write(first, 0, first.length);

System.out.println(buffer.toString(StandardCharsets.UTF_8));

buffer.reset(); // Xóa nội dung logic, giữ vùng đệm để tái sử dụng.

byte[] second = "lần hai".getBytes(StandardCharsets.UTF_8);
buffer.write(second, 0, second.length);

System.out.println(buffer.toString(StandardCharsets.UTF_8));
```

`reset()` không xóa dữ liệu vật lý khỏi vùng nhớ theo nghĩa bảo mật; nó chỉ đặt số byte hiện có về 0. Nếu buffer chứa dữ liệu nhạy cảm, không coi `reset()` là biện pháp xóa an toàn.

`close()` của `ByteArrayOutputStream` không có tác dụng; có thể tiếp tục ghi và lấy dữ liệu sau khi gọi `close()`. Điều này khác với nhiều stream gắn với file hoặc socket. Dù vậy, sử dụng try-with-resources khi bọc nó bằng một writer/stream khác vẫn cần hiểu tài nguyên nào thực sự bị đóng.

## 10. Kết hợp PrintStream hoặc Writer với ByteArrayOutputStream

Một trường hợp thường gặp là dùng `ByteArrayOutputStream` làm đích tạm cho API ghi văn bản.

### 10.1. PrintStream với charset rõ ràng

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;

ByteArrayOutputStream bytes = new ByteArrayOutputStream();

try (PrintStream out = new PrintStream(
        bytes, false, StandardCharsets.UTF_8)) {
    out.println("Xin chào");
    out.println("Tiếng Việt 🌍");
}

String result = bytes.toString(StandardCharsets.UTF_8);
```

`PrintStream` encode ký tự thành UTF-8; `ByteArrayOutputStream` chỉ giữ byte. Khi đọc lại, phải dùng cùng charset. Đóng `PrintStream` sẽ gọi đóng stream bên dưới; với `ByteArrayOutputStream`, `close()` không làm mất nội dung và không cấm đọc lại.

### 10.2. OutputStreamWriter với Charset tường minh

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

ByteArrayOutputStream bytes = new ByteArrayOutputStream();

try (OutputStreamWriter writer =
        new OutputStreamWriter(bytes, StandardCharsets.UTF_8)) {
    writer.write("Báo cáo");
    writer.write('\n');
}

String result = bytes.toString(StandardCharsets.UTF_8);
```

Ở đây `OutputStreamWriter` chịu trách nhiệm encode. `ByteArrayOutputStream` không biết nội dung là UTF-8; charset chỉ được xác định bởi code đã tạo byte và phải được giữ nhất quán khi đọc lại.

Nếu cần phát hiện ký tự không thể mã hóa thay vì thay thế, cấu hình `CharsetEncoder` với `CodingErrorAction.REPORT` cho `OutputStreamWriter`.

## 11. Lựa chọn API theo mục tiêu

| Mục tiêu | API phù hợp |
| --- | --- |
| Lấy văn bản UTF-8 từ buffer | `buffer.toString(StandardCharsets.UTF_8)` |
| Lấy văn bản theo default charset có chủ ý | `buffer.toString()` |
| Đọc byte gốc để gửi hoặc parse binary | `buffer.toByteArray()` |
| Chuyển byte sang stream khác | `buffer.writeTo(destination)` |
| Xác thực byte UTF-8 nghiêm ngặt | `CharsetDecoder` với `REPORT` |
| Xử lý dữ liệu lớn, không muốn giữ toàn bộ trong RAM | Stream/decoder theo khối thay vì `ByteArrayOutputStream` |
| Ghi văn bản vào buffer | `OutputStreamWriter` hoặc `PrintStream` có charset tường minh |

Đừng dùng `toString()` chỉ để log nội dung của mọi buffer. Nếu buffer chứa dữ liệu nhị phân, hãy log kích thước, hex có giới hạn hoặc metadata phù hợp thay vì cố giải mã toàn bộ.

## 12. Kiểm thử byte và round-trip

Một phép kiểm thử tốt xác nhận byte thực tế và kết quả giải mã:

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String original = "café - Tiếng Việt 🌍";

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
byte[] expectedBytes = original.getBytes(StandardCharsets.UTF_8);
buffer.write(expectedBytes, 0, expectedBytes.length);

byte[] actualBytes = buffer.toByteArray();
if (!Arrays.equals(expectedBytes, actualBytes)) {
    throw new AssertionError("Byte trong buffer không đúng UTF-8");
}

String restored = buffer.toString(StandardCharsets.UTF_8);
if (!original.equals(restored)) {
    throw new AssertionError("Round-trip UTF-8 không khớp");
}
```

Nên bổ sung các ca:

1. Nội dung ASCII và Unicode có dấu, ví dụ `café`, `Tiếng Việt`.
2. Ký tự ngoài BMP như `🌍`, để xác minh nội dung Unicode sau round-trip.
3. Byte được encode bằng charset khác UTF-8, rồi decode bằng charset đúng.
4. Byte malformed, xác nhận `toString(Charset)` thay thế và decoder `REPORT` phát hiện lỗi.
5. Buffer rỗng, buffer sau `reset()` và buffer sau `close()`.
6. Payload nhị phân để xác nhận code giữ `byte[]` hoặc dùng `writeTo`, không gọi `toString()`.

Ví dụ byte malformed để kiểm tra strict decoder:

```java
byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
buffer.write(invalidUtf8, 0, invalidUtf8.length);

try {
    decodeUtf8Strict(buffer);
    throw new AssertionError("Phải phát hiện UTF-8 malformed");
} catch (java.nio.charset.MalformedInputException expected) {
    // Đúng: decoder REPORT đã phát hiện chuỗi byte không hợp lệ.
}
```

## 13. Những nhận định dễ nhầm

- **“ByteArrayOutputStream biết charset của dữ liệu được ghi.”** Sai. Nó chỉ giữ byte.
- **“`toString()` luôn dùng UTF-8 trên mọi cấu hình JDK.”** Sai. Nó dùng default charset; Java 18+ mặc định UTF-8 trong cấu hình thông thường nhưng có thể có chế độ tương thích.
- **“`toString(Charset)` báo lỗi nếu byte malformed.”** Sai. Nó thay chuỗi byte lỗi bằng replacement string mặc định của charset.
- **“`toByteArray()` trả về buffer nội bộ.”** Sai. Nó trả về bản sao byte hiện có.
- **“`size()` là số ký tự.”** Sai. Đây là số byte.
- **“Có thể chuyển PNG hoặc ZIP thành String UTF-8 để xem dữ liệu.”** Sai. Dữ liệu nhị phân phải được xử lý như byte.
- **“`reset()` xóa an toàn dữ liệu nhạy cảm.”** Sai. Nó chỉ đặt số byte logic về 0.
- **“`close()` làm ByteArrayOutputStream không thể dùng tiếp.”** Sai. `close()` không có tác dụng với lớp này; nhưng wrapper khác có thể có hành vi đóng riêng.
- **“Dùng `toString()` rồi encode lại sẽ khôi phục byte gốc.”** Không bảo đảm. Decode sai charset hoặc thay thế byte malformed có thể làm mất thông tin.

## 14. Tài liệu tham khảo chính thức

- [ByteArrayOutputStream — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ByteArrayOutputStream.html): `toString()`, `toString(Charset)`, `toByteArray()`, `writeTo()`, `reset()` và `close()`.
- [Charset — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/Charset.html): `defaultCharset()` và các charset.
- [CharsetDecoder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html): xử lý byte malformed/unmappable và `CodingErrorAction.REPORT`.
- [StandardCharsets — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn như UTF-8, ISO-8859-1 và US-ASCII.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18 và phạm vi tác động.

