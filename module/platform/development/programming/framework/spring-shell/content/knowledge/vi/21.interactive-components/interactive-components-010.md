# Tùy biến thông báo, nhãn và trạng thái cuối cùng

Một luồng nhập liệu trong CLI không chỉ cần hỏi người dùng một câu rồi lấy giá trị. Người dùng cần biết đang nhập thông tin gì, vì sao thông tin đó cần thiết, lỗi nhập liệu nằm ở đâu và kết quả đã được ghi nhận hay chưa. Nếu mọi thành phần đều hiển thị cùng một nhãn chung chung, cùng một thông báo và cùng một dòng kết thúc, luồng tương tác sẽ khó hiểu.

Spring Shell 3.3 cho phép tùy biến giao diện của các component tương tác qua context, handler, template và renderer. Với nhóm nhập văn bản như `StringInput`, `PathInput` và `ConfirmationInput`, context có thể chứa tên component, nội dung đang nhập, giá trị kết quả, thông báo và mức thông báo. Với selector, template có thêm trạng thái danh sách và cờ cho biết component đang hiển thị kết quả cuối cùng.

Bài này tập trung vào cách điều khiển ba phần người dùng nhìn thấy:

- **Nhãn (name):** tiêu đề hoặc câu hỏi gắn với component.
- **Thông báo (message):** hướng dẫn, cảnh báo hoặc lỗi đi kèm đầu vào.
- **Trạng thái cuối (result state):** cách component trình bày giá trị sau khi người dùng hoàn tất, hoặc khi một giá trị có sẵn được chấp nhận.

Sau bài này, bạn có thể:

- Đặt tên dễ hiểu cho từng component trong `ComponentFlow`.
- Gắn thông báo `INFO`, `WARN` hoặc `ERROR` vào context.
- Dùng `preHandler` và `postHandler` để chuẩn bị hoặc cập nhật trạng thái component.
- Tùy biến giao diện bằng StringTemplate hoặc renderer Java.
- Phân biệt trạng thái đang nhập và trạng thái kết quả.
- Chọn `ResultMode.ACCEPT` hoặc `ResultMode.VERIFY` theo cách xử lý giá trị có sẵn.
- Đọc kết quả flow và tạo thông báo hoàn tất phù hợp với nghiệp vụ.

> Ví dụ dùng API component flow của Spring Shell 3.3.x trong package `org.springframework.shell.component` và `org.springframework.shell.component.flow`.

## 1. Vòng đời hiển thị của một component

Các component tích hợp như nhập chuỗi, nhập đường dẫn, xác nhận và chọn mục thường đi qua một vòng đời:

1. Bắt đầu vòng lặp nhận input.
2. Tạo context riêng cho component.
3. Render trạng thái đang tương tác.
4. Kết thúc vòng lặp khi người dùng hoàn tất hoặc component chấp nhận kết quả.
5. Render trạng thái cuối cùng.

~~~mermaid
flowchart TD
    A[Flow gọi component] --> B[Tạo component context]
    B --> C[preHandler chuẩn bị nhãn / message]
    C --> D[Render trạng thái đang nhập]
    D --> E[Người dùng nhập hoặc chọn]
    E --> F{Đã hoàn tất?}
    F -->|Chưa| D
    F -->|Rồi| G[postHandler cập nhật context]
    G --> H[Render trạng thái cuối]
    H --> I[storeResult vào ComponentContext]
    I --> J[Flow tiếp tục hoặc kết thúc]
~~~

Điểm cần nhớ là component có thể render nhiều lần trong lúc người dùng di chuyển, gõ hoặc lọc danh sách. Khi kết thúc, component render thêm trạng thái kết quả. Một renderer tốt phải phân biệt được hai thời điểm này để không hiển thị giá trị kết quả như thể người dùng vẫn đang nhập.

## 2. Đặt nhãn bằng name()

Trong `ComponentFlow`, mỗi component có một ID dùng để định danh trong flow và một `name` dùng làm nhãn hiển thị. Hai giá trị này có mục đích khác nhau:

| Thuộc tính | Dùng để | Ví dụ |
|---|---|---|
| ID trong `withStringInput("project")` | Lưu kết quả và điều hướng giữa các bước | `project` |
| `name("Tên dự án")` | Hiển thị nhãn cho người dùng | `Tên dự án` |

Ví dụ:

~~~java
ComponentFlow flow = componentFlowBuilder.clone().reset()
        .withStringInput("project")
            .name("Tên dự án")
            .defaultValue("demo")
            .and()
        .withConfirmationInput("confirm")
            .name("Xác nhận tạo dự án")
            .defaultValue(false)
            .and()
        .build();
~~~

Nhãn nên nói rõ giá trị cần nhập hoặc hành động cần xác nhận. Tránh dùng tên nội bộ như `field1`, `step2` hoặc `inputA` làm nội dung hiển thị. ID vẫn có thể ngắn và ổn định để code dễ tham chiếu.

`name()` có trên các spec nhập chuỗi, đường dẫn, xác nhận và selector. Khi component được render bằng template hoặc renderer riêng, context cung cấp tên qua `getName()` hoặc biến template `name`.

## 3. Gắn thông báo và mức thông báo

Các context dựa trên `AbstractTextComponent.TextComponentContext` hỗ trợ thông báo. Có thể đặt message bằng `setMessage(...)`:

~~~java
import org.springframework.shell.component.support.AbstractTextComponent.TextComponentContext.MessageLevel;

context.setMessage("Nhập mã dự án gồm chữ thường và dấu gạch ngang.", MessageLevel.INFO);
~~~

Ba mức thông báo:

| Mức | Dùng khi | Ví dụ |
|---|---|---|
| `INFO` | Hướng dẫn hoặc thông tin bổ sung | `Nhập mã dự án, ví dụ billing-api.` |
| `WARN` | Cảnh báo về lựa chọn hoặc dữ liệu | `Tên này đã tồn tại trong môi trường thử nghiệm.` |
| `ERROR` | Đầu vào hoặc thao tác không hợp lệ | `Mã dự án chỉ được chứa chữ thường, số và dấu gạch ngang.` |

Context cũng có các phương thức:

- `getMessage()` và `setMessage(String)`.
- `getMessageLevel()` và `setMessageLevel(MessageLevel)`.
- `setMessage(String, MessageLevel)` để đặt cả nội dung và mức trong một lần gọi.

Các biến template tương ứng gồm `message`, `messageLevel`, `hasMessageLevelInfo`, `hasMessageLevelWarn` và `hasMessageLevelError`. Template có thể dùng các cờ này để chọn biểu tượng hoặc style phù hợp.

Ví dụ dùng mức ERROR khi ứng dụng có sẵn một giá trị cần người dùng sửa:

~~~java
.withStringInput("project")
    .name("Mã dự án")
    .resultValue("Billing API")
    .resultMode(ResultMode.VERIFY)
    .preHandler(context -> context.setMessage(
            "Mã dự án không được chứa khoảng trắng hoặc chữ hoa.",
            MessageLevel.ERROR))
    .and()
~~~

Component đưa giá trị hiện tại ra để người dùng xác minh hoặc chỉnh sửa, còn message giải thích lý do cần thay đổi. Khi command xử lý input, vẫn phải kiểm tra lại quy tắc ở tầng nghiệp vụ.

### Đặt thông báo trước khi component chạy

`preHandler` được gọi trước khi component bắt đầu tương tác. Đây là nơi phù hợp để đặt hướng dẫn:

~~~java
.withStringInput("project")
    .name("Tên dự án")
    .defaultValue("demo")
    .preHandler(context -> context.setMessage(
            "Dùng chữ thường, số và dấu gạch ngang.",
            MessageLevel.INFO))
    .and()
~~~

`preHandler` nhận context cụ thể của component. Với `StringInput`, context là `StringInput.StringInputContext`; với xác nhận, context là `ConfirmationInput.ConfirmationInputContext`. Cả hai đều kế thừa `TextComponentContext`, nên có thể đặt tên, message, message level và giá trị kết quả.

### Cập nhật thông báo sau khi nhập

`postHandler` chạy sau khi component kết thúc. Có thể dùng nó để cập nhật thông báo gắn với kết quả:

~~~java
.withStringInput("project")
    .name("Tên dự án")
    .postHandler(context -> {
        String value = context.getResultValue();
        if (value != null && !value.isBlank()) {
            context.setMessage(
                    "Đã nhận tên dự án: " + value,
                    MessageLevel.INFO);
        }
    })
    .and()
~~~

Vì component render trạng thái cuối sau khi thoát vòng lặp, message được cập nhật trong handler có thể được dùng khi trình bày kết quả cuối. Nếu dùng renderer riêng, hãy đọc `getMessage()` và `getMessageLevel()` để hiển thị đúng trạng thái.

Thông báo trong context là dữ liệu trình bày. Nó không tự xác thực đầu vào và cũng không tự làm flow chuyển sang nhánh khác. Quy tắc hợp lệ phải được kiểm tra trong logic ứng dụng; nếu cần điều hướng, dùng `next(...)` hoặc quyết định tiếp tục flow dựa trên kết quả.

## 4. Thông báo nào dùng được cho loại component nào?

Không phải mọi context đều có cùng tập thuộc tính:

| Loại component | Dữ liệu context đáng chú ý | Cách tùy biến |
|---|---|---|
| `StringInput` | `name`, `input`, `resultValue`, `message`, `messageLevel`, `defaultValue`, dữ liệu mask | `preHandler`, `postHandler`, `renderer`, `template` |
| `PathInput` | Tên, input, kết quả, message và message level | `preHandler`, `postHandler`, `renderer`, `template` |
| `ConfirmationInput` | Tên, kết quả boolean, default value, message và message level | `preHandler`, `postHandler`, `renderer`, `template` |
| `SingleItemSelector` | Tên, input lọc, danh sách item state, danh sách đang hiển thị, `isResult`, `cursorRow` | `preHandler`, `postHandler`, `renderer`, `template` |
| `MultiItemSelector` | Tên, input lọc, item state và trạng thái kết quả | `preHandler`, `postHandler`, `renderer`, `template` |

Selector dùng `SelectorComponentContext`, không phải `TextComponentContext`. Vì vậy, không giả định selector có `setMessage()` giống `StringInput`. Với selector, thường tùy biến nhãn, danh sách, vị trí con trỏ và trạng thái kết quả trong template hoặc renderer.

## 5. Tùy biến trạng thái cuối bằng ResultMode

Một component có thể được cung cấp sẵn `resultValue`. `ResultMode` quyết định cách xử lý giá trị này:

| Chế độ | Hành vi |
|---|---|
| `ResultMode.ACCEPT` | Chấp nhận trực tiếp `resultValue`, bỏ qua vòng tương tác và dùng giá trị đó làm kết quả |
| `ResultMode.VERIFY` | Vẫn chạy component để người dùng xác nhận giá trị có sẵn; cách xác minh cụ thể tùy loại component, thường giá trị được đưa thành mặc định để người dùng tiếp tục hoặc chỉnh sửa |

Ví dụ chấp nhận giá trị đã biết:

~~~java
import org.springframework.shell.component.flow.ResultMode;

.withStringInput("region")
    .name("Vùng triển khai")
    .resultValue("ap-southeast-1")
    .resultMode(ResultMode.ACCEPT)
    .and()
~~~

Trong trường hợp này, component không cần hỏi lại người dùng; giá trị được chấp nhận tự động.

Nếu muốn người dùng xác nhận hoặc chỉnh sửa:

~~~java
.withStringInput("region")
    .name("Vùng triển khai")
    .resultValue("ap-southeast-1")
    .resultMode(ResultMode.VERIFY)
    .and()
~~~

Giá trị có sẵn được đưa qua component để người dùng xác minh. Đây là lựa chọn phù hợp khi ứng dụng nạp cấu hình cũ hoặc đề xuất một giá trị mặc định nhưng vẫn muốn người dùng kiểm tra trước khi tiếp tục.

`resultValue` và `defaultValue` không nên bị xem là cùng một khái niệm:

- `defaultValue` là giá trị gợi ý ban đầu cho input.
- `resultValue` là giá trị kết quả được cung cấp sẵn cho component.
- `resultMode` quy định component có chấp nhận ngay hay yêu cầu người dùng xác minh giá trị đó.

## 6. Lưu kết quả để hiển thị thông báo hoàn tất

Các spec flow mặc định bật `storeResult(true)`. Sau khi component chạy, kết quả được lưu trong `ComponentContext` theo ID đã dùng trong `withStringInput`, `withConfirmationInput` hoặc selector.

Ví dụ:

~~~java
ComponentFlow.ComponentFlowResult flowResult = flow.run();
ComponentContext<?> context = flowResult.getContext();

String project = context.get("project", String.class);
Boolean confirmed = context.get("confirm", Boolean.class);
~~~

Nếu cần lấy giá trị đã chọn, hãy dùng đúng kiểu của component. Với xác nhận, kiểu kết quả là `Boolean`; với nhập chuỗi, kiểu là `String`; selector trả về kiểu dữ liệu được cấu hình cho selector.

Command có thể dựa vào kết quả để tạo thông báo cuối:

~~~java
if (!Boolean.TRUE.equals(confirmed)) {
    return "Đã hủy yêu cầu tạo dự án.";
}

return "Đã xác nhận tạo dự án " + project + ".";
~~~

Thông báo này là kết quả nghiệp vụ của command sau khi flow kết thúc. Nó tách biệt với trạng thái cuối mà component tự render trong lúc hoàn tất input.

Nếu gọi `storeResult(false)`, component không tự động ghi kết quả vào `ComponentContext` bằng ID của nó. Chỉ tắt cơ chế này khi ứng dụng có cách lấy hoặc chuyển kết quả khác, chẳng hạn xử lý qua context handler hoặc không cần dùng kết quả trong phần còn lại của flow.

## 7. Tùy biến bằng template

Spring Shell cho phép render component bằng ANTLR StringTemplate. Đây là lựa chọn phù hợp khi muốn sửa bố cục hiện có mà không cần viết nhiều code Java. Các template tích hợp nằm trong classpath dưới `org/springframework/shell/component`.

Trong `ComponentFlow`, có thể chỉ định template cho từng component:

~~~java
.withStringInput("project")
    .name("Tên dự án")
    .template("classpath:/templates/project-input.st")
    .and()
~~~

Vị trí template phải được cung cấp qua `ResourceLoader` mà flow sử dụng. Khi dùng builder được Spring Shell auto-configure, builder thường đã được cấu hình với terminal, resource loader và template executor. Nếu tự tạo component độc lập, cần cung cấp các phụ thuộc này cho component như ví dụ tài liệu Spring Shell.

### Biến template cho input văn bản

Các biến dùng chung của `TextComponentContext`:

| Biến | Ý nghĩa |
|---|---|
| `name` | Nhãn hoặc tiêu đề component |
| `input` | Nội dung người dùng đang nhập |
| `resultValue` | Giá trị sau khi component hoàn tất |
| `message` | Nội dung thông báo |
| `messageLevel` | Mức `INFO`, `WARN` hoặc `ERROR` |
| `hasMessageLevelInfo` | `true` nếu message ở mức INFO |
| `hasMessageLevelWarn` | `true` nếu message ở mức WARN |
| `hasMessageLevelError` | `true` nếu message ở mức ERROR |

Ví dụ template StringTemplate:

~~~text
$name$
$if(message)$
  $if(hasMessageLevelInfo)$[INFO]$endif$
  $if(hasMessageLevelWarn)$[WARN]$endif$
  $if(hasMessageLevelError)$[ERROR]$endif$
  $message$
$endif$
$if(resultValue)$
  Đã chọn: $resultValue$
$else$
  Nhập: $input$
$endif$
~~~

Template dùng các biến của context để thể hiện cả lúc đang nhập và lúc đã có kết quả. Hãy tránh hiển thị giá trị thô khi component đang mask dữ liệu nhạy cảm; với `StringInput` có mask, context cung cấp `maskedInput`, `maskedResultValue`, `maskCharacter` và `hasMaskCharacter`.

### Biến template cho selector

Selector có các biến riêng:

| Biến | Ý nghĩa |
|---|---|
| `name` | Nhãn của selector |
| `input` | Chuỗi lọc người dùng đang nhập |
| `itemStates` | Toàn bộ trạng thái của các item |
| `itemStateView` | Các item hiện đang hiển thị |
| `isResult` | `true` khi selector đang render trạng thái kết quả |
| `cursorRow` | Dòng đang được con trỏ chọn |

`isResult` đặc biệt hữu ích để phân biệt giao diện danh sách đang chọn với phần tóm tắt sau khi chọn xong. Trong trạng thái kết quả, template có thể chuyển từ danh sách dài sang một dòng xác nhận lựa chọn. Với selector nhiều mục, có thể dùng danh sách trạng thái kết quả để trình bày các mục đã chọn.

## 8. Tùy biến bằng renderer Java

Nếu bố cục cần điều kiện phức tạp hoặc dữ liệu cần được định dạng theo logic Java, dùng `renderer(...)`. Renderer là một `Function` nhận context và trả về danh sách `AttributedString`.

Ví dụ renderer cho `StringInput`:

~~~java
import java.util.List;

import org.jline.utils.AttributedString;
import org.springframework.shell.component.StringInput.StringInputContext;

private List<AttributedString> renderProjectInput(StringInputContext context) {
    StringBuilder line = new StringBuilder(context.getName());

    if (context.getResultValue() != null) {
        line.append("  ✓ ").append(context.getResultValue());
    }
    else if (context.getInput() != null && !context.getInput().isBlank()) {
        line.append("  > ").append(context.getInput());
    }
    else if (context.getDefaultValue() != null) {
        line.append("  [Mặc định: ")
                .append(context.getDefaultValue())
                .append("]");
    }

    if (context.getMessage() != null && !context.getMessage().isBlank()) {
        line.append(System.lineSeparator())
                .append(context.getMessage());
    }

    return List.of(new AttributedString(line.toString()));
}
~~~

Gắn renderer vào flow:

~~~java
.withStringInput("project")
    .name("Tên dự án")
    .defaultValue("demo")
    .preHandler(context -> context.setMessage(
            "Nhập tên ngắn, không chứa khoảng trắng.",
            MessageLevel.INFO))
    .renderer(this::renderProjectInput)
    .and()
~~~

Renderer kiểm tra `getResultValue()` trước để biết component đã hoàn tất hay chưa. Khi kết quả đã có, nó hiển thị dấu xác nhận và giá trị cuối; khi chưa có kết quả, nó hiển thị nội dung đang nhập hoặc giá trị mặc định. Message được đưa xuống dòng riêng để không lẫn với giá trị.

Renderer trả `AttributedString` nên có thể áp dụng style của JLine nếu cần. Với bố cục đơn giản, template thường dễ bảo trì hơn; với điều kiện và định dạng phức tạp, renderer Java cho phép dùng logic quen thuộc của ứng dụng.

## 9. Tùy biến selector và trạng thái lựa chọn

Selector đơn có thể dùng `name`, `defaultSelect`, `resultValue`, `resultMode`, `renderer` hoặc `template`:

~~~java
.withSingleItemSelector("region")
    .name("Chọn vùng triển khai")
    .selectItem("Singapore", "ap-southeast-1")
    .selectItem("Tokyo", "ap-northeast-1")
    .selectItem("Frankfurt", "eu-central-1")
    .defaultSelect("Singapore")
    .template("classpath:/templates/region-selector.st")
    .and()
~~~

`name` là nhãn hiển thị; `defaultSelect` chọn sẵn một mục theo tên; `resultValue` có thể cung cấp một giá trị kết quả và `resultMode` quyết định chấp nhận hoặc xác minh giá trị đó. `max(...)` giới hạn số mục hiển thị trong selector.

Với selector nhiều mục, dùng `resultValues(...)` để cung cấp danh sách kết quả có sẵn và `resultMode(...)` để quy định cách xử lý:

~~~java
.withMultiItemSelector("features")
    .name("Chọn tính năng cần bật")
    .selectItems(featureItems)
    .resultValues(List.of("audit", "metrics"))
    .resultMode(ResultMode.VERIFY)
    .max(8)
    .and()
~~~

Template selector có thể dùng `isResult` để hiển thị danh sách mục đang được chọn trong lúc tương tác và phần tóm tắt sau khi hoàn tất. Dùng nhãn mô tả hành động, chẳng hạn `Chọn tính năng cần bật`, thay vì tên kỹ thuật của danh sách.

## 10. Kết hợp nhãn, thông báo và trạng thái cuối trong một flow

Ví dụ dưới đây kết hợp nhập tên dự án và xác nhận tạo. Component đầu hiển thị hướng dẫn; component thứ hai cảnh báo rằng thao tác sẽ tạo tài nguyên. Sau flow, command đọc kết quả và trả thông báo phù hợp.

~~~java
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.component.flow.ComponentFlow.ComponentFlowResult;
import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.support.AbstractTextComponent.TextComponentContext.MessageLevel;

public String createProject() {
    ComponentFlow flow = componentFlowBuilder.clone().reset()
            .withStringInput("project")
                .name("Tên dự án")
                .defaultValue("demo")
                .preHandler(context -> context.setMessage(
                        "Dùng chữ thường, số và dấu gạch ngang.",
                        MessageLevel.INFO))
                .postHandler(context -> context.setMessage(
                        "Đã nhận tên dự án.",
                        MessageLevel.INFO))
                .and()
            .withConfirmationInput("confirm")
                .name("Xác nhận tạo dự án")
                .defaultValue(false)
                .preHandler(context -> context.setMessage(
                        "Thao tác này sẽ tạo một dự án mới.",
                        MessageLevel.WARN))
                .and()
            .build();

    ComponentFlowResult result = flow.run();
    ComponentContext<?> context = result.getContext();

    String project = context.get("project", String.class);
    Boolean confirmed = context.get("confirm", Boolean.class);

    if (!Boolean.TRUE.equals(confirmed)) {
        return "Đã hủy tạo dự án " + project + ".";
    }

    projectService.create(project);
    return "Đã tạo dự án " + project + " thành công.";
}
~~~

Trong ví dụ, `preHandler` chuẩn bị thông báo trước khi component chạy. `postHandler` cập nhật thông báo sau khi nhập. `ComponentFlowResult.getContext()` trả context cuối của flow; `storeResult` mặc định bật nên có thể đọc kết quả bằng ID component. Command quyết định hành động nghiệp vụ sau khi xác nhận.

Trong ứng dụng thực tế, cần kiểm tra tên dự án ở service trước khi tạo và xử lý trường hợp tên đã tồn tại. Message chỉ hướng dẫn người dùng; nó không thay thế validation hoặc kiểm tra quyền.

## 11. Những lựa chọn thường bị nhầm lẫn

| Cần tùy biến | API nên dùng | Không nên nhầm với |
|---|---|---|
| Tiêu đề hoặc câu hỏi | `name(...)` | ID component trong `withStringInput("...")` |
| Hướng dẫn trước khi nhập | `preHandler(...)` và `setMessage(...)` | `defaultValue(...)` |
| Cảnh báo hoặc lỗi | `setMessage(message, MessageLevel)` | Exception hoặc validation tự động |
| Bố cục hiển thị | `template(...)` hoặc `renderer(...)` | Giá trị nghiệp vụ của command |
| Giá trị đã có | `resultValue(...)` | Giá trị mặc định nhập |
| Chấp nhận ngay giá trị có sẵn | `ResultMode.ACCEPT` | Bỏ qua validation nghiệp vụ |
| Yêu cầu người dùng xác minh | `ResultMode.VERIFY` | Một kiểu validation tự động |
| Lưu kết quả flow | `storeResult(true)` và `ComponentFlowResult.getContext()` | Kết quả trả về của command |
| Thông báo hoàn tất nghiệp vụ | Chuỗi trả về từ command sau `flow.run()` | Trạng thái cuối của component |

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Người dùng thấy tên kỹ thuật như `field1` | Chưa gọi `name(...)` hoặc template không dùng biến `name` | Đặt nhãn dễ hiểu và kiểm tra renderer |
| Message không xuất hiện | Template/renderer không đọc `message` hoặc handler đặt message sai thời điểm | Kiểm tra context và `preHandler`/`postHandler` |
| Message có nội dung nhưng không phân biệt mức | Renderer chỉ in message, bỏ qua `messageLevel` | Dùng `MessageLevel` và các biến `hasMessageLevel...` |
| Thông báo hướng dẫn bị lặp ở trạng thái cuối | Renderer luôn in cùng một nội dung mà không kiểm tra `resultValue` | Phân biệt trạng thái đang nhập với trạng thái kết quả |
| Component không hỏi người dùng | Có `resultValue` và `ResultMode.ACCEPT` | Dùng `VERIFY` nếu cần người dùng xác nhận |
| Không đọc được kết quả từ flow context | `storeResult(false)` hoặc dùng sai ID/kiểu | Kiểm tra `storeResult`, ID và kiểu dữ liệu khi gọi `get` |
| Template không được tải | Sai resource location hoặc builder thiếu `ResourceLoader`/`TemplateExecutor` | Kiểm tra classpath và cấu hình flow |
| Selector không hiển thị message như input text | Selector dùng context khác `TextComponentContext` | Tùy biến selector qua `name`, `isResult`, item states và renderer/template |
| Giá trị cuối không được hiển thị | Template không xử lý trạng thái result hoặc renderer chỉ đọc `input` | Dùng `resultValue` hoặc `isResult` phù hợp với loại component |
| Thông báo nói thành công dù người dùng chọn hủy | Command không kiểm tra giá trị xác nhận | Đọc Boolean result và chỉ thực hiện nghiệp vụ khi giá trị là `true` |

## 13. Checklist tùy biến component

- Đặt ID ổn định cho flow và nhãn `name` dễ hiểu cho người dùng.
- Dùng `preHandler` để chuẩn bị hướng dẫn trước khi tương tác.
- Chọn đúng `MessageLevel`: INFO, WARN hoặc ERROR.
- Dùng `postHandler` để cập nhật trạng thái sau khi component kết thúc.
- Chọn template cho thay đổi bố cục nhỏ, renderer Java cho logic hiển thị phức tạp.
- Kiểm tra cả biến trạng thái đang nhập và biến kết quả cuối.
- Với selector, dùng các biến `isResult`, `itemStates`, `itemStateView` và `cursorRow`.
- Chỉ dùng `ResultMode.ACCEPT` khi có thể chấp nhận giá trị có sẵn ngay.
- Dùng `VERIFY` khi cần người dùng xem lại giá trị đã có.
- Kiểm tra `storeResult` trước khi đọc kết quả từ `ComponentFlowResult`.
- Tạo thông báo hoàn tất nghiệp vụ sau khi kiểm tra kết quả flow.
- Không hiển thị dữ liệu bí mật trong message, template hoặc renderer.

## 14. Bài tập thực hành

Tạo flow `project create` gồm ba bước:

1. Nhập mã dự án bằng `StringInput`, nhãn là `Mã dự án`.
2. Chọn môi trường bằng `SingleItemSelector`, nhãn là `Môi trường triển khai`.
3. Xác nhận bằng `ConfirmationInput`, nhãn là `Xác nhận tạo dự án`.
4. Dùng `preHandler` để hiển thị hướng dẫn cho mã dự án ở mức INFO.
5. Nếu mã dự án không đúng quy tắc, cập nhật message mức ERROR và yêu cầu người dùng sửa theo cơ chế kiểm tra của ứng dụng.
6. Dùng `postHandler` để hiển thị thông báo đã nhận giá trị sau mỗi component.
7. Viết template riêng cho bước chọn môi trường; dùng `isResult` để hiển thị danh sách khi đang chọn và giá trị đã chọn ở trạng thái cuối.
8. Thử `ResultMode.VERIFY` với một môi trường đã được cấu hình sẵn.
9. Thử `ResultMode.ACCEPT` để xác nhận component bỏ qua bước nhập khi giá trị được chấp nhận trực tiếp.
10. Đọc kết quả qua `ComponentFlowResult.getContext()` và chỉ tạo dự án khi người dùng xác nhận.
11. Viết thông báo kết thúc riêng cho hai trường hợp xác nhận và hủy.

Khi hoàn thành, hãy giải thích cách `name`, `message`, `renderer/template` và `resultMode` phối hợp để người dùng hiểu từng bước cũng như kết quả cuối.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Flow Components](https://docs.spring.io/spring-shell/reference/3.3/components/ui/index.html): vòng đời component, context và các component tích hợp.
- [Spring Shell 3.3 – Flow](https://docs.spring.io/spring-shell/reference/3.3/components/flow/index.html): xây dựng luồng nhiều component, điều hướng và đọc kết quả.
- [Spring Shell 3.3 – Component Render](https://docs.spring.io/spring-shell/reference/3.3/components/ui/render.html): template variables, renderer function và cách tùy biến giao diện.
- [Spring Shell 3.3 – String Input](https://docs.spring.io/spring-shell/reference/3.3/components/ui/stringinput.html): context nhập chuỗi và dữ liệu mask.
- [Spring Shell 3.3 – Confirmation](https://docs.spring.io/spring-shell/reference/3.3/components/ui/confirmation.html): component xác nhận và context.
- [Spring Shell 3.3 – StringInputSpec API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/StringInputSpec.html): nhãn, message handler, renderer, template và result mode.
- [Spring Shell 3.3 – TextComponentContext API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/support/AbstractTextComponent.TextComponentContext.html): tên, input, result value và message level.
- [Spring Shell 3.3 – ResultMode API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ResultMode.html): hành vi ACCEPT và VERIFY.
- [Spring Shell 3.3 – ComponentFlowResult API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html): truy cập context sau khi flow chạy.
