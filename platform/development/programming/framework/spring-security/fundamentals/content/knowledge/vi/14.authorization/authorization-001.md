# Phân quyền: Ai được thực hiện thao tác nào trên tài nguyên nào?

## 1. Bản chất của authorization

**Phân quyền (authorization)** là quá trình quyết định một chủ thể đã được xác định có được phép thực hiện **một hành động cụ thể trên một tài nguyên cụ thể, trong ngữ cảnh hiện tại** hay không. Có thể viết quyết định này dưới dạng:

~~~text
allow = policy(subject, action, resource, context)
~~~

Bốn thành phần phải được tách bạch:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| `subject` (chủ thể) | **Ai** yêu cầu? | Người dùng `alice`, tài khoản dịch vụ, principal lấy từ JWT/session |
| `action` (hành động) | Muốn **làm gì**? | Đọc, sửa, xoá, duyệt, xuất báo cáo; HTTP GET/POST/DELETE là tín hiệu nhưng chưa đủ mô tả nghiệp vụ |
| `resource` (tài nguyên) | Tác động **lên cái gì**? | Tài liệu `doc-42`, đơn hàng `order-17`, một trường dữ liệu nhạy cảm |
| `context` (ngữ cảnh) | Điều kiện nào phải đúng? | Tenant, chủ sở hữu, trạng thái giao dịch, giờ truy cập, mức phân loại, quan hệ với tài nguyên |

Kết quả thông thường là `ALLOW` hoặc `DENY`. **Đã đăng nhập không đồng nghĩa có quyền**. Với cùng một người và một hành động, kết quả có thể khác nhau trên hai tài nguyên: Alice được đọc tài liệu do Alice sở hữu nhưng không được đọc tài liệu riêng của Bob.

Ví dụ chính sách trong một hệ thống tài liệu:

- Alice có quyền `document:read`, cùng tenant và là chủ sở hữu `doc-1` → được đọc.
- Bob có quyền `document:read` và cùng tenant, nhưng không sở hữu `doc-1` → bị từ chối nếu tài liệu là riêng tư.
- Quản trị viên của tenant có `document:delete` và chính sách cho phép quản trị viên xoá tài liệu trong tenant → được xoá.
- Quản trị viên tenant A không tự động được đọc dữ liệu tenant B.
- Người chưa đăng nhập không truy cập tài liệu riêng, dù biết chính xác URL hoặc ID.

Đây là điểm cốt lõi của câu hỏi **“ai được thực hiện thao tác nào trên tài nguyên nào”**: một quyền tổng quát như `document:read` có thể chỉ là **điều kiện cần**, chưa đủ để cấp quyền với từng bản ghi.

## 2. Authentication và authorization khác nhau

| | Authentication (xác thực) | Authorization (phân quyền) |
| --- | --- | --- |
| Câu hỏi | “Bạn là ai?” | “Bạn có được thực hiện việc này không?” |
| Dữ liệu chính | Credential, session, token, danh tính | Principal, authorities, action, resource, chính sách |
| Kết quả | Thiết lập danh tính đã xác thực hoặc thất bại | Cho phép/từ chối một thao tác |
| Ví dụ | Kiểm tra mật khẩu/JWT hợp lệ | Alice có được xoá tài liệu `doc-1` không? |

Trong một ứng dụng điển hình, xác thực diễn ra trước để tạo `Authentication` đại diện cho chủ thể; tiếp theo, phân quyền dùng thông tin đó cùng tài nguyên và quy tắc nghiệp vụ. API công khai có thể cho phép truy cập không cần xác thực; API riêng phải áp dụng điều kiện tương ứng.

**Đừng dùng dữ liệu do client tự khai** như `userId`, `ownerId`, `role` hoặc `tenantId` trong body/query làm bằng chứng người gọi có quyền. Danh tính và quyền phải đến từ nguồn tin cậy sau xác thực; định danh tài nguyên trong URL chỉ là đối tượng cần kiểm tra.

## 3. Ba trục kiểm tra quyền và hai tầng bảo vệ

Một thiết kế dễ hiểu bắt đầu từ bộ ba `(principal, action, resource)`:

1. **Principal**: người dùng/dịch vụ nào? Có authority, vai trò và tenant nào đã được hệ thống xác nhận?
2. **Action**: đọc, tạo, cập nhật, xoá, duyệt hay xuất dữ liệu? Tránh đồng nhất mọi thao tác GET với nhau hoặc mọi thao tác POST với nhau nếu ý nghĩa nghiệp vụ khác nhau.
3. **Resource**: đúng loại tài nguyên và **đúng instance** nào? Bản ghi thuộc ai, thuộc tenant nào, trạng thái có cho phép thay đổi không?

Ở Spring Security, thường phải phối hợp hai tầng:

- **Request-level authorization**: kiểm tra đường dẫn và HTTP method ngay trong security filter chain. Ví dụ GET `/documents/**` cần `document:read`, DELETE `/documents/**` cần `document:delete`.
- **Method/domain-level authorization**: kiểm tra thao tác nghiệp vụ và quyền với **bản ghi cụ thể** trong service. Ví dụ chỉ chủ sở hữu hoặc người được uỷ quyền mới được sửa `doc-42`, sau khi kiểm tra tenant.

Tầng URL hữu ích để chặn sớm, nhưng **không chứng minh người dùng có quyền với mọi ID** khớp URL. Nếu service được gọi từ REST, scheduler, message consumer hay một service khác, kiểm tra ở tầng nghiệp vụ giúp bảo vệ nhất quán. Ngược lại, các method không được đánh dấu bảo vệ sẽ không tự động có `@PreAuthorize`; cấu hình request nên có quy tắc chặn mặc định.

## 4. Role, authority, permission và chính sách tài nguyên

**Role** nhóm trách nhiệm, như `USER`, `EDITOR`, `ADMIN`. **Authority/permission** biểu diễn một khả năng cụ thể, như `document:read`, `document:publish`, `invoice:approve`. Với mặc định của Spring Security:

- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` kiểm tra chính xác chuỗi `ROLE_ADMIN`.
- `hasAuthority("document:read")` kiểm tra chính xác `document:read`.
- Vai trò `ADMIN` không tự “bỏ qua mọi kiểm tra”; ứng dụng phải định nghĩa rõ vai trò này cho phép điều gì.

Ba mô hình thường gặp có thể kết hợp:

| Mô hình | Quy tắc | Phù hợp |
| --- | --- | --- |
| **RBAC** (theo vai trò) | `ADMIN` duyệt cấu hình, `EDITOR` sửa nội dung | Quyền ổn định theo nhóm trách nhiệm |
| **ABAC** (theo thuộc tính) | Chỉ sửa đơn khi `status=DRAFT`, cùng tenant, đúng bộ phận | Quyết định phụ thuộc thuộc tính/ngữ cảnh |
| **Quan hệ/ownership** | Chủ sở hữu được đọc tài liệu; thành viên dự án được xem hồ sơ | Quyền gắn với từng tài nguyên và quan hệ |

Ví dụ, một policy thực tế có thể là: người có `document:write` **và** cùng tenant **và** (là chủ sở hữu **hoặc** được giao quyền sửa) **và** tài liệu chưa khoá. Nếu thiếu bất kỳ điều kiện bắt buộc nào, kết quả là từ chối. Trong hệ thống nhiều tenant, “admin của tenant A” thường chỉ được quản trị **phạm vi A**; một quyền toàn hệ thống nếu cần phải được định nghĩa riêng.

## 5. Thực hành: mô hình policy thuần Java 17 chạy độc lập

Ví dụ nhỏ sau tách rõ ai, thao tác, tài nguyên. Nó **không thay Spring Security** mà giúp kiểm chứng tư duy quyết định trước khi gắn chính sách vào API. Các record và code đều tương thích Java 17.

**Tệp `AuthorizationDecisionDemo.java`:**

~~~java
import java.util.Set;

record Actor(String name, String tenant, Set<String> permissions, boolean admin) {}
record Document(String id, String owner, String tenant) {}

public class AuthorizationDecisionDemo {
    static boolean allow(Actor actor, String action, Document doc) {
        // Fail closed: thiếu chủ thể/tài nguyên hoặc sai tenant => từ chối.
        return actor != null && doc != null
                && actor.tenant().equals(doc.tenant())
                && actor.permissions().contains(action)
                && (actor.admin() || actor.name().equals(doc.owner()));
    }

    public static void main(String[] args) {
        Document doc = new Document("doc-1", "alice", "tenant-a");
        Actor alice = new Actor("alice", "tenant-a",
                Set.of("document:read"), false);
        Actor bob = new Actor("bob", "tenant-a",
                Set.of("document:read"), false);
        Actor admin = new Actor("admin", "tenant-a",
                Set.of("document:read", "document:delete"), true);
        Actor otherTenant = new Actor("root", "tenant-b",
                Set.of("document:read", "document:delete"), true);

        System.out.println("alice read: "
                + allow(alice, "document:read", doc));
        System.out.println("bob read: "
                + allow(bob, "document:read", doc));
        System.out.println("admin delete: "
                + allow(admin, "document:delete", doc));
        System.out.println("alice delete: "
                + allow(alice, "document:delete", doc));
        System.out.println("other tenant read: "
                + allow(otherTenant, "document:read", doc));
    }
}
~~~

Chạy từ thư mục chứa tệp, với JDK 17 trở lên:

~~~bash
javac --release 17 AuthorizationDecisionDemo.java
java AuthorizationDecisionDemo
~~~

**Stdout chính xác:**

~~~text
alice read: true
bob read: false
admin delete: true
alice delete: false
other tenant read: false
~~~

Giải thích từng kết quả:

1. Alice có permission đọc, đúng tenant và là chủ tài liệu → `true`.
2. Bob có permission đọc nhưng không phải chủ sở hữu → `false`.
3. Admin có permission xoá, đúng tenant và có cờ quản trị → `true`.
4. Alice là chủ sở hữu nhưng **thiếu permission xoá** → `false`.
5. “Admin” thuộc tenant khác vẫn bị chặn **trước** khi xét quyền quản trị → `false`.

Cờ `admin` chỉ là mô hình học tập, không phải bằng chứng tin cậy khi client gửi lên. Trong ứng dụng thật, role/permission/tenant phải lấy từ danh tính đã xác thực và dữ liệu quyền phía server. Thao tác xoá thực tế còn có thể yêu cầu kiểm tra trạng thái tài liệu, quy trình phê duyệt và ghi audit.

## 6. Áp dụng vào Spring Security (Servlet)

Trong Spring Security, `SecurityContext` giữ `Authentication` của request đã xác thực; `Authentication` chứa tên/principal và tập `GrantedAuthority`. `AuthorizationManager` dùng những dữ liệu này để ra quyết định. Với ứng dụng Servlet, `AuthorizationFilter` thường thực thi chính sách HTTP; Method Security có thể thực thi tiếp tại lời gọi method của bean Spring.

Ví dụ **cấu hình minh hoạ** trong ứng dụng Spring Boot có Spring Web và Spring Security, dùng Java 17+; đây là class cấu hình cần đặt trong dự án Spring, **không phải chương trình Java độc lập chạy bằng `javac`**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class AuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/documents/**")
                    .hasAuthority("document:read")
                .requestMatchers(HttpMethod.DELETE, "/documents/**")
                    .hasAuthority("document:delete")
                .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Đọc cấu hình theo thứ tự:

- GET đường dẫn công khai khớp `/public/**` không yêu cầu quyền; `permitAll()` là ngoại lệ **đã chủ đích**.
- GET `/documents/123` yêu cầu authority `document:read`; DELETE cùng URL yêu cầu `document:delete`.
- Tất cả request còn lại bị `denyAll()` (quy tắc mặc định từ chối).
- **Thứ tự matcher có ý nghĩa:** Spring Security chọn quy tắc đầu tiên khớp. Nếu đặt `anyRequest()` trước các quy tắc cụ thể thì cấu hình sẽ sai/không hợp lệ.
- `@EnableMethodSecurity` kích hoạt các annotation như `@PreAuthorize` trên bean được Spring quản lý. Chỉ thêm dependency Spring Security không tự bật mọi kiểm tra method.
- Ví dụ tập trung vào **phân quyền**; nó chưa cấu hình cơ chế đăng nhập (HTTP Basic, session/form, JWT/resource server...), user store hay endpoint. Tích hợp thực tế phải cấu hình xác thực phù hợp.

Ví dụ kiểm soát quyền ở method:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public Document readDocument(String documentId) {
    // Bước nghiệp vụ: tải đúng tài liệu, kiểm tra tenant và quyền đối
    // với documentId (owner, người được chia sẻ, trạng thái...), rồi mới trả dữ liệu.
    // Ví dụ cụ thể ở đây được lược để tập trung vào ranh giới phân quyền.
}
~~~

Đoạn method trên là **sơ đồ logic minh hoạ**, không biên dịch độc lập vì chưa khai báo `Document`/repository và chưa có body thực thi. Quy tắc `hasAuthority` chỉ xác nhận quyền đọc **ở cấp hành động**; ứng dụng phải kiểm tra quyền **trên tài liệu được yêu cầu**. Nếu muốn đưa điều kiện tài nguyên vào annotation, có thể ủy quyền cho một bean policy bằng SpEL, ví dụ `@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")` với `#p0` là tham số đầu tiên và `documentPolicy` là bean do ứng dụng cung cấp. Bean này phải truy vấn dữ liệu/quan hệ đáng tin cậy và trả kết quả đúng trên tài nguyên cụ thể; không suy đoán từ ID do client gửi.

Một cách thực hiện khác là giữ `@PreAuthorize` cho quyền thao tác rồi kiểm tra domain policy trong service và ném `AccessDeniedException` khi không đủ quyền. Cách nào cũng phải được gọi **trước khi trả dữ liệu hoặc tạo side effect**. Với thao tác sửa/xoá, kiểm tra và thay đổi trạng thái cần cùng ranh giới transaction/điều kiện cập nhật phù hợp để tránh race condition kiểu *time-of-check vs time-of-use*.

### Luồng quyết định HTTP điển hình

~~~text
Client gửi yêu cầu GET /documents/doc-1
    |
    v
Bộ lọc xác thực kiểm tra session/token và xây dựng Authentication
    |
    v
AuthorizationFilter đọc HTTP method + path + authorities
    |-- không đủ document:read --> từ chối
    |
    v
Controller -> Service (có thể chịu @PreAuthorize)
    |
    v
Policy tải document, kiểm tra tenant, owner/chia sẻ, trạng thái
    |-- điều kiện không đạt --> từ chối (AccessDeniedException)
    |
    v
Thực thi nghiệp vụ và trả dữ liệu được phép
~~~

**Một quyết định ở filter không thay thế được quyết định ở tầng dữ liệu.** Nếu kẻ tấn công đổi `/documents/1` thành `/documents/2` và cả hai cùng khớp URL, chỉ có kiểm tra gắn với tài liệu mới ngăn truy cập trái phép kiểu IDOR/BOLA.

## 7. Xử lý từ chối và ngữ nghĩa HTTP

- **Chưa xác thực** nhưng endpoint yêu cầu danh tính: thông thường hệ thống API trả `401 Unauthorized` kèm challenge nếu có cơ chế như HTTP Basic/Bearer; ứng dụng form-login có thể điều hướng đến trang đăng nhập. Hành vi cụ thể phụ thuộc authentication entry point.
- **Đã xác thực nhưng thiếu quyền**: thường là `403 Forbidden`. Spring Security phát sinh/biên dịch tình huống từ chối qua `AccessDeniedException` và xử lý trong security exception flow.
- **Tài nguyên không tồn tại**: có thể trả `404 Not Found`; một số hệ thống chủ ý trả 404 để hạn chế tiết lộ sự tồn tại của tài nguyên, nhưng phải có chính sách nhất quán.
- `permitAll()` có nghĩa request được phép qua tầng rule này; nó **không bảo đảm** dữ liệu nghiệp vụ được phép xem, không bỏ qua kiểm tra đầu vào hay những cơ chế bảo vệ khác.
- **CSRF không phải phân quyền.** Với browser/cookie/session và các request đổi trạng thái, CSRF protection vẫn quan trọng; một DELETE hợp lệ về role có thể bị chặn bởi CSRF nếu thiếu token. Đừng tắt CSRF chỉ để khiến ví dụ DELETE trả thành công.
- Không trả chi tiết nhạy cảm như danh sách quyền nội bộ, chủ sở hữu bí mật hay cấu trúc policy trong thông báo lỗi cho client; ghi log có kiểm soát để hỗ trợ điều tra.

## 8. Kiểm thử theo ma trận chủ thể × hành động × tài nguyên

Đừng chỉ kiểm tra người dùng hợp lệ. Ít nhất phải có các ca **bị từ chối**, để phát hiện lỗ hổng phân quyền theo chiều ngang (khác người cùng role) và chiều dọc (role thấp gọi chức năng cao):

| Actor / trạng thái | Action và tài nguyên | Mong đợi | Điều kiện quyết định |
| --- | --- | --- | --- |
| Chưa đăng nhập | GET tài liệu riêng | Không cho đọc | Thiếu danh tính; auth entry point xử lý |
| Alice, có `document:read` | GET tài liệu của Alice trong tenant A | Cho đọc | Có permission, đúng tenant, đúng owner |
| Bob, có `document:read` | GET tài liệu riêng của Alice trong tenant A | Từ chối | Có permission nhưng sai owner |
| Alice, không có `document:delete` | DELETE tài liệu của Alice | Từ chối | Owner không thay thế permission thao tác |
| Admin tenant A | DELETE tài liệu tenant A | Cho phép **nếu** policy định nghĩa và mọi điều kiện khác đúng | Authority + tenant + rule quản trị |
| Admin tenant B | GET tài liệu tenant A | Từ chối | Chặn vượt biên tenant |
| Bất kỳ actor | Thao tác không khai báo | Từ chối | Deny-by-default |
| Actor đã được cấp quyền | Sửa tài liệu ở trạng thái khoá | Từ chối nếu policy cấm | Điều kiện trạng thái nghiệp vụ |

Trong bài kiểm thử Spring MVC, có thể dùng `spring-security-test` và `@WithMockUser(username = "alice", authorities = "document:read")` hoặc `MockMvc` với user/token tương ứng. Kiểm tra **status và dữ liệu thực tế**: một endpoint trả 200 nhưng lộ bản ghi của người khác vẫn là lỗi. Với request đổi trạng thái, cấu hình CSRF và test helper tương ứng; đảm bảo thao tác bị từ chối **không tạo side effect**. Ưu tiên test của service policy với tài nguyên thật/giả lập và test tích hợp filter → controller → service để bắt lỗi bỏ sót một tầng.

## 9. Các lỗi phổ biến và cách sửa

1. **“Đã đăng nhập là được xem”:** chỉ dùng `authenticated()` cho endpoint nhạy cảm. → Thêm permission cho từng thao tác và kiểm tra quyền trên đối tượng.
2. **Nhầm role với authority:** dùng `hasRole("ADMIN")` trong khi principal chỉ có `ADMIN`, hoặc tự thêm `ROLE_` vào tham số sai cách. → Kiểm tra giá trị `GrantedAuthority` thực tế; nhớ quy ước prefix mặc định.
3. **Chỉ bảo vệ URL:** GET `/documents/{id}` có `document:read` là đủ, không đối chiếu owner/tenant. → Kiểm tra ID thực tại service/repository, tránh BOLA/IDOR.
4. **Tin tham số từ client:** nhận `?isAdmin=true` hoặc `tenantId` từ client làm cơ sở cấp quyền. → Lấy principal và tenant từ nguồn đã xác thực, so với dữ liệu phía server.
5. **Kiểm tra sau khi lộ dữ liệu/ghi DB:** policy chạy sau khi trả DTO, gửi event hoặc cập nhật. → Quyết định trước side effect; với cập nhật cạnh tranh, enforce điều kiện tại transaction/query.
6. **Phân quyền mặc định quá rộng:** `anyRequest().permitAll()`, matcher mơ hồ hoặc thứ tự sai. → Quy tắc cụ thể trước, `anyRequest().denyAll()` cho phần không khai báo khi phù hợp.
7. **Cho rằng mọi `@PreAuthorize` đều chạy:** quên `@EnableMethodSecurity`, gọi method nội bộ qua `this` (self-invocation) nên bỏ qua Spring proxy, hoặc gọi object tự tạo bằng `new`. → Đặt rule trên bean Spring và kiểm tra đường gọi thực tế.
8. **Dùng role tổng quát thay cho kiểm tra ngữ cảnh:** admin tenant A đọc mọi tenant, hoặc editor sửa tài liệu đã khoá. → Chính sách gồm tenant + trạng thái + owner/chia sẻ + permission.
9. **Chỉ có happy-path test:** thiếu ca khác chủ sở hữu, khác tenant, thiếu permission. → Lập ma trận allow/deny và kiểm tra cả dữ liệu lẫn side effect.
10. **Nhầm 401 với 403:** coi mọi từ chối là “chưa đăng nhập”. → Phân biệt xác thực thất bại với đã xác thực nhưng không đủ quyền; kiểm tra authentication entry point, access-denied handler và CSRF riêng.

## 10. Quy trình thiết kế một chính sách mới

Khi thêm chức năng như “phê duyệt hóa đơn”, hãy trả lời tuần tự:

1. **Ai?** `ACCOUNTANT`, `APPROVER`, dịch vụ nền; quyền nào được xác nhận từ danh tính thực?
2. **Làm gì?** `invoice:read`, `invoice:approve`, `invoice:cancel`; phân biệt rõ từng action nghiệp vụ.
3. **Trên tài nguyên nào?** Hoá đơn ID gì, tenant nào, người tạo/phê duyệt, trạng thái hiện tại?
4. **Khi nào được phép?** Ví dụ chỉ người có `invoice:approve`, cùng tenant, khác người tạo, hoá đơn đang `PENDING`.
5. **Gắn rule ở đâu?** Chặn quyền tổng quát tại request; chặn quyền theo dữ liệu ở service; kiểm soát query/transaction để không rò rỉ hoặc ghi sai.
6. **Làm sao chứng minh đúng?** Viết test cho phép/từ chối theo từng actor, action, resource, context, đồng thời kiểm tra không có side effect khi deny.

**Câu tự kiểm:** Bob và Alice cùng role `EDITOR`. Bob có được sửa tài liệu của Alice không? **Không thể kết luận chỉ từ role.** Phải biết policy về ownership/chia sẻ, tenant, trạng thái và permission sửa. Đây chính là lý do authorization luôn cần cả **ai + thao tác + tài nguyên + ngữ cảnh**.

### Tài liệu đối chiếu chính thức

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
