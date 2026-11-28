# AppView và tổ chức cây view

Một ứng dụng terminal có nhiều màn hình thường cần bố cục ổn định: thanh menu ở trên, vùng nội dung ở giữa và thanh trạng thái ở dưới. Khi số lượng thành phần tăng lên, việc vẽ mọi thứ trong một đoạn output duy nhất trở nên khó bảo trì. Spring Shell 3.x cung cấp Terminal UI framework với mô hình `View` lồng nhau; `AppView` ghép vùng nội dung chính, menu bar và status bar thành một giao diện ứng dụng.

Bài viết giải thích cách tổ chức cây view, vai trò của `AppView`, cách dùng `GridView` để bố trí các view con, cách điều phối vòng đời bằng `TerminalUI` và cách trao đổi sự kiện giữa các view. Ví dụ xuyên suốt là một CLI quản lý workspace có danh sách dự án, vùng chi tiết, menu thao tác và trạng thái hiện tại.

## 1. Terminal UI được tổ chức theo cây

Trong Spring Shell 3.x, `View` là một phần giao diện có thể hiển thị và chứa không hoặc nhiều view con. Mỗi view chịu trách nhiệm render nội dung trong vùng hình chữ nhật mà nó được cấp, đồng thời có thể xử lý focus, bàn phím, chuột và command riêng.

Một cây view điển hình:

```text
TerminalUI
└── AppView
    ├── MenuBarView             Thanh menu
    ├── GridView                 Vùng nội dung chính
    │   ├── ListView             Danh sách dự án
    │   └── BoxView              Chi tiết dự án đang chọn
    └── StatusBarView            Trạng thái và phím tắt
```

Terminal UI framework phân biệt ba khái niệm:

- **Control:** đối tượng biết vùng tọa độ của mình và có thể vẽ lên `Screen`.
- **View:** control có thể hiển thị và chứa các view con, đồng thời tham gia vào hệ thống focus và event.
- **TerminalUI:** thành phần điều phối terminal, event loop, sự kiện bàn phím/chuột và cây view trong suốt vòng đời giao diện.

`AppView` là một `View` cấp cao, kế thừa `BoxView`. Nó tạo bố cục ứng dụng có sẵn và nhận ba view: `main`, `menuBar`, `statusBar`. Vì vậy, có thể dùng `GridView`, `ListView`, `DialogView` hoặc một view tự xây dựng làm nội dung chính.

## 2. Các view nền tảng thường dùng

Spring Shell 3.x có sẵn nhiều view để ghép thành ứng dụng terminal:

| View | Vai trò |
|---|---|
| `BoxView` | Vùng nội dung có nền, tiêu đề và border tùy chọn |
| `GridView` | Container bố trí các view con theo hàng, cột và breakpoint kích thước |
| `ListView<T>` | Danh sách dọc có lựa chọn hiện tại và sự kiện thay đổi/chọn item |
| `MenuBarView` | Thanh menu ngang, bên trong dùng `MenuView` để hiển thị menu |
| `MenuView` | Menu dọc, hỗ trợ item thường và submenu |
| `StatusBarView` | Thanh trạng thái ngang với các item và hành động tùy chọn |
| `InputView` | Trường nhập văn bản trong terminal |
| `ButtonView` | Nút có border và nội dung, phát sự kiện khi chọn |
| `DialogView` | Cửa sổ hội thoại có nội dung và các nút |
| `WindowView` | View xác định một vùng cửa sổ bên trong giao diện |
| `ProgressView` | Hiển thị tiến trình và trạng thái tác vụ |

Các view này đều triển khai `View`, vì vậy có thể được lồng vào `GridView`, đặt làm nội dung chính của `AppView`, hoặc dùng làm modal qua `TerminalUI.setModal(...)`.

## 3. AppView tạo khung ứng dụng

Constructor của `AppView` nhận ba đối số theo thứ tự:

```java
new AppView(mainView, menuBarView, statusBarView)
```

Về mặt bố cục, menu bar nằm phía trên, main view chiếm vùng trung tâm và status bar nằm phía dưới:

```text
┌──────────────────────────────────────────────┐
│ File   Workspace   Help                      │  MenuBarView
├──────────────────────────────────────────────┤
│                                              │
│  Danh sách       Chi tiết                    │
│  dự án           dự án đang chọn             │  Main View
│                                              │
├──────────────────────────────────────────────┤
│ Ready   Project: catalog-api   F1 Help       │  StatusBarView
└──────────────────────────────────────────────┘
```

`AppView` còn hỗ trợ ẩn/hiện menu bar và status bar bằng `setMenuBarVisible`, `setStatusBarVisible`, `toggleMenuBarVisibility` và `toggleStatusBarVisibility`. Nó cũng có thể nhận theme name và `ThemeResolver` để các view con dùng chung quy tắc hiển thị.

Điểm quan trọng là `AppView` chỉ tổ chức khung tổng thể. Cấu trúc chi tiết bên trong main view do ứng dụng thiết kế, thường bằng một hoặc nhiều `GridView` lồng nhau.

## 4. GridView bố trí các view con

`GridView` là container không có view con ban đầu. Có thể thêm view bằng `addItem(...)`:

```java
grid.addItem(view, row, column, rowSpan, colSpan,
        minGridHeight, minGridWidth);
```

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `view` | View được đặt vào grid |
| `row`, `column` | Ô bắt đầu, tính từ 0 |
| `rowSpan`, `colSpan` | Số hàng và cột mà view chiếm |
| `minGridHeight` | Chiều cao tối thiểu của grid để vị trí này được chọn |
| `minGridWidth` | Chiều rộng tối thiểu của grid để vị trí này được chọn |

Nếu `rowSpan` hoặc `colSpan` bằng `0`, view sẽ không được vẽ ở vị trí đó. Có thể thêm cùng một view nhiều lần ở các vị trí khác nhau để thay đổi bố cục theo kích thước terminal.

### Phân chia chiều rộng và chiều cao

`setColumnSize(int...)` và `setRowSize(int...)` quy định cách chia kích thước:

- Giá trị lớn hơn `0` biểu thị kích thước tuyệt đối theo số cột hoặc số hàng terminal.
- Giá trị bằng `0` hoặc nhỏ hơn biểu thị phần tỷ lệ của không gian còn lại.
- `0` được xem như `-1`; `-3` nhận phần không gian gấp ba lần một cột `-1`.
- Nếu không gọi `setColumnSize`, các cột đang được sử dụng có chiều rộng bằng nhau.

Ví dụ, chia cột trái cố định 24 ký tự và phần còn lại cho chi tiết:

```java
GridView main = new GridView();
main.setColumnSize(24, -1);
main.addItem(projectList, 0, 0, 1, 1, 0, 0);
main.addItem(projectDetails, 0, 1, 1, 1, 0, 0);
```

Ở đây, `projectList` chiếm cột trái 24 đơn vị, `projectDetails` chiếm phần còn lại. Nếu terminal hẹp hơn tổng kích thước tối thiểu của các view, grid có thể vượt quá vùng hiển thị; cần thiết kế breakpoint hoặc bố cục thay thế cho màn hình nhỏ.

## 5. Tạo MenuBarView và StatusBarView

`MenuBarView` hiển thị các mục menu theo chiều ngang. Mỗi `MenuBarItem` chứa một hoặc nhiều `MenuView.MenuItem`. Một menu item có thể gắn `Runnable` để thực hiện hành động khi người dùng chọn.

Ví dụ:

```java
import org.springframework.shell.component.view.control.MenuBarView;
import org.springframework.shell.component.view.control.MenuView;

MenuBarView menuBar = MenuBarView.of(
        MenuBarView.MenuBarItem.of(
                "File",
                MenuView.MenuItem.of(
                        "Refresh",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        refreshAction),
                MenuView.MenuItem.of(
                        "Quit",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        quitAction)),
        MenuBarView.MenuBarItem.of(
                "Help",
                MenuView.MenuItem.of(
                        "About",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        aboutAction)));
```

`MenuBarItem.setHotKey(...)` có thể gán phím tắt để mở menu. Mặc định, mũi tên trái/phải di chuyển giữa các menu và nhấn chuột trái để chọn mục. `MenuBarView` không phát `ViewEvent` riêng; hành động được thực hiện qua `Runnable` của `MenuItem`.

`StatusBarView` hiển thị các mục trạng thái theo chiều ngang:

```java
import java.util.List;
import org.springframework.shell.component.view.control.StatusBarView;

StatusBarView statusBar = new StatusBarView(List.of(
        StatusBarView.StatusItem.of("Ready"),
        StatusBarView.StatusItem.of("Workspace: default")));
```

`StatusItem` có thể có action và hotkey. Khi trạng thái thay đổi, gọi `statusBar.setItems(...)` rồi yêu cầu `TerminalUI.redraw()` để cập nhật màn hình.

## 6. Khởi tạo TerminalUI và chạy AppView

`TerminalUIBuilder` là cách được khuyến nghị để tạo `TerminalUI`. Builder được Spring Shell auto-configure và gắn các dịch vụ cần thiết như terminal, theme resolver và customizer.

Ví dụ đầy đủ về cây view quản lý workspace:

```java
import java.util.List;

import reactor.core.Disposable;
import org.springframework.shell.component.message.ShellMessageBuilder;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.AppView;
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.control.GridView;
import org.springframework.shell.component.view.control.ListView;
import org.springframework.shell.component.view.control.MenuBarView;
import org.springframework.shell.component.view.control.MenuView;
import org.springframework.shell.component.view.control.StatusBarView;
import org.springframework.shell.component.view.control.MenuView.MenuItem;
import org.springframework.stereotype.Component;

@Component
public class WorkspaceTerminalApp {

    private final TerminalUIBuilder terminalUIBuilder;

    public WorkspaceTerminalApp(TerminalUIBuilder terminalUIBuilder) {
        this.terminalUIBuilder = terminalUIBuilder;
    }

    public void run() {
        TerminalUI ui = terminalUIBuilder.build();

        ListView<String> projects = new ListView<>();
        projects.setTitle("Projects");
        projects.setItems(List.of("catalog-api", "billing-api", "identity"));

        BoxView details = new BoxView();
        details.setTitle("Select a project");

        GridView main = new GridView();
        main.setColumnSize(24, -1);
        main.addItem(projects, 0, 0, 1, 1, 0, 0);
        main.addItem(details, 0, 1, 1, 1, 0, 0);

        StatusBarView status = new StatusBarView(List.of(
                StatusBarView.StatusItem.of("Ready")));

        Runnable refreshAction = () -> {
            projects.setItems(List.of("catalog-api", "billing-api", "identity"));
            status.setItems(List.of(StatusBarView.StatusItem.of("Projects refreshed")));
            ui.redraw();
        };

        Runnable aboutAction = () -> {
            status.setItems(List.of(StatusBarView.StatusItem.of("Workspace CLI 1.0")));
            ui.redraw();
        };

        Runnable quitAction = () ->
                ui.getEventLoop().dispatch(ShellMessageBuilder.ofInterrupt());

        MenuBarView menu = MenuBarView.of(
                MenuBarView.MenuBarItem.of("File",
                        MenuItem.of("Refresh", MenuView.MenuItemCheckStyle.NOCHECK, refreshAction),
                        MenuItem.of("Quit", MenuView.MenuItemCheckStyle.NOCHECK, quitAction)),
                MenuBarView.MenuBarItem.of("Help",
                        MenuItem.of("About", MenuView.MenuItemCheckStyle.NOCHECK, aboutAction)));

        AppView appView = new AppView(main, menu, status);
        ui.configure(appView);
        ui.setRoot(appView, true);

        Disposable selectionSubscription = ui.getEventLoop()
                .viewEvents(ListView.ListViewSelectedItemChangedEvent.class, projects)
                .subscribe(event -> {
                    details.setTitle("Project: " + event.args().item());
                    status.setItems(List.of(
                            StatusBarView.StatusItem.of("Selected: " + event.args().item())));
                    ui.redraw();
                });
        ui.getEventLoop().onDestroy(selectionSubscription);

        ui.run();
    }
}
```

Ví dụ minh họa các điểm chính:

1. `TerminalUIBuilder.build()` tạo bộ điều phối giao diện.
2. `GridView` tổ chức danh sách dự án và vùng chi tiết.
3. `MenuBarView` cung cấp thao tác Refresh, Quit và About.
4. `StatusBarView` hiển thị trạng thái hiện tại.
5. `AppView` kết hợp ba vùng thành khung ứng dụng.
6. `ui.configure(appView)` gắn event loop, theme resolver và `ViewService` cho cây view.
7. `ui.setRoot(appView, true)` đặt root view ở chế độ toàn màn hình.
8. `ui.run()` bắt đầu event loop và chặn luồng gọi cho đến khi vòng lặp kết thúc.

`ShellMessageBuilder.ofInterrupt()` tạo thông điệp interrupt để yêu cầu event loop dừng. Trong ứng dụng thực tế, hành động Quit có thể xác nhận trước khi dispatch thông điệp này.

## 7. Hiểu thứ tự xử lý focus và phím trong AppView

`AppView` có quy tắc điều phối bàn phím riêng:

- Nếu menu đang có focus, key handling được xử lý ở menu trước.
- Sau đó, main view được hỏi để xử lý phím.
- Cuối cùng, các phím trái/phải có thể được chuyển thành `AppViewEvent` với hướng `NEXT` hoặc `PREVIOUS`.

Hotkey được kiểm tra theo thứ tự main view, menu bar rồi status bar. Điều này giúp phím tắt của nội dung chính có thể được ưu tiên trước phím tắt ở menu hoặc status.

Trong ví dụ workspace, khi người dùng điều hướng trong `ListView`, view nhận focus và xử lý phím lên/xuống. Khi focus ở menu bar, mũi tên trái/phải di chuyển giữa các menu. Không nên đăng ký cùng một phím ở nhiều view mà không xác định thứ tự ưu tiên và hành vi khi một view không xử lý được phím.

`View` có các phương thức liên quan đến focus và input:

- `hasFocus()` kiểm tra view có focus hay không.
- `focus(view, boolean)` thông báo một view nhận hoặc mất focus.
- `getKeyHandler()` và `getHotKeyHandler()` cung cấp bộ xử lý phím thường và phím tắt.
- `getMouseHandler()` cung cấp bộ xử lý sự kiện chuột.
- `setEventLoop(...)` và `setViewService(...)` gắn view với hạ tầng điều phối.

## 8. EventLoop kết nối các view trong cây

`EventLoop` là nơi điều phối sự kiện trong vòng đời Terminal UI. Nó nhận message, phát các luồng sự kiện có kiểu và phối hợp cập nhật trạng thái với việc redraw.

Các luồng sự kiện thường dùng:

| API | Dữ liệu |
|---|---|
| `events()` | Mọi message của event loop |
| `keyEvents()` | Sự kiện bàn phím |
| `mouseEvents()` | Sự kiện chuột |
| `viewEvents(Class)` | Sự kiện view theo kiểu cụ thể |
| `viewEvents(Class, View)` | Sự kiện của kiểu view, lọc theo một view cụ thể |
| `systemEvents()` | Sự kiện hệ thống như redraw |
| `signalEvents()` | Sự kiện signal |

Ví dụ lắng nghe item được chọn trong một `ListView`:

```java
ui.getEventLoop()
        .viewEvents(ListView.ListViewSelectedItemChangedEvent.class, projects)
        .subscribe(event -> {
            Object selected = event.args().item();
            details.setTitle("Selected: " + selected);
            ui.redraw();
        });
```

`ListViewSelectedItemChangedEvent` chứa view phát sự kiện và `ListViewItemEventArgs`; `args().item()` trả về item mới được chọn. Sự kiện `ListViewOpenSelectedItemEvent` biểu thị người dùng yêu cầu mở item đang chọn, phù hợp để điều hướng sang màn hình chi tiết.

Nếu subscription có vòng đời ngắn hơn toàn bộ ứng dụng, giữ `Disposable` trả về từ `subscribe()` và hủy khi view không còn dùng. `EventLoop.onDestroy(disposable)` đăng ký disposable để tự hủy khi event loop kết thúc.

Không chạy truy vấn mạng hoặc tác vụ dài trực tiếp trên luồng xử lý input. Hãy chuyển công việc sang service hoặc scheduler phù hợp, sau đó cập nhật state của view và yêu cầu redraw khi có kết quả.

## 9. Tổ chức nhiều tầng bằng GridView lồng nhau

Khi màn hình lớn hơn, có thể tạo nhiều grid con để giữ bố cục rõ ràng. Ví dụ:

```text
AppView
└── GridView (main)
    ├── GridView (navigation)
    │   ├── MenuView (workspace)
    │   └── ListView (resources)
    └── GridView (content)
        ├── BoxView (details)
        └── ProgressView (task progress)
```

Mỗi grid con quản lý một vùng bố cục độc lập. Cách này giúp thay đổi kích thước hoặc nội dung của vùng chi tiết mà không phải viết lại toàn bộ main view.

Không nên lồng grid quá sâu nếu một grid đơn giản đã đủ. Mỗi cấp container làm tăng độ phức tạp khi tính kích thước, focus và thứ tự điều hướng.

## 10. Bố cục thích ứng với kích thước terminal

`GridView.addItem(...)` hỗ trợ `minGridWidth` và `minGridHeight`. Có thể thêm cùng một view ở nhiều vị trí với điều kiện kích thước khác nhau. Khi terminal đủ rộng, danh sách và chi tiết có thể nằm cạnh nhau; khi terminal hẹp, ứng dụng có thể chuyển sang bố cục một cột.

Ví dụ về chiến lược:

```java
GridView main = new GridView();

// Bố cục một cột khi terminal hẹp.
main.addItem(projects, 0, 0, 1, 2, 0, 0);
main.addItem(details, 1, 0, 1, 2, 0, 0);

// Bố cục hai cột khi terminal đủ rộng.
main.addItem(projects, 0, 0, 2, 1, 0, 100);
main.addItem(details, 0, 1, 2, 1, 0, 100);
```

Các vị trí có cùng view có thể được chọn theo kích thước tổng thể của grid. Hãy kiểm tra các ngưỡng bằng terminal thực tế, nhất là khi có border, padding và thanh menu/status.

Nếu bố cục cần nhiều breakpoint, hãy viết một sơ đồ vị trí rõ ràng trước khi thêm view vào grid. Cần tránh hai cấu hình cùng phù hợp nhưng có thứ tự ưu tiên không chủ đích; tài liệu API quy định vị trí được chọn theo các ngưỡng tối thiểu và thứ tự thêm khi điều kiện bằng nhau.

## 11. Modal và hộp thoại

`TerminalUI` hỗ trợ một modal view đang hoạt động tại một thời điểm. Modal được đặt trên các view còn lại và nhận input trong khi đang mở.

Mở modal:

```java
DialogView dialog = new DialogView(dialogContent, confirmButton, cancelButton);
ui.setModal(dialog);
```

Đóng modal:

```java
ui.setModal(null);
```

`DialogView` kế thừa `WindowView` và nhận một view nội dung cùng danh sách `ButtonView`. Có thể dùng modal cho xác nhận xóa dữ liệu, thông báo lỗi hoặc lựa chọn ngắn. Khi modal đóng, ứng dụng quay lại cây view gốc và tiếp tục xử lý input ở view đang có focus.

Không tạo nhiều modal chồng lên nhau. Nếu cần nhiều bước xác nhận, hãy quản lý một trạng thái dialog và thay nội dung hoặc chuyển sang dialog tiếp theo sau khi dialog hiện tại đóng.

## 12. Cập nhật dữ liệu và redraw

View hiển thị trạng thái hiện tại của ứng dụng. Khi dữ liệu thay đổi, cập nhật view tương ứng rồi yêu cầu `TerminalUI.redraw()` để vẽ lại màn hình.

Ví dụ:

```java
projects.setItems(updatedProjects);
status.setItems(List.of(StatusBarView.StatusItem.of("Loaded 12 projects")));
ui.redraw();
```

Một số nguyên tắc:

- Chỉ cập nhật view liên quan tới thay đổi dữ liệu.
- Không dựng lại toàn bộ cây view sau mỗi phím nếu chỉ cần thay một tiêu đề hoặc danh sách.
- Dùng `setItems(...)` khi danh sách thay đổi.
- Gọi `redraw()` sau khi state đã được cập nhật.
- Không gọi redraw liên tục trong vòng lặp nhanh; gom các thay đổi thành một lần cập nhật.
- Giữ logic nghiệp vụ trong service/model, để view chỉ hiển thị và chuyển tiếp thao tác của người dùng.

## 13. Kiểm thử cây view và điều hướng

Kiểm thử Terminal UI nên bao gồm cả cấu trúc, sự kiện và hành vi trên terminal.

| Trường hợp | Điều cần xác nhận |
|---|---|
| AppView composition | Main, menu bar và status bar được gắn đúng vị trí |
| Grid layout | Cột và hàng có kích thước đúng theo cấu hình |
| Responsive breakpoint | Bố cục đổi đúng khi terminal hẹp/rộng |
| Focus | View đang hoạt động nhận bàn phím |
| Menu action | Runnable của menu thực hiện đúng hành động |
| List selection | Event mang đúng item vừa chọn |
| View event filter | Chỉ nhận event từ view được chỉ định |
| Status update | Nội dung status bar thay đổi sau thao tác |
| Modal | Modal nhận input và đóng về root view |
| Redraw | Thay đổi state được phản ánh trên màn hình |
| Exit | Interrupt message kết thúc vòng lặp UI |
| Terminal nhỏ | Nội dung không bị cắt hoặc tràn ngoài dự kiến |

Spring Shell có `ShellTestClient` để mô phỏng phiên shell, gửi input và đọc `ShellScreen`. Với ứng dụng Terminal UI tùy chỉnh, nên kiểm thử riêng logic event handler và cấu trúc view; sau đó chạy integration test trên terminal giả lập hoặc terminal mục tiêu để kiểm tra focus, phím và kích thước thực tế.

## 14. Các lỗi tổ chức cây view thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| View không nhận bàn phím | Chưa được cấu hình vào TerminalUI hoặc không có focus | Gọi `ui.configure(root)` và kiểm tra focus |
| Không thấy menu hoặc status | Đưa sai đối số vào constructor AppView | Truyền theo thứ tự `main`, `menuBar`, `statusBar` |
| Grid bị tràn ngang | Tổng chiều rộng cột hoặc min size vượt terminal | Thiết kế breakpoint và kiểm tra terminal nhỏ |
| View không được vẽ | `rowSpan` hoặc `colSpan` bằng 0, hoặc breakpoint không thỏa | Kiểm tra vị trí và minGridWidth/minGridHeight |
| Chọn item nhưng chi tiết không đổi | Chưa subscribe event hoặc quên redraw | Theo dõi `ListViewSelectedItemChangedEvent`, cập nhật state và gọi redraw |
| Menu action không chạy | Menu item chưa gắn Runnable | Tạo `MenuItem` có action và kiểm tra key/mouse bindings |
| UI không kết thúc | `TerminalUI.run()` đang chặn và không có interrupt | Dispatch `ShellMessageBuilder.ofInterrupt()` từ hành động thoát |
| Modal không biến mất | Chưa gọi `setModal(null)` | Xóa modal khi xác nhận hoặc hủy |
| Sự kiện xử lý lặp | Subscription được tạo lại mỗi lần render | Đăng ký subscription một lần trong vòng đời view/app và dispose đúng lúc |
| Main view quá phức tạp | Tất cả nội dung nằm trong một view lớn | Tách vùng thành GridView và các view chuyên biệt |

## 15. Checklist thiết kế AppView

- [ ] Đã xác định rõ root view và cây view con.
- [ ] Dùng `AppView(main, menuBar, statusBar)` đúng thứ tự.
- [ ] Dùng `GridView` để phân chia vùng nội dung chính.
- [ ] Đã chọn chiều rộng cột/hàng phù hợp với terminal.
- [ ] Đã cấu hình `TerminalUI` bằng `TerminalUIBuilder`.
- [ ] Đã gọi `ui.configure(root)` trước khi chạy.
- [ ] Đã gọi `ui.setRoot(root, fullScreen)`.
- [ ] Đã xác định quy tắc focus và thứ tự xử lý phím.
- [ ] Menu item có action rõ ràng; status bar hiển thị trạng thái hữu ích.
- [ ] EventLoop subscription được lọc theo view và quản lý vòng đời.
- [ ] Modal được mở/đóng qua `ViewService` của TerminalUI.
- [ ] Các thay đổi dữ liệu được phản ánh bằng `redraw()`.
- [ ] Có bố cục fallback cho terminal nhỏ.
- [ ] Có đường thoát rõ ràng cho vòng lặp `ui.run()`.
- [ ] Đã kiểm thử focus, event, menu, modal và kích thước terminal.

## Tài liệu tham khảo

1. [Spring Shell 3.3 – AppView API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/AppView.html) – constructor, key/hotkey handling, menu/status visibility và theme.
2. [Spring Shell 3.3 – TerminalUI API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUI.html) – configure, root view, modal, event loop, redraw và run.
3. [Spring Shell 3.3 – TerminalUIBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUIBuilder.html) – tạo và cấu hình TerminalUI.
4. [Spring Shell 3.3 – View API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/View.html) – contract của view, focus, key/mouse handler và event loop.
5. [Spring Shell 3.3 – GridView API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/GridView.html) – addItem, row/column size và responsive layout.
6. [Spring Shell 3.3 – MenuBarView API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/MenuBarView.html) và [MenuBarItem API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/MenuBarView.MenuBarItem.html) – menu ngang, submenu và hotkey.
7. [Spring Shell 3.3 – StatusBarView API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/StatusBarView.html) – status items và action.
8. [Spring Shell 3.3 – EventLoop API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/event/EventLoop.html) – event streams, view events và dispatch.
9. [Spring Shell 3.3 – ShellMessageBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/message/ShellMessageBuilder.html) – message redraw và interrupt.
10. [Spring Shell 3.3 – Terminal UI AppView guide](https://docs.spring.io/spring-shell/reference/3.3/tui/views/app.html) – cấu trúc AppView và quy tắc điều phối phím.

`AppView` cung cấp khung ứng dụng terminal, còn cây `View` bên trong quyết định cách chia nội dung, điều hướng và cập nhật trạng thái. Hãy bắt đầu với một root view rõ ràng, dùng `GridView` cho bố cục, để `TerminalUI` điều phối event loop và chỉ thêm tầng lồng nhau khi nó giúp phân chia trách nhiệm hoặc thích ứng với kích thước terminal.
