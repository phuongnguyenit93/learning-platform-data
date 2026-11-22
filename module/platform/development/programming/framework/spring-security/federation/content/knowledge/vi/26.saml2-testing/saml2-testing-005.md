# Kiểm thử SP-initiated SSO từ AuthnRequest đến phiên ứng dụng

**Học phần:** Spring Security – federation → Kiểm thử SAML2.

**Mục tiêu:** kiểm thử toàn bộ **SP-initiated SAML 2.0 Web Browser SSO** trong ứng dụng Java/Spring Security, bắt đầu bằng một request chưa xác thực đến ứng dụng (Service Provider/Relying Party), phát sinh `AuthnRequest`, đi qua IdP/Asserting Party, nhận `SAMLResponse` tại Assertion Consumer Service (ACS), xác minh assertion, tạo `Authentication`, lưu phiên ứng dụng và truy cập tài nguyên được bảo vệ. Không dừng ở “HTTP 302 đúng” hoặc “trang login IdP hiện ra”; một test đạt yêu cầu phải chứng minh **người dùng đã được xác thực bằng assertion đúng và session thật sự hoạt động ở request tiếp theo**.

**Nguyên tắc QA:** tách rõ **protocol validation** (chữ ký, Issuer, Audience, Destination, InResponseTo, SubjectConfirmation, time/replay), **authentication/session persistence** (Spring SecurityContext, session cookie, session fixation) và **business authorization** (role, tenant, account, resource). Ba việc này không thay thế nhau.

Bài sử dụng ví dụ **Spring Security 7.x/Spring Boot 4.x và Java 17+** theo contract hiện hành. Với Spring Security 6.x, cấu trúc chính tương tự nhưng phải đối chiếu API, OpenSAML và cấu hình theo đúng BOM/runtime. Các tên miền `example.test` và certificate test chỉ mang tính minh họa. Mã cấu hình Spring là **mảnh tích hợp**, cần IdP sandbox/metadata/credentials thật; chương trình Java 17 riêng ở phần thực hành chạy độc lập và chỉ mô phỏng invariants, **không tạo/chấp nhận assertion SAML thật**.

## 1. Thành phần và dữ liệu cần quan sát

Một mô hình kiểm thử tiêu biểu:

| Thành phần | Giá trị minh họa | Vai trò |
| --- | --- | --- |
| SP ứng dụng | `https://portal.example.test` | Spring Security web app |
| SP EntityID | `https://portal.example.test/saml/sp` | Định danh Relying Party được IdP tin |
| Registration ID | `corp` | Khóa cấu hình Spring `RelyingPartyRegistration` |
| Protected resource | `/reports` | Yêu cầu login |
| AuthnRequest endpoint | `/saml2/authenticate/corp` | Bắt đầu SP-initiated login |
| IdP EntityID / Issuer | `https://idp.example.test/metadata` | Asserting Party được tin |
| IdP SSO Service | `https://idp.example.test/sso` | Nhận AuthnRequest |
| ACS | `https://portal.example.test/login/saml2/sso/corp` | Nhận SAMLResponse qua browser POST |
| Test user | `user-17` | Subject test trong sandbox |
| App user | `U-100` | Tài khoản nội bộ sau verified mapping |
| Browser session | `JSESSIONID` hoặc session ID do cấu hình ứng dụng dùng | Chứa state trước/sau login theo kiến trúc |
| SAML trust | IdP signing certificate + SP signing/decryption credentials theo yêu cầu | Chống giả mạo/thay đổi SAML messages |

**Không nhầm** `Registration ID` (`corp`) với `SP EntityID` hay `IdP EntityID`. `registrationId` là khóa cấu hình cục bộ. `Issuer` của AuthnRequest phải là SP EntityID; `Issuer` của Response/Assertion phải khớp IdP đã được tin. `Audience` trong assertion thường phải khớp SP EntityID; `Recipient`/`Destination` phải hướng tới ACS phù hợp.

### 1.1. Kiểm thử cả “đi” lẫn “về”

- **Đi:** trình duyệt chưa login được redirect tới đúng IdP; AuthnRequest hợp lệ, có `ID` và `IssueInstant`, `Destination`/`Issuer`/`AssertionConsumerServiceURL` hoặc ACS index phù hợp, binding đúng và ký request nếu IdP yêu cầu.
- **Ở IdP:** một tài khoản thử nghiệm được xác thực, IdP biết đúng SP registration, phát Response và assertion theo contract.
- **Về:** browser gửi POST `SAMLResponse` và `RelayState` tại ACS; Spring resolve được RelyingPartyRegistration và pending request; chữ ký/conditions/subject được xác minh.
- **Sau:** Spring tạo `Saml2Authentication`/principal, ánh xạ user nội bộ, lưu session/SecurityContext; request tiếp theo đến `/reports` với cookie phiên được phép truy cập, trong khi browser phiên khác vẫn chưa xác thực.

**Không dùng OIDC `code` hoặc CAS `ticket` thay `SAMLResponse`.** Đây là luồng SAML Web Browser SSO, không phải OAuth Authorization Code hay CAS Login.

## 2. Luồng SP-initiated SSO chuẩn

```mermaid
sequenceDiagram
    actor User as Browser của user
    participant SP as Spring Security SP
    participant Store as AuthnRequest Repository / Session
    participant IdP as SAML2 Identity Provider
    participant App as App user/authorization
    User->>SP: GET /reports (không có phiên)
    SP-->>User: 302 /saml2/authenticate/corp
    User->>SP: GET /saml2/authenticate/corp
    SP->>Store: Lưu AuthnRequest ID, RelayState, session, IdP
    SP-->>User: 302 tới IdP SSO + SAMLRequest + RelayState
    User->>IdP: GET SSO URL chứa AuthnRequest
    IdP->>IdP: Validate SP, request, signature/policy
    IdP->>IdP: Authenticate test user
    IdP-->>User: HTML form POST SAMLResponse tới SP ACS
    User->>SP: POST /login/saml2/sso/corp
    SP->>Store: Resolve pending AuthnRequest và correlation
    SP->>SP: Validate signature/issuer/audience/recipient/time/replay
    SP->>App: Map NameID/attributes -> internal user, roles
    App-->>SP: U-100 + authorities
    SP->>SP: Create Authentication; persist SecurityContext/session
    SP-->>User: Redirect về safe route /reports
    User->>SP: GET /reports kèm cookie phiên
    SP->>SP: Load SecurityContext từ session
    SP->>App: Authorize U-100 xem reports
    App-->>SP: ALLOW
    SP-->>User: 200 HTML/JSON dành cho U-100
```

Đây là sơ đồ điển hình **Redirect binding cho AuthnRequest và POST binding cho Response**; Spring/IdP có thể chọn POST cho AuthnRequest hoặc binding khác theo metadata. Vì vậy “đúng luồng” phải theo **binding đã được thương lượng/cấu hình**, không hardcode rằng tất cả AuthnRequest đều là HTTP GET.

### 2.1. Những sự kiện trong log/traces

| Bước | Sự kiện có thể đo | Bằng chứng PASS |
| --- | --- | --- |
| 0 | Anonymous request protected resource | Không có user Authentication; bảo vệ route |
| 1 | Redirect sang authentication entrypoint | Đúng SP registration/IdP, không open redirect |
| 2 | AuthnRequest generated | `ID` unique, `Issuer`/`Destination`/ACS chính xác |
| 3 | Request stored | Có pending request gắn original browser/session |
| 4 | IdP receives request | IdP chấp nhận đúng SP metadata/signing policy |
| 5 | User authenticates | Sandbox IdP xác thực test user hợp lệ |
| 6 | ACS receives SAMLResponse | Đúng HTTP binding, không lộ token trong log |
| 7 | Response validation | Chữ ký/trust/issuer/audience/time/correlation PASS |
| 8 | Principal mapping | External NameID/Issuer map đúng internal U-100 |
| 9 | Spring authentication completed | `Saml2Authentication.isAuthenticated()` true |
| 10 | Session persisted | SecurityContext còn sau **request mới** |
| 11 | Authorization | User U-100 truy cập đúng resource, unauthorized user bị deny |
| 12 | Session ended | Logout/expiry làm protected route phải xác thực lại |

**Kiểm thử toàn luồng cần chứng minh cả các bước 7–11.** Một SAMLResponse có `StatusCode=Success` chưa đủ; một cookie `JSESSIONID` xuất hiện cũng chưa đủ vì session có thể được tạo ngay từ trước khi đăng nhập để lưu AuthnRequest.

## 3. Chuẩn bị môi trường IdP/SP có thể kiểm thử thật

### 3.1. Chọn IdP sandbox/fixture

Có thể dùng:
- Một realm/sandbox riêng của IdP hỗ trợ SAML2, ví dụ Keycloak test realm, IdP test instance của tổ chức hoặc SAML test provider đã được phê duyệt.
- Một SP registration tách biệt production, có signing/verification certificates dành riêng.
- User thử nghiệm không có quyền production và không trùng với tài khoản thật.
- HTTPS hoặc môi trường localhost/loopback được phép theo contract test; không bỏ TLS verification trong test tích hợp với hosted IdP.
- Metadata được cố định hoặc pin theo test policy, không cho test tải metadata/JWKS từ URL do request tự quyết định.
- Đồng bộ NTP/đồng hồ các node; thử time skew với **fixtures riêng**, không chỉnh domain controller production.

**Không dùng IdP production phát assertions thật** rồi paste SAMLResponse vào CI logs. Assertions thường chứa NameID/email/groups và có thời hạn ngắn. Test fixtures cần có khóa/certificate **riêng cho test**, không dùng key production.

### 3.2. SP metadata/ACS/EntityID phải khớp

Đối chiếu giữa SP và IdP:
1. SP EntityID do ứng dụng khai báo phải đúng với Audience IdP sẽ phát.
2. ACS URL được IdP đăng ký phải trùng URL mà Response gửi về, bao gồm scheme, host, port, context path và registration ID theo contract.
3. IdP SSO endpoint/EntityID trong SP registration phải đúng metadata.
4. Verification certificate là key tin cậy của IdP; nếu IdP rollover certificate, test cả overlap/rotation.
5. SP signing certificate/private key phải phù hợp khi IdP yêu cầu signed AuthnRequest; test fail nếu key sai.
6. Assertion encryption nếu bật cần SP decryption credential thật trong test.
7. Reverse proxy phải giữ public scheme/host và callback path; tránh ACS thành `http://backend:8080` trong metadata.
8. Nếu IdP chọn ACS qua index thay vì URL, kiểm mapping metadata đúng, không đòi cả URL/index xuất hiện cùng lúc.
9. RelyingPartyRegistration có thể được resolve từ pending AuthnRequest/registrationId/Issuer; test không để issuer chưa tin chỉ định cấu hình arbitrary.
10. Hạn chế callback/ACS chỉ nhận binding hỗ trợ; không để một endpoint khác bypass SAML validator.

### 3.3. Dependency và cấu hình Spring (mảnh định hướng)

Đối với một Spring Boot Servlet application dùng Spring Security SAML2, các modules thường là:

```xml
<!-- Dependency fragment: cần Boot parent/BOM phù hợp. -->
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId>
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
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Spring SAML2 dùng OpenSAML; một số bản có dependency artifact cần repository Shibboleth releases. Làm theo BOM/version/repository **đúng release** của Spring Security đang chạy, không tự phối OpenSAML 4/5 lẫn lộn. Với Spring Boot 3.x, tên web starter/dependency có thể khác Boot 4.x, nên điều chỉnh theo BOM thay vì giữ nguyên XML trên mọi phiên bản.

Ví dụ cấu hình IdP **mô tả contract**, phải cung cấp certificate thật trong test:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: https://portal.example.test/saml/sp
            acs:
              location: https://portal.example.test/login/saml2/sso/corp
            assertingparty:
              entity-id: https://idp.example.test/metadata
              verification:
                credentials:
                  - certificate-location: classpath:idp-test.crt
              singlesignon:
                url: https://idp.example.test/sso
                sign-request: false

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

**Giải thích và giới hạn:**
- `corp` là `registrationId` để mở `/saml2/authenticate/corp`.
- `entity-id` trong relying-party là **SP EntityID**, khác IdP issuer dưới `assertingparty.entity-id`.
- `acs.location` là public callback; một số Spring Boot release dùng property shape khác hoặc yêu cầu custom RelyingPartyRegistration builder; **đối chiếu configuration metadata của đúng Boot release trước khi áp dụng**.
- `sign-request=false` chỉ chấp nhận nếu IdP test **không yêu cầu** signing. Nếu IdP yêu cầu signed AuthnRequests, phải cấu hình SP signing key/cert; đừng tắt để né kiểm thử.
- `idp-test.crt` là signing verification certificate được test trust store phê duyệt, không tải từ request/Response chưa verify.
- YAML chưa có app main/controller, IdP metadata registration bên kia, môi trường DNS/cert, hoặc CA trust: **không coi đây là ứng dụng chạy được độc lập**.
- Ứng dụng thật nên xác định cách quản lý IdP metadata, signing/decryption credentials/rotation thay vì hardcode môi trường test.

### 3.4. SecurityFilterChain và protected endpoint

```java
package com.example.samltest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Đây là **mảnh cấu hình Spring**; cần Spring Boot app và RelyingPartyRegistration thực. Khi browser truy cập `/reports` chưa có phiên, Spring phải khởi tạo SAML login/chuyển tới IdP. Nếu dùng nhiều registrations, Spring có thể hiện login picker; để E2E ổn định, test có thể mở trực tiếp `/saml2/authenticate/corp`. Không làm các endpoint SAML/ACS `permitAll` bằng cách vô hiệu hóa SAML filters; Spring filter phải còn khả năng xử lý callback **trước** authorization logic.

## 4. Bước 1 – Anonymous request phải dẫn tới SP-initiated login

**Input:**

```http
GET /reports HTTP/1.1
Host: portal.example.test
Cookie: (chưa có app login session)
```

**Kỳ vọng:**
- Protected route không trả nội dung user-specific khi chưa authentication.
- Spring entrypoint khởi động SAML flow: có thể redirect tới `/saml2/authenticate/corp` hoặc trang login để chọn IdP, tùy số registrations.
- Sau khi gọi `/saml2/authenticate/corp`, request được gửi đến **IdP SSO URL đã đăng ký**.
- Không xuất hiện username/session-authenticated trong backend chỉ vì đã có `HttpSession` lưu handshake.
- Nếu test trực tiếp URL `/saml2/authenticate/corp`, kết quả phụ thuộc configured binding: Redirect binding trả 3xx tới IdP; POST binding có thể trả HTML auto-submit form.
- Không dùng raw query `?idp=https://evil.example` làm nơi chọn issuer/SSO destination.

**Tiêu chí QA:** so hostname IdP SSO thực với metadata/registration, không so toàn bộ `Location` byte-for-byte vì `SAMLRequest` chứa ID, IssueInstant và RelayState thay đổi theo mỗi lần chạy.

### 4.1. Phân biệt HTTP redirect 302 và successful authentication

```text
GET /reports                     → 302 /saml2/authenticate/corp (có thể)
GET /saml2/authenticate/corp     → 302 https://idp.example.test/sso?SAMLRequest=...
GET https://idp.example.test/sso → trang login IdP
```

**Đây mới là điểm bắt đầu.** Test chỉ check 302 **không chứng minh**:
- IdP chấp nhận SP EntityID/signature.
- IdP cấp assertion cho đúng user.
- SP verify response.
- Spring lưu authenticated SecurityContext.
- App map và authorize principal.

Phải có ít nhất một test E2E với SAMLResponse thực sự được test IdP ký.

## 5. Bước 2 – Kiểm tra AuthnRequest sinh ra

Ví dụ cấu trúc XML (rút gọn, không phải full signed production request):

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request_123"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://idp.example.test/sso"
    AssertionConsumerServiceURL=
        "https://portal.example.test/login/saml2/sso/corp"
    ProtocolBinding=
        "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
  <saml:Issuer>https://portal.example.test/saml/sp</saml:Issuer>
</samlp:AuthnRequest>
```

Đây là **XML cấu trúc dùng để đọc hiểu**; attribute formatting và AuthnRequest signing policy có thể khác trong môi trường thật. Không copy `ID="_request_123"` làm giá trị cố định để phát AuthnRequest thực.

### 5.1. Những trường phải xác minh

| Trường | Kỳ vọng | Lỗi khi sai |
| --- | --- | --- |
| `ID` | Có, unique/hard-to-guess theo protocol, lưu pending | Replay/correlation không xác định |
| `Version` | SAML 2.0 | Không đúng profile |
| `IssueInstant` | Thời điểm hợp lý theo clock policy | Request stale/clock skew |
| `Issuer` | SP EntityID do IdP đăng ký | IdP không nhận SP |
| `Destination` | SSO endpoint đã được IdP ký/metadata xác nhận | Sai destination/open redirect |
| `AssertionConsumerServiceURL` hoặc ACS index | Trùng registered ACS contract | IdP post Response sai endpoint |
| `ProtocolBinding` | Binding mong muốn cho Response (thường HTTP-POST) | IdP phát binding không tương thích |
| `NameIDPolicy` nếu dùng | Format/`AllowCreate` theo thỏa thuận | Không map principal |
| `RequestedAuthnContext` nếu dùng | Assurance/MFA yêu cầu, IdP hỗ trợ | AuthnContext mismatch |
| `ForceAuthn` nếu dùng | Chủ đích buộc IdP xác thực lại | UX/step-up khác kỳ vọng |
| `IsPassive` nếu dùng | Phản hồi không tương tác đúng policy | IdP cần login lại, phải fail |
| Request signature | Ký/thuật toán/certificate theo IdP policy | IdP reject hoặc hạ an toàn |
| `RelayState` | Opaque, ngắn, có correlation session | Login fixation/open redirect |

**Không áp đặt mọi field luôn hiện diện.** Ví dụ một request có thể dùng ACS index hoặc URL; `NameIDPolicy`/`RequestedAuthnContext` là tùy chọn. Test phải xác minh **contract đã chốt với IdP**, không hardcode mọi mục là mandatory.

### 5.2. Decode đúng binding khi phân tích network trace

Với **HTTP Redirect Binding**:
1. Browser nhận Location có `SAMLRequest=<URL-encoded base64>`.
2. URL-decode **tham số query**.
3. Base64-decode SAMLRequest.
4. Giải nén **raw DEFLATE** theo SAML Redirect binding (không phải GZIP).
5. Parse XML an toàn: cấm external entities/DTD, giới hạn input.
6. Nếu có `SigAlg`/`Signature`, xác minh chữ ký **trên query string canonical bytes** theo binding; không coi một XML `<ds:Signature>` có/không là toàn bộ signature logic của Redirect binding.

Với **HTTP POST Binding** của AuthnRequest (nếu cấu hình):
1. Browser nhận auto-submit HTML form.
2. `SAMLRequest` là Base64 của XML, thông thường **không raw-DEFLATE** như Redirect binding.
3. Signature được biểu diễn theo contract/binding (có thể XMLDSig trong message).
4. Không tự động dùng cùng quy trình inflate cho tất cả bindings.

**Không paste SAMLRequest/SAMLResponse thật vào public decoder.** Dùng tool nội bộ được duyệt, có thể đọc ký tự ID/Issuer/Destination mà không lưu private credentials hoặc PII vào telemetry.

### 5.3. Redirect Binding signature cần được kiểm riêng

Ví dụ các tham số:

```text
SAMLRequest=<URL-ENCODED-BASE64-DEFATE>
RelayState=<OPAQUE-ID>
SigAlg=<ALGORITHM-URI>
Signature=<BASE64-SIGNATURE>
```

Khi có signature qua Redirect binding, nó bảo vệ canonical ordered query parameters theo SAML Bindings; validator cần đúng encoding/order và trusted SP verification certificate. Không parse XML ra rồi xác minh “nội dung giống” là đủ.

**Kỳ vọng test:** nếu IdP yêu cầu signed AuthnRequest mà SP không ký/sai signature, IdP sandbox phải reject. Nếu contract cho phép unsigned requests, test có thể không yêu cầu `Signature`, nhưng Response/Assertion verification ở SP vẫn bắt buộc.

## 6. Bước 3 – AuthnRequest Repository, RelayState và original browser session

Spring Security dùng `Saml2WebSsoAuthenticationRequestFilter` để tạo AuthnRequest và lưu qua `Saml2AuthenticationRequestRepository`. Theo tài liệu Spring Security 7.1, repository mặc định là `HttpSessionSaml2AuthenticationRequestRepository`, lưu `AbstractSaml2AuthenticationRequest` trong `HttpSession`.

**Vì sao phải test repository?** Khi IdP trả Response, SP cần biết:
- Response đang trả lời **request ID nào** (`InResponseTo`).
- Request đó được phát cho **IdP nào** và SP registration nào.
- Browser/session nào đã khởi tạo login.
- RelayState của handshake đó là gì.
- Đã tiêu thụ request hay chưa.
- Request đã hết hạn/chuyển login context chưa.

Nếu chỉ lấy AuthnRequest bằng `InResponseTo` hoặc `RelayState` từ cache chung mà **không ràng buộc browser đã khởi tạo**, attacker có thể thực hiện **login fixation/login CSRF**: ép một SAML Response cho phiên của họ vào phiên nạn nhân. Tài liệu Spring đặc biệt nhắc lợi ích bảo vệ fixation của **session-bound repository**.

### 6.1. Các case session correlation

| Test | Bối cảnh | Kỳ vọng |
| --- | --- | --- |
| Đúng phiên | Browser A bắt đầu login; A nhận Response | Accept sau SAML validation |
| Sai phiên | A bắt đầu, browser B gửi Response/RelayState của A | Reject, không login B bằng identity A |
| Sai request ID | Response `InResponseTo` khác pending ID | Reject |
| RelayState bị sửa | Response có value lạ | Reject hoặc safe failure; không redirect theo raw RelayState |
| Replay | Callback thứ hai dùng same Response ID/Assertion ID | Reject; không tạo phiên mới |
| Request hết TTL | IdP trả sau timeout | Reject/khởi động flow mới có chủ đích |
| Hai tabs song song | A bắt đầu hai lần | Policy/repository xử lý rõ; không gắn nhầm Request A vào Response B |
| Khác node/pod | Start ở pod1, ACS ở pod2 | Session/shared state đúng hoặc sticky session được kiểm chứng |
| Session bị rotate trước callback | Cookie/session ID thay đổi | State transfer/correlation theo thiết kế, không nhận nhầm |
| Session bị xóa giữa chặng | Cookie không được gửi hoặc store mất | Fail closed, không fallback unsecured lookup |
| IdP khác | AuthnRequest IdP A, Response IdP B | Reject |
| ACS khác | Request ACS corp, POST sang partner | Reject hoặc chọn registration đúng theo trusted context |

### 6.2. `CacheSaml2AuthenticationRequestRepository` khi chạy nhiều nodes

Spring Security có `CacheSaml2AuthenticationRequestRepository` để lưu request theo RelayState trong distributed cache. Nó có thể hữu ích khi cookie SameSite/cluster architecture khiến session repository khó hoạt động. **Nhưng không có nghĩa có thể bỏ session binding.** Phải tự xác định browser correlation, TTL, one-time request use và access controls. Chỉ dùng cache mapping `RelayState → AuthnRequest` mà bất kỳ client nào cũng lookup được có thể tạo login fixation.

Tại cluster phải kiểm:
- `JSESSIONID` hoặc session cookie có thể được đọc bởi pod khác qua Spring Session/shared store nếu dùng session.
- Request repository chia sẻ đúng backend, TTL và atomic consume.
- Clock/NTP giữa nodes, valid certificate/config giống nhau.
- Không phát ID lặp do random generator sai.
- InResponseTo/RelayState không làm lộ user PII/URL redirect.
- Các kịch bản mất cookie/third-party context được xử lý an toàn, không “bật accept unsolicited” như workaround.

### 6.3. SameSite cookie và HTTP POST từ IdP

IdP thường dùng **cross-site POST Binding** về ACS. Các browser hiện đại có thể **không gửi cookie SameSite=Lax trong cross-site POST** theo hành vi thông dụng; `SameSite=Strict` còn hạn chế hơn. Điều này có thể làm SP **không tìm thấy pending AuthnRequest trong HttpSession** dù signature SAMLResponse đúng.

Cách xử lý:
1. Kiểm Network trace của browser xem request ACS có mang session cookie tương ứng hay không (không công khai raw cookie).
2. Xác định SameSite behavior thực của browser; **không dựa vào ngoại lệ tạm thời của một vài browsers**.
3. Khi cần cross-site POST cookie, có thể dùng `SameSite=None; Secure` theo threat model/cookie policy của tổ chức và HTTPS bắt buộc; test CSRF cho các endpoint khác.
4. Cân nhắc repository/flow phù hợp nếu không muốn mở rộng SameSite cho toàn app; **không bỏ request correlation** để vượt lỗi.
5. Không disable CSRF trên mọi endpoint của app chỉ vì ACS cần nhận form POST từ IdP; dùng framework SAML CSRF exception cho callback theo profile đúng.

**Một session cookie xuất hiện trước login là bình thường** nếu SP cần lưu AuthnRequest. Điều kiện kiểm thử là SecurityContext sau xác thực và tình trạng unauthenticated trước đó, không đơn giản “có cookie hay không”.

## 7. Bước 4 – IdP xác thực và tạo SAMLResponse

Một IdP sandbox có metadata và SP registration đúng sẽ kiểm AuthnRequest, xác thực user theo IdP policy rồi phát SAMLResponse tới ACS. SP kiểm chứng **thông điệp và danh tính** trước khi tạo session.

### 7.1. Response mẫu để đọc hiểu (không dùng xác thực)

```xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp_456"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:10Z"
    Destination="https://portal.example.test/login/saml2/sso/corp"
    InResponseTo="_request_123">
  <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assertion_789"
                  Version="2.0"
                  IssueInstant="2026-11-07T03:00:10Z">
    <saml:Issuer>https://idp.example.test/metadata</saml:Issuer>
    <saml:Subject>
      <saml:NameID>user-17</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://portal.example.test/login/saml2/sso/corp"
            InResponseTo="_request_123"
            NotOnOrAfter="2026-11-07T03:05:10Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="2026-11-07T02:59:10Z"
                     NotOnOrAfter="2026-11-07T03:05:10Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://portal.example.test/saml/sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <!-- AuthnStatement và XML Signature cố ý chưa có. -->
  </saml:Assertion>
</samlp:Response>
```

**Quan trọng:** đoạn XML trên **không phải SAMLResponse hợp lệ để đăng nhập**: thiếu `AuthnStatement`/signature và các thành phần khác theo profile. Đừng dùng chuỗi này làm fixture PASS. Fixture PASS cần IdP sandbox tạo và **ký bằng test private key**, SP chỉ tin test public certificate từ registration.

### 7.2. Các phép kiểm SAMLResponse tại ACS

| Kiểm tra | Kỳ vọng PASS | Negative test |
| --- | --- | --- |
| HTTP binding/endpoint | `POST` tới đúng ACS và form field `SAMLResponse` | POST sang path không đăng ký |
| Encoding/parser | Base64/XML hợp lệ, parser chống XXE/DTD | Malformed Base64/XML, entity expansion |
| SAML Version/Status | 2.0 và success theo profile | Unsupported version/Status != Success |
| Message signature/trust | Response hoặc assertion được ký **đúng cấu trúc/profile** bằng IdP key tin cậy | Xóa signature, sửa bytes, key giả |
| Issuer | Đúng IdP entityID đã trust | Response từ issuer khác |
| Destination | Đúng public ACS | Destination tới host/path khác |
| AudienceRestriction | Đúng SP EntityID | Assertion phát cho SP khác |
| SubjectConfirmation | Bearer, Recipient/NotOnOrAfter/InResponseTo khớp | Đổi recipient, hết thời gian |
| InResponseTo | Khớp pending AuthnRequest và đúng browser/session | Mismatch/unrequested response |
| Time | NotBefore/NotOnOrAfter, optional clock skew nhỏ | Future/expired assertion |
| Replay | Response/Assertion IDs chưa dùng, one-time response handling | POST lặp message |
| AuthnStatement | Có subject authentication hợp lệ theo profile | Không có/assurance sai |
| NameID/attributes | Subject đúng type/namespace và mapping policy | Email/NameID rỗng hoặc tenant khác |
| Signature wrapping | Ứng dụng dùng **đúng assertion đã được ký** | Signed benign assertion + unsigned attacker assertion |
| EncryptedAssertion nếu dùng | SP decryption credential hợp lệ, signature đúng | Wrong decryption key/alter ciphertext |
| Certificate rotation | Trust set đúng với IdP metadata đã duyệt | Cert không trust hoặc hết rotation window |

**Không chỉ assert `StatusCode=Success`**, vì Status do một bên gửi có thể bị giả nếu không có message signature/trust thích hợp. **Không chỉ so SAML XML bằng regex**; dùng thư viện SAML/OpenSAML có cơ chế XML Signature Reference validation và chống signature wrapping.

### 7.3. Signature có thể nằm ở Response hoặc Assertion

Spring Security 7.x (OpenSAML5 integration theo docs) kiểm signed SAML Response hoặc assertions theo profile và RelyingPartyRegistration. **Không bắt buộc mọi IdP ký cả hai** nếu contract cho phép signature trên Response hoặc Assertion phù hợp. Nhưng:
- Không chấp nhận unsigned message/assertion không được bảo vệ bởi signature hợp lệ theo profile.
- Nếu Response đã ký, assertion bên trong chỉ được tin khi nó thực sự là nội dung được chữ ký bảo vệ/được parse an toàn.
- Nếu Assertion đã ký, không lấy dữ liệu user từ một sibling/element chưa ký.
- Kiểm key trust từ metadata/config, không lấy certificate tùy ý do chính message đính kèm rồi xem là authoritative.
- Nếu doanh nghiệp yêu cầu cả Response và Assertion signed, viết test enforce policy cao hơn default.
- Phát hiện certificate/algorithm lỗi và SHA-1 signing policy không đáp ứng yêu cầu bảo mật.

### 7.4. Clock skew không phải cách bỏ validation

Spring/OpenSAML hỗ trợ cấu hình clock skew ở validators/provider. Mức skew phải nhỏ và theo security policy, không dùng “1 ngày” để tránh expired fixture. Test:
- Assertion sắp bắt đầu có `NotBefore` trong tương lai vượt skew → reject.
- Assertion hết `NotOnOrAfter` → reject.
- IdP/SP lệch giờ trong tolerance được duyệt → có thể pass.
- VM/containers NTP sync; timezone hiển thị không phải clock drift.

Với fixture cố định cũ, **đừng** giữ thời gian `2026-11-07` rồi kỳ vọng test PASS mãi. IdP sandbox cần phát assertions gần thời gian hiện tại; test unit time validation có thể dùng injected/mock clock hoặc fixture generator, nhưng phải tách khỏi test E2E thực.

## 8. Bước 5 – Từ assertion thành Spring Authentication

Khi ACS được xử lý bằng Spring Security:

```text
POST /login/saml2/sso/corp
  ↓
Saml2WebSsoAuthenticationFilter
  ↓
Saml2AuthenticationTokenConverter
  ↓
AuthenticationManager
  ↓
OpenSaml5AuthenticationProvider (theo Spring Security 7.x)
  ↓
Verify SAMLResponse/Assertion, decrypt nếu cần,
check issuer/audience/destination/conditions...
  ↓
Saml2Authentication với Saml2AuthenticatedPrincipal
  ↓
Application account mapping, authorities
  ↓
SecurityContext và session persistence
```

Spring Security docs mô tả `Saml2AuthenticatedPrincipal` dùng để truy cập `NameID`, `attributes`; một số version cấp `ROLE_USER` theo provider converter mặc định. **`ROLE_USER` không tự đồng nghĩa ROLE_ADMIN**; nếu business cần role, ứng dụng phải map group/tenant từ issuer đã trust và kiểm quyền trong resource.

### 8.1. Controller đọc authenticated principal

```java
package com.example.samltest;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/whoami")
    public Map<String, String> whoami(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of("name", principal.getName(),
                "auth", "saml2");
    }
}
```

**Mảnh controller trong Spring Boot app**, không chạy độc lập bằng JDK. Chỉ dùng trong sandbox hoặc production khi business policy cho phép trả principal name; không expose toàn bộ SAML attributes/token vì có thể chứa PII/group details. Khi cần map `user-17` thành `U-100`, nên dùng verified `IdP issuer + stable NameID/attribute contract` và application user repository; không map chỉ theo email chưa đủ tin cậy.

### 8.2. Session là một bằng chứng riêng cần test

Sau ACS thành công, kiểm:
1. Spring `Authentication` có kiểu/semantic SAML authenticated, principal phù hợp test IdP.
2. `SecurityContext` của request đã được lưu qua `SecurityContextRepository`/session strategy phù hợp framework version.
3. Browser giữ cookie session với `Secure`, `HttpOnly`, `SameSite` theo web threat model; đúng domain/path/expiration.
4. **Request mới** `GET /whoami` hoặc `GET /reports` **không cần gửi lại SAMLResponse**, chỉ mang session cookie hợp lệ.
5. Request mới xác thực lại được principal đúng, không sinh redirect IdP vòng lặp.
6. Một browser khác không có cookie/same-origin session không được hưởng login này.
7. Session fixation protection được áp dụng: session ID có thể đổi/rotate theo Spring session strategy khi authentication thành công. Không hardcode rằng cookie buộc phải xuất hiện lần đầu **sau** login.
8. Invalidated/expired session mất Authentication; protected resource không còn accessible.
9. Nếu app stateless vì cấu hình riêng, **không được giả định** có phiên HttpSession như bài yêu cầu; phải đổi kiến trúc test cho đúng mục tiêu hoặc sửa cấu hình.
10. Nếu production dùng Spring Session Redis/JDBC, test across pods/instances thay vì chỉ một JVM.

**Dấu hiệu PASS thực:** SAML Response verified và một request độc lập tiếp theo lấy được authenticated principal **cùng nội bộ user/tenant**, còn anonymous/new browser bị chặn.

### 8.3. Session fixation và authentication source

Spring Security có cơ chế session fixation protection thông qua session authentication strategy. Trong Spring Security 6/7, authentication mechanisms chịu trách nhiệm gọi strategy (không nên cấu hình dựa trên giả định Spring Security 5 `SessionManagementFilter`). Test cần so trạng thái **trước và sau login**:
- Nếu đã có HttpSession để lưu AuthnRequest, session ID **có thể được rotate** theo policy; việc session ID mới khác cũ không làm mất AuthnRequest correlation vì auth đã hoàn tất.
- Session từ attacker cố fix không được trở thành session authenticated dùng chung.
- Request sau login phải dùng cookie mới/current, không dùng cookie đã invalidated.
- User logout hoặc idle timeout phải giải phóng SecurityContext.
- Không xem việc IdP có SSO cookie là bằng chứng ứng dụng còn local session hoặc ngược lại.

## 9. Bước 6 – Trở về protected resource và kiểm business authorization

Khi SP tạo `Authentication`, ứng dụng có thể redirect về saved request `/reports` hoặc một local success URL. Kiểm:
- Chỉ redirect đến **safe internal route**, không dùng raw RelayState làm `Location`.
- `GET /reports` dùng authenticated session và trả dữ liệu test user được phép; nếu user thiếu role/resource permission thì `403`, **dù SAML login hợp lệ**.
- Không tạo internal admin role chỉ vì IdP phát `groups=["admin"]` mà chưa có mapping policy.
- Nếu IdP B phát NameID giống IdP A, identity key phải có issuer namespace.
- Khi app có tenant, SAML attributes phải map theo tenant authority; không cho tenant B truy cập dữ liệu A.
- Request thứ hai và thứ ba chứng minh session persistence, không tạo một lần `SecurityContextHolder` tạm chỉ sống trong request ACS.
- Nếu app tạo local account JIT, test account status/uniqueness và không auto-merge theo email.

### 9.1. Kiểm `Authentication` và business session

| Tầng | Ví dụ assert đúng | Assert thiếu an toàn |
| --- | --- | --- |
| Protocol | Signature + issuer + audience + InResponseTo + replay valid | `SAMLResponse` có `Success` |
| Identity | `issuer + persistent subject` map `U-100` | Chỉ khớp email |
| Spring Authentication | Principal và authorities đúng, authenticated true | Controller tự set `isLoggedIn=true` |
| Session | Request mới cùng cookie được xác thực | Chỉ thấy `Set-Cookie` |
| Authorization | U-100 có đúng quyền xem report | Có `ROLE_USER` là auto xem mọi report |
| Logout | Session invalidated làm request sau phải auth lại | Browser hiển thị “signed out” |
| Multi-user | A và B giữ identity isolation | Cùng browser tab cache username |

## 10. Cấu trúc một bộ test có sức chứng minh

Một test suite đáng tin cần ít nhất bốn lớp:

### Lớp A – Static/config tests

- SP entityId, ACS, IdP entityId, SSO URL, bindings, credentials/metadata.
- Application public URL và proxy forwarded headers.
- Certificate/private key/trust rotation theo profile; không hardcode key production.
- User/tenant attribute mapping config và default session policy.
- Startup fail nếu registration sai/missing/trust anchor chưa có.
- Việc custom AuthnRequest resolver và request repository có tồn tại và hoạt động đúng.

### Lớp B – Spring MockMvc: entrypoint/filter wiring

- Anonymous `GET /reports` không trả protected data.
- `GET /saml2/authenticate/corp` tạo AuthnRequest và response đúng **binding**: 3xx Location chứa SAMLRequest (Redirect) hoặc HTML form POST (POST binding).
- Request được lưu trong session/repository.
- Multiple registrations chỉ chọn đúng IdP và không có open redirect.
- SAML ACS không bị custom controller chiếm route/bypass validator.
- Auth success/failure handlers được gọi ở đúng nơi.

**Giới hạn:** MockMvc chưa có IdP ký fixture **không chứng minh** Response signature/subject/session end-to-end. `@WithMockUser`/`with(user(...))` chỉ đặt mock Authentication vào request, **không mô phỏng SAML Web SSO**.

### Lớp C – Protocol-integrated tests

- Chạy IdP sandbox hoặc test IdP service với **test signing private key**.
- SP chỉ trust test IdP signing cert đã đăng ký.
- Phát AuthnRequest thật qua HTTP, IdP parse, login user test, phát signed Response thật.
- SP validate Response ở ACS, check replay/mismatch/expiration/crypto failures.
- Chạy bad fixtures được tạo từ dedicated test issuer/key và có cấu trúc invalid có chủ đích.
- Kiểm provider/error path không tạo session khi Response invalid.
- Đo certificate rotation, signed/unsigned response policies, encryption nếu bật.
- Không bypass OpenSAML provider bằng một mock trả authenticated token để giả E2E.

### Lớp D – Browser E2E

- Browser thật giữ cookies/chuyển hướng, qua IdP login HTML POST và ACS.
- Dùng một context mới trước login, một context khác để thử isolation.
- Kiểm SameSite, Secure, Domain, Path, reverse proxy và redirect chain.
- Check request tiếp theo sau login lấy đúng internal user/roles.
- Logout/session expiration làm mất quyền; IdP-SSO local session distinction.
- Thử browser/headless, site isolation, multiple tabs, renew session và cluster failover.
- Test IdP downtime, stale metadata, expired cert, weak time sync trong sandbox.
- **Không dump SAMLResponse/token/cookies vào CI artifacts**; redact ở Playwright/Browser logs.

**Definition of Done:** có bằng chứng Lớp B + C + D cho happy path; các negative tests thuộc protocol/session/authorization được thực thi, không dựa vào mock user làm E2E.

## 11. MockMvc: kiểm điểm phát sinh AuthnRequest (không giả E2E)

Một test JUnit/Spring Boot dùng MockMvc để kiểm endpoint Start SAML, với điều kiện **test registration corp đã cấu hình Redirect binding**:

```java
package com.example.samltest;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SamlAuthnRequestStartTest {
    @Autowired
    MockMvc mvc;

    @Test
    void startsSamlWithRedirectBinding() throws Exception {
        var result = mvc.perform(
                    get("/saml2/authenticate/corp").secure(true))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andReturn();

        String location =
                result.getResponse().getHeader(HttpHeaders.LOCATION);
        assertTrue(location.startsWith(
                "https://idp.example.test/sso"));
        assertTrue(location.contains("SAMLRequest="));
    }
}
```

**Giới hạn và version note:** code là mảnh test trong một dự án Spring Boot có registration, dependency test và HTTP Redirect binding thực. Nếu Boot 4 hoặc plugin kiểm thử thay đổi package auto-configuration test annotations, import `AutoConfigureMockMvc` cần điều chỉnh theo BOM. Nếu IdP yêu cầu ký AuthnRequest, SP phải có signing credentials trong test; nếu dùng POST binding, test cần kiểm HTML form thay vì `3xx Location`. Không kết luận signature hợp lệ chỉ vì Location chứa `SAMLRequest=`: có thể decode XML, kiểm fields và test IdP accept signed request riêng.

### 11.1. Vì sao không kiểm `redirectedUrl("https://idp...SAMLRequest=<literal>")`?

AuthnRequest ID, IssueInstant, RelayState và Signature có thể thay đổi theo mỗi request. Test byte-exact một URL động dễ flaky và có thể làm team hardcode ID nguy hiểm. Thay vào đó:
- Phân tích URI: origin IdP SSO được allowlist; path đúng; không có open redirect.
- Parse query parameters bằng URL-aware parser.
- Decode SAMLRequest theo binding.
- Assert XML structure/Issuer/Destination/ACS/ID/Version.
- Kiểm signature khi policy yêu cầu bằng test IdP verifier.
- Correlate request repository với ID/RelayState test đã ghi.

**Không viết regex để validate XML signature.** Dùng OpenSAML/SAML verifier cùng metadata trust.

### 11.2. MockMvc cho ACS: không đưa chuỗi `<Response>` chưa ký vào PASS

Một test vô ích:

```java
// ANTI-PATTERN: test bypass, không chứng minh SAML validation.
mvc.perform(get("/reports").with(
    org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user("user-17")))
    .andExpect(status().isOk());
```

Test trên chỉ chứng minh endpoint xử lý **mock authenticated user**; nó không chạy IdP, `AuthnRequest`, ACS, signature verification, InResponseTo hay session persistence.

Tương tự, gọi:

```text
POST /login/saml2/sso/corp
SAMLResponse=base64("<Response Status=Success.../>")
```

không phải happy-path fixture. Phải sử dụng một **real signed response** từ test IdP, đã liên kết với pending AuthnRequest và test browser session. Với invalid fixture, status failure có thể trả redirect tới login hoặc error handler thay vì HTTP 401: assert **không tạo Authentication/không cấp data**, không hardcode mọi failure đều HTTP 401.

## 12. E2E test script thực hiện bằng trình duyệt

Dưới đây là **test plan** có thể triển khai với Playwright/Selenium hoặc thủ công trong sandbox, không dùng credential production.

### 12.1. Chuẩn bị

- Khởi động IdP test realm; user `user-17` có group/report permission tùy policy.
- SP chạy HTTPS public `https://portal.example.test`, đã đăng ký EntityID/ACS test.
- Browser context A mới, sạch cookies/app session.
- Browser context B mới, hoàn toàn tách biệt A.
- Bật network trace **đã che** SAMLRequest/SAMLResponse/SessionID và Authorization.
- Đồng bộ thời gian; IdP signing certificate và SP verification key khớp.
- Bật audit event IDs: request started/response verified/login succeeded/session persisted/authorization decision.

### 12.2. Các bước và expected results

**Step 1 — Anonymous access:** A mở `/reports`. Expect protected content không được trả. Nếu có login picker, chọn corp. **Chưa có authenticated app user**.

**Step 2 — Start AuthnRequest:** A tới `/saml2/authenticate/corp`. Expect Redirect hoặc POST tới IdP endpoint hợp lệ. Capture request ID/RelayState vào **test memory an toàn** để đối chiếu, không in raw credentials.

**Step 3 — Verify request contract:** Decode SAMLRequest. Check `Issuer=SP EntityID`, `Destination=IdP SSO`, `AssertionConsumerServiceURL`/index phù hợp, `Version=2.0`, ID unique, timestamp gần hiện tại và request signed nếu IdP yêu cầu.

**Step 4 — IdP login:** A đăng nhập test user tại IdP. Nếu user đã có IdP SSO session, IdP có thể bỏ màn hình nhập mật khẩu; test vẫn phải kiểm response subject/assurance đúng. Nếu cần kiểm fresh login, dùng isolated IdP browser context và `ForceAuthn` policy.

**Step 5 — ACS POST:** Browser A gửi SAMLResponse tới `/login/saml2/sso/corp`, kèm `RelayState`. Expect **đúng browser cookie/session** để SP tra pending request. Nếu SameSite chặn cookie, test phải fail với lỗi correlation, không tự cho unsolicited login.

**Step 6 — SAML validation:** SP verify signed assertion/response. Audit không in token nhưng xác nhận trusted IdP/Request ID correlation, accepted subject và correct ACS/audience.

**Step 7 — App identity:** Principal của Spring là `Saml2Authentication`; app resolver mapping `(IdP, NameID) → U-100`. Verify user is ACTIVE, tenant/role correct; không auto-merge theo email.

**Step 8 — Session:** Browser A nhận/cập nhật cookie phiên sau authentication. Mở `GET /whoami`/**`/reports`** trong request mới. Expect authenticated user `U-100`, không quay lại IdP. Nếu session fixation protection rotate session ID, browser dùng cookie mới.

**Step 9 — Isolation:** Browser B mở `/reports` không cookie A. Expect khởi tạo login/deny, không truy cập tài nguyên của U-100. Không dùng chung test BrowserContext nếu muốn chứng minh isolation.

**Step 10 — Authorization:** A xem report được phép. Thử `/admin` hoặc report khác tenant, Expect 403/deny, **không coi SAML login thành công là được quyền mọi nơi**.

**Step 11 — Replay:** Lấy một bản SAMLResponse **đã dùng** từ bộ test nội bộ (không public logs) rồi POST lại với cùng session hoặc session mới trong môi trường thử nghiệm. Expect fail/no new authenticated session; log event `REPLAY_DETECTED` nếu có.

**Step 12 — Logout:** A POST logout theo CSRF policy, session invalidated. Sau đó `/reports` không còn dùng local session. Nếu browser IdP SSO còn hiệu lực, lần mở lại có thể SSO ngay; test phân biệt **logout local vs IdP SLO**.

### 12.3. Artifact nên giữ sau test

Chỉ lưu:
- Correlation IDs đã hash/redact.
- Test registration name, issuer config ID (không phải secret).
- Verified request ID/response ID dưới dạng hashed audit identifier nếu cần.
- HTTP statuses, redirect origins và cookie attribute flags (không raw cookie values).
- Timings: request start, ACS success, session-established, protected resource.
- Assertion validation pass/fail reason code **không lộ NameID/PII**.
- Screenshots UI login/success/logout đã che dữ liệu cá nhân.
- Version Spring Security/OpenSAML/IdP test + fingerprint certificate public.

**Không giữ** raw `SAMLResponse`, private keys, session cookies, service secrets hoặc full browser HAR chứa credentials ngoài secret storage được kiểm soát.

## 13. Java 17 runnable demo: kiểm correlation và phiên

Một test E2E SAML thật phải dùng OpenSAML + signed fixture + IdP. Tuy nhiên, trước khi kết nối IdP, có thể học **những invariant quan trọng** bằng chương trình Java 17 độc lập:

1. Một response chỉ được chấp nhận khi có pending request `InResponseTo`.
2. RelayState và original browser session phải khớp.
3. Issuer, Audience, Destination phải đúng.
4. Signature validity là điều kiện cần (mô phỏng bằng boolean test input, **không verify XMLDSig**).
5. Response còn thời hạn, ID chưa bị dùng (replay).
6. Chỉ sau khi pass mới có app session authenticated để request sau đọc identity.

Tệp `SamlSpInitiatedFlowDemo.java`:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class SamlSpInitiatedFlowDemo {
    static final String ISSUER = "https://idp.example.test/metadata";
    static final String AUDIENCE = "https://portal.example.test/saml/sp";
    static final String ACS =
            "https://portal.example.test/login/saml2/sso/corp";

    record Pending(
            String requestId, String relayState,
            String browserSession, Instant expiresAt) {}

    record Response(
            String responseId, String inResponseTo,
            String relayState, String issuer,
            String audience, String destination,
            String subject, Instant notOnOrAfter,
            boolean signatureVerified) {}

    static final class MiniServiceProvider {
        private final Map<String, Pending> pending = new HashMap<>();
        private final Set<String> usedResponseIds = new HashSet<>();
        private final Map<String, String> authenticated = new HashMap<>();

        void begin(Pending request) {
            pending.put(request.requestId(), request);
        }

        boolean accept(
                String browserSession,
                Response response,
                Instant now) {
            if (response == null || !response.signatureVerified()) {
                return false;
            }
            Pending request = pending.get(response.inResponseTo());
            if (request == null
                    || usedResponseIds.contains(response.responseId())
                    || !request.browserSession().equals(browserSession)
                    || !request.relayState().equals(response.relayState())
                    || !ISSUER.equals(response.issuer())
                    || !AUDIENCE.equals(response.audience())
                    || !ACS.equals(response.destination())
                    || response.subject() == null
                    || response.subject().isBlank()
                    || !now.isBefore(request.expiresAt())
                    || !now.isBefore(response.notOnOrAfter())) {
                return false;
            }
            pending.remove(response.inResponseTo());
            usedResponseIds.add(response.responseId());
            authenticated.put(browserSession, response.subject());
            return true;
        }

        String principal(String browserSession) {
            return authenticated.get(browserSession);
        }
    }

    static Response validResponse(String id, Pending request) {
        return new Response(
                id, request.requestId(), request.relayState(),
                ISSUER, AUDIENCE, ACS, "user-17",
                Instant.parse("2026-11-07T03:05:00Z"), true);
    }

    public static void main(String[] args) {
        MiniServiceProvider sp = new MiniServiceProvider();
        Instant now = Instant.parse("2026-11-07T03:00:00Z");

        Pending first = new Pending(
                "_request_A", "opaque-relay-A", "session-A",
                Instant.parse("2026-11-07T03:04:00Z"));
        sp.begin(first);
        Response signed = validResponse("_response_1", first);

        System.out.println("Anonymous before SSO: "
                + (sp.principal("session-A") == null));
        System.out.println("Valid response accepted: "
                + sp.accept("session-A", signed, now));
        System.out.println("Application principal: "
                + sp.principal("session-A"));
        System.out.println("Replay rejected: "
                + !sp.accept("session-A", signed, now));
        System.out.println("Another browser stays anonymous: "
                + (sp.principal("session-B") == null));

        Pending second = new Pending(
                "_request_B", "opaque-relay-B", "session-B",
                Instant.parse("2026-11-07T03:04:00Z"));
        sp.begin(second);
        Response secondResponse = validResponse("_response_2", second);

        System.out.println("Wrong browser rejected: "
                + !sp.accept("session-A", secondResponse, now));

        Response wrongAudience = new Response(
                "_response_3", second.requestId(),
                second.relayState(), ISSUER,
                "https://other-sp.example.test", ACS,
                "user-17",
                Instant.parse("2026-11-07T03:05:00Z"), true);
        System.out.println("Wrong audience rejected: "
                + !sp.accept("session-B", wrongAudience, now));

        System.out.println("Correct browser accepted: "
                + sp.accept("session-B", secondResponse, now));
        System.out.println("Session-B principal: "
                + sp.principal("session-B"));

        Pending third = new Pending(
                "_request_C", "opaque-relay-C", "session-C",
                Instant.parse("2026-11-07T02:59:59Z"));
        sp.begin(third);
        System.out.println("Expired pending request rejected: "
                + !sp.accept("session-C",
                        validResponse("_response_4", third), now));
    }
}
```

Chạy:

```bash
javac SamlSpInitiatedFlowDemo.java
java SamlSpInitiatedFlowDemo
```

**Stdout chính xác:**

```text
Anonymous before SSO: true
Valid response accepted: true
Application principal: user-17
Replay rejected: true
Another browser stays anonymous: true
Wrong browser rejected: true
Wrong audience rejected: true
Correct browser accepted: true
Session-B principal: user-17
Expired pending request rejected: true
```

**Giới hạn quan trọng:**
- `signatureVerified` là một boolean giả định, **không có thuật toán XMLDSig**. Ứng dụng thật tuyệt đối không nhận boolean đó từ browser/JSON để quyết định auth.
- Chương trình không tạo SAML XML, không kiểm Issuer/AttributeStatement/SubjectConfirmation/NameID Format đầy đủ, không validate certificate/trust, không chống XML signature wrapping, không thực hiện SAML/HTTP binding.
- `HashMap/HashSet` không thread-safe và không có multi-node/durable TTL/replay store. Production cần session/repository/cache có locking hoặc atomic operations theo threat model.
- `session-A` là chuỗi mô phỏng; HTTP session thật có cookie, SameSite, session fixation rotation, CSRF và SecurityContextRepository.
- Thời gian được cố định để stdout lặp lại. Không dùng timestamp này làm fixture SAML PASS trong production.
- Mục đích chỉ chứng minh logic “**AuthnRequest phù hợp + verified Response ⇒ authenticated app session**” và các negative assertions cơ bản. Test giao thức thật phải dùng signed IdP Response theo `RelyingPartyRegistration`.
- Một authenticated session trong demo chỉ chứa `user-17`; tài khoản ứng dụng thật cần mapping tenant/role và authorization.

## 14. Negative test matrix chi tiết

| Case | Input/thao tác | Kết quả cần chứng minh |
| --- | --- | --- |
| Anonymous protected route | GET `/reports` không session | Không trả dữ liệu user; khởi tạo login |
| Correct AuthnRequest | SP chọn corp | Issuer, Destination, ACS, unique ID đúng |
| Wrong IdP registration | URL corp nhưng IdP partner | Không gửi request sang IdP không tin |
| AuthnRequest malformed | Base64/Deflate/XML sai | IdP test từ chối |
| Missing AuthnRequest ID | XML thiếu ID | Không được xem là đúng flow |
| Duplicated AuthnRequest ID | Gửi hai requests trùng ID | Bị phát hiện; không overwrite/hijack state |
| Signed request required | IdP requires signature, SP không ký | Reject |
| Wrong SP signing credential | Signature RSA key không đăng ký | IdP từ chối |
| Wrong Destination SSO | Địa chỉ IdP sai | IdP từ chối / SP không gửi |
| Wrong ACS | Response về host/path không đăng ký | SP từ chối |
| Wrong SP EntityID | Audience khác | Reject |
| RelayState URL ngoài | `https://evil.example` | Không redirect theo raw value |
| RelayState bị sửa | Opaque ID không tồn tại | Reject/correlation fail |
| Cross-session RelayState | Browser A start, B POST | Reject |
| Missing session cookie | ACS POST không có original session | Fail closed |
| SameSite blocks cookie | Cross-site POST | Phát hiện cookie không gửi; không bypass correlation |
| Expired pending request | Chờ quá TTL | Reject/restart flow |
| Two tabs | Start A/B và responses đảo thứ tự | Không map nhầm |
| Cross-pod | Start pod1, callback pod2 | PASS nếu state shared đúng; deny nếu mất correlation |
| Wrong `InResponseTo` | Response trả lời request khác | Reject |
| Missing `InResponseTo` on SP flow | Unsolicited response | Reject nếu SP-initiated-only policy |
| Wrong response issuer | Metadata IdP B, expected A | Reject |
| Wrong assertion issuer | Nested issuer không khớp | Reject |
| Tampered signed XML | Đổi NameID/attribute sau ký | Reject signature |
| Unsigned response/assertion | Không có signature bảo vệ assertion | Reject |
| Unknown signing certificate | Token ký bằng attacker key | Reject |
| Weak signature algorithm | SHA-1 theo policy cấm | Reject |
| XML signature wrapping | Attacker assertion khác assertion đã ký | Reject |
| External entities/DTD | XXE payload trong XML | Reject an toàn |
| Empty/malformed Base64 | SAMLResponse không parse được | Không authenticated |
| SAML Status failure | Responder/AuthnFailed/NoAuthnContext | Không login |
| Future NotBefore | Assertion chưa đến hiệu lực | Reject ngoài skew |
| Expired NotOnOrAfter | Assertion đã hết hạn | Reject |
| SubjectConfirmation Recipient sai | ACS khác | Reject |
| SubjectConfirmation InResponseTo sai | Không khớp request | Reject |
| Missing AuthnStatement | Assertion không chứng minh authn theo profile | Reject |
| Replay same Response ID | POST lại sau success | Reject |
| Replay same Assertion ID | Ký response khác dùng lại assertion | Reject theo replay policy |
| Wrong audience | Assertion dành cho SP B vào SP A | Reject |
| EncryptedAssertion wrong key | SP không giải mã được | Reject |
| Certificate rotation | IdP đổi cert theo metadata đã duyệt | PASS trong overlap, FAIL cert chưa trust |
| Signature downgrade | Tắt verify trong test | Test suite phải FAIL |
| SP clock skew | KDC/IdP lệch 10 phút | Reject nếu ngoài tolerance |
| User not active | IdP auth success, account disabled | App reject/deny |
| Same email different issuer | IdP A/B cùng email | Không tự merge user |
| Group claim admin from untrusted IdP | User bình thường | Không cấp ROLE_ADMIN |
| User lacks report permission | SAML login success | `403` tại resource |
| Missing SecurityContext persistence | Request ACS pass, GET /reports redirect login | Integration test FAIL |
| Session fixation | Attacker-known pre-login session ID | Không chiếm post-login session |
| Session isolation | Browser B không có cookie A | B không truy cập dữ liệu A |
| CSRF bypass elsewhere | Vì SAML ACS POST mà tắt CSRF app | Security test FAIL |
| Logout local | POST logout hợp lệ | Session mất auth; protected route yêu cầu login |
| IdP SSO session còn | Sau local logout | Không nhầm SSO re-login với failed logout |
| Open redirect post-login | RelayState/next là external URL | Location phải ở safe local origin |
| Proxy header spoof | `X-Forwarded-Host: attacker` | ACS/base URL không đổi sang attacker |
| High-volume malicious callbacks | Random SAMLResponse spam | Resource limits, no auth, observability safe |
| Untrusted log exposure | Trace chứa SAMLResponse/cookie/private key | Security audit FAIL |

### 14.1. SAML protocol test ≠ business E2E test

Nếu user không có quyền xem `/reports` nhưng SAMLResponse valid, có thể có:
- Authentication PASS;
- Session PASS;
- Business authorization FAIL với 403.

Đó **không tự là lỗi SAML**. Để đánh giá từ AuthnRequest tới phiên, dùng route `/whoami` bảo vệ bằng `authenticated()` và route nghiệp vụ kiểm role/tenant riêng. Report kết quả từng tầng để đội vận hành biết sửa đúng chỗ.

### 14.2. Các response failure không nhất thiết là HTTP 401

Spring Security có failure handler có thể redirect tới login/error hoặc trả 4xx tùy custom config. Test không nên fail chỉ vì SAML invalid tạo 302 thay vì 401; điều cần assert:
- Response invalid **không tạo `Authentication`**.
- Không có authenticated SecurityContext persisted.
- Không trả nội dung protected.
- Error được log an toàn và không leak token.
- Không tự chuyển sang IdP khác hoặc nhận unsigned assertion để “retry”.

## 15. Multi-IdP, multi-tenant và registration resolution

Hệ thống có `corp` và `partner` registrations có thể phát AuthnRequests khác nhau:

```text
/saml2/authenticate/corp
/saml2/authenticate/partner
```

Tests cần tách:
- `corp` uses SP EntityID/ACS theo contract và IdP corp, `partner` uses IdP partner; nếu shared SP EntityID, trust mappings vẫn phải phân biệt issuer.
- RelyingPartyRegistration được resolve bằng trusted pending request/registrationId/Issuer, không lấy raw `Issuer` chưa verify làm lý do chấp nhận cert ngoài trust store.
- Response IdP B không thể được coi là Response của pending request IdP A.
- NameID `user-17` ở hai IdPs không mặc định là cùng app user; namespace identity phải gồm IdP authority.
- Tenant-specific ACS/audience/roles được test; không “trộn tenant” qua RelayState.
- Multi-tab có thể làm request state overlap; test đúng repository semantics/version.
- Kể cả IdP đã sign đúng, app business authorization có thể deny theo tenant.

### 15.1. Một registration có thể có nhiều ACS/mapping?

SAML metadata có thể công bố nhiều ACS endpoints/index và bindings. Spring app có thể dùng custom `RelyingPartyRegistration` hoặc routing. Test phải xác định:
- Request đang chọn ACS URL/index nào.
- IdP phát Response tới URL nào.
- Destination/Recipient match exact endpoint được chấp nhận.
- Không cho tenant A đưa Response đến tenant B ACS chỉ vì cả hai thuộc domain chung.
- Reverse proxy không làm thay public baseUrl/port/Host trong response.
- Các bindings được yêu cầu/thực hiện theo metadata, không fallback sang URL không đăng ký.

## 16. Xử lý lỗi theo chặng, không mở bảo mật

| Triệu chứng | Lớp lỗi thường gặp | Chẩn đoán ưu tiên |
| --- | --- | --- |
| Anonymous `/reports` trả 200 không login | Authorization/filter chain sai | `SecurityFilterChain` và matcher |
| Không thấy `/saml2/authenticate/corp` | Registration/login entrypoint sai | Registration ID, login page/picker |
| Không redirect tới IdP | Missing signing key/metadata/SSO endpoint | SAML request filter, IdP registration |
| IdP nói “unknown SP” | SP EntityID sai | IdP registered SP EntityID/Issuer |
| IdP nói “invalid ACS” | Public callback URL sai | ACS URL/index, reverse proxy |
| IdP nói “invalid signature” | SP request signing key/algorithm sai | Trust/cert, Redirect binding bytes |
| AuthnRequest có malformed SAMLRequest | Binding decode sai | URL decode + Base64 + raw Deflate |
| SAMLResponse về ACS nhưng login không thành | Signature/Issuer/Audience/Time/Request mapping | Provider diagnostics đã redact |
| `InResponseTo` mismatch | Request repository/session mất hoặc wrong flow | Pending request ID, session correlation |
| Không nhận RelayState | IdP không echo hoặc callback mismatch | Binding/IdP config, opaque state |
| Cookie session mất ở ACS POST | SameSite cross-site POST, domain/path, TLS | Browser Network trace cookie flags |
| Session request ở node khác | Non-shared HttpSession/repository | Spring Session/shared store/ingress routing |
| Invalid IdP cert | Metadata/rotation trust set | Cert fingerprint và test lifecycle |
| Time expired hoặc not yet valid | NTP lệch, fixture cũ | Issuer/recipient windows, test time |
| POST ACS 403 CSRF | CSRF exception không đúng cho SAML endpoint | SAML filter config, không disable all CSRF |
| Authentication PASS, GET /reports redirect login | SecurityContext không persist, cookie không set/được gửi | Session repository, cookie, session strategy |
| Authentication PASS, GET /reports 403 | Business RBAC/tenant sai | App user mapping, authorities |
| Login lặp không ngừng | Cookie/SameSite, success handler hoặc saved request | Redirect chain, session persistence |
| Wrong user after login | NameID/issuer mapping, parallel tabs, fixation | Identity namespace, original browser binding |
| Browser B truy cập được user A | Session isolation/cookie leak | Test contexts, Session IDs |
| Logout chỉ xóa local session | IdP SSO còn | Thiết kế SAML SLO riêng, không coi là bug mặc định |
| Chỉ lỗi sau load balancer | Proxy Host/Proto, pods configs/keys | Public base URL, forwarded trust, shared state |
| Test pass ở MockMvc nhưng browser fail | Mock không có cookies/cross-site/IdP | E2E browser network trace |
| Cert rotation làm test fail | Key overlap/metadata sync | Pin/rollover/expiry management |

**Không “fix” bằng cách** tắt signature validation, bỏ `InResponseTo`, chấp nhận arbitrary unsolicited assertion, nâng clock skew lên nhiều giờ, bật `permitAll()` trên toàn app, tắt CSRF toàn hệ thống hoặc set `RelayState` bằng raw URL. Chúng chỉ biến lỗi tích hợp thành lỗ hổng SSO.

## 17. Runbook QA cho một lần kiểm thử hoàn chỉnh

**Trước khi chạy**
1. Ghi phiên bản Java/Spring Security/Boot/OpenSAML/IdP test và trust metadata fingerprint.
2. Xác định một SP EntityID, IdP EntityID, registered ACS URL và bindings theo contract.
3. Bật HTTPS, kiểm public host/forwarded headers, test user/roles/tenant.
4. Chuẩn bị browser contexts tách biệt, secret-safe capture và current IdP test signing key.
5. Đảm bảo clock/NTP và session/cache tương thích với cross-site POST.
6. Xác định expected local success route, protected route và logout policy.

**Thực hiện**
1. Anonymous GET protected route → login initiated.
2. AuthnRequest generated → kiểm ID, Issuer, Destination, ACS và Request signature nếu cần.
3. Pending AuthnRequest lưu server-side, gắn session/RelayState.
4. IdP sandbox xác thực user test và phát signed SAMLResponse.
5. Browser POST ACS với đúng session/RelayState.
6. SP kiểm XML signature/trust, issuer, audience, destination, subject/time và InResponseTo.
7. App map principal → user/tenant/roles; SecurityContext/session được lưu.
8. Browser gửi request mới bằng cookie hiện hành; truy cập đúng protected resource mà không lặp IdP.
9. Browser mới không có quyền; unauthorized resource trả 403; logout/expiry làm mất phiên.
10. Chạy negative tests theo ma trận, đặc biệt replay, wrong audience, wrong session, unsigned response, wrong signing cert, open redirect.

**Sau khi chạy**
1. Kết quả PASS/FAIL cho từng chặng, không chỉ một nhãn “SSO works”.
2. Audit không chứa SAML assertions/tokens/cookies; quan sát đầy đủ sự kiện ở SP và IdP.
3. Xóa test users/credentials/fixture sensitive theo retention policy.
4. Ghi nhận issues về SameSite, sessions, certificate rollover, delegated IdP trust, cluster routing và phiên bản.
5. Nếu thay code/config, chạy lại full browser E2E; không chỉ rerun unit MockMvc.

## 18. Definition of Done và đánh giá tối thiểu

| Tiêu chí | Bằng chứng đạt |
| --- | --- |
| SP-initiated thật | Start từ `/reports` hoặc `/saml2/authenticate/corp`, AuthnRequest do SP tạo |
| Request đúng | Issuer, ID, Destination, ACS, binding và signing theo contract |
| Correlation | `InResponseTo`/RelayState khớp original request/browser session |
| Verified IdP | Chỉ chấp nhận signed Response/Assertion từ test IdP cert tin cậy |
| Conditions đúng | Audience/Recipient/NotBefore/NotOnOrAfter và replay checks |
| Authentication | Spring `Saml2Authentication` được tạo từ verified assertion |
| Identity mapping | `Issuer + stable subject` trỏ đúng app account/tenant |
| Session persistence | Request **tiếp theo** cùng browser còn authenticated |
| Browser isolation | Browser khác không dùng chung authenticated session |
| Authorization | Được phép đúng resource, không tự có admin |
| Logout/expiry | Phiên kết thúc làm protected route yêu cầu login |
| Negative tests | Fake/tampered/replayed/out-of-session response bị reject |
| Secure diagnostics | Không log raw SAMLResponse/cookie/keys |
| Cluster/browser behavior | SameSite/ACS POST/shared request store được kiểm chứng |

**Bộ test chỉ đạt “SP-initiated SSO end-to-end” khi cả handshake, SAML verification và authenticated application session đều được chứng minh.** Nếu chỉ có test `@WithMockUser`, chỉ có ID Token/JWT test, hoặc chỉ thấy AuthnRequest redirect, hãy ghi phạm vi thực tế là **unit/filter wiring**, không gọi E2E.

## 19. Câu hỏi tự kiểm tra

**Q1. Làm sao chứng minh đây là SP-initiated SSO chứ không phải IdP-initiated?**  
Phải có AuthnRequest do SP phát trước, có pending request được lưu; Response mang `InResponseTo` khớp request và đúng browser/session correlation. Một SAMLResponse gửi tự do từ IdP không có pending request không đạt tiêu chí SP-initiated.

**Q2. 302 sang IdP có đủ để test PASS không?**  
Không. Nó chỉ chứng minh endpoint phát request; chưa chứng minh IdP ký Response và Spring tạo session.

**Q3. Response có Status=Success và NameID đúng mà không có chữ ký có đăng nhập được không?**  
Không trong profile bảo mật cần thiết. SP phải xác minh signature/trust và các conditions bằng SAML provider; chỉ parse XML để lấy NameID là bypass.

**Q4. Cùng RelayState nhưng khác browser có chấp nhận không?**  
Không. Correlation phải gắn với original browser/session và pending request; nếu chỉ tin một RelayState chung, có thể có login fixation.

**Q5. Vì sao ACS POST thành công vẫn có thể không lưu được phiên?**  
Cookie cross-site POST có thể mất do SameSite, callback dùng session khác hoặc SecurityContext không persist. Cần kiểm request mới bằng cookie hiện hành.

**Q6. Tại sao `JSESSIONID` có thể xuất hiện trước khi user login?**  
SP có thể dùng HttpSession để lưu AuthnRequest và RelayState. Presence of session ≠ authenticated application session.

**Q7. Test @WithMockUser có chạy OpenSAML signature verifier không?**  
Không. Nó tạo mock SecurityContext, chỉ dùng cho authorization/controller logic; không phải protocol integration test.

**Q8. Assertion valid nhưng user bị 403 có là SAML failure không?**  
Không nhất thiết. Authentication/session có thể PASS; resource authorization có thể DENY theo role/tenant.

**Q9. Nguy cơ nếu test disable signature verification để có fake positive response?**  
Một unsigned/tampered assertion có thể giả user, dẫn đến account takeover. Test suite phải fail khi signature/issuer/audience checks bị bypass.

**Q10. Tại sao cần test full browser và cluster thay vì chỉ JVM MockMvc?**  
Vì browser cookie SameSite, cross-site POST, reverse proxy public ACS URL, redirect chain và cross-node request/session storage không được mô phỏng đầy đủ bằng unit mocks.

## 20. Tài liệu chính thức

1. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): filter chain, AuthnRequest, SAMLResponse, OpenSAML provider, RelyingPartyRegistration, default endpoint patterns.
2. [Spring Security – Producing SAML2 AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): request filter, Redirect/POST, signed requests, `HttpSessionSaml2AuthenticationRequestRepository` và cache repository/session-fixation warning.
3. [Spring Security – Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `Saml2AuthenticationTokenConverter`, `OpenSaml5AuthenticationProvider`, Response/Assertion validation, principal mapping và clock skew.
4. [Spring Security – SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/): SAML Web Browser SSO Profile và link samples.
5. [Spring Security – Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): MockMvc integration và tests with Security filter chain.
6. [Spring Security – Running a Test as a User](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `@WithMockUser`/mock processors chỉ tạo giả user, không thay SAML verification.
7. [Spring Security – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContext/session persistence, Spring Security 6+ session strategy.
8. [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): verify issuer/audience/recipient/time, XML signature wrapping/replay, RelayState/open redirect.
9. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): AuthnRequest, Response, Assertion, Conditions, SubjectConfirmation và signatures.
10. [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP Redirect/POST binding, DEFLATE/Base64, RelayState.
11. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO Profile, SP-initiated login, InResponseTo, bearer confirmation.
12. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, fixation, expiration và logout.
13. [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF handling khi có form POST/cookies.
14. [OWASP SAML Security – Testing considerations](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html#validate-security-countermeasures): negative assertions, replay and validation defenses.

**Kết luận:** kiểm thử **SP-initiated SSO** không chỉ là một `302` sang IdP hay một `SAMLResponse` có chữ “Success”. Một test hoàn chỉnh phải kiểm **AuthnRequest do SP phát → pending request/session/RelayState → signed IdP SAMLResponse → strict SAML validation và InResponseTo → Spring Authentication → authenticated session còn hiệu lực trên request tiếp theo → business authorization đúng**. Với Spring Security, giữ đúng SAML filters/repositories, không bypass OpenSAML verifier, và kiểm browser SameSite/cluster/session fixation trong môi trường gần production.