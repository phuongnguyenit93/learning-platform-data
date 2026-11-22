# Vòng đời biểu mẫu từ hiển thị đến tiếp nhận

## 1. Biểu mẫu trong luồng MVC web

Trong ứng dụng Model–View–Controller, biểu mẫu (form) là một cách để người dùng gửi dữ liệu vào ứng dụng. View tạo các trường nhập liệu và hướng dẫn; trình duyệt thu thập giá trị rồi gửi HTTP request; Controller tiếp nhận request, binding dữ liệu vào đối tượng đầu vào, phối hợp validation và nghiệp vụ, sau đó chọn response phù hợp.

Một biểu mẫu tạo sách thường đi qua hai request chính:

- `GET /books/new`: lấy trang biểu mẫu và hiển thị các trường ban đầu.
- `POST /books`: gửi dữ liệu người dùng đã nhập để ứng dụng kiểm tra và tạo sách.

Nếu dữ liệu không hợp lệ, máy chủ trả lại trang biểu mẫu cùng giá trị đã nhập và thông báo lỗi. Nếu thao tác thành công, máy chủ chuyển hướng đến trang kết quả. Đây là vòng đời cơ bản từ hiển thị đến tiếp nhận.

## 2. Toàn bộ vòng đời biểu mẫu

~~~mermaid
flowchart TD
    A[Browser gửi GET /books/new] --> B[Controller chuẩn bị Form DTO và dữ liệu phụ]
    B --> C[View render biểu mẫu HTML]
    C --> D[Người dùng nhập và gửi form]
    D --> E[Browser gửi POST /books]
    E --> F[Routing và kiểm tra bảo mật]
    F --> G[Binding request vào Form DTO]
    G --> H[Validation dữ liệu đầu vào]
    H -->|Có lỗi| I[Trả lại View cùng giá trị và lỗi]
    I --> C
    H -->|Hợp lệ| J[Service thực hiện quy tắc nghiệp vụ]
    J -->|Nghiệp vụ từ chối| I
    J -->|Thành công| K[Lưu dữ liệu]
    K --> L[Redirect đến GET]
    L --> M[Browser tải trang kết quả]
~~~

Luồng này có thể được mở rộng cho chỉnh sửa, tìm kiếm hoặc nhiều bước. Tuy nhiên, cần phân biệt ba lớp kiểm tra:

1. **Binding:** chuyển dữ liệu dạng chuỗi từ request thành kiểu dữ liệu mà ứng dụng mong đợi, ví dụ `String` thành `LocalDate` hoặc UUID.
2. **Validation đầu vào:** kiểm tra trường bắt buộc, độ dài, định dạng và quan hệ giữa các trường.
3. **Quy tắc nghiệp vụ:** kiểm tra điều kiện phụ thuộc vào trạng thái miền hoặc dữ liệu hiện có, ví dụ ISBN đã được sử dụng hay sách có thể được mượn hay không.

Binding và validation thường diễn ra trước khi gọi Service. Quy tắc nghiệp vụ vẫn phải được bảo vệ ở Model/Service vì dữ liệu có thể đến từ API, tác vụ nền hoặc một luồng khác không dùng biểu mẫu.

## 3. Bước GET: chuẩn bị và hiển thị biểu mẫu

Khi người dùng mở trang tạo sách, Controller tạo một đối tượng Form DTO rỗng hoặc có giá trị mặc định, nạp dữ liệu phụ cho các trường chọn, rồi trả về tên View logic.

~~~java
@Controller
@RequestMapping("/books")
public class BookController {
    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping("/new")
    public String showCreateForm(Model model) {
        model.addAttribute("form", new CreateBookForm());
        return "books/form";
    }
}
~~~

`form` là tên thuộc tính mà template sẽ dùng. Đối tượng này mô tả dữ liệu cần nhập; nó không phải Entity được lưu trực tiếp. Với biểu mẫu chỉnh sửa, Controller thường tải Entity hoặc dữ liệu truy vấn, chuyển sang Form DTO rồi đưa vào model để View hiển thị giá trị hiện tại.

Ví dụ, biểu mẫu chỉnh sửa sách có thể được nạp bằng `bookFormMapper.toForm(book)`. Không nên đưa toàn bộ Entity có quan hệ persistence vào biểu mẫu nếu người dùng chỉ được phép sửa một vài trường.

## 4. Thiết kế Form DTO

Form DTO (Data Transfer Object) mô tả hợp đồng dữ liệu mà một request biểu mẫu được phép gửi. Nó giúp tách dữ liệu đầu vào khỏi Domain Entity và tránh việc người dùng gửi thêm những thuộc tính nội bộ như `id`, `status`, `createdAt` hoặc `approvedBy` để thay đổi ngoài ý muốn.

Ví dụ một biểu mẫu tạo sách chỉ nhận tiêu đề, tác giả, ISBN và ngày xuất bản:

~~~java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class CreateBookForm {
    @NotBlank(message = "Tiêu đề không được để trống")
    @Size(max = 200, message = "Tiêu đề tối đa 200 ký tự")
    private String title;

    @NotBlank(message = "Tên tác giả không được để trống")
    @Size(max = 120, message = "Tên tác giả tối đa 120 ký tự")
    private String authorName;

    @NotBlank(message = "ISBN không được để trống")
    private String isbn;

    @NotNull(message = "Vui lòng chọn ngày xuất bản")
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate publishedDate;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public String getAuthorName() { return authorName; }
    public void setAuthorName(String authorName) { this.authorName = authorName; }

    public String getIsbn() { return isbn; }
    public void setIsbn(String isbn) { this.isbn = isbn; }

    public LocalDate getPublishedDate() { return publishedDate; }
    public void setPublishedDate(LocalDate publishedDate) {
        this.publishedDate = publishedDate;
    }
}
~~~

`@NotBlank` kiểm tra chuỗi có nội dung sau khi bỏ khoảng trắng; `@Size` giới hạn độ dài; `@NotNull` yêu cầu ngày xuất bản có giá trị. `@DateTimeFormat` hướng dẫn Spring chuyển chuỗi ngày theo định dạng ISO `yyyy-MM-dd`, phù hợp với giá trị mà trường HTML `input type="date"` gửi lên.

Ví dụ dùng JavaBean có constructor mặc định và getter/setter để minh họa binding theo thuộc tính. Có thể dùng record hoặc immutable DTO với cơ chế constructor binding phù hợp phiên bản Spring; điều quan trọng là phải xác định rõ các trường được phép bind.

## 5. Bước View: liên kết trường HTML với Form DTO

Thymeleaf hỗ trợ `th:object` để chọn đối tượng biểu mẫu và `th:field` để liên kết từng trường với thuộc tính tương ứng. Framework tự tạo `name`, `id` và giá trị hiển thị theo quy ước, đồng thời có thể hiển thị lại giá trị đã binding sau khi validation thất bại.

~~~html
<form th:action="@{/books}" th:object="${form}" method="post">
  <div>
    <label for="title">Tiêu đề</label>
    <input id="title" type="text" th:field="*{title}"
           aria-describedby="title-error" />
    <p id="title-error" th:if="${#fields.hasErrors('title')}"
       th:errors="*{title}">Lỗi tiêu đề</p>
  </div>

  <div>
    <label for="authorName">Tác giả</label>
    <input id="authorName" type="text" th:field="*{authorName}"
           aria-describedby="author-error" />
    <p id="author-error" th:if="${#fields.hasErrors('authorName')}"
       th:errors="*{authorName}">Lỗi tác giả</p>
  </div>

  <div>
    <label for="isbn">ISBN</label>
    <input id="isbn" type="text" th:field="*{isbn}"
           aria-describedby="isbn-error" />
    <p id="isbn-error" th:if="${#fields.hasErrors('isbn')}"
       th:errors="*{isbn}">Lỗi ISBN</p>
  </div>

  <div>
    <label for="publishedDate">Ngày xuất bản</label>
    <input id="publishedDate" type="date"
           th:field="*{publishedDate}"
           aria-describedby="published-date-error" />
    <p id="published-date-error"
       th:if="${#fields.hasErrors('publishedDate')}"
       th:errors="*{publishedDate}">Lỗi ngày xuất bản</p>
  </div>

  <button type="submit">Lưu sách</button>
</form>
~~~

`th:field="*{title}"` liên kết trường với `form.title`; `th:errors` hiển thị lỗi gắn với thuộc tính đó. Cần giữ `id` và `label` liên kết với nhau để người dùng bàn phím và trình đọc màn hình có thể nhận biết trường.

Với các lỗi chung không gắn vào một trường, có thể hiển thị khu vực lỗi tổng quát:

~~~html
<div th:if="${#fields.hasGlobalErrors()}" role="alert">
  <p th:each="error : ${#fields.globalErrors()}"
     th:text="${error}">Lỗi biểu mẫu</p>
</div>
~~~

Trình duyệt có thể thực hiện một số kiểm tra như `required`, `maxlength` hoặc `type="date"`. Đây là hỗ trợ trải nghiệm người dùng; request vẫn có thể được gửi bằng công cụ khác nên máy chủ phải kiểm tra lại.

## 6. Bước POST: binding request vào đối tượng

Khi người dùng gửi biểu mẫu, trình duyệt gửi các cặp tên/giá trị trong request body. Ví dụ:

~~~http
POST /books
Content-Type: application/x-www-form-urlencoded

title=Clean+Architecture&authorName=Robert+Martin&isbn=9780132350884&publishedDate=2008-08-11
~~~

Spring MVC dùng `@ModelAttribute` để binding request parameters vào Form DTO. Quá trình này bao gồm đọc giá trị, tìm thuộc tính tương ứng và chuyển đổi sang kiểu đích.

Ví dụ `publishedDate=2008-08-11` được chuyển thành `LocalDate`. Nếu client gửi `publishedDate=tomorrow`, quá trình chuyển đổi thất bại và lỗi binding được ghi nhận trong `BindingResult`.

### Controller tiếp nhận biểu mẫu

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@PostMapping
public String create(
        @Valid @ModelAttribute("form") CreateBookForm form,
        BindingResult bindingResult,
        Model model,
        RedirectAttributes redirectAttributes) {

    if (bindingResult.hasErrors()) {
        return "books/form";
    }

    bookService.create(form);
    redirectAttributes.addFlashAttribute(
            "successMessage", "Đã tạo sách thành công.");
    return "redirect:/books";
}
~~~

`BindingResult` phải đứng ngay sau tham số được binding và kiểm tra (`form`) để Spring cung cấp lỗi cho đúng đối tượng. Nếu bỏ qua hoặc đặt sai vị trí, lỗi binding/validation có thể được ném ra thay vì cho phép Controller trả lại biểu mẫu.

Ví dụ trên giả định phương thức nằm trong `BookController` có `bookService` được tiêm qua constructor. Trong trường hợp có dữ liệu phụ như danh sách thể loại, Controller cần nạp lại dữ liệu đó trước khi trả về `books/form`; các thuộc tính chỉ có trong GET không tự động tồn tại trong POST.

## 7. Validation và hiển thị lại lỗi

Khi binding hoàn tất, Bean Validation kiểm tra các constraint đã khai báo trên Form DTO. Nếu một hoặc nhiều constraint không đạt, `BindingResult` chứa lỗi theo trường và Controller trả lại template biểu mẫu.

Việc trả lại View trực tiếp rất quan trọng: đối tượng form và `BindingResult` vẫn có trong model của request hiện tại, giúp Thymeleaf hiển thị giá trị người dùng đã nhập cùng lỗi tương ứng.

Không redirect ngay khi validation thất bại. Redirect tạo request mới, vì vậy `BindingResult` của request POST không còn sẵn để template hiển thị. Với lỗi validation, thông thường trả lại cùng View; với thao tác thành công, dùng redirect theo PRG.

### Phân biệt lỗi binding và lỗi validation

| Loại lỗi | Ví dụ | Cách phản hồi |
|---|---|---|
| Binding/conversion | Chuỗi ngày không chuyển được thành `LocalDate`; UUID sai định dạng | Nêu trường có dữ liệu sai định dạng và yêu cầu nhập lại |
| Validation | Tiêu đề rỗng; tên tác giả vượt độ dài | Hiển thị lỗi gắn với trường tương ứng |
| Nghiệp vụ | ISBN đã thuộc về một sách khác; trạng thái không cho phép cập nhật | Hiển thị thông báo nghiệp vụ phù hợp, có thể gắn vào trường hoặc lỗi chung |
| Hệ thống | Database hoặc dịch vụ phụ thuộc không khả dụng | Trả lỗi hệ thống an toàn và ghi log để điều tra |

Không nên biến lỗi hệ thống thành lỗi validation hoặc danh sách rỗng. Người dùng không thể sửa dữ liệu để khắc phục một sự cố kết nối cơ sở dữ liệu.

### Thêm lỗi nghiệp vụ vào biểu mẫu

Giả sử ISBN phải duy nhất. Form có thể hợp lệ về cấu trúc nhưng Service phát hiện ISBN đã tồn tại. Controller có thể gắn lỗi nghiệp vụ vào trường ISBN:

~~~java
try {
    bookService.create(form);
} catch (DuplicateIsbnException exception) {
    bindingResult.rejectValue(
            "isbn",
            "book.isbn.duplicate",
            "ISBN này đã được sử dụng.");
    return "books/form";
}

redirectAttributes.addFlashAttribute(
        "successMessage", "Đã tạo sách thành công.");
return "redirect:/books";
~~~

Đoạn này là phần xử lý bổ sung trong action POST sau khi kiểm tra `bindingResult.hasErrors()`. Cần bảo đảm `DuplicateIsbnException` là lỗi nghiệp vụ đã được định nghĩa và chỉ bắt lỗi có thể phục hồi theo biểu mẫu. Không bắt `Exception` chung rồi hiển thị như lỗi ISBN.

Việc kiểm tra trùng trước khi lưu giúp tạo thông báo thân thiện, nhưng không đủ để bảo vệ tính duy nhất khi có request đồng thời. Service và cơ sở dữ liệu vẫn cần transaction và unique constraint; lỗi vi phạm constraint cần được ánh xạ thành lỗi nghiệp vụ phù hợp.

## 8. Ràng buộc trường được phép bind và chống over-posting

Không nên binding trực tiếp request vào Domain Entity có nhiều thuộc tính. Người dùng có thể thêm tham số mà giao diện không hiển thị, chẳng hạn `status=APPROVED`, `createdBy=admin` hoặc `role=MANAGER`. Nếu binder cập nhật các thuộc tính đó, đây là một dạng over-posting/mass assignment.

Cách phòng tránh chính là dùng Form DTO chỉ chứa các trường được phép nhận. Với Spring MVC, có thể giới hạn thêm thuộc tính được binding bằng `@InitBinder`:

~~~java
@InitBinder("form")
public void configureFormBinder(WebDataBinder binder) {
    binder.setAllowedFields(
            "title",
            "authorName",
            "isbn",
            "publishedDate");
}
~~~

Allowlist cần khớp với tên thuộc tính của Form DTO. Nếu request gửi thêm trường ngoài danh sách, binder sẽ không bind trường đó. Đây là lớp phòng vệ bổ sung; DTO riêng và kiểm tra quyền ở Service vẫn cần thiết.

Không dùng dữ liệu do client gửi để quyết định danh tính người tạo, quyền sở hữu, trạng thái phê duyệt hoặc các giá trị chỉ máy chủ được phép xác định. Những trường đó cần lấy từ security context hoặc quy tắc nghiệp vụ.

## 9. Bảo vệ biểu mẫu và request

Form HTML thường gửi dữ liệu bằng GET hoặc POST. Chọn method theo mục đích:

- **GET** phù hợp với tìm kiếm, lọc và truy vấn không làm thay đổi trạng thái. Dữ liệu xuất hiện trong URL nên không gửi mật khẩu hoặc thông tin nhạy cảm qua query string.
- **POST** phù hợp với thao tác tạo hoặc thay đổi trạng thái. Không dùng GET để thực hiện hành động có tác động nghiệp vụ.

Với ứng dụng dùng cookie/session authentication, biểu mẫu POST cần được bảo vệ khỏi Cross-Site Request Forgery (CSRF). Spring Security thường bật CSRF protection cho các request thay đổi trạng thái và cung cấp token để đưa vào biểu mẫu. Khi dùng tích hợp Thymeleaf–Spring Security thông dụng, token có thể được thêm tự động cho form có `th:action`; nếu không có cơ chế tự động, cần đưa token vào hidden field theo cấu hình của ứng dụng.

~~~html
<input type="hidden"
       th:if="${_csrf != null}"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}" />
~~~

Chỉ dùng một cơ chế đưa token phù hợp với cấu hình để tránh gửi trường token trùng lặp. Không tắt CSRF chỉ để làm biểu mẫu hoạt động trong môi trường có session cookie; hãy kiểm tra token và cấu hình bảo mật.

Validation cũng không thay thế xác thực và phân quyền. Controller hoặc security layer phải kiểm tra người dùng đã đăng nhập và có quyền tạo/sửa tài nguyên. Việc ẩn nút gửi trên View không ngăn được request trực tiếp.

## 10. Sau khi thành công: Post/Redirect/Get

Nếu POST thành công và server trả thẳng HTML, người dùng tải lại trang có thể khiến trình duyệt hỏi gửi lại request POST. Mẫu **Post/Redirect/Get (PRG)** giải quyết vấn đề này:

1. Browser gửi POST để thực hiện hành động.
2. Server xử lý thành công và trả response redirect, thường là `302` hoặc `303` tùy cấu hình.
3. Browser gửi GET đến URL đích.
4. Server trả trang kết quả; tải lại trang chỉ lặp GET.

Trong Spring MVC, Controller có thể thêm thông báo ngắn hạn qua `RedirectAttributes.addFlashAttribute` rồi trả `redirect:/books`. Flash attribute được chuyển qua request kế tiếp và thường chỉ dùng một lần.

Không nên dùng redirect để giữ toàn bộ Form DTO hoặc dữ liệu nhạy cảm trong URL. Nếu cần lưu tiến trình nhiều bước, hãy thiết kế trạng thái server-side với vòng đời và quyền truy cập rõ ràng.

## 11. Biểu mẫu nhiều loại trường

HTML cung cấp nhiều loại input và mỗi loại có quy tắc binding riêng:

| Loại trường | Giá trị thường gửi | Lưu ý khi binding |
|---|---|---|
| `text` / `email` | Chuỗi | Kiểm tra rỗng, độ dài, định dạng và chuẩn hóa phù hợp |
| `number` | Chuỗi biểu diễn số | Chuyển sang kiểu số; kiểm tra min/max và độ chính xác |
| `date` | `yyyy-MM-dd` | Dùng `LocalDate` và cấu hình format phù hợp |
| `checkbox` | Giá trị khi được chọn; có thể không gửi tham số khi bỏ chọn | Xác định rõ quy ước false khi không có tham số |
| `select` | Giá trị option | Kiểm tra giá trị có thuộc tập lựa chọn hợp lệ ở phía server |
| `file` | Multipart part | Kiểm tra kích thước, loại nội dung thực tế, tên file và quyền lưu |

Đặc biệt, không tin giá trị option chỉ vì nó được tạo từ danh sách mà View đã hiển thị. Client có thể tự gửi một ID không tồn tại hoặc không được phép chọn; Service cần xác minh giá trị đó theo dữ liệu và quyền hiện tại.

Với checkbox, một số cấu hình Spring/Thymeleaf tạo hidden field để gửi giá trị false khi checkbox không được chọn. Cần hiểu cấu trúc request thực tế của template và binder để tránh nhầm “không có tham số” với “false”.

Với upload file, endpoint cần nhận `MultipartFile`, giới hạn kích thước ở cả web server và ứng dụng, kiểm tra loại nội dung bằng cách phù hợp, tạo tên lưu trữ do server kiểm soát và không lưu file tải lên vào vị trí có thể thực thi trực tiếp. Không dựa riêng vào phần mở rộng hoặc `Content-Type` do client khai báo.

## 12. Biểu mẫu chỉnh sửa và giá trị ban đầu

Biểu mẫu chỉnh sửa có thêm bước tải dữ liệu hiện tại. Controller lấy sách theo ID, chuyển sang Form DTO và render template. Khi POST, ID hoặc định danh tài nguyên phải được xác định theo route và kiểm tra quyền; không tin một ID ẩn trong form như bằng chứng người dùng được phép sửa.

~~~java
@GetMapping("/{id}/edit")
public String showEditForm(@PathVariable UUID id, Model model) {
    Book book = bookService.getBook(new BookId(id));
    model.addAttribute("form", bookFormMapper.toForm(book));
    model.addAttribute("bookId", id);
    return "books/form";
}

@PostMapping("/{id}")
public String update(
        @PathVariable UUID id,
        @Valid @ModelAttribute("form") UpdateBookForm form,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "books/form";
    }

    bookService.update(new BookId(id), form);
    return "redirect:/books/" + id;
}
~~~

Đây là ví dụ khái niệm; cần nạp lại dữ liệu phụ của form khi có lỗi và kiểm tra quyền cập nhật trong Service hoặc tầng bảo mật. Tách `CreateBookForm` và `UpdateBookForm` nếu hai use case có tập trường được phép thay đổi khác nhau.

## 13. Những lỗi thường gặp trong vòng đời biểu mẫu

- **Dùng Entity làm đối tượng form:** có thể cho phép binding các trường nội bộ ngoài dự kiến.
- **Chỉ kiểm tra ở trình duyệt:** request có thể được gửi trực tiếp và bỏ qua validation phía client.
- **Đặt `BindingResult` sai vị trí:** Controller không nhận được lỗi gắn với đúng Form DTO.
- **Redirect khi validation thất bại:** làm mất lỗi và giá trị binding của request hiện tại.
- **Không nạp lại dữ liệu phụ:** danh sách option hoặc dữ liệu điều hướng biến mất khi trả lại form lỗi.
- **Nhầm lỗi binding với lỗi nghiệp vụ:** chuỗi ngày sai định dạng khác với ISBN đã tồn tại.
- **Dùng GET để thay đổi dữ liệu:** có thể bị kích hoạt ngoài ý muốn qua link, prefetch hoặc cache.
- **Không bảo vệ CSRF:** request POST dùng session cookie có thể bị giả mạo từ site khác.
- **Tin các trường ẩn hoặc option do client gửi:** hidden field và select không phải ranh giới bảo mật.
- **Không dùng PRG sau thành công:** tải lại trang có thể gửi lại thao tác POST.
- **Hiển thị exception kỹ thuật:** làm lộ cấu trúc nội bộ và không giúp người dùng sửa dữ liệu.

## 14. Kiểm thử vòng đời biểu mẫu

Kiểm thử cần đi qua cả request hiển thị và request tiếp nhận, thay vì chỉ kiểm tra một phương thức Controller.

| Ca kiểm thử | Điều cần xác minh |
|---|---|
| GET tạo mới | Trả đúng View và có Form DTO rỗng với dữ liệu phụ cần thiết |
| POST hợp lệ | Binding đúng kiểu, Service được gọi, response redirect theo PRG |
| Trường bắt buộc bị bỏ trống | Trả lại form, lỗi xuất hiện đúng trường, Service không được gọi |
| Giá trị sai định dạng | Binding error được hiển thị và không gọi nghiệp vụ |
| Lỗi nghiệp vụ có thể khắc phục | Gắn lỗi vào trường hoặc lỗi chung và giữ dữ liệu người dùng |
| Trường ngoài allowlist | Không được bind vào DTO |
| Thiếu hoặc sai CSRF token | Request bị từ chối theo cấu hình bảo mật |
| Người dùng thiếu quyền | Server từ chối dù request được gửi trực tiếp |
| POST thành công rồi tải lại GET | Không lặp lại thao tác tạo dữ liệu |
| Form chỉnh sửa | Giá trị ban đầu đúng và chỉ trường được phép thay đổi |

Với Spring MVC, `MockMvc` có thể gửi GET/POST, kiểm tra view name, model attributes, `BindingResult`, status và redirect. Unit test cho Service xác minh quy tắc nghiệp vụ. Integration test cần xác minh CSRF filter, binder, template engine và transaction trong cấu hình gần thực tế.

## 15. Kết luận

Vòng đời biểu mẫu bắt đầu khi Controller chuẩn bị Form DTO và View render các trường nhập liệu. Khi người dùng gửi form, Spring MVC binding request vào DTO, chuyển đổi kiểu và chạy validation. Controller chỉ gọi Service khi dữ liệu đầu vào vượt qua các kiểm tra phù hợp; nếu có lỗi, ứng dụng trả lại biểu mẫu với giá trị và thông báo để người dùng sửa. Khi thao tác thành công, PRG và flash attributes tạo luồng phản hồi rõ ràng.

Khi thiết kế form trong MVC, hãy xác định hợp đồng đầu vào, trường nào được phép bind, lỗi thuộc binding, validation hay nghiệp vụ, dữ liệu nào cần nạp lại khi render và request cần được bảo vệ ra sao. Làm rõ từng bước giúp biểu mẫu dễ dùng, an toàn và giữ được tính nhất quán của miền nghiệp vụ.
