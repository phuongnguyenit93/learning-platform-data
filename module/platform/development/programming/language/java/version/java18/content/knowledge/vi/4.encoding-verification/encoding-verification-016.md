# Thực hành xây dựng bộ đọc ghi văn bản UTF-8 có kiểm tra lỗi và thông báo chẩn đoán

## 1. Mục tiêu và bối cảnh

Một ứng dụng thường đọc và ghi văn bản ở nhiều nơi: tệp cấu hình, log, dữ liệu trao đổi, nội dung HTTP hoặc dữ liệu xuất từ hệ thống. Nếu văn bản được quy ước là UTF-8, chương trình cần kiểm tra byte đầu vào và ký tự đầu ra theo đúng quy tắc UTF-8. Khi dữ liệu lỗi, thông báo cần chỉ ra tệp và vị trí có vấn đề để người vận hành có thể sửa nguồn dữ liệu.

Từ **JDK 18**, UTF-8 là charset mặc định của các Java SE API dùng default charset theo JEP 400. Tuy nhiên, một tiện ích đọc/ghi dữ liệu trao đổi vẫn nên chỉ định rõ `StandardCharsets.UTF_8`. Việc này làm hợp đồng định dạng hiển thị ngay trong mã và tránh phụ thuộc vào cấu hình tương thích hoặc API có quy tắc charset riêng. Các luồng console như `System.out` và `System.err` có quy tắc charset riêng của console; không nên suy ra rằng mọi đầu ra đều dùng default charset.

Bài thực hành xây dựng một tiện ích có hai thao tác:

- Đọc tệp UTF-8 ở chế độ nghiêm ngặt, phát hiện byte sai định dạng hoặc chuỗi nhiều byte bị cắt cụt.
- Ghi chuỗi Java thành UTF-8 ở chế độ nghiêm ngặt, phát hiện surrogate không hợp lệ trước khi thay nội dung tệp đích.

Sau bài học, bạn có thể:

- Phân biệt giải mã thay thế với giải mã có kiểm tra lỗi.
- Cấu hình `CharsetDecoder` và `CharsetEncoder` bằng `CodingErrorAction.REPORT`.
- Tạo chẩn đoán có đường dẫn, byte offset hoặc vị trí ký tự UTF-16.
- Ghi qua tệp tạm để lỗi mã hóa không làm mất nội dung cũ.
- Kiểm thử round-trip, malformed input, dữ liệu bị cắt cụt và surrogate không hợp lệ.
- Chọn cách đọc toàn bộ tệp hoặc đọc streaming theo kích thước dữ liệu.

## 2. Hợp đồng UTF-8 và các loại lỗi cần phát hiện

UTF-8 mã hóa Unicode code point bằng một đến bốn byte. Một chuỗi byte hợp lệ phải tuân theo cấu trúc UTF-8, gồm byte mở đầu, byte tiếp nối và các giới hạn của từng dạng mã hóa. Không phải mọi dãy byte đều là UTF-8 hợp lệ.

Ví dụ:

| Ký tự | Byte UTF-8 |
| --- | --- |
| `A` | `41` |
| `é` | `C3 A9` |
| `€` | `E2 82 AC` |
| `😀` | `F0 9F 98 80` |

Các lỗi đọc thường gặp:

- Byte mở đầu không hợp lệ, ví dụ byte continuation đứng riêng.
- Byte tiếp nối không đúng vị trí.
- Chuỗi nhiều byte bị cắt cụt ở cuối tệp, ví dụ `E2 82` nhưng không có byte thứ ba.
- Các dạng mã hóa UTF-8 không hợp lệ như overlong encoding hoặc mã hóa surrogate.

Ở chiều ghi, Java `String` lưu văn bản bằng UTF-16 code unit. Một code point ngoài BMP được biểu diễn bằng một cặp surrogate hợp lệ. Một high surrogate không có low surrogate theo sau, hoặc một low surrogate đứng riêng, là dữ liệu UTF-16 không hợp lệ để mã hóa thành UTF-8.

Ví dụ:

~~~java
String valid = "Tiếng Việt – € – 😀";
String invalid = "broken " + (char) 0xD800;
~~~

Chuỗi đầu tiên có thể mã hóa UTF-8. Chuỗi thứ hai chứa high surrogate đơn lẻ; encoder cần phát hiện thay vì âm thầm thay bằng ký tự mặc định.

## 3. Vì sao cần REPORT thay cho REPLACE?

Các API tiện ích thường có hành vi thay thế khi gặp dữ liệu không hợp lệ. Điều này hữu ích cho ứng dụng hiển thị nội dung không quan trọng tính toàn vẹn tuyệt đối, nhưng nguy hiểm khi đọc cấu hình, dữ liệu nghiệp vụ hoặc tệp trao đổi cần được bảo toàn.

`CodingErrorAction` cung cấp ba chính sách:

| Chính sách | Hành vi | Khi phù hợp |
| --- | --- | --- |
| `REPORT` | Trả về lỗi để ứng dụng xử lý. | Cấu hình, dữ liệu nghiệp vụ, giao thức và tác vụ kiểm chứng. |
| `REPLACE` | Thay dữ liệu lỗi bằng chuỗi thay thế. | Nội dung hiển thị có thể chấp nhận mất thông tin. |
| `IGNORE` | Bỏ qua phần dữ liệu lỗi. | Chỉ khi việc mất dữ liệu đã được chấp nhận rõ ràng. |

Với bộ đọc/ghi kiểm chứng, chọn `REPORT` cho cả lỗi malformed và unmappable:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);
~~~

Mặc dù UTF-8 có thể biểu diễn mọi Unicode scalar value hợp lệ, việc đặt rõ cả hai chính sách giúp mã thể hiện ý định và nhất quán nếu sau này thay charset. Với UTF-8 decoder, lỗi thường gặp là malformed byte sequence; với UTF-8 encoder, lỗi quan trọng là chuỗi Java chứa surrogate không hợp lệ.

## 4. Thiết kế thông báo chẩn đoán

Thông báo nên trả lời được bốn câu hỏi:

1. Thao tác nào thất bại: đọc hay ghi?
2. Tệp nào có dữ liệu lỗi?
3. Vị trí lỗi được tính theo đơn vị nào?
4. Lỗi thuộc loại nào và có thể xem nguyên nhân gốc ở đâu?

Đơn vị offset phải được ghi rõ:

| Thao tác | Offset | Ý nghĩa |
| --- | --- | --- |
| Đọc UTF-8 | Byte offset, bắt đầu từ 0 | Vị trí byte đầu tiên của chuỗi byte lỗi trong tệp. |
| Ghi UTF-8 | UTF-16 char offset, bắt đầu từ 0 | Vị trí code unit đầu tiên của chuỗi Java không hợp lệ. |

`CoderResult.length()` cho biết số đơn vị đầu vào thuộc chuỗi lỗi: byte đối với decoder và ký tự đầu vào đối với encoder. Không được gọi offset ghi là “byte offset”, vì tại thời điểm mã hóa, lỗi nằm trong chuỗi UTF-16 trước khi tạo byte UTF-8.

Ví dụ thông báo:

~~~text
Cannot decode UTF-8 file 'config/app.txt' at byte offset 128 (malformed length 1)
Cannot encode UTF-8 for 'output.txt' at UTF-16 char offset 42 (malformed length 1)
~~~

Với offset byte, người vận hành có thể mở tệp bằng công cụ hex editor hoặc script để kiểm tra chính xác. Offset này không tự động là số dòng/cột; nếu cần line/column, phải phân tích phần byte hợp lệ trước lỗi hoặc bổ sung một bước dò vị trí riêng.

## 5. Xây dựng bộ đọc UTF-8 nghiêm ngặt

Với tệp nhỏ hoặc vừa, cách đơn giản để có byte offset chính xác là đọc byte bằng `Files.readAllBytes`, sau đó tự gọi decoder với `endOfInput=true`. Khi decoder báo lỗi, `ByteBuffer.position()` chỉ đến vị trí byte lỗi.

Ví dụ lớp `StrictUtf8Files`:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Objects;

public final class StrictUtf8Files {
    private StrictUtf8Files() {
    }

    public static String read(Path path) throws IOException {
        Objects.requireNonNull(path, "path");

        byte[] bytes = Files.readAllBytes(path);
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        ByteBuffer input = ByteBuffer.wrap(bytes);

        // UTF-8 tạo không quá một UTF-16 code unit trên mỗi byte đầu vào.
        // Dùng tối thiểu một ô để trường hợp tệp rỗng vẫn hợp lệ.
        CharBuffer output = CharBuffer.allocate(Math.max(1, bytes.length));

        CoderResult result = decoder.decode(input, output, true);
        if (result.isError()) {
            throw codingFailure("decode", path, "byte", input.position(), result);
        }
        if (result.isOverflow()) {
            throw new IOException("Unexpected UTF-8 decoder output overflow for " + path);
        }

        result = decoder.flush(output);
        if (result.isError()) {
            throw codingFailure("flush decoder", path, "byte", input.position(), result);
        }
        if (result.isOverflow()) {
            throw new IOException("Unexpected UTF-8 decoder flush overflow for " + path);
        }

        output.flip();
        return output.toString();
    }

    private static IOException codingFailure(
            String operation,
            Path path,
            String offsetUnit,
            int offset,
            CoderResult result) {

        try {
            result.throwException();
        } catch (CharacterCodingException cause) {
            return new IOException(
                    "Cannot " + operation + " UTF-8 file '" + path
                            + "' at " + offsetUnit + " offset " + offset
                            + " (malformed length " + result.length() + ")",
                    cause);
        }

        throw new AssertionError("Expected an error CoderResult");
    }
}
~~~

### Vì sao output buffer có kích thước bằng số byte?

Trong UTF-8 hợp lệ:

- Một byte ASCII tạo một UTF-16 code unit.
- Hai hoặc ba byte tạo một UTF-16 code unit.
- Bốn byte tạo một cặp surrogate gồm hai UTF-16 code unit.

Vì thế, số UTF-16 code unit đầu ra không vượt quá số byte đầu vào. Buffer có kích thước `max(1, bytes.length)` đủ cho kết quả hợp lệ. Nếu decoder gặp chuỗi byte sai định dạng với chính sách `REPORT`, nó trả lỗi trước khi thay dữ liệu bằng ký tự thay thế.

Cách làm này phù hợp với tệp nhỏ/vừa. `Files.readAllBytes` và output buffer đều cần bộ nhớ tỷ lệ với kích thước tệp; không dùng nguyên mẫu này cho tệp không giới hạn kích thước.

### Vì sao gọi decode với endOfInput=true?

Đây là thao tác đọc toàn bộ byte đã có. Không còn chunk nào sẽ đến sau, nên decoder phải được báo rằng input đã kết thúc. Nếu tệp kết thúc giữa một sequence UTF-8, decoder trả lỗi malformed thay vì chờ thêm byte.

Sau khi decode trả `UNDERFLOW`, gọi `flush()` để hoàn tất vòng đời decoder. Với UTF-8, flush thường không tạo thêm ký tự, nhưng vẫn là bước đúng theo hợp đồng `CharsetDecoder`.

## 6. Xây dựng bộ ghi UTF-8 nghiêm ngặt

Bộ ghi cần kiểm tra toàn bộ chuỗi Java trước khi thay tệp đích. Nếu ghi trực tiếp bằng `Files.newBufferedWriter` hoặc `OutputStreamWriter` với charset, ứng dụng không kiểm soát được chính sách thay thế theo cách tường minh như khi tự cấu hình encoder.

Cách triển khai an toàn hơn:

1. Tạo tệp tạm trong cùng thư mục với tệp đích.
2. Dùng `CharsetEncoder` có `REPORT` để mã hóa vào tệp tạm.
3. Chỉ khi mã hóa và đóng tệp tạm thành công mới chuyển tệp tạm thành tệp đích.
4. Nếu mã hóa thất bại, xóa tệp tạm; nội dung cũ của tệp đích chưa bị ghi đè.

Thêm các phương thức sau vào lớp `StrictUtf8Files`:

~~~java
    public static void write(Path target, String text) throws IOException {
        Objects.requireNonNull(target, "target");
        Objects.requireNonNull(text, "text");

        Path absolute = target.toAbsolutePath().normalize();
        if (absolute.getFileName() == null) {
            throw new IOException("Target must name a file: " + target);
        }

        Path parent = absolute.getParent();
        Files.createDirectories(parent);

        Path temporary = Files.createTempFile(
                parent, "." + absolute.getFileName() + ".", ".tmp");
        boolean committed = false;

        try {
            try (OutputStream output = Files.newOutputStream(temporary)) {
                encode(text, absolute, output);
            }

            Files.move(temporary, absolute, StandardCopyOption.REPLACE_EXISTING);

            committed = true;
        } finally {
            if (!committed) {
                Files.deleteIfExists(temporary);
            }
        }
    }

    private static void encode(
            String text,
            Path target,
            OutputStream destination) throws IOException {

        CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        CharBuffer input = CharBuffer.wrap(text);
        ByteBuffer output = ByteBuffer.allocate(8192);

        while (true) {
            CoderResult result = encoder.encode(input, output, true);
            drain(output, destination);

            if (result.isError()) {
                throw codingFailure(
                        "encode", target, "UTF-16 char",
                        input.position(), result);
            }
            if (result.isOverflow()) {
                continue;
            }
            break; // UNDERFLOW: toàn bộ input đã được mã hóa.
        }

        while (true) {
            CoderResult result = encoder.flush(output);
            drain(output, destination);

            if (result.isError()) {
                throw codingFailure(
                        "flush encoder", target, "UTF-16 char",
                        input.position(), result);
            }
            if (result.isOverflow()) {
                continue;
            }
            break;
        }
    }

    private static void drain(ByteBuffer output, OutputStream destination)
            throws IOException {

        output.flip();

        if (output.hasRemaining()) {
            byte[] bytes = new byte[output.remaining()];
            output.get(bytes);
            destination.write(bytes);
        }

        output.clear();
    }
~~~

Phương thức `codingFailure` trong phần bộ đọc dùng chung cho cả decoder và encoder. Đối với encoder, offset được ghi là UTF-16 char offset vì `CharBuffer.position()` đếm code unit Java.

### Vì sao phải mã hóa vào tệp tạm?

Giả sử chuỗi có một high surrogate đơn lẻ ở gần cuối. Nếu mở tệp đích ở chế độ truncate rồi mới mã hóa, chương trình có thể xóa nội dung cũ trước khi phát hiện lỗi. Tệp tạm giúp quá trình kiểm tra và mã hóa hoàn tất trước khi thay thế tệp đích.

Tệp tạm được tạo trong cùng thư mục để thao tác move nằm trên cùng filesystem. `REPLACE_EXISTING` yêu cầu thay tệp đích nếu nó đã tồn tại. Bước move không được bảo đảm là nguyên tử trên mọi filesystem/provider; nếu ứng dụng cần atomic replacement để chống gián đoạn giữa chừng, hãy dùng `ATOMIC_MOVE` sau khi xác minh provider hỗ trợ và kiểm tra hành vi khi đích đã tồn tại. Dù vậy, lỗi encoding hoặc lỗi ghi tệp tạm xảy ra trước bước move nên không làm truncate tệp đích.

## 7. Sử dụng bộ đọc ghi

Sau khi ghép các phương thức vào lớp `StrictUtf8Files`, có thể dùng như sau:

~~~java
import java.io.IOException;
import java.nio.file.Path;

public class TextFileJob {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("input.txt");
        Path destination = Path.of("output.txt");

        try {
            String text = StrictUtf8Files.read(source);
            StrictUtf8Files.write(destination, text);
            System.out.println("UTF-8 copy completed");
        } catch (IOException ex) {
            System.err.println("[UTF-8] " + ex.getMessage());
            throw ex;
        }
    }
}
~~~

Nếu thao tác thất bại, thông báo có đường dẫn và offset giúp xác định dữ liệu cần kiểm tra. Ví dụ:

~~~text
[UTF-8] Cannot decode UTF-8 file 'input.txt' at byte offset 15 (malformed length 1)
~~~

Không nên bắt lỗi rồi tiếp tục xử lý chuỗi rỗng hoặc chuỗi thay thế như thể dữ liệu đã hợp lệ. Hãy quyết định rõ tác vụ có thể bỏ qua tệp, yêu cầu người gửi gửi lại dữ liệu, hay dừng cả giao dịch.

## 8. Kiểm thử các trường hợp quan trọng

Một bộ đọc/ghi có kiểm tra lỗi cần kiểm thử cả dữ liệu hợp lệ và dữ liệu hỏng. Có thể viết test JUnit hoặc một chương trình kiểm tra nhỏ không cần thư viện ngoài.

Các đoạn test bên dưới giả sử phần setup đã tạo thư mục tạm dùng chung:

~~~java
Path temporaryDirectory = Files.createTempDirectory("strict-utf8-test-");
~~~

Trong JUnit, có thể thay biến này bằng thư mục được cung cấp qua `@TempDir`.

### 8.1. Round-trip với văn bản đa ngôn ngữ

~~~java
String expected = "Tiếng Việt – café – € – 😀";
Path file = temporaryDirectory.resolve("valid.txt");

StrictUtf8Files.write(file, expected);
String actual = StrictUtf8Files.read(file);

if (!expected.equals(actual)) {
    throw new AssertionError("UTF-8 round-trip changed the text");
}
~~~

Test này kiểm tra dấu tiếng Việt, ký tự Latin mở rộng, ký hiệu tiền tệ và code point ngoài BMP được biểu diễn bằng surrogate pair.

### 8.2. Byte UTF-8 bị cắt cụt ở EOF

Ký tự `€` cần ba byte `E2 82 AC`. Tạo tệp chỉ có hai byte đầu:

~~~java
Path broken = temporaryDirectory.resolve("truncated.txt");
Files.write(broken, new byte[] {
        (byte) 0xE2,
        (byte) 0x82
});

try {
    StrictUtf8Files.read(broken);
    throw new AssertionError("Expected malformed UTF-8");
} catch (IOException ex) {
    if (!ex.getMessage().contains("byte offset 0")) {
        throw new AssertionError("Missing byte offset diagnostic", ex);
    }
}
~~~

Decoder nhận `endOfInput=true` nên không chờ byte thứ ba. Với `REPORT`, nó trả lỗi malformed tại byte offset 0.

### 8.3. Byte tiếp nối không hợp lệ

Một byte continuation không thể đứng sau byte mở đầu tùy ý. Ví dụ `E2 28 A1` không phải sequence UTF-8 hợp lệ:

~~~java
Path invalid = temporaryDirectory.resolve("invalid-sequence.txt");
Files.write(invalid, new byte[] {
        (byte) 0xE2,
        (byte) 0x28,
        (byte) 0xA1
});

try {
    StrictUtf8Files.read(invalid);
    throw new AssertionError("Expected malformed UTF-8");
} catch (IOException ex) {
    System.err.println(ex.getMessage());
}
~~~

Thông báo cần giữ byte offset và độ dài chuỗi lỗi từ `CoderResult.length()`. Không hard-code rằng mọi lỗi luôn có độ dài một byte; độ dài phụ thuộc sequence mà decoder nhận diện là malformed.

### 8.4. Chuỗi Java có surrogate không hợp lệ

Tạo high surrogate đơn lẻ:

~~~java
Path target = temporaryDirectory.resolve("existing.txt");
Files.writeString(target, "old content", StandardCharsets.UTF_8);

String malformed = "new content " + (char) 0xD800;

try {
    StrictUtf8Files.write(target, malformed);
    throw new AssertionError("Expected malformed UTF-16 input");
} catch (IOException expectedFailure) {
    String remaining = Files.readString(target, StandardCharsets.UTF_8);
    if (!remaining.equals("old content")) {
        throw new AssertionError("Existing file was changed after encode failure");
    }
}
~~~

Encoder có `REPORT` nên từ chối chuỗi malformed. Vì việc mã hóa diễn ra trên tệp tạm, tệp đích vẫn chứa `old content`.

### 8.5. Ma trận kiểm thử tối thiểu

| Trường hợp | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| ASCII | `Hello` | Đọc/ghi thành công. |
| Tiếng Việt | `Xin chào` | Round-trip không đổi. |
| Ký tự 3 byte | `€` | Round-trip không đổi. |
| Code point 4 byte | `😀` | Round-trip không đổi. |
| Byte mở đầu sai | Byte UTF-8 không hợp lệ | Báo lỗi và byte offset. |
| Sequence bị cắt cụt | `E2 82` tại EOF | Báo malformed input. |
| Sequence sai continuation | `E2 28 A1` | Báo malformed input. |
| High surrogate đơn lẻ | `(char) 0xD800` | Encoder từ chối và báo char offset. |
| Low surrogate đơn lẻ | `(char) 0xDC00` | Encoder từ chối và báo char offset. |
| Tệp đích đã có nội dung | Ghi chuỗi malformed | Tệp đích cũ vẫn còn nguyên sau lỗi encode. |

## 9. Chẩn đoán theo dòng và cột

Byte offset là chẩn đoán chính xác ở cấp tệp, nhưng người dùng thường muốn biết dòng và cột. Có thể mở rộng theo hai cách:

- Khi đọc tệp nhỏ/vừa, sau khi decoder xác định byte offset lỗi, quét phần byte hợp lệ đứng trước offset để đếm newline và vị trí trong dòng. Cần thống nhất cách đếm newline là LF hay CRLF và cách tính cột theo byte, code point hay UTF-16 code unit.
- Với tệp lớn, đọc streaming và duy trì bộ đếm byte đã tiêu thụ cùng trạng thái dòng/cột. Cần tính đến việc một ký tự UTF-8 có thể chia giữa các lần đọc; không tăng cột khi mới nhận một phần sequence.

Không nên lấy byte offset làm cột ký tự. Với văn bản có ký tự nhiều byte, byte offset và cột code point khác nhau. Ngoài ra, tab, CRLF và ký tự ngoài BMP làm định nghĩa cột hiển thị khác với số UTF-16 code unit.

Thông báo thực tế có thể bao gồm cả hai nếu đã tính đúng:

~~~text
Invalid UTF-8 in config.txt at byte offset 128 (line 7, code-point column 12)
~~~

Nếu chưa có bước tính line/column đáng tin cậy, chỉ báo byte offset chính xác còn tốt hơn một dòng/cột phỏng đoán.

## 10. Khi tệp lớn: chuyển sang streaming

`Files.readAllBytes` dễ xây dựng và cho phép lấy offset lỗi trực tiếp từ `ByteBuffer.position()`, nhưng bộ nhớ tăng theo kích thước tệp. Với log lớn hoặc tệp nhiều GB, dùng `InputStreamReader` với decoder strict để xử lý từng phần:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new BufferedReader(
        new InputStreamReader(Files.newInputStream(path), decoder))) {

    char[] chars = new char[8192];
    int count;

    while ((count = reader.read(chars)) != -1) {
        process(chars, 0, count);
    }
}
~~~

`InputStreamReader` quản lý việc gọi decoder khi dữ liệu đến theo từng khối và báo EOF. Khi decoder dùng `REPORT`, sequence sai định dạng sẽ được ném thành lỗi mã hóa thay vì tự thay thế. Cách này giới hạn bộ nhớ theo buffer và phần dữ liệu ứng dụng giữ lại.

Đoạn code trên cần các import `java.io.Reader`, `java.io.BufferedReader`, `java.io.InputStreamReader`, cùng `java.nio.file.Files` và `java.nio.file.Path`; `process(char[], int, int)` là hàm xử lý từng chunk do ứng dụng cung cấp.

Đổi lại, `Reader` không cung cấp byte offset lỗi trực tiếp cho bên gọi. Nếu yêu cầu chẩn đoán bắt buộc có byte offset chính xác trên tệp rất lớn, cần tự quản lý `ByteBuffer` và `CharsetDecoder` theo vòng lặp tăng dần, đồng thời cộng dồn số byte đã tiêu thụ. Bài giải mã từng phần đã trình bày cơ chế `UNDERFLOW`, `OVERFLOW`, `compact()`, EOF và `flush()`; có thể dùng cùng cơ chế đó để xây bộ đọc streaming có offset.

Với ghi streaming, giữ cùng nguyên tắc: encoder dùng `REPORT`, ghi ra tệp tạm, xử lý `OVERFLOW` bằng cách xả byte đã mã hóa, gọi `flush()` sau `encode(..., true)` và chỉ thay tệp đích khi hoàn tất.

## 11. BOM và quy ước tệp

UTF-8 có thể bắt đầu bằng byte order mark (BOM) `EF BB BF`. UTF-8 không cần BOM để xác định byte order. Decoder `StandardCharsets.UTF_8` sẽ giải mã BOM thành ký tự `U+FEFF` ở đầu chuỗi; nó không tự động xóa ký tự này.

Hãy xác định quy ước của định dạng tệp:

- Nếu định dạng cho phép BOM và ứng dụng muốn giữ nguyên nội dung, giữ `U+FEFF`.
- Nếu định dạng yêu cầu bỏ BOM ở đầu tệp, kiểm tra và bỏ đúng một `U+FEFF` đầu chuỗi sau khi giải mã.
- Không xóa mọi ký tự `U+FEFF` ở giữa văn bản vì chúng có thể là nội dung có ý nghĩa.

Khi ghi bằng `StandardCharsets.UTF_8.newEncoder()`, encoder UTF-8 tiêu chuẩn không tự thêm BOM. Nếu định dạng yêu cầu BOM, ứng dụng phải ghi byte BOM theo quy ước rõ ràng và kiểm thử tương ứng.

## 12. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng charset mặc định mà không nêu hợp đồng. | Hành vi phụ thuộc API hoặc chế độ tương thích. | Chỉ định `StandardCharsets.UTF_8`. |
| Dùng decoder/encoder với `REPLACE` cho dữ liệu cần toàn vẹn. | Byte hoặc ký tự lỗi bị thay âm thầm. | Dùng `REPORT`, phát sinh chẩn đoán. |
| Ghi trực tiếp vào tệp đích trước khi kiểm tra chuỗi. | Tệp cũ có thể bị truncate trước khi phát hiện surrogate lỗi. | Mã hóa vào tệp tạm rồi mới move. |
| Ghi lỗi encoder offset theo byte. | Đơn vị vị trí sai. | Ghi rõ UTF-16 char offset. |
| Giả định `CoderResult.length()` luôn bằng 1. | Chẩn đoán sai độ dài sequence lỗi. | Dùng đúng giá trị từ kết quả. |
| Gọi `flush()` trước khi `encode/decode(..., true)` hoàn tất. | Vi phạm vòng đời coder. | Kết thúc input, xử lý UNDERFLOW rồi mới flush. |
| Đọc tệp rất lớn bằng `readAllBytes()`. | Tăng bộ nhớ theo toàn bộ tệp. | Dùng streaming reader/decoder. |
| Xóa BOM ở mọi vị trí trong văn bản. | Làm mất nội dung hợp lệ. | Chỉ xử lý BOM đầu tệp theo hợp đồng định dạng. |
| Coi UTF-8 hợp lệ đồng nghĩa dữ liệu nghiệp vụ hợp lệ. | Có thể bỏ qua lỗi cấu trúc, schema hoặc checksum. | Kiểm tra charset trước, rồi xác thực định dạng và quy tắc nghiệp vụ. |

## 13. Quy trình triển khai trong dự án

1. **Xác định hợp đồng tệp:** encoding UTF-8, có/không có BOM, newline và định dạng nội dung.
2. **Chọn API tường minh:** dùng `StandardCharsets.UTF_8` thay vì charset mặc định.
3. **Chọn chính sách lỗi:** dùng `REPORT` cho dữ liệu cần toàn vẹn.
4. **Xây bộ đọc:** lấy byte, giải mã strict và báo byte offset khi malformed.
5. **Xây bộ ghi:** mã hóa strict, báo UTF-16 char offset và ghi qua tệp tạm.
6. **Xác định giới hạn kích thước:** dùng read-all cho tệp nhỏ/vừa, streaming cho dữ liệu lớn.
7. **Kiểm thử biên:** byte continuation sai, sequence bị cắt cụt, ký tự 4 byte, surrogate đơn lẻ và BOM.
8. **Kiểm tra chẩn đoán:** xác nhận path, offset, đơn vị offset và cause.
9. **Tích hợp CI:** chạy test reader/writer khi thay đổi API xử lý văn bản hoặc hợp đồng tệp.
10. **Kiểm tra môi trường:** chạy trên JDK mục tiêu và filesystem triển khai, đặc biệt nếu phụ thuộc hành vi thay thế hoặc atomic move.

## 14. Bài tập thực hành

### Bài tập 1: Tìm byte lỗi

Tạo tệp chứa byte `41 E2 82` rồi EOF. Dùng bộ đọc strict, xác định byte offset và độ dài malformed sequence. Giải thích vì sao hai byte cuối không phải lỗi khi còn chunk tiếp theo, nhưng trở thành lỗi khi đã EOF.

### Bài tập 2: So sánh REPORT và REPLACE

Tạo cùng một tệp byte lỗi. Đọc bằng decoder `REPORT` và `REPLACE`. So sánh exception, chuỗi kết quả và khả năng phát hiện dữ liệu bị hỏng. Chọn chính sách cho tệp cấu hình và giải thích.

### Bài tập 3: Kiểm tra surrogate

Tạo chuỗi chứa high surrogate đơn lẻ và low surrogate đơn lẻ. Dùng encoder strict để ghi. Xác định UTF-16 char offset của lỗi và giải thích vì sao không thể tạo UTF-8 hợp lệ từ các code unit đó.

### Bài tập 4: Bảo vệ tệp đích

Tạo tệp đích có nội dung `original`. Gọi writer với chuỗi malformed. Xác nhận thao tác thất bại và tệp đích vẫn giữ nguyên. Sau đó ghi chuỗi hợp lệ và xác nhận tệp được thay thế.

### Bài tập 5: Mở rộng line/column

Sau khi có byte offset, viết hàm quét phần byte hợp lệ đứng trước lỗi để tính line và code-point column. Kiểm thử với LF, CRLF, tab, tiếng Việt và emoji. Ghi rõ quy ước cột mà chương trình sử dụng.

### Bài tập 6: Streaming cho tệp lớn

Thay bộ đọc `readAllBytes()` bằng `InputStreamReader` dùng decoder `REPORT`. Xử lý từng mảng char và so sánh mức sử dụng bộ nhớ với cách đọc toàn bộ. Nêu thông tin chẩn đoán nào còn có sẵn và thông tin nào cần tự quản lý.

**Tự kiểm:** reader từ chối malformed UTF-8; writer từ chối surrogate sai; chẩn đoán có đúng đơn vị offset; tệp đích không bị thay khi encode lỗi; round-trip giữ nguyên văn bản hợp lệ; streaming có giới hạn bộ nhớ phù hợp.

## 15. Ghi nhớ

- **JDK 18 đặt UTF-8 làm default charset cho Java SE APIs**, nhưng hợp đồng tệp và giao thức nên chỉ định rõ `StandardCharsets.UTF_8`.
- **Dùng `CharsetDecoder` và `CharsetEncoder` với `CodingErrorAction.REPORT`** khi cần phát hiện dữ liệu hỏng.
- **Byte offset và UTF-16 char offset là hai đơn vị khác nhau.** Thông báo phải ghi rõ đơn vị.
- **`CoderResult.length()` cho biết độ dài sequence lỗi.** Không giả định lỗi luôn dài một byte hoặc một char.
- **Chỉ thay tệp đích sau khi encoder hoàn tất.** Tệp tạm giúp lỗi encoding không làm truncate nội dung cũ.
- **`Files.readAllBytes()` phù hợp với tệp nhỏ/vừa.** Tệp lớn cần streaming để giới hạn bộ nhớ.
- **BOM là quy ước của định dạng tệp.** UTF-8 decoder giữ BOM thành `U+FEFF`; encoder chuẩn không tự thêm BOM.
- **Kiểm thử cả dữ liệu hợp lệ và lỗi biên.** Round-trip, truncated sequence, continuation sai và surrogate đơn lẻ đều cần được kiểm tra.

## Tài liệu chính thống

- [Oracle – Java SE 26 API: CharsetDecoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Oracle – Java SE 26 API: CharsetEncoder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html).
- [Oracle – Java SE 26 API: CoderResult](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CoderResult.html).
- [Oracle – Java SE 26 API: CodingErrorAction](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CodingErrorAction.html).
- [Oracle – Java SE 26 API: Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html).
- [Oracle – JDK 18 Release Notes, JEP 400: UTF-8 by Default](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html).
- [OpenJDK – JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).

