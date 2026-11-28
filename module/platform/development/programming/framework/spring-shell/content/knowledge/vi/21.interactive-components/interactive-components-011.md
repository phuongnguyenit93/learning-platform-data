# Thoát hoặc hủy một thành phần mà không làm sai trạng thái ứng dụng

Thành phần tương tác trong Spring Shell giúp command hỏi dữ liệu, chọn mục hoặc hiển thị một giao diện terminal. Người dùng có thể rời thành phần trước khi hoàn tất. Khi điều đó xảy ra, ứng dụng cần dừng đúng phạm vi, giải phóng tài nguyên tạm và giữ nguyên dữ liệu nghiệp vụ chưa được xác nhận.

Một thao tác hủy giao diện không tự hoàn tác những gì ứng dụng đã ghi vào database, gửi qua mạng hoặc thay đổi trong service. Vì vậy, hãy tách dữ liệu đang nhập khỏi trạng thái đã được chấp nhận, chỉ commit sau khi người dùng hoàn tất và xác nhận, đồng thời thiết kế cleanup cho mọi đường thoát.

Bài này dùng API Spring Shell 3.3.x. Các package minh họa thuộc `org.springframework.shell.component`, `org.springframework.shell.component.flow` và `org.springframework.shell.component.view`; chúng khác package TUI được tổ chức lại trong Spring Shell 4.

## 1. Phân biệt thoát component, dừng flow và thoát shell

Spring Shell 3.x có nhiều lớp tương tác. Mỗi lớp có cách kết thúc riêng:

| Phạm vi | Cơ chế | Kết quả |
|---|---|---|
| Một component nhập liệu hoặc selector | `AbstractComponent.OPERATION_EXIT` | Kết thúc vòng đọc của component hiện tại |
| Một bước trong wizard | Hàm `next(...)` trả `null` hoặc ID không tồn tại | Dừng luồng component tại bước đó |
| Một view đang chạy | `ViewComponent.exit()` | Yêu cầu vòng thực thi view kết thúc |
| Một view chạy bất đồng bộ | `ViewComponentRun.cancel()` | Hủy lần chạy view; có thể chờ và kiểm tra trạng thái bằng `await()` và `isDone()` |
| Một modal view | `TerminalUI.setModal(null)` | Gỡ modal hiện tại khỏi giao diện |
| Toàn bộ phiên Spring Shell | Built-in command `quit` hoặc `exit` | Thoát shell và đi vào quy trình kết thúc ứng dụng |

Không dùng thao tác thoát shell để thay cho việc đóng một dialog hoặc hủy một bước wizard. Tương tự, dừng component không có nghĩa application context hoặc tiến trình JVM phải kết thúc.

## 2. Component cơ bản có thao tác exit

Các component dựng sẵn như `StringInput`, `PathInput`, `ConfirmationInput`, `SingleItemSelector` và `MultiItemSelector` kế thừa cơ chế chung từ `AbstractComponent` hoặc các lớp hỗ trợ của nó.

`AbstractComponent` công bố hằng `OPERATION_EXIT` cùng những operation như `OPERATION_SELECT`, `OPERATION_UP`, `OPERATION_DOWN` và `OPERATION_BACKSPACE`. Component dùng key map để chuyển phím terminal thành operation. Phím cụ thể phụ thuộc key map của component và cấu hình terminal; khi tùy chỉnh phím thoát, hãy kiểm tra binding của đúng component và phiên bản đang dùng.

Có thể chạy một component trực tiếp và nhận context đã cập nhật:

```java
import org.springframework.shell.component.StringInput;
import org.springframework.shell.component.StringInput.StringInputContext;
import org.jline.terminal.Terminal;

class ProjectNamePrompt {

    private final Terminal terminal;

    ProjectNamePrompt(Terminal terminal) {
        this.terminal = terminal;
    }

    String ask() {
        StringInput input = new StringInput(terminal, "Tên dự án", null);
        StringInputContext result = input.run(StringInputContext.empty());

        String projectName = result.getResultValue();
        if (projectName == null || projectName.isBlank()) {
            return null;
        }
        return projectName;
    }
}
```

`run(ComponentContext<?>)` trả về context cụ thể của component. Với `StringInput`, có thể đọc `getResultValue()` để biết giá trị cuối cùng mà component trả về. Không nên mặc định rằng một giá trị rỗng luôn có nghĩa người dùng nhấn hủy: tùy nghiệp vụ, chuỗi rỗng có thể là input hợp lệ hoặc input không hợp lệ. Nếu cần phân biệt rõ, hãy cung cấp lựa chọn hủy riêng hoặc lưu trạng thái quyết định riêng.

Nếu component được tạo với `defaultValue`, hãy kiểm tra cách default value tham gia vào kết quả trước khi dùng `null` làm dấu hiệu hủy. Khi cần phân biệt “chấp nhận giá trị mặc định” và “hủy”, lưu một quyết định riêng thay vì suy luận từ chuỗi kết quả.

`OPERATION_EXIT` là operation của component. Nó không phải command `quit`, không tự đóng `ApplicationContext` và cũng không tự rollback dữ liệu mà ứng dụng đã ghi trước đó.

## 3. Dùng pre-run và post-run handler đúng trách nhiệm

`AbstractComponent` cung cấp `addPreRunHandler(...)` và `addPostRunHandler(...)`. Chúng phù hợp để chuẩn bị hoặc hoàn tất phần trạng thái riêng của component.

```java
import org.springframework.shell.component.StringInput;

StringInput input = new StringInput(terminal, "Tên dự án", null);

input.addPreRunHandler(context -> {
    context.setMessage("Nhập tên rồi nhấn Enter để tiếp tục");
});

input.addPostRunHandler(context -> {
    // Chỉ xử lý trạng thái giao diện hoặc dữ liệu tạm của component.
    // Không lưu dự án vào database tại đây.
});

StringInput.StringInputContext result =
        input.run(StringInput.StringInputContext.empty());
```

Pre-run handler được gọi trước logic chạy component; post-run handler được dùng cho bước xử lý sau khi component chạy. Hãy giữ các handler này ngắn và tránh side effect nghiệp vụ khó hoàn tác.

Nếu cần bảo đảm cleanup khi component ném exception hoặc command bị dừng ở một nhánh lỗi, đặt cleanup ở `finally` tại nơi gọi component:

```java
StringInput.StringInputContext result;
try {
    result = input.run(StringInput.StringInputContext.empty());
} finally {
    clearTemporaryPromptState();
}
```

Ở đây `clearTemporaryPromptState()` chỉ dọn dữ liệu tạm do command sở hữu. Nếu giá trị cần dùng sau khi component kết thúc, giữ nó trong context hoặc biến cục bộ rồi kiểm tra trước khi commit.

## 4. Dừng một flow bằng `next(...)`

Khi có nhiều component liên tiếp, `ComponentFlow` giúp khai báo các bước và thứ tự chạy. Mỗi bước có thể cung cấp hàm `next(...)` để chọn ID của component kế tiếp. Theo API Spring Shell 3.x, nếu hàm trả về `null` hoặc ID không tồn tại, flow dừng tại bước hiện tại.

Ví dụ luồng có điều kiện:

```java
import java.util.Map;

import org.springframework.shell.component.flow.ComponentFlow;

ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withSingleItemSelector("action")
            .name("Chọn thao tác")
            .selectItems(Map.of(
                    "Tạo dự án", "create",
                    "Hủy", "cancel"))
            .next(context -> "create".equals(
                    context.getResultItem().map(item -> item.getItem()).orElse(null))
                    ? "projectName"
                    : null)
            .and()
        .withStringInput("projectName")
            .name("Tên dự án")
            .and()
        .build();
```

Nếu người dùng chọn `cancel`, hàm `next` trả `null` và flow dừng, không chạy bước nhập tên. Nếu chọn `create`, flow chuyển đến component có ID `projectName`.

Dừng flow không đồng nghĩa toàn bộ command bị hủy. Command vẫn nhận được kết quả của flow và cần quyết định xử lý context như thế nào.

## 5. Đọc kết quả flow và nhận biết nhánh hủy

`ComponentFlow.run()` trả về `ComponentFlowResult`. API này cung cấp `getContext()` để đọc kết quả đã được lưu. `ComponentFlowResult` không có phương thức `isCancelled()` riêng, vì vậy ứng dụng nên lưu lựa chọn hoặc trạng thái hoàn tất theo một quy ước rõ ràng.

Các input spec của flow có `storeResult(boolean)`; mặc định là `true`. Khi bật, kết quả component được lưu vào `ComponentContext` bằng ID của component. Có thể đọc giá trị bằng `get(key, type)`.

Ví dụ hoàn chỉnh hơn: người dùng chọn tạo hoặc hủy, nhập tên, rồi xác nhận trước khi ứng dụng gọi service:

```java
import java.util.List;

import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.component.flow.ComponentFlow.ComponentFlowResult;
import org.springframework.shell.component.flow.SelectItem;

// componentFlowBuilder được inject từ Spring context.
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withSingleItemSelector("action")
            .name("Bạn muốn làm gì?")
            .selectItems(List.of(
                    SelectItem.of("Tạo dự án", "create"),
                    SelectItem.of("Hủy", "cancel")))
            .storeResult(true)
            .next(context -> "create".equals(
                    context.getResultItem().map(item -> item.getItem()).orElse(null))
                    ? "projectName"
                    : null)
            .and()
        .withStringInput("projectName")
            .name("Tên dự án")
            .storeResult(true)
            .next(context -> context.getResultValue() != null
                    && !context.getResultValue().isBlank()
                    ? "confirm"
                    : null)
            .and()
        .withConfirmationInput("confirm")
            .name("Xác nhận tạo dự án?")
            .storeResult(true)
            .and()
        .build();

ComponentFlowResult flowResult = flow.run();
ComponentContext<?> values = flowResult.getContext();

String action = values.get("action", String.class);
String projectName = values.get("projectName", String.class);
Boolean confirmed = values.get("confirm", Boolean.class);

if (!"create".equals(action)
        || projectName == null
        || projectName.isBlank()
        || !Boolean.TRUE.equals(confirmed)) {
    return "Đã hủy. Không có dự án nào được tạo.";
}

projectService.create(projectName);
return "Đã tạo dự án " + projectName;
```

Các điểm cần chú ý:

- ID của component (`action`, `projectName`, `confirm`) là key để đọc dữ liệu trong context.
- `next(...)` dừng flow khi người dùng chọn `cancel` hoặc tên dự án rỗng.
- `Boolean.TRUE.equals(confirmed)` chỉ cho phép commit khi người dùng xác nhận rõ ràng.
- `projectService.create(...)` chỉ chạy sau khi đã kiểm tra toàn bộ kết quả.

Nếu nghiệp vụ cho phép tên rỗng, không dùng chuỗi rỗng làm dấu hiệu hủy. Hãy giữ một cờ hoặc lựa chọn hủy riêng để phân biệt “người dùng không nhập” với “người dùng chủ động hủy”.

## 6. Không ghi trạng thái nghiệp vụ trong lúc người dùng đang nhập

Một lỗi thiết kế phổ biến là cập nhật database hoặc state service ngay trong từng bước nhập liệu. Nếu người dùng hủy ở bước cuối, các bước trước đã thay đổi dữ liệu thật và không thể tự hoàn tác chỉ bằng cách dừng flow.

Hãy chia dữ liệu thành hai giai đoạn:

1. **Draft:** dữ liệu tạm trong biến cục bộ, DTO hoặc `ComponentContext`.
2. **Committed:** dữ liệu đã qua validation và được người dùng xác nhận; lúc này mới gọi service ghi dữ liệu.

Ví dụ DTO cho một dự án mới:

```java
record ProjectDraft(String name) {
}
```

Tạo draft từ kết quả flow:

```java
ProjectDraft draft = new ProjectDraft(
        values.get("projectName", String.class));

validate(draft);
projectService.create(draft);
```

Nếu flow kết thúc sớm hoặc xác nhận là `false`, bỏ draft và trả thông báo hủy. Không cần xóa dữ liệu trong database vì chưa có thao tác ghi nào xảy ra.

Với workflow có nhiều bước ghi dữ liệu, đặt thao tác commit trong service có transaction phù hợp. Giao diện chỉ thu thập input và yêu cầu xác nhận; service chịu trách nhiệm bảo vệ invariant nghiệp vụ.

## 7. Dùng `ViewComponent.exit()` để kết thúc vòng lặp view

Spring Shell 3.x có `ViewComponent` để chạy một `View` trong khu vực terminal không toàn màn hình. `runBlocking()` chạy vòng lặp đồng bộ; `exit()` yêu cầu vòng lặp đó kết thúc.

```java
import org.jline.terminal.Terminal;
import org.springframework.shell.component.ViewComponent;
import org.springframework.shell.component.ViewComponentExecutor;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.control.View;

ViewComponent viewComponent = new ViewComponent(
        terminalUI,
        terminal,
        viewComponentExecutor,
        view);

viewComponent.runBlocking();
```

Từ callback của view hoặc thành phần sở hữu vòng lặp, có thể gọi `viewComponent.exit()` khi người dùng chọn Hủy hoặc khi ứng dụng muốn kết thúc view. `exit()` chỉ yêu cầu dừng execution loop của view đó; nó không phải lệnh thoát Spring Shell.

`TerminalUI.run()` là vòng lặp của terminal UI cấp ứng dụng và cũng là thao tác blocking. Nếu chỉ muốn đóng một cửa sổ hoặc modal, hãy đóng đúng view đó thay vì dừng vòng lặp UI gốc.

## 8. Hủy view chạy bất đồng bộ

`ViewComponent.runAsync()` trả về `ViewComponent.ViewComponentRun`. Đối tượng trạng thái này cung cấp:

- `cancel()` để hủy lần chạy component.
- `await()` để chờ component kết thúc.
- `isDone()` để kiểm tra component đã hoàn tất hay chưa.

Ví dụ quản lý vòng đời của một view chạy nền:

```java
import org.jline.terminal.Terminal;
import org.springframework.shell.component.ViewComponent;
import org.springframework.shell.component.ViewComponent.ViewComponentRun;
import org.springframework.shell.component.ViewComponentExecutor;
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.control.AbstractView;
import org.springframework.shell.component.view.control.View;

ViewComponent viewComponent = new ViewComponent(
        terminalUI,
        terminal,
        viewComponentExecutor,
        view);

ViewComponentRun run = viewComponent.runAsync();
try {
    // Thành phần điều phối chờ sự kiện xác nhận hoặc yêu cầu hủy.
    if (cancelRequested()) {
        run.cancel();
    }
    run.await();
} finally {
    if (!run.isDone()) {
        run.cancel();
        run.await();
    }
    if (view instanceof AbstractView abstractView) {
        abstractView.destroy();
    }
}
```

`cancelRequested()` trong ví dụ là hàm của ứng dụng, đại diện cho sự kiện hủy đến từ nút, phím hoặc thành phần điều phối. Không để một vòng lặp chờ vô hạn trong command chính; hãy nối sự kiện hủy với callback hoặc event loop thực tế.

Nếu ứng dụng tự tạo `ViewComponentExecutor`, hãy đóng executor khi không còn view nào dùng nó. `ViewComponentExecutor` triển khai `AutoCloseable`; không đóng executor dùng chung khi một component đơn lẻ kết thúc.

## 9. Gỡ modal mà vẫn giữ màn hình chính

`TerminalUI` hỗ trợ một modal view đang hoạt động. Modal nằm trên các view khác và nhận input. Khi người dùng hủy dialog, gọi `setModal(null)` để xóa modal hiện tại:

```java
terminalUI.setModal(dialogView);

// Khi người dùng chọn Hủy hoặc đóng dialog:
terminalUI.setModal(null);
```

Lệnh này chỉ gỡ modal khỏi giao diện. Nó không tự quyết định dữ liệu draft có được lưu hay không; command/service vẫn phải kiểm tra kết quả trước khi commit.

Nếu dialog là một `AbstractView` có đăng ký subscription hoặc state nội bộ, hãy gọi `destroy()` khi vòng đời view kết thúc để dọn running state. Không xóa root view hoặc dừng `TerminalUI` nếu mục tiêu chỉ là đóng dialog.

## 10. Dọn subscription và tài nguyên theo vòng đời view

View có thể đăng ký nhận sự kiện bàn phím, chuột hoặc message qua `EventLoop`. Các subscription cần được giải phóng khi event loop kết thúc.

Spring Shell 3.x cung cấp `EventLoop.onDestroy(Disposable)` để đăng ký một disposable được dispose khi event loop chấm dứt.

```java
import reactor.core.Disposable;

Disposable keySubscription = eventLoop.keyEvents()
        .subscribe(event -> handleKey(event));

eventLoop.onDestroy(keySubscription);
```

Với view kế thừa `AbstractView`, có thể dùng `onDestroy(Disposable)` của view để gắn cleanup vào vòng đời view:

```java
import org.springframework.shell.component.view.control.AbstractView;
import reactor.core.Disposable;

@Override
protected void initInternal() {
    Disposable subscription = getEventLoop().keyEvents()
            .subscribe(this::handleKey);
    onDestroy(subscription);
}
```

Khi view bị destroy, subscription được dispose theo lifecycle đã đăng ký. Cách này tránh listener cũ tiếp tục nhận sự kiện sau khi người dùng đã đóng dialog hoặc chuyển sang view khác.

Không đăng ký subscription mới mỗi lần redraw. Hãy đăng ký trong giai đoạn khởi tạo view và gắn cleanup ngay khi tạo subscription.

## 11. Hủy giao diện không đồng nghĩa hủy side effect bên ngoài

Nếu command đã gửi HTTP request, ghi file hoặc cập nhật database trước khi người dùng hủy view, việc dừng component không tự thu hồi side effect đó.

Hãy phân loại hành động:

| Hành động | Hủy trước khi commit | Hủy sau khi đã thực hiện |
|---|---|---|
| Nhập tên trong `StringInput` | Bỏ giá trị draft | Không ảnh hưởng dữ liệu nghiệp vụ nếu chưa lưu |
| Chọn mục trong selector | Bỏ lựa chọn tạm | Không tự hoàn tác thao tác đã gọi service |
| Tạo file tạm | Xóa file tạm trong cleanup | Xóa hoặc giữ file theo chính sách phục hồi |
| Gửi request tới hệ thống từ xa | Có thể hủy nếu request chưa được gửi | Cần kiểm tra trạng thái hoặc gọi API bù trừ |
| Ghi database | Không ghi trước xác nhận | Dùng transaction hoặc thao tác bù phù hợp |

Đối với tác vụ bất đồng bộ, truyền cancellation signal xuống service hoặc API client nếu thư viện hỗ trợ. Việc hủy một `ViewComponentRun` không tự động hủy mọi task mà view đã khởi chạy bên ngoài.

Nếu request từ xa đã được gửi, client có thể chỉ ngừng chờ kết quả trong khi server vẫn hoàn tất thao tác. Hãy dùng request ID, idempotency key hoặc cơ chế kiểm tra trạng thái để tránh hiểu nhầm rằng “đã hủy giao diện” đồng nghĩa “thao tác đã bị hủy trên server”.

## 12. Phân biệt hủy, từ chối và lỗi

Ba trạng thái này nên có ý nghĩa riêng:

| Trạng thái | Ý nghĩa | Xử lý |
|---|---|---|
| `CANCELLED` | Người dùng chủ động rời thao tác | Bỏ draft, dọn tài nguyên tạm và trả về command trước |
| `DECLINED` | Người dùng đã trả lời câu hỏi xác nhận bằng Không | Không commit; hiển thị kết quả từ chối rõ ràng |
| `FAILED` | Component hoặc nghiệp vụ gặp lỗi | Hiển thị thông báo lỗi, log diagnostics và cleanup |
| `COMPLETED` | Người dùng hoàn tất và dữ liệu hợp lệ | Commit một lần rồi hiển thị kết quả |

Không bắt mọi exception rồi coi như người dùng hủy. Lỗi đọc file, lỗi kết nối hoặc lỗi lập trình cần được ghi nhận như lỗi thực thi để có thể chẩn đoán.

Một enum có thể giúp mô hình hóa kết quả:

```java
enum InteractionStatus {
    COMPLETED,
    CANCELLED,
    DECLINED,
    FAILED
}
```

Kết quả của command có thể chứa status cùng dữ liệu draft. Chỉ status `COMPLETED` mới được phép đi tới bước commit.

## 13. Xử lý hủy nhiều bước và điều hướng quay lại

Với flow dài, người dùng có thể muốn quay lại bước trước thay vì hủy toàn bộ. Hãy phân biệt ba hành động:

- **Back:** quay về bước trước và giữ draft hiện tại nếu còn hợp lệ.
- **Cancel:** dừng flow và bỏ toàn bộ draft.
- **Confirm:** chấp nhận draft và chuyển sang bước commit.

`next(...)` điều khiển ID của component tiếp theo. Có thể dùng ID component trước để tạo nhánh quay lại, hoặc trả `null` để dừng flow. Nếu cần giữ draft khi quay lại, lưu kết quả ở `ComponentContext` và chỉ ghi đè khi người dùng nhập lại.

Đừng dùng một giá trị `null` cho cả Back và Cancel nếu nghiệp vụ cần phân biệt hai hành động. Hãy có lựa chọn rõ ràng trong selector hoặc trạng thái điều hướng riêng.

Ví dụ sơ đồ:

```text
       [Nhập tên]
            |
            v
       [Chọn thao tác]
        /    |     \
       /     |      \
    Back   Cancel   Continue
     |       |         |
     v       v         v
 [Nhập tên] [Dừng]  [Xác nhận]
                        |
                  +-----+-----+
                  |           |
                 No          Yes
                  |           |
               [Dừng]      [Commit]
```

## 14. Kiểm thử các đường thoát

Đừng chỉ kiểm thử trường hợp người dùng hoàn tất form. Cần xác nhận cả việc dừng giữa chừng và cleanup.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Thoát ở component đầu tiên | Flow dừng, không gọi service commit |
| Chọn mục Hủy trong selector | `next` dừng flow; context được kiểm tra trước khi dùng |
| Để trống trường bắt buộc | Không đi tới bước tiếp theo hoặc commit |
| Từ chối confirmation | Không gọi service tạo/cập nhật |
| Hủy modal | Modal được gỡ, root view vẫn hoạt động |
| Gọi `ViewComponent.exit()` | Vòng lặp view kết thúc, command/shell vẫn tiếp tục |
| Gọi `ViewComponentRun.cancel()` | Run được hủy và trạng thái hoàn tất được kiểm tra |
| Exception trong component | Cleanup chạy và lỗi được báo đúng trạng thái |
| Event loop kết thúc | Subscription đã đăng ký được dispose |
| Hủy sau khi gửi request | Có kiểm tra trạng thái hoặc phương án bù nếu server đã thực hiện |

Với phần nghiệp vụ, kiểm thử riêng service điều phối bằng mock để xác nhận service commit không được gọi khi trạng thái là `CANCELLED` hoặc `DECLINED`:

```java
if (interactionStatus != InteractionStatus.COMPLETED) {
    return "Thao tác đã dừng; dữ liệu chưa được lưu.";
}

projectService.create(draft);
```

Với phần giao diện, dùng terminal test harness hoặc integration test phù hợp với phiên bản Spring Shell để gửi chuỗi phím và xác nhận component dừng. Kiểm thử thêm trường hợp view bị hủy khi đang có subscription hoặc tác vụ nền.

## 15. Bài tập thực hành

Xây dựng wizard tạo môi trường triển khai với các bước:

1. Nhập tên môi trường.
2. Chọn vùng triển khai.
3. Chọn cấu hình tài nguyên.
4. Xác nhận trước khi tạo môi trường.

Yêu cầu:

- Cho phép hủy ở từng bước.
- Có thể quay lại bước trước mà không mất các giá trị draft còn hợp lệ.
- Khi chọn Hủy hoặc trả lời Không, không gọi service tạo môi trường.
- Chỉ gọi service sau khi toàn bộ dữ liệu hợp lệ và người dùng xác nhận Có.
- Nếu dùng `ViewComponent`, đóng view và dispose subscription khi kết thúc.
- Nếu tác vụ tạo môi trường đã gửi request từ xa, lưu request ID để tra cứu kết quả khi người dùng rời giao diện.
- Kiểm thử hoàn tất, hủy ở từng bước, từ chối xác nhận, exception và cleanup.

**Kết quả cần nộp:** flow builder, DTO draft, service commit, sơ đồ trạng thái, các ca kiểm thử và log chứng minh không có side effect khi hủy trước commit.

## 16. Checklist trước khi phát hành component tương tác

- [ ] Đã phân biệt component exit, flow stop, view exit/cancel và shell quit.
- [ ] Đã biết operation `OPERATION_EXIT` và key map của component đang dùng.
- [ ] Không giả định `ComponentFlowResult` có cờ `isCancelled()`.
- [ ] Flow có nhánh hủy rõ ràng và kiểm tra context sau khi chạy.
- [ ] Giá trị `null`, rỗng và giá trị mặc định được phân biệt theo nghiệp vụ.
- [ ] Dữ liệu người dùng nhập được giữ trong draft cho đến khi xác nhận.
- [ ] Chỉ commit sau validation và confirmation thành công.
- [ ] `ViewComponent.exit()` hoặc `ViewComponentRun.cancel()` được dùng đúng phạm vi.
- [ ] Modal được gỡ mà không dừng root UI khi chỉ cần đóng dialog.
- [ ] Event subscription và view state được dọn khi component kết thúc.
- [ ] Executor chỉ được đóng bởi thành phần sở hữu nó.
- [ ] Cancellation signal được truyền xuống task nền nếu cần.
- [ ] Không giả định hủy UI sẽ rollback request, file hoặc database đã ghi.
- [ ] Đã kiểm thử mọi điểm có thể hủy, exception và cleanup.

## Tài liệu tham khảo

- [Spring Shell 3.3 — Flow Components](https://docs.spring.io/spring-shell/reference/3.3/components/ui/index.html)
- [Spring Shell 3.3 — Flow](https://docs.spring.io/spring-shell/reference/3.3/components/flow/index.html)
- [Spring Shell 3.3 — Component Render](https://docs.spring.io/spring-shell/reference/3.3/components/ui/render.html)
- [Spring Shell 3.3 API — `AbstractComponent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/support/AbstractComponent.html)
- [Spring Shell 3.3 API — `ComponentFlow.ComponentFlowResult`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html)
- [Spring Shell 3.3 API — `ComponentContext`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/context/ComponentContext.html)
- [Spring Shell 3.3 API — `ViewComponent`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponent.html)
- [Spring Shell 3.3 API — `ViewComponent.ViewComponentRun`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponent.ViewComponentRun.html)
- [Spring Shell 3.3 API — `ViewComponentExecutor`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/ViewComponentExecutor.html)
- [Spring Shell 3.3 API — `TerminalUI`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUI.html)
- [Spring Shell 3.3 API — `EventLoop`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/event/EventLoop.html)
- [Spring Shell 3.3 API — `AbstractView`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/AbstractView.html)
- [Spring Shell 3.3 API — `SingleItemSelectorSpec`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/SingleItemSelectorSpec.html)
- [Spring Shell 3.3 API — `ConfirmationInputSpec`](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ConfirmationInputSpec.html)
