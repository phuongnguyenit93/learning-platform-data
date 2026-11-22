# 26.6. Ràng buộc tenant với state, callback và principal

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** phục vụ **nhiều tenant**, đăng nhập thành công tại OpenID Provider chưa đủ để user được truy cập tenant đã chọn.

Giả sử người dùng mở `/t/acme/login`. Nếu sau callback ứng dụng đọc tenant từ query parameter hoặc một session attribute `selectedTenant` dùng chung, browser có thể thay đổi giá trị này hoặc hai login tabs có thể ghi đè lên nhau. Kết quả có thể là user được gắn với sai tenant dù OAuth2 Login vừa hoàn tất.

Nguyên tắc cốt lõi là tạo một ràng buộc không thể bị browser sửa:

**Tenant ban đầu → Authorization Request cùng `state` → callback đã được xác minh → issuer + subject → membership → tenant-scoped principal/session → tenant-aware authorization ở mọi API.**

Sau bài, bạn có thể:

1. Phân biệt tenant routing hint, canonical tenant ID, client registration và issuer.
2. Ràng buộc tenant với `state` do Spring Security tạo khi bắt đầu Authorization Code flow.
3. Dùng server-side pending login store theo state với TTL, session binding và one-time consumption.
4. Đối chiếu tenant, registration và expected issuer ở callback mà không bỏ kiểm tra OAuth2/OIDC mặc định.
5. Nhận diện mix-up, login CSRF, state replay, tenant hopping và account confusion.
6. Xây identity dựa trên `iss` + `sub` sau khi ID token được xác minh và kiểm tra membership trong tenant.
7. Tránh race của hai login tabs và vấn đề session ID rotation.
8. Phân biệt tenant claim do OP phát và tenant role/quyền của ứng dụng.
9. Thiết kế tenant context cho session/principal mà không dùng quyền tenant A cho B.
10. Tổ chức Resolver/Success Handler với Spring MVC và hiểu phần Reactive/WebFlux tương ứng.
11. Kiểm tra tenant isolation ở service/database, token cache, API authorization và logout.
12. Viết test cho mismatch, replay, concurrent flow và trường hợp user không thuộc tenant.

## 1. Bối cảnh: SaaS Portal nhiều tenant

Giả sử Portal có ba tenant:

~~~text
Acme
Globex
Contoso
~~~

Cùng một Spring Boot application phục vụ:

~~~text
https://portal.example.com/t/acme
https://portal.example.com/t/globex
https://portal.example.com/t/contoso
~~~

Mỗi tenant có thể dùng OP riêng hoặc dùng chung một OP. Tenant có users, memberships, roles và dữ liệu nghiệp vụ riêng.

Ví dụ cấu hình tin cậy:

| Tenant ID | Slug | Registration ID | Expected issuer |
|---|---|---|---|
| 42 | `acme` | `acme-oidc` | `https://id.acme.example/oidc` |
| 51 | `globex` | `globex-oidc` | `https://sso.globex.example` |
| 88 | `contoso` | `shared-oidc` | `https://login.corp.example` |

Một registration ID là khóa local của `ClientRegistration`. Issuer là danh tính AS/OP đã được cấu hình và xác minh. Tenant ID là danh tính tổ chức nội bộ, không nhất thiết giống bất kỳ claim nào trong ID token.

### 1.1. Luồng đăng nhập mục tiêu

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser
    participant Portal as Spring Security Portal
    participant Store as Pending login store
    participant OP as OpenID Provider
    participant Members as Membership service
    User->>Browser: Mở /t/acme/login
    Browser->>Portal: Chọn tenant Acme
    Portal->>Portal: Resolve tenant, allowlist registration/issuer
    Portal->>Portal: Sinh Authorization Request với state
    Portal->>Store: Save state → expected Acme/registration/issuer
    Portal-->>Browser: 302 tới OP
    Browser->>OP: Authorization Request
    OP-->>Browser: Callback code + state
    Browser->>Portal: /login/oauth2/code/acme-oidc
    Portal->>Portal: Spring xác minh state, token và OIDC
    Portal->>Store: Consume pending binding theo state
    Store-->>Portal: Expected Acme/registration/issuer
    Portal->>Members: Check (Acme, iss, sub)
    Members-->>Portal: Membership ACTIVE
    Portal->>Portal: Tạo tenant-scoped context
    Portal-->>Browser: Redirect đến /t/acme
~~~

Nếu state không có, issuer sai, registration khác hoặc membership không hợp lệ, hệ thống phải **từ chối**. Không lấy tenant từ query callback để chữa lỗi.

### 1.2. Quy tắc trước và sau login

Trước khi OP xác thực:

~~~text
Tenant selection = request routing hint
Identity = chưa xác thực
Membership = chưa được cấp
~~~

Sau khi OIDC token được xác minh và membership check thành công:

~~~text
TenantId = 42
Issuer = https://id.acme.example/oidc
Subject = user-123
LocalUserId = user-92817
Registration = acme-oidc
Membership = ACTIVE
TenantAuthorities = [ORDER_VIEWER]
~~~

Ngay cả lúc này, API vẫn phải kiểm tra quyền trên từng tài nguyên, không chỉ dựa vào việc một lần login đã thành công.

## 2. Các ranh giới tin cậy

| Dữ liệu | Đến từ | Có được tin trực tiếp không? |
|---|---|---|
| Tenant slug trong path | Browser | Không, phải tra directory |
| Host hoặc subdomain | HTTP request/proxy | Không, nếu chưa kiểm soát host và forwarded headers |
| Canonical tenant ID | Server-side directory | Có thể dùng làm identity của tenant |
| `registrationId` | OAuth client configuration | Tin cậy khi chọn từ allowlist |
| `state` | Spring OAuth2 Client tạo | Correlation key; cần đối chiếu server-side |
| Callback query `code`/`state` | Browser chuyển từ OP | Chỉ dùng sau protocol validation |
| ID token `iss`/`sub` | OP | Chỉ dùng sau OIDC signature/issuer/audience validation |
| Membership | Application directory/ACL | Cơ sở cấp quyền tenant |
| Claims `tid`/`org` | OP | Chỉ dùng nếu semantics được định nghĩa và xác minh |
| Active tenant context | Application sau authorization | Chỉ đáng tin khi được bảo vệ khỏi client mutation |

### 2.1. Tenant selection không phải authorization

Bất kỳ browser nào cũng có thể nhập:

~~~text
https://portal.example.com/t/globex/login
~~~

Điều đó chỉ yêu cầu hệ thống bắt đầu login dành cho Globex. Nó không chứng minh người dùng có quyền đọc đơn hàng của Globex.

### 2.2. OIDC authentication không tự cấp membership

Một OP dùng chung có thể xác thực cả nhân viên Acme và Globex. Alice là user hợp lệ của OP nhưng có thể chỉ thuộc Acme.

Alice chọn Globex, OP vẫn có thể trả ID token hợp lệ cho Alice. Portal vẫn phải kiểm tra **Alice có membership trong Globex hay không**.

### 2.3. Tenant claim không luôn trùng tenant của SaaS

Một ID token có thể có `tid` là tenant của hệ thống identity, không phải tenant ID nội bộ của Portal.

Không dùng trực tiếp claim đó như quyền truy cập dữ liệu SaaS trừ khi có contract và mapping rõ ràng.

## 3. TenantDirectory: nguồn ánh xạ đã được phê duyệt

Một `TenantDirectory` chịu trách nhiệm:

- Tra canonical tenant ID từ slug hoặc domain.
- Kiểm tra tenant đang ACTIVE.
- Chỉ định các `registrationId` được phép cho tenant.
- Ánh xạ registration tới issuer đã được phê duyệt.
- Quản lý version cấu hình khi issuer/registration thay đổi.
- Đưa ra tenant-specific login policy và return path phù hợp.

### 3.1. Interface minh họa

~~~java
public interface TenantDirectory {

    PendingTenantLogin beginLogin(
            String tenantSlug,
            String registrationId);
}
~~~

Method phải xác minh cả hai input, không coi chúng là quyền truy cập. Trong thực tế có thể nhận tenant ID canonical do router xác định thay vì slug.

### 3.2. Không dùng URL issuer do user gửi

Mẫu nguy hiểm:

~~~text
/login?issuer=https://untrusted.example.net
~~~

Nếu backend tạo `ClientRegistration` và tự discovery theo URL bất kỳ, rủi ro gồm SSRF và đăng nhập qua một OP không được phê duyệt.

Browser chỉ nên được chọn một tenant/registration **trong allowlist của server**.

### 3.3. Một tenant có thể được phép dùng nhiều OP

Ví dụ:

~~~text
Acme:
  acme-oidc
  shared-corporate-oidc
~~~

Mỗi OP có chính sách riêng. Cùng một tenant có thể có nhiều cách đăng nhập, nhưng membership kiểm tra vẫn phải xác định user từ issuer/subject tương ứng.

### 3.4. Một OP có thể dùng chung cho nhiều tenants

Ví dụ:

~~~text
Acme -> shared-oidc
Globex -> shared-oidc
Issuer -> https://login.corp.example
~~~

Trong trường hợp này, **`registrationId` và issuer đều giống nhau** cho hai flows. Vì vậy bắt buộc lưu tenant được chọn theo `state` và kiểm tra membership.

## 4. Vai trò của OAuth `state`

OAuth2 Client tạo một Authorization Request với `state` ngẫu nhiên khó đoán, lưu nó trong `OAuth2AuthorizationRequestRepository`, rồi chuyển browser tới Authorization Server.

Ví dụ bắt đầu flow:

~~~http
GET /oauth2/authorization/acme-oidc?tenant=acme HTTP/1.1
Host: portal.example.com
~~~

Callback:

~~~http
GET /login/oauth2/code/acme-oidc?code=CODE&state=STATE_A HTTP/1.1
Host: portal.example.com
~~~

Spring Security đối chiếu `state` với Authorization Request đã lưu trước khi hoàn thành login.

### 4.1. Không dùng tenant slug làm state

Sai:

~~~text
state=acme
~~~

State đó đoán được và không phân biệt được hai requests cùng tenant. Nó không phải correlation key bảo mật.

Đúng là dùng giá trị ngẫu nhiên do framework/secure generator sinh:

~~~text
state=RANDOM_OPAQUE_VALUE
~~~

và có một mapping server-side:

~~~text
state=RANDOM_OPAQUE_VALUE
  -> tenantId=42
  -> registrationId=acme-oidc
  -> expectedIssuer=https://id.acme.example/oidc
  -> startedAt=...
~~~

### 4.2. Không tin tenant ở callback

Callback có thể chứa query giả:

~~~text
/login/oauth2/code/acme-oidc?code=...&state=...&tenant=globex
~~~

Ứng dụng không được lấy `tenant=globex` làm tenant thực. Tenant đã được bind ở thời điểm bắt đầu flow và lấy lại từ server-side state store.

### 4.3. State tự chứa có những yêu cầu bổ sung

Nếu muốn đặt tenant vào payload state thay vì server-side store, cần bảo đảm:

- Integrity/authentication của payload.
- Entropy đủ mạnh.
- Timestamp/TTL.
- Chống replay.
- Browser/session binding.
- Không lộ thông tin nhạy cảm.
- Key rotation.

Chỉ encode JSON sang Base64 không mang lại tính toàn vẹn hay bí mật.

## 5. PendingTenantLogin: transaction context

Có thể lưu một object bất biến:

~~~java
import java.time.Instant;

public record PendingTenantLogin(
        String tenantId,
        String registrationId,
        String expectedIssuer,
        Instant startedAt,
        String returnPath) {
}
~~~

Giải thích:

| Field | Ý nghĩa |
|---|---|
| `tenantId` | Canonical tenant ID đã được server resolve |
| `registrationId` | ClientRegistration được allowlist |
| `expectedIssuer` | Issuer được cấu hình/trust tại lúc bắt đầu login |
| `startedAt` | Đánh giá TTL |
| `returnPath` | Internal path an toàn sau login |

Không lưu:

~~~text
client_secret
raw access_token
refresh_token
id_token
authorization_code
raw user password
full OIDC claim set
~~~

Pending binding chỉ chứa dữ liệu cần kiểm soát transaction, không phải token store.

### 5.1. Ràng buộc với cấu hình tại thời điểm bắt đầu

Nếu admin đổi issuer của Acme khi user đang đăng nhập, callback thuộc issuer cũ không được âm thầm xử lý như issuer mới.

Có thể lưu thêm configuration version và từ chối pending flow khi thay đổi security-sensitive policy.

### 5.2. Return path phải được validate

Ví dụ path hợp lệ:

~~~text
/t/acme/orders
~~~

Không đưa `https://attacker.example.net` vào return path chỉ vì browser gửi tham số `returnUrl`.

## 6. Lưu pending state trên server

Một interface đơn giản:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;

public interface PendingTenantLoginStore {

    void save(
            HttpServletRequest request,
            String state,
            PendingTenantLogin pending);

    Optional<PendingTenantLogin> consume(
            HttpServletRequest request,
            String state);
}
~~~

`save` được gọi trước redirect đến OP. `consume` được gọi sau khi callback đã được Spring Security xác thực.

### 6.1. Những bất biến của store

- Mỗi state chỉ ánh xạ tới một pending transaction.
- Không cho sửa tenant/registration/issuer sau khi đã lưu.
- State thuộc browser/session đã bắt đầu flow.
- Record có TTL ngắn và giới hạn số entry.
- Consume phải một lần và atomic khi chạy nhiều nodes.
- Callback thứ hai cùng state phải thất bại.
- Không tìm state của session khác để “khôi phục” flow.
- Không log raw state, session ID hoặc credentials.

### 6.2. Session-backed map

Thay vì:

~~~text
HttpSession:
  selectedTenant=globex
~~~

hãy lưu:

~~~text
HttpSession:
  pendingTenantLogins:
    state-A -> acme
    state-B -> globex
~~~

Hai requests không làm thay đổi tenant đã bind cho state khác nhau.

### 6.3. Redis/database store

Nếu dùng storage chia sẻ nhiều nodes, `consume` phải có semantics **read-and-delete atomic** (transaction, Redis script hoặc primitive tương ứng).

Một chuỗi `GET` rồi `DEL` tách rời có thể để hai callbacks cùng nhận binding khi chạy song song.

### 6.4. TTL

Thời gian chờ callback thường ngắn và phụ thuộc trải nghiệm với OP. Dữ liệu pending cần bị xóa khi hết thời hạn, logout hoặc failure.

TTL quá ngắn khiến flow hợp lệ thất bại; quá dài làm tăng retention và rủi ro state replay nếu implementation có lỗi.

## 7. Hai tab đăng nhập đồng thời

Ví dụ:

~~~text
Tab A bắt đầu Acme login -> state-A
Tab B bắt đầu Globex login -> state-B
~~~

Nếu ứng dụng chỉ có một biến session:

~~~text
Tab A: selectedTenant=acme
Tab B: selectedTenant=globex
Tab A callback -> đọc globex (sai)
~~~

State-indexed map giải quyết nhầm tenant giữa hai transaction:

~~~text
state-A -> acme
state-B -> globex
~~~

### 7.1. Còn cần kiểm tra AuthorizationRequestRepository

Một số implementation mặc định của `HttpSessionOAuth2AuthorizationRequestRepository` giữ một Authorization Request ở session tại một thời điểm. Hai flow cùng session có thể khiến flow trước mất state correlation.

**Thêm pending tenant map không tự động làm repository mặc định hỗ trợ concurrent OAuth login.**

Nếu sản phẩm yêu cầu nhiều login tabs đồng thời, cần custom `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` lưu nhiều pending requests theo state, kèm TTL, upper bound và one-time removal.

### 7.2. Không bỏ state check để sửa multi-tab

Nếu một callback không còn Authorization Request tương ứng, từ chối và yêu cầu user bắt đầu lại. Không chấp nhận code chỉ vì endpoint callback đúng.

### 7.3. Số entry cần giới hạn

Một browser có thể cố bắt đầu hàng nghìn login flows. Pending state store cần giới hạn số entries/session và dọn những entry đã quá hạn để tránh resource exhaustion.

## 8. Session fixation và session ID rotation

Spring Security có thể đổi session ID sau khi xác thực để hạn chế session fixation.

Một custom store dùng Redis key:

~~~text
pending:{raw-session-id}:{state}
~~~

có thể gặp vấn đề nếu session ID đổi trước khi ứng dụng consume pending binding và key không được migrate.

### 8.1. Không phụ thuộc mù vào session ID string

Có thể lưu pending map trong session attributes được migration theo strategy đang dùng, hoặc dùng một session-bound stable handle được kiểm soát.

Cần kiểm tra timing thực tế của OAuth2 Login filter, session fixation strategy và custom success processing.

### 8.2. Session hết hạn trước callback

Nếu session/correlation đã mất, callback phải fail closed. Không tìm toàn cục một state rồi gắn user vào session khác.

### 8.3. Session cookie

Nếu dùng cookie-backed session, thiết lập `Secure`, `HttpOnly` và `SameSite` phù hợp OAuth redirect flow. Không tắt những cơ chế này chỉ để callback hoạt động.

## 9. Thứ tự xác minh callback

Thứ tự tham khảo:

1. Spring Security tìm Authorization Request khớp state.
2. Kiểm tra flow/callback và đổi authorization code ở token endpoint đúng registration.
3. Xác minh OIDC ID token: signature, issuer, audience, time và nonce khi áp dụng.
4. Tạo `OAuth2AuthenticationToken` có registration ID thực tế.
5. Ứng dụng consume pending tenant binding đã lưu theo state.
6. So sánh expected registration với Authentication.
7. So sánh expected issuer với validated ID token issuer.
8. Đọc subject đã được xác minh.
9. Kiểm tra membership trong canonical tenant.
10. Chỉ sau đó cấp active tenant context/authorities theo policy.
11. Điều hướng về path thuộc tenant đã xác minh.
12. Tiếp tục kiểm tra tenant và ownership trong mọi API request.

Custom tenant check là **lớp bổ sung**, không thay thế state/PKCE/nonce/ID token validation của framework.

### 9.1. Registration check

`OAuth2AuthenticationToken` có:

~~~java
oauth.getAuthorizedClientRegistrationId();
~~~

Giá trị này phải khớp `registrationId` đã bind trong pending record.

### 9.2. Issuer check

`OidcUser` có ID token đã được OP xác minh. Issuer từ token đó phải khớp issuer mà tenant/registration đã chọn và tin cậy.

### 9.3. Membership check

Một user hợp lệ tại OP nhưng không thuộc tenant đã chọn **không được cấp quyền tenant đó**.

Nếu SaaS hỗ trợ just-in-time provisioning, nó phải có chính sách được phê duyệt; không mặc định “login thành công tức là tạo member”.

## 10. Custom Authorization Request Resolver trong Spring MVC

Một cách tích hợp là **bọc resolver chuẩn** để lấy state do framework tạo, sau đó ghi tenant binding.

### 10.1. Resolver wrapper

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.client.web
        .OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint
        .OAuth2AuthorizationRequest;

public final class TenantBoundAuthorizationRequestResolver
        implements OAuth2AuthorizationRequestResolver {

    private static final String BASE_PATH =
            "/oauth2/authorization/";

    private final OAuth2AuthorizationRequestResolver delegate;
    private final TenantDirectory tenantDirectory;
    private final PendingTenantLoginStore store;

    public TenantBoundAuthorizationRequestResolver(
            OAuth2AuthorizationRequestResolver delegate,
            TenantDirectory tenantDirectory,
            PendingTenantLoginStore store) {
        this.delegate = delegate;
        this.tenantDirectory = tenantDirectory;
        this.store = store;
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request) {

        OAuth2AuthorizationRequest authorization =
                delegate.resolve(request);

        if (authorization == null) {
            return null;
        }

        String registrationId =
                registrationFromPath(request.getServletPath());

        return bind(request, registrationId, authorization);
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request,
            String registrationId) {

        OAuth2AuthorizationRequest authorization =
                delegate.resolve(request, registrationId);

        if (authorization == null) {
            return null;
        }

        return bind(request, registrationId, authorization);
    }

    private OAuth2AuthorizationRequest bind(
            HttpServletRequest request,
            String registrationId,
            OAuth2AuthorizationRequest authorization) {

        String tenantSlug = request.getParameter("tenant");

        PendingTenantLogin pending =
                tenantDirectory.beginLogin(
                        tenantSlug, registrationId);

        store.save(
                request,
                authorization.getState(),
                pending);

        return authorization;
    }

    private String registrationFromPath(String path) {
        if (path == null || !path.startsWith(BASE_PATH)) {
            throw new IllegalArgumentException(
                    "Unknown OAuth authorization route");
        }

        String registrationId =
                path.substring(BASE_PATH.length());

        if (registrationId.isBlank()
                || registrationId.contains("/")) {
            throw new IllegalArgumentException(
                    "Invalid registration route");
        }

        return registrationId;
    }
}
~~~

Đoạn code giả định đường dẫn bắt đầu OAuth login đúng `/oauth2/authorization/{registrationId}` và servlet path không bị rewrite đặc biệt. Nếu deployment dùng custom base URI/context path, phải điều chỉnh cách lấy registration ID theo routing thực tế.

### 10.2. Vì sao cần delegate?

`DefaultOAuth2AuthorizationRequestResolver` của Spring Security biết cách tạo Authorization Request đúng registration, state, redirect URI, scope, PKCE/nonce theo flow.

Wrapper chỉ gắn tenant vào state; **không tự thay state** bằng tenant slug.

### 10.3. Ví dụ bắt đầu login

~~~text
GET /oauth2/authorization/acme-oidc?tenant=acme
~~~

`tenant=acme` vẫn là input chưa tin cậy. `TenantDirectory.beginLogin(...)` phải kiểm tra registration này được allowlist cho canonical tenant Acme.

## 11. Cấu hình resolver trong SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders
        .HttpSecurity;
import org.springframework.security.oauth2.client.registration
        .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
        .DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class TenantSecurityConfiguration {

    @Bean
    SecurityFilterChain tenantSecurityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations,
            TenantDirectory directory,
            PendingTenantLoginStore store,
            TenantLoginSuccessHandler successHandler)
            throws Exception {

        var delegate =
                new DefaultOAuth2AuthorizationRequestResolver(
                        registrations, "/oauth2/authorization");

        var tenantResolver =
                new TenantBoundAuthorizationRequestResolver(
                        delegate, directory, store);

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/", "/t/*/login", "/error")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(oauth2 -> oauth2
                        .authorizationEndpoint(endpoint -> endpoint
                                .authorizationRequestResolver(
                                        tenantResolver))
                        .successHandler(successHandler))
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

Các bean `TenantDirectory`, `PendingTenantLoginStore` và `TenantLoginSuccessHandler` là **thành phần custom** cần được triển khai trong ứng dụng; Spring Security không tự cung cấp chúng.

Đây là ví dụ cho Servlet OAuth2 Login. Không cần viết một callback HTTP handler mới tự đổi code, vì Spring Security đã có filter thực hiện flow.

## 12. Membership service và tenant identity

Sau khi xác minh ID token, cần map identity sang local user/tenant membership.

~~~java
public record TenantIdentity(
        String tenantId,
        String issuer,
        String subject,
        String registrationId,
        String localUserId) {
}

public interface TenantMembershipService {

    TenantIdentity requireActiveMembership(
            String tenantId,
            String issuer,
            String subject,
            String registrationId);
}
~~~

Một implementation production nên:

- Dùng `issuer` + `subject` đã xác minh làm external identity key.
- Kiểm tra registration/issuer được tenant cho phép.
- Tra account linking đã được xác minh.
- Kiểm tra tenant active.
- Kiểm tra membership active.
- Áp roles/permissions đúng tenant.
- Từ chối nếu user không có membership.
- Không tự tạo account bởi email trùng nhau trừ khi policy provisioning cho phép.

### 12.1. `iss` + `sub`

Một OP có thể phát `sub=user-123`, một OP khác cũng phát `sub=user-123`.

Hai subjects này **không mặc nhiên là cùng user**. Phải xét issuer.

### 12.2. Email không thay membership

Claim email có thể bị thay đổi hoặc chưa verified. Ngay cả email verified cũng không tự chứng minh quyền đối với dữ liệu tenant trong SaaS.

## 13. Success handler minh họa

Một cách kiểm tra tenant **sau khi Spring Security đã hoàn thành OAuth2/OIDC authentication** là custom success handler.

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication
        .OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.authentication
        .AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.logout
        .SecurityContextLogoutHandler;

public final class TenantLoginSuccessHandler
        implements AuthenticationSuccessHandler {

    private final PendingTenantLoginStore store;
    private final TenantMembershipService memberships;

    public TenantLoginSuccessHandler(
            PendingTenantLoginStore store,
            TenantMembershipService memberships) {
        this.store = store;
        this.memberships = memberships;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        try {
            if (!(authentication
                    instanceof OAuth2AuthenticationToken oauth)) {
                throw new IllegalStateException(
                        "OAuth2 authentication required");
            }

            PendingTenantLogin expected = store
                    .consume(
                            request,
                            request.getParameter("state"))
                    .orElseThrow(() ->
                            new IllegalStateException(
                                    "Pending tenant login missing"));

            if (!expected.registrationId().equals(
                    oauth.getAuthorizedClientRegistrationId())) {
                throw new IllegalStateException(
                        "Registration mismatch");
            }

            if (!(oauth.getPrincipal() instanceof OidcUser user)) {
                throw new IllegalStateException(
                        "OIDC principal required");
            }

            String issuer =
                    user.getIdToken().getIssuer().toString();
            String subject =
                    user.getIdToken().getSubject();

            if (!expected.expectedIssuer().equals(issuer)) {
                throw new IllegalStateException(
                        "Issuer mismatch");
            }

            TenantIdentity identity =
                    memberships.requireActiveMembership(
                            expected.tenantId(),
                            issuer,
                            subject,
                            expected.registrationId());

            request.getSession().setAttribute(
                    "VERIFIED_TENANT_IDENTITY", identity);

            // Production: redirect ONLY to a validated path
            // belonging to identity.tenantId(), then return.
            response.sendRedirect(
                    request.getContextPath() + "/t/"
                            + identity.tenantId() + "/home");

        } catch (RuntimeException failure) {
            // Fail closed; ensure local auth/session is removed.
            new SecurityContextLogoutHandler()
                    .logout(request, response, authentication);
            response.sendError(
                    HttpServletResponse.SC_FORBIDDEN,
                    "Tenant login is not permitted");
        }
    }
}
~~~

### 13.1. Giới hạn của ví dụ

Đây là **khung minh họa**. Đoạn redirect giả định route chứa canonical tenant ID. Với route dùng slug hoặc vanity domain, dùng một path resolver server-side đáng tin cậy và encode path segment đúng chuẩn, không nối input chưa được validate.

Quan trọng hơn: success handler chạy sau quá trình authentication của Spring Security, lúc đó SecurityContext/authorized client **có thể đã được lưu**. Khi tenant check thất bại, cần dọn trạng thái đã tạo, kể cả authorized client trong `OAuth2AuthorizedClientService` nếu nằm ngoài session.

Trong hệ thống yêu cầu tenant verification hoàn tất **trước khi lưu Authentication**, nên tích hợp verification vào authentication pipeline/strategy phù hợp, vẫn giữ mọi kiểm tra OAuth2/OIDC tiêu chuẩn. Không coi riêng success handler minh họa là đầy đủ cho production.

### 13.2. Không gọi success logic trước framework state check

Handler chỉ nên được gọi từ flow OAuth2 Login đã thành công của Spring Security. Nó không phải endpoint riêng nhận một state bất kỳ và tự cấp tenant context.

### 13.3. Không tự động dùng saved request từ tenant khác

Nếu request trước login là `/t/globex/orders` nhưng pending login gắn với Acme, redirect tới saved request có thể gây confusion. Validate tenant của redirect hoặc dùng đường dẫn cố định thuộc tenant đã xác minh.

## 14. Ràng buộc principal sau login

Một application principal hoặc context có thể bao gồm:

~~~text
localUserId
issuer
subject
registrationId
activeTenantId
membershipId
tenantAuthorities
authenticatedAt
~~~

Nhưng **một session attribute tự nó không phải authorization decision**.

### 14.1. Tenant-scoped authorities

User có thể là:

~~~text
Alice:
  Acme -> ORDER_ADMIN
  Globex -> ORDER_VIEWER
~~~

Không được dùng `ORDER_ADMIN` của Acme để thực hiện thao tác admin tại Globex.

### 14.2. Membership thay đổi sau login

Admin có thể thu hồi membership Alice/Acme khi session vẫn còn hoạt động.

Tùy chính sách, cần recheck membership theo request, versioning, cache invalidation hoặc session invalidation. Không dùng một claim cũ trong ID token như quyền bất biến cho tới expiry.

### 14.3. Principal identity và tenant context

Identity toàn cục (issuer, subject, local user) khác active tenant. Một user có thể được phép thuộc nhiều tenants; mỗi request vẫn cần active tenant được kiểm soát.

### 14.4. Authorized client storage

Nếu custom token store key chỉ dựa trên một `sub` trùng giữa issuers hoặc một registration/username không có namespace, token có thể bị gán sai principal.

Cần bảo đảm storage key phân biệt registration, trusted principal và tenant/issuer khi kiến trúc yêu cầu.

## 15. One issuer phục vụ nhiều tenants

Ví dụ:

~~~text
Acme: shared-oidc
Globex: shared-oidc
Issuer: https://login.corp.example
~~~

User Alice được OP xác thực thành công, nhưng chỉ là member Acme.

Nếu Alice cố:

~~~text
/oauth2/authorization/shared-oidc?tenant=globex
~~~

OP vẫn có thể cấp ID token hợp lệ.

**Chỉ so sánh issuer và registration không phát hiện được Alice không thuộc Globex.** Bắt buộc có pending tenant binding theo state và membership check.

### 15.1. `login_hint` và `domain_hint` là hints

Một số OP nhận hint để chọn form hoặc tổ chức. Không coi hint này là membership decision của SaaS.

### 15.2. Claim tenant từ OP

Nếu OP phát `organizations` hoặc `roles`, chỉ dùng nó theo profile đã thỏa thuận và được kiểm tra issuer, audience, thời gian và quyền. Không copy claim vào ACL nội bộ mà không có policy mapping.

## 16. Nhiều OP và Authorization Server mix-up

Khi Acme và Globex có issuers khác nhau, có nguy cơ app nhầm phản hồi của OP này với flow OP kia.

Ví dụ cần ngăn:

~~~text
Start Acme login
  -> Callback thuộc Globex
  -> App xử lý như Acme vì chỉ đọc URL tenant
~~~

Các biện pháp:

- State correlation của Spring Security.
- Registration binding theo state.
- Issuer binding theo state.
- Token endpoint lấy từ trusted ClientRegistration.
- ID token issuer/audience/signature/nonce validation.
- Callback path/redirect URI tương ứng registration.
- Authorization response issuer validation nếu profile/framework hỗ trợ.
- Không tự nhận token endpoint hoặc issuer từ callback.

### 16.1. Callback path chưa phải chứng cứ

`/login/oauth2/code/acme-oidc` là một route, không phải bằng chứng cryptographic cho issuer.

Nó phải được dùng cùng state correlation và token validation.

### 16.2. Không tắt issuer validation

Nếu issuer mismatch, sửa registration/metadata/flow. Không tắt `iss` validation để cho multi-tenant login “chạy được”.

## 17. Login CSRF, replay và PKCE/nonce

### 17.1. Login CSRF

Nếu ứng dụng chấp nhận callback không khớp request do browser bắt đầu, user có thể bị đăng nhập nhầm account hoặc tenant.

Spring Security dùng `state` để correlate OAuth2 Authorization Request. Tenant binding giúp đảm bảo tenant cũng không bị thay đổi giữa chừng.

### 17.2. Replay

Một state chỉ được consume một lần:

~~~text
First callback state-A -> consume -> valid
Second callback state-A -> missing -> reject
~~~

Authorization Code cũng có tính single-use tại AS, nhưng store của ứng dụng vẫn nên có one-time semantics.

### 17.3. PKCE

PKCE bảo vệ Authorization Code bằng code verifier/challenge. Mỗi authorization transaction phải có verifier riêng khi PKCE được áp dụng.

### 17.4. Nonce

OIDC nonce liên kết ID token với authentication request khi áp dụng. Không dùng chung một nonce toàn cục cho mọi tenant hoặc browser session.

### 17.5. OAuth state không thay CSRF protection ở application

Một POST `/tenant/switch` hoặc `/account/link` dùng cookie session vẫn cần CSRF protection theo thiết kế web app. State chỉ giải quyết correlation của OAuth flow.

## 18. Redirect sau callback và open redirect

Nếu app cho user chọn return path, đừng nhận URL tùy ý:

~~~text
returnTo=https://attacker.example.net
returnTo=//attacker.example.net
~~~

Nên kiểm tra chỉ cho phép path nội bộ thuộc tenant đã xác minh:

~~~text
/t/acme/home
/t/acme/orders
~~~

### 18.1. Avoid cross-tenant saved request

Nếu user chọn Acme nhưng saved request trỏ Globex, phải reject hoặc redirect về trang Acme. Không coi redirect path là được phép chỉ vì login thành công.

### 18.2. Path normalization

Cần kiểm tra URL encoding, protocol-relative URLs, backslash và dot segments theo parser phù hợp. Không chỉ dùng `startsWith("/t/acme")` vì nó có thể chấp nhận tiền tố không dự kiến như `/t/acme-evil`.

### 18.3. Return path không quyết định tenant

Tenant đã được xác minh từ pending state và membership. Return path chỉ điều hướng trong phạm vi tenant đó.

## 19. Tenant switching sau login

Một user có thể thuộc cả Acme và Globex, muốn đổi active tenant.

Đây là **authorization operation trong ứng dụng**, không phải callback của OIDC flow.

Flow ví dụ:

~~~text
POST /tenant/switch
  targetTenant = Globex
  -> CSRF validation nếu browser session
  -> Check authenticated identity
  -> Check membership Globex
  -> Recalculate tenant roles
  -> Update active tenant context
  -> Invalidate stale tenant caches if needed
  -> Redirect to Globex path
~~~

### 19.1. Không chỉ đổi URL

Nếu Alice đang ở Acme rồi nhập `/t/globex/orders`, app không được tự set tenant context là Globex và cấp quyền.

### 19.2. Khi các tenant dùng OP khác nhau

Policy có thể yêu cầu Authorization Code/OIDC Login mới với OP của tenant đích. Không dùng token/cookies của OP A cho OP B.

### 19.3. Khi cùng OP và identity là member cả hai

Có thể cho switch không login lại nếu policy cho phép và membership được xác minh. Tuy vậy vẫn phải ràng buộc roles, caches và downstream token với active tenant.

## 20. Tenant-aware authorization ở service và database

Một callback đúng không bù được một truy vấn dữ liệu bỏ tenant filter.

Ví dụ request:

~~~http
GET /t/acme/orders/123
~~~

Service phải đảm bảo:

~~~text
requested tenant = Acme
authenticated tenant = Acme
order.tenant = Acme
user has ORDER_VIEWER permission in Acme
~~~

### 20.1. Repository theo tenant

~~~java
import java.util.Optional;

public interface TenantOrderRepository {

    Optional<OrderEntity> findByTenantIdAndId(
            String tenantId,
            String orderId);
}
~~~

`tenantId` truyền vào phải đến từ trusted authorization context, không từ request body có thể bị sửa.

### 20.2. Kiểm tra ownership

Ngay cả khi order thuộc Acme, user có thể chỉ được xem đơn hàng do mình tạo. Tenant isolation và object-level authorization là hai lớp riêng.

### 20.3. Cache key phải có tenant

Sai:

~~~text
orders-list:alice
~~~

Nếu Alice thuộc hai tenants, cache có thể trả nhầm dữ liệu.

Cần khóa theo tenant/principal/resource phù hợp:

~~~text
orders-list:tenant-42:user-92817
orders-list:tenant-51:user-92817
~~~

## 21. Token và authorized client isolation

`OAuth2AuthorizedClient` gắn với registration và principal. Trong multi-tenant system, cần bảo đảm principal name và storage namespace không trùng giữa issuers/tenants.

### 21.1. Tránh cache key thiếu issuer

Nếu hai OP cùng phát `sub=12345`, cache token theo `sub` đơn lẻ có thể lẫn credential.

Có thể cần dùng internal user ID hoặc namespace `issuer + subject + tenant` cho custom storage.

### 21.2. Token đúng audience

Access token Acme không được tự gửi tới Resource Server Globex. API phải xác minh issuer, audience, scope và tenant-related authorization theo contract.

### 21.3. Refresh token không chứng minh membership

Refresh token thành công chỉ cho biết AS đã cấp access token mới. Nó không tự chứng minh user vẫn thuộc tenant sau khi admin đã thu hồi membership.

### 21.4. Logout/đổi user

Nếu authorized client nằm trong service store ngoài session, logout không tự xóa mọi record. Cần cleanup và revoke khi policy yêu cầu, tránh session mới của Bob dùng token Alice.

## 22. Cấu hình dynamic registration và issuer rotation

Một SaaS lớn có thể tạo registration từ database tenant config. Cần phòng:

- Tenant tự nhập discovery URL không được kiểm soát.
- SSRF qua metadata/JWKS/Token endpoint.
- Issuer bị sửa giữa authorization và callback.
- Client secret bị lộ từ config/log.
- Cache ClientRegistration trộn tenant.
- Callback route sử dụng version cấu hình không khớp.

### 22.1. Configuration version binding

Pending transaction có thể lưu:

~~~text
tenantId
registrationId
expectedIssuer
registrationConfigVersion
startedAt
~~~

Nếu issuer thay đổi trong lúc user ở OP, nên áp policy rõ ràng, thường fail closed và yêu cầu login lại thay vì tự chuyển flow cũ sang issuer mới.

### 22.2. Trusted provisioning

Issuer/client registration nên được tạo qua admin workflow có thẩm định, HTTPS, discovery endpoint allowlist, client credential protection và audit.

## 23. WebFlux/Reactive

Nguyên tắc tenant binding không đổi khi ứng dụng chạy Spring WebFlux. Các API tương ứng khác Servlet:

| Servlet | WebFlux |
|---|---|
| `OAuth2AuthorizationRequestResolver` | `ServerOAuth2AuthorizationRequestResolver` |
| `OAuth2AuthorizationRequestRepository` | `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` |
| `HttpServletRequest` / HttpSession | `ServerWebExchange` / WebSession |
| `AuthenticationSuccessHandler` | `ServerAuthenticationSuccessHandler` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `SecurityContextHolder` | `ReactiveSecurityContextHolder` |

### 23.1. Reactive flow

~~~text
ServerOAuth2AuthorizationRequestResolver
  -> Mono<OAuth2AuthorizationRequest>
  -> bind tenant context with state in WebSession/store
  -> redirect

OIDC callback
  -> state and token validation
  -> consume pending tenant binding
  -> reactive membership check
  -> tenant-scoped context or reject
~~~

### 23.2. Không dùng `block()` hoặc `subscribe()` thủ công

Một reactive membership lookup nên được compose bằng `flatMap`; không gọi blocking DB trực tiếp trên event loop và không tự tạo subscription khiến error/security context bị mất.

### 23.3. Reactive SecurityContext

WebFlux dùng Reactor Context cho Authentication. Không mặc định Servlet-style ThreadLocal `SecurityContextHolder` là nguồn tin cậy trong mọi reactive operator.

### 23.4. Concurrent tabs và WebSession

Vẫn cần state-indexed pending store, atomic consume và tương thích với AuthorizationRequestRepository nếu login đa tab là requirement.

## 24. Multi-domain tenants và cookie isolation

Với subdomains:

~~~text
acme.portal.example.com
globex.portal.example.com
~~~

cần đánh giá cookie domain và session boundary.

### 24.1. Host-only cookie

Nếu cần cô lập cao giữa tenants, cân nhắc cookie host-only thay vì domain cookie rộng chia sẻ cho toàn bộ subdomains.

### 24.2. Trusted reverse proxy

Không tin `Host` hoặc `X-Forwarded-Host` từ Internet để chọn tenant. Forwarded headers phải do reverse proxy tin cậy cung cấp và app phải có allowed hosts.

### 24.3. SameSite

OAuth redirect cần session cookie/correlation tồn tại khi browser quay về. Chọn SameSite policy theo flow và browser behavior, đồng thời giữ Secure/HttpOnly và CSRF protection.

## 25. Kiểm thử tenant binding

### 25.1. Unit tests cho TenantDirectory

| Tình huống | Kỳ vọng |
|---|---|
| Acme + acme-oidc | Trả tenant canonical Acme và issuer đã duyệt |
| Acme + globex-oidc | Reject khi không được phép |
| Tenant disabled | Reject |
| Tenant slug không tồn tại | Reject |
| Browser gửi issuer URL khác | Không dùng URL đó |
| Tenant alias | Resolve canonical ID nhất quán |

### 25.2. State mapping tests

~~~text
Start Acme -> state-A -> Acme
Start Globex -> state-B -> Globex

consume(state-A) -> Acme
consume(state-B) -> Globex
consume(state-A) lần 2 -> reject
consume(expired state-C) -> reject
consume(state-D) từ session khác -> reject
~~~

### 25.3. Callback tests

- State hợp lệ, registration đúng, issuer đúng, membership active: allow.
- Registration mismatch: reject.
- Issuer mismatch: reject.
- Subject không là tenant member: reject.
- State missing/expired/replayed: reject.
- User bị thu hồi membership trước callback: reject.
- OAuth2-only principal xuất hiện trong flow OIDC bắt buộc: reject.
- Saved request trỏ host ngoài hoặc tenant khác: reject.

### 25.4. Concurrent login tests

- Mở hai login flows trong một browser/session.
- Callback theo thứ tự ngược.
- State-A vẫn là Acme, state-B vẫn là Globex.
- Repository Authorization Request có thể lưu hai requests nếu yêu cầu.
- Session ID rotation không làm mất binding trước khi consume.
- Logout/session timeout xóa pending data.

### 25.5. Authorization sau login

User đã xác thực và là member Acme vẫn phải bị từ chối khi gọi:

~~~text
GET /t/globex/orders/123
~~~

nếu không có quyền Globex. Dùng integration tests service/API, không chỉ test callback.

### 25.6. Test bằng token giả

Dùng MockMvc, mock OIDC metadata/token endpoint hoặc test OP. Không dùng token production và không log authorization codes, refresh tokens hoặc session cookies.

## 26. Troubleshooting

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Login Acme xong vào Globex | Dùng shared `selectedTenant` | State-indexed binding |
| Hai tabs khiến một callback lỗi | Repository chỉ giữ một Authorization Request | Multi-request repository nếu cần |
| State mismatch | Cookie/session mất, request ghi đè | Session/SameSite/repository |
| Pending binding missing | TTL quá ngắn, session rotation, consume sớm | Store lifecycle |
| Issuer mismatch | Registration/provider mix-up | Kiểm tra expected issuer và ID token |
| User hợp lệ OP vào tenant không thuộc | Thiếu membership check | Tenant authorization |
| `sub` trùng từ hai OP | Dùng subject đơn lẻ | Dùng `iss` + `sub` |
| Redirect sang tenant khác | Saved request/returnPath chưa validate | Tenant-bound redirect |
| State reuse | Consume không atomic | One-time store |
| Token Acme dùng ở Globex | Sai principal/tenant cache key | Authorized client isolation |
| Admin revoke membership nhưng vẫn truy cập | Session/role cache stale | Recheck/invalidate |
| WebFlux không thấy Authentication | ThreadLocal hoặc broken Reactor chain | Reactive security context |
| Session cookie cross-subdomain | Cookie domain quá rộng | Isolation policy |
| Dynamic issuer bị attacker thay | Untrusted discovery URL | Server allowlist/admin approval |

## 27. Các hiểu nhầm thường gặp

**“Tenant slug trong URL là bằng chứng quyền truy cập.”** Không. Đó là routing hint.

**“OIDC Login thành công có nghĩa user thuộc tenant đã chọn.”** Không. Phải xác minh membership.

**“Có `state` nên không cần bind tenant.”** State bảo vệ OAuth correlation; app vẫn cần liên kết state với tenant và kiểm tra membership.

**“State có thể bằng tenant ID.”** Không. State cần entropy, uniqueness và replay protection.

**“Đọc tenant ở callback cũng giống lúc bắt đầu.”** Không. Callback đi qua browser; tenant phải lấy từ pending context đã được lưu.

**“Một `selectedTenant` session attribute đủ cho mọi trường hợp.”** Không khi có nhiều tabs và login transactions.

**“State map tự giải quyết concurrent OAuth logins.”** Không nếu AuthorizationRequestRepository không hỗ trợ nhiều requests.

**“Issuer + registration đúng là đủ.”** Không khi nhiều tenants chia sẻ một issuer/registration.

**“`sub` là globally unique.”** Không. Subject thuộc namespace của issuer.

**“ID token có `tid` nên khỏi cần membership.”** Không mặc định; phải xác minh semantics/policy.

**“Một lần set tenant trong session thì database luôn an toàn.”** Không. API vẫn cần tenant/ownership authorization.

**“PKCE và nonce thay thế state/tenant binding.”** Không; mỗi cơ chế giải quyết rủi ro riêng.

**“Local logout tự revoke token.”** Không. AS revocation là hoạt động riêng.

## 28. Tình huống thực hành

### A. Alice chọn tenant không thuộc quyền

Alice là member Acme, chọn Globex với OP dùng chung.

**Xử lý:** OIDC xác thực có thể thành công, nhưng membership Globex không có nên từ chối.

### B. Hai tabs login

Tab A là Acme, tab B là Globex.

**Xử lý:** pending map theo state, không một biến selectedTenant chung; nếu cần concurrent OAuth flows, repository cũng phải hỗ trợ nhiều states.

### C. Callback thay tenant query

State-A thuộc Acme, callback có `tenant=globex`.

**Xử lý:** bỏ qua tenant query, dùng pending binding của state-A.

### D. Cùng issuer cho hai tenants

Issuer/registration không phân biệt Acme và Globex.

**Xử lý:** tenant state binding và membership là bắt buộc.

### E. Admin đổi issuer giữa flow

Flow bắt đầu với issuer A nhưng config đã đổi B.

**Xử lý:** so sánh issuer/version đã bind; thường fail closed và login lại.

### F. Session ID rotation

Pending store dùng raw session ID và callback không tìm thấy entry sau xác thực.

**Xử lý:** thiết kế session migration hoặc stable browser-bound handle, không bỏ xác minh state.

### G. User bị revoke sau login

Alice login Acme hợp lệ, sau đó membership bị thu hồi.

**Xử lý:** chặn request sau theo recheck/invalidation; refresh access token không tự phục hồi membership.

### H. Saved request vào tenant khác

Pending login Acme nhưng redirect sau login trỏ Globex.

**Xử lý:** validate internal return path và kiểm tra tenant authorization trước redirect/serving data.

## 29. Câu hỏi tự kiểm tra

**1. Tenant slug từ URL có chứng minh membership không?**

Không. Phải resolve canonical tenant và kiểm tra user sau authentication.

**2. Vì sao bind tenant với `state`?**

Để callback được gắn với tenant đã chọn khi Authorization Request được khởi tạo.

**3. Có thể dùng state là `acme` không?**

Không. State phải ngẫu nhiên, khó đoán, riêng mỗi transaction.

**4. Tenant ở callback query có đáng tin không?**

Không. Dùng server-side state binding.

**5. Vì sao một session `selectedTenant` không đủ cho hai tabs?**

Tab sau có thể ghi đè lựa chọn của tab trước.

**6. State store hỗ trợ nhiều tabs nhưng repository OAuth request chỉ giữ một request thì sao?**

Một flow vẫn có thể lỗi state. Cần repository hỗ trợ concurrency nếu đó là requirement.

**7. Callback có OIDC ID token hợp lệ đã đủ quyền tenant chưa?**

Chưa. Cần issuer, registration và membership.

**8. Vì sao dùng `iss` + `sub`?**

Subject không duy nhất giữa các issuers.

**9. Khi hai tenants có cùng issuer và registration, cần kiểm tra thêm gì?**

State-bound tenant và membership.

**10. `tid` trong ID token có phải tenant ID nội bộ không?**

Không mặc định; phụ thuộc semantics và mapping.

**11. Tại sao pending state chỉ consume một lần?**

Ngăn replay và cập nhật tenant context từ một transaction đã dùng.

**12. Session ID rotation ảnh hưởng gì?**

Có thể làm pending store keyed theo old session ID không tìm lại được.

**13. Có cần tenant check ở API/database sau callback không?**

Có. Cần tenant-aware authorization và ownership checks.

**14. User có hai memberships có thể switch tenant không?**

Có thể theo policy, qua thao tác kiểm tra quyền tenant đích, không chỉ thay URL.

**15. Logout Portal có tự revoke token ở OP không?**

Không.

**16. WebFlux có nên dùng Servlet SecurityContext ThreadLocal không?**

Không; dùng Reactor Context và reactive APIs phù hợp.

**17. State missing nhưng ID token issuer hợp lệ có được login không?**

Không. Thiếu transaction correlation phải từ chối.

**18. Có thể redirect sau login sang tenant khác vì user đã login không?**

Không. Phải kiểm tra tenant-bound return path và authorization.

## Ghi nhớ

- **Tenant ban đầu là routing hint, không phải quyền truy cập.** Cần canonical tenant mapping và membership check sau khi OIDC identity được xác minh.
- **Ràng buộc tenant, registration và issuer vào pending transaction theo state** do Spring Security sinh; state phải opaque, có TTL, session binding và one-time consume.
- **Không tin tenant từ callback query, Host header hoặc email claim.** Lấy tenant từ state-bound server store.
- **Kiểm tra registration, issuer và `iss` + `sub`** rồi xác minh membership trong đúng tenant trước khi cấp quyền.
- **Nhiều tab và session ID rotation cần được thiết kế trước**, không dùng một biến `selectedTenant` chung cho mọi login flow.
- **Giữ state, PKCE, nonce và ID token validation của framework**, không bỏ kiểm tra để xử lý mix-up.
- **Tenant-scoped principal không thay thế authorization trên từng API/resource**. Database, cache và downstream calls vẫn phải giới hạn tenant và ownership.
- **Tenant switching, account linking, logout và revocation là các workflow khác nhau**. Không mang roles/tokens của tenant này sang tenant khác.
- **Thiếu pending state, issuer/registration mismatch hoặc membership không hợp lệ phải fail closed**, không tự gán tenant mặc định từ dữ liệu browser.
