# Dùng giá trị byte và mã Unicode làm bằng chứng khi terminal hiển thị sai

## 1. Mục tiêu

Trong module **JAVA_VERSION_JAVA18**, Java 18 đưa UTF-8 thành charset mặc định cho nhiều API Java theo [JEP 400](https://openjdk.org/jeps/400). Tuy nhiên, điều này không bảo đảm mọi byte xuất hiện ở terminal đều được giải mã và vẽ đúng. Terminal có thể dùng charset khác, IDE có thể chuyển tiếp dữ liệu qua lớp riêng, và font có thể thiếu glyph.

Bài thuộc chương **Kiểm chứng mã hóa**. Hai loại bằng chứng độc lập sẽ được dùng:

- **Byte hex:** cho biết byte thực tế, ví dụ **c3 a9** là UTF-8 của U+00E9 (**é**).
- **Unicode code point:** cho biết chuỗi Java chứa giá trị nào, ví dụ U+0065 U+0301 là **e** cộng dấu sắc kết hợp, khác U+00E9 dù thường nhìn giống nhau.

Không kết luận dữ liệu hỏng chỉ vì glyph trên màn hình sai. Kiểm tra code point trong **String**, byte sau encode, charset của luồng xuất và byte thực tế ở đích trước khi sửa chương trình.

## 2. Bốn lớp cần phân biệt

```text
Mã nguồn / dữ liệu đầu vào
        |
        v
Java String (UTF-16 code units, Unicode code points)
        |
        | PrintStream.encode theo charset của stream
        v
Byte trên stdout / stderr
        |
        | terminal hoặc consumer giải mã byte
        v
Ký tự được terminal tiếp nhận
        |
        | font, shaping, glyph coverage
        v
Hình ảnh người dùng nhìn thấy
```

| Lớp | Dấu hiệu | Bằng chứng |
| --- | --- | --- |
| Mã nguồn / dữ liệu đầu vào | Chuỗi sai trước khi in | Code point, byte nguồn, cách đọc file |
| Java output stream | PrintStream mã hóa không phù hợp | System.out.charset(), System.err.charset() |
| Terminal / consumer | Byte đúng nhưng giải mã sai | Charset terminal, locale/code page, byte capture |
| Font / bộ dựng chữ | Byte và chuỗi đúng nhưng hiện ô vuông hoặc emoji sai | Glyph coverage, font fallback, text shaping |

**Các charset không giống nhau:**

- **Charset.defaultCharset()** là charset mặc định của JVM. Từ Java 18, mặc định là UTF-8 trong cấu hình thông thường theo JEP 400.
- **System.out.charset()** và **System.err.charset()** cho biết charset của từng PrintStream. Phương thức **PrintStream.charset()** có từ Java 18.
- **System.console().charset()** cho biết charset của Console khi có console. **Console.charset()** có từ Java 17; **System.console()** có thể trả null trong IDE, service hoặc môi trường không có console.
- Charset của terminal hoặc chương trình nhận pipe là cách consumer giải mã byte. Java không thể suy ra font chỉ từ **Charset.defaultCharset()**.

Vì vậy, default charset là UTF-8 chưa chứng minh System.out, terminal và font cùng xử lý UTF-8 đúng.

## 3. Code point không phải số glyph

String của Java dùng đơn vị mã UTF-16. Một code point ngoài BMP dùng cặp surrogate, nên String.length() không phải số code point. Một glyph người dùng nhìn thấy cũng có thể gồm nhiều code point.

| Chuỗi | Code point | UTF-16 length | UTF-8 hex |
| --- | --- | ---: | --- |
| A | U+0041 | 1 | 41 |
| é dựng sẵn | U+00E9 | 1 | c3 a9 |
| e + dấu sắc tổ hợp | U+0065 U+0301 | 2 | 65 cc 81 |
| 🚀 | U+1F680 | 2 | f0 9f 9a 80 |
| 👩‍💻 | U+1F469 U+200D U+1F4BB | 5 | f0 9f 91 a9 e2 80 8d f0 9f 92 bb |

👩‍💻 có ba code point nhưng thường được dựng như một emoji ghép. U+200D là ZERO WIDTH JOINER. Terminal hoặc font không hỗ trợ sequence này có thể hiển thị thành nhiều hình riêng dù chuỗi và byte đều hợp lệ.

NFC và NFD cũng khác nhau:

```java
String composed = "é";           // U+00E9
String decomposed = "e\u0301";   // U+0065 U+0301

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.codePointCount(0, composed.length())); // 1
System.out.println(decomposed.codePointCount(0, decomposed.length())); // 2
```

Nếu hai dạng trông giống nhau nhưng equals là false, chưa thể kết luận terminal bị lỗi. Chỉ chuẩn hóa bằng Normalizer khi hợp đồng dữ liệu yêu cầu; trong chẩn đoán hãy ghi lại code point ban đầu trước khi chuẩn hóa.

## 4. Chương trình chẩn đoán trên Java 18+

Lưu đoạn mã dưới đây thành **TerminalEncodingDiagnostic.java** bằng UTF-8. Chương trình in charset mặc định, charset của stdout/stderr và charset của Console nếu có; ghi một tệp báo cáo UTF-8 bằng API tường minh; kiểm tra byte và giải mã nghiêm ngặt; in code point cùng byte hex bằng ký tự ASCII.

```java
import java.io.Console;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;
import java.util.Locale;

public final class TerminalEncodingDiagnostic {
    private static final String SAMPLE =
            "VI|Tiếng Việt"
            + "|NFC=é"
            + "|NFD=e\u0301"
            + "|ROCKET=🚀"
            + "|DEV=👩‍💻";

    private static final Path REPORT = Path.of("terminal-encoding-report.txt");

    public static void main(String[] args) throws Exception {
        byte[] expectedUtf8 = SAMPLE.getBytes(StandardCharsets.UTF_8);
        String reportText = SAMPLE + "\n";

        Files.writeString(REPORT, reportText, StandardCharsets.UTF_8);
        byte[] reportBytes = Files.readAllBytes(REPORT);
        String restored = decodeUtf8Strict(reportBytes);

        require(reportText.equals(restored),
                "File UTF-8 đọc lại không giống chuỗi ban đầu");
        require(reportBytes[reportBytes.length - 1] == 0x0A,
                "File báo cáo thiếu byte LF cuối dòng");

        requireHex("é", "c3a9");
        requireHex("e\u0301", "65cc81");
        requireHex("🚀", "f09f9a80");

        // Gửi raw bytes riêng một lần chạy để tránh trộn hai encoding.
        if (args.length > 0 && args[0].equals("raw-utf8")) {
            System.out.write(expectedUtf8);
            System.out.write(0x0A);
            System.out.flush();
            return;
        }

        System.out.println("DEFAULT_CHARSET="
                + java.nio.charset.Charset.defaultCharset().name());
        System.out.println("STDOUT_CHARSET=" + System.out.charset().name());
        System.out.println("STDERR_CHARSET=" + System.err.charset().name());

        Console console = System.console();
        System.out.println("CONSOLE_CHARSET="
                + (console == null ? "<no-console>" : console.charset().name()));

        System.out.println("SAMPLE_CODE_POINTS=" + codePointReport(SAMPLE));
        System.out.println("SAMPLE_UTF8_HEX=" + HexFormat.of().formatHex(expectedUtf8));
        System.out.println("FILE_UTF8_HEX=" + HexFormat.of().formatHex(reportBytes));
        System.out.println("FILE_ROUND_TRIP=PASS");
        System.out.println(SAMPLE);
        System.out.println("REPORT_PATH=" + REPORT.toAbsolutePath());
    }

    private static String codePointReport(String value) {
        StringBuilder result = new StringBuilder();
        value.codePoints().forEach(cp -> {
            if (result.length() > 0) result.append(' ');
            result.append(String.format(Locale.ROOT, "U+%04X", cp));
            String name = Character.getName(cp);
            if (name != null) result.append('[').append(name).append(']');
        });
        return result.toString();
    }

    private static String decodeUtf8Strict(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static void requireHex(String value, String expectedHex)
            throws CharacterCodingException {
        String actualHex = HexFormat.of().formatHex(
                value.getBytes(StandardCharsets.UTF_8));
        if (!actualHex.equals(expectedHex)) {
            throw new AssertionError("UTF-8 vector sai: " + actualHex);
        }
    }

    private static void require(boolean valid, String message) {
        if (!valid) throw new AssertionError(message);
    }
}
```

Biên dịch trên JDK 18 hoặc mới hơn:

```bash
javac -encoding UTF-8 TerminalEncodingDiagnostic.java
java TerminalEncodingDiagnostic
```

Tham số **-encoding UTF-8** nói rõ charset của mã nguồn cho compiler. Nếu file .java đã bị lưu sai encoding hoặc compiler đọc sai, String SAMPLE có thể sai trước khi chương trình bắt đầu in.

### Cách đọc kết quả

- **DEFAULT_CHARSET** thường là UTF-8 từ Java 18 theo JEP 400.
- **STDOUT_CHARSET** là charset thực tế của PrintStream đang ghi ra stdout. **STDERR_CHARSET** có thể khác, nên kiểm tra riêng nếu log lỗi hiển thị khác log thường.
- **CONSOLE_CHARSET=<no-console>** nghĩa là JVM không có đối tượng Console; thường gặp khi chạy trong IDE, service hoặc môi trường không có console. Không xem đây là lỗi chương trình.
- **SAMPLE_CODE_POINTS** cho biết nội dung String thực sự chứa. Ký tự có dấu hoặc emoji hiển thị sai nhưng code point đúng có thể là lỗi ở tầng output/terminal/font.
- **SAMPLE_UTF8_HEX** cho biết byte UTF-8 kỳ vọng được tạo từ SAMPLE; **FILE_UTF8_HEX** là byte đã đọc lại từ file.
- **FILE_ROUND_TRIP=PASS** chứng minh tệp báo cáo đúng theo phép kiểm tra của chương trình. Nó chưa chứng minh terminal đang giải mã hoặc dựng glyph đúng.

**PrintStream.charset()** là API công khai từ Java 18. Có thể dùng trực tiếp trên JDK hiện đại để kiểm tra charset của chính stream, thay vì dựa vào thuộc tính nội bộ của JVM.

## 5. Kiểm tra byte mà không cần tin vào terminal

Chương trình trên tạo **terminal-encoding-report.txt** bằng Files.writeString với UTF-8 tường minh và xác minh bằng Files.readAllBytes. Đây là bằng chứng ở tầng file, không phụ thuộc cách terminal vẽ ký tự.

Nếu cần kiểm tra file bên ngoài, dùng công cụ hiển thị byte:

```powershell
Format-Hex -Path terminal-encoding-report.txt
```

Trên Linux hoặc macOS, có thể dùng:

```bash
xxd -g 1 terminal-encoding-report.txt
# hoặc
od -An -tx1 -c terminal-encoding-report.txt
```

Các công cụ này cho biết byte thực tế. Với nội dung UTF-8 có tiếng Việt hoặc emoji, hãy tìm byte mốc đã biết thay vì đọc phần ký tự hiển thị của công cụ. Ví dụ é dựng sẵn phải có c3 a9; emoji 🚀 phải có f0 9f 9a 80.

Để kiểm tra byte của stdout, có thể chạy chương trình với đầu ra được chuyển hướng vào file nhị phân bằng shell phù hợp, sau đó xem file bằng công cụ hex. Lưu ý một số shell/IDE có cơ chế redirect hoặc ghi file riêng; hãy xác định công cụ nào đang nhận stdout và liệu nó có chuyển mã hay không. Tệp báo cáo được ghi trực tiếp bằng Files.writeString trong chương trình là phép đối chiếu đơn giản hơn.

### Chế độ gửi raw UTF-8

Chạy:

```bash
java TerminalEncodingDiagnostic raw-utf8
```

Chế độ này dùng System.out.write(byte[]) để gửi byte UTF-8 trực tiếp, bỏ qua encoder ký tự của PrintStream. So sánh với lần chạy bình thường:

- Nếu chế độ println hiển thị đúng còn raw-utf8 sai, charset của PrintStream và cách terminal giải mã raw UTF-8 có thể không khớp.
- Nếu println sai nhưng raw UTF-8 đúng, hãy kiểm tra STDOUT_CHARSET và charset mà terminal đang mong đợi.
- Nếu cả hai hiển thị sai nhưng file UTF-8 và code point đúng, tập trung kiểm tra terminal/consumer và font.
- Nếu SAMPLE_CODE_POINTS hoặc byte trong file đã sai, vấn đề xảy ra trước tầng terminal: kiểm tra mã nguồn, compiler encoding hoặc bước giải mã dữ liệu đầu vào.

Không trộn lẫn các lần ghi text và raw bytes trong cùng một luồng sản phẩm mà không có hợp đồng rõ ràng. Chế độ raw ở đây chỉ là phép thử chẩn đoán.

## 6. Phân biệt lỗi charset với lỗi font và bộ dựng chữ

Một khi đã xác nhận code point trong String đúng, byte xuất ra đúng theo charset đã thống nhất và consumer giải mã byte bằng đúng charset, lỗi còn lại có thể nằm ở font hoặc bộ dựng chữ.

| Biểu hiện | Khả năng | Hướng xác minh |
| --- | --- | --- |
| Tiếng Việt thành Tiáº¿ng Viá»‡t | Byte UTF-8 bị giải mã như charset khác (mojibake) | So STDOUT_CHARSET, charset terminal và byte thực tế |
| Emoji thành ? hoặc � | Charset encoder không biểu diễn được dữ liệu hoặc byte lỗi bị thay thế | Kiểm tra code point, encoder, byte hex; dùng encoder REPORT khi cần |
| Emoji thành ô vuông/tofu | Font thiếu glyph hoặc fallback không hoạt động | Chọn font có glyph; kiểm tra cùng nội dung trong terminal/font khác |
| e và dấu sắc tách rời | Font hoặc shaping không ghép combining mark đúng; hoặc chuỗi không ở dạng mong đợi | Xem code point có U+0065 U+0301 hay không; thử font khác |
| 👩‍💻 tách thành nhiều emoji | Terminal/font không hỗ trợ đúng chuỗi emoji có ZWJ | Kiểm tra U+200D và thử terminal/font có hỗ trợ emoji sequence |
| Dòng tiếng Việt trong IDE sai nhưng file đọc bằng UTF-8 đúng | Console của IDE có cấu hình/decoder riêng | So sánh với terminal ngoài và kiểm tra thiết lập encoding của IDE |

**Mojibake** thường là dấu hiệu giải mã byte bằng charset sai. **Tofu** (ô vuông rỗng) thường là dấu hiệu không có glyph phù hợp. Hai biểu hiện có thể giống nhau trong một số font, vì vậy vẫn cần byte hex và code point để kết luận.

Code point đúng cũng không bảo đảm mọi terminal vẽ được ký tự đó. Unicode có thể chứa ký tự kết hợp, variation selector, zero-width joiner và emoji sequence; việc ghép chúng thành một glyph phụ thuộc khả năng của font và text shaping engine.

## 7. Kiểm tra môi trường terminal và luồng nhận

### Windows

Trong Command Prompt hoặc PowerShell, lệnh sau hiển thị active console code page:

```powershell
chcp
```

Mã trang của console là một thông tin về cách console xử lý văn bản; nó không cho biết font có glyph hay không. Windows Terminal, PowerShell host, ứng dụng IDE và chương trình nhận pipe có thể có các lớp cấu hình khác nhau. Đừng thay code page một cách máy móc trước khi xác định byte chương trình đang phát.

### Linux và macOS

Kiểm tra locale/charset của môi trường:

```bash
locale
locale charmap
```

LANG, LC_CTYPE và LC_ALL có thể ảnh hưởng cách một số chương trình native xử lý văn bản. Nếu Java chạy qua SSH, container hoặc pipeline, hãy kiểm tra cả môi trường ở phía tiến trình chạy Java và terminal phía người dùng. Một locale UTF-8 ở máy local không tự động chứng minh môi trường remote đang dùng UTF-8.

### IDE, log collector và pipeline

Khi System.console() là null, chương trình có thể đang ghi vào IDE, test runner, log collector hoặc pipe. Consumer đó có thể dùng decoder khác terminal ngoài. Hãy kiểm tra:

- System.out.charset() và System.err.charset() của Java process.
- Cấu hình encoding của console trong IDE hoặc test runner.
- Charset mà log viewer dùng để đọc file/log stream.
- Byte thực tế sau khi đi qua pipeline hoặc SSH, nếu có.

Đừng mặc định mọi công cụ đều dùng cùng charset chỉ vì chương trình Java đang chạy trên JDK 18+.

## 8. Quy trình chẩn đoán theo bằng chứng

Khi gặp lỗi hiển thị, đi theo thứ tự sau để khoanh vùng:

1. **Kiểm tra chuỗi trước khi in:** ghi code point bằng String.codePoints() và tên bằng Character.getName. Nếu sai, truy ngược nơi tạo String hoặc giải mã input.
2. **Kiểm tra byte kỳ vọng:** encode bằng StandardCharsets.UTF_8, ghi hex và so với vector chuẩn hoặc golden file.
3. **Kiểm tra encoder của output:** đọc System.out.charset()/System.err.charset() trên Java 18+; khi có console, đối chiếu System.console().charset().
4. **Kiểm tra byte ở đích:** ghi file UTF-8 bằng Files.writeString hoặc capture raw stdout, rồi đọc bằng Files.readAllBytes/hex viewer.
5. **Kiểm tra consumer:** xác minh terminal, shell, IDE, SSH hoặc log collector giải mã đúng charset.
6. **Kiểm tra font:** chỉ sau khi code point và byte đều đúng, mới tập trung vào glyph coverage, font fallback và khả năng dựng combining mark/emoji.

Sơ đồ quyết định:

```text
Code point của String có đúng?
   |-- Không --> Sai ở source/input/decode trước khi in.
   |
   +-- Có
        |
        v
Byte đầu ra có đúng theo hợp đồng?
   |-- Không --> Kiểm tra PrintStream charset/encode.
   |
   +-- Có
        |
        v
Consumer giải mã đúng charset?
   |-- Không --> Sửa cấu hình terminal/IDE/pipeline.
   |
   +-- Có
        |
        v
Glyph vẫn sai?
   |-- Có --> Kiểm tra font, fallback và text shaping.
   +-- Không --> Hiển thị đã đúng.
```

Nếu chuỗi được chuẩn hóa Unicode hoặc biến đổi theo nghiệp vụ trước khi in, phải xác định điểm chuẩn so sánh trước bước biến đổi. Đừng coi NFC/NFD là lỗi mã hóa nếu hợp đồng cho phép hai dạng tương đương; cũng đừng tự chuẩn hóa khi yêu cầu là bảo toàn byte nguyên gốc.

## 9. Bài thực hành

1. Chạy TerminalEncodingDiagnostic và lưu lại DEFAULT_CHARSET, STDOUT_CHARSET, STDERR_CHARSET, CONSOLE_CHARSET.
2. Đối chiếu SAMPLE_CODE_POINTS và SAMPLE_UTF8_HEX. Xác nhận é là U+00E9/c3a9, còn e + dấu sắc là U+0065 U+0301/65cc81.
3. Mở terminal-encoding-report.txt bằng hex viewer. Kiểm tra file có byte UTF-8 đúng và kết thúc bằng 0a.
4. Chạy chế độ raw-utf8 và so với chế độ println. Ghi nhận khác biệt, nếu có, rồi dùng charset của stream và terminal để giải thích.
5. Mở cùng file hoặc chạy cùng chương trình trong terminal/font khác. Nếu byte và code point không đổi nhưng glyph đổi, đó là bằng chứng cho vấn đề font/bộ dựng chữ.
6. Thử đưa một chuỗi có combining mark hoặc emoji ZWJ vào fixture. Kiểm tra code point trước, rồi mới đánh giá hình dạng glyph.

**Tiêu chí hoàn thành:** bạn có thể dùng byte hex và Unicode code point để chứng minh chuỗi Java có đúng hay không; xác định được charset của PrintStream và console khi có; phân biệt lỗi encode/decode với lỗi font; và đưa ra bằng chứng ở đúng lớp thay vì sửa charset mặc định một cách phỏng đoán. Đây là kỹ năng vẫn cần thiết trên JDK hiện đại dù UTF-8 đã trở thành charset mặc định từ Java 18.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ Java 18 và phạm vi của thay đổi.
- [Java SE PrintStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintStream.html): charset() cho biết charset mà stream sử dụng; API này có từ Java 18.
- [Java SE Console](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html): charset và reader/writer của console.
- [Java SE String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): codePoints() và cách biểu diễn chuỗi.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): ranh giới grapheme cluster và phân đoạn văn bản Unicode.
