# Saml2WebSsoAuthenticationRequestFilter và khởi tạo AuthnRequest

> **Module:** Spring Security – federation. **Nhóm:** Luồng đăng nhập SAML2. Bài này giải thích luồng **SP-initiated SAML Web SSO** trong Spring Security Servlet: từ yêu cầu truy cập tài nguyên được bảo vệ đến `Saml2WebSsoAuthenticationRequestFilter`, cách resolver tạo `AuthnRequest`, gửi qua browser đến Identity Provider (IdP), lưu ngữ cảnh để đối chiếu response, và các lựa chọn cấu hình, bảo mật, kiểm thử. Ví dụ API tập trung vào Spring Security 6.3.x / Spring Boot 3.x; khi nâng major version phải kiểm tra tài liệu phiên bản đang chạy.

## 1. AuthnRequest là gì và filter này làm gì?

Trong SAML 2.0 Web SSO, ứng dụng làm **Service Provider (SP)** hoặc **Relying Party**, còn **Identity Provider (IdP)**, cũng được gọi là **Asserting Party**, chịu trách nhiệm xác thực user và phát SAML assertion/response. Để khởi tạo đăng nhập từ SP, ứng dụng tạo một XML message `<samlp:AuthnRequest>` yêu cầu IdP thực hiện xác thực. Trình duyệt vận chuyển request sang IdP thông qua HTTP-Redirect hoặc HTTP-POST binding.

**Saml2WebSsoAuthenticationRequestFilter** là điểm vào của Spring Security **tạo và gửi AuthnRequest** trong Servlet filter chain. Nó không xác minh một `SAMLResponse` và chưa cấp quyền cho user. Việc nhận, xác thực SAMLResponse qua ACS thuộc **Saml2WebSsoAuthenticationFilter** cùng converter, authentication manager và OpenSAML provider.

| Thành phần | Nhận gì? | Làm gì? | Kết quả |
| --- | --- | --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | Request khởi tạo, ví dụ `GET /saml2/authenticate/corp` | Resolve cấu hình, chuẩn bị AuthnRequest, lưu pending request, gửi sang IdP | Redirect/POST chứa `SAMLRequest` |
| `Saml2WebSsoAuthenticationFilter` | Callback `SAMLResponse` đến SP ACS | Resolve registration, dùng request đã lưu, xác thực response/assertion | `Authentication` thành công hoặc thất bại |
| `AuthorizationFilter` / `ExceptionTranslationFilter` / `AuthenticationEntryPoint` | Request vào trang được bảo vệ khi chưa login | Khởi động luồng login/điều hướng tới login page hoặc URL tạo AuthnRequest | Browser đi vào request filter |
| `RelyingPartyRegistrationRepository` | Các registration SP/IdP đã cấu hình | Cung cấp issuer, ACS, SSO URL, binding, keys | Dữ liệu tin cậy để resolver tạo request |

**Điểm dễ nhầm:** AuthnRequest chỉ là **đề nghị bắt đầu xác thực** từ SP; nó không phải assertion đã được IdP ký xác nhận user. Không được coi “request filter đã chạy” là user đã authenticated.

### Kết quả học tập

Sau bài học, người đọc sẽ:

- Mô tả được URL khởi tạo SAML và chuỗi filter/entry point dẫn tới nó.
- Phân biệt request filter, resolver, registration repository và request-state repository.
- Đọc được `AuthnRequest`: `ID`, `IssueInstant`, `Destination`, `Issuer`, `AssertionConsumerServiceURL` và `ProtocolBinding`.
- Giải thích cách Redirect và POST binding mã hóa request, vị trí chữ ký và điều kiện SP phải ký.
- Hiểu ranh giới giữa pending request trong HttpSession, `RelayState`, `InResponseTo` và session sau đăng nhập.
- Cấu hình và tùy biến đúng API Spring Security 6.3, kiểm thử cả luồng hợp lệ và các lỗi âm tính.

## 2. Tổng thể luồng SP-initiated SAML login

Giả sử các giá trị **giả lập**:

```text
SP public origin:       https://portal.example.org
registrationId:         corp
SP entityId:            https://portal.example.org/saml/sp/corp
SP AuthnRequest path:   /saml2/authenticate/corp
IdP entityId:           https://login.example.org/idp
IdP SingleSignOnService https://login.example.org/saml/sso
SP ACS:                 https://portal.example.org/login/saml2/sso/corp
Request binding:        HTTP-Redirect
Response binding:       HTTP-POST
```

Chuỗi xử lý:

```text
Browser                    Spring Security SP                  IdP
   |                              |                             |
   | GET /private                 |                             |
   |----------------------------->|                             |
   | AuthorizationFilter: yêu cầu authentication                 |
   | ExceptionTranslationFilter + AuthenticationEntryPoint      |
   |<-----------------------------| redirect login              |
   | GET /saml2/authenticate/corp |                             |
   |----------------------------->|                             |
   |  Saml2WebSsoAuthenticationRequestFilter                     |
   |     -> RequestResolver tìm registration corp                |
   |     -> tạo ID/Issuer/Destination/ACS và AuthnRequest         |
   |     -> ký/encode theo binding; sinh RelayState               |
   |     -> lưu pending request trong repository                  |
   |<-----------------------------| 302 tới IdP SSO + SAMLRequest
   | GET IdP /saml/sso?SAMLRequest=...                           |
   |----------------------------------------------------------->|
   |                              |       IdP verify request   |
   |                              |       login/MFA user       |
   |<-----------------------------------------------------------|
   | HTML form POST SAMLResponse về SP ACS                       |
   | POST /login/saml2/sso/corp   |                             |
   |----------------------------->|                             |
   |   Saml2WebSsoAuthenticationFilter                           |
   |     -> tìm pending request, đối chiếu InResponseTo           |
   |     -> validate trust/issuer/signature/audience/time        |
   |     -> Authentication, SecurityContext, session             |
   |<-----------------------------| redirect /private           |
```

Đây là luồng **SP-initiated**. Nếu IdP gửi **unsolicited/IdP-initiated SAMLResponse**, có thể không có AuthnRequest trước đó. Đó là trường hợp riêng, cần policy tiếp nhận và chống login injection/replay. Không suy ra từ sơ đồ rằng mọi response có thể bỏ `InResponseTo`.

### 2.1. Đi từ trang bảo vệ tới filter tạo request

Nếu browser gọi `GET /private` khi chưa authenticated, `AuthorizationFilter` từ chối truy cập. `ExceptionTranslationFilter` cùng `AuthenticationEntryPoint` hướng browser vào login flow. Khi chỉ có một registration và cấu hình phù hợp, entry point có thể chuyển ngay tới URL tạo request. Khi có nhiều IdP, app có thể hiển thị **trang chọn nhà cung cấp định danh** trước.

Browser cũng có thể truy cập trực tiếp `/saml2/authenticate/corp` qua link “Sign in with corporate SSO”. Khi đó request filter được kích hoạt mà không bắt buộc có một `/private` trước đó.

Không tự tạo một REST controller `/saml2/authenticate/corp` cùng URL nếu Spring Security đã chiếm endpoint này. Endpoint này là bộ lọc giao thức; controller trả JSON sẽ không thay thế an toàn quá trình tạo, ký và lưu AuthnRequest.

### 2.2. Ba địa chỉ thường bị đảo lẫn

| Địa chỉ | Thuộc bên nào? | Hành động |
| --- | --- | --- |
| `https://portal.example.org/saml2/authenticate/corp` | SP | Bắt đầu login và tạo AuthnRequest |
| `https://login.example.org/saml/sso` | IdP | Nhận AuthnRequest qua `SingleSignOnService` |
| `https://portal.example.org/login/saml2/sso/corp` | SP | Nhận SAMLResponse tại `AssertionConsumerService` (ACS) |

`SP entityID` là định danh logic của SP để đặt trong `Issuer`, **không bắt buộc** là URL có endpoint hoạt động. `registrationId=corp` là tên nội bộ Spring Security để chọn registration, **không phải** IdP entityID hay username.

## 3. Saml2WebSsoAuthenticationRequestFilter và các cộng tác viên

### 3.1. Endpoint request và request matcher

URL mặc định thường dùng:

```http
GET /saml2/authenticate/corp HTTP/1.1
Host: portal.example.org
```

Tài liệu Spring Security hiện hành mô tả cả dạng path `/saml2/authenticate/{registrationId}` và một dạng query `/saml2/authenticate?registrationId={registrationId}`; khả năng match/tùy biến phải đối chiếu phiên bản cụ thể. Với Spring Security 6.3, dạng path theo registration ID là cách an toàn, tường minh để giải thích hành vi mặc định.

Bước match phụ thuộc **SecurityFilterChain hiện hoạt**: khi dự án có chain cho REST API và chain cho web SAML, `/saml2/authenticate/**` phải đi vào chain có `saml2Login()`. Nếu chain của resource server bắt URL này trước, request filter SAML có thể không chạy.

### 3.2. Những lớp quan trọng và trách nhiệm

| Loại | Vai trò |
| --- | --- |
| `Saml2LoginConfigurer` | DSL tạo và cấu hình SAML login filters khi gọi `http.saml2Login(...)` |
| `Saml2WebSsoAuthenticationRequestFilter` | Filter phát một prepared SAML authentication request qua Redirect/POST |
| `Saml2AuthenticationRequestResolver` | Interface giải quyết request từ `HttpServletRequest`, trả kiểu `AbstractSaml2AuthenticationRequest` hoặc không match |
| `OpenSaml4AuthenticationRequestResolver` | Implementation dùng OpenSAML 4 trong Spring Security 6.3, có customizer |
| `RelyingPartyRegistrationRepository` | Kho registrations đã cấu hình và được phê duyệt |
| `RelyingPartyRegistration` | Dữ liệu tích hợp một SP–IdP: IDs, ACS, bindings, signing/verification keys |
| `Saml2AuthenticationRequestRepository` | Lưu/tải/xóa pending AuthnRequest để correlation callback |
| `HttpSessionSaml2AuthenticationRequestRepository` | Implementation mặc định lưu trạng thái trong `HttpSession` |
| `AbstractSaml2AuthenticationRequest` | Kiểu dữ liệu prepared request chung |
| `Saml2RedirectAuthenticationRequest` | Prepared request theo HTTP-Redirect binding |
| `Saml2PostAuthenticationRequest` | Prepared request theo HTTP-POST binding |
| `Saml2AuthenticationTokenConverter` | Tại callback, lấy SAMLResponse và xác định registration/request context |
| `Saml2WebSsoAuthenticationFilter` | Filter ACS chuyển SAMLResponse tới authentication manager/provider để xác thực |

**Phân biệt version:** ví dụ Spring Security 6.3.x dùng `OpenSaml4AuthenticationRequestResolver`. Ở các phiên bản mới, thư viện OpenSAML nền và API có thể khác. Khi dùng một snippet khác major version, phải kiểm tra javadoc, dependency và cú pháp builder thực tế.

### 3.3. Logic khái niệm khi request filter chạy

```text
HTTP request đến SP
  -> matcher chọn URL /saml2/authenticate/{registrationId}
  -> resolver xác định RelyingPartyRegistration
  -> dùng cấu hình SP/IdP tạo OpenSAML AuthnRequest
  -> xác định RelayState, binding, chữ ký theo policy
  -> chuẩn bị AbstractSaml2AuthenticationRequest
  -> repository.saveAuthenticationRequest(...)
  -> nếu Redirect: trả 302/Location sang IdP
     nếu POST: trả HTML form auto-submit sang IdP
```

Đây là **pseudocode giải thích trách nhiệm**, không phải trích nguyên mã nguồn một bản phát hành. Chi tiết thứ tự serialize/sign, object constructors và handling khi resolver không match thay đổi theo version. Ý nghĩa quan trọng: filter không tự chọn IdP từ nội dung XML do browser đưa tới; nó dựa vào **registration đã có** và strategy resolver.

### 3.4. Filter request khác filter response

`Saml2WebSsoAuthenticationFilter` nhận browser POST `SAMLResponse` tới ACS, dùng converter và provider xử lý authentication. Chữ ký Response/Assertion được kiểm tra bằng **IdP public signing certificate** tin cậy. Không dùng `Saml2WebSsoAuthenticationRequestFilter` hoặc tự thêm logic parse callback vào nó.

Sau khi request filter gửi request sang IdP, **chưa có authenticated principal** từ SAML login. `SecurityContext` được thiết lập khi callback hợp lệ được xử lý và authentication thành công.

## 4. Dữ liệu registration định hình AuthnRequest

`RelyingPartyRegistration` gồm cấu hình hai chiều:

| Thuộc tính | Phía | Được dùng vào đâu? |
| --- | --- | --- |
| `registrationId` | SP | Chọn đúng IdP/SP integration khi browser bắt đầu login |
| `entityId` của SP | SP | Giá trị `Issuer` trong AuthnRequest |
| `assertionConsumerServiceLocation` | SP | Địa chỉ ACS, có thể đi trong `AssertionConsumerServiceURL` |
| `assertionConsumerServiceBinding` | SP | Binding IdP dùng trả response; có thể đi trong `ProtocolBinding` |
| `signingX509Credentials` | SP | Private signing key/certificate dùng ký message SP phát |
| `entityId` của IdP | IdP | Định danh IdP để xây trust và xác minh callback |
| `singleSignOnServiceLocation` | IdP | `Destination`, URL IdP nhận request |
| `singleSignOnServiceBinding` | IdP | HTTP-Redirect hay HTTP-POST cho request SP gửi |
| `wantAuthnRequestsSigned` | IdP | Policy IdP mong SP ký authentication requests |
| `verificationX509Credentials` | IdP | Public cert IdP để SP verify response/assertion |

**Lỗi phổ biến:** lấy IdP entityID đặt vào `Issuer` AuthnRequest; đặt SP ACS vào `Destination`; lấy IdP verification certificate làm SP signing key; dùng `acs.binding` như request binding. Chúng dẫn đến request bị từ chối hoặc tạo ranh giới tin cậy sai.

### 4.1. XML AuthnRequest minh họa

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req_31f0a"
    Version="2.0"
    IssueInstant="2026-11-07T03:20:00Z"
    Destination="https://login.example.org/saml/sso"
    AssertionConsumerServiceURL="https://portal.example.org/login/saml2/sso/corp"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>https://portal.example.org/saml/sp/corp</saml:Issuer>
    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
        AllowCreate="true"/>
</samlp:AuthnRequest>
```

Đây là **trích đoạn XML giáo dục**, chưa có chữ ký và không phải message hoàn chỉnh cho IdP thực. Từng trường có ý nghĩa:

- `ID`: identifier của request, cần duy nhất cho giao dịch; IdP có thể trả `InResponseTo` tương ứng.
- `IssueInstant`: thời điểm phát request; IdP có thể kiểm tra cửa sổ thời gian.
- `Destination`: **IdP SSO endpoint**.
- `Issuer`: **SP entityID**.
- `AssertionConsumerServiceURL`: **SP ACS URL** mà IdP được phép trả response.
- `ProtocolBinding`: **binding mong nhận SAMLResponse**, không phải binding gửi AuthnRequest.
- `NameIDPolicy`: yêu cầu định dạng NameID phù hợp hợp đồng với IdP.
- `ForceAuthn` (tùy chọn): yêu cầu xác thực lại; phụ thuộc chính sách IdP.

`RelayState` thường đi ở query parameter/form field theo HTTP binding, **không ở trong XML AuthnRequest**. Nó phải được sinh/kiểm tra theo login transaction và redirect policy của ứng dụng.

### 4.2. Bắt đầu login không đồng nghĩa IdP đã xác thực

Ở thời điểm tạo ID, SP chỉ giữ trạng thái “đang chờ”. User chưa có `Saml2AuthenticatedPrincipal`/session authentication do IdP xác nhận. Nếu user đóng browser, từ chối login hoặc IdP không phản hồi, trạng thái pending sẽ hết hạn/được dọn theo thiết kế repository; không coi request đã phát là bằng chứng thành công.

## 5. HTTP-Redirect và HTTP-POST binding

### 5.1. Redirect binding

Với Redirect, request XML được raw-DEFLATE, Base64 encode, URL encode và gửi qua query `SAMLRequest` tới IdP SingleSignOnService. Nếu request được ký, chữ ký thường nằm trong **query** dưới dạng `SigAlg` và `Signature`.

```text
XML AuthnRequest
  -> raw DEFLATE
  -> Base64
  -> URL-encoded SAMLRequest
  -> RelayState (nếu dùng)
  -> SigAlg + Signature (nếu ký)
  -> HTTP 302 Location: IdP SSO
```

Ví dụ định dạng giao thức **minh họa, không phải payload hợp lệ**:

```http
HTTP/1.1 302 Found
Location: https://login.example.org/saml/sso?SAMLRequest=ENCODED_TEST_DATA&RelayState=opaqueState7&SigAlg=SIGNATURE_ALGORITHM_URI&Signature=ENCODED_SIGNATURE
```

Để kiểm tra chữ ký Redirect, IdP dùng public signing certificate của **SP** và chuỗi tham số URL-encoded theo đúng thứ tự:

```text
SAMLRequest=<url-encoded-value>&RelayState=<url-encoded-value>&SigAlg=<url-encoded-value>
```

Nếu không có RelayState, bỏ cặp `RelayState=...` cùng dấu phân cách tương ứng. `Signature` là kết quả ký, không phải phần dữ liệu được đưa vào ký. Với Redirect, XML đã inflate có thể **không có `<ds:Signature>`**, nhưng request vẫn được ký hợp lệ qua query. Đừng nhầm hai dạng chữ ký.

### 5.2. POST binding

Nếu IdP hỗ trợ/đòi POST, request được Base64 encode (không áp dụng raw DEFLATE như Redirect) rồi đặt trong hidden field của HTML form trỏ tới IdP:

```html
<form action="https://login.example.org/saml/sso/post" method="post">
  <input type="hidden" name="SAMLRequest" value="BASE64_TEST_DATA"/>
  <input type="hidden" name="RelayState" value="opaqueState7"/>
  <button type="submit">Continue SSO</button>
</form>
```

Đây là **HTML minh họa**, không thay thế filter Spring Security, signing hoặc nonce/state management. Signed POST AuthnRequest thường dùng **XML Digital Signature** ngay trong XML trước khi Base64 encode, không dùng `SigAlg` và `Signature` query của Redirect.

| Tiêu chí | Request Redirect | Request POST |
| --- | --- | --- |
| Browser → IdP | GET | POST |
| `SAMLRequest` | Query parameter | HTML form field |
| Encoding | Raw DEFLATE + Base64 + URL encoding | Base64 XML |
| Vị trí signature điển hình | Query `SigAlg`/`Signature` | XML `ds:Signature` |
| URL đích | IdP SingleSignOnService Redirect Location | IdP SingleSignOnService POST Location |
| Liên quan ACS binding | Độc lập | Độc lập |

**Quan trọng:** SP hoàn toàn có thể gửi AuthnRequest **Redirect** trong khi `ProtocolBinding` trong XML là **HTTP-POST**: field này yêu cầu IdP trả **SAMLResponse** qua POST vào ACS.

## 6. Lưu pending AuthnRequest và correlation callback

`Saml2AuthenticationRequestRepository` là cầu nối giữa filter khởi tạo và filter tiếp nhận response. Nó lưu dữ liệu prepared request để callback xác định IdP/registration, request ID và ngữ cảnh tin cậy.

### 6.1. Mặc định dùng HttpSession

`HttpSessionSaml2AuthenticationRequestRepository` là lựa chọn mặc định phổ biến của Spring Security 6.x. Nó lưu đối tượng `AbstractSaml2AuthenticationRequest` trong HTTP session của browser SP. Khi response đến ACS, Spring Security có thể lấy request đang đợi, đối chiếu `InResponseTo` và ngữ cảnh registration.

Trước login, session này là **pending login session**, chưa phải principal đã authenticated. Sau callback thành công, Spring Security có thể lưu SecurityContext/session login. Thời hạn assertion khác thời hạn HttpSession.

### 6.2. Khác RequestCache và SavedRequest

| Kho | Lưu gì? | Dùng để làm gì? |
| --- | --- | --- |
| `RequestCache` | Request vào trang nội bộ (ví dụ `/private`) trước login | Điều hướng trở lại trang đó sau login |
| `Saml2AuthenticationRequestRepository` | Prepared AuthnRequest đã gửi, RelayState/ngữ cảnh SAML | Correlation khi nhận SAMLResponse |
| `SecurityContextRepository` | Thông tin `Authentication` đã xác thực | Giữ danh tính ở các request tiếp theo |

Không dùng `RequestCache` để thay `InResponseTo`/pending SAML request store. Hai loại “request được lưu” giải các bài toán khác nhau.

### 6.3. Session cookie, SameSite và cross-site POST

Trong flow phổ biến, request filter bắt đầu login ở SP, nhưng sau đó browser POST `SAMLResponse` **từ origin IdP về origin SP**. Nếu SP session cookie dùng `SameSite=Lax` hoặc `Strict`, browser có thể không gửi cookie cho cross-site POST. Khi đó response filter không tìm được pending request trong `HttpSession` dù SAMLResponse đúng.

Hướng xử lý:

1. Trên browser thật, kiểm tra cookie `Set-Cookie` ở bước khởi tạo và Cookie header ở ACS POST.
2. Kiểm tra `SameSite`, `Secure`, HTTPS public origin và trusted reverse proxy.
3. Nếu cần cookie qua cross-site POST, cân nhắc chiến lược `SameSite=None; Secure` và biện pháp CSRF phù hợp, hoặc một thiết kế state/correlation khác được kiểm soát.
4. Với multi-node SP, dùng session replication/compatible shared session store khi callback đến pod khác.
5. Không bỏ `InResponseTo` và không chấp nhận mọi unsolicited response để chữa triệu chứng mất session.

### 6.4. Chuyển sang cache ngoài session phải giữ ràng buộc browser

Có thể thay repository bằng implementation sử dụng distributed cache để giải quyết replication/SameSite. Tuy nhiên, **lookup bằng RelayState hoặc InResponseTo trong cache không tự chứng minh browser nhận response đã khởi tạo request đó**. Kẻ tấn công có thể tìm cách tạo login transaction rồi gây **login injection/login fixation** nếu correlation yếu.

Yêu cầu tối thiểu: state đủ ngẫu nhiên, TTL ngắn, chỉ sử dụng một lần, giới hạn concurrent requests, gắn registration/tenant, bảo vệ khỏi log leakage, giải quyết failure/replay atomically, và policy đảm bảo browser/transaction binding. Chữ ký SAML/trust/audience/time validation vẫn bắt buộc. Cần thử nhiều tab và nhiều SP replicas.

## 7. Cấu hình Spring Boot 3.x / Spring Security 6.x

### 7.1. SecurityFilterChain

Tạo `SamlSecurityConfiguration.java` trong project Spring Boot có SAML2 service provider dependency:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là **class cấu hình cho ứng dụng Spring Boot**, không phải chương trình Java tự chạy bằng `java` độc lập. `saml2Login()` cấu hình SAML request + response filters. Cần cung cấp bean `RelyingPartyRegistrationRepository` hoặc cấu hình Boot để tạo bean tương ứng; code trên không tự có IdP.

Nếu đã dùng DSL `saml2Login()`, không cần tự `new Saml2WebSsoAuthenticationRequestFilter(...)` rồi add filter thêm một lần. Việc tự lắp hai filter dễ tạo double registration, wrong matcher hoặc state lệch.

### 7.2. application.yml giả lập

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
              binding: POST
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/config/sp-signing.crt"
            assertingparty:
              entity-id: "https://login.example.org/idp"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                binding: REDIRECT
                sign-request: true
              verification:
                credentials:
                  - certificate-location: "file:/run/config/idp-signing.crt"
```

Đây là ví dụ **không hoạt động nếu thiếu file khóa/certificate, trust và IdP registration thực tế**. `{baseUrl}`/`{registrationId}` là placeholders URI của Spring Security, được giải quyết theo request/deployment config.

- `entity-id` là SP entityID, đưa vào `Issuer` request.
- `acs.location` là callback của SP, không phải URL gửi AuthnRequest.
- `acs.binding` là response binding, có thể là POST.
- `assertingparty.singlesignon.url` là IdP SSO endpoint nhận AuthnRequest.
- `assertingparty.singlesignon.binding` quyết định Redirect hay POST request.
- `assertingparty.singlesignon.sign-request` định cấu hình policy request signing.
- `signing.credentials` cần **SP private key + SP public certificate**.
- `assertingparty.verification.credentials` là **IdP public signing certificate** để kiểm tra SAMLResponse/assertion.

**Không dùng một certificate của IdP như SP private signing key.** Nếu IdP yêu cầu ký AuthnRequest, SP phải có khóa riêng tương ứng cert mà IdP đã đăng ký để xác minh.

### 7.3. Request trigger và đường đi mạng

Mở:

```text
https://portal.example.org/saml2/authenticate/corp
```

Nếu IdP SSO dùng Redirect và policy yêu cầu ký, browser thường nhận một 302/303 đến `https://login.example.org/saml/sso` với `SAMLRequest`, `SigAlg` và `Signature`. Nếu POST binding, browser nhận HTML form tự submit. Nếu endpoint trả 404, cần rà filter chain/matcher/registration, **chưa có cơ sở nói IdP từ chối đăng nhập**.

### 7.4. Reverse proxy và public URL

Ví dụ SP chạy nội bộ `http://10.0.0.5:8080`, public origin là `https://portal.example.org`. Nếu `{baseUrl}` bị tính theo origin nội bộ, AuthnRequest có thể phát:

```text
AssertionConsumerServiceURL =
  http://10.0.0.5:8080/login/saml2/sso/corp
```

IdP có thể từ chối vì không khớp ACS đã đăng ký. Cấu hình proxy forwarded headers **từ ingress đáng tin** và public URLs chính xác, rồi kiểm tra SP metadata lẫn request thực tế. Không bỏ Recipient/Destination validation để tránh lỗi mismatch.

## 8. Tùy biến AuthnRequest đúng chỗ

### 8.1. Trường hợp cần resolver tùy biến

Nhu cầu thường gặp là thay `ForceAuthn`, `NameIDPolicy`, `RequestedAuthnContext` hoặc RelayState. Với endpoint, binding, signing và certificate, nên ưu tiên thay **RelyingPartyRegistration/metadata** trước khi viết code. Các thông số này là hợp đồng SP–IdP, không phải logic business trong controller.

### 8.2. Ví dụ Spring Security 6.3: ForceAuthn customizer

Spring Security 6.3 sử dụng `OpenSaml4AuthenticationRequestResolver`. API `setAuthnRequestCustomizer` nhận callback với `getAuthnRequest()`. Ví dụ class thay cho class cấu hình mặc định ở trên:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ReauthenticationSamlConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RelyingPartyRegistrationRepository registrations) throws Exception {

        OpenSaml4AuthenticationRequestResolver resolver =
                new OpenSaml4AuthenticationRequestResolver(registrations);

        resolver.setAuthnRequestCustomizer(context ->
                context.getAuthnRequest().setForceAuthn(Boolean.TRUE));

        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationRequestResolver(resolver));

        return http.build();
    }
}
```

**Lưu ý kỹ thuật:** đây là class cấu hình Spring cần dependency/version đúng, không phải Java thuần. `ForceAuthn=true` yêu cầu IdP xác thực lại, có thể gây nhiều login/MFA; **không bật global** nếu mục tiêu là SSO thông thường. Tùy policy, chỉ bật ở trường hợp cần re-authentication. Khi nâng Spring Security major, xác minh các lớp resolver/OpenSAML thay vì copy API 6.3.

### 8.3. Custom authentication-request URI

Spring Security cho phép thay URL khởi tạo qua cấu hình `Saml2LoginConfigurer` (API `authenticationRequestUri` hoặc `authenticationRequestUriQuery` tùy phiên bản). Khi thay đường dẫn:

1. Resolver/matcher phải nhận đúng pattern mới.
2. Login page và `AuthenticationEntryPoint` phải trỏ đúng pattern.
3. Security filter chain phải bao phủ URL mới.
4. Chọn `registrationId` an toàn, không tạo IdP từ request tùy ý.
5. **ACS vẫn là endpoint riêng**; không tự đổi theo request URI.

Đặc biệt khi phiên bản 6.3 khác tài liệu 7.x, tra javadoc của bản đang chạy trước khi dùng method name cụ thể.

### 8.4. RelayState resolver

Trong Spring Security 6.3, `OpenSaml4AuthenticationRequestResolver` có `setRelayStateResolver(...)`. Nếu tùy biến RelayState, cần giá trị opaque và policy xác định chiều dài, TTL, dữ liệu được phép, state/session binding, one-time use và redirect allowlist. Một query `returnUrl=https://attacker.example` không được trở thành target redirect sau SSO mà không kiểm soát.

## 9. Phân tích lỗi theo đúng bước của filter

| Triệu chứng | Vị trí nhiều khả năng | Cách xử lý |
| --- | --- | --- |
| `GET /saml2/authenticate/corp` trả 404 | URL/`SecurityFilterChain`/request matcher | Kiểm tra chain match và registration; IdP chưa nhận request |
| Không thấy redirect/form tới IdP | Request resolver hoặc registration | Kiểm tra `RelyingPartyRegistrationRepository` và logs an toàn |
| Chọn sai IdP khi multi-tenant | Registration mapping | Ràng buộc tenant/issuer với registration đáng tin |
| IdP trả “unknown SP” | `Issuer`/SP entityID | Đối chiếu IdP registration, metadata |
| IdP trả “destination invalid” | `Destination`/SSO URL | Đối chiếu SingleSignOnService Location theo binding |
| IdP yêu cầu signed request | Signing policy/key SP | Cấu hình khóa riêng SP và cert đăng ký tại IdP |
| Redirect XML không có `ds:Signature` | Hiểu sai binding | Xem query `SigAlg`/`Signature` |
| POST request bị IdP reject | Binding/endpoint/XML signature | Chọn đúng POST SSO Location và key, validate XML sig |
| ACS URL trong XML là HTTP nội bộ | Forwarded headers/public baseUrl | Sửa reverse proxy trust và ACS metadata |
| Callback không thấy pending request | HttpSession/cookie/SameSite/TTL | Kiểm tra POST cookie/session/shared state |
| `InResponseTo` sai | Pending request khác callback | Reject; rà nhiều tabs, session, RelayState |
| Response signature đúng nhưng vẫn fail | `Issuer`, audience, recipient, time, request binding | Điều tra response filter/provider |
| Login vòng lặp | Session/ACS/request correlation/validation | Xem toàn bộ HTTP redirects và logs lý do |
| `RequestCache` quay về sai URL | SavedRequest/success handling | Tách kiểm tra điều hướng khỏi AuthnRequest repository |
| Login thành công nhưng thiếu quyền | Authorization mapping | Sửa policy/domain roles; không sửa request filter để cấp quyền |

Không suy đoán 401/403/404 là một lỗi duy nhất: SecurityFilterChain, IdP server và callback handler có cách trả mã khác nhau. Kết hợp trace HTTP, thông tin event và cấu hình xác thực để phân định.

### 9.1. Đặc biệt: Session state bị mất ở callback

Hãy bắt đầu bằng cách xác nhận **request đã thực sự được tạo và lưu** ở SP; tiếp theo kiểm tra cookie từ browser ở IdP POST ACS, session ID/TTL, proxy và môi trường multi-node. Nếu SP cố lookup request ở session rỗng, đừng chữa bằng cách tắt `InResponseTo`/SAML signature verification.

### 9.2. Đặc biệt: Signing key và thuật toán

Signed AuthnRequest bằng Redirect cần query signature đúng encoding và SP signing private key; signed POST thường cần XML Signature. Thuật toán mặc định/được thương lượng phụ thuộc IdP metadata và phiên bản thư viện; thường dùng RSA-SHA256, tránh downgrade sang SHA-1 chỉ để “chạy được”. Certificate rollover cần IdP chấp nhận SP public key mới trước khi SP bắt đầu ký bằng key mới.

## 10. Những ranh giới bảo mật không được bỏ qua

1. **Metadata và IdP trust:** Browser chỉ được chọn registration có sẵn. Không tải metadata theo URL do attacker tự cung cấp rồi tự động tin signing key đó.
2. **Request signing:** ký AuthnRequest khi IdP policy yêu cầu, với SP private key; đừng lấy IdP certificate làm signing credential.
3. **Response validation:** xác minh IdP signing key, issuer, audience, recipient, destination, time conditions và request correlation; request filter không làm phần này.
4. **Replay/one-time:** pending request được liên kết login transaction; chống replay response/assertion là phần validation riêng, không tự có chỉ vì HTTP session tồn tại.
5. **RelayState:** state/nav hint không phải trust anchor. Chặn login injection và open redirect.
6. **Session:** cookie `Secure`/`HttpOnly`, `SameSite` phù hợp cross-site POST, rotate session ID sau đăng nhập và logout/invalidate phía server.
7. **Multi-IdP/multi-tenant:** tách registration, trust keys, account mapping và quyền theo issuer/tenant; không gom mọi user theo email mà bỏ qua issuer.
8. **Logging:** không log raw `SAMLResponse`/assertion, cookie, private signing keys và state nhạy cảm; dùng correlation ID và error code.
9. **Authorization:** một `Saml2Authentication` hợp lệ vẫn cần xác thực quyền theo endpoint/resource/tenant trước khi truy cập dữ liệu.

## 11. Thực hành Java 17+: mô phỏng pending request và InResponseTo

Ví dụ Java thuần này minh họa lý do phải **giữ state sau khi phát AuthnRequest**. Đây là mô hình về string matching, **không tạo/giải mã XML, không ký, không kiểm tra SAML Response hay authentication thật**.

Lưu file `AuthnRequestCorrelationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class AuthnRequestCorrelationDemo {

    record PendingRequest(String id, String registrationId,
                          String trustedIdpIssuer) {}

    record ResponseInfo(String inResponseTo,
                        String registrationId, String idpIssuer) {}

    static boolean consumeIfMatched(
            ResponseInfo response, Map<String, PendingRequest> pending) {
        PendingRequest request = pending.get(response.inResponseTo());
        if (request == null) {
            return false;
        }
        if (!request.registrationId().equals(response.registrationId())) {
            return false;
        }
        if (!request.trustedIdpIssuer().equals(response.idpIssuer())) {
            return false;
        }
        pending.remove(request.id());
        return true;
    }

    public static void main(String[] args) {
        Map<String, PendingRequest> pending = new HashMap<>();
        pending.put("_req_42", new PendingRequest(
                "_req_42", "corp", "https://login.example.org/idp"));

        ResponseInfo wrongTenant = new ResponseInfo(
                "_req_42", "partner", "https://login.example.org/idp");
        ResponseInfo correct = new ResponseInfo(
                "_req_42", "corp", "https://login.example.org/idp");

        System.out.println("initial pending: " + pending.size());
        System.out.println("wrong registration: "
                + consumeIfMatched(wrongTenant, pending));
        System.out.println("correct response: "
                + consumeIfMatched(correct, pending));
        System.out.println("replayed response: "
                + consumeIfMatched(correct, pending));
        System.out.println("remaining pending: " + pending.size());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac AuthnRequestCorrelationDemo.java
java AuthnRequestCorrelationDemo
```

Stdout chính xác:

```text
initial pending: 1
wrong registration: false
correct response: true
replayed response: false
remaining pending: 0
```

**Phân tích:** Request `_req_42` gắn với `corp` và issuer mong đợi. Response nhầm registration không làm mất pending state, response có thông tin khớp sẽ tiêu thụ ID và lần gọi tiếp bị từ chối. Tuy nhiên, kẻ tấn công có thể tự tạo object `ResponseInfo` chứa dữ liệu giả: **kết quả `true` chỉ phản ánh logic ví dụ**, không chứng minh issuer thật hay chữ ký hợp lệ. Hệ thống production phải dùng Spring Security/OpenSAML xác minh chữ ký, issuer, audience, recipient, thời gian, subject confirmation, binding và replay trước khi tạo `Authentication`. `HashMap` cũng không xử lý atomic consume hay cross-node store; không đưa thẳng đoạn này vào production.

## 12. Các tình huống kiểm thử tích hợp

| Test | Kỳ vọng an toàn |
| --- | --- |
| Truy cập protected URL khi chưa login | Entry point đưa browser vào SAML login |
| Gọi `/saml2/authenticate/corp` | Chọn registration `corp` và tạo AuthnRequest |
| Gọi registration không tồn tại | Không tạo request cho IdP tùy ý |
| Redirect binding | 302 có `SAMLRequest`, đi đúng IdP SSO URL |
| Redirect request ký | Query có `SigAlg`/`Signature`; IdP test verify được |
| POST binding | HTML form `SAMLRequest` POST tới IdP POST SSO |
| Response dùng POST khi request dùng Redirect | Hợp lệ nếu ACS/IdP đã thỏa thuận |
| SP signing key thiếu khi bắt ký | Không phát request được coi là đã ký hợp lệ |
| SP entityID sai | IdP từ chối hoặc báo issuer unknown |
| ACS public URL sai qua proxy | Bị phát hiện, không bỏ Recipient validation |
| `InResponseTo` không khớp request pending | Reject |
| Mất session cookie ở callback | Reject an toàn và điều tra SameSite/session |
| RelayState trỏ domain ngoài allowlist | Không open redirect |
| Hai tabs login khác registrations | Không trộn state/issuer/tenant |
| Callback sang pod khác | Dùng compatible session/store hoặc fail an toàn |
| SAMLResponse signature sai | SP từ chối authentication |
| SAMLResponse ký đúng nhưng audience sai | SP từ chối |
| Replay cùng response/assertion | Không phát thêm login session |
| Success login rồi mở `/private` | Authenticated session + authorization hoạt động |
| User thiếu quyền ở `/admin` | 403/deny theo policy dù đã SAML login |

Khi kiểm thử bằng browser, có thể quan sát request HTTP theo thứ tự nhưng **không chia sẻ raw SAMLResponse hoặc session cookies trong issue/traces**. Nên log `registrationId`, event, request correlation ID, lý do reject và thời gian sau khi kiểm soát dữ liệu nhạy cảm.

### 12.1. Quy trình chẩn đoán tối thiểu

1. Xác minh filter chain match đúng `/saml2/authenticate/{registrationId}`; request đã chạm request filter chưa?
2. Xác minh repository có registration cần thiết; SP entityID, IdP SSO Location/Binding và SP ACS đúng.
3. Quan sát Redirect/POST thực phát theo binding, chữ ký request có đúng format và cert SP đã tin không?
4. Xác minh browser gửi SAMLRequest tới đúng IdP, IdP chấp nhận và trả SAMLResponse.
5. Xác minh ACS nhận POST và có đúng pending request/state/session; kiểm tra `SameSite`.
6. Xác minh SAMLResponse signature/issuer/audience/recipient/time và `InResponseTo` được kiểm tra; chỉ sau đó mới có `Authentication`.
7. Kiểm tra success handler, SavedRequest và authorization khi user quay vào ứng dụng.

## 13. Câu hỏi ôn tập

**1. `Saml2WebSsoAuthenticationRequestFilter` tạo ra user principal?**  
Không. Filter tạo **AuthnRequest**. Principal được tạo khi callback SAMLResponse được xác thực thành công ở response filter/provider.

**2. Dùng đường dẫn `/saml2/authenticate/corp`; `corp` có phải IdP entityID?**  
Không. Nó là **registrationId** nội bộ của Spring, chọn cấu hình SP/IdP đã được định nghĩa.

**3. `AuthnRequest.Destination` và `AssertionConsumerServiceURL` trỏ về đâu?**  
`Destination` trỏ **IdP SSO endpoint**; `AssertionConsumerServiceURL` trỏ **SP ACS endpoint**.

**4. Vì sao `ProtocolBinding=HTTP-POST` không buộc AuthnRequest phải gửi POST?**  
Bởi field `ProtocolBinding` trong AuthnRequest nói về **SAMLResponse binding** mà SP muốn nhận, không phải transport request sang IdP.

**5. Request đã ký nhưng XML Redirect không có `ds:Signature`, có sai không?**  
Không. Với **HTTP-Redirect binding**, signature có thể nằm ở query `SigAlg`/`Signature`.

**6. `HttpSessionSaml2AuthenticationRequestRepository` làm gì?**  
Lưu **pending AuthnRequest** và ngữ cảnh để phối hợp callback, không phải kho user roles hay SavedRequest về trang ban đầu.

**7. Tại sao callback có thể mất state khi `SameSite=Lax`?**  
Vì SAMLResponse thường gửi qua **cross-site POST**; browser có thể không đính kèm session cookie SP, làm không tìm được pending request.

**8. Nếu cache ngoài session theo RelayState thì có tự an toàn không?**  
Không. Cần ràng buộc login với browser/transaction, TTL, one-time semantics, anti-replay và validation SAML đầy đủ để tránh login fixation/injection.

**9. `OpenSaml4AuthenticationRequestResolver` có dùng trong mọi Spring Security version không?**  
Không. Đây là API của thế hệ OpenSAML 4 như Spring Security 6.3; các major version khác có thể đổi resolver và builder API.

**10. Vì sao response có signature hợp lệ vẫn cần kiểm tra `InResponseTo`?**  
Signature xác nhận nguồn/vùng dữ liệu ký; `InResponseTo` ràng buộc response với **giao dịch login mà SP đã khởi tạo**, giúp tránh lẫn request và một số dạng login injection/replay.

## Tài liệu tra cứu

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) – entrypoint, request filter và response filter.
- [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) – request endpoint, repository, cache, binding và signing.
- [Spring Security 6.3 API – OpenSaml4AuthenticationRequestResolver](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html) – các customization hooks.
- [Spring Security 6.3 API – AuthnRequestContext](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.AuthnRequestContext.html) – truy cập AuthnRequest và registration trong customizer.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) – xác thực SAMLResponse phía ACS.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) – cấu trúc/AuthnRequest, `Issuer`, `InResponseTo` và điều kiện.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf) – Redirect, POST, encoding, signature và RelayState.
- [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) – SP/IdP endpoints, bindings, certificates.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet) – signature validation, trust boundary và replay.

**Ghi nhớ:** `Saml2WebSsoAuthenticationRequestFilter` là điểm bắt đầu một **giao dịch xác thực SAML**, không phải bộ xác thực response. Nó dựa trên registration và request resolver để tạo AuthnRequest, chuyển sang IdP theo binding/signing policy, lưu ngữ cảnh pending login và phối hợp với callback. Chỉ sau khi `Saml2WebSsoAuthenticationFilter`/provider xác minh SAMLResponse hợp lệ, Spring Security mới có thể cấp `Authentication` cho user và áp dụng authorization.