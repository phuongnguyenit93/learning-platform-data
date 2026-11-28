# Vẽ lại, kích thước terminal và cập nhật dữ liệu view

Terminal UI của Spring Shell 3.x hiển thị giao diện qua TerminalUI, View và Screen. Khi dữ liệu thay đổi hoặc cửa sổ terminal được thay đổi kích thước, ứng dụng cần yêu cầu giao diện vẽ lại để nội dung và bố cục phản ánh trạng thái mới.

Ba việc cần phối hợp:

- **Cập nhật model:** lưu trạng thái mới mà view sẽ hiển thị.
- **Đo kích thước terminal:** đọc số cột và số hàng hiện tại để tính vùng hiển thị.
- **Yêu cầu redraw:** gửi yêu cầu cho event loop để vẽ lại màn hình theo model và kích thước mới.

Bài học dùng API Terminal UI của Spring Shell 3.2.x/3.3.x. Ví dụ dùng TerminalUIBuilder, BoxView, Screen và JLine Terminal.

## 1. Vai trò của TerminalUI, View và Screen

TerminalUI điều phối terminal, event loop, sự kiện bàn phím/chuột và cây view. View là phần tử hiển thị có thể tự vẽ và chứa các view con. Screen là vùng hiển thị trung gian giữa view và terminal cấp thấp.

| Thành phần | Trách nhiệm |
|---|---|
| TerminalUI | Khởi tạo root view, quản lý event loop, focus và yêu cầu vẽ lại |
| TerminalUIBuilder | Tạo TerminalUI đã được cấu hình với các dịch vụ cần thiết |
| View | Mô tả một vùng giao diện có thể hiển thị |
| BoxView | View cơ sở có thể vẽ tiêu đề, nền và đường viền |
| Screen | Cung cấp vùng vẽ và Writer để ghi nội dung |
| EventLoop | Nhận và điều phối message, key, mouse, signal và yêu cầu redraw |
| Terminal | Cung cấp kích thước cửa sổ terminal và tín hiệu hệ thống |

Luồng khởi tạo cơ bản:

~~~text
TerminalUIBuilder
       |
       v
TerminalUI
       |
       +---- configure(rootView)
       |
       +---- setRoot(rootView, fullScreen)
       |
       v
    run()
       |
       v
   EventLoop
       |
       v
   View.draw(Screen)
       |
       v
    Terminal
~~~

TerminalUI.run() chạy vòng lặp giao diện và chặn cho đến khi vòng lặp kết thúc. Hãy cấu hình view và đặt root trước khi gọi run().

## 2. Tạo TerminalUI bằng TerminalUIBuilder

Spring Shell Boot cung cấp TerminalUIBuilder đã được cấu hình. Có thể inject builder qua constructor:

~~~java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.stereotype.Component;

@Component
public class DashboardScreen {

    private final TerminalUIBuilder terminalUIBuilder;

    public DashboardScreen(TerminalUIBuilder terminalUIBuilder) {
        this.terminalUIBuilder = terminalUIBuilder;
    }

    public void show() {
        TerminalUI ui = terminalUIBuilder.build();
        BoxView root = new BoxView();

        ui.configure(root);
        ui.setRoot(root, true);
        ui.run();
    }
}
~~~

build() tạo một TerminalUI mới và áp dụng cấu hình từ builder. configure(view) gắn các dịch vụ cần thiết vào view, gồm event loop, theme resolver, theme name và view service.

Không cần tự tạo event loop hoặc theme resolver khi dùng builder do Spring Shell Boot cấu hình. Nếu khởi tạo TerminalUI thủ công bằng constructor nhận Terminal, ứng dụng phải tự bảo đảm các dịch vụ và cấu hình view cần thiết.

## 3. Vẽ nội dung bằng BoxView và Screen.Writer

BoxView là một view cơ sở có thể hiển thị tiêu đề và đường viền. setDrawFunction(...) nhận callback được gọi sau khi view đã vẽ phần khung. Callback nhận Screen và Rectangle giới hạn vùng vẽ, sau đó trả về rectangle.

~~~java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.screen.Screen;
import org.springframework.stereotype.Component;

@Component
public class DashboardScreen {

    private final TerminalUIBuilder terminalUIBuilder;

    public DashboardScreen(TerminalUIBuilder terminalUIBuilder) {
        this.terminalUIBuilder = terminalUIBuilder;
    }

    public void show() {
        TerminalUI ui = terminalUIBuilder.build();
        BoxView root = new BoxView();
        root.setTitle("Trạng thái dịch vụ");

        root.setDrawFunction((screen, rect) -> {
            Screen.Writer writer = screen.writerBuilder().build();
            writer.text("Dịch vụ đang hoạt động", rect.x() + 1, rect.y() + 1);
            writer.text("Nhấn Ctrl+C để thoát", rect.x() + 1, rect.y() + 2);
            return rect;
        });

        ui.configure(root);
        ui.setRoot(root, true);
        try {
            ui.run();
        }
        finally {
            ui = null;
            root.destroy();
        }
    }
}
~~~

Screen.Writer có thể ghi chuỗi tại tọa độ (x, y) hoặc căn chuỗi trong một Rectangle. Ví dụ căn giữa:

~~~java
import org.springframework.shell.component.view.screen.HorizontalAlign;
import org.springframework.shell.component.view.screen.VerticalAlign;

writer.text(
        "Hello World",
        rect,
        HorizontalAlign.CENTER,
        VerticalAlign.CENTER);
~~~

Tọa độ và kích thước được tính theo ô ký tự của terminal. Khi vẽ nhiều dòng, hãy dựa vào rect.x(), rect.y(), rect.width() và rect.height() để không ghi ra ngoài vùng được cấp.

Callback vẽ nên làm việc ngắn gọn: đọc một snapshot dữ liệu, định dạng và ghi nội dung. Không gọi database, HTTP hoặc thao tác I/O chặn trong callback vì nó chạy trong quá trình render và có thể làm giao diện ngừng phản hồi.

## 4. Yêu cầu vẽ lại toàn màn hình

Sau khi dữ liệu thay đổi, gọi TerminalUI.redraw():

~~~java
state.set(latestState);
ui.redraw();
~~~

redraw() yêu cầu vẽ lại toàn bộ màn hình. API này gửi một message vào event loop; message được xử lý khi event loop có thể thực hiện. Vì vậy, redraw() là yêu cầu cập nhật giao diện, không phải lời gọi đồng bộ để vẽ ngay tại dòng code hiện tại.

Có thể gửi message redraw trực tiếp qua event loop:

~~~java
import org.springframework.shell.component.message.ShellMessageBuilder;

ui.getEventLoop().dispatch(ShellMessageBuilder.ofRedraw());
~~~

Đây là message cùng loại mà TerminalUI.redraw() sử dụng. Trong code ứng dụng thông thường, gọi ui.redraw() dễ đọc hơn; dispatch trực tiếp hữu ích khi đang làm việc với các message khác của event loop.

Không gọi view.draw(screen) trực tiếp để cập nhật giao diện. TerminalUI cần điều phối việc render, layer, view bounds và event loop; hãy cập nhật model rồi gửi yêu cầu redraw.

## 5. Cập nhật dữ liệu view sau khi service trả kết quả

View nên đọc dữ liệu từ một model hoặc snapshot. Khi dữ liệu mới đến, thay snapshot rồi yêu cầu redraw. Cách này tránh việc callback vẽ phải truy vấn service mỗi lần màn hình render.

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.screen.Screen;
import org.springframework.stereotype.Component;

@Component
public class DashboardScreen {

    private record DashboardState(long completed, String status) {
    }

    private final AtomicReference<DashboardState> state =
            new AtomicReference<>(new DashboardState(0, "Đang khởi tạo"));

    private volatile TerminalUI ui;
    private final TerminalUIBuilder terminalUIBuilder;

    public DashboardScreen(TerminalUIBuilder terminalUIBuilder) {
        this.terminalUIBuilder = terminalUIBuilder;
    }

    public void show() {
        ui = terminalUIBuilder.build();
        BoxView root = new BoxView();
        root.setTitle("Tiến trình xử lý");

        root.setDrawFunction((screen, rect) -> {
            DashboardState snapshot = state.get();
            Screen.Writer writer = screen.writerBuilder().build();

            if (rect.width() > 4 && rect.height() > 1) {
                writer.text(
                        "Đã xử lý: " + snapshot.completed(),
                        rect.x() + 1,
                        rect.y() + 1);
            }
            if (rect.width() > 4 && rect.height() > 2) {
                writer.text(
                        "Trạng thái: " + snapshot.status(),
                        rect.x() + 1,
                        rect.y() + 2);
            }
            return rect;
        });

        ui.configure(root);
        ui.setRoot(root, true);
        ui.run();
    }

    public void onProgress(long completed, String status) {
        state.set(new DashboardState(completed, status));
        TerminalUI current = ui;
        if (current != null) {
            current.redraw();
        }
    }
}
~~~

Trong ví dụ, AtomicReference cho phép callback vẽ đọc snapshot nhất quán khi dữ liệu được cập nhật từ luồng khác. onProgress(...) cập nhật trạng thái rồi gửi yêu cầu redraw. Khi event loop vẽ lại, callback đọc snapshot mới nhất.

Với ứng dụng có nhiều dữ liệu, nên tạo một immutable view model gồm những trường cần hiển thị. Không đưa entity JPA hoặc đối tượng service phức tạp trực tiếp vào callback vẽ.

## 6. Lấy kích thước terminal hiện tại

JLine Terminal.getSize() trả về kích thước cửa sổ terminal đang hiển thị. Size cung cấp:

- getColumns(): số ô ký tự theo chiều ngang.
- getRows(): số hàng theo chiều dọc.

Ví dụ:

~~~java
import org.jline.terminal.Size;
import org.jline.terminal.Terminal;

Size size = terminal.getSize();
int columns = size.getColumns();
int rows = size.getRows();
~~~

Kích thước terminal được tính bằng ô ký tự, không phải pixel. Đừng dùng chiều rộng pixel của cửa sổ desktop để tính layout terminal.

Hãy đọc kích thước mới khi cần tính lại bố cục. Không lưu cứng các giá trị như 80 x 24 làm kích thước thật của người dùng; chúng chỉ phù hợp làm kích thước giả lập trong một số bài test.

## 7. Điều chỉnh vùng hiển thị theo kích thước terminal

TerminalUI.setRoot(view, fullScreen) xác định root view có yêu cầu toàn màn hình hay không. Khi fullScreen là true, mặc định vùng của root view bằng kích thước terminal. Có thể thay đổi phép tính vùng bằng setFullScreenViewRect(...).

Ví dụ chừa lề một ô ở mỗi cạnh:

~~~java
import org.jline.terminal.Size;
import org.springframework.shell.geom.Rectangle;

ui.setFullScreenViewRect((terminal, view) -> {
    Size size = terminal.getSize();
    int width = Math.max(1, size.getColumns() - 2);
    int height = Math.max(1, size.getRows() - 2);
    return new Rectangle(1, 1, width, height);
});
~~~

Callback nhận Terminal và View, vì vậy có thể tính rectangle theo kích thước hiện tại thay vì giữ một rectangle cố định.

Với view không chiếm toàn màn hình, dùng setNonfullScreenViewRect(...):

~~~java
ui.setNonfullScreenViewRect((terminal, view) -> {
    Size size = terminal.getSize();
    int height = Math.min(8, size.getRows());
    return new Rectangle(0, 0, size.getColumns(), height);
});
ui.setRoot(root, false);
~~~

Mặc định, vùng non-full-screen dùng rectangle đã gán cho root view nếu rectangle đó không rỗng. Nếu chưa có, Spring Shell dùng vùng bắt đầu từ (0, 0), rộng bằng số cột terminal và cao 5 hàng.

Hãy dùng Math.max hoặc Math.min khi tính kích thước để không tạo rectangle có chiều rộng hoặc chiều cao bằng số âm khi terminal quá nhỏ.

## 8. Phản ứng khi người dùng thay đổi kích thước cửa sổ

Trên terminal hỗ trợ tín hiệu resize, JLine có Terminal.Signal.WINCH. Ứng dụng có thể đăng ký signal handler để đọc kích thước mới và yêu cầu vẽ lại:

~~~java
import org.jline.terminal.Terminal;
import org.jline.terminal.Terminal.SignalHandler;

SignalHandler previousHandler = terminal.handle(
        Terminal.Signal.WINCH,
        signal -> ui.redraw());

try {
    ui.run();
}
finally {
    terminal.handle(Terminal.Signal.WINCH, previousHandler);
}
~~~

Khi nhận WINCH, có thể đọc terminal.getSize() để lấy kích thước hiệu lực rồi gọi redraw(). Nếu rectangle được tính bằng setFullScreenViewRect hoặc setNonfullScreenViewRect, callback sẽ nhận terminal hiện tại trong lần render tiếp theo và có thể tính lại vùng view.

Việc hỗ trợ và phát signal phụ thuộc terminal, hệ điều hành và cách chạy ứng dụng. Nếu môi trường không phát WINCH, vẫn có thể yêu cầu redraw sau một sự kiện khác làm thay đổi bố cục, ví dụ thay đổi panel, thay đổi nội dung hoặc thao tác điều hướng.

Không gọi Screen.resize(...) để thay đổi kích thước terminal vật lý. Screen là vùng vẽ ảo; kích thước cửa sổ thật được JLine cung cấp qua Terminal.

## 9. Kết hợp cập nhật dữ liệu và thay đổi kích thước

Một view có thể nhận hai loại thay đổi:

1. **Dữ liệu thay đổi:** số liệu, trạng thái công việc hoặc nội dung danh sách mới.
2. **Kích thước thay đổi:** số cột hoặc số hàng của terminal đổi.

Cả hai đều có thể dẫn tới ui.redraw(). Trong callback vẽ, hãy đọc snapshot mới nhất và dùng rectangle hiện tại để quyết định hiển thị bao nhiêu nội dung.

~~~java
root.setDrawFunction((screen, rect) -> {
    DashboardState snapshot = state.get();
    Screen.Writer writer = screen.writerBuilder().build();

    int contentWidth = Math.max(0, rect.width() - 2);
    int contentHeight = Math.max(0, rect.height() - 2);

    if (contentHeight >= 1 && contentWidth >= 12) {
        writer.text(
                shorten("Trạng thái: " + snapshot.status(), contentWidth),
                rect.x() + 1,
                rect.y() + 1);
    }
    if (contentHeight >= 2 && contentWidth >= 12) {
        writer.text(
                "Đã xử lý: " + snapshot.completed(),
                rect.x() + 1,
                rect.y() + 2);
    }
    return rect;
});
~~~

Hàm shorten(...) trong ví dụ là hàm tiện ích của ứng dụng, cắt chuỗi theo độ rộng hiển thị. Với tiếng Việt hoặc ký tự Unicode có độ rộng terminal khác nhau, nên dùng API đo độ rộng ký tự theo terminal thay vì chỉ dựa vào String.length().

Ở terminal hẹp, có thể ẩn các cột phụ hoặc chỉ hiển thị thông tin quan trọng. Ở terminal cao hơn, view có thể hiển thị thêm lịch sử hoặc chi tiết. Bố cục nên dựa trên rect.width() và rect.height() để thích ứng với vùng thực tế được cấp.

## 10. Dùng EventLoop để gửi redraw

EventLoop là nơi điều phối message trong vòng đời của giao diện. Nó cung cấp dispatch(...) để gửi message, keyEvents() và mouseEvents() để nhận sự kiện đầu vào, cùng các luồng sự kiện hệ thống và view.

Hai cách yêu cầu redraw:

~~~java
// Cách thông thường
ui.redraw();

// Gửi message redraw trực tiếp vào event loop
ui.getEventLoop().dispatch(ShellMessageBuilder.ofRedraw());
~~~

ShellMessageBuilder.ofRedraw() tạo message redraw. TerminalUI.redraw() đã thực hiện việc dispatch này, nên không cần gọi cả hai cách cho cùng một thay đổi.

Nếu một thao tác nền tạo ra nhiều cập nhật liên tiếp, hãy gộp hoặc giới hạn tần suất redraw. Vẽ lại toàn màn hình cho mỗi byte hoặc mỗi bản ghi có thể làm event loop bận và khiến tương tác bàn phím/chuột chậm đi.

## 11. Vòng đời của view và dọn dẹp

TerminalUI.run() là thao tác chặn. Khi vòng lặp kết thúc, hãy dọn dẹp tài nguyên mà ứng dụng tự đăng ký:

- Khôi phục signal handler đã thay thế.
- Hủy subscription hoặc task nền không còn cần thiết.
- Gọi destroy() trên custom view khi view không còn được sử dụng.
- Không đóng Terminal do Spring quản lý nếu ứng dụng không sở hữu terminal đó.

Ví dụ:

~~~java
try {
    ui.run();
}
finally {
    terminal.handle(Terminal.Signal.WINCH, previousHandler);
    root.destroy();
}
~~~

Nếu có task nền cập nhật model, hãy hủy task hoặc subscription khi giao diện kết thúc để nó không tiếp tục gọi redraw() trên một UI đã ngừng hoạt động.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Dữ liệu model đã đổi nhưng màn hình vẫn cũ | Chưa yêu cầu redraw | Cập nhật model rồi gọi ui.redraw() |
| Màn hình nhấp nháy hoặc vẽ quá nhiều | Gọi redraw liên tục trong vòng lặp nhanh | Gộp cập nhật và giới hạn tần suất redraw |
| Nội dung bị cắt khi terminal hẹp | View dùng tọa độ hoặc kích thước cố định | Dựa vào rect.width() và rect.height() |
| View không mở rộng khi terminal rộng hơn | Root view dùng rectangle cố định | Dùng setFullScreenViewRect hoặc setNonfullScreenViewRect theo terminal.getSize() |
| Sau khi resize, nội dung cũ còn sót | Chưa yêu cầu redraw hoặc callback không vẽ lại toàn vùng | Gửi redraw và bảo đảm callback vẽ trạng thái đầy đủ |
| Chữ bị ghi ra ngoài khung | Không tính phần padding và giới hạn rectangle | Dùng vùng nội dung bên trong rectangle |
| UI ngừng phản hồi khi cập nhật dữ liệu | Callback vẽ gọi service hoặc I/O chặn | Nạp dữ liệu bên ngoài callback; callback chỉ đọc snapshot |
| Giao diện hỏng sau khi in log | Ghi trực tiếp vào terminal writer khi full-screen UI đang chạy | Ghi log qua logger; cập nhật thông báo trong view rồi redraw |
| Resize không làm đổi bố cục | Terminal không phát signal hoặc handler chưa đăng ký | Kiểm tra WINCH, đọc lại Terminal.getSize() và yêu cầu redraw từ sự kiện phù hợp |
| Handler resize còn tác động sau khi UI đóng | Không khôi phục handler cũ | Khôi phục handler trong finally |

## 13. Kiểm thử redraw và resize

Nên kiểm tra view ở nhiều kích thước và nhiều trạng thái dữ liệu:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Khởi động với terminal 80 x 24 | Root view chiếm đúng vùng được cấu hình |
| Thu nhỏ còn 40 x 12 | Nội dung không vượt rectangle, các trường phụ được ẩn hoặc rút gọn |
| Mở rộng terminal | View sử dụng thêm không gian khi phù hợp |
| Thay đổi snapshot dữ liệu | Lần redraw tiếp theo hiển thị dữ liệu mới |
| Cập nhật từ luồng nền | UI nhận redraw mà không truy vấn service trong callback vẽ |
| Thoát UI | Signal handler và subscription được dọn dẹp |
| Terminal không phát resize signal | Sự kiện cập nhật khác vẫn có thể yêu cầu redraw |

Có thể kiểm thử logic tính rectangle bằng các kích thước giả lập. Để xác nhận tín hiệu resize và thao tác vẽ trên terminal thật, nên chạy integration test với pseudo-terminal hoặc kiểm tra thủ công trong terminal emulator.

## 14. Quy trình triển khai

1. Tạo TerminalUI bằng TerminalUIBuilder.
2. Tạo root view, ví dụ BoxView, và cấu hình callback vẽ.
3. Gọi ui.configure(view) rồi ui.setRoot(view, fullScreen).
4. Nếu cần bố cục riêng, cấu hình setFullScreenViewRect hoặc setNonfullScreenViewRect.
5. Đọc kích thước hiện tại bằng terminal.getSize().
6. Đăng ký xử lý WINCH nếu ứng dụng cần phản ứng trực tiếp với resize.
7. Khi dữ liệu thay đổi, cập nhật snapshot và gọi ui.redraw().
8. Gọi ui.run() để bắt đầu vòng lặp giao diện.
9. Trong finally, khôi phục signal handler và dọn dẹp view/task.
10. Kiểm thử với terminal hẹp, rộng, ít hàng và nhiều hàng.

## 15. Tổng kết

TerminalUI quản lý vòng lặp giao diện và cung cấp redraw() để gửi yêu cầu vẽ lại vào event loop. View nên đọc dữ liệu từ một snapshot, vẽ qua Screen.Writer và dùng rectangle được cấp để giới hạn nội dung. Khi model thay đổi, cập nhật snapshot rồi gọi redraw(); không vẽ trực tiếp ra terminal trong lúc full-screen UI đang hoạt động.

JLine Terminal.getSize() cung cấp số cột và số hàng hiện tại. Dùng kích thước này trong setFullScreenViewRect hoặc setNonfullScreenViewRect để bố cục thay đổi theo terminal. Khi cần phản ứng với resize, có thể lắng nghe Terminal.Signal.WINCH, đọc kích thước mới và yêu cầu redraw. Kiểm thử ở nhiều kích thước giúp phát hiện nội dung bị cắt, vùng vẽ vượt giới hạn và redraw quá thường xuyên.

## Tài liệu tham khảo

- [Spring Shell 3.2.8 — Terminal UI Introduction](https://docs.spring.io/spring-shell/reference/3.2/tui/intro/index.html) — khởi tạo TerminalUIBuilder, cấu hình BoxView, đặt root view và chạy event loop.
- [Spring Shell 3.3.0 TerminalUI API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUI.html) — configure, setRoot, run, redraw, setFullScreenViewRect và setNonfullScreenViewRect.
- [Spring Shell 3.3.0 TerminalUIBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUIBuilder.html) — tạo và cấu hình TerminalUI.
- [Spring Shell 3.3.0 AbstractView API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/AbstractView.html) — setDrawFunction, draw và quản lý event loop của view.
- [Spring Shell 3.3.0 BoxView API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/BoxView.html) — view có tiêu đề, đường viền, padding và draw callback.
- [Spring Shell 3.3.0 Screen API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/screen/Screen.html) — vùng vẽ ảo, writer builder và resize screen.
- [Spring Shell 3.3.0 EventLoop API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/event/EventLoop.html) — dispatch message, key event, mouse event và system event.
- [Spring Shell 3.3.0 ShellMessageBuilder API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/message/ShellMessageBuilder.html) — tạo message redraw và các message giao diện.
- [JLine Terminal Handling](https://jline.github.io/docs/terminal/) — lấy kích thước terminal, kiểm tra chế độ tương tác và xử lý tín hiệu resize.
