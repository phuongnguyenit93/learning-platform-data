# Kiểm tra hợp đồng dữ liệu và ranh giới nghiệp vụ

Một thiết kế MVC có thể chạy đúng trong trường hợp thông thường nhưng vẫn có lỗi ở ranh giới giữa HTTP, application service, domain model và database. Controller có thể nhận thêm trường mà client không được phép sửa; response có thể vô tình công bố thuộc tính nội bộ; một quy tắc nghiệp vụ có thể chỉ được kiểm tra ở giao diện; hoặc transaction có thể kết thúc trước khi các thay đổi liên quan được lưu đầy đủ.

Review thiết kế cần kiểm tra đồng thời hai điều:

1. **Hợp đồng dữ liệu:** client gửi gì, server chấp nhận gì, server trả gì và những cam kết nào cần giữ ổn định?
2. **Ranh giới nghiệp vụ:** thành phần nào có quyền quyết định một hành động hợp lệ, trạng thái nào được phép thay đổi và những thay đổi nào phải nhất quán với nhau?

Hai câu hỏi này liên kết chặt chẽ. Hợp đồng HTTP là bề mặt giao tiếp; nó không được trở thành nơi quyết định quy tắc nghiệp vụ. Controller chuyển dữ liệu qua ranh giới, application service điều phối use case, domain model bảo vệ bất biến, còn repository và adapter thực hiện lưu trữ. Review tốt giúp mỗi phần có trách nhiệm rõ, tránh việc cùng một quy tắc được kiểm tra ở nhiều nơi theo cách không nhất quán.

Bài học sử dụng ví dụ đăng ký mượn sách trong ứng dụng quản lý thư viện. Người dùng gửi yêu cầu mượn một cuốn sách; hệ thống xác minh người mượn, kiểm tra sách còn khả dụng, tạo phiếu mượn và trả kết quả. Ví dụ này đủ cụ thể để xem xét DTO, quyền truy cập, domain invariant, transaction, cạnh tranh đồng thời và response contract.

## 1. Phân biệt hợp đồng dữ liệu và ranh giới nghiệp vụ

Hợp đồng dữ liệu mô tả cách hai thành phần trao đổi thông tin. Trong ứng dụng MVC, có nhiều hợp đồng:

- Form HTML gửi dữ liệu đến Controller.
- REST request gửi JSON đến API Controller.
- Controller chuyển dữ liệu thành command cho use case.
- Use case gọi repository hoặc gateway qua interface.
- Use case trả application result.
- Presenter chuyển result thành ViewModel hoặc response DTO.
- Adapter persistence ánh xạ domain object sang cấu trúc lưu trữ.

Ranh giới nghiệp vụ xác định nơi một quy tắc có thẩm quyền được thực thi. Ví dụ:

- Người dùng không thể mượn sách nếu tài khoản bị khóa.
- Một cuốn sách không thể được cho hai người mượn cùng lúc khi chỉ có một bản sao.
- Ngày trả dự kiến phải sau ngày mượn và nằm trong giới hạn chính sách.
- Số sách đang mượn không vượt hạn mức của thành viên.
- Một phiếu mượn đã đóng không thể được đóng lần nữa.

| Câu hỏi review | Hợp đồng dữ liệu | Ranh giới nghiệp vụ |
|---|---|---|
| Ai quyết định? | API/adapter công bố schema và quy tắc giao tiếp | Domain policy/use case có thẩm quyền |
| Dữ liệu nào liên quan? | Request, response, field, type, nullability | Trạng thái aggregate, actor, resource và điều kiện |
| Thay đổi ảnh hưởng ai? | Client, form, API consumer, tích hợp | Người dùng, nghiệp vụ, dữ liệu và hệ thống phụ thuộc |
| Test ở đâu? | Contract/MVC test, serialization test | Domain/application test, integration test |
| Lỗi thường gặp | DTO lộ nội bộ hoặc đổi schema không tương thích | Bỏ qua invariant, kiểm tra quyền ở UI hoặc cập nhật không nguyên tử |

Không nên dùng một object cho mọi hợp đồng chỉ để giảm số class. Request DTO, command, domain entity, persistence entity và response DTO có thể có field giống nhau nhưng vòng đời và quyền sở hữu khác nhau.

## 2. Bản đồ một request trước khi review

Trước khi đọc từng class, hãy chọn một use case cụ thể và vẽ đường đi từ request đến dữ liệu được lưu và response được trả về.

~~~mermaid
flowchart TD
    A[HTTP Request] --> B[Controller: bind và kiểm tra cấu trúc]
    B --> C[Request DTO]
    C --> D[Mapping thành Command]
    D --> E[Application Use Case]
    E --> F[Authorization và Business Policy]
    F --> G[Domain Model: bảo vệ invariant]
    G --> H[Repository/Gateway Port]
    H --> I[Persistence Adapter và Database]
    I --> J[Application Result]
    J --> K[Presenter/Response Mapper]
    K --> L[Response DTO hoặc ViewModel]
    L --> M[HTTP Response hoặc View]
~~~

Review từng bước bằng các câu hỏi:

1. Dữ liệu nào đến từ client và dữ liệu nào đến từ ngữ cảnh tin cậy của server?
2. Có field nào được bind nhưng không nên cho client kiểm soát không?
3. Validation cấu trúc và quy tắc nghiệp vụ có được phân chia rõ không?
4. Use case có nhận kiểu dữ liệu độc lập framework không?
5. Quy tắc có được thực thi ở nơi có đủ thông tin và thẩm quyền không?
6. Những thay đổi nào phải nằm trong cùng transaction?
7. Response có chỉ công bố dữ liệu được phép và ổn định không?
8. Có test ở từng ranh giới quan trọng không?

Đừng bắt đầu review bằng việc đếm số lớp hoặc yêu cầu thêm interface. Trước hết hãy xác định luồng dữ liệu và quyền quyết định.

## 3. Ví dụ hợp đồng tạo phiếu mượn

API tạo phiếu mượn có thể nhận:

~~~http
POST /api/loans
Content-Type: application/json
Authorization: Bearer <token>

{
  "bookId": 42,
  "dueDate": "2026-12-03"
}
~~~

Request chỉ chứa dữ liệu người dùng được phép đề xuất: sách cần mượn và ngày trả dự kiến. Những trường sau không nên do client quyết định:

- `memberId`: danh tính người mượn lấy từ principal đã xác thực.
- `status`: trạng thái phiếu mượn do use case/domain quyết định.
- `approvedBy`: người phê duyệt lấy từ quy trình và danh tính server.
- `borrowedAt`: thời điểm được xác định bằng clock của hệ thống.
- `fineAmount`: khoản phạt được tính từ quy tắc và dữ liệu có thẩm quyền.

Response có thể là:

~~~http
HTTP/1.1 201 Created
Location: /api/loans/9001
Content-Type: application/json

{
  "id": 9001,
  "bookId": 42,
  "dueDate": "2026-12-03",
  "status": "ACTIVE"
}
~~~

Đây là một hợp đồng minh họa. Trong dự án thật, status, field, kiểu dữ liệu và mã lỗi phải được xác định từ yêu cầu sản phẩm và các client đang sử dụng. Không lấy ví dụ này làm mặc định cho mọi thư viện.

### 3.1. Request DTO là biên giao tiếp

~~~java
public record CreateLoanRequest(
        @NotNull @Positive Long bookId,
        @NotNull LocalDate dueDate
) {
}
~~~

DTO này phản ánh schema HTTP. Nó có thể dùng Bean Validation để kiểm tra `bookId` có giá trị dương và `dueDate` có mặt. Tuy nhiên, annotation không chứng minh ngày trả nằm trong chính sách cho mượn; đó là quy tắc cần được kiểm tra ở application/domain.

Không thêm `memberId`, `status`, `borrowedAt` hoặc `fineAmount` vào request rồi hy vọng Controller bỏ qua chúng. Việc không định nghĩa các field đó trong DTO làm rõ ngay hợp đồng client được phép gửi gì.

### 3.2. Controller chuyển request thành command

~~~java
@RestController
@RequestMapping("/api/loans")
public class LoanController {
    private final CreateLoanUseCase createLoan;
    private final LoanResponseMapper responseMapper;

    public LoanController(
            CreateLoanUseCase createLoan,
            LoanResponseMapper responseMapper
    ) {
        this.createLoan = createLoan;
        this.responseMapper = responseMapper;
    }

    @PostMapping
    public ResponseEntity<LoanResponse> create(
            @Valid @RequestBody CreateLoanRequest request,
            @AuthenticationPrincipal CurrentUser currentUser
    ) {
        CreateLoanCommand command = new CreateLoanCommand(
                currentUser.memberId(),
                request.bookId(),
                request.dueDate()
        );

        CreateLoanResult result = createLoan.execute(command);
        LoanResponse response = responseMapper.toResponse(result);

        URI location = URI.create("/api/loans/" + result.loanId());
        return ResponseEntity.created(location).body(response);
    }
}
~~~

Controller chỉ làm nhiệm vụ adapter: nhận HTTP, lấy actor từ principal, chuyển thành command, gọi use case và tạo response. Nó không tự truy vấn entity rồi sửa trạng thái mượn.

Trong ứng dụng dùng Spring Security, cần cấu hình principal đúng kiểu `CurrentUser`. Nếu endpoint dùng cookie/session, cần áp dụng CSRF protection theo cấu hình bảo mật. Không tin `memberId` gửi trong body hoặc query string để thay thế danh tính đã xác thực.

## 4. Review sự khác nhau giữa Request, Command, Domain và Response

Một luồng thường có các kiểu dữ liệu riêng:

| Kiểu | Chủ sở hữu | Mục đích | Có nên phụ thuộc Spring/HTTP? |
|---|---|---|---|
| `CreateLoanRequest` | Web/API adapter | Schema client gửi | Có thể dùng Bean Validation |
| `CreateLoanCommand` | Application layer | Yêu cầu use case thực hiện | Không |
| `Loan` | Domain | Trạng thái và quy tắc phiếu mượn | Không |
| `LoanJpaEntity` | Persistence adapter | Ánh xạ database | Có thể dùng JPA |
| `CreateLoanResult` | Application layer | Kết quả use case | Không |
| `LoanResponse` | API adapter | Schema công bố cho client | Có thể dùng serialization metadata |
| `LoanViewModel` | HTML adapter | Dữ liệu cho màn hình | Có thể chứa nhãn đã dịch |

Các kiểu có thể trùng nhau trong ứng dụng nhỏ, nhưng review cần xác nhận việc dùng chung không làm lộ field, kéo framework vào domain hoặc khiến một thay đổi UI phá hợp đồng API.

Ví dụ command:

~~~java
public record CreateLoanCommand(
        long memberId,
        long bookId,
        LocalDate dueDate
) {
}
~~~

Command thể hiện ý định nghiệp vụ. Nó không chứa `HttpServletRequest`, `BindingResult`, `Model`, `ResponseEntity` hoặc entity JPA.

Input port và kết quả use case:

~~~java
public interface CreateLoanUseCase {
    CreateLoanResult execute(CreateLoanCommand command);
}

public record CreateLoanResult(
        long loanId,
        long bookId,
        LocalDate dueDate,
        LoanStatus status
) {
}
~~~

Response:

~~~java
public record LoanResponse(
        long id,
        long bookId,
        LocalDate dueDate,
        String status
) {
}
~~~

Response chỉ chứa field đã được duyệt công bố. Không serialize trực tiếp `LoanJpaEntity` vì entity có thể chứa quan hệ lazy, field audit, dữ liệu nội bộ hoặc vòng tham chiếu.

## 5. Review validation theo đúng lớp

Validation không phải một thao tác duy nhất. Hãy phân loại theo câu hỏi mà nó trả lời:

| Loại | Ví dụ | Nơi phù hợp |
|---|---|---|
| Binding/conversion | JSON hợp lệ, `bookId` chuyển được thành số | HTTP adapter/framework |
| Structural validation | `bookId` bắt buộc và dương | Request DTO/Bean Validation |
| Use case validation | Thành viên còn quyền mượn không? | Application service/policy |
| Domain invariant | Ngày trả phải sau ngày mượn; phiếu mới ở trạng thái ACTIVE | Domain model/value object |
| Persistence constraint | Không thể tạo hai phiếu đang hoạt động cho cùng bản sao sách | Database và persistence adapter |

### 5.1. Validation ở Controller không thay thế domain rule

`@NotNull` và `@Positive` bảo vệ cấu trúc request. Nhưng use case có thể được gọi từ REST, HTML, message consumer, batch job hoặc test. Vì vậy, quy tắc nghiệp vụ phải được bảo vệ bên trong ranh giới application/domain.

Ví dụ, không nên chỉ kiểm tra ngày trả trong Controller:

~~~java
if (request.dueDate().isAfter(LocalDate.now())) {
    // Cho phép
}
~~~

Đoạn này phụ thuộc đồng hồ hệ thống, có thể không thống nhất múi giờ và không kiểm tra chính sách thời hạn tối đa. Hãy đưa clock và policy vào use case/domain:

~~~java
public record LoanPeriod(LocalDate borrowedAt, LocalDate dueDate) {
    public LoanPeriod {
        if (borrowedAt == null || dueDate == null
                || !dueDate.isAfter(borrowedAt)) {
            throw new InvalidLoanPeriodException();
        }
    }
}
~~~

Với chính sách ngày mượn, ngày nghỉ và thời hạn tối đa, có thể dùng `LoanPolicy` nhận `Clock` hoặc ngày nghiệp vụ làm đầu vào. Test có thể cố định thời gian mà không phụ thuộc đồng hồ máy.

### 5.2. Kiểm tra binding error trước khi gọi use case

Với Spring MVC, nếu dùng `BindingResult`, nó phải đứng ngay sau tham số được validate:

~~~java
@PostMapping
public ResponseEntity<?> create(
        @Valid @RequestBody CreateLoanRequest request,
        BindingResult errors
) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
                ApiValidationError.from(errors)
        );
    }

    // Gọi use case sau khi request hợp lệ
    ...
}
~~~

Đây là phác thảo về vị trí xử lý; với `@RequestBody`, nhiều ứng dụng để `MethodArgumentNotValidException` được xử lý tập trung qua `@RestControllerAdvice`. Dù chọn cách nào, review cần xác nhận request không hợp lệ không đi vào use case và lỗi trả về có schema ổn định.

## 6. Review ranh giới nghiệp vụ và quyền quyết định

Một quy tắc cần có một nơi chịu trách nhiệm chính. Nếu Controller kiểm tra số sách đang mượn, service khác kiểm tra lại bằng một cách khác và database chỉ lưu mà không có bảo vệ đồng thời, hệ thống có thể tạo kết quả không nhất quán.

Với use case mượn sách, review các điều kiện:

- Thành viên tồn tại và đang hoạt động.
- Thành viên không bị khóa quyền mượn.
- Sách tồn tại và bản sao được phép lưu hành.
- Sách chưa được người khác mượn hoặc giữ chỗ.
- Thành viên chưa vượt hạn mức.
- Ngày trả nằm trong khoảng chính sách.
- Phiếu mượn được tạo ở trạng thái ban đầu hợp lệ.

Một policy có thể phối hợp các quy tắc phụ thuộc nhiều đối tượng:

~~~java
public class BorrowingPolicy {
    public void ensureCanBorrow(
            Member member,
            BookCopy copy,
            int activeLoanCount
    ) {
        if (!member.isActive()) {
            throw new MemberNotActiveException();
        }
        if (!member.canBorrow()) {
            throw new BorrowingNotAllowedException();
        }
        if (!copy.isAvailable()) {
            throw new BookCopyUnavailableException();
        }
        if (activeLoanCount >= member.borrowingLimit()) {
            throw new BorrowingLimitExceededException();
        }
    }
}
~~~

Ví dụ policy cho thấy quyết định không nằm ở View. Trong hệ thống thực tế, một số quy tắc có thể thuộc aggregate `Member`, `BookCopy` hoặc `Loan`; policy chỉ điều phối điều kiện cần xem xét nhiều đối tượng. Tránh tạo service trung tâm biết mọi dữ liệu và chứa tất cả quy tắc.

### 6.1. Aggregate và bất biến

Aggregate là ranh giới nhất quán mà domain model bảo vệ khi thay đổi trạng thái. Review cần hỏi:

- Aggregate root nào được phép thay đổi trạng thái?
- Có thể sửa entity con trực tiếp từ bên ngoài không?
- Invariant nào phải đúng sau mỗi command?
- Có cần transaction hoặc khóa để bảo vệ invariant khi nhiều request đồng thời?

Ví dụ, `Loan` có thể bảo vệ chuyển trạng thái:

~~~java
public class Loan {
    private LoanStatus status;
    private LocalDate borrowedAt;
    private LocalDate dueDate;

    public static Loan start(
            LocalDate borrowedAt,
            LocalDate dueDate
    ) {
        if (borrowedAt == null || dueDate == null
                || !dueDate.isAfter(borrowedAt)) {
            throw new InvalidLoanPeriodException();
        }
        Loan loan = new Loan();
        loan.borrowedAt = borrowedAt;
        loan.dueDate = dueDate;
        loan.status = LoanStatus.ACTIVE;
        return loan;
    }

    public void close(LocalDate returnedAt) {
        if (status != LoanStatus.ACTIVE) {
            throw new LoanCannotBeClosedException();
        }
        if (returnedAt == null || returnedAt.isBefore(borrowedAt)) {
            throw new InvalidReturnDateException();
        }
        status = LoanStatus.CLOSED;
    }
}
~~~

Đoạn mã minh họa invariant của phiếu mượn. Nếu quy tắc khả dụng của bản sao sách phải nhất quán cùng lúc với tạo phiếu, use case cần phối hợp aggregate liên quan và persistence transaction phù hợp.

## 7. Review authorization: ai được làm gì với tài nguyên nào?

Authentication xác định người gọi; authorization quyết định người đó có quyền thực hiện hành động trên tài nguyên cụ thể hay không.

Review cần phân biệt:

- **Function-level authorization:** người dùng có quyền gọi chức năng tạo phiếu mượn không?
- **Resource-level authorization:** người dùng có quyền xem hoặc sửa phiếu mượn cụ thể không?
- **Tenant/organization scope:** dữ liệu thuộc thư viện hoặc đơn vị nào?
- **Field-level authorization:** người dùng có được xem thông tin nội bộ như ghi chú quản trị hoặc khoản phạt không?

Không chỉ kiểm tra role ở route. Một người có role `LIBRARIAN` vẫn có thể bị giới hạn theo chi nhánh; một thành viên chỉ được xem phiếu của chính mình.

Ví dụ:

~~~java
public LoanDetails getLoanForMember(long memberId, long loanId) {
    Loan loan = loans.findById(loanId)
            .orElseThrow(LoanNotFoundException::new);

    if (!loan.belongsTo(memberId)) {
        throw new LoanNotAccessibleException();
    }

    return mapper.toDetails(loan);
}
~~~

Policy trả 403 hay 404 phụ thuộc hợp đồng và yêu cầu tránh tiết lộ sự tồn tại của tài nguyên. Điều quan trọng là kiểm tra ở server với danh tính đã xác thực. Ẩn liên kết trong View không phải cơ chế bảo vệ.

### 7.1. Không tin dữ liệu phân quyền do client gửi

Các field sau cần được xem xét đặc biệt:

- `memberId`, `ownerId`, `tenantId`.
- `role`, `isAdmin`, `approved`.
- `status`, `createdBy`, `updatedBy`.
- `price`, `fineAmount`, `discount`.

Nếu client có thể gửi các field này và mapper tự động bind vào entity, ứng dụng có nguy cơ mass assignment. Hãy dùng DTO allowlist và gán các giá trị có thẩm quyền từ server.

## 8. Review transaction và tính nhất quán dữ liệu

Một use case có thể cần cập nhật nhiều dữ liệu:

1. Đánh dấu bản sao sách là đang được mượn.
2. Tạo phiếu mượn.
3. Tăng số phiếu đang hoạt động của thành viên hoặc cập nhật projection tương ứng.
4. Ghi audit/outbox event.

Nếu các thay đổi trong cùng database phải cùng thành công hoặc thất bại, transaction cần bao phủ toàn bộ đơn vị công việc phù hợp. Không để Controller gọi từng repository trong nhiều transaction tách rời mà không có thiết kế nhất quán.

~~~mermaid
sequenceDiagram
    participant C as Controller
    participant U as CreateLoan Use Case
    participant DB as Database Transaction
    participant O as Outbox
    C->>U: CreateLoanCommand
    U->>DB: Begin transaction
    U->>DB: Lock/check book copy
    U->>DB: Check member limit
    U->>DB: Create Loan + update copy
    U->>O: Insert LoanCreated event
    U->>DB: Commit
    DB-->>U: Commit successful
    U-->>C: CreateLoanResult
    Note over O: Publisher sends event after commit
~~~

Outbox event được ghi trong cùng transaction với thay đổi nghiệp vụ; publisher bên ngoài đọc và gửi sau commit. Cách này giảm nguy cơ database đã commit nhưng event bị mất do tiến trình dừng trước khi gửi. Consumer cần idempotency vì message có thể được gửi lại.

### 8.1. Không gửi side effect không thể rollback trước commit

Nếu gửi email hoặc gọi dịch vụ bên ngoài trước khi database commit, transaction có thể rollback sau khi email đã được gửi. Người nhận sẽ thấy thông tin về một phiếu mượn không tồn tại.

Các lựa chọn:

- Ghi outbox trong transaction rồi gửi sau commit.
- Dùng transaction event `AFTER_COMMIT` cho trường hợp đơn giản trong cùng ứng dụng, có nhận thức về độ bền của event.
- Dùng saga hoặc quy trình bù trừ khi phối hợp nhiều dịch vụ.
- Thiết kế command idempotent để retry không tạo nhiều phiếu.

Không giữ transaction database mở trong khi chờ người dùng hoặc chờ một cuộc gọi mạng dài.

## 9. Review cạnh tranh đồng thời và idempotency

Hai request có thể đến gần như đồng thời:

1. Request A đọc bản sao sách là AVAILABLE.
2. Request B cũng đọc cùng trạng thái AVAILABLE.
3. Cả hai cùng tạo phiếu mượn.
4. Hệ thống có hai phiếu ACTIVE cho một bản sao.

Kiểm tra trong Java trước khi ghi không đủ bảo vệ trường hợp này. Cần cơ chế ở database hoặc concurrency boundary:

- Pessimistic lock khi đọc bản sao để cập nhật.
- Optimistic locking bằng version và retry/conflict handling.
- Conditional update chỉ thành công khi trạng thái hiện tại còn AVAILABLE.
- Unique constraint phù hợp để chặn nhiều phiếu active cho cùng bản sao, nếu mô hình dữ liệu hỗ trợ.

Hạn mức của thành viên cũng có thể gặp race condition: hai request mượn hai cuốn khác nhau cùng đọc số phiếu đang hoạt động là 4 trong khi giới hạn là 5, rồi cả hai cùng tạo phiếu. Nếu invariant này phải được bảo đảm tuyệt đối, cần khóa hoặc cập nhật có điều kiện trên phạm vi thành viên, isolation phù hợp hoặc một mô hình reservation/constraint có thể thực thi ở database. Chỉ khóa từng bản sao sách không bảo vệ được hạn mức tổng của thành viên.

Ví dụ optimistic lock với JPA:

~~~java
@Entity
public class BookCopyEntity {
    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private CopyStatus status;

    @Version
    private long version;
}
~~~

`@Version` cho phép phát hiện cập nhật cạnh tranh khi transaction ghi một version đã cũ. Application layer cần chuyển lỗi optimistic locking thành kết quả xung đột phù hợp, ví dụ HTTP 409, và không tự retry vô hạn.

Idempotency key có thể giúp request retry sau timeout không tạo phiếu trùng. Key cần được lưu cùng kết quả hoặc liên kết với command đã xử lý trong phạm vi actor phù hợp. Không dùng idempotency key thay thế authorization hoặc kiểm soát tồn kho.

## 10. Review hợp đồng response và error

Response là điều client dựa vào. Review nên kiểm tra:

- Status code có phù hợp với hành động và trạng thái không?
- Field có ý nghĩa rõ và kiểu dữ liệu ổn định không?
- Có trả field nội bộ hoặc dữ liệu nhạy cảm không?
- Null, omitted và empty có ý nghĩa nhất quán không?
- Error code có ổn định để client xử lý không?
- Có trả thông tin debug, SQL, stack trace hoặc dữ liệu nội bộ không?

Một response lỗi có cấu trúc:

~~~json
{
  "type": "https://api.example.test/problems/book-unavailable",
  "title": "Không thể tạo phiếu mượn",
  "status": 409,
  "code": "BOOK_COPY_UNAVAILABLE",
  "detail": "Bản sao sách hiện không khả dụng."
}
~~~

Đây là ví dụ theo Problem Details; URL, status và code cần khớp hợp đồng thật. Client nên dựa vào `code` hoặc `type` ổn định, không parse câu `detail` để quyết định logic.

### 10.1. Ánh xạ lỗi nghiệp vụ ở adapter

Domain/application có thể ném exception có ý nghĩa nghiệp vụ:

- `BookCopyUnavailableException`
- `BorrowingLimitExceededException`
- `MemberNotActiveException`
- `LoanNotAccessibleException`
- `ConcurrentLoanUpdateException`

Adapter web chuyển các lỗi đó thành HTTP response:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BookCopyUnavailableException.class)
    ProblemDetail handleUnavailable(BookCopyUnavailableException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.CONFLICT
        );
        problem.setTitle("Không thể tạo phiếu mượn");
        problem.setDetail("Bản sao sách hiện không khả dụng.");
        problem.setProperty("code", "BOOK_COPY_UNAVAILABLE");
        return problem;
    }

    @ExceptionHandler(BorrowingLimitExceededException.class)
    ProblemDetail handleLimit(BorrowingLimitExceededException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(
                HttpStatus.UNPROCESSABLE_ENTITY
        );
        problem.setTitle("Vượt hạn mức mượn");
        problem.setProperty("code", "BORROWING_LIMIT_EXCEEDED");
        return problem;
    }
}
~~~

Status code cụ thể là quyết định API design. Có thể chọn 409 cho xung đột trạng thái và 422 cho điều kiện nghiệp vụ không thể xử lý; điều quan trọng là dùng nhất quán, có tài liệu và có test. Không trả exception message nội bộ nguyên văn nếu nó có thể chứa dữ liệu hoặc chi tiết triển khai.

## 11. Review tương thích và tiến hóa hợp đồng dữ liệu

Hợp đồng API có thể được nhiều client sử dụng độc lập. Một thay đổi tưởng nhỏ trong DTO có thể phá client cũ.

| Thay đổi | Rủi ro tương thích | Cách review |
|---|---|---|
| Thêm field response tùy chọn | Thường ít rủi ro nhưng client strict parser có thể lỗi | Kiểm tra consumer và serializer |
| Xóa hoặc đổi tên field | Cao | Versioning/deprecation và migration |
| Đổi kiểu số thành chuỗi | Cao | Giữ schema hoặc version contract |
| Thêm enum value | Có thể làm client cũ không parse được | Quy định cách client xử lý giá trị chưa biết |
| Thay null bằng omitted | Có thể đổi ý nghĩa | Định nghĩa semantics rõ |
| Đổi status code | Có thể làm thay đổi nhánh xử lý client | Contract test và release note |
| Siết validation | Có thể từ chối request trước đây hợp lệ | Phân tích dữ liệu/client đang gửi |
| Đổi timezone hoặc format ngày | Cao nếu client diễn giải khác | Chuẩn hóa ISO-8601 và timezone |

### 11.1. Null, omitted và empty

Ba trạng thái có thể khác nhau:

- Field không xuất hiện: client không gửi hoặc server không công bố giá trị.
- Field có `null`: giá trị được xác định là không có.
- Field có chuỗi rỗng hoặc danh sách rỗng: có giá trị nhưng không chứa phần tử.

Với PATCH, cần xác định `null` có nghĩa xóa field hay bỏ qua cập nhật. Không để mapper tự quyết định ngầm.

### 11.2. Ngày giờ, tiền và enum

- Dùng `LocalDate` cho ngày lịch không gắn thời điểm, ví dụ dueDate.
- Dùng `Instant` hoặc offset-aware timestamp cho thời điểm tuyệt đối.
- Quy định timezone khi hiển thị cho người dùng.
- Với tiền, giữ amount và currency riêng; không dùng floating-point cho tính toán tiền.
- Dùng mã enum ổn định trong API; tránh đổi tên enum nội bộ làm đổi response ngoài ý muốn.

## 12. Review mapping và nguy cơ mass assignment

Mapper là nơi chuyển đổi dữ liệu giữa các hợp đồng. Review cần kiểm tra mapping tường minh, đặc biệt với field nhạy cảm hoặc field chỉ server được phép đặt.

Ví dụ rủi ro:

~~~java
BeanUtils.copyProperties(request, loanEntity);
~~~

Nếu request object có thêm field `status`, `memberId` hoặc `fineAmount`, việc copy tự động có thể ghi đè dữ liệu mà client không được phép kiểm soát.

Mapping tường minh:

~~~java
CreateLoanCommand toCommand(
        CreateLoanRequest request,
        CurrentUser user
) {
    return new CreateLoanCommand(
            user.memberId(),
            request.bookId(),
            request.dueDate()
    );
}
~~~

Review mapping theo nguyên tắc allowlist:

- Field nào client được gửi?
- Field nào lấy từ principal hoặc tenant context?
- Field nào do domain tính?
- Field nào do database tạo?
- Field nào chỉ được trả cho role cụ thể?
- Field nào phải được loại bỏ khỏi response?

Không xem mapper là lớp kỹ thuật vô hại. Một mapping sai có thể trở thành lỗi phân quyền hoặc phá vỡ invariant.

## 13. Review repository và truy vấn theo phạm vi

Repository không chỉ lưu và đọc dữ liệu; nó còn phải bảo vệ phạm vi truy vấn theo thiết kế.

Ví dụ, truy vấn phiếu mượn của một thành viên nên ràng buộc cả loan ID và member ID:

~~~java
Optional<LoanEntity> findByIdAndMemberId(
        long loanId,
        long memberId
);
~~~

Điều này giảm nguy cơ IDOR khi endpoint nhận ID tài nguyên từ URL. Với hệ thống đa tenant, điều kiện tenant cũng cần được áp dụng từ context tin cậy.

Review thêm:

- Có truy vấn nào tải toàn bộ dữ liệu rồi lọc ở Java không?
- Có N+1 query khi mapper hoặc View truy cập quan hệ lazy không?
- Có phân trang/giới hạn khi dữ liệu lớn không?
- Có unique constraint hoặc index hỗ trợ invariant không?
- Có lộ field nội bộ qua projection không?
- Transaction isolation có phù hợp với cập nhật cạnh tranh không?

Không chuyển mọi quy tắc nghiệp vụ thành điều kiện SQL. Repository thực hiện truy vấn và persistence constraint; domain/application vẫn là nơi mô tả ý nghĩa nghiệp vụ. Tuy nhiên, database constraint có thể là lớp bảo vệ cuối cùng cho invariant quan trọng dưới tải đồng thời.

## 14. Review sự kiện và hợp đồng giữa các module

Nếu use case phát event như `LoanCreated`, đó cũng là một hợp đồng dữ liệu. Consumer có thể chạy ở service khác hoặc được triển khai độc lập.

Event nên chứa thông tin cần thiết để consumer xử lý, không nhất thiết sao chép toàn bộ domain entity:

~~~java
public record LoanCreatedEvent(
        UUID eventId,
        long loanId,
        long memberId,
        long bookCopyId,
        Instant occurredAt,
        int schemaVersion
) {
}
~~~

Review event contract:

- Event biểu diễn sự kiện đã xảy ra hay command yêu cầu hành động?
- Field nào bắt buộc và field nào có thể bổ sung?
- Consumer có thể nhận event trùng không?
- Có event ordering requirement không?
- Schema có version hoặc chính sách tương thích không?
- Có chứa PII hoặc dữ liệu nhạy cảm không cần thiết không?
- Retry và dead-letter được xử lý thế nào?

Tên event nên mô tả sự kiện đã xảy ra (`LoanCreated`) thay vì mệnh lệnh (`CreateLoan`). Không công bố object domain mutable trực tiếp làm message payload.

## 15. Bộ kiểm thử cần có để bảo vệ hợp đồng và ranh giới

Một review không kết thúc ở việc đọc code. Hãy kiểm tra xem các ranh giới quan trọng đã có test chứng minh chưa.

| Loại test | Nội dung cần xác nhận |
|---|---|
| Request/contract test | Field bắt buộc, kiểu dữ liệu, status, response schema |
| MVC slice test | Binding, validation, authentication, error mapping |
| Use case test | Actor, policy, command, kết quả và port interaction |
| Domain unit test | Invariant, trạng thái và phép tính |
| Repository integration test | Query scope, unique constraint, optimistic lock |
| Transaction test | Rollback, commit và outbox |
| Security test | Không đọc/sửa tài nguyên ngoài phạm vi |
| Concurrency test | Hai request cạnh tranh không phá invariant |
| Consumer contract test | Event schema và hành vi consumer |

### 15.1. Test request không thể tự gán memberId

Một test nên xác nhận danh tính đến từ principal:

~~~java
@Test
void createLoanUsesAuthenticatedMember() throws Exception {
    given(createLoan.execute(any()))
            .willReturn(new CreateLoanResult(
                    9001L, 42L, LocalDate.parse("2026-12-03"),
                    LoanStatus.ACTIVE
            ));

    mockMvc.perform(post("/api/loans")
                    .with(authentication(memberAuthentication(7L)))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "bookId": 42,
                              "dueDate": "2026-12-03",
                              "memberId": 999
                            }
                            """))
            .andExpect(status().isCreated());

    ArgumentCaptor<CreateLoanCommand> captor =
            ArgumentCaptor.forClass(CreateLoanCommand.class);
    verify(createLoan).execute(captor.capture());
    assertThat(captor.getValue().memberId()).isEqualTo(7L);
}
~~~

Ví dụ giả định DTO không có field `memberId`; JSON field dư được bỏ qua hoặc xử lý theo cấu hình deserializer. Nếu API được cấu hình từ chối unknown property, test có thể mong đợi 400 thay vì tiếp tục. Trong cả hai chính sách, client không thể chọn memberId của command.

### 15.2. Test domain invariant

~~~java
@Test
void cannotCloseAlreadyClosedLoan() {
    Loan loan = anActiveLoan();
    loan.close(LocalDate.parse("2026-11-20"));

    assertThatThrownBy(
            () -> loan.close(LocalDate.parse("2026-11-21"))
    ).isInstanceOf(LoanCannotBeClosedException.class);
}
~~~

Test này bảo vệ quy tắc miền mà không cần Spring MVC hoặc database.

### 15.3. Test xung đột cập nhật

Integration test nên tạo hai transaction cạnh tranh trên cùng bản sao sách và xác nhận chỉ một thao tác thành công. Cách đồng bộ test cần dùng barrier/latch hoặc transaction riêng để tạo tình huống xác định; không dùng `Thread.sleep()` để hy vọng race xuất hiện.

## 16. Quy trình review thiết kế trong một buổi

Một buổi review hiệu quả có thể đi theo thứ tự:

1. **Xác định use case:** mục tiêu người dùng, actor và resource.
2. **Đọc hợp đồng đầu vào:** route, method, request schema, validation và nguồn danh tính.
3. **Đọc mapping:** request DTO thành command; kiểm tra field nào bị bỏ qua hoặc được server bổ sung.
4. **Theo dõi nghiệp vụ:** policy, aggregate, invariant và trạng thái trước/sau.
5. **Theo dõi persistence:** repository query, transaction, constraint và concurrency.
6. **Đọc hợp đồng đầu ra:** response DTO, status, error code, header và field nhạy cảm.
7. **Đánh giá tương thích:** client cũ, event consumer, nullability, enum và versioning.
8. **Kiểm tra test:** xác nhận test ở đúng ranh giới và có trường hợp thất bại.
9. **Ghi finding:** nêu bằng chứng, tác động, mức độ và đề xuất sửa.

Đừng review tất cả file theo thứ tự folder. Bắt đầu từ một request cụ thể và theo dõi đường đi của nó; cách này dễ phát hiện ranh giới bị bỏ qua hơn.

## 17. Mẫu ghi nhận finding

Một finding tốt cần giúp người sửa hiểu vấn đề và kiểm chứng được:

~~~text
ID: API-LOAN-01
Vị trí: LoanController.create / CreateLoanRequest
Mức độ: High
Quan sát: Request có thể cung cấp memberId và mapper copy field này vào command.
Rủi ro: Người dùng có thể tạo phiếu mượn dưới danh tính thành viên khác.
Bằng chứng: DTO/mapper nhận memberId từ JSON; không thay bằng principal.
Đề xuất: Bỏ memberId khỏi request DTO; lấy actor từ authenticated principal.
Kiểm thử: Gửi memberId giả trong request và xác nhận command dùng memberId từ principal.
~~~

Phân loại mức độ có thể dựa trên tác động:

| Mức độ | Ví dụ |
|---|---|
| Critical | Có thể truy cập dữ liệu nhạy cảm xuyên tenant hoặc bỏ qua quyền nghiêm trọng |
| High | Có thể tạo/cập nhật dữ liệu dưới danh tính khác hoặc phá invariant quan trọng |
| Medium | Response sai hợp đồng, transaction thiếu nhất quán trong trường hợp có thể xảy ra |
| Low | Tên field khó hiểu, mapping lặp hoặc thiếu test cho trường hợp ít rủi ro |

Mức độ phải dựa trên khả năng khai thác, phạm vi ảnh hưởng và hậu quả nghiệp vụ; không chỉ dựa vào số dòng code.

## 18. Các dấu hiệu thiết kế cần xem xét

| Dấu hiệu | Rủi ro | Hướng review |
|---|---|---|
| Controller nhận thẳng JPA entity | Mass assignment, lộ field nội bộ | Dùng request DTO và mapping allowlist |
| Client gửi owner/member/tenant ID | Giả mạo actor hoặc truy cập chéo phạm vi | Lấy từ principal/context tin cậy |
| Controller chứa toàn bộ quy tắc | Khó tái sử dụng và test không nhất quán | Chuyển vào use case/domain policy |
| View ẩn nút để “bảo vệ” thao tác | Endpoint vẫn có thể bị gọi trực tiếp | Authorization ở server |
| Response serialize entity | Lộ dữ liệu, lazy loading, vòng tham chiếu | Response DTO riêng |
| Một field status được cập nhật từ request | Bỏ qua state transition | Command mô tả hành động, domain quyết định trạng thái |
| Validation chỉ ở form | API hoặc batch có thể bỏ qua | Bảo vệ invariant ở lớp trong |
| Ghi nhiều bảng qua nhiều transaction không rõ | Trạng thái một phần | Xác định transaction boundary |
| Kiểm tra tồn kho trước rồi ghi không khóa | Race condition | Lock, version, conditional update hoặc constraint |
| Gửi email trước commit | Side effect không thể rollback | Outbox hoặc gửi sau commit |
| Mapper copy tất cả field | Ghi đè dữ liệu server quản lý | Mapping tường minh |
| Error trả stack trace/SQL | Lộ chi tiết nội bộ | Error contract ổn định |
| Đổi enum hoặc nullability không review client | Breaking change | Contract/version compatibility test |
| Không có test ở repository/transaction | Chỉ kiểm thử mock, bỏ sót lỗi thật | Integration/concurrency test |

## 19. Checklist review hợp đồng dữ liệu

**Request**

- Route, method và content type có rõ không?
- Field bắt buộc, tùy chọn, null và default có được định nghĩa không?
- Kiểu ngày giờ, số tiền, enum và ID có ổn định không?
- Request DTO có chỉ chứa field client được phép gửi không?
- Unknown field được bỏ qua hay từ chối theo chính sách nào?
- Giới hạn kích thước, độ dài và số lượng có được áp dụng không?

**Command và mapping**

- Command có thể hiện ý định nghiệp vụ rõ không?
- Actor/tenant có đến từ nguồn tin cậy không?
- Mapper có allowlist và không copy field nhạy cảm không?
- Request DTO có bị dùng nhầm làm domain entity không?

**Response**

- Status, header và body có khớp hợp đồng không?
- Response có lộ field nội bộ hoặc dữ liệu nhạy cảm không?
- Null, omitted, empty và enum có semantics rõ không?
- Error code có ổn định và không lộ chi tiết nội bộ không?
- Thay đổi có tương thích client cũ không?

## 20. Checklist review ranh giới nghiệp vụ

- Actor và resource được xác định từ nguồn đáng tin cậy chưa?
- Authorization được kiểm tra ở server cho đúng resource/tenant chưa?
- Quy tắc nghiệp vụ có một nơi chịu trách nhiệm chính chưa?
- Aggregate root có bảo vệ invariant không?
- Command có mô tả hành động thay vì cho client sửa trạng thái tùy ý không?
- Use case có điều phối các bước cần thiết không?
- Repository có áp dụng phạm vi truy vấn và constraint phù hợp không?
- Transaction có bao phủ các thay đổi cần nguyên tử không?
- Side effect có được phát ở thời điểm phù hợp không?
- Cạnh tranh đồng thời và retry có được xử lý không?
- Idempotency có cần thiết cho thao tác có thể retry không?
- Có test chứng minh cả happy path và trường hợp bị từ chối không?

## 21. Kết luận

Review hợp đồng dữ liệu và ranh giới nghiệp vụ là cách kiểm tra xem một request MVC có đi qua đúng trách nhiệm hay không. Request DTO mô tả dữ liệu client được phép gửi; Controller lấy danh tính từ ngữ cảnh xác thực và chuyển request thành command; use case điều phối hành động; domain model bảo vệ invariant; repository và database duy trì trạng thái; presenter tạo response đúng hợp đồng.

Một thiết kế đáng tin cậy không dựa vào việc người dùng gửi dữ liệu “đúng như giao diện”, cũng không dựa vào việc các bước kiểm tra trong Controller luôn được gọi. Nó bảo vệ quyền và quy tắc ở phía server, giữ các thay đổi liên quan trong transaction phù hợp, xử lý cạnh tranh đồng thời và công bố schema có thể tiến hóa có kiểm soát. Khi review theo luồng end-to-end và có test cho từng ranh giới, nhóm có thể phát hiện sớm mass assignment, rò dữ liệu, invariant bị phá vỡ và breaking change trước khi chúng trở thành lỗi production.
