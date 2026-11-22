# Cấu hình SSO endpoint, binding và yêu cầu ký AuthnRequest trong SAML 2.0

> **Bối cảnh:** Spring Security – federation → Đăng ký SAML2. Bài này hướng dẫn xác định **đúng SSO endpoint của IdP**, **đúng HTTP binding để gửi AuthnRequest**, **đúng yêu cầu ký và bộ khóa của SP**, sau đó đối chiếu với **ACS endpoint nhận SAMLResponse** trong Spring Security. Mọi URL và chứng chỉ trong ví dụ đều thuộc môi trường giả lập.

## 1. Mục tiêu và vấn đề thực tế

Khi cấu hình một ứng dụng Spring Boot làm **SAML Service Provider (SP)**, thường phải khai báo nhiều URL và chứng chỉ. Ba câu hỏi dễ bị nhầm:

1. **Gửi `AuthnRequest` đi đâu?** → Tới **SingleSignOnService** (SSO endpoint) do **Identity Provider (IdP)** công bố.
2. **Gửi bằng cách nào?** → HTTP-Redirect hoặc HTTP-POST binding mà IdP hỗ trợ và SP chọn. Hai binding có cách mã hóa và biểu diễn chữ ký **khác nhau**.
3. **IdP có yêu cầu SP ký `AuthnRequest` không?** → Đọc chính sách đăng ký/metadata và cấu hình **khóa riêng ký của SP** cùng certificate công khai mà IdP tin cậy. Không dùng nhầm certificate dùng để kiểm tra **SAMLResponse của IdP**.

Một câu hỏi liên quan nhưng khác hướng là **IdP gửi kết quả đăng nhập về đâu?** → Tới **Assertion Consumer Service (ACS)** do **SP** công bố; thường là HTTP-POST mang `SAMLResponse`.

Kết quả mong đợi của bài học: có thể giải thích trường nào thuộc IdP, trường nào thuộc SP, áp dụng YAML và `SecurityFilterChain` tương ứng, đọc request trên đường đi để xác nhận binding/signature, và xử lý các lỗi phổ biến mà không tắt các kiểm tra bảo mật.

## 2. Đặt tên đúng: Endpoint khởi tạo login, SSO service và ACS

Các khái niệm gần nhau nhưng có **chủ sở hữu và chiều truyền khác nhau**:

| Thành phần | Bên sở hữu | Bên gọi | Mục đích | Ví dụ giả lập |
| --- | --- | --- | --- | --- |
| SP login initiation endpoint | SP / Spring Security | Trình duyệt | Tạo `AuthnRequest` cho registration đã chọn | `https://portal.example.org/saml2/authenticate/corp` |
| IdP `SingleSignOnService Location` | IdP | Trình duyệt do SP điều hướng | Nhận `AuthnRequest`, thực hiện xác thực người dùng | `https://login.example.org/saml/sso/redirect` |
| SP `AssertionConsumerService Location` (ACS) | SP | Trình duyệt mang kết quả từ IdP | Nhận `SAMLResponse`, kiểm tra rồi tạo phiên SP | `https://portal.example.org/login/saml2/sso/corp` |
| SP `entityID` | SP | Được nhúng trong `Issuer`/metadata | Định danh logic của SP; không nhất thiết là URL đang phục vụ HTTP | `https://portal.example.org/saml2/service-provider-metadata/corp` |
| IdP `entityID` | IdP | Dùng trong trust/Issuer | Định danh logic của IdP; không mặc nhiên là SSO URL | `https://login.example.org/saml/metadata` |
| IdP metadata URL hoặc file | Bên vận hành IdP | SP admin/process khởi tạo cấu hình | Cung cấp entityID, SSO services, signing certificates, flags | `https://login.example.org/saml/metadata.xml` |
| SP metadata endpoint | SP | IdP admin/service khi onboarding | Công bố entityID, ACS, hỗ trợ binding, signing certificate | `https://portal.example.org/saml2/service-provider-metadata/corp` |

**Các cặp phân biệt bắt buộc:**

- `/saml2/authenticate/corp` của SP **không phải** SSO endpoint của IdP. Browser truy cập đường dẫn này để Spring Security tạo request và điều hướng sang IdP.
- `https://login.example.org/saml/sso/redirect` của IdP **không phải** SP ACS. Nó nhận `AuthnRequest`, không nhận `SAMLResponse`.
- `entityID` không đồng nghĩa với endpoint. Nó là định danh tin cậy, dù nhiều triển khai dùng URL trông giống endpoint.
- Chữ ký của **AuthnRequest** và chữ ký của **Response/Assertion** bảo vệ hai thông điệp và do **hai bên ký khác nhau**; chúng cần credential khác nhau.

## 3. Sơ đồ SP-initiated Web SSO và các ranh giới tin cậy

Giả sử registration tên `corp`, IdP hỗ trợ HTTP-Redirect cho request và ACS dùng HTTP-POST cho response:

```text
Browser               Spring Security SP                  SAML IdP
   |                         |                                 |
   | GET /private            |                                 |
   |------------------------>|                                 |
   | 302 /saml2/authenticate/corp                               |
   |<------------------------|                                 |
   | GET /saml2/authenticate/corp                               |
   |------------------------>|                                 |
   |                         | tạo AuthnRequest (ID, Issuer,    |
   |                         | Destination, ACS, thời gian)     |
   |                         | ký theo chính sách SP/IdP        |
   |                         | lưu request để so InResponseTo   |
   | 302 Location: IdP SSO + SAMLRequest + SigAlg + Signature   |
   |<------------------------|                                 |
   | GET /saml/sso/redirect?SAMLRequest=...&SigAlg=...          |
   |---------------------------------------------------------->|
   |                         |                    IdP kiểm tra |
   |                         |                    request/binding
   |                         |                    và xác thực user
   | HTML form POST SAMLResponse -> SP ACS                       |
   |<----------------------------------------------------------|
   | POST /login/saml2/sso/corp                                 |
   |------------------------>|                                 |
   |                         | kiểm tra SAMLResponse/assertion  |
   |                         | issuer, chữ ký, audience, ACS,   |
   |                         | thời gian, InResponseTo ...      |
   | Set-Cookie + 302 /private                                 |
   |<------------------------|                                 |
   | GET /private (cookie)    |                                 |
   |------------------------>| kiểm tra session + authorization|
```

Sơ đồ minh họa **HTTP-Redirect request + HTTP-POST response**, không phải mọi triển khai đều dùng cặp này. Một IdP có thể hỗ trợ POST cho `AuthnRequest`; response binding là một lựa chọn giao thức **riêng** được SP/IdP hỗ trợ và công bố trong ACS metadata.

**Trust boundary:** `SAMLRequest` do SP tạo được browser chuyển tới IdP. IdP không tin nội dung request chỉ vì nó có XML hợp lệ; nếu chính sách yêu cầu ký, IdP phải kiểm tra chữ ký bằng khóa công khai **SP đã đăng ký**. Tương tự, `SAMLResponse` do browser POST về SP phải được SP kiểm tra bằng trust của **IdP đã cấu hình**, không sử dụng key từ request của người lạ.

## 4. Đọc IdP metadata để chọn SSO endpoint

### 4.1. `SingleSignOnService` có Binding và Location

IdP metadata có thể khai báo **nhiều** `SingleSignOnService` cùng chức năng nhưng khác binding. Ví dụ fragment:

```xml
<md:IDPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    WantAuthnRequestsSigned="true">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://login.example.org/saml/sso/redirect"/>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://login.example.org/saml/sso/post"/>
</md:IDPSSODescriptor>
```

**Đây là fragment metadata giải thích cấu trúc**, không phải file metadata có thể triển khai độc lập: còn cần entityID, cơ chế phân phối metadata tin cậy và thông tin certificate của IdP/SP theo cấu hình thực. Các ý nghĩa chính:

- `Binding` là URI **cách vận chuyển `AuthnRequest` tới endpoint đó**. Với ví dụ, IdP công bố hai lựa chọn.
- `Location` là **URL đích của IdP** cho binding tương ứng. Không tự thay endpoint Redirect bằng endpoint POST trừ khi IdP công bố/chấp thuận.
- `WantAuthnRequestsSigned="true"` là **chính sách mong đợi của IdP**: IdP muốn SP ký authentication requests. Chi tiết enforcement còn tùy nhà cung cấp, nhưng khi cấu hình hợp đồng nên coi đây là yêu cầu cần đáp ứng.
- Metadata thường còn chứa `KeyDescriptor` để SP kiểm tra chữ ký SAMLResponse/assertion do IdP phát, cùng các dịch vụ logout. Đừng lấy `SingleLogoutService` làm `SingleSignOnService`.

**Cách chọn endpoint:** lấy metadata từ nguồn đã xác thực, tìm IdP entityID đã được duyệt, chọn `SingleSignOnService` mà Spring Security/IdP cùng hỗ trợ theo binding mong muốn, rồi kiểm tra hành vi thực tế. Không suy luận binding từ hậu tố đường dẫn `/redirect` hay `/post`; nguồn quyết định là thuộc tính `Binding`/hợp đồng, không phải tên URL.

### 4.2. Điều gì phải đi cùng metadata?

Tối thiểu cần xác nhận:

1. Đúng **IdP entityID** và tổ chức sở hữu.
2. Đúng **SSO Location và Binding** (có nhiều môi trường sandbox/production).
3. Chính sách ký request: `WantAuthnRequestsSigned` trong metadata **và** policy thực tế IdP; đôi khi cấu hình ứng dụng trên IdP yêu cầu cao hơn metadata công bố.
4. Bộ **IdP signing certificate** đáng tin để SP verify response/assertion.
5. Hợp đồng **SP entityID, ACS Location/Binding và SP signing certificate** đã đăng ký phía IdP.
6. Quy trình đổi certificate và cập nhật metadata: ai được duyệt, khi nào bắt đầu/ngừng tin khóa cũ, quy trình thử nghiệm trước production.

**Không tin metadata tùy ý từ request browser.** Nếu cho người ngoài cung cấp metadata URL/certificate trong một query parameter rồi tạo registration mới, họ có thể ảnh hưởng trust anchor của SP. Việc tin IdP phải là quyết định cấu hình/admin độc lập.

### 4.3. SP metadata: ACS và công bố khả năng ký

Ở phía SP, một fragment metadata có thể trông như sau:

```xml
<md:SPSSODescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol"
    AuthnRequestsSigned="true"
    WantAssertionsSigned="true">
    <md:AssertionConsumerService
        index="0"
        isDefault="true"
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://portal.example.org/login/saml2/sso/corp"/>
</md:SPSSODescriptor>
```

Fragment này cũng được lược để giải thích, chưa có `EntityDescriptor`/`KeyDescriptor` và không đại diện metadata production đầy đủ.

- `AuthnRequestsSigned` trên **SPSSODescriptor** công bố rằng **SP ký AuthnRequest**.
- `WantAuthnRequestsSigned` trên **IDPSSODescriptor** công bố **IdP muốn SP ký AuthnRequest**. Đây là **hai thuộc tính ở hai phía**; tránh đánh tráo chúng.
- `WantAssertionsSigned` là **SP mong IdP ký SAML Assertions**. Nó không tương đương `AuthnRequestsSigned` hoặc chính sách ký AuthnRequest; validation SAML Response/Assertion vẫn cần được cấu hình và kiểm thử riêng.
- `AssertionConsumerService.Binding` mô tả binding **SAMLResponse đi về SP ACS**. Nó không ép `AuthnRequest` phải đi POST.
- Khi SP ký request, metadata cần công bố **SP public signing certificate** phù hợp để IdP verify. **Private signing key của SP không bao giờ nằm trong metadata**.

## 5. Binding: cách chuyển tải AuthnRequest

**Binding** là quy ước biểu diễn SAML message trên HTTP, bao gồm phương thức, encoding và vị trí chữ ký. Hai binding thường gặp là `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect` và `urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST`.

### 5.1. HTTP-Redirect Binding (SP → IdP)

Với `AuthnRequest` theo Redirect binding:

1. SP tạo XML `<samlp:AuthnRequest>`, có các trường ID, IssueInstant, Issuer và thông tin đích.
2. XML được **DEFLATE theo raw DEFLATE**, Base64 encode rồi URL encode thành query parameter `SAMLRequest` theo chuẩn binding.
3. Browser nhận HTTP `302/303 Location` trỏ tới `SingleSignOnService Location` của IdP, mang `SAMLRequest`.
4. Nếu ký request theo **Redirect binding**, SP thêm `SigAlg` và `Signature` vào **query string**. Dữ liệu được ký là chuỗi các tham số **theo thứ tự và encoding chuẩn**, chứ không phải chỉ là XML raw hay toàn bộ URL.
5. IdP decode/decompress và xác minh chữ ký theo binding/policy trước khi chấp nhận request.

Các tên parameter quan trọng:

| Parameter | Vai trò |
| --- | --- |
| `SAMLRequest` | AuthnRequest đã encode để vận chuyển |
| `RelayState` | State dùng để liên kết luồng/chỉ định trang quay về theo quy tắc ứng dụng; tùy chọn |
| `SigAlg` | URI thuật toán chữ ký, ví dụ RSA-SHA256 URI |
| `Signature` | Chữ ký trên chuỗi tham số đã quy định |

Định dạng chuỗi cần ký khi `RelayState` tồn tại:

```text
SAMLRequest=<URL-encoded value>&RelayState=<URL-encoded value>&SigAlg=<URL-encoded value>
```

Khi không có `RelayState`, chuỗi dùng để ký chỉ gồm `SAMLRequest` và `SigAlg` theo thứ tự đó. `Signature` là kết quả mã hóa chữ ký; **không được đưa chính `Signature` vào dữ liệu cần ký**. Các dấu `<URL-encoded value>` ở trên là ký hiệu cú pháp mô tả format, không phải giá trị có thể gửi đi.

**Sai lầm phổ biến:**

- Dùng HTTP Redirect nhưng tìm `<ds:Signature>` bên trong AuthnRequest XML để kết luận “không ký”. Với Redirect binding, **chữ ký thường nằm trong query parameters**.
- Chạy Base64 decode trực tiếp rồi parse XML, quên bước DEFLATE, làm báo lỗi XML sai.
- Tự ghép `SigAlg` và `Signature` bằng encoding không đúng chuẩn, hoặc đảo thứ tự tham số, khiến IdP verify thất bại.
- Coi HTTPS thay thế chữ ký AuthnRequest: TLS bảo vệ đường truyền, nhưng không xác minh thông điệp theo trust policy của IdP.

**Ghi chú URL length:** Redirect binding đặt payload vào URL, nên các proxy/browser có giới hạn độ dài khác nhau. AuthnRequest thông thường tương đối nhỏ, nhưng nếu phải truyền request lớn hoặc yêu cầu IdP cụ thể, cân nhắc POST binding đúng policy thay vì tự cắt XML/giảm validation.

### 5.2. HTTP-POST Binding (SP → IdP)

Với POST binding:

1. SP tạo `AuthnRequest` XML.
2. Nếu request phải được ký, với POST binding chữ ký **thường là XML Digital Signature** trong thông điệp XML, được kiểm tra theo XML Signature/SAML profile.
3. XML (đã ký nếu áp dụng) được Base64 encode thành field `SAMLRequest` trong form POST gửi tới `SingleSignOnService Location` của IdP.
4. Browser gửi POST form đến IdP. `RelayState` có thể là một form field khác.
5. IdP giải mã và xác minh chữ ký XML theo certificate của SP đã đăng ký.

Sơ đồ HTML **minh họa cơ chế**, không nên dùng để tự tạo request production:

```html
<form method="post" action="https://login.example.org/saml/sso/post">
  <input type="hidden" name="SAMLRequest"
         value="PHNhbWxwOkF1dGhuUmVxdWVzdA==">
  <input type="hidden" name="RelayState" value="opaque-state-7"/>
  <button type="submit">Continue SSO</button>
</form>
```

Giá trị `SAMLRequest` trên chỉ là **dữ liệu giả lập**, không phải AuthnRequest có chữ ký, cấu trúc đầy đủ hoặc có thể dùng để đăng nhập. Spring Security sinh và encode form theo binding; đừng đưa logic tạo/đổi chữ ký vào HTML controller tùy biến.

### 5.3. So sánh Redirect và POST

| Tiêu chí | HTTP-Redirect | HTTP-POST |
| --- | --- | --- |
| Phương thức browser → IdP | GET sau redirect | POST của HTML form |
| Chỗ chứa request | `SAMLRequest` query parameter | `SAMLRequest` form field |
| Encoding cơ bản | Raw DEFLATE → Base64 → URL encoding | Base64 của XML |
| Chữ ký request điển hình | `SigAlg` và `Signature` trong query string | `<ds:Signature>` trong XML trước khi Base64 |
| Vấn đề thường gặp | Sai URI-encoding, sai thứ tự dữ liệu ký, độ dài URL | XML signature/reference, form POST/Content Security Policy |
| Điểm khác với response | Chỉ định **request** tới IdP | Cũng chỉ định **request** tới IdP |
| Có làm ACS response tự thành POST? | Không | Không |

**Quan trọng:** Binding của **AuthnRequest** và của **SAMLResponse** là hai quyết định độc lập. Ví dụ phổ biến: Redirect AuthnRequest từ SP tới IdP, rồi POST SAMLResponse từ IdP tới SP. Đừng đổi `acs.binding` sang Redirect chỉ vì `singlesignon.binding=REDIRECT`.

### 5.4. Những binding khác

SAML còn có HTTP-Artifact, SOAP/back-channel và các profile/binding khác. Chúng có cơ chế trao đổi và hỗ trợ thư viện riêng; không coi mọi SSO endpoint chỉ cần đổi enum sang `ARTIFACT` hay `SOAP` là chạy được. Với Spring Security `saml2Login` kiểu Servlet phổ biến, cần đối chiếu chính xác các binding được phiên bản ứng dụng hỗ trợ và metadata IdP.

## 6. AuthnRequest có những trường nào liên quan tới routing và signing?

Đoạn XML minh họa **không chứa chữ ký** để người học đọc cấu trúc trước:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-20261107-a1"
    Version="2.0"
    IssueInstant="2026-11-07T03:10:00Z"
    Destination="https://login.example.org/saml/sso/redirect"
    AssertionConsumerServiceURL="https://portal.example.org/login/saml2/sso/corp"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>https://portal.example.org/saml2/service-provider-metadata/corp</saml:Issuer>
    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
        AllowCreate="true"/>
</samlp:AuthnRequest>
```

| Trường | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| `ID` | Định danh duy nhất của request; IdP có thể phản hồi bằng `InResponseTo` | Dùng lại ID hoặc không lưu request để correlation |
| `Version` | Phiên bản giao thức, thông thường `2.0` | Tự thay sai version |
| `IssueInstant` | Thời điểm tạo AuthnRequest | Clock skew quá lớn; IdP từ chối request cũ/tương lai |
| `Destination` | URL **IdP SSO endpoint** mà request gửi đến | Đặt ACS URL vào Destination |
| `Issuer` | **SP entityID**; ai gửi AuthnRequest | Điền IdP entityID |
| `AssertionConsumerServiceURL` | **SP ACS** mà IdP sẽ gửi response đến | Sai host/HTTPS/path/trailing slash, không khớp metadata |
| `ProtocolBinding` | Binding **mà SP mong nhận SAMLResponse tại ACS** | Nhầm là binding của request gửi đến IdP |
| `AssertionConsumerServiceIndex` | Chỉ số ACS đã đăng ký trong SP metadata, phương án khác với ACS URL | Gửi chỉ số không tồn tại trong metadata |
| `NameIDPolicy` | Định dạng NameID/cho phép tạo theo khả năng IdP | Bắt IdP dùng format không hỗ trợ |
| `ForceAuthn` | Yêu cầu xác thực lại nếu áp dụng | Đặt true mọi lúc gây trải nghiệm đăng nhập lại không cần thiết |
| `IsPassive` | Hạn chế tương tác xác thực khi yêu cầu | Dùng mà không hiểu IdP có thể từ chối request |

Những trường cần nhấn mạnh:

- **`ProtocolBinding=HTTP-POST` không mâu thuẫn với việc gửi AuthnRequest bằng Redirect**, vì trường này mô tả binding *response*.
- `Destination` và `Issuer` hoàn toàn khác nhau: Destination là URL **IdP**, Issuer là định danh logic **SP**.
- `AssertionConsumerServiceURL` trong request phải được IdP tin là ACS hợp lệ của SP; không dùng để ép IdP gửi assertion đến URL tùy ý do browser cung cấp.
- Không gửi đồng thời `AssertionConsumerServiceIndex` và `AssertionConsumerServiceURL` nếu profile/chuẩn quy định lựa chọn thay thế; làm theo metadata và behavior của IdP.
- `RelayState` **không nằm trong AuthnRequest XML** ở các binding HTTP phổ biến; nó là một parameter/field bên ngoài message, cần được tạo và ràng buộc an toàn.
- `InResponseTo` là thuộc tính của response/subject confirmation để gắn về request trước đó, **không phải thuộc tính của AuthnRequest gốc**.

### 6.1. SP phát gì và IdP phải xác minh gì?

Khi IdP yêu cầu signed requests, IdP cần xác minh ít nhất:

1. Request thuộc registration **SP đã đăng ký**; `Issuer` khớp SP entityID.
2. Chữ ký hợp lệ theo binding dùng thật, bằng **SP signing public certificate** đã tin.
3. `Destination`/SSO endpoint phù hợp, request không hết hạn theo chính sách IdP, ID/replay được kiểm soát nếu áp dụng.
4. `AssertionConsumerServiceURL` hoặc `AssertionConsumerServiceIndex` thuộc danh sách ACS đã đăng ký; binding phản hồi hỗ trợ.
5. Các trường như NameIDPolicy/ForceAuthn/RequestedAuthnContext (nếu có) được xử lý theo IdP policy.

Ở chiều ngược lại, SP phải xác minh response/assertion bằng khóa ký của IdP và `Issuer`/`Audience`/`Recipient`/`Destination`/thời gian/`InResponseTo`/chống replay theo policy. **IdP đã xác nhận signed AuthnRequest không miễn trừ validation ở chiều response.**

## 7. Chính sách ký AuthnRequest: ai yêu cầu, ai ký, ai kiểm tra?

### 7.1. Ba khái niệm rất dễ nhầm

| Thuộc tính / cấu hình | Thuộc phía nào | Diễn giải |
| --- | --- | --- |
| `IDPSSODescriptor WantAuthnRequestsSigned` | Metadata của **IdP** | IdP **mong SP ký AuthnRequests** |
| `SPSSODescriptor AuthnRequestsSigned` | Metadata của **SP** | SP **công bố mình ký AuthnRequests** |
| `RelyingPartyRegistration` signing credentials | Cấu hình **SP** | Chứa private key/certificate để SP thực sự **tạo chữ ký** |

Không nên coi một flag trong metadata là “chữ ký đã có”. Chỉ request trên wire có cơ chế signature đúng binding mới chứng minh SP thực sự ký. Hơn nữa, **IdP cần biết trước và tin SP certificate** tương ứng; certificate ở metadata chỉ là dữ liệu được trao đổi, việc tin nguồn metadata vẫn phải được quản trị.

### 7.2. Trường hợp bật/tắt ký và hệ quả

| IdP yêu cầu ký? | SP được cấu hình ký? | SP có signing key hợp lệ? | Kết quả/đánh giá |
| --- | --- | --- | --- |
| Có | Có | Có | Đúng chính sách, nhưng cần kiểm thử thuật toán, certificate và binding |
| Có | Không | Không/có | IdP phải từ chối nếu thực thi chính sách; cần bật ký |
| Có | Có | Không | SP không thể ký đúng; lỗi cấu hình hoặc runtime |
| Không | Có | Có | Có thể hợp lệ; SP có thể yêu cầu ký để tăng assurance nếu IdP hỗ trợ |
| Không | Không | Không | Có thể tương thích nếu hai bên chấp thuận, nhưng đánh giá rủi ro request injection/registration trước khi triển khai |
| Không rõ | Bất kỳ | Bất kỳ | Chưa đủ để đưa production; kiểm tra metadata, tài liệu nhà cung cấp và config ứng dụng IdP |

**Tư duy đúng:** việc “không yêu cầu ký” là một **quyết định policy**, không phải workaround mặc định khi gặp lỗi. Với một số IdP, **SP cũng có thể chủ động yêu cầu ký** dù phía IdP nói không bắt buộc; quyết định thực tế phụ thuộc cả flags và cách Spring Security xử lý ở phiên bản đang dùng.

### 7.3. Hai bộ khóa không được đánh tráo

```text
SP ký AuthnRequest:
  SP private signing key  --ký-->  AuthnRequest
  SP signing certificate  --công bố-->  IdP dùng verify request

IdP ký SAMLResponse / Assertion:
  IdP private signing key --ký-->  Response/Assertion
  IdP signing certificate --công bố--> SP dùng verify response
```

Trong Spring Boot, vì vậy thường có hai nhóm property khác nhau:

- `registration.corp.signing.credentials`: **private key + certificate của SP** để ký request hoặc thông điệp SP được cấu hình ký.
- `registration.corp.assertingparty.verification.credentials`: **public certificate của IdP** để SP xác minh message/assertion do IdP ký.

**Không lấy IdP verification certificate làm private signing key của SP.** Certificate công khai tự nó không thể ký; ký phải có private key tương ứng. Nếu SP có key để ký `AuthnRequest`, secret đó phải được bảo vệ bằng secret management, quyền file, audit và quy trình rotation. Không commit private key vào Git.

### 7.4. Thuật toán và kiểu chữ ký

- Với HTTP-Redirect, chữ ký đặt ở `SigAlg`/`Signature` của **URL query**, dựa trên chuỗi tham số theo đúng SAML binding.
- Với HTTP-POST, việc ký AuthnRequest thường sử dụng **XML Digital Signature** gắn với XML message.
- RSA-SHA256 là lựa chọn thường gặp; thuật toán thực phải tương thích với policy của IdP, JCA/OpenSAML và certificate. Tránh cho phép SHA-1 hoặc thuật toán yếu chỉ để “qua lỗi”.
- Certificate/SP signing key có thể được xoay theo kế hoạch: IdP cần biết public key mới trước khi SP bắt đầu ký bằng private key mới; bảo đảm giai đoạn chuyển đổi và rollback có kiểm soát.
- Metadata mô tả signing algorithms mà IdP hỗ trợ/ưu tiên nếu có; không tự sửa URI `SigAlg` trong request mà vẫn dùng thuật toán khác.

**Quan trọng về wire-level verification:** Một Redirect request đã ký có thể không chứa `<ds:Signature>` trong XML nhưng vẫn hợp lệ. Một POST request XML có `<ds:Signature>` phải được kiểm tra đúng reference/canonicalization; chỉ nhìn thấy tag `Signature` không chứng minh hợp lệ.

## 8. Cấu hình Spring Boot: signed Redirect AuthnRequest

Ví dụ tập trung cho **Spring Boot 3.x / Spring Security 6.x**. Các tên file và URL ở đây chỉ mô tả một môi trường giả lập. Để chạy thật, phải cung cấp khóa/certificate hợp lệ, cấu hình ứng dụng SP tương ứng bên IdP và xác nhận version property hiện dùng.

### 8.1. `application.yml` minh họa

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "{baseUrl}/saml2/service-provider-metadata/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
              binding: POST
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/config/sp-signing.crt"
            assertingparty:
              entity-id: "https://login.example.org/saml/metadata"
              verification:
                credentials:
                  - certificate-location: "file:/run/config/idp-signing.crt"
              singlesignon:
                url: "https://login.example.org/saml/sso/redirect"
                binding: REDIRECT
                sign-request: true
```

Giải thích theo đường dữ liệu:

| Property | Ý nghĩa đúng | Người quản lý nguồn dữ liệu |
| --- | --- | --- |
| `registration.corp` | Registration ID nội bộ để Spring chọn cấu hình IdP/SP | SP |
| `entity-id` | SP entityID (Issuer trong AuthnRequest) | SP và IdP cùng đăng ký |
| `acs.location` | SP ACS để nhận response | SP, phải được IdP tin |
| `acs.binding=POST` | Binding của response vào ACS, độc lập request binding | SP và IdP |
| `signing.credentials[*].private-key-location` | **Khóa riêng SP** cho chữ ký request | SP secret store |
| `signing.credentials[*].certificate-location` | Certificate công khai tương ứng SP signing key | SP, IdP được cung cấp |
| `assertingparty.entity-id` | IdP entityID tin cậy | IdP metadata/registration |
| `assertingparty.verification.credentials[*]` | IdP **public signing cert** để verify response/assertion | IdP metadata đáng tin |
| `assertingparty.singlesignon.url` | **Đích IdP nhận AuthnRequest** | IdP metadata |
| `assertingparty.singlesignon.binding=REDIRECT` | Binding request SP gửi sang IdP | IdP metadata + SP |
| `assertingparty.singlesignon.sign-request=true` | Mong đợi ký AuthnRequest theo cấu hình registration | SP/IdP policy |

**Đừng nhầm “certificate-location” của signing và verification.** Mối quan hệ đủ là: private signing key của SP phải khớp certificate SP đã đăng ký phía IdP; public certificate IdP phải khớp chữ ký Response/Assertion và issuer mà SP tin.

Các chuỗi `{baseUrl}` và `{registrationId}` là **placeholders chuẩn của Spring Security trong URI pattern**, khác với placeholder tự đặt trong bài học. `{baseUrl}` được giải quyết từ public scheme/host/port của request; phía sau reverse proxy cần cấu hình forwarded header đúng để tạo ACS tuyệt đối chính xác.

### 8.2. Class cấu hình Spring Security

Tạo `SamlSpSecurityConfiguration.java` trong source set của ứng dụng Spring Boot có Spring Security và SAML2 Service Provider dependency:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSpSecurityConfiguration {

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

Đây là **class Spring đầy đủ**, nhưng **không phải chương trình Java độc lập chạy bằng `java SamlSpSecurityConfiguration`**. Để hoạt động cần Spring Boot application, dependency SAML2 và các credentials/config thật. `saml2Login()` bật chuỗi filter cho SAML Web SSO; bản thân class không chứa private key hay tự xác minh HTTP Redirect signature của IdP. Spring Security/OpenSAML quản lý việc tạo request và xác thực response theo registration.

Khi điều hướng tới:

```text
GET https://portal.example.org/saml2/authenticate/corp
```

Spring Security chọn registration `corp`, tạo `AuthnRequest`, đưa nó đến `https://login.example.org/saml/sso/redirect` bằng HTTP-Redirect và ký theo chính sách/credentials. Sau login, IdP POST `SAMLResponse` về URL ACS của SP, Spring Security xác minh trước khi tạo `Authentication`.

**Ghi chú về phiên bản:** Các APIs cấu hình SAML được cải tiến qua nhiều bản Spring Security. Kiểm tra Javadoc/Reference của phiên bản đang triển khai, đặc biệt builder APIs và alias properties như `sso-url`/`singlesignon.url`. Luôn kiểm tra **request thực tế** và nội dung metadata đã triển khai thay vì chỉ suy từ YAML.

### 8.3. Chuyển sang POST binding cho AuthnRequest

Nếu IdP metadata/hợp đồng yêu cầu gửi AuthnRequest bằng POST, thay **phần request binding** thành:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              singlesignon:
                url: "https://login.example.org/saml/sso/post"
                binding: POST
                sign-request: true
```

Đây là **fragment ghi đè tương ứng**, không phải toàn bộ cấu hình ứng dụng; cần giữ các mục SP signing/IdP verification/ACS/entityID của ví dụ trước. Sau đổi, trình duyệt phải gửi HTML POST chứa `SAMLRequest` đến URL IdP POST; chữ ký request phải phù hợp **POST/XML Signature**. **Không đổi `acs.binding` theo thói quen:** response vẫn có thể POST về SP như cũ.

### 8.4. Trường hợp IdP cho phép request không ký

Chỉ khi **IdP metadata/policy đã xác nhận** rằng request có thể không ký, SP có thể dùng:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              singlesignon:
                sign-request: false
```

Đoạn này là **fragment thay đổi policy**, không phải một cấu hình ứng dụng hoàn chỉnh. Nếu SP đã cấu hình để **chủ động ký AuthnRequest** (ví dụ dùng builder flag `authnRequestsSigned(true)`), điều đó có thể vẫn khiến request được ký dù IdP không bắt buộc. Chỉ khẳng định “đã không ký” sau khi xác minh dữ liệu phát ra và cấu hình thực tế của version đang chạy.

Lý do tắt ký phải được ghi rõ trong threat model và hợp đồng IdP/SP. Không tắt ký để che lỗi private key, mismatch certificate, sai endpoint hoặc thuật toán yếu.

## 9. Cấu hình qua metadata và Java builder

Spring Security biểu diễn mỗi cặp SP–IdP bằng `RelyingPartyRegistration`, lưu trong `RelyingPartyRegistrationRepository` (ví dụ `InMemoryRelyingPartyRegistrationRepository`). Một registration gói cả:

- **Relying party/SP:** `registrationId`, SP `entityId`, ACS location/binding, signing credentials và decryption credentials nếu dùng.
- **Asserting party/IdP:** IdP `entityId`, SSO service location/binding, `wantAuthnRequestsSigned`, verification credentials và signing algorithms.

### 9.1. Nguồn metadata đáng tin

Sử dụng IdP metadata do bên quản trị đã thẩm định. Ví dụ fragment Java ở Spring Security 6.x khi dự án dùng API `RelyingPartyRegistrations`:

```java
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

// Fragment nằm trong @Bean hoặc phương thức cấu hình.
// Metadata nguồn đã được administrator xác minh.
RelyingPartyRegistration registration =
        RelyingPartyRegistrations
            .fromMetadataLocation("classpath:corp-idp-metadata.xml")
            .registrationId("corp")
            .build();
```

Đây là **fragment**, không phải class Java độc lập. Nó đọc thông tin IdP từ metadata file đã được kiểm soát; ứng dụng vẫn phải đăng ký SP entityID/ACS/certificate, bổ sung **SP signing credentials** nếu ký request, và thiết lập các policy được IdP yêu cầu.

### 9.2. Điều chỉnh request binding và yêu cầu ký

Trên builder APIs thích hợp với phiên bản Spring Security hỗ trợ `assertingPartyMetadata(...)`, có thể chỉ định:

```java
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.saml2.provider.service.registration.Saml2MessageBinding;

// Fragment của bean registration (không phải chương trình chạy độc lập).
RelyingPartyRegistration registration =
        RelyingPartyRegistrations
            .fromMetadataLocation("classpath:corp-idp-metadata.xml")
            .registrationId("corp")
            .assertingPartyMetadata(party -> party
                .singleSignOnServiceBinding(Saml2MessageBinding.POST)
                .wantAuthnRequestsSigned(true))
            .build();
```

Cần xác minh **metadata có SSO POST endpoint thật**; đổi binding mà giữ SSO Redirect URL có thể khiến IdP báo không hỗ trợ. Ví dụ builder trên chưa thêm key ký SP, vì thế khi bật signed request cần cung cấp `signingX509Credentials` cho registration (hoặc cấu hình YAML tương ứng). Trong các phiên bản 6.x cũ, tên builder API có thể dùng `assertingPartyDetails(...)` thay cho `assertingPartyMetadata(...)`; tra tài liệu phiên bản trước khi copy.

**Không nhầm `wantAuthnRequestsSigned(true)` và `authnRequestsSigned(true)`:** một cái là policy phía IdP, một cái thể hiện SP ký request. Spring Security dùng chúng để quyết định tạo chữ ký theo thiết lập. Nếu không chắc trạng thái hiệu lực, xem cấu hình resolved và request trên wire.

## 10. Kiểm tra endpoint và binding sau triển khai

Một cấu hình YAML trông hợp lý vẫn có thể sai do reverse proxy, metadata stale hoặc định dạng chữ ký. Hãy xác minh bằng **IdP kiểm thử** và browser/devtools/trace được bảo vệ, không dùng tài khoản production nhạy cảm.

### 10.1. Kiểm tra thứ tự các bước

**Bước 1 — xác nhận SP đăng ký được khởi tạo:**

- Ứng dụng Spring Boot khởi động và có bean `RelyingPartyRegistrationRepository` với `registrationId=corp`.
- SP `entityId`/ACS tuyệt đối đúng với thông tin IdP đã đăng ký. `https://portal.example.org` khác `http://localhost:8080` và có thể khác do reverse proxy.
- SP signing key có quyền đọc cho tiến trình, format phù hợp và certificate được IdP tin.

**Bước 2 — kích hoạt login:**

```text
GET /saml2/authenticate/corp
```

- Với Redirect binding, quan sát HTTP `302/303` tới **IdP SSO Redirect Location**; query có `SAMLRequest`, và nếu ký thì có `SigAlg`, `Signature` theo binding.
- Với POST binding, quan sát HTML auto-submit/form POST tới **IdP SSO POST Location**; form có `SAMLRequest` và có thể có `RelayState`; signed request phải có XML Signature phù hợp khi giải mã trong **môi trường test**.
- Dù có ký hay không, request `Issuer` phải là SP entityID, `Destination` phải là IdP endpoint, `AssertionConsumerServiceURL` phải là ACS.

**Bước 3 — IdP xác nhận request:**

- IdP chọn đúng SP registration theo Issuer/metadata.
- IdP kiểm tra chữ ký nếu yêu cầu, thuật toán, certificate, ACS URL, request ID/IssueInstant và policy đăng nhập.
- Nếu IdP báo chữ ký sai, **kiểm tra đúng binding/vị trí signature, key và URI encoding trước**; không chuyển sign-request thành false để chữa tạm.

**Bước 4 — kiểm tra response:**

- Browser POST `SAMLResponse` đến SP ACS đã đăng ký.
- Spring Security xác thực chữ ký của IdP, issuer, audience, recipient, thời gian và request correlation/`InResponseTo` khi có.
- Chỉ sau đó tạo `Authentication` và session, chuyển hướng tới tài nguyên yêu cầu ban đầu.

### 10.2. Quan sát request ký theo binding mà không rò credential

| Binding | Dấu hiệu khi signed AuthnRequest | Cách kiểm chứng đúng |
| --- | --- | --- |
| Redirect | URL có `SAMLRequest`, `SigAlg` và `Signature`; XML có thể không chứa `ds:Signature` | Dùng công cụ SAML-test verifier phù hợp Redirect binding và public SP certificate đã đăng ký |
| POST | Form field `SAMLRequest` Base64; XML giải mã chứa XML Signature khi signed | Dùng validator XML/SAML theo đúng reference/canonicalization và SP cert |
| Response vào ACS | `SAMLResponse` form field, thường ở POST ACS | SP kiểm tra bằng **IdP verification certificate** theo cấu hình |

**Lưu ý logging:** `SAMLRequest` có thể chứa thông tin nhận diện tenant/hệ thống và là dữ liệu giao thức. `SAMLResponse` có thể mang assertions và thông tin cá nhân rất nhạy cảm. Không log nguyên payload, `RelayState` bí mật, cookies hay private keys trong production; chỉ dùng trace test đã ẩn dữ liệu, retention ngắn và quyền truy cập hạn chế.

### 10.3. Phân tích request bằng công cụ khi cần

- Với Redirect binding, thứ tự cơ bản: URL decode → Base64 decode → raw DEFLATE inflate để đọc XML. **Kiểm tra chữ ký phải dựa trên chuỗi URL-encoded tham số đúng chuẩn**, không dựa trên XML sau inflate.
- Với POST binding, Base64 decode form field để đọc XML. Kiểm tra XML Signature phải dùng thư viện SAML/XML signature tin cậy; thao tác parse DOM đơn giản chỉ giúp quan sát và không tạo trust.
- Khi xem XML, đối chiếu `Issuer`/`Destination`/`AssertionConsumerServiceURL`/`ProtocolBinding`. Không tự sửa các giá trị trong signed request rồi mong chữ ký vẫn hợp lệ.

## 11. Các lỗi triển khai thường gặp

| Triệu chứng | Khả năng chính | Cách xử lý có kiểm chứng |
| --- | --- | --- |
| IdP báo “Unknown SP”, “Issuer not found” | SP `Issuer/entityID` khác registration IdP | So sánh **SP entityID**, không lấy SSO endpoint làm Issuer |
| IdP báo “Unknown destination” | `Destination` không đúng SSO `Location` hoặc dùng endpoint/binding sai | Đọc metadata, chọn đúng Binding/Location |
| IdP báo “Invalid binding” | Gửi POST vào Redirect endpoint hoặc ngược lại | Kiểm tra request method + metadata + config |
| IdP đòi “signed AuthnRequest” | `WantAuthnRequestsSigned`/policy true nhưng SP chưa ký | Cấu hình SP signing key, public cert phía IdP, sign-request |
| Redirect có `SAMLRequest` nhưng không `Signature`/`SigAlg` | Request chưa ký hoặc policy không bật | Kiểm tra resolved registration và yêu cầu ký |
| Không thấy `<ds:Signature>` trong Redirect XML | Chữ ký nằm trong **query string** | Xác minh bằng Redirect binding verifier |
| XML POST có `ds:Signature` nhưng IdP reject | XML signature/reference/canonicalization/key sai | Xác minh đúng key/alg/profile; dùng OpenSAML |
| SigAlg không hỗ trợ | Không khớp danh sách thuật toán IdP | Chọn RSA-SHA256 hoặc thuật toán được duyệt trong hợp đồng |
| Chứng chỉ IdP dùng ở SP signing credentials | Nhầm chiều key | SP ký bằng SP private key; IdP cert chỉ để SP verify response |
| SP private key không đọc được hoặc cert/key không khớp | Secret mount/format/permission lỗi | Rà đường dẫn, định dạng PKCS#8/cert và quyền truy cập |
| `AssertionConsumerServiceURL` bị HTTP/localhost | Reverse proxy chưa chuyển trusted forwarded headers | Cấu hình public baseUrl, proxy headers tin cậy, metadata ACS |
| IdP báo ACS URL mismatch | SP ACS khác URL đã đăng ký: scheme, host, port, path, slash | So chính xác URL từ request và metadata IdP |
| IdP login thành công nhưng callback 404 | Sai đường dẫn ACS hoặc filter không bắt request | Xác nhận `/login/saml2/sso/{registrationId}` và SecurityFilterChain |
| Callback POST không tìm thấy `AuthnRequest` | Session/state mất, SameSite cookie, load balancer | Kiểm tra session repository, binding POST, cookie, proxy, replication |
| SP từ chối `SAMLResponse` với invalid signature | SP dùng sai IdP verification certificate hoặc response bị sửa | Xác nhận IdP metadata/key rollover; **không tắt verification** |
| Multi-IdP đăng nhập sai tổ chức | Chọn nhầm `registrationId` / tenant registration | Ràng buộc login context và issuer với đúng IdP |
| Metadata đúng trên dev, sai production | Cache metadata cũ, certificate rollover chưa đồng bộ | Kiểm tra nguồn và thời điểm cập nhật, vận hành rollover |
| SSO bị vòng lặp chuyển hướng | Cookie/session bị chặn, ACS mismatch, IdP policy lỗi | Kiểm tra cả request lẫn response, trạng thái session và redirect chain |

### 11.1. Mismatch 401/403/404 và lỗi SAML

HTTP `404` tại ACS thường là routing/filter URL sai; `401`/không tạo principal có thể là lỗi authentication, nhưng Spring Security cũng có thể redirect tới trang login hoặc error handler thay vì trả 401 tùy cấu hình. `403` có thể do CSRF/authorization hoặc các policy khác. **Không suy đoán nguyên nhân chỉ qua HTTP status**: cần kiểm tra chuỗi filter, reason code, logs an toàn và trace liên quan.

### 11.2. SameSite ảnh hưởng SAML POST

Với flow Redirect request rồi **cross-site POST response từ IdP về ACS**, cookie SP được đặt `SameSite=Lax` hoặc `Strict` có thể **không được browser gửi** trong POST. Khi đó kho `HttpSessionSaml2AuthenticationRequestRepository` mặc định có thể không tìm lại request/state để ghép `InResponseTo`.

Điều cần làm:

- Kiểm tra cookie `SameSite`/`Secure` trên browser thực tế và xem POST ACS có gửi cookie session hay không.
- Chọn chiến lược session/correlation phù hợp (ví dụ cookie được phép qua POST bằng `SameSite=None; Secure` trong môi trường phù hợp) và giảm nguy cơ CSRF ở các endpoint khác.
- Nếu chuyển sang cache state ngoài session, đánh giá rủi ro **login fixation/session confusion**: việc lookup qua RelayState hoặc InResponseTo **không tự chứng minh** browser hiện tại đã khởi tạo login. Giữ ràng buộc mạnh với transaction/tenant/session và chống replay.
- Đừng tắt toàn bộ CSRF trên ứng dụng chỉ để POST ACS đi qua; Spring Security có cơ chế xử lý callback SAML chuyên biệt.

## 12. Ranh giới bảo mật và vận hành

### 12.1. HTTPS là cần thiết nhưng không thay chữ ký

- TLS bảo vệ kênh truyền từ browser tới IdP/SP, tránh đọc/sửa thông điệp trên đường truyền.
- Signed AuthnRequest giúp IdP kiểm tra **request thực sự do SP được đăng ký phát ra**, theo policy của IdP.
- Signed Response/Assertion giúp SP kiểm tra **bằng chứng đăng nhập do IdP được tin phát hành**. Một chiều ký không thay thế chiều còn lại.
- RelayState cần được liên kết login transaction và kiểm soát redirect; nó không phải chữ ký trên assertion hay thông tin cho phép redirect đến host tùy ý.
- `InResponseTo` cùng request state, issuer/audience/recipient/time validation hỗ trợ chống login injection và replay. Cần đánh giá thêm anti-replay theo ID cho multi-node SP.

### 12.2. Reverse proxy và public URL

Nếu Spring Boot chạy ở `http://10.0.0.5:8080` sau ingress HTTPS công khai, IdP cần thấy `https://portal.example.org` trong SP ACS/Issuer nơi phù hợp. Mismatch phổ biến:

```text
External request: https://portal.example.org/saml2/authenticate/corp
Internal app:     http://10.0.0.5:8080/saml2/authenticate/corp

Incorrect generated ACS:
  http://10.0.0.5:8080/login/saml2/sso/corp

Expected public ACS:
  https://portal.example.org/login/saml2/sso/corp
```

Cấu hình Spring Boot forwarded-header handling và proxy để chỉ tin các `Forwarded`/`X-Forwarded-*` headers từ **trusted ingress**, không tin headers do client Internet tự gửi. Nếu request host/scheme do client kiểm soát, SP có thể tạo ACS/URL sai hoặc bị redirect/callback confusion.

Đặt `entityId`/ACS theo public deployment và kiểm tra metadata SP thực tế sau deploy. Không sửa bằng cách cho IdP bỏ kiểm tra `Recipient`/`Destination`.

### 12.3. Quản lý khóa và certificate

- Bảo vệ SP signing private key bằng quyền file, secret store, container mount, quản lý truy cập và audit; không log hoặc commit.
- Có lịch rotate certificate/keys; IdP nên hỗ trợ giai đoạn song song theo thỏa thuận để tránh downtime.
- Phân biệt **SP certificate cho request signing** với **IdP certificate cho response verification**; đặt tên file/secret rõ vai trò.
- Theo dõi cảnh báo khi IdP signing key thay hoặc metadata được cập nhật bất thường; chỉ nhận metadata từ nguồn tin cậy.
- Dùng thuật toán ký được hỗ trợ và đủ mạnh; không chấp nhận “verify bằng bất kỳ khóa trong XML `KeyInfo`” thay cho certificate/issuer pinning.

## 13. Bài thực hành Java 17+: mô hình kiểm tra endpoint/binding/sign policy

Để hiểu **quy tắc cấu hình** trước khi tích hợp SAML thật, chương trình Java thuần sau mô phỏng việc kiểm tra URI HTTPS, IdP yêu cầu ký, SP có bật ký và SP có signing key. Nó **không tạo, ký hoặc xác thực SAML XML**. Các cụm `query Signature` và `XML Signature` chỉ là mô tả vị trí chữ ký theo binding.

Tạo `SamlRequestPolicyDemo.java`:

```java
public class SamlRequestPolicyDemo {

    enum Binding { REDIRECT, POST }

    record Settings(
            String idpSsoUrl,
            Binding requestBinding,
            boolean idpRequiresSignature,
            boolean spSigns,
            boolean hasSpSigningKey) {}

    static String inspect(Settings settings) {
        if (!settings.idpSsoUrl().startsWith("https://")) {
            return "reject: insecure SSO URL";
        }
        if (settings.idpRequiresSignature() && !settings.spSigns()) {
            return "reject: IdP requires signed request";
        }
        if (settings.spSigns() && !settings.hasSpSigningKey()) {
            return "reject: SP signing key missing";
        }
        if (!settings.spSigns()) {
            return "accept: unsigned request by policy";
        }
        return settings.requestBinding() == Binding.REDIRECT
                ? "accept: signed Redirect (query Signature)"
                : "accept: signed POST (XML Signature)";
    }

    public static void main(String[] args) {
        Settings redirect = new Settings(
                "https://login.example.org/sso/redirect",
                Binding.REDIRECT, true, true, true);
        Settings post = new Settings(
                "https://login.example.org/sso/post",
                Binding.POST, true, true, true);
        Settings unsigned = new Settings(
                "https://login.example.org/sso/redirect",
                Binding.REDIRECT, true, false, false);
        Settings noKey = new Settings(
                "https://login.example.org/sso/redirect",
                Binding.REDIRECT, true, true, false);

        System.out.println("Redirect: " + inspect(redirect));
        System.out.println("POST: " + inspect(post));
        System.out.println("Unsigned: " + inspect(unsigned));
        System.out.println("No key: " + inspect(noKey));
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac SamlRequestPolicyDemo.java
java SamlRequestPolicyDemo
```

Kết quả stdout chính xác:

```text
Redirect: accept: signed Redirect (query Signature)
POST: accept: signed POST (XML Signature)
Unsigned: reject: IdP requires signed request
No key: reject: SP signing key missing
```

**Hiểu giới hạn demo:**

- Mã xác nhận logic **chính sách ký tối thiểu**, chưa kiểm tra URI có nằm trong metadata thật hay không, certificate, thuật toán, `Issuer`/`Destination`, request replay hoặc XML signature.
- `Redirect` và `POST` đều signed hợp lệ trong **mô hình giả**, nhưng vị trí chữ ký khác nhau.
- `Unsigned` sai vì IdP policy yêu cầu ký; `No key` sai vì không có khóa riêng SP.
- Nếu IdP **không** yêu cầu ký và SP chủ động không ký, chương trình có thể trả `accept: unsigned request by policy`; điều đó chỉ nói về policy giả lập, **không khẳng định mọi hệ thống SSO nên chấp nhận unsigned request**.
- Khi tích hợp thật, để Spring Security/OpenSAML tạo request và chữ ký; không tự biến `inspect()` thành validation filter hoặc dùng nó thay cho framework.

## 14. Kiểm thử tích hợp âm tính và tiêu chí chấp nhận

Thiết lập một IdP **test** và ít nhất hai configuration profiles để chứng minh hệ thống phản ứng đúng với binding/signature.

| Trường hợp | Kỳ vọng |
| --- | --- |
| Đăng ký `corp` với Redirect và ký bật, key hợp lệ | Spring tạo signed Redirect AuthnRequest, IdP nhận và xác minh |
| Thay IdP SSO URL bằng URL không nằm trong metadata | Bị chặn theo policy IdP/hệ thống; không lặng lẽ tin endpoint mới |
| Đăng ký binding Redirect nhưng gửi POST vào endpoint Redirect | IdP từ chối hoặc không hỗ trợ; sửa cấu hình endpoint/binding |
| Bỏ SP signing private key khi IdP bắt ký | Startup/request signing lỗi; không tạo request giả mạo đã ký |
| SP ký bằng key/certificate không được IdP trust | IdP reject signature |
| Thay một byte trong signed Redirect query | IdP reject signature, kể cả XML parse được |
| Đổi `SigAlg` nhưng giữ chữ ký cũ | IdP reject signature |
| Bật HTTP-POST signed request | IdP kiểm tra XML Signature, không đòi query `SigAlg`/`Signature` |
| Chỉ nhìn XML Redirect không thấy `ds:Signature` | Không kết luận unsigned; kiểm tra query đúng binding |
| SP `Issuer/entityID` sai | IdP từ chối SP lạ hoặc không khớp registration |
| ACS URL sai hoặc HTTP sau reverse proxy | IdP reject ACS/Recipient, hoặc SP reject response; sửa public URL |
| Request `ProtocolBinding`=POST, request binding=REDIRECT | Hợp lệ nếu cả IdP/SP hỗ trợ: request Redirect, response POST |
| Cố dùng IdP verification cert làm SP signing credential | Không có private key phù hợp; lỗi ký hoặc IdP reject |
| Thay `registrationId` sang IdP/tenant khác | SP chọn đúng configuration; không nhận SAMLResponse sai issuer/tenant |
| Response/Assertion signature invalid | SP từ chối login, dù AuthnRequest đã ký |
| POST ACS thiếu session correlation | SP từ chối hoặc thực hiện flow fallback đã thiết kế an toàn; không bỏ validation |
| SP signing key được rotate theo lịch | IdP biết certificate mới trước khi SP chuyển; signed request được chấp nhận trong rollout |
| SP metadata công bố ACS/binding và signing cert | Trùng cấu hình IdP đã đăng ký và request thực tế |

### 14.1. Cách viết một integration test hữu ích

Một bài test nên ghi rõ:

- **Given:** IdP metadata/trust source, SP entityID, ACS, binding request/response, chính sách signed/unsigned, signing key và certificate kiểm thử.
- **When:** gọi endpoint `/saml2/authenticate/corp` hoặc gửi callback có/không có response hợp lệ trong hệ thống test.
- **Then:** Redirect dùng `SAMLRequest`/`SigAlg`/`Signature` đúng binding; POST dùng form POST/XML Signature theo policy; IdP/SP chỉ chấp nhận đúng key, đúng issuer, đúng URL và state; sai trường nào reject trường đó.

Không ghi assertions/cookies hay private keys thật vào CI logs. Chỉ lưu fixtures tự tạo cho test, và redact các payload sau khi debug.

### 14.2. Checklist review trước production

- [ ] SSO `Location` lấy từ IdP metadata **đáng tin**; request binding trùng một `SingleSignOnService.Binding` được hỗ trợ.
- [ ] SP `entityID`, ACS Location/Binding và registration ID đều thống nhất với IdP.
- [ ] `WantAuthnRequestsSigned` của IdP và `AuthnRequestsSigned` của SP được hiểu **đúng phía**; hợp đồng yêu cầu ký rõ ràng.
- [ ] Khi cần ký, SP có private signing key và certificate tương ứng; IdP tin public certificate của SP; thuật toán được hai bên duyệt.
- [ ] Khi Redirect signed, request có query `SigAlg`/`Signature` đúng chuẩn; khi POST signed, XML Signature được tạo/kiểm tra đúng.
- [ ] `ProtocolBinding` của AuthnRequest mô tả **response binding**, không bị nhầm với request binding.
- [ ] SP xác thực response/Assertion bằng IdP verification certificate và đầy đủ issuer/audience/recipient/time/request correlation.
- [ ] Public HTTPS URL đúng qua reverse proxy; trusted forwarded headers và SameSite cookie đã được kiểm tra với browser.
- [ ] Không lộ SAMLResponse, cookies, RelayState nhạy cảm, SP private key trong logs/telemetry/repository.
- [ ] Key rotation, metadata updates, failure alerts và test âm tính đã được triển khai.
- [ ] Những thay đổi về binding, ACS và signing policy được test end-to-end trên IdP kiểm thử trước production.

## 15. Câu hỏi ôn tập

**Câu 1.** `SingleSignOnService` của IdP và `AssertionConsumerService` của SP khác nhau như thế nào?  
**Trả lời:** SSO service của **IdP nhận AuthnRequest**; ACS của **SP nhận SAMLResponse**. Chúng có owner, URL và binding riêng.

**Câu 2.** Có thể dùng Redirect để gửi AuthnRequest dù `ProtocolBinding` trong request là HTTP-POST không?  
**Trả lời:** Có. `ProtocolBinding` chỉ **binding SP muốn nhận response**; binding gửi request được chọn qua IdP `SingleSignOnService` và cấu hình SP.

**Câu 3.** Vì sao Redirect signed AuthnRequest có thể không có `<ds:Signature>` trong XML?  
**Trả lời:** Với SAML HTTP-Redirect binding, signature được chuyển thành `SigAlg` và `Signature` query parameters. Phải verify theo quy tắc binding.

**Câu 4.** IdP metadata `WantAuthnRequestsSigned=true`, SP không có private signing key: điều gì sai?  
**Trả lời:** SP không thể tạo signature đúng yêu cầu; cần cấu hình SP key/cert và đăng ký public cert tương ứng phía IdP, không tự tắt policy để bỏ lỗi.

**Câu 5.** Dùng IdP signing certificate ở mục `signing.credentials` của SP có đúng không?  
**Trả lời:** Không. `signing.credentials` cần **private key của SP** và public certificate tương ứng. IdP signing certificate dùng ở `assertingparty.verification.credentials` để verify response/assertion.

**Câu 6.** Bật signed AuthnRequest có làm SP khỏi phải kiểm tra SAMLResponse không?  
**Trả lời:** Không. Request signing là chiều SP→IdP; response/assertion verification là chiều IdP→SP. SP vẫn cần signature/issuer/audience/recipient/time/request correlation và chống replay phù hợp.

**Câu 7.** IdP báo “ACS URL mismatch” và SP tạo `http://localhost:8080/login/saml2/sso/corp` trên production. Sửa ở đâu?  
**Trả lời:** Sửa public base URL/ACS và trusted forwarded headers ở reverse proxy/Spring Boot, đối chiếu metadata SP và cấu hình IdP. Không bỏ kiểm tra Recipient/Destination.

**Câu 8.** Khi nào được đặt `sign-request=false`?  
**Trả lời:** Chỉ khi IdP hỗ trợ/chấp thuận unsigned requests và chính sách bảo mật của hệ thống quyết định như vậy; cần kiểm tra request thực phát và cấu hình RP/IdP nhất quán.

## Tài liệu tham khảo chuẩn

- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) – `AuthnRequest`, `Issuer`, `Destination`, `AssertionConsumerServiceURL`, `ProtocolBinding` và semantics.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf) – HTTP-Redirect/POST transport, encoding, signature placement và `RelayState`.
- [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) – `IDPSSODescriptor`, `SPSSODescriptor`, `SingleSignOnService`, `AssertionConsumerService`, `WantAuthnRequestsSigned`.
- [OASIS SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html) – luồng SP-initiated Redirect/POST và khái niệm tin cậy.
- [Spring Security: Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) – request endpoint, repository/state, binding POST/Redirect và signing policy.
- [Spring Security: SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) – `saml2Login()`, `RelyingPartyRegistration`, credentials, ACS và metadata.
- [Spring Boot: SAML 2.0 Relying Party](https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html) – cấu hình `spring.security.saml2.relyingparty.registration`.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet) – yêu cầu validation chữ ký, issuer, audience, destination và replay.
- [Microsoft Entra ID: SAML protocol](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol) – ví dụ thực tế Redirect AuthnRequest và POST Response.

**Ghi nhớ:** SSO endpoint là **nơi IdP nhận AuthnRequest**, ACS là **nơi SP nhận SAMLResponse**, request binding quyết định cách truyền/chữ ký của `AuthnRequest`, và yêu cầu ký phải được thực thi bằng **private key của SP** cùng public certificate mà IdP đã tin. Chọn đúng endpoint, binding, Issuer, ACS và key sẽ giúp luồng SSO hoạt động an toàn, đồng thời giữ nguyên các kiểm tra response ở phía Spring Security.