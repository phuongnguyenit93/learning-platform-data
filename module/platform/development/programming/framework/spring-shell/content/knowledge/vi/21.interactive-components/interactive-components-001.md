# Phạm vi phiên bản của Flow Components trong nhánh 3.x

Flow Components không phải tính năng mới được đưa vào riêng Spring Shell 3.x. Tài liệu chính thức ghi nhận mô hình component này từ Spring Shell 2.1.x; vì vậy, các bản 3.x kế thừa khả năng tạo tương tác ngay trong command. Trong nhánh 3.x, ứng dụng có thể hỏi văn bản, yêu cầu đường dẫn, xác nhận thao tác hoặc cho người dùng chọn một hay nhiều mục. **ComponentFlow** ghép nhiều bước thành một luồng tương tác có thứ tự và có thể rẽ nhánh.

Điểm cần nắm khi đọc tài liệu 3.x là phạm vi của từng API. Các component độc lập có thể được chạy riêng trong command; **ComponentFlow.Builder** chỉ cung cấp một tập loại đầu vào cụ thể. Không nên suy ra rằng mọi component độc lập đều có phương thức tương ứng trong flow builder.

## 1. Flow Components xuất hiện từ phiên bản nào?

Spring Shell giới thiệu mô hình component tương tác từ dòng 2.1.x. Tài liệu Spring Shell 3.1.5 có riêng hai phần Flow và Flow Components; tài liệu 3.4.3 tiếp tục duy trì hai phần này. API Javadoc của các dòng 3.0, 3.2, 3.3 và 3.4 cũng liệt kê ComponentFlow, các builder và các component liên quan.

| Phiên bản | Tình trạng Flow Components | Điều cần lưu ý |
| --- | --- | --- |
| 2.1.x | Mô hình component được giới thiệu | Là mốc xuất hiện được tài liệu Spring Shell nêu rõ |
| 3.0.x | Có Flow Components và ComponentFlow | Dùng package org.springframework.shell.component và org.springframework.shell.component.flow |
| 3.1.x | Tiếp tục hỗ trợ | Tài liệu 3.1.5 có ví dụ flow và component; dòng 3.1 cũng bổ sung mô hình annotation command mới |
| 3.2.x | Tiếp tục hỗ trợ | Javadoc vẫn có ComponentFlow.Builder, ComponentFlowResult và các spec |
| 3.3.x | Tiếp tục hỗ trợ | API component vẫn thuộc package 3.x; thay đổi runner mặc định không làm mất Flow Components |
| 3.4.x | Tiếp tục hỗ trợ | Tài liệu 3.4.3 và Javadoc mô tả đầy đủ flow builder, selector và các component |

Vì vậy, khi một dự án dùng Spring Shell 3.x, có thể dựa vào mô hình Flow Components. Tuy nhiên, hãy kiểm tra API của đúng minor version đang dùng trước khi sao chép ví dụ hoặc nâng cấp dependency. Không dùng tài liệu 4.x để suy ra rằng mọi phương thức của builder đều tồn tại trong 3.x.

## 2. Phân biệt component độc lập và ComponentFlow

Flow Components là các thành phần giao diện tương tác có thể chạy bên trong một command. ComponentFlow là lớp điều phối nhiều thành phần đó thành một wizard:

| Thành phần | Vai trò | Cách sử dụng |
| --- | --- | --- |
| **StringInput** | Nhận một chuỗi, có thể che ký tự nhập | Tạo và chạy trực tiếp trong command |
| **PathInput** | Yêu cầu người dùng nhập một đường dẫn | Tạo và chạy trực tiếp trong command |
| **PathSearch** | Tìm đường dẫn từ thư mục gốc và cho chọn kết quả | Tạo và chạy trực tiếp trong command |
| **ConfirmationInput** | Hỏi xác nhận có/không | Tạo và chạy trực tiếp trong command |
| **SingleItemSelector** | Chọn một mục trong danh sách | Tạo và chạy trực tiếp trong command |
| **MultiItemSelector** | Chọn nhiều mục trong danh sách | Tạo và chạy trực tiếp trong command |
| **ComponentFlow** | Kết nối nhiều bước đầu vào thành một luồng | Dùng ComponentFlow.Builder để khai báo các bước |

Các component thường chạy một vòng lặp nhận phím và dữ liệu người dùng, tạo context cho lần chạy, hiển thị trạng thái trong lúc nhập, kết thúc rồi hiển thị kết quả cuối. Mỗi loại có context riêng, đồng thời kế thừa các trường chung như tên component, nội dung nhập, thông báo và mức thông báo.

Một component độc lập phù hợp khi command chỉ cần một câu hỏi. Khi cần hỏi tên workspace, chọn môi trường rồi xác nhận triển khai, ComponentFlow giúp gom các bước vào cùng một luồng và giữ kết quả trong context chung.

## 3. Các loại đầu vào mà Flow Builder 3.x hỗ trợ

Trong Javadoc Spring Shell 3.4.3, ComponentFlow.BaseBuilder cung cấp các phương thức tạo bước sau:

| Phương thức | Spec trả về | Mục đích |
| --- | --- | --- |
| **withStringInput(id)** | StringInputSpec | Nhập chuỗi |
| **withPathInput(id)** | PathInputSpec | Nhập đường dẫn |
| **withConfirmationInput(id)** | ConfirmationInputSpec | Xác nhận có/không |
| **withSingleItemSelector(id)** | SingleItemSelectorSpec | Chọn một mục |
| **withMultiItemSelector(id)** | MultiItemSelectorSpec | Chọn nhiều mục |

Mỗi bước có một ID duy nhất trong flow. Có thể cấu hình tên hiển thị, giá trị mặc định, danh sách mục, xử lý trước/sau khi chạy, cách lưu kết quả, template hoặc hàm điều hướng tiếp theo. Gọi **and()** để quay lại builder cha và khai báo bước tiếp.

**Giới hạn quan trọng của nhánh 3.x:** ComponentFlow.Builder trong API 3.4.3 không có **withNumberInput**. API Flow Components 4.x đã bổ sung NumberInput và withNumberInput, nhưng không được dùng các phương thức đó trong mã 3.x. Nếu cần nhận số trong 3.x, có thể dùng StringInput rồi parse và kiểm tra giá trị, hoặc dùng option kiểu số của command nếu không cần giao diện hỏi từng bước.

PathSearch cũng là component độc lập trong package component 3.x, nhưng không có phương thức **withPathSearch** trong danh sách phương thức của ComponentFlow.Builder 3.4.3. Nếu cần tìm tệp trong một flow, hãy dùng PathInput trong flow rồi tự kiểm tra đường dẫn, hoặc gọi component PathSearch độc lập ở bước phù hợp.

## 4. Package API trong nhánh 3.x

Các package chính được dùng trong Spring Shell 3.x:

| Nhóm | Package |
| --- | --- |
| Component độc lập | org.springframework.shell.component |
| Context dùng chung | org.springframework.shell.component.context |
| Flow và các spec của builder | org.springframework.shell.component.flow |
| Lớp hỗ trợ và context cơ sở | org.springframework.shell.component.support |

Ví dụ import trong 3.x:

```java
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.component.context.ComponentContext;
```

Package là một dấu hiệu quan trọng khi nâng cấp. Trong Spring Shell 4.x, component API được chuyển vào các package có tiền tố org.springframework.shell.jline.tui.component. Không trộn import 4.x vào dự án 3.x, dù tên interface hoặc class có thể giống nhau.

## 5. Cách Spring cung cấp ComponentFlow.Builder

Khi dùng cấu hình Spring Shell với Spring Boot, ComponentFlowAutoConfiguration đăng ký builder để inject vào component hoặc command bean. Cách dùng thường gặp trong tài liệu 3.x là:

```java
@Autowired
private ComponentFlow.Builder componentFlowBuilder;
```

Builder được dùng để tạo cấu hình flow. Nên gọi clone().reset() trước khi thêm các bước của một flow mới:

```java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("workspace")
            .name("Workspace")
            .defaultValue("demo")
            .and()
        .withConfirmationInput("deploy")
            .name("Deploy now?")
            .defaultValue(false)
            .and()
        .build();
```

clone() tạo builder riêng cho flow đang xây dựng; reset() xóa cấu hình bước trước đó trên builder vừa clone. Cách này tránh để cấu hình của một flow ảnh hưởng flow khác khi builder được inject từ Spring.

build() tạo ComponentFlow; run() bắt đầu tương tác và trả về ComponentFlowResult. Có thể đọc context kết quả:

```java
ComponentFlow.ComponentFlowResult result = flow.run();
ComponentContext<?> context = result.getContext();

String workspace = context.get("workspace", String.class);
Boolean deploy = context.get("deploy", Boolean.class);
```

Các spec của flow mặc định lưu kết quả theo ID của bước vào ComponentContext; có thể điều chỉnh bằng storeResult(false) nếu không muốn tự động lưu. Hãy dùng ID ổn định và duy nhất để đọc kết quả sau khi flow hoàn tất.

## 6. Ví dụ command dùng Flow Components trong Spring Shell 3.x

Ví dụ dưới đây dùng mô hình annotation legacy có mặt trong Spring Shell 3.x. Command hỏi tên workspace và xác nhận có triển khai hay không:

```java
import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class WorkspaceCommands {

    private final ComponentFlow.Builder componentFlowBuilder;

    public WorkspaceCommands(ComponentFlow.Builder componentFlowBuilder) {
        this.componentFlowBuilder = componentFlowBuilder;
    }

    @ShellMethod(key = "workspace setup", value = "Thiết lập workspace qua các bước hỏi đáp.")
    public String setup() {
        ComponentFlow flow = componentFlowBuilder.clone()
                .reset()
                .withStringInput("workspace")
                    .name("Workspace name")
                    .defaultValue("demo")
                    .and()
                .withConfirmationInput("deploy")
                    .name("Deploy after setup?")
                    .defaultValue(false)
                    .and()
                .build();

        ComponentFlow.ComponentFlowResult result = flow.run();
        ComponentContext<?> context = result.getContext();

        String workspace = context.get("workspace", String.class);
        Boolean deploy = context.get("deploy", Boolean.class);

        if (Boolean.TRUE.equals(deploy)) {
            return "Đã thiết lập workspace " + workspace
                    + " và yêu cầu triển khai.";
        }
        return "Đã thiết lập workspace " + workspace
                + "; chưa yêu cầu triển khai.";
    }
}
```

Đây là ví dụ cho Spring Shell 3.x: dùng package org.springframework.shell.component.flow và các bước withStringInput/withConfirmationInput. Từ Spring Shell 3.1.x, ứng dụng cũng có mô hình annotation command mới; việc đổi cách khai báo command không làm thay đổi nguyên tắc tạo ComponentFlow trong method.

## 7. Thứ tự thực thi và điều hướng có điều kiện

Nếu không cấu hình điều hướng, flow chạy các bước theo đúng thứ tự khai báo trong builder. Ví dụ:

```java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("project")
            .name("Project name")
            .and()
        .withPathInput("source")
            .name("Source directory")
            .and()
        .withConfirmationInput("publish")
            .name("Publish now?")
            .and()
        .build();
```

Muốn rẽ nhánh, cấu hình next(...) cho bước hiện tại. Hàm nhận context của component vừa chạy và trả về ID của bước tiếp theo. Nếu trả về null hoặc ID không tồn tại, flow dừng tại đó.

```java
import java.util.Map;

ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withSingleItemSelector("action")
            .name("Choose an action")
            .selectItems(Map.of(
                    "Create workspace", "workspaceName",
                    "Inspect workspace", "workspacePath"
            ))
            .next(context -> context.getResultItem()
                    .map(item -> item.getItem())
                    .orElse(null))
            .and()
        .withStringInput("workspaceName")
            .name("New workspace name")
            .next(context -> null)
            .and()
        .withPathInput("workspacePath")
            .name("Workspace path")
            .next(context -> null)
            .and()
        .build();
```

Trong ví dụ, giá trị được chọn ở bước action chính là ID bước tiếp theo. Nếu người dùng chọn create, flow chuyển đến workspaceName; nếu chọn inspect, flow chuyển đến workspacePath. Hai bước cuối trả null để kết thúc sau khi thu thập dữ liệu.

Khi viết hàm next, phải bảo đảm ID trả về trùng với ID đã khai báo trong builder. Nên dùng hằng số hoặc enum để tránh lỗi chính tả trong các flow dài.

## 8. Tùy chỉnh renderer và template

Các component 3.x có context riêng và dùng template để hiển thị trạng thái trong lúc người dùng nhập cũng như kết quả cuối. Template mặc định của built-in components nằm trong classpath dưới org/springframework/shell/component.

Có hai hướng tùy chỉnh:

- **Template:** thay đổi cách trình bày mà không phải viết toàn bộ logic render. Phù hợp khi chỉ cần đổi nhãn, bố cục hoặc cách hiển thị kết quả.
- **Renderer bằng Java:** cung cấp một hàm nhận component context và trả về danh sách AttributedString. Cách này phù hợp khi cần định dạng hoặc logic hiển thị phức tạp.

Các spec trong ComponentFlow có thể cung cấp template(...) hoặc renderer(...) tùy loại component. Với component độc lập, có thể thiết lập ResourceLoader và TemplateExecutor trước khi gọi run().

Không nên tùy chỉnh giao diện trước khi xác định đúng loại component và context của nó. StringInputContext có trường nhập và giá trị mặc định; selector context có danh sách mục, vị trí con trỏ và trạng thái lựa chọn. Dùng nhầm context sẽ khiến template không hiển thị dữ liệu mong muốn.

## 9. Điều kiện môi trường và giới hạn sử dụng

Flow Components là giao diện tương tác cần người dùng nhập hoặc chọn dữ liệu. Vì vậy, chúng phù hợp với command chạy trong terminal có khả năng đọc input. Với quy trình CI, script hoặc chế độ không tương tác, không nên phụ thuộc vào câu hỏi yêu cầu người dùng bấm phím.

Đối với tác vụ tự động:

- Ưu tiên nhận dữ liệu qua option hoặc argument của command.
- Dùng giá trị mặc định có ý nghĩa khi nghiệp vụ cho phép.
- Yêu cầu xác nhận tường minh bằng option như --confirm nếu thao tác có tác động lớn.
- Tách logic nghiệp vụ khỏi phần hỏi đáp để cùng một service có thể được gọi từ command tương tác hoặc command tự động.

Flow Components không thay thế validation nghiệp vụ. Dữ liệu người dùng chọn vẫn phải được kiểm tra trước khi ghi hoặc thực hiện tác vụ; ví dụ đường dẫn phải tồn tại và người dùng phải có quyền truy cập.

## 10. Những điều không nên suy diễn khi làm việc với 3.x

| Nhận định sai | Thực tế trong nhánh 3.x |
| --- | --- |
| Flow Components được giới thiệu ở 3.x | Tài liệu ghi nhận mô hình component từ 2.1.x |
| Mọi component độc lập đều có builder method tương ứng | ComponentFlow.Builder chỉ công bố một tập method cụ thể |
| Có thể gọi withNumberInput trong 3.4 | API 3.4.3 không có method này; NumberInput/withNumberInput xuất hiện trong API 4.x |
| Có withPathSearch trong flow builder | PathSearch là component độc lập; 3.4 builder không liệt kê withPathSearch |
| ComponentFlow tự thực hiện nghiệp vụ | Flow chỉ thu thập và điều phối tương tác; command/service vẫn xử lý nghiệp vụ |
| Flow tự động phù hợp với CI hoặc script | Flow cần input tương tác; automation nên dùng option/argument tường minh |
| Builder được inject có thể tùy ý tái sử dụng mà không reset | Dùng clone().reset() để tạo cấu hình riêng cho từng flow |

## 11. Lưu ý khi chuyển từ Spring Shell 3.x lên 4.x

Spring Shell 4.x thay đổi package của component API sang org.springframework.shell.jline.tui.component và org.springframework.shell.jline.tui.component.flow. Bản 4.x cũng có NumberInput và withNumberInput, nên code 3.x cần được rà soát trước khi sao chép ví dụ mới.

Khi nâng cấp:

1. Cập nhật dependency theo bộ phiên bản Spring Shell 4.x và Spring Boot tương ứng.
2. Cập nhật import component, context và flow sang package 4.x.
3. Kiểm tra các bước nhập số; nếu cần, chuyển sang NumberInput/withNumberInput của 4.x.
4. Kiểm tra lại template và renderer vì các context/package đã chuyển.
5. Chạy lại các command trong terminal thật và các bài kiểm thử shell.

Không đổi import một cách máy móc rồi cho rằng flow có hành vi giống hệt. Hãy so sánh builder methods, kiểu kết quả và template context trong Javadoc đúng phiên bản đích.

## 12. Kiểm thử Flow Components

Nên kiểm thử cả việc thu thập dữ liệu lẫn luồng điều hướng:

- Nhập chuỗi và chấp nhận giá trị mặc định.
- Xác nhận cả hai nhánh true và false.
- Chọn một mục và nhiều mục.
- Kiểm tra flow chạy đúng thứ tự khi không có next.
- Kiểm tra next chuyển đến đúng ID và dừng khi trả null.
- Kiểm tra kết quả có trong ComponentFlowResult.getContext() theo ID của bước.
- Kiểm tra hành vi khi người dùng hủy hoặc đóng terminal.
- Kiểm tra command không gọi service nếu dữ liệu đầu vào không hợp lệ.
- Xác nhận command automation không bị treo chờ input tương tác.

Spring Shell có @ShellTest và ShellTestClient để kiểm thử command qua shell infrastructure. Với component tương tác, cần chuẩn bị input terminal phù hợp hoặc tách phần xử lý nghiệp vụ thành service để unit test độc lập. Một bài test chỉ kiểm tra command trả về chuỗi không đủ chứng minh điều hướng của flow đúng.

## 13. Checklist xác định phạm vi Flow Components 3.x

- Nhớ rằng mô hình component đã có từ Spring Shell 2.1.x.
- Xác nhận minor version 3.x đang dùng trước khi tham chiếu Javadoc.
- Dùng package org.springframework.shell.component và org.springframework.shell.component.flow.
- Phân biệt component độc lập với ComponentFlow.Builder.
- Với builder 3.x, chỉ dùng string, path, confirmation, single selector và multi selector.
- Không gọi withNumberInput hoặc withPathSearch trong flow builder 3.x.
- Tạo builder riêng bằng clone().reset().
- Đặt ID duy nhất cho từng bước và trả đúng ID trong next.
- Đọc kết quả qua ComponentFlowResult.getContext().
- Dùng template hoặc renderer phù hợp với context của component.
- Không phụ thuộc Flow Components trong môi trường không có input tương tác.
- Kiểm thử thứ tự, rẽ nhánh, kết quả và hành vi khi hủy.

## Tài liệu tham khảo

- [Spring Shell 3.1.5 — Components, Flow và Flow Components](https://docs.spring.io/spring-shell/docs/3.1.5/docs/index.html)
- [Spring Shell 3.4.3 — Flow Components](https://docs.spring.io/spring-shell/reference/3.4/components/ui/)
- [Spring Shell 3.4.3 — Flow](https://docs.spring.io/spring-shell/reference/3.4/components/flow/index.html)
- [Spring Shell 3.4.3 — ComponentFlow.BaseBuilder API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.BaseBuilder.html)
- [Spring Shell 3.4.3 — ComponentFlow.ComponentFlowResult API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html)
- [Spring Shell 3.4.3 — ComponentContext API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/component/context/ComponentContext.html)
- [Spring Shell 4.0.3 — ComponentFlow.BaseBuilder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/component/flow/ComponentFlow.BaseBuilder.html)
