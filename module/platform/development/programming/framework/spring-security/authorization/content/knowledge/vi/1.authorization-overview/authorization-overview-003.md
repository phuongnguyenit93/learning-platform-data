# Chủ thể, tài nguyên, hành động và ngữ cảnh của một quyết định phân quyền

## 1. Mục tiêu và ý tưởng cốt lõi

Sau bài này, bạn có thể nhận diện bốn đầu vào của một quyết định phân quyền; phân biệt danh tính đã được xác thực với quyền trên một đối tượng cụ thể; viết chính sách có xét chủ sở hữu, tenant, trạng thái nghiệp vụ và ngữ cảnh; rồi đặt kiểm tra vào đúng vị trí trong ứng dụng Spring Security.

**Authentication (xác thực)** trả lời: “Ai đang thực hiện yêu cầu?” **Authorization (phân quyền)** trả lời: “Chủ thể này có được thực hiện hành động đó trên tài nguyên ấy, trong hoàn cảnh hiện tại không?”. Đăng nhập thành công chưa đồng nghĩa được phép đọc/sửa mọi dữ liệu.

Có thể mô hình hóa một phép kiểm tra như sau:

```text
Decision = authorize(Subject, Resource, Action, Context, Policy)

Subject  = ai yêu cầu?
Resource = đối tượng nào bị tác động?
Action   = thao tác nghiệp vụ gì?
Context  = điều kiện nào đang áp dụng?
Policy   = quy tắc nào quyết định ALLOW hay DENY?
```

`Policy` là tập quy tắc dùng để đánh giá bốn đầu vào, không phải một đầu vào do client tự khai báo. Quyết định cuối cần được **thực thi** trước khi trả dữ liệu hoặc thực hiện tác động phụ. Khi thiếu thông tin đáng tin cậy hoặc không có quy tắc cho phép, áp dụng **deny by default** (mặc định từ chối).

## 2. Bốn thành phần cần phân biệt

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong hệ thống tài liệu | Nguồn đáng tin cậy |
| --- | --- | --- | --- |
| **Subject (S) — chủ thể** | Ai đang yêu cầu và chủ thể đang có thuộc tính/quyền gì? | Người dùng `u17`, tenant `acme`, vai trò `EDITOR`, tài khoản đang hoạt động | `Authentication` đã được xác thực; thông tin thành viên/quyền từ hệ thống quản lý danh tính |
| **Resource (R) — tài nguyên** | Đúng bản ghi, đối tượng hoặc phạm vi dữ liệu nào? | Tài liệu `doc-42`, thuộc tenant `acme`, owner `u17`, trạng thái `DRAFT` | Bản ghi/metadata do phía server tải từ nguồn dữ liệu có thẩm quyền |
| **Action (A) — hành động** | Chính xác thao tác gì được đề nghị? | `READ`, `EDIT`, `DELETE`, `APPROVE`, `EXPORT` | API/use case/service đã xác định thao tác và ý nghĩa nghiệp vụ |
| **Context (C) — ngữ cảnh** | Những điều kiện bổ sung nào đang đúng tại thời điểm ra quyết định? | MFA vừa được xác nhận, chế độ chỉ đọc, thời gian, trạng thái phiên, tổ chức hiện hành | Tín hiệu server kiểm chứng; phiên/xác thực; trạng thái hệ thống và chính sách |

### 2.1. Subject không chỉ là username

`Subject` có thể là người dùng, service account hoặc tác nhân máy. Tùy nghiệp vụ, thuộc tính có ích gồm:

- Danh tính ổn định (`subjectId`), trạng thái khóa/vô hiệu hóa và thông tin phiên.
- `GrantedAuthority`/role như `ROLE_ADMIN`, `document:read`; vai trò là **một phần thông tin về chủ thể**, chưa đủ kết luận quyền trên từng bản ghi.
- Thành viên tenant, nhóm, phòng ban, phạm vi ủy quyền. Nếu thuộc tính biến động, cần lấy từ nguồn đủ mới, không mặc định mọi claim cũ còn hiệu lực.

Trong Spring Security, `Authentication` thường mang principal và các `GrantedAuthority`. Dữ liệu phân quyền bổ sung có thể phải tra cứu ở ứng dụng. Không tin `userId`, `roles` hoặc `tenantId` mà người gọi tự gửi trong body/query/header; một claim chỉ có thể dùng làm đầu vào đáng tin khi token đã được xác minh và semantics của claim được hệ thống chấp nhận.

### 2.2. Resource là đối tượng thực, không phải riêng ID

`/api/documents/doc-42` chỉ cung cấp định danh đối tượng được yêu cầu. Phía server phải tra cứu dữ liệu để biết `doc-42` thuộc ai, ở tenant nào, đã bị khóa/duyệt chưa. UUID khó đoán cũng **không thay thế** kiểm tra quyền.

Tài nguyên có thể là một hàng DB, tệp, giao dịch, trường dữ liệu hoặc tập kết quả. Với danh sách, phân quyền còn quyết định **bản ghi nào được xuất hiện**; không nên tải toàn bộ dữ liệu rồi vô tình trả về đối tượng ngoài phạm vi.

### 2.3. Action phải có ý nghĩa nghiệp vụ rõ ràng

`GET` thường gợi ý hành động đọc, nhưng phương thức HTTP không luôn mô tả đầy đủ nghiệp vụ. Một `POST /documents/{id}/approve` là `APPROVE`, khác `EDIT`; một hành động `EXPORT` có thể nhạy cảm hơn `READ`. Phải kiểm tra đúng quyền theo thao tác thực sự diễn ra, kể cả API batch, message consumer hoặc job nội bộ không đi qua HTTP controller.

### 2.4. Context có thể thay đổi ngay cả khi S, R, A giữ nguyên

Một người có quyền sửa bản nháp vào sáng nay nhưng không được sửa khi hệ thống bật chế độ chỉ đọc. Quyền xóa có thể cần MFA; lệnh duyệt có thể chỉ hợp lệ trong khung thời gian hoặc khi tài liệu đang `PENDING`. Context cần được xác định ở thời điểm ra quyết định và gắn với yêu cầu hiện tại.

Phân biệt rõ **ngữ cảnh bảo mật** (ví dụ đã hoàn thành MFA) và **ngữ cảnh nghiệp vụ** (ví dụ kỳ kế toán đã khóa). Không dựa riêng vào IP hoặc header do client tự khai báo để chứng minh điều kiện bảo mật. Tenant cũng có thể được xem là thuộc tính subject/resource hoặc thuộc context; điều cốt yếu là phải so sánh nhất quán từ nguồn đáng tin.

## 3. Từ bốn thành phần đến quyết định

Ví dụ quy tắc trong hệ thống quản lý tài liệu nhiều tenant:

1. Chỉ tài khoản đang hoạt động mới được xét quyền.
2. Chủ thể và tài liệu phải ở **cùng tenant**.
3. `READ`: chủ sở hữu **hoặc** người có vai trò `AUDITOR` trong tenant.
4. `EDIT`: chủ sở hữu có vai trò `EDITOR`, tài liệu đang `DRAFT` và hệ thống không ở chế độ chỉ đọc.
5. `DELETE`: người có vai trò `ADMIN` trong tenant, tài liệu đang `DRAFT`, phiên đã qua MFA và hệ thống không ở chế độ chỉ đọc.
6. Trường hợp còn lại: `DENY`. Không có “`ADMIN` toàn hệ thống bỏ qua tenant” trong chính sách ví dụ này.

Viết gọn:

```text
allow(S, R, A, C) =
    S.active
    AND sameTenant(S, R)
    AND NOT (C.readOnly AND A != READ)
    AND (
         (A == READ   AND (isOwner(S, R) OR hasRole(S, AUDITOR)))
      OR (A == EDIT   AND isOwner(S, R) AND hasRole(S, EDITOR) AND R.state == DRAFT)
      OR (A == DELETE AND hasRole(S, ADMIN) AND R.state == DRAFT AND C.mfaPassed)
    )
```

Đây là **chính sách ví dụ để học tư duy**, không phải mặc định của Spring Security hay một quy tắc áp dụng cho mọi sản phẩm. Trong thực tế, quyền duyệt, chia sẻ, phân loại dữ liệu, pháp lý và ràng buộc tổ chức có thể khiến biểu thức phức tạp hơn.

### Bảng tình huống

| Chủ thể | Tài nguyên | Hành động | Ngữ cảnh | Quyết định / lý do |
| --- | --- | --- | --- | --- |
| `u17`, `EDITOR`, tenant `acme` | Bản nháp do `u17` sở hữu, tenant `acme` | `READ` | Bình thường | **ALLOW** — cùng tenant, là owner |
| `u17`, `EDITOR`, tenant `acme` | Cùng bản nháp | `EDIT` | Bình thường | **ALLOW** — owner + EDITOR + DRAFT |
| `u88`, `AUDITOR`, tenant `other` | Bản nháp tenant `acme` | `READ` | Bình thường | **DENY** — khác tenant dù có role |
| `u17`, `EDITOR`, tenant `acme` | Tài liệu đã `APPROVED` do `u17` sở hữu | `EDIT` | Bình thường | **DENY** — trạng thái không cho sửa |
| `u21`, `ADMIN`, tenant `acme` | Bản nháp tenant `acme` | `DELETE` | MFA chưa đạt | **DENY** — thiếu điều kiện context |
| `u21`, `ADMIN`, tenant `acme` | Cùng bản nháp | `DELETE` | MFA đã đạt | **ALLOW** — đáp ứng tất cả điều kiện |
| `u17`, `EDITOR`, tenant `acme` | Bản nháp do `u17` sở hữu | `EDIT` | Hệ thống chỉ đọc | **DENY** — context chặn thao tác ghi |

Cùng một người có thể được `READ` nhưng bị `EDIT`; cùng hành động có thể được phép trên tài liệu của mình và bị từ chối trên tài liệu người khác; cùng S–R–A có thể đổi kết quả khi C thay đổi.

## 4. Quy trình đánh giá và thực thi trong một request

Với `GET /api/documents/doc-42`:

1. **Xác thực:** server xác minh phiên hoặc token, tạo `Authentication`; nếu chưa có danh tính hợp lệ và endpoint yêu cầu đăng nhập, kết quả thường là HTTP `401 Unauthorized`.
2. **Xác định hành động:** endpoint/use case xác nhận đang yêu cầu `READ`.
3. **Nạp tài nguyên:** tra cứu `doc-42` cùng owner, tenant, trạng thái và các thuộc tính cần thiết. Không suy quyền từ một ID hoặc tenant do caller cung cấp.
4. **Thu thập ngữ cảnh:** ví dụ thành viên tenant hiện hành, session/MFA, trạng thái bảo trì hoặc quy định thời điểm.
5. **Đánh giá policy:** hàm phân quyền kiểm tra đầy đủ S–R–A–C, đưa ra `ALLOW` hoặc `DENY` (có thể kèm mã lý do phục vụ audit).
6. **Thực thi quyết định:** từ chối trước khi tiết lộ dữ liệu/thay đổi trạng thái, hoặc chỉ chạy nghiệp vụ khi được phép. Với caller đã xác thực nhưng thiếu quyền, thường trả `403 Forbidden`; đôi khi API cố ý trả `404 Not Found` để không tiết lộ sự tồn tại của đối tượng, theo thiết kế nhất quán.
7. **Ghi audit phù hợp:** ghi nhận subject ID, resource ID, action, outcome và reason code; hạn chế dữ liệu nhạy cảm, access token và nội dung tài liệu trong log.

```text
Request → Authentication → xác định Action/Resource
                               ↓
                    nạp dữ liệu và Context
                               ↓
                       Policy(S,R,A,C)
                        ┌──────┴──────┐
                      ALLOW          DENY
                        ↓              ↓
                    Thực thi       Chặn yêu cầu
```

Nếu truy vấn danh sách, hãy đưa điều kiện tenant/quyền vào truy vấn dữ liệu (hoặc lọc an toàn trước khi phản hồi). Nếu một nghiệp vụ đổi trạng thái quan trọng giữa bước kiểm tra và bước ghi, cần thực thi với giao dịch, điều kiện cập nhật hoặc khóa thích hợp để tránh lỗi **time of check vs. time of use**.

## 5. Ví dụ Java 17+ chạy độc lập

Ví dụ dưới đây cài đặt chính sách ở mục 3 bằng Java thuần. `record` giữ các thuộc tính đầu vào; `Decision` biểu diễn kết quả. Nó tách phần ra quyết định khỏi HTTP/framework để dễ unit test.

Tạo tệp `AuthorizationDecisionDemo.java`:

```java
import java.util.Set;

public class AuthorizationDecisionDemo {
    enum Action { READ, EDIT, DELETE }
    enum State { DRAFT, APPROVED }
    enum Decision { ALLOW, DENY }

    record Subject(
            String userId, String tenantId, Set<String> roles, boolean enabled) {
        Subject {
            roles = Set.copyOf(roles);
        }
    }

    record Document(
            String id, String tenantId, String ownerId, State state) {}

    record Context(boolean mfaPassed, boolean readOnly) {}

    static Decision decide(
            Subject subject, Document resource, Action action, Context context) {
        if (subject == null || resource == null
                || action == null || context == null) {
            return Decision.DENY;
        }
        if (!subject.enabled()
                || subject.tenantId() == null
                || resource.tenantId() == null
                || !subject.tenantId().equals(resource.tenantId())) {
            return Decision.DENY;
        }
        if (context.readOnly() && action != Action.READ) {
            return Decision.DENY;
        }

        boolean owner = subject.userId() != null
                && subject.userId().equals(resource.ownerId());

        return switch (action) {
            case READ -> (owner || subject.roles().contains("AUDITOR"))
                    ? Decision.ALLOW : Decision.DENY;
            case EDIT -> (owner
                    && subject.roles().contains("EDITOR")
                    && resource.state() == State.DRAFT)
                    ? Decision.ALLOW : Decision.DENY;
            case DELETE -> (subject.roles().contains("ADMIN")
                    && resource.state() == State.DRAFT
                    && context.mfaPassed())
                    ? Decision.ALLOW : Decision.DENY;
        };
    }

    public static void main(String[] args) {
        Subject alice = new Subject("u17", "acme", Set.of("EDITOR"), true);
        Subject bob = new Subject("u88", "other", Set.of("AUDITOR"), true);
        Subject admin = new Subject("u21", "acme", Set.of("ADMIN"), true);
        Document draft = new Document("doc-42", "acme", "u17", State.DRAFT);
        Document approved = new Document("doc-43", "acme", "u17", State.APPROVED);
        Context normal = new Context(false, false);
        Context withMfa = new Context(true, false);
        Context readOnly = new Context(false, true);

        System.out.println("owner-read="
                + decide(alice, draft, Action.READ, normal));
        System.out.println("owner-edit-draft="
                + decide(alice, draft, Action.EDIT, normal));
        System.out.println("other-tenant-read="
                + decide(bob, draft, Action.READ, normal));
        System.out.println("edit-approved="
                + decide(alice, approved, Action.EDIT, normal));
        System.out.println("delete-without-mfa="
                + decide(admin, draft, Action.DELETE, normal));
        System.out.println("delete-with-mfa="
                + decide(admin, draft, Action.DELETE, withMfa));
        System.out.println("edit-during-read-only="
                + decide(alice, draft, Action.EDIT, readOnly));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AuthorizationDecisionDemo.java
java AuthorizationDecisionDemo
```

Kết quả chính xác:

```text
owner-read=ALLOW
owner-edit-draft=ALLOW
other-tenant-read=DENY
edit-approved=DENY
delete-without-mfa=DENY
delete-with-mfa=ALLOW
edit-during-read-only=DENY
```

Giải thích:

- Role `EDITOR` của Alice tự nó không cấp quyền sửa mọi tài liệu; cần quan hệ sở hữu, tenant trùng và trạng thái `DRAFT`.
- Bob có `AUDITOR` nhưng bị từ chối trước khi xét quyền đọc vì tenant khác.
- Admin chỉ xóa được bản nháp cùng tenant và khi `mfaPassed` là `true`.
- `readOnly` không thay đổi subject/resource/action, nhưng làm kết quả `EDIT` chuyển sang `DENY`.

Trong sản phẩm thật, `Subject`/`Context` phải hình thành từ dữ liệu server tin cậy, `Document` phải lấy từ persistence, và chính sách có thể cần phân quyền trường, khóa dữ liệu, thời hạn ủy quyền hoặc điều kiện nghiệp vụ bổ sung.

## 6. Liên hệ với Spring Security

Spring Security giúp **chặn lời gọi** và cung cấp `Authentication`/authorities; ứng dụng chịu trách nhiệm mô hình hóa dữ liệu và quy tắc phân quyền cho từng tài nguyên.

### 6.1. Request-level authorization: cổng vào HTTP

Ở ứng dụng Servlet, `SecurityFilterChain` và `authorizeHttpRequests` thường bảo vệ endpoint ở tầng request. Ví dụ phần phương thức bên trong một lớp `@Configuration` đã import đúng thư viện:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(registry -> registry
            .requestMatchers("/api/documents/**").authenticated()
            .anyRequest().denyAll()
    ).build();
}
```

Đoạn trên yêu cầu caller đăng nhập mới tới được đường dẫn tài liệu. Nó **chưa kiểm tra** `doc-42` có thuộc tenant/owner phù hợp hoặc trạng thái có cho phép sửa/xóa hay không. Các điều kiện theo đối tượng cần kiểm tra trong use case/service hoặc một `AuthorizationManager` tùy biến có đủ dữ liệu.

### 6.2. Method-level authorization: gần nghiệp vụ và đối tượng

Bật method security bằng `@EnableMethodSecurity` trên cấu hình Spring. Có thể dùng `@PreAuthorize` để gọi bean đánh giá chính sách:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}

// Đoạn minh họa trong một Spring-managed service:
@PreAuthorize("@documentPolicy.canRead(authentication, #documentId)")
public Document readDocument(String documentId) {
    return documentRepository.findById(documentId).orElseThrow();
}
```

Đây là **đoạn tích hợp minh họa, không phải chương trình Java độc lập**: `Document`, `documentRepository` và bean `documentPolicy` là các thành phần ứng dụng phải tự định nghĩa. Bean `documentPolicy.canRead(...)` cần giải quyết subject từ `Authentication`, nạp tài nguyên theo `documentId`, xác định context đáng tin cậy và kiểm tra chính sách `READ`; không được mặc định `isAuthenticated()` hoặc `hasRole('USER')` đồng nghĩa có quyền đọc tài liệu bất kỳ.

Các thao tác `EDIT`, `DELETE`, `APPROVE` phải có kiểm tra riêng tương ứng. Khi phân quyền cần trạng thái cập nhật đồng bộ với ghi dữ liệu, hãy thiết kế giao dịch/điều kiện cập nhật ở service hoặc repository. Method security dựa trên Spring AOP/proxy: lời gọi nội bộ trực tiếp trong cùng bean có thể không đi qua interceptor; đặt chốt phân quyền ở ranh giới nghiệp vụ thực sự được gọi và bảo vệ đường đi khác.

### 6.3. AuthorizationManager và các mô hình policy

Trong kiến trúc Spring Security hiện đại, `AuthorizationManager` xử lý quyết định cho request/method hoặc nơi được tích hợp. `GrantedAuthority` mô tả quyền đã gắn với subject; so khớp `hasRole`/`hasAuthority` là trường hợp đơn giản. Với điều kiện phụ thuộc resource và context, ứng dụng phải cung cấp logic truy vấn dữ liệu và đánh giá thích hợp.

- **RBAC (role-based):** “`ADMIN` có quyền xóa” — dễ dùng, nhưng role đơn lẻ thường quá thô.
- **ABAC (attribute-based):** “`EDITOR` chỉ được sửa tài liệu `DRAFT` của cùng tenant khi không ở chế độ chỉ đọc” — xét thuộc tính S, R và C.
- **ReBAC/quan hệ:** “người đang yêu cầu là owner/cộng tác viên của tài liệu” — xét quan hệ giữa S và R.
- **Kết hợp:** `sameTenant && (isOwner || canAudit)` hoặc `role && state && mfa`. Các kiểu chính sách bổ sung lẫn nhau, không bắt buộc chọn một kiểu duy nhất.

## 7. Các lỗi thường gặp và cách tự kiểm tra

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| “Đã đăng nhập nên đọc được mọi `/documents/{id}`” | Đổi ID có thể truy cập tài liệu người khác: **Broken Object Level Authorization (BOLA)** | Kiểm tra quyền trên **mỗi đối tượng** được yêu cầu |
| Chỉ xét role, quên tenant/owner/state | Quyền quá rộng, rò rỉ dữ liệu liên tenant hoặc sửa tài liệu đã khóa | Kết hợp bốn đầu vào theo policy nghiệp vụ |
| Tin `ownerId`, `tenantId`, `isAdmin` từ body/header | Client có thể giả mạo thuộc tính quyết định | Lấy subject và resource/context từ nguồn đã kiểm chứng |
| Dùng `GET/POST` làm thay thế cho `READ/APPROVE` | Không bảo vệ đúng tác vụ nghiệp vụ | Đặt tên action rõ ràng và kiểm tra ở từng use case |
| Truy vấn danh sách trước, trả toàn bộ hoặc phân trang sai rồi mới lọc | Rò dữ liệu, tổng số và trang kết quả không đúng quyền | Ràng buộc phạm vi truy vấn theo tenant/quyền ngay từ nguồn |
| Kiểm tra trước khi trạng thái quan trọng đổi, rồi ghi dựa trên trạng thái cũ | Lỗi tranh chấp/thay đổi sau kiểm tra | Dùng transaction và điều kiện ghi phù hợp |
| Cho phép khi thiếu dữ liệu hoặc không tìm thấy rule | Tạo đường bypass | **Fail closed**: thông tin không đủ → từ chối |
| Chỉ chặn ở controller/UI | Job, message, endpoint khác có thể đi vòng qua | Cố định kiểm tra tại ranh giới service/use case và các điểm truy cập dữ liệu cần thiết |

Bộ kiểm thử tối thiểu nên bao gồm: cùng tenant/khác tenant; owner/người không sở hữu; role có/không; trạng thái `DRAFT`/`APPROVED`; MFA có/không; chế độ chỉ đọc; account bị vô hiệu hóa; resource không tồn tại; yêu cầu qua API trực tiếp, API batch và đường gọi nội bộ. Cần kiểm tra **cả trường hợp bị từ chối**, tránh chỉ test happy path.

## 8. Câu hỏi tự kiểm tra

1. Alice có role `EDITOR` và cùng tenant với tài liệu, nhưng tài liệu do Bob sở hữu. Alice có được `EDIT` theo policy mục 3 không? **Không**: còn thiếu quan hệ owner.
2. Người có `ADMIN` ở tenant khác và đã MFA có được xóa bản nháp không? **Không**: sai tenant, điều kiện nền tảng đã không đạt.
3. Cùng Alice, cùng tài liệu nháp, cùng `EDIT`; tại sao lúc bình thường là `ALLOW` còn khi bật chế độ chỉ đọc là `DENY`? **Context thay đổi** dù subject, resource, action giữ nguyên.
4. Vì sao `.requestMatchers("/api/documents/**").authenticated()` chưa đủ? Vì nó kiểm tra quyền vào tuyến HTTP, chưa xác minh **quyền trên từng tài nguyên** gắn với ID.

**Ghi nhớ:** mọi phép phân quyền có ý nghĩa đều phải trả lời đầy đủ **ai → trên cái gì → làm gì → trong điều kiện nào**. Mức độ phức tạp của policy tùy nghiệp vụ, nhưng thiếu một chiều cần thiết có thể biến một endpoint đã đăng nhập thành một lỗ hổng quyền truy cập.

## Tài liệu tham khảo

- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- OWASP API Security Top 10 (2023) — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
