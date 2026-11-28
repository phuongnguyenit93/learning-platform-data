# Kích thước terminal, xuống dòng và bố trí thích ứng

Terminal không có kích thước cố định. Người dùng có thể mở cửa sổ rộng 140 cột, thu nhỏ còn 60 cột, kết nối qua SSH với một terminal thấp hoặc chạy command trong môi trường không có TTY. Nếu CLI luôn in bảng với các cột cố định, nội dung có thể bị tràn, cắt mất hoặc khó đọc.

Spring Shell dùng JLine để làm việc với terminal trong chế độ tương tác. JLine cung cấp kích thước hiện tại, tín hiệu thay đổi kích thước và các tiện ích xử lý văn bản theo số ô hiển thị. Spring Shell cũng có API dựng bảng nhận chiều rộng khả dụng để tính kích thước cột và xuống dòng. Bài học này hướng dẫn cách dùng những khả năng đó để hiển thị gọn trên terminal rộng lẫn hẹp.

## 1. Terminal được đo bằng cột và dòng

Kích thước terminal được biểu diễn bằng hai giá trị:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Columns | Số ô ký tự theo chiều ngang | `120` cột |
| Rows | Số dòng hiển thị theo chiều dọc | `30` dòng |

Một terminal có kích thước `120 x 30` nghĩa là cửa sổ hiển thị có 120 cột và 30 dòng. Cột là đơn vị ô hiển thị, không phải số byte UTF-8 hay số phần tử `char` của Java.

Chiều rộng ảnh hưởng đến cách bố trí bảng, tiêu đề và văn bản dài. Chiều cao ảnh hưởng đến số dòng có thể hiển thị cùng lúc, kích thước menu và cách phân trang. Không nên giả định mọi người dùng đều có terminal 80 cột x 24 dòng.

## 2. Đọc kích thước terminal bằng JLine

Trong Spring Shell 4.0.3, cấu hình JLine cung cấp bean `org.jline.terminal.Terminal` cho shell tương tác. Có thể inject bean này vào command hoặc service trình bày để lấy kích thước hiện tại:

```java
import org.jline.terminal.Size;
import org.jline.terminal.Terminal;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class TerminalCommands {

    private final Terminal terminal;

    public TerminalCommands(Terminal terminal) {
        this.terminal = terminal;
    }

    @Command(name = "terminal-size")
    public String terminalSize() {
        Size size = terminal.getSize();
        return "Kích thước terminal: " + size.getColumns()
                + " cột x " + size.getRows() + " dòng";
    }
}
```

`Terminal.getSize()` trả về `Size`; dùng `getColumns()` và `getRows()` để đọc số cột và số dòng. Spring Shell 4.0.3 tạo terminal thông qua `JLineShellAutoConfiguration`/`DefaultJLineShellConfiguration`. <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/JLineShellAutoConfiguration.html" title="JLineShellAutoConfiguration API — Spring Shell 4.0.3"/> · <Link url="https://jline.org/versions/3.x/docs/terminal/" title="JLine 3 — Terminal API"/>.

Ví dụ trên dành cho ứng dụng có JLine terminal bean. Nếu ứng dụng còn chạy bằng runner không dùng JLine hoặc chạy non-interactive, hãy dùng `ObjectProvider<Terminal>` hoặc một cấu hình chiều rộng riêng để tránh phụ thuộc bắt buộc vào terminal tương tác.

## 3. Xử lý khi kích thước không xác định

Trong terminal giả lập, pipe hoặc môi trường không có TTY, kích thước có thể bằng `0` hoặc không được phát hiện đúng. Không dùng trực tiếp giá trị đó để tính chiều rộng cột hoặc chia trang.

```java
Size size = terminal.getSize();

int columns = size.getColumns();
int rows = size.getRows();

if (columns <= 0) {
    columns = 80;
}
if (rows <= 0) {
    rows = 24;
}
```

80 cột và 24 dòng là giá trị fallback thông dụng, không phải kích thước bắt buộc của mọi terminal. Nếu ứng dụng có cấu hình `cli.output.width`, có thể ưu tiên cấu hình đó khi không phát hiện được terminal. Với output dành cho máy đọc như JSON, nên giữ cấu trúc dữ liệu ổn định và không chèn line wrap theo chiều rộng terminal.

JLine lưu ý size detection có thể không hoạt động trong non-interactive terminal; khi xây dựng giao diện tương tác, cần có fallback hợp lý và thông báo nếu terminal quá nhỏ cho một màn hình đặc biệt. <Link url="https://jline.org/docs/troubleshooting/" title="JLine Troubleshooting — Terminal Size"/>.

## 4. Dùng chiều rộng để chọn bố cục

Thay vì ép mọi terminal dùng cùng một bảng, hãy xác định một vài ngưỡng bố cục. Các ngưỡng này là quyết định thiết kế của ứng dụng, không phải giới hạn của Spring Shell.

| Chiều rộng | Bố cục gợi ý | Cách trình bày |
| ---: | --- | --- |
| Dưới 60 cột | Compact | Mỗi bản ghi thành nhóm key-value theo chiều dọc |
| 60–99 cột | Medium | Bảng rút gọn, chỉ giữ cột quan trọng |
| Từ 100 cột | Wide | Bảng nhiều cột và mô tả chi tiết |

Ví dụ, danh sách dự án có thể hiển thị bảng `ID | Tên | Trạng thái | Cập nhật` ở terminal rộng. Khi terminal hẹp, bỏ cột cập nhật và trình bày từng dự án thành ba dòng. Người dùng vẫn đọc được thông tin chính mà không phải cuộn ngang.

Đừng chọn ngưỡng chỉ dựa trên một máy phát triển. Hãy thử trên terminal 60, 80, 100 và 140 cột để biết cách bố trí có hoạt động trong điều kiện thực tế hay không.

## 5. Dựng bảng theo chiều rộng khả dụng

Spring Shell 4.0.3 có `TableModel`, `TableBuilder` và `Table`. `Table.render(int totalAvailableWidth)` nhận tổng chiều rộng được phép sử dụng. `TableBuilder` mặc định áp dụng chiến lược tự tính kích thước cột, cố gắng tận dụng không gian và xuống dòng tại dấu cách khi cần.

Ví dụ sau dựng bảng danh sách dự án và truyền chiều rộng terminal vào renderer:

```java
import java.util.List;
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModel;

public String renderProjects(List<ProjectSummary> projects, int terminalColumns) {
    TableModel model = new TableModel() {

        @Override
        public int getRowCount() {
            return projects.size() + 1;
        }

        @Override
        public int getColumnCount() {
            return 3;
        }

        @Override
        public Object getValue(int row, int column) {
            if (row == 0) {
                return switch (column) {
                    case 0 -> "ID";
                    case 1 -> "Tên dự án";
                    default -> "Trạng thái";
                };
            }

            ProjectSummary project = projects.get(row - 1);
            return switch (column) {
                case 0 -> project.id();
                case 1 -> project.name();
                default -> project.status();
            };
        }
    };

    int availableWidth = Math.max(20, terminalColumns - 2);
    Table table = new TableBuilder(model).build();
    return table.render(availableWidth);
}
```

`ProjectSummary` là kiểu dữ liệu của ứng dụng, có các accessor `id()`, `name()` và `status()`. Hàng đầu tiên trong ví dụ là tiêu đề. Hai cột trừ đi dành cho lề trái và phải; hãy điều chỉnh theo border hoặc prefix mà ứng dụng thêm vào output.

API `Table` áp dụng formatter, giới hạn kích thước cột, chính sách wrap và căn lề theo từng cell. <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html" title="Table API — Spring Shell 4.0.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html" title="TableBuilder API — Spring Shell 4.0.3"/>.

## 6. Chọn bảng hay bố cục key-value

Bảng phù hợp khi người dùng cần so sánh nhiều bản ghi theo cùng một tập thuộc tính. Bố cục key-value phù hợp khi terminal hẹp hoặc mỗi bản ghi có nhiều nội dung không đồng đều.

```text
ID: PRJ-102
Tên: Cổng quản lý đơn hàng
Trạng thái: Đang triển khai

ID: PRJ-103
Tên: Đồng bộ kho hàng
Trạng thái: Chờ xử lý
```

Ví dụ chọn layout trong command:

```java
import java.util.List;
import org.springframework.shell.core.command.annotation.Command;

// Giả sử class đã inject Terminal và ProjectService.
@Command(name = "projects")
public String projects() {
    List<ProjectSummary> values = projectService.findAll();
    int columns = terminal.getSize().getColumns();
    if (columns <= 0) {
        columns = 80;
    }

    if (columns < 60) {
        return renderKeyValue(values);
    }
    return renderProjects(values, columns);
}
```

`renderKeyValue` và `renderProjects` là các phương thức trình bày riêng. Cách tách này giúp command không phải chứa nhiều logic định dạng và dễ kiểm thử từng layout.

## 7. Xuống dòng tại ranh giới từ

Khi một đoạn văn dài hơn chiều rộng cột, nên ngắt ở dấu cách gần nhất để giữ nguyên từ. `TableBuilder` mặc định dùng cách wrap tại dấu cách. Spring Shell cũng cung cấp `DelimiterTextWrapper`, một `TextWrapper` ngắt theo delimiter; mặc định delimiter là dấu cách.

Với bảng, có thể áp dụng wrapper cho một cell hoặc một nhóm cell bằng `TableBuilder.CellMatcherStub.addWrapper(...)`. `TextWrapper.wrap(...)` nhận nội dung gốc và chiều rộng cột, rồi trả về các dòng đã căn theo độ rộng đó. <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/DelimiterTextWrapper.html" title="DelimiterTextWrapper API — Spring Shell 4.0.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TextWrapper.html" title="TextWrapper API — Spring Shell 4.0.3"/>.

Không nên ngắt tùy tiện giữa các từ khi hiển thị câu mô tả. Với URL, đường dẫn file, UUID hoặc chuỗi không có dấu cách, cần chọn chính sách riêng: wrap theo ký tự, rút gọn có dấu `…`, hoặc in nguyên chuỗi trên dòng riêng để người dùng có thể sao chép.

## 8. Xử lý chuỗi dài không có dấu cách

Chiến lược wrap theo dấu cách không thể chia một token dài như:

```text
https://example.internal/api/v1/deployments/very-long-resource-identifier
```

Nếu giữ nguyên chuỗi trong một cell hẹp, nó có thể tràn khỏi bảng. Có ba cách xử lý thường gặp:

| Cách xử lý | Khi nên dùng | Ví dụ |
| --- | --- | --- |
| Truncate | Cột chỉ để nhận diện nhanh | `https://example...` |
| Break token | Người dùng cần đọc toàn bộ giá trị | Ngắt theo `/`, `-` hoặc ký tự an toàn |
| Dòng riêng | Giá trị cần sao chép chính xác | In URL ở dòng dưới nhãn `URL:` |

Nếu rút gọn, đừng làm mất dữ liệu gốc. Có thể hiển thị giá trị ngắn trong bảng và cung cấp command `show <id>` để xem đầy đủ. Với output JSON hoặc CSV, luôn giữ giá trị gốc; không truncate dữ liệu máy đọc chỉ vì terminal hẹp.

## 9. Chiều cao terminal và phân trang

Rows cho biết số dòng hiển thị theo chiều dọc. Khi in danh sách dài, có thể dùng chiều cao để xác định số bản ghi mỗi trang:

```java
int rows = terminal.getSize().getRows();
if (rows <= 0) {
    rows = 24;
}

int reservedRows = 5; // tiêu đề, trạng thái, prompt và khoảng trống
int pageSize = Math.max(1, rows - reservedRows);
```

`pageSize` chỉ là số dòng dự kiến cho mỗi trang; nếu một bản ghi tự wrap thành nhiều dòng, cần tính số dòng thực tế thay vì số bản ghi. Với danh sách lớn, nên hỗ trợ tham số `--limit`/`--offset`, `--page` hoặc command lọc để người dùng không phải in toàn bộ dữ liệu.

Trong interactive mode, có thể dùng component selector hoặc pager phù hợp. Trong non-interactive mode, không chờ phím người dùng để chuyển trang; hãy in dữ liệu theo giới hạn rõ ràng hoặc xuất file.

## 10. Phản ứng khi người dùng thay đổi kích thước cửa sổ

JLine phát tín hiệu `WINCH` khi kích thước terminal thay đổi. Ứng dụng có giao diện toàn màn hình hoặc màn hình tự vẽ có thể đăng ký signal handler, đọc lại `terminal.getSize()` và render lại theo kích thước mới.

Ví dụ tối giản đánh dấu cần render lại:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.jline.terminal.Size;
import org.jline.terminal.Terminal;

AtomicBoolean resizeRequested = new AtomicBoolean(false);

terminal.handle(Terminal.Signal.WINCH,
        signal -> resizeRequested.set(true));

// Trong event loop của giao diện:
if (resizeRequested.getAndSet(false)) {
    Size newSize = terminal.getSize();
    renderScreen(newSize.getColumns(), newSize.getRows());
}
```

Không nên thực hiện render phức tạp trực tiếp trong signal handler. Hãy đặt một cờ hoặc gửi event về event loop của giao diện rồi vẽ lại ở luồng phù hợp. Nếu tự đăng ký handler trong một component, cần giữ và khôi phục handler trước đó khi component kết thúc để không ghi đè cách JLine đang quản lý tín hiệu. <Link url="https://jline.org/docs/advanced/terminal-size/" title="JLine — Terminal Size and Resize Events"/>.

Với command thông thường chỉ in kết quả một lần, không cần tự xử lý resize signal. Chỉ cần đọc chiều rộng ngay trước khi render. Resize listener phù hợp với TUI, dashboard hoặc màn hình liên tục cập nhật.

## 11. Component UI có thể nhận `terminalWidth`

Trong Spring Shell 4.0.3, `ComponentContext` có thuộc tính `terminalWidth` kiểu `Integer`; giá trị có thể là `null` nếu chưa được thiết lập. Renderer dùng context này để điều chỉnh layout:

```java
Integer width = context.getTerminalWidth();
int availableWidth = (width == null || width <= 0) ? 80 : width;

if (availableWidth < 60) {
    return renderCompact(context);
}
return renderWide(context, availableWidth);
```

Trong renderer thực tế, `context` là kiểu context cụ thể của component, ví dụ `StringInputContext` hoặc context do ứng dụng định nghĩa. Tài liệu render mô tả `terminalWidth` là chiều rộng terminal và có thể không được thiết lập. <Link url="https://docs.spring.io/spring-shell/reference/components/ui/render.html" title="Component Render — Spring Shell 4.0.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/context/ComponentContext.html" title="ComponentContext API — Spring Shell 4.0.3"/>.

## 12. Độ rộng Unicode khác `String.length()`

Java `String.length()` đếm UTF-16 code unit, không đếm số ô hiển thị trên terminal. Một ký tự CJK thường chiếm hai cột; dấu kết hợp có thể chiếm không cột; emoji có thể gồm nhiều code point nhưng được terminal hiển thị thành một grapheme cluster.

Ví dụ:

```java
import org.jline.utils.WCWidth;

int latinWidth = WCWidth.wcwidth('A');       // 1 cột
int cjkWidth = WCWidth.wcwidth(0x4F60);      // thường là 2 cột
int combiningWidth = WCWidth.wcwidth(0x0301); // 0 cột
```

`WCWidth.wcwidth(int)` nhận Unicode code point và trả độ rộng ô hiển thị. Spring Shell 4.0.3 dùng JLine 3.30.13. Với chuỗi có emoji ghép, cờ hoặc ký tự kết hợp, không nên chỉ cộng độ rộng từng `char`; cần xử lý grapheme cluster và kiểm tra cách terminal mục tiêu hiển thị. <Link url="https://www.javadoc.io/doc/org.jline/jline/3.30.13/org/jline/utils/WCWidth.html" title="WCWidth API — JLine 3.30.13"/> · <Link url="https://jline.org/versions/3.x/docs/advanced/unicode-support/" title="JLine 3 — Unicode Support"/>.

Khi căn cột thủ công, đừng dùng `String.length()` để thêm dấu cách cho nội dung tiếng Việt, tiếng Nhật hoặc emoji. Hãy dùng renderer hiểu display width, hoặc để Table/JLine xử lý căn chỉnh. Luôn thử trên terminal và font mà người dùng mục tiêu sử dụng.

## 13. Màu sắc và chuỗi điều khiển không chiếm cột hiển thị

ANSI escape sequence dùng để đổi màu, in đậm hoặc di chuyển con trỏ. Các byte điều khiển đó không phải ký tự hiển thị. Nếu đo độ dài chuỗi ANSI thô bằng `String.length()`, kết quả sẽ lớn hơn độ rộng thực tế và làm lệch cột.

Trong JLine, dùng `AttributedString` và `AttributedStyle` để gắn style vào nội dung thay vì tự nối escape sequence vào chuỗi rồi tính độ dài. Khi in, JLine có thể chuyển attributed string thành ANSI phù hợp với terminal. <Link url="https://jline.org/docs/advanced/attributed-strings/" title="JLine — Attributed Strings"/>.

Luôn có phương án hiển thị không màu. Terminal có thể không hỗ trợ màu hoặc người dùng có thể tắt màu trong môi trường automation. Không dùng màu làm tín hiệu duy nhất để phân biệt thành công, cảnh báo và lỗi; hãy thêm nhãn văn bản như `OK`, `WARN` hoặc `ERROR`.

## 14. Interactive output và non-interactive output

Chiều rộng terminal chỉ nên ảnh hưởng đến cách trình bày cho con người. Khi command được gọi trong script hoặc CI, output cần ổn định và dễ phân tích.

| Chế độ | Cách trình bày phù hợp |
| --- | --- |
| JLine interactive | Bảng co giãn, wrap, màu sắc và phân trang |
| Terminal không xác định được size | Fallback width, bố cục compact, không vẽ màn hình toàn phần |
| Script/CI | Dòng output rõ ràng, mã thoát ổn định, không chờ phím |
| JSON/CSV | Schema cố định, không chèn border, màu hoặc line wrap phụ thuộc terminal |

Có thể cung cấp `--format table|json|csv`. `table` dùng chiều rộng terminal; `json` và `csv` giữ cấu trúc ổn định để chương trình khác đọc. Không nên tự động đổi output thành JSON chỉ vì không phát hiện TTY nếu điều đó phá vỡ hợp đồng CLI đã công bố.

## 15. Kiểm thử bố cục với nhiều kích thước

Một lần chạy trên terminal phát triển không đủ để chứng minh layout thích ứng. Hãy kiểm thử nhiều kích thước và dữ liệu có độ rộng khác nhau.

| Kích thước giả lập | Trường hợp cần kiểm tra |
| --- | --- |
| 40 x 12 | Compact layout, không tràn ngang, ít dòng |
| 60 x 20 | Bảng rút gọn và wrap mô tả |
| 80 x 24 | Layout mặc định |
| 120 x 30 | Bảng rộng và cột bổ sung |
| 0 x 0 hoặc unknown | Fallback cho non-TTY |

Kiểm tra thêm:

- Tên dự án rất dài, URL, đường dẫn và UUID không có dấu cách.
- Tiếng Việt có dấu, ký tự CJK, emoji và dấu kết hợp.
- Terminal được thu nhỏ rồi mở rộng trong lúc TUI đang hiển thị.
- Nội dung dài hơn số dòng terminal và hành vi phân trang.
- Terminal không hỗ trợ màu hoặc ký tự vẽ khung.
- Output JSON/CSV không thay đổi theo chiều rộng terminal.

Spring Shell có `ShellTestClient` để kiểm tra command output và hành vi command. Để xác nhận resize signal, số cột thực tế và cách terminal vẽ Unicode, nên chạy thêm integration test với pseudo-terminal hoặc terminal emulator; unit test thuần không mô phỏng đầy đủ mọi đặc tính terminal. <Link url="https://docs.spring.io/spring-shell/reference/testing.html" title="Spring Shell — Testing"/>.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bảng tràn sang phải | Dùng chiều rộng cố định hoặc không trừ lề/border | Đọc `getSize().getColumns()` và truyền width vào `Table.render` |
| Bảng quá chật | Quá nhiều cột hoặc cột có min width lớn | Bỏ cột phụ, chuyển sang key-value layout |
| Nội dung bị cắt giữa từ | Dùng substring theo số ký tự | Dùng word wrapping hoặc `TextWrapper` |
| URL/UUID vẫn tràn | Wrapper chỉ ngắt tại dấu cách | Truncate, break theo delimiter hoặc in dòng riêng |
| Căn cột tiếng Việt bị lệch | Dùng `String.length()` | Tính display width bằng JLine hoặc dùng renderer hỗ trợ Unicode |
| Resize không cập nhật | Không đọc lại terminal size hoặc không xử lý `WINCH` trong TUI | Đánh dấu redraw và render lại từ event loop |
| Giao diện vỡ khi chạy qua pipe | Không có TTY hoặc size bằng 0 | Dùng fallback và chế độ output không tương tác |
| Màu làm lệch căn cột | Đo chuỗi có ANSI escape thô | Dùng `AttributedString` của JLine |
| Output CI thay đổi theo máy | Dùng layout tương tác làm output máy đọc | Cung cấp JSON/CSV hoặc định dạng ổn định |

## 17. Bài thực hành tổng hợp

Tạo command `projects` hiển thị danh sách dự án thích ứng với terminal:

1. Inject `org.jline.terminal.Terminal` trong ứng dụng Spring Shell chạy JLine.
2. Đọc `columns` và `rows` từ `terminal.getSize()`; đặt fallback khi size không xác định.
3. Dùng `TableModel` và `TableBuilder` để render danh sách ở terminal rộng.
4. Khi terminal hẹp hơn 60 cột, chuyển sang bố cục key-value theo chiều dọc.
5. Giới hạn chiều rộng bảng bằng `Table.render(totalAvailableWidth)` và kiểm tra lề.
6. Thử mô tả dài, URL, UUID và tên dự án tiếng Việt; chọn wrap hoặc truncate phù hợp.
7. Nếu xây dựng TUI, xử lý `WINCH` để render lại khi terminal đổi kích thước.
8. Thêm `--format json` để output máy đọc không phụ thuộc terminal width.
9. Kiểm thử trên 40, 60, 80, 120 cột và một môi trường không có TTY.

Sau bài thực hành, bạn cần giải thích được vì sao terminal dùng columns/rows, cách chọn layout theo width, vì sao `String.length()` không phải display width, và vì sao output cho CI cần tách khỏi giao diện tương tác.

## 18. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Terminal geometry | Đọc đúng số cột và số dòng bằng JLine `Terminal` |
| Fallback | Xử lý size không xác định hoặc non-TTY |
| Responsive layout | Chọn được bảng rộng, bảng rút gọn và key-value layout |
| Table rendering | Truyền chiều rộng khả dụng cho `Table.render(...)` |
| Wrapping | Ngắt theo từ và xử lý token không có dấu cách |
| Resize | Render lại TUI khi nhận tín hiệu thay đổi kích thước |
| Unicode | Phân biệt code unit, code point và display cell width |
| Styling | Không để ANSI escape sequence làm sai phép đo chiều rộng |
| Automation | Giữ output JSON/CSV ổn định, không phụ thuộc terminal |
| Testing | Kiểm tra nhiều kích thước và terminal không tương tác |

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — JLineShellAutoConfiguration](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/JLineShellAutoConfiguration.html)
- [Spring Shell 4.0.3 — Table API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html)
- [Spring Shell 4.0.3 — TableBuilder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html)
- [Spring Shell 4.0.3 — TextWrapper API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TextWrapper.html)
- [Spring Shell 4.0.3 — Component Render](https://docs.spring.io/spring-shell/reference/components/ui/render.html)
- [JLine — Terminal Size](https://jline.org/docs/advanced/terminal-size/)
- [JLine — Terminal API](https://jline.org/docs/terminal/)
- [JLine — Unicode Support](https://jline.org/docs/advanced/unicode-support/)
- [JLine — Attributed Strings](https://jline.org/docs/advanced/attributed-strings/)
- [JLine 3.30.13 — WCWidth API](https://www.javadoc.io/doc/org.jline/jline/3.30.13/org/jline/utils/WCWidth.html)
