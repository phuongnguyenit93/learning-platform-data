# Đánh giá phương án thay thế cho các thành phần UI không được nhánh mới hỗ trợ

Khi nâng một ứng dụng Spring Shell lên nhánh mới, một thành phần giao diện có thể không còn biên dịch vì package đã chuyển, module đã tách hoặc dependency terminal không còn được kéo vào tự động. Một số thành phần khác vẫn tồn tại nhưng chỉ hoạt động khi chọn runner và module phù hợp. Cũng có trường hợp API mới thay thế một giao diện cũ bằng mô hình khác, hoặc tính năng mới còn ở trạng thái experimental.

Không nên kết luận một UI component đã bị xóa chỉ vì import cũ không còn tìm thấy. Spring Shell 4 tách phần core khỏi JLine, chuyển module bảng vào module JLine và giới thiệu Terminal UI framework mới. Các Flow Components như nhập chuỗi, nhập số, chọn đường dẫn, xác nhận, chọn một hoặc nhiều mục và ComponentFlow vẫn có trong tài liệu v4. Vì vậy, việc đánh giá cần bắt đầu bằng cách phân loại chính xác trạng thái của từng component.

Bài này hướng dẫn cách kiểm tra API sau nâng cấp, so sánh các phương án thay thế và chọn giải pháp theo yêu cầu thực tế. Các phương án gồm Flow Components của Spring Shell, JLine, Terminal UI framework, giao diện dòng lệnh thuần, thư viện TUI bên ngoài và giao diện web.

Sau bài này, bạn có thể:

- Phân biệt component bị xóa, chuyển package, chuyển module và component chỉ cần dependency tùy chọn.
- Xác định thành phần UI nào còn được hỗ trợ trong Spring Shell 4.
- Chọn giữa Flow Components, JLine và Terminal UI framework.
- Dùng command argument/option thay cho prompt khi chạy tự động.
- Đánh giá thư viện TUI bên ngoài như Lanterna.
- Nhận biết khi nào một quy trình nên chuyển sang web UI.
- So sánh chi phí migration, độ ổn định, khả năng kiểm thử và hỗ trợ terminal.
- Thiết kế lớp nghiệp vụ độc lập để có thể thay giao diện mà không viết lại logic.
- Lập kế hoạch prototype, kiểm thử và chuyển đổi theo từng nhóm component.

> Ví dụ dựa trên Spring Shell 4.0.4 và tài liệu Spring Shell 4.x hiện hành. Terminal UI framework của Spring Shell được tài liệu chính thức đánh dấu experimental; hãy kiểm tra lại trạng thái và API ở đúng patch release trước khi dùng trong sản phẩm.

## 1. Xác định chính xác điều gì đã thay đổi

Một lỗi compile sau nâng cấp có thể đến từ nhiều nguyên nhân khác nhau:

1. Package của class đã thay đổi.
2. Module chứa class đã được gộp hoặc chuyển sang dependency khác.
3. Core không còn kéo theo thư viện terminal như trước.
4. API cũ bị loại bỏ và có API mới thay thế.
5. Thành phần vẫn tồn tại nhưng chỉ dùng được với interactive runner hoặc terminal có tính năng tương ứng.
6. Tính năng mới thay thế chưa ổn định hoặc chưa đáp ứng đầy đủ hành vi cũ.

Hãy kiểm tra migration guide, Javadoc và dependency tree trước khi chọn thư viện thay thế. Đặc biệt, phân biệt việc một class không còn nằm trong module core với việc tính năng đó thực sự không còn được hỗ trợ.

### Những thay đổi đáng chú ý trong Spring Shell 4

| Khu vực | Thay đổi | Ảnh hưởng đến UI |
|---|---|---|
| Core và JLine | `spring-shell-core` không còn phụ thuộc JLine | Ứng dụng chỉ dùng core không tự có mọi tính năng terminal nâng cao |
| Runner | Có `SystemShellRunner`, `JLineShellRunner` và `NonInteractiveShellRunner` | Cần chọn runner phù hợp với khả năng UI |
| Table | Module `spring-shell-table` được gộp vào `spring-shell-jline` | Cần đổi dependency và package import |
| Flow Components | Các component nhập liệu và selector vẫn có trong v4, nhưng API thuộc nhánh JLine/TUI | Kiểm tra package mới và dependency |
| Terminal UI | Có các view như input, list, menu, dialog và progress | Phù hợp với giao diện toàn màn hình nhưng framework còn experimental |
| Completion command | Built-in command `completion` bị loại bỏ | Cấu hình completion theo shell người dùng như Bash hoặc Zsh |

### Phân biệt package cũ và package mới

Một số API UI trước đây nằm trong các package tổng quát của Spring Shell. Trong v4, các API phụ thuộc JLine được đặt dưới namespace JLine:

| Thành phần | Package cũ thường gặp | Package v4 |
|---|---|---|
| Flow Components | `org.springframework.shell.component.flow` | `org.springframework.shell.jline.tui.component.flow` |
| Table API | `org.springframework.shell.table` | `org.springframework.shell.jline.tui.table` |
| TUI controls/views | Không có cùng mô hình view trong API cũ | `org.springframework.shell.jline.tui.component.view.control` |

Nếu compiler báo không tìm thấy `ComponentFlow`, `StringInput` hoặc `Table`, hãy kiểm tra import và module trước khi viết lại component. Với Flow Components và Table API, migration có thể chỉ cần chuyển sang package mới và thêm dependency JLine phù hợp.

## 2. Kiểm kê component đang được ứng dụng sử dụng

Trước khi chọn giải pháp, hãy lập danh sách những tương tác thực tế của người dùng. Đừng chỉ ghi tên class Java; hãy ghi hành vi mà người dùng cần thực hiện.

Ví dụ:

| Hành vi người dùng | Component hoặc tính năng có thể đang dùng |
|---|---|
| Nhập tên, email hoặc token | String input |
| Nhập số lượng hoặc giới hạn | Number input |
| Chọn file hoặc thư mục | Path input / path search |
| Xác nhận xóa hoặc ghi đè | Confirmation input |
| Chọn một môi trường | Single select |
| Chọn nhiều module | Multi select |
| Đi qua nhiều bước cấu hình | ComponentFlow |
| Xem danh sách có căn cột | Table |
| Xem tiến độ hoặc trạng thái liên tục | Progress indicator / spinner |
| Điều hướng trong menu nhiều cấp | Menu / list / dialog |
| Nhập lệnh với history và tab completion | JLine REPL |

Với mỗi hành vi, ghi thêm:

- Có bắt buộc dùng bàn phím tương tác không?
- Có cần chuột, phím mũi tên hoặc cập nhật toàn màn hình không?
- Có chạy trong script, CI hoặc môi trường không có TTY không?
- Có cần history, completion, màu sắc hoặc Unicode không?
- Có cần hoạt động trên Windows Terminal, terminal Linux qua SSH và terminal hạn chế không?
- Người dùng có cần trình đọc màn hình hoặc một phương án không dùng màu không?
- Thành phần có được kiểm thử tự động bằng terminal giả lập không?

Kết quả kiểm kê giúp tránh chọn một framework TUI nặng cho một câu hỏi yes/no đơn giản, hoặc chọn một prompt một dòng cho quy trình cần nhiều màn hình và điều hướng phức tạp.

## 3. Phân loại trạng thái của các UI components trong Spring Shell 4

Các component thường được chia thành bốn nhóm:

| Trạng thái | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Còn hỗ trợ, package thay đổi | Tính năng vẫn tồn tại nhưng import cũ không còn đúng | Chuyển package và kiểm tra API |
| Còn hỗ trợ, module tùy chọn | Core không còn kéo dependency terminal vào tự động | Thêm `spring-shell-jline` hoặc starter tương ứng |
| Có API mới nhưng experimental | Có thể dùng nhưng API và hành vi có thể thay đổi | Prototype, cô lập adapter và chấp nhận chi phí nâng cấp |
| Không còn API tương đương trực tiếp | Tính năng đã bị loại bỏ hoặc thay đổi mô hình | Dùng command option, shell completion, thư viện khác hoặc web UI |

### Flow Components vẫn có trong v4

Tài liệu Spring Shell 4 vẫn mô tả các component:

- `StringInput`: nhập chuỗi và có thể che nội dung nhạy cảm.
- `NumberInput`: nhập số.
- `PathInput` và `PathSearch`: nhập hoặc tìm đường dẫn.
- `ConfirmationInput`: câu hỏi yes/no.
- `SingleItemSelector`: chọn một mục trong danh sách.
- `MultiItemSelector`: chọn nhiều mục.
- `ComponentFlow`: ghép nhiều component thành một wizard, có thể có nhánh điều kiện.

Những component này phù hợp với tương tác theo từng bước. Nếu ứng dụng đang dùng các thành phần đó, hãy kiểm tra package v4 và bảo đảm JLine có mặt. Không cần chuyển ngay sang một TUI framework khác chỉ vì import của phiên bản cũ không biên dịch.

### Table API đã được chuyển module

Module `spring-shell-table` đã được gộp vào `spring-shell-jline`. Table API mới nằm dưới `org.springframework.shell.jline.tui.table`. API bảng có thể định dạng dữ liệu, đặt giới hạn chiều rộng, wrap text và căn lề.

Nếu ứng dụng chỉ cần hiển thị vài cột trong một kết quả command, Table API vẫn là lựa chọn phù hợp. Nếu output cần được đọc bởi script hoặc công cụ khác, hãy cân nhắc CSV hoặc JSON thay vì chỉ tạo bảng ASCII.

### Terminal UI framework là lựa chọn mới, nhưng experimental

Spring Shell 4 cung cấp Terminal UI framework với các view:

- `AppView`, `BoxView` và `GridView` để tổ chức bố cục.
- `ButtonView` và `DialogView` để tạo thao tác hoặc hộp thoại.
- `InputView` để nhập và sửa text.
- `ListView`, `MenuView` và `MenuBarView` để điều hướng.
- `ProgressView` và `StatusBarView` để hiển thị tiến độ và trạng thái.

Framework dùng event loop, view và terminal rendering. Tài liệu chính thức cảnh báo đây là tính năng experimental và có thể có breaking changes. Nó phù hợp để thử nghiệm giao diện console phong phú, nhưng không nên coi đây là API ổn định dài hạn nếu ứng dụng chưa có ngân sách bảo trì và kiểm thử tương ứng.

## 4. Các phương án thay thế và tiêu chí đánh giá

Không có một lựa chọn duy nhất phù hợp với mọi component. Hãy chọn theo mức độ tương tác cần thiết:

| Phương án | Phù hợp với | Ưu điểm | Chi phí hoặc giới hạn |
|---|---|---|---|
| Spring Shell Flow Components | Prompt, xác nhận, nhập đường dẫn, selector, wizard | Tích hợp với Spring Shell, có builder và context | Cần JLine; chủ yếu là tương tác tuần tự |
| JLine trực tiếp | Line editor, prompt, history, completion, terminal control | Kiểm soát chi tiết terminal và tích hợp với Spring Shell | Phải tự quản lý nhiều hành vi và test terminal |
| Spring Shell Terminal UI | Menu, dialog, list, progress và giao diện toàn màn hình | Có sẵn view, event loop và integration của Spring Shell | Experimental; có thể phải sửa khi API thay đổi |
| SystemShellRunner và Java Console | Prompt đơn giản hoặc ứng dụng không cần UI nâng cao | Ít dependency, dễ triển khai | Không có history, tab completion và rich text |
| Thư viện TUI bên ngoài như Lanterna | Ứng dụng cần cửa sổ, widget và screen buffer riêng | Toolkit TUI độc lập, có nhiều mức trừu tượng | Phải quản lý terminal lifecycle và tích hợp riêng |
| Command option/argument | Script, CI, automation và thao tác có thể mô tả bằng tham số | Dễ kiểm thử, dễ lặp lại, không cần TTY | Kém thuận tiện cho người dùng cần khám phá lựa chọn |
| Web UI | Form phức tạp, nhiều người dùng, truy cập từ xa hoặc yêu cầu accessibility cao | Có hệ sinh thái trình duyệt, form và accessibility | Cần thêm ứng dụng, bảo mật và vận hành web |

### Tiêu chí nên dùng khi so sánh

**Độ bao phủ chức năng:** phương án mới có hỗ trợ đúng hành vi cũ không? Ví dụ một menu chọn một mục không thay thế được một selector nhiều lựa chọn có trạng thái đã chọn.

**Độ ổn định API:** API đã được đánh dấu stable hay experimental? Có lịch sử thay đổi lớn không? Có thể cô lập code phụ thuộc framework trong một adapter không?

**Khả năng chạy không tương tác:** component có thể bỏ qua prompt và nhận giá trị qua option không? Nếu chạy trong CI, ứng dụng có thể chờ người dùng vô thời hạn không?

**Khả năng tương thích terminal:** cần ANSI, cursor addressing, mouse, Unicode hoặc native terminal provider nào? Terminal giả lập trong IDE có thể khác terminal SSH hoặc Windows.

**Khả năng kiểm thử:** có thể cung cấp input xác định và kiểm tra screen/output không? Có cần chạy test thủ công trên nhiều terminal không?

**Accessibility:** người dùng có thể thao tác chỉ bằng bàn phím không? Thông tin có còn hiểu được khi tắt màu không? Một TUI toàn màn hình có đáp ứng được nhu cầu của người dùng trình đọc màn hình không?

**Chi phí vận hành:** dependency có kéo native provider, JLine hoặc thư viện ngoài vào artifact không? Có ảnh hưởng đến native image hoặc cách đóng gói không?

**Quyền sở hữu terminal:** chỉ một thư viện nên quản lý input reader, raw mode, cursor và screen buffer tại một thời điểm. Hai framework cùng điều khiển terminal có thể làm mất phím, sai vị trí con trỏ hoặc không khôi phục terminal sau lỗi.

## 5. Phương án 1: Giữ Flow Components và cập nhật dependency

Đây thường là lựa chọn đầu tiên nếu ứng dụng chỉ cần nhập dữ liệu, xác nhận hoặc chọn mục. Flow Components vẫn có trong Spring Shell 4 và có thể ghép thành wizard bằng `ComponentFlow`.

### Thêm module JLine

Nếu ứng dụng đang dùng Spring Shell core mà không có JLine, thêm module:

~~~xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-jline</artifactId>
</dependency>
~~~

Để Spring Boot BOM hoặc dependency management của Spring Shell quản lý version. Spring Shell cũng cung cấp các starter chọn JLine terminal provider như `spring-shell-starter-jansi`, `spring-shell-starter-jni` và `spring-shell-starter-jna`. Chọn starter theo môi trường đóng gói và nền tảng triển khai.

### Dùng ComponentFlow cho wizard

Ví dụ dưới đây hỏi môi trường triển khai và xác nhận chạy thử. Builder được inject từ Spring:

~~~java
import org.springframework.shell.jline.tui.component.context.ComponentContext;
import org.springframework.shell.jline.tui.component.flow.ComponentFlow;
import org.springframework.stereotype.Component;
import org.springframework.shell.core.command.annotation.Command;

@Component
public class SetupCommands {

    private final ComponentFlow.Builder flowBuilder;

    public SetupCommands(ComponentFlow.Builder flowBuilder) {
        this.flowBuilder = flowBuilder;
    }

    @Command(name = "setup")
    public String setup() {
        ComponentFlow.ComponentFlowResult result = flowBuilder.clone()
                .reset()
                .withStringInput("environment")
                    .name("Môi trường")
                    .defaultValue("staging")
                    .and()
                .withConfirmationInput("dryRun")
                    .name("Chạy thử trước?")
                    .and()
                .build()
                .run();

        ComponentContext<?> context = result.getContext();
        String environment = context.get("environment", String.class);
        Boolean dryRun = context.get("dryRun", Boolean.class);

        return "Môi trường: " + environment + ", dry run: " + dryRun;
    }
}
~~~

Ví dụ thể hiện mô hình builder của Flow Components v4. Trong ứng dụng thực tế, hãy kiểm tra trạng thái hủy flow, giá trị rỗng và kết quả chưa được cung cấp trước khi dùng dữ liệu. Không coi việc người dùng xác nhận trên UI là thay thế cho kiểm tra quyền nghiệp vụ.

### Khi nên giữ Flow Components?

- Quy trình chỉ có một số câu hỏi tuần tự.
- Người dùng cần nhập text, số, path hoặc chọn mục.
- Giao diện không cần bố cục toàn màn hình phức tạp.
- Có thể cung cấp một đường chạy non-interactive tương ứng.
- Muốn giữ integration và test support sẵn có của Spring Shell.

Nếu chỉ cần xác nhận xóa, không cần dựng một dialog riêng. Một `ConfirmationInput` là đủ ở interactive mode; trong script nên dùng option xác nhận tường minh.

## 6. Phương án 2: Dùng Table API mới cho dữ liệu dạng bảng

Nếu lỗi migration đến từ package `org.springframework.shell.table`, kiểm tra dependency trước. Trong v4, table module được gộp vào `spring-shell-jline`; package mới là `org.springframework.shell.jline.tui.table`.

Table API nhận một `TableModel`, sau đó áp dụng formatter, giới hạn kích thước cột, wrapping và alignment. `Table.render(totalAvailableWidth)` tạo chuỗi theo chiều rộng terminal được cung cấp.

~~~java
import org.springframework.shell.jline.tui.table.Table;
import org.springframework.shell.jline.tui.table.TableModel;

// Tạo TableModel từ dữ liệu nghiệp vụ bằng TableModelBuilder.
// Tạo Table từ model và cấu hình formatter/alignment cần thiết.
String rendered = table.render(terminalWidth);
~~~

Đoạn trên minh họa điểm gọi render; việc xây dựng `TableModel` và cấu hình `TableBuilder` cần theo API của đúng patch Spring Shell đang dùng.

Nếu cần thay thế đơn giản hơn:

- Dùng `String.format` hoặc formatter riêng cho bảng ít cột.
- Trả về CSV khi dữ liệu cần chuyển tiếp cho spreadsheet hoặc script.
- Trả về JSON khi hệ thống khác cần đọc có cấu trúc.
- Giới hạn số cột và số dòng để bảng không vượt quá terminal nhỏ.

Không nên dùng bảng ASCII làm định dạng máy đọc nếu người gọi cần xử lý dữ liệu tự động. Bảng là giao diện cho con người; CSV/JSON là định dạng trao đổi dữ liệu.

## 7. Phương án 3: Dùng Terminal UI framework cho giao diện toàn màn hình

Khi command cần menu, dialog, list, progress và nhiều vùng hiển thị đồng thời, Flow Components có thể không đủ. Spring Shell 4 có `TerminalUI` để chạy một giao diện dựa trên view và event loop.

Một khung tối thiểu:

~~~java
TerminalUI ui = terminalUIBuilder.build();
BoxView root = new BoxView();

ui.configure(root);
ui.setRoot(root, true);
ui.run();
~~~

`TerminalUI.run()` là thao tác blocking. Ứng dụng phải có cách kết thúc event loop, ví dụ đăng ký phím Ctrl-Q và dispatch interrupt message. Các dialog có thể được đặt làm modal view để nhận input cho tới khi đóng.

Các view có sẵn gồm:

| View | Mục đích |
|---|---|
| `BoxView` | Vùng nội dung có border/title |
| `GridView` | Bố cục nhiều vùng |
| `InputView` | Nhập và sửa text |
| `ListView` | Danh sách có lựa chọn |
| `MenuView` / `MenuBarView` | Điều hướng menu |
| `DialogView` | Hộp thoại và nút thao tác |
| `ProgressView` | Tiến độ, spinner và phần trăm |
| `StatusBarView` | Trạng thái ở một vùng riêng |

### Vì sao cần thận trọng?

Tài liệu chính thức đánh dấu Terminal UI framework là experimental và có thể thay đổi breaking API. Điều này ảnh hưởng đến:

- Cách tạo view và cấu hình event loop.
- Cách xử lý input, mouse và key binding.
- Cách vẽ lại màn hình và tối ưu frame.
- Cách kiểm thử screen và event.
- Cách đóng terminal khi command bị lỗi hoặc người dùng thoát.

Nếu chọn phương án này, hãy đặt code TUI trong một adapter riêng, giữ nghiệp vụ ở service độc lập và viết test cho hành vi điều hướng. Khi framework đổi API, chỉ adapter và lớp trình bày cần được cập nhật.

Không chọn Terminal UI chỉ vì một prompt cũ không compile. Hãy dùng nó khi ứng dụng thực sự cần giao diện toàn màn hình.

## 8. Phương án 4: Dùng JLine trực tiếp cho tương tác mức thấp

JLine phù hợp khi cần kiểm soát line editor, history, completion, key binding hoặc terminal capabilities nhưng không cần toàn bộ view framework.

Các trường hợp phù hợp:

- Custom prompt hoặc input masking.
- Lịch sử nhập lệnh.
- Completion dựa trên ngữ cảnh.
- Xử lý phím đặc biệt.
- Terminal size và màu sắc.
- Điều khiển cursor hoặc cập nhật dòng tiến độ.

Spring Shell 4 tách JLine ra khỏi core. `JLineShellRunner` cần `spring-shell-jline`. Nếu ứng dụng chỉ chọn `SystemShellRunner`, các tính năng nâng cao như history, tab completion và rich text không có sẵn theo mô tả trong migration guide.

Khi dùng JLine trực tiếp, cần quản lý:

- Reader/writer và vòng đời terminal.
- Chế độ raw/cooked và việc khôi phục terminal.
- Cancel/interrupt và đóng tài nguyên.
- Hành vi khi standard input không phải TTY.
- Test với terminal giả lập và terminal thật.

JLine là lựa chọn tốt cho một khả năng terminal cụ thể. Nếu cần một ứng dụng có nhiều cửa sổ, layout và widget, hãy so sánh với Terminal UI hoặc thư viện TUI đầy đủ.

## 9. Phương án 5: Dùng giao diện dòng lệnh thuần cho automation

Một UI component tương tác thường không phù hợp khi command được gọi từ CI, cron, container hoặc script. Trong những môi trường đó, command nên nhận mọi dữ liệu cần thiết qua argument và option.

Ví dụ, thay vì hiện confirmation dialog khi deploy:

~~~java
@Command(name = "deploy")
public String deploy(
        @Option(longName = "environment") String environment,
        @Option(longName = "yes") boolean confirmed) {

    if (!confirmed) {
        return "Thao tác cần được xác nhận bằng --yes.";
    }

    deploymentService.deploy(environment);
    return "Đã triển khai lên " + environment;
}
~~~

Người dùng tương tác có thể gọi:

~~~text
deploy --environment staging --yes
~~~

Pipeline cũng có thể gọi đúng cùng command mà không cần terminal tương tác. Đối với thao tác phá hủy dữ liệu, xác nhận bằng option chỉ là một bước trong quy trình; service vẫn phải kiểm tra quyền và điều kiện nghiệp vụ.

Nếu dùng `SystemShellRunner`, có thể dùng Java Console cho prompt đơn giản. Tuy nhiên, không nên giả định Java Console có history, tab completion, rich text hoặc selector như JLine.

### Khi nên chọn CLI thuần?

- Command cần chạy trong CI/CD hoặc cron.
- Các giá trị đầu vào đã biết trước.
- Kết quả cần được script xử lý.
- Không cần điều hướng bằng phím mũi tên hoặc mouse.
- Muốn giảm dependency và rủi ro terminal.

Một nguyên tắc hữu ích là mỗi workflow interactive quan trọng nên có cách gọi non-interactive tương đương. Người dùng có thể chọn prompt để thuận tiện, còn automation truyền giá trị tường minh.

## 10. Phương án 6: Dùng thư viện TUI bên ngoài

Nếu Terminal UI của Spring Shell chưa đáp ứng hoặc rủi ro experimental không phù hợp, có thể đánh giá một thư viện TUI độc lập như Lanterna.

Lanterna là thư viện Java cho giao diện text-mode, hỗ trợ terminal tương thích xterm và cung cấp ba tầng:

1. Terminal API cấp thấp để điều khiển cursor và ký tự.
2. Screen buffer để dựng màn hình rồi flush thay đổi.
3. GUI toolkit với window, button, label và các widget.

Ưu điểm:

- Có thể xây dựng giao diện độc lập với Spring Shell.
- Có lớp terminal, screen và GUI để chọn mức trừu tượng.
- Chạy bằng Java thuần, không bắt buộc native library theo mô tả của dự án.
- Phù hợp nếu cần một TUI có vòng đời riêng.

Chi phí:

- Phải tích hợp với command và service của Spring Shell bằng adapter.
- Phải quyết định framework nào sở hữu terminal input, cursor và screen buffer.
- Cần kiểm thử trên terminal đích và xử lý encoding, resize, key mapping.
- Cần kiểm tra điều khoản giấy phép LGPL-3.0 khi phân phối sản phẩm.

Không để JLine và Lanterna cùng điều khiển một terminal trong cùng thời điểm. Nếu chọn Lanterna, hãy thiết kế một chế độ chạy riêng hoặc một adapter quản lý quyền sở hữu terminal rõ ràng.

## 11. Phương án 7: Chuyển workflow sang web UI

Một số quy trình đã vượt quá phạm vi hợp lý của terminal UI. Ví dụ:

- Form nhiều bước có nhiều trường và validation phức tạp.
- Bảng dữ liệu cần sort, filter, phân trang và chỉnh sửa.
- Nhiều người dùng cùng thao tác.
- Cần truy cập từ xa qua trình duyệt.
- Cần hỗ trợ accessibility, trình đọc màn hình và thao tác chuột phong phú.
- Cần upload/download file hoặc xem biểu đồ.

Trong trường hợp đó, có thể giữ service nghiệp vụ hiện tại và xây một web UI làm adapter mới. Spring Shell vẫn có thể tiếp tục là công cụ vận hành hoặc automation.

Đừng chuyển toàn bộ nghiệp vụ sang controller hoặc command. Hãy giữ service/domain layer dùng chung để hai giao diện không tạo ra hai bộ quy tắc khác nhau.

## 12. Ma trận chọn giải pháp theo loại component

| Nhu cầu cũ | Lựa chọn đầu tiên trong v4 | Phương án dự phòng |
|---|---|---|
| Nhập text/number/path | Flow Components | CLI option hoặc Java Console |
| Xác nhận yes/no | ConfirmationInput | `--yes` trong non-interactive mode |
| Chọn một/nhiều mục | Single/Multi Item Selector | Số thứ tự qua option hoặc list-based TUI |
| Wizard nhiều bước | ComponentFlow | Terminal UI nếu cần layout phong phú |
| Bảng ASCII | Table API trong `spring-shell-jline` | Formatter riêng, CSV hoặc JSON |
| History/completion | JLineShellRunner | CLI option và shell completion ngoài |
| Dialog/menu toàn màn hình | Terminal UI nếu chấp nhận experimental | Lanterna hoặc web UI |
| Progress bar/spinner | ProgressView trong Terminal UI | Dòng tiến độ hoặc log theo mốc |
| Rich text/màu | JLine | Plain text khi terminal không hỗ trợ |
| Completion command bị loại bỏ | Completion script theo Bash/Zsh | Tài liệu option và ví dụ command |

Ma trận là điểm bắt đầu. Trước khi chọn, hãy xác nhận component đang dùng thuộc API nào, package nào và dependency nào trong phiên bản nguồn.

## 13. Quy trình đánh giá và migration từng component

### Bước 1: Ghi nhận hành vi hiện tại

Chụp lại hoặc mô tả input, output, key binding, default value, validation, cancel behavior và kết quả trả về. Nếu có nhiều nhánh trong wizard, ghi lại điều kiện chuyển nhánh.

### Bước 2: Xác minh trạng thái API

Tra cứu:

- Migration guide của Spring Shell v4.
- Javadoc của phiên bản đích.
- Reference documentation đúng version.
- Dependency tree của ứng dụng.
- Release notes của patch release đang dùng.

Phân loại component là retained, relocated, optional dependency, experimental hoặc removed.

### Bước 3: Chọn tối đa hai phương án để prototype

Ví dụ:

- Flow Components so với Terminal UI cho một wizard.
- Table API mới so với CSV cho danh sách dữ liệu.
- JLine so với plain CLI cho input trong pipeline.

Không triển khai toàn bộ migration trên nhiều framework trước khi có kết quả prototype.

### Bước 4: Đo hành vi thực tế

Prototype cần kiểm tra:

- Số bước và số thao tác của người dùng.
- Thời gian phản hồi.
- Hành vi khi nhấn Esc, Ctrl-C hoặc Enter.
- Terminal hẹp, terminal rộng và resize.
- Unicode, tiếng Việt, emoji và màu.
- Khi không có TTY hoặc stdin được redirect.
- Khi command bị lỗi giữa chừng.
- Khi người dùng hủy workflow.

### Bước 5: Đánh giá chi phí dài hạn

Ghi lại dependency mới, kích thước artifact, yêu cầu JDK, native library, test support, mức độ ổn định API và cách nâng cấp trong tương lai. Một component trông đẹp hơn nhưng yêu cầu một event loop phức tạp có thể không đáng dùng cho command chỉ chạy vài lần mỗi ngày.

### Bước 6: Chuyển đổi theo nhóm nhỏ

Chuyển từng nhóm component, giữ hành vi nghiệp vụ và command contract ổn định. Sau mỗi nhóm, chạy test, smoke test và kiểm tra trên terminal mục tiêu.

### Bước 7: Giữ fallback cho automation

Nếu workflow cần UI tương tác, vẫn cung cấp command option hoặc file input để chạy non-interactive. Không để pipeline phải giả lập thao tác phím trên một TUI nếu có thể truyền dữ liệu trực tiếp.

## 14. Kiểm thử sau khi thay UI component

UI migration cần nhiều hơn compile test. Hãy kiểm tra cả hành vi terminal và dữ liệu trả về:

| Nhóm test | Nội dung |
|---|---|
| Unit test | Validation, default value, điều kiện nhánh và chuyển đổi dữ liệu |
| Component test | Input, selector, confirmation và kết quả được trả về |
| Shell integration test | Command đăng ký đúng, terminal nhận output và flow hoạt động |
| Non-interactive test | Command chạy không cần prompt hoặc TTY |
| Terminal compatibility test | Width, height, Unicode, màu, cursor và key handling |
| Failure/cancel test | Người dùng hủy, input sai, terminal đóng hoặc service ném exception |
| Packaging test | Dependency JLine hoặc thư viện ngoài có mặt trong artifact |

Với Terminal UI experimental, test thêm:

- Event loop dừng đúng cách.
- Terminal được khôi phục sau Ctrl-C hoặc exception.
- Modal view được đóng đúng.
- Không còn thread giữ ứng dụng sau khi người dùng thoát.
- Redraw không gây nhấp nháy hoặc mất nội dung.

Với thư viện ngoài, kiểm tra cả hành vi khi terminal không hỗ trợ cursor addressing hoặc màu. Một TUI cần có phương án plain-text hoặc thông báo rõ khi môi trường không đáp ứng yêu cầu.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ComponentFlow` không tìm thấy | Import cũ hoặc thiếu module JLine | Dùng package v4 và thêm `spring-shell-jline` |
| `Table` không tìm thấy | Dùng module/package của v3 | Chuyển sang `org.springframework.shell.jline.tui.table` |
| Không có history hoặc tab completion | Đang chạy bằng `SystemShellRunner` | Chọn `JLineShellRunner` và dependency tương ứng |
| Rich text không hiển thị | Core runner không dùng JLine | Dùng JLine hoặc output plain text |
| TUI mới hoạt động không ổn định | Dùng framework experimental mà chưa có test đầy đủ | Prototype riêng, cô lập adapter và pin version |
| Command treo trong CI | Flow đang chờ input tương tác | Cung cấp option và đường chạy non-interactive |
| Terminal bị lỗi sau khi thoát | Không khôi phục raw mode hoặc event loop | Quản lý vòng đời và cleanup trong finally |
| Phím bị mất hoặc cursor nhảy sai | Hai thư viện cùng đọc/ghi terminal | Chỉ để một framework sở hữu terminal tại một thời điểm |
| Bảng ASCII khó xử lý bằng script | Output được thiết kế cho con người | Cung cấp CSV/JSON riêng |
| UI mới làm thay đổi nghiệp vụ | Logic nằm trong component thay vì service | Chuyển quy tắc vào service/domain và test độc lập |
| Không thể dùng với screen reader | Chỉ dựa vào màu hoặc layout toàn màn hình | Cung cấp plain-text mode hoặc web UI |

## 16. Checklist đánh giá phương án thay thế

- Ghi lại hành vi của component cũ trước khi thay.
- Xác minh API có bị xóa hay chỉ chuyển package/module.
- Kiểm tra `spring-shell-jline` có cần được thêm vào hay không.
- Xác nhận runner hỗ trợ đúng khả năng UI.
- Ưu tiên Flow Components cho input, confirmation và selector đơn giản.
- Chỉ dùng Terminal UI khi cần giao diện nhiều vùng hoặc toàn màn hình.
- Đánh giá rủi ro experimental và chi phí nâng cấp.
- Cân nhắc JLine trực tiếp khi chỉ cần một tính năng terminal mức thấp.
- Dùng CLI options cho automation và non-interactive mode.
- Đánh giá Lanterna hoặc thư viện TUI khác nếu cần toolkit độc lập.
- Chuyển sang web UI khi workflow cần accessibility và tương tác phong phú.
- Không để nhiều framework cùng sở hữu terminal.
- Kiểm thử cancel, error, resize, Unicode, color và no-TTY.
- Giữ service nghiệp vụ độc lập với giao diện.
- Ghi quyết định kỹ thuật và lý do chọn phương án.

## 17. Bài tập thực hành

Một ứng dụng quản trị đang dùng Spring Shell 3.4 với các thành phần: `ComponentFlow`, `SingleItemSelector`, `spring-shell-table` và một màn hình tiến độ tùy chỉnh. Mục tiêu là nâng lên Spring Shell 4.

1. Lập danh sách hành vi mà người dùng đang thực hiện trong từng component.
2. Đối chiếu migration guide và Javadoc v4 để xác định component nào còn hỗ trợ, chuyển package hoặc chuyển module.
3. Thêm `spring-shell-jline` vào một prototype và chuyển `ComponentFlow` sang package v4.
4. Dùng Flow Components để hỏi môi trường, xác nhận dry-run và chọn một nhóm tài nguyên.
5. Chuyển Table API sang package mới; render bảng với chiều rộng terminal xác định.
6. Tạo một bản thử `ProgressView` trong Terminal UI và ghi nhận rủi ro do framework experimental.
7. So sánh progress view với phương án in các mốc tiến độ plain text.
8. Tạo đường chạy non-interactive nhận môi trường và xác nhận qua option.
9. Kiểm tra cùng workflow trên terminal interactive, script và CI không có TTY.
10. Viết test cho input sai, cancel, terminal resize và output Unicode.
11. So sánh dependency, độ phức tạp, khả năng bảo trì và testability của từng phương án.
12. Viết quyết định migration: component nào giữ, component nào thay, lý do và điều kiện chấp nhận.

Khi hoàn thành, hãy giải thích vì sao `ComponentFlow` không nên bị xem là đã bị xóa chỉ vì package cũ không còn, và vì sao Terminal UI framework cần được đánh giá riêng về mức độ ổn định.

## Tài liệu tham khảo

- [Spring Shell 4 – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): module changes, JLine dependency, table migration và API changes.
- [Spring Shell 4 – Building](https://docs.spring.io/spring-shell/reference/building.html): các starter và terminal provider của JLine.
- [Spring Shell 4 – Flow Components](https://docs.spring.io/spring-shell/reference/components/ui/index.html): nhập liệu, selector và các component tương tác.
- [Spring Shell 4 – Flow](https://docs.spring.io/spring-shell/reference/components/flow/index.html): ghép nhiều component thành wizard và điều hướng có điều kiện.
- [Spring Shell 4 – Terminal UI](https://docs.spring.io/spring-shell/reference/tui/index.html): trạng thái experimental và tổng quan framework.
- [Spring Shell 4 – TerminalUI](https://docs.spring.io/spring-shell/reference/tui/intro/terminalui.html): tạo UI, cấu hình view, event loop và modal view.
- [Spring Shell 4 – Views](https://docs.spring.io/spring-shell/reference/tui/views/index.html): danh sách view có sẵn.
- [Spring Shell 4 – ProgressView](https://docs.spring.io/spring-shell/reference/tui/views/progress.html): progress state, spinner và phần trăm.
- [Spring Shell 4 – Table API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html): render bảng theo chiều rộng có sẵn.
- [Spring Shell – Releases](https://github.com/spring-projects/spring-shell/releases): kiểm tra patch release và thay đổi mới.
- [Lanterna – GitHub](https://github.com/mabe02/lanterna): thư viện Java xây dựng giao diện text-mode, terminal, screen buffer và GUI toolkit.
