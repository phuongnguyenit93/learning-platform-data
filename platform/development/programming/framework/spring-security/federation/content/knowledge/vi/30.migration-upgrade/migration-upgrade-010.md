# Đối chiếu chính sách đăng xuất, MFA và thời hạn phiên trước khi chuyển đổi Spring Security federation

## 1. Mục tiêu: migration SSO phải giữ nguyên các ranh giới bảo vệ

Khi nâng cấp ứng dụng Spring Security từ cơ chế xác thực cũ sang **SAML 2.0, OpenID Connect (OIDC), CAS** hoặc thay đổi phiên bản framework/Identity Provider, một lần đăng nhập thành công chưa chứng minh migration an toàn. Chính sách **đăng xuất (logout/session revocation)**, **xác thực nhiều yếu tố (MFA/step-up)** và **thời hạn phiên (idle/overall/freshness)** có thể âm thầm bị nới lỏng.

Bài thuộc nhóm **Chuyển đổi và nâng cấp**. Mục tiêu là lập một **policy-parity contract** được phê duyệt, kiểm đúng luồng giao thức, viết positive/negative tests và đặt **GO/NO-GO gate** trước cutover. Người học cần phân biệt:

- **Local logout**, **RP/SP-initiated logout**, **IdP/OP/AP-initiated logout**, **Single Logout (SLO)** và **administrator revocation**.
- **IdP SSO session**, **local HttpSession** và **access/refresh tokens**: ba vòng đời độc lập.
- **MFA đã xảy ra** với **MFA vừa xảy ra**: ACR/AMR/AuthnContext và thời điểm `auth_time`/`AuthnInstant`.
- **Idle timeout** với **overall reauthentication timeout**, **MFA freshness**, **hard cap từ thời điểm phát session** và **JWT exp**.
- Spring Security Servlet `SecurityContextRepository`, session fixation, concurrency limits, OIDC back-channel logout, SAML SLO và CAS SLO.
- Khi **UNKNOWN assurance** hoặc thiếu event delivery proof phải **fail closed** cho tác vụ yêu cầu bảo đảm cao.

**Nguyên tắc:** một chính sách mới chỉ đạt parity khi không cho phép một user/session/action mà chính sách cũ đã được phê duyệt sẽ từ chối, trừ thay đổi đã được security/business owner chấp thuận bằng văn bản.

## 2. Kịch bản cho thấy lỗi ẩn

~~~text
Legacy policy đã duyệt:
  Local idle timeout             = 30 phút
  Overall reauth timeout         = 8 giờ
  Sensitive transfer MFA maximum = 10 phút
  Admin sensitive MFA            = phishing resistant
  Active sessions per subject    = tối đa 2
  Identity Provider logout       = phải hủy local sessions liên quan

Candidate migration:
  Login OIDC thành công, nhận signed ID Token.
  App chỉ dùng HTTP session idle=60 phút.
  ID Token có iat mới, auth_time cũ; app nhầm iat là fresh MFA.
  /logout xóa browser cookie nhưng không xử lý OP back-channel.
  Admin access vẫn có ROLE_ADMIN với phiên cũ.
  Mobile/API còn dùng bearer token chưa revoked.

=> Đăng nhập trên staging PASS, nhưng MFA/session/logout parity FAIL.
~~~

Các con số **30 phút, 8 giờ và 10 phút** là giả định cho một ứng dụng; **không phải thông số bắt buộc chung** của SAML/OIDC/CAS. Chỉ dùng policy thật được doanh nghiệp phê duyệt để đánh giá.

## 3. Inventory trước khi so sánh

### 3.1. Những câu hỏi phải có câu trả lời

1. User login từ bao nhiêu IdPs? Mỗi provider có **issuer, clientId/registrationId, SP entityId, tenant, subject identifier** nào?
2. MFA áp dụng cho nhóm nào: mọi login, nhóm admin, dữ liệu nhạy cảm, đổi phương thức MFA, chuyển tiền hay thao tác sau risk event?
3. Bằng chứng MFA là claim nào? **OIDC acr/amr/auth_time**, **SAML AuthnContext/AuthnInstant**, CAS-specific attributes hay trusted gateway attestation?
4. App có **local, global, IdP-initiated, admin revoke, inactivity, overall** logout không? Phạm vi từng tác vụ là **một session, toàn bộ sessions user, một ứng dụng hay nhiều ứng dụng**?
5. Local session lưu ở Servlet container, **Spring Session Redis/JDBC**, BFF cookie, stateless JWT hay session registry riêng?
6. Timeout của browser cookie, server session, remember-me, access token, refresh token, IdP SSO session có bị nhầm lẫn không?
7. Điều gì xảy ra khi IdP callback đến muộn, browser có hai tab, hai sessions ở hai thiết bị, nhiều Spring replicas, logout event retry hoặc revocation đến sau login?
8. Legacy có case đặc biệt: break-glass, trusted devices, administrator session, long-lived remember-me, delegated/proxy user, step-up?
9. Lúc rollback, **session đã logout hoặc user bị khóa có được sống lại không**?
10. Ai xác nhận policy baseline và ai quyết định một chênh lệch có thể được chấp nhận?

Phải thu **cả cấu hình và hành vi thực tế**. Một flag `singleLogout=true` không chứng minh local session đã bị xóa. Một timeout property không chứng minh tất cả replicas cùng enforce.

### 3.2. Bảng chứng cứ cần lập

| Policy item | Evidence legacy | Candidate implementation | Test proof | Owner |
| --- | --- | --- | --- | --- |
| Local logout | Controller/filter/logs | Spring LogoutFilter | Old cookie denied | App |
| Upstream/global logout | IdP/CAS contract | SAML SLO hoặc OIDC RP logout | Other RP state | IAM |
| Remote logout | Signed callback logs | OIDC back-channel / SAML SLO / CAS SLO | Mapped sessions invalid | IAM + App |
| MFA classes | IAM policy + attributes | Verified claims adapter | Low assurance denied | Security |
| MFA freshness | Trusted authentication event | `auth_time`/AuthnInstant + state | Boundary tests | Security |
| Idle/overall timeout | Effective session config | Servlet + explicit policy | Frozen-clock tests | App |
| Concurrency | Session registry | Session management | Third login | App |
| Account disable/revoke | IAM events | Event/lookup/cache TTL | Time-to-deny SLA | Security |
| Browser+API token cleanup | Logout implementation | Cookie/session and revocation | Token replay tests | API |
| Rollback and migration | Old session store | Controlled expiry/re-auth | No resurrected user | Operations |

Đánh dấu **UNKNOWN**, **UNSUPPORTED**, **NOT TESTED** khi không có chứng cứ; đừng tự nâng những hàng này thành PASS.

## 4. Tách ba loại phiên và bốn loại thời hạn

~~~text
             Identity Provider / OP / CAS
                upstream SSO session
                         |
                  SAML/OIDC/CAS proof
                         |
            Spring Security Relying Party
                  local HttpSession
                         |
             API access/refresh tokens
~~~

- **IdP SSO session** duy trì tại domain IdP, có cookie/session/reauth policy riêng.
- **Local HttpSession** chứa Spring `SecurityContext` hoặc app session identity. Việc xóa app cookie không tự xóa phiên IdP.
- **Access token** được resource server xác minh; có thể còn hợp lệ dù user đã logout browser. **Refresh token** còn vòng đời và revocation riêng.

Một OIDC **ID Token `exp`** chỉ giới hạn tính hợp lệ của chứng từ tại thời điểm validate; **không phải** local HttpSession deadline. `iat` là lúc phát token, không phải lúc user thực sự xác thực; `auth_time` mới nói về authentication event khi claim được hỗ trợ/verified. Access token `exp` không chứng minh user còn hiện diện.

SAML **`Conditions@NotOnOrAfter`** và bearer `SubjectConfirmationData@NotOnOrAfter` giới hạn **accept assertion**, không mặc định là local session lifetime. `AuthnStatement@SessionNotOnOrAfter` thuộc thông tin upstream session và phải được ánh xạ bằng policy, không tự đặt Spring HttpSession timeout. CAS **Service Ticket** chỉ validate một lần, không là session cookie hay TGT lifetime.

| Timer | Mốc bắt đầu | Khi nào được reset? | Kiểm gì |
| --- | --- | --- | --- |
| **Idle** | Hoạt động hợp lệ gần nhất | User activity | Sau X phút không hoạt động → session expires |
| **Overall reauth** | Authentication hoặc reauthentication thành công gần nhất | Chỉ reauth thực sự | Dù có activity, quá X giờ vẫn phải reauthenticate |
| **MFA freshness** | Trusted MFA event gần nhất | Fresh verified MFA/step-up | Action nhạy cảm đòi proof không quá Y phút |
| **Hard lifetime** | Session issued-at | Không reset nếu policy yêu cầu | Session không tồn tại quá Z giờ |
| **OP/IdP session lifetime** | Upstream session | Theo IdP policy | Không suy tự động từ local session |
| **Token expiry/rotation** | Token `iat/exp`/grant state | Theo token server | Không thay local session policy |

**NIST SP 800-63B-4 (2025)** phân biệt **overall** và **inactivity** reauthentication. Với AAL2, mức khuyến nghị là overall không quá **24 giờ (SHOULD)** và inactivity không quá **1 giờ (SHOULD)**; đây không phải lệnh tự nới policy cũ 30 phút/8 giờ. Revision 3 (2017) dùng các khuyến nghị khác; luôn ghi đúng revision, phạm vi AAL và quy định áp dụng. Nếu tổ chức yêu cầu hard cap không reset dù reauth, phải thiết kế **timer riêng**.

## 5. Policy-parity matrix: cách chốt yêu cầu có thể kiểm thử

| Dimension | Legacy giả định | Candidate không yếu hơn | Negative/positive test |
| --- | --- | --- | --- |
| Local logout | POST + CSRF, session invalid | Giữ đúng | Old cookie sau POST → DENY |
| RP-initiated global | Có lựa chọn logout upstream | Có tương đương | OP session và other RPs kiểm thực |
| IdP-initiated logout | Hủy sessions liên quan | Không bỏ | Signed event → no access |
| User/admin revoke | Phản ánh theo SLA | Không nới | Disable user mid-session |
| Login basic assurance | Trusted issuer/account | Không nhầm issuer/tenant | Unknown IDP → DENY |
| Sensitive MFA | Fresh MFA ≤10 phút | ≤10 phút | 9m59s PASS, 10m STEP_UP |
| Phishing-resistant admin | Bắt buộc | Vẫn bắt buộc | OTP-only denied |
| Idle session | 30 phút | ≤30 phút | Frozen clock boundary |
| Overall session | 8 giờ | ≤8 giờ | User active vẫn expire |
| Max simultaneous | 2 | ≤2 | Third login policy |
| Session fixation | Rotate session ID | Giữ | Old ID denied |
| Remember-me | Low risk only | Không cấp high risk | Remember-me → STEP_UP |
| JWT/refresh token | Revocation có SLA | Không bỏ | Old token after logout |
| Multi-node enforcement | Cùng session view | Cùng hoặc chặt hơn | Node A/B |
| Failure handling | No fail-open | No fail-open | OP outage, unknown ACR |

### 5.1. Các so sánh không thể chỉ dùng số

**Time and count** có thể so:

~~~text
new.idle <= approved.idle
new.overall <= approved.overall
new.mfaMaxAge <= approved.mfaMaxAge
new.maxConcurrentSessions <= approved.maxConcurrentSessions
~~~

**Assurance** phải dùng mapping đã được IdP/security owner xác thực, không tự so chuỗi `acr`. Một `acr="2"` ở OP A không đương nhiên bằng `acr="2"` ở OP B, và `amr=["pwd","otp"]` không đương nhiên thỏa chính sách **phishing resistance**. Không rõ evidence → `UNKNOWN` và **deny/step-up**.

**Logout scope** phải so hậu điều kiện. Nếu legacy xóa tất cả application sessions khi IdP phát sự kiện, candidate chỉ xóa browser hiện tại là **regression**, dù cả hai có URL chứa chữ “logout”.

## 6. Đăng xuất local: bất biến nền tảng

Trong Spring Security Servlet, local logout theo `LogoutFilter`/`LogoutHandler` xóa Authentication và session theo cấu hình. Ví dụ:

~~~java
// Spring Security Servlet fragment; cần imports/dependencies.
http.logout(l -> l
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID"));
~~~

Khi **CSRF bật** (mặc định trên Spring Servlet), nên giữ **POST /logout có CSRF**. Đổi thành unauthenticated GET logout để “tiện liên kết” có thể tạo logout CSRF. Nếu dùng Spring Session, tên cookie thường là `SESSION` chứ không phải `JSESSIONID`; chỉnh ứng dụng thực.

Sau logout:

- Old local HttpSession bị invalidate trong server store, không chỉ xóa browser cookie.
- Old cookie/header/session ID không lấy được protected content.
- Spring `SecurityContextRepository`/custom authentication filters không lưu lại stale context.
- Browser có thể SSO đăng nhập lại nếu upstream IdP session còn; đó là **đăng nhập mới**, không chứng minh local logout đã thất bại.
- Downstream tokens/refresh token families cần xử lý riêng theo policy: xóa local cookie không tự revoke JWT đang còn valid.
- Multi-tab and multi-node requests phải thấy cùng kết quả; concurrent logout/reauth race không làm sống lại session.

**Không chỉ kiểm HTTP 302 sang trang /login**. Hãy gửi lại old cookie tới một endpoint protected và kiểm security outcome.

## 7. OIDC logout: local, RP-initiated và back-channel

Spring Security hiện đại hỗ trợ ba use cases qua OAuth2 Login.

### 7.1. RP-initiated logout

`OidcClientInitiatedLogoutSuccessHandler` có thể redirect browser đến `end_session_endpoint` từ OP discovery:

~~~java
@Bean
SecurityFilterChain oidcChain(
        HttpSecurity http,
        ClientRegistrationRepository clients) throws Exception {
    OidcClientInitiatedLogoutSuccessHandler handler =
        new OidcClientInitiatedLogoutSuccessHandler(clients);
    handler.setPostLogoutRedirectUri("{baseUrl}");
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .logout(l -> l.logoutSuccessHandler(handler));
    return http.build();
}
~~~

Đây là Spring integration fragment cần đúng imports/client registrations; **không biên dịch một mình bằng javac**. Cần OP hỗ trợ discovery/end-session và allowlist `post_logout_redirect_uri`. Một redirect thành công tới OP **không bảo đảm** các RP khác đã bị logout; IdP propagation là trách nhiệm của OP/other clients. Nếu UI ghi “Đăng xuất tất cả thiết bị”, phải kiểm phạm vi thực tế.

### 7.2. OP-initiated OIDC Back-Channel Logout

Spring Security Servlet:

~~~java
@Bean
SecurityFilterChain oidcBackChannel(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oidcLogout(o -> o.backChannel(Customizer.withDefaults()));
    return http.build();
}
~~~

Endpoint mặc định là `POST /logout/connect/back-channel/{registrationId}`; OP gửi **Logout Token** JWT đã ký. Phải validate signature/alg, `iss`, `aud`, `iat/exp`, `events`, `sub` hoặc `sid`, `jti` replay và yêu cầu **không có `nonce`** theo OIDC Back-Channel Logout spec. Không dùng user-controlled HTTP `?sub=alice` làm tín hiệu logout.

Scope:

- Có `sid`: invalidates matching **OP session** trong đúng client/issuer; không hủy mọi browser của user nếu event chỉ nhắm một phiên.
- Chỉ có `sub`: invalidates sessions cùng **issuer/client/subject** theo profile.
- Có cả `sid` và `sub`: phải kiểm hai giá trị thuộc đúng identity và không hủy session của user khác.
- Sai issuer, audience, jti hoặc chữ ký: reject.
- Duplicate event: replay controls/idempotency; không tạo session mới hoặc xóa nhầm.

**Spring Session cookie name trap:** Spring Security OIDC back-channel handler mặc định dùng `JSESSIONID`, trong khi Spring Session thường đặt `SESSION`. Official docs hướng dẫn:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcBackChannelLogoutHandler(
        OidcSessionRegistry registry) {
    OidcBackChannelLogoutHandler handler =
        new OidcBackChannelLogoutHandler(registry);
    handler.setSessionCookieName("SESSION");
    return handler;
}
~~~

Kiểm `HttpSessionEventPublisher`/session registry cleanup theo version và thao tác invalidation thật. **Callback trả HTTP 200 nhưng old cookie vẫn được xác thực là FAIL**.

## 8. SAML2 Single Logout: RP-initiated, AP-initiated

Spring Security hỗ trợ `saml2Logout(Customizer.withDefaults())` với `RelyingPartyRegistration` có `SingleLogoutService` metadata, verification/signing credentials phù hợp.

~~~java
// Spring Security fragment
http.saml2Login(Customizer.withDefaults())
    .saml2Logout(Customizer.withDefaults());
~~~

**RP-initiated SLO:** local user POST logout theo endpoint được cấu hình; Spring invalidates session, tạo/ký `saml2:LogoutRequest` gửi IdP; có thể nhận `saml2:LogoutResponse` và kiểm chữ ký, issuer, request correlation, status.

**AP/IdP-initiated SLO:** IdP gửi signed `saml2:LogoutRequest` đến `/logout/saml2/slo`; Spring kiểm issuer/signature/NameID/SessionIndex/request details, logout đúng local session rồi gửi signed response.

Có thể tách local logout và SAML SLO:

~~~java
http.logout(l -> l.logoutUrl("/logout"))
    .saml2Logout(s -> s.logoutUrl("/saml2/logout"));
~~~

Không được suy tất cả POST /logout sẽ kích hoạt global SLO nếu app đã tách endpoint. Một SAMLResponse ký đúng khi login **không đảm bảo IdP có hỗ trợ SLO**; cần metadata `SingleLogoutService` và integration tests.

Các trường `SessionIndex`, `NameID`, registration/issuer và browser/session context phải map đúng; không logout user Bob chỉ vì NameID/email giống Alice. Front-channel có thể phụ thuộc browser cookies/redirects; policy cần thử browser privacy/SameSite. Assertion `Conditions NotOnOrAfter` chỉ giới hạn assertion acceptance, không tự đặt local session TTL.

## 9. CAS Single Logout khi rời CAS sang giao thức khác

Apereo CAS có **CAS SSO Session/TGC** tại CAS Server và local client sessions. **Local CAS application logout** và **central CAS logout** không tự làm nhau biến mất. CAS SLO gửi thông báo tới ứng dụng đã tham gia khi SSO session kết thúc; cấu hình có thể là back-channel POST hoặc front-channel, theo CAS version/service registry/client support.

Test:

1. CAS user có nhiều client applications và local sessions.
2. Central CAS logout phát thông báo theo configured SLO channel.
3. CAS client xử lý event gắn **Service Ticket/Session identifier** với đúng local HttpSession.
4. Protected resource ở từng app không truy cập bằng old cookie.
5. Offline app, retry/timeouts và best-effort delivery có SLA/monitoring rõ.
6. CAS `renew=true` yêu cầu primary auth theo CAS protocol, **không tự chứng minh MFA**; phải map CAS-specific assurance attributes theo IdP contract.

Khi migrate CAS → OIDC, không chỉ đổi URL login. Phải thay **CAS SLO correlation** bằng OIDC logout token/session registry và kiểm hiệu lực tương đương. Đừng giả định CAS SLO payload là SAML 2.0 IdP-initiated LogoutRequest cho SAML SP; mỗi protocol có semantics và security validation riêng.

## 10. MFA evidence: OIDC ACR/AMR/Auth Time

### 10.1. Ba claim khác nhau

- `acr`: **Authentication Context Class Reference**, giá trị chỉ có nghĩa qua IdP policy/contract. `acr="urn:example:mfa"` chỉ là ví dụ.
- `amr`: **Authentication Methods References**, danh sách phương pháp OP khai đã dùng. Đây không phải một bảng assurance universal; cần mapping và kiểm độ tin cậy.
- `auth_time`: thời điểm user **thực sự được OP xác thực**, không phải `iat` (thời điểm ID Token phát hành). OP có thể phát token mới từ SSO session cũ mà auth_time không mới.
- `exp`: giới hạn tuổi token, không là assurance/freshness claim.
- `sid`: OP session ID cho một số profiles, không phải local JSESSIONID.

Ví dụ mapping **cần được security owner phê duyệt**:

~~~text
trusted issuer=https://idp.example.test/realms/corp
acr=urn:example:basic            => PASSWORD
acr=urn:example:mfa              => VERIFIED_MFA
acr=urn:example:phishing-resist  => VERIFIED_MFA + phishingResistant=true
acr missing / unknown            => UNKNOWN; sensitive action DENIED
~~~

Không tự nâng `amr=["pwd","otp"]` lên **phishing-resistant MFA** và không giả định cùng acr label ở hai IdPs tương đương.

### 10.2. OIDC step-up

Một protected action có thể yêu cầu fresh authentication và assured ACR trong authorization request:

~~~text
GET /authorize?response_type=code
  &client_id=portal-client
  &redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcorp
  &state=<fresh-random-state>
  &nonce=<fresh-random-nonce>
  &max_age=600
  &acr_values=urn%3Aexample%3Amfa
~~~

Đây chỉ là cấu trúc minh họa; production phải tạo `state`/`nonce` bằng framework, dùng PKCE nếu áp dụng, bind transaction/browser và validate ID Token. OIDC Core định nghĩa:

- `max_age`: maximum authentication age tính bằng giây từ lần **active authentication** tại OP; khi gửi `max_age`, ID Token **phải có `auth_time`**.
- `max_age=0` tương đương `prompt=login`, **không tự là MFA**. Fresh password-only vẫn có thể không đạt sensitive policy.
- `acr_values` thường là voluntary; nếu RP cần một assurance bắt buộc và OP hỗ trợ `claims`, có thể yêu cầu **Essential `acr`** theo OIDC Core; vẫn phải kiểm claims thực tế.
- Nếu `acr` thiếu/sai, `auth_time` quá cũ, `iss/aud/nonce` sai hoặc user subject đổi, **không thực hiện sensitive action**.
- Custom `OAuth2AuthorizationRequestResolver`/`DefaultOAuth2AuthorizationRequestResolver` có thể thêm provider-specific parameters, nhưng không bỏ `AuthorizationRequestRepository`/state correlation.

Kết quả step-up chỉ được dùng nếu **cùng trusted issuer+subject+tenant**, không silent account switch hoặc account linking từ attacker.

## 11. SAML MFA: RequestedAuthnContext, ForceAuthn và AuthnInstant

SAML `AuthnRequest` có thể chứa:

- `ForceAuthn="true"`: yêu cầu IdP thực hiện **fresh authentication** theo SAML, không bắt buộc MFA nếu IdP chỉ dùng password.
- `RequestedAuthnContext/AuthnContextClassRef`: SP nêu ngữ cảnh yêu cầu; ý nghĩa class URNs phụ thuộc IdP/federation agreement.
- `Comparison="exact"` hoặc mode khác theo SAML profile; đừng tự xếp mọi vendor ACR theo rank.
- Kết quả `Assertion/AuthnStatement/AuthnContext` và `AuthnInstant` phải được verify (sau XMLDSig/issuer/audience/subject validations).

Ví dụ cấu trúc **chưa ký**, chỉ chỉ vị trí element:

~~~xml
<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                   ForceAuthn="true">
  <samlp:RequestedAuthnContext Comparison="exact">
    <saml:AuthnContextClassRef
        xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
      urn:example:mfa
    </saml:AuthnContextClassRef>
  </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

Spring Security 7/OpenSAML 5 có `OpenSaml5AuthenticationRequestResolver.setAuthnRequestCustomizer`:

~~~java
@Bean
Saml2AuthenticationRequestResolver resolver(
        RelyingPartyRegistrationRepository registrations) {
    RelyingPartyRegistrationResolver r =
        new DefaultRelyingPartyRegistrationResolver(registrations);
    OpenSaml5AuthenticationRequestResolver x =
        new OpenSaml5AuthenticationRequestResolver(r);
    x.setAuthnRequestCustomizer(c ->
        c.getAuthnRequest().setForceAuthn(true));
    return x;
}
~~~

Đây là Spring integration fragment, không phải standalone Java. Cần wiring resolver vào actual SAML filter. ForceAuthn ở request chỉ là **ý định**; sensitive action phải kiểm **ngữ cảnh và thời điểm thực ở response**. **IdP-initiated SSO** không có SP AuthnRequest; với privileged operations, cần trusted outcome assurance hoặc một SP-initiated step-up flow.

CAS `renew=true` hay Kerberos/SPNEGO automatic SSO cũng **không tự tương đương fresh MFA**. Trusted proxy header chỉ được dùng khi proxy kiểm xác thực và strip/override client-supplied headers.

## 12. Spring session policy: idle, overall, MFA freshness

Spring Boot Servlet config minh họa:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

`server.servlet.session.timeout` thường điều khiển **idle session timeout**, không tự enforce overall 8 giờ, hard cap từ issuance hoặc MFA 10 phút. Khi dùng Spring Session/Redis, cần kiểm store TTL và cookie name thực. Cookie `Max-Age` không thay được server invalidation; ID Token expiry cũng không tự hủy `SecurityContext`.

Spring Security session fixation/concurrency fragment:

~~~java
http.sessionManagement(s -> s
    .sessionFixation(f -> f.newSession())
    .maximumSessions(2));
~~~

Cần session registry/event publisher và distributed-session enforcement thực khi deploy nhiều nodes. Không coi `maximumSessions` đơn lẻ là bằng chứng trên hai replicas.

Thiết kế policy service server-side phải lưu:

~~~text
sessionEstablishedAt
lastVerifiedAuthenticationAt  (auth_time/AuthnInstant trusted)
lastActivityAt                (chỉ user activity đúng policy)
lastVerifiedMfaAt             (không reset bởi token refresh)
verifiedAssuranceClass        (issuer-specific mapping)
phishingResistanceEvidence    (verified and scoped)
localUser/issuer/client/tenant/subject
sessionVersion, revokedAt, policyVersion
~~~

Tại mỗi sensitive request:

1. Kiểm local user còn active, issuer/client/tenant binding đúng.
2. Kiểm idle/session overall/hard cap nếu có.
3. Kiểm role/business permission.
4. Kiểm trusted MFA evidence và freshness; nếu chưa đủ, **STEP_UP**.
5. Không dùng HTTP header/claim từ client làm evidence trực tiếp.
6. Đảm bảo callback step-up vẫn là **cùng account**, không replay/CSRF, action được xử lý đúng một lần.
7. Session logout/revoke phải invalidate local state và không bị stale cache tái tạo.

**User activity không reset overall timeout hoặc MFA freshness**. Chỉ reauthentication thật mới làm mới proof phù hợp.

## 13. Các kịch bản cắt chuyển dễ sai

### 13.1. Cũ có MFA, mới chỉ có email trùng

~~~text
Legacy CAS:
  alice, MFA đã verify, ROLE_APPROVER.

OIDC mới:
  email=alice@example.test
  iss/subject mới; acr missing; auth_time cũ.

KHÔNG được:
  copy lastMfaAt/ROLE_APPROVER từ session cũ vì cùng email.

PHẢI:
  verify IdP issuer/client/subject/tenant and account linking,
  map assurance evidence theo policy, reload local authorization.
  Nếu evidence thiếu: step-up/re-auth, không approve action.
~~~

### 13.2. Local logout thành công nhưng người dùng SSO lại

Nếu logout contract là **LOCAL_ONLY**, điều này có thể đúng. Nếu contract là **GLOBAL**, cần OP end_session/SAML SLO/CAS central logout và xác nhận các sessions khác đã bị xóa. Không phỏng đoán từ giao diện login.

### 13.3. IdP remote logout và hai browsers

Browser A và B của Alice có hai OP `sid`; Bob có một session khác. Một Logout Token có `sid=A` chỉ hủy session A. Nếu token chỉ có `sub=alice` có thể hủy mọi matching sessions Alice trong cùng client/issuer. Không scope theo email, không hủy Bob.

### 13.4. Tài nguyên nhạy cảm sau khi SSO được dùng lại

ID Token mới có `iat=now` nhưng `auth_time=now-2h`; app policy yêu cầu MFA trong 10 phút. **Deny/STEP_UP**, không suy iat mới là MFA mới. Nếu `max_age`/Essential ACR không được OP đáp ứng, sensitive action vẫn deny.

### 13.5. Session hết hạn và activity

Ở idle 30 phút và overall 8 giờ:

~~~text
lastActivityAt=10:00Z
At 10:29:59Z: idle còn hiệu lực
At 10:30:00Z: idle hết hạn (chính sách boundary inclusive)

lastVerifiedReauthAt=02:00Z
At 10:00:00Z: overall 8 giờ hết hạn,
  dù có HTTP request hoạt động lúc 09:59:59Z.
~~~

Clock-skew handling, Redis TTL/lastAccessedTime, browser cookie phải được kiểm theo **đúng tiêu chí của dự án**, dùng clock injection thay vì `Thread.sleep()` dài trong CI.

### 13.6. User bị vô hiệu hóa giữa phiên

Khi IAM disable account, một OIDC ID Token hoặc SAML Assertion đã được validate trước đó **không tự biến mất**. Cần event logout/revoke, local user status check hoặc cơ chế khác để đạt **revocation SLA**. Nếu JWT access token không có introspection/revocation/short enough lifetime, không hứa “revoke ngay lập tức” khi thực tế API còn nhận token.

## 14. Ma trận kiểm thử regression

| ID | Input | Expected |
| --- | --- | --- |
| L01 | Local POST logout + CSRF hợp lệ | Old session cookie denied |
| L02 | Cross-site GET logout không intent | Không logout trái phép |
| L03 | OIDC RP end_session | Đúng OP/redirect, local session clean |
| L04 | OP logout Token đúng `sid` | Chỉ mapped session đó bị hủy |
| L05 | OP logout Token chỉ `sub` | Các matching sessions đúng issuer/client bị hủy |
| L06 | OIDC forged Logout Token/`iss`/`aud`/`events` sai | Reject, không hủy user khác |
| L07 | Logout Token có cả sid/sub không khớp | Không hủy session sai |
| L08 | OIDC `jti` replay | Idempotent/replay controls |
| L09 | Spring Session cookie tên `SESSION` | Backchannel handler map đúng |
| L10 | SAML signed AP LogoutRequest + SessionIndex | Session tương ứng bị hủy |
| L11 | SAML wrong issuer/signature/SessionIndex | Reject |
| L12 | SAML RP LogoutResponse mismatch/replay | Reject theo protocol; local cleanup đúng |
| L13 | CAS SLO event | CAS client invalidates đúng local session |
| L14 | IdP/OP logout nhưng one node vẫn active | FAIL parity |
| L15 | User disabled giữa session | Enforcement đạt SLA |
| M01 | Verified MFA mới | Sensitive action ALLOW |
| M02 | MFA expired dù local session active | STEP_UP/DENY |
| M03 | OIDC `auth_time` cũ, `iat` mới | Không tự coi fresh |
| M04 | OIDC Essential ACR không đạt | Deny sensitive action |
| M05 | OIDC `max_age` nhưng ID Token thiếu auth_time | Deny/validation failure |
| M06 | `prompt=login` nhưng password-only | Không tự suy MFA |
| M07 | SAML ForceAuthn nhưng AuthnContext yếu | Không cấp sensitive authorization |
| M08 | CAS renew nhưng assurance claim thiếu | Unknown → step-up |
| M09 | Wrong issuer/tenant cùng email | Không tự share MFA/roles |
| M10 | MFA không phishing-resistant, policy yêu cầu | Deny |
| T01 | 29m59s idle với giới hạn 30 phút | Pass nếu các hạn khác hợp lệ |
| T02 | 30m00s idle | Expire |
| T03 | Reauth overall 8h, user active gần đây | Expire/reauth |
| T04 | Cookie Max-Age dài nhưng server TTL hết | Deny |
| T05 | ID Token exp nhưng app session còn | Không đồng nhất hai TTL |
| T06 | Silent refresh cấp token mới | Không reset lastMfaAt |
| T07 | Concurrent sessions vượt mức | Giới hạn đúng trên nhiều nodes |
| T08 | Session fixation trước/sau login | Session ID rotation, old ID invalid |
| T09 | Remember-me user truy cập admin | Yêu cầu fresh MFA |
| T10 | Token/API access sau logout | Theo revocation policy, không fail-open |
| C01 | Legacy sessions tồn tại lúc cutover | Force reauth hoặc bridge design approved |
| C02 | Rollback sau logout user | Session đã revoked không hồi sinh |
| C03 | Callback step-up đến muộn sau logout | Không tạo authenticated session mới |
| C04 | Cross-tenant OP logout event | Không ảnh hưởng tenant khác |
| C05 | Canary một node pass, node khác không nhận logout | NO-GO |
| C06 | Wrong ACR mapping chỉ trên mobile client | NO-GO high-risk |
| C07 | IdP unavailable khi cần step-up | Deny sensitive action, rõ lỗi |
| C08 | Positive baseline với signed assertion/token đúng | Login và permission đúng |

**Đừng chỉ assert HTTP 200/302/401.** Một failure handler có thể redirect 302, old `SecurityContext` có thể vẫn còn; cần assert **đúng subject/tenant/roles**, session registry, revocation và downstream authorization.

## 15. Java 17 độc lập: policy parity, MFA freshness và logout scope

Ví dụ sau **chạy được bằng `javac --release 17`**, không cần IdP/Spring. Nó kiểm candidate policy không yếu hơn approved policy; mô phỏng assurance evidence, session expiry và remote/local logout.

**Ranh giới quan trọng:** `VerifiedLogout.proofVerified`/`Session.evidence` là kết quả **mock verifier đáng tin trong test**, không được lấy thẳng từ HTTP request/JWT chưa verify trong production. Code không thực hiện JWT/XML signature, JWK, X.509, OAuth state/PKCE, CAS ticket validation, browser cookies, database concurrency hoặc replay cache phân tán. `HashMap`/`HashSet` không thread-safe, và ordinal `UNKNOWN < PASSWORD < VERIFIED_MFA` chỉ là bảng cấp độ **nội bộ minh họa**, không phải định nghĩa ACR chung cho mọi IdP.

Tệp **FederationPolicyMigrationDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class FederationPolicyMigrationDemo {
    static final Instant NOW = Instant.parse("2026-11-07T10:00:00Z");
    static final String ISSUER = "https://idp.example.test/realms/corp";
    static final String CLIENT = "portal-client";

    enum Assurance { UNKNOWN, PASSWORD, VERIFIED_MFA }
    enum Action { READ, TRANSFER }
    enum Verdict {
        ALLOW, NO_SESSION, WRONG_CONTEXT, IDLE_EXPIRED,
        OVERALL_EXPIRED, INSUFFICIENT_ASSURANCE,
        MFA_TOO_OLD, PHISHING_RESISTANCE_REQUIRED
    }

    record Policy(Duration idle, Duration overall,
                  Duration sensitiveMaxAge, Assurance baseline,
                  Assurance sensitive, boolean remoteLogoutRequired,
                  boolean phishingResistantForSensitive,
                  int maxConcurrentSessions) {}

    record Session(String localId, String providerSid, String issuer,
                   String client, String subject, String tenant,
                   Instant lastReauthAt, Instant lastActivityAt,
                   Instant lastMfaAt, Assurance evidence,
                   boolean phishingResistant, boolean revoked) {}

    record VerifiedLogout(String issuer, String client, String sid,
                          String sub, String jti, boolean proofVerified) {}

    static final Policy APPROVED = new Policy(Duration.ofMinutes(30),
        Duration.ofHours(8), Duration.ofMinutes(10),
        Assurance.PASSWORD, Assurance.VERIFIED_MFA, true, true, 2);

    static boolean noWeaker(Policy old, Policy candidate) {
        return candidate.idle().compareTo(Duration.ZERO) > 0
            && candidate.overall().compareTo(Duration.ZERO) > 0
            && candidate.sensitiveMaxAge().compareTo(Duration.ZERO) > 0
            && candidate.idle().compareTo(old.idle()) <= 0
            && candidate.overall().compareTo(old.overall()) <= 0
            && candidate.sensitiveMaxAge().compareTo(
                   old.sensitiveMaxAge()) <= 0
            && candidate.baseline().ordinal() >= old.baseline().ordinal()
            && candidate.sensitive().ordinal() >= old.sensitive().ordinal()
            && (!old.remoteLogoutRequired()
                || candidate.remoteLogoutRequired())
            && (!old.phishingResistantForSensitive()
                || candidate.phishingResistantForSensitive())
            && candidate.maxConcurrentSessions() >= 1
            && candidate.maxConcurrentSessions()
                <= old.maxConcurrentSessions();
    }

    static Policy changed(Duration idle, Duration overall,
            Duration mfaAge, Assurance baseline, Assurance sensitive,
            boolean remoteLogout, boolean phishingResistant,
            int maxSessions) {
        return new Policy(idle, overall, mfaAge, baseline, sensitive,
            remoteLogout, phishingResistant, maxSessions);
    }

    static Session testSession(String localId, String providerSid,
            String subject, Instant reauth, Instant activity,
            Instant mfa, Assurance evidence, boolean phishingResistant) {
        return new Session(localId, providerSid, ISSUER, CLIENT,
            subject, "tenant-A", reauth, activity, mfa, evidence,
            phishingResistant, false);
    }

    static Verdict access(Policy p, Session s, Action action,
            String issuer, String client, String tenant, Instant now) {
        if (s == null || s.revoked()) return Verdict.NO_SESSION;
        if (!issuer.equals(s.issuer()) || !client.equals(s.client())
                || !tenant.equals(s.tenant())) return Verdict.WRONG_CONTEXT;
        if (s.lastActivityAt() == null
                || !now.isBefore(s.lastActivityAt().plus(p.idle())))
            return Verdict.IDLE_EXPIRED;
        if (s.lastReauthAt() == null
                || !now.isBefore(s.lastReauthAt().plus(p.overall())))
            return Verdict.OVERALL_EXPIRED;
        Assurance needed = action == Action.TRANSFER
            ? p.sensitive() : p.baseline();
        if (s.evidence() == null
                || s.evidence().ordinal() < needed.ordinal())
            return Verdict.INSUFFICIENT_ASSURANCE;
        if (action == Action.TRANSFER) {
            if (s.lastMfaAt() == null
                    || !now.isBefore(
                        s.lastMfaAt().plus(p.sensitiveMaxAge())))
                return Verdict.MFA_TOO_OLD;
            if (p.phishingResistantForSensitive()
                    && !s.phishingResistant())
                return Verdict.PHISHING_RESISTANCE_REQUIRED;
        }
        return Verdict.ALLOW;
    }

    static final class LocalSessions {
        final Map<String, Session> sessions = new HashMap<>();
        final Set<String> seenJti = new HashSet<>();

        void add(Session s) { sessions.put(s.localId(), s); }
        boolean active(String id) {
            Session s = sessions.get(id);
            return s != null && !s.revoked();
        }
        void localLogout(String id) { sessions.remove(id); }

        int remoteLogout(VerifiedLogout e) {
            // proofVerified must come from complete trusted JWT verification!
            if (e == null || !e.proofVerified() || e.jti() == null
                    || e.jti().isBlank() || e.issuer() == null
                    || e.client() == null
                    || (e.sid() == null && e.sub() == null)
                    || !seenJti.add(e.jti())) return 0;
            int affected = 0;
            for (Session s : sessions.values()) {
                if (s.revoked() || !s.issuer().equals(e.issuer())
                        || !s.client().equals(e.client())) continue;
                boolean match = e.sid() != null
                    ? e.sid().equals(s.providerSid())
                        && (e.sub() == null || e.sub().equals(s.subject()))
                    : e.sub().equals(s.subject());
                if (match) {
                    sessions.put(s.localId(), new Session(
                        s.localId(), s.providerSid(), s.issuer(),
                        s.client(), s.subject(), s.tenant(),
                        s.lastReauthAt(), s.lastActivityAt(),
                        s.lastMfaAt(), s.evidence(),
                        s.phishingResistant(), true));
                    affected++;
                }
            }
            return affected;
        }
    }

    static void check(String name, boolean condition) {
        System.out.println(name + "=" + condition);
        if (!condition) throw new AssertionError(name);
    }

    public static void main(String[] args) {
        Policy p = APPROVED;
        check("samePolicyAccepted", noWeaker(p, p));
        check("stricterIdleAccepted", noWeaker(p, changed(
            Duration.ofMinutes(20), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, true, 2)));
        check("relaxedIdleRejected", !noWeaker(p, changed(
            Duration.ofMinutes(45), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, true, 2)));
        check("relaxedOverallRejected", !noWeaker(p, changed(
            p.idle(), Duration.ofHours(9), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, true, 2)));
        check("relaxedMfaAgeRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), Duration.ofMinutes(20),
            p.baseline(), p.sensitive(), true, true, 2)));
        check("mfaDowngradeRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), Assurance.PASSWORD, true, true, 2)));
        check("missingRemoteLogoutRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), false, true, 2)));
        check("phishingResistanceDowngradeRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, false, 2)));
        check("moreSessionsRejected", !noWeaker(p, changed(
            p.idle(), p.overall(), p.sensitiveMaxAge(),
            p.baseline(), p.sensitive(), true, true, 3)));

        Session alice = testSession("local-A", "op-sid-A", "alice",
            NOW.minusSeconds(60), NOW.minusSeconds(30),
            NOW.minusSeconds(60), Assurance.VERIFIED_MFA, true);
        check("normalAllowed",
            access(p, alice, Action.READ, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.ALLOW);
        check("freshMfaAllowed",
            access(p, alice, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.ALLOW);

        Session password = testSession("local-P", "op-sid-P", "alice",
            NOW.minusSeconds(30), NOW.minusSeconds(5), null,
            Assurance.PASSWORD, false);
        check("passwordOnlyCannotTransfer",
            access(p, password, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.INSUFFICIENT_ASSURANCE);
        Session unknown = testSession("local-U", "op-sid-U", "alice",
            NOW.minusSeconds(30), NOW.minusSeconds(5), null,
            Assurance.UNKNOWN, false);
        check("unknownAssuranceNotMfa",
            access(p, unknown, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.INSUFFICIENT_ASSURANCE);

        Session oldMfa = testSession("local-M", "op-sid-M", "alice",
            NOW.minusSeconds(20), NOW.minusSeconds(5),
            NOW.minusSeconds(601), Assurance.VERIFIED_MFA, true);
        check("oldMfaRequiresStepUp",
            access(p, oldMfa, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.MFA_TOO_OLD);
        Session notResistant = testSession("local-O", "op-sid-O", "alice",
            NOW.minusSeconds(20), NOW.minusSeconds(5),
            NOW.minusSeconds(20), Assurance.VERIFIED_MFA, false);
        check("notPhishingResistantRejected",
            access(p, notResistant, Action.TRANSFER, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.PHISHING_RESISTANCE_REQUIRED);

        Session idle = testSession("local-I", "op-sid-I", "alice",
            NOW.minusSeconds(20), NOW.minusSeconds(1800),
            NOW.minusSeconds(20), Assurance.VERIFIED_MFA, true);
        check("idleBoundaryExpired",
            access(p, idle, Action.READ, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.IDLE_EXPIRED);
        Session overall = testSession("local-H", "op-sid-H", "alice",
            NOW.minus(Duration.ofHours(9)), NOW.minusSeconds(3),
            NOW.minusSeconds(3), Assurance.VERIFIED_MFA, true);
        check("overallExpiredDespiteActivity",
            access(p, overall, Action.READ, ISSUER, CLIENT,
                "tenant-A", NOW) == Verdict.OVERALL_EXPIRED);
        check("issuerMismatchRejected",
            access(p, alice, Action.READ, "https://wrong.example.test",
                CLIENT, "tenant-A", NOW) == Verdict.WRONG_CONTEXT);
        check("tenantMismatchRejected",
            access(p, alice, Action.READ, ISSUER, CLIENT,
                "tenant-B", NOW) == Verdict.WRONG_CONTEXT);
        check("clientMismatchRejected",
            access(p, alice, Action.READ, ISSUER, "other-client",
                "tenant-A", NOW) == Verdict.WRONG_CONTEXT);

        LocalSessions registry = new LocalSessions();
        registry.add(alice);
        registry.add(testSession("local-B", "op-sid-B", "alice",
            NOW.minusSeconds(30), NOW.minusSeconds(10),
            NOW.minusSeconds(30), Assurance.VERIFIED_MFA, true));
        registry.add(testSession("local-C", "op-sid-C", "bob",
            NOW.minusSeconds(30), NOW.minusSeconds(10),
            NOW.minusSeconds(30), Assurance.VERIFIED_MFA, true));

        check("forgedLogoutRejected",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-A", null, "jti-fake", false)) == 0);
        check("forgedLogoutPreservesSession",
            registry.active("local-A"));
        check("wrongIssuerLogoutDoesNothing",
            registry.remoteLogout(new VerifiedLogout(
                "https://wrong.example.test", CLIENT,
                "op-sid-A", null, "jti-wrong-issuer", true)) == 0);
        check("wrongClientLogoutDoesNothing",
            registry.remoteLogout(new VerifiedLogout(ISSUER,
                "other-client", "op-sid-A", null,
                "jti-wrong-client", true)) == 0);
        check("sidSubMismatchDoesNothing",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-A", "bob", "jti-both", true)) == 0);
        check("sidLogoutRevokesOnlyTarget",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-A", null, "jti-sid", true)) == 1);
        check("sidLogoutLeavesOtherSession",
            registry.active("local-B"));
        check("sidLogoutLeavesOtherUser",
            registry.active("local-C"));
        check("logoutJtiReplayRejected",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-B", null, "jti-sid", true)) == 0);
        check("subjectLogoutRevokesRemainingAlice",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                null, "alice", "jti-sub", true)) == 1);
        check("subjectLogoutLeavesBobActive",
            registry.active("local-C"));
        registry.localLogout("local-C");
        check("localLogoutClearsOwnSession",
            !registry.active("local-C"));
        check("localLogoutIsNotGlobalLogout",
            registry.remoteLogout(new VerifiedLogout(ISSUER, CLIENT,
                "op-sid-C", null, "jti-local", true)) == 0);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 FederationPolicyMigrationDemo.java
java FederationPolicyMigrationDemo
~~~

**Stdout mong đợi sau khi compile/run:**

~~~text
samePolicyAccepted=true
stricterIdleAccepted=true
relaxedIdleRejected=true
relaxedOverallRejected=true
relaxedMfaAgeRejected=true
mfaDowngradeRejected=true
missingRemoteLogoutRejected=true
phishingResistanceDowngradeRejected=true
moreSessionsRejected=true
normalAllowed=true
freshMfaAllowed=true
passwordOnlyCannotTransfer=true
unknownAssuranceNotMfa=true
oldMfaRequiresStepUp=true
notPhishingResistantRejected=true
idleBoundaryExpired=true
overallExpiredDespiteActivity=true
issuerMismatchRejected=true
tenantMismatchRejected=true
clientMismatchRejected=true
forgedLogoutRejected=true
forgedLogoutPreservesSession=true
wrongIssuerLogoutDoesNothing=true
wrongClientLogoutDoesNothing=true
sidSubMismatchDoesNothing=true
sidLogoutRevokesOnlyTarget=true
sidLogoutLeavesOtherSession=true
sidLogoutLeavesOtherUser=true
logoutJtiReplayRejected=true
subjectLogoutRevokesRemainingAlice=true
subjectLogoutLeavesBobActive=true
localLogoutClearsOwnSession=true
localLogoutIsNotGlobalLogout=true
~~~

### 15.1. Giải thích ý nghĩa

- Policy gate từ chối nới idle/overall/MFA max age/concurrent sessions và bỏ remote logout/phishing resistance.
- Valid user được phép READ/TRANSFER khi đủ proof. Password-only hoặc unknown assurance không cấp privileged action.
- User active vẫn hết overall timeout; action nhạy cảm vẫn cần MFA còn mới.
- Logout Token giả/sai issuer/sai client không hủy session; sid+sub mâu thuẫn không logout nhầm Bob.
- `sid` logout chỉ hủy một OP session; `sub` logout các sessions liên quan user/client/issuer.
- Event `jti` lặp lại không gây thêm tác động; local logout một phiên không tự tuyên bố đã kết thúc toàn bộ IdP SSO.

Demo **không thay thế** Spring Security real OIDC Logout Token verifier, SAML SLO, CAS client, business policy engine hay distributed session registry.

## 16. Phương án rollout theo pha

**P0 — Baseline:** thu chính sách cũ thật, các endpoints, issuer/tenants, sessions, MFA settings, logout propagation, SLA revoke, business owners. Chốt policy-parity matrix có chữ ký security owner.

**P1 — Mapping:** định nghĩa trusted assurance adapter theo từng protocol; timeout source of truth; local vs global logout endpoints; OIDC/SAML/CAS callback verifiers. Không để unknown ACR trở thành MFA.

**P2 — Dual-run trong test/canary:** chạy cùng hành trình user ở legacy/candidate, so verdict ALLOW/DENY/STEP_UP/LOGOUT và local session state. Dùng frozen clock, synthetic IdP, signed fixtures, browser hai tabs, multi-node/Redis và risk-appropriate negative tests.

**P3 — Cutover:** chuyển theo client/tenant/role có kiểm soát, không random route mỗi request của một browser qua hai stacks. Prefer **invalidate legacy sessions và yêu cầu đăng nhập lại** thay vì import assurance/roles bằng email. Nếu buộc bridge, phải có explicit signed design, TTL ngắn và approval. Monitor logout event latency, forced reauth, MFA step-up success, unknown ACR và customer impact.

**P4 — Stabilize/retire:** chờ các legacy sessions/tokens được revoke hoặc hết hạn theo plan, tắt old callbacks/keys có kiểm soát, lưu test evidence, close change và cập nhật runbook. **Rollback không được làm sống lại session đã revoked/logout**.

## 17. GO/NO-GO trước khi chuyển traffic

**GO** khi policy matrix được duyệt và các bằng chứng sau đều đạt:

- Logout local/upstream/IdP-initiated đúng scope, callback được verify và session thực sự bị xóa ở mọi nodes.
- Sensitive endpoints bắt buộc trusted MFA assurance, freshness và phishing resistance theo policy.
- Idle/overall/hard cap/MFA freshness/concurrency không lỏng hơn baseline; boundaries đã kiểm.
- Một user/account/tenant không thể dùng claim/logout event của issuer/client khác.
- Disabled user/revoked account/token bị từ chối theo SLA.
- Signed OIDC/SAML/CAS integrations thực pass positive and negative tests.
- Có canary/metrics/log redaction, support escalation, rollback strategy.
- Test old cookies/sessions/tokens không tạo backdoor.

**NO-GO** nếu phát hiện:

- Chỉ hỗ trợ local logout trong khi legacy bắt buộc global logout.
- OIDC Logout Token không validate signature/iss/aud/events/jti.
- SAML SLO không kiểm issuer/SessionIndex hoặc logout nhầm user.
- Bằng chứng MFA unknown/expired mà privileged action vẫn thành công.
- `iat` token bị dùng thay `auth_time` khi yêu cầu fresh auth.
- Idle time tăng lên, overall timeout bị loại bỏ, remember-me bypass MFA.
- Một Spring replica thiếu session registry hoặc back-channel handler.
- Rollback resurrect session cũ, logout callback bị mất mà không alert.

Các thay đổi policy có chủ ý phải được ghi **approved risk exception**, không gắn nhãn parity PASS.

## 18. Quan sát lỗi và runbook

| Triệu chứng | Khả năng | Cách kiểm |
| --- | --- | --- |
| Logout app rồi SSO lại ngay | IdP session còn | Local-only hay global contract? |
| OP logout 200 nhưng old cookie còn dùng | Wrong session cookie/registry mapping | `JSESSIONID` vs `SESSION`, Redis invalidation |
| SAML SLO hủy user khác | Scope NameID/SessionIndex sai | Signed LogoutRequest + mapped session |
| CAS SLO không tới app | Callback/client registry | CAS delivery logs/connection |
| Step-up loop | OP không support acr/claims hoặc session state lost | ID Token auth_time/acr, state/nonce |
| MFA bypass sau migration | Unknown ACR được tin hoặc dùng iat | Approved mapping and timestamps |
| Local session không hết hạn | Timer chỉ reset/lưu sai | lastActivityAt vs lastReauthAt |
| User revoked vẫn truy cập API | Bearer token còn valid | API revocation/introspection controls |
| Error chỉ ở một node | Session store/config drift | Replica policy version and store |
| Logout rồi session tự sống lại | Race/stale cache, rollback | Atomic revoke/versioned sessions |
| Tăng 403 sau cutover | Roles vs MFA vs local user status | Separate authorization reason codes |

Log/metrics chỉ dùng **policy version, registration alias, event type, reason category, elapsed time và pseudonymous correlation ID**. Không log raw Logout Token, ID Token, SAMLResponse, Service Ticket, NameID/email, session cookie, MFA secrets. Có thể theo dõi:

~~~text
federation_logout_event_validated_total
federation_logout_session_invalidation_total
federation_remote_logout_failed_total
federation_stepup_required_total
federation_unknown_assurance_denied_total
federation_session_idle_expired_total
federation_session_overall_expired_total
federation_policy_parity_regression_total
~~~

**Runbook:** xác định protocol/issuer/client và local sessions → chọn event đầu tiên → verify source and mapping → xem SecurityContext/session store → đối chiếu MFA/time policy → thử old cookie/token ở protected endpoint → fix đúng nơi → chạy positive+negative+multi-node tests → security owner sign-off.

## 19. Checklist hoàn thành

- [ ] Policy logout/MFA/timeout legacy và candidate đã có owner và approved baseline.
- [ ] Local logout POST+CSRF xóa session/SecurityContext đúng.
- [ ] OP/SAML/CAS SLO đúng giao thức, không chỉ redirect UI.
- [ ] OIDC back-channel `sid`/`sub`/`iss`/`aud`/`jti`/signature validation đầy đủ.
- [ ] Session cookie `JSESSIONID`/`SESSION` tương thích handler và Spring Session.
- [ ] SAML SessionIndex/NameID/issuer được ràng buộc vào đúng local session.
- [ ] CAS SLO notification được xử lý với Service Ticket-to-session mapping.
- [ ] Admin revocation/disabled user/token deny đạt SLA.
- [ ] OIDC ACR/AMR/auth_time mappings được IdP/security owner phê duyệt.
- [ ] SAML ForceAuthn/RequestedAuthnContext được kiểm bằng AuthnContext/AuthnInstant đầu ra.
- [ ] `prompt=login`, `max_age` và CAS renew không bị coi tự động là MFA.
- [ ] Unknown assurance không được nâng lên MFA.
- [ ] MFA freshness chỉ reset sau trusted fresh MFA.
- [ ] Phishing resistance được xác minh khi policy yêu cầu.
- [ ] Idle timer và overall reauth timer hoạt động độc lập; hard cap riêng nếu có.
- [ ] Cookie Max-Age, ID Token exp, SAML assertion TTL không bị nhầm local session TTL.
- [ ] Session fixation protection, concurrent sessions, remember-me và multiple nodes đúng.
- [ ] Pending step-up callback sau logout không thể tạo lại session.
- [ ] External account key dùng trusted issuer/client/tenant/subject, không chỉ email.
- [ ] Legacy session/roles/MFA evidence không được tự động copy sang login mới.
- [ ] Rollback không phục hồi revoked sessions hoặc trusted access token cũ.
- [ ] Positive tests, negative tests, exact boundary tests và integration tests đều đạt.
- [ ] Không có credentials/PII trong logs, session IDs không bị lộ qua URLs.
- [ ] Có Go/No-Go gate, rollback, observability và post-cutover ownership.

## 20. Câu hỏi tự kiểm tra

**1. Local logout có luôn kết thúc IdP session không?** Không. Local session và upstream SSO session là hai vòng đời.

**2. ID Token `exp` có là deadline local HttpSession không?** Không mặc định; token validity khác local session timeout.

**3. `auth_time` khác `iat` thế nào?** `auth_time` là khi user thực sự xác thực tại OP; `iat` là khi token được phát, có thể mới hơn nhiều.

**4. `prompt=login` hoặc SAML ForceAuthn có chắc là MFA?** Không. Chỉ có fresh authentication theo semantics của protocol; cần kiểm assurance class kết quả.

**5. OIDC Logout Token `sid` nhắm gì?** Một OP session; còn `sub` có thể nhắm mọi sessions của user trong đúng issuer/client theo profile.

**6. Vì sao local cookie `SESSION` quan trọng với OIDC back-channel?** Spring default thường dùng `JSESSIONID`; nếu tên khác mà không cấu hình đúng, mapping/invalidation có thể không hoạt động.

**7. CAS SLO giống SAML2 SLO không?** Không. CAS protocol có ticket-to-session notifications; SAML có signed LogoutRequest/Response và SessionIndex.

**8. User rất active nhưng overall reauth hết hạn có tiếp tục được không?** Không nếu policy yêu cầu reauth; activity chỉ reset idle.

**9. Có thể giữ lastMfaAt từ legacy session khi email giống new OIDC user không?** Không tự động; phải xác minh trusted subject/issuer/tenant và proof mới theo policy.

**10. NIST SP800-63B-4 cho AAL2 bao nhiêu?** Guidance SHOULD overall không quá 24h và idle không quá 1h; không tự nới policy doanh nghiệp chặt hơn.

**11. Test logout callback trả 200 có đủ không?** Không. Phải thử old cookies và local session state ở protected endpoints, trên nhiều nodes.

**12. Bản migration có LOGIN PASS nhưng remote logout/MFA FAIL có được cutover không?** Không nếu các policy này là critical requirement chưa có approved deviation.

## 21. Nguồn chính thức

- Spring Security **Servlet Logout**: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security **OIDC Logout, RP/Back-Channel, cookie name**: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security **SAML2 Single Logout**: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security **Session Management / fixation / concurrency**: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security **OAuth2 Authorization Request Customization**: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- Spring Security **SAML AuthnRequest ForceAuthn customization**: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- **OpenID Connect Core 1.0** (acr, amr, max_age, auth_time, essential ACR): https://openid.net/specs/openid-connect-core-1_0.html
- **OpenID Connect Back-Channel Logout 1.0** (Logout Token validation): https://openid.net/specs/openid-connect-backchannel-1_0.html
- **OpenID Connect RP-Initiated Logout 1.0**: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- **NIST SP 800-63B-4 Session Management (2025)**: https://pages.nist.gov/800-63-4/sp800-63b/session/
- **NIST SP 800-63B-4 Authentication Assurance Levels**: https://pages.nist.gov/800-63-4/sp800-63b/aal/
- **OASIS SAML 2.0 Core** (AuthnContext/AuthnInstant/SessionIndex): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- **OASIS SAML 2.0 Profiles** (SLO): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- **Apereo CAS 8.0 Single Logout**: https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html
- **OWASP Session Management Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- **OWASP Authentication Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

**Kết luận:** trước khi chuyển đổi Spring Security federation, phải đối chiếu **phạm vi logout và revocation**, **MFA/step-up với proof đáng tin và còn mới**, **idle/overall/hard-cap/concurrent-session limits**. Không nhầm IdP SSO session, local HttpSession, token expiry và MFA freshness. Chỉ chuyển traffic khi ma trận policy đã duyệt, signed protocol flows, boundary tests, multi-node invalidation và rollback không phục hồi phiên đã bị thu hồi.