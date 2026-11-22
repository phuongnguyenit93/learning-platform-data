# Chuyển một luồng MVC tương tác sang luồng MVC trên web

Trong bài thực hành này, bạn sẽ chuyển luồng **thêm một cuốn sách** từ giao diện desktop Java Swing sang ứng dụng web dùng Spring MVC và Thymeleaf. Mục tiêu là giữ nguyên quy tắc nghiệp vụ và use case hiện có, đồng thời thay cách nhận tương tác và trình bày dữ liệu cho phù hợp với HTTP và trình duyệt.

Đây là bài thực hành về kiến trúc MVC, không phải bài dựng lại toàn bộ hệ thống quản lý thư viện. Bạn sẽ làm việc với một luồng hoàn chỉnh: mở biểu mẫu, nhập dữ liệu, gửi request, kiểm tra đầu vào, áp dụng quy tắc nghiệp vụ, lưu sách, hiển thị lỗi hoặc chuyển đến trang chi tiết.

Sau bài này, bạn cần có khả năng:

- nhận diện phần nào của ứng dụng desktop có thể giữ lại khi chuyển sang web;
- thiết kế ranh giới giữa Web Controller, Form DTO, Application Service, Domain Model và Repository;
- ánh xạ sự kiện giao diện thành HTTP GET/POST;
- xử lý binding, Bean Validation và lỗi nghiệp vụ;
- trả lại biểu mẫu mà vẫn giữ dữ liệu người dùng đã nhập;
- dùng Post/Redirect/Get sau khi lưu thành công;
- bảo vệ form bằng authentication, authorization và CSRF;
- kiểm thử Controller và use case ở các ranh giới phù hợp.

## Bối cảnh và yêu cầu bài toán

Giả sử ứng dụng desktop quản lý thư viện đã có màn hình thêm sách. Người dùng nhập tiêu đề, tác giả, ISBN, ngày xuất bản và thể loại, sau đó nhấn nút **Lưu**. Controller desktop nhận sự kiện, gọi use case `CreateBook`, rồi hiển thị kết quả bằng thông báo hoặc cập nhật danh sách.

Bạn được giao chuyển luồng này sang ứng dụng web. Người dùng sẽ mở `/books/new`, nhập dữ liệu trên trình duyệt và gửi `POST /books`. Ứng dụng phải kiểm tra dữ liệu, tạo sách và đưa người dùng đến trang chi tiết nếu thành công.

### Quy tắc nghiệp vụ của bài thực hành

Áp dụng các quy tắc sau trong suốt bài:

1. Tiêu đề và tên tác giả không được để trống.
2. Tiêu đề tối đa 200 ký tự; tên tác giả tối đa 120 ký tự.
3. ISBN phải được chuẩn hóa và có checksum hợp lệ theo chuẩn ISBN-10 hoặc ISBN-13 mà ứng dụng hỗ trợ.
4. ISBN không được trùng với một cuốn sách khác.
5. Ngày xuất bản không được ở tương lai.
6. Thể loại phải tồn tại và đang hoạt động.
7. Người dùng phải đăng nhập và có quyền thêm sách trong phạm vi thư viện của mình.
8. `createdBy`, `ownerId`, trạng thái kiểm duyệt và metadata tạo bản ghi do server xác định; trình duyệt không được tự quyết định các giá trị này.

Quy tắc 1, 2 và một phần quy tắc 5 có thể kiểm tra ở Form DTO để phản hồi sớm. Quy tắc ISBN, thể loại, quyền và tính duy nhất vẫn phải được xác minh ở use case/domain/persistence vì chúng phụ thuộc dữ liệu và trạng thái hiện tại.

## Phần nào được giữ lại, phần nào cần thay?

Khi chuyển giao diện desktop sang web, không nên chuyển nguyên `JFrame`, `JPanel` hoặc `ActionListener` vào Controller web. Hãy giữ lại phần nghiệp vụ độc lập với giao diện và thay adapter nhận/trả tương tác.

| Thành phần desktop hiện tại | Cách chuyển sang web | Lý do |
|---|---|---|
| `Book` và `Isbn` | Giữ Domain Model nếu không phụ thuộc Swing | Quy tắc sách không phụ thuộc loại giao diện |
| `CreateBookService` / `CreateBookUseCase` | Giữ hợp đồng use case | Cùng hành động tạo sách có thể được gọi từ desktop, web hoặc API |
| `BookRepository` | Giữ port; tái sử dụng adapter nếu phù hợp | Persistence không nên phụ thuộc giao diện |
| `JTextField` và `JComboBox` | Thay bằng HTML input/select và `BookForm` | Trình duyệt gửi dữ liệu qua HTTP |
| `ActionListener` của nút Lưu | Thay bằng route `POST /books` và method Controller | HTTP request là điểm vào của tương tác web |
| `JOptionPane` báo lỗi | Thay bằng field error, global error hoặc trang lỗi | Lỗi cần được gắn với hợp đồng form/HTTP |
| `JTable` hoặc danh sách desktop | Thay bằng View Model và template HTML | View web chỉ render dữ liệu được chuẩn bị |
| Trạng thái component trong cửa sổ | Dùng URL, request model, flash attribute hoặc state client phù hợp | Vòng đời request web khác vòng đời cửa sổ desktop |

Quy tắc nghiệp vụ không được chuyển vào JavaScript hoặc Controller chỉ vì giao diện đã đổi. Web Controller là adapter mới của cùng use case.

## Kiến trúc đích

Luồng web sau khi chuyển đổi:

```mermaid
flowchart TD
    A[Browser: HTML Form] -->|GET /books/new| B[Spring Security]
    B --> C[DispatcherServlet]
    C --> D[BookWebController]
    D --> E[BookForm + Reference Data]
    E --> F[Thymeleaf View]
    F --> A
    A -->|POST /books + CSRF| B
    B --> C
    C --> D
    D --> G[Binding + Bean Validation]
    G -->|Invalid| F
    G -->|Valid| H[CreateBookUseCase]
    H --> I[Book Domain Model]
    H --> J[BookRepository]
    J --> K[(Database)]
    K --> J
    H --> L[BookId / Result]
    L --> D
    D -->|Redirect /books/{id}| A
```

Trong sơ đồ, `BookForm` là hợp đồng đầu vào của giao diện web; nó không phải Domain Model. `CreateBookUseCase` vẫn chịu trách nhiệm điều phối nghiệp vụ. `BookRepository` thực hiện lưu trữ. Thymeleaf chỉ trình bày dữ liệu và lỗi.

### Các route cần hoàn thành

| HTTP method | URL | Mục đích | Kết quả |
|---|---|---|---|
| GET | `/books/new` | Hiển thị form thêm sách | View `books/form` |
| POST | `/books` | Kiểm tra và tạo sách | Render lại form nếu lỗi; redirect nếu thành công |
| GET | `/books/{id}` | Hiển thị chi tiết sách | View `books/detail` |

Không dùng GET để tạo hoặc thay đổi dữ liệu. GET phải an toàn và có thể được trình duyệt, proxy hoặc crawler gọi lại mà không tạo tác dụng phụ.

## Chuẩn bị hợp đồng ứng dụng

Trước khi viết Controller, xác định use case và các port mà nó cần. Bạn có thể đã có những kiểu tương đương trong ứng dụng desktop; hãy dùng lại hợp đồng phù hợp thay vì tạo một bản nghiệp vụ riêng cho web.

### Command và use case

```java
public record CreateBookCommand(
        String title,
        String author,
        String isbn,
        LocalDate publishedOn,
        CategoryId categoryId,
        UserId actorId) {
}
```

```java
public interface CreateBookUseCase {
    BookId handle(CreateBookCommand command);
}
```

`actorId` được lấy từ danh tính đã xác thực ở server, không lấy từ một input ẩn do browser gửi. Nếu use case hiện tại đã nhận `ActorContext` hoặc principal abstraction, hãy dùng đúng hợp đồng hiện có.

### Repository và lỗi nghiệp vụ

```java
public interface BookRepository {
    boolean existsByIsbn(Isbn isbn);
    Book save(Book book);
}

public interface CategoryRepository {
    Optional<Category> findActiveById(CategoryId id);
}
```

Use case cần phân biệt ít nhất các kết quả nghiệp vụ sau:

| Lỗi nghiệp vụ | Ý nghĩa | Cách giao diện có thể phản hồi |
|---|---|---|
| `DuplicateIsbnException` | ISBN đã được dùng | Gắn lỗi vào trường ISBN |
| `InactiveCategoryException` | Thể loại không còn được phép chọn | Gắn lỗi vào trường thể loại hoặc toàn form |
| `BookPermissionDeniedException` | Người dùng không có quyền tạo sách trong phạm vi này | Trả trang/response từ chối truy cập |
| `InvalidIsbnException` | ISBN không đạt quy tắc miền | Gắn lỗi vào trường ISBN |

Lỗi database, timeout hoặc lỗi lập trình không phải lỗi nhập liệu. Chúng cần được ghi nhận và xử lý ở ranh giới lỗi kỹ thuật.

### Việc cần làm 1

Mở use case đang được Controller desktop gọi và trả lời:

1. Use case nhận những dữ liệu nào?
2. Dữ liệu nào phải lấy từ danh tính/ngữ cảnh server?
3. Quy tắc nào đang nằm trong Domain Model?
4. Repository đang cung cấp những thao tác nào?
5. Use case đang phát sinh những lỗi nghiệp vụ nào?

Ghi câu trả lời vào ghi chú thiết kế của bạn. Không bắt đầu bằng cách sao chép logic từ `ActionListener` sang method Controller.

## Bước 1: Tạo Form DTO cho giao diện web

Tạo `BookForm` trong package web adapter, ví dụ `ui.web.book`. Chỉ đưa vào những trường mà người dùng được phép nhập.

```java
public class BookForm {
    @NotBlank(message = "Tiêu đề là bắt buộc")
    @Size(max = 200, message = "Tiêu đề không được vượt quá 200 ký tự")
    private String title;

    @NotBlank(message = "Tên tác giả là bắt buộc")
    @Size(max = 120, message = "Tên tác giả không được vượt quá 120 ký tự")
    private String author;

    @NotBlank(message = "ISBN là bắt buộc")
    @Size(max = 17, message = "ISBN không được vượt quá 17 ký tự")
    private String isbn;

    @NotNull(message = "Ngày xuất bản là bắt buộc")
    @PastOrPresent(message = "Ngày xuất bản không được ở tương lai")
    private LocalDate publishedOn;

    @NotNull(message = "Vui lòng chọn thể loại")
    private Long categoryId;

    // Bổ sung getter và setter theo JavaBean.
}
```

Các annotation ở ví dụ dùng Jakarta Bean Validation trong Spring Boot 3. Với Spring Boot 2, package có thể là `javax.validation`. Thêm dependency validation tương ứng nếu dự án chưa có.

`BookForm` không có `id`, `ownerId`, `createdBy`, `status`, `version` hoặc `approved`. Các giá trị đó do server/use case quản lý. Nếu màn hình chỉnh sửa cần ID, lấy ID từ path và xác minh quyền trên tài nguyên; không bind ID từ form rồi tin nó.

### Kiểm tra ISBN

`@Size` chỉ kiểm tra độ dài. Có thể thêm một custom constraint hoặc kiểm tra qua `Isbn.parse()` trong use case để xác minh checksum và chuẩn hóa ISBN. Đừng dùng một regex ký tự đơn giản rồi coi ISBN đã hợp lệ.

Nếu Form DTO có `@Pattern` để từ chối ký tự không hợp lệ, hãy giữ cùng quy tắc ở Domain Model. Client validation có thể bổ sung phản hồi nhanh nhưng server vẫn là nơi quyết định cuối cùng.

### Việc cần làm 2

- Tạo `BookForm` với các trường trên.
- Bổ sung getter/setter hoặc constructor phù hợp với data binder của Spring MVC.
- Thêm validation cho trường bắt buộc, độ dài và ngày xuất bản.
- Viết test để chứng minh form không nhận các trường nội bộ như `ownerId` và `createdBy`.
- Kiểm tra rằng lỗi binding ngày không hợp lệ được ghi nhận trong `BindingResult`.

## Bước 2: Tạo Web Controller

Controller web không kế thừa Controller Swing và không truy cập repository trực tiếp. Nó nhận request, chuẩn bị dữ liệu cho View, chuyển Form DTO thành command, gọi use case và chọn response.

```java
@Controller
@RequestMapping("/books")
public class BookWebController {
    private final CreateBookUseCase createBook;
    private final ListActiveCategoriesQuery listCategories;

    public BookWebController(
            CreateBookUseCase createBook,
            ListActiveCategoriesQuery listCategories) {
        this.createBook = createBook;
        this.listCategories = listCategories;
    }

    @GetMapping("/new")
    public String newForm(
            @AuthenticationPrincipal AppPrincipal principal,
            Model model) {
        model.addAttribute("bookForm", new BookForm());
        addReferenceData(principal, model);
        return "books/form";
    }

    private void addReferenceData(AppPrincipal principal, Model model) {
        model.addAttribute(
                "categories", listCategories.handle(principal.userId()));
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("bookForm") BookForm form,
            BindingResult bindingResult,
            @AuthenticationPrincipal AppPrincipal principal,
            Model model,
            RedirectAttributes redirectAttributes) {

        if (bindingResult.hasErrors()) {
            addReferenceData(principal, model);
            return "books/form";
        }

        try {
            BookId id = createBook.handle(new CreateBookCommand(
                    form.getTitle(),
                    form.getAuthor(),
                    form.getIsbn(),
                    form.getPublishedOn(),
                    new CategoryId(form.getCategoryId()),
                    principal.userId()));

            redirectAttributes.addFlashAttribute(
                    "successMessage", "Đã thêm sách thành công.");
            return "redirect:/books/" + id.value();
        } catch (DuplicateIsbnException ex) {
            bindingResult.rejectValue(
                    "isbn", "book.isbn.duplicate",
                    "ISBN này đã được sử dụng.");
            addReferenceData(principal, model);
            return "books/form";
        }
    }
}
```

Đây là skeleton để bạn hoàn thiện; các kiểu `AppPrincipal`, `CategoryId`, command, query và exception phải khớp ứng dụng. Tham số `BindingResult` đặt ngay sau đối tượng có `@Valid`. Nếu đặt sai vị trí, Spring không gắn lỗi vào đúng form object.

Controller chỉ bắt lỗi nghiệp vụ đã biết và có thể sửa trên form. Không bắt mọi `RuntimeException` rồi hiển thị thành lỗi ISBN. Với lỗi kỹ thuật, để exception đi đến handler tập trung.

### Lưu ý về transaction và unique constraint

Use case cần kiểm tra ISBN trùng để trả lỗi sớm, nhưng database vẫn phải có unique constraint trên ISBN đã chuẩn hóa để chống hai request đồng thời cùng tạo một ISBN. Persistence adapter phải ánh xạ đúng unique constraint thành lỗi nghiệp vụ.

Với JPA, constraint có thể chỉ bị phát hiện khi flush hoặc commit. Nếu exception chỉ xuất hiện lúc transaction commit sau khi method use case trả về, `catch` bên trong Controller có thể không bắt được tại vị trí dự kiến. Hãy đặt việc chuyển constraint cụ thể thành `DuplicateIsbnException` ở ranh giới transaction/persistence phù hợp; không chuyển mọi lỗi integrity thành lỗi ISBN.

### Việc cần làm 3

- Tạo `BookWebController` với GET `/books/new` và POST `/books`.
- Inject use case và query lấy thể loại qua constructor.
- Lấy actor từ `AppPrincipal`.
- Nếu binding/validation lỗi, nạp lại thể loại và render form.
- Nếu ISBN trùng, thêm field error vào `isbn` và render lại form.
- Nếu thành công, redirect đến `/books/{id}` và thêm flash message.
- Không đưa repository hoặc entity JPA vào Controller.

## Bước 3: Tạo View Thymeleaf

Tạo template `templates/books/form.html`. Template nhận `bookForm` và `categories`; nó không truy vấn database hoặc gọi use case.

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thêm sách</title>
</head>
<body>
  <main>
    <h1>Thêm sách</h1>

    <form th:action="@{/books}" th:object="${bookForm}" method="post">
      <div>
        <label for="title">Tiêu đề</label>
        <input id="title" type="text" th:field="*{title}"
               th:attr="aria-invalid=${#fields.hasErrors('title')}"
               aria-describedby="title-error">
        <p id="title-error" th:if="${#fields.hasErrors('title')}"
           th:errors="*{title}"></p>
      </div>

      <div>
        <label for="author">Tác giả</label>
        <input id="author" type="text" th:field="*{author}"
               th:attr="aria-invalid=${#fields.hasErrors('author')}"
               aria-describedby="author-error">
        <p id="author-error" th:if="${#fields.hasErrors('author')}"
           th:errors="*{author}"></p>
      </div>

      <div>
        <label for="isbn">ISBN</label>
        <input id="isbn" type="text" th:field="*{isbn}"
               th:attr="aria-invalid=${#fields.hasErrors('isbn')}"
               aria-describedby="isbn-error">
        <p id="isbn-error" th:if="${#fields.hasErrors('isbn')}"
           th:errors="*{isbn}"></p>
      </div>

      <div>
        <label for="publishedOn">Ngày xuất bản</label>
        <input id="publishedOn" type="date" th:field="*{publishedOn}"
               th:attr="aria-invalid=${#fields.hasErrors('publishedOn')}"
               aria-describedby="publishedOn-error">
        <p id="publishedOn-error"
           th:if="${#fields.hasErrors('publishedOn')}"
           th:errors="*{publishedOn}"></p>
      </div>

      <div>
        <label for="categoryId">Thể loại</label>
        <select id="categoryId" th:field="*{categoryId}"
                th:attr="aria-invalid=${#fields.hasErrors('categoryId')}"
                aria-describedby="categoryId-error">
          <option value="">-- Chọn thể loại --</option>
          <option th:each="category : ${categories}"
                  th:value="${category.id}"
                  th:text="${category.name}"></option>
        </select>
        <p id="categoryId-error"
           th:if="${#fields.hasErrors('categoryId')}"
           th:errors="*{categoryId}"></p>
      </div>

      <div th:if="${#fields.hasGlobalErrors()}">
        <p th:each="error : ${#fields.globalErrors()}"
           th:text="${error}"></p>
      </div>

      <button type="submit">Lưu sách</button>
      <a th:href="@{/books}">Hủy</a>
    </form>
  </main>
</body>
</html>
```

Khi Spring Security và Thymeleaf được tích hợp qua `RequestDataValueProcessor`, `th:action` cho form POST sẽ tự thêm CSRF hidden field. Nếu dự án không có cơ chế tích hợp này, thêm token theo request attribute `_csrf` phù hợp cấu hình. Không thêm cả hai cách cùng lúc.

`th:field` liên kết input với Form DTO và giữ lại giá trị đã bind khi render lại form. `th:errors` hiển thị lỗi trường. `th:text` escape thông báo theo ngữ cảnh text; không dùng HTML thô cho nội dung do người dùng hoặc exception cung cấp.

### Việc cần làm 4

- Tạo `books/form.html` với đủ năm trường.
- Hiển thị lỗi cạnh trường tương ứng.
- Hiển thị lỗi toàn form nếu có.
- Giữ label liên kết với input và thêm `aria-invalid`/`aria-describedby` khi phù hợp.
- Xác minh HTML cuối cùng có CSRF token đúng một lần khi Spring Security bật.
- Không dùng JavaScript làm nơi xác minh cuối cùng cho quy tắc nghiệp vụ.

## Bước 4: Bảo vệ route và form

Với form dùng session cookie, bật CSRF protection. Spring Security bật CSRF mặc định trong cấu hình thông thường; không tắt chỉ vì request là form HTML hoặc API JSON.

Ví dụ cấu hình rút gọn Spring Security 6:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/css/**", "/images/**").permitAll()
                    .requestMatchers("/books/**").authenticated()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Ví dụ giữ CSRF ở trạng thái bật mặc định. Trong ứng dụng thật, quyền tạo sách nên được kiểm tra theo policy cụ thể, ví dụ `BOOK_CREATE` trong tenant/thư viện của actor. `authenticated()` chỉ xác nhận người dùng đã đăng nhập; nó không tự chứng minh người đó có quyền tạo sách.

Use case phải xác minh quyền và category thuộc phạm vi người dùng được phép. Ẩn nút hoặc chỉ đưa category được phép vào dropdown là chưa đủ vì request có thể được tạo thủ công.

### Việc cần làm 5

- Yêu cầu đăng nhập với `/books/**`.
- Giữ CSRF protection cho POST.
- Kiểm tra quyền tạo sách ở use case/policy.
- Lấy actor từ principal đã xác thực.
- Kiểm tra `categoryId` thuộc phạm vi người dùng được phép.
- Thử gửi POST thiếu CSRF token và xác minh request bị từ chối.

## Bước 5: Xử lý lỗi kỹ thuật riêng với lỗi biểu mẫu

Không phải mọi lỗi đều nên render lại `books/form`. Ví dụ:

- tiêu đề rỗng: validation error, trả form với lỗi `title`;
- ISBN trùng: business rejection, trả form với lỗi `isbn`;
- category đã ngừng hoạt động: business rejection, trả form với lỗi `categoryId`;
- database timeout: technical error, trả trang lỗi dịch vụ;
- chưa đăng nhập: security flow chuyển đến login hoặc trả 401;
- không đủ quyền: trả 403 hoặc trang từ chối truy cập.

Một `@ControllerAdvice` có thể ánh xạ lỗi kỹ thuật thành trang lỗi chung:

```java
@ControllerAdvice
public class WebExceptionHandler {
    @ExceptionHandler(BookStorageUnavailableException.class)
    public ModelAndView storageUnavailable() {
        ModelAndView view = new ModelAndView("errors/service-unavailable");
        view.setStatus(HttpStatus.SERVICE_UNAVAILABLE);
        view.addObject("message",
                "Dịch vụ lưu trữ tạm thời không khả dụng. Vui lòng thử lại sau.");
        return view;
    }
}
```

Handler thực tế cần ghi log exception phía server bằng logger/observability đã cấu hình. Không trả stack trace, câu SQL, tên bảng, hostname nội bộ hoặc credential cho browser.

### Việc cần làm 6

Tạo bảng ánh xạ lỗi cho luồng tạo sách. Với mỗi lỗi, xác định:

- lớp phát sinh lỗi;
- mã lỗi ổn định;
- lỗi gắn với field hay toàn form;
- HTTP status hoặc View cần trả;
- thông tin nào được phép hiển thị cho người dùng;
- thông tin nào chỉ được ghi log phía server.

Sau đó kiểm tra rằng Controller chỉ bắt lỗi nghiệp vụ có thể sửa trên form và lỗi kỹ thuật đi qua handler phù hợp.

## Bước 6: Hoàn thiện Post/Redirect/Get

Khi tạo sách thành công, Controller redirect đến trang chi tiết:

```text
POST /books
  -> CreateBookUseCase.handle(command)
  -> commit transaction
  -> redirect:/books/42

GET /books/42
  -> GetBookDetailsQuery.handle(42, actorId)
  -> render books/detail
```

Redirect giúp refresh trang kết quả thực hiện GET thay vì gửi lại POST. Dùng flash attribute để hiển thị thông báo thành công ở request kế tiếp.

PRG không tự ngăn hai POST xảy ra đồng thời hoặc client retry khi không biết request trước đã commit hay chưa. Với thao tác tạo có nguy cơ trùng, cân nhắc idempotency key hoặc quy tắc unique constraint phù hợp.

### Việc cần làm 7

- Tạo route GET `/books/{id}` và query trả DTO chi tiết.
- Sau khi lưu thành công, redirect đến route đó.
- Hiển thị flash message ở trang chi tiết.
- Refresh trang chi tiết và xác minh không tạo thêm bản ghi.
- Thử gửi hai request tạo cùng ISBN và xác minh database không lưu trùng.

## Bước 7: Kiểm thử từng ranh giới

Không cần kiểm thử mọi thứ qua browser. Mỗi lớp có một loại kiểm thử phù hợp.

| Lớp | Kiểm thử | Điều cần xác minh |
|---|---|---|
| Form DTO | Unit test validation | Tiêu đề rỗng, độ dài quá mức và ngày tương lai bị từ chối |
| Domain Model | Unit test | ISBN checksum, trạng thái sách và invariant |
| Application Service | Unit test với fake/mock repository | Quy tắc, quyền, kết quả và lỗi nghiệp vụ |
| Web Controller | MockMvc / `@WebMvcTest` | Binding, View, field error, redirect và gọi use case |
| Repository adapter | Integration test với database | Unique constraint, query, transaction và mapping |
| Browser | E2E test | Người dùng đi qua form, sửa lỗi và hoàn thành luồng |

### Kiểm thử form validation

Ví dụ kiểm thử POST có tiêu đề rỗng:

```java
mockMvc.perform(post("/books")
        .with(authentication(testAuthentication))
        .with(csrf())
        .param("title", "")
        .param("author", "Nguyễn An")
        .param("isbn", "9786041234567")
        .param("publishedOn", "2025-06-01")
        .param("categoryId", "3"))
    .andExpect(status().isOk())
    .andExpect(view().name("books/form"))
    .andExpect(model().attributeHasFieldErrors("bookForm", "title"));

verifyNoInteractions(createBook);
```

`testAuthentication` là Authentication chứa `AppPrincipal` thử nghiệm phù hợp với tham số `@AuthenticationPrincipal`; cấu hình test cần Spring Security MockMvc support. Nếu dự án dùng principal khác, hãy tạo test principal khớp cấu hình. Mục tiêu của test là chứng minh lỗi validation không gọi use case.

### Các test tối thiểu cần có

1. GET `/books/new` trả đúng View, có `bookForm` và danh sách thể loại.
2. POST thiếu tiêu đề trả lại form và có lỗi `title`.
3. POST có ngày sai định dạng trả lại form với lỗi binding.
4. POST ISBN trùng trả lại form với lỗi `isbn`.
5. POST category không hoạt động không tạo sách.
6. POST hợp lệ gọi use case với actor lấy từ principal và redirect đến `/books/{id}`.
7. POST thiếu CSRF token bị từ chối khi CSRF bật.
8. Người dùng không có quyền không thể tạo sách trong thư viện ngoài phạm vi.
9. Unique constraint ngăn hai request đồng thời tạo cùng ISBN.
10. Lỗi database được ánh xạ thành trang/response kỹ thuật, không thành field error.

## Bài tập thực hiện

Thực hiện các nhiệm vụ sau theo thứ tự. Đánh dấu từng mục sau khi hoàn thành trong repository hoặc ghi chú thực hành của bạn.

### Phần A — Khảo sát luồng desktop hiện có

- [ ] Tìm View desktop đang hiển thị form thêm sách.
- [ ] Xác định listener/Action đang nhận nút Lưu.
- [ ] Tìm use case/service mà listener gọi.
- [ ] Xác định Domain Model và Repository liên quan.
- [ ] Vẽ luồng hiện tại từ sự kiện người dùng đến kết quả.
- [ ] Ghi rõ logic nào đang nằm sai trong View hoặc Controller desktop.

### Phần B — Tạo adapter web

- [ ] Tạo `BookForm` và validation.
- [ ] Tạo `BookWebController` với GET `/books/new`.
- [ ] Tạo template `books/form.html`.
- [ ] Tạo POST `/books` và chuyển Form DTO thành command.
- [ ] Gọi lại use case hiện có.
- [ ] Không sao chép quy tắc nghiệp vụ vào Controller web.

### Phần C — Hoàn thiện lỗi và bảo mật

- [ ] Hiển thị lỗi binding/validation cạnh input.
- [ ] Hiển thị business rejection như ISBN trùng.
- [ ] Nạp lại dữ liệu thể loại trên mọi nhánh render form.
- [ ] Thêm CSRF token theo tích hợp Spring Security.
- [ ] Xác minh authentication và authorization phía server.
- [ ] Phân biệt lỗi kỹ thuật với lỗi người dùng.

### Phần D — Hoàn thiện và kiểm thử

- [ ] Dùng PRG sau khi tạo sách thành công.
- [ ] Tạo trang chi tiết sách.
- [ ] Viết unit test cho Form DTO và Domain Model.
- [ ] Viết MockMvc test cho các nhánh request.
- [ ] Viết repository integration test cho unique constraint.
- [ ] Chạy browser flow để xác minh trải nghiệm hoàn chỉnh.

## Tiêu chí nghiệm thu

Bài thực hành được xem là hoàn thành khi đáp ứng tất cả điều kiện sau:

| Nhóm | Điều kiện đạt |
|---|---|
| Kiến trúc | Controller web không phụ thuộc component Swing và không truy cập database trực tiếp |
| Tái sử dụng | Domain Model/use case/repository contract được dùng lại nếu không phụ thuộc UI; không sao chép quy tắc nghiệp vụ |
| Form contract | `BookForm` chỉ nhận các trường người dùng được phép nhập |
| Validation | Lỗi binding và validation được hiển thị đúng trường |
| Business rule | ISBN trùng và category không hoạt động được từ chối ở server |
| Persistence | Unique constraint bảo vệ ISBN trước request đồng thời |
| View | Giá trị đã nhập được giữ khi form lỗi; dropdown thể loại được nạp lại |
| HTTP | POST thành công redirect đến GET trang chi tiết |
| Security | CSRF, authentication và authorization được kiểm tra ở server |
| Error handling | Lỗi kỹ thuật không bị trình bày thành lỗi nhập liệu và không lộ chi tiết nội bộ |
| Testing | Có unit, controller và repository integration test cho các nhánh quan trọng |

## Gợi ý tổ chức package sau khi chuyển đổi

Một cách tổ chức tham khảo:

```text
com.example.library/
  domain/
    book/
      Book.java
      Isbn.java
      BookRepository.java
      DuplicateIsbnException.java
  application/
    book/
      CreateBookCommand.java
      CreateBookUseCase.java
      CreateBookService.java
      GetBookDetailsQuery.java
    category/
      ListActiveCategoriesQuery.java
  infrastructure/
    persistence/
      JpaBookRepositoryAdapter.java
      SpringDataBookRepository.java
  ui/
    web/
      book/
        BookWebController.java
        BookForm.java
        BookFormMapper.java
      error/
        WebExceptionHandler.java
  resources/
    templates/
      books/
        form.html
        detail.html
```

Đây là cấu trúc minh họa, không phải yêu cầu phải tạo đúng từng package. Hãy ưu tiên quy ước đang có của dự án và giữ dependency direction dễ hiểu.

## Mở rộng sau khi hoàn thành luồng cơ bản

Khi luồng tạo sách đã chạy, chọn một hoặc nhiều phần mở rộng:

### Mở rộng 1 — Chỉnh sửa sách

Thêm GET `/books/{id}/edit` và POST `/books/{id}`. Dùng `EditBookForm`, xác minh quyền trên sách, xử lý ISBN trùng nhưng loại trừ chính bản ghi đang sửa, và dùng `@Version` hoặc cơ chế tương đương để phát hiện cập nhật đồng thời.

### Mở rộng 2 — Trả lỗi bằng REST API

Tạo `POST /api/books` nhận JSON DTO. Dùng cùng `CreateBookUseCase`, nhưng trả response DTO hoặc `ProblemDetail`. Validation error có thể trả 400/422 theo hợp đồng; ISBN trùng có thể trả 409. Không tạo một bản sao use case chỉ vì adapter trả JSON.

### Mở rộng 3 — Tìm kiếm và phân trang

Thêm GET `/books?query=...&page=...`. Đưa tìm kiếm và phân trang vào Query Service/Repository; không tải toàn bộ sách rồi lọc trong template. Giới hạn page size và allowlist sort field.

### Mở rộng 4 — Kiểm thử cạnh tranh ISBN

Tạo hai request đồng thời cùng ISBN và xác minh chỉ một request tạo thành công. Request còn lại nhận lỗi nghiệp vụ đã được ánh xạ. Test này cần database thật tương thích với constraint và transaction semantics của môi trường triển khai.

## Những lỗi dễ mắc khi chuyển MVC desktop sang MVC web

- **Chuyển nguyên Controller desktop sang web:** listener và trạng thái component không tương ứng với vòng đời request. Thiết kế Controller web theo HTTP.
- **Đưa toàn bộ nghiệp vụ vào `@PostMapping`:** Controller phình to và không dùng lại được. Gọi use case hiện có.
- **Bind trực tiếp vào Domain Entity/JPA Entity:** có nguy cơ mass assignment và lộ field nội bộ. Dùng Form DTO.
- **Dùng session để lưu toàn bộ trạng thái form lâu dài:** tạo state khó đồng bộ và khó scale. Dùng request model/flash attribute cho mục đích ngắn hạn; dữ liệu bền vững nằm trong Model/persistence.
- **Dùng `JOptionPane` tương đương bằng một alert chung:** mất ngữ cảnh lỗi. Dùng field/global error hoặc trang lỗi phù hợp.
- **Quên nạp lại thể loại khi validation lỗi:** template thiếu dữ liệu tham chiếu. Nạp lại ở mọi nhánh trả form.
- **Redirect ngay khi validation lỗi:** dễ mất `BindingResult` và dữ liệu người dùng. Render lại form trong cùng request hoặc thiết kế cơ chế lưu lỗi rõ ràng.
- **Không dùng PRG sau thành công:** refresh có thể gửi lại POST. Redirect đến GET.
- **Tin client validation:** request có thể bỏ qua JavaScript. Server phải kiểm tra lại.
- **Tắt CSRF vì form đã có authentication:** session cookie vẫn có thể bị CSRF. Giữ cơ chế CSRF phù hợp.
- **Ẩn nút thay cho authorization:** endpoint vẫn có thể được gọi trực tiếp. Use case phải xác minh quyền.
- **Cho rằng kiểm tra ISBN trước khi lưu là đủ:** có race condition. Database cần unique constraint.
- **Catch mọi exception trong Controller:** lỗi kỹ thuật bị hiểu thành lỗi nhập liệu. Dùng exception mapping theo loại lỗi.
- **Kiểm thử chỉ bằng trình duyệt:** lỗi nghiệp vụ khó định vị. Bổ sung unit và integration test ở từng ranh giới.

## Tự đánh giá sau thực hành

Trả lời bằng lời của bạn, không chỉ chọn đúng thuật ngữ:

1. Vì sao có thể giữ lại Domain Model và use case khi chuyển từ Swing sang Spring MVC?
2. Vì sao `ActionListener` không được chuyển nguyên thành một object dùng chung trong Controller web?
3. `BookForm` khác `Book` ở trách nhiệm và vòng đời nào?
4. Dữ liệu actor nên lấy từ đâu và vì sao không nhận từ hidden input?
5. Khi validation lỗi, vì sao phải trả lại form cùng `BindingResult` và danh sách thể loại?
6. ISBN trùng là lỗi binding, validation đầu vào hay business rejection? Vì sao?
7. Vì sao cần unique constraint dù use case đã gọi `existsByIsbn()`?
8. PRG ngăn vấn đề nào và không ngăn được trường hợp nào?
9. CSRF và authorization bảo vệ hai điều gì khác nhau?
10. Những test nào chứng minh Controller wiring đúng, và test nào chứng minh database constraint đúng?

## Kết quả mong đợi

Sau khi hoàn thành, ứng dụng có một luồng web tạo sách hoạt động độc lập với giao diện desktop. Browser gửi request đến `BookWebController`; Controller bind và kiểm tra `BookForm`; use case hiện có thực thi quy tắc; repository lưu dữ liệu; View hiển thị lỗi hoặc trang chi tiết. Phần nghiệp vụ được giữ ở Model/application layer, trong khi HTTP và Thymeleaf trở thành một adapter giao diện mới.

Việc chuyển đổi thành công không được đo bằng số class Spring đã tạo, mà bằng việc cùng một use case có thể được gọi từ nhiều adapter mà không phải sao chép quy tắc. Khi ranh giới này rõ, ứng dụng có thể tiếp tục hỗ trợ desktop, web hoặc REST API mà vẫn duy trì một nguồn quy tắc nghiệp vụ nhất quán.
