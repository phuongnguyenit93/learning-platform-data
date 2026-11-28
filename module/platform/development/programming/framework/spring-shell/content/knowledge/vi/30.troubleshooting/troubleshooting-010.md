# Bảng, Unicode hoặc màu sắc hiển thị sai

## 1. Nhận diện đúng lớp gây lỗi

Khi output của Spring Shell bị lệch cột, mất dấu tiếng Việt, hiện ký tự hình vuông hoặc in mã màu thô như `\u001B[31m`, nguyên nhân có thể nằm ở nhiều lớp khác nhau:

1. **Dữ liệu:** chuỗi đã sai trước khi được đưa ra terminal, ví dụ đọc file bằng charset không đúng hoặc dữ liệu đã bị thay thế bằng ký tự `�`.
2. **Mã hóa:** JVM, JLine, pipe hoặc terminal không thống nhất charset khi ghi và đọc dữ liệu.
3. **Font và Unicode:** font không có glyph cần thiết hoặc terminal hiển thị ký tự có độ rộng khác với cách chương trình tính toán.
4. **Kích thước terminal:** bảng được render theo chiều rộng khác với số cột thực tế hoặc nội dung dài không được wrap đúng.
5. **Terminal capability:** JLine nhận diện terminal là `dumb`, không phát hiện màu hoặc không hỗ trợ ANSI/Unicode box drawing.
6. **Theme và style:** Spring Shell phát ra màu hoặc ký hiệu trang trí không phù hợp với terminal, pipe hay môi trường test.

Đừng sửa dữ liệu gốc chỉ vì màn hình hiển thị sai. Trước hết hãy xác định chuỗi sai ở trong ứng dụng hay chỉ sai ở bước terminal render.

## 2. Chạy một phép thử tối thiểu

Hãy chạy cùng một command trong ba môi trường: terminal hệ điều hành, terminal tích hợp IDE và output đã redirect vào tệp. Nếu chỉ một môi trường bị lỗi, khả năng cao vấn đề nằm ở terminal, font, encoding hoặc cách redirect của môi trường đó.

Dùng chuỗi thử có tiếng Việt, dấu kết hợp, ký tự CJK, box drawing và emoji:

~~~text
Tiếng Việt: Đặng Thị Hương — kiểm thử tiếng Việt có dấu.
Unicode: é / é / 中文 / 日本語 / 한국어 / 😀
Box drawing: ┌────────┬──────────┐
             │ Mã     │ Trạng thái│
             └────────┴──────────┘
~~~

Hai chuỗi `é` và `é` trông gần giống nhau nhưng có thể có cách biểu diễn Unicode khác nhau: ký tự `é` dựng sẵn hoặc chữ `e` kết hợp dấu sắc. Nếu một chuỗi hiển thị sai còn chuỗi kia đúng, cần kiểm tra chuẩn hóa Unicode và font.

Ghi nhận các dấu hiệu:

- Dấu tiếng Việt thành `?` hoặc `�`: kiểm tra charset và dữ liệu.
- Chữ đúng nhưng đường viền bảng lệch: kiểm tra độ rộng hiển thị và cách tính cột.
- Emoji hoặc ký tự CJK đẩy cột sang phải: kiểm tra độ rộng hai ô và font.
- Ký tự `┌`, `─`, `│` thành ô vuông: font hoặc terminal thiếu glyph.
- Chuỗi `\u001B[` hoặc `[31m` xuất hiện trong output: ANSI escape sequence không được terminal xử lý hoặc đang bị ghi ra tệp.
- Màu biến mất nhưng chữ vẫn đúng: kiểm tra capability, theme và chế độ redirect.

## 3. Kiểm tra terminal mà Spring Shell đang sử dụng

Spring Shell 3.4 dùng JLine để quản lý terminal. Với annotation model mới, lấy terminal qua `CommandContext.getTerminal()`. Có thể tạo một command chẩn đoán ngắn để in loại terminal, kích thước, charset và số màu mà JLine nhận diện.

~~~java
import org.jline.terminal.Terminal;
import org.jline.utils.InfoCmp.Capability;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class DiagnosticsCommands {

    private final Terminal terminal;

    public DiagnosticsCommands(Terminal terminal) {
        this.terminal = terminal;
    }

    @ShellMethod(key = "diagnostics terminal", value = "Hiển thị thông tin terminal")
    public String terminalInfo() {
        Integer colors = terminal.getNumericCapability(Capability.max_colors);

        return "type=" + terminal.getType()
                + ", columns=" + terminal.getColumns()
                + ", rows=" + terminal.getRows()
                + ", encoding=" + terminal.encoding()
                + ", inputEncoding=" + terminal.inputEncoding()
                + ", outputEncoding=" + terminal.outputEncoding()
                + ", maxColors=" + colors;
    }
}
~~~

Ví dụ dùng legacy `@ShellComponent`/`@ShellMethod` của Spring Shell 3.4 và inject `org.jline.terminal.Terminal` do JLine quản lý. Nếu dùng annotation model mới, có thể lấy terminal qua `CommandContext.getTerminal()` và phải kích hoạt đăng ký command theo cấu hình của mô hình đó.

Đọc kết quả theo hướng sau:

- `type=dumb` hoặc loại terminal tối giản: không kỳ vọng cursor control, box drawing hoặc màu nâng cao hoạt động đầy đủ.
- `columns` bằng 0 hoặc có giá trị không hợp lý: terminal không cung cấp kích thước đáng tin cậy; table renderer có thể chọn chiều rộng mặc định hoặc tính sai.
- `outputEncoding` không phải UTF-8 trong khi dữ liệu và terminal đang dùng UTF-8: cần điều tra đường mã hóa output.
- `maxColors` là `null` hoặc nhỏ: JLine không nhận diện được khả năng màu; dùng output đơn sắc hoặc kiểm tra terminal type/provider.

Các giá trị này phản ánh cách JLine nhìn thấy terminal, không chứng minh font đang có glyph hay terminal emulator sẽ render mọi ký tự giống nhau.

## 4. Sửa lỗi tiếng Việt bị mất dấu hoặc thành ký tự lạ

### 4.1. Xác định dữ liệu đã sai ở đâu

So sánh chuỗi tại ba điểm:

1. Giá trị ngay sau khi đọc từ resource, database hoặc file.
2. Giá trị trước khi command trả về hoặc ghi ra terminal.
3. Nội dung xuất hiện trên màn hình hoặc trong file redirect.

Nếu chuỗi đã chứa `�` hoặc `?` ngay tại bước 1, lỗi xảy ra khi đọc hoặc lưu dữ liệu. Đổi terminal sang UTF-8 không thể khôi phục những byte đã bị giải mã sai. Hãy xác định charset thật của nguồn dữ liệu rồi giải mã đúng.

Nếu chuỗi Java vẫn đúng nhưng màn hình sai, kiểm tra `Terminal.outputEncoding()`, encoding của console và font. Nếu redirect ra file đúng nhưng terminal sai, tập trung vào terminal emulator và font. Nếu terminal đúng nhưng file redirect sai, kiểm tra encoding của stream được dùng để redirect hoặc công cụ mở file.

### 4.2. Dùng UTF-8 nhất quán

Với file text do ứng dụng quản lý, chỉ rõ UTF-8 thay vì phụ thuộc charset mặc định của máy:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("input.txt");
Path outputPath = Path.of("output.txt");
String content = Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(outputPath, content, StandardCharsets.UTF_8);
~~~

Đoạn mã trên áp dụng cho file được quy định là UTF-8. Nếu file đầu vào thuộc encoding khác, hãy cấu hình charset đúng với định dạng của file thay vì ép mọi dữ liệu thành UTF-8 một cách mù quáng.

JLine cho phép cấu hình encoding khi tạo terminal bằng `TerminalBuilder.encoding("UTF-8")`, đồng thời có thể đặt encoding riêng cho input và output. Tuy nhiên, Spring Shell đã quản lý terminal của ứng dụng; không tạo terminal thứ hai trong command chỉ để đổi encoding. Hãy kiểm tra cấu hình terminal/provider của ứng dụng và đảm bảo môi trường chạy Java, console và terminal emulator thống nhất.

Với JLine 3, các system property liên quan đến stream có thể dùng khi cấu hình terminal được tạo bởi JLine:

~~~bash
java -Dorg.jline.terminal.stdout.encoding=UTF-8 -jar build-cli.jar
~~~

Tên property và khả năng áp dụng phụ thuộc phiên bản JLine được Spring Shell kéo vào. Xác nhận `outputEncoding()` sau khi chạy; đừng thêm property này nếu terminal đã báo UTF-8 và dữ liệu vẫn lỗi ở font hoặc renderer.

### 4.3. Kiểm tra Windows console

Trên Windows, thử chạy cùng ứng dụng trong Windows Terminal hoặc một terminal hiện đại trước khi kết luận code Java sai. Với một số console host cũ, code page có thể không phải UTF-8. Có thể kiểm tra bằng:

~~~powershell
chcp
~~~

Nếu môi trường cũ đang dùng code page không phù hợp, có thể thử chuyển sang UTF-8 trong phiên hiện tại:

~~~powershell
chcp 65001
java -jar .\build-cli.jar diagnostics terminal
~~~

Lệnh `chcp 65001` thay đổi code page của console hiện tại; nó không sửa dữ liệu đã bị ghi sai và cũng không bổ sung glyph còn thiếu trong font. PowerShell 7 và Windows Terminal thường xử lý Unicode tốt hơn các host cũ, nhưng vẫn cần kiểm tra terminal provider và font thực tế.

## 5. Chuẩn hóa Unicode khi dữ liệu dùng dạng kết hợp

Unicode cho phép một ký tự nhìn thấy được biểu diễn bằng một code point dựng sẵn hoặc nhiều code point kết hợp. Ví dụ `é` có thể là U+00E9 hoặc `e` + U+0301. Hai chuỗi có thể nhìn giống nhau nhưng so sánh bằng `String.equals()` không nhất thiết bằng nhau.

Nếu nghiệp vụ cần chuẩn hóa chuỗi hiển thị hoặc so sánh theo dạng chuẩn, có thể dùng NFC:

~~~java
import java.text.Normalizer;

String displayValue = Normalizer.normalize(input, Normalizer.Form.NFC);
~~~

Chỉ chuẩn hóa ở ranh giới phù hợp. Không tự ý chuẩn hóa khóa, đường dẫn, chữ ký số, token hoặc dữ liệu mà định dạng nguồn yêu cầu giữ nguyên byte/code point. Với dữ liệu người dùng, quy tắc chuẩn hóa phải nhất quán ở nơi lưu, so sánh và hiển thị.

## 6. Phân biệt số ký tự với số cột hiển thị

Một nguyên nhân phổ biến khiến bảng lệch là chương trình dùng `String.length()` để tính số khoảng trắng cần chèn. Độ dài Java đo số UTF-16 code unit, không phải số ô terminal.

| Nội dung | Đặc điểm khi hiển thị |
|---|---|
| `ABC` | Thường chiếm 3 cột. |
| `Đặng` | Có số code unit và độ rộng terminal khác nhau tùy ký tự/font; dấu không nhất thiết chiếm thêm một ô. |
| `中文` | Mỗi ký tự thường chiếm 2 cột terminal. |
| `e` + dấu kết hợp | Có thể gồm nhiều code point nhưng hiển thị như một grapheme. |
| `😀` | Thường chiếm 2 cột. |
| Emoji có skin tone hoặc ZWJ | Có thể gồm nhiều code point nhưng hiển thị như một grapheme cluster. |

Ví dụ sau không căn cột đáng tin cậy với Unicode:

~~~java
String value = "中文";
int padding = 12 - value.length();
String cell = value + " ".repeat(Math.max(0, padding));
~~~

`value.length()` không cho biết số ô mà terminal đã dùng để vẽ chuỗi. JLine có tiện ích tính độ rộng hiển thị như `WCWidth` ở các phiên bản tương ứng. Khi tự viết table renderer, hãy dùng thuật toán width-aware có xét ký tự rộng, combining marks và grapheme; không tự cộng số ký tự UTF-16.

Với Spring Shell `TableBuilder`, để thư viện thực hiện sizing, wrapping và alignment thay vì tự đệm khoảng trắng trong từng cell. Tuy vậy, nếu dữ liệu chứa emoji, CJK, combining marks hoặc terminal font đặc biệt, vẫn phải kiểm tra kết quả trên terminal đích.

## 7. Kiểm tra font và ký tự box drawing

Terminal emulator chỉ có thể vẽ glyph nếu font hiện tại có ký tự tương ứng. Nếu `┌`, `─`, `┬`, `│`, `└` hoặc emoji thành ô vuông, hãy:

1. Chọn font monospace có hỗ trợ Unicode box drawing và ký tự ngôn ngữ đang dùng.
2. Kiểm tra font fallback của terminal emulator.
3. Chạy chuỗi thử ở phần 2 trong terminal khác.
4. Thử bảng dùng viền ASCII để xác định vấn đề chỉ nằm ở glyph trang trí.
5. Tránh dùng emoji làm ký hiệu trạng thái bắt buộc; cung cấp chữ như `OK`, `WARN`, `ERROR`.

Ký tự Unicode không đảm bảo có cùng hình dạng hoặc độ rộng trên mọi font. Emoji còn có thể được render bằng font màu riêng, tạo độ rộng hoặc chiều cao khác với font monospace chính.

## 8. Dùng TableBuilder và chọn border phù hợp

Spring Shell 3.4 có API bảng trong package `org.springframework.shell.table`. `ArrayTableModel` giữ dữ liệu theo hàng; `TableBuilder` cấu hình border và trả về `Table`; `Table.render(width)` tạo chuỗi theo chiều rộng được cung cấp.

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.table.ArrayTableModel;
import org.springframework.shell.table.BorderStyle;
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableBuilder;

@ShellComponent
public class ProjectCommands {

    private final Terminal terminal;

    public ProjectCommands(Terminal terminal) {
        this.terminal = terminal;
    }

    @ShellMethod(key = "project list", value = "Liệt kê project")
    public String list() {
        Object[][] rows = {
                { "ID", "Tên", "Trạng thái" },
                { "P-001", "Dự án kế toán", "Đang chạy" },
                { "P-002", "Cổng thông tin", "Tạm dừng" }
        };

        Table table = new TableBuilder(new ArrayTableModel(rows))
                .addHeaderBorder(BorderStyle.oldschool)
                .build();

        int width = terminal.getColumns() > 0 ? terminal.getColumns() : 80;
        return table.render(width);
    }
}
~~~

Ví dụ dùng `BorderStyle.oldschool`, chỉ dựa trên ký tự ASCII cơ bản. Đây là lựa chọn an toàn khi box drawing Unicode không có trong font hoặc terminal. Nếu môi trường đã hỗ trợ Unicode, có thể đổi thành `BorderStyle.fancy_light` hoặc `BorderStyle.fancy_double`.

Một số kiểu border:

| BorderStyle | Đặc điểm | Dùng khi |
|---|---|---|
| `oldschool` | Ký tự ASCII đơn giản như `+`, `-`, `|` | Cần tương thích terminal cũ hoặc font hạn chế. |
| `fancy_light` | Viền Unicode nét mảnh | Terminal có font hỗ trợ box drawing. |
| `fancy_heavy` | Viền Unicode nét đậm | Terminal hiển thị tốt nét đậm. |
| `fancy_double` | Viền Unicode nét đôi | Muốn phân biệt vùng nhưng cần font phù hợp. |
| `air` | Dùng khoảng trắng để tách cột | Muốn bảng nhẹ, ít ký tự trang trí. |

Nếu đổi `fancy_light` sang `oldschool` mà bảng thẳng hàng, vấn đề có thể nằm ở glyph hoặc độ rộng ký tự. Nếu vẫn lệch, kiểm tra width của terminal, dữ liệu dài, wrapping và thuật toán căn cột.

## 9. Xử lý bảng bị tràn hoặc wrap sai

`TableBuilder` mặc định tìm cách dùng không gian khả dụng, có thể wrap nội dung theo dấu cách. Một chuỗi dài không có dấu cách như URL, hash, token hoặc đường dẫn có thể không wrap như người dùng mong đợi.

Kiểm tra theo thứ tự:

1. Đọc `terminal.getColumns()` và so sánh với chiều rộng cửa sổ thật.
2. Render lại bảng với chiều rộng nhỏ hơn để xác nhận có phụ thuộc vào terminal size không.
3. Rút gọn cột chứa ID, hash hoặc path; hiển thị phần chi tiết bằng command riêng.
4. Tránh đặt toàn bộ JSON hoặc exception message vào một cell.
5. Chọn bảng ít cột hơn hoặc chuyển sang dạng key-value khi màn hình hẹp.
6. Kiểm tra lại sau khi terminal được resize.

Ví dụ một cách trình bày phù hợp với màn hình hẹp:

~~~text
ID: P-001
Tên: Dự án kế toán
Trạng thái: Đang chạy
Owner: finance-team
~~~

Không phải dữ liệu nào cũng cần nằm trong bảng. Với màn hình nhỏ hoặc nội dung nhiều cột, dạng key-value có thể dễ đọc và ổn định hơn.

## 10. Kiểm tra màu sắc và ANSI capability

JLine sử dụng thông tin terminal type và terminfo để quyết định những tính năng terminal có thể dùng. Một số terminal tối giản không hỗ trợ cursor control hoặc màu; `dumb-color` có thể hỗ trợ màu cơ bản nhưng không hỗ trợ các tính năng khác.

Có thể kiểm tra capability màu qua terminal:

~~~java
import org.jline.terminal.Terminal;
import org.jline.utils.InfoCmp.Capability;

private boolean supportsColor(Terminal terminal) {
    Integer colors = terminal.getNumericCapability(Capability.max_colors);
    return colors != null && colors > 0;
}
~~~

Nếu không có capability hoặc giá trị bằng 0, chọn output không màu. Đừng chỉ kiểm tra `TERM` có chứa chuỗi `xterm` rồi giả định chắc chắn terminal hỗ trợ true color. `TERM`, `COLORTERM`, terminal provider và cấu hình emulator đều có thể ảnh hưởng đến nhận diện.

Các mức màu thường gặp:

| Khả năng | Ý nghĩa |
|---|---|
| 0 hoặc không xác định | Không nên dựa vào màu. |
| 8/16 màu | Màu cơ bản. |
| 256 màu | Bảng màu mở rộng. |
| 24-bit/true color | Màu RGB đầy đủ nếu terminal và đường output hỗ trợ. |

Nếu ứng dụng dùng ANSI escape sequence trực tiếp, phải kiểm tra terminal capability và cung cấp plain-text fallback. Không tự chèn mã ANSI vào JSON, CSV hoặc nội dung được redirect cho máy đọc.

## 11. Dùng theme không màu khi cần output ổn định

Spring Shell có theming framework kết hợp style và figure. Theme mặc định có thể dùng màu và ký hiệu Unicode cho thông báo, trạng thái hoặc thành phần terminal. Theme `dump` hướng đến output đơn giản, không dùng style màu và hạn chế ký hiệu đặc biệt.

Để thử nghiệm output không màu, cấu hình:

~~~properties
spring.shell.theme.name=dump
~~~

Có thể đặt trong `application.properties` hoặc truyền lúc khởi động:

~~~bash
java -jar build-cli.jar --spring.shell.theme.name=dump
~~~

Nếu lỗi màu hoặc ký hiệu biến mất khi dùng theme `dump`, hãy kiểm tra theme mặc định, font và terminal capability. Theme `dump` là phương án fallback hữu ích cho terminal hạn chế, log hoặc môi trường cần output dễ đọc.

Không coi theme `dump` là cách sửa lỗi charset. Nó có thể bỏ màu và một số ký hiệu trang trí nhưng không thể sửa chuỗi đã bị decode sai.

## 12. Màu bị in thành mã escape hoặc mất khi redirect

Mã ANSI thường có dạng `ESC [` theo sau là các tham số và ký tự kết thúc. Terminal hiểu chuỗi này như lệnh điều khiển; file text thông thường thì chỉ lưu các byte/ký tự đó.

Ví dụ khi output bị redirect:

~~~bash
java -jar build-cli.jar project list > result.txt
~~~

Nếu `result.txt` chứa các chuỗi như `\u001B[0m`, màu chưa được strip trước khi ghi file. Với output dành cho script, hãy chọn plain theme hoặc cấu hình ứng dụng tắt styling khi không chạy trên terminal tương tác.

Biến môi trường `NO_COLOR` là quy ước cộng đồng để người dùng yêu cầu chương trình không dùng màu. Không phải mọi phiên bản thư viện tự động áp dụng biến này. Nếu ứng dụng tự quản lý style, hãy kiểm tra biến `NO_COLOR` và tôn trọng yêu cầu khi giá trị không rỗng. Với Spring Shell, có thể cấu hình theme `dump` cho môi trường cần output đơn sắc.

Trên JLine, `TERM=dumb` biểu thị terminal tối giản. Không tự đặt `TERM=xterm-256color` chỉ để ép màu nếu terminal thật không hỗ trợ; khai báo capability sai có thể làm cursor control và các escape sequence khác hoạt động không đúng.

## 13. Phân biệt lỗi terminal với lỗi của bảng trong ứng dụng

| Triệu chứng | Kiểm tra | Hướng xử lý |
|---|---|---|
| Mọi dấu tiếng Việt đều sai | So sánh chuỗi trong Java và `outputEncoding()` | Sửa charset của nguồn dữ liệu hoặc terminal output. |
| Chỉ một vài glyph thành ô vuông | Thử font và terminal khác | Cài/chọn font có glyph hoặc dùng ASCII fallback. |
| Bảng lệch khi có CJK/emoji | So sánh với nội dung ASCII, kiểm tra display width | Dùng renderer Unicode-aware, bỏ emoji hoặc rút gọn cell. |
| Bảng tràn màn hình | Kiểm tra `getColumns()` và dữ liệu dài | Render theo width thực, wrap/rút gọn hoặc chuyển key-value. |
| Bảng sai sau khi resize | Kiểm tra kích thước terminal sau resize | Render lại với kích thước mới. |
| Mã ANSI xuất hiện trong file | Redirect output và kiểm tra theme/style | Tắt màu cho non-interactive output. |
| Màu mất trong IDE nhưng có trong terminal ngoài | So sánh terminal type/capability | Dùng terminal emulator hỗ trợ ANSI hoặc fallback đơn sắc. |
| Màu nền/chữ khó đọc | Kiểm tra theme và nền sáng/tối | Chọn palette tương phản, không dựa vào màu duy nhất để truyền trạng thái. |
| Test bảng wrap khác máy | Kiểm tra terminal width của test | Cố định `spring.shell.test.terminal-width` và height. |

## 14. Kiểm thử kích thước terminal và Unicode

Spring Shell test support cho phép cấu hình kích thước terminal mô phỏng. Mặc định test terminal có chiều rộng 80 cột và chiều cao 24 dòng. Có thể đặt kích thước khác để kiểm tra wrap và table layout.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest(terminalWidth = 120, terminalHeight = 40)
class ProjectTableTests {

    @Test
    void rendersProjectTableAtWideTerminal() {
        // Gọi command project list và xác nhận các cột quan trọng.
    }
}
~~~

Hoặc đặt property:

~~~java
@ShellTest(properties = {
        "spring.shell.test.terminal-width=60",
        "spring.shell.test.terminal-height=20"
})
class NarrowTerminalTests {
}
~~~

Nên có test với ít nhất hai chiều rộng: terminal hẹp và terminal rộng. Với nội dung Unicode, kiểm tra cả tiếng Việt, CJK, combining marks và chuỗi dài không có dấu cách. Đừng chỉ assert số ký tự của output; hãy kiểm tra nội dung và vị trí/đường wrap theo màn hình mô phỏng.

Test terminal giả lập không thay thế việc kiểm tra font và encoding của terminal thật. Bổ sung smoke test thủ công trên Windows Terminal, terminal Linux/macOS hoặc terminal emulator thực tế mà người dùng mục tiêu sử dụng.

## 15. Quy trình chẩn đoán từng bước

1. Chạy command chẩn đoán terminal và lưu `type`, `columns`, `rows`, `encoding`, `outputEncoding` và `maxColors`.
2. In chuỗi thử Unicode và box drawing.
3. So sánh output trong terminal thật, IDE console và file redirect.
4. Nếu dữ liệu Java đã sai, sửa bước đọc/giải mã nguồn.
5. Nếu dữ liệu đúng nhưng dấu sai, kiểm tra UTF-8 và font.
6. Nếu chỉ lệch bảng, kiểm tra width, wrapping và ký tự có độ rộng hai ô.
7. Nếu chỉ lỗi border, thử `BorderStyle.oldschool`.
8. Nếu màu sai, kiểm tra capability và thử `spring.shell.theme.name=dump`.
9. Nếu ANSI bị in thô, tắt styling cho output redirect hoặc chọn theme đơn sắc.
10. Thêm test với terminal width khác nhau và xác nhận lại trên môi trường triển khai.

## 16. Checklist trước khi phát hành

- [ ] Dữ liệu text được đọc và ghi bằng charset đã xác định.
- [ ] Terminal output encoding tương thích với terminal emulator.
- [ ] Font hỗ trợ tiếng Việt, box drawing và các ký tự cần hiển thị.
- [ ] Bảng không dùng `String.length()` để tự căn cột Unicode.
- [ ] Renderer nhận chiều rộng terminal thực tế hoặc có fallback hợp lý.
- [ ] Nội dung dài có quy tắc wrap, truncate hoặc chuyển sang dạng key-value.
- [ ] Có border ASCII fallback cho môi trường thiếu Unicode glyph.
- [ ] Màu chỉ được dùng khi terminal capability phù hợp.
- [ ] Có plain-text fallback hoặc theme `dump` cho output không màu.
- [ ] ANSI escape sequence không lọt vào JSON, CSV hoặc file output dành cho máy đọc.
- [ ] Test bao phủ terminal hẹp/rộng và nội dung Unicode.
- [ ] Đã smoke test trên terminal emulator và hệ điều hành mục tiêu.

## Kết luận

Bảng, Unicode và màu sắc hiển thị sai thường xuất phát từ sự không thống nhất giữa dữ liệu, charset, font, độ rộng ô terminal, terminal capability và theme. Hãy bắt đầu bằng command chẩn đoán JLine, xác nhận chuỗi còn đúng trước khi render, dùng `TableBuilder` thay cho căn cột bằng số ký tự, chọn `oldschool` khi thiếu glyph Unicode và dùng theme `dump` khi cần output đơn sắc. Cuối cùng, kiểm thử ở nhiều chiều rộng terminal và trên đúng terminal emulator mà người dùng sẽ sử dụng.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Theming and Styling](https://docs.spring.io/spring-shell/reference/3.4/customization/styling.html)
- [Spring Shell 3.4 API – TableBuilder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/table/TableBuilder.html)
- [Spring Shell 3.4 API – BorderStyle](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/table/BorderStyle.html)
- [Spring Shell 3.4 API – Table](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/table/Table.html)
- [Spring Shell 3.4 – Test Terminal Settings](https://docs.spring.io/spring-shell/reference/3.4/testing/settings.html)
- [JLine 3 – Terminal](https://jline.org/versions/3.x/docs/terminal/)
- [JLine 3 – Troubleshooting](https://jline.org/versions/3.x/docs/troubleshooting/)
- [JLine – Unicode Support](https://jline.org/docs/advanced/unicode-support/)
