# Luồng cập nhật với kiểm soát xung đột

Trong ứng dụng quản lý sách, hai thủ thư có thể cùng mở trang chỉnh sửa một cuốn sách. Người thứ nhất cập nhật tên sách và lưu thành công. Một lúc sau, người thứ hai lưu biểu mẫu đã mở từ trước với dữ liệu cũ. Nếu hệ thống cứ ghi bản gửi đến sau cùng, thay đổi của người thứ nhất có thể bị ghi đè mà không ai nhận ra.

Đây là **xung đột cập nhật đồng thời** (concurrent update conflict). Ứng dụng MVC cần phát hiện trường hợp dữ liệu người dùng đang sửa đã thay đổi kể từ lúc họ tải biểu mẫu, sau đó phản hồi rõ ràng để người dùng quyết định tải lại hoặc kết hợp thay đổi.

Bài học xây dựng luồng cập nhật sách bằng Spring MVC và Spring Data JPA. Ta dùng optimistic locking với trường `@Version`, đưa phiên bản vào form như một concurrency token, kiểm tra dữ liệu cũ trước khi cập nhật và xử lý cả cuộc đua xảy ra ngay trước lúc transaction commit.

## 1. Tình huống: hai người cùng sửa một cuốn sách

Giả sử bản ghi sách có ID `42` và phiên bản hiện tại là `7`.

1. Thủ thư An mở `/books/42/edit`, nhận dữ liệu sách ở version `7`.
2. Thủ thư Bình cũng mở cùng trang, nhận version `7`.
3. An đổi tiêu đề rồi lưu. Database ghi thay đổi và tăng version lên `8`.
4. Bình vẫn đang giữ form version `7`, đổi tên tác giả rồi lưu.
5. Nếu server không kiểm tra phiên bản, dữ liệu của Bình có thể ghi đè dữ liệu An vừa cập nhật.

Ứng dụng cần nhận ra rằng form của Bình dựa trên một bản dữ liệu cũ. Server nên từ chối cập nhật cũ và hiển thị trạng thái mới nhất để Bình xem lại.

```mermaid
sequenceDiagram
    actor An
    actor Binh as Bình
    participant MVC as Spring MVC
    participant S as BookApplicationService
    participant DB as Database

    An->>MVC: GET /books/42/edit
    MVC->>S: getEditForm(42)
    S->>DB: SELECT book
    DB-->>S: version=7
    S-->>MVC: Form(version=7)
    MVC-->>An: HTML form version=7

    Binh->>MVC: GET /books/42/edit
    MVC->>S: getEditForm(42)
    S->>DB: SELECT book
    DB-->>S: version=7
    S-->>MVC: Form(version=7)
    MVC-->>Binh: HTML form version=7

    An->>MVC: POST form(version=7)
    MVC->>S: update(42, version=7)
    S->>DB: UPDATE ... WHERE id=42 AND version=7
    DB-->>S: 1 row; version becomes 8
    MVC-->>An: Redirect to detail

    Binh->>MVC: POST form(version=7)
    MVC->>S: update(42, version=7)
    S->>DB: Read current book version=8
    S-->>MVC: Conflict: submitted version is stale
    MVC-->>Binh: HTTP 409 with latest data
```

Đây là luồng điển hình. Ngoài tình huống server đọc thấy phiên bản đã cũ, còn một cuộc đua nhỏ hơn: hai request cùng đọc version `7`, cùng vượt qua bước so sánh ở Service, rồi mới cập nhật. Cơ chế optimistic locking của database/JPA sẽ xử lý cuộc đua thứ hai.

## 2. Phân biệt ghi đè dữ liệu và kiểm soát xung đột

Một hệ thống dùng chiến lược *last write wins* chấp nhận lần ghi sau cùng ghi đè dữ liệu trước đó. Cách này đơn giản, nhưng chỉ phù hợp khi ghi đè là hành vi được chấp nhận và dữ liệu không cần bảo toàn các thay đổi đồng thời.

Với thông tin thư mục sách như tiêu đề, tác giả, ISBN, năm xuất bản hoặc ghi chú biên mục, việc mất thay đổi âm thầm thường không phù hợp. Kiểm soát xung đột giúp ứng dụng:

- Phát hiện form dựa trên dữ liệu cũ.
- Bảo toàn cập nhật đã commit trước đó.
- Cho người dùng biết dữ liệu đã thay đổi.
- Cho phép người dùng tải lại, so sánh hoặc kết hợp thay đổi một cách có chủ đích.

Kiểm soát xung đột không có nghĩa tự động hợp nhất mọi trường. Server không thể tự biết thay đổi nào quan trọng với người dùng. Với một số trường độc lập có thể xây dựng quy tắc merge, nhưng mặc định an toàn là báo xung đột và để người dùng quyết định.

## 3. Optimistic locking với `@Version`

Optimistic locking giả định xung đột không xảy ra thường xuyên. Hệ thống không khóa bản ghi trong suốt thời gian người dùng mở form. Thay vào đó, mỗi lần cập nhật sẽ kiểm tra phiên bản mà request đang dựa vào.

Với JPA, có thể khai báo trường phiên bản trong entity:

```java
@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, length = 160)
    private String author;

    @Column(nullable = false, length = 20)
    private String isbn;

    protected Book() {
    }

    public void updateDetails(String title, String author, String isbn) {
        this.title = title;
        this.author = author;
        this.isbn = isbn;
    }

    public Long getId() { return id; }
    public long getVersion() { return version; }
    public String getTitle() { return title; }
    public String getAuthor() { return author; }
    public String getIsbn() { return isbn; }
}
```

`@Version` báo cho JPA rằng trường `version` được dùng để phát hiện cập nhật đồng thời. Ứng dụng không tự tăng trường này khi sửa entity; provider sẽ quản lý phiên bản khi ghi thành công.

Một câu lệnh cập nhật có thể có dạng tương đương:

```sql
UPDATE books
SET title = ?, author = ?, isbn = ?, version = 8
WHERE id = 42 AND version = 7;
```

Nếu không có request nào thay đổi bản ghi kể từ lúc entity được đọc, điều kiện `version = 7` khớp và một hàng được cập nhật. Nếu một transaction khác đã tăng version lên `8`, câu lệnh cập nhật theo version `7` không tác động hàng nào. JPA báo lỗi optimistic locking thay vì âm thầm ghi đè.

Database schema cần có cột version tương ứng. Với ứng dụng dùng migration, hãy thêm cột qua migration và đặt giá trị mặc định ban đầu phù hợp cho các bản ghi hiện có. Không chỉ thêm annotation vào entity rồi giả định schema production đã tự thay đổi.

Ví dụ migration SQL cho bảng đã có dữ liệu:

```sql
ALTER TABLE books
    ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Tên kiểu dữ liệu và cú pháp migration cần điều chỉnh theo hệ quản trị database và công cụ migration của dự án.

## 4. Vì sao chỉ có `@Version` là chưa đủ cho form MVC?

Đây là điểm quan trọng của luồng chỉnh sửa qua trình duyệt.

Giả sử request của Bình gửi form version `7`, nhưng trước khi request đến server, An đã cập nhật bản ghi lên version `8`. Service tải entity hiện tại từ database sẽ nhận được entity version `8`. Nếu Service chỉ sửa entity mới tải bằng dữ liệu cũ trong form rồi lưu, JPA có thể dùng version `8` làm điều kiện cập nhật. Việc ghi sẽ thành công và dữ liệu của An vẫn bị ghi đè.

Vì vậy, luồng MVC cần so sánh hai giá trị:

- `submittedVersion`: version mà trình duyệt nhận khi mở form.
- `currentVersion`: version hiện tại của entity khi Service tải dữ liệu.

Nếu hai giá trị khác nhau, từ chối cập nhật ngay. Sau bước so sánh đó, `@Version` tiếp tục bảo vệ khoảng thời gian từ lúc đọc entity đến lúc transaction ghi/commit.

Hai lớp bảo vệ giải quyết hai tình huống khác nhau:

| Cơ chế | Phát hiện trường hợp nào? |
|---|---|
| So sánh version trong Service | Form đã cũ trước khi request cập nhật bắt đầu |
| JPA `@Version` khi flush/commit | Một transaction khác cập nhật sau lần đọc hiện tại nhưng trước khi transaction này ghi thành công |

Nếu bỏ bước so sánh version được gửi từ form, ứng dụng vẫn có thể gặp lost update dù entity đã khai báo `@Version`.

## 5. Form object và command cho thao tác cập nhật

Không bind request trực tiếp vào entity `Book`. Entity có thể chứa trường nội bộ, trạng thái nghiệp vụ hoặc thuộc tính mà người dùng không được quyền thay đổi. Dùng form object cho dữ liệu giao diện và command cho ý định nghiệp vụ.

Form object:

```java
public class UpdateBookForm {
    @NotNull
    @Min(0)
    private Long version;

    @NotBlank(message = "Tên sách không được để trống.")
    @Size(max = 200, message = "Tên sách tối đa 200 ký tự.")
    private String title;

    @NotBlank(message = "Tác giả không được để trống.")
    @Size(max = 160, message = "Tên tác giả tối đa 160 ký tự.")
    private String author;

    @NotBlank(message = "ISBN không được để trống.")
    @Size(max = 20, message = "ISBN tối đa 20 ký tự.")
    private String isbn;

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getAuthor() { return author; }
    public void setAuthor(String author) { this.author = author; }
    public String getIsbn() { return isbn; }
    public void setIsbn(String isbn) { this.isbn = isbn; }
}
```

Command:

```java
public record UpdateBookCommand(
        long version,
        String title,
        String author,
        String isbn) {
}
```

Trong form object, `version` dùng kiểu `Long` kèm `@NotNull`. Nếu dùng `long` nguyên thủy, một request thiếu trường version có thể bị bind thành `0`; với bản ghi đang ở version `0`, token bị thiếu có thể vô tình vượt qua bước so sánh. Kiểu nullable giúp validation phát hiện request không gửi token.

Form object phục vụ binding và validation ở ranh giới web. Command diễn đạt dữ liệu mà use case cập nhật sách cần nhận. `version` trong command là concurrency token để kiểm tra bản dữ liệu mà người dùng đã sửa.

Giá trị version do client gửi không phải dữ liệu đáng tin cậy để cấp quyền. Người dùng có thể sửa trường hidden, nên concurrency token này không phải chữ ký số hay cơ chế chống giả mạo. Nó chủ yếu phát hiện form cũ trong luồng sử dụng bình thường; nó không ngăn một client cố ý thay version thành giá trị mới nhất để ghi đè. Server vẫn phải xác thực người dùng, kiểm tra quyền sửa đúng cuốn sách và chỉ cho phép cập nhật các trường nằm trong hợp đồng. Nếu nghiệp vụ cần chứng minh token đúng là phiên bản server đã phát cho một form cụ thể, có thể ký token bằng HMAC hoặc lưu trạng thái form phía server; vẫn phải giữ kiểm tra quyền độc lập. Biết version hiện tại không có nghĩa là được phép cập nhật.

## 6. Repository và truy vấn lấy dữ liệu chỉnh sửa

Repository có thể dùng Spring Data JPA:

```java
public interface BookRepository extends JpaRepository<Book, Long> {
}
```

Service trả form dữ liệu từ entity:

```java
@Service
public class BookApplicationService {
    private final BookRepository bookRepository;
    private final BookAccessPolicy accessPolicy;

    public BookApplicationService(
            BookRepository bookRepository,
            BookAccessPolicy accessPolicy) {
        this.bookRepository = bookRepository;
        this.accessPolicy = accessPolicy;
    }

    // Phương thức update ở phần tiếp theo thuộc cùng service này.

    @Transactional(readOnly = true)
    public UpdateBookForm getEditForm(long bookId, long actorId) {
        Book book = bookRepository.findById(bookId)
                .orElseThrow(() -> new BookNotFoundException(bookId));
        accessPolicy.checkCanEdit(actorId, book);

        UpdateBookForm form = new UpdateBookForm();
        form.setVersion(book.getVersion());
        form.setTitle(book.getTitle());
        form.setAuthor(book.getAuthor());
        form.setIsbn(book.getIsbn());
        return form;
    }
}
```

Trong ứng dụng lớn, có thể dùng một `BookEditView` immutable thay vì tái sử dụng form class cho dữ liệu GET. Ví dụ dùng cùng `UpdateBookForm` để tập trung vào luồng. Dù chọn kiểu nào, chỉ đưa các trường cần hiển thị và token phiên bản vào Model.

## 7. Service kiểm tra bản gửi lên và cập nhật entity

Service tải entity trong transaction, kiểm tra quyền, so sánh version được gửi từ form rồi mới áp dụng thay đổi:

```java
@Transactional
public void update(long bookId, long actorId, UpdateBookCommand command) {
    Book book = bookRepository.findById(bookId)
            .orElseThrow(() -> new BookNotFoundException(bookId));

    accessPolicy.checkCanEdit(actorId, book);

    if (book.getVersion() != command.version()) {
        throw new BookConflictException(bookId);
    }

    book.updateDetails(
            command.title(),
            command.author(),
            command.isbn());
}
```

Exception miền có thể được định nghĩa đơn giản:

```java
public class BookConflictException extends RuntimeException {
    public BookConflictException(long bookId) {
        super("Book was changed by another request: " + bookId);
    }
}
```

Đoạn mã là một phương thức trong `BookApplicationService` ở phần trước. Entity được quản lý trong persistence context, nên JPA dirty checking sẽ phát hiện thay đổi. Khi transaction flush/commit, `@Version` bảo vệ trường hợp có request khác cập nhật sau bước so sánh.

Nếu ứng dụng dùng repository không có dirty checking, Service cần gọi thao tác lưu tương ứng. Nếu dùng bulk update JPQL hoặc SQL trực tiếp, phải tự đưa version vào điều kiện `WHERE`, tăng version và kiểm tra số hàng bị cập nhật; bulk update thường bỏ qua cơ chế quản lý version tự động của entity.

Không gọi API ngoài hoặc gửi email trực tiếp trong transaction cập nhật chỉ vì muốn hoàn thành tất cả trong một phương thức. Nếu cần phát thông báo sau cập nhật, có thể ghi outbox event trong cùng transaction rồi xử lý riêng sau commit.

## 8. Controller điều phối GET form và POST update

Controller giữ trách nhiệm HTTP: lấy actor, bind form, kiểm tra validation, gọi use case và chọn trang hoặc redirect.

```java
@Controller
@RequestMapping("/books")
public class BookController {
    private final BookApplicationService bookService;

    public BookController(BookApplicationService bookService) {
        this.bookService = bookService;
    }

    @GetMapping("/{id}/edit")
    public ModelAndView edit(
            @PathVariable long id,
            @AuthenticationPrincipal AppUserPrincipal actor) {

        ModelAndView view = new ModelAndView("books/edit");
        view.addObject("bookId", id);
        view.addObject("form", bookService.getEditForm(id, actor.userId()));
        return view;
    }

    @PostMapping("/{id}")
    public ModelAndView update(
            @PathVariable long id,
            @AuthenticationPrincipal AppUserPrincipal actor,
            @Valid @ModelAttribute("form") UpdateBookForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            ModelAndView view = new ModelAndView("books/edit");
            view.addObject("bookId", id);
            view.addObject("form", form);
            return view;
        }

        UpdateBookCommand command = new UpdateBookCommand(
                form.getVersion(),
                form.getTitle(),
                form.getAuthor(),
                form.getIsbn());

        try {
            bookService.update(id, actor.userId(), command);
            return new ModelAndView("redirect:/books/" + id);
        } catch (BookConflictException
                 | ObjectOptimisticLockingFailureException exception) {

            ModelAndView view = new ModelAndView("books/edit-conflict");
            view.setStatus(HttpStatus.CONFLICT);
            view.addObject("bookId", id);
            view.addObject("submitted", form);
            view.addObject("latest", bookService.getEditForm(id, actor.userId()));
            return view;
        }
    }
}
```

Các import quan trọng trong ví dụ:

```java
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.ModelAndView;
```

`BindingResult` được đặt ngay sau tham số form để Spring gắn lỗi binding/validation vào đúng object. Khi validation thất bại, Controller trả lại form cùng dữ liệu người dùng vừa nhập. Khi xung đột xảy ra, trang riêng nhận cả dữ liệu đã gửi và dữ liệu mới nhất để người dùng so sánh.

Trong Spring, lỗi optimistic locking có thể được ném khi flush hoặc commit transaction, tức là sau khi thân phương thức Service đã chạy xong. Vì lời gọi qua Spring transaction proxy chỉ trả về sau khi transaction interceptor hoàn tất commit, Controller có thể bắt exception phát sinh ở ranh giới lời gọi này. Nếu có transaction bao ngoài Controller hoặc một tầng gọi khác, cần đặt xử lý xung đột ở nơi thực sự nhận exception commit.

`ObjectOptimisticLockingFailureException` là loại exception Spring thường dùng khi dịch lỗi optimistic locking từ persistence provider. Tùy cấu hình và loại thao tác, ứng dụng cũng có thể cần ánh xạ các exception optimistic locking khác về cùng một lỗi miền `409 Conflict`.

## 9. Template gửi version về server

Template `templates/books/edit.html` dùng `th:object` và `th:field` để binding form. Trường version là hidden input:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Chỉnh sửa sách</title>
</head>
<body>
<main>
    <h1>Chỉnh sửa sách</h1>

    <form th:action="@{/books/{id}(id=${bookId})}"
          th:object="${form}"
          method="post">

        <input type="hidden" th:field="*{version}">

        <label for="title">Tên sách</label>
        <input id="title" type="text" th:field="*{title}">
        <p th:if="${#fields.hasErrors('title')}" th:errors="*{title}"></p>

        <label for="author">Tác giả</label>
        <input id="author" type="text" th:field="*{author}">
        <p th:if="${#fields.hasErrors('author')}" th:errors="*{author}"></p>

        <label for="isbn">ISBN</label>
        <input id="isbn" type="text" th:field="*{isbn}">
        <p th:if="${#fields.hasErrors('isbn')}" th:errors="*{isbn}"></p>

        <button type="submit">Lưu thay đổi</button>
    </form>
</main>
</body>
</html>
```

Hidden field không hiển thị cho người dùng nhưng được gửi trong POST. Nó không phải bí mật và không có tác dụng chống giả mạo. Vai trò của nó chỉ là mang version mà form đã đọc đến server.

Nếu Spring Security bật CSRF, form POST cũng phải gửi CSRF token. Thymeleaf/Spring Security có thể tự thêm token trong một số cấu hình tích hợp; nếu không, thêm hidden field `_csrf` theo cấu hình ứng dụng. Không dùng version token thay cho CSRF token: hai token giải quyết hai vấn đề khác nhau.

## 10. Trang phản hồi khi có xung đột

Trang `templates/books/edit-conflict.html` cần nói rõ điều gì đã xảy ra và đưa ra lựa chọn an toàn. Ví dụ:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Dữ liệu sách đã thay đổi</title>
</head>
<body>
<main>
    <h1>Không thể lưu thay đổi</h1>
    <p>
        Một người dùng khác đã cập nhật cuốn sách sau khi bạn mở biểu mẫu.
        Thay đổi vừa gửi chưa được lưu.
    </p>

    <section>
        <h2>Dữ liệu bạn vừa gửi</h2>
        <dl>
            <dt>Tên sách</dt>
            <dd th:text="${submitted.title}">Tên sách đã nhập</dd>
            <dt>Tác giả</dt>
            <dd th:text="${submitted.author}">Tác giả đã nhập</dd>
            <dt>ISBN</dt>
            <dd th:text="${submitted.isbn}">ISBN đã nhập</dd>
        </dl>
    </section>

    <section>
        <h2>Dữ liệu mới nhất</h2>
        <dl>
            <dt>Tên sách</dt>
            <dd th:text="${latest.title}">Tên sách hiện tại</dd>
            <dt>Tác giả</dt>
            <dd th:text="${latest.author}">Tác giả hiện tại</dd>
            <dt>ISBN</dt>
            <dd th:text="${latest.isbn}">ISBN hiện tại</dd>
        </dl>
    </section>

    <a th:href="@{/books/{id}/edit(id=${bookId})}">Tải lại biểu mẫu mới nhất</a>
    <a th:href="@{/books/{id}(id=${bookId})}">Quay lại chi tiết sách</a>
</main>
</body>
</html>
```

Trang xung đột có thể cho người dùng xem phần đã gửi và bản mới nhất. Với dữ liệu phức tạp, giao diện có thể hiển thị so sánh từng trường và cho phép sao chép thủ công các thay đổi cần giữ. Nếu người dùng chọn tải lại form, server phải cấp version mới nhất.

Không nên tự động đổi hidden version cũ thành version mới rồi gửi lại toàn bộ dữ liệu cũ. Làm như vậy sẽ bỏ qua kiểm soát xung đột và quay lại hành vi ghi đè âm thầm.

## 11. Vì sao phải xử lý cả lỗi ở thời điểm commit?

Kiểm tra `book.getVersion() == command.version()` bảo vệ trường hợp dữ liệu đã cũ trước khi Service tải entity. Nhưng có thể xảy ra lịch trình sau:

1. Request A tải version `7`.
2. Request B tải version `7`.
3. Cả A và B đều so sánh form version `7` với entity version `7`, nên đều vượt qua.
4. A flush và commit, database tăng version thành `8`.
5. B flush với điều kiện version `7`; database không cập nhật hàng nào.
6. JPA ném optimistic locking exception; transaction B rollback.

Đó là lý do cần cả kiểm tra version đầu vào lẫn `@Version` của JPA. Chỉ kiểm tra ở Service mà không dùng version locking trong persistence vẫn có race condition giữa bước đọc và ghi.

Trong môi trường có transaction lồng nhau, cần xem xét nơi exception thực sự xuất hiện. Nếu Service được gọi bên trong transaction lớn hơn, commit có thể diễn ra ở caller chứ không phải tại ranh giới Service. Xử lý lỗi nên đặt ở ranh giới hoàn tất transaction hoặc dùng exception handler thống nhất cho toàn ứng dụng.

## 12. API cũng cần phản hồi xung đột rõ ràng

Nếu cùng use case được cung cấp qua REST API, server có thể trả `409 Conflict` cùng mã lỗi ổn định. Ví dụ:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://example.com/problems/book-version-conflict",
  "title": "Dữ liệu sách đã thay đổi",
  "status": 409,
  "code": "BOOK_VERSION_CONFLICT",
  "detail": "Hãy tải lại dữ liệu trước khi lưu thay đổi."
}
```

Client có thể hiển thị thông báo, tải lại representation mới nhất hoặc mở giao diện so sánh. Không nên trả `200 OK` cho một cập nhật đã bị từ chối vì xung đột; client cần biết thao tác chưa thành công.

Với REST, một lựa chọn khác là dùng HTTP conditional request: server trả `ETag` đại diện cho version và client gửi `If-Match` khi cập nhật. Nếu representation đã thay đổi, server trả `412 Precondition Failed`. Cách này đưa concurrency token vào HTTP protocol thay vì body JSON.

Ví dụ:

```http
GET /api/books/42
```

```http
HTTP/1.1 200 OK
ETag: "book-42-v7"
Content-Type: application/json
```

Client gửi điều kiện khi cập nhật:

```http
PUT /api/books/42
If-Match: "book-42-v7"
Content-Type: application/json

{
  "title": "Thiết kế phần mềm",
  "author": "Nguyễn An",
  "isbn": "9780000000000"
}
```

Nếu ETag không còn khớp, server trả `412 Precondition Failed`. `409 Conflict` thường phù hợp với xung đột nghiệp vụ tổng quát; `412` phù hợp khi điều kiện HTTP như `If-Match` không được đáp ứng. Hãy chọn một hợp đồng nhất quán và mô tả rõ cho client.

## 13. Optimistic locking hay pessimistic locking?

Optimistic locking không giữ khóa ghi trong toàn bộ thời gian người dùng mở form. Nó phù hợp khi xung đột ít xảy ra và muốn nhiều người đọc/sửa song song.

Pessimistic locking yêu cầu database khóa bản ghi trong một transaction để ngăn transaction khác cập nhật đồng thời. Ví dụ với Spring Data JPA:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select b from Book b where b.id = :id")
Optional<Book> findForUpdate(@Param("id") long id);
```

Đây là phương thức bổ sung vào `BookRepository` đã khai báo ở phần trước; cần gọi nó bên trong transaction đang hoạt động.

Pessimistic lock có thể phù hợp khi xung đột thường xuyên, thao tác ngắn và cần tuần tự hóa cập nhật. Nhưng không nên giữ khóa trong suốt thời gian người dùng suy nghĩ hoặc nhập form. Giữ transaction mở qua nhiều phút sẽ làm tăng thời gian khóa, nguy cơ deadlock và giảm khả năng phục vụ request khác.

| Tiêu chí | Optimistic locking | Pessimistic locking |
|---|---|---|
| Cách phát hiện/xử lý | So sánh version lúc ghi | Khóa bản ghi trong transaction |
| Phù hợp | Xung đột hiếm, nhiều lượt đọc | Tranh chấp cao, thao tác ngắn |
| Khi xung đột | Một transaction thất bại và cần xử lý lại | Transaction khác phải chờ hoặc bị timeout |
| Chi phí | Ít khóa, cần xử lý lỗi optimistic | Có thể chặn request, cần quản lý lock timeout/deadlock |
| Form mở lâu | Phù hợp vì không giữ khóa khi người dùng nhập | Không phù hợp để khóa từ lúc mở form |

Với màn hình quản lý sách, optimistic locking thường là lựa chọn tự nhiên: người dùng có thể mở form trong thời gian dài và chỉ cần kiểm tra version khi lưu.

## 14. Không tự động retry một cập nhật đã lỗi version

Khi optimistic locking thất bại, một số thao tác backend có thể được retry nếu có thể tải lại trạng thái và tính toán lại kết quả an toàn. Nhưng với biểu mẫu do người dùng nhập, retry tự động bằng dữ liệu cũ thường không đúng.

Ví dụ, Bình gửi tiêu đề và tác giả dựa trên version `7`. Nếu server tự tải version `8`, thay version trong command rồi ghi lại các trường cũ, nó đã bỏ qua ý định của An và ghi đè dữ liệu mới.

Thay vào đó:

- Trả xung đột cho người dùng.
- Hiển thị bản gửi lên và bản mới nhất.
- Cho phép người dùng chọn tải lại hoặc hợp nhất thủ công.
- Nếu có quy tắc merge tự động, chỉ áp dụng cho trường độc lập và có chính sách rõ ràng.
- Ghi nhận hành động cuối cùng bằng một request mới với version mới nhất.

Không nhầm retry với idempotency. Idempotency bảo vệ việc gửi lặp cùng một yêu cầu; optimistic locking bảo vệ khỏi cập nhật dựa trên trạng thái cũ. Hai vấn đề có thể cùng xuất hiện trong một API.

## 15. Kiểm thử luồng cập nhật và xung đột

Một bộ test tốt cần kiểm tra cả trường hợp cập nhật bình thường, form đã cũ trước khi gửi và cuộc đua xảy ra trong lúc hai transaction cùng cập nhật.

### Unit test cho kiểm tra version cũ

Có thể kiểm tra Service từ chối command có version không khớp:

```java
@Test
void rejectsCommandBasedOnOldVersion() {
    Book book = bookWithVersion(8L);
    given(bookRepository.findById(42L)).willReturn(Optional.of(book));

    UpdateBookCommand staleCommand = new UpdateBookCommand(
            7L, "Tên mới", "Tác giả mới", "9780000000000");

    assertThatThrownBy(() -> service.update(42L, 10L, staleCommand))
            .isInstanceOf(BookConflictException.class);

    assertThat(book.getTitle()).isNotEqualTo("Tên mới");
    then(bookRepository).should().findById(42L);
}
```

`bookWithVersion` là fixture tạo entity có version được kiểm soát trong test. Trong JPA thực tế, trường version do provider quản lý; test unit có thể dùng fixture hoặc factory chuyên dụng, còn test tích hợp phải xác nhận version thật trong database.

### MVC test cho response xung đột

Mock Service ném `BookConflictException` để kiểm tra Controller trả trang xung đột và status `409`:

```java
mockMvc.perform(post("/books/{id}", 42L)
        .with(user("librarian"))
        .with(csrf())
        .param("version", "7")
        .param("title", "Tên sách đã sửa")
        .param("author", "Tác giả")
        .param("isbn", "9780000000000"))
    .andExpect(status().isConflict())
    .andExpect(view().name("books/edit-conflict"))
    .andExpect(model().attributeExists("submitted", "latest"));
```

Test cần cấu hình principal phù hợp với `AppUserPrincipal` của ứng dụng. `.with(user("librarian"))` chỉ phù hợp nếu Controller dùng principal mặc định hoặc cấu hình test đã chuyển đổi đúng kiểu. Trong ứng dụng thực tế có thể dùng `@WithUserDetails` hoặc custom security test support. CSRF token được gửi vì đây là POST dùng session/cookie security.

### Integration test cho optimistic locking thật

Unit test không chứng minh JPA tạo câu lệnh có version predicate. Hãy có integration test dùng database tương thích production và hai bản entity được tải trong hai persistence context/transaction độc lập.

Ví dụ khung với `TransactionTemplate`:

```java
Book firstCopy = transactionTemplate.execute(status ->
        bookRepository.findById(bookId).orElseThrow());

Book secondCopy = transactionTemplate.execute(status ->
        bookRepository.findById(bookId).orElseThrow());

transactionTemplate.executeWithoutResult(status -> {
    firstCopy.updateDetails("Tên do An sửa", "Tác giả", "9780000000000");
    bookRepository.save(firstCopy);
    bookRepository.flush();
});

assertThatThrownBy(() -> transactionTemplate.executeWithoutResult(status -> {
    secondCopy.updateDetails("Tên do Bình sửa", "Tác giả", "9780000000000");
    bookRepository.save(secondCopy);
    bookRepository.flush();
})).isInstanceOf(OptimisticLockingFailureException.class);
```

Đây là khung kiểm thử; cần cấu hình `TransactionTemplate` dùng transaction manager của test và bảo đảm test không bị bao bởi một transaction ngoài làm hai lần đọc dùng chung persistence context. Sau khi lần ghi thứ nhất commit, lần ghi thứ hai dùng version cũ phải thất bại. Kiểm tra database cuối cùng vẫn chứa thay đổi của An.

### Các trường hợp nên có trong bộ test

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Form version hiện tại | Cập nhật thành công, version tăng |
| Form version cũ trước khi POST | Service từ chối, không đổi dữ liệu |
| Hai transaction cùng đọc một version | Chỉ một transaction commit thành công |
| Form thiếu tiêu đề | Validation trả form, không cập nhật |
| Người dùng không có quyền sửa | Request bị từ chối, không lộ dữ liệu ngoài phạm vi |
| Sách đã bị xóa | Trả `404` hoặc kết quả theo hợp đồng ứng dụng |
| Request gửi version giả | Không vượt qua kiểm tra quyền hoặc kiểm tra version |
| Cập nhật thành công rồi refresh browser | PRG tránh gửi lại POST ngoài ý muốn |

## 16. Những lỗi thường gặp khi kiểm soát cập nhật đồng thời

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ khai báo `@Version`, không gửi/so sánh version của form | Dữ liệu form cũ có thể ghi đè entity vừa được tải ở version mới | Gửi concurrency token và so sánh với entity hiện tại |
| Tự tăng version trong Controller hoặc Service | Xung đột với cơ chế quản lý version của JPA | Để persistence provider quản lý `@Version` |
| Bind request trực tiếp vào entity | Mass assignment và thay đổi trường ngoài ý muốn | Dùng Form/DTO/Command có allowlist trường |
| Bắt lỗi optimistic locking nhưng trả `200 OK` | Client tưởng cập nhật đã thành công | Trả trang xung đột hoặc status `409`/`412` theo hợp đồng |
| Tự động đổi version cũ thành version mới rồi lưu lại | Vô hiệu hóa kiểm soát xung đột | Yêu cầu người dùng xem lại và gửi request mới |
| Chỉ test bằng mock repository | Không kiểm tra version predicate thực tế | Bổ sung integration test với JPA và database |
| Dùng pessimistic lock khi người dùng mở form | Giữ khóa lâu, gây chặn và deadlock | Dùng optimistic locking cho form mở lâu |
| Dùng `@Version` nhưng bulk update không cập nhật version | Bỏ qua cơ chế kiểm soát của entity | Tự thêm version predicate, tăng version và kiểm tra row count |
| Coi version là bằng chứng phân quyền | Người dùng có thể giả mạo version | Kiểm tra authentication và authorization độc lập |

## 17. Quy trình triển khai luồng cập nhật có kiểm soát xung đột

Khi xây dựng màn hình chỉnh sửa một cuốn sách, có thể làm theo thứ tự:

1. Xác định các trường người dùng được phép sửa và các quy tắc validation.
2. Thêm trường `@Version` vào entity và migration database.
3. Tạo form object/command có concurrency token, không bind trực tiếp vào entity.
4. Khi GET form, tải dữ liệu và version hiện tại rồi đưa vào Model.
5. Template gửi version bằng hidden field cùng các trường được phép cập nhật.
6. Controller lấy actor từ security context, kiểm tra validation và chuyển thành command.
7. Service tải entity trong transaction, kiểm tra quyền và so sánh version được gửi.
8. Cập nhật entity; để JPA kiểm tra version lần nữa khi flush/commit.
9. Ánh xạ stale version hoặc optimistic locking exception thành phản hồi xung đột.
10. Hiển thị bản gửi lên và bản mới nhất; cho phép tải lại hoặc hợp nhất có chủ đích.
11. Kiểm thử stale form và hai transaction cạnh tranh bằng database thật.

Kiểm soát xung đột là một phần của hợp đồng cập nhật, không chỉ là chi tiết của ORM. MVC chuyển concurrency token từ lúc hiển thị form đến request POST; Service xác minh người dùng đang sửa phiên bản nào; `@Version` bảo vệ khoảng thời gian giữa đọc và ghi; Controller trả phản hồi để người dùng xử lý thay đổi đồng thời. Khi cả các bước này được thiết kế rõ, ứng dụng quản lý sách có thể ngăn mất cập nhật mà không cần khóa bản ghi trong suốt thời gian người dùng chỉnh sửa.
