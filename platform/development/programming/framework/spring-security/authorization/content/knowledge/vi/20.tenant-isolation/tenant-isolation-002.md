# Xác định tenant từ nguồn đáng tin cậy trong Spring Security

## 1. Vấn đề: một tenant ID hợp lệ chưa chắc là tenant được phép

Trong ứng dụng SaaS đa khách hàng, `tenantId` thường xuất hiện ở URL, subdomain, HTTP header, JWT claim, session, message queue và cột dữ liệu trong database. Điều dễ mắc sai là nhìn thấy `X-Tenant-Id: beta` hoặc đường dẫn `/tenants/beta/documents` rồi coi `beta` là tenant hiện hành **đã được xác thực**.

Header và path đều có thể do caller chủ động chọn. Chúng rất hữu ích để nói **muốn thao tác ở tenant nào**, nhưng **không phải bằng chứng** rằng caller có quyền truy cập tenant ấy.

Một yêu cầu đúng cần tách ba câu hỏi:

1. **Ai là caller?** Định danh được xác thực qua Spring Security (JWT đã kiểm chứng, session đã xác thực, service identity/mTLS...).
2. **Caller được phép vào những tenant nào?** Dựa trên membership, grant hoặc policy phía server; thông tin trong token chỉ dùng trong giới hạn trust contract của issuer.
3. **Request này chọn tenant nào?** URL/header/subdomain chỉ là *requested tenant*. Phải đối chiếu lựa chọn đó với tập tenant được phép, rồi buộc các truy vấn và hành động tiếp theo vào tenant đã được giải quyết.

Ví dụ:

```text
JWT đã được xác minh:
  sub = alice
  tenants = ["alpha", "beta"]

Membership DB hiện hành:
  alice -> tenant alpha (ACTIVE)
  alice -> tenant beta (REVOKED)

Request:
  GET /tenants/beta/documents

=> DENY. JWT được ký đúng không có nghĩa membership tenant beta còn hiệu lực.
```

Kết quả không thể là “thử dùng tenant mặc định alpha” hoặc “nếu thiếu membership thì bỏ filter tenant”. **Fail closed** có nghĩa thiếu hoặc xung đột thông tin quyền thì ngăn nghiệp vụ, không tạo truy vấn unrestricted.

### Sau bài học bạn sẽ làm được

- Phân biệt nguồn identity đáng tin và dữ liệu chọn tenant chưa đáng tin.
- Biết xác minh JWT đúng issuer/audience/chữ ký/thời hạn trước khi dùng claim.
- Thiết kế `TenantResolver`/`TenantAccessPolicy` không chấp nhận tenant do client tự khẳng định quyền.
- Hiểu trường hợp người dùng thuộc một tenant, nhiều tenant, đổi tenant và tài khoản máy.
- Đưa tenant đã xác minh vào repository, transaction, DB/RLS, cache, jobs và audit.
- Viết test chống sửa header/path/JWT, stale membership, confused deputy và rò dữ liệu xuyên tenant.
- Áp dụng ví dụ Java 17 chạy độc lập và mẫu Spring Security Resource Server tích hợp.

## 2. Một bảng phân loại nguồn tenant

| Nguồn | Người dùng có thể điều khiển? | Mức tin cậy | Nên sử dụng |
| --- | --- | --- | --- |
| `/tenants/{id}/...` | Có | **Untrusted selector** | Chọn tenant yêu cầu; phải authorize |
| Query `?tenantId=...` | Có | **Untrusted selector** | Chỉ áp dụng cho chức năng có tenant selector |
| `X-Tenant-Id` từ internet | Có | **Untrusted selector** | Không làm bằng chứng quyền |
| Subdomain `alpha.example.com` | Người dùng chọn host | **Untrusted selector** | Map hostname → tenant đã được cấp phép; chống host header injection |
| Cookie do browser gửi | Browser có thể gửi/sửa | Tùy xác thực và ký | Không coi cookie tên tenant tự đủ quyền |
| Session principal phía server | Qua authentication | Nguồn identity có thể tin **nếu session an toàn** | Xác định subject, sau đó đối chiếu membership |
| Claim `tenant`/`tenants` trong JWT đã validate | Do issuer đã được tin xác nhận | **Có điều kiện** | Ràng buộc theo contract token, thời hạn, audience và membership |
| JWT payload chỉ base64-decode | Có thể giả mạo | **Không đáng tin** | Không dùng để cấp quyền |
| Membership/ACL từ repository phía server | Hệ thống quản lý | Nguồn chính sách | Xác minh active membership và scope |
| HTTP header được gateway tin cậy gắn | Chỉ tin nếu gateway strip/rewrite và đường truyền bảo vệ | Có điều kiện | Identity propagation có trust boundary rõ; vẫn authorize |
| Message metadata/job payload | Người gửi job có thể đặt | Phụ thuộc hàng đợi/producer | Re-auth/re-authorize hoặc dùng capability đã kiểm chứng |
| `ThreadLocal` tenant | Code nào cũng có thể set | **Không phải bằng chứng** | Chỉ là chỗ truyền một kết quả đã xác minh, phải cleanup |
| Tenant ID từ database record | Nguồn authoritative cho resource | Dữ liệu resource | Đối chiếu với tenant của caller trước khi đọc/ghi |

Một giá trị có **nguồn tin cậy** không có nghĩa nó tự mang **đầy đủ quyền**. Ví dụ một issuer đáng tin có thể ký token nói caller thuộc tenant alpha ở thời điểm phát hành, nhưng quản trị viên đã thu hồi quyền cách đây 5 phút. Chính sách phải xác định token claim có đủ làm membership snapshot cho đến khi hết hạn hay cần tra membership hiện hành.

## 3. Thuật ngữ: subject, issuer, selected tenant và authorized tenant

Định nghĩa:

- **Subject**: ID caller ổn định trong phạm vi một issuer, thường lấy từ `sub` của JWT đã xác minh. Cùng `sub` có thể xuất hiện tại hai issuers khác nhau, nên hệ thống multi-issuer cần phân biệt bằng cặp `(iss, sub)` hoặc identity nội bộ đã chuẩn hóa.
- **Issuer (iss)**: nguồn phát hành token. Nó phải thuộc **allowlist** và được verify theo security configuration.
- **Audience (aud)**: ứng dụng/API mà token được phát hành cho; token dành cho API khác không được coi là access token hợp lệ cho API hiện tại.
- **Tenant claim**: thông tin về tenant trong token; phải có schema/issuer contract, không suy diễn từ string bất kỳ.
- **Membership**: mối quan hệ caller ↔ tenant, gồm trạng thái ACTIVE/REVOKED, role, hiệu lực, phạm vi dự án khi cần.
- **Requested tenant**: tenant do route, subdomain hoặc header đề xuất cho request hiện tại.
- **Resolved tenant/authorized tenant**: tenant được resolver cho phép sau khi xác thực caller và kiểm tra policy.
- **Resource tenant**: tenant mà record/task/document thực sự thuộc về trong dữ liệu server.

Với user thuộc đúng một tenant, hệ thống có thể tự chọn tenant đó nếu API cho phép. Với user thuộc nhiều tenant, nên yêu cầu chọn rõ tenant (hoặc session-selected tenant đã được kiểm tra), tránh “lấy phần tử đầu của Set” làm mặc định không ổn định.

### Hai chính sách khác nhau cần ghi rõ

**Tenant claim là giới hạn quyền:** token nói `alpha`, DB nói `alpha,beta`. Caller chỉ vào alpha cho đến khi nhận token có beta (trừ khi thiết kế contract khác).

**Tenant claim chỉ mô tả preferred tenant:** token nói alpha là default, nhưng DB cho phép alpha,beta. Caller có thể chọn beta sau khi kiểm tra membership. Hai contract này khác nhau; không nên trộn trong cùng resolver. Ví dụ chạy của bài chọn **giao nhau giữa token tenants và membership DB** để minh họa policy chặt.

## 4. Luồng giải quyết tenant an toàn

```text
HTTP request / message
        |
        v
Security authentication
  - xác minh chữ ký/session/mTLS
  - JWT: issuer, audience, thời gian, token type
        |
        v
Principal/subject đã xác thực
        |
        v
Resolve server-side membership / policy
        |
        v
Requested tenant từ path/header/subdomain
        |
        v
Authorize requested tenant against memberships + token scope
        |
        +--- DENY ---> AccessDeniedException / 403
        |
        v
Immutable AuthorizedTenantScope
  - canonical tenant ID
  - canonical subject ID
  - permissions và policy version khi cần
        |
        v
Repository/DB query/transaction + tenant predicate
        |
        v
Response/caches/jobs/audit luôn có đúng tenant scope
```

Quan trọng: **xác thực trước, chọn tenant sau, dùng tenant đã được cấp phép ở mọi tầng**. Nếu phải chọn tenant *trước* khi xác thực để quyết định issuer/JWK, hãy coi giá trị đó chỉ là **routing hint** để chọn bộ xác minh **trong allowlist**, tuyệt đối chưa dùng nó làm quyền truy cập dữ liệu.

## 5. JWT đáng tin cậy nghĩa là đã kiểm chứng những gì?

Không thể tin vào `JWT.decode(token).getClaim("tenant")` nếu chỉ base64-decode payload. Một JWT có thể bị người dùng tự sửa payload. Điều kiện tối thiểu của API nhận JWT:

1. **Signature** được kiểm tra với key/algorithm tin cậy, key được lấy từ issuer/JWK set tin cậy. Không chấp nhận algorithm không đúng policy, token không chữ ký hoặc các kiểu key-confusion.
2. **`iss`** đúng một issuer được cấu hình/allowlist.
3. **`aud`** có đúng audience của resource server; đây là kiểm tra chống dùng token của ứng dụng khác.
4. **`exp`** chưa hết hạn và **`nbf`** hợp lệ; clock skew chỉ điều chỉnh có kiểm soát.
5. **Token purpose/type** hợp lệ: access token của API này, không tự thay ID token thành API bearer token.
6. **`sub`** tồn tại, không rỗng và được ánh xạ sang canonical identity đúng ngữ cảnh issuer.
7. **Claim tenant** đúng kiểu, định dạng, và tên schema đã quy ước; không coi claim tùy ý là quyền quản trị.
8. **Revocation/validity contract** rõ: token ngắn hạn, introspection hoặc lookup membership khi cần thu hồi gần tức thời.

Spring Security Resource Server có thể xác minh JWT qua `oauth2ResourceServer().jwt()` và `JwtDecoder`. Ví dụ cấu hình Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/company
          audiences: api://documents
```

Trong dòng Spring Boot hỗ trợ thuộc tính `audiences`, property này yêu cầu claim `aud` chứa audience tương ứng. `issuer-uri` giúp cấu hình phát hiện JWK và kiểm tra issuer, cùng kiểm tra thời gian token. Ứng dụng vẫn cần kiểm tra custom tenant claim và membership; Spring không tự hiểu nghiệp vụ tenant của bạn.

Ví dụ security filter chain cho API dùng Bearer token:

```java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
        );
        http.oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
```

Imports cần thiết:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Đây là **mã cấu hình tích hợp**, cần dependency `spring-boot-starter-oauth2-resource-server` và `spring-security-oauth2-jose` (được starter kéo vào tùy cấu hình), issuer thực và trust store phù hợp. Với ứng dụng sử dụng cookie/session hoặc request ghi, cần đánh giá **CSRF và session policy**; không tắt CSRF chỉ vì ví dụ là REST API.

### Tại sao cần audience?

Giả sử IdP phát JWT cho ứng dụng analytics với cùng issuer và subject. Nếu documents API chỉ kiểm tra `iss` nhưng không kiểm tra `aud`, attacker có thể thử dùng token dành cho analytics để truy cập documents. Audience là ranh giới giữa resource servers.

### Claim tenant là thông tin ủy quyền, không phải dữ liệu định danh bất biến

Người dùng có thể chuyển team, bị khóa khỏi một tenant, được cấp quyền tenant mới hoặc có quyền tạm thời. Nếu hệ thống lấy `tenants` từ JWT, phải xác định token lifetime, khi nào refresh, kiểm tra membership hiện hành như thế nào và sẽ xử lý quyền đã bị thu hồi ra sao. Token đã ký **không cập nhật tự động** khi DB đổi.

## 6. Không tin trực tiếp `X-Tenant-Id`, path và subdomain

### Header do client gửi

```http
GET /api/documents HTTP/1.1
Authorization: Bearer <access-token>
X-Tenant-Id: beta
```

Header nói “hãy phục vụ tenant beta”. Quyết định đúng là:

```text
authenticatedUser = verifyAccessToken()
requestedTenant = request.headers["X-Tenant-Id"]
authorizedTenants = membershipService.getActiveTenants(authenticatedUser)

if requestedTenant NOT IN authorizedTenants:
    DENY
else:
    setAuthorizedScope(requestedTenant)
```

Đây là pseudocode, không phải API Spring có sẵn. Không dựa vào chuyện header xuất hiện “đúng định dạng” hay “được frontend đặt” để cấp quyền.

### Tenant trong URL

`/tenants/{tenantId}/documents` rất rõ và tốt cho REST routing, nhưng path variable cũng do client chọn. Trước khi gọi service, phải authorize tenant đó. Với ID resource trong path, vẫn cần xác minh **resource nằm trong tenant đã được phép**:

```sql
SELECT id, title
FROM documents
WHERE id = :document_id
  AND tenant_id = :authorized_tenant;
```

Một request `/tenants/alpha/documents/42` phải không đọc được document 42 thuộc beta, dù caller có quyền vào alpha. Kiểm tra mỗi URL tenant là chưa đủ: record tenant mới là authoritative.

### Subdomain và Host

`alpha.example.com` có thể định tuyến tới tenant alpha. Tuy nhiên:

- Host header từ internet không phải chứng cứ quyền.
- Reverse proxy cần kiểm soát hostnames hợp lệ và trusted forwarded headers.
- Wildcard domains, custom domains và IDN/punycode cần mapping đến canonical tenant trên server.
- Domain có thể được chuyển chủ hoặc hết hạn; cần kiểm tra trạng thái mapping.
- Tenant từ hostname vẫn phải được đối chiếu với principal/membership nếu endpoint không public.
- Đừng ghép `Host` trực tiếp thành schema/table name hoặc JDBC connection string.

### Proxy-injected header

Header nội bộ có thể đáng tin **chỉ khi** mọi request đều đi qua một gateway được xác thực, gateway xóa mọi header client có cùng tên rồi set lại, đường truyền gateway → service được bảo vệ (mTLS/network ACL), backend không thể truy cập trực tiếp từ internet, và service kiểm tra contract. Nếu một điều kiện hỏng, attacker có thể spoof header.

Ngay cả header đã được gateway ký/gắn vẫn không nhất thiết thay việc kiểm tra caller có membership trong tenant được chọn.

## 7. Xác minh membership tại server

Bảng mô hình:

```sql
CREATE TABLE tenant_membership (
    subject_id VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    granted_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    PRIMARY KEY (subject_id, tenant_id)
);
```

Truy vấn quyền đang có:

```sql
SELECT tenant_id
FROM tenant_membership
WHERE subject_id = :authenticated_subject
  AND state = 'ACTIVE'
  AND revoked_at IS NULL;
```

Đây là schema SQL **minh họa**. Production có thể cần `issuer_id` trong khóa chính, identity nội bộ, membership role, thời hạn hiệu lực, thông tin tổ chức và permission versions.

Trạng thái phải được kiểm tra: record membership tồn tại nhưng `SUSPENDED`/`REVOKED` không chứng minh caller có quyền. Không lấy tenant từ một request body như:

```json
{"subjectId":"alice","tenantId":"beta"}
```

rồi dùng `subjectId` client khai để query membership. Subject phải đến từ principal đã xác thực; nếu admin đang thao tác “thay người khác”, đó là workflow ủy quyền riêng, có audit.

### Nhiều tenant trong token và DB

| Token claims | Membership DB | Requested | Kết quả nếu dùng giao nhau |
| --- | --- | --- | --- |
| [alpha] | [alpha] | alpha | ALLOW |
| [alpha] | [alpha,beta] | beta | DENY, token không cấp beta |
| [alpha,beta] | [alpha] | beta | DENY, membership beta không ACTIVE |
| [alpha,beta] | [alpha,beta] | beta | ALLOW |
| [alpha,beta] | [alpha,beta] | không có | DENY nếu policy yêu cầu explicit selection |
| [alpha] | [] | alpha | DENY |
| Thiếu `tenants` | [alpha] | alpha | DENY nếu policy đòi claim tenants |
| [alpha] | [alpha] | gamma | DENY |
| [alpha] | [alpha] | chuỗi tenant lỗi format | DENY |

Đây là **một policy minh họa chặt chẽ**, không phải mặc định chung của Spring. Nếu doanh nghiệp muốn membership DB là nguồn duy nhất và token chỉ xác thực subject, resolver có thể bỏ giao nhau với token tenants; nhưng quyết định đó cần rõ, có tests và không suy diễn ngầm.

## 8. Thiết kế API `TenantResolver`

Mục đích là không để từng controller tự viết:

```java
String tenant = request.getHeader("X-Tenant-Id");
repository.findAllByTenantId(tenant);
```

Thay bằng một thành phần trung tâm:

```text
TenantResolver.resolve(
    verifiedAuthentication,
    requestedTenantHint
) -> AuthorizedTenantScope
```

Một `AuthorizedTenantScope` nên bất biến, tối thiểu:

```java
public record AuthorizedTenantScope(
        String subjectId,
        String tenantId) {
}
```

Nếu cần role/permission, chỉ thêm giá trị đã được xác minh. Không cho controller tạo `new AuthorizedTenantScope("alice", "beta")` từ input rồi coi đó là chứng cứ quyền: nên giới hạn nơi khởi tạo (package/module boundary, factory) hoặc thiết kế service yêu cầu principal và tự resolve.

### Điều kiện của resolver

1. Authentication khác null và đã authenticated.
2. Không phải anonymous identity.
3. Subject hợp lệ, ổn định và đã normalize trong context issuer.
4. Caller có quyền gọi chức năng dự kiến (ví dụ scope READ).
5. Token claims được lấy từ `JwtAuthenticationToken` **sau khi decoder validate**, không tự decode raw bearer.
6. Tập tenant được phép được tra theo membership và policy server.
7. Requested tenant phải là canonical ID, nằm trong allowed tenants.
8. Nếu không requested và allowed chỉ có một tenant, có thể chọn tenant đó **theo API contract**.
9. Nếu allowed nhiều tenant, phải có lựa chọn rõ hoặc một session-selected tenant được kiểm tra lại.
10. Resolve xong mới query dữ liệu, tạo job hoặc truyền tenant xuống downstream.

Có thể dùng custom exception/`AccessDeniedException` cho denied; lỗi authentication tương ứng với 401 và authorization tương ứng với 403 theo filter chain và exception handling thực tế. Không dùng trả empty list để che một lỗi xác thực khiến client không biết mình thiếu quyền.

## 9. Java 17 runnable: token-scoped tenants ∩ server memberships

Chương trình dưới đây **đầy đủ, không có dependency ngoài JDK 17**. Nó mô phỏng bước *sau khi authentication đã được verify*. `AuthenticatedCaller` đại diện cho principal đáng tin do hệ thống xác thực tạo, không phải đối tượng frontend có quyền tự gửi. Mục đích là thấy rõ thuật toán tenant selection, membership và fail closed.

Tệp `TenantResolutionLab.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public final class TenantResolutionLab {

    record AuthenticatedCaller(
            String subject,
            Set<String> tokenTenants,
            Set<String> authorities) {}

    record AuthorizedTenantScope(
            String subject,
            String tenant) {}

    record Document(long id, String tenant) {}

    static final Map<String, Set<String>> ACTIVE_MEMBERSHIPS = Map.of(
            "alice", Set.of("alpha"),
            "bob", Set.of("alpha", "beta"),
            "carol", Set.of("alpha")
    );

    static final List<Document> DOCUMENTS = List.of(
            new Document(11L, "alpha"),
            new Document(12L, "alpha"),
            new Document(21L, "beta"),
            new Document(22L, "beta"),
            new Document(31L, "gamma")
    );

    private static AuthorizedTenantScope resolve(
            AuthenticatedCaller caller, String requestedTenant) {

        if (caller == null || caller.subject() == null
                || caller.subject().isBlank()
                || caller.tokenTenants() == null
                || caller.authorities() == null
                || !caller.authorities().contains("DOC_READ")) {
            throw new SecurityException("Denied");
        }

        Set<String> membership = ACTIVE_MEMBERSHIPS.getOrDefault(
                caller.subject(), Set.of());

        Set<String> allowed = caller.tokenTenants().stream()
                .filter(membership::contains)
                .collect(Collectors.toCollection(TreeSet::new));

        if (requestedTenant != null) {
            if (!requestedTenant.matches("[a-z][a-z0-9-]{0,31}")
                    || !allowed.contains(requestedTenant)) {
                throw new SecurityException("Denied");
            }
            return new AuthorizedTenantScope(
                    caller.subject(), requestedTenant);
        }

        if (allowed.size() != 1) {
            throw new SecurityException("Explicit tenant required");
        }

        return new AuthorizedTenantScope(
                caller.subject(), allowed.iterator().next());
    }

    private static List<Long> visibleIds(AuthorizedTenantScope scope) {
        return DOCUMENTS.stream()
                .filter(doc -> doc.tenant().equals(scope.tenant()))
                .sorted(Comparator.comparingLong(Document::id))
                .map(Document::id)
                .toList();
    }

    private static void attempt(
            String label, AuthenticatedCaller caller, String tenant) {
        try {
            AuthorizedTenantScope scope = resolve(caller, tenant);
            System.out.println(label + ": tenant=" + scope.tenant()
                    + " ids=" + visibleIds(scope));
        } catch (SecurityException denied) {
            System.out.println(label + ": DENIED");
        }
    }

    public static void main(String[] args) {
        AuthenticatedCaller alice = new AuthenticatedCaller(
                "alice",
                Set.of("alpha", "beta"),
                Set.of("DOC_READ"));

        AuthenticatedCaller bob = new AuthenticatedCaller(
                "bob",
                Set.of("alpha", "beta"),
                Set.of("DOC_READ"));

        AuthenticatedCaller carol = new AuthenticatedCaller(
                "carol",
                Set.of("alpha"),
                Set.of());

        attempt("alice alpha", alice, "alpha");
        attempt("alice beta", alice, "beta");
        attempt("alice implicit", alice, null);
        attempt("bob beta", bob, "beta");
        attempt("bob no selection", bob, null);
        attempt("carol no authority", carol, "alpha");
        attempt("no authentication", null, "alpha");
        attempt("malformed selection", alice, "Alpha");
        attempt("attempt tenant gamma", alice, "gamma");
    }
}
```

Chạy:

```bash
javac TenantResolutionLab.java
java TenantResolutionLab
```

Stdout chính xác theo mã:

```text
alice alpha: tenant=alpha ids=[11, 12]
alice beta: DENIED
alice implicit: tenant=alpha ids=[11, 12]
bob beta: tenant=beta ids=[21, 22]
bob no selection: DENIED
carol no authority: DENIED
no authentication: DENIED
malformed selection: DENIED
attempt tenant gamma: DENIED
```

Giải thích:

- Alice có token claim alpha,beta nhưng membership hiện hành chỉ alpha, nên beta bị từ chối.
- Alice không chọn tenant vẫn được resolve alpha vì giao nhau chỉ còn **một** tenant.
- Bob được cả alpha,beta; khi chọn beta, dữ liệu chỉ có ID 21,22. Không chọn tenant thì từ chối vì mơ hồ.
- Carol có membership alpha nhưng thiếu `DOC_READ` nên không được tra danh sách.
- Header/path `Alpha` bị từ chối vì canonical ID trong demo dùng chữ thường; không tự lowercase input rồi cho qua.
- Tenant gamma không được phép dù có tài liệu tồn tại.
- Chương trình giả định `AuthenticatedCaller` chỉ được tạo sau xác thực; **nó không xác minh chữ ký JWT**, không kết nối database và không phải implementation HTTP Spring Security. Phần Spring thực tế ở mục tiếp theo.

### Vì sao không dùng `Set.iterator().next()` khi có hai tenant?

Set không đại diện cho lựa chọn có chủ đích của người dùng và thứ tự phần tử có thể thay đổi. Tự chọn “tenant đầu tiên” dễ khiến lệnh ghi/sao chép dữ liệu vào tenant không định trước. Chỉ auto-select khi **đúng một** tenant hợp lệ và API đã chọn contract đó.

### Membership cache

Nếu `ACTIVE_MEMBERSHIPS` đến từ database/cache, phải có chính sách TTL/invalidation. Ví dụ admin thu hồi Alice khỏi beta: JWT cũ có thể còn beta, nhưng resolver tra membership hiện hành hoặc cache đã được cập nhật sẽ từ chối. Nếu membership cache cũ, còn khoảng trễ thu hồi quyền cần đo và chấp nhận theo threat model.

## 10. Tích hợp Spring Security Resource Server với resolver

Phần này là **mẫu tích hợp vào một ứng dụng Spring Boot**, không phải project Maven độc lập hoàn chỉnh. Nó giả định JWT decoder đã được Spring Security cấu hình/validate, có bảng membership và một `TenantMembershipRepository` đọc được dữ liệu tin cậy.

### 10.1. Interface kiểm tra membership

```java
public interface TenantMembershipRepository {
    Set<String> findActiveTenantIdsBySubject(String subjectId);
}
```

Đây là interface nghiệp vụ cần implementation JDBC/JPA thật. Với multi-issuer, thay subject string bằng canonical principal ID hoặc cặp issuer+subject để tránh collision. Repository không được lấy subject từ request input thay vì Authentication.

### 10.2. TenantScopeResolver đọc JwtAuthenticationToken đã xác thực

```java
@Component
public class TenantScopeResolver {

    private final TenantMembershipRepository memberships;

    public TenantScopeResolver(TenantMembershipRepository memberships) {
        this.memberships = memberships;
    }

    public AuthorizedTenantScope require(
            Authentication authentication,
            String requestedTenant) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !jwtAuth.isAuthenticated()) {
            throw new AccessDeniedException("JWT authentication required");
        }

        Jwt jwt = jwtAuth.getToken(); // JWT đã đi qua JwtDecoder của Resource Server.
        String subject = jwt.getSubject();
        if (subject == null || subject.isBlank()) {
            throw new AccessDeniedException("Missing subject");
        }

        if (jwtAuth.getAuthorities().stream()
                .noneMatch(a -> "SCOPE_documents.read"
                        .equals(a.getAuthority()))) {
            throw new AccessDeniedException("Document read scope required");
        }

        List<String> tenantsClaim = jwt.getClaimAsStringList("tenants");
        if (tenantsClaim == null || tenantsClaim.isEmpty()) {
            throw new AccessDeniedException("Missing tenant claim");
        }

        Set<String> activeMemberships =
                memberships.findActiveTenantIdsBySubject(subject);

        if (activeMemberships == null) {
            throw new AccessDeniedException("Tenant membership unavailable");
        }

        Set<String> allowed = tenantsClaim.stream()
                .filter(activeMemberships::contains)
                .collect(Collectors.toUnmodifiableSet());

        final String tenant;
        if (requestedTenant == null) {
            if (allowed.size() != 1) {
                throw new AccessDeniedException("Select a tenant");
            }
            tenant = allowed.iterator().next();
        } else {
            if (!requestedTenant.matches("[a-z][a-z0-9-]{0,31}")
                    || !allowed.contains(requestedTenant)) {
                throw new AccessDeniedException("Tenant access denied");
            }
            tenant = requestedTenant;
        }

        return new AuthorizedTenantScope(subject, tenant);
    }
}

public record AuthorizedTenantScope(String subjectId, String tenantId) {
}
```

Imports:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
```

Điều kiện quan trọng:

- Resolver **chỉ nhận `JwtAuthenticationToken` từ security infrastructure**. Đừng để client truyền một instance Java `Jwt` vào resolver rồi coi nó là đã xác thực.
- Cấu hình resource server phải xác minh issuer, audience, signature và thời hạn token. `JwtAuthenticationToken` tự nó là một type Java; test mock token không chứng minh token thật đã được xác minh.
- `getClaimAsStringList("tenants")` yêu cầu issuer contract cung cấp danh sách string. Nếu claim có kiểu khác, thiếu hay chứa ID không hợp lệ, nên từ chối thay vì tự ép kiểu tùy tiện. Có thể thêm validation từng phần tử theo tenant-ID policy.
- Spring mặc định thường ánh xạ `scope`/`scp` sang authorities có tiền tố `SCOPE_`. Nếu dự án custom converter, tên authority phải được đồng bộ trong resolver và `@PreAuthorize`.
- `Set` membership không nên cache vô thời hạn; cần quản lý revocation.
- Dữ liệu từ claim trong ví dụ được **giao** với membership. Nếu policy khác, phải thay đổi cả implementation, documentation và tests, không chỉ bỏ một dòng kiểm tra.

### 10.3. Controller không tự quyết định tenant

```java
@RestController
@RequestMapping("/tenants/{tenantId}/documents")
class DocumentController {

    private final DocumentQueryService service;

    DocumentController(DocumentQueryService service) {
        this.service = service;
    }

    @GetMapping
    List<DocumentSummary> list(
            @PathVariable String tenantId,
            Authentication authentication) {
        return service.listForTenant(authentication, tenantId);
    }
}
```

`tenantId` ở path vẫn là một **selector**, không được chuyển thẳng vào unscoped repository. Controller chuyển cho service để xác minh. `DocumentSummary` là DTO do ứng dụng định nghĩa; cần giữ property-level authorization khi chọn field.

### 10.4. Service giải quyết tenant rồi mới query

```java
@Service
class DocumentQueryService {

    private final TenantScopeResolver resolver;
    private final DocumentRepository repository;

    DocumentQueryService(
            TenantScopeResolver resolver,
            DocumentRepository repository) {
        this.resolver = resolver;
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_documents.read')")
    @Transactional(readOnly = true)
    public List<DocumentSummary> listForTenant(
            Authentication authentication, String requestedTenant) {

        AuthorizedTenantScope scope =
                resolver.require(authentication, requestedTenant);

        return repository.findVisibleSummaries(
                scope.tenantId(), scope.subjectId());
    }
}
```

Đây là **snippet tích hợp**; `DocumentRepository.findVisibleSummaries` phải triển khai query có tenant predicate và thêm chính sách owner/share/ACL. `@EnableMethodSecurity` phải được bật và service gọi qua Spring-managed proxy để `@PreAuthorize` có hiệu lực. Resolver vẫn kiểm tra authority nên nếu advice bị bỏ qua, service cũng không tự cấp quyền; tuy nhiên không được coi điều đó thay thiết kế method security đúng.

Nếu principal là một service account có quyền thao tác với tenant cụ thể, cần một policy riêng cho service identity; không giả lập một `JwtAuthenticationToken` user bằng cách copy token hay gán một subject tùy ý.

## 11. Tenant đã được xác minh phải đi tới tầng dữ liệu

Sau `resolver.require`, có một tenant đã được chấp thuận. Tuy nhiên lỗi xuyên tenant vẫn có thể xảy ra nếu repository dùng:

```java
repository.findById(documentId);
```

và không đối chiếu resource tenant. Không dựa vào việc caller đi từ route `/tenants/alpha` để suy ra document ID thuộc alpha.

Một truy vấn đọc đúng hướng:

```sql
SELECT id, title, status
FROM documents
WHERE tenant_id = :authorized_tenant
  AND id = :document_id;
```

Tìm kiếm và đếm:

```sql
SELECT id, title
FROM documents
WHERE tenant_id = :authorized_tenant
  AND (owner_id = :subject_id OR visibility = 'TEAM')
ORDER BY id
LIMIT :limit OFFSET :offset;
```

```sql
SELECT COUNT(*)
FROM documents
WHERE tenant_id = :authorized_tenant
  AND (owner_id = :subject_id OR visibility = 'TEAM');
```

Cùng tenant scope và business filters phải áp dụng cho `Page.content`, `totalElements`, `count`, exports, facets và thống kê. Không lọc sau khi đã phân trang vì có thể để lộ count/metadata và làm sai nội dung.

### Truy vấn cập nhật theo tenant

```sql
UPDATE documents
SET title = :new_title
WHERE id = :document_id
  AND tenant_id = :authorized_tenant
  AND owner_id = :authenticated_subject;
```

Ứng dụng kiểm tra affected rows: chỉ 1 row là thành công; 0 row không được coi thành công. Nếu nghiệp vụ còn trạng thái/phiên bản, thêm optimistic locking, transaction hoặc conditional predicates phù hợp.

**Nguyên tắc:** `tenant_id` trong `WHERE` đến từ **AuthorizedTenantScope**, không đến trực tiếp từ query/header/path. Vẫn cần chính sách object-level trong tenant khi người dùng không được nhìn mọi record của tenant đó.

### Joins

Mọi quan hệ tenant-scoped phải được join nhất quán:

```sql
SELECT d.id, a.name
FROM documents d
JOIN attachments a
  ON a.document_id = d.id
 AND a.tenant_id = d.tenant_id
WHERE d.id = :id
  AND d.tenant_id = :authorized_tenant;
```

Thiếu điều kiện tenant khi join có thể gắn dữ liệu của tenant khác nếu IDs cục bộ trùng nhau. Dùng composite foreign key/index phù hợp với thiết kế database.

## 12. Ba mô hình lưu trữ multi-tenant và trust boundary

### Shared schema, tenant_id trên mỗi row

Mọi tenant dùng chung tables; phải có tenant predicate cho **mọi đường đọc/ghi/aggregate**. Ưu: đơn giản vận hành. Rủi ro: một query quên `WHERE tenant_id` có thể rò dữ liệu.

### Schema per tenant

Mỗi tenant có schema riêng. Tenant resolver không được lấy schema name tùy ý từ request. Chỉ chọn schema từ registry allowlisted gắn với authorized tenant. Không nối trực tiếp `SET search_path = ` + client input. Kết nối pooled có thể giữ schema/connection state: phải reset sau mỗi giao dịch, test cross-request leakage.

### Database per tenant

Mỗi tenant dùng DataSource/database khác. Registry `authorizedTenantId → approved datasource` phải được kiểm soát và audit. Không biến header tenant thành JDBC URL/host để kết nối vào một database tùy ý (có nguy cơ SSRF và truy cập sai dữ liệu). Pooling, credential rotation, migrations và privileged operational tooling phải giới hạn scope.

Cả ba mô hình vẫn cần nhận diện caller, membership, quyền trên resource và cách truyền tenant tới jobs/caches. Việc có database riêng không khiến header client trở thành đáng tin.

## 13. Database Row-Level Security (RLS) hỗ trợ, nhưng không thay authentication

Với PostgreSQL RLS, có thể bổ sung lớp phòng thủ:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_tenant_policy ON documents
USING (tenant_id = current_setting('app.tenant_id', true))
WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
```

Đây là **snippet PostgreSQL tích hợp**, không phải cấu hình hoàn chỉnh. Ứng dụng phải thiết lập `app.tenant_id` theo tenant đã được authorize **trong đúng transaction/connection**, đảm bảo reset khi connection trả pool. Nếu setting thiếu, dùng policy fail closed; tránh role DB bypass RLS hoặc table owner bypass không được dự kiến. Cần review quyền `BYPASSRLS`/`FORCE ROW LEVEL SECURITY` và quyền gọi `SET` tương ứng trong threat model.

**Giới hạn quan trọng:** một connection user có thể có khả năng set custom GUC. RLS dùng `current_setting` chỉ an toàn như boundary app/DB role đang thiết lập nó. Nếu cho client chạy SQL tùy ý trên cùng role, họ có thể đổi context. Không coi RLS là phép xác thực tenant độc lập.

### Transaction và connection pooling

Với connection pooling và thread reuse, việc đặt tenant context mà không cleanup có thể khiến request sau dùng tenant trước. Ưu tiên local transaction-scoped setting, reset theo transaction và integration tests với pool size 1 để dễ phát hiện leak. Nếu dùng global session setting mà không reset, rủi ro nghiêm trọng.

## 14. SecurityContextHolder không phải “tenant do ai cũng được set”

`SecurityContextHolder` trong servlet app thường lưu `Authentication` theo thread; Spring Security cung cấp cơ chế bảo vệ và dọn context quanh request. Một số ứng dụng tạo riêng:

```java
private static final ThreadLocal<String> CURRENT_TENANT =
        new ThreadLocal<>();
```

`ThreadLocal` chỉ **truyền trạng thái**, không xác minh được tenant có hợp lệ hay không. Bất kỳ code nào nắm access có thể `set("beta")`. Nếu middleware đưa trực tiếp `X-Tenant-Id` vào ThreadLocal, toàn bộ repository phía sau có thể chạy sai tenant.

Ưu tiên thứ tự:

1. Truyền `AuthorizedTenantScope` bất biến thành tham số service/repository.
2. Nếu framework persistence cần tenant context ngầm, chỉ populate từ resolver đã được kiểm tra.
3. Giữ scope thật hẹp, cleanup bằng `try/finally`.
4. Không lưu scope vào singleton field hoặc static mutable global.
5. Không copy raw tenant selector vào security context làm authority.

Ví dụ wrapper hạn chế rò trạng thái thread (đoạn tích hợp):

```java
final class TenantContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    static String require() {
        String tenant = CURRENT.get();
        if (tenant == null) {
            throw new IllegalStateException("Missing authorized tenant");
        }
        return tenant;
    }

    static void runWith(AuthorizedTenantScope scope, Runnable job) {
        if (CURRENT.get() != null) {
            throw new IllegalStateException("Unexpected nested tenant scope");
        }
        CURRENT.set(scope.tenantId());
        try {
            job.run();
        } finally {
            CURRENT.remove();
        }
    }
}
```

Chỉ gọi `runWith` với scope do resolver đáng tin tạo. Với nested flows hoặc reactive programming, cần context propagation phù hợp, không áp dụng ThreadLocal máy móc. Ví dụ chủ ý từ chối nested scope nhằm tránh âm thầm ghi đè tenant, chứ không phải mọi ứng dụng đều phải cấm nested calls.

## 15. Async, message queue và scheduled jobs

### @Async và Executor

Spring Security mô tả `SecurityContext` thường gắn với thread; khi chuyển sang thread mới, context **không tự có**. `DelegatingSecurityContextExecutor` hoặc các wrapper liên quan giúp truyền authentication khi phù hợp. Nhưng **tenant context do ứng dụng tự tạo** không tự được framework đó truyền theo.

Không trông chờ:

```text
request thread: tenant=alpha
    |
    +-- @Async worker thread: tenant chắc vẫn alpha
```

Thiết kế tốt: truyền `tenantId` đã resolve cùng immutable job command và identity/authorization snapshot có contract rõ, rồi **re-authorize ở thời điểm job thực thi** nếu quyền có thể thay đổi. Với job được queue nhiều giờ, snapshot ở lúc enqueue không mặc nhiên còn đúng.

### Event/message headers

Message chứa `tenantId` không phải bằng chứng quyền. Broker/topic có thể được chia sẻ, consumer có thể nhận message từ nhiều producers. Cần xác thực producer/service identity, ràng buộc topic/tenant, kiểm tra chữ ký/capability hoặc tra policy server trước khi thao tác.

### Scheduled jobs

Không có end-user principal cho cron/scheduler. Thiết kế một **service identity** có quyền chạy trên một tenant cụ thể (hoặc một quy trình cross-tenant quản trị được phê duyệt). Với batch qua nhiều tenant, lặp từng tenant allowlisted trong phạm vi riêng, audit từng lần; không đặt `tenant = "*"` rồi cho repository bỏ filter trừ khi đó là quy trình quản trị đặc biệt đã có cơ chế kiểm soát khác.

### Downstream HTTP calls

Khi gọi service B, không tự tin rằng service B sẽ chấp nhận tenant vì service A đã authorize. Dùng token propagation hoặc service-to-service credentials đúng audience/trust boundary, chuyển tenant scope được kiểm soát, service B validate độc lập theo chính sách của nó. Tránh confused deputy: một service có quyền global không được phục vụ tenant bất kỳ chỉ vì user gửi header tenant tùy chọn.

## 16. Multiple issuers và tenant routing

Spring Security Resource Server hỗ trợ multi-tenant authentication khi API tin **nhiều authorization servers**. Ví dụ chọn decoder bằng issuer:

```java
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp-a.example.org",
                "https://idp-b.example.org");
```

Đoạn này cần import:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
```

Cấu hình vào resource server:

```java
http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
```

**Hai điểm rất quan trọng:**

1. Khi routing theo `iss`, claim có thể được đọc trước khi chữ ký được verify **chỉ để chọn một AuthenticationManager từ allowlist**; sau đó chính manager/decoder phải verify JWT bằng key/validator của issuer đã chọn. Không coi giá trị `iss` đọc thô là đã được xác thực.
2. **Issuer không nhất thiết bằng tenant.** Một issuer có thể phục vụ nhiều tenant, hoặc nhiều issuers đại diện nhiều loại identity. Cần một bước mapping `(issuer, subject) → canonical user → memberships` và xử lý claims theo contract.

Tài liệu Spring Security cảnh báo không được tự động tạo manager từ bất kỳ issuer URL nào do token khai, vì mở ra việc tin nguồn token không được phép. Với dynamic tenants, registry các issuers phải do bên quản trị đáng tin kiểm soát, không lấy tùy ý từ request header.

### Tenant by subdomain vs tenant by issuer

Nếu subdomain `alpha.example.org` chọn tenant alpha còn JWT do một issuer chung phát hành, xác thực issuer dùng issuer chung; tenant alpha vẫn phải verify membership.

Nếu từng tenant có issuer riêng, bước routing xác thực cần chọn issuer tin cậy và xác minh. Sau đó resolve tenant nghiệp vụ bằng claims và membership. Hai bước không được gộp thành “issuer match thì tự được đọc mọi resource của tenant đó”.

## 17. Các tình huống user đổi tenant

### Người dùng thuộc một tenant

Có thể chọn tenant duy nhất một cách tự động, nếu đó là contract API. Nếu tenant bị khóa sau đó, membership lookup phải từ chối chứ không tiếp tục dùng stale session-selected tenant.

### Người dùng thuộc nhiều tenant

Client có thể gửi `/tenants/beta` hoặc một tenant selector ở UI. Server phải verify:

- Người dùng authenticated.
- Tenant beta có active membership hoặc delegated permission.
- Token/scope còn cho phép beta theo contract.
- Chức năng đang gọi có quyền cần thiết tại beta.
- Record của request thực sự thuộc beta.

Không giữ tenant “gần nhất đã chọn” trong một static singleton dùng chung. Nếu lưu selected tenant trong session, thay đổi session phải kiểm tra lại membership và chống CSRF/session fixation tương ứng.

### Admin cross-tenant

Không tự cho `ROLE_ADMIN` bỏ qua tenant predicate. Có nhiều loại admin: admin một tenant, support operator hỗ trợ một tập tenants, platform administrator có thủ tục break-glass. Nên dùng một `CrossTenantAccessPolicy` riêng, audit reason/ticket/TTL và thêm test không được mở scope vô hạn bằng một header do khách hàng tạo.

### Delegated access

Ví dụ kế toán bên ngoài có quyền read trên project của tenant beta nhưng không là member toàn tenant. Policy phải định nghĩa scope được ủy quyền (document/project/resource), không vô tình mở toàn bộ tenant bằng cách cho phép “beta” trong tenant resolver mà không kèm ràng buộc object-level.

## 18. Test chống spoof tenant và confused deputy

Ma trận kiểm thử cần đi từ authentication đến data layer:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| JWT hợp lệ, membership alpha ACTIVE, chọn alpha | Được truy cập dữ liệu trong alpha theo quyền khác |
| JWT hợp lệ, chọn beta ngoài membership | 403 hoặc denied |
| Client sửa `X-Tenant-Id` thành beta | Không thể mở beta nếu membership không có |
| Client sửa URL `/tenants/beta` | Không thể mở beta nếu membership không có |
| Không có `Authorization` nhưng có header tenant hợp lệ | 401/không xác thực |
| JWT payload chứa beta nhưng chữ ký sai | 401, không chạy tenant resolver ở tầng nghiệp vụ |
| JWT đúng issuer nhưng sai `aud` | 401 |
| JWT hết hạn hoặc `nbf` chưa hợp lệ | 401 |
| JWT issuer không thuộc allowlist | 401 |
| JWT claim tenants là string thay vì string list | Không được chuyển thành quyền tùy tiện |
| Token tenants alpha,beta nhưng DB chỉ alpha | Chọn beta bị deny |
| Membership alpha đã REVOKED | Deny sau khi state/caches được cập nhật theo SLA |
| User có nhiều tenant, không chọn | Deny hoặc theo explicit contract, không chọn ngẫu nhiên |
| User chỉ có 1 tenant, không chọn | Có thể auto-select tenant duy nhất theo contract |
| User thiếu business authority trên alpha | Deny chức năng dù thuộc alpha |
| Resource ID thuộc beta nhưng URL ghi alpha | Không trả resource; tenant predicate thắng |
| Query count/stats/export ở alpha | Không chứa số liệu beta |
| Cache key không phân tenant | Test phát hiện leak và bắt buộc sửa |
| Async job đổi/revoke membership sau enqueue | Reauthorize theo quy định lúc xử lý |
| Tenant context được dùng lại trên thread pooled | Không được giữ tenant của request trước |
| Trusted gateway không xóa client-supplied identity header | Test giả mạo header phải bị chặn |
| Admin cross-tenant không có workflow break-glass | Deny |

### Mockito/JUnit tests cho resolver

Sau khi có `TenantMembershipRepository` và `TenantScopeResolver`, có thể kiểm tra độc lập:

```java
@Test
void requestedTenantMustBelongToVerifiedPrincipal() {
    when(memberships.findActiveTenantIdsBySubject("alice"))
            .thenReturn(Set.of("alpha"));

    // JwtAuthenticationToken của test chứa tenants alpha,beta
    // và authority SCOPE_documents.read.
    assertThrows(AccessDeniedException.class,
            () -> resolver.require(aliceJwtAuthentication, "beta"));
}
```

Đây là **test snippet**, không phải file độc lập: test fixture `aliceJwtAuthentication` phải được dựng rõ, resolver và repository mock được inject. Unit test dùng `JwtAuthenticationToken` dựng bằng tay chỉ chứng minh logic resolver, **không chứng minh chữ ký token**. Signature/issuer/audience cần integration tests với `JwtDecoder`/security filter chain hoặc identity provider test.

### Spring MVC integration test

Dùng `MockMvc`:

- Request thiếu token tới `/tenants/alpha/documents` → 401 theo filter chain.
- Mock authenticated Alice thuộc alpha, gửi path beta → 403.
- Mock authenticated Alice thuộc alpha, path alpha → 200 và chỉ có IDs alpha.
- Token thực ký bằng test key của issuer chưa được tin → 401, không vào controller.
- JWT có `aud` sai → 401, không dùng tenant claim dù claim đúng chữ ký.
- Nếu test dùng `SecurityMockMvcRequestPostProcessors.jwt()`, nhớ nó **bypass token signature verification** bằng cách dựng authentication test; nên dùng thêm integration test giải mã JWT thật.

Không chỉ assert status. Assert **ID cụ thể**, absence của data tenant khác và count/totalElements; lưu một số record có cùng local ID ở hai tenant để bắt lỗi lookup.

## 19. Cách tránh fail-open khi phát triển

### Không trả null/empty filter khi thiếu tenant

```java
// Phản ví dụ: thiếu tenant lại cho toàn bộ bản ghi.
Specification<Document> scope = requestedTenant == null
        ? null
        : (root, query, cb) -> cb.equal(root.get("tenantId"),
                                        requestedTenant);
```

Trong nhiều API query builder, `null` có thể hiểu là “không có điều kiện”, tương đương bỏ tenant isolation. Resolver phải fail closed trước khi tới repository; không có AuthorizedTenantScope thì không được query.

### Không dùng giá trị mặc định quá rộng

```java
// Phản ví dụ.
String tenant = header != null ? header : "all";
```

`"all"` là một phạm vi có chủ đích rất đặc biệt, không phải giá trị fallback cho người dùng thường. Cần API cross-tenant riêng và quyền mạnh, không biến absence thành global access.

### Không tự tin vào thông tin từ UI

Frontend có thể ẩn nút switch tenant nhưng attacker vẫn sửa HTTP request. Mọi kiểm tra membership phải ở server. CORS không phải authorization; API key/CSRF protection không thay role/tenant check.

### Không chọn database theo chuỗi chưa xác minh

```text
header tenant -> "customer-db-" + tenant -> JDBC connection
```

Nguy hiểm nếu có dynamic hostname/schema hoặc truy cập tenant khác. Chọn từ registry có key canonical `AuthorizedTenantScope.tenantId`, không dùng URL tùy ý do người dùng gửi.

## 20. Audit và tính quan sát

Mỗi quyết định tenant quan trọng nên có audit fields:

- Subject ID canonical và issuer (hoặc internal principal ID).
- Requested tenant từ route/header (đã giới hạn/khử ký tự điều khiển trong log).
- Resolved tenant đã được phép, hoặc lý do từ chối.
- Hành động: READ_DOC, EXPORT, UPDATE, SWITCH_TENANT, ADMIN_IMPERSONATE.
- Policy version/membership version nếu có.
- Resource type/ID và correlation/request ID.
- Timestamp, service và kết quả.

Không log JWT nguyên vẹn, access token, session cookie hoặc dữ liệu nhạy cảm. Tránh dùng requested tenant làm metric label có cardinality vô hạn nếu client có thể gửi nhiều giá trị bất kỳ. Với denial bất thường từ header tenant, có thể giám sát brute-force/enumeration nhưng không trả thông tin chi tiết về tenant có tồn tại hay không cho caller chưa đủ quyền.

### Lỗi 401, 403 hay 404?

- **401**: không có authentication hợp lệ.
- **403**: authenticated nhưng không được phép truy cập tenant/chức năng.
- **404**: có thể dùng cho resource không tồn tại hoặc che sự tồn tại của record/tenant theo API contract.

Phân loại này là nguyên tắc thông thường; framework mapping thực tế cần được cấu hình đúng. Không trả 403/404 khác nhau theo cách giúp attacker liệt kê tenant bí mật, nếu sự tồn tại của tenant cũng cần được bảo vệ.

## 21. Rủi ro khi thay đổi membership và đồng bộ hệ thống

Membership thường thay đổi:

```text
t0: Alice có quyền beta -> JWT được phát hành
t1: Admin thu hồi Alice khỏi beta
t2: Alice vẫn có JWT cũ và gọi API beta
```

Nếu API chỉ tin claim JWT cho đến `exp`, quyền có thể tồn tại đến hết token validity. Nếu ứng dụng cần thu hồi ngay, dùng membership lookup/introspection/token revocation hoặc entitlement version phù hợp.

Với cache membership:

- Định nghĩa TTL/invalidation và SLA thu hồi quyền.
- Phân biệt cache theo issuer+subject, tenant và policy context.
- Không dùng cache kết quả “Alice được tenant beta” khi identity khác có cùng username dưới issuer khác.
- Khi policy backend lỗi, không trả danh sách tenants mặc định toàn bộ.
- Nếu membership đang chuyển từ ACTIVE sang REVOKED, không thực hiện các thao tác ghi nhạy cảm chỉ dựa trên snapshot rất cũ.

Với database replication/read replica, membership vừa bị revoke ở primary có thể chưa có trên replica. Quy trình nhạy cảm cần chọn consistency phù hợp. RLS/row predicates vẫn phải áp dụng với scope đã được xác minh.

## 22. Lỗi thường gặp

**1. Tin `X-Tenant-Id` hoặc `Host` là chứng cứ quyền.** Chúng là selectors, phải xác minh membership.

**2. Chỉ base64-decode JWT rồi lấy claim tenant.** Chưa verify signature, issuer, audience và time validity.

**3. Xác minh chữ ký nhưng bỏ `aud`.** Token dành cho API khác có thể bị dùng sai.

**4. Tin claims từ issuer chưa được allowlist.** Với multi-issuer, chỉ select verifier từ trusted issuer registry.

**5. Coi token tenant claim luôn còn hiệu lực.** Membership có thể bị thu hồi; xác định re-check và revocation SLA.

**6. Lấy tenant từ body/path rồi truyền thẳng repository.** Đầu vào client không được biến thành authorized scope.

**7. Auto-select ngẫu nhiên một tenant trong Set.** Khi user có nhiều tenant, dễ thực hiện hành động sai tenant.

**8. Không xử lý membership thiếu bằng deny.** `null` scope có thể biến thành unrestricted query.

**9. Chỉ filter tenant trên list mà quên count/stats/export.** Có thể lộ số lượng và dữ liệu tổng hợp của tenant khác.

**10. Dùng chỉ tenant check cho mọi record.** Trong cùng tenant vẫn có owner, private, ACL/roles và property-level policy.

**11. Chỉ kiểm tra `/tenants/alpha` mà không kiểm tra document thực thuộc alpha.** ID có thể trỏ tới beta.

**12. Lưu tenant vào ThreadLocal không cleanup.** Thread pool có thể reuse context của request trước.

**13. Cho rằng `@Async` tự mang tenant.** Spring Security context và ứng dụng tenant context cần propagation có kiểm soát.

**14. Message/job có tenant ID thì mặc nhiên trusted.** Cần xác minh producer/service identity và re-authorize theo SLA.

**15. Gộp issuer với tenant.** Một issuer có thể cấp nhiều tenant, mỗi tenant có thể có nhiều identity flows.

**16. Không bind tenant vào cache key.** Cross-tenant cache poisoning/leakage.

**17. Tin gateway header dù backend mở cổng trực tiếp.** Attacker có thể bypass gateway và spoof header.

**18. Biến `ROLE_ADMIN` thành quyền global không kiểm soát.** Cần cross-tenant policy, audit và scope tường minh.

**19. Không khóa hoặc kiểm tra lại quyền trước mutation.** Owner/tenant/membership có thể thay đổi giữa check và use.

**20. Chỉ test mock JWT không test decoder.** Mock authentication bỏ qua chữ ký/audience; cần tests cả authentication boundary.

## 23. Checklist trước production

- [ ] Có mô hình phân biệt authenticated subject, requested tenant và authorized tenant.
- [ ] JWT được verify chữ ký, issuer allowlist, audience, exp/nbf và token purpose.
- [ ] Tenant claim schema rõ; không lấy claim từ JWT chỉ decode.
- [ ] Không tin trực tiếp header/path/subdomain/cookie để cấp tenant access.
- [ ] Membership/grants được lấy từ server, kiểm tra ACTIVE và hạn hiệu lực.
- [ ] Resolver định nghĩa rõ có/không giao token tenants với DB memberships.
- [ ] Multi-tenant user phải chọn tenant tường minh hoặc có session selector đã kiểm chứng.
- [ ] Thiếu authentication, claim, membership hoặc policy backend không tạo unrestricted scope.
- [ ] `AuthorizedTenantScope` được truyền vào service/repository như giá trị đã được authorize.
- [ ] Read/write/count/search/stats/export đều có tenant predicate và object-level scope.
- [ ] Query ID, join, attachment, blob và background jobs đều ràng buộc resource tenant.
- [ ] Schema/database routing không xây từ raw tenant selector; registry allowlist và pool cleanup.
- [ ] Nếu dùng RLS, đã xem xét DB role, transaction setting, connection pool và bypass RLS.
- [ ] Tenant context trong ThreadLocal/reactive/async được propagate và cleanup đúng.
- [ ] Trusted proxy headers được strip/rewrite tại edge, service chỉ nhận qua mTLS/network đáng tin.
- [ ] Hỗ trợ issuer nhiều nguồn bằng trusted issuer registry, không tạo verifier cho URL bất kỳ.
- [ ] Membership cache/revocation có TTL, event và consistency SLA rõ.
- [ ] Cross-tenant admin/job có policy, approval và audit riêng.
- [ ] Có integration tests cho spoof header/path, JWT sai iss/aud/signature, stale membership và API resource ID trái tenant.
- [ ] Có test count/stats/caching, concurrency và identity collision ở nhiều issuers/tenants.
- [ ] Không log JWT/session secret và không tiết lộ danh sách tenant bí mật trong error response.

**Kết luận:** *Tenant ID là một lựa chọn dữ liệu, không tự nó là quyền truy cập*. Nguồn tin cậy bắt đầu ở identity đã được xác thực; phạm vi tenant được phép đến từ token được verify **theo contract** và chính sách membership server; lựa chọn tenant của request phải được kiểm tra trước khi tạo `AuthorizedTenantScope`. Toàn bộ SQL, cache, job, thống kê và giao dịch phía sau chỉ được dùng **tenant đã được giải quyết và ủy quyền**, không dùng lại raw header/path do client gửi.

## Tài liệu chính thức

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security — Testing OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [OWASP — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
