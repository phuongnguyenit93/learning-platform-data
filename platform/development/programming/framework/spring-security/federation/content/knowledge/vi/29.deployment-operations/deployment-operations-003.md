# Quản lý session, AuthnRequest và ánh xạ đăng xuất trong cụm nhiều nút

> **Module:** Spring Security – federation · **Nhóm:** Triển khai và vận hành. Bài Knowledge tập trung vào vận hành SAML 2.0 Service Provider (SP) Java/Spring Security khi một ứng dụng chạy **nhiều JVM/pods/nodes** sau load balancer. Ba trạng thái phải được quản lý riêng nhưng nhất quán: **(1) HttpSession / Spring SecurityContext của trình duyệt; (2) AuthnRequest đang chờ SAMLResponse và dữ liệu correlation; (3) LogoutRequest đang chờ LogoutResponse cùng ánh xạ từ danh tính/SessionIndex của IdP sang các local sessions cần thu hồi**. Nội dung bao gồm Redis/Spring Session, browser cookies/SameSite, login CSRF, SAML Single Logout (SLO), replay protection, tên public ACS/SLO sau proxy, failover/rolling deploy, quyền quản trị secret và kiểm thử chaos. Ví dụ Java 17 ở cuối chạy độc lập nhưng **chỉ mô phỏng trạng thái**, không triển khai bộ xác minh chữ ký SAML thật. Tên miền, định danh và endpoint trong bài đều là giả lập.

## 1. Một lỗi production điển hình: request qua node A, callback tới node B

Giả sử ứng dụng báo cáo chạy ba pods `sp-a`, `sp-b`, `sp-c` dưới public URL `https://reports.example.org`. Tại thời điểm bắt đầu đăng nhập:

```text
Browser                    Ingress / LB                  SAML SP Cluster
   |                           |                                |
   | GET /saml2/authenticate/corp                            |
   |-------------------------->|---------------------> sp-a     |
   |                           |                      creates  |
   |                           |                 AuthnRequest R |
   |                           |                 saves in A's   |
   |                           |                 local session  |
   |<--------------------------|<--------------------- redirect |
   |                           |                                |
   | Browser visits IdP; IdP authenticates and sends Response   |
   |                           |                                |
   | POST /login/saml2/sso/corp with InResponseTo=R              |
   |-------------------------->|---------------------> sp-b     |
   |                           |                      tries to  |
   |                           |                      load R    |
   |                           |                 R not in B's   |
   |                           |                 local session  |
   |<--------------------------|<-------------------- SSO error |
```

Chữ ký IdP có thể hợp lệ, clocks chính xác, nhưng Spring Security không tìm được `AuthnRequest` cần để đối chiếu `InResponseTo` và `RelayState`. Thay đổi backend giữa hai HTTP requests là bình thường; hệ thống thiết kế đúng không được phụ thuộc vào bộ nhớ riêng của node A.

Một lỗi khác: user có hai browser sessions `S1` trên node A, `S2` trên node C. IdP gửi `LogoutRequest` chứa `SessionIndex=IX-123` đến node B. Nếu handler chỉ gọi `request.getSession(false).invalidate()` thì có thể **không hủy S1/S2**, vì SLO callback từ IdP có thể đến **không kèm cookie browser**. Khi app phản hồi `LogoutResponse Success` trong khi sessions còn active, SLO tạo cảm giác hoàn tất nhưng người dùng vẫn truy cập dữ liệu.

**Mục tiêu bài học:** Giữ được state/correlation qua nhiều nodes **mà không bỏ binding với trình duyệt**; logout đúng tập sessions và chỉ khi `LogoutRequest` đã được tin cậy và kiểm tra đủ profile.

## 2. Bốn vòng đời không được nhập làm một

| Đối tượng | Khóa nhận diện chính | Tạo ở đâu? | Dùng khi nào? | Kết thúc khi nào? |
| --- | --- | --- | --- | --- |
| **Browser HttpSession** | Random server-generated session ID qua cookie `SESSION`/`JSESSIONID` | Trước/sau login ở SP | Session authentication và app state | Timeout, local logout, revocation, user disable |
| **Pending AuthnRequest** | SAML request ID + unguessable `RelayState` + browser-flow binding | SP khởi tạo login | Đối chiếu SAMLResponse `InResponseTo` | One-time consume, TTL, cancel/expiry |
| **Pending RP LogoutRequest** | SAML LogoutRequest ID, optional RelayState + browser/logout transaction binding | SP khởi tạo SLO | Kiểm `LogoutResponse@InResponseTo` và kết quả | One-time consume, TTL, failure/timeout |
| **SAML session association** | Trusted IdP registration + NameID context + `SessionIndex` → local session IDs | Sau khi xác thực assertion | IdP-initiated SLO/targeted revocation | Local session expiry, unlink, logout, deprovision |

**Thứ năm:** `SecurityContext` chứa authenticated principal/authorities, thường được giữ trong HttpSession hoặc một repository phù hợp. Nó là **trạng thái sau xác thực**, không thay pending AuthnRequest hay bảng chỉ mục logout.

### 2.1. Những định danh không thể dùng thay nhau

- **Browser session ID** là bí mật (bearer session credential) do ứng dụng quản lý, **không phải** SAML `SessionIndex`.
- **SAML SessionIndex** xuất hiện trong `AuthnStatement` và `LogoutRequest`, do IdP phát; không phải local Redis session ID.
- **AuthnRequest ID** là ID của request SP gửi đi; `Response@InResponseTo` tham chiếu ID này.
- **LogoutRequest ID** là ID của yêu cầu SLO; `LogoutResponse@InResponseTo` tham chiếu ID đó.
- **RelayState** là opaque state truyền qua browser, có thể dùng làm correlation hint. Không coi giá trị do browser gửi là bằng chứng sở hữu HttpSession.
- **NameID** chỉ có ý nghĩa với trusted IdP, format và qualifiers của nó; có thể là transient hoặc persistent theo IdP profile.
- **Registration ID / Entity ID** ràng buộc một SP integration tới IdP cụ thể; không trộn sessions giữa các IdPs hoặc tenants.

### 2.2. Các tính chất phải bảo toàn

1. **Confidentiality:** session ID, auth tokens, SAML assertions, credentials và mappings không xuất hiện trong logs.
2. **Integrity:** chỉ principal đã xác minh từ IdP registered mới được tạo mapping.
3. **Correct association:** callback không được nối vào browser khác hoặc request khác.
4. **One-time use:** AuthnRequest, LogoutRequest và replay-sensitive response IDs không bị chấp nhận nhiều lần.
5. **Bounded lifetime:** mọi pending request và mapping có TTL/cleanup; không phải cache vô hạn.
6. **Multi-node visibility:** node B đọc được state đúng do node A tạo.
7. **Atomicity:** consume state + create/revoke session phải tránh races.
8. **Revocation completeness:** SLO chỉ trả Success khi hành động thuộc trách nhiệm SP đã thực hiện đúng policy.
9. **Failure behavior:** cache/session store mất thì fail closed cho chức năng phụ thuộc vào nó, không bỏ `InResponseTo` để “cứu” SSO.
10. **Isolation:** trusted issuer, tenant, NameID format, SessionIndex và browser session không bị lẫn giữa RPs.

## 3. Tổng thể kiến trúc khuyến nghị

```text
                          Internet / Browser
                                 |
                                 v
                 TLS Ingress / Reverse Proxy
                 canonical https://reports.example.org
                                 |
                 +---------------+---------------+
                 |               |               |
               sp-a            sp-b            sp-c
           Spring Boot      Spring Boot      Spring Boot
           Security SAML2   Security SAML2   Security SAML2
                 |               |               |
                 +---------------+---------------+
                                 |
                 Centralized, protected state stores
                 +-------------------------------+
                 | Spring Session Redis / DB     |
                 |   HTTP session + SecurityCtx  |
                 |   pending AuthnRequest        |
                 |   pending LogoutRequest       |
                 +-------------------------------+
                                 |
                 +-------------------------------+
                 | SAML application indexes      |
                 |   (IdP, NameID, SessionIndex) |
                 |          -> sessionId set     |
                 |   sessionId -> association    |
                 |   replay IDs / completed SLO  |
                 +-------------------------------+
                                 |
                        SAML IdP / metadata
```

**Lưu ý:** bảng application indexes là **thiết kế cần chủ động triển khai nếu muốn logout nhiều sessions theo SessionIndex**; không tự xuất hiện chỉ vì bật Spring Session Redis. Thư viện Spring Security SAML2 có chức năng SLO, nhưng khả năng định vị và hủy **mọi** sessions ở nhiều thiết bị/nodes phải được **kiểm thử thực tế** và có thể cần custom validated mapping/revocation.

### 3.1. Sticky sessions không tương đương distributed state

Load balancer có thể dùng affinity để browser quay lại node A. Nhưng:
- Node A restart/evicted khi callback về ⇒ request mapping mất.
- Callback cross-site có thể mất cookie affinity.
- Scale in, failover, rolling upgrade đổi node.
- IdP-initiated SLO có thể không có affinity cookie.
- Session trên thiết bị khác nằm trên node khác, không hủy hết bằng current browser session.

Sticky sessions là **optimization/temporary mitigation**, không phải bảo đảm SAML correlation và global logout. Với yêu cầu HA/SLO đầy đủ, cần shared state hoặc thiết kế stateless **có security binding tương đương** và distributed revocation.

### 3.2. Dùng riêng hay chung Redis?

Một cluster Redis có thể lưu Spring Session và domain SAML indexes với **namespaces và permissions tách biệt**. Không cần một Redis riêng cho mỗi loại state, nhưng cần phân quyền least-privilege, TTL, replica/failover, eviction policy, monitoring và redaction. Không dùng Redis `KEYS *` để “xóa những phiên lỗi” trong production.

## 4. SP-initiated SSO: vòng đời AuthnRequest trong cụm

### 4.1. Trình tự bình thường

1. Browser tới `/saml2/authenticate/corp`.
2. `Saml2WebSsoAuthenticationRequestFilter` resolve `RelyingPartyRegistration` trusted.
3. SP tạo `samlp:AuthnRequest` có **ID duy nhất khó đoán**, `IssueInstant`, destination và ACS information.
4. `Saml2AuthenticationRequestRepository` lưu `AbstractSaml2AuthenticationRequest` cùng correlation information.
5. Browser chuyển tới IdP bằng Redirect/POST binding kèm `SAMLRequest`/`RelayState` theo cấu hình.
6. IdP xác thực và phát `SAMLResponse` có `InResponseTo` tham chiếu AuthnRequest ID.
7. Browser POST response đến ACS `/login/saml2/sso/corp`.
8. `Saml2WebSsoAuthenticationFilter` / `Saml2AuthenticationTokenConverter` đọc pending AuthnRequest từ repository.
9. OpenSAML provider kiểm chữ ký trusted IdP, issuer, audience, recipient/destination, Conditions, bearer SubjectConfirmation, `InResponseTo`, replay và profile checks.
10. Khi success, pending request được dùng/consume đúng policy; tạo authenticated SecurityContext và local session.
11. Mapping SAML identity/sessionIndex→new session ID được ghi sau khi session fixation protection hoàn tất.
12. Lúc thất bại, không tạo authenticated SecurityContext hay link logout index.

Các API/filters kể trên là thành phần Spring Security Servlet SAML2; nếu dùng Spring Security 6.x/7.x cần đối chiếu release/Javadoc cho từng method.

### 4.2. Spring default: request trong HttpSession

Tài liệu Spring Security xác nhận mặc định dùng `HttpSessionSaml2AuthenticationRequestRepository`. Nếu HttpSession là **Tomcat in-memory per node**, node B không thể đọc AuthnRequest lưu ở node A. Nhưng nếu Spring Session **thay HttpSession bằng Redis-backed session** đúng cách, request state có thể theo cookie và được chia sẻ qua nodes.

```text
Browser cookie: SESSION = opaque-123
   |
   +--> sp-a stores AuthnRequest R in HttpSession
   |      Spring Session persists opaque-123 -> R in Redis
   |
   +--> IdP completes authentication
   |
   +--> sp-b receives browser cookie opaque-123
          Spring Session resolves opaque-123 from Redis
          AuthnRequest R found, then validates InResponseTo
```

Đây là phương án thường ưu tiên vì giữ **browser-session binding** trong request repository, không chỉ lưu map global theo ID do người gửi tự khai.

### 4.3. Spring Boot + Redis-backed HttpSession

Ví dụ dependencies với Spring Boot dependency management:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
  </dependency>
</dependencies>
```

Ví dụ Spring Boot configuration fragment:

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: none

spring:
  session:
    redis:
      namespace: reports:sessions
      flush-mode: on_save
  data:
    redis:
      host: redis.internal.example
      port: 6379
      ssl:
        enabled: true
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: https://idp.example.org/saml/metadata
```

**Đây là fragment vận hành, không phải cấu hình sẵn dùng cho mọi phiên bản.** Cần cấu hình credentials Redis từ secret manager, truststore TLS cho Redis/IdP, trusted metadata/signing credentials, network policy, complete RelyingPartyRegistration, service-provider entityID/ACS/SLO, CSRF/session policies. Kiểm tra tên Spring Boot properties và dependency ở phiên bản cụ thể. `same-site: none` chỉ nên chọn sau khi xác minh browser callback binding và privacy policy; nó yêu cầu cookie `Secure` và không thay CSRF protection.

Spring Session thay thế `HttpSession` bằng một repository backed bởi Redis thông qua `springSessionRepositoryFilter`. Nó không tự biến **mọi** custom singleton map, local Caffeine cache hay ứng dụng logout index thành distributed state.

### 4.4. Validate session cookie qua real browser

Spring Session thường dùng cookie `SESSION`; các cấu hình servlet/session khác có thể sử dụng `JSESSIONID`. **Không hardcode** tên cookie vào business logic. Dùng Network tab trong **môi trường test**, kiểm cookie được gửi khi browser từ IdP POST về ACS, kể cả các trường hợp:

- Top-level cross-site POST từ IdP.
- Browser privacy restrictions, third-party-cookie policy.
- SameSite=Lax, Strict và None.
- Cookie `Secure`/`HttpOnly`/Domain/Path.
- Cross-subdomain vs cross-origin deployment.
- Existing browser session vs new session.
- HTTPS offload tại ingress và public Host/Proto.

Với cross-site POST, SameSite=Lax **thường không gửi cookie** trong bối cảnh đó; default browser có thể có nuance. SameSite=Strict càng dễ mất cookie khi trở về từ IdP. SameSite=None;Secure hỗ trợ use case cross-site nhưng có rủi ro CSRF khác, vì vậy phải giữ SAML response correlation, state và browser/session safeguards.

## 5. Không “sửa” mất AuthnRequest bằng cách bỏ correlation

### 5.1. Một phương án nguy hiểm

```text
Response arrives on node B
  AuthnRequest R not found
      |
      v
Developer disables InResponseTo check
  / accepts IdP-initiated style regardless of flow
      |
      v
Attacker can exploit unsolicited assertions / login CSRF
```

**Sai nguyên tắc:** SAMLResponse có chữ ký hợp lệ vẫn có thể là response mà **browser này chưa từng yêu cầu**. Khi bỏ kiểm pending request, attacker có thể cố đưa một assertion từ account của attacker vào session victim hoặc thực hiện unsolicited login nếu những controls khác yếu.

### 5.2. Chỉ lookup bằng RelayState cũng có trade-off

Spring Security hỗ trợ `CacheSaml2AuthenticationRequestRepository`, giúp cache AuthnRequest bằng RelayState thay session trong một số triển khai. Tài liệu Spring Security **cảnh báo rõ**: lookup bởi `RelayState` hoặc `InResponseTo` mà không có browser-session binding có thể đánh mất một lớp chống login fixation/CSRF. Kẻ tấn công có thể tạo một SAML flow hợp lệ rồi ép browser victim nhận callback từ flow ấy.

Nếu kiến trúc dùng distributed AuthnRequest cache ngoài HttpSession:

- RelayState phải là giá trị ngẫu nhiên mạnh, opaque, không chứa PII, redirect URL tùy ý hoặc session ID.
- Tập state ràng buộc với **browser/login transaction** bằng session cookie hoặc mechanism độc lập có assurance tương đương.
- Correlate request ID, trusted registration/issuer, destination, browser binding, TTL và one-time usage.
- Không load request từ bất kỳ `RelayState` do browser tự khai mà bỏ browser binding rồi tạo authenticated session.
- TTL ngắn, consume atomic (GET+DELETE không atomic là chưa đủ khi có race).
- Kiểm open redirect trên target URL sau login; không trust `RelayState` như absolute redirect URI.
- Khi cookie bị browser chặn, xem xét thay đổi cookie deployment/flow an toàn; không chọn cache-only làm “fix magic”.

### 5.3. Chỉ một AuthnRequest hay nhiều pending requests mỗi session?

User có thể mở hai tabs, hai logins cùng lúc hoặc đổi registration. Nếu repository/model chỉ giữ một pending AuthnRequest per session, flow thứ hai có thể ghi đè flow thứ nhất. Cần test actual Spring Security release và repository behavior. Nếu muốn hỗ trợ nhiều flows, dùng server-side map theo request ID **gắn cùng browser-session context**, giới hạn số pending flows/TTL và atomic consume; không mở vô hạn.

Không lấy request ID từ URL làm phép xác thực; nó chỉ là **correlation identifier** trong một thông điệp đã validate. Một IdP-initiated SSO flow không có pending request là profile riêng cần whitelist và replay/recipient controls, không dùng để bypass SP-initiated checks.

## 6. RelayState, InResponseTo và session fixation

### 6.1. Các ràng buộc cần kiểm

Với request `R`:

```text
Pending:
  expectedRegistration = corp
  expectedIdP          = https://idp.example.org
  requestId            = _req-7432
  relayState           = opaque-strong-random
  originalBrowserFlow  = bound-to-session-S0
  expiresAt            = T+3min

Inbound Response:
  registration         = corp
  issuer               = expected trusted IdP
  inResponseTo         = _req-7432
  relayState           = opaque-strong-random
  browser session      = S0
  signature/audience/time/replay validated
```

**Một match `InResponseTo` không thay việc validate signature, issuer, audience, bearer Recipient và Conditions.** Ngược lại, signature hợp lệ không thay browser-flow correlation.

### 6.2. Session ID đổi sau đăng nhập

Spring Security thường có session fixation defense thay session ID khi user đăng nhập (Servlet `changeSessionId` hoặc strategy khác). Từ đó:

```text
Before auth:
  SESSION = S0
  Pending AuthnRequest refers to flow S0

After successful auth:
  SESSION = S1
  SAML session index mapping MUST point to S1
  and should no longer point to obsolete S0
```

**Không ghi SAML logout index trước khi session ID mới được chốt rồi giữ forever S0.** Nếu có events `HttpSessionIdListener` hoặc `SessionFixationProtectionEvent`, dùng để update mapping atomically và test cả case node change. Không tắt session fixation protection chỉ vì session index mapping chưa theo kịp.

### 6.3. Invalid cookies, session expiry giữa flow

Nếu browser mất `SESSION` khi callback hoặc session đã hết TTL, SP có thể không tìm pending AuthnRequest. Theo strict SP-initiated flow, **reject an toàn và bắt đầu login mới**, không tự tin một `RelayState` còn tồn tại ở shared cache như bằng chứng user sở hữu session ban đầu. Nên tránh auto-retry loop vô hạn; UI có thể gợi ý login lại, logs chỉ giữ safe correlation reason codes.

### 6.4. Race và one-time consume

Hai POST của cùng SAMLResponse vào node B/C có thể xảy ra gần như đồng thời do reload, retry proxy hoặc tấn công replay. Repository phải bảo đảm chỉ một transaction consume AuthnRequest. Replay detection cho signed Response/Assertion ID là một lớp độc lập; **không chỉ dựa vào xóa pending state** nếu IdP-initiated flow có thể được cho phép.

Trong Redis, dùng Lua script/transaction hoặc thao tác atomic phù hợp để kiểm expected value + remove đúng một lần. Không dùng `GET` rồi `DEL` không kiểm concurrency để mô phỏng one-time guarantee. Eventual consistency/replica reads có thể gây duplicated acceptance.

## 7. Spring Security SAML2: các thành phần và chỗ thay repository

### 7.1. AuthnRequest repository

Các thành phần từ tài liệu Spring Security:

| Component | Vai trò |
| --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | Sinh AuthnRequest trước khi redirect IdP |
| `Saml2AuthenticationRequestRepository` | Lưu và đọc pending `AbstractSaml2AuthenticationRequest` |
| `HttpSessionSaml2AuthenticationRequestRepository` | Mặc định: lưu request vào HttpSession |
| `CacheSaml2AuthenticationRequestRepository` | Repository theo RelayState/cache trong versions hỗ trợ, có caveat browser binding |
| `Saml2WebSsoAuthenticationFilter` | Xử lý ACS SAMLResponse |
| `Saml2AuthenticationTokenConverter` | Resolve registration, load pending request context |
| `OpenSaml5AuthenticationProvider` | Verify signed SAML/protocol theo release hiện hành |
| `RelyingPartyRegistrationRepository` | Trusted IdP/SP entityID, keys, endpoints |

Ví dụ bean theo Spring Security version có `CacheSaml2AuthenticationRequestRepository`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.saml2.provider.service.web
        .Saml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web
        .CacheSaml2AuthenticationRequestRepository;

@Bean
Saml2AuthenticationRequestRepository<?> authnRequestRepository() {
    // Fragment: ensure browser/session binding policy before choosing this!
    return new CacheSaml2AuthenticationRequestRepository();
}
```

**Cảnh báo:** đây là Spring configuration fragment, không phải chương trình biên dịch độc lập. Class/method names có thể khác theo Spring Security 6.x/7.x; phải đối chiếu docs đúng version. **Không coi factory mặc định của cache repo là cấu hình Redis cluster và browser binding đã được chứng minh.** Nếu dùng Spring Session Redis và HttpSession default, thường **không cần** chuyển sang RelayState cache.

### 7.2. Một SecurityFilterChain tối thiểu về ý tưởng

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .saml2Login(saml -> {})
        .saml2Logout(saml -> {})
        .build();
}
```

Fragment này minh họa **bật SAML login và SLO**, chưa bao gồm complete SAML registration, trusted IdP signing certs, private signing keys cho logout, Spring Session Redis, SLO SessionIndex index, CSRF policies và authorization thực tế. `saml2Logout` chỉ hoạt động đúng khi IdP metadata/registration có SingleLogoutService và SP signing credentials cần thiết. Không gọi nó là cấu hình HA/SLO đầy đủ.

### 7.3. Đừng bỏ trusted verification để chẩn đoán cluster

Khi lỗi `InResponseTo` sau deploy, phải xem session repository/cookie/Redis first. Không giải quyết bằng cách:
- Tắt signature verification.
- Chấp nhận `Response` của mọi IdP.
- Đưa untrusted certificate từ `KeyInfo` thành verification credential.
- Bỏ `InResponseTo`/Audience/Recipient/replay.
- Chấp nhận RelayState từ browser làm trust anchor.
- Cho phép callback tự chọn issuer/registration/JWKS URL.

Đó là các security controls riêng, cần giữ nguyên dù một node đang không thể đọc state.

## 8. Single Logout trong SAML: hai hướng độc lập

### 8.1. RP-initiated logout

Ví dụ user nhấn logout khi đang ở SP:

```text
Browser -> SP POST /logout (CSRF protected)
      |
      v
Saml2RelyingPartyInitiatedLogoutSuccessHandler
      |
      +-- invalidate local session / clear SecurityContext
      +-- resolve trusted IdP SLO endpoint
      +-- create/sign LogoutRequest with ID L1
      +-- persist pending LogoutRequest correlation
      |
      v
Browser / IdP receives SAML LogoutRequest
      |
      v
IdP returns signed LogoutResponse InResponseTo=L1
      |
      v
SP verifies signature, status, destination, issuer,
  InResponseTo & RelayState against L1
      |
      v
Complete / show logout result
```

Theo docs, Spring Security local logout handlers có thể invalidate session **trước** khi xử lý outbound SAML LogoutRequest. Thư viện có `Saml2LogoutRequestRepository` để giữ `Saml2LogoutRequest` nhằm đối chiếu khi IdP trả `LogoutResponse`. **Nếu thiết kế custom repository**, phải bảo đảm record vẫn tồn tại và có binding phù hợp **sau local session invalidation**, hoặc dùng semantics chuẩn đã kiểm thử; không giả định cứ lưu vào old session rồi xóa session là correlation sẽ còn.

### 8.2. IdP-initiated logout (AP-initiated)

IdP gửi `samlp:LogoutRequest` cho SP tại endpoint ví dụ `/logout/saml2/slo`:

```xml
<samlp:LogoutRequest
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="_logout-request-18"
  Version="2.0"
  IssueInstant="2026-11-07T10:00:00Z"
  Destination="https://reports.example.org/logout/saml2/slo">

  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    opaque-person-9
  </saml:NameID>
  <samlp:SessionIndex>IX-123</samlp:SessionIndex>
</samlp:LogoutRequest>
```

Đây là **XML minh họa, chưa có chữ ký**, không dùng làm production/logout proof. Thông điệp thật phải được xử lý theo binding/signature/profile và trusted IdP metadata; Spring Security có `Saml2LogoutRequestFilter` và `Saml2LogoutRequestValidator`. Sau khi verify, SP tìm local sessions tương ứng `NameID` + `SessionIndex` và hủy theo policy, rồi gửi `samlp:LogoutResponse` có `InResponseTo` bằng ID yêu cầu.

**Không** đọc raw `SessionIndex` rồi xóa sessions ngay. Chỉ truy vấn mapping sau khi signature, issuer, destination, audience/recipient theo profile, time và replay đã được xác minh. SLO callback có thể không có browser session cookie.

### 8.3. Spring Security components

| Component | Công dụng |
| --- | --- |
| `Saml2LogoutRequestFilter` | Nhận/validate LogoutRequest từ IdP |
| `Saml2LogoutRequestValidator` | Verify request theo SAML profile/trusted registration |
| `Saml2LogoutResponseResolver` | Tạo/sign LogoutResponse khi SP xử lý IdP request |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Khởi tạo RP SLO sau local logout |
| `Saml2LogoutRequestResolver` | Tạo outbound SAML LogoutRequest |
| `Saml2LogoutRequestRepository` | Lưu pending RP LogoutRequest để match inbound LogoutResponse |
| `HttpSessionLogoutRequestRepository` | Lưu pending request trong HttpSession theo implementation/docs |
| `Saml2LogoutResponseFilter` | Nhận LogoutResponse của IdP |
| `Saml2LogoutResponseValidator` | Verify response và InResponseTo/status |
| `RelyingPartyRegistration` | Trusted IdP SLO endpoint, verification/signing credentials |

Trong Servlet SAML2, docs mặc định dùng endpoint `POST /logout` cho RP-initiated SLO và `/logout/saml2/slo` cho IdP request/response, nhưng routes có thể custom. Đừng dùng đường endpoint từ SAML XML chưa verify để tự cấu hình trusted IdP.

## 9. Pending LogoutRequest: local session đã hủy nhưng correlation phải tồn tại

### 9.1. Hai vấn đề khác nhau

**Issue A:** SP đã xóa browser session, khi IdP gửi LogoutResponse có `InResponseTo=L1`, repository không tìm thấy `L1`. Điều này có thể xảy ra nếu custom state đặt sai nơi hoặc browser cookie không quay lại.

**Issue B:** SP tìm được một pending LogoutRequest từ cache global bằng `L1` nhưng không biết callback thuộc **trình duyệt/logout flow** nào, từ đó xử lý sai redirect/result/CSRF.

Cách khắc phục cần **transactional correlation** chứ không chỉ giữ một map theo request ID.

### 9.2. Pending record gợi ý

```text
LogoutTransaction {
  requestId:          _logout-L1
  registrationId:     corp
  expectedIssuer:     https://idp.example.org/saml
  expectedDestination:https://reports.example.org/logout/saml2/slo
  opaqueRelayState:   highEntropyRandom
  browserBinding:     independent short-lived transaction secret
  localAccountRef:    RP-internal opaque ID (optional; minimized)
  createdAt:          UTC
  expiresAt:          UTC + short approved TTL
  consumedAt:         absent
}
```

Không lưu private signing key trong pending record. Nếu đã invalidate HttpSession cũ, `browserBinding` phải dùng một control có lifecycle độc lập thích hợp hoặc state được bảo vệ phía server/cryptographically bound, không giả định một session cookie vừa xóa vẫn còn. Mỗi implement cần đánh giá UX/threat model để tránh login/logout CSRF, open redirect và leak information.

### 9.3. Custom repository extension

Docs Spring Security cho phép:

```java
http.saml2Logout(saml -> saml
    .logoutRequest(request -> request
        .logoutRequestRepository(
            myCustomLogoutRequestRepository)));
```

Fragment này cần `HttpSecurity` và bean `myCustomLogoutRequestRepository` kiểu `Saml2LogoutRequestRepository` được triển khai/đăng ký theo release. Repository phải hỗ trợ **load/save/remove** đúng contract mà filters mong đợi, TTL, signed issuer checks ở validator, one-time match và multi-node read. Chỉ thay repository **không** tự triển khai “IdP SessionIndex → mọi browser sessions”; đó là lớp khác.

### 9.4. Repeated LogoutResponse

IdP có thể retry cùng LogoutResponse hoặc attacker replay. Một record LogoutRequest đã được tiêu thụ không được dùng để approve response lần hai. Với concurrency, cần atomic compare-and-delete hoặc consumed marker. Khi timeout, xử lý pending record; **đừng tái tạo authenticated local session** chỉ vì SLO thất bại — local logout đã xảy ra.

### 9.5. SLO có thể thất bại một phần

RP-initiated SLO không đảm bảo IdP hay các RP khác đã logout thành công. IdP có thể không trả LogoutResponse, trả PartialLogout hoặc network fail. Local session đã bị hủy thì vẫn phải hủy; UI/audit nên phân biệt **local logout success**, **federated SLO pending/partial/failure**. Không báo “đã đăng xuất mọi ứng dụng” nếu không có protocol outcome và operational evidence.

## 10. Ánh xạ NameID/SessionIndex → local sessions

### 10.1. Vì sao Redis-backed HttpSession vẫn chưa đủ?

Spring Session Redis cho phép node nào cũng đọc session nếu có **session ID**. Nhưng IdP-initiated SLO thường chỉ có:

```text
Verified IdP entityID = https://idp.example.org/saml
Verified NameID        = opaque-person-9
Verified SessionIndex  = IX-123
SAML LogoutRequest ID  = _logout-X
```

Nó **không gửi Redis session ID** của app và có thể không gửi cookie. SP cần một **secondary index** từ trusted SAML identity/session identifiers đến các local sessions. Đây là dữ liệu application-specific cần lưu có kiểm soát.

### 10.2. Key của mapping không chỉ là SessionIndex

Đừng viết:

```text
index["IX-123"] -> sessionId
```

`SessionIndex` có thể trùng giữa IdPs/tenants hoặc từ hai SAML sessions khác nhau; và có thể một IdP dùng cùng SessionIndex cho nhiều app sessions. Key nên bao gồm:

```text
SamlSessionKey(
  rpRegistrationId,
  trustedIdpEntityId,
  nameIdFormat,
  nameQualifier,
  spNameQualifier,
  nameIdValue,
  sessionIndex
) -> Set<localHttpSessionIds>
```

Dùng exact IDP/NameID semantics đã được IdP contract xác nhận. Nếu không có stable NameID hoặc SessionIndex, policy phải định nghĩa rõ fallback. **Không** so email/username/substring làm key vì dễ logout nhầm user.

### 10.3. Một SessionIndex có thể ánh xạ nhiều local sessions

User có thể đăng nhập cùng một IdP SSO session trên:
- Browser A trên laptop.
- Browser B trong profile riêng.
- Tab/session khác của cùng browser theo ứng dụng.
- Mobile client dùng browser SAML front-channel nếu kiến trúc hỗ trợ.

Khi IdP gửi LogoutRequest chỉ rõ `SessionIndex=IX-123`, một implementation SLO đầy đủ có thể cần hủy **tất cả local session IDs tương ứng index này**, không chỉ request-scoped `HttpSession`. Ngược lại, không được hủy những sessions khác `IX-456` khi logout được target vào IX-123 trừ policy/profile cho phép phạm vi rộng hơn.

### 10.4. Hệ số association và reverse mapping

```text
Forward:
  key(corp, IdP-A, opaque-person-9, IX-123)
      -> {S1, S2}

Reverse:
  S1 -> key(corp, IdP-A, opaque-person-9, IX-123)
  S2 -> key(corp, IdP-A, opaque-person-9, IX-123)

After S1 expires:
  forward -> {S2}
  reverse[S1] removed

After verified IdP SLO for IX-123:
  revoke S2
  forward key removed
  reverse[S2] removed
```

Reverse index giúp cleanup khi session expired/renamed/invalidated. Nếu chỉ có forward set, các stale entries có thể kéo dài và làm tăng xung đột hoặc invalidate nhầm session IDs tái sử dụng (session IDs phải ngẫu nhiên không reuse).

### 10.5. Bảo mật key index

`NameID`, `SessionIndex` và session IDs là dữ liệu liên kết danh tính/session. Tránh raw PII trong Redis key names, metrics và logs. Có thể dùng **HMAC keyed index** với server-controlled secret:

```text
indexKey = HMAC-SHA256(
  index-secret,
  registration + issuer + NameID qualifiers
  + NameID + SessionIndex
)
```

Không dùng SHA-256(email) public; HMAC keyed giúp hạn chế dictionary attacks. Tuy nhiên HMAC result vẫn có thể là pseudonymous personal data. Key lifecycle/migration phải được tính khi rotate secret; không để mất khả năng logout các sessions cũ vì đổi HMAC secret đột ngột.

### 10.6. No SessionIndex và multiple SessionIndex

SAML `LogoutRequest` có thể chứa nhiều `SessionIndex` hoặc không có. Khi không có index, yêu cầu có thể mang ý nghĩa rộng hơn theo SAML profile/IdP contract: logout mọi sessions cho NameID từ issuer đó, hoặc cần chính sách xử lý khác. Để tránh mass logout:

1. Verify trusted IdP signature/issuer/NameID context.
2. Xác định semantics của SLO profile đang dùng.
3. Nếu index có mặt, target **chỉ các indexes hợp lệ được khai báo**.
4. Nếu không có index, chỉ thực hiện broad logout khi contract/security policy cho phép; nếu không, reject/return appropriate status.
5. Không bao giờ dùng raw browser-supplied email để suy ra “logout all”.
6. Giới hạn tối đa indexes/sessions để phòng abuse và stale records; báo partial failure khi không thực hiện đủ.

### 10.7. SessionIndex có thể không sẵn có

Spring Security `Saml2AuthenticatedPrincipal` cung cấp NameID/attributes; mức độ exposed `SessionIndex` trực tiếp có thể phụ thuộc release/provider. Nếu cần lưu SessionIndex, phải trích từ **Assertion/AuthnStatement đã được OpenSAML verify**, qua authentication converter/hook sau validation; không parse raw `SAMLResponse` bằng regex/DOM rồi tin một `SessionIndex` nằm trong unsigned subtree.

Khi không có SessionIndex ở assertion, không tự tạo một giá trị tùy ý và coi như IdP SessionIndex. Phải dùng fallback/logout policy riêng.

## 11. Spring Session indexing và sự khác biệt với SAML SessionIndex

Spring Session cung cấp `FindByIndexNameSessionRepository` và method `findByPrincipalName(...)` nếu repository/version hỗ trợ. Nó giúp tra **HTTP sessions theo Spring principal name** và có thể dùng cho toàn-account revocation.

Nhưng **principal name index ≠ SAML SessionIndex**. Nếu một user có hai IdP sessions khác nhau:

```text
principal = "opaque-user-9"
SessionIndex X -> S1, S2
SessionIndex Y -> S3
```

`findByPrincipalName("opaque-user-9")` có thể trả **S1,S2,S3** (nếu được index), không đủ để target chỉ X. Nếu IdP SLO chỉ yêu cầu X mà bạn xóa cả 3, đó là **over-logout**; nếu xóa chỉ một session từ request cookie, đó là **under-logout**.

### 11.1. Java fragment tìm sessions theo principal

```java
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

// Fragment: repository là Spring Session repository có indexing.
Map<String, ? extends Session> sessions =
        repository.findByPrincipalName(
            "trusted-and-normalized-local-principal");
```

Không dùng code này tự động cho mọi IdP SLO. Cần verify principal index được tạo và duy trì đúng; docs nói việc populate có thể là trách nhiệm của app và implementation khác nhau. Với SAML targeted logout, dùng association có **NameID/SessionIndex** và chỉ hủy matched HTTP session IDs.

### 11.2. SessionRepository.deleteById và cảnh báo

```java
// Fragment: đã verify SAML LogoutRequest và tìm các IDs
// được phép revoke cho specific IdP/NameID/SessionIndex.
for (String localSessionId : verifiedTargets) {
    springSessionRepository.deleteById(localSessionId);
}
```

Đây là operation nguy hiểm nếu `verifiedTargets` đến từ token chưa verify. Ngay cả khi đã verify, cần kiểm target session đang tồn tại và gắn với đúng identity/index, xử lý concurrent session rotation, error/retry/idempotency và audit. Trong distributed caches, deletion propagation có latency; security-sensitive endpoints có thể cần revocation marker/epoch check.

### 11.3. Session fixation và reverse index

Nếu session ID đổi `S0→S1` sau authentication, phải:
- Chuyển reverse index từ S0 sang S1.
- Update forward set xóa S0/thêm S1, atomically.
- Tránh delete nhầm S1 trong race với logout.
- Nếu đang dùng Spring Session principal index, xác minh index mới đã cập nhật.
- Test `changeSessionId`/`migrateSession` tùy servlet container/release.

Không nên lưu raw session ID trong một IdP-visible field như RelayState hay SAML SessionIndex. Mapping chỉ tồn tại phía SP.

## 12. Session/store TTL, eviction và cơ chế dọn dẹp

### 12.1. Các TTL không có cùng giá trị

| State | TTL vận hành cần chọn | Sau khi hết TTL |
| --- | --- | --- |
| AuthnRequest pending | Ngắn, đủ redirect/MFA với policy | Callback thiếu correlation bị reject |
| LogoutRequest pending | Ngắn nhưng đủ round-trip IdP SLO | Reject stale LogoutResponse, local logout vẫn xong |
| Authenticated HttpSession | Theo app session security policy | Session vô hiệu, indexes phải cleanup |
| SAML mapping key | Ít nhất theo active local session lifecycle, không vô hạn | Remove khi session ended; reaper cleanup |
| Replay ledger | Bao phủ toàn validity window/replay risk với skew | Không chấp nhận reused IDs trong thời hạn rủi ro |
| SSO SessionIndex material | Chỉ khi phục vụ logout/incident policy | Xóa khi không còn active references |
| Audit events | Theo retention policy riêng | Purge/aggregate, không giữ raw PII |

**Đừng dùng “mọi thứ 30 phút”** rồi để pending AuthnRequests tồn tại cả nửa giờ hoặc SessionIndex mapping hết sau 3 phút khi HttpSession còn 8 giờ. Không dùng một giá trị cố định cho mọi trường hợp; đồng bộ với IdP assertion TTL, SLO timing và business policy.

### 12.2. Cleanup qua events và reaper

- Khi logout local, xóa reverse entry và forward set membership.
- Khi session timeout, nghe session destroyed/expired events nếu backend phát chúng đáng tin.
- Có một **reconciliation/reaper job** xử lý missed events, Redis failover và partial failures.
- Khi `changeSessionId`, chuyển associations.
- Khi IdP SLO invalidates nhiều sessions, delete sessions và index entries idempotently.
- Không giữ index membership cho session IDs không tồn tại.
- Xét TTL của forward set khi còn active members; không expire key sớm hơn session lâu nhất.
- Không phụ thuộc 100% Redis keyspace notifications làm security guarantee; các events có thể bị disable/mất hoặc delivered không tức thời.

### 12.3. Eviction và Redis failure

Nếu Redis bị eviction vì memory pressure, pending correlation có thể biến mất và login fail. Đây là **availability issue**, không phải lý do bỏ checks. Thiết kế Redis memory limit/eviction policy để hạn chế mất security state; monitor:
- evicted keys,
- pending request misses,
- session lookup latency,
- Redis replication lag,
- timeouts,
- connection saturation,
- stale SLO indexes,
- failed atomic operations.

Nếu Redis unavailable, ứng dụng nên **reject callbacks cần correlation** và fail safely, hiển thị retry message. Không fallback sang local in-memory request map trên một node mà không thiết kế security/consistency cho cluster.

## 13. Race conditions: login, logout, lock và expiry

### 13.1. Login callback đôi

```text
T1 sp-b reads pending AuthnRequest R
T2 sp-c reads same R
T1 verifies and creates session S1
T2 verifies and creates session S2

Unsafe result: same signed SAMLResponse accepted twice.

Expected:
  only one atomic consume of R succeeds,
  replay ledger rejects duplicate signed IDs,
  second request cannot create new authenticated session.
```

Atomic consume must be guarded by request ID, trusted registration and expected browser flow binding. A simple `GET` then `DEL` race is not enough.

### 13.2. Login và IdP SLO cùng lúc

```text
T1 login callback authenticated, prepares S1 mapping IX-X
T2 IdP LogoutRequest for IX-X arrives, revokes all known sessions
T1 commits S1 after logout -> user appears logged in again
```

To avoid a **resurrection race**, consider a short-lived revocation marker/generation for the (trusted IdP, NameID, SessionIndex) association. Login commit checks current generation or forced reauthentication policy before publishing S1. Logout increments generation atomically, invalidates existing sessions, and stale login commits are rejected or revalidated. This behavior is **application architecture**, not automatic Spring Session Redis feature.

### 13.3. Logout and session ID rotation

T1 creates authenticated session `S1`; T2 still sees old `S0`. If mapping update is non-atomic, SLO may revoke S0 only while S1 remains. Use transaction/Lua to update forward/reverse mapping in one logical operation or store stable local session entity with generation-aware ID mapping.

### 13.4. Repeated IdP LogoutRequest

SLO request ID `L1` replay must not revoke a new session created later for the same account. Maintain replay ledger keyed by verified IdP/LogoutRequest ID with TTL and processing status. For a duplicate request, return protocol-appropriate result or reject according to policy, but **do not reinterpret old L1 as fresh instruction to terminate future sessions**.

### 13.5. DB/Redis partial failure

If session deletion succeeds but index update fails, reaper should repair. If index update succeeds but delete fails, session may stay live: **do not respond unconditional Success** when security policy requires revocation. Use idempotent job/retry, metrics and documented SLO status semantics. For sensitive apps, a revocation epoch checked on each protected request can close the window even before physical deletion finishes.

## 14. Load balancer, cookies và public URL consistency

### 14.1. Public URLs phải trùng trên mọi nodes

Ví dụ IdP nhận AuthnRequest có:

```text
AssertionConsumerServiceURL:
  https://reports.example.org/login/saml2/sso/corp

SP entityID:
  https://reports.example.org/saml2/service-provider-metadata/corp

SingleLogoutService:
  https://reports.example.org/logout/saml2/slo
```

Không để sp-a tự advertise `http://10.1.1.11:8080/...`, sp-b `http://10.1.1.12:8080/...` vì proxy TLS termination hoặc forwarded-header misconfiguration. IdP sẽ ký/redirect đến endpoints không nhất quán và Spring `Destination`/`Recipient` validators có thể reject.

### 14.2. Forwarded headers

Spring Boot có `server.forward-headers-strategy` để xử lý headers của reverse proxy tùy deployment. Chỉ trust `X-Forwarded-Proto`/`X-Forwarded-Host`/`Forwarded` **từ ingress đã xác thực**, strip malicious client-supplied headers. Nếu app tự tin HTTP headers do internet user gửi, attacker có thể làm sai recipient, ACS URL và redirect checks.

### 14.3. Cookie Domain/Path

Nếu app public path `/reports` nhưng internal context path `/`, cookie path mismatch có thể khiến browser không gửi session cookie tới `/login/saml2/sso/corp`. Check actual browser request/cookie attributes, không nhìn mỗi server configuration. Cookies có thể đổi `SESSION` vs `JSESSIONID` sau Spring Session integration.

### 14.4. IdP callback không luôn có browser cookie

Đặc biệt IdP-initiated SLO có thể được gửi qua iframe/front-channel; browser privacy policies và SameSite rules có thể chặn cookie. **Đừng thiết kế IdP SLO dựa vào `request.getSession()`** để tìm tất cả users đang logged in. Validate IdP request rồi tra server-side SAML session index và revoke targeted sessions.

## 15. Chữ ký, chứng thư và metadata trong cluster

### 15.1. Mọi node phải dùng cùng trust model

- Cùng `RelyingPartyRegistration` (entityID, IdP entityID, ACS/SLO endpoints, bindings).
- Cùng trusted IdP signing verification keys, có controlled old+new overlap khi rollover.
- Cùng SP private signing key hoặc key-service để ký AuthnRequest/LogoutRequest theo registration, trừ khi profile hỗ trợ nhiều keys và metadata tương ứng.
- Cùng SP decryption credentials nếu encrypted assertions được dùng; không node nào giải mã được node khác không.
- Cùng accepted clock skew policy, replay semantics và authn request repository configuration.
- Version config có rollout/rollback plan, không để node A accept issuer B còn node C không.
- Secret keys và certificates nằm trong secret manager, không Git/image/log/exception.

### 15.2. Signing certificate rollover đồng thời với rolling deploy

Một request từ node A dùng SP signing key v1 nhưng callback được node B đang cấu hình chỉ v2 có thể gây verification/trust hoặc logout flow mismatch tùy IdP metadata và SP profile. Có overlap/vintage tagging rõ, kiểm signing credential versions trên mỗi node, và phối hợp IdP metadata publication. Không tự tin certificate trong SAMLResponse `KeyInfo` để “chữa” stale trusted keys.

### 15.3. IdP metadata refresh

Nếu mỗi node refresh metadata độc lập và không cùng snapshot, trusted keys/endpoints có thể lệch. Chọn chiến lược config versioning/cache refresh có kiểm soát. Một đổi SLO endpoint có thể phá pending logout transactions; retention của outbound request context phải đủ để validate inbound old response đúng issuer/destination policy trong giai đoạn chuyển.

## 16. Java 17: mô phỏng shared state giữa hai nodes và SLO targeted

Ví dụ tạo một **shared in-memory state object** để mô phỏng Redis cluster. Hai logical nodes A/B dùng **cùng store instance**, do đó node A có thể tạo pending AuthnRequest và node B xử lý callback. Chương trình còn kiểm:
- Chặn callback sai browser cookie hoặc sai RelayState.
- Chặn dùng lại AuthnRequest đã consume.
- Chặn pending AuthnRequest quá hạn.
- Ánh xạ (registration, issuer, NameID, SessionIndex) → **tập local session IDs**.
- IdP SLO **đã verify** hủy đúng các sessions cùng SessionIndex, giữ session index khác.
- RP SLO xóa local session ngay, nhưng giữ **pending LogoutRequest transaction độc lập** để callback từ IdP tới node khác vẫn được match và consume một lần.
- Reject wrong browser-logout binding và replay LogoutResponse.

**Giới hạn cực kỳ quan trọng:** boolean `verifiedBySamlProvider` là dữ liệu **giả định được trusted framework cung cấp** trong test; không phải giá trị client được phép gửi. Code không parse XML, không verify chữ ký IdP, assertion Audience/Recipient/InResponseTo/time/replay, không cấp cookies, không kết nối Redis, không có TLS hay atomic Redis Lua scripts. Bản đồ `HashMap` không thread-safe và không thay một cluster repository production.

Lưu file `SamlClusterStateDemo.java`:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SamlClusterStateDemo {

    enum Decision {
        ACCEPT, REJECT_MISSING,
        REJECT_BINDING, REJECT_EXPIRED, REJECT_UNVERIFIED
    }

    record Identity(
            String registration, String issuer,
            String nameId, String sessionIndex) {}

    record PendingLogin(
            String requestId, String relayState,
            String browserSession, String registration,
            Instant expiresAt) {}

    record PendingLogout(
            String requestId, String relayState,
            String browserBinding, Instant expiresAt) {}

    static final class SharedStore {
        private final Map<String, PendingLogin> logins =
                new HashMap<>();
        private final Map<String, PendingLogout> logouts =
                new HashMap<>();
        private final Map<String, Identity> sessions =
                new HashMap<>();
        private final Map<Identity, Set<String>> index =
                new HashMap<>();

        void beginLogin(String requestId, String relayState,
                String browserSession, String registration,
                Instant expiresAt) {
            logins.put(requestId, new PendingLogin(
                requestId, relayState, browserSession,
                registration, expiresAt));
        }

        Decision completeLogin(
                String requestId, String relayState,
                String browserSession, Identity identity,
                Instant now, boolean verifiedBySamlProvider) {

            if (!verifiedBySamlProvider) {
                return Decision.REJECT_UNVERIFIED;
            }
            PendingLogin p = logins.get(requestId);
            if (p == null) {
                return Decision.REJECT_MISSING;
            }
            if (!now.isBefore(p.expiresAt())) {
                logins.remove(requestId);
                return Decision.REJECT_EXPIRED;
            }
            if (!p.relayState().equals(relayState)
                    || !p.browserSession().equals(browserSession)
                    || !p.registration().equals(
                        identity.registration())) {
                return Decision.REJECT_BINDING;
            }
            logins.remove(requestId);
            sessions.put(browserSession, identity);
            index.computeIfAbsent(identity,
                    ignored -> new HashSet<>())
                    .add(browserSession);
            return Decision.ACCEPT;
        }

        boolean sessionAlive(String localId) {
            return sessions.containsKey(localId);
        }

        void deleteSession(String localId) {
            Identity key = sessions.remove(localId);
            if (key == null) {
                return;
            }
            Set<String> ids = index.get(key);
            if (ids != null) {
                ids.remove(localId);
                if (ids.isEmpty()) {
                    index.remove(key);
                }
            }
        }

        int idpInitiatedLogout(
                Identity verifiedIdentity,
                boolean verifiedBySamlProvider) {
            if (!verifiedBySamlProvider) {
                return 0;
            }
            List<String> targets = new ArrayList<>(
                index.getOrDefault(
                    verifiedIdentity, Set.of()));
            for (String id : targets) {
                deleteSession(id);
            }
            return targets.size();
        }

        void beginRpLogout(
                String localSession, String requestId,
                String relayState, String browserBinding,
                Instant expiresAt) {
            if (!sessionAlive(localSession)) {
                throw new IllegalStateException(
                    "Active session required");
            }
            deleteSession(localSession);
            logouts.put(requestId, new PendingLogout(
                requestId, relayState,
                browserBinding, expiresAt));
        }

        Decision completeRpLogoutResponse(
                String responseInResponseTo,
                String relayState, String browserBinding,
                Instant now, boolean verifiedBySamlProvider) {
            if (!verifiedBySamlProvider) {
                return Decision.REJECT_UNVERIFIED;
            }
            PendingLogout p = logouts.get(responseInResponseTo);
            if (p == null) {
                return Decision.REJECT_MISSING;
            }
            if (!now.isBefore(p.expiresAt())) {
                logouts.remove(responseInResponseTo);
                return Decision.REJECT_EXPIRED;
            }
            if (!p.relayState().equals(relayState)
                    || !p.browserBinding().equals(browserBinding)) {
                return Decision.REJECT_BINDING;
            }
            logouts.remove(responseInResponseTo);
            return Decision.ACCEPT;
        }
    }

    static final class Node {
        final String name;
        final SharedStore store;

        Node(String name, SharedStore store) {
            this.name = name;
            this.store = store;
        }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        SharedStore shared = new SharedStore();
        Node nodeA = new Node("sp-a", shared);
        Node nodeB = new Node("sp-b", shared);

        Identity ix1 = new Identity("corp",
            "https://idp.example.org", "name-9", "IX-1");
        Identity ix2 = new Identity("corp",
            "https://idp.example.org", "name-9", "IX-2");

        nodeA.store.beginLogin(
            "R1", "relay-1", "browser-A",
            "corp", now.plusSeconds(120));
        System.out.println("Cross-node AuthnRequest: " +
            nodeB.store.completeLogin(
                "R1", "relay-1", "browser-A",
                ix1, now.plusSeconds(5), true));
        System.out.println("Replay AuthnRequest: " +
            nodeA.store.completeLogin(
                "R1", "relay-1", "browser-A",
                ix1, now.plusSeconds(6), true));

        nodeA.store.beginLogin(
            "R2", "relay-2", "browser-B",
            "corp", now.plusSeconds(120));
        System.out.println("Wrong browser binding: " +
            nodeB.store.completeLogin(
                "R2", "relay-2", "browser-X",
                ix1, now.plusSeconds(5), true));
        System.out.println("Wrong RelayState: " +
            nodeB.store.completeLogin(
                "R2", "wrong-relay", "browser-B",
                ix1, now.plusSeconds(6), true));
        System.out.println("Correct callback still works: " +
            nodeB.store.completeLogin(
                "R2", "relay-2", "browser-B",
                ix1, now.plusSeconds(7), true));

        nodeA.store.beginLogin(
            "OLD", "relay-old", "browser-X",
            "corp", now.plusSeconds(3));
        System.out.println("Expired pending request: " +
            nodeB.store.completeLogin(
                "OLD", "relay-old", "browser-X",
                ix1, now.plusSeconds(4), true));

        nodeA.store.beginLogin(
            "R3", "relay-3", "browser-C",
            "corp", now.plusSeconds(120));
        if (nodeB.store.completeLogin(
                "R3", "relay-3", "browser-C",
                ix2, now.plusSeconds(7), true)
                != Decision.ACCEPT) {
            throw new IllegalStateException(
                "Test login setup failed");
        }

        System.out.println("Unverified IdP SLO revoked: " +
            nodeB.store.idpInitiatedLogout(ix1, false));
        System.out.println("Verified SLO IX-1 revoked: " +
            nodeB.store.idpInitiatedLogout(ix1, true));
        System.out.println("Different SessionIndex remains: " +
            nodeA.store.sessionAlive("browser-C"));

        Identity foreign = new Identity("corp",
            "https://other-idp.example.org", "name-9", "IX-2");
        System.out.println("Foreign issuer revokes: " +
            nodeB.store.idpInitiatedLogout(foreign, true));

        nodeA.store.beginRpLogout(
            "browser-C", "L1", "logout-relay",
            "browser-transaction", now.plusSeconds(120));
        System.out.println("RP logout removed local session: " +
            !nodeB.store.sessionAlive("browser-C"));
        System.out.println("Wrong LogoutResponse binding: " +
            nodeB.store.completeRpLogoutResponse(
                "L1", "logout-relay", "other-browser",
                now.plusSeconds(10), true));
        System.out.println("Cross-node LogoutResponse: " +
            nodeB.store.completeRpLogoutResponse(
                "L1", "logout-relay", "browser-transaction",
                now.plusSeconds(11), true));
        System.out.println("Replay LogoutResponse: " +
            nodeA.store.completeRpLogoutResponse(
                "L1", "logout-relay", "browser-transaction",
                now.plusSeconds(12), true));
    }
}
```

Chạy với JDK 17+:

```bash
javac SamlClusterStateDemo.java
java SamlClusterStateDemo
```

Stdout **chính xác**:

```text
Cross-node AuthnRequest: ACCEPT
Replay AuthnRequest: REJECT_MISSING
Wrong browser binding: REJECT_BINDING
Wrong RelayState: REJECT_BINDING
Correct callback still works: ACCEPT
Expired pending request: REJECT_EXPIRED
Unverified IdP SLO revoked: 0
Verified SLO IX-1 revoked: 2
Different SessionIndex remains: true
Foreign issuer revokes: 0
RP logout removed local session: true
Wrong LogoutResponse binding: REJECT_BINDING
Cross-node LogoutResponse: ACCEPT
Replay LogoutResponse: REJECT_MISSING
```

### 16.1. Giải thích các kết quả

- `sp-a` lưu pending `R1`, `sp-b` đọc cùng shared store và nhận callback hợp lệ → `ACCEPT`. Nếu dùng hai HashMaps cục bộ khác nhau, case này sẽ fail.
- `R1` bị remove sau accept → lần sau `REJECT_MISSING`. Production còn cần replay ledger theo SAML Response/Assertion IDs.
- Browser `X` không được sử dụng pending request của browser `B`, dù biết `R2`/`RelayState`; `REJECT_BINDING`.
- RelayState sai cũng reject, nhưng không tiêu thụ pending `R2` để callback hợp lệ còn có cơ hội thành công. Production cần rate limiting để tránh probe.
- `OLD` có expiry ngắn nên bị từ chối; không kéo dài TTL vô hạn.
- `IX-1` có **hai local sessions** A/B; verified IdP SLO targeted đúng hai sessions, không hủy IX-2.
- Một LogoutRequest giả không được phép revoke; demo dùng boolean trusted giả lập để biểu diễn gate này.
- Một SLO request từ issuer khác, dù NameID tương tự, không revoke session của issuer thực.
- RP logout đã xóa local session C; pending `L1` vẫn còn trong **separate state map**, nên node B có thể kiểm LogoutResponse sau đó.
- Wrong browser binding không được consume `L1`; correct callback accept; replay callback reject.

### 16.2. Giới hạn code mẫu

1. `verifiedBySamlProvider` do test tự truyền không phải real crypto; production **không nhận boolean đó từ HTTP**. Phải lấy từ trusted, successfully validated SAML response/request.
2. `SharedStore` là HashMap một JVM, không thread-safe, không atomic Redis operations hoặc TTL background cleanup.
3. SAML identity key chỉ gồm registration/issuer/NameID/SessionIndex; production cần NameID format/qualifiers, tenant, trusted subject context.
4. Browser binding trong demo là string rõ, production dùng cookie/session-bound high-entropy secret hoặc mechanism mạnh đã phê duyệt.
5. Session ID của demo không đổi sau login; production phải xử lý session fixation/rotation ID.
6. Không xác minh XML signatures, time, Destination, AudienceRestriction, Recipient, InResponseTo, LogoutResponse status/replay.
7. `completeLogin` giả định verified IdP đã match Response InResponseTo với requestId; production phải **kiểm thật** trong OpenSAML provider.
8. Không có transaction/lock, unique keys hay generation-based revocation guard.
9. Không có distributed session storage, actual Redis SessionRepository, encrypted at rest và secret management.
10. Không nên lấy demo code làm SAML login/logout implementation; dùng Spring Security providers/filters và code mapping phía sau trust boundary.
11. Không chứng minh full global logout trên mọi devices; đó là yêu cầu phải test với live IdP, browsers và Spring Session Redis.
12. Không xử lý IdP LogoutRequest thiếu `SessionIndex` hoặc nhiều SessionIndex; production có policy riêng.

## 17. Bộ kiểm thử AuthnRequest multi-node

| ID | Tình huống | Expected |
| --- | --- | --- |
| AUTH-01 | Start login trên node A, ACS đến node B với same browser cookie | Pending request tìm được, SSO pass |
| AUTH-02 | Start trên A, node A restart, ACS đến C | Pass nếu shared state chưa hết TTL |
| AUTH-03 | Redis session state không đọc được | Reject callback, không bỏ InResponseTo |
| AUTH-04 | Cookie SESSION không gửi khi POST cross-site | Reject strict correlation hoặc xử lý browser-binding policy đã duyệt |
| AUTH-05 | Client gửi đúng InResponseTo nhưng khác browser session | Reject |
| AUTH-06 | Same RelayState nhưng altered InResponseTo | Reject |
| AUTH-07 | Same InResponseTo nhưng wrong registration/issuer | Reject |
| AUTH-08 | Pending request expired | Reject, không tạo SecurityContext |
| AUTH-09 | Duplicate valid SAMLResponse gửi tới B và C | Only first accepted; replay reject |
| AUTH-10 | Two tabs start two logins trong cùng browser session | Behavior đúng repository policy, không silent overwrite nguy hiểm |
| AUTH-11 | Browser timeout trước callback | Restart login, không fail-open |
| AUTH-12 | Valid signature nhưng wrong Audience | Reject |
| AUTH-13 | Valid signature nhưng wrong ACS Recipient | Reject |
| AUTH-14 | Valid response from untrusted IdP | Reject |
| AUTH-15 | IdP-initiated unsolicited response, SP chỉ cho SP-initiated | Reject |
| AUTH-16 | SameSite=Strict làm mất cookie | Test cross-site callback, không bỏ binding |
| AUTH-17 | SameSite=None;Secure + CSRF/correlation | Pass browser flow, không tạo login CSRF |
| AUTH-18 | Session fixation ID đổi sau login | New session indexed, old association removed |
| AUTH-19 | Node A/B có RelyingPartyRegistration versions khác nhau | Canary fail, rollout gate |
| AUTH-20 | Redis eviction mất pending request | Fail closed, monitor eviction |
| AUTH-21 | Callback trên wrong public hostname/proto | Reject wrong recipient/destination, fix proxy |
| AUTH-22 | User clicks login twice rapidly | No duplicate unexpected account/session |
| AUTH-23 | Redis replica lag khi đọc request | Không accept stale/replayed request |
| AUTH-24 | RelayState chứa attacker redirect URL | Không thực hiện arbitrary redirect |
| AUTH-25 | Signature altered sau signing | Reject vì signature, không tính correlation test |
| AUTH-26 | Protocol verification fails | Không ghi logout index/session association |
| AUTH-27 | Pending request created with unbounded TTL | Security QA FAIL |
| AUTH-28 | Request cache keyed only by RelayState không browser binding | Security QA FAIL cho strict SP-initiated flow |
| AUTH-29 | Node thuộc version cũ parse session serialized object mới | Version compatibility test, không silently bypass |
| AUTH-30 | Browser persistent cookie nhưng backend session expired | Reject, no ghost session |

### 17.1. Test fixture chuẩn

Mỗi integration test cần IdP test trusted signing key, current signed SAMLResponse, valid `Conditions`/bearer `SubjectConfirmationData`, correct `InResponseTo` và actual browser cookie khi test strict session repository. Sửa timestamp, NameID hoặc request ID trên XML sau khi ký sẽ tạo signature error, không chứng minh request repository.

### 17.2. Hãy kiểm điểm đích thay vì chỉ HTTP code

SAML login có thể redirect 302 đến success hoặc login error; verify:
- `SecurityContext` / authenticated principal đúng sau callback.
- New session ID nếu session fixation protection.
- Pending request consumed exactly once.
- Correct local session is indexed to IdP session.
- No session created on failed callback.
- Protected endpoint accessibility with browser cookie.
- No raw SAMLResponse/NameID/SessionIndex leaked in logs.

## 18. Bộ kiểm thử Single Logout multi-node

| ID | Tình huống | Expected |
| --- | --- | --- |
| SLO-01 | RP POST logout node A, IdP LogoutResponse đến B | Correlation and status handled across nodes |
| SLO-02 | RP local session invalidated trước LogoutResponse | Pending logout transaction still resolvable per design |
| SLO-03 | LogoutResponse InResponseTo không match pending LogoutRequest | Reject |
| SLO-04 | LogoutResponse RelayState wrong/missing against required binding | Reject according to profile |
| SLO-05 | Duplicate LogoutResponse after successful processing | Reject/idempotent response, never resurrect login |
| SLO-06 | LogoutResponse signature from unknown IdP | Reject |
| SLO-07 | IdP SLO signed, NameID/SessionIndex match two sessions on nodes A/C | Both sessions revoked |
| SLO-08 | IdP SLO targets IX-A, another IX-B exists | IX-B stays unless policy broader |
| SLO-09 | Same SessionIndex string from another IdP | No cross-issuer revocation |
| SLO-10 | Same NameID string from tenant B | No cross-tenant revocation |
| SLO-11 | IdP SLO callback with no browser cookie | Server-side mapping handles it |
| SLO-12 | IdP request no SessionIndex | Apply reviewed broad/strict policy, not guessed |
| SLO-13 | IdP request multiple SessionIndex entries | Validate then revoke only associated indexes |
| SLO-14 | IdP request unverified signature | Zero sessions deleted |
| SLO-15 | IdP request has duplicate Request ID | Replay reject; no future session deletion |
| SLO-16 | Session S1 expired but forward index stale | Reaper/reconciliation removes stale refs |
| SLO-17 | Session ID S0 changed to S1 at login | Index targets S1, not S0 |
| SLO-18 | SLO races fresh login for same IX | Revocation marker prevents session resurrection |
| SLO-19 | Redis partial deletion failure | Retry/idempotency and honest status, no false Success |
| SLO-20 | Logout request expires without IdP response | Local logout remains effective, pending cleaned |
| SLO-21 | IdP returns PartialLogout status | Show/audit partial, do not claim global SLO |
| SLO-22 | Browser third-party cookies blocked | IdP-initiated SLO not dependent on browser cookie |
| SLO-23 | A session in another browser/device shares IX | Scope according to verified SAML IX mapping |
| SLO-24 | A session has same username but different IdP session | No accidental blanket deletion |
| SLO-25 | Mapped HttpSession missing from store | Cleanup safe, no extra deletion |
| SLO-26 | sessionRepository.deleteById hits stale id | Idempotent, verify state/generation |
| SLO-27 | Role/locked account during SLO | Status/revocation apply, no re-login through race |
| SLO-28 | SAML NameID is transient, mapping changed | Only verified current association can be revoked |
| SLO-29 | Signing key rotates during pending LogoutRequest | Trusted old/new rollover policy tested |
| SLO-30 | IdP LogoutResponse indicates success but SP session still live | QA FAIL |
| SLO-31 | Local logout without SLO | Only local session ended; do not claim IdP logout |
| SLO-32 | User reauthenticates after SLO | New session can be established only after new trusted login |
| SLO-33 | IdP LogoutRequest sent at same time from different regions | Idempotent distributed revocation |
| SLO-34 | Health checks show Redis available but SAML index unavailable | SLO readiness fails |
| SLO-35 | Logs include raw SAMLResponse/NameID/SESSION cookie | Security QA FAIL |

### 18.1. Validate SLO message trước khi xóa

Không thể lấy `SessionIndex` trong raw LogoutRequest rồi xóa HTTP sessions vì một requester bất kỳ có thể gửi XML giả. Thứ tự:

```text
Parse hardened XML / binding
  -> resolve server-trusted registration/issuer
  -> verify IdP signature/certificate/algorithm
  -> verify destination, time, name ID, session index rules
  -> replay detect request ID
  -> derive authorized SAML session key
  -> resolve targeted local sessions
  -> revoke idempotently (and audit)
  -> sign/send LogoutResponse with correct Status/InResponseTo
```

Nếu application customizes handlers, đừng bỏ các validators mặc định của Spring Security. Với IdP-initiated SLO cần test nếu library hiện tại chỉ hủy **request-associated session** hay đáp ứng kỳ vọng cross-browser của app; nếu không có global mapping, thêm module được phép sau verified gate.

## 19. Chaos engineering / rolling deployment

### 19.1. Mô phỏng node failure

1. Browser bắt đầu SSO trên A, pending AuthnRequest persist Redis.
2. Kill pod A trước khi callback.
3. IdP POST callback đến B, assert login success với same session cookie.
4. Kill B ngay sau session created, protected request đến C still authenticated.
5. IdP gửi LogoutRequest vào C, assert sessions của A/B/device khác bị revoke theo SessionIndex.
6. Reuse old cookie sau logout trên B, assert protected data denied.
7. Repost same Response/LogoutRequest: replay rejected.
8. Không để thông tin PII/credentials trong chaos test artifacts.

### 19.2. Rolling deploy có schema/version mismatch

Nếu `AbstractSaml2AuthenticationRequest` hoặc custom session attribute serializes bằng Java object, bản app v1 có thể không đọc được object mà v2 viết. Một zero-downtime rollout cần:
- Backward/forward-compatible serialization (đừng dựa vào Java default serialization của arbitrary classes nếu chưa quản trị).
- Versioned DTOs, schema migration, canary login across versions.
- Namespace prefixes và TTL không phá pending transactions.
- Test v1 initiates / v2 completes và ngược lại.
- Controlled draining của old pending requests nếu intentionally breaking protocol.
- Không xóa Redis toàn bộ khi deploy — làm gián đoạn tất cả sessions và có thể che replay tests.

### 19.3. Redis failover

Check availability/consistency: login request write acknowledged bởi primary rồi read trên node khác có thể race replica lag trong setup không đồng bộ. Đối với one-time consume/replay, ưu tiên atomic operations trên consistency domain đúng; cache replica stale có thể dẫn đến double acceptance. Test failover khi:
- pending login just written,
- SLO revocation in progress,
- session index update after session ID rotation,
- IdP SLO request replayed.

Không chuyển sang `permitAll`, unsigned SAML, no InResponseTo hay session-less login chỉ để giữ UX khi Redis mất.

## 20. Bảo mật và riêng tư của trạng thái distributed

### 20.1. Redis không phải public session cache

- Đặt Redis ở private network, TLS, server auth/ACL.
- Secret credentials qua secret manager; rotate mà không làm mất state.
- Không exposing Redis trực tiếp internet hoặc dùng default weak password.
- Encrypt backups/snapshots, giới hạn retention, kiểm restore.
- Dùng namespace và ACL để một ứng dụng không đọc sessions của app khác.
- Không log `SESSION` cookie, SAMLResponse, NameID, raw RelayState hoặc raw SessionIndex.
- Giới hạn kích thước serialized SecurityContext và data minimization của SAML attributes.
- Không dùng Redis key chứa plaintext email/NameID nếu có thể dùng opaque/HMAC key.
- Phân biệt SAML signing/decryption keys với Redis encryption/auth keys.

### 20.2. Session IDs là bearer secrets

Ai biết session ID hợp lệ có thể chiếm session. Không đưa giá trị này trong:
- SAML `RelayState`.
- URL query parameters.
- Metrics labels.
- HTTP referrer hoặc browser analytics.
- Error messages/tickets/chat.
- Application debug logs.

Khi cần correlate logs, dùng independent opaque event IDs với TTL hoặc keyed hashing có scope; không tiết lộ mapping table cho support staff không được cấp quyền.

### 20.3. Session data minimization

SAML Assertion chứa NameID, attributes, groups, SessionIndex. Spring Security SAML2 Authentication có thể giữ serialized SAMLResponse/principal trong SecurityContext/session tùy release. Chỉ lưu những dữ liệu thật sự cần cho authorization và SLO; audit session serialization, Redis memory dumps, backups. **Không xóa signed Assertion không kiểm soát rồi phá framework semantics**, nhưng giảm attribute release từ IdP và đưa mapping minimal vào application index.

### 20.4. Cấp quyền revoke sessions

Một admin action “logout all sessions for user X” cũng là security-sensitive. Không cho API anonymous truyền `sessionIndex`/`NameID` và xóa Redis. Tách:
- Signed, validated IdP-initiated SLO.
- Authenticated user-initiated local logout.
- Admin-initiated revocation with RBAC/MFA/audit.
- Security incident bulk revocation with approval and job tracking.

Mỗi nguồn có trust/authorization khác nhau dù đều dẫn tới `SessionRepository.deleteById`.

## 21. Observability và runbook

### 21.1. Event log được phép

```json
{
  "event": "saml_callback_rejected",
  "registration": "corp",
  "node": "sp-b",
  "reason": "AUTHN_REQUEST_NOT_FOUND",
  "request_correlation": "opaque-event-8",
  "session_store": "redis",
  "result": "rejected"
}
```

Không log full SAMLResponse XML, private key, encoded tokens, raw SessionIndex/NameID, cookie ID hoặc user attributes. Logging nên giữ only safe reason codes & aggregate counters.

### 21.2. Metrics quan trọng

| Metric | Ý nghĩa |
| --- | --- |
| `saml_authn_request_missing_total` | Callback không tìm được pending request; browser cookie/Redis/TTL issue |
| `saml_inresponseto_mismatch_total` | Correlation fail, potential attack hoặc config |
| `saml_login_replay_rejected_total` | Repeated response rejection |
| `saml_logout_request_pending` | Outstanding RP logout transactions |
| `saml_logout_response_mismatch_total` | InResponseTo/RelayState validation fail |
| `saml_slo_target_sessions_count` | Các sessions targeted mỗi verified SLO |
| `saml_slo_partial_failure_total` | Delete/index/revocation partial failures |
| `saml_session_index_stale_total` | Stale forward/reverse mappings |
| `spring_session_redis_latency_ms` | Session lookup latency |
| `spring_session_redis_evicted_keys` | Capacity pressure |
| `saml_slo_replay_rejected_total` | Replay detected |
| `saml_same_site_cookie_missing_total` | Test-only/safe aggregate callback cookie absence |

**Đừng** thêm user email/NameID/sessionId làm metric labels vì cardinality và rò thông tin.

### 21.3. Runbook lỗi SSO sau scale-out

1. Kiểm flow: login redirect đầu tiên node nào, callback node nào.
2. Kiểm browser **có gửi đúng cookie tới ACS** sau cross-site POST không; không log cookie value.
3. Kiểm Spring Session Redis filter thực sự active, không phải in-memory Tomcat HttpSession.
4. Kiểm Redis namespace/credentials/TTL/evictions/config across pods.
5. Kiểm pending `AuthnRequest` retention theo release và session fixation lifecycle.
6. Kiểm `InResponseTo`, `RelayState` mismatch qua safe internal reason codes.
7. Kiểm proxy public ACS entityID/Recipient/Destination và forwarded headers.
8. Kiểm IdP trusted cert/keys/config versions và clocks.
9. Nếu chỉ một pod lỗi, drain/canary pod, so serialization/repository versions.
10. Nếu Redis unavailable, reject safely và hiện retry, không bypass correlation.
11. Test node A initiation → node B callback để xác nhận fix.
12. Monitor replay failures và unexpected login successes sau thay đổi.

### 21.4. Runbook lỗi SLO khi nhiều sessions còn sống

1. Xác minh IdP **thật sự phát signed LogoutRequest** và SP nhận đúng endpoint.
2. Xác minh validator signature/issuer/destination/timing/replay chạy thành công.
3. Xác định SessionIndex có mặt, nhiều indexes hay vắng mặt; áp scope đúng contract.
4. Dùng trusted registration + NameID context + SessionIndex tìm forward index.
5. Với từng target session ID, verify reverse association và current SessionRepository state.
6. Xóa sessions có kiểm soát, cập nhật mappings idempotently.
7. Nếu app có distributed revocation marker, update để chặn login/old-cookie races.
8. Trả SAML LogoutResponse đúng status theo kết quả thực, không báo Success giả.
9. Test old cookies từ **hai browser/nodes khác nhau** còn truy cập được không.
10. Audit cleanup/partial failures, reaper stale entries, Redis failover events.
11. Kiểm custom SLO handler có chạy khi không có browser session cookie không.
12. Chạy lại RP-initiated SLO và IdP-initiated SLO riêng; một flow pass không chứng minh flow kia.

## 22. Checklist production

- [ ] Public SP entityID, ACS và SLO URLs nhất quán qua mọi nodes/proxy.
- [ ] Trusted IdP metadata/verification keys và SP signing/decryption keys được đồng bộ/versioned.
- [ ] Spring Session Redis thực sự thay local HttpSession và có TLS/ACL/HA/TTL.
- [ ] Pending AuthnRequest được lưu theo security-binding policy, không chỉ local map.
- [ ] Callback trên node khác vẫn load được request với đúng browser-flow binding.
- [ ] `InResponseTo`/`RelayState`, signed assertion, issuer, audience, bearer và replay checks đều hoạt động.
- [ ] Không bypass `InResponseTo` khi Redis/cache fail.
- [ ] SameSite, Secure, HttpOnly, Cookie Domain/Path và cross-site POST đã test thực browser.
- [ ] Pending requests có TTL ngắn và atomic consume, hỗ trợ hoặc chặn multiple tabs theo policy.
- [ ] RP LogoutRequest repository giữ state cần thiết sau local session invalidation.
- [ ] LogoutResponse verify trusted IdP, `InResponseTo`/RelayState và consume exactly once.
- [ ] IdP LogoutRequest được verify **trước khi** tra SessionIndex và xóa sessions.
- [ ] SAML key gồm trusted registration, IdP issuer, NameID context và SessionIndex.
- [ ] Index maps to **set of local HTTP session IDs**, không chỉ current session.
- [ ] Reverse mapping cleanup đúng khi session expiry, logout và session ID rotation.
- [ ] IdP SLO không phụ thuộc browser cookie có mặt.
- [ ] Nếu SessionIndex absent/multiple, policy xác định rõ scope và failure behavior.
- [ ] SessionIndex targeted SLO không hủy sessions của IdP/tenant khác.
- [ ] Spring Session principal-name index không bị nhầm với SAML SessionIndex.
- [ ] One-time replay/expired request checks có atomic shared-store semantics.
- [ ] Login-vs-logout race có revocation/generation handling phù hợp.
- [ ] Redis failures làm login/logout fail safely, không bỏ trust/correlation.
- [ ] Local logout và federated logout được thông báo khác nhau nếu SLO partial.
- [ ] Rolling deploy serialization và config version compatibility được test.
- [ ] Chaotic node restart/Redis failover không phá auth/session binding.
- [ ] Không log session cookies, SAML raw assertions, NameID, RelayState hoặc keys.
- [ ] Multi-browser/multi-pod SLO acceptance tests xác minh old cookies bị deny.
- [ ] Cleanup/reaper và index reconciliation có metrics/alerts.
- [ ] High-risk actions check local account disabled/locked/session revocation state.
- [ ] SLO security incident runbook, change approvals và rollback plan sẵn có.

## 23. Câu hỏi ôn tập

**1. Vì sao login node A nhưng callback node B có thể fail?**  
Vì pending `AuthnRequest`/`HttpSession` đang nằm trong memory của A, B không đọc được. Chia sẻ state qua Spring Session Redis hoặc repository phân tán có browser binding.

**2. Sticky session có đảm bảo SSO HA không?**  
Không. Failover, callback mất affinity, pod restart và IdP SLO không kèm cookie phá giả định sticky.

**3. Spring Security mặc định lưu AuthnRequest ở đâu?**  
Ở `HttpSessionSaml2AuthenticationRequestRepository` theo tài liệu; khi HttpSession dùng Spring Session Redis, state được chia sẻ nếu callback mang đúng cookie.

**4. Có nên bỏ InResponseTo khi repository bị miss?**  
Không. Đó là bypass correlation/security; cần sửa cookie/Redis/TTL hoặc retry login an toàn.

**5. Lookup AuthnRequest chỉ theo RelayState có rủi ro gì?**  
Có thể mất browser-session binding, tạo login fixation/CSRF; cần additional flow binding nếu dùng global cache.

**6. Tại sao pending AuthnRequest phải one-time consume?**  
Để response/IdP assertion không thể được dùng để xác thực nhiều lần, bên cạnh replay controls.

**7. HttpSession ID và SAML SessionIndex có giống nhau không?**  
Không. HttpSession là ứng dụng/browser cookie; SessionIndex là IdP SAML session identifier.

**8. Vì sao IdP-initiated SLO không được dựa vào cookie?**  
Callback có thể không mang current browser cookie; để hủy sessions ở nhiều thiết bị cần trusted SessionIndex→sessions mapping phía server.

**9. Có thể map SessionIndex duy nhất không kèm issuer không?**  
Không an toàn; phải namespace bởi trusted registration/IdP và NameID context.

**10. Một SessionIndex có thể map nhiều local HttpSessions không?**  
Có. Targeted SLO cần revoke đúng tập active sessions theo hợp đồng.

**11. Spring Session findByPrincipalName có tự là SAML SessionIndex index không?**  
Không. Nó index theo principal name, không phân biệt IdP sessions/SessionIndex.

**12. IdP-initiated LogoutRequest có nên xóa session trước kiểm signature?**  
Không. Phải verify issuer/signature/profile/replay trước khi dùng NameID/SessionIndex.

**13. RP-initiated logout đã xóa local session trước LogoutResponse thì sao?**  
Phải có pending LogoutRequest correlation tồn tại đủ lâu ở đúng repository/flow binding để validate response từ IdP.

**14. LogoutResponse nói Success có nghĩa tất cả other apps đã logout?**  
Không mặc nhiên; có thể partial/failure/async. SP nên báo đúng local/federated status mà mình kiểm chứng được.

**15. Khi session ID đổi S0→S1 sau login, logout mapping trỏ đâu?**  
S1, cần update forward/reverse mapping; không chỉ giữ S0.

**16. Nếu Redis mất AuthnRequest có nên fallback local hashmap không?**  
Không tự động; làm phá consistency và browser binding. Fail safely và retry flow.

**17. Nếu IdP gửi SLO không có SessionIndex, SP làm gì?**  
Thực hiện theo SAML profile/trust contract đã duyệt: có thể broad logout cho NameID hoặc reject; không tự giả định chỉ xóa một session hay mọi user cùng email.

**18. Nếu user login đồng thời với IdP logout, có thể xảy ra gì?**  
Session resurrection race; cần atomic generation/revocation marker hoặc equivalent protection.

**19. Tại sao App session còn sống dù SAML Assertion đã hết hạn?**  
Assertion validity giới hạn sử dụng assertion; local session có lifetime riêng. Logout cần hủy local session theo policy.

**20. Vì sao cần xem SameSite/Path/Host khi debug AuthnRequest missing?**  
Cookie có thể không quay về ACS, nên node không xác định được browser HttpSession dù Redis khỏe.

**21. Có thể đặt RelayState bằng local session ID không?**  
Không. Session ID là bearer secret, không đưa vào browser-visible SAML parameters/URLs hoặc logs.

**22. Có thể tự tin việc bật `saml2Logout` sẽ đăng xuất mọi devices không?**  
Không. Phải kiểm khả năng library/ứng dụng map IdP SessionIndex đến local sessions và test multi-browser thực tế.

**23. Một IdP LogoutRequest được ký hợp lệ nhưng IdP B có NameID giống IdP A, có xóa phiên A không?**  
Không. Lookup phải namespace theo trusted IdP registration/issuer.

**24. Node đổi sau rolling deploy, object Spring Session không deserialize được thì sao?**  
Login/logout fail vì state incompatibility; cần versioned serialization và cross-version integration tests, không bỏ validation.

## 24. Tài liệu chính thức và tham khảo

- [Spring Security — Producing SAML2 AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `Saml2AuthenticationRequestRepository`, `HttpSessionSaml2AuthenticationRequestRepository` và `CacheSaml2AuthenticationRequestRepository` cùng cảnh báo RelayState/session binding.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `Saml2WebSsoAuthenticationFilter`, `Saml2AuthenticationTokenConverter` và verified response processing.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): luồng AuthnRequest, ACS, xác minh IdP assertions.
- [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/IdP-initiated SLO, LogoutRequest/LogoutResponse filters, `Saml2LogoutRequestRepository` và customization.
- [Spring Security — SAML2 Logout Request Repository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestRepository.html): save/load/remove pending SLO request.
- [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): Spring Session Redis-backed HttpSession, `springSessionRepositoryFilter`, namespace/cookies.
- [Spring Session — API Indexing](https://docs.spring.io/spring-session/reference/api.html): `FindByIndexNameSessionRepository` và `findByPrincipalName`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext persistence, session fixation protection, session expiry/logout.
- [OASIS SAML2 Core — Assertions and Protocols](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AuthnStatement/SessionIndex, LogoutRequest/LogoutResponse, InResponseTo, NameID.
- [OASIS SAML2 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO, Single Logout, bearer requirements.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature validation, InResponseTo, replay, XML parsing.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie security, session IDs, lifecycle.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): fail-closed auth, login CSRF, session behavior.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): protecting session IDs/claims in logs.

**Ghi nhớ:** Một cụm Spring Security SAML2 không chỉ cần các nodes cùng nhìn thấy `HttpSession`. Nó cần **AuthnRequest correlated đúng browser và tiêu thụ một lần**, **RP LogoutRequest vẫn tra được sau khi local logout**, và **IdP SessionIndex/NameID ánh xạ có kiểm soát tới mọi local sessions liên quan**. Spring Session Redis giúp giải bài toán shared HttpSession nhưng **không tự xây global SLO index**; sticky sessions không đảm bảo failover, và RelayState-only cache có thể mất browser binding. Luôn kiểm signature/issuer/audience/recipient/time/replay trước khi tạo hay thu hồi session, giới hạn TTL, quản trị Redis/keys và kiểm multi-browser multi-node SSO/SLO. Nếu store hoặc correlation thất bại, **fail closed** chứ không bỏ validation.