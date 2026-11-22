# Phân quyền thao tác và xử lý dữ liệu không tồn tại

Trong ví dụ quản lý sách theo **MODEL_VIEW_CONTROLLER**, người dùng có thể xem danh mục, tìm sách, tạo hoặc cập nhật đầu sách, mượn sách và theo dõi phiếu mượn. Những thao tác này không dành cho mọi người dùng như nhau. Khách chưa đăng nhập có thể được xem danh mục công khai; thành viên có thể mượn sách và xem phiếu mượn của chính mình; thủ thư quản lý đầu sách và quy trình mượn/trả; quản trị viên quản lý các thao tác quản trị nhạy cảm.

Một ứng dụng MVC cần kiểm tra quyền ở phía server cho từng request và từng tài nguyên. Việc ẩn nút trên View chỉ giúp giao diện dễ sử dụng, không ngăn người dùng tự tạo request. Đồng thời, khi một mã sách hoặc phiếu mượn không tồn tại, ứng dụng cần trả kết quả nhất quán như **404 Not Found**, thay vì trả dữ liệu rỗng, null hoặc lỗi máy chủ không rõ nguyên nhân.

Bài này trình bày cách thiết kế ma trận quyền, bảo vệ endpoint và dữ liệu theo người sở hữu, lấy danh tính từ security context, xử lý tài nguyên không tồn tại và kiểm thử các tình huống thành công, bị từ chối hoặc không tìm thấy trong một ứng dụng Spring MVC.

## 1. Xác định vai trò và thao tác trong hệ thống quản lý sách

Trước khi viết annotation hoặc cấu hình Spring Security, cần liệt kê các thao tác mà hệ thống cung cấp. Một ví dụ đơn giản có ba vai trò:

- **MEMBER (thành viên):** xem danh mục công khai, mượn sách và xem phiếu mượn của chính mình.
- **LIBRARIAN (thủ thư):** tạo, cập nhật đầu sách, quản lý số bản còn có thể cho mượn và xác nhận quy trình mượn/trả.
- **ADMIN (quản trị viên):** quản lý người dùng, vai trò và các thao tác quản trị nhạy cảm.

Ma trận quyền minh họa:

| Thao tác | Khách | MEMBER | LIBRARIAN | ADMIN |
| --- | --- | --- | --- | --- |
| Xem danh mục sách công khai | Cho phép | Cho phép | Cho phép | Cho phép |
| Xem chi tiết sách công khai | Cho phép | Cho phép | Cho phép | Cho phép |
| Tạo đầu sách | Từ chối | Từ chối | Cho phép | Cho phép |
| Sửa thông tin đầu sách | Từ chối | Từ chối | Cho phép | Cho phép |
| Xóa/ẩn đầu sách | Từ chối | Từ chối | Theo chính sách | Cho phép |
| Tạo phiếu mượn cho chính mình | Từ chối | Cho phép | Theo nghiệp vụ | Cho phép |
| Xem phiếu mượn của mình | Từ chối | Cho phép | Cho phép | Cho phép |
| Xem phiếu mượn của thành viên khác | Từ chối | Từ chối | Theo nhiệm vụ | Cho phép |
| Quản lý vai trò người dùng | Từ chối | Từ chối | Từ chối | Cho phép |

Ma trận cần được điều chỉnh theo chính sách thư viện thực tế. Ví dụ, một số thư viện cho phép thủ thư xóa đầu sách nhưng chỉ khi không còn bản sao đang được mượn; một số hệ thống chỉ cho phép ẩn sách khỏi danh mục. Quyền vai trò xác định nhóm hành động, còn quy tắc nghiệp vụ xác định hành động có hợp lệ với trạng thái tài nguyên hiện tại hay không.

## 2. Phân biệt xác thực và phân quyền

Hai khái niệm này giải quyết hai câu hỏi khác nhau:

- **Authentication (xác thực):** request đến từ ai? Ví dụ, người dùng đã đăng nhập bằng tài khoản thành viên nào?
- **Authorization (phân quyền):** người đó có được phép thực hiện hành động cụ thể trên tài nguyên này không? Ví dụ, thành viên có được xem phiếu mượn có ID 501 hay chỉ được xem phiếu của chính mình?

Người dùng đăng nhập thành công không có nghĩa họ được phép thực hiện mọi thao tác. Một thành viên có thể được xác thực nhưng vẫn không có quyền tạo đầu sách hoặc thay đổi vai trò người dùng.

Trong Spring Security, sau khi xác thực thành công, danh tính và authorities được đặt trong SecurityContext. Controller có thể lấy principal từ context:

~~~java
public record AppPrincipal(
        UserId userId,
        String username
) {}
~~~

~~~java
@GetMapping("/my/loans")
public String myLoans(
        @AuthenticationPrincipal AppPrincipal principal,
        Model model) {
    model.addAttribute(
            "loans",
            loanQuery.findForBorrower(principal.userId())
    );
    return "loans/mine";
}
~~~

userId được lấy từ principal đã xác thực, không lấy từ một trường hidden hoặc query parameter do trình duyệt gửi. Điều này ngăn người dùng thay userId trong request để yêu cầu dữ liệu của tài khoản khác.

## 3. Bảo vệ route ở ranh giới HTTP

Với Spring Security, có thể khai báo quyền theo HTTP method và URL pattern trong SecurityFilterChain. Ví dụ:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/books", "/books/*")
                            .permitAll()
                        .requestMatchers(HttpMethod.POST, "/books/*/loans")
                            .hasAnyRole("MEMBER", "LIBRARIAN", "ADMIN")
                        .requestMatchers(HttpMethod.POST, "/books/**")
                            .hasAnyRole("LIBRARIAN", "ADMIN")
                        .requestMatchers(HttpMethod.PUT, "/books/**")
                            .hasAnyRole("LIBRARIAN", "ADMIN")
                        .requestMatchers(HttpMethod.DELETE, "/books/**")
                            .hasRole("ADMIN")
                        .requestMatchers("/admin/**")
                            .hasRole("ADMIN")
                        .requestMatchers("/my/loans", "/my/loans/**")
                            .hasAnyRole("MEMBER", "LIBRARIAN", "ADMIN")
                        .anyRequest()
                            .authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

Ví dụ cho phép xem danh mục công khai, yêu cầu thủ thư hoặc quản trị viên khi tạo/cập nhật sách và chỉ quản trị viên được xóa sách. Các endpoint còn lại yêu cầu đăng nhập. Ứng dụng có thể thay formLogin bằng cơ chế xác thực phù hợp.

hasRole("ADMIN") thường kiểm tra authority ROLE_ADMIN; cần thống nhất cách đặt role khi tạo tài khoản. Cấu hình route là lớp bảo vệ đầu tiên và giúp chính sách dễ nhìn thấy. Tuy nhiên, URL pattern không thể diễn đạt đầy đủ quyền trên từng bản ghi, ví dụ thành viên chỉ được xem phiếu mượn do chính họ tạo.

## 4. Kiểm tra quyền ở use case và trên từng tài nguyên

Có thể dùng method security để bảo vệ các hành động nghiệp vụ:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

~~~java
@Service
public class BookCommandService {
    private final BookRepository books;

    public BookCommandService(BookRepository books) {
        this.books = books;
    }

    @PreAuthorize("hasAnyRole('LIBRARIAN', 'ADMIN')")
    @Transactional
    public BookId create(CreateBookCommand command) {
        Book book = Book.create(
                command.isbn(),
                command.title(),
                command.author()
        );
        return books.save(book).id();
    }

    @PreAuthorize("hasAnyRole('LIBRARIAN', 'ADMIN')")
    @Transactional
    public void update(BookId id, UpdateBookCommand command) {
        Book book = books.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
        book.updateDetails(command.title(), command.author());
        books.save(book);
    }

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public void remove(BookId id) {
        Book book = books.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
        book.archive();
    }
}
~~~

Method security giúp chính sách gắn với thao tác nghiệp vụ, kể cả khi thao tác được gọi từ một Controller khác. Các phương thức được bảo vệ phải được gọi qua Spring proxy; gọi một phương thức được bảo vệ từ một phương thức khác trong cùng instance (self-invocation) có thể bỏ qua proxy. Với logic quyền phức tạp theo tài nguyên, nên gọi một policy/service kiểm tra quyền rõ ràng bên trong use case.

Đừng chỉ dựa vào @PreAuthorize ở một Controller rồi cho rằng mọi caller khác cũng an toàn. Use case có thể được gọi từ REST controller khác, tác vụ nền hoặc một luồng nội bộ. Quy tắc quyền cần được đặt ở ranh giới mà mọi đường gọi phải đi qua.

## 5. Quyền theo vai trò và quyền theo đối tượng

Role-based access control (RBAC) trả lời người dùng thuộc nhóm nào và nhóm đó có thể làm loại thao tác nào. Nhưng nhiều tài nguyên còn cần kiểm tra quyền theo đối tượng:

- Thành viên chỉ được xem phiếu mượn của mình.
- Thủ thư chỉ được thao tác trên chi nhánh được phân công.
- Người dùng chỉ được sửa hồ sơ của chính mình.
- Một đầu sách có thể xem công khai, nhưng chỉ thủ thư được sửa.

Ví dụ repository cung cấp truy vấn theo ID phiếu mượn và người mượn:

~~~java
public interface LoanRepository {
    Optional<Loan> findByIdAndBorrowerId(
            LoanId loanId,
            UserId borrowerId
    );
}
~~~

Query service chỉ trả phiếu mượn thuộc thành viên đang đăng nhập:

~~~java
@Service
public class LoanQuery {
    private final LoanRepository loans;

    public LoanQuery(LoanRepository loans) {
        this.loans = loans;
    }

    @PreAuthorize("#p1 == authentication.principal.userId()")
    public LoanDetailView getMine(LoanId loanId, UserId borrowerId) {
        Loan loan = loans.findByIdAndBorrowerId(loanId, borrowerId)
                .orElseThrow(() -> new LoanNotFoundException(loanId));
        return LoanDetailView.from(loan);
    }
}
~~~

Nếu thành viên A thử thay ID để xem phiếu của thành viên B, truy vấn không trả bản ghi và ứng dụng có thể trả 404. Cách truy vấn có điều kiện này giúp tránh lộ thông tin về việc phiếu mượn của người khác có tồn tại hay không.

Với thủ thư hoặc quản trị viên có quyền xem nhiều phiếu, có thể cung cấp use case khác được bảo vệ theo vai trò và phạm vi chi nhánh. Không nên bỏ điều kiện owner khỏi endpoint “phiếu của tôi” chỉ để tái sử dụng cho màn hình quản trị.

## 6. Không tin ID hoặc vai trò do client gửi

Những giá trị sau đều có thể bị người dùng thay đổi:

- userId, borrowerId hoặc ownerId trong query string, URL hay JSON.
- Trường hidden như role, isAdmin, branchId hoặc approved.
- Nút bị ẩn hoặc disabled trên View.
- Trạng thái hiển thị trong JavaScript.
- ID của một bản ghi được gửi trong form.

Server có thể nhận bookId từ URL vì đó là tài nguyên người dùng muốn truy cập, nhưng phải truy vấn và kiểm tra quyền trên bản ghi. Với hành động mượn sách, người mượn phải lấy từ principal:

~~~java
@PostMapping("/books/{id}/loans")
public String borrow(
        @PathVariable long id,
        @AuthenticationPrincipal AppPrincipal principal,
        RedirectAttributes flash) {
    loanService.borrow(
            new BookId(id),
            principal.userId()
    );
    flash.addFlashAttribute("message", "Đã tạo yêu cầu mượn sách.");
    return "redirect:/my/loans";
}
~~~

Client chỉ gửi ID sách. Server xác định người mượn từ principal, kiểm tra sách có tồn tại và còn được mượn hay không, rồi tạo phiếu mượn gắn với đúng thành viên.

## 7. Xử lý dữ liệu không tồn tại bằng Optional và exception có nghĩa

Khi tìm sách theo ID, repository nên thể hiện rõ khả năng không tìm thấy:

~~~java
public interface BookRepository {
    Optional<Book> findById(BookId id);
}
~~~

Không nên trả null rồi để Controller tự kiểm tra ở nhiều nơi. Có thể tạo exception mang ý nghĩa nghiệp vụ:

~~~java
public class BookNotFoundException extends RuntimeException {
    public BookNotFoundException(BookId id) {
        super("Book not found: " + id.value());
    }
}
~~~

Use case hoặc query service chuyển kết quả thiếu thành exception:

~~~java
public BookDetailView getDetail(BookId id) {
    Book book = books.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    return BookDetailView.from(book);
}
~~~

Controller không phải lặp if (book == null) cho mọi endpoint. Một exception handler có thể ánh xạ trường hợp này thành response hoặc trang lỗi phù hợp.

Không nên trả một đối tượng mặc định hoặc danh sách rỗng khi một tài nguyên đơn lẻ không tồn tại. GET /books/123 có ý nghĩa khác GET /books?author=... không có kết quả:

- Không tìm thấy tài nguyên theo ID: thường là 404 Not Found.
- Tìm danh sách hợp lệ nhưng không có phần tử phù hợp: thường trả 200 OK với danh sách rỗng.

## 8. Phân biệt 401, 403, 404 và 409

Các status code cần phản ánh đúng nguyên nhân:

| Mã HTTP | Ý nghĩa | Ví dụ trong quản lý sách |
| --- | --- | --- |
| 400 Bad Request | Request sai cấu trúc hoặc dữ liệu không hợp lệ | ISBN thiếu hoặc số lượng mượn không hợp lệ |
| 401 Unauthorized | Chưa xác thực hoặc thông tin xác thực không hợp lệ | Khách gọi endpoint yêu cầu đăng nhập |
| 403 Forbidden | Đã xác thực nhưng không có quyền thực hiện | Thành viên gọi API tạo đầu sách |
| 404 Not Found | Không có tài nguyên phù hợp với request | Mã sách không tồn tại |
| 409 Conflict | Tài nguyên tồn tại nhưng trạng thái hiện tại xung đột với hành động | Sách đã bị lưu trữ hoặc không còn bản có thể mượn |

Tên 401 Unauthorized dễ gây nhầm: mã này thường có nghĩa request chưa được xác thực. 403 Forbidden cho biết server hiểu người gọi là ai nhưng từ chối quyền. Với ứng dụng HTML dùng form login, Spring Security thường redirect khách đến trang đăng nhập thay vì trả trực tiếp 401; với REST API, có thể cấu hình entry point trả 401.

### Khi nào trả 403 hay 404 cho tài nguyên người gọi không được xem?

Nếu tài nguyên tồn tại nhưng người gọi không có quyền, có hai chính sách thường gặp:

- Trả 403 khi sản phẩm cho phép người dùng biết tài nguyên tồn tại nhưng họ không được truy cập.
- Trả 404 khi cần che giấu sự tồn tại của tài nguyên, ví dụ phiếu mượn thuộc thành viên khác.

Chọn chính sách nhất quán theo loại tài nguyên và không để response, thời gian xử lý hoặc thông báo vô tình tiết lộ dữ liệu. Truy vấn findByIdAndBorrowerId là một cách thực hiện chính sách 404 cho tài nguyên ngoài phạm vi.

## 9. Ánh xạ exception thành HTTP response

Với REST API, @RestControllerAdvice có thể chuyển exception thành response có cấu trúc. Ví dụ Spring Framework 6 hỗ trợ ProblemDetail:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<ProblemDetail> handleBookNotFound(
            BookNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Không tìm thấy đầu sách."
        );
        problem.setTitle("Không tìm thấy tài nguyên");
        problem.setProperty("code", "BOOK_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(BookNotAvailableException.class)
    ResponseEntity<ProblemDetail> handleBookUnavailable(
            BookNotAvailableException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "Sách hiện không có bản sẵn sàng để mượn."
        );
        problem.setTitle("Không thể thực hiện thao tác");
        problem.setProperty("code", "BOOK_NOT_AVAILABLE");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
~~~

Response chỉ chứa thông tin cần thiết cho client. Không trả stack trace, câu SQL, đường dẫn file hoặc chi tiết nội bộ trong nội dung lỗi công khai. Chi tiết phục vụ điều tra nên được ghi log ở server với correlation ID và không chứa dữ liệu xác thực nhạy cảm.

AccessDeniedException và lỗi chưa xác thực thường được xử lý ở Spring Security filter chain, trước khi request vào Controller. Vì vậy, không nên giả định mọi lỗi 401/403 đều được @RestControllerAdvice bắt. Hãy cấu hình AuthenticationEntryPoint và AccessDeniedHandler hoặc cơ chế form login phù hợp.

## 10. Trả trang lỗi cho ứng dụng HTML MVC

Với trang server-rendered, có thể trả template lỗi thân thiện:

~~~java
@ControllerAdvice
public class HtmlErrorHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ModelAndView bookNotFound() {
        ModelAndView view = new ModelAndView("errors/404");
        view.setStatus(HttpStatus.NOT_FOUND);
        view.addObject(
                "message",
                "Đầu sách bạn yêu cầu không tồn tại hoặc đã được gỡ khỏi danh mục."
        );
        return view;
    }
}
~~~

Template errors/404 nên có liên kết quay lại danh mục, thông báo rõ ràng và không để lộ exception kỹ thuật. Handler đặt HTTP status thành 404 rõ ràng; chỉ đặt tên View là errors/404 không tự động làm response mang status 404. Hai ví dụ HTML và API ở trên là hai cách ánh xạ cho hai loại endpoint; nếu cùng tồn tại, hãy scope advice bằng basePackages hoặc assignableTypes để chúng không cùng bắt một exception trên toàn ứng dụng. Ví dụ có thể đặt REST controller trong package api và dùng RestControllerAdvice(basePackages = "com.example.web.api"), còn HTML controller trong package html và dùng ControllerAdvice(basePackages = "com.example.web.html").

Với request form thành công, mẫu Post/Redirect/Get giúp tránh gửi lại thao tác khi người dùng tải lại trang:

~~~java
@PostMapping("/books")
public String create(
        @Valid @ModelAttribute("form") BookForm form,
        BindingResult result,
        RedirectAttributes flash) {
    if (result.hasErrors()) {
        return "books/new";
    }
    BookId id = bookCommandService.create(form.toCommand());
    flash.addFlashAttribute("message", "Đã tạo đầu sách.");
    return "redirect:/books/" + id.value();
}
~~~

Nếu sách không tồn tại khi mở trang chi tiết, handler trả trang 404. Nếu người dùng gửi form cập nhật cho ID không còn tồn tại, server cũng phải xử lý BookNotFoundException; không được giả định bản ghi vẫn tồn tại chỉ vì form đã được hiển thị trước đó.

## 11. Xử lý xóa và trạng thái tài nguyên

Trong hệ thống quản lý sách, xóa cứng một đầu sách có thể không phù hợp nếu sách đã có lịch sử mượn. Nhiều ứng dụng dùng trạng thái lưu trữ (ARCHIVED) hoặc ẩn khỏi danh mục thay vì xóa bản ghi.

Use case xóa/ẩn cần kiểm tra:

- Người gọi có vai trò phù hợp hay không.
- Đầu sách có tồn tại hay không.
- Có bản sao đang được mượn hoặc phiếu mượn đang mở không.
- Chính sách cho phép lưu trữ hay yêu cầu hoàn tất giao dịch trước.

Ví dụ:

~~~java
@PreAuthorize("hasRole('ADMIN')")
@Transactional
public void archive(BookId id) {
    Book book = books.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));

    if (loans.existsOpenLoanForBook(id)) {
        throw new BookHasOpenLoansException(id);
    }

    book.archive();
    books.save(book);
}
~~~

Nếu sách tồn tại nhưng còn phiếu mượn mở, đây không phải lỗi 404. Tài nguyên có thật nhưng trạng thái hiện tại không cho phép hành động, vì vậy có thể ánh xạ sang 409 Conflict. Quy tắc kiểm tra và cập nhật phải được bảo vệ trong transaction hoặc cơ chế đồng thời phù hợp để tránh tình trạng phát sinh phiếu mượn mới ngay sau khi kiểm tra.

## 12. Phân biệt tài nguyên không tồn tại và danh sách rỗng

Trong quản lý sách, các trường hợp sau có ý nghĩa khác nhau:

| Request | Kết quả phù hợp |
| --- | --- |
| GET /books/99999 và ID không tồn tại | 404 Not Found |
| GET /books?author=Unknown và không có sách phù hợp | 200 OK với danh sách rỗng |
| GET /my/loans/501 nhưng phiếu không thuộc người đang đăng nhập | 404 nếu chính sách che giấu tài nguyên |
| GET /books/10 và sách đã lưu trữ, không còn hiển thị công khai | 404 đối với danh mục công khai hoặc response theo chính sách lưu trữ |
| POST /books bởi thành viên | 403 Forbidden hoặc redirect tới trang không đủ quyền trong ứng dụng HTML |
| POST /books/10/loans khi sách đã hết bản có thể mượn | 409 Conflict hoặc thông báo nghiệp vụ tương ứng |

Không dùng một response rỗng chung cho mọi trường hợp. Client cần biết có thể hiển thị “chưa có kết quả”, “không tìm thấy tài nguyên”, “không đủ quyền” hay “trạng thái hiện tại không cho phép thao tác”.

## 13. Kiểm thử phân quyền với nhiều vai trò

Kiểm thử cần xác minh cả đường được phép và đường bị từ chối. Chỉ kiểm tra rằng thành viên xem được danh mục là chưa đủ; cần xác nhận họ không thể tạo, sửa hoặc xóa sách.

Ví dụ Spring MockMvc kiểm tra thành viên không được tạo đầu sách:

~~~java
@WebMvcTest(BookController.class)
class BookControllerSecurityTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    BookCommandService bookCommandService;

    @Test
    @WithMockUser(username = "member-a", roles = "MEMBER")
    void memberCannotCreateBook() throws Exception {
        mvc.perform(post("/books")
                        .with(csrf())
                        .param("isbn", "9780000000001")
                        .param("title", "Lập trình Java")
                        .param("author", "Nguyễn An"))
                .andExpect(status().isForbidden());

        verifyNoInteractions(bookCommandService);
    }
}
~~~

Trong test slice thực tế, cần import cấu hình Security và các bean liên quan phù hợp. Nếu ứng dụng dùng form login thay vì API, hành vi với khách chưa đăng nhập có thể là redirect đến trang login; test cần khớp cấu hình thật.

Một test khác xác nhận thủ thư có thể tạo sách:

~~~java
@Test
@WithMockUser(username = "librarian-1", roles = "LIBRARIAN")
void librarianCanCreateBook() throws Exception {
    given(bookCommandService.create(any())).willReturn(new BookId(42L));

    mvc.perform(post("/books")
                    .with(csrf())
                    .param("isbn", "9780000000001")
                    .param("title", "Lập trình Java")
                    .param("author", "Nguyễn An"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/books/42"));

    verify(bookCommandService).create(any());
}
~~~

## 14. Kiểm thử tài nguyên không tồn tại và quyền theo chủ sở hữu

Kiểm thử không tìm thấy cần xác minh status và hợp đồng lỗi:

~~~java
@Test
void missingBookReturns404() throws Exception {
    given(bookQuery.getDetail(new BookId(99999L)))
            .willThrow(new BookNotFoundException(new BookId(99999L)));

    mvc.perform(get("/api/books/99999"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("BOOK_NOT_FOUND"));
}
~~~

Với phiếu mượn, kiểm thử hai thành viên khác nhau:

1. Thành viên A yêu cầu phiếu của A và nhận dữ liệu.
2. Thành viên A thay ID thành phiếu của B.
3. Query theo loanId + borrowerId không trả bản ghi.
4. API trả 404 theo chính sách che giấu tài nguyên.
5. Không có dữ liệu của B xuất hiện trong response hoặc log công khai.

Ngoài MockMvc, nên có repository integration test xác nhận truy vấn findByIdAndBorrowerId thực sự lọc theo cả hai điều kiện. Một mock test chỉ chứng minh Controller gọi đúng method, chưa chứng minh câu truy vấn database không bị thiếu điều kiện.

## 15. Checklist cho từng endpoint quản lý sách

Trước khi hoàn thành một endpoint, hãy kiểm tra:

- Endpoint có yêu cầu đăng nhập hay được công khai theo đúng chính sách?
- Vai trò nào được phép gọi từng HTTP method?
- Có kiểm tra quyền trên từng tài nguyên, chi nhánh hoặc người sở hữu không?
- Danh tính người dùng được lấy từ principal/security context thay vì request field không?
- Request có thể chứa ID hoặc role giả mạo không?
- Tài nguyên không tồn tại có được biểu diễn bằng 404 nhất quán không?
- Danh sách rỗng có được phân biệt với một tài nguyên đơn lẻ không tồn tại không?
- Trạng thái nghiệp vụ xung đột có được trả 409 hoặc lỗi phù hợp không?
- Response lỗi có tránh lộ stack trace, SQL và dữ liệu nhạy cảm không?
- Có test cho khách, thành viên, thủ thư, quản trị viên và người sở hữu khác nhau không?
- Form POST có CSRF protection khi dùng session cookie không?
- Endpoint xóa có kiểm tra lịch sử mượn và chính sách lưu trữ không?

## 16. Quy trình triển khai phân quyền và xử lý not found

Khi xây dựng một chức năng trong ứng dụng quản lý sách:

1. Liệt kê thao tác và vai trò được phép thực hiện.
2. Xác định tài nguyên công khai, tài nguyên theo người sở hữu và tài nguyên theo chi nhánh.
3. Cấu hình quyền ở HTTP route để chặn request không phù hợp sớm.
4. Bảo vệ use case bằng method security hoặc policy kiểm tra quyền ở server.
5. Lấy user ID và tenant/branch context từ danh tính đã xác thực.
6. Truy vấn tài nguyên theo ID cùng điều kiện owner/scope khi cần.
7. Dùng Optional và exception có nghĩa để biểu diễn dữ liệu không tồn tại.
8. Ánh xạ lỗi sang 400, 401, 403, 404 hoặc 409 theo đúng nguyên nhân.
9. Trả trang lỗi hoặc ProblemDetail phù hợp với HTML/API.
10. Kiểm thử cả vai trò được phép, bị từ chối, tài nguyên thiếu và truy cập chéo người dùng.

## Kết luận

Trong ứng dụng MVC quản lý sách, phân quyền cần được xác định theo thao tác và phạm vi tài nguyên. Spring Security bảo vệ route và danh tính; use case hoặc method security kiểm soát hành động; repository giới hạn truy vấn theo người sở hữu khi cần. Dữ liệu không tồn tại nên được biểu diễn rõ bằng 404, danh sách không có kết quả vẫn có thể trả 200 với danh sách rỗng, còn trạng thái nghiệp vụ xung đột có thể trả 409. Khi kết hợp response lỗi nhất quán với kiểm thử nhiều vai trò và nhiều chủ sở hữu, ứng dụng tránh được truy cập trái phép và giúp người dùng hiểu chính xác kết quả của thao tác.
