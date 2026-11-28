# Kiểm thử UTF-8 hợp lệ, byte bị cắt, BOM và chuỗi đầu vào không thể giải mã

## 1. Mục tiêu: phân biệt dữ liệu sai với dữ liệu chưa nhận đủ

Trong module **JAVA_VERSION_JAVA18**, Java 18 đưa UTF-8 thành charset mặc định cho nhiều API Java theo [JEP 400](https://openjdk.org/jeps/400). Thay đổi này vẫn hữu ích trên JDK hiện đại, nhưng không làm cho mọi chuỗi byte trở thành UTF-8 hợp lệ. Dữ liệu từ file, HTTP, classpath hoặc tiến trình con vẫn phải được kiểm tra theo hợp đồng của nguồn.

Bài thuộc chương **Kiểm chứng mã hóa**. Ta sẽ xây dựng bộ kiểm thử để phân biệt bốn trường hợp:

1. **UTF-8 hợp lệ:** byte tạo thành các chuỗi mã UTF-8 đúng chuẩn và giải mã được.
2. **Byte bị cắt:** một ký tự nhiều byte mới nhận được một phần, thường do kết thúc file hoặc luồng truyền bị ngắt.
3. **BOM UTF-8:** ba byte đánh dấu ở đầu dữ liệu; đây là một dấu hiệu định dạng hợp lệ nhưng cần xử lý theo quy tắc của file/giao thức.
4. **Dữ liệu không thể giải mã:** byte vi phạm cấu trúc UTF-8, chẳng hạn continuation byte đứng riêng, overlong sequence, surrogate được mã hóa trực tiếp hoặc code point vượt giới hạn Unicode.

Điểm cần nhớ: **một chunk kết thúc bằng byte chưa hoàn chỉnh chưa chắc là lỗi nếu luồng còn dữ liệu tiếp theo**. Nó chỉ trở thành lỗi khi bên nhận xác nhận đã đến cuối dữ liệu mà ký tự vẫn chưa hoàn chỉnh.

Sau bài này, bạn có thể dùng **CharsetDecoder** ở chế độ **CodingErrorAction.REPORT**, kiểm tra BOM ở đúng vị trí, nhận biết malformed input và phân biệt lỗi thật với tình huống streaming cần chờ thêm byte.

## 2. UTF-8 hợp lệ có cấu trúc như thế nào?

UTF-8 mã hóa một Unicode code point bằng từ một đến bốn byte:

| Dải code point | Số byte | Mẫu byte |
| --- | ---: | --- |
| U+0000 đến U+007F | 1 | 0xxxxxxx |
| U+0080 đến U+07FF | 2 | 110xxxxx 10xxxxxx |
| U+0800 đến U+FFFF (trừ surrogate) | 3 | 1110xxxx 10xxxxxx 10xxxxxx |
| U+10000 đến U+10FFFF | 4 | 11110xxx 10xxxxxx 10xxxxxx 10xxxxxx |

Các byte bắt đầu bằng 10 là continuation byte; chúng phải xuất hiện đúng số lượng và đúng vị trí sau một byte mở đầu. UTF-8 hiện đại cũng yêu cầu mã hóa ngắn nhất (không overlong), không mã hóa surrogate U+D800–U+DFFF và không vượt U+10FFFF.

Ví dụ vector byte:

| Ký tự | Code point | Byte UTF-8 |
| --- | --- | --- |
| A | U+0041 | 41 |
| é | U+00E9 | C3 A9 |
| € | U+20AC | E2 82 AC |
| 🚀 | U+1F680 | F0 9F 9A 80 |

Các ví dụ lỗi:

| Byte hex | Vì sao không hợp lệ |
| --- | --- |
| 80 | Continuation byte đứng riêng, không có byte mở đầu. |
| C0 AF | Overlong encoding; ký tự không được mã hóa bằng số byte ngắn hơn quy định. |
| E2 28 A1 | Byte thứ hai 28 không phải continuation byte. |
| ED A0 80 | Mã hóa giá trị thuộc vùng surrogate U+D800–U+DFFF. |
| F4 90 80 80 | Giá trị vượt U+10FFFF. |
| FF | Không phải byte mở đầu hợp lệ trong UTF-8. |

**Byte bị cắt khác malformed sequence ở giữa dữ liệu:** E2 82 có thể là phần đầu của ký tự € nếu chunk tiếp theo mang AC. Nhưng nếu đó là toàn bộ dữ liệu và EOF đã được xác nhận, chuỗi UTF-8 chưa hoàn chỉnh và phải bị từ chối trong chế độ nghiêm ngặt.

## 3. BOM UTF-8: byte hợp lệ nhưng cần chính sách rõ ràng

UTF-8 BOM (Byte Order Mark) là dãy byte:

```text
EF BB BF
```

Khi giải mã như UTF-8, ba byte này biểu diễn code point U+FEFF (ZERO WIDTH NO-BREAK SPACE; ở đầu luồng thường được dùng làm dấu BOM). UTF-8 không cần BOM để xác định byte order, vì UTF-8 không có vấn đề endian như UTF-16/UTF-32. Do đó, BOM là dấu hiệu tùy chọn của một số định dạng và công cụ, không phải yêu cầu chung của UTF-8 hay của JEP 400.

**Java decoder UTF-8 không tự động bỏ BOM.** Khi giải mã EF BB BF 41, kết quả bắt đầu bằng U+FEFF rồi đến A. Các API đọc văn bản dùng UTF-8 không nên được giả định là tự loại bỏ dấu này. Nếu định dạng cho phép BOM và ứng dụng muốn loại bỏ, hãy loại bỏ **đúng ba byte ở đầu dữ liệu** hoặc đúng một U+FEFF ở đầu chuỗi sau khi giải mã. Không xóa mọi U+FEFF ở giữa nội dung.

Chọn một trong các chính sách sau theo hợp đồng:

| Chính sách | Cách xử lý | Khi nào dùng |
| --- | --- | --- |
| BOM bị cấm | Phát hiện prefix EF BB BF và từ chối input | Định dạng quy định không có BOM. |
| BOM được chấp nhận và bỏ | Bỏ đúng prefix ở offset 0 trước khi decode | File văn bản cho phép BOM nhưng ứng dụng muốn nội dung thuần. |
| BOM được giữ như ký tự | Giải mã bình thường, giữ U+FEFF đầu chuỗi | Ứng dụng cần bảo toàn chính xác nội dung đã nhận. |

Không nhầm BOM với chuỗi UTF-8 lỗi. EF BB BF là một chuỗi byte UTF-8 hợp lệ. Quyết định chấp nhận hay từ chối là **quy tắc của định dạng**, không phải lỗi của decoder.

## 4. Dùng decoder nghiêm ngặt để kiểm tra input hoàn chỉnh

Phương thức tiện dụng new String(bytes, StandardCharsets.UTF_8) thay thế dữ liệu không hợp lệ bằng ký tự U+FFFD (REPLACEMENT CHARACTER). Khi cần xác nhận đầu vào đúng UTF-8, dùng **CharsetDecoder** với **CodingErrorAction.REPORT**.

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] bytes)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString();
}
```

Phương thức CharsetDecoder.decode(ByteBuffer) là thao tác giải mã toàn bộ input, coi buffer hiện có là dữ liệu cuối cùng (end of input). Vì vậy, byte bị cắt ở cuối sẽ được báo là malformed input thay vì chờ thêm byte.

Ví dụ:

```java
byte[] validEuro = {(byte) 0xE2, (byte) 0x82, (byte) 0xAC};
byte[] truncatedEuro = {(byte) 0xE2, (byte) 0x82};

String euro = decodeUtf8Strict(validEuro); // "€"

// Ném MalformedInputException: ký tự 3 byte bị cắt ở cuối.
decodeUtf8Strict(truncatedEuro);
```

MalformedInputException là một dạng CharacterCodingException. Khi đọc file hoặc xử lý giao thức, hãy bắt lỗi ở ranh giới input và đưa ra thông báo có ngữ cảnh (tên file, endpoint, offset nếu có). Không tiếp tục xử lý chuỗi đã bị thay thế U+FFFD như thể dữ liệu gốc vẫn nguyên vẹn.

### 4.1. Thử bộ dữ liệu hợp lệ và không hợp lệ

Ví dụ sau kiểm tra nhiều trường hợp bằng một helper:

```java
import java.nio.charset.CharacterCodingException;

static void expectValid(byte[] bytes, String expected) throws Exception {
    String actual = decodeUtf8Strict(bytes);
    if (!expected.equals(actual)) {
        throw new AssertionError("Nội dung UTF-8 không khớp");
    }
}

static void expectInvalid(byte[] bytes) throws Exception {
    try {
        decodeUtf8Strict(bytes);
        throw new AssertionError("Đã chấp nhận byte UTF-8 không hợp lệ");
    } catch (CharacterCodingException expected) {
        // Đạt: decoder REPORT đã từ chối dữ liệu.
    }
}

static void runVectors() throws Exception {
    expectValid(new byte[] {0x41}, "A");
    expectValid(new byte[] {(byte) 0xC3, (byte) 0xA9}, "é");
    expectValid(new byte[] {
            (byte) 0xE2, (byte) 0x82, (byte) 0xAC
    }, "€");
    expectValid(new byte[] {
            (byte) 0xF0, (byte) 0x9F, (byte) 0x9A, (byte) 0x80
    }, "🚀");

    expectInvalid(new byte[] {(byte) 0x80}); // continuation đứng riêng
    expectInvalid(new byte[] {(byte) 0xC0, (byte) 0xAF}); // overlong
    expectInvalid(new byte[] {
            (byte) 0xE2, 0x28, (byte) 0xA1
    }); // continuation sai
    expectInvalid(new byte[] {
            (byte) 0xED, (byte) 0xA0, (byte) 0x80
    }); // surrogate
    expectInvalid(new byte[] {
            (byte) 0xF4, (byte) 0x90, (byte) 0x80, (byte) 0x80
    }); // ngoài U+10FFFF
    expectInvalid(new byte[] {(byte) 0xFF}); // byte mở đầu cấm

    expectInvalid(new byte[] {(byte) 0xC3}); // EOF sau byte đầu 2-byte
    expectInvalid(new byte[] {(byte) 0xE2, (byte) 0x82}); // EOF 3-byte
    expectInvalid(new byte[] {
            (byte) 0xF0, (byte) 0x9F, (byte) 0x9A
    }); // EOF 4-byte
}
```

Các test cuối là trường hợp **đã kết thúc input**. Nếu cùng các byte đó xuất hiện ở cuối một chunk nhưng stream vẫn mở, decoder streaming phải giữ lại byte chưa hoàn chỉnh để ghép với chunk tiếp theo; không được coi UNDERFLOW trước EOF là lỗi.

## 5. Byte bị cắt trong streaming: phân biệt UNDERFLOW và malformed

Khi đọc dữ liệu theo nhiều chunk, một ký tự UTF-8 có thể bị chia qua ranh giới chunk. Ví dụ ký tự € có byte E2 82 AC. Nếu chunk đầu chỉ chứa E2 82, decoder chưa thể xuất ký tự nhưng cũng chưa thể kết luận input lỗi, vì AC có thể đến sau.

Với API streaming CharsetDecoder.decode(input, output, endOfInput):

- **endOfInput=false:** nếu cuối buffer có chuỗi byte chưa hoàn chỉnh, decoder trả CoderResult.UNDERFLOW và để nguyên các byte chưa tiêu thụ trong input buffer. Caller phải giữ lại chúng và nối với byte chunk kế tiếp.
- **endOfInput=true:** caller xác nhận không còn byte nào nữa. Chuỗi byte chưa hoàn chỉnh ở cuối sẽ là malformed input nếu action là REPORT.
- **CoderResult.OVERFLOW:** buffer output không đủ chỗ; caller cần xử lý phần ký tự đã tạo và gọi tiếp, không bỏ dữ liệu.
- Sau khi decode với endOfInput=true thành công, gọi flush để hoàn tất decoder theo hợp đồng API.

Ví dụ tối giản: chunk đầu mang hai byte đầu của €, chunk thứ hai mang byte cuối. Buffer đầu vào dùng compact() để giữ phần byte decoder chưa tiêu thụ:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CoderResult;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

ByteBuffer input = ByteBuffer.allocate(4);
CharBuffer output = CharBuffer.allocate(4);

// Chunk 1: hai byte đầu của U+20AC.
input.put((byte) 0xE2).put((byte) 0x82);
input.flip();

CoderResult first = decoder.decode(input, output, false);
if (first.isError()) first.throwException();
if (!first.isUnderflow()) throw new AssertionError("Cần UNDERFLOW");

// Giữ lại byte chưa tiêu thụ ở đầu buffer, rồi thêm chunk kế tiếp.
input.compact();
input.put((byte) 0xAC);
input.flip();

// Chunk 2 hoàn tất ký tự; đây cũng là EOF.
CoderResult last = decoder.decode(input, output, true);
if (last.isError()) last.throwException();
if (last.isOverflow()) throw new AssertionError("Output buffer quá nhỏ");

CoderResult flushed = decoder.flush(output);
if (flushed.isError()) flushed.throwException();
if (flushed.isOverflow()) throw new AssertionError("Output buffer quá nhỏ");

output.flip();
if (!"€".contentEquals(output)) {
    throw new AssertionError("Không ghép đúng ký tự từ hai chunk");
}
```

Đoạn mã minh họa một ký tự và buffer đủ lớn. Trong bộ đọc production, cần lặp xử lý OVERFLOW, đọc thêm vào buffer sau compact, và chỉ đặt endOfInput=true khi nguồn thật sự báo EOF. Không tạo decoder mới cho từng chunk; decoder phải giữ trạng thái giữa các lần gọi.

**Quy tắc quan trọng:** UNDERFLOW chỉ có nghĩa decoder cần thêm input hoặc đã tiêu thụ hết input hiện có. Nó không tự khẳng định dữ liệu hợp lệ hoàn chỉnh. Chỉ khi đã báo EOF và gọi decode với endOfInput=true, decoder mới có đủ thông tin để kết luận một chuỗi byte cuối bị cắt là lỗi.

## 6. Kiểm tra BOM và quyết định chấp nhận

Dùng prefix byte để nhận diện UTF-8 BOM:

```java
static boolean hasUtf8Bom(byte[] bytes) {
    return bytes.length >= 3
            && (bytes[0] & 0xFF) == 0xEF
            && (bytes[1] & 0xFF) == 0xBB
            && (bytes[2] & 0xFF) == 0xBF;
}
```

Nếu định dạng cho phép BOM và muốn bỏ nó đúng một lần:

```java
import java.util.Arrays;

static byte[] stripLeadingUtf8Bom(byte[] bytes) {
    if (!hasUtf8Bom(bytes)) return bytes;
    return Arrays.copyOfRange(bytes, 3, bytes.length);
}
```

Sau đó mới giải mã phần còn lại bằng decoder nghiêm ngặt. Nếu BOM bị cấm, hãy từ chối thay vì âm thầm bỏ. Nếu cần bảo toàn file byte nguyên gốc, hãy giữ byte[] ban đầu và lưu lại quyết định BOM riêng.

Không dùng String.replace(U+FEFF, "") trên toàn bộ văn bản: U+FEFF có thể xuất hiện như dữ liệu ở vị trí khác và thao tác thay toàn cục làm mất thông tin. Nếu đã giải mã và định dạng cho phép bỏ dấu ở đầu chuỗi, chỉ bỏ đúng một ký tự U+FEFF ở index 0.

Ví dụ xác nhận decoder giữ BOM:

```java
byte[] bomAndA = {
        (byte) 0xEF, (byte) 0xBB, (byte) 0xBF, 0x41
};

String decoded = decodeUtf8Strict(bomAndA);
if (!decoded.equals("\uFEFFA")) {
    throw new AssertionError("BOM không được giữ theo mong đợi");
}
```

Đây là phép thử hữu ích để chứng minh BOM không tự biến mất khi giải mã bằng UTF-8. Quy tắc thực tế vẫn phải theo định dạng: một số công cụ xuất file có BOM, trong khi nhiều giao thức yêu cầu hoặc mặc định nội dung UTF-8 không BOM.

## 7. Tạo bộ kiểm thử file hoàn chỉnh

Khi kiểm tra file văn bản, hãy xác minh ba lớp riêng:

1. Byte file có tuân thủ hợp đồng không (BOM, newline, byte UTF-8).
2. Toàn bộ byte có giải mã nghiêm ngặt được không.
3. Chuỗi sau decode có đúng nội dung kỳ vọng không.

Ví dụ với file UTF-8 không BOM:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

Path file = Path.of("sample-utf8.txt");
String expected = "Tiếng Việt 🚀\n";
byte[] expectedBytes = expected.getBytes(StandardCharsets.UTF_8);

Files.write(file, expectedBytes);

byte[] actualBytes = Files.readAllBytes(file);
if (!Arrays.equals(expectedBytes, actualBytes)) {
    throw new AssertionError("Byte file khác dữ liệu kỳ vọng");
}
if (hasUtf8Bom(actualBytes)) {
    throw new AssertionError("File không được có BOM");
}

String actualText = decodeUtf8Strict(actualBytes);
if (!expected.equals(actualText)) {
    throw new AssertionError("Chuỗi đọc lại không khớp");
}
```

Trong ứng dụng thật, không phải file nào cũng cần cấm BOM hoặc dùng LF. Các điều kiện đó phải xuất phát từ định dạng file mà ứng dụng hỗ trợ. Ví dụ trên chọn một hợp đồng đơn giản để minh họa: UTF-8, không BOM, LF cuối dòng.

Với HTTP, cần xác định body đã được giải nén hay chưa và charset/media type mà endpoint cam kết. Với tài nguyên classpath, đọc byte từ getResourceAsStream rồi áp dụng charset của tài nguyên. Với tiến trình con, đừng coi EOF của một lần đọc chunk là EOF của toàn bộ tiến trình nếu pipe vẫn mở.

## 8. Bảng chẩn đoán và cách xử lý

| Quan sát | Diễn giải | Hành động |
| --- | --- | --- |
| Decoder strict giải mã thành công, không BOM | Byte hợp lệ theo UTF-8 | Tiếp tục kiểm tra nội dung và hợp đồng dữ liệu. |
| Prefix là EF BB BF, decoder trả U+FEFF đầu chuỗi | BOM hợp lệ, chưa có chính sách xử lý | Áp dụng quy tắc của định dạng: giữ, bỏ prefix hoặc từ chối. |
| C3 ở cuối file, EOF đã xác nhận | Ký tự hai byte bị cắt | Báo input không hoàn chỉnh; lấy lại nguồn hoặc từ chối file. |
| E2 82 ở cuối chunk, stream vẫn mở | Ký tự ba byte có thể hoàn tất ở chunk tiếp | Giữ byte còn lại và chờ chunk sau. |
| 80 đứng riêng hoặc C0 AF | Byte sequence không hợp lệ | Từ chối input, ghi nhận vị trí lỗi. |
| new String(bytes, UTF_8) tạo U+FFFD | API tiện dụng đã thay byte lỗi khi giải mã | Giữ byte gốc và dùng decoder REPORT để xác minh. |
| Decoder strict thành công nhưng nội dung sai | Byte hợp lệ nhưng có thể chọn sai charset/hợp đồng | Kiểm tra metadata, charset bên phát và vector chuẩn. |

Đừng dùng việc “không có exception” làm bằng chứng duy nhất. Byte có thể hợp lệ dưới UTF-8 nhưng vẫn không đúng nội dung mong đợi; BOM có thể hợp lệ nhưng bị cấm theo định dạng; và chunk chưa hoàn chỉnh chỉ trở thành lỗi khi xác nhận EOF.

## 9. Những lỗi triển khai cần tránh

### 9.1. Dùng String constructor để xác thực byte

new String(bytes, UTF_8) được thiết kế để tạo String thuận tiện. Với byte malformed, nó thay thế phần dữ liệu lỗi bằng U+FFFD thay vì cung cấp bằng chứng rằng input bị lỗi. Khi cần xác thực, hãy dùng decoder với REPORT và giữ byte nguồn để ghi log/đối chiếu.

### 9.2. Coi UNDERFLOW là dữ liệu hợp lệ hoàn chỉnh

Trong streaming, UNDERFLOW có thể có nghĩa là buffer hết dữ liệu hoặc còn byte chưa hoàn chỉnh chờ chunk tiếp theo. Phải giữ các byte chưa tiêu thụ, đọc thêm và chỉ đánh dấu EOF khi nguồn báo kết thúc. Khi EOF thật sự đến, gọi decode với endOfInput=true để phát hiện phần cuối bị cắt.

### 9.3. Tạo decoder mới cho từng chunk

Decoder giữ trạng thái chuyển đổi và cần phối hợp với phần byte còn lại ở cuối chunk. Nếu tạo decoder mới mỗi lần đọc, chuỗi nhiều byte bị chia đôi có thể bị xử lý như các input độc lập và bị từ chối hoặc thay thế sai. Giữ một decoder cho một luồng logic; khi kết thúc luồng, hoàn tất decode và flush theo đúng trình tự.

### 9.4. Tự ý xóa BOM hoặc ký tự thay thế

Không loại bỏ BOM toàn cục và không xóa U+FFFD để “làm sạch” nội dung. U+FFFD có thể là ký tự thật mà người dùng nhập; chỉ byte decode lỗi mới là bằng chứng malformed input. Hãy lưu byte gốc, xác định quy tắc định dạng và áp dụng chính sách đúng ở đầu luồng.

### 9.5. Đoán charset khi byte không giải mã được

Một byte sequence không hợp lệ dưới UTF-8 không tự chứng minh nó là Windows-1252, ISO-8859-1 hay charset khác. Cần metadata của định dạng, header, BOM tương ứng hoặc hợp đồng từ bên phát. Nếu không có, hãy báo không xác định thay vì đoán và làm thay đổi nội dung.

## 10. Bài thực hành và tiêu chí hoàn thành

1. **Input hợp lệ:** kiểm tra ASCII, tiếng Việt, €, 🚀 bằng decoder strict và đối chiếu code point.
2. **Byte bị cắt:** thử C3, E2 82, F0 9F 9A khi toàn bộ input đã kết thúc. Tất cả phải bị từ chối.
3. **Chunk bị chia:** gửi E2 82 ở chunk đầu và AC ở chunk sau. Decoder streaming phải giữ hai byte đầu và tạo đúng € khi nhận byte cuối.
4. **BOM:** kiểm tra EF BB BF 41. Xác nhận kết quả giải mã có U+FEFF ở đầu; thử riêng chính sách giữ, bỏ prefix hoặc từ chối.
5. **Byte sai cấu trúc:** thử 80, C0 AF, E2 28 A1, ED A0 80, F4 90 80 80, FF. Decoder strict phải báo lỗi.
6. **So sánh cách giải mã:** thử new String(bytes, UTF_8) với decodeUtf8Strict trên byte sai. Quan sát sự khác biệt giữa thay thế U+FFFD và từ chối input.

**Tiêu chí hoàn thành:** bạn phân biệt được UTF-8 hợp lệ, malformed sequence và byte chưa hoàn chỉnh do chunk; hiểu rằng EOF quyết định byte bị cắt có phải lỗi hay không; xử lý BOM theo chính sách của định dạng; và dùng decoder REPORT để không âm thầm chấp nhận dữ liệu lỗi. Đây là cách kiểm chứng input UTF-8 còn phù hợp trên các JDK hiện đại kể từ thay đổi mặc định của Java 18.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ Java 18.
- [Java SE CharsetDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): decode, end-of-input, flush và error action.
- [Java SE CoderResult](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CoderResult.html): phân biệt UNDERFLOW, OVERFLOW và coding error.
- [Unicode Standard, UTF-8](https://www.unicode.org/versions/latest/core-spec/chapter-3/): cấu trúc và tính hợp lệ của UTF-8.
