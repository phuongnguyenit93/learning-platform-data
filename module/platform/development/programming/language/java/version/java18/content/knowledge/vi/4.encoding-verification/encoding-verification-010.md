# Kiểm tra đầu ra trực tiếp, chuyển hướng ra tệp và truyền qua pipe trên Windows hoặc Linux

## 1. Mục tiêu: xác định byte thay đổi ở ranh giới nào

Trong module **JAVA_VERSION_JAVA18**, UTF-8 trở thành charset mặc định của nhiều API Java từ JDK 18 theo [JEP 400](https://openjdk.org/jeps/400). Điều này giúp hành vi mặc định nhất quán hơn, nhưng một chương trình Java vẫn phải giao tiếp với terminal, file, shell và tiến trình khác. Mỗi ranh giới có thể có quy tắc xử lý byte riêng.

Bài thuộc chương **Kiểm chứng mã hóa**. Ta sẽ kiểm tra cùng một chuỗi theo ba đường đi:

1. **Đầu ra trực tiếp:** Java ghi ra terminal đang gắn với tiến trình. Terminal phải giải mã byte và font phải dựng glyph.
2. **Chuyển hướng ra tệp:** shell lấy byte stdout của Java và ghi vào file. Có thể kiểm tra byte thật bằng hex viewer mà không cần tin vào cách hiển thị.
3. **Truyền qua pipe:** stdout của tiến trình Java thứ nhất trở thành stdin của tiến trình thứ hai. Ta sẽ dùng một chương trình nhận chỉ đọc byte, in hex và thử giải mã UTF-8 nghiêm ngặt.

Ta sẽ so sánh hai cách phát dữ liệu:

- `System.out.print(String)` để `PrintStream` mã hóa String theo charset của chính stream.
- `System.out.write(byte[])` với byte đã mã hóa tường minh bằng UTF-8, bỏ qua bước chuyển String thành byte của `PrintStream`.

**Nguyên tắc chẩn đoán:** `Charset.defaultCharset()` cho biết default charset của JVM; `System.out.charset()` cho biết charset mà `PrintStream` dùng để mã hóa ký tự; còn terminal, shell hoặc tiến trình nhận quyết định cách diễn giải byte tiếp theo. Không thể suy ra toàn bộ đường đi chỉ từ một trong các giá trị đó.

## 2. Ba đường đi của stdout

```text
                       +------------------------+
                       | Java String trong JVM  |
                       +------------+-----------+
                                    |
                   +----------------+----------------+
                   |                                 |
          System.out.print(text)           getBytes(UTF_8)
                   |                                 |
           PrintStream charset               byte UTF-8 tường minh
                   |                                 |
                   +----------------+----------------+
                                    |
                               stdout bytes
                                    |
                +-------------------+-------------------+
                |                   |                   |
             Terminal          Redirect file        Native pipe
                |                   |                   |
          decode + font          raw bytes          stdin bytes
                |                   |                   |
          hình ảnh hiển thị      hex viewer        consumer kiểm tra
```

Ba đường đi có thể cho kết quả khác nhau dù chương trình chỉ có một chuỗi nguồn:

- Terminal có thể hiển thị sai vì charset giải mã hoặc font.
- File chuyển hướng có thể chứa byte khác UTF-8 nếu `PrintStream` phát theo charset khác.
- Pipe giữa hai tiến trình native thường truyền byte trực tiếp, nhưng một shell có thể giải mã và mã hóa lại khi thực hiện pipeline theo mô hình đối tượng của nó.

## 3. Những thông tin cần ghi nhận trước khi kiểm tra

Trên JDK 18+, `PrintStream.charset()` là API công khai để xem charset mà một `PrintStream` sử dụng. Hãy kiểm tra riêng stdout và stderr vì đây là hai stream độc lập. Nếu JVM có `Console`, `Console.charset()` cho biết charset của console; `System.console()` có thể trả `null` khi chạy trong IDE, service hoặc pipe.

| Thông tin | API/lệnh | Cho biết điều gì |
| --- | --- | --- |
| Default charset JVM | `Charset.defaultCharset()` | Charset của API dựa vào default charset. JDK 18+ mặc định UTF-8 theo JEP 400, trừ cấu hình tương thích được hỗ trợ. |
| Charset stdout | `System.out.charset()` | Charset mà `PrintStream` dùng khi ghi ký tự ra stdout. |
| Charset stderr | `System.err.charset()` | Charset mà `PrintStream` dùng khi ghi ký tự ra stderr. |
| Charset console | `System.console().charset()` nếu Console tồn tại | Charset của console được JVM nhận diện. |
| Windows console code page | `chcp` trong Command Prompt | Code page đang hoạt động trong console host. |
| Linux locale charset | `locale charmap` | Charset của locale hiện tại trong môi trường tiến trình. |

Các thông tin này là bằng chứng về từng lớp. `System.out.charset()` không cho biết font có glyph hay không; `chcp` không chứng minh byte file đã được mã hóa đúng; `locale charmap` không xác nhận nội dung một file cụ thể.

## 4. Chương trình kiểm tra stdout ở bốn chế độ

Lưu mã dưới đây thành **StdoutTransportProbe.java** bằng UTF-8. Chương trình có năm chế độ:

- `--info`: in thông tin charset bằng ASCII.
- `--text`: ghi chuỗi qua `System.out.print`, dùng charset của `PrintStream`.
- `--raw-utf8`: ghi byte UTF-8 được tạo tường minh.
- `--stderr-text`: ghi chuỗi qua `System.err.print`, dùng charset của stderr.
- `--capture`: đọc toàn bộ stdin dưới dạng byte, in độ dài, hex, so sánh với byte UTF-8 kỳ vọng và thử giải mã nghiêm ngặt.

Chế độ capture chỉ xuất báo cáo ASCII bằng `System.out.write`, để kết quả của consumer không bị ảnh hưởng bởi việc mã hóa một chuỗi tiếng Việt khác.

```java
import java.io.Console;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.Locale;

public final class StdoutTransportProbe {
    private static final String SAMPLE =
            "ASCII|Tiếng Việt|café|€|🚀\n";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Use --info, --text, --raw-utf8, --stderr-text or --capture");
        }

        switch (args[0]) {
            case "--info" -> printInfo();
            case "--text" -> writeText();
            case "--raw-utf8" -> writeRawUtf8();
            case "--stderr-text" -> writeStderrText();
            case "--capture" -> capture();
            default -> throw new IllegalArgumentException("Unknown mode");
        }
    }

    private static void printInfo() throws IOException {
        Console console = System.console();

        writeAsciiLine("DEFAULT_CHARSET="
                + java.nio.charset.Charset.defaultCharset().name());
        writeAsciiLine("STDOUT_CHARSET=" + System.out.charset().name());
        writeAsciiLine("STDERR_CHARSET=" + System.err.charset().name());
        writeAsciiLine("CONSOLE_CHARSET="
                + (console == null ? "<no-console>" : console.charset().name()));
        writeAsciiLine("FILE_ENCODING="
                + System.getProperty("file.encoding"));
        writeAsciiLine("NATIVE_ENCODING="
                + System.getProperty("native.encoding"));
    }

    private static void writeText() {
        // PrintStream chuyển String thành byte theo charset của stream.
        System.out.print(SAMPLE);
        System.out.flush();
    }

    private static void writeRawUtf8() throws IOException {
        // Byte đã được mã hóa rõ ràng; write(byte[]) không encode String.
        byte[] bytes = SAMPLE.getBytes(StandardCharsets.UTF_8);
        System.out.write(bytes);
        System.out.flush();
    }

    private static void writeStderrText() {
        // Kiểm tra riêng charset của PrintStream stderr.
        System.err.print(SAMPLE);
        System.err.flush();
    }

    private static void capture() throws IOException {
        // Đọc raw bytes từ stdin, không dùng Reader hoặc default charset.
        byte[] received = System.in.readAllBytes();
        byte[] expected = SAMPLE.getBytes(StandardCharsets.UTF_8);

        writeAsciiLine("BYTE_LENGTH=" + received.length);
        writeAsciiLine("HEX="
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(received));
        writeAsciiLine("MATCH_EXPECTED_UTF8="
                + Arrays.equals(received, expected));

        try {
            String decoded = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(received))
                    .toString();

            writeAsciiLine("UTF8_DECODE=PASS");
            writeAsciiLine("CODE_POINTS=" + codePoints(decoded));
        } catch (CharacterCodingException malformed) {
            writeAsciiLine("UTF8_DECODE=REJECTED");
            writeAsciiLine("ERROR=" + malformed.getClass().getSimpleName());
        }
    }

    private static String codePoints(String value) {
        StringBuilder result = new StringBuilder();
        value.codePoints().forEach(cp -> {
            if (result.length() > 0) result.append(' ');
            result.append(String.format(Locale.ROOT, "U+%04X", cp));
        });
        return result.toString();
    }

    private static void writeAsciiLine(String value) throws IOException {
        System.out.write(value.getBytes(StandardCharsets.US_ASCII));
        System.out.write('\n');
        System.out.flush();
    }
}
```

Biên dịch trên JDK 18 hoặc mới hơn:

```bash
javac -encoding UTF-8 StdoutTransportProbe.java
```

`-encoding UTF-8` xác định charset của file mã nguồn khi biên dịch. Điều này tách vấn đề encoding source code khỏi vấn đề stdout lúc chương trình chạy.

## 5. Kiểm tra đầu ra trực tiếp trên terminal

Trước tiên, xem các charset mà JVM và stream đang sử dụng:

```bash
java StdoutTransportProbe --info
```

Sau đó ghi chuỗi mẫu trực tiếp ra terminal:

```bash
java StdoutTransportProbe --text
```

So sánh với chế độ gửi byte UTF-8 trực tiếp:

```bash
java StdoutTransportProbe --raw-utf8
```

Quan sát:

- Nếu `--text` và `--raw-utf8` hiển thị giống nhau, đó là dấu hiệu tốt nhưng chưa chứng minh font có thể dựng mọi ký tự.
- Nếu hai chế độ hiển thị khác nhau, so sánh `STDOUT_CHARSET`, charset của console và code page/locale của terminal.
- Nếu chữ có dấu hiển thị sai nhưng byte sau redirect đúng UTF-8, vấn đề có thể ở consumer hoặc font.
- Nếu byte của `--text` không giống UTF-8 kỳ vọng nhưng `--raw-utf8` đúng, `PrintStream` đang mã hóa theo charset khác UTF-8 hoặc có lớp chuyển đổi ở giữa.

Trên Windows, có thể ghi nhận code page trong Command Prompt:

```cmd
chcp
```

Trên Linux, xem locale:

```bash
locale
locale charmap
```

Không thay code page hoặc locale trước khi lưu lại kết quả ban đầu. Khi chẩn đoán, cần giữ được cấu hình và byte đã quan sát để so sánh.

## 6. Chuyển hướng stdout ra tệp và kiểm tra byte thực tế

### 6.1. Linux

Chuyển hướng chế độ `--text` và `--raw-utf8` thành hai file riêng:

```bash
java StdoutTransportProbe --text > stdout-text.bin
java StdoutTransportProbe --raw-utf8 > stdout-raw-utf8.bin

xxd -g 1 stdout-text.bin
xxd -g 1 stdout-raw-utf8.bin
```

Hoặc dùng:

```bash
od -An -tx1 -c stdout-text.bin
od -An -tx1 -c stdout-raw-utf8.bin
```

Byte UTF-8 kỳ vọng của phần chuỗi mẫu bắt đầu như sau:

```text
ASCII|Tiếng Việt|café|€|🚀
41 53 43 49 49 7c 54 69 e1 ba bf 6e 67 20 56 69 e1 bb 87 74 ...
```

Dùng `xxd` hoặc `od` để xem byte; không dựa vào cột ký tự bên phải của hex viewer nếu terminal cũng có thể hiển thị sai.

### 6.2. Windows Command Prompt

Trong `cmd.exe`, chuyển hướng stdout của native process trực tiếp ra file:

```cmd
java StdoutTransportProbe --text > stdout-text.bin
java StdoutTransportProbe --raw-utf8 > stdout-raw-utf8.bin
```

`cmd.exe` chuyển byte stdout vào file. Để xác minh byte, dùng `Format-Hex` hoặc một hex viewer. Không dùng `type`, `Get-Content` hay mở bằng text editor làm bằng chứng byte nguyên gốc, vì các công cụ hiển thị văn bản phải giải mã byte theo một quy tắc nào đó.

Chạy các lệnh sau trong PowerShell để xem byte của hai file:

```powershell
Format-Hex -Path .\stdout-text.bin
Format-Hex -Path .\stdout-raw-utf8.bin
```

### 6.3. PowerShell và khác biệt phiên bản

PowerShell có mô hình xử lý native command khác với shell POSIX và `cmd.exe`:

- Windows PowerShell 5.1 xử lý nhiều thao tác redirect/pipeline theo mô hình văn bản; toán tử `>` không phải lựa chọn đáng tin cậy để lưu raw byte stdout của native process.
- PowerShell 7.4 trở lên hỗ trợ giữ byte stream khi redirect output của native command ra file và khi nối native command với native command.
- Nếu chưa xác định phiên bản PowerShell hoặc cần phép đo byte nhất quán, dùng `cmd.exe /d /c` cho redirect/pipeline native, hoặc chạy trong shell phù hợp.

Ví dụ gọi `cmd.exe` từ PowerShell:

```powershell
cmd.exe /d /c "java StdoutTransportProbe --raw-utf8 > stdout-raw-utf8.bin"
Format-Hex -Path .\stdout-raw-utf8.bin
```

Đừng nhầm `Format-Hex` với `Get-Content`: `Format-Hex` đọc và trình bày byte; `Get-Content` đọc nội dung theo quy tắc văn bản.

## 7. Kiểm tra pipe giữa hai tiến trình Java

Pipe là cách xác minh byte tại ranh giới tiến trình. Tiến trình thứ nhất chỉ ghi payload; tiến trình thứ hai đọc `System.in` bằng `readAllBytes()` và in byte hex.

### 7.1. Linux hoặc macOS

Chạy hai chế độ:

```bash
java StdoutTransportProbe --text | java StdoutTransportProbe --capture
java StdoutTransportProbe --raw-utf8 | java StdoutTransportProbe --capture
```

Dòng `MATCH_EXPECTED_UTF8=true` cho biết byte nhận được giống chính xác byte UTF-8 kỳ vọng của chuỗi mẫu. `UTF8_DECODE=PASS` chỉ xác nhận byte giải mã được theo UTF-8; byte vẫn có thể hợp lệ nhưng mang nội dung khác, vì vậy cần kiểm tra thêm `MATCH_EXPECTED_UTF8`.

Nếu dùng Bash và muốn phát hiện cả lỗi ở producer hoặc consumer, bật `pipefail` trước khi chạy pipeline:

```bash
set -o pipefail
java StdoutTransportProbe --raw-utf8 | java StdoutTransportProbe --capture
```

### 7.2. Windows Command Prompt

Dùng native pipe của `cmd.exe`:

```cmd
java StdoutTransportProbe --text | java StdoutTransportProbe --capture
java StdoutTransportProbe --raw-utf8 | java StdoutTransportProbe --capture
```

Nếu chạy từ PowerShell, gọi `cmd.exe` để toàn bộ pipe được xử lý bởi Command Prompt:

```powershell
cmd.exe /d /c "java StdoutTransportProbe --raw-utf8 | java StdoutTransportProbe --capture"
```

Với PowerShell 7.4+, native-to-native pipeline có thể giữ byte stream. Với phiên bản cũ, dữ liệu native có thể được giải mã thành chuỗi PowerShell rồi mã hóa lại khi chuyển cho lệnh kế tiếp. Điều đó có thể thay đổi byte và làm phép thử không còn đo riêng Java stdout.

### 7.3. Diễn giải kết quả của pipe

| Kết quả | Ý nghĩa |
| --- | --- |
| `MATCH_EXPECTED_UTF8=true`, `UTF8_DECODE=PASS` | Byte đến consumer đúng như payload UTF-8 mẫu. |
| `MATCH_EXPECTED_UTF8=false`, `UTF8_DECODE=PASS` | Byte vẫn là UTF-8 hợp lệ nhưng nội dung/encoding khác kỳ vọng. |
| `UTF8_DECODE=REJECTED` | Byte nhận được có chuỗi không hợp lệ theo UTF-8. |
| `--raw-utf8` đúng, `--text` sai | Cần kiểm tra charset của `PrintStream` và cách shell truyền native bytes. |
| Cả hai đều sai | Kiểm tra source, executable, shell trung gian hoặc consumer; không kết luận font là nguyên nhân từ phép thử pipe. |

## 8. Phân biệt stdout, stderr và các lớp chuyển đổi

`System.out` và `System.err` là hai `PrintStream` riêng, có thể có charset riêng. Khi kiểm tra byte stdout, đừng gộp stderr vào stdout bằng `2>&1` vì thông báo lỗi hoặc cảnh báo có thể chen vào payload. Nếu cần kiểm tra stderr, chuyển hướng riêng:

```bash
java StdoutTransportProbe --stderr-text 2> stderr-text.bin
```

Trong `cmd.exe`:

```cmd
java StdoutTransportProbe --stderr-text 2> stderr-text.bin
```

Trên PowerShell, có thể xem byte của file bằng `Format-Hex -Path .\stderr-text.bin`.

Một số lớp khác cũng có thể ảnh hưởng dữ liệu:

- **Terminal emulator:** giải mã byte và dựng ký tự.
- **Shell:** có thể truyền byte nguyên vẹn hoặc giải mã rồi tạo lại chuỗi, tùy loại shell, phiên bản và loại pipeline.
- **IDE/test runner:** có thể nhận stdout qua một lớp console riêng.
- **SSH/container/log collector:** có thể có decoder, transport hoặc formatter riêng.
- **Font và text shaping:** quyết định glyph có được vẽ đúng sau khi ký tự đã được giải mã.

Nếu file redirect và pipe đều có byte đúng, nhưng terminal hiển thị sai, hãy kiểm tra terminal decoder và font. Nếu file đã chứa byte sai, hãy kiểm tra charset của `PrintStream` hoặc bước tạo payload trước khi sửa terminal.

## 9. Quy trình chẩn đoán theo bằng chứng

1. **Ghi lại charset của JVM và stream:** chạy `--info`, lưu `DEFAULT_CHARSET`, `STDOUT_CHARSET`, `STDERR_CHARSET`, `CONSOLE_CHARSET`.
2. **Thử đầu ra trực tiếp:** so sánh `--text` và `--raw-utf8`; ghi nhận glyph nào sai.
3. **Chuyển hướng ra file:** tạo hai file riêng, xem byte bằng `Format-Hex`, `xxd` hoặc `od`.
4. **Truyền qua pipe:** dùng `--capture` để đọc byte tại đầu nhận, kiểm tra cả hex, strict UTF-8 decode và so sánh với payload chuẩn.
5. **Xác định shell:** trên Windows kiểm tra đang dùng CMD, Windows PowerShell 5.1 hay PowerShell 7.4+; trên Linux kiểm tra shell và locale.
6. **Tách stderr:** không gộp log lỗi vào payload khi cần xác minh byte chính xác.
7. **Chỉ kiểm tra font sau cùng:** nếu code point và byte đều đúng nhưng glyph hiển thị sai, xem font fallback và khả năng dựng combining mark/emoji.

Sơ đồ quyết định:

```text
Terminal hiển thị sai?
       |
       v
File redirect có byte UTF-8 đúng?
   |-- Không --> Kiểm tra PrintStream/source encoding.
   |
   +-- Có
        |
        v
Pipe capture có byte đúng?
   |-- Không --> Kiểm tra shell hoặc lớp trung gian.
   |
   +-- Có
        |
        v
Code point sau decode có đúng?
   |-- Không --> Kiểm tra decoder/charset của consumer.
   |
   +-- Có
        |
        v
Glyph vẫn sai?
   |-- Có --> Kiểm tra terminal, font và text shaping.
   +-- Không --> Đường đi dữ liệu đã được xác minh.
```

## 10. Bài thực hành và tiêu chí hoàn thành

1. Biên dịch `StdoutTransportProbe` với `javac -encoding UTF-8`.
2. Chạy `--info` và ghi lại default charset, charset stdout/stderr và charset console nếu có.
3. Chạy `--text` và `--raw-utf8` trực tiếp trên terminal; mô tả khác biệt nếu có.
4. Chuyển hướng hai chế độ ra file riêng và kiểm tra byte bằng `Format-Hex` trên Windows hoặc `xxd`/`od` trên Linux.
5. Pipe cả hai chế độ vào `--capture`. So sánh `MATCH_EXPECTED_UTF8`, `UTF8_DECODE` và `CODE_POINTS`.
6. Trên Windows, thực hiện phép thử raw byte trong `cmd.exe`; nếu thử PowerShell, ghi rõ phiên bản và so sánh với CMD.
7. Chạy `--stderr-text` với redirect `2>` và so byte file với charset `STDERR_CHARSET`; giải thích vì sao trộn stderr vào stdout làm hỏng phép so sánh payload.
8. Nếu terminal hiển thị sai nhưng file và pipe đều có byte đúng, thử terminal/font khác và kiểm tra glyph fallback.

**Tiêu chí hoàn thành:** bạn có thể phân biệt charset của JVM với charset của `PrintStream`; xác minh byte stdout qua terminal, file redirect và native pipe; nhận biết khi shell PowerShell chuyển đổi native output; và xác định lỗi thuộc producer, shell/consumer hay tầng font. Đây là kỹ năng vẫn áp dụng trên JDK hiện đại, đặc biệt khi UTF-8 mặc định của Java 18 giao tiếp với công cụ và môi trường bên ngoài.

### Tài liệu tham khảo

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset của Java 18+ và ngoại lệ liên quan console.
- [Java SE PrintStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/PrintStream.html): `charset()` và cách stream mã hóa ký tự.
- [Java SE Console](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html): charset của console.
- [PowerShell 7.4 — native command byte stream redirection](https://learn.microsoft.com/en-us/powershell/scripting/whats-new/what's-new-in-powershell-74): thay đổi giữ byte stream khi redirect native output.
- [Windows Format-Hex](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/format-hex): hiển thị byte của file dưới dạng hex.
