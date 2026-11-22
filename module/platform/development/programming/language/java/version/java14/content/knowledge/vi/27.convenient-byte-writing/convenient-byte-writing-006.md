# Chọn bảng mã tường minh trước khi tạo dữ liệu byte

> **Java 14 → Ghi byte tiện dụng.** Khi chuyển văn bản thành dữ liệu byte, hãy xác định **Charset** trước khi gọi `String.getBytes(Charset)`, rồi mới ghi các bytes đã tạo bằng `ByteArrayOutputStream.writeBytes(byte[])`, `OutputStream.write(byte[])` hoặc `Files.write`. Ví dụ phổ biến là `text.getBytes(StandardCharsets.UTF_8)`. `ByteArrayOutputStream.writeBytes(byte[])` được giới thiệu từ **Java 11**, đã có trong Java 14 và vẫn được hỗ trợ ở JDK hiện đại; **không được gọi nhầm là API mới từ Java 14**. Bài chỉ dùng kiến thức còn áp dụng, với ví dụ độc lập Java 17+, các quy tắc Unicode hiện hành và không phụ thuộc bảng mã mặc định khó kiểm soát.

## 1. Mục tiêu

Học xong, bạn có thể:

1. Phân biệt `String`, Unicode code points, UTF-16 code units, `Charset` và `byte[]`.
2. Chọn `StandardCharsets.UTF_8` khi giao thức/file quy định UTF-8; chọn charset khác khi **hợp đồng dữ liệu thực sự yêu cầu**.
3. Tạo dữ liệu byte bằng `String.getBytes(Charset)` trước khi ghi bằng `ByteArrayOutputStream.writeBytes(byte[])`.
4. Biết `writeBytes(byte[])` không tự mã hóa chuỗi, không tự thêm newline, BOM, length prefix hoặc ký tự kết thúc.
5. Tính **byte length** từ `byte[].length`, không từ `String.length()` khi dữ liệu có Unicode.
6. Giải thích khác biệt `getBytes()` với `getBytes(StandardCharsets.UTF_8)`, kể cả mốc **JEP 400 — UTF-8 by Default (JDK 18)**.
7. Phân biệt `ByteArrayOutputStream.writeBytes(byte[])` với `DataOutputStream.writeBytes(String)` và `DataOutputStream.writeUTF(String)`.
8. Phát hiện dữ liệu bị thay thế khi charset không mã hóa được ký tự; dùng `CharsetEncoder` với `CodingErrorAction.REPORT` để **không chấp nhận mất dữ liệu âm thầm**.
9. Ghi file/stream có charset rõ ràng và đọc lại bằng charset tương ứng.
10. Kiểm thử bằng bytes/hex, round-trip, ký tự có dấu, emoji, BOM, newline và Unicode normalization.

## 2. Từ văn bản đến byte: diễn ra những bước nào?

`String` trong Java lưu văn bản dưới dạng chuỗi **UTF-16 code units**. Một `char` là một code unit 16 bit; không nhất thiết tương ứng với một Unicode code point. Chẳng hạn, emoji ngoài Basic Multilingual Plane thường được biểu diễn bằng **hai `char`** (surrogate pair).

Khi dữ liệu được truyền qua mạng hoặc lưu thành file, bên nhận thấy **bytes**. Mỗi charset quy định cách chuyển các ký tự sang bytes. Cùng một từ có thể có nhiều byte sequence nếu dùng các charset khác nhau.

~~~text
String (văn bản Unicode)
       |
       | chọn charset trước
       v
Charset encoder (ví dụ UTF-8)
       |
       v
byte[] (bytes đã mã hóa)
       |
       +--> ByteArrayOutputStream.writeBytes(bytes)
       +--> OutputStream.write(bytes)
       +--> Files.write(path, bytes)
       |
       v
bộ nhớ / file / socket
       |
       v
Charset decoder (phải phù hợp bên ghi)
       |
       v
String được tái tạo
~~~

**Sai charset khi decode** có thể sinh *mojibake* — văn bản bị lỗi hiển thị. Ngược lại, một `byte[]` chứa hình ảnh, file ZIP, mã băm hoặc định dạng nhị phân không nên bị chuyển thành `String` nếu format không nói đó là text.

| Khái niệm/API | Làm gì? | Không làm gì? |
| --- | --- | --- |
| `String` | Biểu diễn văn bản | Không tự xác định định dạng file. |
| `Charset` | Xác định quy tắc chuyển text ↔ bytes | Không tự ghi stream. |
| `StandardCharsets.UTF_8` | Hằng charset UTF-8 chuẩn | Không sửa Unicode malformed. |
| `String.getBytes(Charset)` | Tạo `byte[]` mới từ String | Không ghi file. |
| `ByteArrayOutputStream.writeBytes(byte[])` | Ghi nguyên dãy bytes vào buffer | Không nhận `String` hay chọn charset. |
| `OutputStream.write(byte[])` | Ghi bytes tới output stream bất kỳ | Không encode text cho bạn. |
| `new String(bytes, Charset)` | Decode bytes thành String | Không đoán đúng charset nếu caller chọn sai. |
| `Files.write(path, bytes)` | Lưu bytes nguyên trạng | Không mã hóa văn bản. |
| `Files.writeString(path, text, cs)` | Encode text theo `cs` rồi ghi file | Không phải API viết giao thức nhị phân tùy ý. |

## 3. Chọn bảng mã (Charset) theo hợp đồng dữ liệu

**Ưu tiên UTF-8 cho text mới**, trừ khi giao thức/format đang tích hợp quy định charset khác. Hãy thống nhất quy tắc này giữa người gửi và người nhận, cùng với quy tắc BOM, newline và normalization nếu cần tính tương thích byte-for-byte.

Các charset chuẩn do `java.nio.charset.StandardCharsets` cung cấp:

| Hằng | Khi nào dùng? | Giới hạn |
| --- | --- | --- |
| `UTF_8` | Text Unicode, JSON, văn bản giao tiếp mới | 1–4 bytes cho một Unicode scalar value. |
| `US_ASCII` | Protocol quy định ASCII 7 bit | Không chứa `é`, chữ Việt và emoji. |
| `ISO_8859_1` | Format/legacy protocol quy định Latin-1 | Không thể biểu diễn đủ Unicode. |
| `UTF_16BE` | Protocol yêu cầu UTF-16 big-endian | Thứ tự bytes phải thống nhất. |
| `UTF_16LE` | Protocol yêu cầu UTF-16 little-endian | Không giống UTF-8. |
| `UTF_16` | Protocol quy định dạng UTF-16 và xử lý byte-order mark thích hợp | Phải hiểu quy tắc BOM. |

Hằng `StandardCharsets.UTF_8` an toàn hơn việc tự ghép chuỗi tên charset: nó có type `Charset`, được JVM chuẩn bảo đảm hỗ trợ và không cần overload có thể ném `UnsupportedEncodingException` vì tên encoding không tồn tại.

### Pattern đúng

~~~java
String text = "Hello";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

ByteArrayOutputStream output = new ByteArrayOutputStream();
output.writeBytes(bytes);
~~~

Đây là **mảnh code** cần import `java.io.ByteArrayOutputStream` và `java.nio.charset.StandardCharsets`.

Trình tự rõ ràng:

1. Đặc tả payload yêu cầu UTF-8.
2. `getBytes(UTF_8)` mã hóa `String` thành một mảng byte.
3. `writeBytes(bytes)` đưa đúng mảng đó vào bộ đệm, theo thứ tự.
4. Khi đọc ngược, sử dụng `new String(bytes, UTF_8)` hoặc decoder đúng charset.

### Pattern sai

~~~java
output.writeBytes(text); // KHÔNG COMPILE: yêu cầu byte[], không phải String
~~~

Vì `ByteArrayOutputStream.writeBytes` chỉ nhận `byte[]`, bạn phải quyết định encoding **trước** khi tạo byte data.

## 4. Gắn đúng phiên bản API

Trong bài Java 14, cần tránh hiểu nhầm mốc xuất hiện các API:

| API | Có từ | Còn áp dụng hiện nay? |
| --- | --- | --- |
| `String.getBytes(Charset)` | Java 1.6 | Có. |
| `StandardCharsets.UTF_8` | Java 7 | Có. |
| `ByteArrayOutputStream.writeBytes(byte[])` | **Java 11** | Có, đã tồn tại ở Java 14. |
| `ByteArrayOutputStream.toString(Charset)` | Java 10 | Có. |
| `Files.writeString(Path, CharSequence, Charset)` | Java 11 | Có. |
| `OutputStream.write(byte[])` | Từ API OutputStream cơ bản | Có. |
| `HexFormat` | **Java 17** | Có; các ví dụ dùng `--release 17`. |
| UTF-8 làm default charset theo `JEP 400` | **JDK 18** | Quy tắc hiện hành cho các API sử dụng default charset. |

**Đừng tuyên bố Java 14 “ra mắt `writeBytes`”**: phương thức này đã có từ Java 11. Bài Java 14 học cách dùng nó an toàn, với charset được quyết định đúng.

Nếu thực sự phải biên dịch source ở `--release 14`, hãy thay phần xuất hex dùng `HexFormat` (mới từ 17) bằng bộ định dạng hex tương thích; logic `getBytes(UTF_8)` và `writeBytes(byte[])` vẫn hợp lệ.

## 5. Ví dụ độc lập 1 — `String.length()` khác độ dài bytes

Tạo tệp **`ExplicitCharsetBasicsDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class ExplicitCharsetBasicsDemo {
    public static void main(String[] args) {
        String text = "Aé€🙂";
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        System.out.println("utf16Units=" + text.length());
        System.out.println("codePoints=" +
                text.codePointCount(0, text.length()));
        System.out.println("utf8Bytes=" + bytes.length);
        System.out.println("hex=" +
                HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(bytes));
        System.out.println("roundTrip=" +
                text.equals(new String(bytes, StandardCharsets.UTF_8)));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ExplicitCharsetBasicsDemo.java
java ExplicitCharsetBasicsDemo
~~~

**Stdout chính xác:**

~~~text
utf16Units=5
codePoints=4
utf8Bytes=10
hex=41 C3 A9 E2 82 AC F0 9F 99 82
roundTrip=true
~~~

Giải thích byte-level:

- `A` (U+0041) là một code unit, một code point, **1 byte** `41`.
- `é` (U+00E9) là một code unit, **2 bytes** `C3 A9`.
- `€` (U+20AC) là một code unit, **3 bytes** `E2 82 AC`.
- `🙂` (U+1F642) là hai UTF-16 code units, một code point, **4 bytes** `F0 9F 99 82`.

Do đó, với chuỗi trên, **`String.length()==5`** nhưng **`bytes.length==10`**. Để ghi length-prefix của payload UTF-8, phải dùng **`bytes.length`**, không dùng `text.length()`.

Demo in hex và boolean thay vì in trực tiếp Unicode vào terminal, nên stdout không phụ thuộc font hoặc cài đặt terminal.

## 6. Ví dụ độc lập 2 — `ByteArrayOutputStream.writeBytes` nối các dãy byte

Tạo tệp **`WriteBytesUtf8Demo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class WriteBytesUtf8Demo {
    public static void main(String[] args) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        output.writeBytes("Hi ".getBytes(StandardCharsets.UTF_8));
        output.writeBytes("é".getBytes(StandardCharsets.UTF_8));

        byte[] result = output.toByteArray();

        System.out.println("bytes=" + result.length);
        System.out.println("hex=" +
                HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(result));
        System.out.println("decodedCorrect=" +
                "Hi é".equals(
                        output.toString(StandardCharsets.UTF_8)));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 WriteBytesUtf8Demo.java
java WriteBytesUtf8Demo
~~~

**Stdout chính xác:**

~~~text
bytes=5
hex=48 69 20 C3 A9
decodedCorrect=true
~~~

`"Hi "` có 3 bytes ASCII, `"é"` có 2 bytes UTF-8, tổng 5. `writeBytes` ghi các bytes lần lượt, **không thêm newline, dấu phân cách, BOM hoặc length prefix**.

`output.toByteArray()` trả một bản sao mảng hiện có. `output.toString(StandardCharsets.UTF_8)` decode bytes với đúng charset. Trong khi đó, `output.toString()` không có tham số dùng default charset; không nên dựa vào overload này khi payload có contract UTF-8 cụ thể.

### Khi chỉ có `OutputStream`

~~~java
OutputStream out = Files.newOutputStream(path);
out.write(text.getBytes(StandardCharsets.UTF_8));
~~~

Đây là mảnh code, cần import tương ứng và `try-with-resources` để đóng stream. **`OutputStream` không có `writeBytes(byte[])`**; phương thức tổng quát là `write(byte[])`. Các file/network streams có thể ném `IOException`, khác với `ByteArrayOutputStream` ghi bộ nhớ.

## 7. Ví dụ độc lập 3 — UTF-8 và Latin-1 có bytes khác nhau

Tạo tệp **`CharsetMismatchDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class CharsetMismatchDemo {
    public static void main(String[] args) {
        String text = "Café";

        byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
        byte[] latin1 = text.getBytes(StandardCharsets.ISO_8859_1);
        HexFormat hex = HexFormat.ofDelimiter(" ").withUpperCase();

        System.out.println("utf8=" + hex.formatHex(utf8));
        System.out.println("latin1=" + hex.formatHex(latin1));
        System.out.println("utf8RoundTrip=" +
                text.equals(new String(utf8,
                        StandardCharsets.UTF_8)));
        System.out.println("latin1RoundTrip=" +
                text.equals(new String(latin1,
                        StandardCharsets.ISO_8859_1)));
        System.out.println("wrongDecodeEqual=" +
                text.equals(new String(utf8,
                        StandardCharsets.ISO_8859_1)));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CharsetMismatchDemo.java
java CharsetMismatchDemo
~~~

**Stdout chính xác:**

~~~text
utf8=43 61 66 C3 A9
latin1=43 61 66 E9
utf8RoundTrip=true
latin1RoundTrip=true
wrongDecodeEqual=false
~~~

UTF-8 dùng `C3 A9` cho `é`, Latin-1 dùng `E9`. Khi dữ liệu UTF-8 bị giải mã nhầm bằng Latin-1, văn bản kết quả **không bằng chuỗi gốc**.

**Không test chỉ `"ABC"` để xác nhận charset.** ASCII có bytes giống nhau trong nhiều encoding, khiến lỗi không lộ ra. Test Unicode có dấu, emoji hoặc ký tự đặc thù của dữ liệu thật.

Không “sửa” mojibake bằng cách tự ghép ký tự thay thế nếu chưa biết nguồn encoding. Phải xem protocol, file metadata hoặc hợp đồng bên gửi để xác định charset đúng.

## 8. Default charset và JEP 400: hiểu quy tắc hiện hành

Có hai overload:

~~~java
byte[] implicit = text.getBytes();
byte[] explicit = text.getBytes(StandardCharsets.UTF_8);
~~~

Đây là mảnh code với biến `text` đã tồn tại.

- `getBytes()` dùng `Charset.defaultCharset()`.
- `getBytes(UTF_8)` mã hóa UTF-8 **đúng theo lựa chọn của caller**.
- Trước JDK 18, default charset thường phụ thuộc OS/locale/runtime configuration.
- **JEP 400**, được triển khai từ JDK 18, quy định **UTF-8 mặc định** cho các Java SE APIs phụ thuộc default charset, có cơ chế tương thích và chi tiết cấu hình theo phiên bản.
- Riêng `Files.writeString(path, text)` và `Files.readString(path)` được **đặc tả là UTF-8** từ lúc được bổ sung vào Java 11; không phải mọi API không có tham số Charset đều dùng default charset.

Vì vậy, dù JDK hiện đại thường đã có default UTF-8, **định dạng dữ liệu chia sẻ vẫn nên ghi rõ `StandardCharsets.UTF_8`** ở nơi chuyển text ↔ bytes.

### Vì sao vẫn ghi rõ UTF-8 khi JDK 25 mặc định UTF-8?

1. Code có thể cần chạy với minimum JDK thấp hơn 18.
2. Môi trường hoặc thiết lập tương thích có thể làm hành vi default khác dự đoán.
3. Người review nhìn thấy rõ **contract của protocol** mà không cần tra JDK version.
4. Hash/signature cần byte-for-byte reproducibility.
5. API consumer ở hệ thống khác không có khái niệm “default charset của Java process này”.

Đừng coi việc đặt `-Dfile.encoding=UTF-8` cho toàn process là thay thế hoàn chỉnh cho thiết kế encoding tường minh trong serialization.

## 9. Không phải charset nào cũng mã hóa được mọi ký tự

Theo Javadoc, `String.getBytes(Charset)` **thay** các chuỗi malformed hoặc ký tự unmappable bằng replacement bytes mặc định của charset. Điều này có thể gây **mất dữ liệu âm thầm**.

Ví dụ `US_ASCII` chỉ biểu diễn các ký tự ASCII, không biểu diễn được `é`, tiếng Việt hoặc emoji. Nếu text cần giữ nguyên tuyệt đối, thay vì chấp nhận replacement hãy dùng `CharsetEncoder` với `CodingErrorAction.REPORT`.

### Ví dụ độc lập 4 — Strict encoding từ chối ký tự không biểu diễn được

Tạo tệp **`StrictCharsetEncoderDemo.java`**:

~~~java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class StrictCharsetEncoderDemo {
    public static void main(String[] args) {
        String text = "café";

        byte[] lossy = text.getBytes(StandardCharsets.US_ASCII);
        System.out.println("lossy=" +
                new String(lossy, StandardCharsets.US_ASCII));

        CharsetEncoder encoder =
                StandardCharsets.US_ASCII.newEncoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            encoder.encode(CharBuffer.wrap(text));
            System.out.println("strict=accepted");
        } catch (CharacterCodingException expected) {
            System.out.println("strict=rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 StrictCharsetEncoderDemo.java
java StrictCharsetEncoderDemo
~~~

**Stdout chính xác:**

~~~text
lossy=caf?
strict=rejected
~~~

Giải thích:

- Với `getBytes(US_ASCII)`, `é` không biểu diễn được, bị thay thành replacement `?` của US-ASCII.
- `CharsetEncoder` với `REPORT` cho malformed và unmappable input sẽ **ném `CharacterCodingException`** khi không encode hợp lệ được.
- Bắt đúng lớp exception, không so nguyên văn message vì message không phải hợp đồng ổn định.

### UTF-8 có thể có malformed input không?

Có. UTF-8 mã hóa mọi Unicode **scalar value**, nhưng một `String` Java có thể chứa unpaired UTF-16 surrogate, vốn không đại diện một scalar value hợp lệ. Khi cần bảo đảm không thay thế dữ liệu, vẫn có thể dùng:

~~~java
CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Đây là mảnh code cần các import như demo. Với dữ liệu không tin cậy, chọn **reject**, **replace** hay **report** là quyết định theo đặc tả, không để tình cờ phụ thuộc overload.

## 10. Ghi bytes hay ghi String vào file?

Hai lối đi đều đúng khi text và charset được chọn thống nhất:

~~~java
Files.write(path, text.getBytes(StandardCharsets.UTF_8));
Files.writeString(path, text, StandardCharsets.UTF_8);
~~~

Đây là **hai mảnh code** với `Path path`/`String text` và quản lý `IOException`. Thực tế phải chọn cách nào phù hợp, **không cần ghi đè cùng file hai lần** như hai lệnh minh họa liên tiếp.

| Nhu cầu | Phương thức | Kết quả |
| --- | --- | --- |
| Đã có binary `byte[]` | `Files.write(path, bytes)` | Ghi nguyên bytes. |
| Có text, format UTF-8 | `Files.writeString(path, text, UTF_8)` | Encoder UTF-8 ghi text. |
| Có text, dùng default overload `writeString` | `Files.writeString(path, text)` | Theo Javadoc vẫn là UTF-8. |
| Dữ liệu text lớn, ghi nhiều lần | `Files.newBufferedWriter(path, UTF_8)` | Writer mã hóa từng chunk/dòng. |
| Binary stream | `Files.newOutputStream(path)` | `OutputStream.write(bytes)`, tự quản lifecycle. |
| Đọc bytes rồi decode | `new String(bytes, UTF_8)` | Chọn đúng charset; strict decoder nếu cần reject malformed. |

**Line endings khác nhau theo API:** `Files.writeString` ghi đúng các ký tự xuống dòng đã có, không tự thêm newline; `Files.write(path, Iterable<CharSequence>, Charset)` ghi các dòng với line separator theo hợp đồng API. Khi byte output cần chính xác, test các bytes `0A` so với `0D 0A` thay vì chỉ nhìn file trong editor.

### Ví dụ độc lập 5 — Hai cách tạo cùng UTF-8 file content

Tạo tệp **`FilesUtf8RoundTripDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class FilesUtf8RoundTripDemo {
    public static void main(String[] args) throws Exception {
        String text = "Dữ liệu";
        Path bytesFile = Files.createTempFile("explicit-bytes-", ".bin");
        Path textFile = Files.createTempFile("explicit-text-", ".txt");

        try {
            byte[] payload = text.getBytes(StandardCharsets.UTF_8);
            Files.write(bytesFile, payload);
            Files.writeString(textFile, text, StandardCharsets.UTF_8);

            byte[] first = Files.readAllBytes(bytesFile);
            byte[] second = Files.readAllBytes(textFile);

            System.out.println("sameBytes=" + Arrays.equals(first, second));
            System.out.println("roundTrip=" +
                    text.equals(Files.readString(
                            textFile, StandardCharsets.UTF_8)));
        } finally {
            Files.deleteIfExists(bytesFile);
            Files.deleteIfExists(textFile);
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 FilesUtf8RoundTripDemo.java
java FilesUtf8RoundTripDemo
~~~

**Stdout chính xác nếu quyền I/O và filesystem bình thường:**

~~~text
sameBytes=true
roundTrip=true
~~~

`Files.write` không re-encode, còn `Files.writeString` mã hóa đúng UTF-8 được nêu tường minh; hai file có bytes bằng nhau. `Files.readString` giải mã bằng cùng charset nên nội dung trở lại đúng text gốc.

Dùng file tạm chỉ để demo; `finally` thực hiện cleanup. Với file lớn hoặc input không tin cậy, tránh `Files.readAllBytes` nếu không muốn giữ cả file trong RAM.

## 11. Streaming text: `OutputStreamWriter` với charset rõ ràng

Khi text được sinh thành nhiều mảnh hoặc payload rất lớn, có thể dùng `OutputStreamWriter` để mã hóa theo stream thay vì giữ toàn bộ một `byte[]`.

~~~java
try (Writer writer =
        new OutputStreamWriter(outputStream, StandardCharsets.UTF_8)) {
    writer.write(text);
}
~~~

Đây là **mảnh code**, cần import `Writer`, `OutputStreamWriter` và có `outputStream`/`text`. Đóng writer cũng **đóng output stream được bọc**; cần thiết kế quyền sở hữu stream rõ ràng.

### Ví dụ độc lập 6 — Writer tạo byte UTF-8 chính xác

Tạo tệp **`OutputStreamWriterUtf8Demo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class OutputStreamWriterUtf8Demo {
    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        try (Writer writer =
                new OutputStreamWriter(out, StandardCharsets.UTF_8)) {
            writer.write("Aé");
        }

        byte[] bytes = out.toByteArray();
        System.out.println("bytes=" + bytes.length);
        System.out.println("hex=" +
                HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(bytes));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 OutputStreamWriterUtf8Demo.java
java OutputStreamWriterUtf8Demo
~~~

**Stdout chính xác:**

~~~text
bytes=3
hex=41 C3 A9
~~~

Khi writer được đóng, bytes được flush ra `ByteArrayOutputStream`. Theo Javadoc, `ByteArrayOutputStream.close()` không có tác dụng làm mất dữ liệu, nhưng **không được khái quát** điều này cho file/socket stream. Với network stream, phải quyết định khi nào `flush`, khi nào `close`.

Không trộn `writer.write(...)` với `outputStream.write(...)` trên cùng sink một cách tùy tiện: buffering có thể làm thứ tự bytes không giống thứ tự lệnh gọi nếu chưa flush đúng.

## 12. Hai phương thức giống tên nhưng **khác về Unicode**

Có hai API cần phân biệt:

- `ByteArrayOutputStream.writeBytes(byte[])` nhận **bytes đã có**, ghi nguyên nội dung mảng (từ Java 11).
- `DataOutputStream.writeBytes(String)` nhận **String** nhưng theo Javadoc nó ghi **8 bit thấp của từng UTF-16 `char`**, không chọn một charset để encode Unicode.

Ví dụ mảnh code:

~~~java
byteOut.writeBytes("é".getBytes(StandardCharsets.UTF_8));
dataOut.writeBytes("é");
~~~

Giả định `byteOut` là `ByteArrayOutputStream` và `dataOut` là `DataOutputStream`. Dòng đầu ghi `C3 A9` (UTF-8). Dòng thứ hai ghi byte `E9` từ byte thấp của U+00E9; nếu dùng ký tự có code point ngoài dải 8 bit, nó có thể **mất dữ liệu**.

Cũng đừng nhầm:

~~~java
dataOut.writeUTF(text);
~~~

`DataOutputStream.writeUTF(String)` dùng **modified UTF-8** cùng phần prefix độ dài 2 bytes theo định dạng Java DataInput/DataOutput; **không phải raw UTF-8** do `text.getBytes(StandardCharsets.UTF_8)` tạo ra. Nó chỉ phù hợp khi giao thức thực sự yêu cầu modified UTF-8 và receiver đọc đúng bằng `DataInputStream.readUTF()`.

| API | Loại tham số | Trường hợp sử dụng |
| --- | --- | --- |
| `ByteArrayOutputStream.writeBytes(byte[])` | Bytes | Gom các byte chunks trong RAM. |
| `OutputStream.write(byte[])` | Bytes | Ghi ra file/network/stream. |
| `DataOutputStream.writeBytes(String)` | Text | Legacy low-byte behavior; **không dùng cho Unicode text tổng quát**. |
| `DataOutputStream.writeUTF(String)` | Text | Format đặc thù modified UTF-8 của Java, có prefix. |
| `OutputStreamWriter(out, UTF_8)` | Text dần dần | Ghi text streaming có charset. |

**Cẩn trọng:** chuyển `String` thành `byte[]` đúng cách là trách nhiệm của tầng **encoding**, không phải tầng **ghi bytes**.

## 13. Framing: tính độ dài theo bytes, không theo `String.length()`

Một giao thức thường cần length-prefix để receiver biết cần đọc bao nhiêu bytes. Nếu dùng UTF-8, length là **số bytes sau encoding**, không phải số `char`/code points.

Giả sử frame format:

~~~text
[4 bytes unsigned-like length stored as signed int, big-endian]
[length bytes of UTF-8 payload]
~~~

Nếu dùng kiểu `int` cho length, phải kiểm tra length không âm và không vượt giới hạn payload thiết kế. `DataOutputStream.writeInt(int)` ghi 4 bytes theo big-endian.

### Ví dụ độc lập 7 — Một frame UTF-8 trong bộ nhớ

Tạo tệp **`Utf8LengthPrefixDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class Utf8LengthPrefixDemo {
    public static void main(String[] args) throws Exception {
        String text = "Hé";
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(buffer)) {
            out.writeInt(payload.length);
            out.write(payload);
        }

        byte[] frame = buffer.toByteArray();
        System.out.println("payloadBytes=" + payload.length);
        System.out.println("frameBytes=" + frame.length);
        System.out.println("hex=" +
                HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(frame));

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(frame))) {
            int length = in.readInt();
            if (length < 0 || length > 1024
                    || length > in.available()) {
                throw new IOException("Invalid payload length");
            }

            byte[] received = new byte[length];
            in.readFully(received);

            System.out.println("roundTrip=" +
                    text.equals(new String(
                            received, StandardCharsets.UTF_8)));
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 Utf8LengthPrefixDemo.java
java Utf8LengthPrefixDemo
~~~

**Stdout chính xác:**

~~~text
payloadBytes=3
frameBytes=7
hex=00 00 00 03 48 C3 A9
roundTrip=true
~~~

Giải thích:

1. `"Hé"` có 2 UTF-16 code units, nhưng 3 bytes UTF-8: `48 C3 A9`.
2. `payload.length` trả `3` nên `writeInt(3)` ghi `00 00 00 03`.
3. `out.write(payload)` ghi đúng 3 bytes.
4. Tổng frame: 4 + 3 = 7 bytes.
5. Receiver đọc length có giới hạn, đọc đủ bytes và decode UTF-8.

**Giới hạn an toàn:** `in.available()` ở đây chỉ có ý nghĩa vì input là **ByteArrayInputStream với frame đã có đủ trong bộ nhớ**. Với socket, **không dùng `available()` để xác định message đã đến đủ**. Cần đọc theo length với timeout/EOF/error handling, giới hạn allocation và framing integrity.

Đừng cấp phát `new byte[length]` trực tiếp từ đầu vào không đáng tin mà không kiểm tra length: giá trị âm, quá lớn hoặc sai lệch có thể gây lỗi/cạn RAM.

## 14. Unicode normalization: cùng chữ hiển thị, bytes khác nhau

Chọn đúng charset vẫn chưa bảo đảm hai chuỗi **nhìn giống nhau** sẽ có bytes giống nhau. Unicode có thể biểu diễn `é` bằng:

- U+00E9 (một code point composed).
- U+0065 U+0301 (chữ `e` và combining accent).

Hai chuỗi hiển thị gần giống nhau nhưng khi encode UTF-8 có byte sequence khác nhau. Nếu đặc tả cần **canonical normalization**, chọn quy tắc như NFC **trước** khi tạo byte[].

### Ví dụ độc lập 8 — NFC và bytes

Tạo tệp **`UnicodeNormalizationDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Arrays;

public class UnicodeNormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        byte[] a = composed.getBytes(StandardCharsets.UTF_8);
        byte[] b = decomposed.getBytes(StandardCharsets.UTF_8);
        System.out.println("sameBefore=" + Arrays.equals(a, b));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        byte[] c = normalized.getBytes(StandardCharsets.UTF_8);
        System.out.println("sameAfter=" + Arrays.equals(a, c));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

**Stdout chính xác:**

~~~text
sameBefore=false
sameAfter=true
~~~

**Không tự normalize nếu format không yêu cầu.** Với chữ ký số, hashing hoặc định dạng canonical, thay đổi chuỗi trước encoding có thể thay đổi dữ liệu và phá tính tương thích. Hai phía phải thống nhất cả charset và normalization.

## 15. UTF-8 BOM, newline và Content-Type

### BOM

Byte-order mark thường gặp ở đầu một số file UTF-8 là `EF BB BF`. Nhưng:

~~~java
"Hello".getBytes(StandardCharsets.UTF_8)
~~~

không tự thêm BOM. Chỉ thêm BOM khi format quy định, không suy đoán từ phần mở rộng `.txt`. Khi decode bytes có BOM, một số API có thể giữ U+FEFF; đừng mặc định mọi bộ giải mã tự bỏ BOM.

### Line endings

`\n` trong UTF-8 là `0A`, còn `\r\n` là `0D 0A`. Đối với payload được ký/hash, đây là **hai byte sequence khác nhau**. `Files.writeString` ghi đúng line separators có trong `CharSequence`; những API ghi theo danh sách dòng có thể thêm separator theo quy tắc riêng.

### Metadata

Nếu protocol/HTTP response khai báo `charset=UTF-8`, bytes thực sự phải được encode UTF-8. Đặt tên header không tự chuyển Latin-1 bytes thành UTF-8. Với dữ liệu binary như ảnh/nén, không được gán charset chỉ để tiện gọi `new String(...)`.

## 16. Chọn API theo lượng dữ liệu

| Dữ liệu và kích thước | API nên chọn | Lưu ý |
| --- | --- | --- |
| Chuỗi nhỏ cần bytes để hash/gửi | `text.getBytes(UTF_8)` | Tạo mảng mới, rõ charset. |
| Nhiều `byte[]` nhỏ cần gom trong RAM | `ByteArrayOutputStream.writeBytes` | Buffer tăng theo tổng bytes. |
| Ghi bytes vào output stream tổng quát | `out.write(bytes)` | Xử lý `IOException`, flush/close. |
| File text nhỏ | `Files.writeString(path, text, UTF_8)` | Không cần tự tạo byte array nếu không dùng nó. |
| File nhị phân | `Files.write(path, bytes)` | Không thêm bước encode. |
| Text lớn/gồm nhiều chunk | `OutputStreamWriter` hoặc `BufferedWriter` với Charset | Không gom tất cả bytes trong RAM. |
| Đọc bytes về text | `new String(bytes, UTF_8)` | Dùng strict `CharsetDecoder` nếu phải từ chối malformed input. |
| Encoding lossless khi charset hạn chế | `CharsetEncoder(...REPORT)` | Bắt `CharacterCodingException`. |
| Giao thức length-prefix | Encode trước, ghi `payload.length` | Validate length và đặt kích thước tối đa. |

**ByteArrayOutputStream tự mở rộng buffer**, nên có thể tiêu thụ rất nhiều heap nếu đọc dữ liệu lớn hoặc không tin cậy. Với file/network streaming, đặt giới hạn số bytes và dùng cơ chế backpressure phù hợp thay vì gom vô hạn.

## 17. Lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `text.getBytes()` khi protocol quy định UTF-8 | Phụ thuộc default charset | `text.getBytes(StandardCharsets.UTF_8)`. |
| Gọi `output.writeBytes(text)` | Không compile; cần `byte[]` | Encode trước. |
| Gọi `OutputStream.writeBytes(bytes)` | Không có API trên kiểu `OutputStream` | `out.write(bytes)`. |
| Gọi `ByteArrayOutputStream.writeBytes` là tính năng mới Java 14 | Javadoc ghi **Since 11** | Ghi đúng lịch sử. |
| Nhầm `DataOutputStream.writeBytes(String)` là UTF-8 | Chỉ ghi byte thấp của từng `char` | Encode bằng Charset và `write(byte[])`. |
| Dùng `DataOutputStream.writeUTF` thay raw UTF-8 | Modified UTF-8 + prefix | Chỉ dùng khi protocol quy định. |
| Ghi length bằng `String.length()` | UTF-16 units khác byte count | `byte[].length` sau encoding. |
| Ghi UTF-8, đọc Latin-1 | Mojibake | Dùng cùng charset. |
| Test toàn ASCII | Che giấu mismatch | Test ký tự đa byte. |
| Dùng US-ASCII và tưởng mọi ký tự được giữ | Default replacement có thể mất dữ liệu | Chọn UTF-8 hoặc strict encoder. |
| Cho rằng UTF-8 không có malformed input | Unpaired surrogate trong String vẫn có thể xảy ra | Strict encoder nếu cần. |
| Cho rằng JDK 25 default UTF-8 nên không cần ghi encoding trong API | Bỏ mờ hợp đồng/compatibility | Ghi charset tường minh. |
| Cho rằng `Files.writeString` default phụ thuộc OS | Theo Javadoc nó dùng UTF-8 | Hiểu đặc tả của từng overload. |
| Chuyển binary bất kỳ thành String | Dữ liệu có thể không phải text | Giữ nguyên byte stream. |
| Không kiểm tra BOM/newline/normalization | Byte-for-byte không giống nhau | Định nghĩa protocol và test hex. |
| Đưa secret/payload vào log hex | Rò rỉ dữ liệu | Chỉ log metadata được phép. |
| Cấp phát buffer theo length của peer không validate | Có thể OOM hoặc EOF/hang | Giới hạn kích thước và đọc theo framing. |
| Quên flush/close writer | Bytes có thể chưa được đẩy tới sink | Quản lý lifecycle rõ ràng. |

## 18. Kiểm thử đáng tin cho byte output

Các nhóm test hữu ích:

**Byte-vector test:** chọn vài input Unicode và so bytes hex chuẩn. Ví dụ `"Aé€🙂"` phải mã hóa UTF-8 thành `41 C3 A9 E2 82 AC F0 9F 99 82`.

**Round-trip test:** encode → ghi → đọc → decode bằng cùng charset và so String; chỉ chứng minh đúng với dữ liệu test, chưa kiểm hết mọi input malformed.

**Wrong-charset negative test:** encode UTF-8 nhưng decode Latin-1, xác minh mismatch được phát hiện bằng so dữ liệu hoặc test byte-level. Test ASCII không đủ.

**Strict encoding test:** dùng US-ASCII với `é`, nhận `CharacterCodingException` khi `REPORT`, không im lặng thay ký tự.

**Protocol test:** kiểm tra prefix theo `payload.length`, giới hạn length, byte order, đủ bytes và xử lý EOF.

**Compatibility test:** chạy trên target JDK/OS thật, không phụ thuộc default charset của máy developer. Nếu hỗ trợ Java 14 thì không dùng `HexFormat` trong phần code phải biên dịch bằng `--release 14`.

**Security test:** cap tổng byte payload, tránh hex logging dữ liệu nhạy cảm, từ chối input sai charset theo contract.

### Test matrix gợi ý

| Input | Charset | Byte sequence hoặc kết quả |
| --- | --- | --- |
| `"ABC"` | UTF-8 | `41 42 43` |
| `"é"` | UTF-8 | `C3 A9` |
| `"é"` | ISO-8859-1 | `E9` |
| `"€"` | UTF-8 | `E2 82 AC` |
| `"🙂"` | UTF-8 | `F0 9F 99 82` |
| `"é"` | US-ASCII với `getBytes` | `3F` (replacement) |
| `"é"` | US-ASCII strict encoder | `CharacterCodingException` |
| `"Hé"` | UTF-8 frame | `00 00 00 03 48 C3 A9` |
| `"e\u0301"` và `"\u00E9"` | UTF-8 trước NFC | Khác bytes |
| Hai chuỗi ở trên sau NFC | UTF-8 | Bytes bằng nhau |

### Chạy toàn bộ các demo Java 17

~~~bash
javac --release 17 ExplicitCharsetBasicsDemo.java
java ExplicitCharsetBasicsDemo

javac --release 17 WriteBytesUtf8Demo.java
java WriteBytesUtf8Demo

javac --release 17 CharsetMismatchDemo.java
java CharsetMismatchDemo

javac --release 17 StrictCharsetEncoderDemo.java
java StrictCharsetEncoderDemo

javac --release 17 FilesUtf8RoundTripDemo.java
java FilesUtf8RoundTripDemo

javac --release 17 OutputStreamWriterUtf8Demo.java
java OutputStreamWriterUtf8Demo

javac --release 17 Utf8LengthPrefixDemo.java
java Utf8LengthPrefixDemo

javac --release 17 UnicodeNormalizationDemo.java
java UnicodeNormalizationDemo
~~~

Mỗi file độc lập có `public class` trùng tên file. Chương trình thao tác file tạm cần quyền I/O bình thường, nếu không sẽ ném lỗi thay vì báo PASS giả. Các kết quả hex/boolean được nêu là kết quả ổn định trên JDK hỗ trợ các API này.

## 19. Bài tập có đáp án

### Bài 1 — Ghi text tiếng Việt vào byte buffer

Một `String text = "Tiếng Việt";` phải được ghi UTF-8 vào `ByteArrayOutputStream out`.

**Đáp án:**

~~~java
byte[] payload = text.getBytes(StandardCharsets.UTF_8);
out.writeBytes(payload);
~~~

Chọn `Charset` tại bước encode, không chờ tới bước ghi stream.

### Bài 2 — Hai chữ ký giống tên

So sánh `ByteArrayOutputStream.writeBytes(byte[])` với `DataOutputStream.writeBytes(String)`.

**Đáp án:** loại đầu nhận dữ liệu **đã mã hóa** và ghi nguyên bytes. Loại sau lấy **8 bit thấp** từng `char`, không tương đương encode UTF-8; không thích hợp cho Unicode text tổng quát.

### Bài 3 — Tính kích thước

`"Aé"` có `String.length()==2`, nhưng khi mã hóa UTF-8 thành `41 C3 A9` thì **3 bytes**. Với framing phải ghi length=3, không phải 2.

### Bài 4 — Mismatched charset

`"Café"` encode UTF-8 rồi decode ISO-8859-1. Vì sao so với text gốc là `false`?

**Đáp án:** UTF-8 lưu `é` là `C3 A9`; Latin-1 giải mã chúng thành hai ký tự khác, gây mojibake.

### Bài 5 — Mất dữ liệu âm thầm

Khi encode US-ASCII một từ chứa `é`, `getBytes(US_ASCII)` có thể thay bằng `?`. Muốn từ chối thì dùng `CharsetEncoder` với `REPORT` cho malformed và unmappable input.

### Bài 6 — Vì sao vẫn ghi UTF-8 rõ ràng ở JDK 25?

**Đáp án:** mặc định từ JDK 18 thường là UTF-8, nhưng protocol và khả năng tương thích cần quy tắc bytes tường minh; API vẫn có thể chạy trên JDK cũ hoặc cấu hình khác.

### Bài 7 — Chuỗi giống nhau về hình thức

`"\u00E9"` và `"e\u0301"` có thể nhìn giống nhau nhưng khác code points/bytes. Nếu format yêu cầu NFC, normalize **trước** khi encode, không normalize bừa trong dữ liệu đã ký.

### Bài 8 — Payload giả mạo

Network receiver nhận length prefix `2_000_000_000` rồi lập tức tạo mảng bằng độ dài đó. Đây là rủi ro cạn RAM. Đặt max length theo protocol, kiểm tra đủ dữ liệu, EOF và timeout trước khi cấp phát/đọc.

### Bài 9 — Chọn writer hay byte array?

Khi cần ghi một file văn bản lớn theo từng chunk, nên dùng `OutputStreamWriter`/`BufferedWriter` với `UTF_8` thay vì tạo một mảng byte khổng lồ; khi cần payload binary nguyên trạng, dùng `OutputStream.write(byte[])`.

## 20. Checklist trước khi triển khai

- [ ] Đầu vào là văn bản hay binary payload đã có?
- [ ] Có hợp đồng charset rõ ràng giữa writer và reader?
- [ ] Khi cần UTF-8, đã dùng `StandardCharsets.UTF_8` ở điểm encode?
- [ ] Có tránh `String.getBytes()` không tham số cho dữ liệu chia sẻ byte-for-byte?
- [ ] Có hiểu `ByteArrayOutputStream.writeBytes(byte[])` chỉ ghi bytes, không encode?
- [ ] Có dùng `OutputStream.write(bytes)` khi biến chỉ có kiểu `OutputStream`?
- [ ] Có tránh `DataOutputStream.writeBytes(String)` nếu cần Unicode?
- [ ] Có tránh `writeUTF` trừ khi protocol dùng Java modified UTF-8?
- [ ] Prefix length được tính bằng `byte[].length` sau encoding?
- [ ] Reader có decode bằng cùng charset?
- [ ] Cần lossless thì có strict `CharsetEncoder(REPORT)`?
- [ ] Đã test non-ASCII, emoji, malformed/unmappable input?
- [ ] Đã kiểm tra BOM, newline và normalization theo contract?
- [ ] Files/streams có được flush/close đúng ownership?
- [ ] Có giới hạn byte payload và bộ nhớ cho input không tin cậy?
- [ ] Byte output được xác nhận bằng hex/byte equality?
- [ ] Có tránh log các secret, PII hoặc raw payload nhạy cảm?
- [ ] Minimum JDK có phù hợp với các API ví dụ (nhất là `HexFormat` từ Java 17)?

## 21. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 25 — `String` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `getBytes(Charset)` và `getBytes()`, replacement mặc định, decode `new String(byte[], Charset)`.
2. [Oracle Java SE 25 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn được hỗ trợ.
3. [Oracle Java SE 25 — `ByteArrayOutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ByteArrayOutputStream.html): `writeBytes(byte[])`, `Since 11`, `toString(Charset)` và `toByteArray`.
4. [Oracle Java SE 14 — `ByteArrayOutputStream`](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/io/ByteArrayOutputStream.html): phương thức `writeBytes(byte[])` đã hiện diện trong ngữ cảnh Java 14.
5. [Oracle Java SE 25 — `OutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStream.html): `write(byte[])`, `write(int)` và I/O contract.
6. [Oracle Java SE 25 — `Files`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `write`, `writeString`, `readString` và default UTF-8 của các text tiện ích.
7. [Oracle Java SE 25 — `OutputStreamWriter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/OutputStreamWriter.html): charset-based character-to-byte stream.
8. [Oracle Java SE 25 — `CharsetEncoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát malformed/unmappable qua `CodingErrorAction.REPORT`.
9. [Oracle Java SE 25 — `DataOutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/DataOutputStream.html): `writeBytes(String)` và `writeUTF` (modified UTF-8).
10. [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ JDK 18.
11. [Oracle Java SE 25 — `HexFormat`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HexFormat.html): hex formatting, `Since 17`.
12. [Oracle Java SE 25 — `Normalizer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html): NFC và các Unicode normalization forms.

**Ghi nhớ:** với văn bản, **chọn Charset trước**, mã hóa thành bytes bằng `text.getBytes(StandardCharsets.UTF_8)` hoặc một charset khác theo protocol, sau đó ghi bằng `ByteArrayOutputStream.writeBytes(bytes)`, `OutputStream.write(bytes)` hoặc `Files.write`. Luôn đo chiều dài bằng **số bytes sau encode**, decode bằng cùng charset và kiểm tra dữ liệu Unicode thật. `writeBytes` chỉ ghi bytes; nó không xác định encoding thay bạn.