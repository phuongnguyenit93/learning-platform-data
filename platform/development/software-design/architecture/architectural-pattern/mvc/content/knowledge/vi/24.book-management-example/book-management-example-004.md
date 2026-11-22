# Thiết kế Controller và các hành động

Trong ví dụ quản lý sách của module **MODEL_VIEW_CONTROLLER**, Controller là điểm tiếp nhận các tương tác từ người dùng và điều phối chúng đến chức năng ứng dụng phù hợp. Một Controller tốt giúp luồng từ request đến kết quả có thể đọc, kiểm thử và bảo trì: nhận dữ liệu, kiểm tra hợp lệ ở mức giao thức, gọi use case, rồi chọn View hoặc response. Controller không nên trở thành nơi chứa toàn bộ quy tắc quản lý sách, truy vấn database và xử lý giao diện.

Bài học thuộc chương **Minh họa quản lý sách**. Ta sẽ thiết kế các hành động phổ biến như xem danh sách, tìm kiếm, xem chi tiết, tạo, sửa, xóa và thay đổi trạng thái sách. Qua đó, bài học làm rõ cách đặt route, tổ chức method của Controller, binding và validation form, chuyển hướng sau khi ghi dữ liệu, xử lý lỗi, bảo mật, phân quyền, kiểm soát cập nhật đồng thời và kiểm thử các luồng MVC bằng Java Spring MVC.

## 1. Bài toán quản lý sách

Giả sử ứng dụng quản lý một thư viện có các chức năng:

- Xem danh sách sách và phân trang.
- Tìm kiếm theo tiêu đề, ISBN, tác giả hoặc danh mục.
- Xem thông tin chi tiết một cuốn sách.
- Tạo sách mới.
- Sửa thông tin sách.
- Xóa hoặc lưu trữ sách.
- Đánh dấu sách đã xuất bản hoặc ngừng lưu hành.
- Quản lý trạng thái sẵn sàng cho mượn.

Mỗi chức năng bắt đầu từ một tương tác, nhưng không phải mọi tương tác đều có cùng ý nghĩa. Xem danh sách là thao tác đọc; tạo và sửa là thao tác thay đổi trạng thái; xóa hoặc chuyển trạng thái có thể cần quyền cao hơn và quy tắc nghiệp vụ riêng.

Controller đóng vai trò điều phối những hành động này. Nó nhận request HTTP, chuyển dữ liệu sang kiểu phù hợp, gọi application service hoặc use case, rồi trả về View, redirect hoặc response. Quy tắc như ISBN có được trùng không, sách đang được mượn có được xóa không, hoặc người dùng nào được sửa sách phải được thực thi ở application/domain layer và các lớp bảo mật phía server.

### 1.1. Luồng tổng quát

~~~mermaid
flowchart TD
    U["Người dùng"] --> V["View: danh sách / form / chi tiết"]
    V -->|"HTTP request"| C["BookController"]
    C --> B["Binding và validation"]
    B --> A["Application service / use case"]
    A --> D["Domain rules"]
    A --> R["Repository"]
    R --> DB[("Database")]
    DB --> R
    R --> A
    A --> C
    C -->|"ViewModel hoặc redirect"| V
~~~

Sơ đồ mô tả luồng điển hình của ứng dụng server-rendered MVC. Controller là adapter web. Application service điều phối hành động; domain model bảo vệ quy tắc; repository chịu trách nhiệm truy cập dữ liệu; View chỉ trình bày kết quả được cung cấp.

## 2. Xác định trách nhiệm trước khi viết Controller

Một Controller thường đảm nhiệm những việc sau:

1. Nhận request và các tham số route/query/form.
2. Binding dữ liệu HTTP thành request object.
3. Kiểm tra validation ở mức đầu vào.
4. Gọi đúng use case hoặc application service.
5. Chuyển kết quả thành dữ liệu cho View hoặc response.
6. Chọn trang, redirect hoặc HTTP status phù hợp.
7. Chuyển lỗi ở ranh giới web thành phản hồi dễ hiểu.

Controller không nên:

- Viết SQL hoặc tự thao tác EntityManager.
- Chứa quy tắc nghiệp vụ dài như quyết định trạng thái xuất bản.
- Tự kiểm tra quyền bằng cách chỉ ẩn nút trên giao diện.
- Nhận trực tiếp JPA entity làm form input.
- Trả entity persistence ra JSON không kiểm soát.
- Tự định nghĩa lại cùng một quy tắc ở nhiều endpoint.
- Giữ trạng thái nghiệp vụ trong field của Controller giữa các request.

Controller của Spring thường là singleton bean. Không đặt dữ liệu riêng của một request vào field mutable của Controller vì nhiều request có thể chạy đồng thời.

### 2.1. Phân biệt action, endpoint và use case

Ba khái niệm có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Endpoint/route | Địa chỉ và HTTP method nhận request | GET /books/42 |
| Controller action | Method nhận request và điều phối | BookController.detail(...) |
| Use case | Hành động ứng dụng có ý nghĩa nghiệp vụ | GetBookDetails, UpdateBook |

Một use case có thể được gọi từ nhiều adapter như MVC Controller, REST Controller hoặc message consumer. Controller action là phần chuyển giao thức HTTP thành lời gọi use case.

## 3. Thiết kế route cho các hành động quản lý sách

Route nên diễn đạt tài nguyên và hành động theo cách nhất quán. Với ứng dụng web dùng form HTML, có thể dùng bảng sau:

| HTTP method | Route | Controller action | Mục đích |
|---|---|---|---|
| GET | /books | list | Xem và tìm kiếm danh sách |
| GET | /books/{id} | detail | Xem chi tiết |
| GET | /books/new | createForm | Hiển thị form tạo |
| POST | /books | create | Tạo sách |
| GET | /books/{id}/edit | editForm | Hiển thị form sửa |
| POST | /books/{id} | update | Cập nhật sách từ form |
| POST | /books/{id}/delete | delete | Yêu cầu xóa sách |
| POST | /books/{id}/publication | changePublication | Thay đổi trạng thái xuất bản |

Với REST API, cập nhật thường dùng PUT hoặc PATCH và xóa dùng DELETE. Form HTML tiêu chuẩn chỉ gửi GET hoặc POST; một ứng dụng có thể dùng POST cho form cập nhật/xóa, hoặc cấu hình hidden method filter để hỗ trợ PUT/DELETE. Dù chọn cách nào, route cần nhất quán và không dùng GET cho hành động thay đổi trạng thái.

### 3.1. GET phải an toàn

GET được dùng để đọc dữ liệu và không nên tạo tác dụng phụ nghiệp vụ. Ví dụ:

- GET /books hiển thị danh sách.
- GET /books/42 hiển thị chi tiết.
- GET /books/42/delete không được thực sự xóa sách.

Nếu xóa bằng GET, trình duyệt, crawler, prefetch hoặc một liên kết bị mở ngoài ý muốn có thể kích hoạt thao tác phá hủy dữ liệu. Xóa cần một request thay đổi trạng thái, thường là POST trong form HTML hoặc DELETE trong API.

### 3.2. Route nên ổn định và dễ hiểu

Dùng danh từ số nhiều cho collection và ID cho tài nguyên cụ thể. Tránh tạo route chỉ dựa trên tên method Java hoặc nhồi nhiều tham số vào path nếu chúng thực chất là bộ lọc.

Các bộ lọc danh sách thường nằm trong query string:

~~~text
/books?keyword=java&category=programming&page=0&size=20&sort=title
~~~

Query string giúp bookmark, chia sẻ và khôi phục trạng thái tìm kiếm. Khi bộ lọc thay đổi, nên đưa page về trang đầu để tránh trang hiện tại vượt quá phạm vi kết quả mới.

## 4. Thiết kế hợp đồng request và ViewModel

Không bind trực tiếp entity vào form. Mỗi request nên chỉ chứa dữ liệu client được phép gửi.

### 4.1. Form tìm kiếm

~~~java
public record BookSearchForm(
    @Size(max = 100)
    String keyword,

    String category,

    @Min(0)
    Integer page,

    @Min(1)
    @Max(100)
    Integer size
) {}
~~~

Các giá trị page và size cần có default ở Controller hoặc một request mapper. Server phải giới hạn size tối đa để tránh request yêu cầu quá nhiều dữ liệu.

### 4.2. Form tạo sách

~~~java
public record CreateBookForm(
    @NotBlank
    @Size(max = 160)
    String title,

    @NotBlank
    @Size(max = 20)
    String isbn,

    @NotNull
    UUID authorId,

    @NotNull
    UUID categoryId,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price,

    @NotBlank
    @Pattern(regexp = "[A-Z]{3}")
    @Size(max = 3)
    String currencyCode,

    @Size(max = 4000)
    String description
) {}
~~~

Form chỉ nhận các giá trị người dùng được phép cung cấp. ID tenant, ngày tạo, người tạo, trạng thái kiểm duyệt và số bản sao thực tế có thể do server hoặc use case quyết định.

### 4.3. Form cập nhật sách

~~~java
public record UpdateBookForm(
    @NotBlank
    @Size(max = 160)
    String title,

    @NotBlank
    @Size(max = 20)
    String isbn,

    @NotNull
    UUID authorId,

    @NotNull
    UUID categoryId,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price,

    @NotBlank
    @Pattern(regexp = "[A-Z]{3}")
    String currencyCode,

    @Size(max = 4000)
    String description,

    @NotNull
    Long version
) {}
~~~

Trường version dùng cho optimistic locking. Nếu hệ thống chưa cần kiểm soát cập nhật đồng thời, có thể chưa đưa trường này vào form; khi thêm cần giữ nó trong hợp đồng và kiểm tra stale update ở server.

### 4.4. ViewModel không phải request object

Dữ liệu cho trang chi tiết có thể khác form cập nhật:

~~~java
public record BookDetailViewModel(
    UUID id,
    String title,
    String isbn,
    String authorName,
    String categoryName,
    String formattedPrice,
    String publicationStatus,
    boolean canEdit,
    boolean canDelete
) {}
~~~

ViewModel có thể chứa chuỗi đã định dạng và các cờ phục vụ hiển thị. Các cờ canEdit/canDelete chỉ giúp View hiển thị đúng thao tác; use case vẫn phải kiểm tra quyền khi request thực sự được gửi.

## 5. Controller action đọc dữ liệu

Các action đọc thường đơn giản hơn action ghi. Controller nhận tham số, gọi query service và đưa kết quả vào Model.

### 5.1. Danh sách và tìm kiếm

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final BookQueryService bookQueries;
    private final BookCommandService bookCommands;

    public BookController(
        BookQueryService bookQueries,
        BookCommandService bookCommands
    ) {
        this.bookQueries = bookQueries;
        this.bookCommands = bookCommands;
    }

    @GetMapping
    public String list(
        @Valid @ModelAttribute("search") BookSearchForm search,
        BindingResult errors,
        Model model
    ) {
        if (errors.hasErrors()) {
            return "books/invalid-search";
        }

        int page = search.page() == null ? 0 : search.page();
        int size = search.size() == null ? 20 : search.size();

        var result = bookQueries.search(
            search.keyword(),
            search.category(),
            page,
            Math.min(size, 100)
        );

        model.addAttribute("result", result);
        return "books/list";
    }
}
~~~

Trong Spring MVC, BindingResult phải đứng ngay sau tham số được validate. Nếu đặt một tham số khác xen giữa, lỗi binding/validation có thể được xử lý theo cách không mong muốn.

Controller giới hạn size như một lớp bảo vệ bổ sung. Trong hệ thống thực tế, request mapper hoặc service cần từ chối giá trị ngoài hợp đồng rõ ràng thay vì chỉ âm thầm sửa mọi input.

### 5.2. Xem chi tiết

~~~java
@GetMapping("/{id}")
public String detail(
    @PathVariable UUID id,
    Model model
) {
    BookDetailViewModel book = bookQueries.getDetail(id);
    model.addAttribute("book", book);
    return "books/detail";
}
~~~

Query service có thể trả projection/ViewModel đã chuẩn bị sẵn. Controller không cần tải entity rồi tự duyệt quan hệ tác giả, danh mục hoặc bản sao. Điều này giúp tránh lazy loading và giữ hợp đồng View rõ ràng.

Nếu không tìm thấy sách, query service có thể ném lỗi BookNotFoundException. Exception handler ở ranh giới web sẽ chuyển lỗi đó thành trang 404 hoặc response tương ứng.

## 6. Action hiển thị form tạo và sửa

Hiển thị form là request GET. Nó không ghi dữ liệu. Controller có thể chuẩn bị danh sách tác giả, danh mục hoặc các lựa chọn khác cho View.

### 6.1. Form tạo

~~~java
@GetMapping("/new")
public String createForm(Model model) {
    model.addAttribute("form", new CreateBookForm(
        null, null, null, null, null, "VND", null
    ));
    model.addAttribute("authors", bookQueries.listAuthors());
    model.addAttribute("categories", bookQueries.listCategories());
    return "books/create";
}
~~~

Ví dụ khởi tạo record với null cần khớp constructor và chính sách validation của dự án. Có thể dùng factory hoặc form class mutable có constructor mặc định nếu template engine cần binding theo cách đó.

### 6.2. Form sửa

~~~java
@GetMapping("/{id}/edit")
public String editForm(
    @PathVariable UUID id,
    Model model
) {
    UpdateBookForm form = bookQueries.getEditForm(id);
    model.addAttribute("form", form);
    model.addAttribute("authors", bookQueries.listAuthors());
    model.addAttribute("categories", bookQueries.listCategories());
    return "books/edit";
}
~~~

Query service cần kiểm tra người dùng có quyền xem form sửa và tài nguyên thuộc phạm vi dữ liệu được phép. Không dựa vào việc link sửa chỉ xuất hiện với admin ở trang chi tiết.

## 7. Action tạo sách

Action POST tạo sách nhận form, validation, chuyển sang command và gọi use case. Khi thành công, Controller thường redirect sang trang chi tiết.

~~~java
@PostMapping
public String create(
    @Valid @ModelAttribute("form") CreateBookForm form,
    BindingResult errors,
    Model model,
    RedirectAttributes redirect
) {
    if (errors.hasErrors()) {
        model.addAttribute("authors", bookQueries.listAuthors());
        model.addAttribute("categories", bookQueries.listCategories());
        return "books/create";
    }

    UUID id = bookCommands.create(
        new CreateBookCommand(
            form.title(),
            form.isbn(),
            form.authorId(),
            form.categoryId(),
            form.price(),
            form.currencyCode(),
            form.description()
        )
    );

    redirect.addFlashAttribute("message", "Đã tạo sách.");
    return "redirect:/books/" + id;
}
~~~

Controller không tự kiểm tra ISBN có tồn tại hay không bằng cách gọi repository trực tiếp. Command service/domain sẽ kiểm tra quy tắc nghiệp vụ như ISBN duy nhất, tác giả hợp lệ và giá không âm.

### 7.1. Validation có hai lớp

Validation đầu vào và quy tắc nghiệp vụ không hoàn toàn giống nhau:

| Loại | Ví dụ | Vị trí thường phù hợp |
|---|---|---|
| Validation cấu trúc | Tiêu đề không rỗng, ISBN đúng độ dài | Request DTO / Bean Validation |
| Validation nghiệp vụ | ISBN chưa được dùng, tác giả còn hoạt động | Application/domain service |
| Authorization | Người dùng được phép tạo sách trong thư viện này | Security/application layer |
| Constraint dữ liệu | ISBN unique trong database | Database constraint + xử lý lỗi |

Một request có thể vượt qua @Valid nhưng vẫn thất bại vì ISBN trùng hoặc tác giả đã bị khóa. Controller cần xử lý lỗi use case để hiển thị thông báo phù hợp.

## 8. Action cập nhật sách

Action cập nhật nhận ID từ route và các trường được phép sửa từ form. Không tin ID hoặc tenant do form gửi nếu server có thể xác định từ path và security context.

~~~java
@PostMapping("/{id}")
public String update(
    @PathVariable UUID id,
    @Valid @ModelAttribute("form") UpdateBookForm form,
    BindingResult errors,
    Model model,
    RedirectAttributes redirect
) {
    if (errors.hasErrors()) {
        model.addAttribute("authors", bookQueries.listAuthors());
        model.addAttribute("categories", bookQueries.listCategories());
        return "books/edit";
    }

    bookCommands.update(
        new UpdateBookCommand(
            id,
            form.title(),
            form.isbn(),
            form.authorId(),
            form.categoryId(),
            form.price(),
            form.currencyCode(),
            form.description(),
            form.version()
        )
    );

    redirect.addFlashAttribute("message", "Đã cập nhật sách.");
    return "redirect:/books/" + id;
}
~~~

Use case tải sách hiện có, kiểm tra quyền và cập nhật qua hành vi nghiệp vụ. Không tạo một entity mới chỉ từ form rồi save đè lên entity cũ vì cách đó có thể bỏ qua field nội bộ, quan hệ hoặc quy tắc chuyển trạng thái.

### 8.1. Cập nhật đồng thời

Giả sử hai thủ thư cùng mở form sửa một cuốn sách. Người thứ hai lưu sau khi người thứ nhất đã cập nhật. Nếu không có concurrency control, dữ liệu mới hơn có thể bị ghi đè âm thầm.

JPA hỗ trợ optimistic locking bằng @Version:

~~~java
@Entity
public class BookEntity {
    @Id
    private UUID id;

    @Version
    private Long version;

    private String title;
}
~~~

Annotation @Version bảo vệ cuộc đua ghi xảy ra sau khi entity được tải trong transaction hiện tại. Với form đã mở từ trước, use case còn phải so sánh version gửi lên với version hiện tại trước khi áp dụng thay đổi:

~~~java
BookEntity book = repository.findById(command.bookId())
    .orElseThrow(BookNotFoundException::new);

if (!Objects.equals(command.version(), book.getVersion())) {
    throw new StaleBookUpdateException();
}

Author author = authorRepository.getActive(command.authorId());
Category category = categoryRepository.getActive(command.categoryId());

book.updateDetails(
    command.title(),
    command.isbn(),
    author,
    category,
    new Money(command.price(), command.currencyCode()),
    command.description()
);
~~~

Sau bước so sánh này, @Version tiếp tục bảo vệ trường hợp một transaction khác cập nhật bản ghi trước khi transaction hiện tại flush. Ứng dụng nên ánh xạ cả hai tình huống stale update thành thông báo yêu cầu người dùng tải lại dữ liệu. Version do server/database quản lý; giá trị gửi từ form chỉ là mốc để phát hiện form đã cũ, không phải giá trị được phép ghi trực tiếp.

## 9. Action xóa và thay đổi trạng thái

Xóa là thao tác có tác động lớn. Hệ thống cần xác định xóa cứng hay soft delete, điều kiện xóa và quyền thực hiện.

### 9.1. Xác nhận xóa bằng GET, thực hiện bằng POST

GET có thể hiển thị trang xác nhận:

~~~java
@GetMapping("/{id}/delete")
public String confirmDelete(@PathVariable UUID id, Model model) {
    model.addAttribute("book", bookQueries.getDeleteSummary(id));
    return "books/confirm-delete";
}
~~~

POST mới thực hiện thao tác:

~~~java
@PostMapping("/{id}/delete")
public String delete(
    @PathVariable UUID id,
    RedirectAttributes redirect
) {
    bookCommands.delete(id);
    redirect.addFlashAttribute("message", "Đã xóa sách.");
    return "redirect:/books";
}
~~~

Trong form HTML, cần có CSRF token khi Spring Security được cấu hình CSRF protection. Không tắt CSRF chỉ để form hoạt động. Việc kiểm tra quyền xóa phải diễn ra trong use case hoặc security policy phía server.

### 9.2. Xóa cứng hay lưu trữ?

Một cuốn sách có thể đã xuất hiện trong lịch sử mượn hoặc giao dịch. Xóa cứng có thể phá vỡ tham chiếu và audit trail. Nhiều hệ thống chọn trạng thái archived hoặc deletedAt để ẩn sách khỏi danh sách đang hoạt động mà vẫn giữ lịch sử.

Quy tắc xóa có thể là:

- Không xóa nếu sách đang được mượn.
- Không xóa nếu còn bản sao đang lưu thông.
- Chỉ quản trị viên mới được xóa.
- Cho phép lưu trữ thay vì xóa cứng.
- Ghi audit event cho thao tác thay đổi.

Những quyết định này thuộc nghiệp vụ, không nên chỉ được viết trong Controller.

### 9.3. Thay đổi trạng thái là use case riêng

Không nên cho form cập nhật tổng quát nhận một field status rồi để client chuyển bất kỳ trạng thái nào. Các chuyển trạng thái quan trọng có thể cần hành động riêng:

~~~java
@PostMapping("/{id}/publication")
public String changePublication(
    @PathVariable UUID id,
    @RequestParam PublicationAction action,
    RedirectAttributes redirect
) {
    bookCommands.changePublication(id, action);
    redirect.addFlashAttribute("message", "Đã cập nhật trạng thái xuất bản.");
    return "redirect:/books/" + id;
}
~~~

Use case kiểm tra transition hợp lệ. Ví dụ, sách đang chờ duyệt có thể được xuất bản hoặc từ chối; sách đã lưu trữ có thể không được xuất bản lại nếu thiếu quy trình phục hồi. Không cho client tự đặt một trạng thái tùy ý.

## 10. Post/Redirect/Get và giữ trạng thái form

Sau khi POST tạo hoặc cập nhật thành công, nên dùng **Post/Redirect/Get (PRG)**:

1. Trình duyệt gửi POST.
2. Server xử lý và lưu dữ liệu.
3. Server trả redirect.
4. Trình duyệt gửi GET đến trang kết quả.

Điều này tránh việc refresh trang kết quả gửi lại POST theo cách thông thường và giúp URL sau cùng có thể bookmark.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Controller as Controller
    participant Service as Command Service
    participant DB as Database

    User->>Browser: Submit form tạo sách
    Browser->>Controller: POST /books
    Controller->>Service: create(command)
    Service->>DB: INSERT
    DB-->>Service: ID sách
    Service-->>Controller: ID sách
    Controller-->>Browser: 303 Redirect /books/{id}
    Browser->>Controller: GET /books/{id}
    Controller-->>Browser: 200 HTML chi tiết
~~~

Spring có thể tạo redirect qua chuỗi return "redirect:/books/" + id. Với redirect sau POST, cần xác định status và hành vi flash attribute theo framework/configuration. Flash attribute giúp hiển thị thông báo một lần ở request GET kế tiếp.

### 10.1. PRG không thay thế idempotency

PRG giảm việc gửi lại form khi refresh trang sau khi redirect, nhưng không bảo đảm request chỉ được xử lý một lần. Người dùng có thể nhấn nút nhiều lần, trình duyệt gửi lại do mạng hoặc client retry.

Với thao tác tạo có nguy cơ trùng, dùng ràng buộc nghiệp vụ như ISBN unique, idempotency key hoặc cơ chế chống submit lặp phù hợp. Database unique constraint vẫn là lớp bảo vệ cuối cùng cho tính duy nhất.

### 10.2. Giữ dữ liệu khi validation lỗi

Khi form không hợp lệ, trả lại cùng View và giữ dữ liệu người dùng đã nhập. Controller cần nạp lại danh sách tham chiếu như tác giả và danh mục; nếu thiếu, template có thể không render được hoặc làm mất lựa chọn.

Không redirect sau validation lỗi nếu dữ liệu lỗi và BindingResult cần được giữ lại, trừ khi ứng dụng có cơ chế lưu form state riêng.

## 11. Xử lý lỗi ở ranh giới Controller

Một Controller cần phân biệt các nhóm lỗi:

| Lỗi | Ví dụ | Phản hồi phù hợp |
|---|---|---|
| Binding/validation | Giá âm, tiêu đề rỗng | Hiển thị form và lỗi tại trường |
| Not found | ID sách không tồn tại | Trang 404 hoặc API 404 |
| Forbidden | Người dùng không có quyền sửa | 403 hoặc trang từ chối |
| Conflict | ISBN trùng, version đã cũ | 409 hoặc form thông báo xung đột |
| Business rule | Sách đang được mượn nên không thể xóa | Form/detail với thông báo rõ |
| Unexpected error | Database unavailable | Trang lỗi chung, log nội bộ |

### 11.1. ControllerAdvice cho lỗi web

~~~java
@ControllerAdvice
public class BookWebExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public String handleNotFound() {
        return "error/404";
    }

    @ExceptionHandler(BookConflictException.class)
    public String handleConflict(Model model) {
        model.addAttribute(
            "message",
            "Thông tin sách đã thay đổi hoặc xung đột với dữ liệu hiện tại."
        );
        return "error/conflict";
    }
}
~~~

Ví dụ rút gọn. Trong ứng dụng thật, handler cần phân biệt request HTML và REST API; không nên trả cùng một template cho endpoint JSON. Không đưa stack trace, SQL, tên bảng hoặc dữ liệu nhạy cảm vào thông báo cho người dùng.

### 11.2. Lỗi nghiệp vụ cần có mã hoặc loại rõ ràng

Không nên dùng một RuntimeException chung cho mọi trường hợp. Các lỗi như BookNotFound, DuplicateIsbn, BookCurrentlyBorrowed và StaleBookUpdate có ý nghĩa khác nhau và có thể ánh xạ sang UI khác nhau.

Thông báo người dùng nên được viết theo ngữ cảnh, còn log nội bộ ghi thông tin kỹ thuật cần thiết với correlation ID. Không đưa toàn bộ exception message từ database ra View.

## 12. Bảo mật và phân quyền cho từng action

Controller là ranh giới HTTP nhưng không phải lớp duy nhất bảo vệ ứng dụng. Mỗi use case phải xác minh quyền thực hiện thao tác trên tài nguyên cụ thể.

### 12.1. Authentication và authorization

- Authentication xác định người dùng là ai.
- Authorization xác định người dùng có được thực hiện hành động này trên tài nguyên này không.

Có thể dùng method security như @PreAuthorize ở application service hoặc security policy riêng. Dù kiểm tra ở đâu, phải kiểm tra phía server và áp dụng cho mọi adapter gọi use case.

Ví dụ:

~~~java
@PreAuthorize("hasAuthority('BOOK_EDIT')")
public void update(UpdateBookCommand command) {
    // Tải sách, kiểm tra tenant/ownership và cập nhật
}
~~~

Chỉ kiểm tra role chung có thể chưa đủ. Cần kiểm tra sách có thuộc thư viện/tenant mà người dùng được phép quản lý không.

### 12.2. CSRF cho form thay đổi trạng thái

Với session cookie authentication, form POST/PUT/DELETE cần CSRF protection. Spring Security thường tích hợp token vào form template. Không dùng GET cho create, update, delete hoặc đổi trạng thái.

CORS và CSRF là hai cơ chế khác nhau. CORS không thay thế CSRF protection cho ứng dụng dùng cookie.

### 12.3. Mass assignment

Không nhận BookEntity trực tiếp qua @ModelAttribute. Dùng request DTO allowlist để client chỉ có thể gửi field được phép. ID tenant, người tạo, trạng thái kiểm duyệt và version do server kiểm soát theo hợp đồng.

### 12.4. Kiểm tra quyền trên từng ID

Một người dùng có thể được phép xem một số sách nhưng không được sửa tất cả. Mỗi action phải kiểm tra quyền trên ID được truyền vào. Việc ẩn nút edit/delete trong View chỉ là trải nghiệm giao diện, không phải kiểm soát truy cập.

## 13. Phân trang, lọc và sắp xếp ở action danh sách

Action list thường nhận nhiều query parameter. Cần giới hạn và chuẩn hóa:

- Keyword có độ dài tối đa.
- Category chỉ nhận giá trị hỗ trợ.
- Page không âm.
- Size có default và maximum.
- Sort field dùng allowlist.
- Direction chỉ ASC hoặc DESC.

Không ghép trực tiếp sort parameter vào SQL. Sắp xếp và lọc phải được áp dụng ở query layer trước khi giới hạn trang. Với bảng lớn, cân nhắc offset hoặc keyset pagination theo cách người dùng điều hướng.

Controller không nên tự tải toàn bộ danh sách rồi filter/sort trong bộ nhớ. Query service/repository nên trả page hoặc slice với projection phù hợp.

## 14. Tách Controller theo phạm vi chức năng

Một Controller quá lớn có thể quản lý danh sách, import, xuất báo cáo, quản trị tác giả, kiểm duyệt, mượn trả và xóa. Khi đó, mỗi method có thể dùng nhiều dependency và khó kiểm thử.

Có thể tách theo nhóm hành động:

~~~text
books/
  web/
    BookPageController.java
    BookAdminController.java
    BookApiController.java
  application/
    query/
      SearchBooksService.java
      GetBookDetailService.java
    command/
      CreateBookService.java
      UpdateBookService.java
      DeleteBookService.java
      ChangePublicationService.java
  domain/
    Book.java
    ISBN.java
    PublicationStatus.java
  persistence/
    BookJpaRepository.java
    JpaBookQueryAdapter.java
~~~

Không cần tạo một Controller cho từng method. Tách khi nhóm hành động có quyền, luồng hoặc phụ thuộc khác nhau. Ví dụ, BookPageController phục vụ trang đọc/tìm kiếm, BookAdminController xử lý thao tác quản trị và BookApiController công bố hợp đồng JSON.

## 15. Kiểm thử Controller và hành động

Kiểm thử nên xác nhận cả phản hồi HTTP lẫn việc Controller gọi đúng use case. Không cần khởi động database thật khi chỉ kiểm tra binding, validation và tên View.

### 15.1. Controller slice test với MockMvc

~~~java
@WebMvcTest(BookController.class)
class BookControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    BookQueryService bookQueries;

    @MockitoBean
    BookCommandService bookCommands;

    @Test
    void showsBookDetail() throws Exception {
        UUID id = UUID.randomUUID();

        given(bookQueries.getDetail(id))
            .willReturn(new BookDetailViewModel(
                id,
                "Thiết kế hệ thống",
                "9780000000001",
                "Nguyễn An",
                "Công nghệ",
                "250.000 đ",
                "PUBLISHED",
                true,
                true
            ));

        mockMvc.perform(get("/books/{id}", id))
            .andExpect(status().isOk())
            .andExpect(view().name("books/detail"))
            .andExpect(model().attributeExists("book"));
    }
}
~~~

Tên annotation mock bean có thể phụ thuộc phiên bản Spring Boot. Nếu dự án dùng phiên bản cũ hơn, có thể dùng @MockBean; với phiên bản mới, @MockitoBean có thể được hỗ trợ. Hãy dùng API đúng phiên bản của dự án.

### 15.2. Kiểm thử validation

- Gửi form thiếu tiêu đề.
- Gửi ISBN sai định dạng.
- Gửi giá âm.
- Xác nhận không gọi command service khi validation thất bại.
- Xác nhận form và danh sách tham chiếu được trả lại.
- Xác nhận lỗi gắn với đúng field.

### 15.3. Kiểm thử action ghi

- Tạo sách thành công trả redirect đến chi tiết.
- ISBN trùng hiển thị conflict phù hợp.
- Cập nhật sách không thuộc tenant bị từ chối.
- Xóa sách đang được mượn thất bại theo quy tắc.
- Version cũ được xử lý như stale update.
- Request thiếu CSRF token bị từ chối khi CSRF protection được bật.
- Người dùng không đủ quyền không thể gọi action dù biết URL.

### 15.4. Integration và end-to-end test

Controller slice test không xác nhận toàn bộ wiring hoặc SQL. Cần thêm integration test cho repository, transaction, constraint và optimistic locking. End-to-end test có thể xác nhận người dùng hoàn thành một luồng từ form tạo sách đến trang chi tiết.

Không dùng một test end-to-end lớn để thay thế toàn bộ unit/controller test. Mỗi loại test nên tập trung vào ranh giới mà nó xác nhận.

## 16. Những sai lầm thường gặp khi thiết kế Controller

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Controller chứa toàn bộ nghiệp vụ | Method dài, khó test và tái sử dụng | Gọi application service/use case |
| Controller gọi trực tiếp SQL/JPA | Coupling với persistence | Dùng query/command service hoặc port |
| Bind form vào entity | Mass assignment và ghi đè field | Request DTO allowlist |
| Dùng GET để xóa hoặc cập nhật | Có thể bị kích hoạt ngoài ý muốn | POST/PUT/PATCH/DELETE phù hợp |
| Không dùng PRG sau POST | Refresh có thể gửi lại form | Redirect đến GET sau khi thành công |
| Chỉ ẩn nút theo role | Endpoint vẫn có thể bị gọi trực tiếp | Authorization phía server |
| Không giới hạn page size | Request có thể gây tải lớn | Default, maximum và validation |
| Trả entity trực tiếp ra JSON | Lộ field, vòng serialization, coupling schema | Response DTO/projection |
| Dùng một Controller cho mọi chức năng | Quá nhiều dependency và trách nhiệm | Tách theo phạm vi/use case |
| Bắt mọi exception rồi trả trang chung | Mất ngữ nghĩa lỗi và khó debug | Exception type và mapping rõ |
| Không xử lý cập nhật đồng thời | Ghi đè dữ liệu mới | Optimistic locking/version |
| Nghĩ PRG bảo đảm thao tác chỉ chạy một lần | Retry vẫn có thể tạo tác dụng phụ lặp | Unique constraint/idempotency khi cần |

## 17. Checklist thiết kế Controller quản lý sách

### Route và action

- [ ] Route và HTTP method phản ánh đúng thao tác đọc/ghi.
- [ ] GET chỉ đọc và không tạo tác dụng phụ.
- [ ] Mỗi action có một mục đích rõ ràng.
- [ ] Tên method thể hiện hành động và tài nguyên.
- [ ] Bộ lọc nằm trong query parameter, không nhồi vào logic Controller.

### Request và response

- [ ] Form dùng request DTO thay vì persistence entity.
- [ ] BindingResult đặt ngay sau tham số được validate.
- [ ] View nhận ViewModel/projection phù hợp.
- [ ] Response API có DTO và allowlist field.
- [ ] Không đưa tenant, audit hoặc field nội bộ ra output.

### Nghiệp vụ và bảo mật

- [ ] Quy tắc ISBN, trạng thái và xóa nằm trong application/domain layer.
- [ ] Authorization được kiểm tra trên server và đúng tài nguyên.
- [ ] Form ghi dữ liệu có CSRF protection khi dùng session cookie.
- [ ] Tenant/owner được xác định từ ngữ cảnh đáng tin cậy.
- [ ] Cập nhật đồng thời được xử lý theo yêu cầu.
- [ ] Các thao tác dễ bị retry có chính sách idempotency phù hợp.

### Lỗi và kiểm thử

- [ ] Validation lỗi trả lại form cùng dữ liệu tham chiếu.
- [ ] Not found, forbidden, conflict và lỗi hệ thống được phân biệt.
- [ ] POST thành công dùng redirect theo PRG khi phù hợp.
- [ ] Controller test xác nhận binding, gọi use case và response.
- [ ] Integration test xác nhận persistence, transaction và constraint.
- [ ] Có test quyền truy cập, CSRF và cập nhật đồng thời.

## 18. Kết luận

Trong ví dụ quản lý sách, Controller là điểm chuyển đổi giữa giao thức HTTP và các hành động của ứng dụng. Mỗi action nên nhận input theo hợp đồng rõ ràng, kiểm tra dữ liệu ở mức phù hợp, gọi use case và chọn View hoặc response. Các quy tắc như ISBN duy nhất, quyền sửa, điều kiện xóa và chuyển trạng thái cần được bảo vệ ở application/domain layer.

Khi thiết kế đúng ranh giới, BookController dễ đọc và tập trung vào luồng request; request DTO ngăn client gửi field ngoài ý muốn; ViewModel giữ hợp đồng trình bày ổn định; application service thực thi quy tắc; repository quản lý persistence. Kết hợp route nhất quán, PRG, authorization, xử lý lỗi và kiểm thử ở từng tầng sẽ tạo nên một luồng MVC quản lý sách dễ mở rộng và đáng tin cậy.
