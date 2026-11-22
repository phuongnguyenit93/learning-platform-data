# Tenant là ranh giới dữ liệu và quyền trong ứng dụng nhiều khách hàng

> **Chủ đề:** Spring Security – authorization · **Nhóm:** Cách ly tenant. Bài Knowledge này giải thích vì sao tenant (khách hàng/tổ chức sử dụng chung một nền tảng SaaS) phải là **ranh giới của cả dữ liệu lẫn quyết định phân quyền**, không chỉ một nhãn hiển thị hoặc tham số lọc UI. Bài tập trung vào Spring Boot Servlet + Spring Security 6.x, Java 17+, JPA/JDBC và thiết kế bảo mật dữ liệu; phần PostgreSQL Row-Level Security (RLS) là lớp bảo vệ bổ sung tùy hạ tầng. Đoạn mã dùng Spring được ghi rõ là chạy trong dự án đã có dependencies, còn ví dụ JDK thuần có thể chạy độc lập.

## 1. Sau bài học bạn cần làm được gì?

1. Định nghĩa tenant, membership, active tenant, principal, resource owner, authority và object-level permission; phân biệt ranh giới tenant với quyền trong nội bộ tenant.
2. Trình bày đường tin cậy từ HTTP/JWT → xác thực principal → xác minh membership → chọn active tenant → kiểm tra action → truy vấn resource theo tenant → kiểm tra business/ACL.
3. Không tin `X-Tenant-ID`, path `/tenants/{id}` hoặc `tenantId` trong JSON như bằng chứng quyền; coi chúng chỉ là **đề nghị chọn tenant** cần được xác minh bằng nguồn server đáng tin.
4. Thiết kế query/insert/update/delete luôn gắn tenant scope; biết vì sao `findById(id)` rồi chỉ kiểm tra sau đó có thể tạo lộ dữ liệu hoặc race.
5. So sánh ba cách lưu trữ: shared schema với cột `tenant_id`, schema riêng cho từng tenant, database riêng; hiểu vai trò và giới hạn của PostgreSQL RLS.
6. Áp dụng Spring Security URL/method security, policy membership và repository scoped; kiểm tra quyền tenant ở mọi đường gọi (HTTP, scheduled jobs, async, queue).
7. Ngăn rò rỉ qua cache, search, export, object storage, file upload, audit log, event, correlation, bulk operations và liên kết giữa nhiều bảng.
8. Viết test cross-tenant GRANT/DENY/NOT_FOUND, truy vấn danh sách, thao tác ghi, dữ liệu không có tenant, tái sử dụng connection và nested resource.
9. Nhận diện các lỗi “có quyền tính năng nhưng sai tenant”, “tenant do client khai được dùng trực tiếp”, “tenant context bị rò giữa thread pool”, “admin toàn cục không có giới hạn” và “RLS bị bypass bởi DB role”.

## 2. Tenant không chỉ là một cột dữ liệu

Một hệ thống quản lý tài liệu phục vụ hai khách hàng doanh nghiệp:

~~~text
SaaS platform
  |
  +-- Tenant alpha (Công ty A)
  |     +-- Alice: document:read, document:write
  |     +-- Document 101: "Kế hoạch A"
  |     +-- Project 20: "Dự án A"
  |
  +-- Tenant beta (Công ty B)
        +-- Bob: document:read
        +-- Document 201: "Kế hoạch B"
        +-- Project 30: "Dự án B"
~~~

Nếu Alice biết hoặc đoán đúng ID Document 201, ứng dụng **không được** trả dữ liệu của beta chỉ vì Alice đã đăng nhập và có authority `document:read`. Một câu lệnh sau là **không đủ**:

~~~java
@PreAuthorize("hasAuthority('document:read')")
public Document find(long id) {
    return repository.findById(id).orElseThrow();
}
~~~

`document:read` thể hiện một khả năng chung, chưa nói **tenant nào**, **resource nào**, **thời điểm nào**. Để chấp nhận yêu cầu, thường cần đồng thời:

~~~text
ALLOW =
  actor đã xác thực hợp lệ
  AND actor là thành viên có quyền tại active tenant
  AND action được policy cho phép ở tenant đó
  AND đối tượng thực sự thuộc tenant đã xác minh
  AND ACL/ownership/state nghiệp vụ (nếu có) cũng cho phép
~~~

Nếu một điều kiện bắt buộc thiếu bằng chứng, **không cấp quyền**. Thông báo lỗi gửi client phải theo API contract, tránh tiết lộ sự tồn tại tài liệu của tenant khác.

### 2.1. Một user có thể ở nhiều tenant

Alice có thể là nhân viên Công ty A và cộng tác viên Công ty B. **Principal Alice không đồng nghĩa active tenant cố định.** Nếu đang thao tác trong alpha, ứng dụng phải ghi/đọc theo alpha; nếu chuyển sang beta, phải xác minh membership và quyền cho beta **tại lúc chuyển/ở request tương ứng**.

~~~text
Alice authenticated (stable principal ID = user-17)
  memberships:
    alpha -> role EDITOR
    beta  -> role VIEWER
  active tenant selected: beta
  effective action: READ on beta, NOT WRITE on beta
~~~

Không được lấy role EDITOR của alpha rồi dùng cho beta. Chỉ vì tên authority chung là `ROLE_EDITOR` không có nghĩa nó áp dụng vô điều kiện cho mọi tenant. Có thể mô hình hóa bằng tenant-scoped roles/memberships hoặc custom `AuthorizationManager` tra chính sách theo tenant.

### 2.2. Tách bốn khái niệm

| Khái niệm | Ví dụ | Ai xác nhận? |
| --- | --- | --- |
| `principalId` | `user-17` | Authentication provider/identity directory |
| `requestedTenantId` | `alpha` trong URL hoặc header | Client **đề nghị**, không phải bằng chứng |
| `membership` | `user-17` là EDITOR của alpha, VIEWER của beta | Identity/membership store được server tin cậy |
| `resource.tenantId` | Document 101 thuộc alpha | DB/resource store có integrity constraint |

**Active tenant** là tenant được chọn **sau khi** xác minh membership, không phải một trường string bất kỳ được gán vào `ThreadLocal` từ client.

### 2.3. Ranh giới tenant khác object authorization

Hai user đều thuộc alpha nhưng Document 101 chỉ có ACL READ cho Alice. Khi Bob cũng là thành viên alpha, Bob **vẫn có thể bị từ chối** với Document 101 nếu chính sách có object-level ACL/ownership. Tenant scope là điều kiện cần, không tự thay thế các rule nội bộ tenant.

Ngược lại, một ACE ACL nhầm cấp READ cho user alpha trên Document beta cũng **không được** ghi đè ranh giới tenant. Với tài nguyên nhạy cảm, kết hợp tenant check bắt buộc với ACL, ví dụ:

~~~text
allOf(
    authenticated,
    membershipInResourceTenant,
    actionAllowedInActiveTenant,
    resourceAclAllowsAction
)
~~~

Nếu dùng `AuthorizationManagers.allOf(...)` với custom manager có thể trả `null` (abstain), cần nhớ fallback và thứ tự đánh giá. Điều kiện tenant bắt buộc phải trả DENY khi không thể xác minh, **không** trả abstain rồi vô tình để các check khác GRANT.

## 3. Mô hình đe dọa: “lộ chéo tenant” xảy ra như thế nào?

### 3.1. IDOR / Broken Object Level Authorization

Người dùng beta gửi:

~~~http
GET /api/tenants/beta/documents/101
Authorization: Bearer [token của Bob]
~~~

Document 101 thật ra thuộc alpha. Nếu controller bỏ qua tenant trong URL và gọi `repository.findById(101)`, dữ liệu alpha có thể bị lộ. Ngay cả khi đoạn code sau đó kiểm tra tenant, exception message hoặc log trước bước check đã có thể tiết lộ title/owner.

### 3.2. Mass assignment và forged tenant

~~~json
{
  "title": "Secret",
  "tenantId": "victim-tenant",
  "ownerId": "someone-else"
}
~~~

Nếu API tạo Document chỉ việc `new Document(body.tenantId, ...)`, attacker có thể chèn tài liệu vào tenant không thuộc quyền hoặc tạo mối liên kết trái phép. Với request tạo, hãy chọn tenant từ **context đã xác minh**; owner/creator từ authenticated principal hoặc policy delegation hợp lệ.

### 3.3. Cross-tenant query trong export/search

Endpoint danh sách có thể lọc `tenant_id`, nhưng tác vụ export dùng query khác không lọc; search index trả cả tenant; file backup/report truy cập bằng token toàn cục. Phân quyền đúng ở một controller không bảo vệ mọi data path.

### 3.4. Connection/thread reuse

Một request alpha đặt `tenantContext.set(alpha)` trong `ThreadLocal`, nhưng code không xóa; worker servlet/async tái sử dụng thread cho beta. Query sau đọc nhầm alpha. Tương tự, RLS tenant session variable không được reset ở connection pool có thể giữ context cũ.

### 3.5. Cross-tenant reference

Một Comment thuộc tenant beta nhưng `document_id` trỏ vào Document của alpha. Nếu foreign key chỉ tham chiếu ID, DB vẫn có thể cho phép liên kết chéo ngay cả khi từng bảng có `tenant_id` riêng. Đây là lý do cần constraint tenant-aware, không chỉ filter trong repository.

### 3.6. Elevated administrator

Một support agent có quyền toàn cục có thể cần hỗ trợ khách hàng, nhưng quyền break-glass **không phải mặc định cho mọi request**. Nên có quy trình xác nhận tenant cụ thể, thời gian giới hạn, reason/ticket, audit, least privilege và kiểm tra trước khi xem dữ liệu.

## 4. Chuỗi tin cậy cho một request

~~~text
Request GET /api/tenants/alpha/documents/101
    |
    v
(1) Authentication filter:
    validate Basic/OIDC/JWT/session credential
    -> principal user-17, issuer/audience/signature hợp lệ
    |
    v
(2) Tenant selection:
    requested tenant "alpha" từ route
    -> CHỈ là selector, chưa đáng tin
    |
    v
(3) Membership/tenant policy:
    user-17 có membership active trong alpha?
    user-17 có quyền document:read tại alpha?
    -> trusted ActiveTenantContext(alpha, user-17, read)
    |
    v
(4) Repository:
    SELECT ... WHERE id=101 AND tenant_id='alpha'
    -> chỉ dữ liệu alpha mới có thể trả
    |
    v
(5) Object/business policy:
    owner/ACL, trạng thái publish, retention, classification
    |
    v
(6) Response:
    chỉ thông tin được phép; không lộ tài nguyên ngoài tenant
~~~

**Không đảo thứ tự theo cách nguy hiểm:** gọi query toàn cục, nạp Document beta, log tất cả trường rồi mới làm membership check. Cũng không nên chỉ check membership alpha ở controller rồi để service công khai gọi được từ scheduler mà không còn ràng buộc tenant.

### 4.1. Header, subdomain, path và token

Tenant có thể được chọn từ:
- Path: `/api/tenants/{tenantId}/...`.
- Host: `alpha.example.com`.
- Header: `X-Tenant-ID: alpha`.
- Token claim chứa tenant đang hoạt động.
- Server-side session active tenant sau bước switch có xác minh.

**Mọi giá trị do client điều khiển là input không tin cậy cho tới khi xác minh.** Host header cũng cần được reverse proxy/ingress xác nhận; tránh tin `X-Forwarded-Host` tùy tiện. Signed JWT claim cần verify chữ ký, `iss`, `aud`, thời hạn và nguồn issuer tin cậy. Token có tenant claim không tự cấp quyền tất cả object trong tenant.

### 4.2. Multi-issuer authentication khác data isolation

Spring Security OAuth2 Resource Server có thể sử dụng `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` cho nhiều issuer **đã được tin cậy**. Đây là lớp chọn chiến lược xác thực token, **không tự đảm bảo** query luôn lọc tenant. Không lấy issuer do token tự khai rồi tải JWK URL bất kỳ; phải kiểm tra allow-list/trusted tenant configuration.

Tương tự, một issuer có thể cấp token cho nhiều tenant; không giả định `iss` = `tenant_id` trong domain. Hợp đồng ánh xạ issuer, principal, tenant và membership thuộc ứng dụng/identity provider và phải kiểm thử.

## 5. Chọn mô hình lưu trữ nhiều tenant

| Mô hình | Điểm mạnh | Rủi ro và yêu cầu bảo vệ |
| --- | --- | --- |
| **Một DB, một schema, mọi bảng có `tenant_id`** | Vận hành đơn giản, shared migrations, quản lý chi phí | Phải lọc tất cả access paths; rủi ro thiếu WHERE tenant; có thể dùng RLS bổ sung |
| **Một DB, schema riêng mỗi tenant** | Ranh giới namespace rõ, backup/migration theo schema | Chọn schema đúng, không tin string schema từ request; tránh rò ở connection pool, quản lý schema migrations |
| **DB riêng mỗi tenant** | Cách ly storage/credential/backup tốt hơn, dễ đáp ứng một số yêu cầu compliance | Routing datasource, secret rotation, migrations trên nhiều DB, cost, job/admin cross-tenant; không tự đảm bảo app authorization |
| **Hybrid** | Tenant nhạy cảm DB riêng, phần lớn shared | Phức tạp routing và observability; tenant move phải kiểm soát nhất quán |

Không có mô hình nào tự biến API thành an toàn. Một DB riêng giúp giảm blast radius khi credential bị lộ, nhưng code có thể routing nhầm datasource; shared DB với RLS có thể rất mạnh nếu DB role và tenant session context đúng. Quyết định phụ thuộc mức độ cách ly, quy mô tenant, chi phí, compliance và kỹ năng vận hành.

### 5.1. Shared-table phải có tenant_id trong dữ liệu

Ví dụ:

~~~sql
CREATE TABLE tenant (
    id VARCHAR(40) PRIMARY KEY,
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE document (
    tenant_id VARCHAR(40) NOT NULL,
    id BIGINT NOT NULL,
    title VARCHAR(180) NOT NULL,
    owner_id VARCHAR(120) NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id) REFERENCES tenant(id)
);

CREATE TABLE document_comment (
    tenant_id VARCHAR(40) NOT NULL,
    id BIGINT NOT NULL,
    document_id BIGINT NOT NULL,
    content VARCHAR(1000) NOT NULL,
    PRIMARY KEY (tenant_id, id),
    FOREIGN KEY (tenant_id, document_id)
        REFERENCES document(tenant_id, id)
);
~~~

**Composite foreign key** ngăn Comment của beta trỏ tới Document của alpha **ngay trong DB**. Nếu muốn một `id` globally unique thay vì per-tenant ID, vẫn có thể thêm `UNIQUE(tenant_id, id)` để tạo composite FK và query scope. Không tạo FK chỉ trên `document.id` rồi cho rằng tenant của hai hàng tự khớp.

### 5.2. Chỉ số và uniqueness cũng cần tenant-aware

Email, slug, project code hoặc invoice number có thể chỉ cần unique **trong cùng tenant**. Khi đó:

~~~sql
CREATE UNIQUE INDEX document_title_unique_per_tenant
    ON document(tenant_id, title);
~~~

Đây chỉ là ví dụ nếu business thật sự yêu cầu title unique; thông thường title được phép trùng. Với khóa danh mục, dùng `UNIQUE(tenant_id, local_key)` thay vì unique global không cần thiết. Ngược lại, một stable global principal ID có thể phải unique xuyên tenant theo identity model.

Nên có index phục vụ `WHERE tenant_id = ? AND id = ?` và các truy vấn danh sách tenant; không chạy query scan toàn bộ dữ liệu lớn rồi filter ở Java memory.

### 5.3. Tenant lifecycle

Khi onboard tenant:
- Tạo tenant identity với status PENDING/ACTIVE/SUSPENDED.
- Cấp membership ban đầu qua quy trình đáng tin, không tự chấp nhận owner ID trong body.
- Provision quota, namespace, encryption key/secret và retention policy theo design.
- Chỉ ACTIVE sau khi schema/ACL/policy/resources sẵn sàng.
- Suspend tenant phải chặn cả HTTP, background jobs và data exports; không chỉ khóa UI.
- Tenant deletion/offboarding cần quyết định retention, backups, audit legal hold, object storage và cache purge theo contract.

Tenant ID nên ổn định và không chứa dữ liệu dễ nhầm/không phù hợp để làm identifier; display name có thể đổi mà tenant ID không đổi.

## 6. Phân quyền phải gắn với active tenant

### 6.1. Trường hợp authority toàn cục và per-tenant

Ví dụ Alice có `document:read` toàn cục ở account, nhưng membership cho phép:
- alpha → EDITOR
- beta → VIEWER

Ở alpha, Alice có thể đọc/ghi nếu policy ROLE_EDITOR cho phép. Ở beta, Alice chỉ được đọc. Nếu hệ thống chỉ check `hasAuthority('document:write')` chung, nó có thể vô tình cho phép WRITE ở beta. Vì thế hoặc:
1. Lưu role/permission theo membership, query theo active tenant tại điểm authorize; hoặc
2. Phát token chứa permission tenant-scoped và có quy trình xác minh cập nhật/thu hồi; vẫn check resource tenant; hoặc
3. Kết hợp global feature authority với per-tenant membership và action policy (mẫu đơn giản bên dưới).

**Bài demo sử dụng lựa chọn (3)**: authority là cổng tính năng; membership là cổng tenant. Demo cho member cùng tenant được đọc mọi tài liệu nếu có global read authority; production có thể thêm ACL per-object.

### 6.2. Contract của TenantMembershipPolicy

Một policy dùng được ở nhiều service có thể có hàm:

~~~java
void requireAccess(Authentication authentication,
                   String requestedTenant,
                   String requiredAction);
~~~

Nó phải:
- Xác minh principal đã authenticated và không phải anonymous.
- Xác minh requested tenant có cú pháp/ID hợp lệ và ACTIVE.
- Lấy membership từ identity directory/repository phía server.
- So role/permission **trong requested tenant**, không trộn với tenant khác.
- Nếu hết hạn membership, tenant suspended, record thiếu hoặc remote policy service lỗi → fail closed/exception có xử lý rõ.
- Trả một context **đã được xác minh** hoặc ném `AccessDeniedException`.
- Ghi audit tối thiểu cho thao tác nhạy cảm mà không tiết lộ metadata tenant khác.

Không dùng `@PreAuthorize("hasAuthority('ROLE_USER')")` đơn thuần làm bằng chứng một user thuộc tenant. Authority role có thể là global hoặc session-wide và không thể tự hiện diện “đúng tenant” nếu model không thiết kế.

### 6.3. Vai trò của URL và method security

`SecurityFilterChain` có thể yêu cầu authentication và các điều kiện route-level. `@PreAuthorize` bảo vệ service ở mức method; domain service cần tenant scope dù được gọi từ controller, message listener hoặc batch. Để giảm rủi ro bypass, đặt chính sách tenant tại application service/data access, không chỉ trong MVC argument resolver.

Nếu có custom `AuthorizationManager<RequestAuthorizationContext>`, nó có thể kiểm tra tenant path trước khi request tới controller. Tuy nhiên **vẫn cần lọc resource** khi query; một user là member alpha không được tải một row beta bằng một ID alpha-looking.

## 7. Spring Boot example: membership + scoped repository + method security

Ví dụ này cố ý dùng **in-memory repository** để tập trung vào authorization và không lẫn với transaction/JPA/RLS. Nó là ứng dụng Spring Boot Servlet hoàn chỉnh khi đặt vào dự án có dependencies đúng; dữ liệu và mật khẩu chỉ dùng cho demo. API:

~~~text
GET  /api/tenants/{tenantId}/documents
GET  /api/tenants/{tenantId}/documents/{id}
POST /api/tenants/{tenantId}/documents
~~~

- `alice` có `document:read` + `document:write`, member alpha và beta.
- `bob` có `document:read`, chỉ member beta.
- `viewer` thiếu `document:read`, member alpha.
- Document 1 thuộc alpha, Document 2 thuộc beta.
- URL tenant là selector **phải qua membership check**.
- Repository chỉ trả record có `tenantId` khớp.

Lưu thành `src/main/java/demo/tenant/TenantBoundaryApplication.java`:

~~~java
package demo.tenant;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class TenantBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantBoundaryApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(a -> a
                        .requestMatchers("/api/tenants/**").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // CSRF không bị tắt; POST cần CSRF khi chính sách yêu cầu.
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read", "document:write")
                    .build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read")
                    .build());
        // {noop} chỉ để học; production cần encoder an toàn.
    }
}

record Document(long id, String tenantId,
                String creatorId, String title) {
}

record NewDocument(@NotBlank @Size(max = 100) String title) {
}

@Component
class TenantMemberships {
    // Fixture ở server: client không thể tự sửa Map này.
    private final Map<String, Set<String>> members = Map.of(
            "alice", Set.of("alpha", "beta"),
            "bob", Set.of("beta"),
            "viewer", Set.of("alpha"));

    void requireMember(Authentication actor, String tenant) {
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Authentication required");
        }
        if (tenant == null
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")
                || !members.getOrDefault(actor.getName(), Set.of())
                            .contains(tenant)) {
            throw new AccessDeniedException("Tenant access denied");
        }
    }
}

@Component
class DocumentStore {
    private final ConcurrentMap<Long, Document> rows =
            new ConcurrentHashMap<>(Map.of(
                    1L, new Document(1L, "alpha", "alice", "Budget A"),
                    2L, new Document(2L, "beta", "bob", "Budget B")));
    private final AtomicLong nextId = new AtomicLong(10L);

    Optional<Document> findWithinTenant(String tenant, long id) {
        Document row = rows.get(id);
        return Optional.ofNullable(row)
                .filter(d -> d.tenantId().equals(tenant));
    }

    List<Document> listWithinTenant(String tenant) {
        return rows.values().stream()
                .filter(d -> d.tenantId().equals(tenant))
                .sorted(Comparator.comparingLong(Document::id))
                .toList();
    }

    Document insertWithinTenant(String trustedTenant,
                                String creator, String title) {
        long id = nextId.getAndIncrement();
        Document row = new Document(id, trustedTenant, creator, title);
        rows.put(id, row);
        return row;
    }
}

@Service
class DocumentService {
    private final TenantMemberships memberships;
    private final DocumentStore store;

    DocumentService(TenantMemberships memberships, DocumentStore store) {
        this.memberships = memberships;
        this.store = store;
    }

    private Authentication actor() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Document read(String tenant, Long id) {
        memberships.requireMember(actor(), tenant);
        // Lookup gắn tenant. Sai tenant hoặc không tồn tại cùng là 404.
        return store.findWithinTenant(tenant, id)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @PreAuthorize("hasAuthority('document:read')")
    public List<Document> list(String tenant) {
        memberships.requireMember(actor(), tenant);
        return store.listWithinTenant(tenant);
    }

    @PreAuthorize("hasAuthority('document:write')")
    public Document create(String tenant, NewDocument command) {
        Authentication authenticated = actor();
        memberships.requireMember(authenticated, tenant);
        // Không có tenantId/creatorId từ body.
        return store.insertWithinTenant(
                tenant, authenticated.getName(), command.title());
    }
}

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Document get(@PathVariable("tenantId") String tenant,
                 @PathVariable("id") Long id) {
        return service.read(tenant, id);
    }

    @GetMapping
    List<Document> list(@PathVariable("tenantId") String tenant) {
        return service.list(tenant);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    Document create(@PathVariable("tenantId") String tenant,
                    @Valid @RequestBody NewDocument request) {
        return service.create(tenant, request);
    }
}
~~~

### 7.1. Dependencies cho Spring Boot 3.x

Đặt trong `build.gradle` của dự án đã có Spring Boot Gradle plugin, dependency management, Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là một đoạn `dependencies`, **không phải file build.gradle hoàn chỉnh**. Có thể tạo project qua Spring Initializr. Trên Unix chạy `./gradlew bootRun`, trên Windows chạy `gradlew.bat bootRun`. Nếu dùng Spring Boot 4, cần kiểm tra lại package/dependency test/MockMvc theo phiên bản; bài này định hướng Spring Boot 3.x.

### 7.2. Vì sao tách ba lớp?

- `SecurityFilterChain` xác thực route để người chưa đăng nhập không truy cập.
- `DocumentService` là **Spring bean được method-security proxy bảo vệ**. `@PreAuthorize` kiểm tra quyền tính năng trước khi vào body; `TenantMemberships` xác minh tenant do caller chọn, rồi repository lọc tenant.
- `DocumentStore` là ranh giới dữ liệu; cả `read` lẫn `list` có `tenant`; `create` dùng tenant đã được xác minh, không lấy tenant từ body.

Trong demo, `TenantMemberships` chỉ lưu membership, chưa biểu diễn role khác nhau theo tenant. Do Alice có global `document:write`, cô ấy được ghi trong cả alpha lẫn beta. Nếu policy của Alice ở beta chỉ là VIEWER, phải thay `requireMember` bằng `requirePermission(actor, tenant, "document:write")` hoặc custom `AuthorizationManager` dùng membership scoped theo action. **Không sao chép demo này vào production nếu tenant-scoped roles là yêu cầu.**

### 7.3. Vì sao lookup phải nằm trong phạm vi tenant?

~~~java
// ĐƯỜNG ĐÚNG: query/resource scope bị giới hạn bởi tenant.
store.findWithinTenant(tenant, id);

// ĐƯỜNG SAI: nạp dữ liệu mọi tenant rồi mới hy vọng kiểm tra.
store.findById(id);
~~~

Một repository JPA thường dùng:

~~~java
// Trích đoạn Spring Data JPA, cần entity/repository đã định nghĩa.
Optional<DocumentEntity> findByTenantIdAndId(
        String tenantId, Long id);

Page<DocumentEntity> findByTenantId(
        String tenantId, Pageable pageable);
~~~

Với bulk update/delete, dùng điều kiện tenant và kiểm tra số bản ghi bị ảnh hưởng:

~~~java
// Sơ đồ SQL - chỉ cập nhật tài nguyên trong tenant đã xác minh.
UPDATE document
SET title = :title
WHERE tenant_id = :tenantId AND id = :documentId;
~~~

Nếu 0 hàng được cập nhật, có thể là sai tenant hoặc không tồn tại; không chạy retry `UPDATE WHERE id = ?` không còn tenant. Với `@Modifying`/JPA, kiểm tra return row count và transaction. Nếu mutation cần owner/ACL, thêm predicate hoặc policy kiểm tra dưới transaction/locking phù hợp để tránh TOCTOU.

### 7.4. Các điểm cố ý chưa có trong demo

In-memory store không có persistent transaction, DB tenant constraints, ACL per-document, role membership thay đổi theo thời gian, audit, pagination hay rate limit. Cần bổ sung cho ứng dụng thật:
- Persistent member registry theo tenant/action, tenant ACTIVE state, stable IDs.
- Owner/ACL/classification/state checks khi resource nhạy cảm.
- Transaction + SQL tenant predicate ở mọi read/write path.
- Unique key, composite foreign key, RLS/database permissions nếu phù hợp.
- Audit + monitoring cross-tenant access và repeated 403/404 probing.
- Cache keys theo tenant, file storage policy, scheduled job context.

## 8. MockMvc integration tests: chứng minh không lộ dữ liệu

Test phải qua Spring context và Security Filter Chain; không chỉ `new DocumentService(...)` vì có thể bỏ qua `@PreAuthorize`. Với test Spring Boot 3.x, tạo `src/test/java/demo/tenant/TenantBoundaryApplicationTest.java`:

~~~java
package demo.tenant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.everyItem;
import static org.hamcrest.Matchers.is;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantBoundaryApplicationTest {
    @Autowired MockMvc mvc;

    @Test
    void aliceReadsAlphaDocument() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/1")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenantId").value("alpha"))
                .andExpect(jsonPath("$.title").value("Budget A"));
    }

    @Test
    void bobCannotSelectAlpha() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/1")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void bobCannotReadAlphaIdViaBetaRoute() throws Exception {
        mvc.perform(get("/api/tenants/beta/documents/1")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isNotFound());
    }

    @Test
    void bobReadsDocumentWithinBeta() throws Exception {
        mvc.perform(get("/api/tenants/beta/documents/2")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tenantId").value("beta"));
    }

    @Test
    void alphaListContainsOnlyAlphaRows() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[*].tenantId",
                        everyItem(is("alpha"))));
    }

    @Test
    void missingFeatureAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/1")
                    .with(httpBasic("viewer", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousIsRejectedByBasicEntryPoint() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/1"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void bobCannotCreateWithoutWriteAuthority() throws Exception {
        mvc.perform(post("/api/tenants/beta/documents")
                    .with(httpBasic("bob", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Attempt\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCanCreateOnlyInSelectedMemberTenant()
            throws Exception {
        mvc.perform(post("/api/tenants/alpha/documents")
                    .with(httpBasic("alice", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"New Alpha Doc\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.tenantId").value("alpha"))
                .andExpect(jsonPath("$.creatorId").value("alice"));
    }

    @Test
    void aliceCannotSelectUnknownTenantForCreate()
            throws Exception {
        mvc.perform(post("/api/tenants/gamma/documents")
                    .with(httpBasic("alice", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Forbidden Doc\"}"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Ghi chú test:** `@AutoConfigureMockMvc` trong Spring Boot 3.x tích hợp các filter khi cấu hình chuẩn. `httpBasic(...)` gửi Basic credentials, còn `csrf()` thêm CSRF token cho POST theo cơ chế Spring Security Test. Các test này **không** chứng minh production SQL row-scoping hoặc database RLS: chúng chứng minh đường HTTP → service → in-memory scoped store.

Để chạy:

~~~bash
./gradlew test
~~~

Hoặc `gradlew.bat test` trên Windows.

### 8.1. Một khác biệt bảo mật quan trọng giữa 403 và 404

- Bob chọn `alpha` dù không có membership → 403 trong demo, vì selector tenant bị bác.
- Bob là member beta nhưng tra Document 1 thuộc alpha qua `/beta/documents/1` → 404, vì scoped lookup không thấy record trong beta.
- Người chưa authenticated → 401 với Basic entry point.
- Bob thiếu `document:write` → 403.

Không có một quy tắc HTTP cứng duy nhất cho mọi sản phẩm; ứng dụng có thể chủ động trả 404 thay 403 để chống resource/tenant enumeration, miễn nhất quán và không tiết lộ metadata. **Điều không được phép thay đổi là dữ liệu tenant khác không được trả về.**

### 8.2. Kiểm thử regression do thiếu tenant filter

Một mutation test hữu ích: cố tình đổi `findWithinTenant` thành `rows.get(id)` rồi chạy `bobCannotReadAlphaIdViaBetaRoute`. Test phải đỏ vì Bob có thể nhận dữ liệu alpha từ route beta. Nếu không đỏ, test suite chưa bảo vệ ranh giới dữ liệu.

Tương tự, xóa `memberships.requireMember(actor(), tenant)` thì test `bobCannotSelectAlpha` phải đỏ. Xóa `@PreAuthorize` hoặc không bật `@EnableMethodSecurity` thì test `missingFeatureAuthorityIsDenied` và test POST thiếu write phải đỏ. Đây là cách kiểm tra chất lượng test authorization, không chỉ trạng thái “HTTP 200”.

## 9. PostgreSQL RLS: phòng tuyến bổ sung tại database

Shared-table model có thể dùng PostgreSQL Row-Level Security để DB tự áp predicate trên từng row. Đây là một **lớp defense-in-depth**, không thay cho authentication, membership, ACL, domain validation hay cách cấp DB role đúng.

Ví dụ schema tách riêng để giải thích RLS:

~~~sql
CREATE TABLE document_rls (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL
);

ALTER TABLE document_rls ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_rls FORCE ROW LEVEL SECURITY;

CREATE POLICY document_rls_select
ON document_rls FOR SELECT
USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY document_rls_insert
ON document_rls FOR INSERT
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY document_rls_update
ON document_rls FOR UPDATE
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY document_rls_delete
ON document_rls FOR DELETE
USING (tenant_id = current_setting('app.tenant_id', true));
~~~

`current_setting('app.tenant_id', true)` trả tenant context của DB session hoặc NULL nếu chưa được thiết lập (với cấu hình/phiên bản liên quan); phép so sánh với NULL không trả true nên không tự mở dữ liệu. Nếu tenant context bị set sai, RLS **có thể cho kết quả sai** vì DB tin giá trị được cung cấp — đó là lý do app phải xác minh context trước khi set.

### 9.1. Đặt tenant context theo transaction, không để rò connection pool

~~~sql
BEGIN;
SELECT set_config('app.tenant_id', 'alpha', true);
SELECT id, tenant_id, title FROM document_rls ORDER BY id;
COMMIT;
~~~

Tham số thứ ba `true` cho `set_config` nghĩa là **local to the current transaction**. Trong Java/JDBC, dùng PreparedStatement/bind parameter để truyền tenant đã được membership policy xác minh; không nối tenant ID chưa xác thực thành câu SQL. Không dùng `SET` ở session level rồi để connection trở lại pool với tenant cũ.

Nếu transaction bị mở trễ hơn lúc set tenant context, hoặc JDBC call đi qua connection khác, RLS có thể không thấy context — điều này thường gây deny/empty result, nhưng không được sửa bằng cách tắt RLS. Cần tích hợp tenant setting với transaction manager và kiểm thử trên cùng connection.

### 9.2. RLS chỉ có tác dụng với role và policy phù hợp

Tài liệu PostgreSQL nhấn mạnh:
- Superuser hoặc role mang `BYPASSRLS` **bypass** row-level policies.
- Owner của bảng thường bypass trừ khi dùng `FORCE ROW LEVEL SECURITY`.
- `TRUNCATE` và một số thao tác schema không bị row policy kiểm soát như `SELECT/UPDATE/DELETE/INSERT`.
- Cần cấp SQL `GRANT` phù hợp; RLS không tự cấp quyền thao tác bảng.

Do đó production application DB role không nên là superuser hoặc có BYPASSRLS. Tách migration/admin DB role khỏi runtime role. Kiểm thử bằng **đúng runtime DB credentials**, không chạy test với owner/admin rồi tưởng RLS đã bảo vệ.

### 9.3. Giới hạn quan trọng của tenant session variable

Nếu attacker có thể thực thi SQL tùy ý với app DB role, họ có thể cố `set_config('app.tenant_id', 'beta', true)` trước khi query. Một custom GUC do application tự đặt không phải phép chứng minh cryptographic “người dùng thuộc beta”. RLS ở ví dụ là defense-in-depth chống code quên WHERE tenant khi **application trusted context** được đặt đúng, không phải cơ chế chống mọi loại SQL injection nếu DB role được phép tự đổi tenant context.

Dùng prepared statements, tránh arbitrary SQL execution, least privilege, review SECURITY DEFINER functions và chọn kiến trúc mạnh hơn khi tenant threat model yêu cầu attacker có thể kiểm soát SQL execution.

### 9.4. WITH CHECK tránh insert/update sang tenant khác

`USING` kiểm soát hàng được nhìn/đụng tới trong SELECT/UPDATE/DELETE; `WITH CHECK` kiểm tra trạng thái hàng **sau INSERT/UPDATE** được phép tạo. Nếu thiếu WITH CHECK ở policy phù hợp, có thể để một tài khoản cập nhật `tenant_id` làm di chuyển row ngoài ý muốn, tùy sự kết hợp chính sách. Luôn test UPDATE `SET tenant_id='beta'` từ transaction alpha phải bị từ chối.

### 9.5. RLS không thay thế composite foreign key

Một comment beta tham chiếu document alpha bằng ID không tự trở thành hợp lệ chỉ vì RLS cho thấy comment beta. Cần ràng buộc dữ liệu tenant-aware, và lưu ý kiểm tra toàn vẹn khóa ngoại của PostgreSQL có ngữ nghĩa đặc biệt so với row policy. Thiết kế schema composite FK vẫn cần thiết để tránh liên kết chéo tenant.

## 10. Hibernate @Filter và schema routing: tránh nhầm lẫn

Có thể dùng Hibernate filter, multi-tenancy support hoặc Spring Data query method để đính tenant. Nhưng:
- `@Filter` cần được bật đúng session và đúng những mapping/query liên quan; không tự giả định mọi native SQL hoặc bulk DML đều được lọc.
- Custom repository, JDBC template, native query, search DSL và stored procedure có thể bỏ qua cơ chế query scoping của ORM.
- Routing datasource/schema theo ThreadLocal cần cleanup an toàn khi connection/pool/async thay đổi.
- `@Where` hoặc soft-delete predicate không thay một chính sách tenant có context người dùng.
- Bất cứ thao tác nâng quyền tạm thời để chạy migration/admin job phải có kiểm soát, không mở một global “bypass tenant filter” cho request thông thường.

**Phân lớp:** method/AuthorizationManager xác định **ai được làm gì**; repository/RLS xác định **dữ liệu nào thực sự vào phạm vi**. Dùng cả hai khi rủi ro leakage đáng kể.

## 11. Java 17 độc lập: chứng minh tenant boundary mà không cần Spring

Chương trình sau dùng JDK thuần, mô phỏng membership, action authority, tenant-scoped resource lookup và owner rule. Mục đích là học sự khác biệt giữa:
- DENY_TENANT: actor không thuộc tenant được chọn.
- DENY_ACTION: actor thiếu quyền đọc tính năng.
- NOT_FOUND: ID không có trong tenant được phép (có thể tồn tại ở tenant khác).
- DENY_OBJECT: trong cùng tenant nhưng object owner policy không cho phép.
- ALLOW: mọi điều kiện cùng đạt.

Lưu thành `TenantBoundaryDemo.java`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class TenantBoundaryDemo {
    record User(String name, Set<String> tenants,
                Set<String> authorities) {}

    record Document(long id, String tenant, String owner, String title) {}

    static final Map<Long, Document> DATA = Map.of(
            1L, new Document(1L, "alpha", "alice", "Budget A"),
            2L, new Document(2L, "beta", "bob", "Budget B"),
            3L, new Document(3L, "alpha", "carol", "Plan C"));

    static String read(User user, String requestedTenant, long id) {
        if (user == null || requestedTenant == null
                || !user.tenants().contains(requestedTenant)) {
            return "DENY_TENANT";
        }
        if (!user.authorities().contains("document:read")) {
            return "DENY_ACTION";
        }

        Document doc = DATA.get(id);
        if (doc == null || !doc.tenant().equals(requestedTenant)) {
            // Không lộ tên/owner/tenant thật của record khác tenant.
            return "NOT_FOUND";
        }
        if (!doc.owner().equals(user.name())) {
            return "DENY_OBJECT";
        }
        return "ALLOW:" + doc.title();
    }

    static int countWithinTenant(String tenant) {
        return (int) DATA.values().stream()
                .filter(d -> d.tenant().equals(tenant))
                .count();
    }

    public static void main(String[] args) {
        User alice = new User("alice",
                Set.of("alpha", "beta"), Set.of("document:read"));
        User bob = new User("bob",
                Set.of("beta"), Set.of("document:read"));
        User viewer = new User("viewer",
                Set.of("alpha"), Set.of("profile:read"));

        System.out.println("alice-alpha-1=" +
                read(alice, "alpha", 1L));
        System.out.println("alice-beta-2=" +
                read(alice, "beta", 2L));
        System.out.println("bob-alpha-1=" +
                read(bob, "alpha", 1L));
        System.out.println("bob-beta-1=" +
                read(bob, "beta", 1L));
        System.out.println("bob-beta-2=" +
                read(bob, "beta", 2L));
        System.out.println("viewer-alpha-1=" +
                read(viewer, "alpha", 1L));
        System.out.println("alice-alpha-99=" +
                read(alice, "alpha", 99L));
        System.out.println("missing-tenant=" +
                read(alice, null, 1L));
        System.out.println("alpha-document-count=" +
                countWithinTenant("alpha"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 TenantBoundaryDemo.java
java TenantBoundaryDemo
~~~

**stdout chính xác:**

~~~text
alice-alpha-1=ALLOW:Budget A
alice-beta-2=DENY_OBJECT
bob-alpha-1=DENY_TENANT
bob-beta-1=NOT_FOUND
bob-beta-2=ALLOW:Budget B
viewer-alpha-1=DENY_ACTION
alice-alpha-99=NOT_FOUND
missing-tenant=DENY_TENANT
alpha-document-count=2
~~~

**Chú ý:** Demo thuần Java thêm owner policy nên Alice không đọc được Document beta của Bob dù có membership beta. Spring Boot demo ở mục 7 **chỉ kiểm tra membership + authority** (không có owner ACL) và sẽ cho Alice đọc Document beta; hai demo được ghi rõ **mức policy khác nhau**, không phải kết quả mâu thuẫn của cùng một implementation. Trong production, xác định object-level ACL cần hay không và giữ policy thống nhất ở mọi đường đi.

## 12. Tenant không được thất lạc khi xử lý ngoài request

### 12.1. @Async và ThreadLocal

`SecurityContextHolder` trong ứng dụng Servlet thường giữ context trên thread đang thực thi. `@Async` đổi executor thread và không tự chuyển mọi state; nếu app dùng custom `TenantContextHolder` dựa trên `ThreadLocal` cũng phải coi đây là ranh giới rõ ràng.

Không dùng `MODE_INHERITABLETHREADLOCAL` với thread pool như một “bản vá” tự động: thread tái sử dụng có thể mang tenant của caller khác. Khi cần, dùng executor/context propagation đã được kiểm soát, capture tại submit, cài trong worker và **dọn/khôi phục trong finally**. Dù đã chuyển context, worker nên xác minh tenant/membership và tính hợp lệ của job theo contract hiện tại, nhất là task chờ lâu.

### 12.2. Queue, scheduled job và outbox

Một message/job cần metadata tối thiểu:

~~~json
{
  "jobType": "GENERATE_REPORT",
  "tenantId": "alpha",
  "requestedBy": "user-17",
  "resourceId": "project-20",
  "correlationId": "job-821"
}
~~~

Đây là dữ liệu job do server tạo sau authorization, **không phải** nguyên `SecurityContext` serialize. Worker ở process khác phải xác minh message publisher, tenant ACTIVE, actor/service identity và action được phép; không tin arbitrary tenantId trong message đến từ client hoặc queue ít tin cậy.

Scheduled batch chạy qua nhiều tenant cần vòng lặp định tuyến rõ ràng:
- Chọn tenant từ registry tin cậy.
- Gán resource scope/DB connection cho **một tenant mỗi lần**.
- Không dùng global admin token cho mọi truy vấn nếu có thể dùng service identity least privilege.
- Khi kết thúc mỗi task, reset context/cache/connection.
- Audit tenant, actor/service identity, resource, outcome và correlation ID.

### 12.3. Tenant offboarding trong async jobs

Nếu tenant alpha bị suspend sau khi job đã enqueue nhưng trước khi execute, một snapshot cũ không tự bảo đảm permission còn hiệu lực. Đặt điểm re-check trước khi đọc/ghi dữ liệu nhạy cảm; queue retry/dead letter không được đổi sang tenant default khi tenant ID thiếu.

## 13. Cache, files, search và observability cũng là ranh giới tenant

### 13.1. Cache key phải bao gồm scope

Phản ví dụ:

~~~java
@Cacheable("document")
public Document getDocument(Long id) { ... }
~~~

Nếu ID trùng giữa tenant hoặc quyền phụ thuộc tenant, key `id` không đủ. Ví dụ key khái niệm:

~~~text
document:v2:tenant=alpha:id=101
document:v2:tenant=beta:id=101
~~~

Với cache **kết quả quyết định quyền**, còn cần actor, permission/action, policy version hoặc invalidation phù hợp; không cache “allowed=true for document 101” rồi reuse cho Bob. Trong Spring Cache, thiết kế method signature nhận **trustedTenantId** tường minh và key theo tenant, không dùng raw unverified path value làm identity duy nhất.

### 13.2. File/object storage

Đường lưu file có thể chứa tenant prefix:

~~~text
tenants/alpha/documents/101/report.pdf
tenants/beta/documents/201/report.pdf
~~~

Nhưng prefix **không tự là authorization**. Cần kiểm tra DB resource tenant + ACL trước khi sinh presigned URL, cấu hình IAM/storage ACL theo nguyên tắc tối thiểu, thời gian URL ngắn và tránh cho client tự chọn arbitrary object key. Không nhận `fileKey` trong request rồi nối vào đường dẫn không có kiểm tra tenant/ownership.

### 13.3. Search index và analytics

Truy vấn Elasticsearch/OpenSearch, search/vector store hoặc analytics warehouse phải lọc tenant ngay ở query hoặc security layer được hỗ trợ; đừng lấy top 100 kết quả toàn hệ thống rồi xóa kết quả sai tenant trong Java vì có thể:
- Lộ document ID/title qua log/metrics.
- Trả số đếm/hit count/timing ám chỉ sự tồn tại tenant khác.
- Làm pagination/recall sai.
- Lộ dữ liệu qua highlights/embedding/chunk metadata.

Nếu dùng vector retrieval cho RAG, mọi chunk/document phải gắn tenant scope và authorization filter; không dựa vào prompt “chỉ trả dữ liệu tenant alpha” làm hàng rào.

### 13.4. Logs, traces và audit

Audit event nên ghi trusted tenant ID, stable actor ID, object type+ID, action, decision và correlation ID. Không ghi token, raw credentials, dữ liệu tài liệu nhạy cảm. Khi multi-tenant ops dashboard, bản thân audit/search UI cũng phải áp tenant scope, trừ người có quyền điều tra được kiểm soát.

Log chỉ có `userId` mà không có tenant khiến điều tra khó phân biệt Alice đọc Document 101 của alpha hay beta. Tuy nhiên không ghi `requestedTenantId` chưa xác minh như thể đã authenticated tenant; nên tách `requestedTenant` và `authorizedTenant` nếu cần forensic trace.

### 13.5. Webhook và callback

Webhook payload gửi ra ngoài phải được xác minh target subscription thuộc tenant, URL được lưu/duyệt an toàn và data được scope. Một endpoint “notify all tenants” không được tái dùng cache/output của tenant trước; thêm tenant id vào event/outbox và dedupe keys, đồng thời kiểm soát replay/correlation.

## 14. Tenant scope trong mutation và giao dịch

### 14.1. Read trước write không tự bảo đảm atomic

Một anti-pattern:

~~~java
Document doc = repository.findById(id).orElseThrow();
if (!doc.getTenantId().equals(tenant)) throw new AccessDeniedException(...);
doc.setTitle(newTitle);
repository.save(doc);
~~~

Giữa lần đọc và lần ghi, tenant/ownership có thể đổi hoặc actor bị thu hồi quyền. Với mutation rủi ro cao, dùng transaction, optimistic/pessimistic locking hoặc câu UPDATE có cả tenant/policy predicates:

~~~sql
UPDATE document
SET title = :newTitle,
    version = version + 1
WHERE tenant_id = :trustedTenant
  AND id = :documentId
  AND version = :expectedVersion;
~~~

Kiểm tra số hàng bị cập nhật; 0 hàng có thể là không tồn tại trong tenant hoặc concurrent update. Nếu owner/ACL là điều kiện bắt buộc, cần bảo vệ tại cùng boundary truy cập/ghi, hoặc kiểm tra có khóa thích hợp; không chỉ dựa trên controller check ở t1.

### 14.2. Unique constraint và foreign keys phải bảo toàn tenant

Một insert xuyên tenant có thể xảy ra từ luồng CSV import hoặc background task dù REST controller đã an toàn. Composite unique/FK như phần 5 cung cấp defense-in-depth. Với nhiều bảng, join điều kiện đúng là:

~~~sql
SELECT d.id, c.content
FROM document d
JOIN document_comment c
  ON c.tenant_id = d.tenant_id
 AND c.document_id = d.id
WHERE d.tenant_id = :trustedTenant;
~~~

Không join chỉ trên `document_id` khi ID không globally unique hoặc khi nghiệp vụ yêu cầu cùng tenant; đây là nguy cơ cross-tenant join.

### 14.3. Tenant-aware event và outbox

Một outbox event phải ghi tenant cùng object/action, không lấy tenant từ thread-local vào lúc consumer chạy sau commit. Publisher/consumer phải xác minh ACL/tenant tại điểm phù hợp, không để message từ alpha được xử lý bằng datasource/namespace beta.

### 14.4. Các trường hợp quyền xuyên tenant có chủ đích

Có những use case hợp lệ như vendor support hoặc chia sẻ một resource giữa tổ chức:
- Thiết kế **explicit sharing object** hoặc delegation với nguồn gốc, tenant source/target, permission, thời hạn, consent/approval và audit.
- Không “đánh lừa” bằng cách xóa `WHERE tenant_id=?` hoặc cho user có multi-tenant membership rồi đọc toàn bộ DB.
- Nếu bản ghi được chuyển tenant, đó là workflow riêng với kiểm tra cả source và destination, transactional consistency, ACL migration, caches và audit.
- Không để child resource hoặc ACL parent của tenant khác được tham chiếu chỉ do client gửi ID.

## 15. Các lỗi thiết kế phổ biến

### Lỗi 1 — Coi tenant như metadata hiển thị

`tenant_id` xuất hiện trong JSON nhưng query theo `id` không có tenant predicate. Sửa ở repository/data layer và test cross-tenant lookup.

### Lỗi 2 — Tin URL/header tenant ngay lập tức

Client đổi `/alpha/` thành `/beta/`. Nếu server dùng nó làm `trustedTenantId` không check membership, leak xảy ra. Hãy xác minh người dùng là member, tenant ACTIVE và action policy đúng.

### Lỗi 3 — Chỉ có role chung, không kiểm tra tenant-scoped permission

Alice là ADMIN của alpha nhưng VIEWER của beta. `hasRole('ADMIN')` không tự trả lời ở tenant nào. Dùng role membership theo tenant, resource tenant và action.

### Lỗi 4 — Filter ở UI hoặc controller thôi

Hidden button hoặc controller check không bảo vệ scheduler, export, repository gọi từ code khác. Đặt enforcement ở service và data access.

### Lỗi 5 — Load global entity rồi trả sau khi check

`repository.findById(id)` toàn DB có thể lộ metadata, log, timing và làm predicate dễ quên. Query `findByTenantIdAndId` và thiết kế 404/403 nhất quán.

### Lỗi 6 — Update/delete chỉ theo id

`DELETE FROM document WHERE id=:id` hoặc `UPDATE ... WHERE id=:id` có thể đụng tenant khác. Luôn kèm trusted tenant, ACL/policy và kiểm tra row count.

### Lỗi 7 — Join/FK không có tenant

Comment beta trỏ Document alpha, hoặc join làm trộn dữ liệu. Thiết kế composite FK/unique và join theo tenant.

### Lỗi 8 — “RLS bật rồi thì ai cũng không thể vượt”

DB owner/superuser/BYPASSRLS có thể vượt; runtime role và transaction tenant setting có thể sai. Test với DB credentials thật, `FORCE ROW LEVEL SECURITY` phù hợp và role không bypass.

### Lỗi 9 — Dùng SET session-level với connection pool

Request alpha set tenant và trả connection về pool; beta dùng lại connection. Chọn transaction-local setting, cleanup và test reuse.

### Lỗi 10 — Tenant ThreadLocal không clear

Thread servlet/executor giữ tenant từ task trước. Dùng scope/finally, explicit tenant parameters hoặc context propagation được kiểm chứng; tránh global static current tenant.

### Lỗi 11 — Cache key thiếu tenant

Cùng document ID hoặc authority snapshot được tái sử dụng giữa alpha/beta. Scope cache keys và invalidation, không cache decision toàn cục.

### Lỗi 12 — Export/search bỏ predicate

API GET by ID an toàn nhưng export/analytics/search không lọc. Test tất cả đường đọc dữ liệu, cả file storage và search index.

### Lỗi 13 — Reparent/move dữ liệu qua tenant không kiểm soát

Đổi tenant ID của Document mà không cập nhật ACL, parent, FK, search/cache/object storage dẫn đến quyền sai. Thiết kế workflow migration riêng có audit và rollback/compensation.

### Lỗi 14 — Chỉ trả 403 cho cross-tenant nhưng log title thật

Server đọc Document beta, log trước khi deny Alice; dữ liệu vẫn bị rò vào log hoặc trace. Scope query và minimization ở mọi lớp.

### Lỗi 15 — Tin JWT tenant claim không kiểm chữ ký/issuer

Dữ liệu claim chưa được xác thực hoặc `iss` không nằm danh sách trusted issuers có thể bị giả mạo. Sử dụng JWT validation đúng, `aud`/expiry và membership policy.

### Lỗi 16 — Tenant không hoạt động vẫn được job chạy

HTTP đã khóa tenant nhưng job chạy queue cũ. Xác minh trạng thái tenant và identity tại worker, không dùng context snapshot vô thời hạn.

### Lỗi 17 — Không kiểm soát internal admin bypass

Một support endpoint có `permitAll` hoặc admin token toàn quyền mà thiếu reason, tenant selection và audit. Dùng scope, approval/break-glass và monitoring.

### Lỗi 18 — Nhầm 404 với không tồn tại toàn cục

Scoped query không tìm thấy Document ID 101 trong beta; có thể nó tồn tại trong alpha. Không truy vấn toàn cục để “giải thích 404” cho client; response nhất quán và không lộ tồn tại tenant khác.

## 16. Ma trận QA và test hiệu năng an toàn

| Ca kiểm thử | Kết quả mong muốn |
| --- | --- |
| Alice authenticated, alpha member, alpha Document, quyền READ | Cho phép nếu object policy cũng đồng ý |
| Alice authenticated, beta không có membership | DENY tenant |
| Bob member beta, truy ID thuộc alpha qua beta | 404/no data; không lộ owner/title/tenant thật |
| User thiếu feature authority trong tenant hợp lệ | DENY action |
| Alice editor alpha, viewer beta | WRITE alpha hợp lệ, WRITE beta bị chặn |
| Requested tenant null, unknown, suspended | Fail closed |
| Resource.tenantId null hoặc sai type | Bị loại/không được cấp quyền, data repair có kiểm soát |
| Client cố post tenantId/ownerId khác | Server bỏ qua/reject, không insert cross-tenant |
| List/search/export/bulk APIs | Mọi row thuộc tenant đã xác minh |
| UPDATE/DELETE với id tenant khác | 0 row, không thay đổi dữ liệu |
| Composite FK comment/doc khác tenant | DB từ chối |
| Một user có nhiều membership | Tenant switching chỉ đổi sau khi xác minh quyền riêng |
| Cross-tenant share được phê duyệt | Chỉ resource/action/thời hạn có delegation rõ |
| Role/tenant status thay đổi | Cache và token theo freshness policy, revoke hiệu lực đúng |
| Cache key thiếu tenant (mutation test) | Suite phải phát hiện contamination |
| Async worker reuse | Không giữ tenant user trước sau task |
| DB connection pool reuse | SET LOCAL/transaction setting không rò alpha→beta |
| RLS policy missing, runtime app role | Default deny và no BYPASSRLS theo thiết kế |
| SQL injection/thao tác tuỳ ý | Không cho thay trusted tenant context/đọc ngoài scope |
| File download/presigned URL | Chỉ URL cho object tenant đã authorize |
| Search/vector index | Tenant filter trước retrieval, không leak highlights/counts |
| Audit log | Actor + trusted tenant + resource + action, không token |
| Monitoring | 403/404 probing và access anomalies được phát hiện |
| Concurrency | Tenant reassignment/role revoke không tạo TOCTOU leak |
| Backup/restore/offboarding | Không trộn/khôi phục sai tenant, retention đúng |

### 16.1. Negative testing quan trọng hơn happy path đơn thuần

Một suite chỉ kiểm Alice đọc Document alpha **không kiểm được ranh giới tenant**. Phải cố tình dùng:
- User beta với ID alpha hợp lệ.
- User alpha với ID beta hợp lệ.
- Token của user multi-tenant nhưng role thấp hơn ở tenant đang chọn.
- Tenant bị suspend sau khi token phát hành.
- Quan hệ comment→document cross-tenant, file storage key tùy ý.
- Cache đã warm ở alpha trước rồi request beta cùng ID.
- Connection pool sử dụng theo thứ tự alpha→beta→alpha.
- Async job của alpha lỗi giữa chừng trước khi worker nhận job beta.

Bảo đảm những bài test này chạy trong CI và nhất là sau khi thêm repository/native query, cache hoặc migration mới.

## 17. Bài tập tự luyện

**Câu 1 — User có quyền document:read là đủ chưa?**

Alice có `document:read` và là member alpha. Khi Alice gửi `/api/tenants/beta/documents/201`, nên cho xem không?

**Đáp án:** Không nếu Alice không có membership/permission trong beta. Authority tính năng không thay điều kiện tenant và tài nguyên.

**Câu 2 — Sửa URL tenant có thể tạo quyền không?**

Bob chỉ thuộc beta, tự đổi `X-Tenant-ID` hoặc path thành alpha. Server có nên dùng alpha làm trusted tenant context không?

**Đáp án:** Không. Tenant selector không đáng tin; cần tra membership trong nguồn server, tenant status và action scoped.

**Câu 3 — Có RLS rồi có cần code kiểm tra membership?**

RLS dùng `tenant_id = current_setting('app.tenant_id', true)`. Một controller lấy header client, gọi `set_config` mà không check membership. Đủ an toàn không?

**Đáp án:** Không. RLS đang dùng context không đáng tin; attacker có thể chọn tenant khác. App phải xác minh trước và dùng DB role/transaction phù hợp.

**Câu 4 — Bob là beta member, yêu cầu GET beta/101, trong DB 101 thuộc alpha. Nên trả về gì?**

**Đáp án:** Query `WHERE tenant_id='beta' AND id=101` không tìm thấy và thường trả 404; tuyệt đối không trả metadata của alpha. Hợp đồng HTTP có thể chọn mã khác nhưng không tiết lộ cross-tenant resource.

**Câu 5 — Tenant scope có thay ACL không?**

Alice và Carol cùng là member alpha. Document 101 chỉ chia sẻ cho Alice. Carol có được đọc nhờ member alpha không?

**Đáp án:** Không nếu policy yêu cầu object ACL/owner. Tenant scope là điều kiện cần, không phải quyền tự động trên từng object.

**Câu 6 — Vì sao composite foreign key quan trọng?**

Một comment có `tenant_id='beta'` và `document_id=101`, nhưng Document 101 thuộc alpha. FK chỉ theo `document_id` có thể hợp lệ không?

**Đáp án:** Có thể hợp lệ nếu ID tồn tại và FK chỉ tham chiếu ID. FK kép `(tenant_id,document_id)` tới `(tenant_id,id)` ngăn liên kết cross-tenant khi key/constraint được khai báo nhất quán.

**Câu 7 — Worker async đang xử lý beta mà thấy tenant alpha là lỗi gì?**

**Đáp án:** Rò context giữa thread/task hoặc routing sai. Phải capture/validate tenant từng task, cài scope đúng, cleanup trong finally, kiểm tra cả connection cache và các downstream clients.

**Câu 8 — Truy vấn 100 kết quả toàn DB rồi filter ở Java có đúng không?**

**Đáp án:** Không phù hợp làm boundary. Có thể lộ dữ liệu qua log/count/highlights, làm pagination sai và bỏ sót/over-fetch. Scope query tại data source/search index.

## 18. Tóm tắt kiến trúc

Một ứng dụng multi-tenant an toàn cần **một chuỗi kiểm chứng không đứt đoạn**:

~~~text
Verified principal
  -> verified membership and active tenant
  -> action authorization for that tenant
  -> tenant-scoped resource lookup and data integrity constraints
  -> object ACL/business-state policy
  -> correctly scoped response, cache, file, search and event
  -> audit with trusted tenant context
~~~

Tenant **không** chỉ là filter UI, route prefix, claim hay session variable. Nó là phạm vi dữ liệu và chính sách được áp đặt nhất quán cho **mọi** đường xử lý, kể cả job nền và các thành phần không thuộc HTTP. Nếu một layer mắc lỗi, các lớp khác (repository predicates, composite keys, DB RLS, storage IAM, audit) phải hạn chế hậu quả thay vì cùng tin một input giả.

**Câu hỏi kiểm tra mỗi API:** “Nếu thay principal bằng người của tenant B nhưng giữ nguyên ID tài nguyên tenant A, API này có thể trả một byte dữ liệu A, sửa một dòng A hoặc tạo một liên kết tới A hay không?” Nếu câu trả lời có thể là có, ranh giới tenant chưa được bảo vệ đủ.

## Tài liệu chính thức để đối chiếu

- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request authorization, authentication supplier, `AuthorizationManager` và DSL.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, Spring proxy và method interception.
- [Spring Security – Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): giải quyết issuer/tenant bằng trusted issuers, `JwtIssuerAuthenticationManagerResolver` và trade-offs.
- [Spring Security – Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): HTTP security integration tests, `httpBasic` và `csrf` post-processors.
- [PostgreSQL – Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, `USING`/`WITH CHECK` và role bypass.
- [PostgreSQL – Configuration Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-ADMIN-SET): `current_setting` và `set_config`, bao gồm local transaction setting.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy/transaction boundaries, ranh giới xử lý đồng thời và dữ liệu.
