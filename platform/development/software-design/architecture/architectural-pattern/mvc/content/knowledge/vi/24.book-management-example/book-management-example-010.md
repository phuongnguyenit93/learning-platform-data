# Kiểm thử và truy vết một ca sử dụng hoàn chỉnh

Một ứng dụng quản lý sách có thể có nhiều chức năng: tra cứu danh mục, quản lý bản sao, đăng ký độc giả, mượn sách, gia hạn và trả sách. Để kiểm tra kiến trúc MVC một cách có ý nghĩa, nên chọn một ca sử dụng đi qua đầy đủ các ranh giới thay vì chỉ kiểm tra một Controller action riêng lẻ.

Bài này dùng ca **độc giả mượn một bản sao sách**. Người dùng mở trang sách, chọn bản sao đang có sẵn và gửi biểu mẫu. Ứng dụng xác minh danh tính, kiểm tra tình trạng độc giả, giới hạn số sách đang mượn, khóa bản sao để tránh hai người mượn cùng lúc, tạo phiếu mượn trong transaction và chuyển người dùng đến trang xác nhận.

Qua một luồng cụ thể, ta sẽ theo dõi request từ View đến Controller, Application Service, Domain Model và Repository; xác định dữ liệu nào được phép đi qua từng tầng; rồi xây dựng unit test, MVC test, integration test, security test và concurrency test. Phần cuối trình bày cách ghi log, correlation ID và trace để điều tra lỗi khi hệ thống chạy thật.

Các tên lớp và đoạn mã Spring MVC/JPA dưới đây là một thiết kế minh họa. Có thể thay framework hoặc ORM, nhưng trách nhiệm và các bất biến cần kiểm tra vẫn giữ nguyên.

## 1. Xác định ca sử dụng và quy tắc nghiệp vụ

Một đầu sách có thể có nhiều bản sao vật lý. Độc giả mượn một bản sao cụ thể, không mượn một hàng danh mục trừu tượng.

Ví dụ:

- Đầu sách: *Thiết kế phần mềm hướng đối tượng*.
- Bản sao: COPY-1042.
- Độc giả: MEMBER-208.
- Thời hạn mượn: 14 ngày.
- Giới hạn đang mượn: 5 bản sao.

Trước khi viết Controller hoặc test, cần xác định các quy tắc:

1. Độc giả phải tồn tại và đang hoạt động.
2. Độc giả không được vượt quá giới hạn số bản sao đang mượn.
3. Bản sao phải thuộc đầu sách được yêu cầu và đang ở trạng thái AVAILABLE.
4. Một bản sao không thể được cấp cho hai phiếu mượn đang hiệu lực.
5. Khi mượn thành công, trạng thái bản sao chuyển sang ON_LOAN và một phiếu mượn ACTIVE được tạo.
6. Nếu một bước ghi thất bại, thay đổi liên quan phải rollback cùng transaction.
7. Danh tính độc giả lấy từ phiên đăng nhập đã xác thực, không lấy từ dữ liệu form.
8. Khi hai request tranh cùng một bản sao, chỉ một request được phép thành công.

Các quy tắc này là tiêu chí chấp nhận của ca sử dụng. Test nên kiểm tra kết quả nghiệp vụ và trạng thái lưu trữ, không chỉ kiểm tra Controller trả về một chuỗi view name.

### 1.1. Trạng thái của bản sao và phiếu mượn

Có thể mô hình hóa trạng thái bản sao:

~~~java
public enum CopyStatus {
    AVAILABLE,
    ON_LOAN,
    MAINTENANCE,
    LOST
}
~~~

Phiếu mượn có vòng đời riêng:

~~~java
public enum LoanStatus {
    ACTIVE,
    RETURNED,
    OVERDUE
}
~~~

Không nên dùng một cờ boolean chung như isBorrowed cho mọi trạng thái. Một bản sao đang bảo trì hoặc đã mất cũng không thể được mượn, nhưng lý do và cách xử lý khác nhau.

### 1.2. Bất biến của Domain Model

Domain Model bảo vệ chuyển trạng thái hợp lệ:

~~~java
@Entity
public class BookCopy {
    @Id
    private UUID id;

    private UUID bookId;

    @Enumerated(EnumType.STRING)
    private CopyStatus status;

    @Version
    private long version;

    protected BookCopy() {}

    public void borrow() {
        if (status != CopyStatus.AVAILABLE) {
            throw new BookCopyUnavailableException(id);
        }

        status = CopyStatus.ON_LOAN;
    }

    public void markReturned() {
        if (status != CopyStatus.ON_LOAN) {
            throw new InvalidCopyTransitionException(id, status);
        }

        status = CopyStatus.AVAILABLE;
    }

    public UUID id() {
        return id;
    }

    public UUID bookId() {
        return bookId;
    }

    public CopyStatus status() {
        return status;
    }
}
~~~

BookCopy.borrow() không biết HTTP status, Controller hoặc template. Nó chỉ bảo đảm bản sao chỉ chuyển từ AVAILABLE sang ON_LOAN.

Độc giả cũng có thể bảo vệ trạng thái:

~~~java
@Entity
public class LibraryMember {
    @Id
    private UUID id;

    private boolean active;

    private int borrowingLimit;

    @Version
    private long version;

    protected LibraryMember() {}

    public void ensureCanBorrow(long activeLoanCount) {
        if (!active) {
            throw new MemberNotActiveException(id);
        }

        if (activeLoanCount >= borrowingLimit) {
            throw new BorrowingLimitReachedException(id);
        }
    }

    public UUID id() {
        return id;
    }
}
~~~

Số phiếu đang mượn được truy vấn từ repository, còn chính sách giới hạn được kiểm tra bằng phương thức domain. Nếu hệ thống lưu bộ đếm đang mượn trên Member để tối ưu, bộ đếm đó phải được cập nhật nguyên tử và kiểm thử nhất quán với các phiếu mượn.

Phiếu mượn giữ thông tin của một lần giao dịch:

~~~java
@Entity
public class Loan {
    @Id
    private UUID id;

    private UUID memberId;
    private UUID bookCopyId;
    private Instant borrowedAt;
    private LocalDate dueDate;

    @Enumerated(EnumType.STRING)
    private LoanStatus status;

    protected Loan() {}

    private Loan(
        UUID id,
        UUID memberId,
        UUID bookCopyId,
        Instant borrowedAt,
        LocalDate dueDate
    ) {
        this.id = id;
        this.memberId = memberId;
        this.bookCopyId = bookCopyId;
        this.borrowedAt = borrowedAt;
        this.dueDate = dueDate;
        this.status = LoanStatus.ACTIVE;
    }

    public static Loan open(
        UUID memberId,
        UUID bookCopyId,
        Instant borrowedAt,
        LocalDate dueDate
    ) {
        if (!dueDate.isAfter(borrowedAt.atZone(ZoneOffset.UTC).toLocalDate())) {
            throw new InvalidLoanPeriodException();
        }

        return new Loan(
            UUID.randomUUID(),
            memberId,
            bookCopyId,
            borrowedAt,
            dueDate
        );
    }

    public UUID id() {
        return id;
    }
}
~~~

Trong dự án thực tế, cách tính ngày đến hạn nên nằm trong một policy/service có thể kiểm thử riêng và cần xác định rõ timezone, ngày nghỉ hoặc lịch thư viện. Ví dụ dùng UTC để tránh phụ thuộc timezone mặc định của máy chủ.

## 2. Xác định hợp đồng dữ liệu ở từng ranh giới

Không đưa toàn bộ BookCopy hoặc LibraryMember entity vào form. Người dùng chỉ cần chọn bản sao. Member ID được lấy từ principal.

Form Model:

~~~java
public record BorrowBookForm(
    @NotNull(message = "Hãy chọn bản sao sách")
    UUID copyId
) {}
~~~

Command của application:

~~~java
public record BorrowBookCommand(
    UUID bookId,
    UUID copyId,
    UUID memberId
) {}
~~~

Kết quả use case:

~~~java
public record BorrowBookResult(
    UUID loanId,
    LocalDate dueDate
) {}
~~~

Presentation Model cho trang chọn bản sao:

~~~java
public record CopyOption(
    UUID id,
    String label
) {}

public record BorrowBookPageModel(
    UUID bookId,
    String bookTitle,
    List<CopyOption> availableCopies
) {
    public BorrowBookPageModel {
        availableCopies = List.copyOf(availableCopies);
    }
}
~~~

Response cho trang xác nhận có thể dùng một model khác:

~~~java
public record LoanReceiptViewModel(
    UUID loanId,
    String bookTitle,
    String copyLabel,
    String dueDateText,
    String memberDisplayName
) {}
~~~

| Hợp đồng | Ai tạo | Ai sử dụng | Dữ liệu điển hình |
|---|---|---|---|
| BorrowBookForm | Binding của MVC | Controller | copyId |
| BorrowBookCommand | Controller | Application Service | bookId, copyId, memberId từ principal |
| Domain Model | Application/Domain | Quy tắc nghiệp vụ | trạng thái bản sao, độc giả, phiếu mượn |
| BorrowBookResult | Application Service | Controller | loanId, dueDate |
| BorrowBookPageModel | Query/Presentation Factory | View | tiêu đề sách, bản sao có thể chọn |
| LoanReceiptViewModel | Query/Presentation Factory | View | thông tin biên nhận đã định dạng |

Tách hợp đồng giúp giới hạn trường được ghi, tránh lộ dữ liệu nội bộ và cho phép thay đổi giao diện mà không phải thay cấu trúc entity.

## 3. Truy vết request qua kiến trúc MVC

Luồng thành công:

~~~mermaid
sequenceDiagram
    actor Reader as Độc giả
    participant View as Thymeleaf View
    participant C as BorrowBookController
    participant A as BorrowBookService
    participant M as Domain Model
    participant R as Repositories
    participant DB as Database

    Reader->>View: Mở trang mượn sách
    View->>C: GET /books/{bookId}/borrow
    C->>R: Tải sách và bản sao AVAILABLE
    R->>DB: SELECT
    DB-->>R: Dữ liệu sách
    R-->>C: Query result
    C-->>View: Form Model + Page Model

    Reader->>View: Chọn bản sao và gửi form
    View->>C: POST /books/{bookId}/borrow
    C->>C: Bind + validate + lấy principal
    C->>A: BorrowBookCommand
    A->>R: Lock Member
    R->>DB: SELECT FOR UPDATE
    A->>R: Đếm phiếu mượn ACTIVE
    A->>R: Lock BookCopy
    R->>DB: SELECT FOR UPDATE
    A->>M: Kiểm tra và chuyển trạng thái
    M-->>A: Hợp lệ
    A->>R: Lưu Loan
    A->>DB: UPDATE + INSERT
    DB-->>A: Commit
    A-->>C: BorrowBookResult
    C-->>View: Redirect /loans/{loanId}
    View-->>Reader: Biên nhận mượn sách
~~~

Luồng này có ba ranh giới cần quan sát:

- HTTP/presentation: request có được bind đúng và người dùng có được phép truy cập không?
- Application/domain: use case có kiểm tra đủ điều kiện và áp dụng quy tắc đúng không?
- Persistence/transaction: thay đổi bản sao và phiếu mượn có cùng commit hoặc rollback không?

Một test chỉ gọi borrowBookService.handle(...) không xác minh routing, CSRF, binding hoặc nội dung response. Ngược lại, test chỉ kiểm tra HTTP 302 không chứng minh database đã lưu đúng phiếu mượn.

## 4. Repository và khóa dữ liệu đồng thời

Nếu chỉ đọc trạng thái AVAILABLE rồi mới cập nhật, hai request có thể cùng nhìn thấy bản sao còn trống và cùng tạo phiếu mượn. Đây là race condition.

Một cách triển khai là khóa pessimistic trong transaction. Ví dụ Spring Data JPA:

~~~java
public interface BookCopyRepository
        extends JpaRepository<BookCopy, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select copy
        from BookCopy copy
        where copy.id = :copyId
        """)
    Optional<BookCopy> findByIdForUpdate(
        @Param("copyId") UUID copyId
    );
}
~~~

Repository của Member cũng khóa bản ghi:

~~~java
public interface MemberRepository
        extends JpaRepository<LibraryMember, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select member
        from LibraryMember member
        where member.id = :memberId
        """)
    Optional<LibraryMember> findByIdForUpdate(
        @Param("memberId") UUID memberId
    );
}
~~~

Đếm các phiếu đang hiệu lực:

~~~java
public interface LoanRepository extends JpaRepository<Loan, UUID> {
    long countByMemberIdAndStatus(
        UUID memberId,
        LoanStatus status
    );
}
~~~

Khóa Member trước khi đếm giúp tuần tự hóa các yêu cầu mượn đồng thời của cùng một độc giả, với điều kiện mọi luồng mượn đều tuân thủ cùng cơ chế khóa. Ví dụ này giả định isolation READ_COMMITTED: sau khi transaction thứ hai chờ khóa Member, câu lệnh đếm tiếp theo nhìn thấy phiếu mượn đã commit của transaction thứ nhất. Nếu dùng isolation có snapshot ổn định như REPEATABLE_READ, cần kiểm tra semantics của database; có thể phải xử lý serialization failure hoặc cập nhật một bộ đếm giới hạn theo cách nguyên tử. Khóa BookCopy bảo đảm hai độc giả không cùng nhận một bản sao.

Mọi use case có nhiều khóa nên tuân thủ thứ tự lấy khóa thống nhất, ví dụ Member trước rồi BookCopy, để giảm nguy cơ deadlock. Cần xác minh hành vi trên hệ quản trị database thực tế; không suy luận từ mock hoặc embedded database.

Một lựa chọn khác là optimistic locking với @Version. Khi có xung đột version, một transaction thất bại và ứng dụng có thể trả thông báo “Bản sao vừa được người khác mượn”. Với nghiệp vụ này, cần chọn cơ chế dựa trên mức tranh chấp và khả năng retry.

## 5. Application Service điều phối transaction

Use case mở transaction, khóa các bản ghi cần thiết, kiểm tra chính sách và lưu thay đổi:

~~~java
@Service
public class BorrowBookService {
    private final MemberRepository members;
    private final BookCopyRepository copies;
    private final LoanRepository loans;
    private final Clock clock;
    private final LoanPeriodPolicy loanPeriodPolicy;

    public BorrowBookService(
        MemberRepository members,
        BookCopyRepository copies,
        LoanRepository loans,
        Clock clock,
        LoanPeriodPolicy loanPeriodPolicy
    ) {
        this.members = members;
        this.copies = copies;
        this.loans = loans;
        this.clock = clock;
        this.loanPeriodPolicy = loanPeriodPolicy;
    }

    @Transactional
    public BorrowBookResult handle(BorrowBookCommand command) {
        LibraryMember member = members
            .findByIdForUpdate(command.memberId())
            .orElseThrow(MemberNotFoundException::new);

        long activeLoans = loans.countByMemberIdAndStatus(
            member.id(),
            LoanStatus.ACTIVE
        );

        member.ensureCanBorrow(activeLoans);

        BookCopy copy = copies
            .findByIdForUpdate(command.copyId())
            .orElseThrow(BookCopyNotFoundException::new);

        if (!copy.bookId().equals(command.bookId())) {
            throw new CopyDoesNotBelongToBookException();
        }

        copy.borrow();

        Instant borrowedAt = clock.instant();
        LocalDate dueDate =
            loanPeriodPolicy.dueDate(borrowedAt);

        Loan loan = Loan.open(
            member.id(),
            copy.id(),
            borrowedAt,
            dueDate
        );

        loans.save(loan);

        return new BorrowBookResult(
            loan.id(),
            dueDate
        );
    }
}
~~~

Điểm cần chú ý:

- Member được tải bằng khóa ghi trước khi đếm phiếu mượn.
- Copy được tải bằng khóa ghi trước khi kiểm tra và chuyển trạng thái.
- Copy phải thuộc đúng Book ID trong URL.
- copy.borrow() tự bảo vệ trạng thái AVAILABLE.
- Loan được tạo trong cùng transaction với việc cập nhật Copy.
- Clock được inject để test thời gian xác định.
- Application Service không biết template, HTTP redirect hoặc thông báo HTML.

Nếu lưu Loan thất bại sau khi Copy đã chuyển trạng thái trong bộ nhớ, transaction phải rollback thay đổi Copy. Điều này cần được kiểm tra bằng integration test với transaction/database thật.

Lưu ý: các phương thức repository trong ví dụ là interface Spring Data JPA; query lock và transaction cần chạy trong transaction đang hoạt động. Exception nghiệp vụ được minh họa là unchecked exception để mặc định Spring rollback. Nếu dùng checked exception, cần cấu hình rollback rule phù hợp.

## 6. Controller nhận form, lấy danh tính và điều hướng

Controller chỉ xử lý HTTP và ánh xạ hợp đồng:

~~~java
@Controller
@RequestMapping("/books")
public class BorrowBookController {
    private final BorrowBookService borrowBook;
    private final BorrowBookPageFactory pageFactory;

    public BorrowBookController(
        BorrowBookService borrowBook,
        BorrowBookPageFactory pageFactory
    ) {
        this.borrowBook = borrowBook;
        this.pageFactory = pageFactory;
    }

    @GetMapping("/{bookId}/borrow")
    public String form(
        @PathVariable UUID bookId,
        @AuthenticationPrincipal LibraryPrincipal principal,
        Model model
    ) {
        model.addAttribute(
            "form",
            new BorrowBookForm(null)
        );
        model.addAttribute(
            "page",
            pageFactory.create(bookId, principal.memberId())
        );
        return "books/borrow";
    }

    @PostMapping("/{bookId}/borrow")
    public String borrow(
        @PathVariable UUID bookId,
        @Valid @ModelAttribute("form") BorrowBookForm form,
        BindingResult errors,
        @AuthenticationPrincipal LibraryPrincipal principal,
        Model model,
        RedirectAttributes redirect
    ) {
        if (errors.hasErrors()) {
            model.addAttribute(
                "page",
                pageFactory.create(bookId, principal.memberId())
            );
            return "books/borrow";
        }

        try {
            BorrowBookResult result = borrowBook.handle(
                new BorrowBookCommand(
                    bookId,
                    form.copyId(),
                    principal.memberId()
                )
            );

            redirect.addFlashAttribute(
                "notice",
                "Mượn sách thành công."
            );

            return "redirect:/loans/" + result.loanId();
        } catch (BookCopyUnavailableException ex) {
            model.addAttribute(
                "page",
                pageFactory.create(bookId, principal.memberId())
            );
            model.addAttribute(
                "businessError",
                "Bản sao vừa được mượn hoặc không còn khả dụng."
            );
            return "books/borrow";
        }
    }
}
~~~

Ví dụ rút gọn chỉ minh họa một lỗi nghiệp vụ thường gặp. Ứng dụng thực tế nên ánh xạ từng mã lỗi nghiệp vụ đã biết thành thông điệp an toàn, hoặc dùng ControllerAdvice/presenter chung. Không bắt mọi RuntimeException rồi biến thành thông báo “không thể mượn”, vì lỗi lập trình hoặc lỗi hạ tầng cần được ghi nhận và xử lý như lỗi hệ thống.

Danh tính lấy từ LibraryPrincipal. Không thêm memberId vào form để người dùng tự chọn. Nếu thư viện cho phép nhân viên mượn hộ độc giả, đó là một use case khác với quyền riêng, cần command và authorization policy thể hiện rõ người thực hiện và người nhận sách.

Cấu hình Spring Security phải yêu cầu đăng nhập cho các route mượn sách và xem phiếu mượn. Controller sử dụng principal đã được xác thực; nó không thay thế authentication filter hoặc authorization policy. Nếu principal không tồn tại, request cần bị chặn trước khi action chạy.

## 7. View hiển thị form và dữ liệu trang

Page Factory tạo các lựa chọn đang khả dụng:

~~~java
@Component
public class BorrowBookPageFactory {
    private final BookQueryService books;

    public BorrowBookPageFactory(BookQueryService books) {
        this.books = books;
    }

    public BorrowBookPageModel create(
        UUID bookId,
        UUID memberId
    ) {
        BookBorrowOptions result =
            books.findBorrowOptions(bookId, memberId);

        List<CopyOption> options = result.availableCopies()
            .stream()
            .map(copy -> new CopyOption(
                copy.id(),
                copy.displayLabel()
            ))
            .toList();

        return new BorrowBookPageModel(
            result.bookId(),
            result.bookTitle(),
            options
        );
    }
}
~~~

Query service phải giới hạn dữ liệu theo quyền và trả các bản sao có thể chọn tại thời điểm tải trang. Danh sách này chỉ giúp giao diện thuận tiện; nó có thể cũ khi người dùng submit. Application Service vẫn kiểm tra lại trạng thái dưới khóa database.

Thymeleaf View:

~~~html
<h1 th:text="'Mượn: ' + ${page.bookTitle}">Mượn sách</h1>

<p th:if="${businessError}"
   th:text="${businessError}"
   role="alert"></p>

<form th:action="@{/books/{id}/borrow(id=${page.bookId})}"
      th:object="${form}"
      method="post">
    <label for="copyId">Chọn bản sao</label>

    <select id="copyId" th:field="*{copyId}">
        <option value="">Chọn một bản sao</option>
        <option th:each="copy : ${page.availableCopies}"
                th:value="${copy.id}"
                th:text="${copy.label}">
        </option>
    </select>

    <p th:if="${#fields.hasErrors('copyId')}"
       th:errors="*{copyId}"></p>

    <button type="submit"
            th:disabled="${#lists.isEmpty(page.availableCopies)}">
        Xác nhận mượn
    </button>
</form>
~~~

Khi dùng tích hợp Thymeleaf–Spring Security, token CSRF thường được thêm tự động vào form POST. Nếu ứng dụng tùy chỉnh cấu hình, cần xác minh token vẫn được gửi. Nội dung người dùng nhập phải được render bằng cơ chế escaping mặc định, không đánh dấu nội dung không tin cậy là HTML an toàn.

## 8. Trang biên nhận là một truy vấn riêng

Sau khi mượn thành công, Controller redirect đến GET /loans/{loanId}. Trang biên nhận tải dữ liệu đã commit và tạo ViewModel:

~~~java
public record LoanReceiptViewModel(
    UUID loanId,
    String bookTitle,
    String copyLabel,
    String memberName,
    String borrowedAtText,
    String dueDateText,
    String statusLabel
) {}
~~~

Không dùng nguyên BorrowBookResult làm biên nhận nếu trang cần thêm tên sách, bản sao và độc giả. Result chỉ cần trả dữ liệu tối thiểu để Controller điều hướng hoặc tiếp tục use case.

Query service phải xác minh người đang đăng nhập có quyền xem phiếu mượn đó. Biết loanId không đồng nghĩa có quyền truy cập.

## 9. Xác định test theo từng ranh giới

Một ca sử dụng hoàn chỉnh cần nhiều lớp test với mục tiêu khác nhau:

| Loại test | Thành phần thật | Điều cần chứng minh |
|---|---|---|
| Domain unit test | Domain Model | Bất biến và chuyển trạng thái |
| Application unit test | Service + mock port | Thứ tự điều phối, chính sách và nhánh lỗi |
| MVC slice test | Spring MVC + Controller | Binding, validation, principal, redirect và View |
| Repository integration test | ORM + database | Query, mapping, lock và constraint |
| Application integration test | Service + transaction + database | Commit, rollback và tính nguyên tử |
| MVC end-to-end integration | HTTP pipeline + database | Request thực sự tạo đúng phiếu mượn |
| Concurrency test | Database thật + nhiều transaction | Không cấp cùng một bản sao hai lần |
| Security test | Security filter + use case | Không giả danh hoặc truy cập phiếu mượn của người khác |

Không cần lặp lại mọi assertion trong tất cả loại test. Mỗi test nên bảo vệ một ranh giới cụ thể và có tên thể hiện hành vi.

## 10. Unit test cho Domain Model

Domain test không cần Spring context hoặc database.

~~~java
class BookCopyTest {
    @Test
    void availableCopyCanBeBorrowed() {
        BookCopy copy = availableCopy();

        copy.borrow();

        assertThat(copy.status()).isEqualTo(CopyStatus.ON_LOAN);
    }

    @Test
    void copyAlreadyOnLoanCannotBeBorrowedAgain() {
        BookCopy copy = onLoanCopy();

        assertThatThrownBy(copy::borrow)
            .isInstanceOf(BookCopyUnavailableException.class);
    }

    @Test
    void copyInMaintenanceCannotBeBorrowed() {
        BookCopy copy = maintenanceCopy();

        assertThatThrownBy(copy::borrow)
            .isInstanceOf(BookCopyUnavailableException.class);
    }
}
~~~

Các fixture như availableCopy() nên tạo object ở trạng thái xác định mà không phụ thuộc vào database. Nếu entity chỉ có constructor/factory private, có thể cung cấp factory domain phù hợp hoặc dùng fixture builder trong test.

Kiểm tra Member:

~~~java
class LibraryMemberTest {
    @Test
    void memberCanBorrowBelowLimit() {
        LibraryMember member = activeMemberWithLimit(5);

        assertThatCode(() -> member.ensureCanBorrow(4))
            .doesNotThrowAnyException();
    }

    @Test
    void memberCannotBorrowAtLimit() {
        LibraryMember member = activeMemberWithLimit(5);

        assertThatThrownBy(() -> member.ensureCanBorrow(5))
            .isInstanceOf(BorrowingLimitReachedException.class);
    }

    @Test
    void inactiveMemberCannotBorrow() {
        LibraryMember member = inactiveMember();

        assertThatThrownBy(() -> member.ensureCanBorrow(0))
            .isInstanceOf(MemberNotActiveException.class);
    }
}
~~~

Các test này xác minh quy tắc domain độc lập với Controller. Chúng không chứng minh khóa database hoặc transaction; phần đó cần integration test.

## 11. Unit test cho Application Service

Application unit test dùng mock để kiểm tra orchestration:

- Tải Member bằng phương thức khóa.
- Đếm phiếu mượn ACTIVE.
- Tải Copy bằng phương thức khóa.
- Kiểm tra Book ID và trạng thái.
- Lưu Loan khi hợp lệ.
- Không lưu Loan khi có điều kiện thất bại.

Ví dụ thành công:

~~~java
@Test
void createsLoanForEligibleMemberAndAvailableCopy() {
    given(members.findByIdForUpdate(memberId))
        .willReturn(Optional.of(member));
    given(loans.countByMemberIdAndStatus(
        memberId,
        LoanStatus.ACTIVE
    )).willReturn(1L);
    given(copies.findByIdForUpdate(copyId))
        .willReturn(Optional.of(copy));

    BorrowBookResult result = service.handle(
        new BorrowBookCommand(bookId, copyId, memberId)
    );

    verify(copies).findByIdForUpdate(copyId);
    verify(loans).save(any(Loan.class));
    assertThat(result.loanId()).isNotNull();
}
~~~

Ví dụ vượt giới hạn:

~~~java
@Test
void doesNotLoadOrSaveCopyWhenMemberReachedLimit() {
    given(members.findByIdForUpdate(memberId))
        .willReturn(Optional.of(member));
    given(loans.countByMemberIdAndStatus(
        memberId,
        LoanStatus.ACTIVE
    )).willReturn(5L);

    assertThatThrownBy(() ->
        service.handle(
            new BorrowBookCommand(bookId, copyId, memberId)
        )
    ).isInstanceOf(BorrowingLimitReachedException.class);

    verify(copies, never()).findByIdForUpdate(any());
    verify(loans, never()).save(any());
}
~~~

Mock xác minh luồng điều phối, không chứng minh PESSIMISTIC_WRITE thực sự khóa hàng hoặc transaction rollback. Không dùng application unit test thay thế repository/database integration test.

## 12. MVC test cho binding, principal và response

Với Spring Boot, @WebMvcTest có thể kiểm tra Controller và MVC infrastructure mà không khởi tạo toàn bộ database:

~~~java
@WebMvcTest(BorrowBookController.class)
class BorrowBookControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    BorrowBookService borrowBook;

    @MockitoBean
    BorrowBookPageFactory pageFactory;

    @Test
    void rejectsMissingCopyIdWithoutCallingUseCase() throws Exception {
        UUID authenticatedMemberId = UUID.randomUUID();
        LibraryPrincipal principal = principalFor(authenticatedMemberId);

        given(pageFactory.create(bookId, authenticatedMemberId))
            .willReturn(pageModelWithAvailableCopies());

        mvc.perform(post("/books/{id}/borrow", bookId)
                .with(authentication(authenticationFor(principal)))
                .with(csrf())
                .param("copyId", ""))
            .andExpect(status().isOk())
            .andExpect(view().name("books/borrow"))
            .andExpect(model().attributeHasFieldErrors(
                "form",
                "copyId"
            ));

        verifyNoInteractions(borrowBook);
    }
}
~~~

Tên annotation mock bean tùy phiên bản Spring Boot; dự án cũ có thể dùng @MockBean. Test cần cấu hình principal test tương thích với @AuthenticationPrincipal LibraryPrincipal.

Trong ví dụ, authenticationFor(...) là helper tạo Authentication có principal đúng kiểu LibraryPrincipal; điều này giúp @AuthenticationPrincipal nhận đúng object thay vì một UserDetails test không tương thích.

Kiểm tra thành công và danh tính:

~~~java
@Test
void usesAuthenticatedMemberIdInsteadOfFormValue() throws Exception {
    UUID copyId = UUID.randomUUID();
    UUID authenticatedMemberId = UUID.randomUUID();

    given(borrowBook.handle(any(BorrowBookCommand.class)))
        .willReturn(new BorrowBookResult(loanId, dueDate));

    mvc.perform(post("/books/{id}/borrow", bookId)
            .with(authentication(
                authenticationFor(principalFor(authenticatedMemberId))
            ))
            .with(csrf())
            .param("copyId", copyId.toString()))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/loans/" + loanId));

    ArgumentCaptor<BorrowBookCommand> captor =
        ArgumentCaptor.forClass(BorrowBookCommand.class);

    verify(borrowBook).handle(captor.capture());

    assertThat(captor.getValue().memberId())
        .isEqualTo(authenticatedMemberId);
    assertThat(captor.getValue().copyId()).isEqualTo(copyId);
}
~~~

Điểm quan trọng là command nhận memberId từ principal. Nếu client gửi thêm tham số memberId, Controller không được dùng nó để thay danh tính đã xác thực.

Với test security, cần gửi request không có CSRF token và xác minh POST bị từ chối khi CSRF protection được bật. Cũng cần test người chưa đăng nhập bị chuyển đến trang đăng nhập hoặc nhận 401/403 theo hợp đồng ứng dụng.

## 13. Integration test cho transaction và database

Repository integration test nên dùng cùng loại database với production khi hành vi query, constraint hoặc lock có ý nghĩa. Testcontainers có thể khởi chạy PostgreSQL cho suite:

~~~java
@Testcontainers
@SpringBootTest
class BorrowBookIntegrationTest {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // Datasource được cấu hình trỏ đến container
    // qua @ServiceConnection hoặc DynamicPropertySource.
}
~~~

Cấu hình đầy đủ phụ thuộc phiên bản Spring Boot và Testcontainers. Migration Flyway/Liquibase nên chạy trong test để xác minh schema thật thay vì chỉ để Hibernate tự tạo schema.

### 13.1. Kiểm tra kết quả sau commit

Nếu muốn xác minh application service tự commit transaction, test không nên có transaction bao ngoài:

~~~java
@SpringBootTest
class BorrowBookCommitTest {
    @Autowired
    BorrowBookService service;

    @Autowired
    LoanRepository loans;

    @Autowired
    BookCopyRepository copies;

    @Test
    void commitsLoanAndCopyStatusTogether() {
        SeedData seed = seedAvailableCopyAndActiveMember();

        BorrowBookResult result = service.handle(
            new BorrowBookCommand(
                seed.bookId(),
                seed.copyId(),
                seed.memberId()
            )
        );

        Loan saved = loans.findById(result.loanId())
            .orElseThrow();

        BookCopy savedCopy = copies.findById(seed.copyId())
            .orElseThrow();

        assertThat(savedCopy.status()).isEqualTo(CopyStatus.ON_LOAN);
        assertThat(saved.id()).isEqualTo(result.loanId());
        assertThat(savedCopy.id()).isEqualTo(seed.copyId());
    }
}
~~~

Ví dụ giả định seedAvailableCopyAndActiveMember() tạo dữ liệu đã commit trước lời gọi service. Vì service được gọi qua Spring proxy và không có transaction test bao ngoài, transaction của use case kết thúc trước khi test đọc lại.

Nếu test method gắn @Transactional, service có thể tham gia transaction test với propagation REQUIRED; khi đó phương thức trả về chưa chứng minh transaction đã commit. Cần hiểu rõ transaction boundary trước khi kết luận.

### 13.2. Kiểm tra rollback

Tạo tình huống để thao tác ghi Loan thất bại sau khi Copy đã được chuyển trạng thái, chẳng hạn dùng constraint thật hoặc một persistence adapter test gây lỗi. Sau khi exception thoát khỏi service, đọc lại bằng transaction mới:

- Không có Loan mới.
- Copy vẫn AVAILABLE.
- Các dữ liệu liên quan không bị ghi một phần.

Không chỉ assert exception được ném. Phải xác minh trạng thái database sau rollback. Nếu dùng checked exception, test cần xác minh cấu hình rollbackFor tương ứng.

### 13.3. Kiểm tra migration và constraint

Test schema nên xác minh:
- Foreign key từ Loan đến Member và BookCopy.
- Unique constraint hoặc cơ chế bảo đảm không có hai loan ACTIVE cho cùng một copy, nếu database schema được thiết kế theo cách đó.
- Index cho truy vấn các loan ACTIVE theo member.
- Enum/status mapping đúng với schema.
- Migration chạy từ database rỗng và từ phiên bản schema trước.

Nếu dùng partial unique index để giới hạn một ACTIVE loan trên mỗi copy, cú pháp và tính năng phụ thuộc database. Hãy test trên đúng engine production.

## 14. Concurrency test: hai độc giả tranh một bản sao

Đây là test đặc biệt quan trọng vì unit test tuần tự không thể phát hiện race condition. Tạo hai Member đang hoạt động, một BookCopy AVAILABLE và gửi hai lệnh mượn gần như đồng thời.

Kịch bản:
1. Hai thread chờ cùng một latch.
2. Khi latch mở, mỗi thread gọi use case trong transaction riêng với một member khác nhau nhưng cùng copyId.
3. Một transaction khóa copy trước và tạo Loan.
4. Transaction còn lại chờ khóa; sau khi transaction đầu commit, nó đọc trạng thái mới và nhận BookCopyUnavailableException.
5. Truy vấn lại database và xác minh chỉ có một loan ACTIVE cho copy.

Pseudocode cho phần điều phối:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

Callable<BorrowOutcome> attempt(UUID memberId) {
    return () -> {
        ready.countDown();
        start.await();

        try {
            BorrowBookResult result = service.handle(
                new BorrowBookCommand(bookId, copyId, memberId)
            );
            return BorrowOutcome.success(result.loanId());
        } catch (BookCopyUnavailableException ex) {
            return BorrowOutcome.unavailable();
        }
    };
}

Future<BorrowOutcome> first = pool.submit(attempt(memberA));
Future<BorrowOutcome> second = pool.submit(attempt(memberB));

ready.await();
start.countDown();

BorrowOutcome a = first.get();
BorrowOutcome b = second.get();
~~~

Đây là khung minh họa; test thực tế cần try/finally để đóng ExecutorService, giới hạn timeout cho mọi await/get và cleanup nếu một thread thất bại.

Assertion cuối:

~~~java
assertThat(List.of(a, b))
    .filteredOn(BorrowOutcome::isSuccess)
    .hasSize(1);

assertThat(loanRepository.countActiveByCopyId(copyId))
    .isEqualTo(1);

assertThat(copyRepository.findById(copyId).orElseThrow().status())
    .isEqualTo(CopyStatus.ON_LOAN);
~~~

Chạy test này trên database tương thích production. Không dùng Thread.sleep để đoán thời điểm thread; latch/barrier và timeout giúp test ổn định hơn. Nếu database dùng isolation mạnh hơn READ_COMMITTED, có thể phát sinh serialization failure; ứng dụng cần định nghĩa retry hoặc kết quả xung đột phù hợp.

Cần thêm concurrency test cho cùng một Member mượn hai bản sao khác nhau cùng lúc nếu giới hạn số sách là bất biến quan trọng. Khóa BookCopy không giải quyết trường hợp này; khóa Member và truy vấn số loan sau khi lấy khóa mới là phần bảo vệ giới hạn của độc giả.

## 15. Kiểm thử toàn luồng qua HTTP

Một MVC integration test có thể gửi request qua MockMvc và kiểm tra database sau khi request hoàn tất:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BorrowBookHttpIntegrationTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    LoanRepository loans;

    @Autowired
    BookCopyRepository copies;

    @Test
    void authenticatedReaderCanBorrowAvailableCopy() throws Exception {
        SeedData seed = seedAvailableCopyAndActiveMember();

        MvcResult response = mvc.perform(
                post("/books/{id}/borrow", seed.bookId())
                    .with(authentication(
                        authenticationFor(principalFor(seed.memberId()))
                    ))
                    .with(csrf())
                    .param("copyId", seed.copyId().toString())
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertThat(response.getResponse().getRedirectedUrl())
            .contains("/loans/");

        assertThat(copies.findById(seed.copyId()).orElseThrow().status())
            .isEqualTo(CopyStatus.ON_LOAN);

        assertThat(loans.countByMemberIdAndStatus(
            seed.memberId(),
            LoanStatus.ACTIVE
        )).isEqualTo(1);
    }
}
~~~

Nếu test dùng MockMvc, request được xử lý trong pipeline Spring test nhưng không nhất thiết có transaction bao ngoài giống một lời gọi service trực tiếp. Để chứng minh commit, tránh đặt @Transactional trên test method và đọc dữ liệu sau response bằng transaction độc lập.

Test HTTP nên xác minh thêm:
- Không có CSRF token thì POST bị từ chối.
- Không đăng nhập thì không thể mượn.
- Member không hoạt động nhận lỗi phù hợp.
- Member đã đạt giới hạn không tạo Loan.
- Copy không thuộc Book ID trong URL bị từ chối.
- Copy không còn AVAILABLE được hiển thị lỗi nghiệp vụ.
- Người dùng không xem được biên nhận của member khác.

## 16. Kiểm thử lỗi theo hợp đồng

Mỗi lỗi nên có một kết quả quan sát được ở đúng tầng:

| Tình huống | Tầng phát hiện | Kết quả HTTP/UI gợi ý | Bất biến cần xác minh |
|---|---|---|---|
| copyId thiếu hoặc sai định dạng | Binding/validation | Render lại form với lỗi trường | Use case chưa được gọi |
| Member không tồn tại | Application | 404 hoặc thông báo tài khoản không hợp lệ | Không tạo Loan |
| Member bị khóa | Domain/Application | 403 hoặc trang giải thích | Không đổi trạng thái Copy |
| Đạt giới hạn mượn | Domain/Application | Thông báo giới hạn | Không tạo Loan |
| Copy không thuộc Book | Application | 404/400 theo chính sách | Không ghi dữ liệu |
| Copy đã được mượn | Domain/persistence | Thông báo không còn khả dụng | Tối đa một Loan ACTIVE |
| Database không khả dụng | Infrastructure | 5xx an toàn | Không hiển thị chi tiết SQL |
| Deadlock/serialization failure | Database/transaction | Retry có giới hạn hoặc lỗi tạm thời | Không commit dữ liệu một phần |

Không nên dùng một status code duy nhất cho mọi tình huống. Ví dụ 404 có thể được chọn để tránh tiết lộ sự tồn tại của tài nguyên ngoài quyền; 409 phù hợp với xung đột trạng thái; 422 có thể dùng cho input hợp lệ về cú pháp nhưng không thỏa quy tắc theo hợp đồng API. Với HTML, có thể render trang lỗi thay vì trả JSON.

## 17. Truy vết khi chạy thật

Test cho biết hệ thống hoạt động trong kịch bản được kiểm soát. Observability giúp điều tra một request cụ thể trong production.

Một trace hữu ích cho ca mượn sách có thể gồm các span:

~~~mermaid
flowchart TD
    A["HTTP POST /books/{id}/borrow"] --> B["MVC binding + validation"]
    B --> C["BorrowBookService.handle"]
    C --> D["Lock member"]
    D --> E["Count active loans"]
    E --> F["Lock book copy"]
    F --> G["Domain: copy.borrow"]
    G --> H["Insert loan + update copy"]
    H --> I["Transaction commit"]
    I --> J["HTTP 302 /loans/{loanId}"]
~~~

Các thuộc tính có thể gắn vào trace/log:
- requestId hoặc traceId.
- useCase = BorrowBook.
- bookId và copyId.
- memberId nội bộ nếu chính sách logging cho phép.
- loanId khi tạo thành công.
- outcome hoặc errorCode.
- duration và transaction result.

Không ghi mật khẩu, session cookie, access token, CSRF token hoặc toàn bộ dữ liệu form. Nếu memberId có thể liên kết dữ liệu cá nhân, áp dụng chính sách hạn chế truy cập log, thời gian lưu và masking phù hợp.

### 17.1. Structured logging

Ví dụ log hoàn tất use case:

~~~java
log.info(
    "book.borrow.completed requestId={} memberId={} copyId={} loanId={}",
    requestId,
    member.id(),
    copy.id(),
    loan.id()
);
~~~

Lỗi nghiệp vụ dự kiến có thể ghi ở mức phù hợp với outcome, kèm mã lỗi ổn định. Không nhất thiết ghi stack trace cho mọi lần độc giả chọn một bản sao vừa được người khác mượn; đó là xung đột nghiệp vụ có thể dự kiến.

Lỗi database, timeout hoặc lỗi không dự kiến cần log exception nội bộ cùng trace ID để điều tra. Response gửi người dùng chỉ chứa thông báo an toàn.

Chỉ ghi sự kiện thành công sau khi transaction đã commit. Có thể ghi ở caller sau khi phương thức service được proxy trả về, hoặc dùng transaction synchronization/after-commit event. Nếu log “completed” ngay bên trong phương thức transactional trước commit, log có thể báo thành công dù commit sau đó thất bại.

### 17.2. Correlation ID và distributed tracing

Correlation ID cho phép nối log của một request qua Controller, Application Service và adapter. Nếu ứng dụng dùng OpenTelemetry hoặc tracing tương đương, mỗi bước có thể là một span con trong trace của HTTP request.

Khi request gọi một hệ thống ngoài, trace context có thể được truyền tiếp để nối các dịch vụ. Không tự tạo một trace ID mới ở mỗi tầng; hãy giữ trace context của request và bổ sung span cho thao tác cần đo.

### 17.3. Metrics có ích

Một số metrics phù hợp:
- library_borrow_attempts_total theo outcome.
- library_borrow_duration_seconds.
- library_borrow_lock_wait_seconds.
- Số phiếu mượn ACTIVE.
- Số lỗi deadlock/serialization retry.
- Số lần bản sao không khả dụng khi submit.

Không đưa memberId, loanId hoặc copyId làm metric label vì cardinality tăng không giới hạn. Dùng label có tập giá trị nhỏ như outcome, errorCode hoặc loại thao tác; ID cụ thể thuộc log/trace có kiểm soát.

## 18. Ma trận kiểm thử tối thiểu cho ca mượn sách

| Nhóm | Trường hợp | Assertion chính |
|---|---|---|
| Domain | AVAILABLE → ON_LOAN | Trạng thái đổi đúng |
| Domain | ON_LOAN → borrow lần nữa | Ném lỗi |
| Domain | Member inactive | Không cho mượn |
| Domain | Member đạt limit | Không cho mượn |
| Application | Mượn hợp lệ | Tạo đúng Loan |
| Application | Copy thuộc Book khác | Không lưu Loan |
| MVC | Thiếu copyId | Render lỗi, không gọi use case |
| MVC | Request hợp lệ | Command dùng memberId từ principal |
| Security | Không đăng nhập | Bị từ chối |
| Security | Thiếu CSRF token | POST bị từ chối |
| Integration | Thành công | Loan commit và Copy ON_LOAN |
| Integration | Lỗi khi lưu Loan | Copy rollback về AVAILABLE |
| Concurrency | Hai Member cùng copy | Chỉ một Loan ACTIVE |
| Concurrency | Một Member mượn hai copy đồng thời | Không vượt giới hạn |
| Observability | Thành công/thất bại | Trace và errorCode có thể đối chiếu |

Không nhất thiết chạy mọi concurrency test ở mọi lần build nếu chúng tốn thời gian. Có thể đặt suite database concurrency riêng nhưng phải chạy thường xuyên trong pipeline phù hợp và trước khi phát hành thay đổi transaction/locking.

## 19. Chuẩn bị dữ liệu test và giữ test độc lập

Fixture cần thể hiện rõ điều kiện đầu vào:
- Member ACTIVE, chưa đạt limit.
- Member INACTIVE.
- Member đã có đúng số Loan ACTIVE bằng limit.
- Book có nhiều Copy với các trạng thái khác nhau.
- Copy AVAILABLE, ON_LOAN, MAINTENANCE.
- Loan ACTIVE và RETURNED.

Mỗi test nên tạo dữ liệu riêng và không dựa vào thứ tự chạy. Tránh hard-code ID tự tăng hoặc dùng chung entity mutable giữa test method.

Có thể chọn:
- Rollback transaction cho repository test đơn giản.
- Xóa dữ liệu theo test ID cho test cần commit thật.
- Database/schema riêng cho suite chạy song song.
- Testcontainers để có database engine gần production.

Khi cần xác minh transaction commit/rollback, không dùng transaction bao ngoài test làm mọi thay đổi tự rollback rồi kết luận service đã commit. Khi cần xác minh migration, để Flyway/Liquibase tạo schema thay vì chỉ dùng Hibernate create-drop.

## 20. Những lỗi thiết kế và kiểm thử thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Test chỉ assert redirect | Không biết Loan có được lưu hay không | Đọc lại database sau request |
| Chỉ mock repository | Không kiểm tra SQL, lock hoặc constraint | Bổ sung database integration test |
| Đọc AVAILABLE rồi save không khóa | Hai request có thể cùng mượn một copy | Pessimistic/optimistic locking và constraint |
| Lấy memberId từ form | Có thể mượn dưới danh tính người khác | Lấy từ principal |
| Chỉ ẩn copy đã mượn ở View | Form cũ vẫn có thể gửi copyId đó | Kiểm tra lại trong use case dưới transaction |
| Dùng @Transactional trên test commit | Transaction test che khuất commit của service | Gọi service không có transaction bao ngoài |
| Assert exception nhưng không đọc dữ liệu | Không biết rollback có hoàn chỉnh không | Kiểm tra state trong transaction mới |
| Dùng sleep cho concurrency | Test không ổn định | Latch/barrier và timeout |
| Ghi toàn bộ request vào log | Có nguy cơ lộ dữ liệu nhạy cảm | Structured logging có chọn lọc |
| Dùng ID làm metric label | Cardinality tăng không kiểm soát | Đưa ID vào trace/log, metric dùng label hữu hạn |

## 21. Quy trình truy vết một ca sử dụng mới

Khi triển khai một chức năng khác như gia hạn hoặc trả sách, có thể lặp lại quy trình:

1. Viết các quy tắc nghiệp vụ và bất biến trước khi thiết kế endpoint.
2. Xác định aggregate/entity và trạng thái được phép chuyển.
3. Thiết kế Form/Input DTO, Command, Result và Presentation Model.
4. Vẽ request flow từ route đến response.
5. Đặt transaction tại application use case.
6. Xác định dữ liệu nào cần khóa hoặc version để bảo vệ concurrency.
7. Viết domain unit test cho chuyển trạng thái.
8. Viết application test cho orchestration và nhánh lỗi.
9. Viết MVC test cho binding, principal, CSRF và response.
10. Viết integration test cho commit, rollback, query và migration.
11. Viết concurrency test cho bất biến dễ bị tranh chấp.
12. Bổ sung trace/log/metrics với correlation ID và dữ liệu tối thiểu.
13. Đọc trace và database state để đối chiếu một request thành công lẫn thất bại.

Mỗi ca sử dụng có thể có độ phức tạp khác nhau. Một trang tìm sách chỉ đọc có thể không cần khóa ghi; mượn, trả hoặc gia hạn cần kiểm tra trạng thái, transaction và cạnh tranh dữ liệu.

## 22. Những điểm cần ghi nhớ

Kiểm thử một ca sử dụng MVC hoàn chỉnh phải theo dõi cả dữ liệu đi qua các tầng và trạng thái cuối cùng trong database. Với ca mượn sách, Controller nhận Form Model và lấy memberId từ principal; Application Service điều phối transaction; Domain Model bảo vệ trạng thái bản sao và điều kiện độc giả; Repository thực thi truy vấn và khóa dữ liệu; View nhận Page Model hoặc biên nhận riêng.

Unit test xác minh quy tắc và orchestration. MVC test xác minh binding, validation, principal, CSRF và response. Integration test xác minh SQL, commit, rollback và migration. Concurrency test xác minh hai request không thể cấp cùng một bản sao hoặc làm độc giả vượt giới hạn. Không loại test nào thay thế hoàn toàn các loại còn lại.

Khi chạy production, correlation ID, structured log, trace và metrics giúp nối một request với use case, transaction và kết quả. Chỉ ghi dữ liệu cần thiết, không ghi bí mật hoặc nội dung form nhạy cảm. Kết hợp test theo ranh giới với truy vết có cấu trúc giúp nhóm phát hiện lỗi ở đúng tầng và giải thích được vì sao một ca sử dụng thành công, thất bại hoặc bị từ chối.
