# Theme, style và tài nguyên hiển thị theo từng nhánh

Terminal có thể hiển thị nhiều hơn văn bản thuần: tiêu đề in đậm, màu cho trạng thái, ký hiệu thành công hoặc lỗi, checkbox và hoạt ảnh tiến trình. Nếu mỗi command tự chọn màu và tự viết ký hiệu, giao diện nhanh chóng thiếu nhất quán; khi đổi terminal hoặc cần chế độ không màu, việc sửa từng nơi cũng khó khăn.

Spring Shell 3.3 cung cấp hệ thống theming dựa trên JLine. Một theme gom ba nhánh tài nguyên hiển thị:

- **Style:** cách trình bày văn bản như màu chữ, màu nền, in đậm, làm nổi bật, trạng thái được chọn hoặc bị vô hiệu hóa.
- **Figure:** ký hiệu dùng trong giao diện như dấu tick, dấu lỗi, cảnh báo, mũi tên và checkbox.
- **Spinner:** các khung ký tự luân phiên để biểu diễn một công việc đang diễn ra.

Ba nhánh này được tổ chức trong `ThemeSettings`, gắn với một tên qua `Theme` và được tra cứu bằng `ThemeResolver`. Nhờ vậy, command hoặc thành phần giao diện có thể dùng tên tag mang ý nghĩa như tiêu đề, lỗi hay cảnh báo; theme quyết định cách hiển thị cụ thể.

Sau bài này, bạn có thể:

- Phân biệt style, figure và spinner trong Spring Shell.
- Sử dụng theme mặc định và theme `dump`.
- Tạo `StyleSettings`, `FigureSettings`, `SpinnerSettings` tùy chỉnh.
- Đóng gói các nhánh tài nguyên trong `ThemeSettings` và đăng ký `Theme` thành Spring bean.
- Chọn theme bằng `spring.shell.theme.name`.
- Dùng `ThemeResolver` để tra cứu style, figure và spinner.
- Áp dụng theme riêng cho một màn hình `TerminalUI`.
- Viết output có khả năng hoạt động trên terminal không hỗ trợ màu hoặc Unicode.

> Ví dụ sử dụng API Spring Shell 3.3.x và JLine 3. Các lớp và package trong bài thuộc mô hình Spring Shell 3.x; hãy đối chiếu API đúng phiên bản khi nâng cấp framework.

## 1. Cấu trúc của một theme

Một theme gồm một tên và một tập hợp cài đặt hiển thị. `ThemeSettings` gom các nhánh tài nguyên:

~~~mermaid
flowchart TD
    A[Theme: tên và settings] --> B[ThemeSettings]
    B --> C[StyleSettings]
    B --> D[FigureSettings]
    B --> E[SpinnerSettings]
    C --> F[Style tag: title, value, error, highlight]
    D --> G[Figure tag: tick, warning, error, arrow, checkbox]
    E --> H[Spinner tag: dot, line]
    I[ThemeResolver] -->|Tra cứu theo tag| C
    I -->|Tra cứu theo tag| D
    I -->|Tra cứu theo tag| E
~~~

| Nhánh | Đối tượng | Ví dụ tài nguyên |
|---|---|---|
| Kiểu chữ và màu | `StyleSettings` | `title`, `value`, `highlight`, `listLevelError` |
| Ký hiệu | `FigureSettings` | `tick`, `error`, `warning`, `checkboxOn`, `rightwardsArrow` |
| Hoạt ảnh | `SpinnerSettings` | `dot`, `line` |

`Theme` là hợp đồng cung cấp tên và `ThemeSettings`. `ThemeRegistry` lưu các theme đã đăng ký. `ThemeResolver` tra cứu các tag theo theme đang hoạt động hoặc theo tên theme được chỉ định.

Spring Shell có theme mặc định tên `default`. Theme tích hợp `dump` bỏ màu và hạn chế ký hiệu đặc biệt, phù hợp với terminal đơn giản, log, CI hoặc môi trường cần output dễ đọc dưới dạng văn bản thuần.

## 2. Style: màu sắc và cách nhấn mạnh văn bản

`StyleSettings` định nghĩa các style có ý nghĩa trong giao diện. Thay vì gắn trực tiếp một màu vào từng dòng output, ứng dụng dùng các tag ngữ nghĩa:

| Tag/thuộc tính | Mục đích |
|---|---|
| `title()` | Tiêu đề |
| `value()` | Giá trị hiển thị |
| `listKey()` và `listValue()` | Tên và giá trị trong danh sách |
| `listLevelInfo()` | Nội dung mức thông tin |
| `listLevelWarn()` | Nội dung cảnh báo |
| `listLevelError()` | Nội dung lỗi |
| `highlight()` | Nội dung được làm nổi bật |
| `itemEnabled()` / `itemDisabled()` | Trạng thái có thể hoặc không thể chọn |
| `itemSelected()` / `itemUnselected()` | Trạng thái được chọn hoặc chưa chọn |
| `itemSelector()` | Dấu chỉ mục đang chọn |
| `background()`, `dialogBackground()` | Nền nội dung hoặc hộp thoại |
| `buttonBackground()`, `menubarBackground()`, `statusbarBackground()` | Nền các vùng giao diện tương ứng |

Các hằng số như `StyleSettings.TAG_TITLE`, `StyleSettings.TAG_LEVEL_ERROR` và `StyleSettings.TAG_HIGHLIGHT` đại diện cho những tag này. Dùng hằng số giúp tránh gõ sai tên tag.

### Cú pháp style của JLine

Spring Shell dùng `AttributedString` và `AttributedStyle` của JLine. Style expression có thể kết hợp nhiều thuộc tính bằng dấu phẩy:

| Expression | Ý nghĩa |
|---|---|
| `bold` | In đậm |
| `fg:cyan` | Màu chữ cyan |
| `fg:red` | Màu chữ đỏ |
| `bold,fg:bright-white` | Chữ trắng sáng và in đậm |
| `bg:blue` | Nền xanh dương |
| `fg-rgb:#ff3333` | Màu chữ RGB |
| `italic,underline` | In nghiêng và gạch chân |

JLine hỗ trợ các màu cơ bản `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white` và các dạng rút gọn tương ứng. Tiền tố `bright-` hoặc `!` yêu cầu màu sáng. Với màu RGB, dùng dạng `fg-rgb:#RRGGBB` hoặc `bg-rgb:#RRGGBB`.

Có thể chỉ định biểu thức dự phòng bằng cú pháp `spec:=fallback`. Ví dụ:

~~~text
fg-rgb:#ff3333:=fg:red
~~~

Nếu terminal hoặc parser không xử lý được màu RGB, biểu thức dự phòng dùng màu đỏ cơ bản. Những thuộc tính như `bold`, `faint`, `italic`, `underline`, `inverse` và `crossed-out` có thể kết hợp với màu.

## 3. Figure: ký hiệu cho trạng thái và điều hướng

`FigureSettings` quản lý ký tự hoặc biểu tượng xuất hiện trong giao diện. Các tag thường dùng:

| Tag/thuộc tính | Mục đích |
|---|---|
| `tick()` | Dấu xác nhận thành công |
| `info()` | Ký hiệu thông tin |
| `warning()` | Ký hiệu cảnh báo |
| `error()` | Ký hiệu lỗi |
| `checkboxOn()` / `checkboxOff()` | Checkbox bật/tắt |
| `leftwardsArrow()` / `righwardsArror()` | Mũi tên trái/phải |
| `upwardsArrow()` / `downwardsArror()` | Mũi tên lên/xuống |
| `questionMark()` | Ký hiệu câu hỏi |
| `leftPointingQuotation()` / `rightPointingQuotation()` | Dấu chỉ hướng hoặc trích dẫn |

Tên một số phương thức trong API có cách viết đặc biệt, chẳng hạn `downwardsArror()` và `righwardsArror()`. Khi dùng trực tiếp, hãy tham chiếu đúng tên trong API 3.3.

Figure giúp người dùng nhận biết trạng thái nhanh hơn, nhưng không nên chỉ dựa vào biểu tượng. Ví dụ, hãy hiển thị cả `✔ Đã lưu` hoặc `✖ Không thể kết nối` để thông tin vẫn rõ khi terminal không hỗ trợ ký tự hoặc người dùng không phân biệt được hình dạng.

## 4. Spinner: tài nguyên cho trạng thái đang xử lý

`SpinnerSettings` cung cấp các spinner theo tag. Spring Shell 3.3 có hai lựa chọn tích hợp:

- `SpinnerSettings.TAG_DOT`: spinner dạng dấu chấm.
- `SpinnerSettings.TAG_LINE`: spinner dạng đường/quay.

Mỗi `Spinner` gồm một mảng các frame và khoảng thời gian ước tính giữa các lần đổi frame. Kiểu `Spinner` nằm trong package `org.springframework.shell.component.view.control` và có factory `Spinner.of(String[] frames, int interval)`.

Ví dụ tạo spinner riêng:

~~~java
import org.springframework.shell.component.view.control.Spinner;

Spinner spinner = Spinner.of(
        new String[] {"-", "\\", "|", "/"},
        100);
~~~

Trong ví dụ, các frame luân phiên theo khoảng 100 mili giây. Khoảng thời gian thực tế phụ thuộc tần suất terminal được vẽ lại; đây là nhịp ước tính, không phải bộ định thời chính xác.

Spinner phù hợp với thao tác kéo dài trong terminal tương tác. Với chế độ non-interactive hoặc output được chuyển hướng vào file, nên ưu tiên thông báo theo dòng hoặc phần trăm tiến độ để tránh tạo ký tự điều khiển không cần thiết.

## 5. Tạo theme tùy chỉnh

Để tạo theme riêng, triển khai các nhánh tài nguyên và ghép chúng trong một lớp kế thừa `ThemeSettings`. Ví dụ dưới đây tạo theme `ocean` với màu xanh cyan, ký hiệu trạng thái và spinner dạng dấu chấm.

~~~java
import org.springframework.shell.component.view.control.Spinner;
import org.springframework.shell.style.FigureSettings;
import org.springframework.shell.style.SpinnerSettings;
import org.springframework.shell.style.StyleSettings;
import org.springframework.shell.style.ThemeSettings;

class OceanStyles extends StyleSettings {

    @Override
    public String title() {
        return "bold,fg:bright-cyan";
    }

    @Override
    public String highlight() {
        return "bold,fg:yellow";
    }

    @Override
    public String listLevelInfo() {
        return "fg:cyan";
    }

    @Override
    public String listLevelWarn() {
        return "bold,fg:yellow";
    }

    @Override
    public String listLevelError() {
        return "bold,fg:red";
    }
}

class OceanFigures extends FigureSettings {

    @Override
    public String tick() {
        return "✓";
    }

    @Override
    public String info() {
        return "ℹ";
    }

    @Override
    public String warning() {
        return "⚠";
    }

    @Override
    public String error() {
        return "✖";
    }
}

class OceanSpinners extends SpinnerSettings {

    @Override
    public Spinner dot() {
        return Spinner.of(
                new String[] {".", "o", "O", "o"},
                120);
    }
}

class OceanThemeSettings extends ThemeSettings {

    OceanThemeSettings() {
        super(
                new OceanStyles(),
                new OceanFigures(),
                new OceanSpinners());
    }
}
~~~

Các lớp trên chỉ ghi đè những tài nguyên muốn thay đổi. Những style, figure hoặc spinner khác tiếp tục dùng giá trị mặc định mà lớp cơ sở cung cấp.

### Đăng ký Theme thành Spring bean

Spring Shell tìm theme tùy chỉnh thông qua bean `Theme`. Có thể đăng ký bằng `Theme.of(name, settings)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.style.Theme;

@Configuration
public class TerminalThemeConfiguration {

    @Bean
    Theme oceanTheme() {
        return Theme.of("ocean", new OceanThemeSettings());
    }
}
~~~

`Theme` có hai thông tin: tên theme và `ThemeSettings`. `ThemeRegistry` lưu các theme theo tên để `ThemeResolver` có thể tìm đúng cấu hình.

### Chọn theme trong application.yml

Sau khi đăng ký bean, chọn theme bằng thuộc tính `spring.shell.theme.name`:

~~~yaml
spring:
  shell:
    theme:
      name: ocean
~~~

Nếu cần output thuần văn bản, đặt:

~~~yaml
spring:
  shell:
    theme:
      name: dump
~~~

Theme được chọn khi ứng dụng khởi tạo. Chỉ đổi giá trị trong file cấu hình khi ứng dụng đang chạy không tự động làm các view hiện tại thay đổi theme; nếu muốn chọn theme ở runtime, dùng `ThemeResolver` hoặc cấu hình theme cho `TerminalUI` tương ứng.

## 6. Dùng ThemeResolver để tra cứu tài nguyên

`ThemeResolver` là dịch vụ tra cứu style, figure và spinner theo tag. Trong ứng dụng Spring, có thể inject bean này:

~~~java
import org.jline.utils.AttributedStyle;
import org.springframework.stereotype.Component;
import org.springframework.shell.component.view.control.Spinner;
import org.springframework.shell.style.FigureSettings;
import org.springframework.shell.style.SpinnerSettings;
import org.springframework.shell.style.StyleSettings;
import org.springframework.shell.style.ThemeResolver;

@Component
public class TerminalThemeSupport {

    private final ThemeResolver themeResolver;

    public TerminalThemeSupport(ThemeResolver themeResolver) {
        this.themeResolver = themeResolver;
    }

    public void inspectThemeResources() {
        String titleSpec =
                themeResolver.resolveStyleTag(StyleSettings.TAG_TITLE);
        AttributedStyle titleStyle =
                themeResolver.resolveStyle(titleSpec);

        String errorFigure =
                themeResolver.resolveFigureTag(FigureSettings.TAG_ERROR);
        Spinner progressSpinner =
                themeResolver.resolveSpinnerTag(SpinnerSettings.TAG_DOT);
    }
}
~~~

`resolveStyleTag()` trả về style expression theo theme đang hoạt động. `resolveStyle()` chuyển expression đó thành `AttributedStyle` của JLine. `resolveFigureTag()` trả về ký tự tương ứng, còn `resolveSpinnerTag()` trả về một `Spinner`.

Nếu cần tra cứu style của một theme cụ thể, dùng overload nhận tên theme:

~~~java
String oceanTitle = themeResolver.resolveStyleTag(
        StyleSettings.TAG_TITLE,
        "ocean");
~~~

Có thể dùng `themeResolver.themeNames()` để lấy danh sách tên theme đã đăng ký. Nếu tag không có trong theme, hãy kiểm tra tag và việc đăng ký theme thay vì tự ghép ANSI sequence trong code nghiệp vụ.

## 7. Chọn theme cho một TerminalUI riêng

Theme toàn ứng dụng được chọn bằng `spring.shell.theme.name`. Với ứng dụng có nhiều màn hình terminal UI, một view có thể cần giao diện riêng. `TerminalUIBuilder` cho phép truyền `ThemeResolver` và tên theme khi tạo UI:

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.style.ThemeResolver;

public TerminalUI createAdminUi(
        Terminal terminal,
        ThemeResolver themeResolver) {

    return new TerminalUIBuilder(terminal)
            .themeResolver(themeResolver)
            .themeName("ocean")
            .build();
}
~~~

`TerminalUI` cũng có `setThemeName(...)` và `setThemeResolver(...)`. Các control/view có hỗ trợ theme có thể nhận cùng resolver và tên theme. Điều này cho phép một màn hình chọn theme khác với theme đang hoạt động của shell, miễn là theme đó đã được đăng ký.

Không phải mọi command text thông thường đều tự có theme riêng. Cơ chế theme theo view chủ yếu áp dụng cho các thành phần terminal UI dùng `ThemeResolver`. Với output command thông thường, hãy dùng kết quả rendering và style tag được Spring Shell hỗ trợ.

## 8. Dùng style tag thay vì gắn màu trực tiếp vào nghiệp vụ

Giả sử command hiển thị kết quả kiểm tra:

~~~text
Kiểm tra kết nối
Database: OK
Storage: WARNING
Queue: ERROR
~~~

Phần nghiệp vụ nên xác định trạng thái `OK`, `WARNING`, `ERROR`; tầng hiển thị chọn style và figure tương ứng. Khi đổi theme, cùng trạng thái có thể được thể hiện bằng màu và ký hiệu khác mà không sửa logic kiểm tra.

Một số nguyên tắc:

- Dùng tag ngữ nghĩa như `TAG_TITLE`, `TAG_LEVEL_INFO`, `TAG_LEVEL_WARN`, `TAG_LEVEL_ERROR`.
- Dùng figure riêng cho thành công, cảnh báo và lỗi.
- Giữ nguyên nội dung thông tin khi tắt màu.
- Không nhúng ANSI escape code trực tiếp vào service/domain.
- Không dùng màu làm dấu hiệu duy nhất; thêm nhãn hoặc ký hiệu.
- Dùng theme `dump` để kiểm tra output khi không có màu và Unicode.

Nếu dùng template StringTemplate (ST), Spring Shell có `StringToStyleExpressionRenderer` để chuyển chuỗi style expression thành định dạng JLine dựa trên `ThemeResolver`. Điều này giúp template dùng tag/style theo theme thay vì chứa mã màu cố định.

## 9. Tương thích terminal và fallback

Không phải terminal nào cũng hỗ trợ cùng một tập tính năng. Môi trường có thể giới hạn màu, không hỗ trợ true color, hiển thị ký tự Unicode không đúng hoặc xử lý ký tự có độ rộng khác nhau.

| Khả năng | Rủi ro | Cách xử lý |
|---|---|---|
| ANSI color | Output có mã escape khi bị redirect hoặc terminal không hỗ trợ | Chọn theme `dump` cho môi trường không màu |
| RGB/true color | Terminal chỉ hỗ trợ 8 hoặc 16 màu | Dùng biểu thức fallback về màu cơ bản |
| Unicode figure | Font hoặc encoding không hiển thị đúng ký tự | Dùng ký hiệu ASCII đơn giản hoặc theme `dump` |
| Spinner animation | CI/log collector không xử lý cập nhật cùng dòng | Dùng thông báo tiến độ theo dòng |
| Độ rộng ký tự | Emoji hoặc ký tự full-width làm lệch bố cục | Dùng figure có độ rộng ổn định trong bảng/menu |

Một theme tốt vẫn truyền tải đủ ý nghĩa khi màu bị loại bỏ. Ví dụ, `ERROR` nên có nhãn hoặc dấu `!`, không chỉ dùng màu đỏ. Khi cần output có thể lưu vào log, hãy kiểm tra kết quả với `dump`.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Theme tùy chỉnh không được chọn | Bean `Theme` chưa được đăng ký hoặc tên cấu hình không khớp | Kiểm tra component/configuration scan và `spring.shell.theme.name` |
| Theme không đổi sau khi sửa YAML | Ứng dụng chưa khởi động lại | Khởi động lại ứng dụng với cấu hình mới |
| Style tag trả về giá trị không mong đợi | Tag không tồn tại hoặc theme khác đang hoạt động | Kiểm tra hằng số tag và tên theme |
| Màu không xuất hiện | Terminal không hỗ trợ ANSI hoặc đang dùng theme `dump` | Kiểm tra terminal và theme đang chọn |
| Ký hiệu bị lỗi font | Terminal không hỗ trợ glyph hoặc encoding | Dùng ASCII figure hoặc theme `dump` |
| Spinner không chạy | UI không được redraw hoặc đang ở non-interactive mode | Kiểm tra vòng đời view và dùng thông báo theo dòng khi chạy script |
| Theme của một view không đổi | View chưa nhận `ThemeResolver` hoặc `themeName` | Cấu hình bằng `TerminalUIBuilder` hoặc setter tương ứng |
| Template không áp dụng style | Renderer chưa được đăng ký với template executor | Kiểm tra cấu hình `StringToStyleExpressionRenderer` |
| Nội dung chỉ phân biệt bằng màu | Người dùng/terminal không thể nhận ra màu | Bổ sung nhãn và figure cho từng trạng thái |

## 11. Checklist thiết kế theme

- Tách style, figure và spinner thành ba nhóm tài nguyên rõ ràng.
- Dùng tag ngữ nghĩa thay vì màu hoặc ký hiệu hard-code.
- Đăng ký theme tùy chỉnh bằng bean `Theme`.
- Chọn theme toàn ứng dụng bằng `spring.shell.theme.name`.
- Dùng `dump` để kiểm tra output không màu và không phụ thuộc ký hiệu đặc biệt.
- Dùng `ThemeResolver` để tra cứu tag và style expression.
- Chỉ đặt theme riêng cho view khi UI thực sự cần giao diện khác.
- Kiểm tra độ rộng ký tự và font của terminal.
- Không dựa hoàn toàn vào màu để truyền đạt trạng thái.
- Kiểm tra output ở terminal tương tác và khi chuyển hướng sang file/log.

## 12. Bài tập thực hành

Tạo một ứng dụng Spring Shell có command `system status`:

1. Hiển thị ba trạng thái `Database`, `Storage` và `Queue`.
2. Tạo `OceanStyles` để định nghĩa style cho tiêu đề, thông tin, cảnh báo và lỗi.
3. Tạo `OceanFigures` để định nghĩa ký hiệu thành công, thông tin, cảnh báo và lỗi.
4. Tạo `OceanSpinners` với spinner riêng bằng `Spinner.of(...)`.
5. Ghép ba nhóm trong `OceanThemeSettings` và đăng ký bean `Theme` tên `ocean`.
6. Chọn theme `ocean` bằng `spring.shell.theme.name`.
7. Chạy command và quan sát style/figure trong terminal hỗ trợ ANSI và Unicode.
8. Đổi theme sang `dump`, xác nhận thông tin vẫn hiểu được khi không có màu và ký hiệu đặc biệt.
9. Tạo một `TerminalUI` riêng dùng theme `ocean` qua `TerminalUIBuilder`.
10. Giải thích sự khác nhau giữa style tag, figure tag và spinner tag; chỉ ra nơi nào cần `ThemeResolver`.

Khi hoàn thành, hãy mô tả cách thay đổi theme mà không sửa logic nghiệp vụ của command.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Theming](https://spring-doc.cn/spring-shell/3.3.3/customization_styling.en.html): hệ thống theme, style, figure và đăng ký theme tùy chỉnh.
- [Spring Shell 3.3 – Theming Internals](https://spring-doc.cn/spring-shell/3.3.3/appendices_techintro_theming.en.html): cú pháp style expression của JLine và cách phân tích màu.
- [Spring Shell 3.3 – StyleSettings API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/style/StyleSettings.html): tag và cài đặt style.
- [Spring Shell 3.3 – FigureSettings API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/style/FigureSettings.html): ký hiệu và figure tag.
- [Spring Shell 3.3 – SpinnerSettings API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/style/SpinnerSettings.html): spinner tag và tài nguyên spinner.
- [Spring Shell 3.3 – ThemeSettings API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/style/ThemeSettings.html): kết hợp style, figure và spinner settings.
- [Spring Shell 3.3 – ThemeResolver API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/style/ThemeResolver.html): tra cứu style, figure, spinner theo tag và tên theme.
- [Spring Shell 3.3 – TerminalUIBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUIBuilder.html): cấu hình theme cho terminal UI.
- [JLine 3 – Terminal](https://jline.org/versions/3.x/docs/terminal/): nền tảng terminal mà Spring Shell sử dụng để hiển thị output.
