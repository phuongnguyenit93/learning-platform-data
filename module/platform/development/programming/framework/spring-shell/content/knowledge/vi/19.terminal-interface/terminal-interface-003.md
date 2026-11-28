# Màu ANSI và khả năng hỗ trợ của terminal

Màu sắc giúp người dùng nhận biết nhanh trạng thái thành công, cảnh báo và lỗi trong CLI. Tuy nhiên, không phải mọi nơi chạy ứng dụng đều hiển thị màu giống nhau. Terminal có thể hỗ trợ 8 màu, 256 màu hoặc truecolor; một số môi trường chỉ hiển thị văn bản thuần; output được chuyển hướng vào file có thể giữ nguyên các mã điều khiển thay vì render chúng.

Spring Shell 4.x dùng JLine để làm việc với terminal và cung cấp hệ thống theme để định dạng nội dung. Để tạo CLI dễ dùng trên nhiều môi trường, cần hiểu ANSI SGR, cách JLine đọc capability của terminal, cách Spring Shell áp dụng theme, quy ước `NO_COLOR` và cách fallback khi không có màu.

## 1. Màu ANSI là gì?

ANSI escape sequence là chuỗi điều khiển được gửi cùng output để yêu cầu terminal thay đổi cách hiển thị. Với màu văn bản, ứng dụng thường dùng nhóm SGR (Select Graphic Rendition). Một chuỗi SGR có dạng tổng quát:

```text
ESC [ tham-số-m1 ; tham-số-m2 ; ... m
```

`ESC` là ký tự Escape có mã `0x1B`. Trong Java có thể viết bằng `\u001B`. Ví dụ:

```java
String red = "\u001B[31m";
String reset = "\u001B[0m";

System.out.println(red + "ERROR: Cannot connect" + reset);
```

Terminal hiểu `31` là đặt màu chữ đỏ và `0` là đặt lại các thuộc tính hiển thị về mặc định. Khi terminal hỗ trợ ANSI, dòng chữ được tô màu. Nếu terminal không hiểu escape sequence, người dùng có thể nhìn thấy các ký tự điều khiển lẫn trong output.

### Các mã SGR thường gặp

| Mã | Ý nghĩa |
|---|---|
| `0` | Đặt lại toàn bộ thuộc tính hiển thị |
| `1` | Chữ đậm hoặc cường độ sáng cao |
| `2` | Chữ mờ |
| `3` | Chữ nghiêng nếu terminal hỗ trợ |
| `4` | Gạch chân |
| `7` | Đảo màu chữ và nền |
| `22` | Tắt bold/faint |
| `23` | Tắt italic |
| `24` | Tắt underline |
| `27` | Tắt inverse |
| `30`–`37` | Màu chữ cơ bản: đen đến trắng |
| `39` | Trả màu chữ về mặc định |
| `40`–`47` | Màu nền cơ bản |
| `49` | Trả màu nền về mặc định |
| `90`–`97` | Màu chữ sáng |
| `100`–`107` | Màu nền sáng |

Ví dụ kết hợp bold và màu chữ:

```java
String style = "\u001B[1;31m";
String reset = "\u001B[0m";
System.out.println(style + "ERROR" + reset + ": Invalid input");
```

Nên luôn đặt lại style sau đoạn văn bản được định dạng. Nếu quên reset, những nội dung tiếp theo có thể tiếp tục mang màu hoặc thuộc tính cũ.

## 2. Các mức màu: 8/16, 256 và truecolor

Không phải terminal nào cũng hỗ trợ cùng một bảng màu. Có thể chia khả năng hiển thị thành các mức phổ biến:

| Mức | Cách biểu diễn thường gặp | Khi sử dụng |
|---|---|---|
| 8 màu | Mã chữ `30`–`37`, nền `40`–`47` | Terminal cơ bản, tương thích rộng |
| 16 màu | Thêm dải sáng `90`–`97`, `100`–`107` | Phân biệt màu cơ bản và màu sáng |
| 256 màu | `38;5;n` cho chữ, `48;5;n` cho nền | Terminal có bảng palette 256 màu |
| Truecolor 24-bit | `38;2;r;g;b`, `48;2;r;g;b` | Terminal hỗ trợ RGB trực tiếp |

Ví dụ các mã SGR mở rộng:

```text
ESC[38;5;208m       Chữ màu cam trong palette 256 màu
ESC[48;5;24m        Nền màu xanh trong palette 256 màu
ESC[38;2;255;80;80m Chữ RGB (255, 80, 80)
ESC[48;2;20;40;80m  Nền RGB (20, 40, 80)
ESC[0m               Đặt lại style
```

Các terminal hiện đại thường hỗ trợ 256 màu và nhiều terminal hỗ trợ truecolor, nhưng không nên suy luận chắc chắn chỉ từ tên terminal. `COLORTERM=truecolor` hoặc `COLORTERM=24bit` là dấu hiệu môi trường thường công bố; đây không phải bằng chứng tuyệt đối rằng mọi đường output đều render đúng.

Thiết kế theme nên dùng màu cơ bản làm fallback. Chỉ dùng RGB cho chi tiết trang trí khi có lý do rõ ràng; trạng thái quan trọng vẫn cần được thể hiện bằng nhãn như `ERROR`, `WARN` hoặc `SUCCESS`.

## 3. Terminal capability khác với mã ANSI cố định

Mã ANSI mô tả một chuỗi điều khiển. Terminal capability mô tả terminal cụ thể có hỗ trợ thao tác đó hay không và cách tạo chuỗi điều khiển phù hợp.

JLine cung cấp interface `Terminal` để truy cập capability dựa trên terminfo. Thay vì mặc định terminal nào cũng hiểu một mã escape giống nhau, ứng dụng có thể hỏi:

- Terminal có hỗ trợ màu không?
- Terminal có bao nhiêu màu?
- Terminal có chuỗi điều khiển đặt màu chữ hoặc màu nền không?
- Terminal có hỗ trợ di chuyển con trỏ, xóa màn hình hoặc các thao tác khác không?

Một số API quan trọng của JLine:

| API | Mục đích |
|---|---|
| `terminal.getType()` | Lấy tên loại terminal, thường dựa trên `TERM` |
| `getBooleanCapability(...)` | Kiểm tra capability dạng có/không |
| `getNumericCapability(...)` | Đọc capability dạng số như số lượng màu tối đa |
| `getStringCapability(...)` | Lấy chuỗi điều khiển tương ứng nếu capability có hỗ trợ |
| `terminal.puts(...)` | Ghi chuỗi điều khiển đã được JLine định dạng |
| `terminal.writer()` | Ghi văn bản ra terminal |
| `terminal.flush()` | Đẩy output đang đệm ra terminal |

JLine dùng tên terminal như `xterm-256color`, `screen-256color`, `ansi`, `windows-vtp` hoặc `dumb` để tra cứu capability. Terminal `dumb` có rất ít tính năng điều khiển và thường không hỗ trợ màu. `TERM` là tên loại terminal, không phải một cờ bật/tắt màu đơn giản.

## 4. Kiểm tra khả năng hiển thị màu bằng JLine

Spring Shell 4 tích hợp JLine và đăng ký `Terminal` trong Spring context khi dùng JLine shell runner. Có thể inject terminal bean vào một service để kiểm tra capability. Không cần tự tạo một `Terminal` thứ hai cho cùng phiên shell.

Ví dụ kiểm tra capability màu:

```java
import org.jline.terminal.Terminal;
import org.jline.utils.InfoCmp.Capability;
import org.springframework.stereotype.Component;

@Component
public class TerminalColorProbe {

    private final Terminal terminal;

    public TerminalColorProbe(Terminal terminal) {
        this.terminal = terminal;
    }

    public void printCapabilities() {
        boolean colors = terminal.getBooleanCapability(Capability.colors);
        Integer maxColors = terminal.getNumericCapability(Capability.max_colors);
        boolean foregroundSequence =
                terminal.getStringCapability(Capability.set_a_foreground) != null;

        terminal.writer().println("Terminal type: " + terminal.getType());
        terminal.writer().println("Color capability: " + colors);
        terminal.writer().println("Maximum colors: " + maxColors);
        terminal.writer().println("Foreground sequence: " + foregroundSequence);
        terminal.flush();
    }
}
```

`Capability.colors` cho biết terminal khai báo hỗ trợ màu. `max_colors` cho biết số màu tối đa nếu terminfo cung cấp giá trị. `set_a_foreground` là capability đặt màu chữ. Nên kiểm tra cả capability và chuỗi điều khiển cần dùng trước khi render.

Giá trị `maxColors` có thể là `null` nếu terminfo không cung cấp thông tin. Không nên tự suy ra truecolor chỉ vì giá trị lớn hoặc vì tên terminal có chứa `256color`.

### Chọn màu và fallback trước khi ghi output

Thêm các method sau vào `TerminalColorProbe` ở ví dụ trước:

```java
public boolean supportsBasicColor() {
    return terminal.getBooleanCapability(Capability.colors)
            && terminal.getStringCapability(Capability.set_a_foreground) != null;
}

public void printStatus(boolean success, String message) {
    if (supportsBasicColor()) {
        int colorIndex = success ? 2 : 1;

        try {
            terminal.puts(Capability.set_a_foreground, colorIndex);
            terminal.writer().print(success ? "SUCCESS" : "ERROR");
        }
        finally {
            terminal.puts(Capability.exit_attribute_mode);
        }
        terminal.writer().println(": " + message);
    }
    else {
        terminal.writer().println((success ? "SUCCESS" : "ERROR") + ": " + message);
    }
    terminal.flush();
}
```

Trong ví dụ, màu được dùng để nhấn mạnh nhãn. Nội dung và nhãn vẫn truyền tải đầy đủ ý nghĩa khi terminal không có màu. Với mã thực tế, nên tách phần chọn màu thành một policy hoặc renderer để không lặp logic ở từng command.

`Terminal` được Spring quản lý theo vòng đời của shell. Khi inject bean này, không tự đóng terminal sau mỗi lần in; việc đóng terminal thuộc về thành phần quản lý phiên shell.

## 5. Xử lý `NO_COLOR` và tùy chọn bật/tắt màu

`NO_COLOR` là quy ước chung trong hệ sinh thái CLI. Khi biến môi trường này tồn tại và có giá trị không rỗng, chương trình nên tắt màu ANSI mặc định. Giá trị cụ thể không quan trọng; `NO_COLOR=1` và `NO_COLOR=true` đều được xem là bật quy ước.

```bash
NO_COLOR=1 java -jar catalog-cli.jar
```

PowerShell:

```powershell
$env:NO_COLOR = "1"
java -jar .\catalog-cli.jar
```

Giá trị rỗng không kích hoạt quy ước:

```bash
NO_COLOR= java -jar catalog-cli.jar
```

Chuẩn `NO_COLOR` cho phép cấu hình người dùng hoặc tùy chọn command cụ thể ghi đè mặc định đó. Một chương trình có thể cung cấp `--color=always`, `--color=never` hoặc `--color=auto`.

Thứ tự lựa chọn phù hợp:

1. Tùy chọn màu tường minh trên lần gọi hiện tại (`always` hoặc `never`).
2. Cấu hình màu tường minh của ứng dụng.
3. `NO_COLOR` không rỗng: tắt màu mặc định.
4. Chế độ tự động: kiểm tra capability terminal và loại output.

Không nên giả định Spring Shell tự động đọc `NO_COLOR` và tắt mọi theme. Nếu ứng dụng cần tuân thủ quy ước này, hãy áp dụng nó trong policy output hoặc cấu hình theme tương ứng.

`NO_COLOR` chỉ nói về màu sắc. Nó không yêu cầu tắt các thuộc tính không phải màu như bold, underline hoặc italic.

Ví dụ hàm kiểm tra biến môi trường theo đúng quy ước:

```java
private boolean noColorRequested() {
    String value = System.getenv("NO_COLOR");
    return value != null && !value.isEmpty();
}
```

Nếu command có `--color=always|never|auto`, hãy xử lý giá trị tường minh trước khi xét `NO_COLOR`:

```java
public enum ColorMode {
    AUTO, ALWAYS, NEVER
}
```

Trong class policy, thêm method:

```java
public boolean shouldUseColor(ColorMode mode) {
    return switch (mode) {
        case ALWAYS -> true;
        case NEVER -> false;
        case AUTO -> !noColorRequested() && supportsBasicColor();
    };
}
```

`ColorMode` là enum do ứng dụng định nghĩa. Với chế độ `AUTO`, `supportsBasicColor()` kiểm tra capability mà JLine nhận diện. Nếu ứng dụng ghi output qua một stream riêng thay vì terminal writer, cần xác định stream đó có gắn với TTY hay không trước khi bật màu.

## 6. Dùng theme `dump` để tạo output không màu

Spring Shell 4 có hệ thống theming gồm hai phần:

- **Style:** định dạng chữ như màu chữ, màu nền, bold, italic hoặc underline.
- **Figure:** các ký tự biểu tượng như dấu tick, dấu lỗi, mũi tên hoặc checkbox.

Hai phần được kết hợp thành một `Theme`. Theme mặc định có tên `default`. Spring Shell cũng cung cấp theme `dump`, không dùng styling màu và cố gắng không dùng các figure đặc biệt.

Có thể chọn theme `dump` bằng cấu hình:

```yaml
spring:
  shell:
    theme:
      name: dump
```

Hoặc dùng biến môi trường theo relaxed binding của Spring Boot:

```bash
SPRING_SHELL_THEME_NAME=dump java -jar catalog-cli.jar
```

Theme `dump` hữu ích khi output được ghi vào file, dùng trong CI, hoặc cần văn bản dễ đọc trên terminal giới hạn tính năng. Nó cũng là một fallback tốt khi người dùng muốn output không màu.

## 7. Tùy chỉnh theme của Spring Shell

Nếu muốn giữ theme mặc định nhưng thay đổi màu nhấn, có thể kế thừa `StyleSettings`. Ví dụ dưới đây thay đổi style của nội dung được highlight:

```java
import org.springframework.shell.jline.tui.style.StyleSettings;

public class BrandStyleSettings extends StyleSettings {

    @Override
    public String highlight() {
        return "bold,fg:bright-cyan";
    }
}
```

JLine style expression hỗ trợ tên màu cơ bản như `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white` và `black`; có thể dùng `bright-` hoặc `!` để chọn màu sáng. Với RGB, dùng dạng `fg-rgb:#ff3333` hoặc `bg-rgb:#203040`.

Có thể kết hợp style và figure thành theme riêng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.jline.tui.style.FigureSettings;
import org.springframework.shell.jline.tui.style.Theme;
import org.springframework.shell.jline.tui.style.ThemeSettings;

@Configuration
public class TerminalThemeConfiguration {

    @Bean
    Theme brandTheme() {
        return new Theme() {
            @Override
            public String getName() {
                return "brand";
            }

            @Override
            public ThemeSettings getSettings() {
                return new ThemeSettings(
                        new BrandStyleSettings(),
                        FigureSettings.defaults());
            }
        };
    }
}
```

Chọn theme mới:

```yaml
spring:
  shell:
    theme:
      name: brand
```

Tên package của API theming trong Spring Shell 4 là `org.springframework.shell.jline.tui.style`. Hãy dùng đúng API của version Spring Shell trong dự án nếu đang nâng cấp từ thế hệ cũ.

## 8. Phân biệt capability terminal với lựa chọn theme

Theme mô tả ứng dụng muốn trình bày nội dung như thế nào. Capability mô tả terminal có thể thực hiện thao tác hiển thị đó hay không. Hai lớp này bổ trợ nhau.

Ví dụ theme có thể yêu cầu `bold,fg:bright-cyan`, nhưng terminal chỉ hỗ trợ 8 màu hoặc không có chuỗi điều khiển màu. JLine chịu trách nhiệm chuyển attributed style thành output phù hợp với terminal. Nếu tự ghi ANSI sequence trực tiếp, ứng dụng phải tự quản lý fallback và reset style.

| Tình huống | Theme | Capability | Hành vi nên chọn |
|---|---|---|---|
| Terminal 256 màu | `default` hoặc theme thương hiệu | Có màu, nhiều màu | Render màu theo capability |
| Terminal 8 màu | Theme có màu cơ bản | Có màu, palette nhỏ | Dùng màu cơ bản và bold |
| Terminal `dumb` | `dump` | Không có màu | Chỉ in văn bản và ký hiệu ASCII |
| Output được redirect | `dump` hoặc plain renderer | Không có terminal tương tác phù hợp | Không thêm escape sequence vào file |
| Người dùng đặt `NO_COLOR` | `dump` hoặc policy no-color | Có thể vẫn hỗ trợ màu | Tôn trọng yêu cầu tắt màu mặc định |
| Theme dùng RGB nhưng terminal không hỗ trợ | Fallback theme/style | Không đủ capability | Chọn màu cơ bản hoặc bỏ màu |

Không nên tự kết luận rằng terminal hỗ trợ truecolor chỉ vì nó hỗ trợ ANSI. Mỗi mức màu cần được kiểm tra và có fallback riêng nếu ứng dụng trực tiếp tạo sequence.

## 9. Vì sao output chuyển hướng cần được xử lý riêng?

Khi chạy:

```bash
java -jar catalog-cli.jar report-list > report.txt
```

output được ghi vào file. File văn bản không tự diễn giải ANSI sequence như terminal. Nếu ứng dụng ghi `ESC[31m` vào file, người đọc có thể nhìn thấy ký tự điều khiển hoặc công cụ xử lý file bị ảnh hưởng.

Tương tự, khi chạy qua pipe:

```bash
java -jar catalog-cli.jar report-list | grep FAILED
```

escape sequence có thể làm nội dung không còn khớp với cách grep hoặc parser mong đợi. Trong chế độ automation, ưu tiên output thuần hoặc định dạng có cấu trúc như CSV/JSON.

JLine có thể nhận biết một số trường hợp không có TTY và chuyển sang terminal `dumb`. Tuy nhiên, ứng dụng vẫn cần kiểm thử đúng đường output của mình, đặc biệt khi stdout và stderr được chuyển hướng riêng hoặc command được chạy bên trong IDE.

## 10. Màu sắc không được là cách duy nhất truyền tải trạng thái

Không phải người dùng nào cũng phân biệt được mọi màu. Terminal có thể dùng palette tùy chỉnh, nền sáng hoặc nền tối; màu đỏ có thể khó đọc trên một số theme.

Hãy kết hợp màu với văn bản và cấu trúc:

```text
[SUCCESS] Import completed: 120 records
[WARNING] 3 records were skipped
[ERROR] Database connection failed
```

Khi terminal hỗ trợ màu, có thể tô `SUCCESS` xanh, `WARNING` vàng và `ERROR` đỏ. Khi không hỗ trợ, nhãn vẫn thể hiện trạng thái.

Một số nguyên tắc thiết kế:

- Dùng màu có mục đích: trạng thái, mức độ nghiêm trọng hoặc điểm cần chú ý.
- Giữ độ tương phản đủ cao với cả nền sáng và nền tối.
- Không tô màu toàn bộ output dài nếu chỉ cần nhấn mạnh một nhãn.
- Không dùng riêng đỏ/xanh để biểu thị thất bại/thành công.
- Không dựa vào emoji hoặc ký tự Unicode phức tạp khi terminal có thể thiếu font.
- Luôn có phương án plain text.

## 11. Kiểm thử màu và fallback

Kiểm thử trên một terminal duy nhất chưa đủ. Nên thử nhiều loại terminal và cách chạy khác nhau.

| Môi trường | Điều cần kiểm tra |
|---|---|
| Linux terminal với `xterm-256color` | Màu cơ bản, palette và reset sequence |
| macOS Terminal/iTerm2 | Màu, truecolor và Unicode |
| Windows Terminal | ANSI/VT, palette và theme nền sáng/tối |
| Windows console cũ | Khả năng hỗ trợ VT và fallback |
| IDE terminal | Màu, ký tự đặc biệt, prompt và output redirect |
| SSH/tmux/screen | Capability theo terminal type và phiên trung gian |
| CI hoặc container không TTY | Không phát ANSI vào log nếu không được yêu cầu |
| `NO_COLOR=1` | Output mặc định không chứa mã màu |
| `TERM=dumb` | Không dùng thao tác điều khiển hoặc màu không được hỗ trợ |
| `> output.txt` hoặc pipe | Nội dung thuần dễ đọc và xử lý |

### Kiểm tra nhanh trên terminal

Linux/macOS:

```bash
printf '\033[31mRED\033[0m plain text\n'
printf 'TERM=%s\n' "$TERM"
printf 'COLORTERM=%s\n' "$COLORTERM"
printf 'NO_COLOR=%s\n' "$NO_COLOR"
```

PowerShell:

```powershell
Write-Host "RED" -ForegroundColor Red
$env:TERM
$env:COLORTERM
$env:NO_COLOR
```

Các lệnh này giúp kiểm tra terminal hiện tại có render màu và cung cấp thông tin môi trường hay không. Chúng không thay thế việc kiểm tra capability từ JLine trong ứng dụng.

### Kiểm tra tự động

Nên có test cho ít nhất các trường hợp:

1. Terminal hỗ trợ màu: renderer có thể tạo style màu phù hợp.
2. Terminal không hỗ trợ màu: nội dung vẫn có nhãn trạng thái và không có escape sequence.
3. `NO_COLOR` không rỗng: màu bị tắt theo policy mặc định.
4. `NO_COLOR` rỗng: không kích hoạt quy ước tắt màu.
5. `--color=never`: luôn tạo output thuần.
6. `--color=always`: tôn trọng lựa chọn tường minh nếu ứng dụng cho phép.
7. Output redirect: file không chứa escape sequence ngoài chủ đích.

Khi kiểm thử output, có thể kiểm tra các ký tự Escape hoặc chuỗi `\u001B[` để phát hiện ANSI sequence. Với test theme, kiểm tra cả nội dung hiển thị và style đã được gán; không chỉ so sánh chuỗi sau khi đã render.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Terminal hiển thị `^[` hoặc `[31m` | Terminal không xử lý ANSI sequence | Kiểm tra capability và dùng plain fallback |
| Màu chữ kéo dài sang dòng sau | Không reset style | Dùng `ESC[0m` hoặc capability reset trong `finally` |
| Màu RGB bị đổi thành màu gần đúng | Terminal chỉ hỗ trợ palette nhỏ | Dùng màu cơ bản hoặc đọc số lượng màu từ terminfo |
| CI log chứa mã escape | Output không gắn với TTY hoặc không có policy no-color | Dùng theme `dump` hoặc tắt màu khi redirect |
| `TERM` không đúng | Biến môi trường khai báo sai loại terminal | Đặt `TERM` phù hợp với terminal emulator thực tế |
| `TERM=dumb` nhưng ứng dụng vẫn in màu thủ công | Code bỏ qua capability | Kiểm tra JLine capability trước khi ghi ANSI |
| Đã đặt `NO_COLOR` nhưng Spring Shell vẫn có màu | Theme không tự động ánh xạ biến này trong ứng dụng | Chọn `spring.shell.theme.name=dump` hoặc triển khai policy NO_COLOR |
| Màu đỏ khó đọc trên nền tối | Palette terminal và theme không tương thích | Dùng màu sáng, kiểm tra contrast và thêm nhãn chữ |
| Emoji hoặc biểu tượng bị lỗi | Font/terminal không hỗ trợ glyph | Chọn figure ASCII hoặc theme `dump` |

## 13. Checklist thiết kế output có màu

- [ ] Đã phân biệt ANSI SGR, terminal type và terminfo capability.
- [ ] Dùng theme của Spring Shell cho định dạng output thông thường.
- [ ] Kiểm tra `colors`, `max_colors` và capability đặt foreground khi ghi màu qua JLine.
- [ ] Không giả định mọi terminal hỗ trợ 256 màu hoặc truecolor.
- [ ] Có fallback plain text cho terminal `dumb`, output redirect và CI.
- [ ] Tôn trọng `NO_COLOR` khi biến có giá trị không rỗng.
- [ ] Có tùy chọn rõ ràng như `--color=auto|always|never` nếu sản phẩm cần điều khiển màu.
- [ ] Có thể chọn theme `dump` bằng `spring.shell.theme.name=dump`.
- [ ] Mọi đoạn ANSI trực tiếp đều có reset style.
- [ ] Không dùng màu làm dấu hiệu duy nhất cho trạng thái.
- [ ] Đã kiểm tra nền sáng, nền tối, Windows, IDE, SSH và CI.
- [ ] Đã kiểm thử output file không có escape sequence ngoài dự kiến.

## Tài liệu tham khảo

1. [Spring Shell 4 – Theming](https://docs.spring.io/spring-shell/reference/customization/styling.html) – theme mặc định, theme `dump`, `StyleSettings`, `FigureSettings`, `ThemeSettings` và `ThemeResolver`.
2. [Spring Shell 4 – Theming Technical Introduction](https://docs.spring.io/spring-shell/reference/appendices/techintro/theming.html) – style expression của JLine, màu cơ bản, màu RGB và các thuộc tính văn bản.
3. [Spring Shell 4 – `TerminalCustomizer` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/TerminalCustomizer.html) – tùy chỉnh `TerminalBuilder` khi cần cấu hình terminal.
4. [JLine 3 – Terminal](https://jline.org/versions/3.x/docs/terminal/) – `Terminal`, `TerminalBuilder`, terminfo capability và màu terminal.
5. [JLine 3 – Troubleshooting](https://jline.org/versions/3.x/docs/troubleshooting/) – terminal không hỗ trợ ANSI, Windows và output redirect.
6. [NO_COLOR](https://no-color.org/) – quy ước tắt màu ANSI qua biến môi trường.

Màu ANSI là một khả năng của đường output, không phải thuộc tính luôn có của mọi terminal. Hãy dùng theme của Spring Shell để định dạng nhất quán, kiểm tra capability bằng JLine khi cần điều khiển trực tiếp và luôn giữ nội dung dễ hiểu khi màu bị tắt hoặc terminal chỉ hỗ trợ văn bản thuần.
