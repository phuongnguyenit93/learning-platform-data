# Unicode, UTF-8, UTF-16 và các charset thường gặp

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích khác biệt giữa **Unicode**, **code point**, **code unit**, **byte**, **glyph** và **grapheme cluster**; đọc được quy tắc mã hóa UTF-8/UTF-16; lựa chọn charset khi đọc/ghi văn bản Java; nhận biết BOM, endianness, văn bản lỗi mã hóa (*mojibake*), dữ liệu Unicode không hợp lệ và vấn đề chuẩn hóa; đồng thời sử dụng API Java 17 để xử lý văn bản an toàn.

**Điểm cốt lõi:** Unicode xác định các mã số và thuộc tính ký tự; **UTF-8/UTF-16 là các cách mã hóa** Unicode để lưu trữ và truyền dữ liệu. Không thể nhìn vài byte tùy ý rồi khẳng định đó là một chuỗi văn bản đúng nếu chưa xác định cách giải mã.

## 1. Những khái niệm phải tách bạch

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Character (ký tự)** | Khái niệm chữ/ký hiệu trong văn bản; ý nghĩa phụ thuộc ngữ cảnh | chữ `é`, chữ `A`, emoji |
| **Unicode code point** | Giá trị nguyên được ký hiệu `U+XXXX`, từ `U+0000` đến `U+10FFFF` | `U+0041` là `A`; `U+1F600` là 😀 |
| **Unicode scalar value** | Code point **trừ** vùng surrogate `U+D800..U+DFFF` | `U+1F600` hợp lệ; `U+D83D` tự nó không phải scalar value |
| **Code unit** | Đơn vị mà một encoding dùng để biểu diễn chuỗi | UTF-8: 8 bit; UTF-16: 16 bit; UTF-32: 32 bit |
| **Byte** | Đơn vị 8 bit trong dữ liệu tệp/mạng | `0xC3`, `0xA9` là hai byte UTF-8 của `é` |
| **Grapheme cluster** | Cụm ký tự người đọc thường xem là một ký tự hiển thị | `e` + dấu sắc kết hợp có thể hiển thị thành “é” |
| **Glyph** | Hình dạng vẽ ra bởi font/rendering engine | Một code point có thể có nhiều hình dạng; một glyph có thể đại diện nhiều code point |
| **Charset / character encoding** | Quy tắc chuyển giữa chuỗi ký tự và chuỗi byte | UTF-8, UTF-16LE, windows-1252, Shift_JIS |

**Một ký tự nhìn thấy được không nhất thiết bằng một code point, một `char`, hay một byte.** Ví dụ chữ “é” có thể được biểu diễn bằng `U+00E9` (ký tự dựng sẵn) hoặc bằng `U+0065 U+0301` (chữ e và dấu sắc kết hợp). Hai chuỗi có thể giống nhau khi hiển thị nhưng không bằng nhau khi so sánh code point.

Unicode có cả các code point chưa gán; “nằm trong khoảng `U+0000..U+10FFFF`” không tự bảo đảm đó là ký tự được gán hoặc hợp lệ để sử dụng ở mọi ngữ cảnh. **Surrogate code point** nằm trong `U+D800..U+DFFF` được dành riêng cho biểu diễn UTF-16, không được mã hóa riêng lẻ thành chuỗi UTF-8 hợp lệ.

### Mối quan hệ dữ liệu trong chương trình

```text
Văn bản ở mức khái niệm
  ↓ chọn chuỗi Unicode code point / scalar values
Chuỗi code point
  ↓ dùng charset/encoding cụ thể
Dãy code unit
  ↓ sắp xếp byte theo encoding và byte order (nếu có)
Dãy byte trên file/network
  ↓ dùng cùng encoding để giải mã
Chuỗi code point → text render với font, layout, normalization...
```

Đường đi từ text sang byte được gọi là **encoding**; chiều ngược lại là **decoding**. Một decoder phải biết charset (từ chuẩn giao thức, metadata, header, BOM hay cấu hình đã thỏa thuận). Suy đoán charset từ byte chỉ là heuristic, không thể chắc chắn với mọi đầu vào.

## 2. UTF-8: biến độ dài, tương thích ASCII

UTF-8 biểu diễn một Unicode scalar value bằng **1–4 byte**. Số byte phụ thuộc dải code point:

| Dải Unicode scalar value | Byte UTF-8 | Mẫu bit |
|---|---:|---|
| `U+0000..U+007F` | 1 | `0xxxxxxx` |
| `U+0080..U+07FF` | 2 | `110xxxxx 10xxxxxx` |
| `U+0800..U+FFFF` (trừ surrogate) | 3 | `1110xxxx 10xxxxxx 10xxxxxx` |
| `U+10000..U+10FFFF` | 4 | `11110xxx 10xxxxxx 10xxxxxx 10xxxxxx` |

Các bit `x` chứa giá trị code point. Byte tiếp diễn có tiền tố `10`. Decoder UTF-8 chuẩn phải **từ chối** chuỗi quá dài so với dạng ngắn nhất (*overlong encoding*), byte tiếp diễn không đúng, các giá trị surrogate và giá trị lớn hơn `U+10FFFF`.

Ví dụ cụ thể:

| Văn bản | Code point | Byte UTF-8 (hex) | Độ dài |
|---|---|---|---:|
| `A` | `U+0041` | `41` | 1 |
| `é` | `U+00E9` | `C3 A9` | 2 |
| `中` | `U+4E2D` | `E4 B8 AD` | 3 |
| 😀 | `U+1F600` | `F0 9F 98 80` | 4 |

ASCII chuẩn dùng byte `00..7F`, nên text chỉ chứa các ký tự ASCII có cùng byte ở UTF-8. Đây là lý do UTF-8 phổ biến trong giao thức, source code, JSON và hệ thống tệp hiện đại. **Nhưng** byte `0xE9` đơn lẻ (ký tự é trong ISO-8859-1) không phải một chuỗi UTF-8 hoàn chỉnh.

UTF-8 **không có byte order**; UTF-8 BOM tùy chọn là chuỗi `EF BB BF` biểu diễn `U+FEFF` ở đầu file. BOM UTF-8 đôi khi giúp công cụ cũ nhận dạng encoding, nhưng nhiều giao thức/công cụ không cần hoặc không mong đợi BOM. Không thêm BOM nếu định dạng không cho phép. Trên Java, khi decode `EF BB BF` bằng `StandardCharsets.UTF_8`, `U+FEFF` có thể tồn tại trong `String`; đừng mặc nhiên tin mọi API sẽ tự loại bỏ nó.

UTF-8 là mã hóa Unicode, **không phải mã hóa luôn ra một byte cho mỗi chữ**. Nếu ghi chiều dài payload cho HTTP/socket/file nhị phân thì phải đếm **byte sau encoding**, không dùng `String.length()`.

## 3. UTF-16: code unit 16 bit, surrogate pair

UTF-16 dùng các **code unit 16 bit**, mỗi đơn vị tương ứng **2 byte**.

- Với Unicode scalar value từ `U+0000` đến `U+FFFF` ngoài vùng surrogate (BMP), UTF-16 thường dùng **một code unit**.
- Với giá trị từ `U+10000` đến `U+10FFFF`, UTF-16 dùng **surrogate pair**, gồm *high surrogate* (`D800..DBFF`) và *low surrogate* (`DC00..DFFF`), tổng cộng **hai code unit = 4 byte**.
- Một high surrogate không đi kèm low surrogate đúng cách, hoặc low surrogate đứng đơn độc, là **chuỗi UTF-16 sai cấu trúc** khi được diễn giải như văn bản Unicode.

Ví dụ 😀 = `U+1F600` trở thành cặp `D83D DE00` trong UTF-16. Chuyển code point `U+10000` trở lên thành surrogate pair có thể hiểu bằng cách:

1. Lấy `U = codePoint - 0x10000`.
2. High surrogate = `0xD800 + (U >> 10)`.
3. Low surrogate = `0xDC00 + (U & 0x3FF)`.

Ví dụ này giải thích vì sao một emoji có thể chiếm **hai vị trí `char` trong Java**, dù là một code point Unicode.

### Endianness và BOM của UTF-16

| Encoding | Byte của `A` (`U+0041`) | Byte của 😀 (`U+1F600`) |
|---|---|---|
| `UTF-16BE` | `00 41` | `D8 3D DE 00` |
| `UTF-16LE` | `41 00` | `3D D8 00 DE` |
| `UTF-8` | `41` | `F0 9F 98 80` |

**BE** (*big-endian*) lưu byte cao trước; **LE** (*little-endian*) lưu byte thấp trước. `UTF-16` không chỉ rõ BE/LE ở tên có thể dùng BOM `FE FF` (BE) hoặc `FF FE` (LE) để nhận diện; khi không có BOM, chính sách đọc phải do chuẩn giao thức/API quy định, không đoán theo hệ điều hành. Với charset chuẩn Java, `StandardCharsets.UTF_16` nhận diện BOM và dùng big-endian làm mặc định khi không có BOM; encoder tương ứng có thể phát BOM. `UTF_16BE`/`UTF_16LE` chọn byte order tường minh và không tự phát BOM chỉ vì encoding được chọn.

Không nhầm UTF-16 với “16 bit cho mọi ký tự”: emoji ngoài BMP cần 4 byte. Và **code unit UTF-16 không phải code point Unicode**.

## 4. UTF-32, ASCII và các charset không phải Unicode

UTF-32 dùng **một code unit 32 bit cho mỗi Unicode scalar value**, với byte order BE/LE. Nó dễ định vị code point theo đơn vị cố định, nhưng thường tốn 4 byte/ký tự và không phổ biến như UTF-8 cho dữ liệu trao đổi. UTF-32 vẫn không bảo đảm một code point tương ứng một grapheme cluster.

Các tên thường gặp:

| Charset | Đặc điểm | Chú ý sử dụng |
|---|---|---|
| **US-ASCII** | 7 bit, byte `00..7F` | Không biểu diễn tiếng Việt có dấu, emoji |
| **ISO-8859-1 (Latin-1)** | Một byte cho `U+0000..U+00FF` | Nhiều byte có ý nghĩa khác windows-1252 |
| **windows-1252** | Mã hóa một byte kiểu Tây Âu | Các byte `0x80..0x9F` khác Latin-1; thường gặp trong dữ liệu Windows cũ |
| **UTF-8** | Unicode 1–4 byte, tương thích ASCII | Ưu tiên cho trao đổi dữ liệu mới |
| **UTF-16/UTF-16LE/UTF-16BE** | Unicode, code unit 16 bit | Phải rõ byte order/BOM |
| **UTF-32LE/UTF-32BE** | Unicode, code unit 32 bit | Không nằm trong sáu charset bắt buộc của `StandardCharsets` |
| **Shift_JIS**, **EUC-JP** | Charset tiếng Nhật đời trước | Cần biết đúng biến thể/nguồn dữ liệu |
| **GB18030**, **GBK**, **Big5** | Charset/biến thể dùng trong dữ liệu tiếng Trung | Không đồng nghĩa với UTF-8 |
| **EUC-KR**, **windows-949** | Charset tiếng Hàn đời trước | Không giả định chúng tương đương |

Một số tên lịch sử không bao phủ toàn bộ Unicode và không biểu diễn mọi ký tự. Hai charset “trông giống” nhau vẫn có thể gán byte thành ký tự khác, gây lỗi khó phát hiện. Chẳng hạn byte `0x80` trong windows-1252 thường biểu diễn `€`, còn trong ISO-8859-1 là ký tự điều khiển `U+0080`. Đây là một nguyên nhân phổ biến khiến văn bản hiển thị thành ký tự lạ.

Các alias như `UTF8`, `utf-8`, `ISO8859_1` có thể được Java nhận diện qua registry charset; khi phát triển nên dùng hằng số chuẩn hoặc tên chính thức, tránh tự suy luận biến thể. Mức hỗ trợ một số charset lịch sử phụ thuộc JDK/provider. **Sáu charset luôn có trong Java SE `StandardCharsets`**: `US_ASCII`, `ISO_8859_1`, `UTF_8`, `UTF_16`, `UTF_16BE`, `UTF_16LE`.

### Unicode khác với UTF-8/UTF-16

| Câu nói | Đánh giá |
|---|---|
| “Unicode là UTF-8” | Sai: Unicode là hệ thống mã ký tự; UTF-8 là một encoding của Unicode |
| “UTF-16 luôn dùng 2 byte cho một ký tự” | Sai: code point ngoài BMP cần 4 byte; grapheme có thể có nhiều code point |
| “UTF-8 và UTF-16 chứa các ký tự khác nhau” | Sai với chuỗi scalar Unicode hợp lệ: cùng tập giá trị có thể biểu diễn; cách lưu byte khác |
| “ASCII là một tập con tương thích byte của UTF-8” | Đúng đối với dữ liệu ASCII chuẩn `00..7F` |
| “Cùng byte phải decode ra cùng text” | Sai nếu dùng các charset khác nhau |
| “BOM là bắt buộc trong UTF-8” | Sai |
| “Độ dài Java String bằng số ký tự nhìn thấy” | Sai |

## 5. Unicode trong Java: `String`, `char`, code point

Java `String` thể hiện chuỗi theo **đơn vị UTF-16** ở tầng API. `char` là giá trị **16 bit**, có thể là một code unit của surrogate pair, không tự bảo đảm tương ứng một code point hoàn chỉnh. Các phương thức quan trọng:

| API Java | Đếm/truy cập gì? |
|---|---|
| `String.length()` | Số **UTF-16 code unit** |
| `String.charAt(index)` | Một `char` (code unit) tại chỉ số |
| `String.codePointAt(index)` | Một code point tại vị trí code unit được chỉ định; ghép surrogate pair hợp lệ |
| `String.codePointCount(begin, end)` | Số code point trong khoảng chỉ số UTF-16 |
| `String.codePoints()` | `IntStream` code point (surrogate không ghép được vẫn có thể xuất hiện như giá trị đơn lẻ) |
| `Character.toChars(codePoint)` | Các `char` UTF-16 để biểu diễn code point |
| `String.getBytes(charset)` | Encode `String` thành byte theo charset |
| `new String(bytes, charset)` | Decode byte theo charset |

### Ví dụ 1 — số `char`, code point và byte hoàn toàn khác nhau

Lưu tên tệp **`UnicodeBasicsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import java.util.stream.Collectors;

public class UnicodeBasicsDemo {
    public static void main(String[] args) {
        String text = "Aé😀";

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("Code points: " +
            text.codePointCount(0, text.length()));
        System.out.println("Code points: " +
            text.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(", ")));

        System.out.println("UTF-8: " +
            HexFormat.of().formatHex(
                text.getBytes(StandardCharsets.UTF_8)));
        System.out.println("UTF-16BE: " +
            HexFormat.of().formatHex(
                text.getBytes(StandardCharsets.UTF_16BE)));
        System.out.println("UTF-16LE: " +
            HexFormat.of().formatHex(
                text.getBytes(StandardCharsets.UTF_16LE)));
    }
}
```

Chạy Java 17+:

```bash
javac UnicodeBasicsDemo.java
java UnicodeBasicsDemo
```

Stdout chính xác:

```text
UTF-16 units: 4
Code points: 3
Code points: U+0041, U+00E9, U+1F600
UTF-8: 41c3a9f09f9880
UTF-16BE: 004100e9d83dde00
UTF-16LE: 4100e9003dd800de
```

Phân tích: `A` = một `char`; `é` = một `char`; 😀 = **hai** `char` (high/low surrogate), nên `length() == 4`, nhưng chỉ có ba code point. UTF-8 cần 1 + 2 + 4 = **7 byte**. `HexFormat` được bổ sung ở Java 17. Đừng dùng `charAt`/substring tùy tiện để cắt giữa surrogate pair.

> Nếu bài toán cần đếm **ký tự người dùng nhìn thấy**, code point count cũng chưa đủ: chuỗi `e\u0301`, một số emoji có tone modifier, cờ và emoji ZWJ có thể là một grapheme cluster gồm nhiều code point. Có thể sử dụng các thuật toán phân đoạn văn bản theo Unicode được thư viện hỗ trợ, ví dụ ICU4J cho yêu cầu grapheme đầy đủ; không tự mặc định rằng duyệt từng code point sẽ duyệt từng ký tự hiển thị.

## 6. Encoding và decoding trong Java 17

### Chọn charset tường minh khi chuyển byte ↔ text

Ví dụ các thao tác thường gặp:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
String decoded = new String(bytes, StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa** với `text` kiểu `String`; cần import `java.nio.charset.StandardCharsets`. Nếu chuỗi là Unicode hợp lệ và cùng charset hai chiều, kết quả thường khớp. Nếu `String` chứa surrogate đơn lẻ không hợp lệ hoặc charset không biểu diễn được ký tự, cách xử lý lỗi của encoder/decoder có thể làm mất thông tin.

Đối với file văn bản, `Path`/`Files` (NIO.2) thường là điểm bắt đầu phù hợp:

```java
Files.writeString(path, content, StandardCharsets.UTF_8);
String result = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là **đoạn minh họa**: `path` là `Path`, `content` là `String`, phương thức gọi xử lý `IOException`. File lớn nên đọc/ghi dần bằng `Files.newBufferedReader` và `Files.newBufferedWriter`, hoặc `InputStreamReader`/`OutputStreamWriter` chỉ rõ charset:

```java
try (var reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý một dòng; readLine() loại bỏ ký tự kết thúc dòng
    }
}
```

`reader` đóng tự động. `readLine()` trả dữ liệu không gồm `\\r`, `\\n` hay `\\r\\n`; nếu muốn giữ nguyên byte, line ending hay BOM, thao tác trên byte gốc trước khi thay đổi.

### Charset mặc định có thể là nguồn lỗi

Những API cho phép bỏ charset có thể phụ thuộc version/runtime:

- Trên **Java 17**, `Charset.defaultCharset()` tùy môi trường; có thể khác giữa máy phát triển, máy CI hoặc hệ điều hành.
- Từ **Java 18**, JEP 400 quy định UTF-8 làm charset mặc định trong các trường hợp tiêu chuẩn, kèm những chế độ tương thích; không nên xây dựng giao thức dựa trên ngầm định runtime.
- Khi có chuẩn dữ liệu như HTTP response, CSV trao đổi, file cấu hình hoặc message protocol, **quy định và truyền charset cụ thể**.

`new String(bytes)` hay `string.getBytes()` không đối số charset dễ dẫn đến tác vụ chạy đúng tại máy A nhưng sai trên máy B. Dùng `StandardCharsets.UTF_8` nếu đặc tả cho phép UTF-8.

## 7. Khi byte lỗi hoặc chọn sai charset

### Phân biệt hai trường hợp

1. **Byte hợp lệ theo charset X nhưng lại decode theo Y** → thường thành chữ lạ (*mojibake*). Ví dụ UTF-8 của `é` (`C3 A9`) nếu diễn giải dưới ISO-8859-1 sẽ thành `Ã©`.
2. **Byte không hợp lệ theo charset đang decode** → decoder có thể báo lỗi hoặc thay bằng `U+FFFD` (replacement character `�`). Ví dụ byte đơn `E9` từ Latin-1 không phải chuỗi UTF-8 hợp lệ.

Đừng dùng cách đổi qua lại charset nhiều lần để “sửa” văn bản nếu chưa biết **byte gốc** và các bước encode/decode đã thực hiện; thao tác thay thế `�` có thể đã làm mất thông tin.

### Ví dụ 2 — decode nghiêm ngặt và thay thế khi gặp lỗi

Lưu tên tệp **`CharsetErrorDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class CharsetErrorDemo {
    public static void main(String[] args) {
        // "café" mã hóa ISO-8859-1
        byte[] latin1 = {
            (byte) 0x63, (byte) 0x61,
            (byte) 0x66, (byte) 0xE9
        };

        System.out.println("Latin-1: " +
            new String(latin1, StandardCharsets.ISO_8859_1));
        System.out.println("UTF-8 replacement: " +
            new String(latin1, StandardCharsets.UTF_8));

        try {
            var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
            decoder.decode(ByteBuffer.wrap(latin1));
        } catch (CharacterCodingException ex) {
            System.out.println("Strict UTF-8: " +
                ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac CharsetErrorDemo.java
java CharsetErrorDemo
```

Stdout:

```text
Latin-1: café
UTF-8 replacement: caf�
Strict UTF-8: MalformedInputException
```

`new String(bytes, UTF_8)` dùng hành vi thay thế byte UTF-8 lỗi bằng replacement character; còn `CharsetDecoder` với `CodingErrorAction.REPORT` làm lỗi hiển lộ. Trong hệ thống nhập dữ liệu cần tính chính xác, đặc biệt ID, log kiểm toán hoặc dữ liệu đã ký số, decoder nghiêm ngặt thường thích hợp hơn việc âm thầm thay ký tự.

Các `CodingErrorAction`:
- `REPORT`: trả lỗi; với `decode(ByteBuffer)`, thường ném `MalformedInputException` hoặc `UnmappableCharacterException`.
- `REPLACE`: chèn chuỗi/ký tự thay thế khi có lỗi.
- `IGNORE`: bỏ dữ liệu sai, có thể làm mất thông tin và thường không phù hợp để lưu trữ dữ liệu quan trọng.

**Malformed input** là chuỗi byte/code unit vi phạm encoding; **unmappable character** là ký tự hợp lệ nhưng charset đích không có cách biểu diễn. Ví dụ encode `"Tiếng Việt"` theo Latin-1 có nhiều ký tự không mã hóa được: encoder có thể thay thế, bỏ, hoặc báo lỗi tùy cấu hình. Đừng coi `getBytes(ISO_8859_1)` là phép chuyển không mất dữ liệu cho tiếng Việt.

### Trường hợp UTF-8 đến theo nhiều chunk

Một ký tự UTF-8 có thể trải qua ranh giới đọc từ socket hoặc file. Ví dụ 😀 có `F0 9F 98 80`: lần đọc đầu chỉ có `F0 9F`, lần sau mới có `98 80`. Gọi `new String(chunk, UTF_8)` riêng trên mỗi chunk có thể tạo replacement characters.

Với dữ liệu nhiều chunk, hãy giữ byte chưa xử lý qua `ByteBuffer.compact()` hoặc cấu trúc lưu đệm tương ứng, và dùng **`CharsetDecoder` có trạng thái** qua nhiều lần `decode(input, output, endOfInput)` rồi `flush(output)` khi đến EOF. Kiểm tra `CoderResult.UNDERFLOW`, `OVERFLOW`, lỗi và dung lượng `CharBuffer`. Tránh lấy ranh giới TCP `read()` làm ranh giới text/message. Một cách đơn giản hơn khi đầu vào là stream byte tuần tự: dùng `InputStreamReader` bọc `InputStream`, đã được thiết kế để decode dữ liệu đến dần.

## 8. Unicode normalization: cùng cách nhìn, khác byte

Một chuỗi có thể biểu diễn cùng nội dung văn bản theo nhiều chuỗi code point. Ví dụ:

- `café` với `é = U+00E9` (composed)
- `cafe\u0301` với `e = U+0065`, dấu sắc kết hợp `U+0301` (decomposed)

Trong Java, `String.equals` so sánh nội dung UTF-16 thực tế, không tự chuẩn hóa Unicode.

**Normalization forms** (Unicode Standard Annex #15):

| Dạng | Mô tả | Ví dụ dùng |
|---|---|---|
| **NFC** | Canonical decomposition rồi composition | Đồng nhất những biểu diễn canonically equivalent |
| **NFD** | Canonical decomposition | Một số quy trình xử lý phân tách dấu |
| **NFKC** | Compatibility decomposition rồi composition | Một số bài toán tìm kiếm/chuẩn hóa tương thích, cần cân nhắc thay đổi ý nghĩa trình bày |
| **NFKD** | Compatibility decomposition | Phân tích dạng ký tự có biến thể tương thích |

Các dạng `NFKC`/`NFKD` có thể làm mất khác biệt trình bày mang ý nghĩa (ví dụ một số ký tự tương thích). Không dùng bừa chúng cho văn bản nguồn, chữ ký số hoặc định danh có chuẩn riêng.

### Ví dụ 3 — NFC và so sánh chuỗi

Lưu tên tệp **`NormalizationDemo.java`**:

```java
import java.text.Normalizer;

public class NormalizationDemo {
    public static void main(String[] args) {
        String composed = "café";
        String decomposed = "cafe\u0301";

        System.out.println("Raw equals: " +
            composed.equals(decomposed));
        System.out.println("NFC equals: " +
            composed.equals(
                Normalizer.normalize(
                    decomposed, Normalizer.Form.NFC
                )));
        System.out.println("Raw code points: " +
            decomposed.codePointCount(0, decomposed.length()));
    }
}
```

Chạy:

```bash
javac NormalizationDemo.java
java NormalizationDemo
```

Stdout:

```text
Raw equals: false
NFC equals: true
Raw code points: 5
```

Chuỗi `cafe\u0301` có `c`, `a`, `f`, `e`, dấu sắc = **5 code point**; nó thường hiển thị giống “café” được dựng sẵn với 4 code point. Việc so sánh, tìm kiếm, băm hoặc tạo khóa Unicode có thể cần quy tắc normalization **được thống nhất tại ranh giới dữ liệu**. Không chuẩn hóa một phía trước khi kiểm tra chữ ký/HMAC trên byte gốc.

**Normalization khác case folding:** `toLowerCase()` không giải quyết mọi so sánh Unicode không phân biệt hoa/thường. Nếu cần xử lý tìm kiếm/ngôn ngữ, phải xác định locale và semantics rõ ràng; `String.toLowerCase(Locale.ROOT)` có thể phù hợp cho một số định danh phi ngôn ngữ nhưng không phải giải pháp tổng quát cho mọi quy tắc Unicode.

## 9. Quy trình đọc/ghi đúng với tệp và API

### Đọc từ byte vào Java text

```text
Nguồn byte → xác minh encoding bằng hợp đồng giao thức/metadata
          → nhận diện BOM khi đặc tả có quy định
          → CharsetDecoder (REPORT hoặc chính sách lỗi rõ ràng)
          → String / Reader theo code unit UTF-16 của Java
          → xử lý code point / grapheme theo yêu cầu nghiệp vụ
```

Không “đọc text” bằng cách cast từng byte sang `char`. Khi byte chứa UTF-8, một code point có thể chiếm bốn byte; khi một file UTF-16LE được decode bằng UTF-8, ngay cả byte `00` xen kẽ cũng có thể làm dữ liệu hiển thị sai.

### Ghi Java text ra byte

```text
String → lựa chọn normalization nếu giao thức đòi hỏi
       → CharsetEncoder với chính sách lỗi minh bạch
       → byte[]/OutputStream/Files
       → BOM/metadata/media type nhất quán với charset
```

Nếu chọn UTF-8, một số API như `Files.writeString(path, text, UTF_8)` đã đủ. Với dữ liệu nhị phân có trường “length”, phải tính `text.getBytes(UTF_8).length`. Nếu dùng `Writer`, nó encode ký tự sang byte; `BufferedWriter` chỉ là buffer, không tự chọn charset chuẩn cho ứng dụng.

### BOM, newline và dấu hiệu file

Ba khái niệm độc lập:

- **BOM**: một số byte đầu thể hiện byte order hoặc signature encoding, ví dụ `EF BB BF` trong UTF-8, `FE FF` trong UTF-16BE, `FF FE` trong UTF-16LE.
- **Newline**: `LF`, `CRLF` là nội dung văn bản; charset quyết định byte tương ứng, nhưng không tự quy định hệ thống phải dùng loại xuống dòng nào.
- **Binary file marker / magic bytes**: có thể giúp nhận diện định dạng file, không nhất thiết là một charset.

Một file không có BOM **không đồng nghĩa ASCII hoặc UTF-8**. Một file chứa BOM cũng phải được kiểm tra cùng hợp đồng định dạng và API decode cụ thể, vì không phải mọi decoder đều tự bỏ BOM.

## 10. Tình huống thực tế: khi nào chọn cách nào?

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| File cấu hình/JSON/log mới | UTF-8 theo đặc tả, thường không BOM | Phổ biến, tương thích ASCII, lưu được Unicode |
| CSV trao đổi giữa nhiều hệ thống | Thống nhất UTF-8, ghi rõ charset trong hợp đồng; quy tắc BOM theo nơi tiêu thụ | CSV không tự định danh encoding |
| File UTF-16 của hệ thống legacy | Dùng đúng UTF-16LE/BE hoặc UTF-16 theo BOM/đặc tả | Không decode nhầm sang UTF-8 |
| File Latin-1 / windows-1252 cũ | Chỉ rõ charset thực tế, xử lý và chuyển đổi có kiểm chứng | Tránh mojibake ở các byte ngoài ASCII |
| Socket TCP nhận UTF-8 dần | `InputStreamReader` hoặc decoder streaming với framing rõ | Không phân tách ký tự theo mỗi lần đọc byte |
| Định danh/so sánh Unicode | Đặc tả normalization + case/locale + chính sách ký tự | Tránh hai dạng chuỗi trông giống nhau nhưng khác byte |
| Ký số, hash nội dung text | Chốt byte encoding và normalization trước khi ký | Hash/HMAC làm việc với byte, khác byte thì khác chữ ký |
| Cắt/giới hạn text trong UI | Cân nhắc grapheme cluster thay vì `String.length()` | Tránh cắt surrogate, dấu kết hợp hoặc emoji nối |

**Thực hành cho dữ liệu Việt:** UTF-8 biểu diễn đầy đủ chữ có dấu, kể cả dạng combining marks. ISO-8859-1 và US-ASCII không biểu diễn đầy đủ tiếng Việt; không nên chuyển dữ liệu Việt vào chúng theo cách thay thế mặc định rồi mong khôi phục nguyên trạng.

## 11. Những lỗi hay gặp và cách kiểm tra

1. **Khai báo UTF-8 nhưng byte không phải UTF-8.** So sánh bytes hex đầu vào với metadata thực tế. Nội dung chỉ có ASCII rất khó giúp phát hiện mismatch; dùng test có chữ `Tiếng Việt`, `é`, `中`, emoji.
2. **`String.length()` bị dùng làm độ dài payload byte.** Dùng `text.getBytes(UTF_8).length` hoặc đếm byte ngay từ quá trình ghi.
3. **Cắt nửa surrogate pair.** Khi cần xử lý code point, dùng `codePoints()`, `offsetByCodePoints()`, `Character.charCount()` phù hợp. Khi cần xử lý ký tự hiển thị, dùng grapheme segmentation.
4. **Một lần socket `read` rồi decode ngay cả chunk.** Byte của ký tự nhiều byte có thể bị chia; giữ decoder state và xử lý framing.
5. **Giải mã sai encoding rồi encode lại thêm lần nữa.** Chuỗi mojibake có thể được lưu vĩnh viễn; giữ bản byte gốc để chẩn đoán, không biến đổi thử trên dữ liệu sản xuất.
6. **Bỏ qua BOM.** Byte mở đầu có thể làm xuất hiện `U+FEFF`, làm sai header đầu tiên của CSV, khóa cấu hình hoặc chuỗi so sánh. Chỉ loại BOM khi format cho phép, kiểm tra đúng byte/ký tự đầu.
7. **Tự cho rằng mọi charset là Unicode.** Charset legacy có thể không biểu diễn ký tự; dùng encoder `REPORT` nếu tuyệt đối không được mất thông tin.
8. **So sánh chuỗi không xét normalization.** Hai chuỗi giống về hình thức có thể khác code point; áp dụng NFC/NFD theo hợp đồng trước khi tạo khóa hoặc tìm kiếm nếu phù hợp.
9. **Đánh đồng normalization với bảo mật.** Ký tự dễ nhầm (*confusable*), ký tự điều khiển định hướng hai chiều (bidi), zero-width và mixed scripts có thể gây hiểu sai; chính sách định danh cần kiểm tra riêng. Không nghĩ NFC tự loại các nguy cơ đó.
10. **Phụ thuộc charset mặc định của runtime.** Dùng charset rõ ràng khi ghi/đọc dữ liệu được trao đổi giữa các máy.
11. **Nhầm Java `char` với Unicode scalar value.** Một `char` có thể là surrogate. Một code point có thể không tương ứng một grapheme, và nhiều code point có thể kết hợp thành một glyph.
12. **Không phân biệt data encoding và escaping.** JSON `"\u00E9"` là biểu diễn *escape* trong cú pháp JSON; các ký tự byte của file JSON vẫn có encoding riêng (thường UTF-8). URL percent-encoding, HTML entities, Base64 cũng không phải charset thay thế UTF-8.

### Cách chẩn đoán nhanh dữ liệu lỗi

1. Tìm **byte gốc** và nguồn tạo, lưu nguyên mẫu để tái hiện.
2. Xem thông số giao thức/file thực tế: charset, BOM, byte order, media type, cấu hình kết nối.
3. In byte hex có giới hạn trong môi trường thử nghiệm để so `C3 A9` (UTF-8 của é) với `E9` (Latin-1 của é).
4. Decode nghiêm ngặt bằng charset được chỉ định; báo lỗi khi dữ liệu vi phạm. Nếu decode được nhưng chữ lạ, kiểm chứng charset nguồn có đúng không.
5. Kiểm tra normalization khi text nhìn giống mà so sánh thất bại; phân biệt lỗi hiển thị font/glyph với lỗi encoding bytes.
6. Cố định regression tests cho chữ tiếng Việt, emoji, dấu kết hợp, byte lỗi, BOM và ranh giới buffer.

## 12. Tự kiểm tra

**Câu 1.** `String s = "A😀";` có `s.length()` bằng mấy, `codePointCount(0, s.length())` bằng mấy, UTF-8 dài bao nhiêu byte?

**Đáp án:** `length() == 3` vì `A` dùng một `char`, 😀 dùng surrogate pair hai `char`; có **2 code point**; UTF-8 có **5 byte** (`41 F0 9F 98 80`).

**Câu 2.** Tại sao dãy byte `C3 A9` có thể thành `Ã©`?  
**Đáp án:** đây là byte UTF-8 của `é`, nhưng nếu giải mã từng byte theo ISO-8859-1 sẽ nhận `U+00C3` (Ã) và `U+00A9` (©).

**Câu 3.** UTF-16LE mã hóa 😀 thành byte nào? UTF-16BE thì sao?  
**Đáp án:** cặp surrogate `D83D DE00`; UTF-16LE là `3D D8 00 DE`, UTF-16BE là `D8 3D DE 00`.

**Câu 4.** Vì sao `String.equals` có thể báo false với hai chữ “é” trông giống nhau?  
**Đáp án:** một chuỗi dùng `U+00E9`; chuỗi còn lại dùng `U+0065 U+0301`. Chúng khác code point/code unit; có thể cần NFC theo hợp đồng dữ liệu.

**Câu 5.** Muốn không âm thầm mất byte khi nhận file UTF-8 lỗi thì dùng API nào?  
**Đáp án:** `CharsetDecoder` của `StandardCharsets.UTF_8` kết hợp `CodingErrorAction.REPORT`; xử lý `CharacterCodingException`.

**Câu 6.** Có thể giả định một lần `InputStream.read(byte[])` nhận đủ một ký tự UTF-8 hay một message TCP không?  
**Đáp án:** Không. UTF-8 có thể bị chia giữa các lần đọc và TCP không bảo đảm ranh giới message. Cần reader/decoder streaming và giao thức framing.

**Ghi nhớ:** Unicode mô tả code point; UTF-8/UTF-16/UTF-32 quy định cách biểu diễn các giá trị đó trong code unit/byte. Trong Java 17, `String` được đánh chỉ số theo code unit UTF-16; dùng charset tường minh khi chuyển `String ↔ byte[]`, kiểm soát lỗi decoding, BOM, normalization và ranh giới dữ liệu để tránh văn bản sai hoặc mất thông tin.
