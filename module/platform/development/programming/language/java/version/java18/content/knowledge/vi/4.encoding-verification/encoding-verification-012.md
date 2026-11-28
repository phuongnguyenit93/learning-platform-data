# Chuyển đổi tệp đầu vào có charset được xác định rõ sang UTF-8 và xác minh byte đầu ra

## 1. Mục tiêu: chuyển mã theo hợp đồng của tệp nguồn

Trong module **JAVA_VERSION_JAVA18**, Java 18 đưa UTF-8 thành charset mặc định của nhiều API Java theo [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400). Tuy nhiên, khi chuyển một tệp cũ sang UTF-8, charset mặc định của JVM không cho biết byte trong tệp nguồn đang được mã hóa như thế nào.

Bài thuộc chương **Kiểm chứng mã hóa**. Quy trình chuyển đổi cần xác định rõ:

1. Charset của tệp nguồn, dựa trên đặc tả định dạng, metadata hoặc hợp đồng của hệ thống tạo tệp.
2. Cách giải mã byte nguồn thành Unicode, có từ chối byte không hợp lệ hay không.
3. Cách mã hóa String thành UTF-8, có cho phép thay thế ký tự lỗi hay không.
4. Byte thực tế sau khi ghi, có đúng với nội dung và hợp đồng UTF-8 mong đợi hay không.

Ví dụ xuyên suốt bài dùng tệp legacy Windows-1252 chứa nội dung `café €`. Byte nguồn là `63 61 66 E9 20 80`; sau khi giải mã đúng và mã hóa UTF-8, byte đích phải là `63 61 66 C3 A9 20 E2 82 AC`.

Mục tiêu không chỉ là tạo ra một tệp mà decoder UTF-8 chấp nhận. Ta còn phải chứng minh văn bản sau chuyển đổi giữ đúng nội dung ban đầu, byte đầu ra đúng chuẩn và không có ký tự bị thay thế âm thầm.

## 2. Xác định charset nguồn trước khi đọc

Một tệp văn bản thông thường lưu byte. Tên file, phần mở rộng và hệ điều hành tạo file không đủ để kết luận charset. Hãy tìm bằng chứng từ:

- Đặc tả định dạng hoặc tài liệu của hệ thống xuất dữ liệu.
- Header, metadata hoặc khai báo charset đi kèm payload.
- Cấu hình tích hợp giữa hệ thống phát và hệ thống nhận.
- BOM nếu định dạng quy định có sử dụng và cách diễn giải BOM đã được xác định.

Không suy charset chỉ từ vài byte hoặc từ việc một editor đang hiển thị đúng. Nhiều charset có thể giải mã cùng một dãy byte nhưng tạo ra văn bản khác nhau. Ví dụ byte `E9` biểu diễn `é` trong Windows-1252, nhưng không phải một chuỗi UTF-8 hợp lệ đứng độc lập.

### 2.1. Charset nguồn phải được truyền tường minh

Với Java, có thể lấy charset từ `StandardCharsets` nếu đó là charset chuẩn:

```java
Charset sourceCharset = StandardCharsets.ISO_8859_1;
```

Với charset được hỗ trợ qua tên chuẩn/alias của runtime, dùng `Charset.forName`:

```java
Charset sourceCharset = Charset.forName("windows-1252");
```

`Charset.forName` có thể ném `IllegalCharsetNameException` nếu tên không hợp lệ hoặc `UnsupportedCharsetException` nếu charset không được runtime hỗ trợ. Hãy xác thực tên charset ở cấu hình ứng dụng lúc khởi động thay vì để một tên tùy ý đi sâu vào quy trình chuyển đổi.

Không dùng `Charset.defaultCharset()` để đoán charset của file legacy. JEP 400 làm UTF-8 trở thành default của nhiều API Java trên JDK 18+, nhưng không sửa byte cũ, không thêm metadata vào file và không chuyển định dạng của hệ thống bên ngoài.

### 2.2. Phân biệt charset với BOM và newline

BOM là dấu hiệu ở đầu một số định dạng, không phải metadata phổ quát cho mọi file. Nếu nguồn có BOM, hãy quyết định theo hợp đồng: giữ U+FEFF như nội dung, bỏ đúng BOM ở đầu file, hay từ chối vì định dạng không cho phép. Không xóa mọi U+FEFF ở giữa văn bản.

Newline cũng là nội dung: `LF` là U+000A, `CRLF` là U+000D U+000A. Quy trình chuyển charset thuần túy nên giữ nguyên các ký tự này. Nếu cần chuẩn hóa newline, đó là một phép biến đổi nội dung riêng và phải được yêu cầu rõ ràng.

## 3. Mô hình chuyển đổi: byte nguồn → Unicode → byte UTF-8

Quá trình chuyển mã có hai bước độc lập:

```text
byte nguồn
    |
    | decode bằng charset nguồn đã xác định
    v
String / Unicode
    |
    | encode bằng StandardCharsets.UTF_8
    v
byte UTF-8
    |
    | ghi file và đọc lại
    v
xác minh byte, nội dung và hợp đồng đích
```

Không nên coi chuyển đổi charset là thao tác thay byte theo bảng tra cứu tùy tiện. Decoder phải diễn giải byte nguồn theo đúng charset; encoder sau đó mới tạo byte UTF-8 từ các ký tự Unicode đã giải mã.

Hai lỗi có thể xuất hiện ở hai ranh giới:

- **Sai khi đọc:** dùng charset nguồn không đúng, nên String đã sai ngay sau decode. Mã hóa String đó thành UTF-8 chỉ tạo ra byte UTF-8 hợp lệ cho nội dung sai.
- **Sai khi ghi:** String đúng nhưng encoder/Writer dùng charset khác UTF-8 hoặc thay ký tự không biểu diễn được.

Để tránh mất dữ liệu, hãy cấu hình decoder và encoder với `CodingErrorAction.REPORT` khi hợp đồng yêu cầu chuyển đổi chính xác. `REPLACE` có thể thay byte/ký tự lỗi bằng giá trị thay thế; `IGNORE` có thể bỏ phần lỗi. Cả hai đều có thể làm mất thông tin.

## 4. Giải mã nghiêm ngặt và mã hóa UTF-8 nghiêm ngặt

### 4.1. Decoder với REPORT

Dùng `CharsetDecoder` khi cần từ chối byte không hợp lệ theo charset nguồn:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;

static String decodeStrict(byte[] bytes, Charset sourceCharset)
        throws CharacterCodingException {
    return sourceCharset.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

`decode(ByteBuffer)` xử lý toàn bộ buffer như input đã kết thúc. Nếu byte cuối là một chuỗi chưa hoàn chỉnh, hoặc có malformed sequence, decoder ở chế độ `REPORT` ném `CharacterCodingException` (thường là `MalformedInputException` hoặc `UnmappableCharacterException` tùy charset và tình huống).

Đây là phép decode cho tệp đã đọc đầy đủ. Với stream chia chunk, cần dùng API streaming và chỉ xác nhận EOF khi nguồn thực sự kết thúc; không kết luận byte cuối chunk là lỗi nếu dữ liệu còn tiếp.

### 4.2. Encoder với REPORT

Sau khi có String đúng, mã hóa bằng UTF-8 tường minh:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static byte[] encodeUtf8Strict(String text)
        throws CharacterCodingException {
    ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(text));

    byte[] result = new byte[encoded.remaining()];
    encoded.get(result);
    return result;
}
```

UTF-8 biểu diễn được mọi Unicode scalar value. Encoder vẫn cần `REPORT` để phát hiện `String` Java có surrogate không ghép cặp, thay vì âm thầm thay bằng ký tự hoặc byte thay thế.

### 4.3. Vì sao không dùng constructor String hoặc getBytes() mặc định?

`new String(bytes, charset)` và `text.getBytes(charset)` là API tiện dụng; khi gặp dữ liệu lỗi, chúng có thể thay thế phần không hợp lệ theo quy tắc của API/charset. Nếu cần xác thực dữ liệu nguồn và bảo đảm không mất ký tự, hãy dùng decoder/encoder có chính sách `REPORT`.

Tuyệt đối không dùng `new String(sourceBytes)` hay `text.getBytes()` để thực hiện một hợp đồng chuyển mã xác định. Các overload đó dựa vào default charset của JVM; default UTF-8 từ Java 18 không có nghĩa file nguồn chắc chắn là UTF-8.

## 5. Ví dụ hoàn chỉnh: chuyển Windows-1252 sang UTF-8

Tệp nguồn ví dụ chứa chuỗi `café €`. Theo hợp đồng Windows-1252, byte là:

```text
63 61 66 E9 20 80
```

UTF-8 đầu ra mong đợi:

```text
63 61 66 C3 A9 20 E2 82 AC
```

Lớp dưới đây nhận ba tham số: đường dẫn tệp nguồn, đường dẫn tệp đích và tên charset nguồn. Tệp đích phải khác tệp nguồn. Chương trình đọc byte, giải mã strict, mã hóa UTF-8 strict, ghi file, đọc lại byte và xác minh.

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Locale;

public final class ConvertFileToUtf8 {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: ConvertFileToUtf8 <input> <output> <source-charset>");
        }

        Path input = Path.of(args[0]).toAbsolutePath().normalize();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();

        if (input.equals(output)) {
            throw new IllegalArgumentException(
                    "Input và output phải là hai file riêng biệt");
        }

        Charset sourceCharset = Charset.forName(args[2]);
        byte[] sourceBytes = Files.readAllBytes(input);

        String text = decodeStrict(sourceBytes, sourceCharset);
        byte[] utf8Bytes = encodeUtf8Strict(text);

        // Files.write tạo hoặc ghi đè file đích; không sửa file nguồn.
        Files.write(output, utf8Bytes);

        // Đọc lại byte trên đĩa để xác minh nội dung đã ghi.
        byte[] actualBytes = Files.readAllBytes(output);
        if (!Arrays.equals(utf8Bytes, actualBytes)) {
            throw new IllegalStateException(
                    "Byte đầu ra khác byte đã mã hóa");
        }

        String verifiedText = decodeStrict(
                actualBytes, StandardCharsets.UTF_8);
        if (!text.equals(verifiedText)) {
            throw new IllegalStateException(
                    "Nội dung sau khi đọc lại không khớp");
        }

        writeAscii("SOURCE_CHARSET=" + sourceCharset.name());
        writeAscii("OUTPUT_CHARSET=UTF-8");
        writeAscii("SOURCE_BYTES=" + hex(sourceBytes));
        writeAscii("OUTPUT_BYTES=" + hex(actualBytes));
        writeAscii("OUTPUT_UTF8_VALID=true");
        writeAscii("TEXT_ROUND_TRIP_MATCH=true");
        writeAscii("CODE_POINTS=" + codePoints(verifiedText));
    }

    private static String decodeStrict(byte[] bytes, Charset charset)
            throws CharacterCodingException {
        return charset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static byte[] encodeUtf8Strict(String text)
            throws CharacterCodingException {
        ByteBuffer encoded = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .encode(CharBuffer.wrap(text));

        byte[] result = new byte[encoded.remaining()];
        encoded.get(result);
        return result;
    }

    private static String hex(byte[] bytes) {
        return HexFormat.ofDelimiter(" ").withUpperCase().formatHex(bytes);
    }

    private static String codePoints(String value) {
        StringBuilder result = new StringBuilder();
        value.codePoints().forEach(cp -> {
            if (result.length() > 0) result.append(' ');
            result.append(String.format(Locale.ROOT, "U+%04X", cp));
        });
        return result.toString();
    }

    private static void writeAscii(String value) throws Exception {
        System.out.write(value.getBytes(StandardCharsets.US_ASCII));
        System.out.write('\n');
        System.out.flush();
    }
}
```

Biên dịch trên JDK 18 hoặc mới hơn:

```bash
javac -encoding UTF-8 ConvertFileToUtf8.java
```

Chạy với một tệp đã được xác định chắc chắn là Windows-1252:

```bash
java ConvertFileToUtf8 legacy.txt converted.txt windows-1252
```

Nếu `legacy.txt` chứa đúng byte mẫu `63 61 66 E9 20 80`, kết quả quan trọng phải là:

| Trường | Kết quả |
| --- | --- |
| `SOURCE_CHARSET` | `windows-1252` |
| `OUTPUT_CHARSET` | `UTF-8` |
| `SOURCE_BYTES` | `63 61 66 E9 20 80` |
| `OUTPUT_BYTES` | `63 61 66 C3 A9 20 E2 82 AC` |
| `OUTPUT_UTF8_VALID` | `true` |
| `TEXT_ROUND_TRIP_MATCH` | `true` |
| `CODE_POINTS` | `U+0063 U+0061 U+0066 U+00E9 U+0020 U+20AC` |

Báo cáo chỉ chứa ASCII để không nhầm lỗi hiển thị terminal với lỗi byte trong file.

## 6. Xác minh độc lập byte UTF-8 đầu ra

Một phép kiểm tra tốt cần nhiều bằng chứng. Không nên chỉ gọi decoder UTF-8 rồi kết luận file đúng, vì một dãy byte có thể hợp lệ theo UTF-8 nhưng vẫn mang nội dung sai do charset nguồn đã chọn nhầm.

### 6.1. So sánh với vector byte chuẩn khi có dữ liệu mẫu

Với fixture Windows-1252 `café €`, ta biết độc lập cả byte nguồn, nội dung mong đợi và byte UTF-8 đích:

| Lớp kiểm tra | Giá trị chuẩn |
| --- | --- |
| Byte nguồn | `63 61 66 E9 20 80` |
| Charset nguồn | `windows-1252` |
| Nội dung Unicode | `U+0063 U+0061 U+0066 U+00E9 U+0020 U+20AC` |
| Byte UTF-8 đích | `63 61 66 C3 A9 20 E2 82 AC` |

Có thể thêm kiểm tra fixture độc lập vào chương trình:

```java
private static void verifyKnownFixture(
        byte[] sourceBytes, String decodedText, byte[] utf8Bytes) {
    byte[] expectedSource = {
            0x63, 0x61, 0x66, (byte) 0xE9, 0x20, (byte) 0x80
    };
    String expectedText = "caf\u00E9 \u20AC";
    byte[] expectedUtf8 = {
            0x63, 0x61, 0x66, (byte) 0xC3, (byte) 0xA9,
            0x20, (byte) 0xE2, (byte) 0x82, (byte) 0xAC
    };

    if (Arrays.equals(sourceBytes, expectedSource)) {
        if (!expectedText.equals(decodedText)
                || !Arrays.equals(expectedUtf8, utf8Bytes)) {
            throw new AssertionError(
                    "Fixture Windows-1252 không chuyển thành UTF-8 đúng");
        }
    }
}
```

Gọi helper sau khi decode và encode trong bài test. Đây là kiểm tra độc lập với phép round-trip do chương trình tự tạo; nó phát hiện trường hợp chọn nhầm charset nhưng decoder vẫn giải mã thành công.

### 6.2. Round-trip có ích nhưng không đủ

Sau khi ghi file, chương trình đọc lại bằng UTF-8 strict và so sánh với String trước khi ghi. Điều này xác nhận:

- Byte trên đĩa đúng với byte mà encoder đã tạo.
- Byte đầu ra là UTF-8 hợp lệ.
- Nội dung Unicode sau khi đọc lại giống String trước khi ghi.

Tuy nhiên, nếu ngay từ đầu byte nguồn đã được giải mã bằng charset sai nhưng vẫn hợp lệ, phép round-trip vẫn có thể thành công. Ví dụ byte `80` được diễn giải thành U+20AC trong Windows-1252, nhưng thành U+0080 trong ISO-8859-1. Cả hai phép giải mã đều có thể thành công; chỉ hợp đồng nguồn hoặc nội dung chuẩn mới xác định cách hiểu đúng.

Vì vậy, khi có golden file, checksum, record count hoặc dữ liệu mẫu đã biết, hãy kiểm tra chúng độc lập. Đừng coi `TEXT_ROUND_TRIP_MATCH=true` là bằng chứng charset nguồn đã được chọn đúng.

### 6.3. Kiểm tra code point thay vì chỉ nhìn terminal

In byte hex và code point giúp tách nội dung trong JVM khỏi cách terminal dựng glyph. Với chuỗi `café €`, code point đúng phải là:

```text
U+0063 U+0061 U+0066 U+00E9 U+0020 U+20AC
```

Nếu terminal hiển thị sai nhưng code point và byte file đều đúng, kiểm tra charset của terminal và font. Nếu code point sai, quay lại kiểm tra charset nguồn trước khi sửa cách hiển thị.

## 7. BOM, newline và Unicode normalization trong chuyển đổi

### 7.1. Chính sách BOM đầu vào

UTF-8 BOM có byte `EF BB BF`. Decoder UTF-8 của Java giải mã dãy này thành U+FEFF; không nên giả định API tự bỏ BOM. Nếu định dạng nguồn dùng BOM như dấu nhận diện và hợp đồng yêu cầu bỏ dấu, chỉ bỏ đúng BOM ở đầu tệp:

```java
static byte[] stripLeadingUtf8Bom(byte[] bytes) {
    if (bytes.length >= 3
            && (bytes[0] & 0xFF) == 0xEF
            && (bytes[1] & 0xFF) == 0xBB
            && (bytes[2] & 0xFF) == 0xBF) {
        return Arrays.copyOfRange(bytes, 3, bytes.length);
    }
    return bytes;
}
```

Chỉ gọi helper này khi charset nguồn là UTF-8 và định dạng quy định BOM là marker. Nếu U+FEFF là nội dung thật hoặc định dạng yêu cầu bảo toàn byte, không tự ý bỏ nó. Không áp dụng helper này lên file Windows-1252 hay charset khác.

### 7.2. Chính sách BOM đầu ra

`StandardCharsets.UTF_8` encoder tạo UTF-8 không BOM. Đây là lựa chọn phổ biến cho dữ liệu UTF-8, nhưng một định dạng có thể yêu cầu BOM vì tương thích với consumer cụ thể. Nếu hợp đồng đích yêu cầu BOM, thêm đúng ba byte `EF BB BF` ở đầu output một cách tường minh; nếu không yêu cầu, không tự thêm.

BOM là quy tắc định dạng, không phải điều kiện để byte UTF-8 hợp lệ. Khi kiểm tra output, xác nhận cả nội dung và chính sách BOM đã chọn.

### 7.3. Giữ nguyên newline và nội dung

Nếu mục tiêu chỉ là đổi charset, không dùng `BufferedReader.readLine()` rồi ghép lại bằng `System.lineSeparator()`. Cách đó có thể biến CRLF thành LF hoặc ngược lại. Chuyển byte thành String rồi mã hóa String giữ nguyên các ký tự CR và LF nếu chương trình không chủ động chỉnh sửa chúng.

Tương tự, không gọi `trim()`, thay tab, xóa khoảng trắng hay chuẩn hóa Unicode trong bước transcoding. Hai chuỗi có thể hiển thị giống nhau nhưng khác code point, ví dụ ký tự dựng sẵn U+00E9 và chuỗi U+0065 U+0301. Unicode normalization như NFC/NFD là một phép biến đổi riêng; chỉ áp dụng nếu hợp đồng dữ liệu yêu cầu.

## 8. Chuyển tệp lớn theo luồng và giữ tệp đích an toàn

Ví dụ `Files.readAllBytes` phù hợp với file nhỏ hoặc vừa. Với file lớn, đọc toàn bộ byte và giữ toàn bộ String trong heap có thể tốn bộ nhớ. Dùng Reader/Writer streaming với decoder và encoder được cấu hình `REPORT`.

Một cách triển khai là ghi vào file tạm cùng thư mục, chỉ thay file đích sau khi toàn bộ quá trình đọc, decode và encode thành công:

```java
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.Charset;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

static void convertLargeFile(Path input, Path output, Charset sourceCharset)
        throws Exception {
    Path source = input.toAbsolutePath().normalize();
    Path target = output.toAbsolutePath().normalize();

    if (source.equals(target)) {
        throw new IllegalArgumentException("Input và output phải khác nhau");
    }

    Path parent = target.getParent();
    Files.createDirectories(parent);
    Path temporary = Files.createTempFile(parent, "utf8-convert-", ".tmp");
    boolean completed = false;

    try {
        var decoder = sourceCharset.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        var encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try (Reader reader = new InputStreamReader(
                    Files.newInputStream(source), decoder);
             Writer writer = new OutputStreamWriter(
                    Files.newOutputStream(temporary), encoder)) {
            char[] buffer = new char[8192];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                writer.write(buffer, 0, count);
            }
        }

        // Chỉ công bố file mới sau khi stream đóng thành công.
        Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
        completed = true;
    } finally {
        if (!completed) {
            Files.deleteIfExists(temporary);
        }
    }
}
```

Decoder và encoder được giữ xuyên suốt stream. `InputStreamReader` xử lý byte đầu vào theo decoder đã cấu hình; `OutputStreamWriter` ghi theo encoder UTF-8. Khi byte nguồn malformed, lỗi xuất hiện trong lúc đọc và file tạm bị xóa; file đích cũ vẫn còn nguyên.

File tạm được tạo trong cùng thư mục với file đích để thao tác move không phải chuyển giữa hai filesystem. `Files.move(..., REPLACE_EXISTING)` thay thế file đích sau khi conversion thành công; nếu ứng dụng cần bảo đảm atomicity theo hợp đồng lưu trữ, hãy yêu cầu `ATOMIC_MOVE`, xử lý `AtomicMoveNotSupportedException` và kiểm tra ngữ nghĩa thay thế file trên filesystem triển khai.

Đoạn streaming giữ nguyên ký tự newline và không đọc từng dòng. Nếu cần BOM, hãy xử lý theo chính sách đã xác định ở đầu stream; không xóa ký tự đầu một cách vô điều kiện.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Decoder strict báo malformed input | Byte nguồn bị cắt, sai charset hoặc dữ liệu đã hỏng | Lưu byte gốc, kiểm tra hợp đồng nguồn và vị trí lỗi |
| Decoder thành công nhưng văn bản sai | Charset được chọn không đúng nhưng byte vẫn hợp lệ theo charset đó | So với metadata, golden text hoặc vector byte đã biết |
| UTF-8 đầu ra hợp lệ nhưng nội dung sai | String đã sai trước khi encode | Kiểm tra code point ngay sau bước decode |
| Byte đầu ra có ký tự `?` | Đã dùng replacement khi mã hóa sang charset không biểu diễn được | Kiểm tra encoder, charset đích và byte replacement |
| Byte đầu ra bắt đầu bằng `EF BB BF` | Có BOM ở đầu file | Xác nhận định dạng đích có yêu cầu BOM hay không |
| Newline khác file nguồn | Có bước đọc/ghi theo dòng hoặc chuẩn hóa newline | So sánh U+000A/U+000D trước và sau chuyển đổi |
| File đích bị thiếu hoặc chỉ có một phần | Lỗi xảy ra trong khi ghi trực tiếp vào file đích | Ghi vào file tạm rồi thay thế sau khi conversion thành công |

### 9.1. Không tự động thử nhiều charset đến khi có kết quả

Một cách làm không an toàn là thử UTF-8, Windows-1252, ISO-8859-1 và chọn charset đầu tiên không ném exception. Nhiều charset có thể giải mã cùng byte thành văn bản khác nhau mà không báo lỗi. “Decode thành công” chỉ có nghĩa byte có thể được diễn giải theo charset đó, không chứng minh charset đó là charset nguồn.

Nếu metadata không còn, hãy yêu cầu bên phát xác nhận hoặc dùng một quy tắc khôi phục đã được nghiệp vụ chấp thuận. Không ghi đè file nguồn bằng kết quả đoán.

### 9.2. Không thay thế lỗi rồi tiếp tục như thể dữ liệu được bảo toàn

`new String(bytes, charset)` hoặc encoder dùng replacement có thể tạo kết quả nhìn hợp lệ, nhưng phần lỗi đã bị thay. Nếu nghiệp vụ cho phép thay thế, hãy ghi nhận số lần thay và thông báo rõ đây là conversion có mất mát. Với chuyển đổi cần bảo toàn, dùng `REPORT` và dừng khi có lỗi.

### 9.3. Phân biệt tính hợp lệ với tính đúng nội dung

UTF-8 strict decoder xác nhận byte tuân thủ cấu trúc UTF-8. Nó không biết văn bản đó có phải nội dung mà người dùng mong đợi hay không. Kiểm tra nội dung cần thêm bằng chứng độc lập: text chuẩn, code point kỳ vọng, checksum, số bản ghi hoặc quy tắc nghiệp vụ.

## 10. Quy trình chuyển đổi an toàn

1. **Xác định nguồn:** ghi nhận charset nguồn từ hợp đồng hoặc metadata; xác nhận BOM và newline nếu định dạng có quy tắc riêng.
2. **Giữ bản gốc:** không ghi đè nguồn; tạo đường dẫn đích riêng và lưu lại byte nguồn nếu cần audit.
3. **Đọc byte:** với file nhỏ/vừa có thể dùng `Files.readAllBytes`; với file lớn dùng stream.
4. **Decode strict:** dùng decoder của charset nguồn với `REPORT`; không dùng default charset hoặc thay thế âm thầm.
5. **Kiểm tra nội dung:** đối chiếu String/code point với golden data khi có; xác nhận không có mojibake hoặc ký tự thay thế ngoài dự kiến.
6. **Encode strict:** dùng UTF-8 encoder với `REPORT`; chọn rõ chính sách BOM đích.
7. **Ghi an toàn:** ghi ra file tạm cùng thư mục rồi move sau khi hoàn thành; chỉ ghi đè đích khi hợp đồng cho phép.
8. **Đọc lại và xác minh:** đọc byte đích, so sánh với byte đã encode, decode UTF-8 strict và kiểm tra nội dung.
9. **Lưu bằng chứng:** ghi charset nguồn, charset đích, kích thước byte, checksum hoặc vector hex phù hợp; tránh log nội dung nhạy cảm.

Sơ đồ quyết định:

```text
Đã biết charset nguồn?
   |-- Không --> Dừng, xác minh hợp đồng/metadata.
   |
   +-- Có
        |
        v
Decode với REPORT thành công?
   |-- Không --> Giữ byte gốc, báo lỗi nguồn.
   |
   +-- Có
        |
        v
Nội dung/code point đúng theo fixture?
   |-- Không --> Xem lại charset nguồn hoặc dữ liệu gốc.
   |
   +-- Có
        |
        v
Encode UTF-8 với REPORT thành công?
   |-- Không --> Kiểm tra String có surrogate lỗi.
   |
   +-- Có
        |
        v
Ghi, đọc lại và so byte?
   |-- Không --> Không công bố file đích.
   |
   +-- Có --> Xác nhận UTF-8 output.
```

## 11. Bài thực hành và tiêu chí hoàn thành

1. Tạo file Windows-1252 chứa byte `63 61 66 E9 20 80`. Dùng `Charset.forName("windows-1252")` để giải mã và xác nhận nội dung là `café €`.
2. Mã hóa String sang UTF-8 bằng encoder `REPORT`. Xác nhận byte đầu ra là `63 61 66 C3 A9 20 E2 82 AC`.
3. Đọc lại output bằng decoder UTF-8 strict. So sánh String và byte với fixture chuẩn.
4. Thử đọc cùng byte nguồn bằng ISO-8859-1. Giải thích vì sao decoder có thể thành công nhưng code point U+0080 khác U+20AC.
5. Thử một file UTF-8 có BOM. Chạy với chính sách giữ BOM và chính sách bỏ đúng BOM đầu file; so sánh code point và byte đầu ra.
6. Tạo file có CRLF và file có LF. Chuyển charset mà không đọc theo dòng; xác nhận newline được giữ nguyên.
7. Thử byte nguồn malformed với charset nguồn có thể phát hiện lỗi. Xác nhận `REPORT` dừng conversion và file đích hiện có không bị thay thế khi dùng chiến lược file tạm.
8. Chạy conversion trên file lớn bằng phương án streaming; so sánh checksum hoặc byte mẫu của đầu vào/đầu ra sau khi giải mã theo đúng charset.

**Tiêu chí hoàn thành:** bạn chọn được charset nguồn từ hợp đồng dữ liệu; chuyển byte thành Unicode và mã hóa UTF-8 bằng chính sách nghiêm ngặt; xác minh byte đầu ra độc lập với phép round-trip; xử lý BOM, newline và file lớn theo yêu cầu; và dừng conversion khi phát hiện dữ liệu không thể giải mã. Kỹ năng này vẫn áp dụng trên JDK hiện đại dù UTF-8 đã là charset mặc định của nhiều API từ Java 18.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi thay đổi default charset từ Java 18.
- [Java SE Charset](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html): charset chuẩn, lookup và default charset.
- [Java SE CharsetDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): decode, malformed input và error action.
- [Java SE CharsetEncoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetEncoder.html): encode, unmappable character và replacement.
- [Java SE Files](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): đọc, ghi và move file.
- [Unicode Standard — UTF-8](https://www.unicode.org/versions/latest/core-spec/chapter-3/): cấu trúc byte và tính hợp lệ của UTF-8.

