# Pre-authentication và trách nhiệm xác thực đã được thực hiện ở tầng trước

**Pre-authentication (xác thực từ trước)** là mô hình trong đó một thành phần nằm trước ứng dụng — chẳng hạn **identity-aware proxy, API gateway, reverse proxy có SSO, web access management agent hoặc servlet container** — đã xác minh danh tính của người dùng trước khi request tới Spring Security. Ứng dụng nhận **kết quả danh tính đã được chứng thực bởi thành phần đó**, chứ không tự thực hiện lại đầy đủ bước login với mật khẩu, Kerberos ticket, SAML assertion hoặc OIDC authorization code ở mỗi request.

Trong Spring Security, pre-authentication **không có nghĩa bỏ Spring Security**. Framework vẫn cần: (1) lấy principal đáng tin cậy từ request/container, (2) tạo `Authentication` trong `SecurityContext` đúng vòng đời, (3) tải hoặc ánh xạ authorities, (4) từ chối request sai trust boundary hoặc tài khoản không được cấp phép, và (5) áp **authorization** đối với tài nguyên/tenant.

Đây là một trong những mô hình tích hợp dễ sai nhất: nếu ứng dụng công khai đọc `X-Verified-User: admin` từ header do bất kỳ browser nào tự gửi, attacker có thể đăng nhập thành admin **mà không cần xác thực tại proxy**. `RequestHeaderAuthenticationFilter` của Spring Security **chỉ đọc header**, không kiểm chữ ký, token, trạng thái đăng nhập hoặc danh tính proxy. Tài liệu Spring Security cảnh báo trực tiếp về khả năng giả mạo danh tính khi dùng sai filter này.

Bài thuộc nhóm **Xác thực qua proxy**, đi từ kiến trúc trust, trách nhiệm của mỗi lớp, cấu hình `RequestHeaderAuthenticationFilter`/`PreAuthenticatedAuthenticationProvider`, ánh xạ user/role, session/identity lifecycle, các failure modes, Java 17 demo, ma trận kiểm thử và checklist production. Domain `.example`, user và các chính sách trong ví dụ chỉ minh họa; không phải cấu hình hay danh tính production.

## 1. Phân biệt authentication, pre-authentication và authorization

| Hoạt động | Bên chủ trì | Đầu vào | Đầu ra |
| --- | --- | --- | --- |
| **Authentication thực sự** | IdP/gateway/container được tin | Credential, session, Kerberos/SPNEGO, SAML, OIDC, client cert tùy cơ chế | Identity đã được kiểm, trạng thái xác thực |
| **Pre-authentication adapter** | Spring Security ở backend | **Tín hiệu danh tính tin cậy** do upstream chuyển vào | `Authentication` và principal bên trong app |
| **Identity mapping** | App/identity directory được phê duyệt | Issuer/realm + subject ID | Local account, trạng thái active/locked, tenant |
| **Authorization** | Spring + service/business layer | Local authorities, quyền đối tượng, tenant | Cho phép/từ chối từng thao tác |
| **Session/revocation policy** | Gateway và ứng dụng, mỗi bên chịu một phần | Session lifetime, logout, offboarding, revalidation | Không dùng lại danh tính đã bị thu hồi |

**Authentication** trả lời “request này thực sự gắn với ai?”. **Authorization** trả lời “người đó có được thao tác này ở ngữ cảnh này không?”. **Pre-authentication** là một **kiểu tích hợp giữa hai lớp**, không phải cách “đánh dấu mọi request đã authenticated”.

### Ví dụ công ty

~~~text
User browser
  -> https://reports.corp.example/reports
  -> Identity-Aware Gateway
       checks OIDC login at corporate IdP + MFA + active session
       resolves trusted subject: employee-4102
       strips all client-supplied identity headers
       writes X-Verified-Subject: employee-4102
  -> private HTTPS/mTLS to Spring backend
       reads X-Verified-Subject ONLY on authenticated gateway hop
       loads local user 4102, status ACTIVE, tenant REPORTS
       assigns ROLE_REPORT_VIEWER from local policy
       checks the requested report belongs to tenant REPORTS
  -> HTTP 200 / 403
~~~

Nếu Browser cố gửi `X-Verified-Subject: ceo` thì gateway **phải xóa** giá trị đó và thay bằng danh tính đã xác thực hoặc chặn request. Nếu Browser truy cập backend pod trực tiếp, network/authn layer phải chặn **trước khi header filter xử lý**.

## 2. Luồng request và ranh giới tin cậy

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant G as Trusted Gateway
    participant I as Identity Provider
    participant S as Spring Backend
    participant D as Local Identity/Policy
    B->>G: GET /reports + cookies / request headers
    G->>G: Strip client-supplied identity headers
    alt Chưa có gateway session hợp lệ
        G-->>B: Redirect/401 tới IdP
        B->>I: Login / MFA
        I-->>G: Verified identity theo protocol
    end
    G->>G: Validate session, issuer, audience, expiration
    G->>G: Derive approved stable subject
    G->>S: Private HTTPS/mTLS + X-Verified-Subject: employee-4102
    S->>S: Confirm request came via trusted ingress
    S->>S: Pre-auth filter extracts principal
    S->>D: Look up active local user, tenant and authorities
    D-->>S: ROLE_REPORT_VIEWER
    S->>S: Check report ownership/tenant and authorization
    S-->>B: Response via Gateway
~~~

Sơ đồ minh họa **gateway có cơ chế SSO riêng**; chi tiết SAML/OIDC/Negotiate sẽ tùy sản phẩm gateway. Điểm cốt lõi là **Spring chỉ đọc danh tính khi sự tin cậy đối với gateway/hop đã được chứng minh bằng hạ tầng hoặc chữ ký**. Chỉ thấy header không phải bằng chứng.

### Ba ranh giới riêng

1. **Internet/Browser → Gateway:** một request có thể đến từ bất kỳ client nào, các header HTTP user tự ghi là **không đáng tin**.
2. **Gateway → Backend:** chỉ các gateway được phê duyệt có quyền truy cập, kết nối bảo vệ bằng network policies, firewall/security group, mTLS hoặc một cơ chế tương đương. Header danh tính được sinh bởi gateway sau login thật.
3. **Spring → dữ liệu nghiệp vụ:** ngay cả một user đã được upstream xác thực cũng chỉ được xem những resources được cấp phép nội bộ.

**Không coi private IP, header `X-Forwarded-For` hoặc `X-Forwarded-Proto` là bằng chứng đủ về việc request đi qua gateway**. Một backend có listener trực tiếp, ingress rule sai hoặc sidecar khác có thể cho attacker tự gắn các header này.

## 3. Proxy phải thực hiện những trách nhiệm gì?

Một **identity-aware proxy** được trao trách nhiệm xác thực phải làm được ít nhất:

- Chỉ chấp nhận session hoặc credential đã được kiểm theo **giao thức xác thực chuẩn** ở tầng trước: OIDC, SAML, Kerberos, client certificate, session theo policy.
- Kiểm issuer/identity provider, audience/client/service, expiry và các ràng buộc flow (**state**, **nonce**, chữ ký khi áp dụng), không tin ID Token/access token chỉ vì decode ra JSON.
- Kiểm tài khoản bị khóa, session expired, logout/revocation và mức xác thực **MFA/assurance** nếu tài nguyên yêu cầu.
- **Xóa mọi header định danh do client gửi** trước khi tính toán và gắn header do chính gateway tạo.
- Đảm bảo mọi đường vào backend chỉ qua **gateway hợp lệ**; không có “debug port”, node IP, health ingress hoặc path bypass ngoài ý muốn.
- Tách **identity headers** khỏi các `X-Forwarded-*` nói về host/proto/IP; chỉ một namespace dành riêng cho tín hiệu đã xác thực.
- Không để user lựa chọn tự do `trusted issuer`, `principalId`, tenant hoặc role.
- Giới hạn độ dài và định dạng headers; xử lý nhiều header cùng tên, header folding, Unicode và duplicate case theo chính sách.
- Chuyển identity qua kênh bảo vệ, chống packet capture, spoofing và replay theo threat model.
- Truyền correlation ID/audit không chứa credentials hay token nhạy cảm; ghi log đủ để quy kết session upstream có thật.
- Có fail-closed behavior khi IdP, policy engine, session store hoặc gateway identity validation thất bại.

Nếu có nhiều gateway cạnh nhau, tất cả phải thực hiện **cùng một quy tắc sanitize/overwrite**. Một gateway “chỉ forward” header client sẽ phá hỏng toàn bộ trust contract, ngay cả những gateway khác làm đúng.

### Header nào được coi là danh tính đã xác thực?

Ví dụ đặt tên riêng trong mạng nội bộ:

~~~text
X-Verified-Subject: employee-4102
X-Verified-Issuer: https://login.corp.example/realms/employees
X-Verified-Tenant: reports
X-Verified-Assurance: mfa
~~~

Đây **không phải các header có ý nghĩa bảo mật chuẩn tự sinh chỉ vì có tiền tố X-Verified**. Chúng chỉ có giá trị khi:

1. **Proxy được cấu hình/kiểm thử** để tạo giá trị từ một login đã xác minh;
2. **Proxy strip/overwrite** mọi bản client-supplied cùng tên;
3. **Backend không thể bị gọi trực tiếp**, và xác thực/giới hạn được hop của gateway;
4. Các trường có schema, issuer/tenant namespaces và vòng đời rõ;
5. App chỉ dùng thông tin theo policy nội bộ, không tự cấp admin từ một role string.

Một header `X-Verified-Assurance: mfa` do client tự gửi không chứng minh MFA. Nếu backend quyết định nghiệp vụ nhạy cảm dựa trên assurance, nên dùng một **attestation đáng tin** có nguồn/TTL/contract được kiểm hoặc tự xác minh assertion đã ký, không chỉ so sánh literal.

## 4. Spring Security hiểu pre-authentication như thế nào?

Tài liệu Spring Security liệt kê các trường hợp:

- **X.509 client-certificate authentication:** external TLS stack nhận certificate; Spring dùng certificate/principal đã được xử lý theo trust setup.
- **Identity management agent/SiteMinder:** external system xác thực và gửi principal qua HTTP request header.
- **Container-managed authentication:** Servlet container đã xác thực user và cung cấp `HttpServletRequest.getUserPrincipal()`.
- **Custom proxy/Gateway:** ứng dụng có thể tích hợp theo contract cụ thể bằng bộ pre-auth processing classes.

Spring Security cần **lấy identity + authorities**, không xác minh lại password/IdP redirect từ header trong `RequestHeaderAuthenticationFilter`.

Các class trung tâm:

| Class/interface | Nhiệm vụ |
| --- | --- |
| `AbstractPreAuthenticatedProcessingFilter` | Kiểm SecurityContext, trích principal/credential từ request, gửi vào `AuthenticationManager` |
| `RequestHeaderAuthenticationFilter` | Đọc principal (mặc định `SM_USER`) từ HTTP header |
| `J2eePreAuthenticatedProcessingFilter` | Đọc principal do servlet container cung cấp |
| `PreAuthenticatedAuthenticationToken` | Mang principal và details qua auth pipeline |
| `PreAuthenticatedAuthenticationProvider` | Giao `AuthenticationUserDetailsService` tải `UserDetails`/authorities |
| `AuthenticationUserDetailsService<T>` | Tải user dựa trên `Authentication` token, có thể sử dụng details |
| `UserDetailsByNameServiceWrapper` | Bọc `UserDetailsService` thông thường thành adapter phù hợp |
| `PreAuthenticatedGrantedAuthoritiesUserDetailsService` | Dùng authorities trong token details khi contract thật sự tin được |
| `GrantedAuthoritiesContainer` | Cách đưa authorities từ external system vào details theo policy |
| `SecurityFilterChain` / `HttpSecurity` | Gắn filter, phân quyền và session policy |
| `SecurityContext` | Chứa Authentication cho request/phiên |

**Bản thân pre-authentication provider không biết mật khẩu user**. Thông thường nó kiểm tài khoản/authorities từ nguồn local và tạo Authentication bằng identity đã được coi là xác thực ở hop trước. Nếu nguồn identity chưa đủ trust, đừng dùng nó làm pre-auth principal.

## 5. Vòng đời xử lý của AbstractPreAuthenticatedProcessingFilter

Một `AbstractPreAuthenticatedProcessingFilter` điển hình:

1. Được gọi ở chain bảo vệ resource, kiểm `SecurityContext` theo phiên bản/cấu hình.
2. Khi cần xác thực, gọi `getPreAuthenticatedPrincipal(request)` và `getPreAuthenticatedCredentials(request)`.
3. Tạo `PreAuthenticatedAuthenticationToken` ban đầu (chưa có authorities).
4. Gửi token đến `AuthenticationManager`/`PreAuthenticatedAuthenticationProvider`.
5. Provider gọi `AuthenticationUserDetailsService`, từ đó lấy user/roles hợp lệ.
6. Nếu thành công, đặt kết quả vào `SecurityContext` theo lifecycle và repository của phiên bản.
7. Authorization rules như `hasRole("REPORT_VIEWER")` kiểm user đã được map.
8. Nếu thất bại, policy phải **fail closed** — không cho route bảo vệ đi tiếp như anonymous có quyền.

**Bước quan trọng chưa được framework thực hiện:** `RequestHeaderAuthenticationFilter` **không xác minh header do ai phát**. Đây là trách nhiệm kết hợp của proxy/network hoặc một backend cryptographic attestation verifier được xây riêng.

### Thông số thay đổi hành vi

- `setPrincipalRequestHeader("X-Verified-Subject")`: tên header principal; mặc định `SM_USER` dành cho tương thích một số agent cũ.
- `setCredentialsRequestHeader(...)`: nhận một giá trị credentials header nếu có; thông thường pre-auth không có password, mặc định sử dụng dummy value. **Không truyền mật khẩu hoặc access token của user sang backend chỉ để điền credentials**.
- `setExceptionIfHeaderMissing(true)`: `RequestHeaderAuthenticationFilter` ném `PreAuthenticatedCredentialsNotFoundException` nếu không có header (mặc định true).
- `setExceptionIfHeaderMissing(false)`: cho phép thiếu principal header; nếu toàn bộ backend vẫn yêu cầu `authenticated()` và không có auth fallback, request thiếu header không được xem là authenticated. Phải kiểm chính xác filter chain/exception handling.
- `setContinueFilterChainOnUnsuccessfulAuthentication(false)`: tránh nuốt `AuthenticationException` rồi thử một authentication mechanism khác trong route pre-auth-only. Default của các phiên bản hiện đại có thể là true, cần kiểm Javadoc resolved version.
- `setCheckForPrincipalChanges(true)`: so principal header và Authentication hiện tại, làm mới khi có thay đổi (cần cân nhắc overhead/policy).
- `setInvalidateSessionOnPrincipalChange(true)`: nếu bật principal-change checks, session cũ có thể bị invalidate khi principal đổi để tránh session dùng sai user; kiểm hành vi chính xác theo version.

**Không chỉ set một property rồi khẳng định mọi request đã tự động 401.** Filter order, missing-header behavior, AuthenticationEntryPoint, Spring Security version và các authentication mechanisms khác ảnh hưởng HTTP response. Quyết định fail-closed phải được chứng minh bằng integration tests.

## 6. PreAuthenticatedAuthenticationProvider và role mapping

Provider được xây để **load `UserDetails`**, không tự kiểm mật khẩu đã dùng ở IdP/gateway:

~~~text
Trusted gateway header:
  X-Verified-Subject = employee-4102

RequestHeaderAuthenticationFilter
  -> PreAuthenticatedAuthenticationToken("employee-4102", dummy)
  -> AuthenticationManager
  -> PreAuthenticatedAuthenticationProvider
  -> AuthenticationUserDetailsService
  -> local UserDetailsService.loadUserByUsername("employee-4102")
  -> UserDetails { enabled=true, authorities=[ROLE_REPORT_VIEWER] }
  -> authenticated Authentication
~~~

Nếu user không tồn tại, disabled hoặc không được cấp entitlement, `UserDetailsService` phải ném lỗi/thực hiện deny policy. Một số cấu hình user service chỉ kiểm credential store nhưng không kiểm tenant; cần bổ sung local policy.

### Giữ ranh giới identity namespaces

Một hệ thống đa IdP/tenant không nên coi chuỗi `alice` là đủ:

~~~text
Gateway issuer A: alice -> local user 100
Gateway issuer B: alice -> local user 999

Unsafe mapping:
  alice -> local user 100 (không lưu namespace)

Safer mapping:
  (trustedIssuer, stableSubject) -> localUserId
~~~

Nếu gateway chỉ gửi `X-Verified-Subject` và ứng dụng chỉ nhận duy nhất một issuer trust cố định, contract phải ghi rõ namespace đó; nếu nhiều issuer, phải truyền issuer/subject đáng tin trong một **identity assertion** và kiểm nó trước khi map. Đừng chỉ nhận thêm `X-Verified-Issuer` từ client request rồi ghép key.

### Có nên dùng group/role header từ proxy?

Cần rất cẩn thận. `PreAuthenticatedGrantedAuthoritiesUserDetailsService` có thể dùng authorities trong token details có `GrantedAuthoritiesContainer`, nhưng điều đó **không xác minh tính đúng của danh sách roles**. Nếu chỉ cần authentication qua proxy, ưu tiên tra quyền trong database/policy engine của ứng dụng.

Nếu gateway thực sự chịu trách nhiệm authorization cho một số quyền, phải có **contract chặt** về issuer, tenant, mapping group, freshness, revoke và hạn chế quyền. Không tự chuyển `X-Verified-Groups: GlobalAdmins` thành `ROLE_ADMIN` ở mọi ứng dụng.

## 7. JavaConfig Spring Security Servlet: header pre-auth + local roles

Đoạn mã dưới đây là **mẫu cấu hình Spring project** cho các phiên bản có API `SecurityFilterChain`/`RequestHeaderAuthenticationFilter` tương ứng. Nó **không phải chương trình chạy độc lập bằng javac**: cần Spring Boot Web + Security dependencies, một `UserDetailsService` chính thức, hạ tầng gateway đã chặn direct backend traffic, và bản SecurityFilterChain được lắp vào ứng dụng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class TrustedProxyPreauthConfig {

    @Bean
    SecurityFilterChain preauthSecurityFilterChain(
            HttpSecurity http,
            UserDetailsService localUsers) throws Exception {

        // Account status, tenant và role được kiểm trong localUsers.
        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
                userDetailsAdapter =
                new UserDetailsByNameServiceWrapper<>(localUsers);

        provider.setPreAuthenticatedUserDetailsService(
                userDetailsAdapter);

        AuthenticationManager authenticationManager =
                new ProviderManager(provider);

        RequestHeaderAuthenticationFilter preauthFilter =
                new RequestHeaderAuthenticationFilter();

        preauthFilter.setPrincipalRequestHeader("X-Verified-Subject");
        preauthFilter.setExceptionIfHeaderMissing(false);
        preauthFilter.setContinueFilterChainOnUnsuccessfulAuthentication(
                false);
        preauthFilter.setCheckForPrincipalChanges(true);
        preauthFilter.setAuthenticationManager(authenticationManager);

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/reports/**").hasRole("REPORT_VIEWER")
                .anyRequest().authenticated())
            .addFilterBefore(
                preauthFilter,
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Điều kiện bắt buộc trước khi dùng:** `X-Verified-Subject` đã được gateway **strip và overwrite**, và backend **không thể** được truy cập từ Internet/untrusted workloads. Chính code này **không tự kiểm source IP, client certificate hoặc chữ ký identity assertion**. Đó là lớp tin cậy mà hạ tầng phải đảm bảo (hoặc có verifier riêng trước pre-auth filter).

**Vì sao chọn STATELESS trong ví dụ?** Mẫu này mong proxy gắn identity đã xác minh **ở mỗi request**. Khi Spring không dựa vào server-side session để lưu một Authentication cũ, mất identity header ở request tiếp theo không được tái sử dụng session đã xác thực. Tuy nhiên session policy **không xác thực gateway** và cần test cùng CSRF, API/browser flows, security context repository và ứng dụng thật.

**Vì sao `setExceptionIfHeaderMissing(false)`?** Health endpoint được phép không có identity; mọi route còn lại bị `authenticated()`/`hasRole` hạn chế. Đây là một **thiết kế cụ thể**, không phải khuyến cáo tắt exception cho mọi app. Nếu muốn tất cả requests trên một chain chỉ dành cho gateway phải có header, có thể để default true và tách health/anonymous endpoints sang chain khác. Cần test HTTP status/error handler của từng nhánh.

**Vì sao không khai báo `@Bean RequestHeaderAuthenticationFilter`?** Trong Spring Boot, một bean thuộc loại servlet `Filter` có thể bị container tự đăng ký **ngoài** Spring Security filter chain nếu không được quản lý thứ tự/đăng ký phù hợp, gây chạy đôi hoặc sai thứ tự. Ví dụ tạo filter bên trong chain để đơn giản hóa phạm vi. Với hệ thống nhiều chains, lựa chọn `securityMatcher` và filter placement phải được thiết kế rõ.

**Vì sao `setContinueFilterChainOnUnsuccessfulAuthentication(false)`?** Để provider fail không bị bỏ qua và dẫn tới cơ chế auth khác ít an toàn hơn. Trong hệ thống có login form được duyệt, hãy dùng chains/path trust boundaries riêng, không vô tình cho header authentication thất bại rồi **fallback** sang một cách xác thực bypass gateway.

### Những phần cần bổ sung ở sản phẩm thật

- Bean `UserDetailsService` dùng data source/identity links thật, kiểm active/locked/tenant.
- AuthenticationEntryPoint và handler thống nhất 401/403 hoặc proxy redirect semantics; code trên không cố hứa một status cụ thể.
- Cơ chế xác thực **gateway hop**/mTLS, network policies, ingress listeners và header sanitization.
- Principal normalization, issuer-scoped key và allowlist tenant theo contract.
- Audit/correlation ID, session/CSRF design, error handling và rate limiting.
- Test tích hợp trong **đúng Spring Security/Boot version** đã resolve.

## 8. Ví dụ local UserDetailsService minh họa

Trong ứng dụng một issuer duy nhất, có thể dùng service local tra theo ID:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

UserDetailsService localUsers = subject -> {
    if (!"employee-4102".equals(subject)) {
        throw new UsernameNotFoundException("Unknown local subject");
    }
    return User.withUsername(subject)
            .password("{noop}NOT_USED_FOR_PREAUTH")
            .roles("REPORT_VIEWER")
            .disabled(false)
            .build();
};
~~~

**Đây chỉ là fragment minh họa, không phải database implementation**. Password dummy không được sử dụng để xác thực ở pre-auth provider; trong production không hardcode/duy trì mật khẩu giả như một cách bảo mật. User status/role phải lấy từ nguồn nghiệp vụ đã kiểm; nếu ứng dụng cũng cho phép form/password login, không dùng placeholder password để làm account credential thật.

Trường `employee-4102` là một **stable subject đã được gateway xác thực**, không phải `displayName`/email do user tự thay. Với nhiều issuers, truyền principal namespace trong một identity key/attestation đáng tin rồi map về ID nội bộ. **Không tự lower-case subject** nếu IdP contract coi case là có ý nghĩa.

## 9. Đường vào backend: không được bypass gateway

Một flow sai:

~~~text
Public internet
  -> https://portal.example.com (gateway verifies login)
  -> http://spring-backend:8080 (Spring reads X-Verified-Subject)

BUT ALSO:
Public internet -> http://spring-backend-public-ip:8080
  with X-Verified-Subject: admin
  -> Spring treats admin as authenticated
~~~

**Đây là lỗ hổng nghiêm trọng.** Header từ client trên direct path sẽ đi thẳng vào Spring filter. Không có một property Spring nào có thể biến một HTTP header do user gửi thành assertion xác thực đúng khi thiếu trust boundary.

### Kiểm soát phải có

1. Backend listen trên private interface/subnet và firewall/security group chặn mọi source không phải gateway.
2. Trong Kubernetes, `ClusterIP`/NetworkPolicy chỉ cho ingress pods đã định danh gọi backend; kiểm cả internal pods cùng cluster, không chỉ traffic Internet.
3. Ingress controller/gateway strip tất cả inbound identity headers trước authentication, kể cả duplicate spelling/hyphen/underscore forms mà stack có thể diễn giải khác.
4. Gateway chỉ tạo header từ identity context sau khi kiểm session/credential.
5. Gateway↔backend dùng TLS/mTLS hoặc kết nối tương đương theo threat model; nếu mTLS phải kiểm client cert identity đúng gateway, không chỉ “một cert hợp lệ bất kỳ”.
6. Xóa/không forward authentication headers qua untrusted secondary proxies, caches, middlewares; có danh sách chain rõ.
7. Cần kiểm mạng test rằng direct pod/NodePort/load-balancer/management endpoints không bypass.
8. Hạn chế listener health/admin và tách public/untrusted routes khỏi pre-auth-only chain.
9. Test **spoofed header** từ Internet phải bị xóa hoặc chặn.
10. Theo dõi policy drift sau deploy/Kubernetes ingress changes.

**IP allowlist một mình không phải chứng thực danh tính đủ mạnh** trong mọi cloud/service-mesh architecture: pod/IP có thể thay đổi, NAT hoặc gateway có nhiều workloads. Chọn danh tính workload/service identity + network segmentation + TLS theo yêu cầu.

## 10. Ingress proxy và ví dụ header contract

Một số sản phẩm gateway dùng auth sub-request, OIDC proxy, SAML gateway hoặc sidecar. Các chỉ dẫn dưới là **hợp đồng logic**, không phải một nginx.conf đầy đủ có thể paste vào production:

~~~text
ON PUBLIC REQUEST:
  drop any inbound X-Verified-Subject
  drop any inbound X-Verified-Issuer
  drop any inbound X-Verified-Tenant
  authenticate the browser/session using approved IdP
  reject unauthenticated/expired/revoked sessions
  derive immutable subject and verified issuer
  set X-Verified-Subject and related fields from trusted identity context
  proxy only to private backend over authenticated hop

ON BACKEND:
  accept requests only from the authenticated gateway identity
  do not trust headers on direct/untrusted routes
  find local user and authorities
  deny unknown/disabled user or wrong tenant
  apply resource-level authorization
~~~

**Không triển khai bằng cách chỉ viết `proxy_set_header X-Verified-Subject $http_x_verified_subject;`**: biến `$http_x_verified_subject` trong nhiều proxy stacks mang nguyên giá trị **do client gửi**. Nếu forward trực tiếp, attacker được tự chọn username. Cần nguồn identity nội bộ của proxy **sau xác thực** và cơ chế overwrite từ nó; nếu gateway không có API/biến trusted user, không nên cấu hình header pre-auth.

### X-Forwarded headers không phải authentication assertions

`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `Forwarded` dùng mô tả client IP/scheme/host qua proxies, không mang bảo đảm user đã xác thực. Chỉ tin các phần được trusted proxies thêm sau khi đã xóa giá trị untrusted. Kể cả `X-Forwarded-For` xác định đúng IP, **IP không phải user principal**.

Cấu hình `server.forward-headers-strategy=framework` có thể làm Spring Boot xử lý forwarded host/proto cho URL generation, nhưng **không xác thực ai tạo các headers**. Gateway/ingress phải bảo vệ nguồn; không lấy IP hoặc hostname từ header client để tự quyết định user.

## 11. Khi nào dùng header, khi nào dùng signed assertion hoặc JWT?

Không có một phương thức “đúng cho mọi kiến trúc”. Cần chọn theo trust boundary và khả năng kiểm:

| Kiểu truyền danh tính | Ưu điểm | Rủi ro/điều kiện |
| --- | --- | --- |
| **Plain internal identity header** | Đơn giản; phù hợp với private trusted-hop | Chỉ an toàn khi network/mTLS/gateway sanitization thật sự đảm bảo; không có chứng thực per-header |
| **Signed gateway assertion/JWT** | Backend có thể xác minh issuer, audience, signature, expiry | Cần key rotation, alg allowlist, replay/privacy controls; không được tin claim trước khi verify |
| **OIDC Access Token trực tiếp** | Backend dùng OAuth2 Resource Server | Phải kiểm Access Token intended audience/scopes; khác pre-auth header và khác ID Token |
| **Mutual TLS client cert** | Backend xác minh service/gateway identity theo cert | Không tự xác thực **end-user** nếu chỉ có gateway cert; vẫn cần user binding |
| **Container principal** | Container kiểm authentication và cung cấp `getUserPrincipal()` | Không có nếu container không được cấu hình; principal không phải header raw |
| **Native browser OIDC Login** | Spring tự xử lý code/ID Token, không tin raw header | Thích hợp khi app tự làm RP và cần quản lý login |

Nếu gateway phát **JWT ký** cho backend, một hướng vững chắc là `oauth2ResourceServer().jwt()` với validator cho issuer/audience/exp và token purpose, nếu token đúng là access token dùng cho API. Không tự gọi `jwt.decode()` rồi tạo `UsernamePasswordAuthenticationToken` đã authenticated mà chưa kiểm cryptography. Nếu token là **custom gateway identity assertion**, dùng verifier riêng có contract rõ; không mặc định mọi JWT đều dùng chuẩn OAuth2 Resource Server.

**Chữ ký JWT không thay channel controls** khi có rủi ro replay/exfiltration; đồng thời mTLS tới gateway **không xác thực user** nếu header không được gắn với session đúng.

## 12. Sai lầm về authenticationDetails và roles

Một `Authentication.getDetails()` có thể chứa metadata như remote address/session ID. Tài liệu Spring Security pre-auth cũng cho phép cấu hình `GrantedAuthoritiesContainer` trong details để truyền authorities từ external container.

**Không coi mọi thuộc tính trong details là đáng tin**. Nguồn tạo details phải được kiểm bằng gateway/container trust. Các flags như `isUserInRole()` của servlet container chỉ đáng tin khi **container** đã xác thực principal và role mapping đúng. Header `X-Groups` do browser thêm không biến thành trusted `GrantedAuthority` chỉ vì được đặt vào details.

Nếu phải chuyển group membership từ gateway:

- Chỉ nhận issuer + stable subject + role claims đã được gateway kiểm theo contract.
- Giới hạn các giá trị role trong allowlist, không mapping regex kiểu “chứa Admin”.
- Nêu rõ policy nào là **gateway authorization** và policy nào là **app local authorization**.
- Đảm bảo account disabled/offboarded được kiểm tại backend hoặc có session revocation SLA.
- Với multi-tenant, quyền cần namespace issuer/tenant/resources; không chỉ tên group đơn lẻ.
- Có audit dấu vết ai đã phê duyệt việc ánh xạ quyền.

## 13. Session, principal change và logout

Một gateway thường có **upstream SSO session**, còn Spring có thể chọn dùng **local HTTP session** hoặc stateless mỗi request. Chúng là **hai trạng thái khác nhau**.

| Tình huống | Rủi ro nếu không thiết kế |
| --- | --- |
| Browser đã logout gateway nhưng còn Spring JSESSIONID | App tiếp tục tin Authentication cũ |
| User A đăng nhập gateway rồi đổi thành B trong cùng browser | Spring giữ SecurityContext của A nếu không re-evaluate |
| Proxy hết hạn session nhưng vẫn gửi cached identity header | Backend chấp nhận user đã bị thu hồi |
| App có public bypass route và protected route cùng session | Có thể carry over Authentication giữa trust contexts |
| Nhiều Spring nodes dùng session store chung | Role/identity stale khác nhau khi thay chính sách |
| Gateway session MFA expired nhưng backend session còn sống | Sensitive operation dùng assurance cũ |

### Hai mô hình

**Mô hình A — stateless mỗi request (phù hợp ví dụ JavaConfig):** Gateway xác thực session và tạo header verified ở **mỗi request**; backend không rely vào một `SecurityContext` persisted dài hạn. Nếu mất header, protected route fail. Có chi phí local user lookup/caching và cần chính sách refresh/revocation rõ.

**Mô hình B — stateful Spring session:** Spring tạo session sau pre-auth và sử dụng trên các request tiếp theo. Phải cấu hình SecurityContextRepository, session fixation/concurrency, principal-change detection, logout propagation hoặc TTL/revalidation rõ. **Không giả định logout gateway tự xóa JSESSIONID tại Spring**.

### Identity switch và Spring filter options

`setCheckForPrincipalChanges(true)` giúp filter so principal hiện tại với principal lấy từ request; `setInvalidateSessionOnPrincipalChange(true)` có tác dụng khi có session và principal-change detection. Tuy nhiên thiếu header, custom principal normalization, multi-issuer identities và các authentication chains có thể có behavior khác nhau; cần test chính xác theo phiên bản/framework và không dựa vào một cờ duy nhất.

**Đừng tắt `csrf` toàn site** chỉ để pre-auth hoạt động. Nếu browser mang cookie và làm state-changing requests, CSRF vẫn phải được phân tích. Trong API stateless với header do gateway thêm, CSRF/risk phụ thuộc browser credential model và chính sách của hệ thống, không tự động miễn trừ.

## 14. MFA, authorization context và step-up

Gateway có thể chứng minh user đã hoàn tất login cơ bản, nhưng một thao tác nghiệp vụ như duyệt thanh toán cần **MFA mới** (*step-up authentication*) hoặc assurance riêng.

Ví dụ:

~~~text
GET /reports
  requires authenticated user + ROLE_REPORT_VIEWER

POST /payments/approve
  requires local ROLE_PAYMENT_APPROVER
  and independently verified recent MFA assurance
  and dual control / maker-checker business rule
~~~

Một string `X-Verified-Assurance: mfa` chỉ an toàn nếu gateway đã sinh nó từ **authentication context đáng tin**, có thời hạn, issuer/audience, replay/freshness policy và backend không thể bị bypass. Nếu gateway không cam kết freshness, ứng dụng cần redirect/step-up theo protocol riêng hoặc xác minh signed assertion có `auth_time`/`acr`/`amr` theo contract.

**Không cấp quyền phê duyệt thanh toán chỉ từ vai trò hoặc assurance header**. Authentication strength và authorization entitlement là hai phép kiểm độc lập.

## 15. Tính đúng của identity mapping

Trong doanh nghiệp, người dùng có thể có nhiều định danh:

~~~text
Gateway subject:        employee-4102
OIDC upstream subject:  00u.... (theo issuer)
Email:                  an@example.org
Display name:           Nguyễn An
Local user:             internal-user-704
Tenant:                 reports-corp
~~~

Nếu ứng dụng lưu bằng email, đổi email hoặc một tenant khác tạo email tương tự có thể dẫn tới account collision. Ưu tiên **subject ổn định được IdP/gateway bảo đảm**, scoped theo issuer/tenant và quy trình migration.

**Những điều cần kiểm:**

- Không dùng header `X-Remote-User` do client tự gửi.
- Nếu gateway cho phép nhiều IdPs, giữ **issuer + subject** và chính sách link account.
- Không tự canonicalize case/Unicode nếu source ID có semantics phân biệt.
- Không dùng displayName làm key.
- Khi `UserDetailsService` không tìm được user, từ chối hoặc dùng JIT provisioning **chỉ khi có approval policy**.
- Khi user đã bị disabled, backend không tiếp tục cấp quyền vì gateway vẫn còn session.
- Phải chống local username alias/duplicate và user deletion/reuse.

## 16. Quan sát log và phân biệt lỗi ở từng tầng

Một flow lỗi cần biết **đã được xác thực tại gateway chưa**, **header đã được gắn chưa**, **Spring có user nội bộ chưa**, và **app có đủ quyền chưa**.

| Biểu hiện | Tầng nghi ngờ | Kiểm gì? |
| --- | --- | --- |
| Gateway redirect login liên tục | Upstream login/session/cookie | IdP redirect/callback/session/MFA |
| Request không đến backend | Gateway ACL/network/route | Ingress route, auth subrequest, backend health |
| Backend có header nhưng không tin gateway | mTLS/service identity/network policy | Certificate/ingress identity, path bypass |
| `PreAuthenticatedCredentialsNotFoundException` | Missing principal header | Proxy inject logic, header strip, filter config |
| `UsernameNotFoundException` | Local user lookup | Issuer-scoped identity, provisioning, account disabled |
| Spring 401/403 sau gateway login | Filter order/authorization | SecurityContext, UserDetails, requestMatchers |
| User A thấy data B | Session identity collision/tenant authorization | Principal changes, local mapping, object-level policy |
| User bị vô hiệu hóa nhưng vẫn truy cập | Session/revocation stale | Gateway session expiration, local cache TTL |
| User được ROLE_ADMIN sai | Group/role header được tin quá rộng | Local authority mapper, allowlist |
| Browser spoof `X-Verified-Subject` và được login | Header sanitization/direct backend bypass | **Security incident — chặn ngay, sửa trust boundary** |
| External X-Forwarded-Host thay redirect | Trusted proxy forwarding lỗi | Strip/replace Host/Forwarded chain |
| Health check thiếu header bị 500 | Missing-header behavior trên route public | Split chains hoặc exceptionIfHeaderMissing false |
| Logout gateway xong backend vẫn thấy auth | Spring session stale | Stateless request or coordinated session invalidation |
| Fail only on pod B | Ingress/identity injection cấu hình lệch | So network policy, filter chains, deployment config |

### Logging tối thiểu nhưng đủ

Log nên có request correlation ID, gateway/service ID đã xác minh, **local user ID**, tenant và decision code (authenticated/denied/unknown). Không log raw access tokens, ID tokens, cookies, client secrets, SAML assertions, Kerberos tickets, đầy đủ identity headers hoặc thông tin cá nhân không cần thiết.

**Nếu thấy header injection từ Internet thành công, không chỉ sửa một endpoint:** cần kiểm mọi entry path, phiên bị lạm dụng, quyền admin và dữ liệu đã truy cập, đồng thời triển khai incident response theo chính sách doanh nghiệp.

## 17. Java 17 độc lập: mô phỏng hợp đồng tin cậy giữa gateway và Spring

Chương trình **Java thuần** dưới đây giúp học viên phân biệt **tin được kênh gateway** và **cấp quyền tài nguyên cho user**. Nó dùng một record identity chứa subject, issuer, tenant, assurance, role do edge khai báo, cùng local policy cấp role từ database mô phỏng.

Quan trọng: hàm `evaluate` **không thực sự xác minh TLS/mTLS, chữ ký, OIDC tokens hoặc gateway session**. Các boolean `trustedGatewayHop` và `headersSanitized` chỉ mô phỏng kết quả do hạ tầng **đã** kiểm. Không dùng chương trình này để tạo Authentication production.

Tạo file **`TrustedGatewayPreauthDemo.java`**:

~~~java
import java.util.Map;
import java.util.Set;

public class TrustedGatewayPreauthDemo {

    record EdgeIdentity(
            String subject,
            String issuer,
            String tenant,
            String assurance,
            String claimedRole) {}

    static final String ISSUER =
            "https://login.corp.example/realms/employees";

    static final Map<String, Set<String>> LOCAL_ROLES = Map.of(
            "employee-4102", Set.of("ROLE_REPORT_VIEWER"));

    static String evaluate(
            EdgeIdentity identity,
            boolean trustedGatewayHop,
            boolean headersSanitized) {

        if (!trustedGatewayHop) {
            return "DENY: untrusted gateway hop";
        }
        if (!headersSanitized) {
            return "DENY: headers not sanitized";
        }
        if (identity == null
                || identity.subject() == null
                || identity.subject().isBlank()) {
            return "DENY: missing subject";
        }
        if (!ISSUER.equals(identity.issuer())) {
            return "DENY: unexpected issuer";
        }
        if (!"reports".equals(identity.tenant())) {
            return "DENY: tenant not allowed";
        }

        Set<String> localRoles =
                LOCAL_ROLES.get(identity.subject());
        if (localRoles == null) {
            return "DENY: local user not approved";
        }

        if (!"mfa".equals(identity.assurance())) {
            return "DENY: assurance too low";
        }

        // Do NOT trust identity.claimedRole() for local authorities!
        return "ALLOW: " + String.join(",", localRoles);
    }

    public static void main(String[] args) {
        EdgeIdentity user = new EdgeIdentity(
                "employee-4102",
                ISSUER,
                "reports",
                "mfa",
                "ROLE_ADMIN");

        System.out.println("Trusted: "
                + evaluate(user, true, true));
        System.out.println("Direct: "
                + evaluate(user, false, true));
        System.out.println("Unstripped header: "
                + evaluate(user, true, false));

        EdgeIdentity unknownUser = new EdgeIdentity(
                "outside-999", ISSUER, "reports", "mfa", "ROLE_USER");
        System.out.println("Unapproved: "
                + evaluate(unknownUser, true, true));

        EdgeIdentity otherTenant = new EdgeIdentity(
                user.subject(), ISSUER, "payments", "mfa", "ROLE_ADMIN");
        System.out.println("Wrong tenant: "
                + evaluate(otherTenant, true, true));

        EdgeIdentity weakLogin = new EdgeIdentity(
                user.subject(), ISSUER, "reports", "pwd", "ROLE_ADMIN");
        System.out.println("No MFA: "
                + evaluate(weakLogin, true, true));

        EdgeIdentity wrongIssuer = new EdgeIdentity(
                user.subject(), "https://attacker.example",
                "reports", "mfa", "ROLE_ADMIN");
        System.out.println("Wrong issuer: "
                + evaluate(wrongIssuer, true, true));

        System.out.println("External admin promoted: "
                + evaluate(user, true, true)
                    .contains("ROLE_ADMIN"));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac TrustedGatewayPreauthDemo.java
java TrustedGatewayPreauthDemo
~~~

**Stdout chính xác:**

~~~text
Trusted: ALLOW: ROLE_REPORT_VIEWER
Direct: DENY: untrusted gateway hop
Unstripped header: DENY: headers not sanitized
Unapproved: DENY: local user not approved
Wrong tenant: DENY: tenant not allowed
No MFA: DENY: assurance too low
Wrong issuer: DENY: unexpected issuer
External admin promoted: false
~~~

**Giải thích từng điểm:**

- `Trusted` được allow **vì demo giả định gateway đã được chứng thực + header đã sanitize + account/tenant/MFA và role local hợp lệ**.
- `Direct` bị từ chối dù body identity trông giống user, vì request không từ trusted hop.
- `Unstripped header` từ chối vì browser có thể đã gắn principal tùy ý.
- `Unapproved` từ chối account không có trong kho local.
- `Wrong tenant` bị từ chối khi tenant không khớp resource contract.
- `No MFA` minh họa chính sách yêu cầu assurance phù hợp.
- `Wrong issuer` cho thấy identifier phải scoped; tuy nhiên so chuỗi issuer **không** là xác minh chữ ký thật.
- `External admin promoted: false` cho thấy `claimedRole=ROLE_ADMIN` không được tự ánh xạ thành quyền local.

**Không biến `trustedGatewayHop=true` thành một giá trị hardcode trong Spring production.** Muốn biết gateway có thật sự trusted phải dùng network/service identity/mTLS/chữ ký hoặc phương thức được tổ chức phê duyệt; sau đó mới cho phép pre-auth filter nhận principal. Code demo cũng không làm session, CSRF, authentication filter hoặc HTTP network thật.

## 18. Test matrix bắt buộc cho tích hợp proxy pre-auth

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Gateway SSO | User login qua IdP đã phê duyệt | Gateway xác minh session/credential trước khi gắn header |
| Anonymous | Chưa có gateway login | Gateway redirect/401, không gắn verified identity |
| MFA policy | User chỉ đăng nhập bằng password | Sensitive route không được step-up bypass |
| Valid identity | Gateway hợp lệ gửi subject đã verify | Spring load đúng local user |
| Missing header | Protected request không có principal | Không được authenticated |
| Forged principal | Browser gửi `X-Verified-Subject: admin` | Gateway strip/overwrite, backend không nhận admin |
| Duplicate identity headers | Client gửi nhiều values/case variants | Proxy canonicalize và chặn ambiguous request |
| Direct backend | Truy cập NodePort/pod/private IP không qua gateway | Network/mTLS từ chối |
| Wrong gateway cert | Workload lạ có client certificate không được phép | Backend không trust |
| Proxy skipped path | URL encoded/alternate host bypass auth route | Bị chặn, không vào backend protected |
| Alternate ingress | Gọi backend qua ingress phụ/debug endpoint | Không bypass pre-auth |
| Valid external subject | `employee-4102` + approved issuer | Local lookup đúng namespace |
| Unknown issuer | Attestation từ source không nằm allowlist | Deny |
| Same username, different issuer | Hai người cùng `alice` | Không gộp local account |
| Unknown local user | Gateway auth OK, local record không tồn tại | Deny hoặc JIT theo policy có review |
| Disabled account | Local disabled, gateway session còn | App deny |
| Local role missing | User có identity, không có role cho resource | HTTP 403 theo policy |
| Role spoof | Header chứa `ROLE_ADMIN` | Không được cấp admin từ raw header |
| Tenant boundary | User Reports đọc Payments data | Deny |
| Gateway logout | Session gateway expired/revoked | Backend không tái dùng authenticated session cũ |
| Identity switch | User A → B trong browser | Không giữ SecurityContext/role của A |
| Gateway 5xx/session store down | Proxy không xác minh được identity | Fail closed, không forward verified header |
| Proxy header rules change | Một gateway node quên sanitize | Test tìm và chặn drift |
| Forwarded header spoof | Client tự đặt `X-Forwarded-Host`/For | Không thay auth/redirect/tenant trust |
| Session fixation | Identity đổi giữa request/session | Không giữ quyền từ principal cũ |
| CORS/CSRF | Cross-site browser request | Không bypass nghiệp vụ chỉ vì pre-auth |
| Spring filter chain | Request đi qua chain đúng | Filter hoạt động đúng thứ tự/route |
| Java role mapping | `UserDetailsService` trả local authorities | Không dùng proxy group unreviewed |

**Chỉ mock `Authentication` trong Spring MVC test chưa đủ**: nó giúp test controllers/RBAC, nhưng không kiểm gateway header sanitization, direct backend isolation, mTLS hoặc real session logout. Cần E2E test xuyên qua gateway và negative tests cố tình gửi spoofed headers trên các đường được phép thử.

### Ví dụ test nhận thức bằng curl

~~~bash
# Trong lab được phép, gọi GATEWAY public với header giả:
curl -i \
  -H "X-Verified-Subject: admin" \
  "https://reports.corp.example/reports"

# Test backend direct phải bị network/mTLS từ chối:
curl -i \
  -H "X-Verified-Subject: admin" \
  "https://backend-test-private.example/reports"
~~~

Các host trên là minh họa. Không có stdout cố định và không được xem HTTP 200 từ gateway như bằng chứng security PASS: cần kiểm **backend đã nhận user nào**, có hay không header mà gateway tự phát, và account role thực tế. Nếu direct path trả response có quyền admin thì đó là **lỗi bảo mật phải xử lý**, không phải hiện tượng để chấp nhận khi staging.

## 19. Tách phạm vi filter chains và cơ chế xác thực khác

Một ứng dụng có thể có nhiều loại endpoint:

~~~text
/health                health checks không cần identity
/reports/**            proxy-preauthenticated web app
/api/**                OAuth2 resource server với bearer access token
/login/**              OIDC RP login nếu ứng dụng có flow riêng
/internal/**           mTLS service-to-service
~~~

Không nên đặt một `RequestHeaderAuthenticationFilter` tin raw headers lên **mọi** paths rồi thêm form login/OIDC/Bearer dưới cùng chain thiếu thiết kế; có thể làm yếu một cơ chế nhờ fallback hoặc đọc nhầm user từ các request contexts.

Các lựa chọn thiết kế:

- Đặt **SecurityFilterChain** riêng cho proxy-only routes; mọi request tới chain này phải đến từ trusted proxy.
- API bearer-token dùng một chain có `oauth2ResourceServer(...)` với issuer/audience validation.
- Health endpoints có chain cho permitAll nhưng **chỉ nằm trên mạng/port thích hợp**.
- Form/OIDC login native nên ở chain/path riêng có state/session/CSRF rules của nó.
- Khi gateway terminate TLS và inject identity, Spring phải tin đúng **trang mạng này**, không trộn với public listener.
- Trường hợp proxy gửi **signed bearer access token**, cân nhắc dùng resource-server validation thay vì chỉ trích `sub` vào header.

**Không dùng `anyRequest().permitAll()` hoặc anonymous với authority mặc định để làm “fallback” trong khi pre-auth lỗi.** Nên fail closed, thông báo 401/403 được thiết kế, quan sát logs và sửa trust boundary.

## 20. Container và X.509 pre-auth: cùng khái niệm, nguồn khác

Spring Security không giới hạn pre-auth ở HTTP header:

### Java EE/Jakarta Servlet container authentication

Servlet container có thể xác thực người dùng bằng realm cấu hình trước khi Spring xử lý. `J2eePreAuthenticatedProcessingFilter` lấy principal từ `HttpServletRequest.getUserPrincipal()`. `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` có thể dùng `isUserInRole(...)` và role mapping theo configuration.

**Điều kiện tin cậy:** chính servlet container phải thật sự thực hiện authentication, chứ không phải custom request wrapper lấy `getUserPrincipal()` từ raw header user input. Container role không tự có quyền business tenant.

### X.509 client certificate

Spring Security có hỗ trợ X.509 authentication, nơi TLS layer xác minh client certificate khi có mTLS. Principal được rút ra theo rule được cấu hình từ certificate fields. Cần certificate chain trust, revocation/lifetime, subject/issuer mapping và đúng client-auth policy. `X.509` không tương đương với việc tự chuyển `X-Client-Cert` từ Internet vào Spring rồi tin giá trị: header certificate nếu có phải được bảo vệ/verify qua proxy trust contract.

### Agent/legacy SSO

SiteMinder hoặc một web access management agent có thể gắn header `SM_USER`. Tài liệu RequestHeaderAuthenticationFilter còn giữ `SM_USER` là **default header name**, nhưng **không vì mặc định mà nó an toàn**. Bạn phải chắc chắn agent là nguồn duy nhất có thể cung cấp header đó.

## 21. Đánh giá “pre-auth” là bypass hay defense-in-depth?

Bản chất pre-auth là **chuyển ranh giới thực hiện kiểm danh tính** từ backend sang upstream đã được tin cậy. Điều đó có thể tăng chất lượng an ninh nếu gateway thực thi SSO/MFA tập trung, secret/token xử lý riêng và backend chỉ nhận danh tính tối thiểu. Tuy nhiên nó cũng tạo **failure mode tập trung**: một lỗi header sanitization, bypass path hoặc gateway compromise có thể ảnh hưởng toàn bộ applications phía sau.

### Bảo vệ bổ sung nên có

1. **Network identity:** xác thực workload/proxy, mTLS, không public backend.
2. **Cryptographic identity attestation:** signed assertion khi muốn bảo vệ hop độc lập hoặc chống rủi ro intermediary.
3. **App-local entitlement check:** user active/locked, roles, tenant object ACL.
4. **Header contract versioning:** tên, encoding, max length, duplicate, issuer namespace, freshness.
5. **Observability:** có metrics cho missing header, unapproved user, role denied, gateway error.
6. **Revocation:** gateway logout và app session/caches đồng bộ theo SLA.
7. **Security testing:** direct backend, spoofed role, header collisions, alternate ingress.
8. **Operational ownership:** ai chịu trách nhiệm khi gateway down, user offboarded hoặc chính sách thay đổi.
9. **Fallback discipline:** không có “open route” khi gateway fail; fallback OIDC phải được thiết kế riêng.
10. **Incident response:** thu hồi sessions/tokens, audit các endpoint bị bypass, sửa security groups/ingress.

### Chống nhầm với “thêm header kiểm tra bí mật”

Một số hệ thống thêm `X-Shared-Secret: fixed-value` rồi coi đó là bằng chứng gateway đáng tin. Một secret tĩnh trong HTTP header có thể bị lộ qua logs/sidecars, được copy/replay, thiếu binding với user/session và khó rotate. **Không coi shared secret header là biện pháp thay thế mTLS hoặc signed short-lived identity assertion** khi threat model đòi hỏi chống giả mạo/replay.

## 22. Quy trình triển khai production từng bước

1. **Xác định authority của gateway**: gateway xác thực user qua gì (OIDC, SAML, Kerberos, session) và ai vận hành.
2. **Vẽ sơ đồ đường mạng**: browser→gateway, ingress/sidecar→backend, các ports và mọi đường bypass.
3. **Chọn signal**: stable subject + trusted issuer + tenant (nếu cần), không truyền raw password/token.
4. **Định nghĩa sanitize contract**: drop/overwrite identity headers; không để client quyết định trusted user.
5. **Thiết lập backend isolation**: firewall, security group, NetworkPolicy, mTLS workload identity.
6. **Cấu hình Spring pre-auth**: header filter + provider + user details + explicit authorization.
7. **Phân tích phiên**: stateless request vs Spring session, logout, principal switch, revocation.
8. **Tách authentication chains**: proxy-only paths khác resource server/OIDC/API/health khi phù hợp.
9. **Thử tích hợp**: gateway thực, user thật trong lab, local roles, tenant object ownership.
10. **Chạy negative tests**: spoof direct/duplicate headers, issuer/tenant mismatch, gateway down, user disabled.
11. **Giám sát drift**: gateways/pods config, header contract, RBAC và TLS certificate.
12. **Hướng dẫn vận hành**: dashboard, alerts, incident playbook, rollback khi thay ingress/auth policies.

**Không giao production cho tới khi test trực tiếp backend bằng header giả bị từ chối**. Đó là negative test quan trọng nhất cho pre-auth header deployment.

## 23. Câu hỏi tự kiểm tra và đáp án

### Bài A — request header đến từ đâu?

Browser gửi `X-Verified-Subject: admin` đến gateway, gateway forward nguyên.

**Đáp:** Lỗ hổng **header spoofing**. Gateway phải strip/overwrite và backend chỉ chấp nhận hop đã được bảo vệ. Spring `RequestHeaderAuthenticationFilter` không thể phân biệt header của user và proxy nếu cả hai giống nhau.

### Bài B — role từ gateway có đáng tin tuyệt đối?

Gateway gửi `X-Verified-Groups: ADMIN`; user chưa được phê duyệt trong tenant.

**Đáp:** Không. App phải có local role/tenant policy; nếu sử dụng group claims từ proxy cần contract được review. Không tự map `ADMIN` thành `ROLE_ADMIN` trên mọi app.

### Bài C — logout gateway có đủ không?

User logout IdP, nhưng trình duyệt còn `JSESSIONID` của Spring và backend dùng SecurityContext cũ.

**Đáp:** Không đủ. Thiết kế **stateless mỗi request** hoặc session expiration/invalidation/revalidation phối hợp với gateway. Login/logout/session state phải xét riêng.

### Bài D — request có HTTPS là tin gateway được chưa?

Backend dùng HTTPS nhưng cho mọi workload kết nối và chấp nhận identity header tùy ý.

**Đáp:** Chưa. Server-side HTTPS thường chỉ xác thực server với client; backend cần **xác thực/giới hạn gateway identity** (mTLS/client cert/network policy/chữ ký assertion) và sanitation header.

### Bài E — cùng tên alice ở hai IdP

`alice` từ issuer A và `alice` từ issuer B.

**Đáp:** Không tự gộp. Dùng `(trustedIssuer, subject)` để liên kết tới localUserId, giữ tenant boundary, chỉ account-link theo quy trình có chứng thực.

### Bài F — proxy đã login OK nhưng Spring 403?

**Đáp:** Đây có thể là phân quyền đúng. Spring có thể nhận principal hợp lệ nhưng user thiếu local role/entitlement cho resource. Không sửa bằng `permitAll()`.

### Bài G — cơ chế nào nên dùng khi gateway gửi JWT?

**Đáp:** Nếu đó là OAuth2 Access Token thực sự dành cho backend API, dùng Resource Server JWT validation với issuer, audience và scopes đúng; nếu là custom signed identity assertion, phải có verifier tương ứng. Đừng chỉ decode token lấy `sub` rồi coi là pre-authenticated.

### Bài H — đặt `exceptionIfHeaderMissing=false` có luôn an toàn?

**Đáp:** Không. Nó chỉ cho phép filter tiếp tục khi thiếu header; mọi protected route vẫn phải yêu cầu Authentication, không có permissive fallback hoặc stateful session cũ. Kiểm chain và status thực tế bằng tests.

## 24. Checklist QA khi bàn giao

- [ ] Gateway đã xác thực người dùng theo protocol và MFA/assurance policy đúng.
- [ ] Proxy strip/overwrite **mọi** identity headers do client gửi.
- [ ] Spring backend không có direct/untrusted ingress, NodePort hoặc listener bypass.
- [ ] Gateway→backend có network isolation và service identity/mTLS phù hợp.
- [ ] `RequestHeaderAuthenticationFilter` chỉ đọc header đã chứng thực qua trust contract.
- [ ] `PreAuthenticatedAuthenticationProvider` tải local UserDetails/authorities.
- [ ] Không dùng raw group/role header để cấp ROLE_ADMIN.
- [ ] Stable subject và issuer namespace được ánh xạ chính xác tới local user.
- [ ] Disabled/unknown users bị deny; JIT provisioning có policy riêng nếu bật.
- [ ] Tenant/object-level authorization được kiểm ở từng nghiệp vụ.
- [ ] SecurityFilterChain cho proxy-only paths được phân tách với bearer/API/OIDC flows.
- [ ] Thiếu header, gateway session fail hoặc auth provider fail đều fail closed.
- [ ] `continueFilterChainOnUnsuccessfulAuthentication` và missing-header behavior được test.
- [ ] Session stateless/stateful, logout và identity switch đã được thiết kế/test.
- [ ] Reverse proxy `Forwarded`/`X-Forwarded-*` không dùng làm bằng chứng user identity.
- [ ] Duplicate/ambiguous header values và header-size limits được test.
- [ ] MFA/step-up claims được kiểm theo trusted assurance/freshness contract.
- [ ] Logs/metrics không chứa raw token/cookie/PII nhưng đủ correlation/audit.
- [ ] Không có auth bypass do health/debug/alternate ingress hoặc proxy config drift.
- [ ] Integration tests bao gồm spoofed admin header và direct backend denial.
- [ ] Cơ chế mTLS/secret/identity assertion rotation có owner và rollback.
- [ ] Spring Security/Boot/Jakarta Servlet version và filter order đã được kiểm.

## 25. Tài liệu chính thức tham khảo

1. [Spring Security — Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html): khái niệm pre-auth, principal, authorities và framework classes.
2. [Spring Security — RequestHeaderAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html): mặc định `SM_USER`, cách đọc header, cảnh báo spoofing và missing header.
3. [Spring Security — AbstractPreAuthenticatedProcessingFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html): auth lifecycle, principal change/session options và fallback.
4. [Spring Security — PreAuthenticatedAuthenticationProvider Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html): provider lấy UserDetails và authorities.
5. [Spring Security — UserDetailsByNameServiceWrapper Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsByNameServiceWrapper.html): chuyển ordinary UserDetailsService thành AuthenticationUserDetailsService.
6. [Spring Security — PreAuthenticatedGrantedAuthoritiesUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedGrantedAuthoritiesUserDetailsService.html): authorities từ trusted GrantedAuthoritiesContainer.
7. [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, SecurityContext, nhiều security chains và request matchers.
8. [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext persistence, session policies và logout.
9. [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validate bearer access token thay vì tin raw subject header khi mô hình yêu cầu.
10. [Spring Boot — How-to: Embedded Web Servers and Forwarded Headers](https://docs.spring.io/spring-boot/how-to/webserver.html): forwarded headers strategy và reverse proxy considerations.
11. [OWASP — HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): headers thuộc về những trust contexts khác nhau, tránh header security confusion.
12. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): reauthentication, session/context và threat controls.
13. [MDN — X-Forwarded-For Security Considerations](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For): header source/trust boundaries và spoofing.
14. [Keycloak — Configuring Reverse Proxy](https://www.keycloak.org/server/reverseproxy): documented forwarded-header rewriting/spoof risks (tham khảo trust-boundary nguyên lý, không phải hướng dẫn thay Spring).

**Ghi nhớ:** trong pre-authentication, **proxy/IdP xác thực user; Spring vẫn xác thực tính đáng tin của kênh/nguồn identity (qua hạ tầng hoặc verifier), tải principal và authorities rồi phân quyền**. `RequestHeaderAuthenticationFilter` chỉ là adapter; **header không tự có giá trị xác thực**. Chỉ một đường direct-backend hoặc một lỗi proxy không strip header có thể biến SSO tập trung thành đăng nhập giả mạo. Hãy kiểm trust boundary, session lifecycle, local roles và negative tests trước khi coi tích hợp proxy SSO hoàn thành.