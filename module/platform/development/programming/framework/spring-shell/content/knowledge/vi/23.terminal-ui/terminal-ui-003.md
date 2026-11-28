# BoxView, GridView và bố trí nội dung

Khi một command cần hiển thị dashboard hoặc một màn hình có nhiều vùng nội dung, việc ghi từng dòng bằng `System.out` sẽ khó kiểm soát vị trí, kích thước và cách bố trí khi terminal thay đổi kích thước. Spring Shell 3.x cung cấp hệ thống `View` để vẽ giao diện trên một vùng terminal. `BoxView` tạo một khung nội dung có tiêu đề và đường viền; `GridView` sắp xếp nhiều view con theo hàng, cột và vùng chiếm chỗ.

Bài học thuộc chương **Terminal UI 3.x**. Nội dung tập trung vào vai trò của `BoxView`, cách tự vẽ nội dung trong khung, cách bố trí view bằng `GridView`, phân chia kích thước hàng/cột, ghép ô và tạo layout thích ứng theo kích thước terminal.

Sau bài học, bạn có thể:

- Phân biệt `BoxView` với `GridView`.
- Tạo khung có tiêu đề, border, padding và nền.
- Vẽ nội dung qua `setDrawFunction(...)` và `Screen.Writer`.
- Thêm view vào grid bằng `addItem(...)`.
- Chia kích thước hàng và cột theo độ rộng tuyệt đối hoặc tỷ lệ.
- Dùng `rowSpan`, `colSpan` và ngưỡng kích thước để thay đổi bố cục.
- Chạy view trong command bằng `ViewComponentBuilder`.
- Kiểm thử và xử lý terminal hẹp, resize, focus và vòng đời view.

## View, Control và Screen

Trong Terminal UI của Spring Shell 3.x, `Control` là thành phần có thể nhận một vùng hình chữ nhật (`Rectangle`) và vẽ nội dung vào `Screen`. `View` mở rộng `Control`, đại diện cho một thành phần hiển thị và có thể chứa các view lồng nhau.

Các khái niệm chính:

| Thành phần | Vai trò |
| --- | --- |
| `View` | Giao diện hiển thị có thể được vẽ và có thể chứa view con. |
| `Control` | Định nghĩa vùng hoạt động và phương thức vẽ lên `Screen`. |
| `Screen` | Vùng hiển thị ảo nằm giữa ứng dụng và JLine terminal. |
| `Screen.Writer` | API ghi text, border và background lên screen. |
| `TerminalUI` | Điều phối terminal, event loop, key/mouse event và cây view. |
| `ViewComponent` | Chạy một view trong vùng terminal không chiếm toàn màn hình. |

`BoxView` và `GridView` đều là `View`. `GridView` kế thừa `BoxView`, vì vậy nó vừa có thể có tiêu đề/viền ngoài, vừa quản lý các view con trong một lưới.

## Khi nào dùng BoxView và khi nào dùng GridView?

`BoxView` phù hợp khi cần một vùng nội dung có khung riêng: trạng thái dịch vụ, thông tin dự án, thông báo hoặc phần mô tả. `GridView` phù hợp khi có nhiều vùng cần sắp xếp theo bố cục hàng/cột.

| Nhu cầu | Component phù hợp | Ví dụ |
| --- | --- | --- |
| Hiển thị một khối thông tin có tiêu đề | `BoxView` | Trạng thái kết nối máy chủ. |
| Vẽ một đoạn text hoặc thông tin tùy chỉnh trong vùng cố định | `BoxView` + `setDrawFunction(...)` | Tóm tắt lần triển khai gần nhất. |
| Đặt hai hoặc nhiều khung cạnh nhau | `GridView` | Thẻ CPU và bộ nhớ. |
| Tạo dashboard có hàng/cột và ô chiếm nhiều cột | `GridView` | Bảng điều khiển vận hành. |
| Thay đổi bố cục theo chiều rộng terminal | `GridView` với ngưỡng `minGridWidth` | Màn hình một cột trên terminal hẹp, nhiều cột trên terminal rộng. |

Không cần tạo `GridView` nếu màn hình chỉ có một vùng nội dung. Ngược lại, không nên tự tính tọa độ cho nhiều `BoxView` bằng các hằng số rời rạc khi grid có thể quản lý vị trí và kích thước giúp bạn.

## BoxView: khung nội dung có tiêu đề và đường viền

`BoxView` là view cơ sở với nền rỗng và border/title tùy chọn. Có thể dùng trực tiếp hoặc làm lớp cha cho view tùy chỉnh.

Các phương thức thường dùng:

| Phương thức | Mục đích |
| --- | --- |
| `setTitle(String)` | Đặt tiêu đề nằm trên cạnh viền phía trên. |
| `setShowBorder(boolean)` | Bật hoặc tắt border. |
| `setBorderPadding(top, bottom, left, right)` | Đặt khoảng đệm bên trong border. |
| `setTitleAlign(HorizontalAlign)` | Căn tiêu đề. |
| `setTitleColor(int)` | Đặt màu tiêu đề. |
| `setTitleStyle(int)` | Đặt kiểu hiển thị tiêu đề. |
| `setFocusedTitleColor(int)` | Đặt màu tiêu đề khi view được focus. |
| `setFocusedTitleStyle(int)` | Đặt kiểu tiêu đề khi view được focus. |
| `setBackgroundColor(int)` | Đặt màu nền. |

Ví dụ tạo một khung thông tin:

```java
import org.springframework.shell.component.view.control.BoxView;

BoxView statusView = new BoxView();
statusView.setTitle("Deployment status");
statusView.setShowBorder(true);
statusView.setBorderPadding(1, 1, 2, 2);
```

`setTitle(...)` chỉ hiển thị tiêu đề khi border đang bật. `setBorderPadding(...)` nhận lần lượt padding phía trên, phía dưới, bên trái và bên phải.

## Vẽ nội dung bằng setDrawFunction

`BoxView` tạo khung nhưng không tự quyết định nội dung nghiệp vụ bên trong. `AbstractView` cung cấp `setDrawFunction(BiFunction<Screen, Rectangle, Rectangle>)`, được gọi sau khi view đã vẽ xong phần nền và nội dung cơ bản. Callback nhận `Screen` và vùng `Rectangle` của view, sau đó trả lại rectangle.

`Screen.Writer` có các cách ghi text:

- `text(String, int x, int y)` để ghi tại tọa độ cụ thể.
- `text(String, Rectangle, HorizontalAlign, VerticalAlign)` để căn text trong một vùng.
- `border(...)` để vẽ border theo tọa độ.
- `background(...)` để tô nền cho một vùng.

Ví dụ ghi nội dung vào bên trong khung:

```java
import org.springframework.shell.component.view.control.BoxView;

BoxView statusView = new BoxView();
statusView.setTitle("Deployment status");
statusView.setShowBorder(true);
statusView.setBorderPadding(1, 1, 2, 2);

statusView.setDrawFunction((screen, rect) -> {
    var writer = screen.writerBuilder().build();
    writer.text("Environment: staging", rect.x() + 1, rect.y() + 1);
    writer.text("Status: READY", rect.x() + 1, rect.y() + 2);
    return rect;
});
```

`Rectangle` trong Spring Shell 3.3.x là record có `x()`, `y()`, `width()` và `height()`. Vì vậy, nội dung có thể dựa vào vị trí và kích thước hiện tại của view thay vì ghi cố định từ góc trên bên trái của toàn terminal.

Nếu cần căn giữa một dòng trong vùng view:

```java
import org.springframework.shell.geom.HorizontalAlign;
import org.springframework.shell.geom.VerticalAlign;

statusView.setDrawFunction((screen, rect) -> {
    var writer = screen.writerBuilder().build();
    writer.text(
        "All services are healthy",
        rect,
        HorizontalAlign.CENTER,
        VerticalAlign.CENTER);
    return rect;
});
```

Callback vẽ lại nội dung khi view được render. Hãy giữ callback nhẹ và chỉ vẽ từ dữ liệu đã chuẩn bị; không gọi API mạng hoặc thực hiện truy vấn cơ sở dữ liệu trong mỗi lần vẽ. Nếu dữ liệu thay đổi, cập nhật model rồi yêu cầu UI redraw theo cơ chế phù hợp.

## GridView: bố trí nhiều view theo hàng và cột

`GridView` là một layout container kế thừa `BoxView`. Khi khởi tạo, grid chưa có view con. Dùng `addItem(...)` để đặt một view vào vị trí cụ thể:

```java
grid.addItem(view, row, column, rowSpan, colSpan,
             minGridHeight, minGridWidth);
```

| Tham số | Ý nghĩa |
| --- | --- |
| `view` | View con cần đặt vào grid. |
| `row` | Chỉ số hàng bắt đầu, tính từ `0`. |
| `column` | Chỉ số cột bắt đầu, tính từ `0`. |
| `rowSpan` | Số hàng mà view chiếm. |
| `colSpan` | Số cột mà view chiếm. |
| `minGridHeight` | Chiều cao tối thiểu của grid để vị trí này được áp dụng. |
| `minGridWidth` | Chiều rộng tối thiểu của grid để vị trí này được áp dụng. |

Nếu `rowSpan` hoặc `colSpan` bằng `0`, view không được vẽ ở vị trí đó. Các giá trị `minGridHeight` và `minGridWidth` được tính theo kích thước tổng thể của grid.

Ví dụ tạo grid 2 hàng, 2 cột:

```java
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.control.GridView;

GridView grid = new GridView();
grid.setShowBorder(true);
grid.setShowBorders(true);
grid.setTitle("Operations dashboard");

BoxView cpuView = new BoxView();
cpuView.setTitle("CPU");

BoxView memoryView = new BoxView();
memoryView.setTitle("Memory");

BoxView serviceView = new BoxView();
serviceView.setTitle("Services");

BoxView eventsView = new BoxView();
eventsView.setTitle("Recent events");

grid.addItem(cpuView, 0, 0, 1, 1, 0, 0);
grid.addItem(memoryView, 0, 1, 1, 1, 0, 0);
grid.addItem(serviceView, 1, 0, 1, 1, 0, 0);
grid.addItem(eventsView, 1, 1, 1, 1, 0, 0);
```

`setShowBorder(true)` bật border ngoài được kế thừa từ `BoxView`; `setShowBorders(true)` bật các đường phân cách của grid. Hai thuộc tính này phục vụ hai lớp đường viền khác nhau.

Bố cục có thể hình dung như sau:

```text
┌─────────────────────────────────────────────┐
│              Operations dashboard           │
├──────────────────────┬──────────────────────┤
│ CPU                  │ Memory               │
│                      │                      │
├──────────────────────┼──────────────────────┤
│ Services             │ Recent events        │
│                      │                      │
└──────────────────────┴──────────────────────┘
```

## Chia kích thước cột và hàng

`GridView.setColumnSize(int...)` điều khiển cách phân phối chiều rộng cột; `setRowSize(int...)` áp dụng quy tắc tương tự cho chiều cao hàng.

Quy tắc của giá trị kích thước:

- Giá trị lớn hơn `0`: kích thước tuyệt đối theo số ô terminal.
- Giá trị nhỏ hơn hoặc bằng `0`: phần tỷ lệ của không gian còn lại.
- `0` được hiểu giống `-1`.
- `-3` nhận tỷ lệ gấp ba lần một cột `-1`.

Ví dụ:

```java
grid.setColumnSize(-1, -2);
grid.setRowSize(0, 0);
```

Hai cột chia theo tỷ lệ `1:2`; hai hàng chia đều. Nếu không gọi `setColumnSize(...)`, các cột đang được sử dụng mặc định có cùng chiều rộng. Các cột được khai báo kích thước nhưng chưa có view vẫn chiếm chỗ trong layout.

Có thể trộn kích thước tuyệt đối và tỷ lệ:

```java
grid.setColumnSize(24, -1, -2);
```

Cột đầu rộng 24 ô; phần không gian còn lại chia theo tỷ lệ `1:2` cho hai cột sau. Kích thước tuyệt đối không bao gồm khoảng trống phân cách cột.

## Kích thước tối thiểu của grid

`setMinSize(minWidth, minHeight)` đặt kích thước tối thiểu cho grid. Các giới hạn tối thiểu luôn được tôn trọng khi tính kích thước hàng và cột.

```java
grid.setMinSize(60, 12);
```

Điều này có nghĩa grid có thể cần ít nhất 60 ô chiều rộng và 12 ô chiều cao. Nếu terminal nhỏ hơn kích thước tối thiểu, layout có thể vượt khỏi vùng terminal khả dụng. Vì vậy, hãy chọn giới hạn tối thiểu dựa trên nội dung thực tế và kiểm tra với terminal hẹp.

## Ghép nhiều hàng hoặc nhiều cột

`rowSpan` và `colSpan` cho phép một view chiếm nhiều ô. Ví dụ, một panel tổng quan chiếm toàn bộ hàng đầu, bên dưới là hai panel nhỏ:

```java
grid.addItem(summaryView, 0, 0, 1, 2, 0, 0);
grid.addItem(cpuView,     1, 0, 1, 1, 0, 0);
grid.addItem(memoryView,  1, 1, 1, 1, 0, 0);
```

`summaryView` bắt đầu ở hàng `0`, cột `0` và chiếm một hàng, hai cột. Hai view còn lại đặt cạnh nhau ở hàng tiếp theo.

Nếu view chiếm nhiều ô, hãy kiểm tra vùng hiển thị và nội dung của view để tránh chữ hoặc border chồng lên đường phân cách của grid.

## Bố cục thích ứng theo kích thước terminal

`GridView.addItem(...)` cho phép thêm cùng một view nhiều lần ở các vị trí khác nhau, mỗi vị trí có ngưỡng `minGridHeight` và `minGridWidth`. Grid chọn vị trí phù hợp nhất với kích thước hiện tại. Cách này có thể tạo bố cục một cột khi terminal hẹp và nhiều cột khi terminal rộng.

Ví dụ cùng một summary panel có cách bố trí khác nhau theo chiều rộng:

```java
// Ẩn panel ở layout quá hẹp.
grid.addItem(summaryView, 0, 0, 0, 0, 0, 0);

// Khi grid rộng từ 90 ô, panel chiếm toàn bộ hai cột đầu.
grid.addItem(summaryView, 0, 0, 1, 2, 0, 90);

// Khi grid rộng từ 140 ô, panel chuyển sang vị trí và kích thước khác.
grid.addItem(summaryView, 1, 1, 1, 2, 0, 140);
```

Trong mỗi lời gọi, hai tham số cuối lần lượt là ngưỡng chiều cao và chiều rộng. Khi nhiều vị trí của cùng view cùng thỏa điều kiện, vị trí có ngưỡng tối thiểu cao hơn được ưu tiên; nếu các ngưỡng bằng nhau, vị trí được thêm sau cùng được chọn. Đặt `rowSpan` hoặc `colSpan` bằng `0` là cách ẩn view ở một biến thể bố cục.

Để layout luôn giống nhau ở mọi kích thước, truyền `0` cho cả `minGridHeight` và `minGridWidth`. Với layout thích ứng, hãy xác định ngưỡng dựa trên chiều rộng nội dung tối thiểu mà panel cần để không bị cắt.

## Border và padding

`GridView` kế thừa các thuộc tính khung từ `BoxView` và bổ sung border phân cách giữa các ô:

| Phương thức | Phạm vi |
| --- | --- |
| `setShowBorder(true)` | Viền ngoài của toàn grid. |
| `setShowBorders(true)` | Các đường phân cách hàng/cột bên trong grid. |
| `setTitle(...)` | Tiêu đề trên viền ngoài. |
| `setBorderPadding(...)` | Padding bên trong khung ngoài. |

Không cần bật mọi border trong mọi màn hình. Với dashboard nhiều panel, border nội bộ giúp người dùng nhận ra từng vùng; với layout đơn giản, có thể chỉ giữ viền ngoài hoặc dùng khoảng trắng để phân tách.

## Chạy view trong command Spring Shell 3.x

Trong Spring Shell 3.x, `AbstractShellComponent` cung cấp `getViewComponentBuilder()` để tạo `ViewComponent`. Builder này được auto-configure cùng terminal, `TerminalUIBuilder` và executor.

`ViewComponentBuilder.build(view)` tạo component để chạy view trong vùng terminal không chiếm toàn màn hình. `runBlocking()` chạy event loop cho đến khi component yêu cầu thoát. `setUseTerminalWidth(true)` được bật mặc định.

Ví dụ command hiển thị dashboard:

```java
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.control.GridView;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class DashboardCommands extends AbstractShellComponent {

    @ShellMethod(key = "dashboard", value = "Hiển thị dashboard")
    public void dashboard() {
        BoxView cpu = createPanel("CPU", "Usage: 42%");
        BoxView memory = createPanel("Memory", "Used: 6.2 GB");
        BoxView services = createPanel("Services", "3 services healthy");
        BoxView events = createPanel("Recent events", "No new alerts");

        GridView grid = new GridView();
        grid.setTitle("System dashboard");
        grid.setShowBorder(true);
        grid.setShowBorders(true);
        grid.setBorderPadding(1, 1, 2, 2);
        grid.setColumnSize(-1, -1);
        grid.setRowSize(0, 0);

        grid.addItem(cpu, 0, 0, 1, 1, 0, 0);
        grid.addItem(memory, 0, 1, 1, 1, 0, 0);
        grid.addItem(services, 1, 0, 1, 1, 0, 0);
        grid.addItem(events, 1, 1, 1, 1, 0, 0);

        getViewComponentBuilder()
            .build(grid)
            .runBlocking();
    }

    private BoxView createPanel(String title, String message) {
        BoxView view = new BoxView();
        view.setTitle(title);
        view.setShowBorder(true);
        view.setBorderPadding(1, 1, 1, 1);
        view.setDrawFunction((screen, rect) -> {
            var writer = screen.writerBuilder().build();
            writer.text(message, rect.x() + 1, rect.y() + 1);
            return rect;
        });
        return view;
    }
}
```

Command tạo các panel, đặt chúng vào `GridView`, rồi chạy view bằng `ViewComponentBuilder`. Trong ứng dụng thực tế, dữ liệu của CPU, memory và services nên được lấy từ service trước khi vẽ. Không gọi service trong `setDrawFunction(...)`, vì callback có thể chạy nhiều lần khi terminal redraw hoặc resize.

## TerminalUI toàn màn hình

Nếu muốn tự quản lý một terminal UI độc lập chiếm toàn màn hình, có thể dùng `TerminalUIBuilder` và `TerminalUI`:

```java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.GridView;

TerminalUI terminalUI = terminalUIBuilder.build();
GridView root = new GridView();

terminalUI.configure(root);
terminalUI.setRoot(root, true);
terminalUI.run();
```

`TerminalUI` điều phối terminal, event loop và cây view. `configure(view)` gắn event loop, theme resolver, theme name và view service vào view. `setRoot(view, true)` đặt view gốc ở chế độ toàn màn hình; `run()` bắt đầu vòng lặp giao diện.

Trong command Spring Shell thông thường, `ViewComponentBuilder` thường phù hợp hơn vì nó quản lý view trong một vùng terminal không toàn màn hình và có tích hợp sẵn với `AbstractShellComponent`.

## Focus, event và vòng đời view

`View` có thể nhận focus và cung cấp `KeyHandler` hoặc `MouseHandler`. `GridView` quản lý vị trí các view con; các view con chịu trách nhiệm xử lý thao tác bàn phím hoặc chuột của riêng chúng. `GridView` không tự cung cấp các binding mặc định hay event nghiệp vụ.

Một số điểm cần nhớ:

- `init()` khởi tạo view và gọi `initInternal()`.
- `draw(...)` thực hiện vẽ nền rồi vẽ nội dung bên trong.
- `setDrawFunction(...)` đăng ký callback vẽ sau khi view đã được vẽ.
- `destroy()` dọn trạng thái đang chạy của view để view có thể được thu hồi.
- `ViewComponent.exit()` yêu cầu thoát event loop.

Nếu tự tạo view con có đăng ký key/mouse binding hoặc tài nguyên reactive, hãy giải phóng chúng trong lifecycle thích hợp. Tránh giữ reference đến view đã đóng trong singleton bean nếu mỗi lần mở dashboard tạo một cây view mới.

## Kiểm thử bố cục

Nên kiểm thử ở hai mức:

1. **Kiểm thử cấu hình:** xác nhận view được thêm đúng hàng/cột, span, border và sizing strategy.
2. **Kiểm thử terminal:** chạy view trong terminal giả lập, kiểm tra nội dung, border, resize, focus và cách layout thay đổi theo kích thước.

Các trường hợp nên có:

- Terminal rộng và terminal hẹp.
- Grid có hai cột tỷ lệ bằng nhau và grid có cột tỷ lệ khác nhau.
- View chiếm nhiều cột hoặc nhiều hàng.
- View bị ẩn khi span bằng `0`.
- Nhiều vị trí responsive cho cùng một view.
- Nội dung dài hơn vùng view.
- Thoát `ViewComponent` rồi mở lại dashboard.

Spring Shell 3.3.x có terminal test support và `ShellTestClient`; với bố cục TUI, cần kiểm tra screen buffer sau khi chạy view trong terminal giả lập hoặc integration test phù hợp. Kiểm tra bằng terminal thật cũng hữu ích vì font, chiều rộng ký tự và hỗ trợ Unicode có thể khác giữa các môi trường.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Khung có border nhưng không có nội dung | `BoxView` chỉ tạo khung; chưa đăng ký draw function hoặc view con. | Dùng `setDrawFunction(...)` hoặc đặt view vào `GridView`. |
| Tiêu đề không hiển thị | Border đang tắt. | Gọi `setShowBorder(true)`. |
| Grid trống | Chưa gọi `addItem(...)`. | Thêm các view con và xác định vị trí. |
| Không thấy đường chia hàng/cột | `setShowBorders(false)` hoặc chưa bật. | Gọi `setShowBorders(true)`. |
| Các cột có chiều rộng không như mong muốn | Giá trị `setColumnSize(...)` được hiểu là tỷ lệ hoặc kích thước tuyệt đối khác dự kiến. | Kiểm tra dấu và tỷ lệ từng giá trị. |
| Grid rộng hơn terminal | `setMinSize(...)` hoặc kích thước tuyệt đối lớn hơn vùng terminal. | Giảm kích thước tối thiểu và kiểm thử với terminal hẹp. |
| View không xuất hiện ở kích thước nhỏ | Ngưỡng `minGridWidth`/`minGridHeight` chưa thỏa hoặc span bằng `0`. | Kiểm tra hai ngưỡng cuối của `addItem(...)` và span. |
| Bố cục responsive chọn nhầm vị trí | Nhiều vị trí cùng thỏa điều kiện hoặc ngưỡng bị đặt sai. | Kiểm tra ngưỡng; vị trí có ngưỡng cao hơn được ưu tiên. |
| Nội dung bị đè lên border | Callback vẽ dùng tọa độ ngoài vùng trong của view. | Dựa trên `rect.x()`, `rect.y()` và chừa padding cho border. |
| Dashboard treo command | `ViewComponent.runBlocking()` vẫn đang chạy event loop. | Dùng thao tác thoát phù hợp hoặc gọi `ViewComponent.exit()` từ luồng điều khiển. |

## Checklist trước khi phát hành TUI

- [ ] Đã chọn `BoxView` cho khung đơn và `GridView` cho bố cục nhiều vùng.
- [ ] Mỗi BoxView có tiêu đề và border phù hợp.
- [ ] Padding để nội dung không chạm đường viền.
- [ ] Nội dung được vẽ bằng `Screen.Writer` trong draw function.
- [ ] Grid có view con và vị trí hàng/cột rõ ràng.
- [ ] Đã xác định tỷ lệ hoặc chiều rộng tuyệt đối cho cột/hàng.
- [ ] `rowSpan` và `colSpan` đúng với vùng cần chiếm.
- [ ] Ngưỡng responsive phù hợp với chiều rộng terminal.
- [ ] Đã kiểm tra `setMinSize(...)` không làm layout vượt quá vùng hiển thị.
- [ ] View được chạy và thoát qua `ViewComponent` hoặc `TerminalUI` đúng lifecycle.
- [ ] Đã kiểm thử terminal hẹp, resize và dữ liệu dài.

## Ghi nhớ

`BoxView` tạo khung có tiêu đề, border, padding và nền; dùng `setDrawFunction(...)` để vẽ nội dung bằng `Screen.Writer`. `GridView` kế thừa `BoxView` và sắp xếp các view con theo hàng/cột bằng `addItem(...)`. `setColumnSize(...)` và `setRowSize(...)` hỗ trợ kích thước tuyệt đối hoặc tỷ lệ; `rowSpan`/`colSpan` cho phép một view chiếm nhiều ô; hai ngưỡng cuối của `addItem(...)` hỗ trợ layout thích ứng. Trong command Spring Shell 3.x, có thể chạy view bằng `getViewComponentBuilder().build(view).runBlocking()`.

## Tài liệu tham khảo

- [Spring Shell 3.3.0 API — `BoxView`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/BoxView.html): border, title, padding, background và vùng nội dung.
- [Spring Shell 3.3.0 API — `GridView`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/GridView.html): thêm view, chia hàng/cột, span, kích thước tối thiểu và layout thích ứng.
- [Spring Shell 3.3.0 API — `AbstractView`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/AbstractView.html): draw lifecycle, `setDrawFunction`, focus, event loop và destroy.
- [Spring Shell 3.3.0 API — `Screen`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/screen/Screen.html): screen ảo và `writerBuilder()`.
- [Spring Shell 3.3.0 API — `Screen.Writer`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/screen/Screen.Writer.html): ghi text, border và background.
- [Spring Shell 3.3.0 API — `ViewComponentBuilder`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponentBuilder.html): tạo ViewComponent từ một view.
- [Spring Shell 3.3.0 API — `ViewComponent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponent.html): chạy blocking/async và yêu cầu thoát event loop.
- [Spring Shell 3.3.0 API — `AbstractShellComponent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/AbstractShellComponent.html): truy cập `getViewComponentBuilder()` trong shell component.
- [Spring Shell 3.3.0 API — `TerminalUI`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUI.html): quản lý root view, event loop và terminal UI toàn màn hình.
