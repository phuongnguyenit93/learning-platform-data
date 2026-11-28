# Xử lý ký tự điều khiển terminal trong dữ liệu không đáng tin

Command line thường hiển thị dữ liệu lấy từ file, database, API hoặc người dùng khác. Một trường tên, mô tả hay thông báo lỗi có thể chứa ký tự điều khiển terminal. Nếu in nguyên văn chuỗi đó, terminal có thể di chuyển con trỏ, xóa nội dung, đổi tiêu đề cửa sổ, tạo hyperlink hoặc thực hiện hành động đặc thù của terminal emulator. Dữ liệu cũng có thể làm giả nhiều dòng log bằng ký tự xuống dòng hoặc khiến tên file hiển thị sai thứ tự bằng ký tự điều khiển hướng chữ.

Spring Shell sử dụng terminal và các thư viện như JLine để đọc và hiển thị nội dung. Các thư viện này không biến mọi chuỗi nghiệp vụ thành văn bản an toàn tự động. Ứng dụng phải xử lý dữ liệu không đáng tin tại điểm hiển thị: escape hoặc loại bỏ ký tự điều khiển trước khi đưa chuỗi vào output, bảng, thông báo lỗi, log hay view. Dữ liệu gốc vẫn được giữ nguyên trong domain và storage.

## Vì sao dữ liệu văn bản có thể điều khiển terminal?

Terminal không chỉ hiển thị ký tự in được. Nó còn nhận các byte và code point có ý nghĩa điều khiển. Một số ký tự có thể xuất hiện trong dữ liệu mà mắt thường không dễ nhận ra:

| Ký tự | Tác động thường gặp |
| --- | --- |
| `ESC` (`U+001B`) | Bắt đầu chuỗi điều khiển ANSI/VT |
| `CR` (`U+000D`) | Đưa con trỏ về đầu dòng hiện tại |
| `LF` (`U+000A`) | Chuyển sang dòng mới; có thể làm giả dòng log |
| `BS` (`U+0008`) | Lùi con trỏ một vị trí, có thể ghi đè ký tự |
| `BEL` (`U+0007`) | Phát tín hiệu chuông hoặc thông báo |
| `TAB` (`U+0009`) | Di chuyển đến vị trí tab tiếp theo |
| `DEL` (`U+007F`) | Ký tự điều khiển xóa trong một số ngữ cảnh |
| C1 controls (`U+0080`–`U+009F`) | Có thể biểu diễn CSI, OSC và các lệnh terminal khác |
| Bidi controls | Thay đổi thứ tự hiển thị trái/phải của văn bản |

Các terminal hiện đại thường hiểu chuỗi escape ANSI/VT. Một chuỗi bắt đầu bằng `ESC [` thường là CSI (Control Sequence Introducer), dùng để điều khiển màu, vị trí con trỏ, xóa dòng hoặc thay đổi thuộc tính hiển thị. `ESC ]` bắt đầu OSC (Operating System Command), có thể điều khiển tiêu đề terminal hoặc hyperlink. Một số terminal emulator còn hỗ trợ OSC 52 để ghi clipboard, OSC 8 để tạo hyperlink, và các chuỗi DCS/APC/PM khác.

Ví dụ dữ liệu có thể chứa chuỗi xóa màn hình:

```text
\u001B[2J\u001B[H
```

Nếu hai ký tự `\u001B` ở trên thực sự là ESC (`U+001B`) trong chuỗi được in, terminal có thể xóa màn hình rồi đưa con trỏ về góc trên bên trái. Trong file văn bản hoặc log, chuỗi điều khiển thường không hiện ra như chữ thông thường nên người đọc khó nhận biết nguồn gốc thay đổi.

## Những kiểu tấn công thường gặp

### Xóa hoặc thay đổi nội dung terminal

Kẻ tấn công đưa `ESC [ 2 J` vào trường tên hoặc thông báo. Khi command in dữ liệu đó, terminal có thể xóa màn hình. Các chuỗi CSI khác có thể di chuyển con trỏ, xóa một phần dòng hoặc thay đổi màu khiến nội dung tiếp theo trông như đến từ nguồn khác.

### Giả mạo log bằng CR/LF

Nếu ứng dụng ghi một giá trị không đáng tin vào log mà không xử lý CR/LF, một giá trị có thể tạo thêm dòng trông như một sự kiện độc lập:

```text
2026-11-26 10:00:00 INFO Login failed for user=alice
2026-11-26 10:00:01 INFO Login succeeded for user=admin
```

Dòng thứ hai có thể là nội dung do người dùng gửi trong trường username, không phải sự kiện xác thực thật. Đây là dạng log forging/log injection. Việc dùng structured logging giúp giữ trường dữ liệu tách biệt, nhưng vẫn cần bảo đảm encoder và sink không cho phép CR/LF hoặc ký tự điều khiển phá vỡ định dạng.

### Hyperlink hoặc hành động phụ của terminal

OSC 8 có thể tạo hyperlink trong terminal hỗ trợ. OSC 52 có thể yêu cầu terminal ghi dữ liệu vào clipboard, tùy emulator và cấu hình bảo vệ. Chuỗi điều khiển đổi tiêu đề terminal cũng có thể làm người dùng hiểu nhầm cửa sổ đang kết nối tới máy chủ hoặc môi trường nào.

Không ghép trực tiếp URL, tiêu đề hoặc nhãn do người dùng cung cấp vào chuỗi OSC. Nếu ứng dụng cần hyperlink, hãy tạo nó bằng API có cấu trúc, giới hạn scheme như `https`, kiểm tra host theo chính sách và escape phần văn bản hiển thị.

### Đánh lừa thứ tự hiển thị bằng Unicode bidi controls

Unicode có các ký tự điều khiển hướng chữ như Right-to-Left Override (`U+202E`) và các isolate controls. Chúng hữu ích cho văn bản đa ngôn ngữ, nhưng trong tên file, log, mã định danh hoặc tên gói, chúng có thể khiến phần mở rộng và thứ tự ký tự hiển thị khác với thứ tự lưu trữ.

Ví dụ tên hiển thị có thể chứa `U+202E` trước phần mở rộng. Người xem có thể đọc tên theo thứ tự gây hiểu nhầm, trong khi ứng dụng xử lý chuỗi theo thứ tự code point thực tế. Với định danh và trường dùng để ra quyết định bảo mật, hãy hiển thị bidi controls dưới dạng escape để người xem nhận biết chúng.

## Nguyên tắc xử lý an toàn

1. Xác định ranh giới output. Mọi chuỗi đến từ file, database, API, biến môi trường hoặc người dùng đều là dữ liệu không đáng tin khi được đưa ra terminal.
2. Escape ký tự điều khiển trước khi hiển thị. Với dữ liệu đơn dòng, escape C0/C1 controls, CR/LF, ESC, tab, bidi controls và các Unicode line separator.
3. Giữ dữ liệu gốc. Không ghi đè tên, mô tả hoặc nội dung trong database chỉ vì cách hiển thị terminal cần escape.
4. Không tự ghép mã ANSI từ dữ liệu. Màu sắc và style phải đến từ code tin cậy hoặc API có cấu trúc.
5. Dùng encoder riêng cho từng output context. Terminal, log, HTML và CSV có quy tắc escaping khác nhau; escaping cho một context không bảo vệ context khác.
6. Giữ log một sự kiện trên một dòng nếu định dạng log yêu cầu. Chuẩn hóa hoặc escape CR/LF trong trường dữ liệu.
7. Kiểm thử các chuỗi điều khiển thật, bao gồm C1 và OSC, chứ không chỉ kiểm tra chuỗi màu `ESC[...m`.

Không dùng một regex chỉ xóa chuỗi màu ANSI SGR làm biện pháp bảo vệ đầy đủ. Regex kiểu `ESC\[[0-9;]*m` chỉ nhận diện một tập con chuỗi điều khiển màu, bỏ sót OSC, DCS, cursor movement, CR/LF, C1 controls và Unicode bidi controls.

## Tạo helper escape dữ liệu đơn dòng

Với trường dữ liệu hiển thị trong một dòng, một chính sách dễ kiểm tra là thay các ký tự điều khiển bằng biểu diễn nhìn thấy được. Ví dụ `ESC` thành `\x1B`, CR thành `\r`, LF thành `\n`, và bidi override thành `\u202E`.

```java
import java.util.Locale;
import java.util.Objects;

public final class TerminalText {

    private TerminalText() {
    }

    public static String escapeForTerminal(String value) {
        Objects.requireNonNull(value, "value");

        StringBuilder safe = new StringBuilder(value.length());
        value.codePoints().forEach(codePoint -> {
            if (Character.isISOControl(codePoint)
                    || isBidiControl(codePoint)
                    || codePoint == 0x2028
                    || codePoint == 0x2029
                    || Character.getType(codePoint) == Character.SURROGATE) {
                appendEscape(safe, codePoint);
            }
            else {
                safe.appendCodePoint(codePoint);
            }
        });
        return safe.toString();
    }

    private static boolean isBidiControl(int codePoint) {
        return codePoint == 0x061C
                || codePoint == 0x200E
                || codePoint == 0x200F
                || (codePoint >= 0x202A && codePoint <= 0x202E)
                || (codePoint >= 0x2066 && codePoint <= 0x206F);
    }

    private static void appendEscape(StringBuilder target, int codePoint) {
        switch (codePoint) {
            case '\n' -> target.append("\\n");
            case '\r' -> target.append("\\r");
            case '\t' -> target.append("\\t");
            case '\b' -> target.append("\\b");
            case '\f' -> target.append("\\f");
            default -> {
                String pattern = codePoint <= 0xFF
                        ? "\\x%02X"
                        : codePoint <= 0xFFFF ? "\\u%04X" : "\\u{%X}";
                target.append(String.format(Locale.ROOT, pattern, codePoint));
            }
        }
    }
}
```

Helper trên xử lý theo Unicode code point thay vì duyệt từng `char`, nên có thể nhận diện cả ký tự ngoài BMP. `Character.isISOControl(...)` bao phủ C0 và C1 controls. Hàm `isBidiControl(...)` nhận diện các ký tự hướng chữ thường gây nhầm lẫn trong định danh. `U+2028` và `U+2029` được escape để không tạo ranh giới dòng hoặc đoạn trong output.

Đây là chính sách dành cho dữ liệu hiển thị một dòng. Nếu ứng dụng cần trình bày văn bản nhiều dòng, hãy xây dựng renderer tách dòng có chủ đích: chuẩn hóa line ending, escape từng dòng và thêm prefix/indentation tin cậy. Không giữ nguyên CR/LF tùy ý trong trường log hoặc một ô bảng.

## Dùng helper ở ranh giới hiển thị Spring Shell

Ví dụ command hiển thị tên khách hàng lấy từ dữ liệu bên ngoài:

```java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @ShellMethod(key = "customer show", value = "Xem thông tin khách hàng")
    public String show(String code) {
        Customer customer = customerService.findByCode(code);

        return "Mã: " + TerminalText.escapeForTerminal(customer.code())
                + "\nTên: " + TerminalText.escapeForTerminal(customer.name());
    }
}
```

Nếu command trả về nhiều dòng do ứng dụng chủ động định dạng, dấu xuống dòng giữa các nhãn là cấu trúc output tin cậy. Dữ liệu của từng trường đã được escape nên CR/LF bên trong tên không thể chèn thêm dòng giả.

Áp dụng cùng quy tắc cho:

- Tên file và đường dẫn do người dùng cung cấp.
- Tên người dùng, tên khách hàng và nhãn từ database.
- Nội dung lỗi từ dịch vụ bên ngoài.
- Dữ liệu trong bảng, danh sách, `ListView` và `AttributedString`.
- Nội dung hiển thị trong progress view hoặc status bar.
- Dữ liệu đưa vào terminal log hoặc thông báo debug.

Nếu dùng JLine `AttributedString` hoặc builder để tô màu, hãy escape nội dung trước khi đưa vào phần text. Style metadata của JLine giúp ứng dụng kiểm soát màu và thuộc tính hiển thị; nó không tự làm cho byte ESC có trong text trở nên vô hại. Không đưa chuỗi ANSI do người dùng cung cấp vào một builder rồi kỳ vọng JLine tự phân biệt phần nào là dữ liệu và phần nào là lệnh terminal.

## Không làm mất dữ liệu nghiệp vụ

Escape là bước trình bày, không phải bước chuẩn hóa dữ liệu lưu trữ. Ví dụ, nếu tên gốc có CR/LF hoặc bidi control, có thể cần giữ nguyên giá trị để phục vụ điều tra, đối chiếu hoặc xử lý nghiệp vụ. Hãy tách rõ:

```java
String rawName = customer.name();
String terminalName = TerminalText.escapeForTerminal(rawName);

// Lưu và so sánh dùng rawName theo quy tắc nghiệp vụ.
// Chỉ dùng terminalName khi hiển thị ra terminal.
```

Không dùng chuỗi đã escape để làm khóa tìm kiếm, kiểm tra chữ ký, xác thực quyền hoặc ghi ngược vào database. Nếu ứng dụng muốn từ chối ký tự điều khiển ngay từ đầu vào, đó là một validation rule riêng; hãy áp dụng theo yêu cầu domain và không nhầm với escaping output.

## Xử lý log và thông báo lỗi

Log cần giữ được ranh giới giữa các sự kiện. Nếu ghi dữ liệu không đáng tin vào log dạng văn bản, hãy escape CR/LF và các control characters. Với structured logging, truyền dữ liệu vào field riêng thay vì nối chuỗi thành một dòng tự tạo; đồng thời kiểm tra encoder của log appender để bảo đảm ký tự điều khiển được mã hóa an toàn.

Ví dụ:

```java
log.warn("Rejected customer name='{}'",
        TerminalText.escapeForTerminal(untrustedName));
```

Trong môi trường production, log nên chứa đủ thông tin để điều tra nhưng không ghi mật khẩu, token, session ID hoặc dữ liệu cá nhân không cần thiết. Escape không thay thế việc giảm thiểu dữ liệu nhạy cảm.

Với exception từ hệ thống ngoài, tránh in nguyên `exception.getMessage()` nếu thông điệp có thể chứa dữ liệu do người dùng kiểm soát. Ghi stack trace vào log có kiểm soát, còn thông báo hiển thị nên được làm sạch và giới hạn độ dài.

## Bảo vệ hyperlink và style terminal

Nếu muốn hiển thị màu hoặc hyperlink, hãy tạo style từ code tin cậy:

```java
import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStyle;

AttributedString safeLabel = new AttributedString(
        TerminalText.escapeForTerminal(untrustedLabel),
        AttributedStyle.DEFAULT.foreground(AttributedStyle.CYAN));
```

Ở ví dụ này, màu cyan do ứng dụng chọn; phần text không đáng tin đã được escape. Nếu xây dựng hyperlink, hãy kiểm tra scheme và host trước, mã hóa URI đúng cách và dùng API hyperlink có cấu trúc của terminal library nếu phiên bản đang dùng hỗ trợ. Không nối trực tiếp dữ liệu vào chuỗi OSC 8.

Đặc biệt không phát các chuỗi OSC 52 hoặc chuỗi terminal khác từ dữ liệu bên ngoài. Không cần thiết phải tắt mọi tính năng terminal; điều quan trọng là chỉ phát lệnh terminal từ logic tin cậy của ứng dụng, không từ chuỗi dữ liệu.

## Kiểm thử chuỗi điều khiển

Kiểm thử helper cần xác nhận rằng output không còn control code point nguy hiểm và biểu diễn escape vẫn đọc được:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class TerminalTextTests {

    @Test
    void escapesCarriageReturnAndLineFeed() {
        assertEquals("alice\\r\\nadmin",
                TerminalText.escapeForTerminal("alice\r\nadmin"));
    }

    @Test
    void escapesAnsiEscapeCharacter() {
        String escape = String.valueOf((char) 0x001B);
        assertEquals("\\x1B[2J",
                TerminalText.escapeForTerminal(escape + "[2J"));
    }

    @Test
    void escapesC1ControlCharacter() {
        String c1 = String.valueOf((char) 0x009B);
        assertEquals("\\x9B31m",
                TerminalText.escapeForTerminal(c1 + "31m"));
    }

    @Test
    void escapesBidirectionalOverride() {
        String bidiOverride = String.valueOf((char) 0x202E);
        assertEquals("report\\u202Egpj.exe",
                TerminalText.escapeForTerminal("report" + bidiOverride + "gpj.exe"));
    }

    @Test
    void leavesOrdinaryUnicodeTextReadable() {
        assertEquals("Nguyễn Văn An 😊",
                TerminalText.escapeForTerminal("Nguyễn Văn An 😊"));
    }

    @Test
    void rejectsNullInput() {
        assertThrows(NullPointerException.class,
                () -> TerminalText.escapeForTerminal(null));
    }
}
```

Ngoài unit test, nên có integration test chạy command với dữ liệu chứa ESC, OSC, CR/LF và bidi controls. Kiểm tra chuỗi được ghi ra terminal test harness không chứa code point điều khiển gốc. Có thể kiểm tra thêm rằng output vẫn chứa phần văn bản còn lại sau khi escape.

Danh sách tình huống nên bao gồm:

- CSI xóa màn hình, di chuyển con trỏ và đổi màu.
- OSC đổi tiêu đề, hyperlink và clipboard.
- C1 CSI/OSC và ký tự ST.
- CR, LF, CRLF, TAB, BS, BEL, NUL và DEL.
- Bidi override, isolate và direction marks.
- Chuỗi rỗng, null theo hợp đồng của helper và chuỗi rất dài.
- Unicode ngoài BMP và surrogate không hợp lệ.
- Output trong bảng, exception, log, `AttributedString` và progress/status view.

Kiểm thử bằng cách nhìn terminal bằng mắt là chưa đủ. Một chuỗi điều khiển có thể chỉ tác động trên một số terminal emulator hoặc cấu hình cụ thể. Unit test kiểm tra code point output giúp xác nhận sanitizer hoạt động độc lập với emulator.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| In trực tiếp tên hoặc mô tả lấy từ bên ngoài | Dữ liệu có thể điều khiển terminal | Escape tại điểm hiển thị |
| Chỉ xóa `ESC[` | Bỏ sót OSC, DCS, C1, CR/LF và bidi controls | Xử lý toàn bộ C0/C1 và nhóm Unicode cần bảo vệ |
| Chỉ loại bỏ mã màu ANSI | Chuỗi cursor movement hoặc OSC vẫn hoạt động | Không xem strip màu là sanitizer đầy đủ |
| Giữ nguyên CR/LF trong log | Kẻ tấn công có thể giả mạo dòng sự kiện | Escape hoặc encode line ending theo log format |
| Escape dữ liệu ngay khi lưu | Làm thay đổi giá trị nghiệp vụ và gây double-escape | Giữ raw value; escape riêng ở output boundary |
| Ghép chuỗi OSC từ input | Có thể tạo hyperlink, đổi title hoặc lệnh terminal ngoài ý muốn | Dùng API có cấu trúc và allowlist scheme/host |
| Nghĩ `AttributedString` tự lọc ESC | ESC trong text vẫn có thể được terminal nhận | Sanitize text trước khi tạo attributed content |
| Chỉ kiểm tra bằng terminal hiện tại | Bỏ sót hành vi khác giữa emulator | Kiểm thử code point và nhiều output context |
| Escape mọi Unicode format character một cách mù quáng | Có thể làm hỏng chữ viết hoặc emoji hợp lệ | Áp dụng policy theo loại trường; ưu tiên escape bidi controls trong định danh/log |
| Ghi nguyên exception message | Log hoặc terminal có thể bị chèn dòng và lộ dữ liệu | Làm sạch message hiển thị, kiểm soát nội dung log |

## Quy trình bảo vệ output terminal

1. Liệt kê mọi nguồn dữ liệu không đáng tin có thể xuất hiện trong terminal, bảng, log hoặc view.
2. Xác định output context: một dòng, nhiều dòng có cấu trúc, log hay attributed text.
3. Dùng sanitizer chuyên cho terminal để escape C0/C1 controls, CR/LF, ESC, bidi controls và Unicode line separator.
4. Chỉ thêm màu, cursor movement hoặc hyperlink từ logic tin cậy của ứng dụng.
5. Giữ nguyên dữ liệu gốc trong domain/storage và chỉ dùng chuỗi đã escape cho hiển thị.
6. Kiểm thử CSI, OSC, C1, CR/LF, bidi controls và các trường hợp Unicode.
7. Rà soát các điểm output mới khi thêm command hoặc tích hợp dữ liệu ngoài.

Terminal control injection xảy ra khi dữ liệu được coi như văn bản nhưng terminal diễn giải nó thành lệnh. Việc escape tại ranh giới hiển thị giúp ngăn dữ liệu bên ngoài thay đổi màn hình hoặc giả mạo log, đồng thời giữ nguyên giá trị nghiệp vụ để ứng dụng xử lý đúng.

## Tài liệu tham khảo

- [CWE-150: Improper Neutralization of Escape, Meta, or Control Sequences](https://cwe.mitre.org/data/definitions/150.html)
- [CWE-117: Improper Output Neutralization for Logs](https://cwe.mitre.org/data/definitions/117.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [XTerm Control Sequences](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html)
- [Unicode Bidirectional Algorithm – UAX #9](https://www.unicode.org/reports/tr9/)
- [Java Character API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html)
