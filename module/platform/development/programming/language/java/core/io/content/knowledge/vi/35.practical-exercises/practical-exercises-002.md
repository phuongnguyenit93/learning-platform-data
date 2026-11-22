# Chuyển văn bản giữa hai charset có kiểm tra lỗi (Java 17+)

## 1. Bài toán và kết quả mong muốn

Một tệp văn bản chứa **bytes**, không chứa các Java `char` theo nghĩa trực tiếp. Khi di chuyển dữ liệu từ một hệ thống cũ sử dụng ISO-8859-1, Windows-1252, Shift_JIS hoặc UTF-16 sang hệ thống mới dùng UTF-8, ứng dụng cần **giải mã** byte nguồn thành các ký tự Unicode rồi **mã hóa** các ký tự đó thành bytes của charset đích.

Bài toán thực hành:

> Chuyển nội dung văn bản từ charset nguồn xác định sang charset đích xác định, nhưng **không âm thầm thay ký tự lỗi**. Nếu bytes nguồn sai cấu trúc, hoặc có ký tự không thể biểu diễn trong charset đích, phải báo lỗi và **không công bố tệp kết quả dở dang**.

Ví dụ có đầu vào ISO-8859-1:

```text
Bytes nguồn (hex):       43 61 66 E9
Charset nguồn:           ISO-8859-1
Ký tự Unicode sau decode: C a f é
Charset đích:            UTF-8
Bytes đích (hex):        43 61 66 C3 A9
```

Đây là quá trình **transcoding** chứ không phải đổi đuôi file, copy bytes nguyên trạng hay gọi `String.replace`.

Luồng đúng:

```text
                  DECODE                         ENCODE
byte[] nguồn ───────────────────▶ ký tự Unicode ─────────────────▶ byte[] đích
  ISO-8859-1        CharsetDecoder      chars       CharsetEncoder       UTF-8
                      REPORT                           REPORT
                       │                                │
                       └── lỗi malformed                └── lỗi unmappable
                           hoặc unmappable                  hoặc malformed
```

Hai vị trí kiểm tra lỗi là **độc lập**. Byte đầu vào có thể giải mã hợp lệ nhưng ký tự thu được vẫn không thể mã hóa sang charset đích; ngược lại, charset đích có thể hỗ trợ mọi ký tự hợp lệ trong khi input bytes đã hỏng trước bước mã hóa.

## 2. Các khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| `Charset` | Quy tắc ánh xạ giữa bytes và ký tự Unicode | `StandardCharsets.UTF_8` |
| `CharsetDecoder` | Chuyển bytes sang chars với chính sách xử lý lỗi rõ ràng | UTF-8 → Unicode |
| `CharsetEncoder` | Chuyển chars sang bytes với chính sách xử lý lỗi rõ ràng | Unicode → ISO-8859-1 |
| `CharacterCodingException` | Ngoại lệ gốc cho các lỗi mã hóa/giải mã | Cha của hai ngoại lệ dưới |
| `MalformedInputException` | Input không hợp lệ về mặt cấu trúc mã hóa | UTF-8 byte `C3 28` |
| `UnmappableCharacterException` | Một ký tự/đơn vị đầu vào không có mapping hợp lệ trong charset đích hoặc charset nguồn | Unicode `é` sang US-ASCII |
| `CodingErrorAction.REPORT` | Báo lỗi thay vì âm thầm thay/bỏ | Phù hợp dữ liệu cần chính xác |
| `CodingErrorAction.REPLACE` | Thay phần lỗi bằng chuỗi/byte thay thế của codec | Có thể làm mất thông tin |
| `CodingErrorAction.IGNORE` | Bỏ qua phần lỗi | Dễ mất dữ liệu âm thầm |

**Phân biệt lỗi của decoder và encoder:**

- **Malformed ở decoder**: byte source không tạo thành chuỗi mã hợp lệ. Ví dụ hai byte `C3 28` không phải một code point UTF-8 hợp lệ.
- **Unmappable ở decoder**: một dãy byte hợp lệ theo định dạng nguồn nhưng không có ký tự Unicode tương ứng theo mapping của charset đó; sự khác biệt tùy charset.
- **Unmappable ở encoder**: Unicode có ký tự mà bảng mã đích không thể lưu; chẳng hạn `é` hoặc `☃` vào US-ASCII.
- **Malformed ở encoder**: char sequence không hợp lệ, ví dụ một UTF-16 surrogate lẻ trong `CharBuffer`, ngay cả khi charset đích là UTF-8.

Không dùng ngoại lệ duy nhất như `IOException` rồi diễn giải mọi thứ thành “tệp hỏng”. Hãy giữ thông tin: charset nào, bước nào, mã lỗi nào, và vị trí dữ liệu nếu đã được theo dõi.

## 3. Vì sao phải khai báo charset rõ ràng?

Một file bytes không tự mang metadata chuẩn chung bảo đảm decoder nào đúng. Những câu lệnh dùng **charset mặc định** có thể tạo kết quả khác nhau theo JDK, cấu hình runtime hoặc nền tảng:

```java
// Tránh phụ thuộc default charset trong giao thức và dữ liệu lưu trữ.
new InputStreamReader(inputStream);
new OutputStreamWriter(outputStream);
```

Đây là đoạn minh họa API với stream đã được khai báo. Kể từ Java 18, default charset của JDK hướng tới UTF-8 theo JEP 400, nhưng vẫn có ngoại lệ/cấu hình; ứng dụng đọc dữ liệu lịch sử hoặc trao đổi với hệ thống khác không được trông đợi default sẽ tự nhận ra ISO-8859-1, Windows-1252 hay Shift_JIS.

**Luôn xác định nguồn gốc charset** từ contract, metadata đáng tin, user lựa chọn được kiểm chứng hoặc quy tắc giao thức.

```java
Charset source = StandardCharsets.ISO_8859_1;
Charset target = StandardCharsets.UTF_8;
```

Hai hằng số này nằm trong `java.nio.charset.StandardCharsets` và luôn được hỗ trợ trong Java SE. Nếu thực tế file nguồn dùng Windows-1252, bạn có thể chọn `Charset.forName("windows-1252")` nếu JDK/provider hỗ trợ; **không tự coi Windows-1252 và ISO-8859-1 hoàn toàn giống nhau**, đặc biệt tại các byte 0x80–0x9F.

### 3.1. Có thể nhận diện charset tự động tuyệt đối không?

Không có thuật toán tổng quát nào bảo đảm suy ra đúng charset cho **mọi** dãy bytes. Một chuỗi bytes có thể hợp lệ trong nhiều charset khác nhau nhưng sinh văn bản khác nhau.

Ví dụ byte UTF-8 của `é` là `C3 A9`. Nếu giải mã nhầm thành ISO-8859-1, chương trình nhận `Ã©`; cả hai byte đều hợp lệ trong ISO-8859-1 nên **decoder REPORT không báo lỗi**.

```text
43 61 66 C3 A9
   UTF-8      → Café
   ISO-8859-1 → CafÃ©
```

Vì vậy “không ném exception” chỉ chứng minh **input hợp lệ theo charset đã chọn**, **không chứng minh charset đó là charset gốc đúng**. Với nguồn không rõ charset, cần metadata, quy trình thẩm định hoặc xác nhận con người; heuristic chỉ cung cấp độ tin cậy có giới hạn.

## 4. Vì sao các API tiện lợi có thể che giấu dữ liệu lỗi?

Các lệnh ngắn gọn như:

```java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] converted = text.getBytes(StandardCharsets.US_ASCII);
```

là cú pháp Java hợp lệ trong method có `bytes` là `byte[]` và import `StandardCharsets`. Nhưng các convenience API kiểu này **mặc định có chính sách thay thế** đối với phần không thể giải mã/mã hóa; chúng không cung cấp kênh báo lỗi chi tiết như `CharsetDecoder` và `CharsetEncoder` với `REPORT`.

Với file cần chuyển mã **không mất thông tin**, không nên chỉ dựa vào chúng. Tương tự:

```java
Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(target, text, StandardCharsets.US_ASCII);
```

Các phương thức cấp cao có hợp đồng xử lý lỗi riêng (chẳng hạn `readString` có thể báo `MalformedInputException` theo API); **không suy luận mọi tiện ích đều REPLACE**. Điểm quan trọng là phải đọc contract của **chính overload** và chọn cơ chế chủ động `REPORT` cả **đầu vào lẫn đầu ra** khi yêu cầu kiểm chứng nghiêm ngặt.

### 4.1. Ba chính sách và tác động dữ liệu

Giả sử input UTF-8 chứa `C3 28`:

- `REPORT`: decoder báo `MalformedInputException`; không tạo kết quả “sửa hộ”.
- `REPLACE`: codec dùng ký tự thay thế, thường là `U+FFFD` (ký hiệu `�`), rồi tiếp tục xử lý những byte hợp lệ khác. Nội dung đã **thay đổi**.
- `IGNORE`: codec bỏ qua phần lỗi; nội dung có thể **mất byte/ký tự**.

Chính sách nào được phép là quyết định nghiệp vụ. Với backup, dữ liệu tài chính, định danh, file nguồn dùng cho build, hoặc migration cần kiểm chứng, `REPORT` thường là mặc định hợp lý; nếu phải REPLACE/IGNORE theo yêu cầu, cần ghi lại việc mất thông tin.

## 5. `CharsetDecoder`: từ bytes sang Unicode

Tạo decoder mới với chính sách lỗi tường minh:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
```

Đây là đoạn code hợp lệ trong method, cần import `CharsetDecoder`, `CodingErrorAction` và `StandardCharsets`.

Giải mã một `ByteBuffer` đầy đủ:

```java
byte[] source = {
        0x43, 0x61, 0x66, (byte) 0xC3, (byte) 0xA9
};

CharBuffer chars = decoder.decode(ByteBuffer.wrap(source));
System.out.println(chars);
```

Đây là snippet trong method có `decoder` từ bước trước và imports `ByteBuffer`/`CharBuffer`. Kết quả hiển thị ký tự `Café` khi đầu vào đúng UTF-8. Phương thức `decode(ByteBuffer)` dạng convenience của **decoder được cấu hình** sẽ báo lỗi theo `CodingErrorAction.REPORT`.

**Ví dụ input sai:**

```java
byte[] invalid = { (byte) 0xC3, (byte) 0x28 };

try {
    decoder.reset(); // Reset nếu tái dùng sau lượt decode trước.
    decoder.decode(ByteBuffer.wrap(invalid));
} catch (MalformedInputException ex) {
    System.out.println("UTF-8 malformed");
}
```

Đây là snippet trong method có decoder phù hợp, cần import `MalformedInputException`. Với chương trình production, **tạo decoder mới cho mỗi operation** thường đơn giản hơn việc chia sẻ/tái dùng decoder có state; không dùng cùng `CharsetDecoder` đồng thời trên nhiều thread.

### 5.1. Decoder có trạng thái

Một số charset có chuyển trạng thái (stateful), và ngay cả UTF-8 có thể có chuỗi nhiều byte bị chia qua ranh giới I/O. Vì vậy một decoder xử lý stream phải giữ được trạng thái giữa các chunk:

```text
Chunk 1: ... E2 82
Chunk 2: AC ...
                └─ ba byte E2 82 AC tạo ký tự €
```

Nếu giải mã hai chunk UTF-8 **độc lập** với hai decoder mới, chunk 1 có thể bị báo malformed/truncated còn chunk 2 cũng hỏng. Không được chia file tùy tiện thành byte chunks rồi gọi `new String(chunk, UTF_8)` theo từng chunk khi cần giữ nguyên văn bản.

`InputStreamReader` được xây trên `CharsetDecoder` xử lý việc tiếp tục đọc và lưu trạng thái decoder qua các byte chunks. Đây thường là lựa chọn đơn giản hơn việc tự quản lý `CoderResult`/`ByteBuffer.compact` cho bài thực hành streaming.

## 6. `CharsetEncoder`: từ Unicode sang charset đích

Đầu ra cũng có lỗi riêng. Ví dụ muốn mã hóa một `String` thành ISO-8859-1:

```java
CharsetEncoder encoder = StandardCharsets.ISO_8859_1.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharBuffer chars = CharBuffer.wrap("Caf\u00E9");
ByteBuffer bytes = encoder.encode(chars);
```

Đây là snippet trong method có import `CharsetEncoder`, `CharBuffer`, `ByteBuffer`; Java xử lý escape `\u00E9` như ký tự é.

Trường hợp đích không biểu diễn được ký tự:

```java
CharsetEncoder ascii = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try {
    ascii.encode(CharBuffer.wrap("Caf\u00E9"));
} catch (UnmappableCharacterException ex) {
    System.out.println("ASCII unmappable");
}
```

Với Java 17+, kết quả lỗi đúng là `UnmappableCharacterException`, vì US-ASCII không mã hóa được `é`.

**Quy tắc:** nguồn đọc được hợp lệ **không** có nghĩa mọi ký tự có thể đưa tới đích. UTF-8 có thể mã hóa mọi Unicode scalar value hợp lệ; các charset khác thường có tập ký tự hẹp hơn. Chuyển từ UTF-8 sang US-ASCII hoặc ISO-8859-1 có khả năng mất thông tin dù input hoàn toàn tốt.

### 6.1. `canEncode` có thay thế error handling không?

`encoder.canEncode(...)` có thể trả lời liệu một ký tự hoặc chuỗi có thể được mã hóa với encoder tương ứng. Nhưng nếu convert file rất lớn, **không cần đọc toàn bộ file thành String** chỉ để kiểm tra canEncode trước. Một `CharsetEncoder` cấu hình `REPORT` ở luồng ghi sẽ phát hiện lỗi khi encoder thực sự xử lý input.

Ngoài ra, giữa bước precheck và bước encode, nếu dữ liệu nguồn bị thay đổi, kết quả precheck không còn đáng tin. Cách đơn giản, chắc chắn là xử lý đúng **một chuỗi chuyển mã**, bắt và báo lỗi ở nơi xảy ra, chỉ công bố bản đích sau khi toàn bộ decode/encode thành công.

## 7. Từ demo nhỏ tới chuyển mã file lớn

Có hai chiến lược chính:

| Chiến lược | Ưu điểm | Giới hạn |
|---|---|---|
| `Files.readAllBytes` → `decoder.decode` → `encoder.encode` → `Files.write` | Rõ từng bước, dễ học về lỗi, phù hợp payload nhỏ đã giới hạn | Cần giữ toàn bộ bytes/chars; không hợp file lớn |
| `InputStreamReader` dùng decoder `REPORT` + `OutputStreamWriter` dùng encoder `REPORT` | Xử lý streaming bằng mảng char cố định, không cần giữ toàn file | Phải quản lý lifecycle/error/staging; báo offset lỗi chi tiết cần bộ đếm/decoder riêng |

**Ví dụ bản đơn giản cho dữ liệu nhỏ:**

```java
byte[] sourceBytes = Files.readAllBytes(sourcePath);

CharsetDecoder decoder = sourceCharset.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = targetCharset.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharBuffer characters = decoder.decode(
        ByteBuffer.wrap(sourceBytes));

ByteBuffer encoded = encoder.encode(characters);

byte[] result = new byte[encoded.remaining()];
encoded.get(result);

Files.write(targetPath, result);
```

Đoạn này **chỉ là minh họa trong method** với imports tương ứng, Paths/Charsets đã khai báo và checked exceptions được xử lý. Nó không an toàn cho file tùy ý lớn; cũng **không bảo đảm** target không bị ghi dở nếu lỗi xuất hiện khi `Files.write`. Muốn giữ file đích cũ và không công bố output lỗi, dùng staging như ví dụ đầy đủ bên dưới.

## 8. Ví dụ thực hành hoàn chỉnh: stream + strict decode/encode + staging

Ứng dụng dưới đây chuyển từ **ISO-8859-1 sang UTF-8**, sau đó kiểm tra riêng hai nhánh lỗi:

1. File nguồn UTF-8 malformed: chuyển sang UTF-8 bị **từ chối**.
2. File nguồn UTF-8 hợp lệ nhưng chứa ký tự không có trong US-ASCII: mã hóa ra US-ASCII bị **từ chối**.

Mỗi lần chuyển mã:

- Tạo `CharsetDecoder` và `CharsetEncoder` mới với cả hai lỗi `REPORT`.
- Dùng `InputStreamReader`/`OutputStreamWriter` cho **streaming**.
- Đọc/ghi theo khối `char[]`, không nạp toàn file.
- Ghi vào **tệp staging trong cùng thư mục đích**.
- Chỉ `Files.move(staging, target)` **sau khi** đóng thành công các stream và toàn bộ decoder/encoder không báo lỗi.
- Xóa staging khi conversion thất bại; đích chưa được tạo sẽ không xuất hiện.

**Tên tệp:** `StrictTranscodeDemo.java`

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

public class StrictTranscodeDemo {

    public static void convert(
            Path source,
            Path target,
            Charset inputCharset,
            Charset outputCharset) throws IOException {

        CharsetDecoder decoder = inputCharset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        CharsetEncoder encoder = outputCharset.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        // Đặt staging tại parent đích để tránh tạo output dở dang
        // dưới tên target khi decode/encode thất bại.
        Path parent = target.toAbsolutePath().getParent();
        Path staging = Files.createTempFile(
                parent, ".transcoding-", ".tmp");

        boolean published = false;

        try {
            try (Reader reader = new BufferedReader(
                        new InputStreamReader(
                                Files.newInputStream(source), decoder));
                 Writer writer = new BufferedWriter(
                        new OutputStreamWriter(
                                Files.newOutputStream(
                                        staging,
                                        StandardOpenOption.WRITE,
                                        StandardOpenOption.TRUNCATE_EXISTING),
                                encoder))) {

                char[] chunk = new char[4096];
                int n;

                while ((n = reader.read(chunk)) != -1) {
                    writer.write(chunk, 0, n);
                }
            }

            // Chỉ publish sau khi cả reader/writer đã close thành công.
            // Ở demo này target chưa tồn tại; move không có option
            // không phải bảo đảm atomic replacement/durability.
            Files.move(staging, target);
            published = true;

        } finally {
            if (!published) {
                Files.deleteIfExists(staging);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("transcode-");

        try {
            Path latin1 = directory.resolve("latin1.txt");
            Path utf8 = directory.resolve("utf8.txt");

            Files.write(
                    latin1,
                    "Caf\u00E9".getBytes(StandardCharsets.ISO_8859_1));

            convert(
                    latin1, utf8,
                    StandardCharsets.ISO_8859_1,
                    StandardCharsets.UTF_8);

            System.out.println(
                    "converted exact: "
                    + Files.readString(
                            utf8, StandardCharsets.UTF_8)
                            .equals("Caf\u00E9"));

            System.out.println(
                    "input bytes: " + Files.size(latin1));
            System.out.println(
                    "output bytes: " + Files.size(utf8));

            Path invalid = directory.resolve("invalid.bin");
            Path invalidTarget = directory.resolve("invalid-out.txt");

            // C3 28: dãy UTF-8 malformed.
            Files.write(invalid, new byte[]{
                    (byte) 0xC3, (byte) 0x28
            });

            try {
                convert(
                        invalid, invalidTarget,
                        StandardCharsets.UTF_8,
                        StandardCharsets.UTF_8);
            } catch (MalformedInputException ex) {
                System.out.println(
                        "malformed input: "
                        + ex.getClass().getSimpleName());
            }

            System.out.println(
                    "invalid target exists: "
                    + Files.exists(invalidTarget));

            Path unicode = directory.resolve("unicode.txt");
            Path asciiTarget = directory.resolve("ascii.txt");

            Files.writeString(
                    unicode, "Caf\u00E9 \u2603",
                    StandardCharsets.UTF_8);

            try {
                convert(
                        unicode, asciiTarget,
                        StandardCharsets.UTF_8,
                        StandardCharsets.US_ASCII);
            } catch (UnmappableCharacterException ex) {
                System.out.println(
                        "unmappable output: "
                        + ex.getClass().getSimpleName());
            }

            System.out.println(
                    "unmappable target exists: "
                    + Files.exists(asciiTarget));

        } finally {
            try (Stream<Path> files = Files.list(directory)) {
                for (Path file : files.toList()) {
                    Files.deleteIfExists(file);
                }
            }
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac StrictTranscodeDemo.java
java StrictTranscodeDemo
```

**Stdout kỳ vọng (đã kiểm chứng bằng JDK):**

```text
converted exact: true
input bytes: 4
output bytes: 5
malformed input: MalformedInputException
invalid target exists: false
unmappable output: UnmappableCharacterException
unmappable target exists: false
```

### 8.1. Giải thích từng bước

1. `latin1.txt` được ghi bằng `ISO_8859_1`, chứa byte `E9` cho ký tự `é`; kích thước 4 byte.
2. `InputStreamReader` nhận `CharsetDecoder` đã bật `REPORT` và đọc thành ký tự Unicode. `OutputStreamWriter` nhận `CharsetEncoder` cũng bật `REPORT`, ghi theo UTF-8: `é` thành hai byte `C3 A9`, tổng 5 byte.
3. Code dùng buffer `char[4096]` nhưng vẫn xử lý được ký tự nhiều byte vì **Reader/Writer giữ trạng thái mã hóa qua các lần read/write**. Không tạo decoder mới cho từng chunk.
4. Nếu bytes đầu vào hỏng, `InputStreamReader` ném `MalformedInputException` trong lúc đọc. Khối try-with-resources đóng tài nguyên; vì move chưa chạy nên target không xuất hiện.
5. Với input Unicode có `é`/`☃` nhưng target `US_ASCII`, encoder `REPORT` ném `UnmappableCharacterException` trong lúc ghi (hoặc khi flush/close).
6. Biến `published` giúp `finally` xóa staging trong mọi nhánh lỗi trước publish. Nếu đã move thành công, staging không còn tại đường dẫn cũ.
7. `Files.move(staging,target)` không có `REPLACE_EXISTING`; demo dùng target chưa tồn tại. **Không** gọi hành vi đó là “atomic commit” hay “durable commit” trên mọi OS.
8. Bản demo dọn file trong thư mục riêng do chính nó tạo, không sửa tệp người dùng. Nếu filesystem bất thường gây lỗi cleanup, exception được báo; demo không giấu thất bại.

### 8.2. Vì sao có escape `\u00E9` và `\u2603` trong mã nguồn?

Đó là cú pháp Unicode escape của Java, lần lượt cho `é` và `☃`, giúp file nguồn của ví dụ có thể lưu dưới ASCII khi môi trường terminal/editor có charset khác. Chương trình không “ép ký tự thành ASCII”; các escape được Java compiler xử lý thành đúng ký tự Unicode trước khi chương trình chạy.

### 8.3. Điều ví dụ **không** bảo đảm

- Không có xác thực nguồn tệp hay giới hạn tổng số byte/chars của input.
- Không ghi checksum hoặc manifest nội dung.
- Không bảo đảm source không bị tác nhân khác thay đổi trong lúc đọc.
- Không tự có cơ chế giao dịch/độ bền sau mất điện.
- Không thay thế file target đã tồn tại một cách nguyên tử.
- Không báo chính xác **byte offset** của ký tự lỗi trong file; exception cho biết loại lỗi, muốn offset cần bộ đếm bytes hoặc xử lý trực tiếp `CoderResult`.
- Không kiểm soát symlink/path races nếu path do người dùng không tin cậy cung cấp.

Đây là một ví dụ **chuyển mã nghiêm ngặt và ngăn công bố output dở dang do lỗi mã hóa**, không phải một công cụ ETL production đầy đủ.

## 9. Chuyển file thật từ command line

Khi áp dụng vào bài toán thực tế, nên thiết kế chương trình nhận:

```text
transcode <sourcePath> <targetPath> <sourceCharset> <targetCharset>
```

Ở tầng CLI cần:

- Parse và xác nhận đúng số tham số.
- Dùng `Charset.forName(name)` cùng xử lý `IllegalCharsetNameException`/`UnsupportedCharsetException` hoặc `IllegalArgumentException` phù hợp.
- Không tự chọn charset nguồn nếu nghiệp vụ đã định rõ.
- Kiểm tra source là tệp thường, đường dẫn target thuộc khu vực được phép, không tự cho phép ghi đè nhầm.
- Gọi logic `convert` trong ví dụ sau khi đã validate.
- In thông báo lỗi rõ: input malformed, output unmappable, permissions, hết dung lượng, target tồn tại hoặc đường dẫn không hợp lệ.
- Trả exit code thất bại và không báo kết quả đã công bố nếu `Files.move` chưa xong.

### 9.1. Helper xử lý charset names

```java
static Charset parseCharset(String name) {
    try {
        return Charset.forName(name);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "Unsupported or illegal charset: " + name, ex);
    }
}
```

Đây là một helper trong class có `import java.nio.charset.Charset`. Trong chương trình CLI thực, thông báo lỗi không nên ghép những input tùy ý vào log nhạy cảm mà không xử lý; helper dùng để minh họa cách fail-fast với charset không hỗ trợ.

Một số tên hợp lệ ví dụ `UTF-8`, `ISO-8859-1`, `US-ASCII`, `UTF-16LE`; với Windows-1252 có thể dùng `Charset.forName("windows-1252")` khi provider của runtime hỗ trợ. Một tên charset **hợp lệ** không chứng minh tệp đó thật sự dùng charset ấy.

## 10. UTF-8 và UTF-16: BOM, byte order và lựa chọn charset

### 10.1. Byte Order Mark (BOM) là gì?

Một số tệp văn bản mở đầu bằng dấu BOM:

| Encoding thường gặp | BOM bytes (hex) |
|---|---|
| UTF-8 | `EF BB BF` |
| UTF-16BE | `FE FF` |
| UTF-16LE | `FF FE` |
| UTF-32BE | `00 00 FE FF` |
| UTF-32LE | `FF FE 00 00` |

BOM có thể cung cấp dấu hiệu về mã hóa hoặc thứ tự byte, nhưng **không phải mọi file đều có BOM**, và không được dựa vào BOM để kết luận encoding chắc chắn nếu file từ nguồn không đáng tin.

### 10.2. `UTF_16` khác `UTF_16LE` và `UTF_16BE`

- `StandardCharsets.UTF_16` có semantics xử lý BOM/byte-order theo contract Java. Khi encode, nó có thể phát sinh BOM theo quy tắc charset; khi decode, nó có thể dùng BOM để xác định byte order, còn mặc định nếu thiếu BOM theo quy tắc riêng.
- `StandardCharsets.UTF_16LE` và `UTF_16BE` cố định byte order. Không tự biến file thành UTF-8 hoặc tự suy đoán từ BOM tùy ý.
- Nếu protocol yêu cầu UTF-16LE **không BOM**, chọn đúng charset và định nghĩa BOM policy.

Không trộn bytes ở UTF-16LE với decoder UTF-16BE chỉ vì cùng có “UTF-16” trong tên. Kết quả có thể thành ký tự sai hoặc báo malformed.

### 10.3. UTF-8 BOM có thể trở thành U+FEFF

Nếu stream UTF-8 có đầu `EF BB BF`, nhiều decoder UTF-8 sẽ thể hiện nó thành ký tự Unicode `U+FEFF` trong dữ liệu. Trong Java, `StandardCharsets.UTF_8` **không được coi là BOM-stripping API tổng quát**.

Nếu muốn loại UTF-8 BOM của file đầu vào, hãy định nghĩa điều đó trong format contract và chỉ xử lý ở **đầu stream**, trước khi dùng text. Không xóa mọi ký tự `\uFEFF` ở bất kỳ vị trí nào vì có thể làm thay đổi dữ liệu hợp lệ theo định dạng của ứng dụng.

### 10.4. Newline cũng cần chính sách riêng

Trong quá trình chuyển charset, chương trình có thể cần giữ nguyên `\r\n`, `\n` hay `\r`. Ví dụ `StrictTranscodeDemo` dùng Reader/Writer với `read(char[])` và `write(char[],0,n)`, **không dùng `readLine()`**, nên nó không tự chuyển mọi xuống dòng thành separator của OS.

Nếu dùng `BufferedReader.readLine()` rồi `BufferedWriter.newLine()`, bạn đang thực hiện thêm **chuyển đổi newline**, có thể làm file output khác về mặt ký tự ngay cả khi encoding hợp lệ.

## 11. Một Unicode character có thể dài bao nhiêu?

Cần phân biệt:

- **Byte**: đơn vị lưu của charset.
- **UTF-16 code unit (`char`)**: Java `char` là 16 bit, không phải luôn một ký tự Unicode hoàn chỉnh.
- **Unicode code point**: giá trị Unicode, một code point ngoài BMP có thể dùng **hai char** (surrogate pair).
- **Grapheme cluster**: ký tự nhìn thấy trên màn hình có thể bao gồm nhiều code points, chẳng hạn chữ + dấu kết hợp.

Ví dụ:

```java
String snowman = "\u2603";
String emoji = "\uD83D\uDE00";

System.out.println(snowman.length()); // 1 UTF-16 code unit.
System.out.println(emoji.length());   // 2 UTF-16 code units.
```

Đoạn này là snippet có thể chạy trong method; ký tự `☃` ở BMP dùng một char, emoji 😀 ngoài BMP dùng hai char.

### 11.1. Vì sao ranh giới chunk có thể cắt giữa surrogate pair?

Một lần `Reader.read(char[])` có thể kết thúc ngay sau high surrogate của một code point ngoài BMP. `Writer`/`CharsetEncoder` giữ state phù hợp để xử lý phần char còn lại khi có lần `write` kế tiếp. Tuy nhiên, **nếu bạn tự gọi `CharsetEncoder.encode(CharBuffer)` độc lập trên từng chunk**, chunk kết thúc bằng high surrogate lẻ có thể bị báo malformed dù ký tự hoàn chỉnh trải sang chunk tiếp theo.

Do đó:

- Dùng **một** pipeline Reader/Writer tồn tại xuyên các chunk, hoặc
- Tự triển khai state machine của `CharsetDecoder.decode`/`CharsetEncoder.encode` với `endOfInput` và `flush` đúng API.

Không “sửa lỗi” bằng cách thay high surrogate cuối chunk thành dấu hỏi — đó là mất dữ liệu do ứng dụng tự gây ra.

## 12. Khi nào cần quản lý `CoderResult` thủ công?

Ở mức nâng cao, bạn có thể gọi:

```java
CoderResult result = decoder.decode(
        inputBytes, outputChars, false);
```

Đây là đoạn minh họa: `decoder` đã tạo, `inputBytes` là ByteBuffer và `outputChars` là CharBuffer; cần import `CoderResult`.

`CoderResult` có các tình huống:

- `UNDERFLOW`: decoder cần thêm input hoặc đã xử lý hết input hiện tại; nếu cuối stream, phải xử lý end-of-input đúng contract.
- `OVERFLOW`: CharBuffer output không còn chỗ; cần flip/consume rồi tiếp tục.
- `isMalformed()`: dãy bytes không hợp lệ.
- `isUnmappable()`: input hợp lệ nhưng không có character mapping.
- `throwException()`: chuyển kết quả lỗi thành ngoại lệ `CharacterCodingException` phù hợp.

Khi dùng `REPORT` và API streaming low-level, bạn có thể theo dõi `inputBytes.position()` để tính vị trí byte gây lỗi tương đối trong cửa sổ, nhưng cần cộng **offset file** và giữ các byte chưa xử lý giữa chunks. Đây là con đường tốt khi hệ thống cần log “UTF-8 malformed tại byte offset 1.234.567” hoặc xử lý dữ liệu rất lớn với diagnostics chuyên sâu.

### 12.1. State machine đúng ở cuối input

Một chu kỳ decoder low-level thường cần:

1. `decode(in,out,false)` cho các chunk trước cuối.
2. `compact()` các byte chưa xử lý, đọc thêm bytes vào phần buffer còn chỗ.
3. Khi EOF: `decode(in,out,true)` để xác nhận input kết thúc thật.
4. `flush(out)` cho phần trạng thái còn lại.
5. Xử lý `OVERFLOW` bằng cách consume output và gọi lại.
6. Khi tạo encoder low-level, cũng thực hiện chu kỳ `encode(...,endOfInput)` và `flush` tương ứng.

Nếu bỏ `endOfInput=true` ở EOF, một chuỗi UTF-8 thiếu byte cuối có thể không được đánh giá chính xác là malformed. Nếu quên preserve bytes underflow, ký tự chia giữa hai lần đọc có thể bị lỗi giả hoặc bị thay thế.

Với mục tiêu bài thực hành thông thường, `InputStreamReader`/`OutputStreamWriter` cung cấp state machine này và ít rủi ro hơn tự viết decoder loop.

## 13. Xử lý lỗi với độ chính xác phù hợp

### 13.1. Exception nào thường xuất hiện?

| Bước | Dấu hiệu | Ví dụ |
|---|---|---|
| Input decoder | `MalformedInputException` | UTF-8 `C3 28` |
| Input decoder | `UnmappableCharacterException` | Charset có byte sequence hợp lệ nhưng không map sang Unicode |
| Output encoder | `UnmappableCharacterException` | `é` → US-ASCII |
| Output encoder | `MalformedInputException` | Unpaired UTF-16 surrogate |
| I/O của source | `NoSuchFileException`, `AccessDeniedException`, `IOException` | Không mở được file |
| I/O của target/staging | `IOException` | Hết dung lượng, thiếu quyền, filesystem lỗi |
| Publish staging | `FileAlreadyExistsException` hoặc `IOException` | Target tồn tại hoặc không move được |

**Không** giả định mọi `MalformedInputException` là “file đang dùng charset khác” — có thể nguồn thực sự hỏng, thiếu bytes do truyền bị cắt, hoặc ứng dụng chọn charset sai.

### 13.2. Có nên thử charset khác sau lỗi?

Nếu format nguồn đã khai báo UTF-8, input malformed nên được **từ chối** hoặc chuyển vào hàng xử lý lỗi, không tự đoán một charset khác rồi đọc tiếp.

Chỉ dùng fallback khi **nghiệp vụ quy định** một tập charset được phép và có cách phân biệt kết quả hợp lệ. Ví dụ hệ thống cũ cho phép Windows-1252/ISO-8859-1 với metadata nguồn; code cần ghi nhận charset đã áp dụng và các trường hợp mơ hồ.

Không tự thay mọi byte malformed bằng `?` rồi tuyên bố convert thành công trọn vẹn, vì dữ liệu sẽ không còn phản ánh bản gốc.

### 13.3. Nếu cần chính sách thay thế có kiểm soát

Một số ứng dụng trình bày log có thể chấp nhận replacement. Ví dụ:

```java
CharsetDecoder permissive = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE)
        .replaceWith("\uFFFD");
```

Đây là snippet trong method, với các import tương ứng. Với encoder, replacement bytes phải hợp lệ trong charset đích và thường sử dụng byte sequence thay thế mặc định; chọn `?` có thể được chấp nhận trong US-ASCII, nhưng không thể coi đó là biểu diễn gốc của Unicode không hỗ trợ.

Nếu chọn REPLACE, nên đo số trường hợp bị thay hoặc ghi nhận ở tầng nghiệp vụ, bởi `CodingErrorAction.REPLACE` **không tự cung cấp báo cáo từng vị trí lỗi**.

## 14. Tính nguyên vẹn dữ liệu: phải xác minh điều gì?

Một bản chuyển mã **đúng** không có nghĩa bytes trước/sau giống nhau. Ngược lại, bytes thường khác ngay cả với cùng văn bản.

| Kiểm tra | Điều xác nhận | Điều không xác nhận |
|---|---|---|
| Không exception từ decoder `REPORT` | Input hợp lệ theo charset nguồn đã chọn | Charset nguồn thật sự đúng về ngữ nghĩa |
| Không exception từ encoder `REPORT` | Unicode đã decode có thể biểu diễn bởi charset đích | Nội dung nghiệp vụ hợp lệ |
| Decode output bằng charset đích | Text đầu ra có thể được đọc lại | Có đảm bảo byte-for-byte giống nguồn không |
| So sánh Unicode nguồn sau decode với Unicode output sau decode | Mức giữ nguyên ký tự theo chính sách | Normalization/newline/metadata của file có thể khác |
| So sánh bytes đầu vào/đầu ra | Chỉ phù hợp nếu cùng encoding và không biến đổi | Không dùng cho transcoding giữa charset khác nhau |
| Checksum bytes | Phát hiện byte khác khi có mẫu chuẩn | Không chứng minh nguồn bytes được giải mã với đúng charset |

Với migration quan trọng, có thể ghi manifest gồm source charset, target charset, size, checksum SHA-256, số record, thời gian và kết quả validation. Nếu nghiệp vụ cho phép normalization thì phải áp dụng quy tắc Unicode normalization minh bạch, không tự diễn ra khi chỉ thay encoding.

### 14.1. Round trip để kiểm tra

Mô hình test:

```text
sourceBytes --decode(sourceCharset)--> characters
characters --encode(targetCharset)--> targetBytes
targetBytes --decode(targetCharset)--> restoredCharacters
assert characters.equals(restoredCharacters)
```

Đây là test tốt khi cả hai encoder/decoder là nghiêm ngặt, input không bị sửa đồng thời và không có transformation khác. Tuy nhiên một round trip đúng **không bảo đảm** charset nguồn đã chọn đúng về mặt lịch sử (một chuỗi bị mojibake vẫn có thể round trip như chính nó).

### 14.2. Chuyển đổi văn bản khác sao chép binary

Không dùng transcoding với ảnh, ZIP, PDF, class file hoặc byte stream bất kỳ chỉ vì muốn đổi đuôi. CharsetDecoder giải thích bytes như ký tự; dữ liệu binary có thể chứa byte sequences bất hợp lệ và bị lỗi hoặc bị biến dạng.

Nếu mục tiêu là giữ nguyên bytes, chọn `Files.copy` hoặc byte streams/FileChannel; nếu mục tiêu là giữ nguyên **ký tự** mà đổi byte encoding, dùng decoder/encoder.

## 15. Memory và performance khi chuyển file lớn

### 15.1. Chi phí theo kích thước file

- `Files.readAllBytes` làm bộ nhớ tạm tăng theo kích thước file, cộng CharBuffer và ByteBuffer đích có thể lớn.
- Pipeline `Reader`/`Writer` với `char[4096]` giữ lượng buffer ứng dụng gần như cố định, không phụ thuộc tổng số ký tự trong file.
- Output byte size có thể **nhỏ hơn hoặc lớn hơn** source: `é` là một byte Latin-1 nhưng hai byte UTF-8; ngược lại, những case chuyển UTF-16LE sang UTF-8 có tỷ lệ khác.
- `BufferedReader`/`BufferedWriter` có thêm char buffers nội bộ; có thể tăng kích thước chunk nếu benchmark cho thấy lợi ích, nhưng không coi càng to càng nhanh.
- Việc encode/decode tiêu thụ CPU, đặc biệt khi phải kiểm tra malformed input; throughput còn tùy disk/network và loại charset.

### 15.2. Nếu file chỉ có một dòng cực dài?

Ví dụ dùng `char[]` đọc theo chunk, **không gọi `readLine()`**, nên một dòng dài hàng trăm MB không tạo một `String` khổng lồ chỉ vì không có newline. Đó là lợi thế cho file lớn có dòng không giới hạn.

Nếu ứng dụng phải parse records sau transcoding, cần tự đặt record length limit và xử lý phân cách dòng/CSV quoting theo format, không trông cậy vào việc chuyển charset tự giới hạn record size.

### 15.3. Theo dõi progress khác độ chính xác của byte offset

Khi dùng `Reader`, số phần tử `n` trả về là **UTF-16 char units**, không phải số byte nguồn đã đọc. Với UTF-8, không thể cộng số char để biết exact byte offset khi gặp lỗi.

Nếu cần tiến độ theo byte, có thể wrap `InputStream` bằng một counter; nhưng do buffering/read-ahead, số byte stream đã lấy không nhất thiết trùng **byte đang được decoder xử lý** tại thời điểm exception. Muốn offset lỗi chính xác, phải quản lý ByteBuffer position/CoderResult và phần bytes chưa xử lý, hoặc thiết kế một decoder có tracking riêng.

## 16. Công bố file đích an toàn và xử lý lỗi

### 16.1. Vì sao không ghi thẳng target quan trọng?

Nếu mở target với `TRUNCATE_EXISTING` rồi bắt đầu viết, mà nửa chừng decoder phát hiện UTF-8 sai, file đích đã bị cắt ngắn hoặc chứa nửa văn bản hợp lệ. Một file migration thất bại có thể làm hỏng bản gốc/đích quan trọng.

```text
Ghi thẳng:
target (bản cũ) → truncate → viết 50% → MALFORMED → target bị dở dang

Ghi staging:
target (bản cũ) ─────────── giữ nguyên trong lúc convert
                       staging (bản mới) → lỗi → xóa staging
                       hoặc
                       staging hoàn chỉnh → publish theo policy
```

**Staging** giúp không đặt tên kết quả cuối lên nội dung đang convert, nhưng bản thân nó không tự giải quyết **atomicity, concurrency hoặc durability**. Cần chính sách riêng cho overwrite, rename, sync file và sync directory nếu ứng dụng yêu cầu.

### 16.2. Tệp đích đã tồn tại thì sao?

Ví dụ `StrictTranscodeDemo` dùng `Files.move(staging,target)` không có `REPLACE_EXISTING` và tạo các tên target mới. Trong ứng dụng thật:

- Nếu **cấm ghi đè**, dùng chính sách create/move phù hợp và xử lý `FileAlreadyExistsException`. Đừng tự chạy `Files.delete(target)` trước rồi move, vì có khoảng thời gian mất target.
- Nếu **được thay thế**, cân nhắc `Files.move(staging,target,REPLACE_EXISTING)` nhưng **không** được bảo đảm move là atomic.
- Nếu cần **atomic replacement**, có thể thử `Files.move(staging,target,ATOMIC_MOVE)` trên provider hỗ trợ; khi chỉ định `ATOMIC_MOVE`, Java bỏ qua các option khác và với target đã tồn tại, chính sách replace có thể **implementation-specific**.
- Nếu cần **crash durability**, sau khi hoàn tất nội dung staging còn cần sync/force tệp và có thể sync directory theo hợp đồng OS trước khi tuyên bố committed; `Files.move` không phải fsync.
- Nếu có nhiều process ghi cùng đích, phải có ownership/locking/versioning; check `Files.exists` riêng lẻ có race.

### 16.3. Cleanup không được xóa đích hợp lệ

Khi convert thất bại, chỉ xóa staging do operation tạo, không xóa target đang tồn tại của phiên bản trước. Khi publish thành công, đổi trạng thái `published` rồi không cố xóa staging như thể nó còn ở tên cũ.

Trong ứng dụng production, nếu cleanup staging cũng thất bại, cần log và lên lịch dọn file tồn đọng. Java try-with-resources có thể giữ lỗi close dưới dạng suppressed exception; khi xử lý, đừng đánh mất exception gốc của decoder.

## 17. Kiểm thử các trường hợp quan trọng

Một bộ test hữu ích nên có:

| Input / tình huống | Source → Target | Mong đợi |
|---|---|---|
| ASCII thuần | UTF-8 → UTF-8 | Bytes và characters giống nhau |
| `é` | ISO-8859-1 → UTF-8 | Byte `E9` thành `C3 A9` |
| Tiếng Việt có dấu | UTF-8 → UTF-16LE | Giữ Unicode sau decode lại |
| Emoji ngoài BMP | UTF-8 → UTF-8 | Không mất surrogate pair dù split chunk |
| UTF-8 `C3 28` | UTF-8 → UTF-8, REPORT | `MalformedInputException` |
| UTF-8 có dãy multi-byte thiếu phần cuối | UTF-8 → UTF-8, REPORT | `MalformedInputException` tại EOF |
| `é` | UTF-8 → US-ASCII, REPORT | `UnmappableCharacterException` |
| String chứa surrogate lẻ (đầu vào char tùy tạo) | Unicode → UTF-8, REPORT | `MalformedInputException` ở encoder |
| UTF-8 bytes nhưng khai nhầm Latin-1 | Latin-1 → UTF-8 | Có thể **không lỗi** nhưng cho mojibake |
| File rỗng | Charset A → Charset B | Tệp đích rỗng theo contract; xem BOM nếu charset đích phát sinh BOM |
| Target đã tồn tại | Không cho phép replace | Phải báo lỗi và giữ đích |
| Disk full/permission | Bất kỳ | Không công bố staging hỏng |
| Input lớn | UTF-8 → UTF-16 | Bộ nhớ không tăng theo kích thước file toàn bộ |
| Source bị thay đổi khi đọc | Bất kỳ | Cần test theo snapshot/ownership policy |
| Source có BOM | UTF-8/UTF-16 | Xử lý theo format contract đã chọn |

### 17.1. Test tách đôi UTF-8 multi-byte

Chuẩn bị chuỗi có emoji hoặc `€` tại các vị trí gần ranh giới của buffer đọc. Chuyển bằng Reader/Writer theo chunk nhỏ và so sánh Unicode sau khi đọc lại. Nếu tự decode **từng mảng bytes độc lập**, test đó sẽ bộc lộ lỗi ở chỗ code point bị chia qua hai lượt I/O.

### 17.2. Test lỗi sau khi đã ghi một phần staging

Đặt một ký tự không thể mã hóa ở gần cuối tệp (ví dụ hơn 10 MB ASCII hợp lệ rồi `☃` và đích US-ASCII). Encoder có thể đã ghi rất nhiều byte staging trước khi nhận ra lỗi. Yêu cầu test:

- Method phải ném exception.
- **Target** chưa có hoặc vẫn là bản cũ.
- Staging của operation được dọn hoặc ghi nhận rõ nếu cleanup thất bại.
- Không có log “SUCCESS/COMMITTED”.
- Không tự retry với `REPLACE`/`IGNORE` nếu policy là strict.

## 18. Những lỗi thường gặp

1. **Đổi tên `.txt` thành `.utf8` và coi đã chuyển charset.** Không thay bytes.
2. **Copy bytes nguyên trạng bằng `Files.copy` dù nguồn/đích có charset khác.** Đó là binary copy, không transcoding.
3. **Dùng charset mặc định của hệ thống** thay vì charset đã quy định.
4. **Nhầm ISO-8859-1 với Windows-1252** ở vùng byte có khác biệt.
5. **Cho rằng detector luôn biết đúng charset nguồn.** Byte sequences có thể hợp lệ trong nhiều bảng mã.
6. **Dùng `new String(bytes, charset)` rồi `getBytes(other)` và kỳ vọng tự báo mọi lỗi.** Nhiều convenience overload thay ký tự không hợp lệ.
7. **Chỉ đặt `REPORT` ở decoder mà quên encoder.** Ký tự không biểu diễn được ở đích vẫn có nguy cơ bị thay.
8. **Chỉ đặt `REPORT` ở encoder mà quên decoder.** Dữ liệu nguồn malformed có thể bị mất từ bước đọc.
9. **Dùng `IGNORE` để “vượt lỗi”** khi yêu cầu chính xác dữ liệu.
10. **Dùng `REPLACE` rồi ghi log “100% không mất ký tự”.** Replacement chính là sự thay đổi dữ liệu.
11. **Giải mã mỗi byte chunk thành một String riêng** làm đứt UTF-8 multi-byte sequence.
12. **Mã hóa từng char[] chunk bằng encoder mới**, làm hỏng surrogate pair nằm qua ranh giới.
13. **Không gọi end-of-input/flush ở low-level decoder** khiến EOF malformed không được phát hiện đúng.
14. **Quên `ByteBuffer.flip()`/`compact()` khi tự triển khai `CoderResult` loop.**
15. **Đếm byte từ `char[].length`.** UTF-8 có số byte khác UTF-16 code units.
16. **Cho rằng `String.length()` là số Unicode code points hoặc ký tự nhìn thấy.** Không đúng cho surrogate pairs/combining marks.
17. **Cho rằng UTF-8 BOM luôn tự bị strip.** Phải định nghĩa BOM policy riêng.
18. **Dùng `UTF_16LE` khi file thật là UTF-16BE.** Sai byte order.
19. **Sử dụng `readLine`/`newLine` trong pipeline muốn bảo toàn chính xác newline.** Có thể chuẩn hóa CRLF/LF ngoài ý muốn.
20. **Ghi trực tiếp target rồi khi decode lỗi vẫn để target dở dang.** Dùng staging và công bố sau thành công.
21. **Xóa target cũ trước khi convert.** Nếu conversion lỗi thì mất phiên bản hợp lệ.
22. **Cho rằng `Files.move` không option là atomic replacement/durable.** Không được API cam kết.
23. **Không kiểm tra target đã tồn tại hoặc bị ghi concurrent.** Có race và rủi ro overwrite.
24. **Không đóng Writer khi có exception.** State encoder/các byte đã buffer có thể chưa xử lý xong, tài nguyên bị rò rỉ.
25. **Không kiểm tra output sau conversion.** Nên có round-trip/semantic verification phù hợp.
26. **So byte nguồn và byte đích rồi báo sai vì khác nhau.** Đó là điều bình thường khi chuyển charset.
27. **Chỉ xem không có exception là chọn đúng charset nguồn.** Mojibake có thể hoàn toàn hợp lệ về cấu trúc.
28. **Đọc toàn file hàng chục GB vào heap** khi chỉ cần chuyển mã theo stream.
29. **Chia sẻ `CharsetDecoder`/`CharsetEncoder` giữa threads** mà không có ownership và reset đúng.
30. **Lẫn lộn UTF-8 malformed với unmappable ở charset đích**, khiến hướng sửa sai.
31. **Không test ký tự ngoài BMP**, chỉ test ASCII nên bỏ sót lỗi surrogate boundary.
32. **Trả về success dù cleanup/publish có lỗi**, khiến job status không phản ánh tệp thực.
33. **Tưởng charset conversion tự bảo vệ khỏi dữ liệu không tin cậy**, bỏ qua giới hạn input size, path validation và các lớp bảo mật.
34. **Lấy `InputStream.available()` làm kích thước file/network còn lại**, rồi cấp buffer tùy tiện.
35. **Cho rằng `UTF-16` và `UTF-16LE` cùng hành vi BOM.** Chọn rõ policy.
36. **Tự replace ký tự không đọc được bằng dấu ? mà không ghi nhận**, gây mất dấu lỗi dữ liệu.
37. **Để file nguồn bị sửa concurrent trong lúc convert**, tạo output không thuộc một phiên bản nhất quán.
38. **Chỉ catch `IOException` và che mất loại lỗi cụ thể**, khiến người dùng không biết sửa charset nguồn hay thay charset đích.
39. **Không xử lý file rỗng, file thiếu newline, text có ký tự NUL**, rồi giả định đều là text lỗi.
40. **Dùng raw bytes CRC/checksum trước/sau để kết luận Unicode giữ nguyên.** Hash bytes thay đổi khi encoding đổi; cần kiểm tra theo ý nghĩa của migration.

## 19. Câu hỏi tự kiểm tra

**1.** Tại sao chuyển ISO-8859-1 → UTF-8 không phải `Files.copy`?  
**Trả lời:** `Files.copy` giữ nguyên bytes, còn transcoding phải decode bytes nguồn thành Unicode rồi encode thành bytes đích.

**2.** `C3 28` được giải mã theo UTF-8 với `REPORT` dẫn tới gì?  
**Trả lời:** `MalformedInputException` vì dãy bytes không hợp lệ theo UTF-8.

**3.** String `Café` hợp lệ nhưng ghi sang US-ASCII với encoder `REPORT` sẽ thế nào?  
**Trả lời:** `UnmappableCharacterException` vì ký tự `é` không có mapping US-ASCII.

**4.** Cần cấu hình `REPORT` ở đâu?  
**Trả lời:** Cả `CharsetDecoder` và `CharsetEncoder`, cho cả malformed và unmappable khi yêu cầu conversion nghiêm ngặt.

**5.** Nếu bytes nguồn đã là UTF-8 của `é` nhưng chọn nhầm ISO-8859-1, decoder REPORT có luôn phát hiện không?  
**Không.** Nó có thể đọc thành `Ã©` mà không lỗi vì từng byte hợp lệ theo Latin-1.

**6.** Vì sao mã hóa từng chunk bằng encoder mới là lỗi tiềm ẩn?  
**Vì** surrogate pair hoặc trạng thái charset có thể trải qua ranh giới chunk; tạo encoder mới làm mất state.

**7.** `Reader.read(char[])` trả `n` tính bằng gì?  
**Trả lời:** Số UTF-16 `char` units đã đọc, không nhất thiết số bytes nguồn hay số Unicode code points.

**8.** `CodingErrorAction.REPLACE` có giữ nguyên mọi Unicode character không?  
**Không.** Nó dùng replacement và có thể mất thông tin gốc.

**9.** Chuyển Latin-1 `Café` từ 4 bytes sang UTF-8 cần bao nhiêu bytes?  
**Trả lời:** 5 bytes (`é` từ E9 thành C3 A9).

**10.** Nếu nguồn có byte UTF-8 lỗi sau khi writer đã ghi nhiều bytes staging, nên làm gì?  
**Trả lời:** Fail, đóng stream, xóa/giữ staging theo cleanup policy, không publish target dở dang.

**11.** `Files.move(staging,target)` không option có bảo đảm atomic replace và power-loss durability không?  
**Không.** Cần contract riêng cho atomicity và sync/durability.

**12.** `UTF_16LE` có giống hoàn toàn `UTF_16` về BOM không?  
**Không.** Một bên cố định little-endian; bên kia có semantics BOM/byte-order riêng.

**13.** Vì sao ví dụ dùng `char[4096]` mà không bị cắt hỏng emoji khi streaming?  
**Trả lời:** Reader và Writer với decoder/encoder giữ state xuyên qua các lần đọc/ghi trong cùng pipeline.

**14.** Sau khi chuyển UTF-8 sang UTF-16LE, `Files.mismatch(source,target)` nên bằng `-1` không?  
**Không.** Hai byte streams có định dạng encoding khác nhau; cần so Unicode sau decode.

**15.** Có thể dùng `Files.readAllBytes` để chuyển file hàng trăm GB không?  
**Không nên.** Nó cấp phát theo toàn bộ file và có giới hạn heap/array; ưu tiên streaming.

**16.** Muốn báo chính xác offset byte lỗi trong một file UTF-8 rất lớn, làm sao?  
**Trả lời:** Tự quản lý bộ đếm bytes và `CoderResult`/ByteBuffer vị trí với xử lý underflow/overflow đúng; exception ở tầng Reader không tự cung cấp absolute byte offset.

## 20. Tổng kết và tài liệu chính thức

**Công thức chuẩn:**

```text
[Bytes nguồn + charset nguồn đã xác định]
     → CharsetDecoder (malformed=REPORT, unmappable=REPORT)
     → Unicode chars (giữ state qua chunks)
     → CharsetEncoder (malformed=REPORT, unmappable=REPORT)
     → Bytes đích trong staging
     → Close thành công + validate + publish theo policy
```

Điểm phải nhớ: **transcoding là bảo toàn văn bản chứ không bảo toàn bytes**; kiểm tra lỗi ở cả *decode* lẫn *encode*. Khi nguồn không hợp lệ hoặc charset đích không biểu diễn được ký tự, **báo lỗi và tránh công bố tệp kết quả dở dang**. Muốn dữ liệu chính xác cần cả charset metadata đúng, xử lý BOM/newline hợp đồng, streaming có state, validation nghiệp vụ và chính sách file lifecycle phù hợp.

Nguồn Java SE 21:

- `Charset` — mô tả charset, `forName`, các conversion helpers: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html
- `CharsetDecoder` — `onMalformedInput`, `onUnmappableCharacter`, `decode`, `CoderResult`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
- `CharsetEncoder` — `encode`, `canEncode`, handling malformed/unmappable chars: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html
- `CodingErrorAction` — `REPORT`, `REPLACE`, `IGNORE`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CodingErrorAction.html
- `InputStreamReader` — stream decoder và charset decoder constructor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html
- `OutputStreamWriter` — stream encoder và charset encoder constructor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/OutputStreamWriter.html
- `MalformedInputException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/MalformedInputException.html
- `UnmappableCharacterException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/UnmappableCharacterException.html
- `Files.move` và `Files.readString/writeString`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html
- Unicode Standard, UTF encoding forms và BOM: https://www.unicode.org/versions/latest/
