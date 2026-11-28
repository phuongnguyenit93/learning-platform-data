# Vòng đời nhập liệu, ngữ cảnh và hiển thị của một thành phần

## 1. Thành phần tương tác không chỉ là một câu hỏi

Trong Spring Shell 3.x, một interactive component đảm nhận một tác vụ nhập liệu cụ thể như nhập văn bản, chọn đường dẫn, xác nhận yes/no hoặc chọn một hay nhiều phần tử trong danh sách. Component điều khiển vòng lặp nhận phím, giữ trạng thái nhập, cập nhật ngữ cảnh và hiển thị giao diện trong lúc người dùng thao tác.

Các component dựng sẵn thường đi theo một vòng đời chung:

1. Bắt đầu vòng lặp nhận input.
2. Tạo hoặc cập nhật context riêng của component.
3. Render trạng thái hiện tại trong khi người dùng nhập hoặc di chuyển lựa chọn.
4. Kết thúc vòng lặp khi thao tác hoàn tất.
5. Render trạng thái cuối cùng của component.

Nhờ tách input, context và rendering, ứng dụng có thể thay đổi cách hiển thị mà không phải viết lại toàn bộ logic đọc phím. Component cũng có thể được chạy độc lập trong một command hoặc được kết hợp thành nhiều bước bằng `ComponentFlow`.

## 2. Các component thường dùng trong Spring Shell 3.x

Spring Shell 3.x cung cấp những component phục vụ các kiểu tương tác phổ biến:

| Component | Mục đích | Kết quả thường nhận được |
|---|---|---|
| `StringInput` | Nhập một chuỗi văn bản, có thể che ký tự nhạy cảm | `String` |
| `PathInput` | Nhập và chọn đường dẫn tệp hoặc thư mục | `Path` |
| `ConfirmationInput` | Xác nhận một câu hỏi yes/no | `Boolean` |
| `SingleItemSelector` | Chọn một phần tử từ danh sách | Giá trị của phần tử được chọn |
| `MultiItemSelector` | Chọn nhiều phần tử từ danh sách | Danh sách giá trị được chọn |

Các component có context chuyên biệt. Ví dụ, `StringInputContext` có dữ liệu về input, giá trị mặc định, kết quả và message; selector context có thêm trạng thái các phần tử và vị trí con trỏ.

## 3. Vòng đời của một component

Một component được chạy thông qua phương thức `run(...)`. Với component văn bản, tham số đầu vào thường là context rỗng được tạo bởi `StringInputContext.empty()` hoặc `PathInputContext.empty()`.

Ở cấp API, `AbstractComponent` cung cấp `run(ComponentContext<?>)` để chạy logic và trả về context đã cập nhật. Component cụ thể triển khai phần xử lý nội bộ và đọc input. Các hook `addPreRunHandler(...)` và `addPostRunHandler(...)` cho phép thực hiện công việc trước và sau lần chạy component.

~~~mermaid
flowchart TD
    A[Tạo component và cấu hình] --> B[Tạo context ban đầu]
    B --> C[Pre-run handler]
    C --> D[Vòng lặp đọc phím]
    D --> E[Cập nhật context]
    E --> F[Render trạng thái đang nhập]
    F --> G{Đã hoàn tất?}
    G -->|Chưa| D
    G -->|Rồi| H[Component kết thúc]
    H --> I[Post-run handler]
    H --> J[Render trạng thái cuối]
    I --> K[Trả context đã cập nhật]
    J --> K
~~~

Sơ đồ mô tả vòng đời ở mức khái niệm. Chi tiết đọc phím và render phụ thuộc loại component. Điều cần nhớ là `run(...)` trả lại context mang kết quả; ứng dụng nên đọc kết quả từ context sau khi component chạy xong.

## 4. Ví dụ: chạy StringInput độc lập

Ví dụ sau dùng `StringInput` để hỏi tên dự án. Component nhận terminal, tên trường, giá trị mặc định, `ResourceLoader` và `TemplateExecutor` để có thể nạp template giao diện.

~~~java
package com.example.cli;

import org.jline.terminal.Terminal;
import org.springframework.context.ResourceLoaderAware;
import org.springframework.core.io.ResourceLoader;
import org.springframework.shell.component.StringInput;
import org.springframework.shell.component.StringInput.StringInputContext;
import org.springframework.shell.style.TemplateExecutor;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ProjectCommands implements ResourceLoaderAware {

    private final Terminal terminal;
    private final TemplateExecutor templateExecutor;
    private ResourceLoader resourceLoader;

    public ProjectCommands(Terminal terminal, TemplateExecutor templateExecutor) {
        this.terminal = terminal;
        this.templateExecutor = templateExecutor;
    }

    @Override
    public void setResourceLoader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    @ShellMethod(key = "project ask-name", value = "Nhập tên dự án")
    public String askProjectName() {
        StringInput component = new StringInput(
                terminal, "Tên dự án", "demo-project");

        component.setResourceLoader(resourceLoader);
        component.setTemplateExecutor(templateExecutor);

        StringInputContext context = component.run(StringInputContext.empty());
        return "Tên dự án đã chọn: " + context.getResultValue();
    }
}
~~~

Khi người dùng gọi `project ask-name`, component hiển thị lời nhắc, nhận chuỗi nhập và trả `StringInputContext`. `getResultValue()` lấy giá trị đã được chấp nhận. Nếu nghiệp vụ yêu cầu chuỗi không được rỗng, hãy kiểm tra giá trị sau khi component trả context và hiển thị lại yêu cầu phù hợp trước khi tiếp tục.

Ví dụ dùng `ResourceLoaderAware` để nhận `ResourceLoader` từ Spring. Trong một component khác, có thể inject `ResourceLoader` trực tiếp qua constructor nếu ứng dụng cung cấp bean đó. `Terminal` và `TemplateExecutor` là hạ tầng cần thiết cho việc đọc input và render component.

## 5. Context giữ trạng thái của component

`ComponentContext` là hợp đồng context cơ sở. Nó cung cấp một vùng key/value để component giữ dữ liệu chung, đồng thời cho phép mỗi loại component bổ sung thuộc tính riêng.

Các thao tác thường dùng:

| API | Mục đích |
|---|---|
| `ComponentContext.empty()` | Tạo context ban đầu rỗng. |
| `get(key)` | Lấy giá trị theo khóa. |
| `get(key, type)` | Lấy giá trị và yêu cầu ép sang kiểu chỉ định. |
| `put(key, value)` | Đưa dữ liệu vào context. |
| `containsKey(key)` | Kiểm tra context có khóa hay chưa. |
| `stream()` | Duyệt các cặp key/value. |
| `toTemplateModel()` | Chuyển dữ liệu context thành map để đưa vào template. |
| `getTerminalWidth()` | Lấy chiều rộng terminal nếu đã được thiết lập. |

Context chuyên biệt còn có các thuộc tính riêng:

**Text component context** như `StringInputContext` và `PathInputContext:

- `name`: tên hoặc tiêu đề của component.
- `input`: nội dung người dùng đang nhập.
- `resultValue`: giá trị sau khi component hoàn tất.
- `message`: thông điệp hiển thị kèm component.
- `messageLevel`: mức thông điệp `INFO`, `WARN` hoặc `ERROR`.

**Selector component context**:

- `name`: tiêu đề danh sách.
- `input`: nội dung tìm kiếm hoặc lọc danh sách.
- `itemStates`: trạng thái của toàn bộ phần tử.
- `itemStateView`: danh sách phần tử đang được hiển thị.
- `isResult`: cho biết component đang ở chế độ hiển thị kết quả.
- `cursorRow`: vị trí con trỏ hiện tại trong danh sách.

Context giúp renderer biết cần hiển thị gì ở mỗi thời điểm. Ví dụ, khi người dùng đang nhập, renderer có thể hiển thị `input`; sau khi hoàn tất, renderer dùng `resultValue`.

## 6. Message và mức thông báo trong context

Text component context cho phép đặt message và mức độ của message. Điều này hữu ích khi cần hướng dẫn người dùng hoặc phản hồi lỗi ngay tại vị trí nhập liệu.

Đoạn mã sau bổ sung hook cho component ở phần 4. Cần import `AbstractTextComponent`:

~~~java
import org.springframework.shell.component.support.AbstractTextComponent;

component.addPreRunHandler(context -> {
    context.setMessage("Nhập tên ngắn, không chứa khoảng trắng ở đầu hoặc cuối",
            AbstractTextComponent.TextComponentContext.MessageLevel.INFO);
});
~~~

`addPreRunHandler(...)` và `addPostRunHandler(...)` nhận một `Consumer` của context tương ứng. Có thể dùng handler để chuẩn bị tên, message hoặc dữ liệu phụ trước khi chạy, rồi kiểm tra kết quả hoặc ghi nhận trạng thái sau khi component kết thúc.

Nếu cần phân loại thông điệp, dùng `MessageLevel.INFO`, `MessageLevel.WARN` hoặc `MessageLevel.ERROR`. Renderer mặc định có thể sử dụng các thuộc tính này để chọn cách trình bày phù hợp.

Không nên dùng message làm nơi lưu dữ liệu nghiệp vụ. Hãy đọc giá trị từ `resultValue` hoặc các khóa trong context; message chỉ phục vụ giao tiếp với người dùng.

## 7. Pre-run và post-run handler

`AbstractComponent` cung cấp hai hook:

- `addPreRunHandler(handler)`: đăng ký xử lý trước khi component bắt đầu phần nhập liệu.
- `addPostRunHandler(handler)`: đăng ký xử lý sau khi component hoàn tất phần chạy.

Ví dụ:

Đây là phần trích minh họa cách gắn handler; `auditService` là service của ứng dụng và cần được inject vào command:

~~~java
StringInput component = new StringInput(terminal, "Tên workspace", "default");

component.addPreRunHandler(context -> {
    context.setName("Workspace cần sử dụng");
    context.setMessage("Có thể nhấn Enter để dùng giá trị mặc định");
});

component.addPostRunHandler(context -> {
    String workspace = context.getResultValue();
    auditService.recordWorkspacePrompt(workspace);
});

StringInputContext context = component.run(StringInputContext.empty());
~~~

Pre-run handler phù hợp để chuẩn bị context trước khi hiển thị. Post-run handler phù hợp để ghi nhận kết quả, cập nhật trạng thái hoặc thực hiện xử lý sau khi input đã hoàn tất.

Handler nhận context có kiểu cụ thể, vì vậy có thể gọi các phương thức như `getInput()`, `setMessage()` hoặc `getResultValue()` mà không cần tự ép kiểu từ `Map`.

Nếu post-run handler cần dùng kết quả cho nghiệp vụ chính, hãy cân nhắc xử lý sau lời gọi `run(...)` để luồng điều khiển thể hiện rõ ràng. Handler không nên chứa logic nghiệp vụ lớn hoặc thao tác mạng kéo dài khiến component khó kiểm thử.

## 8. Hiển thị component bằng template

Spring Shell hỗ trợ hai cách render component:

1. Dùng template dựa trên ANTLR StringTemplate.
2. Tự viết renderer bằng Java.

Template phù hợp khi chỉ cần thay đổi nhẹ bố cục có sẵn hoặc muốn tách phần trình bày khỏi code. Các template built-in nằm trong classpath dưới `org/springframework/shell/component`.

`AbstractComponent` có các API liên quan đến template:

- `setResourceLoader(...)`: cung cấp cơ chế tìm và nạp resource.
- `setTemplateExecutor(...)`: cung cấp bộ thực thi template.
- `setTemplateLocation(...)`: chọn vị trí template cho component.
- `renderTemplateResource(attributes)`: render template với map thuộc tính.

Context có thể chuyển thành template model bằng `toTemplateModel()`. Nhờ vậy, template có thể đọc `name`, `input`, `resultValue`, `message` và các thuộc tính riêng của component.

Khi tùy chỉnh template, hãy giữ các biến context cần thiết để thể hiện cả trạng thái đang nhập lẫn trạng thái kết quả. Nếu chỉ render `resultValue`, người dùng có thể không thấy nội dung đang gõ trong lúc component chạy.

## 9. Hiển thị component bằng renderer Java

Nếu cần bố cục phức tạp hoặc quy tắc hiển thị đặc biệt, có thể đặt renderer bằng `setRenderer(...)`. Renderer là một `Function` nhận context và trả về danh sách `AttributedString`.

Ví dụ renderer cho `StringInput`:

~~~java
import java.util.List;
import java.util.function.Function;

import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStringBuilder;
import org.springframework.shell.component.StringInput.StringInputContext;
import org.springframework.util.StringUtils;

Function<StringInputContext, List<AttributedString>> renderer = context -> {
    AttributedStringBuilder line = new AttributedStringBuilder();
    line.append(context.getName());
    line.append(": ");

    if (context.getResultValue() != null) {
        line.append(context.getResultValue());
    }
    else if (StringUtils.hasText(context.getInput())) {
        line.append(context.getInput());
    }
    else {
        line.append("[Mặc định: " + context.getDefaultValue() + "]");
    }

    return List.of(line.toAttributedString());
};

component.setRenderer(renderer);
~~~

Renderer kiểm tra ba tình huống:

- Nếu đã có `resultValue`, hiển thị kết quả cuối.
- Nếu chưa hoàn tất nhưng có `input`, hiển thị nội dung người dùng đang gõ.
- Nếu chưa có input, hiển thị giá trị mặc định để người dùng biết có thể chấp nhận giá trị nào.

`AttributedString` hỗ trợ style terminal như màu sắc và thuộc tính chữ. Có thể trả nhiều dòng bằng cách trả nhiều phần tử trong danh sách. Renderer nên chỉ chuyển context thành nội dung hiển thị; không thực hiện cập nhật dữ liệu hoặc gọi service nghiệp vụ.

## 10. Điều khiển việc in kết quả cuối

`AbstractComponent.setPrintResults(boolean)` điều khiển việc component có tự in phần kết quả ra console hay không. Mặc định giá trị là `true`.

~~~java
component.setPrintResults(false);
StringInputContext context = component.run(StringInputContext.empty());
String value = context.getResultValue();
~~~

Đặt `false` khi ứng dụng muốn tự quyết định cách trình bày kết quả sau khi component chạy xong, chẳng hạn gom nhiều giá trị vào một bảng hoặc in một thông báo tổng hợp. Việc tắt in kết quả không làm mất dữ liệu trong context; ứng dụng vẫn đọc được `resultValue`.

Không nên tắt kết quả nếu command không có phần output thay thế, vì người dùng có thể không nhận được tín hiệu rằng thao tác nhập đã hoàn tất.

## 11. Kết hợp nhiều component bằng ComponentFlow

Khi cần hỏi nhiều thông tin liên tiếp, có thể tạo từng component riêng lẻ. Tuy nhiên, việc quản lý thứ tự và kết quả sẽ trở nên dài dòng. `ComponentFlow` kết nối nhiều component thành một luồng tương tác.

Spring Shell cung cấp `ComponentFlow.Builder`, có thể inject từ Spring context. Nên dùng `clone().reset()` trước khi khai báo flow mới để tạo builder riêng, không mang cấu hình từ lần sử dụng trước.

Ví dụ wizard tạo workspace:

~~~java
package com.example.cli;

import java.util.List;

import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.component.flow.ComponentFlow.ComponentFlowResult;
import org.springframework.shell.component.flow.SelectItem;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class WorkspaceCommands {

    private final ComponentFlow.Builder componentFlowBuilder;
    private final WorkspaceService workspaceService;

    public WorkspaceCommands(
            ComponentFlow.Builder componentFlowBuilder,
            WorkspaceService workspaceService) {
        this.componentFlowBuilder = componentFlowBuilder;
        this.workspaceService = workspaceService;
    }

    @ShellMethod(key = "workspace setup", value = "Tạo workspace qua các bước tương tác")
    public String setup() {
        List<SelectItem> types = List.of(
                SelectItem.of("Service project", "service"),
                SelectItem.of("Library project", "library"));

        ComponentFlow flow = componentFlowBuilder.clone()
                .reset()
                .withStringInput("name")
                    .name("Tên workspace")
                    .defaultValue("my-workspace")
                    .and()
                .withSingleItemSelector("type")
                    .name("Loại dự án")
                    .selectItems(types)
                    .and()
                .withConfirmationInput("confirm")
                    .name("Tạo workspace với thông tin vừa chọn?")
                    .defaultValue(true)
                    .and()
                .build();

        ComponentFlowResult result = flow.run();

        String name = result.getContext().get("name", String.class);
        String type = result.getContext().get("type", String.class);
        Boolean confirmed = result.getContext().get("confirm", Boolean.class);

        if (!Boolean.TRUE.equals(confirmed)) {
            return "Đã hủy tạo workspace";
        }

        workspaceService.create(name, type);
        return "Đã tạo workspace " + name;
    }
}
~~~

`WorkspaceService` là service nghiệp vụ của ứng dụng ví dụ. Ví dụ cho thấy ba component có ID lần lượt là `name`, `type` và `confirm`. Theo mặc định, flow lưu kết quả component vào context dùng ID làm key; có thể đọc lại qua `ComponentFlowResult.getContext()`.

Các điểm quan trọng:

- `ComponentFlow.Builder` tạo flow bằng chuỗi lời gọi builder.
- `withStringInput`, `withSingleItemSelector` và `withConfirmationInput` thêm các bước nhập liệu.
- `name(...)` đặt tiêu đề hiển thị của mỗi bước.
- `defaultValue(...)` đặt giá trị ban đầu.
- `and()` quay lại builder cha để khai báo component tiếp theo.
- `build()` tạo flow; `run()` thực thi và trả kết quả.

Thứ tự thực thi mặc định là thứ tự component được thêm vào builder. Flow giúp gom các context kết quả và trả về một `ComponentContext` chung để command xử lý sau khi người dùng hoàn tất.

## 12. Chia nhánh luồng bằng next(...)

Không phải wizard nào cũng cần chạy tất cả các bước. Với `next(...)`, component có thể quyết định ID của component tiếp theo dựa trên kết quả hiện tại.

Ví dụ, người dùng chọn loại workspace rồi chỉ nhập thông tin riêng của loại đó:

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withSingleItemSelector("type")
            .name("Loại workspace")
            .selectItems(List.of(
                    SelectItem.of("Service project", "service"),
                    SelectItem.of("Library project", "library")))
            .next(context -> context.getResultItem()
                    .map(item -> item.getItem().equals("service")
                            ? "serviceDetails" : "libraryDetails")
                    .orElse(null))
            .and()
        .withStringInput("serviceDetails")
            .name("Tên module service")
            .next(context -> null)
            .and()
        .withStringInput("libraryDetails")
            .name("Tên artifact library")
            .next(context -> null)
            .and()
        .build();
~~~

Hàm `next(...)` trả về ID của component cần chạy tiếp. Nếu trả về `null` hoặc ID không tồn tại trong flow, flow dừng tại đó. Điều này cho phép tạo wizard có nhánh mà không cần tự viết vòng lặp điều khiển bên ngoài.

Với flow có nhánh, hãy đặt ID component rõ ràng và kiểm tra các đường đi có thể xảy ra. Nếu selector có thể không trả kết quả, xử lý `Optional` trước khi gọi `get()` để tránh `NoSuchElementException`.

## 13. preHandler, postHandler và storeResult trong flow

Các spec của `ComponentFlow.Builder` hỗ trợ hook riêng cho từng component:

- `preHandler(...)`: chạy xử lý trước khi component bắt đầu.
- `postHandler(...)`: chạy xử lý sau khi component hoàn tất.
- `storeResult(boolean)`: bật hoặc tắt việc tự lưu kết quả vào context chung của flow.
- `next(...)`: xác định component tiếp theo.
- `renderer(...)` hoặc `template(...)`: tùy chỉnh cách hiển thị component.

Ví dụ:

Đoạn mã minh họa dùng `auditService` được inject vào command:

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("email")
            .name("Email quản trị")
            .preHandler(context -> context.setMessage(
                    "Dùng địa chỉ email có thể nhận thông báo"))
            .postHandler(context -> auditService.recordInput("email"))
            .storeResult(true)
            .and()
        .build();
~~~

`storeResult(true)` là mặc định của các spec flow. Khi tắt lưu kết quả, component vẫn có context riêng sau khi chạy, nhưng không tự thêm kết quả vào context tổng hợp của flow theo ID. Hãy bật lưu kết quả nếu command cần đọc giá trị đó qua `ComponentFlowResult.getContext()`. Với `StringInputSpec` trong Spring Shell 3.x, tính bắt buộc không được cấu hình bằng `required()`; hãy kiểm tra giá trị nhận được trước khi gọi service nghiệp vụ.

Không nên đặt thao tác ghi dữ liệu quan trọng vào `preHandler` hoặc `postHandler` chỉ vì đây là hook tiện lợi. Hãy dùng chúng cho chuẩn bị context, message, logging nhẹ hoặc điều chỉnh giao diện; nghiệp vụ chính nên được thực hiện sau khi flow trả kết quả và command đã xác nhận dữ liệu cần thiết.

## 14. Khi nào dùng component độc lập và khi nào dùng ComponentFlow?

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Chỉ hỏi một chuỗi hoặc một đường dẫn | Chạy trực tiếp `StringInput` hoặc `PathInput`. |
| Cần một xác nhận trước thao tác | `ConfirmationInput` độc lập. |
| Cần chọn một hoặc nhiều mục | `SingleItemSelector` hoặc `MultiItemSelector`. |
| Cần hỏi nhiều trường theo thứ tự | `ComponentFlow`. |
| Có nhánh phụ thuộc lựa chọn trước | `ComponentFlow` với `next(...)`. |
| Cần tái sử dụng context và kết quả giữa các bước | `ComponentFlow` với `storeResult(true)`. |

Component độc lập cho phép kiểm soát trực tiếp một bước. Flow phù hợp hơn khi nhiều bước có quan hệ với nhau và command cần nhận một context kết quả thống nhất.

## 15. Những lỗi thường gặp

**Không đọc được giá trị sau khi nhập:** hãy dùng context trả về từ `component.run(...)`, hoặc `ComponentFlowResult.getContext()` sau khi `flow.run()` hoàn tất. Không đọc context ban đầu vì nó chưa chứa kết quả.

**Flow không lưu kết quả:** kiểm tra `storeResult(false)` có được cấu hình hay không. Với flow, ID truyền vào `withStringInput("name")` hoặc selector chính là key mặc định dùng để lưu kết quả.

**Template không được nạp:** kiểm tra `ResourceLoader`, `TemplateExecutor` và `templateLocation`. Nếu dùng renderer Java, xác nhận renderer trả về danh sách `AttributedString` không null.

**Không thấy kết quả cuối:** kiểm tra `setPrintResults(false)`. Khi tắt tùy chọn này, command phải tự hiển thị kết quả phù hợp.

**Message không xuất hiện:** kiểm tra context đã được cập nhật trước khi render và template/renderer có đọc `message` cùng `messageLevel` hay không.

**Flow đi nhầm nhánh:** kiểm tra ID trả về từ `next(...)` có trùng chính xác với ID đã khai báo ở builder không. Giá trị `null` hoặc ID không tồn tại làm flow dừng.

**Builder mang cấu hình từ flow trước:** tạo builder mới bằng `componentFlowBuilder.clone().reset()` trước khi khai báo flow khác.

## 16. Kiểm thử vòng đời và hiển thị

Kiểm thử không nên chỉ xác nhận giá trị cuối. Hãy kiểm tra cả các giai đoạn và dữ liệu context:

1. Component nhận context ban đầu rỗng và trả context đã cập nhật.
2. Pre-run handler được gọi trước phần nhập liệu và có thể thiết lập message hoặc tên hiển thị.
3. Post-run handler nhận được kết quả đã hoàn tất.
4. Renderer hiển thị input trong lúc nhập và `resultValue` ở trạng thái cuối.
5. Message cùng `messageLevel` được phản ánh đúng trong output.
6. `setPrintResults(false)` không làm mất giá trị trong context.
7. Flow chạy theo thứ tự builder khi không có `next(...)`.
8. Flow đi đúng nhánh và dừng đúng lúc khi `next(...)` trả `null`.
9. Kết quả được lưu theo ID khi `storeResult(true)`.
10. Template và renderer hoạt động với kích thước terminal khác nhau.

Nên kiểm thử tương tác thực tế trong terminal hoặc pseudo-terminal khi cần xác nhận hành vi phím, di chuyển selector và cách render. Unit test context/renderer hữu ích để xác nhận logic dữ liệu và hiển thị, nhưng không thay thế kiểm thử terminal cho vòng lặp nhập liệu.

## Kết luận

Một interactive component trong Spring Shell 3.x có vòng đời gồm nhận input, cập nhật context, render trạng thái đang chạy, hoàn tất và render kết quả cuối. `ComponentContext` giữ dữ liệu chung và các trường chuyên biệt như `input`, `resultValue`, `message` hoặc trạng thái selector. `AbstractComponent` cung cấp pre-run/post-run handler, renderer, template và tùy chọn in kết quả. Khi cần kết hợp nhiều bước, `ComponentFlow` điều khiển thứ tự, lưu kết quả theo ID và hỗ trợ rẽ nhánh qua `next(...)`. Hiểu rõ ba phần vòng đời, context và rendering giúp component dễ tùy chỉnh, kiểm thử và tái sử dụng.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Flow Components](https://docs.spring.io/spring-shell/reference/3.4/components/ui/)
- [Spring Shell 3.4 – Flow](https://docs.spring.io/spring-shell/reference/3.4/components/flow/index.html)
- [Spring Shell 3.4 – Component Render](https://docs.spring.io/spring-shell/reference/3.4/components/ui/render.html)
- [Spring Shell 3.4 API – AbstractComponent](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/support/AbstractComponent.html)
- [Spring Shell 3.4 API – AbstractTextComponent](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/support/AbstractTextComponent.html)
- [Spring Shell 3.4 API – StringInput](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/StringInput.html)
- [Spring Shell 3.4 API – ComponentFlow.Builder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.Builder.html)
- [Spring Shell 3.4 API – ComponentContext](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/context/ComponentContext.html)
- [Spring Shell 3.4 API – TemplateExecutor](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/style/TemplateExecutor.html)
