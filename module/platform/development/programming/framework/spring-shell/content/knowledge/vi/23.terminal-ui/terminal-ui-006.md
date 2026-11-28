# DialogView và tương tác có ngữ cảnh

Một command đôi khi cần hiển thị thông tin liên quan đến một thao tác rồi yêu cầu người dùng chọn tiếp tục hoặc hủy. Ví dụ, trước khi triển khai, CLI cần cho biết dự án nào, môi trường nào và phiên bản nào sẽ được phát hành. Một câu hỏi `yes/no` đơn giản có thể không đủ ngữ cảnh; `DialogView` cho phép đặt nội dung tùy ý cùng các nút hành động trong một cửa sổ terminal.

Trong Spring Shell 3.x, `DialogView` là một `View` có viền, vùng nội dung và danh sách `ButtonView`. `TerminalUI` điều phối các view, event loop, focus và modal. Dữ liệu nghiệp vụ nên được chuẩn bị thành một context rõ ràng rồi truyền vào phần nội dung và callback của dialog. Khi người dùng chọn nút, event cho biết view nào phát sinh tương tác để ứng dụng cập nhật quyết định tương ứng.

## 1. DialogView nằm ở đâu trong Terminal UI?

Spring Shell 3.4 cung cấp các view cơ bản để xây dựng giao diện terminal:

| View | Vai trò |
| --- | --- |
| `BoxView` | Khung nội dung có tiêu đề, nền và viền tùy chọn |
| `GridView` | Bố trí nhiều view theo hàng và cột |
| `InputView` | Nhập và chỉnh sửa văn bản trong một vùng |
| `ListView<T>` | Hiển thị danh sách có thể chọn |
| `ButtonView` | Nút có nhãn và hành động khi được chọn |
| `DialogView` | Cửa sổ có nội dung chính và vùng nút ở phía dưới |
| `AppView` | Bố cục ứng dụng gồm menu, nội dung chính và status bar |

`DialogView` kế thừa `WindowView` và nhận một `View` làm nội dung cùng một danh sách hoặc mảng `ButtonView`. Cấu trúc này phù hợp với hộp thoại xác nhận, thông báo lỗi, xem trước thay đổi hoặc yêu cầu người dùng chọn một hành động. <Link url="https://docs.spring.io/spring-shell/reference/3.4/tui/views/dialog.html" title="DialogView — Spring Shell 3.4.3"/>.

## 2. Phân biệt ba lớp: dữ liệu nghiệp vụ, View và EventLoop

Khi xây dựng dialog có ngữ cảnh, hãy phân chia trách nhiệm thành ba lớp:

1. **Dữ liệu nghiệp vụ:** thông tin cần hiển thị và dùng để quyết định, ví dụ project ID, tên project, environment, version và người yêu cầu.
2. **View:** cách trình bày dữ liệu và các lựa chọn cho người dùng, ví dụ `BoxView`, `DialogView`, `ButtonView`.
3. **EventLoop:** nhận sự kiện bàn phím/chuột và sự kiện view, điều phối callback, cập nhật trạng thái và redraw.

`DialogView` không tự biết dự án hoặc môi trường triển khai là gì. Ứng dụng cung cấp dữ liệu vào view. Khi người dùng chọn nút, ứng dụng đọc sự kiện và quyết định tiếp tục hay hủy. Không nên đặt truy vấn dữ liệu hoặc quy tắc quyền truy cập vào phần render của view.

Một context nghiệp vụ có thể là record bất biến:

```java
public record DeploymentDialogContext(
        String projectId,
        String projectName,
        String environmentId,
        String environmentName,
        String version) {
}
```

Quyết định sau khi người dùng tương tác có thể biểu diễn bằng enum:

```java
public enum DeploymentDecision {
    CONFIRM,
    CANCEL
}
```

Tạo context sau khi service đã kiểm tra dữ liệu cần hiển thị. Dialog sử dụng cùng snapshot này cho nội dung và hành động, nhờ đó người dùng nhìn thấy đúng đối tượng mà command đang yêu cầu xác nhận.

## 3. Tạo TerminalUI bằng TerminalUIBuilder

`TerminalUI` là thành phần điều phối terminal, event loop, sự kiện bàn phím/chuột và cấu trúc view. Spring Shell 3.4 khuyến nghị sử dụng `TerminalUIBuilder` đã được cấu hình tự động thay vì tự tạo toàn bộ dịch vụ.

```java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.stereotype.Component;

@Component
public class DialogSupport {

    private final TerminalUIBuilder terminalUIBuilder;

    public DialogSupport(TerminalUIBuilder terminalUIBuilder) {
        this.terminalUIBuilder = terminalUIBuilder;
    }

    public TerminalUI createTerminalUI() {
        return terminalUIBuilder.build();
    }
}
```

`TerminalUIBuilder.build()` tạo một `TerminalUI` mới và áp dụng các customizer, theme resolver và theme name đã cấu hình. Khi cần cấu hình một UI đã tạo sẵn, builder cũng có `configure(terminalUI)`. <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUIBuilder.html" title="TerminalUIBuilder API — Spring Shell 3.4.3"/>.

## 4. Tạo nội dung dialog bằng BoxView

`DialogView` nhận nội dung dưới dạng một `View`, không bắt buộc nội dung phải là một loại component cụ thể. `BoxView` phù hợp để hiển thị thông tin tóm tắt bằng `setDrawFunction(...)`.

```java
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.geom.HorizontalAlign;
import org.springframework.shell.geom.VerticalAlign;

private BoxView createDeploymentSummary(DeploymentDialogContext context) {
    BoxView content = new BoxView();
    content.setTitle("Thông tin triển khai");
    content.setDrawFunction((screen, rect) -> {
        String details = "Dự án: " + context.projectName()
                + "\nMôi trường: " + context.environmentName()
                + "\nPhiên bản: " + context.version();

        screen.writerBuilder().build().text(
                details, rect, HorizontalAlign.LEFT, VerticalAlign.TOP);
        return rect;
    });
    return content;
}
```

`setDrawFunction` nhận callback vẽ nội dung trong hình chữ nhật mà view được cấp. Callback trả về rectangle theo hợp đồng của renderer. Trong ví dụ, dữ liệu được chuẩn bị trước; renderer chỉ chuyển dữ liệu thành văn bản hiển thị.

## 5. Thêm nút vào DialogView

`ButtonView` có thể được tạo bằng nhãn và `Runnable`:

```java
ButtonView confirmButton = new ButtonView("Triển khai");
ButtonView cancelButton = new ButtonView("Hủy");

DialogView dialog = new DialogView(
        createDeploymentSummary(context),
        confirmButton,
        cancelButton);
```

`DialogView` cũng có constructor nhận `List<ButtonView>`. `ButtonView` hỗ trợ `setAction(...)` hoặc constructor `ButtonView(String, Runnable)` nếu muốn gắn hành động trực tiếp. Mặc định, Enter chọn nút đang focus và thao tác nhấn chuột trái cũng chọn nút. <Link url="https://docs.spring.io/spring-shell/reference/3.4/tui/views/button.html" title="ButtonView — Spring Shell 3.4.3"/>.

`DialogView` không có default bindings riêng. Hành vi xác nhận, hủy và đóng cần được định nghĩa rõ trong ứng dụng, thông qua hành động của nút hoặc xử lý event phù hợp.

## 6. Cấu hình view và mở dialog dạng modal

`TerminalUI.configure(view)` gắn các tích hợp cần thiết cho view như `EventLoop`, `ThemeResolver`, theme name và `ViewService`. Sau khi cấu hình, có thể đặt một view làm root hoặc làm modal.

```java
TerminalUI ui = terminalUIBuilder.build();

BoxView root = new BoxView();
root.setTitle("Quản lý triển khai");

DialogView dialog = new DialogView(
        createDeploymentSummary(context),
        confirmButton,
        cancelButton);

ui.configure(root);
ui.configure(dialog);
ui.setRoot(root, true);
ui.setModal(dialog);
```

Modal được đặt trên view nền và nhận toàn bộ input khi đang mở. `setModal(null)` xóa modal hiện tại. Vì vậy, có thể giữ nguyên màn hình chính trong khi dialog xuất hiện, rồi quay lại màn hình đó khi dialog đóng. <Link url="https://docs.spring.io/spring-shell/reference/3.4/tui/intro/terminalui.html" title="TerminalUI — Spring Shell 3.4.3"/>.

## 7. Chạy event loop và nhận kết quả tương tác

`TerminalUI.run()` khởi chạy vòng lặp giao diện và chặn cho đến khi vòng lặp kết thúc. Event loop cung cấp các luồng event có kiểu, bao gồm `keyEvents()`, `mouseEvents()` và `viewEvents(...)`.

`ButtonViewSelectEvent` cho biết một nút được chọn. Trường `view()` trả về view phát sinh sự kiện; ứng dụng có thể so sánh với các nút đã tạo để xác định người dùng chọn hành động nào.

Ví dụ xử lý lựa chọn bằng event loop:

```java
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.Disposable;
import org.springframework.shell.component.message.ShellMessageBuilder;
import org.springframework.shell.component.view.event.EventLoop;
import org.springframework.shell.component.view.control.ButtonView;

AtomicReference<DeploymentDecision> decision =
        new AtomicReference<>(DeploymentDecision.CANCEL);
EventLoop eventLoop = ui.getEventLoop();

Disposable selectionSubscription = eventLoop
        .viewEvents(ButtonView.ButtonViewSelectEvent.class)
        .subscribe(event -> {
            if (event.view() == confirmButton) {
                decision.set(DeploymentDecision.CONFIRM);
                dialog.getViewService().setModal(null);
            } else if (event.view() == cancelButton) {
                decision.set(DeploymentDecision.CANCEL);
                dialog.getViewService().setModal(null);
            }
        });

eventLoop.onDestroy(selectionSubscription);
```

Trong ví dụ này, callback chỉ cập nhật quyết định và đóng modal. Nếu dialog đang chạy như một giao diện độc lập, cần kết thúc vòng lặp sau khi lựa chọn được ghi nhận; mục tiếp theo trình bày cách làm. Nếu dialog nằm trong một ứng dụng TUI lớn hơn, chỉ đóng modal để trả quyền điều khiển về view nền.

## 8. Đóng dialog và kết thúc một UI độc lập

Khi dialog là modal trong một ứng dụng đang chạy, chỉ cần gọi `ViewService.setModal(null)` để đóng nó. `ViewService` cung cấp `getModal()`, `setModal(...)` và `setFocus(...)`, nhờ đó view có thể quản lý modal hoặc focus mà không cần phụ thuộc trực tiếp vào `TerminalUI`.

Nếu command tự khởi chạy một UI riêng cho dialog, cần kết thúc vòng lặp sau khi người dùng chọn. Có thể gửi interrupt message vào event loop:

```java
eventLoop.dispatch(ShellMessageBuilder.ofInterrupt());
```

Khi dùng trong subscription ở mục trước, thêm dòng này sau khi cập nhật quyết định và đóng modal. Sau đó gọi `ui.run()` và đọc kết quả khi vòng lặp kết thúc:

```java
ui.run();
return decision.get();
```

Không gửi interrupt khi dialog chỉ là modal của một ứng dụng TUI dài hạn, vì thao tác đó kết thúc toàn bộ UI loop thay vì chỉ đóng dialog. <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/EventLoop.html" title="EventLoop API — Spring Shell 3.4.3"/> · <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ViewService.html" title="ViewService API — Spring Shell 3.4.3"/>.

## 9. Ví dụ hoàn chỉnh: xác nhận triển khai có ngữ cảnh

Ví dụ dưới đây ghép các bước: tạo context từ dữ liệu preview, dựng nội dung dialog, nhận lựa chọn bằng event, đóng modal và chỉ gọi service triển khai sau khi người dùng xác nhận.

```java
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.Disposable;
import org.springframework.shell.component.message.ShellMessageBuilder;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.BoxView;
import org.springframework.shell.component.view.control.ButtonView;
import org.springframework.shell.component.view.control.DialogView;
import org.springframework.shell.component.view.event.EventLoop;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class DeploymentCommands {

    private final TerminalUIBuilder terminalUIBuilder;
    private final DeploymentService deploymentService;

    public DeploymentCommands(
            TerminalUIBuilder terminalUIBuilder,
            DeploymentService deploymentService) {
        this.terminalUIBuilder = terminalUIBuilder;
        this.deploymentService = deploymentService;
    }

    @ShellMethod(key = "deploy-confirmed", value = "Triển khai sau khi xác nhận")
    public String deploy(String projectId, String environmentId) {
        DeploymentDialogContext context =
                deploymentService.createPreview(projectId, environmentId);

        if (showConfirmation(context) != DeploymentDecision.CONFIRM) {
            return "Đã hủy triển khai.";
        }

        deploymentService.deploy(context.projectId(), context.environmentId());
        return "Đã gửi yêu cầu triển khai " + context.projectName();
    }

    private DeploymentDecision showConfirmation(DeploymentDialogContext context) {
        TerminalUI ui = terminalUIBuilder.build();
        EventLoop eventLoop = ui.getEventLoop();
        AtomicReference<DeploymentDecision> decision =
                new AtomicReference<>(DeploymentDecision.CANCEL);

        BoxView root = new BoxView();
        root.setTitle("Deployment Console");

        BoxView content = createDeploymentSummary(context);
        ButtonView confirm = new ButtonView("Triển khai");
        ButtonView cancel = new ButtonView("Hủy");
        DialogView dialog = new DialogView(content, confirm, cancel);

        ui.configure(root);
        ui.configure(dialog);
        ui.setRoot(root, true);
        ui.setModal(dialog);

        Disposable subscription = eventLoop
                .viewEvents(ButtonView.ButtonViewSelectEvent.class)
                .subscribe(event -> {
                    if (event.view() == confirm) {
                        decision.set(DeploymentDecision.CONFIRM);
                    } else if (event.view() == cancel) {
                        decision.set(DeploymentDecision.CANCEL);
                    } else {
                        return;
                    }

                    dialog.getViewService().setModal(null);
                    eventLoop.dispatch(ShellMessageBuilder.ofInterrupt());
                });
        eventLoop.onDestroy(subscription);

        ui.run();
        return decision.get();
    }

    private BoxView createDeploymentSummary(DeploymentDialogContext context) {
        BoxView content = new BoxView();
        content.setTitle("Xác nhận triển khai");
        content.setDrawFunction((screen, rect) -> {
            String details = "Dự án: " + context.projectName()
                    + "\nMôi trường: " + context.environmentName()
                    + "\nPhiên bản: " + context.version();
            screen.writerBuilder().build().text(
                    details, rect,
                    org.springframework.shell.geom.HorizontalAlign.LEFT,
                    org.springframework.shell.geom.VerticalAlign.TOP);
            return rect;
        });
        return content;
    }
}
```

Các kiểu `DeploymentDialogContext`, `DeploymentDecision` và `DeploymentService` thuộc ứng dụng. Ví dụ giả định `createPreview(...)` đã tải và kiểm tra dữ liệu cần hiển thị. `deploy(...)` chỉ được gọi sau khi lựa chọn là `CONFIRM`; nhánh hủy không thực hiện thay đổi nghiệp vụ.

Trong ứng dụng thực tế, hãy tách `createDeploymentSummary(...)` và phần dựng dialog thành lớp hỗ trợ nếu nhiều command cần dùng chung. Có thể thay event subscription bằng `ButtonView.setAction(...)` khi hành động đơn giản và không cần xử lý event tập trung.

## 10. Event của dialog và event của nút

Spring Shell định nghĩa các event có kiểu cho từng view:

| Event | Ý nghĩa | Dữ liệu chính |
| --- | --- | --- |
| `ButtonViewSelectEvent` | Một nút được chọn | `view()` là `ButtonView` phát sinh sự kiện |
| `DialogViewCloseEvent` | Dialog yêu cầu được đóng | `view()` là dialog phát sinh sự kiện |
| `InputViewTextChangeEvent` | Nội dung nhập thay đổi | View và thông tin thay đổi input |
| `ListViewSelectedItemChangedEvent` | Mục đang chọn trong danh sách thay đổi | View và dữ liệu mục được chọn |
| `ListViewOpenSelectedItemEvent` | Người dùng yêu cầu mở mục đang chọn | View và mục hiện tại |

Có thể subscribe riêng từng loại bằng `eventLoop.viewEvents(EventClass.class)`. Khi cần giới hạn theo một view cụ thể, API còn có overload nhận `View` để lọc. Hãy xử lý event theo kiểu cụ thể thay vì ép mọi event về một message không có ngữ nghĩa.

## 11. Truyền dữ liệu và cập nhật nội dung khi tương tác

Một dialog có thể thay đổi nội dung theo thao tác của người dùng. Ví dụ, khi chọn một môi trường khác, phần tóm tắt cần hiển thị region và version tương ứng.

Một cách tổ chức là giữ state riêng cho phiên dialog:

```java
public record DeploymentDialogState(
        DeploymentDialogContext context,
        String selectedRegion,
        boolean acknowledged) {
}
```

Khi nhận event:

1. Đọc view phát sinh và giá trị liên quan.
2. Cập nhật state của dialog.
3. Yêu cầu event loop redraw nếu nội dung hiển thị đã thay đổi.
4. Chỉ gọi service nghiệp vụ khi người dùng xác nhận và dữ liệu đã được kiểm tra.

`TerminalUI.redraw()` gửi yêu cầu vẽ lại toàn màn hình qua event loop. Nếu cập nhật state từ một tác vụ nền, hãy dispatch về event loop để tránh sửa trực tiếp view trong lúc renderer đang vẽ.

## 12. Modal, focus và view nền

`TerminalUI` hỗ trợ một modal view đang hoạt động tại một thời điểm. Modal nằm trên các view khác và nhận input. Khi modal được xóa, view nền tiếp tục nhận tương tác.

`ViewService.setFocus(view)` chuyển focus sang view mong muốn. Điều này hữu ích sau khi đóng dialog hoặc khi dialog có nhiều vùng tương tác như `InputView`, `ListView` và `ButtonView`.

Trong một ứng dụng có `AppView`, menu, main content và status bar có thể vẫn tồn tại trong khi modal mở. Dùng modal cho tác vụ ngắn cần xác nhận; dùng thay đổi main view khi người dùng đang chuyển sang một màn hình làm việc mới.

## 13. ViewComponent cho một view chạy riêng

Nếu chỉ muốn chạy một view trong một vùng terminal không chiếm toàn màn hình, Spring Shell 3.4 có `ViewComponent`. Nó nhận `TerminalUI`, JLine `Terminal`, `ViewComponentExecutor` và `View`; hỗ trợ `runBlocking()` hoặc `runAsync()`.

```java
ViewComponent component = new ViewComponent(
        terminalUI,
        terminal,
        viewComponentExecutor,
        dialog);

component.runBlocking();
```

`runAsync()` trả về `ViewComponentRun`, cho phép chờ, hủy hoặc kiểm tra component đã hoàn tất hay chưa. `ViewComponent` phù hợp khi cần thực thi một view riêng lẻ; `TerminalUI` phù hợp khi ứng dụng quản lý nhiều view, modal và event loop chung. <Link url="https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/ViewComponent.html" title="ViewComponent API — Spring Shell 3.4.3"/>.

## 14. Quản lý tài nguyên và vòng đời view

Event subscription cần được dispose khi event loop kết thúc. Có thể đăng ký `Disposable` với `eventLoop.onDestroy(...)`; khi view bị hủy, `AbstractView.onDestroy(...)` cũng cung cấp cơ chế đăng ký tài nguyên cần dispose.

Khi tạo UI cho mỗi lần gọi command:

- Tạo `TerminalUI` và các view cho lần chạy đó.
- Đăng ký event handler trước khi gọi `run()`.
- Dispose subscription khi event loop kết thúc.
- Không giữ `DialogView` hoặc `ButtonView` cũ trong singleton service sau khi dialog đã đóng.
- Không để callback giữ reference đến dữ liệu nhạy cảm lâu hơn cần thiết.

Nếu dùng view lâu dài trong ứng dụng TUI, hãy quản lý lifecycle rõ ràng: khi chuyển màn hình, gọi `destroy()` cho view không còn sử dụng nếu view giữ subscription hoặc tài nguyên riêng.

## 15. Xử lý lỗi và hủy thao tác

Dialog chỉ thu thập quyết định của người dùng. Service vẫn phải kiểm tra quyền, trạng thái và dữ liệu ngay trước khi thực hiện hành động.

Một số tình huống cần xử lý:

- Người dùng chọn `Hủy`: đóng dialog và trả quyết định cancel.
- Người dùng đóng dialog bằng cơ chế đóng được ứng dụng hỗ trợ: xem như cancel nếu chưa xác nhận.
- Dữ liệu preview hết hạn trong khi dialog đang mở: service kiểm tra lại và yêu cầu người dùng xem preview mới.
- Service triển khai thất bại sau khi xác nhận: hiển thị thông báo lỗi bằng dialog khác hoặc status view.
- Terminal bị ngắt hoặc event loop kết thúc bất thường: không mặc định xem thao tác là đã xác nhận.

Khởi tạo kết quả mặc định là `CANCEL` giúp các đường thoát không xác định không vô tình thực hiện hành động. Chỉ đổi sang `CONFIRM` khi nhận đúng event từ nút xác nhận.

## 16. DialogView trong interactive và non-interactive mode

`DialogView` yêu cầu terminal có tương tác để nhận phím và nút. Không mở dialog khi command được chạy từ script hoặc CI không có TTY.

Với command tự động, cung cấp tham số tường minh như `--yes` hoặc `--confirm`, đồng thời kiểm tra quyền và dữ liệu trong service. Nếu hành động có tác động lớn, có thể yêu cầu người vận hành truyền một cờ xác nhận rõ ràng trong non-interactive mode.

Command tương tác có thể hiển thị dialog để người dùng xem lại thông tin; command non-interactive dùng cùng service nhưng nhận quyết định từ tham số. Không để service nghiệp vụ phụ thuộc vào `TerminalUI` hoặc `DialogView`.

## 17. Kiểm thử dialog và event flow

Nên kiểm thử riêng phần dựng view, điều phối event và hành vi nghiệp vụ:

| Trường hợp | Điều cần xác nhận |
| --- | --- |
| Dialog content | Hiển thị đúng dữ liệu preview và ngữ cảnh thao tác |
| Nút xác nhận | Event nhận diện đúng `ButtonView` và trả `CONFIRM` |
| Nút hủy | Event trả `CANCEL` và không gọi service ghi dữ liệu |
| Modal | Dialog nhận input khi mở và được xóa khi đóng |
| Focus | Focus trở về view nền hoặc view được chỉ định |
| Event disposal | Subscription được dispose khi event loop kết thúc |
| Dữ liệu thay đổi | Service kiểm tra lại trạng thái trước khi thực hiện |
| UI độc lập | Interrupt kết thúc `TerminalUI.run()` sau khi có quyết định |
| UI nhúng | Đóng modal không kết thúc event loop của ứng dụng |
| Non-interactive | Command dùng option/argument thay cho DialogView |

Unit test có thể kiểm tra hàm tạo context, nội dung preview và cách ánh xạ quyết định. Integration test nên dùng terminal giả lập hoặc pseudo-terminal để kiểm tra phím Enter, điều hướng focus, chọn nút và đóng modal. Không chỉ kiểm tra text output; cần xác nhận service chỉ được gọi trong nhánh xác nhận.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dialog không xuất hiện | Chưa gọi `ui.configure(dialog)` hoặc `ui.setModal(dialog)` | Cấu hình view rồi đặt modal trước khi chạy UI loop |
| Nút không phản hồi | Chưa gắn action hoặc chưa xử lý `ButtonViewSelectEvent` | Gắn `setAction` hoặc subscribe event loop |
| Chọn nút nhưng dialog vẫn còn | Callback không gọi `ViewService.setModal(null)` | Xóa modal sau khi ghi nhận quyết định |
| UI độc lập không kết thúc | Chỉ đóng modal nhưng không interrupt loop | Dispatch `ShellMessageBuilder.ofInterrupt()` trong UI độc lập |
| Toàn bộ TUI bị dừng khi chỉ muốn đóng dialog | Gửi interrupt trong ứng dụng đang có event loop dài hạn | Chỉ xóa modal, giữ event loop chạy |
| Hành động chạy dù người dùng hủy | Giá trị quyết định mặc định sai hoặc service gọi trước xác nhận | Mặc định cancel và gọi service sau khi kiểm tra confirm |
| Nội dung dialog cũ | Giữ snapshot hoặc view từ lần chạy trước | Tạo context và view mới cho mỗi thao tác |
| Event handler vẫn chạy sau khi đóng | Không dispose subscription | Đăng ký Disposable với `eventLoop.onDestroy(...)` |
| Dialog không nhận input | Modal chưa được đặt hoặc focus không đúng | Kiểm tra `setModal` và `setFocus` |

## 19. Bài thực hành tổng hợp

Xây dựng command `deploy-review` hiển thị hộp thoại xác nhận trước khi triển khai:

1. Tạo `DeploymentDialogContext` chứa project, environment và version.
2. Tạo `TerminalUI` từ `TerminalUIBuilder` được Spring cấu hình.
3. Tạo root `BoxView` và nội dung dialog bằng một `BoxView` khác.
4. Tạo `DialogView` với hai nút `Triển khai` và `Hủy`.
5. Đăng ký `ButtonViewSelectEvent` trên event loop và nhận diện nút qua `event.view()`.
6. Khi xác nhận, ghi `CONFIRM`; khi hủy, giữ `CANCEL`.
7. Xóa modal bằng `dialog.getViewService().setModal(null)`.
8. Với UI độc lập, dispatch interrupt để kết thúc `ui.run()`; với modal nhúng, chỉ đóng modal.
9. Chỉ gọi `DeploymentService.deploy(...)` sau khi quyết định là `CONFIRM`.
10. Viết test xác nhận nút hủy không gọi service và command non-interactive có thể dùng `--confirm`.

Sau bài thực hành, bạn cần giải thích được dữ liệu nghiệp vụ đi vào dialog như thế nào, `ViewEvent` xác định view phát sinh ra sao, modal khác root view như thế nào và vì sao hủy dialog không được thực hiện hành động.

## 20. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| DialogView | Tạo dialog từ content View và các ButtonView |
| TerminalUI | Tạo UI bằng TerminalUIBuilder và cấu hình view |
| Modal | Mở, đóng modal và giữ view nền hoạt động |
| Context | Truyền dữ liệu nghiệp vụ vào nội dung và callback |
| EventLoop | Subscribe event có kiểu và nhận diện nguồn qua `view()` |
| Button | Xử lý xác nhận/hủy qua action hoặc event |
| Lifecycle | Kết thúc UI độc lập và dispose subscription |
| ViewService | Quản lý modal/focus mà không gắn chặt view với TerminalUI |
| Business rule | Chỉ thực hiện nghiệp vụ sau khi xác nhận và kiểm tra lại |
| Automation | Có cách chạy non-interactive không cần dialog |
| Testing | Kiểm thử event, modal, cancel và service invocation |

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — DialogView](https://docs.spring.io/spring-shell/reference/3.4/tui/views/dialog.html)
- [Spring Shell 3.4.3 — TerminalUI](https://docs.spring.io/spring-shell/reference/3.4/tui/intro/terminalui.html)
- [Spring Shell 3.4.3 — ButtonView](https://docs.spring.io/spring-shell/reference/3.4/tui/views/button.html)
- [Spring Shell 3.4.3 — `DialogView` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/DialogView.html)
- [Spring Shell 3.4.3 — `ButtonView` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ButtonView.html)
- [Spring Shell 3.4.3 — `TerminalUI` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUI.html)
- [Spring Shell 3.4.3 — `TerminalUIBuilder` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/TerminalUIBuilder.html)
- [Spring Shell 3.4.3 — `EventLoop` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/event/EventLoop.html)
- [Spring Shell 3.4.3 — `ViewService` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/view/control/ViewService.html)
- [Spring Shell 3.4.3 — `ViewComponent` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/ViewComponent.html)
