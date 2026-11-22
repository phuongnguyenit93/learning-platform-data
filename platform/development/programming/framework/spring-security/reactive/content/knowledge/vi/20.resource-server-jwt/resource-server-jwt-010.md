# Phân quyền theo scope, claim nghiệp vụ và chủ sở hữu tài nguyên

## Mục tiêu học tập

Bài này thuộc chủ đề **Resource Server JWT** của **Spring Security reactive / Spring WebFlux**. Sau khi học, bạn có thể:

- Giải thích sự khác biệt giữa **Authentication** (JWT có hợp lệ, ai gọi API?), **authorization theo scope** (token được cấp phạm vi thao tác nào?), **claim nghiệp vụ** (chính sách vai trò/quyền từ issuer tin cậy) và **resource ownership** (bản ghi thực tế thuộc ai, tenant nào?).
- Biết cách Spring Security chuyển claim `scope` hoặc `scp` thành các authorities có tiền tố `SCOPE_` và dùng `ServerHttpSecurity.authorizeExchange(...)` cho từng HTTP method/path.
- Tùy biến `JwtAuthenticationConverter` + `ReactiveJwtAuthenticationConverterAdapter` để bổ sung một **allowlist business permissions** mà vẫn **giữ lại scope authorities mặc định**.
- Sử dụng `@EnableReactiveMethodSecurity` và `@PreAuthorize` cho quyền nghiệp vụ trên phương thức trả `Mono`/`Flux`.
- Lấy principal JWT đã được xác minh bằng `@AuthenticationPrincipal Jwt`, đối chiếu `sub` và `tenant_id` với dữ liệu **phía server**, không dùng ID do client khai để tự cấp quyền.
- Phòng chống **Broken Object Level Authorization (BOLA/IDOR)**: không cho user chỉ đổi `/documents/{id}` để đọc/sửa bản ghi của user hay tenant khác.
- Viết ứng dụng Java 17 WebFlux chạy được với Spring Boot, cấu hình issuer/JWKS/audience, API GET/PATCH, lớp lưu trữ reactive minh họa và kiểm thử WebTestClient `mockJwt()`.
- Phân biệt 401 (token không xác thực được), 403 (thiếu scope/quyền) và 404 (không tìm thấy hoặc chủ động che việc tồn tại tài nguyên), cùng những giới hạn của offline mocked JWT tests.

> **Phạm vi:** JWT Bearer Resource Server **reactive**, không phải Servlet `HttpSecurity`, không phải OAuth2 Login, và không phải việc “thêm claim role vào JWT là mọi record đều được đọc”. Phân quyền phải gắn với **operation + policy + tài nguyên thực tế**. Ví dụ dùng các tài khoản/tokens/dữ liệu thử, không dùng làm chính sách production mà chưa kiểm tra mô hình tenant, resource lifecycle và IdP.

## 1. Bốn lớp quyết định quyền

Giả sử API `GET /api/documents/D-101`:

~~~text
HTTP Authorization: Bearer <JWT>
            |
            v
1. Authentication: Resource Server xác minh chữ ký,
   issuer, audience, exp/nbf, định dạng token.
            |
            +-- Không hợp lệ -> 401
            |
            v
2. Scope: Token có SCOPE_documents.read?
            |
            +-- Không -> 403
            |
            v
3. Quyền nghiệp vụ: Token có PERM_documents:view?
            |
            +-- Không -> 403
            |
            v
4. Dữ liệu thực tế: document D-101
      tenant_id của document == tenant_id đã xác minh?
      owner_sub của document == sub đã xác minh?
            |
            +-- Không -> 404 (policy che existence)
            |
            v
200 OK: trả DTO đã giới hạn trường
~~~

Điều kiện tổng quát:

\[
\text{ALLOW}(u,a,r) =
  \text{ValidJWT}(u)
  \land \text{ScopeAllowed}(u,a)
  \land \text{BusinessPermission}(u,a)
  \land \text{RelationshipAllowed}(u,r)
\]

Trong đó `u` là caller, `a` là action và `r` là resource. Các lớp kiểm tra khác nhau không nên bị nhập làm một.

| Lớp | Dữ liệu xuất phát từ đâu? | Ví dụ | Quyết định |
|---|---|---|---|
| JWT authentication | Signature, claims, issuer/JWKS, validator | `iss`, `aud`, `sub`, `exp` | Token có được tin cậy hay không |
| Scope | `scope` hoặc `scp` được ký trong access token | `documents.read` | Token có quyền thao tác loại nào |
| Business claim/permission | Claim do **issuer đáng tin** cấp, theo policy của ứng dụng | `app_permissions=["documents:view"]` | Vai trò/nghiệp vụ có cho thao tác đó? |
| Ownership/tenant | Bản ghi trong repository/DB và principal đã xác minh | `owner_sub="alice"`, `tenant_id="org-a"` | Cụ thể resource D-101 có thuộc phạm vi người gọi? |
| Field-level policy | Chính sách riêng cho trường nhạy cảm | `salary`/`bank_account` | Được xem/sửa trường nào của resource |

**Không thể suy ra ownership từ việc token có `documents.read`.** Scope này thường cho phép “thử truy cập tài nguyên loại documents”, không cho đọc *mọi document*.

### 1.1. Dấu hiệu bị BOLA/IDOR

Nếu cả hai lời gọi dưới đều trả 200 chỉ vì token có scope, API có nguy cơ BOLA:

~~~http
GET /api/documents/D-101
Authorization: Bearer <token-cua-alice>

GET /api/documents/D-102
Authorization: Bearer <token-cua-alice>
~~~

Giả sử D-101 của Alice nhưng D-102 của Bob. **Đổi ID trên URL là đầu vào không tin cậy**; muốn bảo vệ, server phải tra row D-102 và kiểm tra quan hệ với Alice **trước khi trả dữ liệu**. Không thể sửa bằng cách ẩn nút UI hoặc ký mã định danh theo một công thức dễ đoán.

### 1.2. AuthN và AuthZ độc lập

- **401 Unauthorized:** không có Bearer token, token bị sửa, hết hạn, sai chữ ký/issuer/audience hoặc không xác thực được (tùy cách backend map lỗi).
- **403 Forbidden:** token đã được xác minh nhưng thiếu scope/permission/role theo chính sách; không đủ quyền thao tác.
- **404 Not Found:** bản ghi không tồn tại hoặc ứng dụng **chủ động trả 404** cho bản ghi không thuộc caller để giảm lộ tồn tại. Đây là một **quyết định policy**, không phải quy tắc bắt buộc của Spring.
- **200 OK:** phải qua **tất cả** điều kiện, sau đó trả representation tối thiểu.

Cần tránh tạo side channel: nếu tài nguyên không thuộc người dùng mà trả 403, còn ID không tồn tại trả 404, một attacker có thể dò ID hợp lệ. Với API nhạy cảm, thường chọn một response thống nhất (404) cho cả hai nhánh. Tuy nhiên 404 không thay thế logging/audit và kiểm tra quyền thực.

## 2. JWT là dữ liệu đã được xác minh, không phải mọi claim đều là quyền

Một access token minh họa, chỉ là payload JSON chứ **không phải JWT đã được ký hợp lệ**:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["documents-api"],
  "sub": "alice",
  "tenant_id": "org-a",
  "scope": "documents.read documents.write",
  "app_permissions": ["documents:view", "documents:edit"],
  "exp": 1893456000,
  "iat": 1893452400,
  "jti": "fixture-123"
}
~~~

Các trường quan trọng:

| Claim | Ý nghĩa | Lưu ý authorization |
|---|---|---|
| `iss` | Issuer đã cấp token | **Chỉ tin issuer được cấu hình**; nếu đa issuer, định danh người dùng nên là `iss + sub`. |
| `aud` | API/token recipient | Phải chứa audience dành cho **documents-api**, không lấy access token cấp cho service khác. |
| `sub` | Subject/resource owner identity | Dùng ID ổn định từ issuer; không mặc định email là khóa ownership. |
| `scope` / `scp` | Những scope token được cấp | Thường chuyển sang `SCOPE_...` authorities. |
| `app_permissions` | Một claim nghiệp vụ **tùy thỏa thuận giữa IdP/API** | Không có chuẩn bắt mọi IdP phải cung cấp claim tên này. |
| `tenant_id` | Tenant claim đã được định nghĩa/kiểm soát | Cần kiểm tra nó có phù hợp **row tenant**; không tin `X-Tenant-Id` bên ngoài. |
| `exp`/`nbf` | Thời gian token hợp lệ | Token hết hạn/chưa có hiệu lực không được tạo Authentication. |
| `jti` | ID JWT, nếu có | Không tự tạo revocation check nếu hệ thống không có denylist/introspection. |

**JWT được ký không có nghĩa claim luôn phản ánh quyền mới nhất.** Role/tenant membership có thể bị thu hồi sau khi access token đã phát. Với hành động nhạy cảm, cân nhắc access token sống ngắn, version claims, tra policy/ACL/DB thời điểm request, denylist hoặc introspection. Chữ ký hợp lệ không biến một `tenant_id` cũ thành “membership hiện tại”.

### 2.1. Xác minh JWT trước khi sử dụng claim

Resource Server phải kiểm tra signature/JWKS, thuật toán được chấp nhận, issuer, audience, thời hạn (và các validator bổ sung khi cần) **trước** khi dùng claim làm quyền. Không:

- Decode JWT payload với Base64 rồi tin các fields mà không verify JWS.
- Cho caller tự truyền `scope`, `roles`, `tenant_id` hoặc `ownerId` trong HTTP headers thay JWT.
- Nhận JWT của bất kỳ issuer nào có cùng tên scope.
- Tự coi `id_token` của OIDC login là access token dành cho resource API.
- Chấp nhận `alg=none` hoặc thuật toán/ký hiệu `kid` từ token mà không kiểm soát provider/JWKS.
- Chỉ verify signature nhưng bỏ `aud`; token có thể dành cho resource server khác.

Spring Boot hỗ trợ cấu hình `issuer-uri`, `jwk-set-uri`, `audiences` để thực thi các ràng buộc cơ bản. Bài thực hành sẽ sử dụng cả ba.

## 3. Phân quyền theo scope trong Resource Server reactive

Spring Security JWT Resource Server mặc định đọc claim `scope` hoặc `scp` và biến thành `GrantedAuthority` có tiền tố **`SCOPE_`**.

Ví dụ:

~~~json
{
  "scope": "documents.read documents.write"
}
~~~

Từ token đã được xác minh, authentication có authorities:

~~~text
SCOPE_documents.read
SCOPE_documents.write
~~~

Nếu issuer dùng:

~~~json
{
  "scp": ["documents.read", "documents.write"]
}
~~~

Spring Security cũng có hỗ trợ quy ước `scp`. Cách diễn giải cụ thể của claim tùy issuer/token type; cần kiểm tra trong tích hợp thật. Không giả định mọi provider đều cấp cùng tên/kiểu trường.

### 3.1. Bảo vệ API theo path và HTTP method

Một mảnh cấu hình WebFlux:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/documents/**")
        .hasAuthority("SCOPE_documents.read")
    .pathMatchers(HttpMethod.PATCH, "/api/documents/**")
        .hasAuthority("SCOPE_documents.write")
    .anyExchange().denyAll())
~~~

- GET cần quyền đọc.
- PATCH cần quyền ghi.
- DELETE không được cho phép nếu chưa khai báo.
- Rule **cụ thể** phải đứng trước `anyExchange().denyAll()`.
- Matching HTTP method là cách giảm lỗi “cùng một endpoint nhưng quyền đọc lại cho phép ghi”.
- Nếu user có cả read/write scopes, vẫn phải kiểm tra business permission và ownership ở các lớp tiếp theo.

`SCOPE_documents.read` là authority string sau mapping; đừng viết `hasRole("SCOPE_documents.read")` vì `hasRole` thường áp `ROLE_` prefix, không phải `SCOPE_`. Dùng `hasAuthority(...)` hoặc authorization manager `hasScope(...)` của reactive khi thích hợp.

### 3.2. Scope không bảo đảm đúng audience

Một JWT mang `scope=documents.read` nhưng `aud=["billing-api"]` phải bị từ chối **ngay ở authentication/validation** khi API của bạn yêu cầu `aud=documents-api`. Đừng chữa bằng cách thêm một granted authority; audience xác định token **được cấp cho ai**, không phải chỉ một nhãn quyền nghiệp vụ.

### 3.3. Scope là tập quyền được cấp, không là quyền của mọi user

Một confidential client dùng `client_credentials` có thể có scope `documents.read` nhưng **không có user subject tương ứng với document owner**. API phải định nghĩa rõ policy service accounts: ví dụ service role read-all được cấp phép và audit riêng, không vô tình áp dụng branch “nếu không có owner thì cho qua”.

## 4. Claim nghiệp vụ: chuyển dữ liệu IdP thành authorities có kiểm soát

Nhiều hệ thống cần phân quyền tường minh hơn scope OAuth2:

~~~json
{
  "app_permissions": ["documents:view", "documents:edit"],
  "tenant_id": "org-a"
}
~~~

Một số providers dùng `roles`, `realm_access.roles`, `groups`, `permissions` hoặc tên claim riêng. Không có mapper chuẩn phù hợp mọi IdP. Phải có **hợp đồng schema** giữa issuer và Resource Server.

Bài này dùng convention:

~~~text
scope "documents.read"            -> authority SCOPE_documents.read
app_permissions "documents:view"   -> authority PERM_documents:view
app_permissions "documents:edit"   -> authority PERM_documents:edit
~~~

Các prefix khác nhau giúp tránh việc một giá trị trong `app_permissions` vô tình cấp authority scope hoặc role dành cho nguồn dữ liệu khác.

### 4.1. Vì sao không map mọi string tùy ý thành ROLE_ADMIN?

Sai:

~~~java
// PHẢN VÍ DỤ, không áp dụng trực tiếp:
jwt.getClaimAsStringList("roles").stream()
   .map(role -> new SimpleGrantedAuthority("ROLE_" + role));
~~~

Nếu nhiều token issuers/clients/tenants hoặc một issuer cho user tự chỉnh claim, cách này có thể khiến role không đáng tin được cấp quyền. Thậm chí với issuer đáng tin, **role global** không có nghĩa user là admin của *mọi tenant*.

Cách an toàn hơn:

- Validate issuer + audience và thỏa thuận claim schema.
- **Allowlist chính xác** những permission strings mà API hiểu.
- Giữ các authorities ở namespace riêng (ví dụ `PERM_`).
- Đối chiếu tenant/ownership từ dữ liệu thật sau khi kiểm tra quyền nghiệp vụ.
- Không map claim bất kỳ sang `ROLE_SUPER_ADMIN` chỉ vì tên trông giống.

### 4.2. Giữ lại mapping scopes mặc định khi thêm business claim

Một `JwtGrantedAuthoritiesConverter` mặc định chuyển scope/scp thành authorities có prefix `SCOPE_`. Nếu custom converter **thay** nó chỉ bằng business roles, bạn có thể làm mất scope authorities khiến rule `hasAuthority("SCOPE_documents.read")` luôn 403.

Pattern dùng trong demo:

~~~java
JwtGrantedAuthoritiesConverter scopeConverter =
    new JwtGrantedAuthoritiesConverter();

JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setJwtGrantedAuthoritiesConverter(jwt -> {
    Collection<GrantedAuthority> authorities =
        new ArrayList<>(scopeConverter.convert(jwt));

    Object raw = jwt.getClaim("app_permissions");
    if (raw instanceof Collection<?> permissions) {
        for (Object permission : permissions) {
            if ("documents:view".equals(permission)) {
                authorities.add(
                    new SimpleGrantedAuthority("PERM_documents:view"));
            }
            if ("documents:edit".equals(permission)) {
                authorities.add(
                    new SimpleGrantedAuthority("PERM_documents:edit"));
            }
        }
    }
    return authorities;
});
~~~

Đây là **mảnh code** bên trong method config. Nó giữ scopes mặc định và chỉ thêm **hai** permissions đã khai báo. Nếu `app_permissions` không có hoặc sai kiểu, không cấp business permission; deny-by-default.

Trong **WebFlux**, `jwtAuthenticationConverter(...)` của DSL nhận reactive converter. Có thể bọc converter đồng bộ:

~~~java
new ReactiveJwtAuthenticationConverterAdapter(converter)
~~~

Không đem thẳng Servlet-only filter vào reactive security chain. Spring Security cung cấp adapter này để biến kết quả thành `Mono<AbstractAuthenticationToken>`.

### 4.3. Role và business rule còn cần điều kiện bổ sung

`PERM_documents:edit` chỉ nói account có thể thực hiện **loại thao tác edit**, không chứng minh resource D-102 thuộc account. Trong ứng dụng có tổ chức, một user có thể có permission edit của tenant A nhưng không của tenant B. Ràng buộc **tenant/record ownership** bắt buộc ở lớp data/service.

Khi business claim thay đổi thường xuyên (membership bị xóa, role bị thu hồi, account bị khóa), access token còn hạn có thể chứa **quyền cũ**. Những hệ thống yêu cầu thu hồi quyền tức thời nên có authorization state kiểm tra tại server hoặc token lifetime phù hợp, không dùng mỗi JWT claim.

## 5. Kiểm tra chủ sở hữu tài nguyên và tenant

Giả sử bảng dữ liệu:

| document_id | tenant_id | owner_sub | title |
|---|---|---|---|
| `D-101` | `org-a` | `alice` | Tài liệu của Alice |
| `D-102` | `org-a` | `bob` | Tài liệu của Bob |
| `D-201` | `org-b` | `alice` | Tài liệu Alice ở tenant khác |

Caller có JWT:

~~~json
{
  "sub": "alice",
  "tenant_id": "org-a",
  "scope": "documents.read",
  "app_permissions": ["documents:view"]
}
~~~

Các kết quả **sau khi JWT đã được xác minh**:

| Request | Kết quả trong demo | Tại sao |
|---|---|---|
| GET D-101 | **200** | Scope + permission hợp lệ, owner Alice, tenant org-a. |
| GET D-102 | **404** | Cùng tenant nhưng owner là Bob. |
| GET D-201 | **404** | Owner Alice nhưng tenant org-b khác tenant claim. |
| GET D-999 | **404** | Không có bản ghi. |
| GET D-101, thiếu scope | **403** | WebFlux chain từ chối trước khi đọc tài nguyên. |
| GET D-101, thiếu permission | **403** | Method security từ chối. |
| GET D-101, không token | **401** | Bearer authentication chưa thành công. |

**Điểm mấu chốt:** JWT `sub`/`tenant_id` là **input đã xác minh của authorization decision**, nhưng quyền sở hữu nằm ở **row thực tế** hoặc ACL được server quản lý.

### 5.1. Mẫu truy vấn DB nên lọc quyền từ đầu

Ở production với R2DBC, ý tưởng truy vấn là:

~~~sql
SELECT id, title
FROM documents
WHERE id = :id
  AND tenant_id = :tenant_id_from_verified_jwt
  AND owner_sub = :sub_from_verified_jwt;
~~~

Các parameters phải được bind bằng database driver, không nối chuỗi user input vào SQL. Truy vấn này giúp DB không trả row của tenant/owner khác ngay từ đầu. Nếu dùng shared database, còn cần index/composite keys và tenant data isolation đúng.

Nếu ứng dụng hỗ trợ **chia sẻ tài liệu/ACL**, điều kiện phải được mở rộng có kiểm soát:

~~~sql
SELECT d.id, d.title
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :trusted_tenant
  AND (
        d.owner_sub = :trusted_subject
        OR EXISTS (
          SELECT 1
          FROM document_acl a
          WHERE a.document_id = d.id
            AND a.grantee_sub = :trusted_subject
            AND a.can_read = TRUE
        )
      );
~~~

Đây là SQL khái niệm, không phải một implementation repository hoàn chỉnh. Nếu có nhiều issuers, ACL identity nên chứa issuer cùng subject. Với cập nhật, dùng `UPDATE ... WHERE id=? AND tenant_id=? AND owner_sub=?` hoặc policy predicate trong **cùng transaction**; chỉ kiểm tra quyền trước rồi update vô điều kiện có thể tạo race/TOCTOU.

### 5.2. Không tin “owner” trong request body

Sai:

~~~http
PATCH /api/documents/D-102
Authorization: Bearer <token-cua-alice>
Content-Type: application/json

{"ownerSub":"alice","tenantId":"org-a","title":"Đổi tên"}
~~~

Nếu backend tin hai trường `ownerSub`/`tenantId` do caller gửi, attacker có thể tự khai mình là chủ sở hữu. Thay vào đó, request payload chỉ nhận trường nghiệp vụ được phép đổi (ví dụ `title`). Server lấy `sub` và `tenant_id` từ Authentication **đã verify**, rồi đối chiếu row trong kho dữ liệu.

### 5.3. Ownership không phải chỉ so sánh tên hiển thị

Không dùng username/email làm identity mặc định vì có thể đổi hoặc trùng. Thông thường dùng **issuer + subject** (`iss` + `sub`) làm khóa nhận dạng dài hạn; nếu hệ thống có internal user ID, cần mapping verified identity → internal user ổn định. `tenant_id` cũng cần quy ước rõ: claim có thể là active tenant hay tập memberships, có thời điểm hiệu lực/thu hồi riêng.

### 5.4. Dùng 403 hay 404 cho tài nguyên không thuộc user?

Không có quy tắc duy nhất:

- **403**: minh bạch rằng resource có tồn tại nhưng caller thiếu quyền, phù hợp một số API nội bộ.
- **404**: che việc tồn tại resource khi caller không có quan hệ với nó. Hữu ích cho API có object IDs dễ đoán.
- **Thống nhất** response cho “không có” và “không được thấy” nếu policy yêu cầu chống enumeration.
- Dù chọn response nào, audit server-side vẫn nên ghi nguyên nhân an toàn; không lộ thông tin owner/tenant trong body lỗi.

Ví dụ thực hành chọn **404** khi một document không tồn tại hoặc không thuộc `sub + tenant_id`, còn 403 cho thiếu scope/permission.

## 6. Method security reactive: business claim ở lớp phương thức

Spring Security hỗ trợ:

~~~java
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
~~~

Trên cấu hình Spring, cùng:

~~~java
@PreAuthorize("hasAuthority('PERM_documents:view')")
public Mono<DocumentView> findDocument(...) {
    // ...
}
~~~

**Điểm đặc thù WebFlux:** Method có authorization reactive nên trả `Mono` hoặc `Flux` để Spring đọc `Authentication` từ Reactor Context. Không áp dụng máy móc method security blocking trên một service trả kết quả trực tiếp rồi tự `block()`.

Có thể đặt `@PreAuthorize` ở controller/service theo kiến trúc. Nếu cùng business action được gọi từ HTTP endpoint, scheduled job và message listener, đặt policy ở **service boundary** có thể tránh bỏ sót một entrypoint. Tuy nhiên quyền sở hữu bản ghi phải được kiểm soát ở repository/service nơi có dữ liệu thật, không chỉ kiểm tra role trên controller.

### 6.1. Vì sao cần cả path rule lẫn @PreAuthorize?

Ví dụ:

~~~text
SecurityWebFilterChain:
    GET /api/documents/** → SCOPE_documents.read

Method security:
    GET document → PERM_documents:view

Data/service:
    document.tenantId == jwt.tenant_id
    document.ownerSub == jwt.sub
~~~

Ba điều kiện kết hợp theo logic **AND**. Nếu rule scope đúng nhưng business claim sai, request bị từ chối. Nếu scope + permission đúng nhưng owner khác, backend vẫn không trả row.

### 6.2. @PostAuthorize có đủ thay ownership query không?

`@PostAuthorize` có thể kiểm tra dữ liệu sau khi method trả publisher, nhưng không nên là biện pháp duy nhất nếu query đã tải nhiều hàng nhạy cảm, có side effects hoặc kết quả lớn. Với dữ liệu multi-tenant, **lọc tại truy vấn/repository** thường giảm rủi ro lộ dữ liệu và tránh công việc không cần thiết. Dùng `@PostAuthorize` khi phù hợp với từng use case và phải test failure behavior, không mặc định mọi `returnObject` là đồng bộ.

## 7. Ví dụ Java 17: WebFlux Resource Server, scope + permission + ownership

Ví dụ dùng **Spring Boot 3.5.16**, Java 17, Spring WebFlux và Spring Security. Ứng dụng là một **JWT Resource Server**:

- Kiểm tra `iss` và `aud` qua cấu hình Spring Boot, đọc public keys ở JWKS URI.
- `GET /api/documents/{id}` cần `SCOPE_documents.read` và `PERM_documents:view`.
- `PATCH /api/documents/{id}` cần `SCOPE_documents.write` và `PERM_documents:edit`.
- Document được trả/sửa **chỉ khi** `sub` và `tenant_id` khớp row của document.
- Không có database thật; demo dùng `ConcurrentHashMap` được bọc trong reactive `Mono`. Trong production, thay bằng R2DBC queries với điều kiện tenant/owner ở SQL.
- Tests dùng `mockJwt()` để kiểm tra authorization mà **không cần IdP**, và test riêng converter map scope/claim.

**Cảnh báo:** `mockJwt()` bỏ qua việc verify chữ ký/issuer/audience thật của Bearer token. Unit/integration tests dưới đây **không chứng minh** Spring JWT decoder nhận token từ IdP. Cần test thật với signed JWT, mock JWKS hoặc IdP staging trước production.

### 7.1. Cấu trúc project

~~~text
reactive-document-authz/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/DocumentAuthzApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/example/DocumentAuthzTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-document-authz'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng JDK 17+ và Gradle/Gradle Wrapper tương thích. `spring-boot-starter-oauth2-resource-server` mang hỗ trợ xác minh JWT/JWS qua Spring Security OAuth2 Resource Server + JOSE. **Không cần** `spring-boot-starter-web` Servlet trong demo reactive.

### 7.2. application.yml

Tệp `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - documents-api
~~~

Đây là **cấu hình minh họa**: issuer/JWKS phải được thay bằng IdP thật trong môi trường kiểm thử tích hợp/production. Khi có cả issuer URI và JWKS URI, Spring Boot không cần gọi discovery IdP ngay lúc app startup nhưng sẽ cần tải keys khi xử lý JWT thật. Đồng thời có `issuer-uri` để validate `iss` và `audiences` để validate `aud`.

**Không lấy JWKS URI từ JWT header hoặc user query tùy ý.** Chỉ tin metadata/provider được cấu hình. Dùng HTTPS thật, issuer/audience chính xác và algorithm policy phù hợp. Không cho phép JWT `alg=none`.

### 7.3. Ứng dụng đầy đủ

Tệp `src/main/java/example/DocumentAuthzApplication.java`:

~~~java
package example;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class DocumentAuthzApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentAuthzApplication.class, args);
    }

    @Bean
    JwtAuthenticationConverter authorizationClaimsConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            // Giữ mapping scope/scp -> SCOPE_...
            Collection<GrantedAuthority> result =
                new ArrayList<>(scopes.convert(jwt));

            // Chỉ công nhận một allowlist quyền nghiệp vụ.
            Object raw = jwt.getClaim("app_permissions");
            if (raw instanceof Collection<?> permissions) {
                for (Object permission : permissions) {
                    if ("documents:view".equals(permission)) {
                        result.add(new SimpleGrantedAuthority(
                            "PERM_documents:view"));
                    }
                    if ("documents:edit".equals(permission)) {
                        result.add(new SimpleGrantedAuthority(
                            "PERM_documents:edit"));
                    }
                }
            }

            return result;
        });

        return converter;
    }

    @Bean
    SecurityWebFilterChain security(
        ServerHttpSecurity http,
        JwtAuthenticationConverter authorizationClaimsConverter) {

        return http
            // Chỉ đúng khi API dùng Bearer header và KHÔNG dùng
            // browser cookie/session authentication.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.read")
                .pathMatchers(HttpMethod.PATCH, "/api/documents/**")
                    .hasAuthority("SCOPE_documents.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    new ReactiveJwtAuthenticationConverterAdapter(
                        authorizationClaimsConverter))))
            .build();
    }

    public record DocumentRecord(
        String id, String tenantId, String ownerSub, String title) {
    }

    public record DocumentView(String id, String title) {
    }

    public record RenameDocument(String title) {
    }

    @Service
    public static class DocumentService {

        // DỮ LIỆU DEMO: thay bằng R2DBC repository trong production.
        private final Map<String, DocumentRecord> documents =
            new ConcurrentHashMap<>(Map.of(
                "D-101", new DocumentRecord(
                    "D-101", "org-a", "alice", "Tài liệu Alice"),
                "D-102", new DocumentRecord(
                    "D-102", "org-a", "bob", "Tài liệu Bob"),
                "D-201", new DocumentRecord(
                    "D-201", "org-b", "alice", "Tài liệu tenant B")));

        private boolean owns(Jwt jwt, DocumentRecord document) {
            // JWT ở đây đã được authentication filter xác minh.
            String sub = jwt.getSubject();
            String tenant = jwt.getClaimAsString("tenant_id");

            return sub != null && !sub.isBlank()
                && tenant != null && !tenant.isBlank()
                && Objects.equals(document.ownerSub(), sub)
                && Objects.equals(document.tenantId(), tenant);
        }

        private DocumentView toView(DocumentRecord document) {
            // Chỉ trả field cần thiết; không leak tenant/owner.
            return new DocumentView(
                document.id(), document.title());
        }

        public Mono<DocumentView> getForOwner(
            String id, Jwt jwt) {

            return Mono.justOrEmpty(documents.get(id))
                .filter(doc -> owns(jwt, doc))
                .map(this::toView)
                .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                        HttpStatus.NOT_FOUND)));
        }

        public Mono<DocumentView> renameForOwner(
            String id, Jwt jwt, RenameDocument request) {

            return Mono.defer(() -> {
                if (request == null
                    || request.title() == null
                    || request.title().isBlank()
                    || request.title().length() > 120) {
                    return Mono.error(
                        new ResponseStatusException(
                            HttpStatus.BAD_REQUEST,
                            "Invalid title"));
                }

                // Atomic compute đảm bảo check ownership
                // và update cùng critical section của Map demo.
                AtomicReference<DocumentRecord> accepted =
                    new AtomicReference<>();

                documents.computeIfPresent(id, (key, current) -> {
                    if (!owns(jwt, current)) {
                        return current;
                    }

                    DocumentRecord updated = new DocumentRecord(
                        current.id(),
                        current.tenantId(),
                        current.ownerSub(),
                        request.title());

                    accepted.set(updated);
                    return updated;
                });

                return Mono.justOrEmpty(accepted.get())
                    .map(this::toView)
                    .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                            HttpStatus.NOT_FOUND)));
            });
        }
    }

    @RestController
    public static class DocumentController {

        private final DocumentService service;

        public DocumentController(DocumentService service) {
            this.service = service;
        }

        @GetMapping("/api/health")
        public Mono<Map<String, String>> health() {
            return Mono.just(Map.of("status", "ok"));
        }

        @GetMapping("/api/documents/{id}")
        @PreAuthorize("hasAuthority('PERM_documents:view')")
        public Mono<DocumentView> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

            return service.getForOwner(id, jwt);
        }

        @PatchMapping("/api/documents/{id}")
        @PreAuthorize("hasAuthority('PERM_documents:edit')")
        public Mono<DocumentView> rename(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody Mono<RenameDocument> body) {

            return body.flatMap(request ->
                service.renameForOwner(id, jwt, request));
        }
    }
}
~~~

### 7.4. Cách đọc chính xác các lớp bảo vệ

1. **JWT authentication:** `oauth2ResourceServer(...jwt(...))` nhận Bearer header, dùng decoder/JWKS và validators từ cấu hình Boot. JWT chưa xác minh sẽ không thành authenticated Jwt principal.
2. **Scopes:** `JwtGrantedAuthoritiesConverter` giữ prefix `SCOPE_`. GET/PATCH được bảo vệ theo **method + path** ở SecurityWebFilterChain.
3. **Business permissions:** Custom converter chỉ hiểu `documents:view` hoặc `documents:edit` từ `app_permissions`; giữ scope authorities cùng lúc. `@PreAuthorize` ở controller bắt buộc PERM tương ứng.
4. **Ownership:** `DocumentService.owns(...)` so sánh trusted `sub`/`tenant_id` với **row demo**. Không dùng `ownerSub` trong request body.
5. **Output:** `DocumentView` chỉ có `id` và `title`; không trả internal permission/tenant data không cần thiết.
6. **404 policy:** Nếu row không có hoặc không thuộc owner/tenant, service trả cùng 404. Thiếu scope/permission trả 403, không authentication trả 401.
7. **PATCH:** Sửa title có validate 1–120 chars; logic read-check-update nằm trong `ConcurrentHashMap.computeIfPresent` để demo tránh race trên một key. Với DB phải dùng transaction/conditional update và xử lý số row thay đổi.
8. **Reactive:** API trả `Mono`, không gọi `block()`/`subscribe()` trong WebFlux handler; `@EnableReactiveMethodSecurity` làm method authorization trên Reactor Context.
9. **CSRF:** `csrf.disable()` ở đây **chỉ hợp lệ cho stateless Bearer-header API không dùng browser cookie/session authentication**. Nếu bạn cũng nhận session cookie, HTTP Basic tự gửi hoặc form login, hãy đánh giá CSRF riêng; không copy dòng disable một cách máy móc.
10. **Demo data:** In-memory map sẽ mất khi restart và không tương đương R2DBC multi-instance. Không dùng nó cho production authorization state.

### 7.5. Chạy chương trình

~~~bash
gradle bootRun
~~~

Hoặc `./gradlew bootRun` / `gradlew.bat bootRun` nếu có wrapper. Sau khi app khởi động, kiểm tra health:

~~~bash
curl -i http://localhost:8080/api/health
~~~

Kỳ vọng có HTTP **200** và JSON:

~~~json
{"status":"ok"}
~~~

API tài liệu cần Bearer JWT hợp lệ, được cấp bởi issuer đã cấu hình và có audience `documents-api`. Vì `idp.example.test` là domain minh họa, **không thể gọi API protected thành công với token thật cho đến khi thay issuer/JWKS URI và có IdP hợp lệ**. Với không token:

~~~bash
curl -i http://localhost:8080/api/documents/D-101
~~~

Kỳ vọng HTTP **401**; response có thể có `WWW-Authenticate: Bearer`. Với JWT thật cần thử:

~~~bash
# Chỉ minh họa cách truyền JWT do IdP thật cấp:
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN_DUOC_CAP_HOP_LE>" \
  http://localhost:8080/api/documents/D-101
~~~

Không đặt access token production vào file chia sẻ, screenshot, shell history hoặc issue tracker. Thay placeholder bằng token thử nghiệm cấp cho đúng issuer/audience/scope/permission. Header `Authorization` phải truyền **access token**, không phải ID Token của OIDC login.

### 7.6. Kiểm thử không cần IdP với mockJwt

Spring Security Test có `mockJwt()` cho **WebTestClient**. Nó đặt một JWT Authentication vào test ServerWebExchange, thuận tiện để test authorization decisions mà không tạo JWT đã được ký.

**Rất quan trọng:** `mockJwt()` có thể cấp sẵn authorities thông qua `.authorities(...)`. Nó **bypass decoder và thường bỏ qua custom JWT converter trong production filter**, vì vậy cần một test **riêng cho JwtAuthenticationConverter** để chứng minh claim mapping. Bài này có cả hai.

Tệp `src/test/java/example/DocumentAuthzTest.java`:

~~~java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class DocumentAuthzTest {

    @Autowired
    WebTestClient client;

    @Autowired
    JwtAuthenticationConverter authorizationClaimsConverter;

    private WebTestClient as(
        String subject, String tenant, String... authorities) {

        SimpleGrantedAuthority[] grants =
            new SimpleGrantedAuthority[authorities.length];

        for (int i = 0; i < authorities.length; i++) {
            grants[i] = new SimpleGrantedAuthority(authorities[i]);
        }

        return client.mutateWith(mockJwt()
            .jwt(jwt -> jwt
                .claim("sub", subject)
                .claim("tenant_id", tenant))
            .authorities(grants));
    }

    @Test
    void noTokenReturns401() {
        client.get().uri("/api/documents/D-101")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void scopeIsNecessaryEvenWithBusinessPermission() {
        as("alice", "org-a", "PERM_documents:view")
            .get().uri("/api/documents/D-101")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void businessPermissionIsNecessaryEvenWithScope() {
        as("alice", "org-a", "SCOPE_documents.read")
            .get().uri("/api/documents/D-101")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void ownerWithScopeAndPermissionCanRead() {
        as("alice", "org-a",
           "SCOPE_documents.read", "PERM_documents:view")
            .get().uri("/api/documents/D-101")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("D-101");
    }

    @Test
    void cannotReadAnotherOwnersDocument() {
        as("alice", "org-a",
           "SCOPE_documents.read", "PERM_documents:view")
            .get().uri("/api/documents/D-102")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void cannotReadDifferentTenantsDocument() {
        as("alice", "org-a",
           "SCOPE_documents.read", "PERM_documents:view")
            .get().uri("/api/documents/D-201")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void missingDocumentAlsoReturns404() {
        as("alice", "org-a",
           "SCOPE_documents.read", "PERM_documents:view")
            .get().uri("/api/documents/D-999")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void patchRequiresWriteScope() {
        as("alice", "org-a", "PERM_documents:edit")
            .patch().uri("/api/documents/D-101")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new DocumentAuthzApplication.RenameDocument(
                "New title"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void patchRequiresEditBusinessPermission() {
        as("alice", "org-a", "SCOPE_documents.write")
            .patch().uri("/api/documents/D-101")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new DocumentAuthzApplication.RenameDocument(
                "New title"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void cannotEditOtherOwnersDocument() {
        as("alice", "org-a",
           "SCOPE_documents.write", "PERM_documents:edit")
            .patch().uri("/api/documents/D-102")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new DocumentAuthzApplication.RenameDocument(
                "Not allowed"))
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void ownerCanEditWhenAllChecksPass() {
        as("alice", "org-a",
           "SCOPE_documents.write", "PERM_documents:edit")
            .patch().uri("/api/documents/D-101")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new DocumentAuthzApplication.RenameDocument(
                "Renamed by Alice"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Renamed by Alice");
    }

    @Test
    void converterPreservesScopeAndAllowlistsPermissions() {
        Jwt jwt = Jwt.withTokenValue("not-a-signed-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .claim("scope", "documents.read documents.write")
            .claim("app_permissions", List.of(
                "documents:view", "some-untrusted-admin"))
            .build();

        var authentication =
            authorizationClaimsConverter.convert(jwt);

        assertNotNull(authentication);
        assertTrue(authentication.getAuthorities().contains(
            new SimpleGrantedAuthority("SCOPE_documents.read")));
        assertTrue(authentication.getAuthorities().contains(
            new SimpleGrantedAuthority("SCOPE_documents.write")));
        assertTrue(authentication.getAuthorities().contains(
            new SimpleGrantedAuthority("PERM_documents:view")));

        // Business claim lạ không được nâng thành quyền.
        assertFalse(authentication.getAuthorities().contains(
            new SimpleGrantedAuthority(
                "PERM_some-untrusted-admin")));
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Với Gradle Wrapper dùng `./gradlew test` hoặc `gradlew.bat test`. Kỳ vọng **12 tests** pass với Spring Boot 3.5.x/Spring Security 6.5.x tương thích, nhưng **cần thực thi trên máy/CI thật để xác nhận**. Các test `mockJwt` kiểm tra scope, business permission và ownership ở Spring Security + controller/service; test cuối kiểm tra converter. Chúng **không** test chữ ký JWT, `iss`, `aud` hoặc remote JWKS vì mocking bỏ qua decoder.

Một lưu ý: tests có thay title của D-101 trong map in-memory. Các test GET không assert title gốc để tránh phụ thuộc thứ tự chạy; còn các test authorization 403/404 không cập nhật data.

### 7.7. Checklist end-to-end bổ sung cho JWT thật

Trước khi lên production, cần test với IdP test/staging hoặc locally signed fixtures và trusted test JWKS:

1. JWT hợp lệ với `iss`/`aud` đúng được decoder chấp nhận.
2. JWT có `aud` sai nhưng scope đúng **bị 401**, không đi qua authorization.
3. JWT với `iss` sai, chữ ký sai, expired/`nbf` ở tương lai đều bị từ chối.
4. Token dùng algorithm không được allowlist hoặc có `alg=none` bị từ chối.
5. Token đúng issuer nhưng `app_permissions` không đúng type/không có → không tự cấp permission.
6. Token đúng permissions nhưng issuer đã thu hồi user/tenant membership → policy kiểm tra trạng thái hiện tại nếu nghiệp vụ đòi tức thời.
7. Token của service account không có user owner **không tự lấy được** mọi document.
8. PATCH cần row count/version/ACL checks; concurrent updates không tạo cross-tenant race.
9. Mọi lỗi trả status chuẩn và không lộ token trong trace/log.
10. Kiểm tra test của gateway/proxy không tin header `X-User`, `X-Tenant-Id` hoặc `X-Roles` nếu nó không được một trusted identity system bảo vệ.

## 8. Nâng cấp sang repository R2DBC và chính sách đa tenant

In-memory demo chỉ để học. Với PostgreSQL/R2DBC, security enforcement nên gần dữ liệu:

~~~sql
-- Read: không trả bản ghi không đúng tenant/owner.
SELECT id, title
FROM documents
WHERE id = :doc_id
  AND tenant_id = :tenant_id
  AND owner_sub = :owner_sub;

-- Write: update với cùng điều kiện quyền,
-- đồng thời kiểm soát concurrent write qua version.
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :doc_id
  AND tenant_id = :tenant_id
  AND owner_sub = :owner_sub
  AND version = :expected_version;
~~~

Các dấu `:doc_id` v.v. là **named parameters** của truy vấn minh họa, phải bind từ verified context qua driver/framework. Nếu `UPDATE` ảnh hưởng **0 rows**, có thể vì không tồn tại/không thuộc owner/tenant hoặc version conflict; response policy phải phân biệt nếu không tạo enumeration leak.

### 8.1. Trường hợp user xem tài liệu được chia sẻ

Ownership thuần `owner_sub == sub` không đủ cho tất cả sản phẩm. Có thể mở rộng thành:

~~~text
resource.tenantId == jwt.tenant_id
AND (
    resource.ownerSub == jwt.sub
    OR exists active ACL(resource.id, jwt.sub, "read")
    OR hasTrustedTenantRole(jwt.sub, tenant, "document-auditor")
)
~~~

Nhưng role auditor cần được gắn với **tenant hiện tại**, không phải một role toàn cục ở issuer. ACL/tenant membership nên được kiểm tra từ DB/policy engine có version/cache invalidation phù hợp; token permission chỉ là điều kiện **cần**, không tự thành điều kiện **đủ**.

### 8.2. Nếu token chứa nhiều tenants

Một JWT có `tenant_ids=["org-a","org-b"]` không nghĩa endpoint được bỏ tenant check. Khi client chọn active tenant qua path/header, server phải:

1. Lấy tenant ID từ request chỉ như **đối tượng xin truy cập**.
2. Kiểm tra tenant đó thuộc danh sách membership **đáng tin và còn hiệu lực** của caller.
3. Truy vấn dữ liệu kèm tenant predicate.
4. Không cho user thay tenant để nhìn tenant khác dù cùng `documents.read`.

Nếu membership thay đổi thường xuyên, nên kiểm tra trạng thái server-side thay vì dựa vào token dài hạn.

### 8.3. Nhiều IdP/issuers

`sub="alice"` từ issuer A **không** đồng nhất với `sub="alice"` từ issuer B. Dùng identity composite `issuer + subject` hoặc map từng issuer subject đến internal user ID đã được xác minh. Khi hỗ trợ multi-issuer, security config cần trusted issuers resolver và validators đúng. Không cho token của issuer lạ tự đưa `tenant_id` giống tenant nội bộ để vượt quyền.

### 8.4. Pagination và search cũng phải kiểm tra quyền

Không chỉ `GET /documents/{id}`. Mọi endpoint `GET /documents?query=...`, `GET /documents/count`, `GET /documents/export`, `GET /documents/{id}/attachments`, `PATCH`, `DELETE`, batch APIs và background jobs phải dùng cùng data-scope policy.

Với query list, **filter tại DB trước khi LIMIT/OFFSET**. Nếu tải toàn bộ documents rồi lọc ở Java sau phân trang, bạn có thể làm sai page counts, leak metadata hoặc tiêu tốn quá nhiều tài nguyên. Search index, cache, CDN và event streams cũng phải gắn tenant/owner policy tương đương.

## 9. Vai trò scope, business claim, role và ownership trong thiết kế

Một chính sách quyền cho API tài liệu có thể viết rõ:

~~~text
GET /documents/{id}
  require JWT trusted for documents-api
  AND SCOPE_documents.read
  AND PERM_documents:view
  AND active tenant membership
  AND (same owner OR explicit read ACL)
  AND not soft-deleted / document active

PATCH /documents/{id}
  require JWT trusted for documents-api
  AND SCOPE_documents.write
  AND PERM_documents:edit
  AND same tenant
  AND (owner OR approved editor ACL)
  AND allowed document state (not locked)
  AND optimistic lock/version matches
~~~

Điều kiện “resource owner” đôi khi cần suy rộng sang RBAC/ABAC/relationship-based access control:

| Mô hình | Ví dụ | Điểm lưu ý |
|---|---|---|
| **RBAC** | `ROLE_DOCUMENT_EDITOR` | Cần biết role áp trong tenant nào, không được globalize vô ý. |
| **ABAC** | Có tenant org-a + department finance + document classification internal | Claims/attributes cần đáng tin và mới. |
| **ReBAC/ACL** | User được share document qua ACL row | Đọc quyền từ quan hệ thực tế, revoke phải có hiệu lực. |
| **Owner-only** | `document.ownerSub == jwt.sub` | Đơn giản nhưng không hỗ trợ share/assistant/delegation nếu sản phẩm cần. |
| **Service account** | Token `client_credentials` cho batch export đã được phê duyệt | Quyền service tách với user; audit và scope tối thiểu. |

Bất kỳ role/permission nào cũng phải có **phạm vi áp dụng**. `documents:edit` có thể chỉ cho phép sửa documents trong tenant và trạng thái được phép, chứ không cấp toàn quyền toàn hệ thống.

### 9.1. Trường-level security và mass assignment

Đừng trả nguyên JPA/R2DBC entity với tất cả các trường rồi dựa vào frontend ẩn phần nhạy cảm. Dùng DTO cụ thể và mapping được review. Trong PATCH, chỉ nhận fields được phép đổi; không bind toàn bộ JSON trực tiếp vào entity có `ownerSub`, `tenantId`, `createdBy`, `status=APPROVED`.

Nếu quyền đọc metadata khác quyền đọc nội dung, tách `documents.metadata.read` và `documents.content.read` theo API/use case; đừng trả confidential body chỉ vì token có `documents.read` chung.

### 9.2. Cẩn thận với claim “roles” lấy từ user profile

Spring Security có thể map JWT business claim thành authority, **nhưng đó vẫn là dữ liệu từ token của issuer**. Không dùng một endpoint client có thể tự cập nhật profile field `role=admin` rồi IdP đưa thẳng vào token để cấp quyền. Claim security phải đến từ trusted identity/authorization workflow. Cần review ai được quyền sửa các mappings/groups ở IdP.

### 9.3. Thời gian thu hồi quyền

Access token còn sống đến `exp`. Khi người dùng bị chuyển tenant hoặc mất quyền sau issuance:

- Một API chỉ đọc claim cũ có thể còn cho phép thao tác đến khi token hết hạn.
- API rủi ro cao có thể tra active membership/ACL ở DB hoặc PDP mỗi request.
- Cần cache TTL/invalidation, bảo vệ policy backend nếu service down, quyết định fail-open hay fail-closed.
- Không nên tự ghi đè `role`/`tenant` trong HTTP context cho đến khi hết hạn token theo cách bypass validator.

## 10. Những lỗi phổ biến

**1. Chỉ kiểm tra SCOPE_documents.read, không kiểm tra owner.** User có token đúng scope vẫn đọc được document của Bob → BOLA. Cần row ownership/ACL predicate.

**2. Chỉ kiểm tra owner ID do request cung cấp.** User có thể đổi `ownerId` hoặc `tenantId` trong URL/body. Lấy identity đã xác minh từ Authentication, đối chiếu server-side data.

**3. Tin claim chưa verify JWT.** Decode Base64 không phải verify signature. Dùng Resource Server JWT decoder với trusted issuer/JWKS.

**4. Không xác minh audience.** Access token dành cho API khác có thể được dùng nhầm. Cấu hình `audiences`/custom validator.

**5. Dùng `hasRole("documents.read")` thay cho `hasAuthority("SCOPE_documents.read")`.** Prefix role và scope khác nhau, dẫn đến deny sai hoặc policy rối.

**6. Custom claim converter làm mất scopes.** Nếu converter chỉ map `permissions`, rule SCOPE_ sẽ không thấy scope. Kết hợp `JwtGrantedAuthoritiesConverter` mặc định và custom allowlist.

**7. Map tất cả business strings thành ROLE_ADMIN tùy ý.** Claim schema/issuer/tenant không được kiểm tra có thể gây privilege escalation. Dùng allowlist.

**8. Claim quyền của tenant A được dùng cho tenant B.** Tenant permission phải scoped, không chỉ có role name toàn cục.

**9. Nhầm email với `sub`.** Email có thể đổi/trùng/chưa verify; dùng stable subject và issuer, hoặc internal ID mapping.

**10. JWT còn hạn nên chắc quyền vẫn hợp lệ.** Role/ACL có thể bị revoke; kiểm tra fresh policy khi cần.

**11. Chỉ kiểm tra quyền ở controller, repository vẫn có hàm đọc mọi tenant.** Các entrypoints khác có thể bypass. Đặt guard tại service/repository và test tất cả.

**12. Lấy row rồi tự gửi response trước khi kiểm tra owner.** Phải kiểm tra trước khi emit dữ liệu; tốt hơn lọc tại SQL.

**13. Lấy 1.000 rows rồi lọc ownership sau pagination.** Sai page counts, có thể lộ metadata; lọc tại query trước LIMIT.

**14. Ẩn nút frontend và nghĩ API đã bảo mật.** Attacker có thể gọi HTTP trực tiếp; server phải enforce.

**15. Trả 403 cho owner mismatch nhưng 404 cho ID không có một cách không chủ đích.** Có thể cho phép enumeration; chọn policy response đồng nhất khi cần.

**16. Cập nhật bằng find→check→save thiếu transaction/conditional predicate.** TOCTOU khi quyền/owner thay đổi; dùng conditional UPDATE/transaction/version.

**17. Quên bảo vệ export, search, count, attachment hoặc batch endpoint.** BOLA có thể nằm ở route phụ.

**18. Bật `csrf.disable()` cho app có cookie/session.** Chỉ tắt với bearer-only stateless API được đánh giá CSRF; với cookie auth vẫn cần biện pháp phù hợp.

**19. Dùng `mockJwt()` rồi tuyên bố đã test chữ ký JWT.** Mock test bypass decoder; phải test signed token/issuer/audience riêng.

**20. Dùng authorization_code user token như service account cho mọi tenant.** Phân biệt delegated user access và client_credentials service policy.

**21. Tự log raw Authorization/JWT để debug.** JWT thường có PII và Bearer credential; sanitize logs/traces.

**22. Không có negative tests.** Happy path 200 chưa chứng minh BOLA được chặn; test Bob, tenant khác, scope/permission thiếu.

**23. Không bảo vệ claim parser trước kiểu dữ liệu bất ngờ.** Nếu `app_permissions` là string/map không đúng schema, deny-by-default thay vì crash/cấp quyền.

**24. Chạy JDBC blocking trên Reactor event loop.** Dùng R2DBC hoặc cách bridge được thiết kế, không `block()` trong WebFlux chain.

**25. Trộn nhiều issuers nhưng dùng mỗi `sub` làm khóa user.** Hai issuers có thể trùng sub, cần issuer binding.

## 11. Checklist production

1. **Trusted issuer/JWKS:** JWT chỉ được chấp nhận từ issuer cấu hình và ký bằng algorithm/keys được tin cậy?
2. **Audience:** `aud` đúng resource API? Có negative test token audience khác?
3. **Expiry:** `exp`/`nbf`/clock skew được kiểm soát? Revoke/denylist policy có cần?
4. **Scope mapping:** `scope`/`scp` chuyển đúng `SCOPE_` authorities, không nhầm `ROLE_`?
5. **HTTP method:** GET/PATCH/POST/DELETE có quyền riêng; chưa khai báo phải deny?
6. **Business claims:** Schema do trusted issuer kiểm soát, quyền được allowlist, sai kiểu/missing → deny?
7. **Method security:** `@PreAuthorize` có thực thi trên `Mono/Flux` và không bị bypass qua entrypoints khác?
8. **Ownership:** Resource được tra với trusted `sub` + `tenant_id`/issuer, không dùng owner do client tự nhập?
9. **Multi-tenancy:** Tenant filters áp dụng trong database/index/cache/search/export?
10. **ACL:** Nếu share/transfer ownership, policy/permissions được xác định rõ, revocation có hiệu lực?
11. **Data minimization:** DTO không tiết lộ owner/tenant/private fields khi không cần?
12. **Write safety:** Conditional UPDATE, optimistic locking, transaction, validation, mass-assignment protection?
13. **Response policy:** 401/403/404 có nghĩa rõ và không tạo enumeration leak?
14. **Security tests:** Có test thiếu token/scope/permission, sai owner/tenant, đúng owner, write negative/positive?
15. **Decoder tests:** Có test chữ ký, issuer, audience, expiry và JWKS rotation với token thật/fake signed?
16. **Service accounts:** M2M token chỉ có quyền rõ, không tự bypass user ownership?
17. **Token freshness:** Quyền có thể bị revoke giữa thời hạn token; có membership/ACL lookup hoặc TTL hợp lý?
18. **HTTP security:** HTTPS/HSTS, no token logging, limit headers/size/rate, handling 401/403?
19. **CSRF:** Bearer-only vs browser cookie auth được tách rõ; không disable CSRF sai?
20. **Reactive correctness:** Không block/subscribe thủ công; R2DBC/async DB operations trong chain?
21. **Observability:** Audit denial lý do server-side mà không lộ raw JWT/PII?
22. **Review định kỳ:** Khi thêm claim/permission/scope/API, update policy table và regression tests.

## 12. Câu hỏi tự kiểm tra

**1.** JWT có `scope="documents.read"`. Có được GET mọi document không?

**Đáp án:** Không. Scope là quyền cho một loại thao tác; vẫn cần business permission và ownership/tenant/ACL theo resource.

**2.** Spring Security mặc định biến `scope="documents.read"` thành gì?

**Đáp án:** Authority `SCOPE_documents.read`, có thể kiểm tra bằng `hasAuthority("SCOPE_documents.read")`.

**3.** Tại sao `hasRole("SCOPE_documents.read")` không tương đương?

**Đáp án:** `hasRole` thường dùng prefix `ROLE_`, còn OAuth scopes có prefix `SCOPE_`.

**4.** Token có cả scope và `app_permissions`, có còn cần tra row DB không?

**Đáp án:** Có. JWT không chứa quan hệ sở hữu đáng tin cho từng resource đang thay đổi; cần đối chiếu row/ACL server-side.

**5.** Nếu user dùng token Alice để đọc row của Bob trong cùng tenant thì sao?

**Đáp án:** Bị từ chối bởi owner predicate; demo dùng 404 để che resource existence.

**6.** Nếu token có `tenant_id="org-a"` nhưng row thuộc `org-b` dù ownerSub đều là Alice?

**Đáp án:** Bị từ chối; cùng user ở hai tenants không tự được quyền xem dữ liệu tenant kia.

**7.** Tại sao phải có `audiences` ở Resource Server?

**Đáp án:** Để không nhận access token được cấp cho một resource/API khác, dù chữ ký và scopes trông đúng.

**8.** Khi nào trả 401, 403 và 404?

**Đáp án:** 401 khi chưa/không xác thực được; 403 cho token verified nhưng thiếu scope/permission; 404 nếu row không có/không thuộc owner và policy muốn che existence.

**9.** Dùng `mockJwt()` đã test decoder signature/issuer/audience chưa?

**Đáp án:** Chưa. `mockJwt` chủ yếu setup SecurityContext giả; cần signed JWT/JWKS test riêng.

**10.** Tại sao cần test converter khác với test WebTestClient mockJwt?

**Đáp án:** Vì mockJwt authorities có thể bỏ qua converter thực của Resource Server; unit test converter chứng minh scope + business claim mappings được cấu hình đúng.

**11.** Tại sao không để client gửi `ownerSub` trong JSON PATCH?

**Đáp án:** Client có thể sửa giá trị để giả làm owner; server phải dùng verified JWT claims rồi kiểm tra row thực tế.

**12.** JWT roles thay đổi mà token vẫn chưa hết hạn, quyền có tự cập nhật ngay không?

**Đáp án:** Không. JWT có dữ liệu tại thời điểm phát; cần token TTL hợp lý hoặc authorization state server-side cho nghiệp vụ có yêu cầu revoke nhanh.

**13.** Nếu dùng nhiều issuers, nên nhận diện user bằng mỗi `sub`?

**Đáp án:** Không. Cần composite issuer + subject hoặc mapping đến internal user ID vì sub chỉ duy nhất trong phạm vi issuer.

**14.** Một HTTP GET được bảo vệ bằng scope nhưng DELETE cùng path chưa có rule, nên làm gì?

**Đáp án:** Deny DELETE theo fallback; nếu thêm use case thì khai báo scope/permission riêng và kiểm tra ownership/ACL cho delete.

## Tài liệu chính thức

- Spring Security — Reactive Resource Server JWT, claim `scope` → `SCOPE_`, converter, signature/issuer validation: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive Method Security, `@EnableReactiveMethodSecurity` và `@PreAuthorize`: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security — Reactive OAuth2 Resource Server API: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/index.html
- Spring Security — Reactive OAuth2 Testing với `mockJwt()`: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Boot 3.5 — Resource Server properties `issuer-uri`, `jwk-set-uri`, `audiences`: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- `JwtGrantedAuthoritiesConverter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html
- `ReactiveJwtAuthenticationConverterAdapter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html
- OWASP API Security — Broken Object Level Authorization (API1:2023): https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
