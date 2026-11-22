# Phân quyền theo chức năng và phân quyền theo đối tượng

## 1. Mục tiêu bài học

Trong một hệ thống bảo mật, việc người dùng **có quyền gọi một chức năng** và việc họ **được phép thực hiện chức năng đó trên một đối tượng cụ thể** là hai câu hỏi khác nhau. Hiểu sự khác nhau này giúp ngăn lỗi cấp quyền quá rộng, đặc biệt khi API nhận mã tài liệu, đơn hàng, tài khoản hoặc bản ghi từ người gọi.

Sau bài học, bạn có thể:

- Phân biệt **phân quyền theo chức năng** (function-level authorization) và **phân quyền theo đối tượng** (object-level authorization).
- Diễn đạt chính sách kết hợp hai lớp kiểm tra và liên hệ với vai trò, quyền thao tác, chủ sở hữu, tenant, trạng thái đối tượng.
- Áp dụng các lớp kiểm tra vào HTTP endpoint và tầng nghiệp vụ với Spring Security.
- Nhận biết, kiểm thử và xử lý các lỗ hổng **Broken Function Level Authorization (BFLA)** và **Broken Object Level Authorization (BOLA)**.
- Xử lý riêng phân quyền cho danh sách, tìm kiếm, tác vụ nền và trường hợp trạng thái tài nguyên thay đổi.

## 2. Phân biệt hai câu hỏi cốt lõi

**Phân quyền theo chức năng:** “Người này có quyền sử dụng thao tác `APPROVE_DOCUMENT`, `DELETE_USER` hay `EXPORT_REPORT` trong hệ thống hay không?”

**Phân quyền theo đối tượng:** “Cho dù người này có quyền sử dụng thao tác đó, họ có được thực hiện trên **tài liệu d42**, **người dùng u13** hoặc **hóa đơn i07** hay không?”

```text
Yêu cầu: Alice PATCH /documents/d42
                    |
          Đã xác thực Alice?
                    |
            Alice có quyền
           DOCUMENT_EDIT không?    <-- chức năng
                    |
           Alice có quyền sửa
           chính document d42?    <-- đối tượng
                    |
             Điều kiện đang
             áp dụng còn hợp lệ?
                    |
               Cho phép ghi
```

**Nguyên tắc:** Cho phép thao tác chỉ khi **mọi điều kiện bắt buộc** đều đạt. Có quyền thao tác chung không tự động cho phép tác động lên mọi bản ghi.

Ta có thể mô tả:

```text
ALLOW = authenticated(subject)
        AND canInvoke(subject, action)
        AND canAccess(subject, action, resource)
        AND contextAllows(subject, action, resource, context)
```

Trong thiết kế thực tế, quyền theo đối tượng và điều kiện ngữ cảnh có thể nằm cùng một policy. Việc tách chúng ở đây nhằm làm rõ từng trách nhiệm kiểm tra, không bắt buộc triển khai thành bốn hàm riêng. Nếu thiếu dữ liệu tin cậy hoặc không có chính sách cho phép, kết quả phải là **DENY**.

### 2.1. So sánh

| Góc nhìn | Theo chức năng | Theo đối tượng |
| --- | --- | --- |
| Phạm vi câu hỏi | Một loại hành động/use case | Một đối tượng hoặc tập đối tượng cụ thể |
| Đầu vào thường gặp | Principal, roles, permissions, chức năng yêu cầu | Principal, hành động, ID và thuộc tính đối tượng, quan hệ, tenant, trạng thái |
| Ví dụ | `document:edit`; `invoice:approve`; `user:delete` | Người gọi là owner? Cùng tenant? Được giao duyệt? Hóa đơn còn `PENDING`? |
| Chốt kiểm tra | Request matcher, phương thức service, policy ứng dụng | Service/domain policy, truy vấn dữ liệu có điều kiện, custom authorization |
| Lỗi điển hình | Người thiếu quyền quản trị vẫn gọi được endpoint quản trị | Người có quyền đọc tài liệu sửa ID để đọc tài liệu người khác |
| Lỗ hổng API thường liên quan | **BFLA** | **BOLA**, còn gọi phổ biến là IDOR trong nhiều ngữ cảnh |
| Có thay thế cho lớp còn lại? | **Không** | **Không** |

Ví dụ: Bob có `document:edit` vì là biên tập viên. Nếu Bob gửi `PATCH /documents/d42`, chỉ kiểm tra `document:edit` sẽ cho Bob sửa **mọi** tài liệu. Policy theo đối tượng phải xác nhận `d42` thuộc phạm vi Bob được sửa; có thể đòi hỏi Bob là owner, cùng tenant và tài liệu đang là bản nháp.

### 2.2. Hai lớp kiểm tra không đồng nhất với RBAC và ABAC

**RBAC** (phân quyền theo vai trò), **ABAC** (theo thuộc tính) và **ReBAC** (theo quan hệ) mô tả **cách biểu diễn/quyết định quyền**, còn “theo chức năng” và “theo đối tượng” mô tả **phạm vi câu hỏi phân quyền**.

- Kiểm tra theo chức năng có thể dựa trên `GrantedAuthority`, role, thuộc tính phòng ban hoặc ca trực, không bắt buộc chỉ dùng RBAC.
- Kiểm tra theo đối tượng có thể xét owner/nhóm cộng tác (ReBAC), phân loại tài liệu/trạng thái/tenant (ABAC), hoặc role của người dùng **trong chính tài nguyên đó**.
- Cùng một chính sách có thể sử dụng cả RBAC, ABAC và ReBAC để trả lời cả hai câu hỏi.

Ví dụ `ROLE_EDITOR` là thuộc tính của chủ thể; `ownerId == currentUserId` là quan hệ với đối tượng; `status == DRAFT` là thuộc tính đối tượng. Chúng được kết hợp, không có lớp nào tự thay thế lớp khác.

## 3. Ví dụ nhất quán: hệ thống tài liệu nhiều tenant

Giả sử API tài liệu có ba chức năng:

| Hành động nghiệp vụ | Endpoint minh họa | Quyền chức năng |
| --- | --- | --- |
| Đọc tài liệu | `GET /api/documents/{id}` | `document:read` |
| Sửa tài liệu | `PATCH /api/documents/{id}` | `document:edit` |
| Duyệt tài liệu | `POST /api/documents/{id}/approve` | `document:approve` |

Định nghĩa chính sách đối tượng của **hệ thống giả định** như sau:

1. **Điều kiện nền:** tài khoản hoạt động, đối tượng tồn tại và `subject.tenantId == document.tenantId`.
2. **Đọc (`READ`):** người gọi là owner hoặc reviewer được giao của đúng tài liệu.
3. **Sửa (`EDIT`):** người gọi là owner và tài liệu đang `DRAFT`.
4. **Duyệt (`APPROVE`):** người gọi là reviewer được giao, không đồng thời là owner và tài liệu đang `PENDING`.
5. Mọi trường hợp không đáp ứng chính sách bị từ chối; các điều kiện khác như phiên bị thu hồi, hệ thống chỉ đọc hoặc MFA sẽ được bổ sung khi nghiệp vụ yêu cầu.

Đây chỉ là mô hình sư phạm. Trong một sản phẩm khác, quyền đọc có thể mở rộng cho người được chia sẻ hoặc quản trị viên thuộc cùng tenant; thao tác duyệt có thể có nhiều cấp. Quan trọng là xác định quy tắc trước, kiểm tra nhất quán ở các đường đi thực tế và không ngầm cấp quyền do có role chung.

### 3.1. Ma trận quyết định

Giả sử tài liệu `d42` thuộc tenant `alpha`, owner là Alice, reviewer là Ruth; bản nháp `DRAFT` có thể sửa, tài liệu `PENDING` có thể duyệt.

| Người gọi | Quyền chức năng | Đối tượng/hành động | Kết quả | Lớp quyết định |
| --- | --- | --- | --- | --- |
| Alice | `document:edit` | Sửa bản nháp `d42` của Alice | **ALLOW** | Cả hai lớp đạt |
| Bob | `document:edit` | Sửa bản nháp `d42` của Alice | **DENY** | Có chức năng nhưng không phải owner |
| Guest | Chỉ `document:read` | Sửa `d42` | **DENY** | Không có quyền chức năng sửa |
| Ruth | `document:approve` | Duyệt `d42` trạng thái `PENDING`, Ruth là reviewer | **ALLOW** | Đúng quyền, quan hệ và trạng thái |
| Alice | `document:approve` | Duyệt tài liệu `PENDING` do Alice sở hữu | **DENY** | Chính sách cấm tự duyệt |
| Eve thuộc tenant `beta` | `document:read` | Đọc `d42` thuộc tenant `alpha` | **DENY** | Sai phạm vi tenant |
| Ruth | `document:approve` | Duyệt `d42` khi vẫn `DRAFT` | **DENY** | Trạng thái đối tượng không phù hợp |

Trong bảng, **“quyền chức năng” chỉ cho biết người dùng được phép thử một loại thao tác**. Quyền trên `d42` vẫn cần đánh giá độc lập, sử dụng metadata lấy từ máy chủ.

### 3.2. Vì sao ID do client cung cấp không chứng minh quyền?

Hai yêu cầu:

```http
GET /api/documents/d42
GET /api/documents/d43
```

có cùng endpoint, HTTP method và người dùng, nhưng có thể cho kết quả khác nhau. Dữ liệu về owner, tenant, trạng thái và người được giao phải được truy vấn từ nguồn có thẩm quyền; **không tin** `ownerId`, `tenantId` hoặc `isAdmin` trong body/query/header do client tự khai. Một UUID khó đoán cũng không phải cơ chế phân quyền. Client có thể biết ID qua log, đường dẫn, thông báo hoặc chính tài liệu được chia sẻ.

## 4. Quy trình kiểm tra cho một thao tác

Giả sử Bob cố sửa tài liệu của Alice:

1. **Authentication:** Xác minh session/token. Chưa xác thực với tài nguyên yêu cầu đăng nhập thường nhận `401 Unauthorized`.
2. **Xác định chức năng:** API/use case yêu cầu `document:edit`; lấy `Authentication` hoặc subject có quyền đã xác minh. Thiếu quyền chức năng → từ chối.
3. **Nạp đối tượng:** Tìm tài liệu theo `id`; chỉ tin owner, tenant, reviewer, trạng thái do server cung cấp. Không để API tự dựng một đối tượng “owner” từ request body.
4. **Kiểm tra đối tượng và ngữ cảnh:** Với tài liệu đã nạp, xác nhận cùng tenant, đúng quan hệ owner và trạng thái `DRAFT`; kiểm tra thêm điều kiện phiên/chế độ hệ thống nếu chính sách yêu cầu.
5. **Thực thi:** Chỉ thay đổi tài liệu sau khi tất cả kiểm tra đạt. Với người đã xác thực nhưng không có quyền, thường trả `403 Forbidden`; theo thiết kế chống lộ thông tin, một số API có thể dùng `404 Not Found` để che việc đối tượng tồn tại, nhưng phải nhất quán.
6. **Audit:** Ghi định danh người dùng, tài nguyên, thao tác, kết quả và reason code ở mức phù hợp; không ghi token hoặc dữ liệu nhạy cảm không cần thiết.

Với hành động thay đổi trạng thái quan trọng, kiểm tra và cập nhật phải bảo vệ khỏi **time-of-check/time-of-use**: tài liệu có thể chuyển từ `DRAFT` sang `APPROVED` giữa lúc đọc và lúc ghi. Sử dụng giao dịch, khóa hoặc điều kiện cập nhật theo phiên bản/trạng thái tùy hệ thống; một lần kiểm tra không bảo đảm trạng thái mãi không đổi.

Nếu quyền chức năng không đạt, có thể từ chối trước khi truy xuất đối tượng, giảm chi phí và tránh vô tình lộ thông tin. Dù thứ tự các bước trong kiến trúc cụ thể có thể khác, thao tác phải luôn đi qua đủ các kiểm tra bắt buộc trước khi gây tác động.

## 5. Ví dụ Java 17+ chạy độc lập

Ví dụ Java thuần dưới đây làm rõ kết quả từ chối do **thiếu quyền chức năng** và từ chối do **thiếu quyền trên đối tượng**. Trong API công khai, không nhất thiết tiết lộ lý do chi tiết cho caller; reason code có thể ghi ở audit nội bộ.

Tạo tệp `FunctionObjectAuthorizationDemo.java`:

```java
import java.util.Set;

public class FunctionObjectAuthorizationDemo {

    enum Action { READ, EDIT, APPROVE }
    enum State { DRAFT, PENDING, APPROVED }
    enum Decision { ALLOW, DENY_FUNCTION, DENY_OBJECT }

    record Actor(
            String userId,
            String tenantId,
            Set<String> permissions,
            boolean enabled) {
        Actor {
            permissions = permissions == null
                    ? Set.of() : Set.copyOf(permissions);
        }
    }

    record Document(
            String id,
            String tenantId,
            String ownerId,
            String reviewerId,
            State state) {}

    static Decision authorize(Actor actor, Action action, Document document) {
        // Thiếu thông tin xác thực hoặc action hợp lệ -> fail closed.
        if (actor == null || action == null || !actor.enabled()
                || actor.userId() == null) {
            return Decision.DENY_FUNCTION;
        }

        // Bước 1: quyền dùng chức năng.
        String requiredPermission = switch (action) {
            case READ -> "document:read";
            case EDIT -> "document:edit";
            case APPROVE -> "document:approve";
        };
        if (!actor.permissions().contains(requiredPermission)) {
            return Decision.DENY_FUNCTION;
        }

        // Bước 2: quyền trên đối tượng cụ thể.
        if (document == null || actor.tenantId() == null
                || !actor.tenantId().equals(document.tenantId())) {
            return Decision.DENY_OBJECT;
        }

        boolean owner = actor.userId().equals(document.ownerId());
        boolean reviewer = actor.userId().equals(document.reviewerId());

        boolean objectAllowed = switch (action) {
            case READ -> owner || reviewer;
            case EDIT -> owner && document.state() == State.DRAFT;
            case APPROVE -> reviewer && !owner
                    && document.state() == State.PENDING;
        };

        return objectAllowed ? Decision.ALLOW : Decision.DENY_OBJECT;
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "alpha",
                Set.of("document:read", "document:edit", "document:approve"),
                true);
        Actor bob = new Actor("bob", "alpha",
                Set.of("document:read", "document:edit"), true);
        Actor ruth = new Actor("ruth", "alpha",
                Set.of("document:read", "document:approve"), true);
        Actor guest = new Actor("guest", "alpha",
                Set.of("document:read"), true);
        Actor eve = new Actor("eve", "beta",
                Set.of("document:read"), true);

        Document draft = new Document(
                "d42", "alpha", "alice", "ruth", State.DRAFT);
        Document pending = new Document(
                "d43", "alpha", "alice", "ruth", State.PENDING);

        System.out.println("owner-edits-own-draft="
                + authorize(alice, Action.EDIT, draft));
        System.out.println("editor-edits-other-draft="
                + authorize(bob, Action.EDIT, draft));
        System.out.println("viewer-tries-edit="
                + authorize(guest, Action.EDIT, draft));
        System.out.println("reviewer-approves-pending="
                + authorize(ruth, Action.APPROVE, pending));
        System.out.println("owner-approves-own="
                + authorize(alice, Action.APPROVE, pending));
        System.out.println("cross-tenant-read="
                + authorize(eve, Action.READ, draft));
        System.out.println("reviewer-approves-draft="
                + authorize(ruth, Action.APPROVE, draft));
        System.out.println("reviewer-reads-assigned="
                + authorize(ruth, Action.READ, draft));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac FunctionObjectAuthorizationDemo.java
java FunctionObjectAuthorizationDemo
```

Kết quả stdout:

```text
owner-edits-own-draft=ALLOW
editor-edits-other-draft=DENY_OBJECT
viewer-tries-edit=DENY_FUNCTION
reviewer-approves-pending=ALLOW
owner-approves-own=DENY_OBJECT
cross-tenant-read=DENY_OBJECT
reviewer-approves-draft=DENY_OBJECT
reviewer-reads-assigned=ALLOW
```

Phân tích hai kết quả dễ nhầm:

- Bob có `document:edit` giống Alice, nên **qua** bước chức năng nhưng **trượt** bước đối tượng do không phải owner. Hệ thống vẫn từ chối ghi.
- Guest là thành viên cùng tenant nhưng chỉ có `document:read`. Vì không có quyền chức năng sửa nên hệ thống từ chối ngay, bất kể chủ sở hữu và trạng thái đối tượng.

Hai quyết định `DENY_FUNCTION` và `DENY_OBJECT` được tách ra để quan sát cơ chế trong ví dụ. Đây không phải các mã lỗi HTTP mặc định của Spring Security. Trong ứng dụng thực, ta thường chuyển chúng thành phản hồi từ chối phù hợp, không trả chi tiết nhạy cảm về owner/tenant/reviewer.

## 6. Đặt hai lớp kiểm tra trong Spring Security

Spring Security cung cấp `Authentication`, `GrantedAuthority`, cơ chế request authorization, method security và điểm mở rộng chính sách. **Nó không thể tự biết một tài liệu thuộc ai** nếu ứng dụng chưa đưa thông tin đối tượng vào quá trình quyết định.

### 6.1. Cổng HTTP: quyền sử dụng chức năng

Với Spring MVC/Servlet, `SecurityFilterChain` có thể chặn các endpoint bằng `authorizeHttpRequests`. Đoạn sau nằm trong một lớp `@Configuration` có các import cần thiết; nó là **mảnh tích hợp Spring**, không phải chương trình Java độc lập:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/api/documents/*")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.PATCH, "/api/documents/*")
                .hasAuthority("document:edit")
            .requestMatchers(HttpMethod.POST, "/api/documents/*/approve")
                .hasAuthority("document:approve")
            .anyRequest().denyAll()
    ).build();
}
```

Các matcher trên minh họa bảo vệ thao tác **theo chức năng**. Lựa chọn matcher và cách tổ chức endpoint cần khớp thiết kế API thực tế; route bảo mật nào không khớp rule sẽ rơi vào `denyAll()`. Đây chưa phải lời giải cho quyền trên `/api/documents/d42`.

`hasAuthority("document:edit")` kiểm tra đúng chuỗi authority được cấp trong `Authentication`. Không mặc định mọi `ROLE_EDITOR` sẽ được tự đổi thành `document:edit`: việc ánh xạ role → permission phải được định nghĩa rõ tại nguồn cấp quyền hoặc policy.

### 6.2. Service/method: ranh giới đối tượng

Bật method security bằng `@EnableMethodSecurity` trong một lớp cấu hình. Sau đó có thể kiểm tra cả thao tác và đối tượng bằng `@PreAuthorize`:

```java
// Một method trong @Service do Spring quản lý.
// "documentAccess" là bean policy do ứng dụng tự định nghĩa.
@PreAuthorize("hasAuthority('document:edit') and " +
        "@documentAccess.canEdit(authentication, #documentId)")
public void editDocument(String documentId, EditDocumentCommand command) {
    documentRepository.updateDocument(documentId, command);
}
```

Trong đó `documentAccess.canEdit(authentication, documentId)` là phương thức **ứng dụng phải viết** để: đọc subject từ `Authentication`; nạp đúng document; kiểm tra tenant, owner, trạng thái và ngữ cảnh; sau đó trả boolean. `EditDocumentCommand` và `documentRepository` cũng là các thành phần minh họa cần hiện thực trong project.

Lưu ý kỹ thuật:

- Trong SpEL, `#documentId` phải có tên tham số truy cập được; dùng cấu hình biên dịch lưu tên tham số (ví dụ `-parameters`) hoặc đánh dấu tham số bằng cơ chế đặt tên tương ứng của Spring Security.
- Method security thường hoạt động qua Spring AOP proxy; **self-invocation** (method trong cùng bean gọi trực tiếp một method có annotation) có thể bỏ qua interceptor. Bảo vệ đúng ranh giới public service và các đường gọi khác.
- Nếu đã nạp tài liệu để phân quyền rồi lại nạp để ghi, cân nhắc race condition. Với lệnh thay đổi quan trọng, có thể chọn một service transaction tự nạp/kiểm tra/cập nhật cùng đối tượng và ràng buộc trạng thái khi ghi.
- `@PreAuthorize` nên là **cổng nhất quán**, nhưng không có nghĩa chỉ một annotation là đủ khi nhiều endpoint/job/consumer dùng chung nghiệp vụ.

### 6.3. Khi logic theo đối tượng cần nhiều dữ liệu

Một cách tổ chức rõ ràng là service thực hiện tuần tự: nạp tài nguyên có thẩm quyền → kiểm tra function permission → kiểm tra object policy → thực thi nghiệp vụ. Ví dụ **pseudocode**:

```text
editDocument(actor, documentId, change):
    requireAuthority(actor, "document:edit")
    document = repository.getDocument(documentId)
    requireSameTenant(actor, document)
    requireOwner(actor, document)
    requireState(document, DRAFT)
    repository.updateIfVersionAndStateMatch(document, change)
```

Đối tượng không tồn tại được xử lý riêng theo contract. Những điều kiện như `requireOwner` và `requireState` thuộc **quy tắc ứng dụng**, không phải Spring Security tự suy luận. Tùy kiến trúc có thể gói chúng thành bean policy, `AuthorizationManager` tùy biến hoặc lớp domain service; lựa chọn nào cũng phải bảo đảm tất cả đường đi đều được bảo vệ.

## 7. Phân quyền theo đối tượng cho danh sách, tìm kiếm và bulk API

Với `GET /api/documents`, không có một `{id}` duy nhất để kiểm tra. Cách an toàn là **giới hạn tập bản ghi được phép nhìn thấy ngay trong truy vấn**, rồi mới phân trang, đếm và trả kết quả.

Ví dụ, nếu chính sách đọc chỉ cho owner hoặc reviewer trong cùng tenant:

```sql
SELECT *
FROM documents
WHERE tenant_id = :tenantId
  AND (owner_id = :userId OR reviewer_id = :userId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
```

Trước khi chạy truy vấn, API vẫn phải kiểm tra quyền chức năng `document:read`. Các tham số `:tenantId`, `:userId` phải lấy từ subject đã xác thực và kiểm chứng, không lấy từ input tùy ý. Truy vấn chỉ là ví dụ biểu đạt chính sách, không tự xử lý các trường hợp chia sẻ, ACL, soft-delete hay phân quyền trường nếu sản phẩm còn các quy tắc đó.

Những điểm dễ sót:

- **Pagination/count:** nếu lọc đối tượng sau khi phân trang hoặc trả `totalCount` từ toàn bộ tenant, có thể làm sai kết quả và lộ thông tin.
- **Export/report/search:** việc có quyền `document:export` cũng không cho phép xuất dữ liệu ngoài tập tài nguyên được phép.
- **Bulk update/delete:** từng ID trong danh sách phải được kiểm tra hoặc toàn bộ lệnh phải có điều kiện ghi bảo đảm cùng chính sách. Cần định nghĩa rõ hành vi all-or-nothing hay partial success; không bỏ qua ID không hợp lệ một cách âm thầm.
- **Truy cập gián tiếp:** file attachment, URL tải xuống, ảnh thu nhỏ, audit view, thông báo, cache và tác vụ nền phải áp dụng cùng phạm vi truy cập.
- **Dữ liệu nhạy cảm theo trường:** có quyền đọc một tài liệu không nhất thiết được xem mọi trường của tài liệu. Nếu bài toán cần, có thêm lớp phân quyền theo property/field để kiểm soát nội dung phản hồi.

## 8. BFLA và BOLA: hai kiểu lỗ hổng khác nhau

### 8.1. Broken Function Level Authorization (BFLA)

**Tình huống:** người dùng bình thường có tài khoản hợp lệ nhưng gọi được `DELETE /api/users/u12` hoặc `POST /api/documents/d42/approve` vốn dành cho vai trò được cấp đặc quyền. UI có thể ẩn nút nhưng endpoint không kiểm tra authority.

- **Nguyên nhân:** phân quyền chỉ dựa trên giao diện; thiếu rule trên endpoint/service; matcher sai thứ tự hoặc quá rộng; chỉ kiểm tra `authenticated()` cho chức năng đặc quyền.
- **Khắc phục:** định nghĩa danh mục thao tác và authority tương ứng; bảo vệ ở server; dùng `denyAll`/mặc định từ chối; kiểm thử cả phương thức HTTP, route cũ, API nội bộ và chức năng quản trị.

### 8.2. Broken Object Level Authorization (BOLA)

**Tình huống:** Alice được phép gọi `GET /api/invoices/{id}` cho hóa đơn của mình. Cô đổi `{id}` thành hóa đơn của Bob và server vẫn trả dữ liệu vì chỉ kiểm tra `invoice:read`.

- **Nguyên nhân:** endpoint có kiểm tra chức năng nhưng bỏ qua owner, quan hệ được chia sẻ hoặc phạm vi tổ chức của **bản ghi đích**.
- **Khắc phục:** kiểm tra từng đối tượng theo subject + action + resource; lọc truy vấn phù hợp; duy trì tenant isolation tại nhiều lớp khi cần.

BFLA và BOLA thường xuất hiện **cùng nhau**. Ví dụ endpoint “xuất báo cáo khách hàng” cho phép bất kỳ user gọi (BFLA), rồi đọc mọi khách hàng ngoài tenant (BOLA). Sửa riêng một lớp vẫn để lại lỗ hổng ở lớp kia.

## 9. Kiểm thử thiết kế quyền theo cả hai chiều

Nên tạo **ma trận quyền** cho mỗi hành động nghiệp vụ quan trọng. Tối thiểu:

| Test case | Quyền chức năng | Quyền đối tượng | Kỳ vọng |
| --- | --- | --- | --- |
| Đúng authority, đúng owner/tenant/state | Có | Có | `ALLOW` |
| Không có authority nhưng là owner | Không | Có | `DENY` |
| Có authority nhưng khác owner | Có | Không | `DENY` |
| Có authority nhưng khác tenant | Có | Không | `DENY` |
| Có authority, đúng owner, sai trạng thái | Có | Không | `DENY` |
| Thiếu cả hai | Không | Không | `DENY` |
| Token/phiên không hợp lệ | Không xác thực | Bất kỳ | Từ chối từ bước xác thực |
| Tài nguyên không tồn tại | Có thể có | Không xác minh được | Trả lỗi theo API contract, không tiết lộ dữ liệu |
| Cùng quyền nhưng ID khác | Có | Thay đổi theo từng ID | Mỗi ID nhận đúng kết quả |

Kịch bản thực tế cần kiểm cả **HTTP/controller**, **service trực tiếp**, **danh sách**, **truy vấn đếm**, **batch**, và **job/message consumer** nếu các đường này tồn tại. Với một số chức năng, kiểm thử sự thay đổi trạng thái giữa check và write để tránh dùng quyền dựa trên trạng thái cũ.

Đừng chỉ test bằng một tài khoản admin có toàn quyền: nó không phát hiện sự khác nhau giữa thiếu quyền chức năng và thiếu quyền trên tài nguyên. Hãy dùng ít nhất hai subject cùng tenant, một subject tenant khác, hai object có owner khác nhau và các trạng thái khác nhau.

## 10. Sai lầm thường gặp

1. **“Đăng nhập rồi là được”:** `authenticated()` chỉ xác nhận danh tính, chưa cấp quyền thao tác hay quyền trên bản ghi.
2. **“Có role ADMIN thì bỏ qua mọi giới hạn”:** role có thể là **tenant admin** chứ không phải global admin. Cần ghi rõ scope của authority.
3. **“Dùng UUID ngẫu nhiên nên không cần kiểm tra owner”:** đoán khó không ngăn lộ ID từ đường dẫn, cache, log hoặc link chia sẻ.
4. **“Ẩn nút là đã bảo vệ chức năng”:** client không phải ranh giới tin cậy; phải chặn tại server.
5. **“Chỉ kiểm tra ở controller”:** method nội bộ, consumer và job có thể đi vòng qua controller.
6. **“Đã lọc sau khi lấy danh sách là đủ”:** count, pagination, cache và bước serialize có thể đã lộ dữ liệu.
7. **“Chỉ kiểm tra lúc bắt đầu tác vụ”:** đối tượng có thể chuyển trạng thái, đổi chủ hoặc bị thu hồi quyền trước khi ghi.
8. **“Client nói mình thuộc tenant nào thì tin”:** claim/body/header không được tin nếu chưa xác minh; cross-tenant boundary phải được áp dụng từ phía server.
9. **“Mọi request trả 403 là đủ”:** phải thiết kế rõ xử lý 401, 403, 404 và giới hạn thông tin trong lỗi/audit để không vô tình lộ sự tồn tại hoặc thuộc tính đối tượng.
10. **“Có một @PreAuthorize là xong”:** cần đúng tham số, đúng bean policy, proxy invocation, giao dịch và bảo vệ mọi đường truy cập.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Bob có `document:edit` nhưng không sở hữu `d42`. Có được sửa không?

**Không.** Bob đạt kiểm tra chức năng nhưng không đạt kiểm tra đối tượng (theo chính sách ví dụ ở mục 3).

**Câu 2.** Alice sở hữu `d42` nhưng không có `document:approve`. Có được duyệt nếu tài liệu đang `PENDING`?

**Không.** Quyền đối tượng/chủ sở hữu không thay thế quyền sử dụng chức năng. Hơn nữa, chính sách ví dụ còn cấm owner tự duyệt ngay cả khi được cấp authority.

**Câu 3.** API `GET /api/documents` đã có `hasAuthority('document:read')`. Có đủ để trả về mọi tài liệu không?

**Không.** Còn phải giới hạn tập bản ghi theo tenant, quan hệ owner/reviewer hoặc chính sách chia sẻ thực tế. Phân trang, count và export phải dựa trên cùng phạm vi được phép.

**Câu 4.** Kết quả `ALLOW` cho tài liệu `d42` có áp dụng mặc định cho `d43` không?

**Không.** Quyết định theo đối tượng là quyết định cho một resource cùng hành động/ngữ cảnh cụ thể; thuộc tính hai đối tượng có thể khác nhau.

**Ghi nhớ:** *được phép dùng chức năng* và *được phép dùng chức năng đó trên bản ghi cụ thể* là hai điều kiện bổ sung cho nhau. Đảm bảo cả hai được thực thi ở server trước khi đọc dữ liệu nhạy cảm hoặc thay đổi trạng thái.

## Tài liệu tham khảo

- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- OWASP API Security Top 10 (2023), API1 Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP API Security Top 10 (2023), API5 Broken Function Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/
