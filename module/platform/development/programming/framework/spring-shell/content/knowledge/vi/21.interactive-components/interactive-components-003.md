# `StringInput` cho chuỗi và giá trị mặc định

Một command đôi khi cần hỏi thêm thông tin sau khi người dùng đã gọi lệnh. Ví dụ, command tạo hồ sơ có thể yêu cầu nhập tên hiển thị; command cấu hình có thể hỏi tên môi trường hoặc nhãn của một tài nguyên. Nếu giá trị thường dùng đã biết, ứng dụng có thể đưa ra giá trị mặc định để người dùng chấp nhận hoặc chỉnh sửa.

Spring Shell 3.x cung cấp component `StringInput` để nhận một chuỗi trong terminal. Component hiển thị tên trường, giá trị mặc định nếu có, cho phép người dùng nhập hoặc sửa nội dung và trả kết quả qua `StringInputContext`. Với một quy trình gồm nhiều câu hỏi, `ComponentFlow` có thể kết hợp nhiều component và lưu kết quả theo ID.

Bài viết dùng API Spring Shell 3.4.x trong package `org.springframework.shell.component`. Đây là component nhập liệu tương tác trong lúc command đang chạy, không phải annotation khai báo option của command.

## `StringInput` dùng để làm gì?

`StringInput` là component dành cho một giá trị văn bản. Nó phù hợp với các dữ liệu như:

- Tên hiển thị hoặc tên dự án.
- Mô tả ngắn, nhãn hoặc ghi chú.
- Tên môi trường hoặc vùng triển khai.
- Một chuỗi cấu hình mà người dùng có thể thay đổi trước khi lưu.

Luồng sử dụng cơ bản:

```mermaid
flowchart TD
    A[Người dùng gọi command] --> B[Command tạo StringInput]
    B --> C[Đặt tên trường và giá trị mặc định]
    C --> D[Component hiển thị prompt]
    D --> E[Người dùng nhập hoặc giữ giá trị]
    E --> F[StringInputContext]
    F --> G[getResultValue()]
    G --> H[Kiểm tra và xử lý nghiệp vụ]
```

Component có vòng lặp nhận phím riêng. Sau khi người dùng hoàn tất, `run(...)` trả về một `StringInputContext` chứa thông tin của lần nhập. Command đọc giá trị cuối cùng từ context rồi chuyển sang bước nghiệp vụ.

## Tạo một `StringInput` đơn giản

Trong Spring Shell 3.x, `StringInput` nằm trong package `org.springframework.shell.component`. Constructor phổ biến nhận terminal, tên trường và giá trị mặc định:

```java
new StringInput(terminal, name, defaultValue)
```

Ví dụ command yêu cầu người dùng nhập tên hiển thị:

```java
import org.springframework.shell.component.StringInput;
import org.springframework.shell.component.StringInput.StringInputContext;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.util.StringUtils;

@ShellComponent
public class ProfileCommands extends AbstractShellComponent {

    @ShellMethod(key = "profile ask-name", value = "Nhập tên hiển thị")
    public String askName() {
        StringInput input = new StringInput(
                getTerminal(), "Tên hiển thị", "Nguyen Van An");
        input.setResourceLoader(getResourceLoader());
        input.setTemplateExecutor(getTemplateExecutor());

        StringInputContext context = input.run(StringInputContext.empty());
        String name = context.getResultValue();

        if (!StringUtils.hasText(name)) {
            return "Tên hiển thị không được để trống.";
        }

        return "Tên đã chọn: " + name;
    }
}
```

`AbstractShellComponent` cung cấp các tài nguyên mà component cần dùng:

- `getTerminal()` trả về JLine `Terminal` hiện tại.
- `getResourceLoader()` cung cấp bộ nạp template.
- `getTemplateExecutor()` cung cấp bộ thực thi template của Spring Shell.

Sau khi tạo component, hãy thiết lập `ResourceLoader` và `TemplateExecutor` trước khi gọi `run(...)`. `StringInputContext.empty()` tạo context ban đầu chưa có giá trị nhập. Khi component kết thúc, `getResultValue()` trả về chuỗi kết quả để command kiểm tra và sử dụng.

## Đặt giá trị mặc định

Giá trị mặc định được truyền vào constructor:

```java
StringInput input = new StringInput(
        getTerminal(), "Tên môi trường", "development");
```

Giá trị này giúp người dùng nhận biết lựa chọn thường dùng và có thể giữ nguyên hoặc chỉnh sửa trước khi hoàn tất. Nếu không có giá trị phù hợp để đề xuất, truyền `null`:

```java
StringInput input = new StringInput(
        getTerminal(), "Mô tả", null);
```

`StringInputContext` cũng có factory method để khởi tạo context:

```java
StringInputContext.empty();
StringInputContext.of("development", null);
```

`empty()` tạo context rỗng. `of(defaultValue, maskCharacter)` tạo context với giá trị mặc định và ký tự che nếu cần. Khi component đã được tạo với default value trong constructor, cách dùng thường gặp là truyền `StringInputContext.empty()` vào `run(...)`, như ví dụ chính thức.

Giá trị mặc định nên là một gợi ý an toàn và có ý nghĩa. Không đặt mật khẩu, token, API key hoặc bí mật vào default value vì component có thể hiển thị giá trị đó trên terminal hoặc trong template.

### Phân biệt giá trị mặc định, input và kết quả

`StringInputContext` kế thừa `TextComponentContext`, do đó có thể đọc các thông tin sau:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getName()` | Tên hoặc nhãn của trường nhập |
| `getDefaultValue()` | Giá trị mặc định đã cấu hình |
| `getInput()` | Nội dung người dùng đang nhập trong quá trình tương tác |
| `getResultValue()` | Giá trị cuối cùng sau khi component hoàn tất |
| `getMaskedInput()` | Nội dung nhập đã được che theo mask, nếu có |
| `getMaskedResultValue()` | Kết quả đã được che theo mask, nếu có |

Trong command nghiệp vụ, thường chỉ cần `getResultValue()`. `getInput()` hữu ích khi viết renderer tùy chỉnh vì nó phản ánh phần đang được nhập trước khi có kết quả cuối.

Không nên lấy `getDefaultValue()` làm kết quả nghiệp vụ một cách trực tiếp. Hãy đọc `getResultValue()` sau `run(...)`, rồi áp dụng validation cho giá trị thực tế mà component trả về.

## Nhận biết và kiểm tra chuỗi rỗng

`StringInput` nhận dữ liệu dạng `String`; component không tự biết chuỗi đó có hợp lệ theo quy tắc nghiệp vụ hay không. Sau khi nhập, command cần kiểm tra các điều kiện như:

- Không được null hoặc rỗng.
- Không được chỉ chứa khoảng trắng.
- Có giới hạn độ dài.
- Phải tuân theo định dạng hoặc tập ký tự cho phép.

Ví dụ kiểm tra tên trước khi lưu:

```java
String name = context.getResultValue();

if (!StringUtils.hasText(name)) {
    return "Vui lòng nhập tên có ít nhất một ký tự khác khoảng trắng.";
}

String normalizedName = name.trim();
if (normalizedName.length() > 80) {
    return "Tên không được vượt quá 80 ký tự.";
}

profileService.rename(normalizedName);
```

`StringUtils.hasText(...)` kiểm tra chuỗi có ít nhất một ký tự không phải whitespace. `trim()` chuẩn hóa khoảng trắng ở hai đầu nếu quy tắc dữ liệu của ứng dụng yêu cầu. Hãy giữ nguyên khoảng trắng bên trong nếu nó có ý nghĩa với tên hoặc mô tả.

Ở Spring Shell 3.4.x, API `StringInput` độc lập không thay thế Bean Validation. Hãy kiểm tra kết quả trong command hoặc application service. Với `ComponentFlow`, có thể dùng `preHandler` và `postHandler` để bổ sung xử lý trước và sau một component; quy tắc nghiệp vụ quan trọng vẫn nên được bảo vệ trong service.

## Che ký tự khi nhập dữ liệu nhạy cảm

`StringInput` hỗ trợ `setMaskCharacter(Character)` để che phần nhập và kết quả hiển thị:

```java
StringInput input = new StringInput(
        getTerminal(), "Mã truy cập", null);
input.setResourceLoader(getResourceLoader());
input.setTemplateExecutor(getTemplateExecutor());
input.setMaskCharacter('*');

StringInputContext context = input.run(StringInputContext.empty());
String accessCode = context.getResultValue();
```

Context cung cấp các phương thức:

- `hasMaskCharacter()` cho biết có thiết lập ký tự che hay không.
- `getMaskCharacter()` trả về ký tự che.
- `getMaskedInput()` trả về phần nhập đã che.
- `getMaskedResultValue()` trả về kết quả đã che.

Mask chỉ điều khiển cách hiển thị. `getResultValue()` vẫn là giá trị thật để ứng dụng xử lý; việc che ký tự không mã hóa hay bảo vệ chuỗi trong bộ nhớ. Vì vậy:

- Không nối `accessCode` vào thông báo kết quả.
- Không ghi giá trị thật vào log hoặc lịch sử command.
- Không đưa bí mật vào template tùy chỉnh.
- Chỉ giữ giá trị trong phạm vi cần thiết và chuyển giao an toàn cho service.

Nếu ứng dụng xử lý mật khẩu hoặc token, hãy cân nhắc một cơ chế nhập bí mật chuyên dụng và không lưu `String` lâu hơn cần thiết. `StringInput` hữu ích cho trường nhập cần che ký tự, nhưng không thay thế secret management.

## Tùy chỉnh cách hiển thị bằng renderer

Constructor thứ tư nhận một renderer có kiểu:

```java
Function<StringInputContext, List<AttributedString>>
```

Renderer nhận context và trả về danh sách `AttributedString` để component hiển thị. Có thể dùng renderer mặc định nếu giao diện đã phù hợp. Khi cần thay đổi cách trình bày, tạo một hàm riêng:

```java
import java.util.List;
import java.util.function.Function;

import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStringBuilder;
import org.springframework.shell.component.StringInput.StringInputContext;
import org.springframework.util.StringUtils;

public class NameInputRenderer
        implements Function<StringInputContext, List<AttributedString>> {

    @Override
    public List<AttributedString> apply(StringInputContext context) {
        AttributedStringBuilder builder = new AttributedStringBuilder();
        builder.append(context.getName());
        builder.append(": ");

        if (context.getResultValue() != null) {
            builder.append(context.getResultValue());
        }
        else if (StringUtils.hasText(context.getInput())) {
            builder.append(context.getInput());
        }
        else if (context.getDefaultValue() != null) {
            builder.append("[Mặc định: ");
            builder.append(context.getDefaultValue());
            builder.append("]");
        }

        return List.of(builder.toAttributedString());
    }
}
```

Gắn renderer khi tạo component:

```java
StringInput input = new StringInput(
        getTerminal(),
        "Tên hiển thị",
        "Nguyen Van An",
        new NameInputRenderer());
input.setResourceLoader(getResourceLoader());
input.setTemplateExecutor(getTemplateExecutor());

StringInputContext context = input.run(StringInputContext.empty());
```

Renderer nên chỉ chịu trách nhiệm trình bày. Không đặt truy vấn database, gọi API mạng hoặc thay đổi dữ liệu nghiệp vụ trong `apply(...)`, vì renderer có thể được gọi nhiều lần trong quá trình nhập. Với trường nhạy cảm, không hiển thị `getResultValue()` hoặc `getDefaultValue()` dạng rõ; dùng `getMaskedInput()` và `getMaskedResultValue()` khi cần hiển thị trạng thái đã che.

## Dùng `StringInput` trong `ComponentFlow`

Khi command cần hỏi nhiều trường, có thể tạo từng component độc lập, nhưng việc quản lý thứ tự và kết quả sẽ trở nên rời rạc. `ComponentFlow` gom các component thành một wizard. Trong flow, `withStringInput(id)` tạo một trường nhập chuỗi; `.name(...)` đặt nhãn và `.defaultValue(...)` đặt giá trị mặc định.

Ví dụ flow hỏi tên hiển thị và ghi chú:

```java
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ProfileWizardCommands extends AbstractShellComponent {

    private final ComponentFlow.Builder componentFlowBuilder;
    private final ProfileService profileService;

    public ProfileWizardCommands(
            ComponentFlow.Builder componentFlowBuilder,
            ProfileService profileService) {
        this.componentFlowBuilder = componentFlowBuilder;
        this.profileService = profileService;
    }

    @ShellMethod(key = "profile create", value = "Tạo hồ sơ bằng wizard")
    public String create() {
        ComponentFlow flow = componentFlowBuilder.clone()
                .reset()
                .withStringInput("displayName")
                    .name("Tên hiển thị")
                    .defaultValue("Nguyen Van An")
                    .and()
                .withStringInput("note")
                    .name("Ghi chú")
                    .defaultValue("Khách hàng mới")
                    .and()
                .build();

        ComponentFlow.ComponentFlowResult result = flow.run();
        String displayName = result.getContext()
                .get("displayName", String.class);
        String note = result.getContext()
                .get("note", String.class);

        profileService.create(displayName, note);
        return "Đã tạo hồ sơ cho " + displayName;
    }
}
```

Trong ví dụ, mỗi component có một ID (`displayName`, `note`). Mặc định `storeResult` của `StringInputSpec` là `true`, nên kết quả được lưu vào `ComponentContext` theo ID tương ứng. `flow.run()` trả về `ComponentFlowResult`; command lấy context bằng `getContext()` và đọc giá trị theo key cùng kiểu dữ liệu.

Builder được inject từ Spring Shell. Gọi `clone().reset()` trước khi khai báo một flow mới để tạo cấu hình độc lập từ builder được cung cấp. Các component chạy theo thứ tự khai báo, trừ khi dùng `next(...)` để chuyển hướng hoặc kết thúc flow có điều kiện.

## Phân biệt `defaultValue`, `resultValue` và `ResultMode`

Trong `ComponentFlow`, giá trị mặc định và kết quả đã có là hai khái niệm khác nhau:

| API | Ý nghĩa |
| --- | --- |
| `defaultValue(value)` | Đưa ra giá trị khởi đầu để người dùng có thể giữ hoặc sửa |
| `resultValue(value)` | Cung cấp một kết quả đã có cho component |
| `resultMode(ResultMode.VERIFY)` | Chạy component để người dùng xác nhận hoặc chỉnh sửa kết quả đã cung cấp; component thường dùng result làm giá trị mặc định |
| `resultMode(ResultMode.ACCEPT)` | Chấp nhận ngay `resultValue` và bỏ qua việc chạy component |

`ResultMode` có hai giá trị trong API 3.4.x:

- `VERIFY`: xác minh `resultValue` qua giao diện component. Component thường đặt kết quả đó làm giá trị mặc định để người dùng tiếp tục.
- `ACCEPT`: chấp nhận trực tiếp `resultValue`, bỏ qua vòng nhập và đặt kết quả đó vào context.

Ví dụ xác nhận lại tên đã lưu:

```java
import org.springframework.shell.component.flow.ResultMode;

builder.withStringInput("displayName")
        .name("Tên hiển thị")
        .resultValue(existingName)
        .resultMode(ResultMode.VERIFY)
        .and();
```

Nếu muốn bỏ qua câu hỏi và dùng kết quả đã có:

```java
builder.withStringInput("displayName")
        .name("Tên hiển thị")
        .resultValue(existingName)
        .resultMode(ResultMode.ACCEPT)
        .and();
```

Không dùng `resultValue(...)` thay cho `defaultValue(...)` khi mục tiêu chỉ là gợi ý một giá trị ban đầu. `resultValue` thể hiện rằng ứng dụng đã có kết quả và muốn xác minh hoặc chấp nhận nó theo `ResultMode`.

## Xử lý kết quả và trường hợp người dùng không nhập

Sau khi component chạy, hãy xử lý kết quả trước khi gọi service:

```java
String value = context.getResultValue();

if (!StringUtils.hasText(value)) {
    return "Bạn cần nhập giá trị trước khi tiếp tục.";
}

String normalized = value.trim();
if (normalized.length() > 120) {
    return "Giá trị không được vượt quá 120 ký tự.";
}

configurationService.updateLabel(normalized);
```

Trong flow nhiều bước, có thể dùng `preHandler(...)` để chuẩn bị context trước khi chạy và `postHandler(...)` để xử lý context sau khi component kết thúc. `next(...)` cho phép quyết định component tiếp theo dựa trên giá trị vừa nhập; trả `null` hoặc ID không tồn tại sẽ kết thúc flow.

Với Spring Shell 3.4.x, `StringInputSpec` cung cấp `defaultValue`, `maskCharacter`, `renderer`, `template`, `preHandler`, `postHandler`, `resultValue`, `resultMode`, `storeResult` và `next`. Không nên mặc định có builder method `required()` trong mọi bản 3.4.x; nếu trường bắt buộc, hãy kiểm tra chuỗi sau khi nhập và trả thông báo phù hợp.

## Giới hạn trong non-interactive mode

`StringInput` cần terminal có khả năng nhận tương tác từ người dùng. Khi command chạy trong CI, script hoặc tiến trình không có TTY, không thể giả định người dùng sẽ trả lời prompt.

`AbstractComponent.hasTty()` là phương thức `protected`, dành cho logic nội bộ của component; command bên ngoài không thể gọi trực tiếp để kiểm tra. Với command cần hỗ trợ cả người dùng lẫn automation, hãy thiết kế nhánh non-interactive rõ ràng theo cấu hình runner của ứng dụng và cung cấp option command-line để truyền giá trị trong script. Chỉ mở `StringInput` trong nhánh tương tác khi người dùng có thể trả lời prompt.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Quên `setResourceLoader` hoặc `setTemplateExecutor` | Template mặc định có thể không được nạp đúng | Thiết lập hai dependency trước `run(...)` |
| Đọc `getInput()` sau khi component kết thúc để lấy kết quả | Có thể đọc nội dung trung gian thay vì kết quả cuối | Dùng `getResultValue()` |
| Coi default value là kết quả đã xác thực | Dữ liệu mặc định có thể không còn phù hợp với quy tắc hiện tại | Kiểm tra kết quả sau khi nhập |
| Dùng `resultValue` thay cho `defaultValue` | Component có thể chạy theo chế độ xác minh hoặc chấp nhận kết quả | Chọn đúng API và `ResultMode` |
| Không kiểm tra chuỗi trắng | Dữ liệu rỗng được lưu như tên hoặc nhãn hợp lệ | Dùng `StringUtils.hasText` và chuẩn hóa theo quy tắc |
| Nghĩ `maskCharacter` mã hóa dữ liệu | Giá trị thật vẫn có trong context và bộ nhớ | Chỉ xem mask là bảo vệ hiển thị; không log hoặc echo dữ liệu thật |
| Gọi `StringInput` trong CI không có TTY | Command có thể không nhận được input | Dùng option hoặc nhánh xử lý non-interactive |
| Dùng một `ComponentFlow.Builder` mutable cho nhiều flow mà không reset | Cấu hình component trước có thể ảnh hưởng flow sau | Clone và reset builder trước khi khai báo flow mới |
| Ghi đè kết quả bằng custom renderer | Người dùng thấy dữ liệu không phản ánh trạng thái thực | Chỉ trình bày context; để component quản lý input/result |

## Kiểm thử `StringInput`

Kiểm thử nên bao gồm giá trị mặc định, dữ liệu người dùng nhập và cách command xử lý kết quả:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Có default value | Context nhận đúng giá trị mặc định và renderer hiển thị phù hợp |
| Không có default value | `getDefaultValue()` trả `null` |
| Người dùng thay đổi giá trị | `getResultValue()` chứa giá trị cuối cùng |
| Người dùng giữ giá trị gợi ý | Kết quả theo đúng hành vi mặc định của component |
| Chuỗi rỗng hoặc whitespace | Command từ chối nếu nghiệp vụ yêu cầu nội dung |
| Mask bật | Input/result được hiển thị bằng ký tự che |
| Renderer tùy chỉnh | Nhãn, input, default và result được trình bày đúng |
| Flow nhiều trường | Kết quả được lưu theo từng ID trong `ComponentContext` |
| `ResultMode.VERIFY` | Giá trị đã có được đưa vào bước xác minh |
| `ResultMode.ACCEPT` | Component bỏ qua nhập liệu và chấp nhận kết quả |
| Không có TTY | Command dùng fallback hoặc báo cần terminal tương tác |

Đối với unit test, có thể kiểm tra renderer và phần kiểm tra chuỗi bằng context tạo sẵn. Với hành vi nhập phím, default value và TTY, nên dùng test harness terminal của Spring Shell để chạy component trong môi trường terminal mô phỏng. Unit test chỉ tạo context không chứng minh người dùng thực sự có thể sửa hoặc chấp nhận giá trị trong REPL.

## Quy trình sử dụng `StringInput`

1. Xác định dữ liệu cần hỏi là một chuỗi đơn hay một phần của wizard nhiều trường.
2. Với một trường đơn, tạo `StringInput` bằng terminal, tên trường và default value.
3. Thiết lập `ResourceLoader` và `TemplateExecutor`, sau đó gọi `run(StringInputContext.empty())`.
4. Đọc `getResultValue()` và kiểm tra null, chuỗi trắng, độ dài hoặc định dạng.
5. Nếu cần che ký tự, dùng `setMaskCharacter()` và không echo giá trị thật.
6. Nếu cần nhiều trường, dùng `ComponentFlow.Builder`, đặt ID và `defaultValue()` cho từng `StringInputSpec`.
7. Phân biệt `defaultValue`, `resultValue` và `ResultMode` khi xác minh dữ liệu đã có.
8. Kiểm thử cả terminal tương tác lẫn trường hợp không có TTY.

`StringInput` giúp command hỏi một chuỗi ngay trong terminal và đưa ra giá trị mặc định để giảm thao tác nhập. Khi cần nhiều câu hỏi, `ComponentFlow` gom các trường thành một luồng và lưu kết quả theo ID. Hãy luôn kiểm tra kết quả trước khi lưu dữ liệu, dùng mask đúng mục đích và cung cấp đường chạy khác cho script không có terminal tương tác.

## Tài liệu tham khảo

- [StringInput API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/StringInput.html)
- [StringInputContext API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/StringInput.StringInputContext.html)
- [BaseStringInput API – Spring Shell 3.4.2](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/BaseStringInput.html)
- [StringInputSpec API – Spring Shell 3.4.3-SNAPSHOT](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/component/flow/StringInputSpec.html)
- [ComponentFlow – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/components/flow/index.html)
- [ComponentFlow API – Spring Shell 3.4.3-SNAPSHOT](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/component/flow/ComponentFlow.html)
- [ComponentFlowResult API – Spring Shell 3.4.3-SNAPSHOT](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html)
- [ResultMode API – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ResultMode.html)
- [Component Rendering – Spring Shell](https://docs.spring.io/spring-shell/reference/components/ui/render.html)
