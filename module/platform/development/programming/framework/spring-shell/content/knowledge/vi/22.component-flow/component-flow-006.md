# Điều kiện dừng luồng và bước đích không hợp lệ

ComponentFlow trong Spring Shell 3.x nối nhiều component nhập liệu thành một quy trình tương tác. Mặc định, các component chạy theo thứ tự khai báo trong builder. Khi cần rẽ nhánh, mỗi component có thể khai báo hàm `next` để chọn ID của component tiếp theo.

Hai kết quả của `next` có ý nghĩa đặc biệt: trả về `null` là dừng flow có chủ đích; trả về ID không tồn tại cũng làm flow dừng ngay tại component hiện tại. Kết quả thứ hai dễ bị nhầm với một nhánh kết thúc bình thường, trong khi nguyên nhân có thể chỉ là lỗi đánh máy hoặc đổi tên component nhưng quên cập nhật target.

Bài học giải thích cách Spring Shell 3.x điều khiển thứ tự component, cách dừng flow, cách chọn target hợp lệ, cách đọc kết quả sau khi flow kết thúc và cách kiểm thử các nhánh. Trọng tâm là tránh việc một ID sai khiến quy trình dừng sớm mà không có thông báo rõ ràng.

## 1. ComponentFlow tổ chức các bước tương tác

Một flow thường gồm nhiều component như:

- `StringInput` để nhập chuỗi.
- `PathInput` để nhập đường dẫn.
- `ConfirmationInput` để xác nhận.
- `SingleItemSelector` để chọn một mục.
- `MultiItemSelector` để chọn nhiều mục.

Trong mô hình builder, mỗi component được thêm bằng phương thức như `withStringInput("projectName")` hoặc `withSingleItemSelector("action")`. Chuỗi truyền vào phương thức này là ID của component trong flow.

Ví dụ:

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("projectName")
            .name("Project name")
            .and()
        .withConfirmationInput("confirm")
            .name("Continue?")
            .and()
        .build();
~~~

Trong ví dụ, `projectName` và `confirm` là ID dùng để lưu kết quả, tham chiếu component và điều hướng. `name("Project name")` chỉ đặt nhãn hiển thị cho người dùng; nó không đổi ID.

Nếu không khai báo `next`, flow chạy theo thứ tự các component được thêm vào builder: `projectName` trước, rồi `confirm`.

## 2. Thứ tự mặc định và điều hướng bằng next

Spring Shell 3.1.6 mô tả hai quy tắc:

1. Thứ tự thực thi thông thường của component giống thứ tự khai báo trong builder.
2. Có thể chọn nơi tiếp tục bằng cách trả về ID component đích từ hàm `next`.

Ví dụ một flow không rẽ nhánh:

~~~java
ComponentFlow flow = componentFlowBuilder.clone().reset()
        .withStringInput("firstName")
            .name("First name")
            .and()
        .withStringInput("lastName")
            .name("Last name")
            .and()
        .withConfirmationInput("confirm")
            .name("Save?")
            .and()
        .build();

ComponentFlow.ComponentFlowResult result = flow.run();
~~~

Người dùng nhập lần lượt tên, họ và xác nhận. Đây là thứ tự mặc định vì builder không khai báo hàm `next` để thay đổi đường đi.

Khi thêm `next`, flow có thể bỏ qua component kế tiếp theo thứ tự hoặc chuyển đến component khác:

~~~java
.withStringInput("firstName")
    .name("First name")
    .next(ctx -> "confirm")
    .and()
~~~

Sau khi component `firstName` hoàn tất, hàm `next` trả về ID `confirm`. Flow chuyển đến component có ID đó nếu nó tồn tại trong flow đã build.

## 3. Hợp đồng của hàm next

Các interface spec trong Spring Shell 3.x khai báo `next(Function<context, String>)`. Hàm nhận context của component vừa chạy và trả về một chuỗi:

| Kết quả của next | Hành vi |
|---|---|
| ID của component tồn tại trong flow | Chuyển đến component có ID đó |
| `null` | Dừng flow tại component hiện tại |
| ID không tồn tại | Dừng flow tại component hiện tại |

Các spec có phương thức `next` gồm:

| Spec | Kiểu context truyền vào |
|---|---|
| `StringInputSpec` | `StringInput.StringInputContext` |
| `PathInputSpec` | `PathInput.PathInputContext` |
| `ConfirmationInputSpec` | `ConfirmationInput.ConfirmationInputContext` |
| `SingleItemSelectorSpec` | `SingleItemSelector.SingleItemSelectorContext` |
| `MultiItemSelectorSpec` | `MultiItemSelector.MultiItemSelectorContext` |

Do đó, hàm `next` có thể quyết định đường đi dựa trên câu trả lời vừa nhận. Ví dụ, xác nhận `true` có thể chuyển đến bước triển khai, còn `false` trả `null` để dừng flow.

Tài liệu API mô tả cả `null` và ID không tồn tại đều là điều kiện dừng. API không mô tả việc ID sai sẽ tự động ném một exception riêng để báo lỗi điều hướng. Vì vậy, không nên dựa vào exception của framework để phát hiện lỗi đánh máy trong ID.

## 4. Dừng flow có chủ đích bằng null

Dừng flow là một phần bình thường của thiết kế nhánh. Ví dụ, người dùng không muốn tiếp tục thì có thể trả về `null`:

~~~java
ComponentFlow flow = componentFlowBuilder.clone().reset()
        .withStringInput("projectName")
            .name("Project name")
            .next(ctx -> "confirm")
            .and()
        .withConfirmationInput("confirm")
            .name("Create this project?")
            .next(ctx -> Boolean.TRUE.equals(ctx.getResultValue())
                    ? "createProject"
                    : null)
            .and()
        .withStringInput("createProject")
            .name("Project details")
            .next(ctx -> null)
            .and()
        .build();
~~~

Nếu người dùng xác nhận, flow chuyển đến `createProject`. Nếu người dùng từ chối, `next` trả `null` và flow kết thúc sau bước xác nhận.

Trong trường hợp này, `null` là một quyết định nghiệp vụ rõ ràng. Nó không phải lỗi cấu hình. Nên đặt điều kiện dừng ở nhánh mà người đọc có thể nhận ra, chẳng hạn từ kết quả confirmation hoặc lựa chọn “Cancel”.

Đừng trả `null` chỉ vì không biết ID nào phải dùng. Nếu chưa xác định được nhánh tiếp theo, hãy kiểm tra dữ liệu và báo lỗi ở tầng ứng dụng thay vì biến lỗi logic thành kết thúc im lặng.

## 5. Bước đích không tồn tại cũng làm flow dừng

Một lỗi dễ gặp là trả về ID không trùng với ID đã khai báo:

~~~java
.withSingleItemSelector("action")
    .name("Choose action")
    .selectItems(Map.of(
            "Create project", "createProject",
            "Open project", "openProject"))
    .next(ctx -> ctx.getResultItem()
            .map(item -> item.getItem())
            .orElse(null))
    .and()
.withStringInput("create-project")
    .name("Project details")
    .and()
.withStringInput("openProject")
    .name("Project ID")
    .and()
~~~

Lựa chọn “Create project” trả về `createProject`, nhưng component được khai báo là `create-project`. Hai chuỗi không giống nhau.

Khi người dùng chọn “Create project”, target `createProject` không tồn tại. Theo hợp đồng của `next`, flow dừng tại selector. Component nhập chi tiết dự án không chạy.

Đây là lỗi điều hướng, không phải lỗi nhập liệu của người dùng. Người dùng chọn đúng mục hiển thị; cấu hình của flow mới là phần không nhất quán.

### 5.1. ID không hợp lệ khác với component không được chạy do nhánh

Cần phân biệt:

- **Nhánh kết thúc hợp lệ:** hàm `next` trả `null` theo chủ đích.
- **Nhánh bỏ qua hợp lệ:** hàm `next` trả ID của một component khác đã khai báo.
- **Target không hợp lệ:** hàm `next` trả ID không được khai báo; flow cũng dừng, nhưng thường là lỗi cấu hình.
- **Component không nằm trên nhánh được chọn:** component có tồn tại nhưng không được thực thi vì đường đi không dẫn đến nó.

Một component không chạy chưa đủ để kết luận ID bị sai. Hãy kiểm tra giá trị trả về của `next` và danh sách ID trong builder.

## 6. ID component và nhãn hiển thị là hai giá trị khác nhau

Một nguyên nhân gây lỗi target là nhầm ID với tên hiển thị:

~~~java
.withStringInput("environmentId")
    .name("Environment")
    .and()
~~~

Trong ví dụ:

- ID là `environmentId`.
- Nhãn hiển thị là `Environment`.

Nếu `next` trả về `Environment`, flow sẽ tìm component có ID đó. Nó không tìm theo nhãn hiển thị. Nếu không có ID `Environment`, flow dừng.

Nên dùng quy ước đặt ID thống nhất:

- Dùng camelCase hoặc kebab-case nhất quán.
- ID ngắn, mô tả vai trò của component.
- Không thay đổi ID tùy tiện sau khi đã được dùng trong các hàm `next`.
- Tập trung ID vào hằng số để giảm lỗi gõ sai.

Ví dụ:

~~~java
private static final String STEP_ACTION = "action";
private static final String STEP_CREATE_PROJECT = "createProject";
private static final String STEP_OPEN_PROJECT = "openProject";
private static final String STEP_FINISH = "finish";
~~~

Dùng cùng hằng số khi khai báo component và khi trả target:

~~~java
.withSingleItemSelector(STEP_ACTION)
    .name("Choose action")
    .next(ctx -> STEP_CREATE_PROJECT)
    .and()
.withStringInput(STEP_CREATE_PROJECT)
    .name("Project details")
    .and()
~~~

Cách này giúp IDE hỗ trợ rename và giảm nguy cơ một chuỗi target không còn khớp với component.

## 7. Ví dụ rẽ nhánh hoàn chỉnh bằng selector

Ví dụ sau tạo flow cho phép người dùng chọn tạo mới hoặc mở một dự án hiện có.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.stereotype.Component;

@Component
public class ProjectWizard {

    private static final String ACTION = "action";
    private static final String CREATE_PROJECT = "createProject";
    private static final String OPEN_PROJECT = "openProject";

    @Autowired
    private ComponentFlow.Builder componentFlowBuilder;

    public ComponentFlow.ComponentFlowResult run() {
        Map<String, String> actions = new LinkedHashMap<>();
        actions.put("Create a project", CREATE_PROJECT);
        actions.put("Open an existing project", OPEN_PROJECT);

        ComponentFlow flow = componentFlowBuilder.clone().reset()
                .withSingleItemSelector(ACTION)
                    .name("Choose an action")
                    .selectItems(actions)
                    .next(ctx -> ctx.getResultItem()
                            .map(item -> item.getItem())
                            .orElse(null))
                    .and()
                .withStringInput(CREATE_PROJECT)
                    .name("New project name")
                    .next(ctx -> null)
                    .and()
                .withStringInput(OPEN_PROJECT)
                    .name("Project ID")
                    .next(ctx -> null)
                    .and()
                .build();

        return flow.run();
    }
}
~~~

Map truyền vào `selectItems` dùng nhãn làm key và giá trị được chọn làm item. Trong ví dụ, item chính là ID của component đích.

Khi người dùng chọn “Create a project”, `getResultItem()` trả item `createProject`. Khi chọn “Open an existing project”, nó trả `openProject`.

Mỗi nhánh kết thúc bằng `null` sau khi thu thập dữ liệu cần thiết. Nếu một item trong map chứa ID viết sai, flow sẽ dừng ngay sau selector thay vì hiển thị component tương ứng.

## 8. Dùng context để chọn target an toàn

Hàm `next` nhận context riêng của component. Với selector đơn, `getResultItem()` trả về `Optional`. Nên xử lý trường hợp không có item được chọn thay vì gọi `get()` trực tiếp:

~~~java
.next(ctx -> ctx.getResultItem()
        .map(item -> item.getItem())
        .orElse(null))
~~~

Với string input, có thể dùng `getResultValue()` để đọc kết quả:

~~~java
.withStringInput("environment")
    .name("Environment")
    .next(ctx -> {
        String value = ctx.getResultValue();

        if ("production".equalsIgnoreCase(value)) {
            return "productionApproval";
        }

        if ("staging".equalsIgnoreCase(value)) {
            return "stagingReview";
        }

        return null;
    })
    .and()
~~~

Nếu người dùng nhập giá trị ngoài các trường hợp đã định nghĩa, ví dụ `dev`, đoạn code trả `null` và flow dừng. Điều này có thể là nhánh kết thúc mong muốn, nhưng nếu `dev` cần có bước riêng thì trả `null` sẽ làm mất bước đó.

Khi input không hợp lệ cần được yêu cầu nhập lại, hãy dùng validation hoặc thông báo lỗi của component phù hợp. Không dùng `next` như một cơ chế thay thế validation.

## 9. Kiểm tra target trước khi trả về

Vì ID không tồn tại cũng làm flow dừng, ứng dụng nên kiểm tra target động trước khi trả nó. Có thể tạo một tập ID hợp lệ:

~~~java
import java.util.Set;

private static final Set<String> VALID_TARGETS = Set.of(
        "createProject",
        "openProject",
        "finish");

private static String checkedTarget(String target) {
    if (target == null) {
        return null; // Dừng flow có chủ đích.
    }

    if (!VALID_TARGETS.contains(target)) {
        throw new IllegalStateException(
                "Unknown ComponentFlow target: " + target);
    }

    return target;
}
~~~

Sau đó sử dụng:

~~~java
.next(ctx -> checkedTarget(
        ctx.getResultItem()
                .map(item -> item.getItem())
                .orElse(null)))
~~~

Hàm kiểm tra giữ nguyên ý nghĩa của `null` nhưng phát hiện ID không được khai báo. Exception ở đây do ứng dụng chủ động ném ra; đó không phải exception được Spring Shell tự ném khi nhận target không tồn tại.

Danh sách `VALID_TARGETS` phải được cập nhật cùng với builder. Nếu ID được tạo động, hãy xây dựng tập hợp từ cùng nguồn dữ liệu dùng để khai báo component để tránh hai danh sách bị lệch nhau.

## 10. Dùng hằng số để tránh lệch ID

Một cách khác là khai báo các ID ở một nơi duy nhất:

~~~java
private static final String ACTION = "action";
private static final String CREATE_PROJECT = "createProject";
private static final String OPEN_PROJECT = "openProject";
private static final String REVIEW_PROJECT = "reviewProject";
~~~

Dùng hằng số cả ở builder và trong hàm điều hướng:

~~~java
.withSingleItemSelector(ACTION)
    .selectItems(Map.of(
            "Create", CREATE_PROJECT,
            "Open", OPEN_PROJECT))
    .next(ctx -> ctx.getResultItem()
            .map(item -> item.getItem())
            .orElse(null))
    .and()
.withStringInput(CREATE_PROJECT)
    .next(ctx -> REVIEW_PROJECT)
    .and()
.withStringInput(OPEN_PROJECT)
    .next(ctx -> REVIEW_PROJECT)
    .and()
.withConfirmationInput(REVIEW_PROJECT)
    .next(ctx -> null)
    .and()
~~~

Cách này tạo ra một luồng hội tụ: cả hai nhánh đều chuyển tới bước review. Khi đổi tên component, compiler sẽ giúp tìm những vị trí tham chiếu bằng hằng số.

Không nên tạo ID từ nhãn hiển thị bằng cách nối chuỗi hoặc chuyển chữ hoa/thường trong nhiều nơi. Một quy tắc chuẩn hóa khác nhau giữa chỗ khai báo và chỗ trả target có thể gây ra ID không tồn tại.

## 11. Kết quả flow sau khi dừng

`ComponentFlow.run()` trả về `ComponentFlow.ComponentFlowResult`. Kết quả có phương thức `getContext()` để lấy context tổng hợp của flow.

~~~java
import org.springframework.shell.component.context.ComponentContext;

ComponentFlow.ComponentFlowResult result = flow.run();

ComponentContext<?> context = result.getContext();

if (context.containsKey("action")) {
    String action = context.get("action", String.class);
    System.out.println("Selected action: " + action);
}
~~~

Các component có `storeResult` mặc định là `true` sẽ tự lưu kết quả vào `ComponentContext` bằng ID được truyền khi tạo component. Có thể tắt hành vi này bằng `storeResult(false)` nếu ứng dụng không muốn lưu kết quả tự động.

Nếu flow dừng giữa chừng, chỉ nên đọc những giá trị đã được tạo. Một component bị bỏ qua do rẽ nhánh có thể chưa có giá trị trong context. Dùng `containsKey` trước khi đọc để tránh giả định mọi bước đều đã chạy.

Ví dụ:

~~~java
ComponentFlow.ComponentFlowResult result = flow.run();
ComponentContext<?> context = result.getContext();

String projectName = context.containsKey("createProject")
        ? context.get("createProject", String.class)
        : null;
~~~

Không suy ra nhánh đã chạy chỉ từ thứ tự khai báo. Hãy đọc kết quả hoặc lưu một giá trị trạng thái rõ ràng khi cần xử lý tiếp sau flow.

## 12. Builder dùng lại và reset cấu hình

Trong ứng dụng Spring, `ComponentFlow.Builder` thường được inject. Builder có các phương thức `clone()` và `reset()`.

Ví dụ trong tài liệu Spring Shell:

~~~java
ComponentFlow flow = componentFlowBuilder.clone()
        .reset()
        .withStringInput("field1")
            .name("Field1")
            .and()
        .withStringInput("field2")
            .name("Field2")
            .and()
        .build();
~~~

`clone().reset()` tạo builder riêng cho lần cấu hình flow hiện tại và xóa các cấu hình component đã thêm trước đó vào bản clone.

Khi một service tạo nhiều flow khác nhau, nên bắt đầu bằng builder clone và reset. Điều này tránh vô tình mang cấu hình component từ lần tạo flow trước sang lần tiếp theo.

Việc reset builder không kiểm tra các target trong `next`. ID vẫn phải được bảo đảm trùng với các component được khai báo trong lần build đó.

## 13. Phân biệt dừng flow với lỗi trong component

Một flow có thể dừng vì nhiều lý do:

| Tình huống | Ý nghĩa |
|---|---|
| `next` trả `null` | Kết thúc nhánh theo chủ đích |
| `next` trả ID không tồn tại | Flow dừng vì target không hợp lệ |
| `next` trả ID hợp lệ | Flow chuyển đến component đích |
| Component chạy xong và không có `next` | Tiếp tục theo thứ tự mặc định |
| Component phát sinh exception | Lỗi trong lúc component xử lý; không phải điều kiện dừng điều hướng |
| Người dùng nhập giá trị không hợp lệ | Cần xử lý ở validation/input component |

Không nên dùng các khái niệm này thay thế nhau. Ví dụ, một đường dẫn không tồn tại do người dùng nhập là vấn đề xác thực dữ liệu của `PathInput` hoặc nghiệp vụ; trả target `null` để dừng flow không tự biến đường dẫn đó thành hợp lệ.

Tương tự, exception từ một component hoặc callback không phải là một target ID không tồn tại. Hãy xem stack trace và thông báo lỗi nếu flow dừng do exception.

## 14. Thiết kế điều kiện dừng rõ ràng

Một flow dễ bảo trì nên phân biệt rõ ba kết quả:

- Tiếp tục tới một bước cụ thể.
- Kết thúc bình thường.
- Dữ liệu hoặc cấu hình không hợp lệ.

Có thể dùng hàm định tuyến riêng để tránh nhồi quá nhiều logic vào lambda:

~~~java
import org.springframework.shell.component.ConfirmationInput;

private String nextAfterConfirmation(
        ConfirmationInput.ConfirmationInputContext context) {

    if (Boolean.TRUE.equals(context.getResultValue())) {
        return "publish";
    }

    return null;
}
~~~

Gắn hàm này vào component:

~~~java
.withConfirmationInput("confirmPublish")
    .name("Publish this release?")
    .next(this::nextAfterConfirmation)
    .and()
~~~

Nếu có nhiều nhánh, dùng switch expression hoặc một phương thức định tuyến:

~~~java
private String nextAfterAction(String action) {
    return switch (action) {
        case "createProject" -> "projectDetails";
        case "openProject" -> "projectId";
        case "cancel" -> null;
        default -> throw new IllegalArgumentException(
                "Unsupported action: " + action);
    };
}
~~~

Trong ví dụ, `cancel` là kết thúc có chủ đích; giá trị khác không được hỗ trợ là lỗi dữ liệu và được báo riêng. Sau đó, cần bảo đảm các ID `projectDetails` và `projectId` thực sự được khai báo trong builder.

## 15. Tránh vòng lặp điều hướng ngoài ý muốn

Khi thiết kế flow có nhiều nhánh, hãy kiểm tra đường đi để tránh quay lại một component mà không có điều kiện thay đổi trạng thái.

Ví dụ logic định tuyến có thể trả về một ID đã chạy trước đó. Nếu nhánh đó tiếp tục trả lại cùng ID ở lần sau, quy trình có nguy cơ lặp lại.

Để kiểm soát:

- Vẽ các bước và mũi tên trước khi viết builder.
- Chỉ tạo đường quay lại khi có mục đích cho người dùng sửa dữ liệu.
- Bảo đảm điều kiện thoát khỏi nhánh lặp có thể đạt được.
- Kiểm thử trường hợp người dùng chọn lại hoặc nhập lại cùng giá trị.
- Ghi nhận số lần lặp nếu flow có thể lặp theo dữ liệu bên ngoài.

Không nên giả định mọi ID hợp lệ đều dẫn đến một flow kết thúc. ID tồn tại chỉ chứng minh component đích có trong flow; tính kết thúc còn phụ thuộc logic của các hàm `next` tiếp theo.

## 16. Kiểm thử các nhánh và điều kiện dừng

Nên kiểm thử hàm định tuyến độc lập trước. Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class ProjectFlowRoutingTests {

    @Test
    void createActionTargetsCreateStep() {
        assertThat(nextAfterAction("createProject"))
                .isEqualTo("projectDetails");
    }

    @Test
    void cancelStopsFlow() {
        assertThat(nextAfterAction("cancel")).isNull();
    }

    @Test
    void unsupportedActionIsReported() {
        assertThatThrownBy(() -> nextAfterAction("unknown"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Bên cạnh unit test cho logic điều hướng, cần kiểm thử tích hợp flow:

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Chọn nhánh A | Component A được chạy |
| Chọn nhánh B | Component B được chạy |
| Trả `null` | Flow dừng ở bước hiện tại |
| Trả ID sai | Flow dừng; test phát hiện cấu hình sai |
| Trả ID đúng nhưng component chưa chạy trước đó | Flow chuyển đến đúng component |
| Một nhánh hội tụ | Các nhánh cùng đi đến component chung |
| Component bị bỏ qua | Kết quả của component đó không bị giả định là có |
| Callback định tuyến ném exception | Lỗi được phát hiện và báo rõ |
| Builder tạo nhiều flow liên tiếp | Flow mới không thừa component từ flow cũ |

Để kiểm thử lỗi target, hãy tạo một test cố ý trả về ID sai và xác nhận flow kết thúc trước bước mong đợi. Trong code production, nên bổ sung kiểm tra target để lỗi cấu hình không bị nhầm với nhánh kết thúc bình thường.

## 17. Quy trình chẩn đoán khi flow dừng sớm

Khi người dùng nói wizard kết thúc ngay sau một lựa chọn, hãy kiểm tra theo thứ tự:

1. Xác định component cuối cùng đã hiển thị.
2. Tìm hàm `next` được gắn vào component đó.
3. Ghi nhận chính xác chuỗi mà hàm `next` trả về.
4. So sánh chuỗi đó với ID truyền vào các phương thức `with...Input(id)` và `with...Selector(id)`.
5. Kiểm tra trường hợp `null` có phải nhánh kết thúc được thiết kế hay không.
6. Kiểm tra `name()` có bị nhầm với ID hay không.
7. Kiểm tra builder có được reset trước khi tạo flow mới hay không.
8. Kiểm tra kết quả trong `ComponentFlowResult.getContext()` để biết các bước nào đã lưu dữ liệu.
9. Nếu target đúng, xem exception hoặc lỗi trong component thay vì tiếp tục điều tra điều hướng.

Một log hữu ích trong giai đoạn phát triển là ghi lại ID target trước khi trả về. Không ghi dữ liệu nhạy cảm của input nếu context có chứa mật khẩu hoặc thông tin cá nhân.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Flow dừng ngay sau selector | Giá trị item không trùng ID component | So sánh map item với ID trong builder |
| Chọn đúng nhãn nhưng không tới bước mong đợi | Nhầm nhãn `name()` với component ID | Trả về ID từ `with...Input(id)` |
| Nhánh cancel chạy tiếp | Hàm `next` trả ID thay vì `null` | Trả `null` khi cần kết thúc |
| Flow kết thúc im lặng sau khi đổi tên bước | Một hàm `next` còn giữ ID cũ | Dùng hằng số và kiểm tra target |
| Component được khai báo nhưng không xuất hiện | Nhánh hiện tại không dẫn đến ID đó | Kiểm tra đồ thị điều hướng |
| Dữ liệu của bước bị bỏ qua là `null` | Component không chạy hoặc `storeResult` tắt | Kiểm tra `containsKey` và cấu hình lưu kết quả |
| Flow mới có bước thừa từ lần trước | Dùng lại builder mà không clone/reset | Bắt đầu bằng `componentFlowBuilder.clone().reset()` |
| Không phân biệt kết thúc và lỗi cấu hình | Dùng `null` cho mọi trường hợp không nhận diện được | Chỉ dùng `null` cho kết thúc có chủ đích; báo lỗi với dữ liệu lạ |
| Hàm next truy cập kết quả bằng get() gây lỗi | Context chưa có item được chọn | Dùng `Optional.map(...).orElse(null)` |
| Flow quay lại bước cũ liên tục | Điều kiện định tuyến không thay đổi | Thiết kế điều kiện thoát và kiểm thử nhánh lặp |

## 19. Bài thực hành: wizard tạo dự án có nhánh

Tạo wizard với các bước:

- `action`: chọn tạo mới, mở dự án hoặc hủy.
- `projectDetails`: nhập tên dự án mới.
- `projectId`: nhập ID dự án hiện có.
- `confirm`: xác nhận thao tác.
- `finish`: bước kết thúc hoặc hiển thị kết quả.

Yêu cầu:

1. Khai báo tất cả component với ID riêng biệt.
2. Dùng map selector để trả về ID của nhánh.
3. Dùng `next` để chuyển từ `action` đến đúng bước.
4. Trả `null` khi người dùng chọn hủy.
5. Sau khi nhập thông tin, chuyển tới bước xác nhận.
6. Nếu xác nhận, chuyển đến `finish`.
7. Nếu từ chối, kết thúc flow.
8. Viết unit test cho từng giá trị của hàm định tuyến.
9. Tạo một test với ID sai để nhận biết flow dừng sớm.
10. Thêm kiểm tra target hợp lệ trong code production.

Kịch bản mong đợi:

~~~text
Choose an action
  1. Create a project
  2. Open an existing project
  3. Cancel

Create a project
Project name: inventory-api

Confirm?
  Yes

Project inventory-api is ready.
~~~

Nếu chọn “Open an existing project”, flow hỏi ID dự án. Nếu chọn “Cancel”, flow dừng ngay sau selector và không hỏi thêm dữ liệu.

## 20. Checklist trước khi hoàn thiện ComponentFlow

- [ ] Mỗi component có ID duy nhất và ổn định.
- [ ] Không nhầm ID với nhãn hiển thị trong `name()`.
- [ ] Hiểu thứ tự mặc định theo builder.
- [ ] Chỉ dùng `next` khi cần rẽ nhánh hoặc kết thúc rõ ràng.
- [ ] Mọi target không phải `null` đều trỏ tới ID đã khai báo.
- [ ] `null` chỉ biểu diễn điều kiện dừng có chủ đích.
- [ ] Giá trị selector được ánh xạ đúng sang ID component.
- [ ] Dùng `Optional` an toàn khi đọc kết quả selector.
- [ ] Kiểm tra target động trước khi trả về.
- [ ] Dùng `clone().reset()` khi tạo flow từ builder được inject.
- [ ] Kiểm tra `storeResult` nếu cần đọc dữ liệu sau flow.
- [ ] Không giả định component bị bỏ qua đã có kết quả.
- [ ] Kiểm thử tất cả nhánh, nhánh hủy và target sai.
- [ ] Kiểm tra điều kiện kết thúc nếu có đường quay lại bước cũ.

## 21. Kết luận

Trong Spring Shell 3.x, `ComponentFlow` chạy component theo thứ tự builder nếu không có điều hướng tùy chỉnh. Hàm `next` cho phép trả về ID của bước tiếp theo. Trả `null` là cách dừng flow có chủ đích; trả về ID không tồn tại cũng khiến flow dừng ngay tại component hiện tại.

Vì hai trường hợp này có cùng hành vi dừng, lỗi gõ sai ID có thể trông giống một nhánh kết thúc hợp lệ. Hãy dùng hằng số cho ID, kiểm tra target động, tách rõ cancel với lỗi cấu hình và kiểm thử từng đường đi. Sau khi flow kết thúc, dùng `ComponentFlowResult.getContext()` để đọc các giá trị đã được lưu và không giả định những component bị bỏ qua đã tạo kết quả.

## Tài liệu tham khảo

- [Spring Shell 3.1.6 Reference: Components Flow](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: `ComponentFlow`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ComponentFlow.html)
- [Spring Shell 3.1 API: `ComponentFlow.Builder`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ComponentFlow.Builder.html)
- [Spring Shell 3.1 API: `ComponentFlow.ComponentFlowResult`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html)
- [Spring Shell 3.1 API: `StringInputSpec`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/StringInputSpec.html)
- [Spring Shell 3.1 API: `PathInputSpec`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/PathInputSpec.html)
- [Spring Shell 3.1 API: `ConfirmationInputSpec`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ConfirmationInputSpec.html)
- [Spring Shell 3.1 API: `SingleItemSelectorSpec`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/SingleItemSelectorSpec.html)
- [Spring Shell 3.1 API: `MultiItemSelectorSpec`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/MultiItemSelectorSpec.html)
- [Spring Shell 3.1 API: `ComponentContext`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/context/ComponentContext.html)
- [Spring Shell 3.1 API: `ResultMode`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/component/flow/ResultMode.html)

