# EventLoop và luồng xử lý sự kiện

Một ứng dụng terminal UI thường phải xử lý nhiều nguồn tương tác cùng lúc: phím bấm, chuột, tín hiệu từ terminal, sự kiện do view phát ra và kết quả của tác vụ chạy nền. Nếu mỗi thành phần tự đọc input và tự vẽ lại màn hình, các thao tác dễ xung đột và khó quản lý vòng đời.

Trong Spring Shell 3.x, `EventLoop` là điểm điều phối các sự kiện trong vòng đời của terminal UI. Sự kiện được biểu diễn dưới dạng Spring `Message`, truyền qua các luồng Reactor `Flux`. Ứng dụng có thể đăng ký listener để nhận sự kiện, gửi message vào loop bằng `dispatch`, lọc theo loại hoặc kiểu payload và dọn dẹp subscription khi loop kết thúc.

## 1. EventLoop giải quyết vấn đề gì?

`EventLoop` tập trung việc tiếp nhận và điều phối sự kiện của terminal UI. Nó hỗ trợ đồng bộ thời điểm cập nhật trạng thái component và vẽ lại màn hình.

Một ứng dụng quản lý tiến trình triển khai có thể nhận các sự kiện sau:

- Người dùng nhấn `Ctrl+Q` để thoát.
- Người dùng nhấn phím mũi tên để chọn một mục trong danh sách.
- Người dùng nhấp chuột vào nút làm mới.
- Terminal gửi tín hiệu resize.
- Tác vụ chạy nền hoàn tất và trả về kết quả mới.
- Một view phát sự kiện khi lựa chọn hoặc trạng thái nội dung thay đổi.

Các nguồn này có thể đưa message vào cùng một event loop. View và ứng dụng đăng ký subscriber để xử lý đúng loại sự kiện mà mình quan tâm.

`EventLoop` không phải command dispatcher của Spring Shell. Command dispatcher phân tích và gọi command CLI; event loop xử lý tương tác trong giao diện terminal UI đang hiển thị.

## 2. Message là đơn vị trao đổi sự kiện

Trong Spring Shell 3.x, event loop làm việc với Spring `Message<?>`. Một message có:

- Payload: dữ liệu chính của sự kiện, ví dụ `KeyEvent`, `MouseEvent` hoặc một record do ứng dụng định nghĩa.
- Header: metadata như loại sự kiện, view liên quan hoặc mức ưu tiên.

Spring Shell cung cấp `ShellMessageBuilder` để tạo message theo quy ước của terminal UI. Một số factory thường dùng:

| API | Mục đích |
|---|---|
| `ShellMessageBuilder.ofKeyEvent(event)` | Tạo message từ `KeyEvent` |
| `ShellMessageBuilder.ofMouseEvent(event)` | Tạo message từ `MouseEvent` |
| `ShellMessageBuilder.ofSignal(signal)` | Tạo message tín hiệu |
| `ShellMessageBuilder.ofRedraw()` | Tạo message yêu cầu vẽ lại |
| `ShellMessageBuilder.ofInterrupt()` | Tạo message yêu cầu ngắt vòng lặp |
| `ShellMessageBuilder.ofView(view, args)` | Tạo message liên quan đến view |
| `ShellMessageBuilder.withPayload(payload)` | Bắt đầu tạo message tùy chỉnh |

Với message tùy chỉnh, gọi `setEventType(...)` để gắn loại sự kiện trước khi `build()`:

~~~java
Message<RefreshRequested> message =
        ShellMessageBuilder.withPayload(new RefreshRequested())
                .setEventType(EventLoop.Type.USER)
                .build();
~~~

`EventLoop.Type.USER` dành cho sự kiện do ứng dụng định nghĩa. Việc gắn type giúp subscriber lọc đúng nhóm message.

## 3. Các loại sự kiện của EventLoop

`EventLoop.Type` trong Spring Shell 3.4.3 có các giá trị:

| Type | Ý nghĩa |
|---|---|
| `KEY` | Sự kiện phím từ terminal |
| `MOUSE` | Sự kiện chuột từ terminal |
| `SIGNAL` | Tín hiệu được gửi từ terminal |
| `SYSTEM` | Sự kiện hệ thống, ví dụ yêu cầu redraw |
| `VIEW` | Sự kiện phát ra từ view |
| `USER` | Sự kiện tùy chỉnh do ứng dụng gửi |
| `TASK` | Nhóm type dành cho xử lý task; chi tiết phụ thuộc processor sử dụng |

Type cho biết nhóm sự kiện, còn payload cho biết dữ liệu cụ thể. Ví dụ, hai message cùng có type `USER` vẫn có thể mang payload là `RefreshRequested` hoặc `ImportFinished`.

Không nên dùng type `USER` cho mọi message chỉ vì nó dễ nhớ. Hãy dùng `KEY`, `MOUSE`, `SIGNAL`, `SYSTEM` hoặc `VIEW` khi sự kiện thuộc đúng nhóm đó, và dành `USER` cho sự kiện nghiệp vụ của ứng dụng.

## 4. Lấy EventLoop từ TerminalUI

`TerminalUI` điều phối terminal, event loop và cây view. Có thể tạo trực tiếp với JLine `Terminal`, cấu hình view gốc rồi lấy event loop:

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.control.View;
import org.springframework.shell.component.view.event.EventLoop;

public void runUi(Terminal terminal, View rootView) {
    TerminalUI ui = new TerminalUI(terminal);

    ui.configure(rootView);
    ui.setRoot(rootView, true);

    EventLoop eventLoop = ui.getEventLoop();
    // Đăng ký subscriber trước khi chạy vòng lặp.

    ui.run();
}
~~~

`ui.configure(rootView)` thiết lập các tích hợp cần thiết cho view, gồm event loop, theme resolver, tên theme và `ViewService`. `setRoot(rootView, true)` đặt view gốc và yêu cầu chế độ toàn màn hình.

`ui.run()` là thao tác blocking: phương thức giữ luồng hiện tại cho đến khi vòng lặp kết thúc. Vì vậy, hãy đăng ký các listener và cơ chế thoát trước khi gọi `run()`.

Trong ứng dụng Spring Boot, có thể dùng `TerminalUIBuilder` đã được auto-configure để tạo UI với các dịch vụ cần thiết. Cách tạo thủ công bằng `new TerminalUI(terminal)` hữu ích khi muốn thấy rõ các bước khởi tạo trong ví dụ.

## 5. Đăng ký nhận mọi message hoặc một nhóm cụ thể

`events()` trả về `Flux` chứa các Spring `Message<?>`. Subscriber chỉ nhận sự kiện sau khi đăng ký:

~~~java
eventLoop.events()
        .subscribe(message -> {
            Object payload = message.getPayload();
            // Phân loại và xử lý message.
        });
~~~

Thông thường nên dùng các phương thức lọc có kiểu rõ ràng thay vì nhận mọi message:

| Phương thức | Kiểu payload |
|---|---|
| `keyEvents()` | `KeyEvent` |
| `mouseEvents()` | `MouseEvent` |
| `signalEvents()` | `String` |
| `systemEvents()` | `String` |
| `viewEvents(MyViewEvent.class)` | Kiểu con của `ViewEvent` |
| `events(type, Payload.class)` | Payload có kiểu chỉ định và event type tương ứng |

Ví dụ, chỉ theo dõi sự kiện phím:

~~~java
eventLoop.keyEvents()
        .subscribe(event -> {
            System.out.println("Key code: " + event.key());
            System.out.println("Raw data: " + event.data());
        });
~~~

Hoặc chỉ nhận một loại payload do ứng dụng định nghĩa:

~~~java
eventLoop.events(EventLoop.Type.USER, RefreshRequested.class)
        .subscribe(event -> {
            // Xử lý yêu cầu làm mới.
        });
~~~

Các `Flux` này tiếp tục phát sự kiện cho đến khi subscription bị dispose hoặc event loop kết thúc. Nếu không có subscriber, đoạn xử lý trong `subscribe` không chạy.

## 6. Xử lý sự kiện bàn phím

`KeyEvent` là record chứa mã phím và dữ liệu thô từ terminal. Một số phương thức hữu ích:

| Thành phần | Vai trò |
|---|---|
| `key()` | Giá trị mã phím có mask |
| `data()` | Chuỗi dữ liệu thô |
| `getPlainKey()` | Mã phím sau khi bỏ phần modifier |
| `hasCtrl()` | Kiểm tra modifier Ctrl |
| `isKey(int)` | So sánh với một mã phím |

Ví dụ, đăng ký `Ctrl+Q` để gửi yêu cầu ngắt event loop:

~~~java
import org.springframework.shell.component.message.ShellMessageBuilder;
import org.springframework.shell.component.view.event.EventLoop;
import org.springframework.shell.component.view.event.KeyEvent;

eventLoop.keyEvents()
        .filter(event ->
                event.hasCtrl()
                        && event.getPlainKey() == KeyEvent.Key.q)
        .subscribe(event ->
                eventLoop.dispatch(ShellMessageBuilder.ofInterrupt()));
~~~

`KeyEvent.Key.q` là hằng số mã phím `q`. Kết hợp với `hasCtrl()` giúp phân biệt `Ctrl+Q` với ký tự `q` thông thường.

Ví dụ trên chỉ gửi message ngắt vòng lặp. Để ứng dụng hoàn tất đúng cách, cần bảo đảm tài nguyên liên quan đến view và terminal được đóng theo vòng đời của ứng dụng.

## 7. Thoát khỏi TerminalUI bằng interrupt message

Tài liệu Spring Shell minh họa cách thoát khỏi UI bằng tổ hợp `Ctrl+Q`. Event listener nhận phím, sau đó dispatch `ShellMessageBuilder.ofInterrupt()` vào event loop:

~~~java
import org.jline.terminal.Terminal;
import org.springframework.shell.component.message.ShellMessageBuilder;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.control.View;
import org.springframework.shell.component.view.event.EventLoop;
import org.springframework.shell.component.view.event.KeyEvent;
import reactor.core.Disposable;

public void runUi(Terminal terminal, View rootView) {
    TerminalUI ui = new TerminalUI(terminal);
    ui.configure(rootView);
    ui.setRoot(rootView, true);

    EventLoop eventLoop = ui.getEventLoop();
    Disposable exitListener = eventLoop.keyEvents()
            .filter(event ->
                    event.hasCtrl()
                            && event.getPlainKey() == KeyEvent.Key.q)
            .subscribe(event ->
                    eventLoop.dispatch(ShellMessageBuilder.ofInterrupt()));
    eventLoop.onDestroy(exitListener);

    ui.run();
}
~~~

`ofInterrupt()` tạo message đặc biệt yêu cầu vòng lặp dừng. Không nên chỉ đặt một biến boolean trong subscriber rồi chờ `ui.run()` tự kết thúc; hãy gửi message ngắt theo cơ chế của framework.

Trong mã ứng dụng thực tế, hãy giữ `Disposable` trả về từ `subscribe()` và đăng ký nó với `eventLoop.onDestroy(...)` như phần quản lý vòng đời bên dưới.

## 8. Dispatch message vào event loop

`dispatch` có hai overload:

- `dispatch(Message<?>)`: gửi một message.
- `dispatch(Publisher<? extends Message<?>>)`: gửi nhiều message từ một publisher như `Mono` hoặc `Flux`.

Ví dụ gửi một message redraw:

~~~java
eventLoop.dispatch(ShellMessageBuilder.ofRedraw());
~~~

Hoặc gửi một message tùy chỉnh:

~~~java
record RefreshRequested(String section) {}

eventLoop.dispatch(
        ShellMessageBuilder.withPayload(
                new RefreshRequested("deployments"))
                .setEventType(EventLoop.Type.USER)
                .build()
);
~~~

Một subscriber có thể nhận lại message này:

~~~java
eventLoop.events(EventLoop.Type.USER, RefreshRequested.class)
        .subscribe(request -> {
            // Cập nhật trạng thái phần deployments.
            ui.redraw();
        });
~~~

`dispatch` là cách đưa một sự kiện vào luồng điều phối. Không cần gọi trực tiếp subscriber hoặc tự gọi từng view để thông báo về một sự kiện ứng dụng.

## 9. Sự kiện từ view và bộ lọc theo view

View có thể phát các sự kiện chuyên biệt, ví dụ nội dung input thay đổi, item trong danh sách được chọn hoặc dialog đóng. Những sự kiện này kế thừa `ViewEvent`.

Có thể nhận mọi view event của một kiểu:

~~~java
eventLoop.viewEvents(MyViewEvent.class)
        .subscribe(event -> {
            // Xử lý event từ các view.
        });
~~~

Nếu chỉ quan tâm đến một view cụ thể, truyền thêm view vào bộ lọc:

~~~java
eventLoop.viewEvents(MyViewEvent.class, targetView)
        .subscribe(event -> {
            // Chỉ xử lý event phát ra từ targetView.
        });
~~~

Cách lọc này hữu ích khi ứng dụng có nhiều component cùng phát một kiểu event. Subscriber của màn hình chi tiết có thể chỉ nhận sự kiện từ view chi tiết thay vì nhận sự kiện của toàn bộ cây UI.

## 10. Sự kiện chuột

`mouseEvents()` trả về `Flux<MouseEvent>`. `MouseEvent` chứa tọa độ X/Y và thông tin sự kiện chuột của JLine.

~~~java
eventLoop.mouseEvents()
        .subscribe(event -> {
            // Đọc tọa độ và loại thao tác chuột.
            // Chuyển đổi thành hành động của view nếu cần.
        });
~~~

Terminal cần hỗ trợ mouse reporting thì ứng dụng mới nhận được đầy đủ sự kiện chuột. Khi triển khai trên terminal không hỗ trợ mouse mode, nên giữ các phím điều hướng tương đương để người dùng vẫn thao tác được.

## 11. Gửi sự kiện tùy chỉnh từ ứng dụng

`EventLoop.Type.USER` phù hợp cho sự kiện do ứng dụng định nghĩa. Ví dụ, khi người dùng bấm nút làm mới, view có thể gửi `RefreshRequested`; service xử lý dữ liệu rồi gửi `RefreshCompleted`.

~~~java
record RefreshRequested(String section) {}
record RefreshCompleted(String section, int itemCount) {}
record RefreshFailed(String section, String reason) {}
~~~

Đăng ký subscriber cho kết quả:

~~~java
eventLoop.events(EventLoop.Type.USER, RefreshCompleted.class)
        .subscribe(event -> {
            // Cập nhật số lượng item trên view.
            ui.redraw();
        });

eventLoop.events(EventLoop.Type.USER, RefreshFailed.class)
        .subscribe(event -> {
            // Hiển thị lỗi trên status bar.
            ui.redraw();
        });
~~~

Khi bắt đầu yêu cầu, dispatch sự kiện:

~~~java
eventLoop.dispatch(
        ShellMessageBuilder.withPayload(
                new RefreshRequested("deployments"))
                .setEventType(EventLoop.Type.USER)
                .build()
);
~~~

Sự kiện tùy chỉnh tạo hợp đồng rõ ràng giữa các phần của UI. Payload nên chứa dữ liệu cần thiết cho subscriber, không mang theo cả đối tượng view hoặc các dependency không liên quan.

## 12. Xử lý tác vụ chạy nền mà không chặn UI

Một thao tác gọi API hoặc đọc dữ liệu có thể mất nhiều thời gian. Nếu thực hiện trực tiếp trong subscriber của event loop, giao diện có thể ngừng phản hồi trong lúc chờ.

Hãy chạy I/O trên scheduler phù hợp, sau đó dispatch kết quả trở lại event loop:

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Disposable task = Mono.fromCallable(reportService::loadLatest)
        .subscribeOn(Schedulers.boundedElastic())
        .subscribe(
                report -> eventLoop.dispatch(
                        ShellMessageBuilder.withPayload(
                                new RefreshCompleted("reports", report.size()))
                                .setEventType(EventLoop.Type.USER)
                                .build()),
                error -> eventLoop.dispatch(
                        ShellMessageBuilder.withPayload(
                                new RefreshFailed("reports", error.getMessage()))
                                .setEventType(EventLoop.Type.USER)
                                .build())
        );

eventLoop.onDestroy(task);
~~~

Luồng xử lý:

1. Event loop nhận yêu cầu làm mới.
2. Tác vụ đọc dữ liệu chạy trên `boundedElastic`, không giữ luồng xử lý UI trong lúc chờ I/O.
3. Khi hoàn tất, tác vụ dispatch `RefreshCompleted` hoặc `RefreshFailed`.
4. Subscriber của event loop nhận kết quả và cập nhật trạng thái view.
5. `onDestroy(task)` đăng ký subscription để nó được dispose khi event loop kết thúc.

`onDestroy` quản lý subscription, còn việc dừng một thao tác I/O đang chạy phụ thuộc khả năng hủy của nguồn dữ liệu. Nếu service gọi API hoặc thư viện không hỗ trợ cancellation, ứng dụng vẫn cần timeout và cơ chế đóng tài nguyên phù hợp.

## 13. EventLoopProcessor

`EventLoop.EventLoopProcessor` là hợp đồng xử lý message trước khi hoặc trong khi message được điều phối. Một processor có hai phương thức:

| Phương thức | Vai trò |
|---|---|
| `canProcess(Message<?>)` | Xác định processor có xử lý message này không |
| `process(Message<?>)` | Xử lý message và trả về `Flux` chứa một hoặc nhiều message mới |

Nếu `canProcess` trả `true`, `process` sẽ được gọi để chuyển đổi message. Nhờ vậy, một sự kiện đầu vào có thể được chuẩn hóa hoặc tạo thành các sự kiện tiếp theo.

Spring Shell có các processor tích hợp như:

- `AnimationEventLoopProcessor`: chuyển message đầu vào thành các message tick phục vụ animation.
- `TaskEventLoopProcessor`: xử lý message liên quan đến task.

`DefaultEventLoop` là implementation mặc định và có constructor nhận danh sách `EventLoopProcessor`. Chỉ cần viết processor riêng khi ứng dụng thật sự cần một bước chuyển đổi sự kiện dùng chung. Với logic đơn giản của một màn hình, subscriber và `dispatch` thường dễ đọc hơn.

## 14. Quản lý subscription và vòng đời

Mỗi lần gọi `subscribe()` trả về một `Disposable`. Nếu subscription sống lâu hơn view hoặc event loop, nó có thể tiếp tục nhận sự kiện và giữ tham chiếu tới các đối tượng đã không còn dùng.

Đăng ký dọn dẹp cùng event loop:

~~~java
Disposable keySubscription = eventLoop.keyEvents()
        .subscribe(this::handleKey);

Disposable viewSubscription =
        eventLoop.viewEvents(MyViewEvent.class)
                .subscribe(this::handleViewEvent);

eventLoop.onDestroy(keySubscription);
eventLoop.onDestroy(viewSubscription);
~~~

Khi event loop kết thúc, các `Disposable` đã đăng ký được dispose. Với subscription cần dừng sớm trước khi UI kết thúc, có thể gọi `dispose()` trực tiếp.

Các nguyên tắc cần giữ:

- Đăng ký subscriber sau khi đã lấy được event loop và trước khi chạy UI.
- Không tạo subscription mới mỗi lần redraw nếu subscription cũ vẫn còn hoạt động.
- Dispose listener gắn với view khi view bị hủy.
- Đưa công việc I/O dài ra khỏi xử lý tương tác.
- Định nghĩa nhánh xử lý lỗi cho các luồng Reactor chạy lâu.

## 15. Phân biệt redraw, interrupt và signal

Ba message có mục đích khác nhau:

| Message | Ý nghĩa |
|---|---|
| `ShellMessageBuilder.ofRedraw()` | Yêu cầu UI vẽ lại màn hình |
| `ShellMessageBuilder.ofInterrupt()` | Yêu cầu dừng vòng lặp terminal UI |
| `ShellMessageBuilder.ofSignal(value)` | Đưa một tín hiệu vào event loop |

`ui.redraw()` cũng yêu cầu vẽ lại toàn bộ màn hình bằng cách dispatch message vào event loop. Nên dùng API mức cao này khi đang có `TerminalUI`; dùng `ofRedraw()` khi cần tạo message redraw để gửi qua event loop.

Không dùng interrupt chỉ để làm mới giao diện. Interrupt kết thúc vòng lặp; redraw chỉ yêu cầu hiển thị lại trạng thái mới.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Subscriber không nhận sự kiện | Chưa gọi `subscribe()` | Đăng ký subscriber trước khi chạy UI |
| Subscriber nhận quá nhiều loại message | Dùng `events()` mà không lọc | Dùng `keyEvents()`, `viewEvents()` hoặc `events(type, Class)` |
| Message tùy chỉnh không được nhận | Chưa gắn `EventLoop.Type` phù hợp | Gọi `setEventType(EventLoop.Type.USER)` trước `build()` |
| Subscriber nhận sai payload | Bộ lọc type hoặc class không khớp | Kiểm tra event type và lớp payload khi dispatch |
| UI không thoát khi nhấn phím | Chỉ đặt cờ trong listener, không gửi interrupt | Dispatch `ShellMessageBuilder.ofInterrupt()` |
| UI đứng khi gọi service | Thực hiện I/O đồng bộ trong subscriber | Dùng Reactor scheduler hoặc cơ chế async phù hợp |
| Listener chạy sau khi view đã hủy | Không dispose subscription | Đăng ký `Disposable` với `onDestroy` |
| Vẽ lại liên tục hoặc nhấp nháy | Dispatch redraw quá nhiều lần | Gộp thay đổi trạng thái và chỉ redraw khi cần |
| Tín hiệu chuột không đến | Terminal không hỗ trợ hoặc chưa bật mouse reporting | Kiểm tra terminal và cung cấp thao tác bàn phím thay thế |
| Luồng nền cập nhật trực tiếp view | Không điều phối kết quả qua event loop | Dispatch một message kết quả rồi cập nhật view trong subscriber |

## 17. Checklist kiểm thử EventLoop

Trước khi phát hành terminal UI, hãy kiểm tra:

1. View gốc được cấu hình bằng `ui.configure(view)` và đăng ký bằng `ui.setRoot(...)`.
2. `ui.run()` bắt đầu vòng lặp và giữ luồng cho đến khi có yêu cầu kết thúc.
3. Listener phím nhận đúng `KeyEvent` và phân biệt được modifier.
4. Sự kiện chuột được nhận khi terminal hỗ trợ mouse reporting.
5. `events(type, Payload.class)` chỉ nhận đúng type và payload.
6. Message tùy chỉnh được dispatch và subscriber nhận đúng dữ liệu.
7. Tác vụ chạy nền không làm UI ngừng phản hồi.
8. Lỗi của tác vụ được chuyển thành message để view hiển thị.
9. `Disposable` được dispose khi event loop kết thúc.
10. Interrupt dừng UI; redraw chỉ làm mới màn hình.

## 18. Bài tập thực hành

Xây dựng một màn hình theo dõi tiến trình triển khai:

- Hiển thị trạng thái hiện tại và số tác vụ đã hoàn tất.
- Nhấn `R` để yêu cầu tải lại dữ liệu.
- Nhấn `Ctrl+Q` để thoát.
- Khi tải dữ liệu, hiển thị trạng thái đang xử lý.
- Khi tác vụ hoàn tất, gửi `RefreshCompleted` qua event loop và cập nhật view.
- Khi tác vụ lỗi, gửi `RefreshFailed` và hiển thị thông báo.

Yêu cầu:

1. Tạo `TerminalUI`, cấu hình root view và lấy `EventLoop`.
2. Đăng ký subscriber `keyEvents()` để xử lý `R` và `Ctrl+Q`.
3. Tạo record `RefreshRequested`, `RefreshCompleted` và `RefreshFailed`.
4. Dùng `ShellMessageBuilder.withPayload(...).setEventType(USER).build()` để dispatch event.
5. Dùng `events(USER, Payload.class)` để nhận kết quả.
6. Chạy thao tác tải dữ liệu trên scheduler phù hợp.
7. Đăng ký mọi `Disposable` bằng `eventLoop.onDestroy(...)`.
8. Kiểm thử thành công, lỗi, thao tác thoát và việc hủy subscription.

Sau bài tập, hãy giải thích được vì sao sự kiện phím, kết quả tác vụ và yêu cầu redraw đều có thể đi qua cùng một event loop nhưng vẫn được phân biệt bằng event type và kiểu payload.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 – EventLoop](https://docs.spring.io/spring-shell/reference/3.4/tui/events/eventloop.html)
- [Spring Shell 3.4.3 – Events](https://docs.spring.io/spring-shell/reference/3.4/tui/events/index.html)
- [Spring Shell 3.4.3 – Key Handling](https://docs.spring.io/spring-shell/reference/3.4/tui/events/key.html)
- [Spring Shell 3.4.3 – Mouse Handling](https://docs.spring.io/spring-shell/reference/3.4/tui/events/mouse.html)
- [Spring Shell 3.4.3 API – EventLoop](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/EventLoop.html)
- [Spring Shell 3.4.3 API – EventLoop.Type](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/EventLoop.Type.html)
- [Spring Shell 3.4.3 API – EventLoopProcessor](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/EventLoop.EventLoopProcessor.html)
- [Spring Shell 3.4.3 API – KeyEvent](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/KeyEvent.html)
- [Spring Shell 3.4.3 API – ShellMessageBuilder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/message/ShellMessageBuilder.html)
- [Spring Shell 3.4.3 API – TerminalUI](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUI.html)
- [Spring Shell 3.4.3 API – DefaultEventLoop](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/DefaultEventLoop.html)
