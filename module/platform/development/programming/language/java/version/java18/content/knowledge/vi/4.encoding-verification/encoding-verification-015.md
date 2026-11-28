# Thiết kế kiểm thử hồi quy mã hóa chạy ổn định trên máy cá nhân và CI

## 1. Mục tiêu của kiểm thử hồi quy encoding

Lỗi encoding thường xuất hiện sau khi đổi JDK, hệ điều hành, cấu hình JVM, thư viện đọc/ghi file hoặc môi trường chạy CI. Một bài test chỉ kiểm tra chuỗi “trông đúng” trên terminal có thể bỏ sót lỗi vì terminal, font và charset của output cũng tham gia vào quá trình hiển thị.

Kiểm thử hồi quy mã hóa cần xác nhận được các hợp đồng ở từng ranh giới:

1. Byte đầu vào được tạo theo encoding đã công bố.
2. Decoder sử dụng đúng charset và chính sách lỗi.
3. Chuỗi Java sau decode có đúng nội dung Unicode.
4. Encoder tạo ra đúng byte theo định dạng đầu ra.
5. File, giao thức và metadata tuân thủ hợp đồng qua các môi trường chạy.
6. Kết quả không thay đổi chỉ vì máy developer hoặc runner CI có locale, charset mặc định, line separator hay filesystem khác nhau.

Trong Java 18, JEP 400 đặt UTF-8 làm default charset thông thường. Điều này giảm khác biệt giữa các máy, nhưng không loại bỏ nhu cầu kiểm thử charset tường minh. Một API có hợp đồng riêng, một file cũ hoặc một giao thức đối tác vẫn có thể dùng ISO-8859-1, UTF-16 hay encoding khác.

```text
Fixture byte đã biết
        |
        v
Decode theo charset hợp đồng
        |
        v
Assert String / code point
        |
        v
Encode theo charset hợp đồng
        |
        v
Assert byte chính xác
        |
        v
Kiểm thử file / protocol / CI
```

Bài này xây dựng cách kiểm thử có thể lặp lại trên máy cá nhân và CI, tránh phụ thuộc vào hình thức hiển thị hoặc cấu hình ngầm của máy.

## 2. Nguyên tắc: kiểm tra hợp đồng, không kiểm tra cảm giác

Một kiểm thử encoding tốt phải có expected value độc lập với implementation đang kiểm tra.

Ví dụ không đủ mạnh:

```java
String original = "Tiếng Việt";
byte[] bytes = original.getBytes();
String restored = new String(bytes);

assertEquals(original, restored);
```

Test này dùng default charset cho cả encode và decode. Hai thao tác có thể cùng sai so với hợp đồng mà test vẫn pass.

Cách kiểm tra rõ ràng hơn:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;

String expected = "Tiếng Việt 🌍";
byte[] expectedBytes = {
        (byte) 0x54, (byte) 0x69, (byte) 0xE1, (byte) 0xBA,
        (byte) 0xBF, (byte) 0x6E, (byte) 0x67, (byte) 0x20,
        (byte) 0x56, (byte) 0x69, (byte) 0xE1, (byte) 0xBB,
        (byte) 0x87, (byte) 0x74, (byte) 0x20, (byte) 0xF0,
        (byte) 0x9F, (byte) 0x8C, (byte) 0x8D
};

assertArrayEquals(expectedBytes, expected.getBytes(StandardCharsets.UTF_8));
assertEquals(expected, new String(expectedBytes, StandardCharsets.UTF_8));
```

Trong test thực tế, expected bytes có thể nằm trong fixture binary được commit cùng source. Điểm cốt lõi là expected bytes không được sinh bằng chính phương thức đang kiểm thử trong cùng một assertion.

Các nguyên tắc nên áp dụng:

- Charset luôn được chỉ rõ khi hợp đồng dữ liệu đã chỉ rõ.
- Kiểm tra byte bằng `assertArrayEquals`, không chỉ so sánh chuỗi.
- Kiểm tra Unicode bằng `String.equals` hoặc code point khi cần chẩn đoán.
- Kiểm tra lỗi malformed/unmappable bằng decoder/encoder ở chế độ `REPORT`.
- Tách test codec khỏi test file I/O và test hiển thị.
- Không phụ thuộc `Charset.defaultCharset()` trừ khi chính default charset là điều đang được kiểm thử.

## 3. Xây dựng bộ fixture ổn định

Fixture là dữ liệu đầu vào đã biết trước, được lưu trong repository hoặc được khai báo dưới dạng byte literal. Fixture phải có encoding được ghi rõ trong tên, tài liệu hoặc metadata.

Ví dụ cấu trúc:

```text
src/test/
├── java/
│   └── com/example/encoding/
│       ├── Utf8CodecTest.java
│       ├── LegacyCharsetTest.java
│       ├── FileEncodingTest.java
│       └── DefaultCharsetProcessTest.java
└── resources/
    └── encoding/
        ├── utf8-vietnamese.txt
        ├── utf8-with-bom.txt
        ├── iso-8859-1-cafe.properties
        ├── malformed-utf8.bin
        └── utf16le-sample.txt
```

Không chỉ dựa vào phần mở rộng file để suy encoding. Có thể thêm README nhỏ trong thư mục fixture mô tả charset, BOM, line ending và nội dung mong đợi. Nếu fixture là file binary, không mở rồi lưu lại bằng editor có thể tự đổi encoding hoặc newline.

Một fixture nên có nhiều dạng dữ liệu:

| Nhóm | Ví dụ | Điều cần phát hiện |
| --- | --- | --- |
| ASCII | `ABC-123` | Không thể dùng ASCII để phân biệt nhiều charset |
| Latin có dấu | `café` | UTF-8 và ISO-8859-1 có byte khác nhau |
| Tiếng Việt | `Tiếng Việt` | Phát hiện lỗi decode/encode thường gặp |
| Ngoài BMP | `🌍` | Kiểm tra cặp surrogate và byte UTF-8 nhiều byte |
| Ký tự tiền tệ | `€` | Phân biệt ISO-8859-1 với Windows-1252 |
| Malformed UTF-8 | `C3 28` | Decoder `REPORT` phải từ chối |
| BOM | `EF BB BF` ở đầu | Xác minh chính sách BOM của định dạng |
| Unicode normalization | NFC/NFD | Chuỗi nhìn giống nhau nhưng code point khác |

Fixture không nên chỉ chứa ASCII. ASCII thường tạo kết quả giống nhau ở nhiều charset và không phát hiện được lỗi encoding.

## 4. Kiểm thử encode/decode UTF-8 bằng byte chính xác

Ví dụ dùng JUnit 5 để xác nhận UTF-8 round-trip và byte đầu ra:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class Utf8CodecTest {
    @Test
    void encodesAndDecodesVietnameseAsUtf8() {
        String expected = "Café - Tiếng Việt 🌍";

        byte[] bytes = expected.getBytes(StandardCharsets.UTF_8);
        String decoded = new String(bytes, StandardCharsets.UTF_8);

        assertEquals(expected, decoded);
        assertArrayEquals(
                new byte[] {
                        0x43, 0x61, 0x66, (byte) 0xC3, (byte) 0xA9,
                        0x20, 0x2D, 0x20,
                        0x54, 0x69, (byte) 0xE1, (byte) 0xBA,
                        (byte) 0xBF, 0x6E, 0x67, 0x20,
                        0x56, 0x69, (byte) 0xE1, (byte) 0xBB,
                        (byte) 0x87, 0x74, 0x20,
                        (byte) 0xF0, (byte) 0x9F, (byte) 0x8C, (byte) 0x8D
                },
                bytes);
    }
}
```

Đoạn test này xác nhận cả nội dung String lẫn biểu diễn byte UTF-8 của chuỗi. Khi có thay đổi JDK hoặc thư viện, nếu implementation vô tình quay về API dùng default charset, assertion byte sẽ phát hiện sai lệch.

Đối với dữ liệu lớn, không cần nhúng cả byte array trong test. Lưu fixture binary và so sánh với byte được tạo ra. Cần bảo đảm fixture được commit nguyên trạng và không bị Git/editor chuyển đổi line ending.

## 5. Kiểm thử charset legacy bằng fixture độc lập

Một hệ thống có thể vẫn phải đọc dữ liệu đối tác theo ISO-8859-1 hoặc Windows-1252. Kiểm thử những charset này là kiểm thử hợp đồng tương thích, không phải khuyến nghị dùng chúng cho file mới.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class LegacyCharsetTest {
    @Test
    void decodesIso88591BytesAccordingToContract() {
        byte[] bytes = {
                0x63, 0x61, 0x66, (byte) 0xE9
        };

        assertEquals(
                "café",
                new String(bytes, StandardCharsets.ISO_8859_1));
    }
}
```

ISO-8859-1 không biểu diễn được `€`. Windows-1252 có byte `80` cho ký tự euro. Nếu hệ thống nhận file từ đối tác Windows cũ, cần fixture riêng để xác nhận chính xác encoding mà hợp đồng yêu cầu:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.Charset;
import org.junit.jupiter.api.Test;

class Windows1252Test {
    @Test
    void decodesEuroAccordingToWindows1252Contract() {
        Charset windows1252 = Charset.forName("windows-1252");
        byte[] bytes = {(byte) 0x80};

        assertEquals("€", new String(bytes, windows1252));
    }
}
```

`windows-1252` được hỗ trợ trong các JDK OpenJDK thông dụng, nhưng nếu ứng dụng chạy trên runtime/provider tùy biến, hãy kiểm tra charset đó có sẵn. Không dùng byte `80` làm test ISO-8859-1 rồi mong nhận `€`; đó là nhầm lẫn giữa hai charset.

## 6. Kiểm thử malformed input với CharsetDecoder REPORT

Các constructor tiện lợi như `new String(bytes, UTF_8)` có thể thay byte lỗi bằng `U+FFFD`. Điều đó hữu ích cho một số ứng dụng hiển thị, nhưng không đủ để kiểm tra tính hợp lệ của payload.

Dùng `CharsetDecoder` với `CodingErrorAction.REPORT` để test phải thất bại khi byte malformed:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class MalformedUtf8Test {
    @Test
    void rejectsMalformedUtf8() {
        byte[] malformed = {(byte) 0xC3, 0x28};

        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        assertThrows(
                MalformedInputException.class,
                () -> decoder.decode(ByteBuffer.wrap(malformed)));
    }
}
```

`C3 28` không phải chuỗi UTF-8 hợp lệ: `C3` mở đầu một sequence nhiều byte nhưng `28` không phải continuation byte.

Có thể thêm assertion để minh họa khác biệt với decoder thay thế mặc định:

```java
String lenient = new String(malformed, StandardCharsets.UTF_8);

assertEquals('\uFFFD', lenient.charAt(0));
assertEquals('(', lenient.charAt(1));
```

Trong test production, chính sách phải theo hợp đồng. Nếu payload bắt buộc hợp lệ, hãy kiểm tra `REPORT`; không chấp nhận một test chỉ xác nhận rằng chương trình đã tạo ra một chuỗi nào đó.

## 7. Kiểm thử unmappable character khi encode

Malformed input và unmappable character là hai lỗi khác nhau. Chuỗi Java có thể hợp lệ nhưng charset đích không thể biểu diễn nó.

Ví dụ `€` hợp lệ trong Unicode nhưng không thể encode bằng US-ASCII:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;
import org.junit.jupiter.api.Test;

class UnmappableCharacterTest {
    @Test
    void rejectsEuroInAsciiOutput() {
        var encoder = StandardCharsets.US_ASCII.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        assertThrows(
                UnmappableCharacterException.class,
                () -> encoder.encode(CharBuffer.wrap("€")));
    }
}
```

Chuỗi UTF-16 chứa surrogate đứng lẻ là malformed input, khác với ký tự Unicode hợp lệ nhưng không có trong charset đích:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class MalformedSurrogateTest {
    @Test
    void rejectsUnpairedSurrogateWhenEncodingUtf8() {
        String malformed = new String(new char[] {(char) 0xD800});
        var encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        assertThrows(
                MalformedInputException.class,
                () -> encoder.encode(CharBuffer.wrap(malformed)));
    }
}
```

Nếu hệ thống chấp nhận replacement hoặc ignore, hãy test đúng chính sách đó bằng byte đầu ra cụ thể. Không chỉ kiểm tra `encoder.canEncode()` rồi kết luận mọi dữ liệu thực tế đều an toàn; dữ liệu có thể thay đổi giữa bước kiểm tra và bước ghi, hoặc chứa surrogate đứng lẻ.

## 8. Kiểm thử file I/O bằng thư mục tạm

Không dùng đường dẫn cố định như `C:\temp\test.txt` hoặc `/tmp/test.txt` trong test. Dùng `@TempDir` của JUnit 5 để tạo thư mục riêng cho từng test:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileEncodingTest {
    @TempDir
    Path tempDir;

    @Test
    void writesUtf8BytesAndReadsSameText() throws Exception {
        Path file = tempDir.resolve("message.txt");
        String expected = "Xin chào - Tiếng Việt 🌍";

        Files.writeString(file, expected, StandardCharsets.UTF_8);

        byte[] bytes = Files.readAllBytes(file);
        assertArrayEquals(
                expected.getBytes(StandardCharsets.UTF_8),
                bytes);

        assertEquals(
                expected,
                Files.readString(file, StandardCharsets.UTF_8));
    }
}
```

`Files.writeString` và `Files.readString` có overload nhận `Charset`; dùng overload đó để test không phụ thuộc default charset. `@TempDir` cũng tránh test va chạm khi CI chạy nhiều test song song.

Nếu cần test hợp đồng UTF-8 mặc định riêng của Files API, viết test riêng cho overload không charset và ghi rõ mục tiêu. Không trộn test đó với test default charset của JVM vì hai hợp đồng khác nhau.

## 9. Kiểm thử default charset của JVM trong tiến trình riêng

JEP 400 thay đổi default charset thông thường từ Java 18. Tuy nhiên, `Charset.defaultCharset()` là trạng thái môi trường được khởi tạo trong tiến trình. Không nên gọi `System.setProperty("file.encoding", ...)` giữa test suite rồi kỳ vọng default charset thay đổi ổn định.

Các nguyên tắc:

- Không thay `file.encoding` trong `@BeforeEach` hoặc `@AfterEach`.
- Không chạy các test phụ thuộc default charset song song trong cùng JVM với test sửa system properties.
- Không giả định charset default của máy cá nhân là giống charset của mọi runner.
- Nếu cần kiểm tra cấu hình JVM, chạy probe trong một JVM con với tham số khởi động riêng.
- Test logic nghiệp vụ nên truyền charset tường minh; test default charset là một nhóm integration/environment test riêng.

Một probe đơn giản:

```java
import java.io.IOException;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CharsetProbe {
    public static void main(String[] args) throws IOException {
        String result = Charset.defaultCharset().name()
                + "\n" + System.getProperty("file.encoding");
        Files.writeString(Path.of(args[0]), result, StandardCharsets.UTF_8);
    }
}
```

Có thể khởi chạy class này bằng `ProcessBuilder` với các VM arguments đã chọn cho test. Ví dụ, tiến trình riêng có thể được chạy với `-Dfile.encoding=UTF-8` để kiểm tra cấu hình UTF-8. Nếu cần kiểm tra chế độ tương thích `COMPAT`, chạy một tiến trình khác theo cấu hình đó và so sánh kết quả với môi trường native đã được ghi nhận. Không thay property sau khi JVM đã khởi tạo charset.

Ví dụ khởi chạy probe trong JVM con trên Windows, Linux hoặc macOS:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class DefaultCharsetProcessTest {
    @TempDir
    Path tempDir;

    @Test
    void startsForkedJvmWithUtf8Default() throws Exception {
        String executable = System.getProperty("os.name").startsWith("Windows")
                ? "java.exe" : "java";
        Path java = Path.of(System.getProperty("java.home"), "bin", executable);
        Path resultFile = tempDir.resolve("charset-probe.txt");

        Process process = new ProcessBuilder(
                java.toString(),
                "-Dfile.encoding=UTF-8",
                "-cp", System.getProperty("java.class.path"),
                CharsetProbe.class.getName(),
                resultFile.toString())
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start();

        if (!process.waitFor(30, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            throw new AssertionError("JVM con không kết thúc trong 30 giây");
        }
        assertEquals(0, process.exitValue());
        var observed = Files.readAllLines(resultFile, StandardCharsets.UTF_8);
        assertEquals("UTF-8", observed.get(0));
        assertEquals("UTF-8", observed.get(1));
    }
}
```

Probe ghi kết quả vào file bằng UTF-8 tường minh nên test không phụ thuộc charset của stdout hoặc terminal. Trong project thực tế, nếu test chạy trong module hoặc test runner có classpath riêng, truyền classpath/module path phù hợp cho JVM con.

Việc tạo process con cần dùng cùng JDK/toolchain đang được kiểm tra, truyền classpath rõ ràng và kiểm tra exit code. Không so sánh output bằng ảnh terminal; đọc kết quả đã ghi bằng encoding cố định.

## 10. Tách test UTF-8 mặc định của Files khỏi Charset.defaultCharset()

Một nguồn nhầm lẫn phổ biến là coi mọi API không truyền charset đều dùng `Charset.defaultCharset()`. Files API có hợp đồng UTF-8 riêng cho nhiều overload văn bản, chẳng hạn `Files.readString(path)` và `Files.newBufferedReader(path)`.

Kiểm thử riêng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FilesDefaultUtf8Test {
    @TempDir
    Path tempDir;

    @Test
    void readStringWithoutCharsetUsesFilesUtf8Contract() throws Exception {
        Path file = tempDir.resolve("vietnamese.txt");
        byte[] utf8 = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
        Files.write(file, utf8);

        assertEquals("Tiếng Việt", Files.readString(file));
    }
}
```

Test này kiểm tra hợp đồng của Files API, không kiểm tra `Charset.defaultCharset()`. Nó nên pass độc lập với default charset JVM nếu chạy trên JDK hỗ trợ API đó.

Ngược lại, test `new String(bytes)` hoặc `text.getBytes()` là test default charset; nếu cần xác nhận hành vi của nó, dùng process con và cấu hình khởi động xác định.

## 11. Kiểm thử BOM và chính sách xử lý BOM

UTF-8 không bắt buộc BOM. Nếu định dạng cho phép BOM, test phải xác định rõ ứng dụng giữ hay loại bỏ BOM.

Ví dụ xác nhận decoder UTF-8 tạo `U+FEFF` ở đầu chuỗi khi byte BOM được decode trực tiếp:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class Utf8BomTest {
    @Test
    void utf8DecoderPreservesBomAsLeadingCharacter() {
        byte[] bytes = {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF,
                0x41, 0x42, 0x43
        };

        String text = new String(bytes, StandardCharsets.UTF_8);

        assertEquals('\uFEFF', text.charAt(0));
        assertEquals("ABC", text.substring(1));
    }
}
```

Nếu ứng dụng cần bỏ BOM theo hợp đồng file, test hành vi đó ở lớp đọc file của ứng dụng. Không viết test chung rằng “mọi decoder phải tự xóa BOM”; API và định dạng có quy tắc riêng.

Khi nhận diện BOM, kiểm tra UTF-32 trước UTF-16 vì byte BOM UTF-32 little-endian `FF FE 00 00` có cùng prefix `FF FE` với UTF-16 little-endian.

## 12. Kiểm thử newline và Unicode normalization

Encoding không tự chuẩn hóa newline hoặc Unicode normalization.

### 12.1. Newline

`Files.readString` giữ nội dung newline như trong file. `BufferedReader.readLine()` bỏ line terminator khi trả từng dòng. `BufferedWriter.newLine()` ghi line separator của nền tảng.

Nếu định dạng file quy định LF (`\n`) bất kể hệ điều hành, hãy ghi và kiểm tra byte LF tường minh:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FixedNewlineTest {
    @TempDir
    Path tempDir;

    @Test
    void writesLfRegardlessOfOperatingSystem() throws Exception {
        Path file = tempDir.resolve("records.txt");
        String content = "first\nsecond\n";
        Files.writeString(file, content, StandardCharsets.UTF_8);

        byte[] bytes = Files.readAllBytes(file);
        assertArrayEquals(content.getBytes(StandardCharsets.UTF_8), bytes);
    }
}
```

Nếu định dạng cho phép newline của nền tảng, kiểm tra theo quy tắc đó. Đừng để test phụ thuộc `System.lineSeparator()` khi output là một giao thức hoặc file có đặc tả LF/CRLF cố định.

### 12.2. Unicode normalization

Hai chuỗi có thể hiển thị giống nhau nhưng có code point khác nhau. Ví dụ `é` có thể là một code point NFC (`U+00E9`) hoặc `e` cộng combining acute accent NFD (`U+0065 U+0301`).

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.text.Normalizer;
import java.text.Normalizer.Form;

String nfc = "\u00E9";
String nfd = "e\u0301";

assertNotEquals(nfc, nfd);
assertEquals(
        Normalizer.normalize(nfd, Form.NFC),
        nfc);
```

Nếu hợp đồng dữ liệu yêu cầu giữ nguyên code point, so sánh chính xác chuỗi và byte. Nếu hợp đồng yêu cầu chuẩn hóa NFC/NFD, kiểm thử bước normalization riêng. Charset encoding và Unicode normalization là hai vấn đề khác nhau.

## 13. Kiểm thử không phụ thuộc Locale, timezone và thứ tự test

Một test encoding có thể vô tình phụ thuộc vào locale nếu dùng `Formatter`, `Scanner` hoặc API định dạng số. Ví dụ dấu thập phân trong `printf` có thể thay đổi theo locale.

- Truyền `Locale.ROOT` hoặc locale được hợp đồng quy định khi định dạng số.
- Không dùng default Locale để tạo nội dung fixture.
- Nếu test có định dạng ngày/giờ, dùng `ZoneId`/`Clock` cố định theo hợp đồng; timezone không phải charset nhưng có thể làm expected text thay đổi giữa runner.
- Không dựa vào thứ tự chạy test để thiết lập `file.encoding`.
- Không sửa system properties toàn cục trong test song song.
- Không giả định thứ tự file trong thư mục hoặc thứ tự key trong `Properties`.
- Không so sánh toàn bộ file có comment timestamp nếu API ghi comment thời gian; so sánh nội dung đã parse hoặc loại bỏ phần không ổn định theo hợp đồng.

Nếu cần kiểm tra `Properties.store`, kiểm tra byte/encoding và nạp lại theo đúng API tương ứng. Đừng chỉ so sánh file nguyên văn khi định dạng cho phép timestamp hoặc thứ tự entry không cố định.

## 14. Ma trận chạy CI

Kiểm thử cần chạy trên JDK và môi trường mà dự án hỗ trợ. Với dự án hiện đại, dùng toolchain rõ ràng và ma trận CI có chủ đích thay vì dựa vào JDK cài sẵn trên runner.

Ví dụ ma trận khái niệm:

| Trục | Các cấu hình nên cân nhắc | Mục tiêu |
| --- | --- | --- |
| JDK | JDK tối thiểu dự án hỗ trợ và các JDK LTS/hiện hành mà dự án kiểm thử | Phát hiện thay đổi runtime/API |
| OS | Linux, Windows, macOS nếu sản phẩm hỗ trợ | Phát hiện path, newline, filesystem và console khác nhau |
| Charset default | Cấu hình UTF-8; chế độ COMPAT nếu dự án cần hỗ trợ | Phát hiện phụ thuộc default charset |
| Locale | Locale mặc định khác nhau | Phát hiện định dạng số/ngày ngoài ý muốn |
| Test mode | Chạy thường và test process con | Kiểm tra cấu hình khởi động JVM |

Không cần chạy mọi tổ hợp nếu chi phí CI lớn. Chọn tổ hợp đại diện dựa trên phạm vi hỗ trợ thực tế và tách test unit nhanh khỏi integration test môi trường.

### 14.1. Cố định JDK toolchain

Maven/Gradle nên dùng toolchain hoặc cấu hình CI để đảm bảo compiler và test JVM chạy trên JDK đã chọn. Chỉ đặt `--release` không tự bảo đảm test đang chạy bằng cùng runtime version.

Trong CI, in ra `java -version`, `javac -version`, `Charset.defaultCharset()` và các thông tin môi trường hữu ích ở đầu job. Dữ liệu này giúp điều tra khi chỉ một runner bị lỗi.

### 14.2. Giữ test độc lập giữa các runner

- Mỗi job có workspace riêng.
- Fixture được checkout nguyên trạng.
- Test dùng `@TempDir` hoặc thư mục tạm riêng.
- Không ghi output vào cùng file dùng chung giữa test song song.
- Không dựa vào cache test để bỏ qua test encoding.
- Nếu test dùng subprocess, truyền đường dẫn JDK/classpath rõ ràng thay vì dựa vào `PATH` ngẫu nhiên.

## 15. Kiểm tra encoding của fixture trong repository

Một fixture có thể bị thay đổi ngay trong quá trình commit nếu editor, script sinh file hoặc Git attributes chuyển encoding/newline. Nên kiểm tra byte thực tế của fixture trong test hoặc bằng công cụ độc lập.

Có thể dùng Java để in hex:

```java
import java.nio.file.Files;
import java.nio.file.Path;

byte[] bytes = Files.readAllBytes(Path.of("src/test/resources/encoding/utf8-vietnamese.txt"));

for (byte value : bytes) {
    System.out.printf("%02X ", value & 0xFF);
}
System.out.println();
```

Khi cần xác minh file được lưu đúng trong Git:

- Kiểm tra fixture trên working tree và blob đã commit nếu có nghi ngờ line-ending conversion.
- Tránh đặt `working-tree-encoding` hoặc `text` conversion tùy tiện cho fixture binary.
- Dùng `.gitattributes` phù hợp để fixture byte-sensitive không bị biến đổi ngoài ý muốn.
- Với fixture văn bản có newline chuẩn, ghi rõ LF/CRLF và kiểm tra bytes.
- Không mở và save fixture bằng editor tự đổi encoding mà không xác nhận.

Nếu fixture là file nhị phân chứa byte malformed, không khai báo nó như file text trong Git.

## 16. Kiểm thử ResourceBundle và Properties theo đúng API

Không gộp mọi file `.properties` thành một loại encoding. Hai API có hợp đồng byte khác nhau:

| API | Hợp đồng khi nhận byte |
| --- | --- |
| `Properties.load(InputStream)` | ISO-8859-1 |
| `PropertyResourceBundle(InputStream)` | UTF-8 trước; mặc định fallback ISO-8859-1 khi malformed/unmappable, có thể khóa bằng system property |
| `Properties.load(Reader)` | Reader quyết định charset |
| `PropertyResourceBundle(Reader)` | Reader quyết định charset |

Một test đọc file UTF-8 trực tiếp qua `Properties` nên tạo Reader UTF-8:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class PropertiesUtf8Test {
    @TempDir
    Path tempDir;

    @Test
    void loadsUtf8PropertiesThroughReader() throws Exception {
        Path file = tempDir.resolve("messages.properties");
        Files.writeString(file, "greeting=Tiếng Việt 🌍\n",
                StandardCharsets.UTF_8);

        Properties properties = new Properties();
        try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        assertEquals("Tiếng Việt 🌍", properties.getProperty("greeting"));
    }
}
```

Với `PropertyResourceBundle(InputStream)`, nếu cần kiểm thử system property `java.util.PropertyResourceBundle.encoding`, hãy chạy test trong JVM riêng vì property được đọc khi lớp khởi tạo. Không đổi property giữa các test rồi mong lớp được khởi tạo lại.

## 17. Chẩn đoán lỗi chỉ xảy ra trên CI

Khi test pass trên máy cá nhân nhưng fail trên CI, thu thập đủ bằng chứng trước khi đổi charset:

1. JDK vendor, version và runtime executable thực tế.
2. `Charset.defaultCharset()` và cấu hình `file.encoding` lúc JVM khởi động.
3. Charset được chọn từ hợp đồng/metadata của payload.
4. Byte đầu vào (hoặc hash/fixture tái hiện được nếu payload nhạy cảm).
5. Kết quả strict decode và loại ngoại lệ.
6. Locale, line separator, OS và filesystem.
7. Charset của `System.out`/`System.err` nếu lỗi chỉ xuất hiện ở log/terminal.
8. Fixture có bị chuyển newline/encoding trong checkout hoặc build step hay không.

Từ Java 18, `PrintStream.charset()` giúp kiểm tra charset của `System.out` và `System.err`. Nó có thể khác `Charset.defaultCharset()`. Nếu chuỗi trong bộ nhớ đúng nhưng log terminal sai, điều tra tầng output và terminal trước khi sửa decoder đầu vào.

Ví dụ thu thập thông tin trong test hoặc diagnostic task:

```java
import java.nio.charset.Charset;

System.out.println("JVM default: " + Charset.defaultCharset().name());
System.out.println("stdout: " + System.out.charset().name());
System.out.println("stderr: " + System.err.charset().name());
```

Một test có thể in code point để phân biệt lỗi dữ liệu với lỗi render:

```java
String value = actualText;

value.codePoints().forEach(codePoint ->
        System.err.printf("U+%04X%n", codePoint));
```

Nếu code point đúng nhưng glyph hiển thị sai, đó là vấn đề font/render. Nếu chuỗi chứa `U+FFFD` hoặc mojibake, kiểm tra byte và charset tại điểm decode.

## 18. Danh sách kiểm tra trước khi merge

- [ ] Charset của mọi file/protocol đầu vào được xác định từ hợp đồng hoặc metadata.
- [ ] Code đọc/ghi dữ liệu có charset tường minh khi định dạng quy định charset.
- [ ] Test không dùng `getBytes()` hoặc `new String(bytes)` không charset trừ khi đang kiểm tra default charset.
- [ ] Expected bytes độc lập với code đang kiểm thử.
- [ ] Có fixture Unicode ngoài ASCII, tiếng Việt và ký tự ngoài BMP.
- [ ] Có test malformed input và unmappable output theo chính sách nghiệp vụ.
- [ ] BOM được giữ/bỏ theo đặc tả, không xử lý chung cho mọi file.
- [ ] Newline và Unicode normalization được kiểm tra riêng với encoding.
- [ ] Test file dùng thư mục tạm, không ghi vào đường dẫn cố định.
- [ ] Test default charset chạy trong process riêng nếu cần thay cấu hình JVM.
- [ ] CI dùng JDK toolchain đã xác định và runner OS phù hợp phạm vi hỗ trợ.
- [ ] Fixture byte-sensitive không bị Git/editor chuyển đổi.
- [ ] Test ResourceBundle/Properties dùng đúng hợp đồng API.
- [ ] Log/terminal được phân biệt với dữ liệu decode trong bộ nhớ.

## 19. Những nhận định dễ nhầm

- **“Round-trip thành công là đủ chứng minh encoding đúng.”** Sai. Encode và decode cùng charset sai vẫn có thể tạo kết quả nhất quán.
- **“JDK 18+ luôn làm mọi test encoding pass giống nhau.”** Sai. API có hợp đồng riêng, cấu hình COMPAT, output stream và terminal vẫn có thể khác.
- **“Đặt `file.encoding` trong `@BeforeEach` sẽ đổi default charset.”** Không đáng tin cậy. Charset được khởi tạo theo JVM; dùng process riêng với VM arguments.
- **“ASCII fixture đủ để test UTF-8.”** Sai. ASCII giống nhau trong nhiều charset; cần Unicode đa dạng.
- **“Một chuỗi hiển thị đúng trên terminal chứng minh byte đúng.”** Sai. Font và terminal là tầng render riêng.
- **“`new String(bytes, UTF_8)` tự báo lỗi byte malformed.”** Sai. API tiện lợi thay byte lỗi; dùng `CharsetDecoder` với `REPORT` nếu phải từ chối.
- **“BOM luôn được decoder tự xóa.”** Sai. Kiểm tra hợp đồng và hành vi API cụ thể.
- **“Newline là một phần của charset.”** Sai. Charset mã hóa ký tự; quy tắc line ending thuộc định dạng và cách ghi.
- **“NFC và NFD là cùng một chuỗi vì nhìn giống nhau.”** Sai. Chúng có thể có dãy code point khác nhau.
- **“Một test dùng default Locale có thể chạy ổn định trên mọi CI.”** Không bảo đảm. Truyền Locale theo hợp đồng khi định dạng dữ liệu.

## 20. Tài liệu tham khảo chính thức

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset từ Java 18, `file.encoding` và chế độ tương thích.
- [Charset — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/Charset.html): default charset, tên charset và tạo encoder/decoder.
- [CharsetDecoder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html): strict decoding và `CodingErrorAction`.
- [CharsetEncoder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html): strict encoding và lỗi malformed/unmappable.
- [Files — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): đọc/ghi văn bản với charset tường minh và UTF-8 theo hợp đồng API.
- [PrintStream — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/PrintStream.html): `charset()` và kiểm tra encoding của stream xuất.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, assertions, `@TempDir` và parameterized tests.
- [Git Attributes](https://git-scm.com/docs/gitattributes): quản lý line endings và nội dung fixture trong repository.

