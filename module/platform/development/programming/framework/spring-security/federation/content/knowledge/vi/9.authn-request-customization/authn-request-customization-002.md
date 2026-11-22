# Điều chỉnh địa chỉ bắt đầu đăng nhập và Assertion Consumer Service trong Spring Security SAML2

**Địa chỉ bắt đầu đăng nhập** và **Assertion Consumer Service (ACS)** là hai endpoint ở phía Service Provider (SP), nhưng đảm nhận hai nửa khác nhau của SAML 2.0 Web Browser SSO. Một endpoint **tạo AuthnRequest để chuyển người dùng sang Identity Provider (IdP)**; endpoint còn lại **nhận SAMLResponse từ IdP qua trình duyệt để kiểm chứng và tạo Authentication**. Thay đổi đường dẫn phải làm đúng ở Spring Security, thông tin `RelyingPartyRegistration`, SP metadata và cấu hình IdP.

Bài học thuộc nhóm **Tùy chỉnh AuthnRequest** của Spring Security federation. Nội dung giải thích cách xác định endpoint mặc định, tùy chỉnh cả hai endpoint bằng DSL, ràng buộc ACS với SAML protocol, thử nghiệm trong môi trường proxy và xử lý lỗi. Các địa chỉ với miền `.example` chỉ là ví dụ, không phải máy chủ thật.

## 1. Nhìn đúng vai trò từng địa chỉ

Giả sử Portal A tại `https://portal.example.com` tin IdP đối tác B, có `registrationId = partner-b`.

| Thành phần | Địa chỉ minh họa | Bên xử lý và ý nghĩa |
| --- | --- | --- |
| **SP start/login initiation** | `https://portal.example.com/saml2/authenticate/partner-b` | SP: nhận lệnh bắt đầu SSO, tạo AuthnRequest |
| **IdP SingleSignOnService** | `https://login.partner-b.example/sso` | IdP: nhận AuthnRequest từ SP |
| **SP Assertion Consumer Service** | `https://portal.example.com/login/saml2/sso/partner-b` | SP: nhận SAMLResponse, xác minh danh tính |
| **SP metadata HTTP endpoint** | `https://portal.example.com/saml2/metadata/partner-b` | Cung cấp XML mô tả SP cho quản trị IdP |
| **SP Entity ID** | `https://portal.example.com/sp/partner-b` | Định danh SAML của SP; IdP dùng để giới hạn audience |

Đây là **năm địa chỉ/định danh khác nhiệm vụ**. SP Entity ID là chuỗi định danh giao thức, không nhất thiết là endpoint HTTP. IdP SSO URL là nơi SP gửi AuthnRequest, **không** phải URL browser gửi SAMLResponse về. SP metadata GET không phải ACS POST.

**Spring Security sử dụng hai filter chính:**

- `Saml2WebSsoAuthenticationRequestFilter`: sinh, lưu và phát SAML AuthnRequest ở endpoint bắt đầu.
- `Saml2WebSsoAuthenticationFilter`: nhận SAMLResponse ở ACS, tạo `Saml2AuthenticationToken` thông qua converter, chuyển cho authentication provider để xác minh.

`registrationId` là khóa tìm cấu hình **cặp SP–IdP** trong `RelyingPartyRegistrationRepository`; nó không phải email, issuer của IdP hay quyền trên tenant.

## 2. Luồng Web Browser SSO trước khi tùy chỉnh

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Portal A / Spring Security
    participant IdP as Identity Provider B
    U->>SP: GET /private
    SP-->>U: Chuyển tới start URL
    U->>SP: GET /saml2/authenticate/partner-b
    SP->>SP: Tạo AuthnRequest, lưu request ID và state
    SP-->>U: Redirect hoặc form POST tới SSO URL của IdP
    U->>IdP: SAMLRequest + RelayState nếu có
    IdP->>IdP: Xác thực, kiểm thông số SP
    IdP-->>U: HTML form chứa SAMLResponse
    U->>SP: POST /login/saml2/sso/partner-b
    SP->>SP: Xác minh Response/Assertion và quyền
    SP-->>U: Session đã xác thực hoặc lỗi
~~~

**Các route mặc định đáng nhớ trên Spring Security hiện đại:**

~~~text
GET /saml2/authenticate/{registrationId}
GET /saml2/authenticate?registrationId={registrationId}
POST /login/saml2/sso/{registrationId}
POST /login/saml2/sso          (có thể dùng trong một số luồng/resolver)
GET /saml2/metadata/{registrationId}   (khi đã bật metadata)
~~~

Start URL thuộc **SP**, nhưng nó là điểm xuất phát để đưa trình duyệt **đến IdP**, không phải điểm đến của SAMLResponse. IdP thường trả SAMLResponse qua HTTP-POST binding tới ACS; SP có thể gửi AuthnRequest bằng HTTP-Redirect hoặc HTTP-POST binding theo thỏa thuận.

Với SP-initiated SSO, IdP có thể đọc `AssertionConsumerServiceURL` trong AuthnRequest hoặc sử dụng ACS đã đăng ký. Dù theo cách nào, IdP phải gửi Response tới một ACS đã được phép, không phải URL tùy ý mà bên ngoài tự đề xuất.

## 3. Đổi start và đổi ACS là hai thay đổi khác nhau

Mục tiêu sau khi tùy chỉnh:

~~~text
START MỚI:
https://portal.example.com/federation/saml/start/partner-b

ACS MỚI:
https://portal.example.com/federation/saml/acs/partner-b

SP ENTITY ID GIỮ NGUYÊN:
https://portal.example.com/sp/partner-b

IdP SSO URL GIỮ NGUYÊN:
https://login.partner-b.example/sso
~~~

| Cấu hình hoặc tài liệu | Chỉ đổi start | Đổi ACS |
| --- | --- | --- |
| `saml2Login.authenticationRequestUriQuery(...)` | **Đổi** | Không bắt buộc |
| Link trên trang login/redirect entry point | **Đổi** | Thường không bắt buộc |
| `saml2Login.loginProcessingUrl(...)` | Giữ nguyên | **Đổi** |
| `RelyingPartyRegistration.assertionConsumerServiceLocation` | Giữ nguyên | **Đổi** |
| Spring Boot `acs.location` nếu dùng YAML | Giữ nguyên | **Đổi** |
| SAML AuthnRequest ACS field nếu được phát | Giữ nguyên | **Phải phản ánh ACS mới** |
| SP metadata `AssertionConsumerService Location` | Giữ nguyên | **Phải phản ánh ACS mới** |
| ACS/Reply URL đã lưu tại IdP | Giữ nguyên | **Phải đồng bộ với IdP** |
| `RelyingPartyRegistration.entityId` | Giữ nguyên nếu không đổi SP identity | Không tự đổi |
| Phép thử SAML E2E và negative tests | Cần | **Bắt buộc trước triển khai** |

Vì thế, **không đủ** khi chỉ đổi `loginProcessingUrl` mà quên `acs.location` hoặc IdP Reply URL. Khi ấy backend có thể đang đợi POST ở địa chỉ mới nhưng IdP vẫn gửi về đường cũ. Ngược lại, nếu chỉ đổi metadata ACS mà filter vẫn nghe đường cũ, browser POST đúng địa chỉ mới sẽ không được filter xác thực.

## 4. Bước 1: tùy chỉnh endpoint bắt đầu SSO

Theo Spring Security 7.1, `Saml2WebSsoAuthenticationRequestFilter` mặc định nhận `/saml2/authenticate/{registrationId}` và `/saml2/authenticate?registrationId={registrationId}`.

API `Saml2LoginConfigurer.authenticationRequestUriQuery(String)` có từ **Spring Security 6.0**, cho phép cấu hình URI và query parameter của endpoint tạo AuthnRequest. Với path variable:

~~~java
.saml2Login(saml -> saml
    .authenticationRequestUriQuery(
        "/federation/saml/start/{registrationId}"))
~~~

Khi registration là `partner-b`:

~~~text
GET https://portal.example.com/federation/saml/start/partner-b
~~~

Nếu doanh nghiệp yêu cầu query form, có thể cấu hình theo API:

~~~java
.saml2Login(saml -> saml
    .authenticationRequestUriQuery(
        "/federation/saml/start?registrationId={registrationId}"))
~~~

Nếu thay tên tham số khác hoặc tự xây resolver, phải đảm bảo resolver thực sự hiểu và **chỉ chọn registration đã được server cho phép**. Không cho user truyền một IdP metadata URL bất kỳ rồi coi đó là registration hợp lệ.

**Sửa các liên kết khởi động SSO.** Một giao diện cũ có:

~~~html
<a href="/saml2/authenticate/partner-b">Đăng nhập với B</a>
~~~

Sau thay đổi cần:

~~~html
<a href="/federation/saml/start/partner-b">Đăng nhập với B</a>
~~~

Nếu `loginPage("/login")` được cấu hình, hãy kiểm trang đó có hiển thị đúng link/IdP picker. `loginPage` chỉ định **trang lựa chọn đăng nhập**, còn `authenticationRequestUriQuery` đặt **điểm xử lý tạo AuthnRequest**. Thay route mà quên sửa trang login, bookmarks, portal link hoặc redirect entry point sẽ khiến browser tiếp tục gọi đường cũ.

**Không nhầm URL với nội dung request.** Nếu cần `ForceAuthn`, `NameIDPolicy`, `RequestedAuthnContext` hoặc signing algorithm khác, đó là công việc tùy chỉnh `Saml2AuthenticationRequestResolver`/OpenSAML, không phải tác dụng của `authenticationRequestUriQuery`.

## 5. Bước 2: thay ACS mà `Saml2WebSsoAuthenticationFilter` xử lý

Spring Security SAML2 mặc định xử lý SAMLResponse ở `/login/saml2/sso/{registrationId}`. Để dùng đường mới, cấu hình `Saml2LoginConfigurer.loginProcessingUrl(String)`:

~~~java
.saml2Login(saml -> saml
    .loginProcessingUrl(
        "/federation/saml/acs/{registrationId}"))
~~~

IdP phải gửi HTTP POST đến:

~~~text
POST https://portal.example.com/federation/saml/acs/partner-b
Content-Type: application/x-www-form-urlencoded

SAMLResponse=<base64-encoded-saml-response>
~~~

Ví dụ HTTP trên là **hình thức minh họa**, không phải SAMLResponse hợp lệ và không nên đưa token/assertion thật vào log. Khi xử lý, filter tạo authentication request, tìm đúng `RelyingPartyRegistration`, kiểm XML signature/conditions bằng provider và trả session hoặc lỗi.

**Giữ `{registrationId}` trong đường ACS là lựa chọn dễ kiểm soát** nếu có nhiều IdP. Javadoc cảnh báo khi thay `loginProcessingUrl` nên cân nhắc `authenticationConverter(...)`, vì converter mặc định phụ thuộc vào `{registrationId}` trong URL, AuthnRequest đã lưu hoặc issuer của Response để xác định registration. Đổi thành path không chứa ID có thể cần chiến lược tra cứu riêng.

Một ACS chung như `/federation/saml/acs` là khả thi trong một số thiết kế, nhưng phải quyết định rõ cách chọn IdP/registration, kiểm `InResponseTo` và trust boundary. Không chọn một IdP dựa vào email hoặc query parameter do browser tự gửi, cũng không coi issuer khai báo trong XML **chưa xác minh** là nguồn tin cậy.

**Đừng viết controller tự giải mã Base64** rồi tạo session. Đây là điểm tiếp nhận giao thức xác thực, cần bộ xử lý SAML đầy đủ.

## 6. Bước 3: đổi `assertionConsumerServiceLocation` trong registration

`loginProcessingUrl` là điểm lắng nghe HTTP của filter. `RelyingPartyRegistration.assertionConsumerServiceLocation` là **địa chỉ ACS được SP công bố trong giao thức**, bao gồm metadata và AuthnRequest khi thích hợp.

Nếu dùng Spring Boot có property `acs.location`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-b:
            entity-id: "https://portal.example.com/sp/partner-b"
            acs:
              location: "https://portal.example.com/federation/saml/acs/partner-b"
            assertingparty:
              metadata-uri: "classpath:saml/partner-b-idp-metadata.xml"
~~~

File metadata IdP `saml/partner-b-idp-metadata.xml` phải có thật, được xác minh qua kênh tin cậy. Chứng thư, signing credentials, encryption/decryption và mức yêu cầu chữ ký của từng IdP phải cấu hình đúng môi trường. Các property thay đổi giữa một số dòng Spring Boot; **kiểm phiên bản Boot đang dùng** trước khi sao chép.

Giải nghĩa:

- `entity-id` là **SP Entity ID**, không đổi chỉ vì đổi ACS.
- `acs.location` là **URL IdP phải POST Response về**.
- `assertingparty.metadata-uri` là **nguồn IdP metadata** SP dùng, không phải địa chỉ ACS hoặc start endpoint.

Với repository dựng bằng Java, có thể đặt ACS trên builder. **Fragment này cần dự án Spring và metadata thật, không phải chương trình độc lập**:

~~~java
RelyingPartyRegistration partnerB = RelyingPartyRegistrations
    .fromMetadataLocation("classpath:saml/partner-b-idp-metadata.xml")
    .registrationId("partner-b")
    .entityId("https://portal.example.com/sp/partner-b")
    .assertionConsumerServiceLocation(
        "https://portal.example.com/federation/saml/acs/partner-b")
    .build();
~~~

Nên giữ public URL nhất quán, đặc biệt sau reverse proxy. Một số trường URI hỗ trợ placeholders `{baseUrl}`, `{registrationId}`, `{baseScheme}`, `{baseHost}`, `{basePort}`:

~~~text
ACS template:
{baseUrl}/federation/saml/acs/{registrationId}

Nếu baseUrl = https://portal.example.com,
registrationId = partner-b:

ACS =
https://portal.example.com/federation/saml/acs/partner-b
~~~

Khi nhiều proxy hoặc context path, URL public cố định thường dễ kiểm hơn việc để runtime đoán `{baseUrl}` từ headers có thể sai.

## 7. Ví dụ JavaConfig kết hợp start và ACS (Spring Security 6.1+/7.x)

Giả sử project Spring Boot đã chứa `spring-security-saml2-service-provider` và có `RelyingPartyRegistrationRepository` hợp lệ, tạo file `SamlEndpointsSecurityConfiguration.java`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlEndpointsSecurityConfiguration {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationRequestUriQuery(
                    "/federation/saml/start/{registrationId}")
                .loginProcessingUrl(
                    "/federation/saml/acs/{registrationId}"))
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Giới hạn phiên bản của ví dụ:** `authenticationRequestUriQuery` có từ Spring Security 6.0; `saml2Metadata(...)` có từ 6.1. Do đó mã tổng hợp này dành cho Spring Security **6.1+ và 7.x** khi các module được BOM quản lý tương thích. Cần project Spring, OpenSAML, một IdP thật/test, certificates và registration. Không thể chạy riêng file cấu hình bằng `javac`.

Kết quả được mong đợi ở mức **routing**:

~~~text
GET  /federation/saml/start/partner-b
   -> Saml2WebSsoAuthenticationRequestFilter
   -> AuthnRequest gửi tới IdP B

POST /federation/saml/acs/partner-b
   -> Saml2WebSsoAuthenticationFilter
   -> Xác minh SAMLResponse

GET  /saml2/metadata/partner-b
   -> SP metadata được công bố khi đã bật DSL metadata
~~~

Nếu application có nhiều `SecurityFilterChain` dùng `securityMatcher`, cả start và ACS phải nằm trong chain được bật SAML. Một chain khác bắt mất đường dẫn sẽ tạo 404, 302 hoặc 403 dù cấu hình trên nhìn đúng.

**Không đánh dấu hoàn tất chỉ vì compile**: còn phải cập nhật `acs.location`, IdP Reply/ACS URL và thử luồng browser thực.

## 8. AuthnRequest và SAMLResponse phải nhất quán

Một `AuthnRequest` minh họa sau khi đổi ACS:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request-example"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://login.partner-b.example/sso"
    AssertionConsumerServiceURL="https://portal.example.com/federation/saml/acs/partner-b"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>https://portal.example.com/sp/partner-b</saml:Issuer>
</samlp:AuthnRequest>
~~~

Đây là **XML học tập**, chưa có chữ ký hợp lệ, không thể gửi làm thông điệp production. Mỗi trường cho thấy một vai trò:

- `Destination` là **IdP SSO URL**.
- `AssertionConsumerServiceURL` là **SP ACS**; khác start endpoint.
- `Issuer` là **SP Entity ID**.
- `ID` giúp đối chiếu `InResponseTo` khi IdP trả Response.
- `ProtocolBinding` mô tả binding SP muốn nhận Response, trong ví dụ là HTTP-POST.

Không mặc định mọi phiên bản/IdP đều đưa đủ các thuộc tính minh họa vào request. Có hệ thống chỉ sử dụng ACS trong metadata IdP đã đăng ký hoặc dùng ACS index; cần kiểm thực tế.

Khi nhận Response, Spring phải xác minh:

1. **Issuer:** IdP Entity ID khớp registration tin cậy.
2. **Signature:** đúng chứng thư IdP và phần XML có chữ ký hợp lệ.
3. **Audience:** assertion dành cho **SP Entity ID**, không phải start URL.
4. **Destination/Recipient:** thông điệp và subject confirmation hướng tới **ACS hiện tại**.
5. **InResponseTo:** gắn với request SP đã phát theo policy của SP-initiated login.
6. **Conditions/time:** `NotBefore`, `NotOnOrAfter`, clock skew và replay.
7. **Subject/identity mapping:** principal được ánh xạ vào đúng local user.
8. **Authorization:** quyền tenant, object và nghiệp vụ được kiểm riêng.

**Không bỏ validate Destination/Recipient/Audience chỉ để né lỗi đổi URL.** Lỗi đó thường cho thấy hai bên cấu hình không đồng bộ hoặc proxy tạo public URL sai.

## 9. Bước 4: cập nhật SP metadata và cấu hình IdP

Khi bật `saml2Metadata(...)`, tải SP metadata từ đúng public domain:

~~~bash
curl -i "https://portal.example.com/saml2/metadata/partner-b"
~~~

Trong XML, hãy kiểm `EntityDescriptor/@entityID`, `AssertionConsumerService/@Location`, binding và certificate, ví dụ fragment minh họa:

~~~xml
<md:AssertionConsumerService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    Location="https://portal.example.com/federation/saml/acs/partner-b"
    index="1" />
~~~

Ở IdP, đội quản trị có thể gọi trường này là **ACS URL**, **Reply URL**, **Assertion Consumer URL** hoặc endpoint nhận assertion. Cần đăng ký URL mới đúng scheme, host, path, port, trailing slash và binding.

**Không đổi SP Entity ID nếu không thực sự định thay SP identity.** Một thay đổi Entity ID có thể buộc IdP cập nhật audience, làm hỏng các trust contract còn lại. Khi chỉ chuyển ACS, hãy giữ Entity ID/certificate ổn định nếu chính sách cho phép.

Nếu IdP đọc SP metadata từ URL định kỳ, cần biết cache/refresh interval. Một số IdP lưu snapshot tĩnh cho đến khi quản trị viên cập nhật. Vì vậy cập nhật SP metadata **không bảo đảm** IdP đã tự chấp nhận ACS mới ngay.

Nếu IdP yêu cầu ký AuthnRequest, SP phải có khóa ký tương ứng. Việc thay ACS không loại bỏ yêu cầu ký. Không thêm private key vào SP metadata: metadata chỉ công bố public certificate.

## 10. Cấu hình khác nhau với nhiều IdP hoặc nhiều tenant

Một cổng có thể có các registration:

~~~text
corp      -> IdP nội bộ
partner-b -> IdP của công ty B
partner-c -> IdP của công ty C

START:
  /federation/saml/start/corp
  /federation/saml/start/partner-b
  /federation/saml/start/partner-c

ACS:
  /federation/saml/acs/corp
  /federation/saml/acs/partner-b
  /federation/saml/acs/partner-c
~~~

**Điều này hỗ trợ routing, không tự bảo đảm tenant isolation.** Server phải xác minh signer/issuer đúng registration, ánh xạ user nội bộ theo IdP và định danh bền vững, rồi kiểm quyền dữ liệu theo tenant. Nếu B và C cùng dùng `alice` hoặc email giống nhau, không được tự gộp account.

Khi chọn ACS **không có registrationId**:

~~~text
POST /federation/saml/acs
~~~

framework có thể tra registration qua AuthnRequest đã lưu hoặc issuer trong Response. Nhưng với multi-IdP, IdP-initiated và resolver tùy chỉnh, phải đánh giá kỹ trust policy, anti-replay và security context. Nếu không có nhu cầu cụ thể, **giữ `{registrationId}`** giúp dễ kiểm, dễ truy vết lỗi, dễ phối hợp với từng IdP.

## 11. Session, RelayState và tương quan request không được bỏ

`Saml2WebSsoAuthenticationRequestFilter` lưu `AuthnRequest` qua `Saml2AuthenticationRequestRepository`; mặc định trên các dòng hiện đại có thể dùng `HttpSessionSaml2AuthenticationRequestRepository`.

Khi browser gửi SAMLResponse về ACS, `Saml2WebSsoAuthenticationFilter` và `Saml2AuthenticationTokenConverter` có thể sử dụng request đã lưu để giải quyết registration/correlation. Khi chỉnh start/ACS:

- Đảm bảo request ID và state được lưu trước khi đi IdP.
- Browser cần giữ session/cookie qua redirect và POST từ domain IdP.
- `InResponseTo` phải đáp ứng chính sách correlation cho SP-initiated.
- `RelayState` không được dùng như một bằng chứng danh tính/tenant tự thân.
- Không cho browser cung cấp một issuer URL tùy ý rồi chọn registration ngoài allowlist.
- Đừng sửa lỗi mất session bằng cách mặc định nhận mọi unsolicited SAMLResponse.
- Nếu dùng Redis/distributed cache cho request repository, ràng buộc request với đúng phiên/browser, TTL và anti-replay.

Tài liệu Spring Security cảnh báo việc lấy AuthnRequest chỉ dựa vào `InResponseTo` hoặc `RelayState` trong cache chung có thể làm mất sự bảo vệ chống login fixation vốn có khi ràng buộc bằng session. Đừng chọn giải pháp cache chỉ vì tiện routing.

## 12. CSRF và ACS POST từ IdP

SAML Response tới ACS thường là một **cross-site POST** vì browser đến từ domain của IdP. Spring Security có xử lý tích hợp cho luồng SAML Web SSO, nhưng khi thay `loginProcessingUrl` phải kiểm đúng matcher/filter/CSRF exemption với phiên bản đang chạy.

**Không sửa 403 tại ACS bằng cách tắt CSRF toàn ứng dụng:**

~~~java
// Đây không phải giải pháp mặc định cho lỗi đổi ACS
http.csrf(csrf -> csrf.disable());
~~~

Cách an toàn hơn:

1. Chắc chắn `POST /federation/saml/acs/{registrationId}` thực sự đi vào SAML filter.
2. Kiểm ngoại lệ CSRF dành cho ACS trong cấu hình SAML hiện hành.
3. Nếu cần cấu hình CSRF thủ công, chỉ giới hạn cho **đúng path/method ACS**.
4. Bảo vệ các form/POST nghiệp vụ vẫn cần CSRF.
5. Kiểm cookie `SameSite` và `Secure` để session có thể quay lại sau IdP.
6. Phân biệt 403 do CSRF với 403 do authorization, hoặc lỗi SAML validation.

Giữ HTTPS/TLS và không ghi nguyên SAMLResponse, cookie, private key vào log debug production.

## 13. Reverse proxy, public URL và context path

Ứng dụng có thể chạy ở `http://saml-service:8080`, trong khi người dùng/IdP thấy `https://portal.example.com/app`. Nếu Spring tính `{baseUrl}` từ host nội bộ, AuthnRequest hoặc metadata có thể quảng bá ACS `http://saml-service:8080/...` và bị IdP từ chối.

Quy trình:

1. Chốt **public base URL** thật: scheme, hostname, port và context path.
2. Dùng public ACS URL tường minh khi proxy phức tạp.
3. Kiểm đường rewrite từ public `/app/federation/saml/acs/...` tới Spring handler nội bộ tương ứng.
4. Chỉ nhận `Forwarded`/`X-Forwarded-*` từ proxy được quản trị, không tin header giả của client.
5. Đảm bảo proxy chuyển **HTTP POST và body SAMLResponse**, không rewrite thành GET.
6. Kiểm cookies/session ổn khi request đi qua IdP rồi quay về.
7. Tải SP metadata qua public URL và so với Reply URL trên IdP.
8. Test login trên public hostname, không chỉ `localhost`.

Một thay đổi start URL không đòi hỏi đổi public ACS nếu ACS cũ đã đúng. Ngược lại, đổi ACS đòi hỏi kiểm lại toàn bộ đường đi public tới backend.

## 14. Java 17 độc lập: kiểm tra hợp đồng endpoint

Chương trình sau minh họa **logic mapping URL**, không phát AuthnRequest, không xác minh chữ ký, không có Spring Security và không chứng minh login thành công. Dùng nó để tập phân biệt start với ACS và kiểm hai phía có thống nhất về ACS hay chưa.

Tạo file `SamlEndpointContractDemo.java`:

~~~java
import java.util.Map;

public class SamlEndpointContractDemo {
    record Paths(String start, String acs) {
        String startUrl(String base, String id) {
            return base + start.replace("{registrationId}", id);
        }
        String acsUrl(String base, String id) {
            return base + acs.replace("{registrationId}", id);
        }
    }

    public static void main(String[] args) {
        String base = "https://portal.example.com";
        String id = "partner-b";
        Paths paths = new Paths(
                "/federation/saml/start/{registrationId}",
                "/federation/saml/acs/{registrationId}");

        Map<String, String> registeredAtIdP = Map.of(
                id, "https://portal.example.com/federation/saml/acs/partner-b");

        String start = paths.startUrl(base, id);
        String acs = paths.acsUrl(base, id);
        String oldAcs = base + "/login/saml2/sso/" + id;

        System.out.println("Start: " + start);
        System.out.println("ACS: " + acs);
        System.out.println("IdP agrees: "
                + acs.equals(registeredAtIdP.get(id)));
        System.out.println("Old ACS agrees: "
                + oldAcs.equals(registeredAtIdP.get(id)));
        System.out.println("Unknown registration: "
                + registeredAtIdP.containsKey("partner-c"));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac SamlEndpointContractDemo.java
java SamlEndpointContractDemo
~~~

Stdout chính xác:

~~~text
Start: https://portal.example.com/federation/saml/start/partner-b
ACS: https://portal.example.com/federation/saml/acs/partner-b
IdP agrees: true
Old ACS agrees: false
Unknown registration: false
~~~

Ý nghĩa:

- **Start** là URL browser đến để yêu cầu SP tạo AuthnRequest.
- **ACS** là nơi IdP cần gửi Response.
- **IdP agrees: true** nghĩa địa chỉ trong ví dụ đã đồng nhất về mặt **chuỗi**.
- **Old ACS agrees: false** mô phỏng việc URL cũ không khớp cấu hình mới.
- **Unknown registration: false** cho thấy đối tác chưa khai báo không thuộc danh sách.

Đây chỉ là **phép kiểm hợp đồng URL trước tích hợp**, chưa kiểm SAML metadata, trust anchors, certificates, HTTP, session hoặc chính sách authorization.

## 15. Bộ kiểm thử tích hợp từ đầu đến cuối

| Kịch bản | Đầu vào/thao tác | Kỳ vọng |
| --- | --- | --- |
| Start mới | GET `/federation/saml/start/partner-b` | Sinh AuthnRequest cho đúng IdP |
| Start cũ | GET `/saml2/authenticate/partner-b` | Hành vi đúng chính sách migration |
| Registration lạ | GET `/federation/saml/start/unknown` | Không tự chọn fallback IdP khác |
| SSO Destination | Đọc AuthnRequest trong test lab | Trỏ tới IdP SSO URL, không phải ACS |
| ACS trong AuthnRequest | Kiểm `AssertionConsumerServiceURL` nếu được phát | Trùng ACS mới được IdP chấp nhận |
| SP metadata | GET metadata theo ID | ACS mới, Entity ID ổn định, cert đúng |
| IdP config | Kiểm Reply/ACS URL của B | Khớp public ACS mới |
| Browser SSO | Login account test qua IdP B | Browser POST về ACS mới, session đúng |
| Wrong issuer | Response từ IdP C tại route B | Từ chối |
| Wrong destination | SAMLResponse nhắm ACS cũ hoặc nơi khác | Từ chối |
| Wrong recipient | Subject confirmation nhắm endpoint khác | Từ chối |
| Wrong audience | Assertion dành cho SP khác | Từ chối |
| Expired assertion | `NotOnOrAfter` đã qua | Từ chối |
| Request correlation | `InResponseTo` sai, hoặc session mất | Từ chối theo policy |
| Replay | Nộp lại assertion đã dùng | Không tạo session trái phép |
| IdP-initiated | Không có AuthnRequest trước | Chỉ chấp nhận theo chính sách riêng |
| CSRF | ACS POST và POST nghiệp vụ | ACS hoạt động; form khác vẫn được bảo vệ |
| Authorization | User B cố xem dữ liệu C | 403 dù login thành công |
| Proxy rewrite | Public URL có context prefix | Filter/ACS/metadata khớp |
| Multi-node | Quay về node khác | Request repository/session vận hành như thiết kế |

Kiểm thủ công trong staging (nơi các ví dụ URL đã được thay bằng URL thật):

~~~bash
curl -i "https://portal.example.com/federation/saml/start/partner-b"
curl -i "https://portal.example.com/saml2/metadata/partner-b"
~~~

Start có thể trả 302 tới IdP hoặc HTML form nếu dùng POST binding; metadata trả XML khi bật đúng cấu hình. **Không có stdout cố định** cho các lệnh này. Đừng dùng URL .example như URL production. Cần dùng IdP test và một browser session thật để kiểm đầy đủ response.

**PASS chỉ khi cả ba mặt thống nhất:** Spring xử lý start và ACS đúng; SAML protocol có issuer/audience/recipient/correlation hợp lệ; ứng dụng cấp quyền đúng tenant.

## 16. Bảng lỗi thường gặp

| Hiện tượng | Lý do thường gặp | Hướng xử lý |
| --- | --- | --- |
| Bấm login vẫn về đường cũ | Link trên loginPage/entry point chưa sửa | Cập nhật links và test browser |
| Start mới trả 404 | Sai matcher/filter chain hoặc chưa cấu hình `authenticationRequestUriQuery` | Kiểm SecurityFilterChain và URL |
| Browser không tới IdP | Sai SSO URL, signing/binding của IdP hoặc request resolver | Kiểm `RelyingPartyRegistration` và AuthnRequest |
| IdP báo ACS chưa đăng ký | ACS mới chưa có trong cấu hình IdP | Cập nhật Reply URL/metadata |
| IdP vẫn POST về ACS cũ | Cache metadata/config snapshot cũ | Đồng bộ IdP và kế hoạch cutover |
| POST ACS mới trả 404/405 | Filter không nhận path/method, proxy rewrite sai | Kiểm `loginProcessingUrl` và POST routing |
| POST ACS trả 403 | CSRF rule, session, authentication/authorization khác | Trace đúng filter và policy; không tắt CSRF toàn cục |
| Invalid Destination/Recipient | Public ACS không khớp endpoint đã xác minh | Sửa ACS/IdP/proxy, không tắt validation |
| Invalid Audience | SP Entity ID bị đổi hoặc IdP phát cho SP khác | Giữ/đồng bộ Entity ID đúng |
| Unknown registration | ID không có trong repository hoặc converter tra sai | Kiểm repository/resolver và lưu request |
| InResponseTo unknown | Request không được lưu hoặc session/cookie bị mất | Kiểm request repo, SameSite, multi-node |
| Signature mismatch | Sai cert/rotation/signing policy | Đồng bộ trust anchors, không bỏ verify |
| Login thành công nhưng 403 tài nguyên | Thiếu role/membership/object authorization | Sửa policy nghiệp vụ, không lỗi ACS |

Chẩn đoán nên lưu mã lỗi đã rút gọn, registrationId đã xác minh và thông tin vận hành cần thiết. Không log raw SAML assertions hay private keys.

## 17. Khác biệt theo phiên bản Spring Security

| Dòng phiên bản | Ghi chú khi tùy chỉnh |
| --- | --- |
| **Spring Security 5.2–5.6** | SAML2 login tồn tại nhưng cách đặt custom AuthnRequest endpoint cần API filter/resolver đúng version; không copy code DSL đời mới |
| **Spring Security 5.7–5.8** | Có `authenticationRequestResolver` và các API tùy chỉnh; sử dụng Servlet `javax.servlet` ở 5.x |
| **Spring Security 6.0** | `authenticationRequestUriQuery` có từ 6.0; đã chuyển sang `jakarta.servlet` |
| **Spring Security 6.1–6.5** | Có `saml2Metadata(...)` giúp công bố SP metadata; `SecurityFilterChain` là cách cấu hình chuẩn |
| **Spring Security 7.x** | Tiếp tục `authenticationRequestUriQuery` và `loginProcessingUrl`; provider OpenSAML của nhánh mới khác các ví dụ cũ |

Khi nâng version, không chỉ xem `pom.xml` khai báo dependency nào mà phải xem **resolved dependencies** thực tế. Ví dụ:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-saml2-service-provider
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-config
~~~

Hoặc Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Build thành công **không tự chứng minh SSO đã hoạt động**. Luôn có integration test với IdP và public URL thật.

## 18. Checklist trước khi triển khai production

- [ ] Xác định đúng hai endpoint start và ACS, kèm URL public đã được phê duyệt.
- [ ] Chọn `registrationId` có sẵn, không tự tạo IdP từ tham số bên ngoài.
- [ ] Cập nhật `authenticationRequestUriQuery` và login page/entry point khi đổi start.
- [ ] Cập nhật `loginProcessingUrl` và `assertionConsumerServiceLocation` khi đổi ACS.
- [ ] Kiểm `RelyingPartyRegistration.entityId` không bị đổi ngoài ý muốn.
- [ ] Cập nhật SP metadata và đăng ký ACS mới với IdP.
- [ ] Kiểm đúng signing verification certificates, bindings, SSO endpoint.
- [ ] Chạy cùng browser session, kiểm AuthnRequest ID, RelayState và `InResponseTo`.
- [ ] Negative tests sai issuer/audience/recipient/destination/expiration đều bị từ chối.
- [ ] CSRF bảo vệ form nghiệp vụ; ACS POST hoạt động đúng mà không tắt toàn bộ CSRF.
- [ ] Reverse proxy, HTTPS, context path, forwarded headers, session cookies được cấu hình an toàn.
- [ ] Login thành công vẫn kiểm quyền tenant, role, object.
- [ ] Có kế hoạch chuyển đổi IdP, giám sát lỗi, key rotation và rollback.

## 19. Tài liệu gốc cần đối chiếu

- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): start endpoint, `authenticationRequestUriQuery`, request repository và resolver.
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `loginProcessingUrl`, ACS và authentication converter.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): mô hình Web Browser SSO và URI patterns.
- [Javadoc — Saml2LoginConfigurer](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html): định nghĩa các API thay URL.
- [Javadoc — Saml2WebSsoAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/Saml2WebSsoAuthenticationFilter.html): điểm xử lý SAMLResponse.
- [Javadoc — RelyingPartyRegistration.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.Builder.html): `assertionConsumerServiceLocation`.
- [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): xuất metadata SP để nhập tại IdP.

**Kết luận:** thay **start URL** là thay nơi user gọi để SP tạo AuthnRequest; thay **ACS** là thay nơi IdP gửi SAMLResponse, nên phải đồng bộ **filter xử lý, RelyingPartyRegistration, SP metadata và IdP**. Một hệ thống chỉ thực sự đúng khi test được cả luồng và vẫn giữ đầy đủ các kiểm tra chữ ký, issuer, audience, recipient, thời gian, session và quyền tài nguyên.