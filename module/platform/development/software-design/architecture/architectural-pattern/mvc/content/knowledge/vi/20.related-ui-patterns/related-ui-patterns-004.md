# Vai trò của Presentation Model

Trong ứng dụng MVC, View cần nhiều thông tin hơn dữ liệu nghiệp vụ thô. Một trang danh sách công việc có thể cần tiêu đề trang, nhãn trạng thái đã dịch, ngày tháng theo định dạng địa phương, bộ lọc đang chọn, trạng thái rỗng, thông tin phân trang và việc có nên hiển thị một nút thao tác hay không. Nếu View tự tính toán tất cả những điều này, template sẽ dần chứa logic và phụ thuộc vào cấu trúc của Model nghiệp vụ.

**Presentation Model** là một đối tượng mô hình hóa trạng thái và hành vi cần thiết cho phần trình bày. Nó tách những quyết định về cách hiển thị và tương tác khỏi mã giao diện cụ thể. View đọc Presentation Model để render; Controller hoặc presentation layer tạo và cập nhật model đó dựa trên dữ liệu từ use case cùng trạng thái tương tác.

Presentation Model thường nằm trong presentation layer của ứng dụng MVC. Nó không thay thế Domain Model, không phải repository và cũng không đồng nghĩa với tham số `org.springframework.ui.Model` của Spring MVC. Mục tiêu là để View trở nên đơn giản, có thể thay đổi cách trình bày mà không phải sửa quy tắc nghiệp vụ, đồng thời giữ logic hiển thị đủ rõ để kiểm thử độc lập.

## 1. Presentation Model là gì?

Presentation Model là một mẫu thiết kế giao diện (UI pattern) trong đó trạng thái và hành vi phục vụ trình bày được gom vào một đối tượng riêng. Đối tượng này mô tả giao diện cần biết gì để hiển thị và phản ứng với tương tác, thay vì để các quyết định đó rải rác trong từng widget hoặc template.

Ví dụ một màn hình danh sách công việc có thể cần:

- Danh sách hàng đã được chuẩn bị để hiển thị.
- Nhãn trạng thái dễ hiểu thay cho mã trạng thái nội bộ.
- Ngày đến hạn theo locale và timezone phù hợp.
- Bộ lọc, trang và thứ tự sắp xếp hiện tại.
- Thông tin có dữ liệu hay không.
- Các hành động có thể hiển thị với người dùng.
- Thông báo validation hoặc thông báo kết quả thao tác.
- Trạng thái loading, lỗi tải dữ liệu hoặc empty state nếu giao diện có những trạng thái đó.

Nếu không có Presentation Model, View có thể phải tự gọi hàm định dạng, so sánh trạng thái, kiểm tra nhiều điều kiện và ghép dữ liệu từ nhiều nguồn. Template trở nên khó đọc và khó kiểm thử.

Presentation Model chuyển các quyết định mang tính trình bày vào một object có cấu trúc rõ ràng. View chủ yếu đọc thuộc tính và render nội dung.

## 2. Presentation Model nằm ở đâu trong MVC?

Presentation Model thường thuộc presentation layer, nằm giữa kết quả của application use case và View. Controller nhận request, gọi application service, sau đó dùng kết quả để tạo Presentation Model.

~~~mermaid
flowchart TD
    A["HTTP request / UI interaction"] --> B["Controller"]
    B --> C["Application Service / Use Case"]
    C --> D["Domain Model"]
    C --> R["Repository Port / Adapter"]
    D --> C
    R --> C
    C --> E["Application Result / Query DTO"]
    E --> F["Presentation Model"]
    B --> F
    F --> G["View / Template"]
    G --> H["HTML / UI"]
~~~

Luồng dữ liệu thường có dạng:

1. Controller tiếp nhận request và trạng thái tương tác.
2. Application service thực hiện use case hoặc truy vấn dữ liệu.
3. Application trả về kết quả trung lập với giao diện.
4. Presentation layer ánh xạ kết quả đó thành Presentation Model.
5. View đọc Presentation Model để hiển thị.
6. Khi người dùng tương tác, View gửi lệnh mới qua Controller hoặc UI command handler.

Presentation Model có thể được tạo trong Controller, một presenter/assembler hoặc một factory thuộc presentation layer. Chọn vị trí sao cho Controller không phình to và logic ánh xạ có thể được kiểm thử riêng.

### 2.1. Presentation Model không phải một tầng nghiệp vụ mới

Presentation Model chỉ xử lý nhu cầu của giao diện. Nó có thể quyết định một nhãn được hiển thị ra sao, một vùng thông tin có xuất hiện hay không, hoặc cách biểu diễn một trạng thái rỗng. Nó không sở hữu quy tắc cốt lõi như “đơn hàng chỉ được hoàn tiền khi đã thanh toán”.

Ví dụ, Presentation Model có thể có thuộc tính `showRefundButton` để View biết có nên hiển thị nút. Nhưng khi người dùng bấm nút, application service vẫn phải xác minh quyền và trạng thái đơn hàng trước khi thực hiện hoàn tiền. Giá trị dùng để hiển thị không phải cơ chế bảo vệ nghiệp vụ.

## 3. Phân biệt các khái niệm thường bị nhầm lẫn

Tên gọi Model được dùng ở nhiều cấp độ. Cần phân biệt Presentation Model với các object khác:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| MVC Model | Khái niệm về dữ liệu/trạng thái mà View trình bày | Dữ liệu của một màn hình |
| Spring `org.springframework.ui.Model` | Container chứa attribute để chuyển từ Controller sang View | `model.addAttribute("page", pageModel)` |
| Domain Model | Mô hình hóa khái niệm và quy tắc nghiệp vụ | Task, Order, Account |
| Application DTO/Result | Dữ liệu đầu vào/đầu ra của use case | TaskSummary, CreateTaskResult |
| Presentation Model | Trạng thái và dữ liệu đã chuẩn bị cho giao diện | TaskListPresentationModel |
| ViewModel | Tên thường dùng cho object mà View binding vào | Có thể tương đương Presentation Model tùy framework |

Presentation Model là một mẫu thiết kế về cách tách logic trình bày. ViewModel là tên được dùng trong nhiều framework và kiến trúc; ở một số nơi hai khái niệm gần như đồng nghĩa, ở nơi khác ViewModel có thêm quy ước riêng.

Đặc biệt, tham số Spring `org.springframework.ui.Model` chỉ là một map-like container để thêm attribute vào model của View. Nó không tự động chứa Presentation Model pattern. Một Controller có thể thêm Presentation Model vào Spring Model:

~~~java
model.addAttribute("page", presentationModel);
~~~

Trong ví dụ này, `presentationModel` mới là object mô hình hóa trạng thái giao diện; Spring Model chỉ là nơi chuyển object đó sang template.

## 4. Presentation Model chịu trách nhiệm về điều gì?

Phạm vi chính của Presentation Model là thông tin và hành vi chỉ có ý nghĩa đối với cách giao diện hoạt động.

### 4.1. Trạng thái hiển thị

Ví dụ:
- Tab đang được chọn.
- Bộ lọc và thứ tự sắp xếp hiện tại.
- Trang hiện tại và số trang.
- Giá trị đang nhập trong form.
- Thông báo thành công hoặc lỗi.
- Loading, empty state và trạng thái hiển thị lỗi.
- Phần nội dung đang mở hoặc thu gọn.

Những trạng thái này thường không thuộc domain entity. Một Task không cần biết người dùng đang chọn tab “Tất cả” hay “Đang làm”.

### 4.2. Dữ liệu đã được định dạng

Presentation Model có thể chuẩn bị:
- Ngày theo định dạng locale.
- Số tiền theo đơn vị tiền tệ.
- Nhãn trạng thái đã dịch.
- Văn bản mô tả dễ hiểu.
- Giá trị hiển thị thay thế khi dữ liệu tùy chọn không tồn tại.
- URL hoặc thông tin điều hướng do presentation layer tạo.

Định dạng nên dùng locale/timezone được xác định rõ. Không nên tự giả định timezone của server là timezone của người dùng.

### 4.3. Trạng thái suy ra (derived state)

Một số thuộc tính được suy ra từ dữ liệu khác:

- `showEmptyState` khi danh sách không có hàng.
- `showPagination` khi có nhiều hơn một trang.
- `showClearFilter` khi người dùng đang dùng bộ lọc.
- `hasValidationErrors` khi form có lỗi.
- `showCompleteAction` khi policy cho biết hành động có thể được hiển thị.

Derived state giúp View tránh phải viết điều kiện phức tạp. Nếu một giá trị có thể tính một cách đơn giản từ các trường khác, có thể tạo accessor hoặc tính trong factory thay vì lưu trùng lặp.

### 4.4. Hành vi trình bày

Với UI tương tác nhiều, Presentation Model có thể chứa các thao tác thay đổi trạng thái giao diện như:
- Chọn tab.
- Cập nhật bộ lọc đang nhập.
- Mở/đóng panel.
- Tính trạng thái nút khi form thay đổi.
- Xác định trường nào cần hiển thị lỗi.

Các thao tác này chỉ điều khiển presentation state. Thao tác nghiệp vụ như tạo đơn, chuyển tiền hoặc xóa tài khoản vẫn phải đi qua application use case.

## 5. Điều gì không nên đặt trong Presentation Model?

Presentation Model không nên trở thành nơi gom toàn bộ ứng dụng. Các trách nhiệm sau thuộc tầng khác:

| Không nên đặt trong Presentation Model | Nơi phù hợp |
|---|---|
| Quy tắc bất biến và chuyển trạng thái nghiệp vụ | Domain Model / Domain Policy |
| Điều phối nhiều bước use case | Application Service |
| Mở transaction và quản lý commit/rollback | Application layer |
| SQL, JPQL, truy vấn database | Repository / Infrastructure |
| Xác thực danh tính | Security infrastructure |
| Quyết định quyền cuối cùng cho một hành động | Authorization policy / Application service |
| Định nghĩa route và xử lý HTTP | Controller / Web adapter |
| Gửi email hoặc gọi dịch vụ ngoài | Application use case / Infrastructure adapter |

Presentation Model có thể chứa một cờ như `canEdit` để điều khiển hiển thị. Nhưng nó không được dùng thay cho kiểm tra quyền trên server. Người dùng có thể sửa request hoặc gọi endpoint trực tiếp.

Presentation Model cũng không nên chứa HttpServletRequest, HttpSession, EntityManager hoặc một JPA entity mutable chỉ để View đọc. Những dependency đó làm object trình bày khó kiểm thử và gắn chặt vào framework hoặc vòng đời request.

## 6. Ví dụ: Presentation Model cho trang danh sách công việc

Giả sử application query service trả về dữ liệu trung lập:

~~~java
public record TaskSummary(
    UUID id,
    String title,
    TaskStatus status,
    LocalDate dueDate,
    boolean completionAllowed
) {}

public record TaskListPageData(
    List<TaskSummary> tasks,
    String selectedStatus,
    int page,
    int totalPages
) {}
~~~

Đây là application result. Nó chứa dữ liệu cần thiết cho use case truy vấn; chưa nhất thiết có nhãn trạng thái hoặc ngày đã định dạng cho giao diện.

Presentation layer tạo các kiểu riêng:

~~~java
public record TaskRowPresentation(
    UUID id,
    String title,
    String statusLabel,
    String dueDateText,
    boolean showCompleteAction
) {}

public record TaskListPresentationModel(
    String pageTitle,
    List<TaskRowPresentation> rows,
    String selectedStatus,
    int page,
    int totalPages,
    boolean showEmptyState,
    boolean showPagination,
    boolean showClearFilter
) {
    public TaskListPresentationModel {
        rows = List.copyOf(rows);
    }
}
~~~

Factory ánh xạ dữ liệu:

~~~java
public final class TaskListPresentationFactory {
    private final MessageSource messages;

    public TaskListPresentationFactory(MessageSource messages) {
        this.messages = messages;
    }

    public TaskListPresentationModel create(
        TaskListPageData data,
        Locale locale
    ) {
        DateTimeFormatter dateFormatter =
            DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale);

        List<TaskRowPresentation> rows = data.tasks().stream()
            .map(task -> new TaskRowPresentation(
                task.id(),
                task.title(),
                statusLabel(task.status(), locale),
                task.dueDate() == null
                    ? "Chưa đặt hạn"
                    : task.dueDate().format(dateFormatter),
                task.completionAllowed()
            ))
            .toList();

        boolean hasFilter =
            data.selectedStatus() != null
            && !data.selectedStatus().isBlank();

        return new TaskListPresentationModel(
            "Danh sách công việc",
            rows,
            data.selectedStatus(),
            data.page(),
            data.totalPages(),
            rows.isEmpty(),
            data.totalPages() > 1,
            hasFilter
        );
    }

    private String statusLabel(
        TaskStatus status,
        Locale locale
    ) {
        String messageCode = switch (status) {
            case OPEN -> "task.status.open";
            case IN_PROGRESS -> "task.status.in-progress";
            case DONE -> "task.status.done";
            case CANCELLED -> "task.status.cancelled";
        };

        return messages.getMessage(messageCode, null, locale);
    }
}
~~~

Ví dụ dùng Spring `MessageSource` để lấy nhãn từ message bundle theo locale. Factory cũng có thể nhận Clock, ZoneId hoặc formatter policy nếu cách hiển thị phụ thuộc thời gian và múi giờ.

Presentation Model được tạo từ dữ liệu application và quy tắc hiển thị. Nó không truy cập repository, không thay đổi Task và không tự quyết định một Task có được hoàn tất theo nghiệp vụ hay không. `completionAllowed` chỉ là thông tin để hiển thị affordance; use case complete vẫn phải xác minh quyền và trạng thái khi được gọi.

### 6.1. Controller tạo Presentation Model

~~~java
@Controller
@RequestMapping("/tasks")
class TaskController {
    private final TaskQueryService taskQueryService;
    private final TaskListPresentationFactory presentationFactory;

    TaskController(
        TaskQueryService taskQueryService,
        TaskListPresentationFactory presentationFactory
    ) {
        this.taskQueryService = taskQueryService;
        this.presentationFactory = presentationFactory;
    }

    @GetMapping
    String list(
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page,
        Locale locale,
        Model model
    ) {
        TaskListPageData data =
            taskQueryService.findPage(status, page);

        TaskListPresentationModel pageModel =
            presentationFactory.create(data, locale);

        model.addAttribute("page", pageModel);
        return "tasks/list";
    }
}
~~~

Controller tiếp nhận HTTP, gọi query service và đặt Presentation Model vào Spring Model. Template không cần biết application result hoặc domain status enum.

### 6.2. View chỉ render thuộc tính

Ví dụ Thymeleaf:

~~~html
<h1 th:text="${page.pageTitle}">Danh sách công việc</h1>

<p th:if="${page.showEmptyState}">
    Chưa có công việc phù hợp.
</p>

<table th:if="${!page.showEmptyState}">
    <tr th:each="task : ${page.rows}">
        <td th:text="${task.title}">Tên công việc</td>
        <td th:text="${task.statusLabel}">Trạng thái</td>
        <td th:text="${task.dueDateText}">Ngày đến hạn</td>
        <td>
            <form th:if="${task.showCompleteAction}"
                  th:action="@{/tasks/{id}/complete(id=${task.id})}"
                  method="post">
                <button type="submit">Hoàn tất</button>
            </form>
        </td>
    </tr>
</table>

<nav th:if="${page.showPagination}">
    <!-- Liên kết phân trang -->
</nav>
~~~

View tập trung vào cấu trúc và cách render. Nó không phải tự chuyển enum thành nhãn, định dạng ngày hoặc tính điều kiện empty state.

## 7. Presentation Model cho biểu mẫu

Form có nhiều trạng thái hơn một danh sách: dữ liệu đang nhập, lựa chọn, lỗi theo trường, thông báo chung và các option cần hiển thị.

Có thể mô hình hóa một trang tạo công việc:

~~~java
public record FieldMessage(
    String field,
    String message
) {}

public record CreateTaskPageModel(
    String title,
    String dueDate,
    List<String> categories,
    List<FieldMessage> fieldErrors,
    String formError,
    boolean canSubmit
) {
    public CreateTaskPageModel {
        categories = List.copyOf(categories);
        fieldErrors = List.copyOf(fieldErrors);
    }

    public boolean hasErrors() {
        return !fieldErrors.isEmpty()
            || formError != null;
    }
}
~~~

Khi người dùng gửi form:
1. Controller binding dữ liệu vào Form/Request object.
2. Validation kiểm tra định dạng và constraint.
3. Nếu có lỗi, Controller ánh xạ BindingResult thành thông tin hiển thị.
4. Presentation Model giữ lại giá trị đã nhập và danh sách option.
5. View render lại form cùng lỗi ở đúng trường.
6. Nếu hợp lệ, Controller tạo command và gọi use case.

Không nên đưa nguyên BindingResult hoặc exception object vào Presentation Model. Hãy chuyển chúng thành thông tin trình bày ổn định, chẳng hạn field name và message đã được chọn lọc.

Presentation Model của form có thể giữ chuỗi ngày người dùng nhập để render lại đúng nội dung. Command gửi vào application layer nên dùng kiểu dữ liệu phù hợp nghiệp vụ, ví dụ LocalDate. Hai biểu diễn có mục đích khác nhau.

### 7.1. Lỗi validation và lỗi nghiệp vụ

Validation đầu vào có thể nói “Ngày đến hạn không đúng định dạng”. Lỗi nghiệp vụ có thể nói “Không thể thay đổi ngày đến hạn vì công việc đã khóa”. Cả hai có thể xuất hiện trên form nhưng nguồn phát sinh khác nhau.

Controller/presentation layer chuyển lỗi thành FieldMessage hoặc formError. Domain/application vẫn sở hữu quy tắc và không cần biết template sẽ hiển thị thông báo ở đâu.

## 8. Presentation Model và trạng thái tương tác

Presentation Model đặc biệt hữu ích khi một màn hình có nhiều trạng thái tương tác:

- Người dùng chọn một tab và nội dung tương ứng thay đổi.
- Bộ lọc đang nhập khác với bộ lọc đã áp dụng.
- Một panel mở hoặc đóng.
- Một form có thể submit hay chưa.
- Một thao tác đang loading và tạm khóa nút.
- Một thông báo tạm thời cần biến mất sau khi người dùng xác nhận.

Ví dụ, với bộ lọc danh sách, có thể phân biệt:
- `draftFilter`: giá trị người dùng đang nhập.
- `appliedFilter`: giá trị đã gửi lên server và đang ảnh hưởng kết quả.
- `selectedTab`: tab đang được chọn.
- `resultState`: loading, success, empty hoặc error.

Không nên gom mọi trạng thái này vào domain entity. Chúng phản ánh tiến trình tương tác của giao diện.

### 8.1. Trạng thái suy ra thay vì lưu trùng lặp

Nếu `showClearFilter` luôn bằng `selectedStatus != null`, có thể tính trực tiếp từ selectedStatus. Nếu lưu cả hai field độc lập, chúng có thể lệch nhau sau một lần cập nhật.

Quy tắc:
- Lưu trạng thái nguồn khi cần.
- Tính derived state từ nguồn đó.
- Chỉ cache derived state nếu có lý do hiệu năng và có cách giữ đồng bộ.
- Tránh tạo nhiều boolean có quan hệ mâu thuẫn như isLoading, isDone, hasError mà không định nghĩa state machine.

Với màn hình có nhiều trạng thái, có thể dùng enum hoặc sealed type thay cho tập boolean tùy ý. Ví dụ `LoadState = Loading | Loaded(data) | Failed(message)` giúp tránh trạng thái vừa loading vừa failed.

## 9. Vòng đời Presentation Model trong ứng dụng server-rendered

Trong Spring MVC server-rendered, mỗi HTTP request thường tạo Presentation Model mới cho response đó. View render xong thì object không còn được dùng như một store lâu dài.

Điều này có nghĩa:
- Bộ lọc cần duy trì qua request nên nằm trong query parameter hoặc form state được gửi lại.
- Thông báo sau redirect có thể dùng flash attribute hoặc cơ chế message phù hợp.
- Dữ liệu cần tồn tại qua nhiều bước có thể nằm trong session hoặc kho lưu trữ có vòng đời rõ.
- Không lưu Presentation Model mutable của một người dùng vào field của Controller singleton.

Một Controller singleton có thể nhận nhiều request đồng thời. Nếu giữ `currentPageModel` trong field, request của người dùng này có thể ghi đè trạng thái của người dùng khác. Hãy tạo model trong biến cục bộ cho từng request.

### 9.1. Post/Redirect/Get

Với form thành công, mô hình Post/Redirect/Get thường được dùng:
1. POST nhận dữ liệu và gọi use case.
2. Server lưu thay đổi.
3. Controller redirect sang trang kết quả.
4. GET tạo Presentation Model mới từ dữ liệu đã lưu.

Cách này tránh trình duyệt gửi lại POST khi refresh trang. Nếu cần hiển thị thông báo sau redirect, có thể dùng flash attribute, nhưng không nên coi flash attribute là nơi lưu trạng thái nghiệp vụ lâu dài.

## 10. Presentation Model trong SPA hoặc UI client-side

Trong ứng dụng SPA, Presentation Model có thể nằm ở client và giữ state qua nhiều tương tác mà không cần tải lại toàn bộ trang. Framework có thể gọi object này là ViewModel, store hoặc component state.

Ví dụ:
- State của form.
- Danh sách đang hiển thị.
- Loading/error state của API call.
- Bộ lọc và sắp xếp.
- Trạng thái modal hoặc drawer.
- Selection và trạng thái phân trang.

Client-side Presentation Model không phải nguồn có thẩm quyền cho dữ liệu nghiệp vụ. Người dùng có thể sửa state trong trình duyệt. Server vẫn phải xác thực, phân quyền và kiểm tra bất biến.

Nếu dùng React, Vue, Angular hoặc framework khác, state có thể được quản lý qua component, store hoặc reactive model. Không cần tạo một class Presentation Model riêng cho mọi component; pattern hữu ích khi logic trình bày đủ phức tạp hoặc cần tái sử dụng/kiểm thử độc lập.

## 11. Presentation Model so với MVP và MVVM

Presentation Model có quan hệ gần với các pattern giao diện khác, nhưng không hoàn toàn đồng nhất:

| Pattern | Thành phần trung gian | View tương tác với logic như thế nào? |
|---|---|---|
| MVC | Controller và Model | Controller xử lý input; View hiển thị dữ liệu từ Model |
| Presentation Model | Object mô hình hóa trạng thái/hành vi trình bày | View đọc và đồng bộ với Presentation Model |
| MVP | Presenter | View thường là passive; Presenter điều khiển View qua interface |
| MVVM | ViewModel | View binding với thuộc tính/command của ViewModel, thường qua data binding |

### 11.1. Presentation Model và MVC

MVC truyền thống không bắt buộc phải có Presentation Model riêng. Ở ứng dụng đơn giản, Controller có thể chuẩn bị vài attribute cho View. Khi logic hiển thị tăng lên, Presentation Model giúp gom logic đó thành một object có cấu trúc và có thể kiểm thử.

### 11.2. Presentation Model và MVP

Trong MVP, Presenter thường là thành phần điều khiển View thông qua interface. Presentation Model có thể chứa trạng thái hiển thị mà View quan sát, còn Presenter có thể điều phối sự kiện và cập nhật model. Hai pattern có thể được kết hợp, nhưng không nên đồng nhất vai trò của chúng.

### 11.3. Presentation Model và MVVM

MVVM thường sử dụng data binding để View tự đồng bộ với ViewModel. ViewModel có thể chứa observable property và command. Presentation Model có thể được xem là một ý tưởng gần với ViewModel, nhưng không phải mọi Presentation Model đều có cơ chế binding hoặc command như MVVM.

Tên gọi phụ thuộc framework và tài liệu. Khi đọc codebase, hãy xem object thực sự làm gì thay vì chỉ dựa vào tên class.

## 12. Kiểm thử Presentation Model

Một lợi ích lớn của Presentation Model là có thể kiểm thử logic trình bày mà không cần render giao diện hoặc chạy database.

Các nhóm test:

| Loại test | Nội dung |
|---|---|
| Mapping test | Application result được ánh xạ đúng thành Presentation Model |
| Derived state test | Empty state, pagination, filter indicator được tính đúng |
| Formatting test | Ngày, số tiền, nhãn trạng thái theo locale/timezone |
| Form state test | Giá trị nhập và lỗi validation được giữ đúng |
| Interaction state test | Chọn tab, mở panel, loading/error state thay đổi đúng |
| MVC test | Controller đặt đúng Presentation Model vào View hoặc response |
| View test | Template render đúng thuộc tính và trạng thái |

Ví dụ unit test cho factory:

~~~java
@Test
void createsEmptyStateWhenNoTasksExist() {
    TaskListPageData data = new TaskListPageData(
        List.of(),
        null,
        0,
        0
    );

    TaskListPresentationModel model =
        factory.create(data, Locale.forLanguageTag("vi-VN"));

    assertThat(model.rows()).isEmpty();
    assertThat(model.showEmptyState()).isTrue();
    assertThat(model.showPagination()).isFalse();
    assertThat(model.showClearFilter()).isFalse();
}
~~~

Test này không cần Spring context hoặc database. Nó chỉ xác minh quy tắc trình bày trong factory.

Ví dụ kiểm thử nhãn và ngày:

~~~java
@Test
void formatsTaskRowForVietnameseLocale() {
    TaskSummary task = new TaskSummary(
        UUID.fromString("8b1e4f5a-0000-0000-0000-000000000001"),
        "Chuẩn bị báo cáo",
        TaskStatus.OPEN,
        LocalDate.of(2026, 11, 19),
        true
    );

    TaskListPageData data = new TaskListPageData(
        List.of(task),
        "OPEN",
        0,
        1
    );

    TaskListPresentationModel model =
        factory.create(data, Locale.forLanguageTag("vi-VN"));

    assertThat(model.rows()).hasSize(1);
    assertThat(model.rows().get(0).statusLabel())
        .isEqualTo("Đang mở");
    assertThat(model.rows().get(0).showCompleteAction())
        .isTrue();
}
~~~

Ngày định dạng có thể khác theo JDK locale provider; nếu cần test chuỗi chính xác, hãy cố định formatter và môi trường locale hoặc kiểm tra thuộc tính có ý nghĩa thay vì phụ thuộc cấu hình máy.

### 12.1. Không kiểm thử quyền chỉ qua Presentation Model

Test xác minh `showCompleteAction == true` chỉ chứng minh giao diện được hướng dẫn hiển thị nút. Cần có test riêng cho use case complete để chứng minh server từ chối người không có quyền hoặc task không ở trạng thái phù hợp.

Presentation test và authorization test bảo vệ hai trách nhiệm khác nhau.

## 13. Accessibility và tính nhất quán giao diện

Presentation Model cũng giúp View biểu diễn trạng thái một cách nhất quán và dễ tiếp cận:

- Trạng thái loading có nhãn mà công nghệ hỗ trợ có thể nhận biết.
- Lỗi form gắn với đúng trường và có thông báo rõ.
- Empty state giải thích vì sao không có kết quả và cách tiếp tục.
- Nút bị vô hiệu hóa có lý do nếu điều đó hữu ích.
- Trạng thái không chỉ được biểu diễn bằng màu sắc.
- Ngày và số được định dạng theo locale nhưng vẫn có giá trị ngữ nghĩa rõ ràng.

Không nên để Presentation Model chỉ cung cấp màu hoặc icon mà không có nhãn văn bản tương ứng. View vẫn cần dùng semantic HTML và thuộc tính accessibility phù hợp; Presentation Model cung cấp trạng thái và nội dung, còn View quyết định cấu trúc markup.

## 14. Khi nào nên dùng Presentation Model?

Presentation Model hữu ích khi:
- View có nhiều điều kiện hiển thị.
- Nhiều trường cần format hoặc dịch nhãn.
- Một màn hình kết hợp dữ liệu từ nhiều use case.
- Form có nhiều trạng thái và lỗi.
- Logic hiển thị được dùng lại ở nhiều View.
- Muốn kiểm thử logic trình bày mà không cần chạy giao diện.
- Template hoặc UI component đang chứa nhiều biểu thức và điều kiện.

Không nhất thiết phải tạo Presentation Model cho một trang tĩnh chỉ hiển thị một chuỗi. Nếu object chỉ sao chép từng thuộc tính từ DTO sang một object khác mà không thêm ngữ nghĩa trình bày, nó có thể tạo boilerplate không cần thiết.

Có thể bắt đầu với ViewModel nhỏ khi xuất hiện logic hiển thị lặp lại, sau đó mở rộng khi nhu cầu thực sự tăng.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm Spring Model với Presentation Model | Chỉ có container attribute, logic hiển thị vẫn rải trong template | Tạo object riêng mô hình hóa UI state |
| Đưa toàn bộ Domain Entity vào Presentation Model | Giao diện phụ thuộc cấu trúc nghiệp vụ và persistence | Ánh xạ sang dữ liệu trình bày tối thiểu |
| Đưa quy tắc nghiệp vụ vào Presentation Model | Các nguồn gọi khác không được bảo vệ cùng quy tắc | Đưa invariant vào domain/application |
| Presentation Model truy cập repository | UI object bị gắn với persistence | Tạo model từ application result |
| Dùng cờ hiển thị thay cho authorization | Người dùng vẫn có thể gọi endpoint trực tiếp | Kiểm tra quyền ở server mỗi lần thực hiện |
| Lưu model mutable trong singleton Controller | Request người dùng có thể ghi đè trạng thái nhau | Tạo instance theo request hoặc dùng store có phạm vi rõ |
| Lưu trùng lặp derived state | Các thuộc tính hiển thị có thể mâu thuẫn | Tính derived state từ nguồn |
| Nhồi mọi thứ vào một ViewModel lớn | Model khó hiểu và khó kiểm thử | Chia theo màn hình hoặc vùng trình bày |
| Dùng Presentation Model cho trang quá đơn giản | Tăng lớp và boilerplate | Chỉ áp dụng khi có logic trình bày đáng kể |
| Đưa HTTP/session/framework object vào model | Khó kiểm thử và phụ thuộc vòng đời ngoài | Dùng kiểu dữ liệu độc lập framework |

## 16. Quy trình thiết kế Presentation Model

Khi một màn hình bắt đầu có logic trình bày phức tạp, hãy thực hiện:

1. Liệt kê dữ liệu mà View cần hiển thị.
2. Liệt kê trạng thái tương tác: filter, tab, loading, empty, error và form state.
3. Xác định thuộc tính nào là dữ liệu nguồn, thuộc tính nào có thể suy ra.
4. Xác định dữ liệu nào đến từ application use case.
5. Ánh xạ dữ liệu nghiệp vụ sang nhãn, định dạng và cấu trúc trình bày.
6. Đưa logic trình bày vào factory/assembler hoặc Presentation Model khi phù hợp.
7. Giữ quy tắc nghiệp vụ và authorization ở tầng có thẩm quyền.
8. Chọn vòng đời model phù hợp: theo request, component hoặc store.
9. Giữ View tập trung vào render và tương tác.
10. Viết unit test cho mapping, derived state, formatting và validation display.

Nếu màn hình được render ở server, model thường được tạo mới cho từng request. Nếu UI chạy phía client, state có thể tồn tại trong component hoặc store lâu hơn. Trong cả hai trường hợp, không được để trạng thái giao diện trở thành nguồn có thẩm quyền cho dữ liệu nghiệp vụ.

## 17. Những điểm cần ghi nhớ

Presentation Model mô hình hóa trạng thái và hành vi phục vụ giao diện. Nó giúp View nhận dữ liệu đã được chuẩn bị, nhãn đã định dạng, trạng thái hiển thị và thông tin tương tác mà không phải tự thực hiện nhiều phép tính hoặc biết chi tiết domain/persistence.

Trong MVC, Presentation Model thường thuộc presentation layer và được tạo từ kết quả application use case. Nó khác với Domain Model, application DTO và Spring `org.springframework.ui.Model`; Spring Model chỉ là container truyền attribute sang View. ViewModel là tên gần nghĩa trong nhiều framework, nhưng cần xem cách object thực sự được dùng.

Hãy giữ Presentation Model độc lập với database và HTTP, không đặt quy tắc nghiệp vụ hoặc quyền cuối cùng vào đó, không lưu state mutable theo người dùng trong singleton Controller và không tạo abstraction cho màn hình quá đơn giản. Kiểm thử mapping, formatting và derived state riêng; đồng thời kiểm thử use case để bảo đảm các hành động vẫn được xác thực và phân quyền ở server.

Khi dùng đúng chỗ, Presentation Model tạo một hợp đồng rõ giữa application result và View. Giao diện có thể thay đổi cách bố trí hoặc framework trình bày mà không kéo theo thay đổi không cần thiết ở domain và persistence.
