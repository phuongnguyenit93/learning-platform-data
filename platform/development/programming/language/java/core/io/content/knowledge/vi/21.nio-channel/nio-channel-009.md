# `Channels.newReader`, `Channels.newWriter` và chuyển đổi charset trong Java NIO

## 1. Bối cảnh: Channel vận chuyển byte, Reader/Writer xử lý ký tự

`ReadableByteChannel` và `WritableByteChannel` thao tác với **byte** qua `ByteBuffer`, trong khi `java.io.Reader` và `java.io.Writer` cung cấp giao diện **ký tự** (`char`/chuỗi Java). Khi dữ liệu là văn bản, giữa hai tầng cần có quá trình chuyển đổi theo **charset**:

```text
ĐỌC:
Nguồn (file/socket/byte stream)
    → ReadableByteChannel: byte
    → CharsetDecoder: byte → ký tự Unicode của Java
    → Reader: char / String

GHI:
Writer: char / String
    → CharsetEncoder: ký tự Java → byte
    → WritableByteChannel: byte
    → Đích (file/socket/byte stream)
```

`java.nio.channels.Channels` là lớp tiện ích làm cầu nối giữa I/O kiểu channel và các API stream/reader/writer truyền thống. Hai nhóm phương thức tập trung của bài:

- `Channels.newReader(...)`: tạo `Reader` để **giải mã** byte lấy từ `ReadableByteChannel` thành ký tự.
- `Channels.newWriter(...)`: tạo `Writer` để **mã hóa** ký tự thành byte rồi ghi vào `WritableByteChannel`.

Các adapter **không biến channel byte thành đối tượng lưu văn bản độc lập**: chúng dùng channel được truyền vào, giữ bộ đệm chuyển đổi riêng và có quan hệ vòng đời với channel. Khái niệm "charset" quyết định byte nào biểu diễn ký tự nào; nếu chọn sai, văn bản có thể lỗi dù đọc/ghi channel không báo lỗi I/O.

Sau bài học, bạn cần chọn đúng overload, quản lý charset minh bạch, kiểm soát lỗi giải mã/mã hóa, đóng tài nguyên và hiểu giới hạn khi ghép Reader/Writer với channel.

## 2. Các overload chính xác trong `java.nio.channels.Channels`

Java SE 17+ hỗ trợ sáu overload quan trọng sau:

| Đọc hoặc ghi | Chữ ký | Khi nên dùng |
|---|---|---|
| Đọc | `newReader(ReadableByteChannel ch, String csName)` | Tên charset ở dạng chuỗi, chẳng hạn `"UTF-8"` |
| Đọc | `newReader(ReadableByteChannel ch, Charset charset)` | Charset đã biết, thường dùng `StandardCharsets.UTF_8` |
| Đọc | `newReader(ReadableByteChannel ch, CharsetDecoder dec, int minBufferCap)` | Cần điều chỉnh chính sách lỗi khi giải mã hoặc cấp phát buffer |
| Ghi | `newWriter(WritableByteChannel ch, String csName)` | Tên charset ở dạng chuỗi |
| Ghi | `newWriter(WritableByteChannel ch, Charset charset)` | Chọn charset rõ ràng, không cần cấu hình encoder riêng |
| Ghi | `newWriter(WritableByteChannel ch, CharsetEncoder enc, int minBufferCap)` | Cần chính sách lỗi khi mã hóa hoặc cấu hình encoder |

Các overload nhận `Charset` có từ Java 10, nên dùng được trên Java 17+. Với overload nhận `Charset`:

```java
Reader reader = Channels.newReader(channel, StandardCharsets.UTF_8);
Writer writer = Channels.newWriter(channel, StandardCharsets.UTF_8);
```

*Hai dòng trên là minh họa độc lập: `channel` của dòng đầu phải là `ReadableByteChannel`; dòng thứ hai phải là `WritableByteChannel`. Chúng không nhất thiết là cùng một đối tượng.* Mỗi lời gọi tạo adapter trên channel cho trước, **không tự mở file** và không nhận một `Path`.

Về mặt hành vi, hai overload này tương đương với:

```java
Reader reader = Channels.newReader(
        readableChannel, StandardCharsets.UTF_8.newDecoder(), -1);

Writer writer = Channels.newWriter(
        writableChannel, StandardCharsets.UTF_8.newEncoder(), -1);
```

Đây là đoạn minh họa cần các biến channel thích hợp và import `java.io.Reader`, `java.io.Writer`, `java.nio.channels.Channels`, `java.nio.charset.StandardCharsets`. Tùy chọn `-1` ở đây có nghĩa dùng dung lượng buffer mặc định do implementation quyết định.

Với overload `String csName`, Java phải phân giải tên charset, ví dụ `"UTF-8"`. Tên không hợp lệ/không được hỗ trợ có thể gây `IllegalCharsetNameException` hoặc `UnsupportedCharsetException`. Nên ưu tiên `StandardCharsets.UTF_8`, `StandardCharsets.ISO_8859_1`… khi biết charset lúc biên dịch để tránh lỗi chính tả, kiểm soát môi trường và loại bỏ phụ thuộc vào charset mặc định.

**Không có overload `Channels.newReader(channel)` hoặc `Channels.newWriter(channel)` chỉ một tham số**. Việc chọn charset là một phần bắt buộc của giao diện này.

## 3. Chuyển đổi charset là gì?

Java `String` và phần lớn API ký tự lưu chuỗi theo đơn vị mã UTF-16 (`char` là một code unit 16-bit). Một ký tự Unicode có thể gồm một hoặc hai `char`, ví dụ nhiều emoji dùng **surrogate pair**. Channel chỉ vận chuyển byte; charset ánh xạ giữa chuỗi code unit hợp lệ và byte.

Ví dụ ký tự `é` (`U+00E9`):

| Charset | Byte mã hóa `é` (hex) | Số byte |
|---|---|---|
| UTF-8 | `C3 A9` | 2 |
| ISO-8859-1 | `E9` | 1 |
| UTF-16BE | `00 E9` | 2 |

Cùng byte nhưng dùng charset khác khi đọc có thể tạo ra văn bản khác:

```text
Byte thực tế (UTF-8): C3 A9
Giải mã UTF-8:          é
Giải mã ISO-8859-1:    Ã©
```

Trường hợp chọn sai nhưng mỗi byte vẫn được charset đích chấp nhận, kết quả là **mojibake** (chuỗi sai hiển thị) chứ không nhất thiết có ngoại lệ. Vì vậy, không thể dựa vào việc `Reader.read()` không lỗi để khẳng định đã chọn đúng charset.

Ngược lại, chuỗi byte `C3 28` không phải UTF-8 hợp lệ: sau byte mở đầu `C3` phải là một continuation byte, nhưng `28` không phải continuation byte. Khi `CharsetDecoder` ở chế độ `REPORT`, việc đọc có thể ném `MalformedInputException`.

Chiều ghi có lỗi khác: một số ký tự không có biểu diễn trong charset đích. Chẳng hạn `☕` (`U+2615`) không mã hóa được trong ISO-8859-1; encoder báo lỗi **unmappable character** nếu cấu hình `REPORT`.

## 4. Dùng `newReader` để đọc văn bản từ channel

Ví dụ đọc file UTF-8 bằng channel:

```java
import java.io.Reader;
import java.nio.channels.Channels;
import java.nio.channels.ReadableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

Path path = Path.of("notes.txt");

try (ReadableByteChannel channel = Files.newByteChannel(path);
     Reader reader = Channels.newReader(
             channel, StandardCharsets.UTF_8)) {

    char[] chars = new char[1024];
    int count;
    while ((count = reader.read(chars)) != -1) {
        System.out.print(new String(chars, 0, count));
    }
}
```

Đây là **đoạn mã minh họa trong phương thức khai báo `throws IOException`**, không phải tệp Java độc lập có `main`. `Files.newByteChannel(path)` mở channel cho đọc; `newReader` dùng UTF-8 giải mã; `reader.read(chars)` trả số `char` thực sự đọc được, `-1` khi kết thúc.

Lưu ý:

- `reader.read(chars)` là thao tác trên **char buffer**; một lần đọc không tương ứng với một byte hay một ký tự Unicode hoàn chỉnh theo nghĩa code point.
- Một lần đọc có thể trả ít ký tự hơn kích thước mảng mà chưa đạt EOF. Với dữ liệu lớn, đọc theo vòng lặp.
- Dùng đúng phạm vi `0..count`, không in toàn bộ mảng nếu lần đọc cuối có ít dữ liệu.
- Nếu chỉ cần toàn bộ văn bản của một file nhỏ với charset cụ thể, `Files.readString(path, StandardCharsets.UTF_8)` đơn giản hơn. `Channels.newReader` có ích khi nguồn đã là channel hoặc cần một API nhận `Reader`.
- Đừng dùng `new String(bytes)` hoặc `new InputStreamReader(input)` mà không nêu charset khi muốn kết quả độc lập môi trường.

### 4.1. Đọc theo dòng

`Reader` từ `Channels.newReader` cung cấp thao tác đọc ký tự, không có `readLine()`. Để đọc theo dòng, bọc trong `BufferedReader`:

```java
try (var reader = new java.io.BufferedReader(
        Channels.newReader(
                Files.newByteChannel(Path.of("notes.txt")),
                StandardCharsets.UTF_8))) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

*Đoạn minh họa nằm trong method xử lý `IOException`; `Channels`/`StandardCharsets`/`Files`/`Path` đã được import.* `BufferedReader` thêm chức năng đọc dòng và cơ chế buffer ký tự; `Channels.newReader` tự có bộ đệm **byte** phục vụ decoder. `readLine()` không bao gồm dấu kết thúc dòng trong kết quả, nên khi tái tạo văn bản gốc từ các dòng cần chính sách giữ xuống dòng phù hợp.

## 5. Dùng `newWriter` để ghi văn bản ra channel

Ví dụ mở file output, ghi UTF-8:

```java
import java.io.Writer;
import java.nio.channels.Channels;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("notes.txt");

try (WritableByteChannel channel = Files.newByteChannel(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
     Writer writer = Channels.newWriter(
             channel, StandardCharsets.UTF_8)) {

    writer.write("Xin chào");
    writer.write(System.lineSeparator());
}
```

Đây là đoạn minh họa trong method xử lý `IOException`. `Writer` nhận ký tự từ Java, encoder chuyển thành byte UTF-8 và channel ghi ra file. Các option `CREATE`, `TRUNCATE_EXISTING`, `WRITE` có nghĩa: tạo nếu chưa có, xóa nội dung cũ khi mở, mở để ghi. Nếu muốn nối tiếp, thiết kế option khác như `APPEND` và bảo đảm cấu hình thích hợp; không dùng `TRUNCATE_EXISTING` khi muốn giữ file cũ.

**Thời điểm byte tới đích:** Writer có buffer byte nội bộ. `write` có thể giữ một phần dữ liệu trong buffer trước khi chuyển cho channel. `flush()` yêu cầu đẩy dữ liệu đã buffer sang channel; `close()` hoàn tất xử lý encoder, flush phần chưa ghi và đóng channel bên dưới. `flush()` không có nghĩa dữ liệu đã bền vững trên thiết bị lưu trữ. Nếu cần độ bền ghi file sau sự cố, đó là yêu cầu riêng, chẳng hạn `FileChannel.force(...)` với điều kiện áp dụng.

### 5.1. Có nên bọc `BufferedWriter`?

`BufferedWriter` thêm **buffer ký tự** ở lớp ngoài:

```java
try (var writer = new java.io.BufferedWriter(
        Channels.newWriter(
                Files.newByteChannel(
                        Path.of("notes.txt"),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING),
                StandardCharsets.UTF_8))) {

    writer.write("Dòng 1");
    writer.newLine();
    writer.write("Dòng 2");
}
```

Đây là đoạn minh họa trong method xử lý `IOException`. Lớp ngoài có thể giảm số lời gọi nhỏ xuống lớp encoder và hỗ trợ `newLine()`. Không vì vậy mà kết luận mọi trường hợp phải thêm `BufferedWriter`: hiệu quả phụ thuộc kiểu ghi, buffer và sink. `Writer` từ `Channels` vốn đã có buffer byte nội bộ.

## 6. Mặc định xử lý lỗi của adapter và cách cấu hình

**Điểm khác biệt dễ bỏ qua:** overload `Channels.newReader(channel, Charset)` và `Channels.newWriter(channel, Charset)` dùng decoder/encoder mới với hành động mặc định là **`CodingErrorAction.REPORT`** cho cả lỗi malformed và unmappable. Có nghĩa chúng báo lỗi thay vì tự lặng lẽ thay bằng ký tự dự phòng.

Tùy chọn chính sách theo từng chiều:

| Hành động | Ý nghĩa khi gặp dữ liệu lỗi | Khi cân nhắc |
|---|---|---|
| `REPORT` | Báo lỗi (qua exception khi adapter đọc/ghi) | Dữ liệu cấu hình, giao thức chặt chẽ, kiểm thử tính toàn vẹn |
| `REPLACE` | Thay bằng ký tự/byte thay thế do decoder/encoder quy định | Hiển thị best-effort khi việc mất thông tin được chấp nhận |
| `IGNORE` | Bỏ qua phần dữ liệu không giải mã/mã hóa được | Chỉ khi nghiệp vụ chấp nhận mất dữ liệu mà không có ký hiệu thay thế |

Cấu hình decoder:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);

Reader reader = Channels.newReader(sourceChannel, decoder, -1);
```

Đoạn minh họa giả định `sourceChannel` là `ReadableByteChannel` đã mở; import `CharsetDecoder`, `CodingErrorAction`, `StandardCharsets`, `Reader` và `Channels`. Decoder UTF-8 mặc định thường thay lỗi bằng `U+FFFD` (ký tự thay thế `�`) khi đã chọn `REPLACE`; giá trị thay thế có thể cấu hình với `CharsetDecoder.replaceWith(...)`.

Cấu hình encoder:

```java
CharsetEncoder encoder = StandardCharsets.ISO_8859_1
        .newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);

Writer writer = Channels.newWriter(outputChannel, encoder, -1);
```

Đoạn minh họa giả định `outputChannel` là `WritableByteChannel` đã mở, đã import các lớp phù hợp. Encoder ISO-8859-1 có byte thay thế mặc định là `?` (0x3F). Với encoder khác, không đoán byte thay thế: xem `replacement()` và contract của charset. `REPLACE` hoặc `IGNORE` tạo kết quả có thể mất thông tin, không dùng nếu yêu cầu byte round-trip chính xác.

`MalformedInputException` và `UnmappableCharacterException` đều là subtype của `CharacterCodingException`, kế thừa `IOException`. Việc chuyển lỗi ra ngoài diễn ra khi `read`/`write`/`flush`/`close` thực sự xử lý dữ liệu, không nhất thiết ngay lúc tạo Reader/Writer.

### 6.1. Phân biệt malformed và unmappable

- **Malformed input**: một chuỗi byte hoặc chuỗi `char` **sai quy tắc** của encoding được chọn, ví dụ byte UTF-8 `C3 28`; hoặc UTF-16 chứa high surrogate không có low surrogate tương ứng khi encode.
- **Unmappable character**: đầu vào hợp lệ về cấu trúc nhưng không biểu diễn được trong charset đích, ví dụ `☕` hợp lệ của Java String nhưng ISO-8859-1 không hỗ trợ.
- Charset mismatch có thể tạo văn bản sai mà **không có lỗi** nếu decoder vẫn chấp nhận mọi byte. Chính sách `REPORT` không tự phát hiện chọn sai charset khi byte vẫn hợp lệ theo charset đã chọn.

Giải pháp xử lý văn bản chính xác luôn cần biết định dạng nguồn (spec/protocol/metadata/user choice) và mã hóa đích.

## 7. Ví dụ Java 17+ chạy được: round-trip và báo lỗi charset

Đây là ví dụ hoàn chỉnh, không phụ thuộc file trên máy. Nó tạo channel từ `ByteArrayOutputStream` và `ByteArrayInputStream` bằng `Channels.newChannel`. Kết quả minh họa cả vòng khứ hồi UTF-8 lẫn lựa chọn `REPORT` / `REPLACE`.

**Tệp nguồn:** `ChannelCharsetDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.Reader;
import java.io.StringWriter;
import java.io.Writer;
import java.nio.channels.Channels;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;

public class ChannelCharsetDemo {

    private static String readAll(Reader reader) throws IOException {
        StringWriter result = new StringWriter();
        reader.transferTo(result); // Có từ Java 10.
        return result.toString();
    }

    public static void main(String[] args) throws IOException {
        // Unicode escapes giúp mã nguồn không phụ thuộc encoding khi copy.
        String message = "C\u00E0 ph\u00EA \u2615";
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();

        try (Writer writer = Channels.newWriter(
                Channels.newChannel(encoded), StandardCharsets.UTF_8)) {
            writer.write(message);
        }

        byte[] utf8 = encoded.toByteArray();
        try (Reader reader = Channels.newReader(
                Channels.newChannel(new ByteArrayInputStream(utf8)),
                StandardCharsets.UTF_8)) {
            System.out.println("UTF-8 round-trip: "
                    + message.equals(readAll(reader)));
        }

        // C3 phải đi với continuation byte; 28 không phải continuation.
        byte[] malformed = {(byte) 0xC3, (byte) 0x28};

        try (Reader reader = Channels.newReader(
                Channels.newChannel(new ByteArrayInputStream(malformed)),
                StandardCharsets.UTF_8)) {
            readAll(reader);
        } catch (MalformedInputException ex) {
            System.out.println("decode strict: MalformedInputException");
        }

        CharsetDecoder forgivingDecoder = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPLACE);

        try (Reader reader = Channels.newReader(
                Channels.newChannel(new ByteArrayInputStream(malformed)),
                forgivingDecoder, -1)) {
            System.out.println("decode replace equals: "
                    + "\uFFFD(".equals(readAll(reader)));
        }

        try (Writer writer = Channels.newWriter(
                Channels.newChannel(new ByteArrayOutputStream()),
                StandardCharsets.ISO_8859_1)) {
            writer.write("\u2615");
        } catch (UnmappableCharacterException ex) {
            System.out.println("encode strict: UnmappableCharacterException");
        }

        ByteArrayOutputStream replaced = new ByteArrayOutputStream();
        CharsetEncoder forgivingEncoder = StandardCharsets.ISO_8859_1
                .newEncoder()
                .onUnmappableCharacter(CodingErrorAction.REPLACE);

        try (Writer writer = Channels.newWriter(
                Channels.newChannel(replaced), forgivingEncoder, -1)) {
            writer.write("\u2615");
        }

        System.out.println("encode replace: "
                + new String(replaced.toByteArray(),
                             StandardCharsets.ISO_8859_1));
    }
}
```

Biên dịch/chạy tại thư mục chứa file:

```bash
javac ChannelCharsetDemo.java
java ChannelCharsetDemo
```

**Stdout (ASCII, độc lập khả năng hiển thị emoji của terminal):**

```text
UTF-8 round-trip: true
decode strict: MalformedInputException
decode replace equals: true
encode strict: UnmappableCharacterException
encode replace: ?
```

Giải thích kết quả:

1. Writer mã hóa `"Cà phê ☕"` thành UTF-8; Reader dùng **cùng** charset giải mã, nên so sánh với chuỗi đầu là `true`.
2. Decoder UTF-8 mặc định trên `Channels.newReader` dùng `REPORT`. Khi gặp `C3 28`, Reader ném `MalformedInputException`; chương trình bắt riêng ngoại lệ này.
3. Decoder tùy biến dùng `REPLACE` tạo `"\uFFFD("`, nên phép so sánh in `true`.
4. ISO-8859-1 không thể biểu diễn `☕`; writer mặc định báo `UnmappableCharacterException`.
5. Encoder đã chuyển sang `REPLACE` ghi byte dự phòng; khi đọc lại bằng ISO-8859-1, kết quả là ký tự `?`.

`ByteArrayOutputStream` có thể lấy byte sau khi wrapper đóng; nguồn byte dùng trong ví dụ cũng không cần dọn tệp. Nếu thay bằng socket/file thật, đóng Reader/Writer sẽ đóng channel, nên phải quản lý quyền sở hữu tài nguyên phù hợp.

## 8. Chuyển mã văn bản: từ một charset sang charset khác

“Transcoding” văn bản là **decode từ charset nguồn rồi encode theo charset đích**. Không nên đổi nhãn charset của byte array và mong byte tự biến đổi. Sơ đồ:

```text
file ISO-8859-1 --[ReadableByteChannel]
                 --[CharsetDecoder ISO-8859-1]
                 --> char / String
                 --[CharsetEncoder UTF-8]
                 --[WritableByteChannel] --> file UTF-8
```

Phương thức dưới đây chuyển nội dung theo luồng, không giữ cả file trong RAM:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.channels.Channels;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TextTranscoder {
    public static void transcode(
            Path source, Charset sourceCharset,
            Path target, Charset targetCharset) throws IOException {

        try (Reader reader = Channels.newReader(
                Files.newByteChannel(source), sourceCharset);
             Writer writer = Channels.newWriter(
                Files.newByteChannel(target,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING,
                        StandardOpenOption.WRITE),
                targetCharset)) {

            char[] chunk = new char[4096];
            int count;

            while ((count = reader.read(chunk)) != -1) {
                writer.write(chunk, 0, count);
            }
        }
    }
}
```

Đây là **class helper biên dịch được** (`TextTranscoder.java`), không có `main` và không có stdout. Ví dụ gọi bên ngoài:

```java
TextTranscoder.transcode(
        Path.of("source-latin1.txt"),
        StandardCharsets.ISO_8859_1,
        Path.of("target-utf8.txt"),
        StandardCharsets.UTF_8);
```

Đoạn gọi minh họa yêu cầu các import `Path`, `StandardCharsets` và xử lý `IOException`; file đầu vào phải tồn tại. Nguồn và đích cần là **hai đường dẫn không trỏ tới cùng file**, bởi mở writer với `TRUNCATE_EXISTING` có thể phá dữ liệu nguồn nếu chúng trùng nhau. Với dữ liệu quan trọng, ghi vào file tạm rồi thay thế file đích theo quy trình an toàn sau khi thành công, đồng thời xử lý lỗi và quyền truy cập.

Lưu ý:

- Mỗi lần đọc có thể trả vài ký tự, không có quan hệ 1:1 với số byte đọc hoặc ghi.
- `Writer` thực hiện encode khi ghi và hoàn tất dữ liệu còn buffer khi đóng; không cần chuyển `char[]` thành byte thủ công.
- Số ký tự và số byte trước/sau có thể khác nhau. Ví dụ ISO-8859-1 `é` là một byte, UTF-8 `é` là hai byte.
- Nếu ký tự nguồn không có trong đích, encoder mặc định `REPORT` sẽ báo lỗi; việc “đọc được” không có nghĩa “ghi sang charset khác không mất thông tin”.
- Đây là chuyển đổi **văn bản**; không dùng để xử lý tệp nhị phân, ảnh, ZIP, hoặc byte protocol không chứa văn bản.
- Cần quyết định có giữ/chuẩn hóa xuống dòng, Unicode normalization và BOM hay không nếu nghiệp vụ yêu cầu. Các thao tác đó **không** tự xảy ra chỉ vì đổi charset.

## 9. `minBufferCap` và thực tế buffering

Hai overload chi tiết nhận `minBufferCap`:

```java
Channels.newReader(readable, decoder, minBufferCap);
Channels.newWriter(writable, encoder, minBufferCap);
```

`minBufferCap` mô tả **dung lượng tối thiểu của bộ đệm byte nội bộ** khi adapter đọc/ghi, hoặc `-1` để dùng mặc định do implementation quyết định. Với Writer, tài liệu API cho phép implementation **bỏ qua** giá trị này. Vì vậy:

- Tham số là capacity của **byte buffer**, không phải số `char` của `String`/`char[]`.
- Nó **không** giới hạn tổng kích thước file/văn bản, độ dài một lần `read` hoặc `write`, số byte cuối cùng trên đĩa, hay số byte trong charset.
- Giá trị lớn không đồng nghĩa chắc chắn nhanh hơn. Ảnh hưởng thực tế phụ thuộc cách adapter giải mã/mã hóa, kiểu channel, kích thước lời gọi và I/O bên dưới.
- Khi chưa có bằng chứng đo đạc hiệu năng, dùng overload `Charset` hoặc `-1`. Nếu muốn tối ưu, benchmark một workload thực tế với nhiều ngôn ngữ/độ dài chuỗi, tránh suy luận bằng mắt.

Bộ đệm nội bộ là một nguyên nhân dẫn tới vấn đề **vị trí channel**: Reader có thể đọc nhiều byte từ channel để chuẩn bị decode dù caller mới lấy một ít `char`. Nếu sau đó một phần code khác đọc trực tiếp từ cùng channel, nó có thể bắt đầu ở vị trí byte đã tiến xa hơn dự kiến.

## 10. Vòng đời tài nguyên và chia sẻ channel

### 10.1. Đóng wrapper cũng đóng channel

Theo contract `Channels.newReader` và `newWriter`, **`close()` của wrapper đóng channel bên dưới**. Đây là điểm quan trọng khi channel đến từ caller:

```java
ReadableByteChannel channel = Files.newByteChannel(Path.of("notes.txt"));
Reader reader = Channels.newReader(channel, StandardCharsets.UTF_8);

reader.close();
System.out.println(channel.isOpen()); // false
```

Đoạn minh họa giả định file tồn tại, import phù hợp, method xử lý `IOException`. Sau khi `reader.close()`, channel không còn dùng được; đừng ghi/đọc tiếp bằng channel như trước. Đóng Writer cũng đóng WritableByteChannel bên dưới.

**Khuyến nghị:** trong vùng sở hữu tài nguyên, dùng `try-with-resources`. Nếu API caller phải giữ channel mở để dùng tiếp, không tự ý tạo wrapper rồi đóng mà không thỏa thuận contract; cân nhắc tách lifecycle hoặc điều chỉnh API để người sở hữu quyết định việc đóng.

### 10.2. Tránh hai adapter cùng đọc/ghi trên một channel

Hai Reader riêng cùng dùng một `ReadableByteChannel` **không** sở hữu hai vị trí byte độc lập. Mỗi Reader có buffer và decoder state riêng; việc gọi xen kẽ tạo ra khả năng đọc lẫn byte, đặc biệt với mã hóa nhiều byte.

Tương tự, việc tạo hai Writer trên cùng một channel rồi ghi xen kẽ có thể làm thứ tự byte không khớp với thứ tự ký tự mong muốn, nhất là khi một Writer còn byte đang buffer. Trên `FileChannel` có file position dùng chung, trộn `channel.position(...)`, `channel.read(ByteBuffer)` và `Reader.read(...)` có thể phá các giả định về vị trí.

Nếu nghiệp vụ cần đọc các đoạn độc lập, hãy quản lý channel/stream và decoder riêng theo đoạn, xác định offset theo **byte** và không cắt giữa chuỗi byte nhiều phần. Đừng chia văn bản UTF-8 theo offset bất kỳ rồi decode mỗi khúc như một văn bản hợp lệ độc lập.

### 10.3. Non-blocking channel là một giới hạn thực tế

`Channels.newReader`/`newWriter` là adapter API ký tự đồng bộ. Theo tài liệu, nếu một **selectable channel** đang ở chế độ non-blocking vào lúc adapter cần thực hiện I/O, nó có thể ném `IllegalBlockingModeException`. Những wrapper này không tự biến quy trình sang selector/reactive/asynchronous I/O.

Ví dụ với `SocketChannel` cấu hình `configureBlocking(false)`, không dùng `Channels.newReader(socket, UTF_8)` như một lời giải tự động cho protocol non-blocking. Thay vào đó, với `Selector` đọc/ghi `ByteBuffer` và quản lý `CharsetDecoder`/`CharsetEncoder` theo trạng thái của connection và ranh giới thông điệp, gồm các lần decode thiếu byte và flush cuối luồng.

### 10.4. CharsetDecoder/CharsetEncoder giữ trạng thái

Các codec có thể là **stateful** và nói chung không an toàn cho việc nhiều thread cùng thao tác trên cùng instance. Với mỗi luồng dữ liệu logic, thường tạo decoder/encoder riêng bằng `charset.newDecoder()`/`charset.newEncoder()`. Không đưa cùng một decoder đang được Reader sử dụng cho Reader khác, hoặc gọi `decode(...)` thủ công xen kẽ với Reader sử dụng nó.

Khi bắt đầu một luồng văn bản mới, đừng giả định có thể tái sử dụng nguyên trạng một coder còn state của luồng trước. Thiết kế vòng đời codec riêng, hoặc reset một cách tường minh khi API/contract cho phép.

## 11. Phân biệt các API gần nhau

| Nhu cầu | API phù hợp | Lưu ý |
|---|---|---|
| Channel byte → ký tự | `Channels.newReader(ch, charset)` | Giải mã byte; wrapper đóng channel khi close |
| Ký tự → channel byte | `Channels.newWriter(ch, charset)` | Mã hóa ký tự; wrapper đóng channel khi close |
| InputStream byte → ký tự | `new InputStreamReader(input, charset)` | Không cần tạo channel trung gian khi đã có InputStream |
| Ký tự → OutputStream byte | `new OutputStreamWriter(output, charset)` | Không cần channel nếu chỉ làm việc với stream |
| File văn bản nhỏ → String | `Files.readString(path, charset)` | Tự xử lý mở/đóng file theo API |
| String → file | `Files.writeString(path, text, charset, options...)` | Dễ sử dụng hơn khi không cần channel |
| Channel byte → InputStream byte | `Channels.newInputStream(ch)` | Không thực hiện chuyển đổi charset |
| OutputStream byte → channel byte | `Channels.newChannel(output)` | Không thực hiện chuyển đổi charset |
| Channel byte → ByteBuffer | `channel.read(buffer)`/`write(buffer)` | Cấp byte thấp hơn; caller tự quyết định decode/encode |

Hai điểm thường gây nhầm:

1. **`Channels.newInputStream` không phải `Channels.newReader`.** Stream mang byte, Reader mang ký tự Unicode sau giải mã.
2. **`Charset.encode/decode` convenience methods và adapter `newReader/newWriter` có thể có chính sách lỗi khác nhau.** Đọc contract của API bạn thực sự gọi; với adapter dựa trên `Charset`, lỗi mặc định là `REPORT`.

## 12. BOM, xuống dòng và tính toàn vẹn nội dung

### 12.1. Byte Order Mark (BOM)

Một số tệp văn bản bắt đầu với BOM, ví dụ UTF-8 BOM bytes `EF BB BF`, UTF-16BE `FE FF`, UTF-16LE `FF FE`. BOM giúp mô tả thứ tự byte với một số định dạng, nhưng cách xử lý phụ thuộc charset và decoder cụ thể.

Không được cho rằng `Channels.newReader(..., UTF_8)` luôn “tự xóa mọi BOM”. Với UTF-8, BOM có thể được giải mã thành ký tự `U+FEFF` ở đầu nội dung. Nếu protocol quy định BOM tùy chọn, hãy xây dựng quy tắc đọc đầu vào cụ thể và kiểm tra bằng dữ liệu thật. Đừng xóa mọi `U+FEFF` giữa văn bản vì nó có thể xuất hiện với ý nghĩa khác ngoài marker đầu file.

### 12.2. Kết thúc dòng và normalization

`newReader`/`newWriter` **không tự chuyển** CRLF (`\r\n`) thành LF (`\n`), cũng không tự chuẩn hóa Unicode sang NFC/NFD. `BufferedReader.readLine()` có hành vi tách dòng, nhưng đó là tầng riêng. Khi chuyển mã tệp cấu hình, CSV hoặc protocol ký số, khác biệt của line endings, BOM và normalization có thể ảnh hưởng byte output hoặc chữ ký. Xác định chính sách chuyển đổi trước khi xử lý.

### 12.3. Round-trip cần điều kiện rõ

Đọc rồi ghi bằng cùng charset không phải phép bảo toàn byte cho mọi input. Điều kiện cần xét:

- Byte nguồn có hợp lệ với charset không?
- Decoder và encoder có thể ánh xạ qua Unicode rồi trở về đúng byte ban đầu không? Có encoding cho nhiều biểu diễn byte của cùng chuỗi ký tự.
- Có dùng `REPLACE`/`IGNORE` gây mất thông tin không?
- Có thêm/xóa BOM, đổi xuống dòng hoặc normalization không?
- Có dạng file không phải văn bản thuần mà chứa byte có ý nghĩa ngoài charset không?

Nếu yêu cầu **copy byte đúng 100%**, hãy copy bytes bằng channel/stream mà không qua `Reader`/`Writer`. Nếu yêu cầu **văn bản có thể đọc/ghi qua charset cụ thể**, dùng decoder/encoder và kiểm tra kết quả phù hợp.

## 13. Các lỗi phổ biến và cách khắc phục

1. **Quên charset** rồi tin rằng mọi môi trường dùng UTF-8. Khi dùng Channels adapter, truyền `StandardCharsets.UTF_8` hoặc charset đúng theo protocol.
2. **Nhầm hướng chuyển đổi.** `newReader` nhận bytes từ channel và decode; `newWriter` nhận chars và encode. Không gọi `newReader` cho WritableByteChannel chỉ có khả năng ghi.
3. **Dùng `newReader(ch)` hoặc `newWriter(ch)`.** Không có overload một tham số; phải nêu charset/decoder/encoder.
4. **Xem `Charset` và `CharsetDecoder` là cùng kiểu.** Overload decoder còn yêu cầu `minBufferCap`; overload Charset không có tham số buffer.
5. **Dùng nhầm mã hóa đích** khiến văn bản mojibake. Không có exception trong một số trường hợp charset mismatch; phải dựa vào thông số nguồn.
6. **Nghĩ codec luôn tự thay ký tự không hợp lệ.** Channels adapter với overload Charset dùng `REPORT`; xử lý `CharacterCodingException` hoặc tạo coder có `CodingErrorAction` cụ thể.
7. **Nhầm “malformed” với “unmappable”.** Một bên sai biểu diễn đầu vào, bên kia ký tự hợp lệ nhưng không encode/decode được theo bảng ánh xạ.
8. **Tin `REPLACE` là không mất dữ liệu.** Replacement bảo toàn khả năng tiếp tục xử lý nhưng có thể mất byte hoặc ký tự gốc.
9. **Chỉ gọi `write` mà không đóng/flush writer**. Dữ liệu có thể còn ở buffer. Dùng `try-with-resources` trong phạm vi sở hữu channel.
10. **Tưởng `flush()` bảo đảm file đã fsync.** Đẩy buffer Java xuống channel khác với cam kết durability của hệ thống lưu trữ.
11. **Đóng Reader/Writer rồi vẫn muốn dùng channel cũ.** `close` đóng cả channel; quy định rõ ownership.
12. **Gọi `readLine()` trực tiếp trên `Reader`.** Dùng `BufferedReader` cho xử lý theo dòng.
13. **Trộn đọc trực tiếp channel với Reader trên cùng channel**. Read-ahead và decoder state làm sai vị trí byte mong đợi.
14. **Gắn Reader/Writer đồng bộ lên non-blocking SocketChannel**. Có thể gặp `IllegalBlockingModeException`; non-blocking I/O cần quản lý ByteBuffer và decoder theo state machine.
15. **Chia byte UTF-8 bất kỳ rồi decode từng chunk riêng biệt**. Một ký tự có thể trải qua nhiều byte. Dùng decoder stateful trên chuỗi byte liên tục, hoặc adapter Reader quản lý phần byte chưa hoàn chỉnh.
16. **Dùng `minBufferCap` như giới hạn kích thước văn bản**. Nó chỉ liên quan buffer byte nội bộ và có thể bị implementation bỏ qua với Writer.
17. **Tưởng đóng channel chỉ giải phóng metadata mà không cần xử lý trạng thái encoder**. Việc đóng Writer hoàn tất mã hóa, flush, rồi đóng channel.
18. **Dùng chuyển mã ký tự để copy dữ liệu nhị phân**. Văn bản decode/encode có thể biến đổi bytes; copy binary theo bytes.
19. **Quên BOM và xuống dòng** khi cần byte giống file ban đầu. Charset không tự bảo đảm tính tương đương byte.
20. **Dùng chung CharsetDecoder/Encoder ở nhiều thread**. Các codec có state, không mặc định thread-safe.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Một `ReadableByteChannel` chứa byte UTF-8. Phương thức nào trả `Reader` với UTF-8?  
**Trả lời:** `Channels.newReader(channel, StandardCharsets.UTF_8)`.

**Câu 2.** Ghi ký tự `☕` qua `Channels.newWriter(channel, StandardCharsets.ISO_8859_1)` có thể xảy ra điều gì?  
**Trả lời:** Khi encode, mặc định `REPORT` nên có thể ném `UnmappableCharacterException`; charset này không biểu diễn được ký tự ấy.

**Câu 3.** Cần chấp nhận UTF-8 không hợp lệ và hiển thị `U+FFFD` thay thế, làm thế nào?  
**Trả lời:** Tạo `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPLACE)` rồi dùng overload `Channels.newReader(channel, decoder, -1)`.

**Câu 4.** Đóng `Reader` do `Channels.newReader` tạo có đóng channel không?  
**Có.** Reader sở hữu việc đóng underlying channel theo contract của adapter.

**Câu 5.** Gọi `newReader` rồi đọc 10 ký tự có chắc channel mới tiêu thụ đúng 10 byte không?  
**Không.** Unicode và charset có số byte/ký tự khác nhau; adapter còn có buffer byte và có thể read-ahead.

**Câu 6.** Chỉ cần đọc toàn bộ file văn bản UTF-8 nhỏ thành `String`, có nên luôn dùng `Channels.newReader`?  
**Không cần.** `Files.readString(path, StandardCharsets.UTF_8)` thường gọn hơn. Chọn Channels khi nguồn/channel hoặc API Reader là yêu cầu thực tế.

**Câu 7.** Muốn convert ISO-8859-1 text sang UTF-8, chỉ đổi tên file hoặc chuyển `byte[]` sang newWriter có đủ không?  
**Không.** Phải decode theo ISO-8859-1 thành chars rồi encode theo UTF-8 (hoặc API transcoder tương đương).

**Câu 8.** `minBufferCap=8192` có bảo đảm Writer sẽ chỉ ghi mỗi lần đúng 8192 byte không?  
**Không.** Đó là yêu cầu/đề nghị về buffer nội bộ, implementation có thể bỏ qua, và số byte mỗi lần channel write phụ thuộc dữ liệu và thời điểm flush.

**Câu 9.** Nếu UTF-8 bytes giải mã theo ISO-8859-1 ra chuỗi `Ã©`, chế độ `REPORT` có nhất thiết báo lỗi?  
**Không.** ISO-8859-1 có thể giải mã các byte hợp lệ riêng lẻ, dù người dùng thấy văn bản sai.

**Câu 10.** Đọc text bằng Reader rồi ghi qua Writer có luôn giữ byte 100% không?  
**Không.** Decode/encode có thể đổi byte, nhất là khác charset, replacement, BOM, line ending hoặc mapping không có tính round-trip byte.

## 15. Ghi nhớ và tài liệu chính thức

**Cốt lõi:** `Channels.newReader` là adapter **channel byte → Reader ký tự** thông qua `CharsetDecoder`; `Channels.newWriter` là adapter **Writer ký tự → channel byte** thông qua `CharsetEncoder`. Nêu rõ charset, dùng chính sách lỗi thích hợp, quản lý vòng đời wrapper/channel, và tách việc chuyển mã văn bản khỏi sao chép byte nguyên trạng.

Tài liệu Java SE 21:

- `Channels` (six overloads, buffering, blocking mode, close behavior): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Channels.html
- `Charset`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html
- `CharsetDecoder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
- `CharsetEncoder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html
- `CodingErrorAction`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CodingErrorAction.html
- `StandardCharsets`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html
- `ReadableByteChannel`, `WritableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html và https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html
