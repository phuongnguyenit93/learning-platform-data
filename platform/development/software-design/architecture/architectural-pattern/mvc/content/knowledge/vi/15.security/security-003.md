# Phân quyền theo hành động và theo đối tượng nghiệp vụ

## 1. Vì sao MVC cần phân quyền ở nhiều mức?

Trong ứng dụng Model–View–Controller, Controller tiếp nhận request và điều phối nghiệp vụ; Model biểu diễn trạng thái và quy tắc miền; View trình bày dữ liệu cùng những thao tác người dùng có thể thực hiện. Tuy nhiên, việc một người dùng đã đăng nhập không có nghĩa họ được phép thực hiện mọi hành động hoặc truy cập mọi đối tượng.

Ví dụ trong hệ thống quản lý sách, một nhân viên có thể được phép xem danh sách sách, nhưng chỉ được sửa những cuốn sách thuộc chi nhánh của mình. Một quản lý có thể sửa sách trong toàn chi nhánh; quản trị viên có thể lưu trữ hoặc xóa sách. Quyền còn có thể phụ thuộc trạng thái sách: chỉ sách ở trạng thái nháp mới được chỉnh sửa.

Vì vậy, cần kiểm tra ít nhất hai câu hỏi:

- **Người dùng có được phép thực hiện hành động này không?** Ví dụ quyền `BOOK_EDIT`, `BOOK_DELETE` hoặc `BOOK_PUBLISH`.
- **Người dùng có được phép thực hiện hành động đó trên đối tượng cụ thể này không?** Ví dụ chỉ chủ sở hữu hoặc nhân viên cùng tenant/chi nhánh mới được sửa cuốn sách.

Trong một số hệ thống, quyết định còn phụ thuộc thuộc tính và ngữ cảnh như trạng thái tài nguyên, đơn vị tổ chức, thời gian, mức phân loại dữ liệu hoặc quan hệ giữa người dùng và đối tượng. Phân quyền cần được thực thi ở phía server tại ranh giới nghiệp vụ và dữ liệu; giao diện chỉ phản ánh các hành động được phép để hỗ trợ trải nghiệm.

## 2. Phân biệt xác thực và phân quyền

**Xác thực (authentication)** trả lời câu hỏi “người gửi request là ai?”. Ứng dụng xác minh danh tính qua session, token, chứng thư hoặc cơ chế phù hợp.

**Phân quyền (authorization)** trả lời câu hỏi “danh tính này được phép làm gì, trên tài nguyên nào, trong điều kiện nào?”. Xác thực thành công chỉ cung cấp danh tính và thông tin quyền để hệ thống ra quyết định; nó không tự cấp quyền truy cập mọi tài nguyên.

Ví dụ:

- Người chưa đăng nhập gửi request đến trang quản lý: ứng dụng yêu cầu xác thực.
- Người dùng đã đăng nhập nhưng không có quyền `BOOK_EDIT`: ứng dụng từ chối hành động sửa sách.
- Người dùng có quyền sửa sách nói chung nhưng đang truy cập sách thuộc tenant khác: ứng dụng từ chối truy cập đối tượng đó.
- Người dùng có quyền sửa đúng cuốn sách nhưng sách đã được xuất bản và quy tắc miền không cho sửa nội dung: đây có thể là xung đột trạng thái nghiệp vụ, không phải thiếu quyền danh tính.

Không nên gộp mọi trường hợp từ chối thành một lỗi duy nhất. Xác thực, phân quyền đối tượng và quy tắc trạng thái có ngữ nghĩa khác nhau, nên cần phản hồi và log phù hợp.

## 3. Phân quyền theo hành động (Action-Level Authorization)

Phân quyền theo hành động xác định một người dùng hoặc nhóm người dùng được phép thực hiện loại thao tác nào. Một số quyền thường gặp:

| Permission | Hành động |
|---|---|
| `BOOK_VIEW` | Xem thông tin sách |
| `BOOK_CREATE` | Tạo sách mới |
| `BOOK_EDIT` | Chỉnh sửa thông tin sách |
| `BOOK_DELETE` | Xóa hoặc yêu cầu xóa sách |
| `BOOK_PUBLISH` | Xuất bản sách |
| `BOOK_EXPORT` | Xuất dữ liệu sách |

Quyền nên mô tả hành động nghiệp vụ rõ ràng. Một quyền quá rộng như `ADMIN_ACCESS` có thể tiện lúc đầu nhưng khó áp dụng nguyên tắc quyền tối thiểu (least privilege). Một quyền quá vụn cũng làm hệ thống khó quản lý. Hãy chọn mức hạt phù hợp với use case và chính sách tổ chức.

### Role và permission

Role-Based Access Control (RBAC) gom các permission thành vai trò. Ví dụ:

| Role | Permission có thể được cấp |
|---|---|
| `LIBRARIAN` | `BOOK_VIEW`, `BOOK_CREATE`, `BOOK_EDIT` |
| `BRANCH_MANAGER` | Các quyền trên và `BOOK_DELETE`, `BOOK_EXPORT` trong phạm vi chi nhánh |
| `PUBLISHER` | `BOOK_VIEW`, `BOOK_PUBLISH` |
| `AUDITOR` | `BOOK_VIEW`, `BOOK_EXPORT` ở chế độ chỉ đọc |

Role giúp quản trị quyền theo công việc. Trong mã ứng dụng, kiểm tra permission cụ thể thường linh hoạt hơn kiểm tra tên role ở mọi nơi. Khi một người dùng có nhiều role, quyền hiệu lực thường là tập hợp permission được cấp theo chính sách.

Không mặc định rằng tên role là bằng chứng cho quyền trên mọi tài nguyên. `BRANCH_MANAGER` có thể có quyền sửa sách trong chi nhánh của mình nhưng không có quyền sửa sách của chi nhánh khác. Phạm vi đối tượng cần được kiểm tra riêng.

### Kiểm tra permission trong Spring Security

Spring Security có thể kiểm tra authority ở tầng request hoặc method. Ví dụ cấu hình request-level:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(HttpMethod.POST, "/books")
                        .hasAuthority("BOOK_CREATE")
                    .requestMatchers(HttpMethod.PUT, "/books/**")
                        .hasAuthority("BOOK_EDIT")
                    .requestMatchers("/admin/**")
                        .hasAuthority("SYSTEM_ADMIN")
                    .anyRequest().authenticated())
            .build();
}
~~~

Đây là ví dụ rút gọn; ứng dụng cần cấu hình cơ chế xác thực và CSRF phù hợp. `hasAuthority` so khớp chính xác tên authority. `hasRole("ADMIN")` trong Spring Security thường kiểm tra authority có tiền tố `ROLE_`, ví dụ `ROLE_ADMIN`.

Request-level authorization là lớp bảo vệ sớm cho nhóm endpoint. Nó chưa trả lời người dùng có được sửa cuốn sách có ID cụ thể hay không. Một endpoint `PUT /books/{id}` có thể được phép ở mức hành động nhưng vẫn phải kiểm tra quyền đối với bản ghi được yêu cầu.

## 4. Phân quyền theo đối tượng nghiệp vụ (Object-Level Authorization)

Phân quyền theo đối tượng xác định người dùng có được truy cập hoặc thực hiện hành động trên một tài nguyên cụ thể hay không. Một đối tượng có thể là sách, đơn hàng, hồ sơ, hóa đơn, tài liệu hoặc bản ghi thuộc một tenant.

Quyết định thường dựa trên:

- **Chủ sở hữu:** người tạo hoặc chủ sở hữu có quyền đọc/sửa đối tượng.
- **Phạm vi tổ chức:** người dùng chỉ thao tác trên dữ liệu thuộc tenant, chi nhánh hoặc phòng ban của mình.
- **Quan hệ:** người được giao xử lý hồ sơ, thành viên của dự án hoặc người tham gia giao dịch có quyền phù hợp.
- **Thuộc tính:** mức phân loại, trạng thái, thời gian hiệu lực hoặc loại dữ liệu.
- **Hành động:** cùng một người có thể được xem nhưng không được sửa, xóa hoặc xuất đối tượng.

Ví dụ, nhân viên A có `BOOK_EDIT` nhưng chỉ được sửa sách thuộc chi nhánh A. Nhân viên B cũng có cùng permission nhưng không thể sửa sách thuộc chi nhánh A. Quyền hành động giống nhau, quyết định trên từng đối tượng khác nhau.

### Ma trận quyết định

| Người dùng | Hành động | Đối tượng | Kết quả ví dụ |
|---|---|---|---|
| Nhân viên chi nhánh A | Xem | Sách chi nhánh A | Cho phép |
| Nhân viên chi nhánh A | Sửa | Sách chi nhánh A do người khác tạo | Theo policy chi nhánh; có thể cho phép |
| Nhân viên chi nhánh A | Sửa | Sách chi nhánh B | Từ chối |
| Chủ sở hữu sách | Sửa | Sách của mình đang ở trạng thái nháp | Cho phép nếu có permission hành động |
| Chủ sở hữu sách | Sửa | Sách đã xuất bản và bị khóa chỉnh sửa | Từ chối theo quy tắc trạng thái |
| Người chỉ có quyền xem | Xóa | Bất kỳ sách nào | Từ chối |

Ma trận là ví dụ chính sách. Quy tắc cụ thể phải xuất phát từ yêu cầu nghiệp vụ và được áp dụng thống nhất trong Service, query và API.

## 5. RBAC, ABAC và phân quyền theo quan hệ

Ba cách tiếp cận thường được kết hợp:

**RBAC (Role-Based Access Control):** quyền được gom theo role. Ví dụ `LIBRARIAN` có `BOOK_VIEW` và `BOOK_EDIT`. RBAC dễ quản lý khi quyền gắn với chức năng công việc tương đối ổn định.

**ABAC (Attribute-Based Access Control):** quyết định dựa trên thuộc tính của subject, resource, action và môi trường. Ví dụ cho phép sửa nếu `user.branchId == book.branchId`, `book.status == DRAFT` và request nằm trong giờ làm việc được quy định. ABAC phù hợp khi chính sách phụ thuộc nhiều thuộc tính.

**Relationship-Based Access Control (ReBAC):** quyết định dựa trên quan hệ giữa người dùng và tài nguyên. Ví dụ người dùng là chủ sở hữu, thành viên dự án, người được giao xử lý hoặc người quản lý của chủ sở hữu.

Trong hệ thống thực tế, có thể dùng RBAC để xác định quyền hành động cơ bản, ABAC để giới hạn theo tenant/trạng thái và quan hệ sở hữu để quyết định quyền trên từng bản ghi. Không nhất thiết phải triển khai một policy engine phức tạp nếu vài điều kiện rõ ràng trong Service đã đáp ứng yêu cầu.

## 6. Thực thi phân quyền ở đúng tầng MVC

Không nên chỉ kiểm tra quyền ở một nơi duy nhất nếu có nhiều đường truy cập vào cùng use case. Các lớp thường phối hợp như sau:

| Tầng | Trách nhiệm phân quyền |
|---|---|
| Security filter / request mapping | Chặn sớm nhóm endpoint hoặc HTTP method cần authority |
| Controller | Điều phối request; có thể chuẩn bị thông tin hành động được phép để View hiển thị |
| Application Service | Bảo vệ use case và kiểm tra quyền thực hiện hành động |
| Object policy / Domain policy | Kiểm tra quan hệ người dùng với đối tượng và điều kiện nghiệp vụ liên quan |
| Repository/query | Giới hạn dữ liệu theo tenant, chủ sở hữu hoặc phạm vi được phép |
| View | Ẩn/hiện nút hoặc liên kết để giao diện dễ hiểu; không phải ranh giới bảo mật |

Điểm thực thi quan trọng nhất là nơi mọi đường gọi use case phải đi qua. Nếu một Service có thể được gọi từ Controller, API khác hoặc tác vụ nền, phân quyền chỉ nằm trong một Controller là không đủ. Cần bảo vệ ở Service hoặc một lớp application policy được mọi đường gọi sử dụng.

### Ví dụ policy cho sách

Giả sử mỗi sách có `ownerId` và `tenantId`. Người dùng cần authority `BOOK_EDIT`; ngoài ra họ phải là chủ sở hữu hoặc có quyền chỉnh sửa mọi sách trong tenant.

~~~java
import java.util.Set;
import java.util.UUID;

public record Actor(
        UUID userId,
        UUID tenantId,
        Set<String> authorities
) {
    public boolean hasAuthority(String authority) {
        return authorities.contains(authority);
    }
}

public class BookAccessDeniedException extends RuntimeException {
    public BookAccessDeniedException() {
        super("Không được phép thực hiện hành động trên sách này");
    }
}

public class BookAuthorizationPolicy {
    public void requireCanEdit(Actor actor, Book book) {
        boolean sameTenant = actor.tenantId().equals(book.tenantId());
        boolean owner = actor.userId().equals(book.ownerId());
        boolean manager = actor.hasAuthority("BOOK_EDIT_ANY");

        if (!sameTenant || (!owner && !manager)) {
            throw new BookAccessDeniedException();
        }
    }

    public void requireCanManage(Actor actor, Book book) {
        boolean sameTenant = actor.tenantId().equals(book.tenantId());
        boolean owner = actor.userId().equals(book.ownerId());
        boolean manager = actor.hasAuthority("BOOK_MANAGE_ANY");

        if (!sameTenant || (!owner && !manager)) {
            throw new BookAccessDeniedException();
        }
    }
}
~~~

Ví dụ giả định `Book` có `tenantId()` và `ownerId()`, đồng thời policy được đăng ký thành bean để tiêm vào Service. `BookAccessDeniedException` là ngoại lệ của ứng dụng; lớp web ánh xạ nó thành `403 Forbidden` mà không buộc Domain Model phụ thuộc Spring Security. Policy chỉ quyết định quyền trên đối tượng; quyền hành động `BOOK_EDIT` được kiểm tra riêng. Nếu người dùng có quyền hành động nhưng không thuộc tenant hoặc không có quan hệ phù hợp với sách, policy từ chối.

### Bảo vệ use case trong Service

~~~java
@Service
public class BookApplicationService {
    private final BookRepository books;
    private final CurrentActor currentActor;
    private final BookAuthorizationPolicy authorization;

    public BookApplicationService(
            BookRepository books,
            CurrentActor currentActor,
            BookAuthorizationPolicy authorization) {
        this.books = books;
        this.currentActor = currentActor;
        this.authorization = authorization;
    }

    @PreAuthorize("hasAuthority('BOOK_EDIT')")
    @Transactional
    public void rename(UUID id, String newTitle) {
        Actor actor = currentActor.require();
        Book book = books.findByIdAndTenantId(id, actor.tenantId())
                .orElseThrow(BookNotFoundException::new);

        authorization.requireCanEdit(actor, book);
        book.rename(newTitle);
        books.save(book);
    }
}
~~~

Ví dụ giả định `CurrentActor` lấy danh tính từ security context đã xác thực, không lấy `userId` hoặc `tenantId` từ request body. `findByIdAndTenantId` giới hạn truy vấn theo tenant hiện tại; nếu bản ghi thuộc tenant khác, ứng dụng có thể trả `404` để không tiết lộ sự tồn tại của nó. `@PreAuthorize` cần được bật bằng `@EnableMethodSecurity` và lời gọi phải đi qua Spring proxy; self-invocation trong cùng bean có thể bỏ qua method interceptor.

Phương thức `rename` thực hiện kiểm tra object policy sau khi tải đối tượng trong transaction. Hành vi `book.rename` vẫn phải bảo vệ invariant của miền, chẳng hạn không cho sửa sách đã bị khóa. Nếu người dùng được phép truy cập sách nhưng hành động không hợp lệ do trạng thái, đó là lỗi nghiệp vụ và nên được biểu diễn riêng với lỗi thiếu quyền.

## 7. Giới hạn truy vấn dữ liệu theo quyền

Phân quyền không chỉ áp dụng cho thao tác cập nhật. Các truy vấn đọc cũng có thể làm lộ dữ liệu nếu lấy mọi bản ghi rồi chỉ ẩn một phần trên View.

Ví dụ, thay vì:

~~~java
List<Book> books = repository.findAll();
return books.stream()
        .filter(book -> policy.canView(actor, book))
        .toList();
~~~

có thể giới hạn ngay ở truy vấn:

~~~java
List<Book> books = repository.findVisibleTo(
        actor.tenantId(),
        actor.userId(),
        actor.authorities());
~~~

Đây là ví dụ hợp đồng repository; cách biểu diễn policy trong SQL/JPQL phụ thuộc mô hình dữ liệu. Lọc ở tầng truy vấn giúp tránh tải và vô tình trả dữ liệu ngoài phạm vi. Với chính sách phức tạp, cần bảo đảm điều kiện truy vấn phản ánh đúng policy trung tâm, tránh hai bản triển khai bị lệch nhau.

Với thao tác theo lô như export, delete nhiều bản ghi hoặc cập nhật hàng loạt, phải áp dụng cùng giới hạn đối tượng cho toàn bộ tập dữ liệu. Không tin danh sách ID do client gửi lên; mỗi ID phải được kiểm tra quyền và phạm vi tenant.

## 8. Ngăn IDOR và truy cập trực tiếp bằng ID

Insecure Direct Object Reference (IDOR) xảy ra khi ứng dụng dùng một ID do client cung cấp để truy cập đối tượng mà không kiểm tra người dùng có quyền trên đối tượng đó hay không.

Ví dụ:

~~~http
GET /orders/10025
~~~

Nếu người dùng thay ID thành `10026` và server trả đơn hàng của người khác chỉ vì ID tồn tại, endpoint có lỗ hổng IDOR. UUID khó đoán hơn số tăng tuần tự nhưng không phải biện pháp phân quyền. Client có thể nhận ID từ log, liên kết, dữ liệu chia sẻ hoặc một nguồn khác.

Để ngăn IDOR:

- Xác thực người dùng ở mọi request cần bảo vệ.
- Truy vấn tài nguyên trong phạm vi tenant/owner được phép khi có thể.
- Kiểm tra quyền trên đúng đối tượng trước khi đọc hoặc thay đổi dữ liệu.
- Áp dụng kiểm tra cho cả endpoint đọc, cập nhật, xóa, download, export và API phụ.
- Không dựa vào việc ẩn ID, nút bấm hoặc URL trong View.
- Kiểm thử bằng cách thay ID của đối tượng sang ID thuộc người dùng/tenant khác.

Chính sách có thể trả `404` cho tài nguyên ngoài phạm vi để tránh tiết lộ sự tồn tại, hoặc `403` khi hệ thống chủ đích công khai tài nguyên tồn tại nhưng người gọi không có quyền. Chọn một quy ước nhất quán theo yêu cầu bảo mật.

## 9. Phân quyền theo trạng thái nghiệp vụ

Quyền hành động và trạng thái đối tượng cần được xét riêng. Ví dụ người dùng có quyền `BOOK_PUBLISH`, nhưng một cuốn sách chỉ được xuất bản khi đã qua kiểm duyệt và có đủ metadata.

Policy có thể xác định người dùng có quyền xuất bản cuốn sách thuộc phạm vi của họ; Model hoặc Service tiếp tục kiểm tra trạng thái và invariant trước khi chuyển trạng thái.

~~~java
@PreAuthorize("hasAuthority('BOOK_PUBLISH')")
@Transactional
public void publish(UUID id) {
    Actor actor = currentActor.require();
    Book book = books.findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(BookNotFoundException::new);

    authorization.requireCanManage(actor, book);
    book.publish();
    books.save(book);
}
~~~

`book.publish()` cần tự kiểm tra điều kiện miền như sách đang ở trạng thái `REVIEWED`. Nếu điều kiện không đạt, nó phát sinh lỗi nghiệp vụ phù hợp. Người dùng thiếu authority hoặc không có quan hệ với đối tượng bị từ chối bởi authorization policy. Phân biệt này giúp giao diện đưa ra thông báo đúng và log không nhầm lỗi quyền với lỗi trạng thái.

## 10. Hiển thị hành động được phép trên View

View có thể nhận một tập hành động được phép để quyết định hiển thị nút:

~~~java
public record BookDetailView(
        UUID id,
        String title,
        String statusLabel,
        boolean canEdit,
        boolean canDelete,
        boolean canPublish
) {}
~~~

Controller hoặc mapper tính các cờ này từ cùng policy dùng ở tầng application. Template có thể hiển thị:

~~~html
<a th:if="${book.canEdit}"
   th:href="@{/books/{id}/edit(id=${book.id})}">Chỉnh sửa</a>

<form th:if="${book.canDelete}"
      th:action="@{/books/{id}(id=${book.id})}"
      method="post">
  <input type="hidden" name="_method" value="delete" />
  <button type="submit">Xóa sách</button>
</form>
~~~

Đây chỉ là cách cải thiện trải nghiệm. Người dùng có thể tự tạo request hoặc sửa HTML trong trình duyệt. Endpoint xử lý `PUT`, `POST` hoặc `DELETE` vẫn phải kiểm tra quyền hành động và quyền trên đối tượng. Không dùng `canEdit` từ form gửi lại như bằng chứng phân quyền.

## 11. Phân biệt 401, 403 và 404

Phản hồi HTTP nên phản ánh chính sách truy cập:

| Status | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| `401 Unauthorized` | Request chưa có danh tính được xác thực hợp lệ | Session hết hạn hoặc bearer token thiếu/sai |
| `403 Forbidden` | Đã xác thực nhưng không được phép thực hiện hành động | Người dùng thiếu `BOOK_DELETE` |
| `404 Not Found` | Tài nguyên không tồn tại hoặc được cố ý che giấu vì người gọi không có quyền biết | ID không thuộc tenant hiện tại |

Không phải mọi ứng dụng đều phải trả `404` cho tài nguyên ngoài phạm vi. Nhưng nếu dùng cách này để tránh dò tìm tài nguyên, cần áp dụng nhất quán trên API, trang HTML, export và các endpoint phụ để không tạo kênh rò rỉ qua khác biệt response.

## 12. Những điểm bảo mật cần chú ý

**Deny by default:** nếu không có quy tắc cho phép rõ ràng, từ chối truy cập. Tránh cấu hình endpoint mới thành public chỉ vì chưa thêm matcher.

**Least privilege:** cấp permission tối thiểu cần cho công việc. Role quản trị không nên được gán mặc định cho tài khoản ứng dụng hoặc tác vụ nền.

**Không tin dữ liệu client:** `ownerId`, `tenantId`, role, permission, trạng thái và các cờ `isAdmin` gửi từ form không phải nguồn có thẩm quyền. Lấy danh tính/quyền từ security context và dữ liệu server.

**Kiểm tra mọi đường truy cập:** cùng một use case có thể được gọi từ HTML Controller, REST Controller, scheduled job hoặc message consumer. Bảo vệ ở application service/policy dùng chung, đồng thời xác định rõ danh tính hệ thống cho tác vụ nền.

**Tránh TOCTOU:** nếu kiểm tra quyền rồi cập nhật đối tượng trong hai transaction hoặc hai thời điểm tách biệt, trạng thái/quan hệ có thể thay đổi giữa lúc kiểm tra và lúc ghi. Với thao tác nhạy cảm, tải đối tượng và kiểm tra policy trong cùng transaction; dùng optimistic/pessimistic locking hoặc điều kiện cập nhật phù hợp khi cần.

**Giới hạn cache:** response hoặc dữ liệu đã lọc theo người dùng/tenant không được cache bằng khóa chỉ gồm URL nếu có thể trả nhầm dữ liệu giữa người dùng. Cache key và invalidation phải tính đến phạm vi bảo mật.

**CSRF vẫn cần thiết:** authorization xác minh người dùng có quyền, còn CSRF protection ngăn một site khác lợi dụng browser đã đăng nhập để gửi request thay người dùng. Hai cơ chế giải quyết hai rủi ro khác nhau.

**Log an toàn:** ghi nhận ai thực hiện hành động gì trên loại tài nguyên nào, kết quả cho phép/từ chối và correlation ID khi cần. Không ghi token, session ID hoặc nội dung nhạy cảm.

## 13. Kiểm thử phân quyền

Kiểm thử cần bao phủ cả quyền hành động lẫn quyền trên đối tượng. Chỉ test người dùng có role quản trị thành công là chưa đủ.

| Người dùng | Hành động | Đối tượng | Kết quả mong đợi |
|---|---|---|---|
| Chưa xác thực | Xem sách | Bất kỳ | `401` hoặc chuyển đến đăng nhập theo cơ chế ứng dụng |
| Có `BOOK_VIEW` | Xem | Sách cùng tenant | Cho phép |
| Có `BOOK_VIEW` | Sửa | Sách cùng tenant | Từ chối |
| Có `BOOK_EDIT` và là chủ sở hữu | Sửa | Sách nháp của mình | Cho phép |
| Có `BOOK_EDIT` nhưng khác tenant | Sửa | Sách tenant khác | Từ chối; không rò rỉ dữ liệu |
| Có `BOOK_EDIT` nhưng không sở hữu và không có quyền quản lý | Sửa | Sách cùng tenant của người khác | Từ chối theo policy |
| Có `BOOK_PUBLISH` | Xuất bản | Sách chưa qua kiểm duyệt | Từ chối theo quy tắc trạng thái |
| Có `BOOK_PUBLISH` | Xuất bản | Sách đã được duyệt và trong phạm vi | Cho phép |
| Có quyền trên một bản ghi | Export hàng loạt | Tập ID gồm cả bản ghi ngoài phạm vi | Chỉ xử lý bản ghi được phép hoặc từ chối toàn bộ theo hợp đồng |

**Unit test policy** kiểm tra tổ hợp actor, action, resource và context. **Test Service** xác minh mọi đường gọi use case đều thực thi kiểm tra quyền trước thay đổi. **MockMvc/integration test** gửi request với nhiều user khác nhau và thay ID tài nguyên để phát hiện IDOR. Kiểm tra cả response body, status, dữ liệu không bị thay đổi và log/audit khi cần.

Với policy phức tạp, dùng test dạng bảng hoặc property-based test để kiểm tra các tổ hợp role, tenant, owner và trạng thái. Khi chính sách thay đổi, các test này giúp phát hiện quyền vô tình được mở rộng.

## 14. Những sai lầm thường gặp

- **Chỉ kiểm tra người dùng đã đăng nhập:** authentication không chứng minh quyền trên hành động hoặc đối tượng.
- **Chỉ kiểm tra role ở URL:** người dùng có thể truy cập ID của đối tượng khác qua cùng endpoint.
- **Chỉ ẩn nút trên View:** request trực tiếp vẫn có thể gọi endpoint.
- **Tin ID khó đoán:** UUID không thay thế kiểm tra ownership hoặc tenant.
- **Tin `ownerId` hoặc `tenantId` từ request:** client có thể sửa các giá trị này.
- **Lọc dữ liệu sau khi trả về quá nhiều bản ghi:** dễ rò rỉ dữ liệu và tốn tài nguyên; nên giới hạn truy vấn theo policy khi có thể.
- **Gộp thiếu quyền với trạng thái nghiệp vụ:** gây thông báo sai và khó theo dõi.
- **Kiểm tra quyền ở một Controller duy nhất:** API hoặc job khác có thể gọi Service mà bỏ qua.
- **Không xét quyền trên export/download/bulk action:** các endpoint phụ có thể trở thành đường rò rỉ dữ liệu.
- **Kiểm tra quyền rồi cập nhật ở thời điểm khác:** có thể phát sinh race condition hoặc TOCTOU.
- **Cache response không theo user/tenant:** dữ liệu của người này có thể xuất hiện trong phiên người khác.

## 15. Kết luận

Phân quyền theo hành động xác định người dùng có thể thực hiện loại thao tác nào; phân quyền theo đối tượng xác định thao tác đó có được phép trên tài nguyên cụ thể hay không. RBAC giúp quản lý permission theo vai trò; ABAC và quan hệ sở hữu/đơn vị bổ sung điều kiện theo thuộc tính và mối quan hệ.

Trong MVC, hãy kiểm tra quyền ở tầng request để chặn sớm, bảo vệ use case tại Service hoặc application policy, giới hạn truy vấn theo phạm vi dữ liệu và chỉ dùng View để phản ánh các thao tác được phép. Mỗi request phải được kiểm tra ở server, kể cả khi người dùng tự tạo URL hoặc gửi ID khác. Cách tổ chức này giúp giảm IDOR, bảo vệ dữ liệu đa tenant và giữ chính sách nhất quán giữa giao diện, API và tác vụ nền.
