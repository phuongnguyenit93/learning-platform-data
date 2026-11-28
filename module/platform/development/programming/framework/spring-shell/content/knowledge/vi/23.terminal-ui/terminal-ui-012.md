# Đối chiếu khả năng hỗ trợ trước khi chuyển giao diện sang thế hệ mới

Spring Shell 3.x cung cấp bộ Terminal UI dựa trên JLine để xây dựng màn hình console có layout, view lồng nhau, sự kiện bàn phím/chuột, hộp thoại, danh sách và thanh trạng thái. Spring Shell 4.x tiếp tục cung cấp các khái niệm này, nhưng chuyển chúng sang module và package mới, thay đổi cách phụ thuộc JLine, đồng thời đánh dấu Terminal UI là tính năng experimental.

Vì vậy, chuyển từ 3.x sang 4.x không chỉ là đổi import. Trước khi chuyển, cần kiểm tra ứng dụng đang dùng loại giao diện nào, API nào, terminal provider nào, dependency nào và cách kiểm thử nào. Kết quả đối chiếu sẽ cho biết phần nào có thể giữ nguyên về hành vi, phần nào phải sửa mã và phần nào cần kiểm thử lại trên terminal thật.

## Phân biệt các lớp giao diện trong Spring Shell

Spring Shell có nhiều API cùng phục vụ tương tác nhưng giải quyết những bài toán khác nhau:

| API | Mục đích | Ví dụ |
|---|---|---|
| Command line và output writer | Nhận command/option, in kết quả theo dòng | `customer-list`, `CommandContext.outputWriter()` |
| Component đơn | Hỏi một giá trị hoặc chọn một mục | `StringInput`, `PathInput`, `ConfirmationInput`, `SingleItemSelector` |
| `ComponentFlow` | Ghép nhiều component thành wizard tuần tự hoặc có nhánh | Form triển khai gồm môi trường, phiên bản và xác nhận |
| `TerminalUI` và `View` | Xây dựng màn hình TUI có layout, focus, event loop, modal và redraw | Dashboard, menu điều hướng, màn hình quản lý tài nguyên |
| Table API | Render dữ liệu theo hàng/cột | Danh sách khách hàng hoặc trạng thái dịch vụ |

`ComponentFlow` là wizard hỏi dữ liệu theo từng bước. `TerminalUI` điều phối một giao diện view có event loop và vùng vẽ màn hình. Một ứng dụng có thể dùng cả hai, nhưng không nên coi chúng là cùng một API. Khi kiểm kê trước migration, hãy tìm riêng `ComponentFlow`, `TerminalUI`, `ViewComponent`, `View`, `EventLoop`, `Screen` và table classes.

## Mức hỗ trợ theo thế hệ

| Hạng mục | Spring Shell 3.3.x/3.4.x | Spring Shell 4.0.x |
|---|---|---|
| Terminal UI framework | Có `TerminalUI`, `TerminalUIBuilder`, `View`, `EventLoop`, `Screen` và các view dựng sẵn | Vẫn có các khái niệm tương ứng; package chuyển sang `org.springframework.shell.jline.tui.*` |
| View dựng sẵn | `AppView`, `BoxView`, `ButtonView`, `DialogView`, `GridView`, `InputView`, `ListView`, `MenuBarView`, `MenuView`, `ProgressView`, `StatusBarView`, `WindowView` | API 4.0.x vẫn liệt kê các view này |
| Event | Key, mouse, signal, system, task, user và view events | Vẫn có `EventLoop`, `keyEvents()`, `mouseEvents()`, `signalEvents()` và `viewEvents()` |
| ComponentFlow | String, path, confirmation, single selector và multi selector | Các component tiếp tục có; API 4.0.x bổ sung `NumberInput`/`NumberInputSpec` |
| Table | Module `spring-shell-table`, package `org.springframework.shell.table` | Table API được gộp vào `spring-shell-jline`, package `org.springframework.shell.jline.tui.table` |
| JLine dependency | Có trong mô hình dependency 3.x của shell | Không còn là dependency của `spring-shell-core`; thêm `spring-shell-jline` nếu cần JLine/TUI |
| Mức ổn định được tài liệu công bố | Tài liệu 3.4.3 mô tả UI framework và API | Tài liệu 4.0.4 đánh dấu Terminal UI là experimental, có thể có breaking change |

Ma trận này mô tả khả năng có mặt ở cấp API. Nó không bảo đảm mọi hành vi render, key binding, resize hoặc terminal provider sẽ giống hệt giữa hai phiên bản. Cần kiểm tra lại trên terminal và dependency thực tế của ứng dụng.

## Kiểm tra điều kiện nền trước khi chuyển

Spring Shell 4.x dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên khi tích hợp với Spring Boot. Hãy nâng ứng dụng lên phiên bản Spring Shell 3.4.x mới nhất trước khi bắt đầu migration, sau đó mới nâng nền Spring Boot/Framework và Spring Shell.

Một số thay đổi dependency quan trọng:

| Thành phần | 3.x | 4.x |
|---|---|---|
| Spring Boot integration | `spring-shell-autoconfigure` và starter theo phiên bản | `spring-shell-core-autoconfigure` hoặc Spring Shell starter |
| JLine | Được kéo vào theo cấu hình/module của 3.x | `spring-shell-core` không phụ thuộc JLine; thêm `spring-shell-jline` để dùng JLine shell và TUI |
| Table | Module `spring-shell-table` | Được gộp vào `spring-shell-jline` |
| Standard commands | Có module `spring-shell-standard`/`spring-shell-standard-commands` | Được gộp vào `spring-shell-core` |
| Framework baseline | Spring Framework 6 trong dòng Boot 3 tương ứng | Spring Framework 7, Spring Boot 4+ |

Nếu ứng dụng dùng Spring Boot starter, hãy kiểm tra dependency tree để biết starter đang kéo vào runner và JLine nào. Nếu ứng dụng tự cấu hình context hoặc dùng core module trực tiếp, cần khai báo rõ module hỗ trợ Boot và JLine. `TerminalUI` nhận `org.jline.terminal.Terminal`; nếu thiếu JLine module, việc chỉ nâng `spring-shell-core` sẽ không đủ để biên dịch hoặc chạy giao diện dựa trên JLine.

Ví dụ dependency cho ứng dụng Spring Boot 4 chọn starter có JLine provider Jansi:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter-jansi</artifactId>
    </dependency>
</dependencies>
```

Nếu tự ghép module, dùng `spring-shell-core-autoconfigure` cùng `spring-shell-jline` và các dependency Boot cần thiết. Các starter `spring-shell-starter-jansi`, `spring-shell-starter-jni`, `spring-shell-starter-jna` và `spring-shell-starter-ffm` chọn JLine terminal provider tương ứng; `ffm` yêu cầu JDK 22+. Đây là ví dụ về cách chọn starter, không phải một BOM hoàn chỉnh. Dùng Spring Shell BOM hoặc dependency management tương ứng để giữ cùng phiên bản cho các module. Xác nhận dependency thực tế bằng `mvn dependency:tree` hoặc `gradle dependencies`.

## Đối chiếu package API

Các lớp giao diện quen thuộc vẫn tồn tại trong API 4.x, nhưng package được chuyển sang nhánh `org.springframework.shell.jline.tui`. Bảng sau giúp tìm import cần sửa:

| Thành phần | Package 3.x | Package 4.x |
|---|---|---|
| `TerminalUI`, `TerminalUIBuilder`, `TerminalUICustomizer` | `org.springframework.shell.component.view` | `org.springframework.shell.jline.tui.component.view` |
| `View`, `AbstractView`, `BoxView`, `DialogView`, `GridView`, `ListView`, `AppView` | `org.springframework.shell.component.view.control` | `org.springframework.shell.jline.tui.component.view.control` |
| `EventLoop`, `KeyEvent`, `MouseEvent`, `ViewEvent` | `org.springframework.shell.component.view.event` | `org.springframework.shell.jline.tui.component.view.event` |
| `Screen`, `DefaultScreen`, `ScreenItem` | `org.springframework.shell.component.view.screen` | `org.springframework.shell.jline.tui.component.view.screen` |
| `ViewComponent`, `ViewComponentBuilder`, `ViewComponentExecutor` | `org.springframework.shell.component` | `org.springframework.shell.jline.tui.component` |
| `ComponentFlow`, `ComponentFlow.Builder`, các input specs | `org.springframework.shell.component.flow` | `org.springframework.shell.jline.tui.component.flow` |
| `ComponentContext` | `org.springframework.shell.component.context` | `org.springframework.shell.jline.tui.component.context` |
| `Table`, `TableModel`, `TableBuilder` | `org.springframework.shell.table` | `org.springframework.shell.jline.tui.table` |

Không thay mọi chuỗi `org.springframework.shell.component` bằng `org.springframework.shell.jline.tui.component` một cách máy móc. Trước tiên hãy xác nhận class đó thuộc API TUI/JLine trong Javadoc 4.x. Những API command/core có package chuyển đổi riêng, ví dụ `org.springframework.shell.core.*`.

### Ví dụ đổi import cho TerminalUI

Trong 3.x:

```java
import org.springframework.shell.component.view.TerminalUI;
import org.springframework.shell.component.view.TerminalUIBuilder;
import org.springframework.shell.component.view.control.BoxView;
```

Trong 4.x:

```java
import org.springframework.shell.jline.tui.component.view.TerminalUI;
import org.springframework.shell.jline.tui.component.view.TerminalUIBuilder;
import org.springframework.shell.jline.tui.component.view.control.BoxView;
```

Mô hình khởi tạo vẫn tương tự: lấy `TerminalUIBuilder`, tạo `TerminalUI`, cấu hình view, đặt root view rồi chạy event loop. Ví dụ dùng builder được auto-configure:

```java
@Autowired
TerminalUIBuilder builder;

void showDashboard() {
    TerminalUI ui = builder.build();
    BoxView root = new BoxView();
    ui.configure(root);
    ui.setRoot(root, true);
    ui.run();
}
```

Đổi package import theo phiên bản đang build. `ui.run()` là thao tác blocking; cần thiết kế một đường thoát rõ ràng, chẳng hạn xử lý phím tắt và dispatch interrupt event. Không khởi chạy event loop trên thread mà ứng dụng còn cần dùng để xử lý tác vụ nền hoặc phục vụ command khác.

### Ví dụ đổi import cho ComponentFlow

Trong 3.x:

```java
import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow;
```

Trong 4.x:

```java
import org.springframework.shell.jline.tui.component.context.ComponentContext;
import org.springframework.shell.jline.tui.component.flow.ComponentFlow;
```

Các bước builder như `clone()`, `reset()`, `withStringInput()`, `withPathInput()`, `withConfirmationInput()` và `withSingleItemSelector()` vẫn có trong API 4.x. API 4.0.x còn có `withNumberInput()`. Hãy kiểm tra type kết quả, nullability và validator của từng component sau khi đổi import; không chỉ dựa vào việc tên method vẫn tồn tại.

## Đối chiếu chức năng view và event

Trước migration, lập danh sách tính năng UI đang dùng và xác nhận API tương ứng trong Javadoc 4.x:

| Chức năng đang dùng | API 3.x | Đối chiếu ở 4.x |
|---|---|---|
| Màn hình gốc và vùng hiển thị | `TerminalUI.setRoot(view, fullScreen)` | `TerminalUI.setRoot(...)` vẫn có |
| Cấu hình tích hợp view | `TerminalUI.configure(view)` | Vẫn có `configure(View)` |
| Event loop | `TerminalUI.getEventLoop()` | Vẫn có `getEventLoop()` |
| Sự kiện bàn phím | `EventLoop.keyEvents()` | Vẫn có `keyEvents()` |
| Sự kiện chuột | `EventLoop.mouseEvents()` | Vẫn có `mouseEvents()` |
| Modal | `setModal(view)`/`setModal(null)` | Vẫn có modal view và `ViewService` |
| Focus | `setFocus(view)` | Vẫn có `setFocus(View)` |
| Vẽ lại màn hình | `TerminalUI.redraw()` | Vẫn có `redraw()` |
| Render nội dung | `Screen`, `Screen.Writer`, `writerBuilder()` | Các khái niệm vẫn có trong package screen mới |
| Chạy view không fullscreen | `ViewComponent.runBlocking()`/`runAsync()` trong các API 3.x tương ứng | `ViewComponent` và builder được chuyển package; kiểm tra lại lifecycle và executor |

Các view dựng sẵn như `AppView`, `BoxView`, `ButtonView`, `DialogView`, `GridView`, `InputView`, `ListView`, `MenuBarView`, `MenuView`, `ProgressView`, `StatusBarView` và `WindowView` vẫn xuất hiện trong API 4.x. Nếu ứng dụng dùng view tự viết kế thừa `AbstractView`, hãy kiểm tra cả phương thức vẽ, xử lý key/mouse, focus, event registration và các phương thức protected được override.

## Khác biệt cần xử lý ngoài package

### Nullability và JSpecify

Spring Shell 4 bổ sung null-safety annotations. Một số API 4.x khai báo giá trị nullable rõ ràng hơn. Ví dụ `Screen.clip(x, y, width, height)` trong API 3.x khai báo trả về `Screen`, còn API 4.x khai báo `@Nullable Screen`. Code migration cần xử lý trường hợp không có vùng clip hợp lệ:

```java
Screen clipped = screen.clip(x, y, width, height);
if (clipped != null) {
    drawContent(clipped);
}
```

Không dùng `@SuppressWarnings` để bỏ qua toàn bộ cảnh báo nullability. Kiểm tra từng API mà custom view gọi, nhất là `Screen`, modal, focus, theme resolver, view service và các giá trị lấy từ component context.

### ComponentFlow có thêm NumberInput

Trong Javadoc `ComponentFlow.Builder` của Spring Shell 3.4.3, các builder được liệt kê gồm string, path, confirmation, single selector và multi selector. API 4.0.x có thêm `NumberInputSpec` và `withNumberInput()`. Nếu form hiện tại dùng `StringInput` để nhập số, có thể đánh giá chuyển sang number input sau khi migration; cần kiểm tra `numberClass`, default value, required state, parsing và validation để bảo đảm không thay đổi hợp đồng dữ liệu.

### Maturity của Terminal UI

Tài liệu Spring Shell 4.0.4 đánh dấu Terminal UI là experimental và nêu rõ có thể có breaking changes khi nền tảng tiếp tục hoàn thiện. Do đó:

- Không xem việc package đã có trong Javadoc là cam kết API ổn định dài hạn.
- Khóa phiên bản Spring Shell và JLine trong dependency management.
- Theo dõi release notes khi nâng patch/minor.
- Giữ test cho custom view và event handling để phát hiện thay đổi hành vi.
- Nếu UI là đường đi quan trọng của sản phẩm, cân nhắc một lớp adapter nội bộ để giảm số nơi phụ thuộc trực tiếp vào API TUI.

## Chọn shell runner phù hợp với TUI

Trong Spring Shell 4, `spring-shell-core` mặc định dùng Java `Console` và không kéo JLine. `SystemShellRunner` cung cấp chức năng shell cơ bản, nhưng không có các tính năng nâng cao như history, Tab completion và rich text formatting. `JLineShellRunner` cần `spring-shell-jline` và phù hợp khi ứng dụng dùng Terminal UI dựa trên JLine.

| Runner | Dependency | Khả năng |
|---|---|---|
| `SystemShellRunner` | Java Console, không cần JLine | Shell cơ bản; không có history, completion và rich text nâng cao |
| `JLineShellRunner` | `spring-shell-jline` | JLine input, history, completion, rich terminal features và TUI |
| `NonInteractiveShellRunner` | Không cần REPL tương tác | Chạy command từ process arguments rồi kết thúc |

Spring Shell 4 yêu cầu chọn shell mode từ lúc khởi động; mặc định là interactive và có thể tắt bằng `spring.shell.interactive.enabled=false`. Các command không còn gắn `InteractionMode`; enum `InteractionMode` của 3.x đã bị loại bỏ. Nếu ứng dụng đang dựa vào `@ShellMethod(interactionMode=...)` hoặc kiểm tra `InteractionMode` để quyết định có mở TUI, phải thiết kế lại theo mode của shell và khả năng terminal ở entry point phù hợp.

Nếu command mở TUI đang dùng annotation legacy `@ShellComponent`, `@ShellMethod` hoặc `@ShellOption`, cần chuyển sang command annotations mới `@Command`, `@Option` và `@Argument` trong `org.springframework.shell.core.command.annotation`; các annotation legacy đã bị loại bỏ trong 4.x.

Không khởi chạy full-screen TUI khi ứng dụng đang ở non-interactive mode hoặc output bị pipe. Với đường chạy tự động, cung cấp command options, file cấu hình hoặc output dạng máy đọc thay vì gọi `TerminalUI.run()`.

## Kiểm tra table và output cùng TUI

Nếu màn hình sử dụng table renderer, đổi module và package cùng lúc:

```java
// 3.x
import org.springframework.shell.table.Table;
import org.springframework.shell.table.TableModel;
```

```java
// 4.x
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableModel;
```

Trong 4.x, table module được gộp vào `spring-shell-jline`. Xác nhận formatter, sizing, wrapping, Unicode display width và màu trong terminal thật. Một bảng render đúng trong `Screen` giả lập chưa bảo đảm giống nhau trên Windows Terminal, macOS Terminal, SSH hoặc Docker PTY.

## Kiểm thử sau migration

Migration guide 4.x liệt kê một số test APIs cũ đã bị loại bỏ, gồm `ShellWriteSequence`, `ShellTypeExcludeFilter`, `SpringShellTestProperties`, `@AutoConfigureShell` và `@AutoConfigureShellTestClient`. Hãy kiểm tra test support hiện tại của 4.x và thay thế test harness đã bị remove; không giữ các import 3.x chỉ vì production code đã biên dịch.

Ma trận kiểm thử tối thiểu:

| Nhóm | Kiểm thử | Tiêu chí đạt |
|---|---|---|
| Dependency | Build với Spring Boot 4/Framework 7 và dependency tree | Không thiếu hoặc trộn phiên bản core/JLine |
| Khởi tạo | `TerminalUIBuilder.build()` và `configure(view)` | View được gắn event loop, theme và view service |
| Layout | Root view fullscreen và non-fullscreen | Không vỡ bố cục ở terminal hẹp/rộng |
| Navigation | Key bindings, focus, menu, list selection | Phím điều hướng và focus đúng |
| Modal | Mở/đóng `DialogView` hoặc modal view | Modal nhận input, đóng xong trả focus về view đúng |
| Event loop | Key, mouse, signal, redraw và interrupt | Không mất event, không treo khi thoát |
| Rendering | Screen writer, border, text, theme và color | Không lộ escape sequence, không lệch Unicode |
| Resize | Thu nhỏ/phóng to terminal trong lúc chạy | View được bố trí lại đúng |
| ComponentFlow | Mỗi input type, default, required, validation, result context | Giá trị trả về giữ đúng kiểu và semantics |
| Table | Sort, sizing, wrapping, empty/null values | Bảng đúng trên các kích thước terminal mục tiêu |
| Non-interactive | Chạy command với stdin/stdout không phải TTY | Không mở event loop hoặc chờ phím |
| Exit/lifecycle | Thoát qua phím tắt, signal và exception | Terminal được khôi phục; thread/event loop kết thúc |

Ngoài test tự động, chạy acceptance test trên terminal thật. Kiểm tra ít nhất một môi trường Windows và một môi trường POSIX nếu sản phẩm hỗ trợ cả hai; thử SSH/Docker khi người dùng chạy CLI trong container hoặc remote session.

## Quy trình quyết định chuyển đổi

1. Xác định ứng dụng đang dùng `ComponentFlow`, `TerminalUI`/`ViewComponent`, table hay chỉ command output.
2. Lập danh sách package/import và các class custom kế thừa `AbstractView` hoặc dùng `EventLoop`.
3. Xác nhận target Spring Boot 4+, Spring Framework 7 và Java baseline của ứng dụng.
4. Nâng ứng dụng lên Spring Shell 3.4.x mới nhất và chạy lại test hiện có để có baseline.
5. Chọn dependency 4.x: core/autoconfigure hoặc starter, thêm `spring-shell-jline` nếu cần JLine/TUI.
6. Đổi package theo mapping; kiểm tra riêng ComponentFlow, ComponentContext, ViewComponent và Table.
7. Sửa nullability, lifecycle, shell runner và mọi phụ thuộc `InteractionMode`.
8. Cập nhật test harness đã bị loại bỏ và thêm test cho event loop, resize, modal, key/mouse và non-interactive mode.
9. Chạy acceptance test trên terminal thật, kiểm tra output và process exit.
10. Chỉ phát hành khi dependency, TUI behavior và fallback non-interactive đều đạt yêu cầu.

## Tiêu chí go/no-go

| Điều kiện | Quyết định |
|---|---|
| Ứng dụng cần full-screen views, event loop hoặc JLine rich terminal | Có cơ sở để dùng `spring-shell-jline` và đánh giá TUI 4.x |
| Chỉ dùng command, output writer và bảng đơn giản | Có thể chuyển core/command trước; chưa cần xây full-screen TUI |
| Chưa thể nâng Spring Boot lên 4/Framework 7 | Chưa thể chuyển Spring Shell 4; giữ phiên bản 3.x tương thích |
| Dùng custom view nhiều và không có test terminal | Chưa nên phát hành migration cho tới khi bổ sung test |
| Cần API TUI ổn định tuyệt đối và không chấp nhận breaking changes | Đánh giá rủi ro experimental của TUI 4.x trước khi cam kết |
| Dependency tree không có `spring-shell-jline` nhưng code dùng `TerminalUI`/JLine | Chưa đạt; bổ sung module phù hợp hoặc chọn runner khác |

Không cần chuyển toàn bộ command sang giao diện full-screen chỉ vì đã nâng framework. Hãy giữ đúng mức UI mà người dùng cần và chỉ chuyển các capability có giá trị rõ ràng. Nếu chọn Terminal UI 4.x, hãy xem nó là một phần cần quản lý rủi ro phiên bản, dependency và kiểm thử riêng.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy `TerminalUI` sau nâng cấp | Import vẫn dùng package 3.x | Chuyển sang `org.springframework.shell.jline.tui.component.view` |
| Không tìm thấy `ComponentFlow` hoặc `ComponentContext` | Package flow/context đã chuyển | Dùng package `org.springframework.shell.jline.tui.component.flow` và `.context` |
| Không tìm thấy `Table` | Module/package table đã đổi | Thêm `spring-shell-jline`, đổi import sang `.jline.tui.table` |
| Không có bean `TerminalUIBuilder` hoặc thiếu JLine Terminal | Core không còn kéo JLine | Kiểm tra dependency tree và thêm `spring-shell-jline` |
| History/completion biến mất | Ứng dụng chạy `SystemShellRunner` | Chọn `JLineShellRunner` và cung cấp JLine module |
| Lỗi biên dịch khi dùng `InteractionMode` | Enum đã bị loại bỏ trong 4.x | Chọn shell mode khi khởi động và thiết kế lại command theo mode đó |
| Cảnh báo hoặc lỗi nullability ở `Screen.clip()` | API 4.x trả nullable | Kiểm tra `null` trước khi dùng screen đã clip |
| ComponentFlow nhập số không biên dịch trên 3.4.3 | `withNumberInput()` chưa có trong builder 3.4.3 | Dùng input hiện có hoặc chỉ dùng `NumberInput` sau khi nâng lên 4.x |
| TUI hiển thị khác trên terminal người dùng | Capability, font, Unicode, terminal width hoặc JLine version khác | Kiểm thử terminal thật và điều chỉnh fallback/layout |
| Test không biên dịch sau nâng cấp | Test API 3.x đã bị remove | Dùng test support 4.x và viết lại test sequence/session |
| TUI không thoát hoặc giữ terminal ở trạng thái lạ | Event loop không được interrupt/cleanup | Xử lý đường thoát, signal và lifecycle của view/event loop |

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — Terminal UI Appendix](https://docs.spring.io/spring-shell/reference/3.4/appendices/tui/index.html): giới thiệu UI framework và view development trong dòng 3.4.x.
- [Spring Shell 3.3.0 API — TerminalUI](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/TerminalUI.html): event loop, root view, modal, focus, redraw và chạy UI.
- [Spring Shell 3.3.0 API — View](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/control/View.html): hợp đồng view và các handler.
- [Spring Shell 3.3.0 API — EventLoop](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/view/event/EventLoop.html): key, mouse, signal, system và view events.
- [Spring Shell 3.4.3 API — ComponentFlow.Builder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.Builder.html): các input builder trong 3.4.3.
- [Spring Shell 4.0.4 — Terminal UI](https://docs.spring.io/spring-shell/reference/tui/index.html): TUI framework và trạng thái experimental.
- [Spring Shell 4.0.3 API — TerminalUI](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/view/TerminalUI.html): API điều phối terminal, event loop và views trong 4.x.
- [Spring Shell 4.0.3 API — TerminalUIBuilder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/view/TerminalUIBuilder.html): build/configure TerminalUI và áp dụng customizers/theme.
- [Spring Shell 4.0.3 API — EventLoop](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/view/event/EventLoop.html): API sự kiện trong package mới.
- [Spring Shell 4.0.3 API — Screen](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/view/screen/Screen.html): screen, cursor, resize, clip và writer.
- [Spring Shell 4.0.3 API — ComponentFlow.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/flow/ComponentFlow.BaseBuilder.html): các builder input và `NumberInput` trong 4.x.
- [Spring Shell 4.0.3 API — View package](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/view/control/package-summary.html): danh sách view dựng sẵn trong 4.x.
- [Spring Shell 4.0.3 — Building](https://docs.spring.io/spring-shell/reference/building.html): danh sách starter và JLine terminal providers (`jansi`, `jni`, `jna`, `ffm`).
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): baseline Boot/Framework, module split, JLine dependency, runner, command interactivity, test API và package migration.
