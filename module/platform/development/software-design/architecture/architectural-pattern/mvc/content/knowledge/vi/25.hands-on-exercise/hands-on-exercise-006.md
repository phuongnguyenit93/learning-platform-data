# Thiết kế phản hồi khi thao tác thất bại

Trong ứng dụng **Model–View–Controller (MVC)**, thao tác thất bại là một phần bình thường của luồng sử dụng. Người dùng có thể gửi form thiếu dữ liệu, ISBN đã tồn tại, mở một cuốn sách đã bị xóa, không có quyền sửa hoặc lưu một phiên bản dữ liệu đã cũ. Hệ thống cần nhận diện đúng nguyên nhân, giữ lại thông tin người dùng cần, trả về trạng thái phù hợp và hướng dẫn bước tiếp theo mà không để lộ chi tiết nội bộ.

Bài thực hành thuộc chương **Thực hành** của module **MODEL_VIEW_CONTROLLER**. Người học xây dựng phản hồi lỗi cho một ứng dụng quản lý sách dùng Spring MVC. Bài tập đi qua lỗi binding và validation, lỗi nghiệp vụ, lỗi tài nguyên, phân quyền, xung đột cập nhật và lỗi hạ tầng. Trọng tâm là phân chia trách nhiệm: Controller tiếp nhận request và điều phối; application/domain layer xác định kết quả nghiệp vụ; View trình bày lỗi có thể sửa; exception handler ánh xạ lỗi ở ranh giới web; logging lưu dấu vết kỹ thuật an toàn.

## 1. Tình huống thực hành

Một thủ thư đang sửa thông tin cuốn sách có mã BK-204. Form gồm tiêu đề, ISBN, tác giả, danh mục, giá, mô tả và version. Khi gửi form, một trong các tình huống sau có thể xảy ra:

1. Tiêu đề bị bỏ trống hoặc giá không hợp lệ.
2. ISBN đã được một cuốn sách khác sử dụng.
3. Tác giả hoặc danh mục đã bị ngừng hoạt động.
4. Cuốn sách không tồn tại hoặc thuộc thư viện khác.
5. Người dùng không có quyền sửa cuốn sách.
6. Một thủ thư khác đã sửa cuốn sách sau khi form được mở.
7. Database tạm thời không truy cập được.

Không nên trả cùng một thông báo “Có lỗi xảy ra” cho tất cả tình huống. Mỗi loại lỗi cần cách xử lý khác nhau:

- Lỗi người dùng có thể sửa cần chỉ rõ trường hoặc điều kiện chưa đạt.
- Lỗi tài nguyên cần phản hồi 404 hoặc trang không tìm thấy.
- Lỗi quyền cần phản hồi từ chối truy cập.
- Lỗi xung đột cần giải thích dữ liệu đã thay đổi và hướng dẫn tải lại.
- Lỗi hạ tầng cần thông báo dịch vụ tạm thời không khả dụng, đồng thời ghi log để đội vận hành điều tra.

### 1.1. Kết quả cần đạt

Sau bài thực hành, người học có thể:

- Phân loại lỗi theo nguồn phát sinh và khả năng người dùng khắc phục.
- Giữ dữ liệu form khi validation hoặc quy tắc nghiệp vụ thất bại.
- Hiển thị lỗi tại trường và lỗi chung của form.
- Ánh xạ lỗi tài nguyên, quyền, xung đột và lỗi hạ tầng sang response phù hợp.
- Tách thông báo cho người dùng khỏi exception message kỹ thuật.
- Dùng Post/Redirect/Get sau thao tác thành công.
- Ghi log có correlation ID mà không lưu dữ liệu nhạy cảm.
- Kiểm thử cả hành vi Controller lẫn use case và exception mapping.

## 2. Phân loại lỗi trước khi thiết kế phản hồi

Hãy bắt đầu bằng việc phân loại lỗi. Một lỗi không nên được quyết định cách xử lý chỉ dựa trên tên exception; cần xét nó xảy ra ở tầng nào, người dùng có thể làm gì và trạng thái hệ thống hiện tại ra sao.

| Nhóm lỗi | Ví dụ | Phản hồi HTML | HTTP/API thường dùng |
|---|---|---|---|
| Binding | UUID không parse được, giá trị số sai định dạng | Giữ form và báo trường không hợp lệ | 400 |
| Validation | Tiêu đề rỗng, giá âm | Hiển thị lỗi cạnh trường | 400 hoặc 422 theo hợp đồng |
| Business rule | ISBN đã tồn tại, sách đang được mượn | Hiển thị lỗi có thể xử lý trong form | 409 hoặc lỗi form |
| Not found | ID sách không tồn tại | Trang 404 | 404 |
| Forbidden | Không có quyền sửa sách | Trang từ chối truy cập | 403 |
| Conflict/stale data | Version trong form đã cũ | Trang xung đột, yêu cầu tải lại | 409 |
| Rate limit | Gửi quá nhiều request | Thông báo thử lại sau | 429 |
| Dependency/infrastructure | Database hoặc dịch vụ ngoài ngừng hoạt động | Trang lỗi tạm thời | 503 nếu thực sự tạm thời |
| Unexpected | Lỗi lập trình chưa dự đoán | Trang lỗi chung | 500 |

Mã HTTP là một phần của hợp đồng. Không nên dùng 200 cho mọi lỗi chỉ vì trang lỗi vẫn render được. Với form validation thông thường, ứng dụng HTML có thể render lại trang form với 200; API thường trả 400 hoặc 422 theo quy ước đã công bố. Lỗi not found, forbidden, conflict và unexpected cần status tương ứng.

### 2.1. Lỗi có thể sửa và lỗi không thể sửa tại form hiện tại

Có thể chia tiếp theo hành động của người dùng:

- **Có thể sửa ngay:** tiêu đề trống, ISBN sai định dạng, giá âm.
- **Cần thay đổi lựa chọn:** tác giả đã ngừng hoạt động, ISBN trùng.
- **Cần tải lại hoặc liên hệ người quản trị:** dữ liệu đã thay đổi, quyền không đủ.
- **Không thể tự khắc phục:** database tạm ngừng hoạt động, lỗi hệ thống.

Phân loại này giúp View đưa ra hướng dẫn có ích thay vì chỉ hiển thị mã lỗi.

## 3. Luồng xử lý lỗi trong MVC

Trong MVC, lỗi có thể phát sinh ở nhiều tầng:

- Spring binding không chuyển đổi được dữ liệu HTTP.
- Bean Validation phát hiện dữ liệu không hợp lệ.
- Application service phát hiện vi phạm quy tắc nghiệp vụ.
- Repository không tìm thấy tài nguyên hoặc gặp constraint.
- Security layer từ chối quyền.
- Hạ tầng không phản hồi.

Controller và exception handler nằm ở ranh giới web, nơi lỗi được chuyển thành phản hồi phù hợp với HTML hoặc JSON. Không đưa logic nghiệp vụ vào View để tự đoán lỗi.

~~~mermaid
flowchart TD
    A["Người dùng gửi form"] --> B["Controller binding"]
    B --> C{"Binding / validation hợp lệ?"}
    C -->|Không| V["Gắn lỗi vào form"]
    V --> R["Render lại form và giữ input"]
    C -->|Có| U["Gọi application use case"]
    U --> D{"Use case thành công?"}
    D -->|Có| P["Redirect sau POST"]
    P --> S["GET trang kết quả"]
    D -->|Lỗi nghiệp vụ| E["Ánh xạ lỗi nghiệp vụ"]
    D -->|Không tìm thấy / quyền| H["Exception handler / security handler"]
    D -->|Lỗi hạ tầng| I["Log kỹ thuật + phản hồi an toàn"]
    E --> R
    H --> X["Trang lỗi / HTTP status"]
    I --> X
~~~

Một nguyên tắc hữu ích: lỗi được xử lý gần nơi có đủ ngữ cảnh để quyết định. Binding error thuộc web adapter; quy tắc nghiệp vụ thuộc application/domain; lỗi kỹ thuật được chuyển đổi ở adapter hạ tầng; việc biến chúng thành HTML hoặc HTTP response thuộc web boundary.

## 4. Thiết kế form và dữ liệu lỗi

Giả sử form sửa sách có các trường sau:

~~~java
public record UpdateBookForm(
    @NotBlank(message = "{book.title.required}")
    @Size(max = 160, message = "{book.title.tooLong}")
    String title,

    @NotBlank(message = "{book.isbn.required}")
    @Size(max = 20, message = "{book.isbn.tooLong}")
    String isbn,

    @NotNull(message = "{book.author.required}")
    UUID authorId,

    @NotNull(message = "{book.category.required}")
    UUID categoryId,

    @NotNull(message = "{book.price.required}")
    @DecimalMin(value = "0.00", message = "{book.price.negative}")
    BigDecimal price,

    @NotBlank(message = "{book.currency.required}")
    @Pattern(regexp = "[A-Z]{3}", message = "{book.currency.invalid}")
    String currencyCode,

    @Size(max = 4000, message = "{book.description.tooLong}")
    String description,

    @NotNull
    Long version
) {}
~~~

Request object chỉ chứa field người dùng được phép thay đổi. Không bind trực tiếp JPA entity vì client có thể gửi thêm tenantId, ownerId, published hoặc field nội bộ khác.

### 4.1. Field error và global error

- **Field error** gắn với một trường cụ thể, ví dụ ISBN trùng.
- **Global/object error** áp dụng cho toàn form, ví dụ sách không thể chuyển danh mục vì đang có giao dịch đang mở.
- **System error** không nên gắn vào một trường giả; nó cần trang lỗi hoặc thông báo chung.

Spring BindingResult có thể lưu cả field error và object error:

~~~java
errors.rejectValue(
    "isbn",
    "book.isbn.duplicate",
    "ISBN này đã được sử dụng."
);

errors.reject(
    "book.update.conflict",
    "Thông tin sách không thể cập nhật ở trạng thái hiện tại."
);
~~~

Trong ứng dụng thật, nên dùng message code và MessageSource để hỗ trợ localization. Thông điệp mặc định ở ví dụ chỉ giúp minh họa.

### 4.2. Không xóa dữ liệu người dùng đã nhập

Khi form lỗi, render lại chính View với form object và BindingResult hiện tại. Nạp lại các dữ liệu tham chiếu như danh sách tác giả và danh mục. Không tạo một form rỗng mới sau khi validation thất bại.

Nếu dùng redirect sau validation lỗi, cần một cơ chế lưu form state và lỗi riêng. Với MVC server-side thông thường, trả trực tiếp View là cách đơn giản để giữ BindingResult.

## 5. Xử lý lỗi binding và Bean Validation trong Controller

Một Controller action cập nhật có thể viết như sau:

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
        populateEditOptions(model);
        return "books/edit";
    }

    try {
        bookCommands.update(toCommand(id, form));
    } catch (DuplicateIsbnException ex) {
        errors.rejectValue(
            "isbn",
            "book.isbn.duplicate",
            "ISBN này đã được sử dụng."
        );
        populateEditOptions(model);
        return "books/edit";
    } catch (InactiveAuthorException ex) {
        errors.rejectValue(
            "authorId",
            "book.author.inactive",
            "Tác giả đã ngừng hoạt động. Hãy chọn tác giả khác."
        );
        populateEditOptions(model);
        return "books/edit";
    }

    redirect.addFlashAttribute("message", "Đã cập nhật sách.");
    return "redirect:/books/" + id;
}
~~~

BindingResult phải đứng ngay sau tham số được validate. Nếu đặt một tham số khác giữa form và BindingResult, Spring MVC có thể không liên kết lỗi theo cách mong muốn.

Trong ví dụ, lỗi ISBN trùng và tác giả không hoạt động được chuyển thành lỗi trường vì người dùng có thể sửa form. Các lỗi không thuộc phạm vi form, như tài nguyên không tồn tại hoặc không có quyền, nên được xử lý ở handler phù hợp.

### 5.1. Không bắt mọi exception trong Controller

Không nên viết:

~~~java
try {
    bookCommands.update(command);
} catch (Exception ex) {
    errors.reject("error.general", "Có lỗi xảy ra.");
    return "books/edit";
}
~~~

Cách này biến mọi lỗi thành lỗi form, kể cả database unavailable, bug lập trình hoặc lỗi bảo mật. Nó còn che giấu nguyên nhân và khiến hệ thống có thể trả status sai.

Chỉ bắt những lỗi nghiệp vụ đã biết và có hành động khắc phục phù hợp tại form. Các lỗi còn lại cần được xử lý ở ranh giới thích hợp.

### 5.2. Nạp lại dữ liệu tham chiếu khi render form lỗi

~~~java
private void populateEditOptions(Model model) {
    model.addAttribute("authors", bookQueries.listActiveAuthors());
    model.addAttribute("categories", bookQueries.listActiveCategories());
}
~~~

Method này chỉ minh họa. Có thể đưa logic nạp dữ liệu form vào một helper/facade riêng nếu nhiều Controller cùng dùng. Đảm bảo không ghi đè attribute form hoặc BindingResult đã được Spring đặt trong Model.

## 6. Xử lý lỗi nghiệp vụ ở application/domain layer

Quy tắc nghiệp vụ phải được bảo vệ dù use case được gọi từ MVC, REST hay message consumer. Ví dụ, ISBN không được trùng trong cùng phạm vi thư viện.

Một application service có thể kiểm tra:

~~~java
@Transactional
public void update(UpdateBookCommand command) {
    Book book = books.findByIdAndTenant(
        command.bookId(),
        currentUser.tenantId()
    ).orElseThrow(BookNotFoundException::new);

    authorization.requireCanEdit(book);

    if (books.existsOtherBookWithIsbn(
        command.isbn(),
        book.id(),
        book.tenantId()
    )) {
        throw new DuplicateIsbnException();
    }

    Author author = authors.findActive(command.authorId())
        .orElseThrow(InactiveAuthorException::new);

    book.updateDetails(command, author);
}
~~~

Đây là ví dụ rút gọn. Kiểm tra trùng ở application service cần được hỗ trợ bởi unique constraint phù hợp trong database để tránh hai request đồng thời cùng vượt qua bước kiểm tra. Nếu constraint bị vi phạm, adapter persistence cần chuyển lỗi kỹ thuật thành lỗi nghiệp vụ đã biết ở ranh giới phù hợp.

### 6.1. Exception nên biểu diễn ý nghĩa, không mang HTTP

Các exception như BookNotFoundException, DuplicateIsbnException, InactiveAuthorException hoặc StaleBookUpdateException mô tả kết quả ứng dụng. Không nên để domain/application layer ném ResponseStatusException, HttpStatus hoặc ModelAndView nếu mục tiêu là giữ use case độc lập với web.

Web adapter quyết định một lỗi ứng dụng trở thành trang HTML, redirect, 404, 409 hay JSON Problem Detail.

### 6.2. Constraint database vẫn cần thiết

Một truy vấn existsByIsbn không bảo đảm duy nhất khi có hai request cùng lúc:

1. Request A kiểm tra ISBN chưa tồn tại.
2. Request B cũng kiểm tra ISBN chưa tồn tại.
3. Cả hai cùng insert.
4. Database có thể nhận cả hai nếu không có unique constraint.

Đặt unique constraint theo phạm vi nghiệp vụ (ví dụ tenant + ISBN), sau đó chuyển lỗi constraint có tên xác định thành DuplicateIsbnException. Không phân tích mọi chuỗi exception database để suy đoán lỗi; adapter nên nhận diện constraint cụ thể.

## 7. Xử lý not found, forbidden và conflict bằng exception handler

Các lỗi không thể sửa bằng cách thay một field thường được xử lý ở cấp request.

### 7.1. HTML exception handler

~~~java
@ControllerAdvice(assignableTypes = BookController.class)
public class BookPageExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ModelAndView notFound() {
        ModelAndView result = new ModelAndView("error/404");
        result.setStatus(HttpStatus.NOT_FOUND);
        return result;
    }

    @ExceptionHandler(StaleBookUpdateException.class)
    public ModelAndView staleUpdate() {
        ModelAndView result = new ModelAndView("books/conflict");
        result.setStatus(HttpStatus.CONFLICT);
        result.addObject(
            "message",
            "Sách đã được cập nhật bởi người khác. Hãy tải lại trước khi sửa tiếp."
        );
        return result;
    }
}
~~~

Handler có thể giới hạn theo Controller hoặc package để tránh ảnh hưởng đến những phần khác của ứng dụng. Với lỗi forbidden do Spring Security chặn trước khi request vào Controller, cần cấu hình AccessDeniedHandler hoặc AccessDeniedException flow phù hợp; ControllerAdvice không phải lúc nào cũng là nơi nhận lỗi security filter chain.

### 7.2. Không để exception message kỹ thuật xuất hiện trong trang lỗi

Không đưa exception.getMessage() trực tiếp ra View nếu exception có thể chứa SQL, tên bảng, đường dẫn file, token hoặc dữ liệu nội bộ. Hãy dùng message code hoặc nội dung an toàn do ứng dụng định nghĩa.

Ví dụ thông báo tốt:

- “Không tìm thấy cuốn sách này.”
- “Bạn không có quyền sửa cuốn sách này.”
- “Dữ liệu đã được cập nhật bởi người khác. Hãy tải lại trang.”
- “Dịch vụ đang tạm thời không khả dụng. Vui lòng thử lại sau.”

Thông tin kỹ thuật đầy đủ được ghi trong log có kiểm soát.

## 8. Trả lỗi phù hợp cho REST API

HTML form và REST API có cách trình bày khác nhau. Không trả template HTML cho API hoặc serialize exception thành JSON tùy tiện.

Spring hỗ trợ ProblemDetail theo RFC 9457 trong các phiên bản phù hợp. Ví dụ:

~~~java
@RestControllerAdvice
public class BookApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
        HttpServletRequest request
    ) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy cuốn sách được yêu cầu."
        );
        problem.setTitle("Không tìm thấy sách");
        problem.setType(URI.create("https://api.example.test/problems/book-not-found"));
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "BOOK_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

Ví dụ minh họa cấu trúc; domain exception không cần được truyền vào response nếu handler không dùng nó. Trong thực tế, URL type nên là định danh tài liệu lỗi do API quản lý, không nhất thiết phải trỏ đến domain .test.

Một response lỗi có thể trông như sau:

~~~json
{
  "type": "https://api.example.test/problems/book-not-found",
  "title": "Không tìm thấy sách",
  "status": 404,
  "detail": "Không tìm thấy cuốn sách được yêu cầu.",
  "instance": "/api/books/204",
  "code": "BOOK_NOT_FOUND"
}
~~~

Không trả stack trace hoặc SQL trong detail. Với validation error, có thể thêm một property errors chứa danh sách field, message code và thông báo an toàn. Hãy giữ cấu trúc nhất quán để client có thể xử lý theo code, thay vì phân tích câu chữ.

## 9. Bản đồ lỗi và status code

Một hợp đồng response có thể dùng quy ước:

| Trường hợp | HTML | API | Ghi chú |
|---|---|---|---|
| Form validation | Render form, thường 200 | 400 hoặc 422 | Giữ field errors |
| Tài nguyên không tồn tại | Trang 404 | 404 | Không lộ tài nguyên ngoài quyền nếu chính sách dùng 404 |
| Không đủ quyền | Trang 403 | 403 | Security handler có thể xử lý trước MVC |
| ISBN trùng | Lỗi form | 409 | Conflict với trạng thái hiện tại |
| Stale version | Trang conflict 409 | 409 | Người dùng cần tải lại và đối chiếu |
| Request sai cú pháp | Trang lỗi request hoặc form | 400 | Ví dụ UUID/enum không parse được |
| Quá nhiều request | Trang/thông báo giới hạn | 429 | Có thể gửi Retry-After |
| Dependency tạm ngừng | Trang tạm thời không khả dụng | 503 | Chỉ dùng khi thực sự là lỗi dịch vụ tạm thời |
| Lỗi không dự kiến | Trang 500 | 500 | Mã tham chiếu để hỗ trợ |

Status code phải nhất quán trong toàn API. Không dùng 500 cho lỗi người dùng nhập sai, và không dùng 200 cho API chỉ vì đã tạo được một JSON chứa nội dung lỗi.

## 10. Giữ input, hiển thị lỗi và hỗ trợ accessibility

Một trang form lỗi cần cho người dùng biết:

- Trường nào sai.
- Vì sao giá trị không hợp lệ.
- Cách sửa.
- Form có giữ lại dữ liệu đã nhập hay không.
- Lỗi áp dụng cho một trường hay toàn bộ thao tác.

Ví dụ HTML:

~~~html
<div role="alert" aria-labelledby="error-summary-title">
  <h2 id="error-summary-title">Có 2 lỗi cần sửa</h2>
  <ul>
    <li><a href="#title">Tiêu đề không được để trống</a></li>
    <li><a href="#isbn">ISBN này đã được sử dụng</a></li>
  </ul>
</div>

<label for="title">Tiêu đề</label>
<input id="title" name="title" aria-invalid="true"
       aria-describedby="title-error" />
<p id="title-error">Vui lòng nhập tiêu đề sách.</p>
~~~

Trong template thật, giá trị input cần được bind lại từ form object. Mỗi lỗi cần được liên kết với input qua aria-describedby; dùng aria-invalid="true" cho trường lỗi. Error summary nên có liên kết đến từng trường để người dùng bàn phím có thể di chuyển nhanh.

Khi submit lỗi, có thể đưa focus đến heading của error summary hoặc trường lỗi đầu tiên theo hành vi đã thiết kế. Không chỉ đổi viền thành màu đỏ; phải có thông báo bằng văn bản. Nếu form dài, giữ vị trí người dùng dễ tìm lại trường cần sửa.

## 11. Post/Redirect/Get và thông báo sau thao tác

Khi thao tác ghi thành công, dùng Post/Redirect/Get (PRG):

1. Browser gửi POST.
2. Controller gọi use case.
3. Use case thành công.
4. Controller redirect đến GET.
5. GET hiển thị kết quả cùng flash message.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Controller as Controller
    participant UseCase as UpdateBook
    participant DB as Database

    User->>Browser: Gửi form sửa sách
    Browser->>Controller: POST /books/BK-204
    Controller->>UseCase: update(command)
    UseCase->>DB: UPDATE
    DB-->>UseCase: Thành công
    UseCase-->>Controller: Kết quả
    Controller-->>Browser: Redirect /books/BK-204
    Browser->>Controller: GET /books/BK-204
    Controller-->>Browser: Trang chi tiết + thông báo
~~~

PRG giúp refresh trang kết quả không gửi lại POST theo cách thông thường. Nó không thay thế idempotency: người dùng có thể nhấn submit nhiều lần hoặc client có thể retry khi mất kết nối. Với thao tác tạo, cần unique constraint hoặc idempotency key nếu việc thực thi lặp có thể gây tác dụng phụ.

Không redirect sau lỗi validation nếu cần giữ BindingResult và dữ liệu form. Nếu dùng redirect cho lỗi nghiệp vụ, phải có cơ chế lưu lỗi/form state rõ ràng, chẳng hạn flash attributes có giới hạn và không chứa dữ liệu nhạy cảm.

## 12. Lỗi cập nhật đồng thời

Giả sử hai thủ thư mở cùng một form sửa. Người thứ nhất lưu thành công. Người thứ hai gửi dữ liệu cũ sau đó. Hệ thống cần phát hiện stale update thay vì âm thầm ghi đè.

JPA hỗ trợ optimistic locking:

~~~java
@Entity
public class BookEntity {
    @Id
    private UUID id;

    @Version
    private Long version;
}
~~~

Form gửi version đã đọc:

~~~html
<input type="hidden" name="version" value="7" />
~~~

Application service so sánh version từ form với version hiện tại; @Version tiếp tục bảo vệ cuộc đua xảy ra giữa lúc entity được tải và lúc transaction ghi. Khi version đã cũ, ném StaleBookUpdateException và chuyển thành 409 hoặc trang conflict.

Không tự động retry một thao tác cập nhật stale bằng cách ghi lại cùng dữ liệu lên bản mới nhất. Người dùng cần xem nội dung đã thay đổi và quyết định áp dụng lại.

## 13. Ghi log và correlation ID

Phản hồi người dùng cần ngắn gọn và an toàn. Log nội bộ cần đủ dữ liệu để điều tra.

Nên ghi:

- Correlation ID hoặc trace ID.
- Tên use case/route và HTTP method.
- Mã lỗi ổn định.
- Loại exception.
- User ID hoặc tenant ID theo chính sách log và quyền riêng tư.
- Thời điểm và thông tin dependency cần thiết.
- Stack trace cho lỗi bất ngờ ở mức log phù hợp.

Không ghi:

- Password, session cookie, access token hoặc CSRF token.
- Toàn bộ form có thể chứa dữ liệu cá nhân.
- Bí mật tenant hoặc dữ liệu nhạy cảm.
- SQL có bind value nhạy cảm.
- Nội dung exception database chưa được lọc.

Ví dụ:

~~~java
log.warn(
    "Book update rejected: code={}, bookId={}, correlationId={}",
    "BOOK_ISBN_DUPLICATE",
    bookId,
    correlationId
);
~~~

Với lỗi bất ngờ:

~~~java
log.error(
    "Unexpected failure in updateBook: correlationId={}",
    correlationId,
    exception
);
~~~

Không log và trả exception message kỹ thuật cho người dùng cùng lúc. Correlation ID có thể được trả trong trang lỗi hoặc response header để hỗ trợ tra cứu, nhưng không nên chứa thông tin bí mật.

## 14. Khi nào cho phép thử lại?

Không phải lỗi nào cũng nên có nút “Thử lại”.

| Lỗi | Có nên retry? | Hành động phù hợp |
|---|---|---|
| Validation | Không | Sửa input |
| ISBN trùng | Không | Chọn ISBN khác hoặc mở bản ghi hiện có |
| Not found | Không | Quay lại danh sách hoặc tìm lại |
| Forbidden | Không | Liên hệ quản trị viên nếu cần quyền |
| Stale update | Không tự retry | Tải lại, so sánh và sửa lại |
| Timeout khi đọc | Có thể | Retry có giới hạn và backoff |
| Timeout khi ghi | Chỉ khi có idempotency/kiểm tra kết quả | Tra cứu trạng thái trước khi gửi lại |
| 429 | Có thể sau thời gian được chỉ định | Tôn trọng Retry-After |
| 503 | Có điều kiện | Chỉ retry request an toàn/idempotent hoặc có idempotency key; dùng backoff và jitter |

Timeout khi ghi có trạng thái không chắc chắn: server có thể đã commit nhưng response bị mất. Gửi lại ngay có thể tạo bản ghi trùng hoặc lặp tác dụng phụ. Cần idempotency key, unique business key hoặc cơ chế tra cứu kết quả trước khi retry.

## 15. Bài tập thực hành

Hãy triển khai phản hồi lỗi cho chức năng sửa sách tại /books/{id}.

### Phần A — Tạo các trường hợp lỗi

Chuẩn bị dữ liệu test và tạo các tình huống:

1. Tiêu đề rỗng.
2. ISBN sai định dạng.
3. ISBN trùng với một sách khác.
4. Tác giả được chọn đã ngừng hoạt động.
5. ID sách không tồn tại.
6. Người dùng không có quyền sửa.
7. Version trong form đã cũ.
8. Database không khả dụng.

### Phần B — Thiết kế phản hồi

Với mỗi tình huống, xác định:

- Lỗi phát sinh ở tầng nào?
- Người dùng có thể tự khắc phục không?
- Có cần giữ lại form không?
- Field error hay global error?
- HTTP status hoặc trang nào được trả?
- Có cần ghi log không?
- Có thể retry không?

Ghi kết quả vào bảng:

| Tình huống | Tầng phát sinh | Giữ form? | Phản hồi | Status | Retry? |
|---|---|---|---|---:|---|
| Tiêu đề rỗng | Binding/validation | Có | Lỗi tại trường | 200 HTML / 422 API | Không |
| ISBN trùng | Application/domain | Có | Lỗi tại ISBN | 200 HTML / 409 API | Không |
| Sách không tồn tại | Application/query | Không | Trang/response 404 | 404 | Không |
| Không có quyền | Security/application | Không | Trang/response 403 | 403 | Không |
| Version cũ | Application/persistence | Không hoặc form conflict | Yêu cầu tải lại | 409 | Không tự retry |
| Database tạm ngừng | Infrastructure | Không tự gửi lại form | Trang lỗi tạm thời | 503 | Có điều kiện |

### Phần C — Cài đặt

- Tạo request DTO với Bean Validation.
- Viết Controller action giữ form và danh sách tác giả/danh mục khi lỗi.
- Chuyển lỗi nghiệp vụ có thể sửa thành field/global error.
- Viết ControllerAdvice cho not found và stale update.
- Viết RestControllerAdvice nếu có API JSON.
- Cấu hình Security handler cho forbidden.
- Dùng PRG sau khi cập nhật thành công.
- Thêm correlation ID vào log và response lỗi nếu phù hợp.
- Không trả exception message hoặc stack trace ra View/API.

### Phần D — Kiểm thử

- Test form giữ lại input khi validation lỗi.
- Test lỗi ISBN trùng được gắn vào đúng field.
- Test lỗi tài nguyên trả 404.
- Test quyền bị từ chối trả 403.
- Test stale update trả 409.
- Test lỗi bất ngờ không lộ chi tiết nội bộ.
- Test thành công redirect theo PRG.
- Test API trả Problem Detail có code ổn định.
- Test không tự retry thao tác ghi không idempotent.

## 16. Tiêu chí nghiệm thu

Bài thực hành được xem là hoàn thành khi:

- [ ] Lỗi binding và validation được hiển thị đúng trường.
- [ ] Dữ liệu hợp lệ người dùng đã nhập được giữ lại khi form lỗi.
- [ ] Danh sách tác giả/danh mục vẫn được nạp khi render lại form.
- [ ] Lỗi ISBN trùng được chuyển thành lỗi nghiệp vụ có thể hiểu.
- [ ] Not found, forbidden, conflict và unexpected error được phân biệt.
- [ ] Status HTTP phù hợp với từng loại lỗi.
- [ ] HTML và API có cách biểu diễn lỗi riêng.
- [ ] Exception message kỹ thuật không bị lộ.
- [ ] Lỗi cập nhật đồng thời yêu cầu người dùng tải lại.
- [ ] Log có correlation ID và không chứa secret hoặc toàn bộ dữ liệu form.
- [ ] POST thành công dùng PRG.
- [ ] Có test cho các trường hợp chính và luồng thành công.

## 17. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Trả một thông báo chung cho mọi lỗi | Người dùng không biết cách sửa | Phân loại lỗi và hướng dẫn cụ thể |
| Bắt Exception rồi trả về form | Che giấu lỗi hạ tầng và bug | Chỉ xử lý lỗi nghiệp vụ đã biết |
| Redirect sau validation lỗi | Mất BindingResult và dữ liệu form | Render lại cùng View |
| Không nạp lại select options | Form lỗi không thể sử dụng tiếp | Nạp lại dữ liệu tham chiếu |
| Đưa exception message ra giao diện | Lộ SQL, schema hoặc dữ liệu nội bộ | Message code an toàn |
| Dùng 200 cho mọi API error | Client không thể phân loại response | Dùng status HTTP phù hợp |
| Dùng 500 cho lỗi input | Ghi nhận sai bản chất lỗi | 400/422 hoặc lỗi form |
| Dùng GET để thay đổi dữ liệu | Request ngoài ý muốn có thể gây tác dụng phụ | Dùng method thay đổi trạng thái và CSRF |
| Tự retry stale update | Ghi đè dữ liệu người khác | Yêu cầu tải lại và đối chiếu |
| Log toàn bộ form | Lưu dữ liệu nhạy cảm ngoài mục đích | Log mã lỗi và correlation ID |
| Chỉ test trang lỗi | Bỏ sót lỗi binding, quyền và use case | Test theo tầng và end-to-end |

## 18. Kết luận

Thiết kế phản hồi khi thao tác thất bại là một phần của hợp đồng MVC. Controller tiếp nhận và điều phối; application/domain xác định kết quả nghiệp vụ; exception handler và security handler ánh xạ lỗi ở ranh giới web; View hoặc API trình bày thông tin phù hợp. Lỗi có thể sửa cần giữ dữ liệu và chỉ rõ cách khắc phục, còn lỗi quyền, tài nguyên, xung đột và hạ tầng cần status và hướng xử lý riêng.

Khi phân loại lỗi rõ ràng, không bắt mọi exception trong Controller, không để lộ chi tiết nội bộ và kiểm thử cả luồng thành công lẫn thất bại, ứng dụng trở nên dễ sử dụng và dễ vận hành hơn.
