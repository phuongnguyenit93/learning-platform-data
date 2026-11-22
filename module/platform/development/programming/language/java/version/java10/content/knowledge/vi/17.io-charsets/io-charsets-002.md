# `StandardCharsets` và việc chọn bộ mã tường minh trong I/O (Java 10+)

## 1. Vấn đề: cùng một văn bản, tại sao đọc lại có thể bị lỗi dấu?

Khi ứng dụng đọc hoặc ghi văn bản, Java phải chuyển đổi giữa **ký tự** và **byte**. Một chuỗi Java như `"Tiếng Việt: cà phê ☕"` là dữ liệu văn bản; còn file, socket và nhiều giao thức I/O truyền **dãy byte**. Phép chuyển đổi phụ thuộc vào **charset** (*bộ mã ký tự*), ví dụ UTF-8, ISO-8859-1 hoặc UTF-16.

Nếu bên ghi dùng UTF-8 nhưng bên đọc giải mã bằng ISO-8859-1, các byte có thể được diễn giải thành những ký tự khác. Kết quả là văn bản trông bị lỗi dấu (*mojibake*), dù file không hề bị hỏng ở tầng lưu trữ.

Ví dụ:

```java
byte[] bytes = "café".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

String correct = new String(
        bytes, java.nio.charset.StandardCharsets.UTF_8);

String wrong = new String(
        bytes, java.nio.charset.StandardCharsets.ISO_8859_1);

System.out.println("café".equals(correct)); // true
System.out.println("café".equals(wrong));   // false
```

Bốn byte đầu và cuối của chuỗi mã hóa UTF-8 có quy tắc riêng; chữ `é` được mã thành hai byte `C3 A9`. Nếu giải mã hai byte đó theo ISO-8859-1, mỗi byte trở thành một ký tự riêng biệt, không còn đúng `é`.

**Bài học cốt lõi:** ở mọi ranh giới chuyển đổi **text ↔ bytes**, chỉ định charset theo **hợp đồng dữ liệu**. Khi chủ động lựa chọn được, **UTF-8** thường là mặc định thiết kế phù hợp; nếu đang trao đổi với hệ thống/định dạng quy định charset khác, hãy dùng **đúng charset được quy định**, không ép mọi nguồn thành UTF-8.

`java.nio.charset.StandardCharsets` là tập hợp hằng `Charset` có từ **Java 7**, tiếp tục áp dụng nguyên vẹn trong Java 10 và các bản Java hiện hành. Nó **không phải tính năng chỉ mới xuất hiện trong Java 10**, nhưng là kiến thức nền quan trọng khi làm I/O ở module Java 10.

## 2. Hiểu chính xác `Charset`, ký tự và byte

Ba khái niệm cần tách biệt:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Văn bản/`String` | `"Xin chào"` | Chuỗi ký tự trong chương trình; không nên đồng nhất nó với byte UTF-8 của file |
| `Charset` | `StandardCharsets.UTF_8` | Quy định ánh xạ khi mã hóa ký tự thành byte và giải mã byte thành ký tự |
| Dãy byte | `byte[]`, nội dung file, nội dung luồng mạng | Những giá trị thực tế được lưu hoặc truyền ở ranh giới I/O |

Hai hướng chuyển đổi:

```text
                 encoding
String/ký tự  --------------> byte[] / file / network
             <--------------
                 decoding
                   Charset
```

- **Encode:** `text.getBytes(StandardCharsets.UTF_8)` chuyển văn bản thành byte UTF-8.
- **Decode:** `new String(bytes, StandardCharsets.UTF_8)` chuyển byte UTF-8 thành chuỗi Java.
- **Đồng thuận:** cả hai phía dùng charset tương thích với cách dữ liệu được tạo ra.
- **Không phải phép đoán:** `StandardCharsets.UTF_8` không tự phát hiện file có thực sự được mã bằng UTF-8 hay không.

Với UTF-8, một ký tự Unicode có thể chiếm **1–4 byte**. Vì thế, không được suy ra `string.length()` chính là số byte cần ghi file hoặc gửi mạng. `String.length()` đếm **UTF-16 code units**, không đếm byte UTF-8 và cũng không luôn bằng số ký tự mà người đọc cảm nhận.

Ví dụ `"A"` có một byte UTF-8, trong khi `"é"` có hai byte UTF-8. Emoji hoặc nhiều ký hiệu khác có thể cần bốn byte. Muốn xác định chính xác dung lượng payload đã mã hóa, xem `bytes.length` sau khi encode bằng charset thực sự được dùng.

## 3. `StandardCharsets` có những hằng nào?

`java.nio.charset.StandardCharsets` cung cấp các hằng `public static final Charset` cho những bộ mã chuẩn. Các hằng quen thuộc:

| Hằng | Tên charset chuẩn | Trường hợp sử dụng |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | `UTF-8` | Văn bản Unicode phổ biến, JSON, dữ liệu dịch vụ và text file hiện đại |
| `StandardCharsets.US_ASCII` | `US-ASCII` | Giao thức hoặc định dạng **chỉ cho phép ASCII 7-bit** |
| `StandardCharsets.ISO_8859_1` | `ISO-8859-1` | Trao đổi với định dạng/nguồn dữ liệu Latin-1 được quy định rõ |
| `StandardCharsets.UTF_16` | `UTF-16` | Dữ liệu UTF-16 có cơ chế nhận biết thứ tự byte qua BOM tùy nội dung |
| `StandardCharsets.UTF_16BE` | `UTF-16BE` | UTF-16 với thứ tự byte big-endian, không tự thêm BOM theo phép encode hằng này |
| `StandardCharsets.UTF_16LE` | `UTF-16LE` | UTF-16 với thứ tự byte little-endian, không tự thêm BOM theo phép encode hằng này |

Một số bản Java mới còn có những charset chuẩn khác; bảng trên **không phải danh sách toàn bộ field của mọi phiên bản**. Tất cả các hằng nêu trên đều đã được bảo đảm có từ lâu và vẫn được dùng trong Java hiện hành.

Ví dụ:

```java
import java.nio.charset.StandardCharsets;

var charset = StandardCharsets.UTF_8;
System.out.println(charset.name()); // UTF-8
```

**Ưu tiên hằng thay cho chuỗi tên** khi là charset chuẩn:

```java
var bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
```

Thay vì dùng:

```java
var bytes = "Xin chào".getBytes("UTF-8");
```

Hai cách đều có thể mã hóa UTF-8, nhưng overload nhận `Charset` tránh xử lý chuỗi tên và ngoại lệ `UnsupportedEncodingException` của overload nhận `String`. Mã cũng dễ đọc, được compiler kiểm tra tên hằng và không phụ thuộc alias do người viết gõ.

Khi charset **thực sự phải chọn từ cấu hình** theo tên, có thể dùng `Charset.forName(name)` và xử lý trường hợp tên không hợp lệ/không được hỗ trợ; không nên hard-code `forName("UTF-8")` thay cho hằng chuẩn mà không có lý do.

## 4. Chỉ định charset khi đổi giữa `String` và `byte[]`

### 4.1. Mã hóa rõ ràng

```java
import java.nio.charset.StandardCharsets;

String message = "Tiếng Việt";
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
```

`payload` là byte UTF-8. Đây là cách phù hợp nếu một giao thức, service hoặc file format quy định nội dung dạng text UTF-8.

### 4.2. Giải mã rõ ràng

```java
String restored = new String(payload, StandardCharsets.UTF_8);
System.out.println(message.equals(restored)); // true
```

Lúc này bên decode biết chính xác các byte đang được đọc theo UTF-8. Nếu dữ liệu thực sự dùng charset khác, phải **chọn đúng charset đó**, thay vì thử ngẫu nhiên nhiều cách mà không biết hợp đồng.

### 4.3. Không dựa vào charset mặc định khi giao tiếp qua ranh giới

```java
// Tránh khi payload/file có quy định charset:
byte[] bytes = message.getBytes();
String text = new String(bytes);
```

Hai overload trên sử dụng **default charset**. Chúng có thể tình cờ hoạt động tốt trên một máy nhưng tạo dữ liệu khác khi runtime hoặc thiết lập encoding khác, đặc biệt với Java 10–17.

**Sửa bằng hợp đồng rõ ràng:**

```java
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
```

Trong nhiều tình huống, phép decode với charset sai **không báo lỗi** nếu dãy byte vẫn hợp lệ dưới charset được chọn. Kết quả có thể là văn bản sai dấu nhưng không có exception. Vì thế, kiểm thử **round-trip** và kiểm tra dữ liệu thực tế quan trọng hơn việc chỉ xem code có ném lỗi hay không.

## 5. Charset mặc định trong Java 10 và Java hiện đại

Phần này đặc biệt cần phân biệt **phiên bản Java**.

### 5.1. Java 10–17: default charset có thể phụ thuộc môi trường

Với JDK 17 trở về trước (trong đó có Java 10), default charset của nhiều API truyền thống có thể được xác định từ hệ điều hành, locale và cấu hình khi JVM khởi động.

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
```

Lời gọi này cho biết default charset mà **runtime hiện tại** sử dụng. **Không ghi cố định stdout** của nó cho bài kiểm thử đa nền tảng, vì Java 10–17 có thể khác giữa các máy.

Một chương trình dùng `new String(bytes)` hoặc `getBytes()` không tham số có thể phụ thuộc vào thiết lập đó. Sự khác biệt thường lộ ra khi dữ liệu chứa dấu tiếng Việt, dấu châu Âu hoặc ký tự ngoài ASCII.

### 5.2. Từ JDK 18: JEP 400 chọn UTF-8 làm default charset

**JEP 400 — UTF-8 by Default** có hiệu lực từ **JDK 18**. Với cấu hình mặc định của Java SE APIs chịu ảnh hưởng, `Charset.defaultCharset()` dùng UTF-8 thay vì codepage hệ điều hành.

Tuy nhiên, điều này **không có nghĩa mọi API I/O trong mọi tình huống đều bỏ qua charset đặc thù**:

- Cơ chế tương thích như `-Dfile.encoding=COMPAT` trong các JDK hỗ trợ có thể chọn lại hành vi theo môi trường. Đừng coi `file.encoding` là cách thiết kế giao thức trao đổi dữ liệu giữa ứng dụng.
- `System.in`, `System.out` và `System.err` có quy tắc charset riêng gắn với console/host environment; **đừng mặc định chúng luôn giống `Charset.defaultCharset()`**.
- Một số API/định dạng có **quy tắc encoding được ghi riêng trong đặc tả**, không phụ thuộc default charset, ví dụ `Properties.load(InputStream)` theo định dạng ISO-8859-1.
- Dữ liệu lưu từ trước bằng Windows codepage hoặc Latin-1 **không tự đổi thành UTF-8** chỉ vì ứng dụng nâng lên JDK 18+.

**Kết luận thực hành xuyên phiên bản:** khi đọc/ghi file, HTTP payload, message queue hoặc giao thức được chỉ định charset, hãy **truyền charset tường minh**, kể cả trên JDK 18+. Nhờ vậy kết quả không phụ thuộc default runtime và dễ kiểm chứng trong code review.

## 6. Chọn charset tường minh khi đọc và ghi file

### 6.1. API `Files.newBufferedReader` và `newBufferedWriter`

Ví dụ đọc/ghi file UTF-8 bằng `java.nio.file.Files`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("notes.txt");

try (var writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Xin chào Việt Nam");
}

try (var reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
```

Đây là đoạn **mã đặt trong phương thức có xử lý hoặc khai báo `IOException`**, với các import tương ứng. `Path.of` có từ Java 11; nếu codebase bắt buộc chạy trên Java 10, dùng `Paths.get("notes.txt")`. `Files.newBufferedReader/Writer(Path, Charset)` đã tồn tại trước Java 10.

Vì sao dùng `try-with-resources`? Nó bảo đảm reader/writer được đóng sau khi xử lý, kể cả khi xảy ra ngoại lệ. Writer cần được đóng hoặc flush theo hợp đồng trước khi một bên khác kỳ vọng đọc được đủ các byte đã ghi.

**Lưu ý:** overload `Files.newBufferedReader(path)` và `newBufferedWriter(path)` **không nhận Charset** đã được đặc tả dùng **UTF-8** từ trước JEP 400. Dù vậy, truyền `StandardCharsets.UTF_8` tường minh vẫn có ích khi muốn người đọc thấy chính sách encoding ngay tại lời gọi.

### 6.2. `Files.readString` và `writeString` (Java 11+)

Với file nhỏ hoặc vừa, có thể dùng API chuỗi:

```java
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);
String content = Files.readString(path, StandardCharsets.UTF_8);
```

Hai phương thức này có từ **Java 11**, không dùng được nếu phải **biên dịch với `--release 10`**. Chúng tiện dụng nhưng `Files.readString` đọc toàn bộ nội dung vào bộ nhớ, không phải lựa chọn mặc định cho file cực lớn. Với file lớn, dùng reader/buffered stream để xử lý từng phần.

Trong `Files.readString`/`Files.writeString`, overload không truyền Charset vốn được đặc tả dùng UTF-8. Điều này **khác** những overload truyền thống từng dùng `defaultCharset`.

### 6.3. `InputStreamReader` và `OutputStreamWriter`

Khi có **byte stream** (file, socket hoặc stream từ thư viện), ta dùng lớp cầu nối rõ charset:

```java
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

// 'in' là InputStream đã được cấp từ nguồn byte phù hợp.
var reader = new InputStreamReader(in, StandardCharsets.UTF_8);

// 'out' là OutputStream đích phù hợp.
var writer = new OutputStreamWriter(out, StandardCharsets.UTF_8);
```

Đây là ví dụ biểu thức trong phương thức với `in`/`out` đã có; muốn thành chương trình đầy đủ phải tạo/nhận và quản lý vòng đời hai stream. **Không mở luồng byte chỉ để đưa lại qua `String.getBytes()` rồi quên charset ở bước đọc.**

Khi muốn xử lý theo dòng, có thể bọc:

```java
var buffered = new java.io.BufferedReader(
        new InputStreamReader(in, StandardCharsets.UTF_8));
```

Khi ghi, `BufferedWriter` bao `OutputStreamWriter` giúp giảm số lần ghi. Hãy đóng resource theo quy ước sở hữu stream: với stream mạng/stream của framework, xác định rõ ai chịu trách nhiệm đóng, tránh vô tình đóng resource mà caller vẫn cần.

### 6.4. Phân biệt text với dữ liệu nhị phân

Dữ liệu PNG, ZIP, ciphertext, ảnh hoặc byte protocol tùy ý **không tự động là UTF-8**. `new String(binaryBytes, UTF_8)` không phải một bước chuyển đổi bảo toàn byte cho dữ liệu nhị phân.

- **Text có charset đã biết:** dùng Reader/Writer hoặc encode/decode bằng Charset.
- **Binary:** dùng `InputStream`/`OutputStream`, `Files.readAllBytes`, `Files.write`, `ByteBuffer` hoặc API định dạng binary thích hợp, không đi vòng qua `String`.
- **Một protocol kết hợp header và payload:** làm theo định dạng protocol, không tự áp UTF-8 lên toàn bộ khung byte.

Chọn `StandardCharsets` là một quyết định **đúng cho text**, không phải phép biến đổi áp dụng được cho mọi byte.

## 7. Sai charset có thể gây mojibake dù không hề có ngoại lệ

Ví dụ có thể kiểm chứng chính xác:

```java
import java.nio.charset.StandardCharsets;

byte[] utf8 = "café".getBytes(StandardCharsets.UTF_8);

String correct = new String(utf8, StandardCharsets.UTF_8);
String incorrect = new String(utf8, StandardCharsets.ISO_8859_1);

System.out.println("café".equals(correct));   // true
System.out.println("café".equals(incorrect)); // false
```

UTF-8 của `café` là:

```text
63 61 66 C3 A9
```

`63 61 66` là các byte ASCII tương ứng `c`, `a`, `f`; `C3 A9` mã hóa chữ `é` theo UTF-8. ISO-8859-1 giải mã từng byte riêng biệt, nên hai byte cuối không tạo đúng chữ `é`.

**Không sửa dữ liệu bằng cách encode/decode lặp lại tùy tiện** khi chưa xác định encoding gốc. Nếu một file có byte ISO-8859-1 mà ta đọc thành UTF-8, có thể gặp ngoại lệ hoặc ký tự thay thế; nếu byte UTF-8 bị đọc thành ISO-8859-1, có thể tạo văn bản sai nhưng vẫn hợp lệ về mặt cú pháp charset.

Quy trình chẩn đoán:

1. Xác định **nguồn dữ liệu và định dạng quy định**, không dựa vào cách trình soạn thảo tự hiển thị.
2. Kiểm tra byte thực tế hoặc metadata charset do format/protocol công bố.
3. Giải mã bằng đúng Charset đã xác định.
4. Nếu cần chuyển đổi sang UTF-8, **giải mã theo charset gốc rồi mã hóa bằng UTF-8**, không chỉ gắn nhãn UTF-8 lên byte cũ.
5. Kiểm tra lại các chuỗi có dấu, emoji và ký tự ngoài ASCII bằng test.

## 8. Charset không biểu diễn được ký tự: thay thế hay báo lỗi?

UTF-8 có thể biểu diễn các Unicode scalar values hợp lệ; nhưng `US_ASCII` chỉ bao phủ 7-bit ASCII và `ISO_8859_1` chỉ biểu diễn tập Latin-1. Một số chữ tiếng Việt và ký hiệu như `€` không có trong ISO-8859-1.

### 8.1. `String.getBytes(Charset)` có chính sách thay thế mặc định

```java
byte[] encoded = "€".getBytes(StandardCharsets.ISO_8859_1);
```

`€` không thể được biểu diễn trong ISO-8859-1. Overload `String.getBytes(Charset)` được đặc tả **thay thế** các ký tự không biểu diễn được bằng byte thay thế mặc định của charset, không tự động ném lỗi. Trong ví dụ được kiểm thử trên JDK, byte thu được có giá trị hex `3f` (ký tự `?`).

Điều này rất quan trọng nếu dữ liệu cần **bảo toàn tuyệt đối**: chỉ gọi `getBytes(ISO_8859_1)` có thể làm mất ký tự mà chương trình không nhận ra.

### 8.2. Dùng `CharsetEncoder` nếu muốn thất bại rõ ràng

```java
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var encoder = StandardCharsets.ISO_8859_1.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

// encoder.encode(CharBuffer.wrap("€"));
// Ném UnmappableCharacterException vì ISO-8859-1 không biểu diễn được €.
```

Phương thức `encode` có thể ném `CharacterCodingException`, trong trường hợp cụ thể trên là `UnmappableCharacterException`.

Các hành vi xử lý lỗi thường dùng:

| `CodingErrorAction` | Tác dụng |
| --- | --- |
| `REPORT` | Báo lỗi, giúp ứng dụng từ chối dữ liệu không hợp lệ hoặc không mã hóa được |
| `REPLACE` | Thay bằng ký tự/byte thay thế của charset |
| `IGNORE` | Bỏ qua dữ liệu lỗi, có thể gây mất nội dung |

**Khuyến nghị:** đối với dữ liệu cần nguyên vẹn (hồ sơ, trao đổi có chữ ký, hợp đồng dữ liệu), cân nhắc `REPORT` và xử lý lỗi phù hợp; không mặc nhiên dùng `IGNORE` hoặc thay thế mà không thông báo.

### 8.3. Decode byte UTF-8 sai cũng có thể được thay thế

```java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};
String lenient = new String(invalid, StandardCharsets.UTF_8);
```

Đây là chuỗi byte UTF-8 không hợp lệ; constructor `new String(byte[], Charset)` **thay thế các chuỗi byte lỗi** bằng ký tự thay thế của charset, thay vì buộc phải ném ngoại lệ. Trong ví dụ được kiểm thử, `lenient` chứa ký tự Unicode replacement `U+FFFD`.

Nếu không được phép chấp nhận dữ liệu hỏng, dùng `CharsetDecoder` nghiêm ngặt:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

// decoder.decode(ByteBuffer.wrap(invalid));
// Ném MalformedInputException cho byte sequence ở ví dụ.
```

`Files.newBufferedReader(path, charset)` và `Files.readString(path, charset)` đã có hợp đồng báo lỗi đọc khi gặp byte không thể giải mã hợp lệ. **Đừng nghĩ mọi overload của mọi API Java đều có chung chính sách thay thế/báo lỗi**: hãy đọc đúng API đang dùng.

## 9. UTF-16, thứ tự byte và BOM

UTF-8 thường phù hợp khi thiết kế định dạng text mới. Tuy nhiên, một file hoặc giao thức có thể quy định **UTF-16BE**, **UTF-16LE** hoặc **UTF-16**.

Thứ tự byte là khác biệt thật:

```java
byte[] bigEndian = "A".getBytes(StandardCharsets.UTF_16BE);
byte[] littleEndian = "A".getBytes(StandardCharsets.UTF_16LE);
```

Trong hai byte biểu diễn chữ `A` (U+0041):

```text
UTF-16BE: 00 41
UTF-16LE: 41 00
```

`UTF_16` là charset có hỗ trợ nhận biết byte order bằng BOM (*byte-order mark*). Khi **encode** bằng `StandardCharsets.UTF_16` trong Java, chuỗi `"A"` của ví dụ cho byte `FE FF 00 41` (BOM big-endian rồi đến `A`). Không đánh đồng `UTF_16` với `UTF_16LE` hay `UTF_16BE` khi giao thức yêu cầu đúng byte.

**Không suy rằng mọi file UTF-8 phải có BOM**, hoặc rằng `String.getBytes(StandardCharsets.UTF_8)` sẽ tự thêm BOM. Với UTF-8 thông thường của Java, kết quả encode không tự thêm BOM cho phần mở đầu. Nếu giao thức có quy định BOM, xử lý nó **theo đúng định dạng**.

Trong bài kiểm thử byte-level, luôn so sánh byte dưới dạng hex thay vì cố in byte nhị phân trực tiếp ra console.

## 10. Những ngoại lệ về định dạng cần nhớ

### 10.1. `Properties.load(InputStream)` dùng ISO-8859-1 theo hợp đồng riêng

Một ngoại lệ quan trọng với suy nghĩ “JDK mới thì mọi văn bản đều tự là UTF-8” là:

```java
var properties = new java.util.Properties();
try (var input = java.nio.file.Files.newInputStream(path)) {
    properties.load(input);
}
```

Với `Properties.load(InputStream)`, định dạng được đặc tả dùng **ISO-8859-1**, và các ký tự ngoài phạm vi đó có thể được biểu diễn bằng Unicode escapes. **JEP 400 không thay đổi hợp đồng của overload này thành UTF-8.**

Nếu chính file `.properties` của ứng dụng được quản lý ở dạng UTF-8 thực sự và bạn muốn giải mã theo UTF-8, hãy chọn overload `load(Reader)` với Reader có charset rõ ràng:

```java
var properties = new java.util.Properties();
try (var reader = java.nio.file.Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

Hai snippet là **mã đặt trong phương thức** có biến `path` kiểu `Path`, xử lý hoặc khai báo `IOException`, cùng các import phù hợp. Dù tên file đều có phần mở rộng `.properties`, **overload API mới là thứ quyết định cách giải mã trong ví dụ**.

### 10.2. Console không phải file text thông thường

`System.out`, `System.err` và các luồng console có thể dùng charset do môi trường đầu cuối quyết định. Việc file được ghi UTF-8 không bảo đảm một terminal cụ thể sẽ **hiển thị** dấu tiếng Việt đúng nếu môi trường đầu ra đang dùng bộ mã khác.

Khi debug lỗi hiển thị:

- Kiểm tra file byte/charset đọc ghi riêng.
- Kiểm tra charset của console và công cụ hiển thị riêng.
- Đừng vội thay đổi cách lưu file chỉ vì terminal đang hiển thị sai.

Một chương trình có thể **lưu đúng byte UTF-8** trong file nhưng log trực tiếp lên console bị lỗi chữ do quy ước output khác. Ngược lại, console hiển thị ổn không đủ chứng minh file đã được mã hóa đúng.

### 10.3. Charset và Unicode normalization là hai vấn đề khác nhau

Hai chuỗi có thể biểu diễn ký tự nhìn tương tự nhưng khác dãy Unicode code points, ví dụ chữ có dấu ở dạng *composed* hoặc *decomposed*. Chuyển cả hai sang UTF-8 **không tự làm chúng bằng nhau** về mặt `String.equals`. Khi ứng dụng cần chuẩn hóa Unicode để so sánh/tra cứu, hãy xem xét `java.text.Normalizer` theo chính sách nghiệp vụ, **tách biệt** với encode/decode bằng `StandardCharsets`.

Tương tự, **charset** không quy định line ending (LF/CRLF). Việc dùng `UTF_8` không tự động thống nhất mọi `\n` hoặc `\r\n` trong file.

## 11. Chương trình Java 17+ hoàn chỉnh và kiểm chứng

Lưu nội dung sau trong tệp **`CharsetExplicitDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class CharsetExplicitDemo {
    public static void main(String[] args) throws Exception {
        String text = "Tiếng Việt: cà phê ☕";
        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        String restored = new String(utf8, StandardCharsets.UTF_8);

        System.out.println("charset=" + StandardCharsets.UTF_8.name());
        System.out.println("roundTrip=" + text.equals(restored));
        System.out.println("utf8Length=" + utf8.length);
        System.out.println("cafeHex=" + HexFormat.of().formatHex(
                "café".getBytes(StandardCharsets.UTF_8)));

        byte[] cafeBytes = "café".getBytes(StandardCharsets.UTF_8);
        String mojibake = new String(
                cafeBytes, StandardCharsets.ISO_8859_1);
        System.out.println(
                "wrongDecoderMatches=" + "café".equals(mojibake));

        System.out.println("latin1EuroHex=" + HexFormat.of().formatHex(
                "€".getBytes(StandardCharsets.ISO_8859_1)));

        var strictEncoder = StandardCharsets.ISO_8859_1.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            strictEncoder.encode(CharBuffer.wrap("€"));
        } catch (CharacterCodingException ex) {
            System.out.println(
                    "strictEncode=" + ex.getClass().getSimpleName());
        }

        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
        String replaced = new String(
                invalidUtf8, StandardCharsets.UTF_8);
        System.out.println(
                "lenientHasReplacement=" + replaced.contains(String.valueOf((char) 0xFFFD)));

        var strictDecoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            strictDecoder.decode(ByteBuffer.wrap(invalidUtf8));
        } catch (CharacterCodingException ex) {
            System.out.println(
                    "strictDecode=" + ex.getClass().getSimpleName());
        }

        Path path = Files.createTempFile("charset-demo-", ".txt");
        try {
            try (BufferedWriter writer =
                    Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
                writer.write(text);
            }
            try (BufferedReader reader =
                    Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                System.out.println("bufferedFileRoundTrip=" +
                        text.equals(reader.readLine()));
            }

            Files.writeString(path, text, StandardCharsets.UTF_8);
            System.out.println("stringFileRoundTrip=" +
                    text.equals(Files.readString(
                            path, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(path);
        }

        System.out.println("utf16Hex=" + HexFormat.of().formatHex(
                "A".getBytes(StandardCharsets.UTF_16)));
        System.out.println("utf16LeHex=" + HexFormat.of().formatHex(
                "A".getBytes(StandardCharsets.UTF_16LE)));
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac --release 17 -encoding UTF-8 CharsetExplicitDemo.java
java CharsetExplicitDemo
```

**Stdout chính xác của chương trình:**

```text
charset=UTF-8
roundTrip=true
utf8Length=28
cafeHex=636166c3a9
wrongDecoderMatches=false
latin1EuroHex=3f
strictEncode=UnmappableCharacterException
lenientHasReplacement=true
strictDecode=MalformedInputException
bufferedFileRoundTrip=true
stringFileRoundTrip=true
utf16Hex=feff0041
utf16LeHex=4100
```

### Phân tích kết quả

1. `roundTrip=true`: văn bản tiếng Việt và ký hiệu cà phê được mã hóa rồi giải mã bằng **cùng UTF-8** nên khớp.
2. `utf8Length=28`: tổng byte thực tế của chuỗi UTF-8, **không** lấy từ `String.length()`.
3. `cafeHex=636166c3a9`: `café` có ba byte ASCII cộng hai byte cho `é`.
4. `wrongDecoderMatches=false`: cùng các byte nhưng giải mã theo ISO-8859-1 cho văn bản khác.
5. `latin1EuroHex=3f`: overload `getBytes(ISO_8859_1)` dùng byte thay thế cho ký tự `€` không thể mã hóa.
6. `strictEncode=UnmappableCharacterException`: encoder cấu hình `REPORT` từ chối ký tự không biểu diễn được, thay vì lặng lẽ thay thế.
7. `lenientHasReplacement=true` và `strictDecode=MalformedInputException`: hai chính sách xử lý **cùng byte UTF-8 lỗi**.
8. Hai dòng `bufferedFileRoundTrip` và `stringFileRoundTrip` là `true` vì cả bên ghi và đọc đều chỉ định UTF-8; chương trình tạo file tạm và xóa trong `finally`.
9. `utf16Hex=feff0041` và `utf16LeHex=4100`: byte-order mark và thứ tự byte có thể làm byte output khác nhau dù ký tự gốc cùng là `A`.

**Về phiên bản:** `HexFormat` và `Files.readString/writeString` là API của JDK mới hơn Java 10 (`HexFormat` từ Java 17; `readString/writeString` từ Java 11). Chúng được dùng để làm ví dụ đầy đủ **Java 17+**; trọng tâm `StandardCharsets`, `String.getBytes(Charset)` và `Files.newBufferedReader/Writer` vẫn dùng được trên **Java 10**. Không cần bật preview.

## 12. Tình huống thực tế và cách áp dụng

### 12.1. File cấu hình và file dữ liệu trao đổi giữa dịch vụ

Khi bạn quản lý định dạng:

```java
try (var writer = Files.newBufferedWriter(
        outputPath, StandardCharsets.UTF_8)) {
    writer.write(content);
}
```

Đây là đoạn minh họa trong một phương thức: `outputPath` là `Path`, `content` là `String` và cần import/ngoại lệ tương ứng. Quy tắc quan trọng là **ghi rõ encoding trong contract của file**. Bên đọc phải dùng đúng charset theo contract đó.

### 12.2. Đọc dữ liệu lịch sử theo encoding được khai báo

Nếu hệ thống cũ đưa file ISO-8859-1 theo hợp đồng:

```java
String text = Files.readString(
        legacyPath, StandardCharsets.ISO_8859_1);
```

Không được “sửa cho hiện đại” thành UTF-8 nếu byte nguồn chưa được chuyển mã. Khi muốn chuyển sang định dạng mới:

```java
String text = Files.readString(
        legacyPath, StandardCharsets.ISO_8859_1);

Files.writeString(
        targetPath, text, StandardCharsets.UTF_8);
```

Đây là một **quy trình transcoding**: decode theo charset cũ, sau đó encode sang UTF-8. Cả hai đoạn giả định Java 11+ và có xử lý `IOException`.

### 12.3. Dữ liệu HTTP hoặc queue

Nếu protocol/metadata quy định UTF-8, ghi:

```java
byte[] requestBody = jsonText.getBytes(StandardCharsets.UTF_8);
```

Với byte nhận về:

```java
String responseBody = new String(
        responseBytes, StandardCharsets.UTF_8);
```

Đây là minh họa ý tưởng; ứng dụng thực tế phải **tuân theo đặc tả của định dạng và Content-Type/encoding metadata phù hợp**, giới hạn kích thước payload, xử lý stream và lỗi hợp lý. Không tự đoán charset chỉ bằng tên file hay cảm giác rằng nội dung “trông giống JSON”.

### 12.4. Khi hiệu suất quan trọng

Nếu đọc file lớn, đừng nạp toàn bộ file vào `String` chỉ để chuyển mã. Dùng Reader/Writer với charset tường minh, xử lý theo khối hoặc theo dòng, và giới hạn tài nguyên. Những lựa chọn này ảnh hưởng hiệu năng và memory usage; `StandardCharsets.UTF_8` chỉ giải quyết **quy tắc mã hóa**, không tự thay thế streaming/buffering.

## 13. Lỗi phổ biến

**Lỗi 1 — Gọi `getBytes()`/`new String(bytes)` không tham số ở ranh giới dữ liệu.**  
Có thể phụ thuộc default charset hoặc thiết lập runtime. Sửa bằng `getBytes(StandardCharsets.UTF_8)` và `new String(bytes, StandardCharsets.UTF_8)` theo contract.

**Lỗi 2 — Nghĩ từ Java 18 mọi byte đầu vào đều là UTF-8.**  
Không. JEP 400 thay đổi default charset của những API chịu ảnh hưởng, **không chuyển mã các file cũ** hoặc thay đổi charset đặc thù của từng định dạng.

**Lỗi 3 — Dùng `ISO_8859_1` hoặc `US_ASCII` cho văn bản tiếng Việt đầy đủ.**  
Các charset đó không biểu diễn được mọi ký tự. `String.getBytes(Charset)` có thể **thay thế âm thầm**; nếu cần giữ nguyên dữ liệu, chọn UTF-8 hoặc strict encoder/report lỗi.

**Lỗi 4 — Coi byte hợp lệ theo một charset là đúng nội dung.**  
Byte UTF-8 giải mã theo ISO-8859-1 có thể cho mojibake nhưng không ném ngoại lệ. Cần biết charset gốc.

**Lỗi 5 — Nhầm chuẩn hóa Unicode với charset.**  
UTF-8 encode/decode không tự biến các biến thể Unicode normalization thành cùng một chuỗi ký tự; đây là một bước xử lý riêng khi cần.

**Lỗi 6 — Dùng `Files.readString` trong mã phải chạy Java 10.**  
API này có từ Java 11. Nếu cần tương thích Java 10, dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)`, `InputStreamReader` hoặc các API phù hợp có sẵn.

**Lỗi 7 — Mở file bằng `newBufferedReader` không Charset và nghĩ nó dùng charset platform.**  
Overload `Files.newBufferedReader(Path)` được đặc tả dùng UTF-8, **khác** các API truyền thống dựa vào default charset. Không đánh đồng những overload có cùng mục đích đọc file.

**Lỗi 8 — Coi UTF-16LE và UTF-16BE tương đương ở mức byte.**  
Sai: byte order khác nhau. Nếu protocol có BOM hoặc yêu cầu endian cụ thể, dùng đúng charset và kiểm chứng byte.

**Lỗi 9 — Đem binary qua `new String(..., UTF_8)` để lưu an toàn.**  
Không bảo toàn dãy byte không phải text. Dữ liệu nhị phân phải xử lý bằng API byte stream.

**Lỗi 10 — Xác định encoding của file chỉ dựa trên console.**  
Console có charset riêng; file có thể đúng UTF-8 nhưng log hiển thị sai. Kiểm tra byte file và thiết lập output riêng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao nên viết `text.getBytes(StandardCharsets.UTF_8)` thay cho `text.getBytes()` khi lưu file trao đổi giữa máy?  
**Đáp án:** Vì codec được chỉ định tường minh, không phụ thuộc default charset mà runtime đang dùng. Bên đọc có thể tuân theo cùng contract.

**Câu 2.** Từ JDK 18, default charset thường là UTF-8. Có cần ghi rõ `StandardCharsets.UTF_8` nữa không?  
**Đáp án:** Rất nên khi có hợp đồng dữ liệu. Nó giúp code tự mô tả, tránh lệ thuộc cấu hình tương thích và không nhầm với các API có quy tắc charset riêng.

**Câu 3.** Tại sao `new String(utf8Bytes, ISO_8859_1)` có thể sai dấu mà không báo ngoại lệ?  
**Đáp án:** ISO-8859-1 định nghĩa ký tự cho mọi giá trị byte đơn; byte UTF-8 nhiều byte được hiểu như nhiều ký tự Latin-1 riêng rẽ.

**Câu 4.** `"€".getBytes(StandardCharsets.ISO_8859_1)` luôn ném lỗi vì `€` không thể mã hóa?  
**Đáp án:** Không. `getBytes(Charset)` dùng replacement khi không mã hóa được; dùng `CharsetEncoder` với `CodingErrorAction.REPORT` nếu muốn exception.

**Câu 5.** `Files.readString(path)` có dùng platform default charset giống `new String(byte[])` trên Java 10–17 không?  
**Đáp án:** Không. `Files.readString` chỉ xuất hiện từ Java 11 và overload không Charset được đặc tả dùng UTF-8. `new String(byte[])` dùng default charset của runtime.

**Câu 6.** `Properties.load(InputStream)` có chuyển sang UTF-8 chỉ vì chạy JDK 18+ không?  
**Đáp án:** Không. Overload nhận `InputStream` có hợp đồng ISO-8859-1 riêng. Muốn đọc properties UTF-8, có thể dùng `load(Reader)` với Reader giải mã tường minh UTF-8.

**Câu 7.** Nếu đầu vào là dữ liệu ZIP, có dùng `new String(zipBytes, UTF_8)` rồi `getBytes(UTF_8)` để giữ nguyên không?  
**Đáp án:** Không. ZIP là binary, byte bất kỳ có thể không là UTF-8 hợp lệ. Dùng API byte/binary thích hợp.

**Câu 8.** Vì sao `utf8Bytes.length` khác `string.length()`?  
**Đáp án:** `String.length()` đếm UTF-16 code units trong chuỗi Java; UTF-8 mã hóa Unicode thành số byte biến thiên theo ký tự.

## 15. Ghi nhớ

1. **`StandardCharsets` là tập hằng `Charset` chuẩn, ổn định từ Java 7 và còn áp dụng trong Java 10+.** Dùng `StandardCharsets.UTF_8` khi hợp đồng dữ liệu yêu cầu UTF-8.
2. Ở mọi ranh giới **text ↔ bytes**, chỉ định cùng một charset đúng định dạng cho encode/decode. Đừng mặc định byte từ nguồn bên ngoài tự là UTF-8.
3. **JDK 18+** áp dụng JEP 400 cho default charset của nhiều Java SE API; Java 10–17 có thể phụ thuộc môi trường. Điều này **không** làm thay đổi encoding thực tế của file cũ, console hoặc API có quy tắc riêng.
4. Các overload `Files.newBufferedReader/Writer` không Charset đã được quy định dùng UTF-8; `Files.readString/writeString` xuất hiện từ Java 11 và cũng dùng UTF-8 theo mặc định.
5. `String.getBytes(Charset)` và `new String(bytes, Charset)` có thể **thay thế dữ liệu lỗi**. Cần từ chối byte hoặc ký tự không hợp lệ thì dùng `CharsetEncoder`/`CharsetDecoder` với `CodingErrorAction.REPORT` hoặc API I/O có hợp đồng báo lỗi phù hợp.
6. UTF-8, ISO-8859-1, ASCII và các biến thể UTF-16 **không thể hoán đổi tùy tiện**. Với UTF-16, cần quan tâm endian/BOM; với binary, không dùng String như một container byte.
7. **Charset, Unicode normalization, line ending và encoding của console** là các lớp vấn đề riêng. Chọn đúng từng tầng để mã nguồn đáng tin và dễ bảo trì.

## Tài liệu tham khảo chính thức còn áp dụng

- Java SE 26 API — `StandardCharsets`, các hằng `Charset` chuẩn: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html
- Java SE 26 API — `Charset`, standard charsets và quy tắc encode/decode: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/Charset.html
- Java SE 26 API — `String.getBytes(Charset)` và `String(byte[], Charset)`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html
- Java SE 26 API — `Files.newBufferedReader`, `newBufferedWriter`, `readString` và `writeString`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html
- Java SE 26 API — `CharsetEncoder`, `CharsetDecoder` và `CodingErrorAction`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CodingErrorAction.html
- OpenJDK JEP 400 — UTF-8 by Default (Java 18): https://openjdk.org/jeps/400
- Oracle JDK 26 Internationalization Guide — charset mặc định và console: https://docs.oracle.com/en/java/javase/26/intl/internationalization-guide.pdf
- Java SE 26 API — `Properties.load(InputStream)`/`load(Reader)`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Properties.html
