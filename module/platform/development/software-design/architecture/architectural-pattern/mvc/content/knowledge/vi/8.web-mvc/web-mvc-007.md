# Đóng gói dữ liệu hiển thị và chọn khuôn mẫu

## 1. Vì sao cần đóng gói dữ liệu hiển thị?

Trong MVC trên web, Controller nhận HTTP request, gọi nghiệp vụ và chuẩn bị dữ liệu cho View. View dùng dữ liệu đó để tạo HTML hoặc một representation khác gửi về client. Hai quyết định cần được làm rõ là:

- **Dữ liệu nào được đưa vào View?** Controller cần cung cấp một hợp đồng dữ liệu đủ để trình bày, có cấu trúc và không làm lộ chi tiết nội bộ của miền nghiệp vụ.
- **View nào sẽ trình bày dữ liệu?** Ứng dụng cần chọn khuôn mẫu (template) hoặc loại response phù hợp với mục đích của request.

Nếu Controller truyền thẳng toàn bộ Entity hoặc đối tượng persistence vào template, View có thể phụ thuộc vào cấu trúc cơ sở dữ liệu, vô tình truy cập quan hệ lazy, hoặc hiển thị trường nhạy cảm. Nếu Controller chọn template bằng cách ghép đường dẫn từ dữ liệu người dùng, ứng dụng có thể mở ra lỗ hổng truy cập file hoặc template ngoài dự kiến.

Đóng gói dữ liệu và chọn khuôn mẫu là một phần của hợp đồng giữa Controller và View. Khi hợp đồng rõ ràng, có thể thay đổi giao diện hoặc cách lưu trữ mà ít ảnh hưởng đến phần còn lại của ứng dụng.

## 2. Luồng từ request đến template

Một request đọc danh sách sách có thể đi qua các bước:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as Router
    participant C as BookController
    participant S as BookQueryService
    participant M as View Model
    participant T as Template Resolver
    participant V as books/list.html
    B->>R: GET /books?q=java
    R->>C: Chọn action list
    C->>S: Tìm sách theo từ khóa
    S-->>C: Kết quả nghiệp vụ
    C->>M: Chuyển thành dữ liệu hiển thị
    C->>T: Tên view logic books/list
    T-->>V: Tìm template tương ứng
    V-->>B: HTML response
~~~

Trong luồng này, Service tập trung vào truy vấn và quy tắc ứng dụng. Controller chuyển kết quả thành dữ liệu dành cho giao diện và chọn tên View. Template Resolver của framework ánh xạ tên View logic đến file template thực tế. View render dữ liệu thành HTML.

Không phải framework nào cũng dùng đúng tên hoặc đúng thành phần như Spring MVC. Tuy nhiên, ranh giới khái niệm vẫn tương tự: dữ liệu trình bày được chuẩn bị riêng, còn cơ chế render tìm khuôn mẫu theo quy ước đã cấu hình.

## 3. Đóng gói dữ liệu bằng View Model

**View Model** là cấu trúc dữ liệu được thiết kế theo nhu cầu của một màn hình hoặc một response. Nó trả lời câu hỏi View cần biết những gì để trình bày một use case cụ thể.

Ví dụ, trang danh sách sách có thể cần tiêu đề, tên tác giả, ISBN và nhãn trạng thái. View không nhất thiết cần toàn bộ đối tượng `Book`, lịch sử giao dịch, quan hệ ORM hoặc thông tin nội bộ khác.

### Ví dụ View Model bằng Java

~~~java
import java.util.List;
import java.util.UUID;

public record BookListItemView(
        UUID id,
        String title,
        String authorName,
        String isbn,
        String statusLabel
) {}

public record PaginationView(
        int currentPage,
        int totalPages,
        long totalItems
) {}

public record BookListViewModel(
        String pageTitle,
        String query,
        List<BookListItemView> items,
        PaginationView pagination
) {}
~~~

`BookListViewModel` gom những dữ liệu cùng phục vụ trang danh sách. `items` là danh sách các mục đã được chuyển đổi; `pagination` chứa thông tin điều hướng; `query` giúp biểu mẫu hiển thị lại từ khóa hiện tại. Cấu trúc này có thể thay đổi độc lập với Entity và schema cơ sở dữ liệu.

### Những nguyên tắc khi thiết kế View Model

**Chỉ đưa dữ liệu cần trình bày.** Nếu trang danh sách chỉ hiển thị tên tác giả, hãy truyền `authorName` thay vì toàn bộ Entity `Author` cùng các quan hệ của nó.

**Dùng tên có ý nghĩa đối với giao diện.** `statusLabel` có thể là “Đang lưu hành”, còn mã trạng thái miền có thể là `AVAILABLE`. View Model có thể chứa cả mã và nhãn nếu giao diện cần biểu diễn trạng thái hoặc hỗ trợ thao tác lọc.

**Chuẩn hóa cấu trúc rỗng.** Collection nên được cung cấp dưới dạng danh sách rỗng thay vì `null`; trường tùy chọn cần có quy ước rõ. Nhờ vậy template không phải xử lý nhiều trạng thái thiếu dữ liệu không cần thiết.

**Đưa metadata trình bày vào đúng nơi.** Tiêu đề trang, thông tin phân trang, breadcrumb, bộ lọc hiện tại hoặc các hành động được phép có thể thuộc View Model khi chúng cần cho một màn hình.

**Không nhúng quy tắc nghiệp vụ vào View Model.** Việc chuyển `AVAILABLE` thành nhãn hiển thị là công việc trình bày. Quyết định một cuốn sách có thể được mượn hay không vẫn thuộc Model/Service.

**Không đưa dữ liệu nhạy cảm vào response.** Ẩn trường bằng CSS không làm trường đó trở nên bí mật. Nếu dữ liệu không cần hiển thị, đừng đưa nó vào View Model.

## 4. Phân biệt Domain Model, Request DTO và View Model

Trong một ứng dụng web, từ “Model” có thể chỉ nhiều loại đối tượng khác nhau. Chúng có thể trùng nhau ở ứng dụng nhỏ, nhưng cần phân biệt mục đích:

| Loại dữ liệu | Mục đích | Ví dụ |
|---|---|---|
| Domain Entity/Value Object | Biểu diễn khái niệm, trạng thái và quy tắc nghiệp vụ | `Book`, `Isbn` |
| Request DTO/Form | Nhận dữ liệu từ client theo hợp đồng đầu vào | `CreateBookForm` |
| View Model/Response DTO | Cung cấp dữ liệu đã chọn cho một màn hình hoặc response | `BookListViewModel` |
| Persistence Model | Phục vụ ánh xạ và lưu trữ | JPA entity hoặc document |

Request DTO và View Model thường có hướng dữ liệu khác nhau. Request DTO đi từ client vào ứng dụng; View Model đi từ ứng dụng ra giao diện. Không nên dùng một đối tượng duy nhất cho cả hai chiều nếu các trường được phép gửi và các trường được phép hiển thị khác nhau.

Ví dụ, `CreateBookForm` nhận `title` và `isbn` từ người dùng. Sau khi Service tạo sách thành công, Controller có thể chuyển Entity thành `BookDetailView` chỉ gồm `id`, `title`, `authorName`, `isbn` và `statusLabel`. Client không thể tự gửi `statusLabel` để quyết định trạng thái nghiệp vụ.

## 5. Đưa dữ liệu vào Model của Spring MVC

Trong Spring MVC, tham số `org.springframework.ui.Model` là nơi Controller thêm các thuộc tính để View sử dụng. Từ “Model” ở đây chỉ model map của request hiện tại, không đồng nghĩa với Domain Model.

### Ví dụ Controller trả về tên View logic

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class BookController {
    private final BookQueryService bookQueryService;
    private final BookViewMapper bookViewMapper;

    public BookController(
            BookQueryService bookQueryService,
            BookViewMapper bookViewMapper) {
        this.bookQueryService = bookQueryService;
        this.bookViewMapper = bookViewMapper;
    }

    @GetMapping("/books")
    public String list(
            @RequestParam(defaultValue = "") String q,
            Model model) {
        var result = bookQueryService.search(q);
        var page = bookViewMapper.toListView(result, q);

        model.addAttribute("page", page);
        return "books/list";
    }
}
~~~

`model.addAttribute("page", page)` tạo thuộc tính `page` cho template. Chuỗi trả về `books/list` là **tên View logic**, không phải đường dẫn file do client cung cấp. Với Thymeleaf và cấu hình thông dụng, tên này có thể được ánh xạ đến `templates/books/list.html`.

Template có thể đọc dữ liệu như sau:

~~~html
<h1 th:text="${page.pageTitle}">Danh sách sách</h1>

<form method="get" th:action="@{/books}">
  <label for="q">Tìm sách</label>
  <input id="q" name="q" th:value="${page.query}" />
  <button type="submit">Tìm</button>
</form>

<p th:if="${#lists.isEmpty(page.items)}">
  Không tìm thấy sách phù hợp.
</p>

<ul th:if="${!#lists.isEmpty(page.items)}">
  <li th:each="book : ${page.items}">
    <a th:href="@{/books/{id}(id=${book.id})}"
       th:text="${book.title}">Tên sách</a>
    <span th:text="${book.authorName}">Tác giả</span>
    <span th:text="${book.statusLabel}">Trạng thái</span>
  </li>
</ul>
~~~

Controller và template phải thống nhất tên thuộc tính và cấu trúc dữ liệu. Nếu Controller đổi tên `page` thành `bookPage` mà template vẫn đọc `${page...}`, giao diện sẽ thiếu dữ liệu hoặc render lỗi. View Model là hợp đồng, vì vậy thay đổi cấu trúc cần được xem xét như thay đổi API nội bộ giữa Controller và View.

### Thêm thuộc tính dùng chung bằng `@ModelAttribute`

Nếu nhiều trang cần cùng dữ liệu như tên ứng dụng hoặc thông tin điều hướng, Controller có thể dùng phương thức `@ModelAttribute` để thêm thuộc tính trước khi chạy các handler:

~~~java
@Controller
public class BookPageController {

    @ModelAttribute("navigation")
    public NavigationView navigation() {
        return new NavigationView("Thư viện", "/books");
    }

    @GetMapping("/books")
    public String list(Model model) {
        model.addAttribute("books", bookQueryService.findAll());
        return "books/list";
    }
}

public record NavigationView(String label, String href) {}
~~~

Trong ví dụ rút gọn, `bookQueryService` cần được khai báo và inject như dependency của Controller. Phương thức `@ModelAttribute` được gọi để chuẩn bị thuộc tính cho các request phù hợp trong phạm vi Controller. Với dữ liệu toàn cục dùng ở nhiều Controller, có thể dùng `@ControllerAdvice` cùng `@ModelAttribute`, nhưng chỉ nên thêm dữ liệu thật sự cần thiết để tránh truy vấn lặp hoặc làm mọi trang phụ thuộc vào dữ liệu không liên quan.

## 6. Kết hợp dữ liệu và View bằng `ModelAndView`

Spring MVC cũng hỗ trợ `ModelAndView`, một đối tượng kết hợp tên View và model attributes. Cách này hữu ích khi muốn trả cả dữ liệu lẫn View từ một phương thức:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.servlet.ModelAndView;

@Controller
public class BookDetailController {
    private final BookQueryService bookQueryService;
    private final BookViewMapper bookViewMapper;

    public BookDetailController(
            BookQueryService bookQueryService,
            BookViewMapper bookViewMapper) {
        this.bookQueryService = bookQueryService;
        this.bookViewMapper = bookViewMapper;
    }

    @GetMapping("/books/featured")
    public ModelAndView featured() {
        var book = bookQueryService.findFeatured();
        var viewModel = bookViewMapper.toDetailView(book);

        return new ModelAndView("books/detail", "book", viewModel);
    }
}
~~~

Ở đây, `books/detail` là tên View logic; `book` là tên thuộc tính trong model; `viewModel` là dữ liệu được template sử dụng. Có thể dùng `Model` và trả về `String` hoặc dùng `ModelAndView`; hãy chọn một phong cách nhất quán theo quy ước của dự án.

`ModelAndView` không có nghĩa Controller phải tự tạo HTML. Framework vẫn dùng View Resolver để tìm và render template.

## 7. Chọn khuôn mẫu bằng tên View logic

Trong MVC phía máy chủ, Controller thường trả về tên View logic. View Resolver hoặc Template Resolver dùng cấu hình để ánh xạ tên này đến khuôn mẫu.

Ví dụ cấu trúc template:

~~~text
src/main/resources/
└── templates/
    ├── books/
    │   ├── list.html
    │   ├── detail.html
    │   └── form.html
    └── errors/
        ├── 404.html
        └── 500.html
~~~

Controller có thể trả về:

| Tên View logic | Template được ánh xạ theo cấu hình ví dụ | Mục đích |
|---|---|---|
| `books/list` | `templates/books/list.html` | Danh sách sách |
| `books/detail` | `templates/books/detail.html` | Chi tiết sách |
| `books/form` | `templates/books/form.html` | Tạo hoặc sửa sách |
| `errors/404` | `templates/errors/404.html` | Không tìm thấy tài nguyên |

Với Thymeleaf trong Spring Boot, resolver thường được cấu hình tự động theo quy ước thư mục `templates` và phần mở rộng `.html`. Dự án có thể thay đổi prefix, suffix hoặc cấu hình resolver khác. Vì vậy, tên View logic cần theo quy ước của ứng dụng.

### Chọn template theo kết quả use case

Controller có thể chọn template dựa trên kết quả nghiệp vụ đã xác định:

~~~java
@GetMapping("/books/{id}")
public String detail(@PathVariable UUID id, Model model) {
    var result = bookQueryService.findDetail(id);

    if (result.isEmpty()) {
        model.addAttribute("message", "Sách không tồn tại.");
        return "errors/404";
    }

    model.addAttribute(
            "book", bookViewMapper.toDetailView(result.get()));
    return "books/detail";
}
~~~

Ví dụ giả định Service trả về `Optional` và các kiểu cần thiết đã được khai báo. Trong ứng dụng Spring, cũng có thể ném `BookNotFoundException` và dùng `@ControllerAdvice` để xử lý lỗi tập trung. Hãy tránh trả về một template chi tiết với dữ liệu `null`, vì người dùng có thể hiểu nhầm tài nguyên vẫn tồn tại.

### Không lấy tên template trực tiếp từ input

Không nên viết:

~~~java
return request.getParameter("template");
~~~

hoặc nối tên template từ query parameter, tên file tải lên hay giá trị do người dùng kiểm soát. Nếu đầu vào có thể trở thành tên View logic, người dùng có thể cố truy cập template ngoài phạm vi dự kiến.

Nếu giao diện có nhiều biến thể, hãy ánh xạ một lựa chọn đã được kiểm tra vào một tập tên View cố định:

~~~java
String viewName = switch (layout == null ? "" : layout) {
    case "compact" -> "books/list-compact";
    case "detailed" -> "books/list-detailed";
    default -> "books/list";
};
return viewName;
~~~

Ở ví dụ này, `layout` phải được kiểm tra theo danh sách cho phép; lựa chọn mặc định được dùng cho mọi giá trị không hợp lệ. Tên View vẫn là hằng số do ứng dụng kiểm soát.

## 8. Chọn HTML hay JSON

Không phải mọi request web đều cần template HTML. Một ứng dụng có thể trả HTML cho trình duyệt và JSON cho API. Cách trả response phải phù hợp với hợp đồng endpoint.

**HTML phía máy chủ:** Controller dùng `@Controller`, thêm thuộc tính vào `Model` hoặc trả `ModelAndView`, sau đó trả tên View logic.

**JSON API:** Controller dùng `@ResponseBody`, `@RestController` hoặc trả `ResponseEntity<DTO>`. Dữ liệu được serialize thành JSON; không cần chọn template HTML.

Ví dụ tách endpoint theo mục đích:

~~~java
@Controller
public class BookPageController {
    @GetMapping(value = "/books", produces = MediaType.TEXT_HTML_VALUE)
    public String listPage(Model model) {
        model.addAttribute("page", bookQueryService.listView());
        return "books/list";
    }
}

@RestController
public class BookApiController {
    @GetMapping(value = "/api/books", produces = MediaType.APPLICATION_JSON_VALUE)
    public BookListResponse listApi() {
        return bookQueryService.listResponse();
    }
}
~~~

Đoạn mã minh họa, giả định các dependency, DTO và import Spring đã được khai báo. `produces` mô tả loại representation endpoint tạo ra. Nếu cùng một URL cần phục vụ nhiều representation, có thể dùng content negotiation dựa trên `Accept` hoặc các mapping `produces` riêng; cần kiểm thử trường hợp client gửi `Accept: */*` và định nghĩa rõ representation mặc định.

Không nên trả JSON bằng cách render template HTML rồi yêu cầu client tự phân tích. Cũng không nên trả tên View logic từ một endpoint API chỉ vì phương thức Controller cần trả dữ liệu.

## 9. Dữ liệu qua redirect và Flash Attributes

Khi một biểu mẫu được gửi thành công, ứng dụng HTML thường dùng mẫu **Post/Redirect/Get (PRG)**:

1. Browser gửi POST để thực hiện thao tác.
2. Server xử lý và chuyển hướng bằng response 3xx.
3. Browser gửi GET mới để tải trang kết quả.

PRG tránh việc tải lại trang làm trình duyệt gửi lại POST. Nếu cần hiển thị thông báo một lần sau redirect, Spring MVC cung cấp `RedirectAttributes` và flash attributes:

~~~java
@PostMapping("/books")
public String create(
        @Valid @ModelAttribute("form") CreateBookForm form,
        BindingResult errors,
        RedirectAttributes redirectAttributes) {
    if (errors.hasErrors()) {
        return "books/form";
    }

    bookService.create(form);
    redirectAttributes.addFlashAttribute(
            "successMessage", "Đã tạo sách thành công.");
    return "redirect:/books";
}
~~~

Flash attribute được lưu tạm cho request sau redirect theo cơ chế của Spring MVC, thường dùng cho thông báo thành công hoặc lỗi ngắn hạn. Không dùng flash attribute làm nơi lưu trạng thái nghiệp vụ lâu dài hoặc dữ liệu lớn. Với lỗi validation, thường trả lại trực tiếp template biểu mẫu cùng `BindingResult` để giữ lỗi gắn với từng trường.

## 10. Kiểm soát scope và vòng đời dữ liệu

Model attributes thông thường được chuẩn bị cho request xử lý hiện tại. Chúng phù hợp với dữ liệu chỉ cần trong lúc render response, như View Model, thông báo và thông tin phân trang.

Không nên lưu dữ liệu riêng của từng request trong field mutable của một Controller singleton. Trong Spring, Controller thường là singleton; nhiều request có thể đồng thời gọi cùng một instance. Dữ liệu hiển thị nên được tạo thành biến cục bộ và đưa vào `Model` của request.

Cũng cần phân biệt các phạm vi:

| Phạm vi | Dùng khi nào | Ví dụ |
|---|---|---|
| Request model | Dữ liệu chỉ phục vụ response hiện tại | `BookListViewModel` |
| Flash attribute | Thông báo hoặc dữ liệu ngắn hạn đi qua redirect | `successMessage` |
| Session | Trạng thái người dùng cần tồn tại qua nhiều request và có chủ đích | Wizard nhiều bước hoặc tùy chọn phiên làm việc |
| Persistent storage | Dữ liệu nghiệp vụ cần tồn tại lâu dài | Sách, phiếu mượn trong database |

Không đưa toàn bộ View Model vào session chỉ để tránh truy vấn lại. Session có vòng đời dài hơn request, tiêu tốn bộ nhớ và có thể tạo dữ liệu cũ. Hãy lưu trạng thái ở phạm vi nhỏ nhất đáp ứng được nhu cầu.

## 11. Kiểm thử hợp đồng dữ liệu và lựa chọn template

Kiểm thử cần xác minh cả dữ liệu được đóng gói lẫn View logic được chọn. Một số ca quan trọng:

| Tình huống | Điều cần xác minh |
|---|---|
| Danh sách có kết quả | Model có `page` với các mục, metadata và query đúng |
| Danh sách rỗng | Template nhận collection rỗng và hiển thị trạng thái rỗng |
| Chi tiết tồn tại | Controller chọn `books/detail` và truyền View Model phù hợp |
| Chi tiết không tồn tại | Chọn `errors/404` hoặc response 404 theo cơ chế đã thiết kế |
| Form không hợp lệ | Trả lại `books/form`, giữ `BindingResult` và không gọi Service tạo dữ liệu |
| POST thành công | Redirect đến GET và flash message xuất hiện một lần |
| API JSON | Trả DTO JSON, content type phù hợp và không render template HTML |
| Input chọn layout không hợp lệ | Dùng template mặc định trong danh sách cho phép |

**Unit test cho mapper** kiểm tra Entity/Service result được chuyển thành View Model đúng và không chứa trường không cần thiết. **Test Controller** kiểm tra tên View, model attributes, status và redirect. **Integration test** có thể render template thật để phát hiện sai tên thuộc tính hoặc sai đường dẫn template.

Với Spring MVC, `MockMvc` thường được dùng để gửi request và kiểm tra view name, model, status, header và nội dung response. Nếu kiểm tra HTML được render, cần cấu hình template engine trong test context hoặc dùng kiểm thử tích hợp phù hợp.

## 12. Những sai lầm thường gặp

- **Truyền toàn bộ Entity vào template:** View bị phụ thuộc persistence, có thể gặp lazy loading và lộ trường không cần thiết.
- **Dùng chung Request DTO và View Model:** dữ liệu đầu vào và đầu ra có mục đích khác nhau, dễ tạo trường không an toàn hoặc hợp đồng khó hiểu.
- **Đưa logic nghiệp vụ vào template:** View khó kiểm thử và các luồng khác có thể bỏ qua quy tắc.
- **Nhầm tên View logic với đường dẫn file:** framework resolver chịu trách nhiệm ánh xạ tên logic theo cấu hình.
- **Lấy tên template từ request:** có thể mở đường truy cập template ngoài danh sách được phép.
- **Trộn HTML và JSON trong một handler không rõ hợp đồng:** client khó dự đoán content type và cấu trúc response.
- **Dùng session cho mọi dữ liệu hiển thị:** làm trạng thái cũ tồn tại quá lâu và tăng bộ nhớ.
- **Không kiểm thử view name và model attributes:** template có thể render sai dù Service trả dữ liệu đúng.

## 13. Kết luận

Đóng gói dữ liệu hiển thị giúp Controller cung cấp cho View một hợp đồng rõ ràng, thường thông qua View Model hoặc DTO dành riêng cho response. Chọn khuôn mẫu bằng tên View logic giúp tách quyết định trình bày khỏi vị trí file thực tế và tận dụng cơ chế resolver của framework. Với API, Controller có thể trả DTO JSON thay vì template HTML; với biểu mẫu, redirect và flash attributes hỗ trợ luồng PRG.

Khi thiết kế MVC web, hãy xác định dữ liệu nào cần được hiển thị, phạm vi tồn tại của dữ liệu đó, View logic nào phù hợp với kết quả use case và representation nào client mong đợi. Giữ hợp đồng Controller–View rõ ràng giúp giao diện dễ thay đổi, dữ liệu an toàn và việc kiểm thử có mục tiêu.
