# Rà soát bộ kiểm chứng và bộ chuyển đổi tùy chỉnh khi nâng phiên bản

> **Module:** Spring Security – federation. **Nhóm:** Chuyển đổi và nâng cấp. Bài Knowledge này là hướng dẫn độc lập để kiểm kê, nâng cấp, kiểm thử và vận hành các **validators, converters, mappers, authentication providers và resolvers tùy chỉnh** trong Spring Security, đặc biệt ở SAML 2.0, OIDC/OAuth2 Login, JWT Resource Server, LDAP, Kerberos và CAS. Trọng tâm không chỉ là sửa API lỗi biên dịch, mà còn giữ nguyên các ranh giới bảo mật khi framework thay đổi cách xác minh, chuyển đổi danh tính, quản lý phiên và phân quyền.

## 1. Kết quả học tập và nguyên tắc không thể bỏ

Sau bài học, bạn cần:
1. Phân biệt validation với conversion, authentication và authorization.
2. Tìm đủ extension points tùy chỉnh trong source, config và dependencies.
3. So sánh **hành vi mặc định của phiên bản cũ và mới** thay vì chỉ đổi tên class.
4. Biết rủi ro khi tùy biến OpenSAML authentication provider, SAML Response/Assertion validators và converters.
5. Hiểu các khác biệt liên quan Spring Security 6→7: OpenSAML 5, NameID/validation order, principal/assertion accessor, missing RelyingPartyRegistration, SAML logout.
6. Kiểm OIDC UserService/GrantedAuthoritiesMapper và JWT JwtDecoder/JwtAuthenticationConverter không mất issuer, audience, lifetime, signature và authority scope.
7. Thiết kế negative security fixtures để chứng minh **dữ liệu bị giả mạo vẫn bị từ chối** sau nâng cấp.
8. Phát hiện regression về tenant mapping, role prefix, SecurityFilterChain, CSRF, session, cookie và SSO callbacks.
9. Viết tests Java 17, đo observability, có rollback và release gates.
10. Phân biệt code ví dụ standalone với Spring framework fragments cần project/dependencies.

**Nguyên tắc cốt lõi:** **Chỉ map principal và authorities từ identity đã được framework chứng minh bằng trusted credential và đúng protocol context.** Nếu bổ sung một business validation, hãy **giữ lại** các built-in checks bắt buộc. Khi bỏ/thay một validator, đó là thay đổi mô hình bảo mật cần được xem xét độc lập.

## 2. Bốn lớp trách nhiệm thường bị nhầm

| Lớp | Câu hỏi | Thành phần điển hình |
|---|---|---|
| Parsing/decoding | Dữ liệu HTTP/XML/JWT có được đọc an toàn không? | OpenSAML unmarshaller, JWT parser |
| Validation | Chữ ký, signer, issuer, audience, thời gian và protocol context đúng không? | SAML validators, JwtDecoder, OAuth2TokenValidator |
| Conversion | Dữ liệu đã xác minh được ánh xạ thành principal/authorities như thế nào? | ResponseAuthenticationConverter, JwtAuthenticationConverter, GrantedAuthoritiesMapper |
| Authorization | Principal có được truy cập tài nguyên/hành động này không? | AuthorizationManager, @PreAuthorize, domain ACL |

Ví dụ JWT Resource Server: `JwtDecoder` phải xác minh token ký đúng, issuer và thời hạn; `JwtAuthenticationConverter` chỉ chuyển các claims đã kiểm thành `JwtAuthenticationToken` và authorities. Việc converter tạo `ROLE_ADMIN` không làm cho token trở nên đúng issuer.

Ví dụ SAML: OpenSAML provider xác minh Response/Assertion, trusted IdP certificate và Conditions; response converter tạo principal/authorities. Nếu converter đọc NameID từ một XML element chưa được ký, cả pipeline có thể trở thành lỗ hổng XML Signature Wrapping.

### 2.1. Sơ đồ trust boundary

~~~text
Raw HTTP request / browser callback
       |
       v
Secure parser: SAML XML, OIDC code exchange, JWT bytes
       |
       v
Signing credential trust + cryptographic verification
       |
       v
Default protocol validators + approved custom validators
       |
       v
Validated identity and context
       |
       v
Custom converter / authorities mapper
       |
       v
Authentication (SecurityContext)
       |
       v
URL AuthorizationManager / method / tenant rules
       |
       v
Resource granted or denied
~~~

Nếu thay toàn bộ AuthenticationProvider, nguy cơ ảnh hưởng cả hai lớp verification/conversion. Nếu chỉ thay GrantedAuthoritiesMapper, phạm vi thường là mapping nhưng vẫn có thể dẫn tới privilege escalation. **Cần biết chính xác hook chạy trước hay sau validation ở target version**, không đoán theo tên API.

## 3. Lập inventory trước khi nâng cấp

Cần ghi theo từng điểm mở rộng:
- Module/protocol (SAML, OIDC, JWT, LDAP, CAS, Kerberos).
- Old dependency versions, target versions, BOM/JDK.
- Bean/class/filter chain/method tùy chỉnh.
- Input source: trusted result hay raw untrusted request.
- Phần default nào đã được thay thế hoặc được compose.
- Tại sao customization tồn tại.
- Invariants phải giữ.
- Acceptance/negative tests.
- Owner, review date, rollback và audit impact.

Ví dụ:

| Extension | Chức năng | Regression thường gặp |
|---|---|---|
| `ResponseValidator` | Kiểm SAML Response | Bỏ Issuer, Destination, InResponseTo |
| `AssertionValidator` | Kiểm Conditions/Subject/Audience | Chấp nhận expired/wrong audience |
| `ResponseAuthenticationConverter` | Tạo SAML Authentication | Chọn NameID sai, thiếu role, mất SLO support |
| `Saml2AuthenticationTokenConverter` | Resolve RelyingPartyRegistration | Chọn sai IdP/tenant, missing registration loop |
| `OidcUserService` | Tải OIDC UserInfo và principal | Bỏ delegate, sai sub, mất validated claims |
| `GrantedAuthoritiesMapper` | Map OIDC groups | Role prefix sai, cấp Admin tự động |
| `JwtDecoder` | Kiểm JWT signature và claims | Bỏ issuer/exp/nbf |
| `JwtGrantedAuthoritiesConverter` | Map scopes/roles | Claim name, delimiter hoặc prefix sai |
| `AuthorizationManager` | Kiểm quyền URL/method | Filter ordering, tenant bypass |
| `UserDetailsService` | Local account mapping | Same email across IdPs bị merge |
| `SecurityContextRepository` | Session state | Callback OK nhưng request sau anonymous |

### 3.1. Tìm điểm tùy biến trong repo ứng dụng

Đây là lệnh hướng dẫn cho developer dùng trên checkout **của chính dự án cần nâng cấp**, không phải thao tác trên workspace khác:

~~~bash
rg -n 'SecurityFilterChain|AuthenticationProvider|AuthenticationManager' src
rg -n 'OpenSaml4|OpenSaml5|ResponseValidator|AssertionValidator' src
rg -n 'ResponseAuthenticationConverter|Saml2AuthenticationTokenConverter' src
rg -n 'RelyingPartyRegistration|Saml2AuthenticatedPrincipal' src
rg -n 'JwtDecoder|JwtValidators|OAuth2TokenValidator' src
rg -n 'JwtAuthenticationConverter|JwtGrantedAuthoritiesConverter' src
rg -n 'OidcUserService|OAuth2UserService|GrantedAuthoritiesMapper' src
rg -n 'UserDetailsService|Kerberos|Cas|LdapAuthoritiesPopulator' src
rg -n 'requestMatchers|securityMatcher|PreAuthorize|AuthorizationManager' src
rg -n 'SecurityContextRepository|sessionManagement|requestCache|csrf' src
~~~

`rg` là ripgrep; dùng IDE structural search nếu hệ thống không có. Chú ý code có thể cấu hình bằng XML/YAML, Java, Kotlin, factory methods hoặc Spring auto-configuration, không chỉ qua class names.

### 3.2. Kiểm dependency tree

Với Maven:
~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Với Gradle:
~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-saml2-service-provider \
  --configuration runtimeClasspath
~~~

Tài liệu Spring Boot/Framework/Security và các adapter vendor quyết định compatibility. Không tự trộn OpenSAML 4 và 5 hoặc nhiều major versions của Apache Santuario/XML security JARs chỉ để “cho build xanh”. Với Spring Boot major upgrade còn kiểm Java/Jakarta Servlet/Jackson namespace changes và cách serialize SecurityContext.

## 4. Xác định hợp đồng an toàn trước khi sửa code

Bất biến nên được biểu diễn bằng testable assertions:

~~~text
SAML:
- Trusted IdP signature on expected Response/Assertion
- Signed object is the consumed authentication assertion
- Registration issuer + key + audience + ACS remain consistent
- Destination/Recipient/InResponseTo/Conditions validated
- No replay or unsigned attribute escalation
- Principal and group mapping come from validated objects

OIDC:
- State and nonce (when applicable) verified
- ID Token signed by approved provider and iss/aud/time valid
- UserInfo subject consistent with verified ID Token
- Local identity link by approved issuer + stable subject
- Only approved group/entitlement to business role mapping

JWT API:
- Signed by trusted issuer's JWK, approved algorithm
- iss/exp/nbf and required aud checked
- Claims never promoted to ROLE_ADMIN without policy
- Access token not confused with ID Token
- Invalid token denied, not silently anonymous-authenticated

Application:
- SecurityFilterChain routes preserved
- CSRF/session/context/cookie rules preserved
- Tenant/resource/method authorization enforced
- No secrets or raw credentials in telemetry
~~~

Nếu test baseline đang thiếu ca âm tính, hãy thêm **trước** upgrade để có so sánh hành vi cũ/mới. Một test login thành công chỉ xác nhận happy path, không chứng minh validator chưa bị tắt.

### 4.1. Định nghĩa thành công theo 3 lớp

1. **API compatibility:** build và startup không lỗi.
2. **Functional compatibility:** login, logout, callback, session, user mapping hoạt động.
3. **Security-semantic compatibility:** signature/issuer/audience/time/recipient/replay và permission denials giữ nguyên hoặc được siết có chủ đích.

Điểm thứ ba là release gate quan trọng nhất.

## 5. Những thay đổi SAML2 khi chuyển Spring Security 6 → 7

**Lưu ý phiên bản:** Các thay đổi được diễn giải từ Spring Security 7.0 migration guide và tài liệu SAML authentication. Khi triển khai phải pin phiên bản chạy thực tế và xem migration notes/Javadoc tương ứng; không mặc định một API tồn tại nguyên trạng ở mọi release.

### 5.1. OpenSAML 5 trở thành baseline

Hướng dẫn migrate chỉ rõ OpenSAML 4 không còn được upstream hỗ trợ, nên Spring Security chuyển sang những thành phần OpenSAML 5 trong target release. Kiểm:
- Code tự khởi tạo `OpenSaml4AuthenticationProvider` và các OpenSAML4 types.
- API trên `OpenSaml5AuthenticationProvider`.
- SAML XML object model, signature/decryption strategy APIs.
- Apache Santuario và XML parser dependencies.
- Key/certificate loading, RelyingPartyRegistration.
- Integration tests với real signed SAMLResponse.

Không thay class name cơ học rồi giả định equivalent behavior. Một số phiên bản đổi constructor, type parameters, provider defaults, principal representation và thứ tự validators.

### 5.2. Validation order và NameID

Migration documentation giải thích sự dịch chuyển thứ tự kiểm SAML Response và Assertion:
- Pipeline cũ có các Response validations trước Assertion validation và một bước kiểm NameID/name ở Response phase.
- Đường xử lý mới có thể validate assertions trước rồi Response validations, và **ResponseValidator không còn mặc định kiểm sự hiện diện NameID theo giả định cũ**.
- Custom ResponseAuthenticationConverter khi đòi NameID phải **tự fail closed** nếu NameID không tồn tại, blank hoặc không phải identity được approved.
- Nếu business dùng một stable attribute khác NameID, trường đó phải thuộc Assertion đã được signature/conditions verify; không fallback sang request parameter hoặc email header.

**Regression:**
~~~text
Old custom converter:
  framework rejected missing NameID before converter
New converter path:
  converter receives a validated structure with NameID absent
  code accidentally falls back to "admin" or empty localUserId
Outcome:
  identity confusion or wrong account linking
~~~

Cần test missing NameID, wrong format, missing Subject, blank stable ID, duplicates và multi Assertions. Nếu login được phép không có NameID thì phải có documented alternative identity contract.

### 5.3. Principal và SAML assertion accessor

Spring Security 7 migration guide nói về tách thông tin Assertion khỏi principal để hỗ trợ Single Logout, với `Saml2ResponseAssertionAccessor` và `Saml2AssertionAuthentication` trong API/model mới, đồng thời lưu ý đường dùng `Saml2AuthenticatedPrincipal` có thể bị deprecated.

Rà soát:
- `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` ở controller.
- Cast sâu `authentication.getPrincipal()` sang class cũ.
- Custom converter tự `new Saml2Authentication(...)`.
- SLO code tìm assertion details trong principal.
- Session serialization/Redis Jackson classes.
- Unit tests assert exact Authentication type.
- UserDetailsService bridge có trả đúng stable subject không.

Giữ business layer phụ thuộc interface/domain abstraction ổn định thay vì framework-specific implementation class nếu có thể. **Không tự chuyển một verified SAML Assertion thành raw DOM khác rồi dựng Authentication** để giữ API cũ.

### 5.4. Không tìm được relying-party registration

Migration guide mô tả hành vi `Saml2WebSsoAuthenticationFilter` với URL khớp nhưng không tìm được `RelyingPartyRegistration` có thể thay đổi: filter tiếp tục chain thay vì lập tức ném exception, kéo theo `AuthenticationEntryPoint` và đôi khi redirect loop.

Cần test:
- registrationId không tồn tại.
- Unexpected SAML issuer và multiple IdPs.
- Callback ACS có/mất registrationId.
- Missing pending AuthnRequest.
- Unknown IdP cert/metadata.
- Failure handler và redirect chain.

**Điều kiện bắt buộc:** Không có authenticated SecurityContext nếu relying party/IdP không được trust. Một HTTP status đổi sau upgrade chưa chắc là security regression; nhưng một redirect loop hoặc default registration fallback sai có thể là bug nghiêm trọng.

### 5.5. SAML LogoutRequest/LogoutResponse behavior

Spring Security 7 migration docs ghi việc xử lý LogoutRequest invalid có thể trả SAML LogoutResponse báo lỗi thay vì một số HTTP 401 cũ. Kiểm:
- Custom SAML SLO request validator.
- LogoutResponseResolver.
- IdP/SP issuer và signing keys.
- Logout status/error semantics.
- Session invalidation/CSRF.
- Tests trước đây assert HTTP 401 quá chặt mà không kiểm SAML protocol.

Không làm yếu LogoutRequest signature hoặc SLO correlation để giữ HTTP status cũ. Tách **protocol correctness** khỏi **error presentation**.

### 5.6. Chú ý SAMLResponse qua GET

Tài liệu migration còn đề cập cấu hình tương lai của converter khi gặp GET chứa SAMLResponse; việc không xử lý GET sẽ trở thành mặc định ở release tiếp theo được hướng dẫn. Vì vậy:
- Đọc đúng target release/Javadoc về `setShouldConvertGetRequests`.
- Không tuyên bố mọi phiên bản 7 đã từ chối GET mặc định.
- Ưu tiên SAML HTTP-POST binding theo contract.
- Không gửi SAMLResponse trong query URL, history, logs.
- Negative test GET payload không đăng nhập nếu deployment policy cấm.

## 6. Custom ResponseValidator phải giữ kiểm chứng mặc định

Trong SAML, một Response hoặc Assertion có chữ ký hợp lệ chưa đủ để đăng nhập. Các thuộc tính cần kiểm theo profile:
- Signature/trusted IdP signing key.
- Response Issuer và Assertion Issuer.
- Destination/ACS Location.
- AudienceRestriction = SP entityID.
- SubjectConfirmationData.Recipient/NotOnOrAfter.
- Conditions.NotBefore/NotOnOrAfter.
- InResponseTo cho SP-initiated SSO.
- Status, AuthnStatement và other profile requirements.
- Unique XML IDs và signed Reference target.
- Replay/correlation policy.
- Local tenant and account rules.

Một custom validator chỉ kiểm business attribute không thể tự thay tất cả các checks trên.

### 6.1. Pattern mở rộng thay vì thay toàn bộ

Spring Security SAML2 reference có mẫu:
~~~java
// Spring fragment: actual interface and imports depend on target release.
ResponseValidator combined =
        ResponseValidator.withDefaults(myCustomValidator);
provider.setResponseValidator(combined);
~~~

Đoạn trên **không standalone**, `myCustomValidator` và `provider` phải được khai báo đúng OpenSAML5/Spring API. Ý nghĩa: bổ sung một policy check nhưng vẫn giữ các ResponseValidator mặc định. Dùng cùng nguyên tắc cho AssertionValidator, kiểm API builder/extension của version hiện tại.

**Sai lầm:** code chỉ gọi `provider.setResponseValidator(customBusinessOnlyValidator)` mà không review việc setter thay thế hay compose. Nếu default checks bị thay, có thể chấp nhận wrong Destination/Issuer dù XML chữ ký đúng.

### 6.2. InResponseTo không được tự bỏ

Trong SP-initiated SSO:
- SP phát AuthnRequest ID và lưu request context.
- IdP Response/InResponseTo trỏ đúng request.
- SubjectConfirmationData.InResponseTo theo profile cũng phải correlate.
- Một custom validator không được bỏ correlation vì test IdP gửi sai request ID.

IdP-initiated/unsolicited flow, nếu tổ chức cho phép, là mode riêng không có pending AuthnRequest. Nó đòi stringent issuer/signature/audience/recipient/replay/login-CSRF policy, không phải lý do tắt validation cho SP-initiated.

### 6.3. Time/skew khi nâng

Spring provider có các APIs cấu hình AssertionValidator clock skew. Kiểm:
- NotBefore future vượt skew → reject.
- NotOnOrAfter hết hạn → reject.
- SubjectConfirmationData expiry riêng.
- Request/Assertion IssueInstant consistency theo policy.
- Replay cùng signed assertion dù chữ ký còn hợp lệ.
- Đồng bộ NTP giữa IdP, SP nodes.

Không đặt clock skew rất lớn để mọi static test fixtures sống mãi.

### 6.4. XML Signature Wrapping

XSW xảy ra khi verifier xác minh signed object A nhưng converter lấy NameID/attributes từ một object B chưa ký. Regression tests:
- Signed Assertion A, unsigned Assertion B.
- Duplicate XML IDs.
- Unexpected nested Assertion.
- Signature Reference URI trỏ object không phải consumed assertion.
- Multiple Assertions mixed signed/unsigned.
- Wrong KeyInfo trust.
- XML schema/namespace/DTD/XXE violations.

Nếu Response thực sự signed bao phủ AssertIon subtree, việc sửa nội dung con thường làm digest fail. Không mô tả như thể attacker có thể sửa bất kỳ signed XML mà signature vẫn valid; XSW là **signed scope và selection confusion**. Dùng OpenSAML validated object graph, không tự tìm `NameID` bằng global XPath.

## 7. Custom ResponseAuthenticationConverter: nguồn gốc identity

Một converter SAML hợp lệ có thể:
- Dùng persistent NameID hoặc approved stable attribute.
- Map verified attributes sang domain user.
- Gọi UserDetailsService để liên kết local account.
- Gán GrantedAuthority theo allowlist.
- Bảo tồn SAML assertion accessor cần cho SLO.

Nhưng không được:
- Đọc raw `SAMLResponse` khác với object đã verify.
- Lấy user/role từ request header hoặc query.
- Gán admin mặc định khi NameID null.
- Hợp nhất hai IdPs theo email trùng.
- Dùng signed Assertion A để hợp thức hóa attributes của unsigned B.
- Không kiểm user local active/tenant.
- Tự tạo authenticated token trước khi provider xác minh.
- Đánh rơi authentication factors/metadata mặc định mà target version yêu cầu.

### 7.1. Quy trình converter có delegation

~~~text
Validated ResponseToken in trusted OpenSAML provider
            |
            v
Built-in ResponseAuthenticationConverter
            |
            v
Verified Authentication + attributes
            |
            v
Approved issuer/subject -> localUserId lookup
            |
            v
Approved group/entitlement -> app authorities
            |
            v
Authentication with preserved SAML protocol context
~~~

Hook conversion có thể được gọi tại giai đoạn khác nhau giữa releases. Vì vậy không khẳng định “hễ converter nhận Response là mọi property đã được kiểm” mà không đọc source/API phiên bản mục tiêu. Luôn giữ default converter và bổ sung business mapping ở hook chính thức; không thay nó bằng một parser tự viết.

### 7.2. Tạo một domain principal contract ổn định

Ví dụ mô hình khái niệm:

~~~text
FederatedIdentity:
  protocol         = "SAML2" | "OIDC" | "KERBEROS" | "CAS"
  trustedIssuer    = canonical issuer / realm
  stableSubject    = verified subject identifier
  localUserId      = approved local identity link
  tenantId         = approved membership
  authorities      = allowlisted entitlements
~~~

Đây là schema thiết kế, không phải một Java class compile sẵn. Mục đích: controller/service không cast trực tiếp `Saml2AuthenticatedPrincipal` hay một internal OpenSAML implementation chỉ để lấy user ID. Cũng không flatten mọi identity thành email; stable subject và issuer scope rất quan trọng.

## 8. OIDC/OAuth2 Login: UserService và GrantedAuthoritiesMapper

Các extension points:
- `OAuth2AuthorizationRequestResolver`/Repository.
- ClientRegistration.
- Access token response client.
- `OidcUserService`, `OAuth2UserService`.
- `GrantedAuthoritiesMapper`.
- AuthenticationSuccessHandler/FailureHandler.
- Session/cookie/RequestCache.
- Logout endpoints.

Khi nâng, tránh viết lại toàn AuthenticationProvider chỉ vì cần gán app role.

### 8.1. Delegating OidcUserService

Spring reference giới thiệu mô hình:
~~~java
// Spring framework fragment; requires appropriate imports and configuration.
OidcUserService delegate = new OidcUserService();

OAuth2UserService<OidcUserRequest, OidcUser> service = request -> {
    OidcUser oidcUser = delegate.loadUser(request);

    // Add approved local identity link / entitlement lookup here.
    // Preserve the verified ID Token and identity contract.
    return oidcUser;
};
~~~

Đây là **fragment**, không phải standalone JDK class. Nó giữ default OIDC processing thay vì tự parse JSON từ browser. Đặc biệt cần kiểm UserInfo `sub` khớp ID Token `sub` theo OIDC contract và account linking không dựa chỉ trên email.

### 8.2. GrantedAuthoritiesMapper và role prefix

OIDC/OAuth2 login có thể tạo `OIDC_USER`/`OAUTH2_USER` và `SCOPE_*`; các authority này không phải business roles. App có thể map group IDs từ verified claims thành `ROLE_REPORT_VIEW` nhưng:
- Chỉ trust approved IdP issuer/client registration.
- Chỉ allowlist exact group IDs.
- Không tự biến arbitrary text `admin` thành ROLE_ADMIN.
- Không bỏ authorities mặc định quan trọng cho target version nếu adapter yêu cầu.
- Xử lý claim list/string/null/case/duplicates đúng policy.
- Có tests for group removed, missing group, disabled account.
- Những changes về factor authorities giữa versions phải được đánh giá theo contract, tránh assert exact full raw set vô lý nhưng vẫn assert no privilege escalation.

### 8.3. OIDC state/nonce/PKCE

Nếu custom AuthorizationRequestRepository hoặc redirect resolver thay đổi:
- State có thể mất giữa request và callback.
- Nonce có thể không được kiểm đúng.
- PKCE challenge/verifier mismatch.
- Callback URI mismatch với IdP registered redirect.
- Cookie SameSite/Secure hoặc forwarded Host/Proto khiến session không persistent.
- Multi-IdP client registration bị chọn sai.

**Không tắt state hoặc nonce để chữa callback 302/401.** Tách lỗi session/proxy với token validation và kiểm end-to-end.

## 9. JWT Resource Server: giữ JwtDecoder defaults

`oauth2ResourceServer().jwt()` phân lớp:
- `JwtDecoder` giải mã, verify signature/trusted issuer/algorithms, validate claims.
- `JwtAuthenticationConverter` map validated claims thành Authentication.
- `JwtGrantedAuthoritiesConverter` map scopes, mặc định thường có prefix `SCOPE_`.
- AuthorizationManager quyết định API permission, không phải decoder.

### 9.1. Lỗi custom decoder/validator hay gặp

- `NimbusJwtDecoder` tự tạo nhưng quên `JwtValidators.createDefaultWithIssuer`.
- Custom `setJwtValidator(audienceOnly)` thay defaults thay vì compose.
- Không đặt required audience validator cho API có audience contract.
- JWT `kid`/`jku` được dùng để tải arbitrary public key do client chỉ định.
- Tin issuer do query param/header chỉ định, không có approved issuer allowlist.
- Chấp nhận `alg=none`/weak algorithms ngoài policy.
- Dùng API access token như OIDC ID Token hoặc ngược lại.
- Mapping raw claim `roles` thành `ROLE_ADMIN` không có group/tenant policy.

### 9.2. Ví dụ Spring: compose issuer/time và Audience

Tệp `JwtValidationConfiguration.java` trong Spring Boot project:

~~~java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfiguration {

    private static final String ISSUER =
            "https://idp.example.org/issuer";
    private static final String AUDIENCE = "reporting-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audValidator = jwt -> {
            List<String> audiences = jwt.getAudience();
            if (audiences != null && audiences.contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Required audience is missing",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(ISSUER),
                        audValidator));
        return decoder;
    }
}
~~~

**Giải thích:**
- Đây là Spring configuration, không phải standalone `javac` file. Cần compatible OAuth2 Resource Server + JOSE modules và trusted issuer metadata/JWKS.
- Decoder thực hiện chữ ký/JWK trust, còn `JwtValidators.createDefaultWithIssuer` giữ expected issuer và thời gian theo framework version; custom audience được **bổ sung**.
- Có thể dùng config API khác trong target release; đây là mẫu nguyên tắc compose.
- Khi có nhiều JWT issuers, không suy ra trusted JWKS từ arbitrary token claim rồi tải; allowlist issuers và dùng decoder tương ứng.
- Test đúng 4 nhóm: valid, expired, wrong issuer, wrong audience, invalid signature.

### 9.3. JWT authority converter riêng

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter granted =
            new JwtGrantedAuthoritiesConverter();

    granted.setAuthoritiesClaimName("scope");
    granted.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(granted);
    return converter;
}
~~~

Đây là **bean fragment**, cần imports và cấu hình resource server. Nếu thực tế issuer gửi `scp` như list, `scope` như space-separated string, hoặc custom claim `roles`, converter phải theo đúng contract, không đoán từ unit test giả.

**Khi đổi prefix từ SCOPE_ sang ROLE_ có thể gây thay đổi phân quyền lớn.** Kiểm authorization policies trước khi sửa. Một token có scope `profile` không nên thành ROLE_ADMIN bằng logic mơ hồ.

## 10. AuthenticationProvider hoặc Manager tùy chỉnh là điểm rủi ro cao

Thay `AuthenticationProvider` có thể bỏ:
1. XMLDSig/JWT signature verification.
2. IdP trusted key/issuer checks.
3. SAML Audience/Recipient/Destination/Conditions.
4. OIDC nonce/state/PKCE.
5. InResponseTo/correlation.
6. Replay prevention theo profile.
7. Session fixation/cookie policies.
8. Authentication failure handling.
9. Local disabled account check.
10. Extra factor/authorities metadata của version mới.

**Quy tắc:** Nếu chỉ cần mapping business groups, dùng converter/mapper. Nếu chỉ cần một điều kiện bổ sung, compose validator. Chỉ thay Provider/Manager khi có lý do protocol-level rõ ràng và bộ integration tests đủ mạnh.

### 10.1. Không fallback sang Authentication cũ sau lỗi

Một anti-pattern:
~~~java
// Anti-pattern fragment: never use in production.
try {
    return customProvider.authenticate(request);
}
catch (Exception ignored) {
    return previousSessionAuthentication;
}
~~~

Đoạn minh họa không compile độc lập do thiếu context/types. Nó nguy hiểm vì lỗi invalid signature/issuer hoặc expired ticket có thể dẫn đến reuse một Authentication đáng tin cũ cho request hiện tại. **Fail closed** nếu credentials/protocol validation lỗi; exception handler không tự cấp identity.

## 11. Multi-IdP và tenant mapping

Một ứng dụng có hai identity sources:
~~~text
registrationId=staff
issuer=urn:example:saml:staff-idp
trusted public signing certs=STAFF
tenant=employees

registrationId=partners
issuer=urn:example:saml:partners-idp
trusted public signing certs=PARTNERS
tenant=partners
~~~

Custom `RelyingPartyRegistrationRepository`/resolver phải map đúng:
- SAML Request context và SP entityID.
- Approved IdP issuer/signing keys.
- ACS/Recipient/Destination.
- Audience, Conditions và signature scope.
- Local subject link và tenant/role membership.

Không chọn registration chỉ dựa raw `X-Forwarded-Host` hoặc user email. Khi ingress dùng dynamic tenant routing, public hostname đã được allowlist/proxy normalized nhưng IdP key trust vẫn phải do server-side registration quyết định.

Với OIDC, `iss+sub` tạo identity namespace. Với SAML, IdP issuer + stable NameID/qualifiers hoặc approved persistent attribute. Với Kerberos, realm + full principal. Hai users cùng email ở hai issuers không mặc nhiên là một local user.

## 12. LDAP, Kerberos, CAS và adapter cũ

Ngoài các web federation protocols, ứng dụng có thể tích hợp:
- **LDAP/AD:** `LdapBindAuthenticationManagerFactory`, LDAPS/StartTLS, user/group search, nested roles, DN/filter escaping.
- **Kerberos/SPNEGO:** GSS token, keytab, service principal `HTTP/host@REALM`, enctypes/JDK, group mapping.
- **CAS:** service ticket validation, server/service URLs, login/logout callbacks, authorities.
- **X.509 preauth:** client cert trust, TLS termination, mapping validated subject.
- **Custom enterprise token adapter:** proprietary claims mapped sang Authentication.

Khi nâng:
- Kiểm vendor adapter version hỗ trợ target Spring API/JDK.
- Không dùng username không có realm/issuer làm unique account ID.
- Không trust `X-Forwarded-User`/`X-Remote-User` từ HTTP request tùy ý.
- Không bỏ LDAPS trust certificate validation vì CA thay đổi.
- Không cấp roles dựa only successful Kerberos ticket nếu local user disabled.
- CAS ticket/service binding phải còn được xác minh.
- Test no service principal, invalid ticket, wrong realm, expired ticket, group missing.

**Việc directory lookup trả user entry không đồng nghĩa user đã authenticate.** Conversion nên nhận validated identity result, không tự coi một LDAP query thành login.

## 13. Kiểm filter chain và callback routing

Một upgrade có thể làm custom validator **không được gọi** vì request đi vào chain khác. Rà soát:
- `SecurityFilterChain` order.
- `securityMatcher` và `requestMatchers`.
- SAML ACS `/login/saml2/sso/{registrationId}`.
- OIDC callback `/login/oauth2/code/{registrationId}`.
- API JWT resource server paths.
- CSRF exemptions đúng phạm vi callback.
- `SessionCreationPolicy` và `SecurityContextRepository`.
- `RequestCache`, SavedRequest, success/failure handlers.
- Proxy forwarded headers và external public origin.
- SAML SLO, OIDC logout, session invalidation.

### 13.1. Baseline Spring Security Servlet

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Đây là class Spring configuration**, cần dependencies và RelyingPartyRegistration tin cậy. Trong integration branch, có thể so đường default này với custom provider để tìm extension gây regression. Không dùng baseline `anyRequest().authenticated()` thay cho domain authorization thực của production.

### 13.2. Session cookies và CSRF

SAML POST callback/OIDC redirect có thể gặp lỗi sau Spring version change do:
- Cookie Secure/SameSite/Domain/Path.
- HTTP vs HTTPS public origin.
- Proxy forward headers chưa được sanitize.
- Session state không persist sau authentication.
- CSRF filter chain path mismatch.
- IdP-initiated vs SP-initiated correlation.
- Multi-node session store và stale serialized principal.

Không tắt CSRF toàn hệ thống để test login pass; chỉ thiết kế exemption đúng callback protocol theo Spring configuration và kiểm browser E2E.

## 14. Unit Java 17: mô phỏng compose default và custom validators

Chương trình chạy với JDK 17+ và không cần framework. **Mục đích:** hiểu vì sao một custom-only validator có thể chấp nhận token ký bằng key không tin, còn default-only validator không chặn wrong Audience mới yêu cầu.

Tệp `ValidatorCompositionDemo.java`:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.function.Predicate;

public class ValidatorCompositionDemo {

    record Token(
            String issuer,
            String audience,
            Instant expiresAt,
            String subject,
            boolean trustedSignature) {
    }

    static boolean allPass(
            Token token,
            List<Predicate<Token>> validators) {

        return validators.stream().allMatch(v -> v.test(token));
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-06-01T12:00:00Z");

        Predicate<Token> issuer =
                t -> "https://idp.example.org".equals(t.issuer());
        Predicate<Token> notExpired =
                t -> now.isBefore(t.expiresAt());
        Predicate<Token> trustedSigner =
                Token::trustedSignature;
        Predicate<Token> approvedAudience =
                t -> "reporting-api".equals(t.audience());

        List<Predicate<Token>> defaults =
                List.of(issuer, notExpired, trustedSigner);
        List<Predicate<Token>> composed =
                List.of(issuer, notExpired, trustedSigner, approvedAudience);

        Token valid = new Token(
                "https://idp.example.org", "reporting-api",
                now.plusSeconds(300), "synthetic-user-001", true);
        Token wrongKey = new Token(
                "https://idp.example.org", "reporting-api",
                now.plusSeconds(300), "synthetic-user-002", false);
        Token wrongAudience = new Token(
                "https://idp.example.org", "other-api",
                now.plusSeconds(300), "synthetic-user-003", true);

        System.out.println("valid=" + allPass(valid, composed));
        System.out.println("wrong-key-custom-only=" +
                allPass(wrongKey, List.of(approvedAudience)));
        System.out.println("wrong-key-composed=" +
                allPass(wrongKey, composed));
        System.out.println("wrong-audience-default-only=" +
                allPass(wrongAudience, defaults));
        System.out.println("wrong-audience-composed=" +
                allPass(wrongAudience, composed));
    }
}
~~~

Chạy:
~~~bash
javac ValidatorCompositionDemo.java
java ValidatorCompositionDemo
~~~

**Stdout chính xác:**
~~~text
valid=true
wrong-key-custom-only=true
wrong-key-composed=false
wrong-audience-default-only=true
wrong-audience-composed=false
~~~

**Giới hạn:** `trustedSignature` trong demo chỉ là boolean giả định. Production không bao giờ tin cờ `signatureValid=true` từ browser; phải dùng OpenSAML/JwtDecoder verify chữ ký thật, IdP/JWK trust, time, issuer, audience, correlation và replay. Mã chỉ minh họa việc **đánh mất default validators**.

## 15. Unit Java 17: chuyển đổi role theo issuer và tenant

Chương trình thứ hai minh họa allowlisted group mapping. Identity trong record **giả định đã qua upstream authentication**; mã không thay SAML/OIDC/Kerberos token validator.

Tệp `FederatedAuthorityPolicyDemo.java`:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class FederatedAuthorityPolicyDemo {

    record Identity(
            String issuer,
            String subject,
            String tenant,
            List<String> groups,
            boolean previouslyVerified) {
    }

    static Set<String> authorities(Identity user) {
        if (!user.previouslyVerified()) {
            return Set.of();
        }
        if (!"urn:example:idp:staff".equals(user.issuer())) {
            return Set.of();
        }
        if (!"tenant-a".equals(user.tenant())) {
            return Set.of();
        }
        if (user.subject() == null
                || user.subject().isBlank()) {
            return Set.of();
        }

        Set<String> result = new HashSet<>();
        result.add("ROLE_USER");
        if (user.groups().contains("ReportReaders")) {
            result.add("ROLE_REPORT_VIEW");
        }
        return Set.copyOf(result);
    }

    static String display(Set<String> roles) {
        return roles.stream().sorted().toList().toString();
    }

    public static void main(String[] args) {
        Identity alice = new Identity(
                "urn:example:idp:staff", "u-1001", "tenant-a",
                List.of("ReportReaders", "Admin"), true);
        Identity unsigned = new Identity(
                "urn:example:idp:staff", "u-1001", "tenant-a",
                List.of("ReportReaders"), false);
        Identity otherIdp = new Identity(
                "urn:example:idp:partner", "u-1001", "tenant-a",
                List.of("ReportReaders"), true);
        Identity otherTenant = new Identity(
                "urn:example:idp:staff", "u-1001", "tenant-b",
                List.of("ReportReaders"), true);

        System.out.println("alice=" +
                display(authorities(alice)));
        System.out.println("unsigned=" +
                display(authorities(unsigned)));
        System.out.println("other-idp=" +
                display(authorities(otherIdp)));
        System.out.println("other-tenant=" +
                display(authorities(otherTenant)));
    }
}
~~~

Chạy:
~~~bash
javac FederatedAuthorityPolicyDemo.java
java FederatedAuthorityPolicyDemo
~~~

**Stdout chính xác:**
~~~text
alice=[ROLE_REPORT_VIEW, ROLE_USER]
unsigned=[]
other-idp=[]
other-tenant=[]
~~~

**Giải thích:** Claim group `Admin` xuất hiện trong list của Alice nhưng app không cấp ROLE_ADMIN vì nó không thuộc allowlist; token/identity khác IdP hoặc tenant bị từ chối. Một mapper chỉ trả rỗng chưa tự deny HTTP request — AuthorizationManager phải tiếp tục kiểm endpoint/resource.

**Giới hạn:** `previouslyVerified` là tín hiệu mô phỏng nội bộ, không phải trust proof. Không copy record này làm production security model mà thiếu signature verification, identity linking, active-account check và SAML/OIDC protocol.

## 16. Ma trận kiểm thử hồi quy cho SAML/OIDC/JWT

| Test | Input/điều kiện | Kỳ vọng |
|---|---|---|
| S01 | SAML Response ký đúng trusted IdP | Authentication success nếu conditions pass |
| S02 | SAML Assertion ký đúng trusted IdP | Authentication success nếu conditions pass |
| S03 | Unsigned Response và unsigned Assertion | Reject |
| S04 | Signature bytes/digest bị sửa sau ký | Reject signature |
| S05 | IdP signing key không trong registration trust | Reject |
| S06 | Correct signature nhưng Audience sai | Reject Audience |
| S07 | Correct signature nhưng Destination sai | Reject |
| S08 | Correct signature nhưng Recipient sai | Reject |
| S09 | Correct signature nhưng InResponseTo sai | Reject SP-initiated |
| S10 | NotBefore tương lai hoặc NotOnOrAfter expired | Reject time |
| S11 | Missing NameID nhưng converter yêu cầu | Reject, không fallback user |
| S12 | Stable alternate subject approved và protected | Accept chỉ theo policy |
| S13 | Signed Assertion A và unsigned B được app chọn | Reject XSW |
| S14 | Duplicate XML IDs/multiple Assertions không hỗ trợ | Reject |
| S15 | EncryptedAssertion valid, correct SP private key | Correct decrypt/validate |
| S16 | EncryptedAssertion wrong decryption key | Reject |
| S17 | Unknown registrationId/issuer | No authenticated session/no loop |
| S18 | SAML HTTP GET Response disallowed by policy | No login from GET |
| S19 | SAML LogoutRequest invalid | Proper error per target version |
| S20 | New principal/accessor implementation | Stable user mapping and SLO |
| O01 | OIDC Authorization Code + valid ID Token | Login correct iss+sub |
| O02 | ID Token signature/issuer/audience wrong | Reject |
| O03 | State/nonce/PKCE mismatched | Reject |
| O04 | UserInfo sub khác ID Token sub | Reject per OIDC policy |
| O05 | Same email hai issuers | Không merge local accounts |
| O06 | Verified group approved | Map correct ROLE_REPORT_VIEW |
| O07 | Unapproved Admin group | No elevated authority |
| O08 | UserInfo timeout | Fail closed or explicit limited policy |
| O09 | OIDC callback success, session cookie lost | Detect persistence regression |
| J01 | Signed JWT correct issuer/aud/time | API authenticated |
| J02 | Wrong JWT signature/alg | Reject |
| J03 | Wrong JWT issuer | Reject |
| J04 | Missing/wrong required audience | Reject |
| J05 | Expired JWT | Reject |
| J06 | Future nbf outside skew | Reject |
| J07 | Valid token lacks required scope | Authorization deny, usually 403 |
| J08 | Untrusted custom roles claim | No privilege escalation |
| J09 | Unknown kid/arbitrary JWK URL | No untrusted signer accepted |
| A01 | URL matcher requires role not present | 403 |
| A02 | @PreAuthorize tenant/owner mismatch | Deny |
| A03 | CSRF token absent on protected POST | Reject |
| A04 | Multiple filter chains | Correct callback and API chain selection |
| A05 | Browser session serialized across versions | Defined behavior, no wrong principal |
| A06 | Unknown login path after upgrade | No permissive fallback |
| A07 | Enabled resource server but browser OAuth2 session | Correct 401/302 semantics |
| A08 | Logout/SP-initiated session revocation | Works under protocol policy |

**Phân biệt 3 negative types:** “tamper-after-sign” phải thất bại ở signature; “wrong signing key” phải thất bại ở trust; “wrong Audience **được ký đúng sau khi đặt giá trị sai**” phải thất bại ở protocol validation. Nếu sửa Audience sau signing, bạn chưa test AudienceValidator mà chỉ test XMLDSig.

## 17. Tầng kiểm thử và độ tin cậy

### 17.1. Unit tests

Dùng JUnit 5 hoặc Java 17 standalone:
- Claim parsing/map.
- Null NameID/subject.
- Group allowlist/case.
- Role prefix.
- Issuer+subject/tenant linking.
- Default+custom validator composition.
- Error mapping/diagnostic categories.

Unit tests có mock `Jwt` hoặc `Saml2AuthenticatedPrincipal` **không chứng minh chữ ký thật**.

### 17.2. Provider-level integration tests

- Dựng test IdP keypair/metadata riêng, Spring SP chỉ trust public cert.
- Tạo real signed SAMLResponse/Assertion qua OpenSAML/test IdP.
- Kiểm chữ ký, issuer, audience, recipient, destination, time, InResponseTo.
- Chạy XML Signature Wrapping/duplicate ID tests.
- Dùng test JWT issuer/JWKS với ký thật; kiểm wrong signer/issuer/aud/time.
- Assert không tạo authenticated SecurityContext từ invalid input.
- Assert principal/authorities được tạo từ verified content.

**Không mang private keys production vào tests**. Dùng synthetic subjects và isolated test network.

### 17.3. HTTP/browser E2E

1. Browser GET protected URL.
2. Spring tạo SAML AuthnRequest hoặc OIDC AuthorizationRequest.
3. Test IdP nhận request và phát signed response.
4. Browser callback đến đúng ACS/redirect URI.
5. Spring verify, lưu SecurityContext/session.
6. Request sau được authenticate và authorized đúng.
7. Request thiếu role/tenant bị deny.
8. Logout/SLO và session cleanup.
9. Failure path không redirect loop.
10. Origin/forwarded headers, cookie SameSite/Secure, CSRF được kiểm.

REST Resource Server stateless nên gửi Bearer JWT cho mỗi request, không dùng OIDC browser session làm bằng chứng tự động.

## 18. MockMvc và test policy

Spring Security test helpers có thể mô phỏng authenticated user để test HTTP/method authorization. Ví dụ:

~~~java
// JUnit/MockMvc fragment inside a configured Spring Boot test.
mvc.perform(get("/reports/view/demo")
        .with(user("synthetic-user")
            .authorities(() -> "ROLE_REPORT_VIEW")))
    .andExpect(status().isOk());

mvc.perform(get("/reports/approve/demo")
        .with(user("synthetic-user")
            .authorities(() -> "ROLE_REPORT_VIEW")))
    .andExpect(status().isForbidden());
~~~

Fragment này cần imports/static imports và endpoints tồn tại; nó **không phải standalone Java file**. `user()` bypass thực token validation, do đó không gắn nhãn “SAML signature verified” cho test này.

Khi test POST role-denial, hãy cung cấp CSRF token hợp lệ nếu CSRF được bật; nếu thiếu CSRF thì 403 có thể do CsrfFilter trước khi role validator chạy.

## 19. Quy trình migration từng bước có thể kiểm soát

### 19.1. Baseline

1. Ghi versions và dependency tree.
2. Chụp danh mục custom hooks.
3. Lưu security config/RP/client registration contract.
4. Chạy positive + negative tests trên version cũ.
5. Tạo sanitized baseline authn/authz metrics.
6. Đặt canary rollback plan.
7. Kiểm SAML/XMLDSig/JWT signing algorithms hiện có.
8. Xác nhận vendor adapters có bản hỗ trợ target.

### 19.2. Nâng từ nhỏ đến lớn

1. Chọn version mới chính xác; dùng Spring Boot dependency management.
2. Xử lý deprecated APIs theo migration guide.
3. Chạy app với framework defaults trong test branch để so sánh.
4. Thêm lại từng custom validator bằng composition.
5. Thêm lại converters/mappers với verified identity contract.
6. Chạy negative security suite sau **mỗi hook**.
7. Test session/rolling restart, logout/SLO, multi-IdP.
8. Test browser/public URLs/callbacks qua proxy thật.
9. Review source diff theo những trust boundaries bị ảnh hưởng.
10. Chốt release chỉ khi no security regression.

### 19.3. Mỗi extension change cần lý do

Ghi một Architecture Decision Record ngắn:
- Hook cũ/hook mới.
- Vì sao cần custom behavior.
- Default validators được giữ.
- Input đã verified hay chưa.
- Invariants liên quan.
- Unit/integration test IDs.
- Failure semantics.
- Security reviewer/owner.
- Rollback approach.

Không đưa một exception “catch all, return true” vào production chỉ để migration xanh.

## 20. Quan sát và chẩn đoán sau nâng cấp

Phân biệt:
- `authentication_failure`: token/assertion/credential không hợp lệ.
- `authentication_success`: trusted identity được tạo.
- `authorization_denied`: user đã authenticate nhưng thiếu business role/tenant.
- `registration_not_found`: routing/IdP resolution issue.
- `state_or_correlation_invalid`: OIDC state/SAML InResponseTo mismatch.
- `session_not_persisted`: cookie/repository/rolling upgrade.
- `saml_logout_error`: SLO protocol failure.
- `authority_mapping_changed`: role mapping drift.

Spring Security logging/debug và Micrometer Observations có thể hỗ trợ nhưng event names/enablement phụ thuộc version/config. Không tự mặc định mọi AuthenticationSuccessEvent đều được phát trong mọi SSO flow.

### 20.1. Metrics mẫu (đề xuất, không phải mặc định)

~~~text
security_authn_success_total{protocol,registration}
security_authn_failure_total{protocol,failure_category}
security_authz_denied_total{policy_category}
saml_signature_failure_total{registration}
saml_unknown_registration_total{registration_category}
oidc_callback_state_error_total{client_category}
jwt_audience_mismatch_total{issuer_category}
role_mapping_rejected_total{policy_category}
slo_error_total{registration}
~~~

Không dùng raw NameID, `sub`, email, JWT, dynamic URI, token, IP address hay arbitrary tenant ID làm metric labels. Chúng gây high cardinality và có thể lộ dữ liệu cá nhân.

### 20.2. Không log thông tin nhạy cảm

Cấm ghi vào logs/tickets:
- Raw SAMLResponse/Assertion XML/Base64.
- ID Token, access token, refresh token, Authorization Code.
- Session cookies, Kerberos Negotiate ticket.
- IdP/SP private signing/decryption keys.
- LDAP passwords/bind credentials.
- Claim chứa sensitive PII.
- JWT HMAC/shared secrets.

Dùng trace ID, approved issuer/registration category, error type, anonymized user reference khi policy cho phép.

## 21. Troubleshooting matrix

| Triệu chứng sau nâng | Nguyên nhân khả dĩ | Bước kiểm |
|---|---|---|
| SAML NameID null gây NPE | NameID presence assumption đổi | Validate required subject in converter |
| SAML callback redirect liên tục | No-registration/entrypoint behavior | RelyingPartyRegistration resolver |
| SAML XML signature invalid | OpenSAML5/algorithm/metadata mismatch | Real signed fixture + cert |
| SAML Audience sai được chấp nhận | Custom validator mất default | Compose + negative test |
| SAML Response signed nhưng user sai | Custom converter chọn unsigned object | XSW/provenance test |
| SAML logout nay trả error Response | SLO behavior đổi | Verify protocol/handler |
| SAML principal ClassCastException | New Authentication representation | Stable principal adapter |
| OIDC login success nhưng roles trống | Claim/mapper format đổi | Trusted claims + authorities |
| OIDC state/nonce fail | Cookie/AuthorizationRequestRepository | Browser callback trace |
| JWT API token 401 hàng loạt | Decoder issuer/JWKS/expiry policy | JwtDecoder configuration |
| JWT signature valid nhưng 403 | SCOPE_/ROLE_ mismatch | Converter and URL policy |
| Wrong-audience JWT accepted | Missing custom audience validator | Signed-invalid-aud test |
| Unknown JWT issuer accepted | Overbroad dynamic issuer resolver | Strict allowlist |
| Same email map sai tenant | Subject linking only email | Issuer+stable subject |
| 403 sau login callback | Method/tenant/CSRF | Authn vs authz distinction |
| User login ở node A, node B anonymous | Session serialization/store drift | Cross-version rolling tests |
| Key rotation IdP lỗi | Approved metadata/key overlap mismatch | Credential trust set |
| Kerberos sai SPN sau JVM update | GSS/keytab/enctype compatibility | Validate service tickets |
| CAS service ticket loop | Service URL/redirect changes | CAS validator and proxy origin |
| Test pass dù SAMLResponse unsigned | Mocked provider/permitAll path | Real provider E2E and negative suite |

### 21.1. Debug theo thứ tự

1. Xác định request failure là authn, session hay authorization.
2. Kiểm đúng SecurityFilterChain.
3. Kiểm IdP/client registration và trusted credentials.
4. Kiểm signature/issuer/audience/time/correlation validators.
5. Kiểm converter tạo đúng principal + authorities.
6. Kiểm local identity link, tenant và @PreAuthorize.
7. Kiểm callback public origin/redirect/session cookies.
8. Kiểm observed behavior của target release vs migration notes.
9. Thêm regression test cô lập nguyên nhân.
10. Không vô hiệu hóa controls để chữa symptom.

## 22. Rollout, canary, rollback và session compatibility

Một nâng cấp SAML/OIDC có thể đổi class của Authentication/Principal. Nếu session lưu trong Redis/Java serialization hoặc custom session codec, rolling deployment có thể khiến node mới không đọc được SecurityContext do node cũ ghi.

Cách chuẩn bị:
- Kiểm serializability/session storage format.
- Test cross-version read/write nếu zero-downtime yêu cầu.
- Khi không bảo đảm, cân nhắc session invalidation và yêu cầu người dùng SSO lại.
- Kiểm logout/SLO trước–sau rollback.
- Không deserialize untrusted bytes thành arbitrary principal bằng insecure polymorphic mapping.
- Giám sát callback failures, session loops, unexpected elevated authorities.
- Canary theo IdP/tenant approved, không thử trên production accounts nhạy cảm.
- Rollback code không làm mở lại trust cho deprecated algorithms/issuers.
- Có documented communication nếu cần login lại sau upgrade.

**Điều quan trọng:** Rollback không phải “đổi property chấp nhận mọi token cũ”. Cần bảo toàn signature/issuer/time validation, và vô hiệu hóa sessions không tương thích theo policy.

## 23. Checklist review trước release

- [ ] Đã ghi exact old/target Spring Security, Boot, OpenSAML/JDK versions.
- [ ] Đã rà mọi AuthenticationProvider, validators, converters, mappers, resolvers.
- [ ] Đã đọc migration guide theo đúng major/minor release.
- [ ] Không có parser tự đọc raw SAMLResponse để sinh principal.
- [ ] SAML signature/trusted IdP signing credentials còn được verify.
- [ ] Assertion được dùng nằm trong trusted signed coverage.
- [ ] ResponseValidator/AssertionValidator giữ các checks bắt buộc.
- [ ] NameID missing/alternate stable ID policy có negative tests.
- [ ] Issuer/Audience/Destination/Recipient/Conditions/InResponseTo được kiểm.
- [ ] Unknown registrationId không tạo login hoặc redirect loop.
- [ ] SLO/LogoutResponse behavior theo đúng target release.
- [ ] Authentication/principal/accessor change không làm sai account mapping.
- [ ] OIDC ID Token issuer/audience/time, state/nonce/PKCE được kiểm.
- [ ] UserInfo subject binding và approved identity link còn đúng.
- [ ] JWT Decoder verify signature, issuer, expiry, nbf, required audience.
- [ ] JWT authority prefix/claim conversion đúng contract.
- [ ] Không có arbitrary `ROLE_ADMIN` từ untrusted claim.
- [ ] Multi-IdP tenant routing và localUserId mapping tách biệt.
- [ ] Kerberos/CAS/LDAP adapter theo supported version.
- [ ] SecurityFilterChain và MethodSecurity policies còn enforce.
- [ ] CSRF/session/cookie/redirect_uri/SAML ACS settings đúng.
- [ ] Có unit tests Java17 cho mapping/composition.
- [ ] Có real signed SAML + JWT integration security tests.
- [ ] Có negative tests XSW, replay, wrong key, missing signature, wrong audience.
- [ ] Không log tokens/keys/PII.
- [ ] Có release gates, metrics, canary, rollback và session handling plan.
- [ ] Mọi lỗi validator/decoder đều fail closed; không permissive fallback.

## 24. Câu hỏi ôn tập

1. **Validator khác converter?** Một bên xác minh dữ liệu, bên kia ánh xạ dữ liệu đã kiểm.
2. **Tại sao build PASS chưa chứng minh nâng cấp an toàn?** Có thể bỏ default checks mà app vẫn chạy.
3. **ResponseValidator.withDefaults có ý nghĩa gì?** Giữ built-in Response validation khi bổ sung rule tùy chỉnh.
4. **OpenSAML5 quan trọng thế nào?** Provider model, XMLDSig/decryption, APIs và behavior cần kiểm lại.
5. **Spring Security 7 thay đổi gì với NameID?** Custom converter phải rõ policy khi presence validation order/default dịch chuyển.
6. **Vì sao Saml2ResponseAssertionAccessor đáng chú ý?** Dữ liệu assertion tách khỏi principal cho workflows như logout.
7. **Unknown RelyingPartyRegistration sau upgrade có thể gây gì?** Redirect loop/khác handler, không được cấp Authentication.
8. **SAML LogoutRequest invalid có thể trả gì?** SAML LogoutResponse lỗi theo target protocol behavior.
9. **GET SAMLResponse nên được xử lý thế nào?** Theo binding/profile và policy, không tạo login tùy ý.
10. **Signature valid nhưng Audience sai?** Reject.
11. **KeyInfo do browser tự khai là trust anchor?** Không.
12. **Có thể dùng attributes của unsigned assertion B khi signed A valid?** Không.
13. **OIDC_USER có nghĩa ROLE_ADMIN?** Không.
14. **Cặp identity key quan trọng trong OIDC?** Approved issuer + stable subject.
15. **JwtAuthenticationConverter tự verify JWT không?** Không, decoder chịu trách nhiệm.
16. **Khi thêm Audience validation làm gì để không mất defaults?** Compose issuer/time validators với audience rule.
17. **SCOPE_profile và ROLE_ADMIN có tương đương không?** Không.
18. **Nếu custom group converter gặp null claim?** Không cấp quyền vượt policy.
19. **Có nên bỏ state/nonce để sửa callback fail?** Không.
20. **Nếu local user disabled nhưng SAML valid?** App phải deny business access.
21. **Một MockMvc user() test có kiểm signature thật?** Không.
22. **Negative test wrong audience phải ký trước hay sau đặt sai audience?** Đặt sai rồi ký lại.
23. **Khi session serialization đổi, phải làm gì?** Test rolling deployment hoặc invalidate sessions có kiểm soát.
24. **Khi nhiều IdP cùng email, có auto merge local user?** Không.
25. **Có thể tin X-Forwarded-User trực tiếp?** Không.
26. **Khi token sai issuer mà vẫn accepted?** Release blocker vì validation regression.
27. **Vì sao phải test HTTP, method và domain authorization?** Login đúng không tự cấp quyền mọi resource.
28. **Rà soát quan trọng nhất khi upgrade?** Giữ default cryptographic/protocol validators và trusted identity provenance.
29. **Có thể log raw SAMLResponse để debug?** Không, có thông tin nhạy cảm.
30. **Dấu hiệu hoàn tất migration?** Positive path pass, negative inputs vẫn reject, roles đúng, operations/canary/rollback được kiểm.

## 25. Tài liệu tham khảo

- Spring Security – Migrating to 7: https://docs.spring.io/spring-security/reference/migration/
- Spring Security – Servlet SAML2 Migrations: https://docs.spring.io/spring-security/reference/7.0/migration/servlet/saml2.html
- Spring Security – SAML2 Authenticating Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Relying Party Configuration: https://docs.spring.io/spring-security/reference/servlet/saml2/login/relying-party.html
- Spring Security – OAuth2 Login Advanced, UserService and GrantedAuthoritiesMapper: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security – OAuth2 Login Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Boot – Dependency Management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- OWASP – SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- OWASP – JSON Web Token for Java Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
- OWASP – Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OASIS – SAML Core 2.0: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS – SAML Web Browser SSO Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf

**Tổng kết:** Rà soát validator và converter tùy chỉnh là nhiệm vụ bảo mật chứ không chỉ sửa API khi nâng Spring Security federation. Mọi upgrade phải giữ hoặc chủ động tăng các kiểm soát **trusted signature → issuer → audience/recipient/destination → lifetime/correlation → validated subject → approved roles → resource authorization**. Đặc biệt khi chuyển Spring Security 6→7, cần xác minh các khác biệt OpenSAML5, NameID/principal, missing registration và SLO. Chỉ phát hành sau khi negative security fixtures chứng minh dữ liệu giả mạo vẫn bị reject, không có identity/tenant/role escalation và khả năng quan sát/rollback được chuẩn bị.
