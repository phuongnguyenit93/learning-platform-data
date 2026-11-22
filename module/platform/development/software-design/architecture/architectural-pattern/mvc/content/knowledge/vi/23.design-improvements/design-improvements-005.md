# Tách dữ liệu biểu mẫu và dữ liệu trình bày

Trong ứng dụng MVC, dữ liệu người dùng gửi lên và dữ liệu giao diện cần hiển thị thường có hình dạng khác nhau. Một biểu mẫu tạo công việc chỉ cần các trường người dùng được phép nhập như tiêu đề, ngày đến hạn và danh mục. Trang hiển thị lại có thể cần thêm nhãn trạng thái, danh sách danh mục, mô tả hướng dẫn, quyền hiển thị nút, thông tin phân trang và thông báo lỗi.

Nếu dùng cùng một đối tượng cho cả hai chiều, ứng dụng dễ gặp các vấn đề: client có thể gửi thêm trường nội bộ, View phụ thuộc vào cấu trúc entity, dữ liệu hiển thị bị trộn với dữ liệu ghi, validation khó kiểm soát và thay đổi giao diện có thể ảnh hưởng hợp đồng API hoặc nghiệp vụ.

Cải tiến thiết kế là **tách dữ liệu biểu mẫu (Form/Input Model) khỏi dữ liệu trình bày (Presentation Model/ViewModel)**. Form Model mô tả những gì client được phép gửi cho một thao tác. Presentation Model mô tả những gì View cần để render một màn hình. Application Command và Domain Model tiếp tục giữ trách nhiệm thực hiện use case và bảo vệ quy tắc nghiệp vụ.

Trong module **MODEL_VIEW_CONTROLLER**, cách tách này làm rõ luồng request, hợp đồng dữ liệu, xử lý biểu mẫu, lỗi, bảo mật và kiểm thử. Controller nhận Form Model, chuyển dữ liệu hợp lệ thành command, gọi use case, sau đó chuẩn bị Presentation Model cho View.

## 1. Vì sao không nên dùng một object cho cả form và View?

Giả sử một trang chỉnh sửa công việc hiển thị:

- Tiêu đề.
- Ngày đến hạn.
- Danh mục.
- Trạng thái hiện tại.
- Người tạo.
- Thời điểm tạo và cập nhật.
- Nhãn trạng thái đã dịch.
- Danh sách danh mục có thể chọn.
- Nút “Hoàn tất” hoặc “Hủy” tùy quyền và trạng thái.

Người dùng chỉ được phép sửa tiêu đề, ngày đến hạn và danh mục. Các trường như người tạo, thời điểm tạo, trạng thái hoặc quyền thao tác do server quản lý.

Nếu bind request thẳng vào một entity có tất cả thuộc tính, client có thể thử gửi thêm `ownerId`, `status`, `createdAt` hoặc các trường nội bộ khác. Đây là một dạng mass assignment/overposting. Ngay cả khi framework bỏ qua một số trường, việc dùng entity làm hợp đồng request vẫn khiến phạm vi cập nhật không rõ ràng.

Nếu dùng chính object form để render, nó lại thiếu các dữ liệu chỉ dành cho giao diện như nhãn trạng thái, danh sách option hoặc thông tin phân trang. Khi đó, các thuộc tính trình bày dễ bị thêm dần vào object đầu vào và làm hai trách nhiệm dính chặt.

Tách hai loại dữ liệu giúp xác định rõ:

- Form Model: người dùng được nhập gì?
- Presentation Model: màn hình cần hiển thị gì?
- Application Command: use case cần thực hiện điều gì?
- Domain Model: quy tắc và trạng thái nghiệp vụ được bảo vệ ra sao?

## 2. Bản đồ các loại object trong luồng MVC

Tên gọi có thể khác giữa các framework, nhưng một ứng dụng MVC thường có những hợp đồng dữ liệu sau:

| Object | Hướng dữ liệu | Trách nhiệm |
|---|---|---|
| Form Model / Input DTO | Client → Controller | Chứa các trường được phép gửi và validation đầu vào |
| Application Command | Controller → Application | Diễn đạt yêu cầu use case sau khi đã bổ sung ngữ cảnh tin cậy |
| Domain Model / Entity | Bên trong nghiệp vụ | Giữ trạng thái và bảo vệ bất biến |
| Query DTO / Application Result | Application → Presentation | Trả dữ liệu cần thiết từ use case truy vấn |
| Presentation Model / ViewModel | Controller/Presenter → View | Chứa dữ liệu đã chuẩn bị để hiển thị |
| Response DTO | Server → API client | Định nghĩa hợp đồng JSON hoặc response công khai |

Các object này không nhất thiết phải là nhiều class trong mọi ứng dụng. Với một màn hình rất đơn giản, một DTO có thể vừa đủ dùng. Việc tách nên phản ánh sự khác biệt thật về trách nhiệm, quyền sở hữu dữ liệu và vòng đời.

### 2.1. Luồng dữ liệu tổng thể

~~~mermaid
flowchart TD
    A["View: form và dữ liệu hiển thị"] --> B["HTTP request"]
    B --> C["Controller: binding Form Model"]
    C --> D{"Đầu vào hợp lệ?"}
    D -->|Không| E["Giữ Form Model + lỗi"]
    E --> F["Tạo Presentation Model cho màn hình"]
    F --> G["Render lại View"]
    D -->|Có| H["Tạo Application Command"]
    H --> I["Application Service / Use Case"]
    I --> J["Domain Model + Repository"]
    J --> K["Application Result"]
    K --> L["Tạo Presentation Model hoặc Response DTO"]
    L --> M["View / API response"]
~~~

Trong luồng này, Form Model không đi thẳng vào database. Controller hoặc application boundary chuyển nó thành command. Application service kiểm tra quyền và điều phối nghiệp vụ. Domain Model bảo vệ bất biến. Kết quả sau đó được ánh xạ thành dữ liệu trình bày phù hợp với màn hình.

## 3. Form Model chỉ chứa dữ liệu client được phép gửi

Form Model mô tả hợp đồng đầu vào cho một thao tác cụ thể. Ví dụ tạo công việc:

~~~java
public record CreateTaskForm(
    @NotBlank(message = "Tiêu đề không được để trống")
    @Size(max = 120, message = "Tiêu đề tối đa 120 ký tự")
    String title,

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate dueDate,

    @NotNull(message = "Hãy chọn danh mục")
    UUID categoryId
) {}
~~~

Các trường trên là những gì người dùng được phép nhập. Form không có `ownerId`, `status`, `createdAt` hoặc `isAdmin`. Server sẽ lấy owner từ principal đã xác thực và áp dụng trạng thái mặc định theo quy tắc nghiệp vụ.

Form Model có thể chứa annotation validation để kiểm tra cú pháp và giới hạn đầu vào. Tuy nhiên, validation ở form không thay thế quy tắc domain. Ví dụ, categoryId có định dạng UUID hợp lệ chưa có nghĩa danh mục đó tồn tại hoặc người dùng được phép sử dụng.

### 3.1. Form Model theo thao tác

Không nhất thiết dùng một Form Model cho mọi thao tác. Tạo mới và chỉnh sửa có thể có trường khác nhau:

~~~java
public record CreateTaskForm(
    @NotBlank @Size(max = 120) String title,
    LocalDate dueDate,
    @NotNull UUID categoryId
) {}

public record UpdateTaskForm(
    @NotBlank @Size(max = 120) String title,
    LocalDate dueDate,
    @NotNull UUID categoryId
) {}
~~~

Nếu hai thao tác có cùng hợp đồng và cùng quy tắc, có thể dùng chung một type. Nếu quyền, trường được phép thay đổi hoặc quy tắc khác nhau, tách riêng giúp tránh vô tình mở rộng quyền ghi.

Ví dụ, màn hình cập nhật hồ sơ cá nhân không nên nhận role, trạng thái tài khoản hoặc cờ xác minh email chỉ vì entity User có các thuộc tính đó.

### 3.2. Không bind trực tiếp vào Domain Entity

Cách dễ gây lỗi:

~~~java
@PostMapping("/tasks")
String create(@ModelAttribute Task task) {
    taskRepository.save(task);
    return "redirect:/tasks";
}
~~~

Ở đây, framework có thể bind các thuộc tính có thể ghi của entity từ request. Phạm vi dữ liệu được phép cập nhật trở nên phụ thuộc vào cấu trúc entity và cơ chế binding.

Cách rõ ràng hơn:

~~~java
@PostMapping("/tasks")
String create(
    @Valid @ModelAttribute("form") CreateTaskForm form,
    BindingResult errors
) {
    // Kiểm tra lỗi, tạo command và gọi use case
}
~~~

Controller chỉ nhận các trường được định nghĩa trong Form Model. Application service vẫn phải xác minh quyền và quy tắc nghiệp vụ trước khi lưu.

## 4. Presentation Model chỉ chứa dữ liệu cần để render

Presentation Model mô tả màn hình, không mô tả những gì client được phép ghi. Ví dụ trang tạo công việc cần tiêu đề trang, danh sách danh mục, nội dung trợ giúp và trạng thái hiển thị:

~~~java
public record CategoryOption(
    UUID id,
    String label
) {}

public record CreateTaskPageModel(
    String pageTitle,
    List<CategoryOption> categories,
    String dueDateHelp,
    String submitLabel
) {
    public CreateTaskPageModel {
        categories = List.copyOf(categories);
    }
}
~~~

Presentation Model có thể chứa:
- Nhãn đã dịch.
- Giá trị ngày/tiền đã định dạng.
- Danh sách option cho select.
- Trạng thái empty/loading/error.
- Thông tin phân trang.
- Thông báo hướng dẫn.
- Cờ hiển thị một thành phần giao diện.
- Link hoặc action label đã chuẩn bị.

Các trường này không nhất thiết được gửi ngược về server khi submit. Chúng là dữ liệu đầu ra để View render.

### 4.1. ViewModel không phải nơi lưu quy tắc nghiệp vụ

Ví dụ Presentation Model có thể chứa `showCompleteButton` để View biết có nên hiển thị nút hoàn tất. Nhưng khi người dùng bấm nút, application service vẫn phải kiểm tra quyền và trạng thái Task. Client có thể tự tạo request dù nút bị ẩn.

Cờ hiển thị là gợi ý cho giao diện, không phải kiểm soát bảo mật.

### 4.2. Trạng thái suy ra và dữ liệu nguồn

Presentation Model có thể tính `showEmptyState` từ danh sách hàng hoặc `showPagination` từ totalPages. Nếu có thể suy ra đơn giản từ dữ liệu nguồn, không cần lưu thêm nhiều boolean có thể mâu thuẫn.

Ví dụ:

~~~java
public record TaskListPageModel(
    List<TaskRowViewModel> rows,
    int page,
    int totalPages
) {
    public boolean isEmpty() {
        return rows.isEmpty();
    }

    public boolean showPagination() {
        return totalPages > 1;
    }
}
~~~

Nếu state của màn hình phức tạp hơn, hãy mô hình hóa các trạng thái rõ ràng thay vì kết hợp nhiều cờ rời rạc như isLoading, hasError, isComplete mà không định nghĩa chuyển tiếp hợp lệ.

## 5. Phân biệt Form Model, Command, Domain Model và ViewModel

Bốn object có thể cùng mô tả một công việc nhưng mỗi object trả lời một câu hỏi khác nhau:

~~~java
// Dữ liệu người dùng được phép nhập.
public record CreateTaskForm(
    String title,
    LocalDate dueDate,
    UUID categoryId
) {}

// Yêu cầu ứng dụng cần thực hiện; owner do server bổ sung.
public record CreateTaskCommand(
    String title,
    LocalDate dueDate,
    UUID categoryId,
    UUID ownerId
) {}

// Dữ liệu kết quả truy vấn phục vụ màn hình.
public record TaskDetailQueryResult(
    UUID id,
    String title,
    TaskStatus status,
    LocalDate dueDate,
    String categoryName
) {}

// Dữ liệu đã chuẩn bị để render.
public record TaskDetailViewModel(
    String title,
    String statusLabel,
    String dueDateText,
    String categoryLabel,
    boolean showCompleteAction
) {}
~~~

Domain Model có thể là một class riêng với phương thức chuyển trạng thái và bất biến. Nó không nhất thiết trùng với TaskDetailQueryResult hoặc TaskDetailViewModel.

| Câu hỏi | Object trả lời |
|---|---|
| Người dùng được nhập gì? | Form Model |
| Server muốn thực hiện use case nào? | Application Command |
| Trạng thái nghiệp vụ hợp lệ ra sao? | Domain Model |
| Màn hình cần hiển thị gì? | Presentation Model |
| API công khai trả dữ liệu nào? | Response DTO |

Việc tách này đặc biệt hữu ích khi form và màn hình có vòng đời khác nhau hoặc khi API contract không giống giao diện HTML.

## 6. Ví dụ hoàn chỉnh với Spring MVC

Xét trang tạo công việc. Người dùng nhập tiêu đề, ngày đến hạn và danh mục. Server cần cung cấp danh sách danh mục đang hoạt động, giữ dữ liệu form nếu validation thất bại và gán owner từ principal.

### 6.1. Form Model và Presentation Model

~~~java
public record CreateTaskForm(
    @NotBlank(message = "Tiêu đề không được để trống")
    @Size(max = 120, message = "Tiêu đề tối đa 120 ký tự")
    String title,

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate dueDate,

    @NotNull(message = "Hãy chọn danh mục")
    UUID categoryId
) {}

public record CategoryOption(
    UUID id,
    String label
) {}

public record CreateTaskPageModel(
    String heading,
    List<CategoryOption> categories,
    String dateHint,
    String submitLabel
) {
    public CreateTaskPageModel {
        categories = List.copyOf(categories);
    }
}
~~~

Form Model chỉ có title, dueDate và categoryId. Page Model chứa dữ liệu phụ để hiển thị form. Chúng có thể được tạo và truyền cùng lúc cho template nhưng không nên bị trộn thành một object đầu vào duy nhất.

### 6.2. Factory tạo dữ liệu trình bày

~~~java
@Component
class CreateTaskPageFactory {
    private final CategoryQueryService categories;
    private final MessageSource messages;

    CreateTaskPageFactory(
        CategoryQueryService categories,
        MessageSource messages
    ) {
        this.categories = categories;
        this.messages = messages;
    }

    CreateTaskPageModel create(UUID ownerId, Locale locale) {
        List<CategoryOption> options =
            categories.findAvailableFor(ownerId).stream()
                .map(category -> new CategoryOption(
                    category.id(),
                    category.displayName()
                ))
                .toList();

        return new CreateTaskPageModel(
            messages.getMessage("task.create.heading", null, locale),
            options,
            messages.getMessage("task.create.due-date-hint", null, locale),
            messages.getMessage("task.create.submit", null, locale)
        );
    }
}
~~~

Factory gom việc chuẩn bị dữ liệu dành riêng cho trang. Ví dụ dùng Spring `MessageSource` để lấy nội dung theo locale; các message code được khai báo trong message bundle của ứng dụng. Factory có thể gọi query service để lấy danh sách option và định dạng nhãn. Nó không nên tự lưu Task hoặc thực hiện quy tắc chuyển trạng thái.

Nếu việc lấy option cần nhiều dữ liệu hoặc có quy tắc truy cập, query service phải giới hạn kết quả theo người dùng/tenant. Không lấy mọi danh mục rồi chỉ ẩn những mục không được phép trong template.

### 6.3. Application Command và Use Case

~~~java
public record CreateTaskCommand(
    String title,
    LocalDate dueDate,
    UUID categoryId,
    UUID ownerId
) {}

public record CreateTaskResult(UUID taskId) {}

public interface CreateTaskUseCase {
    CreateTaskResult handle(CreateTaskCommand command);
}
~~~

Controller tạo command sau khi xác thực Form Model. ownerId lấy từ principal, không lấy từ form.

Application service có thể kiểm tra danh mục thuộc phạm vi được phép, tạo domain object và lưu trong transaction:

~~~java
@Service
class CreateTaskService implements CreateTaskUseCase {
    private final TaskRepository tasks;
    private final CategoryRepository categories;

    CreateTaskService(
        TaskRepository tasks,
        CategoryRepository categories
    ) {
        this.tasks = tasks;
        this.categories = categories;
    }

    @Transactional
    public CreateTaskResult handle(CreateTaskCommand command) {
        Category category = categories
            .findAvailableForOwner(
                command.categoryId(),
                command.ownerId()
            )
            .orElseThrow(CategoryNotAvailableException::new);

        Task task = Task.create(
            command.title(),
            command.dueDate(),
            category.id(),
            command.ownerId()
        );

        tasks.save(task);
        return new CreateTaskResult(task.id());
    }
}
~~~

Ví dụ giả định repository cung cấp phương thức giới hạn danh mục theo owner. Quy tắc domain như tiêu đề hợp lệ hoặc trạng thái khởi tạo vẫn cần được bảo vệ trong Task. Transaction nằm quanh use case vì đây là ranh giới điều phối thao tác ghi.

### 6.4. Controller kết hợp hai hợp đồng

~~~java
@Controller
@RequestMapping("/tasks")
class TaskController {
    private final CreateTaskUseCase createTask;
    private final CreateTaskPageFactory pageFactory;

    TaskController(
        CreateTaskUseCase createTask,
        CreateTaskPageFactory pageFactory
    ) {
        this.createTask = createTask;
        this.pageFactory = pageFactory;
    }

    // Các route này được bảo vệ bởi authentication policy của ứng dụng.
    @GetMapping("/new")
    String newForm(
        @AuthenticationPrincipal AppPrincipal principal,
        Locale locale,
        Model model
    ) {
        model.addAttribute("form", new CreateTaskForm("", null, null));
        model.addAttribute(
            "page",
            pageFactory.create(principal.userId(), locale)
        );

        return "tasks/new";
    }

    @PostMapping
    String create(
        @Valid @ModelAttribute("form") CreateTaskForm form,
        BindingResult errors,
        @AuthenticationPrincipal AppPrincipal principal,
        Locale locale,
        Model model,
        RedirectAttributes redirect
    ) {
        if (errors.hasErrors()) {
            model.addAttribute(
                "page",
                pageFactory.create(principal.userId(), locale)
            );
            return "tasks/new";
        }

        CreateTaskResult result = createTask.handle(
            new CreateTaskCommand(
                form.title(),
                form.dueDate(),
                form.categoryId(),
                principal.userId()
            )
        );

        redirect.addFlashAttribute(
            "notice",
            "Đã tạo công việc."
        );

        return "redirect:/tasks/" + result.taskId();
    }
}
~~~

Một số điểm quan trọng:

- `BindingResult` đứng ngay sau tham số `@Valid` mà nó nhận lỗi.
- Khi validation thất bại, Controller giữ Form Model đã binding và tạo lại Page Model cần thiết để render.
- Khi hợp lệ, Controller ánh xạ Form Model thành Application Command.
- ownerId lấy từ principal đã xác thực.
- Use case quyết định dữ liệu có được tạo hay không.
- Sau thành công, Controller redirect để áp dụng Post/Redirect/Get.

Lỗi nghiệp vụ như danh mục vừa bị vô hiệu hóa có thể xảy ra sau validation. Controller hoặc exception handler cần chuyển lỗi đó thành thông báo phù hợp cho form; không được giả định dữ liệu hợp lệ về cú pháp là luôn hợp lệ về nghiệp vụ.

### 6.5. View nhận Form Model và Page Model riêng

Ví dụ Thymeleaf:

~~~html
<h1 th:text="${page.heading}">Tạo công việc</h1>

<form th:action="@{/tasks}" th:object="${form}" method="post">
    <label for="title">Tiêu đề</label>
    <input id="title" type="text" th:field="*{title}" />
    <p th:if="${#fields.hasErrors('title')}"
       th:errors="*{title}"></p>

    <label for="dueDate">Ngày đến hạn</label>
    <input id="dueDate" type="date" th:field="*{dueDate}" />
    <small th:text="${page.dateHint}"></small>
    <p th:if="${#fields.hasErrors('dueDate')}"
       th:errors="*{dueDate}"></p>

    <label for="categoryId">Danh mục</label>
    <select id="categoryId" th:field="*{categoryId}">
        <option value="">Chọn danh mục</option>
        <option th:each="category : ${page.categories}"
                th:value="${category.id}"
                th:text="${category.label}">
        </option>
    </select>
    <p th:if="${#fields.hasErrors('categoryId')}"
       th:errors="*{categoryId}"></p>

    <button type="submit" th:text="${page.submitLabel}">Tạo công việc</button>
</form>
~~~

Form binding dùng `form`; dữ liệu phụ của trang dùng `page`. View không cần biết Application Command hoặc Domain Entity. Với tích hợp Thymeleaf–Spring Security, token CSRF thường được thêm tự động vào form POST; nếu ứng dụng tùy biến cơ chế này, cần bảo đảm form gửi token theo cấu hình bảo mật.

## 7. Xử lý validation mà không trộn hai loại dữ liệu

Có ít nhất ba nhóm lỗi khác nhau:

1. **Binding error:** không thể chuyển chuỗi request thành kiểu dữ liệu mong muốn, ví dụ ngày không đúng định dạng.
2. **Input validation:** dữ liệu không thỏa constraint của form, ví dụ title rỗng hoặc dài quá giới hạn.
3. **Business validation:** dữ liệu đúng định dạng nhưng không hợp lệ theo trạng thái hoặc quy tắc nghiệp vụ, ví dụ danh mục đã đóng hoặc người dùng không được tạo task trong dự án đó.

Form Model và BindingResult hỗ trợ nhóm đầu và nhóm thứ hai. Application/Domain chịu trách nhiệm nhóm thứ ba. Presentation layer chuyển lỗi thành thông báo mà người dùng hiểu được.

### 7.1. Giữ dữ liệu form khi lỗi

Với lỗi validation, thường render lại cùng template trong POST để giữ dữ liệu và lỗi. Cần nạp lại các dữ liệu phụ như danh sách danh mục, danh sách quốc gia hoặc lựa chọn tham chiếu. Nếu chỉ trả template mà thiếu Page Model, form có thể không render được dù lỗi đã được phát hiện đúng.

Không nên redirect khi muốn giữ BindingResult mặc định vì redirect tạo request mới và trạng thái lỗi không tự tồn tại. Nếu cần redirect sau lỗi, phải thiết kế cơ chế lưu lỗi và dữ liệu form rõ ràng; cách này phức tạp hơn và có thể làm lộ dữ liệu nếu lưu không đúng.

### 7.2. Không đưa nguyên exception vào View

Một Presentation Model có thể chứa `formError` hoặc danh sách `FieldMessage`:

~~~java
public record FieldMessage(
    String field,
    String message
) {}

public record FormFeedback(
    List<FieldMessage> fieldErrors,
    String formError
) {}
~~~

Controller chuyển exception nghiệp vụ đã biết thành thông điệp an toàn. Không đưa exception message thô, SQL hoặc stack trace vào template. Nếu cần trace ID để hỗ trợ, hiển thị mã tham chiếu ngắn và ghi chi tiết trong log nội bộ.

## 8. Tách dữ liệu form khỏi dữ liệu hiển thị trong trang chỉnh sửa

Một trang chỉnh sửa thường cần cả dữ liệu ban đầu để nhập và dữ liệu trình bày bổ sung:

~~~java
public record EditTaskForm(
    @NotBlank @Size(max = 120) String title,
    LocalDate dueDate,
    @NotNull UUID categoryId,
    long version
) {}

public record EditTaskPageModel(
    String heading,
    String statusLabel,
    List<CategoryOption> categories,
    String createdAtText,
    boolean showDeleteAction
) {}
~~~

Form chứa các trường được phép thay đổi. `version` có thể được dùng như optimistic concurrency token nếu ứng dụng muốn phát hiện form cũ; nó không phải quyền truy cập và server phải kiểm tra version khi cập nhật.

Page Model chứa trạng thái chỉ đọc như nhãn trạng thái và thời điểm tạo. Không đặt createdAt vào form rồi cho phép client sửa nó. Nếu một trường không được phép thay đổi, nó không nên xuất hiện như một giá trị ghi trong hợp đồng đầu vào.

### 8.1. Khởi tạo Form Model từ dữ liệu hiện có

GET edit có thể tải query result rồi ánh xạ thành hai object:

~~~java
@GetMapping("/{id}/edit")
String editForm(
    @PathVariable UUID id,
    @AuthenticationPrincipal AppPrincipal principal,
    Locale locale,
    Model model
) {
    EditTaskQueryResult result =
        taskQueryService.getEditableTask(id, principal.userId());

    model.addAttribute(
        "form",
        new EditTaskForm(
            result.title(),
            result.dueDate(),
            result.categoryId(),
            result.version()
        )
    );

    model.addAttribute(
        "page",
        editTaskPageFactory.create(result, principal.userId(), locale)
    );

    return "tasks/edit";
}
~~~

Query service phải xác minh tài nguyên thuộc phạm vi người dùng được phép truy cập. Không tải một entity bất kỳ rồi dựa vào việc View ẩn nút để bảo vệ dữ liệu.

POST update nhận Form Model, kiểm tra validation và chuyển thành UpdateTaskCommand. Application service kiểm tra quyền, version và trạng thái trước khi lưu.

## 9. Form Model và API Request DTO

Form HTML và API JSON có thể dùng cùng use case nhưng không nhất thiết phải dùng chung request class.

Ví dụ:
- Form dùng chuỗi ngày theo định dạng HTML date input.
- API có thể dùng ISO-8601 hoặc một kiểu ngày giờ có timezone.
- Form có thể gửi categoryId dưới dạng chuỗi.
- API có thể có metadata, idempotency key hoặc cấu trúc lồng nhau.
- Form cần giữ giá trị nhập và thông báo theo trường.
- API cần error code ổn định cho client.

Nếu hai hợp đồng khác nhau, tạo Form Model và API Request DTO riêng rồi ánh xạ về cùng Application Command. Nếu hợp đồng thực sự giống nhau, dùng chung type có thể giảm trùng lặp; không cần tách class chỉ vì tên gọi khác.

### 9.1. Không trả Form Model làm response mặc định

Form Model được thiết kế để nhận input. Nó có thể chứa các trường không phù hợp để công khai trong response, hoặc thiếu dữ liệu cần cho UI. Response DTO nên được thiết kế theo nhu cầu client và không vô tình phản chiếu toàn bộ cấu trúc request.

Tương tự, không trả Domain Entity thẳng ra JSON chỉ vì serializer có thể đọc được các thuộc tính của nó. Response contract nên ổn định và chỉ chứa trường được phép công khai.

## 10. Bảo mật khi binding và mapping

Tách dữ liệu giúp giảm rủi ro nhưng không tự động bảo đảm an toàn. Cần kiểm soát các điểm sau:

- Chỉ khai báo trong Form Model những trường người dùng được phép gửi.
- Không lấy ownerId, role, tenantId hoặc trạng thái tin cậy từ form.
- Lấy danh tính từ security principal đã xác thực.
- Kiểm tra quyền trên từng tài nguyên trong use case.
- Giới hạn danh sách option theo owner/tenant.
- Xác minh ID tham chiếu như categoryId có thuộc phạm vi được phép.
- Không serialize trường nội bộ hoặc dữ liệu nhạy cảm vào ViewModel/Response DTO.
- Dùng CSRF protection cho form dựa trên cookie session.
- Dùng output encoding khi render dữ liệu do người dùng nhập.

Một Form Model chỉ có `categoryId` không chứng minh người dùng có quyền chọn danh mục đó. Server phải tải hoặc kiểm tra danh mục trong phạm vi quyền tương ứng.

### 10.1. Mapping không phải validation

Đoạn mapping:

~~~java
new CreateTaskCommand(
    form.title(),
    form.dueDate(),
    form.categoryId(),
    principal.userId()
)
~~~

chỉ chuyển dữ liệu giữa các hợp đồng. Nó không chứng minh categoryId hợp lệ, user có quyền hoặc title thỏa mọi quy tắc nghiệp vụ. Các kiểm tra cần được đặt ở tầng có thẩm quyền.

### 10.2. Không dùng hidden field làm nguồn tin cậy

Một trường hidden vẫn là dữ liệu client gửi lên. Có thể dùng hidden field cho ID hoặc version như một phần của hợp đồng, nhưng server phải xác minh giá trị và quyền. Không dùng hidden field để tin ownerId, role, price hoặc trạng thái đã được server quyết định.

## 11. Vòng đời dữ liệu và Post/Redirect/Get

Form Model thường sống trong một request. Khi validation thất bại và server render lại cùng response, nó giữ giá trị và BindingResult cho request đó. Khi submit thành công, Post/Redirect/Get tạo một GET mới để hiển thị dữ liệu đã lưu.

~~~mermaid
sequenceDiagram
    actor User
    participant View
    participant Controller
    participant UseCase
    User->>View: Mở form
    View->>Controller: GET /tasks/new
    Controller-->>View: Form Model rỗng + Page Model
    User->>View: Nhập và submit
    View->>Controller: POST /tasks
    Controller->>Controller: Bind + validate
    alt Có lỗi
        Controller-->>View: Form Model đã nhập + BindingResult + Page Model
        View-->>User: Render lại form và lỗi
    else Hợp lệ
        Controller->>UseCase: Application Command
        UseCase-->>Controller: Kết quả tạo
        Controller-->>View: Redirect
        View->>Controller: GET /tasks/{id}
        Controller-->>View: Presentation Model mới
        View-->>User: Trang chi tiết
    end
~~~

Không lưu một Form Model mutable trong field của Controller singleton hoặc biến dùng chung giữa người dùng. Controller có thể xử lý nhiều request đồng thời; dữ liệu form phải có phạm vi request hoặc được lưu trong một store có khóa người dùng/session và chính sách bảo mật rõ.

Flash attribute có thể mang thông báo ngắn sau redirect. Nó không thay thế database hoặc application state và không phù hợp để lưu toàn bộ dữ liệu nghiệp vụ dài hạn.

## 12. Tổ chức mapping ở đâu?

Mapping có thể được đặt ở Controller, factory/assembler hoặc application layer tùy chiều dữ liệu và trách nhiệm:

| Mapping | Vị trí thường phù hợp |
|---|---|
| Form Model → Application Command | Controller hoặc request mapper trong presentation |
| Domain Entity → Application Result/Query DTO | Application/query service hoặc repository projection |
| Query DTO → Presentation Model | Presenter, factory hoặc assembler trong presentation |
| Domain Entity → Persistence Entity | Infrastructure mapper nếu tách domain khỏi ORM |
| Application Result → API Response DTO | API adapter/presenter |

Không nên tạo một mapper tổng quát biết mọi tầng và mọi loại object. Mapping nên rõ ràng theo use case hoặc màn hình để người đọc biết dữ liệu nào được phép đi qua ranh giới.

Với mapping đơn giản vài trường, viết trực tiếp trong Controller có thể dễ hiểu. Khi mapping lặp lại, có nhiều quy tắc format hoặc nhiều màn hình dùng chung, factory/assembler riêng sẽ có giá trị.

## 13. Kiểm thử hai hợp đồng độc lập

Tách Form Model và Presentation Model tạo ra các điểm kiểm thử nhỏ, rõ ràng:

| Phạm vi | Điều cần xác minh |
|---|---|
| Form Model | Binding, validation, trường được phép nhận |
| Form → Command mapper | Chuyển đúng giá trị và bổ sung principal/tenant từ server |
| Application service | Quyền, quy tắc nghiệp vụ, transaction |
| Presentation factory | Nhãn, định dạng, option, derived state |
| Controller MVC test | Request sai trả form cùng lỗi; request hợp lệ gọi use case và redirect |
| View test | Template đọc đúng thuộc tính từ Form Model và Page Model |
| Security integration | Client không thể giả owner, role hoặc truy cập dữ liệu ngoài phạm vi |

Ví dụ kiểm thử Form Model:

~~~java
class CreateTaskFormTest {
    private final Validator validator =
        Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void rejectsBlankTitle() {
        CreateTaskForm form =
            new CreateTaskForm(" ", LocalDate.now(), UUID.randomUUID());

        Set<ConstraintViolation<CreateTaskForm>> violations =
            validator.validate(form);

        assertThat(violations)
            .extracting(ConstraintViolation::getPropertyPath)
            .extracting(Object::toString)
            .contains("title");
    }
}
~~~

Ví dụ kiểm thử Presentation Factory:

~~~java
@Test
void createsPageModelWithAvailableCategories() {
    Locale locale = Locale.forLanguageTag("vi-VN");
    given(categoryQueryService.findAvailableFor(ownerId))
        .willReturn(List.of(category));
    given(messages.getMessage("task.create.heading", null, locale))
        .willReturn("Tạo công việc");
    given(messages.getMessage("task.create.due-date-hint", null, locale))
        .willReturn("Để trống nếu chưa xác định ngày đến hạn");
    given(messages.getMessage("task.create.submit", null, locale))
        .willReturn("Tạo công việc");

    CreateTaskPageModel page =
        factory.create(ownerId, locale);

    assertThat(page.heading()).isEqualTo("Tạo công việc");
    assertThat(page.categories())
        .extracting(CategoryOption::id)
        .containsExactly(category.id());
}
~~~

Ví dụ MVC test cho validation nên xác minh:
- POST với title rỗng trả lại template tạo mới.
- BindingResult có lỗi tại title.
- Page Model vẫn có danh sách category.
- Use case không được gọi.
- Dữ liệu người dùng nhập ở các trường hợp lệ vẫn được giữ.

Ví dụ request hợp lệ nên xác minh command nhận ownerId từ principal, không phải từ dữ liệu form. Test bảo mật nên gửi thêm trường giả như ownerId hoặc status và chứng minh chúng không thể ghi đè dữ liệu server quản lý.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng JPA Entity làm Form Model | Client có thể bind trường nội bộ; form phụ thuộc persistence | Dùng Form/Input DTO giới hạn trường |
| Dùng cùng object cho input và output dù hợp đồng khác nhau | Trộn dữ liệu ghi với dữ liệu hiển thị | Tách Form Model và Presentation Model |
| Đưa danh sách option vào Form Model | Hợp đồng đầu vào chứa dữ liệu server chỉ cung cấp | Đặt option trong Page/ViewModel |
| Đưa ownerId hoặc role vào form | Có nguy cơ mass assignment/giả mạo quyền | Lấy từ principal và kiểm tra ở server |
| Nghĩ validation form bảo vệ mọi quy tắc | Các nguồn gọi khác có thể bỏ qua form | Bảo vệ bất biến trong domain/application |
| Presentation Model truy cập repository | Logic trình bày phụ thuộc persistence | Dùng query service/factory |
| View tự định dạng và suy ra nhiều trạng thái | Template phình to, khó kiểm thử | Chuẩn bị Presentation Model |
| Redirect khi validation lỗi mà không lưu state | Mất dữ liệu nhập và lỗi | Render lại form hoặc thiết kế state transfer rõ |
| Lưu Form Model mutable trong Controller singleton | Request đồng thời có thể ghi đè dữ liệu nhau | Giữ state theo request |
| Tách quá nhiều DTO không có khác biệt | Boilerplate và mapping không cần thiết | Chỉ tách khi hợp đồng/vòng đời/trách nhiệm khác nhau |

## 15. Quy trình refactor một màn hình đang dùng chung Model

Không cần viết lại toàn bộ ứng dụng để áp dụng cách tách này. Có thể refactor từng màn hình:

1. Liệt kê các trường client thực sự được phép sửa.
2. Tạo Form Model/Input DTO chỉ chứa những trường đó.
3. Loại owner, role, status nội bộ và timestamp khỏi hợp đồng đầu vào.
4. Tạo Presentation Model cho option, nhãn, dữ liệu phụ và trạng thái hiển thị.
5. Chuyển logic format hoặc điều kiện lặp lại ra khỏi template.
6. Ánh xạ Form Model thành Application Command sau binding/validation.
7. Lấy danh tính và tenant từ principal hoặc context tin cậy.
8. Giữ quy tắc nghiệp vụ và authorization trong application/domain.
9. Kiểm tra lại POST validation để giữ form và dữ liệu phụ.
10. Bổ sung test binding, mapping, ViewModel và quyền truy cập.
11. Xóa các thuộc tính entity hoặc logic template không còn cần thiết sau khi đã xác minh mọi caller.

Nếu một màn hình chỉ có một trường nhập và không có dữ liệu trình bày bổ sung, việc tạo hai class có thể chưa mang lại lợi ích. Hãy tách khi có sự khác nhau thực sự về quyền ghi, nguồn dữ liệu, định dạng hoặc vòng đời.

## 16. Những điểm cần ghi nhớ

Form Model và Presentation Model phục vụ hai chiều khác nhau. Form Model mô tả dữ liệu client được phép gửi; Presentation Model mô tả dữ liệu View cần để hiển thị. Application Command diễn đạt use case sau khi server bổ sung ngữ cảnh tin cậy; Domain Model bảo vệ trạng thái và quy tắc nghiệp vụ.

Không bind trực tiếp Domain/JPA Entity vào form, không đưa owner hoặc role từ client vào command như dữ liệu đáng tin, và không coi cờ hiển thị là authorization. Khi validation thất bại, giữ Form Model cùng lỗi và tạo lại dữ liệu phụ của trang. Khi thành công, chuyển form thành command, gọi use case rồi dùng redirect hoặc response DTO phù hợp.

Tách hai hợp đồng giúp View không phụ thuộc vào cấu trúc lưu trữ, form không vô tình mở rộng quyền ghi và logic trình bày có thể được kiểm thử độc lập. Hãy tạo đúng số object cần thiết cho khác biệt thực tế của màn hình; mục tiêu là ranh giới rõ, không phải số lượng class nhiều hơn.
