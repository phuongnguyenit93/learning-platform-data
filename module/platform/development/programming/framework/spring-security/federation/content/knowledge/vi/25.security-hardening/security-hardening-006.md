# Nhầm lẫn IdP, issuer hoặc tenant khi chọn cấu hình xác minh

**Khi Spring Security hỗ trợ nhiều Identity Provider (IdP), nhiều issuer hoặc nhiều tenant, việc chọn nhầm cấu hình xác minh có thể trở thành lỗ hổng chiếm tài khoản hoặc vượt quyền xuyên tenant.** Chữ ký token đúng không đủ: phải đúng **nhà phát hành**, đúng **khóa gắn với nhà phát hành**, đúng **người nhận/audience**, đúng **giao dịch đăng nhập**, đúng **thời gian**, đúng **loại token** và **tenant mà người dùng thực sự được cấp phép**.

**Ví dụ:** một công ty dùng OIDC issuer Corp và Partner, cùng SAML IdP Enterprise. Người dùng `alex` của Partner gửi token đã ký hợp lệ bằng khóa Partner đến endpoint dành cho Corp. Nếu backend tra người dùng chỉ bằng username, chọn JWKS tự động từ `iss` chưa xác minh hoặc map group `admins` từ Partner sang quyền Corp, đó là **issuer/IdP confusion** và có thể dẫn tới **account takeover**. Nếu backend dựa vào `tenant=south` do browser truyền để xác định luôn quyền, đó là **tenant confusion**.

**Quy tắc xuyên suốt:** định nghĩa **tập cấu hình tin cậy do server quản lý**; dữ liệu `iss`, SAML `Issuer`, `kid`, registrationId/path hoặc tenant slug đến từ request **chỉ có thể là gợi ý tìm ứng viên trong tập đó**, không phải bằng chứng đáng tin. Sau khi chọn ứng viên, phải chạy **validator đúng giao thức và đúng registration**; chỉ sau xác minh mới liên kết identity vào local account và xét quyền tenant/resource.

Bài thuộc **Spring Security – federation → Gia cố an toàn**, đi sâu vào OIDC/OAuth mix-up, JWT issuer/key confusion, SAML IdP/ACS/audience confusion, Spring Security đa issuer/đa RelyingPartyRegistration, quy trình cho phép IdP mới, kỹ thuật kiểm thử và một chương trình Java 17 độc lập.

## 1. Tại sao đây là lỗi bảo mật thực sự?

Một ứng dụng SaaS có hai tenant và hai nguồn identity:

~~~text
User/Browser
      |
      | Chọn đăng nhập /t/north hoặc /t/south
      v
  Spring Application
      |
      +---- OIDC Corp:    issuer = https://id.corp.test/realm/staff
      |
      +---- OIDC Partner: issuer = https://id.partner.test/realm/client
      |
      +---- SAML Enterprise:
             IdP entityID = urn:enterprise:idp
      |
      v
 Verified identity -> Local account -> Tenant membership
      |
      v
 Protected API and object-level authorization
~~~

Hai IdP có thể cùng phát `sub=123`, `email=alex@example.test` hoặc `groups=["admin"]`. Chúng **không tự tuyên bố cùng một người**. Tương tự, token có issuer Corp nhưng `aud=payroll-api` không được Billing nhận. Một SAML Assertion ký bởi Enterprise nhưng `AudienceRestriction` dành cho ứng dụng khác không được chấp nhận ở Portal.

Vì thế cần bảo vệ **cả ba biên giới**: nguồn danh tính (issuer/IdP), điểm nhận (SP/client/API audience) và quyền trên tenant/tài nguyên.

## 2. Các khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa | Không được nhầm với |
| --- | --- | --- |
| **IdP** | Hệ thống xác thực người dùng và phát bằng chứng (ví dụ SAML/ OIDC) | Tenant hoặc email domain |
| **OIDC issuer / OAuth AS issuer** | Định danh URL của issuer/Authorization Server, dùng trong `iss` | Hostname của gateway |
| **SAML IdP entityID** | Định danh asserting party trong trusted SAML metadata | Spring registrationId |
| **Spring ClientRegistration.registrationId** | Khóa cấu hình OAuth/OIDC client nội bộ | Issuer hoặc tenant ID |
| **RelyingPartyRegistration.registrationId** | Khóa cấu hình SAML RP↔IdP nội bộ | IdP entityID |
| **SAML SP entityID** | Định danh Service Provider nhận Assertion | IdP entityID |
| **Tenant** | Ranh giới tổ chức, dữ liệu và chính sách của ứng dụng | Issuer hoặc subdomain |
| **Subject** | `sub` OIDC hoặc NameID/stable attribute SAML trong phạm vi IdP | Email/username toàn cục |
| **Audience** | Bên được nhận token/assertion | Người dùng đăng nhập |
| **Key ID (kid)** | Hint chọn khóa trong một bộ khóa đã tin | Trust anchor độc lập |
| **JWKS / certificate metadata** | Khóa xác minh được đăng ký/kiểm soát | URL có thể lấy tùy ý từ token |

Quan hệ không phải luôn 1–1: một tenant có thể tin **nhiều IdPs**; một issuer có thể hỗ trợ **nhiều tenants**; một IdP có thể có **nhiều registrations** cho các ứng dụng. Không hardcode `issuer == tenant` trong mọi tình huống.

## 3. Authentication, verifier selection và authorization là ba bước

**Routing/candidate selection:** ứng dụng cần biết nên dùng registration/decoder nào. Chọn được một candidate **chưa có nghĩa token đã tin cậy**.

**Authentication/protocol verification:** dùng verifier của candidate để kiểm signature, issuer, audience, thời gian, replay, nonce hoặc InResponseTo và recipient.

**Authorization:** quyết định verified subject có quyền vào tenant/tài nguyên này không. Một user có thể được IdP xác thực thành công nhưng không có quyền vào tenant yêu cầu.

~~~text
HTTP request / browser callback (UNTRUSTED)
      |
      v
Select only from trusted registrations
      | Unknown/ambiguous -> REJECT
      v
Exact protocol verifier
      | Signature + issuer + audience + time
      | State/nonce/recipient/InResponseTo + replay controls
      | Failure -> REJECT
      v
Verified (protocol, issuer/IdP, subject, actor)
      |
      v
Local account linking, account active state
      |
      v
Tenant membership + action/resource authorization
      |
      v
ALLOW or DENY
~~~

**Sai:** chọn key theo bất kỳ `iss` nào token tự khai báo, sau đó chỉ kiểm chữ ký. **Đúng:** chọn candidate từ trusted allowlist và buộc kết quả xác minh khớp đầy đủ với expected registration.

## 4. Nhóm tấn công và sai cấu hình điển hình

| Loại lỗi | Cách xảy ra | Hệ quả |
| --- | --- | --- |
| IdP confusion | Token/Assertion B được nhận ở flow A | Nhận sai user/trust context |
| OAuth AS mix-up | Callback không biết code thuộc Authorization Server nào | Có thể lộ authorization code/token |
| Issuer confusion | JWT có `iss` sai hoặc arbitrary issuer được auto-trust | Token attacker tự ký được nhận |
| Key confusion | Global `kid` map không gắn issuer | Key B được dùng để nhận claims A |
| Algorithm confusion | Parser tin `alg` do token chọn, không kiểm policy | Signature validation yếu/bypass |
| SAML registration confusion | Chọn RelyingPartyRegistration bằng XML Issuer rồi coi là proof | Nhận Assertion sai recipient/tenant |
| Audience confusion | Token ký đúng nhưng dành cho API khác | Confused deputy |
| Tenant confusion | Tin tenant slug/header như membership | Cross-tenant data exposure |
| Principal collision | Dùng email/sub/NameID không namespace | Account takeover |
| Role collision | Group admin của B thành ROLE_ADMIN của A | Privilege escalation |
| Replay confusion | Không đối chiếu state/nonce/InResponseTo hoặc assertion ID | Session fixation/replay |
| Stale trust | IdP đã thu hồi nhưng decoder/session vẫn accept | Quyền tiếp tục tồn tại ngoài policy |

**Threat modeling:** đánh dấu rõ input nào attacker có thể sửa: URL, query, Host, forwarded headers, `iss`, `kid`, `jku`, XML Issuer, email, tenant ID, group names và callback parameters. Tất cả đều phải có trust boundary.

## 5. JWT issuer chưa verify chỉ là một gợi ý

JWT có thể chứa:

~~~json
{
  "header": {
    "alg": "RS256",
    "kid": "key1",
    "jku": "https://untrusted.test/keys"
  },
  "payload": {
    "iss": "https://untrusted.test",
    "sub": "admin",
    "aud": ["billing-api"],
    "tenant": "north"
  }
}
~~~

Đây là **một minh họa hai phần của JWT**, không phải JWT compact hợp lệ. Cả `header` và `payload` đều là dữ liệu **chưa xác minh** trước khi decoder kiểm chữ ký.

**Không làm:**

~~~java
// PSEUDOCODE KHÔNG AN TOÀN; không phải mã chạy được.
String issuerFromUnverifiedJwt = parseWithoutVerifying(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(
        issuerFromUnverifiedJwt);
Jwt authentication = decoder.decode(token);
~~~

Nếu issuer URL do attacker kiểm soát, decoder có thể truy cập JWKS của attacker, và token tự ký sẽ hợp lệ **với bộ khóa của attacker**. Điều đó không có nghĩa backend có quyền tin attacker là IdP.

**Thay thế:** mapping từ trusted issuer exact string sang AuthenticationManager hoặc JwtDecoder đã được chủ sở hữu bảo mật phê duyệt. `iss` chưa verify chỉ giúp lookup **trong tập đó**; sau khi verify phải kiểm exact issuer.

## 6. Spring Security: JwtIssuerAuthenticationManagerResolver an toàn

Tài liệu Spring Security cho Resource Server đa issuer cung cấp `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)`.

Ví dụ dành cho **Spring Security Servlet trong dự án Spring Boot**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        JwtIssuerAuthenticationManagerResolver trustedIssuers =
            JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://id.corp.test/realm/staff",
                "https://id.partner.test/realm/client"
            );

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .authenticationManagerResolver(trustedIssuers))
            .build();
    }
}
~~~

**Lưu ý tích hợp:** cấu hình thuộc dự án Spring Security/OAuth2 Resource Server, **không chạy bằng `javac` thuần JDK**; cần thư viện, Authorization Servers, trusted metadata/JWKS, chính sách endpoint và các SecurityFilterChains khác. Spring có thể tạo provider cho một issuer được phê duyệt khi issuer đó phát sinh request lần đầu.

**Không biến fromTrustedIssuers thành tự nhận mọi issuer** bằng cách tự thêm mọi `iss` có trong JWT vào danh sách trusted. Dynamic tenant management phải là **quy trình quản trị tin cậy**, không phải self-enrollment từ user input.

## 7. Một issuer hợp lệ chưa đủ: audience và token purpose

Giả sử token do Corp phát:

~~~text
iss = https://id.corp.test/realm/staff
aud = payroll-api
sub = employee-82
scope = payroll.read
~~~

Billing API cũng tin issuer Corp, nhưng **không được chấp nhận** token này vì audience không chứa `billing-api`.

Resource Server kiểm ít nhất:

1. JWT signature và trusted algorithm/key.
2. `iss` chính xác.
3. `aud` thuộc các resource IDs được chấp nhận cho API.
4. `exp` và `nbf`, clock skew theo profile.
5. Token **purpose/type**: access token chứ không phải ID Token hoặc một JWT nội bộ khác.
6. Client/actor identity nếu API có chính sách client-specific.
7. Scope/permissions theo app contract.
8. Tenant membership, account active, resource ownership.

**Lưu ý:** `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers` xử lý **issuer selection**; khi tự lắp ghép managers/decoders, **vẫn phải cấu hình audience và purpose validators cho từng issuer**. Không giả định properties của mô hình single issuer luôn được áp vào managers tùy biến.

## 8. Ví dụ audience validator trong Spring

Một `JwtDecoder` chỉ nên được cấu hình từ nguồn issuer đã tin. Mảnh Java minh họa **nằm trong @Configuration**, với imports Spring OAuth2 tương ứng:

~~~java
// trustedIssuer là literal/config đã qua approval, không lấy
// trực tiếp từ token chưa verify hoặc query parameter.
NimbusJwtDecoder decoder = JwtDecoders
        .fromIssuerLocation(trustedIssuer) instanceof NimbusJwtDecoder n
        ? n : null;

if (decoder == null) {
    throw new IllegalStateException("Unexpected JwtDecoder type");
}

OAuth2TokenValidator<Jwt> issuerAndDefaults =
        JwtValidators.createDefaultWithIssuer(trustedIssuer);

OAuth2TokenValidator<Jwt> requiredAudience = jwt ->
        jwt.getAudience().contains("billing-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndDefaults, requiredAudience));
~~~

**Đây là fragment**, không phải class độc lập. Phụ thuộc version; cách đơn giản hơn là tạo `JwtDecoder` từ cấu hình trusted JWK URL và cấu hình validators rõ. Mục tiêu là **không mất các checks mặc định** khi thêm một check tùy biến. Nếu có nhiều issuers và AS key sets khác nhau, tạo per-issuer decoder từ registry tin cậy, không chuyển toàn bộ vào một global key pool.

**Token type** (chẳng hạn JWT access token theo RFC 9068) cũng phải kiểm theo contract, không chỉ issuer/audience.

## 9. kid và jku: khác biệt giữa key hint và trust anchor

JWT header có thể chứa `kid` để chọn một khóa trong JWKS đã biết. Nhưng:

- `kid` **không globally unique**. IdP Corp và Partner có thể đều dùng `kid=key1`.
- `jku` hoặc `x5u` do token cung cấp **không tự được tin** là nơi tải key.
- `alg` do JWT header công bố phải **nằm trong approved algorithms**, không được tự làm giảm mức bảo mật.
- Nếu ứng dụng lookup key trong một global map `kid → public key`, có thể dùng nhầm key của issuer khác.
- Nếu ứng dụng fetch arbitrary URLs, có nguy cơ **SSRF**, DNS rebinding và key substitution.
- Metadata/JWKS có thể được cache nhưng key cache phải gắn issuer/registration/source trust context.

**Mẫu đúng:** `(trusted_issuer, trusted_metadata_version, kid) → candidate public key`; kiểm chữ ký và chính sách thuật toán, sau đó kiểm claims `iss/aud/exp/type`. Không mở trust bằng cách tải JWKS trực tiếp từ URL do token đề xuất.

## 10. OAuth Authorization Server mix-up xuất hiện trước ID Token validation

Khi OAuth/OIDC client làm việc với nhiều Authorization Servers, user có thể chọn AS A nhưng callback bị xử lý như thể code của AS B. Nếu client **gửi authorization code tới token endpoint sai**, bí mật có thể bị tiết lộ **trước khi bước kiểm ID Token xảy ra**.

~~~text
Browser            OAuth Client             AS Legit          AS Malicious
   |                    |                       |                  |
   |--- choose A ------>|                       |                  |
   |                    |---- auth request A -->|                  |
   |<------------------- redirect code+state --|                  |
   |--- callback ------>|                       |                  |
   |                    |----- WRONG exchange -------------------->|
   |                    |                               code leaked
~~~

**RFC 9700 (OAuth 2.0 Security BCP)** yêu cầu khách hàng có nhiều AS phải có biện pháp phòng chống mix-up. **RFC 9207** mô tả `iss` trong authorization response để client so với issuer đã lưu khi khởi tạo.

**Không suy rằng dùng PKCE tự động miễn tất cả mix-up protections.** PKCE bảo vệ authorization code trong những điều kiện nhất định, nhưng client vẫn phải bảo đảm không gửi code/credentials tới AS sai.

## 11. Ràng buộc OAuth callback bằng state và issuer

Khi khởi tạo đăng nhập, lưu giao dịch **server-side** hoặc trong cơ chế request repository an toàn:

~~~text
transaction:
  registrationId         = corp-oidc
  expectedIssuer         = https://id.corp.test/realm/staff
  expectedClientId       = portal-corp
  expectedTokenEndpoint  = trusted AS token endpoint
  redirectUri            = exact callback URI
  state                  = random, one-time, session-bound
  pkceCodeVerifier       = secret for this request
  nonce                  = random when required by OIDC flow
  expiresAt              = short lifetime
~~~

Ở callback:

1. Xác nhận `state` còn tồn tại, one-time, gắn đúng browser context.
2. Xác nhận callback route/registrationId khớp expected registration.
3. Nếu authorization response có `iss` (RFC 9207), kiểm khớp **expected issuer** trước khi token exchange.
4. Nếu sử dụng countermeasure khác theo RFC 9700, ví dụ distinct redirect URIs, phải kiểm chính xác mapping theo AS; không tự bỏ mix-up defense.
5. Trao code **chỉ ở token endpoint đã đăng ký**, áp client authentication/PKCE theo flow.
6. Verify ID Token của đúng issuer/client: signature, `iss`, `aud`, `azp` khi cần, `exp`, `nonce`/`auth_time` theo profile.
7. Link user bằng verified `(iss,sub)`, không bằng user-supplied email lúc bắt đầu.
8. Kiểm tenant/resource authorization sau authentication.

**Lưu ý:** `state`/`nonce`/PKCE có chức năng khác nhau; hãy dùng framework đúng release thay vì tự viết callback nếu không cần.

## 12. OIDC issuer phải khớp chính xác, không chỉ cùng host

Ví dụ:

~~~text
Expected: https://login.example.test/realm/north
Actual:   https://login.example.test/realm/south
=> REJECT

Expected: https://login.example.test/realm/north
Actual:   https://login.example.test
=> REJECT

Expected: https://login.example.test/realm/north
Actual:   https://evil-login.example.test/realm/north
=> REJECT
~~~

Không cắt path, lấy email domain, bỏ trailing slash tùy tiện hoặc kiểm `startsWith("https://login.example.test")`. Giá trị `iss` phải khớp issuer được công bố theo profile/metadata và contract của OP.

**Một issuer có thể phục vụ nhiều tenants**, nên issuer đúng **không tự xác nhận user thuộc tenant đã yêu cầu**.

## 13. OIDC ID Token khác API Access Token

OIDC **ID Token** được phát để client/Relying Party biết user đã đăng nhập; OAuth2 **Access Token** dành cho Resource Server. Hai loại có thể là JWT nhưng khác audience, claims và mục đích.

| Thuộc tính | ID Token | JWT Access Token |
| --- | --- | --- |
| Người nhận chính | OIDC client, `aud=client_id` | Resource Server, `aud=api/resource` |
| Mục đích | Xác thực user cho RP | Ủy quyền truy cập API |
| Issuer validation | Bắt buộc theo OP registration | Bắt buộc theo AS trust |
| Nonce | Kiểm theo OIDC flow khi yêu cầu | Không là mặc định của API Bearer |
| Scope | Không biến ID Token thành quyền API | Access-token scopes dùng với resource policy |
| Token type | ID Token | Access token profile/purpose |

**Không chấp nhận ID Token ở API** chỉ vì nó được cùng IdP ký. Với JWT access token theo RFC 9068, áp kiểm `typ`/token profile nếu hệ cung cấp.

## 14. SAML: các định danh khác nhau

Trong SAML2:

| Tên | Ý nghĩa |
| --- | --- |
| **IdP entityID** | Issuer của asserting party được đăng ký tin cậy |
| **SP entityID** | Relying Party được Assertion nhắm tới |
| **registrationId** | Khóa nội bộ của Spring Security cho một registration |
| **ACS endpoint** | Assertion Consumer Service nhận POST SAMLResponse |
| **Response/Assertion Issuer** | Claim về bên phát, phải kiểm đúng theo metadata |
| **AudienceRestriction** | SP entityID mà Assertion cho phép nhận |
| **Destination/Recipient** | Endpoint mà SAMLResponse hoặc SubjectConfirmation hướng tới |
| **InResponseTo** | Liên kết AuthnRequest của SP đã phát |
| **NameID** | Danh tính user theo một format trong phạm vi IdP |
| **Signing credentials** | Keys/certs tin cậy của đúng IdP registration |

**Spring registrationId không phải IdP entityID**. Cấu hình SAML còn chứa verification certificates, entityID, ACS, metadata, decryption keys và trust.

## 15. SAML authentication và chọn RelyingPartyRegistration

Tài liệu Spring Security SAML2 Login mô tả `Saml2WebSsoAuthenticationFilter` tạo `Saml2AuthenticationToken` thông qua AuthenticationConverter, trong đó resolved `RelyingPartyRegistration` được đưa đến OpenSAML provider.

Candidate registration có thể được chọn từ:

- registrationId trong URL ví dụ `/login/saml2/sso/corp`;
- AuthnRequest đã lưu trong SP-initiated flow;
- SAML Response `Issuer` nếu phù hợp và được dùng để lookup một registration đã tin.

**Quan trọng:** `Issuer` ban đầu là untrusted XML; có thể dùng để chọn **candidate**, chứ **không phải bằng chứng chữ ký hợp lệ**. Sau khi chọn registration, provider phải kiểm signature, expected issuer, Destination, AudienceRestriction, Recipient, assertion Conditions và các checks tương ứng.

~~~text
POST /login/saml2/sso/corp + SAMLResponse
          |
     Candidate registration "corp"
          |
     Verify against Corp IdP credentials only
          |
     Check Response/Assertion Issuer
     Check Destination/ACS and Recipient
     Check AudienceRestriction equals configured SP entityID
     Check time, conditions, subject confirmation
     Correlate InResponseTo to stored AuthnRequest
     Reject replayed assertion IDs
          |
     Verified (IdP entityID, subject)
          |
     Map local account + requested tenant
~~~

**Không thử lần lượt mọi certificates của mọi IdP rồi lấy user từ assertion ký đúng bất kỳ key nào.** Kể cả shared signing key trong hai registrations cũng không cho phép bỏ issuer/audience/tenant restrictions.

## 16. Ví dụ nhiều SAML registrations trong Spring Boot

Đây là ví dụ cấu hình cho một ứng dụng **Spring Boot có thư viện SAML2 Service Provider**, không phải chương trình độc lập:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "https://idp.corp.test/saml/metadata"
          partner:
            assertingparty:
              metadata-uri: "https://idp.partner.test/saml/metadata"
~~~

**Cần bổ sung thực tế:** IdP metadata endpoints đáng tin, SP registration, entityID/ACS, SSO profiles, cert rotation, IdP allowlist và reverse-proxy public origin. Các Spring Boot/Security versions có property/API khác biệt; test trên BOM sử dụng.

**Không nhận metadata-uri do browser truyền rồi bật registration ngay.** Việc thêm IdP phải qua phê duyệt trust/configuration, chống SSRF và identity link collision.

## 17. SAML SP-initiated phải ràng buộc request và response

~~~text
1. Browser chọn login Corp.
2. SP lưu expected RelyingPartyRegistration=corp.
3. SP phát AuthnRequest ID=REQ-42 tới Corp IdP.
4. Corp authenticate user và gửi SAMLResponse về ACS.
5. SP đối chiếu InResponseTo=REQ-42 với outbound request.
6. SP xác minh signed Response/Assertion, Issuer, Audience, Recipient.
7. SP kiểm time/SubjectConfirmation và replay ID.
8. SP tạo Authentication mang IdP context đã xác minh.
~~~

Nếu response của Partner đến trong flow Corp, không được tự chuyển sang Partner registration chỉ vì phần XML có `Issuer=Partner` rồi bỏ qua request correlation.

**IdP-initiated/unsolicited SAML** không có AuthnRequest trước để correlate. Nếu business cho phép, cần policy rất rõ: exact IdP trust, audience/recipient, time, replay, login-CSRF protection và tenant mapping. Không tự bỏ qua signature hoặc destination vì không có InResponseTo.

## 18. Những kiểm tra SAML không thể lược bỏ

- **Signature:** dùng đúng trusted IdP verification credentials; phân biệt Response và Assertion signatures theo profile.
- **Issuer:** Response/Assertion claims phải khớp asserting party registration đúng.
- **Destination:** Response phải hướng tới URL mà RP chấp nhận.
- **AudienceRestriction:** Assertion phải dành cho SP entityID được cấu hình.
- **SubjectConfirmationData.Recipient:** phải là ACS đúng, không phải URL nào có cùng domain.
- **InResponseTo:** khi SP-initiated, phải khớp AuthnRequest đã lưu.
- **Conditions timestamps:** NotBefore/NotOnOrAfter, clock skew policy.
- **Replay:** không nhận lại Assertion ID hoặc response ID ngoài policy.
- **Decryption:** nếu encrypted, decrypt bằng credential đúng và tiếp tục validate đầy đủ.
- **XML handling:** chống signature wrapping, XXE, malicious XML, oversized messages.

**Dùng Spring/OpenSAML provider chuẩn**, không tự parse XML bằng regex rồi xác minh một node trong khi đọc principal từ node khác. Spring Security 6.x và 7.x có khác biệt OpenSAML/API, nên phải theo release cụ thể.

## 19. Tenant trong URL/header không tự là quyền

Ví dụ URL:

~~~text
GET /t/south/api/invoices/inv-203
X-Tenant: south
Authorization: Bearer ACCESS_TOKEN
~~~

User có token đúng issuer nhưng chỉ thuộc tenant North. Trường `south` trong path/header chỉ xác định **tài nguyên được yêu cầu**, không chứng minh membership.

**Domain authorization:**

~~~text
ALLOW
 IF token/assertion verified against trusted issuer/IdP
 AND local account active
 AND requested tenant exists and is permitted for this IdP/registration
 AND user is active member of requested tenant
 AND action permission granted in requested tenant
 AND invoice belongs to requested tenant
 ELSE DENY
~~~

Nếu ứng dụng dùng subdomain theo tenant, phải bảo vệ Host/X-Forwarded-Host spoofing qua trusted proxy và allowlist. **Không chọn IdP/tenant dựa vào untrusted Host rồi cho login thành công theo trust mở rộng.**

## 20. Identity linking: cùng sub/email vẫn có thể khác người

Hai nguồn:

~~~text
Corp:
  issuer = https://id.corp.test/realm/staff
  sub    = 123
  email  = alex@example.test

Partner:
  issuer = https://id.partner.test/realm/client
  sub    = 123
  email  = alex@example.test
~~~

Tuy trùng `sub` và email, đây là **hai external identities**. Key an toàn thường là:

~~~text
(protocol, verified_issuer_or_saml_entityID, verified_subject)
    -> local_account_id

local_account_id + requested_tenant
    -> membership and entitlements
~~~

Đối với SAML NameID, cần xem format (persistent/transient/email address) và contract; nhiều NameID không ổn định, không dùng email như UUID. Khi một tenant đổi IdP, account migration phải có linking proof/approval và audit.

**Không tự nối hai local accounts chỉ bằng email trùng**, nhất là nếu tenant admin có thể tự đăng ký IdP.

## 21. Group/role confusion và GrantedAuthority

Giả sử Partner IdP phát group `FinanceAdmins` và Corp IdP cũng có group cùng tên. Không được map cả hai thành `ROLE_ADMIN` trên tất cả tenants.

Cần policy riêng:

| Trusted source | Trusted group ID | Tenant | App permission |
| --- | --- | --- | --- |
| Corp issuer | `corp-billing-readers` | North | `ROLE_INVOICE_VIEWER` |
| Corp issuer | `corp-billing-approvers` | North | `ROLE_INVOICE_APPROVER` |
| Partner issuer | `partner-support-readers` | South | `ROLE_SUPPORT_VIEWER` |
| Unknown source | `ROLE_ADMIN` (raw string) | Bất kỳ | **Không cấp** |

Chỉ map sau signature/token validation và account linking. **Các roles là application-owned**, cần exact allowlist và checks theo tenant/resource. Một verified user không tự có quyền tất cả endpoints.

## 22. Dynamic issuer onboarding cần quy trình quản trị

Nếu SaaS cho khách hàng đăng ký IdP mới:

1. Tenant owner gửi yêu cầu onboarding, chưa tạo trusted profile ngay.
2. Xác minh admin có quyền quản trị tenant và quyền thay đổi federation trust.
3. Kiểm issuer/entityID uniqueness, allowed tenant mappings, consent và legal requirements.
4. Chỉ tải metadata/JWKS qua HTTPS với egress kiểm soát, chống SSRF/private IP/link-local.
5. Kiểm metadata issuer, algs, signing certificate/JWKS, endpoints, redirect/ACS.
6. Thực hiện test login canary xác minh request correlation/audience/tenant.
7. Yêu cầu phê duyệt security owner trước ACTIVE.
8. Version cấu hình, ghi audit ai đổi issuer/key/roles, khi nào.
9. Cấu hình key rotation và policy revoke/disable.
10. Không auto-trust một issuer chỉ vì JWT tự khai báo issuer đó.

**Dynamic trusted configuration ≠ dynamic trust from unverified input.** Khi tenant bị đóng hoặc IdP compromise, phải disable registration và xử lý sessions đã phát.

## 23. Key rotation, metadata cache và failure mode

Các issuers quay vòng JWKs; SAML IdPs quay vòng signing certificates. Cần:

- Gắn key cache với **exact issuer/registration**, không với `kid` toàn cục.
- Chỉ tin metadata/JWKS endpoints đã phê duyệt; kiểm TLS certificate và redirects.
- Kiểm algorithm và key type theo policy, không hạ xuống thuật toán yếu để giải quyết outage.
- Có khoảng overlap keys khi rotation được quản lý.
- Có timeout, caching, bounded retry và metrics.
- Nếu new `kid` chưa có, refresh đúng trusted issuer JWKS theo rate limit; không tìm sang issuer khác.
- Khi issuer bị revoke, dừng new authentications, xử lý cached managers/session according to SLA.
- Không dùng một certificate expired hoặc untrusted chỉ vì tên đúng.
- Kiểm impact multi-node và stale cache sau deploy.
- Có kế hoạch rollback **không mở rộng trust**.

**Bộ khóa của IdP A không thể bù lỗi cấu hình IdP B.** “Tìm một issuer khác xác minh được” là lỗi thiết kế.

## 24. Java 17 độc lập: mô phỏng chọn verifier và tenant

Chương trình sau dùng **policy mô phỏng**. Nó **không thực sự verify JWT/SAML signatures**; các boolean `signatureVerified` và `flowCorrelated` phải được hiểu là kết quả **sau khi một thư viện giao thức đáng tin đã xử lý**, không phải giá trị đọc từ HTTP request.

Tạo file **IssuerTenantSelectionDemo.java**:

~~~java
import java.util.Map;
import java.util.Set;

public class IssuerTenantSelectionDemo {

    record Profile(String issuer, String audience,
                   String tenant, Set<String> keyIds) {}

    record Evidence(String issuer, String audience,
                    String tenant, String keyId,
                    boolean signatureVerified,
                    boolean flowCorrelated,
                    boolean freshAndNotReplayed) {}

    private static final Map<String, Profile> TRUST = Map.of(
        "corp", new Profile(
            "https://id.corp.test/realm/staff",
            "portal-corp", "north", Set.of("corp-key")),
        "partner", new Profile(
            "https://id.partner.test/realm/client",
            "portal-partner", "south", Set.of("partner-key"))
    );

    static String verify(String trustedRegistration,
                         Evidence evidence,
                         String resourceTenant) {
        Profile profile = TRUST.get(trustedRegistration);

        if (profile == null) {
            return "DENY_UNKNOWN_REGISTRATION";
        }
        if (!profile.issuer().equals(evidence.issuer())) {
            return "DENY_ISSUER";
        }
        if (!profile.audience().equals(evidence.audience())) {
            return "DENY_AUDIENCE";
        }
        if (!profile.keyIds().contains(evidence.keyId())) {
            return "DENY_KEY";
        }
        if (!evidence.signatureVerified()) {
            return "DENY_SIGNATURE";
        }
        if (!evidence.flowCorrelated()) {
            return "DENY_FLOW";
        }
        if (!evidence.freshAndNotReplayed()) {
            return "DENY_REPLAY";
        }
        if (!profile.tenant().equals(evidence.tenant())) {
            return "DENY_TENANT_CLAIM";
        }
        if (!profile.tenant().equals(resourceTenant)) {
            return "DENY_RESOURCE_TENANT";
        }
        return "ALLOW " + trustedRegistration;
    }

    static Evidence evidence(String issuer, String audience,
                             String tenant, String keyId,
                             boolean signature,
                             boolean flow,
                             boolean fresh) {
        return new Evidence(issuer, audience, tenant, keyId,
                            signature, flow, fresh);
    }

    public static void main(String[] args) {
        Evidence corp = evidence(
            "https://id.corp.test/realm/staff",
            "portal-corp", "north", "corp-key",
            true, true, true);

        System.out.println("Valid: "
            + verify("corp", corp, "north"));
        System.out.println("Unknown registration: "
            + verify("attacker", corp, "north"));
        System.out.println("Wrong issuer: "
            + verify("partner", corp, "south"));
        System.out.println("Wrong audience: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "other-api", "north", "corp-key",
                true, true, true), "north"));
        System.out.println("Wrong key scope: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "north", "partner-key",
                true, true, true), "north"));
        System.out.println("Bad signature: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "north", "corp-key",
                false, true, true), "north"));
        System.out.println("No state binding: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "north", "corp-key",
                true, false, true), "north"));
        System.out.println("Replay: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "north", "corp-key",
                true, true, false), "north"));
        System.out.println("Wrong tenant: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "south", "corp-key",
                true, true, true), "north"));
        System.out.println("Resource from South: "
            + verify("corp", corp, "south"));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac IssuerTenantSelectionDemo.java
java IssuerTenantSelectionDemo
~~~

**Stdout chính xác:**

~~~text
Valid: ALLOW corp
Unknown registration: DENY_UNKNOWN_REGISTRATION
Wrong issuer: DENY_ISSUER
Wrong audience: DENY_AUDIENCE
Wrong key scope: DENY_KEY
Bad signature: DENY_SIGNATURE
No state binding: DENY_FLOW
Replay: DENY_REPLAY
Wrong tenant: DENY_TENANT_CLAIM
Resource from South: DENY_RESOURCE_TENANT
~~~

**Giải thích:** trustedRegistration được giả định lấy từ **server-side saved login transaction/approved route**, không phải tùy tiện từ query; `keyId` là hint đã được validator kiểm trong đúng trusted issuer keyset; tenant check trong demo là 1:1 để minh họa. Production có thể cho một issuer nhiều tenants nhưng phải kiểm membership. **Không dùng demo làm production JwtDecoder, AuthenticationProvider hoặc SAML verifier**.

## 25. Multi-tenant và multi-issuer là hai bài toán khác nhau

**Multi-issuer:** API chấp nhận access tokens của nhiều Authorization Servers. Cần xác minh mỗi token với **đúng issuer/keyset**.

**Multi-tenant:** app phục vụ nhiều organizations, mỗi organization có data, memberships và entitlements. Cần **authorization isolation**.

Các topology:

| Quan hệ | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| 1 issuer : 1 tenant | Corp → North | Trusted issuer map + domain membership |
| 1 issuer : nhiều tenants | Shared enterprise OP → North/South | Một verifier có thể đủ; tenant checks riêng |
| Nhiều issuers : 1 tenant | Corp + Partner → North | Cho phép nhiều IdPs, identity links riêng |
| Nhiều tenants : Nhiều IdPs | SaaS marketplace | Trusted registry (issuer, tenant, registration), local authorization |
| 1 tenant có OIDC + SAML | Hệ chuyển đổi | Validators khác giao thức, unified account link |
| User thuộc nhiều tenants | Consultant | Chỉ cấp quyền tenant được chọn và resource thực |

**Không ép kiến trúc 1–1 trong trường hợp thực tế 1–n/n–1.** Nhưng cũng không tự nới policy để một issuer được tất cả tenants tin.

## 26. Home Realm Discovery không phải chứng cứ

Trang login có thể hỏi email và đề xuất IdP tương ứng:

~~~text
alice@corp.test
  -> hint: đăng nhập Corp IdP
  -> server chọn ClientRegistration corp (trusted)
  -> tạo state/nonce/PKCE transaction
  -> validate callback và token với Corp config
~~~

**Email do người dùng nhập không chứng minh người đó có quyền với Corp.** Hãy dùng email domain chỉ làm UX discovery và luôn recheck identity sau login. Không tự tạo local account/tenant membership dựa email.

Nếu dùng subdomain để chọn tenant/IdP, phải bảo vệ Host, Forwarded, X-Forwarded-* headers và alias/misrouting. Không biến `tenant=corp` trong URL thành quyền tạo trust registration.

## 27. Sessions, logout và reauthentication

Có thể xảy ra:

~~~text
09:00 User Corp login -> Spring session account A/North
09:30 Admin rút quyền của A hoặc đổi IdP trust
09:40 Session cũ vẫn có SecurityContext/GrantedAuthorities
10:00 Browser bắt đầu login Partner user B
10:01 Callback/tenant mismatch hoặc principal change
~~~

Nếu session vẫn giữ A sau callback B, hoặc role A không refresh khi quyền đổi, có thể dùng sai identity/entitlement.

**Biện pháp:**
- Session principal change detection, session fixation protection.
- Logout flow theo đúng nguồn; OIDC logout/SAML SLO nếu hỗ trợ, không giả mọi IdPs tự đồng bộ.
- Giới hạn session/Authentication snapshot tuổi tối đa.
- Re-check account active, trusted issuer/profile và tenant membership khi quyền nhạy cảm.
- Revoke sessions/tokens khi issuer disabled/compromised theo SLA.
- Khi user đổi tenant, thực hiện authorization/step-up theo policy.
- Multi-node session/replay caches phải phối hợp.
- Không chỉ chờ JWT hết hạn nếu cần revocation tức thì.

**Authentication thành công một lần không là bảo đảm authorization vĩnh viễn.**

## 28. API, browser và SAML không dùng chung filter giả định

Hệ có thể có các SecurityFilterChains:

~~~text
/login/oauth2/**           -> Spring OAuth2/OIDC login
/oauth2/authorization/**   -> Spring OAuth2 authorization request
/login/saml2/sso/**        -> Spring SAML2 response validation
/saml2/authenticate/**     -> Spring SAML2 AuthnRequest
/api/**                    -> OAuth2 Resource Server access tokens
/admin/**                  -> Elevated authorization policy
~~~

Đây là **sơ đồ logic**, không phải cấu hình đường dẫn có thể copy nguyên; những endpoints mặc định/framework có thể khác theo app, và filter order/matcher cần test thật.

**Không dùng:**
- JWT ID Token ở Bearer API.
- SAML Assertion ở JWT decoder.
- Một header `X-User` như fallback sau signature failure.
- Một custom parser chọn bất kỳ verifier thành công đầu tiên.
- Một entrypoint thiếu authentication để chuyển request sang registration lỏng hơn.
- Một wildcard issuer/certificate trust để tạm vượt lỗi production.

## 29. Nguyên tắc xử lý lỗi

| Lỗi | Xử lý |
| --- | --- |
| Unknown issuer/JWK source | Từ chối, không auto-enroll |
| Signature invalid | Từ chối, không fallback issuer |
| JWT audience sai | API trả 401 |
| OIDC callback issuer/state mismatch | Dừng flow, không gửi code sai token endpoint |
| SAML Issuer/cert/Audience/Recipient mismatch | Authentication failure |
| Assertion/ID Token expired/replayed | Từ chối |
| User đúng issuer nhưng không có tenant membership | Authorization 403 |
| User có membership nhưng thiếu quyền trên object | Authorization 403 |
| Metadata/JWKS outage | Không bỏ validation; xử lý unavailable theo policy |
| Untrusted tenant Host/header | Không dùng làm trust context |
| Same sub từ hai IdPs | Giữ distinct identities hoặc linking proof |
| User suspended sau login | Revoke/deny theo application policy |

**Không ghi raw JWT, authorization codes, SAMLResponse, certificate private key, session cookie hoặc NameID đầy đủ vào public logs**. Dùng correlation ID và mã lỗi đã phân loại.

## 30. Ma trận kiểm thử security end-to-end

| # | Tình huống | Kết quả cần |
| --- | --- | --- |
| 01 | Corp issuer, Corp key, đúng audience | Authentication hợp lệ |
| 02 | Token tự ký từ attacker issuer | Unknown issuer, 401 |
| 03 | Partner JWT vào Corp-only flow | Từ chối |
| 04 | Corp token dành Payroll vào Billing | 401 wrong audience |
| 05 | OIDC ID Token vào resource server API | Từ chối token type/audience |
| 06 | JWT kid giống nhau ở hai issuers | Không dùng nhầm key |
| 07 | JWT có jku tới attacker.test | Không fetch/trust arbitrary URL |
| 08 | JWT alg ngoài allowlist | Từ chối |
| 09 | Valid iss nhưng invalid signature | Từ chối |
| 10 | JWT expired hoặc nbf chưa hiệu lực | Từ chối |
| 11 | Một issuer phục vụ North và South | Phân quyền tách tenant |
| 12 | User Corp không có North membership | 403 |
| 13 | Username/sub trùng ở hai IdPs | Không gộp account |
| 14 | Email trùng giữa hai tenants | Không auto-link |
| 15 | Authorization code A, state B | Abort |
| 16 | OAuth callback iss không đúng expected issuer | Abort trước token exchange |
| 17 | OAuth state expired/reused | Reject |
| 18 | Redirect URI không đúng registration | Reject |
| 19 | OIDC nonce mismatch | Reject |
| 20 | OIDC aud/azp không hợp lệ | Reject |
| 21 | SAML Response IdP B vào ACS registration A | Reject |
| 22 | SAML cert B được dùng ký assertion khai báo A | Reject |
| 23 | SAML AudienceRestriction sai SP entityID | Reject |
| 24 | SAML Recipient/Destination sai | Reject |
| 25 | SAML InResponseTo không tồn tại | Reject SP-initiated response |
| 26 | SAML NotOnOrAfter hết hạn | Reject |
| 27 | SAML assertion ID replay | Reject |
| 28 | XML Signature Wrapping | Không dùng unsigned identity |
| 29 | SAML unsolicited khi policy cấm | Reject |
| 30 | Metadata URI bị thay bởi user | Không thay đổi trusted registration |
| 31 | Dynamic issuer tự thêm từ JWT iss | Không được phép |
| 32 | Tenant slug do browser đổi North→South | Membership/object rules 403 |
| 33 | Group ROLE_ADMIN do Partner phát | Không cấp admin Corp |
| 34 | Issuer bị revoke khi session còn | Sessions/tokens xử lý theo SLA |
| 35 | Key rotation new kid đúng trust | Chấp nhận theo policy |
| 36 | Key rotation unexpected key | Reject |
| 37 | JWKS fetch timeout | Không fallback issuer/cert |
| 38 | Tenant admin thêm IdP nhưng chưa approval | Profile pending, không trusted |
| 39 | Một tenant có hai IdPs đã approved | Hai identity namespaces vẫn tách |
| 40 | SAML issuer đúng nhưng signature sai | Reject |
| 41 | SAML signature đúng nhưng recipient sai | Reject |
| 42 | Token đúng aud nhưng client/actor không được phép | Deny theo policy |
| 43 | Host/X-Forwarded-Host spoof | Không thay đổi trusted tenant/issuer |
| 44 | Callback có nhiều issuer identifiers mâu thuẫn | Reject |
| 45 | User disabled nhưng token còn hạn | Backend deny theo SLA |
| 46 | API route bị SecurityFilterChain khác bắt nhầm | Test phát hiện configuration mismatch |
| 47 | Session user A đổi thành B | Không dùng stale SecurityContext A |
| 48 | Canaries phát hiện cross-tenant success ngoài policy | Rollback an toàn và incident xử lý |

**E2E test phải chứng minh verifier được chọn từ trusted registration, không chỉ mock `Authentication.isAuthenticated()==true`.** Test các đường cross-issuer/cross-tenant bằng token/assertion thật trong môi trường test được kiểm soát.

## 31. Runbook triển khai

### Pha A — Inventory trust configuration

1. Liệt kê OIDC/OAuth issuers, SAML IdP entityIDs, tenant↔registration mappings.
2. Ghi metadata/JWKS URLs, certs, algorithms, ACS/redirect, client IDs/SP entityIDs và audience.
3. Xác định danh tính ổn định cho mỗi issuer và phương pháp local account linking.
4. Phân tích ai có quyền thêm/đổi issuer/cert/tenant mappings.
5. Liệt kê dynamic issuer resolution và các đường mở trust từ unverified inputs.
6. Xác định session/replay/cache lifetimes và revocation SLA.

### Pha B — Hardening

1. Dùng issuer allowlist, Spring multi-issuer resolver phù hợp.
2. Gắn đúng JWKS/certificates/algorithms cho issuer tương ứng.
3. Thêm JWT audience/token purpose validators cho từng issuer.
4. OAuth multi-AS client ràng buộc state + expected issuer theo RFC 9207/9700.
5. OIDC kiểm iss/aud/nonce/azp và user account linking.
6. SAML kiểm registration, signature, issuer, recipient, destination, audience, InResponseTo, replay.
7. Chống Host/Forwarded spoof và metadata-fetch SSRF.
8. Map groups qua tenant-specific allowlist.
9. Domain authorization theo user account + tenant + resource.

### Pha C — Canary

1. Canaries cho Corp/Partner, các tenants và cross-scope tokens.
2. Thử authorization-server mix-up với các callback state/issuer mâu thuẫn.
3. Thử SAML XML issuer/cert mismatch và ACS/audience mismatch.
4. Thử JWT kid collision, jku injection, wrong audience, expired tokens.
5. Thử IdP outage, JWKS rotation, certificate rollover và session revocation.
6. Giám sát 401/403/mismatch/replay counters có correlation ID, không lộ token.
7. Duyệt security test results trước khi tăng traffic.

### Pha D — Vận hành

1. Quản lý issuer/cert trust registry có owner và audit.
2. Khi phát hiện compromise: disable issuer/registration, evict sessions/tokens theo policy.
3. Không sửa outage bằng wildcard issuer hay bỏ chữ ký.
4. Theo dõi metadata freshness và fail-closed behavior.
5. Quản lý migration giữa IdPs bằng linking proof, không ghép email.
6. Định kỳ thử cross-tenant access, refresh roles và rà soát trust drift.

## 32. Monitoring và audit

Đây là metrics gợi ý do hệ thống tự instrument, không phải tất cả được Spring Security sinh sẵn:

| Metric | Ý nghĩa |
| --- | --- |
| `federation_unknown_issuer_total` | Issuer chưa trusted |
| `federation_issuer_mismatch_total` | Token/asertion issuer khác expected |
| `oauth_mixup_prevented_total` | Callback AS mismatch/state errors |
| `jwt_wrong_audience_total` | Token dành cho API khác |
| `jwt_invalid_signature_total` | Không verify được |
| `jwks_untrusted_url_rejected_total` | Chặn dynamic key URL |
| `saml_registration_mismatch_total` | Sai RelyingPartyRegistration |
| `saml_replay_blocked_total` | Assertion replay bị chặn |
| `tenant_authorization_denied_total` | Không thuộc tenant/resource |
| `identity_link_collision_total` | Trùng user IDs từ issuers khác nhau |
| `trust_profile_changes_total` | Config trust thay đổi |
| `stale_session_denied_total` | Session/token bị revoked |

Không dùng `sub`, email, token, raw SAML XML, raw kid do user kiểm soát trong metric labels. Ghi trusted registrationId, policy version, pseudonymous user ID, operation, correlation ID và decision category.

**Cảnh báo cao:** suddenly many unknown issuers; JWT tự ký vẫn được 200; một user verified ở Partner truy cập tài nguyên Corp không có membership; callbacks không có state/issuer vẫn thành công; IdP bị revoke vẫn được tạo sessions mới.

## 33. Câu hỏi tự đánh giá

**1. JWT signature đúng với JWKS từ URL chính JWT tự khai báo đã đáng tin chưa?**  
Không. Issuer và JWKS URI cần nằm trong approved trust configuration; chữ ký tự nhất quán với key attacker không là authentication.

**2. Có được đọc iss chưa verify để chọn decoder không?**  
Có, nhưng chỉ làm **candidate hint trong trusted allowlist**, sau đó phải verify signature và exact issuer/audience/time/type.

**3. kid có duy nhất trên toàn Internet không?**  
Không, phải gắn key lookup với issuer/registration.

**4. OAuth mix-up khác ID Token issuer mismatch như thế nào?**  
Mix-up có thể làm client gửi authorization code tới token endpoint sai **trước khi có ID Token**; cần binding expected issuer với transaction và callback.

**5. RFC 9207 giải quyết bằng tham số gì?**  
`iss` trong authorization response để client so với expected AS issuer.

**6. Spring JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers làm gì?**  
Cho phép issuer selection trong tập đã tin; không thay audience/type/tenant authorization validators.

**7. SAML Response Issuer có thể dùng chọn RelyingPartyRegistration không?**  
Có thể làm hint theo Spring/flow, nhưng cần full SAML signature/protocol verification mới tin được.

**8. SAML registrationId có phải IdP entityID không?**  
Không. registrationId là key nội bộ Spring; IdP entityID là identifier theo SAML protocol.

**9. Tại sao phải kiểm Recipient và AudienceRestriction?**  
Để đảm bảo assertion dành cho đúng ACS và SP, không chấp nhận assertion phát cho dịch vụ khác.

**10. Tenant ID trong token đã verify có tự cấp membership không?**  
Không mặc định. Backend phải kiểm server-side tenant membership và resource-level authorization theo contract.

**11. Email có đủ để link user từ hai IdPs không?**  
Không. Cần verified issuer+subject và linking proof.

**12. Khi JWKS của Corp outage, dùng key Partner để validate có hợp lý không?**  
Không. Fail closed, không đổi trust context.

**13. Khi issuer phục vụ hai tenants, có cần hai JWT validators riêng không?**  
Không nhất thiết; issuer verifier có thể chung, nhưng authorization tenant phải tách biệt.

**14. Nếu SAML IdP-initiated không có InResponseTo thì sao?**  
Chỉ nhận khi policy cho phép unsolicited login và có strict signature/issuer/audience/recipient/replay/login-CSRF protections.

**15. Có thể tự thêm IdP vào trust list khi người dùng đưa metadata URL không?**  
Không. Cần owner approval và verification.

## 34. Checklist production

- [ ] Có versioned trusted registry cho OIDC issuers và SAML IdP entityIDs.
- [ ] Unknown issuers/IdPs fail closed, không auto-discovery từ JWT.
- [ ] Issuer claim hoặc SAML Issuer trước verification chỉ là candidate hint.
- [ ] Mỗi issuer gắn đúng JWKS/signing certs và allowed algorithms.
- [ ] Không tin jku/x5u arbitrary, không dùng global kid map.
- [ ] JWT API kiểm signature, iss, aud, exp/nbf, token purpose và scopes.
- [ ] OAuth multi-AS login có mix-up protections RFC 9700/RFC 9207 hoặc tương đương.
- [ ] OAuth callback ràng buộc state, expected registration, issuer, PKCE và redirectUri.
- [ ] OIDC ID Token kiểm iss/aud/azp/nonce theo flow.
- [ ] Spring JwtIssuerAuthenticationManagerResolver dùng trusted issuers.
- [ ] SAML RelyingPartyRegistration resolver chọn đúng registration và trusted signing credentials.
- [ ] SAML Response/Assertion kiểm Issuer, Destination/Recipient, Audience, Conditions và signature.
- [ ] SP-initiated SAML kiểm AuthnRequest InResponseTo và replay.
- [ ] Không tự nhận unsolicited SAML khi chưa có policy.
- [ ] Local identity links namespace theo issuer/IdP; không chỉ email/username.
- [ ] Tenant từ URL/header không tự là quyền; kiểm membership/resource.
- [ ] Group mapping qua issuer+tenant allowlist, không auto ROLE_ADMIN.
- [ ] Client credentials/service identities khác user identities, không lẫn token types.
- [ ] Có session logout/revocation policy khi IdP/tenant config đổi.
- [ ] Có test cross-issuer, cross-tenant, kid collision, wrong aud, mix-up và SAML ACS mismatch.
- [ ] Host/Forwarded spoofing, metadata SSRF và key rotation được kiểm tra.
- [ ] Không log raw tokens, SAML assertions, private keys hoặc PII ngoài mục đích.
- [ ] Khi outage, không hạ trust bằng accept-any-issuer/key/metadata.
- [ ] Có canary, incident runbook và phương án disable issuer nhanh.

## 35. Kết luận

**Nhầm lẫn IdP, issuer hoặc tenant là lỗi tin cậy, không chỉ là nhầm tên cấu hình.** Một JWT có chữ ký hợp lệ từ IdP B không được nhận tại trust profile của A; một SAML assertion signed đúng nhưng sai SP/ACS không được dùng; một verified identity không tự có quyền trên tenant do caller chọn.

Luồng an toàn là **trusted registration và giao dịch đã khởi tạo → chọn candidate từ allowlist → verifier đúng key/issuer/recipient/audience → full protocol validation và replay protection → verified subject trong issuer namespace → local account/tenant/resource authorization**.

Với Spring Security, khai thác **JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)** cho API nhiều issuers và **RelyingPartyRegistrationRepository/Resolver cùng OpenSAML provider** cho SAML. Với OAuth/OIDC client hỗ trợ nhiều Authorization Servers, thực thi mix-up defenses **trước token exchange**, theo RFC 9207 và RFC 9700. Tenant authorization luôn là trách nhiệm của backend, không phải một claim tự động cấp quyền.

### Tài liệu chính thức

- Spring Security — Multi-tenancy of OAuth2 Resource Servers: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
- Spring Security — JWT Resource Server validation: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — SAML2 Login Overview, registration resolution and OpenSAML validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification: https://www.rfc-editor.org/rfc/rfc9207
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- RFC 8414 — OAuth 2.0 Authorization Server Metadata: https://www.rfc-editor.org/rfc/rfc8414
- RFC 9068 — JWT Profile for OAuth2 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- OpenID Connect Core 1.0 — Issuer/ID Token Validation: https://openid.net/specs/openid-connect-core-1_0.html
- OASIS SAML 2.0 Core/Profiles/Metadata: https://www.oasis-open.org/standard/saml/
