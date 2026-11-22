# Bộ dữ liệu kiểm thử đa người dùng, role, tenant và quan hệ chia sẻ

## 1. Mục tiêu của bài học

Trong hệ thống đa tenant, một yêu cầu được phép chỉ khi **principal đã xác thực**, **membership đúng tenant**, **role tại tenant**, **thuộc tính tài nguyên** và **quan hệ chia sẻ hợp lệ** cùng thỏa mãn chính sách. Một bài test chỉ có một user ADMIN và một document không thể phát hiện rò rỉ dữ liệu xuyên tenant, role được áp dụng nhầm phạm vi, hoặc chia sẻ nâng quyền sai.

Bài này hướng dẫn tạo một **test dataset có nhiều user, role, tenant và quan hệ chia sẻ**, xác định expected result độc lập với mã cần kiểm thử, rồi chạy ma trận authorization ở mức policy và HTTP. Trọng tâm thuộc chủ đề **Kiểm thử dữ liệu và chính sách** của module **Spring Security - authorization**.

Sau bài học, bạn có thể:
- Phân biệt user, membership, role, owner, visibility, resource state và ACL/share grant.
- Thiết kế fixture có trường hợp được phép, bị từ chối, tenant khác, grant hết hạn/thu hồi và role khác nhau ở từng tenant.
- Kiểm thử kết hợp RBAC (role), ABAC (tenant, trạng thái, thuộc tính), ReBAC (owner/share) cùng ranh giới tin cậy.
- Chứng minh quyết định từ chối không rò rỉ dữ liệu qua list/search/count hoặc tạo side effect ở database.
- Tái chạy test quyết định nhờ ID ổn định, thời gian cố định và dọn dữ liệu độc lập.

## 2. Mô hình và ranh giới tin cậy

| Thành phần | Dữ liệu ví dụ | Vai trò |
|---|---|---|
| Principal | u-alice, u-sam | Danh tính lấy từ Authentication; đăng nhập không tự trao quyền. |
| Tenant | t-a, t-b | Ranh giới sở hữu và cô lập dữ liệu. |
| Membership | (t-a, u-sam, EDITOR) | Một user có thể ở nhiều tenant với role khác nhau. |
| Document | D-A1, tenant=t-a, owner=u-alice | Resource có tenant, owner, visibility, state. |
| Share/ACL | D-A1 → u-carol, WRITE | Quyền trên một resource cụ thể; có người nhận và ngày hết hạn. |
| Action | READ, EDIT, SHARE, DELETE | Hành động cần kiểm tra độc lập, không gộp chung vào quyền “truy cập”. |

Phân tách ba kiểm tra bắt buộc:

1. **Authentication**: user là ai? Không có principal hợp lệ thì protected endpoint từ chối.
2. **Tenant membership**: user có membership hợp lệ tại tenant của document không? Role ADMIN tại t-b không có tác dụng ở t-a. Client gửi tenantId không chứng minh membership.
3. **Object/action authorization**: với đúng membership, xét role, owner, visibility, document state và grant còn hiệu lực. Một EDITOR cùng tenant không mặc nhiên được sửa mọi document riêng tư.

Nguồn tin cậy là principal xác thực và dữ liệu membership/resource/share được tra từ server/repository. Không tin ownerId, role, grantedBy hoặc tenantId trong request như bằng chứng quyền. Không suy tenant thật từ tiền tố ID “D-A”; đó chỉ là tên mẫu dễ đọc.

## 3. Đặc tả chính sách ví dụ

Ví dụ sử dụng ba role ADMIN, EDITOR, VIEWER; visibility PRIVATE/TENANT; trạng thái OPEN/ARCHIVED; permission chia sẻ READ/WRITE. Recipient phải là member **cùng tenant**. WRITE grant bao hàm READ nhưng **không nâng VIEWER thành EDITOR** và không tự có SHARE/DELETE. Grant có hiệu lực khi **now < expiresAt**; đúng tại thời điểm hết hạn phải bị từ chối.

| Action | Điều kiện sau khi xác minh membership đúng tenant |
|---|---|
| READ | Owner, hoặc ADMIN, hoặc document hiển thị TENANT, hoặc có READ/WRITE grant còn hạn. ARCHIVED vẫn đọc được. |
| EDIT | Document OPEN và actor là ADMIN, hoặc actor là EDITOR đồng thời là owner/có WRITE grant. VIEWER không được sửa. |
| SHARE | Document OPEN và actor là ADMIN hoặc EDITOR đồng thời là owner; khi cấp quyền phải kiểm tra recipient cùng tenant. |
| DELETE | Document OPEN và actor là ADMIN hoặc EDITOR đồng thời là owner. ARCHIVED bất biến trong mẫu này. |
| Bất kỳ action | Không có membership, sai tenant, document không tồn tại hoặc không đạt điều kiện → DENY. |

Không có quyền “ADMIN toàn cục” ngầm định. Chính sách trên là **quy ước nghiệp vụ của bài kiểm thử**, không phải mặc định tự có của Spring Security. Trước khi viết test, đội dự án cần chốt đặc tả tương ứng với sản phẩm thực tế. HTTP có thể dùng 403 cho thiếu quyền hoặc 404 để giấu sự tồn tại của document khác tenant; phải thống nhất contract. Bảng kiểm thử bên dưới dùng ALLOW/DENY độc lập với status HTTP.

## 4. Dataset được thiết kế theo nhiều chiều

Đặt **now = 2026-11-06T00:00:00Z** cố định cho toàn bộ test. ID, trạng thái, role và thời điểm hết hạn được seed cùng một baseline; không lấy thời gian thực làm oracle.

### 4.1. User và membership

| User | Tenant | Role | Mục đích |
|---|---|---|---|
| u-alice | t-a | EDITOR | Owner document riêng tư. |
| u-bob | t-a | VIEWER | Nhận READ và WRITE grant; thử giới hạn role. |
| u-carol | t-a | EDITOR | Owner document khác và recipient WRITE từ Alice. |
| u-diana | t-a | ADMIN | Quản trị viên riêng tenant A. |
| u-sam | t-a | EDITOR | Cùng user có role cao hơn ở tenant A. |
| u-erin | t-b | ADMIN | Thử ADMIN tenant B truy cập tài nguyên A. |
| u-frank | t-b | VIEWER | Recipient với grant hết hạn đúng biên. |
| u-sam | t-b | VIEWER | Cùng user có role thấp hơn ở tenant B. |

Có **7 user duy nhất, 8 membership, 2 tenant, 3 role**. Role phải được tra theo cặp (tenantId, userId). Nếu lưu role toàn cục trên user, một người như u-sam rất dễ được quyền sai tenant.

### 4.2. Document

| ID | Tenant | Owner | Visibility | State | Kịch bản chính |
|---|---|---|---|---|---|
| D-A1 | t-a | u-alice | PRIVATE | OPEN | Owner và recipient có quyền khác nhau. |
| D-A2 | t-a | u-carol | TENANT | OPEN | Mọi member A đọc được, không mặc nhiên sửa. |
| D-A3 | t-a | u-carol | PRIVATE | ARCHIVED | Đọc được khi có quyền, nhưng không được ghi. |
| D-B1 | t-b | u-erin | PRIVATE | OPEN | Kiểm thử expiry trên grant. |
| D-B2 | t-b | u-sam | PRIVATE | OPEN | Owner với role VIEWER chỉ được đọc. |

### 4.3. Quan hệ chia sẻ

| Grant | Document → Recipient | Permission | ExpiresAt (UTC) | Ý nghĩa |
|---|---|---|---|---|
| S1 | D-A1 → u-bob | READ | 2027-01-01T00:00:00Z | Bob được đọc, không sửa. |
| S2 | D-A1 → u-carol | WRITE | 2027-01-01T00:00:00Z | Carol EDITOR sửa được nhưng không SHARE tiếp. |
| S3 | D-A2 → u-bob | WRITE | 2027-01-01T00:00:00Z | VIEWER vẫn không được EDIT. |
| S4 | D-A3 → u-alice | WRITE | 2027-01-01T00:00:00Z | ARCHIVED vẫn chặn EDIT. |
| S5 | D-B1 → u-frank | READ | 2026-11-06T00:00:00Z | Chính xác tại expiry, READ bị từ chối. |

Trong hệ thống thật, grant nên có tenantId, documentId, recipientId, grantedBy, permission, expiresAt, trạng thái revoked hoặc cách xóa quan hệ, cùng audit timestamp. Khóa ngoại/kiểm tra giao dịch phải giữ document và recipient trong cùng tenant. **Không seed grant sai tenant vào database tích hợp** khi ràng buộc cấm nó; chỉ cố tình tiêm một grant giả vào pure unit test để xác nhận chính sách vẫn an toàn trước dữ liệu không hợp lệ.

### 4.4. Tại sao fixture này hữu ích?

- **Cùng resource, khác actor:** Alice, Bob, Carol, Diana, Erin trên D-A1 phơi bày khác biệt owner, recipient, admin và tenant.
- **Cùng actor, khác tenant:** u-sam ở A/B phơi bày lỗi áp role toàn cục.
- **Cùng grant WRITE, khác role:** Carol EDITOR sửa được D-A1; Bob VIEWER không sửa được D-A2.
- **Cùng quyền, khác trạng thái:** WRITE có tác dụng với D-A1 OPEN, không có với D-A3 ARCHIVED.
- **Cùng recipient, khác trạng thái quan hệ:** Carol đọc D-A1 trước revoke, bị từ chối sau revoke; Frank bị từ chối tại expiry.

Bộ dữ liệu nhỏ có đối chứng có giá trị hơn việc tạo ngẫu nhiên hàng nghìn bản ghi chỉ gồm case ALLOW.

## 5. Ma trận expected authorization

**Oracle phải xuất phát từ đặc tả mục 3**, không lấy kết quả của chính hàm đang được test làm expected value.

| # | Actor/role/tenant | Action | Resource | Expected | Lý do |
|---|---|---|---|---|---|
| 1 | Alice / EDITOR A | READ | D-A1 | ALLOW | Owner. |
| 2 | Alice / EDITOR A | EDIT | D-A1 | ALLOW | Owner + EDITOR + OPEN. |
| 3 | Bob / VIEWER A | READ | D-A1 | ALLOW | S1 READ còn hạn. |
| 4 | Bob / VIEWER A | EDIT | D-A1 | DENY | VIEWER không sửa. |
| 5 | Carol / EDITOR A | EDIT | D-A1 | ALLOW | S2 WRITE còn hạn. |
| 6 | Carol / EDITOR A | SHARE | D-A1 | DENY | Có WRITE nhưng không phải owner/admin. |
| 7 | Diana / ADMIN A | DELETE | D-A1 | ALLOW | ADMIN đúng tenant, OPEN. |
| 8 | Erin / ADMIN B | READ | D-A1 | DENY | Sai tenant dù là ADMIN. |
| 9 | Bob / VIEWER A | READ | D-A2 | ALLOW | TENANT visibility. |
| 10 | Bob / VIEWER A | EDIT | D-A2 | DENY | S3 WRITE không nâng VIEWER. |
| 11 | Alice / EDITOR A | EDIT | D-A2 | DENY | Không phải owner và không có WRITE grant. |
| 12 | Alice / EDITOR A | READ | D-A3 | ALLOW | S4 WRITE bao hàm READ. |
| 13 | Alice / EDITOR A | EDIT | D-A3 | DENY | ARCHIVED không cho mutation. |
| 14 | Frank / VIEWER B | READ | D-B1 | DENY | S5 hết hạn tại now. |
| 15 | Sam / VIEWER B | READ | D-B2 | ALLOW | Owner được đọc. |
| 16 | Sam / VIEWER B | EDIT | D-B2 | DENY | Owner không vượt role. |
| 17 | Sam / EDITOR A | READ | D-B2 | DENY | Membership A không có hiệu lực ở B. |
| 18 | Carol / EDITOR A | READ | D-A1 sau revoke S2 | DENY | Không còn quan hệ hợp lệ. |
| 19 | Không có membership | READ | D-A1 | DENY | Thiếu chủ thể đủ điều kiện. |
| 20 | Erin / ADMIN B + grant giả | EDIT | D-A1 | DENY | Tenant boundary chặn trước ACL. |

Luôn truyền membership đúng tenant dựa trên identity đã xác thực. Đừng để test “Sam là EDITOR” mà không nêu đó là membership A hay B.

## 6. Ví dụ Java 17 chạy độc lập: policy và 20 kiểm tra

Chương trình dùng enum, record, List và Instant; không cần Spring hoặc database. Lớp Membership trong ví dụ **được giả định là bản ghi server đã xác minh**, không phải đối tượng client có thể tự tạo. Hàm allow xử lý null cho case thiếu membership.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class AuthorizationDatasetDemo {
    enum Role { ADMIN, EDITOR, VIEWER }
    enum Visibility { PRIVATE, TENANT }
    enum State { OPEN, ARCHIVED }
    enum Permission { READ, WRITE }
    enum Action { READ, EDIT, SHARE, DELETE }

    record Membership(String userId, String tenantId, Role role) {}
    record Document(
            String id, String tenantId, String ownerId,
            Visibility visibility, State state) {}
    record Share(
            String documentId, String recipientId,
            Permission permission, Instant expiresAt) {}

    static boolean hasGrant(List<Share> shares, Document doc,
                            Membership actor, Permission needed, Instant now) {
        return shares.stream().anyMatch(s ->
                s.documentId().equals(doc.id())
                && s.recipientId().equals(actor.userId())
                && now.isBefore(s.expiresAt())
                && (s.permission() == needed
                    || (needed == Permission.READ
                        && s.permission() == Permission.WRITE)));
    }

    static boolean allow(Membership actor, Document doc, Action action,
                         List<Share> shares, Instant now) {
        if (actor == null || doc == null || action == null || now == null
                || !actor.tenantId().equals(doc.tenantId())) {
            return false;
        }

        boolean admin = actor.role() == Role.ADMIN;
        boolean editor = actor.role() == Role.EDITOR;
        boolean owner = actor.userId().equals(doc.ownerId());

        return switch (action) {
            case READ -> admin || owner
                    || doc.visibility() == Visibility.TENANT
                    || hasGrant(shares, doc, actor, Permission.READ, now);
            case EDIT -> doc.state() == State.OPEN
                    && (admin || (editor && (owner
                        || hasGrant(shares, doc, actor, Permission.WRITE, now))));
            case SHARE, DELETE -> doc.state() == State.OPEN
                    && (admin || (editor && owner));
        };
    }

    static void check(String name, Membership actor, Document doc,
                      Action action, List<Share> shares, Instant now,
                      boolean expected) {
        boolean actual = allow(actor, doc, action, shares, now);
        if (actual != expected) {
            throw new AssertionError(name + ": expected=" + expected
                    + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T00:00:00Z");
        Instant future = Instant.parse("2027-01-01T00:00:00Z");

        Membership alice = new Membership("u-alice", "t-a", Role.EDITOR);
        Membership bob = new Membership("u-bob", "t-a", Role.VIEWER);
        Membership carol = new Membership("u-carol", "t-a", Role.EDITOR);
        Membership diana = new Membership("u-diana", "t-a", Role.ADMIN);
        Membership samA = new Membership("u-sam", "t-a", Role.EDITOR);
        Membership erin = new Membership("u-erin", "t-b", Role.ADMIN);
        Membership frank = new Membership("u-frank", "t-b", Role.VIEWER);
        Membership samB = new Membership("u-sam", "t-b", Role.VIEWER);

        Document a1 = new Document(
                "D-A1", "t-a", "u-alice", Visibility.PRIVATE, State.OPEN);
        Document a2 = new Document(
                "D-A2", "t-a", "u-carol", Visibility.TENANT, State.OPEN);
        Document a3 = new Document(
                "D-A3", "t-a", "u-carol", Visibility.PRIVATE, State.ARCHIVED);
        Document b1 = new Document(
                "D-B1", "t-b", "u-erin", Visibility.PRIVATE, State.OPEN);
        Document b2 = new Document(
                "D-B2", "t-b", "u-sam", Visibility.PRIVATE, State.OPEN);

        List<Share> shares = List.of(
                new Share("D-A1", "u-bob", Permission.READ, future),
                new Share("D-A1", "u-carol", Permission.WRITE, future),
                new Share("D-A2", "u-bob", Permission.WRITE, future),
                new Share("D-A3", "u-alice", Permission.WRITE, future),
                new Share("D-B1", "u-frank", Permission.READ, now));

        check("owner read", alice, a1, Action.READ, shares, now, true);
        check("owner edit", alice, a1, Action.EDIT, shares, now, true);
        check("shared read", bob, a1, Action.READ, shares, now, true);
        check("viewer edit", bob, a1, Action.EDIT, shares, now, false);
        check("shared write", carol, a1, Action.EDIT, shares, now, true);
        check("recipient reshare", carol, a1, Action.SHARE, shares, now, false);
        check("tenant admin delete", diana, a1, Action.DELETE, shares, now, true);
        check("cross tenant admin", erin, a1, Action.READ, shares, now, false);
        check("tenant visible", bob, a2, Action.READ, shares, now, true);
        check("write cannot elevate viewer", bob, a2, Action.EDIT, shares, now, false);
        check("editor no grant", alice, a2, Action.EDIT, shares, now, false);
        check("archived readable", alice, a3, Action.READ, shares, now, true);
        check("archived immutable", alice, a3, Action.EDIT, shares, now, false);
        check("expiry boundary", frank, b1, Action.READ, shares, now, false);
        check("viewer owner read", samB, b2, Action.READ, shares, now, true);
        check("viewer owner edit", samB, b2, Action.EDIT, shares, now, false);
        check("role scoped to tenant", samA, b2, Action.READ, shares, now, false);

        List<Share> revoked = shares.stream()
                .filter(s -> !(s.documentId().equals("D-A1")
                        && s.recipientId().equals("u-carol")))
                .toList();
        check("revoked share", carol, a1, Action.READ, revoked, now, false);
        check("missing membership", null, a1, Action.READ, shares, now, false);

        List<Share> tampered = new ArrayList<>(shares);
        tampered.add(new Share("D-A1", "u-erin", Permission.WRITE, future));
        check("forged cross tenant grant",
                erin, a1, Action.EDIT, tampered, now, false);

        System.out.println("All checks passed.");
    }
}
~~~

Lưu file **AuthorizationDatasetDemo.java**, rồi chạy:

~~~bash
javac --release 17 AuthorizationDatasetDemo.java
java AuthorizationDatasetDemo
~~~

Stdout chính xác nếu tất cả assertion đạt:

~~~text
All checks passed.
~~~

**Giải thích logic:** kiểm tra tenant được thực hiện trước mọi grant/role; READ nhận visibility TENANT hoặc READ/WRITE grant còn hạn. EDIT cần OPEN và role đủ mạnh kết hợp owner/WRITE. SHARE/DELETE không phát sinh từ WRITE grant. Điều kiện now.isBefore(expiresAt) làm trường hợp đúng bằng expiry bị từ chối. Thu hồi S2 được mô phỏng bằng tập share mới không có quan hệ của Carol; dữ liệu giả mạo của Erin không vượt qua tenant boundary.

Đây là ví dụ chính sách, chưa bao gồm tra membership thật, repository, giao dịch, audit, bảo vệ đường ghi, hoặc concurrency. Những phần đó được triển khai trong ứng dụng Spring và database.

## 7. Áp dụng vào Spring Security và test HTTP

### 7.1. Luồng kiểm soát truy cập phía server

Đối với GET /api/tenants/{tenantId}/documents/{id}, hệ thống cần: lấy userId từ Authentication; tra membership theo **đúng tenantId + userId**; đọc document theo **tenantId + id**; lấy share của đúng tenant/document; chạy policy READ; chỉ chuyển document thành response sau ALLOW. Với POST/PUT/DELETE, kiểm tra đúng action trong transaction và kiểm chứng không có mutation nếu DENY.

Sơ đồ ngắn:

~~~text
Authentication → Membership(userId, tenantId)
                → Document(tenantId, documentId)
                → Share(documentId, recipientId, expiresAt)
                → Policy(action, role, owner, visibility, state, now)
                → ALLOW / DENY → HTTP + database outcome
~~~

Một đoạn service mang tính minh họa (không phải class độc lập, vì repository, mapper, exception và policy do ứng dụng định nghĩa):

~~~java
public DocumentView readDocument(
        String tenantId, String documentId, Authentication authentication) {
    String userId = authentication.getName();
    Membership membership = membershipRepository
            .findByTenantIdAndUserId(tenantId, userId)
            .orElseThrow(AccessDeniedException::new);
    Document document = documentRepository
            .findByTenantIdAndId(tenantId, documentId)
            .orElseThrow(DocumentNotFoundException::new);
    List<Share> shares = shareRepository
            .findByTenantIdAndDocumentId(tenantId, documentId);

    if (!policy.allow(membership, document, Action.READ,
                      shares, clock.instant())) {
        throw new AccessDeniedException("Document access denied");
    }
    return mapper.toView(document);
}
~~~

Có thể đặt kiểm tra ở @PreAuthorize thông qua policy bean hoặc AuthorizationManager, song annotation không tự suy ra tenant/ownership/share. Nếu query chỉ findById(documentId) mà thiếu tenantId thì phải sửa query; policy check không thay thế được data scoping của list/search/count.

### 7.2. Mô phỏng principal trong MockMvc

Trong Spring Boot test đã cấu hình MockMvc, seed database và spring-security-test, có thể kiểm tra ADMIN t-b không đọc D-A1. Ví dụ chọn contract **404 với resource ngoài tenant**:

~~~java
mockMvc.perform(get("/api/tenants/{tenantId}/documents/{id}", "t-a", "D-A1")
        .with(jwt().jwt(j -> j.subject("u-erin"))
                .authorities(new SimpleGrantedAuthority("SCOPE_documents:read"))))
    .andExpect(status().isNotFound());
~~~

Đây là đoạn test minh họa trong một lớp đã có import/fixture, không phải file chạy độc lập. Nếu sản phẩm quy định 403 cho cross-tenant, sửa expected status thành 403. Phải xác nhận truy vấn membership cho u-erin chỉ tìm thấy (t-b, ADMIN) nên không thể lấy document t-a. JWT mock chỉ tạo authentication trong kiểm thử, không kiểm tra chữ ký token với IdP thực.

Không dùng @WithMockUser(roles="ADMIN") như bằng chứng đã tạo tenant membership: annotation này không tự seed domain role, owner, ACL. Phân biệt authority như SCOPE_documents:read với role nghiệp vụ ở tenant: có scope JWT không có nghĩa có quyền trên mọi object.

### 7.3. Database và mutation

Ràng buộc nên bảo đảm:
- Membership duy nhất theo (tenant_id, user_id), role hợp lệ; thay role không vô tình ảnh hưởng tenant khác.
- Document thuộc một tenant và owner được xác minh theo quy tắc nghiệp vụ; query theo (tenant_id, id).
- Share gắn cùng tenant với document và recipient; không nhận grantedBy/ownerId từ client như dữ liệu đáng tin.
- Kiểm tra quyền SHARE của actor trước khi tạo, sửa, thu hồi grant; không cho user thường tự ghi ACL.
- Có index phù hợp với (tenant_id, document_id, recipient_id), cơ chế xác định grant hết hạn/revoked, và cache invalidation khi đổi role/revoke.
- Tránh race giữa authorization và mutation: kết hợp transaction, version/locking khi chính sách có thể đổi đồng thời.

Đối với test sửa/chia sẻ/xóa bị từ chối, chụp document và danh sách share **trước/sau** request, xác nhận không có thay đổi. Chỉ assert HTTP status là chưa đủ: ứng dụng có thể đã ghi xuống database rồi mới trả lỗi.

## 8. Các lớp kiểm thử nên có

| Lớp test | Fixture sử dụng | Bằng chứng cần kiểm tra |
|---|---|---|
| Pure unit | Membership/document/share/Clock cố định | 20 quyết định ALLOW/DENY đúng theo ma trận. |
| Repository | 2 tenant có document khác nhau, sharing riêng | Không có kết quả khác tenant từ detail/list/search/count; tenant predicate áp dụng cho pagination. |
| HTTP integration | Principal tương ứng + DB seed | Status đúng contract, body không tiết lộ document khác tenant; scope JWT không vượt policy. |
| Mutation | EDIT/SHARE/DELETE, revoke và cấp lại | ALLOW sửa đúng object; DENY không đổi dữ liệu. |
| Lifecycle | grant trước/đúng/sau expiry, đổi role, revoke | Quyền cập nhật tức thì, không dùng cache stale hay Clock thực ngoài tầm kiểm soát. |

Các ca mở rộng nếu sản phẩm hỗ trợ: recipient không còn membership, share lặp, đổi owner, chuyển tenant, owner rời tenant, nhiều role trên cùng tenant, link sharing, bulk download/export, event hoặc background job. Test cả trường hợp danh sách rỗng, dữ liệu bí mật bị lộ qua count/tổng, và object ID bị thay trong route để phát hiện IDOR (insecure direct object reference). Chỉ thêm trường hợp phù hợp đặc tả thực tế, tránh invent quyền không có.

Để fixture tái lập:
1. Tạo test factory/seed xác định và cố định thời gian bằng Clock injectable. Không phụ thuộc ngày chạy test, thứ tự test hay UUID random khó debug.
2. Trong mỗi test dùng baseline độc lập; rollback transaction hoặc reset DB/container. Không tái sử dụng dữ liệu đã mutate từ test trước.
3. Dùng ma trận expected thủ công làm oracle; đừng gọi policy trước rồi lấy output làm expected.
4. Khi lỗi, báo userId + tenantId + action + documentId + grantId + expected/actual; tránh log token/PII thật.
5. Kiểm tra authorization ở service/database và tất cả đường đi có thể trả tài nguyên; giao diện ẩn nút chỉ là UX, không phải hàng rào quyền.

## 9. Lỗi phổ biến

- **Một tenant duy nhất:** không thể phát hiện query thiếu tenant_id; thêm t-b với ADMIN và document riêng.
- **Role toàn cục:** u-sam EDITOR tại A vô tình được EDIT ở B; cần lookup theo cặp membership.
- **Cùng tenant = toàn quyền:** D-A2 TENANT cho mọi member READ, không cho họ EDIT.
- **WRITE share = SHARE/DELETE:** Carol có S2 chỉ sửa D-A1 trong role EDITOR, không tự chia sẻ tiếp.
- **WRITE share nâng VIEWER:** Bob có S3 nhưng vẫn bị từ chối EDIT.
- **Owner vượt role:** Sam VIEWER là owner D-B2 vẫn không được sửa theo chính sách đã định.
- **Thời gian động:** test expiry chập chờn; dùng Instant cố định và kiểm tra biên bằng expiresAt.
- **Chỉ kiểm tra status:** lệnh trả 403 vẫn có thể gây mutation; đọc lại DB.
- **Bỏ qua list/search/count:** tài nguyên từ tenant khác có thể lộ ở tổng số kết quả dù detail endpoint đã chặn.
- **Tin input tự khai của client:** tenant, role, owner và grantedBy phải đối chiếu server.
- **Grant hợp lệ về syntax nhưng sai tenant:** database phải chặn quan hệ sai, policy vẫn có tenant boundary.
- **Fixture rò trạng thái giữa các test:** test chạy độc lập sẽ sai; reset seed/rollback mỗi ca.

## 10. Checklist nghiệm thu

Dataset được coi là đủ để kiểm thử chính sách này khi có nhiều user, ít nhất hai tenant, role gắn với membership, tài nguyên PRIVATE/TENANT và OPEN/ARCHIVED, owner khác nhau, quan hệ READ/WRITE còn hạn/hết hạn/thu hồi, cùng ít nhất một user đa membership. Test phải có đối chứng ALLOW/DENY, cross-tenant ADMIN bị từ chối, VIEWER có WRITE không vượt role, data scoping ở query/HTTP, và không có side effect với lệnh bị từ chối. ID, Clock và baseline phải xác định để người khác chạy lại thu được cùng kết quả.

Điểm mấu chốt là cố tình đưa vào fixture những trường hợp **có vẻ đủ quyền** — ADMIN ở tenant khác, EDITOR có role ở tenant khác, VIEWER được chia sẻ WRITE, recipient có grant trên document ARCHIVED — để kiểm tra tenant boundary, role, quan hệ và trạng thái không thể bị bỏ qua.