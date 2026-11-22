# Chọn HTTP-Redirect hoặc HTTP-POST cho AuthnRequest theo khả năng của đối tác

> **Chủ đề:** Spring Security – federation. **Nhóm:** Tùy chỉnh AuthnRequest. Bài này giải thích cách Service Provider (SP/Relying Party) chọn **SAML 2.0 HTTP-Redirect Binding** hay **HTTP-POST Binding** khi gửi `<samlp:AuthnRequest>` đến Identity Provider (IdP/Asserting Party), cách kiểm tra khả năng thực tế của IdP, cấu hình Spring Security và xác nhận luồng hoạt động bằng bằng chứng trên trình duyệt.

## 1. Vì sao phải chọn đúng binding?

Khi người dùng chưa có phiên và truy cập tài nguyên được bảo vệ, SP khởi tạo đăng nhập SAML bằng một **AuthnRequest**. Thông điệp này chứa các thuộc tính như `ID`, `IssueInstant`, `Destination`, `AssertionConsumerServiceURL` khi được cấu hình, `Issuer` và các tùy chọn xác thực. Thông điệp phải đến đúng **SingleSignOnService (SSO)** mà IdP hỗ trợ.

**SAML binding** quy định cách mang thông điệp qua HTTP. Với AuthnRequest trong Web Browser SSO, hai binding thông dụng là:

- **HTTP-Redirect:** Spring đưa thông điệp vào query string của URL SSO và đáp ứng bằng chuyển hướng để **trình duyệt thực hiện GET** tới IdP.
- **HTTP-POST:** Spring tạo trang HTML chứa form có hidden input mang thông điệp và để **trình duyệt thực hiện POST** tới IdP.

Cả hai đều có thể là lựa chọn hợp lệ. Nhưng đối tác có thể chỉ bật một loại, có URL SSO **khác nhau** cho từng binding, hoặc yêu cầu chữ ký ở định dạng đúng với binding. Chỉ thay `GET` thành `POST` trong controller hoặc đổi URL một cách tùy tiện sẽ không đáp ứng đặc tả SAML.

**Quyết định cần dựa trên IdP metadata và thử nghiệm có xác nhận của đối tác**, không dựa vào sở thích đặt tên endpoint. Giá trị mặc định của Spring Security thường là tạo AuthnRequest qua **HTTP-Redirect**; khi IdP đòi HTTP-POST, SP phải cấu hình binding tương ứng.

## 2. Đừng nhầm binding gửi AuthnRequest với binding nhận SAMLResponse

Luồng SSO thông dụng:

```text
Browser           Spring SP / RP                       SAML IdP
   |                    |                                  |
   | GET /private       |                                  |
   |------------------->|                                  |
   |    302 tới login/authenticate                          |
   |<-------------------|                                  |
   | GET /saml2/authenticate/partner                         |
   |------------------->|                                  |
   |                    | Tạo AuthnRequest, lưu correlation |
   |                    |                                  |
   |==== PHƯƠNG ÁN A: HTTP-Redirect ========================|
   |<--- 302 Location: IdP/SSO?SAMLRequest=...&RelayState=...|
   |------------------------ GET IdP/SSO ------------------->|
   |                    |                                  |
   |==== PHƯƠNG ÁN B: HTTP-POST ============================|
   |<--- HTML form gồm hidden SAMLRequest và RelayState ----|
   |----------------------- POST IdP/SSO ------------------->|
   |                    |                                  |
   |            IdP xác thực người dùng                    |
   |<---------------- form SAMLResponse --------------------|
   | POST /login/saml2/sso/partner                          |
   |------------------->| Verify response, tạo session      |
   |<---- redirect ------|                                  |
   | GET /private       |                                  |
   |------------------->|                                  |
   |<--- 200 -----------|                                  |
```

Chỉ **một** trong hai phương án A/B được dùng để gửi một AuthnRequest. Sau đó IdP thường trả **SAMLResponse bằng HTTP-POST** tới **Assertion Consumer Service (ACS)** của SP, ví dụ `/login/saml2/sso/partner`.

**Điểm phải nhớ:** HTTP-Redirect **cho AuthnRequest** vẫn hoàn toàn tương thích với HTTP-POST **cho SAMLResponse**. Binding cho hai chiều được chọn **độc lập theo những binding mà hai phía hỗ trợ**. Không bật POST cho request chỉ vì response được POST tới ACS; không đổi cấu hình ACS khi chỉ muốn đổi cách gửi AuthnRequest.

Giao thức SAML 2.0 còn có HTTP-Artifact Binding. Bài này tập trung vào hai lựa chọn được dùng phổ biến trong cấu hình Spring SP: Redirect và POST, không tự coi chúng là đầy đủ mọi binding SAML có thể có.

## 3. Cơ chế HTTP-Redirect Binding

### 3.1. Các bước đóng gói

Đối với HTTP-Redirect Binding thông dụng:

1. SP tạo XML `<samlp:AuthnRequest>` theo SAML 2.0, gồm `ID` duy nhất và `IssueInstant` hiện tại.
2. XML được nén bằng **DEFLATE theo dạng raw DEFLATE** theo quy tắc binding, rồi Base64 và URL-encode để đặt vào tham số `SAMLRequest`.
3. Nếu có correlation state, giá trị `RelayState` được mang theo trong query string; chỉ chứa giá trị phù hợp với giới hạn và chính sách bảo mật.
4. Nếu yêu cầu ký AuthnRequest qua Redirect, SP chuẩn bị `SigAlg` và `Signature` theo quy tắc **chữ ký của binding trên query parameters đã URL-encode**, không chỉ đơn giản ký XML như POST.
5. SP phản hồi HTTP 302/303 phù hợp để trình duyệt chuyển tới URL `SingleSignOnService` của IdP.
6. Trình duyệt GET tới URL đích, IdP giải mã và kiểm tra request/binding/signature rồi thực hiện xác thực.

Hình dạng request minh họa (giá trị SAMLRequest thật rất dài và biến đổi theo phiên):

```http
GET /saml/sso/redirect?SAMLRequest=...&RelayState=...&SigAlg=...&Signature=... HTTP/1.1
Host: idp.partner.example
```

`SigAlg` và `Signature` xuất hiện khi request được ký theo HTTP-Redirect Binding; **không phải lúc nào cũng có**. Khi không ký, bảo đảm chính sách của IdP thật sự chấp nhận unsigned request. URL có các tham số này **không phải access token** để gọi API.

### 3.2. Ưu, nhược điểm cần đánh giá

**Lợi thế:** Đơn giản và phổ biến; browser chỉ cần theo redirect, không yêu cầu auto-submit JavaScript; nhiều IdP cung cấp endpoint Redirect như lựa chọn mặc định; dễ nhận diện bằng DevTools qua status 302, Location và request GET.

**Giới hạn:** XML nén/Base64/URL-encode vẫn có thể dài, đặc biệt với `RequestedAuthnContext` phức tạp, `Scoping` hoặc `Extensions`. URL dài có thể bị browser, proxy, ingress, WAF, CDN hay IdP từ chối do giới hạn request line/query string; **không có một ngưỡng ký tự duy nhất đúng cho mọi hạ tầng**. Tham số URL còn có nguy cơ xuất hiện trong browser history, proxy log, tracing và nơi ghi URL khác. Dùng TLS, giảm ghi log và tránh đặt PII/bí mật vào RelayState.

**Chữ ký:** Khi IdP yêu cầu signed AuthnRequest, SP phải có private signing key đã đăng ký. Với Redirect Binding, kiểm tra chữ ký thường dựa trên chuỗi query được dựng đúng quy tắc `SAMLRequest`, `RelayState` (nếu có), `SigAlg`. Nếu một gateway rewrite/query-normalize URL đã ký, IdP có thể từ chối vì chữ ký không còn hợp lệ.

## 4. Cơ chế HTTP-POST Binding

### 4.1. Các bước đóng gói

Khi dùng HTTP-POST Binding:

1. SP tạo XML `<samlp:AuthnRequest>` và lưu dữ liệu correlation cho lần đăng nhập này.
2. Nếu request bắt buộc phải ký, chữ ký thường là **XML Digital Signature** gắn với SAML message, có canonicalization/transforms đúng profile. Cơ chế này khác chữ ký query của Redirect Binding.
3. XML thông điệp được Base64-encode, đặt vào hidden field `SAMLRequest` trong form HTML.
4. SP trả một trang form HTML có `action` trỏ tới **SingleSignOnService Location dành cho POST**. Browser gửi form bằng POST, thường tự động bằng JavaScript.
5. IdP nhận body `application/x-www-form-urlencoded`, giải mã và kiểm tra AuthnRequest; tiếp tục xác thực và trả SAMLResponse theo binding đã thỏa thuận.

Dạng HTML minh họa cấu trúc, **không phải payload thật để gửi vào IdP**:

```html
<form method="post" action="https://idp.partner.example/saml/sso/post">
  <input type="hidden" name="SAMLRequest" value="BASE64_SAML_REQUEST">
  <input type="hidden" name="RelayState" value="OPAQUE_CORRELATION_VALUE">
  <button type="submit">Tiếp tục đăng nhập</button>
</form>
```

Trên thực tế framework tạo giá trị hợp lệ và form tự submit theo triển khai. Không tự copy HTML minh họa này thành controller gửi request thật: việc tự serialize/encode/sign rất dễ sai tiêu chuẩn, bỏ qua request repository hoặc làm lộ dữ liệu.

### 4.2. Ưu, nhược điểm cần đánh giá

**Lợi thế:** Thông điệp không nằm trong query URL nên ít gặp giới hạn độ dài URL và ít bị ghi lại ở log chỉ lưu request URL. POST phù hợp khi AuthnRequest dài hoặc đối tác hỗ trợ/kỳ vọng chữ ký XML theo HTTP-POST Binding.

**Giới hạn:** Browser phải gửi form, thường sử dụng HTML/JavaScript auto-submit; policy CSP, extension chặn script, trang HTML bị proxy rewrite hoặc hạ tầng IdP chặn POST có thể làm thất bại. Dữ liệu **vẫn đi qua browser** và có thể quan sát ở network panel, nên POST không tự biến nội dung thành bí mật; HTTPS vẫn bắt buộc. Nếu IdP chỉ có Redirect endpoint, gửi form POST tới đó sẽ bị từ chối.

**Chữ ký:** Với POST Binding truyền thống, IdP mong đợi SAML XML Signature nếu signed AuthnRequest được yêu cầu. Không lấy chuỗi `Signature` từ query Redirect rồi đưa vào form và kỳ vọng phía IdP sẽ chấp nhận. Một số sản phẩm có chế độ/chữ ký mở rộng khác; phải thống nhất đúng binding, thuật toán và cách verify theo profile thực tế.

## 5. Bảng so sánh để chọn đúng

| Tiêu chí | HTTP-Redirect cho AuthnRequest | HTTP-POST cho AuthnRequest |
| --- | --- | --- |
| Trình duyệt gửi tới IdP bằng | **GET** sau HTTP 302/303 từ SP | **POST** từ form HTML của SP |
| Vị trí `SAMLRequest` | Query string trên URL IdP | Hidden form field trong body |
| Mã hóa thường dùng | XML → raw DEFLATE → Base64 → URL encoding | XML → Base64, không áp dụng cùng pipeline DEFLATE như Redirect |
| `RelayState` | Tham số query | Trường form |
| Chữ ký request theo binding | `SigAlg`/`Signature` trên query đã chuẩn hóa theo đặc tả | XML Signature nằm trong message khi ký |
| Chiều dài request | Chịu giới hạn URL/request line của các hop | Ít chịu giới hạn URL, vẫn chịu giới hạn body của browser/proxy/IdP |
| Quan sát thực tế | 302 Location và GET có `SAMLRequest` | HTML form và POST có `SAMLRequest` |
| Khả năng lộ ở URL log | Cao hơn, vì dữ liệu có trong URL | Ít hơn đối với URL log, vẫn có rủi ro từ body/công cụ debug |
| Yêu cầu ở IdP | Endpoint trong metadata với binding Redirect | Endpoint trong metadata với binding POST |
| Mức bảo mật mặc định | Không mặc nhiên kém an toàn nếu ký, TLS, validation chuẩn | Không mặc nhiên an toàn hơn chỉ vì là POST |
| Trường hợp hay gặp | Luồng SSO thông dụng, AuthnRequest vừa phải | Đối tác chỉ nhận POST, yêu cầu XML signature, request lớn |
| Kết quả phía SP sau khi xác thực | Tiếp nhận SAMLResponse ở ACS, thường HTTP-POST | **Cũng** tiếp nhận SAMLResponse ở ACS, thường HTTP-POST |

**Lưu ý về thuật ngữ:** “HTTP redirect” trong câu chuyện này có thể chỉ (a) HTTP response 302/303, hoặc (b) **SAML HTTP-Redirect Binding** gồm quy tắc encode/sign thông điệp; đừng đồng nhất hai khái niệm. Tương tự, một POST HTTP bất kỳ chưa chắc là **SAML HTTP-POST Binding** đúng chuẩn.

## 6. Nguồn sự thật để biết đối tác hỗ trợ binding nào

### 6.1. Đọc chính xác `SingleSignOnService` trong IdP metadata

IdP metadata thường có một hoặc nhiều phần tử `SingleSignOnService` trong `IDPSSODescriptor`:

```xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.partner.example/saml/sso/redirect"/>
  <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="https://idp.partner.example/saml/sso/post"/>
</md:IDPSSODescriptor>
```

Đây là **đoạn metadata minh họa**, không phải tệp metadata SAML hoàn chỉnh: không có `EntityDescriptor`, `entityID`, X.509 certificate và chữ ký. Không import XML thiếu cấu trúc này vào Spring làm registration thật.

Thông tin cần lấy từ metadata thật:

- `EntityDescriptor/@entityID`: định danh logic của IdP đã thống nhất; không nhất thiết bằng URL SSO.
- `IDPSSODescriptor/SingleSignOnService/@Binding`: urn chính xác, ví dụ `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect` hoặc `...:HTTP-POST`.
- `SingleSignOnService/@Location`: URL thực tế cho **binding đó**, thường HTTPS.
- `WantAuthnRequestsSigned` (nếu có) cùng chính sách do đối tác cung cấp: IdP có bắt buộc SP ký request không?
- Thuật toán ký/certificate, yêu cầu `Issuer`, `NameIDPolicy`, `RequestedAuthnContext` và các điều kiện mở rộng nếu IdP kiểm tra chúng.

Nếu IdP khai báo cả hai binding, đừng suy đoán endpoint nào mặc định phù hợp với mục đích: xem hướng dẫn tích hợp, contract, khả năng ký của SP và thử nghiệm với IdP. Có IdP dùng chung URL cho POST/Redirect, nhưng cũng có IdP dùng hai URL khác nhau. **Đừng gửi POST vào URL Redirect chỉ vì hostname trùng nhau.**

### 6.2. Metadata đáng tin từ đâu?

Tải IdP metadata qua kênh được quản trị phê duyệt hoặc lấy file đã kiểm chứng. Kiểm tra `entityID` và signing certificate đã thống nhất; nếu dùng metadata signature thì xác minh bằng trust anchor độc lập. Không nhận URL metadata tùy ý từ tenant rồi để backend tự fetch. HTTP redirect trong quá trình backend fetch metadata là chuyện **khác SAML HTTP-Redirect Binding** và có thể tạo rủi ro SSRF nếu không kiểm soát URL/egress.

Lưu bản metadata đã duyệt để đối chiếu và xác định chính xác `Binding` + `Location` khi đối tác cập nhật endpoint. Nếu metadata cũ chứa POST nhưng phiên bản IdP mới đã tắt POST, cần điều phối thay đổi, kiểm tra lại và triển khai cùng đối tác; không tự “fallback” sang binding khác mà chưa được phê duyệt.

## 7. Quy trình ra quyết định theo khả năng đối tác

Thực hiện theo thứ tự:

1. **Thu thập IdP metadata** từ nguồn tin cậy; xác nhận đúng IdP `entityID` và signing certificate.
2. Liệt kê các `SingleSignOnService`, mỗi mục gồm **Binding + Location**. Nếu IdP chỉ khai báo Redirect, chọn Redirect; nếu chỉ khai báo POST, chọn POST khi Spring/phiên bản đang dùng hỗ trợ.
3. Nếu cả hai được hỗ trợ, chọn Redirect cho AuthnRequest gọn, tương thích tốt; cân nhắc POST khi request lớn, IdP yêu cầu hoặc chữ ký theo POST dễ đáp ứng hơn trong môi trường ấy.
4. Hỏi rõ **IdP có yêu cầu signed AuthnRequest không**, thuật toán nào, SP certificate nào đã được đối tác đăng ký; điều này có thể quyết định khả năng dùng binding.
5. Khóa cấu hình binding và **đích SSO URL của cùng binding** trong `RelyingPartyRegistration`/Spring Boot. Không để browser/client chọn binding bằng query parameter không tin cậy.
6. Thử browser flow end-to-end và kiểm tra kết quả trong DevTools: method, target URL, vị trí `SAMLRequest`, thông điệp có chữ ký đúng dạng, IdP chấp nhận, ACS nhận SAMLResponse và SP lập session.
7. Trước production, chạy thử qua ingress/WAF/proxy thực tế, kiểm tra URL/request size, CSP, cookie/RelayState, TLS và thay đổi IdP metadata trong vòng đời.

Một quyết định nên được ghi trong tài liệu triển khai:

| Thuộc tính | Ví dụ quyết định |
| --- | --- |
| `registrationId` | `partner` |
| IdP issuer | `https://idp.partner.example/entity` |
| AuthnRequest binding | `HTTP-POST` |
| SSO URL cho binding này | `https://idp.partner.example/saml/sso/post` |
| Signed requests | Có, SP certificate đã đăng ký với IdP |
| Response binding/ACS | IdP gửi SAMLResponse bằng POST tới `https://sp.example.org/login/saml2/sso/partner` |
| Đường thử nghiệm | Browser login, kiểm tra POST body/response/session và trường hợp sai binding |
| Chủ sở hữu thay đổi | Đội tích hợp SP + đầu mối IdP |

## 8. Cấu hình Spring Boot theo từng binding

**Giả định chung:** Ứng dụng Spring Boot servlet + Spring Security SAML2; đã có IdP test thật và đã đăng ký SP entityID, ACS URL/certificate với đối tác. Các domain `*.example` dưới đây mang tính minh họa; phải thay bằng thông tin đã được phê duyệt và cung cấp certificate thật. Các mẫu là **hai phương án thay thế**, không copy cả hai để tranh chấp cùng `registrationId`.

### 8.1. Phương án HTTP-Redirect

File `application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            assertingparty:
              entity-id: https://idp.partner.example/entity
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing.crt
              singlesignon:
                url: https://idp.partner.example/saml/sso/redirect
                binding: REDIRECT
                sign-request: false
```

**Ý nghĩa:** Khi người dùng khởi tạo `/saml2/authenticate/partner`, SP tạo AuthnRequest và hướng trình duyệt GET tới endpoint Redirect. Mẫu `sign-request: false` **chỉ áp dụng khi IdP thử nghiệm thực sự chấp nhận unsigned AuthnRequest**. Không tắt ký request nếu IdP/quan hệ federation yêu cầu ký. Certificate `idp-signing.crt` dùng để SP **xác minh chữ ký từ IdP**; không phải khóa để SP ký yêu cầu.

Nếu IdP yêu cầu ký AuthnRequest, phải khai báo signing key/certificate của **SP** và bật `sign-request: true`; ví dụ cấu hình ở mục 8.3.

### 8.2. Phương án HTTP-POST

File `application.yml`, áp dụng cho cùng registration trong một cấu hình **thay thế**:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            assertingparty:
              entity-id: https://idp.partner.example/entity
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing.crt
              singlesignon:
                url: https://idp.partner.example/saml/sso/post
                binding: POST
                sign-request: false
```

**Ý nghĩa:** Giá trị `singlesignon.binding: POST` chọn HTTP-POST Binding để gửi AuthnRequest đến `url` đã khai báo. Spring có thể tạo trang form để browser POST `SAMLRequest` sang IdP. Việc chọn `POST` không đổi callback ACS (thường vẫn `/login/saml2/sso/partner`) và không đổi cấu hình xác minh SAMLResponse.

Nếu IdP bắt buộc ký, chuyển sang phương án `sign-request: true` cùng **SP signing credentials** và đảm bảo IdP đã lưu SP signing certificate. Chữ ký tương ứng với POST Binding phải được kiểm tra theo XML signature, không phải query signature của Redirect.

### 8.3. Khi IdP yêu cầu signed AuthnRequest

Ví dụ riêng cho POST có ký; file/certificate **phải có thật, thuộc SP và được quản lý bí mật**:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner:
            signing:
              credentials:
                - private-key-location: file:/run/secrets/sp-signing.key
                  certificate-location: file:/run/secrets/sp-signing.crt
            assertingparty:
              entity-id: https://idp.partner.example/entity
              verification:
                credentials:
                  - certificate-location: classpath:saml/idp-signing.crt
              singlesignon:
                url: https://idp.partner.example/saml/sso/post
                binding: POST
                sign-request: true
```

Trong môi trường chạy thực, chỉnh đường dẫn secret theo topology, sử dụng HTTPS, phân quyền đọc private key tối thiểu và đăng ký **public SP signing certificate** với IdP. Tham số `sign-request` điều khiển **yêu cầu ký AuthnRequest**, còn `verification.credentials` của asserting party dùng để kiểm tra **SAMLResponse/Assertion do IdP ký**. Hai tập certificate có mục đích khác nhau.

Nếu chuyển ví dụ này thành Redirect signed request, thay đúng cả `binding: REDIRECT` và `url` sang endpoint Redirect mà IdP công bố, giữ SP signing key đã đăng ký. Spring sẽ sử dụng quy tắc ký của binding tương ứng. **Đừng tự tạo `Signature` query hay XML signature bằng controller**.

**Tính tương thích phiên bản:** Các thuộc tính `spring.security.saml2.relyingparty.registration.*.assertingparty.singlesignon.binding` và `sign-request` được Spring Boot ánh xạ từ `Saml2RelyingPartyProperties`. Kiểm tra phiên bản Spring Boot/Spring Security đang chạy để dùng đúng package và API; cấu hình Java thay thế có ở phần dưới.

## 9. Cấu hình trực tiếp `RelyingPartyRegistration` bằng Java

Nếu dự án quản lý registrations bằng Java, Spring Security cho phép đặt binding thông qua `Saml2MessageBinding`. Ví dụ ở đây bắt đầu từ **IdP metadata file đã được kiểm chứng**, rồi chọn rõ endpoint POST của đối tác.

File `src/main/java/com/example/saml/PartnerSamlConfig.java`:

```java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.registration.Saml2MessageBinding;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PartnerSamlConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        RelyingPartyRegistration partner =
            RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/idp-approved.xml")
                .registrationId("partner")
                .assertingPartyMetadata(party -> party
                    .singleSignOnServiceLocation(
                        "https://idp.partner.example/saml/sso/post")
                    .singleSignOnServiceBinding(Saml2MessageBinding.POST))
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(partner);
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/authenticate/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

**Đọc mẫu đúng cách:**

- `fromMetadataLocation("classpath:saml/idp-approved.xml")` đọc metadata **đã phê duyệt**, không tải URL do người dùng nhập. File phải là SAML metadata thực tế với `entityID`, signing certificates và endpoints đúng; nó **không được tạo chỉ từ XML minh họa ngắn trong bài**.
- `.singleSignOnServiceBinding(Saml2MessageBinding.POST)` chọn POST cho AuthnRequest. `singleSignOnServiceLocation(...)` được chỉ rõ để không vô tình dùng **URL dành cho Redirect** lấy từ metadata trong khi đã đổi binding sang POST.
- Đảm bảo IdP metadata/contract thực sự khai báo hỗ trợ POST tại URL đó. Không thêm endpoint POST do mình tưởng tượng.
- Bean `SecurityFilterChain` bật `saml2Login`. `saml2Login` tích hợp filter tạo AuthnRequest và xử lý SAMLResponse, không cần tự viết controller AuthnRequest/ACS.
- Đoạn Java này **chưa khai báo SP signing credentials riêng**: chỉ có thể áp dụng khi IdP cho phép unsigned AuthnRequest hoặc khi metadata/configuration khác của registration đã cung cấp thông tin phù hợp. Với đối tác yêu cầu ký, thêm `signingX509Credentials` và chính sách signing vào registration, hoặc dùng YAML hoàn chỉnh ở mục 8.3.

**Điều kiện build:** Đây là class của ứng dụng Spring Boot sử dụng Java 17+ và dependency Spring Web, Spring Security, `spring-security-saml2-service-provider`. Nó không phải chương trình Java độc lập chạy bằng `javac` thuần. Nếu classpath metadata thiếu hoặc không đúng, application context có thể không khởi động. Không đồng thời đăng ký bean này và một bean repository khác mâu thuẫn với chính registrationId.

Để trở lại Redirect khi đối tác yêu cầu, thay `Saml2MessageBinding.POST` bằng `Saml2MessageBinding.REDIRECT` **và** đổi location tới endpoint Redirect tương ứng. Không cần đổi endpoint mặc định `/saml2/authenticate/partner` chỉ vì thay binding ở phía IdP.

## 10. Những điểm trong `saml2Login` không bị thay đổi bởi lựa chọn binding

### 10.1. URL khởi tạo SSO thuộc SP

Spring Security sử dụng `Saml2WebSsoAuthenticationRequestFilter` để nhận request khởi tạo AuthnRequest, phổ biến:

- `GET /saml2/authenticate/{registrationId}`, ví dụ `/saml2/authenticate/partner`.
- Biến thể query `/saml2/authenticate?registrationId=partner` trong phiên bản hỗ trợ.

Đây là **endpoint trên SP được browser gọi để bắt đầu SSO**. Sau đó, SP chọn Redirect hay POST để gửi AuthnRequest tới **IdP SSO endpoint**; không phải đặt method POST cho đường `/saml2/authenticate/partner` là đã biến outgoing binding thành HTTP-POST.

### 10.2. ACS là nơi nhận SAMLResponse

ACS phổ biến là `POST /login/saml2/sso/{registrationId}`, do `Saml2WebSsoAuthenticationFilter` xử lý. Nó phải nhận request của browser **trước khi có phiên SP**, nhưng SAMLResponse chỉ được tin sau các kiểm tra chữ ký, issuer, `AudienceRestriction`, `Destination`, `Recipient`, `InResponseTo` (khi áp dụng), điều kiện thời gian và chống replay.

Cấu hình `permitAll` cho URL giao thức không bỏ qua authentication filter. Không dùng `web.ignoring("/login/saml2/sso/**")` hay tự viết controller nhận Base64 assertion.

### 10.3. Lưu AuthnRequest và RelayState

Spring Security mặc định có `HttpSessionSaml2AuthenticationRequestRepository` lưu AuthnRequest đang chờ trong phiên SP. Dù outbound là Redirect hay POST, SP vẫn phải liên hệ response của IdP với request đã khởi tạo để tránh login injection/replay và giữ đúng registrationId.

`RelayState` nên là giá trị opaque/được bảo vệ về toàn vẹn theo binding và ứng dụng; không tự cho phép điều hướng tới URL bất kỳ chỉ vì chuỗi `RelayState` xuất hiện trong request. Với HTTP-Redirect Binding, RelayState có thể tham gia chữ ký query; với POST Binding phải bảo đảm cơ chế correlation/session phù hợp. Không ghi RelayState hoặc SAML payload đầy đủ lên log public.

### 10.4. Cookie/session và trình duyệt

Nếu trình duyệt trở về ACS qua POST **cross-site**, chính sách cookie `SameSite` có thể ảnh hưởng khả năng browser gửi session cookie về SP và tìm lại AuthnRequest đã lưu. Cần kiểm thử cookie Secure/HttpOnly, SameSite, HTTPS, Session ID, session affinity/distributed session trong môi trường thật. Lỗi mất correlation thường không liên quan tới bản thân việc AuthnRequest dùng Redirect hay POST. Không bỏ kiểm tra `InResponseTo` để che lỗi cookie/phiên.

## 11. Cách xác nhận binding bằng trình duyệt và log an toàn

### 11.1. Kiểm tra một luồng Redirect

1. Mở tab DevTools Network và đánh dấu preserve log khi cần, dùng người dùng test.
2. Truy cập `https://sp.example.org/saml2/authenticate/partner` (hoặc trang bảo vệ làm phát sinh login).
3. Xem response của SP: thường **302/303** với `Location` trỏ tới **IdP Redirect SSO URL** đã được phê duyệt.
4. Xem request tiếp theo của browser tới IdP: method **GET**, query có `SAMLRequest` và có thể `RelayState`; khi ký theo Redirect Binding sẽ có `SigAlg`/`Signature`.
5. Kiểm tra IdP chấp nhận request; sau login, browser POST `SAMLResponse` về ACS và SP lập phiên.
6. Nếu proxy/WAF trả `414 URI Too Long`, `400` hay cắt query, cần xem giới hạn URL, không vội bỏ ký hoặc sửa bừa thông điệp SAML.

Chỉ ghi trong biên bản kiểm thử: method, URL host/path đã được duyệt, mã HTTP, có/không `SAMLRequest`/`Signature`, kết quả IdP và callback. **Không đính kèm raw SAMLRequest/SAMLResponse, RelayState, cookie hay khóa bí mật** vào ticket công khai.

### 11.2. Kiểm tra một luồng POST

1. Giữ cùng IdP registration test và đổi sang POST theo cấu hình đã thống nhất.
2. Browser gọi endpoint khởi tạo AuthnRequest trên SP.
3. Response của SP thường là **HTML form** (có thể tự submit bằng script) với `method="post"`, `action` đúng **IdP POST SSO URL**, hidden `SAMLRequest` và có thể `RelayState`.
4. Browser gửi **POST** tới IdP; quan sát content-type form thích hợp và xem IdP chấp nhận.
5. IdP hoàn tất login và gửi SAMLResponse về **ACS của SP**; session xác thực được tạo.
6. Kiểm thử browser khi JavaScript/CSP bị chặn, với chính sách proxy/WAF thực tế, vì form POST có thể bị ảnh hưởng bởi chính sách frontend.

Nếu chỉ thấy HTML form nhưng **không có POST tới IdP**, kiểm tra CSP, auto-submit, extension và lỗi script trước khi nghi ngờ signing certificate. Nếu POST đến IdP nhưng bị từ chối, kiểm tra Binding/Location và chữ ký XML.

### 11.3. Ma trận nghiệm thu

| Tình huống | Điều phải kiểm chứng |
| --- | --- |
| IdP chỉ công bố Redirect; SP chọn Redirect | Browser GET đúng URL IdP, AuthnRequest hợp lệ, IdP đăng nhập, ACS nhận SAMLResponse |
| IdP chỉ công bố POST; SP chọn POST | Browser POST form tới đúng URL, IdP chấp nhận, ACS hoàn tất session |
| IdP hỗ trợ cả hai; SP chọn một | Chỉ binding được cấu hình xuất hiện trong lượt khởi tạo; SSO vẫn đạt |
| SP chọn POST nhưng trỏ nhầm URL Redirect | IdP từ chối hoặc trả lỗi; khắc phục bằng **đúng binding và đúng Location**, không tắt verify |
| SP chọn Redirect nhưng endpoint IdP chỉ nhận POST | Login bị từ chối; kiểm tra metadata và thay cấu hình |
| IdP yêu cầu ký, SP không có signing credentials | Không chấp nhận AuthnRequest; cấu hình SP private key/certificate và ký đúng binding |
| Signed Redirect có query bị proxy sửa thứ tự/encoding | Signature check có thể lỗi; cần giữ nguyên query đã ký theo chuẩn |
| Signed POST có XML signature sai | IdP từ chối; xác minh canonicalization/signature và certificate, không đổi thành unsigned chỉ để thành công |
| AuthnRequest có nhiều extensions, URL quá dài | Xem xét POST nếu IdP hỗ trợ; kiểm tra WAF, ingress và size limit |
| Đã login nhưng ACS báo thiếu request correlation | Kiểm tra session/SameSite/RelayState, không tắt chống replay |
| Metadata đổi binding/SSO URL | Phải qua phê duyệt, cập nhật registration, kiểm thử lại; không tự tin URL cũ |
| SAMLResponse sai issuer/audience/chữ ký | SP vẫn phải từ chối ở ACS, **bất kể** outbound binding nào |

**Tách ba lớp nghiệm thu:** (1) SP tạo AuthnRequest đúng binding, (2) IdP chấp nhận và trả response, (3) SP xác minh SAMLResponse và phân quyền. Thành công ở lớp 1 không đủ để chứng minh SSO hoặc bảo vệ danh tính đã đúng.

## 12. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| IdP trả `Unsupported binding`, `Invalid request` hoặc 400 | Binding không hỗ trợ, POST gửi vào endpoint Redirect hoặc ngược lại | Đối chiếu `SingleSignOnService Binding + Location` trong metadata, chỉnh cả hai |
| Spring trả 302 tới IdP dù muốn POST | Registration vẫn dùng Redirect, bean repository khác được chọn hoặc cấu hình không load | Đọc giá trị binding hiệu lực, kiểm tra registrationId/repository, quan sát Network |
| Spring trả form POST nhưng IdP không nhận | IdP chưa bật POST, URL sai, CSP/JS chặn auto-submit | Kiểm tra metadata/IdP product và browser Network |
| IdP báo cần signed AuthnRequest | `sign-request` không khớp hợp đồng, SP thiếu signing credential | Đăng ký SP certificate, cấp private key, cấu hình ký phù hợp |
| IdP báo signature invalid khi Redirect | Query parameter encoding/chữ ký bị thay qua proxy hoặc key/algorithm sai | Kiểm tra SigAlg/Signature, certificate/algorithm, giữ nguyên URL |
| IdP báo signature invalid khi POST | XML signature/canonicalization/certificate sai hoặc IdP kỳ vọng binding khác | Xác nhận đúng XML signature và Binding; không dùng query signature cho form POST |
| `414 Request-URI Too Long` | AuthnRequest Redirect quá dài so với browser/proxy/WAF | Thu gọn request hoặc chọn POST nếu đối tác hỗ trợ, kiểm tra mọi hop |
| Login xong ACS từ chối `InResponseTo` | Mất session/RelayState/correlation, cookie SameSite hoặc cluster session | Khôi phục session/correlation, kiểm tra cookie và sticky/distributed session |
| IdP POST về ACS báo 403 CSRF | URL ACS bị custom mà CSRF exception không khớp | Kiểm tra matcher của SAML filter, ngoại lệ CSRF **chỉ** ACS; không tắt CSRF toàn web |
| IdP yêu cầu `ForceAuthn` hoặc `RequestedAuthnContext` | Cần tùy chỉnh nội dung XML AuthnRequest; không phải lỗi binding | Dùng API tùy chỉnh AuthnRequest/OpenSAML theo version, kiểm tra chính sách IdP |
| URL IdP/ACS bị sinh theo HTTP/internal host | Reverse proxy/forwarded headers hoặc `{baseUrl}` sai | Dùng canonical HTTPS host và trusted proxy, đối chiếu metadata và IdP registration |
| Có hai IdP, người dùng vào nhầm IdP | Chọn sai `registrationId` hoặc repository chứa registration chồng chéo | Gắn mỗi partner với registration riêng và link rõ `/saml2/authenticate/{registrationId}` |
| Chuyển POST nhưng SAMLResponse vẫn POST | Đây là bình thường: outbound và inbound binding độc lập | Không sửa ACS/response binding khi không có yêu cầu từ đối tác |
| Tắt `sign-request` thì login thành công | Có thể đang hạ chính sách của IdP/test; không chứng minh an toàn | Khôi phục yêu cầu ký đúng hợp đồng và sửa certificate/algorithm |

## 13. Kiểm tra an ninh và tương thích trước production

- **Chọn đúng đối tác:** `registrationId` cố định, IdP entityID được phê duyệt, SSO Location HTTPS và binding tương ứng được kiểm tra.
- **Ký AuthnRequest khi được yêu cầu:** SP private key được bảo vệ; public certificate đăng ký với IdP; kiểm tra đúng signature format cho binding, thuật toán được phép và certificate rollover.
- **Xác minh response độc lập:** Spring SP kiểm tra SAMLResponse/Assertion, issuer, audience, recipient, destination, thời gian, replay và correlation. Không chấp nhận assertion chỉ vì request đi theo binding đúng.
- **Chống lộ thông tin:** Không đặt PII/bí mật vào `RelayState`, hạn chế log URL/query/body có SAMLRequest, không lưu raw assertions ở log. Sử dụng HTTPS cả hai đầu.
- **Hạ tầng:** Reverse proxy/WAF có kích thước URL và form body phù hợp, không rewrite tham số đã ký; CSP phù hợp với form POST do framework phát; IdP endpoint có sẵn/đúng host.
- **Phiên:** Cookie Secure/HttpOnly/SameSite phù hợp với SAML POST callback, session correlation có khả năng hoạt động trong cluster; chống session fixation và replay.
- **Phân quyền:** Sau khi SAML login, quyền người dùng ở app do SP kiểm tra từ claims đã xác minh/nguồn nội bộ. Đăng nhập hợp lệ không mặc định được phép vào `/admin/**`.
- **Thay đổi:** Cập nhật IdP metadata và đổi binding phải qua review + kiểm thử; có rollback khi đối tác thay endpoints/certification.
- **Fail closed:** Nếu IdP không hỗ trợ binding được chọn, từ chối login và báo lỗi có thể chẩn đoán; không tự bỏ chữ ký, bỏ TLS, tắt assertion validation hoặc chọn đích từ URL do browser nhập.

### Câu hỏi luyện tập

**1. Đối tác công bố cả HTTP-Redirect và HTTP-POST nhưng AuthnRequest đã dài hơn giới hạn URL của proxy.** Nên xử lý thế nào?

Cần xác minh nguyên nhân URL dài, kiểm tra khả năng POST/SSO Location trong IdP metadata và hỏi đối tác. Nếu hỗ trợ, đổi sang **HTTP-POST cho AuthnRequest** tại đúng endpoint, cấu hình ký tương ứng và thử toàn tuyến. Không tăng giới hạn URL tùy tiện mà bỏ qua WAF/chính sách bảo mật.

**2. Ứng dụng SP gửi AuthnRequest bằng Redirect; IdP trả SAMLResponse bằng POST. Đây có phải cấu hình sai binding?**

Không. Đây là cặp **Redirect (request) + POST (response)** rất phổ biến và hợp lệ. Cần kiểm tra hai chiều độc lập: outgoing tới SingleSignOnService của IdP; incoming tới ACS của SP.

**3. IdP yêu cầu Signed AuthnRequest và chỉ chấp nhận HTTP-POST. Có thể chỉ đặt `binding: POST` và `sign-request: false` không?**

Không. Phải cung cấp **SP signing credential**, bật signed request theo yêu cầu và để framework tạo XML signature đúng binding POST. Đăng ký SP public certificate với IdP và kiểm thử signature.

**4. Đặt `saml2Login` rồi sửa endpoint `/saml2/authenticate/partner` thành POST có đủ chưa?**

Không. Endpoint này là **điểm khởi phát trên SP**. Binding thực sự đưa thông điệp tới IdP được quyết định trong `RelyingPartyRegistration`/`assertingparty.singlesignon.binding`; đích `Location` cũng phải khớp.

**5. Đổi sang POST để “ẩn SAMLRequest khỏi browser”. Nhận định đó đúng không?**

Không. Với HTTP-POST Binding, browser vẫn nhận HTML form và gửi Base64-encoded SAMLRequest. POST giúp tránh một số vấn đề URL dài và ghi query log, nhưng không thay thế HTTPS, ký số, kiểm soát PII hay validation.

## 14. Checklist hoàn thành bài

- [ ] Có metadata IdP đã xác minh, ghi rõ `entityID` và mọi `SingleSignOnService Binding + Location`.
- [ ] Biết đối tác chấp nhận **HTTP-Redirect**, **HTTP-POST** hay cả hai; đã xác nhận yêu cầu ký AuthnRequest.
- [ ] Chọn binding theo khả năng đối tác và kích thước/điều kiện hạ tầng; không dựa vào binding SAMLResponse.
- [ ] Cấu hình `singlesignon.binding`, `url`, `sign-request` và credentials đúng từng registration.
- [ ] Đã xác định SP entityID, ACS HTTPS, IdP verification certificate và SP signing certificate/private key (khi cần).
- [ ] Browser Network chứng minh request thực sự là GET Redirect hoặc POST form vào endpoint IdP tương ứng.
- [ ] IdP chấp nhận request; gửi SAMLResponse về ACS; Spring SP xác minh và tạo session.
- [ ] Request sai binding, sai chữ ký, sai issuer/recipient hoặc sai correlation **không** tạo phiên đăng nhập.
- [ ] Không ghi raw SAMLRequest, SAMLResponse, RelayState, cookie hoặc private key vào ticket/log.
- [ ] Có kiểm thử với ingress/proxy/WAF, CSP, TLS, cluster session và trường hợp IdP đổi metadata.

**Ghi nhớ:** Chọn HTTP-Redirect hay HTTP-POST là quyết định về **cách vận chuyển AuthnRequest từ SP tới SingleSignOnService của IdP**. Spring Security hỗ trợ cả hai; đầu tiên xác minh IdP công bố binding nào và URL nào, sau đó cấu hình binding + Location + chính sách ký **nhất quán**, và cuối cùng kiểm thử cả luồng. Thay đổi này không làm mất nghĩa vụ xác minh SAMLResponse và phân quyền trong ứng dụng.

## 15. Tài liệu đối chiếu

- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) — HTTP-Redirect mặc định, cách chọn `Saml2MessageBinding.POST` và signing credentials.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) — RP/AP, `RelyingPartyRegistration`, ACS và flow đăng nhập.
- [Spring Boot — Saml2RelyingPartyProperties.AssertingParty.Singlesignon](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/saml2/autoconfigure/Saml2RelyingPartyProperties.AssertingParty.Singlesignon.html) — property URL, binding và sign-request trong phiên bản có API tương ứng.
- [Spring Security API — Saml2MessageBinding](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/Saml2MessageBinding.html) — các binding Redirect/POST.
- [OASIS — SAML V2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html) — các trường hợp Redirect/POST, sự độc lập giữa request và response.
- [OASIS — SAML V2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf) — mã hóa/chữ ký của HTTP-Redirect và HTTP-POST.
- [Microsoft Learn — SAML protocol for SSO](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol) — ví dụ đối tác yêu cầu AuthnRequest Redirect và SAMLResponse POST.
