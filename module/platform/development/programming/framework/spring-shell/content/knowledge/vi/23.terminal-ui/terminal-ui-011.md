# Đóng giao diện, khôi phục terminal và giải phóng tài nguyên

Một màn hình Terminal UI có thể chạy đúng khi người dùng hoàn thành tác vụ nhưng vẫn để lại terminal ở trạng thái bất thường nếu luồng kết thúc không được xử lý đầy đủ. Biểu hiện thường gặp là con trỏ biến mất, ký tự nhập không hiển thị, phím Enter không xuống dòng như bình thường hoặc tiến trình vẫn giữ thread sau khi giao diện đã đóng.

Trong Spring Shell 3.3, cần quản lý riêng vòng lặp giao diện, event loop, subscription, ViewComponentExecutor và đối tượng JLine Terminal. Mỗi thành phần có cách kết thúc khác nhau. TerminalUI điều phối giao diện và vòng lặp sự kiện; Terminal là tài nguyên cấp thấp hơn; Spring ApplicationContext quản lý vòng đời của các bean được cấu hình tự động.

Bài học sử dụng Spring Shell 3.3.x và JLine 3. Mục tiêu là kết thúc giao diện có chủ đích, khôi phục thuộc tính terminal khi ứng dụng tự thay đổi chúng và giải phóng tài nguyên đúng theo quyền sở hữu.

## 1. Phân biệt các vòng đời

Không nên xem một lệnh “đóng UI” là thao tác đóng tất cả tài nguyên. Spring Shell có nhiều đối tượng cùng tham gia vào một màn hình:

| Thành phần | Trách nhiệm | Cách kết thúc |
|---|---|---|
| `TerminalUI` | Điều phối view, event loop, phím và chuột | Gửi thông điệp interrupt để thoát `run()` |
| `EventLoop` | Nhận và phân phối sự kiện | Kết thúc vòng lặp; dispose các subscription đã đăng ký với `onDestroy(...)` |
| `ViewComponent` | Chạy một view trong vùng giao diện | Gọi `exit()` hoặc chờ/cancel lần chạy bất đồng bộ |
| `ViewComponentExecutor` | Chạy view bất đồng bộ | Gọi `close()` khi ứng dụng sở hữu executor |
| JLine `Terminal` | Quản lý input, output và trạng thái terminal của hệ điều hành | Gọi `close()` khi chủ sở hữu kết thúc terminal |
| Spring `ApplicationContext` | Quản lý bean và tài nguyên của ứng dụng | Đóng context khi ứng dụng kết thúc |

Các lớp này không thay thế nhau. Ví dụ, dừng `TerminalUI.run()` không có nghĩa là terminal đã được đóng. Ngược lại, đóng terminal khi event loop vẫn đang đọc input có thể làm giao diện lỗi hoặc khiến shell chính không thể tiếp tục sử dụng terminal.

Hãy xác định ai tạo và sở hữu mỗi đối tượng trước khi quyết định nơi gọi `close()`.

## 2. TerminalUI chạy theo kiểu blocking

`TerminalUI` là thành phần điều phối terminal, event loop, key/mouse event và cây view. Có thể tạo nó bằng `TerminalUIBuilder`:

```java
TerminalUI ui = terminalUIBuilder.build();

BoxView root = new BoxView();
root.setTitle("Dashboard");

ui.configure(root);
ui.setRoot(root, true);
ui.run();
```

`ui.run()` là thao tác blocking. Phương thức chỉ trả về khi vòng lặp giao diện kết thúc. Vì vậy, command gọi `run()` sẽ giữ luồng hiện tại cho tới khi có tín hiệu kết thúc phù hợp.

Trong API Spring Shell 3.3, `TerminalUI` không triển khai `AutoCloseable` và không có phương thức `close()`. Không gọi `ui.close()` hoặc tự giả định rằng đóng đối tượng `TerminalUI` sẽ giải phóng terminal. Hãy kết thúc event loop theo cơ chế sự kiện, sau đó xử lý các tài nguyên mà ứng dụng sở hữu.

## 3. Yêu cầu TerminalUI thoát bằng interrupt message

`EventLoop` nhận các message thông qua `dispatch(...)`. Spring Shell cung cấp `ShellMessageBuilder.ofInterrupt()` để tạo message yêu cầu vòng lặp giao diện dừng.

Ví dụ, đăng ký Ctrl+Q làm phím thoát:

```java
import org.springframework.shell.component.message.ShellMessageBuilder;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.event.EventLoop;
import org.springframework.shell.component.view.event.KeyEvent;
import org.springframework.stereotype.Component;

import reactor.core.Disposable;

@Component
public class DashboardCommand {

    private final TerminalUIBuilder terminalUIBuilder;

    public DashboardCommand(TerminalUIBuilder terminalUIBuilder) {
        this.terminalUIBuilder = terminalUIBuilder;
    }

    public void show() {
        TerminalUI ui = terminalUIBuilder.build();

        BoxView root = new BoxView();
        root.setTitle("Dashboard");
        ui.configure(root);
        ui.setRoot(root, true);

        EventLoop eventLoop = ui.getEventLoop();

        Disposable quitOnCtrlQ = eventLoop.keyEvents()
            .filter(event ->
                event.hasCtrl()
                    && event.getPlainKey() == KeyEvent.Key.q
            )
            .subscribe(event ->
                eventLoop.dispatch(ShellMessageBuilder.ofInterrupt())
            );

        eventLoop.onDestroy(quitOnCtrlQ);

        try {
            ui.run();
        }
        finally {
            quitOnCtrlQ.dispose();
        }
    }
}
```

Khi người dùng nhấn Ctrl+Q:

1. `keyEvents()` phát ra `KeyEvent`.
2. Bộ lọc nhận tổ hợp Ctrl+Q.
3. Callback gửi `ofInterrupt()` vào event loop.
4. `ui.run()` kết thúc khi vòng lặp thoát.

`eventLoop.onDestroy(quitOnCtrlQ)` đăng ký subscription để event loop tự dispose khi nó kết thúc. `finally` vẫn dispose subscription nếu `run()` thoát do exception hoặc một đường điều khiển khác. Gọi `dispose()` lần nữa là an toàn với `Disposable`.

Không dùng `Thread.stop()` để kết thúc UI. Cắt ngang thread có thể bỏ qua phần khôi phục terminal, làm hỏng trạng thái dùng chung hoặc để lại tài nguyên chưa được giải phóng.

## 4. Gắn subscription và tác vụ nền với event loop

Một view có thể đăng ký nhiều nguồn sự kiện: phím, chuột, resize, timer hoặc luồng dữ liệu từ service. Nếu subscription tiếp tục sống sau khi view đóng, callback vẫn có thể cập nhật giao diện đã kết thúc hoặc giữ tham chiếu tới object không còn cần thiết.

`EventLoop.onDestroy(Disposable)` cho phép gắn một Reactor `Disposable` vào vòng đời event loop:

```java
Disposable updates = inventoryService.watchChanges()
    .subscribe(
        update -> eventLoop.dispatch(
            ShellMessageBuilder.ofRedraw()
        ),
        error -> log.warn("Không thể nhận cập nhật inventory", error)
    );

eventLoop.onDestroy(updates);
```

Khi event loop kết thúc, subscription được dispose. Nếu một tác vụ có nhiều subscription, có thể gom chúng vào `Disposables.composite()` rồi đăng ký composite với `onDestroy(...)`.

Ví dụ:

```java
import reactor.core.Disposable;
import reactor.core.Disposables;

Disposable.Composite subscriptions = Disposables.composite();

subscriptions.add(eventLoop.keyEvents().subscribe(this::handleKey));
subscriptions.add(eventLoop.mouseEvents().subscribe(this::handleMouse));
subscriptions.add(inventoryService.watchChanges()
    .subscribe(this::updateModel));

eventLoop.onDestroy(subscriptions);
```

Chỉ đăng ký những tác vụ thật sự thuộc về vòng đời của view. Tác vụ nền cần tiếp tục chạy sau khi người dùng đóng màn hình phải được quản lý bởi một service hoặc lifecycle khác, không gắn nhầm vào event loop.

## 5. Khôi phục thuộc tính terminal sau khi thay đổi

Terminal có các thuộc tính điều khiển cách hệ điều hành xử lý input, chẳng hạn:

- `ECHO`: có hiển thị ký tự người dùng nhập hay không.
- `ICANON`: xử lý input theo dòng hay theo từng ký tự.
- `ISIG`: có chuyển các ký tự điều khiển như Ctrl+C thành signal hay không.
- `VMIN` và `VTIME`: điều kiện trả dữ liệu khi đọc ở chế độ non-canonical.

Nếu ứng dụng tự chuyển terminal sang raw mode hoặc thay đổi thuộc tính input, cần lưu trạng thái ban đầu và khôi phục trong `finally`.

JLine cung cấp `enterRawMode()`. Phương thức trả về `Attributes` ban đầu để ứng dụng khôi phục sau đó:

```java
import org.jline.terminal.Attributes;
import org.jline.terminal.Terminal;

public void runRawOperation(Terminal terminal) throws Exception {
    Attributes originalAttributes = terminal.enterRawMode();

    try {
        terminal.writer().println("Đang ở raw mode. Nhấn một phím để tiếp tục.");
        terminal.writer().flush();

        int key = terminal.reader().read();
        terminal.writer().printf("Mã phím: %d%n", key);
        terminal.writer().flush();
    }
    finally {
        terminal.setAttributes(originalAttributes);
        terminal.writer().flush();
    }
}
```

Khôi phục trong `finally` để vẫn thực hiện khi thao tác đọc input hoặc xử lý nghiệp vụ ném exception.

Không tự chuyển terminal sang raw mode nếu JLine hoặc thành phần Spring Shell đang sử dụng terminal đã quản lý chế độ input đó. Chỉ thay đổi thuộc tính khi ứng dụng thực sự cần quyền điều khiển thấp hơn và hiểu tác động của từng flag.

## 6. Không đóng terminal dùng chung của Spring Shell

Trong ứng dụng Spring Shell 3.3 có auto-configuration JLine, bean `org.jline.terminal.Terminal` được tạo bởi `JLineShellAutoConfiguration`. Bean này khai báo `destroyMethod="close"`, nên Spring sẽ gọi `close()` khi ApplicationContext được đóng.

Ví dụ command nhận terminal qua constructor:

```java
import org.jline.terminal.Terminal;
import org.springframework.stereotype.Component;

@Component
public class TerminalStatus {

    private final Terminal terminal;

    public TerminalStatus(Terminal terminal) {
        this.terminal = terminal;
    }

    public void printStatus() {
        terminal.writer().println("Terminal đang hoạt động.");
        terminal.writer().flush();
    }
}
```

Command chỉ đang mượn terminal dùng chung. Khi màn hình riêng kết thúc nhưng shell vẫn tiếp tục hoạt động, không gọi `terminal.close()` trong `finally`. Nếu đóng terminal ở đây, prompt, command tiếp theo và các thành phần khác của shell có thể không còn input/output hợp lệ.

Trong trường hợp này, trách nhiệm được chia như sau:

- Command kết thúc vòng lặp `TerminalUI`.
- Các subscription của view được dispose.
- Các thuộc tính terminal do command tự thay đổi được khôi phục.
- Spring tiếp tục giữ terminal để shell dùng cho command tiếp theo.
- Khi ứng dụng đóng ApplicationContext, Spring gọi `Terminal.close()` theo cấu hình bean.

Đóng một view không đồng nghĩa đóng shell.

## 7. Đóng terminal do ứng dụng tự tạo

Nếu ứng dụng tự tạo terminal bằng `TerminalBuilder`, ứng dụng sở hữu tài nguyên đó và phải đóng nó khi hoàn tất.

Có thể dùng try-with-resources:

```java
import org.jline.terminal.Terminal;
import org.jline.terminal.TerminalBuilder;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.BoxView;

public void runStandaloneUi() throws Exception {
    try (Terminal terminal = TerminalBuilder.builder().build()) {
        TerminalUI ui = new TerminalUIBuilder(terminal).build();

        BoxView root = new BoxView();
        root.setTitle("Standalone UI");
        ui.configure(root);
        ui.setRoot(root, true);

        // Gắn handler gửi ShellMessageBuilder.ofInterrupt()
        // vào EventLoop trước khi chạy UI.
        ui.run();
    }
}
```

Khi khối `try` kết thúc, `Terminal.close()` được gọi kể cả khi `ui.run()` ném exception. Terminal cần được đóng sau khi vòng lặp giao diện đã kết thúc, vì UI còn sử dụng terminal để đọc input và ghi output.

Không tạo một system terminal mới trong mỗi lần mở màn hình nếu ứng dụng đã có terminal dùng chung từ Spring. JLine làm việc với terminal của tiến trình; nhiều đối tượng cùng điều khiển một terminal có thể xung đột về input, cursor và trạng thái.

## 8. Dùng ViewComponent cho giao diện không toàn màn hình

`ViewComponent` chạy một view trong chế độ không chiếm toàn bộ màn hình. Có thể xây dựng nó qua `ViewComponentBuilder` được Spring Shell auto-configure:

```java
import org.springframework.shell.component.ViewComponent;
import org.springframework.shell.component.ViewComponentBuilder;
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.stereotype.Component;

@Component
public class StatusPanel {

    private final ViewComponentBuilder viewComponentBuilder;

    public StatusPanel(ViewComponentBuilder viewComponentBuilder) {
        this.viewComponentBuilder = viewComponentBuilder;
    }

    public void show() {
        BoxView view = new BoxView();
        view.setTitle("Trạng thái");

        ViewComponent component = viewComponentBuilder.build(view);
        component.runBlocking();
    }
}
```

`runBlocking()` chạy vòng lặp của component trên luồng hiện tại. Khi muốn kết thúc component, gọi `component.exit()` từ hành động của view hoặc logic điều khiển phù hợp. Phương thức này yêu cầu vòng lặp component thoát; nó không đóng terminal dùng chung.

Với cách chạy bất đồng bộ:

```java
ViewComponent component = viewComponentBuilder.build(view);
ViewComponent.ViewComponentRun run = component.runAsync();

// Có thể tiếp tục công việc khác trong lúc view đang hiển thị.

run.await();
```

`ViewComponentRun` cung cấp:

- `await()`: chờ component kết thúc.
- `cancel()`: hủy lần chạy bất đồng bộ.
- `isDone()`: kiểm tra lần chạy đã hoàn tất hay chưa.

Ưu tiên `component.exit()` cho đường thoát bình thường do người dùng chọn. Dùng `cancel()` khi cần hủy một lần chạy bất đồng bộ. Hãy chờ hoặc xác nhận trạng thái kết thúc trước khi đóng executor hay tài nguyên mà view đang sử dụng.

## 9. Giải phóng ViewComponentExecutor

`ViewComponentExecutor` chạy view trên một thread để command không phải block trong lúc component hoạt động. Class này triển khai `AutoCloseable` và có `close()` để giải phóng executor.

Nếu ứng dụng tự tạo executor, hãy đóng nó:

```java
import org.jline.terminal.Terminal;
import org.springframework.shell.component.ViewComponent;
import org.springframework.shell.component.ViewComponentExecutor;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.control.View;

public void runOwnedComponent(
        TerminalUI terminalUI,
        Terminal terminal,
        View view) throws Exception {

    try (ViewComponentExecutor executor = new ViewComponentExecutor()) {
        ViewComponent component = new ViewComponent(
            terminalUI, terminal, executor, view
        );

        ViewComponent.ViewComponentRun run = component.runAsync();

        try {
            run.await();
        }
        finally {
            if (!run.isDone()) {
                run.cancel();
            }
        }
    }
}
```

Ví dụ này chỉ áp dụng khi executor được tạo và sở hữu trong cùng phạm vi. Khi dùng `ViewComponentBuilder` được inject từ Spring, builder sử dụng `ViewComponentExecutor` do `TerminalUIAutoConfiguration` cung cấp. Hãy để ApplicationContext quản lý bean đó; không tự đóng executor dùng chung sau mỗi command.

`ViewComponentExecutor.stop()` có thể dừng component đã được executor khởi chạy. `close()` đóng executor và nên được gọi sau khi các lần chạy đã hoàn tất hoặc đã được hủy.

## 10. Khôi phục màn hình và output sau khi UI kết thúc

Sau khi UI toàn màn hình dừng, shell thường cần tiếp tục hiển thị prompt. Một số nguyên tắc giúp chuyển lại giao diện gọn gàng:

- Kết thúc event loop trước khi command ghi thông báo cuối.
- Khôi phục các thuộc tính terminal mà ứng dụng đã tự thay đổi.
- Ghi newline nếu giao diện vừa kết thúc ở giữa dòng.
- Flush writer để output cuối được đẩy ra terminal.
- Không xóa màn hình hoặc phát chuỗi điều khiển tùy tiện nếu shell chính sắp hiển thị prompt.

Ví dụ phần kết thúc command:

```java
Attributes originalAttributes = terminal.getAttributes();

try {
    ui.run();
}
finally {
    quitSubscription.dispose();

    // Chỉ khôi phục trạng thái mà command này đã thay đổi.
    terminal.setAttributes(originalAttributes);

    terminal.writer().println();
    terminal.writer().flush();
}
```

Không dùng đoạn khôi phục `setAttributes(...)` nếu command chưa từng thay đổi thuộc tính terminal hoặc nếu một thành phần khác đang sở hữu thay đổi đó. Chỉ khôi phục trạng thái do chính phạm vi code của bạn tạo ra.

Nếu view sử dụng màu, cursor hoặc chế độ hiển thị đặc biệt, hãy kiểm tra kết quả trên terminal emulator mục tiêu. Không phải terminal nào cũng hỗ trợ cùng bộ capability; cung cấp cách hiển thị dự phòng khi cần.

## 11. Đóng giao diện khi có exception hoặc signal

Luồng thoát bình thường không phải đường duy nhất. `ui.run()` có thể kết thúc do lỗi khi xử lý view, lỗi đọc terminal hoặc tín hiệu ngắt.

Hãy giữ các thao tác dọn dẹp trong `finally`:

- Dispose subscription và timer của view.
- Khôi phục thuộc tính terminal đã thay đổi.
- Dừng component đang chạy bất đồng bộ.
- Ghi output cuối và flush nếu terminal vẫn sử dụng được.
- Để Spring đóng bean terminal khi ApplicationContext kết thúc.

Không nuốt exception chỉ để tránh lỗi hiển thị. Nếu cần thông báo, hãy log exception ở tầng phù hợp rồi để cơ chế xử lý lỗi của command tiếp tục hoạt động.

Với Ctrl+C hoặc signal hệ điều hành, cần xác định rõ ứng dụng muốn hủy view, kết thúc shell hay dừng toàn bộ tiến trình. Không nên tự thay handler của JLine thành bỏ qua signal. Nếu đăng ký handler riêng, hãy giữ và khôi phục handler trước đó theo API JLine mà ứng dụng đang dùng.

## 12. Phân biệt đóng view và đóng ApplicationContext

Spring Shell quản lý tài nguyên theo vòng đời ApplicationContext. Lệnh `quit` hoặc `exit` mặc định yêu cầu shell kết thúc và đóng Spring application context. Khi context đóng, Spring thực hiện các callback destroy của bean, trong đó có JLine `Terminal` được cấu hình với `destroyMethod="close"`.

Nếu chỉ muốn đóng một dashboard rồi quay về prompt, đừng đóng context. Hãy kết thúc `TerminalUI` hoặc `ViewComponent`, dispose subscription và trả quyền điều khiển về command handler.

Nếu ứng dụng cần kết thúc hoàn toàn:

1. Yêu cầu UI loop dừng.
2. Chờ component bất đồng bộ kết thúc hoặc hủy nó.
3. Dispose subscription và tác vụ gắn với view.
4. Trả quyền điều khiển về shell.
5. Để cơ chế quit/exit đóng ApplicationContext.
6. Spring đóng các bean có lifecycle cleanup, bao gồm terminal dùng chung.

Không gọi `System.exit()` để thay thế quy trình này. `System.exit()` có thể kết thúc JVM trước khi Spring và các tài nguyên khác hoàn tất cleanup.

## 13. Kiểm thử vòng đời và khôi phục terminal

Một bài kiểm thử chỉ xác nhận nội dung UI xuất hiện là chưa đủ. Cần kiểm tra cả đường thoát và trạng thái sau khi đóng.

| Trường hợp | Điều cần xác minh |
|---|---|
| Người dùng nhấn Ctrl+Q | `TerminalUI.run()` kết thúc |
| View phát sinh exception | Subscription được dispose và thuộc tính terminal được khôi phục |
| Component chạy blocking | `exit()` kết thúc vòng lặp |
| Component chạy async | `await()` hoàn tất hoặc `cancel()` được gọi |
| View có subscription nền | Subscription được dispose khi event loop kết thúc |
| Command kết thúc nhưng shell còn chạy | Terminal dùng chung vẫn hoạt động |
| ApplicationContext đóng | JLine terminal bean được đóng |
| Terminal do ứng dụng tạo | `close()` được gọi khi khối sở hữu kết thúc |

Với kiểm thử thuộc tính terminal, lưu lại trạng thái trước khi thay đổi:

```java
Attributes before = terminal.getAttributes();

try {
    // Chạy thao tác hoặc UI cần thay đổi terminal.
}
finally {
    terminal.setAttributes(before);
}

Attributes after = terminal.getAttributes();
// So sánh các flag quan trọng giữa before và after.
```

Với kiểm thử tương tác thực tế, dùng pseudo-terminal (PTY) để gửi Ctrl+Q, Ctrl+C và kiểm tra prompt sau khi giao diện thoát. Terminal giả lập dựa trên stream có thể kiểm tra logic event loop và output, nhưng không chứng minh terminal hệ điều hành đã khôi phục đúng thuộc tính.

Cũng nên kiểm thử đường exception: cho view hoặc callback ném lỗi có kiểm soát rồi xác minh `finally` vẫn dispose subscription và khôi phục trạng thái.

## 14. Các lỗi thường gặp

**Gọi `ui.close()` sau `ui.run()`.** `TerminalUI` của Spring Shell 3.3 không có API `close()`. Kết thúc loop bằng interrupt message và dọn dẹp các tài nguyên liên quan.

**Đóng terminal trong mỗi command.** Terminal do Spring quản lý được shell dùng chung. Đóng nó khi command riêng kết thúc sẽ làm hỏng các command tiếp theo.

**Không dispose subscription.** Reactive stream có thể giữ thread, callback và tham chiếu tới view cũ. Dùng `EventLoop.onDestroy(...)` hoặc `finally`.

**Chỉ dọn dẹp khi người dùng thoát bình thường.** Exception có thể bỏ qua đoạn code phía sau `run()`. Đặt cleanup trong `finally`.

**Thay đổi raw mode mà không khôi phục.** `ECHO` hoặc `ICANON` có thể giữ trạng thái sai sau khi view đóng. Lưu `Attributes` ban đầu và gọi `setAttributes(...)` trong `finally`.

**Đóng ViewComponentExecutor quá sớm.** Executor có thể còn task đang chạy. Hãy kết thúc hoặc cancel component rồi mới đóng executor.

**Dùng `cancel()` cho mọi đường thoát.** `cancel()` là hủy lần chạy async. Với lựa chọn thoát bình thường, dùng `ViewComponent.exit()` để yêu cầu vòng lặp kết thúc.

**Gọi `System.exit()` từ view.** JVM có thể dừng trước khi Spring đóng context và tài nguyên. Hãy kết thúc UI, quay lại shell rồi dùng luồng quit/exit chuẩn.

**Tạo nhiều system terminal.** Các terminal cùng điều khiển một phiên terminal của JVM có thể xung đột. Ưu tiên bean terminal dùng chung do Spring Shell cung cấp.

**Bỏ qua terminal không hỗ trợ capability.** Màu, cursor và chế độ màn hình có thể khác nhau giữa terminal emulator. Kiểm tra capability và có fallback.

## 15. Checklist trước khi phát hành Terminal UI

- [ ] Xác định rõ terminal được Spring quản lý hay do ứng dụng tự tạo.
- [ ] Tạo UI từ `TerminalUIBuilder` hoặc `ViewComponentBuilder` phù hợp.
- [ ] Có phím hoặc hành động yêu cầu kết thúc vòng lặp.
- [ ] Dùng `ShellMessageBuilder.ofInterrupt()` để thoát `TerminalUI.run()`.
- [ ] Gắn subscription vào `EventLoop.onDestroy(...)`.
- [ ] Dispose subscription trong `finally` để bao phủ cả exception.
- [ ] Gọi `ViewComponent.exit()` cho đường thoát bình thường.
- [ ] Với async component, chờ hoặc cancel lần chạy trước khi giải phóng executor.
- [ ] Lưu và khôi phục `Attributes` nếu code tự thay đổi terminal mode.
- [ ] Không đóng terminal dùng chung từ command riêng.
- [ ] Đóng terminal do ứng dụng tạo bằng try-with-resources.
- [ ] Để Spring đóng bean terminal khi ApplicationContext kết thúc.
- [ ] Flush output sau thông báo cuối và khôi phục prompt.
- [ ] Kiểm thử đường thoát bình thường, exception và signal.
- [ ] Kiểm thử trên PTY hoặc terminal emulator của hệ điều hành mục tiêu.

## 16. Tài liệu tham khảo chính thức

- [Spring Shell 3.3 API — TerminalUI](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUI.html): `run()`, `getEventLoop()`, `configure(...)` và `setRoot(...)`.
- [Spring Shell 3.3 API — TerminalUIBuilder](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUIBuilder.html): tạo và cấu hình `TerminalUI`.
- [Spring Shell 3.3 API — EventLoop](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/event/EventLoop.html): event stream và `onDestroy(Disposable)`.
- [Spring Shell 3.3 API — ShellMessageBuilder](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/message/ShellMessageBuilder.html): tạo interrupt message bằng `ofInterrupt()`.
- [Spring Shell 3.3 API — JLineShellAutoConfiguration](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/JLineShellAutoConfiguration.html): bean `Terminal` với `destroyMethod="close"`.
- [Spring Shell 3.3 API — TerminalUIAutoConfiguration](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/TerminalUIAutoConfiguration.html): các bean builder và executor cho Terminal UI.
- [Spring Shell 3.3 API — ViewComponent](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponent.html), [ViewComponentExecutor](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponentExecutor.html) và [ViewComponentRun](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponent.ViewComponentRun.html): kết thúc view và quản lý lần chạy bất đồng bộ.
- [JLine 3 — Terminal](https://jline.org/versions/3.x/docs/terminal/): tạo và quản lý terminal, tín hiệu, capability và vòng đời tài nguyên.
- [JLine 3 — Terminal Attributes](https://jline.org/versions/3.x/docs/advanced/terminal-attributes/): lưu, thay đổi và khôi phục thuộc tính terminal.

Một giao diện chỉ được xem là kết thúc đúng khi vòng lặp đã dừng, các subscription và tác vụ riêng của view đã được giải phóng, trạng thái terminal do ứng dụng thay đổi đã được khôi phục và tài nguyên được đóng bởi đúng chủ sở hữu. Giữ terminal dùng chung cho tới khi Spring Shell kết thúc ApplicationContext để người dùng có thể quay lại prompt và tiếp tục làm việc.

