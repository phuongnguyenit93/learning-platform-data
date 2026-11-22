# Thêm, thu hồi tenant và vòng đời cấu hình được tin cậy

Một **Spring Security OAuth 2.0 / OIDC Resource Server** phục vụ nhiều tenant có thể cần xác thực Access Token từ nhiều Authorization Server (AS), OIDC realm hoặc issuer. Vấn đề lớn hơn việc cấu hình nhiều JWT decoder là **xác định lúc nào một tenant hoặc issuer được phép trở thành nguồn tin cậy**, và **làm sao ngừng tin nó sau khi bị đình chỉ hoặc thu hồi**, kể cả khi token cũ vẫn còn hạn và decoder đã được cache.

Ví dụ SaaS quản lý đơn hàng phục vụ:

| Tenant | Issuer được duyệt | Trạng thái trust |
| --- | --- | --- |
| `alpha` | `https://id.alpha.example.test/realms/main` | ACTIVE |
| `beta` | `https://login.beta.example.test/oauth2` | ACTIVE |
| `gamma` | `https://identity.gamma.example.test` | SUSPENDED |

Một JWT có chữ ký hợp lệ của gamma **không được tiếp tục mở quyền truy cập** khi gamma đã bị đình chỉ. Tương tự, JWT từ một issuer hoàn toàn mới **không được tự làm Resource Server tải JWKS và chấp nhận issuer đó**, dù chữ ký có thể xác minh được bằng key do chính bên phát hành công bố.

**Nguyên tắc cốt lõi:** *Issuer, JWKS URI, audience và quyền chấp nhận tenant là cấu hình bảo mật do control plane quản lý, không phải dữ liệu mà request hoặc token chưa xác thực có thể tự khai để được tin cậy.*

Bài học tập trung vào **thêm, kích hoạt, đình chỉ, thu hồi, chuyển đổi và ngừng sử dụng tenant**, thiết kế **trusted registry có phiên bản**, ranh giới xác minh JWT, cache `AuthenticationManager`/`JwtDecoder`, đồng bộ nhiều replicas, lỗi issuer-confusion/SSRF, kiểm thử trạng thái và quy trình vận hành. Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x**, chủ yếu với **Servlet Resource Server**; phần cuối trình bày tương đương cho WebFlux.

## 1. Phân biệt tenant, issuer, audience và principal

**Tenant** là ranh giới khách hàng/tổ chức và dữ liệu trong ứng dụng. **Issuer** là thực thể phát hành Access Token, được nhận biết bằng `iss`. **Audience** xác định resource mà token nhắm đến. **Subject** `sub` nhận diện chủ thể trong phạm vi issuer. **JWT signature** chứng minh token được ký bằng key thích hợp, nhưng chỉ có ý nghĩa sau khi Resource Server đã xác định **key/issuer nào được tin**.

~~~text
Tenant alpha
  localTenantId = 6dca...
  issuer        = https://id.alpha.example.test/realms/main
  audience      = orders-api
  users/orders  = dữ liệu riêng của alpha

Tenant beta
  localTenantId = a28e...
  issuer        = https://login.beta.example.test/oauth2
  audience      = orders-api
  users/orders  = dữ liệu riêng của beta
~~~

Không nên giả định một quan hệ 1–1 tuyệt đối:

- **Một issuer phục vụ nhiều tenants:** ví dụ các công ty dùng chung một IdP. Khi đó `iss` không đủ để quyết định tenant.
- **Một tenant có nhiều issuers hợp lệ tạm thời:** ví dụ migration sang IdP mới; cần quản lý từng binding có thời hạn và chính sách riêng.
- **Một issuer có nhiều client IDs và nhiều audiences:** token có chữ ký đúng chưa chắc dành cho API hiện tại.
- **Cùng một `sub` ở hai issuers:** có thể đại diện hai người hoàn toàn khác nhau. Khi cần liên kết tài khoản nội bộ, dùng cặp **`(iss, sub)` đã xác minh**, không chỉ `sub` hay email.

### 1.1. Bốn câu hỏi bảo mật độc lập

| Câu hỏi | Quyết định từ đâu? | Ví dụ |
| --- | --- | --- |
| Tenant hiện được phục vụ không? | **Trusted tenant registry** đã được phê duyệt. | Gamma SUSPENDED → không chấp nhận. |
| Token đáng tin không? | Decoder/introspection từ issuer/JWKS đã tin, `aud`, `exp`, thuật toán. | JWT alpha có chữ ký và audience đúng. |
| Principal có quyền ở tenant này không? | Claims đã xác minh + local account/membership. | User-42 là nhân viên alpha. |
| Principal có quyền trên tài nguyên cụ thể không? | HTTP scopes + domain authorization. | Order-77 thuộc alpha và caller được đọc. |

**ACTIVE tenant** chỉ là điều kiện đầu tiên. Nó không tự cấp mọi scope và không làm các bản ghi của tenant đó trở thành tài sản công khai.

## 2. Vì sao không được tự tin issuer lấy từ JWT?

JWT payload là dữ liệu có thể đọc được trước khi chữ ký được xác minh. Attacker hoàn toàn có thể tạo:

~~~json
{
  "iss": "https://id.attacker.example.test",
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "admin.manage"
}
~~~

Giả sử ứng dụng có logic sai:

~~~text
Nhận JWT
   |
   v
Đọc iss chưa xác minh
   |
   v
Tự tải /.well-known/openid-configuration của iss
   |
   v
Lấy jwks_uri của issuer do attacker kiểm soát
   |
   v
Xác minh JWT bằng public key của attacker
   |
   v
Chấp nhận token và scope admin.manage  <-- LỖ HỔNG
~~~

Chữ ký đúng theo một public key **không đủ** nếu chính token được quyền chỉ định public key của mình. Một issuer chỉ được dùng để xác thực sau khi **control plane đã phê duyệt**.

### 2.1. Các input có thể bị giả mạo

| Input | Đáng tin trước khi token validation? | Cách sử dụng an toàn |
| --- | --- | --- |
| Claim `iss` của JWT | **Không** | Có thể làm *routing hint* khi được đối chiếu với trusted allowlist; phải validate lại sau decode. |
| JWT header `kid` | **Không** | Chọn key trong **JWKS đã cấu hình**, không chọn nguồn JWKS mới. |
| JWT header `jku` hoặc `x5u` | **Không** | Không tự gửi HTTP request tới URL được token khai báo. |
| Claim `tenant_id`, `sub`, `scope` trước xác minh | **Không** | Chỉ dùng sau JWT signature/issuer/audience validation. |
| Path `/api/tenants/alpha` | **Không phải permission** | Chọn *tenant candidate* trong registry, sau đó xác minh token/membership. |
| Header `X-Tenant-ID` | **Không** | Không thay thế đăng nhập, issuer, account membership. |
| `Host`/`X-Forwarded-Host` từ internet | Có thể bị giả/sai cấu hình proxy | Chỉ dùng với trusted gateway/canonical host routing. |
| Approved registry snapshot | **Có**, nếu nguồn, integrity và version được kiểm soát | Chọn issuer/JWKS/audience và chính sách cho phép. |

### 2.2. Những rủi ro cần thiết kế chống ngay từ đầu

1. **Issuer confusion:** issuer bất kỳ được chấp nhận chỉ vì JWT tự khai `iss`.
2. **SSRF:** ứng dụng lấy metadata/JWKS từ URL do client kiểm soát, chạm vào localhost, private IP, cloud metadata endpoint hoặc máy chủ nội bộ.
3. **Algorithm confusion:** đổi issuer rồi cho phép thuật toán không được policy phê duyệt.
4. **Cross-tenant BOLA:** token hợp lệ của A dùng để đọc đơn hàng B vì chỉ kiểm tra scope.
5. **Stale trust cache:** một `AuthenticationManager` đã cache tiếp tục chấp nhận issuer sau khi tenant REVOKED.
6. **Configuration replay:** node nhận sự kiện ACTIVE cũ sau sự kiện REVOKED mới và vô ý mở lại tenant.
7. **Unauthorized administration:** API public hoặc quản trị viên nghiệp vụ được phép sửa issuer/JWKS URI mà không qua phê duyệt bảo mật.

## 3. Tách control plane khỏi data plane

Một hệ thống nhiều tenant nên có **hai ranh giới**:

~~~text
                 CONTROL PLANE
  Tenant onboarding / Security administration
          |
          +-- Verify ownership
          +-- Verify issuer/JWKS/audience/alg
          +-- Approval / audit / revision
          +-- ACTIVE / SUSPENDED / REVOKED
          |
          v
   Trusted configuration snapshot
          |
      +---+--------------------+
      |                        |
 Resource Server A        Resource Server B
      |                        |
      +------------+-----------+
                   |
                DATA PLANE
                   |
 HTTP Bearer -> trusted tenant check -> JWT verification
                   |
              scope + domain policy
                   |
              customer data
~~~

**Control plane** có quyền thay đổi *hệ thống sẽ tin issuer nào*. **Data plane** chỉ sử dụng snapshot đã được phê duyệt để xác thực request, không bao giờ tự đăng ký issuer khi thấy một token mới.

Nguồn cấu hình có thể là database với administrative service, GitOps được review hoặc configuration service. Dù chọn công nghệ nào, cần **RBAC/approval**, audit, validation, phiên bản, phân phối và cách thu hồi hiệu lực.

### 3.1. Cấu hình bảo mật không phải “tenant profile” thông thường

Thay tên hiển thị của tenant ít rủi ro hơn thay `jwkSetUri`: một người có thể sửa JWKS URI về khóa của mình sẽ có khả năng khiến Resource Server tin token tự ký. Vì thế các trường:

- Issuer/JWKS URI và thuật toán JWS.
- Audience/resource và token profile.
- Chính sách xác thực introspection nếu dùng opaque token.
- Trạng thái ACTIVE/SUSPENDED/REVOKED.

phải được quản lý như **trust configuration**, không mở sửa qua endpoint quản lý thông tin doanh nghiệp bình thường.

## 4. State machine của vòng đời trust tenant

Một hệ thống có thể định nghĩa:

~~~text
REQUESTED
    |
    v
VERIFYING
    |
    v
APPROVED
    |
    v
ACTIVE -------------------> REVOKED --> RETIRED
    |
    v
SUSPENDED
    |
    +-- re-verification / approval --> ACTIVE (revision mới)
    |
    +-----------------------------> REVOKED
~~~

Đây là **state machine của ứng dụng**, không phải trạng thái Spring Security/OAuth tự cung cấp.

| Trạng thái | Ý nghĩa | Token được tiếp tục xác thực? |
| --- | --- | --- |
| `REQUESTED` | Có đề nghị tạo tenant. | **Không.** |
| `VERIFYING` | Đang kiểm tra IdP, ownership, security contract. | **Không.** |
| `APPROVED` | Đã duyệt nhưng chưa kích hoạt/phân phối. | **Không.** |
| `ACTIVE` | Được phép tiếp tục đến JWT validation theo config hiện hành. | **Có điều kiện.** |
| `SUSPENDED` | Tạm dừng vì sự cố/quy trình kinh doanh. | **Không.** |
| `REVOKED` | Thu hồi quyền tin cậy. | **Không.** |
| `RETIRED` | Ngừng sử dụng, lưu tombstone/audit. | **Không.** |

Quy tắc code phải là **allow only ACTIVE**, không phải “allow mọi trạng thái khác REVOKED”. Nếu trạng thái null/unknown/cấu hình hỏng, **fail closed**.

### 4.1. SUSPENDED khác REVOKED nhưng đều phải bị chặn

`SUSPENDED` có thể được mở lại sau khi xem xét; `REVOKED` thường là quyết định chấm dứt trust hoặc phản ứng sự cố nghiêm trọng. Tuy nhiên, cả hai đều cần chặn **request mới** tại data plane. Khác biệt nằm ở **chính sách reactivation, phê duyệt và audit**, không nằm ở việc cho phép token đi qua trong lúc chờ xử lý.

### 4.2. Vì sao cần tombstone?

Nếu xóa một tenant khỏi database, một event `ACTIVE` cũ đến trễ có thể tự tạo lại bản ghi và kích hoạt tenant. Lưu `REVOKED`/`RETIRED` cùng **revision lớn hơn** giúp chống replay và ngăn tái sử dụng slug/issuer không kiểm soát.

## 5. Dạng dữ liệu trusted configuration

Ví dụ bản ghi sau đã qua phê duyệt:

~~~yaml
tenantKey: alpha
localTenantId: tenant-alpha-uuid
issuer: https://id.alpha.example.test/realms/main
jwkSetUri: https://id.alpha.example.test/realms/main/protocol/openid-connect/certs
audience: orders-api
allowedJwsAlgorithms:
  - RS256
status: ACTIVE
revision: 18
approvedBy: security-approver
approvedAt: "2026-11-15T08:30:00Z"
~~~

| Trường | Ý nghĩa | Yêu cầu |
| --- | --- | --- |
| `tenantKey` | Slug để định tuyến. | Canonical, unique, không làm bằng chứng quyền. |
| `localTenantId` | ID tenant trong database. | Dùng để partition dữ liệu, không lấy từ body client. |
| `issuer` | `iss` JWT được phép. | Exact match, URL đã phê duyệt. |
| `jwkSetUri` | JWKS lấy public keys. | HTTPS/allowlist, không lấy từ JWT header. |
| `audience` | Resource ID yêu cầu trong `aud`. | Bắt buộc kiểm tra. |
| `allowedJwsAlgorithms` | Danh sách thuật toán được phép. | Không trust `none`/downgrade. |
| `status` | Quyền chấp nhận tenant. | **Chỉ ACTIVE**. |
| `revision` | Phiên bản config tenant. | Tăng khi issuer/JWKS/audience/status đổi. |
| Approval/audit | Ai duyệt, khi nào, lý do. | Nguồn tin cậy với RBAC và integrity. |

**Cấu hình phải có nguồn đáng tin duy nhất**. Token có `tenant_id` hoặc issuer string phù hợp không thể tự thay đổi nội dung bảng này.

## 6. Quy trình thêm một tenant từ đầu đến ACTIVE

Giả sử tenant `delta` muốn dùng `https://id.delta.example.test/realm`.

### 6.1. Tiếp nhận yêu cầu không kích hoạt trust

~~~text
createTenant(
  tenantKey = delta,
  candidateIssuer = https://id.delta.example.test/realm
)

status = REQUESTED
revision = 1
canAuthenticateInProduction = false
~~~

Đây mới là **yêu cầu**. Không để `POST /admin/tenants` tự động tạo JWT decoder ngay khi request tới, dù người yêu cầu mang một token còn hạn.

### 6.2. Xác minh ownership và quyền quản trị

Tùy hệ thống:

- Xác nhận người yêu cầu có quyền đại diện tổ chức.
- Xác minh quyền kiểm soát domain hoặc IdP registration.
- Đối chiếu hợp đồng, organization ID và tenant owner.
- Thực hiện two-person approval cho thay đổi trust nhạy cảm.
- Tách quyền **security platform admin** khỏi quyền quản lý nhân viên/đơn hàng.

Một email khớp với domain của tenant hoặc claim `email_verified=true` **không tự chứng minh** caller được phép khiến SaaS tin một issuer mới.

### 6.3. Kiểm tra issuer và metadata ở control plane

Chỉ sau khi candidate được chấp nhận qua administrative boundary mới truy vấn metadata/discovery. Kiểm tra:

1. **HTTPS** với xác minh TLS certificate và hostname đầy đủ.
2. Host nằm trong egress policy/allowlist phù hợp.
3. Không cho URL dẫn tới loopback, link-local, private IP hoặc cloud metadata endpoint khi chưa có cơ chế mạng được duyệt.
4. Không tự theo redirect sang host không được phép.
5. Bảo vệ DNS rebinding và giải quyết hostname theo network policy.
6. Metadata issuer công bố **khớp issuer đã phê duyệt**.
7. `jwks_uri` là endpoint HTTPS được cho phép; giới hạn response size, redirect depth và timeout.
8. Không dùng claim `iss` hoặc header `jku` của JWT user gửi lên để tự chọn nơi fetch.

OIDC Discovery và OAuth Authorization Server Metadata giúp tìm cấu hình của một issuer **đã tin**, không thay quy trình phê duyệt.

### 6.4. Kiểm tra hợp đồng token

Phải thống nhất:

- Issuer `iss` exact string (kể cả path/realm).
- Audience `aud` dành cho đúng Resource Server.
- Loại token: **OAuth 2.0 Access Token**, không dùng ID Token thay thế.
- Thuật toán chữ ký, JWKS key rotation, `kid`.
- Thời hạn `exp`, `nbf`, clock skew và token lifetime.
- Cách ánh xạ `scope`/`scp` → `SCOPE_...` authorities.
- Cách định danh user/service principal, tenant membership và local account.
- Sender-constrained token nếu kiến trúc có mTLS/DPoP.

**Signature valid không đủ** khi `aud` không dành cho API hoặc token type sai.

### 6.5. Kiểm thử sandbox trước activation

Trong môi trường kiểm thử tách biệt:

~~~text
Valid signed Access Token đúng issuer/aud -> có thể được chấp nhận
Invalid signature -> từ chối
Wrong issuer -> từ chối
Wrong audience -> từ chối
Expired token -> từ chối
Unknown tenant -> từ chối
Other tenant's account/order -> từ chối
~~~

Không bật issuer mới trong production chỉ để kiểm thử xem việc ký token có hoạt động không.

### 6.6. Phê duyệt, publish và kích hoạt

Chuyển `VERIFYING → APPROVED → ACTIVE` phải gắn với:

1. Administrative permission và approval.
2. Tenant revision tăng đơn điệu.
3. Immutable trusted configuration snapshot mới.
4. Audit actor, approver, timestamp, reason, old/new state.
5. Phân phối snapshot đến Resource Server instances.
6. Canary/health kiểm tra decoder/JWKS và tenant routing.
7. Xác nhận rollout trước khi cho tenant đi vào đường production bình thường.

Trong hệ thống phân phối bất đồng bộ, Admin UI nên phân biệt **“đã commit control-plane change”** với **“đã được mọi serving nodes áp dụng”**; không tuyên bố rollout hoàn tất khi có replica chưa cập nhật.

## 7. Xuất bản cấu hình theo snapshot bất biến và revision

Nếu update các trường `issuer`, `jwksUri`, `audience`, `status` độc lập, một request có thể thấy **issuer mới nhưng JWKS cũ**. Cách an toàn hơn là **tạo một snapshot mới đã validate**, rồi atomic swap.

### 7.1. Mô hình Java

~~~java
import java.net.URI;
import java.util.Map;

enum TenantState {
    REQUESTED, VERIFYING, APPROVED,
    ACTIVE, SUSPENDED, REVOKED, RETIRED
}

record TenantTrustConfig(
    String tenantKey,
    String localTenantId,
    String issuer,
    URI jwksUri,
    String audience,
    long revision,
    TenantState state
) {
    boolean acceptsTokens() {
        return state == TenantState.ACTIVE;
    }
}

record TenantTrustSnapshot(
    long generation,
    Map<String, TenantTrustConfig> tenants
) {
    TenantTrustSnapshot {
        tenants = Map.copyOf(tenants);
    }
}
~~~

`Map.copyOf` giữ cấu trúc map bất biến đối với consumer. Các record này chỉ chứa **trusted values sau validation**; chúng không tự chứng minh URI có an toàn hay snapshot do control plane đúng quyền phát hành.

### 7.2. Atomic registry

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

public final class TrustedTenantRegistry {

    private final AtomicReference<TenantTrustSnapshot> current =
        new AtomicReference<>(
            new TenantTrustSnapshot(0, Map.of()));

    public Optional<TenantTrustConfig> findActive(String key) {
        TenantTrustConfig config =
            current.get().tenants().get(key);

        return config != null && config.acceptsTokens()
            ? Optional.of(config)
            : Optional.empty();
    }

    public long generation() {
        return current.get().generation();
    }

    public void publishApprovedSnapshot(
            TenantTrustSnapshot candidate) {

        // Chỉ gọi từ trusted control-plane adapter:
        // xác thực nguồn, approval, schema và integrity trước.
        for (;;) {
            TenantTrustSnapshot old = current.get();

            if (candidate.generation() <= old.generation()) {
                throw new IllegalArgumentException(
                    "Old or replayed tenant trust configuration");
            }

            if (current.compareAndSet(old, candidate)) {
                return;
            }
        }
    }
}
~~~

**Tác dụng:** node không vô ý chấp nhận snapshot **generation thấp hơn** sau khi đã nhận revocation mới. Việc publish dùng `AtomicReference` giúp các requests trên một JVM nhìn thấy **một snapshot hoàn chỉnh**, không trộn field cũ/mới.

**Giới hạn:** mã ví dụ không triển khai admin authorization, persistent storage hoặc chữ ký snapshot. Production cần bảo vệ adapter cập nhật, tránh gọi public method bằng data không xác minh. `generation` phải được sinh **đơn điệu tại source of truth**; mỗi replica tự tăng số đếm không đủ cho consistency toàn cluster.

### 7.3. Hai loại phiên bản

**Tenant revision** thay đổi khi trạng thái/issuer/JWKS/audience/policy của một tenant thay đổi.

**Global generation** thay đổi khi toàn bộ trusted config snapshot thay đổi.

Cache manager theo `(tenantKey, revision)` để không dùng decoder cũ khi tenant cấu hình mới. Dùng global generation để xử lý snapshot ngoài thứ tự, phục hồi node và xác nhận rollouts.

## 8. Chọn tenant từ request: locator không phải authorization

Các ứng dụng thường định tuyến bằng:

- URL path: `/api/tenants/alpha/orders/42`.
- Hostname: `alpha.api.example.test` sau trusted gateway.
- `iss` chưa xác minh, **chỉ làm hint** để chọn issuer đã có trong registry.

Ví dụ path:

~~~http
GET /api/tenants/alpha/orders/42
Authorization: Bearer ACCESS_TOKEN
~~~

Luồng:

~~~text
Route alpha
   |
   v
registry.findActive("alpha")
   |
   +-- empty -> reject
   |
   v
config issuer/JWKS/audience của alpha
   |
   v
JWT verification (signature, iss, aud, exp, alg)
   |
   v
Đối chiếu principal với membership alpha
   |
   v
Đọc order theo (tenantId=alpha, orderId=42, permissions)
~~~

Một caller chỉ cần đổi path từ `alpha` sang `beta` **không được làm API tự chuyển quyền sang beta**. Decoder theo beta phải từ chối issuer alpha nếu hai issuer khác nhau; nếu cùng issuer, **membership và domain policy** phải chặn.

### 8.1. Trusted router và Host headers

Nếu lấy tenant từ `Host`/`X-Forwarded-Host`, gateway cần:

- Chỉ cho phép registered hosts và SNI/TLS phù hợp.
- Strip hoặc overwrite `Forwarded`/`X-Forwarded-Host` từ nguồn internet chưa tin.
- Không để header user điều khiển issuer/JWKS URL.
- Chuẩn hóa hostname/path/URL encoding trước khi định tuyến.
- Bảo đảm locator và API domain authorization dùng cùng một tenant ID nội bộ.

Slug ở URL chỉ giúp tìm tenant candidate. Nó **không chứng minh user là thành viên** tenant đó.

## 9. Cache AuthenticationManager: bẫy khi thu hồi tenant

Trong Spring Security Servlet, có thể dùng **`AuthenticationManagerResolver<HttpServletRequest>`** để chọn authentication manager theo tenant. Manager cho mỗi issuer có thể chứa `NimbusJwtDecoder`, JWKS cache và validators.

Vấn đề:

~~~text
T0: alpha ACTIVE, revision 7
T1: Resolver tạo manager và cache vào map["alpha"]
T2: Control plane chuyển alpha sang REVOKED
T3: map["alpha"] vẫn chứa manager cũ
T4: JWT alpha còn exp, chữ ký vẫn xác minh được
T5: Nếu resolver trả manager cũ không kiểm tra status
    -> Có thể chấp nhận token của tenant đã revoke!
~~~

Chỉ **xóa issuer khỏi danh sách** hoặc chỉ **xóa một row trong DB** không đảm bảo cached managers không còn hoạt động. Cần một **runtime ACTIVE gate tại mỗi lần request**, cùng revisioned cache/invalidation.

### 9.1. Contract của tenant locator

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;

public interface TenantRequestLocator {
    Optional<String> locate(HttpServletRequest request);
}
~~~

Triển khai `locate` phải nhận canonical tenant key từ routing đáng tin, validate slug/path/URL encoding và không coi kết quả là permission. Bỏ qua việc tự nối URL từ tenant key.

### 9.2. Versioned manager cache và runtime gate

Ví dụ dùng Caffeine để giới hạn bộ nhớ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import jakarta.servlet.http.HttpServletRequest;
import java.time.Duration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;

record ManagerKey(String tenantKey, long revision) {}

public final class TrustedTenantManagerResolver
        implements AuthenticationManagerResolver<HttpServletRequest> {

    private final TrustedTenantRegistry registry;
    private final TenantRequestLocator locator;

    private final Cache<ManagerKey, AuthenticationManager> managers =
        Caffeine.newBuilder()
            .maximumSize(500)
            .expireAfterAccess(Duration.ofMinutes(30))
            .build();

    public TrustedTenantManagerResolver(
            TrustedTenantRegistry registry,
            TenantRequestLocator locator) {
        this.registry = registry;
        this.locator = locator;
    }

    @Override
    public AuthenticationManager resolve(HttpServletRequest request) {
        String tenantKey = locator.locate(request)
            .orElseThrow(() -> new BadCredentialsException(
                "Tenant is not accepted"));

        TenantTrustConfig config = registry.findActive(tenantKey)
            .orElseThrow(() -> new BadCredentialsException(
                "Tenant is not accepted"));

        ManagerKey key =
            new ManagerKey(tenantKey, config.revision());

        AuthenticationManager delegate = managers.get(
            key, ignored -> createManager(config));

        // Không trả thẳng cached delegate.
        // Re-check để config cũ không được dùng như trust mới.
        return authentication -> {
            requireCurrentRevision(tenantKey, config.revision());
            var result = delegate.authenticate(authentication);
            requireCurrentRevision(tenantKey, config.revision());
            return result;
        };
    }

    private void requireCurrentRevision(
            String tenantKey, long expected) {
        TenantTrustConfig now = registry.findActive(tenantKey)
            .orElseThrow(() -> new BadCredentialsException(
                "Tenant is not accepted"));

        if (now.revision() != expected) {
            throw new BadCredentialsException(
                "Tenant trust revision changed");
        }
    }

    private AuthenticationManager createManager(
            TenantTrustConfig config) {

        // Chỉ JWKS URI đã được control plane phê duyệt.
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(config.jwksUri().toString())
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(config.audience())
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        OAuth2ErrorCodes.INVALID_TOKEN,
                        "Audience not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(
                    config.issuer()),
                audienceValidator));

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);
        return provider::authenticate;
    }
}
~~~

**Ý nghĩa của các quyết định:**

- `registry.findActive` kiểm tra **ACTIVE mỗi request**, không chỉ lần đầu manager được tạo.
- Cache key có **tenant revision**, ngăn dùng manager cũ khi issuer/JWKS/audience/status đổi.
- Wrapper `requireCurrentRevision` kiểm tra lại trước/sau khi gọi manager để hạn chế race.
- Decoder lấy JWKS URI **chỉ từ approved config**, không phải token header `jku`.
- `JwtValidators.createDefaultWithIssuer` buộc issuer và các validation mặc định; validator riêng kiểm tra audience.
- `jwsAlgorithm(RS256)` là policy minh họa; nếu issuer dùng ES256, phải cấu hình allowlist thuật toán đã phê duyệt, không tự suy thuật toán từ JWT header.
- Caffeine giới hạn số managers, nhưng vẫn cần eviction/invalidation sau configuration changes.

**Giới hạn quan trọng:** hai lần kiểm tra revision không tạo ra bảo đảm nguyên tử giữa revoke và toàn bộ nghiệp vụ. Request có thể đã qua authentication trước khi control plane revoke, hoặc replica chưa nhận snapshot mới. Với yêu cầu chặn tác vụ đang chạy, cần kiểm tra domain state ở bước xử lý nhạy cảm hoặc trước commit; với nhiều replicas cần rollout consistency policy.

### 9.3. Dùng ConcurrentHashMap cũng cần invalidation

`ConcurrentHashMap.computeIfAbsent` có thể giúp tránh tạo cùng manager nhiều lần. Nhưng nếu key chỉ là tenant slug và không có revision/eviction, nó sẽ giữ trust cũ vô hạn. Dù dùng Caffeine hay map thuần, điều kiện **per-request active check** là thiết yếu.

## 10. Tích hợp AuthenticationManagerResolver vào SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiTenantApiSecurity {

    @Bean
    SecurityFilterChain tenantApiChain(
            HttpSecurity http,
            TrustedTenantManagerResolver resolver)
            throws Exception {

        http
            .securityMatcher("/api/tenants/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST,
                    "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.authenticationManagerResolver(resolver));

        return http.build();
    }
}
~~~

**Lưu ý:** `securityMatcher("/api/tenants/**")` chọn chain cho những URL phù hợp; ứng dụng có URL khác phải có fallback/chain tương ứng. `anyRequest().denyAll()` trong chain không bảo vệ những URL nằm ngoài chain đó.

Việc tắt CSRF trong ví dụ chỉ phù hợp **API thuần Bearer Authorization header, không dựa vào session cookie**; không sao chép cấu hình cho web OIDC Login dùng session.

### 10.1. Spring Security có JwtIssuerAuthenticationManagerResolver

Spring Security hỗ trợ **`JwtIssuerAuthenticationManagerResolver`** để chọn manager theo JWT issuer. Issuer đọc từ JWT ở bước định tuyến vẫn là **unverified hint**, nên bắt buộc có trusted issuers.

Ví dụ cho phiên bản có factory method phù hợp:

~~~java
// Dành cho một tập issuer cố định đã được duyệt;
// đối chiếu chính xác API với Spring Security version.
var issuerResolver =
    JwtIssuerAuthenticationManagerResolver
        .fromTrustedIssuers(
            "https://id.alpha.example.test/realms/main",
            "https://login.beta.example.test/oauth2");
~~~

Không sử dụng một resolver tự tạo decoder cho **mọi `iss` tự khai**. Nếu một resolver dùng predicate `trustedIssuers.contains(issuer)` nhưng chỉ kiểm tra predicate **lúc tạo manager đầu tiên** rồi cache manager, xóa issuer khỏi set có thể **không thu hồi được manager cũ**. Với lifecycle động, cần kiểm tra cache implementation ở version đang dùng, có per-request trust gate và test trường hợp manager đã được warmed trước revoke.

### 10.2. Không đánh đồng issuer với tenant

Nếu alpha và beta dùng **cùng issuer**, issuer resolver có thể xác thực cả hai bằng một decoder. Sau đó API **vẫn phải xác định và bảo vệ tenant membership** theo dữ liệu đã xác thực. Một token có `iss` đúng không đồng nghĩa được phép đọc mọi tenant dùng issuer đó.

## 11. Domain authorization: tenant ACTIVE vẫn chưa đủ

Giả sử API:

~~~http
GET /api/tenants/alpha/orders/77
Authorization: Bearer TOKEN_OF_USER_A
~~~

Sau JWT validation:

~~~text
Issuer đúng và ACTIVE
  AND chữ ký/audience/thời hạn đúng
  AND có SCOPE_orders.read
  AND user A có membership ACTIVE trong alpha
  AND order 77 thực sự thuộc alpha
  AND user A có quyền đọc order 77
~~~

**Không được tra `orders.findById(77)` rồi trả thẳng** nếu database chứa orders nhiều tenant. SQL nên ràng buộc dữ liệu bằng tenant ID nội bộ:

~~~sql
SELECT o.*
FROM app_order o
WHERE o.id = :orderId
  AND o.tenant_id = :trustedLocalTenantId
  AND o.owner_user_id = :trustedLocalUserId;
~~~

`:trustedLocalTenantId` lấy từ **trusted registry**, `:trustedLocalUserId` từ mapping người dùng theo **`(iss,sub)` đã xác minh** và membership. Không lấy `ownerUserId` từ body client để chứng minh quyền.

Với những hệ thống có nhân viên hỗ trợ/admin, định nghĩa ngoại lệ rõ ràng và kiểm tra đúng giới hạn tenant; không tạo một role `ADMIN` toàn cục vô tình bypass mọi dữ liệu.

### 11.1. Có thể dùng @PreAuthorize

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @tenantPolicy.canRead(" +
    "authentication, #tenantKey, #orderId)")
public OrderDto readOrder(String tenantKey, UUID orderId) {
    return loadAuthorizedOrder(tenantKey, orderId);
}
~~~

`tenantPolicy` và `loadAuthorizedOrder` là thành phần ứng dụng **cần tự triển khai**; policy phải dựa vào Authentication đã xác minh, tenant config ACTIVE và database thật. `@EnableMethodSecurity` cần được bật, method phải được gọi qua Spring-managed proxy, và các cập nhật nhạy cảm phải kiểm tra lại quyền/state trong transaction.

## 12. Quy trình đình chỉ hoặc thu hồi tenant

Khi tenant `gamma` cần bị chặn ngay:

~~~text
Security administrator
        |
        v
Control plane: gamma.status = REVOKED
               gamma.revision += 1
               globalGeneration += 1
               append audit event
        |
        v
Publish trusted snapshot / revocation event
        |
   +----+-----------------+
   |                      |
Replica A              Replica B
   |                      |
ACTIVE gate -> deny    ACTIVE gate -> deny
   |                      |
   +-----------+----------+
               |
               v
JWT gamma còn hạn vẫn không được chấp nhận
~~~

**Tenant trust revocation khác với revocation của một Access Token.** Đối với JWT tự chứa, Authorization Server có thể không thu hồi mọi token trước `exp`; Resource Server vẫn có thể **ngừng tin cả tenant** bằng registry gate.

### 12.1. Manager và JWKS cũ vẫn ở RAM

Sau revoke:

~~~text
Cached JwtDecoder gamma: còn trong memory
Cached JWKS keys gamma: còn trong memory
JWT gamma: chữ ký hợp lệ, exp còn 20 phút

registry.findActive("gamma") -> empty

Kết quả: từ chối authentication mới
~~~

Không cần đợi JWK cache hết hạn mới thu hồi trust. Evict manager để quản lý tài nguyên là tốt, nhưng **eviction một lần không thay được active check**, vì event có thể bị mất hoặc concurrent request đang giữ reference.

### 12.2. Request đã xác thực và tác vụ đang chạy

~~~text
T0: Request gamma qua JWT authentication.
T1: Control plane revoke gamma.
T2: Request gamma đang cập nhật đơn hàng.
~~~

Per-request trust gate thường bảo vệ **những request mới**, nhưng không tự rollback transaction đã commit hay hủy background job đang chạy. Nếu SLA yêu cầu dừng thao tác tức thời:

- Kiểm tra trạng thái tenant một lần nữa ở điểm domain/transaction quan trọng.
- Cân nhắc kill-switch cho stream/WebSocket/scheduled job.
- Đưa các nodes đang dùng generation cũ ra khỏi load balancer.
- Xử lý idempotency, audit và các giao dịch đã có side effect.

Không tuyên bố tenant REVOKED có thể tự hoàn tác tất cả business operations đã hoàn tất.

## 13. Nhiều replicas: thu hồi phải đến mọi serving nodes

Ví dụ:

~~~text
Replica A: generation 92, gamma REVOKED
Replica B: generation 91, gamma ACTIVE
Replica C: disconnected, generation 88
~~~

Nếu load balancer tiếp tục chuyển request tới B hoặc C, tenant bị revoke vẫn có thể được chấp nhận trên node dùng **stale trust config**. Đây là vấn đề consistency/lifecycle, không phải lỗi chữ ký JWT.

| Phương án | Ưu điểm | Rủi ro cần xử lý |
| --- | --- | --- |
| Polling snapshots định kỳ | Dễ triển khai. | Thời gian stale phụ thuộc polling interval. |
| Pub/sub events + reconciliation | Cập nhật nhanh, khắc phục event bị mất. | Out-of-order events, node offline. |
| Centralized ACTIVE check per request | Có thể giảm cửa sổ stale. | Thêm network dependency, fail-closed khi outage. |
| Push + acknowledged rollout barrier | Biết node nào đã cập nhật. | Cần orchestration/drain node chậm. |
| Snapshot có max age/fail-closed expiry | Node stale không tin cấu hình vô hạn. | Giảm availability nếu control plane lỗi. |

Một **revocation SLA** cần nêu cụ thể: tenant REVOKED sau bao lâu thì **tất cả request mới** bị chặn? Có được phục vụ bằng snapshot cũ khi control plane outage không? Với các thao tác tài chính/quản trị, câu trả lời có thể cần chặt hơn một API ít nhạy cảm.

### 13.1. Monotonic generation và stale deadline

Snapshot có thể mang:

~~~text
generation: 92
issuedAt: 10:00:00
validUntil: 10:00:30
~~~

Node nhận một event `ACTIVE` generation 90 **không được rollback** trạng thái hiện hành generation 92. Nếu snapshot đã quá deadline mà node không thể cập nhật, policy có thể yêu cầu **fail closed** hoặc loại node khỏi traffic. Không giữ trạng thái ACTIVE từ file cache cũ vô thời hạn.

### 13.2. Chặn emergency và tombstone

Với sự cố ký JWT bị lộ:

1. Ghi `SUSPENDED` hoặc `REVOKED` và tăng revision.
2. Phát emergency deny event và snapshot mới.
3. Require acknowledgement hoặc drain stale instances.
4. Không cho config cũ được replay.
5. Giữ tombstone/revocation record ít nhất đến khi mọi cache cũ không còn hiệu lực theo chính sách.

## 14. SSRF và JWKS rotation

Không làm:

~~~java
// KHÔNG LÀM:
String issuer = unverifiedTokenClaims.getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

Nếu issuer chưa được cho phép, server có thể gửi outbound requests đến địa chỉ do attacker điều khiển. **Discovery phải theo một issuer đã phê duyệt**, với TLS, host/IP egress restrictions, redirect checks, timeout và response limits.

### 14.1. JWT kid không phải trust root

JWT header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
~~~

`kid` chỉ nên chọn một key từ **JWKS URI được control plane duyệt**. Nếu `kid` lạ, decoder có thể refresh từ **nguồn đã tin**, nhưng không chuyển đến `jku` URL bất kỳ trong token.

### 14.2. Rotation bình thường khác key compromise

**Rotation bình thường:** issuer thêm key mới, giữ overlap key cũ/mới theo quy trình, decoder refresh JWKS từ endpoint cũ đã tin.

**Key compromise:** attacker có private key cũ. Cần cân nhắc suspend tenant, vô hiệu hóa key cũ tại IdP, revoke tokens, giảm JWKS cache staleness và kiểm tra manager cache. Không chỉ thêm key mới rồi xem mọi token key cũ vẫn an toàn.

Nếu thay cả **JWKS endpoint** hoặc **issuer**, đây là thay đổi **trust configuration revision**, cần re-validation và approval — không phải một refresh cache bình thường.

## 15. Migration sang issuer mới

Giả sử `alpha` chuyển:

~~~text
old issuer: https://old-idp.alpha.example.test/realm
new issuer: https://new-idp.alpha.example.test/realm
~~~

Quy trình an toàn:

1. Đăng ký issuer binding mới ở **VERIFYING**, không bật ngay.
2. Xác minh ownership, HTTPS, discovery, JWKS, algorithm, audience và Access Token profile.
3. Chuẩn bị liên kết user theo **`(iss,sub)`**, không tự gộp bằng email trùng.
4. Phê duyệt **dual-trust window** nếu cần, có deadline và policy rõ.
5. Không dùng issuer mới như một cách tự cấp quyền toàn tenant cho các user chưa được liên kết.
6. Theo dõi tỷ lệ request từ issuer cũ/mới và lỗi mapping.
7. Ngừng cấp token từ issuer cũ, xử lý refresh/session/expiry theo hợp đồng.
8. Revoke issuer binding cũ, tăng revision và invalidate old managers.
9. Test **token issuer cũ vẫn còn `exp` nhưng phải bị từ chối**.
10. Giữ audit/tombstone, không rollback trust đã bị thu hồi vì key compromise.

Nếu tenant dùng cùng issuer cũ và mới có hai `sub` khác nhau, không suy ra đó là cùng người chỉ dựa vào `email_verified`; cần quy trình identity linking/provisioning có chứng cứ.

### 15.1. Re-activate cần revision mới

Từ `SUSPENDED → ACTIVE` cần approval/re-verification. Với `REVOKED`, tùy chính sách có thể cần **onboarding lại**. Chỉ sửa trạng thái thành ACTIVE có thể khiến **JWT cũ còn hạn** được chấp nhận lại nếu chúng vẫn hợp lệ theo issuer/JWKS. Nếu phải chặn token cũ, cần cơ chế **minimum token issuance epoch**, denylist, revocation tại IdP hoặc issuer/key migration; chỉ tăng config revision của Resource Server không làm JWT cũ tự mất hiệu lực.

## 16. Tenant trust khác vòng đời dữ liệu doanh nghiệp

~~~text
Security trust:
  ACTIVE -> SUSPENDED -> REVOKED

Business/data:
  OPERATING -> OFFBOARDING -> ARCHIVED
  -> EXPORTED/DELETED theo retention/legal hold
~~~

Thu hồi issuer không nhất thiết đồng nghĩa được quyền xóa mọi dữ liệu khách hàng. Dữ liệu vẫn có thể cần lưu phục vụ audit, hợp đồng và retention. Ngược lại, còn lưu dữ liệu tenant **không phải lý do** giữ issuer ACTIVE.

Ngoài API JWT, cần xét:

- Web sessions/cookie sau OIDC Login.
- SSE/WebSocket subscriptions dài hạn.
- Message consumers và background jobs.
- Client-credentials service principals.
- Opaque token introspection cache.
- Local user/tenant memberships.

Nếu tenant bị revoke, mỗi đường trên cần policy tương ứng. Chỉ xóa decoder JWT không tự hủy session cookie đã được tạo từ trước.

## 17. Xử lý lỗi HTTP và tránh lộ thông tin control plane

| Tình huống | Kết quả thường gặp |
| --- | --- |
| Không gửi Bearer token vào endpoint bảo vệ | **401** Bearer challenge. |
| Issuer không trusted hoặc tenant không ACTIVE | Từ chối; **401/404** tùy policy tránh lộ tenant. |
| JWT sai issuer/audience/signature/expiration | **401 invalid_token**. |
| Token hợp lệ nhưng thiếu OAuth scope | **403 insufficient_scope** khi phù hợp. |
| Scope đúng nhưng user không thuộc tenant/order khác owner | **403 hoặc 404** theo domain policy. |
| JWKS hoặc config dependency không khả dụng | **Fail closed**; lỗi vận hành có thể được map thành 5xx/503. |
| Replica dùng snapshot đã quá stale | Từ chối hoặc loại node khỏi traffic theo revocation SLA. |

Không công bố chi tiết như `issuer=...`, `jwksUri=...`, `revocationReason=compromised-key` cho unauthenticated caller. Admin UI có thể hiển thị status cho **quản trị viên được phép**, còn Bearer API nên dùng thông điệp an toàn/trung tính.

**Fail closed:** khi thiếu dữ liệu để chứng minh token được chấp nhận, không tạo principal mặc định, không fallback sang một decoder “chấp nhận mọi issuer”.

## 18. Kiểm thử trạng thái: cần test manager đã warm

| Test | Điều cần chứng minh |
| --- | --- |
| Unknown issuer trong token | Không auto-register, không discovery tới URL token chỉ định. |
| Tenant REQUESTED/VERIFYING/APPROVED | Chưa được chấp nhận trong data plane. |
| ACTIVE + JWT đúng issuer/aud/key/scope | Qua được authentication; domain policy vẫn kiểm tra. |
| ACTIVE + JWT từ issuer khác | **401**. |
| ACTIVE + sai audience hoặc expired | **401**. |
| JWT có `jku` là internal URL | Không fetch URL đó; chỉ trusted JWKS. |
| Token alpha dùng route beta | Từ chối theo issuer/membership. |
| Hai tenants dùng chung issuer | Không lẫn membership/owner. |
| ACTIVE → SUSPENDED, JWT còn hạn | Request mới bị từ chối. |
| ACTIVE → REVOKED với manager đã cache | **Vẫn từ chối**, dù JWT ký đúng và chưa exp. |
| Revision JWKS/issuer đổi | Không dùng manager revision cũ làm trust mới. |
| Event ACTIVE revision cũ tới sau REVOKED | Không hạ version/không re-activate. |
| Node stale vượt deadline | Fail closed hoặc không nhận traffic. |
| Control plane outage khi tenant chưa ACTIVE | Không tự kích hoạt tenant. |
| Issuer migration, `sub` mới và email cũ | Không tự link user chỉ bằng email. |
| Re-activate tenant nhưng token cũ cần bị chặn | Epoch/revocation policy hoạt động. |

### 18.1. Bài test quan trọng nhất: revoke sau khi cache đã được tạo

~~~text
1. Registry: alpha ACTIVE, revision 10.
2. Gửi JWT alpha ký thật, issuer/aud đúng.
3. Resolver tạo manager (alpha,10) và cache.
4. Gửi lại JWT -> authentication thành công.
5. Publish snapshot alpha REVOKED, revision 11.
6. Gửi chính JWT đó, vẫn chưa hết exp.
7. Phải bị từ chối, dù manager (alpha,10) còn trong cache.
8. Replay snapshot ACTIVE cũ -> không re-activate.
~~~

Nếu bước 7 vẫn thành công, quy trình “đã xóa tenant khỏi registry” **chưa thực sự thu hồi trust**.

### 18.2. MockMvc jwt() không chứng minh issuer registry

Ví dụ:

~~~java
mockMvc.perform(get("/api/tenants/alpha/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

`jwt()` trong `spring-security-test` tạo Authentication giả cho **test authorization**, không đi qua JWT decoder và dynamic trust registry. Nó không đủ để test onboarding/revocation. Cần integration tests gửi **raw Bearer JWT ký bằng private key test**, dùng real decoder/JWKS test server, rồi thay snapshot giữa requests. Test phải kiểm tra số requests/fetch từ endpoint tin cậy và **không có fetch tới issuer/JWKS do attacker tự khai**.

### 18.3. Kiểm thử nhiều nodes

Mô phỏng:

~~~text
Replica A: generation 92, alpha REVOKED
Replica B: generation 91, alpha ACTIVE

Kỳ vọng:
  A deny requests mới.
  B bị drain / fail closed trước khi vượt revocation deadline.
  Event ACTIVE generation 90 không hạ state của A/B.
  Control plane không tuyên bố rollout xong khi B còn phục vụ.
~~~

Với SSRF, dùng test HTTP endpoints cô lập và fake DNS/redirect, **không gọi cloud metadata URL production**.

## 19. WebFlux và opaque token: cùng nguyên tắc trust

Nếu triển khai **Spring WebFlux**, thay các thành phần Servlet bằng:

- `SecurityWebFilterChain` / `ServerHttpSecurity`.
- `ReactiveAuthenticationManagerResolver<ServerWebExchange>` hoặc reactive issuer resolver phù hợp.
- `ReactiveJwtDecoder` và validators.

Chính sách vẫn là:

~~~text
ServerWebExchange
  -> Trusted tenant locator + ACTIVE gate
  -> Approved reactive decoder/config revision
  -> JWT signature/issuer/audience validation
  -> Reactive SecurityContext
  -> authorizeExchange + reactive domain authorization
~~~

Không `block()` để tải cấu hình từ control plane trên event loop; dùng snapshot tin cậy với stale policy hoặc nguồn reactive thích hợp. Không `subscribe()` thủ công và cho request đi tiếp trước khi tenant state được xác định.

Với **opaque token**, trusted config phải quản lý **introspection endpoint + Resource Server client credentials**. Kết quả RFC 7662 `active:false` bị từ chối; cache introspection `active:true` có TTL giới hạn và không được làm tenant REVOKED tiếp tục được nhận. **Tenant status gate độc lập** là cần thiết ngay cả khi Authorization Server chưa biết tenant đã bị offboard.

## 20. Audit, observability và readiness

Một sự kiện audit nội bộ:

~~~json
{
  "eventType": "TENANT_TRUST_REVOKED",
  "tenantKey": "gamma",
  "previousRevision": 31,
  "newRevision": 32,
  "generation": 94,
  "actor": "security-admin-id",
  "reasonCode": "SECURITY_INCIDENT",
  "occurredAt": "2026-11-15T09:00:00Z"
}
~~~

**Không công bố event chứa lý do nhạy cảm cho caller không được phép.** Audit nên có integrity, retention và RBAC.

Nên theo dõi:

- Current config generation ở mỗi serving instance.
- Nodes chậm hơn minimum accepted generation.
- Thời gian từ revoke tại control plane đến khi toàn cluster deny.
- Requests bị từ chối vì tenant inactive/unknown.
- JWT issuer/audience/signature validation error categories.
- JWKS fetch latency/unknown kid, cache manager size và evictions.
- Cross-tenant domain denials, 401/403 rates.

Không log raw Bearer Access Token, client secret, private key hoặc toàn bộ JWT claims cá nhân. Không dùng token hay token fingerprint làm metric label công khai.

Instance nên **fail readiness hoặc được drain** nếu không có trusted snapshot hợp lệ, snapshot quá stale theo policy, hoặc không áp dụng được revocation generation bắt buộc.

## 21. Runbook vận hành

### 21.1. Thêm tenant

1. Tạo REQUESTED, chưa mở API token acceptance.
2. Kiểm tra ownership/admin permissions.
3. Validate HTTPS issuer/JWKS và chống SSRF.
4. Kiểm tra token contract: issuer, audience, algorithms, scope.
5. Kiểm thử sandbox với cả positive/negative tokens.
6. Thực hiện approval/audit và tạo revision mới.
7. Publish immutable snapshot/generation mới.
8. Xác nhận serving replicas đã nhận cấu hình.
9. Chuyển ACTIVE và cho traffic.
10. Theo dõi 401/403, JWKS errors và cross-tenant denials.

### 21.2. Đình chỉ hoặc thu hồi tenant khẩn cấp

1. Người có quyền ghi lý do và quyết định SUSPENDED/REVOKED.
2. Tăng tenant revision và global generation.
3. Publish state và emergency deny signal.
4. ACTIVE gate phải từ chối **trước khi dùng cached JWT manager**.
5. Drain hoặc fail closed những replicas chưa cập nhật đúng deadline.
6. Xem xét session, streams, jobs, service tokens và opaque introspection cache.
7. Test JWT **chữ ký đúng, chưa hết hạn**, nhưng tenant REVOKED.
8. Kiểm tra transaction/work đang chạy và audit.
9. Ghi nhận thời gian tất cả nodes đã deny và lưu tombstone.

### 21.3. Mở lại hoặc chuyển issuer

1. Xác định nguyên nhân suspension/revocation đã được giải quyết.
2. Xác minh issuer/JWKS và key compromise nếu có.
3. Thực hiện lại approval; **không tự rollback trust bị revoke**.
4. Lập kế hoạch old tokens: revoke, min issuance epoch hoặc issuer rotation.
5. Liên kết local identities an toàn, không auto-map bằng email.
6. Publish **revision mới**, kiểm thử token cũ/mới.
7. Giám sát rollout và trạng thái account/tenant nghiệp vụ.

## 22. Những sai lầm dễ mắc

| Sai lầm | Hậu quả | Hướng đúng |
| --- | --- | --- |
| Tin mọi `iss` từ token, tự gọi discovery. | Issuer confusion/SSRF. | Trusted issuer registry, phê duyệt trước. |
| Tin `jku`/`x5u` trong JOSE header. | Token chọn nơi tải public key. | JWKS URI approved, allowlist network. |
| Chữ ký đúng là đủ, không kiểm tra `aud`. | Token của API khác được nhận. | Issuer + audience + token profile validation. |
| Coi tenant slug trong URL là permission. | Cross-tenant access. | Membership và owner/domain checks. |
| Map user chỉ bằng `sub` hoặc email. | Lẫn user/chiếm đoạt tài khoản. | `(iss,sub)` và account linking có chứng cứ. |
| Dùng manager cache keyed theo tenantKey vĩnh viễn. | Decoder cũ vẫn hoạt động sau revoke. | Revisioned key + per-request ACTIVE gate. |
| Chỉ xóa issuer khỏi dynamic predicate. | Cached resolver có thể còn manager cũ. | Test/invalidate + runtime state check. |
| Xóa tenant không tombstone. | Event ACTIVE cũ có thể mở lại. | Monotonic revision, REVOKED/RETIRED tombstone. |
| Update từng field không atomic. | Issuer mới + JWKS cũ, policy sai. | Immutable approved snapshot. |
| Node offline dùng config ACTIVE vô thời hạn. | Stale trust sau revoke. | Snapshot max age/watermark/fail closed. |
| Bật issuer ở production trước kiểm tra ownership. | Attacker tự đăng ký IdP. | REQUESTED/VERIFYING/APPROVED. |
| Rollback issuer sau key compromise. | Tin lại key đã lộ. | Re-approval và key/token migration. |
| Re-activate rồi mặc định token cũ mất hiệu lực. | JWT cũ còn hạn có thể được nhận lại. | Revoke/epoch policy, test old tokens. |
| Thu hồi tenant đồng nghĩa xóa sạch dữ liệu. | Mất retention/audit/legal hold. | Tách trust và data lifecycle. |
| Chỉ test bằng MockMvc `jwt()`. | Không chạy resolver/decoder thật. | Signed JWT integration + warmed-cache revoke test. |
| Cho request đi tiếp khi control plane lỗi. | Fail-open. | Trust snapshot policy và fail closed. |

## 23. Tổng kết

Ba lớp bảo vệ phải đi cùng nhau:

1. **Trusted configuration lifecycle:** tenant/issuer chỉ được thêm qua ownership validation, approval, versioned publish; chỉ trạng thái **ACTIVE** mới được tiếp tục.
2. **Token authentication:** JWT được xác minh bằng key đã cấu hình, kiểm tra chữ ký, issuer, audience, thời hạn và thuật toán; `iss` chưa xác minh chỉ là hint, không phải trust root.
3. **Tenant/domain authorization:** principal phải có membership và quyền trên tenant/tài nguyên cụ thể; status thu hồi và dữ liệu owner/tenant cần được kiểm tra ở các điểm thích hợp.

**Thu hồi tenant phải thắng cả một cached manager và JWT còn hạn.** Hãy dùng **per-request ACTIVE gate, revisioned manager cache, immutable snapshots, monotonic generation, fail-closed stale policy, audit và bài test ACTIVE → REVOKED với manager đã cache**. Một hệ thống nhiều replicas chỉ có thể công bố thu hồi hoàn tất khi những nodes còn phục vụ traffic đều đã áp dụng quyết định mới theo SLA.

## Tài liệu tham khảo

- [Spring Security — Servlet Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html).
- [Spring Security — Reactive Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JwtIssuerAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html).
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html).
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
- [OWASP — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/).
