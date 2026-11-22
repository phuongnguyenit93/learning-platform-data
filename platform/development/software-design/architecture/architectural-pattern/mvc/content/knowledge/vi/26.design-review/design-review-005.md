# Kiểm tra lỗi, bảo mật và trải nghiệm phản hồi

## 1. Mục tiêu của một lượt review MVC

Một thiết kế Model–View–Controller tốt cần xử lý đúng cả đường đi thành công lẫn những tình huống request thất bại. Người dùng có thể gửi dữ liệu sai, thiếu quyền, thao tác trên tài nguyên đã bị xóa, gửi lại biểu mẫu nhiều lần hoặc gặp lỗi từ database và dịch vụ bên ngoài. Nếu chỉ review luồng thành công, những rủi ro quan trọng nhất thường bị bỏ sót.

Review nên trả lời ba nhóm câu hỏi:

- **Lỗi:** hệ thống phân loại, xử lý và chuyển lỗi thành response như thế nào? Lỗi có bị nuốt, biến thành thành công giả hoặc làm lộ chi tiết nội bộ không?
- **Bảo mật:** danh tính và quyền được xác minh ở đâu? Dữ liệu đầu vào có được giới hạn, dữ liệu đầu ra có được mã hóa đúng ngữ cảnh và tài nguyên có bị truy cập vượt quyền không?
- **Trải nghiệm phản hồi:** người dùng có hiểu điều gì đã xảy ra, cần sửa gì và có thể tiếp tục từ đâu không? Thông báo có kịp thời, nhất quán và phù hợp với HTML hay API không?

Trong MVC web, Controller là ranh giới tiếp nhận request và tạo response. Model/Application layer thực thi quy tắc và quyền nghiệp vụ. View trình bày kết quả. Review cần kiểm tra hợp đồng giữa các tầng để lỗi được xử lý đúng nơi và phản hồi cuối cùng vẫn an toàn.

## 2. Bắt đầu từ luồng request và các ranh giới tin cậy

Trước khi đọc từng class, hãy vẽ luồng request của chức năng đang review:

~~~mermaid
flowchart TD
    U[Browser hoặc API client] --> N[Network / Reverse proxy]
    N --> F[Filter chain và Security]
    F --> D[DispatcherServlet / Routing]
    D --> B[Binding và Validation]
    B --> C[Controller]
    C --> A[Application Service]
    A --> P[Authorization Policy và Domain Rules]
    P --> R[Repository / External Gateway]
    R --> A
    A --> C
    C --> H[Exception Handler / Response Mapping]
    H --> V[View hoặc JSON response]
    V --> U
~~~

Ở mỗi ranh giới, xác định dữ liệu nào được tin cậy và trách nhiệm nào phải được thực hiện:

| Ranh giới | Câu hỏi review |
|---|---|
| Browser → server | Request có thể bị sửa, gửi lặp hoặc gửi trực tiếp ngoài giao diện không? |
| Security filter → Controller | Authentication, CSRF và request-level authorization đã được áp dụng chưa? |
| Binding → Controller | Kiểu dữ liệu, kích thước, định dạng và trường được phép nhận đã được giới hạn chưa? |
| Controller → Service | Có truyền command rõ ràng và danh tính đã xác thực không? |
| Service → Model/Repository | Quyền trên đối tượng và invariant có được kiểm tra trước side effect không? |
| Server → View/client | Response có status, nội dung, encoding và thông báo an toàn không? |

Không xem dữ liệu ẩn trong form, nút bị disable hoặc URL khó đoán là bằng chứng bảo mật. Client có thể tự tạo request. Server phải kiểm tra mọi điều kiện bảo vệ ở mỗi đường gọi.

## 3. Phân loại lỗi trước khi chọn cách phản hồi

Không nên xử lý mọi lỗi bằng một trang 500 hoặc một thông báo “Có lỗi xảy ra”. Phân loại lỗi giúp chọn đúng HTTP status, thông điệp và hành động tiếp theo.

| Nhóm lỗi | Ví dụ | Xử lý thường phù hợp |
|---|---|---|
| Binding / validation | Thiếu tiêu đề, ngày sai định dạng, chuỗi vượt giới hạn | Trả lại form với lỗi gắn đúng trường; API trả 400 hoặc 422 theo hợp đồng |
| Authentication | Chưa đăng nhập hoặc token không hợp lệ | Yêu cầu đăng nhập hoặc trả 401 cho API |
| Authorization | Đã đăng nhập nhưng không có quyền | Trả 403; có thể dùng 404 nếu policy cần che sự tồn tại tài nguyên |
| Not found | ID không tồn tại hoặc không thuộc phạm vi nhìn thấy | Trả 404 và nội dung phù hợp |
| Business conflict | ISBN trùng, trạng thái không cho phép chuyển tiếp | Trả lỗi nghiệp vụ; API thường dùng 409 khi có xung đột trạng thái |
| Rate limit / request quá lớn | Gửi quá nhiều request hoặc payload vượt giới hạn | Trả 429 hoặc 413 tương ứng |
| Dependency failure | Database timeout, dịch vụ đối tác không sẵn sàng | Response an toàn như 503/502 tùy nguyên nhân và gateway; ghi log/tracing |
| Unexpected failure | Null bất ngờ, lỗi lập trình | Trả 500 chung, ghi nhận correlation ID và điều tra nội bộ |

HTTP status cần phản ánh hợp đồng thực tế. Không chọn status chỉ để làm test pass. Với form HTML, lỗi validation thường render lại cùng trang với status 200 hoặc 400 tùy quy ước sản phẩm; điều quan trọng là lỗi được biểu diễn rõ và không tạo side effect. Với API, thống nhất 400 hay 422 cho validation và dùng nhất quán.

## 4. Phân biệt validation đầu vào với invariant nghiệp vụ

Validation đầu vào giúp phát hiện dữ liệu người dùng có thể sửa ngay tại ranh giới giao diện: trường bắt buộc, độ dài, kiểu ngày, định dạng email hoặc giới hạn trang. Invariant nghiệp vụ bảo vệ trạng thái miền bất kể lệnh đến từ web, API, batch hay message consumer.

Ví dụ:

- Form kiểm tra `title` không rỗng để người dùng nhận lỗi gần trường nhập.
- Domain Model bảo đảm một `Book` không thể được tạo với tiêu đề rỗng.
- Application Service kiểm tra ISBN chưa được sử dụng và xử lý xung đột.
- Database có unique constraint để bảo vệ tính duy nhất khi nhiều request chạy đồng thời.

Không đặt toàn bộ validation trong JavaScript hoặc HTML `required`; client-side validation chỉ hỗ trợ trải nghiệm. Server phải kiểm tra lại vì request có thể được gửi trực tiếp.

### Ví dụ Form DTO và Controller

~~~java
public record CreateBookForm(
        @NotBlank(message = "Tiêu đề không được để trống")
        @Size(max = 200, message = "Tiêu đề tối đa 200 ký tự")
        String title,

        @NotBlank(message = "ISBN không được để trống")
        String isbn
) {}

@Controller
@RequestMapping("/books")
public class BookController {
    private final BookService books;

    public BookController(BookService books) {
        this.books = books;
    }

    @PostMapping
    public String create(
            @Valid @ModelAttribute("form") CreateBookForm form,
            BindingResult errors,
            RedirectAttributes redirect) {
        if (errors.hasErrors()) {
            return "books/form";
        }

        try {
            books.create(new CreateBookCommand(form.title(), form.isbn()));
            redirect.addFlashAttribute("message", "Đã tạo sách thành công.");
            return "redirect:/books";
        } catch (DuplicateIsbnException exception) {
            errors.rejectValue(
                    "isbn", "book.isbn.duplicate",
                    "ISBN này đã được sử dụng.");
            return "books/form";
        }
    }
}
~~~

`BindingResult` phải đứng ngay sau tham số được validate để Spring gắn lỗi vào đúng form. `BookService` vẫn phải bảo vệ invariant và không dựa vào Controller là caller duy nhất. Ví dụ lược bỏ import và các lớp miền.

Review cần xác minh thêm rằng lỗi database do unique constraint được chuyển thành lỗi nghiệp vụ có kiểm soát. Nếu chỉ kiểm tra `existsByIsbn()` trước khi insert, hai request đồng thời vẫn có thể cùng thấy ISBN chưa tồn tại.

## 5. Kiểm tra cách xử lý exception

Exception là cơ chế kỹ thuật để báo một tình huống; nó không phải response dành cho người dùng. Controller hoặc exception handler chuyển exception thành hợp đồng HTTP/HTML phù hợp.

Với trang HTML, có thể dùng `@ControllerAdvice` để xử lý lỗi dùng chung:

~~~java
@ControllerAdvice
public class WebExceptionHandler {
    @ExceptionHandler(BookNotFoundException.class)
    public ModelAndView handleNotFound(BookNotFoundException exception) {
        ModelAndView result = new ModelAndView("errors/404");
        result.setStatus(HttpStatus.NOT_FOUND);
        result.addObject(
                "message", "Không tìm thấy sách hoặc bạn không thể xem tài nguyên này.");
        return result;
    }
}
~~~

Thông điệp cố ý không đưa ID, câu truy vấn hoặc chi tiết nội bộ vào trang. Nếu policy cần phân biệt rõ “không tồn tại” và “không có quyền”, response 404 chung có thể giúp tránh tiết lộ sự tồn tại của tài nguyên.

Với REST API, có thể trả `ProblemDetail`:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound() {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Không tìm thấy tài nguyên");
        problem.setDetail("Sách không tồn tại hoặc không thể truy cập.");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

Không dùng cùng một response format cho mọi client nếu hợp đồng sản phẩm khác nhau. HTML cần View, field errors và hướng dẫn tiếp tục; API cần status, error code ổn định và cấu trúc dữ liệu có thể xử lý bằng máy.

### Những dấu hiệu exception handling có vấn đề

- `catch (Exception)` rồi trả “thành công” hoặc response rỗng.
- Bắt exception nhưng không log, không chuyển tiếp và không cung cấp phản hồi.
- Trả `exception.getMessage()` trực tiếp cho người dùng.
- Trả stack trace, SQL, tên bảng, đường dẫn file hoặc hostname nội bộ.
- Một `@ControllerAdvice` bắt mọi exception và biến lỗi lập trình thành 400.
- Dùng exception cho luồng điều khiển thông thường như tìm kiếm không có kết quả.

Chỉ bắt loại lỗi mà tầng hiện tại có thể xử lý có ý nghĩa. Nếu không biết cách khôi phục, hãy để exception đi tới handler phù hợp và ghi nhận đầy đủ ở server.

## 6. Review authentication và authorization

Authentication trả lời “ai đang gọi?”. Authorization trả lời “người đó được làm gì trên tài nguyên nào?”. Hai kiểm tra này độc lập và cần được xem xét riêng.

Ở mỗi endpoint, kiểm tra:

1. Endpoint có yêu cầu đăng nhập không?
2. Quyền hành động có được kiểm tra ở server không?
3. Quyền trên đối tượng cụ thể có được kiểm tra không?
4. Truy vấn có giới hạn theo tenant/owner khi cần không?
5. Side effect chỉ xảy ra sau khi kiểm tra quyền thành công không?

Ví dụ, `BOOK_EDIT` có thể cho phép hành động sửa sách nói chung; nó không tự chứng minh người dùng được sửa mọi sách. Application Service cần kiểm tra quan hệ owner, tenant hoặc policy quản lý trên đối tượng được tải.

~~~java
@PreAuthorize("hasAuthority('BOOK_EDIT')")
public void rename(Actor actor, BookId id, RenameBookCommand command) {
    Book book = books.findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(BookNotFoundException::new);
    bookPolicy.requireCanEdit(actor, book);
    book.rename(command.title());
    books.save(book);
}
~~~

Ví dụ minh họa method-level action permission và object-level policy. `Actor` phải được tạo từ danh tính đã xác thực, không lấy `userId` hoặc `tenantId` làm nguồn đáng tin từ hidden field hay query parameter. Repository scoping giảm nguy cơ tải nhầm tenant; policy vẫn kiểm tra quyền cụ thể.

### Kiểm tra IDOR

Insecure Direct Object Reference xảy ra khi client thay ID trong URL hoặc body và server thao tác với đối tượng mà client không được phép truy cập.

Ví dụ cần review kỹ:

- `GET /orders/{id}` có kiểm tra owner/tenant không?
- `POST /books/{id}/publish` có kiểm tra quyền trên đúng sách đó không?
- Endpoint export có giới hạn dữ liệu theo actor không?
- Service có thể được gọi từ job hoặc API khác mà vẫn thực thi policy không?

Không dựa vào UUID khó đoán, ẩn nút hoặc kiểm tra quyền ở JavaScript. Kiểm tra quyền phải chạy trên server cho mọi thao tác đọc hoặc ghi được bảo vệ.

## 7. Kiểm tra CSRF, XSS và injection

Ba nhóm lỗ hổng thường liên quan trực tiếp đến View và Controller:

| Rủi ro | Điểm cần review |
|---|---|
| CSRF | Request thay đổi trạng thái có được bảo vệ bằng token hoặc cơ chế phù hợp không? Cookie/session có SameSite và cấu hình bảo mật hợp lý không? |
| XSS | Dữ liệu người dùng có được output-encode theo ngữ cảnh HTML, attribute, URL hoặc JavaScript không? Có template dùng raw/unescaped HTML không? |
| SQL injection | Truy vấn có dùng parameter binding/prepared statement không? Có nối chuỗi input vào SQL hoặc tên cột không được allowlist không? |

Với ứng dụng dùng session cookie, giữ CSRF protection cho các thao tác thay đổi trạng thái. Không chuyển POST thành GET chỉ để tránh lỗi CSRF. Nếu một endpoint API dùng cơ chế bearer token không tự động gửi bởi browser, cách bảo vệ có thể khác; phải dựa trên threat model và cấu hình thực tế.

Trong template, ưu tiên cơ chế escape mặc định. Chỉ render HTML không escape khi nội dung đã được làm sạch bằng sanitizer phù hợp và có lý do sản phẩm rõ ràng. Không dùng chuỗi người dùng làm nội dung JavaScript hoặc URL điều hướng mà không kiểm soát.

Với database, dùng tham số truy vấn. Nếu cần chọn cột sắp xếp hoặc hướng sort, ánh xạ input vào allowlist tên cột và enum; parameter placeholder không thay thế được cho identifier SQL.

## 8. Kiểm tra mass assignment và dữ liệu đầu vào quá rộng

Không bind trực tiếp request vào Domain Entity hoặc persistence entity có nhiều trường nhạy cảm. Client có thể gửi thêm field mà giao diện không hiển thị, chẳng hạn `role`, `ownerId`, `tenantId`, `approved`, `price` hoặc `createdBy`.

Dùng Form DTO hoặc Command chỉ chứa các trường được phép thay đổi:

~~~java
public record UpdateBookForm(
        @NotBlank String title,
        @Size(max = 5000) String description
) {}
~~~

Controller chuyển các trường được cho phép thành command; Service tự lấy Actor, owner và tenant từ nguồn tin cậy, rồi kiểm tra policy. Không dùng `BeanUtils.copyProperties(request, entity)` một cách mù quáng nếu request có thể chứa thuộc tính vượt quyền.

Review cũng cần giới hạn kích thước body, số phần tử collection, độ dài query, page size và loại file upload. Giới hạn này bảo vệ cả tính đúng đắn lẫn khả năng chống tiêu hao tài nguyên.

## 9. Đánh giá response và thông báo cho người dùng

Một response tốt phải giúp người dùng biết:

- Thao tác đã thành công hay chưa.
- Trường nào cần sửa và vì sao.
- Dữ liệu có được lưu hay không.
- Có thể thử lại, đăng nhập hoặc liên hệ hỗ trợ bằng cách nào.
- Một thao tác đang chạy hay đã hoàn tất.

Thông điệp nên cụ thể nhưng không tiết lộ thông tin nội bộ. Ví dụ:

| Tình huống | Phản hồi kém | Phản hồi hữu ích |
|---|---|---|
| Thiếu tiêu đề | “Invalid input” | “Nhập tiêu đề sách.” và focus trường tiêu đề |
| ISBN trùng | “Operation failed” | “ISBN này đã được sử dụng. Kiểm tra lại ISBN hoặc mở sách hiện có.” |
| Hết phiên | “403 error” | Yêu cầu đăng nhập lại và giữ lại dữ liệu form nếu an toàn |
| Không có quyền | “Access denied: role BOOK_ADMIN missing” | “Bạn không có quyền thực hiện thao tác này.” |
| Dịch vụ tạm ngừng | “NullPointerException” | “Chưa thể hoàn tất lúc này. Thử lại sau.” kèm mã tham chiếu |

Không đưa tên role nội bộ, ID của người dùng khác, stack trace hoặc chi tiết bảo mật vào thông báo. Tránh xác nhận sự tồn tại của email/tài khoản nếu điều đó tạo điều kiện dò tìm tài khoản.

### Giữ lại dữ liệu form khi có lỗi

Với lỗi validation, người dùng không nên phải nhập lại toàn bộ biểu mẫu. Hãy trả lại View cùng form đã binding và lỗi theo trường. Không giữ lại mật khẩu, mã xác thực hoặc dữ liệu nhạy cảm trong flash/session khi không cần.

Với thao tác thành công, Post/Redirect/Get giúp refresh trang không gửi lại POST:

~~~java
redirectAttributes.addFlashAttribute(
        "message", "Đã cập nhật sách thành công.");
return "redirect:/books/" + id;
~~~

Flash attribute chỉ tồn tại ngắn cho lần điều hướng tiếp theo. Không dùng query string để truyền secret hoặc thông tin cá nhân nhạy cảm.

## 10. Xem xét retry, gửi lặp và side effect

Người dùng có thể nhấn nút hai lần, trình duyệt gửi lại request sau timeout hoặc proxy retry một lời gọi. Review cần hỏi liệu thao tác có thể chạy hai lần hay không.

Với thao tác tạo đơn, thanh toán, gửi lời mời hoặc phát hành tài liệu:

- Nút submit nên thể hiện trạng thái đang xử lý để giảm double click.
- Server vẫn cần bảo vệ idempotency; trạng thái disabled ở client không đủ.
- Có thể dùng idempotency key hoặc unique business key cho thao tác phù hợp.
- Transaction phải bảo vệ cập nhật dữ liệu liên quan.
- Gửi email hoặc publish message cần cân nhắc outbox/after-commit để tránh side effect xảy ra khi transaction rollback.
- Không tự retry một thao tác không idempotent khi chưa biết lần gọi trước có thành công hay chưa.

Thông báo “thử lại” chỉ nên xuất hiện khi retry là an toàn hoặc người dùng được hướng dẫn cách kiểm tra trạng thái trước khi gửi lại.

## 11. Phản hồi cho thao tác bất đồng bộ

Với tác vụ export, import hoặc xử lý tệp lớn, request HTTP có thể chỉ tạo job rồi trả về mã theo dõi. UI cần các trạng thái rõ ràng như queued, running, succeeded và failed.

Review cần kiểm tra:

- Job ID có gắn với owner/tenant và được kiểm tra quyền khi đọc trạng thái không?
- Người dùng có thấy tiến độ hoặc thời điểm cập nhật gần nhất không?
- Lỗi có thông điệp an toàn và hành động tiếp theo không?
- Job có thể bị gửi trùng hoặc chạy lại không?
- Người dùng có thể hủy tác vụ không; hủy có thực sự được thực thi ở worker không?
- Tác vụ có giữ `HttpServletRequest`, session hoặc mutable singleton state sau khi request kết thúc không?

Không dùng trạng thái loading vô hạn. Nếu không thể xác định tiến độ, hiển thị trạng thái đang xử lý và cung cấp cơ chế làm mới hoặc thông báo khi hoàn tất.

## 12. Logging, correlation ID và thông tin nhạy cảm

Response dành cho người dùng cần ngắn gọn; log nội bộ cần đủ ngữ cảnh để điều tra. Có thể liên kết hai phía bằng request ID hoặc trace ID.

Log nên ghi:

- Correlation/trace ID.
- Route hoặc operation đã chuẩn hóa.
- Actor ID ở dạng phù hợp với chính sách riêng tư nếu cần điều tra.
- Loại lỗi, status và thành phần phát sinh.
- Thời gian xử lý và dependency liên quan.
- Kết quả xử lý hoặc mã lỗi ổn định.

Không ghi mật khẩu, token, cookie, session ID, API key, thông tin thẻ hoặc toàn bộ request body theo mặc định. Cần che/redact dữ liệu cá nhân và giới hạn quyền truy cập log.

Khi đưa dữ liệu không tin cậy vào log, loại bỏ hoặc encode ký tự xuống dòng và ký tự điều khiển để tránh log injection. Không đưa nội dung người dùng tự do vào metric label vì cardinality có thể tăng rất lớn.

## 13. Đánh giá lỗi theo trải nghiệm HTML và API

HTML và API có cùng quy tắc nghiệp vụ nhưng hợp đồng phản hồi khác nhau:

| Tình huống | HTML MVC | REST API |
|---|---|---|
| Validation lỗi | Render lại form, giữ giá trị an toàn và field errors | 400/422 với danh sách lỗi theo field |
| Chưa đăng nhập | Redirect đến login hoặc trang phù hợp | 401 với challenge/response theo cơ chế xác thực |
| Thiếu quyền | Trang 403 hoặc 404 theo policy | 403 hoặc 404 theo policy |
| Không tìm thấy | View 404 | JSON error 404 |
| Xung đột nghiệp vụ | Render form/thông báo conflict | 409 với error code ổn định |
| Lỗi không dự kiến | Trang 500 chung có request reference | 500 với Problem Details an toàn |

Không redirect API client sang trang đăng nhập HTML nếu API contract yêu cầu 401. Không trả JSON stack trace cho browser chỉ vì lỗi xảy ra ở server. Cùng một exception có thể được ánh xạ khác nhau theo loại client, nhưng nguyên nhân và chính sách bảo mật phải nhất quán.

## 14. Xây dựng ma trận review theo kịch bản

Thay vì chỉ đọc từng class, hãy liệt kê kịch bản thành công, lỗi và tấn công có thể xảy ra:

| Kịch bản | Hành vi mong đợi | Bằng chứng cần tìm |
|---|---|---|
| Request hợp lệ | Use case chạy một lần và trả response đúng | Controller, Service test, integration test |
| Thiếu trường bắt buộc | Không có side effect; lỗi gắn đúng trường | Form validation test và verify Service không gọi |
| Kiểu dữ liệu sai | Binding error rõ ràng, response đúng hợp đồng | MockMvc test |
| Chưa xác thực | Request bị chặn theo policy | Security integration test |
| Thiếu action permission | Bị từ chối trước side effect | Method/request authorization test |
| ID thuộc user/tenant khác | Không đọc hoặc sửa được tài nguyên | Object policy và tenant-scoped repository test |
| CSRF token thiếu/sai | POST bị từ chối khi CSRF bật | Security MockMvc test |
| XSS payload | Nội dung được encode, không thực thi script | Template test và security review |
| ISBN trùng | Conflict được ánh xạ thành field error hoặc 409 | Service/repository test |
| Database timeout | Response an toàn, lỗi được ghi nhận | Exception mapping và observability test |
| Double submit | Không tạo hai kết quả ngoài ý muốn | Idempotency/concurrency test |
| Tác vụ nền thất bại | Job chuyển failed, người dùng biết cách tiếp tục | Job status test và ownership check |

Review nên liên kết mỗi rủi ro với test, code path hoặc lý do chấp nhận rủi ro. Nếu không tìm được bằng chứng, ghi thành câu hỏi cần giải quyết thay vì giả định đã được bảo vệ.

## 15. Phân loại phát hiện theo mức độ nghiêm trọng

Không phải mọi vấn đề đều cần chặn phát hành. Hãy đánh giá theo tác động, khả năng khai thác, phạm vi người dùng và khả năng khôi phục.

| Mức | Ví dụ | Hành động review |
|---|---|---|
| Critical | Rò dữ liệu giữa tenant, bỏ qua authorization cho thao tác nhạy cảm, lộ credential | Chặn merge/release cho đến khi sửa |
| High | IDOR, CSRF trên thao tác quan trọng, mass assignment thay đổi role/owner | Yêu cầu sửa trước khi phát hành |
| Medium | Lỗi nghiệp vụ trả sai status, thiếu thông báo có thể khiến người dùng gửi lặp | Sửa trước release hoặc có kế hoạch giảm thiểu rõ |
| Low | Thông điệp chưa rõ, lỗi accessibility nhỏ, log thiếu trường không thiết yếu | Ghi nhận và ưu tiên theo kế hoạch |

Mức độ phải dựa trên bối cảnh. Một lỗi thông báo nhỏ có thể trở thành vấn đề nghiêm trọng nếu khiến người dùng lặp lại giao dịch tài chính; một 404 khác biệt có thể tiết lộ tài nguyên nhạy cảm trong hệ thống đa tenant.

## 16. Checklist review trước khi merge

### Lỗi và tính nhất quán

- [ ] Binding error và validation error được phân biệt với lỗi nghiệp vụ.
- [ ] Invariant được bảo vệ trong Model/Application layer, không chỉ ở View.
- [ ] Exception được ánh xạ thành status và response đúng hợp đồng.
- [ ] Không nuốt exception hoặc trả thành công giả.
- [ ] Lỗi bất ngờ không làm lộ stack trace, SQL hoặc thông tin nội bộ.
- [ ] Side effect không xảy ra khi validation hoặc authorization thất bại.

### Bảo mật

- [ ] Authentication và action authorization được kiểm tra ở server.
- [ ] Object-level authorization và tenant scoping được thực thi.
- [ ] Form DTO chỉ cho phép các field cần thiết; không mass assignment.
- [ ] CSRF được bảo vệ theo mô hình xác thực.
- [ ] Output encoding và parameterized query được sử dụng.
- [ ] Payload, page size, upload và request rate có giới hạn phù hợp.
- [ ] Log và response không chứa secret hoặc dữ liệu nhạy cảm.

### Trải nghiệm phản hồi

- [ ] Thông báo chỉ rõ điều gì đã xảy ra và cách tiếp tục.
- [ ] Validation error được gắn đúng trường và giữ lại dữ liệu an toàn.
- [ ] Thành công dùng PRG khi phù hợp.
- [ ] Trạng thái loading, empty, success và failure được thiết kế.
- [ ] Retry an toàn; thao tác không idempotent có cơ chế chống gửi lặp.
- [ ] HTML và API nhận đúng loại response.
- [ ] Thông báo lỗi có thể đọc bằng bàn phím và công nghệ hỗ trợ.

### Bằng chứng kiểm thử

- [ ] Có test cho luồng hợp lệ và lỗi đầu vào.
- [ ] Có test thiếu authentication/permission và truy cập chéo đối tượng.
- [ ] Có test CSRF nếu session cookie được sử dụng.
- [ ] Có test exception mapping và response format.
- [ ] Có test concurrency/idempotency cho thao tác có nguy cơ chạy lặp.

## 17. Ví dụ nhận xét review có thể hành động

Nhận xét tốt chỉ rõ vị trí, rủi ro và điều kiện để chấp nhận:

**Phát hiện:** Endpoint `POST /books/{id}/publish` chỉ kiểm tra `BOOK_PUBLISH`, sau đó tải sách bằng `findById(id)`. Không thấy kiểm tra tenant hoặc quyền trên đối tượng.

**Tác động:** Người có quyền publish trên một số sách có thể thử ID của sách thuộc tenant khác. Nếu policy không được kiểm tra trong use case, endpoint có nguy cơ IDOR.

**Yêu cầu:** Tải sách theo ID và tenant của Actor đã xác thực, thực thi object policy trước khi chuyển trạng thái, và thêm test với hai tenant để chứng minh request chéo bị từ chối mà không phát sinh side effect.

**Phát hiện:** Khi ISBN trùng, Controller trả trang lỗi chung 500.

**Tác động:** Người dùng không biết trường nào cần sửa; lỗi nghiệp vụ bình thường bị ghi nhận như lỗi hệ thống.

**Yêu cầu:** Ánh xạ `DuplicateIsbnException` thành field error hoặc API 409 theo hợp đồng, giữ lại dữ liệu form an toàn và kiểm thử cả trường hợp hai request tạo đồng thời.

## 18. Những sai lầm thường gặp khi review

- **Chỉ kiểm tra luồng thành công:** bỏ qua các nhánh lỗi và điều kiện tấn công.
- **Coi client-side validation là bảo mật:** request trực tiếp vẫn có thể gửi dữ liệu tùy ý.
- **Chỉ kiểm tra role mà không kiểm tra đối tượng:** có thể dẫn đến IDOR hoặc truy cập chéo tenant.
- **Dùng catch-all để trả response chung:** che lỗi lập trình và làm sai status.
- **Hiển thị exception message cho người dùng:** có thể lộ SQL, đường dẫn hoặc chi tiết nội bộ.
- **Disable nút submit và cho rằng không có double submit:** client có thể gửi nhiều request.
- **Dùng 200 cho mọi lỗi:** client, monitoring và người dùng không phân biệt được kết quả.
- **Trả 403 trong mọi trường hợp:** đôi khi làm lộ sự tồn tại của tài nguyên mà policy cần che.
- **Ghi toàn bộ request vào log:** có thể làm lộ token, mật khẩu và dữ liệu cá nhân.
- **Đánh giá UX chỉ bằng câu chữ:** bỏ qua focus, accessibility, trạng thái loading và khả năng khôi phục.

## 19. Kết luận

Review lỗi, bảo mật và trải nghiệm phản hồi cần bắt đầu từ toàn bộ vòng đời request, từ ranh giới tin cậy đến response cuối cùng. Phân loại lỗi đúng giúp chọn exception handler, status và thông điệp phù hợp. Authentication, action permission, object-level authorization, CSRF, output encoding, input constraints và tenant scoping bảo vệ tài nguyên ở phía server. View cần cung cấp phản hồi rõ ràng, giữ dữ liệu an toàn, hỗ trợ retry có kiểm soát và không tiết lộ chi tiết nội bộ.

Một lượt review tốt luôn gắn phát hiện với kịch bản cụ thể, tác động, vị trí chịu trách nhiệm và bằng chứng kiểm thử. Khi các đường lỗi và ranh giới bảo mật được kiểm tra cùng luồng thành công, ứng dụng MVC vừa đáng tin cậy hơn vừa giúp người dùng hiểu và khôi phục sau sự cố.
