# Chuyển đổi giữa byte và ký tự trong Java: bảng mã, UTF-8 và xử lý lỗi

> **Ngữ cảnh:** Bài học thuộc nhóm **Bảng mã** của Java 7. Bước chuyển dữ liệu từ ký tự thành byte gọi là **encoding**; bước chuyển byte về ký tự gọi là **decoding**. Trong Java hiện đại, hãy chủ động chỉ định `Charset` ở mọi ranh giới file, mạng, database hoặc giao tiếp hệ thống. `java.nio.charset.StandardCharsets` có từ Java 7 và vẫn là API chuẩn trên Java 17+. Bài sử dụng ví dụ biên dịch bằng JDK 17, đồng thời ghi rõ những tiện ích được giới thiệu ở phiên bản mới hơn.

## 1. Phân biệt dữ liệu văn bản và dữ liệu nhị phân

Một chuỗi Java biểu diễn văn bản ở phía chương trình; một mảng `byte[]` chứa **các giá trị 8 bit**. Khi lưu vào file hoặc truyền qua mạng, ký tự phải được biểu diễn thành byte theo **một bảng mã (character encoding)** cụ thể.

Quy trình đúng về mặt ý tưởng:

```text
Văn bản Java (String, UTF-16 code units)
           |
           | encode với một Charset đã chọn
           v
      byte[] (dữ liệu để lưu/truyền)
           |
           | decode với cùng Charset tương thích
           v
Văn bản Java (String) được khôi phục
```

Ví dụ, ký tự Latin `A` có mã Unicode `U+0041` và trong UTF-8 được lưu bởi **một byte `0x41`**. Ký tự `é` (`U+00E9`) cần **hai byte `C3 A9`** trong UTF-8. Ký tự `中` (`U+4E2D`) cần **ba byte `E4 B8 AD`**. Emoji `🙂` (`U+1F642`) cần **bốn byte `F0 9F 99 82`**.

Vì thế không thể luôn áp dụng công thức “một ký tự = một byte”. Kết quả chuyển đổi phụ thuộc **bảng mã được chỉ định**, không chỉ nội dung String.

### 1.1. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Unicode code point** | Giá trị định danh ký tự trừu tượng trong Unicode | `U+0041`, `U+00E9`, `U+1F642` |
| **UTF-16 code unit** | Đơn vị 16 bit mà Java dùng cho một `char` | `char` là 16 bit, emoji có thể cần hai `char` |
| **Charset / character encoding** | Quy tắc ánh xạ văn bản thành byte và ngược lại | UTF-8, UTF-16LE, ISO-8859-1 |
| **Encode** | `String`/ký tự → byte | `text.getBytes(UTF_8)` |
| **Decode** | byte → `String`/ký tự | `new String(bytes, UTF_8)` |
| **Malformed input** | Chuỗi đơn vị byte hoặc UTF-16 không tuân thủ cấu trúc bảng mã | Byte dẫn UTF-8 thiếu byte tiếp nối |
| **Unmappable character** | Ký tự hợp lệ nhưng bảng mã đích không biểu diễn được | `é` trong US-ASCII |
| **Replacement** | Ký tự/byte thay thế khi chọn chính sách tiếp tục | `U+FFFD` khi decode UTF-8 hỏng |
| **Mojibake** | Văn bản biến dạng vì dùng sai bảng mã | UTF-8 bị decode bằng ISO-8859-1 |

**Đừng nhầm byte signed với mã Unicode.** `byte` trong Java có dải giá trị `-128..127`. Khi in một mảng chứa byte `0xC3`, giá trị hiển thị ở dạng số có dấu là `-61`. Điều này không có nghĩa byte đã bị hỏng hay ký tự có code point âm.

## 2. `char` không phải lúc nào cũng là một “ký tự” hoàn chỉnh

Java `char` là một **UTF-16 code unit 16 bit**, không phải byte và cũng không nhất thiết tương ứng một Unicode code point đầy đủ.

Với `String text = "Aé中🙂"`, các đại lượng là:

- **4 Unicode code points**: `U+0041`, `U+00E9`, `U+4E2D`, `U+1F642`.
- **5 UTF-16 code units**: ba ký tự đầu mỗi ký tự một code unit, emoji `🙂` cần **một surrogate pair** (hai `char`).
- **10 byte UTF-8**: lần lượt `1 + 2 + 3 + 4` byte.

`String.length()` đếm **UTF-16 code units**, không đếm Unicode code points và không đếm byte của UTF-8. Muốn đếm code point trong chuỗi, có thể dùng:

```java
int count = text.codePointCount(0, text.length());
```

Đây là đoạn minh họa, với `String text` đã có. Khi duyệt một ký tự ngoài BMP, `charAt(index)` chỉ trả về một nửa surrogate pair ở vị trí đó; `codePointAt(index)` hoặc `text.codePoints()` phù hợp hơn nếu muốn làm việc theo Unicode code point.

**Một cấp độ nữa:** thứ người dùng nhìn nhận là *một ký tự hiển thị* (*grapheme cluster*) có thể gồm **nhiều code points**, ví dụ một chữ có dấu kết hợp hoặc chuỗi emoji có ký tự nối. Vì vậy cả `String.length()` và `codePointCount()` không phải luôn là số “ký tự nhìn thấy” trên giao diện.

## 3. Charset chuẩn trong Java 7+

Để viết code có thể đọc lại ổn định trên những máy khác nhau, ưu tiên các hằng số trong `java.nio.charset.StandardCharsets`:

```java
import java.nio.charset.StandardCharsets;

byte[] data = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(data, StandardCharsets.UTF_8);
```

Đây là **snippet** với `String text` đã có. `StandardCharsets` được giới thiệu trong Java 7 và tiếp tục hỗ trợ các bảng mã chuẩn:

| Hằng số | Ý nghĩa thường gặp |
| --- | --- |
| `StandardCharsets.UTF_8` | UTF-8, bảng mã Unicode rất phổ biến cho API, JSON, file và giao thức hiện đại |
| `StandardCharsets.UTF_16` | UTF-16 với quy tắc và BOM/byte order được xác định bởi charset |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian, dùng khi protocol quy định |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian, dùng khi protocol quy định |
| `StandardCharsets.ISO_8859_1` | Bảng mã 8 bit cho tập ký tự Latin-1 |
| `StandardCharsets.US_ASCII` | ASCII 7 bit; không biểu diễn toàn bộ Unicode |

**Với nội dung văn bản mới, UTF-8 thường là lựa chọn hợp lý.** Tuy nhiên nếu bạn phải đọc một file/giao thức quy định UTF-16LE hay ISO-8859-1, phải dùng **đúng mã mà nguồn dữ liệu đã dùng**. Không thể “sửa tiếng Việt lỗi font” bằng cách thử ngẫu nhiên các charset ở tầng UI.

### 3.1. `Charset.forName` có còn cần không?

`Charset.forName("UTF-8")` vẫn là API hợp lệ. Khi bảng mã đã biết ở lúc viết code, `StandardCharsets.UTF_8` rõ ràng hơn, tránh lỗi do gõ sai tên và không cần tra cứu tên động. `Charset.forName(name)` hữu ích khi `name` được lấy từ cấu hình/protocol, nhưng phải xử lý các giá trị không được hỗ trợ.

### 3.2. Vì sao nên luôn viết charset tường minh?

Các overload như `text.getBytes()` và `new String(bytes)` dùng **charset mặc định của môi trường Java**. Chính sách mặc định đã được chuẩn hóa theo UTF-8 từ Java 18 (JEP 400), nhưng ứng dụng có thể chạy phiên bản cũ, cấu hình đặc biệt hoặc tích hợp với hệ thống có quy ước khác. Dữ liệu bền vững và giao thức không nên phụ thuộc vào sự ngầm định này.

Do đó ưu tiên:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

thay cho:

```java
byte[] bytes = text.getBytes(); // Ngầm dùng default charset.
String decoded = new String(bytes); // Có thể không khớp nguồn.
```

Hai đoạn là **các snippet thay thế nhau**. Overload không chỉ định charset **chưa bị loại bỏ**, nhưng nó kém rõ ràng cho dữ liệu cần trao đổi. Yêu cầu của code hiện đại là làm rõ hợp đồng dữ liệu tại boundary.

## 4. Ví dụ thực thi: String ↔ byte[] bằng UTF-8

Lưu chương trình hoàn chỉnh thành `Utf8RoundTripDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class Utf8RoundTripDemo {
    public static void main(String[] args) {
        String text = "A\u00E9\u4E2D\uD83D\uDE42";
        byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(encoded, StandardCharsets.UTF_8);

        System.out.println("chars=" + text.length());
        System.out.println("codePoints=" + text.codePointCount(0, text.length()));
        System.out.println("bytes=" + encoded.length);
        System.out.println("hex=" + HexFormat.ofDelimiter(" ").withUpperCase()
                .formatHex(encoded));
        System.out.println("equal=" + text.equals(decoded));
        System.out.println("sameObject=" + (text == decoded));
    }
}
```

**Lưu ý:** `\u00E9`, `\u4E2D` và `\uD83D\uDE42` là các escape Unicode trong source Java để dễ tái lập các code points. Chúng tương ứng `é`, `中` và `🙂`. `HexFormat` là API có từ **Java 17**, nên lệnh build sau đặt target `--release 17`.

```bash
javac -encoding UTF-8 --release 17 Utf8RoundTripDemo.java
java Utf8RoundTripDemo
```

Stdout **đã được biên dịch và chạy kiểm chứng**:

```text
chars=5
codePoints=4
bytes=10
hex=41 C3 A9 E4 B8 AD F0 9F 99 82
equal=true
sameObject=false
```

### 4.1. Giải thích byte thực tế

Mỗi Unicode code point được encode theo số byte mà UTF-8 yêu cầu:

| Code point | UTF-8 (hex) | Số byte |
| --- | --- | --- |
| `U+0041` = A | `41` | 1 |
| `U+00E9` = é | `C3 A9` | 2 |
| `U+4E2D` = 中 | `E4 B8 AD` | 3 |
| `U+1F642` = 🙂 | `F0 9F 99 82` | 4 |
| **Tổng** | `41 C3 A9 E4 B8 AD F0 9F 99 82` | **10** |

`chars=5` vì emoji chiếm hai code unit UTF-16, còn `codePoints=4` vì emoji là một code point. `bytes=10` là độ dài biểu diễn UTF-8, không suy ra trực tiếp từ hai con số trước.

`equal=true` nghĩa là nội dung text khôi phục giống nội dung gốc khi encode và decode bằng UTF-8. `sameObject=false` nghĩa là đây không phải cùng một **tham chiếu String**; không dùng toán tử `==` để kiểm tra nội dung văn bản. Trong Java, dùng `String.equals` khi muốn so sánh giá trị.

### 4.2. `byte` có dấu nhưng có thể xuất hex chính xác

Nếu in trực tiếp bằng `Arrays.toString(encoded)`, một số byte có bit cao nhất bật sẽ hiển thị là số âm. Để quan sát **mẫu byte**, xuất hex như `HexFormat` ở Java 17. Nếu build target cũ hơn Java 17, có thể định dạng từng byte qua mask `b & 0xFF` và format `%02X`, nhưng phần cốt lõi chuyển đổi vẫn là `getBytes`/`new String` với `Charset`.

**Không được nhầm `javac -encoding UTF-8` với `String.getBytes(UTF_8)`.** Tùy chọn `-encoding` chỉ nói với **compiler** cách đọc file mã nguồn `.java`; `getBytes(StandardCharsets.UTF_8)` chỉ định cách chương trình chuyển **String khi chạy** sang byte. Đó là hai ranh giới độc lập.

## 5. Tại sao decode sai bảng mã tạo ra văn bản sai?

Encoding và decoding phải dùng **quy tắc tương thích**. Nếu nguồn tạo byte UTF-8 nhưng chương trình đích giải mã bằng ISO-8859-1, một dãy byte có thể vẫn được coi là hợp lệ nhưng biến thành các code points không như mong muốn.

Ví dụ `café`: UTF-8 cho byte `63 61 66 C3 A9`. Khi diễn giải `C3` và `A9` như hai ký tự Latin-1 riêng, chương trình tạo ra `U+00C3` và `U+00A9`, thay vì một `U+00E9`.

Lưu thành `CharsetMismatchDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.stream.Collectors;

public class CharsetMismatchDemo {
    public static void main(String[] args) {
        String expected = "caf\u00E9";
        byte[] bytes = expected.getBytes(StandardCharsets.UTF_8);
        String wrong = new String(bytes, StandardCharsets.ISO_8859_1);
        String restored = new String(bytes, StandardCharsets.UTF_8);

        System.out.println("bytes=" + Arrays.toString(bytes));
        System.out.println("wrongCodePoints=" + wrong.codePoints()
                .mapToObj(cp -> String.format("%04X", cp))
                .collect(Collectors.joining(" ")));
        System.out.println("wrongEqual=" + expected.equals(wrong));
        System.out.println("correctEqual=" + expected.equals(restored));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 CharsetMismatchDemo.java
java CharsetMismatchDemo
```

Stdout đã kiểm chứng:

```text
bytes=[99, 97, 102, -61, -87]
wrongCodePoints=0063 0061 0066 00C3 00A9
wrongEqual=false
correctEqual=true
```

**Rút ra:**

- Byte `0xC3` và `0xA9` hiển thị bằng `-61` và `-87` trong Java `byte[]`. Mẫu byte thực tế không bị thay đổi.
- `wrongCodePoints` có **5 code points** (hai code points cho phần cuối), trong khi chuỗi gốc có 4 code points.
- Việc decode bằng ISO-8859-1 không nhất thiết ném exception: bảng mã này ánh xạ được các byte nên có thể tạo ra **văn bản sai nhưng vẫn hợp lệ theo bảng mã đó**.
- Dùng đúng UTF-8 để giải mã, `correctEqual=true`.

**Khi debug lỗi tiếng Việt:** trước tiên xác định nơi dữ liệu trở thành byte, nơi byte trở thành String, charset của database/HTTP/file/console và liệu một tầng đã decode sai rồi encode lại hay chưa. Không nên gọi `new String(text.getBytes(...), ...)` với các charset thử ngẫu nhiên như một “phép sửa lỗi font” chung.

## 6. Dữ liệu byte không hợp lệ và chính sách xử lý lỗi

Một dãy byte có thể **không phải UTF-8 hợp lệ**. Ví dụ byte `C3` là phần đầu của một chuỗi UTF-8 hai byte, nhưng byte `28` không phải continuation byte hợp lệ.

Có hai lựa chọn thường dùng:

1. **Thay thế để tiếp tục:** các API tiện ích như `new String(bytes, StandardCharsets.UTF_8)` sẽ dùng ký tự thay thế khi gặp dữ liệu hỏng; lỗi có thể được che đi.
2. **Báo lỗi rõ:** dùng `CharsetDecoder` với `CodingErrorAction.REPORT` để phát hiện dữ liệu malformed hoặc unmappable, rồi xử lý tại ranh giới nhận dữ liệu.

Với dữ liệu có giá trị pháp lý, chữ ký số, giao thức nhị phân nghiêm ngặt hoặc đầu vào người dùng cần kiểm tra tính toàn vẹn, **không nên mặc định chấp nhận việc thay ký tự** nếu điều đó làm sai nội dung.

### 6.1. Phân biệt malformed và unmappable

- **Malformed input** là dãy byte (khi decode) hoặc dãy UTF-16 code units (khi encode) có cấu trúc không hợp lệ theo encoding. Ví dụ UTF-8 có byte mở đầu nhưng thiếu continuation byte.
- **Unmappable character** xảy ra khi input hợp lệ về mặt ký tự nhưng encoding đích không có biểu diễn. Ví dụ `é` không có byte tương ứng trong US-ASCII.

`CharsetDecoder` xử lý byte → char; `CharsetEncoder` xử lý char → byte. Hai loại đều có phương thức cấu hình `onMalformedInput(...)` và `onUnmappableCharacter(...)`.

### 6.2. Ví dụ chạy được: REPORT so với REPLACE

Lưu thành `StrictCodingDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.*;
import java.util.Arrays;

public class StrictCodingDemo {
    public static void main(String[] args) {
        byte[] malformed = {(byte) 0xC3, 0x28};
        String replacement = new String(malformed, StandardCharsets.UTF_8);

        System.out.println("replacementCodePoints=" +
                Arrays.toString(replacement.codePoints().toArray()));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(malformed));
        } catch (CharacterCodingException error) {
            System.out.println("decodeError=" + error.getClass().getSimpleName());
        }

        String source = "caf\u00E9";
        System.out.println("asciiReplace=" +
                Arrays.toString(source.getBytes(StandardCharsets.US_ASCII)));

        try {
            StandardCharsets.US_ASCII.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(source));
        } catch (CharacterCodingException error) {
            System.out.println("encodeError=" + error.getClass().getSimpleName());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 StrictCodingDemo.java
java StrictCodingDemo
```

Stdout đã kiểm chứng:

```text
replacementCodePoints=[65533, 40]
decodeError=MalformedInputException
asciiReplace=[99, 97, 102, 63]
encodeError=UnmappableCharacterException
```

**Giải thích từng kết quả:**

- `replacementCodePoints=[65533,40]` tương ứng `U+FFFD` (replacement character) và `U+0028` (dấu mở ngoặc). Đầu byte `C3` không thể giải mã đúng cùng `28`.
- `decodeError=MalformedInputException` xác minh lựa chọn strict decoder báo lỗi thay vì tự thay ký tự.
- Khi encode `café` bằng `US_ASCII` qua API tiện ích `getBytes`, ký tự `é` không biểu diễn được nên phần đó bị thay bằng byte `63` (ký tự `?`).
- Với `CharsetEncoder` cấu hình REPORT, Java ném `UnmappableCharacterException` cho ký tự `é` thay vì âm thầm thay `?`.

**Cách chọn theo sản phẩm:** Dữ liệu chứa lỗi có thể được cho phép **chỉ nếu** hợp đồng quy định replacement là chấp nhận được (ví dụ một preview chỉ để hiển thị và không ảnh hưởng quyết định). Với mã định danh, tài khoản, dữ liệu quan trọng hay giao thức yêu cầu chính xác, nên report và xử lý có kiểm soát.

### 6.3. Strict decoder để dùng trong ứng dụng

Ví dụ method chuyển mảng byte thành String và khai báo checked exception rõ ràng:

```java
static String decodeUtf8Strict(byte[] bytes)
        throws java.nio.charset.CharacterCodingException {
    java.nio.charset.CharsetDecoder decoder =
            java.nio.charset.StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
            .onUnmappableCharacter(java.nio.charset.CodingErrorAction.REPORT);

    return decoder.decode(java.nio.ByteBuffer.wrap(bytes)).toString();
}
```

Đây là **snippet method** cần được đặt trong một class, với `bytes` là tham số. `CharacterCodingException` là checked exception; caller cần bắt hoặc khai báo nó. Dùng một decoder mới cho mỗi công việc độc lập, hoặc quản lý lifecycle và state của decoder theo API. Không dùng chung một instance stateful để xử lý nhiều luồng dữ liệu đồng thời mà không kiểm soát.

**Không dùng `catch(Exception)` để đổi mọi lỗi decoding thành chuỗi rỗng**: lỗi đầu vào sẽ bị mất dấu, dễ tạo bản ghi sai hoặc bỏ qua dữ liệu ngoài ý muốn.

## 7. Dữ liệu UTF-8 đi qua nhiều khối byte: không được giải mã từng mảnh tùy ý

UTF-8 là encoding **có độ dài biến đổi**; một code point có thể dài 1–4 byte. Khi đọc từ mạng hoặc file thành các block, **ranh giới block không nhất thiết trùng ranh giới một ký tự**.

Nếu `é` được encode thành hai byte `C3 A9`, nhưng đầu vào bị chia thành block 1 chứa `C3` và block 2 chứa `A9`, việc gọi `new String(block1, UTF_8)` rồi `new String(block2, UTF_8)` riêng rẽ sẽ mất tính liên tục của ký tự.

### 7.1. Chương trình xác minh split UTF-8

Lưu thành `SplitUtf8Demo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class SplitUtf8Demo {
    public static void main(String[] args) {
        byte[] first = {(byte) 0xC3};
        byte[] second = {(byte) 0xA9};
        String incorrectlySeparated =
                new String(first, StandardCharsets.UTF_8)
              + new String(second, StandardCharsets.UTF_8);
        byte[] together = {(byte) 0xC3, (byte) 0xA9};
        String correct = new String(together, StandardCharsets.UTF_8);

        System.out.println("separate=" +
                Arrays.toString(incorrectlySeparated.codePoints().toArray()));
        System.out.println("combined=" +
                Arrays.toString(correct.codePoints().toArray()));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 SplitUtf8Demo.java
java SplitUtf8Demo
```

Stdout đã kiểm chứng:

```text
separate=[65533, 65533]
combined=[233]
```

`65533` là `U+FFFD`; `233` là `U+00E9`. Khi decode riêng từng fragment, mỗi fragment thiếu cấu trúc cần thiết nên Java dùng replacement hai lần. Khi ghép đủ dãy `C3 A9` rồi decode, kết quả đúng là `é`.

### 7.2. Cách xử lý đúng với luồng dữ liệu

Với dữ liệu văn bản có luồng byte, một lựa chọn thường dùng là `InputStreamReader`/`BufferedReader` (xem phần 8) để decoder giữ được trạng thái cần thiết giữa các lần đọc. Nếu cần streaming NIO ở mức thấp, dùng `CharsetDecoder` theo giao thức decode/incremental state của nó, xử lý `CoderResult`, `endOfInput` và `flush` chính xác.

Đừng tự tách `byte[]` thành các mảnh có kích thước cố định rồi decode từng mảnh thành một String độc lập nếu giao thức không bảo đảm mảnh kết thúc tại ranh giới code point. Đó là nguồn gây ký tự thay thế `�` ở cuối block dù dữ liệu toàn bộ hoàn toàn hợp lệ.

## 8. Đọc và ghi file văn bản theo charset tường minh

Đối với file, dùng API `Reader`/`Writer` thay vì tự ghép byte và char theo kiểu cast.

- `Reader` làm việc với các `char` UTF-16.
- `Writer` tiếp nhận `char` và thực hiện encode theo charset của writer ở ranh giới I/O.
- `InputStream`/`OutputStream` làm việc với raw byte, không biết tự động đó là UTF-8, ISO-8859-1 hay dữ liệu binary.
- `BufferedReader`/`BufferedWriter` thêm buffering cho thao tác ký tự và cần được đóng đúng cách bằng `try-with-resources` khi chúng sở hữu tài nguyên.

### 8.1. Ví dụ hoàn chỉnh: file UTF-8 qua `Files.newBufferedReader`/`newBufferedWriter`

Lưu thành `ReaderWriterCharsetDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReaderWriterCharsetDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("charset-demo-", ".txt");
        String source = "caf\u00E9";
        try {
            try (BufferedWriter out =
                    Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                out.write(source);
            }

            String loaded;
            try (BufferedReader in =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                loaded = in.readLine();
            }

            System.out.println("roundTrip=" + source.equals(loaded));
            System.out.println("fileBytes=" + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 ReaderWriterCharsetDemo.java
java ReaderWriterCharsetDemo
```

Stdout khi máy có quyền tạo file tạm:

```text
roundTrip=true
fileBytes=5
```

**Giải thích:**

- Writer encode `café` thành UTF-8, nên file có 5 byte.
- Sau khi writer đóng, reader mở file với **cùng charset UTF-8**, phục hồi String tương đương; `roundTrip=true`.
- `Files.newBufferedWriter` và `Files.newBufferedReader` cùng NIO.2 được giới thiệu từ **Java 7**, hiện vẫn áp dụng.
- `try-with-resources` đảm bảo writer/reader được đóng khi scope kết thúc, kể cả nếu phát sinh IOException.
- `finally` chỉ dọn **file tạm do chương trình tạo**, không phải để tự đóng writer/reader.
- In `roundTrip=true` kiểm tra văn bản, còn `Files.size(file)` kiểm tra **kích thước byte trên đĩa**; hai giá trị trả lời hai câu hỏi khác nhau.

**Cẩn trọng với file không tin cậy:** dữ liệu có thể chứa byte không hợp lệ; hãy đặt chính sách xử lý decode lỗi tương ứng với trách nhiệm của ứng dụng. Đừng cho rằng việc mở reader với một charset sẽ tự xác nhận file thuộc charset đó trong mọi trường hợp.

### 8.2. Tiện ích từ Java 11

Nếu muốn đọc/ghi toàn bộ nội dung file nhỏ thành một String, Java 11 bổ sung:

```java
String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);
```

Đây là **snippet** với `Path path`, `Files` và `StandardCharsets` đã import. Các method này giúp code gọn hơn, quản lý resource cần thiết bên trong, nhưng không phù hợp khi file lớn đến mức không nên nạp toàn bộ vào RAM.

**Phiên bản:** `try-with-resources` và `StandardCharsets` đã có từ Java 7; `Files.readString/writeString` từ Java 11. Bài sử dụng JDK 17+ nên cả hai kiểu API đều có thể dùng. Không nhầm “bài Java 7” với “mọi API trong ví dụ đều xuất hiện ở Java 7”.

## 9. `InputStreamReader` và `OutputStreamWriter`: cầu nối byte ↔ char

Khi nguồn/đích không phải file path mà là stream — ví dụ socket, HTTP body hoặc stream từ thư viện — bạn có thể dùng:

```java
try (java.io.Reader reader =
         new java.io.InputStreamReader(
             inputStream, java.nio.charset.StandardCharsets.UTF_8)) {
    // Đọc char từ byte stream qua decoder UTF-8.
}
```

và:

```java
try (java.io.Writer writer =
         new java.io.OutputStreamWriter(
             outputStream, java.nio.charset.StandardCharsets.UTF_8)) {
    // Ghi char qua encoder UTF-8 vào byte stream.
}
```

Đây là **snippets** với `inputStream`/`outputStream` có trước; không phải hai chương trình độc lập. `InputStreamReader` decode byte thành UTF-16 code units; `OutputStreamWriter` encode UTF-16 code units thành byte theo charset đã chỉ định. `BufferedReader`/`BufferedWriter` có thể bọc thêm để giảm số lần I/O hoặc cung cấp thao tác dòng.

### 9.1. Quyền sở hữu tài nguyên

Khi đặt wrapper vào `try-with-resources`, `close()` của wrapper thường đóng cả stream được bao bọc theo hợp đồng API. Điều này đúng nếu scope hiện tại **sở hữu** stream, nhưng không đúng nếu stream đang được **mượn** từ caller hoặc một framework muốn tiếp tục dùng nó.

Ví dụ với `System.in`: không tùy tiện tạo reader rồi đóng trong một method nhỏ nếu các chức năng phía sau còn cần đọc standard input. Cần thống nhất ownership và thời điểm kết thúc tài nguyên.

### 9.2. Chọn strict decoding khi cần

Nếu muốn lỗi byte hỏng được báo rõ thay vì thay ký tự, có thể truyền `CharsetDecoder` đã cấu hình REPORT vào constructor `InputStreamReader(InputStream, CharsetDecoder)`. Với stream lớn, đây là phương án có thể giữ cách decode đúng qua ranh giới giữa các lần read. `CharsetDecoder` có trạng thái; không nên tái sử dụng chung một đối tượng stateful giữa nhiều luồng chưa được đồng bộ.

### 9.3. Đừng coi `Reader.read()` trả về “một Unicode character đầy đủ”

`Reader.read()` và `Reader.read(char[])` làm việc theo **UTF-16 code units**, không tự trả trọn mọi grapheme cluster/code point trong một lần read. Với emoji hoặc ký tự bổ sung, hai surrogate code units có thể nằm qua các lần đọc. Nếu cần duyệt theo code point, xử lý đúng UTF-16 surrogate pairing sau khi lấy dữ liệu văn bản.

## 10. `Charset.encode`/`decode` với NIO buffers

Ngoài `String.getBytes`/constructor, `Charset` cung cấp convenience operations làm việc với `CharBuffer` và `ByteBuffer`:

```java
java.nio.ByteBuffer bytes =
    java.nio.charset.StandardCharsets.UTF_8.encode(
        java.nio.CharBuffer.wrap(text));

java.nio.CharBuffer chars =
    java.nio.charset.StandardCharsets.UTF_8.decode(bytes);
```

Đây là snippet với `String text` đã có. Điểm cần hiểu:

- `CharBuffer` chứa các **UTF-16 code units**; `ByteBuffer` chứa byte.
- `Charset.encode(...)`/`decode(...)` có thể sử dụng cơ chế replacement khi gặp dữ liệu không hợp lệ theo convenience API; dùng `newEncoder`/`newDecoder` cấu hình REPORT nếu cần kiểm tra chặt chẽ.
- Chỉ vùng **remaining** của buffer là dữ liệu cần quan tâm; không nên mặc định toàn bộ `capacity()` đều là nội dung đã ghi.
- Trạng thái `position`/`limit` của buffer quyết định phần dữ liệu có thể đọc được. Khi copy ra mảng, dùng `remaining()` và `get(...)` phù hợp thay vì lấy trực tiếp `buffer.array()` rồi cho rằng array có đúng length hoặc offset bằng 0.
- `ByteOrder.BIG_ENDIAN`/`LITTLE_ENDIAN` chủ yếu mô tả thứ tự byte của các lệnh đọc/ghi **giá trị số nhiều byte** trên ByteBuffer; nó không tự thay thế quyết định `UTF_8` hay `UTF_16LE` khi encode/decode văn bản.

### 10.1. Chọn Charset theo đặc tả ngoài

Nếu hệ thống nói “UTF-16LE”, hãy dùng `StandardCharsets.UTF_16LE`. Nếu hệ thống nói “UTF-8”, hãy dùng `StandardCharsets.UTF_8`. Các biến thể này **không tương đương** chỉ vì cùng mã hóa Unicode: chúng tạo byte khác nhau.

Khi làm việc với dữ liệu binary chứa cả số và text, cần thống nhất riêng:
- Endianness cho số nguyên/bộ nhớ.
- Charset cho phần text.
- Cách biểu diễn độ dài chuỗi (độ dài byte hay code point/UTF-16 unit).
- Cách nhận diện marker/BOM và chính sách lỗi.

Không nên gom mọi vấn đề này thành một tùy chọn “encoding” duy nhất.

## 11. BOM (Byte Order Mark) và byte đầu của file

Một số dữ liệu Unicode có thể chứa **BOM** (byte order mark), chẳng hạn chuỗi byte UTF-8 `EF BB BF` tương ứng ký tự `U+FEFF` ở đầu văn bản.

Trong UTF-8, BOM **không cần thiết** để xác định thứ tự byte; không nên tự thêm BOM cho một protocol chỉ quy định “UTF-8” nếu đặc tả không nói. Khi nhận dữ liệu ngoài, có thể có hoặc không có BOM; cần chính sách rõ cho việc chấp nhận, bỏ qua hoặc coi đó là nội dung.

### 11.1. Kiểm chứng với String UTF-8

Lưu thành `Utf8BomDemo.java`:

```java
import java.nio.charset.StandardCharsets;

public class Utf8BomDemo {
    public static void main(String[] args) {
        byte[] withBom = {(byte)0xEF, (byte)0xBB, (byte)0xBF, 0x41};
        String decoded = new String(withBom, StandardCharsets.UTF_8);
        System.out.println("chars=" + decoded.length());
        System.out.println("firstCodePoint=" +
                String.format("%04X", decoded.codePointAt(0)));
        System.out.println("endsWithA=" + decoded.endsWith("A"));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 Utf8BomDemo.java
java Utf8BomDemo
```

Stdout đã kiểm chứng:

```text
chars=2
firstCodePoint=FEFF
endsWithA=true
```

**Điều cần rút ra:** khi decode bằng `new String(bytes, UTF_8)`, ba byte BOM trong ví dụ **trở thành ký tự `U+FEFF` trong String**, không được tự động xóa. String có hai code units: `U+FEFF` và `A`. Nếu file format của ứng dụng cho phép BOM nhưng không coi nó là nội dung, hãy xử lý **ở ranh giới đọc** theo quy tắc rõ ràng; không tự xóa mọi ký tự U+FEFF xuất hiện bất kỳ đâu trong văn bản.

Với UTF-16, BOM có vai trò liên quan đến byte order tùy charset và giao thức. Khi protocol chỉ định rõ `UTF_16LE` hoặc `UTF_16BE`, không tùy tiện thay bằng `UTF_16` rồi giả định kết quả giống nhau ở mọi nguồn.

## 12. Unicode normalization là vấn đề khác encoding

Có thể tồn tại hai String **trông giống nhau** nhưng có dãy Unicode code point khác nhau. Chẳng hạn chữ `é` có thể được biểu diễn bởi:
- `U+00E9` (một code point dựng sẵn), hoặc
- `U+0065` theo sau `U+0301` (chữ `e` và dấu sắc kết hợp).

Cả hai đều có thể được encode đúng UTF-8, nhưng byte và kết quả `String.equals` có thể khác nhau. `Charset` **không tự chuẩn hóa Unicode** khi encode/decode.

Nếu ứng dụng thực sự cần so sánh hay chuẩn hóa văn bản theo một quy tắc Unicode normalization, Java có API `java.text.Normalizer`:

```java
String normalized =
    java.text.Normalizer.normalize(text, java.text.Normalizer.Form.NFC);
```

Đây là snippet với `String text` đã có. Cần chọn normalization có chủ đích cho bài toán tìm kiếm, lưu trữ, identifier hay so sánh; **không** dùng normalization để “sửa charset sai”. Normalization và character encoding là hai lớp xử lý độc lập.

## 13. Các lỗi phổ biến khi chuyển giữa byte và ký tự

| Sai lầm | Vì sao dễ gây lỗi | Cách đúng |
| --- | --- | --- |
| Ép trực tiếp `(char) someByte` để decode UTF-8 | Một ký tự UTF-8 có thể chiếm nhiều byte | `new String(bytes, UTF_8)` hoặc decoder |
| Ép `(byte) someChar` để encode | Làm mất dữ liệu vượt 8 bit | `String.getBytes(charset)` |
| Dùng `String.length()` làm số byte | `length` đếm code units UTF-16 | `getBytes(charset).length` nếu cần byte count |
| Coi một `char` là một code point hoàn chỉnh | Ký tự ngoài BMP cần surrogate pair | `codePoints()` hoặc `codePointAt` |
| Dùng `getBytes()` và `new String(bytes)` không charset | Phụ thuộc môi trường và hợp đồng ngầm | Chỉ định `StandardCharsets.UTF_8` hoặc charset đúng |
| Encode UTF-8, decode Latin-1 | Có thể tạo văn bản sai nhưng không ném lỗi | Dùng charset tương thích |
| Dùng convenience decoder cho dữ liệu phải chính xác tuyệt đối | Có thể âm thầm thay dữ liệu lỗi bằng `U+FFFD` | `CharsetDecoder` + `CodingErrorAction.REPORT` |
| Tưởng mọi ký tự đều biểu diễn được trong ASCII | ASCII có tập ký tự hạn chế | UTF-8 hoặc kiểm tra unmappable có chủ đích |
| Decode từng chunk mạng riêng rẽ | Có thể cắt giữa chuỗi byte của một code point | Dùng streaming decoder/Reader |
| Thấy byte âm là nghĩ dữ liệu sai | `byte` Java là signed | In hex hoặc `b & 0xFF` |
| Nhầm `javac -encoding` với charset runtime | Một cái đọc mã nguồn, cái kia xử lý dữ liệu khi chạy | Đặt cấu hình ở từng boundary |
| Tưởng `ByteBuffer.array()` luôn chứa đúng payload | Buffer có position/limit/offset/capacity | Dùng `remaining` và đọc vùng cần thiết |
| Tự xóa mọi `U+FEFF` | U+FEFF có thể là nội dung thực trong một ngữ cảnh | Xử lý BOM theo file/protocol |
| Tưởng normalize và encode là một | Normalization đổi hình thức code point, encoding đổi thành byte | Xử lý độc lập theo yêu cầu |
| Đưa raw stack trace cho người dùng vì decode lỗi | Lộ thông tin và khó hiểu | Trả lỗi dữ liệu có cấu trúc |
| Dùng `new String(rawBytes)` để “xem” mọi dữ liệu binary | Binary bất kỳ có thể không phải text | Chỉ decode khi có định dạng văn bản rõ |

### 13.1. Vì sao `(char) (byte)0xC3` không phải `é`?

`0xC3` là **byte đầu** trong hai byte UTF-8 biểu diễn `é`. Một phép cast số nguyên → `char` không có đủ thông tin để nhận biết code point, vì còn thiếu byte `0xA9`. Nó không áp dụng state machine hay cấu trúc UTF-8. Đây là lý do cần một decoder thực sự.

### 13.2. Vì sao một chuỗi “round-trip được” chưa chứng minh dữ liệu đúng?

Nếu bạn đã decode bằng charset sai, sau đó encode và decode lại bằng **chính charset sai ấy**, văn bản có thể vẫn round-trip thành công nhưng đã sai từ lúc tiếp nhận. Test tốt nên dùng **test vector byte chuẩn hoặc giá trị code point chuẩn** theo hợp đồng ngoài, không chỉ kiểm tra đầu ra của chính implementation với nó.

### 13.3. Lưu ý khi encode ký tự Java không hợp lệ

Một String Java có thể chứa một **unpaired surrogate** — code unit UTF-16 không tạo được một code point Unicode hoàn chỉnh. Khi dùng encoder convenience, dữ liệu malformed có thể bị thay thế; khi dùng `CharsetEncoder` strict với `REPORT`, có thể báo lỗi. Đừng nghĩ mọi chuỗi có thể được encode chính xác thành UTF-8 chỉ vì type của nó là `String`.

## 14. Thiết kế API rõ ràng: raw byte hay text?

Khi viết method, hãy xác định **tham số đang đại diện cho cái gì**.

**Nhận text khi caller đã decode hợp lệ:**

```java
void acceptMessage(String message) {
    // Xử lý văn bản đã được caller chuyển đổi.
}
```

**Nhận byte và charset nếu method chịu trách nhiệm decode:**

```java
String decodeMessage(byte[] input, java.nio.charset.Charset charset) {
    java.util.Objects.requireNonNull(input, "input required");
    java.util.Objects.requireNonNull(charset, "charset required");
    return new String(input, charset);
}
```

Hai đoạn là **snippet** trong một class phù hợp. Phiên bản thứ hai dùng convenience decoding với chính sách replacement; nếu đây là ranh giới cần dữ liệu chính xác, thay bằng `CharsetDecoder` strict.

### 14.1. Khi nào chỉ dùng `byte[]`?

Nếu dữ liệu là ảnh, PDF, file ZIP, checksum, encrypted payload hoặc các byte giao thức nhị phân khác, đừng biến thành `String` chỉ để truyền đi. Không có “UTF-8 String” đảm bảo round-trip mọi byte ngẫu nhiên theo cách diễn giải văn bản; lỗi malformed và replacement có thể làm mất dữ liệu.

Chỉ chọn `String` khi đầu vào được xác định là **văn bản có charset**. Khi phải truyền binary qua JSON/XML, cần một cách biểu diễn binary được quy định như Base64 (không phải character encoding của văn bản). `Base64` thuộc `java.util` từ Java 8 và vẫn hữu dụng, nhưng nó không thay thế UTF-8 đối với nội dung văn bản.

### 14.2. Hợp đồng giữa các tầng

Một boundary tốt nên quy định:
- Bảng mã sử dụng, ví dụ `UTF-8`.
- Có BOM hay không.
- Chính sách khi dữ liệu invalid: report hay replacement.
- Giới hạn byte/char/code point nếu ứng dụng cần.
- Có bước normalization hay không.
- Ai chịu trách nhiệm đóng Reader/Writer và xử lý lỗi I/O.
- Phương thức đo kích thước: số byte, UTF-16 code unit hay code point.
- Nếu là text trên HTTP, charset thuộc phần nào của content type/protocol và có được hai phía cùng tuân thủ không.

Không nên gói mọi thứ vào một hàm `convert(byte[])` không có tham số charset và không có tài liệu về lỗi.

## 15. Kiểm thử chuyển mã: nên kiểm tra những gì?

Một bộ test đủ mạnh cho API nhập/xuất văn bản nên bao gồm:

1. **ASCII đơn giản:** `"Hello"` → UTF-8 có 5 byte; round-trip bình thường.
2. **Ký tự Latin không ASCII:** `"café"` có `é` dài 2 byte UTF-8.
3. **CJK:** `中` dài 3 byte UTF-8.
4. **Unicode ngoài BMP:** emoji `🙂` dài 4 byte UTF-8, nhưng 2 `char` Java.
5. **Chuỗi rỗng:** encode thành `byte[0]`, decode thành `""`.
6. **Byte UTF-8 malformed:** decoder strict phải report lỗi; convenience decoder có thể replacement.
7. **Unmappable target:** `é` không biểu diễn được trong US-ASCII nếu không dùng replacement.
8. **Chunk boundary:** chia một ký tự UTF-8 đa byte qua hai lần đọc rồi kiểm chứng streaming đúng.
9. **Mismatch charset:** UTF-8 bytes decoded như Latin-1 phải được phát hiện bởi expected code points.
10. **BOM:** quyết định có chấp nhận/lược bỏ U+FEFF ở đầu không.
11. **Source code encoding:** test compile với `javac -encoding UTF-8` khi source chứa chữ tiếng Việt.
12. **File I/O:** đóng tài nguyên và xử lý IOException, không chỉ so sánh String.

**Đối với payload bên ngoài không tin cậy:** còn cần kiểm tra giới hạn kích thước, tránh parse quá lớn, không log raw dữ liệu riêng tư và xử lý rõ lỗi decode. Sự khác biệt giữa hiển thị văn bản hỏng có replacement và dữ liệu quan trọng cần chính xác phải thể hiện ngay trong test.

### 15.1. Các lệnh compile/run dùng chung cho các ví dụ

Mỗi chương trình `*.java` trong bài có `public class` trùng tên file. Nếu lưu cả sáu file vào một thư mục, có thể biên dịch cùng nhau với JDK 17:

```bash
javac -encoding UTF-8 --release 17 Utf8RoundTripDemo.java CharsetMismatchDemo.java StrictCodingDemo.java ReaderWriterCharsetDemo.java Utf8BomDemo.java SplitUtf8Demo.java
```

Sau đó chạy riêng từng class bằng `java <TênClass>` như hướng dẫn trong mỗi mục. `--release 17` giúp ví dụ `HexFormat` biên dịch theo đúng API Java 17. Nếu dự án target Java 8 hoặc 11, thay các tiện ích được thêm sau phiên bản đích (như `HexFormat`) nhưng các nguyên tắc encode/decode với `StandardCharsets` vẫn còn nguyên.

## 16. Câu hỏi thực hành và lời giải

**Câu 1.** `String.length()` và `String.getBytes(StandardCharsets.UTF_8).length` khác nhau ở đâu?  
**Đáp án:** `String.length()` đếm code units UTF-16; array length đếm byte UTF-8. Ký tự ngoài ASCII có thể chiếm nhiều byte và ký tự ngoài BMP cần hai code units.

**Câu 2.** Dãy `C3 A9` là một hay hai ký tự khi decode đúng UTF-8?  
**Đáp án:** Một code point `U+00E9` (`é`), được biểu diễn bởi hai byte.

**Câu 3.** Tại sao Java in byte `0xC3` thành `-61`?  
**Đáp án:** `byte` là số 8-bit có dấu. Giá trị -61 và byte hex C3 là cùng mẫu bit.

**Câu 4.** `new String(bytes, ISO_8859_1)` có luôn báo lỗi nếu bytes thực ra là UTF-8 không?  
**Đáp án:** Không. Nó có thể cho ra String hoàn toàn hợp lệ về mặt Latin-1 nhưng sai về ý nghĩa văn bản gốc.

**Câu 5.** Với String `"Aé中🙂"`, có bao nhiêu UTF-16 code units, code points và UTF-8 byte?  
**Đáp án:** 5 code units, 4 code points, 10 byte.

**Câu 6.** Khi decode UTF-8 hỏng, `new String(bytes, UTF_8)` và `CharsetDecoder` cấu hình REPORT có khác nhau không?  
**Đáp án:** Có. Constructor convenience có thể thay chuỗi byte malformed bằng `U+FFFD`; strict decoder báo `MalformedInputException`.

**Câu 7.** Tại sao encode `é` bằng US-ASCII có thể tạo byte `?`?  
**Đáp án:** Ký tự ấy không thuộc tập ASCII. Convenience encoder thay giá trị không biểu diễn được; strict encoder với REPORT báo `UnmappableCharacterException`.

**Câu 8.** Vì sao không decode hai block `{C3}` và `{A9}` riêng thành String rồi nối?  
**Đáp án:** Mỗi block là một phần không hoàn chỉnh của ký tự đa byte. Hãy giữ trạng thái decoder hoặc ghép đủ bytes trước khi decode.

**Câu 9.** Tham số `-encoding UTF-8` của `javac` có làm mọi `new String(bytes)` trong chương trình dùng UTF-8 không?  
**Đáp án:** Không. Nó chỉ điều khiển cách compiler đọc file `.java`. Encoding runtime vẫn do API được gọi quyết định.

**Câu 10.** `InputStream` và `InputStreamReader` khác nhau thế nào?  
**Đáp án:** InputStream cung cấp byte, InputStreamReader dùng charset để giải mã byte thành các UTF-16 code units cho API Reader.

**Câu 11.** UTF-8 BOM `EF BB BF` có chắc tự bị bỏ khi dùng `new String(bytes, UTF_8)` không?  
**Đáp án:** Không. Ví dụ trong bài cho thấy nó có thể trở thành `U+FEFF` trong String; quyết định bỏ hay giữ theo protocol.

**Câu 12.** Hai String trông giống nhau nhưng `equals` false có chắc do dùng sai charset không?  
**Đáp án:** Không. Có thể do Unicode normalization khác nhau, ký tự điều khiển, ký tự khoảng trắng hoặc nhiều nguyên nhân khác. Kiểm tra code points và encoding từng boundary.

**Câu 13.** Có nên dùng `new String(rawBinary, UTF_8)` để chứa dữ liệu ZIP/ảnh rồi chuyển lại byte không?  
**Đáp án:** Không. Binary không nhất thiết là UTF-8 hợp lệ; replacement có thể làm mất dữ liệu. Giữ `byte[]` hoặc dùng dạng biểu diễn binary được quy định.

**Câu 14.** Đọc file 100 MB bằng `Files.readString` có luôn tốt hơn Reader streaming không?  
**Đáp án:** Không. Chọn cách dựa trên khả năng bộ nhớ và yêu cầu xử lý: nếu file lớn, Reader streaming thường phù hợp hơn.

**Bài thực hành A — Code point:** Sửa `Utf8RoundTripDemo` để thêm chữ tiếng Việt và một emoji khác, dự đoán `length`, `codePointCount` và số byte trước khi chạy.

**Bài thực hành B — Sai bảng mã:** Trong `CharsetMismatchDemo`, đổi decoder sang `US_ASCII` rồi thử kiểm tra dữ liệu theo policy REPORT; giải thích khác nhau giữa malformed input và unmappable character.

**Bài thực hành C — Decoder strict:** Tạo thêm dãy byte UTF-8 đúng `E4 B8 AD` cho `中` và chuỗi thiếu continuation byte. Xác nhận strict decoder chỉ nhận dãy hợp lệ.

**Bài thực hành D — File:** Thay `source` trong `ReaderWriterCharsetDemo` bằng chuỗi gồm ASCII, tiếng Việt và emoji. Đo kích thước file và kiểm tra văn bản sau khi đọc có equals với nguồn.

**Bài thực hành E — Stream chunks:** Giả lập nhận một chuỗi UTF-8 thành các block nhỏ, rồi dùng `InputStreamReader` hoặc stateful `CharsetDecoder` để tái tạo String đúng mà không tự ý thay ký tự.

**Bài thực hành F — BOM và format:** Đọc một file UTF-8 có BOM do công cụ khác tạo, kiểm tra code point đầu tiên và quyết định chính sách theo đặc tả file thay vì áp dụng xóa BOM ở mọi nơi.

## 17. Tài liệu Java chính thức

- [Java SE 17 — Charset](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html): encode/decode và lookup character sets.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, UTF-16, ISO-8859-1, US-ASCII.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html) và [CharsetEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html): error actions và API chuyển mã chặt chẽ.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `getBytes(Charset)`, các constructor từ byte array, `codePointCount`.
- [Java SE 17 — InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) và [OutputStreamWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html): cầu nối giữa byte stream và char stream.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): đọc/ghi file có charset.
- [JEP 400 — UTF-8 by Default, Java 18](https://openjdk.org/jeps/400): chính sách default charset từ Java 18 và lý do vẫn nên chỉ định charset tường minh ở boundary.
- [Java SE 17 — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): xuất byte hex khi debug.

**Ghi nhớ:** `byte[]` chỉ là các byte; `String` là văn bản theo UTF-16 code units; `Charset` là **quy tắc bắt buộc** để chuyển qua lại một cách có ý nghĩa. Hãy encode bằng `text.getBytes(StandardCharsets.UTF_8)`, decode bằng `new String(bytes, StandardCharsets.UTF_8)` khi hợp đồng là UTF-8; với dữ liệu phải chính xác, dùng encoder/decoder strict. Đừng nhầm số byte với số `char`/code point, đừng decode UTF-8 theo các chunk cắt ngang ký tự, và đừng phụ thuộc default charset ngầm khi trao đổi dữ liệu giữa hệ thống.
