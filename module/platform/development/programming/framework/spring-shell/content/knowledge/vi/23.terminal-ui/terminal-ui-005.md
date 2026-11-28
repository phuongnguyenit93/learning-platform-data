# ButtonView, MenuView và MenuBarView

Spring Shell 3.x cung cấp các view để xây dựng giao diện terminal có thể điều hướng bằng bàn phím và chuột. Ba thành phần thường gặp là **ButtonView**, **MenuView** và **MenuBarView**. Chúng cùng thuộc nhóm **View**, có thể được đặt trong một layout và được **TerminalUI** điều phối, nhưng phục vụ những thao tác khác nhau:

- **ButtonView** biểu diễn một nút để kích hoạt một hành động.
- **MenuView** hiển thị danh sách lựa chọn theo chiều dọc, có thể chứa menu con.
- **MenuBarView** hiển thị các nhóm menu theo chiều ngang, thường nằm ở đầu màn hình.

Tài liệu Spring Shell 3.4.3 đánh dấu Terminal UI là tính năng experimental và có thể thay đổi trong các phiên bản tiếp theo. Vì vậy, hãy kiểm tra API của minor version đang dùng và chạy thử trên terminal mục tiêu trước khi phát hành.

## 1. Vị trí của ba view trong Terminal UI

Terminal UI là bộ công cụ xây dựng giao diện terminal có trạng thái và tương tác. Một view có thể vẽ nội dung, nhận focus và xử lý sự kiện bàn phím hoặc chuột. **TerminalUI** kết nối terminal, event loop và cấu trúc view để hiển thị một màn hình hoàn chỉnh.

Ba view trong bài đều kế thừa **BoxView**, nên có thể sử dụng các khả năng chung như đường viền, tiêu đề, màu và padding:

| View | Cách hiển thị | Vai trò chính |
| --- | --- | --- |
| **ButtonView** | Một nút có đường viền và nhãn | Kích hoạt một hành động cụ thể |
| **MenuView** | Danh sách các mục theo chiều dọc | Điều hướng tới chức năng hoặc nhóm chức năng |
| **MenuBarView** | Các mục menu theo chiều ngang | Tạo thanh menu cấp cao như File, View, Help |

Có thể hình dung bố cục một ứng dụng terminal:

```text
┌──────────────────────────────────────────────────────────┐
│ File  Project  Help                         MenuBarView   │
├──────────────────────────────────────────────────────────┤
│ ┌──────────────────────┐  ┌────────────────────────────┐ │
│ │ Workspace            │  │                            │ │
│ │   Overview           │  │   Nội dung màn hình        │ │
│ │   Build              │  │                            │ │
│ │   Deploy             │  │   [ Deploy ]               │ │
│ └──────────────────────┘  └────────────────────────────┘ │
│             MenuView                  ButtonView          │
└──────────────────────────────────────────────────────────┘
```

**MenuBarView** cung cấp lối vào các nhóm chức năng, **MenuView** giúp chọn một chức năng trong danh sách và **ButtonView** thực hiện một hành động đang được hiển thị trên màn hình. Một ứng dụng có thể chỉ cần một trong ba view; không bắt buộc phải dùng chúng cùng nhau.

## 2. Package API trong Spring Shell 3.x

Các lớp chính trong nhánh 3.x nằm trong những package sau:

| Thành phần | Package |
| --- | --- |
| **TerminalUI** | **org.springframework.shell.component.view** |
| **ButtonView**, **MenuView**, **MenuBarView**, **GridView** | **org.springframework.shell.component.view.control** |
| **KeyEvent**, **MouseEvent** và các kiểu sự kiện | **org.springframework.shell.component.view.event** |

Ví dụ import:

```java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.control.ButtonView;
import org.springframework.shell.component.view.control.MenuView;
import org.springframework.shell.component.view.control.MenuBarView;
import org.springframework.shell.component.view.control.GridView;
```

Khi đọc tài liệu hoặc nâng cấp, không trộn các import 3.x với package **org.springframework.shell.jline.tui...** của Spring Shell 4.x. Tên lớp có thể giống nhau nhưng package và API có thể khác.

## 3. ButtonView: nút kích hoạt hành động

**ButtonView** là một view có đường viền và nhãn, hoạt động như một nút. Có thể tạo nút rỗng rồi đặt nội dung và hành động bằng setter, hoặc truyền cả hai vào constructor:

```java
import org.springframework.shell.component.view.control.ButtonView;

ButtonView saveButton = new ButtonView();
saveButton.setText("Lưu cấu hình");
saveButton.setAction(() -> configurationService.save());
```

Dạng ngắn:

```java
ButtonView deployButton = new ButtonView(
        "Triển khai",
        () -> deploymentService.deploy()
);
```

Khi người dùng chọn nút, **Runnable** đã đăng ký sẽ được gọi. Trong ví dụ, hành động gọi service nghiệp vụ; view chỉ nhận tương tác và kích hoạt hành động.

### Phím và chuột mặc định

**ButtonView** có các binding mặc định:

| Thiết bị | Thao tác | Kết quả |
| --- | --- | --- |
| Bàn phím | **Enter** | Chọn nút |
| Chuột | Thả nút trái (**Button1**) | Chọn nút |

Nút cũng phát sự kiện **ButtonViewSelectEvent** khi được chọn. Có thể dùng **Runnable** được truyền vào constructor hoặc **setAction(...)** để xử lý trực tiếp. Nếu cần quan sát sự kiện ở cấp event loop, có thể đăng ký subscriber cho event này. Tránh thực hiện cùng một nghiệp vụ ở cả callback và subscriber vì thao tác có thể bị gọi hai lần.

Ví dụ chỉ quan sát sự kiện:

```java
ui.getEventLoop().events()
        .map(message -> message.getPayload())
        .ofType(ButtonView.ButtonViewSelectEvent.class)
        .subscribe(event ->
                logger.info("Button được chọn: {}", event.view())
        );
```

**ButtonViewSelectEvent** chứa view phát sự kiện và **ButtonViewItemEventArgs**. Phần args hiện không mang dữ liệu bổ sung; có thể dùng **event.view()** để nhận diện nút phát sự kiện.

### Khi nào nên dùng ButtonView?

Dùng **ButtonView** khi có một hành động rõ ràng cần người dùng kích hoạt, ví dụ:

- Lưu thay đổi.
- Chạy build hoặc deploy.
- Làm mới dữ liệu.
- Xác nhận một thao tác đã được chuẩn bị.

Không nên tạo nhiều nút cho mọi chức năng nếu người dùng cần điều hướng qua một danh sách dài. Trong trường hợp đó, **MenuView** phù hợp hơn.

## 4. MenuView: danh sách lựa chọn theo chiều dọc

**MenuView** hiển thị các mục theo chiều dọc. Mỗi mục là một **MenuView.MenuItem**, có thể có tiêu đề, kiểu đánh dấu và hành động. Có thể khởi tạo menu bằng constructor nhận danh sách hoặc mảng item:

```java
import java.util.List;
import org.springframework.shell.component.view.control.MenuView;

MenuView menu = new MenuView(List.of(
        MenuView.MenuItem.of(
                "Làm mới",
                MenuView.MenuItemCheckStyle.NOCHECK,
                () -> projectService.refresh()
        ),
        MenuView.MenuItem.of(
                "Xem build",
                MenuView.MenuItemCheckStyle.NOCHECK,
                () -> projectService.showBuilds()
        ),
        MenuView.MenuItem.of(
                "Triển khai",
                MenuView.MenuItemCheckStyle.NOCHECK,
                () -> deploymentService.deploy()
        )
));
```

**MenuView** cũng hỗ trợ cập nhật danh sách sau khi tạo:

```java
menu.setItems(List.of(
        MenuView.MenuItem.of("Tổng quan"),
        MenuView.MenuItem.of("Cấu hình"),
        MenuView.MenuItem.of("Nhật ký")
));
```

**setItems(...)** thay thế danh sách item hiện tại. Truyền **null** sẽ làm danh sách rỗng.

### Phím và chuột mặc định

| Thiết bị | Thao tác | Kết quả |
| --- | --- | --- |
| Bàn phím | **CursorUp** | Di chuyển lựa chọn lên |
| Bàn phím | **CursorDown** | Di chuyển lựa chọn xuống |
| Bàn phím | **Enter** | Mở hoặc chọn item đang active |
| Chuột | Cuộn lên/xuống | Di chuyển lựa chọn |
| Chuột | Thả nút trái (**Button1**) | Chọn item |

Menu phát hai loại event:

- **MenuViewSelectedItemChangedEvent**: item đang được chọn thay đổi.
- **MenuViewOpenSelectedItemEvent**: người dùng yêu cầu mở item đang chọn.

Event chứa **MenuViewItemEventArgs**; có thể đọc item qua **event.args().item()**. Event đầu phù hợp để cập nhật phần xem trước hoặc status khi người dùng di chuyển qua các lựa chọn. Event thứ hai phù hợp khi cần phản ứng sau thao tác mở/chọn.

### Menu con với MenuView.Menu

**MenuView.Menu** là một loại **MenuItem** đặc biệt có thể chứa danh sách menu con. Dùng nó để nhóm các lựa chọn liên quan:

```java
MenuView menu = new MenuView(List.of(
        MenuView.MenuItem.of(
                "Tổng quan",
                MenuView.MenuItemCheckStyle.NOCHECK,
                () -> screenService.showOverview()
        ),
        MenuView.Menu.of(
                "Xuất dữ liệu",
                MenuView.MenuItem.of(
                        "CSV",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        () -> exportService.exportCsv()
                ),
                MenuView.MenuItem.of(
                        "JSON",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        () -> exportService.exportJson()
                )
        )
));
```

Ở đây, **Xuất dữ liệu** là menu cha; **CSV** và **JSON** là các mục con. Dùng menu con khi nhóm có nhiều hành động cùng một chủ đề, nhưng không nên lồng quá sâu vì người dùng sẽ khó nhớ vị trí của chức năng.

### Kiểu đánh dấu của MenuItem

**MenuView.MenuItemCheckStyle** điều khiển cách hiển thị trạng thái chọn:

| Kiểu | Ý nghĩa | Tình huống dùng |
| --- | --- | --- |
| **NOCHECK** | Hiển thị bình thường, không có dấu chọn | Lệnh hoặc hành động thông thường |
| **CHECKED** | Hiển thị trạng thái đã bật/chưa bật | Tùy chọn có thể bật hoặc tắt |
| **RADIO** | Hiển thị trạng thái chọn trong nhóm radio | Các lựa chọn loại trừ lẫn nhau |

Ví dụ:

```java
MenuView.MenuItem verboseItem = MenuView.MenuItem.of(
        "Hiển thị chi tiết",
        MenuView.MenuItemCheckStyle.CHECKED,
        () -> settings.toggleVerbose(),
        true
);
```

Tham số cuối là trạng thái checked ban đầu. **MenuView.toggle(item)** có thể dùng để đảo trạng thái đánh dấu của một item. Hãy giữ trạng thái hiển thị đồng bộ với cấu hình thật trong ứng dụng; dấu check chỉ nên phản ánh trạng thái đã được lưu hoặc trạng thái hiện tại có thể xác định.

## 5. MenuBarView: thanh menu theo chiều ngang

**MenuBarView** hiển thị các nhóm menu theo chiều ngang. Mỗi phần tử là một **MenuBarView.MenuBarItem**, có tiêu đề và danh sách **MenuView.MenuItem** bên trong. Khi người dùng mở một nhóm, các item tương ứng được hiển thị qua cơ chế menu của **MenuView**.

Ví dụ:

```java
import org.springframework.shell.component.view.control.MenuBarView;
import org.springframework.shell.component.view.control.MenuView;
import org.springframework.shell.component.view.event.KeyEvent.Key;
import org.springframework.shell.component.view.event.KeyEvent.KeyMask;

MenuBarView menuBar = MenuBarView.of(
        MenuBarView.MenuBarItem.of(
                "File",
                MenuView.MenuItem.of(
                        "Làm mới",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        () -> projectService.refresh()
                )
        ).setHotKey(Key.f | KeyMask.AltMask),
        MenuBarView.MenuBarItem.of(
                "Help",
                MenuView.MenuItem.of(
                        "Giới thiệu",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        () -> screenService.showAbout()
                )
        ).setHotKey(Key.h | KeyMask.AltMask)
);
```

**MenuBarItem.setHotKey(...)** đặt phím tắt để kích hoạt một nhóm menu. Ví dụ, **Alt+F** mở nhóm **File**, còn **Alt+H** mở nhóm **Help**. Các item con vẫn dùng **Runnable** riêng để thực hiện hành động.

### Phím và chuột mặc định

| Thiết bị | Thao tác | Kết quả |
| --- | --- | --- |
| Bàn phím | **CursorLeft** | Di chuyển lựa chọn sang nhóm menu bên trái |
| Bàn phím | **CursorRight** | Di chuyển lựa chọn sang nhóm menu bên phải |
| Chuột | Thả nút trái (**Button1**) | Chọn nhóm menu |
| Bàn phím | Hot key đã cấu hình | Kích hoạt nhóm menu tương ứng |

**MenuBarView** không phát event riêng. Hành động được xử lý bởi **Runnable** trên các **MenuItem** thuộc từng **MenuBarItem**. Nếu cần theo dõi lựa chọn của item, hãy dùng event của **MenuView** được dùng bên trong menu.

**MenuBarView.setSelected(index)** có thể đặt nhóm đang được chọn bằng chỉ số. Nếu chỉ số nằm ngoài phạm vi danh sách, không có nhóm nào được chọn. Khi cập nhật menu động, hãy kiểm tra lại chỉ số để tránh giữ lựa chọn cũ không còn hợp lệ.

## 6. Phân biệt ba view

| Tiêu chí | ButtonView | MenuView | MenuBarView |
| --- | --- | --- | --- |
| Hình thức | Một nút có viền và nhãn | Danh sách dọc | Thanh menu ngang |
| Thành phần nội dung | Text và một action | Nhiều MenuItem, có thể có submenu | Nhiều MenuBarItem, mỗi nhóm chứa MenuItem |
| Phím mặc định | Enter | Lên/xuống, Enter | Trái/phải |
| Chuột mặc định | Click nút trái | Cuộn và click | Click nhóm menu |
| Event riêng | ButtonViewSelectEvent | Selection changed và open selected | Không có |
| Dùng khi | Một hành động chính | Chọn chức năng trong danh sách | Điều hướng giữa các nhóm chức năng |

Ba view có thể phối hợp: **MenuBarView** cung cấp menu cấp cao, **MenuView** hiển thị chức năng trong một vùng nội dung, còn **ButtonView** đặt hành động nổi bật ở vị trí dễ nhận biết.

## 7. Đặt ba view vào cùng một màn hình

Các view không tự tạo một ứng dụng terminal hoàn chỉnh. Cần một root view để bố trí chúng và **TerminalUI** để điều phối vòng lặp tương tác. **GridView** là layout container có thể đặt view theo hàng/cột.

Ví dụ sau tạo thanh menu ở hàng đầu, menu dọc ở bên trái và nút triển khai ở vùng nội dung:

```java
import java.util.List;
import org.jline.terminal.Terminal;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.control.ButtonView;
import org.springframework.shell.component.view.control.GridView;
import org.springframework.shell.component.view.control.MenuBarView;
import org.springframework.shell.component.view.control.MenuView;

public class ProjectTerminalScreen {

    public void run(
            Terminal terminal,
            Runnable refreshAction,
            Runnable exportAction,
            Runnable deployAction,
            Runnable aboutAction) {

        MenuView menu = new MenuView(List.of(
                MenuView.MenuItem.of(
                        "Tổng quan",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        refreshAction
                ),
                MenuView.MenuItem.of(
                        "Xuất dữ liệu",
                        MenuView.MenuItemCheckStyle.NOCHECK,
                        exportAction
                )
        ));

        MenuBarView menuBar = MenuBarView.of(
                MenuBarView.MenuBarItem.of(
                        "Project",
                        MenuView.MenuItem.of(
                                "Làm mới",
                                MenuView.MenuItemCheckStyle.NOCHECK,
                                refreshAction
                        )
                ),
                MenuBarView.MenuBarItem.of(
                        "Help",
                        MenuView.MenuItem.of(
                                "Giới thiệu",
                                MenuView.MenuItemCheckStyle.NOCHECK,
                                aboutAction
                        )
                )
        );

        ButtonView deployButton = new ButtonView(
                "Triển khai",
                deployAction
        );

        GridView root = new GridView();
        root.addItem(menuBar, 0, 0, 1, 2, 0, 0);
        root.addItem(menu, 1, 0, 1, 1, 0, 0);
        root.addItem(deployButton, 1, 1, 1, 1, 0, 0);

        TerminalUI ui = new TerminalUI(terminal);
        ui.configure(menuBar);
        ui.configure(menu);
        ui.configure(deployButton);
        ui.configure(root);
        ui.setRoot(root, true);
        ui.setFocus(menu);
        ui.run();
    }
}
```

Đoạn code nhận một **Terminal** đã được ứng dụng quản lý và các **Runnable** cho nghiệp vụ. **TerminalUI.run()** bắt đầu event loop và chặn luồng gọi cho đến khi vòng lặp kết thúc. **setRoot(root, true)** đặt view gốc ở chế độ toàn màn hình; **setFocus(menu)** đặt focus ban đầu vào menu dọc.

**GridView.addItem(...)** nhận view, vị trí hàng/cột, số hàng/cột chiếm dụng và ngưỡng kích thước layout. Trong ví dụ, tất cả ngưỡng đều là **0**, nghĩa là vị trí đó được dùng ở mọi kích thước terminal. Với giao diện phức tạp, có thể đặt **minGridWidth** hoặc **minGridHeight** khác **0** để dùng bố cục khác khi terminal đủ rộng hoặc đủ cao.

Khi ứng dụng đã có **Terminal** do Spring Shell/JLine quản lý, hãy dùng lại terminal đó thay vì tạo thêm một terminal độc lập. Không chạy đồng thời hai **TerminalUI** trên cùng một terminal; chúng sẽ tranh quyền đọc input và ghi nội dung màn hình.

## 8. EventLoop và cách quan sát sự kiện

**TerminalUI** có một **EventLoop** điều phối sự kiện và thời điểm redraw. Các event trong event loop được biểu diễn dưới dạng Spring **Message**. Có thể đăng ký subscriber để quan sát event:

```java
ui.getEventLoop().events()
        .map(message -> message.getPayload())
        .ofType(MenuView.MenuViewOpenSelectedItemEvent.class)
        .subscribe(event -> {
            String title = event.args().item().getTitle();
            logger.info("Người dùng mở menu item: {}", title);
        });
```

**MenuViewOpenSelectedItemEvent** cho biết người dùng yêu cầu mở một item; **MenuViewSelectedItemChangedEvent** cho biết item đang chọn đã thay đổi. **ButtonViewSelectEvent** cho biết nút được chọn. Các subscriber phù hợp để cập nhật telemetry, status hoặc điều phối view; tránh đặt nghiệp vụ quan trọng ở nhiều nơi cùng lúc.

Đăng ký subscriber trước khi gọi **ui.run()** để không bỏ lỡ sự kiện đầu tiên. Nếu view được tạo và hủy nhiều lần, hãy quản lý subscription theo vòng đời view và dispose khi không còn cần lắng nghe.

## 9. Tách hành động giao diện khỏi nghiệp vụ

Một **Runnable** được gắn vào button hoặc menu item nên gọi service hoặc một lớp điều phối. Không nên đặt toàn bộ logic nghiệp vụ trong lambda:

```java
ButtonView deployButton = new ButtonView(
        "Triển khai",
        () -> deploymentService.deploy(projectId, environment)
);
```

Service cần chịu trách nhiệm kiểm tra quyền, validation, trạng thái hiện tại và xử lý lỗi. View chỉ nên khởi chạy thao tác và cập nhật giao diện theo kết quả.

Với tác vụ kéo dài, không nên chạy công việc đồng bộ lâu trên event loop vì giao diện có thể ngừng phản hồi. Hãy chạy tác vụ qua executor/service bất đồng bộ, sau đó gửi cập nhật về event loop và gọi **ui.redraw()** khi cần hiển thị trạng thái mới.

Nên xử lý exception trong hành động giao diện:

```java
ButtonView deployButton = new ButtonView("Triển khai", () -> {
    try {
        deploymentService.deploy(projectId, environment);
        statusService.setMessage("Triển khai thành công");
    }
    catch (DeploymentException ex) {
        statusService.setMessage("Không thể triển khai: " + ex.getMessage());
    }
});
```

Ví dụ minh họa cách phân tách xử lý thành công/thất bại; **statusService** đại diện cho thành phần cập nhật trạng thái của màn hình. Thông báo hiển thị cho người dùng cần được lọc để không lộ token, đường dẫn nội bộ hoặc chi tiết hạ tầng.

## 10. Thay đổi menu trong lúc ứng dụng chạy

Các view hỗ trợ cập nhật item sau khi khởi tạo:

- **MenuView.setItems(...)** thay toàn bộ danh sách menu.
- **MenuView.toggle(item)** đảo trạng thái check của một item.
- **MenuBarView.setItems(...)** thay danh sách nhóm menu.
- **MenuBarView.setSelected(index)** đổi nhóm đang được chọn.
- **ButtonView.setText(...)** đổi nhãn nút.
- **ButtonView.setAction(...)** thay hành động được gọi khi chọn nút.

Ví dụ cập nhật danh sách menu sau khi tải quyền người dùng:

```java
if (authorizationService.canDeploy()) {
    menu.setItems(List.of(
            MenuView.MenuItem.of("Tổng quan"),
            MenuView.MenuItem.of("Triển khai")
    ));
}
else {
    menu.setItems(List.of(
            MenuView.MenuItem.of("Tổng quan")
    ));
}
ui.redraw();
```

Việc ẩn một menu item không thay thế kiểm tra quyền ở service. Người dùng có thể gọi command hoặc API khác; nghiệp vụ vẫn phải kiểm tra quyền tại nơi thực hiện thao tác.

## 11. Binding bàn phím, hot key và chuột

Các binding mặc định đủ cho phần lớn tương tác cơ bản. Khi cần phím tắt riêng, một số view cho phép đăng ký hot key hoặc binding tùy chỉnh. Hot key được xử lý trước key binding thông thường.

Ví dụ menu bar có hot key:

```java
MenuBarView.MenuBarItem fileMenu = MenuBarView.MenuBarItem
        .of("File", MenuView.MenuItem.of("Làm mới"))
        .setHotKey(Key.f | KeyMask.AltMask);
```

Nếu tùy chỉnh phím, hãy giữ các thao tác điều hướng quen thuộc như lên/xuống, trái/phải và Enter nếu chúng vẫn có ý nghĩa trong view. Tránh gán cùng một tổ hợp phím cho nhiều hành động cạnh tranh trong cùng vùng focus.

Đối với chuột, kiểm tra cả sự kiện nhấn và thả theo hành vi mà view hỗ trợ. Tài liệu mặc định mô tả lựa chọn bằng sự kiện thả nút trái; không giả định mọi terminal hoặc môi trường SSH đều hỗ trợ đầy đủ mouse reporting.

## 12. Giới hạn môi trường terminal

**ButtonView**, **MenuView** và **MenuBarView** cần một terminal có thể nhận input tương tác. Chúng phù hợp với phiên CLI trực tiếp, nơi người dùng có thể dùng phím mũi tên, Enter hoặc chuột.

Với CI/CD, script hoặc non-interactive runner:

- Không yêu cầu người dùng điều hướng menu.
- Cung cấp command và option tường minh để automation gọi.
- Giữ logic nghiệp vụ trong service để cả command thường và TUI có thể dùng chung.
- Không giả định chuột hoạt động khi chạy qua SSH hoặc terminal giả lập.
- Cung cấp cách thoát hoặc quay lại rõ ràng nếu màn hình có nhiều cấp.

Terminal UI là một lớp trải nghiệm bổ sung cho CLI. Những thao tác quan trọng vẫn nên có command tương ứng để có thể chạy tự động, ghi log và kiểm thử mà không cần mô phỏng phím bấm.

## 13. Kiểm thử ba view

Kiểm thử nên bao gồm hành vi tương tác lẫn hành động nghiệp vụ:

| Thành phần | Ca kiểm thử cần có |
| --- | --- |
| **ButtonView** | Enter kích hoạt action; click kích hoạt action; action xử lý lỗi; đổi text/action khi chạy |
| **MenuView** | Lên/xuống thay đổi lựa chọn; Enter mở item; submenu điều hướng đúng; event selection/open phát đúng |
| **MenuBarView** | Trái/phải đổi nhóm; click mở nhóm; hot key kích hoạt đúng menu; item con gọi đúng action |
| Layout | Focus ban đầu đúng; view không chồng lấn; resize terminal không làm mất vùng thao tác |
| EventLoop | Subscriber nhận đúng event; subscription được dọn khi màn hình kết thúc |
| Service | Nghiệp vụ được gọi đúng; lỗi không làm hỏng vòng lặp UI; quyền được kiểm tra ở service |

Tách logic nghiệp vụ khỏi view giúp unit test service mà không cần tạo terminal. Sau đó kiểm thử tích hợp giao diện trên terminal thật hoặc terminal test phù hợp với môi trường build. Nên kiểm tra cả terminal hẹp, terminal rộng, Unicode và phiên SSH nếu đó là môi trường người dùng sẽ sử dụng.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Nhấn Enter nhưng button không chạy | View chưa có focus hoặc action chưa được gắn | Kiểm tra **setAction(...)** và focus |
| Menu không di chuyển bằng phím mũi tên | Focus đang nằm ở view khác hoặc key binding bị thay thế | Đặt focus cho MenuView và kiểm tra binding |
| Menu con không xuất hiện | Dùng MenuItem thường thay vì MenuView.Menu | Khai báo menu cha bằng **MenuView.Menu.of(...)** |
| Dấu check không phản ánh cấu hình | Trạng thái item và trạng thái nghiệp vụ không đồng bộ | Cập nhật check state theo nguồn dữ liệu thật |
| Hot key không kích hoạt menu | Giá trị key hoặc mask không đúng | Dùng **Key** và **KeyMask** đúng package 3.x |
| MenuBarView không có event để subscribe | View này không phát event riêng | Đặt action ở MenuItem; theo dõi event của MenuView nếu cần |
| Màn hình bị treo khi chọn nút | Runnable chạy tác vụ dài ngay trên event loop | Chuyển tác vụ dài sang executor và cập nhật UI sau |
| Hai màn hình ghi đè nhau | Nhiều TerminalUI cùng điều khiển một terminal | Chỉ chạy một UI loop trên một terminal |
| UI không hoạt động trong CI | Không có input terminal tương tác | Dùng command/option tường minh cho automation |

## 15. Checklist triển khai

- Xác nhận đang dùng package Terminal UI của Spring Shell 3.x.
- Nhớ rằng Terminal UI 3.4.3 được đánh dấu experimental.
- Chọn **ButtonView** cho hành động đơn, **MenuView** cho danh sách dọc và **MenuBarView** cho nhóm menu ngang.
- Dùng **MenuView.Menu** để tạo submenu.
- Chọn **NOCHECK**, **CHECKED** hoặc **RADIO** đúng ngữ nghĩa.
- Gắn action vào button hoặc menu item bằng **Runnable**.
- Dùng đúng key binding mặc định và hot key.
- Đặt view vào root layout và khởi chạy bằng **TerminalUI**.
- Đặt focus ban đầu cho view phù hợp.
- Quản lý event subscription theo vòng đời giao diện.
- Không chạy nghiệp vụ dài trực tiếp trên event loop.
- Kiểm tra quyền và validation trong service.
- Giữ command/option để automation không cần tương tác bằng phím.
- Kiểm thử bàn phím, chuột, resize terminal và hành vi khi lỗi.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — Terminal UI](https://docs.spring.io/spring-shell/reference/3.4/tui/index.html)
- [Spring Shell 3.4.3 — Views](https://docs.spring.io/spring-shell/reference/3.4/tui/views/index.html)
- [Spring Shell 3.4.3 — ButtonView](https://docs.spring.io/spring-shell/reference/3.4/tui/views/button.html)
- [Spring Shell 3.4.3 — MenuView](https://docs.spring.io/spring-shell/reference/3.4/tui/views/menu.html)
- [Spring Shell 3.4.3 — MenuBarView](https://docs.spring.io/spring-shell/reference/3.4/tui/views/menubar.html)
- [Spring Shell 3.4.3 — ButtonView API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ButtonView.html)
- [Spring Shell 3.4.3 — MenuView.MenuItem API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/MenuView.MenuItem.html)
- [Spring Shell 3.4.3 — MenuBarView.MenuBarItem API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/MenuBarView.MenuBarItem.html)
- [Spring Shell 3.4.3 — TerminalUI API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUI.html)
- [Spring Shell 3.4.3 — EventLoop](https://docs.spring.io/spring-shell/reference/3.4/tui/events/eventloop.html)
