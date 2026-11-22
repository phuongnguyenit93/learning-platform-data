# ForceAuthn, IsPassive và giới hạn bảo đảm do IdP thực thi

## 1. Bài toán và mục tiêu

Trong luồng SAML 2.0 Web Browser SSO, ứng dụng Spring Security đóng vai trò **Service Provider (SP, Relying Party)**. SP tạo một thông điệp `AuthnRequest` và chuyển browser tới **Identity Provider (IdP, Asserting Party)**. IdP quyết định cách xác thực người dùng, có thể tái sử dụng phiên SSO hiện tại hoặc yêu cầu một bước xác minh mới. Hai thuộc tính của `AuthnRequest` ảnh hưởng trực tiếp đến quyết định đó:

- **`ForceAuthn`**: SP yêu cầu IdP xác thực trực tiếp người dùng, không đơn thuần dựa vào **security context trước đó**.
- **`IsPassive`**: SP yêu cầu IdP và user agent **không chiếm quyền điều khiển giao diện để tương tác với người dùng một cách rõ ràng**.

Chúng có vẻ đối lập nhưng không phải lúc nào cũng bất khả thi khi cùng bật: một IdP có phương tiện xác thực trực tiếp **mà không cần tương tác hiển thị** có thể thỏa đồng thời cả hai, tùy chính sách và khả năng. Còn khi không thể thỏa `IsPassive`, IdP phải xử lý thất bại phù hợp thay vì tự hiển thị form login trong một giao dịch passive.

Bài học thuộc **Spring Security - federation → Tùy chỉnh AuthnRequest**. Sau bài, bạn có thể:

1. Đọc chính xác ý nghĩa hai cờ theo **SAML 2.0 Core**, phân biệt giá trị vắng mặt và giá trị `false`.
2. Hiểu bảng kết hợp hai cờ, tình huống reauthentication, SSO im lặng, step-up và mã lỗi `NoPassive`.
3. Tùy chỉnh `AuthnRequest` trong Spring Security Servlet bằng `OpenSaml4AuthenticationRequestResolver` hoặc `OpenSaml5AuthenticationRequestResolver` tương ứng version.
4. Phân biệt **ý định của SP**, **nghĩa vụ trong đặc tả đối với IdP tuân thủ** và **hành vi IdP thực tế có thể kiểm chứng**.
5. Thiết kế yêu cầu xác thực mạnh mà không nhầm `ForceAuthn` với MFA, freshness bảo đảm hoặc authorization của ứng dụng.
6. Kiểm thử cả trường hợp request gửi đi đúng XML nhưng IdP không tuân thủ, phản hồi lỗi, phiên browser không còn và request không được tạo.
7. Giữ nguyên kiểm tra chữ ký SAML, issuer, audience, destination, thời gian và tương quan `InResponseTo`.

Phạm vi ví dụ Spring: **Java 17+, Spring Boot 3.x, Spring Security 6.x trên Servlet/MVC**, với phần khác biệt Spring Security 7.x được trình bày riêng. Ví dụ URL và metadata là giả định, không thể đăng nhập với một IdP không có thật.

## 2. Đọc đúng thuộc tính AuthnRequest

Trong XML, hai thuộc tính nằm **trực tiếp trên phần tử giao thức** `<samlp:AuthnRequest>`, không phải bên trong `RelayState` hay một phần tử `RequestedAuthnContext`:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_request-demo-001"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    Destination="https://idp.example.org/saml/sso"
    AssertionConsumerServiceURL="https://app.example.org/login/saml2/sso/corp"
    ForceAuthn="true"
    IsPassive="false">
  <saml:Issuer
      xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
      >https://app.example.org/saml/metadata</saml:Issuer>
</samlp:AuthnRequest>
~~~

**Đây là XML minh họa cấu trúc**, không phải request hợp lệ để gửi production: ID, IssueInstant, Destination, issuer, ACS, signature và metadata phải do triển khai thực tế tạo, so khớp và bảo vệ.

Cú pháp quan trọng:

| Thành phần | Định nghĩa | Đừng nhầm với |
| --- | --- | --- |
| `ForceAuthn="true"` | Cờ Boolean đặt yêu cầu xác thực trực tiếp mới theo SAML | Chính sách MFA, yêu cầu OTP hay mật khẩu cụ thể |
| `IsPassive="true"` | Cờ Boolean cấm tương tác UI đáng chú ý trong xử lý request | Bảo đảm browser không chuyển hướng hoặc không tạo network request |
| Không ghi `ForceAuthn` | Theo chuẩn, **mặc định false** | “IdP bắt buộc dùng phiên cũ” |
| Không ghi `IsPassive` | Theo chuẩn, **mặc định false** | “IdP bắt buộc hiển thị login form” |
| `RequestedAuthnContext` | Ràng buộc ngữ cảnh/phương thức xác thực theo chính sách | Cờ ForceAuthn |
| `AuthnStatement@AuthnInstant` | Thời điểm sự kiện xác thực được IdP khẳng định | Bằng chứng tuyệt đối rằng ForceAuthn đã được thực thi đúng |
| `Response@InResponseTo` | Liên hệ response với request đã phát | Trường trả lời “ForceAuthn đã được làm” |

SAML Core mục **3.4.1 Authentication Request** nói: nếu `ForceAuthn=true`, IdP **MUST** xác thực trực tiếp người dùng thay vì dựa vào security context trước đó. Nếu `IsPassive=true`, IdP và user agent **MUST NOT** visibly take control of UI để tương tác với người dùng theo cách đáng chú ý. Vắng hai cờ thì mặc định **false**. Đây là nghĩa **chuẩn của giao thức**; thực thi của một sản phẩm IdP cụ thể phải kiểm chứng bằng tài liệu và thử nghiệm.

## 3. ForceAuthn: yêu cầu reauthentication, không mặc định là MFA

Một ứng dụng có thao tác nhạy cảm như xem hồ sơ pháp lý, đổi số tài khoản nhận tiền hoặc phê duyệt giao dịch. Người dùng đã đăng nhập IdP từ trước; ứng dụng muốn IdP **xác thực trực tiếp lại** thay vì chỉ dựa trên phiên SSO có sẵn. Đó là tình huống sử dụng `ForceAuthn=true`.

### Điều ForceAuthn có ý nghĩa

- SP phát **AuthnRequest mới** với thuộc tính `ForceAuthn="true"`.
- IdP tuân thủ SAML xử lý yêu cầu xác thực trực tiếp người dùng **không chỉ suy ra từ một security context trước đó**.
- IdP có thể yêu cầu mật khẩu, passkey, chứng chỉ, bước xác minh có tương tác hoặc một phương thức khác phù hợp với chính sách của nó.
- Nếu IdP không thể thỏa yêu cầu, nó có thể trả trạng thái lỗi theo giao thức; SP phải có đường xử lý thất bại an toàn.
- Sự kiện xác thực thành công có thể tạo `AuthnStatement` và `AuthnContext` trong assertion; SP phải xác minh chúng theo yêu cầu nghiệp vụ.

### Điều ForceAuthn **không tự bảo đảm**

- Không có nghĩa **phải nhập lại mật khẩu**. SAML không quy định một phương thức cụ thể cho thuộc tính này.
- Không có nghĩa **bắt buộc MFA**. Muốn MFA/assurance, phải có chính sách IdP và thường phải sử dụng `RequestedAuthnContext`, trust/contract hoặc claim/assertion phù hợp.
- Không định nghĩa một **tuổi xác thực tối đa** (max age) theo số giây. Thời điểm xác thực cần được xem xét riêng theo `AuthnInstant` và policy; không nhập nhằng với tham số OIDC `max_age`.
- Không có nghĩa browser sẽ luôn thấy form đăng nhập. Cách IdP xác thực trực tiếp có thể khác từng nền tảng.
- Không vô hiệu hay xóa toàn bộ phiên SSO hiện có ở IdP, không ép logout khỏi ứng dụng khác.
- Không làm SP xác minh chữ ký Response/Assertion được “mạnh hơn”; bảo vệ tính xác thực message vẫn là bước riêng.
- Không bảo đảm chống phishing hoặc chống mạo danh ở mức mong muốn nếu chính sách IdP, phương thức xác thực và thiết bị người dùng không đáp ứng.

**Phân biệt nghiêm túc:** chuẩn đặt nghĩa vụ **MUST** lên IdP tuân thủ, nhưng **SP không thể suy ra IdP đã thực thi đúng chỉ vì cờ xuất hiện trong XML**. Với tác vụ quan trọng, kiểm thử/cấu hình/idp audit và bằng chứng assertion/policy mới giúp đánh giá mức bảo đảm thực tế.

## 4. IsPassive: yêu cầu xác thực không tương tác UI

Với `IsPassive=true`, SP yêu cầu quá trình xử lý **không làm IdP hoặc user agent chiếm quyền giao diện của người yêu cầu để giao tiếp với người dùng một cách rõ ràng**. Đây có thể là nhu cầu của một quy trình muốn thăm dò liệu người dùng đã có điều kiện xác thực phù hợp hay chưa.

Ví dụ: ứng dụng vừa mở một cửa sổ/luồng SSO test, muốn biết liệu IdP có thể nhận diện user trong bối cảnh hiện tại mà **không bật form đăng nhập tương tác**. Nếu có, IdP trả response hợp lệ; nếu không, IdP từ chối bằng trạng thái như `NoPassive`.

### Những điều cần phân biệt

- **Passive không có nghĩa IdP tuyệt đối không thực hiện xác thực.** IdP có thể sử dụng security context trước đó khi `ForceAuthn=false`, hoặc một cơ chế thỏa điều kiện passive để xác thực mới nếu bắt buộc.
- **Passive không có nghĩa trình duyệt không có redirect.** Front-channel SAML vẫn có thể đi qua browser. Điều bị giới hạn là tương tác UI đáng chú ý theo chuẩn.
- **Passive không phải “bypass đăng nhập”**. SP vẫn cần response đã ký hợp lệ, đúng issuer/audience/recipient/thời gian, và user có thể không được xác thực nếu IdP trả lỗi.
- **Passive không bảo đảm hoạt động trong iframe**. Third-party cookie, tracking prevention, Content Security Policy, SameSite và chính sách trình duyệt có thể khiến IdP không nhìn thấy phiên trong ngữ cảnh nhúng.
- **Passive không mặc nhiên giống refresh token hoặc gọi API nền**. Nó vẫn là Web Browser SSO dùng AuthnRequest.
- IdP có thể **không hỗ trợ hoặc hạn chế IsPassive**. Nếu không có khả năng xác thực passive theo contract, SP phải có fallback chính sách, không tự chuyển sang interactive mà không thông báo/được phép.

### Trạng thái NoPassive

SAML Core định nghĩa status URI:

~~~text
urn:oasis:names:tc:SAML:2.0:status:NoPassive
~~~

Nó biểu thị IdP **không thể xác thực người dùng theo cách passive đã yêu cầu**. Trong nhiều profile, nó xuất hiện ở một status cấp dưới của `Responder`; triển khai thực tế cần kiểm tra response/status đầy đủ. Nó **không có nghĩa**:
- Username/password sai;
- IdP đang bị tấn công;
- SP nên tự coi user là anonymous đã đăng nhập;
- SP được phép bỏ tính passive rồi xác thực tương tác bằng cách tự tiếp tục request cũ.

Hướng UX an toàn: thông báo không thể đăng nhập im lặng, để người dùng chủ động chọn **đăng nhập tương tác** nếu chính sách cho phép; khởi tạo **giao dịch SAML mới** không có `IsPassive=true`. Không “bẻ” Response lỗi thành Response thành công.

## 5. Bốn tổ hợp ForceAuthn/IsPassive và kết quả mong đợi

| ForceAuthn | IsPassive | Ý định của SP | Hành vi mong đợi từ IdP tuân thủ |
| --- | --- | --- | --- |
| **false** | **false** | Login SSO thông thường | Có thể tận dụng security context hiện có hoặc tương tác tùy chính sách |
| **true** | **false** | Yêu cầu xác thực trực tiếp mới | Không chỉ dựa vào security context trước đó; có thể hiển thị tương tác xác thực |
| **false** | **true** | Thử xác thực mà không cần UI đáng chú ý | Có thể dùng điều kiện/phiên sẵn có nếu phù hợp; nếu không thể, trả lỗi như `NoPassive` |
| **true** | **true** | Muốn xác thực trực tiếp **và** không có UI đáng chú ý | Chỉ thành công nếu IdP có thể **freshly authenticate** mà vẫn đáp ứng IsPassive; nếu không, không được xác thực mới theo cách phá ràng buộc passive |

Trường hợp `true/true` **không luôn là XML sai**. SAML Core chỉ rõ: khi hai cờ cùng true, IdP **MUST NOT freshly authenticate** trừ khi thỏa ràng buộc IsPassive. Trong một sản phẩm chỉ hỗ trợ reauthentication bằng form có tương tác, kết hợp này sẽ không thành công và nên dẫn tới lỗi; ở sản phẩm có phương thức trực tiếp không tương tác, có thể có trường hợp phù hợp.

### Ví dụ dựa trên tình huống

1. **Mở dashboard thông thường, user đã có IdP session:** `false,false` thường đủ; IdP có thể tận dụng SSO.
2. **Phê duyệt hành động nhạy cảm:** cân nhắc `true,false` nếu thực sự cần xác thực mới; đồng thời cấu hình assurance/MFA theo hợp đồng IdP.
3. **Kiểm tra “có thể SSO không tương tác không?”:** `false,true`; nếu `NoPassive`, cho phép người dùng chọn đăng nhập tương tác theo UX.
4. **Bắt buộc xác thực mới nhưng tuyệt đối không gây UI:** `true,true` chỉ thích hợp nếu IdP có phương thức silent fresh authentication đã được xác minh; không nên dùng như lựa chọn mặc định.

## 6. Chúng nằm ở đâu trong luồng HTTP/SAML?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant IDP as SAML IdP
    B->>SP: GET /saml2/authenticate/corp
    SP->>SP: Tạo AuthnRequest: ForceAuthn/IsPassive
    SP-->>B: 302 đến SSO IdP với SAMLRequest
    B->>IDP: GET SSO endpoint
    alt Có thể đáp ứng yêu cầu cờ và chính sách
        IDP-->>B: SAMLResponse thành công qua form POST
        B->>SP: POST SAMLResponse về ACS
        SP->>SP: Verify signature, issuer, audience, time, InResponseTo
        SP-->>B: Tạo phiên SP và chuyển về tài nguyên
    else Không thể passive/không đáp ứng policy
        IDP-->>B: SAML Response lỗi, ví dụ NoPassive
        B->>SP: POST tới ACS nếu IdP dùng Web SSO POST
        SP->>SP: Xử lý thất bại; không tạo authenticated principal
        SP-->>B: Trang lỗi hoặc lựa chọn login tương tác mới
    end
~~~

Ở binding **HTTP-Redirect**, SAML XML thường được raw DEFLATE, Base64 và URL-encode dưới tham số `SAMLRequest`. Cờ nằm **bên trong XML** sau khi decode, không thành `&ForceAuthn=true` hoặc `&IsPassive=true` ở URL query theo cơ chế chuẩn. Trong binding **HTTP-POST AuthnRequest**, browser POST form field `SAMLRequest` chứa Base64 XML; cờ vẫn là thuộc tính XML.

Để debug, cần tìm đúng `SAMLRequest`, giải mã **an toàn trong môi trường test** hoặc dùng log/debug công cụ chuyên dụng, rồi xác định XML có hai thuộc tính hay không. Đừng sửa query sau khi request đã được ký và tin rằng chữ ký vẫn hợp lệ.

Một lưu ý về phân tách: **SP tạo request, browser vận chuyển request, IdP quyết định xác thực**. Một response thành công không tự minh chứng cách IdP đã xác thực trừ khi các thông tin và policy tương ứng cung cấp bằng chứng đáng tin cậy.

## 7. Spring Security xử lý AuthnRequest ở đâu?

Trong `spring-security-saml2-service-provider` trên Servlet stack:

- `Saml2WebSsoAuthenticationRequestFilter` xử lý khởi tạo SSO, mặc định tại `/saml2/authenticate/{registrationId}` hoặc biến thể query được framework hỗ trợ.
- `Saml2AuthenticationRequestResolver` quyết định cách dựng AuthnRequest dựa trên `HttpServletRequest` và registration. Một implementation OpenSAML hỗ trợ customizer trên đối tượng `AuthnRequest` trước khi message được serialize/đưa đi.
- `RelyingPartyRegistrationRepository` lưu cấu hình IdP/ACS/entityId/certificate cho mỗi registration.
- `Saml2AuthenticationRequestRepository` lưu request đã phát để liên hệ với response. Mặc định trên Servlet thường là `HttpSessionSaml2AuthenticationRequestRepository`.
- `Saml2WebSsoAuthenticationFilter` xử lý SAMLResponse ở ACS, thường `POST /login/saml2/sso/{registrationId}`, xác thực qua provider.
- IdP thực thi hoặc không thực thi yêu cầu ForceAuthn/IsPassive theo khả năng và chính sách của nó; Spring Security SP **không điều khiển được màn hình, cookie, MFA engine hay chính sách session trong IdP**.

Mặc định Spring Security đặt `ForceAuthn=false` trong ví dụ chính thức. Muốn điều chỉnh, dùng extension point **`setAuthnRequestCustomizer`**, thay vì viết controller tạo string XML hoặc sửa trực tiếp `SAMLRequest` sau khi framework ký.

## 8. Tùy chỉnh cố định trên Spring Security 6.x

Với **Spring Security 6.x có `OpenSaml4AuthenticationRequestResolver`** và OpenSAML 4 tương thích, đăng ký một bean request resolver được Spring Security nhận biết.

Tệp `src/main/java/com/example/federation/SamlAuthnRequestConfig.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlAuthnRequestConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        RelyingPartyRegistrationResolver resolver =
                new DefaultRelyingPartyRegistrationResolver(registrations);

        OpenSaml4AuthenticationRequestResolver samlResolver =
                new OpenSaml4AuthenticationRequestResolver(resolver);

        samlResolver.setAuthnRequestCustomizer(context -> {
            context.getAuthnRequest().setForceAuthn(Boolean.TRUE);
            context.getAuthnRequest().setIsPassive(Boolean.FALSE);
        });

        return samlResolver;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

**Điều kiện chạy:** đây là lớp Spring configuration bên trong dự án Boot Servlet đã có `@SpringBootApplication`, dependency SAML Service Provider/OpenSAML thích hợp và IdP registration hợp lệ. Nó **không phải Java main độc lập** để chạy `javac SamlAuthnRequestConfig.java` bằng JDK trống. Không có stdout cố định; kết quả cần quan sát là **XML AuthnRequest thực sự có `ForceAuthn="true"`** và hành vi IdP.

Điểm đáng chú ý:
1. Spring Security lấy bean `Saml2AuthenticationRequestResolver` tùy chỉnh từ context theo cơ chế mà phiên bản hỗ trợ.
2. `DefaultRelyingPartyRegistrationResolver` tra registration theo request/path.
3. `setAuthnRequestCustomizer` sửa đối tượng OpenSAML **trước bước serialize/sign**.
4. Cấu hình trên đặt **ForceAuthn=true cho mọi AuthnRequest khởi tạo theo resolver này**; đó là chính sách khá mạnh, có thể làm login thường ngày kém tiện lợi. Dùng có chủ đích.
5. `setIsPassive(false)` được đưa vào để minh họa hai thuộc tính. Vì mặc định spec đã là false, nếu không có nhu cầu có thể chỉ set ForceAuthn.

### Lưu ý import và version

- Spring Security 6.x dựa OpenSAML 4 có `OpenSaml4AuthenticationRequestResolver`. Một số bản 6.x hỗ trợ tùy chọn OpenSAML 5; nếu đã chuyển stack, dùng đúng resolver 5 và hướng dẫn dependency tương ứng.
- Trong Spring Security 7.x, hướng dẫn mới dùng **`OpenSaml5AuthenticationRequestResolver`**. Thay **đúng tên class và import** sau khi nâng phiên bản; không đổi mỗi class name nếu dependency vẫn là OpenSAML 4.
- Giữ Spring Security/OpenSAML versions theo BOM/compatibility. Những tên như `OpenSamlXAuthenticationProvider` trong tài liệu là cách trình bày chung, không phải tên class có thể import.
- Nếu một project đã có bean request resolver của đối tác khác, tích hợp logic trong bean hiện tại; đừng âm thầm tạo hai bean cạnh tranh.

## 9. Phiên bản dùng OpenSAML 5 / Spring Security 7.x

Ý tưởng giống nhau; class resolver 5 có API customizer tương ứng:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml5AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;

@Configuration
public class SamlAuthnRequestResolverConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        RelyingPartyRegistrationResolver registrationResolver =
                new DefaultRelyingPartyRegistrationResolver(registrations);

        OpenSaml5AuthenticationRequestResolver resolver =
                new OpenSaml5AuthenticationRequestResolver(registrationResolver);

        resolver.setAuthnRequestCustomizer(context -> {
            context.getAuthnRequest().setForceAuthn(true);
            context.getAuthnRequest().setIsPassive(false);
        });
        return resolver;
    }
}
~~~

Ví dụ này là **một lựa chọn thay thế** ví dụ OpenSAML 4; không tạo cả hai bean trong cùng app. Để xử lý login, dự án vẫn cần `.saml2Login(... )`, registration IdP và filter chain ở lớp bảo mật khác. Bản Spring Security 7.0/7.1 document chính thức minh họa customizer `setForceAuthn(true)` trên resolver OpenSAML 5.

Nếu project vẫn ở 6.x, kiểm tra **version đang dùng** trước khi chọn API; không áp dụng lớp 7.x chỉ vì thấy URL tài liệu mới.

## 10. Thử chế độ passive bằng request resolver

Khi chủ đích là **thử đăng nhập im lặng**, đổi customizer thành:

~~~java
resolver.setAuthnRequestCustomizer(context -> {
    context.getAuthnRequest().setForceAuthn(false);
    context.getAuthnRequest().setIsPassive(true);
});
~~~

Đây là **mảnh code** đặt trên đối tượng resolver đang dùng (`OpenSaml4...` hoặc `OpenSaml5...`) trong cùng bean; **không phải chương trình Java độc lập**. Cấu hình này nói với IdP: nếu có thể xác thực người dùng mà không tương tác UI đáng chú ý, hãy thực hiện; nếu không, phản hồi lỗi theo profile. Nó không cam kết browser im lặng ở mọi chính sách cookie.

### Tại sao không bật passive cho mọi login?

- User mới chưa có IdP session phù hợp sẽ thường không thể login nếu IdP cần form tương tác.
- Hệ thống có thể rơi vào vòng lặp “silent check → NoPassive → silent check” nếu failure handler chỉ retry cùng request.
- Browser chặn third-party cookie có thể khiến IdP không thấy phiên trong iframe; `IsPassive=true` không thể vượt chính sách browser.
- Nếu SP đã có phiên authenticated và user đang ở route công khai, **filter chain có thể không phát một AuthnRequest mới**, nên customizer không được chạy. Muốn test cờ phải chủ động bắt đầu một SAML login flow được phép.
- Xác thực im lặng từ IdP không bảo đảm user đã đạt mức assurance cần thiết cho hành động nhạy cảm.

Ứng dụng thường dùng chiến lược hai giai đoạn: thử passive ở một **luồng kiểm tra có kiểm soát**, nếu nhận `NoPassive` thì hiển thị lời mời để user tự khởi tạo **một request mới không passive**. Cách fallback cần xử lý response lỗi thật và tránh gây vòng lặp.

## 11. Chính sách theo tình huống: tránh bật ForceAuthn toàn ứng dụng

Trong sản phẩm thực, nên phân biệt:

- **Login mặc định:** user vào dashboard, SSO lại bằng IdP session hợp lệ.
- **Reauthentication:** user cần xác nhận danh tính trước thao tác nhạy cảm; app chủ động mở flow mới với ForceAuthn true.
- **Passive probing:** một màn hình muốn kiểm tra silent SSO; app mở flow riêng IsPassive true.
- **Step-up MFA:** điều kiện về phương thức xác thực mạnh hơn được IdP xử lý; không có bảo đảm chỉ từ ForceAuthn.

Một bảng policy rõ ràng:

| Tình huống nghiệp vụ | Cờ dự kiến | Yêu cầu bổ sung |
| --- | --- | --- |
| Vào trang học tập/portal thông thường | false / false | Session bình thường, authorization |
| Thay đổi thông tin thanh toán | true / false | Policy IdP, assurance/MFA nếu cần, xác minh sự kiện mới |
| Kiểm tra SSO không tương tác | false / true | Trả lỗi NoPassive an toàn, fallback |
| Yêu cầu fresh authentication không UI | true / true, chỉ khi đã thử IdP | Thỏa đồng thời hai điều kiện, nếu không phải thất bại |
| Người dùng yêu cầu MFA bắt buộc | Không có một cặp cờ đủ bảo đảm | RequestedAuthnContext / chính sách IdP / assertion validation |

### Không lấy cờ trực tiếp từ query do browser gửi

Ví dụ thiếu an toàn:

~~~text
GET /saml2/authenticate/corp?forceAuthn=false
~~~

Nếu server biến query này thành `ForceAuthn=false` ngay cả trong flow bắt buộc reauthentication, user/kẻ tấn công có thể hạ yêu cầu bảo mật. Ngược lại, nếu user đặt `isPassive=true` cho flow phải hiển thị MFA, trải nghiệm có thể bị lỗi. **Quyết định policy phải nằm ở server** và gắn với hành động/nguồn request/trạng thái được tin cậy.

Thiết kế khả thi:

1. Khi user bắt đầu thao tác cần step-up, server tạo **giao dịch xác thực có TTL và ràng buộc session**.
2. Server lưu lý do/đích đăng nhập/assurance yêu cầu; phát một opaque handle ngắn.
3. Chỉ server giải quyết handle đó thành policy ForceAuthn/IsPassive trong customizer.
4. Sau response, tra đúng giao dịch và xác minh kết quả thực tế trước khi cấp quyền thực hiện hành động.
5. Một giao dịch đã dùng không được replay; nếu thất bại, hiển thị tùy chọn xử lý, không tự cho phép thao tác nhạy cảm.

Đây là **mẫu kiến trúc**, không phải hành vi mặc định Spring Security tự cung cấp đầy đủ. Với ứng dụng không cần policy động, customizer tĩnh ở mục 8/10 là đủ.

## 12. SP đã có session thì ForceAuthn có được gửi không?

Một nhầm lẫn rất phổ biến: “Đặt ForceAuthn trong config thì lần nào người dùng vào `/transfer` cũng bị IdP yêu cầu xác thực lại”.

Thực tế, ForceAuthn chỉ nằm trong **AuthnRequest mới**. Nếu user đã có `SecurityContext` hợp lệ tại SP và controller/authorization cho phép request, Spring Security không nhất thiết kích hoạt SAML login. Do đó:

- Cờ ForceAuthn trong resolver **chỉ có hiệu lực khi resolver thực sự tạo AuthnRequest**.
- Một endpoint nhạy cảm không thể coi việc cấu hình cờ tĩnh là điều kiện đủ cho step-up.
- Ứng dụng phải nhận biết security level/authentication age theo policy và **chủ động khởi tạo một giao dịch SAML mới** khi cần xác thực mạnh hơn.
- SP phải tránh lặp vô hạn: sau response thành công, đánh dấu server-side rằng yêu cầu step-up vừa hoàn thành **theo chứng cứ đã xác minh** và chỉ chấp nhận trong thời gian/phạm vi policy cho phép.
- Không tự xem “đã quay lại URL thành công” là xác thực mới; bước xác minh assertion/assurance mới là điều cần đánh giá.

Lệnh truy cập trực tiếp **`/saml2/authenticate/corp`** thường khởi tạo flow theo registration; tuy nhiên hãy kiểm tra filter chain/route/security matcher của ứng dụng có cho phép request SAML start. Đừng tạo GET controller mới chỉ để phát URL có ForceAuthn.

## 13. ForceAuthn khác RequestedAuthnContext và AuthnInstant

Ba điều dưới đây phục vụ các yêu cầu khác nhau:

| Yêu cầu nghiệp vụ | Cấu trúc SAML liên quan | Điều có thể kiểm chứng |
| --- | --- | --- |
| Không chỉ dùng IdP security context trước | `AuthnRequest@ForceAuthn` | Request thực sự có cờ; IdP thực thi theo chính sách |
| Phương thức/mức xác thực cụ thể | `<RequestedAuthnContext>` (ClassRef/DeclRef, comparison) | Assertion `AuthnContext` phản ánh ngữ cảnh phù hợp nếu IdP phát và SP kiểm tra |
| Xác thực diễn ra không quá cũ | `AuthnStatement@AuthnInstant` và policy SP | Timestamp trong assertion được xác minh, so với clock server/cửa sổ cho phép |
| Xác thực không hiển thị UI | `AuthnRequest@IsPassive` | Quan sát hành vi IdP và trạng thái NoPassive nếu không thể |
| Ai được truy cập chức năng | Application authorization sau login | Vai trò/quyền theo chính sách, không suy từ ForceAuthn |

Ví dụ muốn **MFA cho phê duyệt**: đặt ForceAuthn=true có thể yêu cầu xác thực mới, nhưng bạn vẫn cần IdP hỗ trợ MFA với context tương ứng và SP **không tự cấp quyền khi assertion thiếu bằng chứng assurance mong muốn**. Một IdP có thể dùng đăng nhập lại bằng một yếu tố; như vậy ForceAuthn có thể được đáp ứng nhưng mục tiêu MFA của sản phẩm chưa đạt.

Ngược lại, `RequestedAuthnContext` không tự chứng minh người dùng vừa được xác thực tại thời điểm hiện tại. Có thể cần cả yêu cầu về context, freshness và đối chiếu chính sách IdP.

**Không sử dụng trực tiếp `AuthnInstant` như bằng chứng ký độc lập.** Nó chỉ đáng tin trong phạm vi một assertion đã được SP xác minh toàn bộ (issuer, signature, conditions, subject confirmation, audience, replay).

## 14. Khi hai cờ cùng true: quy tắc đặc biệt trong chuẩn

SAML Core có quy tắc riêng cho:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_demo-combined"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    ForceAuthn="true"
    IsPassive="true"/>
~~~

Đây là minh họa **hai thuộc tính**, chưa phải request SSO hoàn chỉnh; không gửi nó thay metadata/issuer/signature hợp lệ.

Theo chuẩn:

1. ForceAuthn yêu cầu xác thực trực tiếp, không chỉ sử dụng security context cũ.
2. IsPassive cấm tương tác UI đáng chú ý.
3. Nếu cùng true, IdP **không được thực hiện xác thực mới** khi không thể đáp ứng giới hạn IsPassive.
4. Nếu không thể thỏa, phải xử lý thất bại theo giao thức/chính sách. Không coi đây là lỗi cú pháp XML thuần.
5. Nếu IdP thực sự có một phương thức xác thực trực tiếp mà vẫn không tương tác UI và xử lý đúng chuẩn, flow có thể thành công.

**Không suy luận:** ForceAuthn true + IsPassive true = “ưu tiên ForceAuthn và bật popup”; điều đó phá ràng buộc IsPassive. Cũng không kết luận “hai cờ luôn không hợp lệ”; chuẩn đặt ra điều kiện, không cấm sự kết hợp ngay từ đầu.

## 15. IdP thực thi thế nào và giới hạn bảo đảm ở SP

Đây là trọng tâm của đề bài. Khi SP đã phát request đúng cờ, vẫn có nhiều biến ngoài tầm kiểm soát:

| Biến trong IdP / hệ thống | Điều SP không điều khiển trực tiếp | Việc SP có thể làm |
| --- | --- | --- |
| Chất lượng IdP implementation | IdP có tuân ForceAuthn/IsPassive trong từng binding không | Kiểm tra tài liệu vendor, hợp đồng, test tích hợp và audit |
| Phiên IdP | Cookie, lifetime, session policy, primary login mechanisms | Kiểm tra kỳ vọng qua kịch bản có/không có IdP session |
| Cơ chế tái xác thực | Password, passkey, certificate, MFA, token thiết bị, proxy | Yêu cầu chính sách/mức assurance và xác minh bằng chứng phù hợp |
| Browser / third-party cookie | Cookie isolation, iframe, tracking prevention, SameSite | Kiểm tra trên browser thật và top-level redirect |
| Đường chuyển qua proxy IdP | Có thực sự xác thực trực tiếp hay chỉ nhờ IdP upstream | Thỏa thuận cách IdP xử lý proxy/force authentication và kiểm tra audit |
| Response fidelity | IdP có trả AuthnContext/AuthnInstant đúng không | Chỉ tin thông tin trong assertion đã xác minh và policy |
| Status khi thất bại | IdP trả `NoPassive`, `AuthnFailed` hay lỗi vendor riêng | Phân loại error, không tạo Authentication, UX fallback an toàn |
| AuthnRequest signature | IdP có xác minh chữ ký request nếu policy yêu cầu không | Cấu hình SP signing credentials, đối chiếu IdP metadata và log test |

**Kết luận vận hành:** từ phía SP, việc thiết lập `ForceAuthn=true` là **một yêu cầu giao thức** chứ không phải một nút có thể trực tiếp bắt IdP mở MFA. Theo chuẩn, IdP phải xử lý nghĩa vụ tương ứng nếu tuân thủ, nhưng SP nên dựa vào **hợp đồng IdP + test + bằng chứng assertion + chính sách local** để quyết định có đủ điều kiện vào chức năng nhạy cảm hay không.

Với IdP có quyền cấu hình riêng, có thể có policy luôn bắt MFA khi access certain app, policy không cho silent auth, policy session-level “prompt login”, hoặc policy bỏ qua một số flag. Không mô tả các thay đổi sản phẩm cụ thể nếu chưa kiểm chứng API/version của nhà cung cấp.

## 16. Trường hợp IdP bỏ qua ForceAuthn

Giả sử SP gửi:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_request-stepup"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    ForceAuthn="true"/>
~~~

IdP lại trả SAMLResponse thành công mà không yêu cầu bất kỳ xác thực mới nào, chỉ dựa vào phiên cũ. Có thể là lỗi triển khai/chính sách IdP, hoặc cách diễn giải “fresh authentication” chưa đáp ứng kỳ vọng. SP cần xử lý theo hai lớp:

**Lớp giao thức:** kiểm tra chữ ký Response/Assertion, issuer, audience, destination, recipient, thời hạn, `InResponseTo`, chống replay. Nếu kết quả không hợp lệ, từ chối authentication.

**Lớp nghiệp vụ bảo đảm:** nếu chức năng yêu cầu reauthentication/MFA/freshness mạnh, đối chiếu assertion đã xác minh với yêu cầu (ví dụ `AuthnInstant`, `AuthnContext`, thông tin assurance theo hợp đồng IdP). Nếu thiếu bằng chứng hoặc policy không đạt, **không thực hiện hành động nhạy cảm**; tạo đường xử lý phù hợp như thông báo lỗi/khởi động flow có thể đáp ứng policy.

Không “lách” bằng cách:
- Bỏ kiểm tra assertion để “nhận kết quả thành công”.
- Chỉ đo thời gian redirect `/saml2/authenticate` và coi đó là thời điểm xác thực.
- Lấy query parameter `force=true` do browser gửi làm bằng chứng.
- Suy “IdP trả success thì ForceAuthn chắc chắn đã được thực thi đúng” khi không có chứng cứ kiểm định.

## 17. Bảo vệ AuthnRequest và tránh sửa cờ sau khi ký

Cờ nằm trong AuthnRequest; request có thể bị quan sát qua browser. Nhưng điều nguy hiểm hơn là nó bị **thay đổi** khi qua front-channel:

- Với SAML **HTTP-Redirect binding**, message thường là XML → raw DEFLATE → Base64 → URL encode. Nếu signed request, chữ ký binding kiểm tra các tham số đã encode theo chuẩn.
- Với **HTTP-POST AuthnRequest**, signature nếu có thường là XML Signature trong message trước khi Base64/form submit.
- Một attacker có thể cố thay `ForceAuthn=true` thành false để làm giảm yêu cầu bảo mật; nếu IdP không kiểm tra chữ ký request theo policy, một cờ do browser mang không thể được coi là đáng tin theo ranh giới trust nghiêm ngặt.
- Cấu hình yêu cầu ký AuthnRequest, signing certificate của SP và trust tại IdP phải khớp; không tắt signature verification để xử lý nhanh lỗi integration.

**Quan trọng:** việc Spring Security tự ký request tùy cấu hình IdP/relying party. Nếu IdP **không bắt buộc kiểm tra chữ ký**, SP không thể dùng riêng “request được tạo ở backend” để chứng minh cờ không bị chỉnh trên đường đi.

Ví dụ trong metadata IdP có `WantAuthnRequestsSigned`; ứng dụng cần đọc điều này và cung cấp SP signing credentials khi yêu cầu. SAML Response/Assertion vẫn có bước ký/xác minh riêng; request được ký không thay cho việc xác minh response.

## 18. Response thành công hay lỗi phải được xử lý thế nào?

**Trường hợp response thành công:**
1. Spring Security nhận `SAMLResponse` ở ACS.
2. Kiểm tra phiên/registration và yêu cầu đã phát theo chính sách tương quan; đừng tự nhận unsolicited response của attacker là request do browser này tạo.
3. Xác minh signature, issuer, audience, destination/recipient, thời gian hiệu lực và subject confirmation.
4. Trích thông tin về authentication context/instant khi cần cho policy bảo đảm.
5. Tạo Authentication sau khi kiểm tra giao thức thành công; authorization của route nhạy cảm vẫn cần policy đủ mạnh.

**Trường hợp passive thất bại (`NoPassive`):**
1. Không coi đó là chứng thực người dùng.
2. Đọc code/trạng thái lỗi trong response đã được xử lý an toàn; không log assertion raw.
3. Hiển thị lựa chọn tiếp tục với **interactive login** nếu sản phẩm cho phép.
4. Nếu retry, khởi tạo một AuthnRequest **mới** với `IsPassive=false`, correlation/RelayState mới.
5. Giới hạn retry và không tạo vòng lặp infinite 302.

**Trường hợp IdP trả success mặc dù không thấy tương tác UI:** không vội kết luận IdP bỏ qua ForceAuthn. Một cơ chế xác thực trực tiếp silent có thể tồn tại. Cần xem assertion, IdP audit log, policy và bằng chứng thực tế để quyết định.

## 19. Khi nào “step-up” cần nhiều hơn ForceAuthn?

**Step-up authentication** là quá trình đạt mức bảo đảm cao hơn cho một hành động hoặc bối cảnh cụ thể, ví dụ từ một yếu tố lên MFA chống phishing hoặc ràng buộc thiết bị. Nó **không trùng** với “reauthentication” mà ForceAuthn đề cập:

| Mục tiêu | ForceAuthn | Cần thêm |
| --- | --- | --- |
| Bắt IdP xác thực trực tiếp lại | Có thể sử dụng | IdP có hỗ trợ, request integrity, kiểm tra kết quả |
| MFA bắt buộc | Chưa đủ | IdP MFA policy, assertion/authn context phù hợp, audit |
| Xác thực trong 5 phút gần nhất | Chưa đủ | AuthnInstant/thời gian kiểm tra và policy |
| Phương thức phishing-resistant | Chưa đủ | AuthnContext/IdP assurance contract, bằng chứng đã xác minh |
| Xác thực không tương tác | Không phải cờ thích hợp riêng | IsPassive true và hiểu NoPassive |
| Cho phép user phê duyệt một giao dịch | Không tự quyết định | Transaction authorization, CSRF, quyền, anti-replay, audit |
| Buộc tất cả ứng dụng cùng logout | Không | SAML SLO/IdP session policy riêng |

Nếu đang thiết kế xác thực mạnh, hãy mô tả rõ:
- Cần **freshness** bao nhiêu phút?
- Cần một hay nhiều factor và loại nào?
- IdP có cung cấp ngữ cảnh xác thực có thể kiểm chứng không?
- Khi thiếu evidence, SP chặn thao tác hay cho phép fallback?
- IdP có cơ chế bypass cho thiết bị nội bộ hoặc recovery không, và chính sách đó có đáp ứng yêu cầu không?
- Browser và session SP có cho phép user tự khởi tạo lại một AuthnRequest an toàn không?

## 20. Java 17 độc lập: mô phỏng bảng quyết định, không giả mạo IdP

Chương trình dưới đây **chạy bằng JDK 17, không cần Spring**. Nó minh họa kết hợp hai cờ theo kỳ vọng logic và định danh trường hợp IdP có/không thể xác thực trực tiếp mà vẫn passive.

**Nó không phải trình thực thi SAML**. Mô hình là một mô phỏng đơn giản được lựa chọn cho mục đích học tập, **không** có chữ ký XML, session, browser hay kết luận mức bảo đảm của IdP thật.

Tệp `AuthnFlagDecisionDemo.java`:

~~~java
public final class AuthnFlagDecisionDemo {

    static String describe(
            boolean forceAuthn,
            boolean isPassive,
            boolean hasPreviousSession,
            boolean canFreshlyAuthenticatePassively) {

        if (forceAuthn && isPassive) {
            return canFreshlyAuthenticatePassively
                    ? "Fresh and passive can both be satisfied"
                    : "NoPassive: fresh silent auth is unavailable";
        }

        if (forceAuthn) {
            return "Fresh direct authentication requested";
        }

        if (isPassive) {
            return hasPreviousSession
                    ? "Passive may use existing IdP session"
                    : "NoPassive: interactive login is forbidden";
        }

        return hasPreviousSession
                ? "Normal SSO: IdP may reuse session"
                : "Normal SSO: interaction may be required";
    }

    public static void main(String[] args) {
        System.out.println(describe(false, false, true, false));
        System.out.println(describe(true, false, true, false));
        System.out.println(describe(false, true, false, false));
        System.out.println(describe(true, true, true, false));
        System.out.println(describe(true, true, true, true));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AuthnFlagDecisionDemo.java
java AuthnFlagDecisionDemo
~~~

Stdout **chính xác**:

~~~text
Normal SSO: IdP may reuse session
Fresh direct authentication requested
NoPassive: interactive login is forbidden
NoPassive: fresh silent auth is unavailable
Fresh and passive can both be satisfied
~~~

**Giải thích:**
- `hasPreviousSession` chỉ là biến mô phỏng trạng thái IdP.
- `canFreshlyAuthenticatePassively` là giả định năng lực IdP; trong triển khai thật SP không “bật” năng lực này bằng mã Java.
- Mô hình không gán `NoPassive` cho tất cả lỗi IdP; đây chỉ là đại diện trường hợp thiếu khả năng passive.
- Với `true,true`, điều kiện mới là **có khả năng xác thực trực tiếp mà không tương tác UI**. Nếu không, không được thực hiện xác thực mới phá IsPassive.
- Mã không tạo `AuthnRequest` thật. Dùng customizer Spring ở mục 8/9 để tạo XML trong ứng dụng thực.

## 21. Kiểm thử thực tế với IdP test

### Chuẩn bị

- SP Spring Security Servlet có `RelyingPartyRegistration` hợp lệ, public SP entity ID/ACS đã đăng ký phía IdP.
- Signing key/certificate của SP nếu IdP yêu cầu request ký; public verification cert IdP đã tin cậy để kiểm tra response.
- Một tài khoản kiểm thử được phép dùng trên IdP và một browser có DevTools/Network.
- Các kịch bản có IdP session và không có IdP session, có/không có phương thức silent direct authentication.
- Log IdP cho biết phương thức/sự kiện xác thực theo policy nếu được cấp quyền; tránh sao chép credential, raw assertion hoặc cookie.

### Test 1 — Mặc định false/false

1. Đăng nhập IdP trước trong trình duyệt test.
2. Bắt đầu SAML login từ SP.
3. Xác minh AuthnRequest có `ForceAuthn=false` hoặc vắng thuộc tính, `IsPassive=false` hoặc vắng.
4. Xem IdP có tái sử dụng session không và trả response hợp lệ.
5. SP vẫn phải xác minh assertion và quyền truy cập; không suy cờ false bắt buộc cho phép SSO.

### Test 2 — ForceAuthn true, IsPassive false

1. Tạo IdP session trước.
2. Bắt đầu một **AuthnRequest mới** trong SP có ForceAuthn true.
3. Capture XML outbound đã decode theo phương pháp test, xác nhận ForceAuthn đúng và request signature hợp lệ nếu dùng.
4. Quan sát IdP có thực hiện trực tiếp một sự kiện xác thực mới theo policy, chứ không chỉ redirect nhanh tới ACS.
5. Kiểm tra `AuthnInstant/AuthnContext` trong assertion **đã được xác minh** và audit phía IdP khi cần cho bằng chứng.
6. Nếu IdP bỏ qua flag mà SP vẫn hoàn thành login, không kết luận yêu cầu reauthentication đã đạt; ghi lỗi integration/policy.

### Test 3 — IsPassive true, không có phiên IdP

1. Xóa IdP session ở browser test (không thay session/credentials ngoài phạm vi).
2. Gửi AuthnRequest với `IsPassive=true`, `ForceAuthn=false`.
3. Nếu IdP không có cách passive, kỳ vọng lỗi như `NoPassive` thay vì tương tác login.
4. SP không tạo authenticated session mới từ response lỗi.
5. UI có thể cho phép user tự bấm đăng nhập theo flow interactive mới.

### Test 4 — Hai cờ cùng true

1. IdP không hỗ trợ fresh silent authentication: kỳ vọng fail, không bật form tương tác trái IsPassive.
2. Nếu IdP hỗ trợ cơ chế trực tiếp silent theo contract: có thể thành công, cần bằng chứng xác thực phù hợp.
3. Dù thành công, không suy MFA hay thời gian xác thực từ riêng cặp cờ.
4. Không vô hiệu hóa IsPassive “trong suốt quá trình” ở server mà vẫn tuyên bố giao dịch là passive.

### Test 5 — Kiểm thử an ninh

- Một người cố sửa ForceAuthn trong SAMLRequest đã ký: IdP phải từ chối signature mismatch nếu policy yêu cầu ký/kiểm tra đúng.
- Callback chứa SAMLResponse lỗi chữ ký, issuer, audience, destination/time hoặc InResponseTo: SP phải từ chối, không tạo Authentication.
- Người dùng truy cập route khi SP đã có phiên: xem resolver **có thực sự chạy không**; nếu không, cờ không thể tự kích hoạt step-up.
- IdP trả `NoPassive`: error handler không tạo redirect loop hay tự đổi policy.
- Nhiều tab/phiên: request phải gắn đúng browser/session để tránh login fixation.
- RelayState/URL đích sau login không thành open redirect.

## 22. Đọc request thực trong Developer Tools

1. Trong browser test, bật **Network → Preserve log**.
2. Mở `GET /saml2/authenticate/corp` (hoặc endpoint AuthnRequest đã cấu hình) khi được phép.
3. Xác nhận response của SP chuyển hướng tới IdP SSO endpoint; nếu dùng Redirect binding, URL có `SAMLRequest`.
4. Dùng công cụ SAML/DevTools an toàn hoặc log debug riêng trong test để giải mã request: URL decode → Base64 decode → raw DEFLATE inflate. **Không cần tự ghi một servlet endpoint nhận dữ liệu production để debug**.
5. Xem phần tử `<samlp:AuthnRequest>` có `ForceAuthn="true"`, `IsPassive="true/false"` theo kịch bản.
6. Kiểm tra request có đúng issuer/entity ID, Destination, ACS, binding, signature, RelayState và request ID.
7. Quan sát sau request: IdP tương tác UI hay phát SAMLResponse success/error, status code nào.
8. Xem ACS, cookie/session và correlation; so thông tin `AuthnInstant/AuthnContext` đã xác minh nếu policy yêu cầu.
9. Ghi lại **dữ liệu đã redact**: flags, timestamps, status, issuer phù hợp, test scenario; không xuất raw SAML assertions, session cookie, ký private hoặc dữ liệu cá nhân vào issue công khai.

**Lưu ý:** browser request đến IdP có thể dùng POST AuthnRequest trong cấu hình khác; khi đó `SAMLRequest` nằm trong HTML form field Base64, không dùng bước DEFLATE của Redirect. Cờ vẫn nằm trong XML.

## 23. Lỗi phổ biến và chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Đã viết customizer nhưng AuthnRequest không có cờ | Resolver không được bean wiring, request không khởi tạo, bean khác ghi đè | Xem registered bean, filter chain, đúng endpoint/version; decode XML thực |
| `ClassNotFoundException: OpenSaml5...` | Dùng tài liệu API 7.x trên dependency 6.x cũ | Đối chiếu Spring Security/OpenSAML version, chọn resolver tương thích |
| Cờ ForceAuthn true nhưng không có màn hình nhập lại password | IdP dùng cơ chế khác, bỏ qua flag hoặc có fresh passive method | Kiểm tra IdP policy/audit, assertion AuthnInstant/Context; không suy chỉ từ UI |
| User bị yêu cầu login ở mọi lần vào app | ForceAuthn true cho mọi AuthnRequest | Xem policy: chỉ áp dụng ở flow reauthentication có chủ đích |
| Route nhạy cảm vẫn vào được không reauth | SP session đã có, không tạo AuthnRequest mới | Thiết kế step-up flow, đánh dấu trạng thái freshness đáng tin ở SP |
| IsPassive true nhưng IdP hiển thị form | IdP không hỗ trợ/không tuân hoặc cấu hình sai | Xem request XML, IdP behavior, báo lỗi contract; không tuyên bố passive thành công |
| IsPassive true luôn trả NoPassive | Không có IdP session phù hợp/cookie bị chặn | Test top-level/iframe, cookie policy, capability của IdP |
| ForceAuthn + IsPassive true thất bại | IdP không thể xác thực mới mà giữ passive | Đây có thể là kết quả đúng chuẩn; thay đổi yêu cầu nghiệp vụ/UX |
| IdP trả lỗi ký request | Signing key/algorithm/query signature sai | Kiểm tra IdP metadata, SP key, binding Redirect/POST |
| IdP trả AuthnFailed | Người dùng không xác thực được theo policy | Xử lý như lỗi đăng nhập, không tạo Authentication |
| SP trả 403 ở ACS | CSRF/filter chain hoặc SAML validation lỗi | Phân loại server error và request method; không tắt CSRF toàn cục |
| Error handler loop sau NoPassive | Tự retry cùng IsPassive request | Dừng retry, cung cấp lựa chọn interactive chủ động |
| Assertion hợp lệ nhưng freshness không đạt | IdP assertion/contract không đáp ứng policy | Chặn tác vụ nhạy cảm, yêu cầu IdP/assurance phù hợp |
| InResponseTo mismatch | Mất AuthnRequest/cookie session hoặc request sai | Kiểm tra session repository, SameSite trên cross-site POST |
| Proxy làm sai ACS/issuer | Public base URL/forwarded headers không khớp | Cấu hình proxy tin cậy, metadata và entity ID |
| Team tin ForceAuthn là MFA | Hiểu sai nghĩa giao thức | Tách reauthentication, assurance, MFA và quyền nghiệp vụ |

## 24. Tình huống thực tế: phê duyệt thanh toán

Giả sử user đã đăng nhập và đang xem màn hình **phê duyệt thanh toán 100 triệu đồng**.

**Yêu cầu sản phẩm:** trước khi xác nhận lệnh, người dùng phải trải qua một phương thức xác thực có mức bảo đảm được phê duyệt trong thời gian gần đây. Chỉ bật `ForceAuthn=true` trong mọi lần SAML login là chưa đủ vì:
1. Khi user đã authenticated tại SP, lệnh `POST /payments/approve` có thể chạy mà không phát một AuthnRequest mới.
2. ForceAuthn không mô tả cấp độ MFA.
3. Một IdP có thể không cung cấp assurance/freshness evidence đủ chi tiết.
4. Session SP có thể tồn tại sau khi verification cũ hết hạn theo policy nghiệp vụ.

**Thiết kế hợp lý:**
- SP chặn phê duyệt nếu chưa đạt step-up policy.
- SP tạo một giao dịch step-up server-side, redirect khởi tạo AuthnRequest ForceAuthn true (và IsPassive false nếu cần tương tác).
- IdP thực thi policy xác thực mới và mức assurance đã thỏa thuận.
- SP xác minh assertion, nhận diện user, AuthnInstant/AuthnContext theo policy và ràng buộc đúng giao dịch.
- Nếu đạt, SP đánh dấu **step-up đã xác minh** gắn user/session/transaction với TTL ngắn. Nếu không đạt hoặc IdP bỏ qua yêu cầu, **chặn phê duyệt**.
- Khi người dùng xác nhận thao tác cuối, application authorization/CSRF/transaction integrity vẫn được kiểm tra.
- Audit ghi thời điểm/assurance và quyết định cấp quyền, không lưu raw assertion hoặc khóa riêng.

Đây là ví dụ thiết kế chính sách; không nên dùng RelayState hay ForceAuthn như “chữ ký giao dịch” tự thân.

## 25. Bài tập tự kiểm tra kèm đáp án

**Bài 1.** Người dùng đã đăng nhập IdP và SP muốn IdP **không chỉ dựa vào phiên cũ**, có thể yêu cầu tương tác. Cặp flag nào phù hợp?

**Đáp án:** `ForceAuthn=true, IsPassive=false`. Vẫn cần IdP hỗ trợ và test thực thi, không đồng nghĩa bắt MFA.

**Bài 2.** SP muốn kiểm tra IdP có thể xác thực im lặng, không có IdP session và IdP không hỗ trợ silent authentication. Nếu `IsPassive=true`, hành vi mong đợi là gì?

**Đáp án:** không hiển thị form tương tác trái yêu cầu; IdP nên trả lỗi như `NoPassive`. SP không tạo phiên mới từ lỗi và có thể mời user chủ động khởi tạo login tương tác.

**Bài 3.** Cùng bật ForceAuthn/IsPassive có làm request sai chuẩn ngay từ khi tạo XML không?

**Đáp án:** không. Theo SAML Core, chỉ được xác thực trực tiếp mới nếu vẫn đáp ứng ràng buộc passive; nếu không, IdP không được làm việc đó theo cách phá IsPassive và phải xử lý thất bại phù hợp.

**Bài 4.** Một ứng dụng đặt ForceAuthn=true trong customizer, nhưng user đang có session SP và vào được trang được bảo vệ ngay. Đây có phải IdP đã bỏ qua ForceAuthn?

**Đáp án:** chưa chắc; có thể SP **không tạo AuthnRequest mới**. Cần xác định có request SAML thực sự được phát hay không, rồi mới đánh giá IdP.

**Bài 5.** IdP trả Response thành công; nhóm phát triển kết luận đã có MFA vì request có ForceAuthn=true. Kết luận sai ở đâu?

**Đáp án:** ForceAuthn là yêu cầu xác thực trực tiếp, **không phải khai báo số yếu tố hoặc phương thức**. Cần IdP assurance policy và bằng chứng phù hợp trong assertion đã được xác minh.

**Bài 6.** IdP gửi response có `NoPassive`. Có nên bỏ qua lỗi và giữ phiên authenticated mới?

**Đáp án:** không. Đây là thất bại xác thực passive; phải giữ nguyên ranh giới trust và dùng fallback interactive do người dùng khởi tạo nếu được phép.

**Bài 7.** ForceAuthn=true nhưng kẻ tấn công thay cờ thành false trên URL. Có biện pháp gì?

**Đáp án:** ký `AuthnRequest` theo binding và yêu cầu IdP kiểm tra chữ ký/đúng SP; giữ policy server-side và kiểm tra kết quả. HTTPS không tự đảm bảo tính toàn vẹn dữ liệu mà browser có thể thay đổi.

**Bài 8.** Với IsPassive=true, browser vẫn thấy 302 qua IdP. Điều này tự chứng minh IdP vi phạm chuẩn không?

**Đáp án:** không. Front-channel redirect và “tương tác giao diện đáng chú ý” là các khái niệm khác nhau. Cần quan sát IdP/UX và profile.

**Bài 9.** Hãy chỉ ra đúng chỗ cần đổi cờ trong Spring Security 6.x Servlet.

**Đáp án:** tùy chỉnh OpenSAML `AuthnRequest` qua `OpenSaml4AuthenticationRequestResolver#setAuthnRequestCustomizer` trên bean `Saml2AuthenticationRequestResolver` (hoặc resolver 5 nếu stack/version hỗ trợ).

**Bài 10.** IdP nói không hỗ trợ ForceAuthn; SP vẫn cần reauthentication mạnh. Lựa chọn nào có trách nhiệm?

**Đáp án:** thay đổi hợp đồng/tính năng IdP, dùng cơ chế/endpoint/policy khác được hỗ trợ và kiểm chứng, hoặc chặn tính năng cần assurance. Không tự “giả vờ thành công” bằng cách thấy SAMLResponse hợp lệ.

## 26. Checklist triển khai

- [ ] Xác định rõ use case: login bình thường, reauthentication, passive probing hay step-up assurance.
- [ ] Biết ForceAuthn và IsPassive là **thuộc tính trên AuthnRequest**, mỗi thuộc tính mặc định false khi vắng.
- [ ] Có chính sách rõ cho bốn kết hợp, đặc biệt ForceAuthn=true + IsPassive=true.
- [ ] Spring Security resolver tương ứng version OpenSAML được đăng ký, không xung đột bean khác.
- [ ] Đã giải mã AuthnRequest test và xác nhận cờ thực sự được đưa ra wire.
- [ ] Có SP signing key/đúng request signature nếu IdP yêu cầu hoặc nếu integrity là ràng buộc quan trọng.
- [ ] IdP đã công bố khả năng hỗ trợ flag, binding, phương thức tương tác và xử lý NoPassive.
- [ ] Không lấy policy ForceAuthn/IsPassive từ query parameter do user tùy ý sửa.
- [ ] Nếu cần MFA, có RequestedAuthnContext/IdP policy và kiểm tra AuthnContext đáng tin.
- [ ] Nếu cần freshness, có tiêu chí AuthnInstant/TTL và bước đánh giá assertion đã xác minh.
- [ ] Nếu dùng step-up, SP **chủ động phát AuthnRequest mới** khi cần; không dựa vào session hiện có để tự kích hoạt.
- [ ] Callback/ACS giữ signature, issuer, audience, destination, thời gian, InResponseTo và replay protection.
- [ ] NoPassive/AuthnFailed được phân loại, không có redirect loop hoặc bypass policy.
- [ ] Test có IdP session, không có session, browser cookie hạn chế, nhiều tab, proxy và request signed/unsigned.
- [ ] Không ghi raw SAMLResponse, cookie, RelayState thực, private key hay dữ liệu nhạy cảm vào log/HAR.

## 27. Tổng kết kỹ thuật

**ForceAuthn là lời yêu cầu IdP xác thực trực tiếp thay vì dựa riêng vào security context trước; IsPassive là lời yêu cầu không tương tác UI đáng chú ý.** Nếu cùng true, IdP chỉ có thể xác thực mới nếu vẫn đáp ứng tính passive. SP tạo đúng XML nhờ `Saml2AuthenticationRequestResolver`, còn IdP chịu trách nhiệm xử lý theo chuẩn/chính sách. Với các yêu cầu rủi ro cao, đừng chỉ nhìn hai Boolean để kết luận đã có MFA, xác thực mới đủ mạnh hay quyền thực hiện giao dịch.

### Tài liệu chính thức để đối chiếu

- OASIS — *Assertions and Protocols for the OASIS Security Assertion Markup Language (SAML) V2.0*, mục 3.4.1 (ForceAuthn, IsPassive) và StatusCode: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- Spring Security 6.5 — Producing AuthnRequests, OpenSaml4AuthenticationRequestResolver customizer: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html
- Spring Security 7.0 — Producing AuthnRequests, OpenSaml5AuthenticationRequestResolver customizer: https://docs.spring.io/spring-security/reference/7.0/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses (Servlet): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Microsoft Entra ID — SAML SSO protocol, ForceAuthn and IsPassive behavior on one vendor: https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol
