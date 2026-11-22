# Chuyển byte[] sang String bằng charset xác định trong Java

Khi đọc dữ liệu từ `ByteArrayOutputStream`, tệp nhỏ, socket, bộ nhớ đệm hoặc một API trả về `byte[]`, chương trình thường cần khôi phục **văn bản** dưới dạng `String`. Bước chuyển đổi tưởng như đơn giản nhưng chỉ đúng khi ta biết **những byte đó được mã hóa bằng charset nào** và xử lý rõ dữ liệu byte không hợp lệ.

Trong Java 17+, cách thông dụng là:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
```

Trong đó `bytes` là mảng `byte[]` đã chứa **dữ liệu văn bản mã hóa bằng UTF-8**, và `StandardCharsets.UTF_8` là charset đã được xác định theo hợp đồng dữ liệu. Mảnh mã cần `import java.nio.charset.StandardCharsets;`.

Bài này thuộc nhóm **I/O trong bộ nhớ**: chuyển mảng byte sang chuỗi, xác định đúng charset, hiểu lỗi khi giải mã sai, chọn hành vi khi byte không hợp lệ và biết khi nào cần xử lý theo luồng thay vì nạp toàn bộ dữ liệu.

## 1. Đừng nhầm byte với ký tự

Java `byte[]` là tập hợp các đơn vị 8 bit. Nó **không mang thông tin charset**; ví dụ các byte `C3 A9` tự nó không nói rằng chúng phải trở thành chữ `é`.

```text
String --mã hóa (encode bằng UTF-8)--> byte[]
   "é"                         C3 A9
                                    |
                              giải mã (decode bằng UTF-8)
                                    |
                                    v
                                  "é"
```

Nếu cùng byte `C3 A9` được giải mã theo ISO-8859-1, ta nhận hai ký tự tương ứng `Ã` và `©`, thường hiển thị thành `"Ã©"`. Vì vậy cùng một `byte[]` có thể cho các `String` khác nhau tùy charset.

Phân biệt ba khái niệm:

- **Byte:** đơn vị dữ liệu thô; `byte[]` chứa byte có thể là văn bản, ảnh PNG, file ZIP, mã hóa nhị phân hay dữ liệu nén.
- **Ký tự Java:** `String` sử dụng các đơn vị UTF-16; `char` là đơn vị 16 bit, còn một code point ngoài BMP có thể cần hai `char`.
- **Charset:** quy tắc biến một chuỗi ký tự thành byte và biến byte trở lại ký tự, ví dụ UTF-8, UTF-16, US-ASCII, ISO-8859-1.

Không có phép “ép kiểu” `(String) bytes` hợp lệ cho `byte[]`. Cũng không nên dùng `Arrays.toString(bytes)` để giải mã: phương thức này tạo **biểu diễn văn bản của các số byte**, như `[65, 66]`, chứ không tạo `"AB"`.

## 2. Constructor nên ưu tiên: new String(byte[], Charset)

Cú pháp:

```java
byte[] bytes = { 72, 101, 108, 108, 111 };
String text = new String(bytes, StandardCharsets.UTF_8);
System.out.println(text); // Hello
```

Đây là đoạn mã minh họa cần import `StandardCharsets`. Dữ liệu chỉ gồm ASCII nên khi giải mã UTF-8 mỗi byte tương ứng một ký tự như mong đợi.

API chính:

```java
new String(byte[] bytes, Charset charset)
new String(byte[] bytes, int offset, int length, Charset charset)
```

- `bytes`: mảng byte đầu vào cần giải mã.
- `charset`: bộ mã được chỉ định tường minh; thường dùng một hằng trong `StandardCharsets`.
- `offset`: **vị trí byte bắt đầu** trong mảng.
- `length`: **số byte phải giải mã**, không phải vị trí byte kết thúc, cũng không phải số ký tự sẽ tạo ra.
- Kết quả là một `String` mới chứa các đơn vị ký tự đã giải mã. Thay đổi mảng `bytes` sau đó không thay đổi nội dung của `String` đã tạo.
- `null` cho đối số bắt buộc và offset/length không hợp lệ sẽ làm thao tác thất bại; hãy kiểm tra đầu vào trước khi giải mã nếu chúng đến từ nguồn ngoài.

Cách viết này thể hiện **hợp đồng định dạng dữ liệu** ngay ở điểm chuyển đổi. Không trông chờ vào charset mặc định của máy chạy, cấu hình locale hoặc cách console đang hiển thị.

### Những charset thường gặp

| Charset | Đặc điểm | Khi nào dùng |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode, độ dài mỗi code point có thể từ 1 đến 4 byte | Mặc định hợp lý cho định dạng văn bản hiện đại, nếu protocol/file khai báo UTF-8 |
| `StandardCharsets.US_ASCII` | 7-bit ASCII | Giao thức giới hạn rõ trong ASCII |
| `StandardCharsets.ISO_8859_1` | Mỗi byte 0–255 ánh xạ sang một ký tự Unicode tương ứng | Dữ liệu legacy có hợp đồng Latin-1 |
| `StandardCharsets.UTF_16BE` | UTF-16 theo thứ tự byte big-endian, không tự phát BOM | Dữ liệu có quy định rõ UTF-16BE |
| `StandardCharsets.UTF_16LE` | UTF-16 theo thứ tự byte little-endian, không tự phát BOM | Dữ liệu có quy định rõ UTF-16LE |
| `StandardCharsets.UTF_16` | UTF-16 có quy tắc BOM và thứ tự byte theo đặc tả charset | Dữ liệu thực sự được khai báo UTF-16 |

**Không chọn ISO-8859-1 chỉ vì nó có thể giải mã mọi byte:** kết quả có thể là chuỗi ký tự sai nghĩa. Cũng không chọn UTF-8 một cách suy đoán nếu định dạng nguồn nói rõ một charset khác. Với charset không có trong `StandardCharsets`, dùng `Charset.forName("...")` khi tên đã được xác minh và nhà cung cấp runtime hỗ trợ; một tên sai hoặc không được hỗ trợ có thể gây lỗi tại bước lấy charset.

## 3. Vì sao phải ghi rõ charset?

Hai constructor sau không tương đương về mức độ xác định đầu ra:

```java
String implicit = new String(bytes);
String explicit = new String(bytes, StandardCharsets.UTF_8);
```

`new String(bytes)` dùng **charset mặc định** của môi trường Java. Trong Java 17, mặc định có thể phụ thuộc hệ điều hành/cấu hình. Từ Java 18, UTF-8 là mặc định theo JEP 400 trong cấu hình thông thường, nhưng mã cần trao đổi dữ liệu với hệ thống khác **vẫn nên khai báo charset rõ ràng**.

Tác hại của việc ngầm định:

1. Một file được ghi theo UTF-8 có thể đọc đúng trên máy A nhưng lỗi dấu trên máy B dùng charset mặc định khác.
2. Một chương trình chạy thành công trong IDE nhưng cho kết quả khác khi chạy job, container hoặc runtime cấu hình khác.
3. Phía nhận không thể xác định rõ vì sao byte trở thành ký tự; việc sửa lỗi khó khăn hơn.

Quy tắc bền vững: **nơi tạo byte và nơi đọc byte phải thống nhất charset bằng đặc tả dữ liệu**. Ví dụ, file cấu hình yêu cầu UTF-8 thì cả hai đầu dùng UTF-8; HTTP phải tôn trọng protocol và `Content-Type`/quy tắc tương ứng; một file legacy đã được quy định Windows-1252 thì phải sử dụng charset đó nếu runtime hỗ trợ.

## 4. Ví dụ Java 17+ hoàn chỉnh: từ String → byte[] → String

Tạo tệp `ByteArrayToStringDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.Locale;
import java.util.stream.Collectors;

public class ByteArrayToStringDemo {
    public static void main(String[] args) throws Exception {
        String original = "Ch\u00E0o Java \u2615";
        byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);

        System.out.println("UTF-8 bytes: " + utf8.length);
        System.out.println("Hex: "
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(utf8));

        String restored = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("Round trip: " + original.equals(restored));

        // Chỉ giải mã 3 byte từ vị trí 1: 41 C3 A9 = "Aé".
        byte[] frame = {
                0x21, 0x41, (byte) 0xC3, (byte) 0xA9, 0x3F
        };
        String slice = new String(frame, 1, 3, StandardCharsets.UTF_8);
        System.out.println("Slice A\u00E9: " + "A\u00E9".equals(slice));

        // Cùng 2 byte, nhưng một charset không đúng với nguồn.
        byte[] eAcute = { (byte) 0xC3, (byte) 0xA9 };
        String wronglyDecoded =
                new String(eAcute, StandardCharsets.ISO_8859_1);
        System.out.println("Wrong charset equal: "
                + "\u00E9".equals(wronglyDecoded));

        // C3 28 là UTF-8 lỗi; constructor String có chính sách thay thế.
        byte[] bad = { (byte) 0xC3, (byte) 0x28 };
        String forgiving = new String(bad, StandardCharsets.UTF_8);
        String points = forgiving.codePoints()
                .mapToObj(cp -> "U+" + Integer.toHexString(cp)
                        .toUpperCase(Locale.ROOT))
                .collect(Collectors.joining(" "));
        System.out.println("Decoded error code points: " + points);

        // Cùng dữ liệu lỗi, nhưng decoder nghiêm ngặt từ chối.
        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bad));
        } catch (CharacterCodingException e) {
            System.out.println("Strict decoder: "
                    + e.getClass().getSimpleName());
        }

        // Lấy byte[] từ OutputStream ghi trong bộ nhớ, rồi giải mã.
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (OutputStreamWriter writer =
                     new OutputStreamWriter(sink, StandardCharsets.UTF_8)) {
            writer.write("Hi \u2615");
        }
        System.out.println("BAOS toString Charset: "
                + "Hi \u2615".equals(sink.toString(StandardCharsets.UTF_8)));
    }
}
```

Biên dịch/chạy:

```bash
javac ByteArrayToStringDemo.java
java ByteArrayToStringDemo
```

Stdout đã đối chiếu với JDK:

```text
UTF-8 bytes: 14
Hex: 43 68 C3 A0 6F 20 4A 61 76 61 20 E2 98 95
Round trip: true
Slice Aé: true
Wrong charset equal: false
Decoded error code points: U+FFFD U+28
Strict decoder: MalformedInputException
BAOS toString Charset: true
```

Giải thích:

- `"Chào Java ☕"` có 14 byte UTF-8: `à` là `C3 A0`, còn ký hiệu `☕` là `E2 98 95`. `utf8.length` đếm byte nên khác số ký tự.
- Giải mã bằng cùng UTF-8 tạo chuỗi tương đương với chuỗi gốc; `original.equals(restored)` trả `true`.
- `frame` có hai byte đánh dấu ở hai đầu (`!` và `?`). Lệnh `new String(frame, 1, 3, UTF_8)` chỉ dùng ba byte `41 C3 A9`, tạo `"Aé"`; không kéo theo các byte ngoài vùng được chọn.
- Giải mã `C3 A9` bằng ISO-8859-1 không tạo đúng một ký tự `é`, nên so sánh trả `false`.
- Byte `C3` đứng trước `28` không tạo thành cặp UTF-8 hợp lệ. Constructor `String` với charset thay chuỗi lỗi bằng `U+FFFD` và vẫn giữ ký tự `(` là `U+28`.
- `CharsetDecoder` được cấu hình `REPORT` không chấp nhận dữ liệu đó, nên phát sinh `MalformedInputException`.
- `ByteArrayOutputStream` giúp kết nối trực tiếp bài học với **I/O trong bộ nhớ**: `OutputStreamWriter` mã hóa ký tự thành byte, còn `toString(StandardCharsets.UTF_8)` giải mã byte đã ghi.

Ví dụ cố ý in phần lớn kết quả dưới dạng số, hex hoặc boolean để không phụ thuộc khả năng hiển thị dấu tiếng Việt/emoji của terminal.

## 5. Giải mã một phần byte[]: offset và length là byte

Constructor:

```java
String text = new String(bytes, offset, length, charset);
```

Nó có ý nghĩa: bắt đầu tại chỉ số `offset` trong mảng, lấy **đúng `length` byte** và giải mã phần đó. Độ dài không phải `endIndex`, và không cho phép vượt biên mảng.

Ví dụ `byte[]` chứa:

```text
index: 0   1   2   3   4
byte:  21  41  C3  A9  3F
       !   A    \--é--/ ?
```

`new String(bytes, 1, 3, UTF_8)` nhận `41 C3 A9` và tạo `"Aé"`. Hai lệnh thường bị nhầm:

```java
new String(bytes, 1, 3, StandardCharsets.UTF_8); // bytes 1, 2, 3
new String(bytes, 1, 4, StandardCharsets.UTF_8); // bytes 1, 2, 3, 4
```

Dòng hai lấy bốn byte, bao gồm byte `3F` (`?`). **`offset + length` chỉ được đến `bytes.length`**, không được vượt. Nếu thông tin offset/length đến từ network hoặc cấu trúc dữ liệu chưa đáng tin, kiểm tra cẩn thận để tránh chỉ số âm, vượt biên hoặc overflow số nguyên. Cách kiểm tra khi các biến đều là `int`:

```java
if (offset < 0 || length < 0
        || offset > bytes.length
        || length > bytes.length - offset) {
    throw new IllegalArgumentException("Invalid byte slice");
}
String part = new String(bytes, offset, length, StandardCharsets.UTF_8);
```

Đây là **mảnh mã minh họa**, `bytes`, `offset`, `length` phải có sẵn.

### Không được cắt ở giữa một ký tự UTF-8

Ví dụ byte UTF-8 của `é` là `C3 A9`. Nếu cắt đúng một byte `C3` rồi gọi:

```java
new String(new byte[] { (byte) 0xC3 }, StandardCharsets.UTF_8);
```

Constructor không nhận đủ dữ liệu để tái tạo `é`; với quy tắc thay thế lỗi, nó sinh ký tự thay thế `U+FFFD`. Việc cắt phần mảng đúng về chỉ số **không đảm bảo đúng ranh giới ký tự**.

Cần phân biệt:

- Nếu định dạng chỉ ra **offset và length theo byte**, phải bảo đảm đó là những ranh giới hợp lệ của dữ liệu theo charset; hoặc dùng decoder tăng dần giữ phần byte dở cho chunk tiếp theo.
- Nếu muốn cắt **theo ký tự Java**, hãy giải mã đúng dữ liệu trước rồi thao tác trên `String`. Nếu cần cắt theo Unicode code point, dùng API `codePoint*` vì `String.substring` vẫn dùng vị trí UTF-16 và có thể cắt đôi cặp surrogate.
- Nếu dữ liệu gồm nhiều bản tin, lấy byte slice theo framing/độ dài bản tin thay vì cố dựa vào `String.length()`.

## 6. Byte[] trong bộ nhớ: những API cần biết

### 6.1. ByteArrayOutputStream → byte[] → String

`ByteArrayOutputStream` là một `OutputStream` ghi byte vào bộ đệm bộ nhớ. Khi đã ghi xong:

```java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.write(new byte[] { 65, 66, 67 });
byte[] bytes = out.toByteArray();
String text = new String(bytes, StandardCharsets.US_ASCII); // "ABC"
```

Đây là mảnh mã; cần `java.io.ByteArrayOutputStream` và `java.nio.charset.StandardCharsets`. `toByteArray()` **tạo bản sao** của các byte đang có trong buffer; kết quả không bao gồm phần dung lượng chưa sử dụng.

Java cũng có cách viết gọn:

```java
String text = out.toString(StandardCharsets.UTF_8);
```

`ByteArrayOutputStream.toString(Charset)` giải mã **toàn bộ byte hiện có trong bộ đệm** theo charset đã chọn, thuận tiện khi mục đích cuối cùng là `String`. Phương thức này có từ Java 10 và dùng được trong Java 17+. `out.toString()` không truyền charset lại phụ thuộc default charset, vì vậy không nên dùng cho nội dung trao đổi giữa môi trường khác nhau.

Một `ByteArrayOutputStream` có thể được đọc sau `close()` vì việc đóng loại stream này không làm nội dung bộ nhớ mất hiệu lực. **Không suy diễn rằng mọi OutputStream đều tiếp tục đọc/ghi được sau close.**

### 6.2. ByteArrayInputStream chứa byte, không tự biến thành String

`ByteArrayInputStream` đọc một mảng byte như nguồn stream:

```java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
try (ByteArrayInputStream in = new ByteArrayInputStream(bytes)) {
    byte[] allBytes = in.readAllBytes();
    String text = new String(allBytes, StandardCharsets.UTF_8);
}
```

Mảnh mã cần import `java.io.ByteArrayInputStream` và `java.nio.charset.StandardCharsets`. `InputStream.readAllBytes()` có từ Java 9. Cách này giúp quan sát luồng byte nhưng nếu **đã có mảng byte ban đầu**, có thể gọi trực tiếp `new String(bytes, UTF_8)`; tạo thêm `InputStream` rồi đọc lại chỉ để chuyển đổi là không cần thiết.

Khi cần xử lý luồng lớn hoặc dữ liệu từng phần, một `InputStreamReader(in, UTF_8)` có thể phù hợp hơn, vì nó chuyển byte sang ký tự trong quá trình đọc thay vì gom mọi byte thành một mảng lớn.

### 6.3. ByteBuffer khác byte[]

Khi dùng Java NIO, byte đọc về có thể nằm trong `ByteBuffer` với `position` và `limit`. Không giả định `buffer.array()` luôn tồn tại (direct/read-only buffer có thể không có mảng truy cập được), hoặc `array()` đúng bằng phần byte có hiệu lực. Chỉ các byte trong khoảng `position` đến `limit` mới là **remaining bytes** cần giải mã.

Ví dụ:

```java
ByteBuffer buffer = ByteBuffer.wrap(
        "OK".getBytes(StandardCharsets.UTF_8));
String text = StandardCharsets.UTF_8.decode(buffer).toString();
```

Đây là mảnh mã, cần import `java.nio.ByteBuffer` và `java.nio.charset.StandardCharsets`. `Charset.decode(ByteBuffer)` là hàm tiện ích có chính sách thay thế dữ liệu lỗi; nếu bắt buộc từ chối byte không hợp lệ, dùng một `CharsetDecoder` với `CodingErrorAction.REPORT`.

## 7. Charset sai tạo lỗi dấu: mojibake

Giả sử byte UTF-8:

```text
é → C3 A9 (UTF-8)
```

Giải mã bằng charset ISO-8859-1 thì:

```java
byte[] utf8 = { (byte) 0xC3, (byte) 0xA9 };
String right = new String(utf8, StandardCharsets.UTF_8);        // "é"
String wrong = new String(utf8, StandardCharsets.ISO_8859_1);  // "Ã©"
```

Đây là ví dụ độc lập về ánh xạ byte; charset ISO-8859-1 **vẫn giải mã thành các ký tự hợp lệ**, chỉ sai nghĩa đối với nguồn đã được mã hóa theo UTF-8. Vì vậy **không có exception** chỉ vì nội dung hiển thị sai dấu.

Khi nghi ngờ sai charset:

1. Xác định **nguồn tạo byte**, tài liệu định dạng, header hoặc metadata cung cấp charset gì.
2. Kiểm tra các byte thực tế bằng hex nếu cần; ví dụ `C3 A9` tương ứng UTF-8 `é`.
3. Đổi **charset tại bước giải mã byte** theo hợp đồng đúng; tránh sửa lỗi bằng chuỗi `replace(...)` dựa trên các ký tự đã hiển thị sai.
4. Nếu dữ liệu đã được đọc sai, còn **byte gốc** thì giải mã lại từ byte gốc. Nếu không còn byte gốc và nội dung đã qua các phép biến đổi mất thông tin, không phải lúc nào cũng khôi phục hoàn toàn được.
5. Không “dò charset” từ một byte[] ngắn rồi coi kết quả là chắc chắn. Nhiều charset cho các kết quả trông hợp lệ, nhất là dữ liệu chỉ có ASCII.

Mọi byte từ `0x00` đến `0x7F` của nội dung ASCII cơ bản đều được UTF-8 mã hóa giống US-ASCII; vì vậy test chỉ có `"ABC"` không chứng minh cách giải mã tiếng Việt là đúng. Hãy đưa vào dữ liệu có dấu, emoji hoặc ký tự nằm ngoài ASCII khi kiểm thử giao thức văn bản Unicode.

## 8. Dữ liệu UTF-8 không hợp lệ: constructor String có thể âm thầm thay thế

Đoạn byte:

```text
C3 28
```

là UTF-8 không hợp lệ, vì `C3` mở đầu một chuỗi hai byte nhưng `28` không phải continuation byte. Khi dùng:

```java
byte[] bad = { (byte) 0xC3, (byte) 0x28 };
String text = new String(bad, StandardCharsets.UTF_8);
```

Constructor `String(byte[], Charset)` **thay thế** chuỗi byte malformed/unmappable bằng ký tự thay thế được dùng trong giải mã, không ném `CharacterCodingException` cho lỗi đó. Trong UTF-8 của Java, chuỗi ở trên trở thành `U+FFFD` rồi `U+0028` (`(`).

Điều này hữu ích cho UI xem trước dữ liệu hỏng, nhưng là vấn đề khi:

- Định dạng yêu cầu **UTF-8 hợp lệ tuyệt đối**.
- Hệ thống ký/xác minh dữ liệu và cần giữ nguyên thông tin gốc.
- Tên file, identifier, trường giao thức hoặc dữ liệu quan trọng không được phép bị thay/loại bỏ ký tự.
- Phần mềm muốn báo chính xác bản tin/tệp nào có byte bị cắt cụt.

### Dùng CharsetDecoder để từ chối byte lỗi

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictUtf8Example {
    public static void main(String[] args) {
        byte[] bytes = { (byte) 0xC3, (byte) 0x28 };

        try {
            String text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
            System.out.println("Valid UTF-8: " + text);
        } catch (CharacterCodingException e) {
            System.out.println("Rejected: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Lưu `StrictUtf8Example.java` rồi chạy:

```bash
javac StrictUtf8Example.java
java StrictUtf8Example
```

Stdout:

```text
Rejected: MalformedInputException
```

`CharsetDecoder` mới tạo mặc định đã dùng `REPORT`, nhưng chỉ định cả hai nhóm lỗi làm rõ mục đích và giúp người đọc thấy điểm khác với constructor `String`. `MalformedInputException` và `UnmappableCharacterException` đều là `CharacterCodingException`. Khi dữ liệu lỗi, hãy trả về lỗi phù hợp; không lấy chuỗi đã bị thay ký tự rồi coi là đã xác thực thành công.

Đừng nhầm `new String(bytes, charset)` với `charset.newDecoder().decode(ByteBuffer.wrap(bytes))`: chúng khác nhau về **chính sách xử lý lỗi đầu vào**. `Charset.decode(ByteBuffer)` tiện ích trên `Charset` cũng dùng chế độ thay thế nên không thay cho strict decoder.

## 9. Một số byte không phải nội dung văn bản

Mảng byte trả về từ file hoặc API **có thể là dữ liệu nhị phân**, ví dụ ảnh JPEG/PNG, dữ liệu ZIP/GZIP, định dạng protobuf hoặc bản tin mã hóa. Đừng trực tiếp gọi `new String(binaryBytes, UTF_8)` rồi cố gắng dùng kết quả như một bản sao dữ liệu ban đầu:

- Không phải mọi chuỗi byte là UTF-8 hợp lệ.
- Khi giải mã lỗi bằng chế độ thay thế, nhiều chuỗi byte khác nhau có thể bị biến thành cùng ký tự `U+FFFD`.
- Mã hóa ngược `text.getBytes(UTF_8)` lúc đó **không thể bảo đảm thu lại byte ban đầu**.
- Dữ liệu nhị phân có byte `0`, byte điều khiển và các cấu trúc không tương ứng văn bản.

Nếu yêu cầu là **biểu diễn nhị phân an toàn bằng các ký tự ASCII để truyền/lưu dưới dạng text**, hãy dùng Base64 hoặc hex thay vì coi byte ngẫu nhiên là văn bản.

Ví dụ:

```java
byte[] binary = { 0x00, (byte) 0xFF, 0x10 };
String encoded = Base64.getEncoder().encodeToString(binary);
byte[] recovered = Base64.getDecoder().decode(encoded);
boolean exact = Arrays.equals(binary, recovered); // true
```

Đoạn minh họa cần import `java.util.Base64` và `java.util.Arrays`. Đây là **mã hóa biểu diễn nhị phân (binary-to-text)**, không phải charset UTF-8. Base64 không biến dữ liệu nhị phân thành văn bản Unicode có ý nghĩa và cũng không mã hóa bảo mật/encryption.

## 10. UTF-8 BOM và dữ liệu có tiền tố

Một số nguồn UTF-8 đặt **BOM** `EF BB BF` ở đầu nội dung. Giải mã các byte này bằng UTF-8 có thể tạo ký tự `U+FEFF` ở đầu chuỗi. Vì vậy nếu dự kiến chuỗi bắt đầu bằng `"ABC"` nhưng thực tế là `"\uFEFFABC"`, phép `startsWith("ABC")` thất bại.

Không nên tự xóa ba byte đầu mọi mảng dữ liệu:

- Không phải mọi tài liệu UTF-8 đều có BOM.
- Ba byte đầu có thể thuộc nội dung thật trong một protocol khác.
- Những charset khác như UTF-16 có quy tắc BOM khác.
- BOM được xử lý ra sao có thể phụ thuộc codec/API và định dạng file; phải đọc yêu cầu cụ thể của nguồn.

Chỉ khi đặc tả cho phép BOM và bộ đọc chưa xử lý BOM, có thể xét loại bỏ **ký tự `U+FEFF` đầu chuỗi** sau khi giải mã, với điều kiện ứng dụng không cần giữ nó như nội dung. Việc thay mọi `U+FEFF` trong toàn chuỗi là quá mức.

## 11. Đọc toàn bộ file vào bộ nhớ khi kích thước phù hợp

Nếu tệp văn bản đã có kích thước nhỏ, mã rõ ràng:

```java
Path path = Path.of("message.txt");
byte[] rawBytes = Files.readAllBytes(path);
String text = new String(rawBytes, StandardCharsets.UTF_8);
```

Đây là mảnh mã; cần import `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`, đồng thời xử lý `IOException`. `Files.readAllBytes` trả toàn bộ nội dung, sau đó `new String` giải mã. Nó đơn giản nhưng cần giữ **cả mảng byte và String** trong bộ nhớ, và sẽ dùng chính sách thay thế cho byte không hợp lệ.

Nếu file rất lớn, đường truyền liên tục, hay cần xử lý từng dòng, ưu tiên:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý một dòng rồi chuyển tiếp.
    }
}
```

Đoạn minh họa cần import `java.io.BufferedReader` và các lớp NIO nói trên, xử lý `IOException`. API reader giải mã trong khi đọc, tránh buộc ứng dụng tải toàn bộ file thành `byte[]`. Nếu cần kiểm soát nghiêm ngặt lỗi byte, hãy dùng `InputStreamReader` với `CharsetDecoder` cấu hình `REPORT`.

### ByteArrayOutputStream và String cho payload nhỏ

Khi ghi text ra `ByteArrayOutputStream`, có hai chiều:

```text
String --OutputStreamWriter(UTF-8)--> ByteArrayOutputStream
                                          |
                                      toByteArray()
                                          |
                                          v
                                      byte[] UTF-8
                                          |
                                      new String(bytes, UTF-8)
                                          |
                                          v
                                        String
```

Đây là cấu trúc hữu ích trong unit test, ví dụ khi cần xác minh kết quả text mà một API tạo ra từ `OutputStream`. Nếu chỉ cần so sánh byte chính xác (giao thức, chữ ký), hãy so sánh `byte[]` trước khi giải mã; nếu muốn so sánh nội dung text, giải mã đúng charset rồi so sánh `String`.

## 12. Hiệu năng, sao chép và tính bất biến

- Constructor `new String(bytes, charset)` tạo ra đối tượng `String` từ dữ liệu đã giải mã. Không nên giả định rằng nó là một “view” trực tiếp lên `byte[]`: thay mảng byte sau đó không làm `String` thay đổi.
- Việc giải mã có chi phí CPU và cấp phát bộ nhớ; không nên decode đi decode lại cùng một byte[] trong vòng lặp nóng chỉ để kiểm tra một điều kiện có thể xử lý tốt hơn ở tầng byte.
- `String.length()` trả số **đơn vị UTF-16**, không phải byte input. `"é"` có một đơn vị `char` nhưng hai byte UTF-8; emoji ngoài BMP có hai `char` và bốn byte UTF-8.
- `bytes.length` là độ dài byte sau khi mã hóa hoặc lấy từ nguồn; nếu cần độ dài chính xác của một bản tin trong UTF-8, hãy tính trên **dữ liệu đã mã hóa**, không dùng `text.length()`.
- Không dùng `new String(bytes, charset)` như một phép xác minh round-trip nếu nguồn có thể chứa chuỗi byte không hợp lệ và việc mất byte là không chấp nhận được: dùng strict decoder trước.
- Để xử lý các đoạn byte đọc theo chunk, đừng decode độc lập mỗi chunk bằng constructor `String` nếu có khả năng cắt đôi ký tự đa byte. Dùng decoder tăng dần hoặc `InputStreamReader` để giữ trạng thái qua ranh giới chunk.

Ví dụ lỗi chia khối:

```text
Byte UTF-8 của "é": C3 A9
Chunk #1: C3
Chunk #2: A9

new String(chunk1, UTF_8) + new String(chunk2, UTF_8)
→ không bằng "é" (hai chunk đều thiếu dữ liệu phù hợp).

Giải mã cả C3 A9 một lần hoặc giữ trạng thái decoder giữa chunk
→ "é".
```

## 13. Những lỗi phổ biến và cách sửa

| Sai lầm | Vấn đề | Cách đúng |
| --- | --- | --- |
| `new String(bytes)` cho dữ liệu trao đổi | Phụ thuộc charset mặc định | `new String(bytes, StandardCharsets.UTF_8)` hoặc charset thực theo hợp đồng |
| Giải mã UTF-8 bytes bằng ISO-8859-1 | Mojibake, sai dấu mà có thể không ném exception | Xác nhận và dùng charset ban đầu |
| Coi `byte[]` bất kỳ là text | Dữ liệu nhị phân bị mất khi đi qua String | Giữ byte nguyên vẹn; Base64/hex nếu cần biểu diễn text |
| Dùng `Arrays.toString(bytes)` để lấy văn bản | Ra biểu diễn số byte | `new String(bytes, charset)` |
| Dùng `String.length()` làm kích thước payload | Sai số byte, có thể cắt giữa ký tự | Tính độ dài byte sau mã hóa |
| Truyền `length` như end-index | Giải mã sai phạm vi hoặc vượt mảng | `length` là số byte tính từ `offset` |
| Cắt giữa các byte UTF-8 rồi giải mã độc lập | Sinh `U+FFFD` hoặc lỗi | Giữ ranh giới ký tự/decoder tăng dần |
| Dùng constructor String để kiểm tra UTF-8 hợp lệ | Malformed byte có thể bị thay | `CharsetDecoder` với `REPORT` |
| Giả định lỗi dấu sẽ luôn có exception | Nhiều charset tạo chuỗi hợp lệ nhưng sai nghĩa | Dựa trên metadata/protocol và kiểm tra hex |
| Gọi `toString()` của `byte[]` | Kết quả tên kiểu và địa chỉ/hash biểu diễn, không phải nội dung | `new String(bytes, charset)` |
| Quên đóng stream/reader tệp | Rò tài nguyên | `try-with-resources` |
| Đọc file lớn bằng `readAllBytes` rồi decode | Tăng áp lực bộ nhớ | `BufferedReader`/`InputStreamReader` đọc dần |
| Xóa BOM bất kể nguồn | Làm hỏng dữ liệu hoặc mất nội dung | Áp dụng chính sách BOM theo định dạng thực |

## 14. Câu hỏi kiểm tra

1. **Mảng `byte[]` có charset riêng không?** Không. Nó chỉ chứa byte; charset do định dạng hoặc thỏa thuận bên ngoài xác định.
2. **Cách chuyển byte UTF-8 sang String ổn định?** `new String(bytes, StandardCharsets.UTF_8)`.
3. **Vì sao `C3 A9` có thể thành `"é"` hoặc `"Ã©"`?** Vì UTF-8 và ISO-8859-1 diễn giải cùng byte theo quy tắc khác nhau.
4. **`new String(bytes, 2, 5, UTF_8)` lấy các chỉ số nào?** Năm byte ở chỉ số 2, 3, 4, 5, 6; số 5 là chiều dài.
5. **Điều gì xảy ra nếu mảng chỉ có byte đầu `C3` của chữ `é`?** Giải mã UTF-8 bằng constructor String sẽ thay đoạn byte lỗi/bị cắt, không tạo chữ `é`.
6. **Làm sao từ chối byte UTF-8 sai?** Dùng `UTF_8.newDecoder()` và `CodingErrorAction.REPORT`, bắt `CharacterCodingException`.
7. **`ByteArrayOutputStream.toByteArray()` trả gì?** Bản sao các byte đã ghi trong buffer.
8. **`ByteArrayOutputStream.toString(Charset)` có ý nghĩa gì?** Giải mã nội dung byte của bộ đệm theo charset chỉ định.
9. **Có thể gọi `new String(binary, UTF_8)` để giữ byte ZIP/ảnh nguyên vẹn không?** Không; byte không đại diện văn bản có thể mất thông tin. Giữ byte hoặc dùng Base64 khi cần văn bản biểu diễn.
10. **Vì sao không decode từng chunk mạng bằng `new String(chunk, UTF_8)`?** Chunk có thể chia đôi dãy byte của một ký tự Unicode.
11. **`String.length()` có bằng `bytes.length` không?** Không nhất thiết; mã hóa có thể dùng nhiều byte cho một code point.
12. **Giải mã sai charset có luôn ném exception?** Không. Kết quả có thể chỉ sai nghĩa nhưng vẫn là chuỗi Unicode hợp lệ.

## Tham khảo API Java 17

- [`String` constructors — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
- [`StandardCharsets` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [`Charset` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html).
- [`CharsetDecoder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [`ByteArrayOutputStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html).
- [`Files` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [`InputStreamReader` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html).

**Ghi nhớ:** `byte[]` chỉ là byte thô; ý nghĩa văn bản xuất hiện khi chọn đúng charset. Dùng `new String(bytes, charset)` cho dữ liệu văn bản hợp lệ, `new String(bytes, offset, length, charset)` cho đúng phần byte và `CharsetDecoder` với `REPORT` khi dữ liệu sai cần bị từ chối thay vì âm thầm thay ký tự.
