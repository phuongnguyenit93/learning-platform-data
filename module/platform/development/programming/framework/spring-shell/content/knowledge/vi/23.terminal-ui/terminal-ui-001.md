# Phạm vi của TerminalUI và khác biệt với dòng lệnh tuần tự

Spring Shell thường được dùng như một REPL: người dùng nhập một command, shell phân tích tên lệnh và option, thực thi rồi hiển thị kết quả trước khi nhận dòng tiếp theo. Cách làm này phù hợp với thao tác quản trị, tra cứu và tự động hóa. Tuy nhiên, một số ứng dụng cần màn hình có nhiều vùng cùng lúc, danh sách có thể chọn, thanh trạng thái, hộp thoại, focus và xử lý phím liên tục. Với nhu cầu đó, Spring Shell 3.x cung cấp Terminal UI API.

`TerminalUI` là đối tượng điều phối một giao diện terminal theo mô hình view và event loop. Nó kết nối terminal, sự kiện bàn phím/chuột, cây view và việc vẽ lại màn hình. Một view có thể chứa nhiều view con; các view nhận focus và xử lý sự kiện riêng. Vì vậy, Terminal UI có cách vận hành gần với một ứng dụng giao diện hơn là một command chỉ in kết quả ra terminal.

Bài này xác định phạm vi của TerminalUI và cách chọn giữa ba mức tương tác:

- **Command REPL:** một dòng lệnh được phân tích và thực thi theo lượt.
- **ComponentFlow:** một wizard gồm các bước nhập hoặc chọn theo thứ tự.
- **TerminalUI:** một màn hình tương tác có nhiều view, layout và event loop.

Sau bài này, bạn có thể:

- Giải thích `TerminalUI`, `View`, `EventLoop` và `ViewService` làm nhiệm vụ gì.
- Phân biệt giao diện màn hình với command line tuần tự.
- Nhận biết các view có sẵn như `GridView`, `ListView`, `MenuView`, `InputView`, `ProgressView` và `DialogView`.
- Khởi tạo `TerminalUI`, gắn root view và chạy event loop.
- Hiểu khi nào nên dùng `ViewComponent` cho một view không chiếm toàn màn hình.
- Chọn đúng công cụ giữa REPL, `ComponentFlow` và TerminalUI.
- Nhận biết yêu cầu của terminal tương tác và cách dự phòng cho chế độ non-interactive.

> Nội dung sử dụng API Spring Shell 3.3.x trong package `org.springframework.shell.component.view` và `org.springframework.shell.component.view.control`. Đây là API Terminal UI của Spring Shell 3.x, không phải API HTML/web UI.

## 1. Command REPL và TerminalUI giải quyết hai kiểu tương tác

Trong REPL, người dùng nhập một dòng rồi nhấn Enter. Shell nhận đầu vào, phân tích command và argument, gọi phương thức tương ứng, xử lý kết quả và trở lại prompt. Mỗi command thường là một thao tác độc lập.

Ví dụ:

~~~text
shell:>orders list --status OPEN
shell:>orders show --id 1024
shell:>orders close --id 1024
~~~

TerminalUI dùng một màn hình tồn tại trong suốt một vòng tương tác. Thay vì nhập command cho mỗi hành động, người dùng có thể di chuyển focus giữa các vùng, chọn một dòng trong danh sách, mở dialog hoặc xem tiến độ ở một view khác.

Ví dụ bố cục của một màn hình quản lý đơn hàng:

~~~text
+----------------------------------------------------------------+
| ORDERS       Dashboard   Orders   Customers   Settings         |
+-------------------------------+--------------------------------+
| Danh sách đơn hàng             | Chi tiết đơn hàng              |
| > #1024  OPEN   Nguyễn An      | Mã: 1024                       |
|   #1023  PAID   Trần Bình      | Khách hàng: Nguyễn An          |
|   #1022  OPEN   Lê Chi         | Trạng thái: OPEN               |
|                                |                                |
|                                | [Mở] [Đóng] [Hủy]              |
+--------------------------------+--------------------------------+
| ↑↓ Di chuyển   Enter Mở   Esc Quay lại          Đang kết nối    |
+----------------------------------------------------------------+
~~~

Trong ví dụ, danh sách và vùng chi tiết cùng xuất hiện. Người dùng chuyển focus, chọn một đơn hàng và kích hoạt hành động mà không cần quay lại prompt sau mỗi thao tác.

| Khía cạnh | Command REPL | TerminalUI |
|---|---|---|
| Đơn vị tương tác | Một dòng command | Một màn hình gồm nhiều view |
| Luồng điều khiển | Nhập → phân tích → chạy → hiển thị → prompt | Event loop nhận sự kiện và cập nhật view |
| Điều hướng | Tên command, option, argument | Focus, phím tắt, sự kiện bàn phím/chuột |
| Bố cục | Văn bản kết quả tuần tự | Grid, menu, list, dialog, status bar |
| Trạng thái | Thường nằm trong tham số/kết quả command | View và model giữ trạng thái trong phiên UI |
| Tự động hóa | Phù hợp với script và pipe | Cần terminal tương tác để sử dụng đầy đủ |

TerminalUI không thay thế parser, command catalog, help hoặc cơ chế hoàn thành option của Spring Shell. Nó cung cấp một lớp giao diện khác để trình bày và điều khiển tương tác.

## 2. Ba mức tương tác trong Spring Shell

Không phải ứng dụng nào cũng cần xây dựng màn hình nhiều vùng. Spring Shell có các mức trừu tượng khác nhau:

| Nhu cầu | Công cụ | Cách hoạt động |
|---|---|---|
| Chạy một thao tác và trả kết quả | `@ShellMethod` hoặc `CommandRegistration` | Người dùng gọi command, shell thực thi và hiển thị kết quả |
| Thu thập một nhóm đầu vào theo từng bước | `ComponentFlow` | Chạy wizard gồm input, confirmation và selector |
| Duy trì màn hình có nhiều vùng và tương tác liên tục | `TerminalUI` | Event loop điều phối view, focus, key/mouse và redraw |

Ví dụ cùng một nghiệp vụ tạo dự án:

- Với REPL: `project create --name billing --region ap-southeast-1`.
- Với `ComponentFlow`: hỏi tên, chọn region, xác nhận rồi trả kết quả.
- Với TerminalUI: hiển thị danh sách dự án, vùng chi tiết và menu hành động trong cùng màn hình.

`ComponentFlow` phù hợp khi người dùng cần hoàn thành một quy trình nhập liệu ngắn. TerminalUI phù hợp khi người dùng cần quan sát và điều khiển nhiều phần trạng thái trong cùng một phiên. Nếu chỉ cần một danh sách hoặc bảng kết quả rồi quay lại prompt, command REPL thường đơn giản hơn.

## 3. TerminalUI là bộ điều phối màn hình

`TerminalUI` được tạo với một `org.jline.terminal.Terminal`. Nó cung cấp các khả năng chính:

- Giữ root view của ứng dụng.
- Tạo và quản lý `EventLoop`.
- Điều phối sự kiện bàn phím và chuột.
- Quản lý focus và modal view.
- Chuyển cấu hình `ThemeResolver`, tên theme và `ViewService` xuống view.
- Vẽ lại toàn bộ màn hình khi trạng thái thay đổi.
- Chạy vòng lặp tương tác cho tới khi có yêu cầu thoát.

Sơ đồ thành phần:

~~~mermaid
flowchart TD
    A[Terminal / JLine] <--> B[TerminalUI]
    B <--> C[EventLoop]
    B --> D[Root View]
    D --> E[View con: Grid / List / Input]
    D --> F[Menu / Status bar]
    D --> G[Modal / Dialog]
    C --> H[Key events]
    C --> I[Mouse events]
    H --> D
    I --> D
    D --> J[Screen redraw]
    J --> A
~~~

`TerminalUI` không phải là một view. Nó là đối tượng điều phối; `View` mới là thành phần hiển thị nội dung. Mỗi view có thể vẽ nội dung, chứa view con, nhận focus và đăng ký handler cho phím hoặc chuột.

## 4. View và cây giao diện

Interface `View` là hợp đồng cơ sở cho các thành phần hiển thị. Một view có thể tự vẽ và chứa không hoặc nhiều view con. Các view thường dùng:

| View | Vai trò |
|---|---|
| `BoxView` | Vùng nội dung có thể có đường viền và tiêu đề |
| `GridView` | Bố trí view con theo hàng/cột |
| `AppView` | Khung ứng dụng gồm vùng chính, menu bar, status bar và hệ thống modal |
| `MenuBarView` | Hiển thị các mục menu theo chiều ngang |
| `MenuView` | Hiển thị menu hoặc submenu |
| `ListView` | Danh sách dọc có lựa chọn |
| `InputView` | Vùng nhập văn bản |
| `ButtonView` | Nút có thể kích hoạt |
| `DialogView` | Hộp thoại có nội dung và nút thao tác |
| `ProgressView` | Thanh hoặc chỉ báo tiến độ |
| `StatusBarView` | Hiển thị các mục trạng thái theo chiều ngang |
| `WindowView` | Vùng cửa sổ chứa nội dung khác |

`AppView` là một lựa chọn thuận tiện để tổ chức màn hình ứng dụng. Constructor nhận ba view: vùng chính, menu bar và status bar. AppView quản lý thêm modal window system để hiển thị dialog hoặc vùng phủ khi cần.

Ví dụ khung giao diện:

~~~java
import org.springframework.shell.component.view.control.AppView;
import org.springframework.shell.component.view.control.GridView;
import org.springframework.shell.component.view.control.MenuBarView;
import org.springframework.shell.component.view.control.StatusBarView;
import org.springframework.shell.component.view.control.View;

GridView mainView = new GridView();
mainView.setTitle("Quản lý đơn hàng");

MenuBarView menuBar = MenuBarView.of();
StatusBarView statusBar = new StatusBarView();

View rootView = new AppView(mainView, menuBar, statusBar);
~~~

Ví dụ này tạo bộ khung với vùng nội dung chính, menu bar rỗng và status bar. Ứng dụng thực tế sẽ thêm view con vào `GridView`, tạo menu item và status item theo nghiệp vụ.

### GridView và bố cục thích ứng

`GridView` là container để đặt view theo tọa độ hàng/cột. Phương thức `addItem(...)` nhận view, vị trí, số hàng/cột chiếm dụng và kích thước màn hình tối thiểu để áp dụng bố cục đó.

~~~java
GridView grid = new GridView();
grid.setTitle("Dashboard");
grid.setColumnSize(2, -3);
~~~

`setColumnSize(...)` điều khiển cách phân phối chiều rộng:

- Giá trị lớn hơn 0 là chiều rộng tuyệt đối của cột.
- Giá trị nhỏ hơn hoặc bằng 0 biểu thị tỷ lệ phần không gian còn lại.
- Giá trị `-3` nhận phần rộng gấp ba lần cột `-1`.

Có thể thêm cùng một view ở nhiều vị trí với các ngưỡng kích thước tối thiểu khác nhau. Cách này cho phép bố cục dùng một cột khi terminal hẹp và nhiều cột khi màn hình đủ rộng.

## 5. EventLoop và sự kiện tương tác

`EventLoop` là trung tâm điều phối sự kiện trong vòng đời của component. Nó nhận các Spring `Message` và cung cấp các luồng sự kiện chuyên biệt như:

- `keyEvents()` cho sự kiện bàn phím.
- `mouseEvents()` cho sự kiện chuột.
- `viewEvents(...)` cho sự kiện do view phát ra.
- `signalEvents()` và `systemEvents()` cho các loại sự kiện tương ứng.

View có thể cung cấp `KeyHandler`, `MouseHandler` và hotkey handler. `TerminalUI` gắn event loop và `ViewService` vào view khi cấu hình cây giao diện.

Ví dụ luồng tương tác:

1. Người dùng nhấn phím mũi tên xuống.
2. Terminal/JLine chuyển thao tác thành key event.
3. Event loop chuyển event tới handler của view đang có focus.
4. Handler cập nhật mục được chọn.
5. View yêu cầu redraw để phản ánh trạng thái mới.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant T as Terminal/JLine
    participant E as EventLoop
    participant V as View đang focus
    participant S as Screen
    U->>T: Nhấn phím Down
    T->>E: KeyEvent
    E->>V: Chuyển sự kiện
    V->>V: Cập nhật selection
    V->>S: Yêu cầu vẽ lại
    S-->>U: Hiển thị dòng được chọn
~~~

Không nên xử lý mọi thao tác bằng cách đọc trực tiếp `System.in` bên cạnh TerminalUI. Terminal và event loop đã quản lý luồng nhập; một reader khác có thể tranh chấp input và khiến phím bấm bị mất hoặc xử lý sai.

## 6. Khởi tạo TerminalUI và chạy màn hình

Có thể tạo `TerminalUI` trực tiếp hoặc dùng `TerminalUIBuilder`. Builder cho phép cung cấp customizer, `ThemeResolver` và tên theme. Sau khi tạo UI, gắn root view và gọi `run()`:

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.View;
import org.springframework.shell.style.ThemeResolver;

public void showDashboard(
        Terminal terminal,
        ThemeResolver themeResolver,
        View rootView) {

    TerminalUI terminalUI = new TerminalUIBuilder(terminal)
            .themeResolver(themeResolver)
            .themeName("default")
            .build();

    terminalUI.setRoot(rootView, true);
    terminalUI.run();
}
~~~

`setRoot(rootView, true)` yêu cầu root view dùng chế độ toàn màn hình. `run()` bắt đầu event loop và chặn thread gọi cho tới khi vòng lặp kết thúc. Nếu không muốn chiếm toàn bộ terminal, có thể đặt `fullScreen` thành `false` hoặc tùy biến vùng hiển thị bằng các hàm `setNonfullScreenViewRect(...)` và `setFullScreenViewRect(...)`.

Khi UI chạy, ứng dụng không nên tiếp tục in các dòng log tùy tiện vào cùng terminal vì output đó có thể phá bố cục màn hình. Dùng view, status bar hoặc cơ chế thông báo của UI để cập nhật thông tin đang hiển thị.

## 7. Chạy một view không chiếm toàn màn hình bằng ViewComponent

Không phải mọi view đều cần một ứng dụng toàn màn hình. Spring Shell 3.x có `ViewComponent` để chạy view trong chế độ non-fullscreen. Nó có thể chạy đồng bộ bằng `runBlocking()` hoặc bất đồng bộ bằng `runAsync()`.

`ViewComponentBuilder` nhận `TerminalUIBuilder`, `ViewComponentExecutor` và `Terminal`, sau đó tạo `ViewComponent` cho một view:

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.component.ViewComponent;
import org.springframework.shell.component.ViewComponentBuilder;
import org.springframework.shell.component.ViewComponentExecutor;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.View;

public void showInlineView(Terminal terminal, View view) throws Exception {
    try (ViewComponentExecutor executor = new ViewComponentExecutor()) {
        ViewComponent component = new ViewComponentBuilder(
                new TerminalUIBuilder(terminal),
                executor,
                terminal)
                .build(view);

        component.setUseTerminalWidth(true);
        component.runBlocking();
    }
}
~~~

`ViewComponent` phù hợp khi command cần hiển thị một view trong vùng terminal thông thường rồi trả quyền điều khiển về shell. Executor có thể được quản lý bằng try-with-resources vì nó triển khai `AutoCloseable`.

Với `runAsync()`, kết quả trả về là `ViewComponentRun`, cho phép theo dõi trạng thái hoặc yêu cầu hủy lượt chạy. Dùng chế độ bất đồng bộ khi command cần tiếp tục phối hợp với công việc khác trong khi view đang hoạt động; cần xác định rõ ai sở hữu executor và khi nào đóng nó.

## 8. Khi nào chọn TerminalUI thay vì ComponentFlow?

Hai API đều hỗ trợ tương tác, nhưng phục vụ độ phức tạp khác nhau:

| Tiêu chí | ComponentFlow | TerminalUI |
|---|---|---|
| Mục tiêu | Wizard nhập liệu theo bước | Ứng dụng màn hình tương tác |
| Bố cục | Thường một component tại một thời điểm | Nhiều view cùng xuất hiện |
| Điều hướng | Thứ tự bước và nhánh tiếp theo | Focus, phím, chuột, menu, modal |
| Trạng thái | Context của từng component và flow result | Trạng thái của view và model ứng dụng |
| Tùy biến | Template/renderer của component | Cây view, layout, event handler và theme |
| Độ phức tạp | Thấp đến trung bình | Trung bình đến cao |

Chọn `ComponentFlow` khi cần hỏi tên, chọn một môi trường và xác nhận. Chọn TerminalUI khi người dùng cần xem danh sách và chi tiết cùng lúc, thao tác qua nhiều vùng, cập nhật tiến độ hoặc mở dialog trong một màn hình tồn tại lâu.

Không cần xây dựng TerminalUI chỉ để hỏi một câu xác nhận hoặc chọn một giá trị. Những trường hợp đó đã có component tương tác mức cao hơn.

## 9. TerminalUI và vòng lặp command của Spring Shell

Spring Shell REPL và TerminalUI có thể dùng chung terminal, nhưng có hai vòng lặp điều khiển khác nhau:

| Vòng lặp | Trách nhiệm |
|---|---|
| Shell REPL | Đọc dòng command, parse, tìm command, bind argument, thực thi và hiển thị kết quả |
| TerminalUI EventLoop | Nhận sự kiện key/mouse, cập nhật view, quản lý focus/modal và redraw |

Một ứng dụng có thể khởi chạy một màn hình UI từ command. Khi màn hình đóng, phương thức command tiếp tục hoặc kết thúc và shell có thể hiển thị prompt trở lại. Khi thiết kế tích hợp, cần xác định rõ ai điều khiển terminal tại từng thời điểm và tránh để hai vòng lặp cùng đọc input đồng thời.

Ví dụ luồng gọi:

~~~text
shell:>dashboard
        |
        v
TerminalUI.run()
        |
        v
Người dùng thao tác trong màn hình
        |
        v
Event loop kết thúc
        |
        v
Command trả kết quả
        |
        v
shell:>
~~~

TerminalUI không tự biến các phím bấm thành command Spring Shell. Nếu người dùng chọn mục Orders trong menu, handler của view phải cập nhật màn hình hoặc gọi service tương ứng. Nếu muốn thực thi một command shell, ứng dụng cần chủ động tích hợp với command layer theo thiết kế riêng.

## 10. Yêu cầu terminal và chế độ non-interactive

TerminalUI cần một terminal có khả năng tương tác để nhận phím, vẽ lại vùng hiển thị và quản lý cursor. Các môi trường như CI, scheduler, pipe hoặc redirect output thường không cung cấp trải nghiệm TTY đầy đủ.

Trước khi khởi chạy UI, ứng dụng nên xác định command đang chạy trong môi trường tương tác hay tự động. Khi không có terminal tương tác:

- Trả kết quả dạng văn bản thuần.
- Cung cấp option để chọn mục hoặc truyền giá trị trực tiếp.
- Dùng bảng, JSON hoặc CSV cho kết quả có cấu trúc.
- Không chờ phím bấm hoặc mở dialog.
- Giữ exit code có ý nghĩa cho tiến trình gọi.

Ví dụ, thay vì yêu cầu người dùng mở menu để chọn trạng thái:

~~~text
orders browse
~~~

command tự động nên nhận trạng thái qua option:

~~~text
orders list --status OPEN --page 0 --size 50
~~~

Không nên giả định terminal hỗ trợ chuột. Các thao tác quan trọng cần có phím điều hướng hoặc phím tắt tương ứng để vẫn dùng được trên terminal chỉ hỗ trợ bàn phím.

## 11. Vòng đời và dọn dẹp tài nguyên

Một TerminalUI có thể giữ event loop, view, subscription và tài nguyên terminal trong suốt phiên chạy. Khi màn hình kết thúc, cần bảo đảm:

- Event loop và subscription gắn với view được giải phóng.
- Tác vụ nền hoặc timer không tiếp tục phát event cho view đã bị hủy.
- Executor do ứng dụng tạo được đóng đúng lúc.
- Modal và focus được đưa về trạng thái hợp lệ trước khi thoát.
- Không để terminal ở chế độ raw hoặc trạng thái cursor ẩn sau khi command kết thúc.
- Command không tiếp tục ghi dữ liệu vào terminal trong khi UI đang chiếm quyền hiển thị.

`AbstractView` cung cấp `onDestroy(...)` để đăng ký `Disposable` cần được dispose khi view kết thúc. Dùng cơ chế này cho subscription hoặc tác vụ reactive có vòng đời gắn với view. Với executor, dùng lifecycle bean hoặc try-with-resources nếu phạm vi sở hữu ngắn.

Không giữ một subscription toàn cục vô thời hạn nếu nó chỉ phục vụ một màn hình. Khi người dùng đóng màn hình, mọi công việc chỉ dành cho màn hình đó cũng cần dừng hoặc được chuyển giao rõ ràng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Màn hình không xuất hiện | Chưa gọi `setRoot(...)` hoặc `run()` | Gắn root view trước khi chạy event loop |
| UI chiếm toàn terminal ngoài ý muốn | `setRoot(view, true)` bật fullscreen | Dùng `false` hoặc `ViewComponent` cho view non-fullscreen |
| Phím bấm không điều khiển view | View chưa có handler hoặc chưa được focus | Kiểm tra key handler, focus và event loop |
| Màn hình bị vỡ khi command khác in output | Nhiều thành phần cùng ghi vào terminal | Chỉ để UI quản lý output khi event loop đang chạy |
| Dialog không đóng hoặc không nhận focus | Chưa dùng `ViewService`/modal hoặc handler chưa phát sự kiện đúng | Kiểm tra `setModal`, focus và view event |
| UI chạy nhưng không cập nhật | View thay đổi model nhưng chưa redraw hoặc event không tới handler | Kiểm tra dispatch, event loop và redraw |
| Ứng dụng không kết thúc sau khi đóng view | Subscription, executor hoặc tác vụ nền còn hoạt động | Dispose tài nguyên theo vòng đời view và đóng executor |
| UI không hoạt động trong CI | Không có TTY hoặc input tương tác | Dùng command option và output thuần |
| Chuột không dùng được | Terminal hoặc môi trường không hỗ trợ mouse reporting | Cung cấp key binding thay thế |
| Khó kiểm thử vì UI chiếm màn hình | Logic nghiệp vụ gắn chặt với view | Tách service/model khỏi view và kiểm thử event handler riêng |

## 13. Checklist chọn đúng phạm vi

- Dùng command REPL cho thao tác một lần có input và output rõ ràng.
- Dùng `ComponentFlow` cho wizard nhập liệu theo bước.
- Dùng `TerminalUI` khi cần nhiều vùng hiển thị, focus, key/mouse và event loop.
- Dùng `AppView` khi cần khung main/menu/status/modal.
- Dùng `GridView` để bố trí view con theo kích thước terminal.
- Gắn root view và cấu hình theme trước khi gọi `run()`.
- Xác định fullscreen hay non-fullscreen.
- Dùng `ViewComponent` cho một view không chiếm toàn màn hình.
- Không để REPL và TerminalUI đồng thời đọc cùng terminal.
- Có phương án text/script khi không có TTY.
- Giải phóng subscription, executor và tài nguyên theo vòng đời view.
- Tách logic nghiệp vụ khỏi view để dễ kiểm thử.

## 14. Bài tập thực hành

Tạo một màn hình `orders dashboard` đơn giản:

1. Tạo `GridView` làm vùng nội dung chính.
2. Dùng `AppView` ghép vùng chính, `MenuBarView` và `StatusBarView`.
3. Tạo `TerminalUI` qua `TerminalUIBuilder`, đặt theme và gắn root view.
4. Chạy `TerminalUI.run()` trong một command `dashboard`.
5. Thêm `ListView` hiển thị đơn hàng và một view chi tiết.
6. Bố trí hai view trong `GridView`; dùng `setColumnSize(...)` để vùng chi tiết rộng hơn danh sách.
7. Đăng ký handler cho phím điều hướng và chọn một dòng.
8. Khi dòng được chọn thay đổi, cập nhật vùng chi tiết và yêu cầu redraw.
9. Thêm một `DialogView` để xác nhận thao tác đóng đơn hàng.
10. Đóng event loop và xác nhận command trả về prompt.
11. Tạo một command khác hiển thị view không fullscreen bằng `ViewComponent.runBlocking()`.
12. Chạy ứng dụng trong môi trường không có TTY và cung cấp command `orders list --status OPEN` làm đường đi thay thế.

Khi hoàn thành, hãy giải thích vì sao màn hình dashboard cần TerminalUI, còn thao tác liệt kê đơn hàng có thể dùng command REPL.

## Tài liệu tham khảo

- [Spring Shell 3.3 – TerminalUI API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUI.html): vai trò điều phối terminal, event loop, root view, modal và redraw.
- [Spring Shell 3.3 – TerminalUIBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUIBuilder.html): xây dựng và cấu hình TerminalUI.
- [Spring Shell 3.3 – View API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/View.html): hợp đồng view, focus, key/mouse handler và event loop.
- [Spring Shell 3.3 – EventLoop API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/event/EventLoop.html): điều phối sự kiện trong vòng đời component.
- [Spring Shell 3.3 – View controls](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/package-summary.html): các view tích hợp như AppView, GridView, ListView, MenuView, DialogView và ProgressView.
- [Spring Shell 3.3 – AppView API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/AppView.html): vùng chính, menu bar, status bar và modal window system.
- [Spring Shell 3.3 – GridView API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/GridView.html): bố cục theo hàng/cột và kích thước thích ứng.
- [Spring Shell 3.3 – ViewComponent API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponent.html): thực thi view trong chế độ non-fullscreen, blocking hoặc asynchronous.
- [Spring Shell 3.3 – ViewComponentBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponentBuilder.html): tạo ViewComponent từ terminal, builder và executor.
