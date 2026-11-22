# Phân loại lỗi đầu vào, lỗi nghiệp vụ và lỗi hạ tầng

## 1. Vì sao cần phân loại lỗi trong MVC?

Trong ứng dụng Model–View–Controller, một request có thể thất bại vì nhiều nguyên nhân. Người dùng có thể gửi dữ liệu sai định dạng; một hành động có thể vi phạm quy tắc của miền; hoặc cơ sở dữ liệu, mạng hay dịch vụ bên ngoài có thể gặp sự cố. Dù tất cả đều dẫn đến một response không thành công, chúng không có cùng ý nghĩa và không nên được xử lý theo cùng một cách.

Phân loại lỗi giúp ứng dụng quyết định:

- Ai có thể khắc phục vấn đề: người dùng, quy trình nghiệp vụ hay đội vận hành.
- Thành phần nào chịu trách nhiệm phát hiện và chuyển lỗi.
- Có nên yêu cầu người dùng sửa dữ liệu, thử lại hay liên hệ hỗ trợ.
- Response nào phù hợp với giao diện HTML hoặc API.
- Thông tin nào được phép hiển thị và thông tin nào chỉ được ghi trong log nội bộ.

Trong MVC, Controller là nơi điều phối request và response, nhưng không phải nơi duy nhất phát hiện lỗi. Binding và validation phát hiện lỗi đầu vào; Model hoặc Service phát hiện lỗi nghiệp vụ; Repository và adapter hạ tầng phát hiện lỗi kỹ thuật. Một thiết kế tốt giữ lỗi gần với nơi có đủ ngữ cảnh để nhận diện, sau đó chuyển nó qua ranh giới phù hợp để Controller hoặc exception handler tạo phản hồi nhất quán.

## 2. Ba nhóm lỗi chính

### Lỗi đầu vào (Input Errors)

Lỗi đầu vào xảy ra khi dữ liệu request không đáp ứng hợp đồng mà endpoint yêu cầu. Ví dụ:

- Trường bắt buộc bị bỏ trống.
- Chuỗi ngày không thể chuyển thành `LocalDate`.
- UUID sai định dạng.
- Số lượng âm hoặc vượt giới hạn được công bố.
- JSON sai cú pháp hoặc thiếu thuộc tính bắt buộc.
- Một lựa chọn không thuộc tập giá trị mà API cho phép.

Những lỗi này thường có thể được người dùng sửa bằng cách nhập lại dữ liệu. Chúng được phát hiện ở binding, validation hoặc lớp chuyển đổi request. Với biểu mẫu HTML, phản hồi thường giữ lại giá trị an toàn và hiển thị lỗi cạnh trường tương ứng. Với API, response nên nêu trường nào không hợp lệ và lý do ở mức client có thể hành động.

### Lỗi nghiệp vụ (Business Errors)

Lỗi nghiệp vụ xảy ra khi dữ liệu có thể đúng cú pháp và đúng kiểu, nhưng hành động không hợp lệ theo quy tắc hoặc trạng thái hiện tại của miền. Ví dụ:

- ISBN đã được một cuốn sách khác sử dụng.
- Không thể mượn sách đang được người khác mượn.
- Không thể hủy đơn hàng đã giao.
- Không thể chuyển một hồ sơ đã đóng trở lại trạng thái đang xử lý.
- Người dùng vượt hạn mức đăng ký theo chính sách.

Lỗi nghiệp vụ không nhất thiết là lỗi do người dùng nhập sai. Có thể người dùng đã nhập dữ liệu hợp lệ, nhưng trạng thái hệ thống thay đổi trước khi thao tác được thực hiện. Phản hồi cần giải thích điều kiện nghiệp vụ nào không được đáp ứng và gợi ý hành động tiếp theo nếu có.

### Lỗi hạ tầng (Infrastructure Errors)

Lỗi hạ tầng xảy ra khi một thành phần kỹ thuật không thể thực hiện công việc được yêu cầu. Ví dụ:

- Database không kết nối được hoặc hết connection.
- Transaction bị deadlock hoặc timeout.
- Dịch vụ thanh toán bên ngoài không phản hồi.
- DNS, mạng hoặc TLS gặp sự cố.
- Không thể ghi tệp do hết dung lượng hoặc thiếu quyền hệ thống.
- Message broker hoặc hệ thống lưu trữ tạm thời không khả dụng.

Người dùng thường không thể sửa các lỗi này bằng cách thay đổi trường dữ liệu. Ứng dụng cần ghi nhận sự cố với thông tin tương quan, trả phản hồi an toàn và có thể cho phép thử lại khi lỗi thực sự tạm thời.

## 3. So sánh ba nhóm lỗi

| Tiêu chí | Lỗi đầu vào | Lỗi nghiệp vụ | Lỗi hạ tầng |
|---|---|---|---|
| Bản chất | Request không đáp ứng hợp đồng dữ liệu | Hành động không hợp lệ theo quy tắc hoặc trạng thái miền | Thành phần kỹ thuật không thể hoàn thành công việc |
| Nơi thường phát hiện | Binding, parser, validation | Entity, Value Object, Domain Service, Application Service | Repository, database driver, HTTP client, filesystem, message adapter |
| Ai có thể khắc phục? | Người gửi request | Người dùng hoặc quy trình nghiệp vụ sau khi điều kiện thay đổi | Đội vận hành hoặc cơ chế phục hồi; đôi khi client thử lại |
| Ví dụ | Ngày sai định dạng | Sách đã được mượn | Database timeout |
| Phản hồi thường dùng | Lỗi theo trường hoặc lỗi request | Thông báo điều kiện nghiệp vụ không thỏa | Thông báo hệ thống tạm thời hoặc lỗi chung |
| Log | Thường không cần ghi stack trace ở mức error cho mọi lần nhập sai | Ghi mã lỗi và ngữ cảnh nghiệp vụ phù hợp | Ghi exception, dependency, trace/correlation ID và nguyên nhân kỹ thuật |

Không phân loại chỉ dựa trên việc exception được ném ở tầng nào. Ví dụ, `IllegalArgumentException` có thể là lỗi lập trình nếu một Service nội bộ gọi sai API, nhưng cũng có thể xuất hiện khi một thư viện parse dữ liệu người dùng. Hãy phân loại theo ý nghĩa của lỗi trong hợp đồng ứng dụng, không chỉ theo tên class Java.

## 4. Theo dõi lỗi qua các tầng MVC

Một request tạo sách có thể đi qua các ranh giới sau:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Controller / Binding]
    B -->|Sai kiểu hoặc thiếu trường| I1[Lỗi đầu vào]
    B -->|Dữ liệu hợp lệ về cấu trúc| C[Application Service]
    C --> D[Domain Model]
    D -->|Vi phạm invariant hoặc trạng thái| I2[Lỗi nghiệp vụ]
    C --> E[Repository port]
    E --> F[Infrastructure adapter]
    F -->|Database, mạng, filesystem lỗi| I3[Lỗi hạ tầng]
    F --> G[Thành công]
    G --> H[Controller chọn View hoặc response]
    I1 --> H
    I2 --> H
    I3 --> H
~~~

Sơ đồ là luồng khái niệm. Trong một ứng dụng cụ thể, Repository có thể được gọi từ Service, Domain Model có thể phát sinh lỗi trước hoặc sau khi truy cập dữ liệu, và framework có thể bắt một số lỗi trước khi Controller được gọi.

Điểm quan trọng là không đưa mọi lỗi về một `catch (Exception)` trong Controller. Mỗi tầng nên biểu diễn lỗi theo ngữ nghĩa mà tầng đó hiểu:

- Controller/binding biết request có chuyển đổi được hay không.
- Domain biết hành động có giữ được invariant hay không.
- Application Service biết use case có thể tiếp tục trong trạng thái hiện tại hay không.
- Adapter hạ tầng biết thao tác kỹ thuật thất bại vì nguyên nhân nào.

## 5. Thiết kế lỗi đầu vào

Lỗi đầu vào thường được phát hiện bằng hai bước: binding và validation.

**Binding** chuyển dữ liệu thô thành kiểu dữ liệu ứng dụng. Nếu `publishedDate=tomorrow` không thể chuyển thành `LocalDate`, đây là lỗi chuyển đổi. Controller chưa nên gọi nghiệp vụ với một đối tượng đầu vào chưa được binding thành công.

**Validation** kiểm tra ràng buộc trên Form DTO hoặc Request DTO. Ví dụ `@NotBlank`, `@Size`, `@Email`, `@Min` và `@Max` xác minh dữ liệu có đáp ứng hợp đồng đầu vào hay không.

### Ví dụ Form DTO

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateBookRequest(
        @NotBlank(message = "Tiêu đề không được để trống")
        @Size(max = 200, message = "Tiêu đề tối đa 200 ký tự")
        String title,

        @NotBlank(message = "ISBN không được để trống")
        String isbn,

        @Min(value = 1, message = "Số lượng tối thiểu là 1")
        @Max(value = 1000, message = "Số lượng tối đa là 1000")
        int copies
) {}
~~~

Với Spring MVC, một handler có thể dùng `@Valid` và `BindingResult` để trả lại form:

~~~java
@PostMapping("/books")
public String create(
        @Valid @ModelAttribute("form") CreateBookRequest form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "books/form";
    }

    bookService.create(form);
    return "redirect:/books";
}
~~~

`BindingResult` phải đứng ngay sau đối tượng được binding và validation. Khi có lỗi, Controller trả lại template hiện tại để giữ giá trị và thông báo. Nếu dùng `@RequestBody @Valid` cho JSON API, Spring có thể phát sinh `MethodArgumentNotValidException` khi validation thất bại; lỗi parse hoặc chuyển đổi request có thể phát sinh exception khác.

### Validation không thay thế invariant

Không đặt toàn bộ quy tắc quan trọng ở Form DTO. Biểu mẫu có thể kiểm tra `copies` lớn hơn 0, nhưng quy tắc này vẫn cần được bảo vệ ở Model nếu mọi nguồn tạo sách đều phải tuân thủ. API, import batch và tác vụ nền có thể không đi qua cùng Form DTO.

Validation đầu vào trả lời câu hỏi “request có đúng hình dạng và ràng buộc được công bố không?”. Invariant miền trả lời câu hỏi “trạng thái đối tượng có còn hợp lệ sau hành động này không?”. Hai câu hỏi có liên quan nhưng ở hai ranh giới khác nhau.

## 6. Thiết kế lỗi nghiệp vụ

Lỗi nghiệp vụ nên có tên diễn đạt điều kiện miền không được đáp ứng. Tránh dùng một exception chung như `RuntimeException("Invalid")` cho mọi tình huống.

Ví dụ:

~~~java
public class DuplicateIsbnException extends RuntimeException {
    public DuplicateIsbnException(String isbn) {
        super("ISBN đã tồn tại: " + isbn);
    }
}

public class BookNotAvailableException extends RuntimeException {
    public BookNotAvailableException(BookId id) {
        super("Sách không khả dụng: " + id);
    }
}

public class LoanLimitExceededException extends RuntimeException {
    public LoanLimitExceededException(MemberId memberId) {
        super("Độc giả đã đạt giới hạn mượn sách: " + memberId);
    }
}
~~~

Thông điệp trong exception có thể hữu ích cho log nội bộ, nhưng không nên tự động trả nguyên văn cho client. Lớp trình bày nên ánh xạ loại lỗi sang thông điệp an toàn, có thể dịch và không tiết lộ định danh nhạy cảm.

### Quy tắc nằm ở đâu?

- Invariant của một Value Object như ISBN đúng định dạng nên được bảo vệ khi tạo Value Object.
- Quy tắc trạng thái của Entity như không thể mượn sách đã được mượn nên được bảo vệ trong hành vi của Entity hoặc Aggregate phù hợp.
- Quy tắc phối hợp nhiều Entity hoặc phụ thuộc dữ liệu như ISBN duy nhất có thể cần Application Service, Repository và constraint cơ sở dữ liệu.
- Quy tắc điều phối use case như người dùng chỉ được tạo một đăng ký đang hoạt động có thể thuộc Application Service hoặc Domain Service tùy mô hình.

Không phải mọi điều kiện đều nên được kiểm tra trong Controller. Nếu chỉ kiểm tra ở Controller, các luồng gọi Service trực tiếp có thể bỏ qua quy tắc.

### Ví dụ Service phát sinh lỗi nghiệp vụ

~~~java
@Service
public class BookService {
    private final BookRepository books;

    public BookService(BookRepository books) {
        this.books = books;
    }

    @Transactional
    public Book create(CreateBookCommand command) {
        Isbn isbn = new Isbn(command.isbn());

        if (books.existsByIsbn(isbn)) {
            throw new DuplicateIsbnException(isbn.value());
        }

        Book book = Book.create(
                BookId.newId(),
                isbn,
                command.title(),
                command.copies());
        return books.save(book);
    }
}
~~~

Ví dụ giả định các kiểu miền và Repository đã được định nghĩa. Kiểm tra `existsByIsbn` tạo thông báo sớm, nhưng hai request đồng thời vẫn có thể cùng thấy ISBN chưa tồn tại. Cơ sở dữ liệu cần unique constraint để bảo đảm tính duy nhất; lỗi constraint cần được chuyển thành lỗi nghiệp vụ tương ứng tại adapter hoặc lớp application phù hợp.

## 7. Thiết kế lỗi hạ tầng

Lỗi hạ tầng thường xuất hiện tại ranh giới giao tiếp với hệ thống bên ngoài. Adapter nên chuyển exception đặc thù của thư viện hoặc driver thành lỗi mà ứng dụng hiểu được, đồng thời giữ nguyên nguyên nhân gốc để chẩn đoán.

Ví dụ, tầng persistence có thể gặp `SQLException`, lỗi timeout của driver hoặc exception từ ORM. Service không nên phụ thuộc vào mọi class exception của một database vendor nếu nghiệp vụ chỉ cần biết thao tác lưu trữ không thể hoàn tất.

### Exception translation

Spring cung cấp hệ thống exception translation cho một số công nghệ persistence. Với Spring JDBC và Spring Data, lỗi truy cập dữ liệu thường được chuyển thành hệ phân cấp `DataAccessException`, giúp mã ứng dụng ít phụ thuộc vào exception riêng của driver.

Một adapter tự viết có thể chuyển lỗi cụ thể:

~~~java
public class BookStoreUnavailableException extends RuntimeException {
    public BookStoreUnavailableException(Throwable cause) {
        super("Không thể truy cập kho sách", cause);
    }
}

public class JdbcBookRepository implements BookRepository {
    private final JdbcClient jdbc;

    public JdbcBookRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public Book save(Book book) {
        try {
            // Thực hiện câu lệnh lưu và ánh xạ kết quả.
            return persist(book);
        } catch (DataAccessResourceFailureException exception) {
            throw new BookStoreUnavailableException(exception);
        }
    }
}
~~~

Đây là ví dụ minh họa; `persist` đại diện cho phần triển khai truy vấn thực tế. Chỉ chuyển những lỗi mà adapter có thể diễn giải chính xác. Không bắt tất cả `RuntimeException` rồi đổi thành “database unavailable”, vì như vậy lỗi lập trình như `NullPointerException` cũng bị che thành lỗi hạ tầng.

### Phân biệt lỗi tạm thời và lỗi lâu dài

Một lỗi hạ tầng có thể tạm thời hoặc cần can thiệp:

- Timeout mạng có thể tạm thời.
- Database đang failover có thể phục hồi sau một khoảng ngắn.
- Sai mật khẩu cấu hình thường không tự phục hồi nếu không sửa cấu hình.
- Thiếu quyền truy cập file thường cần điều chỉnh quyền hoặc cấu hình.
- Dữ liệu database vi phạm constraint có thể phản ánh lỗi nghiệp vụ hoặc lỗi đồng bộ dữ liệu, không nhất thiết là lỗi hạ tầng tạm thời.

Chỉ retry khi nguyên nhân có khả năng phục hồi, thao tác an toàn để thực hiện lại và có giới hạn số lần/thời gian. Không retry vô hạn hoặc retry thao tác tạo thanh toán mà không có idempotency key.

## 8. Chuyển lỗi thành response tại ranh giới web

Controller hoặc cơ chế xử lý ngoại lệ tập trung chuyển lỗi nội bộ thành response cho client. Không để mỗi Service tự tạo HTML hoặc JSON, vì Service không nên phụ thuộc vào giao thức HTTP.

Một quy ước phổ biến cho ứng dụng web:

| Nhóm lỗi | Phản hồi HTML | Phản hồi API thường gặp |
|---|---|---|
| Đầu vào không hợp lệ | Trả lại form, gắn lỗi theo trường | `400 Bad Request` hoặc `422 Unprocessable Content` theo hợp đồng |
| Nghiệp vụ xung đột trạng thái | Trang thông báo hoặc form với lỗi nghiệp vụ | `409 Conflict` hoặc mã phù hợp theo ngữ nghĩa |
| Tài nguyên không tồn tại | Trang 404 | `404 Not Found` |
| Không xác thực/không đủ quyền | Đăng nhập hoặc trang từ chối theo chính sách | `401 Unauthorized` / `403 Forbidden` |
| Hạ tầng tạm thời | Trang lỗi có thể thử lại | `503 Service Unavailable` khi phù hợp |
| Lỗi không dự kiến | Trang lỗi chung | `500 Internal Server Error` |

Đây là quy ước phổ biến, không phải ánh xạ cứng cho mọi hệ thống. Chọn status theo semantics của HTTP và hợp đồng endpoint. Ví dụ, không phải mọi lỗi hạ tầng đều là `503`; một lỗi nội bộ không xác định thường là `500`. Không phải mọi lỗi nghiệp vụ đều là `409`; một số trường hợp có thể là `422` hoặc một response miền đã được tài liệu hóa.

### Ví dụ xử lý tập trung bằng Spring

~~~java
@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> handleInvalidInput(
            MethodArgumentNotValidException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Một hoặc nhiều trường dữ liệu không hợp lệ.");
        problem.setTitle("Dữ liệu đầu vào không hợp lệ");
        problem.setProperty(
                "errors",
                exception.getBindingResult().getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "message", safeMessage(error)))
                        .toList());
        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(DuplicateIsbnException.class)
    public ResponseEntity<ProblemDetail> handleDuplicateIsbn(
            DuplicateIsbnException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "ISBN đã được sử dụng cho một cuốn sách khác.");
        problem.setTitle("Không thể tạo sách");
        problem.setProperty("code", "BOOK_ISBN_DUPLICATE");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }

    @ExceptionHandler(BookStoreUnavailableException.class)
    public ResponseEntity<ProblemDetail> handleStoreUnavailable(
            BookStoreUnavailableException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Dịch vụ lưu trữ tạm thời không khả dụng. Vui lòng thử lại sau.");
        problem.setTitle("Dịch vụ tạm thời gián đoạn");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }
}
~~~

Ví dụ dùng `ProblemDetail` của Spring Framework 6 và giả định các helper/import cần thiết đã có. `safeMessage` cần trả thông điệp đã được kiểm soát, không lấy nguyên văn nội dung exception từ thư viện hoặc database. Trong ứng dụng thực tế, nên có handler cuối cùng cho lỗi không dự kiến, ghi log nội bộ rồi trả response `500` an toàn.

Với ứng dụng render HTML, dùng `@ControllerAdvice` và `ModelAndView` hoặc các trang lỗi được cấu hình. Có thể tách handler HTML và API theo package, controller hoặc content negotiation để tránh trả JSON cho một trang trình duyệt hay HTML cho client API.

## 9. Exception hay kết quả lỗi (Result)?

Không phải lỗi nào cũng cần được biểu diễn bằng exception. Hãy chọn dựa trên tính chất của tình huống và quy ước của tầng:

**Exception** phù hợp khi thao tác không thể tiếp tục theo luồng bình thường, hoặc khi framework đã có cơ chế lan truyền và xử lý ngoại lệ. Ví dụ database không kết nối được, không tìm thấy tài nguyên bắt buộc hoặc một hành động vi phạm trạng thái miền.

**Result type** phù hợp khi thất bại là kết quả dự kiến và caller thường cần phân nhánh. Ví dụ một thao tác kiểm tra điều kiện có thể trả `Available` hoặc `Unavailable` mà không nhất thiết là exception. Có thể dùng sealed interface hoặc kiểu kết quả tương tự.

~~~java
public sealed interface BorrowDecision
        permits BorrowDecision.Allowed, BorrowDecision.Rejected {

    record Allowed(Loan loan) implements BorrowDecision {}

    record Rejected(String reasonCode) implements BorrowDecision {}
}
~~~

Ví dụ, một use case kiểm tra trước khả năng mượn có thể trả `Rejected("BOOK_ALREADY_LOANED")`. Nếu caller chọn thực hiện một lệnh mượn và trạng thái đã thay đổi sau khi kiểm tra, Service vẫn phải kiểm tra lại điều kiện tại thời điểm ghi để tránh race condition.

Không nên dùng Result để che một lỗi kỹ thuật nghiêm trọng thành trạng thái nghiệp vụ bình thường. Tương tự, không nên dùng exception cho mọi nhánh điều khiển thông thường nếu điều đó làm mã khó đọc và tạo log nhiễu.

## 10. Retry, transaction và tính nhất quán

Phân loại lỗi giúp quyết định có nên retry:

- **Lỗi đầu vào:** không retry nguyên request với cùng dữ liệu; yêu cầu sửa dữ liệu.
- **Lỗi nghiệp vụ:** thường không retry ngay vì điều kiện miền chưa thay đổi; người dùng hoặc quy trình cần thực hiện hành động khác.
- **Lỗi hạ tầng tạm thời:** có thể retry có giới hạn nếu thao tác an toàn và có timeout.
- **Lỗi hạ tầng không tạm thời:** cần sửa cấu hình, quyền hoặc trạng thái hệ thống trước khi thử lại.

Transaction cần có ranh giới rõ. Nếu thao tác ghi dữ liệu thất bại, transaction manager có thể rollback theo cấu hình. Trong Spring, mặc định các `RuntimeException` và `Error` thường kích hoạt rollback, còn checked exception không tự động rollback trừ khi cấu hình `rollbackFor` hoặc quy tắc tương ứng.

~~~java
@Transactional(rollbackFor = ExternalPartnerException.class)
public void registerAndNotify(RegistrationCommand command)
        throws ExternalPartnerException {
    Registration registration = registrations.save(create(command));
    partnerGateway.notifyRegistration(registration);
}
~~~

Ví dụ minh họa rollback cho checked exception; nó không tự giải quyết vấn đề gọi hệ thống ngoài trong một transaction database. Nếu database commit thất bại sau khi dịch vụ ngoài đã nhận thông báo, hoặc dịch vụ ngoài thành công nhưng database rollback, hai hệ thống có thể lệch trạng thái. Với tích hợp quan trọng, cân nhắc transactional outbox, saga hoặc cơ chế bù trừ phù hợp.

Retry phải có backoff, giới hạn số lần và timeout tổng. Với thao tác có tác động như tạo đơn hàng hoặc thanh toán, cần idempotency key hoặc cơ chế chống ghi nhận lặp. Chỉ retry lỗi được xác định là tạm thời; không retry lỗi validation hay lỗi nghiệp vụ một cách mù quáng.

## 11. Logging và quan sát lỗi

Log cần hỗ trợ đội phát triển và vận hành tìm nguyên nhân mà không làm lộ dữ liệu người dùng.

| Loại lỗi | Cách ghi nhận thường phù hợp |
|---|---|
| Lỗi đầu vào thường gặp | Có thể ghi metric hoặc audit tổng hợp; tránh ghi stack trace ở mức error cho mọi request sai |
| Lỗi nghiệp vụ dự kiến | Ghi mã lỗi, use case và ID tương quan nếu cần; mức log theo mức độ quan trọng |
| Lỗi hạ tầng | Ghi exception gốc, dependency, thời gian, trace/correlation ID và thông tin retry |
| Lỗi không dự kiến | Ghi stack trace ở phía server, phân loại mức nghiêm trọng và phát tín hiệu giám sát |

Không ghi mật khẩu, access token, session ID, dữ liệu thanh toán hoặc toàn bộ payload form. Nếu cần biết request nào gây lỗi, dùng correlation ID hoặc trace ID thay vì đưa toàn bộ dữ liệu đầu vào vào log.

Metric có thể đếm số lỗi theo nhóm, endpoint và dependency. Theo dõi tỷ lệ lỗi, độ trễ, timeout và số lần retry giúp phát hiện vấn đề hạ tầng trước khi người dùng báo lỗi.

## 12. Những sai lầm thường gặp

- **Gộp mọi lỗi thành `400 Bad Request`:** lỗi nghiệp vụ và hạ tầng có ngữ nghĩa khác lỗi đầu vào.
- **Gộp mọi lỗi thành `500`:** client không biết khi nào cần sửa dữ liệu hoặc xử lý xung đột.
- **Chỉ validate trong Controller:** các luồng gọi Service khác có thể bỏ qua invariant nghiệp vụ.
- **Để Service trả HTTP status:** làm tầng nghiệp vụ phụ thuộc vào giao thức web.
- **Bắt `Exception` rồi trả thành công hoặc danh sách rỗng:** che giấu sự cố và tạo trạng thái sai.
- **Chuyển mọi exception thành lỗi hạ tầng:** lỗi lập trình có thể bị che mất và khó phát hiện.
- **Trả nguyên văn exception cho client:** có thể lộ SQL, tên bảng, đường dẫn, cấu hình hoặc thông tin nhạy cảm.
- **Retry mọi lỗi:** có thể lặp thao tác tạo dữ liệu, tăng tải hoặc kéo dài sự cố.
- **Không giữ nguyên cause khi chuyển exception:** làm mất thông tin cần cho chẩn đoán.
- **Không phân biệt lỗi tạm thời với lỗi cấu hình:** retry không giúp khắc phục sai mật khẩu hoặc thiếu quyền.

## 13. Kiểm thử phân loại và ánh xạ lỗi

Kiểm thử nên xác minh không chỉ loại lỗi mà cả tác động của nó:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Thiếu tiêu đề | Validation trả lỗi trường; Service không được gọi |
| Ngày sai định dạng | Binding thất bại; không tạo Entity |
| ISBN đã tồn tại | Lỗi nghiệp vụ có mã ổn định; không lưu bản ghi mới |
| Sách đang được mượn | Hành vi miền từ chối chuyển trạng thái |
| Database timeout | Lỗi hạ tầng giữ nguyên cause và được ánh xạ an toàn |
| Dịch vụ ngoài tạm ngừng | Retry theo policy hoặc response tạm thời; không lặp side effect |
| Lỗi không dự kiến | Response chung; chi tiết chỉ nằm trong log server |
| Client gửi trường nội bộ | Trường không được binding hoặc bị từ chối theo hợp đồng |

**Unit test** kiểm tra validation, invariant và Service phát sinh đúng loại lỗi. **Test Controller** xác minh View, status, body và header. **Integration test** kiểm tra exception translation, transaction rollback, constraint database và handler tập trung. Test retry cần xác minh số lần gọi, backoff/timeout theo cấu hình và tính idempotent của thao tác.

## 14. Kết luận

Lỗi đầu vào cho biết request không đáp ứng hợp đồng dữ liệu; lỗi nghiệp vụ cho biết hành động không hợp lệ theo quy tắc hoặc trạng thái miền; lỗi hạ tầng cho biết một thành phần kỹ thuật không thể hoàn thành công việc. Ba nhóm này cần cách phát hiện, thông điệp, logging và phục hồi khác nhau.

Khi thiết kế xử lý lỗi trong MVC, hãy xác định lỗi thuộc ranh giới nào, giữ ngữ nghĩa của nó khi truyền qua các tầng, ánh xạ thành response tại lớp web và chỉ tiết lộ thông tin cần thiết cho client. Phân loại đúng giúp người dùng biết cách khắc phục, hệ thống tránh retry nguy hiểm và đội vận hành tìm được nguyên nhân kỹ thuật.
