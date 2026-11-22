# Saml2WebSsoAuthenticationFilter và tiếp nhận SAMLResponse

Khi người dùng đăng nhập qua **SAML 2.0 Web Browser SSO**, Identity Provider (IdP) xác thực người dùng rồi trả về **SAML Response** cho ứng dụng Service Provider (SP). Trong Spring Security Servlet, thành phần tiếp nhận kết quả này là **`Saml2WebSsoAuthenticationFilter`**. Nó là điểm nối từ HTTP callback ở **Assertion Consumer Service (ACS)** sang hệ thống `AuthenticationManager` của Spring Security.

Điều quan trọng là hiểu đúng ranh giới trách nhiệm: **filter định tuyến và khởi động quá trình xác thực, converter trích xuất dữ liệu/request context, còn authentication provider mới thực hiện xác minh SAML**. Việc trình duyệt gửi một trường `SAMLResponse` không chứng minh danh tính; chỉ sau khi các bước xác thực thành công, ứng dụng mới có `Authentication` đáng tin cậy để tạo phiên và thực thi quyền truy cập.

## 1. Hai filter của hai chặng đăng nhập

Trong Spring Security, SAML login có **chặng yêu cầu** và **chặng nhận phản hồi**:

| Chặng | Thành phần | Đường dẫn thường gặp | Nhiệm vụ |
| --- | --- | --- | --- |
| Bắt đầu SSO | `Saml2WebSsoAuthenticationRequestFilter` | `/saml2/authenticate/{registrationId}` | Sinh `AuthnRequest`, ghi yêu cầu đang chờ, gửi đến IdP SSO endpoint bằng binding được hỗ trợ. |
| Nhận kết quả SSO | **`Saml2WebSsoAuthenticationFilter`** | **`/login/saml2/sso/{registrationId}`** | Nhận callback chứa `SAMLResponse`, chuyển thành `Saml2AuthenticationToken`, gọi `AuthenticationManager`. |

Đường dẫn đầu là **SP khởi tạo** yêu cầu đi tới IdP; đường dẫn sau là **SP nhận** kết quả từ IdP. Trong metadata SP, đường dẫn thứ hai phải được phản ánh trong `AssertionConsumerService/@Location`. Các phiên bản Spring Security mới có thể hỗ trợ thêm URL ACS không chứa `registrationId`; khi đổi endpoint hoặc cách tìm registration, phải đối chiếu tài liệu và cấu hình của phiên bản đang chạy.

**Không nhầm tên:** `Saml2WebSsoAuthenticationRequestFilter` có chữ *Request* và gửi AuthnRequest; `Saml2WebSsoAuthenticationFilter` xử lý *Response*. Đây không phải hai cách gọi cho cùng một filter.

## 2. Chuỗi xử lý hoàn chỉnh: từ trình duyệt tới SecurityContext

~~~text
                  SP / Spring Security                      IdP
                        |                                   |
Browser -- GET /private --> AuthorizationFilter            |
                        | chưa xác thực                      |
                        v                                   |
              ExceptionTranslationFilter                    |
                        |                                   |
                        v                                   |
        Saml2WebSsoAuthenticationRequestFilter              |
                        | tạo và lưu AuthnRequest           |
                        +----- AuthnRequest --------------->|
                                                            | xác thực
Browser <---------------- HTML form (SAMLResponse) ---------+
                        |
                        | POST tới SP ACS
                        v
       Saml2WebSsoAuthenticationFilter
                        |
                        v
          Saml2AuthenticationTokenConverter
          - lấy SAMLResponse từ HttpServletRequest
          - tìm RelyingPartyRegistration tin cậy
          - liên kết AuthnRequest đã lưu khi có
                        |
                        v
              Saml2AuthenticationToken
                        |
                        v
               AuthenticationManager
                        |
                        v
          OpenSAML AuthenticationProvider
          - parse/decrypt và xác minh chữ ký
          - issuer, destination, audience, thời hạn
          - InResponseTo, subject confirmation, replay
                        |
             +----------+------------+
             |                       |
       thất bại                   thành công
             |                       |
       failure handler      Saml2Authentication
       không cấp phiên         SecurityContext
                                     |
                           success handler / phiên SP
                                     |
                              protected resource
~~~

Đây là **sơ đồ trách nhiệm**, không cố định mọi filter hoặc handler trong một bản Spring Security cụ thể. Vị trí thực tế phụ thuộc `SecurityFilterChain`, authentication success/failure handler, repository và phiên bản thư viện. Với cấu hình mặc định của ứng dụng web, sau thành công Spring Security thường chuyển người dùng về yêu cầu trước đó thông qua saved-request success handler; không nên tự suy ra rằng trình duyệt sẽ luôn nhận HTTP 200 từ ACS.

### 2.1. Ví dụ các HTTP request

Người dùng bắt đầu tại một tài nguyên cần đăng nhập:

~~~http
GET /private HTTP/1.1
Host: sp.example.org
~~~

SP chuyển hướng tới IdP với `SAMLRequest` và trạng thái giao dịch; IdP xác thực rồi gửi một form HTML POST về ACS. Thông điệp đến SP về mặt cấu trúc:

~~~http
POST /login/saml2/sso/corporate HTTP/1.1
Host: sp.example.org
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...

SAMLResponse=<BASE64_ENCODED_SAML_XML>&RelayState=<TRANSACTION_STATE>
~~~

Dữ liệu trên **chỉ để minh họa tên trường/form**; các giá trị trong dấu `<...>` không phải phản hồi có thể dùng để đăng nhập. Khi sử dụng **HTTP-POST binding**, `SAMLResponse` là XML SAML được mã hóa Base64 theo binding; **Base64 không mã hóa bảo mật và cũng không bảo đảm chữ ký**. Một phản hồi thật còn chịu quy tắc profile về XML, chữ ký, issuer, thời hạn và các trường tương quan. Đừng gửi nội dung `SAMLResponse`, cookie phiên, NameID hoặc assertion chứa dữ liệu cá nhân vào công cụ debug công khai.

Trường `RelayState` có thể đi cùng phản hồi nhưng **không phải credential**. SP phải đối chiếu `RelayState` với trạng thái giao dịch đã bảo vệ và `InResponseTo` với yêu cầu đang chờ. Với ứng dụng có nhiều IdP, `registrationId` trong URL là một **gợi ý định tuyến có kiểm soát**, chưa đủ để tin tưởng XML nhận vào.

## 3. Filter có trách nhiệm gì và không có trách nhiệm gì?

`Saml2WebSsoAuthenticationFilter` kế thừa `AbstractAuthenticationProcessingFilter`. Nhờ đó nó tham gia cơ chế Spring Security Servlet: nhận biết request xác thực, gọi xử lý xác thực, xử lý thành công/thất bại và tích hợp `SecurityContext`.

| Hành động | Thành phần chịu trách nhiệm điển hình |
| --- | --- |
| Request có khớp **ACS login processing URL** không? | Request matcher của **`Saml2WebSsoAuthenticationFilter`**. |
| Đọc các tham số HTTP `SAMLResponse`, tìm registration phù hợp? | `Saml2AuthenticationTokenConverter` được filter sử dụng. |
| Tìm `AuthnRequest` đã lưu để biết transaction ban đầu? | `Saml2AuthenticationRequestRepository`, kết hợp converter/filter. |
| Đóng gói thông tin cần xác minh vào `Saml2AuthenticationToken`? | Authentication converter. |
| Quyết định assertion có hợp lệ về chữ ký, issuer, audience, thời hạn, chủ thể? | `OpenSamlXAuthenticationProvider` và các validator tương ứng. |
| Tạo kết quả `Authentication` đã xác thực? | Authentication provider. |
| Gắn trạng thái xác thực vào ứng dụng và chuyển trang theo chính sách? | `AbstractAuthenticationProcessingFilter` và các chiến lược/session/success handler Spring Security. |
| Quyết định người dùng có quyền xem báo cáo thuộc tenant khác không? | **Authorization** của ứng dụng, độc lập với SAML login. |

**Filter không tự tuyên bố XML hợp lệ chỉ vì HTTP POST thành công.** Không viết một `@PostMapping("/login/saml2/sso/...")` tự `Base64.decode` rồi tạo session trực tiếp; cách đó bỏ qua xác minh signature, assertion conditions và quản lý giao dịch.

## 4. Bước 1 — nhận callback tại ACS

### 4.1. Matcher và HTTP-POST binding

Với cấu hình SAML 2.0 login thông thường, IdP trả `Response` theo **HTTP-POST binding** đến ACS. Spring Security dùng login-processing endpoint như:

~~~text
https://sp.example.org/login/saml2/sso/corporate
~~~

Trong đó `corporate` là **registrationId** của cặp SP/IdP được cấu hình ở ứng dụng. Endpoint public phải khớp `AssertionConsumerService.Location` đã đăng ký tại IdP và URL mà runtime đang thực sự xử lý.

Nếu IdP POST đến `/auth/saml/acs` nhưng filter chỉ nhận `/login/saml2/sso/{registrationId}`, request có thể rơi qua filter và nhận 404, 403 hoặc một xử lý khác tùy chain. Chữa đúng bằng cách cấu hình **login processing URL, ACS Location/metadata và IdP registration** cho trùng khớp.

### 4.2. CSRF token và callback liên site

Với SAML HTTP-POST binding, IdP là bên gửi form; nó không có CSRF token do SP tạo cho những form thông thường. Spring Security `saml2Login` cấu hình ngoại lệ CSRF **cho đúng Web SSO processing endpoint** để nhận POST. Đây là ngoại lệ có phạm vi hẹp; **không tắt CSRF cho toàn ứng dụng**.

An toàn của callback vẫn phải dựa vào **chữ ký SAML + điều kiện assertion + giao dịch `AuthnRequest`/phiên + chống replay**. Vấn đề cookie `SameSite` đặc biệt quan trọng vì IdP → SP có thể là cross-site POST: nếu cookie chứa session không được trình duyệt gửi đến ACS, Spring Security sẽ không tìm được `AuthnRequest` gốc. Cần cấu hình session/cookie đúng bối cảnh và kiểm thử trình duyệt thật; **không bỏ kiểm tra `InResponseTo` để tránh lỗi login**.

### 4.3. Điều kiện đầu vào

Theo binding/profile, callback phải có một `SAMLResponse` với nội dung hợp lệ và registration xác định được. Nếu thiếu trường, Base64 sai, XML không hợp lệ, thiếu dữ liệu giao dịch hoặc không tìm được registration, đường xác thực phải **thất bại an toàn**. Đừng xây fallback “bất kỳ XML nào có NameID thì đăng nhập được”.

## 5. Bước 2 — Saml2AuthenticationTokenConverter tạo Authentication request

Spring Security sử dụng **`Saml2AuthenticationTokenConverter`** để biến dữ liệu HTTP thành **`Saml2AuthenticationToken`**. Token ở giai đoạn này là **yêu cầu xác thực chưa được tin cậy**, không phải một `Saml2Authentication` đã đăng nhập.

Về mặt khái niệm, converter thực hiện:

1. Trích `SAMLResponse` từ request và xử lý theo binding được hỗ trợ.
2. Tìm **`RelyingPartyRegistration`** tương ứng: quan hệ cấu hình giữa SP entityID, IdP entityID, ACS và các khóa xác minh.
3. Nạp ngữ cảnh `AuthnRequest` có liên quan từ `Saml2AuthenticationRequestRepository` nếu luồng được SP khởi tạo.
4. Tạo `Saml2AuthenticationToken` chứa thông điệp SAML và cấu hình đối tác cần cho provider xác minh.

**RelyingPartyRegistration không được lấy từ XML chưa xác thực làm nguồn cấu hình tin cậy mới.** Với nhiều IdP, converter có thể dùng thông tin request đang chờ, `registrationId` trong URL, và ở các phiên bản hỗ trợ, issuer trong Response để *tìm một registration đã cấu hình*. Việc tìm kiếm này **không đồng nghĩa tin issuer tự khai**; authentication provider phải tiếp tục kiểm tra issuer và chữ ký theo khóa của registration đó.

### 5.1. Định danh registration và endpoint

Ví dụ:

~~~text
registrationId: corporate
SP entityID:    urn:example:sp:portal
IdP entityID:   urn:example:idp:corporate
SP ACS:         https://sp.example.org/login/saml2/sso/corporate
IdP SSO:        https://idp.example.org/saml/sso
~~~

`corporate` chỉ là **khóa cấu hình nội bộ** của Spring Security, không phải SAML NameID và không nhất thiết phải bằng SP/IdP entityID. Nếu ứng dụng hỗ trợ hai tenant có hai IdP khác nhau, lựa chọn registration phải xuất phát từ chính sách/trạng thái giao dịch, rồi xác minh đúng trust anchor của IdP.

### 5.2. Mối liên hệ với AuthnRequestRepository

Ở chặng bắt đầu SSO, `Saml2WebSsoAuthenticationRequestFilter` lưu một `AbstractSaml2AuthenticationRequest` vào `Saml2AuthenticationRequestRepository`. Mặc định trong các cấu hình Spring Security thông dụng là `HttpSessionSaml2AuthenticationRequestRepository`: yêu cầu đang chờ gắn với `HttpSession`.

Khi ACS nhận SAML Response, filter/converter sử dụng repository để lấy request đã lưu, đối chiếu `InResponseTo` và thông tin giao dịch theo provider/validator. Nếu response thuộc một browser session khác, đã hết hạn, đã dùng hoặc request không còn, không được tự suy ra một giao dịch mới từ `RelayState`. **IdP-initiated/unsolicited SSO** (không có AuthnRequest trước) là lựa chọn tích hợp có chính sách riêng; không phải fallback tùy tiện khi SP-initiated login bị lỗi.

Nếu triển khai nhiều instance Spring Boot, cần session store chung hoặc routing phù hợp: callback đến instance khác mà không có trạng thái giao dịch có thể bị từ chối. Không đánh đổi correlation chỉ để che một lỗi sticky-session.

## 6. Bước 3 — AuthenticationManager chuyển token cho OpenSAML provider

Sau converter, `Saml2WebSsoAuthenticationFilter` gọi `AuthenticationManager#authenticate(...)` với `Saml2AuthenticationToken`. Thông thường một `ProviderManager` sẽ chọn provider có thể xử lý loại token này.

**Khác biệt phiên bản:** ứng dụng Spring Boot 3.3 / Spring Security 6.3 thường dùng **`OpenSaml4AuthenticationProvider`**; các đời Spring Security mới hơn dùng **`OpenSaml5AuthenticationProvider`**. Hãy kiểm tra dependency thực tế trước khi import class hoặc viết custom validator. Cả hai đều mang vai trò: xác thực SAML dựa trên registration đã tin cậy; API cấu hình chi tiết không đồng nhất giữa hai đời.

### 6.1. Provider phải xác minh những gì?

Tại thời điểm nhận callback, thông điệp/khẳng định danh tính từ trình duyệt **chưa đáng tin**. Những nhóm kiểm tra quan trọng gồm:

| Nhóm kiểm tra | Ý nghĩa | Ví dụ lỗi bị từ chối |
| --- | --- | --- |
| Parse và cấu trúc XML | Thông điệp là SAML Response/Assertion đúng định dạng và profile hỗ trợ; parser chống XXE. | XML lỗi, phần tử bất thường, format không hợp lệ. |
| Chữ ký và chứng thư đáng tin | Xác minh chữ ký ở **đúng phần tử được sử dụng** với khóa đã đăng ký của IdP; tránh XML signature wrapping. | Chữ ký sai hoặc ký bằng khóa ngoài trust store. |
| `Response@Status` | IdP báo thành công hay thất bại; chỉ status thích hợp mới tạo phiên. | `Responder`, `AuthnFailed` hoặc trạng thái không thành công. |
| `Issuer` | Đúng IdP đã cấu hình. | Assertion đến từ issuer khác registration. |
| `Destination` | Response hướng đến **ACS URL** tương ứng. | Response dành URL khác. |
| `AudienceRestriction` | Assertion được phép dùng bởi **SP entityID** hiện tại. | Token dành cho SP khác. |
| `Conditions@NotBefore/NotOnOrAfter` | Assertion còn trong khoảng hiệu lực. | Quá hạn, hoặc chưa đến lúc hiệu lực. |
| `SubjectConfirmationData` | Bearer confirmation đúng `Recipient`, `InResponseTo`, thời hạn. | Recipient khác ACS, confirmation hết hạn. |
| Tương quan giao dịch | `InResponseTo` trỏ đến AuthnRequest đang chờ của phiên khởi tạo. | Login CSRF hoặc response từ giao dịch khác. |
| Replay và giới hạn dùng lại | Ngăn chấp nhận assertion/response cũ nhiều lần theo profile/cấu hình. | Replay assertion đã tiêu thụ. |
| Giải mã (nếu được cấu hình) | Decrypt `EncryptedAssertion`/`EncryptedAttribute` bằng khóa riêng SP thích hợp. | Thiếu private key hoặc decrypt lỗi. |

**Không một kiểm tra đơn lẻ thay thế các kiểm tra khác:** chữ ký đúng không đồng nghĩa audience đúng; ACS đúng không đồng nghĩa assertion còn hạn; có `NameID` không đồng nghĩa người đó có quyền truy cập bất kỳ tài nguyên nào.

Trong SAML, `NotOnOrAfter` là biên thời gian **loại trừ**. `SubjectConfirmationData@NotOnOrAfter` có thể hết hạn sớm hơn `Conditions@NotOnOrAfter`; nếu confirmation hết hạn thì không được chấp nhận chỉ vì Conditions còn hạn. Dung sai clock skew chỉ nên nhỏ và có cấu hình, đồng thời phải đồng bộ đồng hồ IdP/SP.

### 6.2. Response chứa gì?

SAML Response trả về ACS thường có dạng cấu trúc (đây **không phải** XML hoàn chỉnh/có chữ ký):

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-42"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://sp.example.org/login/saml2/sso/corporate"
    InResponseTo="_request-17">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assertion-22" Version="2.0"
                  IssueInstant="2026-11-07T03:00:00Z">
    <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
    <!-- Subject, SubjectConfirmation, Conditions, chữ ký,
         AuthnStatement, AttributeStatement ... -->
  </saml:Assertion>
</samlp:Response>
~~~

XML rút gọn trên chỉ giúp nhìn thấy chỗ chứa `Response` và `Assertion`. Nó **không thể xác thực** vì thiếu chữ ký, các điều kiện bắt buộc theo profile và dữ liệu chứng minh chủ thể. Trong thực tế, IdP có thể ký Response, Assertion hoặc cả hai theo cấu hình/profile; provider phải xác minh **đúng phần tử và nội dung được dùng**, không mặc nhiên coi toàn bộ tài liệu an toàn vì có một thẻ `Signature` ở đâu đó.

**Tên trường HTTP `SAMLResponse` khác với tên phần tử XML `<samlp:Response>`.** Filter tiếp nhận trường form rồi thông qua converter/provider xử lý XML; không trực tiếp cho ứng dụng truy cập một assertion đã tin cậy trước khi hoàn tất xác thực.

## 7. Bước 4 — tạo Saml2Authentication và phiên ứng dụng

Khi provider chấp nhận Response, nó tạo **`Saml2Authentication`** (một `Authentication` đã xác thực). Đối tượng kết quả thường chứa:

- **Principal** kiểu `Saml2AuthenticatedPrincipal`, mang tên định danh và các attribute đã được xử lý.
- **`name`/NameID** của người dùng theo chính sách ánh xạ; NameID có thể không phải email và có thể thay đổi tùy định dạng/IdP.
- **GrantedAuthorities**. Với provider mặc định trong các phiên bản phổ biến, thường có `ROLE_USER`; **group/role trong SAML AttributeStatement không tự biến thành quyền nghiệp vụ**.
- Thông tin SAML Response qua API tương ứng; dữ liệu này có thể nhạy cảm và không nên xuất/log nguyên bản.

Filter và framework tiếp tục thực hiện logic thành công: cập nhật `SecurityContext`, lưu trạng thái xác thực theo `SecurityContextRepository`/session strategy đã cấu hình, rồi gọi success handler hoặc tiếp tục chain tùy cấu hình. Người dùng có thể được chuyển về trang trước login (saved request). **Một Assertion hết hạn sau vài phút không tự buộc cookie phiên SP hết hạn ngay lúc đó**: thời hạn session/logout của SP là chính sách riêng.

### 7.1. Lấy principal trong controller Spring MVC

Tệp `src/main/java/example/federation/CurrentUserController.java` trong ứng dụng Spring Boot đã cấu hình SAML login:

~~~java
package example.federation;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return Map.of("principalName", principal.getName());
    }
}
~~~

`/me` phải được bảo vệ bởi authorization (ví dụ `.anyRequest().authenticated()`). Ví dụ trên chỉ trả **principal name của chính người dùng đang đăng nhập**; không xuất toàn bộ SAML attributes hoặc response trong API. Mã Java thuộc dự án Spring Boot có dependency tương ứng, **không thể `javac` độc lập chỉ với JDK**.

Trong service, cần ánh xạ định danh **ổn định, đúng issuer/tenant** tới tài khoản nội bộ và kiểm tra trạng thái active, role, quyền trên tài nguyên. Không dùng email hoặc tên hiển thị làm khóa duy nhất nếu có thể đổi/tái sử dụng. Một người có SAML login thành công vẫn có thể nhận 403 vì thiếu quyền tài nguyên.

## 8. Thiết lập Spring Boot và Spring Security

Ví dụ đơn giản cho ứng dụng **Servlet** sử dụng Java 17+ và Spring Boot/Spring Security tương thích. Các thư viện cốt lõi:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Đây là **đoạn dependencies của `build.gradle`** trong dự án đã cấu hình quản lý phiên bản Spring và kho thư viện cần thiết (OpenSAML có thể yêu cầu repository phù hợp). Không xem nó như build file độc lập.

Cấu hình `src/main/resources/application.yml` dùng **IdP metadata giả định** để xác định một registration:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
~~~

URL trên chỉ minh họa. Muốn chạy thật cần IdP metadata hợp lệ, ký/verification credentials đã thiết lập tin cậy, public base URL đúng và registration tương ứng; nếu IdP yêu cầu `AuthnRequest` có chữ ký thì SP phải có signing key/certificate phù hợp.

Cấu hình filter chain tại `src/main/java/example/federation/SecurityConfig.java`:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Khi các điều kiện tích hợp đã hoàn chỉnh, Spring Security đăng ký các thành phần yêu cầu/nhận SAML mà không cần viết thủ công `Saml2WebSsoAuthenticationFilter` bean. `Saml2WebSsoAuthenticationFilter` xử lý callback ACS, còn `Saml2WebSsoAuthenticationRequestFilter` phụ trách gửi AuthnRequest.

**Không gọi endpoint mẫu bằng `curl` với Base64 tùy ý để “test đăng nhập thành công”**: một SAMLResponse hợp lệ phải có chữ ký/issuer/conditions phù hợp và quan hệ tin cậy đã thiết lập. Kiểm thử thực tế cần IdP test hoặc SAML test fixture có chữ ký và correlation đúng.

### 8.1. Khi cần thay đổi ACS processing URL

Giả sử ứng dụng muốn IdP POST SAML Response tới `/saml/acs/corporate`. Cần thực hiện đồng bộ:

1. Cấu hình `saml2Login(...loginProcessingUrl(...))` cho **filter matcher** tiếp nhận đường dẫn.
2. Cấu hình `RelyingPartyRegistration.assertionConsumerServiceLocation` hoặc property/metadata SP tương ứng.
3. Cập nhật **ACS URL phía IdP** để đúng với public URL mới.
4. Nếu bỏ `{registrationId}` trong URL, đảm bảo converter/resolver vẫn tìm **đúng** registration; đừng để bất kỳ issuer nào từ request tự quyết định tin cậy.
5. Kiểm thử ACS URL trong metadata được sinh ra, `Response@Destination`, `SubjectConfirmationData@Recipient` và flow SP-initiated tương quan.

Ví dụ riêng DSL khi đã cấu hình registration/ACS tương ứng:

~~~java
.saml2Login(saml2 -> saml2
    .loginProcessingUrl("/saml/acs/corporate"))
~~~

Đây là **đoạn chain minh họa, không phải class Java độc lập**. Khi cấu hình custom URL, lưu ý API `Saml2AuthenticationTokenConverter` của một số phiên bản giả định có `{registrationId}` trong đường dẫn: cần bảo đảm lookup/resolver có quy tắc đáng tin cậy. Không chỉ đổi một phía vì `Destination`/`Recipient` và ACS Location sẽ không trùng.

## 9. Tùy biến đúng lớp, giữ validator mặc định

SAML login thường cần map thông tin IdP sang tài khoản và role trong ứng dụng, hoặc điều chỉnh hành vi khi login thất bại. Nên chọn **điểm mở rộng đúng trách nhiệm**:

| Nhu cầu | Điểm mở rộng thích hợp | Điều cần giữ |
| --- | --- | --- |
| Thay đổi cách chọn IdP/registration | `RelyingPartyRegistrationResolver` hoặc `AuthenticationConverter` phù hợp phiên bản. | Chỉ dùng registration được cấu hình tin cậy; chống IdP mix-up. |
| Thay đổi kho lưu `AuthnRequest` | `Saml2AuthenticationRequestRepository`. | Gắn transaction vào browser session, TTL, dùng một lần. |
| Điều chỉnh clock skew, issuer/conditions validation | Validator của OpenSAML provider phù hợp phiên bản. | Gọi/giữ validator mặc định và nới thời gian tối thiểu. |
| Giải mã encrypted assertion/attribute | Credentials/Decrypter của provider. | Dùng khóa riêng SP, không lộ plaintext ra log. |
| Map NameID/attributes thành principal và authorities | Response authentication converter hoặc lớp map người dùng sau xác thực. | Chỉ map từ assertion đã được xác minh; áp dụng đúng tenant/quyền. |
| Chuyển hướng sau login hoặc báo lỗi thân thiện | Authentication success/failure handler. | Không bộc lộ assertion/token trong URL hoặc message. |
| Quyền theo resource, tenant, row | `authorizeHttpRequests`, method security, business authorization service. | SAML login chỉ xác thực danh tính, không thay kiểm tra quyền nghiệp vụ. |

**Không thay toàn bộ `AuthenticationManager` bằng hàm `NameID != null` hoặc decoder XML thủ công.** Một custom manager phải tái hiện đủ kiểm tra SAML, điều rất dễ sai. Trong trường hợp chỉ cần bổ sung một bước mapping/validation, ưu tiên mở rộng provider chính thức, **ủy quyền cho logic xác minh có sẵn** rồi áp dụng điều kiện của ứng dụng.

### 9.1. Khác biệt giữa OpenSaml4 và OpenSaml5

Trong Spring Security 6.3, tài liệu tích hợp thường nhắc `OpenSaml4AuthenticationProvider`, với các cách đặt converter/validator tương ứng. Trong Spring Security 7.x, tài liệu mới dùng `OpenSaml5AuthenticationProvider` và API kiểm tra/khai báo một phần khác. Vì thế không copy một đoạn tùy biến `OpenSaml5AuthenticationProvider` vào dự án 6.3 rồi giả định biên dịch được; hãy xác nhận phiên bản dependency và sử dụng API/validator chính xác. **Cơ chế filter → converter → manager → provider → Authentication là nguyên lý ổn định**.

## 10. Thành công, thất bại và kết quả HTTP

### 10.1. Đăng nhập thành công

Điều kiện chung: request tới đúng ACS, tìm được registration đáng tin, SAMLResponse hợp lệ theo profile, transaction/phiên tương quan đúng, provider trả về `Saml2Authentication`. Khi đó framework thiết lập authentication context và success handler. Người dùng thường được đưa trở lại URL ban đầu. Một callback POST **không phải REST endpoint “trả JSON chứa JWT”** trừ khi ứng dụng đã cố ý thiết kế thêm một tầng riêng sau xác thực.

### 10.2. Đăng nhập thất bại

Ví dụ nguyên nhân: SAMLResponse trống/hỏng, issuer khác, chữ ký sai, response status không thành công, audience/recipient/destination sai, assertion hết hạn, thiếu session chứa request gốc, `InResponseTo` không khớp, hoặc IdP metadata không còn tin cậy.

Khi authentication provider ném `AuthenticationException`, filter thực thi failure path: xóa/ngăn duy trì authentication không hợp lệ theo cấu hình và kích hoạt failure handler/entry point để thông báo hoặc khởi tạo lại đăng nhập. **Không gán mọi lỗi SAML thành 401, 403 hay 500 cố định**; mã HTTP và trang redirect phụ thuộc chiến lược failure được cấu hình.

### 10.3. Nếu filter không xử lý request

Một request không khớp ACS matcher sẽ đi qua các filter khác. Nó có thể gặp authorization filter, controller, 404, 405 hoặc CSRF tùy routing. Vì thế POST trả 403 không luôn chứng minh chữ ký SAML lỗi; có thể request **chưa từng tới filter SAML**. Muốn chẩn đoán, trước hết kiểm tra URL, phương thức, filter chain đang chọn và quy tắc CSRF.

## 11. Bảng kiểm vận hành và chẩn đoán

| Dấu hiệu | Khả năng liên quan | Hướng xử lý an toàn |
| --- | --- | --- |
| IdP báo ACS URL không được phép. | Metadata SP/IdP registration sai URL. | So sánh `AssertionConsumerService.Location` và callback public. |
| Trình duyệt POST `SAMLResponse` nhưng ứng dụng trả 404. | Không có filter/handler nhận đúng path hoặc sai context path. | Kiểm tra `saml2Login`, ACS matcher, proxy và servlet context. |
| POST bị 403 trước SAML validation. | CSRF/matcher/filter chain khác yêu cầu. | Xem chain và ngoại lệ CSRF chỉ tại ACS. |
| Không tìm được relying party registration. | `registrationId` sai, repository trống, converter lookup không phù hợp. | Kiểm tra registration được cấu hình, đường dẫn ACS, resolver. |
| `InResponseTo` không khớp hoặc thiếu AuthnRequest. | Cookie/session mất, nhiều tab, relay state không khớp, callback của phiên khác. | Kiểm tra correlation store, SameSite, TTL, session chung nhiều instance. |
| Chữ ký verification thất bại. | Sai IdP certificate/metadata, key rotation, ký sai phần tử. | Kiểm tra trust anchor, signature được validate đúng object. |
| Destination hoặc Recipient mismatch. | IdP POST về host/scheme khác ACS khai báo. | Kiểm tra URL HTTPS public, proxy forwarded headers, ACS metadata. |
| AudienceRestriction mismatch. | IdP cấp assertion cho SP entityID khác. | So SP entityID đã cấu hình với audience assertion. |
| Assertion expired hoặc not yet valid. | Chênh đồng hồ, TTL quá ngắn, callback chậm. | NTP/UTC, thời hạn, clock skew hợp lý; không nới vô hạn. |
| Login thành công nhưng user không có role nghiệp vụ. | Mặc định chỉ có ROLE_USER; chưa ánh xạ group/attribute. | Cấu hình mapping được xác minh và kiểm tra role/tenant tại service. |
| Login thành công rồi quay lại login. | SecurityContext/session cookie không được duy trì, cookie policy hoặc session repository sai. | Kiểm tra success handler, Secure/SameSite, session fixation, session store. |
| IdP có hai tenant nhưng user vào tenant sai. | Chọn nhầm registration hoặc cấu hình định danh không tách tenant. | Ràng buộc issuer/registration/tenant với transaction và user mapping. |
| Debug cho thấy NameID nhưng filter vẫn fail. | NameID không đủ để xác thực SAML. | Kiểm tra status, signature, issuer, subject confirmation, audience và replay. |

**Thứ tự debug thực tế:** 1) URL/method có vào filter không → 2) converter tìm đúng registration/request gốc không → 3) provider từ chối ở bước nào → 4) success handler/session được lưu không → 5) authorization nghiệp vụ có cho phép không. Ghi log **loại lỗi, mã đăng ký IdP đã cấu hình, transaction/correlation ID đã bảo vệ và thời gian UTC**; tránh log SAMLResponse thô, XML chứa PII, cookie, private key hoặc assertion giải mã.

## 12. Các tình huống kiểm thử cần có

| Test case | Kết quả mong đợi |
| --- | --- |
| SP-initiated login, SAMLResponse ký hợp lệ, ACS đúng, InResponseTo đúng. | Authentication thành công, principal hợp lệ, phiên ứng dụng được tạo theo cấu hình. |
| POST tới ACS với `SAMLResponse` thiếu hoặc Base64 lỗi. | Không tạo authentication. |
| Chữ ký assertion sai hoặc signing key không tin cậy. | Từ chối. |
| Issuer từ IdP chưa được đăng ký. | Từ chối; không tạo registration từ request. |
| Audience dành cho SP khác. | Từ chối. |
| Destination/Recipient không đúng ACS công bố. | Từ chối. |
| `Conditions@NotOnOrAfter` đã qua hoặc `SubjectConfirmationData` hết hạn. | Từ chối theo clock skew có kiểm soát. |
| Response chứa `InResponseTo` của browser session khác. | Từ chối login CSRF/session swapping. |
| Replay lại response/transaction sau khi thành công. | Từ chối theo cơ chế replay/correlation của hệ thống. |
| Callback đi đến node khác nhưng không có shared session. | Không tự chấp nhận; chẩn đoán session store. |
| Dữ liệu SAML hợp lệ nhưng tài khoản ứng dụng bị disable. | Không cấp quyền ứng dụng theo chính sách vòng đời. |
| Đăng nhập thành công nhưng truy cập tài nguyên tenant khác. | Từ chối tại authorization, không phụ thuộc việc login SAML hợp lệ. |

Các bài test đầu-cuối nên dùng **IdP kiểm thử hoặc bộ fixture được ký hợp lệ** và môi trường đã cấu hình khóa tin cậy. Một unit test chỉ decode XML hay giả lập `NameID` không đủ chứng minh toàn bộ chuỗi xác thực hoạt động an toàn.

## 13. Những nhầm lẫn cần tránh

1. **“Filter trực tiếp xác minh mọi chữ ký SAML.”** Filter điều phối; `AuthenticationManager`/OpenSAML provider xác minh thông điệp.
2. **“IdP POST được đến ACS nghĩa là user đã đăng nhập.”** HTTP POST chỉ là đầu vào chưa tin; phải qua tất cả validator.
3. **“`SAMLResponse` Base64 là dữ liệu đã mã hóa an toàn.”** Base64 là encoding, không có tính bảo mật/chống sửa đổi.
4. **“ACS URL, IdP SSO URL và metadata URL là một.”** ACS nhận response, SSO nhận AuthnRequest, metadata URL trả XML cấu hình.
5. **“Chỉ cần NameID thì tạo tài khoản/role admin.”** NameID trong XML chưa được kiểm chứng không đáng tin; authorization phải theo chính sách riêng.
6. **“`registrationId` trong URL chứng minh XML thuộc IdP đó.”** Nó định tuyến tới registration; issuer/chữ ký phải được xác minh riêng.
7. **“Thất bại InResponseTo thì cho chuyển sang IdP-initiated.”** Không hạ cấp chính sách nếu không được phê duyệt rõ.
8. **“Bỏ CSRF toàn bộ ứng dụng để nhận POST SAML.”** Chỉ ACS có ngoại lệ thích hợp; các route khác vẫn cần CSRF theo chính sách.
9. **“Thay ACS mà không sửa metadata cũng được.”** ACS runtime, metadata SP và cấu hình IdP phải nhất quán.
10. **“Assertion còn hạn thì có thể dùng nhiều lần.”** Cần chống replay và transaction correlation; session SP có vòng đời riêng.
11. **“Đã có `ROLE_USER` nghĩa là mọi permission được cấp.”** Quyền quản trị/tenant/resource phải ánh xạ và kiểm tra có chủ đích.
12. **“Sao chép code provider của Spring Security mới vào version cũ sẽ chạy.”** Tên class và extension API thay đổi, cần bám đúng phiên bản.

## 14. Tóm tắt và câu hỏi tự kiểm

**Tóm tắt luồng ở đúng cấp abstraction:**

~~~text
HTTP POST /login/saml2/sso/{registrationId}
        |
Saml2WebSsoAuthenticationFilter
        |
Saml2AuthenticationTokenConverter
        | lấy SAMLResponse, tìm RelyingPartyRegistration
        | khôi phục giao dịch AuthnRequest khi có
Saml2AuthenticationToken (chưa xác thực)
        |
AuthenticationManager
        |
OpenSaml4 / OpenSaml5 AuthenticationProvider
        | signature, issuer, audience, ACS, conditions,
        | subject confirmation, InResponseTo, replay
Saml2Authentication (đã xác thực)
        |
SecurityContext + session/success handler
        |
Authorization nghiệp vụ cho request tiếp theo
~~~

**Tự kiểm:**

- **Filter nào tạo `AuthnRequest`?** `Saml2WebSsoAuthenticationRequestFilter`.
- **Filter nào nhận `SAMLResponse` tại ACS?** **`Saml2WebSsoAuthenticationFilter`**.
- **Ai chuyển HTTP request thành authentication request token?** `Saml2AuthenticationTokenConverter`.
- **Ai kiểm tra SAML Response/assertion?** `AuthenticationManager` gọi `OpenSamlXAuthenticationProvider` và các validator.
- **Tại sao phải giữ `AuthnRequest` trong session?** Để liên kết response với giao dịch do đúng trình duyệt khởi tạo.
- **Vì sao callback có chữ ký hợp lệ vẫn có thể thất bại?** Destination, recipient, audience, thời hạn hoặc `InResponseTo` có thể sai.
- **SAML login thành công có tự cấp quyền admin không?** Không. Phải map quyền và kiểm tra authorization riêng.

## Tài liệu tham khảo

- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Producing AuthnRequests và request repository](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html)
- [Spring Security API — Saml2WebSsoAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/Saml2WebSsoAuthenticationFilter.html)
- [Spring Security API — Saml2AuthenticationTokenConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationTokenConverter.html)
- [Spring Security 6.3.4 API — OpenSaml4AuthenticationProvider](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html)
- [OASIS SAML V2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML V2.0 Profiles — Web Browser SSO](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
