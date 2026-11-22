# HTTP-Redirect, HTTP-POST và giới hạn các binding được hỗ trợ trong SAML 2.0

## 1. Mục tiêu và bối cảnh

**Binding** trong SAML 2.0 là quy tắc đóng gói và vận chuyển một thông điệp giao thức SAML qua phương tiện giao tiếp cụ thể. Đối với Web Browser Single Sign-On (SSO), hai binding thường gặp nhất là **HTTP-Redirect** và **HTTP-POST**. Cùng là SAML 2.0 nhưng chúng khác nhau về HTTP method, nơi đặt dữ liệu, cách mã hóa, kiểu chữ ký và những giới hạn có thể gặp trên trình duyệt/proxy.

Bài học nằm trong ngữ cảnh **Spring Security - federation**, mô hình **SAML 2.0**, tập trung vào chức năng **Service Provider (SP), còn gọi Relying Party (RP)** của thư viện `spring-security-saml2-service-provider` trên Servlet stack. IdP (Identity Provider, còn gọi Asserting Party) chịu trách nhiệm xác thực người dùng và phát hành phản hồi. Browser chuyển tiếp thông điệp ở front-channel, còn Spring Security xác minh phản hồi và thiết lập `Authentication`.

Sau bài học, người học có thể:

- Phân biệt **SAML protocol**, **SAML profile** và **SAML binding**; hiểu một luồng đăng nhập có thể kết hợp hai binding khác nhau.
- Giải thích HTTP-Redirect nén, mã hóa và đưa `SAMLRequest` lên query string; HTTP-POST Base64 message vào form và gửi qua request body.
- Đọc đúng `AuthnRequest`, `SAMLResponse`, `RelayState`, `SigAlg`, `Signature` cùng các URL SSO/ACS.
- Xác định rõ binding nào Spring Security SP hỗ trợ khi **gửi AuthnRequest**, khi **nhận Response**, và những binding không có sẵn.
- Chẩn đoán lỗi do binding, metadata, chữ ký, cookie, endpoint, giới hạn URL hoặc cấu hình IdP không khớp.
- Kiểm tra SSO theo từng HTTP hop mà không nhầm browser redirect với back-channel hay tắt các kiểm tra bảo mật.

Các host có hậu tố `.example.org` chỉ là ví dụ; không tồn tại IdP thực để tự đăng nhập.

## 2. Binding khác profile và protocol như thế nào?

| Khái niệm | Trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| **Protocol** | Các thông điệp nói gì và có quan hệ gì? | `AuthnRequest`, `Response`, `LogoutRequest`, `Assertion`, `InResponseTo` |
| **Profile** | Dùng các giao thức/binding theo trình tự nào cho tình huống sử dụng? | SAML 2.0 **Web Browser SSO Profile** |
| **Binding** | Một message SAML đi qua HTTP hay phương tiện khác như thế nào? | HTTP-Redirect, HTTP-POST, HTTP-Artifact, SOAP, PAOS |

Đừng gọi mọi HTTP 302 là “SAML HTTP-Redirect binding”. Một ứng dụng có thể 302 từ trang bảo vệ tới endpoint Spring `/saml2/authenticate/corp`; đó là redirect ứng dụng thông thường. **SAML HTTP-Redirect binding** là hop mà URL đến IdP chứa thông điệp giao thức đã encode trong `SAMLRequest`.

Một luồng **SP-initiated Web SSO** điển hình:

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Spring Security SP
    participant IDP as SAML IdP
    U->>SP: GET /private
    SP-->>U: 302 đến /saml2/authenticate/corp
    U->>SP: GET /saml2/authenticate/corp
    SP-->>U: 302 Location: IdP?SAMLRequest=... (HTTP-Redirect binding)
    U->>IDP: GET /sso?SAMLRequest=...&RelayState=...
    IDP-->>U: Login/MFA hoặc dùng phiên IdP
    IDP-->>U: HTML form với SAMLResponse (HTTP-POST binding)
    U->>SP: POST /login/saml2/sso/corp
    SP->>SP: Verify SAML và tương quan request
    SP-->>U: Set-Cookie phiên SP; redirect tài nguyên
    U->>SP: GET /private + cookie SP
~~~

Ở ví dụ này **lượt đi là HTTP-Redirect, lượt về là HTTP-POST**. Việc hai chiều có binding khác nhau là bình thường, không phải cấu hình sai. Một IdP khác có thể yêu cầu **POST AuthnRequest** thay vì Redirect, nhưng SAMLResponse vẫn thường POST về ACS.

## 3. HTTP-Redirect binding: thông điệp nằm trong URL

Tên binding chuẩn:

`urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect`

Nó thường được dùng cho **SP gửi AuthnRequest đến IdP** theo top-level GET. Các bước đóng gói theo SAML 2.0 HTTP-Redirect binding:

1. Tạo XML SAML message (ví dụ `<samlp:AuthnRequest>`) và xác định SSO destination.
2. Serialize message thành byte XML theo encoding thích hợp.
3. **DEFLATE raw** các byte XML, thông thường không dùng wrapper zlib/gzip. Chú ý `java.util.zip.Deflater(..., true)`: cờ `true` có nghĩa dùng raw DEFLATE.
4. **Base64** byte nén.
5. **URL-percent-encode** Base64 để đưa an toàn vào giá trị query parameter.
6. Dựng URL tới endpoint IdP cùng tham số **`SAMLRequest`** (hoặc `SAMLResponse` đối với message loại khác trong định nghĩa binding, song phần login response của Spring Security **không hỗ trợ** Redirect).
7. Nếu có, đính **`RelayState`** như một query parameter riêng. Nếu ký Redirect binding, thêm **`SigAlg`** và **`Signature`** theo quy tắc ký chuỗi query của binding.
8. SP gửi HTTP response có `Location`; **browser** theo redirect và tạo một GET mới tới IdP.

HTTP ví dụ đã rút gọn:

~~~http
GET /saml2/authenticate/corp HTTP/1.1
Host: app.example.org

HTTP/1.1 302 Found
Location: https://idp.example.org/sso?SAMLRequest=fZH...%3D&RelayState=r-123&SigAlg=...&Signature=...
~~~

Browser tiếp tục:

~~~http
GET /sso?SAMLRequest=fZH...%3D&RelayState=r-123&SigAlg=...&Signature=... HTTP/1.1
Host: idp.example.org
~~~

Các giá trị `fZH...`, `r-123`, `...` chỉ minh họa hình dạng, **không phải SAML message hay chữ ký hợp lệ**.

### Chữ ký của HTTP-Redirect nằm ở đâu?

Với kiểu ký Redirect binding thông dụng, bên gửi ký **chuỗi query đã encode**, theo thứ tự và phần tham số do đặc tả quy định:

~~~text
SAMLRequest=<url-encoded-value>&RelayState=<url-encoded-value>&SigAlg=<url-encoded-algorithm>
~~~

Nếu không có `RelayState`, bỏ hoàn toàn đoạn `&RelayState=...` khi dựng chuỗi ký. Với message là SAMLResponse thì tên tham số trong công thức binding đổi tương ứng, nhưng **đừng hiểu điều đó là Spring Security Web Browser SSO cho phép nhận response Redirect**. Giá trị `Signature` là Base64 của chữ ký số rồi được URL-encode; `SigAlg` xác định thuật toán chữ ký. Không đổi thứ tự tham số đã ký, không ký một bản XML đã pretty-print lại, và không so sánh chữ ký với string chưa percent-encode.

**Điểm tinh tế:** chữ ký của binding trên query khác với **XML Digital Signature** (`<ds:Signature>`) nằm bên trong XML. Spring Security có mô tả biến thể Redirect với XML signature trong phạm vi API, nhưng không nên mặc định mọi IdP hỗ trợ biến thể đó. Với tích hợp thực tế, cần dựa vào metadata và hướng dẫn của IdP/SP để chọn cách ký đúng.

### Giới hạn vận hành của Redirect

- **URL có giới hạn thực tế** qua browser, proxy, WAF, gateway, log infrastructure và IdP; không có một mức “2.048 ký tự” áp dụng cho mọi hạ tầng. Request quá dài có thể nhận 414 URI Too Long, 400 hoặc bị cắt/chặn.
- URL thường xuất hiện trong **lịch sử, access log, tracing hoặc công cụ giám sát**; không đưa mật khẩu, private key hay token dài hạn vào query.
- **DEFLATE giảm kích thước**, không mã hóa hay bảo vệ bí mật; Base64 chỉ encoding, HTTPS chỉ bảo vệ truyền tải, và kiểm tra chữ ký/xác thực đối tác vẫn cần trên server.
- Khác biệt cách dùng DEFLATE wrapper, escape ký tự `+`/`%2B`, `%2F`, `%3D`, thuật toán chữ ký hoặc canonicalization có thể khiến IdP từ chối.
- Nếu XML AuthnRequest có nhiều extension, yêu cầu ký/định danh phức tạp hay policy làm URL quá dài, IdP có thể ưu tiên **HTTP-POST AuthnRequest**.
- HTTP-Redirect thường phù hợp với **request** có kích thước nhỏ, không phù hợp để chuyển assertion/response kích thước lớn như một URL login thông thường.

Các query parameter khác đã có trên SSO URL phải được xử lý cẩn thận; đừng tự ghép chuỗi hay ký sai phạm vi query.

## 4. HTTP-POST binding: thông điệp nằm trong HTML form

Tên binding chuẩn:

`urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST`

Thông điệp SAML được serialize thành XML, **Base64-encode trực tiếp** (không mặc định DEFLATE như Redirect) rồi đưa vào hidden input của HTML form. Browser submit form đến địa chỉ trong `action` bằng HTTP POST, thông thường `Content-Type: application/x-www-form-urlencoded`. Browser có thể tự submit bằng script hoặc người dùng bấm nút fallback.

Ví dụ phản hồi từ IdP tới SP:

~~~html
<!doctype html>
<html lang="en">
  <body>
    <form id="saml-post" method="post"
          action="https://app.example.org/login/saml2/sso/corp">
      <input type="hidden" name="SAMLResponse"
             value="BASE64_ENCODED_SAML_RESPONSE">
      <input type="hidden" name="RelayState" value="request-correlation">
      <noscript><button type="submit">Continue</button></noscript>
    </form>
    <script>
      document.getElementById("saml-post").submit();
    </script>
  </body>
</html>
~~~

Ở hệ thống thật, `SAMLResponse` có thể chứa assertion/thuộc tính người dùng nhạy cảm; ví dụ trên **không chứa message thật**. `RelayState` có thể có hoặc không và thường được chuyển tiếp từ giao dịch ban đầu.

Sau submit, HTTP request về ACS có hình dạng:

~~~http
POST /login/saml2/sso/corp HTTP/1.1
Host: app.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=PHNhbWxwOlJlc3BvbnNlLi4u&RelayState=request-correlation
~~~

Ở POST binding:
- Dữ liệu chính nằm trong **body**; browser tạo request thật, không phải IdP backend trực tiếp gọi ACS trong front-channel phổ biến.
- **XML Signature**, khi có, thường nằm trong XML SAML Response hoặc Assertion (`<ds:Signature>`), khác chữ ký query của Redirect. SP phải kiểm tra đúng phần ký và điều kiện protocol.
- **Base64 không phải mã hóa bảo mật**. Body có thể bị thu thập bởi DevTools, proxy gỡ TLS, logging middleware, HAR hoặc extension; không xuất toàn bộ body vào log sản xuất.
- Việc không nằm trong URL giảm rủi ro URL quá dài và rò rỉ do URL log, **không khiến POST mặc nhiên đáng tin hay được mã hóa**.
- CORS của JavaScript `fetch()` khác với **top-level HTML form navigation**. Thêm header CORS thường không giải quyết lỗi SAML ACS POST hay cookie SameSite.

HTTP-POST cũng có thể dùng để **SP gửi AuthnRequest tới IdP** nếu metadata IdP, cấu hình RP và triển khai hỗ trợ. Khi đó trường form là `SAMLRequest` và form `action` là SSO endpoint của IdP; response về SP vẫn dùng `SAMLResponse`.

## 5. Cách chọn binding theo hướng, message và sản phẩm Spring Security

Đây là phần cần phân biệt rõ nhất. **SAML 2.0 là đặc tả rộng; Spring Security SAML 2.0 Service Provider hiện đại chỉ triển khai một phạm vi cụ thể.**

| Luồng / message | Binding | Spring Security SAML 2.0 SP (Servlet) | Ghi chú |
| --- | --- | --- | --- |
| SP → IdP: `AuthnRequest` | **HTTP-Redirect** | **Hỗ trợ; thông dụng/mặc định** | Browser GET tới IdP với `SAMLRequest` |
| SP → IdP: `AuthnRequest` | **HTTP-POST** | **Hỗ trợ khi cấu hình** | Browser POST HTML form tới SSO endpoint IdP; IdP cần công bố/hỗ trợ POST |
| IdP → SP: SAML **Response** cho Web SSO | **HTTP-POST** | **Hỗ trợ; luồng login mặc định** | Browser POST `SAMLResponse` về ACS |
| IdP → SP: SAML **Response** qua GET Redirect | **HTTP-Redirect** | **Không hỗ trợ trong Spring Security Web SSO login chuẩn** | Không đổi ACS sang GET để “bắt” response |
| Web SSO dùng HTTP-Artifact và ArtifactResolve | **HTTP-Artifact/SOAP** | **Không có sẵn trong module hiện đại theo tài liệu migration** | Đòi kiến trúc phân giải artifact back-channel riêng hoặc sản phẩm khác |
| SOAP / PAOS / ECP / các profile khác | Tùy giao thức | **Không mặc định là chức năng của `saml2Login()`** | Phải tra tính năng/version cụ thể, không suy từ OpenSAML đã có trên classpath |
| SAML Single Logout | Redirect và/hoặc POST theo config | Có hỗ trợ SLO trong các bản Spring Security phù hợp | **Khác Web SSO login**; cần xét request/response logout riêng, không suy binding login từ logout |

**Lưu ý về version:** ví dụ và phạm vi trong bài áp dụng Spring Security 6.x/7.x Servlet hiện đại, đối chiếu tài liệu cùng phiên bản đang dùng. Tài liệu Spring Security migration nêu rõ **HTTP-Redirect binding cho SAML 2.0 Response và HTTP-Artifact binding là các tính năng chưa được chuyển sang module mới**. Trong tương lai một bản có thể thay đổi nên kiểm tra release note, nhưng đừng suy rằng có `Saml2MessageBinding.REDIRECT` thì bộ lọc SP nhận mọi Response qua GET.

**Khác biệt với sản phẩm cũ:** `Spring Security SAML Extension 1.x` trước đây có phạm vi rộng hơn (HTTP-POST, Redirect, SOAP, PAOS, Artifact...). Nó là integration khác, không phải bằng chứng rằng `spring-security-saml2-service-provider` hiện đại tự động hỗ trợ các binding tương tự. Không trộn filter, endpoint và metadata cũ vào chain mới.

### Bốn câu hỏi bắt buộc trước khi chọn binding

1. Đang vận chuyển **AuthnRequest, Response, LogoutRequest hay một artifact**?
2. Message đi **SP → IdP** hay **IdP → SP**?
3. Đây là **Web Browser SSO profile** hay một profile khác?
4. **Hai phía cùng version/cấu hình** có hỗ trợ binding và URL endpoint tương ứng trong metadata không?

Câu trả lời “hỗ trợ HTTP-POST” là chưa đủ nếu không ghi rõ **POST gì, về đâu**.

## 6. Metadata quyết định endpoint và binding có thể dùng

Các entity trong federation trao đổi metadata XML có các service element gắn `Binding` và `Location`.

**IdP metadata** có thể công bố nhiều SingleSignOnService:

~~~xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.org/sso/redirect"/>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://idp.example.org/sso/post"/>
</md:IDPSSODescriptor>
~~~

Đây là **trích đoạn minh họa**; metadata hoàn chỉnh cần `EntityDescriptor`, entity ID, key descriptors/chữ ký và các thành phần theo yêu cầu. URL POST/Redirect chỉ là ví dụ, nhiều IdP có thể dùng cùng một URL cho nhiều binding.

**SP metadata** công bố ACS cho response:

~~~xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://app.example.org/login/saml2/sso/corp"
      index="0" isDefault="true"/>
</md:SPSSODescriptor>
~~~

Cần đọc đúng thuộc tính:

- `SingleSignOnService@Binding` cho biết **IdP nhận AuthnRequest bằng binding nào** tại `Location` nào. Đây không phải ACS.
- `AssertionConsumerService@Binding` cho biết **SP nhận Response bằng binding nào** tại ACS `Location` nào.
- `AuthnRequest@ProtocolBinding` có thể thể hiện binding mà SP mong muốn cho Response theo profile/cấu hình; không được lẫn với binding dùng để gửi **chính AuthnRequest**.
- `AuthnRequest@Destination` nên chỉ tới SSO endpoint IdP; `Response@Destination` và `SubjectConfirmationData@Recipient` phải tương ứng ACS SP theo điều kiện được xác minh.
- `entityID` xác định entity về logic và không nhất thiết là URL endpoint; không thay entity ID bằng redirect URI tùy tiện.
- `registrationId=corp` là định danh cục bộ của Spring, giúp tìm `RelyingPartyRegistration`; giá trị này không mặc nhiên bằng SAML entity ID.

Một metadata IdP có Redirect và POST **không có nghĩa** Spring sẽ tự nhận POST response/GET response theo một cách linh hoạt bất kể SP metadata. Phải kiểm tra đường **đi và về** được thống nhất giữa hai phía.

## 7. Spring Security thực hiện các binding này ở đâu?

Trong ứng dụng Spring Boot Servlet có `spring-security-saml2-service-provider`, `RelyingPartyRegistrationRepository` và `saml2Login()`:

- `Saml2WebSsoAuthenticationRequestFilter` xử lý request khởi tạo đăng nhập tại `/saml2/authenticate/{registrationId}`, tạo `AuthnRequest`, lưu thông tin tương quan và đưa sang IdP bằng binding tương ứng.
- `Saml2WebSsoAuthenticationFilter` xử lý POST đến ACS mặc định `/login/saml2/sso/{registrationId}`, lấy `SAMLResponse` và dựa vào registration để xác minh.
- Các class OpenSAML provider của Spring Security thực hiện parse, xác minh điều kiện và xây dựng kết quả xác thực. Tên lớp/provider có thể thay đổi theo phiên bản.
- `RelyingPartyRegistration` giữ metadata phía SP và IdP, gồm SSO endpoint/binding phía IdP, ACS location và signing/verification credentials.

Một đoạn cấu hình Servlet điển hình trong dự án Spring Boot có dependency và registration:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Đoạn Java này **là lớp Spring configuration**, không phải chương trình độc lập để chạy với `javac SamlSecurityConfig.java` ngoài dự án. Nó dùng Spring Security 6.x/7.x API phổ biến; dự án phải có JDK theo yêu cầu Spring Boot, dependency SAML SP, metadata/registration hợp lệ và main application. Không có stdout cố định; quan sát HTTP redirect và session khi runtime.

### Lấy binding từ metadata IdP

Trong triển khai dùng metadata:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
~~~

Đây là **một phương án cấu hình hoàn chỉnh về mặt đường dẫn metadata**, nhưng cần file `src/main/resources/saml/corp-idp.xml` thật do IdP cung cấp và đăng ký SP phía IdP. Khi parse metadata, Spring Security chọn thông tin SSO service/binding theo cách API và phiên bản hỗ trợ; đừng đoán rằng chỉ vì XML có POST thì runtime chắc chắn chọn POST nếu cấu hình khác đã override.

### Yêu cầu POST AuthnRequest

Với Spring Security hiện đại cung cấp API `AssertingPartyMetadata.Builder`, có thể lựa chọn POST ở `RelyingPartyRegistration`. Đoạn **Java minh họa trong dự án Spring (cần metadata thật và API phù hợp version)**:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.registration.Saml2MessageBinding;

@Configuration
public class SamlPostRequestConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration registration = RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/corp-idp.xml")
                .registrationId("corp")
                .assertingPartyMetadata(party ->
                        party.singleSignOnServiceBinding(Saml2MessageBinding.POST))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

- Dòng `singleSignOnServiceBinding(Saml2MessageBinding.POST)` đổi **binding gửi AuthnRequest tới IdP**, không đổi binding nhận SAMLResponse tại ACS.
- IdP metadata phải có SSO endpoint hỗ trợ POST; nếu chỉ công bố Redirect, việc ép POST không bảo đảm khả năng tương tác.
- Khi tự cung cấp `RelyingPartyRegistrationRepository`, cần hiểu quy tắc auto-configuration của Boot; tránh tạo hai registration khác nhau cùng ID.
- Đối chiếu signature yêu cầu: Redirect binding thường ký trên query; POST binding thường ký XML message. Nếu IdP đòi signed AuthnRequest, SP phải có **signing private key + certificate**, và bên nhận phải có thông tin công khai để xác minh.
- Builder API có thể đổi giữa Spring Security 6.x và 7.x; theo tài liệu version cụ thể trước khi copy.

**Không nên tự viết controller nhận SAMLResponse bằng GET** hoặc chỉnh Spring filter matcher để lách giới hạn. Việc đó tạo một đường xử lý khác chuẩn, chưa được tích hợp đầy đủ validation.

## 8. Ví dụ Java 17 tự chạy: cơ chế encode/decode cho Redirect

Để thấy “DEFLATE → Base64 → URL-encode” thực sự là ba bước khác nhau, chương trình dưới đây chỉ dùng **Java Standard Library**. Nó thực hiện round-trip trên một chuỗi XML tối giản để minh họa **cơ chế truyền tải**, không tạo SAML AuthnRequest hợp lệ, không ký XML và **không phải cách tự triển khai SAML production**.

Tệp `SamlRedirectCodecDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.zip.Deflater;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.Inflater;
import java.util.zip.InflaterInputStream;

public class SamlRedirectCodecDemo {
    public static void main(String[] args) throws Exception {
        String xml = "<AuthnRequest ID=\"demo-1\"/>";

        ByteArrayOutputStream compressedOut = new ByteArrayOutputStream();
        try (DeflaterOutputStream stream = new DeflaterOutputStream(
                compressedOut, new Deflater(Deflater.DEFAULT_COMPRESSION, true))) {
            stream.write(xml.getBytes(StandardCharsets.UTF_8));
        }

        String base64 = Base64.getEncoder().encodeToString(compressedOut.toByteArray());
        String queryValue = URLEncoder.encode(base64, StandardCharsets.UTF_8);

        String decodedBase64 = URLDecoder.decode(queryValue, StandardCharsets.UTF_8);
        byte[] compressed = Base64.getDecoder().decode(decodedBase64);

        String restored;
        try (InflaterInputStream stream = new InflaterInputStream(
                new ByteArrayInputStream(compressed), new Inflater(true))) {
            restored = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        }

        System.out.println("Round-trip matches: " + xml.equals(restored));
        System.out.println("Query value exists: " + !queryValue.isBlank());
    }
}
~~~

Biên dịch và chạy bằng Java 17+ trong thư mục chứa file:

~~~bash
javac SamlRedirectCodecDemo.java
java SamlRedirectCodecDemo
~~~

Stdout chính xác:

~~~text
Round-trip matches: true
Query value exists: true
~~~

Ý nghĩa: `Deflater(..., true)` dùng raw DEFLATE; `Base64` tạo văn bản biểu diễn byte; `URLEncoder` bảo vệ ký tự đặc biệt trong query value; khi decode phải đảo ngược thứ tự. **Không dùng đoạn demo để thay OpenSAML**, vì nó thiếu SAML protocol namespace, chữ ký, metadata, issuer, destination, replay protection và policy IdP.

Nếu minh họa POST, chỉ cần Base64 XML, đặt vào form field; **không dùng raw DEFLATE** như Redirect.

## 9. RelayState: giá trị đi kèm message nhưng không phải chữ ký

`RelayState` cho phép chuyển trạng thái ngữ cảnh của giao dịch qua SP–IdP–SP. Chẳng hạn SP có thể lưu một mã tương quan ngắn liên kết AuthnRequest với URL người dùng muốn truy cập sau đăng nhập.

- Với **Redirect binding**, RelayState là tham số query riêng và, nếu thông điệp được ký bằng binding signature, thường là thành phần của chuỗi được ký.
- Với **POST binding**, RelayState là hidden input đi cùng `SAMLRequest` hoặc `SAMLResponse`.
- RelayState có thể giữ một **opaque handle** đến dữ liệu trên server; không nên đặt dữ liệu nhạy cảm hay thông tin ủy quyền đầy đủ vào đây.
- Đặc tả SAML binding có ràng buộc về độ dài RelayState (thường được nêu là không quá 80 byte) và khuyến nghị bảo vệ tính toàn vẹn; cần đối chiếu khả năng tương tác và cách triển khai thực tế.
- **RelayState không phải bằng chứng xác thực.** Một POST form có RelayState trông hợp lý vẫn phải xác minh chữ ký SAML, assertion và quan hệ `InResponseTo` nếu là SP-initiated.
- Khi dùng RelayState làm đường điều hướng sau login, không cho giá trị tùy ý tạo **open redirect** tới miền lạ.

Trong Spring Security, `Saml2AuthenticationRequestRepository` thường lưu AuthnRequest trong HTTP session. Browser mang cookie session và message quay về ACS để SP đối chiếu. Nếu tự dùng distributed cache hoặc cookie strategy khác, cần bảo đảm phân biệt giao dịch và chống login CSRF/session fixation.

## 10. Chữ ký, chứng chỉ và những giả định không an toàn

Chữ ký số không “tự có” nhờ HTTPS hoặc Base64. Với SAML, cần phân biệt:

| Vị trí | Ví dụ | Bên kiểm tra |
| --- | --- | --- |
| **Query signature của Redirect binding** | `SAMLRequest=...&SigAlg=...&Signature=...` | IdP khi nhận signed AuthnRequest theo Redirect |
| **XML Digital Signature bên trong message** | `<ds:Signature>` trong AuthnRequest, Response hoặc Assertion | Bên nhận, theo cấu hình và SAML profile |
| **TLS certificate của HTTPS endpoint** | Chứng chỉ web server của `idp.example.org` hoặc SP | Client TLS/browser/server kết nối |
| **SAML signing certificate** | Public X.509 trong metadata hoặc trust registration | Bên nhận xác minh XML/binding signature |

Một chứng chỉ TLS hợp lệ **không chứng minh issuer của SAML Response**; ngược lại, chứng chỉ ký SAML không thay TLS cho browser. Ngoài chữ ký, SP phải kiểm tra audience, issuer, Destination/Recipient, thời hạn, SubjectConfirmation, quan hệ InResponseTo và chống replay tương ứng flow.

**POST không có chữ ký thì cũng không “an toàn vì nằm trong body”.** **Redirect có chữ ký query cũng không mã hóa message.** Quyền tin cậy nằm ở chính sách SAML và validation trên server, không ở HTTP method.

## 11. Cookie, SameSite và phương thức POST về ACS

Ở một flow SP-initiated thường thấy:
- Browser mở SP, SP lưu `AuthnRequest` trong session.
- Browser được chuyển tới IdP (site khác).
- IdP trả form rồi browser POST về ACS ở SP.

Đây là request **cross-site POST** trong nhiều deployment. Cookie phiên SP có `SameSite=Lax` thường **không** được gửi trên cross-site POST thông thường. Spring Security có thể không tìm thấy request đã lưu để so `InResponseTo`; login bị từ chối dù IdP đã xác thực người dùng.

Đừng giải quyết bằng cách bỏ kiểm tra `InResponseTo`. Cần chọn cấu hình cookie/phiên đúng cho kiến trúc, ví dụ đánh giá `SameSite=None; Secure` cho cookie liên quan hoặc chiến lược request repository khác có chống giả mạo và hạn chế session fixation. Với embedded iframe, chính sách third-party cookie còn ảnh hưởng nhiều hơn top-level navigation.

**CORS** điều khiển JavaScript đọc cross-origin response qua fetch/XHR, không phải lớp xác minh SAML form submission. Một lỗi ACS POST 403/404 không thể kết luận do CORS; kiểm tra đúng filter chain, route/method, CSRF exception phù hợp và session correlation. Không tắt CSRF trên toàn ứng dụng chỉ để “cho phép SAML”.

## 12. Tại sao Spring Security không nhận Response qua Redirect?

Đây là một **giới hạn sản phẩm/luồng Web SSO**, không có nghĩa đặc tả SAML không biết đến Redirect binding. Trong hướng dẫn migration của Spring Security, **HTTP-Redirect cho SAML 2.0 Response** được nêu là không được hỗ trợ. Các Response có assertion thường lớn, khó phù hợp URL; việc ký và điều kiện của Web Browser SSO profile cũng khác yêu cầu của AuthnRequest nhỏ.

Ví dụ IdP bị cấu hình trả:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.org/login/saml2/sso/corp?SAMLResponse=...
~~~

Spring Security login flow chuẩn **đợi POST form** mang `SAMLResponse`. Mặc dù có một số API converter/version có tùy chọn liên quan GET, đó không phải cam kết hỗ trợ SAML Response HTTP-Redirect theo Web SSO profile; không sử dụng nó như giải pháp chuẩn cho cấu hình IdP sai.

**Cách khắc phục:** sửa **Response Binding** ở IdP thành **HTTP-POST**, bảo đảm SP metadata công bố ACS HTTP-POST đúng URL, sau đó kiểm thử end-to-end. Nếu IdP chỉ hỗ trợ một profile/binding ngoài phạm vi của Spring Security, phải xem lại yêu cầu tích hợp/giải pháp SP phù hợp thay vì tự biến GET query thành Authentication.

## 13. Artifact, SOAP, PAOS: hiểu giới hạn và phương án

SAML 2.0 định nghĩa nhiều binding hơn hai loại dùng trong bài:

| Binding | Ý tưởng | Liên hệ Spring Security Web SSO hiện đại |
| --- | --- | --- |
| **HTTP-Artifact** | Browser chuyển một artifact tham chiếu ngắn; SP thường phải phân giải message thật từ IdP qua back-channel | Không được hỗ trợ sẵn trong `spring-security-saml2-service-provider` theo migration docs |
| **SOAP** | Server–server transport cho các protocol như artifact resolution | Không đồng nghĩa có SOAP SP Web SSO chỉ vì OpenSAML nằm trên classpath |
| **PAOS (Reverse SOAP)** | Kịch bản Enhanced Client or Proxy (ECP) | Không phải browser SSO thông thường do `saml2Login()` bật |
| **HTTP-POST** | Form POST mang Base64 XML | Luồng nhận SAML Response được Spring Security hỗ trợ |
| **HTTP-Redirect** | GET query mang XML đã DEFLATE/Base64 | Chủ yếu luồng gửi AuthnRequest trong login SP |

Trước khi ký hợp đồng federation, yêu cầu IdP cung cấp **SSO request binding** và **response binding** rõ ràng. Nếu yêu cầu bắt buộc Artifact hoặc PAOS, hãy đặt câu hỏi về kiến trúc/tính năng hỗ trợ từ đầu; đừng phát hiện sau khi integration test rằng endpoint ACS đang đòi một binding khác.

## 14. Chẩn đoán bằng DevTools và server log

Dùng browser có Developer Tools → **Network** → **Preserve log** và một IdP test được phép dùng. Quan sát thứ tự tài liệu chuyển hướng và POST; không cần xuất raw assertion hay cookie.

| Hiện tượng | Dấu hiệu gợi ý | Kiểm tra và xử lý |
| --- | --- | --- |
| GET SSO nhận 414/400 | Redirect URL/SAMLRequest quá dài hoặc bị chặn | Kiểm tra byte/size qua proxy, WAF; cân nhắc POST AuthnRequest nếu IdP hỗ trợ |
| GET SSO báo “binding unsupported” | IdP chỉ có POST SSO endpoint hoặc cấu hình sai | Đọc `SingleSignOnService@Binding/Location`, chọn POST đúng địa chỉ |
| IdP báo “signature invalid” trên AuthnRequest Redirect | Khác thuật toán, sai signing key hoặc query được encode/ký sai | Kiểm tra SigAlg, chuỗi được ký, cert, algorithm và metadata |
| IdP báo missing signed request trên POST | POST AuthnRequest chưa có XML signature theo policy | Cấu hình SP signing credentials và đối chiếu chính sách IdP |
| Sau login browser GET ACS với `SAMLResponse` | IdP cấu hình Response Redirect | Đổi response binding sang POST, sửa metadata/ACS |
| Browser POST ACS nhưng 404 | Sai endpoint/registrationId hoặc custom filter matcher | Đối chiếu ACS public URL, POST method và filter chain |
| Browser POST ACS nhưng 403 | CSRF/filter chain hoặc registration/validation từ chối | Đọc server logs đã khử nhạy cảm, tránh tắt toàn bộ CSRF |
| Response bị từ chối “InResponseTo” | Không tìm được AuthnRequest/SP session | Kiểm tra cookie SameSite, session persistence và repository |
| Response bị từ chối issuer/audience/recipient | Entity ID hoặc ACS/metadata không khớp | Đối chiếu IdP & SP metadata; sửa public URL/reverse proxy |
| Chữ ký SAML Response lỗi | Cert IdP cũ/sai, response bị sửa hoặc profile không khớp | Xác minh metadata, cert rollover và XML signature |
| IdP POST HTML form nhưng browser không submit | JavaScript bị chặn hoặc form action sai; CSP có thể can thiệp | Xem HTML, submit thủ công nếu được hỗ trợ, xem console/network |
| Người dùng login được IdP nhưng quay lại app vẫn chưa login | Chưa xử lý được SAMLResponse hoặc chưa tạo session SP | Xem ACS status/Set-Cookie và SecurityContext; đừng nhầm phiên IdP với SP |

### Cách dựng lại giao dịch không làm lộ dữ liệu

1. Ghi method, status, origin và path từng HTTP hop; phân biệt redirect ứng dụng với redirect SAML có tham số `SAMLRequest`.
2. Xem request đến IdP có `SAMLRequest` **trong URL GET** hay **trong POST form body**.
3. Xem browser quay về ACS bằng **POST** và form field tên **`SAMLResponse`**.
4. So sánh URL thực với metadata: IdP `SingleSignOnService`, SP `AssertionConsumerService`, scheme HTTPS, port, context path, registrationId.
5. Xem session SP và cookie có đi kèm POST không. Nếu không, điều tra SameSite/Secure/Domain và proxy.
6. Kiểm tra response từ ACS, session SP sau đăng nhập và log validation trên server.
7. Redact `SAMLRequest`, `SAMLResponse`, cookie, RelayState, chữ ký, assertion attributes trước khi chia sẻ HAR/log.

Browser không thể tự xác minh XML Signature; nếu Network tab hiện POST 200/302 vẫn chưa đủ kết luận rằng người dùng đã được xác thực. Phải thấy SP tạo session/Authentication hợp lệ và vào được tài nguyên đã bảo vệ.

## 15. Những nhầm lẫn thường gặp

1. **“Redirect và POST là hai giao thức SSO khác nhau.”** Sai: là hai binding vận chuyển message của **cùng giao thức SAML 2.0**.
2. **“HTTP-POST bắt buộc mọi thứ đều là POST.”** Sai: luồng có thể dùng Redirect khi gửi AuthnRequest và POST khi nhận Response.
3. **“HTTP-Redirect nghĩa là backend SP tự gọi IdP.”** Sai: server trả `Location`; browser gửi request tiếp theo.
4. **“POST body được mã hóa nên không cần signature.”** Sai: Base64 không mã hóa và HTTPS không thay validation chữ ký SAML.
5. **“Spring Security có enum REDIRECT thì nhận được Response GET.”** Sai với Spring SAML SP Web SSO chuẩn; hỗ trợ binding phụ thuộc **message/hướng/profile**.
6. **“Có OpenSAML dependency thì Artifact/SOAP/PAOS đã sẵn sàng.”** Sai: thư viện XML cấp thấp không đồng nghĩa các endpoint và state machine tích hợp đã có.
7. **“RelayState hợp lệ nghĩa là assertion hợp lệ.”** Sai: RelayState để tương quan; phải xác minh chính Response và các condition.
8. **“HTTP-Redirect chỉ cần Base64.”** Sai: Redirect có raw DEFLATE trước Base64 và percent-encoding trong URL, khác POST.
9. **“URL dài hơn 2048 ký tự luôn lỗi.”** Sai: giới hạn tùy browser/proxy/IdP và cấu hình; kiểm thử toàn bộ đường truyền.
10. **“CORS gây mọi lỗi login liên domain.”** Sai: form navigation khác fetch/XHR; thường phải xem ACS, cookie, CSRF, chữ ký và redirect URI.
11. **“IdP đăng nhập thành công là SP tự có session.”** Sai: SP chỉ tạo Authentication sau khi nhận/kiểm tra SAMLResponse hợp lệ.
12. **“Chọn binding ở SP là đủ.”** Sai: metadata/URL/chính sách IdP và SP **phải tương thích đồng thời**.

## 16. Bài tập có đáp án

**Bài 1 — Nhận diện binding.** Bạn thấy browser GET `https://idp.example.org/sso?SAMLRequest=...&RelayState=...`, sau đó POST `https://app.example.org/login/saml2/sso/corp` với `SAMLResponse`. Luồng dùng binding nào?

**Đáp án:** AuthnRequest dùng **HTTP-Redirect**, SAMLResponse dùng **HTTP-POST**. Chúng là hai bước của một SAML 2.0 Web Browser SSO flow.

**Bài 2 — Sai cấu hình Response.** IdP chỉ có tùy chọn “SAML Response over Redirect/GET”. Có nên tạo GET controller ở `/login/saml2/sso/corp` rồi tin XML giải mã được?

**Đáp án:** không. Spring Security SAML SP Web SSO không cung cấp hỗ trợ Response Redirect chuẩn. Phải thương lượng IdP dùng Response HTTP-POST hoặc thay đổi yêu cầu/giải pháp tích hợp có hỗ trợ giao thức tương ứng.

**Bài 3 — URL quá dài.** AuthnRequest ngày càng lớn và WAF trả 414. Đâu là hướng hợp lý?

**Đáp án:** kiểm tra kích thước request/limit WAF và thông tin đưa vào AuthnRequest; nếu IdP có SingleSignOnService POST thì chuyển binding gửi **AuthnRequest** sang HTTP-POST. Không cắt URL/chữ ký hay chuyển **SAMLResponse** sang Redirect.

**Bài 4 — Chữ ký.** Redirect binding có `Signature` nhưng IdP xác minh thất bại; người học lại thử “ký lại XML sau Base64”. Vấn đề nằm ở đâu?

**Đáp án:** chữ ký Redirect kiểu query ký chuỗi tham số đã URL-encode theo trật tự quy định, với `SigAlg` và RelayState nếu có; XML Signature là cơ chế khác. Kiểm tra key, thuật toán và biểu diễn byte đúng binding.

**Bài 5 — Cookie.** IdP POST SAMLResponse về ACS, nhưng server không tìm thấy AuthnRequest trong session, mặc dù browser đã đi đúng URL. Nguyên nhân nào có khả năng cao?

**Đáp án:** browser có thể không gửi cookie phiên SP trên cross-site POST do SameSite, hoặc session/request repository không nhất quán. Kiểm tra `Cookie`, `Set-Cookie`, SameSite, proxy và request ID; không bỏ `InResponseTo`.

**Bài 6 — Đọc metadata.** IdP có hai `SingleSignOnService` (Redirect, POST), nhưng SP metadata chỉ có `AssertionConsumerService` POST. Điều này mâu thuẫn không?

**Đáp án:** không. Các SingleSignOnService mô tả **IdP nhận request**, ACS mô tả **SP nhận response**. SP có thể chọn Redirect hoặc POST khi gửi AuthnRequest, còn Response vẫn về ACS POST.

## 17. Checklist khi tích hợp với IdP

- [ ] Đã xác định rõ Web Browser SSO, hướng truyền và loại message ở từng hop.
- [ ] Đã biết IdP SSO endpoint nào hỗ trợ Redirect và/hoặc POST cho AuthnRequest.
- [ ] SP metadata công bố **ACS HTTP-POST** khớp URL công khai thực tế.
- [ ] IdP được cấu hình trả **SAMLResponse bằng HTTP-POST**, không dùng Redirect/GET hay Artifact với Spring Security SP login mặc định.
- [ ] Đã xác nhận signing policy: Redirect query signature, POST XML signature, chứng chỉ tin cậy, thời hạn, audience và recipient.
- [ ] RelayState/Request ID được lưu và so khớp; chính sách unsolicited response được xác định nếu có IdP-initiated login.
- [ ] Browser gửi cookie phiên thích hợp trong cross-site POST; có chiến lược SameSite/CSRF phù hợp.
- [ ] Đã thử với proxy/WAF thật để phát hiện URI quá dài, host/scheme sai, URL encoding lỗi.
- [ ] Đã kiểm tra build/version Spring Security và tính năng binding thực sự hỗ trợ; không dựa vào tính năng của SAML Extension đời cũ.
- [ ] Log/HAR được khử dữ liệu nhạy cảm và mọi assertion được xác minh trên server.

## 18. Ghi nhớ và tài liệu tham khảo

**Cách nhớ nhanh:**

- **HTTP-Redirect**: XML → raw DEFLATE → Base64 → URL-encode → `SAMLRequest` trên **GET URL** (thường SP → IdP).
- **HTTP-POST**: XML → Base64 → HTML form → **POST body** (thường IdP → SP với `SAMLResponse`; cũng có thể SP → IdP với `SAMLRequest`).
- **Spring Security SAML 2.0 SP hiện đại**: gửi **AuthnRequest Redirect hoặc POST**; nhận **login Response POST**. Không coi Artifact hoặc login Response Redirect là binding có sẵn.
- **Hai phía phải thống nhất metadata**: SSO Location/Binding của IdP, ACS Location/Binding của SP, entity ID, signing policy và điều kiện SAML.

Tài liệu chuẩn để đối chiếu theo phiên bản:
1. Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
2. Spring Security — Producing AuthnRequests, bao gồm Redirect/POST: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
3. Spring Security — SAML 2.0 Extension Migration (giới hạn Redirect Response và Artifact): https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/saml-extension-migration.html
4. Spring Security — SAML 2.0 Migration (GET Response converter theo version): https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
5. Spring Security API — Saml2MessageBinding: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/Saml2MessageBinding.html
6. OASIS — SAML 2.0 Technical Overview (profiles/bindings): https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
7. Spring Security SAML Extension 1.x (tài liệu legacy, không áp dụng nguyên xi cho module mới): https://docs.spring.io/spring-security-saml/docs/current/reference/htmlsingle/
