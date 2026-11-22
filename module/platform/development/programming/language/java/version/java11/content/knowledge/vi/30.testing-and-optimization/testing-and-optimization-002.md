# Tệp Unicode, encoding sai và dữ liệu quá lớn (Kiểm thử và tối ưu — Java 11)

Tệp văn bản là **một chuỗi byte**, còn `String` trong Java biểu diễn **chuỗi Unicode theo UTF-16 code units**. Giữa hai thế giới này luôn có **charset/encoding** và quy tắc giải mã. Nếu dùng sai charset, một tệp “Tiếng Việt — café 😀” có thể thành chữ rác (*mojibake*); nếu tệp chứa UTF-8 hỏng, decoder có thể ném lỗi hoặc âm thầm chèn ký tự thay thế `U+FFFD` tùy API/cấu hình. Với tệp lớn, cách đọc tưởng thuận tiện như `Files.readString` hoặc `readAllLines` còn có thể làm đầy heap.

Bài học **“Tệp Unicode, encoding sai và dữ liệu quá lớn”** trong nhóm **Kiểm thử và tối ưu** tập trung vào một chiến lược bền vững trên **Java 11 và các JDK hiện đại**:

1. **Ghi rõ charset theo hợp đồng dữ liệu** (ưu tiên UTF-8 nếu bạn kiểm soát định dạng).
2. **Phát hiện byte lỗi bằng strict decoder**; không âm thầm làm mất thông tin.
3. **Phân biệt malformed bytes với dữ liệu giải mã nhầm charset nhưng vẫn hợp lệ**.
4. **Xử lý UTF-8 BOM, newline, Unicode normalization và supplementary code points** có chủ ý.
5. **Giới hạn tài nguyên và đọc theo luồng** đối với file lớn/không đáng tin: byte limit, line limit, số records, output size, timeout và chính sách hủy.
6. **Test bằng fixtures byte-level và dữ liệu ở ranh giới**, không chỉ dùng một chuỗi ASCII “hello”.
7. Chuyển mã bằng `CharsetDecoder` / `CharsetEncoder`, đóng streams đúng cách và chỉ xuất kết quả sau khi thành công.

Tất cả ví dụ hoàn chỉnh bên dưới sử dụng API có ở **Java 11**, đã biên dịch với `javac --release 11` và chạy trên một JDK hiện đại. Những API thay thế đã lỗi thời, trông chờ platform default charset hoặc lưu toàn bộ file vào RAM khi không cần đều được tránh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích sự khác nhau giữa **byte**, **charset**, **Unicode code point**, **UTF-16 code unit** và ký tự hiển thị (*grapheme cluster*).
- Hiểu vì sao `new String(bytes, UTF_8)` và `CharsetDecoder.onMalformedInput(REPORT)` có hành vi khác nhau khi gặp byte lỗi.
- Dùng `Files.readString(path, UTF_8)` cho file nhỏ đã được giới hạn; biết nó có thể ném `IOException` khi byte sequence không hợp lệ và `OutOfMemoryError` khi file quá lớn.
- Phân biệt **malformed UTF-8** với **mojibake** do dùng sai encoding, kể cả trường hợp không có `U+FFFD`.
- Xử lý UTF-8 BOM `EF BB BF` tương ứng `U+FEFF` ở đầu text; không xóa nhầm ký tự U+FEFF ở giữa nội dung.
- Biết khi nào cần `Normalizer.Form.NFC` và vì sao `String.length()` không phải số Unicode code points.
- Sử dụng `InputStreamReader` + `CharsetDecoder` và `BufferedReader` với giới hạn byte/line để không tải cả file.
- Đọc được `CRLF`, `LF`, `CR`; nêu rõ quy tắc đếm dòng và giới hạn UTF-16 units.
- Chuyển mã UTF-16LE → UTF-8 theo luồng, xử lý lỗi encode/decode và tránh xuất một file đích đã bị ghi dở.
- Thiết kế test matrix cho empty file, byte hỏng, BOM, Unicode phức tạp, dòng rất dài, file vượt giới hạn, file đang thay đổi, output thất bại và đầu vào không tin cậy.

## 2. Từ bytes tới chữ trong Java

```text
FILE ON DISK
byte[]: EF BB BF 54 69 E1 BA BF 6E 67 20 56 69 E1 BB 87 74 ...
         |
         | CharsetDecoder UTF-8
         v
Unicode text trong Java String (UTF-16 code units)
         |
         +--> xét BOM / newline / normalization / parsing
         |
         | CharsetEncoder UTF-8 hoặc charset đích
         v
OUTPUT BYTES (file / socket / response)
```

Nếu chọn sai charset, cùng một dãy bytes có thể tạo ra **một văn bản khác** hoặc lỗi giải mã. Java **không tự biết nguồn gốc tệp** chỉ từ tên file `.txt` hoặc `.csv`. Với dữ liệu production, encoding phải là một phần của **file format, protocol, schema, metadata hoặc cấu hình import**.

### Các khái niệm dễ nhầm

| Khái niệm | Ví dụ | Lưu ý |
| --- | --- | --- |
| Byte | `0xC3` | Đơn vị lưu trong file/network |
| Charset | `StandardCharsets.UTF_8` | Cách biến Unicode thành bytes và ngược lại |
| Unicode code point | `U+1F600` (😀) | Một giá trị Unicode logic |
| UTF-16 code unit | Java `char` (16 bit) | Code point ngoài BMP có thể dùng **2 code units** |
| Grapheme cluster | Một chữ có dấu tổ hợp hoặc emoji ZWJ | Có thể gồm **nhiều code points** |
| BOM | `EF BB BF` ở đầu UTF-8 | Có thể xuất hiện trong file; không phải yêu cầu bắt buộc của UTF-8 |
| Replacement character | `U+FFFD` | Thường xuất hiện khi chọn chế độ thay thế bytes lỗi; không tự chứng minh charset nguồn |
| Unicode normalization | NFC/NFD | Hai chuỗi nhìn giống nhau có thể có code points khác |
| Line terminator | `\n`, `\r\n`, `\r` | Khác nhau trên input/platform |

Một ví dụ ngắn: ký tự `é` có thể biểu diễn bằng code point `U+00E9` hoặc chuỗi `e` + combining acute accent `U+0301`. Hai cách thường trông giống nhau nhưng `String.equals` ban đầu có thể `false`. Nếu định dạng dữ liệu yêu cầu so sánh canonical tương đương, **định nghĩa chính sách chuẩn hóa** (ví dụ NFC) rồi áp dụng nhất quán; không chuẩn hóa bừa bãi secret, hash input, identifier hoặc chữ ký điện tử khi hợp đồng không cho phép.

## 3. Charset mặc định thay đổi giữa các phiên bản JDK

**Java 11 không bảo đảm platform default charset là UTF-8** cho các API sử dụng default charset. Ví dụ `new FileReader(file)` hoặc `new InputStreamReader(in)` không truyền charset có thể dùng charset mặc định của runtime/OS/locale. Một file UTF-8 từ Linux khi đọc trên Windows với charset cũ có thể bị mojibake.

**Từ JDK 18, JEP 400 chuyển default charset của các Java SE APIs liên quan sang UTF-8 theo mặc định.** Nhưng điều này **không sửa được dữ liệu đầu vào đã được encode bằng charset khác**. Hơn nữa, nếu dự án cần chạy trên Java 11, cách làm an toàn vẫn là **luôn truyền charset tường minh**.

### Cách viết nên dùng

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("example.txt");
String text = Files.readString(path, StandardCharsets.UTF_8);
```

Đây là **snippet** trong method khai báo/ xử lý `IOException`. Java 11 có `Files.readString` và mặc định overload không truyền charset của nó **đã dùng UTF-8**, khác nhóm API dựa vào `Charset.defaultCharset()`.

Khi ghi file nhỏ:

```java
Files.writeString(path, text, StandardCharsets.UTF_8);
```

`Files.writeString` cũng có từ Java 11. Hãy chọn charset theo contract; không lấy default của OS làm “phương pháp dò encoding”. Với file Unicode dùng trên nhiều hệ thống, **UTF-8 không BOM** thường là lựa chọn tương thích, nhưng phải tuân theo format cụ thể nếu bên nhận yêu cầu BOM hoặc UTF-16.

### Các API nên phân biệt

| API | Charset theo cách gọi | Phạm vi phù hợp |
| --- | --- | --- |
| `Files.readString(path)` | **UTF-8**, Java 11+ | File nhỏ đã biết giới hạn |
| `Files.readString(path, cs)` | Charset chỉ định | File nhỏ, định dạng rõ |
| `Files.readAllLines(path, cs)` | Charset chỉ định | File nhỏ/vừa, cần tất cả dòng trong List |
| `Files.lines(path, cs)` | Charset chỉ định | Đọc dòng lazy, **phải close Stream** |
| `Files.newBufferedReader(path, cs)` | Charset chỉ định | Đọc theo luồng |
| `new InputStreamReader(in, decoder)` | **Decoder tự cấu hình** | Kiểm soát malformed/unmappable behavior |
| `new String(bytes, cs)` | Charset chỉ định | Chuyển một mảng bytes đã có trong RAM; lỗi thường được **thay thế**, không tự fail-fast |
| `new FileReader(path)` trên Java 11 | Có overload dùng **default charset** | Không nên dùng khi định dạng phải ổn định đa môi trường |

**Không lấy `-Dfile.encoding` như cách sửa lỗi chính của ứng dụng.** Nó ảnh hưởng môi trường runtime và không giúp phân biệt những file có encoding khác nhau; truyền charset cụ thể ở từng I/O boundary là giải pháp dễ kiểm thử và duy trì.

## 4. Hai loại lỗi encoding cần test riêng

### 4.1. UTF-8 byte sequence thực sự bị lỗi

Ví dụ bytes:

```text
C3 28
```

`0xC3` báo một chuỗi UTF-8 hai byte, nhưng `0x28` không phải continuation byte hợp lệ. Đây là **malformed UTF-8**.

Với `CharsetDecoder`:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

Đây là snippet cần imports `CharsetDecoder`, `StandardCharsets`, `CodingErrorAction`. Chọn `REPORT` để decoder ném `MalformedInputException` / `UnmappableCharacterException` khi dùng convenience decode hoặc Reader phù hợp.

Ba chính sách xử lý lỗi:

| `CodingErrorAction` | Hành vi | Rủi ro/ứng dụng |
| --- | --- | --- |
| `REPORT` | Báo lỗi giải mã | Phù hợp import cần bảo toàn dữ liệu |
| `REPLACE` | Dùng replacement, thường `U+FFFD` | Có thể chấp nhận ở preview, nhưng mất dữ liệu gốc |
| `IGNORE` | Bỏ bytes hỏng | Thường không phù hợp dữ liệu quan trọng vì mất thông tin âm thầm |

`new String(invalidBytes, UTF_8)` là convenience conversion có thể thay malformed sequences; **không coi chuỗi trả về là bằng chứng bytes đầu vào hợp lệ**. Ngược lại, `Files.readString` trong Java 11 có contract báo `IOException` nếu gặp malformed/unmappable bytes, rất hữu ích cho các file nhỏ.

### 4.2. Charset sai nhưng bytes vẫn hợp lệ

Khi bytes UTF-8 được **giải mã nhầm bằng ISO-8859-1**, decoder này có thể ánh xạ mọi byte 0..255 sang Unicode và **không ném lỗi**. Kết quả là **mojibake**, có thể không chứa `U+FFFD`. Sau đó lưu “text rác” dưới UTF-8 vẫn tạo **file UTF-8 hợp lệ**, nên một strict UTF-8 decoder ở bước sau **không tự biết văn bản đã hỏng ý nghĩa**.

```text
UTF-8 bytes của dữ liệu đúng
           |
           v
Giải mã bằng ISO-8859-1 -> chuỗi Unicode SAI nhưng hợp lệ
           |
           v
Encode SAI chuỗi ấy thành UTF-8 -> bytes UTF-8 HỢP LỆ
           |
           v
Strict UTF-8 decode vẫn thành công,
nhưng không khôi phục ý nghĩa ban đầu.
```

**Không có phép đoán charset nào chắc chắn cho mọi file không có metadata.** Có thể dùng BOM, contract, file headers, locale, heuristics và kiểm tra nội dung để đưa ra cảnh báo, nhưng khi độ chính xác quan trọng hãy yêu cầu người cung cấp dữ liệu **khai báo encoding**. Không âm thầm thử nhiều charset rồi nhận cái đầu tiên không ném exception.

## 5. Ví dụ 1 — UTF-8 đúng, malformed bytes, mojibake, BOM và NFC

Chương trình **`UnicodeCodecDemo.java`** tạo các file thử trong thư mục tạm, kiểm tra:
- Round-trip UTF-8 có tiếng Việt, dấu dài, emoji.
- Decoder `REPORT` và `Files.readString` trên byte sequence sai.
- Giải mã nhầm `ISO_8859_1` **không** có replacement character.
- UTF-8 BOM đầu file trở thành `U+FEFF` trong chuỗi đọc.
- Unicode NFC và UTF-16 code-unit length.

Tạo file:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;

public final class UnicodeCodecDemo {
    private static String strict(byte[] bytes, Charset charset)
            throws CharacterCodingException {
        return charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("unicode-codec-");
        Path good = dir.resolve("good.txt");
        Path bad = dir.resolve("bad.txt");
        Path bom = dir.resolve("bom.txt");
        try {
            String original = "Tiếng Việt — café 😀";
            byte[] utf8 = original.getBytes(StandardCharsets.UTF_8);
            Files.write(good, utf8);
            System.out.println("UTF-8 round trip: " +
                    Files.readString(good, StandardCharsets.UTF_8)
                            .equals(original));
            System.out.println("Strict UTF-8 matches: " +
                    strict(utf8, StandardCharsets.UTF_8).equals(original));

            String wrong = strict(utf8, StandardCharsets.ISO_8859_1);
            System.out.println("Wrong Latin-1 equals original: " +
                    wrong.equals(original));
            System.out.println("Wrong Latin-1 has replacement char: " +
                    (wrong.indexOf('\uFFFD') >= 0));
            System.out.println("Mojibake can still be valid UTF-8: " +
                    strict(wrong.getBytes(StandardCharsets.UTF_8),
                            StandardCharsets.UTF_8).equals(wrong));

            byte[] invalid = {(byte) 0xC3, (byte) 0x28};
            Files.write(bad, invalid);
            boolean strictRejected = false;
            try {
                strict(invalid, StandardCharsets.UTF_8);
            } catch (CharacterCodingException e) {
                strictRejected = true;
            }
            System.out.println("Strict decoder rejects malformed: " +
                    strictRejected);
            boolean fileRejected = false;
            try {
                Files.readString(bad, StandardCharsets.UTF_8);
            } catch (IOException e) {
                fileRejected = true;
            }
            System.out.println("Files.readString rejects malformed: " +
                    fileRejected);
            System.out.println("Replacing decoder inserts U+FFFD: " +
                    (new String(invalid, StandardCharsets.UTF_8)
                            .indexOf('\uFFFD') >= 0));

            byte[] withBom = new byte[utf8.length + 3];
            withBom[0] = (byte) 0xEF;
            withBom[1] = (byte) 0xBB;
            withBom[2] = (byte) 0xBF;
            System.arraycopy(utf8, 0, withBom, 3, utf8.length);
            Files.write(bom, withBom);
            String decodedBom = Files.readString(bom, StandardCharsets.UTF_8);
            System.out.println("UTF-8 BOM appears as U+FEFF: " +
                    decodedBom.startsWith("\uFEFF"));

            String composed = "\u00e9";
            String decomposed = "e\u0301";
            System.out.println("Canonically equivalent raw strings differ: " +
                    !composed.equals(decomposed));
            System.out.println("NFC normalized strings equal: " +
                    Normalizer.normalize(composed, Normalizer.Form.NFC)
                            .equals(Normalizer.normalize(decomposed,
                                    Normalizer.Form.NFC)));
            System.out.println("UTF-16 units exceed code points: " +
                    (original.length() > original.codePointCount(
                            0, original.length())));
        } finally {
            Files.deleteIfExists(good);
            Files.deleteIfExists(bad);
            Files.deleteIfExists(bom);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy:

```sh
javac --release 11 -encoding UTF-8 UnicodeCodecDemo.java
java UnicodeCodecDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
UTF-8 round trip: true
Strict UTF-8 matches: true
Wrong Latin-1 equals original: false
Wrong Latin-1 has replacement char: false
Mojibake can still be valid UTF-8: true
Strict decoder rejects malformed: true
Files.readString rejects malformed: true
Replacing decoder inserts U+FFFD: true
UTF-8 BOM appears as U+FEFF: true
Canonically equivalent raw strings differ: true
NFC normalized strings equal: true
UTF-16 units exceed code points: true
```

### Giải thích từng nhóm kết quả

- **Round trip true:** cùng UTF-8 bytes/charset, Unicode được bảo toàn.
- **Latin-1 false nhưng không có U+FFFD:** ISO-8859-1 giải mã một dãy bytes sai ý nghĩa nhưng vẫn hợp lệ. Sự vắng mặt của `U+FFFD` **không** chứng minh dữ liệu đúng.
- **Mojibake valid UTF-8 true:** bytes xuất ra sau khi encode lại text sai có thể hoàn toàn hợp lệ; strict decoder chỉ kiểm tra **cú pháp encoding**, không kiểm tra **ngữ nghĩa tiếng Việt**.
- **Strict decoder rejects / readString rejects:** hai cơ chế có thể từ chối byte sequence `C3 28`. Phù hợp khi nhập dữ liệu cần fail-fast.
- **Replacing decoder inserts U+FFFD:** `new String(invalid, UTF_8)` không phải bộ kiểm tra hợp lệ nghiêm ngặt.
- **BOM appears as U+FEFF:** với `Files.readString(path, UTF_8)`, một BOM UTF-8 ở đầu file được đọc thành ký tự `U+FEFF`; Java không tự loại bỏ nó trong ví dụ.
- **NFC normalization:** hai chuỗi biểu diễn cùng `é` trở nên bằng nhau sau canonical normalization.
- **UTF-16 units exceed code points:** emoji ngoài BMP dùng hai `char` trong Java. `String.length()` không đếm số code points, càng không phải số chữ người dùng cảm nhận.

**Lưu ý:** test này sinh file trong một thư mục tạm và xóa ở `finally`; không tự ghi vào bất kỳ file thật nào.

## 6. UTF-8 BOM và Unicode normalization phải có hợp đồng

### UTF-8 BOM

BOM của UTF-8 là ba byte `EF BB BF`. Nó không chỉ thị little/big endian vì UTF-8 không có vấn đề byte order tương tự UTF-16. Nhiều file UTF-8 không có BOM. Nếu định dạng đầu vào cho phép BOM và muốn bỏ nó, chỉ xử lý **một `U+FEFF` đầu tiên**:

```java
if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
    text = text.substring(1);
}
```

Đây là snippet cho file nhỏ đã đọc thành `text`. Với file lớn, nên xử lý BOM tại **đầu stream** mà không tải cả file; chương trình thứ hai làm điều đó. Không gọi `trim()` hay `strip()` để “xóa BOM” vì không phải hợp đồng rõ ràng; cũng **không xóa mọi `U+FEFF` ở giữa nội dung**.

### UTF-16BE/UTF-16LE

Nếu file là UTF-16:
- `StandardCharsets.UTF_16LE`: chỉ định thứ tự bytes **little-endian**.
- `StandardCharsets.UTF_16BE`: chỉ định thứ tự bytes **big-endian**.
- `StandardCharsets.UTF_16`: có xử lý BOM đầu vào để chọn byte order, và có default behavior khi thiếu BOM.

**Tránh nhầm:** `UTF_16LE` và `UTF_16BE` không tự nhận BOM như một dấu hiệu để đổi endian. Nếu input có BOM, xác định policy dựa trên hợp đồng; ví dụ chuyển mã ở phần cuối tạo UTF-16LE **không có BOM** bằng chính Java code để tránh mơ hồ.

### Normalize có thể làm thay đổi bytes và khóa

`Normalizer.normalize(text, Normalizer.Form.NFC)` hữu ích khi cần so sánh/lookup dữ liệu Unicode tương đương về mặt canonical. Nhưng nó có thể đổi biểu diễn code points, làm thay đổi bytes khi encode. Vì vậy:
- Nếu format cần **bảo toàn nguyên văn**: không normalize.
- Nếu tìm kiếm tên, định danh hiển thị cần policy canonical: normalize **một lần tại boundary được định nghĩa**.
- Với digital signatures, hash/canonical JSON, tokens và secret: tuyệt đối theo **chuẩn canonicalization của giao thức**; không tự sửa bytes trước khi verify.

`NFC` không phải spell-checker hay bộ sửa mọi lỗi encoding. Nó không biến mojibake thành nội dung gốc.

## 7. File quá lớn: đừng biến toàn bộ dữ liệu thành một `String`

`Files.readString(path, UTF_8)` và `Files.readAllLines(path, UTF_8)` rất tiện khi file nhỏ. Nhưng chúng cần chứa **toàn bộ nội dung** trong memory:
- `readString` tạo String với nội dung file, có thể tốn RAM đáng kể.
- `readAllLines` tạo List nhiều String và overhead của List/objects.
- Khi file rất lớn, theo Java 11 Javadoc `readString` có thể ném `OutOfMemoryError`, ví dụ file trên 2 GB.
- `Files.readAllBytes` cũng materialize toàn bộ bytes; tránh nếu file lớn/không có giới hạn.

### `Files.lines` có giải quyết mọi vấn đề không?

```java
try (java.util.stream.Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
}
```

Đây là snippet cần `Path path`, imports `Files`/`StandardCharsets`, và xử lý `IOException`. `Files.lines` đọc lazy, **không tải cả file ngay**; nhưng nó phải được close trong `try-with-resources` vì giữ file handle. Các lỗi I/O xảy ra **trong lúc stream tiêu thụ** có thể xuất hiện dưới dạng `UncheckedIOException`.

**Quan trọng:** `Files.lines` và `BufferedReader.readLine` đều tạo ra **một `String` cho mỗi dòng**. Một file có một dòng dài hàng trăm MB vẫn có thể làm tăng heap bất thường. Đọc theo dòng tốt hơn đọc toàn file, nhưng **không tự bảo vệ trước dòng cực dài**. Nếu input không đáng tin, cần giới hạn **byte tổng** và **độ dài của một record/line**, hoặc phân tích bằng từng chunk.

### Trình tự kiểm soát tài nguyên

```text
Source path được cấp phép
     |
     v
Kiểm tra định dạng, size tối đa và quota
     |
     v
Open InputStream có byte budget
     |
     v
CharsetDecoder REPORT (UTF-8 theo contract)
     |
     v
Buffered Reader / scanner có line-unit limit
     |
     v
Xử lý record tại chỗ; không giữ toàn bộ records
     |
     v
Đóng stream, ghi metrics/count và kết quả
```

**Giới hạn input đọc phải áp lên dữ liệu thực**, không chỉ tin `Files.size(path)` hoặc HTTP `Content-Length`: file có thể thay đổi sau khi kiểm tra, stream có thể là pipe/network, dữ liệu gzip/zip có thể giải nén phình to. Đặt cả **giới hạn compressed và decompressed bytes** khi làm việc với compressed streams.

## 8. Ví dụ 2 — scanner có byte limit, line limit, BOM, newline và strict UTF-8

Chương trình **`BoundedUtf8ScannerDemo.java`** minh họa một cách đọc **không phải lưu toàn file hoặc toàn dòng trong memory**. Nó:
- Kiểm tra `Files.size` để từ chối sớm khi file vượt quota.
- Dùng `ByteLimitInputStream` làm tầng kiểm tra tiếp **trong lúc đọc**, giảm rủi ro file tăng sau check.
- Dùng `InputStreamReader` với `CharsetDecoder.REPORT`.
- Đọc `Reader.read()` theo UTF-16 code units qua một buffer nhỏ.
- Chỉ chấp nhận BOM `U+FEFF` ở đầu; đếm `CRLF` là một dòng, đồng thời xử lý `LF` và `CR`.
- Giới hạn số **UTF-16 code units trên dòng** mà **không dựng một String quá dài**.
- Test byte lỗi, file vượt giới hạn và dòng quá dài.

**Định nghĩa rõ:** `lineLimit` đo **UTF-16 code units**, không phải code points hoặc số chữ hiển thị. Emoji 😀 tiêu thụ hai units. Với protocol yêu cầu giới hạn theo UTF-8 bytes/code points/grapheme clusters, phải viết bộ đếm đúng contract ấy.

Tạo file:

```java
import java.io.BufferedReader;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BoundedUtf8ScannerDemo {
    private static final class ByteLimitInputStream
            extends FilterInputStream {
        private final long maximum;
        private long consumed;

        ByteLimitInputStream(InputStream source, long maximum) {
            super(source);
            this.maximum = maximum;
        }

        private void count(long amount) throws IOException {
            consumed += amount;
            if (consumed > maximum) {
                throw new IOException("Input byte limit exceeded");
            }
        }

        @Override
        public int read() throws IOException {
            int value = in.read();
            if (value >= 0) {
                count(1);
            }
            return value;
        }

        @Override
        public int read(byte[] data, int off, int len) throws IOException {
            int n = in.read(data, off, len);
            if (n > 0) {
                count(n);
            }
            return n;
        }
    }

    private static final class Summary {
        final long lines;
        final long utf16Units;
        final boolean hadBom;

        Summary(long lines, long utf16Units, boolean hadBom) {
            this.lines = lines;
            this.utf16Units = utf16Units;
            this.hadBom = hadBom;
        }
    }

    private static Summary scan(Path path, long byteLimit, int lineLimit)
            throws IOException {
        if (byteLimit <= 0 || lineLimit <= 0) {
            throw new IllegalArgumentException("Limits must be positive");
        }
        if (Files.size(path) > byteLimit) {
            throw new IOException("Input byte limit exceeded");
        }

        long lines = 0L;
        long units = 0L;
        int currentLineUnits = 0;
        boolean first = true;
        boolean hadBom = false;
        boolean afterCr = false;
        boolean endedWithSeparator = false;

        InputStream bounded = new ByteLimitInputStream(
                Files.newInputStream(path), byteLimit);
        try (Reader reader = new BufferedReader(new InputStreamReader(
                bounded,
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)),
                4096)) {
            int ch;
            while ((ch = reader.read()) != -1) {
                if (first) {
                    first = false;
                    if (ch == '\uFEFF') {
                        hadBom = true;
                        continue;
                    }
                }
                if (ch == '\r') {
                    lines++;
                    currentLineUnits = 0;
                    afterCr = true;
                    endedWithSeparator = true;
                } else if (ch == '\n') {
                    if (afterCr) {
                        afterCr = false;
                        continue;
                    }
                    lines++;
                    currentLineUnits = 0;
                    endedWithSeparator = true;
                } else {
                    afterCr = false;
                    currentLineUnits++;
                    if (currentLineUnits > lineLimit) {
                        throw new IOException("Line UTF-16 unit limit exceeded");
                    }
                    units++;
                    endedWithSeparator = false;
                }
            }
        }

        if (!endedWithSeparator && currentLineUnits > 0) {
            lines++;
        }
        return new Summary(lines, units, hadBom);
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("bounded-utf8-");
        Path valid = dir.resolve("valid.txt");
        Path huge = dir.resolve("huge.txt");
        Path longLine = dir.resolve("longline.txt");
        Path broken = dir.resolve("broken.txt");
        try {
            String text = "\uFEFFA😀\r\nB\nC\rD";
            Files.write(valid, text.getBytes(StandardCharsets.UTF_8));
            Summary s = scan(valid, 1024, 10);
            System.out.println("Logical lines: " + s.lines);
            System.out.println("UTF-16 content units: " + s.utf16Units);
            System.out.println("Leading UTF-8 BOM removed: " + s.hadBom);

            Files.write(huge, new byte[2000]);
            boolean hugeRejected = false;
            try {
                scan(huge, 64, 10);
            } catch (IOException e) {
                hugeRejected = true;
            }
            System.out.println("Oversized input rejected: " + hugeRejected);

            Files.write(longLine,
                    "ABCDE".getBytes(StandardCharsets.UTF_8));
            boolean longLineRejected = false;
            try {
                scan(longLine, 1024, 4);
            } catch (IOException e) {
                longLineRejected = true;
            }
            System.out.println("Oversized line rejected: " +
                    longLineRejected);

            Files.write(broken, new byte[]{
                    (byte) 0xC3, (byte) 0x28});
            boolean malformedRejected = false;
            try {
                scan(broken, 1024, 10);
            } catch (MalformedInputException e) {
                malformedRejected = true;
            }
            System.out.println("Malformed UTF-8 rejected: " +
                    malformedRejected);
        } finally {
            Files.deleteIfExists(valid);
            Files.deleteIfExists(huge);
            Files.deleteIfExists(longLine);
            Files.deleteIfExists(broken);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy:

```sh
javac --release 11 -encoding UTF-8 BoundedUtf8ScannerDemo.java
java BoundedUtf8ScannerDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
Logical lines: 4
UTF-16 content units: 6
Leading UTF-8 BOM removed: true
Oversized input rejected: true
Oversized line rejected: true
Malformed UTF-8 rejected: true
```

### Phân tích các chi tiết khó

**4 dòng:** nội dung là `A😀\r\nB\nC\rD` sau khi bỏ leading BOM. `\r\n` được tính **một** lần xuống dòng; `\n` và `\r` độc lập được xử lý.

**6 UTF-16 units của nội dung:** `A` là 1, 😀 là 2, `B` là 1, `C` là 1, `D` là 1. Newline/BOM không được cộng vào `utf16Units`. Nếu cần số code points hay grapheme clusters, phải định nghĩa quy tắc khác.

**Oversized input rejected:** file `2000 bytes` bị từ chối khi ngân sách chỉ `64 bytes`. `Files.size` là **fast precheck**; `ByteLimitInputStream` giữ quota trong đường đọc thực tế. `InputStreamReader` có thể đọc trước một buffer, nên “giới hạn” ở đây có nghĩa **không chấp nhận xử lý vượt quota**, không phải bảo đảm OS chưa bao giờ đọc thêm một byte sau mốc giới hạn.

**Oversized line rejected:** một dòng có 5 ASCII units không được chấp nhận khi `lineLimit = 4`, mà không cần dựng một String cực lớn. Đặc biệt hữu ích khi parse một file chứa một dòng dài bất thường.

**Malformed UTF-8 rejected:** decoder `REPORT` phát hiện byte lỗi và ném `MalformedInputException` qua Reader; không tự chèn dấu thay thế.

**Đóng tài nguyên:** `try-with-resources` đóng Reader và input stream khi thành công hoặc có lỗi. Các file test được xóa trong `finally`.

### Giới hạn của demo và nâng cấp cho production

- Chương trình này **chỉ đếm** ký tự/dòng, chưa parse CSV/JSON/records. Khi dùng thật cần giới hạn **số records**, nesting depth, số fields, field sizes và total output.
- Không dùng counter `int` cho lượng vô hạn; áp quota và kiểu số phù hợp.
- Nếu parse CSV có field chứa newline trong dấu ngoặc kép, **logical records không bằng physical lines**. Cần parser CSV đáng tin với giới hạn record/field và proper quoting.
- Nếu đọc HTTP hoặc compressed streams, cần quota cho **raw/decompressed bytes**, timeout, cancellation và backpressure. Đừng tin duy nhất file length trước khi mở.
- Nếu file bị một process khác thay đổi khi đang đọc, kết quả có thể không nhất quán; với dữ liệu cần integrity, nên dùng snapshot/immutable input hoặc atomic file handoff.
- Byte limit và line limit phải xuất phát từ contract/business SLA, không sao chép số `1024`/`10` của ví dụ vào production.
- Scanner đếm cả dòng rỗng kết thúc bằng separator theo quy ước các dòng thực sự có terminator; **một newline cuối không tự tạo thêm một record rỗng** trong phép đếm này. Thống nhất định nghĩa với consumer.

## 9. Chuyển mã file bằng streaming decoder và encoder

Một file import có thể **thực sự được encode bằng UTF-16LE**. Không nên “sửa lỗi” bằng cách decode UTF-8 rồi tìm/replace ký tự hỏng, vì lúc ấy thông tin có thể đã mất. Đường đúng:

```text
Bytes UTF-16LE (charset nguồn được khai báo)
         |
         v
CharsetDecoder UTF-16LE + REPORT
         |
         v
Reader -> char[] buffer nhỏ -> Writer
         |
         v
CharsetEncoder UTF-8 + REPORT
         |
         v
Ghi tệp tạm, đóng flush thành công
         |
         v
Move sang tên đích sau khi conversion hoàn tất
```

Dùng `CharsetEncoder.onMalformedInput(REPORT)` và `onUnmappableCharacter(REPORT)` để tránh **silent replacement** khi viết. Lưu ý **tên phương thức đúng là `onMalformedInput`**, không phải `onMalformedCharacter`.

### Ví dụ 3 — chuyển UTF-16LE thành UTF-8

Tạo file **`StreamingTranscodeDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class StreamingTranscodeDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("transcode-");
        Path source = dir.resolve("source-utf16le.txt");
        Path target = dir.resolve("result-utf8.txt");
        Path staging = null;
        try {
            String expected = "Đường phố: Hà Nội 😀\r\nDòng hai\n";
            Files.write(source, expected.getBytes(StandardCharsets.UTF_16LE));

            // Production: validate source size and contract up front.
            if (Files.size(source) > 1024 * 1024) {
                throw new IllegalArgumentException("Input too large");
            }
            staging = Files.createTempFile(dir, "pending-", ".tmp");
            try (Reader input = new BufferedReader(new InputStreamReader(
                    Files.newInputStream(source),
                    StandardCharsets.UTF_16LE.newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)));
                 Writer output = new BufferedWriter(new OutputStreamWriter(
                    Files.newOutputStream(staging),
                    StandardCharsets.UTF_8.newEncoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)))) {
                char[] buffer = new char[2048];
                int n;
                while ((n = input.read(buffer)) != -1) {
                    output.write(buffer, 0, n);
                }
            }
            Files.move(staging, target,
                    StandardCopyOption.REPLACE_EXISTING);
            staging = null;

            String actual = Files.readString(target, StandardCharsets.UTF_8);
            System.out.println("Transcode preserves Unicode text: " +
                    actual.equals(expected));
            System.out.println("CRLF preserved: " +
                    actual.contains("\r\n"));
            System.out.println("UTF-8 output starts with BOM: " +
                    actual.startsWith("\uFEFF"));
            System.out.println("Output valid UTF-8: true");
        } finally {
            if (staging != null) {
                Files.deleteIfExists(staging);
            }
            Files.deleteIfExists(source);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy:

```sh
javac --release 11 -encoding UTF-8 StreamingTranscodeDemo.java
java StreamingTranscodeDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
Transcode preserves Unicode text: true
CRLF preserved: true
UTF-8 output starts with BOM: false
Output valid UTF-8: true
```

### Vì sao ví dụ này phù hợp cho file lớn hơn?

- Chuyển đổi qua `char[2048]`, **không** cần tạo một String chứa toàn bộ file trong lúc transcoding.
- `InputStreamReader` dùng decoder đúng **UTF-16LE**, không dựa vào default charset.
- Encoder strict của UTF-8 ghi bytes và có thể báo lỗi nếu input UTF-16 units không hợp lệ.
- `CRLF` được bảo toàn vì ví dụ chỉ chuyển mã, không dùng `readLine` rồi ghép newline mới.
- UTF-8 output không chứa BOM vì encoder `UTF_8` **không tự thêm BOM** trong cách dùng này.
- Dùng file tạm `staging`, **chỉ move sang tên đích sau khi converter đóng thành công**, tránh để người dùng nhầm một file đích ghi chưa đầy là kết quả hoàn chỉnh.
- Test dùng `Files.readString` để xác minh **file nhỏ** do chính chương trình tạo, không dùng `readString` trong đường xử lý file production.

**Giới hạn cần nói rõ:** `Files.move(staging, target, REPLACE_EXISTING)` **không cam kết atomic rename**. Nếu sản phẩm yêu cầu atomic handoff, cân nhắc `StandardCopyOption.ATOMIC_MOVE` trên filesystem hỗ trợ và xử lý `AtomicMoveNotSupportedException` theo policy; cùng lúc phải chú ý fsync/durability nếu có yêu cầu chống mất điện.

Đoạn demo kiểm tra `Files.size` một lần ở input đã được nó tạo. **Với nguồn có thể thay đổi hoặc không tin cậy**, cần kết hợp giới hạn bytes trong stream như `ByteLimitInputStream` từ ví dụ 2, thêm giới hạn **output bytes** và xử lý input cancellation. Khi output vượt quota, bỏ file staging thay vì move nó sang đích. Tránh tạo temp file ở thư mục chung có quyền truy cập không phù hợp.

## 10. Tệp lớn và nội dung nén: giới hạn ở đúng tầng

### File size không phải tổng chi phí parser

Một file 10 MB có thể:
- Có một dòng duy nhất dài 10 MB.
- Có hàng triệu dòng cực ngắn gây overhead khi tạo List/String.
- Có ký tự Unicode ngoài BMP cần nhiều UTF-16 units.
- Có một trường JSON/CSV rất sâu hoặc cực dài.
- Là file nén mở rộng thành nhiều GB.
- Có hàng triệu values khiến ứng dụng tạo object graph lớn hơn file trên disk nhiều lần.

Vì vậy cần thiết kế quota ở **nhiều tầng**:

| Tầng | Giới hạn gợi ý cần có | Lý do |
| --- | --- | --- |
| Raw input bytes | Giới hạn bytes thực đọc | Tránh tệp quá lớn hoặc input thay đổi |
| Decompressed bytes | Output từ unzip/gzip có upper bound | Tránh zip/decompression bomb |
| Line / record size | UTF-8 bytes, UTF-16 units hoặc code points theo contract | Tránh một dòng quá dài |
| Record count | Số record tối đa | Tránh số object hoặc DB writes vô hạn |
| Nesting depth | JSON/XML/recursive format depth | Tránh stack overflow/CPU blowup |
| Output size | Byte budget của staging/output | Tránh full disk |
| Wall-clock duration | Timeout/cancellation | Tránh file treo, slow producer |
| Parallelism | Số file/chunk xử lý đồng thời | Tránh nhân lượng memory và file handles |

**Quan trọng:** `Files.size` là metadata tại một thời điểm (time-of-check). Một đối tượng file có thể bị sửa sau đó; giới hạn trong lúc đọc mới là tầng bảo vệ chính. Trong các hệ thống cần snapshot nhất quán, dùng file bất biến/atomic producer handoff hoặc thiết kế locking/versioning thích hợp.

### Vì sao mmap không phải phép màu?

`FileChannel.map` có thể giúp một số workload random access, nhưng:
- Map cả file rất lớn không tự giải quyết memory pressure hay parser object allocations.
- Cần xử lý file offset, mapping ranges, lifecycle và byte/char boundaries.
- Cắt buffers giữa một **UTF-8 multi-byte sequence** hoặc UTF-16 surrogate pair có thể phá decoder nếu không giữ state.
- Không nên map file không tin cậy rồi cast kích thước `long` sang `int` mà không kiểm tra.

Với text xử lý tuần tự, **streaming decoder + fixed-size buffer** là nền tảng đơn giản, an toàn và dễ kiểm thử hơn.

### Performance thực tế

- Chọn buffer hợp lý và benchmark trên workload thật; buffer quá nhỏ gây nhiều I/O, quá lớn nhân memory khi nhiều concurrent files.
- Đừng tạo `StringBuilder` không giới hạn cho cả file/dòng.
- Tránh `String.concat` trong vòng lặp đọc mỗi character nếu có thể xử lý incremental.
- Đọc theo chunks giúp xử lý multibyte encoding đúng **khi sử dụng decoder giữ state**, không tự gọi `new String(chunk, UTF_8)` độc lập trên mỗi chunk.
- Nếu cần integrity, tính checksum/hash theo **raw bytes** trong quá trình streaming; muốn kiểm tra canonical text thì phải định nghĩa normalization và encoding policy.
- Khi có lỗi encoding, ưu tiên trả diagnostics với filename, byte offset hoặc record location (không log raw secrets) thay vì tự sửa bừa.

## 11. Test matrix cho Unicode và file lớn

Một bộ kiểm thử tốt nên có cả **positive**, **negative**, **boundary** và **resource-limit** cases:

| Case | Input / điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Empty file | `byte[0]` | Đọc thành công, 0 dòng theo policy scanner |
| ASCII | `abc\n` | Không lỗi; newline đúng |
| Tiếng Việt | “Tiếng Việt” UTF-8 | Round-trip chính xác |
| Supplementary Unicode | Emoji ngoài BMP | Code point đúng, `String.length` lớn hơn code points |
| Combining marks | `e + U+0301` và `U+00E9` | Có thể khác raw equality; bằng sau NFC |
| UTF-8 BOM | `EF BB BF` + nội dung | Theo policy: nhận diện/bỏ **BOM đầu** |
| Embedded U+FEFF | U+FEFF giữa file | Không xóa bừa |
| UTF-8 malformed | `C3 28` | Decoder `REPORT` từ chối |
| Truncated UTF-8 | Mất continuation bytes cuối file | Từ chối |
| Wrong charset but valid | UTF-8 bytes decoded ISO-8859-1 | Mojibake nhưng không nhất thiết có exception |
| Legacy charset hợp lệ | File được khai báo ISO-8859-1/UTF-16LE | Decode bằng charset nguồn đúng |
| CRLF | `\r\n` | Một separator theo line policy |
| CR / LF | `\r` / `\n` | Đếm đúng và phân biệt nếu business yêu cầu |
| Trailing newline | `a\n` | Không tự tạo một record rỗng ngoài policy |
| Very long line | Dài hơn lineLimit | Reject trước khi tạo String vô hạn |
| Oversized file | `Files.size > byteLimit` hoặc file tăng | Reject |
| Byte boundary | UTF-8 code point cắt qua buffer | Stateful decoder vẫn đúng |
| Two files concurrently | Mỗi file tệp riêng, cùng quota | Không share mutable decoder giữa threads |
| Truncated UTF-16 | Thiếu nửa code unit cuối input | Strict decoder từ chối |
| Output failure | No space/permission/encoder failure | Không publish staging dở |
| Compressed bomb | Dữ liệu giải nén vượt cap | Abort, dọn staging |
| Partial/changed file | Source thay đổi khi đang đọc | Có integrity/snapshot policy rõ |

**Lưu ý về thí nghiệm “byte boundary”:** đọc chunks độc lập và dùng `new String(chunk, UTF_8)` có thể chèn replacement nếu một code point bị cắt ở giữa hai chunks. `InputStreamReader`/`CharsetDecoder` giữ state qua các lần đọc và giải quyết đúng trường hợp này. Khi viết custom ByteBuffer parser, phải tuân quy trình `decode(..., endOfInput)` và `flush` của CharsetDecoder, bảo toàn bytes chưa giải mã xong.

## 12. Cách kiểm thử để tránh “đỗ test nhưng lỗi production”

### Tạo fixtures **từ bytes**, không chỉ từ chuỗi

Nếu một test phải kiểm tra malformed UTF-8, hãy tạo **`byte[]` sai thật** như `C3 28`. Khi đã đưa nó qua một `String` dùng replacement, test có thể chỉ kiểm tra dữ liệu **sau khi bị sửa** chứ không còn kiểm tra decoder lỗi.

Khi test đúng Unicode, dùng:
- Một chuỗi có tiếng Việt, emoji, combining mark.
- Encode đúng charset bằng `getBytes(StandardCharsets.UTF_8)`.
- Đọc lại và so equality/code points.
- Kiểm tra BOM, line breaks và normalized form **theo contract**.

### Không coi exception là đúng khi bắt quá rộng

Nếu đang kiểm tra `MalformedInputException` mà dùng `catch (Exception)`, một `NoSuchFileException` hoặc lỗi quyền truy cập cũng làm test “pass” giả. Trong demo 2, case malformed bắt **đúng `MalformedInputException`**. Trong demo 1, `Files.readString` bắt `IOException` vì đó là contract API và test đã tạo file, còn phần strict decoder bắt `CharacterCodingException` rõ ràng. Trong production test suite, dùng assertions cho **loại lỗi và nguyên nhân** phù hợp.

### Tránh phụ thuộc console encoding

Console của Windows/CI có thể hiển thị Unicode khác nhau tùy terminal/font/output encoding, ngay cả khi **file bytes đúng**. Kiểm tra **byte arrays và String equality**, không chỉ so ảnh chụp terminal. Ba demo in ra **các nhãn ASCII và boolean** để kết quả xác minh ít phụ thuộc console.

### Không lấy một lần đo performance làm kết luận

Với file lớn:
- Đo throughput MB/s, CPU, allocation rate, peak used heap và GC pause.
- Thử nhiều kích thước file và distribution độ dài dòng.
- So approach `readString`/`readAllLines` **chỉ ở file có kích thước an toàn**, và streaming ở workload có giới hạn.
- Làm warmup hoặc ít nhất phân biệt startup/JIT.
- Tính impact của disk cache, SSD/HDD và filesystem.
- Có quotas rõ trước khi chạy benchmark với đầu vào không tin cậy.

**Không tạo file nhiều GB trên ổ production chỉ để “kiểm tra thử”.** Có thể tạo fixture theo chunks với giới hạn nhỏ trong môi trường test và mô phỏng boundary/large-line cases mà không cần tiêu tốn disk thật.

## 13. Những lỗi phổ biến cần tránh

**Lỗi 1 — Dùng `new FileReader(path)` trên Java 11 và tin luôn là UTF-8.** Sai: nhóm API dựa default charset phụ thuộc runtime trước JDK 18.

**Lỗi 2 — Tưởng mọi `String` có độ dài bằng số ký tự người dùng nhìn thấy.** Sai: UTF-16 code units khác code points/grapheme clusters.

**Lỗi 3 — Dùng `new String(bytes, UTF_8)` rồi kết luận bytes hợp lệ.** Sai: có thể có replacement.

**Lỗi 4 — Nếu không thấy `U+FFFD` thì không có encoding lỗi.** Sai: mojibake vẫn có thể là Unicode hợp lệ.

**Lỗi 5 — Sửa text rác bằng NFC.** NFC chỉ canonical normalize, không khôi phục charset nguồn sai.

**Lỗi 6 — Tự đoán encoding theo extension `.txt`/`.csv`.** File extension không chứa charset contract chắc chắn.

**Lỗi 7 — Luôn bỏ BOM bằng cách xóa mọi `U+FEFF`.** Chỉ nên xử lý **BOM đầu file** nếu format cho phép.

**Lỗi 8 — Đọc file rất lớn bằng `Files.readString`.** Dễ tăng RAM/OOME.

**Lỗi 9 — Coi `Files.lines` luôn dùng bộ nhớ cố định.** Một dòng cực dài có thể vẫn cần một String cực lớn.

**Lỗi 10 — Quên đóng `Stream<String>` từ `Files.lines`.** File handle có thể bị giữ.

**Lỗi 11 — Dùng `new String(chunk, UTF_8)` cho từng chunk.** Code point bị cắt tại boundary có thể hỏng.

**Lỗi 12 — Chỉ dùng `Files.size` mà không giới hạn bytes thực đọc.** File có thể thay đổi hoặc nguồn stream không có metadata.

**Lỗi 13 — Giới hạn chỉ compressed size, không giới hạn decompressed bytes.** Dễ gặp decompression bomb.

**Lỗi 14 — Dùng `BufferedReader.readLine` mà không giới hạn độ dài record.** Có thể tạo String rất lớn.

**Lỗi 15 — Bắt `Exception` rồi xem mọi lỗi là malformed Unicode.** Có thể che I/O/permission failures.

**Lỗi 16 — Dùng charset sai nhưng data vẫn decode mà không kiểm tra nội dung.** Là nguồn phổ biến của mojibake.

**Lỗi 17 — Ghi trực tiếp file đích khi transcode, để lại output dở.** Dùng staging và chỉ publish sau khi thành công.

**Lỗi 18 — Nghĩ `Files.move(..., REPLACE_EXISTING)` luôn atomic.** Không có guarantee đó.

**Lỗi 19 — Cắt chuỗi Unicode giữa surrogate pair để chia output.** Có thể tạo malformed UTF-16 khi encode.

**Lỗi 20 — Dùng `String.toLowerCase()` theo locale mặc định cho tất cả identifiers.** Với case-folding không phụ thuộc user locale cần policy thích hợp như `Locale.ROOT`, và không phải mọi Unicode equality là case-insensitive.

**Lỗi 21 — Tưởng từ JDK 18 UTF-8 default sẽ tự sửa file nguồn Windows legacy.** Sai: phải biết charset thật của file.

**Lỗi 22 — Cho rằng một test ASCII đủ bao phủ Unicode.** Cần Vietnamese, emoji, combining marks, BOM, malformed bytes và boundary splits.

## 14. Bài tập thực hành

### Bài 1 — Phân biệt malformed và mojibake

Chạy `UnicodeCodecDemo.java`. Vì sao `Wrong Latin-1 has replacement char: false` nhưng `Wrong Latin-1 equals original: false`? Strict UTF-8 decoder có tự phát hiện text đã bị mojibake từ một lần import trước không?

### Bài 2 — Tạo thêm byte lỗi

Bổ sung fixture UTF-8 thiếu continuation byte ở cuối file. Dùng `CharsetDecoder.REPORT` và kiểm tra exception cụ thể. So sánh với `new String(bytes, UTF_8)` khi dùng replacement behavior.

### Bài 3 — BOM

Thêm `U+FEFF` giữa nội dung file, sau một chữ cái. Vì sao parser chỉ nên bỏ `U+FEFF` **đầu file** khi contract cho phép, mà không xóa tất cả?

### Bài 4 — Unicode counting

Dùng `String` chứa emoji và `e\u0301`. So `length()`, `codePointCount(...)` và cách người dùng cảm nhận số chữ. Vì sao `lineLimit` của scanner tính **UTF-16 units** chứ không tự là “số chữ”?

### Bài 5 — Newline

Chạy `BoundedUtf8ScannerDemo.java`. Kiểm tra kết quả với `A\r\nB\nC\rD`, file trống, file chỉ có `\n`, và file có `A\n`. Ghi rõ quy tắc scanner đếm dòng, không dựa vào newline mặc định của OS.

### Bài 6 — Long line và byte limit

Tăng dòng `ABCDE` thành 10.000 ký tự. Giới hạn 100 UTF-16 units thì ứng dụng có tạo String 10.000 ký tự trước khi reject không? Nếu file đang lớn lên trong lúc scan, vì sao cần cả metadata check và byte counter trong stream?

### Bài 7 — Chuyển mã

Chạy `StreamingTranscodeDemo.java`. Đổi source thành UTF-16BE và decoder thành `StandardCharsets.UTF_16BE` rồi kiểm tra output. Sau đó cố ý dùng decoder sai và giải thích vì sao code có thể ném lỗi hoặc tạo nội dung sai.

### Bài 8 — Partial output

Cho chương trình transcode đọc file bị truncate hoặc thiếu quyền ghi. Thiết kế test bảo đảm **không publish file đích dở**. Nếu cần atomic handoff, xử lý `ATOMIC_MOVE` không được filesystem hỗ trợ ra sao?

### Bài 9 — Compressed data

Một file gzip 5 MB có thể giải nén thành 2 GB. Đề xuất hai quotas khác nhau cho compressed và decompressed bytes, giới hạn line/record và cách đóng streams khi reject.

### Bài 10 — Benchmark đúng

So cách đọc một file an toàn 10 MB bằng `Files.readString` và bằng streaming parser. Đo allocation, CPU, wall time, peak heap, GC và số dòng. Vì sao không thể chỉ nhìn một lần chạy rồi chọn giải pháp?

### Checklist hoàn thành

- [ ] Nắm bytes ↔ charset ↔ Unicode String và code points/UTF-16 units.
- [ ] Chỉ định charset rõ ràng, không dựa default của Java 11.
- [ ] Biết `Files.readString` của Java 11 dùng UTF-8 mặc định nhưng chỉ phù hợp file nhỏ.
- [ ] Phân biệt malformed UTF-8 với mojibake valid bytes.
- [ ] Dùng `CharsetDecoder.REPORT` và `CharsetEncoder.REPORT` khi cần fail-fast.
- [ ] Hiểu UTF-8 BOM, UTF-16LE/BE BOM behavior và NFC normalization.
- [ ] Biết `Files.lines` cần close và một dòng cực dài vẫn có thể gây memory pressure.
- [ ] Dùng byte limit, line limit, stream closure và quota cho decompression/output.
- [ ] Chạy ba Java 11 programs và đối chiếu stdout.
- [ ] Không ghi file đầu ra chưa hoàn chỉnh vào vị trí production.
- [ ] Test boundary cases, không chỉ ASCII happy path.

## 15. Tài liệu tham khảo chính thức, vẫn được áp dụng

1. [Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `newBufferedReader`, `lines`, resource handling và very-large-file caveats.
2. [Java SE 11 — CharsetDecoder](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed/unmappable bytes, `REPORT`, `REPLACE`, `IGNORE` và stateful decoding.
3. [Java SE 11 — CharsetEncoder](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CharsetEncoder.html): strict encoding, UTF-16 surrogate errors và onMalformedInput.
4. [Java SE 11 — CodingErrorAction](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CodingErrorAction.html): ba chính sách xử lý lỗi.
5. [Java SE 11 — StandardCharsets](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, UTF-16, UTF-16LE/BE, ISO-8859-1 và ASCII chuẩn.
6. [Java SE 11 — InputStreamReader](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStreamReader.html): byte-to-character bridge, charset/decoder và read-ahead.
7. [Java SE 11 — Normalizer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/text/Normalizer.html): NFC/NFD và các normalization forms.
8. [OpenJDK — JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi từ JDK 18, không được áp ngược cho mọi default-dependent API trên Java 11.
9. [Unicode Consortium — UTF & BOM FAQ](https://www.unicode.org/faq/utf_bom.html): BOM bytes, quy tắc UTF-8/UTF-16 và U+FEFF.
10. [Java SE 11 — Files.move / StandardCopyOption](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/StandardCopyOption.html): `REPLACE_EXISTING` và `ATOMIC_MOVE`.
11. [Java SE 25 — Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): đối chiếu các API đọc/ghi được duy trì trên JDK mới.
12. [Java SE 11 — String](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html): UTF-16 units, `length` và `codePointCount`.

**Kết luận:** xử lý file Unicode đúng đòi hỏi **charset theo hợp đồng, decoder nghiêm ngặt, test từ bytes gốc và xử lý BOM/normalization có chủ đích**. Khi file quá lớn, phải **streaming và giới hạn tài nguyên ở đúng tầng** — không dùng `readString`/`readAllLines` trên input không giới hạn, không nghĩ `readLine` tự chống dòng cực dài, không tin mỗi `Files.size`. Với chuyển mã, **decode strict → encode strict → xuất qua staging**, kiểm tra cả dữ liệu lẫn đường lỗi, để giữ tính đúng đắn và khả năng vận hành trên Java 11 cũng như JDK hiện đại.