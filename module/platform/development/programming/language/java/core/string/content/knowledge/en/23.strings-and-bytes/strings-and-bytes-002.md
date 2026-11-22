# `String.getBytes(Charset)` với `Charset` và `StandardCharsets` trong Java

Trong Java, một `String` biểu diễn **văn bản Unicode**, còn `byte[]` là dãy byte để truyền qua mạng, ghi tệp hoặc đưa vào giao thức nhị phân. Để chuyển một chuỗi thành byte, chương trình phải chọn **bảng mã ký tự (character encoding / charset)**. Phương thức `getBytes(Charset)` thực hiện việc *encoding* (mã hóa văn bản thành byte); lựa chọn charset quyết định chính xác dãy byte đầu ra.

Bài này giải thích cách dùng `String.getBytes(Charset)` cùng `java.nio.charset.Charset` hoặc các hằng `java.nio.charset.StandardCharsets`, cách giải mã ngược, ảnh hưởng của charset, sự mất dữ liệu và những trường hợp cần kiểm soát lỗi mã hóa. Ví dụ dùng Java 17+.

## 1. Từ `String` sang `byte[]`: hai biểu diễn khác nhau

```java
import java.nio.charset.StandardCharsets;

String text = "Xin chào";
byte[] data = text.getBytes(StandardCharsets.UTF_8);
```

Lệnh trên dùng **UTF-8** để chuyển từng ký tự của `text` thành dãy byte. `data` là một mảng `byte[]` mới; đó **không phải** cùng một đối tượng hay cùng kiểu với `String`. Việc sửa các phần tử trong `data` không sửa chuỗi gốc.

Để chuyển lại thành văn bản, dùng charset tương ứng:

```java
String restored = new String(data, StandardCharsets.UTF_8);
boolean same = text.equals(restored); // true
```

Quy trình:

```text
String "Xin chào"
      │ getBytes(StandardCharsets.UTF_8)
      ▼
    byte[]                 (encoding)
      │ new String(bytes, StandardCharsets.UTF_8)
      ▼
String "Xin chào"          (decoding)
```

Quy tắc quan trọng: **bên mã hóa và bên giải mã phải thống nhất charset**. Byte không tự mang đầy đủ thông tin xác định đang dùng UTF-8, ISO-8859-1 hay UTF-16. Khi dùng charset khác ở hai đầu, kết quả có thể sai ký tự (*mojibake*) hoặc có dấu thay thế.

## 2. Cú pháp `getBytes`: nên dùng overload nào?

| API | Hành vi | Lưu ý |
| --- | --- | --- |
| `text.getBytes(StandardCharsets.UTF_8)` | Mã hóa với `Charset` được chọn tường minh. | **Cách ưu tiên** trong ứng dụng cần kết quả dự đoán được. |
| `text.getBytes(charset)` | Mã hóa với một biến kiểu `Charset`. | Phù hợp khi charset do cấu hình hoặc giao thức cung cấp. |
| `text.getBytes("UTF-8")` | Chọn charset bằng tên `String`. | Có thể ném checked exception `UnsupportedEncodingException`. |
| `text.getBytes()` | Dùng **default charset** của JVM. | Dễ phụ thuộc môi trường; nên tránh cho dữ liệu lưu trữ/giao tiếp cố định. |

Chữ ký chính cần biết:

```java
public byte[] getBytes(java.nio.charset.Charset charset)
```

- Đầu vào `charset` phải khác `null`; truyền `null` sẽ dẫn đến `NullPointerException`.
- Kết quả là mảng byte được mã hóa theo `charset`.
- Nếu chuỗi chứa đầu vào Unicode lỗi hoặc ký tự không biểu diễn được trong charset đã chọn, **overload `getBytes(Charset)` mặc định thay bằng chuỗi byte thay thế của charset**, chứ không mặc nhiên ném lỗi. Vì vậy có nguy cơ mất thông tin.
- Nếu yêu cầu **phát hiện lỗi** thay vì âm thầm thay thế, sử dụng `CharsetEncoder` được cấu hình `CodingErrorAction.REPORT` (mục 7).

Lưu ý lịch sử: `getBytes()` không tham số dùng default charset; trên Java 17 charset mặc định có thể phụ thuộc hệ thống. Từ Java 18, mặc định là UTF-8 theo JEP 400 trong cấu hình tiêu chuẩn, nhưng ứng dụng có thể chạy trên các môi trường và thiết lập khác. **Viết charset tường minh** vẫn là cách chắc chắn để đáp ứng một giao thức cụ thể.

## 3. `Charset` và `StandardCharsets`

`Charset` là kiểu biểu diễn một bộ quy tắc biến đổi giữa ký tự Unicode và byte (đồng thời cung cấp bộ mã hóa/giải mã). `StandardCharsets` chứa các **hằng `Charset` bảo đảm có sẵn** trên mọi triển khai Java chuẩn.

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset utf8 = StandardCharsets.UTF_8;
Charset anotherUtf8 = Charset.forName("UTF-8");
boolean equivalent = utf8.equals(anotherUtf8); // true
```

### Các hằng thông dụng

| Hằng | Đặc điểm | Tình huống |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode, độ dài 1–4 byte cho một Unicode code point hợp lệ; tương thích ASCII cho các ký tự ASCII. | Lựa chọn thường dùng cho API, JSON, tệp văn bản và dữ liệu đa ngôn ngữ. |
| `StandardCharsets.US_ASCII` | Chỉ biểu diễn các ký tự ASCII 7-bit. | Giao thức giới hạn bộ ký tự ASCII. |
| `StandardCharsets.ISO_8859_1` | Bảng mã một byte, biểu diễn Unicode U+0000–U+00FF. | Tương thích dữ liệu Latin-1 cũ. |
| `StandardCharsets.UTF_16` | Mã hóa UTF-16; Java tạo byte-order mark (BOM) theo quy định của charset này. | Khi giao thức yêu cầu UTF-16 kèm cơ chế nhận biết thứ tự byte. |
| `StandardCharsets.UTF_16BE` | UTF-16 big-endian, không tự thêm BOM khi encoding. | Dữ liệu nhị phân quy định big-endian rõ ràng. |
| `StandardCharsets.UTF_16LE` | UTF-16 little-endian, không tự thêm BOM khi encoding. | Dữ liệu nhị phân quy định little-endian rõ ràng. |

**UTF-8 khác UTF-16:** cùng một `String` có thể tạo số lượng byte khác nhau, vị trí byte khác nhau và BOM khác nhau. UTF-16BE/LE dùng 2 byte cho một UTF-16 code unit; code point bổ sung dùng một cặp surrogate, tương ứng 4 byte.

Dùng `StandardCharsets.UTF_8` thay `Charset.forName("UTF-8")` nếu tên charset đã biết tại thời điểm viết mã: rõ ý nghĩa, không nhập sai tên và không cần tra cứu bằng chuỗi.

### Khi tên charset đến từ cấu hình

```java
Charset charset = Charset.forName(configuredName);
byte[] payload = text.getBytes(charset);
```

Đây là **đoạn minh họa**, trong đó `configuredName` và `text` phải có sẵn. `Charset.forName(...)` có thể ném `IllegalCharsetNameException` nếu tên không hợp lệ hoặc `UnsupportedCharsetException` nếu tên hợp lệ nhưng không được hỗ trợ. Các charset ngoài tập hằng chuẩn có thể có trên một JDK nhưng vắng trên triển khai khác; hãy xác thực tên cấu hình.

## 4. Xem byte thực tế: cùng một chuỗi, nhiều charset

Xét chuỗi `"Aé€"` gồm ba ký tự: `A` (U+0041), `é` (U+00E9) và `€` (U+20AC). Ký tự `€` **không** thuộc tập có thể biểu diễn bằng ISO-8859-1.

| Charset | Byte đầu ra dạng hex | Ý nghĩa |
| --- | --- | --- |
| UTF-8 | `41 c3 a9 e2 82 ac` | `A` dùng 1 byte; `é` 2 byte; `€` 3 byte. |
| ISO-8859-1 | `41 e9 3f` | `A`, `é` được biểu diễn; `€` không có mã nên mặc định thay bằng `?` (`3f`) trong trường hợp này. |
| UTF-16BE | `00 41 00 e9 20 ac` | Ba code unit 16-bit theo thứ tự byte lớn trước. |
| UTF-16 | `fe ff 00 41 00 e9 20 ac` | Có BOM `fe ff` ở đầu theo quy tắc encoding `UTF_16`. |

Để kiểm tra dạng hex một cách dễ đọc trong Java 17+, có `java.util.HexFormat`:

```java
String text = "A\u00E9\u20AC";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

String hex = HexFormat.of().formatHex(bytes);
// "41c3a9e282ac"
```

Đoạn mã trên cần import `java.nio.charset.StandardCharsets` và `java.util.HexFormat`. `HexFormat` chỉ **biểu diễn byte thành chữ số hex để quan sát**, không thay đổi charset hay byte thật.

Không nên dùng `Arrays.toString(bytes)` để đọc byte dạng hex: Java `byte` là số có dấu từ -128 đến 127; chẳng hạn byte hex `c3` thường hiện là `-61` ở dạng số thập phân. Khi cần giá trị byte không dấu, có thể dùng `b & 0xFF`.

## 5. Chương trình Java 17+ biên dịch và chạy được

Tạo tệp `CharsetBytesDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetBytesDemo {
    public static void main(String[] args) {
        // Unicode escape giúp tệp nguồn không phụ thuộc cách nhập chữ đặc biệt.
        String text = "A\u00E9\u20AC"; // A, é, €

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        byte[] latin1 = text.getBytes(StandardCharsets.ISO_8859_1);
        byte[] utf16be = text.getBytes(StandardCharsets.UTF_16BE);

        System.out.println("UTF-8: " + HexFormat.of().formatHex(utf8));
        System.out.println("Latin-1: " + HexFormat.of().formatHex(latin1));
        System.out.println("UTF-16BE: " + HexFormat.of().formatHex(utf16be));

        String restored = new String(utf8, StandardCharsets.UTF_8);
        String latin1Restored = new String(
                latin1, StandardCharsets.ISO_8859_1);

        System.out.println("UTF-8 round trip: " + text.equals(restored));
        System.out.println("Latin-1 round trip: "
                + text.equals(latin1Restored));

        System.out.println("Latin-1 encodes euro: "
                + StandardCharsets.ISO_8859_1.newEncoder()
                        .canEncode("\u20AC"));

        // Emoji nằm ngoài BMP: 2 UTF-16 code units nhưng 4 byte UTF-8.
        String emoji = "A\uD83D\uDE00";
        System.out.println("Emoji example String.length: " + emoji.length());
        System.out.println("Emoji example UTF-8 bytes: "
                + emoji.getBytes(StandardCharsets.UTF_8).length);

        CharsetEncoder strict = StandardCharsets.ISO_8859_1.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            ByteBuffer encoded = strict.encode(CharBuffer.wrap(text));
            System.out.println("Strict bytes: " + encoded.remaining());
        } catch (CharacterCodingException e) {
            System.out.println("Strict Latin-1: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 CharsetBytesDemo.java
java CharsetBytesDemo
```

Kết quả:

```text
UTF-8: 41c3a9e282ac
Latin-1: 41e93f
UTF-16BE: 004100e920ac
UTF-8 round trip: true
Latin-1 round trip: false
Latin-1 encodes euro: false
Emoji example String.length: 3
Emoji example UTF-8 bytes: 5
Strict Latin-1: UnmappableCharacterException
```

Giải thích:

1. `getBytes(StandardCharsets.UTF_8)` giữ nguyên ý nghĩa cả ba ký tự; giải mã lại bằng cùng charset cho `true`.
2. ISO-8859-1 biểu diễn được `A` và `é`, nhưng không biểu diễn được `€`. Với `getBytes(Charset)`, ký tự không mã hóa được bị thay thế: giải mã xong không còn chuỗi ban đầu.
3. `CharsetEncoder.canEncode(...)` trả về `false` khi charset không mã hóa được `€`.
4. `CharsetEncoder` đặt `CodingErrorAction.REPORT` phát hiện lỗi và ném `UnmappableCharacterException`, cho phép chương trình dừng hoặc báo lỗi thay vì làm mất dữ liệu.
5. `"A😀"` có `String.length() == 3` vì gồm một code unit cho `A` và **hai UTF-16 code units** cho emoji, nhưng UTF-8 chỉ cần 1 + 4 = 5 byte.

## 6. Đo byte đầu ra của `getBytes(Charset)`

`String.length()` đếm đơn vị mã UTF-16, còn `getBytes(charset).length` đếm số byte **sau đúng lần encode đó**. Ví dụ `"A😀"` có `length() == 3` nhưng `getBytes(StandardCharsets.UTF_8).length == 5`. Nếu giao thức giới hạn payload byte, hãy dùng chính `byte[]` sắp được gửi:

~~~java
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
int byteCount = payload.length;
~~~

Đo byte của toàn bộ JSON/body **sau khi serialize** nếu lớp serialization còn có thể thêm escape hoặc metadata. Bài **Độ dài UTF-8 không bằng length của String** hướng dẫn tính giới hạn byte và cắt chuỗi theo code point.

## 7. Ký tự không biểu diễn được, dữ liệu lỗi và chính sách thay thế

### 7.1. `getBytes(Charset)` mặc định thay thế thay vì báo lỗi

Ví dụ `"€".getBytes(StandardCharsets.ISO_8859_1)` không thể biểu diễn đúng dấu euro. Với các hằng chuẩn trong chương trình trên, đầu ra mặc định có byte thay thế `3f` (dấu `?`). Khi đã thay thế, không thể phục hồi ký tự gốc chỉ nhờ giải mã cùng charset.

Cũng có thể xảy ra đầu vào Unicode không hợp lệ, ví dụ một `String` chứa **surrogate lẻ** không tạo thành cặp hợp lệ. `getBytes(Charset)` cũng dùng cách thay thế mặc định. Việc Java `String` lưu được một code unit dạng surrogate không đồng nghĩa đó là một chuỗi Unicode hợp lệ để encode.

Không suy rộng byte thay thế luôn là `3f` với **mọi** charset; thay thế do charset quyết định.

### 7.2. Cần từ chối thay vì thay thế: `CharsetEncoder`

Khi ký tự bị thay thế có thể gây sai dữ liệu nghiệp vụ, hãy mã hóa bằng encoder:

```java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    ByteBuffer result = encoder.encode(CharBuffer.wrap("Café"));
    // result chứa dãy byte nếu mọi ký tự đều hợp lệ cho ASCII.
} catch (CharacterCodingException e) {
    // Ghi nhận dữ liệu không mã hóa được và xử lý theo yêu cầu nghiệp vụ.
}
```

Đây là **đoạn minh họa**, cần import các lớp `java.nio.ByteBuffer`, `java.nio.CharBuffer`, `java.nio.charset.*`; chương trình đầy đủ ở mục 5 đã có một ví dụ runnable. Với ASCII, `é` không biểu diễn được nên nhánh `catch` được thực thi.

Các chính sách thường dùng của encoder/decoder:

- `CodingErrorAction.REPORT`: phát hiện và báo lỗi.
- `CodingErrorAction.REPLACE`: sử dụng replacement đã cấu hình.
- `CodingErrorAction.IGNORE`: bỏ qua dữ liệu lỗi, có thể mất nội dung.

Nếu yêu cầu dữ liệu không được mất ký tự, dùng `REPORT` và xử lý ngoại lệ rõ ràng.

### 7.3. Giải mã byte không hợp lệ

`new String(bytes, charset)` mặc định cũng thay thế chuỗi byte lỗi bằng ký tự thay thế khi cần. Chẳng hạn các byte `c3 28` không phải một chuỗi UTF-8 hợp lệ:

```java
byte[] broken = {(byte) 0xC3, (byte) 0x28};

String decoded = new String(broken, StandardCharsets.UTF_8);
// Chứa ký tự thay thế U+FFFD trước dấu "(".
```

Khi cần từ chối payload lỗi:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    String decoded = decoder.decode(ByteBuffer.wrap(broken)).toString();
} catch (CharacterCodingException e) {
    // Payload không phải UTF-8 hợp lệ; xử lý hoặc trả lỗi.
}
```

Đây cũng là **đoạn minh họa** và cần các import liên quan từ `java.nio.*`, `java.nio.charset.*`. Dùng `CharsetDecoder` nếu tính hợp lệ của byte đầu vào là yêu cầu bắt buộc; một phép giải mã tự thay thế không đủ để phát hiện lỗi.

## 8. Tình huống sử dụng trong ứng dụng

### 8.1. Gửi văn bản qua mạng hoặc tính kích thước request

```java
byte[] requestBody = jsonText.getBytes(StandardCharsets.UTF_8);
int contentLength = requestBody.length;
```

Đoạn này giả sử `jsonText` đã là **JSON hợp lệ**. `getBytes` chỉ mã hóa thành byte, **không tự escape chuỗi hay tạo JSON**. Truyền MIME/charset phù hợp, ví dụ `Content-Type: application/json; charset=utf-8` khi giao thức/ứng dụng yêu cầu; đừng tự thiết kế giao thức mà không xác nhận charset giữa các bên.

### 8.2. Ghi và đọc dữ liệu văn bản

```java
Path path = Path.of("message.txt");
String message = "Xin chào";
Files.writeString(path, message, StandardCharsets.UTF_8);
String readBack = Files.readString(path, StandardCharsets.UTF_8);
```

Ví dụ cần import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. Với luồng byte, cách tương đương về charset là ghi `message.getBytes(StandardCharsets.UTF_8)` vào tệp rồi giải mã các byte khi đọc. Ưu tiên `Files.writeString/readString` nếu mục đích thuần túy là I/O văn bản.

### 8.3. Dữ liệu theo giao thức yêu cầu bảng mã khác UTF-8

Khi giao thức yêu cầu Latin-1, ASCII hoặc UTF-16LE, hãy dùng chính charset được quy định:

```java
byte[] ascii = "OK".getBytes(StandardCharsets.US_ASCII);
byte[] utf16le = "OK".getBytes(StandardCharsets.UTF_16LE);
```

Cùng chữ `"OK"` nhưng `ascii` có hai byte `4f 4b`, còn `utf16le` có bốn byte `4f 00 4b 00`. **Không thay thế charset giao thức bằng UTF-8 theo cảm tính** khi phía nhận đã quy định định dạng.

## 9. Lỗi thường gặp và cách tránh

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `text.getBytes()` rồi giả định luôn là UTF-8 | Default charset có thể phụ thuộc phiên bản JVM/cấu hình. | Dùng `getBytes(StandardCharsets.UTF_8)`. |
| Encode UTF-8, decode bằng Latin-1 hoặc ngược lại | Các byte có ánh xạ ký tự khác nhau. | Ghi rõ charset và dùng nhất quán ở hai đầu. |
| Dùng `text.length()` làm số byte gửi đi | `String.length()` đo UTF-16 code units. | Dùng `encoded.length`. |
| Dùng ISO-8859-1 cho tiếng Việt, emoji hoặc ký tự ngoài Latin-1 | Không biểu diễn được nhiều ký tự; `getBytes(Charset)` có thể thay thế và mất dữ liệu. | Chọn charset phù hợp; nếu không được mất dữ liệu, dùng encoder với `REPORT`. |
| Nghĩ `byte` âm là lỗi encoding | Java `byte` có dấu; `-61` là cùng bit với byte hex `c3`. | Dùng `HexFormat` hoặc `b & 0xFF`. |
| Dùng `UTF_16` nhưng bên nhận chờ đúng UTF-16LE không BOM | UTF-16 mặc định có BOM và thứ tự byte theo charset. | Chọn đúng `UTF_16LE` / `UTF_16BE` theo giao thức. |
| Dùng `new String(bytes)` mà quên charset | Decoder dùng charset mặc định. | `new String(bytes, StandardCharsets.UTF_8)`. |
| Dùng `Arrays.toString(bytes)` làm chuỗi để truyền/ghi tệp | Đây là văn bản biểu diễn mảng, không phải dữ liệu byte gốc. | Gửi trực tiếp `byte[]` qua API byte, hoặc dùng encoding nhị phân sang văn bản như Base64 khi cần. |
| Dùng `getBytes` như giải pháp mã hóa bảo mật | Encoding ký tự không tạo tính bí mật hay xác thực. | Nếu cần bảo mật, dùng API mật mã phù hợp sau khi xác định byte đầu vào. |

### Cẩn thận khi dùng byte để so khớp hoặc băm nội dung

Hai chuỗi nhìn giống nhau có thể khác **chuỗi code points**, chẳng hạn `"\u00E9"` (một ký tự `é`) và `"e\u0301"` (`e` cộng dấu sắc kết hợp). Khi mã hóa UTF-8, byte của chúng khác nhau. Nếu hệ thống cần cách biểu diễn Unicode chuẩn hóa trước khi so sánh/băm/ký, có thể dùng `java.text.Normalizer` theo quy tắc cụ thể của giao thức trước khi gọi `getBytes`. Chỉ thực hiện chuẩn hóa khi đó là yêu cầu đã thống nhất; không âm thầm thay đổi dữ liệu gốc.

## 10. Tự kiểm tra

**Câu 1.** Vì sao `"A".getBytes(StandardCharsets.UTF_8).length == 1`, nhưng `"😀".getBytes(StandardCharsets.UTF_8).length == 4`?

**Trả lời:** UTF-8 dùng số byte biến thiên theo code point. ASCII `A` dùng một byte; emoji ngoài BMP `😀` dùng bốn byte.

**Câu 2.** Có thể dùng `getBytes(StandardCharsets.ISO_8859_1)` để chuyển mọi `String` Unicode mà không mất dữ liệu không?

**Trả lời:** Không. ISO-8859-1 chỉ biểu diễn một tập ký tự giới hạn. `getBytes(Charset)` thay thế ký tự không biểu diễn được; dùng charset khác như UTF-8 hoặc encoder `REPORT` để phát hiện.

**Câu 3.** Phần mềm nhận byte `41 c3 a9` từ nguồn ghi rõ UTF-8. Giải mã thế nào?

**Trả lời:** `new String(bytes, StandardCharsets.UTF_8)` tạo chuỗi `"Aé"` nếu mảng byte tương ứng đúng ba giá trị hex nêu trên.

**Câu 4.** Lúc nào chọn `StandardCharsets.UTF_8` và lúc nào chọn `Charset.forName(name)`?

**Trả lời:** Dùng hằng `StandardCharsets.UTF_8` nếu charset được xác định ngay trong mã. Dùng `Charset.forName(name)` nếu tên charset nhận động từ cấu hình/giao thức và có bước kiểm tra tên được hỗ trợ.

**Câu 5.** Vì sao `new String(text.getBytes(UTF_8), UTF_8)` không bảo đảm round-trip với **mọi** `String` Java có thể tạo?

**Trả lời:** Chuỗi có surrogate lẻ là đầu vào Unicode không hợp lệ; `getBytes(Charset)` có thể thay thế thay vì bảo toàn code unit đó. Với văn bản Unicode hợp lệ và charset UTF-8 ở cả hai đầu, round-trip bảo toàn nội dung.

## 11. Ghi nhớ khi áp dụng

- Xác định **charset theo đặc tả dữ liệu**, thường là UTF-8 nếu hai bên thống nhất.
- Encode với `text.getBytes(charset)` và decode với `new String(bytes, charset)`.
- Dùng `StandardCharsets` cho các charset phổ biến bảo đảm được Java hỗ trợ.
- Đừng đồng nhất độ dài `String` với độ dài `byte[]`; kiểm tra kích thước payload sau encoding.
- Khi không được phép mất hoặc thay thế ký tự, dùng `CharsetEncoder` / `CharsetDecoder` với `CodingErrorAction.REPORT`.

Tài liệu chuẩn Java 17: [`String.getBytes(Charset)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [`Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html), [`StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
