# Tách thu thập dữ liệu, xác nhận và thực thi nghiệp vụ

Một command có thể cần hỏi người dùng nhiều thông tin trước khi thực hiện một thao tác quan trọng. Nếu vừa đọc input, vừa kiểm tra quy tắc nghiệp vụ, vừa ghi dữ liệu ngay trong từng callback nhập liệu, command sẽ khó kiểm thử và dễ tạo ra tác dụng phụ khi người dùng chưa hoàn tất.

**ComponentFlow** của Spring Shell 3.x gom nhiều component nhập liệu thành một luồng tương tác. Command có thể thu thập các giá trị, lấy chúng từ kết quả flow, kiểm tra dữ liệu, trình bày bản xem trước, hỏi xác nhận rồi mới gọi service nghiệp vụ.

ComponentFlow chịu trách nhiệm điều phối giao diện và giữ kết quả của các bước. Service nghiệp vụ vẫn chịu trách nhiệm kiểm tra quyền, xác thực quy tắc, quản lý transaction và thực hiện thao tác. Tách hai phần này giúp người dùng có cơ hội xem lại và hủy yêu cầu trước khi dữ liệu bị thay đổi.

## 1. Chia command thành các giai đoạn

Một command tương tác có thể được tổ chức thành bốn giai đoạn:

1. **Thu thập:** hỏi các giá trị cần thiết như phiên bản, môi trường, đường dẫn hoặc lựa chọn.
2. **Kiểm tra:** chuyển dữ liệu sang request object và kiểm tra định dạng, tính đầy đủ, quy tắc nghiệp vụ có thể kiểm tra trước.
3. **Xác nhận:** trình bày nội dung sẽ thực hiện và hỏi người dùng có tiếp tục hay không.
4. **Thực thi:** chỉ gọi service khi người dùng xác nhận; service thực hiện kiểm tra cuối cùng và thao tác nghiệp vụ.

~~~mermaid
flowchart TD
    A["Người dùng gọi command"] --> B["ComponentFlow thu thập dữ liệu"]
    B --> C["ComponentContext chứa kết quả"]
    C --> D["Tạo request object"]
    D --> E{"Dữ liệu hợp lệ?"}
    E -->|Không| F["Trả thông báo lỗi"]
    E -->|Có| G["Hiển thị bản xem trước"]
    G --> H["ComponentFlow hỏi xác nhận"]
    H --> I{"Người dùng đồng ý?"}
    I -->|Không| J["Kết thúc, không gọi service"]
    I -->|Có| K["Gọi application service"]
    K --> L["Service kiểm tra cuối và thực thi"]
    L --> M["Trả kết quả command"]
~~~

Điểm quan trọng là không gọi service ghi dữ liệu trong lúc người dùng còn đang nhập. Nếu người dùng đổi ý ở bước xác nhận, command kết thúc mà không tạo thao tác nghiệp vụ.

## 2. ComponentFlow cung cấp những thành phần nào?

Trong Spring Shell 3.x, **ComponentFlow** có thể kết hợp các component nhập liệu phổ biến:

| Builder method | Component | Dữ liệu kết quả thường dùng |
|---|---|---|
| **withStringInput(id)** | Nhập một chuỗi | String |
| **withPathInput(id)** | Nhập đường dẫn | String chứa đường dẫn |
| **withConfirmationInput(id)** | Câu hỏi có/không | Boolean |
| **withSingleItemSelector(id)** | Chọn một mục | Giá trị String của mục được chọn |
| **withMultiItemSelector(id)** | Chọn nhiều mục | Danh sách String |

Mỗi component được định danh bằng một **id**. ID này được dùng để lấy kết quả từ context chung sau khi flow chạy.

Một component có thể đặt tên hiển thị, giá trị mặc định, danh sách lựa chọn, renderer và các handler. Ví dụ:

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("projectName")
            .name("Tên dự án")
            .defaultValue("demo")
            .and()
        .withConfirmationInput("continue")
            .name("Tiếp tục?")
            .defaultValue(false)
            .and()
        .build();
~~~

**name()** là nhãn hiển thị cho người dùng; chuỗi truyền vào **withStringInput()** hoặc **withConfirmationInput()** là ID để lấy kết quả. Hai giá trị này có vai trò khác nhau và không nên dùng nhầm.

## 3. Tạo flow bằng builder

Spring Shell Boot auto-configure một bean **ComponentFlow.Builder**. Có thể inject builder vào command component qua constructor. Builder được cấu hình theo phạm vi prototype; khi tạo flow, tài liệu khuyến nghị gọi **clone().reset()** để bắt đầu một cấu hình mới.

~~~java
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class SetupCommands {

    private final ComponentFlow.Builder componentFlowBuilder;

    public SetupCommands(ComponentFlow.Builder componentFlowBuilder) {
        this.componentFlowBuilder = componentFlowBuilder;
    }

    @ShellMethod(key = "setup wizard", value = "Thu thập thông tin cấu hình.")
    public String setup() {
        ComponentFlow flow = componentFlowBuilder.clone()
                .reset()
                .withStringInput("projectName")
                    .name("Tên dự án")
                    .defaultValue("demo")
                    .and()
                .withConfirmationInput("confirm")
                    .name("Xác nhận cấu hình?")
                    .defaultValue(false)
                    .and()
                .build();

        ComponentFlow.ComponentFlowResult result = flow.run();
        String projectName =
                result.getContext().get("projectName", String.class);
        Boolean confirmed =
                result.getContext().get("confirm", Boolean.class);

        if (!Boolean.TRUE.equals(confirmed)) {
            return "Đã hủy cấu hình.";
        }

        return "Đã xác nhận dự án " + projectName;
    }
}
~~~

Các bước được thực hiện theo thứ tự thêm vào builder. **build()** tạo flow; **run()** bắt đầu hiển thị component và chờ input. Kết quả trả về là **ComponentFlowResult**, có thể lấy **ComponentContext** bằng **getContext()**.

Ví dụ trên chỉ minh họa cách tạo flow và đọc kết quả. Trong ứng dụng thật, nên kiểm tra dữ liệu trước khi xác nhận và chỉ gọi service sau khi nhận được giá trị Boolean **true**.

## 4. Thu thập dữ liệu rồi chuyển thành request object

Không nên để application service phụ thuộc trực tiếp vào **ComponentContext**. Context là cấu trúc dữ liệu phục vụ giao diện; request object là hợp đồng đầu vào của nghiệp vụ.

Ví dụ một lệnh triển khai cần phiên bản, môi trường và ghi chú:

~~~java
public record DeploymentRequest(
        String version,
        String environment,
        String changeNote) {
}
~~~

Flow thu thập các trường:

~~~java
import java.util.List;

import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.component.flow.SelectItem;

List<SelectItem> environments = List.of(
        SelectItem.of("Staging", "staging"),
        SelectItem.of("Production", "production")
);

ComponentFlow collectionFlow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("version")
            .name("Phiên bản")
            .and()
        .withSingleItemSelector("environment")
            .name("Môi trường")
            .selectItems(environments)
            .and()
        .withStringInput("changeNote")
            .name("Ghi chú thay đổi")
            .and()
        .build();

ComponentContext<?> values = collectionFlow.run().getContext();

String version = values.get("version", String.class);
String environment = values.get("environment", String.class);
String changeNote = values.get("changeNote", String.class);
~~~

**SelectItem.of(name, item)** tách nhãn hiển thị khỏi giá trị ứng dụng nhận được. Người dùng thấy **Production**, còn request nhận giá trị ổn định **production**. Không nên dùng nhãn dịch hoặc nội dung hiển thị làm mã định danh nghiệp vụ.

Sau khi lấy giá trị, command tạo request:

~~~java
if (version == null || version.isBlank() || environment == null) {
    return "Thiếu phiên bản hoặc môi trường triển khai.";
}

DeploymentRequest request = new DeploymentRequest(
        version.strip(),
        environment,
        changeNote == null ? "" : changeNote.strip()
);
~~~

**StringInputSpec** của Spring Shell 3.3 không cung cấp một phương thức **required()** trên builder. Vì vậy, không nên giả định trường nhập chuỗi đã được bắt buộc chỉ vì đã khai báo trong flow. Hãy kiểm tra giá trị sau khi thu thập và trả lỗi rõ ràng nếu dữ liệu thiếu.

## 5. Kiểm tra dữ liệu trước khi hỏi xác nhận

Kiểm tra đầu vào có thể chia thành hai lớp:

- **Kiểm tra dữ liệu nhập:** chuỗi rỗng, định dạng phiên bản, đường dẫn không tồn tại, lựa chọn không được hỗ trợ.
- **Kiểm tra quy tắc nghiệp vụ trước:** môi trường có được phép triển khai không, phiên bản có hợp lệ không, người dùng có quyền yêu cầu thao tác không.

Ví dụ command gọi một policy validator trước khi mở bước xác nhận:

~~~java
List<String> problems = deploymentPolicy.validate(request);
if (!problems.isEmpty()) {
    return "Không thể tiếp tục: " + String.join("; ", problems);
}
~~~

Validator này không thực hiện triển khai. Nó chỉ trả về các vấn đề cần giải quyết để command có thể dừng trước khi hỏi xác nhận.

Không coi việc kiểm tra trước xác nhận là bảo đảm cuối cùng. Trạng thái hệ thống có thể thay đổi giữa lúc người dùng xem bản xem trước và lúc service thực thi. Service vẫn phải kiểm tra quyền, điều kiện hiện tại và quy tắc nghiệp vụ trong transaction hoặc tại thời điểm thực hiện.

## 6. Hiển thị bản xem trước và hỏi xác nhận riêng

Sau khi thu thập và kiểm tra, command có thể hiển thị nội dung sẽ thực hiện. Với command dựa trên **AbstractShellComponent**, có thể dùng terminal hiện tại của shell:

~~~java
getTerminal().writer().println("Yêu cầu triển khai:");
getTerminal().writer().println("  Phiên bản: " + request.version());
getTerminal().writer().println("  Môi trường: " + request.environment());
getTerminal().writer().println("  Ghi chú: " + request.changeNote());
getTerminal().writer().flush();
~~~

Sau đó tạo flow xác nhận riêng:

~~~java
ComponentFlow confirmationFlow = componentFlowBuilder.clone()
        .reset()
        .withConfirmationInput("confirmed")
            .name("Bạn có muốn bắt đầu triển khai?")
            .defaultValue(false)
            .and()
        .build();

ComponentContext<?> confirmation =
        confirmationFlow.run().getContext();
Boolean confirmed = confirmation.get("confirmed", Boolean.class);

if (!Boolean.TRUE.equals(confirmed)) {
    return "Đã hủy yêu cầu triển khai.";
}
~~~

Đặt **defaultValue(false)** để Enter không vô tình chấp thuận một thao tác có tác động. Chỉ tiếp tục khi giá trị xác nhận là **Boolean.TRUE**; kiểm tra bằng **Boolean.TRUE.equals()** cũng xử lý an toàn trường hợp giá trị null.

Flow xác nhận không gọi service. Nó chỉ thu thập quyết định của người dùng và trả kết quả cho command.

## 7. Thực thi nghiệp vụ sau khi xác nhận

Sau khi người dùng đồng ý, command mới gọi application service:

~~~java
deploymentService.deploy(request);
return "Đã gửi yêu cầu triển khai.";
~~~

Service nhận **DeploymentRequest**, không nhận **ComponentFlow**, **ComponentContext** hoặc builder. Nhờ vậy, service có thể được tái sử dụng từ REST API, job nền, message consumer hoặc một giao diện khác.

Service cần chịu trách nhiệm:

- Kiểm tra quyền thực hiện thao tác.
- Xác minh trạng thái tài nguyên tại thời điểm thực thi.
- Áp dụng quy tắc nghiệp vụ và transaction.
- Xử lý lỗi, retry và idempotency nếu thao tác có thể được gửi lại.
- Trả kết quả nghiệp vụ để command trình bày cho người dùng.

Confirmation chỉ là xác nhận ý định tại thời điểm tương tác. Nó không thay thế authorization, transaction hoặc kiểm tra trạng thái trong service.

## 8. Ví dụ hoàn chỉnh: thu thập, xác nhận, triển khai

Ví dụ dưới đây kết hợp các giai đoạn thành một command. Các lớp **DeploymentPolicy** và **DeploymentService** là thành phần do ứng dụng định nghĩa.

Hợp đồng nghiệp vụ có thể được khai báo như sau:

~~~java
import java.util.List;

public record DeploymentRequest(
        String version,
        String environment,
        String changeNote) {
}

public interface DeploymentPolicy {
    List<String> validate(DeploymentRequest request);
}

public interface DeploymentService {
    void deploy(DeploymentRequest request);
}
~~~

~~~java
import java.util.List;

import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.component.flow.SelectItem;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class DeploymentCommands extends AbstractShellComponent {

    private final ComponentFlow.Builder componentFlowBuilder;
    private final DeploymentPolicy deploymentPolicy;
    private final DeploymentService deploymentService;

    public DeploymentCommands(
            ComponentFlow.Builder componentFlowBuilder,
            DeploymentPolicy deploymentPolicy,
            DeploymentService deploymentService) {
        this.componentFlowBuilder = componentFlowBuilder;
        this.deploymentPolicy = deploymentPolicy;
        this.deploymentService = deploymentService;
    }

    @ShellMethod(
            key = "deploy wizard",
            value = "Thu thập và xác nhận yêu cầu triển khai."
    )
    public String deployWizard() {
        List<SelectItem> environments = List.of(
                SelectItem.of("Staging", "staging"),
                SelectItem.of("Production", "production")
        );

        ComponentFlow collectionFlow = componentFlowBuilder.clone()
                .reset()
                .withStringInput("version")
                    .name("Phiên bản")
                    .and()
                .withSingleItemSelector("environment")
                    .name("Môi trường")
                    .selectItems(environments)
                    .and()
                .withStringInput("changeNote")
                    .name("Ghi chú thay đổi")
                    .and()
                .build();

        ComponentContext<?> values = collectionFlow.run().getContext();
        String version = values.get("version", String.class);
        String environment = values.get("environment", String.class);
        String changeNote = values.get("changeNote", String.class);

        if (version == null || version.isBlank() || environment == null) {
            return "Thiếu phiên bản hoặc môi trường triển khai.";
        }

        DeploymentRequest request = new DeploymentRequest(
                version.strip(),
                environment,
                changeNote == null ? "" : changeNote.strip()
        );

        List<String> problems = deploymentPolicy.validate(request);
        if (!problems.isEmpty()) {
            return "Không thể tiếp tục: " + String.join("; ", problems);
        }

        getTerminal().writer().println("Yêu cầu triển khai:");
        getTerminal().writer().println("  Phiên bản: " + request.version());
        getTerminal().writer().println("  Môi trường: " + request.environment());
        getTerminal().writer().println("  Ghi chú: " + request.changeNote());
        getTerminal().writer().flush();

        ComponentFlow confirmationFlow = componentFlowBuilder.clone()
                .reset()
                .withConfirmationInput("confirmed")
                    .name("Bạn có muốn bắt đầu triển khai?")
                    .defaultValue(false)
                    .and()
                .build();

        ComponentContext<?> confirmation =
                confirmationFlow.run().getContext();
        Boolean confirmed = confirmation.get("confirmed", Boolean.class);

        if (!Boolean.TRUE.equals(confirmed)) {
            return "Đã hủy yêu cầu triển khai.";
        }

        deploymentService.deploy(request);
        return "Đã gửi yêu cầu triển khai.";
    }
}
~~~

Luồng này có một ranh giới rõ: flow đầu chỉ thu thập dữ liệu; policy kiểm tra request; command trình bày bản xem trước; flow thứ hai lấy xác nhận; service chỉ chạy sau khi người dùng đồng ý.

Nếu người dùng chọn Production nhưng hủy ở bước cuối, **deploymentService.deploy()** không được gọi. Đây là hành vi quan trọng cần kiểm tra bằng test.

## 9. Lưu kết quả vào ComponentContext

Mỗi builder method nhận một ID. Mặc định, component lưu kết quả vào **ComponentContext** bằng ID đó. Ví dụ:

~~~java
ComponentContext<?> context = flow.run().getContext();

String projectName = context.get("projectName", String.class);
Boolean confirmed = context.get("confirm", Boolean.class);
~~~

Các phương thức liên quan:

| API | Vai trò |
|---|---|
| **ComponentFlow.run()** | Chạy flow và trả về kết quả |
| **ComponentFlowResult.getContext()** | Lấy context chung sau khi chạy |
| **ComponentContext.get(id, type)** | Lấy giá trị theo ID và ép kiểu |
| **ComponentContext.containsKey(id)** | Kiểm tra một component đã lưu kết quả hay chưa |
| **storeResult(false)** | Không tự động đưa kết quả component vào context chung |

**storeResult()** mặc định là **true**. Nếu đặt **storeResult(false)**, không thể giả định rằng kết quả vẫn có trong context chung. Khi đó, cần dùng handler hoặc cách lấy context riêng phù hợp.

Nếu flow có nhánh, một số component có thể không chạy. Khi đọc kết quả, hãy kiểm tra **containsKey()** hoặc xử lý null thay vì giả định mọi ID đều có giá trị.

## 10. Thực thi tuần tự và rẽ nhánh bằng next()

Theo mặc định, các component chạy theo thứ tự thêm vào builder. Khi cần bỏ qua hoặc chuyển sang bước khác, dùng **next()** để trả về ID của component kế tiếp.

Ví dụ người dùng chọn dùng cấu hình mặc định hoặc nhập cấu hình tùy chỉnh:

~~~java
import java.util.List;

ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withSingleItemSelector("source")
            .name("Nguồn cấu hình")
            .selectItems(List.of(
                    SelectItem.of("Dùng mặc định", "review"),
                    SelectItem.of("Tự nhập", "customValue")
            ))
            .next(context -> context.getResultItem()
                    .map(item -> item.getItem())
                    .orElse(null))
            .and()
        .withStringInput("customValue")
            .name("Giá trị tùy chỉnh")
            .next(context -> "review")
            .and()
        .withConfirmationInput("review")
            .name("Xác nhận cấu hình?")
            .defaultValue(false)
            .and()
        .build();
~~~

Nếu người dùng chọn **Dùng mặc định**, selector trả về ID **review** và bỏ qua bước nhập tùy chỉnh. Nếu chọn **Tự nhập**, flow chuyển đến **customValue**, rồi từ đó chuyển sang **review**.

Hàm **next()** trả về null hoặc một ID không tồn tại sẽ kết thúc flow tại bước hiện tại. Nó chỉ điều khiển luồng component; không nên gọi service ghi dữ liệu bên trong hàm next.

## 11. Dùng preHandler, postHandler và renderer đúng mục đích

Các spec hỗ trợ handler và renderer để tùy chỉnh một component:

- **preHandler()** đăng ký xử lý trước khi component chạy.
- **postHandler()** đăng ký xử lý sau khi component hoàn tất.
- **renderer()** cung cấp cách hiển thị trạng thái của component.
- **template()** chọn template hiển thị.

Những hook này phù hợp để chuẩn bị trạng thái component, xử lý dữ liệu riêng của bước nhập hoặc thay đổi giao diện. Chúng không nên trở thành nơi gọi nghiệp vụ chính.

Ví dụ, không nên gọi **deploymentService.deploy()** trong postHandler của bước chọn môi trường. Flow có thể còn nhiều bước sau đó; người dùng vẫn có thể hủy ở bước xác nhận. Hãy để command kiểm soát thời điểm gọi service sau khi toàn bộ flow đã trả kết quả.

Với trường nhạy cảm, renderer cần sử dụng giá trị đã che do context cung cấp. Không tự render giá trị thô chỉ vì muốn tùy chỉnh prompt.

## 12. resultValue và ResultMode

Các spec có thể nhận **resultValue()** và **resultMode()** để định nghĩa cách xử lý một giá trị đã biết trước.

| ResultMode | Hành vi |
|---|---|
| **ACCEPT** | Tự chấp nhận resultValue, bỏ qua bước nhập và lưu giá trị làm kết quả |
| **VERIFY** | Hiển thị component để người dùng kiểm tra resultValue; thường dùng giá trị này làm mặc định |

Ví dụ có thể dùng VERIFY khi ứng dụng đề xuất sẵn một môi trường dựa trên cấu hình hiện tại nhưng vẫn muốn người dùng xem lại. ACCEPT phù hợp khi giá trị đã được xác định và không cần hỏi người dùng.

Không dùng **ACCEPT** cho bước xác nhận một thao tác có tác động như xóa, triển khai hoặc ghi đè dữ liệu. Nếu cần sự đồng ý của người vận hành, hãy để component xác nhận thực sự chạy và đặt mặc định an toàn như **false**.

## 13. Không trộn ComponentFlow với nghiệp vụ và transaction

ComponentFlow không phải workflow engine hoặc transaction manager. Nó không bảo đảm các bước nhập liệu và bước nghiệp vụ nằm trong cùng một transaction.

Một thiết kế nên giữ các ranh giới:

| Thành phần | Trách nhiệm |
|---|---|
| **ShellMethod** | Điều phối flow, đọc kết quả, trình bày bản xem trước và quyết định có gọi service hay không |
| **ComponentFlow** | Thu thập input, lựa chọn, xác nhận và lưu kết quả theo ID |
| **Request object** | Mang dữ liệu đã thu thập sang tầng nghiệp vụ |
| **Validator/Policy** | Kiểm tra dữ liệu và điều kiện có thể kiểm tra trước |
| **Application service** | Kiểm tra quyền và trạng thái cuối cùng, quản lý transaction, thực thi nghiệp vụ |

Không mở transaction database trong khi người dùng đang đọc prompt hoặc suy nghĩ. Thời gian tương tác có thể kéo dài; giữ transaction mở trong lúc đó sẽ giữ connection và lock không cần thiết.

Nếu thao tác có thể được gửi lặp lại, service cần idempotency key hoặc cơ chế chống thực thi trùng. Việc người dùng nhấn Enter hai lần hoặc chạy lại command không được tạo ra hai tác động ngoài ý muốn.

## 14. ComponentFlow chỉ dành cho luồng tương tác

ComponentFlow yêu cầu người dùng trả lời các prompt. Nó phù hợp với REPL hoặc terminal có input tương tác.

| Cách chạy | Cách xử lý |
|---|---|
| Người vận hành mở REPL | Dùng ComponentFlow để thu thập và xác nhận |
| CI hoặc script không có TTY | Truyền dữ liệu qua option/argument hoặc file cấu hình đã kiểm tra |
| Job chạy nền | Gọi application service trực tiếp bằng request đã được tạo từ nguồn dữ liệu tự động |
| Test tự động | Dùng terminal test client và input giả lập |

Không gọi flow trong command chạy non-interactive rồi giả định luôn có người nhập. Tác vụ tự động cần một hợp đồng đầu vào rõ ràng và phải có quy tắc xử lý khi thiếu dữ liệu.

## 15. Kiểm thử từng giai đoạn

Kiểm thử nên xác minh cả luồng hiển thị và thời điểm thực thi nghiệp vụ.

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Thu thập đủ dữ liệu | Context có đúng giá trị theo từng ID |
| Nhập chuỗi rỗng | Validation từ chối request và service không được gọi |
| Chọn môi trường hợp lệ | Request nhận đúng item value, không lấy nhãn hiển thị |
| Policy từ chối | Command dừng trước bước xác nhận hoặc thực thi |
| Người dùng chọn No | Service không được gọi |
| Người dùng chọn Yes | Service được gọi đúng một lần với request đã kiểm tra |
| Nhánh mặc định | Bước nhập tùy chỉnh bị bỏ qua |
| Nhánh tùy chỉnh | Bước nhập tùy chỉnh chạy rồi chuyển đến bước tiếp theo |
| storeResult(false) | Command không giả định giá trị có trong context |
| Input bị hủy hoặc thiếu | Command kết thúc an toàn và không có side effect |
| Chạy trong CI không có TTY | Command không bị treo vì prompt |

Spring Shell cung cấp **@ShellTest** và **ShellTestClient** để mô phỏng phiên shell, gửi input và kiểm tra màn hình. Nên mock application service rồi xác minh:

- Khi từ chối xác nhận, số lần gọi service bằng 0.
- Khi chấp nhận, service được gọi đúng một lần.
- Request truyền vào service có đúng dữ liệu đã thu thập.
- Lỗi validation dừng luồng trước khi thực thi.

Ngoài kiểm thử ComponentFlow, hãy kiểm thử validator và service độc lập. Unit test cho service cần xác minh quyền, transaction và quy tắc nghiệp vụ mà giao diện không thể bảo đảm.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không lấy được kết quả từ context | Dùng sai ID hoặc component không lưu kết quả | Kiểm tra ID và storeResult |
| Giá trị selector không đúng mong đợi | Nhầm name với item trong SelectItem | Dùng item làm mã nghiệp vụ |
| Component chạy sai thứ tự | Hiểu nhầm thứ tự builder hoặc dùng order/next không đúng | Kiểm tra thứ tự và ID đích |
| Bước tùy chọn vẫn xuất hiện | Chưa cấu hình next để bỏ qua | Trả về ID component cần đi tới |
| Flow dừng quá sớm | next trả null hoặc ID không tồn tại | Kiểm tra tất cả ID trong nhánh |
| Service chạy dù người dùng hủy | Gọi service trong handler hoặc trước confirmation | Chỉ gọi service sau khi kiểm tra Boolean.TRUE |
| Nhấn Enter vô tình xác nhận | Đặt mặc định confirmation là true | Đặt defaultValue(false) cho thao tác quan trọng |
| Dữ liệu không hợp lệ vẫn đi tiếp | Giả định StringInput tự bắt buộc hoặc kiểm tra ở service quá muộn | Kiểm tra request trước confirmation |
| Transaction bị giữ trong lúc prompt | Mở transaction trước khi flow chạy | Chỉ mở transaction trong application service |
| Flow bị treo trong script | Dùng prompt tương tác trong môi trường không có TTY | Dùng option/argument hoặc nguồn dữ liệu tự động |
| Builder giữ cấu hình cũ | Tái sử dụng builder đã sửa mà không reset | Dùng clone().reset() khi tạo flow mới |

## 17. Checklist thiết kế ComponentFlow

- [ ] Mỗi component có ID duy nhất, dễ hiểu và ổn định.
- [ ] Tên hiển thị được tách khỏi giá trị dùng trong nghiệp vụ.
- [ ] Builder được tạo bằng clone().reset().
- [ ] Thứ tự component và nhánh next được kiểm tra.
- [ ] Kết quả được lấy từ ComponentContext bằng đúng kiểu.
- [ ] Xử lý trường hợp ID chưa có kết quả hoặc giá trị null.
- [ ] Dữ liệu được chuyển thành request object trước khi gọi service.
- [ ] Validation hoàn tất trước khi hỏi xác nhận.
- [ ] Người dùng nhìn thấy bản xem trước đủ để hiểu tác động.
- [ ] Confirmation mặc định là false với thao tác quan trọng.
- [ ] Service chỉ được gọi sau khi nhận Boolean.TRUE.
- [ ] Service vẫn kiểm tra quyền và trạng thái tại thời điểm thực thi.
- [ ] Không giữ transaction mở trong lúc chờ input.
- [ ] Không gọi nghiệp vụ ghi dữ liệu trong preHandler, postHandler hoặc next.
- [ ] Có kiểm thử nhánh Yes/No, validation, hủy và input thiếu.
- [ ] Có đường chạy riêng cho CI, script và môi trường không có TTY.

ComponentFlow giúp command tổ chức trải nghiệm nhập liệu thành một quy trình rõ ràng. Khi command chỉ thu thập và xác nhận, còn application service chịu trách nhiệm thực thi, người dùng có thể xem lại và hủy thao tác mà không tạo side effect ngoài ý muốn; logic nghiệp vụ cũng dễ tái sử dụng và kiểm thử độc lập.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Flow](https://docs.spring.io/spring-shell/reference/3.3/components/flow/index.html) — xây dựng flow từ nhiều component, thứ tự thực thi và điều hướng bằng next.
- [Spring Shell 3.3.4 — Flow Components](https://docs.spring.io/spring-shell/reference/3.3/components/ui/index.html) — mô hình component nhập liệu và cách component hoạt động.
- [Spring Shell 3.3.0 API — ComponentFlow](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.html) — build và run flow.
- [Spring Shell 3.3.0 API — ComponentFlow.Builder](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.Builder.html) — clone, reset, các with...Input và build.
- [Spring Shell 3.3.0 API — StringInputSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/StringInputSpec.html) — default value, mask, handler, next và storeResult.
- [Spring Shell 3.3.0 API — ConfirmationInputSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ConfirmationInputSpec.html) — defaultValue, resultMode, next và storeResult.
- [Spring Shell 3.3.0 API — SingleItemSelectorSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/SingleItemSelectorSpec.html) — selectItems, defaultSelect và nhánh tiếp theo.
- [Spring Shell 3.3.0 API — MultiItemSelectorSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/MultiItemSelectorSpec.html) — chọn nhiều mục và lưu kết quả.
- [Spring Shell 3.3.0 API — ComponentContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/context/ComponentContext.html) — truy cập kết quả theo ID và kiểu.
- [Spring Shell 3.3.0 API — ResultMode](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ResultMode.html) — hành vi ACCEPT và VERIFY.
- [Spring Shell 3.3.0 API — ComponentFlowAutoConfiguration](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/boot/ComponentFlowAutoConfiguration.html) — auto-configure ComponentFlow.Builder.
- [Spring Shell 3.3.0 API — ShellTestClient](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html) — mô phỏng phiên shell và input người dùng trong kiểm thử.
- [Spring Shell 3.3.0 API — AbstractShellComponent](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/AbstractShellComponent.html) — truy cập terminal, resource loader và template executor.
