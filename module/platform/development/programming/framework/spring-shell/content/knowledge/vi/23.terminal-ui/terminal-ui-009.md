# Xử lý phím, focus và sự kiện chuột khi được hỗ trợ

## 1. Terminal UI nhận tương tác từ nhiều nguồn

Một giao diện terminal có thể nhận thao tác từ bàn phím, chuột và tín hiệu hệ thống. Spring Shell 3.x cung cấp `TerminalUI` để kết nối terminal, các view và `EventLoop` thành một ứng dụng giao diện tương tác.

Trong một màn hình quản trị, người dùng có thể:

- Dùng phím mũi tên để di chuyển giữa các mục.
- Nhấn Enter để mở hoặc xác nhận lựa chọn.
- Dùng phím tắt như `q` để đóng màn hình hoặc `?` để mở trợ giúp.
- Chuyển focus giữa thanh menu, vùng nội dung và thanh trạng thái.
- Nhấp chuột vào một hàng hoặc một nút khi terminal hỗ trợ mouse reporting.
- Dùng con lăn chuột để cuộn danh sách nếu view và terminal hỗ trợ thao tác đó.

Terminal UI của Spring Shell 3.4 vẫn được đánh dấu là tính năng thử nghiệm và API có thể thay đổi. Khi dùng trong sản phẩm, hãy khóa phiên bản Spring Shell, kiểm thử trên terminal mục tiêu và đọc đúng tài liệu của phiên bản đang chạy.

## 2. TerminalUI và EventLoop phối hợp như thế nào?

`TerminalUI` là thành phần điều phối chính. Nó quản lý terminal, cây view, focus, modal view và event loop. `EventLoop` nhận các sự kiện rồi điều phối chúng trong vòng đời của giao diện.

Các loại sự kiện trong `EventLoop.Type` gồm:

| Loại | Nội dung |
|---|---|
| `KEY` | Binding và sự kiện bàn phím từ terminal. |
| `MOUSE` | Sự kiện chuột từ terminal. |
| `SIGNAL` | Tín hiệu terminal như resize hoặc signal hệ thống được chuyển vào loop. |
| `SYSTEM` | Sự kiện hệ thống, ví dụ yêu cầu redraw. |
| `VIEW` | Sự kiện do view phát ra, như lựa chọn thay đổi hoặc nút được kích hoạt. |
| `USER` | Sự kiện tùy chỉnh do ứng dụng gửi vào loop. |
| `TASK` | Sự kiện liên quan đến tác vụ trong event loop. |

Mọi sự kiện trong loop được biểu diễn dưới dạng Spring `Message`. Khi cần xử lý một loại cụ thể, dùng các luồng đã lọc như `keyEvents()`, `mouseEvents()`, `signalEvents()` hoặc `viewEvents(...)` thay vì tự phân tích mọi message.

~~~mermaid
flowchart TD
    A[Terminal / JLine] --> B[TerminalUI]
    B --> C[EventLoop]
    C --> D[KEY events]
    C --> E[MOUSE events]
    C --> F[SIGNAL / SYSTEM events]
    C --> G[VIEW / USER / TASK events]
    D --> H[Key handler của view đang focus]
    E --> I[Mouse handler của view]
    F --> J[Cập nhật trạng thái / redraw]
    G --> K[Cập nhật state và điều hướng]
    H --> L[View tree render lại]
    I --> L
    J --> L
    K --> L
~~~

`TerminalUI.run()` bắt đầu vòng lặp thực thi và chặn cho đến khi vòng lặp kết thúc. Vì vậy, code khởi chạy UI thường gọi `run()` sau khi đã tạo view, cấu hình root và đăng ký những listener cần thiết.

## 3. Khởi tạo TerminalUI và view gốc

Spring Shell 3.x cung cấp `TerminalUIBuilder` để tạo `TerminalUI`. Một view đơn giản có thể dùng `BoxView` làm root:

~~~java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.BoxView;

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

`configure(root)` gắn các dịch vụ cần thiết như event loop, theme resolver và `ViewService` vào view. `setRoot(root, true)` đặt root view và yêu cầu hiển thị toàn màn hình. `run()` bắt đầu nhận sự kiện và render giao diện.

Trong ứng dụng thực tế, root thường là `AppView` chứa vùng nội dung, menu và status bar; hoặc một `BoxView` có các view con được bố trí theo nhu cầu. Không cần tự đọc phím từ `Terminal.reader()` khi đã dùng `TerminalUI`, vì event loop và view handlers đảm nhận luồng tương tác.

## 4. Đăng ký sự kiện bàn phím toàn cục

`EventLoop.keyEvents()` trả về `Flux<KeyEvent>`. `KeyEvent` là record chứa mã phím và dữ liệu đầu vào. Một số phương thức hữu ích:

- `isKey(int)` kiểm tra sự kiện có khớp mã phím hay không.
- `hasCtrl()` kiểm tra phím Ctrl có được nhấn cùng hay không.
- `getPlainKey()` lấy mã phím không tính modifier.
- `key()` và `data()` trả về dữ liệu thô của sự kiện.

Ví dụ đăng ký listener để quan sát phím Enter và Ctrl+C:

~~~java
import reactor.core.Disposable;

import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.event.EventLoop;
import org.springframework.shell.component.view.event.KeyEvent;

private void observeKeys(TerminalUI ui) {
    EventLoop eventLoop = ui.getEventLoop();

    Disposable keySubscription = eventLoop.keyEvents()
            .subscribe(event -> {
                if (event.isKey(KeyEvent.Key.Enter)) {
                    logger.debug("Người dùng nhấn Enter");
                }
                else if (event.hasCtrl()
                        && event.getPlainKey() == KeyEvent.Key.c) {
                    logger.debug("Người dùng nhấn Ctrl+C");
                }
            });

    // EventLoop tự dispose subscription khi loop kết thúc.
    eventLoop.onDestroy(keySubscription);
}
~~~

`logger` là logger của ứng dụng. Listener toàn cục phù hợp cho phím tắt ở cấp ứng dụng, telemetry hoặc xử lý sự kiện không thuộc riêng một view. Không nên xử lý cùng một thao tác ở cả listener toàn cục và key binding của view vì có thể khiến một lần nhấn phím kích hoạt hành động hai lần.

Nếu chỉ cần phản hồi phím trong một view cụ thể, nên đăng ký binding tại view. Cách đó giữ logic bàn phím gần với trạng thái mà view quản lý và để view đang focus quyết định nhận sự kiện.

## 5. Key binding, hotkey và thứ tự xử lý

`AbstractView` cung cấp các phương thức đăng ký binding:

- `registerKeyBinding(...)`: gắn phím với `Runnable`, command hoặc `KeyBindingConsumer`.
- `registerHotKeyBinding(...)`: gắn phím tắt ưu tiên xử lý trước key binding thông thường.
- `registerViewCommand(...)`: đăng ký một command nội bộ của view.

Các view dựng sẵn đã có binding mặc định phù hợp với chức năng của chúng. Khi tạo view riêng hoặc muốn thay đổi hành vi mặc định, các binding thường được đăng ký trong `initInternal()`. Ví dụ view danh sách hỗ trợ mũi tên lên/xuống và phím `q`:

~~~java
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.event.KeyEvent;

public class ResultsView extends BoxView {

    private int selectedIndex;

    @Override
    protected void initInternal() {
        super.initInternal();

        registerKeyBinding(KeyEvent.Key.CursorDown, this::selectNext);
        registerKeyBinding(KeyEvent.Key.CursorUp, this::selectPrevious);
        registerHotKeyBinding(KeyEvent.Key.q, this::requestClose);
    }

    private void selectNext() {
        selectedIndex++;
    }

    private void selectPrevious() {
        selectedIndex = Math.max(0, selectedIndex - 1);
    }

    private void requestClose() {
        // Gửi yêu cầu đóng view hoặc điều hướng về màn hình trước.
    }
}
~~~

Đoạn mã minh họa binding. Ứng dụng cần bổ sung giới hạn trên của `selectedIndex`, logic chọn item và cách điều hướng khi đóng view. `KeyEvent.Key` cung cấp hằng số cho phím đặc biệt như `CursorUp`, `CursorDown`, `Enter`, `Tab`, cùng các ký tự thông thường.

Hotkey được xử lý trước key binding thông thường của view. Điều này hữu ích cho phím toàn cục như mở trợ giúp hoặc yêu cầu thoát, nhưng không nên chiếm những phím mà input view cần dùng để nhập văn bản.

## 6. Focus quyết định view nào nhận phím

Focus xác định view đang là đích nhận tương tác bàn phím. `TerminalUI` triển khai `ViewService`, cung cấp:

- `setFocus(view)` để chuyển focus đến view.
- `setFocus(null)` để xóa focus hiện tại.
- `getModal()` và `setModal(view)` để quản lý modal view.

Mỗi `View` có `hasFocus()` để kiểm tra trạng thái focus và callback `focus(view, boolean)` khi view nhận hoặc mất focus.

Ví dụ chuyển focus đến ô tìm kiếm sau khi giao diện được cấu hình:

`terminalUIBuilder` là bean được inject như phần 3; các view `mainView`, `menuBarView`, `statusBarView` và `searchView` được tạo trước đó.

~~~java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.AppView;
import org.springframework.shell.component.view.control.View;

TerminalUI ui = terminalUIBuilder.build();
AppView root = new AppView(mainView, menuBarView, statusBarView);

ui.configure(root);
ui.setRoot(root, true);
ui.setFocus(searchView);
ui.run();
~~~

`mainView`, `menuBarView`, `statusBarView` và `searchView` là các view đã được tạo và gắn vào cây giao diện phù hợp. `setFocus(searchView)` yêu cầu view tìm kiếm nhận focus ban đầu.

Khi focus thay đổi, view có thể cập nhật trạng thái hiển thị:

~~~java
@Override
public void focus(View view, boolean focus) {
    super.focus(view, focus);
    if (focus) {
        // Đánh dấu view đang nhận bàn phím.
    }
    else {
        // Dừng trạng thái nhập hoặc bỏ highlight focus nếu cần.
    }
}
~~~

Không nên giả định focus tự chuyển theo thứ tự component nếu ứng dụng có nhiều vùng tương tác. Hãy xác định rõ phím nào chuyển focus, view nào nhận phím và cách người dùng quay lại vùng trước đó.

## 7. AppView điều phối menu, nội dung và status bar

`AppView` là view bố cục cấp ứng dụng, thường chứa:

- `MenuBarView` ở phía trên.
- View nội dung chính ở giữa.
- `StatusBarView` ở phía dưới.

Theo quy tắc của `AppView`, khi menu đang focus, nó được hỏi xử lý phím trước; sau đó đến view nội dung chính. Cuối cùng, phím mũi tên trái/phải có thể phát `AppViewEvent` để yêu cầu chuyển lựa chọn. Hotkey được xử lý theo thứ tự main, menu và status.

Điều này giúp tách điều hướng cấp ứng dụng khỏi điều hướng nội bộ của từng view. Ví dụ, phím lên/xuống có thể di chuyển lựa chọn trong menu đang focus, còn trái/phải có thể chuyển mục menu hoặc vùng lựa chọn ở cấp `AppView`.

Nếu một view cần mở hộp thoại, có thể dùng `setModal(dialogView)`. Khi đóng hộp thoại, gọi `setModal(null)`. Modal view có thể nhận tương tác ưu tiên trong khi đang hiển thị; hãy trả focus về view phù hợp sau khi đóng modal.

## 8. Nhận sự kiện chuột qua EventLoop

`EventLoop.mouseEvents()` trả về `Flux<MouseEvent>`. `MouseEvent` chứa:

- `x()` và `y()`: tọa độ sự kiện.
- `mouse()`: dữ liệu chuột gốc từ `org.jline.terminal.MouseEvent`.
- `hasType()`, `hasButton()` và `hasModifier()` để kiểm tra nhóm thông tin.
- `has(mask)` để kiểm tra một bit mask cụ thể.

Các loại sự kiện gồm `Pressed`, `Released`, `Moved`, `Dragged` và `Wheel`. Các nút thường gặp gồm `Button1`, `Button2`, `Button3`, `WheelUp` và `WheelDown`.

Ví dụ quan sát click chuột trái:

~~~java
import reactor.core.Disposable;

import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.event.EventLoop;
import org.springframework.shell.component.view.event.MouseEvent;

private void observeMouse(TerminalUI ui) {
    EventLoop eventLoop = ui.getEventLoop();

    Disposable mouseSubscription = eventLoop.mouseEvents()
            .subscribe(event -> {
                if (event.has(MouseEvent.Type.Pressed)
                        && event.has(MouseEvent.Button.Button1)) {
                    logger.debug("Click tại x={}, y={}", event.x(), event.y());
                }
            });

    eventLoop.onDestroy(mouseSubscription);
}
~~~

Ví dụ chỉ ghi nhận click. Để chọn item, ứng dụng cần xác định tọa độ thuộc vùng view nào, chuyển tọa độ terminal sang tọa độ cục bộ của view và cập nhật trạng thái lựa chọn. Không nên giả định mọi terminal trả tọa độ hoặc sự kiện chuột theo cùng cách nếu chưa kiểm thử trên môi trường triển khai.

## 9. Đăng ký mouse binding ngay trong view

Nếu click chỉ có ý nghĩa trong một view, có thể dùng `registerMouseBinding(...)` trong `AbstractView`. Tham số đầu tiên là mask kết hợp loại sự kiện và nút chuột; tham số thứ hai nhận `MouseEvent`.

~~~java
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.event.MouseEvent;

public class SelectableListView extends BoxView {

    @Override
    protected void initInternal() {
        super.initInternal();

        registerMouseBinding(
                MouseEvent.Type.Pressed | MouseEvent.Button.Button1,
                event -> {
                    int x = event.x();
                    int y = event.y();
                    selectItemAt(x, y);
                });
    }

    private void selectItemAt(int x, int y) {
        // Ánh xạ tọa độ vào hàng của danh sách rồi cập nhật selection.
    }
}
~~~

Binding này gắn click trái với hành động chọn item. Khi xử lý wheel, có thể đăng ký mask tương ứng với `MouseEvent.Type.Wheel` và `MouseEvent.Button.WheelUp` hoặc `WheelDown`. Hãy chỉ xử lý những thao tác mà view thực sự hỗ trợ.

## 10. MouseHandler: consumed, focus và capture

Với xử lý chuột nâng cao, `View.getMouseHandler()` trả về một `MouseHandler`. Handler nhận `MouseHandlerArgs` và trả `MouseHandlerResult`, trong đó có ba quyết định quan trọng:

- `consumed`: sự kiện đã được view xử lý hay chưa.
- `focus`: view muốn nhận focus sau sự kiện.
- `capture`: view muốn tiếp tục nhận các sự kiện liên quan, ví dụ trong lúc kéo thả.

`MouseHandler.resultOf(event, consumed, focus, capture)` tạo kết quả tương ứng. Có thể ghép nhiều handler bằng `thenIfConsumed(...)`, `thenIfNotConsumed(...)` hoặc `thenConditionally(...)`.

Ví dụ về luồng xử lý:

1. Người dùng nhấn chuột lên một view.
2. View kiểm tra tọa độ và xác định sự kiện có nằm trong vùng tương tác hay không.
3. Nếu xử lý, handler trả `consumed=true`.
4. Nếu click cần chuyển focus, trả view đó trong trường `focus`.
5. Nếu thao tác kéo cần tiếp tục nhận sự kiện khi con trỏ đi ra ngoài vùng ban đầu, dùng `capture` phù hợp.

Không đánh dấu mọi sự kiện là consumed. Nếu view không xử lý click, hãy để sự kiện tiếp tục đến handler khác hoặc view cha.

## 11. Chuột phụ thuộc vào terminal và môi trường chạy

Spring Shell có API để nhận và xử lý `MouseEvent`, nhưng việc có sự kiện thực tế hay không phụ thuộc terminal emulator, giao thức kết nối và mouse reporting. Một số môi trường chỉ truyền phím; một số môi trường hỗ trợ click nhưng không hỗ trợ đầy đủ drag hoặc wheel.

Các tình huống cần kiểm tra:

- Terminal emulator có gửi mouse reporting hay không.
- Ứng dụng có đang chạy trong SSH, tmux, screen hoặc terminal tích hợp IDE hay không.
- Chuột trái, chuột phải, wheel và drag có được chuyển thành sự kiện như mong đợi không.
- Tọa độ click có khớp với layout sau khi terminal resize không.
- Khi mouse event không đến, người dùng có thể hoàn tất thao tác bằng bàn phím không.

Thiết kế giao diện theo hướng keyboard-first: mọi hành động quan trọng đều phải có đường thao tác bằng bàn phím. Chuột là phương thức bổ sung khi môi trường hỗ trợ; không dùng click làm cách duy nhất để chọn, xác nhận hoặc đóng một màn hình.

## 12. Redraw và cập nhật state trong event loop

`TerminalUI.redraw()` gửi yêu cầu vẽ lại toàn màn hình vào event loop. Đây là cách yêu cầu UI cập nhật sau khi state thay đổi. Thông thường, view bindings được dispatch vào event loop để giữ thứ tự cập nhật và render.

Ví dụ sau khi nhận dữ liệu từ một tác vụ nền:

~~~java
viewModel.setStatus("Đã đồng bộ xong");
terminalUI.redraw();
~~~

Ví dụ trên giả định state được cập nhật trong luồng điều khiển an toàn của UI. Nếu dữ liệu đến từ worker thread, hãy gửi một Spring `Message<?>` có kiểu vào `EventLoop.dispatch(...)` và để processor xử lý message đó trong event loop trước khi cập nhật view model. API `dispatch(...)` nhận message hoặc `Publisher<Message<?>>`, không nhận trực tiếp `Runnable`. Không cập nhật trực tiếp state của view từ nhiều thread nếu view không được thiết kế thread-safe.

Nếu cần gửi sự kiện tùy chỉnh, `EventLoop.dispatch(Message<?>)` có thể đưa message vào loop. Với luồng Reactor, có thể dispatch một `Publisher` như `Mono` hoặc `Flux`. Đăng ký listener theo vòng đời view và dispose subscription khi view hoặc event loop kết thúc.

## 13. Những lỗi thường gặp

**Phím không đến đúng view:** kiểm tra view nào đang focus bằng `hasFocus()` và nơi ứng dụng gọi `setFocus(...)`. Nếu dùng `AppView`, kiểm tra menu có đang giữ focus hay không.

**Hotkey không chạy:** kiểm tra binding có được đăng ký trong `initInternal()` và có bị một handler ưu tiên khác xử lý trước hay không. Tránh dùng cùng một phím cho hotkey toàn cục và hành động nhập liệu thông thường.

**Một lần nhấn phím kích hoạt hai lần:** kiểm tra ứng dụng có xử lý cùng sự kiện trong cả `keyEvents()` và `registerKeyBinding(...)` hay không.

**Click không có tác dụng:** xác nhận terminal gửi mouse event, view có đăng ký mouse handler và tọa độ click nằm trong vùng view. Nếu môi trường không hỗ trợ chuột, cung cấp phím điều hướng thay thế.

**Click chọn sai hàng sau resize:** tính lại layout và vùng hit-test từ rectangle hiện tại của view; không giữ tọa độ cũ sau khi terminal thay đổi kích thước.

**Subscription tiếp tục chạy sau khi UI đóng:** lưu `Disposable` trả về từ `subscribe()` và đăng ký với `eventLoop.onDestroy(...)` hoặc lifecycle của view.

**UI không redraw sau khi cập nhật dữ liệu:** thay đổi state qua event loop hoặc gọi `TerminalUI.redraw()` sau khi state đã được cập nhật đúng thread.

## 14. Kiểm thử phím, focus và chuột

Nên kiểm thử ở cả mức logic view và mức terminal thật:

1. Phím mũi tên thay đổi selection đúng một bước.
2. Enter kích hoạt item đang được chọn.
3. Hotkey được xử lý trước key binding thông thường theo thiết kế.
4. Chuyển focus đến input view khiến phím nhập được chuyển đến đúng view.
5. `AppView` xử lý phím theo thứ tự menu, main và điều hướng cấp ứng dụng.
6. Click trái tại tọa độ một hàng chọn đúng item.
7. Wheel cuộn đúng hướng khi terminal gửi wheel event.
8. Drag tiếp tục được nhận nếu view yêu cầu mouse capture.
9. Terminal resize làm layout và hit-test được tính lại.
10. Event subscriptions được dispose khi event loop kết thúc.
11. Các hành động quan trọng vẫn thao tác được chỉ bằng bàn phím.

Kiểm thử tích hợp nên chạy trong pseudo-terminal hoặc terminal emulator thật để xác nhận JLine có nhận được mouse reporting và phím đặc biệt. Unit test `KeyEvent` hoặc `MouseEvent` chỉ xác nhận logic xử lý dữ liệu sự kiện; chúng không chứng minh terminal emulator sẽ gửi sự kiện đó trong môi trường triển khai.

## 15. Quy trình triển khai tương tác

1. Tạo `TerminalUI` và cấu hình root view.
2. Chọn view nhận focus ban đầu bằng `setFocus(...)`.
3. Dùng default bindings của built-in view nếu đã đáp ứng nhu cầu.
4. Đăng ký key binding và hotkey trong `AbstractView.initInternal()` khi cần hành vi riêng.
5. Dùng `EventLoop.keyEvents()` cho xử lý phím toàn cục hoặc quan sát sự kiện.
6. Dùng `EventLoop.mouseEvents()` hoặc `registerMouseBinding(...)` khi terminal hỗ trợ chuột.
7. Chỉ định rõ view nào nhận focus và view nào capture thao tác chuột.
8. Dispose subscription theo lifecycle của event loop hoặc view.
9. Kiểm thử trên terminal mục tiêu, cả khi có và không có mouse support.
10. Bảo đảm mọi thao tác quan trọng vẫn dùng được bằng bàn phím.

## Kết luận

Trong Spring Shell 3.x, `TerminalUI` phối hợp cây view và `EventLoop` để nhận sự kiện bàn phím, chuột và hệ thống. `keyEvents()` và `mouseEvents()` cung cấp các luồng sự kiện có kiểu; `AbstractView` hỗ trợ đăng ký key binding, hotkey và mouse binding; `setFocus(...)` quyết định view nhận bàn phím. `MouseHandler` còn có thể đánh dấu sự kiện đã xử lý, yêu cầu focus hoặc capture cho thao tác kéo. Chuột chỉ hoạt động khi terminal và đường truyền hỗ trợ mouse reporting, vì vậy hãy thiết kế keyboard-first và kiểm thử trên môi trường chạy thực tế.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Terminal UI Introduction](https://docs.spring.io/spring-shell/reference/3.4/tui/intro/index.html)
- [Spring Shell 3.4 – EventLoop](https://docs.spring.io/spring-shell/reference/3.4/tui/events/eventloop.html)
- [Spring Shell 3.4 – Key Handling](https://docs.spring.io/spring-shell/reference/3.4/tui/events/key.html)
- [Spring Shell 3.4 – Mouse Handling](https://docs.spring.io/spring-shell/reference/3.4/tui/events/mouse.html)
- [Spring Shell 3.4 – AppView](https://docs.spring.io/spring-shell/reference/3.4/tui/views/app.html)
- [Spring Shell 3.4 – View Development and Bindings](https://docs.spring.io/spring-shell/reference/3.4/appendices/tui/viewdev.html)
- [Spring Shell 3.4 API – TerminalUI](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUI.html)
- [Spring Shell 3.4 API – TerminalUIBuilder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUIBuilder.html)
- [Spring Shell 3.4 API – EventLoop](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/EventLoop.html)
- [Spring Shell 3.4 API – KeyEvent](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/KeyEvent.html)
- [Spring Shell 3.4 API – MouseEvent](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/MouseEvent.html)
- [Spring Shell 3.4 API – AbstractView](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/AbstractView.html)
- [Spring Shell 3.4 API – AppView](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/AppView.html)
- [Spring Shell 3.4 API – ViewService](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ViewService.html)
- [Spring Shell 3.4 API – MouseHandler](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/MouseHandler.html)
- [Spring Shell 3.4 API – MouseHandlerResult](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/MouseHandler.MouseHandlerResult.html)
